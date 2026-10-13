---
doc_type: runbook
hypothesis: "One long-lived vision container per day, with every training/eval attempt run inside it, removes the cold-start IO bursts that stalled quant at ~100 % (2026-10-09 16:46) without changing R1-R3, the IO guard or the verified stop."
status: "PROVEN 2026-10-10 (5b: PASS on all four items of 5a) and SWITCHED under Batt's advance approval; history: MERGED 4c5edbf (2026-10-09 ~20:35); APPROVED by Batt 2026-10-09 (~19:30); BUILT on feat/vision-worker (90a7b74), unit-tested, NOT proven live, NOT switched"
role: null
verdict_date: null
verdict_ticket: null
supersedes: null
related: [r3-paired.md, ../../scripts/guarded_build.py, ../../scripts/runbooks/train-day.sh, ../../scripts/runbooks/quiet_start.py, ../../compose.vision-worker.yaml, ../../scripts/runbooks/worker_proof.py]
next_action: "chain15 runs v1's evals + re-proof 2 in one worker; the next training uses train-day WORKER=1. Batt: whether to pre-warm the CUDA libraries before a worker's first run (the remaining burst, 5b)."
---

# Option A: one long-lived vision container per day (BUILT; NOT proven live; NOT switched)

> **Status, 2026-10-09 ~20:30:** the plan (sections 3-6) was APPROVED by Batt (~19:30). It is
> **BUILT on `feat/vision-worker` (90a7b74), unit-tested, NOT proven live, NOT switched.** Nothing
> uses it until the parent runs THE PROOF (section 5, "How to run it") and Batt OKs the result:
> `train-day.sh` still runs `rundev:` unless `WORKER=1`, and `eval.sh` is unchanged. What was
> built, and where it departs from the plan: section 3a.

**Batt, 2026-10-09 ~17:00:** "option A (one long-lived vision container per day; each attempt runs
inside it). PROVE first that an R3 stop still leaves NOTHING of ours on the GPU (the training process
exits, no CUDA context held; check nvidia-smi), and that the IO guard / R3 flows work unchanged.
Plan + test, then my OK before switching."

## 1. Why
- **Today:** every vision attempt is `guarded_build.py rundev:vision@S=CMD`, which runs
  `timeout S docker compose -f compose.yaml -f compose.vision-dev.yaml --profile vision run --rm
  --name poring-lab-vision-rundev-<pid> --no-deps vision CMD` (`guarded_build.run_cmd`).
- **Every attempt is therefore a COLD START:** a new container from the ~5 GB torch image, and a
  Python that imports torch / CUDA / ultralytics from the image's layers on the shared disk.
- **2026-10-09, measured at 1 s** (`data/metrics/io_pressure_20261009T093508Z.csv`):
  - v1's resume at 16:46:18 put quant-postgres, quant-ticker-engine and the capture cron at ~100 %
    full IO stall at 16:46:23-24, and quant-crypto at 85 % at 16:46:31-33.
  - The guard aborted at 16:46:27.
  - The starts at 14:12, 14:33 and 15:22 aborted too.
  - The 16:41-16:46 watch just before was calm (every quant cgroup < 19 %).
- **Chained evals multiply it:** chain8 / chain9 run ~10 more `rundev` containers (9 evals, gold
  predict, the proof runs): ~10 more cold starts.

