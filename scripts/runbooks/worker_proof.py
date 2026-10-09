#!/usr/bin/env python3
"""THE PROOF of option A, the long-lived vision worker (docs/operations/vision-long-lived.md
section 5; Batt 2026-10-09: "PROVE first that an R3 stop still leaves NOTHING of ours on the GPU
... and that the IO guard / R3 flows work unchanged"). Run ONCE by a person, live, with the 1 s IO
sampler on (scripts/io_baseline.py --interval 1: the parent's). Nothing is switched by it.

    python3 scripts/runbooks/worker_proof.py --cache CACHE_ID [--steps 1-6]
        [--io-csv data/metrics/io_pressure_<start>.csv] [--quiet-min 10] [--dry-run]

Each step prints what it runs, then its MEASUREMENT and PASS / FAIL; the run stops at the first
FAIL (a person looks before anything else runs). Every docker action is a guarded_build step; the
script itself only READS (docker inspect, the worker's cgroup, /proc, nvidia-smi).

  1 start   quiet_start (no capture cgroup > 25 % for --quiet-min) -> `worker:vision@120`.
            Measures: the worker cgroup's own block IO over the start; with --io-csv, every capture
            cgroup's per-second full stall over [start, end] (event i, the container start).
  2 idle    nvidia-smi --query-compute-apps + the worker's processes: no process of ours on the GPU,
            only docker-init + `sleep infinity` (no CUDA context).
  3 probe   `execdev:` python -c "import torch, ultralytics" (no CUDA init: it prints
            torch.cuda.is_initialized()). Measures the first import's IO (event ii), 1 s profile.
  4 forced  `execdev:` a --smoke training under the duty cycle, held at the slowest level
            (DUTY_START=DUTY_MIN=4: 2 s per batch, so it is still running when the cycle closes),
            bound 3600 s (a training step: R3's 180 s windows, >= 6 Frigate updates each, so a
            pair is measured as in a real run), with guarded_build's TEST flag
            --test-abort-after-cycles 1: one planned R3 ON/OFF cycle runs (its pairs are printed as
            in any run), then the guard aborts it through the IO-trip path. Measures: seconds to
            STOP VERIFIED, nvidia-smi, the worker up and idle.
  5 warm    `execdev:` a second --smoke (warm), left to finish normally. Measures its import IO
            (compare with step 3), then nvidia-smi empty again and the worker idle.
  6 stop    `worker-stop:vision`: the worker down, nothing of ours on the GPU.

PASS (the plan): every stop VERIFIED with nothing of ours on the GPU within STOP_VERIFY_S; the idle
worker holds no CUDA context; the R3 pairs are measured as today; steps 1, 3 and 5 say whether the
container start (i), the first import (ii) or both cause the burst. Never inside the market-open
windows (09:30-10:15, 14:00-14:45 ICT): a step due inside one is not started.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import shlex
import subprocess
import sys
import threading
import time
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))
import guarded_build as gb  # noqa: E402

ICT = timezone(timedelta(hours=7))
MARKET = ((930, 1015), (1400, 1445))  # ICT hhmm, [start, end): CLAUDE.md rule 5
GUARD = ["python3", "scripts/guarded_build.py", "--sustain", "30", "--spike", "25"]
CAPTURE_COLS = [*gb.CONTAINERS, "cron.service"]  # io_baseline.py's capture cgroups
LIMIT = 25.0  # the guard's spike threshold, and quiet_start's
PROBE = ('import time; t = time.monotonic(); import torch, ultralytics; print("PROBE '
         'import_s=%.1f cuda_initialized=%s torch=%s" % (time.monotonic() - t, '
         'torch.cuda.is_initialized(), torch.__version__), flush=True)')  # fmt: skip
STEP_NAMES = {1: "start", 2: "idle", 3: "probe", 4: "forced", 5: "warm", 6: "stop"}


def now_str() -> str:
    t = datetime.now(UTC)
    return f"{t.astimezone(ICT):%F %T} ICT / {t:%T} UTC"


def in_market(t: datetime, ahead_min: float = 15.0) -> bool:
    """Inside a market-open window, or one starts within ``ahead_min`` (a step's first minutes are
    its disk-heavy import)."""
    for dt in (0.0, ahead_min):
        u = (t + timedelta(minutes=dt)).astimezone(ICT)
        if any(a <= u.hour * 100 + u.minute < b for a, b in MARKET):
            return True
    return False


def parse_steps(spec: str) -> list[int]:
    out: list[int] = []
    for part in spec.split(","):
        a, _, b = part.partition("-")
        out += range(int(a), int(b or a) + 1)
    if not out or any(s not in STEP_NAMES for s in out) or out != sorted(set(out)):
        raise ValueError(f"--steps {spec}: ascending steps among 1-6")
    return out


def smoke(cache: str, name: str) -> str:
    return (f"python -m poring_vision.train --cache /datasets/.framecache/{cache} --smoke "
            f"--batch 2 --workers 1 --name {name} --step-sleep-ms 2000 "
            "--duty-file /lab-duty/duty.json")  # fmt: skip


SLOWEST = {"DUTY_START": "4", "DUTY_MIN": "4"}  # step 4: 2 s per batch, the whole run


def commands(cache: str, quiet_min: float, tag: str, forced_s: int, warm_s: int,
             cycles: int) -> dict[int, tuple[dict[str, str], list[str]]]:  # fmt: skip
    """(extra environment, command) of each step (step 2 runs none: it only reads)."""
    return {
        1: ({}, ["python3", "scripts/runbooks/quiet_start.py", "--quiet-min", f"{quiet_min:g}",
                 "--limit", f"{LIMIT:g}", "--", *GUARD, "worker:vision@120"]),
        2: ({}, []),
        3: ({}, [*GUARD, f"execdev:vision@600=python -c {shlex.quote(PROBE)}"]),
        4: (SLOWEST, [*GUARD, "--test-abort-after-cycles", str(cycles),
                      f"execdev:vision@{forced_s}={smoke(cache, f'worker-proof-{tag}-forced')}"]),
        5: ({}, [*GUARD, f"execdev:vision@{warm_s}={smoke(cache, f'worker-proof-{tag}-warm')}"]),
        6: ({}, [*GUARD, "worker-stop:vision"]),
    }  # fmt: skip


# --- reading only -------------------------------------------------------------------------------
def gpu_apps() -> list[tuple[int, str, int]] | None:
    """(pid, process name, MiB) of every compute process, or None when nvidia-smi fails."""
    try:
        out = subprocess.run(["nvidia-smi", "--query-compute-apps=pid,process_name,used_memory",
                              "--format=csv,noheader,nounits"], capture_output=True, text=True,
                             timeout=15, check=True).stdout  # fmt: skip
    except (OSError, subprocess.SubprocessError):
        return None
    apps = []
    for line in out.splitlines():
        parts = [p.strip() for p in line.split(",")]
        if len(parts) >= 3 and parts[0].isdigit():
            apps.append((int(parts[0]), parts[1], int(parts[2]) if parts[2].isdigit() else -1))
    return apps


def snapshot() -> dict[str, Any]:
    """The worker's state and processes, and the GPU, from the host."""
    state, cid = gb.docker_state(gb.WORKER)
    procs = gb.worker_procs(gb.WORKER)
    apps = gpu_apps()
    ours = None
    if apps is not None:
        ours = gb.gpu_ours_exec(gb.WORKER, [p for p, _, _ in apps], procs or {})
    return {"state": state, "cid": cid, "procs": procs, "busy": gb.busy(procs or {}),
            "gpu": apps, "ours": ours}  # fmt: skip


