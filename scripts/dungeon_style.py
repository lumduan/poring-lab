#!/usr/bin/env python3
"""HOW a dungeon hunt went (Batt 2026-10-22 ~19:3x, after his 15-min orcsdun01 demo: "explain HOW I
kept HP high while killing 4.5x faster than the bot: pack size I engaged at once, kill time per
orc, when I moved on, where I fought (corridors vs open rooms), and whether I pulled monsters
along the loop"). The SAME offline ruler for his demo and the bot's runs, from the PACKETS (the
server's truth, ADR-0007); nothing here reaches a runner.

    dungeon_style.py row SID [--live S]                  one session's style row (JSON)
    dungeon_style.py table SID [SID ...] --target SID [--live S]
                                                         the bot vs the target (Batt), gaps ranked
    dungeon_style.py circuit SID [--live S] [--eps 3] [--merge 6]
                                                         the walked circuit: simplified waypoints

The window is dungeon_judge's (run_start..run_end; ``--live S``: a human demo's first input + S s,
applied to every SID that has a t0_live_ns, the bot's runs keep theirs).

DEFINITIONS (fixed 2026-10-22 ~19:2x ICT after reading only Batt's demo's dungeon_judge row, before
the patrol version is built or run):
- FIGHT: our acts on a unit (normal / critical / multi / endure / lucky, misses included) and
  monster acts on us, merged while consecutive ones are <= FIGHT_GAP_S apart. Per fight: its
  seconds, kills (arm_judge.kills_of inside it + 1.5 s), the distinct monsters that acted on us,
  the PACK = the most distinct attackers inside any PACK_WIN_S window, HP at its start / lowest
  / end (% of MaxHP), our cell at its start and that cell's OPENNESS.
- OPENNESS of a cell: the Chebyshev distance to the nearest non-walkable cell (GAT). corridor
  <= 2 (a passage <= ~5 cells wide), mid 3, open >= 4. Fights are counted per class, beside the
  walked cells' and the map's own shares.
- KILL TIME: per kill, our first act on that unit (after its previous death, within 30 s) to its
  death vanish; the median per species.
- MOVED ON: per fight, its end to our next self_move (s), and the pickups in between.
- PULLED: a monster that acted on us at two of our cells >= PULL_CELLS apart, alive in between
  (it followed us); per 10 min, and those that reached a LATER fight.
- LOOT IN FIGHTS: each pickup request inside a fight / <= 10 s after one / elsewhere.
- TARGET CHOICE: per attack request on a monster (a repeat on the same target <= 2 s later is
  not a new choice): its distance, whether it had acted on us <= 5 s before, its distance rank
  among the monsters within 9 cells (1 = the nearest), its species.
- TIME PER KILL: the window's seconds split into fighting / walking outside fights / standing
  outside fights, each per kill. The gap ranking orders the bot's seconds lost per kill against
  the target's by component.
"""

from __future__ import annotations

import argparse
import bisect
import json
import math
import statistics
import sys
from collections import Counter, deque
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

NS = 1_000_000_000
AID = 2000002
FIGHT_GAP_S = 3.0
PACK_WIN_S = 3.0
PULL_CELLS = 5
CORRIDOR, OPEN = 2, 4
ATTACK_KINDS = ("normal", "critical", "multi", "endure", "lucky")
WHITE_PLANT, WHITE_HERB = 1082, 509
Cell = tuple[int, int]


def _t(e: Mapping[str, Any]) -> int:
    return int(e["t_mono_ns"])


def cheb(a: Sequence[int], b: Sequence[int]) -> int:
    return max(abs(a[0] - b[0]), abs(a[1] - b[1]))