## 2. The open question the proof must answer FIRST
The ~100 % burst may come from either of two events:
- **(i) creating / starting the container** (the overlay mount, the image layers' metadata);
- **(ii) the first Python import** of torch / CUDA / ultralytics, reading several GB of `.so` and
  `.py` files from the image layers.

If it is (ii), a long-lived container still pays the burst at its first `exec`. Later execs are warm
only while the page cache keeps those files: the host has 24 GB and shares it with Frigate, Ollama
and quant, so they can be evicted within hours.

The proof measures the two separately. Section 6 states what each outcome means for the design.

## 3. The design (APPROVED 2026-10-09 ~19:30; BUILT 90a7b74, section 3a)
- **A long-lived service** `vision-worker` (compose.vision-dev.yaml): the same image, mounts and
  limits as today's `vision` run: R1's `VISION_MAX_VRAM_FRACTION`, mem == memswap, `oom_score_adj`,
  the read-only duty mount, the `agent` network only (ADR-0005).
  - Its entrypoint is IDLE (`sleep infinity`, or the warm worker of section 6). It never imports
    torch, so it holds NO CUDA context while idle (proof step 2).
- **New guarded steps** in `guarded_build.py` (the docker hook allows only guarded forms):
  - `worker:vision@S` starts the worker ONCE, through `quiet_start` (a measured quiet window), and
    watches the IO guard for S seconds;
  - `execdev:vision@S=CMD` runs `timeout S docker exec <worker> CMD`. The R3 / IO / R2 machinery
    is UNCHANGED: the same pre-start refusals (Ollama `/api/ps`, another job of ours on the GPU,
    Frigate down), the same PairedR3 ON/OFF windows (docker pause / unpause of the worker
    container, which pauses the training process inside it), the same IO guard, the same
    adaptive duty cycle;
  - `worker-stop:vision`, at the end of the day or on demand.
- **The verified stop for an exec** (the change to `verify_stop`): "stopped" = the exec'd training
  process GONE (no `poring_vision` command line inside the worker or on the host), no process of
  ours on the GPU (nvidia-smi), and the worker idle with NO CUDA context.
  - Escalation is unchanged in spirit: SIGINT to the exec'd process, then `docker exec <worker>
    kill -9 <pid>`. If the GPU still shows ours, `docker kill` the worker itself.
  - A STOP-UNVERIFIED still stops the chain for a person.
- **train-day.sh:** `GUARD` builds `execdev:` instead of `rundev:` behind a switch (`WORKER=1`).
  Everything else is unchanged: the exit codes, MAX_ATTEMPTS, the market windows, the R3 flows.
- **The evals** (chain8's list) become `execdev:` steps inside the same worker, one at a time.

## 3a. As built (90a7b74, `feat/vision-worker`; offline only)
**The pieces:**
- `compose.vision-worker.yaml`: service `vision-worker` (profile `vision-worker`), container
  `poring-lab-vision-worker-1`. It is EXACTLY a `rundev:vision` container: compose.yaml's vision plus
  compose.vision-dev.yaml's two read-only mounts and `PYTHONPATH`, the same image, environment,
  limits, GPU and network. `tests/test_guards.py` pins every field against vision's.
- `guarded_build.py`:
  - `worker:vision@S` = `docker compose -f compose.yaml -f compose.vision-worker.yaml --profile
    vision-worker up -d --no-deps --no-build vision-worker`, under the IO guard, then a watch of S
    seconds, then a check: idle, nothing of it on the GPU (`WORKER UP ...`).
  - `execdev:vision@S=CMD` = `timeout S+60 docker exec poring-lab-vision-worker-1 timeout
    --kill-after=30 S CMD`, with the rundev: machinery unchanged around it.
  - `worker-stop:vision` = `docker compose ... stop vision-worker`, then verified down
    (`WORKER STOPPED ...`).
- `verify_stop(..., exec_mode=True)`. The guard's SIGINT reaches only the `docker exec` client, so:
  1. SIGINT to the exec'd process (the tops of what runs in the worker beyond its entrypoint),
     confirmed within `STOP_VERIFY_S` (30 s);
  2. else kill -9 of every job process in the worker, our GPU processes and the host client,
     confirmed within 15 s;
  3. else, if the GPU still lists ours or the worker is still busy, `docker kill` of the worker,
     logged `WORKER KILLED`, confirmed within 15 s;
  4. else STOP-UNVERIFIED (a person looks).
  "Stopped" = the worker runs only `docker-init -- sleep infinity`; no GPU process of ours (in the
  worker, still exiting in its cgroup, or `poring_vision` anywhere); no client left on the host.
- `train-day.sh WORKER=1`: `GUARD` builds `execdev:`. A worker that is down or was killed ->
  PAUSED (3) at once; one that is not ready -> STOPPED (2). Everything else is unchanged.
- `--test-abort-after-cycles N` (TEST ONLY, proof step 4): the IO-trip abort path once the step's R3
  schedule has closed N ON/OFF cycles.
- `scripts/runbooks/worker_proof.py`: section 5 as a runbook (below).
- Unit tests: `services/backend/tests/test_vision_worker.py` (42), plus cases in test_guards,
  test_guard_hook and test_train_day. The whole suite passes in the worktree (2675; one map-cache
  test needs the gitignored generated caches the tmpfs worktree lacks).

**Departures from the plan, each found while building (none changes R1-R3, the IO guard or the
exit codes):**
1. **An INNER `timeout` in the exec.** The plan's `timeout S docker exec <worker> CMD` would bound
   only the client: the Docker API cannot signal an exec'd process, so killing the client leaves it
   running. The outer bound is now S + 60 s, and the inner one (`--kill-after=30 S`) bounds the
   process.
2. **kill -9 from the host, by host pid**, not `docker exec <worker> kill -9 <pid>`. Same uid, no
   daemon round trip, and no new process in the worker that would read as a job.
3. **`docker kill` of the worker also when it is still BUSY after kill -9**, not only when the GPU
   lists ours.
4. **"Ours on the GPU" in exec mode covers more than `poring_vision`:** any process in the worker
   (e.g. `check_gpu.py`), and an exiting task still in its cgroup (a CUDA context being torn down).
5. **A normal end is verified too** (`settle_exec`). A client that ends on its own while the worker
   is still busy (a daemon hiccup, a SIGINT to it by hand) is stopped like an abort, never left
   running unguarded.
6. **`execdev:` refuses unless the worker is ready:** up, unpaused, IDLE (one job at a time), and
   started from THIS checkout (its source, duty-file and data mounts).
   - Down -> `REFUSED ... WORKER down` (rc 3).
   - Anything else -> `REFUSED ... WORKER not ready` (rc 3).
7. **The worker: `restart: "no"`, no `build`, `pull_policy: never`, no `depends_on`.**
   - A reboot or a crash never restarts it: that would be an unmeasured cold start.
   - `worker:` never recreates a running worker.
   - `worker-stop:` refuses while a job runs.
8. **The docker hook refuses raw `docker exec` into any vision container.** Before this, `docker
   exec` was allowed, and it would have been the one way around R2/R3 for a job in the worker.
9. **Proof step 4 runs a TRAINING step (bound 3600 s: R3's 180 s windows), not a short one.**
   - A short step's 60 s window has ~2.4 Frigate updates after its 20 s settle (one per ~16 s,
     r3-paired.md), below the 3 a window needs, so one cycle would measure no pair.
   - It holds the duty at the slowest level (`DUTY_START=DUTY_MIN=4`), so the smoke is still running
     when the cycle closes.
10. **`quiet_start` wraps the step; `worker:` does not wait for quiet itself.** The proof runbook,
    the guard's docstring and the compose file say to start it as `quiet_start.py --
    guarded_build.py ... worker:vision@120`.

**Left for the switch (needs Batt's OK after the proof; nothing here is wrong today):**
- `scripts/runbooks/eval.sh` and `train.sh` still run `rundev:`. The evals move to `execdev:` at the
  switch.
- The LEGACY `frigate_r3.py watch --sigint` (no production caller since 2026-10-07) finds only
  compose service `vision` containers, so it would not stop a job inside the worker.
- CLAUDE.md rule 5 names "every `run:`/`rundev:` vision step". `execdev:` enforces the same rules;
  add it to that line at the switch.

## 4. Unit tests (before any live run) -- BUILT: test_vision_worker.py + cases elsewhere (3a)
- `run_cmd` / `exec_cmd`: the exact argv for `execdev:`; the worker's name; `timeout`.
- `verify_stop` in exec mode (fakes for docker, ps and nvidia-smi):
  - the process exits → VERIFIED with the container still up;
  - the process lingers → SIGINT, then kill -9, then VERIFIED;
  - a CUDA context still listed after the kill → `docker kill` of the worker → VERIFIED, else
    STOP-UNVERIFIED.
- PairedR3 on a worker: pause / unpause target the worker, and the measurement pairs are unchanged.
- train-day with `WORKER=1`: the guard gets `execdev:`; the exit codes and MAX_ATTEMPTS hold.

## 5. THE PROOF (live, once, in a measured quiet window; one container start)
**How to run it** (the parent, after the merge and after v1's chain10 has ended; never alongside an
S2 session; R1-R3 refuse it by themselves while Ollama holds a model or another job of ours is on
the GPU):

    python3 scripts/io_baseline.py --interval 1 ...      # the 1 s sampler (already the parent's)
    python3 scripts/runbooks/worker_proof.py --cache <CACHE_ID> --dry-run    # print the six steps
    python3 scripts/runbooks/worker_proof.py --cache <CACHE_ID> \
        --io-csv data/metrics/io_pressure_<start>.csv  [--steps 3-6 to resume]

- Each step prints its MEASUREMENT and PASS / FAIL, and the run stops at the first FAIL.
- It never starts a step inside, or within 15 min of, a market-open window.
- Its only docker actions are guarded_build steps; everything else is read-only (docker inspect,
  the worker's cgroup, /proc, nvidia-smi).
- What step 2 must show: the worker's processes are exactly `docker-init -- sleep infinity` and
  `sleep infinity`. `idle_argv` assumes that shape, and it was not observable offline.

Run by the parent with the 1 s IO sampler on, and reported step by step:
1. `quiet_start` → `worker:vision@120`: start the idle worker. **Measure** the per-second full
   stall of every capture cgroup over the start (question 2, event i).
2. `nvidia-smi --query-compute-apps`: **no process of ours** with the worker idle (no CUDA context).
3. `execdev:` a `python -c "import torch, ultralytics"` probe (no CUDA init). **Measure** the IO of
   the first import (event ii).
4. `execdev:` a SMOKE training (`--smoke`, a few minutes, under the duty cycle):
   - a planned R3 ON/OFF cycle runs. Record that the pairs are measured as today;
   - then a FORCED stop through the guard's abort path (a test flag that makes the guard abort as
     on an IO trip).
   - **Measure:** the seconds to "STOP VERIFIED", nvidia-smi showing no process of ours, the worker
     still up and idle, and no CUDA context.
5. A second smoke `execdev:` (warm). **Measure** its import IO, then let it finish normally;
   nvidia-smi is empty again.
6. `worker-stop:vision`.

**PASS:**
- every stop VERIFIED, with nothing of ours on the GPU within STOP_VERIFY_S;
- the idle worker holds no CUDA context;
- the R3 pairs are measured as today;
- the IO of steps 3-5 states whether event (i), event (ii) or both cause the burst.

### 5a. Pre-registered for the run (2026-10-09 ~21:00 ICT, BEFORE any live step)
Batt, 2026-10-09 ~20:20 (the weekend run): "Option A: build, unit-test, then the ONE live proof (start
vs cold torch import answered first). Advance approval to SWITCH train-day to the worker IF every
proof item passes as pre-registered (nothing of ours on the GPU after a forced stop, R3/IO flows
unchanged); otherwise stay on the current path and report."
- **When:** after v1's training ends (chain12 logs `v1 TRAIN DONE`), before v1's evals: the evals
  are ~10 vision starts and were held for option A (chain10's note). Never alongside an S2 session.
- **The command:** `worker_proof.py --cache v0png-20261006 --io-csv <the 1 s sampler's CSV>` (the
  smoke uses the v0png cache, as re-proof 2 does; the cache does not matter to the proof).
