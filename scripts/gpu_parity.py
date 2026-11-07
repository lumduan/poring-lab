#!/usr/bin/env python3
"""Do the GPU's boxes match the CPU's? (docs/benchmarks/cpu-detector-speed.md section 5, "Parity")

    gpu_parity.py BENCH.json --model v1=ONNX --model xmas02=ONNX --out OUT.json

BENCH.json is ``poring_vision.bench_gpu``'s output (its runs keep each frame's boxes, keyed like
its --refs). The same frames are read in place from their tar shards (container paths /datasets/...
map to the host's NAS mount) and run through the CPU path, ``unit_detector.UnitDetector`` with the
model's own ONNX and per-class NMS (no collapse: ultralytics' predict NMS is per class too). Per
run (model x precision): the MONSTER boxes (every class but player / npc / warp) matched one to one
at IoU >= ``--iou`` (0.7), greedy by IoU; reported as matched / CPU boxes and matched / GPU boxes.
Offline; no client, no input.
"""

from __future__ import annotations

import argparse
import io
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

NOT_MONSTER = frozenset({"player", "npc", "warp"})
CONTAINER, HOST = "/datasets/", "/mnt/poring-lab-datasets/"


def iou(a: Sequence[float], b: Sequence[float]) -> float:
    """PURE: intersection over union of two (x0, y0, x1, y1) boxes."""
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union > 0 else 0.0


def match(cpu: Sequence[Sequence[float]], gpu: Sequence[Sequence[float]], thr: float) -> int:
    """PURE: one-to-one matches at IoU >= thr, greedy from the best pair."""
    pairs = sorted(((iou(c, g), i, j) for i, c in enumerate(cpu) for j, g in enumerate(gpu)),
                   reverse=True)  # fmt: skip
    used_c: set[int] = set()
    used_g: set[int] = set()
    n = 0
    for v, i, j in pairs:
        if v < thr:
            break
        if i in used_c or j in used_g:
            continue
        used_c.add(i)
        used_g.add(j)
        n += 1
    return n


def monsters(boxes: Sequence[Sequence[Any]]) -> list[list[float]]:
    """PURE: the (x0, y0, x1, y1) of rows [x0, y0, x1, y1, score, cls] whose cls is a monster."""
    return [[float(v) for v in b[:4]] for b in boxes if str(b[5]) not in NOT_MONSTER]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)  # fmt: skip
    ap.add_argument("bench", type=Path)
    ap.add_argument("--model", action="append", required=True, help="NAME=ONNX (bench's names)")
    ap.add_argument("--iou", type=float, default=0.7)
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args(argv)
    import numpy as np
    import unit_detector as ud
    from PIL import Image

    bench = json.loads(a.bench.read_text())
    refs = json.loads(Path(bench["refs"].replace(CONTAINER, HOST, 1)).read_text())
    models = dict(m.split("=", 1) for m in a.model)
    out: dict[str, Any] = {"bench": str(a.bench), "iou": a.iou, "frames": len(refs), "runs": {}}
    for name, onnx in models.items():
        cpu: dict[str, list[list[float]]] = {}
        with ud.UnitDetector(model=Path(onnx)) as det:
            for key, ref in refs.items():
                with open(ref["path"].replace(CONTAINER, HOST, 1), "rb") as fh:
                    fh.seek(int(ref["offset"]))
                    data = fh.read(int(ref["size"]))
                bgr = np.asarray(Image.open(io.BytesIO(data)).convert("RGB"))[..., ::-1]
                cpu[key] = monsters([[b.x0, b.y0, b.x1, b.y1, b.score, b.cls]
                                     for b in det.detect(bgr)])  # fmt: skip
        for tag, run in bench["runs"].items():
            if not tag.startswith(name + "-"):
                continue
            n_c = n_g = n_m = 0
            for key, c in cpu.items():
                g = monsters(run["boxes"].get(key, []))
                n_c, n_g, n_m = n_c + len(c), n_g + len(g), n_m + match(c, g, a.iou)
            out["runs"][tag] = {"cpu_boxes": n_c, "gpu_boxes": n_g, "matched": n_m,
                                "of_cpu": round(n_m / n_c, 4) if n_c else None,
                                "of_gpu": round(n_m / n_g, 4) if n_g else None}  # fmt: skip
    a.out.write_text(json.dumps(out, indent=1))
    print(json.dumps(out["runs"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
