#!/usr/bin/env python3
"""Section 16's live A/B (docs/planning/live-blocks.md 16; 14.8; Batt 2026-11-15 ~13:0x: "Test it,
and make it work too"): the FIRST REAL EXPERIMENT IN BLOCKS -- no Knife swap on the Christmas
Cookie and the Cookie (they carry no steal worth the swap's time), Batt's Knife swap kept on every
other monster. Alternating runs on the lab's own Rogue on the lab rAthena's xmas_dun02 (player
mode; the MVP alive).

    stage6_ab.py plan  --label L [--pairs N] [--minutes M] [--order alternate|ab]   PURE
    stage6_ab.py run   --label L [--pairs N] [--minutes M] [--order alternate|ab]   LIVE
    stage6_ab.py score --label L [--json]                                            PURE (reads)

THE ARMS differ ONLY in two recipes of the box's monsters tab: both play the checkout's runner
through `flow_play.py play`, run()'s own driver (no hunt tab: 14.12), with the same runner
settings (the boxes' setting blocks and keys, stage2_ab.same_vals):
- B: services/frontend/src/lib/flow/fixtures/project_xmas_dun02.json -- the one box: every
  monster's recipe is the Knife swap (knife_on(); strike(t); wait_steal(t); knife_back();
  wait_kill(t); loot(t));
- C: fixtures/project_xmas_dun02_cookie_noswap.json -- the same box but attack_cookie and
  attack_cookie_xmas, `strike(t); wait_kill(t); loot(t)` (4a's plain shape). At a lock on those
  species the runner strikes with the dagger: no bare phase, no wait for the steal's cue; with
  --bare-ready (the Run config's) the Knife is already on, so the dagger goes on first
  (BareCtl._no_knife, "recipe"), and the next idle moment takes the Knife again. mystcase and
  cruiser keep the swap; a strike that knows no species (the ring scan, a walk / loot SWORD) plays
  the runner's own recipe, the swap, in both arms.
`plan` refuses before any input unless: the two boxes differ ONLY in those two recipes' bodies
(box_difference: C's are B's own strike / wait_kill / loot statements); they take the same runner
settings and keys and the Run config has the fast alarm on; neither has a hunt loop; they give the
runner the same argv and run() the same arguments but box_recipes; B's four recipes are the Knife
swap, C's two cookies the plain shape and its other two B's own, every priority 1; and the runner
accepts both arms' recipes with this Run config (dungeon_hunt.recipes_refused).
The order: "alternate" (the default) is B C, C B, B C, ...; "ab" is B C, B C, ...

THE SETUP before every run: exactly stage2_ab.py's. A STOP file in the series folder
(/dev/shm/poring-lab-tmp/stage6-ab/<label>/STOP) ends the series before its next run.

THE SCORE per run: stage5b_ab's lines (the runner's own session: minutes, deaths, kills, loot
steps, the openers, the steals, the tick pace from the hp_read gaps, the record kinds; a runner
exception from its log) and, per LOCK -- each `recipe` record (the runner asks the box once a
target, at its lock: the species of the box it struck, "?" when the strike knew none) -- what the
runner did there, read from its own records up to the next lock: a Knife strike (`bare` begin ok,
or an opener / unequip AT the strike; never the idle one, by "ready"), its no-knife play (`bare`
recipe, knife false; swap true: the dagger on first), the steals (a swap back on the steal's cue),
the kills after it and the seconds from the lock to the first. The verdict applies BAR (16).
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
from collections import Counter
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import flow_run as fr  # noqa: E402
import stage2_ab as s2  # noqa: E402
import stage3_ab as s3  # noqa: E402
import stage4_ab as s4  # noqa: E402
import stage5_ab as s5  # noqa: E402
import stage5b_ab as s5b  # noqa: E402

VERSION = "9.51"  # dungeon_hunt.BOX_RECIPES_VERSION: the recipe path it measures (no knife_on)
NODE = s2.NODE
PROJECTS = {"B": s4.FIX / "project_xmas_dun02.json",
            "C": s4.FIX / "project_xmas_dun02_cookie_noswap.json"}  # fmt: skip
ARMS = {"B": "the one box: the Knife swap on every monster",
        "C": "no Knife swap on cookie and cookie_xmas (strike, wait_kill, loot)"}  # fmt: skip
SCRATCH = Path("/dev/shm/poring-lab-tmp/stage6-ab")
NO_SWAP = ("cookie", "cookie_xmas")  # the species C fights without the Knife swap
OTHERS = ("mystcase", "cruiser")  # the species both arms fight with it
UNKNOWN = "?"  # a lock whose strike knew no species (the runner's own recipe: the swap)
KNIFE = tuple(s4.TODAY)  # == poring_flow.recipes.KNIFE_SHAPE (test_stage6_ab.py)
PLAIN = ("strike", "wait_kill", "loot")  # == poring_flow.recipes.PLAIN_SHAPE
STEAL_CUES = s3.STEAL_CUES  # a swap back on the steal's own cue: a steal
PLAYED_MIN = s5.PLAYED_MIN
# THE PRE-REGISTERED BAR (live-blocks.md 16, written before any live run): what C must hold vs B
BAR = {
    "min_minutes_share": 0.8,  # a valid run: this share of M minutes, or a weight-home end
    "min_pairs": 3,  # fewer valid pairs: kills / h is not judged
    "plays_min_locks": 5,  # C played its no-swap recipe on at least this many cookie locks
    "plays": "over every run that played: C TRIED the Knife on no cookie / cookie_xmas lock and "
             "played its no-swap recipe (the runner's own record) on at least plays_min_locks of "
             "them; B struck at least one with the Knife (the counter sees one); no lock's answer "
             "was not its arm's plan (recipe_mismatch 0 in both arms)",
    "deaths": "C's deaths <= B's, over EVERY run that played (>= 1 min, or a death)",
    "kills_h_se": 2.0,  # mean paired (C - B) kills / h >= -this x its SE (non-inferiority)
    # C's Knife strikes / h at mystcase + cruiser locks within +-this of B's (valid runs pooled):
    # about 2 SE of the ratio of two 3-run arms, from s5b1-ab / s5b2-ab's 12 runs (16)
    "others_share": 0.25,
    "pace_ms": 5.0,  # 14.7a: C's MEDIAN hp_read gap <= B's + this (valid runs pooled)
    "errors": "no C run ends by an exception of the runner (a traceback in its log, or hunt_end "
              "`error` not a refusal)",
}  # fmt: skip


# --- the plan (PURE) ------------------------------------------------------------------------------
def series(label: str, pairs: int, order: str = "alternate",
           cells: Sequence[tuple[int, int]] | None = None) -> list[s2.Run]:  # fmt: skip
    """PURE: the runs of a series, in order: stage2_ab's alternation, A -> B, B -> C."""
    arm6 = {"A": "B", "B": "C"}
    return [s2.Run(r.k, r.pair, arm6[r.arm], f"{label}-r{r.k:02d}{arm6[r.arm]}", r.warp)
            for r in s2.series(label, pairs, order, cells)]  # fmt: skip


