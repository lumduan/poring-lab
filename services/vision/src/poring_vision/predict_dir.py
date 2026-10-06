"""M10: a model's detections on a directory of frames (the gold set's model-vs-hand).

    python -m poring_vision.predict_dir --weights /data/train/<run>/weights/last.pt \
        --images /data/train/eval/gold/<session>/frames --out /data/train/eval/gold/<run>.json

Every ``*.png`` (a GAME_REGION frame named by its frame_id, as scripts/gold_eval.py extracts them)
is predicted at --imgsz with --conf; the JSON maps frame_id -> [{cls, x1, y1, x2, y2, conf}] in the
frame's own pixels. Scored on the host by scripts/gold_eval.py with label_iou's own scorer. The
GPU is capped at VISION_MAX_VRAM_FRACTION before anything else touches it (as train.py).
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--weights", type=Path, required=True)
    ap.add_argument("--images", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--imgsz", type=int, default=1280)
    ap.add_argument("--conf", type=float, default=0.25)
    a = ap.parse_args(argv)

    from poring_vision.gpu import configure_gpu

    device = configure_gpu(float(os.environ.get("VISION_MAX_VRAM_FRACTION", "0.25")))
    if device is None:
        raise SystemExit("no GPU: the cap is set first, and this needs the card")
    from ultralytics import YOLO

    model = YOLO(str(a.weights))
    names = model.names
    frames: dict[str, list[dict[str, object]]] = {}
    for path in sorted(a.images.glob("*.png")):
        result = model.predict(str(path), imgsz=a.imgsz, conf=a.conf, verbose=False)[0]
        boxes = result.boxes
        frames[path.stem] = [
            {"cls": names[int(c)], "x1": float(b[0]), "y1": float(b[1]), "x2": float(b[2]),
             "y2": float(b[3]), "conf": round(float(p), 4)}
            for b, c, p in zip(boxes.xyxy.tolist(), boxes.cls.tolist(), boxes.conf.tolist(),
                               strict=True)
        ]  # fmt: skip
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps({"weights": str(a.weights), "imgsz": a.imgsz, "conf": a.conf,
                                 "frames": frames}, indent=1))  # fmt: skip
    print(json.dumps({"weights": str(a.weights), "frames": len(frames), "out": str(a.out)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
