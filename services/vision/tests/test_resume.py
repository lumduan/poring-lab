"""Mid-epoch checkpoints (Batt, 2026-10-08): the torch-free half, host-testable. The stream must
resume at any batch with the same order and augmentation, whatever the loader's prefetch and
resets; the checkpoint choice must never rewind a run; the proof's comparator must catch each
failure mode."""

from __future__ import annotations

import argparse
import random
import sys
from collections import deque
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from poring_vision.resume import (
    KeyedRandomness,
    StreamSampler,
    check_compatible,
    digest,
    mid_due,
    pick_resume,
    sample_seeds,
)

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "scripts"))
from resume_proof import compare  # noqa: E402  (the host's Apache-2.0 proof script)


# --- a model of the DataLoader around the sampler (torch's BatchSampler + ultralytics'
# _RepeatSampler / InfiniteDataLoader + our StreamLoader), with the prefetch queue -----------------
def batch_sampler(sampler: Any, b: int) -> Iterator[list[Any]]:
    batch: list[Any] = []
    for x in sampler:
        batch.append(x)
        if len(batch) == b:
            yield batch
            batch = []
    if batch:
        yield batch


class Loader:
    """A persistent iterator that prefetches ``prefetch`` batches ahead (across epoch ends) and
    seeks the sampler to ``position()`` whenever it starts a new iterator."""

    def __init__(self, sampler: StreamSampler, prefetch: int, position: Any) -> None:
        self.sampler, self.prefetch, self.position = sampler, prefetch, position
        self.gen: Iterator[list[Any]] | None = None
        self.queue: deque[list[Any]] = deque()

    def _repeat(self) -> Iterator[list[Any]]:
        while True:
            yield from batch_sampler(self.sampler, self.sampler.batch_size)

    def take(self, k: int) -> list[list[Any]]:
        if self.gen is None:
            self.sampler.seek(*self.position())
            self.gen = self._repeat()
            self.queue = deque(next(self.gen) for _ in range(self.prefetch))
        out = []
        for _ in range(k):
            out.append(self.queue.popleft())
            self.queue.append(next(self.gen))
        return out

    def reset(self) -> None:  # close_mosaic: workers and prefetched batches are discarded
        self.gen = None


def run_stream(n: int, b: int, epochs: int, prefetch: int, start: tuple[int, int] = (0, 0),
               reset_at: int | None = None) -> dict[tuple[int, int], list[Any]]:  # fmt: skip
    """{(epoch, i): batch} as a trainer consumes it (zip(range(i0, nb), loader) per epoch)."""
    s = StreamSampler(n, seed=20261004, batch_size=b)
    nb = s.batches_per_epoch()
    pos = {"p": start}
    loader = Loader(s, prefetch, lambda: pos["p"])
    out: dict[tuple[int, int], list[Any]] = {}
    for epoch in range(start[0], epochs):
        if reset_at is not None and epoch == reset_at:
            loader.reset()
        ie = start[1] if epoch == start[0] else 0
        pos["p"] = (epoch, ie)
        for i, batch in zip(range(ie, nb), loader.take(nb - ie), strict=True):
            out[(epoch, i)] = batch
    return out


def test_a_pass_is_a_function_of_seed_and_epoch_only() -> None:
    a, b = StreamSampler(101, 7, 2), StreamSampler(101, 7, 2)
    assert np.array_equal(a.perm(3), b.perm(3))
    assert sorted(a.perm(3).tolist()) == list(range(101))
    assert not np.array_equal(a.perm(3), a.perm(4))
    assert not np.array_equal(a.perm(3), StreamSampler(101, 8, 2).perm(3))


def test_seek_starts_mid_pass_and_the_next_pass_starts_at_zero() -> None:
    s = StreamSampler(11, 1, 2)
    s.seek(5, 3)  # batch 3 = position 6
    first = list(s)
    assert [p for _, e, p in first] == list(range(6, 11)) and {e for _, e, _ in first} == {5}
    assert [i for i, _, _ in first] == s.perm(5)[6:].tolist()
    second = list(s)
    assert [(e, p) for _, e, p in second] == [(6, p) for p in range(11)]
    assert len(s) == 11  # a full pass, always: nb must not change on resume
    with pytest.raises(ValueError):
        s.seek(0, 6)  # past the end


