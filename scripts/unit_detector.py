"""The host side of the CPU unit detector (scripts/detector_worker.py in its own environment).

    det = UnitDetector()            # fails closed: no environment / model -> DetectorUnavailable
    boxes = det.detect(frame_bgr)   # [Box(x0, y0, x1, y1, score, cls), ...] in the frame's pixels

The worker is spawned once and fed frames over a pipe. Pixels in only (rule 1).

The class NAMES map the worker's class ids by index. They are, in order: the ``names`` argument;
else a sidecar ``<model stem>.names.json`` next to the ONNX (a JSON list in id order, or an
object {"0": name, ...} as a cache manifest / ultralytics writes them); else v1's three
(player, monster, npc), so v1's behaviour is unchanged. A class id beyond the names raises
ClassNamesMismatch (a DetectorUnavailable: a rule that needs the detector must not click on a box
it cannot name). gef10-eval.md AMENDMENT R2-2: a 26-class model needs its own names.

A MAP-SCOPED model (Batt 2026-11-07: "use it" -- xmas02-eval.md PASSED) is chosen by map name:

    det = for_map("xmas_dun02")     # its pinned ONNX (sha256 checked), species -> "monster"
    det = for_map("prt_fild08")     # no entry: v1, as before

``collapse`` renames classes (a species -> ``monster``) and the worker suppresses every class of one
new name TOGETHER, before the boxes leave it: one box per sprite where per-class NMS gave a Cookie
and a Christmas Cookie on the same one. ``Box.species`` keeps the model's own class name.

THE GPU PATH (docs/planning/gpu-live-detector.md option A; ADR-0005 Amendment 2026-11-07, Batt:
"เลือก A", and the GPU may replace the CPU for the bot's detection):

    det = for_map_gpu("xmas_dun02")  # the GPU's forward pass, the CPU detector behind it
    boxes = det.detect(frame_bgr)    # the same Box list; det.last_path says "gpu" or "cpu"

The vision worker's detect server (``poring_vision.detect_server``, a guarded ``execdev:vision``
step) runs only the forward pass; the letterbox, decoding, NMS, names and collapse here are the
CPU worker's own functions (detector_worker), so the two paths differ only in the forward. Any
failure (no server, R3's pause window, a timeout, a bad reply) gives the CPU's boxes, never none.
"""

from __future__ import annotations

import hashlib
import json
import os
import socket
import stat
import struct
import subprocess
import sys
import time
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import detector_worker as dw  # noqa: E402 -- the CPU worker's own letterbox / decode / NMS

ENV = Path("/dev/shm/poring-lab-detector")
PYTHON = ENV / ".venv/bin/python"
# v1 (labels v1, 30 epochs): LIVE since 2026-10-13 (Batt decision 10), after the gold-set deployment
# parity in docs/benchmarks/v1-vs-v0png.md. Rollback: V0_MODEL. 1280 x 736 input, classes as v0.
MODEL = ENV / "model/v1png-last-736x1280.onnx"
V0_MODEL = ENV / "model/v0png-best-736x1280.onnx"  # v0-PNG (2026-10-06, 30 epochs)
WORKER = Path(__file__).resolve().parent / "detector_worker.py"
NAMES = ("player", "monster", "npc")  # v1's (and v0's) classes, by id
# THREADS: 8 -> 16 by Batt's decision 2026-11-07 (docs/benchmarks/cpu-detector-speed.md 1: p50
# 145 -> 110 ms on this host; onnxruntime's auto count is the slowest and is never used).
CONF, IOU, THREADS = 0.25, 0.5, 16


@dataclass(frozen=True)
class MapModel:
    """A map-scoped model: its ONNX in ENV/model, the file's sha256 (a different file fails
    closed), and its classes renamed for the runner (species -> "monster")."""

    onnx: str
    sha256: str
    collapse: Mapping[str, str]
    gpu: str | None = None  # its GPU_WEIGHTS name (the same training run), None: CPU only


