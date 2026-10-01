"""Offline re-decode of banked captures (ADR-0007): pcapng (+ its clock samples) -> events JSONL.

    python -m poring_packets.replay capture-A.pcapng [capture-B.pcapng ...] \\
        [--validation-aid 2000002 ...] [--client-ip 192.168.1.169] > events.jsonl

Why: raw packets are banked so the decoder can be fixed after the fact. On 2026-10-01 the entity
identity was wrong (char_id instead of block id); replaying the morning's pcapng through the fixed
decoder recovers correct entities without re-playing the game.

Files are processed in the order given, so connections that span an hourly rotation keep their
reassembly and framing state. The pcapng is redacted (client -> login payloads are zeroed after the
packet id, so login ids and passwords are gone): validation sessions are tagged by ACCOUNT id
instead (`--validation-aid`; the server's AC_ACCEPT_LOGIN and the client's CH/CZ_ENTER carry it
unredacted).
"""

import argparse
import json
import struct
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from pydantic import TypeAdapter

from poring_packets.capture import CLIENT_IP, parse_frame
from poring_packets.clock import Sample
from poring_packets.events import PacketEvent
from poring_packets.pcapng import CUSTOM_BLOCK, PEN
from poring_packets.sniffer import Session
from poring_packets.tables import load as load_table

EPB = 0x00000006
_EVENT: TypeAdapter[PacketEvent] = TypeAdapter(PacketEvent)


def read_blocks(path: Path) -> Iterator[tuple[str, Any]]:
    """("clock", sample dict) and ("packet", (t_real_ns, frame)) in file order. A truncated tail
    (the newest file is still being written) ends the iteration quietly."""
    data = path.read_bytes()
    pos = 0
    while pos + 12 <= len(data):
        btype, total = struct.unpack_from("<II", data, pos)
        if total < 12 or pos + total > len(data):
            return
        body = data[pos + 8 : pos + total - 4]
        if btype == EPB and len(body) >= 20:
            _iface, hi, lo, caplen, _orig = struct.unpack_from("<IIIII", body, 0)
            yield "packet", ((hi << 32) | lo, body[20 : 20 + caplen])
        elif btype == CUSTOM_BLOCK and len(body) >= 4 and struct.unpack_from("<I", body)[0] == PEN:
            yield "clock", json.loads(body[4:].rstrip(b"\0"))
        pos += total


def replay(paths: list[Path], session: Session) -> Iterator[PacketEvent]:
    for path in paths:
        for kind, value in read_blocks(path):
            if kind == "clock":
                session.clock.add(Sample(**{k: int(v) for k, v in value.items()}))
                continue
            t_real, frame = value
            seg = parse_frame(frame, t_real)
            if seg is not None:
                yield from session.feed(seg)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("pcapng", nargs="+", type=Path)
    ap.add_argument("--validation-aid", type=int, action="append", default=[])
    ap.add_argument("--client-ip", default=CLIENT_IP)
    a = ap.parse_args()
    session = Session(load_table(), a.client_ip, set())
    session.validation_aids.update(a.validation_aid)
    out = sys.stdout
    for ev in replay(a.pcapng, session):
        out.write(json.dumps(_EVENT.dump_python(ev, mode="json"), separators=(",", ":")) + "\n")


if __name__ == "__main__":
    main()