def _step(s: Mapping[str, Any]) -> str:
    return str(s.get("block") if s.get("kind") == "action" else s.get("proc") or s.get("kind"))


def _monsters(d: Mapping[str, Any]) -> dict[str, Any] | None:
    tabs = [t for n in d.get("nodes") or [] for t in n.get("tabs") or []
            if t.get("name") == "monsters"]  # fmt: skip
    return tabs[0] if len(tabs) == 1 else None


def box_difference(b: Mapping[str, Any], c: Mapping[str, Any]) -> str | None:
    """PURE: C is B with attack_cookie's and attack_cookie_xmas's bodies cut to the plain shape --
    B's OWN strike(t), wait_kill(t) and loot(t) statements, in that order -- and nothing else (but
    its name and description); else why not."""
    b, c = json.loads(json.dumps(b)), json.loads(json.dumps(c))
    mb, mc = _monsters(b), _monsters(c)
    if mb is None or mc is None:
        return "a box without exactly one monsters tab"
    for sp in NO_SWAP:
        name = f"attack_{sp}"
        db = next((x for x in mb.get("defs") or [] if x.get("name") == name), None)
        dc = next((x for x in mc.get("defs") or [] if x.get("name") == name), None)
        if db is None or dc is None:
            return f"{'B' if db is None else 'C'} has no {name}"
        if [_step(s) for s in db["body"]] != list(KNIFE):
            return f"B's {name} is not the Knife swap ({', '.join(KNIFE)})"
        if dc["body"] != [db["body"][KNIFE.index(x)] for x in PLAIN]:
            return (f"C's {name} is not B's own strike(t), wait_kill(t), loot(t) (the plain "
                    "shape, the same statements)")  # fmt: skip
        dc["body"] = db["body"]
    for d in (b, c):
        d.pop("name", None)
        d.pop("description", None)
        # the run's length is the harness's (--max-s = minutes * 60), not an arm's: since
        # 2026-11-19 (Batt: no time limit unless set) the ready-made B holds 0 for both, the
        # pinned C its old 7200 s / 120 min
        d.pop("max_runtime_s", None)
        for node in d.get("nodes") or []:
            for tab in node.get("tabs") or []:
                (tab.get("vars") or {}).pop("minutes", None)
    if b != c:
        return "C differs from B in more than its two cookies' recipes (an A/B changes one thing)"
    return None