# xmas02-eval.md PASSED 2026-11-07 00:39 (Q1c 4/4, P4A still 0.946); deployed by Batt's decision
# 2026-11-07 ("use it"). The ONNX's NAS copy: scratch-archive/2026-11-07/detector-model/.
MAP_MODELS: dict[str, MapModel] = {
    "xmas_dun02": MapModel(
        "xmas02-last-736x1280.onnx",
        "293dca922e3e7890e3f26f40f140ef9b3d7eec4799392152ff3be8d132cace13",
        {s: "monster" for s in ("mystcase", "cruiser", "cookie", "cookie_xmas")},
        gpu="xmas02",
    ),
}


class DetectorUnavailable(RuntimeError):
    """No detector here: a rule that needs it must not click."""


class ClassNamesMismatch(DetectorUnavailable):
    """The worker returned a class id the names do not cover: the names are not this model's."""


def sidecar(model: Path) -> Path:
    """The names file next to an ONNX: ``<model stem>.names.json``."""
    return model.with_suffix(".names.json")


def parse_names(doc: Sequence[Any] | Mapping[str, Any], where: str = "names") -> tuple[str, ...]:
    """PURE: a JSON list in id order, or {"0": name, ...} with the ids 0..n-1 (no gap) -> names."""
    if isinstance(doc, Mapping):
        try:
            by_id = {int(k): v for k, v in doc.items()}
        except ValueError:
            raise ValueError(f"{where}: the keys must be class ids") from None
        if sorted(by_id) != list(range(len(doc))):
            raise ValueError(f"{where}: the class ids must be 0..n-1 without a gap or a repeat")
        doc = [by_id[i] for i in range(len(by_id))]
    names = tuple(str(n) for n in doc)
    if not names or any(not n for n in names) or len(set(names)) != len(names):
        raise ValueError(f"{where}: needs one non-empty, distinct name per class id")
    return names


def names_for(model: Path, names: Sequence[str] | None = None) -> tuple[str, ...]:
    """The class names: the argument, else the model's sidecar, else v1's NAMES."""
    if names is not None:
        return parse_names(list(names))
    side = sidecar(model)
    if side.exists():
        return parse_names(json.loads(side.read_text()), str(side))
    return NAMES


@dataclass(frozen=True)
class Box:
    x0: float
    y0: float
    x1: float
    y1: float
    score: float
    cls: str
    species: str | None = None  # the model's own class name when ``collapse`` renamed it

    @property
    def foot(self) -> tuple[float, float]:
        """The unit's feet: the box's bottom centre."""
        return ((self.x0 + self.x1) / 2, self.y1)


