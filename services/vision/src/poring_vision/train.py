"""Train YOLO on a frame cache read from the NAS (Phase 3 Part D / M9).

    python -m poring_vision.train --cache /datasets/.framecache/<id> [--smoke] [--epochs N]
        [--batch B] [--imgsz 1280] [--workers W] [--name RUN] [--resume]
    python -m poring_vision.train --cache ... --eval /data/train/<run>/weights/best.pt
        [--split test] [--sessions S [S ...]]      (evaluate only: a held-out split or sessions)

ADR-0018: this module imports ultralytics (AGPL-3.0), so it belongs to the AGPL vision component.
It runs inside the vision container only (guarded_build `run:`/`rundev:`), never on the host.

- **Data:** the cache's tar shards, read through `poring_vision.shards`, with nothing extracted.
  Ultralytics' YOLODataset gets virtual image names (`/shard/<n>.jpg`), labels straight from the
  shards' YOLO txt, and the module-level `imread` it uses resolves a virtual name to the JPEG
  bytes in the shard. Upstream resize, mosaic and validation run unchanged, and nothing is written
  next to the read-only data (no label cache).
- **The GPU:** `configure_gpu` caps this process at VISION_MAX_VRAM_FRACTION (25 %) BEFORE
  ultralytics touches CUDA. Batch is fixed, with no AutoBatch: it would size against the whole
  card, not the cap.
- **Offline:** vision has no internet (`YOLO_OFFLINE=1`). Weights come from /data/weights (fetched
  on the host, sha256 in THIRD_PARTY.md); plots are off (they would fetch a font).
- **Output:** /data/train/<run>/ (checkpoints every epoch). After an IO-guard SIGINT, `--resume`
  continues from last.pt. The final line is a JSON summary: per-class AP50, mAP50, mAP50-95, peak
  VRAM, seconds.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np

from poring_vision.shards import Sample, load_split, read_image

VIRTUAL = "/shard/"


def label_dicts(samples: list[Sample], h: int = 720, w: int = 1280) -> list[dict[str, Any]]:
    """Ultralytics' label records (dataset.py: im_file, shape, cls, bboxes, ...) for our samples."""
    out = []
    for i, s in enumerate(samples):
        lb = s.labels
        out.append({
            "im_file": f"{VIRTUAL}{i}.jpg", "shape": (h, w),
            "cls": lb[:, 0:1].astype(np.float32), "bboxes": lb[:, 1:5].astype(np.float32),
            "segments": [], "keypoints": None, "normalized": True, "bbox_format": "xywh",
        })  # fmt: skip
    return out


