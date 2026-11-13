#!/usr/bin/env python3
"""LIVE BLOCKS STAGE 4a's A/B (docs/planning/live-blocks.md 3.4, the pre-registered bar there): the
STAGE-3 box (B3) against the STAGE-4a box (B4), both through the live block player, alternating runs
of the same length on xmas_dun02, the same setup before every run, one detect server for the whole
series. Batt 2026-11-13: "break the core into functions, e.g. attack_myst_case, attack_cookie,
because in the future each monster may get a different skill or killing technique" -- B4 names its
trained data (use_model("xmas02")) and writes TODAY's technique as one recipe per monster, which the
runner asks at each lock and plays with its own code; B3 leaves the choice to the runner. B4 is an
EQUIVALENCE check: the hunt must play the same.

    stage4_ab.py plan  --label L [--pairs N] [--minutes M] [--order alternate|ab]   PURE
    stage4_ab.py run   --label L [--pairs N] [--minutes M] [--order alternate|ab]   LIVE
    stage4_ab.py score --label L [--json]                                            PURE (reads)

A sibling of scripts/stage3_ab.py (and through it scripts/stage2_ab.py), sharing their code (the
setup steps, the detect server, the run of one arm, the runner's score, the Knife's score): only
the arms, the recipe lines and the bar are its own.

THE ARMS (the same runner settings for both: the Run config, the boxes' five keys over it -- the
same keys, checked -- and --minutes M), both `flow_play.py play` on the node xmas_dun02:
- B3: services/frontend/src/lib/flow/fixtures/project_xmas_dun02_stage3.json (the box as stage 3
  left it: no use_model, no monsters tab -- the runner's own model choice and technique);
- B4: services/frontend/src/lib/flow/fixtures/project_xmas_dun02.json (the ready-made box: also
  use_model("xmas02") and the monsters tab, every recipe today's technique: plan refuses a B4 that
  is not -- a recipe without the Knife swap, a priority other than 1 -- since that is the next
  experiment, B4 vs B4', not this one).
The order: "alternate" (the default) is B3 B4, B4 B3, ... ; "ab" is B3 B4, B3 B4, ...

THE SETUP before every run: exactly stage2_ab.py's (the read; clear-bag at 40 %; the lab GM's
@warp alternating PATROL_START's two cells; @item under a floor; the chat input closed and read
closed), as child processes, never beside a run. A STOP file in the series folder
(/dev/shm/poring-lab-tmp/stage4-ab/<label>/STOP) ends the series before its next run.

THE SCORE per run: stage3_ab's (stage 2's lines, the Knife, the exits, the weight, the box's calls)
and, from the same runner session, the recipes (each lock's `recipe`: its species, whether the
Knife was swapped, a mismatch between the hook's answer and the run's plan) and the species mix of
the strikes (the runner's own box_target record: the struck box's species, the same reader for
both arms). The verdict applies BAR (live-blocks.md 3.4).
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

VERSION = "9.51"  # dungeon_hunt.BOX_RECIPES_VERSION: the stage it measures
NODE = s2.NODE
FIX = ROOT / "services/frontend/src/lib/flow/fixtures"
PROJECTS = {"B3": FIX / "project_xmas_dun02_stage3.json", "B4": FIX / "project_xmas_dun02.json"}
SCRATCH = Path("/dev/shm/poring-lab-tmp/stage4-ab")
TODAY = ("knife_on", "strike", "wait_steal", "knife_back", "wait_kill", "loot")
# THE PRE-REGISTERED BAR (live-blocks.md 3.4, written before any live run): what B4 must hold vs B3
BAR = {
    "min_minutes_share": 0.8,  # a valid run: this share of M minutes, or a weight-home end
    "min_pairs": 3,  # fewer valid pairs: kills / steals / loot per hour are not judged
    "deaths": "B4's deaths <= B3's (the series' totals)",
    "kills_h_se": 2.0,  # mean paired (B4 - B3) kills / h >= -this x its standard error
    "steals_h_se": 2.0,  # the same rule for the steals (the swaps back on the steal's cue)
    "loot_h_se": 2.0,  # the same rule for the loot steps
    "openers_h_share": 0.20,  # B4's openers / h within +-20 % of B3's (the series' rates)
    "recipes": "every B4 run that struck asked the box at its locks (a recipe event a lock), no "
    "lock's answer differed from the run's plan (recipe_mismatch 0), and B3 asked none",
}


# --- the plan (PURE) ------------------------------------------------------------------------------
def series(label: str, pairs: int, order: str = "alternate",
           cells: Sequence[tuple[int, int]] | None = None) -> list[s2.Run]:  # fmt: skip
    """PURE: the runs of a series, in order: stage2_ab's alternation, A -> B3, B -> B4."""
    arm4 = {"A": "B3", "B": "B4"}
    return [s2.Run(r.k, r.pair, arm4[r.arm], f"{label}-r{r.k:02d}{arm4[r.arm]}", r.warp)
            for r in s2.series(label, pairs, order, cells)]  # fmt: skip