def nms_groups(names: Sequence[str], collapse: Mapping[str, str]) -> list[int]:
    """PURE: one NMS group per class id; classes renamed to the same name share one group."""
    first: dict[str, int] = {}
    return [first.setdefault(collapse.get(n, n), i) for i, n in enumerate(names)]


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class UnitDetector:
    def __init__(self, model: Path = MODEL, conf: float = CONF, iou: float = IOU,
                 threads: int = THREADS, python: Path = PYTHON,
                 names: Sequence[str] | None = None,
                 collapse: Mapping[str, str] | None = None) -> None:  # fmt: skip
        if not python.exists() or not model.exists():
            raise DetectorUnavailable(
                f"{python} / {model} missing (docs/operations/detector-cpu.md)"
            )
        self.model = model
        self.names = names_for(model, names)
        self.collapse = dict(collapse or {})
        unknown = sorted(set(self.collapse) - set(self.names))
        if unknown:
            raise ClassNamesMismatch(f"{model.name}: collapse names {unknown} are not its classes")
        argv = [str(python), str(WORKER), str(model), str(conf), str(iou), str(threads)]
        if self.collapse:
            argv.append(json.dumps(nms_groups(self.names, self.collapse)))
        self.proc = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE)
        self.last_ms = 0.0
        # Batt 2026-10-09: every detection batch may be logged (class + score per box) so the walk
        # gate's refusals can be attributed to the boxes behind them, and hard negatives found.
        # The harness sets it per session (RAM); None = no log. detect() returns the same boxes.
        self.log_path: Path | None = None

    def detect(self, img: Any) -> list[Box]:
        a = np.ascontiguousarray(np.asarray(img)[..., :3], dtype=np.uint8)
        h, w = a.shape[:2]
        assert self.proc.stdin is not None and self.proc.stdout is not None
        self.proc.stdin.write(struct.pack("<HHI", h, w, 0) + a.tobytes())
        self.proc.stdin.flush()
        line = self.proc.stdout.readline()
        if not line:
            raise DetectorUnavailable("the detector worker died")
        reply = json.loads(line)
        self.last_ms = float(reply["ms"])
        boxes = [self.box_of(b) for b in reply["boxes"]]
        if self.log_path is not None:
            row = {"t_ns": time.monotonic_ns(), "ms": self.last_ms, "h": h, "w": w,
                   "boxes": [[round(b.x0, 1), round(b.y0, 1), round(b.x1, 1), round(b.y1, 1),
                              round(b.score, 3), b.cls] for b in boxes]}  # fmt: skip
            with self.log_path.open("a") as fh:
                fh.write(json.dumps(row) + "\n")
        return boxes

    def box_of(self, b: Sequence[Any]) -> Box:
        name = self.name_of(int(b[5]))
        if name in self.collapse:
            return Box(*b[:5], self.collapse[name], name)
        return Box(*b[:5], name)

    def name_of(self, cid: int) -> str:
        if not 0 <= cid < len(self.names):
            raise ClassNamesMismatch(
                f"{self.model.name}: class id {cid} is beyond its {len(self.names)} names "
                f"{list(self.names)}; give the model's names (names=..., or {sidecar(self.model)})"
            )
        return self.names[cid]

    def close(self) -> None:
        if self.proc.stdin is not None:
            self.proc.stdin.close()
        self.proc.wait(timeout=10)

    def __enter__(self) -> UnitDetector:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


def for_map(map_name: str | None, *, env: Path = ENV, **kw: Any) -> UnitDetector:
    """The detector for a map: its MAP_MODELS entry (the ONNX's sha256 must match, else
    DetectorUnavailable), else v1 (``MODEL``). ``kw`` goes to UnitDetector (threads, python...)."""
    spec = MAP_MODELS.get(map_name or "")
    if spec is None:
        return UnitDetector(**kw)
    onnx = env / "model" / spec.onnx
    if not onnx.exists():
        raise DetectorUnavailable(f"{onnx} missing (docs/operations/detector-cpu.md)")
    got = file_sha256(onnx)
    if got != spec.sha256:
        raise DetectorUnavailable(f"{onnx}: sha256 {got[:12]}... is not the deployed "
                                  f"{spec.sha256[:12]}... ({map_name})")  # fmt: skip
    return UnitDetector(model=onnx, collapse=spec.collapse, **kw)


# --- THE GPU PATH (gpu-live-detector.md option A; ADR-0005 Amendment 2026-11-07) ---------------
GPU_DIR = Path("/dev/shm/poring-lab-detect")  # the worker's /detect; guarded_build creates it 0700
GPU_SOCKET = GPU_DIR / "detect.sock"
SERVER_SOCKET = "/detect/detect.sock"  # the same socket, inside the worker
IMGSZ = (736, 1280)  # every deployed model's input (h, w), as the ONNX files' names say
STRIDES = (8, 16, 32)  # YOLO11's heads
PROTOCOL = 1
HEADER = struct.Struct("<HHI")
# The forward is 18-29 ms and 45 / 59 ms p50 / p95 at 10 Hz beside Frigate (cpu-detector-speed.md
# 8): a call slower than GPU_CALL_S gave up, and the GPU is retried GPU_RETRY_S later (R3's OFF
# windows are 60-180 s; a paused worker accepts and never answers).
GPU_CALL_S, GPU_HELLO_S, GPU_RETRY_S = 0.25, 0.25, 5.0
LINE_MAX = 512


