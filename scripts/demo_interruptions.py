#!/usr/bin/env python3
"""Mark the attempts a HUMAN interrupted in a demo session (Batt, 2026-10-07: "mark the affected
attempts as interrupted (not pass/fail) and rerun them").

    demo_interruptions.py SESSION_DIR [--log data/input_log/<day>.jsonl]

- Reads the backend's input log for `source: human` events inside the session's window
  (manifest t0..t1, the shared CLOCK_MONOTONIC). Any human event takes the mux lease in ASSIST,
  so the rule's inputs waited or were refused: the attempt was not run ALONE.
- Each human event marks the attempt whose span contains it AND the next attempt (conservative: the
  event may fall in the next attempt's harness setup).
- Writes `interrupted.json` in the session: {record_id: reason}. demo_verify.py scores those
  records `interrupted`, never success or fail, and they are re-run (rule_run.py --rerun-of).
- The log is read from its END, in 4 MB chunks, only back to the session's start (CLAUDE.md
  rule 5: no whole-file reads of big local files). Only times, sources and event types are
  read: never key codes or text.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
from pathlib import Path
from typing import Any

from poring_env.demo import read

CHUNK = 4 * 1024 * 1024
LOG_DIR = Path(__file__).resolve().parents[1] / "data" / "input_log"


def human_events(log: Path, t0: int, t1: int, chunk: int = CHUNK) -> list[tuple[int, str]]:
    """(t_mono_ns, event type) of human events in [t0, t1], reading the log from its end."""
    size = log.stat().st_size
    out: list[tuple[int, str]] = []
    pos, tail = size, b""
    with log.open("rb") as fh:
        while pos > 0:
            start = max(0, pos - chunk)
            fh.seek(start)
            block = fh.read(pos - start) + tail
            lines = block.split(b"\n")
            tail = (
                lines[0] if start > 0 else b""
            )  # a partial first line: joined with the next chunk
            body = lines[1:] if start > 0 else lines
            oldest = None
            for raw in body:
                if not raw.strip():
                    continue
                try:
                    e = json.loads(raw)
                except ValueError:
                    continue
                t = int(e.get("t_mono_ns", 0))
                oldest = t if oldest is None else min(oldest, t)
                if e.get("source") == "human" and t0 <= t <= t1:
                    ev = e.get("event")
                    kind = ev.get("type") if isinstance(ev, dict) else None
                    out.append((t, str(kind)))
            pos = start
            if oldest is not None and oldest < t0:
                break
    return sorted(out)


def interrupted(session_dir: Path, events: list[tuple[int, str]]) -> dict[str, str]:
    """{record_id: reason} for the attempts the human events touched (and the attempt after)."""
    rule = [r for r in read(session_dir / "demo.jsonl") if not r.actor.startswith("rule:harness@")]
    starts = [r.t_mono_ns for r in rule]
    marks: dict[str, str] = {}
    for t, kind in events:
        before = [i for i, s in enumerate(starts) if s <= t]
        i = before[-1] if before else 0
        for j in (i, i + 1):
            if j < len(rule):
                marks.setdefault(rule[j].record_id, f"human {kind} at mono {t} (attempt {i})")
    return marks


def default_log(manifest: dict[str, Any]) -> Path:
    day = dt.datetime.fromtimestamp(float(manifest["t0_wall"]), dt.UTC).strftime("%Y-%m-%d")
    return LOG_DIR / f"{day}.jsonl"


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("session_dir", type=Path)
    ap.add_argument("--log", type=Path)
    a = ap.parse_args()
    man = json.loads((a.session_dir / "manifest.json").read_text())
    if "t1_mono_ns" not in man:
        raise SystemExit(f"{a.session_dir.name}: the session has not finished (no t1)")
    log = a.log or default_log(man)
    events = human_events(log, int(man["t0_mono_ns"]), int(man["t1_mono_ns"]))
    marks = interrupted(a.session_dir, events)
    tmp = a.session_dir / "interrupted.json.tmp"
    tmp.write_text(json.dumps(marks, indent=1, sort_keys=True))
    os.replace(tmp, a.session_dir / "interrupted.json")
    print(json.dumps({"session": a.session_dir.name, "human_events": len(events),
                      "interrupted": len(marks)}))  # fmt: skip
    return 0


if __name__ == "__main__":
    sys.exit(main())
