---
doc_type: design
hypothesis: "A training run killed mid-epoch and resumed from weights/mid.pt trains on the SAME batches, with the SAME augmentation and the SAME schedule as the uninterrupted run, and its losses stay within the GPU's own run-to-run noise."
status: FAILED
role: null
verdict_date: null
verdict_ticket: null
supersedes: null
related: [../benchmarks/v1-vs-v0png.md, r3-paired.md, ../../services/vision/src/poring_vision/midckpt.py]
next_action: "2026-10-08 22:19: the proof FAILED at B2 (rc 1, a fused-Adam state mismatch on the first step after a bitwise restore; RESULT section). v1 trains WITHOUT mid-epoch checkpoints, as pre-registered; TEMP_HOLD stays. Batt: whether to fix (proposed in RESULT) and re-run the proof as a new pre-registration."
---

# Mid-epoch checkpoints with an exact resume (Batt, 2026-10-08; pre-registered BEFORE any run)

**Why (Batt, decision 2 of 2026-10-08 ~10:15):**
- v1 trains for ~15–16 h through the daytime Frigate peaks.
- Every R3-HARD or IO abort used to throw away the epoch in progress. That was twice this
  morning alone, ~20 and ~15 min of epoch 29.
- He asked for checkpoints every N batches, with the optimizer, scheduler and data-loader
  position, resumed exactly ("or the closest safe equivalent"), proven on a short run first.

## What is built (`--mid-ckpt`; `poring_vision/midckpt.py` + `poring_vision/resume.py`)
- **`weights/mid.pt`** is written right after an optimizer step, so no gradients are pending.
  - It is written every **640 batches or 300 s**, whichever comes first.
  - It is also written at every epoch END (the boundary), so an epoch-level resume is exact too.
    That epoch-end checkpoint carries the gradients the epoch's last batches left pending:
    ultralytics zeroes gradients only after a step.
  - **Only the latest and the previous are kept** (Batt, 2026-10-08 ~10:50; `rotate_write`):
    1. the current mid.pt becomes `mid.prev.pt` (os.replace; the older prev is dropped);
    2. the new one is written as `mid.pt.tmp` and fsynced;
    3. it is renamed onto mid.pt, and the directory is fsynced.
    So at most two files exist at any moment, and neither checkpoint name ever holds a
    half-written file. A kill during step 2 leaves mid.prev.pt (then the latest complete one)
    and an orphan .tmp, which the next save overwrites.
  - A finished run leaves neither file behind; a fresh run in the same directory deletes both.
- **It holds:**
  - the LIVE model in fp32, the EMA in fp32 and its update count;
  - the optimizer state at full precision, and the AMP scaler;
  - the loop state: epoch, next batch, last optimizer step, accumulate, the running loss and
    the early stopper;
  - best fitness and metrics;
  - the mosaic buffer, and the RNG states;
  - a sha256 digest of the training state.
- **The data stream:**
  - The training order comes from `StreamSampler`: pass `e` is a pure function of (seed, e),
    instead of ultralytics' generator-shuffled sampler.
  - Every sample's augmentation is seeded from (seed, epoch, position), not from the worker's
    running RNG.
  - The loader seeks to the trainer's own (epoch, batch) whenever it starts a NEW iterator
    (the run's start, close_mosaic's reset), and never otherwise. So the prefetch that runs
    ahead into the next epoch cannot shift the epoch-to-pass mapping.
- **The mosaic buffer:** mosaic picks its partners among the worker's last ≤ 15 loaded images.
  - The trainer records the buffer after every batch.
  - A resume prefills it, before the worker forks, exactly as the uninterrupted worker held it.
  - It is left empty at close_mosaic's reset epoch, where the uninterrupted run starts a fresh
    worker.
