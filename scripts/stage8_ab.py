#!/usr/bin/env python3
"""Stage 8's live A/B, s8ab (docs/planning/live-blocks.md 18.11; Batt 2026-11-16 ~20:3x, 18.10 #2:
"Agree, do it" -- the HP Fly Wing first too): the ready-made box with fly_first ON (A, 18.10 #1)
against the same box with fly_first_hp ON as well (B, dungeon@9.58 --fly-first-hp), alternating
runs on the lab's own Rogue on the lab rAthena's xmas_dun02 (player mode; the MVP alive).

THE ARMS differ ONLY in one setting block: each arm plays a copy of
services/frontend/src/lib/flow/fixtures/project_xmas_dun02_functions.json whose safety tab holds
fly_first ON, fly_first_land OFF (s8ab measured without it; the fixture holds it ON since
live-blocks 18.18) and fly_first_hp OFF (A) or ON (B) -- each set explicitly -- through
`flow_play.py play` with that copy's own runner settings (runner-config-A.json / -B.json). `plan`
refuses before any input unless: the copies differ in that block alone; their settings in
fly_first_hp alone, with the fast alarm and fly_first on; their runner argv by `--fly-first-hp`
alone (and `--fly-first-land` in neither), their run() arguments, keys and loop not at all; the
checkout's runner is 9.58 and huntstate_check's `drive`, `check` and `flag` hold (`flag`: with
fly_first_hp's branches as their else, the WHOLE module is FLAG_BASE's, the runner s7ab measured --
so A plays s7ab's B program); and the box's step traces equal the driver's.

THE SCORE per run: stage7_ab's (its records, packets and the backend's input log) -- the HP line
judges B's HP fly-first Fly Wings (the fly_first records whose sight says hp), and is judgeable only
when at least one was pressed while she wore the Knife (18.11: the only case where B differs from
A). `score --also LABEL` (the pre-registered extension, 18.11) judges the HP line on more blocks of
4 pairs pooled; every other line stays the main label's.

    stage8_ab.py plan   --label s8ab --pairs 4 --minutes 20
    stage8_ab.py run    --label s8ab --pairs 4 --minutes 20
    stage8_ab.py score  --label s8ab [--also s8ab-x2 ...] [--json]
"""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import statistics
import sys
from collections.abc import Mapping, Sequence
from dataclasses import asdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import flow_run as fr  # noqa: E402
import hunt_trace as ht  # noqa: E402
import huntstate_check as hc  # noqa: E402
import stage2_ab as s2  # noqa: E402
import stage4_ab as s4  # noqa: E402
import stage5b_ab as s5b  # noqa: E402
import stage5c_ab as s5c  # noqa: E402
import stage7_ab as s7  # noqa: E402

VERSION = "9.58"  # dungeon_hunt.FLY_FIRST_HP_VERSION: the runner it measures
NODE = s2.NODE
PROJECT = s7.PROJECT  # the ready-made functions box (fly_first ON since 18.10 #1)
ARMS = {"A": "fly_first on, fly_first_hp off: s7ab's B (the boss Fly Wing first)",
        "B": "fly_first and fly_first_hp on: the HP Fly Wing first too (18.11)"}  # fmt: skip
TAB, VAR, FLAG = "safety", "fly_first_hp", "--fly-first-hp"
# live-blocks 18.18: the block both arms hold OFF -- s8ab measured without the land floor (the
# ready-made box holds fly_first_land ON since s10ab passed); its runner flag in neither argv
OFF_IN_BOTH = ("fly_first_land",)
LAND_FLAG = "--fly-first-land"
SCRATCH = Path("/dev/shm/poring-lab-tmp/stage8-ab")
SEEDS = s7.SEEDS
HP_SRCS = ("hp", "box_hp")  # the fly_first records of an HP Fly Wing (dungeon_hunt 9.58)
MIN_BARE = 1  # 18.11: the HP line is judgeable with at least this many bare HP Fly Wings in B
# THE PRE-REGISTERED BAR (live-blocks.md 18.11, written 2026-11-16 20:40 ICT, before any 9.58 code)
BAR = {
    **{k: v for k, v in s7.BAR.items() if k != "fly_first"},
    "fly_first_hp": "every B HP fly-first Fly Wing pressed while she was alive: no F4 / F5 key "
                    "down (the backend's input log) between the press's start and its F8, and its "
                    f"use_item_request within {s7.FLY_BOUND_S} s of the F8's send time; judgeable "
                    f"only when B made at least {MIN_BARE} such Fly Wing while she wore the Knife "
                    "(none: INCONCLUSIVE); the boss fly-first line of both arms is reported",
    "min_bare": MIN_BARE,
    "extension": "the HP line INCONCLUSIVE and no judged line failed: blocks of 4 more pairs "
                 "(s8ab-x2, s8ab-x3; at most 12 pairs in all), the HP line judged on every block "
                 "pooled (score --also), the other lines on s8ab's 4 pairs",
}  # fmt: skip


