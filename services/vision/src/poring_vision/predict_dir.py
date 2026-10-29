"""M10: a model's detections on a directory of frames (the gold set's model-vs-hand), or on frames
read IN PLACE from tar shards (gef10-eval.md AMENDMENT R2-2).

    python -m poring_vision.predict_dir --weights /data/train/<run>/weights/last.pt \
        --images /data/train/eval/gold/<session>/frames --out /data/train/eval/gold/<run>.json
    python -m poring_vision.predict_dir --weights W --images DIR --glob '*.jpg' --out OUT
    python -m poring_vision.predict_dir --weights W --refs REFS.json --out OUT [--timing]

Every ``--glob`` file (default ``*.png``: a GAME_REGION frame named by its frame_id, as
scripts/gold_eval.py extracts them) is predicted at --imgsz with --conf; the JSON maps the file's
stem -> [{cls, x1, y1, x2, y2, conf}] in the frame's own pixels. ``--refs`` instead names each
frame by its key in a JSON object {key: {"path", "offset", "size"}}: the image's bytes inside a tar
shard (a container path, e.g. /datasets/...), read without extracting anything (rule 7).
``--timing`` adds each frame's wall time of the predict call (ms) and ultralytics' own split, and
the p50 / p95. Scored on the host by scripts/gold_eval.py / scripts/eval_q1.py with label_iou's
own scorer. The GPU is capped at VISION_MAX_VRAM_FRACTION before anything else touches it (as
train.py).
"""

from __future__ import annotations

import argparse
import json
import math
import os
import time
from collections.abc import Iterator, Sequence
from pathlib import Path
from typing import Any


def load_refs(path: Path) -> dict[str, dict[str, Any]]:
    """PURE (after the read): {key: {"path", "offset", "size"}}, every entry checked."""
    doc = json.loads(path.read_text())
    if not isinstance(doc, dict) or not doc:
        raise SystemExit(f"{path}: a non-empty JSON object {{key: {{path, offset, size}}}}")
    for key, ref in doc.items():
        if not {"path", "offset", "size"} <= set(ref) or int(ref["size"]) <= 0:
            raise SystemExit(f"{path}: {key}: needs path, offset and a positive size")
    return doc


def read_ref(ref: dict[str, Any]) -> bytes:
    """The ``size`` bytes at ``offset`` of ``path``; a short read is an error, never a frame."""
    with open(ref["path"], "rb") as fh:
        fh.seek(int(ref["offset"]))
        data = fh.read(int(ref["size"]))
    if len(data) != int(ref["size"]):
        raise SystemExit(f"{ref['path']}@{ref['offset']}: {len(data)} of {ref['size']} bytes")
    return data


def percentile(values: Sequence[float], q: float) -> float:
    """PURE: the nearest-rank percentile (q in 0..100) of a non-empty list."""
    s = sorted(values)
    k = max(1, math.ceil(q / 100 * len(s)))
    return float(s[k - 1])


def timing_summary(ms: Sequence[float]) -> dict[str, Any]:
    """PURE: n, p50, p95, mean and max of the per-frame wall times (ms)."""
    if not ms:
        return {"n": 0}
    return {"n": len(ms), "p50": round(percentile(ms, 50), 2), "p95": round(percentile(ms, 95), 2),
            "mean": round(sum(ms) / len(ms), 2), "max": round(max(ms), 2)}  # fmt: skip


def inputs(a: argparse.Namespace) -> Iterator[tuple[str, Any]]:
    """(key, image) in key order: a path for --images, a decoded BGR array for --refs."""
    if a.refs is not None:
        import cv2
        import numpy as np

        for key, ref in load_refs(a.refs).items():
            img = cv2.imdecode(np.frombuffer(read_ref(ref), np.uint8), cv2.IMREAD_COLOR)
            if img is None:
                raise SystemExit(f"{key}: the bytes at {ref['path']}@{ref['offset']} do not decode")
            yield key, img
    else:
        for path in sorted(a.images.glob(a.glob)):
            yield path.stem, str(path)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--weights", type=Path, required=True)
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--images", type=Path)
    src.add_argument("--refs", type=Path, help="{key: {path, offset, size}}: frames in tar shards")
    ap.add_argument("--glob", default="*.png", help="with --images (e.g. '*.jpg')")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--imgsz", type=int, default=1280)
    ap.add_argument("--conf", type=float, default=0.25)
    ap.add_argument("--timing", action="store_true", help="per-frame wall ms + p50 / p95")
    a = ap.parse_args(argv)

    from poring_vision.gpu import configure_gpu

    device = configure_gpu(float(os.environ.get("VISION_MAX_VRAM_FRACTION", "0.25")))
    if device is None:
        raise SystemExit("no GPU: the cap is set first, and this needs the card")
    from ultralytics import YOLO

    model = YOLO(str(a.weights))
    names = model.names
    frames: dict[str, list[dict[str, object]]] = {}
    ms: dict[str, float] = {}
    speed: dict[str, dict[str, float]] = {}
    for key, image in inputs(a):
        t0 = time.perf_counter()
        result = model.predict(image, imgsz=a.imgsz, conf=a.conf, verbose=False)[0]
        if a.timing:
            ms[key] = round((time.perf_counter() - t0) * 1000.0, 3)
            speed[key] = {k: round(float(v), 3) for k, v in (result.speed or {}).items()}
        boxes = result.boxes
        frames[key] = [
            {"cls": names[int(c)], "x1": float(b[0]), "y1": float(b[1]), "x2": float(b[2]),
             "y2": float(b[3]), "conf": round(float(p), 4)}
            for b, c, p in zip(boxes.xyxy.tolist(), boxes.cls.tolist(), boxes.conf.tolist(),
                               strict=True)
        ]  # fmt: skip
    out: dict[str, Any] = {"weights": str(a.weights), "imgsz": a.imgsz, "conf": a.conf,
                           "source": str(a.refs or a.images), "frames": frames}  # fmt: skip
    if a.timing:
        out["timing_ms"] = {"per_frame": ms, "speed": speed,
                            "summary": timing_summary(list(ms.values()))}  # fmt: skip
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(out, indent=1))
    done: dict[str, Any] = {"weights": str(a.weights), "frames": len(frames), "out": str(a.out)}
    if a.timing:
        done["timing"] = out["timing_ms"]["summary"]
    print(json.dumps(done))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
