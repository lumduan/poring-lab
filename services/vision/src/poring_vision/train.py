"""Train YOLO on a frame cache read from the NAS (Phase 3 Part D / M9).

    python -m poring_vision.train --cache /datasets/.framecache/<id> [--smoke] [--epochs N]
        [--batch B] [--imgsz 1280] [--workers W] [--name RUN] [--resume]

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

from poring_vision.shards import Sample, load_split, read_jpeg

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
    for part in ("train", "val"):
        splits[part], names = load_split(a.cache, part, limit_per_session=limit[part])
        if not splits[part]:
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
        buf = np.frombuffer(read_jpeg(sample), np.uint8)
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


if __name__ == "__main__":
    sys.exit(main())
