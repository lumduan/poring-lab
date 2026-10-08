#!/usr/bin/env python3
"""MEASURE the weight readout's resolution (loot@1 P1, Batt 2026-10-08): the smallest weight change
that moves the number the client shows, from before/after readouts around items of KNOWN weight
(the pinned item_db, data/kb/items.json) given with @item. The parent runs the live steps; this
tool only reads and judges.

    weight_resolution.py plan [--kb data/kb]
        Suggest the steps: the lightest plain items (rAthena weight 1-9: lighter than one shown
        unit) and a weight-10 item, from the KB (printed, never committed).

    weight_resolution.py measure STEPS.jsonl [--kb data/kb] [--packets PACKETS.jsonl[.gz]]
                         [--glyphs data/ui_anchors/weight_glyphs.npz] [--json]
        One step per line, in the order they were run:
            {"before": "90/2030", "after": "91/2030", "items": [[909, 1]],
             "t_before_ns": 123, "t_after_ns": 456}
        before / after: the readout as "N/M", or {"frame": PATH} to read it from a saved frame
        (the reader, complete templates only). items: [item_id, amount] given between the two
        readouts. t_*_ns (optional, host CLOCK_MONOTONIC) + --packets: the server's own weight at
        each readout (stat_change var 24), so the display rule is CHECKED, not assumed.

What it reports:
* per step: the weight given (rAthena units: 10 = 1 shown), the shown delta, and whether the
  shown delta is EXACTLY given / 10 (the P1 positive case: "@item gives an item of known weight
  and the readout rises by exactly that weight");
* moved_min: the smallest given weight whose step moved the number; still_max: the largest given
  weight whose step did not. A lone light item can move the number when the total crosses a
  display boundary, so for a chain of light steps the answer is in:
* moves_at: the cumulative weight given (from the first readout) at each step that moved the
  number, and their spacing -- the RESOLUTION: what must accumulate between two moves (the first
  spacing depends on where the start sat between boundaries);
* with server weights: which display rule (floor, round or ceil of weight / 10) every readout
  agrees with. Under floor a +1..9 item moves the number only when the total crosses a multiple
  of 10, so a sub-resolution pickup may leave the number unchanged.
Steps are judged only in order and only while readouts chain (a step's before = the previous
step's after); a break restarts the cumulative count.
"""

from __future__ import annotations

