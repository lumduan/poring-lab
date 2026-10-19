#!/usr/bin/env python3
"""Queue the remaining PRE-REGISTERED runs of ONE hunt-flow version so the client keeps working
even when the experimenter's turn stalls (Batt 2026-10-18 night: "an agent-side hiccup cost
3.5 h tonight ... Never queue an unjudged NEXT version; judging and pre-registering stay with
you"). It sends no input itself and decides nothing about versions.

    hunt_chain.py --version 39 --seeds 20280202,20280303,20280404 [--minutes 60]

Per seed, in order:
1. wait until no `hunt_flow.py run` process is left (the run before, chained or not);
2. read the CONTROL file (``CTL``: "stop" ends the chain before the next run; the quant hook
   forbids rm under /dev/shm, so it is a content marker, never a file's absence);
3. /health: mode ASSIST and no human lease, else the chain ends (Batt's takeover: stop as
   designed);
4. a screenshot of the game region to ``OUT/pre-v<version>-<seed>.jpg`` (judged by the
   experimenter; the runner's own start check -- client state, immunity, the hunting state --
   refuses an unknown UI state by itself);
5. the run (`nice -n 10`, its stdout to ``OUT/v<version>-<seed>.out``) with the live hard-bar
   monitor beside it (`hardbar_live.py watch V --pid <this run>`, bound to this runner only,
   which SIGINTs it on a hard bar);
6. the runner's exit code: 0 (its time box) -> the next seed. A SAFE runner stop (Batt
   2026-10-19 overnight: "After a safe runner stop, the chain starts the next pre-registered run
   of the SAME version (fresh start checks) so a stalled turn doesn't idle the client") -> the
   next seed too: the runner's own clean stop (rc 3, a FarmStop / Stop it raised itself: an
   unreadable cell, layout or weight, a lost input ack, its UI gate refusing). The chain still
   ENDS on a packet hard bar (the live monitor stopped it: NPC contact, map change, a non-target
   hit), a SIGINT, a human lease / takeover, an immune GM losing HP, a crash, or the 2nd safe
   stop in a row (`after_run`). A stopped seed is not re-run by the chain (its partial run is
   kept); a re-run of a seed gets a letter suffix on its files.
Every step is one line in ``OUT/chain-v<version>.log``.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = Path("/dev/shm/poring-lab-tmp/hunt-flow")
CTL = OUT / "chain.ctl"


def log(version: int, msg: str) -> None:
    line = f"{time.strftime('%Y-%m-%d %H:%M:%S')} {msg}"
    print(line, flush=True)
    with open(OUT / f"chain-v{version}.log", "a") as fh:
        fh.write(line + "\n")


def runner_running() -> bool:
    out = subprocess.run(["ps", "-eo", "args"], capture_output=True, text=True).stdout
    return any("hunt_flow.py run" in a and "uv run" not in a for a in out.splitlines())


def control() -> str:
    """PURE-ish: the control word ("run" unless the file says "stop")."""
    try:
        word = CTL.read_text().strip().lower()
    except OSError:
        return "run"
    return "stop" if word == "stop" else "run"


def health_ok(h: dict[str, object]) -> str | None:
    """PURE: why the next run may NOT start (None = it may)."""
    if h.get("mode") != "ASSIST":
        return f"mode {h.get('mode')}"
    if h.get("lease_active"):
        return "a human lease is active"
    return None


MAX_SAFE_IN_ROW = 2
END_WORDS = ("keyboardinterrupt", "lease", "takeover", "took over", "human", "mux",
             "lost hp")  # fmt: skip


def after_run(rc: int, ended: str | None, monitor_stopped: bool, safe_in_row: int) -> str:
    """PURE: what the chain does after a run -- "next" (the next seed: its time box, or a SAFE
    stop) or "end". Safe = the runner's own clean stop (rc 3, ``ended`` "stopped:FarmStop: ..."
    / "stopped:Stop: ..."), not a packet hard bar (``monitor_stopped``), not a SIGINT, a human
    lease / takeover or an immune GM's HP loss, and fewer than MAX_SAFE_IN_ROW in a row
    (``safe_in_row`` counts this one)."""
    if rc == 0:
        return "next"
    if rc != 3 or not ended or monitor_stopped:
        return "end"
    low = ended.lower()
    if not low.startswith(("stopped:farmstop:", "stopped:stop:")):
        return "end"
    if any(w in low for w in END_WORDS):
        return "end"
    return "next" if safe_in_row < MAX_SAFE_IN_ROW else "end"


def ended_of(text: str) -> str | None:
    """PURE: the runner's ``ended`` from its last JSON summary line in ``text`` (None if none)."""
    for line in reversed(text.strip().splitlines()):
        if line.startswith("{") and '"ended"' in line:
            try:
                return str(json.loads(line)["ended"])
            except (ValueError, KeyError):
                return None
    return None


