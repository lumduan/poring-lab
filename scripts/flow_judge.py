#!/usr/bin/env python3
"""hunt-flow's judge (demonstrations.md 3.40, pre-registered 2026-10-16 09:54 BEFORE any analysis):
CLICK -> WALK IN -> HIT LANDS, from packets OFFLINE (never a decision input). The same functions
judge Batt's human demonstration and every hunt-flow version, so the two compare directly.

    flow_judge.py human SESSION        Batt's played demo (human_demo.py): clicks from his input log
    flow_judge.py bot SESSION          a hunt-flow run: clicks from the runner's clicks.jsonl

Per TRIAL (an attack click, or a click on a detector monster box; not a follow-up click on a unit
we acted on in the 3 s before): HIT = a damaging act of ours on its unit G within T_HIT. Also the
reaction (first seen -> click -> hit), the range at the click, idle %, walk-click spacing and
cadence, target choice and switches, kills / h.
"""

from __future__ import annotations

import argparse
import gzip
import json
import math
import sys
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

Cell = tuple[int, int]
GM = 2000002
GM_MS_CELL = 150.0  # the GM's walk speed (hunt@5's packets)
DIAG = 1.4  # a diagonal step takes 14/10 of a straight one (rAthena)
WINDOW_S = 600.0
T_HIT = 3.0
T_REQ = 1.5
T_WALK = 1.0
BOX_PAD = 6.0
BOX_AGE = 0.5
NEAR = 2
SEEN_NEAR = 1.5
SEEN_GAP = 2.0
SEEN_BACK = 30.0
FOLLOW = 3.0
VIEW = 14
NS = 10**9


@dataclass
class Click:
    t: int
    u: float  # client px
    v: float
    kind: str = ""  # bot: "strike" | "walk" (what the runner meant); human: ""


@dataclass
class Trial:
    t: int
    u: float
    v: float
    gid: int | None
    # hit | walk_only | request_no_act | miss_only | other_unit | no_unit | no_response
    outcome: str
    t_hit: int | None = None
    t_seen: int | None = None
    range_cells: int | None = None
    rank: int | None = None
    switch: bool = False
    info: dict[str, Any] = field(default_factory=dict)


# --- tracks ---------------------------------------------------------------------------------------


def cheb(a: Cell, b: Cell) -> int:
    return max(abs(a[0] - b[0]), abs(a[1] - b[1]))


def steps(a: Cell, b: Cell) -> list[Cell]:
    """Chebyshev steps a -> b, diagonal first (as hunt_core.walk_positions)."""
    out, (x, y) = [], a
    while (x, y) != b:
        x += (b[0] > x) - (b[0] < x)
        y += (b[1] > y) - (b[1] < y)
        out.append((x, y))
    return out


def gm_track(events: Sequence[Mapping[str, Any]], ms_cell: float = GM_MS_CELL
             ) -> tuple[list[tuple[int, Cell]], list[tuple[int, int]]]:  # fmt: skip
    """Our GM: (t, cell) points along each self_move (a step per cell, diagonals x1.4) and the
    pins (entity_stop of our gid, map_change), plus its MOVING intervals [(t0, t1)]."""
    pts: list[tuple[int, Cell]] = []
    moving: list[tuple[int, int]] = []
    for e in events:
        t = int(e["t_mono_ns"])
        typ = e.get("type")
        if typ == "self_move":
            pts = [p for p in pts if p[0] <= t]
            if moving and moving[-1][1] > t:
                moving[-1] = (moving[-1][0], t)
            a, b = (int(e["x0"]), int(e["y0"])), (int(e["x1"]), int(e["y1"]))
            pts.append((t, a))
            tt, prev = float(t), a
            for c in steps(a, b):
                diag = c[0] != prev[0] and c[1] != prev[1]
                tt += ms_cell * (DIAG if diag else 1.0) * 1e6
                pts.append((int(tt), c))
                prev = c
            moving.append((t, int(tt)))
        elif (typ == "entity_stop" and gid_of(e) == GM) or typ == "map_change":
            pts = [p for p in pts if p[0] <= t] + [(t, (int(e["x"]), int(e["y"])))]
            if moving and moving[-1][1] > t:
                moving[-1] = (moving[-1][0], t)
    pts.sort(key=lambda p: p[0])
    return pts, moving


