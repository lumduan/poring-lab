#!/usr/bin/env python3
"""Stage 5c's live A/B (docs/planning/live-blocks.md 15.8): the hunt box (A = B5b-2: the runner
block with the hunt tab's loop, proven live in 14.11) against the ready-made box as functions in
tabs (B = B5c: main calls hunt_loop(), the role blocks, the full hunt_tick()) -- the SAME hunt core
by construction (the compiler lowers B to A's: project.lower_hunt_core), alternating runs on the
lab's own Rogue on the lab rAthena's xmas_dun02 (player mode; the MVP alive).

THE ARMS differ ONLY in the box's shape: both play the checkout's runner through `flow_play.py
play`, with the same runner settings (stage2_ab.same_vals):
- A (B5b-2): services/frontend/src/lib/flow/fixtures/project_xmas_dun02_hunt.json;
- B (B5c): fixtures/project_xmas_dun02_functions.json.
`plan` refuses before any input unless: the two boxes take the same runner settings and keys, and
the Run config has the fast alarm on (section 11); both give the same runner argv and run()
arguments; both drive the canonical loop and B's tick leaves no step out; B is A but for main's
hunt statement, the hunt tab's role blocks and loop default, the tick tab, the name and the
description; the checkout's run() without its drive branch is 5b-1's (huntstate_check.drive_check);
and the step traces of the driver and of each box's loop are equal on every hand scenario and on
SEEDS random ones (hunt_trace.compare).

THE SETUP before every run: exactly stage2_ab.py's. A STOP file in the series folder
(/dev/shm/poring-lab-tmp/stage5c-ab/<label>/STOP) ends the series before its next run.

THE SCORE per run: stage5b2_ab's (the tick pace, the record kinds, a runner exception, the drive's
records). The verdict applies BAR (15.8): 14.7's lines with 14.7a's pace line, and the drive line
for BOTH arms.
"""

from __future__ import annotations

import argparse
import contextlib
import io
import json
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
import stage5b2_ab as s5b2  # noqa: E402
import stage5b_ab as s5b  # noqa: E402

VERSION = "9.56"  # dungeon_hunt.RUNNER_BLOCKS_VERSION: the stage it measures
NODE = s2.NODE
PROJECTS = {"A": s4.FIX / "project_xmas_dun02_hunt.json",
            "B": s4.FIX / "project_xmas_dun02_functions.json"}  # fmt: skip
ARMS = {"A": "B5b-2: the runner block and the hunt tab's loop",
        "B": "B5c: the hunt core as functions in tabs"}  # fmt: skip
SCRATCH = Path("/dev/shm/poring-lab-tmp/stage5c-ab")
SEEDS = 50
DRIVE_KIND = s5b2.DRIVE_KIND
DRIVE_ENDS = s5b2.DRIVE_ENDS
PLAYED_MIN = s5b.PLAYED_MIN
# where B may differ from A (15.8): main's hunt statement, the hunt tab (its role blocks and its
# loop's default), the tick tab, the name and the description
B_ONLY_TABS = ("tick",)
# THE PRE-REGISTERED BAR (live-blocks.md 15.8, written 2026-11-15 13:17 ICT, before any 5c run)
BAR = {
    **{k: v for k, v in s5b2.BAR.items() if k != "drive"},
    "drive": "every run of EITHER arm that played drove (one drive start and one end in its runner "
             "session), passed no step, left none out, and its drive ended as the run did "
             "(time_box / run_end)",
}  # fmt: skip


def _quiet(f: Any, *a: Any) -> tuple[int, str]:
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        rc = f(*a)
    return int(rc), out.getvalue()


