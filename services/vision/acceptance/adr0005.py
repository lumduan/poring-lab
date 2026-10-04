"""ADR-0005's acceptance test, run INSIDE the vision container (Batt approved vision S2-only +
option c2, 2026-10-04):

    python3 scripts/guarded_build.py --sustain 30 --spike 25 \
        'run:vision@120=python /opt/acceptance/adr0005.py'

Every row must PASS for ADR-0005 to close on the S2 path. Row 4 needs a live S2 frame bus; without
one it reports SKIP and the test exits 3 (rows 1-3 + 5 still decide the rest).

  1. no X: the :99 socket is absent (no XTEST, no CLIPBOARD, no screen reads);
  2. the backend's PUBLIC listener refuses this network: /ws/input, /transfer/files, /health
     -- with and without a forged Origin;
  3. /internal/agent works (the mux is the one way in);
  4. Env.grab() on the bus: frames with rising frame_ids at >= the agent's rate;
  5. the network is closed: the agent gateway's host ports and the LAN are unreachable.
"""

import json
import os
import socket
import sys
import time
import urllib.error
import urllib.request

BACKEND = "backend"
ORIGIN_FORGED = "http://192.168.1.13:3000"
TIMEOUT = 3.0


def row1_no_x() -> tuple[str, str]:
    path = "/tmp/.X11-unix/X99"
    if os.path.exists(path):
        return "FAIL", f"{path} exists in vision"
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        s.connect(path)
        return "FAIL", "connected to the X socket"
    except OSError as exc:
        return "PASS", f"no X socket ({exc.strerror})"
    finally:
        s.close()


def _http(path: str, origin: str | None) -> str:
    req = urllib.request.Request(f"http://{BACKEND}:8000{path}")
    if origin:
        req.add_header("Origin", origin)
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            return f"HTTP {resp.status}"
    except urllib.error.HTTPError as exc:
        return f"HTTP {exc.code}"
    except OSError as exc:
        return f"unreachable ({type(exc).__name__})"


def _ws(path: str, origin: str | None) -> str:
    from websockets.exceptions import InvalidStatus, WebSocketException
    from websockets.sync.client import connect

    headers = {"Origin": origin} if origin else {}
    try:
        with connect(f"ws://{BACKEND}:8000{path}", additional_headers=headers,
                     open_timeout=TIMEOUT) as ws:  # fmt: skip
            ws.recv(timeout=TIMEOUT)
            return "ACCEPTED"
    except InvalidStatus as exc:
        return f"refused ({exc.response.status_code})"
    except (WebSocketException, OSError, TimeoutError) as exc:
        return f"refused ({type(exc).__name__})"


def row2_public_refused() -> tuple[str, str]:
    results = {}
    for origin in (None, ORIGIN_FORGED):
        tag = "forged-origin" if origin else "no-origin"
        results[f"ws /ws/input {tag}"] = _ws("/ws/input", origin)
        results[f"GET /transfer/files {tag}"] = _http("/transfer/files", origin)
        results[f"GET /health {tag}"] = _http("/health", origin)
    bad = {k: v for k, v in results.items() if v == "ACCEPTED" or v.startswith("HTTP 2")}
    return ("FAIL" if bad else "PASS"), json.dumps(results)


def row3_internal_agent() -> tuple[str, str]:
    from websockets.sync.client import connect

    from poring_env.clock import monotonic_ns
    from poring_env.protocol import AgentHello

    try:
        with connect(f"ws://{BACKEND}:8001/internal/agent", open_timeout=TIMEOUT) as ws:
            hello = AgentHello(t_mono_ns=monotonic_ns(), agent_id="adr0005", version="acceptance")
            ws.send(hello.model_dump_json())
            msg = json.loads(ws.recv(timeout=5))
            return "PASS", f"connected; first message type {msg.get('type')!r}"
    except Exception as exc:  # noqa: BLE001 -- the row's verdict carries the reason
        return "FAIL", f"{type(exc).__name__}: {exc}"


def row4_grab_bus(seconds: float = 5.0) -> tuple[str, str]:
    from poring_env.bus_source import BusFrameSource
    from poring_env.framebus import FrameBusError

    rate = float(os.environ.get("AGENT_HZ", "10"))
    try:
        src = BusFrameSource(os.environ.get("FRAMEBUS_RING", "/framebus/ring"), "adr0005")
        status = src.reader.writer()
    except (FrameBusError, OSError) as exc:
        return "SKIP", f"no frame bus ({exc})"
    if status.heartbeat_age_s > 2:
        return "SKIP", f"no live writer (heartbeat {status.heartbeat_age_s:.0f} s ago)"
    ids, end = [], time.monotonic() + seconds
    while time.monotonic() < end:
        ids.append(src.grab().frame_id)
    src.close()
    rising = all(b > a for a, b in zip(ids, ids[1:], strict=False))
    fps = len(ids) / seconds
    ok = rising and fps >= rate
    detail = f"{len(ids)} frames in {seconds:.0f} s ({fps:.1f}/s), rising={rising}"
    return ("PASS" if ok else "FAIL"), detail


def row5_closed_network() -> tuple[str, str]:
    # With gateway_mode_ipv4=isolated the host takes NO address on the agent bridge (10.210.97.1 is
    # a container -- the backend). So probe the host where it does live: its LAN address, the
    # default compose bridge's host side, docker0 -- and the outside world.
    targets = [("192.168.1.13", 22), ("192.168.1.13", 8000), ("192.168.1.13", 11434),
               ("10.210.96.1", 22), ("172.17.0.1", 22), ("192.168.1.1", 53),
               ("1.1.1.1", 443)]  # fmt: skip
    reached = []
    for host, port in targets:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(TIMEOUT)
        try:
            s.connect((host, port))
            reached.append(f"{host}:{port}")
        except OSError:
            pass
        finally:
            s.close()
    try:
        socket.gethostbyname("one.one.one.one")
        reached.append("external DNS")
    except OSError:
        pass
    return ("FAIL" if reached else "PASS"), (f"reached {reached}" if reached else "all closed")


def main() -> int:
    rows = {
        "1 no X": row1_no_x(),
        "2 public listener refused": row2_public_refused(),
        "3 /internal/agent works": row3_internal_agent(),
        "4 Env.grab on the bus": row4_grab_bus(),
        "5 network closed": row5_closed_network(),
    }
    print(json.dumps({k: {"verdict": v[0], "detail": v[1]} for k, v in rows.items()}, indent=1))
    verdicts = [v[0] for v in rows.values()]
    if "FAIL" in verdicts:
        return 1
    return 3 if "SKIP" in verdicts else 0


if __name__ == "__main__":
    sys.exit(main())
