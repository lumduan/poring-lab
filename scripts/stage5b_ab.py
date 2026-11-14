#!/usr/bin/env python3
"""Stage 5b-1's live A/B (docs/planning/live-blocks.md 13.5): the runner as main eb160ee1 had it
(A) against 5b-1's runner, HuntState and the loop as steps (B) -- the SAME program by
construction (scripts/huntstate_check.py) -- alternating runs of the ONE box on the lab's own Rogue
on the lab rAthena's xmas_dun02 (player mode; the MVP alive).

THE ARMS differ ONLY in the runner's file: both play services/frontend/src/lib/flow/fixtures/
project_xmas_dun02.json through `flow_play.py play`, with the same runner settings (the box's
setting blocks and keys), each launched by scripts/runner_pin.py with its own pinned runner text:
- A: `git show eb160ee1:scripts/dungeon_hunt.py` (its sha256 pinned here: A_SHA256);
- B: the checkout's scripts/dungeon_hunt.py at plan time (its sha256 recorded in series.json).
`plan` refuses before any input unless B IS the 5b-1 rewrite of A (huntstate_check.check) and
the Run config has the fast alarm on (both arms: section 11).

THE SETUP before every run: exactly stage2_ab.py's. A STOP file in the series folder
(/dev/shm/poring-lab-tmp/stage5b-ab/<label>/STOP) ends the series before its next run.

THE SCORE per run: stage5_ab's lines, and from the same runner session the tick pace (the gaps
between consecutive hp_read records: one a tick) and the record kinds it wrote; from the run's log
a runner exception (a traceback) and the launcher's record (which text ran). The verdict applies
BAR (13.5).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import statistics
import sys
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import flow_run as fr  # noqa: E402
import huntstate_check as hc  # noqa: E402
import stage2_ab as s2  # noqa: E402
import stage4_ab as s4  # noqa: E402
import stage5_ab as s5  # noqa: E402

VERSION = "9.54"  # dungeon_hunt.HUNT_STEPS_VERSION: the stage it measures
NODE = s2.NODE
PROJECT = s4.FIX / "project_xmas_dun02.json"
SCRATCH = Path("/dev/shm/poring-lab-tmp/stage5b-ab")
BASE_REV = hc.BASE_REV
# sha256 of `git show eb160ee1:scripts/dungeon_hunt.py`
A_SHA256 = "a1bb5728bdbb528a856cbad9939dc30fb8aa6eba192b2f50f3466f6913c93479"
PLAYED_MIN = s5.PLAYED_MIN
TRACEBACK = "Traceback (most recent call last)"
# THE PRE-REGISTERED BAR (live-blocks.md 13.5, written before any live run): what B must hold vs A
BAR = {
    "min_minutes_share": 0.8,  # a valid run: this share of M minutes, or a weight-home end
    "min_pairs": 3,  # fewer valid pairs: kills / h and loot / h are not judged
    "deaths": "B's deaths <= A's, over EVERY run that played (>= 1 min, or a death)",
    "kills_h_se": 2.0,  # mean paired (B - A) kills / h >= -this x its standard error
    "loot_h_se": 2.0,  # the same for the loot steps / h
    "openers_h_share": 0.20,  # B's Knife openers / h within +-this of A's (valid runs pooled)
    "pace_ms": 10.0,  # B's median and 95th-percentile hp_read gap each <= A's + this
    "kinds": "every record kind B's runner sessions write is one the base runner's source writes "
             "(its literal kinds) or A's sessions wrote",
    "errors": "no B run ends by an exception of the runner (a traceback in its log, or hunt_end "
              "`error` not a refusal)",
}  # fmt: skip
KIND_RE = re.compile(r"""["']kind["']\s*:\s*["']([a-z_0-9]+)["']""")


def git_text(rev: str) -> str:
    return hc.git_show(rev, hc.TARGET)


def sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def base_kinds(text: str) -> set[str]:
    """PURE: the record kinds a runner text writes literally (`"kind": "..."`)."""
    return set(KIND_RE.findall(text))


def pin_argv(argv: Sequence[str], text_file: Path, sha256: str, record: Path) -> list[str]:
    """PURE: flow_run.play_command's argv, launched by runner_pin.py with a pinned runner text."""
    i = list(argv).index("scripts/flow_play.py")
    return [*argv[:i], "scripts/runner_pin.py", "--text", str(text_file), "--sha256", sha256,
            "--record", str(record), "--", *argv[i:]]  # fmt: skip


def same_program(a_text: str, b_text: str) -> str | None:
    """B is the 5b-1 rewrite of A (huntstate_check.check, as ASTs), or why not."""
    import contextlib
    import io

    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        rc = hc.check(a_text, b_text)
    if rc == 0:
        return None
    bad = [ln for ln in out.getvalue().splitlines() if "NO" in ln or "DIFFERS" in ln
           or ("missing" in ln and "missing none" not in ln)]  # fmt: skip
    return "B is not the 5b-1 rewrite of A: " + ("; ".join(bad) or "huntstate_check failed")[:300]


