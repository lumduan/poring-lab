#!/usr/bin/env python3
"""--quick-drop-scaled's analysis (dungeon@9.38, rogue-xmas02.md 4DG), OFFLINE: every --quick-drop
drop of the sessions given, and what a distance-scaled no-hit window would have done to it.

    quick_drop_scaled_study.py SESSION_DIR [SESSION_DIR ...] [--per-cell 0.2] [--max 3.5]

Reads each session's events.jsonl (the runner), packets.jsonl.gz (OFFLINE ground truth: it never
feeds the bot; our AID by poring_dataset.timeline.infer_self_aid) and battle_log_live.jsonl (the
live reader whose damage lines are the runner's "hit of ours"). Per ``quick_drop`` event, the
strike just before it (the one it gave up):
- its distance in cells (Chebyshev, the strike's ``rel``), its path (``by``), clicks, why; the
  click -> drop time and, after an arrow, the arrow -> drop time (the event clock: the strike's
  ``t_ns`` is taken BEFORE its click, whose input round trips take ~0.5 s);
- the strike's OWN attack request (the first ``attack_request`` between its click and the drop);
- our next attack act after the drop (normal / multi-hit / lucky-dodge acts of our AID), and
  whether a NEW strike of ours came between the drop and that act (then the act is that strike's);
- GIVEN UP (4CR's Q2 definition, 4CY's count): that act came <= GIVEN_UP_S after the drop;
- a no-hit drop: the runner's arrow time (the unlock's own ``s`` is its since-lock time at the
  drop tick, the lock taken right at the arrow: arrow in [drop - s - TICK_S, drop - s]) and the
  first damage line of ours after the click, relative to that arrow ([lo, hi]).
The scaled window W = min(--max, QUICK_HIT_S + --per-cell x cells) (never below the run's own
hit_s) then KEEPS a no-hit lock when the line surely lands before the drop tick (hi + TAIL_LAG_S
<= W), is BORDERLINE when it may (lo + TAIL_LAG_S <= W + TICK_S), else the lock still drops (the
plain "no hits" unlock instead when W >= LOCK_NO_HIT_S). A no-arrow drop is untouched by W.
"""

from __future__ import annotations

import argparse
import gzip
import json
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

NS = 1_000_000_000
GIVEN_UP_S = 2.0  # 4CR's Q2: our attack act within this long after the drop
ATTACK_KINDS = frozenset({"normal", "multi_hit", "lucky_dodge"})
TICK_S = 0.2  # the runner's main loop (READ_HZ 5): the drop and the line are seen on its ticks
TAIL_LAG_S = 0.1  # hunt_flow.BattleLogTail polls the reader's file every 0.03-0.05 s
QUICK_HIT_S, LOCK_NO_HIT_S = 2.0, 3.5  # dungeon_hunt.py's (pinned by the test)


def cells_of(rel: Sequence[int]) -> int:
    """PURE: the strike's distance in cells (Chebyshev), as far_window / quick_hit_window."""
    return max(abs(int(rel[0])), abs(int(rel[1])))


def drop_rows(
    events: Sequence[Mapping[str, Any]],
    packets: Sequence[Mapping[str, Any]],
    lines: Sequence[Mapping[str, Any]],
    aid: int | None,
) -> list[dict[str, Any]]:
    """PURE: one row per ``quick_drop`` event (see the module docstring)."""
    acts = sorted((p for p in packets if p.get("type") == "act" and p.get("src_gid") == aid
                   and p.get("kind") in ATTACK_KINDS),
                  key=lambda p: int(p["t_mono_ns"]))  # fmt: skip
    reqs = sorted((p for p in packets if p.get("type") == "attack_request"),
                  key=lambda p: int(p["t_mono_ns"]))  # fmt: skip
    dmg = sorted(int(x.get("t_emit_ns") or x["t_ns"]) for x in lines if x.get("type") == "damage")
    strikes = sorted((e for e in events if e.get("kind") == "strike"), key=lambda e: int(e["t_ns"]))
    unlocks = [e for e in events if e.get("kind") == "unlock" and e.get("why") == "quick"]
    rows: list[dict[str, Any]] = []
    for e in events:
        if e.get("kind") != "quick_drop":
            continue
        t = int(e["t_ns"])
        before = [s for s in strikes if int(s["t_ns"]) <= t]
        if not before:
            continue
        s = before[-1]
        t_s = int(s["t_ns"])
        req = next((p for p in reqs if t_s <= int(p["t_mono_ns"]) <= t), None)
        nxt = next((p for p in acts if int(p["t_mono_ns"]) > t), None)
        nxt_s = None if nxt is None else (int(nxt["t_mono_ns"]) - t) / NS
        row: dict[str, Any] = {
            "why": e.get("why"), "cells": cells_of(s["rel"]), "rel": list(s["rel"]),
            "by": s.get("by"), "clicks": s.get("clicks"),
            "drop_s": round((t - t_s) / NS, 2),
            "arrow_to_drop_s": None if s.get("arrow_s") is None
            else round((t - t_s) / NS - float(s["arrow_s"]), 2),
            "request_s": None if req is None else round((int(req["t_mono_ns"]) - t_s) / NS, 2),
            "next_act_s": None if nxt_s is None else round(nxt_s, 2),
            "next_on_own_target": None if nxt is None or req is None
            else nxt.get("target_gid") == req.get("target_gid"),
            "new_strike_first": None if nxt is None
            else any(t < int(x["t_ns"]) < int(nxt["t_mono_ns"]) for x in strikes),
            "given_up": nxt_s is not None and nxt_s <= GIVEN_UP_S,
        }  # fmt: skip
        if e.get("why") == "no_hit" and unlocks:
            u = min(unlocks, key=lambda x: abs(int(x["t_ns"]) - t))
            arrow_hi = int(u["t_ns"]) - float(u["s"]) * NS  # the latest the arrow can have been
            first = next((x for x in dmg if x > t_s), None)
            row["hit_s_used"] = float(u["s"])
            lo = None if first is None else (first - arrow_hi) / NS
            row["line_after_arrow"] = None if lo is None else [round(lo, 2), round(lo + TICK_S, 2)]
        rows.append(row)
    return rows


