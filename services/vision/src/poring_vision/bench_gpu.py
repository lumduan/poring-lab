"""How fast is a detector on the GPU? (Batt 2026-11-07: "compare: how much faster would the GPU be")

    python -m poring_vision.bench_gpu --refs /data/.../latency-200-refs.json \
        --weights v1=/datasets/archive/train/v1png-20261008/weights/last.pt \
        --weights xmas02=/datasets/archive/train/xmas02-20261106/weights/last.pt \
        --out /data/train/eval/gpu-bench/bench.json \
        [--sustain-model xmas02 --sustain-s 600 --rate 10]

Phase A, per model and precision (FP32, FP16): ``--warmup`` predicts, then one predict per frame
of ``--refs`` (predict_dir's tar-shard refs, decoded to BGR before the clock starts), each timed
from the call to the boxes on the host (``torch.cuda.synchronize``), with ultralytics' own split
(preprocess / inference / postprocess). The boxes are kept (``--keep-boxes``) so the host can check
them against the CPU ONNX path. Also the bare forward pass on one fixed 1 x 3 x 736 x 1280 tensor.
Phase B (optional): one model at ``--rate`` predicts a second for ``--sustain-s``, the live load a
GPU box watcher would put on the card, so guarded_build's paired R3 measures what it costs Frigate.

guarded_build pauses the container in R3's OFF windows: a call that spans a pause is not a
detection time, so calls slower than ``--pause-ms`` are counted apart and left out of the summary.
predict uses iou 0.5 (unit_detector.IOU), not ultralytics' 0.7, so its boxes compare with the CPU's.
"""

from __future__ import annotations

import argparse
import json
import os
import time
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from poring_vision.predict_dir import load_refs, read_ref, timing_summary

IOU = 0.5  # unit_detector.IOU
CONF = 0.25  # unit_detector.CONF
IMGSZ = (736, 1280)  # the CPU ONNX's input (h, w)
PAUSE_MS = 1000.0  # a call this slow spanned an R3 pause


def split_paused(ms: Sequence[float], pause_ms: float = PAUSE_MS) -> tuple[list[float], int]:
    """PURE: (the calls that did not span a pause, how many did)."""
    kept = [m for m in ms if m < pause_ms]
    return kept, len(ms) - len(kept)


def parse_weights(items: Sequence[str]) -> dict[str, str]:
    """PURE: ["name=path", ...] -> {name: path}; names distinct and non-empty."""
    out: dict[str, str] = {}
    for item in items:
        name, sep, path = item.partition("=")
        if not sep or not name or not path or name in out:
            raise SystemExit(f"--weights {item!r}: NAME=PATH, each name once")
        out[name] = path
    return out


def summarise(walls: Sequence[float], speeds: Sequence[dict[str, float]]) -> dict[str, Any]:
    """PURE: the wall-time summary without paused calls, plus ultralytics' split (p50 each)."""
    kept, paused = split_paused(walls)
    out: dict[str, Any] = {"wall_ms": timing_summary(kept), "paused_calls": paused}
    for part in ("preprocess", "inference", "postprocess"):
        vals = [float(s[part]) for s, w in zip(speeds, walls, strict=True)
                if part in s and w < PAUSE_MS]  # fmt: skip
        out[part + "_ms"] = timing_summary(vals)
    return out