def main() -> int:  # noqa: PLR0915
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--cache", type=Path, required=True)
    ap.add_argument("--weights", type=Path, default=Path("/data/weights/yolo11n.pt"))
    ap.add_argument("--imgsz", type=int, default=1280)
    ap.add_argument("--epochs", type=int, default=100)
    ap.add_argument("--batch", type=int, default=4)
    ap.add_argument("--workers", type=int, default=0)
    ap.add_argument("--project", type=Path, default=Path("/data/train"))
    ap.add_argument("--name", default=None)
    ap.add_argument("--resume", action="store_true")
    ap.add_argument("--smoke", action="store_true", help="200 frames/train session, 100/val, 3 ep")
    ap.add_argument("--seed", type=int, default=20261004)
    ap.add_argument("--eval", type=Path, default=None, help="evaluate these weights only")
    ap.add_argument("--split", default="test", help="--eval: the split to evaluate")
    ap.add_argument("--sessions", nargs="*", default=None, help="--eval: only these sessions")
    a = ap.parse_args()
    t0 = time.monotonic()

    from poring_vision.gpu import configure_gpu

    fraction = float(os.environ.get("VISION_MAX_VRAM_FRACTION", "0.25"))
    device = configure_gpu(fraction)
    if device is None:
        raise SystemExit("no GPU: training needs the card (the cap is set first)")

    import cv2
    import torch
    import ultralytics.data.base as ul_base
    from ultralytics.data.dataset import YOLODataset
    from ultralytics.models.yolo.detect import DetectionTrainer
    from ultralytics.utils import colorstr
    from ultralytics.utils.torch_utils import unwrap_model

    limit = {"train": 200, "val": 100} if a.smoke else {"train": None, "val": None}
    splits: dict[str, list[Sample]] = {}
    names: dict[int, str] = {}
    if a.eval is not None:  # evaluation only: ONE split (or some of its sessions) as "eval"
        splits["eval"], names = load_split(a.cache, a.split, sessions=a.sessions)
    else:
        for part in ("train", "val"):
            splits[part], names = load_split(a.cache, part, limit_per_session=limit[part])
    for part, samples in splits.items():
        if not samples:
            raise SystemExit(f"the {part} split is empty in {a.cache}")
    registry: dict[str, Sample] = {}
    for part, samples in splits.items():
        for i, s in enumerate(samples):
            registry[f"{VIRTUAL}{part}/{i}.jpg"] = s

    original_imread = ul_base.imread

    def shard_imread(filename: str, flags: int = cv2.IMREAD_COLOR) -> Any:
        sample = registry.get(str(filename))
        if sample is None:
            return original_imread(filename, flags)
        buf = np.frombuffer(read_image(sample), np.uint8)
        return cv2.imdecode(buf, flags)

    ul_base.imread = shard_imread  # the dataset module's own reference (base.py imports it)

    class ShardDataset(YOLODataset):  # type: ignore[misc]
        part = "train"

        def get_img_files(self, img_path: Any) -> list[str]:
            return [f"{VIRTUAL}{self.part}/{i}.jpg" for i in range(len(splits[self.part]))]

        def get_labels(self) -> list[dict[str, Any]]:
            labels = label_dicts(splits[self.part])
            for i, lb in enumerate(labels):
                lb["im_file"] = f"{VIRTUAL}{self.part}/{i}.jpg"
            return labels

    data = {"train": "train", "val": "val", "names": names, "nc": len(names), "channels": 3}
    if a.eval is not None:
        data["val"] = "eval"

    class ShardTrainer(DetectionTrainer):  # type: ignore[misc]
        def get_dataset(self) -> dict[str, Any]:
            return dict(data)

        def build_dataset(
            self, img_path: str, mode: str = "train", batch: int | None = None
        ) -> Any:
            gs = max(int(unwrap_model(self.model).stride.max()), 32) if self.model else 32
            cls = type(f"ShardDataset_{img_path}", (ShardDataset,), {"part": img_path})
            return cls(
                img_path=img_path, imgsz=self.args.imgsz, batch_size=batch,
                augment=mode == "train", hyp=self.args, rect=mode == "val", cache=None,
                single_cls=False, stride=gs, pad=0.0 if mode == "train" else 0.5,
                prefix=colorstr(f"{mode}: "), task="detect", classes=self.args.classes,
                data=self.data, fraction=1.0,
            )  # fmt: skip

    if a.eval is not None:
        return evaluate(a, splits, names, data, ShardDataset, t0, fraction)

    name = a.name or ("smoke" if a.smoke else a.cache.name)
    run_dir = a.project / name
    overrides = {
        "model": str(a.weights), "data": "shards", "imgsz": a.imgsz,
        "epochs": 3 if a.smoke else a.epochs, "batch": a.batch, "workers": a.workers,
        "project": str(a.project), "name": name, "exist_ok": True, "plots": False,
        "device": 0, "seed": a.seed, "cache": False, "amp": True, "verbose": False,
    }  # fmt: skip
    if a.resume:
        overrides["resume"] = str(run_dir / "weights" / "last.pt")
    # ultralytics' AMP self-check downloads yolo26n.pt; vision is offline (and its cwd read-only),
    # so it dies with PermissionError (2026-10-04 smoke run). fp16 on this card is verified by
    # scripts/check_gpu.py (matmul + conv2d in fp16), so the check is skipped, not faked.
    import ultralytics.engine.trainer as ul_trainer

    ul_trainer.check_amp = lambda model: True
    # The final evaluation of best.pt runs the validator standalone: it already holds our val
    # dataloader (the trainer's test_loader) but re-resolves `data` by name through
    # check_det_dataset, which knows no "shards" (2026-10-04 smoke run). Answer that one name.
    import ultralytics.engine.validator as ul_validator

    check_det = ul_validator.check_det_dataset

    def shard_dataset(dataset: Any, *args: Any, **kwargs: Any) -> dict[str, Any]:
        return dict(data) if dataset == "shards" else check_det(dataset, *args, **kwargs)

    ul_validator.check_det_dataset = shard_dataset
    trainer = ShardTrainer(overrides=overrides)
    trainer.train()

    metrics = getattr(trainer.validator, "metrics", None)
    per_class: dict[str, float] = {}
    if metrics is not None and hasattr(metrics, "box"):
        for j, c in enumerate(getattr(metrics, "ap_class_index", [])):
            per_class[names.get(int(c), str(c))] = round(float(metrics.box.ap50[j]), 4)
    summary = {
        "run": str(run_dir), "cache": str(a.cache), "smoke": a.smoke,
        "train_frames": len(splits["train"]), "val_frames": len(splits["val"]),
        "epochs": overrides["epochs"], "imgsz": a.imgsz, "batch": a.batch, "workers": a.workers,
        "metrics": {k: round(float(v), 4) for k, v in (trainer.metrics or {}).items()},
        "ap50_per_class": per_class,
        "peak_vram_mib": round(torch.cuda.max_memory_reserved() / 2**20, 1),
        "cap_mib": round(torch.cuda.get_device_properties(0).total_memory * fraction / 2**20, 1),
        "seconds": round(time.monotonic() - t0, 1),
    }  # fmt: skip
    print(json.dumps(summary), flush=True)
    return 0


