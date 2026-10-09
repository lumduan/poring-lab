"""The host side of the CPU unit detector (scripts/detector_worker.py in its own environment).

    det = UnitDetector()            # fails closed: no environment / model -> DetectorUnavailable
    boxes = det.detect(frame_bgr)   # [Box(x0, y0, x1, y1, score, cls), ...] in the frame's pixels

The worker is spawned once and fed frames over a pipe. Pixels in only (rule 1).
"""

from __future__ import annotations

import json
import struct
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

ENV = Path("/dev/shm/poring-lab-detector")
PYTHON = ENV / ".venv/bin/python"
MODEL = ENV / "model/v0png-best-736x1280.onnx"  # v0-PNG (2026-10-06, 30 epochs), 1280 x 736 input
WORKER = Path(__file__).resolve().parent / "detector_worker.py"
NAMES = ("player", "monster", "npc")
CONF, IOU, THREADS = 0.25, 0.5, 8


class DetectorUnavailable(RuntimeError):
    """No detector here: a rule that needs it must not click."""


@dataclass(frozen=True)
class Box:
    x0: float
    y0: float
    x1: float
    y1: float
    score: float
    cls: str

    @property
    def foot(self) -> tuple[float, float]:
        """The unit's feet: the box's bottom centre."""
        return ((self.x0 + self.x1) / 2, self.y1)


class UnitDetector:
    def __init__(self, model: Path = MODEL, conf: float = CONF, iou: float = IOU,
                 threads: int = THREADS, python: Path = PYTHON) -> None:  # fmt: skip
        if not python.exists() or not model.exists():
            raise DetectorUnavailable(
                f"{python} / {model} missing (docs/operations/detector-cpu.md)"
            )
        self.model = model
        self.proc = subprocess.Popen(
            [str(python), str(WORKER), str(model), str(conf), str(iou), str(threads)],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        )  # fmt: skip
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
        boxes = [Box(*b[:5], NAMES[int(b[5])]) for b in reply["boxes"]]
        if self.log_path is not None:
            row = {"t_ns": time.monotonic_ns(), "ms": self.last_ms, "h": h, "w": w,
                   "boxes": [[round(b.x0, 1), round(b.y0, 1), round(b.x1, 1), round(b.y1, 1),
                              round(b.score, 3), b.cls] for b in boxes]}  # fmt: skip
            with self.log_path.open("a") as fh:
                fh.write(json.dumps(row) + "\n")
        return boxes

    def close(self) -> None:
        if self.proc.stdin is not None:
            self.proc.stdin.close()
        self.proc.wait(timeout=10)

    def __enter__(self) -> UnitDetector:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()