def recipes_problem(b: Mapping[str, Mapping[str, Any]],
                    c: Mapping[str, Mapping[str, Any]]) -> str | None:  # fmt: skip
    """PURE: why the arms' prepared recipes (run()'s box_recipes) are not this experiment's (None:
    they are): B's four the Knife swap; C's two cookies the plain shape (knife false), its other
    two B's own; every priority 1 (today's order, both arms)."""
    want = sorted({*NO_SWAP, *OTHERS})
    for arm, rs in (("B", b), ("C", c)):
        if sorted(rs) != want:
            return (f"{arm}'s recipes are for {sorted(rs)}, not {want} (a monster on the "
                    "runner's own)")  # fmt: skip
        for sp, r in sorted(rs.items()):
            if r.get("priority") not in (None, 1, 1.0):
                return (f"{arm}'s {r.get('function')} ({sp}) has priority {r.get('priority')}: "
                        "both arms keep today's order (1)")  # fmt: skip
    for sp in want:
        if tuple(b[sp].get("steps") or ()) != KNIFE or b[sp].get("knife") is not True:
            return f"B's recipe for {sp} plays {b[sp].get('steps')}, not the Knife swap"
    for sp in NO_SWAP:
        if tuple(c[sp].get("steps") or ()) != PLAIN or c[sp].get("knife") is not False:
            return f"C's recipe for {sp} plays {c[sp].get('steps')}, not {list(PLAIN)}"
    for sp in OTHERS:
        if dict(c[sp]) != dict(b[sp]):
            return f"C's recipe for {sp} is not B's (the swap stays on the other monsters)"
    return None


class _Asks:
    """The player's hook as the runner's start check needs it (hook.recipe exists)."""

    def recipe(self, species: str | None, why: str) -> dict[str, Any] | None:
        del species, why
        return None


