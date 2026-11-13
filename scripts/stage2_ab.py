#!/usr/bin/env python3
"""LIVE BLOCKS STAGE 2's A/B (docs/planning/live-blocks.md 3.2, the pre-registered bar there):
the runner ALONE (A) against the ONE-BOX project through the live block player (B), alternating
runs of the same length on xmas_dun02, the same setup before every run, one detect server for the
whole series. Batt 2026-11-13: "Heal: press F1 when HP < 30 %. Fly Wing: press F8 when a boss is
seen or HP < 25 %" -- B plays those two as the box's events inside the hunt core; A is the runner
with its own potion and Fly Wing, exactly as the old Run path starts it.

    stage2_ab.py plan  --label L [--pairs N] [--minutes M] [--order alternate|ab]   PURE
    stage2_ab.py run   --label L [--pairs N] [--minutes M] [--order alternate|ab]   LIVE
    stage2_ab.py score --label L [--json]                                            PURE (reads)
    stage2_ab.py read          a setup step (a child process): pixels only, prints JSON
    stage2_ab.py close-chat    a setup step (a child process): Enter on an OPEN, EMPTY input

THE ARMS (the same runner settings for both: the Run config, the box's five keys over it, its
--minutes M):
- A: `dungeon_hunt.py run` with the Run helper's own argv (flow_run.command: FIXED, --player-mode,
  every technique of the config) -- the old Run path;
- B: `flow_play.py play` of the ready-made project (services/frontend/src/lib/flow/fixtures/
  project_xmas_dun02.json, its time box set to M minutes) on the node xmas_dun02, with those
  settings as its runner config (flow_run.play_command): the hunt core is the same runner, its
  potion, Fly Wing on HP and boss fly played by the box's events (live.hunt_plan).
The order: "alternate" (the default) is AB, BA, AB, ... (each pair's first arm alternates, so a
slow drift -- the MVP's respawn, the map's crowd -- does not favour one arm); "ab" is AB, AB, ...

THE SETUP before every run, the same for both arms (every step a child process, never beside a
run: one input writer), stopping the series at the first step it cannot judge:
1. the read (pixels only): her weight and the hotbar counts on F1 / F8 / F9;
2. the bag at or over CLEAR_AT (or unread): `dungeon_hunt.py clear-bag --tabs etc,use` (the lab's
   own tool, as the night chain: the loot dropped, the potions and Fly Wings restocked), read again;
3. the lab GM's `@warp xmas_dun02 X Y` (crusader.py gm: identity, the chat guard, the UI gate),
   the cell alternating between dungeon_hunt.PATROL_START's two (7 21 / 114 23), so the chat
   guard never meets one line three times in a row; then the minimap must read xmas_dun02;
4. a GM `@item ID N` only for an item under its floor (TOPUP: the Butterfly Wing under 2 -> 3,
   the Fly Wing under 7 -> 10, the White Potion under 7 -> 10); an unread count stops the series;
5. close-chat: the chat input closed and READ closed (else the run's own start would refuse).
The run then refuses on its own start check if anything is still wrong (before any input).

THE DETECT SERVER once (unit_detector.py serve-cmd, its time box the whole series + 10 min), as
the Run helper starts it, and ended by its host PID at the end. A file STOP in the series folder
(/dev/shm/poring-lab-tmp/stage2-ab/<label>/STOP) ends the series before its next run; a run over
its time box + START_GRACE_S gets the runner's stop file, then SIGINT STOP_GRACE_S later.

THE SCORE (per run, from the RUNNER's own session events.jsonl -- the same reader for both arms --
and for B also the player's: its box events): minutes, deaths, potions, Fly Wings by cause (hp,
rate, boss, garm, pos_unread, stuck, unreach, end, other), kills/h, loot steps/h, the lowest HP,
the box's events fired. The verdict applies the bar pre-registered in live-blocks.md 3.2 (BAR).
"""

from __future__ import annotations

import argparse
import contextlib
import json
import math
import os
import signal
import statistics
import subprocess
import sys
import time
from collections import Counter
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
for _p in ("packages/poring_flow/src", "packages/poring_skills/src", "packages/poring_env/src"):
    if str(ROOT / _p) not in sys.path:
        sys.path.append(str(ROOT / _p))

import flow_run as fr  # noqa: E402

