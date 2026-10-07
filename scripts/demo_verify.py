#!/usr/bin/env python3
"""Judge a demo session's actions from its packets (docs/demonstrations.md §2), offline.

    demo_verify.py SESSION_DIR [--aid-gm 2000002] [--aid-player 2000001]

- Reads `demo.jsonl` and the session's `packets.jsonl.gz`.
- Fills each record's outcome with poring_dataset.verify (VERIFIER_VERSION) and writes
  `demo.verified.jsonl` beside them. The actor's stated cue is never consulted.
- Prints, per rule: attempts, verified successes, failures by cause, ambiguous by cause, and
  the time per attempt p50/p95. The bar (pre-registered) is >= 95 % of the non-ambiguous
  attempts, with at most 10 % ambiguous.

Packets are verification ground truth ONLY (ADR-0007): this runs after the fact, never in a loop
that acts.
"""

from __future__ import annotations

import argparse
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


def judge(rec: DemoRecord, events: list[dict[str, Any]], aids: dict[str, int]) -> V.Verdict | None:
    """None = not a scored action (the harness's own records)."""
    if rec.actor.startswith("rule:harness@"):
        return None
    kind = rec.action.type
    decline = rec.outcome.evidence.get("decline") or rec.outcome.evidence.get("rule_decline")
    if decline:
        return V.Verdict("fail", f"declined:{decline}")  # pre-registered: a decline is a FAIL
    if kind == "login":
        return V.verify_login(events, rec.t_mono_ns, aids[rec.action.intended.note or "gm"])
    if kind == "walk":
        aid = aids["gm"]
        start = V.position_before(events, rec.t_mono_ns, aid)
        cell = rec.action.intended.cell
        if start is None or cell is None:
            return V.Verdict("ambiguous", "no position fix before the click")
        target = (start[0] + cell[0], start[1] + cell[1]) if rec.action.intended.relative else cell
        return V.verify_walk(
            events, rec.t_mono_ns, aid, target, V.speed_before(events, rec.t_mono_ns)
        )
    return V.Verdict("ambiguous", f"no verifier for {kind} yet")


def summarise(rows: list[tuple[DemoRecord, V.Verdict]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    by_rule: dict[str, list[tuple[DemoRecord, V.Verdict]]] = {}
    for rec, v in rows:
        by_rule.setdefault(rec.rule or rec.actor, []).append((rec, v))
    for rule, rs in by_rule.items():
        status = Counter(v.status for _, v in rs)
        n_amb = status["ambiguous"]
        scored = len(rs) - n_amb
        secs = [((rec.t_done_ns or rec.t_mono_ns) - rec.t_mono_ns) / 1e9 for rec, _ in rs]
        q = sorted(secs)
        rate = status["success"] / scored if scored else 0.0
        out[rule] = {
            "attempts": len(rs), "verified_success": status["success"], "fail": status["fail"],
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
    ap.add_argument("session_dir", type=Path)
    ap.add_argument("--aid-gm", type=int, default=2000002)
    ap.add_argument("--aid-player", type=int, default=2000001)
    a = ap.parse_args()
    records = read(a.session_dir / "demo.jsonl")
    events = load_events(a.session_dir)
    aids = {"gm": a.aid_gm, "player": a.aid_player}
    rows: list[tuple[DemoRecord, V.Verdict]] = []
    out_lines = []
    for rec in records:
        v = judge(rec, events, aids)
        if v is None:
            out_lines.append(rec.model_dump_json())
            continue
        rows.append((rec, v))
        evidence = {**rec.outcome.evidence, **v.evidence}
        outcome = Outcome(
            status=v.status,
            verifier=v.verifier,
            cause=v.cause,  # type: ignore[arg-type]
            evidence=evidence,
        )
        done = rec.model_copy(update={"outcome": outcome})
        out_lines.append(done.model_dump_json())
    (a.session_dir / "demo.verified.jsonl").write_text("".join(x + "\n" for x in out_lines))
    print(json.dumps({"session": a.session_dir.name, "verifier": f"verify@{V.VERIFIER_VERSION}",
                      "events": len(events), "rules": summarise(rows)}, indent=1))  # fmt: skip
    return 0


if __name__ == "__main__":
    sys.exit(main())