def box_difference(a: Mapping[str, Any], b: Mapping[str, Any]) -> str | None:
    """PURE: B is A in the new shape and nothing else (15.8) -- or why not. A: the runner block
    in main and the hunt tab's hunt_loop(t); B: hunt_loop() at that place, the same loop with a
    default, the role blocks naming exactly the runner block's functions, a full hunt_tick() in
    the tab tick."""
    from poring_flow import project as pj
    from poring_flow import tick as tk

    a, b = json.loads(json.dumps(a)), json.loads(json.dumps(b))
    na, nb = a["nodes"][0], b["nodes"][0]
    ma, mb = na["tabs"][0]["main"], nb["tabs"][0]["main"]
    ia = [i for i, st in enumerate(ma) if st.get("block") == "dungeon_hunt"]
    if len(ia) != 1:
        return "A's main has no runner block (A is the hunt box: the runner block, the hunt tab)"
    runner = ma[ia[0]]
    call = {"kind": "call", "proc": pj.HUNT_CALL, "args": [], "kwargs": {}}
    if len(mb) != len(ma) or mb[ia[0]] != call:
        return "B's main does not start its hunt core with hunt_loop() where A's runner block is"
    roles = {f"{pj.ROLE_PREFIX}{k}": v for k, v in runner["params"].items()}
    hunt_b = next((t for t in nb["tabs"] if t["name"] == "hunt"), None)
    hunt_a = next((t for t in na["tabs"] if t["name"] == "hunt"), None)
    if hunt_a is None or hunt_b is None:
        return "a box has no hunt tab"
    if hunt_b["vars"] != roles:
        return "B's role blocks do not name exactly the functions A's runner block names"
    la, lb = hunt_a["defs"], hunt_b["defs"]
    if len(la) != 1 or len(lb) != 1 or la[0]["body"] != lb[0]["body"]:
        return "B's hunt loop is not A's"
    if not s5b2.canonical_loop(lb[0]["body"]):
        return (
            "B's hunt loop is not the canonical loop "
            "(while True: t = find_target(); fight_target(t))"
        )
    tick = next((t for t in nb["tabs"] if t["name"] == tk.TICK_TAB), None)
    body = [st.get("block") for st in tick["defs"][0]["body"]] if tick and tick["defs"] else None
    if tick is None or len(tick["defs"]) != 1 or body != list(tk.STEP_BLOCKS) \
            or tick["defs"][0]["name"] != tk.TICK:  # fmt: skip
        return "B's tab tick is not the full hunt_tick() (every step, in run()'s order)"
    mb[ia[0]] = runner
    hunt_b["vars"] = hunt_a["vars"]
    lb[0]["params"] = la[0]["params"]
    nb["tabs"] = [t for t in nb["tabs"] if t["name"] not in B_ONLY_TABS]
    for d in (a, b):
        d.pop("name", None)
        d.pop("description", None)
    if a != b:
        return "B differs from A in more than its shape (an A/B changes one thing)"
    return None


def plan_doc(label: str, pairs: int, minutes: float, order: str, folder: Path,
             runner_text: str | None = None, base_text: str | None = None,
             seeds: int = SEEDS) -> dict[str, Any] | str:  # fmt: skip
    """PURE but for reads (the fixtures, git, the checkout's runner): everything a series will do,
    before any screen is read or any input path opened; a refusal: its words."""
    import flow_play as fp

    from poring_flow import project as pj

    vals = s2.same_vals(PROJECTS, minutes)
    if isinstance(vals, str):
        return f"refused before any input: {vals}"
    if not vals.get("alarm_fast"):
        return "refused before any input: the Run config has alarm_fast off (section 11's runs)"
    raw = {arm: json.loads(path.read_text()) for arm, path in PROJECTS.items()}
    why = box_difference(raw["A"], raw["B"])
    if why is not None:
        return f"refused before any input: {why}"
    runner_text = hc.TARGET.read_text() if runner_text is None else runner_text
    base_text = hc.git_show(hc.DRIVE_BASE, hc.TARGET) if base_text is None else base_text
    rc, out = _quiet(hc.drive_check, base_text, runner_text)
    if rc != 0:
        bad = [ln for ln in out.splitlines() if "NO" in ln or "CHANGED" in ln or "NONE" in ln]
        return ("refused before any input: the checkout's run() without its drive branch is not "
                f"5b-1's (huntstate_check.py drive): {'; '.join(bad)[:300]}")  # fmt: skip
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
        arms[arm] = {"what": ARMS[arm], "project": str(path.relative_to(ROOT)), "project_hash": h,
                     "loop": rp.loop, "left_out": list(rp.tick_left_out), "box": rp.box_kwargs(),
                     "keys": rp.keys, "argv": rp.argv("L", None, None)}  # fmt: skip
    if arms["A"]["loop"] != "hunt_loop" or arms["B"]["loop"] != "hunt_loop":
        return "refused before any input: both boxes must drive their hunt loop"
    if arms["B"]["left_out"] or arms["A"]["left_out"]:
        return "refused before any input: a box's tick leaves steps out (15.8: the full tick)"
    for k in ("box", "keys", "argv"):
        if arms["A"][k] != arms["B"][k]:
            return f"refused before any input: the boxes give the runner different {k}"
    scns = [*ht.hand_scenarios(), *ht.random_scenarios(seeds)]
    for arm in ("A", "B"):
        text = s2.project_text(minutes, PROJECTS[arm])
        diff = [f"{s.name}: {r.first_diff}" for s in scns if not (r := ht.compare(s, text)).same]
        if diff:
            return (f"refused before any input: {arm}'s hunt loop's step trace is not the driver's "
                    f"(hunt_trace.py): {'; '.join(diff[:3])}")  # fmt: skip
    runs = s2.series(label, pairs, order)
    for a in arms.values():
        a.pop("argv")
    return {
        "version": VERSION, "label": label, "pairs": pairs, "minutes": minutes, "order": order,
        "arms": arms, "vals": vals, "bar": BAR, "drive_base": hc.DRIVE_BASE,
        "runner_sha256": s5b.sha(runner_text), "trace_scenarios": 2 * len(scns),
        "serve_s": int(len(runs) * (minutes * 60 + s2.START_GRACE_S + 120) + s2.SERVE_EXTRA_S),
        "runs": [{**asdict(r), "argv": fr.play_command(
            s4.project_file(r.arm, folder), NODE, r.label, folder / f"{r.label}.STOP",
            int(round(minutes * 60)), hashes[r.arm], folder / "runner-config.json")}
            for r in runs],
    }  # fmt: skip