- **The bar is section 5's PASS, item by item, scored from the runbook's printed measurements:**
  1. steps 4 and 5: every stop `STOP VERIFIED` within STOP_VERIFY_S (30 s), and nvidia-smi lists no
     process of ours afterwards;
  2. steps 2, 4 and 5: the idle worker's processes are exactly the `sleep infinity` pair, with no
     process on the GPU (no CUDA context);
  3. step 4: the R3 summary shows at least one closed ON/OFF pair measured as today (the same
     `R3 summary` fields as a rundev run), and the forced stop took the IO-trip path (unpause,
     SIGINT, verified stop);
  4. steps 1, 3 and 5: the per-second capture-cgroup stalls are reported for each event, and the
     report states which event (i) start / (ii) import / both carried the burst, or "neither burst".
- **An IO-guard trip during a step is an INTERRUPTION, not a result** (as chain8 / re-proof 2): the
  step stops (verified), its IO is still a measurement for question 2, and the remaining steps run
  ONCE in the next measured quiet window (`--steps N-6`), never an immediate retry (Batt's v1 rule
  for the weekend: "after an IO trip wait for the next quiet window"). A second interruption of the
  same step ends the proof as INCOMPLETE: no switch, reported.
- **PASS (all 4) =>** the switch, under Batt's advance approval: train-day `WORKER=1` from the next
  training run, v1's evals and re-proof 2's runs as `execdev:` steps inside the worker (one start
  for all of them), the worker stopped by `worker-stop:vision` when the GPU queue is empty and
  always before Monday 05:00 ICT. CLAUDE.md rule 5 gains `execdev:` in the same commit.
