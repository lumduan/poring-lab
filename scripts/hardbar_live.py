#!/usr/bin/env python3
"""The EXPERIMENTER's live hard-bar monitor for a running hunt-flow version (Batt 2026-10-17:
"the live hard-bar monitor stays on"). It is not part of the bot: it reads the sniffer's archive
READ-ONLY (record_session's path) and only ever STOPS a run (SIGINT, the runner's own clean stop) on
a hard bar. No packet fact reaches a bot decision (CLAUDE.md rule 1).

Hard bars (Batt 18:3x): an NPC contact, a map change, our damaging hit on a NON-TARGET other than a
Creamy. A Creamy hit is COUNTED and reported apart, never a stop, until a Creamy-aware detector is
trained. (An unknown UI state is the runner's own ui_watch stop.) On a HELD-OUT map (Batt 21:5x)
the species the bot never learned are counted apart too (``--apart``), not a stop.

    hardbar_live.py check SID [--targets J,..] [--apart J,..]      one reading of a session so far
    hardbar_live.py watch VERSION --pid PID [--targets J,..] [--apart J,..]
        every 180 s while THAT runner lives (PID: the runner's python, or the `uv run` / `nice`
        wrapper that started it -- its runner child is resolved once)

BOUND TO ONE RUNNER (Batt 2026-10-19, after the night's stale monitor: a watch that looked for
"any runner of this version" latched onto each next chained run). It ends when its own runner is
gone, whatever else runs; never start a second monitor beside a chain (the chain starts one per
run).
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import time
from collections import Counter
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

DEMO = Path("/dev/shm/poring-lab-demo")
GM = 2000002
TARGETS = {1002, 1063, 1113, 1008}  # farm0.TARGETS (prt_fild08)
CREAMY = 1018
EVERY_S = 180.0


def bars(packets: Iterable[Mapping[str, Any]], targets: set[int] = TARGETS,
         apart: set[int] = frozenset()) -> dict[str, Any]:  # fmt: skip
    """PURE: the hard bars in time-ordered packets -> {"stop": {...}, "creamy_hits": n,
    "apart_hits": {job: n} (``apart``: counted, never a stop), "attack_requests": {...}}."""
    job: dict[int, Any] = {}
    stop: Counter[str] = Counter()
    apart_n: Counter[str] = Counter()
    creamy = 0
    reqs: Counter[str] = Counter()
    for e in packets:
        typ = e.get("type")
        if typ == "entity_appear" and e.get("gid") is not None:
            job[int(e["gid"])] = e.get("job")
        elif typ == "act" and e.get("src_gid") == GM and int(e.get("damage") or 0) > 0:
            j = job.get(int(e.get("target_gid") or -1))
            if j is not None and int(j) == CREAMY:
                creamy += 1
            elif j is not None and int(j) in apart:
                apart_n[str(j)] += 1
            elif j is not None and int(j) not in targets:
                stop[f"non_target_hit:{j}"] += 1
        elif typ == "attack_request":
            j = job.get(int(e.get("target_gid") or -1))
            reqs["target" if j is None or int(j) in targets else f"other:{j}"] += 1
        elif typ == "npc_contact":
            stop["npc_contact"] += 1
        elif typ == "map_change":
            stop["map_change"] += 1
    out = {"stop": dict(stop), "creamy_hits": creamy, "attack_requests": dict(reqs)}
    if apart:
        out["apart_hits"] = dict(apart_n)
    return out


def check(sid: str, targets: set[int] = TARGETS, apart: set[int] = frozenset()) -> dict[str, Any]:
    import record_session as rs
    import ro_agent as r

    ev = [json.loads(x) for x in (DEMO / sid / "events.jsonl").read_text().splitlines() if x]
    t0 = next(e["t_ns"] for e in ev if e["kind"] == "loop_start")
    now = r.ns()
    pk = sorted(rs._events_since(t0, 60.0, t0, now), key=lambda e: int(e["t_mono_ns"]))
    return {"min": round((now - t0) / 60e9, 1), **bars(pk, targets, apart)}


def _sig(version: int) -> str:
    return f"hunt_flow.py run --version {version} "


def pick_runner(ps_lines: Iterable[str], pid: int, version: int) -> int | None:
    """PURE: the runner process bound to ``pid`` in ``ps -eo pid,ppid,args`` lines: ``pid`` itself
    when it is the runner's python, else its descendant that is (``nice`` -> ``uv run`` ->
    python); None when neither is a ``hunt_flow.py run --version VERSION`` python (gone, reused,
    another version)."""
    rows: dict[int, tuple[int, str]] = {}
    for line in ps_lines:
        parts = line.split(None, 2)
        if len(parts) == 3 and parts[0].isdigit() and parts[1].isdigit():
            rows[int(parts[0])] = (int(parts[1]), parts[2])

    def is_runner(p: int) -> bool:
        args = rows[p][1] + " "
        return _sig(version) in args and "uv run" not in args and not args.startswith("nice ")

    if pid not in rows:
        return None
    if is_runner(pid):
        return pid
    todo = [pid]
    while todo:
        q = todo.pop()
        for c, (pp, _a) in rows.items():
            if pp == q:
                if is_runner(c):
                    return c
                todo.append(c)
    return None


def _ps() -> list[str]:
    out = subprocess.run(["ps", "-eo", "pid,ppid,args"], capture_output=True, text=True).stdout
    return out.splitlines()[1:]


def watch(version: int, bound: int, targets: set[int] = TARGETS,
          apart: set[int] = frozenset()) -> int:  # fmt: skip
    """Every EVERY_S while the runner bound to ``bound`` lives (``pick_runner``, resolved once
    within 60 s of the start); SIGINT to THAT runner on a hard bar. Never another runner."""
    pid: int | None = None
    for _ in range(60):
        pid = pick_runner(_ps(), bound, version)
        if pid is not None:
            break
        time.sleep(1.0)
    if pid is None:
        print(time.strftime("%T"), f"no v{version} runner under pid {bound}: watch ends",
              flush=True)  # fmt: skip
        return 2
    print(time.strftime("%T"), f"bound to runner pid {pid}", flush=True)
    time.sleep(60.0)
    while True:
        if pick_runner(_ps(), pid, version) != pid:  # gone (or the pid reused): never re-bind
            print(time.strftime("%T"), f"runner {pid} gone: watch ends", flush=True)
            return 0
        sids = sorted(p.name for p in DEMO.glob(f"*-demo-hunt-flow{version}"))
        try:
            got = check(sids[-1], targets, apart)
        except (StopIteration, FileNotFoundError, IndexError) as exc:  # the loop not started yet
            got = {"waiting": type(exc).__name__}
        print(time.strftime("%T"), json.dumps(got), flush=True)
        if got.get("stop"):
            print(time.strftime("%T"), f"HARD BAR -> SIGINT {pid}", flush=True)
            os.kill(pid, signal.SIGINT)
            return 0
        time.sleep(EVERY_S)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)  # fmt: skip
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name, arg, typ in (("check", "sid", str), ("watch", "version", int)):
        sp = sub.add_parser(name)
        sp.add_argument(arg, type=typ)
        sp.add_argument("--targets", default=",".join(map(str, sorted(TARGETS))))
        sp.add_argument("--apart", default="", help="jobs counted apart, never a stop")
        if name == "watch":
            sp.add_argument("--pid", type=int, required=True,
                            help="the ONE runner to watch (its python or its wrapper)")  # fmt: skip
    a = ap.parse_args()
    tg = {int(x) for x in a.targets.split(",") if x}
    apart = {int(x) for x in a.apart.split(",") if x}
    if a.cmd == "check":
        print(json.dumps(check(a.sid, tg, apart)))
        return 0
    return watch(a.version, a.pid, tg, apart)


if __name__ == "__main__":
    sys.exit(main())