@pytest.mark.parametrize("prefetch", [1, 4, 7])
def test_prefetch_and_a_reset_never_shift_the_epoch_to_pass_mapping(prefetch: int) -> None:
    """The proof the design rests on: the uninterrupted stream with prefetch running ahead into
    the next epoch, the same with close_mosaic's reset at epoch 3, and runs resumed at several
    batches (inside a pass, at a boundary, after the reset) see the same batches."""
    ref = run_stream(n=23, b=2, epochs=5, prefetch=prefetch)
    assert run_stream(n=23, b=2, epochs=5, prefetch=prefetch, reset_at=3) == ref
    for start in [(1, 5), (2, 0), (3, 0), (3, 11), (4, 7)]:
        got = run_stream(n=23, b=2, epochs=5, prefetch=prefetch, start=start, reset_at=3)
        assert got == {k: v for k, v in ref.items() if k >= start}, start


def test_a_counter_without_the_seek_would_shift_the_stream() -> None:
    """Why the loader seeks: after a reset, a pass counter alone would hand epoch 3 the pass the
    discarded prefetch had already opened (epoch 4's)."""
    s = StreamSampler(10, 1, 2)
    gen = batch_sampler(s, 2)
    next(gen)  # epoch 0 opened
    list(gen)
    gen = batch_sampler(s, 2)
    next(gen)  # the prefetch opens epoch 1 ... then a reset discards it
    assert s.next_pass == (2, 0)  # without a seek the new iterator would yield epoch 2


def test_augmentation_seeds_are_keyed_to_the_position_and_leave_the_process_rng_alone() -> None:
    assert sample_seeds(1, 2, 3) == sample_seeds(1, 2, 3)
    assert len({sample_seeds(1, e, p) for e in range(3) for p in range(50)}) == 150
    random.seed(99)
    np.random.seed(99)
    before = (random.random(), np.random.rand())
    random.seed(99)
    np.random.seed(99)
    with KeyedRandomness(sample_seeds(1, 2, 3)):
        draw1 = (random.random(), np.random.rand())
    after = (random.random(), np.random.rand())
    assert after == before  # the process streams continue as if nothing happened
    random.seed(12345)  # whatever state the worker is in ...
    with KeyedRandomness(sample_seeds(1, 2, 3)):
        draw2 = (random.random(), np.random.rand())
    assert draw1 == draw2  # ... the sample's draws are the same


def test_the_dataset_mixin_keys_items_and_reports_the_buffer() -> None:
    from poring_vision.midckpt import StreamItems

    class Base:
        def __init__(self) -> None:
            self.buffer: list[int] = []

        def __getitem__(self, index: int) -> dict[str, Any]:
            self.buffer.append(index)
            return {"r": random.random(), "n": float(np.random.rand())}

    class DS(StreamItems, Base):
        poring_seed = 5

    a, b = DS(), DS()
    b.buffer = [9, 9]  # a different history: the draws must not care
    x, y = a[(4, 1, 7)], b[(4, 1, 7)]
    assert (x["r"], x["n"]) == (y["r"], y["n"])
    assert x["poring_idx"] == 4 and x["poring_pos"] == (1, 7) and x["poring_buf"] == (4,)
    assert "poring_pos" not in a[3]  # the validator's int items: the stock path


def test_resume_picks_mid_unless_it_is_behind_and_never_rewinds() -> None:
    mid = {"epoch": 5, "next_i": 100}
    assert pick_resume(None, None, 30) == "none"
    assert pick_resume(None, 4, 30) == "last"
    assert pick_resume(mid, 4, 30) == "mid"  # (5, 100) after last's (5, 0)
    assert pick_resume({"epoch": 5, "next_i": 0}, 4, 30) == "mid"  # the boundary: same point, exact
    assert pick_resume(mid, 7, 30) == "last"  # a stale mid.pt never rewinds the run
    assert pick_resume(mid, None, 30) == "mid"  # an abort in the first epoch
    assert pick_resume({"epoch": 30, "next_i": 0}, 29, 30) == "none"
    assert pick_resume(None, 29, 30) == "none"