- **FAIL or INCOMPLETE =>** no switch: the current `rundev:` path stays, each eval one start per
  quiet window, and the report says which item failed.
- **What the IO result changes (section 6):** if the burst is (ii) the import, the warm-Python
  variant or the pre-warm is Batt's choice; the switch above still holds (one start per day is
  already an improvement), and the import burst is reported with the numbers.

### 5b. The run (2026-10-10, chain14 after v1's TRAIN DONE at 08:22 ICT)
- **Step 1 start: PASS.** The quiet window came at 08:58:39 ICT (the wait from 08:23:55 saw quant's
  own bursts: quant-postgres up to 37 %, frigate up to 32 %, cron 30.5 %). `worker:vision@120` rc 0;
  the worker cgroup read 35 MiB, wrote 0, in 121 s. Capture full stall over the START itself
  (01:58:37-02:00:46 UTC, computed from the 1 s CSV): frigate 21.9 %, quant-postgres 12.3 %, all
  others <= 4 %, **0 s above 25 %**.
- **Step 2 idle: PASS.** The worker's processes are exactly `docker-init -- sleep infinity` and
  `sleep infinity`; nothing of ours on the GPU.
- **Step 3 probe: the runbook printed FAIL, and the FAIL is the RUNBOOK's (a parser bug), not the
  probe's.** The probe's own output: `PROBE import_s=7.6 cuda_initialized=False torch=2.14.0+cu130`,
  rc 0, the worker idle and nothing of ours on the GPU afterwards -- every condition of step 3 holds.
  The parser took the FIRST line containing "PROBE import_s=", which was the guard's echo of the
  command (its python text holds `cuda_initialized=%s`). The import's IO: the worker read 493 MiB in
  11 s (peak 234 MiB/s); capture full stall over it (02:00:43-02:00:59 UTC): frigate 5.0 %,
  quant-postgres 4.7 %, **0 s above 25 %**.
