#!/usr/bin/env python3
"""The CPU latency of docs/benchmarks/gef10-eval.md (AMENDMENT R2-2): each ONNX model through
``unit_detector.UnitDetector`` (the walk gate's CPU path: onnxruntime, ``ud.THREADS`` threads: 16
since 2026-11-07, 8 before; 736 x 1280) at nice 10, on the SAME frames, p50 / p95 of the worker's
inference ms.

    M=/dev/shm/poring-lab-detector/model
    python scripts/eval_latency.py REFS.json --model v1=$M/v1png-last-736x1280.onnx \
        --model gef10=$M/gef10-r2-last-736x1280.onnx --out JSON

REFS.json is predict_dir's --refs input ({key: {path, offset, size}}, e.g. ``eval_q1.py refs
--latency-200 35``): each frame is read IN PLACE from its tar shard; container paths
(/datasets/...) are read from the host's NAS mount. The models run INTERLEAVED, frame by frame
(model order rotating each frame), so a background load change hits them alike. A model's class
names come from UnitDetector's own rule (its ``<stem>.names.json`` sidecar, else v1's three).
The process lowers its own priority to nice 10 first. No GPU, no client, no input.
"""

from __future__ import annotations

import argparse
import io
import json
import math
import os
import sys
import time
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

NICE = 10
CONTAINER, HOST = "/datasets/", "/mnt/poring-lab-datasets/"


def host_path(path: str) -> str:
    """PURE: a container path (/datasets/...) -> the host's NAS mount; any other path as it is."""
    return HOST + path[len(CONTAINER) :] if path.startswith(CONTAINER) else path


def percentile(values: Sequence[float], q: float) -> float:
    """PURE: the nearest-rank percentile (predict_dir's rule)."""
    s = sorted(values)
    return float(s[max(1, math.ceil(q / 100 * len(s))) - 1])


def summary(ms: Sequence[float]) -> dict[str, Any]:
    if not ms:
        return {"n": 0}
    return {"n": len(ms), "p50": round(percentile(ms, 50), 2), "p95": round(percentile(ms, 95), 2),
            "mean": round(sum(ms) / len(ms), 2), "max": round(max(ms), 2)}  # fmt: skip


def rotation(names: Sequence[str], i: int) -> list[str]:
    """PURE: the model order for frame ``i`` (rotating, so no model always runs first)."""
    k = i % len(names)
    return [*names[k:], *names[:k]]


def read_frame(ref: dict[str, Any]) -> Any:
    """The frame's BGR pixels, read in place (offset, size) from its shard."""
    from PIL import Image

    with open(host_path(str(ref["path"])), "rb") as fh:
        fh.seek(int(ref["offset"]))
        data = fh.read(int(ref["size"]))
    if len(data) != int(ref["size"]):
        raise SystemExit(f"{ref['path']}@{ref['offset']}: a short read")
    rgb = np.asarray(Image.open(io.BytesIO(data)).convert("RGB"))
    return np.ascontiguousarray(rgb[:, :, ::-1])


def run(refs: dict[str, dict[str, Any]], models: dict[str, Path], factory: Any
        ) -> dict[str, Any]:  # fmt: skip
    """Every frame through every model (rotating order); the worker's ms per model."""
    dets = {name: factory(path) for name, path in models.items()}
    ms: dict[str, list[float]] = {name: [] for name in models}
    boxes: dict[str, int] = {name: 0 for name in models}
    try:
        for i, (_key, ref) in enumerate(refs.items()):
            img = read_frame(ref)
            for name in rotation(list(models), i):
                boxes[name] += len(dets[name].detect(img))
                ms[name].append(float(dets[name].last_ms))
    finally:
        for d in dets.values():
            d.close()
    return {name: {**summary(ms[name]), "boxes": boxes[name]} for name in models}


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("refs", type=Path)
    ap.add_argument("--model", action="append", required=True, help="NAME=ONNX (repeat)")
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args(argv)
    models: dict[str, Path] = {}
    for m in a.model:
        name, sep, path = m.partition("=")
        if not sep or not name or name in models:
            raise SystemExit(f"--model {m!r}: NAME=ONNX, each NAME once")
        models[name] = Path(path)
    refs = json.loads(a.refs.read_text())
    if not isinstance(refs, dict) or not refs:
        raise SystemExit(f"{a.refs}: predict_dir's --refs object")
    now = os.nice(0)
    if now < NICE:
        os.nice(NICE - now)
    import unit_detector as ud

    t0 = time.monotonic()
    per_model = run(refs, models, lambda p: ud.UnitDetector(model=p))
    out = {"what": "gef10-eval.md AMENDMENT R2-2: CPU latency through UnitDetector, same frames",
           "refs": str(a.refs), "frames": len(refs), "nice": os.nice(0),
           "threads": ud.THREADS, "models": {k: str(v) for k, v in models.items()},
           "ms": per_model, "seconds": round(time.monotonic() - t0, 1)}  # fmt: skip
    a.out.write_text(json.dumps(out, indent=1) + "\n")
    print(json.dumps(out, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
