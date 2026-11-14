#!/usr/bin/env python3
"""Stage 5b-2's live A/B (docs/planning/live-blocks.md 14): the ONE box played by run()'s own
driver (A = B5b-1) against the same box plus its hunt tab, whose hunt loop plays the steps as
blocks (B = B5b-2) -- the SAME step sequence by construction (scripts/hunt_trace.py), alternating
runs on the lab's own Rogue on the lab rAthena's xmas_dun02 (player mode; the MVP alive).

THE ARMS differ ONLY in the box: both play the checkout's runner through `flow_play.py play`,
with the same runner settings (the boxes' setting blocks and keys, stage2_ab.same_vals):
- A (B5b-1): services/frontend/src/lib/flow/fixtures/project_xmas_dun02.json -- no hunt tab, so
  run() takes its own driver loop, which IS 5b-1's program (huntstate_check.py drive);
- B (B5b-2): fixtures/project_xmas_dun02_hunt.json -- the same box plus the tab hunt, the canonical
  loop (t = find_target(); fight_target(t)): run() calls the player's hook.drive.
`plan` refuses before any input unless: the two boxes take the same runner settings and keys and
the Run config has the fast alarm on (both arms: section 11); A has no hunt loop and B the
canonical one, and B is A plus that tab and nothing else; the checkout's run() without its drive
branch is 5b-1's (huntstate_check.drive_check); and the step traces of the driver and of B's loop
are equal on every hand scenario and on SEEDS random ones (hunt_trace.compare).

THE SETUP before every run: exactly stage2_ab.py's. A STOP file in the series folder
(/dev/shm/poring-lab-tmp/stage5b2-ab/<label>/STOP) ends the series before its next run.

THE SCORE per run: stage5b_ab's lines (stage5_ab's and the tick pace, the record kinds, a runner
exception), and the drive's own record (`drive`: its start, its end with the steps it passed and
how it ended). The verdict applies BAR (section 14).
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

VERSION = "9.55"  # dungeon_hunt.HUNT_BLOCKS_VERSION: the stage it measures
NODE = s2.NODE
PROJECTS = {"A": s4.FIX / "project_xmas_dun02.json", "B": s4.FIX / "project_xmas_dun02_hunt.json"}
ARMS = {"A": "B5b-1: the one box, run()'s own driver", "B": "B5b-2: the box with its hunt loop"}
SCRATCH = Path("/dev/shm/poring-lab-tmp/stage5b2-ab")
SEEDS = 50  # random step-trace scenarios the plan checks (hunt_trace.py), besides the hand ones
DRIVE_KIND = "drive"  # the drive's own record kind (dungeon_hunt.hunt_drive): B's only new kind
DRIVE_ENDS = ("time_box", "run_end")  # how a canonical loop's drive ends: the run's end, never
# a spin, a refusal or the loop returning
PLAYED_MIN = s5b.PLAYED_MIN
# THE PRE-REGISTERED BAR (live-blocks.md 14, written before any live run): what B must hold vs A --
# 13.5's lines, with A the 5b-1 program (the driver) and the drive's own line added
BAR = {
    "min_minutes_share": 0.8,  # a valid run: this share of M minutes, or a weight-home end
    "min_pairs": 3,  # fewer valid pairs: kills / h and loot / h are not judged
    "deaths": "B's deaths <= A's, over EVERY run that played (>= 1 min, or a death)",
    "kills_h_se": 2.0,  # mean paired (B - A) kills / h >= -this x its standard error
    "loot_h_se": 2.0,  # the same for the loot steps / h
    "openers_h_share": 0.20,  # B's Knife openers / h within +-this of A's (valid runs pooled)
    "pace_ms": 10.0,  # B's median and 95th-percentile hp_read gap each <= A's + this
    "kinds": "every record kind B's runner sessions write is one the 5b-1 runner's source writes "
             "(its literal kinds), one A's sessions wrote, or the drive's own (drive)",
    "errors": "no B run ends by an exception of the runner (a traceback in its log, or hunt_end "
              "`error` not a refusal)",
    "drive": "every B run that played drove (one drive start and one end in its runner session), "
             "passed no step, and its drive ended as the run did (time_box / run_end); no A run "
             "drove",
}  # fmt: skip


def _quiet(f: Any, *a: Any) -> tuple[int, str]:
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        rc = f(*a)
    return int(rc), out.getvalue()


def canonical_loop(body: Sequence[Mapping[str, Any]]) -> bool:
    """PURE: the hunt loop's body is the canonical one: `while True: t = find_target();
    fight_target(t)` (their default time boxes)."""
    if len(body) != 1 or body[0].get("kind") != "while":
        return False
    w = body[0]
    if w.get("cond") != {"kind": "lit", "value": True} or w.get("max_iter") or w.get("max_s"):
        return False
    steps = list(w.get("body") or [])
    if len(steps) != 2:
        return False
    a, b = steps
    return (a.get("kind") == b.get("kind") == "action" and a.get("block") == "find_target"
            and a.get("outcome_to") == "t" and a.get("timeout_s") == 120 and not a.get("params")
            and b.get("block") == "fight_target" and b.get("params") == {"target": {"kind": "var",
                                                                             "name": "t"}}
            and b.get("timeout_s") == 300 and b.get("outcome_to") is None)  # fmt: skip


def box_difference(a: Mapping[str, Any], b: Mapping[str, Any]) -> str | None:
    """PURE: B is A plus a tab `hunt` holding the canonical hunt_loop(t), and nothing else (but its
    name and description); else why not."""
    a, b = json.loads(json.dumps(a)), json.loads(json.dumps(b))
    tabs_a, tabs_b = a["nodes"][0]["tabs"], b["nodes"][0]["tabs"]
    hunt = [t for t in tabs_b if t["name"] == "hunt"]
    if [t for t in tabs_a if t["name"] == "hunt"]:
        return "A has a hunt tab (A plays run()'s own driver: no hunt loop)"
    if len(hunt) != 1:
        return "B has no hunt tab"
    tabs_b.remove(hunt[0])
    defs = hunt[0]["defs"]
    if (
        hunt[0].get("main")
        or hunt[0].get("vars")
        or len(defs) != 1
        or defs[0]["name"] != "hunt_loop"
    ):
        return "B's hunt tab holds more than hunt_loop(t)"
    if defs[0]["params"] != [{"name": "t", "default": None}] or not canonical_loop(defs[0]["body"]):
        return (
            "B's hunt_loop is not the canonical loop (while True: t = find_target(); "
            "fight_target(t))"
        )
    for d in (a, b):
        d.pop("name", None)
        d.pop("description", None)
    if a != b:
        return "B differs from A in more than its hunt tab (an A/B changes one thing)"
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
                     "loop": rp.loop, "box": rp.box_kwargs(), "keys": rp.keys}  # fmt: skip
    if arms["A"]["loop"] is not None or arms["B"]["loop"] != "hunt_loop":
        return "refused before any input: A must play run()'s driver and B its hunt loop"
    if arms["A"]["box"] != arms["B"]["box"] or arms["A"]["keys"] != arms["B"]["keys"]:
        return "refused before any input: the boxes give run() different arguments or keys"
    text_b = s2.project_text(minutes, PROJECTS["B"])
    scns = [*ht.hand_scenarios(), *ht.random_scenarios(seeds)]
    diff = [f"{s.name}: {r.first_diff}" for s in scns if not (r := ht.compare(s, text_b)).same]
    if diff:
        return ("refused before any input: the hunt loop's step trace is not the driver's "
                f"(hunt_trace.py): {'; '.join(diff[:3])}")  # fmt: skip
    runs = s2.series(label, pairs, order)
    return {
        "version": VERSION, "label": label, "pairs": pairs, "minutes": minutes, "order": order,
        "arms": arms, "vals": vals, "bar": BAR, "drive_base": hc.DRIVE_BASE,
        "runner_sha256": s5b.sha(runner_text), "trace_scenarios": len(scns),
        "serve_s": int(len(runs) * (minutes * 60 + s2.START_GRACE_S + 120) + s2.SERVE_EXTRA_S),
        "runs": [{**asdict(r), "argv": fr.play_command(
            s4.project_file(r.arm, folder), NODE, r.label, folder / f"{r.label}.STOP",
            int(round(minutes * 60)), hashes[r.arm], folder / "runner-config.json")}
            for r in runs],
    }  # fmt: skip


# --- the score (PURE over the sessions' events and logs) -----------------------------------------
@dataclass
class Score5b2(s5b.Score5b):
    drive_starts: int = 0  # the runner sessions' drive start records
    drive_ends: list[dict[str, Any]] = field(default_factory=list)  # their end records

    def doc(self) -> dict[str, Any]:
        return {**super().doc(), "drive_starts": self.drive_starts,
                "drive_ends": [{k: e.get(k) for k in ("ended", "words", "ticks", "passed")}
                               for e in self.drive_ends]}  # fmt: skip


def score_drive(sc: Score5b2, events: Sequence[Mapping[str, Any]]) -> None:
    """PURE: one runner session's drive records (dungeon_hunt.hunt_drive)."""
    for e in events:
        if e.get("kind") != DRIVE_KIND:
            continue
        if e.get("what") == "start":
            sc.drive_starts += 1
        elif e.get("what") in ("end", "refused"):
            sc.drive_ends.append(dict(e))


def score_run(r: Mapping[str, Any], folder: Path, demo: Path = s2.DEMO) -> Score5b2:
    """Reads (no screen): one run's sessions by its label and its log."""
    base = s5b.score_run(r, folder, demo)
    sc = Score5b2(**{k: getattr(base, k) for k in base.__dataclass_fields__})
    for d in sorted(demo.glob(f"*-{r['label']}-hunt*")):
        if (d / "events.jsonl").is_file():
            score_drive(sc, s2.read_events(d / "events.jsonl"))
    return sc


def drive_line(scores: Sequence[Score5b2]) -> dict[str, Any]:
    """PURE: the drive's own judged line (BAR["drive"])."""
    played = [s for s in scores if s.found and (s.minutes >= PLAYED_MIN or s.deaths)]
    bad: list[str] = []
    for s in played:
        if s.arm == "A" and (s.drive_starts or s.drive_ends):
            bad.append(f"{s.label}: A drove")
        if s.arm != "B":
            continue
        if s.drive_starts != 1 or len(s.drive_ends) != 1:
            bad.append(f"{s.label}: {s.drive_starts} drive starts, {len(s.drive_ends)} ends")
            continue
        e = s.drive_ends[0]
        if e.get("what") != "end" or e.get("ended") not in DRIVE_ENDS:
            bad.append(f"{s.label}: the drive ended {e.get('ended') or e.get('what')!r}")
        if e.get("passed"):
            bad.append(f"{s.label}: it passed steps {e.get('passed')}")
    return {"B_drove": sum(1 for s in played if s.arm == "B" and s.drive_starts),
            "problems": bad, "pass": not bad}  # fmt: skip


def verdict(scores: Sequence[Score5b2], minutes: float, a_kinds: set[str],
            bar: Mapping[str, Any] = BAR) -> dict[str, Any]:  # fmt: skip
    """PURE: the pre-registered bar (live-blocks.md 14). `a_kinds`: the 5b-1 runner text's kinds
    (the drive's own kind is allowed besides)."""
    v = s5b.verdict(scores, minutes, set(a_kinds) | {DRIVE_KIND}, bar)
    lines = dict(v.get("lines") or {})
    lines["drive"] = drive_line(scores)
    out = {**v, "lines": lines}
    if out.get("why") == "an arm has no valid run":
        return out
    judged = [x["pass"] for k, x in lines.items() if k != "report"]
    out["verdict"] = "FAIL" if False in judged else ("INCONCLUSIVE" if None in judged else "PASS")
    return out


def table(scores: Sequence[Score5b2]) -> str:
    """PURE: the per-run table (plain text): stage5b_ab's and the drive's end."""
    rows = s5b.table(scores).splitlines()
    out = [f"{rows[0]}  drive"]
    for s, row in zip(scores, rows[1:], strict=True):
        e = s.drive_ends[0] if s.drive_ends else {}
        passed = f" passed {e['passed']}" if e.get("passed") else ""
        out.append(f"{row}  {e.get('ended') or '-'}{passed}")
    return "\n".join(out)


class Series5b2(s2.Series):
    """stage2_ab's live series (the setup, the detect server, one run at a time), for A / B."""

    score_cmd = "stage5b2_ab.py"


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
            print(table(scores))
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
    return Series5b2(got, folder).run()


if __name__ == "__main__":
    raise SystemExit(main())