def _quiet(f: Any, *a: Any, **k: Any) -> tuple[int, str]:
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        rc = f(*a, **k)
    return int(rc), out.getvalue()


# --- the arms ------------------------------------------------------------------------------------
def arm_doc(arm: str, minutes: float, path: Path = PROJECT) -> dict[str, Any]:
    """PURE but for the read: the box with its time box set, fly_first ON and fly_first_hp set for
    the arm (A off, B on), OFF_IN_BOTH off in both (18.18: the ready-made box holds fly_first_land
    ON), its use_model s7ab's (xmas02; 18.15: the ready-made box names xmas02sk) -- each
    explicitly, whatever the fixture holds."""
    d = json.loads(path.read_text())
    d["max_runtime_s"] = int(round(minutes * 60))
    s5c.set_box_model(d, s7.MEASURED_MODEL)
    tab = next((t for t in d["nodes"][0]["tabs"] if t["name"] == TAB), None)
    if tab is None:
        raise ValueError(f"the box has no tab {TAB}")
    tab["vars"]["fly_first"] = {"kind": "lit", "value": True}
    tab["vars"][VAR] = {"kind": "lit", "value": arm == "B"}
    for var in OFF_IN_BOTH:
        tab["vars"][var] = {"kind": "lit", "value": False}
    return d


def arm_text(arm: str, minutes: float, path: Path = PROJECT) -> str:
    from poring_flow import project as pj

    return pj.to_json(pj.validate(arm_doc(arm, minutes, path)))


def box_difference(a: Mapping[str, Any], b: Mapping[str, Any]) -> str | None:
    """PURE: B is A with its fly_first_hp block on, and nothing else -- or why not."""
    a, b = json.loads(json.dumps(a)), json.loads(json.dumps(b))
    for arm, d in (("A", a), ("B", b)):
        if s5c.box_model_of(d) != s7.MEASURED_MODEL:  # 18.15: s8ab's arms name xmas02
            return f"{arm}'s use_model is not {s7.MEASURED_MODEL} (s8ab's arms)"
        tab = next((t for t in d["nodes"][0]["tabs"] if t["name"] == TAB), None)
        lit = None if tab is None else tab["vars"].get(VAR)
        ff = None if tab is None else tab["vars"].get("fly_first")
        if not isinstance(lit, Mapping) or lit.get("value") is not (arm == "B"):
            return f"{arm}'s {TAB} tab does not hold {VAR} = {arm == 'B'}"
        if not isinstance(ff, Mapping) or ff.get("value") is not True:
            return f"{arm}'s {TAB} tab does not hold fly_first = True (18.10 #1)"
        for var in OFF_IN_BOTH:  # 18.18: s8ab's arms hold the land floor off
            off = tab["vars"].get(var)
            if not isinstance(off, Mapping) or off.get("value") is not False:
                return f"{arm}'s {TAB} tab does not hold {var} = False (s8ab's arms)"
        tab["vars"].pop(VAR)
    if a != b:
        return "B differs from A in more than its fly_first_hp block (an A/B changes one thing)"
    return None


def runner_problem(runner_text: str) -> str | None:
    """PURE: the checkout's runner is 9.58: it takes --fly-first-hp."""
    if f'FLY_FIRST_HP_VERSION = "{VERSION}"' not in runner_text or f'"{FLAG}",' not in runner_text:
        return f"the checkout's runner is not dungeon@{VERSION} (no {FLAG})"
    return None


