#!/usr/bin/env python3
"""The floor-item model's ONNX prediction set (xmas02-detector.md O.9 / O13; round 2: O15): the
item model's ONNX through unit_detector.UnitDetector (the runner's CPU path: onnxruntime,
736 x 1280) on the refs' frames, written in predict_dir's format
({"frames": {key: [{cls, x1, y1, x2, y2, conf}]}}) so fi_eval.py scores it like the GPU set.

    fi_onnx_pred.py REFS.json MODEL.onnx OUT.json

Kept verbatim from O13's scratch copy (only this docstring and the path line are new)."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import eval_latency as el  # noqa: E402
import unit_detector as ud  # noqa: E402

refs = json.loads(Path(sys.argv[1]).read_text())
model = Path(sys.argv[2])
out = Path(sys.argv[3])
det = ud.UnitDetector(model=model, conf=0.25)
frames = {}
try:
    for i, (key, ref) in enumerate(refs.items()):
        img = el.read_frame(ref)
        boxes = det.detect(img)
        frames[key] = [
            {
                "cls": b.cls,
                "x1": float(b.x0),
                "y1": float(b.y0),
                "x2": float(b.x1),
                "y2": float(b.y1),
                "conf": round(float(b.score), 4),
            }
            for b in boxes
        ]
        if i % 500 == 0:
            print(i, len(refs), flush=True)
finally:
    det.close()
out.write_text(
    json.dumps(
        {
            "weights": str(model),
            "imgsz": [736, 1280],
            "conf": 0.25,
            "source": sys.argv[1],
            "frames": frames,
        },
        indent=1,
    )
)
print(json.dumps({"frames": len(frames), "out": str(out)}))