def openness(walkable: Any) -> Any:
    """PURE: per cell, the Chebyshev distance to the nearest non-walkable cell (0 on one); the
    map's border counts as non-walkable. A multi-source BFS over 8 neighbours."""
    import numpy as np

    h, w = walkable.shape
    d = np.full((h, w), -1, dtype=np.int32)
    q: deque[tuple[int, int]] = deque()
    for y, x in zip(*np.nonzero(~walkable), strict=True):
        d[y, x] = 0
        q.append((int(x), int(y)))
    for x in range(w):
        for y in (0, h - 1):
            if d[y, x] < 0:
                d[y, x] = 1
                q.append((x, y))
    for y in range(h):
        for x in (0, w - 1):
            if d[y, x] < 0:
                d[y, x] = 1
                q.append((x, y))
    while q:
        x, y = q.popleft()
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                nx, ny = x + dx, y + dy
                if 0 <= nx < w and 0 <= ny < h and d[ny, nx] < 0:
                    d[ny, nx] = d[y, x] + 1
                    q.append((nx, ny))
    return d


def open_class(d: int) -> str:
    return "corridor" if d <= CORRIDOR else "open" if d >= OPEN else "mid"


def combat(packets: Sequence[Mapping[str, Any]], t0: int, t1: int, monsters: set[int],
           aid: int = AID) -> list[tuple[int, str, int]]:  # fmt: skip
    """PURE: [(t, 'ours' | 'theirs', the monster's gid)] inside [t0, t1]: our acts on a monster and
    a monster's acts on us (attack kinds; misses included)."""
    out = []
    for e in packets:
        if e.get("type") != "act" or e.get("kind") not in ATTACK_KINDS:
            continue
        t = _t(e)
        if not t0 <= t <= t1:
            continue
        s, g = int(e.get("src_gid") or -1), int(e.get("target_gid") or -1)
        if s == aid and g in monsters:
            out.append((t, "ours", g))
        elif g == aid and s in monsters:
            out.append((t, "theirs", s))
    return out


def fights_of(cb: Sequence[tuple[int, str, int]], gap_s: float = FIGHT_GAP_S
              ) -> list[list[tuple[int, str, int]]]:  # fmt: skip
    """PURE: the combat events grouped into fights (consecutive events <= gap_s apart)."""
    out: list[list[tuple[int, str, int]]] = []
    for ev in sorted(cb):
        if out and ev[0] - out[-1][-1][0] <= gap_s * NS:
            out[-1].append(ev)
        else:
            out.append([ev])
    return out


def pack_size(fight: Sequence[tuple[int, str, int]], win_s: float = PACK_WIN_S) -> int:
    """PURE: the most distinct monsters acting on us inside any ``win_s`` window."""
    th = [(t, g) for t, k, g in fight if k == "theirs"]
    best = 0
    for i, (ti, _g) in enumerate(th):
        best = max(best, len({g for t, g in th[i:] if t - ti <= win_s * NS}))
    return best


def rdp(points: Sequence[Cell], eps: float) -> list[Cell]:
    """PURE: Ramer-Douglas-Peucker on a cell polyline (perpendicular distance in cells)."""
    if len(points) < 3:
        return list(points)
    (x0, y0), (x1, y1) = points[0], points[-1]
    dx, dy = x1 - x0, y1 - y0
    norm = math.hypot(dx, dy)
    best, idx = -1.0, 0
    for i in range(1, len(points) - 1):
        px, py = points[i]
        dist = (abs(dy * px - dx * py + x1 * y0 - y1 * x0) / norm if norm
                else math.hypot(px - x0, py - y0))  # fmt: skip
        if dist > best:
            best, idx = dist, i
    if best <= eps:
        return [points[0], points[-1]]
    return rdp(points[: idx + 1], eps)[:-1] + rdp(points[idx:], eps)


def merge_close(wps: Sequence[Cell], merge: int) -> list[Cell]:
    """PURE: drop a waypoint within ``merge`` cells (Chebyshev) of the previous kept one."""
    out: list[Cell] = []
    for c in wps:
        if not out or cheb(out[-1], c) > merge:
            out.append(c)
    return out


def signed_area(poly: Sequence[Cell]) -> float:
    """PURE: the shoelace area of the closed polygon; > 0 = COUNTER-clockwise with x east and y
    north (the map's cells), < 0 = clockwise."""
    return 0.5 * sum(a[0] * b[1] - b[0] * a[1] for a, b in zip(poly, [*poly[1:], poly[0]],
                                                               strict=True))  # fmt: skip