def run_tag(out: Path, version: int, seed: int) -> str:
    """The seed's file tag: the seed, or seed + b, c, ... when its files exist (a re-run)."""
    for suf in ("", "b", "c", "d", "e", "f"):
        if not (out / f"v{version}-{seed}{suf}.out").exists():
            return f"{seed}{suf}"
    return f"{seed}-{int(time.time())}"


def health() -> dict[str, object]:
    sys.path.insert(0, str(ROOT / "scripts"))
    import ro_agent as r

    h = r.backend_health()
    return {k: h.get(k) for k in ("mode", "lease_active", "bot_agents")}


def screenshot(path: Path) -> None:
    sys.path.insert(0, str(ROOT / "scripts"))
    import numpy as np
    import ro_agent as r
    from PIL import Image

    s = r.Screen()
    x0, y0, w, h = r.game_region()
    a = np.asarray(s.grab(x0, y0, w, h)[1])[..., :3][..., ::-1]
    Image.fromarray(np.ascontiguousarray(a)).save(path, quality=85)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)  # fmt: skip
    ap.add_argument("--version", type=int, required=True)
    ap.add_argument("--seeds", required=True, help="comma-separated, in order")
    ap.add_argument("--minutes", type=float, default=60.0)
    a = ap.parse_args()
    seeds = [int(x) for x in a.seeds.split(",") if x.strip()]
    OUT.mkdir(parents=True, exist_ok=True)
    log(a.version, f"chain start: v{a.version} seeds {seeds} x {a.minutes} min")
    safe_in_row = 0
    for seed in seeds:
        while runner_running():
            time.sleep(10)
        if control() == "stop":
            log(a.version, f"control says stop: chain ends before seed {seed}")
            return 0
        try:
            h = health()
        except Exception as exc:  # noqa: BLE001 -- the backend unreachable: never start blind
            log(a.version, f"health unreadable ({exc!r:.120}): chain ends before seed {seed}")
            return 2
        why = health_ok(h)
        if why is not None:
            log(a.version, f"{why}: chain ends before seed {seed} ({json.dumps(h)})")
            return 2
        tag = run_tag(OUT, a.version, seed)
        shot = OUT / f"pre-v{a.version}-{tag}.jpg"
        try:
            screenshot(shot)
        except Exception as exc:  # noqa: BLE001
            log(a.version, f"screenshot failed ({exc!r:.120}): chain ends before seed {seed}")
            return 2
        log(a.version, f"seed {seed}: health {json.dumps(h)}, screenshot {shot.name}; run starts")
        with open(OUT / f"v{a.version}-{tag}.out", "w") as fo:
            run = subprocess.Popen(
                ["nice", "-n", "10", "uv", "run", "python", "scripts/hunt_flow.py", "run",
                 "--version", str(a.version), "--minutes", str(a.minutes), "--seed", str(seed)],
                cwd=ROOT, stdout=fo, stderr=subprocess.STDOUT)  # fmt: skip
            time.sleep(5)
            with open(OUT / f"hardbar-v{a.version}-{tag}.log", "w") as fm:
                # bound to THIS run's process (Batt 2026-10-19): it ends with this runner and
                # can never latch onto the next one
                mon = subprocess.Popen(
                    ["nice", "-n", "10", "uv", "run", "python", "scripts/hardbar_live.py",
                     "watch", str(a.version), "--pid", str(run.pid)], cwd=ROOT, stdout=fm,
                    stderr=subprocess.STDOUT)  # fmt: skip
                rc = run.wait()
                # the monitor only ever stops a RUNNING runner: done with it at once (its own
                # 180-s cadence would leave the client idle for minutes between runs)
                mon.terminate()
                try:
                    mon.wait(timeout=30)
                except subprocess.TimeoutExpired:
                    mon.kill()
        text = (OUT / f"v{a.version}-{tag}.out").read_text()
        tail = text[-400:].strip().splitlines()
        log(a.version, f"seed {seed}: runner rc {rc}; last line {tail[-1][:300] if tail else '-'}")
        mon_stop = "HARD BAR" in (OUT / f"hardbar-v{a.version}-{tag}.log").read_text()
        ended = ended_of(text[-20000:])
        safe_in_row = 0 if rc == 0 else safe_in_row + 1
        if after_run(rc, ended, mon_stop, safe_in_row) != "next":
            log(a.version, f"seed {seed} did not end on its time box ({ended!r:.160}; monitor "
                f"stop {mon_stop}): chain ends")  # fmt: skip
            return 3
        if rc != 0:
            log(a.version, f"seed {seed}: a SAFE stop ({ended!r:.160}); the next seed starts "
                "with fresh start checks")  # fmt: skip
    log(a.version, "chain done")
    return 0


if __name__ == "__main__":
    sys.exit(main())