def plan_doc(label: str, pairs: int, minutes: float, order: str,
             folder: Path) -> dict[str, Any] | str:  # fmt: skip
    """PURE but for reads (the fixtures): everything a series will do, before any screen is read
    or any input path opened; a refusal: its words."""
    import dungeon_hunt as dh
    import flow_play as fp

    from poring_flow import project as pj

    vals = s2.same_vals(PROJECTS, minutes)
    if isinstance(vals, str):
        return f"refused before any input: {vals}"
    if not vals.get("alarm_fast"):
        return "refused before any input: the Run config has alarm_fast off (section 11's runs)"
    raw = {arm: json.loads(path.read_text()) for arm, path in PROJECTS.items()}
    why = box_difference(raw["B"], raw["C"])
    if why is not None:
        return f"refused before any input: {why}"
    hashes: dict[str, str] = {}
    arms: dict[str, Any] = {}
    plans: dict[str, Any] = {}
    for arm, path in PROJECTS.items():
        text = s2.project_text(minutes, path)
        h = pj.project_hash(pj.from_json(text))
        prep = fp.prepare(text, NODE, int(round(minutes * 60)), runner_vals={NODE: vals},
                          want_hash=h)  # fmt: skip
        if isinstance(prep, str):
            return f"{arm}: {prep}"
        rp = plans[arm] = prep.runners[NODE]
        hashes[arm] = h
        box = rp.box_kwargs()
        arms[arm] = {"what": ARMS[arm], "project": str(path.relative_to(ROOT)), "project_hash": h,
                     "loop": rp.loop, "box_plays": sorted(rp.plays), "box_roles": rp.box_roles(),
                     "box_model": (box.get("box_model") or {}).get("id"),
                     "box_recipes": box.get("box_recipes") or {},
                     "default_species": list(rp.default_species), "keys": rp.keys}  # fmt: skip
    if arms["B"]["loop"] is not None or arms["C"]["loop"] is not None:
        return ("refused before any input: a box with a hunt loop (both arms play run()'s own "
                "driver: the one box has no hunt tab, 14.12)")  # fmt: skip
    if plans["B"].argv("L", Path("/S"), None) != plans["C"].argv("L", Path("/S"), None):
        return "refused before any input: the two boxes give the runner different argv"
    kb, kc = ({k: v for k, v in plans[x].box_kwargs().items() if k != "box_recipes"}
              for x in ("B", "C"))  # fmt: skip
    if kb != kc or arms["B"]["keys"] != arms["C"]["keys"]:
        return ("refused before any input: the boxes give run() different arguments (but "
                "box_recipes) or keys")  # fmt: skip
    why = recipes_problem(arms["B"]["box_recipes"], arms["C"]["box_recipes"])
    if why is not None:
        return f"refused before any input: {why}"
    for arm in ("B", "C"):
        box = plans[arm].box_kwargs()
        why = dh.recipes_refused(box.get("box_plays") or [], _Asks(), box.get("box_model"),
                                 box.get("box_recipes"), knife_swap=bool(vals.get("knife_swap")),
                                 value_target=bool(vals.get("value_target")))  # fmt: skip
        if why is not None:
            return f"refused before any input: the runner refuses {arm}'s recipes: {why}"
    runs = series(label, pairs, order)
    return {
        "version": VERSION, "label": label, "pairs": pairs, "minutes": minutes, "order": order,
        "arms": arms, "vals": vals, "bar": BAR,
        "serve_s": int(len(runs) * (minutes * 60 + s2.START_GRACE_S + 120) + s2.SERVE_EXTRA_S),
        "runs": [{**asdict(r), "argv": fr.play_command(
            s4.project_file(r.arm, folder), NODE, r.label, folder / f"{r.label}.STOP",
            int(round(minutes * 60)), hashes[r.arm], folder / "runner-config.json")}
            for r in runs],
    }  # fmt: skip


# --- the score (PURE over the sessions' events and logs) -----------------------------------------
@dataclass
class Lock:
    """One lock (a `recipe` record) and what the runner did there, up to the next lock."""

    species: str
    knife: bool | None  # the recipe record's answer (True: the swap)
    mismatch: bool = False
    t_ns: int = 0
    tried: bool = False  # a Knife strike tried at it (begin ok; an opener / unequip at the strike)
    struck: bool = False  # ... and the Knife read on
    plain: bool = False  # the runner's own record of its no-knife play (`bare` recipe)
    dagger_first: bool = False  # ... with the dagger put on first (the Knife was on: --bare-ready)
    steals: int = 0  # swaps back on the steal's cue
    kills: int = 0  # kill records after it (before the next lock)
    kill_s: float | None = None  # seconds from the lock to the first of them


def locks_of(events: Iterable[Mapping[str, Any]]) -> tuple[list[Lock], int]:
    """PURE: one runner session's locks, in order, and the kills before its first lock."""
    out: list[Lock] = []
    before = 0
    cur: Lock | None = None
    for e in events:
        k = e.get("kind")
        t = int(e.get("t_ns") or 0)
        if k == "recipe":
            cur = Lock(str(e.get("species") or UNKNOWN), e.get("knife"), bool(e.get("mismatch")), t)
            out.append(cur)
        elif k == "kill":
            if cur is None:
                before += 1
                continue
            cur.kills += 1
            if cur.kill_s is None and t and cur.t_ns:
                cur.kill_s = round((t - cur.t_ns) / 1e9, 2)
        elif k == "bare" and cur is not None:
            what, ok = e.get("what"), bool(e.get("ok"))
            if what == "begin" and ok:  # --bare-ready: already bare, the phase begins at it
                cur.tried = cur.struck = True
            elif what in ("opener", "unequip") and e.get("by") != "ready":  # a swap at the strike
                cur.tried = True
                cur.struck = cur.struck or ok
            elif what == "recipe" and e.get("knife") is False:  # BareCtl._no_knife
                cur.plain = True
                cur.dagger_first = cur.dagger_first or bool(e.get("swap"))
            elif (what == "equip" and ok and not e.get("pending")
                  and e.get("why") in STEAL_CUES):  # fmt: skip
                cur.steals += 1
    return out, before


