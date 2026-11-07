"""The live detector's GPU forward pass (docs/planning/gpu-live-detector.md option A; ADR-0005
Amendment 2026-11-07: Batt "เลือก A" and "อนุมัติให้ใช้ gpu แทน cpu ในการ detect ของ bot ได้เลย").

    python -m poring_vision.detect_server --socket /detect/detect.sock \\
        --model v1=/datasets/archive/train/v1png-20261008/weights/last.pt=<sha256> \\
        --model xmas02=/datasets/archive/train/xmas02-20261106/weights/last.pt=<sha256> \\
        [--imgsz 736 1280] [--max-hz 10]

It runs only as a guarded ``execdev:vision`` step inside the long-lived worker (R1-R3: the VRAM
cap, the paired pause windows, the IO guard). ``scripts/unit_detector.py serve-cmd`` prints the
step with the pinned weights.

FRAMES IN, NUMBERS OUT through ONE unix socket in the host RAM directory only the worker mounts
(``/detect``). The host (``scripts/unit_detector.GpuDetector``) is the only client and does the
letterbox, the decoding, the NMS and the class names with the same code as its CPU worker; this
process runs only the model's forward pass, FP32, and returns the head's raw output. No input, no
X, no network, no packet data.

Protocol, one client at a time, per connection:
  1. hello: one JSON line {"v": 1, "model": NAME} from the client. The reply is one JSON line,
     {"ok": true, "model": NAME, "sha256": ..., "imgsz": [H, W], "shape": [1, C, N]}, or
     {"ok": false, "error": ...} and the connection closes.
  2. each frame: an 8-byte header ``<HHI`` (H, W, 0), then H*W*3 uint8 BGR bytes: the
     letterboxed canvas at exactly the model's input size. The reply is one JSON line
     {"shape": [1, C, N], "ms": forward ms}, then C*N float32 little-endian bytes.
Anything malformed closes the connection. Weights load only from ``--model``, each checked against
its sha256 BEFORE it is unpickled. ``--max-hz`` bounds the GPU load whatever the client does.
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import os
import signal
import socket
import stat
import statistics
import struct
import sys
import threading
import time
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any, Protocol

import numpy as np

PROTOCOL = 1
HEADER = struct.Struct("<HHI")
IMGSZ = (736, 1280)  # every deployed model's input (h, w), as the CPU ONNX files
MAX_HZ = 10.0  # the rate bench_gpu's phase B measured beside Frigate (cpu-detector-speed.md 8)
IDLE_S = 60.0  # a connection silent this long is closed (the client reconnects at once)
MSG_S = 5.0  # a started message must arrive whole within this
HELLO_MAX = 512
STATS_EVERY_S = 60.0


class Net(Protocol):
    sha256: str
    shape: tuple[int, int, int]

    def forward(self, canvas: np.ndarray) -> np.ndarray: ...


def parse_models(items: Sequence[str]) -> dict[str, tuple[str, str]]:
    """PURE: ["NAME=PATH=SHA256", ...] -> {name: (path, sha256)}; names distinct, sha256 hex-64."""
    out: dict[str, tuple[str, str]] = {}
    for item in items:
        name, _, rest = item.partition("=")
        path, _, sha = rest.rpartition("=")
        ok_sha = len(sha) == 64 and all(c in "0123456789abcdef" for c in sha)
        if not name or not path or not ok_sha or name in out:
            raise SystemExit(f"--model {item!r}: NAME=PATH=SHA256 (64 hex), each name once")
        out[name] = (path, sha)
    return out


def file_sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


class TorchNet:
    """One YOLO checkpoint's fused model on the GPU, FP32 (bench_gpu's forward)."""

    def __init__(self, path: str, sha256: str, device: str,
                 imgsz: tuple[int, int] = IMGSZ) -> None:  # fmt: skip
        got = file_sha256(path)
        if got != sha256:  # never unpickle a file that is not the pinned one
            raise SystemExit(f"{path}: sha256 {got[:12]}... is not the pinned {sha256[:12]}...")
        import torch
        from ultralytics import YOLO

        self.torch, self.device, self.sha256 = torch, device, sha256
        self.net = YOLO(path).model.fuse().to(device).eval()
        with torch.inference_mode():
            for _ in range(5):  # warm the kernels; the shape comes from the first call
                y = self._run(np.full((*imgsz, 3), 114, np.uint8))
        self.shape = (int(y.shape[0]), int(y.shape[1]), int(y.shape[2]))

    def _run(self, canvas: np.ndarray) -> Any:
        t = self.torch.from_numpy(canvas).to(self.device)
        # detector_worker.to_input on the card: BGR -> RGB, CHW, float32 / 255
        x = t[..., [2, 1, 0]].permute(2, 0, 1)[None].float() / 255.0
        out = self.net(x)
        return out[0] if isinstance(out, (list, tuple)) else out

    def forward(self, canvas: np.ndarray) -> np.ndarray:
        with self.torch.inference_mode():
            y = self._run(canvas)
            self.torch.cuda.synchronize()
        return np.ascontiguousarray(y.float().cpu().numpy(), dtype="<f4")


class BadMessage(Exception):
    """The client broke the protocol: the connection closes."""


def recv_exact(conn: socket.socket, n: int) -> bytes:
    buf = bytearray(n)
    view, got = memoryview(buf), 0
    while got < n:
        k = conn.recv_into(view[got:], n - got)
        if k == 0:
            raise EOFError
        got += k
    return bytes(buf)


def recv_line(conn: socket.socket, limit: int = HELLO_MAX) -> bytes:
    out = bytearray()
    while not out.endswith(b"\n"):
        b = conn.recv(1)
        if not b:
            raise EOFError
        out += b
        if len(out) > limit:
            raise BadMessage("hello line too long")
    return bytes(out)


class Server:
    """Serve ``nets`` on ``path`` until ``stop`` is set. ``clock`` / ``sleep``: tests."""

    def __init__(self, path: Path, nets: Mapping[str, Net], imgsz: tuple[int, int] = IMGSZ,
                 max_hz: float = MAX_HZ, log: Callable[[str], None] = print,
                 clock: Callable[[], float] = time.monotonic,
                 sleep: Callable[[float], None] = time.sleep) -> None:  # fmt: skip
        self.path, self.nets, self.imgsz = path, dict(nets), imgsz
        self.min_gap = 1.0 / max_hz
        self.log, self.clock, self.sleep = log, clock, sleep
        self.stop = threading.Event()
        self.last_fwd = -1e18
        self.ms: list[float] = []
        self.n = {"conn": 0, "frames": 0, "closed": 0, "gone": 0, "bad": 0}
        self.t_stats = clock()

    def bind(self) -> socket.socket:
        with contextlib.suppress(FileNotFoundError):
            st = os.lstat(self.path)
            if not stat.S_ISSOCK(st.st_mode):  # never remove anything but a stale socket
                raise SystemExit(f"{self.path} exists and is not a socket")
            os.unlink(self.path)
        srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        srv.bind(str(self.path))
        os.chmod(self.path, 0o600)
        srv.listen(1)
        srv.settimeout(1.0)
        return srv

    def serve(self) -> None:
        srv = self.bind()
        self.log(json.dumps({"detect_server": "listening", "socket": str(self.path),
                             "models": {k: n.sha256[:12] for k, n in self.nets.items()},
                             "imgsz": list(self.imgsz)}))  # fmt: skip
        try:
            while not self.stop.is_set():
                self.stats()
                try:
                    conn, _ = srv.accept()
                except TimeoutError:
                    continue
                self.n["conn"] += 1
                with conn:
                    self.handle(conn)
        finally:
            srv.close()
            with contextlib.suppress(FileNotFoundError):
                os.unlink(self.path)
            self.stats(force=True)

    def handle(self, conn: socket.socket) -> None:
        try:
            conn.settimeout(MSG_S)
            net = self.hello(conn)
            if net is None:
                return
            h0, w0 = self.imgsz
            while not self.stop.is_set():
                first = self.wait_first(conn)
                if not first:
                    self.n["closed"] += 1  # the client closed, went silent, or we stop
                    return
                conn.settimeout(MSG_S)
                h, w, z = HEADER.unpack(first + recv_exact(conn, HEADER.size - 1))
                if (h, w, z) != (h0, w0, 0):
                    raise BadMessage(f"frame {h}x{w} ({z}): the canvas must be {h0}x{w0}")
                canvas = np.frombuffer(recv_exact(conn, h * w * 3), np.uint8).reshape(h, w, 3)
                wait = self.last_fwd + self.min_gap - self.clock()
                if wait > 0:
                    self.sleep(wait)
                t = time.perf_counter()
                y = net.forward(canvas)
                ms = (time.perf_counter() - t) * 1000.0
                self.last_fwd = self.clock()
                head = {"shape": list(y.shape), "ms": round(ms, 2)}
                conn.sendall(json.dumps(head).encode() + b"\n" + y.tobytes())
                self.ms.append(ms)
                self.n["frames"] += 1
                self.stats()
        except (EOFError, BrokenPipeError, ConnectionResetError, TimeoutError):
            self.n["gone"] += 1  # the client left, or gave up (it falls back to the CPU)
        except (BadMessage, struct.error, ValueError) as exc:
            self.n["bad"] += 1
            self.log(json.dumps({"detect_server": "bad message", "error": str(exc)[:200]}))

    def wait_first(self, conn: socket.socket) -> bytes:
        """The next message's first byte; b"" when the client closed, went silent for IDLE_S, or
        the server is stopping (checked every second, so a SIGTERM ends it promptly)."""
        end = self.clock() + IDLE_S
        conn.settimeout(1.0)
        while True:
            try:
                return conn.recv(1)
            except TimeoutError:
                if self.stop.is_set() or self.clock() >= end:
                    return b""

    def hello(self, conn: socket.socket) -> Net | None:
        try:
            doc = json.loads(recv_line(conn))
        except json.JSONDecodeError as exc:
            raise BadMessage(f"hello: {exc}") from None
        name = doc.get("model") if isinstance(doc, dict) else None
        if not isinstance(doc, dict) or doc.get("v") != PROTOCOL or name not in self.nets:
            err = {"ok": False, "error": f"hello {str(doc)[:80]}: v {PROTOCOL}, a served model "
                                         f"{sorted(self.nets)}"}  # fmt: skip
            conn.sendall(json.dumps(err).encode() + b"\n")
            self.n["bad"] += 1
            return None
        net = self.nets[name]
        ok = {"ok": True, "model": name, "sha256": net.sha256, "imgsz": list(self.imgsz),
              "shape": list(net.shape)}  # fmt: skip
        conn.sendall(json.dumps(ok).encode() + b"\n")
        return net

    def stats(self, force: bool = False) -> None:
        now = self.clock()
        if not force and now - self.t_stats < STATS_EVERY_S:
            return
        self.t_stats = now
        ms = sorted(self.ms)
        p = (lambda q: round(ms[min(len(ms) - 1, int(q * len(ms)))], 2)) if ms else None
        row = {"detect_server": "stats", "t": time.strftime("%FT%T%z"), **self.n,
               "ms_p50": p(0.5) if p else None, "ms_p95": p(0.95) if p else None,
               "ms_mean": round(statistics.fmean(ms), 2) if ms else None}  # fmt: skip
        self.log(json.dumps(row))
        self.ms.clear()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)  # fmt: skip
    ap.add_argument("--socket", type=Path, required=True)
    ap.add_argument("--model", action="append", required=True, help="NAME=PATH=SHA256")
    ap.add_argument("--imgsz", type=int, nargs=2, default=list(IMGSZ))
    ap.add_argument("--max-hz", type=float, default=MAX_HZ)
    a = ap.parse_args(argv)
    models = parse_models(a.model)
    imgsz = (int(a.imgsz[0]), int(a.imgsz[1]))

    from poring_vision.gpu import configure_gpu

    device = configure_gpu(float(os.environ.get("VISION_MAX_VRAM_FRACTION", "0.25")))
    if device is None:
        raise SystemExit("no GPU: nothing to serve (the host's CPU detector serves alone)")
    nets = {name: TorchNet(path, sha, device, imgsz) for name, (path, sha) in models.items()}
    srv = Server(a.socket, nets, imgsz, a.max_hz)
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda *_: srv.stop.set())
    srv.serve()
    return 0


if __name__ == "__main__":
    sys.exit(main())