VERSION = "9.49"  # dungeon_hunt.SURVIVAL_EVENTS_VERSION: the stage it measures
MAP = "xmas_dun02"
NODE = "xmas_dun02"
FLOW_ID = "xmas_dun02_rogue"  # flow_run.FLOWS: the old Run path's runner
PROJECT = ROOT / "services/frontend/src/lib/flow/fixtures/project_xmas_dun02.json"
DEMO = Path("/dev/shm/poring-lab-demo")
SCRATCH = Path("/dev/shm/poring-lab-tmp/stage2-ab")
PY = str(ROOT / ".venv" / "bin" / "python")
CLEAR_AT = 0.40  # the night chain's WEIGHT_CLEAR: at or over it, clear-bag before the run
# (item, its key, floor, to): a GM @item only when the read count is under the floor
TOPUP = ((602, "F9", 2, 3), (601, "F8", 7, 10), (504, "F1", 7, 10))
WARP_SETTLE_S, ARRIVE_S = 4.0, 20.0
START_GRACE_S, STOP_GRACE_S = 180.0, 90.0
SERVE_EXTRA_S = 600
CHAT_GUARD_RUN = 3  # chat_guard refuses the 3rd identical line in a row
# THE PRE-REGISTERED BAR (live-blocks.md 3.2, written before any live run): what B must hold vs A
BAR = {
    "min_minutes_share": 0.8,  # a run counts when it ran at least this share of M minutes
    "min_pairs": 3,  # fewer valid pairs: kills/h is not judged (INCONCLUSIVE)
    "deaths": "B's deaths <= A's (the series' totals)",
    "potions_per_h_margin": 6.0,  # B's potions / h <= A's + this
    "flies_per_h_margin": 4.0,  # B's Fly Wings / h (not the end's own escape) <= A's + this
    "kills_h_se": 2.0,  # mean paired (B - A) kills / h >= -this x its standard error
}


# --- the plan (PURE) ------------------------------------------------------------------------------
@dataclass(frozen=True)
class Run:
    k: int  # 1-based, in the series' order
    pair: int
    arm: str  # "A" (the runner alone) | "B" (the box through the player)
    label: str
    warp: str  # the GM warp line of its setup


def arms(pairs: int, order: str = "alternate") -> list[str]:
    """PURE: the arm of every run, pair by pair: alternate = AB, BA, AB, ...; ab = AB, AB, ..."""
    if order not in ("alternate", "ab"):
        raise ValueError(f"order {order!r}: alternate or ab")
    out: list[str] = []
    for i in range(pairs):
        out += ["B", "A"] if order == "alternate" and i % 2 == 1 else ["A", "B"]
    return out


def warp_lines(n: int, cells: Sequence[tuple[int, int]]) -> list[str]:
    """PURE: the setup's warp line per run, alternating the two cells (the chat guard)."""
    return [f"@warp {MAP} {cells[i % 2][0]} {cells[i % 2][1]}" for i in range(n)]


def dh_cells() -> Sequence[tuple[int, int]]:
    """The map's two patrol starts (dungeon_hunt.PATROL_START): the setup's warp cells."""
    import dungeon_hunt as dh

    return dh.PATROL_START[MAP]