import argparse
import bisect
import json
import math
import sys
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
WEIGHT = 24  # rAthena SP_WEIGHT (stat_change var)
RULES: dict[str, Callable[[int], int]] = {
    "floor": lambda w: w // 10,
    "round": lambda w: int(math.floor(w / 10 + 0.5)),
    "ceil": lambda w: -(-w // 10),
}


@dataclass(frozen=True)
class Step:
    before: tuple[int, int] | None
    after: tuple[int, int] | None
    given: int  # rAthena weight units given between the readouts
    items: tuple[tuple[int, int], ...]
    server_before: int | None = None
    server_after: int | None = None
    unknown_items: tuple[int, ...] = ()


def parse_readout(text: str) -> tuple[int, int]:
    n, sep, m = text.replace(" ", "").partition("/")
    if not sep or not n.isdigit() or not m.isdigit():
        raise ValueError(f"expected N/M, got {text!r}")
    return int(n), int(m)


def server_weight_at(events: Sequence[Mapping[str, Any]]) -> Callable[[int], int | None]:
    """t_ns -> the server's weight (rAthena units) last set at or before t_ns."""
    pts = sorted((int(e["t_mono_ns"]), int(e["value"])) for e in events
                 if e.get("type") == "stat_change" and e.get("var") == WEIGHT)  # fmt: skip
    times = [t for t, _ in pts]

    def at(t_ns: int) -> int | None:
        i = bisect.bisect_right(times, t_ns) - 1
        return None if i < 0 else pts[i][1]

    return at


def build_steps(
    rows: Iterable[Mapping[str, Any]],
    weights: Mapping[int, int],
    read: Callable[[Any], tuple[int, int] | None],
    server: Callable[[int], int | None] | None = None,
) -> list[Step]:
    steps = []
    for row in rows:
        items = tuple((int(i), int(n)) for i, n in row.get("items", []))
        unknown = tuple(i for i, _ in items if i not in weights)
        given = sum(weights.get(i, 0) * n for i, n in items)

        def srv(key: str, row: Mapping[str, Any] = row) -> int | None:
            return server(int(row[key])) if server is not None and key in row else None

        steps.append(Step(read(row.get("before")), read(row.get("after")), given, items,
                          srv("t_before_ns"), srv("t_after_ns"), unknown))  # fmt: skip
    return steps


def judge(steps: Sequence[Step]) -> dict[str, Any]:
    """The per-step table and the resolution verdict (see the module docstring)."""
    table = []
    moved: list[int] = []
    still: list[int] = []
    exact = 0
    rules_ok = {name: True for name in RULES}
    rules_checked = 0
    moves_at: list[list[int]] = [[]]  # per chain: cumulative given at each move
    cumulative = 0
    prev_after: tuple[int, int] | None = None
    for s in steps:
        row: dict[str, Any] = {"items": [list(i) for i in s.items], "given": s.given,
                               "before": s.before, "after": s.after}  # fmt: skip
        if s.unknown_items:
            row["note"] = f"items not in the KB: {list(s.unknown_items)} (step not judged)"
        elif s.before is None or s.after is None:
            row["note"] = "a readout is missing (step not judged)"
        else:
            delta = s.after[0] - s.before[0]
            row["shown_delta"] = delta
            row["exact"] = delta * 10 == s.given
            exact += int(row["exact"])
            (moved if delta else still).append(s.given)
            if prev_after != s.before and moves_at[-1]:
                moves_at.append([])  # the chain broke: restart the cumulative count
            if prev_after != s.before:
                cumulative = 0
            cumulative += s.given
            if delta:
                moves_at[-1].append(cumulative)
        prev_after = s.after if not s.unknown_items else None
        for value, w in ((s.before, s.server_before), (s.after, s.server_after)):
            if value is None or w is None:
                continue
            rules_checked += 1
            for name, rule in RULES.items():
                if rule(w) != value[0]:
                    rules_ok[name] = False
        if s.server_before is not None and s.server_after is not None:
            row["server"] = [s.server_before, s.server_after]
            row["server_given"] = s.server_after - s.server_before
        table.append(row)
    judged = len(moved) + len(still)
    return {
        "steps": table, "judged": judged, "exact_steps": exact,
        "moved_min": min(moved) if moved else None,
        "still_max": max(still) if still else None,
        "display_rules_consistent": (
            [n for n, ok in rules_ok.items() if ok] if rules_checked else None
        ),
        "readouts_checked_against_server": rules_checked,
        "moves_at": [c for c in moves_at if c],
        "move_spacing": sorted({b - a for c in moves_at for a, b in zip(c, c[1:], strict=False)}),
    }  # fmt: skip


def plan(items: Mapping[str, Mapping[str, Any]]) -> list[str]:
    """The lightest plain items (weight 1-9) and weight-10 ones, for the @item steps."""
    plain = ("Etc", "Ammo", "Healing", "Usable")
    light = sorted((int(v["weight"]), int(k), v) for k, v in items.items()
                   if 0 < int(v["weight"]) <= 10 and v.get("type") in plain)  # fmt: skip
    lines = ["rAthena weight units: 10 = 1 shown. Suggested @item steps (one item per step):"]
    for target in (1, 2, 5, 10):
        pick = [x for x in light if x[0] == target][:3]
        for w, item_id, v in pick:
            name = v.get("aegis")
            lines.append(f"  weight {w:>2} ({w / 10:g} shown): @item {item_id} 1   # {name}")
    lines.append("Sequence: read N/M twice (stable) before and after EVERY @item; ten weight-1 "
                 "steps in a row show where the number moves (floor: on the 10th).")  # fmt: skip
    return lines


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p_plan = sub.add_parser("plan")
    p_plan.add_argument("--kb", type=Path, default=ROOT / "data" / "kb")
    p_m = sub.add_parser("measure")
    p_m.add_argument("steps", type=Path)
    p_m.add_argument("--kb", type=Path, default=ROOT / "data" / "kb")
    p_m.add_argument("--packets", type=Path)
    p_m.add_argument("--glyphs", type=Path, default=ROOT / "data/ui_anchors/weight_glyphs.npz")
    p_m.add_argument("--json", action="store_true")
    a = ap.parse_args()
    items: dict[str, dict[str, Any]] = json.loads((a.kb / "items.json").read_text())
    if a.cmd == "plan":
        print("\n".join(plan(items)))
        return 0
    weights = {int(k): int(v["weight"]) for k, v in items.items()}
    glyphs: Any = None

    def read(spec: Any) -> tuple[int, int] | None:
        nonlocal glyphs
        if spec is None:
            return None
        if isinstance(spec, str):
            return parse_readout(spec)
        from poring_env import weight as wt

        if glyphs is None:
            glyphs = wt.load_weight_glyphs(a.glyphs)
        from weight_calibrate import load_frame  # scripts/ is on sys.path (this script's dir)

        return wt.read_weight(load_frame(Path(spec["frame"])), glyphs).value

    server = None
    if a.packets:
        from weight_calibrate import read_events

        server = server_weight_at(read_events(a.packets))
    rows = [json.loads(x) for x in a.steps.read_text().splitlines() if x.strip()]
    out = judge(build_steps(rows, weights, read, server))
    if a.json:
        print(json.dumps(out, indent=1))
        return 0
    for i, r in enumerate(out["steps"]):
        print(f"{i:>3} given {r['given']:>4} units  {r['before']} -> {r['after']}  "
              f"shown delta {r.get('shown_delta')}  exact {r.get('exact')}  "
              f"server {r.get('server')}  {r.get('note', '')}")  # fmt: skip
    print(f"judged {out['judged']}, exact {out['exact_steps']}; smallest change that MOVED the "
          f"number: {out['moved_min']} units; largest that did NOT: {out['still_max']} units; "
          f"display rules consistent with the server: {out['display_rules_consistent']} "
          f"({out['readouts_checked_against_server']} readouts checked); moves at cumulative "
          f"{out['moves_at']} units, spacing {out['move_spacing']} = the resolution")  # fmt: skip
    return 0


if __name__ == "__main__":
    sys.exit(main())
