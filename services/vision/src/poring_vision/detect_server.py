"""The live detector's GPU forward pass (docs/planning/gpu-live-detector.md option A; ADR-0005
Amendment 2026-11-07: Batt "เลือก A" and "อนุมัติให้ใช้ gpu แทน cpu ในการ detect ของ bot ได้เลย").

    python -m poring_vision.detect_server --socket /detect/detect.sock \\
        --model v1=/datasets/archive/train/v1png-20261008/weights/last.pt=<sha256> \\
        --model xmas02=/datasets/archive/train/xmas02-20261106/weights/last.pt=<sha256> \\
        [--imgsz 736 1280] [--max-hz 10]
    python -m poring_vision.detect_server --backend openvino --device GPU --socket SOCK \\
        --model v1=<dir>/v1png-last-736x1280.onnx=<sha256> ...    # any vendor (ADR-0022)
        [--ov-preproc cpu|gpu] [--ov-precision f32|f16]

``--ov-preproc`` (OpenVINO only; Batt 2026-11-08 "we use the GPU for detection"): where the canvas
becomes the model's input (BGR -> RGB, HWC -> CHW, float32 / 255). ``cpu`` (the default until its
parity run passes): ``to_input`` in numpy, then the 11.3 MB float32 tensor goes to the device.
``gpu``: the same formula as OpenVINO pre-processing steps compiled INTO the model (PPP_STEPS), so
the 2.8 MB uint8 canvas goes to the device and is converted there (bot-server-migration.md 16: the
CPU conversion is 17.3 ms a frame on bot-server's Xeon). The wire is the same either way; the mode
is in the start line and every stats line. TorchNet always converts on the card.

It runs only as a guarded ``execdev:vision`` step inside the long-lived worker (R1-R3: the VRAM
cap, the paired pause windows, the IO guard). ``scripts/unit_detector.py serve-cmd`` prints the
step with the pinned weights.

FRAMES IN, NUMBERS OUT through ONE unix socket in the host RAM directory only the worker mounts
(``/detect``). The host (``scripts/unit_detector.GpuDetector``) is the only client and does the
letterbox, the decoding, the NMS and the class names with the same code as its CPU worker; this
process runs only the model's forward pass (FP32; OpenVINO may run --ov-precision f16) and returns
the head's raw output. No input, no
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
OV_PREPROC = ("cpu", "gpu")
OV_PREPROC_DEFAULT = "gpu"  # since its parity run, 2026-11-08 (bot-server-migration.md 16a)
OV_PRECISIONS = ("f32", "f16")
# --ov-precision: OpenVINO's INFERENCE_PRECISION_HINT. f32 is the 11-07 parity's (boxes 0.0 px from
# the CPU's). f16 is OpenVINO's own GPU default and the Arc's XMX units' type: 15.6 -> 9.9 ms a
# forward back to back on bot-server (bot-server-migration.md 19); it goes live only after its own
# box parity run.
OV_PRECISION = "f32"
# The card's clock floor, for the start and stats lines: at the bot's pace (a call every 0.1-0.5 s)
# the Arc's firmware clocks down between calls, 2450 -> ~800 MHz, and a forward takes 29 instead of
# 16 ms (bot-server-migration.md 19). The host keeps the floor at RP0
# (scripts/host/poring-lab-gpu-clock.service).
GPU_CLOCK_GLOB = "/sys/class/drm/card*/gt_{}_freq_mhz"

# --ov-preproc gpu: to_input's formula as OpenVINO pre-processing, compiled INTO the model so it
# runs on the device. The tensor is the canvas as it arrives (PPP_TENSOR: u8, NHWC, BGR). OpenVINO
# runs PPP_STEPS in this order on that NHWC tensor, THEN its implicit layout conversion to the
# model's NCHW (openvino 2026.4.1, preprocess_impls.cpp InputInfoImpl::build: the user's steps
# first, then create_implicit_steps; scale needs a real type, so the conversion comes first).
# Against to_input (flip the u8 channels, transpose, float32, / 255): the flip and the transpose
# only move elements and u8 -> f32 is exact, so they commute with each other and with the one
# arithmetic step, the same f32 division by 255. The device's compiler may turn that division into
# a multiply by 1/255 or fold it into the first convolution: float rounding, nothing more.
PPP_TENSOR = ("u8", "NHWC", "BGR")  # element type, layout, colour format
PPP_MODEL_LAYOUT = "NCHW"
PPP_STEPS: tuple[tuple[str, str | float], ...] = (
    ("convert_element_type", "f32"),  # u8 -> f32 (op Convert): exact
    ("convert_color", "RGB"),  # BGR -> RGB: a Gather of the C axis, reversed (exact)
    ("scale", 255.0),  # op Divide by 255.0, in f32: to_input's `/ 255.0`
)


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


def to_input(canvas: np.ndarray) -> np.ndarray:
    """The canvas -> (1, 3, H, W) float32 RGB in 0..1: scripts/detector_worker.to_input's formula
    (the host's CPU path), so an ONNX here sees exactly what the CPU worker feeds it."""
    x = canvas[..., ::-1].transpose(2, 0, 1)[None].astype(np.float32) / 255.0
    return np.ascontiguousarray(x)


def gpu_clock(pattern: str = GPU_CLOCK_GLOB) -> dict[str, int] | None:
    """The first card's clock settings (MHz) as sysfs shows them -- min (the floor), RP0 (its
    highest), act (now) -- or None where no card's files are visible."""
    import glob

    for d in sorted(glob.glob(pattern.format("min"))):
        out: dict[str, int] = {}
        for key in ("min", "RP0", "act"):
            try:
                out[key] = int(Path(d.replace("_min_", f"_{key}_")).read_text().strip())
            except (OSError, ValueError):
                break
        else:
            return out
    return None


def with_device_preproc(ov: Any, model: Any) -> Any:
    """``model`` (one input, NCHW float32 RGB in 0..1) -> the same model taking the canvas as it
    arrives (PPP_TENSOR), with PPP_STEPS compiled in: --ov-preproc gpu."""
    from openvino.preprocess import ColorFormat, PrePostProcessor

    ppp = PrePostProcessor(model)
    inp = ppp.input()
    elem, layout, colour = PPP_TENSOR
    tensor = inp.tensor()
    tensor.set_element_type(getattr(ov.Type, elem))
    tensor.set_layout(ov.Layout(layout))
    tensor.set_color_format(getattr(ColorFormat, colour))
    inp.model().set_layout(ov.Layout(PPP_MODEL_LAYOUT))
    pre = inp.preprocess()
    for op, arg in PPP_STEPS:
        if op == "convert_element_type":
            pre.convert_element_type(getattr(ov.Type, str(arg)))
        elif op == "convert_color":
            pre.convert_color(getattr(ColorFormat, str(arg)))
        elif op == "scale":
            pre.scale(float(arg))
        else:  # pragma: no cover -- PPP_STEPS is a constant
            raise ValueError(f"pre-processing step {op!r}")
    return ppp.build()


class OvNet:
    """The DEPLOYED ONNX itself on OpenVINO (ADR-0022: Intel's GPU or any OpenVINO device), FP32 by
    default: the same file as the host's CPU detector, so only the forward differs. ``preproc``:
    where the canvas becomes the input (module docstring, --ov-preproc)."""

    def __init__(self, path: str, sha256: str, device: str = "GPU",
                 imgsz: tuple[int, int] = IMGSZ, precision: str = OV_PRECISION,
                 preproc: str = OV_PREPROC_DEFAULT) -> None:  # fmt: skip
        if preproc not in OV_PREPROC:
            raise SystemExit(f"--ov-preproc {preproc!r}: one of {list(OV_PREPROC)}")
        if precision not in OV_PRECISIONS:
            raise SystemExit(f"--ov-precision {precision!r}: one of {list(OV_PRECISIONS)}")
        got = file_sha256(path)
        if got != sha256:
            raise SystemExit(f"{path}: sha256 {got[:12]}... is not the pinned {sha256[:12]}...")
        import openvino as ov

        self.sha256, self.preproc, self.precision = sha256, preproc, precision
        core = ov.Core()
        cfg = {"PERFORMANCE_HINT": "LATENCY", "INFERENCE_PRECISION_HINT": precision}
        model = core.read_model(path)
        if preproc == "gpu":
            model = with_device_preproc(ov, model)
        self.compiled = core.compile_model(model, device, cfg)
        self.req = self.compiled.create_infer_request()
        y = self.forward(np.full((*imgsz, 3), 114, np.uint8))
        self.shape = (int(y.shape[0]), int(y.shape[1]), int(y.shape[2]))

    def forward(self, canvas: np.ndarray) -> np.ndarray:
        # gpu: the uint8 BGR canvas itself, (1, H, W, 3); the device converts it (PPP_STEPS)
        x = canvas[None] if self.preproc == "gpu" else to_input(canvas)
        self.req.infer({0: x})
        out = self.req.get_output_tensor(0).data
        return np.ascontiguousarray(out, dtype="<f4")


class TorchNet:
    """One YOLO checkpoint's fused model on the host's torch accelerator (any vendor, ADR-0022),
    FP32 (bench_gpu's forward)."""

    def __init__(self, path: str, sha256: str, device: str,
                 imgsz: tuple[int, int] = IMGSZ) -> None:  # fmt: skip
        got = file_sha256(path)
        if got != sha256:  # never unpickle a file that is not the pinned one
            raise SystemExit(f"{path}: sha256 {got[:12]}... is not the pinned {sha256[:12]}...")
        import torch
        from ultralytics import YOLO

        from poring_vision import accel

        self.torch, self.device, self.sha256 = torch, device, sha256
        self.acc = accel.current()
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
            self.acc.synchronize()
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
                 sleep: Callable[[float], None] = time.sleep,
                 mode: Mapping[str, Any] | None = None) -> None:  # fmt: skip
        """``mode``: how the nets run (backend, device, ov_preproc, precision), for the start line;
        ``ov_preproc`` is in every stats line too."""
        self.path, self.nets, self.imgsz = path, dict(nets), imgsz
        self.mode = dict(mode or {})
        self.min_gap = 1.0 / max_hz
        self.log, self.clock, self.sleep = log, clock, sleep
        self.stop = threading.Event()
        self.last_fwd = -1e18
        self.ms: list[float] = []
        self.n = {"conn": 0, "frames": 0, "closed": 0, "gone": 0, "bad": 0}
        self.t_stats = clock()
        self.clock_now: Callable[[], dict[str, int] | None] = gpu_clock

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
        self.log(json.dumps({"detect_server": "listening", "t": time.strftime("%FT%T%z"),
                             "socket": str(self.path),
                             "models": {k: n.sha256[:12] for k, n in self.nets.items()},
                             "imgsz": list(self.imgsz), **self.mode,
                             "gpu_clock": self.clock_now()}))  # fmt: skip
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
        row = {"detect_server": "stats", "t": time.strftime("%FT%T%z"),
               "ov_preproc": self.mode.get("ov_preproc"),
               "precision": self.mode.get("precision"), "gpu_clock": self.clock_now(), **self.n,
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
    ap.add_argument("--backend", choices=["torch", "openvino"], default="torch",
                    help="torch: the .pt on the torch accelerator; openvino: the ONNX")  # fmt: skip
    ap.add_argument("--device", default="GPU", help="--backend openvino's device (GPU, CPU, ...)")
    ap.add_argument("--ov-preproc", choices=list(OV_PREPROC), default=None,
                    help="--backend openvino: where the canvas becomes the model's input, "
                    f"cpu (numpy) or gpu (in the model); default {OV_PREPROC_DEFAULT}")  # fmt: skip
    ap.add_argument("--ov-precision", choices=list(OV_PRECISIONS), default=None,
                    help="--backend openvino: the inference precision hint; default "
                    f"{OV_PRECISION}")  # fmt: skip
    a = ap.parse_args(argv)
    if a.backend != "openvino" and a.ov_preproc is not None:
        ap.error("--ov-preproc is --backend openvino's (torch converts on the card already)")
    if a.backend != "openvino" and a.ov_precision is not None:
        ap.error("--ov-precision is --backend openvino's (torch runs FP32)")
    models = parse_models(a.model)
    imgsz = (int(a.imgsz[0]), int(a.imgsz[1]))
    nets: dict[str, Net]
    if a.backend == "openvino":
        preproc = a.ov_preproc or OV_PREPROC_DEFAULT
        precision = a.ov_precision or OV_PRECISION
        mode = {"backend": "openvino", "device": a.device, "ov_preproc": preproc,
                "precision": precision}  # fmt: skip
        nets = {name: OvNet(path, sha, a.device, imgsz, precision, preproc)
                for name, (path, sha) in models.items()}  # fmt: skip
    else:
        from poring_vision.gpu import configure_gpu

        device = configure_gpu(float(os.environ.get("VISION_MAX_VRAM_FRACTION", "0.25")))
        if device is None:
            raise SystemExit("no GPU: nothing to serve (the host's CPU detector serves alone)")
        mode = {"backend": "torch", "device": str(device), "ov_preproc": None, "precision": "f32"}
        nets = {name: TorchNet(path, sha, device, imgsz) for name, (path, sha) in models.items()}
    srv = Server(a.socket, nets, imgsz, a.max_hz, mode=mode)
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda *_: srv.stop.set())
    srv.serve()
    return 0


if __name__ == "__main__":
    sys.exit(main())
