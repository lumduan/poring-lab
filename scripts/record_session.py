#!/usr/bin/env python3
"""Record a session for Phase 2 (ADR-0010): lossless GAME_REGION frames + the packet events.

    record_session.py --backend console --label outdoor-a --seconds 1200 --max-bytes 3G
    record_session.py --backend rdp --label calib --seconds 120 [--fps 1] [--out DIR] --max-bytes 2G
    record_session.py --backend console --format png --fps 1 ...        (PNG, still selectable)

* THE DEFAULT FORMAT (Batt, 2026-10-04, C4): console -> raw H.264 with an IDR every 1 s; rdp -> PNG
  (h264 is the S2 client's own bitstream, console only). ADR-0010's 2026-10-04 note has the rates.
* --format h264: no frames are grabbed here. The S2 client writes the bitstream it decodes into its
  recording dir (S2_REC_DIR, a host bind mount: .s2-h264 under the local root, dot-named so
  dataset_ship never lists it), driven by a control file this script writes and re-touches (the
  client's dead-man switch). At the end the client's files move into the session as stream.h264,
  stream.idx.csv (one row per access unit), stream.hash.csv (a hash per decoded frame) and
  stream.done.json. The determinism check runs OFFLINE on the host after shipping
  (scripts/dataset_check.py: every frame against the live checksum); --check additionally runs
  s2spike.h264check in the gamestream container at the end (it contends with the live stream: a
  20-min session's check took ~12 min, so it is off by default).
* Limits the S2 client enforces (s2spike.h264rec.parse_control), checked here up front: at most
  H264_MAX_SECONDS per recording and an 8192 MB cap.

* Frames: GAME_REGION grabbed inside the backend container (ro_agent.Screen: same CLOCK_MONOTONIC
  as the packets), at most --fps, and only when the picture changed (a still scene costs nothing).
  Lossless PNG in WebDataset-style tar shards (poring_dataset.shards).
  In console mode (S2, ADR-0014) the frames come from the S2 frame bus: each record carries the
  bus writer's `bus_frame_id`, `source` and the decode-complete time as `t_mono_ns`, and the
  recording STOPS on the first non-bus frame (an X grab there is a black or foreign picture).
  RDP mode grabs X (`source` x11, `bus_frame_id` -1).
* Packets: after the run, the sniffer's events for [t0 - 5 s, t1 + 5 s], with every name and chat
  line of anyone but the lab's own accounts replaced by an HMAC pseudonym (CLAUDE.md rule 9; the
  salt lives in data/dataset-pseudonym.salt, gitignored, never in a shard).
* Safety: the capture-backend lock must say --backend (ADR-0009); the quant IO guard
  (guarded_build's Guard, tolerant rule) stops the recording on a breach; a hard size cap.
* Sink (ADR-0010): the VM's local disk, /home/batt/poring-lab-rec (never ./data: vision mounts it).
  It is a buffer on the disk shared with live capture, so it is capped -- refused at the start, and
  stopped cleanly mid-recording, when the filesystem has < --min-free-gb free or more than
  --max-unshipped-gb of sessions wait under the root. scripts/dataset_ship.py ships them to the
  TrueNAS cold store (checksummed, verified, then deleted locally). A warning during SET hours.
"""

import argparse
import gzip
import hashlib
import hmac
import importlib.util
import io
import json
import os
import re
import secrets
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import dataset_ship  # noqa: E402
import lab_servers  # noqa: E402
import measure_delay  # noqa: E402
import ro_agent as r  # noqa: E402

from poring_backend.capture_lock import read_lock  # noqa: E402
from poring_dataset.shards import ShardWriter, write_manifest  # noqa: E402
from poring_dataset.timeline import session_events  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
SALT = ROOT / "data" / "dataset-pseudonym.salt"
RECORDER_VERSION = 5  # v5: h264 by default on console; v4: --format h264 + cpu; v3: bus ids (S2)
H264_MAX_SECONDS = 3570  # the client's time cap is 3600 s; we ask for seconds + 30
H264_MAX_MB = 8192  # the client's size cap
CAP_CHECK_S = 5.0  # how often the local caps are re-checked while recording
GAMESTREAM = "poring-lab-gamestream-1"
BACKEND = "poring-lab-backend-1"
H264_ID = re.compile(r"^[0-9]{8}T[0-9]{6}-[a-z0-9][a-z0-9-]{0,47}$")  # s2spike.h264rec.ID_RE
TOUCH_S = 3.0  # the control file's dead-man touch (the client stops it after 15 s)