def evaluate(
    a: argparse.Namespace,
    splits: dict[str, list[Sample]],
    names: dict[int, str],
    data: dict[str, Any],
    shard_dataset_cls: type,
    t0: float,
    fraction: float,
) -> int:
    """Validate saved weights on one split (or some of its sessions) through ultralytics' own
    validator: its dataset is our ShardDataset, its data dict ours (no files, nothing written)."""
    import torch
    import ultralytics.engine.validator as ul_validator
    from ultralytics import YOLO
    from ultralytics.models.yolo.detect import DetectionValidator
    from ultralytics.utils import colorstr

    ul_validator.check_det_dataset = lambda dataset, *args, **kw: dict(data)

    def build_dataset(self: Any, img_path: str, mode: str = "val", batch: int | None = None) -> Any:
        stride = 32  # YOLO11's largest stride: the rect batches' padding unit
        cls = type(f"ShardDataset_{img_path}", (shard_dataset_cls,), {"part": img_path})
        return cls(
            img_path=img_path, imgsz=self.args.imgsz, batch_size=batch, augment=False,
            hyp=self.args, rect=True, cache=None, single_cls=False, stride=stride, pad=0.5,
            prefix=colorstr("eval: "), task="detect", classes=self.args.classes, data=data,
            fraction=1.0,
        )  # fmt: skip

    DetectionValidator.build_dataset = build_dataset
    model = YOLO(str(a.eval))
    metrics = model.val(data="shards", imgsz=a.imgsz, batch=a.batch, workers=a.workers,
                        device=0, plots=False, split="val", verbose=False,
                        project=str(a.project), name="eval", exist_ok=True)  # fmt: skip
    box = metrics.box
    per_class = {names.get(int(c), str(c)): {"ap50": round(float(box.ap50[j]), 4),
                                             "ap": round(float(box.ap[j]), 4)}
                 for j, c in enumerate(metrics.ap_class_index)}  # fmt: skip
    summary = {
        "eval": str(a.eval), "cache": str(a.cache), "split": a.split, "sessions": a.sessions,
        "frames": len(splits["eval"]), "mAP50": round(float(box.map50), 4),
        "mAP50-95": round(float(box.map), 4), "precision": round(float(box.mp), 4),
        "recall": round(float(box.mr), 4), "per_class": per_class,
        "inference_ms_per_image": round(float(metrics.speed.get("inference", 0.0)), 2),
        "peak_vram_mib": round(torch.cuda.max_memory_reserved() / 2**20, 1),
        "cap_mib": round(torch.cuda.get_device_properties(0).total_memory * fraction / 2**20, 1),
        "seconds": round(time.monotonic() - t0, 1),
    }  # fmt: skip
    print(json.dumps(summary), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
