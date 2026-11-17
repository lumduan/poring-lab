#!/usr/bin/env python3
"""Stage 10's live A/B, s10ab (docs/planning/live-blocks.md 18.17): the stale re-fire's fix. The
ready-made functions box as it is now (A: xmas02sk, fly_first and fly_first_hp ON, fly_first_land
OFF = dungeon@9.59's program) against the same box with fly_first_land ON (B, dungeon@9.60: a boss
sighting counts only when grabbed after the last Fly Wing's key + FF_LAND_S), alternating runs on
the lab's own Rogue on the lab rAthena's xmas_dun02 (player mode; the MVP alive).

THE ARMS differ ONLY in one setting block: each arm plays a copy of
services/frontend/src/lib/flow/fixtures/project_xmas_dun02_functions.json whose safety tab holds
fly_first and fly_first_hp ON, FF_LAND_S at the fixture's value and fly_first_land OFF (A) or ON
(B) -- each set explicitly, the use_model the fixture's (xmas02sk) -- through `flow_play.py play`.
`plan` refuses before any input unless: the copies differ in that block alone; their runner
settings in fly_first_land alone; their runner argv by `--fly-first-land` alone; their run()
arguments, keys, loop and tick not at all; the checkout's runner is 9.60 and huntstate_check's
`drive`, `check`, `flag`, `pick` and `land` hold (`land`: with the fly-land branches as their else
the WHOLE module is LAND_BASE's, the 9.59 runner s9ab measured -- so A plays s9ab's B program); and
the box's step traces equal the driver's.

THE SCORE per run: stage9_ab's (stage7_ab's lines, the packets' truth of every boss Fly Wing, the
party's visits, the detect ms) and, from the runner's own records, every STALE RE-FIRE: an alarm
boss Fly Wing whose sighting (its fly_first record's sight.t_ns, the grab time) was grabbed at or
before the previous Fly Wing's key + the window (the run's own FF_LAND_S, its run_start record's
fixes.fly_first_land; A, which has none: the bar's). The previous Fly Wing's key: the latest
t_key_ns of the run's fly_first records (fly, and B's land records, one per Fly Wing).

    stage10_ab.py plan   --label s10ab --pairs 4 --minutes 20
    stage10_ab.py run    --label s10ab --pairs 4 --minutes 20
    stage10_ab.py score  --label s10ab [--json]
"""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import sys
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, field
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
import stage8_ab as s8  # noqa: E402
import stage9_ab as s9  # noqa: E402

VERSION = "9.60"  # dungeon_hunt.FLY_LAND_VERSION: the runner it measures
NODE = s2.NODE
PROJECT = s7.PROJECT  # the ready-made functions box (xmas02sk; fly_first, fly_first_hp ON)
MODEL = "xmas02sk"  # the fixture's use_model (18.15), both arms
ARMS = {"A": "fly_first_land off: the ready-made box as it is (dungeon@9.59's program)",
        "B": "fly_first_land on: a boss sighting only after the landing (9.60)"}  # fmt: skip
TAB, VAR, FLAG = "safety", "fly_first_land", "--fly-first-land"
SCRATCH = Path("/dev/shm/poring-lab-tmp/stage10-ab")
SEEDS = s7.SEEDS
LAND_S = 0.75  # dungeon_hunt.FF_LAND_S's default (live-blocks.md 18.17's derivation)
# THE PRE-REGISTERED BAR (live-blocks.md 18.17, written before any s10ab run)
BAR = {
    **{k: v for k, v in s7.BAR.items() if k not in ("fly_first", "fly_bound_s")},
    "deaths": s9.BAR["deaths"],
    "stale": "B's STALE re-fires == 0 over its played runs (an alarm boss Fly Wing whose sighting "
             "was grabbed at or before the previous Fly Wing's key + its run's FF_LAND_S, from "
             "the runner's records); judged when B made at least one alarm boss Fly Wing (none: "
             "INCONCLUSIVE); A's count is reported",
    "land_s": LAND_S,
    "reported": "Fly Wings / h, false boss Fly Wings / h by S7's truth, the party's visits flown "
                "and the time to the Fly Wing, the sightings held by the floor, deaths, the "
                "economy with steals, the detect ms, the model each run loaded",
}  # fmt: skip


