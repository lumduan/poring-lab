#!/usr/bin/env python3
"""Judge a demo session's actions from its packets (docs/demonstrations.md §2), offline.

    demo_verify.py SESSION_DIR [SESSION_DIR ...] [--aid-gm 2000002] [--aid-player 2000001]

- Reads `demo.jsonl` and the session's `packets.jsonl.gz`.
- Fills each record's outcome with poring_dataset.verify (VERIFIER_VERSION) and writes
  `demo.verified.jsonl` beside them. The actor's stated cue is never consulted.
- Client-side windows (menu shortcuts) are judged on the session's snapshots by the anchor map
  (§2): the window absent before, present 1 s after.
- `interrupted.json` in a session (scripts/demo_interruptions.py: a human took the lease) makes
  those records `interrupted`: neither success nor fail, left out of the rate. Their re-runs are
  separate sessions (rule_run.py --rerun-of); give them all to score the rule as one set.
- Prints, per rule: attempts, verified successes, failures by cause, ambiguous by cause, and
  the time per attempt p50/p95. The bar (pre-registered) is >= 95 % of the non-ambiguous
  attempts, with at most 10 % ambiguous.

Packets are verification ground truth ONLY (ADR-0007): this runs after the fact, never in a loop
that acts.
"""

from __future__ import annotations

import argparse
import functools
import gzip
import json
import statistics
import sys
from collections import Counter
from pathlib import Path
from typing import Any

from poring_dataset import verify as V
from poring_env.demo import DemoRecord, Outcome, read

BAR = 0.95
MAX_AMBIGUOUS = 0.10


def load_events(session_dir: Path) -> list[dict[str, Any]]:
    path = session_dir / "packets.jsonl.gz"
    if not path.exists():
        raise SystemExit(f"no packets.jsonl.gz in {session_dir}")
    with gzip.open(path, "rt") as fh:
        return [json.loads(line) for line in fh if line.strip()]


ANCHORS = Path(__file__).resolve().parents[1] / "data" / "ui_anchors"


@functools.cache
def window_registry() -> Any:
    """The ADR-0011 anchor map with the cut templates (the menu verifier's screen check)."""
    from poring_env import ui_anchors as ua

    return ua.default_registry(ANCHORS)


def windows_on(session_dir: Path, ref: str | None) -> set[str] | None:
    """The windows whose anchors are found on a snapshot of this session, or None (no frame)."""
    if not ref or ref.startswith("session:"):
        return None
    from poring_dataset.shards import decode_png

    return set(window_registry().locate(decode_png((session_dir / ref).read_bytes())[:, :, :3]))


def judge_window(rec: DemoRecord, session_dir: Path | None) -> V.Verdict:
    """§2 menu shortcut: the window's anchor absent before, present 1 s after (the snapshots)."""
    w = rec.action.intended.window
    if w is None or session_dir is None:
        return V.Verdict("ambiguous", "no window or no session to judge on")
    if w not in window_registry().templates:
        return V.Verdict("ambiguous", f"no cut anchor for {w}")
    before = windows_on(session_dir, rec.frame.ref)
    after = windows_on(session_dir, rec.frame_after.ref if rec.frame_after else None)
    if before is None or after is None:
        return V.Verdict("ambiguous", "a snapshot is missing")
    v = V.verify_menu(w in before, w in after)
    evidence = {"before": sorted(before), "after": sorted(after)}
    return V.Verdict(v.status, v.cause, {**v.evidence, **evidence})


def judge(
    rec: DemoRecord,
    events: list[dict[str, Any]],
    aids: dict[str, int],
    t_end: int | None = None,
    session_dir: Path | None = None,
) -> V.Verdict | None:
    """``t_end``: the next record's start; no window reaches into the next action."""
    """None = not a scored action (the harness's own records)."""
    if rec.actor.startswith("rule:harness@"):
        return None
    kind = rec.action.type
    decline = rec.outcome.evidence.get("decline") or rec.outcome.evidence.get("rule_decline")
    if decline:
        return V.Verdict("fail", f"declined:{decline}")  # pre-registered: a decline is a FAIL
    if kind == "login":
        return V.verify_login(events, rec.t_mono_ns, aids[rec.action.intended.note or "gm"], t_end)
    if kind == "walk" and rec.action.intended.kind == "route":
        # walk@5: end to end -- where the packets put us when the route ended (+0.5 s)
        goal = rec.action.intended.cell
        end = V.position_before(events, (rec.t_done_ns or rec.t_mono_ns) + 500_000_000, aids["gm"])
        if goal is None or end is None:
            return V.Verdict("ambiguous", "no goal or no position fix at the route's end")
        if tuple(end) == tuple(goal):
            return V.Verdict("success", None, {"end": list(end)})
        return V.Verdict(
            "fail", "the route ended elsewhere", {"end": list(end), "goal": list(goal)}
        )
    if kind == "walk":
        aid = aids["gm"]
        start = V.position_before(events, rec.t_mono_ns, aid)
        cell = rec.action.intended.cell
        if start is None or cell is None:
            return V.Verdict("ambiguous", "no position fix before the click")
        target = (start[0] + cell[0], start[1] + cell[1]) if rec.action.intended.relative else cell
        speed = V.speed_before(events, rec.t_mono_ns)
        return V.verify_walk(events, rec.t_mono_ns, aid, target, speed, t_end)
    if kind == "menu_shortcut":
        return judge_window(rec, session_dir)
    return V.Verdict("ambiguous", f"no verifier for {kind} yet")


