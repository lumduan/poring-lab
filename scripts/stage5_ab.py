#!/usr/bin/env python3
"""Section 10's live A/B (docs/planning/live-blocks.md 10.1): the STAGE-4a box (B4) against the ONE
box as Batt's 2026-11-14 answers made it (B5: the drink under 50 %, the candies eaten the moment
their hotbar slot reads a count), both through the live block player, alternating runs on the lab's
own Rogue on the lab rAthena's xmas_dun02 (player mode; the MVP alive).

THE ARMS (the same runner settings for both: the Run config with --alarm-fast ON, dungeon@9.53,
section 11 -- so the series also measures the fast alarm live, report-only; the boxes' five keys
over it -- refused if their keys differ):
- B4: services/frontend/src/lib/flow/fixtures/project_xmas_dun02_stage4.json (the box as stage 4a
  measured it: the drink under 30 %, no eat);
- B5: services/frontend/src/lib/flow/fixtures/project_xmas_dun02.json (the box today).

THE SETUP before every run: exactly stage2_ab.py's (the read; the dagger on if the Knife reads worn;
clear-bag at 40 %; @heal under 95 %; the lab GM's @warp; @item under a floor -- never the candies;
the chat closed). A STOP file in the series folder (/dev/shm/poring-lab-tmp/stage5-ab/<label>/STOP)
ends the series before its next run.

THE SCORE per run: stage4_ab's, and from the same runner session the eat presses, the time under
50 % HP (each HP read holds until the next, at most HOLD_S), and the Garm Baby alarm's fires (inside
a long action or between steps). The verdict applies BAR (live-blocks.md 10.1); deaths count over
EVERY run that played (section 7's flaw: a death made its run invalid, so a death line over valid
pairs could never see one).
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import flow_run as fr  # noqa: E402
import stage2_ab as s2  # noqa: E402
import stage3_ab as s3  # noqa: E402
import stage4_ab as s4  # noqa: E402

VERSION = "9.52"  # dungeon_hunt.BOX_EAT_VERSION: the stage it measures
NODE = s2.NODE
FIX = s4.FIX
PROJECTS = {"B4": FIX / "project_xmas_dun02_stage4.json", "B5": FIX / "project_xmas_dun02.json"}
SCRATCH = Path("/dev/shm/poring-lab-tmp/stage5-ab")
HOLD_S = 2.0  # an HP read stands for at most this long (the loop reads ~2-4 / s)
PLAYED_MIN = 1.0  # a run that lasted this long played (the death line counts it)
POTION_Z = 1200  # the White Potion's NPC price (the local KB: 504 buy), for the cost line only
# THE PRE-REGISTERED BAR (live-blocks.md 10.1, written before any live run): what B5 must hold vs B4
BAR = {
    "min_minutes_share": 0.8,  # a valid run: this share of M minutes, or a weight-home end
    "min_pairs": 3,  # fewer valid pairs: kills / h is not judged
    "deaths": "B5's deaths <= B4's, over EVERY run that played (>= 1 min)",
    "under50": "B5's share of time under 50 % HP < B4's (valid runs pooled): the band closed",
    "openers_h_share": 0.20,  # B5's openers / h >= B4's x (1 - this) (valid runs pooled)
    "kills_h_se": 2.0,  # mean paired (B5 - B4) kills / h >= -this x its standard error
    "eat": "B5 pressed an eat key at least once in the series and B4 never did",
}


def series(label: str, pairs: int, order: str = "alternate",
           cells: Sequence[tuple[int, int]] | None = None) -> list[s2.Run]:  # fmt: skip
    """PURE: the runs of a series, in order: stage2_ab's alternation, A -> B4, B -> B5."""
    arm5 = {"A": "B4", "B": "B5"}
    return [s2.Run(r.k, r.pair, arm5[r.arm], f"{label}-r{r.k:02d}{arm5[r.arm]}", r.warp)
            for r in s2.series(label, pairs, order, cells)]  # fmt: skip


def run_vals(minutes: float) -> dict[str, Any] | str:
    """The runner settings BOTH arms take (stage2_ab.same_vals: each box's setting blocks and
    keys): the same, or refused."""
    return s2.same_vals(PROJECTS, minutes)


