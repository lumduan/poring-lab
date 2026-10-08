"""Mid-epoch checkpoints, the torch-free half (Batt, 2026-10-08): host-testable without torch.

v1 trains for ~15-16 h through the daytime Frigate peaks, and every R3/IO abort used to throw away
the epoch in progress (~30 min). An exact resume needs three things ultralytics does not keep:
1. **The data stream's position.** Stock training draws the order from a DataLoader generator that a
   resume re-creates, so a resumed epoch replays epoch 0's order. Here pass ``e`` is a pure function
   of (seed, e) (`StreamSampler`), and the first pass after a resume starts at batch ``i0``.
2. **The augmentation randomness.** Stock augmentation draws from the worker's RNG, seeded once per
   worker. Here every sample re-seeds from (seed, epoch, position) (`sample_seeds`), so a sample's
   augmentation does not depend on the worker's history.
3. **The mosaic buffer.** Mosaic picks its partners among the worker's recently loaded images (the
   dataset's ``buffer``). The trainer records the buffer after each batch and prefills it on resume
   (`midckpt`).
The torch half is `poring_vision.midckpt`. The proof (`--trace`, then the host's
`scripts/resume_proof.py compare`) checks an uninterrupted run against a killed-and-resumed one,
batch by batch (docs/operations/mid-epoch-checkpoints.md).
"""

from __future__ import annotations

import hashlib
import math
from collections.abc import Callable, Iterator
from typing import Any

import numpy as np
import numpy.typing as npt

PERM_TAG = 0x5045524D  # "PERM": the pass order stream
SAMPLE_TAG = 0x53414D50  # "SAMP": the per-sample augmentation stream
MID_VERSION = 1

Position = tuple[int, int]  # (epoch, batch index within it) of the NEXT batch to train


class StreamSampler:
    """The training order, resumable at any batch: pass ``e`` is a permutation drawn from
    (seed, e) alone, and each item is ``(index, epoch, pos)`` so the dataset can key its
    augmentation to the stream position.

    A DataLoader iterates a sampler once per pass (ultralytics' _RepeatSampler re-iterates it
    forever, prefetching across epoch ends). The pass an ``__iter__`` call yields is the one
    `seek` set, and each call moves the next pass on by one. The trainer seeks ONLY when a new
    loader iterator is created (the first epoch, and close_mosaic's reset), to its own (epoch,
    batch), so prefetch and resets cannot shift the epoch-to-pass mapping."""

    def __init__(self, n: int, seed: int, batch_size: int) -> None:
        if n <= 0 or batch_size <= 0:
            raise ValueError(f"empty stream: n={n} batch={batch_size}")
        self.n, self.seed, self.batch_size = int(n), int(seed), int(batch_size)
        self._next: tuple[int, int] = (0, 0)  # (epoch, sample position) of the next pass

    def perm(self, epoch: int) -> npt.NDArray[np.int64]:
        ss = np.random.SeedSequence([PERM_TAG, self.seed & 0xFFFFFFFF, self.seed >> 32, epoch])
        return np.random.Generator(np.random.PCG64(ss)).permutation(self.n)

    def seek(self, epoch: int, batch_i: int) -> None:
        """The next pass is ``epoch``, starting at its batch ``batch_i``."""
        pos = int(batch_i) * self.batch_size
        if epoch < 0 or not 0 <= pos <= self.n:
            raise ValueError(f"seek out of range: epoch {epoch} batch {batch_i} (n {self.n})")
        self._next = (int(epoch), pos)

    @property
    def next_pass(self) -> tuple[int, int]:
        return self._next

    def __iter__(self) -> Iterator[tuple[int, int, int]]:
        epoch, start = self._next
        self._next = (epoch + 1, 0)
        perm = self.perm(epoch)
        for pos in range(start, self.n):
            yield int(perm[pos]), epoch, pos

    def __len__(self) -> int:
        return self.n  # a FULL pass: the loader's batches per epoch (nb) must not change on resume

    def batches_per_epoch(self) -> int:
        return math.ceil(self.n / self.batch_size)


def sample_seeds(seed: int, epoch: int, pos: int) -> tuple[int, int, int]:
    """(python random, numpy legacy, torch) seeds for the sample at (epoch, pos) of the run."""
    ss = np.random.SeedSequence([SAMPLE_TAG, seed & 0xFFFFFFFF, seed >> 32, epoch, pos])
    a, b, c = (int(x) for x in ss.generate_state(3, dtype=np.uint64))
    return a, b % (1 << 32), c & 0x7FFF_FFFF_FFFF_FFFF


