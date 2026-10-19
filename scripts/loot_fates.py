#!/usr/bin/env python3
"""Where our kills' floor items go, and why the loot step leaves them (Batt 2026-10-19 overnight:
"the judge's 28 % 'gone' first, then size the drops outside the clicked 3 x 3"). OFFLINE, packets
as ground truth (ADR-0007); nothing here runs during play.

    loot_fates.py runs SID [SID ...]     per run: our kills' items and their fates -- picked, lost
                                         to looters, out of our sight (left behind), expired, left
                                         -- on the leaderboard's base (run_row: the drops of the
                                         engagements' kills, arm_judge.drops_of_kill), with the
                                         loot steps' share of drops in the clicked 3 x 3 and of
                                         death cells on the server's (``run_summary``)
    loot_fates.py outside SID [SID ...]  per loot step (events "loot_fixed"): the server's kill it
                                         followed, the bot's loot cell against the server's death
                                         cell, the kill's drops in / outside the clicked 3 x 3 and
                                         their fates, and what a wider area would gain and cost

THE MATCH (``step_kills``): a loot step follows the LAST of our kills (arm_judge.kills_of) in the
6 s before its start (to 1 s after), whose server death cell (flow_judge.mob_at at the vanish)
lies within 6 cells of the step's cell, each kill once. A kill's items are its 'fall' floor items
(-0.6 .. +1.5 s around the vanish, within 4 cells of its death cell: the nearest kill in time).
Steps with no such kill (a dead call without a death, a kill by nobody of ours) are counted apart.

THE OPTIONS (``option_gain``): extra cells (offsets from the step's cell) clicked AFTER the step's
own plan, one click each, at ``click_s`` per clicked cell and ``skip_s`` per skipped one (the
regression of the step's time on its clicks and skips), each clicked with the 3 x 3 ring's measured
share and picking an item still on the floor at its click time with the ring's measured share; the
step's own cap (``cap_s``, hunt_flow's loot_fixed_max_s) cuts the extra clicks. An item counts as a
GAIN only if, in the run, it was not picked.
"""

from __future__ import annotations

import argparse
import bisect
import json
import sys
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

import arm_judge as aj  # noqa: E402

NS = aj.NS
Cell = tuple[int, int]
FATES = ("picked", "looter", "out_of_sight", "expired", "left", "gone")
CLICK_S = 0.274  # s per loot click (2026-10-19, 855 steps of v41 / v43: s = 0.031 + 0.274 clicks
SKIP_S = 0.036  # + 0.036 skips)
CAP_S = 4.5  # hunt_flow PARAMS loot_fixed_max_s


def cheb(a: Sequence[int], b: Sequence[int]) -> int:
    return max(abs(a[0] - b[0]), abs(a[1] - b[1]))


def zone(cell: Sequence[int], dc: Sequence[int]) -> str:
    """PURE: "in3x3" (the clicked plan's cells), "ring2" (the 5 x 5's outer ring), "beyond2"."""
    d = cheb(cell, dc)
    return "in3x3" if d <= 1 else ("ring2" if d == 2 else "beyond2")


Kill = tuple[int, int]  # arm_judge.kills_of: (t_vanish, gid)


def kill_items(items: Mapping[int, Mapping[str, Any]], kills: Sequence[Kill],
               kcell: Mapping[Kill, Cell | None]) -> dict[Kill, list[int]]:  # fmt: skip
    """PURE: kill -> its fall items (time order): -0.6 .. +1.5 s around the vanish, within 4 cells
    of the death cell, the nearest kill in time."""
    kt = [k[0] for k in kills]
    out: dict[Kill, list[int]] = defaultdict(list)
    for f, it in items.items():
        lo = bisect.bisect_left(kt, it["t_fall"] - int(1.5 * NS))
        hi = bisect.bisect_right(kt, it["t_fall"] + int(0.6 * NS))
        best: tuple[int, Kill] | None = None
        for k in kills[lo:hi]:
            c = kcell.get(k)
            if c is None or cheb(c, it["cell"]) > 4:
                continue
            dt = abs(k[0] - it["t_fall"])
            if best is None or dt < best[0]:
                best = (dt, k)
        if best is not None:
            out[best[1]].append(f)
    for k in out:
        out[k].sort(key=lambda f: (items[f]["t_fall"], f))
    return dict(out)