def plan_doc(label: str, pairs: int, minutes: float, order: str,
             folder: Path) -> dict[str, Any] | str:  # fmt: skip
    """PURE but for reads (the fixtures): everything a series will do, before any
    screen is read or any input path opened; a refusal: its words."""
    import flow_play as fp

    from poring_flow import project as pj

    vals = run_vals(minutes)
    if isinstance(vals, str):
        return f"refused before any input: {vals}"
    if not vals.get("alarm_fast"):
        return "refused before any input: the Run config has alarm_fast off (section 11's runs)"
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
                     "box_roles": rp.box_roles(), "box_eat": list(box.get("box_eat") or ()),
                     "box_model": (box.get("box_model") or {}).get("id"),
                     "box_recipes": box.get("box_recipes") or {}}  # fmt: skip
    if "eat" in arms["B4"]["box_plays"] or "eat" not in arms["B5"]["box_plays"]:
        return "refused before any input: B5 must eat and B4 must not (the A/B's one difference)"
    for k in ("box_roles", "box_model", "box_recipes"):
        if arms["B4"][k] != arms["B5"][k]:
            return f"refused before any input: B4 and B5 differ in {k} (not only the drink and eat)"
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


# --- the score (PURE over the sessions' events) ---------------------------------------------------
@dataclass
class Score5(s4.Score4):
    eats: int = 0  # the runner's press records of the box's eat keys
    hp_s: float = 0.0  # seconds covered by HP reads (each holds until the next, <= HOLD_S)
    under50_s: float = 0.0  # of them, under 50 %
    garm_inside: int = 0  # the alarm's fires inside a long action (9.53)
    garm_between: int = 0  # ... between steps

    def doc(self) -> dict[str, Any]:
        u = round(self.under50_s / self.hp_s, 3) if self.hp_s > 0 else None
        return {**super().doc(), "under50_share": u, "eats_h": round(self.per_h(self.eats), 2)}


def score_eat(sc: Score5, events: Iterable[Mapping[str, Any]]) -> None:
    """PURE: one runner session's eat presses, its HP-time under 50 %, its alarm fires."""
    last: tuple[int, int] | None = None
    for e in events:
        k = e.get("kind")
        if k == "press" and e.get("what") == "eat":
            sc.eats += 1
        elif k == "garm_seen":
            if e.get("inside"):
                sc.garm_inside += 1
            else:
                sc.garm_between += 1
        elif k == "hp_read" and isinstance(e.get("pct"), int):
            t = int(e.get("t_ns") or 0)
            if last is not None and t > last[0]:
                dt = min((t - last[0]) / 1e9, HOLD_S)
                sc.hp_s += dt
                sc.under50_s += dt if last[1] < 50 else 0.0
            last = (t, int(e["pct"]))


def score_run(r: Mapping[str, Any], demo: Path = s2.DEMO) -> Score5:
    """Reads (no screen): one run's sessions by its label (the hunt cores' and the player's)."""
    label, arm = str(r["label"]), str(r["arm"])
    sc = Score5(label, arm, int(r["pair"]))
    for d in sorted(demo.glob(f"*-{label}-hunt*")):
        if (d / "events.jsonl").is_file():
            ev = s2.read_events(d / "events.jsonl")
            s2.score_runner(sc, ev)
            s3.score_knife(sc, ev)
            s4.score_recipes(sc, ev)
            score_eat(sc, ev)
    for d in sorted(demo.glob(f"*-play-{label}")):
        if (d / "events.jsonl").is_file():
            s2.score_player(sc, s2.read_events(d / "events.jsonl"))
    return sc


