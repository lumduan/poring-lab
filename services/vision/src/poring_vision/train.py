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
- **Output:** /data/train/<run>/ (checkpoints every epoch). After an IO- or R3-guard SIGINT,
  `--resume` continues from last.pt.
- **R3 (Batt, 2026-10-07):** `--step-sleep-ms N` sleeps N ms after every training batch. That
  lowers our GPU/CPU duty cycle, so the Frigate detector stays within +5 ms of its baseline.
  It changes wall time only, never the maths (batch, seed, data order), and may change at a
  `--resume`.
- **The adaptive duty cycle (Batt, 2026-10-07 ~16:25):** `--duty-file /lab-duty/duty.json`
  makes the sleep LIVE. The host's guarded_build writes the level it derives from Frigate's
  fleet load into a READ-ONLY mount, and it is re-read after every batch. A missing, stale
  (> 120 s) or garbled file means the slowest level (2 s): fail slow, never fast. Batches, running
  seconds and PAUSED seconds per level are printed as `duty_stats` lines: each batch's real wall
  time (compute + the sleep as slept), and a batch longer than PAUSE_GAP_S counts as paused (an R3
  OFF window froze it), never as throughput. Until 2026-10-07 18:20 the NOMINAL sleep was added
  and a frozen batch counted as compute, so the per-level rates of the first v0-JPEG resume mix
  in R3's pauses.
- **Mid-epoch checkpoints (Batt, 2026-10-08), opt-in `--mid-ckpt`:** `weights/mid.pt` every
  `--mid-every-batches` batches or `--mid-every-s` seconds (whichever first, right after an
  optimizer step) and at every epoch end. `--resume` then continues at the exact batch, with the
  data stream, augmentation, mosaic buffer, live weights, optimizer and loop state as they were
  (`poring_vision.midckpt`, `poring_vision.resume`). The run's training order comes from a
  `StreamSampler` instead of ultralytics' shuffling, so a run keeps ONE mode for life
  (`stream.json` marks it; a resume in the other mode is refused). The proof harness: `--trace`,
  `--die-after-batches`, `scripts/resume_proof.py` (docs/operations/mid-epoch-checkpoints.md).
- **The final line** is a JSON summary: per-class AP50, mAP50, mAP50-95, peak VRAM, seconds.
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


DUTY_FALLBACK_MS = 2000  # the slowest level: an unknown duty never speeds us up
DUTY_FILE_STALE_S = 120.0
DUTY_REPORT_EVERY = 500
PAUSE_GAP_S = 30.0  # a batch longer than this was frozen by an R3 OFF window (docker pause)


def read_duty(path: Path, now: float) -> int:
    """The step sleep (ms) the host asks for, or the slowest level when it cannot be trusted."""
    try:
        d = json.loads(path.read_text())
        ms = int(d["sleep_ms"])
        if now - float(d["t_epoch"]) > DUTY_FILE_STALE_S or not 0 <= ms <= 10_000:
            return DUTY_FALLBACK_MS
        return ms
    except (OSError, ValueError, KeyError, TypeError):
        return DUTY_FALLBACK_MS


def step_sleeper(ms: int, duty_file: Path | None = None, report_every: int = DUTY_REPORT_EVERY,
                 out: Any = None) -> Any:  # fmt: skip
    """The R3 duty-cycle knob: an ultralytics `on_train_batch_end` callback that sleeps ``ms``,
    or the live level in ``duty_file``. Accounts each batch's compute + sleep to its level."""
    stats: dict[int, list[float]] = {}  # level ms -> [batches, running s, paused batches, paused s]
    state = {"t": time.monotonic(), "n": 0}

    def report() -> None:
        line = {f"{k}ms": {"batches": int(v[0]), "seconds": round(v[1], 1),
                           "batches_per_s": round((v[0] - v[2]) / v[1], 2) if v[1] else None,
                           "paused_batches": int(v[2]), "paused_s": round(v[3], 1)}
                for k, v in sorted(stats.items())}  # fmt: skip
        print(json.dumps({"duty_stats": line}), file=out or sys.stdout, flush=True)

    def sleep(trainer: Any) -> None:
        cur = read_duty(duty_file, time.time()) if duty_file is not None else ms
        time.sleep(cur / 1000.0)
        now = time.monotonic()
        took = now - state["t"]  # this batch's real wall time: compute + the sleep AS SLEPT
        s = stats.setdefault(cur, [0, 0.0, 0, 0.0])
        s[0] += 1
        if took > PAUSE_GAP_S:
            s[2] += 1
            s[3] += took
        else:
            s[1] += took
        state["t"] = now
        state["n"] += 1
        if report_every and state["n"] % report_every == 0:
            report()

    sleep.report = report  # type: ignore[attr-defined]
    sleep.stats = stats  # type: ignore[attr-defined]
    return sleep