def scaled_window(cells: int, per_cell: float, max_s: float, used: float = QUICK_HIT_S) -> float:
    """PURE: dungeon_hunt.quick_hit_window's rule (never below the run's own window ``used``)."""
    return max(min(max_s, QUICK_HIT_S + per_cell * cells), used)


def scaled_outcome(row: Mapping[str, Any], per_cell: float, max_s: float) -> str:
    """PURE: what the scaled window does to one drop: "unchanged" (a no-arrow drop), "kept",
    "borderline", "drops" (later), or "plain_unlock" (W reaches LOCK_NO_HIT_S: no quick drop --
    the plain "no hits" unlock takes the lock then, so no window keeps a lock past it)."""
    if row.get("why") != "no_hit":
        return "unchanged"
    w = scaled_window(int(row["cells"]), per_cell, max_s, float(row.get("hit_s_used") or 0.0))
    w_eff = min(w, LOCK_NO_HIT_S)
    la = row.get("line_after_arrow")
    if la is not None and la[1] + TAIL_LAG_S <= w_eff:
        return "kept"
    if la is not None and la[0] + TAIL_LAG_S <= w_eff + TICK_S:
        return "borderline"
    return "plain_unlock" if w >= LOCK_NO_HIT_S else "drops"


def load(d: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    ev = [json.loads(x) for x in (d / "events.jsonl").read_text().splitlines() if x.strip()]
    with gzip.open(d / "packets.jsonl.gz", "rt") as fh:
        pk = [json.loads(x) for x in fh if x.strip()]
    bl_path = d / "battle_log_live.jsonl"
    bl = [json.loads(x) for x in bl_path.read_text().splitlines() if x.strip()]
    return ev, pk, bl


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("sessions", type=Path, nargs="+")
    ap.add_argument("--per-cell", type=float, default=0.2)
    ap.add_argument("--max", type=float, default=3.5)
    a = ap.parse_args(argv)
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root / "packages" / "poring_dataset" / "src"))
    from poring_dataset.timeline import infer_self_aid

    all_rows: list[dict[str, Any]] = []
    for d in a.sessions:
        ev, pk, bl = load(d)
        for row in drop_rows(ev, pk, bl, infer_self_aid(pk)):
            row["session"] = d.name
            row["scaled"] = scaled_outcome(row, a.per_cell, a.max)
            all_rows.append(row)
            print(json.dumps(row))
    gu = [r for r in all_rows if r["given_up"]]
    kept = [r for r in all_rows if not r["given_up"]]
    print(json.dumps({
        "drops": len(all_rows), "given_up": len(gu),
        "given_up_by_why": {w: sum(r["why"] == w for r in gu) for w in ("no_hit", "no_arrow")},
        "given_up_cells": sorted(r["cells"] for r in gu),
        "kept_cells": sorted(r["cells"] for r in kept),
        "given_up_after_a_new_strike": sum(bool(r["new_strike_first"]) for r in gu),
        "per_cell": a.per_cell, "max": a.max,
        "given_up_scaled": {o: sum(r["scaled"] == o for r in gu)
                            for o in ("kept", "borderline", "drops", "plain_unlock", "unchanged")},
        "kept_drops_lost": sum(r["scaled"] in ("kept", "plain_unlock") for r in kept),
    }))  # fmt: skip
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