def at(track: Sequence[tuple[int, Cell]], t: int) -> Cell | None:
    last = None
    for tm, c in track:
        if tm > t:
            break
        last = c
    return last


def mob_at(pos: Mapping[int, Sequence[tuple[int, Cell, int]]], g: int, t: int) -> Cell | None:
    last = None
    for tm, c, _j in pos.get(g, ()):
        if tm > t:
            break
        last = c
    return last


def alive(events: Sequence[Mapping[str, Any]]) -> dict[int, tuple[int, int | None, int | None]]:
    """gid -> (first appear t, vanish t or None, vanish reason) for mobs (objtype 5)."""
    out: dict[int, tuple[int, int | None, int | None]] = {}
    for e in events:
        g = gid_of(e)
        if e.get("type") == "entity_appear" and e.get("objtype") == 5:
            first = out[g][0] if g in out and out[g][1] is None else int(e["t_mono_ns"])
            out[g] = (first, None, None)
        elif e.get("type") == "entity_vanish" and g in out and out[g][1] is None:
            out[g] = (out[g][0], int(e["t_mono_ns"]), int(e.get("reason", -1)))
    return out


def gid_of(e: Mapping[str, Any], key: str = "gid") -> int:
    """An event's unit id; -1 when absent or null (pseudonymised players carry none)."""
    v = e.get(key)
    return -1 if v is None else int(v)


def present(life: Mapping[int, tuple[int, int | None, int | None]], g: int, t: int) -> bool:
    if g not in life:
        return False
    t0, t1, _ = life[g]
    return t0 <= t and (t1 is None or t < t1)


def moving_share(moving: Sequence[tuple[int, int]], w0: int, w1: int) -> float:
    tot = sum(max(0, min(b, w1) - max(a, w0)) for a, b in moving)
    return tot / max(1, w1 - w0)


def is_moving(moving: Sequence[tuple[int, int]], t: int) -> bool:
    return any(a <= t < b for a, b in moving)


# --- inputs ---------------------------------------------------------------------------------------


def human_clicks(lines: Iterable[str], desktop: tuple[int, int],
                 region: tuple[int, int, int, int]) -> list[Click]:  # fmt: skip
    """Accepted left button downs of source=human inside the game region, in client px (the UI
    test is applied by the judge)."""
    gx, gy, gw, gh = region
    out = []
    for line in lines:
        try:
            r = json.loads(line)
        except ValueError:
            continue
        e = r.get("event", {})
        if (r.get("source") != "human" or not r.get("accepted") or e.get("type") != "mouse_button"
                or e.get("button") != "left" or e.get("action") != "down"):  # fmt: skip
            continue
        u, v = float(e["x"]) * desktop[0] - gx, float(e["y"]) * desktop[1] - gy
        if 0 <= u < gw and 0 <= v < gh:
            out.append(Click(int(r["t_mono_ns"]), u, v))
    return out


def t0_of(events: Sequence[Mapping[str, Any]], t_from: int) -> int | None:
    return next((int(e["t_mono_ns"]) for e in events
                 if e.get("type") == "self_move_request" and int(e["t_mono_ns"]) >= t_from),
                None)  # fmt: skip


