#!/usr/bin/env python3
"""LIVE BLOCKS STAGE 3's A/B (docs/planning/live-blocks.md 3.3, the pre-registered bar there): the
STAGE-2 box (B2) against the STAGE-3 box (B3), both through the live block player, alternating runs
of the same length on xmas_dun02, the same setup before every run, one detect server for the whole
series. Batt 2026-11-13: "The Knife swap (Damascus): a function: press F4, wait 100 ms, press F5;
the other way back to the Knife: the same swapped"; "make respawn a function block, in case another
server's menu differs" -- B3 plays the Knife swap, the way home, the respawn and the weight home as
the box's functions and event at the runner's own moments; B2 leaves them to the runner, as stage 2.

    stage3_ab.py plan  --label L [--pairs N] [--minutes M] [--order alternate|ab]   PURE
    stage3_ab.py run   --label L [--pairs N] [--minutes M] [--order alternate|ab]   LIVE
    stage3_ab.py score --label L [--json]                                            PURE (reads)

A sibling of scripts/stage2_ab.py, sharing its code (the setup steps, the detect server, the run
of one arm, the runner's score): only the arms, the extra score lines and the bar are its own.

THE ARMS (the same runner settings for both: the Run config, the boxes' five keys over it -- the
same keys, checked -- and --minutes M), both `flow_play.py play` on the node xmas_dun02:
- B2: services/frontend/src/lib/flow/fixtures/project_xmas_dun02_stage2.json (the ready-made box
  as stage 2 left it: heal and the Fly Wing as its events; the Knife, the way home, the respawn
  and the weight exit the runner's own);
- B3: services/frontend/src/lib/flow/fixtures/project_xmas_dun02_stage3.json (the ready-made box
  as stage 3 left it: also the knife tab's two functions, the exits tab's way home and respawn
  clicks, survival's bag_full; kept byte for byte when stage 4a gave the one box its use_model and
  its monsters tab: scripts/stage4_ab.py measures that one).
The order: "alternate" (the default) is B2 B3, B3 B2, ... ; "ab" is B2 B3, B2 B3, ...

THE SETUP before every run: exactly stage2_ab.py's (the read; clear-bag at 40 %; the lab GM's
@warp alternating PATROL_START's two cells; @item under a floor; the chat input closed and read
closed), as child processes, never beside a run. A STOP file in the series folder
(/dev/shm/poring-lab-tmp/stage3-ab/<label>/STOP) ends the series before its next run.

THE SCORE per run: stage2_ab's (the runner's session: minutes, deaths, potions, Fly Wings by cause,
kills, loot steps, the lowest HP; the player's box events) and, from the same runner session, the
Knife (openers read back, opener fails, swaps back read back, swap fails, steals = the swaps back
on the steal's cue, the opener -> steal-cue seconds, the swap-back read-back ms), the respawn
(pressed, arrived), the way home (pressed, arrived), the weight (the highest read, a weight-home
end, by whom), and the box's calls by role. The verdict applies BAR (live-blocks.md 3.3).
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

VERSION = "9.50"  # dungeon_hunt.BOX_FUNCTIONS_VERSION: the stage it measures
NODE = s2.NODE
FIX = ROOT / "services/frontend/src/lib/flow/fixtures"
PROJECTS = {"B2": FIX / "project_xmas_dun02_stage2.json",
            "B3": FIX / "project_xmas_dun02_stage3.json"}  # fmt: skip
SCRATCH = Path("/dev/shm/poring-lab-tmp/stage3-ab")
STEAL_CUES = ("popup", "cyan")  # a swap back on the steal's own cue (bare_steal.BareSteal.tick)
# THE PRE-REGISTERED BAR (live-blocks.md 3.3, written before any live run): what B3 must hold vs B2
BAR = {
    "min_minutes_share": 0.8,  # a valid run: this share of M minutes, or a weight-home end
    "min_pairs": 3,  # fewer valid pairs: kills/h and steals/h are not judged (INCONCLUSIVE)
    "deaths": "B3's deaths <= B2's (the series' totals)",
    "kills_h_se": 2.0,  # mean paired (B3 - B2) kills / h >= -this x its standard error
    "steals_h_se": 2.0,  # mean paired (B3 - B2) steals / h >= -this x its standard error
    "swap_fails_per_h_margin": 2.0,  # B3's failed Knife swaps / h <= B2's + this
    "respawn": "every B3 death respawned and arrived (judged when B3 died)",
    "home": "B3's share of non-death runs that pressed the Butterfly Wing and arrived >= B2's",
    "weight": "every B3 run that read the bag at >= 50 % ended by the box's weight event, and no "
    "box weight event fired under 49.5 % (judged when a B3 run read >= 50 %)",
    "weight_line": 0.50,
}


# --- the plan (PURE) ------------------------------------------------------------------------------
def series(label: str, pairs: int, order: str = "alternate",
           cells: Sequence[tuple[int, int]] | None = None) -> list[s2.Run]:  # fmt: skip
    """PURE: the runs of a series, in order: stage2_ab's alternation, A -> B2, B -> B3."""
    arm3 = {"A": "B2", "B": "B3"}
    return [s2.Run(r.k, r.pair, arm3[r.arm], f"{label}-r{r.k:02d}{arm3[r.arm]}", r.warp)
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
    if keys["B2"] != keys["B3"]:
        return f"the two boxes' keys differ: B2 {keys['B2']}, B3 {keys['B3']}"
    vals, _src, _ks, why = fr.run_values(fr.FLOWS[s2.FLOW_ID], keys["B3"], config_dir)
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
        arms[arm] = {"project": str(path.relative_to(ROOT)), "project_hash": h,
                     "box_plays": sorted(rp.plays), "box_events": list(rp.events),
                     "box_roles": rp.box_roles(),
                     "calls": {r: [x.doc() for x in st] for r, st in rp.calls.items()}}  # fmt: skip
    if arms["B2"]["box_roles"] or "weight_home" in arms["B2"]["box_plays"]:
        return "refused before any input: B2 is not the stage-2 box (it plays stage 3's functions)"
    if not arms["B3"]["box_roles"]:
        return "refused before any input: B3 plays none of stage 3's functions"
    runs = series(label, pairs, order)
    return {
        "version": VERSION, "label": label, "pairs": pairs, "minutes": minutes, "order": order,
        "arms": arms, "vals": vals, "bar": BAR,
        "serve_s": int(len(runs) * (minutes * 60 + s2.START_GRACE_S + 120) + s2.SERVE_EXTRA_S),
        "runs": [{**asdict(r), "argv": commands(r, folder, minutes, hashes)} for r in runs],
    }  # fmt: skip


# --- the score (PURE over the sessions' events) ---------------------------------------------------
@dataclass
class Score3(s2.Score):
    openers: int = 0  # the opener read back worn (the Knife on), or through (the other answer)
    opener_fails: int = 0
    swaps_back: int = 0  # the dagger read back worn
    swap_fails: int = 0
    steals: int = 0  # swaps back on the steal's own cue (popup / cyan)
    steal_s: list[float] = field(default_factory=list)  # opener read back -> the steal's swap back
    equip_ms: list[int] = field(default_factory=list)  # the swap back's read-back time
    respawn_pressed: int = 0
    respawn_arrived: int = 0
    home_pressed: int = 0
    home_arrived: int = 0
    weight_max: float | None = None  # the highest weight share the runner read
    weight_end: str | None = None  # "box" / "runner": who ended it at the weight line
    weight_box_share: float | None = None  # the share the box's weight event fired on
    calls: dict[str, int] = field(default_factory=dict)  # the box's calls by role

    @property
    def died(self) -> bool:
        return self.deaths > 0

    def doc(self) -> dict[str, Any]:
        return {**super().doc(), "steals_h": round(self.per_h(self.steals), 1),
                "swap_fails_h": round(self.per_h(self.opener_fails + self.swap_fails), 2),
                "steal_s_median": None if not self.steal_s else round(
                    statistics.median(self.steal_s), 2),
                "equip_ms_median": None if not self.equip_ms else int(
                    statistics.median(self.equip_ms))}  # fmt: skip


def score_knife(sc: Score3, events: Iterable[Mapping[str, Any]]) -> None:
    """PURE: one runner session's Knife, respawn, way home, weight and box calls (stage 3)."""
    opener_t: int | None = None
    calls: Counter[str] = Counter(sc.calls)
    for e in events:
        k, t = e.get("kind"), int(e.get("t_ns") or 0)
        if k == "bare" and e.get("what") == "opener":
            if e.get("ok"):
                sc.openers += 1
                opener_t = t
            elif e.get("ok") is False:
                sc.opener_fails += 1
        elif k == "bare" and e.get("what") == "equip" and not e.get("pending"):
            if e.get("ok"):
                sc.swaps_back += 1
                if isinstance(e.get("ms"), int):
                    sc.equip_ms.append(int(e["ms"]))
                if e.get("why") in STEAL_CUES:
                    sc.steals += 1
                    if opener_t is not None:
                        sc.steal_s.append(round((t - opener_t) / 1e9, 2))
                opener_t = None
            elif e.get("ok") is False:
                sc.swap_fails += 1
        elif k == "player_respawn":
            sc.respawn_pressed += int(bool(e.get("pressed")))
            sc.respawn_arrived += int(bool(e.get("pressed")) and e.get("back_s") is not None)
        elif k == "player_home":
            sc.home_pressed += int(bool(e.get("pressed")))
            sc.home_arrived += int(bool(e.get("pressed")) and e.get("back_s") is not None)
        elif k == "weight" and isinstance(e.get("share"), int | float):
            w = float(e["share"])
            sc.weight_max = w if sc.weight_max is None else max(sc.weight_max, w)
        elif k == "weight_home":
            sc.weight_end = "box" if e.get("by") == "box" else "runner"
            if e.get("by") == "box" and isinstance(e.get("share"), int | float):
                sc.weight_box_share = float(e["share"])
        elif k == "box_call":
            calls[str(e.get("role"))] += 1
    sc.calls = dict(calls)


def score_run(r: Mapping[str, Any], demo: Path = s2.DEMO) -> Score3:
    """Reads (no screen): one run's sessions by its label (the hunt cores' and the player's)."""
    label, arm = str(r["label"]), str(r["arm"])
    sc = Score3(label, arm, int(r["pair"]))
    for d in sorted(demo.glob(f"*-{label}-hunt*")):
        if (d / "events.jsonl").is_file():
            ev = s2.read_events(d / "events.jsonl")
            s2.score_runner(sc, ev)
            score_knife(sc, ev)
    for d in sorted(demo.glob(f"*-play-{label}")):
        if (d / "events.jsonl").is_file():
            s2.score_player(sc, s2.read_events(d / "events.jsonl"))
    return sc


def _paired(good: list[dict[str, Score3]], f: Callable[[Score3], float], se_k: float,
            min_pairs: int) -> dict[str, Any]:  # fmt: skip
    d = [p["B3"].per_h(f(p["B3"])) - p["B2"].per_h(f(p["B2"])) for p in good]
    mean_d = statistics.fmean(d)
    se = statistics.stdev(d) / math.sqrt(len(d)) if len(d) > 1 else float("inf")
    out: dict[str, Any] = {"mean_diff_h": round(mean_d, 1),
                           "se_h": None if math.isinf(se) else round(se, 1),
                           "pairs": [round(x, 1) for x in d]}  # fmt: skip
    out["pass"] = None if len(good) < min_pairs else mean_d >= -se_k * se
    return out


def verdict(scores: Sequence[Score3], minutes: float,
            bar: Mapping[str, Any] = BAR) -> dict[str, Any]:  # fmt: skip
    """PURE: the pre-registered bar (live-blocks.md 3.3) over the valid pairs."""
    ok_min = minutes * float(bar["min_minutes_share"])
    valid = {s.label for s in scores if s.found and (
        s.minutes >= ok_min or str(s.end or "").startswith("weight_home"))}  # fmt: skip
    pairs: dict[int, dict[str, Score3]] = {}
    for s in scores:
        pairs.setdefault(s.pair, {})[s.arm] = s
    good = [p for p in pairs.values() if set(p) == {"B2", "B3"}
            and p["B2"].label in valid and p["B3"].label in valid]  # fmt: skip
    b2, b3 = [p["B2"] for p in good], [p["B3"] for p in good]
    out: dict[str, Any] = {"pairs_valid": len(good), "pairs": len(pairs),
                           "invalid": sorted({s.label for s in scores} - valid)}  # fmt: skip
    if not good:
        return {**out, "verdict": "INCONCLUSIVE", "why": "no valid pair"}
    hours = {x: sum(s.minutes for s in arm) / 60.0 for x, arm in (("B2", b2), ("B3", b3))}

    def rate(arm: list[Score3], f: Callable[[Score3], float], x: str) -> float:
        return sum(f(s) for s in arm) / hours[x] if hours[x] > 0 else 0.0

    mp = int(bar["min_pairs"])
    deaths = (sum(s.deaths for s in b2), sum(s.deaths for s in b3))
    fails = (rate(b2, lambda s: s.opener_fails + s.swap_fails, "B2"),
             rate(b3, lambda s: s.opener_fails + s.swap_fails, "B3"))  # fmt: skip
    lines: dict[str, Any] = {
        "deaths": {"B2": deaths[0], "B3": deaths[1], "pass": deaths[1] <= deaths[0]},
        "kills_h": _paired(good, lambda s: s.kills, float(bar["kills_h_se"]), mp),
        "steals_h": _paired(good, lambda s: s.steals, float(bar["steals_h_se"]), mp),
        "swap_fails_h": {"B2": round(fails[0], 2), "B3": round(fails[1], 2),
                         "pass": fails[1] <= fails[0] + float(bar["swap_fails_per_h_margin"])},
    }  # fmt: skip
    died = [s for s in b3 if s.died]
    lines["respawn"] = {
        "B3_deaths": deaths[1],
        "B3_arrived": sum(s.respawn_arrived for s in b3),
        "pass": None if not died else all(s.respawn_arrived >= s.deaths for s in died),
    }

    def home_share(arm: list[Score3]) -> float | None:
        alive = [s for s in arm if not s.died]
        return None if not alive else sum(s.home_arrived > 0 for s in alive) / len(alive)

    h2, h3 = home_share(b2), home_share(b3)
    lines["home"] = {
        "B2": h2,
        "B3": h3,
        "pass": None if h3 is None else h3 >= (h2 if h2 is not None else 1.0),
    }
    line = float(bar["weight_line"])
    heavy = [s for s in b3 if s.weight_max is not None and s.weight_max >= line]
    early = [s for s in b3 if s.weight_box_share is not None and s.weight_box_share < line - 0.005]
    lines["weight"] = {
        "B3_heavy": len(heavy), "B3_box_ends": sum(s.weight_end == "box" for s in b3),
        "early": [s.label for s in early],
        "pass": False if early else (None if not heavy else all(s.weight_end == "box"
                                                                for s in heavy))}  # fmt: skip
    rep = {"B2": [s.doc() for s in b2], "B3": [s.doc() for s in b3]}
    lines["report"] = {
        "loot_h_diff": round(statistics.fmean([p["B3"].per_h(p["B3"].loot_steps)
                                               - p["B2"].per_h(p["B2"].loot_steps)
                                               for p in good]), 1),
        "steal_s_median": {x: _median([v for s in arm for v in s.steal_s])
                           for x, arm in (("B2", b2), ("B3", b3))},
        "equip_ms_median": {x: _median([v for s in arm for v in s.equip_ms])
                            for x, arm in (("B2", b2), ("B3", b3))},
        # the steals per Knife opener (Batt's own run 2026-11-12: 91 % stolen)
        "steal_share": {x: _share(sum(s.steals for s in arm), sum(s.openers for s in arm))
                        for x, arm in (("B2", b2), ("B3", b3))},
        "openers_h": {x: round(rate(arm, lambda s: s.openers, x), 1)
                      for x, arm in (("B2", b2), ("B3", b3))},
        "runs": rep, "report_only": True}  # fmt: skip
    # FAIL: a judged line failed; INCONCLUSIVE: too few pairs for kills / steals (and nothing
    # failed); a respawn / home / weight line with nothing to judge is "not exercised", not a fail
    judged = [x["pass"] for x in lines.values() if "pass" in x]
    if False in judged:
        v = "FAIL"
    elif lines["kills_h"]["pass"] is None or lines["steals_h"]["pass"] is None:
        v = "INCONCLUSIVE"
    else:
        v = "PASS"
    out["not_exercised"] = [k for k in ("respawn", "home", "weight") if lines[k]["pass"] is None]
    return {**out, "lines": lines, "verdict": v}


def _share(n: int, of: int) -> float | None:
    return None if of == 0 else round(n / of, 3)


def _median(v: list[float] | list[int]) -> float | None:
    return None if not v else round(float(statistics.median(v)), 2)


def table(scores: Sequence[Score3]) -> str:
    """PURE: the per-run table (plain text, the report's)."""
    head = (
        f"{'run':<22}{'arm':<4}{'min':>6}{'death':>6}{'kills/h':>9}{'steal/h':>9}"
        f"{'open':>6}{'back':>6}{'fail':>5}{'resp':>5}{'home':>5}{'w_max':>7}  end"
    )
    rows = [head]
    for s in scores:
        w = "-" if s.weight_max is None else f"{s.weight_max:.2f}"
        rows.append(
            f"{s.label:<22}{s.arm:<4}{s.minutes:>6.1f}{s.deaths:>6}"
            f"{s.per_h(s.kills):>9.1f}{s.per_h(s.steals):>9.1f}{s.openers:>6}"
            f"{s.swaps_back:>6}{s.opener_fails + s.swap_fails:>5}"
            f"{s.respawn_arrived:>5}{s.home_arrived:>5}{w:>7}  {s.end or '-'}"
        )
    return "\n".join(rows)


class Series3(s2.Series):
    """stage2_ab's live series (the setup, the detect server, one run at a time), for B2 / B3."""

    score_cmd = "stage3_ab.py"


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
    return Series3(got, folder).run()


if __name__ == "__main__":
    raise SystemExit(main())