- **So far, question 2: NEITHER event burst in this quiet window** (neither the start nor the cold
  import pushed any capture cgroup over 25 %); the 2026-10-09 ~100 % bursts came from `rundev` cold
  starts in busier windows.
- **➡️ AMENDMENT (recorded BEFORE continuing, like the IO-trip rule above):** the parser now matches only
  the probe's printed result (`PROBE import_s=<digits>`, tested); step 3 is scored from its own
  output as PASS; the proof continues ONCE with `--steps 4-6` on the same, still-idle worker. The
  runbook's original summary stays in `/dev/shm/poring-lab-tmp/gpu-day/worker-proof.out`.

- **Steps 4-6 (`--steps 4-6`, 09:10-09:38 ICT): all PASS.**
  - **Step 4 forced:** the TEST abort after one R3 ON/OFF cycle took the IO-trip path; **STOP VERIFIED
    after 3 s** (limit 30), no escalation, the worker not killed, nothing of ours on the GPU after;
    the R3 summary held 1 pair, kept 1 (measured as today).
  - **Step 5 warm:** a second smoke run in the same worker finished normally (rc 0); idle and free after.
  - **Step 6 stop:** `worker-stop:vision` rc 0; the worker stopped; nothing of ours on the GPU.
- **Question 2 ANSWERED (the 1 s CSV, per second):** the burst comes from the FIRST CUDA RUN in a
  fresh container, not from the container start (step 1: 0 s > 25 %) nor from the bare torch import
  (step 3: 0 s > 25 %, no CUDA init). Step 4 began 02:03:11 UTC; from 02:03:22 the worker's own cgroup
  stalled 25-46 % for ~80 s (it read 611 MiB: the CUDA libraries and the model) and every capture
  cgroup spiked with it (02:03:32-33: quant-postgres 83.7 %, quant-orderbook 78.4 %, quant-ticker
  70.2 %, cron 79.3 %); the guard's 10 s rule did not trip. In the WARM step 5 (same worker, 8 min
  later) the worker stalled itself again (up to 69 %) but NO capture cgroup passed 25 % at its start.