def _quiet(f: Any, *a: Any, **k: Any) -> tuple[int, str]:
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        rc = f(*a, **k)
    return int(rc), out.getvalue()


# --- the arms ------------------------------------------------------------------------------------
def arm_doc(arm: str, minutes: float, path: Path = PROJECT) -> dict[str, Any]:
    """PURE but for the read: the box with its time box set, fly_first and fly_first_hp ON,
    fly_first_land set for the arm (A off, B on) and its use_model MODEL -- each explicitly."""
    d = json.loads(path.read_text())
    d["max_runtime_s"] = int(round(minutes * 60))
    tab = next((t for t in d["nodes"][0]["tabs"] if t["name"] == TAB), None)
    if tab is None:
        raise ValueError(f"the box has no tab {TAB}")
    for var in (s7.FLY_VAR, s8.VAR):
        tab["vars"][var] = {"kind": "lit", "value": True}
    tab["vars"][VAR] = {"kind": "lit", "value": arm == "B"}
    s5c.set_box_model(d, MODEL)
    return d


def arm_text(arm: str, minutes: float, path: Path = PROJECT) -> str:
    from poring_flow import project as pj

    return pj.to_json(pj.validate(arm_doc(arm, minutes, path)))


def box_difference(a: Mapping[str, Any], b: Mapping[str, Any]) -> str | None:
    """PURE: B is A with its fly_first_land block on, and nothing else -- or why not."""
    a, b = json.loads(json.dumps(a)), json.loads(json.dumps(b))
    for arm, d in (("A", a), ("B", b)):
        if s5c.box_model_of(d) != MODEL:
            return f"{arm}'s use_model is not {MODEL}"
        tab = next((t for t in d["nodes"][0]["tabs"] if t["name"] == TAB), None)
        if tab is None:
            return f"{arm} has no {TAB} tab"
        lit = tab["vars"].get(VAR)
        if not isinstance(lit, Mapping) or lit.get("value") is not (arm == "B"):
            return f"{arm}'s {TAB} tab does not hold {VAR} = {arm == 'B'}"
        for var in (s7.FLY_VAR, s8.VAR):
            on = tab["vars"].get(var)
            if not isinstance(on, Mapping) or on.get("value") is not True:
                return f"{arm}'s {TAB} tab does not hold {var} = True (both arms)"
        tab["vars"].pop(VAR)
    if a != b:
        return "B differs from A in more than its fly_first_land block (an A/B changes one thing)"
    return None


def runner_problem(runner_text: str) -> str | None:
    """PURE: the checkout's runner is 9.60: it takes --fly-first-land."""
    if f'FLY_LAND_VERSION = "{VERSION}"' not in runner_text or f'"{FLAG}",' not in runner_text:
        return f"the checkout's runner is not dungeon@{VERSION} (no {FLAG})"
    return None