def step_kills(bot_events: Iterable[Mapping[str, Any]], items: Mapping[int, Mapping[str, Any]],
               kills: Sequence[Kill], kcell: Mapping[Kill, Cell | None],
               ) -> list[dict[str, Any]]:  # fmt: skip
    """PURE: per "loot_fixed" step: {ts, te, dc, s, kill, cell (the server's death cell), items}
    (see THE MATCH)."""
    by_kill = kill_items(items, kills, kcell)
    used: set[Kill] = set()
    out = []
    for e in bot_events:
        if e.get("kind") != "loot_fixed" or not e.get("cell") or e.get("s") is None:
            continue
        te = int(e["t_ns"])
        ts = te - int(float(e["s"]) * NS)
        dc = (int(e["cell"][0]), int(e["cell"][1]))
        cand = [k for k in kills if ts - 6 * NS <= k[0] <= ts + NS and k not in used
                and (c := kcell.get(k)) is not None and cheb(c, dc) <= 6]  # fmt: skip
        k = max(cand, key=lambda k: k[0]) if cand else None
        if k is not None:
            used.add(k)
        out.append({"ts": ts, "te": te, "dc": dc, "s": float(e["s"]), "kill": k,
                    "cell": kcell.get(k) if k else None,
                    "items": list(by_kill.get(k, [])) if k else []})  # fmt: skip
    return out


def option_gain(steps: Sequence[Mapping[str, Any]], items: Mapping[int, Mapping[str, Any]],
                offsets: Sequence[Cell], p_click: float, p_pick: float,
                click_s: float = CLICK_S, skip_s: float = SKIP_S, cap_s: float | None = CAP_S,
                ) -> dict[str, float]:  # fmt: skip
    """PURE: clicking ``offsets`` (from each step's cell, in this order) after the step's own
    plan: the expected items gained (not picked in the run, still on the floor at the extra click)
    and the expected seconds added, summed over ``steps``."""
    per = p_click * click_s + (1 - p_click) * skip_s
    gain = 0.0
    added = 0.0
    on_cells = 0
    for s in steps:
        dc = s["dc"]
        room = len(offsets) if cap_s is None else max(0, int((cap_s - s["s"]) / per))
        n = min(len(offsets), room)
        added += n * per
        at = {(dc[0] + o[0], dc[1] + o[1]): j for j, o in enumerate(offsets[:n])}
        for f in s["items"]:
            it = items[f]
            j = at.get(tuple(it["cell"]))
            if j is None:
                continue
            on_cells += 1
            t_j = s["te"] + int((j + 0.5) * per * NS)
            if it["fate"] != "picked" and (it["t_end"] is None or it["t_end"] > t_j):
                gain += p_click * p_pick
    return {"gain": gain, "added_s": added, "items_on_cells": on_cells}


# --- the per-session work (reads the banked files) -----------------------------------------------


def session(sid: str) -> dict[str, Any]:
    import flow_judge as fj
    import hunt_core as hc

    s = aj.load(sid)
    d = aj.DEMO / sid
    bot = [json.loads(x) for x in (d / "events.jsonl").read_text().splitlines() if x]
    pos = hc.walk_positions(s["packets"])
    track = fj.gm_track(s["packets"])[0]
    items = aj.item_fates(s["packets"], pos, fj.mob_at, track)
    kills = aj.kills_of(s["packets"])
    kcell = {k: fj.mob_at(pos, k[1], k[0] - 1) for k in kills}
    man = json.loads((d / "manifest.json").read_text())
    return {**s, "bot": bot, "pos": pos, "items": items, "kills": kills, "kcell": kcell,
            "steps": step_kills(bot, items, kills, kcell),
            "run_s": float(man.get("run_s") or 0.0)}  # fmt: skip