def project_file(arm: str, folder: Path) -> Path:
    return folder / f"project-{arm}.json"


def run_vals(minutes: float, config_dir: Path = fr.CONFIG_DIR) -> dict[str, Any] | str:
    """The runner settings BOTH arms take (stage2_ab.run_vals on each box): the same, or refused."""
    from poring_flow import project as pj

    keys = {}
    for arm, path in PROJECTS.items():
        rk = pj.runner_keys(pj.from_json(path.read_text()), NODE)
        if rk.keys is None:
            return f"{arm}'s keys: {'; '.join(rk.problems)}"
        keys[arm] = rk.keys
    if keys["B3"] != keys["B4"]:
        return f"the two boxes' keys differ: B3 {keys['B3']}, B4 {keys['B4']}"
    vals, _src, _ks, why = fr.run_values(fr.FLOWS[s2.FLOW_ID], keys["B4"], config_dir)
    if why:
        return why
    return {**vals, "minutes": minutes}


def commands(r: s2.Run, folder: Path, minutes: float, hashes: Mapping[str, str]) -> list[str]:
    """PURE: the run's argv -- the player of its arm's box (flow_run.play_command), the same runner
    config for both."""
    stop = folder / f"{r.label}.STOP"
    return fr.play_command(project_file(r.arm, folder), NODE, r.label, stop,
                           int(round(minutes * 60)), hashes[r.arm],
                           folder / "runner-config.json")  # fmt: skip


def not_today(recipes: Mapping[str, Mapping[str, Any]], default: Sequence[str]) -> str | None:
    """PURE: why B4's recipes are not TODAY's technique (None: they are) -- every recipe the
    Knife swap in the runner's own order, its priority 1 or none; a monster without one plays the
    runner's own recipe, today's too."""
    for sp, r in sorted(recipes.items()):
        if tuple(r.get("steps") or ()) != TODAY:
            return f"{r.get('function')} ({sp}) plays {r.get('steps')}, not today's {list(TODAY)}"
        if r.get("priority") not in (None, 1, 1.0):
            return f"{r.get('function')} ({sp}) has priority {r.get('priority')}: today's is 1"
    if not recipes:
        return "B4 has no recipe at all (nothing for the hunt core to ask)"
    del default  # the runner's own recipe IS today's: a monster without a function is today's
    return None