def plan_doc(label: str, pairs: int, minutes: float, order: str, folder: Path,
             runner_text: str | None = None, bases: Mapping[str, str] | None = None,
             seeds: int = SEEDS) -> dict[str, Any] | str:  # fmt: skip
    """PURE but for reads (the fixture, git, the checkout's runner): everything a series will do,
    before any screen is read or any input path opened; a refusal: its words. ``bases``: the
    proofs' base texts by name, else git's."""
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
    need = ("garm_fly", "alarm_fast", "fly_first", "fly_first_hp")
    if not all(vals["A"].get(k) for k in need):
        return f"refused before any input: {' / '.join(need)} not all on in the Run config"
    runner_text = hc.TARGET.read_text() if runner_text is None else runner_text
    bad = runner_problem(runner_text)
    if bad:
        return f"refused before any input: {bad}"
    revs = {"drive": hc.DRIVE_BASE, "check": hc.BASE_REV, "flag": hc.FLAG_BASE,
            "pick": hc.PICK_BASE, "land": hc.LAND_BASE}  # fmt: skip
    got_b = {k: (bases or {}).get(k) or hc.git_show(rev, hc.TARGET) for k, rev in revs.items()}
    proofs = (("drive", _quiet(hc.drive_check, got_b["drive"], runner_text)),
              ("check", _quiet(hc.check, got_b["check"], runner_text, drive_ok=True)),
              ("flag", _quiet(hc.flag_check, got_b["flag"], runner_text)),
              ("pick", _quiet(hc.pick_check, got_b["pick"], runner_text)),
              ("land", _quiet(hc.land_check, got_b["land"], runner_text)))  # fmt: skip
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
                     "fly_first_land": arm == "B", "project_hash": h, "loop": rp.loop,
                     "left_out": list(rp.tick_left_out), "box": rp.box_kwargs(),
                     "keys": rp.keys}  # fmt: skip
    for flag in ("--fly-first", "--fly-first-hp"):
        if flag not in argv["A"]:
            return f"refused before any input: A's runner argv has no {flag}"
    if FLAG in argv["A"] or argv["B"].count(FLAG) != 1:
        return f"refused before any input: {FLAG} must be in B's runner argv alone"
    if [x for x in argv["B"] if x != FLAG] != argv["A"]:
        return f"refused before any input: the arms' runner argv differ in more than {FLAG}"
    for k in ("box", "keys", "loop", "left_out"):
        if arms["A"][k] != arms["B"][k]:
            return f"refused before any input: the arms give the runner different {k}"
    if (arms["A"]["box"].get("box_model") or {}).get("id") != MODEL:
        return f"refused before any input: the box's model is not {MODEL}"
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
        "check_base": hc.BASE_REV, "flag_base": hc.FLAG_BASE, "pick_base": hc.PICK_BASE,
        "land_base": hc.LAND_BASE, "runner_sha256": s5b.sha(runner_text),
        "trace_scenarios": len(scns),
        "serve_s": int(len(runs) * (minutes * 60 + s2.START_GRACE_S + 120) + s2.SERVE_EXTRA_S),
        "runs": [{**asdict(r), "argv": fr.play_command(
            s4.project_file(r.arm, folder), NODE, r.label, folder / f"{r.label}.STOP",
            int(round(minutes * 60)), hashes[r.arm], folder / f"runner-config-{r.arm}.json")}
            for r in runs],
    }  # fmt: skip


# --- the stale re-fires (the runner's records) -------------------------------------------------
@dataclass(frozen=True)
class Refire:
    t_key_ns: int
    grab_ns: int  # its sighting's grab time (sight.t_ns)
    prev_key_ns: int  # the previous Fly Wing's key
    land_s: float  # the window it is judged by
    cls: str | None

    @property
    def after_prev_s(self) -> float:
        return round((self.grab_ns - self.prev_key_ns) / 1e9, 3)


def land_of(events: Sequence[Mapping[str, Any]], default: float = LAND_S) -> float:
    """PURE: the run's own window: its run_start's fixes.fly_first_land [FF_LAND_S, version], else
    ``default`` (A: the bar's)."""
    for e in events:
        if e.get("kind") == "run_start":
            got = (e.get("fixes") or {}).get("fly_first_land")
            if isinstance(got, list | tuple) and got and isinstance(got[0], int | float):
                return float(got[0])
    return default


def fly_keys(events: Sequence[Mapping[str, Any]]) -> list[int]:
    """PURE: every Fly Wing's key of a session (its fly_first fly and land records), sorted."""
    return sorted({int(e["t_key_ns"]) for e in events if e.get("kind") == s7.FLY_KIND
                   and e.get("what") in ("fly", "land")
                   and e.get("t_key_ns") is not None})  # fmt: skip