def run_row(s: Mapping[str, Any]) -> dict[str, Any]:
    """The leaderboard's base (run_row.py): the drops of the engagements' kills, by fate."""
    import flow_judge as fj

    kills = {g: t for t, g in s["kills"]}
    c: Counter[str] = Counter()
    for x in s["engagements"]:
        g = s["gid_by_k"].get(int(x["k"]))
        if x.get("result") != "dead" or g is None or g not in kills:
            continue
        c["kills"] += 1
        for f in aj.drops_of_kill(s["items"], kills[g], fj.mob_at(s["pos"], g, kills[g] - 1)):
            c["items"] += 1
            c[s["items"][f]["fate"]] += 1
    n = c["items"] or 1
    return {"run_s": s["run_s"], **{k: c[k] for k in ("kills", "items", *FATES)},
            "picked_share": round(c["picked"] / n, 3), "looter_share": round(c["looter"] / n, 3),
            "out_of_sight_share": round(c["out_of_sight"] / n, 3)}  # fmt: skip


def run_summary(s: Mapping[str, Any]) -> dict[str, Any]:
    """``run_row`` plus, over the run's loot steps with a server kill: the share of the kills'
    drops inside the clicked 3 x 3, and of the bot's loot cells ON the server's death cell / within
    1 cell of it (2026-10-19: v43 runs 1, 3, 4 had 64.8 % / 31 % / 58 % against v40 + v41's
    75-76 % / 41 % / 69-70 %, with the same pick rate inside the 3 x 3 -- the loot drop)."""
    steps = [st for st in s["steps"] if st["kill"] is not None]
    n = sum(len(st["items"]) for st in steps)
    in3 = sum(zone(s["items"][f]["cell"], st["dc"]) == "in3x3" for st in steps for f in st["items"])
    err = [cheb(st["dc"], st["cell"]) for st in steps]
    m = len(err) or 1
    return {**run_row(s), "loot_steps": len(s["steps"]), "steps_with_kill": len(steps),
            "step_items": n, "in3x3_share": round(in3 / (n or 1), 3),
            "dc_exact_share": round(sum(e == 0 for e in err) / m, 3),
            "dc_within1_share": round(sum(e <= 1 for e in err) / m, 3)}  # fmt: skip