def _add(d: dict[str, int], key: str, n: int = 1) -> None:
    d[key] = d.get(key, 0) + n


@dataclass
class Score6(s5b.Score5b):
    locks_sp: dict[str, int] = field(default_factory=dict)  # locks by species ("?": none known)
    tries_sp: dict[str, int] = field(default_factory=dict)  # ... a Knife strike tried at them
    knife_sp: dict[str, int] = field(default_factory=dict)  # ... the Knife read on
    plain_sp: dict[str, int] = field(default_factory=dict)  # ... the runner's no-knife play
    dagger_first: int = 0  # no-knife plays with the dagger put on first
    mismatch_locks: int = 0  # locks whose answer was not the arm's plan (the recipe record)
    steals_sp: dict[str, int] = field(default_factory=dict)  # steals by the lock's species
    kills_sp: dict[str, int] = field(default_factory=dict)  # kills by the lock before ("-": none)
    kill_s: dict[str, list[float]] = field(default_factory=dict)  # lock -> first kill, by species

    def doc(self) -> dict[str, Any]:
        d = {k: v for k, v in super().doc().items() if k != "kill_s"}
        return {**d, "kill_s_median": {sp: s3._median(v) for sp, v in sorted(self.kill_s.items())}}


def score_locks(sc: Score6, events: Iterable[Mapping[str, Any]]) -> None:
    """PURE: add one runner session's locks (locks_of) to the run's score."""
    locks, before = locks_of(events)
    if before:
        _add(sc.kills_sp, "-", before)
    for lk in locks:
        sp = lk.species
        _add(sc.locks_sp, sp)
        if lk.tried:
            _add(sc.tries_sp, sp)
        if lk.struck:
            _add(sc.knife_sp, sp)
        if lk.plain:
            _add(sc.plain_sp, sp)
        sc.dagger_first += int(lk.dagger_first)
        sc.mismatch_locks += int(lk.mismatch)
        if lk.steals:
            _add(sc.steals_sp, sp, lk.steals)
        if lk.kills:
            _add(sc.kills_sp, sp, lk.kills)
        if lk.kill_s is not None:
            sc.kill_s.setdefault(sp, []).append(lk.kill_s)


def score_run(r: Mapping[str, Any], folder: Path, demo: Path = s2.DEMO) -> Score6:
    """Reads (no screen): one run's sessions by its label and its log."""
    base = s5b.score_run(r, folder, demo)
    sc = Score6(**{k: getattr(base, k) for k in base.__dataclass_fields__})
    for d in sorted(demo.glob(f"*-{r['label']}-hunt*")):
        if (d / "events.jsonl").is_file():
            score_locks(sc, s2.read_events(d / "events.jsonl"))
    return sc


def steal_values(path: Path | None = None, map_: str = s2.MAP) -> dict[str, float]:
    """Reads data/econ/maps.json (value_target's file: built locally from the lab server's tables,
    never committed): the lab's value of ONE stolen item per species, zeny at Overcharge -- each
    item drawn in proportion to its drop rate (a steal draws from the drop table; cards cannot be
    stolen): sum(p x sell_oc) / sum(p). {} when the file or the map is missing: the report then
    gives the counts only."""
    import value_target as vt

    path = vt.MAPS_JSON if path is None else path
    if not path.is_file():
        return {}
    m = json.loads(path.read_text()).get("maps", {}).get(map_) or {}
    out: dict[str, float] = {}
    for sp in (m.get("species") or {}).values():
        drops = [d for d in sp.get("drops") or [] if str(d.get("type")) != "Card"]
        den = sum(float(d.get("p") or 0) for d in drops)
        key = str(sp.get("aegis") or "").lower()
        if key and den > 0:
            num = sum(float(d.get("p") or 0) * float(d.get("sell_oc") or 0) for d in drops)
            out[key] = round(num / den, 1)
    return out