def series(label: str, pairs: int, order: str = "alternate",
           cells: Sequence[tuple[int, int]] | None = None) -> list[Run]:  # fmt: skip
    """PURE: the runs of a series, in order."""
    if pairs < 1:
        raise ValueError("at least one pair")
    if cells is None:
        import dungeon_hunt as dh

        cells = dh.PATROL_START[MAP]
    a = arms(pairs, order)
    w = warp_lines(len(a), cells)
    return [Run(k + 1, k // 2 + 1, arm, f"{label}-r{k + 1:02d}{arm}", w[k])
            for k, arm in enumerate(a)]  # fmt: skip


def topup_lines(counts: Mapping[str, int | None],
                table: Sequence[tuple[int, str, int, int]] = TOPUP) -> list[str] | str:  # fmt: skip
    """PURE: the @item lines for the items under their floor, or why the setup stops (a count
    that did not read: a person first). ``counts``: key -> the hotbar's count."""
    out: list[str] = []
    for item, key, floor, to in table:
        n = counts.get(key)
        if n is None:
            return f"the count on {key} (item {item}) did not read: a person first"
        if n < floor:
            out.append(f"@item {item} {to - n}")
    return out


def guard_ok(lines: Iterable[str], run: int = CHAT_GUARD_RUN) -> bool:
    """PURE: no line typed `run` times in a row (chat_guard's repeat rule)."""
    last, n = None, 0
    for ln in lines:
        n = n + 1 if ln == last else 1
        last = ln
        if n >= run:
            return False
    return True


def guard_history(state: Mapping[str, Any]) -> list[str]:
    """PURE: the chat guard's own repeat history (its per-host state, chat_guard.STATE: the last
    chat line and how many times in a row), as the lines a guard_ok check starts from. Lines
    typed by OTHER processes (stage 1's setups, clear-bag) count: the guard counts them too."""
    last = state.get("chat") if isinstance(state, Mapping) else None
    if not isinstance(last, Mapping) or not isinstance(last.get("text"), str):
        return []
    return [str(last["text"])] * max(0, int(last.get("count") or 0))


def pick_warp(planned: str, other: str, history: Sequence[str]) -> str:
    """PURE: the setup's warp line -- the planned cell, or the other one when the planned line
    would be the chat guard's 3rd identical line in a row (2026-11-14 00:38: stage 1's two setups
    had typed the first cell twice, and the series stopped before any run)."""
    if guard_ok([*history, planned]):
        return planned
    return other


def read_guard_state() -> dict[str, Any]:
    """The chat guard's state file (a read; {} when it is missing or unreadable)."""
    import chat_guard

    try:
        return dict(json.loads(chat_guard.STATE.read_text()))
    except (OSError, ValueError):
        return {}


def project_text(minutes: float, path: Path | None = None) -> str:
    """PURE but for the read: the ready-made box with its time box set to the run's length."""
    from poring_flow import project as pj

    d = json.loads((path or PROJECT).read_text())
    d["max_runtime_s"] = int(round(minutes * 60))
    return pj.to_json(pj.validate(d))


def run_vals(minutes: float, config_dir: Path = fr.CONFIG_DIR) -> dict[str, Any] | str:
    """The runner settings BOTH arms take: the Run config (default < every map < this map), the
    box's five keys over it (project.runner_keys), --minutes M. A refusal: its words."""
    from poring_flow import project as pj

    p = pj.from_json(PROJECT.read_text())
    rk = pj.runner_keys(p, NODE)
    if rk.keys is None:
        return f"the box's keys: {'; '.join(rk.problems)}"
    vals, _src, _ks, why = fr.run_values(fr.FLOWS[FLOW_ID], rk.keys, config_dir)
    if why:
        return why
    return {**vals, "minutes": minutes}


def commands(r: Run, folder: Path, vals: Mapping[str, Any], minutes: float,
             project_hash: str) -> list[str]:  # fmt: skip
    """PURE: the run's argv -- A: the old Run path's runner (flow_run.command); B: the player of
    the box (flow_run.play_command) with the same settings in its runner config."""
    stop = folder / f"{r.label}.STOP"
    if r.arm == "A":
        return fr.command(fr.FLOWS[FLOW_ID], r.label, stop, dict(vals))
    return fr.play_command(folder / "project.json", NODE, r.label, stop, int(round(minutes * 60)),
                           project_hash, folder / "runner-config.json")  # fmt: skip


def plan_doc(label: str, pairs: int, minutes: float, order: str, folder: Path,
             config_dir: Path = fr.CONFIG_DIR) -> dict[str, Any] | str:  # fmt: skip
    """PURE but for reads (the config, the fixture): everything a series will do, before any
    screen is read or any input path opened; a refusal: its words."""
    import flow_play as fp

    from poring_flow import project as pj

    vals = run_vals(minutes, config_dir)
    if isinstance(vals, str):
        return f"refused before any input: {vals}"
    text = project_text(minutes)
    h = pj.project_hash(pj.from_json(text))
    prep = fp.prepare(text, NODE, int(round(minutes * 60)), runner_vals={NODE: vals},
                      want_hash=h)  # fmt: skip
    if isinstance(prep, str):
        return prep
    runs = series(label, pairs, order)
    return {
        "version": VERSION, "label": label, "pairs": pairs, "minutes": minutes, "order": order,
        "project_hash": h, "box_plays": sorted(prep.runners[NODE].plays),
        "box_events": list(prep.runners[NODE].events), "vals": vals, "bar": BAR,
        "serve_s": int(len(runs) * (minutes * 60 + START_GRACE_S + 120) + SERVE_EXTRA_S),
        "runs": [{**asdict(r), "argv": commands(r, folder, vals, minutes, h)} for r in runs],
    }  # fmt: skip


# --- the score (PURE over the sessions' events) ---------------------------------------------------
FLY_CAUSES = ("hp", "rate", "boss", "garm", "pos_unread", "stuck", "unreach", "end", "other")


def fly_cause(why: str, garm_just_seen: bool) -> str:
    """PURE: a Fly Wing press's cause from its record's `why` (the runner's words; a box press is
    "box <event> (<reading>)", dungeon@9.49)."""
    if why.startswith("box "):
        return "boss" if "sees_boss True" in why else "hp"
    if why == "boss":
        return "garm" if garm_just_seen else "boss"
    if why.startswith("hp "):
        return "hp"
    if why.startswith("rate "):
        return "rate"
    if why in ("pos_unread", "end", "unreach"):
        return why
    if why in ("idle", "dead_end", "stuck"):
        return "stuck"
    return "other"


@dataclass
class Score:
    label: str
    arm: str
    pair: int
    found: bool = False
    minutes: float = 0.0
    end: str | None = None
    deaths: int = 0
    potions: int = 0
    flies: dict[str, int] = field(default_factory=dict)
    kills: int = 0
    loot_steps: int = 0
    hp_low: int | None = None
    box_fired: dict[str, int] = field(default_factory=dict)
    words: str | None = None  # the player's end (B)

    def per_h(self, n: float) -> float:
        return n * 60.0 / self.minutes if self.minutes > 0 else 0.0

    @property
    def flies_no_end(self) -> int:
        return sum(n for c, n in self.flies.items() if c != "end")

    def doc(self) -> dict[str, Any]:
        return {**asdict(self), "kills_h": round(self.per_h(self.kills), 1),
                "loot_h": round(self.per_h(self.loot_steps), 1),
                "potions_h": round(self.per_h(self.potions), 2),
                "flies_h": round(self.per_h(self.flies_no_end), 2)}  # fmt: skip


GARM_TICK_NS = 2_000_000_000  # a "boss" Fly Wing this soon after a garm_seen is the Garm Baby's


def score_runner(sc: Score, events: Iterable[Mapping[str, Any]]) -> None:
    """PURE: add one runner session's events (a B run may have several hunt cores)."""
    t0 = t1 = None
    garm_t = -(10**18)
    flies: Counter[str] = Counter(sc.flies)
    for e in events:
        k, t = e.get("kind"), int(e.get("t_ns") or 0)
        if k == "run_start":
            t0 = t
        elif k == "run_end":
            t1, sc.end = t, str(e.get("reason") or "")
        elif k == "death":  # the runner records it, then ends (run_end "death")
            sc.deaths += 1
        elif k == "kill":
            sc.kills += 1
        elif k == "loot_step":
            sc.loot_steps += 1
        elif k == "garm_seen":
            garm_t = t
        elif k == "hp_read" and isinstance(e.get("pct"), int):
            sc.hp_low = e["pct"] if sc.hp_low is None else min(sc.hp_low, e["pct"])
        elif k == "press":
            what, why = e.get("what"), str(e.get("why") or "")
            if what == "potion":
                sc.potions += 1
            elif what == "fly":
                flies[fly_cause(why, t - garm_t <= GARM_TICK_NS)] += 1
    sc.flies = dict(flies)
    if t0 is not None and t1 is not None:
        sc.found = True
        sc.minutes += (t1 - t0) / 60e9


def score_player(sc: Score, events: Iterable[Mapping[str, Any]]) -> None:
    """PURE: a B run's player session: its box events fired (inside the hunt core) and its end."""
    fired: Counter[str] = Counter(sc.box_fired)
    for e in events:
        if e.get("kind") == "event" and e.get("in") == "hunt":
            fired[str(e.get("event"))] += 1
        elif e.get("kind") == "run_end":
            sc.words = e.get("words")
    sc.box_fired = dict(fired)


def read_events(path: Path) -> list[dict[str, Any]]:
    out = []
    for ln in path.read_text().splitlines():
        with contextlib.suppress(ValueError):
            out.append(json.loads(ln))
    return out


def score_run(r: Mapping[str, Any], demo: Path = DEMO) -> Score:
    """Reads (no screen): one run's sessions by its label."""
    label, arm = str(r["label"]), str(r["arm"])
    sc = Score(label, arm, int(r["pair"]))
    pattern = f"*-{label}" if arm == "A" else f"*-{label}-hunt*"
    for d in sorted(demo.glob(pattern)):
        if (d / "events.jsonl").is_file():
            score_runner(sc, read_events(d / "events.jsonl"))
    if arm == "B":
        for d in sorted(demo.glob(f"*-play-{label}")):
            if (d / "events.jsonl").is_file():
                score_player(sc, read_events(d / "events.jsonl"))
    return sc


def verdict(scores: Sequence[Score], minutes: float,
            bar: Mapping[str, Any] = BAR) -> dict[str, Any]:  # fmt: skip
    """PURE: the pre-registered bar (live-blocks.md 3.2) over the valid pairs."""
    ok_min = minutes * float(bar["min_minutes_share"])
    valid = {s.label for s in scores if s.found and s.minutes >= ok_min}
    pairs: dict[int, dict[str, Score]] = {}
    for s in scores:
        pairs.setdefault(s.pair, {})[s.arm] = s
    good = [p for p in pairs.values() if set(p) == {"A", "B"}
            and p["A"].label in valid and p["B"].label in valid]  # fmt: skip
    a = [p["A"] for p in good]
    b = [p["B"] for p in good]
    hours = {x: sum(s.minutes for s in arm) / 60.0 for x, arm in (("A", a), ("B", b))}

    def rate(arm: list[Score], f: Callable[[Score], float], x: str) -> float:
        return sum(f(s) for s in arm) / hours[x] if hours[x] > 0 else 0.0

    out: dict[str, Any] = {"pairs_valid": len(good), "pairs": len(pairs),
                           "invalid": sorted({s.label for s in scores} - valid)}  # fmt: skip
    if not good:
        return {**out, "verdict": "INCONCLUSIVE", "why": "no valid pair"}
    deaths = (sum(s.deaths for s in a), sum(s.deaths for s in b))
    pot = (rate(a, lambda s: s.potions, "A"), rate(b, lambda s: s.potions, "B"))
    fly = (rate(a, lambda s: s.flies_no_end, "A"), rate(b, lambda s: s.flies_no_end, "B"))
    d = [p["B"].per_h(p["B"].kills) - p["A"].per_h(p["A"].kills) for p in good]
    lines = {
        "deaths": {"A": deaths[0], "B": deaths[1], "pass": deaths[1] <= deaths[0]},
        "potions_h": {"A": round(pot[0], 2), "B": round(pot[1], 2),
                      "pass": pot[1] <= pot[0] + float(bar["potions_per_h_margin"])},
        "flies_h": {"A": round(fly[0], 2), "B": round(fly[1], 2),
                    "pass": fly[1] <= fly[0] + float(bar["flies_per_h_margin"])},
    }  # fmt: skip
    mean_d = statistics.fmean(d)
    se = statistics.stdev(d) / math.sqrt(len(d)) if len(d) > 1 else float("inf")
    kills: dict[str, Any] = {"mean_diff_h": round(mean_d, 1),
                             "se_h": None if math.isinf(se) else round(se, 1),
                             "pairs": [round(x, 1) for x in d]}  # fmt: skip
    if len(good) < int(bar["min_pairs"]):
        kills["pass"] = None  # too few pairs to judge the noise
    else:
        kills["pass"] = mean_d >= -float(bar["kills_h_se"]) * se
    lines["kills_h"] = kills
    loot = [p["B"].per_h(p["B"].loot_steps) - p["A"].per_h(p["A"].loot_steps) for p in good]
    lines["loot_h"] = {"mean_diff_h": round(statistics.fmean(loot), 1), "report_only": True}
    lines["hp_low"] = {"A": min((s.hp_low for s in a if s.hp_low is not None), default=None),
                       "B": min((s.hp_low for s in b if s.hp_low is not None), default=None),
                       "report_only": True}  # fmt: skip
    judged = [v["pass"] for v in lines.values() if "pass" in v]
    if False in judged:
        v = "FAIL"
    elif None in judged:
        v = "INCONCLUSIVE"
    else:
        v = "PASS"
    return {**out, "lines": lines, "verdict": v}


def table(scores: Sequence[Score]) -> str:
    """PURE: the per-run table (plain text, the report's)."""
    head = (f"{'run':<22}{'arm':<4}{'min':>6}{'death':>6}{'pot':>5}{'fly':>5}{'boss':>5}"
            f"{'kills/h':>9}{'loot/h':>8}{'hp_low':>7}  box events")  # fmt: skip
    rows = [head]
    for s in scores:
        fired = ", ".join(f"{k} {n}" for k, n in sorted(s.box_fired.items())) or "-"
        rows.append(f"{s.label:<22}{s.arm:<4}{s.minutes:>6.1f}{s.deaths:>6}{s.potions:>5}"
                    f"{s.flies_no_end:>5}{s.flies.get('boss', 0):>5}"
                    f"{s.per_h(s.kills):>9.1f}{s.per_h(s.loot_steps):>8.1f}"
                    f"{'-' if s.hp_low is None else s.hp_low:>7}  {fired}")  # fmt: skip
    return "\n".join(rows)


# --- the live steps (each a child process; the series runs them one at a time) --------------------
def env() -> dict[str, str]:
    e = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "TMPDIR": "/dev/shm/poring-lab-tmp",
         "TZ": "Asia/Bangkok"}  # fmt: skip
    e["PATH"] = str(Path.home() / ".local/bin") + ":" + e.get("PATH", "/usr/bin:/bin")
    return e