def test_a_checkpoint_from_another_stream_is_refused() -> None:
    run = {"n": 8193, "batch": 2, "seed": 1, "nb": 4097, "workers": 1, "close_mosaic": 10}
    assert check_compatible(dict(run), run) == []
    bad = check_compatible({**run, "batch": 1, "workers": 2}, run)
    assert len(bad) == 2 and any(m.startswith("batch") for m in bad)


def test_a_mid_save_only_right_after_a_step() -> None:
    assert not mid_due(False, 10_000, 10_000, 640, 300)
    assert mid_due(True, 640, 0, 640, 300)
    assert mid_due(True, 1, 300, 640, 300)
    assert not mid_due(True, 639, 299, 640, 300)
    assert not mid_due(True, 10_000, 10_000, 0, 0)


def test_the_digest_is_canonical_and_sensitive() -> None:
    s = {"b": np.arange(4, dtype=np.float32), "a": [1, (2.5, None)]}
    assert digest(s) == digest({"a": [1, (2.5, None)], "b": np.arange(4, dtype=np.float32)})
    assert digest(s) != digest({**s, "b": np.arange(4, dtype=np.float64)})
    t = {**s, "b": s["b"].copy()}
    t["b"][3] = np.nextafter(t["b"][3], np.float32(10))  # one ulp
    assert digest(s) != digest(t)


