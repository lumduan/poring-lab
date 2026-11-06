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
"""

from __future__ import annotations

import hashlib
import json
import struct
import subprocess
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

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


# xmas02-eval.md PASSED 2026-11-07 00:39 (Q1c 4/4, P4A still 0.946); deployed by Batt's decision
# 2026-11-07 ("use it"). The ONNX's NAS copy: scratch-archive/2026-11-07/detector-model/.
MAP_MODELS: dict[str, MapModel] = {
    "xmas_dun02": MapModel(
        "xmas02-last-736x1280.onnx",
        "293dca922e3e7890e3f26f40f140ef9b3d7eec4799392152ff3be8d132cace13",
        {s: "monster" for s in ("mystcase", "cruiser", "cookie", "cookie_xmas")},
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