def plan_doc(label: str, pairs: int, minutes: float, order: str, folder: Path,
             a_text: str | None = None,
             b_text: str | None = None) -> dict[str, Any] | str:  # fmt: skip
    """PURE but for reads (git, the fixture, the checkout's runner): everything a series will do,
    before any screen is read or any input path opened; a refusal: its words."""
    import flow_play as fp

    from poring_flow import project as pj

    a_text = git_text(BASE_REV) if a_text is None else a_text
    b_text = hc.TARGET.read_text() if b_text is None else b_text
    if sha(a_text) != A_SHA256:
        return f"refused before any input: A's text ({BASE_REV}) is not the pinned one"
    why = same_program(a_text, b_text)
    if why is not None:
        return f"refused before any input: {why}"
    vals = s2.same_vals({"A": PROJECT, "B": PROJECT}, minutes)
    if isinstance(vals, str):
        return f"refused before any input: {vals}"
    if not vals.get("alarm_fast"):
        return "refused before any input: the Run config has alarm_fast off (section 11's runs)"
    text = s2.project_text(minutes, PROJECT)
    h = pj.project_hash(pj.from_json(text))
    prep = fp.prepare(text, NODE, int(round(minutes * 60)), runner_vals={NODE: vals},
                      want_hash=h)  # fmt: skip
    if isinstance(prep, str):
        return f"the box: {prep}"
    rp = prep.runners[NODE]
    texts = {"A": (folder / "runner-A.py", sha(a_text)), "B": (folder / "runner-B.py", sha(b_text))}
    runs = s2.series(label, pairs, order)
    return {
        "version": VERSION, "label": label, "pairs": pairs, "minutes": minutes, "order": order,
        "base_rev": BASE_REV, "runner_sha256": {k: v[1] for k, v in texts.items()},
        "project": str(PROJECT.relative_to(ROOT)), "project_hash": h,
        "box_plays": sorted(rp.plays), "box_roles": rp.box_roles(), "vals": vals, "bar": BAR,
        "serve_s": int(len(runs) * (minutes * 60 + s2.START_GRACE_S + 120) + s2.SERVE_EXTRA_S),
        "runs": [{**asdict(r), "argv": pin_argv(fr.play_command(
            s4.project_file("box", folder), NODE, r.label, folder / f"{r.label}.STOP",
            int(round(minutes * 60)), h, folder / "runner-config.json"),
            texts[r.arm][0], texts[r.arm][1], folder / f"{r.label}.runner.json")}
            for r in runs],
    }  # fmt: skip


# --- the score (PURE over the sessions' events and logs) -----------------------------------------
@dataclass
class Score5b(s5.Score5):
    gaps_ms: list[float] = field(default_factory=list)  # consecutive hp_read gaps (one a tick)
    kinds: dict[str, int] = field(default_factory=dict)  # the runner sessions' record kinds
    error: str | None = None  # a runner exception (the log's traceback / hunt_end error)
    runner: dict[str, Any] | None = None  # runner_pin's record: which text ran

    def doc(self) -> dict[str, Any]:
        d = {k: v for k, v in super().doc().items() if k != "gaps_ms"}
        return {**d, "pace_ms": pace(self.gaps_ms)}


def pace(gaps: Sequence[float]) -> dict[str, float | None]:
    """PURE: the median and the 95th percentile of the tick gaps (ms)."""
    if not gaps:
        return {"median": None, "p95": None, "n": 0}
    g = sorted(gaps)
    return {"median": round(statistics.median(g), 1),
            "p95": round(g[min(len(g) - 1, int(math.ceil(0.95 * len(g))) - 1)], 1),
            "n": len(g)}  # fmt: skip


def score_pace(sc: Score5b, events: Iterable[Mapping[str, Any]]) -> None:
    """PURE: one runner session's tick gaps and record kinds."""
    last: int | None = None
    kinds: dict[str, int] = dict(sc.kinds)
    for e in events:
        k = str(e.get("kind"))
        kinds[k] = kinds.get(k, 0) + 1
        if k == "hp_read":
            t = int(e.get("t_ns") or 0)
            if last is not None and t > last:
                sc.gaps_ms.append((t - last) / 1e6)
            last = t
    sc.kinds = kinds


def score_errors(sc: Score5b, log_text: str, player_events: Iterable[Mapping[str, Any]]) -> None:
    """PURE: a runner exception -- a traceback in the run's log, or the player's hunt_end error
    that is not a start refusal (refusals are rc 2 / a "refused" in words)."""
    if TRACEBACK in log_text:
        tail = log_text[log_text.rindex(TRACEBACK) :].strip().splitlines()
        sc.error = (tail[-1] if tail else "a traceback")[:200]
    for e in player_events:
        err = e.get("error") if e.get("kind") == "hunt_end" else None
        if err and "refused" not in str(err):
            sc.error = sc.error or str(err)[:200]