class KeyedRandomness:
    """Seeds python's ``random``, numpy's legacy global RNG (and torch's, when given) for one
    sample, and restores the previous states afterwards: a sample's augmentation depends on its
    stream position only, and the process's own RNG streams are left as they were (workers=0
    runs the dataset in the trainer's process)."""

    def __init__(self, seeds: tuple[int, int, int], torch_mod: Any = None) -> None:
        self.seeds, self.torch = seeds, torch_mod
        self._saved: tuple[Any, Any, Any] | None = None

    def __enter__(self) -> KeyedRandomness:
        import random

        t = self.torch
        self._saved = (random.getstate(), np.random.get_state(),
                       t.get_rng_state() if t is not None else None)  # fmt: skip
        random.seed(self.seeds[0])
        np.random.seed(self.seeds[1])
        if t is not None:
            t.manual_seed(self.seeds[2])
        return self

    def __exit__(self, *exc: object) -> None:
        import random

        assert self._saved is not None
        random.setstate(self._saved[0])
        np.random.set_state(self._saved[1])
        if self.torch is not None:
            self.torch.set_rng_state(self._saved[2])


def next_position(meta: dict[str, Any]) -> Position:
    """Where a mid checkpoint resumes: (epoch, the first batch not yet trained)."""
    return int(meta["epoch"]), int(meta["next_i"])


def pick_resume(mid_meta: dict[str, Any] | None, last_epoch: int | None, epochs: int) -> str:
    """Which checkpoint ``--resume`` uses: "mid" (exact), "last" (ultralytics' own epoch-level
    resume, NOT exact) or "none".
    - last.pt's ``epoch`` is the last COMPLETED epoch, so it resumes at (last_epoch + 1, 0).
    - mid.pt wins when it is at or past that position (equal = the same point, and mid is exact);
      a stale mid.pt (behind last.pt) never rewinds the run.
    - A mid.pt at or past the final epoch means the run is complete: "none"."""
    last_pos = None if last_epoch is None else (int(last_epoch) + 1, 0)
    if mid_meta is not None:
        pos = next_position(mid_meta)
        if pos[0] >= epochs:
            return "none"
        if last_pos is None or pos >= last_pos:
            return "mid"
    if last_pos is None:
        return "none"
    return "last" if last_pos[0] < epochs else "none"


COMPAT_KEYS = ("n", "batch", "seed", "nb", "workers", "close_mosaic")


def check_compatible(meta: dict[str, Any], run: dict[str, Any]) -> list[str]:
    """Why a mid checkpoint cannot continue THIS run (empty = it can): the stream must be the one
    it was cut from (frames, batch, seed, batches per epoch), with the same worker count (each
    worker holds its own mosaic buffer) and the same close_mosaic epoch."""
    return [f"{k}: checkpoint {meta.get(k)} != run {run.get(k)}" for k in COMPAT_KEYS
            if meta.get(k) != run.get(k)]  # fmt: skip


def mid_due(stepped: bool, batches_since: int, seconds_since: float, every_batches: int,
            every_s: float) -> bool:  # fmt: skip
    """Save now? Only right after an optimizer step (no gradients pending), once either the batch
    or the time interval has passed (a slow duty level makes batches slow, not the abort rarer)."""
    if not stepped:
        return False
    return (every_batches > 0 and batches_since >= every_batches) or (
        every_s > 0 and seconds_since >= every_s
    )


# --- the state digest (the round-trip proof) ----------------------------------------------------
TensorBytes = Callable[[Any], tuple[str, tuple[int, ...], bytes]]


def digest(obj: Any, tensor_bytes: TensorBytes | None = None, h: Any = None) -> str:
    """sha256 over a nested state (dicts by sorted key, lists/tuples in order, arrays and tensors
    by dtype + shape + bytes, scalars by repr). ``tensor_bytes`` turns a torch tensor into
    (dtype, shape, bytes); the torch half passes it, so this module stays torch-free."""
    top = h is None
    h = hashlib.sha256() if h is None else h
    if isinstance(obj, dict):
        h.update(b"{")
        for k in sorted(obj, key=repr):
            h.update(repr(k).encode())
            digest(obj[k], tensor_bytes, h)
        h.update(b"}")
    elif isinstance(obj, (list, tuple)):
        h.update(b"[")
        for v in obj:
            digest(v, tensor_bytes, h)
        h.update(b"]")
    elif isinstance(obj, np.ndarray):
        a = np.ascontiguousarray(obj)
        h.update(f"nd{a.dtype.str}{a.shape}".encode())
        h.update(a.tobytes())
    elif tensor_bytes is not None and hasattr(obj, "detach"):
        dt, shape, data = tensor_bytes(obj)
        h.update(f"t{dt}{shape}".encode())
        h.update(data)
    else:
        h.update(repr(obj).encode())
    return h.hexdigest() if top else ""