- **`--resume`** (`train.py resume_checkpoint`, before the trainer is built):
  - **mid.pt first.** It falls back to **mid.prev.pt** when mid.pt (`inspect_mid`, `choose_mid`):
    - is unreadable (the load fails, or it is not ours);
    - is corrupt: its stored state does not hash to the digest taken when it was saved;
    - contradicts the run while mid.prev.pt agrees with it. The newer file then contradicts
      its own run's history, so it is treated as corrupt.
  - The log line `resume_from` names the file used, and `skipped` says why the other was not.
  - **A genuine setup mismatch refuses with both:** every readable checkpoint disagrees with the
    run on frames, batches per epoch, batch, workers or close_mosaic. With only mid.pt readable
    and disagreeing, it also refuses: the cause cannot be told apart.
  - It refuses a run started in the other mode (`stream.json`).
  - **Never rewind:** whichever mid checkpoint is chosen is used only if it is at or past
    last.pt's position (`pick_resume`); otherwise last.pt (stock, NOT exact, logged).
  - In the trainer: the stream check runs again with the exact worker count, and the RESTORED
    state's digest must equal the saved one. The file already passed its own digest, so a
    mismatch here is a restore fault, not a damaged file: it refuses, with no fallback.
- **Unchanged:** the duty-cycle sleeper, the summary line, validation, and the epoch-level
  last.pt / best.pt.
- **`train-day.sh`:** `MID_CKPT=1` passes `--mid-ckpt`. Any of last.pt, mid.pt or mid.prev.pt
  now triggers `--resume`, so an abort in epoch 1 resumes too.

**Stock ultralytics resume, for contrast (8.4.165, read at the pinned wheel):**
- the model restarts from the EMA weights, not the live ones;
- the optimizer state is rounded to fp16;
- the early stopper restarts;
- the data loader restarts with epoch 0's order and augmentation stream.
So even an epoch-level resume was never exact. Every v0-JPEG resume since 10-07 (train.log lists
them) restarted its stream that way.

## The defaults, from today's numbers
- **The rate:**
  - v0-JPEG has 8,193 train frames, so 4,097 batches per epoch at batch 2.
  - Epochs 24–28 took 1,720–1,928 s each, validation included (results.csv), mostly at duty
    level 0. That is ~2.1–2.4 batches/s, ~2.28 on average.
  - **So 640 batches ≈ 4.7 min at level 0.** At the slowest level (2 s sleep + ~0.4 s compute) it
    would be ~26 min, so the **300 s** trigger governs there.
- **The worst case lost to an abort:** ≤ 300 s + up to 31 batches (to the next optimizer step),
  instead of up to one epoch (~30 min at level 0, ~2.7 h at the slowest level).
- **Disk:**
  - mid.pt ≈ 2–2.5× last.pt: the EMA and the AdamW state in fp32 instead of fp16, plus the live
    weights. last.pt is 21 MB, so an estimated ~45–55 MB; the proof logs the measured `bytes`.
  - **The steady state is TWO such files** (mid.pt + mid.prev.pt, ~100 MB per run directory).
    During a write it is mid.prev.pt + the .tmp: still two, never three.
  - Write volume: one ~50 MB file every ≥ 5 min on `data/train` (the shared disk), ~0.17 MB/s
    on average, against last.pt's 21 MB per ~30 min today. Each write is fsynced; a rotation is
    two renames.

## What is EXACT, and what is not
- **Exact by construction, and checked by the proof:**
  - which frames each batch holds;
  - each frame's augmentation, mosaic partners included;
  - the batch's images and labels as collated (hashed);
  - the learning rate, momentum, accumulate and EMA update count at every optimizer step;
  - the restored state (digest).