def show(s: dict[str, Any]) -> str:
    procs = gb.describe(s["procs"]) if s["procs"] else s["procs"]
    gpu = "UNREADABLE" if s["gpu"] is None else (s["gpu"] or "none")
    return (f"worker {s['state']}; its processes: {procs}; GPU compute apps: {gpu}; "
            f"ours on the GPU: {s['ours']}")  # fmt: skip


def idle_and_free(s: dict[str, Any]) -> bool:
    return bool(s["state"] == "running" and s["procs"] and not s["busy"] and s["ours"] == [])


def io_stat(cid: str) -> tuple[int, int] | None:
    """(read bytes, written bytes) of the worker's cgroup, every device."""
    try:
        text = Path(f"/sys/fs/cgroup/system.slice/docker-{cid}.scope/io.stat").read_text()
    except OSError:
        return None
    rb = sum(int(m) for m in re.findall(r"\brbytes=(\d+)", text))
    wb = sum(int(m) for m in re.findall(r"\bwbytes=(\d+)", text))
    return rb, wb


def profile_text(prof: list[tuple[float, int, int]]) -> str:
    """The worker's block IO over a step: totals, the peak second, the first 60 s in 5 s bins."""
    if len(prof) < 2:
        return "worker block IO: no samples (no worker cgroup during the step)"
    t0, r0, w0 = prof[0]
    mb = 1024 * 1024
    peak = max(((b[1] - a[1]) / max(b[0] - a[0], 1e-3), b[0] - t0)
               for a, b in zip(prof, prof[1:], strict=False))  # fmt: skip
    bins = []
    for k in range(0, 60, 5):
        inside = [r for t, r, _ in prof if t - t0 <= k + 5]
        before = [r for t, r, _ in prof if t - t0 <= k]
        if inside and before:
            bins.append(f"{(inside[-1] - before[-1]) / mb:.0f}")
    return (
        f"worker block IO over {prof[-1][0] - t0:.0f} s: read {(prof[-1][1] - r0) / mb:.0f} MiB,"
        f" written {(prof[-1][2] - w0) / mb:.0f} MiB; peak read {peak[0] / mb:.0f} MiB/s at "
        f"+{peak[1]:.0f} s; read MiB per 5 s over the first 60 s: [{', '.join(bins)}]"
    )