def box_at(frames: Sequence[tuple[int, list[list[Any]]]], t: int, u: float, v: float,
           pad: float = BOX_PAD, age_s: float = BOX_AGE) -> list[Any] | None:  # fmt: skip
    """The monster box under (u, v) on the newest detector frame captured <= age_s before t."""
    best = None
    for tf, boxes in frames:
        if tf > t:
            break
        best = (tf, boxes)
    if best is None or t - best[0] > age_s * NS:
        return None
    for b in best[1]:
        if b[5] == "monster" and b[0] - pad <= u <= b[2] + pad and b[1] - pad <= v <= b[3] + pad:
            return b
    return None


# --- the judge ------------------------------------------------------------------------------------


def classify(click_t: int, next_t: int | None, events: Sequence[Mapping[str, Any]]
             ) -> dict[str, Any]:  # fmt: skip
    """What followed a click (packets): the first attack request within T_REQ (and before the
    next click), the first self_move_request within T_WALK, NPC contact / pickup."""
    lim_req = click_t + int(T_REQ * NS)
    if next_t is not None:
        lim_req = min(lim_req, next_t)
    out: dict[str, Any] = {"request": None, "move": None, "npc": False, "pickup": False}
    for e in events:
        t = int(e["t_mono_ns"])
        if t < click_t:
            continue
        if t > click_t + int(T_REQ * NS):
            break
        typ = e.get("type")
        if typ == "attack_request" and t <= lim_req and out["request"] is None:
            out["request"] = (t, int(e["target_gid"]))
        elif typ == "self_move_request" and t <= click_t + int(T_WALK * NS) and out["move"] is None:
            out["move"] = (t, (int(e["x"]), int(e["y"])))
        elif typ == "npc_contact" and t <= lim_req:
            out["npc"] = True
        elif typ == "pickup_request" and t <= lim_req:
            out["pickup"] = True
    return out