- **Not exact: the GPU arithmetic.**
  - `deterministic=True` is on (ultralytics' default), but some CUDA kernels have no
    deterministic version and only warn.
  - Two uninterrupted runs (A, A2) may differ in the last bits. The proof measures that floor
    and holds the resumed run to it.
- **Exactness is claimed for one GPU and workers ≤ 1** (v1 runs workers 1).
  - With more workers, each worker holds its own mosaic buffer, and a new iterator re-deals the
    batches round-robin from worker 0.
  - The batch contents stay exact there; mosaic partners may not. The checkpoint pins the
    worker count.
- **Residuals, each caught by criterion (a) if it ever happens:**
  - an augmentation that modified a buffered image IN PLACE (the prefill reloads it fresh);
  - an OOM batch halving, which ends exactness and is logged;
  - a resume from last.pt because mid.pt is missing or stale: stock, not exact, logged.
- **The v1 stream differs from v0-PNG's and v0-JPEG's.**
  - It cannot match them: theirs came from ultralytics' sampler and restarted at every resume.
  - The frames, labels-per-frame, split, epochs and hyperparameters stay identical, so the
    v1-vs-v0png comparison keeps its controlled variables. The order of batches was never one
    of them.

## The PROOF (pre-registered; run once, scored as written)
**When:** after the v0-JPEG evals and before v1, through guarded `rundev:vision` (IO + R1–R3).
The duty cycle only changes wall time. `scripts/resume_proof.py plan` prints the exact commands.

**The runs:**
- All `--smoke` on `v0png-20261006`: 1,000 train frames = 500 batches/epoch.
- 3 epochs, `--close-mosaic 1`: mosaic in epochs 1–2, the reset at epoch 3's start. Warmup spans
  epochs 1–2.
- Batch 2 / workers 1, as v1.
- A mid save every 64 batches (`--mid-every-s 0`: deterministic positions), and `--trace` on every
  batch.

| run | what | expected |
|---|---|---|
| A | uninterrupted | rc 0 |
| A2 | A again: the GPU's own noise floor | rc 0 |
| B1 | dies after global batch 850 (epoch 2, batch 350; mosaic on, in warmup); its last mid save was at batch 300 | rc 86 |
| B2 | `--resume`: re-trains batches 300–350, dies after batch 1037 (epoch 3, batch 37: after close_mosaic's reset, before epoch 3's first mid save) | rc 86 |
| B3 | `--resume` from the BOUNDARY checkpoint written at the end of epoch 2, to the end | rc 0 |

All of B goes to one trace file.

**The bar** (`scripts/resume_proof.py compare`, rc 0 only on PASS). PASS iff ALL of:
- **(a) data:** every batch of A exists in B with the same sample indices, stream positions,
  image hash and label hash.
- **(b) schedule:** at every optimizer step, the same lr and momentum per parameter group, the
  same accumulate, and the same EMA update count.
- **(c) losses:**
  - **If A and A2 are bitwise equal everywhere:** B's per-batch losses must be bitwise equal to
    A's after the first resume.
  - **Otherwise:** after the first resume, per loss item, the median and p95 of |B − A| must
    stay ≤ 1.5 × those of |A2 − A| (+ 1e-6).
- **(d) restore:** every resume's restored state digest equals the saved one. The trainer
  itself also refuses to continue otherwise.

**The bar is UNCHANGED by the rotation (added 2026-10-08 ~11:00, before any run).**
- B's resumes go through the rotation as written: two files on disk, mid.pt chosen.
  Additionally reported: each resume's `resume_from` line, which must name mid.pt, and the
  weights directory listing after B3, which must be empty of mid files.
- **The FALLBACK to mid.prev.pt is proven on the host, not on the GPU**
  (`services/vision/tests/test_resume.py`):
  - the rotation never shows more than two files, never a half-written mid.pt, and keeps the
    previous one through a kill during the write;
  - a one-ulp change in a stored state fails the file's own digest;
  - `inspect_mid` names missing, unreadable (a load error, or not ours), corrupt and ok;
  - `choose_mid` falls back on each kind of damage, and on a mid.pt that contradicts the run
    while mid.prev.pt agrees;
  - it refuses a genuine setup change with both, and refuses when it cannot tell;
  - `resume_checkpoint` picks mid.prev.pt over a truncated mid.pt, still never rewinds behind
    last.pt, and refuses a different cache.
- **Why not on the GPU:**
  - The fallback only chooses WHICH file to restore. The restore itself is the code criterion
    (d) already proves, on whichever file it is given.
  - The cheap GPU variant would corrupt mid.pt before B3. B3's mid.prev.pt is epoch 2's last
    mid save, which is behind last.pt (end of epoch 2). The never-rewind rule would then
    correctly choose the inexact last.pt, and criterion (a) would fail by design.
  - A GPU check that lands on mid.prev.pt would need its own run, ~15 min.

**Reported whatever the outcome:**
- each criterion;
- whether A == A2 bitwise;
- the loss envelopes;
- the resume points;
- mid.pt's size and write time (`mid_ckpt` log lines);
- the wall time of each run.

**Decision (Batt's):**
- **PASS:** v1 trains with `MID_CKPT=1` (v1-vs-v0png.md records it before v1 starts).
- **FAIL on any criterion:** v1 keeps epoch-level checkpoints (`MID_CKPT` unset, code path
  unchanged), and the failing criterion is reported.

## RESULT (2026-10-08, scored as written): **FAIL** — B2 crashed on its first optimizer step after the resume

**The runs** (`/dev/shm/poring-lab-tmp/gpu-night/chain6.sh`; guarded `rundev:vision`, the adaptive duty
cycle, R3 paired):

| run | expected | got | ICT (UTC) |
|---|---|---|---|
| A | rc 0 | **rc 0** | 21:06–21:35 (14:06–14:35) |
| A2 | rc 0 | **rc 0** | 21:35–22:01 (14:35–15:01) |
| B1 | dies, rc 86 | **rc 86** (the deliberate kill after batch 850) | 22:01–22:17 (15:01–15:17) |
| B2 | resumes from mid.pt, dies, rc 86 | **rc 1: CRASHED** | 22:17–22:19 (15:17–15:19) |
| B3 | — | not run | — |

- **The resume itself went as designed:** `{"resume_from": "mid.pt", "mid": {"epoch": 1, "next_i":
  300}}`, then "Resuming MID-EPOCH … epoch 2 batch 300/500, state restored bitwise" (`"bitwise":
  true`). Criterion (d) held for what it checks.
- **The first optimizer step then raised**, in `torch/optim/adam.py` `_fused_adam`:
  `RuntimeError: params, grads, exp_avgs, and exp_avg_sqs must have same dtype, device, and layout`.
- `resume_proof.py compare` was not run: there is no B trace to compare. **Per the decision above:
  FAIL, so v1 keeps epoch-level checkpoints (`MID_CKPT` unset).** The overnight chain recorded that
  in `v1-vs-v0png.md` before v1 started. `TEMP_HOLD_MAX_LOAD` stays: its exit condition (r3-paired.md,
  "EXIT") is not met.

**Diagnosis (Claude, NOT proven: both hypotheses need a GPU check):**
1. **The step counters' device.** `load_state_dict` casts the per-parameter `step` to the
   parameter's device only when the SAVED param group says `fused` / `capturable`. `_restore`
   copies `group.get("fused")` from the live group, and that can be `None` while the runtime still
   picks the fused kernel (the traceback shows `_fused_adam`). So the `step` tensors could stay on
   the CPU.
2. **The state's strides.** `to_cpu` makes every saved tensor `.contiguous()`, and
   `load_state_dict` only moves the device and dtype. Any parameter whose memory format is not
   contiguous then gets state with different strides, which the fused kernel refuses.

**Proposed fix (not applied):**
- after `load_state_dict`, rebuild each state tensor as `torch.empty_like(param).copy_(saved)` (the
  parameter's device, dtype and strides), and each `step` as a float32 tensor on the parameter's
  device;
- or pin the kernel at save AND restore (`fused` recorded in the checkpoint and passed explicitly).
- A host test cannot reproduce the fused CUDA kernel (no torch on the host). The fix needs its own
  short GPU check, then the SAME proof re-run as a NEW pre-registration. That is Batt's call; until
  then, `--mid-ckpt` stays opt-in and unused.
