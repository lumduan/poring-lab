"""The sniffer: capture -> pcapng (+ clock samples); decode -> events -> JSONL.gz + backend ingest.

OFFLINE GROUND TRUTH ONLY (ADR-0007). Run (dev overlay, in rathena's network namespace):
    python -m poring_packets.sniffer
Environment:
    CAPTURE_IFACE     eth0
    CAPTURE_DIR       /captures            (the `captures` volume; never ./data)
    INGEST_URL        ws://backend:8001/ingest/packets ("" = no live feed)
    VALIDATION_USERIDS comma-separated login ids of validation (GM) accounts -- never logged
Every second it also sends the backend an ATTESTATION (ADR-0016): is a map session from the Dell
live, for which account id, how old is its last packet -- the interlock's session signal, never
world data.
Rotation: pcapng and events every hour or 256 MB. Retention: 7 days or 20 GB, oldest first.
"""

import gzip
import json
import logging
import os
import queue
import re
import signal
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pydantic import TypeAdapter

from poring_packets.capture import PORT_SERVER, Capture, TcpSegment, parse_frame
from poring_packets.clock import ClockMap, take_sample
from poring_packets.decode import Decoded, decode, is_gm_command, text
from poring_packets.events import GM_WINDOW_NS, Attestation, PacketEvent, PacketStats
from poring_packets.framing import RoFramer, TcpReassembler
from poring_packets.pcapng import LOGIN_PORTS_ENV, LoginScrub, PcapngWriter, login_ports
from poring_packets.tables import LengthTable
from poring_packets.tables import load as load_table
from poring_packets.world import World

log = logging.getLogger("poring_packets.sniffer")
_EVENT: TypeAdapter[PacketEvent] = TypeAdapter(PacketEvent)
ROTATE_S = 3600
ROTATE_BYTES = 256 << 20
RETAIN_S = 7 * 86400
RETAIN_BYTES = 20 << 30
# A map connection counts as live while it is open and its last packet is this recent. The client
# talks to the map server at least every ~10-12 s even when idle (its time sync), so 60 s is a
# generous bound for "still connected", and the TCP FIN/RST is the fast signal.
SESSION_LIVE_S = 60


@dataclass
class Conn:
    server: str
    reasm: dict[str, TcpReassembler]
    framers: dict[str, RoFramer]
    aid: int | None = None
    validation: bool = False
    gm_until_ns: int = 0
    last_unknown: dict[int, int] = field(default_factory=dict)
    last_skipped: int = 0
    last_seen_ns: int = 0  # monotonic time of the last segment either way (the attestation)
    closed: bool = False  # a FIN or RST was seen