def plan_doc(label: str, pairs: int, minutes: float, order: str, folder: Path,
             runner_text: str | None = None, base_text: str | None = None,
             check_base: str | None = None, flag_base: str | None = None,
             seeds: int = SEEDS) -> dict[str, Any] | str:  # fmt: skip
    """PURE but for reads (the fixture, git, the checkout's runner): everything a series will do,
    before any screen is read or any input path opened; a refusal: its words."""
    import flow_play as fp

    from poring_flow import project as pj

    texts = {arm: arm_text(arm, minutes) for arm in ("A", "B")}
    why = box_difference(json.loads(texts["A"]), json.loads(texts["B"]))
    if why is not None:
        return f"refused before any input: {why}"
    vals: dict[str, dict[str, Any]] = {}
    for arm, text in texts.items():
        v = s5c.vals_of(text)
        if isinstance(v, str):
            return f"refused before any input: {arm}: {v}"
        vals[arm] = v
    diff = sorted(
        k for k in set(vals["A"]) | set(vals["B"]) if vals["A"].get(k) != vals["B"].get(k)
    )
    if diff != [VAR] or vals["A"][VAR] is not False or vals["B"][VAR] is not True:
        return (f"refused before any input: the arms' runner settings differ in {diff}, not "
                f"{VAR} alone")  # fmt: skip
    if not (
        vals["A"].get("garm_fly") and vals["A"].get("alarm_fast") and vals["A"].get("fly_first")
    ):
        return "refused before any input: garm_fly / alarm_fast / fly_first off in the Run config"
    runner_text = hc.TARGET.read_text() if runner_text is None else runner_text
    bad = runner_problem(runner_text)
    if bad:
        return f"refused before any input: {bad}"
    base_text = hc.git_show(hc.DRIVE_BASE, hc.TARGET) if base_text is None else base_text
    check_base = hc.git_show(hc.BASE_REV, hc.TARGET) if check_base is None else check_base
    flag_base = hc.git_show(hc.FLAG_BASE, hc.TARGET) if flag_base is None else flag_base
    proofs = (("drive", _quiet(hc.drive_check, base_text, runner_text)),
              ("check", _quiet(hc.check, check_base, runner_text, drive_ok=True)),
              ("flag", _quiet(hc.flag_check, flag_base, runner_text)))  # fmt: skip
    for name, (rc, out) in proofs:
        if rc != 0:
            lines = [ln for ln in out.splitlines() if "NO" in ln or "DIFFERS" in ln
                     or "CHANGED" in ln]  # fmt: skip
            return (f"refused before any input: huntstate_check {name} fails: "
                    f"{'; '.join(lines)[:300]}")  # fmt: skip
    hashes: dict[str, str] = {}
    arms: dict[str, Any] = {}
    argv: dict[str, list[str]] = {}
    for arm, text in texts.items():
        h = pj.project_hash(pj.from_json(text))
        prep = fp.prepare(text, NODE, int(round(minutes * 60)), runner_vals={NODE: vals[arm]},
                          want_hash=h)  # fmt: skip
        if isinstance(prep, str):
            return f"{arm}: {prep}"
        rp = prep.runners[NODE]
        hashes[arm] = h
        argv[arm] = rp.argv("L", None, None)
        arms[arm] = {"what": ARMS[arm], "project": str(PROJECT.relative_to(ROOT)),
                     "fly_first_hp": arm == "B", "project_hash": h, "loop": rp.loop,
                     "left_out": list(rp.tick_left_out), "box": rp.box_kwargs(),
                     "keys": rp.keys}  # fmt: skip
    if "--fly-first" not in argv["A"]:
        return "refused before any input: A's runner argv has no --fly-first (18.10 #1)"
    if LAND_FLAG in argv["A"] or LAND_FLAG in argv["B"]:
        return f"refused before any input: {LAND_FLAG} in a runner argv (s8ab measured without it)"
    if FLAG in argv["A"] or argv["B"].count(FLAG) != 1:
        return f"refused before any input: {FLAG} must be in B's runner argv alone"
    if [x for x in argv["B"] if x != FLAG] != argv["A"]:
        return f"refused before any input: the arms' runner argv differ in more than {FLAG}"
    for k in ("box", "keys", "loop", "left_out"):
        if arms["A"][k] != arms["B"][k]:
            return f"refused before any input: the arms give the runner different {k}"
    if arms["A"]["loop"] != "hunt_loop" or arms["A"]["left_out"]:
        return "refused before any input: the box must drive its hunt loop with the full tick"
    scns = [*ht.hand_scenarios(), *ht.random_scenarios(seeds)]
    diffs = [f"{s.name}: {r.first_diff}" for s in scns if not (r := ht.compare(s, texts["B"])).same]
    if diffs:
        return (f"refused before any input: the box's hunt loop's step trace is not the driver's "
                f"(hunt_trace.py): {'; '.join(diffs[:3])}")  # fmt: skip
    runs = s2.series(label, pairs, order)
    return {
        "version": VERSION, "label": label, "pairs": pairs, "minutes": minutes, "order": order,
        "arms": arms, "vals": vals, "bar": BAR, "drive_base": hc.DRIVE_BASE,
        "check_base": hc.BASE_REV, "flag_base": hc.FLAG_BASE,
        "runner_sha256": s5b.sha(runner_text), "trace_scenarios": len(scns),
        "serve_s": int(len(runs) * (minutes * 60 + s2.START_GRACE_S + 120) + s2.SERVE_EXTRA_S),
        "runs": [{**asdict(r), "argv": fr.play_command(
            s4.project_file(r.arm, folder), NODE, r.label, folder / f"{r.label}.STOP",
            int(round(minutes * 60)), hashes[r.arm], folder / f"runner-config-{r.arm}.json")}
            for r in runs],
    }  # fmt: skip