def circuit(track: Sequence[tuple[int, Cell]], t0: int, t1: int, eps: float = 3.0,
            merge: int = 6) -> dict[str, Any]:  # fmt: skip
    """PURE: the walked cells in [t0, t1] (repeats dropped) -> simplified waypoints, their order and
    the direction of travel around the polygon they enclose."""
    cells: list[Cell] = []
    for t, c in track:
        if t0 <= t <= t1 and (not cells or cells[-1] != c):
            cells.append(c)
    wps = merge_close(rdp(cells, eps), merge)
    area = signed_area(wps) if len(wps) >= 3 else 0.0
    return {"cells_walked": len(cells), "waypoints": [list(c) for c in wps],
            "direction": ("counter-clockwise" if area > 0 else "clockwise" if area < 0
                          else "none") + " (x east, y north)",
            "signed_area": round(area, 1), "eps": eps, "merge": merge}  # fmt: skip


def _med(xs: Sequence[float]) -> float | None:
    return round(statistics.median(xs), 2) if xs else None


def style(packets: Sequence[Mapping[str, Any]], t0: int, t1: int, walkable: Any,
          items: Mapping[str, Mapping[str, Any]] | None = None, aid: int = AID
          ) -> dict[str, Any]:  # noqa: C901, PLR0915  # fmt: skip
    """PURE: the style row of one window."""
    import arm_judge as aj
    import dungeon_judge as dj
    import flow_judge as fj
    import hunt_core as hc

    jobs: dict[int, int] = {}
    for e in packets:
        if e.get("type") == "entity_appear" and e.get("objtype") == 5:
            jobs[int(e["gid"])] = int(e.get("job", -1))
    monsters = set(jobs)
    track, moving = fj.gm_track(packets)
    tt = [p[0] for p in track]
    pos = hc.walk_positions(packets)
    dmap = openness(walkable)

    def here(t: int) -> Cell | None:
        i = bisect.bisect_right(tt, t) - 1
        return track[i][1] if i >= 0 else None

    def d_at(c: Cell | None) -> int | None:
        if c is None or not (0 <= c[1] < dmap.shape[0] and 0 <= c[0] < dmap.shape[1]):
            return None
        return int(dmap[c[1], c[0]])

    hp_s, mhp_s = dj.series(packets, "hp"), dj.series(packets, "max_hp")

    def hp_pct(t: int) -> float | None:
        hp, mhp = dj.in_force(hp_s, t), dj.in_force(mhp_s, t) or dj.MAX_HP
        return round(100 * hp / mhp, 1) if hp is not None and mhp else None

    kills = [(t, g) for t, g in aj.kills_of(packets, aid) if t0 <= t <= t1]
    kill_t = [k[0] for k in kills]
    cb = combat(packets, t0, t1, monsters, aid)
    fights = fights_of(cb)
    secs = (t1 - t0) / NS
    # --- fights
    rows = []
    for f in fights:
        a, b = f[0][0], f[-1][0]
        ks = bisect.bisect_right(kill_t, b + int(1.5 * NS)) - bisect.bisect_left(kill_t, a)
        att = {g for _t_, k, g in f if k == "theirs"}
        hps = [v for tv, v in dj.clip(hp_s, a, b)]
        mhp = dj.in_force(mhp_s, a) or dj.MAX_HP
        c0 = here(a)
        rows.append({"t0": a, "t1": b, "s": (b - a) / NS, "kills": ks, "attackers": att,
                     "pack": pack_size(f), "hp0": hp_pct(a),
                     "hp_min": round(100 * min(hps) / mhp, 1) if hps else None,
                     "hp1": hp_pct(b + NS), "cell": c0, "open": d_at(c0)})  # fmt: skip
    fight_s = sum(r["s"] for r in rows)
    # --- pulled: one monster acting on us at two of our cells >= PULL_CELLS apart, alive between
    deaths: dict[int, list[int]] = {}
    for e in packets:
        if e.get("type") == "entity_vanish" and int(e.get("reason", -1)) == 1:
            deaths.setdefault(int(e["gid"]), []).append(_t(e))
    hits_on_us: dict[int, list[tuple[int, Cell | None]]] = {}
    for t, k, g in cb:
        if k == "theirs":
            hits_on_us.setdefault(g, []).append((t, here(t)))
    pulled = []
    for g, hs in hits_on_us.items():
        c_first = hs[0][1]
        for t, c in hs[1:]:
            died_between = any(hs[0][0] < td < t for td in deaths.get(g, []))
            if died_between:
                break
            if c is not None and c_first is not None and cheb(c, c_first) >= PULL_CELLS:
                pulled.append(g)
                break
    fight_of_att = [r["attackers"] for r in rows]
    reached_later = sum(1 for i, s in enumerate(fight_of_att) for g in s
                        if g in pulled and any(g in s2 for s2 in fight_of_att[i + 1:]))  # fmt: skip
    # --- kill time per species
    ours = sorted((t, g) for t, k, g in cb if k == "ours")
    first_by: dict[int, list[int]] = {}
    for t, g in ours:
        first_by.setdefault(g, []).append(t)
    kt: dict[int, list[float]] = {}
    for td, g in kills:
        prev = max([x for x in deaths.get(g, []) if x < td] or [td - 30 * NS])
        ts_ = [t for t in first_by.get(g, []) if max(prev, td - 30 * NS) < t <= td]
        if ts_:
            kt.setdefault(jobs.get(g, -1), []).append((td - ts_[0]) / NS)
    # --- moved on, loot in fights
    mv = sorted(_t(e) for e in packets if e.get("type") == "self_move")
    pk = sorted(_t(e) for e in packets if e.get("type") == "pickup_request" and t0 <= _t(e) <= t1)
    moved_on, picks_before_move = [], []
    for r in rows:
        i = bisect.bisect_right(mv, r["t1"])
        if i < len(mv) and mv[i] <= t1:
            moved_on.append((mv[i] - r["t1"]) / NS)
            picks_before_move.append(
                bisect.bisect_left(pk, mv[i]) - bisect.bisect_right(pk, r["t1"])
            )
    loot_where = Counter()
    for t in pk:
        r_ = next((r for r in rows if r["t0"] <= t <= r["t1"]), None)
        after = next((r for r in rows if r["t1"] < t <= r["t1"] + 10 * NS), None)
        loot_where["in_fight" if r_ else "after_fight_10s" if after else "elsewhere"] += 1
    # --- target choice
    reqs = sorted((_t(e), int(e.get("target_gid") or -1)) for e in packets
                  if dj.is_attack_request(e, aid) and t0 <= _t(e) <= t1)  # fmt: skip
    choices = []
    last: dict[int, int] = {}
    for t, g in reqs:
        if g not in monsters:
            continue
        if t - last.get(g, -(10**18)) <= 2 * NS:
            last[g] = t
            continue
        last[g] = t
        me = here(t)
        tg = fj.mob_at(pos, g, t)
        if me is None or tg is None:
            continue
        near = []
        for gg in monsters:
            c = fj.mob_at(pos, gg, t) if gg != g else None
            if c is None or cheb(me, c) > 9:
                continue
            if any(t - 60 * NS < td <= t for td in deaths.get(gg, [])):
                continue  # died (and may have respawned elsewhere): not a candidate now
            near.append(cheb(me, c))
        dist = cheb(me, tg)
        attacked = any(g == gg and t - 5 * NS <= tx <= t for tx, k, gg in cb if k == "theirs")
        choices.append({"dist": dist, "rank": 1 + sum(x < dist for x in near),
                        "attacker": attacked, "job": jobs.get(g, -1)})  # fmt: skip
    # --- white plants and herbs
    wp_seen = {int(e["gid"]) for e in packets if e.get("type") == "entity_appear"
               and e.get("objtype") == 5 and int(e.get("job", -1)) == WHITE_PLANT
               and t0 <= _t(e) <= t1}  # fmt: skip
    wp_killed = [g for _t_, g in kills if jobs.get(g) == WHITE_PLANT]
    herbs_fell = [e for e in packets if e.get("type") == "floor_item_appear"
                  and int(e.get("item_id", -1)) == WHITE_HERB and t0 <= _t(e) <= t1]  # fmt: skip
    herbs_got = sum(int(e.get("amount") or 1) for e in packets if e.get("type") == "pickup_result"
                    and e.get("ok") and int(e.get("item_id", -1)) == WHITE_HERB
                    and t0 <= _t(e) <= t1)  # fmt: skip
    herb_value = int((items or {}).get(str(WHITE_HERB), {}).get("sell") or 0)
    # --- time split
    walk_ns = dj.overlap(moving, t0, t1)
    in_fight = [(r["t0"], r["t1"]) for r in rows]
    walk_in_fight = sum(dj.overlap2([(a, b)], moving) for a, b in in_fight)
    walk_out = (walk_ns - walk_in_fight) / NS
    stand_out = max(0.0, secs - fight_s - walk_out)
    nk = max(1, len(kills))
    cls = Counter(open_class(r["open"]) for r in rows if r["open"] is not None)
    k_cls = Counter()
    for r in rows:
        if r["open"] is not None:
            k_cls[open_class(r["open"])] += r["kills"]
    walk_cls = Counter(open_class(d_at(c) or 0) for t, c in track if t0 <= t <= t1)
    map_cls = Counter(open_class(int(v)) for v in dmap[walkable].ravel())
    heading = fj.heading_metrics(packets, t0, t1)

    def shares(c: Counter[str]) -> dict[str, float]:
        n = sum(c.values()) or 1
        return {k: round(c[k] / n, 3) for k in ("corridor", "mid", "open")}

    packs = [r["pack"] for r in rows]
    return {
        "minutes": round(secs / 60, 2),
        "kills": len(kills), "kills_h": round(len(kills) * 3600 / secs, 1),
        "fights": len(rows), "fights_per_10min": round(len(rows) * 600 / secs, 1),
        "kills_per_fight": round(len(kills) / max(1, len(rows)), 2),
        "pack_median": _med(packs), "pack_p90": (sorted(packs)[int(0.9 * (len(packs) - 1))]
                                                 if packs else None),
        "pack_hist": dict(sorted(Counter(min(p, 6) for p in packs).items())),
        "fight_s_median": _med([r["s"] for r in rows]),
        "fight_hp_drop_median_pts": _med([r["hp0"] - r["hp_min"] for r in rows
                                          if r["hp0"] is not None and r["hp_min"] is not None]),
        "fight_hp_min_pct": min((r["hp_min"] for r in rows if r["hp_min"] is not None),
                                default=None),
        "fight_start_hp_median_pct": _med([r["hp0"] for r in rows if r["hp0"] is not None]),
        "kill_time_s_median_by_species": {str(k): _med(v) for k, v in sorted(kt.items())},
        "kill_time_s_median": _med([x for v in kt.values() for x in v]),
        "moved_on_s_median": _med(moved_on), "moved_on_s_p75": (sorted(moved_on)[
            int(0.75 * (len(moved_on) - 1))] if moved_on else None),
        "pickups_before_moving_median": _med(picks_before_move),
        "fights_by_openness": shares(cls), "kills_by_openness": shares(k_cls),
        "walked_cells_by_openness": shares(walk_cls), "map_cells_by_openness": shares(map_cls),
        "pulled": len(pulled), "pulled_per_10min": round(len(pulled) * 600 / secs, 1),
        "pulled_into_a_later_fight": reached_later,
        "monsters_acting_on_us": len(hits_on_us),
        "loot_pickups": dict(loot_where), "pickups": len(pk),
        "target_choice": {"n": len(choices),
                          "nearest_share": round(sum(c["rank"] == 1 for c in choices)
                                                 / max(1, len(choices)), 3),
                          "attacker_share": round(sum(c["attacker"] for c in choices)
                                                  / max(1, len(choices)), 3),
                          "dist_median": _med([c["dist"] for c in choices]),
                          "by_species": dict(Counter(str(c["job"]) for c in choices))},
        "attack_requests_per_kill": round(len(reqs) / nk, 2),
        "white_plant": {"seen": len(wp_seen), "killed": len(wp_killed),
                        "white_herbs_fell": len(herbs_fell), "white_herbs_picked": herbs_got,
                        "white_herb_sell_z": herb_value,
                        "white_herb_value_picked_z": herbs_got * herb_value},
        "sight_per_10min": fj.sight_windowed(packets, t0, t1),
        "reversals_per_min": heading.get("reversals_per_min"),
        "cells_walked_per_min": heading.get("cells_walked_per_min"),
        "time_split_s_per_kill": {"fighting": round(fight_s / nk, 1),
                                  "walking_outside_fights": round(walk_out / nk, 1),
                                  "standing_outside_fights": round(stand_out / nk, 1),
                                  "total": round(secs / nk, 1)},
        "walking_share": round(walk_ns / NS / secs, 3),
    }  # fmt: skip