def rec_dir(out: Path) -> Path:
    """The S2 client's recording dir on the host (compose.dev.yaml mounts it at /s2-rec)."""
    return Path(os.environ.get("S2_REC_DIR") or out / ".s2-h264")


def container_cpu_usec(name: str) -> int | None:
    cid = subprocess.run(["docker", "inspect", "-f", "{{.Id}}", name], capture_output=True,
                         text=True, check=False).stdout.strip()  # fmt: skip
    stat = Path(f"/sys/fs/cgroup/system.slice/docker-{cid}.scope/cpu.stat")
    if not cid or not stat.exists():
        return None
    for line in stat.read_text().splitlines():
        if line.startswith("usage_usec "):
            return int(line.split()[1])
    return None


class CpuMeter:
    """Average cores of the lab containers and of this process over the recording (C3)."""

    def __init__(self) -> None:
        self.t0 = time.monotonic()
        self.c0 = {n: container_cpu_usec(n) for n in (GAMESTREAM, BACKEND)}
        self.self0 = os.times()

    def cores(self) -> dict[str, float | None]:
        wall = time.monotonic() - self.t0
        out: dict[str, float | None] = {}
        for name, before in self.c0.items():
            after = container_cpu_usec(name)
            short = name.removeprefix("poring-lab-").removesuffix("-1")
            out[short] = (None if before is None or after is None or wall <= 0
                          else round((after - before) / 1e6 / wall, 3))  # fmt: skip
        t = os.times()
        used = (t.user - self.self0.user) + (t.system - self.self0.system)
        out["recorder_process"] = round(used / wall, 3) if wall > 0 else None
        return out