def judge(events: Sequence[Mapping[str, Any]], clicks: Sequence[Click],
          frames: Sequence[tuple[int, list[list[Any]]]], t0: int, pick: Any,
          in_ui: Any = lambda u, v: False,
          window_s: float = WINDOW_S) -> dict[str, Any]:  # fmt: skip
    """``pick(origin_cell, (u, v)) -> cell`` maps a client pixel to the cell the client picks;
    ``in_ui(u, v)`` excludes clicks on the fixed UI. Everything within [t0, t0 + window]."""
    import hunt_core as hc

    events = sorted(events, key=lambda e: int(e["t_mono_ns"]))
    w1 = t0 + int(window_s * NS)
    track, moving = gm_track(events)
    pos = hc.walk_positions(events)
    life = alive(events)
    ours = [e for e in events if e.get("type") == "act" and int(e.get("src_gid", -1)) == GM
            and e.get("kind") != "pickup"]  # fmt: skip
    clicks = sorted((c for c in clicks if t0 <= c.t < w1 and not in_ui(c.u, c.v)),
                    key=lambda c: c.t)  # fmt: skip
    trials: list[Trial] = []
    walks: list[dict[str, Any]] = []
    counts = {"clicks": len(clicks), "follow_up": 0, "npc_click": 0, "pickup_click": 0,
              "walk_click": 0, "other_click": 0}  # fmt: skip
    for i, c in enumerate(clicks):
        nxt = clicks[i + 1].t if i + 1 < len(clicks) else None
        f = classify(c.t, nxt, events)
        here = at(track, c.t)
        box = box_at(frames, c.t, c.u, c.v)
        if f["npc"]:
            counts["npc_click"] += 1
            continue
        if f["pickup"] and f["request"] is None:
            counts["pickup_click"] += 1
            continue
        attack = f["request"] is not None or c.kind == "strike" or box is not None
        if not attack:
            if f["move"] is not None and here is not None:
                counts["walk_click"] += 1
                walks.append({"t": c.t, "spacing": cheb(here, f["move"][1]),
                              "while_moving": is_moving(moving, c.t)})  # fmt: skip
            else:
                counts["other_click"] += 1
            continue
        picked = pick(here, (c.u, c.v)) if here is not None else None
        nearest = None
        if picked is not None:
            cands = [(cheb(picked, mc), g) for g in pos
                     if present(life, g, c.t)
                     and (mc := mob_at(pos, g, c.t)) is not None]  # fmt: skip
            cands = [x for x in cands if x[0] <= NEAR]
            nearest = min(cands)[1] if cands else None
        if f["request"] is not None:
            g: int | None = f["request"][1]
        else:
            g = nearest
        if g is not None and any(c.t - FOLLOW * NS <= int(a["t_mono_ns"]) < c.t
                                 and int(a["target_gid"]) == g for a in ours):  # fmt: skip
            counts["follow_up"] += 1
            continue
        tr = Trial(c.t, c.u, c.v, g, "no_response")
        if g is None:
            tr.outcome = "no_unit"
        else:
            hits = [a for a in ours if int(a["target_gid"]) == g
                    and c.t < int(a["t_mono_ns"]) <= c.t + int(T_HIT * NS)]  # fmt: skip
            dmg = [a for a in hits if int(a.get("damage", 0)) + int(a.get("damage2", 0)) > 0]
            if dmg:
                tr.outcome, tr.t_hit = "hit", int(dmg[0]["t_mono_ns"])
            elif hits:
                tr.outcome = "miss_only"
            elif f["request"] is not None:
                tr.outcome = "request_no_act"
            elif f["move"] is not None:
                tr.outcome = "walk_only"
            gc = mob_at(pos, g, c.t)
            if (f["request"] is not None and nearest is not None and nearest != g
                    and picked is not None
                    and (gc is None or cheb(picked, gc) > NEAR)):  # fmt: skip
                tr.outcome = "other_unit"
            if here is not None and gc is not None:
                tr.range_cells = cheb(here, gc)
                vis = sorted(cheb(here, mc) for gg in pos if present(life, gg, c.t)
                             and (mc := mob_at(pos, gg, c.t)) is not None
                             and cheb(here, mc) <= VIEW)  # fmt: skip
                tr.rank = 1 + sum(1 for d in vis if d < tr.range_cells)
            tr.t_seen = first_seen(frames, track, pos, g, c.t, pick)
        tr.info = {"request": f["request"] is not None, "box": box is not None,
                   "moving": is_moving(moving, c.t)}  # fmt: skip
        recent = [p for p in trials if c.t - FOLLOW * NS <= p.t < c.t and p.gid not in (None, g)
                  and present(life, p.gid, c.t)]  # fmt: skip
        tr.switch = bool(recent)
        trials.append(tr)
    return summarise(trials, walks, counts, events, moving, ours, t0, w1)


def first_seen(frames: Sequence[tuple[int, list[list[Any]]]], track: Sequence[tuple[int, Cell]],
               pos: Mapping[int, Sequence[tuple[int, Cell, int]]], g: int, t_click: int,
               pick: Any) -> int | None:  # fmt: skip
    """Going back from the click (no gap over SEEN_GAP, at most SEEN_BACK): the earliest
    detector frame with a monster box whose picked cell is within SEEN_NEAR of G's cell then."""
    seen, last = None, t_click
    for tf, boxes in reversed([f for f in frames if t_click - SEEN_BACK * NS <= f[0] <= t_click]):
        if last - tf > SEEN_GAP * NS:
            break
        here, gc = at(track, tf), mob_at(pos, g, tf)
        if here is None or gc is None:
            continue
        for b in boxes:
            if b[5] != "monster":
                continue
            pc = pick(here, ((b[0] + b[2]) / 2, b[3]))
            if pc is not None and math.dist(pc, gc) <= SEEN_NEAR:
                seen, last = tf, tf
                break
    return seen


def pct(xs: Sequence[float], q: float) -> float | None:
    if not xs:
        return None
    s = sorted(xs)
    return round(s[min(len(s) - 1, int(q * (len(s) - 1) + 0.5))], 2)