def gaps(bot: Mapping[str, Any], target: Mapping[str, Any]) -> list[dict[str, Any]]:
    """PURE: the bot's seconds per kill against the target's, per component, the largest first."""
    out = []
    for k in ("fighting", "walking_outside_fights", "standing_outside_fights"):
        b, t = bot["time_split_s_per_kill"][k], target["time_split_s_per_kill"][k]
        out.append({"component": k, "bot_s_per_kill": b, "target_s_per_kill": t,
                    "lost_s_per_kill": round(b - t, 1)})  # fmt: skip
    return sorted(out, key=lambda r: -r["lost_s_per_kill"])


def pooled_split(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """PURE: the time split pooled over runs (seconds and kills summed)."""
    k = sum(r["kills"] for r in rows) or 1
    out = {}
    for c in ("fighting", "walking_outside_fights", "standing_outside_fights", "total"):
        out[c] = round(sum(r["time_split_s_per_kill"][c] * max(1, r["kills"]) for r in rows) / k, 1)
    return {"kills": k, "time_split_s_per_kill": out}


# --- loading (not pure) --------------------------------------------------------------------------


def load_row(sid: str, live_s: float | None) -> dict[str, Any]:
    import dungeon_judge as dj

    from poring_dataset import camera as cam
    from poring_dataset import gat as gatmod

    ev, pk, man = dj.load(sid)
    if live_s is not None and man.get("t0_live_ns"):
        t0, t1 = dj.live_window(man, live_s)
    else:
        t0, t1, _src = dj.window(ev, man, pk)
    mp = (next((e.get("map") for e in ev if e.get("kind") == "run_start"), None)
          or man.get("map") or dj.MAP)  # fmt: skip
    gat = gatmod.parse((cam.GAT_DIR / f"{mp}.gat").read_bytes())
    row = style(pk, t0, t1, gat.walkable(), dj.load_table(None))
    return {"session": sid, "map": mp, **row}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)  # fmt: skip
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("row", "table", "circuit"):
        p = sub.add_parser(name)
        p.add_argument("sids", nargs="+" if name == "table" else 1)
        p.add_argument("--live", type=float, default=None, metavar="S")
        if name == "table":
            p.add_argument("--target", required=True)
        if name == "circuit":
            p.add_argument("--eps", type=float, default=3.0)
            p.add_argument("--merge", type=int, default=6)
    a = ap.parse_args()
    if a.cmd == "circuit":
        import dungeon_judge as dj
        import flow_judge as fj

        ev, pk, man = dj.load(a.sids[0])
        t0, t1 = (dj.live_window(man, a.live) if a.live is not None
                  else dj.window(ev, man, pk)[:2])  # fmt: skip
        track, _mv = fj.gm_track(pk)
        print(json.dumps(circuit(track, t0, t1, a.eps, a.merge), indent=1))
        return 0
    if a.cmd == "row":
        print(json.dumps(load_row(a.sids[0], a.live), indent=1, default=str))
        return 0
    target = load_row(a.target, a.live)
    rows = [load_row(s, a.live) for s in a.sids]
    pool = pooled_split(rows)
    print(json.dumps({"target": target, "runs": rows, "pooled": pool,
                      "gaps_ranked": gaps(pool, target)}, indent=1, default=str))  # fmt: skip
    return 0


if __name__ == "__main__":
    sys.exit(main())