def verdict(scores: Sequence[Score5], minutes: float,
            bar: Mapping[str, Any] = BAR) -> dict[str, Any]:  # fmt: skip
    """PURE: the pre-registered bar (live-blocks.md 10.1)."""
    ok_min = minutes * float(bar["min_minutes_share"])
    valid = {s.label for s in scores if s.found and (
        s.minutes >= ok_min or str(s.end or "").startswith("weight_home"))}  # fmt: skip
    played = [s for s in scores if s.found and (s.minutes >= PLAYED_MIN or s.deaths)]
    pairs: dict[int, dict[str, Score5]] = {}
    for s in scores:
        pairs.setdefault(s.pair, {})[s.arm] = s
    good = [p for p in pairs.values() if set(p) == {"B4", "B5"}
            and p["B4"].label in valid and p["B5"].label in valid]  # fmt: skip
    arm = {x: [s for s in scores if s.arm == x and s.label in valid] for x in ("B4", "B5")}
    deaths = {x: sum(s.deaths for s in played if s.arm == x) for x in ("B4", "B5")}
    out: dict[str, Any] = {"pairs_valid": len(good), "pairs": len(pairs),
                           "invalid": sorted({s.label for s in scores} - valid),
                           "played": {x: sum(1 for s in played if s.arm == x)
                                      for x in ("B4", "B5")}}  # fmt: skip
    lines: dict[str, Any] = {
        "deaths": {**deaths, "pass": deaths["B5"] <= deaths["B4"]},
        "eat": {x: sum(s.eats for s in scores if s.arm == x) for x in ("B4", "B5")},
    }
    lines["eat"]["pass"] = lines["eat"]["B5"] >= 1 and lines["eat"]["B4"] == 0
    if not arm["B4"] or not arm["B5"]:
        return {**out, "lines": lines, "verdict": "INCONCLUSIVE", "why": "an arm has no valid run"}

    def pooled(x: str, f: Callable[[Score5], float], g: Callable[[Score5], float]) -> float:
        den = sum(g(s) for s in arm[x])
        return sum(f(s) for s in arm[x]) / den if den > 0 else 0.0

    u = {x: round(pooled(x, lambda s: s.under50_s, lambda s: s.hp_s), 3) for x in ("B4", "B5")}
    lines["under50"] = {**u, "pass": u["B5"] < u["B4"]}
    op = {x: round(pooled(x, lambda s: s.openers * 60.0, lambda s: s.minutes), 1)
          for x in ("B4", "B5")}  # fmt: skip
    share = float(bar["openers_h_share"])
    lines["openers_h"] = {**op, "pass": op["B5"] >= op["B4"] * (1 - share)}
    d = [p["B5"].per_h(p["B5"].kills) - p["B4"].per_h(p["B4"].kills) for p in good]
    if d:
        mean_d = statistics.fmean(d)
        se = statistics.stdev(d) / math.sqrt(len(d)) if len(d) > 1 else float("inf")
        lines["kills_h"] = {"mean_diff_h": round(mean_d, 1),
                            "se_h": None if math.isinf(se) else round(se, 1),
                            "pairs": [round(x, 1) for x in d],
                            "pass": None if len(good) < int(bar["min_pairs"])
                            else mean_d >= -float(bar["kills_h_se"]) * se}  # fmt: skip
    else:
        lines["kills_h"] = {"pass": None}
    pot = {x: round(pooled(x, lambda s: s.potions * 60.0, lambda s: s.minutes), 1)
           for x in ("B4", "B5")}  # fmt: skip
    lines["report"] = {
        "potions_h": pot, "potion_cost_z_h": {x: round(v * POTION_Z) for x, v in pot.items()},
        "eats_h": {x: round(pooled(x, lambda s: s.eats * 60.0, lambda s: s.minutes), 1)
                   for x in ("B4", "B5")},
        "garm_fires": {x: {"inside": sum(s.garm_inside for s in scores if s.arm == x),
                           "between": sum(s.garm_between for s in scores if s.arm == x)}
                       for x in ("B4", "B5")},
        "hp_low": {x: min((s.hp_low for s in arm[x] if s.hp_low is not None), default=None)
                   for x in ("B4", "B5")},
        "runs": {x: [s.doc() for s in scores if s.arm == x] for x in ("B4", "B5")},
        "report_only": True}  # fmt: skip
    judged = [v["pass"] for k, v in lines.items() if k != "report"]
    if False in judged:
        v_ = "FAIL"
    elif None in judged:
        v_ = "INCONCLUSIVE"
    else:
        v_ = "PASS"
    return {**out, "lines": lines, "verdict": v_}


def table(scores: Sequence[Score5]) -> str:
    """PURE: the per-run table (plain text, the report's)."""
    head = (f"{'run':<22}{'arm':<4}{'min':>6}{'death':>6}{'kills/h':>9}{'open/h':>8}"
            f"{'pot':>5}{'eat':>5}{'<50%':>6}{'low':>5}{'garm':>6}  end")  # fmt: skip
    rows = [head]
    for s in scores:
        u = f"{s.under50_s / s.hp_s:.2f}" if s.hp_s > 0 else "-"
        rows.append(
            f"{s.label:<22}{s.arm:<4}{s.minutes:>6.1f}{s.deaths:>6}{s.per_h(s.kills):>9.1f}"
            f"{s.per_h(s.openers):>8.1f}{s.potions:>5}{s.eats:>5}{u:>6}"
            f"{s.hp_low if s.hp_low is not None else '-':>5}"
            f"{f'{s.garm_inside}/{s.garm_between}':>6}  {s.end or '-'}"
        )
    return "\n".join(rows)


class Series5(s2.Series):
    """stage2_ab's live series (the setup, the detect server, one run at a time), for B4 / B5."""

    score_cmd = "stage5_ab.py"


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
        s4.project_file(arm, folder).write_text(s2.project_text(a.minutes, path))
    (folder / "runner-config.json").write_text(json.dumps({NODE: got["vals"]}) + "\n")
    return Series5(got, folder).run()


if __name__ == "__main__":
    raise SystemExit(main())