def wilson(k: int, n: int, z: float = 1.96) -> list[float]:
    if n == 0:
        return [0.0, 1.0]
    p = k / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return [round((c - h) / d, 4), round((c + h) / d, 4)]


def summarise(trials: Sequence[Trial], walks: Sequence[Mapping[str, Any]],
              counts: Mapping[str, int], events: Sequence[Mapping[str, Any]],
              moving: Sequence[tuple[int, int]], ours: Sequence[Mapping[str, Any]],
              t0: int, w1: int) -> dict[str, Any]:  # fmt: skip
    hits = [t for t in trials if t.outcome == "hit"]
    why: dict[str, int] = {}
    for t in trials:
        why[t.outcome] = why.get(t.outcome, 0) + 1
    s2c = [(t.t - t.t_seen) / NS for t in hits if t.t_seen is not None]
    c2h = [(t.t_hit - t.t) / NS for t in hits if t.t_hit is not None]
    s2h = [(t.t_hit - t.t_seen) / NS for t in hits if t.t_seen is not None and t.t_hit]
    acted = {int(a["target_gid"]) for a in ours if t0 <= int(a["t_mono_ns"]) < w1}
    kills = sum(1 for e in events if e.get("type") == "entity_vanish"
                and int(e.get("reason", -1)) == 1 and gid_of(e) in acted
                and t0 <= int(e["t_mono_ns"]) < w1)  # fmt: skip
    mv = moving_share(moving, t0, w1)
    after_act = []
    for a in ours:
        ta = int(a["t_mono_ns"])
        if t0 <= ta < w1:
            after_act.append((ta, ta + int(1.5 * NS)))
    idle_att = sum(
        max(0, min(b, w1) - max(a, t0)) - sum(max(0, min(b, y) - max(a, x)) for x, y in moving)
        for a, b in merge(after_act)
    ) / max(1, w1 - t0)  # fmt: skip
    gaps = [(b["t"] - a["t"]) / NS for a, b in zip(walks, walks[1:], strict=False)]
    secs = (w1 - t0) / NS
    return {
        "window_s": round(secs, 1),
        "trials": len(trials), "hits": len(hits),
        "hit_rate": round(len(hits) / len(trials), 4) if trials else None,
        "wilson95": wilson(len(hits), len(trials)), "why": why,
        "reaction_s": {"seen_to_click": [pct(s2c, 0.5), pct(s2c, 0.9)],
                       "click_to_hit": [pct(c2h, 0.5), pct(c2h, 0.9)],
                       "seen_to_hit": [pct(s2h, 0.5), pct(s2h, 0.9)],
                       "n_seen": len(s2c)},
        "range_cells": {"p50": pct([t.range_cells for t in trials if t.range_cells is not None],
                                   0.5),
                        "p90": pct([t.range_cells for t in trials if t.range_cells is not None],
                                   0.9),
                        "hist": hist([t.range_cells for t in trials if t.range_cells is not None])},
        "rank": hist([t.rank for t in trials if t.rank is not None]),
        "switches": sum(t.switch for t in trials),
        "on_moving_gm": sum(1 for t in trials if t.info.get("moving")),
        "idle_pct": round(100 * (1 - mv), 1),
        "idle_attacking_pct": round(100 * idle_att, 1),
        "walk_clicks": {"n": len(walks), "per_min": round(len(walks) / (secs / 60), 1),
                        "spacing_p50_p90": [pct([w["spacing"] for w in walks], 0.5),
                                            pct([w["spacing"] for w in walks], 0.9)],
                        "interval_p50_p90_s": [pct(gaps, 0.5), pct(gaps, 0.9)],
                        "while_moving_pct": round(100 * sum(w["while_moving"] for w in walks)
                                                  / max(1, len(walks)), 1)},
        "clicks": dict(counts),
        "kills": kills, "kills_per_hour": round(kills * 3600 / secs, 1),
        "pickups": sum(1 for e in events if e.get("type") == "pickup_request"
                       and t0 <= int(e["t_mono_ns"]) < w1),
        "trial_rows": [{"t_s": round((t.t - t0) / NS, 2), "gid": t.gid, "outcome": t.outcome,
                        "range": t.range_cells, "rank": t.rank, "switch": t.switch,
                        "seen_to_click": (None if t.t_seen is None
                                          else round((t.t - t.t_seen) / NS, 2)),
                        "click_to_hit": None if t.t_hit is None else round((t.t_hit - t.t) / NS, 2),
                        **t.info} for t in trials],
    }  # fmt: skip