# --- the score: stage5b2_ab's, with the drive line for BOTH arms ---------------------------------
Score5c = s5b2.Score5b2
score_run = s5b2.score_run


def drive_line(scores: Sequence[s5b2.Score5b2]) -> dict[str, Any]:
    """PURE: the drive's judged line for both arms (BAR["drive"])."""
    played = [s for s in scores if s.found and (s.minutes >= PLAYED_MIN or s.deaths)]
    bad: list[str] = []
    for s in played:
        if s.drive_starts != 1 or len(s.drive_ends) != 1:
            bad.append(f"{s.label}: {s.drive_starts} drive starts, {len(s.drive_ends)} ends")
            continue
        e = s.drive_ends[0]
        if e.get("what") != "end" or e.get("ended") not in DRIVE_ENDS:
            bad.append(f"{s.label}: the drive ended {e.get('ended') or e.get('what')!r}")
        if e.get("passed"):
            bad.append(f"{s.label}: it passed steps {e.get('passed')}")
        if e.get("left_out"):
            bad.append(f"{s.label}: its tick left out {e.get('left_out')}")
    drove = {x: sum(1 for s in played if s.arm == x and s.drive_starts) for x in ("A", "B")}
    return {"drove": drove, "problems": bad, "pass": not bad}


def verdict(scores: Sequence[s5b2.Score5b2], minutes: float, a_kinds: set[str],
            bar: Mapping[str, Any] = BAR) -> dict[str, Any]:  # fmt: skip
    """PURE: the pre-registered bar (15.8). `a_kinds`: the 5b-1 runner text's kinds (the drive's
    own kind is allowed besides)."""
    v = s5b.verdict(scores, minutes, set(a_kinds) | {DRIVE_KIND}, bar)
    lines = dict(v.get("lines") or {})
    lines["drive"] = drive_line(scores)
    out = {**v, "lines": lines}
    if out.get("why") == "an arm has no valid run":
        return out
    judged = [x["pass"] for k, x in lines.items() if k != "report"]
    out["verdict"] = "FAIL" if False in judged else ("INCONCLUSIVE" if None in judged else "PASS")
    return out


class Series5c(s2.Series):
    """stage2_ab's live series (the setup, the detect server, one run at a time), for A / B."""

    score_cmd = "stage5c_ab.py"


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
        base = (folder / "runner-5b1.py").read_text()
        v = verdict(scores, float(doc["minutes"]), s5b.base_kinds(base))
        if a.json:
            print(json.dumps({"runs": [s.doc() for s in scores], "verdict": v}, indent=1))
        else:
            print(s5b2.table(scores))
            print(json.dumps({k: x for k, x in v.items() if k != "lines"} | {
                "lines": {k: x for k, x in v.get("lines", {}).items() if k != "report"}},
                indent=1))  # fmt: skip
        return 0
    if not 5 <= a.minutes <= 600:
        print("refused before any input: --minutes is the Run config's: 5..600", flush=True)
        return 2
    base_text = hc.git_show(hc.DRIVE_BASE, hc.TARGET)
    got = plan_doc(a.label, a.pairs, a.minutes, a.order, folder, base_text=base_text)
    if isinstance(got, str):
        print(got, flush=True)
        return 2
    if a.cmd == "plan":
        print(json.dumps(got, indent=1))
        return 0
    folder.mkdir(parents=True, exist_ok=False)  # a series' folder is never reused
    (folder / "series.json").write_text(json.dumps(got, indent=1) + "\n")
    (folder / "runner-5b1.py").write_text(base_text)  # the score's base kinds
    for arm, path in PROJECTS.items():
        s4.project_file(arm, folder).write_text(s2.project_text(a.minutes, path))
    (folder / "runner-config.json").write_text(json.dumps({NODE: got["vals"]}) + "\n")
    return Series5c(got, folder).run()


if __name__ == "__main__":
    raise SystemExit(main())