def summarise(rows: list[tuple[DemoRecord, V.Verdict]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    by_rule: dict[str, list[tuple[DemoRecord, V.Verdict]]] = {}
    for rec, v in rows:
        by_rule.setdefault(rec.rule or rec.actor, []).append((rec, v))
    for rule, all_rs in by_rule.items():
        rs = [(rec, v) for rec, v in all_rs if v.status != "interrupted"]
        status = Counter(v.status for _, v in rs)
        n_amb = status["ambiguous"]
        scored = len(rs) - n_amb
        secs = [((rec.t_done_ns or rec.t_mono_ns) - rec.t_mono_ns) / 1e9 for rec, _ in rs]
        q = sorted(secs)
        rate = status["success"] / scored if scored else 0.0
        out[rule] = {
            "attempts": len(rs), "interrupted": len(all_rs) - len(rs),
            "verified_success": status["success"], "fail": status["fail"],
            "ambiguous": n_amb, "success_rate": round(rate, 4),
            "fail_causes": dict(Counter(v.cause for _, v in rs if v.status == "fail")),
            "ambiguous_causes": dict(Counter(v.cause for _, v in rs if v.status == "ambiguous")),
            "seconds_p50": round(statistics.median(secs), 1) if secs else None,
            "seconds_p95": round(q[int(0.95 * (len(q) - 1))], 1) if q else None,
            "verdict": ("INCONCLUSIVE (ambiguous > 10 %)"
                        if len(rs) and n_amb / len(rs) > MAX_AMBIGUOUS
                        else "PASS" if rate >= BAR else "FAIL"),
        }  # fmt: skip
    return out


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("session_dirs", type=Path, nargs="+")
    ap.add_argument("--aid-gm", type=int, default=2000002)
    ap.add_argument("--aid-player", type=int, default=2000001)
    a = ap.parse_args()
    aids = {"gm": a.aid_gm, "player": a.aid_player}
    rows: list[tuple[DemoRecord, V.Verdict]] = []
    n_events = 0
    for session_dir in a.session_dirs:
        records = read(session_dir / "demo.jsonl")
        events = load_events(session_dir)
        n_events += len(events)
        marks_path = session_dir / "interrupted.json"
        marks: dict[str, str] = json.loads(marks_path.read_text()) if marks_path.exists() else {}
        out_lines = []
        starts = sorted(r.t_mono_ns for r in records)
        for rec in records:
            later = [t for t in starts if t > rec.t_mono_ns]
            if rec.record_id in marks:
                v: V.Verdict | None = V.Verdict("interrupted", marks[rec.record_id][:200])
            else:
                v = judge(rec, events, aids, later[0] if later else None, session_dir)
            if v is None:
                out_lines.append(rec.model_dump_json())
                continue
            rows.append((rec, v))
            evidence = {**rec.outcome.evidence, **v.evidence}
            outcome = Outcome(
                status=v.status,  # type: ignore[arg-type]
                verifier=v.verifier,
                cause=v.cause,
                evidence=evidence,
            )
            done = rec.model_copy(update={"outcome": outcome})
            out_lines.append(done.model_dump_json())
        (session_dir / "demo.verified.jsonl").write_text("".join(x + "\n" for x in out_lines))
    sessions = [d.name for d in a.session_dirs]
    print(json.dumps({"sessions": sessions, "verifier": f"verify@{V.VERIFIER_VERSION}",
                      "events": n_events, "rules": summarise(rows)}, indent=1))  # fmt: skip
    return 0


if __name__ == "__main__":
    sys.exit(main())