def _sum(arm: Sequence[Score6], attr: str, sps: Iterable[str]) -> int:
    keys = tuple(sps)
    return sum(int(getattr(s, attr).get(sp, 0)) for s in arm for sp in keys)


def plays_line(played: Mapping[str, Sequence[Score6]], bar: Mapping[str, Any]) -> dict[str, Any]:
    """PURE: the plays line (BAR["plays"]) over every run that played."""
    out: dict[str, Any] = {
        "C_cookie_locks": _sum(played["C"], "locks_sp", NO_SWAP),
        "C_knife_tries": _sum(played["C"], "tries_sp", NO_SWAP),
        "C_plain_locks": _sum(played["C"], "plain_sp", NO_SWAP),
        "B_cookie_locks": _sum(played["B"], "locks_sp", NO_SWAP),
        "B_knife_locks": _sum(played["B"], "knife_sp", NO_SWAP),
        "mismatch": {x: sum(s.mismatch_locks for s in played[x]) for x in ("B", "C")},
    }  # fmt: skip
    if not played["B"] or not played["C"]:
        out["pass"] = None  # an arm never played: nothing to judge
        return out
    out["pass"] = (out["C_knife_tries"] == 0
                   and out["C_plain_locks"] >= int(bar["plays_min_locks"])
                   and out["B_knife_locks"] >= 1
                   and not any(out["mismatch"].values()))  # fmt: skip
    return out


def _paired(good: Sequence[Mapping[str, Score6]], f: Callable[[Score6], float], se_k: float,
            min_pairs: int) -> dict[str, Any]:  # fmt: skip
    d = [p["C"].per_h(f(p["C"])) - p["B"].per_h(f(p["B"])) for p in good]
    if not d:
        return {"pass": None}
    mean_d = statistics.fmean(d)
    se = statistics.stdev(d) / math.sqrt(len(d)) if len(d) > 1 else float("inf")
    return {"mean_diff_h": round(mean_d, 1), "se_h": None if math.isinf(se) else round(se, 1),
            "pairs": [round(x, 1) for x in d],
            "pass": None if len(good) < min_pairs else mean_d >= -se_k * se}  # fmt: skip


def verdict(scores: Sequence[Score6], minutes: float, bar: Mapping[str, Any] = BAR,
            values: Mapping[str, float] | None = None) -> dict[str, Any]:  # fmt: skip
    """PURE: the pre-registered bar (live-blocks.md 16). ``values``: steal_values' (the report's
    zeny line only)."""
    ok_min = minutes * float(bar["min_minutes_share"])
    valid = {s.label for s in scores if s.found and (
        s.minutes >= ok_min or str(s.end or "").startswith("weight_home"))}  # fmt: skip
    played = {x: [s for s in scores if s.arm == x and s.found
                  and (s.minutes >= PLAYED_MIN or s.deaths)] for x in ("B", "C")}  # fmt: skip
    pairs: dict[int, dict[str, Score6]] = {}
    for s in scores:
        pairs.setdefault(s.pair, {})[s.arm] = s
    good = [p for p in pairs.values() if set(p) == {"B", "C"}
            and p["B"].label in valid and p["C"].label in valid]  # fmt: skip
    arm = {x: [s for s in scores if s.arm == x and s.label in valid] for x in ("B", "C")}
    out: dict[str, Any] = {"pairs_valid": len(good), "pairs": len(pairs),
                           "invalid": sorted({s.label for s in scores} - valid),
                           "played": {x: len(played[x]) for x in ("B", "C")}}  # fmt: skip
    deaths = {x: sum(s.deaths for s in played[x]) for x in ("B", "C")}
    errs = [f"{s.label}: {s.error}" for s in scores if s.arm == "C" and s.error]
    lines: dict[str, Any] = {
        "plays": plays_line(played, bar),
        "deaths": {**deaths, "pass": deaths["C"] <= deaths["B"]},
        "kills_h": _paired(good, lambda s: s.kills, float(bar["kills_h_se"]),
                           int(bar["min_pairs"])),
        "errors": {"C": errs, "B": [f"{s.label}: {s.error}" for s in scores
                                    if s.arm == "B" and s.error], "pass": not errs},
    }  # fmt: skip
    hours = {x: sum(s.minutes for s in arm[x]) / 60.0 for x in ("B", "C")}

    def rate(x: str, f: Callable[[Score6], float]) -> float | None:
        return round(sum(f(s) for s in arm[x]) / hours[x], 1) if hours[x] > 0 else None

    ob = rate("B", lambda s: _sum([s], "knife_sp", OTHERS))
    oc = rate("C", lambda s: _sum([s], "knife_sp", OTHERS))
    share = float(bar["others_share"])
    lines["others_h"] = {"B": ob, "C": oc, "share": share, "pass": None if ob is None or oc is None
                         else (abs(oc - ob) <= share * ob if ob > 0 else oc == 0)}  # fmt: skip
    pa = {x: s5b.pace([g for s in arm[x] for g in s.gaps_ms]) for x in ("B", "C")}
    mb, mc = pa["B"]["median"], pa["C"]["median"]
    lines["pace"] = {**pa, "pass": None if mb is None or mc is None
                     else mc <= mb + float(bar["pace_ms"])}  # fmt: skip
    lines["report"] = report(scores, arm, good, rate, dict(values or {}))
    judged = [v["pass"] for k, v in lines.items() if k != "report"]
    if False in judged:
        v_ = "FAIL"
    elif None in judged:
        v_ = "INCONCLUSIVE"
    else:
        v_ = "PASS"
    return {**out, "lines": lines, "verdict": v_}