def plan_doc(label: str, pairs: int, minutes: float, order: str, folder: Path,
             config_dir: Path = fr.CONFIG_DIR) -> dict[str, Any] | str:  # fmt: skip
    """PURE but for reads (the config, the fixtures): everything a series will do, before any
    screen is read or any input path opened; a refusal: its words."""
    import flow_play as fp

    from poring_flow import project as pj

    vals = run_vals(minutes, config_dir)
    if isinstance(vals, str):
        return f"refused before any input: {vals}"
    hashes: dict[str, str] = {}
    arms: dict[str, Any] = {}
    for arm, path in PROJECTS.items():
        text = s2.project_text(minutes, path)
        h = pj.project_hash(pj.from_json(text))
        prep = fp.prepare(text, NODE, int(round(minutes * 60)), runner_vals={NODE: vals},
                          want_hash=h)  # fmt: skip
        if isinstance(prep, str):
            return f"{arm}: {prep}"
        rp = prep.runners[NODE]
        hashes[arm] = h
        box = rp.box_kwargs()
        arms[arm] = {"project": str(path.relative_to(ROOT)), "project_hash": h,
                     "box_plays": sorted(rp.plays), "box_events": list(rp.events),
                     "box_roles": rp.box_roles(),
                     "box_model": (box.get("box_model") or {}).get("id"),
                     "box_recipes": box.get("box_recipes") or {},
                     "default_species": list(rp.default_species)}  # fmt: skip
    if arms["B3"]["box_model"] or arms["B3"]["box_recipes"]:
        return "refused before any input: B3 is not the stage-3 box (it names a model or recipes)"
    if not arms["B3"]["box_roles"]:
        return "refused before any input: B3 plays none of stage 3's functions"
    if arms["B4"]["box_model"] is None:
        return "refused before any input: B4 names no model (use_model)"
    why = not_today(arms["B4"]["box_recipes"], arms["B4"]["default_species"])
    if why:
        return (
            f"refused before any input: B4 is not today's technique ({why}): this A/B is the "
            "equivalence check; a changed technique is the next experiment (B4 vs B4')"
        )
    if arms["B4"]["box_roles"] != arms["B3"]["box_roles"]:
        return "refused before any input: B3 and B4 play different stage-3 functions"
    runs = series(label, pairs, order)
    return {
        "version": VERSION, "label": label, "pairs": pairs, "minutes": minutes, "order": order,
        "arms": arms, "vals": vals, "bar": BAR,
        "serve_s": int(len(runs) * (minutes * 60 + s2.START_GRACE_S + 120) + s2.SERVE_EXTRA_S),
        "runs": [{**asdict(r), "argv": commands(r, folder, minutes, hashes)} for r in runs],
    }  # fmt: skip


# --- the score (PURE over the sessions' events) ---------------------------------------------------
@dataclass
class Score4(s3.Score3):
    recipes: int = 0  # the locks that asked the box (the runner's `recipe` records)
    recipe_species: dict[str, int] = field(default_factory=dict)  # each lock's species ("?": none)
    recipe_no_knife: int = 0  # locks struck without the Knife swap (a recipe without knife_on)
    recipe_mismatch: int = 0  # locks whose hook answer was not the run's plan
    struck_species: dict[str, int] = field(default_factory=dict)  # box_target strikes by species

    def doc(self) -> dict[str, Any]:
        return {**super().doc(), "loot_h": round(self.per_h(self.loot_steps), 1),
                "openers_h": round(self.per_h(self.openers), 1)}  # fmt: skip


def score_recipes(sc: Score4, events: Iterable[Mapping[str, Any]]) -> None:
    """PURE: one runner session's recipe records and the species of its box strikes."""
    asked: Counter[str] = Counter(sc.recipe_species)
    struck: Counter[str] = Counter(sc.struck_species)
    for e in events:
        k = e.get("kind")
        if k == "recipe":
            sc.recipes += 1
            asked[str(e.get("species") or "?")] += 1
            sc.recipe_no_knife += int(e.get("knife") is False)
            sc.recipe_mismatch += int(bool(e.get("mismatch")))
        elif k == "box_target" and e.get("struck"):
            sp = (e.get("pick") or {}).get("species") if isinstance(e.get("pick"), dict) else None
            struck[str(sp or "?")] += 1
    sc.recipe_species, sc.struck_species = dict(asked), dict(struck)