def load_guard() -> Any:
    spec = importlib.util.spec_from_file_location(
        "guarded_build", ROOT / "scripts" / "guarded_build.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.Guard(module.cgroup_paths(), 10.0, 10.0, sustain=30.0, spike=25.0)


def parse_size(text: str) -> int:
    m = re.fullmatch(r"(\d+)([KMG]?)", text.upper())
    if m is None:
        raise SystemExit(f"bad size {text!r}")
    return int(m.group(1)) * {"": 1, "K": 1 << 10, "M": 1 << 20, "G": 1 << 30}[m.group(2)]


def pseudonymiser() -> Any:
    SALT.parent.mkdir(parents=True, exist_ok=True)
    if not SALT.exists():
        SALT.write_text(secrets.token_hex(32))
        SALT.chmod(0o600)
    key = bytes.fromhex(SALT.read_text().strip())
    env = r.env()
    lab = {env.get("RATHENA_GM_CHAR", ""), env.get("RATHENA_AGENT_CHAR", "")} - {""}

    def name(value: str) -> str:
        if not value or value in lab:
            return value
        return "p_" + hmac.new(key, value.encode(), hashlib.sha256).hexdigest()[:10]

    def event(e: dict[str, Any]) -> dict[str, Any]:
        e = dict(e)
        if e.get("type") == "entity_appear" and e.get("objtype") == 0:
            e["name"] = name(str(e.get("name", "")))
        if e.get("type") == "chat":
            speaker = str(e.get("speaker") or "")
            if speaker not in lab:
                e["speaker"] = name(speaker)
                e["text"] = "<pseudonymised>"
                e["raw_hex"] = ""
        return e

    return event


LOOKBACK_S = 30 * 60  # how far before t0 to look for the anchor (the last map change)


def packets_for(t0_ns: int, t1_ns: int) -> list[dict[str, Any]]:
    """The sniffer's events for [t0 - 5 s, t1 + 5 s] (the measurement window)."""
    return _events_since(t0_ns, 5, t0_ns - 5_000_000_000, t1_ns)


def session_packets(t0_ns: int, t1_ns: int) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    """A recording's events: from the last map change before t0 (so the player's position and the
    entities already on screen are known) through t1 + 5 s. See timeline.session_events."""
    events = _events_since(t0_ns, LOOKBACK_S + 5, t0_ns - (LOOKBACK_S + 5) * 1_000_000_000, t1_ns)
    return session_events(events, t0_ns, t1_ns, lookback_ns=LOOKBACK_S * 1_000_000_000)


def _events_since(t0_ns: int, back_s: float, lo_ns: int, t1_ns: int) -> list[dict[str, Any]]:
    since_wall = time.time() - (r.ns() - t0_ns) / 1e9
    files = measure_delay.events_files(since_wall - back_s)
    if not files:
        return []
    raw = subprocess.run(
        ["docker", "exec", lab_servers.sniffer(), "cat", *files], capture_output=True, check=True
    ).stdout
    out: list[dict[str, Any]] = []
    with gzip.GzipFile(fileobj=io.BytesIO(raw)) as fh:
        try:
            for line in fh:
                e = json.loads(line)
                if lo_ns <= int(e.get("t_mono_ns", 0)) <= t1_ns + 5_000_000_000:
                    out.append(e)
        except EOFError:
            pass
    return out


def record(a: argparse.Namespace) -> dict[str, Any]:
    lock = read_lock(ROOT / "state")
    if lock.backend != a.backend or lock.phase != "steady":
        raise r.Stop(f"the lock says {lock.backend}/{lock.phase}, not {a.backend}/steady")
    import bench  # the same config + hash as the benchmark

    caps = {"min_free": int(a.min_free_gb * 1e9), "max_unshipped": int(a.max_unshipped_gb * 1e9)}
    unshipped = dataset_ship.unshipped_bytes(a.out)
    refused = dataset_ship.local_caps(a.out, unshipped=unshipped, **caps)
    if refused:
        raise r.Stop(f"not recording: {refused}")
    if dataset_ship.in_set_hours():
        print("WARNING: SET hours -- the quant stack is busiest now; the IO guard stays armed",
              file=sys.stderr)  # fmt: skip
    config = bench.run_config(a.backend)
    chash = bench.benchlib.config_hash(config)
    session_id = f"{time.strftime('%Y%m%dT%H%M%S')}-{a.backend}-{a.label}"
    out = a.out / session_id
    if a.format == "h264":
        return record_h264(a, lock, config, chash, session_id, out, caps, unshipped)
    writer = ShardWriter(out, png_level=a.png_level)
    cpu = CpuMeter()
    guard = load_guard()
    gx, gy, gw, gh = r.game_region()
    period = 1.0 / a.fps
    screen = r.Screen()
    stop_reason = "duration"
    t0 = r.ns()
    t_end = time.monotonic() + a.seconds
    prev: np.ndarray | None = None
    frame_id = skipped = repeats = 0
    last_bus_id = -1
    sources: dict[str, int] = {}
    next_cap_check = time.monotonic() + CAP_CHECK_S
    try:
        with subprocess.Popen(["ionice", "-c3", "-p", str(os.getpid())]) as p:
            p.wait()
        next_t = time.monotonic()
        while time.monotonic() < t_end:
            t_cap, img, bus_id, source = screen.grab_meta(gx, gy, gw, gh)
            sources[source] = sources.get(source, 0) + 1
            if a.backend == "console" and source != "bus":
                stop_reason = "non_bus_frame: the S2 frame bus went away (console mode)"
                break
            bgr = img[:, :, :3].copy()
            if source == "bus" and bus_id == last_bus_id:
                repeats += 1  # no new decoded frame since the last grab
            elif prev is not None and np.array_equal(bgr, prev):
                skipped += 1
            else:
                writer.add(frame_id, t_cap, bgr, t_wall=time.strftime("%FT%T%z"),
                           bus_frame_id=bus_id, source=source)  # fmt: skip
                frame_id += 1
                prev = bgr
            last_bus_id = bus_id
            if writer.bytes > a.max_bytes:
                stop_reason = "size_cap"
                break
            hit = guard.breach()
            if hit:
                stop_reason = f"io_guard: {hit[0]} {hit[1]:.1f}% ({hit[2]})"
                break
            if time.monotonic() >= next_cap_check:
                next_cap_check += CAP_CHECK_S
                full = dataset_ship.local_caps(
                    a.out, unshipped=unshipped, extra=writer.bytes, **caps
                )
                if full:
                    stop_reason = f"local_cap: {full}"
                    break
            next_t += period
            time.sleep(max(0.0, next_t - time.monotonic()))
    finally:
        writer.close()
        screen.close()
    t1 = r.ns()
    cpu_cores = cpu.cores()
    freezes = freeze_report(t0, t1)
    events, anchor = write_packets(out, t0, t1)
    seconds = (t1 - t0) / 1e9
    manifest = {
        "session_id": session_id, "recorder_version": RECORDER_VERSION,
        "backend": a.backend, "server": lab_servers.server(), "lock_seq": lock.seq,
        "config": config, "config_hash": chash,
        "game_region": [gx, gy, gw, gh], "fps_cap": a.fps, "png_level": a.png_level,
        "shards": writer.shards,
        "frames": writer.frames, "unchanged_skipped": skipped, "bus_repeats": repeats,
        "frame_sources": sources, "bytes": writer.bytes,
        "t0_mono_ns": t0, "t1_mono_ns": t1, "seconds": round(seconds, 1),
        "mb_per_min": round(writer.bytes / 1e6 / max(seconds / 60, 1e-9), 1),
        "stop_reason": stop_reason, "guard": guard.summary(), "packet_events": len(events),
        "packet_anchor": anchor, "pseudonymised": True, "freezes": freezes,
        "sink": {"root": str(a.out), **caps}, "format": "png", "cpu_cores": cpu_cores,
    }  # fmt: skip
    write_manifest(out, manifest)
    keys = ("frames", "bytes", "mb_per_min", "stop_reason", "packet_events", "cpu_cores")
    return {"dir": str(out), **{k: manifest[k] for k in keys}}


def write_control(directory: Path, text: str) -> None:
    tmp = directory / ".control.tmp"
    tmp.write_text(text + "\n")
    tmp.replace(directory / "control")
    if (directory / "control").read_text().strip() != text:
        raise r.Stop("the S2 recorder's control file did not read back")


def h264_freezes(idx: Path) -> dict[str, Any] | None:
    """Freeze spans from the recording's own index (the decode-complete time of every frame)."""
    from poring_env.freshness import FREEZE_MS, freeze_spans

    times = []
    with idx.open() as f:
        next(f)
        for line in f:
            parts = line.rstrip("\n").split(",")
            if len(parts) == 10 and int(parts[1]) >= 0:
                times.append(int(parts[9]))
    if len(times) < 2:
        return None
    spans = freeze_spans(times, FREEZE_MS)
    return {"threshold_ms": FREEZE_MS, "frames": len(times), "count": len(spans),
            "max_ms": round(max(((b - c) / 1e6 for c, b in spans), default=0.0), 1),
            "spans_ns": [[c, b] for c, b in spans]}  # fmt: skip


def record_h264(
    a: argparse.Namespace, lock: Any, config: dict[str, Any], chash: str, session_id: str,
    out: Path, caps: dict[str, int], unshipped: int,
) -> dict[str, Any]:  # fmt: skip
    if a.backend != "console":
        raise r.Stop("--format h264 records the S2 client's bitstream: console mode only")
    if not H264_ID.match(session_id):
        raise r.Stop("--format h264: the label must be lowercase letters, digits and '-'")
    rec = rec_dir(a.out)
    if not rec.is_dir():
        raise r.Stop(f"{rec} does not exist (the S2 recording dir; compose.dev.yaml S2_REC_DIR)")
    for stale in rec.glob(f"*{session_id}*"):
        raise r.Stop(f"{stale} already exists")
    guard = load_guard()
    gx, gy, gw, gh = r.game_region()
    max_mb = a.max_bytes / 1e6
    part = rec / f".{session_id}.h264"
    cpu = CpuMeter()
    stop_reason = "duration"
    t0 = r.ns()
    write_control(rec, f"start {session_id} {a.idr_every:g} {a.seconds + 30:.0f} {max_mb:.0f}")
    try:
        deadline = time.monotonic() + 5
        while not part.exists():
            if time.monotonic() > deadline:
                raise r.Stop("the S2 client did not start the recording in 5 s (is it streaming "
                             "with --h264-rec? docker logs poring-lab-gamestream-1)")  # fmt: skip
            time.sleep(0.2)
        t_end = time.monotonic() + a.seconds
        next_touch = next_cap = time.monotonic()
        while time.monotonic() < t_end:
            now = time.monotonic()
            if now >= next_touch:
                os.utime(rec / "control")  # the dead-man touch
                next_touch = now + TOUCH_S
            if not part.exists():
                stop_reason = "the client ended the recording (stream end or cap)"
                break
            hit = guard.breach()
            if hit:
                stop_reason = f"io_guard: {hit[0]} {hit[1]:.1f}% ({hit[2]})"
                break
            if now >= next_cap:
                next_cap = now + CAP_CHECK_S
                full = dataset_ship.local_caps(a.out, unshipped=unshipped,
                                               extra=part.stat().st_size, **caps)  # fmt: skip
                if full:
                    stop_reason = f"local_cap: {full}"
                    break
            time.sleep(0.5)
    finally:
        write_control(rec, "stop")
    done = rec / f"{session_id}.done.json"
    deadline = time.monotonic() + 60
    while not done.exists():
        if time.monotonic() > deadline:
            raise r.Stop(f"the S2 client did not finish {session_id} in 60 s")
        time.sleep(0.5)
    t1 = r.ns()
    cpu_cores = cpu.cores()
    summary = json.loads(done.read_text())
    check = None
    if a.check:
        cmd = ["docker", "exec", GAMESTREAM, "python3", "-m", "s2spike.h264check",
               f"/s2-rec/{session_id}"]  # fmt: skip
        res = subprocess.run(cmd, capture_output=True, text=True, check=False)
        lines = res.stdout.strip().splitlines()
        check = json.loads(lines[-1]) if lines else {"error": res.stderr[-400:]}
        check["exit"] = res.returncode
    out.mkdir(parents=True)
    for kind in ("h264", "idx.csv", "hash.csv", "check.json", "done.json"):
        src = rec / f"{session_id}.{kind}"
        if src.exists():
            src.rename(out / f"stream.{kind}")  # same filesystem: a rename, no copy
    events, anchor = write_packets(out, t0, t1)
    seconds = (t1 - t0) / 1e9
    size = (out / "stream.h264").stat().st_size
    manifest = {
        "session_id": session_id, "recorder_version": RECORDER_VERSION, "format": "h264",
        "backend": a.backend, "server": lab_servers.server(), "lock_seq": lock.seq,
        "config": config, "config_hash": chash,
        "game_region": [gx, gy, gw, gh], "idr_every_s": a.idr_every, "shards": [],
        "frames": summary.get("frames"), "bytes": size, "t0_mono_ns": t0, "t1_mono_ns": t1,
        "seconds": round(seconds, 1), "mb_per_min": round(size / 1e6 / max(seconds / 60, 1e-9), 1),
        "stop_reason": stop_reason, "guard": guard.summary(), "packet_events": len(events),
        "packet_anchor": anchor, "pseudonymised": True,
        "freezes": h264_freezes(out / "stream.idx.csv"), "stream": summary, "check": check,
        "cpu_cores": cpu_cores, "sink": {"root": str(a.out), **caps},
    }  # fmt: skip
    write_manifest(out, manifest)
    keys = ("frames", "bytes", "mb_per_min", "stop_reason", "packet_events", "cpu_cores")
    return {"dir": str(out), **{k: manifest[k] for k in keys}, "check": check}


def freeze_report(t0: int, t1: int) -> dict[str, Any] | None:
    """Freeze spans of the S2 stream over [t0, t1] (the frame-age guard, 2026-10-04): gaps above
    FREEZE_MS between consecutive decoded frames, from the S2 client's per-frame log. None in RDP
    mode or when the log is unavailable (stated, never guessed)."""
    from poring_env.freshness import FREEZE_MS, freeze_spans

    cmd = ["docker", "exec", "poring-lab-gamestream-1", "cat", "/tmp/s2spike/frames.csv"]
    res = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if res.returncode != 0:
        return None
    times = []
    for line in res.stdout.splitlines()[1:]:
        parts = line.split(",")
        if len(parts) == 9 and parts[7].isdigit() and t0 <= int(parts[7]) <= t1:
            times.append(int(parts[7]))
    if len(times) < 2:
        return None
    spans = freeze_spans(times, FREEZE_MS)
    return {
        "threshold_ms": FREEZE_MS, "frames": len(times), "count": len(spans),
        "max_ms": round(max(((b - a) / 1e6 for a, b in spans), default=0.0), 1),
        "spans_ns": [[a, b] for a, b in spans],
    }  # fmt: skip


def write_packets(
    out: Path, t0: int, t1: int
) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    events, anchor = session_packets(t0, t1)
    pseudo = pseudonymiser()
    with gzip.open(out / "packets.jsonl.gz", "wt") as fh:
        for e in events:
            fh.write(json.dumps(pseudo(e), sort_keys=True) + "\n")
    return events, anchor


def repack(session: Path) -> dict[str, Any]:
    """Rebuild a session's packets.jsonl.gz from the sniffer's archive (kept 7 days) with the
    current window rule, and update the manifest. Frames are untouched."""
    manifest = json.loads((session / "manifest.json").read_text())
    events, anchor = write_packets(session, manifest["t0_mono_ns"], manifest["t1_mono_ns"])
    manifest.update(
        packet_events=len(events), packet_anchor=anchor, recorder_version=RECORDER_VERSION
    )
    write_manifest(session, manifest)
    return {"dir": str(session), "packet_events": len(events), "packet_anchor": anchor}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--repack", type=Path, help="rebuild an existing session's packets file")
    ap.add_argument("--backend", choices=["rdp", "console"])
    ap.add_argument(
        "--server", choices=sorted(lab_servers.SNIFFERS), default=None,
        help="which server's sniffer holds the packets (default: $PORING_SERVER or lab-rathena)",
    )  # fmt: skip
    ap.add_argument("--label")
    ap.add_argument("--seconds", type=float, default=120.0)
    ap.add_argument("--fps", type=float, default=1.0, help="png: the frame rate cap (Batt: 1)")
    ap.add_argument(
        "--format",
        choices=["png", "h264"],
        default=None,
        help="default: h264 on console (Batt 2026-10-04), png on rdp",
    )
    ap.add_argument(
        "--idr-every",
        type=float,
        default=1.0,
        help="h264: ask for an IDR every N s (default 1; 0 = never)",
    )
    ap.add_argument(
        "--check",
        dest="check",
        action="store_true",
        help="h264: also run s2spike.h264check in gamestream at the end (contends with the stream)",
    )
    ap.add_argument(
        "--png-level", type=int, choices=range(0, 10), default=1,
        help="zlib level of the lossless PNGs: 1 fast (default), 6 smaller and slower",
    )  # fmt: skip
    ap.add_argument("--out", type=Path, default=dataset_ship.LOCAL_ROOT)
    ap.add_argument(
        "--max-bytes",
        type=parse_size,
        required=True,
        help="hard size cap for this session, e.g. 12G (explicit: no default)",
    )
    ap.add_argument(
        "--min-free-gb",
        type=float,
        default=dataset_ship.MIN_FREE_BYTES / 1e9,
        help="refuse / stop below this much free space on --out's filesystem",
    )
    ap.add_argument(
        "--max-unshipped-gb",
        type=float,
        default=dataset_ship.MAX_UNSHIPPED_BYTES / 1e9,
        help="refuse / stop above this much unshipped data under --out",
    )
    a = ap.parse_args()
    lab_servers.select(a.server)  # every packet read below uses this server's sniffer
    if a.repack:
        print(json.dumps(repack(a.repack)))
        return 0
    if not a.backend or not a.label:
        raise r.Stop("--backend and --label are required to record")
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", a.label):
        raise r.Stop("label: letters, digits, _ . - only")
    if str(a.out.resolve()).startswith(str((ROOT / "data").resolve())):
        raise r.Stop("never under ./data: vision mounts it (ADR-0010)")
    resolve_format(a)
    print(json.dumps(record(a)))
    return 0


def resolve_format(a: argparse.Namespace) -> None:
    """The default format per backend (Batt 2026-10-04: h264 on console, png on rdp), and the
    S2 client's own limits checked up front (it silently ignores an out-of-range start)."""
    if a.format is None:
        a.format = "h264" if a.backend == "console" else "png"
    if a.format != "h264":
        return
    if a.seconds > H264_MAX_SECONDS:
        raise r.Stop(f"--format h264: at most {H264_MAX_SECONDS} s per recording")
    if a.max_bytes / 1e6 > H264_MAX_MB:
        raise r.Stop(f"--format h264: --max-bytes at most {H264_MAX_MB} MB (the client's cap)")
    if not 0 <= a.idr_every <= 60:
        raise r.Stop("--idr-every: 0..60 s")


if __name__ == "__main__":
    sys.exit(main())