def refires_of(events: Sequence[Mapping[str, Any]], land_s: float) -> tuple[list[Refire], int]:
    """PURE: one session's alarm boss Fly Wings judged against the previous key + ``land_s``:
    (the stale ones, how many alarm boss Fly Wings in all)."""
    keys = fly_keys(events)
    stale: list[Refire] = []
    n = 0
    for e in events:
        if e.get("kind") != s7.FLY_KIND or e.get("what") != "fly" or e.get("src") != "alarm":
            continue
        sight = e.get("sight") or {}
        if sight.get("t_ns") is None or e.get("t_key_ns") is None:
            continue
        n += 1
        tk, grab = int(e["t_key_ns"]), int(sight["t_ns"])
        prev = max((k for k in keys if k < tk), default=None)
        if prev is not None and grab <= prev + land_s * 1e9:
            stale.append(Refire(tk, grab, prev, land_s, sight.get("cls")))
    return stale, n


@dataclass
class Score10(s9.Score9):
    stale: list[Refire] = field(default_factory=list)
    alarm_flies: int = 0
    land_records: int = 0
    held: int = 0  # alarm detections grabbed inside a landing window (would-be stale sightings)

    def doc(self) -> dict[str, Any]:
        return {**super().doc(), "stale": [{**asdict(x), "after_prev_s": x.after_prev_s}
                                           for x in self.stale],
                "alarm_flies": self.alarm_flies, "land_records": self.land_records,
                "held": self.held}  # fmt: skip


ALARM_CLS = ("garm_baby", "g_gobline_xmas", "knight_of_windstorm")  # xmas02sk's alarm (18.15)
LOG_OFFSET_NS = 47_800_000  # 18.17: a detection's log time - its grab time (median, 70 matched)


def held_of(events: Sequence[Mapping[str, Any]], d: Path, land_s: float) -> int:
    """Reads one session's detections: alarm-class detections grabbed inside a Fly Wing's landing
    window (key, key + land_s] -- what B's floor refuses (reported)."""
    keys = fly_keys(events)
    n = 0
    for name in ("detections.jsonl", "detections_hud.jsonl"):
        p = d / name
        if not p.is_file():
            continue
        with p.open() as f:
            for line in f:
                if not any(c in line for c in ALARM_CLS):
                    continue
                r = json.loads(line)
                g = int(r["t_ns"]) - LOG_OFFSET_NS
                if any(k < g <= k + land_s * 1e9 for k in keys) and any(
                        b[5] in ALARM_CLS for b in r.get("boxes") or ()):  # fmt: skip
                    n += 1
    return n


def score_run(r: Mapping[str, Any], folder: Path, demo: Path = s2.DEMO,
              logs: Path = s7.INPUT_LOG, data: Path = s7.ECON_DATA,
              bar: Mapping[str, Any] = BAR) -> Score10:  # fmt: skip
    """Reads (no screen): stage9_ab's score of the run, then its stale re-fires."""
    base = s9.score_run(r, folder, demo, logs, data)
    sc = Score10(**{k: getattr(base, k) for k in base.__dataclass_fields__})
    for d in sorted(demo.glob(f"*-{r['label']}-hunt*")):
        if not (d / "events.jsonl").is_file():
            continue
        ev = s2.read_events(d / "events.jsonl")
        land_s = land_of(ev, float(bar["land_s"]))
        stale, n = refires_of(ev, land_s)
        sc.stale.extend(stale)
        sc.alarm_flies += n
        sc.land_records += sum(1 for e in ev if e.get("kind") == s7.FLY_KIND
                               and e.get("what") == "land")  # fmt: skip
        sc.held += held_of(ev, d, land_s)
    return sc


# --- the verdict -------------------------------------------------------------------------------
def stale_line(scores: Sequence[Score10]) -> dict[str, Any]:
    """PURE: BAR's stale line over the played runs: B's must be 0 (judged with >= 1 alarm boss Fly
    Wing in B); A's reported."""
    out: dict[str, Any] = {}
    for x in ("A", "B"):
        played = [s for s in scores if s.arm == x and s.found
                  and (s.minutes >= s5c.PLAYED_MIN or s.deaths)]  # fmt: skip
        out[x] = {"stale": sum(len(s.stale) for s in played),
                  "alarm_flies": sum(s.alarm_flies for s in played),
                  "land_records": sum(s.land_records for s in played),
                  "held": sum(s.held for s in played),
                  "where": [f"{s.label}: +{f.after_prev_s} s" for s in played
                            for f in s.stale]}  # fmt: skip
    b = out["B"]
    out["pass"] = None if b["alarm_flies"] == 0 else b["stale"] == 0
    return out


