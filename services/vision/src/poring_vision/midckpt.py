# ruff: noqa: E501 -- `_do_train` below is ultralytics' method, kept with its own (120-col) lines and
# fenced from the formatter, so it diffs line by line against the pinned 8.4.165.
"""Mid-epoch checkpoints with an EXACT resume, the torch half (Batt, 2026-10-08).

ADR-0018: AGPL-3.0, like the rest of poring_vision.train. `resumable()` returns a subclass of our
ShardTrainer whose `_do_train` is a COPY of ultralytics 8.4.165's `BaseTrainer._do_train`
(ultralytics/engine/trainer.py, AGPL-3.0, (c) Ultralytics), changed only where a line says
`# poring:`. Re-diff it against the pinned version before any ultralytics bump.

What it adds (the torch-free logic and the reasons are in `poring_vision.resume`):
- the training loader iterates a `StreamSampler`; the dataset keys each sample's augmentation to
  its stream position (`StreamItems`), and the loader seeks to the trainer's own (epoch, batch)
  whenever it starts a new iterator (`StreamLoader`);
- `weights/mid.pt`: written atomically (tmp + os.replace) right after an optimizer step, every
  `every_batches` batches or `every_s` seconds, whichever comes first, and at every epoch end
  (the boundary, so an epoch-level resume is exact too). It holds the LIVE model (fp32), the EMA
  (fp32), the optimizer (full precision), the scaler, the loop counters, the running loss, the
  stopper, the mosaic buffer and the RNG states, plus a digest of the training state;
- `--resume` prefers mid.pt (`pick_resume`) and restores all of it; the restored state's digest
  must equal the saved one (logged, and traced for the proof);
- the proof harness: `trace` (one JSON line per batch) and `die_at` (os._exit right after a
  batch, no save: a kill).
Stock ultralytics resume, for contrast: the model restarts from the EMA weights, the optimizer
state is rounded to fp16, and the data order restarts at epoch 0's.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import random
import time
import warnings
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from poring_vision.resume import (
    MID_VERSION,
    KeyedRandomness,
    StreamSampler,
    check_compatible,
    digest,
    mid_due,
    next_position,
    sample_seeds,
)

MID_NAME = "mid.pt"
STREAM_NAME = "stream.json"  # marks a run trained on the StreamSampler (its resumes must be too)
DIE_RC = 86  # the proof's deliberate kill


@dataclass(frozen=True)
class MidOptions:
    every_batches: int = 640  # ~4.7 min at v0-JPEG's level-0 rate (2.28 batches/s, 2026-10-08)
    every_s: float = 300.0  # ... and at most 5 min at any duty level (2 s/batch at the slowest)
    trace: Path | None = None
    die_at: int | None = None  # the global batch number (ni) after which the process dies


class StreamItems:
    """Mix in BEFORE the dataset class: an item ``(index, epoch, pos)`` from the StreamSampler is
    augmented under RNGs seeded from (seed, epoch, pos); the output carries its index, position
    and the mosaic buffer after it (for the trace and the checkpoint). Plain int items (the
    validator) take the stock path."""

    poring_seed: int = 0

    def __getitem__(self, item: Any) -> Any:
        if not isinstance(item, tuple):
            return super().__getitem__(item)  # type: ignore[misc]
        try:
            import torch
        except ImportError:  # the host's tests (no torch); the container always has it
            torch = None  # type: ignore[assignment]

        index, epoch, pos = item
        with KeyedRandomness(sample_seeds(self.poring_seed, epoch, pos), torch):
            out = super().__getitem__(index)  # type: ignore[misc]
        out["poring_idx"] = int(index)
        out["poring_pos"] = (int(epoch), int(pos))
        out["poring_buf"] = tuple(int(j) for j in self.buffer)  # type: ignore[attr-defined]
        return out


def tensor_bytes(t: Any) -> tuple[str, tuple[int, ...], bytes]:
    a = t.detach().cpu().contiguous()
    return str(a.dtype), tuple(a.shape), a.numpy().tobytes() if a.numel() else b""


def to_cpu(obj: Any) -> Any:
    """A CPU copy of a nested state (no VRAM spent: the 25 % cap)."""
    if hasattr(obj, "detach"):
        return obj.detach().to("cpu", copy=True).contiguous()
    if isinstance(obj, dict):
        return {k: to_cpu(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [to_cpu(v) for v in obj]
    if isinstance(obj, tuple):
        return tuple(to_cpu(v) for v in obj)
    return deepcopy(obj)


def read_mid_meta(path: Path) -> dict[str, Any] | None:
    """The resume position etc. of a mid checkpoint (None: absent or unreadable)."""
    if not path.exists():
        return None
    from ultralytics.utils.patches import torch_load

    try:
        ck = torch_load(str(path), map_location="cpu")
        mid = ck.get("poring_mid") if isinstance(ck, dict) else None
        return {k: mid[k] for k in ("epoch", "next_i", "nb", "n", "batch", "seed", "workers",
                                     "close_mosaic", "state_sha256")} if mid else None  # fmt: skip
    except Exception as e:  # noqa: BLE001 -- an unreadable mid.pt must not block the epoch resume
        print(json.dumps({"mid_ckpt_unreadable": str(path), "error": repr(e)[:200]}), flush=True)
        return None


def read_last_epoch(path: Path) -> int | None:
    if not path.exists():
        return None
    from ultralytics.utils.patches import torch_load

    return int(torch_load(str(path), map_location="cpu").get("epoch", -1))


def resumable(base: type, opts: MidOptions) -> type:  # noqa: PLR0915
    """``base`` (our ShardTrainer) with the stream loader, mid checkpoints and the exact resume."""
    import torch
    from torch import distributed as dist
    from ultralytics.data.build import InfiniteDataLoader, seed_worker
    from ultralytics.utils import LOGGER, RANK, TQDM, colorstr
    from ultralytics.utils.torch_utils import (
        autocast,
        get_torch_device_backend,
        torch_distributed_zero_first,
        unwrap_model,
    )

    class StreamLoader(InfiniteDataLoader):  # type: ignore[misc]
        """Seeks its StreamSampler to the trainer's position whenever a NEW iterator (a new
        worker) starts: the run's start and close_mosaic's reset. Never in between, so the
        prefetch that runs ahead into the next epoch stays in order."""

        position: Any = None

        def __iter__(self) -> Any:
            if self.iterator is None and self.position is not None:
                self.sampler.seek(*self.position())
            yield from super().__iter__()

    class Resumable(base):  # type: ignore[misc,valid-type]
        _poring_resume: dict[str, Any] | None = None
        _poring_pos: tuple[int, int] = (0, 0)

        # --- the stream ---------------------------------------------------------------------
        def get_dataloader(self, dataset_path: str, batch_size: int = 16, rank: int = 0,
                           mode: str = "train") -> Any:  # fmt: skip
            if mode != "train":
                return super().get_dataloader(dataset_path, batch_size, rank, mode)
            # poring: 8.4.165's DetectionTrainer.get_dataloader + data.build.build_dataloader for
            # ONE GPU, with the StreamSampler in place of the generator-shuffled RandomSampler
            if rank not in (-1, 0) or self.world_size > 1:
                raise SystemExit("mid-epoch checkpoints support one GPU only")
            with torch_distributed_zero_first(rank):
                dataset = self.build_dataset(dataset_path, mode, batch_size)
            seed = int(self.args.seed)
            dataset.poring_seed = seed
            sampler = StreamSampler(len(dataset), seed, batch_size)
            batches = math.ceil(len(dataset) / batch_size)
            dev = getattr(self.device, "type", str(self.device).split(":")[0])
            nd = (
                get_torch_device_backend(self.device).device_count()
                if dev not in {"cpu", "mps"}
                else 0
            )
            nw = min(
                (os.cpu_count() or 1) // max(nd, 1),
                self.args.workers,
                0 if batches <= 1 else batches,
            )
            generator = torch.Generator()  # only the workers' base seed: augmentation is keyed
            generator.manual_seed((6148914691236517205 + RANK + seed) % (1 << 64))
            loader = StreamLoader(
                dataset=dataset, batch_size=batch_size, shuffle=False, num_workers=nw,
                sampler=sampler, prefetch_factor=4 if nw > 0 else None, pin_memory=nd > 0,
                collate_fn=getattr(dataset, "collate_fn", None), worker_init_fn=seed_worker,
                generator=generator, drop_last=False,
            )  # fmt: skip
            loader.position = lambda: self._poring_pos
            return loader

        def _poring_buffer(self, buf: list[int] | None) -> None:
            """The main process's dataset = what a NEW worker inherits: ``buf`` prefilled (a
            resume), or empty (what every worker of an uninterrupted run starts with)."""
            ds = self.train_loader.dataset
            ds.buffer = []
            ds.ims, ds.im_hw0, ds.im_hw = [None] * ds.ni, [None] * ds.ni, [None] * ds.ni
            for j in buf or []:
                ds.load_image(int(j))
            if list(ds.buffer) != list(buf or []):
                raise RuntimeError(f"mosaic buffer prefill: {ds.buffer} != {buf}")

        # --- the checkpoint -----------------------------------------------------------------
        def _poring_state(self) -> dict[str, Any]:
            crit = getattr(unwrap_model(self.model), "criterion", None)
            return {
                "model": to_cpu(unwrap_model(self.model).state_dict()),
                "ema": to_cpu(self.ema.ema.state_dict()),
                "ema_updates": int(self.ema.updates),
                "optimizer": to_cpu(self.optimizer.state_dict()),
                "scaler": deepcopy(self.scaler.state_dict()),
                "criterion_updates": getattr(crit, "updates", None),
                # gradients still accumulating: zeroed only after a step, so an epoch's last
                # batches carry theirs into the next epoch (the boundary checkpoint needs them)
                "grads": [
                    None if p.grad is None else to_cpu(p.grad)
                    for p in unwrap_model(self.model).parameters()
                ],
            }

        def _poring_save_mid(self, epoch: int, next_i: int, nb: int, last_opt_step: int) -> None:
            t0 = time.monotonic()
            state = self._poring_state()
            sha = digest(state, tensor_bytes)
            ema = deepcopy(self.ema.ema).to(memory_format=torch.contiguous_format)
            if hasattr(ema, "criterion"):
                ema.criterion = None
            mid = {
                "version": MID_VERSION, "epoch": epoch, "next_i": next_i, "nb": nb,
                "n": len(self.train_loader.dataset), "batch": self.batch_size,
                "seed": int(self.args.seed), "workers": self.train_loader.num_workers,
                "close_mosaic": int(self.args.close_mosaic), "last_opt_step": last_opt_step,
                "accumulate": self.accumulate, "loss_names": tuple(self.loss_names),
                "tloss": to_cpu(self.tloss), "best_fitness": self.best_fitness,
                "fitness": self.fitness, "metrics": deepcopy(self.metrics),
                "stopper": {k: getattr(self.stopper, k) for k in ("best_fitness", "best_epoch",
                                                                  "possible_stop")},
                "buf": list(self._poring_buf), "rng": {
                    "python": random.getstate(), "numpy": np.random.get_state(),
                    "torch": torch.get_rng_state(),
                    "cuda": torch.cuda.get_rng_state_all() if torch.cuda.is_available() else []},
                "state_sha256": sha,
                **{k: v for k, v in state.items() if k != "ema"},  # the EMA: the module below
            }  # fmt: skip
            # the stock keys: ultralytics' check_resume/setup_model read train_args and the (here
            # fp32, so exact) EMA module; the optimizer and scaler come back from poring_mid
            ck = {"epoch": epoch - 1, "best_fitness": self.best_fitness, "model": None,
                  "ema": ema, "updates": self.ema.updates, "optimizer": None, "scaler": None,
                  "train_args": vars(self.args), "poring_mid": mid}  # fmt: skip
            path = self.wdir / MID_NAME
            tmp = path.with_suffix(".pt.tmp")
            with open(tmp, "wb") as fh:
                torch.save(ck, fh)
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp, path)
            line = {"mid_ckpt": {"at": [epoch, next_i], "sha256": sha[:16],
                                 "bytes": path.stat().st_size,
                                 "seconds": round(time.monotonic() - t0, 2)}}  # fmt: skip
            print(json.dumps(line), flush=True)
            self._poring_trace({"kind": "mid", "at": [epoch, next_i], "sha256": sha})

        def resume_training(self, ckpt: Any) -> None:
            mid = (ckpt or {}).get("poring_mid") if isinstance(ckpt, dict) else None
            if mid is None or not self.resume:
                return super().resume_training(ckpt)
            run = {"n": len(self.train_loader.dataset), "batch": self.batch_size,
                   "seed": int(self.args.seed), "nb": len(self.train_loader),
                   "workers": self.train_loader.num_workers,
                   "close_mosaic": int(self.args.close_mosaic)}  # fmt: skip
            problems = check_compatible(mid, run)
            if problems:
                raise SystemExit(f"mid.pt is from another stream, refusing to resume: {problems}")
            epoch, next_i = next_position(mid)
            if not 0 <= epoch < self.epochs:
                raise SystemExit(f"{self.args.model}: training to {self.epochs} epochs is finished")
            self._load_checkpoint_state(ckpt)  # the EMA (saved fp32: exact) + its update count
            unwrap_model(self.model).load_state_dict(mid["model"])  # the LIVE weights, not the EMA
            opt = deepcopy(mid["optimizer"])
            for saved, group in zip(opt["param_groups"], self.optimizer.param_groups, strict=True):
                saved["fused"] = group.get("fused")  # as stock: the runtime picks the kernel
            self.optimizer.load_state_dict(opt)
            self.scaler.load_state_dict(mid["scaler"])
            self.ema.updates = mid["ema_updates"]
            params = list(unwrap_model(self.model).parameters())
            if len(params) != len(mid["grads"]):
                raise SystemExit("mid.pt: the model's parameter count changed")
            for p, g in zip(params, mid["grads"], strict=True):
                p.grad = None if g is None else torch.empty_like(p).copy_(g)
            crit = getattr(unwrap_model(self.model), "criterion", None)
            if mid.get("criterion_updates") is not None and crit is not None:
                crit.updates = mid["criterion_updates"] - 1
                crit.update()
            self.best_fitness, self.fitness = mid["best_fitness"], mid["fitness"]
            if mid.get("metrics"):
                self.metrics = mid["metrics"]
            for k, v in mid["stopper"].items():
                setattr(self.stopper, k, v)
            self.start_epoch = epoch
            restored = digest(self._poring_state(), tensor_bytes)
            self._poring_resume = {
                "i0": next_i, "last_opt_step": mid["last_opt_step"],
                "accumulate": mid["accumulate"], "loss_names": tuple(mid["loss_names"]),
                "tloss": mid["tloss"], "buf": list(mid["buf"]), "rng": mid["rng"],
            }  # fmt: skip
            ok = restored == mid["state_sha256"]
            LOGGER.info(f"Resuming MID-EPOCH from {self.args.model}: epoch {epoch + 1} batch "
                        f"{next_i}/{mid['nb']}, state {'restored bitwise' if ok else 'MISMATCH'}")  # fmt: skip
            print(json.dumps({"mid_resume": {"at": [epoch, next_i], "bitwise": ok}}), flush=True)
            self._poring_trace({"kind": "resume", "at": [epoch, next_i],
                                "saved_sha256": mid["state_sha256"], "restored_sha256": restored})  # fmt: skip
            if not ok:
                raise SystemExit("mid.pt did not restore bitwise: refusing to train on")

        # --- the proof harness --------------------------------------------------------------
        def _poring_trace(self, rec: dict[str, Any]) -> None:
            if opts.trace is None:
                return
            if getattr(self, "_poring_trace_fh", None) is None:
                opts.trace.parent.mkdir(parents=True, exist_ok=True)
                self._poring_trace_fh = open(opts.trace, "a", buffering=1)  # noqa: SIM115
            self._poring_trace_fh.write(json.dumps(rec) + "\n")

        def _poring_trace_batch(self, epoch: int, i: int, ni: int, meta: dict[str, Any],
                                stepped: bool) -> None:  # fmt: skip
            if opts.trace is None:
                return
            rec: dict[str, Any] = {
                "kind": "batch", "epoch": epoch, "i": i, "ni": ni, "idx": meta["idx"],
                "pos": meta["pos"], "img": meta["img"], "lab": meta["lab"],
                "loss": {k: float(v) for k, v in (self.loss_items or {}).items()},
            }  # fmt: skip
            if stepped:
                rec |= {"lr": [g["lr"] for g in self.optimizer.param_groups],
                        "momentum": [g.get("momentum", g.get("betas", [None])[0])
                                     for g in self.optimizer.param_groups],
                        "accumulate": self.accumulate, "ema_updates": int(self.ema.updates),
                        "scale": float(self.scaler.get_scale())}  # fmt: skip
            self._poring_trace(rec)

        @staticmethod
        def _poring_batch_meta(batch: dict[str, Any]) -> dict[str, Any]:
            """Pops our keys off the collated batch (the loss sees a stock batch) and, for the
            trace, hashes the images and labels exactly as collated."""
            meta = {"idx": list(batch.pop("poring_idx")),
                    "pos": [list(p) for p in batch.pop("poring_pos")],
                    "buf": list(batch.pop("poring_buf")[-1])}  # fmt: skip
            if opts.trace is not None:
                meta["img"] = hashlib.sha256(tensor_bytes(batch["img"])[2]).hexdigest()[:32]
                h = hashlib.sha256()
                for k in ("batch_idx", "cls", "bboxes"):
                    h.update(tensor_bytes(batch[k])[2])
                meta["lab"] = h.hexdigest()[:32]
            return meta

        # --- the loop: ultralytics 8.4.165 BaseTrainer._do_train, changes marked # poring: ---
        # fmt: off
        def _do_train(self) -> None:  # noqa: C901, PLR0912, PLR0915
            """Perform the full training loop including setup, epoch iteration, validation, and final evaluation."""
            if self.world_size > 1:
                self._setup_ddp()
            self._setup_train()

            nb = len(self.train_loader)  # number of batches
            nw = self._get_warmup_iterations(nb)
            last_opt_step = -1
            res = self._poring_resume  # poring: the mid-epoch resume, if any
            i0 = 0
            if res is not None:  # poring: the loop counters exactly where the checkpoint left them
                i0, last_opt_step = int(res["i0"]), int(res["last_opt_step"])
                self.accumulate, self.loss_names = int(res["accumulate"]), res["loss_names"]
                random.setstate(res["rng"]["python"])
                np.random.set_state(res["rng"]["numpy"])
                torch.set_rng_state(res["rng"]["torch"])
                if res["rng"]["cuda"] and torch.cuda.is_available():
                    torch.cuda.set_rng_state_all(res["rng"]["cuda"])
            self._poring_buf = list(res["buf"]) if res is not None else []  # poring
            # poring: the epoch whose first batch an uninterrupted run starts on a fresh worker
            # (close_mosaic's reset): its buffer is empty there, not carried over
            reset_epoch = max(self.epochs - self.args.close_mosaic, 0) if self.args.close_mosaic else -1
            since_n, since_t = 0, time.monotonic()  # poring: batches / seconds since the last mid save
            self.epoch_time = None
            self.epoch_time_start = time.time()
            self.train_time_start = time.time()
            self.run_callbacks("on_train_start")
            LOGGER.info(
                f"Using {len(self.train_loader.dataset)} train, {len(self.test_loader.dataset)} val images for "
                f"fraction={self.args.fraction} at imgsz={self.args.imgsz}\n"
                f"Using {self.train_loader.num_workers * (self.world_size or 1)} dataloader workers\n"
                f"Logging results to {colorstr('bold', self.save_dir)}\n"
                f"Starting training for " + (f"{self.args.time} hours..." if self.args.time else f"{self.epochs} epochs...")
            )
            if self.args.close_mosaic:
                base_idx = (self.epochs - self.args.close_mosaic) * nb
                self.plot_idx.extend([base_idx, base_idx + 1, base_idx + 2])
            epoch = self.start_epoch
            mosaic_closed = not self.args.close_mosaic  # close once when the run enters its final close_mosaic epochs
            if res is None:  # poring: a mid resume restored the pending gradients: keep them
                self.optimizer.zero_grad()  # zero any resumed gradients to ensure stability on train start
            self._oom_retries = 0  # OOM auto-reduce counter for first epoch
            while True:
                self.epoch = epoch
                self.run_callbacks("on_train_epoch_start")
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore")  # suppress 'Detected lr_scheduler.step() before optimizer.step()'
                    self.scheduler.step()

                self._model_train()
                if RANK != -1:
                    self.train_loader.sampler.set_epoch(epoch)
                # Update dataloader attributes (optional)
                if not mosaic_closed and epoch >= self.epochs - self.args.close_mosaic:
                    mosaic_closed = True
                    self._close_dataloader_mosaic()
                    self.train_loader.reset()

                ie = i0 if epoch == self.start_epoch else 0  # poring: the first batch of this epoch
                if self.train_loader.iterator is None:  # poring: a new worker forks from here
                    forks = self.train_loader.num_workers > 0  # workers=0: one dataset, never fresh
                    fresh = forks and epoch == reset_epoch and ie == 0
                    if res is not None and epoch == self.start_epoch and not fresh:
                        self._poring_buffer(res["buf"])  # what the uninterrupted worker held
                    elif forks:
                        self._poring_buffer(None)  # what every fresh worker starts with
                self._poring_pos = (epoch, ie)  # poring: the loader seeks here if it restarts
                pbar = zip(range(ie, nb), self.train_loader, strict=False)  # poring: was enumerate(train_loader)
                if RANK in {-1, 0}:
                    if self.loss_names:
                        LOGGER.info(self.progress_string())
                    pbar = TQDM(pbar, total=nb - ie)  # poring: total nb - ie
                self.tloss = None
                if res is not None and epoch == self.start_epoch and ie > 0:  # poring
                    self.tloss = {k: v.to(self.device) for k, v in res["tloss"].items()} if res["tloss"] else None
                for i, batch in pbar:
                    self.run_callbacks("on_train_batch_start")
                    meta = self._poring_batch_meta(batch)  # poring: stream position, buffer, hashes
                    stepped = False  # poring
                    # Warmup
                    ni = i + nb * epoch
                    if ni < nw:
                        xi = [0, nw]  # x interp
                        self.accumulate = max(1, int(np.interp(ni, xi, [1, self.args.nbs / self.batch_size]).round()))
                        for x in self.optimizer.param_groups:
                            # Bias lr falls from 0.1 to lr0, all other lrs rise from 0.0 to lr0
                            x["lr"] = float(
                                np.interp(
                                    ni,
                                    xi,
                                    [
                                        self.args.warmup_bias_lr if x.get("param_group") == "bias" else 0.0,
                                        x["initial_lr"] * self.lf(epoch),
                                    ],
                                )
                            )
                            if "momentum" in x:
                                x["momentum"] = float(np.interp(ni, xi, [self.args.warmup_momentum, self.args.momentum]))

                    # Forward
                    try:
                        with autocast(torch.bfloat16 if self.args.amp == "bf16" else self.amp, device=self.device.type):
                            batch = self.preprocess_batch(batch)
                            if self.args.compile:
                                # Decouple inference and loss calculations for improved compile performance
                                preds = self.model(batch["img"])
                                loss, self.loss_items = unwrap_model(self.model).loss(batch, preds)
                            else:
                                loss, self.loss_items = self.model(batch)
                            self.loss = loss.sum()
                            if RANK != -1:
                                self.loss *= self.world_size
                            if not self.loss_names:  # derive loss names from the criterion's loss dict on first batch
                                self.loss_names = tuple(self.loss_items)
                                if RANK in {-1, 0}:
                                    LOGGER.info(self.progress_string())
                                    self.metrics.update(dict.fromkeys(self.label_loss_items(prefix="val"), 0.0))
                            self.tloss = (
                                self.loss_items
                                if self.tloss is None
                                else {k: (self.tloss[k] * i + v) / (i + 1) for k, v in self.loss_items.items()}
                            )

                        # Backward
                        self.scaler.scale(self.loss).backward()
                    except RuntimeError as e:
                        is_oom = "out of memory" in str(e).lower()  # torch.cuda.OutOfMemoryError requires torch>=1.13
                        if not is_oom and not any(
                            s in str(e)
                            for s in (
                                "CUBLAS_STATUS_ALLOC_FAILED",
                                "CUDNN_STATUS_INTERNAL_ERROR",
                                "unable to find an engine",
                            )
                        ):
                            raise
                        if epoch > self.start_epoch or self._oom_retries >= 3 or RANK != -1:
                            raise  # only auto-reduce during first epoch on single GPU, max 3 retries
                        self._oom_retries += 1
                        old_batch = self.batch_size
                        self.args.batch = self.batch_size = max(self.batch_size // 2, 1)
                        error = f"{self.device.type.upper()} out of memory" if is_oom else "CUDA backend memory error"
                        LOGGER.warning(
                            f"{error} with batch={old_batch}. "
                            f"Reducing to batch={self.batch_size} and retrying ({self._oom_retries}/3)."
                        )
                        batch = loss = preds = None
                        self.loss = self.loss_items = self.tloss = None
                        if hasattr(self.train_loader, "close"):
                            self.train_loader.close()  # free the replaced loader's workers and prefetched batches
                        self._clear_memory()
                        self._build_train_pipeline()  # retain optimizer state across OOM retries
                        mosaic_closed = not self.args.close_mosaic  # the rebuilt loader reopened mosaic, re-arm the gate
                        self.validator.dataloader = self.test_loader  # the validator holds the pre-halving loader
                        self.scheduler.last_epoch = self.start_epoch - 1
                        nb = len(self.train_loader)
                        nw = self._get_warmup_iterations(nb)
                        last_opt_step = -1
                        self.optimizer.zero_grad()
                        i0, res = 0, None  # poring: a new batch size restarts the epoch: no longer exact
                        LOGGER.warning("mid-epoch checkpoints: the batch size changed; this run is no longer exact")  # poring
                        break  # restart epoch loop with reduced batch size
                    if ni - last_opt_step >= self.accumulate:
                        self.optimizer_step()
                        last_opt_step = ni
                        stepped = True  # poring

                        # Timed stopping
                        if self.args.time:
                            self.stop = (time.time() - self.train_time_start) > (self.args.time * 3600)
                            if RANK != -1:  # if DDP training
                                broadcast_list = [self.stop if RANK == 0 else None]
                                dist.broadcast_object_list(broadcast_list, 0)  # broadcast 'stop' to all ranks
                                self.stop = broadcast_list[0]
                            if self.stop:  # training time exceeded
                                break

                    # Log
                    if RANK in {-1, 0}:
                        loss_length = len(self.tloss)
                        pbar.set_description(
                            ("%11s" * 2 + "%11.4g" * (2 + loss_length))
                            % (
                                f"{epoch + 1}/{self.epochs}",
                                f"{self._get_memory():.3g}G",  # (GB) GPU memory util
                                *self.tloss.values(),  # losses
                                batch.get("cls", batch["img"]).shape[0],  # no. of instances
                                batch["img"].shape[-1],  # imgsz, i.e 640
                            )
                        )
                        if self.args.plots and ni in self.plot_idx:
                            self.plot_training_samples(batch, ni)

                    self.run_callbacks("on_train_batch_end")
                    # poring: the trace, the mid checkpoint (after a step, never on the epoch's
                    # last batch: the boundary checkpoint follows), and the proof's kill
                    self._poring_buf = meta["buf"]
                    self._poring_trace_batch(epoch, i, ni, meta, stepped)
                    since_n += 1
                    if i < nb - 1 and mid_due(stepped, since_n, time.monotonic() - since_t,
                                              opts.every_batches, opts.every_s):  # fmt: skip
                        self._poring_save_mid(epoch, i + 1, nb, last_opt_step)
                        since_n, since_t = 0, time.monotonic()
                    if opts.die_at is not None and ni >= opts.die_at:
                        LOGGER.warning(f"--die-after-batches {opts.die_at}: killing the process now")
                        os._exit(DIE_RC)
                    if self.stop:
                        break  # allow external stop (e.g. platform cancellation) between batches
                else:
                    # for/else: this block runs only when the for loop completes without break (no OOM retry)
                    self._oom_retries = 0  # reset OOM counter after successful first epoch

                if self._oom_retries and not self.stop:
                    continue  # OOM recovery broke the for loop, restart with reduced batch size

                if hasattr(unwrap_model(self.model).criterion, "update"):
                    unwrap_model(self.model).criterion.update()

                self.lr = {f"lr/pg{ir}": x["lr"] for ir, x in enumerate(self.optimizer.param_groups)}  # for loggers

                self.run_callbacks("on_train_epoch_end")
                if RANK in {-1, 0}:
                    self.ema.update_attr(self.model, include=["yaml", "nc", "args", "names", "stride", "class_weights"])

                # Validation
                final_epoch = epoch + 1 >= self.epochs
                if self.args.val or final_epoch or self.stopper.possible_stop or self.stop:
                    self._clear_memory(None if self.device.type == "mps" else 0.5)  # prevent VRAM spike
                    self.metrics, self.fitness = self.validate()

                # NaN recovery
                if self._handle_nan_recovery(epoch):
                    continue

                self.nan_recovery_attempts = 0
                if RANK in {-1, 0}:
                    self.save_metrics(metrics={**self.label_loss_items(self.tloss), **self.metrics, **self.lr})
                    self.stop |= self.stopper(epoch + 1, self.fitness) or final_epoch
                    if self.args.time:
                        self.stop |= (time.time() - self.train_time_start) > (self.args.time * 3600)

                    # Save model
                    if (self.args.save or final_epoch) and self.save_model():
                        self.run_callbacks("on_model_save")
                    # poring: the BOUNDARY checkpoint (resume at the next epoch's batch 0, exact);
                    # a finished run leaves none behind
                    if not self.stop:
                        self._poring_save_mid(epoch + 1, 0, nb, last_opt_step)
                        since_n, since_t = 0, time.monotonic()
                    else:
                        (self.wdir / MID_NAME).unlink(missing_ok=True)

                # Scheduler
                t = time.time()
                self.epoch_time = t - self.epoch_time_start
                self.epoch_time_start = t
                if self.args.time:
                    mean_epoch_time = (t - self.train_time_start) / (epoch - self.start_epoch + 1)
                    self.epochs = self.args.epochs = math.ceil(self.args.time * 3600 / mean_epoch_time)
                    nw = self._get_warmup_iterations(nb)
                    self._setup_scheduler()
                    self.scheduler.last_epoch = self.epoch  # do not move
                    self.stop |= epoch >= self.epochs  # stop if exceeded epochs
                self.run_callbacks("on_fit_epoch_end")
                # clear if memory utilization > 50%; always clear on MPS due to leak https://github.com/ultralytics/ultralytics/issues/22621
                self._clear_memory(None if self.device.type == "mps" else 0.5)

                # Early Stopping
                if RANK != -1:  # if DDP training
                    broadcast_list = [self.stop if RANK == 0 else None]
                    dist.broadcast_object_list(broadcast_list, 0)  # broadcast 'stop' to all ranks
                    self.stop = broadcast_list[0]
                if self.stop:
                    break  # must break all DDP ranks
                epoch += 1

            seconds = time.time() - self.train_time_start
            LOGGER.info(f"\n{epoch - self.start_epoch + 1} epochs completed in {seconds / 3600:.3f} hours.")
            # Do final val with best.pt
            self.final_eval()
            if RANK in {-1, 0}:
                if self.args.plots:
                    self.plot_metrics()
                self.run_callbacks("on_train_end")
            self._clear_memory()
            for loader in (self.train_loader, self.test_loader):
                if hasattr(loader, "close"):
                    loader.close()  # shut down persistent dataloader workers so none survive to interpreter exit
        # fmt: on

    return Resumable