def score_run(r: Mapping[str, Any], demo: Path = s2.DEMO) -> Score4:
    """Reads (no screen): one run's sessions by its label (the hunt cores' and the player's)."""
    label, arm = str(r["label"]), str(r["arm"])
    sc = Score4(label, arm, int(r["pair"]))
    for d in sorted(demo.glob(f"*-{label}-hunt*")):
        if (d / "events.jsonl").is_file():
            ev = s2.read_events(d / "events.jsonl")
            s2.score_runner(sc, ev)
            s3.score_knife(sc, ev)
            score_recipes(sc, ev)
    for d in sorted(demo.glob(f"*-play-{label}")):
        if (d / "events.jsonl").is_file():
            s2.score_player(sc, s2.read_events(d / "events.jsonl"))
    return sc


def _paired(good: list[dict[str, Score4]], f: Callable[[Score4], float], se_k: float,
            min_pairs: int) -> dict[str, Any]:  # fmt: skip
    d = [p["B4"].per_h(f(p["B4"])) - p["B3"].per_h(f(p["B3"])) for p in good]
    mean_d = statistics.fmean(d)
    se = statistics.stdev(d) / math.sqrt(len(d)) if len(d) > 1 else float("inf")
    out: dict[str, Any] = {"mean_diff_h": round(mean_d, 1),
                           "se_h": None if math.isinf(se) else round(se, 1),
                           "pairs": [round(x, 1) for x in d]}  # fmt: skip
    out["pass"] = None if len(good) < min_pairs else mean_d >= -se_k * se
    return out


def verdict(scores: Sequence[Score4], minutes: float,
            bar: Mapping[str, Any] = BAR) -> dict[str, Any]:  # fmt: skip
    """PURE: the pre-registered bar (live-blocks.md 3.4) over the valid pairs."""
    ok_min = minutes * float(bar["min_minutes_share"])
    valid = {s.label for s in scores if s.found and (
        s.minutes >= ok_min or str(s.end or "").startswith("weight_home"))}  # fmt: skip
    pairs: dict[int, dict[str, Score4]] = {}
    for s in scores:
        pairs.setdefault(s.pair, {})[s.arm] = s
    good = [p for p in pairs.values() if set(p) == {"B3", "B4"}
            and p["B3"].label in valid and p["B4"].label in valid]  # fmt: skip
    b3, b4 = [p["B3"] for p in good], [p["B4"] for p in good]
    out: dict[str, Any] = {"pairs_valid": len(good), "pairs": len(pairs),
                           "invalid": sorted({s.label for s in scores} - valid)}  # fmt: skip
    if not good:
        return {**out, "verdict": "INCONCLUSIVE", "why": "no valid pair"}
    hours = {x: sum(s.minutes for s in arm) / 60.0 for x, arm in (("B3", b3), ("B4", b4))}

    def rate(arm: list[Score4], f: Callable[[Score4], float], x: str) -> float:
        return sum(f(s) for s in arm) / hours[x] if hours[x] > 0 else 0.0

    mp = int(bar["min_pairs"])
    deaths = (sum(s.deaths for s in b3), sum(s.deaths for s in b4))
    op3, op4 = rate(b3, lambda s: s.openers, "B3"), rate(b4, lambda s: s.openers, "B4")
    share = float(bar["openers_h_share"])
    struck4 = [s for s in b4 if s.openers > 0 or s.struck_species]
    lines: dict[str, Any] = {
        "deaths": {"B3": deaths[0], "B4": deaths[1], "pass": deaths[1] <= deaths[0]},
        "kills_h": _paired(good, lambda s: s.kills, float(bar["kills_h_se"]), mp),
        "steals_h": _paired(good, lambda s: s.steals, float(bar["steals_h_se"]), mp),
        "loot_h": _paired(good, lambda s: s.loot_steps, float(bar["loot_h_se"]), mp),
        "openers_h": {"B3": round(op3, 1), "B4": round(op4, 1),
                      "pass": abs(op4 - op3) <= share * op3 if op3 > 0 else op4 == 0},
        "recipes": {"B4_asked": sum(s.recipes for s in b4), "B3_asked": sum(s.recipes for s in b3),
                    "B4_mismatch": sum(s.recipe_mismatch for s in b4),
                    "pass": all(s.recipes > 0 for s in struck4)
                    and not any(s.recipe_mismatch for s in b4)
                    and not any(s.recipes for s in b3)},
    }  # fmt: skip

    def mix(arm: list[Score4], f: Callable[[Score4], Mapping[str, int]]) -> dict[str, int]:
        c: Counter[str] = Counter()
        for s in arm:
            c.update(f(s))
        return dict(sorted(c.items()))

    lines["report"] = {
        "struck_species": {"B3": mix(b3, lambda s: s.struck_species),
                           "B4": mix(b4, lambda s: s.struck_species)},
        "recipe_species_B4": mix(b4, lambda s: s.recipe_species),
        "recipe_no_knife_B4": sum(s.recipe_no_knife for s in b4),
        "steal_share": {x: s3._share(sum(s.steals for s in arm), sum(s.openers for s in arm))
                        for x, arm in (("B3", b3), ("B4", b4))},
        "steal_s_median": {x: s3._median([v for s in arm for v in s.steal_s])
                           for x, arm in (("B3", b3), ("B4", b4))},
        "runs": {"B3": [s.doc() for s in b3], "B4": [s.doc() for s in b4]},
        "report_only": True}  # fmt: skip
    judged = [x["pass"] for x in lines.values() if "pass" in x]
    if False in judged:
        v = "FAIL"
    elif any(lines[k]["pass"] is None for k in ("kills_h", "steals_h", "loot_h")):
        v = "INCONCLUSIVE"
    else:
        v = "PASS"
    return {**out, "lines": lines, "verdict": v}