def io_window(path: Path, t0: datetime, t1: datetime, tail_bytes: int = 8 << 20) -> str:
    """Every capture cgroup's per-second full stall over [t0, t1] from the 1 s sampler's CSV (only
    its tail is read: the window is recent)."""
    try:
        with path.open("rb") as fh:
            header = fh.readline().decode().strip().split(",")
            size = fh.seek(0, 2)
            fh.seek(max(len(",".join(header)) + 1, size - tail_bytes))
            if fh.tell() > len(",".join(header)) + 1:
                fh.readline()  # a partial line
            rows = list(csv.reader(fh.read().decode(errors="replace").splitlines()))
    except OSError as exc:
        return f"IO csv unreadable ({exc})"
    lo, hi = t0 - timedelta(seconds=2), t1 + timedelta(seconds=2)
    cols = {n: header.index(f"{n}.full") for n in CAPTURE_COLS if f"{n}.full" in header}
    peak: dict[str, float] = {}
    above: dict[str, int] = {}
    n = 0
    for row in rows:
        try:
            t = datetime.fromisoformat(row[0])
        except (ValueError, IndexError):
            continue
        if not lo <= t <= hi:
            continue
        n += 1
        for name, i in cols.items():
            try:
                v = float(row[i])
            except (ValueError, IndexError):
                continue
            peak[name] = max(peak.get(name, 0.0), v)
            above[name] = above.get(name, 0) + (v > LIMIT)
    if not n:
        return f"IO csv: no rows in [{lo:%T}, {hi:%T}] UTC (is the 1 s sampler running?)"
    worst = sorted(peak.items(), key=lambda kv: -kv[1])
    cells = ", ".join(f"{k} {v:.1f}% ({above[k]} s > {LIMIT:g}%)" for k, v in worst)
    return f"capture full stall over {n} rows [{lo:%T}, {hi:%T}] UTC: {cells}"