@dataclass(frozen=True)
class GpuWeights:
    """What the GPU server may load for a model name, each by its pinned sha256:
    - the torch checkpoint (``path`` INSIDE the vision worker, the NAS, read-only): the training
      run the CPU ONNX was exported from (parity, FP32: cpu-detector-speed.md 8);
    - the deployed ONNX itself (``onnx`` in ENV/model, ``onnx_sha256``): what a vendor-neutral
      backend runs (OpenVINO, onnxruntime: ADR-0022), the very file the CPU worker runs."""

    path: str
    sha256: str
    onnx: str = ""
    onnx_sha256: str = ""


GPU_WEIGHTS: dict[str, GpuWeights] = {
    "v1": GpuWeights("/datasets/archive/train/v1png-20261008/weights/last.pt",
                     "03d539796183179d3085b23cdfe3ac4bd85754308931287bb25839ed268258ca",
                     "v1png-last-736x1280.onnx",
                     "32b448a1d197ded289f53ca9cb306f536ebfc0eb701ebdeaa94ab9e7800a3ba4"),
    "xmas02": GpuWeights("/datasets/archive/train/xmas02-20261106/weights/last.pt",
                         "5c5bb67a746b42014935700f449ecbf45525bbddf250fb21738eb6248a2b8b7b",
                         "xmas02-last-736x1280.onnx",
                         "293dca922e3e7890e3f26f40f140ef9b3d7eec4799392152ff3be8d132cace13"),
}  # fmt: skip


class GpuUnavailable(Exception):
    """This call gets no GPU boxes (the CPU serves it): no server, a timeout, a bad reply."""


class GpuClosed(GpuUnavailable):
    """The server closed the connection before a reply."""


class GpuRefused(GpuUnavailable):
    """Never the GPU again in this run: an unsafe socket, or a server not serving the pinned
    weights at the pinned shape."""