# --- the proof's comparator ---------------------------------------------------------------------
def trace(loss_shift: float = 0.0, start: int = 0, img: str = "h", lr: float = 0.01,
          resume: tuple[str, str] | None = None) -> list[dict[str, Any]]:  # fmt: skip
    recs: list[dict[str, Any]] = []
    if resume is not None:
        recs.append({"kind": "resume", "at": [0, start], "saved_sha256": resume[0],
                     "restored_sha256": resume[1]})  # fmt: skip
    for i in range(start, 20):
        r: dict[str, Any] = {"kind": "batch", "epoch": 0, "i": i, "idx": [i], "pos": [[0, i]],
                             "img": img, "lab": "l",
                             "loss": {"box": 1.0 + i / 100 + loss_shift}}  # fmt: skip
        if i % 4 == 3:
            r |= {"lr": [lr], "momentum": [0.9], "accumulate": 4, "ema_updates": i // 4}
        recs.append(r)
    return recs


def resumed(at: int = 6, **kw: Any) -> list[dict[str, Any]]:
    """B: the first run killed after batch 9, then a resume at ``at`` (its records may differ)."""
    return trace()[:10] + trace(start=at, resume=kw.pop("resume", ("x", "x")), **kw)


def fails(b: list[dict[str, Any]]) -> list[str]:
    return list(compare(trace(), trace(), b)["fail"])


def test_compare_passes_an_exact_resume_and_names_each_failure() -> None:
    ok = compare(trace(), trace(), resumed())
    assert ok["pass"] and ok["a_equals_a2"] and ok["resumed_at"] == [[0, 6]]
    assert any(f.startswith("(d) B never") for f in fails(trace()[:10]))
    assert any(f.startswith("(a) 2 batches") for f in fails(resumed(at=12)))  # 10-11 never trained
    assert any(f.startswith("(a) data") for f in fails(resumed(img="H")))
    assert any(f.startswith("(b)") for f in fails(resumed(lr=0.02)))
    assert any(f.startswith("(d) resume at") for f in fails(resumed(resume=("x", "y"))))
    assert any(f.startswith("(c) A == A2") for f in fails(resumed(loss_shift=1e-7)))


def test_compare_holds_b_to_the_gpu_noise_floor_when_a_and_a2_differ() -> None:
    a = trace()
    a2 = trace(loss_shift=1e-4)
    within = trace()[:6] + trace(start=6, loss_shift=1.2e-4, resume=("x", "x"))
    beyond = trace()[:6] + trace(start=6, loss_shift=5e-4, resume=("x", "x"))
    assert compare(a, a2, within)["pass"]
    res = compare(a, a2, beyond)
    assert not res["pass"] and any(f.startswith("(c) box") for f in res["fail"])


# --- the proof plan and the trainer's resume choice ---------------------------------------------
def save_positions(nb: int, epochs: int, nw: int, top: int, every: int) -> list[tuple[int, int]]:
    """Where `--mid-every-batches every --mid-every-s 0` saves (midckpt's rule + the warmup's
    accumulate ramp of ultralytics 8.4.165), as (epoch, next batch)."""
    last, acc, since, out = -1, top, 0, []
    for ni in range(nb * epochs):
        e, i = divmod(ni, nb)
        if ni < nw:
            acc = max(1, int(np.interp(ni, [0, nw], [1, top]).round()))
        stepped = ni - last >= acc
        last = ni if stepped else last
        since += 1
        if i < nb - 1 and mid_due(stepped, since, 0.0, every, 0):
            out.append((e, i + 1))
            since = 0
        if i == nb - 1 and e < epochs - 1:
            out.append((e + 1, 0))
            since = 0
    return out


def test_the_proof_kills_land_between_saves_and_cover_the_boundary() -> None:
    import resume_proof as rp

    saves = save_positions(nb=500, epochs=3, nw=1000, top=32, every=64)
    k1, k2 = rp.KILLS
    e1, i1 = divmod(k1, 500)
    back1 = [s for s in saves if s <= (e1, i1 + 1)][-1]
    assert e1 == 1 and back1[0] == 1 and back1[1] < i1  # mid-epoch, in warmup, batches re-trained
    e2, i2 = divmod(k2, 500)
    back2 = [s for s in saves if s <= (e2, i2 + 1)][-1]
    assert (e2, back2) == (2, (2, 0))  # after close_mosaic's reset: from the boundary checkpoint
    cmds = [c for _, c, _ in rp.plan("v0png-20261006")]
    assert all(
        "rundev:vision@" in c and "--mid-ckpt" in c and "--close-mosaic 1" in c for c in cmds
    )
    assert sum("--resume" in c for c in cmds) == 2


def test_the_trainer_refuses_a_mixed_resume_and_prefers_mid(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    import poring_vision.midckpt as mc
    from poring_vision.train import resume_checkpoint

    run = tmp_path / "run"
    (run / "weights").mkdir(parents=True)
    a = argparse.Namespace(mid_ckpt=False)
    assert resume_checkpoint(a, run, 30) == run / "weights" / "last.pt"  # stock, unchanged
    a.mid_ckpt = True
    with pytest.raises(SystemExit, match="WITHOUT --mid-ckpt"):
        resume_checkpoint(a, run, 30)
    (run / "stream.json").write_text("{}")
    monkeypatch.setattr(mc, "read_mid_meta", lambda p: {"epoch": 3, "next_i": 9, "nb": 50})
    monkeypatch.setattr(mc, "read_last_epoch", lambda p: 2)
    assert resume_checkpoint(a, run, 30) == run / "weights" / "mid.pt"
    monkeypatch.setattr(mc, "read_last_epoch", lambda p: 3)  # last.pt ahead: never rewind
    assert resume_checkpoint(a, run, 30) == run / "weights" / "last.pt"
    a.mid_ckpt = False
    with pytest.raises(SystemExit, match="WITH --mid-ckpt"):
        resume_checkpoint(a, run, 30)


def test_train_day_passes_mid_ckpt_only_when_asked_and_resumes_on_a_mid_alone() -> None:
    sh = (REPO / "scripts" / "runbooks" / "train-day.sh").read_text()
    assert 'mid=""; [ "${MID_CKPT:-0}" = 1 ] && mid=" --mid-ckpt"' in sh
    assert "/lab-duty/duty.json$mid $extra" in sh
    assert '[ -e "data/train/$RUN/weights/mid.pt" ]' in sh
