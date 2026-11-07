#!/usr/bin/env python3
"""The unit detector for walk@11's click gate, on CPU (Batt 2026-10-08: "CPU is fine, R2").

Runs in a SEPARATE environment with onnxruntime (default /dev/shm/poring-lab-detector/.venv: RAM
only, the host .venv and uv.lock untouched; rebuilt after a host reboot, see
docs/operations/detector-cpu.md). The model is an ONNX export of a trained YOLO checkpoint; the
letterbox, decoding and NMS here are our own, so no ultralytics code runs at decision time.

Protocol (stdin/stdout, binary): per request an 8-byte header `<HH` height, width + `<I` 0, then
height*width*3 BGR bytes; the reply is one JSON line:
{"boxes": [[x0, y0, x1, y1, score, cls], ...], "ms": inference ms}. Pixels in only.

argv: model conf iou [threads [groups]]. ``groups`` (optional, 2026-11-07) is a JSON list, one NMS
group per class id: classes in one group are suppressed TOGETHER, so a map-scoped model's species
(xmas02: cookie + cookie_xmas on one sprite, xmas02-eval.md RESULTS) give one box, not two. The
box keeps its own class id. Without it every class is its own group, as before.
"""

from __future__ import annotations

import json
import struct
import sys
import time
from typing import Any

import numpy as np

NAMES = ("player", "monster", "npc")  # the v0 label set (poring_dataset.labels.CLASSES)


def pad_canvas(img: np.ndarray, size: tuple[int, int]) -> tuple[np.ndarray, float, int, int]:
    """BGR (h, w, 3) -> the model's (H, W, 3) uint8 BGR canvas, grey 114 padding; the scale and
    the (left, top) padding, to map boxes back. `size` = the model's (H, W). The GPU path
    (unit_detector.GpuDetector, 2026-11-07) sends this canvas; the forward's input is
    ``to_input(canvas)``, on either side."""
    h, w = img.shape[:2]
    s = min(size[0] / h, size[1] / w)
    nh, nw = round(h * s), round(w * s)
    if (nh, nw) != (h, w):
        ys = (np.arange(nh) / s).astype(int).clip(0, h - 1)
        xs = (np.arange(nw) / s).astype(int).clip(0, w - 1)
        img = img[ys][:, xs]
    top, left = (size[0] - nh) // 2, (size[1] - nw) // 2
    canvas = np.full((size[0], size[1], 3), 114, np.uint8)
    canvas[top : top + nh, left : left + nw] = img
    return canvas, s, left, top


def to_input(canvas: np.ndarray) -> np.ndarray:
    """The canvas -> (1, 3, H, W) float32 RGB in 0..1 (the GPU server does the same on the card)."""
    x = canvas[..., ::-1].transpose(2, 0, 1)[None].astype(np.float32) / 255.0
    return np.ascontiguousarray(x)


def letterbox(img: np.ndarray, size: tuple[int, int]) -> tuple[np.ndarray, float, int, int]:
    """BGR (h, w, 3) -> (1, 3, H, W) float32 RGB in 0..1, grey 114 padding; the scale and the
    (left, top) padding, to map boxes back. `size` = the model's (H, W)."""
    canvas, s, left, top = pad_canvas(img, size)
    return to_input(canvas), s, left, top


def nms(boxes: np.ndarray, scores: np.ndarray, iou: float) -> list[int]:
    order = np.argsort(-scores)
    keep: list[int] = []
    while len(order):
        i = int(order[0])
        keep.append(i)
        if len(order) == 1:
            break
        rest = order[1:]
        xx0 = np.maximum(boxes[i, 0], boxes[rest, 0])
        yy0 = np.maximum(boxes[i, 1], boxes[rest, 1])
        xx1 = np.minimum(boxes[i, 2], boxes[rest, 2])
        yy1 = np.minimum(boxes[i, 3], boxes[rest, 3])
        inter = np.clip(xx1 - xx0, 0, None) * np.clip(yy1 - yy0, 0, None)
        area = lambda b: (b[..., 2] - b[..., 0]) * (b[..., 3] - b[..., 1])  # noqa: E731
        ov = inter / (area(boxes[i]) + area(boxes[rest]) - inter + 1e-9)
        order = rest[ov < iou]
    return keep


def decode(out: np.ndarray, s: float, left: int, top: int, conf: float, iou: float,
           groups: list[int] | None = None) -> list[list[float]]:  # fmt: skip
    """YOLO11 head (1, 4 + nc, N): centre-xywh + per-class scores -> boxes in the frame's pixels.
    NMS runs per group of ``groups`` (one group id per class id), else per class."""
    p = out[0].T  # (N, 4 + nc)
    cls_scores = p[:, 4:]
    cls = cls_scores.argmax(1)
    score = cls_scores.max(1)
    m = score >= conf
    if not m.any():
        return []
    cx, cy, w, h = p[m, 0], p[m, 1], p[m, 2], p[m, 3]
    boxes = np.stack([cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2], 1)
    boxes[:, [0, 2]] = (boxes[:, [0, 2]] - left) / s
    boxes[:, [1, 3]] = (boxes[:, [1, 3]] - top) / s
    cm = cls[m]
    grp = cm if groups is None else np.asarray(groups)[cm]
    out_rows: list[list[float]] = []
    for g in np.unique(grp):
        idx = np.nonzero(grp == g)[0]
        for k in nms(boxes[idx], score[m][idx], iou):
            j = idx[k]
            out_rows.append([*(round(float(v), 1) for v in boxes[j]), round(float(score[m][j]), 3),
                             int(cm[j])])  # fmt: skip
    return out_rows


def main() -> int:
    import onnxruntime as ort

    model, conf, iou = sys.argv[1], float(sys.argv[2]), float(sys.argv[3])
    opts = ort.SessionOptions()
    opts.intra_op_num_threads = int(sys.argv[4]) if len(sys.argv) > 4 else 4
    sess = ort.InferenceSession(model, opts, providers=["CPUExecutionProvider"])
    name = sess.get_inputs()[0].name
    size = (int(sess.get_inputs()[0].shape[2]), int(sess.get_inputs()[0].shape[3]))
    groups = json.loads(sys.argv[5]) if len(sys.argv) > 5 else None
    nc = int(sess.get_outputs()[0].shape[1]) - 4
    if groups is not None and (len(groups) != nc or not all(isinstance(g, int) for g in groups)):
        raise SystemExit(f"groups: one int per class id ({nc}), got {groups!r}")
    inp, outp = sys.stdin.buffer, sys.stdout
    while True:
        head = inp.read(8)
        if len(head) < 8:
            return 0
        h, w, _ = struct.unpack("<HHI", head)
        buf = inp.read(h * w * 3)
        img = np.frombuffer(buf, np.uint8).reshape(h, w, 3)
        t = time.perf_counter()
        x, s, left, top = letterbox(img, size)
        out = sess.run(None, {name: x})[0]
        boxes = decode(out, s, left, top, conf, iou, groups)
        reply: dict[str, Any] = {"boxes": boxes, "ms": round((time.perf_counter() - t) * 1000, 1)}
        outp.write(json.dumps(reply) + "\n")
        outp.flush()


if __name__ == "__main__":
    sys.exit(main())