def merge(iv: Sequence[tuple[int, int]]) -> list[tuple[int, int]]:
    out: list[tuple[int, int]] = []
    for a, b in sorted(iv):
        if out and a <= out[-1][1]:
            out[-1] = (out[-1][0], max(out[-1][1], b))
        else:
            out.append((a, b))
    return out


def hist(xs: Iterable[int | None]) -> dict[str, int]:
    out: dict[str, int] = {}
    for x in xs:
        if x is not None:
            out[str(x)] = out.get(str(x), 0) + 1
    return dict(sorted(out.items(), key=lambda kv: int(kv[0])))


# --- sessions -------------------------------------------------------------------------------------


def _session(sid: str) -> tuple[Path, dict[str, Any], list[dict[str, Any]], list[Any]]:
    from poring_env.demo import DEMO_ROOT

    d = DEMO_ROOT / sid
    man = json.loads((d / "manifest.json").read_text())
    with gzip.open(d / "packets.jsonl.gz", "rt") as fh:
        events = sorted((json.loads(x) for x in fh), key=lambda e: int(e["t_mono_ns"]))
    frames = []
    if (d / "boxes.jsonl").exists():
        for line in (d / "boxes.jsonl").open():
            x = json.loads(line)
            frames.append((int(x["t"]), x["boxes"]))
    frames.sort(key=lambda f: f[0])
    return d, man, events, frames


def picker(map_name: str) -> Any:
    import ro_agent as r

    from poring_dataset import camera as cam
    from poring_dataset import gat as gatmod
    from poring_dataset import picking

    gat = gatmod.parse((cam.GAT_DIR / f"{map_name}.gat").read_bytes())
    cj = json.loads((r.ROOT / "packages/poring_dataset/src/poring_dataset/camera_rdp.json")
                    .read_text())  # fmt: skip
    camera = cam.camera_from_json(cj["camera"])

    def pick(origin: Cell, px: tuple[float, float]) -> Cell | None:
        off = picking.pick_cells(camera, gat, origin, [px])[0]
        if off[0] < -1000 or off[1] < -1000:
            return None
        return (origin[0] + int(off[0]), origin[1] + int(off[1]))

    return pick


def human(sid: str) -> dict[str, Any]:
    import loot1
    import ro_agent as r

    d, man, events, frames = _session(sid)
    t0 = t0_of(events, int(man["t_armed_ns"]))
    if t0 is None:
        raise SystemExit("no movement after arming: nothing to judge")
    lines = (d / "input_human.jsonl").read_text().splitlines()
    clicks = human_clicks(lines, r.desktop(), r.game_region())
    out = judge(events, clicks, frames, t0, picker(man.get("map", "prt_fild08")), loot1.in_ui)
    out.update({"session": sid, "actor": "human", "t0_from_armed_s":
                round((t0 - int(man["t_armed_ns"])) / NS, 1)})  # fmt: skip
    (d / "flow_judge.json").write_text(json.dumps(out, indent=1))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)  # fmt: skip
    sub = ap.add_subparsers(dest="cmd", required=True)
    h = sub.add_parser("human")
    h.add_argument("session")
    a = ap.parse_args()
    out = human(a.session)
    print(json.dumps({k: v for k, v in out.items() if k != "trial_rows"}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