- **➡️ VERDICT, scored against 5a: PASS on all four items.** Under Batt's advance approval (2026-10-09
  ~20:20) the switch is made: the next training run uses train-day `WORKER=1`; v1's evals and re-proof
  2 run as `execdev:` steps inside ONE worker (chain15, a single worker start in a quiet window);
  CLAUDE.md rule 5 names `execdev:` (this commit). What the result means (section 6): one worker per
  day pays the CUDA burst once, at its first run; later runs reuse the page cache. The warm-Python
  variant would not avoid it (the burst is at CUDA's first use, not the import); a pre-warm of the
  CUDA libraries in a quiet window remains an option for Batt.

## 5c. The warm-resume rule (Batt, 2026-10-13, decision 14)
"Yes: a resume inside a WARM worker skips the IO quiet window; keep the window for worker
(re)starts and after IO trips."
- **Why:** 5b measured that the IO burst is a fresh container's FIRST CUDA run. Later runs in the
  same worker do not burst. On 2026-10-11, v1b lost ~1.5 h waiting for a quiet IO window before a
  warm resume after an R3-HARD abort.
- **So:** after an R3-HARD abort (once the 15 quiet Frigate minutes pass), after an R3 latency trip,
  or after the 12 h step cap, the next attempt in an UP worker starts at once.
  - After an IO trip it waits for the next measured quiet window (unchanged).
  - A worker (re)start always goes through `quiet_start` (unchanged).

## 6. What the proof's IO result means
- **The burst is (i), the container start:** option A as designed. One cold start per day, in a
  quiet window.
- **The burst is (ii), the import:**
  - the worker keeps a WARM Python: a small supervisor that imports torch / ultralytics once (no
    CUDA) and forks one child per attempt (the child inits CUDA and exits; the parent never does),
    so the libraries stay mapped;
  - or B, a rate-limited pre-warm of the library files before the first import, when quiet.
  - Batt chooses.
- **Both:** the warm worker, started in a quiet window.

## 7. Until then (option D, tonight)
- `scripts/runbooks/quiet_start.py` starts v1's resume only after 10 quiet minutes (no capture
  cgroup above 25 % in any second), never in a market window.
- `train-day.sh MAX_ATTEMPTS=1`: one container start, no retry.
- No evals are chained: each would be another cold start.
- Run as `chain10` (`/dev/shm/poring-lab-tmp/gpu-day/chain10.sh`), launched 17:07 ICT; its log is
  `/dev/shm/poring-lab-tmp/gpu-day/quiet_start.log`.