def hyp_overrides(a: argparse.Namespace) -> dict[str, float]:
    """Opt-in augmentation overrides for a NEW run: ``--hsv-s``, the saturation gain
    (docs/planning/payf07-detector.md 12f: Elder Willow and Willow differ by saturation only), and
    ``--scale``, the random rescale gain (gef10-detector.md D7: the RO camera's zoom is fixed, and
    the Orc Lord differs from the Orc Warrior / Archer mainly by SIZE; ultralytics' 0.5 rescales an
    image by 0.5-1.5). Absent: ultralytics' defaults (0.7 / 0.5), as every run before."""
    out: dict[str, float] = {}
    hsv_s = getattr(a, "hsv_s", None)
    if hsv_s is not None:
        if not 0.0 <= hsv_s <= 1.0:
            raise SystemExit(f"--hsv-s {hsv_s}: 0..1")
        out["hsv_s"] = float(hsv_s)
    scale = getattr(a, "scale", None)
    if scale is not None:
        if not 0.0 <= scale <= 0.9:
            raise SystemExit(f"--scale {scale}: 0..0.9")
        out["scale"] = float(scale)
    return out


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
    ap.add_argument("--step-sleep-ms", type=int, default=0,
                    help="R3: sleep after every training batch (duty cycle only)")  # fmt: skip
    ap.add_argument("--duty-file", type=Path, default=None,
                    help="the host's live duty level (read-only)")  # fmt: skip
    ap.add_argument("--mid-ckpt", action="store_true",
                    help="mid-epoch checkpoints + the exact resume")  # fmt: skip
    ap.add_argument("--mid-every-batches", type=int, default=640)
    ap.add_argument("--mid-every-s", type=float, default=300.0)
    ap.add_argument("--close-mosaic", type=int, default=None,
                    help="ultralytics' close_mosaic (default 10); the proof uses 1")  # fmt: skip
    ap.add_argument("--hsv-s", type=float, default=None,
                    help="ultralytics' hsv_s (default 0.7); payf07 12f proposes 0.2")  # fmt: skip
    ap.add_argument("--scale", type=float, default=None,
                    help="ultralytics' scale (default 0.5); gef10 D7 uses 0.1")  # fmt: skip
    ap.add_argument("--trace", type=Path, default=None,
                    help="--mid-ckpt: one JSON line per batch (the resume proof)")  # fmt: skip
    ap.add_argument("--die-after-batches", type=int, default=None,
                    help="PROOF ONLY: os._exit after this global batch (ni)")  # fmt: skip
    a = ap.parse_args()
    if (a.trace is not None or a.die_after_batches is not None) and not a.mid_ckpt:
        raise SystemExit("--trace / --die-after-batches need --mid-ckpt")
    t0 = time.monotonic()

    from poring_vision import accel
    from poring_vision.gpu import configure_gpu

    fraction = float(os.environ.get("VISION_MAX_VRAM_FRACTION", "0.25"))
    acc = accel.current()  # any vendor (ADR-0022): $PORING_ACCEL, else the first available
    device = configure_gpu(fraction, acc)
    if device is None:
        raise SystemExit("no GPU: training needs the card (the cap is set first)")

    import cv2
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

    from poring_vision.midckpt import StreamItems

    class ShardTrainer(DetectionTrainer):  # type: ignore[misc]
        def get_dataset(self) -> dict[str, Any]:
            return dict(data)

        def build_dataset(
            self, img_path: str, mode: str = "train", batch: int | None = None
        ) -> Any:
            gs = max(int(unwrap_model(self.model).stride.max()), 32) if self.model else 32
            bases = (
                (StreamItems, ShardDataset) if a.mid_ckpt and mode == "train" else (ShardDataset,)
            )
            cls = type(f"ShardDataset_{img_path}", bases, {"part": img_path})
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
        "device": acc.ultralytics_device, "seed": a.seed, "cache": False, "amp": True,
        "verbose": False,
    }  # fmt: skip
    if a.close_mosaic is not None:
        overrides["close_mosaic"] = a.close_mosaic
    overrides.update(hyp_overrides(a))
    if a.resume:
        from poring_vision.midckpt import effective_workers

        n = len(splits["train"])
        nb = -(-n // a.batch)
        run = {"n": n, "nb": nb, "batch": a.batch,
               "workers": effective_workers(a.workers, nb, acc.device_count())}  # fmt: skip
        if a.close_mosaic is not None:  # else the checkpoint's own value is used
            run["close_mosaic"] = a.close_mosaic
        overrides["resume"] = str(resume_checkpoint(a, run_dir, overrides["epochs"], run))
    else:  # a fresh run: nothing of an older run in this directory may be resumed into it
        for f in ("mid.pt", "mid.prev.pt", "mid.pt.tmp"):
            (run_dir / "weights" / f).unlink(missing_ok=True)
        (run_dir / "stream.json").unlink(missing_ok=True)
        if a.mid_ckpt:
            run_dir.mkdir(parents=True, exist_ok=True)
            (run_dir / "stream.json").write_text(json.dumps({"sampler": "StreamSampler",
                                                             "seed": a.seed}) + "\n")  # fmt: skip
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
    trainer_cls: type = ShardTrainer
    if a.mid_ckpt:
        from poring_vision.midckpt import MidOptions, resumable

        opts = MidOptions(every_batches=a.mid_every_batches, every_s=a.mid_every_s, trace=a.trace,
                          die_at=a.die_after_batches)  # fmt: skip
        trainer_cls = resumable(ShardTrainer, opts)
    trainer = trainer_cls(overrides=overrides)
    sleeper = None
    if a.step_sleep_ms > 0 or a.duty_file is not None:
        sleeper = step_sleeper(a.step_sleep_ms, a.duty_file)
        trainer.add_callback("on_train_batch_end", sleeper)
    print(json.dumps({"step_sleep_ms": a.step_sleep_ms, "duty_file": str(a.duty_file),
                      "resume": a.resume}), flush=True)  # fmt: skip
    trainer.train()
    if sleeper is not None:
        sleeper.report()

    metrics = getattr(trainer.validator, "metrics", None)
    per_class: dict[str, float] = {}
    if metrics is not None and hasattr(metrics, "box"):
        for j, c in enumerate(getattr(metrics, "ap_class_index", [])):
            per_class[names.get(int(c), str(c))] = round(float(metrics.box.ap50[j]), 4)
    summary = {
        "run": str(run_dir), "cache": str(a.cache), "smoke": a.smoke,
        "train_frames": len(splits["train"]), "val_frames": len(splits["val"]),
        "epochs": overrides["epochs"], "imgsz": a.imgsz, "batch": a.batch, "workers": a.workers,
        "step_sleep_ms": a.step_sleep_ms,
        "metrics": {k: round(float(v), 4) for k, v in (trainer.metrics or {}).items()},
        "ap50_per_class": per_class,
        "accelerator": accel.describe(acc), "peak_vram_mib": acc.peak_mib(),
        "cap_mib": None if acc.total_mib() is None else round(acc.total_mib() * fraction, 1),
        "seconds": round(time.monotonic() - t0, 1),
    }  # fmt: skip
    print(json.dumps(summary), flush=True)
    return 0


def resume_checkpoint(a: argparse.Namespace, run_dir: Path, epochs: int,
                      run: dict[str, Any] | None = None) -> Path:  # fmt: skip
    """The checkpoint ``--resume`` continues from. A run keeps its stream mode for life: a resume
    in the other mode is refused (``stream.json`` marks a --mid-ckpt run).
    With --mid-ckpt (Batt 2026-10-08 ~10:50: the latest AND the previous mid checkpoint):
    - mid.pt, else mid.prev.pt when mid.pt is unreadable, fails its own digest, or contradicts
      the run while mid.prev.pt agrees (`choose_mid`; which one and why is logged);
    - a genuine setup mismatch (``run``: frames, batches, batch, workers, close_mosaic) refuses
      with both;
    - the chosen one never rewinds the run behind last.pt; last.pt alone is ultralytics' own
      epoch-level resume, which is NOT exact (logged)."""
    from poring_vision.midckpt import MID_NAME, PREV_NAME, STREAM_NAME, inspect_mid, read_last_epoch
    from poring_vision.resume import choose_mid, pick_resume

    wdir = run_dir / "weights"
    marked = (run_dir / STREAM_NAME).exists()
    if marked != a.mid_ckpt:
        raise SystemExit(f"{run_dir} was trained {'WITH' if marked else 'WITHOUT'} --mid-ckpt: "
                         "resume it the same way (one data stream per run)")  # fmt: skip
    if not a.mid_ckpt:
        return wdir / "last.pt"
    cands = [inspect_mid(wdir / MID_NAME), inspect_mid(wdir / PREV_NAME)]
    chosen, notes = choose_mid(cands, run or {})
    meta = chosen.meta if chosen else None
    choice = pick_resume(meta, read_last_epoch(wdir / "last.pt"), epochs)
    used = chosen.name if choice == "mid" and chosen else ("last.pt" if choice == "last" else None)
    print(json.dumps({"resume_from": used, "skipped": notes,
                      "mid": meta and {k: meta[k] for k in ("epoch", "next_i", "nb")}}),
          flush=True)  # fmt: skip
    if used is None:
        raise SystemExit(f"{run_dir}: nothing to resume")
    if used == "last.pt":
        print(json.dumps({"warning": "epoch-level resume from last.pt: NOT exact"}), flush=True)
    return wdir / used


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
    import ultralytics.engine.validator as ul_validator

    from poring_vision import accel

    acc = accel.current()  # main() configured it already (configure_gpu)
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
                        device=acc.ultralytics_device, plots=False, split="val", verbose=False,
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
        "accelerator": accel.describe(acc), "peak_vram_mib": acc.peak_mib(),
        "cap_mib": None if acc.total_mib() is None else round(acc.total_mib() * fraction, 1),
        "seconds": round(time.monotonic() - t0, 1),
    }  # fmt: skip
    print(json.dumps(summary), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
