"""Stream + input probe against a running backend -- the seed of Phase 0 (capture FPS, latency).

    uv run python scripts/ws_probe.py --backend http://192.168.1.13:8000 --seconds 5
    uv run python scripts/ws_probe.py --backend http://192.168.1.13:8000 --input-probe

Stream: counts frames on /ws/stream, checks every JPEG follows its FrameMeta and that frame ids
increase, and reports backend-clock latencies (capture->encode, encode->send). Input: sends one
mouse_move through /ws/input (no Origin header, so not treated as a browser) and reads the pointer
back from /health. Prints a JSON summary; exits 1 on any failed check.
"""

import argparse
import json
import statistics
import sys
import time
import urllib.request
from typing import Any

from websockets.sync.client import connect

from poring_env.protocol import FrameMeta, MouseMove, Ping, parse_backend_to_browser
from poring_env.x11 import to_pixels


def pct(values: list[float], q: float) -> float:
    return round(statistics.quantiles(values, n=100)[int(q) - 1], 2) if len(values) >= 2 else 0.0


def probe_stream(ws_base: str, seconds: float) -> dict[str, Any]:
    frames: list[FrameMeta] = []
    cap_to_enc: list[float] = []
    enc_to_send: list[float] = []
    arrivals: list[float] = []
    stray_binaries = 0
    size_mismatches = 0
    with connect(f"{ws_base}/ws/stream", max_size=2**24, open_timeout=5) as ws:
        pending: FrameMeta | None = None
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            try:
                raw = ws.recv(timeout=max(0.01, deadline - time.monotonic()))
            except TimeoutError:
                break
            if isinstance(raw, bytes):
                if pending is None:
                    stray_binaries += 1
                    continue
                if len(raw) != pending.nbytes or raw[:2] != b"\xff\xd8":
                    size_mismatches += 1
                frames.append(pending)
                arrivals.append(time.monotonic())
                cap_to_enc.append((pending.t_encoded_ns - pending.t_capture_ns) / 1e6)
                enc_to_send.append((pending.t_mono_ns - pending.t_encoded_ns) / 1e6)
                pending = None
                continue
            msg = parse_backend_to_browser(raw)
            if isinstance(msg, FrameMeta):
                pending = msg
    ids = [f.frame_id for f in frames]
    elapsed = arrivals[-1] - arrivals[0] if len(arrivals) > 1 else 0.0
    gaps = [1000 * (b - a) for a, b in zip(arrivals, arrivals[1:], strict=False)]
    return {
        "frames": len(frames),
        "fps": round((len(frames) - 1) / elapsed, 2) if elapsed > 0 else 0.0,
        "size": f"{frames[0].width}x{frames[0].height}" if frames else None,
        "frame_ids_increasing": all(b > a for a, b in zip(ids, ids[1:], strict=False)),
        "frames_skipped_by_backend": (ids[-1] - ids[0] + 1 - len(ids)) if ids else 0,
        "stray_binaries": stray_binaries,
        "size_mismatches": size_mismatches,
        "capture_to_encode_ms": {"p50": pct(cap_to_enc, 50), "p95": pct(cap_to_enc, 95)},
        "encode_to_send_ms": {"p50": pct(enc_to_send, 50), "p95": pct(enc_to_send, 95)},
        "arrival_gap_ms": {"p50": pct(gaps, 50), "p95": pct(gaps, 95)},
        "_size": (frames[0].width, frames[0].height) if frames else None,
    }


def probe_input(http_base: str, ws_base: str, size: tuple[int, int]) -> dict[str, Any]:
    x, y = 0.25, 0.5
    with connect(f"{ws_base}/ws/input", open_timeout=5) as ws:
        ws.send(MouseMove(t_mono_ns=time.monotonic_ns(), x=x, y=y).model_dump_json())
        ws.send(Ping(t_mono_ns=time.monotonic_ns()).model_dump_json())
        t0 = time.monotonic()
        while json.loads(ws.recv(timeout=5))["type"] != "pong":  # pong => move was applied
            pass
        rtt_ms = 1000 * (time.monotonic() - t0)
    with urllib.request.urlopen(f"{http_base}/health", timeout=5) as resp:
        health = json.load(resp)
    expected = list(to_pixels(x, y, *size))
    return {
        "sent": [x, y],
        "expected_pointer": expected,
        "pointer": health.get("pointer"),
        "pointer_ok": health.get("pointer") == expected,
        "rtt_ms": round(rtt_ms, 2),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--backend", default="http://127.0.0.1:8000", help="backend base URL")
    ap.add_argument("--seconds", type=float, default=3.0)
    ap.add_argument("--min-frames", type=int, default=30)
    ap.add_argument("--input-probe", action="store_true", help="also check the input round trip")
    args = ap.parse_args()

    http_base = args.backend.rstrip("/")
    ws_base = http_base.replace("http", "ws", 1)
    report: dict[str, Any] = {"stream": probe_stream(ws_base, args.seconds)}
    size = report["stream"].pop("_size")
    stream = report["stream"]
    ok = (
        stream["frames"] >= args.min_frames
        and stream["frame_ids_increasing"]
        and stream["stray_binaries"] == 0
        and stream["size_mismatches"] == 0
    )
    if args.input_probe:
        report["input"] = probe_input(http_base, ws_base, size or (1280, 720))
        ok = ok and report["input"]["pointer_ok"]
    report["ok"] = ok
    print(json.dumps(report, indent=2))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