class Session:
    """Pure decoding state: TCP segments in, packet events out (no IO; unit-tested)."""

    def __init__(
        self,
        table: LengthTable,
        client_ip: str,
        validation_userids: set[str],
        server_id: str | None = None,
    ) -> None:
        self.table, self.client_ip = table, client_ip
        self.server_id = server_id or None  # the attestation's `server` (SNIFFER_SERVER_ID)
        self.validation_userids = validation_userids
        self.validation_aids: set[int] = set()
        self.conns: dict[tuple[str, int, int], Conn] = {}
        self.world = World()
        self.clock = ClockMap()
        self.tcp_gaps = 0

    def _conn(self, seg: TcpSegment, direction: str) -> Conn | None:
        cport, sport = (seg.sport, seg.dport) if direction == "cs" else (seg.dport, seg.sport)
        server = PORT_SERVER.get(sport)
        if server is None:
            return None
        key = (self.client_ip, cport, sport)
        if seg.syn and direction == "cs":
            self.conns.pop(key, None)  # a new connection on a reused port
        conn = self.conns.get(key)
        if conn is None:
            conn = Conn(
                server,
                {"cs": TcpReassembler(), "sc": TcpReassembler()},
                {
                    "cs": RoFramer(self.table, server, "cs"),
                    "sc": RoFramer(
                        self.table, server, "sc", raw_prefix=4 if server == "char" else 0
                    ),
                },
            )
            self.conns[key] = conn
        return conn

    def feed(self, seg: TcpSegment) -> list[PacketEvent]:
        direction = "cs" if seg.src == self.client_ip else "sc"
        conn = self._conn(seg, direction)
        if conn is None:
            return []
        reasm = conn.reasm[direction]
        data = reasm.feed(seg.seq, seg.payload, syn=seg.syn)
        self.tcp_gaps = sum(r.gaps for c in self.conns.values() for r in c.reasm.values())
        framer = conn.framers[direction]
        t_mono = self.clock.to_mono(seg.t_real_ns) if self.clock.samples else 0
        conn.last_seen_ns = max(conn.last_seen_ns, t_mono)
        if seg.fin_or_rst:
            conn.closed = True
        out: list[PacketEvent] = []
        for pkt in framer.feed(data, seg.t_real_ns):
            self._identify(conn, direction, pkt.packet_id, pkt.data)
            d = decode(conn.server, direction, pkt.packet_id, pkt.data)
            if d is None:
                continue
            gm = is_gm_command(d) and direction == "cs"
            if gm:
                conn.gm_until_ns = t_mono + GM_WINDOW_NS
            out.append(self._event(d, conn, direction, pkt.packet_id, t_mono, gm))
        out += self._counter_events(conn, direction, t_mono)
        if seg.fin_or_rst and direction == "cs":
            pass  # keep the conn until a new SYN reuses the port (late segments still frame)
        return out

    def _identify(self, conn: Conn, direction: str, pid: int, b: bytes) -> None:
        """Bind sessions to an account id; mark validation (GM) accounts. Login ids never leave."""
        if conn.server == "login" and direction == "cs" and pid == 0x0064 and len(b) >= 30:
            conn.validation = text(b[6:30]) in self.validation_userids
        elif conn.server == "login" and direction == "sc" and pid == 0x0AC4 and len(b) >= 12:
            conn.aid = int.from_bytes(b[8:12], "little")
            if conn.validation:
                self.validation_aids.add(conn.aid)
        elif direction == "cs" and pid in (0x0065, 0x0436) and len(b) >= 6:
            conn.aid = int.from_bytes(b[2:6], "little")
            conn.validation = conn.aid in self.validation_aids
            if conn.server == "map":
                self.world.aid = conn.aid

    def _event(
        self, d: Decoded, conn: Conn, direction: str, pid: int, t_mono: int, gm: bool
    ) -> PacketEvent:
        self.world.apply(d.type, d.fields)
        payload: dict[str, Any] = {
            "type": d.type,
            **d.fields,
            "t_mono_ns": t_mono,
            "server": conn.server,
            "dir": direction,
            "packet_id": pid,
            "validation_account": conn.validation,
            "gm_command": gm or (t_mono <= conn.gm_until_ns and conn.gm_until_ns > 0),
        }
        return _EVENT.validate_python(payload)

    def _counter_events(self, conn: Conn, direction: str, t_mono: int) -> list[PacketEvent]:
        stats = conn.framers[direction].stats
        out: list[PacketEvent] = []
        for pid, n in stats.unknown_ids.items():
            new = n - conn.last_unknown.get(pid, 0)
            if new > 0:
                out.append(_EVENT.validate_python({
                    "type": "unknown", "count": new, "t_mono_ns": t_mono, "server": conn.server,
                    "dir": direction, "packet_id": pid, "validation_account": conn.validation,
                }))  # fmt: skip
                conn.last_unknown[pid] = n
        if stats.skipped_bytes > conn.last_skipped:
            out.append(_EVENT.validate_python({
                "type": "desync", "skipped_bytes": stats.skipped_bytes - conn.last_skipped,
                "t_mono_ns": t_mono, "server": conn.server, "dir": direction, "packet_id": 0,
                "validation_account": conn.validation,
            }))  # fmt: skip
            conn.last_skipped = stats.skipped_bytes
        return out

    def attestation(self, t_mono: int) -> Attestation:
        """The interlock's session signal: the most recent open map connection from the Dell."""
        live = [c for c in self.conns.values()
                if c.server == "map" and not c.closed and c.last_seen_ns
                and t_mono - c.last_seen_ns <= SESSION_LIVE_S * 1_000_000_000]  # fmt: skip
        newest = max(live, key=lambda c: c.last_seen_ns, default=None)
        return Attestation(
            t_mono_ns=t_mono,
            client_ip=self.client_ip,
            session_live=newest is not None and newest.aid is not None,
            aid=None if newest is None else newest.aid,
            last_packet_age_ms=(None if newest is None
                                else max(0, (t_mono - newest.last_seen_ns) // 1_000_000)),
            map_conns=len(live),
            server=self.server_id,
        )  # fmt: skip

    def stats(self, t_mono: int) -> PacketStats:
        framers = [f for c in self.conns.values() for f in c.framers.values()]
        tick = (t_mono // 1_000_000) % (1 << 32)  # gettick = CLOCK_MONOTONIC ms (verified live)
        pos = self.world.self_position(tick)
        st = self.world.stats
        return PacketStats(
            t_mono_ns=t_mono,
            packets=sum(f.stats.packets for f in framers),
            unknown=sum(sum(f.stats.unknown_ids.values()) for f in framers),
            desyncs=sum(f.stats.desyncs for f in framers),
            skipped_bytes=sum(f.stats.skipped_bytes for f in framers),
            tcp_gaps=self.tcp_gaps,
            clock_steps=self.clock.steps,
            map=self.world.map,
            self_x=pos[0] if pos else None,
            self_y=pos[1] if pos else None,
            entities=len(self.world.entities),
            hp=st.get("hp"),
            max_hp=st.get("max_hp"),
            sp=st.get("sp"),
            max_sp=st.get("max_sp"),
        )


class Ingest(threading.Thread):
    """Best-effort live feed to the backend: a bounded queue, drops COUNTED, reconnects quietly."""

    def __init__(self, url: str) -> None:
        super().__init__(daemon=True, name="ingest")
        self.url = url
        self.q: queue.Queue[str] = queue.Queue(maxsize=10000)
        self.dropped = 0

    def put(self, line: str) -> None:
        try:
            self.q.put_nowait(line)
        except queue.Full:
            self.dropped += 1

    def run(self) -> None:
        from websockets.sync.client import connect

        while True:
            try:
                with connect(self.url, open_timeout=5, max_size=2**20) as ws:
                    log.info("ingest connected")
                    while True:
                        ws.send(self.q.get())
            except Exception as exc:  # noqa: BLE001 -- reconnect on anything, never crash capture
                log.warning("ingest unavailable (%s); retrying in 5 s", type(exc).__name__)
                time.sleep(5)


class Rotating:
    """pcapng + events shard, rotated by age or size; enforces retention after each rotation."""

    def __init__(self, root: Path) -> None:
        self.root = root
        root.mkdir(parents=True, exist_ok=True)
        self.pcap: PcapngWriter | None = None
        self.events: gzip.GzipFile | None = None
        self.opened = 0.0

    def ensure(self) -> tuple[PcapngWriter, gzip.GzipFile]:
        now = time.time()
        if (
            self.pcap is None
            or self.events is None
            or now - self.opened >= ROTATE_S
            or (self.pcap.bytes >= ROTATE_BYTES)
        ):
            self.close()
            stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime(now))
            self.pcap = PcapngWriter(self.root / f"capture-{stamp}.pcapng")
            self.events = gzip.open(self.root / f"events-{stamp}.jsonl.gz", "ab")  # noqa: SIM115
            self.opened = now
            self.retention()
        return self.pcap, self.events

    def retention(self) -> None:
        files = sorted(
            (p for p in self.root.iterdir() if p.is_file()), key=lambda p: p.stat().st_mtime
        )
        total = sum(p.stat().st_size for p in files)
        now = time.time()
        current = {self.pcap.path.name if self.pcap else ""}
        for p in files:
            if p.name in current or p.name.endswith(".map.jsonl"):
                continue
            too_old = now - p.stat().st_mtime > RETAIN_S
            if too_old or total > RETAIN_BYTES:
                total -= p.stat().st_size
                p.unlink()
                log.info("retention: removed %s", p.name)

    def close(self) -> None:
        if self.pcap:
            self.pcap.close()
        if self.events:
            self.events.close()
        self.pcap, self.events = None, None


def run() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    iface = os.environ.get("CAPTURE_IFACE", "eth0")
    root = Path(os.environ.get("CAPTURE_DIR", "/captures"))
    url = os.environ.get("INGEST_URL", "ws://backend:8001/ingest/packets")
    userids = {u for u in os.environ.get("VALIDATION_USERIDS", "").split(",") if u}
    # WHICH server this sniffer watches (its rathena's netns): the interlock requires the
    # environment id to match (2026-10-05). No id, no start: an unnamed session never goes green.
    server_id = os.environ.get("SNIFFER_SERVER_ID", "").strip()
    if not re.fullmatch(r"[a-z0-9-]{1,64}", server_id):
        raise SystemExit("SNIFFER_SERVER_ID must name this sniffer's server (an environment id)")
    table = load_table()
    session = Session(table, os.environ.get("CLIENT_IP", "192.168.1.169"), userids, server_id)
    scrub = LoginScrub(login_ports(os.environ.get(LOGIN_PORTS_ENV)))
    log.info("pcap credential scrub: %s", scrub.mode)
    cap = Capture(iface)
    out = Rotating(root)
    ingest = Ingest(url) if url else None
    if ingest:
        ingest.start()
    stop = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    log.info("capturing on %s into %s (validation accounts: %d)", iface, root, len(userids))
    next_tick = 0.0
    try:
        while not stop.is_set():
            now = time.monotonic()
            if now >= next_tick:
                sample = take_sample()
                if session.clock.add(sample):
                    log.warning("realtime clock step detected")
                pcap, events = out.ensure()
                pcap.clock_sample({"mono_ns": sample.mono_ns, "real_ns": sample.real_ns,
                                   "read_ns": sample.read_ns})  # fmt: skip
                stats = session.stats(time.monotonic_ns())
                if ingest:
                    stats = stats.model_copy(update={"ingest_dropped": ingest.dropped})
                    ingest.put(stats.model_dump_json())
                    ingest.put(session.attestation(time.monotonic_ns()).model_dump_json())
                pcap.flush()
                events.flush()
                next_tick = now + 1.0
            got = cap.read(0.2)
            if got is None:
                continue
            frame, t_real = got
            seg = parse_frame(frame, t_real)
            if seg is None:
                continue
            pcap, events = out.ensure()
            pcap.packet(scrub(seg), t_real)
            for ev in session.feed(seg):
                line = json.dumps(_EVENT.dump_python(ev, mode="json"), separators=(",", ":"))
                events.write(line.encode() + b"\n")
                if ingest:
                    ingest.put(line)
    finally:
        out.close()
        cap.close()


if __name__ == "__main__":
    run()