# --- running a guarded step ---------------------------------------------------------------------
def run(env: dict[str, str], cmd: list[str],
        cid: str | None) -> tuple[int, list[str], list[tuple[float, int, int]]]:  # fmt: skip
    """Run one step (live output), sampling the worker cgroup's block IO every second."""
    words = " ".join(f"{k}={v}" for k, v in env.items())
    print(f"  $ {words + ' ' if words else ''}{shlex.join(cmd)}", flush=True)
    proc = subprocess.Popen(cmd, cwd=REPO, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            text=True, env={**os.environ, **env})  # fmt: skip
    lines: list[str] = []

    def pump() -> None:
        assert proc.stdout is not None
        for line in proc.stdout:
            lines.append(line.rstrip("\n"))
            print(f"  | {line.rstrip()}", flush=True)

    reader = threading.Thread(target=pump, daemon=True)
    reader.start()
    prof: list[tuple[float, int, int]] = []
    looked = 0.0
    while proc.poll() is None:
        if cid is None and time.monotonic() - looked >= 5:  # step 1: the worker appears mid-step
            looked = time.monotonic()
            state, new = gb.docker_state(gb.WORKER)
            if state == "running":
                cid = new
                prof.append((time.monotonic(), 0, 0))  # a NEW cgroup: its counters began at 0
        got = io_stat(cid) if cid else None
        if got is not None:
            prof.append((time.monotonic(), *got))
        time.sleep(1.0)
    reader.join(timeout=10)
    return proc.returncode, lines, prof


def guard_facts(lines: list[str]) -> dict[str, Any]:
    """What the guard's output says about a stop: the forced abort, the R3 pairs, the verified stop
    and its seconds, an escalation, the worker killed."""
    text = "\n".join(lines)
    facts: dict[str, Any] = {
        "forced": "TEST forced stop" in text,
        "verified": "STOP VERIFIED" in text,
        "unverified": "STOP-UNVERIFIED" in text,
        "escalated": "ESCALAT" in text,
        "worker_killed": "WORKER KILLED" in text,
        "refused": next((ln for ln in lines if "REFUSED" in ln), None),
        "stop_s": None,
        "pairs": None,
        "kept": None,
    }
    m = re.search(r"STOP VERIFIED \S+ after (?:escalation \()?(\d+)s", text)
    if m:
        facts["stop_s"] = int(m.group(1))
    for ln in lines:
        if "R3 summary: " in ln:
            try:
                summ = json.loads(ln.split("R3 summary: ", 1)[1])
                facts["pairs"], facts["kept"] = len(summ.get("pairs", [])), summ.get("kept_pairs")
            except ValueError:
                pass
    return facts