def model_report(scores: Sequence[Score10]) -> dict[str, Any]:
    """PURE but for the pins: every played run's box watcher loaded xmas02sk (its box_model
    records; plan's checks make it so: reported)."""
    import unit_detector as ud

    want = [ud.GPU_WEIGHTS[MODEL].onnx, MODEL]
    bad = [f"{s.label}: {s.box_models or 'no box_model record'}" for s in scores
           if s.found and (s.minutes >= s5c.PLAYED_MIN or s.deaths)
           and (not s.box_models or any(m != want for m in s.box_models))]  # fmt: skip
    return {"want": want, "problems": bad}


def verdict(scores: Sequence[Score10], minutes: float, a_kinds: set[str],
            bar: Mapping[str, Any] = BAR,
            econ: Mapping[str, Mapping[str, Any] | None] | None = None,
            ) -> dict[str, Any]:  # fmt: skip
    """PURE: the pre-registered bar (18.17). Deaths are JUDGED (stage5b_ab's line, B <= A)."""
    v = s5b.verdict(scores, minutes, set(a_kinds) | {s5c.DRIVE_KIND, s7.FLY_KIND}, bar)
    lines = dict(v.get("lines") or {})
    rep = dict(lines.get("report") or {})
    rep["arms"] = s7.report_of(scores, minutes, bar, econ)
    rep["alarm"] = s9.alarm_report(scores, minutes, {**s9.BAR, **bar})
    rep["false_flies_h"] = s9.false_line(scores, minutes, {**s9.BAR, **bar})
    rep["model"] = model_report(scores)
    lines["report"] = rep
    lines["drive"] = s5c.drive_line(scores)
    lines["stale"] = stale_line(scores)
    out = {**v, "lines": lines}
    if out.get("why") == "an arm has no valid run":
        out["verdict"] = "INCONCLUSIVE"
        return out
    judged = [x["pass"] for k, x in lines.items() if k != "report"]
    out["verdict"] = "FAIL" if False in judged else ("INCONCLUSIVE" if None in judged else "PASS")
    return out


def table(scores: Sequence[Score10]) -> str:
    """PURE: stage9_ab's table, then the stale re-fires and the held sightings."""
    rows = s9.table(scores).splitlines()
    out = [f"{rows[0]}  stale  held"]
    for s, row in zip(scores, rows[1:], strict=True):
        out.append(f"{row}  {len(s.stale):5d}  {s.held:4d}")
    return "\n".join(out)


class Series10(s2.Series):
    """stage2_ab's live series (the setup, the detect server, one run at a time), for A / B."""

    score_cmd = "stage10_ab.py"


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
            p.add_argument("--no-econ-update", action="store_true",
                           help="do not add the runs' sessions to "
                           "data/econ/lab.sqlite first")  # fmt: skip
    a = ap.parse_args(argv)
    folder = SCRATCH / a.label
    if a.cmd == "score":
        doc = json.loads((folder / "series.json").read_text())
        if not a.no_econ_update:  # Batt 2026-11-16 (17 #7): every run's economy in lab.sqlite
            print(s7.econ_update(doc["runs"]), flush=True)
        scores = [score_run(r, folder, bar=doc["bar"]) for r in doc["runs"]]
        base = (folder / "runner-5b1.py").read_text()
        v = verdict(scores, float(doc["minutes"]), s5b.base_kinds(base), doc["bar"],
                    econ=s7.econ_arms(scores, float(doc["minutes"])))  # fmt: skip
        if a.json:
            print(json.dumps({"runs": [s.doc() for s in scores], "verdict": v}, indent=1))
        else:
            print(table(scores))
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
    return Series10(got, folder).run()


if __name__ == "__main__":
    raise SystemExit(main())