def score_run(r: Mapping[str, Any], folder: Path, demo: Path = s2.DEMO) -> Score5b:
    """Reads (no screen): one run's sessions by its label, its log and its launcher record."""
    label, arm = str(r["label"]), str(r["arm"])
    sc = Score5b(label, arm, int(r["pair"]))
    for d in sorted(demo.glob(f"*-{label}-hunt*")):
        if (d / "events.jsonl").is_file():
            ev = s2.read_events(d / "events.jsonl")
            s2.score_runner(sc, ev)
            s5.s3.score_knife(sc, ev)
            s4.score_recipes(sc, ev)
            s5.score_eat(sc, ev)
            score_pace(sc, ev)
    player: list[dict[str, Any]] = []
    for d in sorted(demo.glob(f"*-play-{label}")):
        if (d / "events.jsonl").is_file():
            player = s2.read_events(d / "events.jsonl")
            s2.score_player(sc, player)
    log = folder / f"{label}.log"
    score_errors(sc, log.read_text(errors="replace") if log.is_file() else "", player)
    rec = folder / f"{label}.runner.json"
    if rec.is_file():
        sc.runner = json.loads(rec.read_text())
    return sc


def verdict(scores: Sequence[Score5b], minutes: float, a_kinds: set[str],
            bar: Mapping[str, Any] = BAR) -> dict[str, Any]:  # fmt: skip
    """PURE: the pre-registered bar (live-blocks.md 13.5). `a_kinds`: the base text's kinds."""
    ok_min = minutes * float(bar["min_minutes_share"])
    valid = {s.label for s in scores if s.found and (
        s.minutes >= ok_min or str(s.end or "").startswith("weight_home"))}  # fmt: skip
    played = [s for s in scores if s.found and (s.minutes >= PLAYED_MIN or s.deaths)]
    pairs: dict[int, dict[str, Score5b]] = {}
    for s in scores:
        pairs.setdefault(s.pair, {})[s.arm] = s
    good = [p for p in pairs.values() if set(p) == {"A", "B"}
            and p["A"].label in valid and p["B"].label in valid]  # fmt: skip
    arm = {x: [s for s in scores if s.arm == x and s.label in valid] for x in ("A", "B")}
    deaths = {x: sum(s.deaths for s in played if s.arm == x) for x in ("A", "B")}
    out: dict[str, Any] = {"pairs_valid": len(good), "pairs": len(pairs),
                           "invalid": sorted({s.label for s in scores} - valid),
                           "played": {x: sum(1 for s in played if s.arm == x)
                                      for x in ("A", "B")}}  # fmt: skip
    seen_a = {k for s in scores if s.arm == "A" for k in s.kinds}
    new_kinds = sorted({k for s in scores if s.arm == "B" for k in s.kinds} - a_kinds - seen_a)
    errs = [f"{s.label}: {s.error}" for s in scores if s.arm == "B" and s.error]
    lines: dict[str, Any] = {
        "deaths": {**deaths, "pass": deaths["B"] <= deaths["A"]},
        "kinds": {"new_in_B": new_kinds, "pass": not new_kinds},
        "errors": {
            "B": errs,
            "A": [f"{s.label}: {s.error}" for s in scores if s.arm == "A" and s.error],
            "pass": not errs,
        },  # fmt: skip
    }
    if not arm["A"] or not arm["B"]:
        return {**out, "lines": lines, "verdict": "INCONCLUSIVE", "why": "an arm has no valid run"}

    def pooled(x: str, f: Callable[[Score5b], float], g: Callable[[Score5b], float]) -> float:
        den = sum(g(s) for s in arm[x])
        return sum(f(s) for s in arm[x]) / den if den > 0 else 0.0

    op = {x: round(pooled(x, lambda s: s.openers * 60.0, lambda s: s.minutes), 1)
          for x in ("A", "B")}  # fmt: skip
    share = float(bar["openers_h_share"])
    lines["openers_h"] = {**op, "pass": op["A"] * (1 - share) <= op["B"] <= op["A"] * (1 + share)}
    pa = {x: pace([g for s in arm[x] for g in s.gaps_ms]) for x in ("A", "B")}
    lim = float(bar["pace_ms"])
    ok_pace = None if pa["A"]["median"] is None or pa["B"]["median"] is None else (
        pa["B"]["median"] <= pa["A"]["median"] + lim  # type: ignore[operator]
        and pa["B"]["p95"] <= pa["A"]["p95"] + lim)  # type: ignore[operator]  # fmt: skip
    lines["pace"] = {**pa, "pass": ok_pace}
    for key, attr, se_key in (("kills_h", "kills", "kills_h_se"),
                              ("loot_h", "loot_steps", "loot_h_se")):  # fmt: skip
        d = [p["B"].per_h(getattr(p["B"], attr)) - p["A"].per_h(getattr(p["A"], attr))
             for p in good]  # fmt: skip
        if d:
            mean_d = statistics.fmean(d)
            se = statistics.stdev(d) / math.sqrt(len(d)) if len(d) > 1 else float("inf")
            lines[key] = {"mean_diff_h": round(mean_d, 1),
                          "se_h": None if math.isinf(se) else round(se, 1),
                          "pairs": [round(x, 1) for x in d],
                          "pass": None if len(good) < int(bar["min_pairs"])
                          else mean_d >= -float(bar[se_key]) * se}  # fmt: skip
        else:
            lines[key] = {"pass": None}
    rate = {x: {k: round(sum(s.kinds.get(k, 0) for s in arm[x]) * 60.0
                         / max(1e-9, sum(s.minutes for s in arm[x])), 1)
                for k in sorted({k for s in arm[x] for k in s.kinds})}
            for x in ("A", "B")}  # fmt: skip
    lines["report"] = {
        "potions_h": {x: round(pooled(x, lambda s: s.potions * 60.0, lambda s: s.minutes), 1)
                      for x in ("A", "B")},
        "flies_h": {x: round(pooled(x, lambda s: s.flies_no_end * 60.0, lambda s: s.minutes), 1)
                    for x in ("A", "B")},
        "steals_h": {x: round(pooled(x, lambda s: s.steals * 60.0, lambda s: s.minutes), 1)
                     for x in ("A", "B")},
        "eats_h": {x: round(pooled(x, lambda s: s.eats * 60.0, lambda s: s.minutes), 1)
                   for x in ("A", "B")},
        "hp_low": {x: min((s.hp_low for s in arm[x] if s.hp_low is not None), default=None)
                   for x in ("A", "B")},
        "ends": {x: [s.end for s in scores if s.arm == x] for x in ("A", "B")},
        "kinds_h": rate,
        "runner": {s.label: s.runner for s in scores},
        "report_only": True}  # fmt: skip
    judged = [v["pass"] for k, v in lines.items() if k != "report"]
    if False in judged:
        v_ = "FAIL"
    elif None in judged:
        v_ = "INCONCLUSIVE"
    else:
        v_ = "PASS"
    return {**out, "lines": lines, "verdict": v_}


