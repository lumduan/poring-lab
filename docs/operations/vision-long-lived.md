---
doc_type: runbook
hypothesis: "One long-lived vision container per day, with every training/eval attempt run inside it, removes the cold-start IO bursts that stalled quant at ~100 % (2026-10-09 16:46) without changing R1-R3, the IO guard or the verified stop."
status: PROPOSED
role: null
verdict_date: null
verdict_ticket: null
supersedes: null
related: [r3-paired.md, ../../scripts/guarded_build.py, ../../scripts/runbooks/train-day.sh, ../../scripts/runbooks/quiet_start.py]
next_action: "Batt: OK the plan. Then build the two guarded steps + their unit tests (no switch), run THE PROOF once in a measured quiet window (quiet_start), report, and switch v1 / the evals only after Batt's OK of the proof."
---

# Option A: one long-lived vision container per day (PLAN; nothing switched)

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

## 3. The design (PROPOSED)
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

## 4. Unit tests (before any live run)
- `run_cmd` / `exec_cmd`: the exact argv for `execdev:`; the worker's name; `timeout`.
- `verify_stop` in exec mode (fakes for docker, ps and nvidia-smi):
  - the process exits → VERIFIED with the container still up;
  - the process lingers → SIGINT, then kill -9, then VERIFIED;
  - a CUDA context still listed after the kill → `docker kill` of the worker → VERIFIED, else
    STOP-UNVERIFIED.
- PairedR3 on a worker: pause / unpause target the worker, and the measurement pairs are unchanged.
- train-day with `WORKER=1`: the guard gets `execdev:`; the exit codes and MAX_ATTEMPTS hold.

## 5. THE PROOF (live, once, in a measured quiet window; one container start)
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