def report(scores: Sequence[Score6], arm: Mapping[str, Sequence[Score6]],
           good: Sequence[Mapping[str, Score6]], rate: Callable[..., float | None],
           values: Mapping[str, float]) -> dict[str, Any]:  # fmt: skip
    """PURE: the report-only lines (valid runs pooled; per hour)."""
    sps = (*NO_SWAP, *OTHERS, UNKNOWN)

    def by_sp(attr: str, keys: Sequence[str] = sps) -> dict[str, dict[str, float | None]]:
        return {x: {sp: rate(x, lambda s, sp=sp: getattr(s, attr).get(sp, 0)) for sp in keys}
                for x in ("B", "C")}  # fmt: skip

    steals = by_sp("steals_sp")
    z: dict[str, dict[str, float]] = {x: {} for x in ("B", "C")}
    for x in ("B", "C"):
        for sp in NO_SWAP:
            n = steals[x].get(sp)
            if sp in values and n is not None:
                z[x][sp] = round(n * values[sp])
    zeny = {"value_per_steal": {sp: values.get(sp) for sp in (*NO_SWAP, *OTHERS)},
            "cookie_steal_z_h": z,
            "lost_z_h": round(sum(z["B"].values()) - sum(z["C"].values()))
            if values and all(z[x] for x in ("B", "C")) else None}  # fmt: skip
    kill_s = {x: {sp: {"median": s3._median([v for s in arm[x] for v in s.kill_s.get(sp, [])]),
                       "n": sum(len(s.kill_s.get(sp, [])) for s in arm[x])} for sp in sps}
              for x in ("B", "C")}  # fmt: skip
    return {
        "steals_h": steals,
        "steal_zeny": zeny,
        "kill_s_from_lock": kill_s,
        "kills_h_species": by_sp("kills_sp", (*sps, "-")),
        "locks_h": by_sp("locks_sp"),
        "knife_h": by_sp("knife_sp"),
        "plain_h": by_sp("plain_sp"),
        "dagger_first_h": {x: rate(x, lambda s: s.dagger_first) for x in ("B", "C")},
        "loot_h": {x: rate(x, lambda s: s.loot_steps) for x in ("B", "C")},
        "loot_h_paired": {k: v for k, v in _paired(good, lambda s: s.loot_steps, 2.0, 1).items()
                          if k != "pass"},  # fmt: skip
        "kills_h": {x: rate(x, lambda s: s.kills) for x in ("B", "C")},
        "openers_h": {x: rate(x, lambda s: s.openers) for x in ("B", "C")},
        "steals_h_all": {x: rate(x, lambda s: s.steals) for x in ("B", "C")},
        "potions_h": {x: rate(x, lambda s: s.potions) for x in ("B", "C")},
        "flies_h": {x: rate(x, lambda s: s.flies_no_end) for x in ("B", "C")},
        "hp_low": {x: min((s.hp_low for s in arm[x] if s.hp_low is not None), default=None)
                   for x in ("B", "C")},
        "ends": {x: [s.end for s in scores if s.arm == x] for x in ("B", "C")},
        "report_only": True,
    }  # fmt: skip