def table(scores: Sequence[Score5b]) -> str:
    """PURE: the per-run table (plain text, the report's)."""
    head = (f"{'run':<20}{'arm':<4}{'min':>6}{'death':>6}{'kills/h':>9}{'loot/h':>8}"
            f"{'open/h':>8}{'tick ms':>9}{'p95':>7}{'err':>5}  end")  # fmt: skip
    rows = [head]
    for s in scores:
        p = pace(s.gaps_ms)
        rows.append(
            f"{s.label:<20}{s.arm:<4}{s.minutes:>6.1f}{s.deaths:>6}{s.per_h(s.kills):>9.1f}"
            f"{s.per_h(s.loot_steps):>8.1f}{s.per_h(s.openers):>8.1f}"
            f"{p['median'] if p['median'] is not None else '-':>9}"
            f"{p['p95'] if p['p95'] is not None else '-':>7}{'yes' if s.error else '-':>5}"
            f"  {s.end or '-'}"
        )
    return "\n".join(rows)


class Series5b(s2.Series):
    """stage2_ab's live series (the setup, the detect server, one run at a time), for A / B."""

    score_cmd = "stage5b_ab.py"


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
        a_text = (folder / "runner-A.py").read_text()
        v = verdict(scores, float(doc["minutes"]), base_kinds(a_text))
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
    a_text, b_text = git_text(BASE_REV), hc.TARGET.read_text()
    got = plan_doc(a.label, a.pairs, a.minutes, a.order, folder, a_text, b_text)
    if isinstance(got, str):
        print(got, flush=True)
        return 2
    if a.cmd == "plan":
        print(json.dumps(got, indent=1))
        return 0
    folder.mkdir(parents=True, exist_ok=False)  # a series' folder is never reused
    (folder / "runner-A.py").write_text(a_text)
    (folder / "runner-B.py").write_text(b_text)
    (folder / "series.json").write_text(json.dumps(got, indent=1) + "\n")
    s4.project_file("box", folder).write_text(s2.project_text(a.minutes, PROJECT))
    (folder / "runner-config.json").write_text(json.dumps({NODE: got["vals"]}) + "\n")
    return Series5b(got, folder).run()


if __name__ == "__main__":
    raise SystemExit(main())