class Stop(Exception):  # noqa: N818 -- the series stops (a person first), with the reason
    pass


class Series:
    """The live series (`run`): the setup, the runs, the detect server; its log and record in
    its folder. Never used by the tests (they test the pure parts)."""

    def __init__(self, doc: Mapping[str, Any], folder: Path) -> None:
        self.doc, self.dir = dict(doc), folder
        self.log_path = folder / "series.log"
        self.server: subprocess.Popen[bytes] | None = None
        self.typed: list[str] = []

    def log(self, msg: str) -> None:
        with self.log_path.open("a") as fh:
            fh.write(f"[{time.strftime('%H:%M:%S')}] {msg}\n")
        print(msg, flush=True)

    def sh(self, argv: Sequence[str], timeout: float) -> subprocess.CompletedProcess[str]:
        return subprocess.run(list(argv), cwd=ROOT, env=env(), capture_output=True, text=True,
                              timeout=timeout)  # fmt: skip

    def read(self) -> dict[str, Any]:
        out = self.sh([PY, str(Path(__file__)), "read"], 120)
        last = (out.stdout.strip().splitlines() or ["{}"])[-1]
        try:
            got = json.loads(last)
        except ValueError:
            raise Stop(f"the read failed: {(out.stderr or last)[-200:]}") from None
        self.log(f"read {json.dumps(got)}")
        return dict(got)

    def gm(self, line: str) -> None:
        if not guard_ok([*guard_history(read_guard_state()), line]):
            raise Stop(f"{line!r} would be the chat guard's 3rd identical line in a row")
        out = self.sh([PY, "scripts/crusader.py", "--char", "thief", "gm", "--job", "rogue", line],
                      180)  # fmt: skip
        last = (out.stdout.strip().splitlines() or [""])[-1]
        if '"typed": true' not in last:
            raise Stop(f"gm {line!r} not typed: {(out.stderr or last).strip()[-200:]}")
        self.typed.append(line)
        self.log(f"gm {line!r} typed")

    def setup(self, r: Run) -> None:
        got = self.read()
        w = got.get("weight")
        if w is None or w >= CLEAR_AT:
            self.log(f"{r.label}: the bag reads {w}: clear-bag (etc, use)")
            out_dir = self.dir / f"clear-bag-{r.label}"
            cb = self.sh([PY, "scripts/dungeon_hunt.py", "clear-bag", "--char", "rogue", "--tabs",
                          "etc,use", "--out", str(out_dir)], 900)  # fmt: skip
            if cb.returncode != 0:
                raise Stop(f"clear-bag rc {cb.returncode}: {cb.stdout.strip()[-200:]}")
            self.typed.append("(clear-bag's own lines)")  # its lines are not ours to count
            got = self.read()
        lines_ = warp_lines(2, dh_cells())
        other = lines_[1] if r.warp == lines_[0] else lines_[0]
        warp = pick_warp(r.warp, other, guard_history(read_guard_state()))
        if warp != r.warp:
            self.log(f"{r.label}: {r.warp!r} would be the chat guard's 3rd in a row: {warp!r}")
        self.gm(warp)
        time.sleep(WARP_SETTLE_S)
        t0 = time.monotonic()
        while got.get("map") != MAP or got.get("counts") is None:
            if time.monotonic() - t0 > ARRIVE_S:
                raise Stop(f"after {warp!r} the minimap reads {got.get('map')}, not {MAP}")
            time.sleep(1.0)
            got = self.read()
        lines = topup_lines(got["counts"])
        if isinstance(lines, str):
            raise Stop(lines)
        for ln in lines:
            self.gm(ln)
            time.sleep(0.8)
        cc = self.sh([PY, str(Path(__file__)), "close-chat"], 120)
        last = (cc.stdout.strip().splitlines() or ["{}"])[-1]
        if '"closed": true' not in last:
            raise Stop(f"the chat input did not read closed: {(cc.stderr or last)[-200:]}")
        self.log(f"{r.label}: setup done ({r.warp}; {len(lines)} top-up line(s); chat closed)")

    def serve(self) -> None:
        up = subprocess.run(["docker", "inspect", "-f", "{{.State.Running}}", fr.WORKER],
                            capture_output=True, text=True).stdout.strip()  # fmt: skip
        if up != "true":
            w = self.sh(["python3", "scripts/guarded_build.py", "worker:vision@60"], 900)
            if w.returncode != 0:
                raise Stop(f"the vision worker did not start: {w.stdout[-200:]}")
        cmd = self.sh([PY, "scripts/unit_detector.py", "serve-cmd", "--backend", "openvino",
                       "--seconds", str(int(self.doc["serve_s"]))], 120)  # fmt: skip
        if cmd.returncode != 0 or not cmd.stdout.strip():
            raise Stop(f"the detect server's command did not build: {cmd.stderr[-200:]}")
        fr.SERVE_LOG.unlink(missing_ok=True)  # only the NEW step's start line may match
        with (self.dir / "serve.log").open("wb") as fh:
            self.server = subprocess.Popen(["bash", "-c", cmd.stdout.strip()], cwd=ROOT,
                                           env=env(), stdout=fh, stderr=subprocess.STDOUT,
                                           stdin=subprocess.DEVNULL,
                                           start_new_session=True)  # fmt: skip
        t0 = time.monotonic()
        while time.monotonic() - t0 < fr.LISTEN_WAIT_S:
            time.sleep(1.0)
            text = fr.SERVE_LOG.read_text(errors="replace") if fr.SERVE_LOG.exists() else ""
            if '"listening"' in text and '"precision": "f32"' in text:
                self.log("the detect server listens (once for the series)")
                return
            if "REFUSED" in (self.dir / "serve.log").read_text(errors="replace"):
                raise Stop("the detect server refused")
        raise Stop("the detect server did not listen in time")

    def end_server(self) -> None:
        out = subprocess.run(["docker", "top", fr.WORKER], capture_output=True, text=True).stdout
        for ln in out.splitlines():
            f = ln.split()
            if (
                len(f) > 8
                and f[0] == "bot"
                and f[7:10] == ["python", "-m", "poring_vision.detect_server"]
            ):
                subprocess.run(["kill", "-TERM", f[1]])  # fmt: skip
        if self.server is not None:
            try:
                self.server.wait(timeout=60)
            except subprocess.TimeoutExpired:
                os.killpg(self.server.pid, signal.SIGTERM)
        self.server = None

    def one(self, rr: Mapping[str, Any]) -> dict[str, Any]:
        ps = subprocess.run(["ps", "-eo", "args"], capture_output=True, text=True).stdout
        why = fr.busy_reason(ps.splitlines())
        if why is not None:
            raise Stop(f"{rr['label']}: {why}")
        stop = self.dir / f"{rr['label']}.STOP"
        stop.unlink(missing_ok=True)
        cap = float(self.doc["minutes"]) * 60 + START_GRACE_S
        t0 = time.monotonic()
        with (self.dir / f"{rr['label']}.log").open("wb") as fh:
            proc = subprocess.Popen(list(rr["argv"]), cwd=ROOT, env=env(), stdout=fh,
                                    stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                                    start_new_session=True)  # fmt: skip
        self.log(f"{rr['label']} ({rr['arm']}) started")
        stop_t: float | None = None
        while proc.poll() is None:
            time.sleep(2.0)
            now = time.monotonic()
            if stop_t is None and now - t0 > cap:
                stop.touch()  # the runner's / player's own Stop: its normal end, its way home
                stop_t = now
                self.log(f"{rr['label']}: over its time box: Stop")
            elif stop_t is not None and now - stop_t > STOP_GRACE_S:
                os.killpg(proc.pid, signal.SIGINT)
                self.log(f"{rr['label']}: no end after Stop: SIGINT")
                stop_t = now + 10**9
        rc = proc.returncode
        self.log(f"{rr['label']} ended rc {rc} after {(time.monotonic() - t0) / 60:.1f} min")
        return {"label": rr["label"], "rc": rc, "s": round(time.monotonic() - t0, 1)}

    def run(self) -> int:
        done: list[dict[str, Any]] = []
        try:
            self.serve()
            for rr in self.doc["runs"]:
                if (self.dir / "STOP").exists():
                    raise Stop("the series' STOP file")
                self.setup(Run(**{k: rr[k] for k in ("k", "pair", "arm", "label", "warp")}))
                done.append(self.one(rr))
                (self.dir / "done.json").write_text(json.dumps(done, indent=1) + "\n")
                if done[-1]["rc"] not in (0, 130):  # a refused start (rc 2 / 1): a person first
                    raise Stop(f"{rr['label']} rc {done[-1]['rc']} (its log first)")
        except Stop as e:
            self.log(f"STOPPED: {e} (a person first)")
            return 2
        finally:
            self.end_server()
        self.log("the series is done: stage2_ab.py score --label " + str(self.doc["label"]))
        return 0