def table(scores: Sequence[Score6]) -> str:
    """PURE: the per-run table (plain text, the report's): ck = cookie + cookie_xmas locks."""
    head = (f"{'run':<20}{'arm':<4}{'min':>6}{'death':>6}{'kills/h':>9}{'loot/h':>8}"
            f"{'ck':>4}{'ckKn':>5}{'ckPl':>5}{'ckSt':>5}{'othKn/h':>9}{'tick':>7}{'err':>5}"
            "  end")  # fmt: skip
    rows = [head]
    for s in scores:
        p = s5b.pace(s.gaps_ms)
        rows.append(
            f"{s.label:<20}{s.arm:<4}{s.minutes:>6.1f}{s.deaths:>6}{s.per_h(s.kills):>9.1f}"
            f"{s.per_h(s.loot_steps):>8.1f}{_sum([s], 'locks_sp', NO_SWAP):>4}"
            f"{_sum([s], 'tries_sp', NO_SWAP):>5}{_sum([s], 'plain_sp', NO_SWAP):>5}"
            f"{_sum([s], 'steals_sp', NO_SWAP):>5}"
            f"{s.per_h(_sum([s], 'knife_sp', OTHERS)):>9.1f}"
            f"{p['median'] if p['median'] is not None else '-':>7}"
            f"{'yes' if s.error else '-':>5}  {s.end or '-'}"
        )
    return "\n".join(rows)


def species_mix(scores: Sequence[Score6]) -> dict[str, dict[str, int]]:
    """PURE: the locks by species per arm (every run), for the report's first look."""
    out: dict[str, Counter[str]] = {"B": Counter(), "C": Counter()}
    for s in scores:
        out.setdefault(s.arm, Counter()).update(s.locks_sp)
    return {x: dict(sorted(c.items())) for x, c in out.items()}


class Series6(s2.Series):
    """stage2_ab's live series (the setup, the detect server, one run at a time), for B / C."""

    score_cmd = "stage6_ab.py"


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("plan", "run", "score"):
        p = sub.add_parser(name)
        p.add_argument("--label", required=True, help="the series' name (its runs' labels)")
        if name != "score":
            p.add_argument("--pairs", type=int, default=3)
            p.add_argument("--minutes", type=int, default=20,
                           help="each run's length (the Run config's minutes: 5..600)")  # fmt: skip
            p.add_argument("--order", choices=("alternate", "ab"), default="alternate")
        else:
            p.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    folder = SCRATCH / a.label
    if a.cmd == "score":
        doc = json.loads((folder / "series.json").read_text())
        scores = [score_run(r, folder) for r in doc["runs"]]
        v = verdict(scores, float(doc["minutes"]), values=steal_values())
        if a.json:
            print(json.dumps({"runs": [s.doc() for s in scores], "verdict": v}, indent=1))
        else:
            print(table(scores))
            print(json.dumps({k: x for k, x in v.items() if k != "lines"} | {
                "lines": {k: x for k, x in v.get("lines", {}).items() if k != "report"},
                "locks": species_mix(scores)}, indent=1))  # fmt: skip
            print(json.dumps({"report": v.get("lines", {}).get("report")}, indent=1))
        return 0
    if not 5 <= a.minutes <= 600:
        print("refused before any input: --minutes is the Run config's: 5..600", flush=True)
        return 2
    got = plan_doc(a.label, a.pairs, a.minutes, a.order, folder)
    if isinstance(got, str):
        print(got, flush=True)
        return 2
    if a.cmd == "plan":
        print(json.dumps(got, indent=1))
        return 0
    folder.mkdir(parents=True, exist_ok=False)  # a series' folder is never reused
    (folder / "series.json").write_text(json.dumps(got, indent=1) + "\n")
    for arm, path in PROJECTS.items():
        s4.project_file(arm, folder).write_text(s2.project_text(a.minutes, path))
    (folder / "runner-config.json").write_text(json.dumps({NODE: got["vals"]}) + "\n")
    return Series6(got, folder).run()


if __name__ == "__main__":
    raise SystemExit(main())