def table(scores: Sequence[Score4]) -> str:
    """PURE: the per-run table (plain text, the report's)."""
    head = (
        f"{'run':<22}{'arm':<4}{'min':>6}{'death':>6}{'kills/h':>9}{'steal/h':>9}"
        f"{'loot/h':>8}{'open/h':>8}{'asked':>6}{'odd':>4}  end"
    )
    rows = [head]
    for s in scores:
        rows.append(
            f"{s.label:<22}{s.arm:<4}{s.minutes:>6.1f}{s.deaths:>6}"
            f"{s.per_h(s.kills):>9.1f}{s.per_h(s.steals):>9.1f}{s.per_h(s.loot_steps):>8.1f}"
            f"{s.per_h(s.openers):>8.1f}{s.recipes:>6}{s.recipe_mismatch:>4}  {s.end or '-'}"
        )
    return "\n".join(rows)


class Series4(s2.Series):
    """stage2_ab's live series (the setup, the detect server, one run at a time), for B3 / B4."""

    score_cmd = "stage4_ab.py"


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
    a = ap.parse_args(argv)
    folder = SCRATCH / a.label
    if a.cmd == "score":
        doc = json.loads((folder / "series.json").read_text())
        scores = [score_run(r) for r in doc["runs"]]
        v = verdict(scores, float(doc["minutes"]))
        if a.json:
            print(json.dumps({"runs": [s.doc() for s in scores], "verdict": v}, indent=1))
        else:
            print(table(scores))
            print(json.dumps({k: x for k, x in v.items() if k != "lines"} | {
                "lines": {k: x for k, x in v.get("lines", {}).items() if k != "report"}},
                indent=1))  # fmt: skip
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
        project_file(arm, folder).write_text(s2.project_text(a.minutes, path))
    (folder / "runner-config.json").write_text(json.dumps({NODE: got["vals"]}) + "\n")
    return Series4(got, folder).run()


if __name__ == "__main__":
    raise SystemExit(main())