def timed(fn: Callable[[], Any], sync: Callable[[], None]) -> tuple[Any, float]:
    t0 = time.perf_counter()
    res = fn()
    sync()
    return res, (time.perf_counter() - t0) * 1000.0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)  # fmt: skip
    ap.add_argument("--refs", type=Path, required=True)
    ap.add_argument("--weights", action="append", required=True, help="NAME=PATH, repeatable")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--warmup", type=int, default=10)
    ap.add_argument("--forward-n", type=int, default=100)
    ap.add_argument("--keep-boxes", action=argparse.BooleanOptionalAction, default=True)
    ap.add_argument("--sustain-model", default=None, help="phase B's model (a --weights NAME)")
    ap.add_argument("--sustain-half", action=argparse.BooleanOptionalAction, default=True)
    ap.add_argument("--sustain-s", type=float, default=0.0)
    ap.add_argument("--rate", type=float, default=10.0, help="phase B's predicts a second")
    a = ap.parse_args(argv)
    weights = parse_weights(a.weights)
    if a.sustain_model is not None and a.sustain_model not in weights:
        raise SystemExit(f"--sustain-model {a.sustain_model!r} is not a --weights name")

    from poring_vision.gpu import configure_gpu

    device = configure_gpu(float(os.environ.get("VISION_MAX_VRAM_FRACTION", "0.25")))
    if device is None:
        raise SystemExit("no GPU: the cap is set first, and this needs the card")
    import cv2
    import numpy as np
    import torch
    from ultralytics import YOLO

    sync = torch.cuda.synchronize
    frames: list[tuple[str, Any]] = []
    for key, ref in load_refs(a.refs).items():
        img = cv2.imdecode(np.frombuffer(read_ref(ref), np.uint8), cv2.IMREAD_COLOR)
        if img is None:
            raise SystemExit(f"{key}: does not decode")
        frames.append((key, img))
    out: dict[str, Any] = {
        "what": "bench_gpu (Batt 2026-11-07): detection time on the GPU, per model and precision",
        "gpu": torch.cuda.get_device_name(0), "torch": torch.__version__,
        "cuda": torch.version.cuda, "imgsz": list(IMGSZ), "conf": CONF, "iou": IOU,
        "frames": len(frames), "refs": str(a.refs), "started": time.strftime("%FT%T%z"),
        "vram_fraction": float(os.environ.get("VISION_MAX_VRAM_FRACTION", "0.25")),
        "runs": {}, "forward": {},
    }  # fmt: skip
    # a FRESH YOLO per precision: ultralytics sets its backend's fp16 when the predictor is first
    # set up, and a later predict(half=...) on the same object would not change it
    for name, path in weights.items():
        for half in (False, True):
            tag = f"{name}-{'fp16' if half else 'fp32'}"
            model = YOLO(path)
            names = model.names

            def call(img: Any, model: Any = model, half: bool = half) -> Any:
                return model.predict(img, imgsz=list(IMGSZ), conf=CONF, iou=IOU, half=half,
                                     device=0, verbose=False)[0]  # fmt: skip

            for _k, img in frames[: a.warmup]:
                timed(lambda img=img: call(img), sync)
            torch.cuda.reset_peak_memory_stats(0)
            walls: list[float] = []
            speeds: list[dict[str, float]] = []
            boxes: dict[str, list[list[Any]]] = {}
            for key, img in frames:
                res, ms = timed(lambda img=img: call(img), sync)
                walls.append(round(ms, 3))
                speeds.append({k: round(float(v), 3) for k, v in (res.speed or {}).items()})
                if a.keep_boxes:
                    b = res.boxes
                    boxes[key] = [[*(round(float(v), 1) for v in xy), round(float(p), 3),
                                   names[int(c)]] for xy, c, p in zip(
                        b.xyxy.tolist(), b.cls.tolist(), b.conf.tolist(), strict=True)]  # fmt: skip
            out["runs"][tag] = {**summarise(walls, speeds), "per_frame_ms": walls,
                                "peak_vram_mib": round(torch.cuda.max_memory_allocated(0) / 2**20),
                                **({"boxes": boxes} if a.keep_boxes else {})}  # fmt: skip
            brief = {k: v for k, v in out["runs"][tag].items()
                     if k.endswith("_ms") and k != "per_frame_ms"}  # fmt: skip
            print(json.dumps({tag: brief}), flush=True)
            net = YOLO(path).model.fuse().to(device).eval()  # fused, as predict's backend
            x = torch.zeros((1, 3, *IMGSZ), device=device)
            if half:
                net, x = net.half(), x.half()
            with torch.inference_mode():
                for _ in range(10):
                    net(x)
                sync()
                fw = [timed(lambda net=net, x=x: net(x), sync)[1] for _ in range(a.forward_n)]
            out["forward"][tag] = timing_summary(split_paused(fw)[0])
            del model, net
            torch.cuda.empty_cache()
    if a.sustain_model is not None and a.sustain_s > 0:
        model = YOLO(weights[a.sustain_model])
        half = bool(a.sustain_half)
        period = 1.0 / a.rate
        walls = []
        t_end = time.monotonic() + a.sustain_s
        i = 0
        while time.monotonic() < t_end:
            t = time.monotonic()
            img = frames[i % len(frames)][1]
            _r, ms = timed(lambda img=img: model.predict(img, imgsz=list(IMGSZ), conf=CONF,
                                                         iou=IOU, half=half, device=0,
                                                         verbose=False), sync)  # fmt: skip
            walls.append(round(ms, 3))
            i += 1
            time.sleep(max(0.0, period - (time.monotonic() - t)))
        kept, paused = split_paused(walls)
        out["sustain"] = {"model": a.sustain_model, "half": half, "rate_hz": a.rate,
                          "seconds": a.sustain_s, "calls": len(walls), "paused_calls": paused,
                          "wall_ms": timing_summary(kept)}  # fmt: skip
        print(json.dumps({"sustain": out["sustain"]}), flush=True)
    out["ended"] = time.strftime("%FT%T%z")
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(out))
    print(json.dumps({"out": str(a.out), "runs": list(out["runs"])}), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