def anchors(imgsz: Sequence[int], strides: Sequence[int] = STRIDES) -> int:
    """PURE: the head's output columns for an input (h, w)."""
    return sum((int(imgsz[0]) // s) * (int(imgsz[1]) // s) for s in strides)


def connect_private(path: Path, timeout: float) -> socket.socket:
    """Connect to the detect socket WITHOUT following anything vision could have planted: the
    directory must be ours, mode 0700, not a symlink; the socket is opened O_PATH | O_NOFOLLOW,
    must be a socket owned by us, and is connected through /proc/self/fd (no second lookup).
    GpuRefused when unsafe; OSError when absent or refused."""
    uid = os.getuid()
    d = os.lstat(path.parent)
    if not stat.S_ISDIR(d.st_mode) or d.st_uid != uid or d.st_mode & 0o077:
        raise GpuRefused(f"{path.parent}: not our private directory "
                         f"(mode {oct(d.st_mode)}, uid {d.st_uid})")  # fmt: skip
    fd = os.open(path, os.O_PATH | os.O_NOFOLLOW)
    try:
        st = os.fstat(fd)
        if not stat.S_ISSOCK(st.st_mode) or st.st_uid != uid:
            raise GpuRefused(f"{path}: not a socket of ours (mode {oct(st.st_mode)}, "
                             f"uid {st.st_uid})")  # fmt: skip
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.settimeout(timeout)
        try:
            s.connect(f"/proc/self/fd/{fd}")
        except OSError:
            s.close()
            raise
        return s
    finally:
        os.close(fd)


class GpuDetector:
    """The GPU's forward pass with the CPU detector behind it: the same ``detect`` -> [Box] as
    UnitDetector. ``detect(img, prefer="cpu")`` forces the CPU for that call (a pilot's CPU arm).
    ``last_path`` says which path gave the last boxes, ``last_ms`` its time (GPU: the call from
    the canvas to the decoded boxes, on the host's clock), ``last_reason`` why the GPU did not.
    ``weights`` None: the model has no GPU checkpoint, so the CPU serves alone."""

    def __init__(self, cpu: UnitDetector, weights: str | None = "v1", *,
                 socket_path: Path = GPU_SOCKET, conf: float = CONF, iou: float = IOU,
                 call_s: float = GPU_CALL_S, hello_s: float = GPU_HELLO_S,
                 retry_s: float = GPU_RETRY_S,
                 clock: Callable[[], float] = time.monotonic) -> None:  # fmt: skip
        if weights is not None and weights not in GPU_WEIGHTS:
            raise DetectorUnavailable(f"GPU weights {weights!r}: not in GPU_WEIGHTS")
        self.cpu = cpu
        self.model, self.names, self.collapse = cpu.model, cpu.names, cpu.collapse
        self.weights = weights
        self.spec = GPU_WEIGHTS[weights] if weights is not None else None
        self.groups = nms_groups(self.names, self.collapse) if self.collapse else None
        self.shape = (1, 4 + len(self.names), anchors(IMGSZ))
        self.socket_path, self.conf, self.iou = socket_path, conf, iou
        self.call_s, self.hello_s, self.retry_s, self.clock = call_s, hello_s, retry_s, clock
        self.sock: socket.socket | None = None
        self.buf = bytearray()
        self.down_until = -1e18
        self.disabled: str | None = None if weights is not None else "no GPU weights"
        self.last_path = ""
        self.last_ms = 0.0
        self.last_reason: str | None = None
        self.counts: Counter[str] = Counter()  # gpu / cpu (asked) / fallback
        self.reasons: Counter[str] = Counter()  # why the GPU did not serve
        self.log_path: Path | None = None
        cpu.log_path = None  # this class logs each batch itself, with its path

    def detect(self, img: Any, prefer: str = "gpu") -> list[Box]:
        a = np.ascontiguousarray(np.asarray(img)[..., :3], dtype=np.uint8)
        rows = self._gpu(a) if prefer == "gpu" else None
        if rows is None:
            boxes = self.cpu.detect(a)
            self.last_path, self.last_ms = "cpu", self.cpu.last_ms
            self.counts["cpu" if prefer == "cpu" else "fallback"] += 1
        else:
            boxes = [self.cpu.box_of(b) for b in rows]
            self.last_path = "gpu"
            self.counts["gpu"] += 1
        if self.log_path is not None:
            row = {"t_ns": time.monotonic_ns(), "t_wall": round(time.time(), 3),
                   "ms": self.last_ms, "path": self.last_path, "prefer": prefer,
                   "reason": self.last_reason, "h": a.shape[0], "w": a.shape[1],
                   "boxes": [[round(b.x0, 1), round(b.y0, 1), round(b.x1, 1), round(b.y1, 1),
                              round(b.score, 3), b.cls] for b in boxes]}  # fmt: skip
            with self.log_path.open("a") as fh:
                fh.write(json.dumps(row) + "\n")
        return boxes

    def _gpu(self, a: np.ndarray) -> list[list[float]] | None:
        self.last_reason = None
        if self.disabled is not None:
            self.last_reason = "disabled"
            return None
        if self.sock is None and self.clock() < self.down_until:
            self.last_reason = "down"
            return None
        t = time.perf_counter()
        canvas, s, left, top = dw.pad_canvas(a, IMGSZ)
        try:
            out = self._call(canvas)
        except GpuRefused as exc:
            self._drop()
            self.disabled = str(exc)[:300]
            self.reasons["refused"] += 1
            self.last_reason = f"refused: {self.disabled}"
            return None
        except (OSError, GpuUnavailable, ValueError) as exc:
            self._drop()
            self.down_until = self.clock() + self.retry_s
            self.reasons[type(exc).__name__] += 1
            self.last_reason = f"{type(exc).__name__}: {exc}"[:300]
            return None
        rows = dw.decode(out, s, left, top, self.conf, self.iou, self.groups)
        self.last_ms = round((time.perf_counter() - t) * 1000.0, 1)
        return rows

    def _call(self, canvas: np.ndarray) -> np.ndarray:
        fresh = self.sock is None
        if fresh:
            self._connect()
        try:
            return self._exchange(canvas)
        except (BrokenPipeError, ConnectionResetError, GpuClosed):
            if fresh:
                raise
            self._drop()  # an idle connection the server had closed: once more, on a new one
            self._connect()
            return self._exchange(canvas)

    def _connect(self) -> None:
        assert self.spec is not None and self.weights is not None
        deadline = time.monotonic() + self.hello_s
        self.sock, self.buf = connect_private(self.socket_path, self.hello_s), bytearray()
        try:
            self._send(json.dumps({"v": PROTOCOL, "model": self.weights}).encode() + b"\n",
                       deadline)  # fmt: skip
            doc = json.loads(self._line(deadline))
        except BaseException:
            self._drop()
            raise
        want = {"ok": True, "model": self.weights, "imgsz": list(IMGSZ),
                "shape": list(self.shape)}  # fmt: skip
        # the pinned torch checkpoint, or the pinned deployed ONNX (a vendor-neutral backend)
        shas = {self.spec.sha256, self.spec.onnx_sha256} - {""}
        got = {k: v for k, v in doc.items() if k != "sha256"} if isinstance(doc, dict) else doc
        if got != want or not isinstance(doc, dict) or doc.get("sha256") not in shas:
            self._drop()
            raise GpuRefused(f"hello {str(doc)[:200]} is not {want} with a sha256 in {shas}")

    def _exchange(self, canvas: np.ndarray) -> np.ndarray:
        deadline = time.monotonic() + self.call_s
        h, w = canvas.shape[:2]
        self._send(HEADER.pack(h, w, 0), deadline)
        self._send(memoryview(np.ascontiguousarray(canvas)).cast("B"), deadline)
        head = json.loads(self._line(deadline))
        if not isinstance(head, dict) or head.get("shape") != list(self.shape):
            raise GpuUnavailable(f"reply {str(head)[:120]}: the shape must be {list(self.shape)}")
        n = int(np.prod(self.shape)) * 4
        out = np.frombuffer(self._exact(n, deadline), "<f4").reshape(self.shape)
        if not np.isfinite(out).all():
            raise GpuUnavailable("a non-finite value in the reply")
        return out

    def _left(self, deadline: float) -> float:
        left = deadline - time.monotonic()
        if left <= 0:
            raise TimeoutError("GPU call timed out")
        return left

    def _send(self, data: Any, deadline: float) -> None:
        assert self.sock is not None
        self.sock.settimeout(self._left(deadline))
        self.sock.sendall(data)

    def _fill(self, deadline: float) -> None:
        assert self.sock is not None
        self.sock.settimeout(self._left(deadline))
        chunk = self.sock.recv(1 << 20)
        if not chunk:
            raise GpuClosed("the server closed the connection")
        self.buf += chunk

    def _line(self, deadline: float) -> bytes:
        while (i := self.buf.find(b"\n", 0, LINE_MAX)) < 0:
            if len(self.buf) >= LINE_MAX:
                raise GpuUnavailable("a reply line too long")
            self._fill(deadline)
        line = bytes(self.buf[:i])
        del self.buf[: i + 1]
        return line

    def _exact(self, n: int, deadline: float) -> bytes:
        while len(self.buf) < n:
            self._fill(deadline)
        data = bytes(self.buf[:n])
        del self.buf[:n]
        return data

    def _drop(self) -> None:
        if self.sock is not None:
            self.sock.close()
        self.sock, self.buf = None, bytearray()

    def info(self) -> dict[str, Any]:
        """For the run's events: the weights, what served, and why the GPU did not."""
        return {"weights": self.weights, "sha256": None if self.spec is None else self.spec.sha256,
                "counts": dict(self.counts), "reasons": dict(self.reasons),
                "disabled": self.disabled}  # fmt: skip

    def close(self) -> None:
        self._drop()
        self.cpu.close()

    def __enter__(self) -> GpuDetector:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


def for_map_gpu(map_name: str | None, *, env: Path = ENV, socket_path: Path = GPU_SOCKET,
                gpu_kw: Mapping[str, Any] | None = None, **kw: Any) -> GpuDetector:  # fmt: skip
    """``for_map``'s CPU detector behind the GPU's forward pass of the SAME model: the map's
    GPU_WEIGHTS name, or v1 for a map without an entry. ``kw`` goes to the CPU detector (never a
    ``model``: the GPU weights must be the deployed model's); ``gpu_kw`` to GpuDetector."""
    if "model" in kw:
        raise DetectorUnavailable("for_map_gpu: the model is the map's, never an argument")
    spec = MAP_MODELS.get(map_name or "")
    cpu = for_map(map_name, env=env, **kw)
    weights = "v1" if spec is None else spec.gpu
    return GpuDetector(cpu, weights, socket_path=socket_path, **dict(gpu_kw or {}))


def serve_step(seconds: int, models: Sequence[str] = tuple(GPU_WEIGHTS)) -> str:
    """PURE: the guarded step that runs the detect server for ``seconds`` (the pinned weights)."""
    parts = ["python", "-m", "poring_vision.detect_server", "--socket", SERVER_SOCKET]
    for m in models:
        w = GPU_WEIGHTS[m]
        parts += ["--model", f"{m}={w.path}={w.sha256}"]
    return f"execdev:vision@{int(seconds)}=" + " ".join(parts)


def serve_openvino(device: str = "GPU", env: Path = ENV, socket_path: Path = GPU_SOCKET,
                   models: Sequence[str] = tuple(GPU_WEIGHTS)) -> list[str]:  # fmt: skip
    """PURE: the detect server on OpenVINO (ADR-0022; bot-server's Intel Arc), as an argv for a
    host process: the DEPLOYED ONNX files in ``env``/model, each by its pinned sha256."""
    argv = ["python", "-m", "poring_vision.detect_server", "--backend", "openvino",
            "--device", device, "--socket", str(socket_path)]  # fmt: skip
    for m in models:
        w = GPU_WEIGHTS[m]
        argv += ["--model", f"{m}={env / 'model' / w.onnx}={w.onnx_sha256}"]
    return argv


def main(argv: list[str] | None = None) -> int:
    import argparse

    ap = argparse.ArgumentParser(description="the detect server's guarded step (GPU path)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sc = sub.add_parser("serve-cmd", help="print the guarded_build command for the detect server")
    sc.add_argument("--seconds", type=int, default=0)
    sc.add_argument("--backend", choices=["torch", "openvino"], default="torch",
                    help="torch: the guarded execdev step (ubuntu-docker's NVIDIA); openvino: a "
                    "host process (ADR-0022)")  # fmt: skip
    sc.add_argument("--device", default="GPU", help="openvino's device")
    a = ap.parse_args(argv)
    if a.cmd == "serve-cmd" and a.backend == "openvino":
        print(" ".join(serve_openvino(a.device)))
    elif a.cmd == "serve-cmd":
        if a.seconds <= 0:
            ap.error("--seconds is needed for the guarded step")
        print(f"python3 scripts/guarded_build.py --threshold 30 --sustain 30 "
              f"'{serve_step(a.seconds)}'")  # fmt: skip
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
