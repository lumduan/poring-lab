"""The sniffer's START-TIME self-test (ADR-0007 Amendment C, ACCEPTED by Batt 2026-10-13).

In dev mode the sniffer's code comes from the host tree (read-only, copied into the container's
tmpfs at each start), not from a built and table-checked image. So the checks the image build made
run at START, before the socket opens, and the sniffer REFUSES to start (exit 1) when either fails:

1. **The length table:** `tables.load()` checks `_generated/lengths.json` against
   `tables.lock.json`, as the Dockerfile's build step does.
2. **The credential scrub:** for every id in LOGIN_REQUEST_IDS, a synthetic client -> server
   segment carrying that id and a DUMMY secret, on a configured login port AND on a port that is
   not one (the shape rule), plus a continuation segment on the same connection. Every dummy byte
   must come out zeroed. A broken edit to LoginScrub therefore cannot start, so it never writes a
   real password.

    python -m poring_packets.selftest      prints one line per check; exit 0 PASS, 1 REFUSED
"""

from __future__ import annotations

import os
import sys
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from poring_packets.pcapng import LOGIN_PORTS_ENV, LOGIN_REQUEST_IDS, LoginScrub, login_ports

DUMMY = b"POR1NG-SELFTEST-NOT-A-SECRET!"  # a recognisable dummy; never a real credential
HEADER = 54  # Ethernet 14 + IPv4 20 + TCP 20: where the synthetic payload starts
OTHER_PORT = 5121  # a port that is not a login port (rathena's map port)


@dataclass(frozen=True)
class Segment:
    """The fields LoginScrub reads from a capture.TcpSegment."""

    src: str
    sport: int
    dst: str
    dport: int
    frame: bytes
    payload: bytes
    payload_offset: int


def _segment(dport: int, sport: int, payload: bytes) -> Segment:
    frame = b"\x11" * HEADER + payload
    return Segment("10.0.0.2", sport, "10.0.0.1", dport, frame, payload, HEADER)


def scrub_failures(scrub_factory: Callable[[frozenset[int] | None], Any] = LoginScrub,
                   ports: frozenset[int] | None = None) -> list[str]:  # fmt: skip
    """Every way the scrub lets a dummy secret through (empty = PASS). ``ports``: the configured
    login ports (None = unknown, shape only); the login-port case uses the first of them."""
    fails: list[str] = []
    login_port = min(ports) if ports else None
    for n, rid in enumerate(sorted(LOGIN_REQUEST_IDS)):
        head = rid.to_bytes(2, "little")
        cases = [("shape", OTHER_PORT)]
        if login_port is not None:
            cases.append(("port", login_port))
        for what, port in cases:
            scrub = scrub_factory(ports)
            sport = 40000 + n * 2 + (what == "port")
            first = scrub(_segment(port, sport, head + DUMMY))
            more = scrub(_segment(port, sport, DUMMY))  # a continuation segment
            if DUMMY[:8] in first[HEADER:] or any(first[HEADER + 2 :]):
                fails.append(f"0x{rid:04x} on {what} port {port}: the first segment kept bytes")
            if any(more[HEADER:]):
                fails.append(f"0x{rid:04x} on {what} port {port}: a continuation kept bytes")
            if first[:HEADER] != b"\x11" * HEADER:
                fails.append(f"0x{rid:04x} on {what} port {port}: the headers were changed")
    return fails


def table_failure() -> str | None:
    """None when the length table loads and matches tables.lock.json; else why not."""
    try:
        from poring_packets.tables import load

        load()
    except Exception as exc:  # noqa: BLE001 -- any failure refuses the start
        return f"{type(exc).__name__}: {exc}"
    return None


def main() -> int:
    commit = os.environ.get("SNIFFER_COMMIT", "") or "unrecorded"
    ports = login_ports(os.environ.get(LOGIN_PORTS_ENV))
    fails = scrub_failures(ports=ports)
    table = table_failure()
    print(f"selftest: code {commit}; login ports {sorted(ports) if ports else 'UNKNOWN'}")
    print(f"selftest: length table {'OK' if table is None else 'REFUSED: ' + table}")
    print(f"selftest: credential scrub {'OK' if not fails else 'REFUSED'} "
          f"({len(LOGIN_REQUEST_IDS)} login ids x {2 if ports else 1} port kinds)")  # fmt: skip
    for f in fails[:10]:
        print(f"selftest:   {f}")
    if table is not None or fails:
        print("selftest: REFUSED -- the sniffer does not start", flush=True)
        return 1
    print("selftest: PASS", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