# --- the two setup steps that touch the game (child processes) -----------------------------------
def read_now() -> dict[str, Any]:
    """Pixels only (no Agent): the map's name (the minimap), the weight share, the chat input,
    the hotbar counts on the box's keys (dungeon_hunt's own readers)."""
    import dungeon_hunt as dh
    import gm_state
    import hotbar_count as hb
    import minimap_id as mi
    import numpy as np
    import ro_agent as r

    screen = r.Screen()
    try:
        region = r.game_region()
        img = np.ascontiguousarray(np.asarray(r.grab_after(screen, region, r.ns()))[..., :3])
        refs = dh.load_map_refs()
        share = gm_state.weight_share(gm_state._weight(gm_state._frames(screen)))
        tpl = hb.load()
        g = hb.gray(img)
        counts = {k: hb.read_count(g, dh.hotbar_slot(k), tpl) for _i, k, _f, _t in TOPUP}
        return {"map": None if refs is None else mi.read_map(img, refs).map,
                "weight": None if share is None else round(share, 4),
                "chat_open": bool(r.is_state(screen, "chat_open")), "counts": counts}  # fmt: skip
    finally:
        screen.close()


def close_chat() -> dict[str, Any]:
    """Enter on an open, EMPTY chat input (bench.close_chat: the UI gate first), read closed."""
    import bench
    import ro_agent as r

    with r.session("rule:stage2-ab-chat") as (agent, screen):
        agent.wait_for_human()
        bench.close_chat(agent, screen)
        time.sleep(0.5)
        return {"closed": not r.is_state(screen, "chat_open")}


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("plan", "run", "score"):
        p = sub.add_parser(name)
        p.add_argument("--label", required=True, help="the series' name (its runs' labels)")
        if name != "score":
            p.add_argument("--pairs", type=int, default=4)
            p.add_argument(
                "--minutes",
                type=int,
                default=20,
                help="each run's length (the Run config's minutes: 5..600)",
            )
            p.add_argument("--order", choices=("alternate", "ab"), default="alternate")
        else:
            p.add_argument("--json", action="store_true")
    sub.add_parser("read")
    sub.add_parser("close-chat")
    a = ap.parse_args(argv)
    if a.cmd == "read":
        print(json.dumps(read_now()))
        return 0
    if a.cmd == "close-chat":
        print(json.dumps(close_chat()))
        return 0
    folder = SCRATCH / a.label
    if a.cmd == "score":
        doc = json.loads((folder / "series.json").read_text())
        scores = [score_run(r) for r in doc["runs"]]
        v = verdict(scores, float(doc["minutes"]))
        if a.json:
            print(json.dumps({"runs": [s.doc() for s in scores], "verdict": v}, indent=1))
        else:
            print(table(scores))
            print(json.dumps(v, indent=1))
        return 0
    if not 5 <= a.minutes <= 600:
        print("refused before any input: --minutes is the Run config's: 5..600", flush=True)
        return 2
    doc = plan_doc(a.label, a.pairs, a.minutes, a.order, folder)
    if isinstance(doc, str):
        print(doc, flush=True)
        return 2
    if a.cmd == "plan":
        print(json.dumps(doc, indent=1))
        return 0
    folder.mkdir(parents=True, exist_ok=False)  # a series' folder is never reused
    (folder / "series.json").write_text(json.dumps(doc, indent=1) + "\n")
    (folder / "project.json").write_text(project_text(a.minutes))
    (folder / "runner-config.json").write_text(json.dumps({NODE: doc["vals"]}) + "\n")
    return Series(doc, folder).run()


if __name__ == "__main__":
    raise SystemExit(main())