# --- the verdict -------------------------------------------------------------------------------
def is_hp(f: s7.Fly) -> bool:
    return f.src in HP_SRCS or bool((f.sight or {}).get("hp"))


def hp_line(scores: Sequence[s7.Score7], bound_s: float = s7.FLY_BOUND_S,
            min_bare: int = MIN_BARE) -> dict[str, Any]:  # fmt: skip
    """PURE: BAR's HP line over B's played runs (the main label's and any --also block's)."""
    played = [s for s in scores if s.arm == "B" and s.found
              and (s.minutes >= s5c.PLAYED_MIN or s.deaths)]  # fmt: skip
    flies = [(s.label, f) for s in played for f in s.flies_ff if is_hp(f)]
    judged = [(lab, f) for lab, f in flies if f.ok(bound_s) is not None]
    bare = [f for _lab, f in judged if (f.sight or {}).get("bare")]
    bad = [f"{lab}: {f.why} ({f.src}): " + ("a weapon key before it " + str(f.keys_before)
           if f.keys_before else "no use_item_request" if f.request_s is None
           else f"its request {f.request_s} s after its send") for lab, f in judged
           if not f.ok(bound_s)]  # fmt: skip
    reqs = sorted(f.request_s for _lab, f in judged if f.request_s is not None)
    return {"flies": len(flies), "judged": len(judged), "bare": len(bare),
            "after_death": sum(1 for _lab, f in flies if f.after_death),
            "request_s": {"median": round(statistics.median(reqs), 3) if reqs else None,
                          "max": reqs[-1] if reqs else None},
            "problems": bad,
            "pass": False if bad else (None if len(bare) < min_bare else True)}  # fmt: skip


def boss_report(scores: Sequence[s7.Score7], bound_s: float = s7.FLY_BOUND_S
                ) -> dict[str, Any]:  # fmt: skip
    """PURE: 9.57's boss fly-first line of each arm (both play it), reported."""
    out: dict[str, Any] = {}
    for x in ("A", "B"):
        sub = [s for s in scores if s.arm == x]
        boss = [f for s in sub for f in s.flies_ff if not is_hp(f)]
        judged = [f for f in boss if f.ok(bound_s) is not None]
        out[x] = {"flies": len(boss), "judged": len(judged),
                  "ok": sum(1 for f in judged if f.ok(bound_s))}  # fmt: skip
    return out