class Proof:
    def __init__(self, a: argparse.Namespace) -> None:
        self.a = a
        tag = datetime.now(UTC).strftime("%Y%m%dT%H%M")
        self.cmds = commands(a.cache, a.quiet_min, tag, a.forced_seconds, a.warm_seconds,
                             a.cycles)  # fmt: skip
        self.results: list[tuple[int, str, bool, str]] = []

    def record(self, n: int, ok: bool, what: str) -> bool:
        self.results.append((n, STEP_NAMES[n], ok, what))
        print(f"STEP {n} {STEP_NAMES[n]}: {'PASS' if ok else 'FAIL'} -- {what}", flush=True)
        return ok

    def window(self, t0: datetime, t1: datetime) -> str:
        if self.a.io_csv:
            return io_window(self.a.io_csv, t0, t1)
        return f"(no --io-csv: read the 1 s sampler's CSV over [{t0:%T}, {t1:%T}] UTC)"

    def step(self, n: int) -> bool:
        print(f"\n=== STEP {n} {STEP_NAMES[n]} -- {now_str()}", flush=True)
        if n == 2:
            s = snapshot()
            print(f"  {show(s)}", flush=True)
            return self.record(
                2,
                idle_and_free(s),
                "idle worker, no CUDA context"
                if idle_and_free(s)
                else f"NOT idle / ours on the GPU: {show(s)}",
            )
        before = snapshot()
        t0 = datetime.now(UTC)
        rc, lines, prof = run(*self.cmds[n], before["cid"] or None)
        t1 = datetime.now(UTC)
        after = snapshot()
        facts = guard_facts(lines)
        io = f"{profile_text(prof)}; {self.window(t0, t1)}"
        print(f"  after: {show(after)}", flush=True)
        if facts["refused"]:
            return self.record(n, False, f"REFUSED (nothing ran): {facts['refused']}")
        if n == 1:
            ok = rc == 0 and idle_and_free(after)
            return self.record(1, ok, f"rc {rc}; {io}")
        if n == 3:
            probe = next((ln for ln in lines if "PROBE import_s=" in ln), "no PROBE line")
            ok = rc == 0 and "cuda_initialized=False" in probe and idle_and_free(after)
            return self.record(3, ok, f"rc {rc}; {probe.split('| ')[-1].strip()}; {io}")
        if n == 4:
            ok = (facts["forced"] and facts["verified"] and not facts["unverified"]
                  and not facts["worker_killed"] and (facts["pairs"] or 0) >= 1
                  and facts["stop_s"] is not None and facts["stop_s"] <= gb.STOP_VERIFY_S
                  and idle_and_free(after))  # fmt: skip
            what = (f"forced stop {'exercised' if facts['forced'] else 'NOT exercised (the smoke '
                    'ended first)'}; R3 pairs {facts['pairs']} (kept {facts['kept']}); "
                    f"STOP VERIFIED after {facts['stop_s']} s (limit {gb.STOP_VERIFY_S:.0f}); "
                    f"escalated {facts['escalated']}; worker killed {facts['worker_killed']}; "
                    f"{io}")  # fmt: skip
            return self.record(4, ok, what)
        if n == 5:
            ok = rc == 0 and not facts["escalated"] and idle_and_free(after)
            return self.record(5, ok, f"rc {rc} (finished normally: {rc == 0}); {io}")
        ok = rc == 0 and after["state"] in ("stopped", "absent") and after["ours"] == []
        return self.record(6, ok, f"rc {rc}; worker {after['state']}; ours on the GPU "
                                  f"{after['ours']}")  # fmt: skip


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)  # fmt: skip
    ap.add_argument("--cache", required=True, help="the frame cache id for the smoke runs")
    ap.add_argument("--steps", default="1-6")
    ap.add_argument("--io-csv", type=Path, default=None, help="the 1 s IO sampler's CSV")
    ap.add_argument("--quiet-min", type=float, default=10.0)
    ap.add_argument(
        "--forced-seconds",
        type=int,
        default=3600,
        help="step 4's bound (> 1200: a training step, R3's 180 s windows)",
    )
    ap.add_argument("--warm-seconds", type=int, default=5400, help="step 5's bound")
    ap.add_argument("--cycles", type=int, default=1, help="step 4: R3 cycles before the abort")
    ap.add_argument("--dry-run", action="store_true", help="print the steps, run nothing")
    a = ap.parse_args()
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", a.cache):
        ap.error("--cache: a frame cache id")
    try:
        steps = parse_steps(a.steps)
    except ValueError as exc:
        ap.error(str(exc))
    proof = Proof(a)
    if a.dry_run:
        for n in steps:
            env, cmd = proof.cmds[n]
            words = "".join(f"{k}={v} " for k, v in env.items())
            print(f"STEP {n} {STEP_NAMES[n]}: {words + shlex.join(cmd) if cmd else '(reads only)'}")
        return 0
    for n in steps:
        if in_market(datetime.now(UTC)):
            print(f"STEP {n} NOT STARTED: inside or within 15 min of a market-open window "
                  f"(09:30-10:15 / 14:00-14:45 ICT); re-run with --steps {n}-{steps[-1]} after it",
                  flush=True)  # fmt: skip
            return 4
        if not proof.step(n):
            print(f"\nSTOPPED at step {n}: a person looks before anything else runs", flush=True)
            break
    print("\n=== SUMMARY", flush=True)
    for n, name, ok, what in proof.results:
        print(f"  {n} {name:<6} {'PASS' if ok else 'FAIL'}  {what}", flush=True)
    return 0 if proof.results and all(ok for *_, ok, _ in proof.results) else 1


if __name__ == "__main__":
    sys.exit(main())
