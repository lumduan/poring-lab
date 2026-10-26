#!/usr/bin/env python3
"""The Miss cue's live counters (docs/planning/rogue-gef10.md Amendments S and W). Offline only:
it reads banked session files, and nothing here reaches a runner.

For a runner session with `--miss-cue`:
- each Miss ONSET (the runner's `miss_cue` event, at most one per second of reads) is TRUE when a
  monster's attack act on us (a miss or a hit, from the packets) came within TRUE_WINDOW_S before
  it, and FALSE otherwise;
- each `engage` "by miss_cue" is judged the same way. gef10-miss-cue.md 7b sets the bar: at most
  1 false engage per 36-min run;
- an engage "by miss_cue" that comes within LOOP_S after a `fight_end` is counted apart, as 9.1's
  re-engage loop (Amendment W: a Miss still drawn restarted the fight on the next tick). 9.1b
  should show none.

TRUE_WINDOW_S is 3.0 s, from gef10-miss-cue.md 1c: the text is drawn 0.6-0.9 s after the act, and
on the PNG recordings it still matches up to ~3.0 s after it.

    miss_cue_live.py SID [SID ...]        one JSON line per session
"""

from __future__ import annotations

import argparse
import bisect
import json
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

TRUE_WINDOW_S = 3.0
LOOP_S = 0.3  # 9.1's loop restarted the fight on the next 0.1 s tick


def truth(times_ns: Sequence[int], theirs_ns: Sequence[int],
          window_s: float = TRUE_WINDOW_S) -> list[bool]:  # fmt: skip
    """PURE: for each time, whether a monster's act on us (``theirs_ns``, sorted) came within
    ``window_s`` before it (the act's own instant included)."""
    out = []
    for t in times_ns:
        i = bisect.bisect_right(theirs_ns, t)
        out.append(i > 0 and t - theirs_ns[i - 1] <= window_s * 1e9)
    return out


def loop_flags(events: Sequence[Mapping[str, Any]], loop_s: float = LOOP_S) -> list[bool]:
    """PURE: for each engage "by miss_cue" in ``events`` (time order), whether it came within
    ``loop_s`` after the last `fight_end`."""
    out, last_end = [], None
    for e in events:
        if e.get("kind") == "fight_end":
            last_end = int(e["t_ns"])
        elif e.get("kind") == "engage" and e.get("by") == "miss_cue":
            out.append(last_end is not None and int(e["t_ns"]) - last_end <= loop_s * 1e9)
    return out


def summary(events: Sequence[Mapping[str, Any]], theirs_ns: Sequence[int], t0: int,
            t1: int) -> dict[str, Any]:  # fmt: skip
    """PURE: the counters inside [t0, t1]."""
    ev = [e for e in events if t0 <= int(e.get("t_ns") or 0) <= t1]
    onsets = [int(e["t_ns"]) for e in ev if e.get("kind") == "miss_cue"]
    engages = [int(e["t_ns"]) for e in ev if e.get("kind") == "engage"
               and e.get("by") == "miss_cue"]  # fmt: skip
    on_true, en_true, loop = truth(onsets, theirs_ns), truth(engages, theirs_ns), loop_flags(ev)
    minutes = (t1 - t0) / 60e9
    n_false = sum(1 for ok, lp in zip(en_true, loop, strict=True) if not ok and not lp)
    return {
        "minutes": round(minutes, 2),
        "onsets": len(onsets),
        "onsets_false": on_true.count(False),
        "engages": len(engages),
        "engages_loop": sum(loop),
        "engages_false": n_false,
        "engages_true": sum(1 for ok, lp in zip(en_true, loop, strict=True) if ok and not lp),
        "false_per_36min": None if minutes <= 0 else round(n_false * 36 / minutes, 2),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)  # fmt: skip
    ap.add_argument("sids", nargs="+")
    a = ap.parse_args()
    import time_budget as tb

    for sid in a.sids:
        ev, pk, man, t0, t1 = tb.load_window(sid, None)
        aid = int(man.get("aid") or tb.AID)
        _ours, theirs = tb.acts(pk, tb.monsters(pk), aid)
        out = summary(ev, [t for t, _m, _d in theirs], t0, t1)
        print(json.dumps({"sid": sid, **out}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