def ring_rates(s: Mapping[str, Any]) -> Counter[str]:
    """The 3 x 3 ring's measured rates: cells clicked of the cells planned, and items picked of
    the ring items still on the floor when their cell got its first click."""
    lc = sorted((int(c["t"]), (int(c["cell"][0]), int(c["cell"][1])))
                for c in s["clicks"] if c.get("kind") == "loot" and c.get("cell"))  # fmt: skip
    lt = [c[0] for c in lc]
    out: Counter[str] = Counter()
    for st in s["steps"]:
        dc = st["dc"]
        first: dict[Cell, int] = {}
        for t, c in lc[bisect.bisect_left(lt, st["ts"] - NS // 10):
                       bisect.bisect_right(lt, st["te"] + NS // 10)]:  # fmt: skip
            first.setdefault(c, t)
        ring = [(dc[0] + dx, dc[1] + dy) for dx in (-1, 0, 1) for dy in (-1, 0, 1) if dx or dy]
        out["ring_cells"] += 8
        out["ring_clicked"] += sum(c in first for c in ring)
        for f in st["items"]:
            it = s["items"][f]
            c = tuple(it["cell"])
            if cheb(c, dc) != 1 or c not in first:
                continue
            if it["t_end"] is None or it["t_end"] > first[c] or it["fate"] == "picked":
                out["ring_present_clicked"] += 1
                out["ring_present_clicked_picked"] += it["fate"] == "picked"
    return out


def outside_table(sessions: Sequence[Mapping[str, Any]],
                  offsets_by: Mapping[str, Sequence[Cell]] | None = None,
                  ) -> dict[str, Any]:  # fmt: skip
    zones: dict[str, Counter[str]] = defaultdict(Counter)
    err: Counter[int] = Counter()
    scatter: Counter[Cell] = Counter()
    out_off: Counter[Cell] = Counter()
    rates: Counter[str] = Counter()
    steps: Counter[str] = Counter()
    hours = sum(s["run_s"] for s in sessions) / 3600
    for s in sessions:
        rates.update(ring_rates(s))
        for st in s["steps"]:
            steps["steps"] += 1
            if st["kill"] is None:
                steps["no_server_kill"] += 1
                continue
            steps["with_kill"] += 1
            dc, tc = st["dc"], st["cell"]
            err[cheb(dc, tc)] += 1
            for f in st["items"]:
                it = s["items"][f]
                z = zone(it["cell"], dc)
                zones[z]["n"] += 1
                zones[z][it["fate"]] += 1
                scatter[(it["cell"][0] - tc[0], it["cell"][1] - tc[1])] += 1
                if z != "in3x3":
                    zones[z]["in_server_3x3"] += cheb(it["cell"], tc) <= 1
                    out_off[(it["cell"][0] - dc[0], it["cell"][1] - dc[1])] += 1
    p_click = rates["ring_clicked"] / max(1, rates["ring_cells"])
    p_pick = rates["ring_present_clicked_picked"] / max(1, rates["ring_present_clicked"])
    n_items = sum(z["n"] for z in zones.values())
    picked = sum(z["picked"] for z in zones.values())
    kills = steps["with_kill"]
    ring2 = sorted(((dx, dy) for dx in range(-2, 3) for dy in range(-2, 3)
                    if cheb((dx, dy), (0, 0)) == 2), key=lambda o: (-out_off[o], o))  # fmt: skip
    opts: dict[str, Sequence[Cell]] = {"5x5 (16 ring-2 cells)": ring2}
    opts.update({f"top {k} ring-2 cells": ring2[:k] for k in (2, 4, 8)})
    opts.update(offsets_by or {})
    options = {}
    for name, offs in opts.items():
        g = Counter()
        for s in sessions:
            st_ = [st for st in s["steps"] if st["kill"] is not None]
            r = option_gain(st_, s["items"], list(offs), p_click, p_pick)
            g.update({k: v for k, v in r.items()})
        s_kill = g["added_s"] / max(1, kills)
        options[name] = {"cells": [list(o) for o in offs], "items_gained": round(g["gain"], 1),
                         "items_per_h": round(g["gain"] / hours, 2),
                         "s_per_kill_added": round(s_kill, 2)}  # fmt: skip
    return {"hours": round(hours, 2), "steps": dict(steps),
            "zones": {z: dict(c) for z, c in sorted(zones.items())},
            "items": n_items, "picked": picked, "kills_with_items_base": kills,
            "picked_per_kill": round(picked / max(1, kills), 3),
            "kills_per_h": round(kills / hours, 1) if hours else None,
            "dc_error_cheb": dict(sorted(err.items())),
            "drop_offset_from_server_cell": [[list(o), c] for o, c in scatter.most_common(12)],
            "outside_offset_from_bot_cell": [[list(o), c] for o, c in out_off.most_common(16)],
            "ring_p_click": round(p_click, 3), "ring_p_pick": round(p_pick, 3),
            "ring_rates": dict(rates), "options": options}  # fmt: skip


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("cmd", choices=("runs", "outside"))
    ap.add_argument("sessions", nargs="+")
    a = ap.parse_args()
    sess = [session(sid) for sid in a.sessions]
    if a.cmd == "runs":
        print(json.dumps({s["sid"]: run_summary(s) for s in sess}, indent=1))
    else:
        print(json.dumps(outside_table(sess), indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