def verdict(scores: Sequence[s7.Score7], minutes: float, a_kinds: set[str],
            bar: Mapping[str, Any] = BAR,
            econ: Mapping[str, Mapping[str, Any] | None] | None = None,
            also: Sequence[s7.Score7] = ()) -> dict[str, Any]:  # fmt: skip
    """PURE: the pre-registered bar (18.11). ``also``: the extension blocks' scores (the HP line
    only). Deaths are reported, never judged."""
    v = s5b.verdict(scores, minutes, set(a_kinds) | {s5c.DRIVE_KIND, s7.FLY_KIND}, bar)
    lines = dict(v.get("lines") or {})
    deaths = lines.pop("deaths", None)
    rep = dict(lines.get("report") or {})
    rep["deaths"] = deaths
    rep["arms"] = s7.report_of(scores, minutes, bar, econ)
    rep["boss_fly_first"] = boss_report(scores, float(bar["fly_bound_s"]))
    lines["report"] = rep
    lines["drive"] = s5c.drive_line(scores)
    lines["fly_first_hp"] = hp_line([*scores, *also], float(bar["fly_bound_s"]),
                                    int(bar["min_bare"]))  # fmt: skip
    out = {**v, "lines": lines}
    if out.get("why") == "an arm has no valid run":
        out["verdict"] = "INCONCLUSIVE"
        return out
    judged = [x["pass"] for k, x in lines.items() if k != "report"]
    out["verdict"] = "FAIL" if False in judged else ("INCONCLUSIVE" if None in judged else "PASS")
    return out


class Series8(s2.Series):
    """stage2_ab's live series (the setup, the detect server, one run at a time), for A / B."""

    score_cmd = "stage8_ab.py"


def _scores(label: str) -> tuple[dict[str, Any], list[s7.Score7]]:
    folder = SCRATCH / label
    doc = json.loads((folder / "series.json").read_text())
    return doc, [s7.score_run(r, folder) for r in doc["runs"]]


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("plan", "run", "score"):
        p = sub.add_parser(name)
        p.add_argument("--label", required=True, help="the series' name (its runs' labels)")
        if name != "score":
            p.add_argument("--pairs", type=int, default=4)
            p.add_argument("--minutes", type=int, default=20,
                           help="each run's length (the Run config's minutes: 5..600)")  # fmt: skip
            p.add_argument("--order", choices=("alternate", "ab"), default="alternate")
        else:
            p.add_argument("--json", action="store_true")
            p.add_argument("--also", action="append", default=[],
                           help="an extension block's label (18.11): the HP line "
                           "pooled")  # fmt: skip
            p.add_argument("--no-econ-update", action="store_true",
                           help="do not add the runs' sessions to "
                           "data/econ/lab.sqlite first")  # fmt: skip
    a = ap.parse_args(argv)
    folder = SCRATCH / a.label
    if a.cmd == "score":
        doc, scores = _scores(a.label)
        if not a.no_econ_update:  # Batt 2026-11-16 (17 #7): every run's economy in lab.sqlite
            print(s7.econ_update(doc["runs"]), flush=True)
            doc, scores = _scores(a.label)
        also = [s for lab in a.also for s in _scores(lab)[1]]
        base = (folder / "runner-5b1.py").read_text()
        v = verdict(scores, float(doc["minutes"]), s5b.base_kinds(base),
                    econ=s7.econ_arms(scores, float(doc["minutes"])), also=also)  # fmt: skip
        if a.json:
            print(json.dumps({"runs": [s.doc() for s in scores], "verdict": v}, indent=1))
        else:
            print(s7.table(scores))
            print(json.dumps(v, indent=1, default=str))
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
    (folder / "runner-5b1.py").write_text(hc.git_show(hc.DRIVE_BASE, hc.TARGET))  # base kinds
    for arm in ("A", "B"):
        s4.project_file(arm, folder).write_text(arm_text(arm, a.minutes))
        (folder / f"runner-config-{arm}.json").write_text(json.dumps({NODE: got["vals"][arm]})
                                                         + "\n")  # fmt: skip
    return Series8(got, folder).run()


if __name__ == "__main__":
    raise SystemExit(main())
