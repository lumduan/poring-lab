#!/usr/bin/env python3
"""ECONOMICS, part 3 (Batt 2026-10-21): the MAP MODEL -- what a kill is worth on a map, at OUR
server's drop rules and FIXED NPC prices, and the ratios that compare maps like P/E or ROE compare
stocks. OFFLINE; nothing here runs during play.

    econ_model.py build [MAP ...]          data/econ/maps.json (species, drops, trips)
    econ_model.py show MAP [--K 150 --L 0.9 --C 1155 --T-s ... --cost-h 0 --gear 310000]
    econ_model.py table [MAP ...]          the comparison table (docs/econ/economics.md section 6)
    econ_model.py screen                   every map with spawn lines: a Base-60 Crusader screen
    econ_model.py species MAP [--L 1.0]    value per kill PER SPECIES, at NPC sell and at Overcharge

The formulas, every symbol and their sources are in docs/econ/economics.md. In short:
- per species s: V_s = sum_i p_i x sell_i (zeny per kill dropped), W_s = sum_i p_i x weight_i,
  p_i = the item's EFFECTIVE drop chance on this server (mob.cpp:6847-6905 at db load, then
  mob_getdroprate 2818-2889 at the kill, then the roll `rnd() % 10000 >= rate` 3335): with the
  lab's battle config (no overrides: conf/battle/drops.conf defaults, all item_rate_* 100) it is
  mob_db's Rate / 10000, clamped to [1, 10000]. Every drop is ONE unit (mob_setdropitem(entry, 1)).
- RARES are out of V (Batt: "no rares"): a drop with base rate <= 10 (<= 0.10 %), every Card and
  every PetEgg (an egg goes into the killer's inventory, not on the floor: mob.cpp:3338-3341);
  their expected NPC value is reported apart as ``rare_v``. MVP drops are never in V.
- the map's kill mix = its spawn lines' amounts (normal `monster` lines; boss_monster lines are
  listed, not farmed), or a run's measured kill mix for model-vs-measured.
- OVERCHARGE (Lv 10, the merchant's +24 %): every drop row carries ``sell_oc`` = econ_items'
  ``sell_oc10``, pc_modifysellvalue at the pin (pc.cpp:5708-5719: (int32)(sell x 124 / 100.),
  truncated PER UNIT, then x the amount, npc.cpp:3080-3082); ``--oc`` (show / table) and
  ``species`` use it. Batt 2026-10-25 (rogue-gef10.md): the Rogue's loot sells at Overcharge.
- per farming hour: G = K x L x V (gross), weight rate K x L x W, fill time F = C / (K x L x W),
  trip T (round trip to the nearest NPC that buys: walk over portals + a fixed sell time),
  u = F / (F + T), net per wall-clock hour N = u x (G - c), cost ratio c / G, payback = gear / N
  (the P/E analogue), N / gear (the ROE analogue), Sharpe-like = mean / sd of the zeny of
  10-min farming windows (compound Poisson: kills ~ Poisson(K / 6), drops independent).
rAthena data is GPL-3.0: maps.json (drop tables, spawns) is generated to data/econ/ (gitignored)
and never committed.
"""

from __future__ import annotations

import argparse
import heapq
import json
import math
import re
import sys
import time
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "econ" / "maps.json"
SRC = Path("/dev/shm/poring-lab-rathena-src")
MOB_DB = "db/pre-re/mob_db.yml"
CONFS = ("conf/battle/drops.conf", "conf/battle/monster.conf", "conf/battle/client.conf")
RARE_RATE = 10  # base rate per 10000 at or below which a drop is a rare (0.10 %)
CORE_RATE = 100  # V_core: drops at >= 1 %; the rest of V is the TAIL (0.1 % < rate < 1 %)
WINDOW_S = 600.0  # the Sharpe-like ratio's window (10 min)
WALK_MS = 150  # DEFAULT_WALK_SPEED, src/common/mmo.hpp:93 (ms per cell; diagonal x 14 / 10)
CHANGE_S = 2.0  # assumed seconds per map change (loading) on a trip
SELL_S = 20.0  # assumed seconds at the NPC (open the shop, pick the items, confirm)
KAFRA_S = 20.0  # assumed seconds at a Kafra (open storage, move the loot)
NEAR = 3  # a shop / Kafra is used from a walkable cell this close (Chebyshev; the server allows
# AREA_SIZE + 1 = 15, npc.cpp:2158-2161; 3 is the conservative approach the lab's KB uses)
MAX_HOPS = 6  # a goal (shop / Kafra) farther than this many hops counts as unreachable
# The bot's maps, Batt's Crusader map and the Base-60 Crusader candidates (why: section 6 of the
# doc and CANDIDATES below).
MAPS = ("prt_fild08", "prt_fild06", "orcsdun01")
CANDIDATES = {
    "gef_fild10": "the orc field the Crusader walks through to orcsdun01 (its portal via "
                  "in_orcs01): Orc Lady / Orc Warrior lv 24-31, NOT undead (no Demon Bane): the "
                  "baseline beside orcsdun01; since 2026-10-25 the Rogue's field (Batt; "
                  "rogue-gef10.md), its loot sold at Overcharge (species --oc)",
    "orcsdun02": "Orc Dungeon F2, the stairs from orcsdun01: Orc Skeleton (Undead, lv 28) + Zenorc "
                 "(lv 31, FLEE 108: MAIN hits 55 %); Orc Archer lv 49 x 5",
    "pay_dun01": "Payon Cave F2: Soldier / Archer Skeleton (Undead, lv 29-31: Demon Bane + Divine "
                 "Protection, MAIN hits 100 %); 68 % of the spawns are Undead / Demon",
    "pay_dun02": "Payon Cave F3: Munak / Bongun / the Skeletons (Undead, lv 29-32) beside Hydras "
                 "and plants; the cave's next floor",
    "moc_pryd02": "Pyramid F2: Mummy (lv 37, 5176 HP) + the Skeletons (Undead) with Isis (Demon, "
                  "lv 47) x 5; 70 % Undead / Demon",
    "ama_dun01": "Amatsu Dungeon F1: Miyabi Doll (Demon, lv 33) + Firelock Soldier (Undead, "
                 "lv 47): 98 % Undead / Demon and the highest V per kill of the Undead maps; "
                 "the top end for Base 60 (MAIN hits ~80 %; 2 Shinobi lv 69)",
}  # fmt: skip
# The Crusader MAIN (docs/planning/crusader-build.md 3e: Flamberge, Base 60, DEX 23, HIT 83,
# batk 82, 730 ms per attack, Sword Mastery 10, Demon Bane 10, 4150 max weight, 920 gear weight).
CRUSADER: dict[str, Any] = {"weapon_atk": 150, "weapon_level": 3, "dex": 23, "batk": 82, "hit": 83,
            "adelay_ms": 730, "sword_mastery": 40, "demon_bane": 60, "max_weight": 4150,
            "gear_weight": 920, "size_fix": {"Small": 75, "Medium": 100, "Large": 75},
            "gear": (1129, 2105, 2316, 2228, 2243, 2505, 2405)}  # fmt: skip
UNDEAD_DEMON = ("undead", "demon")
SEARCH_S = 10.0  # assumed seconds of search / approach per kill (Batt's prt_fild08 demo: 12.0 s
# per kill, of which ~2 s killing)


# --- drop rules (pure) ---------------------------------------------------------------------------


def rate_class(item_type: str) -> str:
    """mob.cpp:6862-6893: the item_rate_* class by item type (IT_HEALING heal; IT_USABLE / IT_CASH
    use; IT_WEAPON / IT_ARMOR / IT_PETARMOR equip; IT_CARD card; anything else common)."""
    t = item_type.lower()
    if t == "healing":
        return "heal"
    if t in ("usable", "cash"):
        return "use"
    if t in ("weapon", "armor", "petarmor"):
        return "equip"
    if t == "card":
        return "card"
    return "common"


def effective_rate(base: int, item_type: str, conf: Mapping[str, Any], boss: str = "",
                   treasure: bool = False) -> int:  # fmt: skip
    """The per-kill drop chance x 10000 on this server, for a kill by a player with no drop
    bonus. ``boss``: "" / "boss" / "mvp" (the mob's class). ``conf``: the battle settings
    (drops.conf, monster.conf; absent keys take the shipped defaults)."""

    def c(key: str, default: Any) -> Any:
        return conf.get(key, default)

    rate = int(base)
    if rate <= 0:
        return 0
    if c("drop_rateincrease", False) and rate < 5000:  # mob.cpp:6847-6849
        rate += 1
    if treasure:  # mob.cpp:6852-6857
        adj, lo, hi = (c("item_rate_treasure", 100), c("item_drop_treasure_min", 1),
                       c("item_drop_treasure_max", 10000))  # fmt: skip
    else:
        k = rate_class(item_type)
        suffix = "_mvp" if boss == "mvp" else ("_boss" if boss == "boss" else "")
        adj = c(f"item_rate_{k}{suffix}", 100)
        lo, hi = c(f"item_drop_{k}_min", 1), c(f"item_drop_{k}_max", 10000)
    if c("item_logarithmic_drops", False) and adj > 0 and adj != 100:  # mob.cpp:4812-4815
        r = rate * math.pow(5.0 - math.log10(rate), math.log(adj / 100.0) / math.log(5.0)) + 0.5
    else:
        r = rate * adj / 100
    rate = int(min(max(r, lo), hi))  # cap_value then the uint32 cast (mob.cpp:4819)
    # mob_getdroprate (mob.cpp:2818-2889): size influence, LUK, the player bonus (100 % for us:
    # no drop-bonus gear; the 90 % cap only bites a bonus), the 100 % and the 0.01 % floors
    if c("drops_by_luk", 0) or c("drops_by_luk2", 0) or c("mob_size_influence", False):
        raise ValueError("this server config adjusts drops by LUK / size: not modelled")
    rate = min(rate, 10000)
    return max(rate, 0) if c("drop_rate0item", False) else max(rate, 1)


def is_rare(base: int, item_type: str) -> bool:
    """Batt's "no rares": base rate <= RARE_RATE, every Card, every PetEgg (never on the floor)."""
    return base <= RARE_RATE or item_type.lower() in ("card", "petegg")


def kill_stats(drops: Sequence[Mapping[str, Any]], L: float = 1.0, key: str = "sell"
               ) -> dict[str, float]:  # fmt: skip
    """PURE: one kill's picked value X = sum_i B_i v_i with B_i ~ Bernoulli(p_i L) independent
    (``drops``: {p, sell, sell_oc, weight, rare}; rares left out). E[X], E[X^2], E[weight]."""
    ev = ew = s2 = sq = core = 0.0
    for d in drops:
        if d.get("rare"):
            continue
        q = float(d["p"]) * L
        v = float(d[key])
        ev += q * v
        ew += q * float(d["weight"])
        s2 += q * v * v
        sq += q * q * v * v
        if int(d.get("base") or 0) >= CORE_RATE:
            core += q * v
    return {"ev": ev, "ew": ew, "ev2": s2 + ev * ev - sq, "ev_core": core}


def mix_stats(species: Mapping[str, Mapping[str, Any]], mix: Mapping[str, float], L: float = 1.0,
              key: str = "sell") -> dict[str, float]:  # fmt: skip
    """PURE: the kill mix's per-kill E[V], E[W], E[V^2] (a kill is species s with probability
    mix[s] / sum(mix)); species missing from ``species`` are reported, not guessed."""
    tot = sum(mix.values())
    ev = ew = ev2 = core = 0.0
    missing = []
    for s, n in mix.items():
        sp = species.get(str(s))
        if sp is None:
            missing.append(s)
            continue
        k = kill_stats(sp["drops"], L, key)
        w = n / tot
        ev += w * k["ev"]
        ew += w * k["ew"]
        ev2 += w * k["ev2"]
        core += w * k["ev_core"]
    return {"ev": ev, "ew": ew, "ev2": ev2, "ev_core": core, "missing": len(missing)}


def ratios(V: float, W: float, EV2: float, K: float, L: float, C: float | None, T_h: float | None,
           cost_h: float = 0.0, gear: float | None = None, V_l: float | None = None,
           W_l: float | None = None, fee: float = 0.0) -> dict[str, Any]:  # fmt: skip
    """PURE: the map ratios (doc section 4). V, W: zeny and weight DROPPED per kill; EV2: E[X^2]
    of the PICKED value per kill (kill_stats with L); K kills per farming hour; L loot
    completeness by value; C free capacity (weight); T_h round trip (h); cost_h consumables per
    farming hour; gear the gear's cost; fee zeny paid once per trip (a Kafra's storage fee).
    V_l / W_l: picked value / weight per kill when known (default L x V, L x W)."""
    vl = L * V if V_l is None else V_l
    wl = L * W if W_l is None else W_l
    G = K * vl
    rate_w = K * wl
    F = C / rate_w if C is not None and rate_w > 0 else None
    u = F / (F + T_h) if F is not None and T_h is not None else None
    Nf = G - cost_h
    N = u * Nf - fee / (F + T_h) if u is not None and F is not None and T_h is not None else None
    n = K * WINDOW_S / 3600.0
    sd = math.sqrt(n * EV2) if n > 0 and EV2 > 0 else None
    return {
        "V": round(V, 2), "W": round(W, 3), "V_per_W": round(V / W, 2) if W else None,
        "K": round(K, 1), "L": round(L, 3), "G_h": round(G, 1), "cost_h": round(cost_h, 1),
        "cost_ratio": round(cost_h / G, 4) if G else None,
        "net_farm_h": round(Nf, 1), "weight_h": round(rate_w, 1),
        "fill_h": None if F is None else round(F, 3), "T_h": None if T_h is None else round(T_h, 4),
        "u": None if u is None else round(u, 4), "net_h": None if N is None else round(N, 1),
        "payback_h": round(gear / N, 1) if gear and N and N > 0 else None,
        "roe_per_h": round(N / gear, 5) if gear and N is not None else None,
        "sharpe_10min": round((n * vl - cost_h * WINDOW_S / 3600.0) / sd, 2) if sd else None,
    }  # fmt: skip


# --- the Crusader's rough kill time (for K_est only; pure) ---------------------------------------


def undead_or_demon(mob: Mapping[str, Any]) -> bool:
    """PURE: Demon Bane's and Divine Protection's targets: Undead race or element, or Demon race
    (battle_check_undead + RC_DEMON, battle.cpp:2291-2294). Compared lower-cased: the capitalised
    names are client UI strings (the locale-pack guard refuses them as literals)."""
    race = str(mob.get("race") or "").lower()
    return race in UNDEAD_DEMON or str(mob.get("element") or "").lower() == UNDEAD_DEMON[0]


def crusader_hit_damage(mob: Mapping[str, Any], attr: Mapping[str, Any],
                        cr: Mapping[str, Any] = CRUSADER) -> tuple[float, float]:  # fmt: skip
    """PURE, ROUGH (doc section 5): the MAIN Crusader's mean normal-hit damage on ``mob`` and its
    hit chance (a plant -- IgnoreMelee -- takes 1 per hit). Weapon roll
    ~ U[min(DEX x (80 + 20 WL) / 100, ATK), ATK) x size fix + batk, x the
    Neutral -> element fix, x (100 - DEF) / 100, - (VIT + E[rnd(0, (VIT/20)^2 - 1)]) (pre-re mob
    soft DEF, battle.cpp:4825-4832), + Sword Mastery 40, + Demon Bane 60 on Undead race / element
    or Demon race (battle.cpp:2291-2294); crits ignored.
    Hit = clamp(80 + HIT - (lv + AGI), 5, 100)."""
    atk = float(cr["weapon_atk"])
    lo = min(int(cr["dex"] * (80 + 20 * cr["weapon_level"]) / 100), int(atk))
    roll = (lo + atk - 1) / 2.0
    size = float(cr["size_fix"].get(str(mob.get("size") or "Small"), 100)) / 100.0
    ele = str(mob.get("element") or "Neutral")
    lvl = int(mob.get("element_level") or 1)
    fix = float(((attr.get(str(lvl)) or {}).get("Neutral") or {}).get(ele, 100)) / 100.0
    vit = int(mob.get("vit") or 0)
    rnd = (vit // 20) ** 2
    vit_def = vit + ((rnd - 1) / 2.0 if rnd > 0 else 0.0)
    dmg = (roll * size + float(cr["batk"])) * fix * (100 - min(100, int(mob.get("def") or 0)))
    dmg = dmg / 100.0 - vit_def + float(cr["sword_mastery"])
    if undead_or_demon(mob):
        dmg += float(cr["demon_bane"])
    if "IgnoreMelee" in (mob.get("modes") or ()):  # plants: every melee hit does 1 (mob modes)
        dmg = 1.0
    flee = int(mob.get("level") or 1) + int(mob.get("agi") or 0)
    hit = min(100, max(5, 80 + int(cr["hit"]) - flee)) / 100.0
    return max(1.0, dmg), hit


def k_est(species: Mapping[str, Mapping[str, Any]], mix: Mapping[str, float],
          search_s: float = SEARCH_S,
          cr: Mapping[str, Any] = CRUSADER) -> float | None:  # fmt: skip
    """PURE, ROUGH: kills per hour = 3600 / (search_s + E[HP / DPS]) over the kill mix."""
    tot = sum(mix.values())
    if not tot:
        return None
    t = 0.0
    for s, n in mix.items():
        sp = species.get(str(s))
        if sp is None or not sp.get("dps"):
            return None
        t += n / tot * float(sp["hp"]) / float(sp["dps"])
    return 3600.0 / (search_s + t)


# --- trips (walk over portals to the nearest NPC that buys) ---------------------------------------


def grid_costs(nopass: Sequence[bool], xs: int, ys: int,
               seeds: Mapping[int, tuple[float, int]], step: float
               ) -> tuple[list[float], list[int]]:  # fmt: skip
    """PURE: Dijkstra over a map's cells from ``seeds`` (cell index -> (initial cost, goal
    label)): a straight step costs ``step``, a diagonal 1.4 x (unit.cpp:228-231,
    MOVE_DIAGONAL_COST 14 / MOVE_COST 10) and needs both orthogonal cells free (path.cpp's rule,
    as kb_first_workflow.Rooms). Returns (cost, the label of the goal reached) per cell."""
    inf = math.inf
    dist = [inf] * (xs * ys)
    lab = [-1] * (xs * ys)
    heap: list[tuple[float, int]] = []
    for i, (c, g) in seeds.items():
        if not nopass[i] and c < dist[i]:
            dist[i] = c
            lab[i] = g
            heap.append((c, i))
    heapq.heapify(heap)
    diag = step * 1.4
    dirs = [(1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (1, -1), (-1, 1), (-1, -1)]
    while heap:
        d, i = heapq.heappop(heap)
        if d > dist[i]:
            continue
        x, y = i % xs, i // xs
        for dx, dy in dirs:
            nx, ny = x + dx, y + dy
            if nx < 0 or ny < 0 or nx >= xs or ny >= ys:
                continue
            j = nx + ny * xs
            if nopass[j]:
                continue
            if dx and dy:
                if nopass[x + dx + y * xs] or nopass[x + (y + dy) * xs]:
                    continue
                nd = d + diag
            else:
                nd = d + step
            if nd < dist[j]:
                dist[j] = nd
                lab[j] = lab[i]
                heapq.heappush(heap, (nd, j))
    return dist, lab


def nopass_list(g: Any) -> list[bool]:
    """MapGrid.nopass for every cell (index x + y * xs), vectorised: gat types 1 and 5, the last
    row and column (poring_dataset.mapcache.MapGrid.nopass)."""
    import numpy as np

    a = np.isin(np.frombuffer(g.cells, dtype=np.uint8), (1, 5)).reshape(g.ys, g.xs)
    a[g.ys - 1, :] = True
    a[:, g.xs - 1] = True
    return [bool(v) for v in a.ravel()]


def near_cells(nopass: Sequence[bool], xs: int, ys: int, cx: int, cy: int,
               r: int = NEAR) -> list[int]:  # fmt: skip
    """Walkable cells within Chebyshev ``r`` of (cx, cy)."""
    return [
        x + y * xs
        for y in range(max(0, cy - r), min(ys, cy + r + 1))
        for x in range(max(0, cx - r), min(xs, cx + r + 1))
        if not nopass[x + y * xs]
    ]


def trip_fields(grids: Mapping[str, Any], portals: Mapping[str, Sequence[Mapping[str, Any]]],
                goals: Mapping[str, Sequence[tuple[int, int, int]]], maps: Iterable[str],
                step_s: float = WALK_MS / 1000.0, change_s: float = CHANGE_S,
                rounds: int = 12) -> dict[str, tuple[list[float], list[int]]]:  # fmt: skip
    """Per map, the seconds from each cell to the nearest goal (a cell within NEAR of a goal NPC)
    walking over portals (a portal's trigger area x +- span_x, y +- span_y, npc.cpp:4994-4999,
    puts you on its destination cell; ``change_s`` per map change). Bellman-Ford over maps, each
    map a grid Dijkstra seeded by its goals ((x, y, label)) and its portals' destination costs;
    each cell also carries the label of the goal it reaches."""
    nps = {m: nopass_list(grids[m]) for m in maps}
    fields: dict[str, tuple[list[float], list[int]]] = {}
    last: dict[str, dict[int, tuple[float, int]]] = {}
    for _ in range(rounds):
        changed = False
        for m in nps:
            g = grids[m]
            seeds: dict[int, tuple[float, int]] = {}
            for gx, gy, gl in goals.get(m, ()):
                for i in near_cells(nps[m], g.xs, g.ys, gx, gy):
                    seeds[i] = (0.0, gl)
            for p in portals.get(m, ()):
                f = fields.get(p["to_map"])
                if f is None:
                    continue
                tg = grids[p["to_map"]]
                tx, ty = int(p["to_x"]), int(p["to_y"])
                if not (0 <= tx < tg.xs and 0 <= ty < tg.ys):
                    continue
                c, cl = f[0][tx + ty * tg.xs], f[1][tx + ty * tg.xs]
                if not math.isfinite(c):
                    continue
                for y in range(p["y"] - p["span_y"], p["y"] + p["span_y"] + 1):
                    for x in range(p["x"] - p["span_x"], p["x"] + p["span_x"] + 1):
                        if 0 <= x < g.xs and 0 <= y < g.ys and not nps[m][x + y * g.xs]:
                            i = x + y * g.xs
                            v = c + change_s + float(p.get("extra_s") or 0.0)
                            if v < seeds.get(i, (math.inf, -1))[0]:
                                seeds[i] = (v, cl)
            if not seeds or seeds == last.get(m):
                continue
            last[m] = seeds
            fields[m] = grid_costs(nps[m], g.xs, g.ys, seeds, step_s)
            changed = True
        if not changed:
            break
    return fields


def trip_summary(field: tuple[Sequence[float], Sequence[int]] | None,
                 goals: Sequence[Mapping[str, Any]] = (), sell_s: float = SELL_S
                 ) -> dict[str, Any]:  # fmt: skip
    """PURE: one-way seconds from a uniformly random reachable cell of the farm map (mean, p50,
    max), the goal most cells reach (``goals`` indexed by label) and its share, and the ROUND TRIP
    T = 2 x mean one-way + the time at the NPC (the return is assumed to cost the same: back to a
    random cell)."""
    if field is None:
        return {"T_s": None, "why": "no goal reachable within the hop limit"}
    dist, lab = field
    v = sorted(c for c in dist if math.isfinite(c))
    if not v:
        return {"T_s": None, "why": "no cell of the farm map reaches a goal"}
    mean = sum(v) / len(v)
    cnt: dict[int, int] = defaultdict(int)
    for c, g in zip(dist, lab, strict=True):
        if math.isfinite(c):
            cnt[g] += 1
    top = max(cnt, key=lambda g: cnt[g])
    return {"one_way_mean_s": round(mean, 1), "one_way_p50_s": round(v[len(v) // 2], 1),
            "one_way_max_s": round(v[-1], 1), "cells": len(v), "npc_s": sell_s,
            "T_s": round(2 * mean + sell_s, 1),
            "goal": dict(goals[top]) if 0 <= top < len(goals) else None,
            "goal_share": round(cnt[top] / len(v), 3)}  # fmt: skip


# --- building (reads the pinned tree; not pure) --------------------------------------------------


def _yaml(text: str) -> Any:
    import yaml

    return yaml.load(text, Loader=getattr(yaml, "CSafeLoader", yaml.SafeLoader))  # noqa: S506


def server_conf(src: Any) -> dict[str, Any]:
    """The battle settings the drop rules read, from the pinned conf files in load order (the
    lab's conf/import/battle_conf.txt is the empty template: no override)."""
    import kb_build

    out: dict[str, Any] = {}
    for p in CONFS:
        for k, v in kb_build.parse_battle_conf(src.read(p)).items():
            out[k] = kb_build._conf_value(v)
    return out


def mob_rows(src: Any, items: Mapping[str, Any], conf: Mapping[str, Any],
             attr: Mapping[str, Any]) -> dict[str, dict[str, Any]]:  # fmt: skip
    """mob id -> {name, level, hp, race, element, size, def, vit, agi, aggressive, boss, drops:
    [{item_id, base, rate, p, sell, sell_oc, weight, type, rare}]} (+ the Crusader's rough dps)."""
    import kb_route

    ai = kb_route.ai_modes(src.ref)
    by_aegis = {str(v.get("aegis")): k for k, v in items.items() if v.get("aegis")}
    out: dict[str, dict[str, Any]] = {}
    for e in _yaml(src.read(MOB_DB))["Body"]:
        modes = {k for k, v in (e.get("Modes") or {}).items() if v}
        bits = ai.get(str(e.get("Ai", "06")).zfill(2), 0)
        cls = str(e.get("Class") or "").lower()  # absent = the default class
        boss = "mvp" if (e.get("MvpExp") or e.get("MvpDrops")) else ("boss" if cls == "boss"
                                                                     else "")  # fmt: skip
        treasure = bool((e.get("RaceGroups") or {}).get("Treasure"))
        drops = []
        for d in e.get("Drops") or []:
            iid = by_aegis.get(str(d.get("Item")))
            it = items.get(iid) if iid is not None else None
            if it is None:
                drops.append({"item_id": None, "aegis": str(d.get("Item")), "base": d.get("Rate"),
                              "p": 0.0, "sell": 0, "sell_oc": 0, "weight": 0.0, "rare": True,
                              "type": None, "note": "unknown item: left out"})  # fmt: skip
                continue
            base = int(d.get("Rate") or 0)
            r = effective_rate(base, str(it["type"]), conf, boss, treasure)
            drops.append({"item_id": int(str(iid)), "base": base, "rate": r, "p": r / 10000.0,
                          "sell": it["sell"], "sell_oc": it["sell_oc10"],
                          "weight": it["weight"], "type": it["type"],
                          "rare": is_rare(base, str(it["type"]))})  # fmt: skip
        row = {
            "name": e.get("Name"), "aegis": e.get("AegisName"), "level": int(e.get("Level") or 1),
            "hp": int(e.get("Hp") or 1), "race": e.get("Race") or "Formless",
            "element": e.get("Element") or "Neutral",
            "element_level": int(e.get("ElementLevel") or 1), "size": e.get("Size") or "Small",
            "def": int(e.get("Defense") or 0), "vit": int(e.get("Vit") or 0),
            "agi": int(e.get("Agi") or 0), "atk": [e.get("Attack"), e.get("Attack2")],
            "aggressive": bool(bits & kb_route.MD_AGGRESSIVE) or "Aggressive" in modes,
            "looter": bool(bits & 0x2), "boss": boss, "drops": drops, "modes": sorted(modes),
            "rare_v": round(sum(d["p"] * d["sell"] for d in drops if d.get("rare")), 3),
        }  # fmt: skip
        dmg, hit = crusader_hit_damage(row, attr)
        row["crusader_hit"], row["crusader_dmg"] = round(hit, 2), round(dmg, 1)
        row["dps"] = round(hit * dmg * 1000.0 / CRUSADER["adelay_ms"], 1)
        out[str(int(e["Id"]))] = row
    return out


def metamorphoses(src: Any) -> dict[int, int]:
    """mob id -> the mob it turns into (NPC_METAMORPHOSIS, skill 193: val1), from the pinned
    db/pre-re/mob_skill_db.txt (e.g. prt_fild08's Pupa -> Creamy)."""
    import kb_build

    out = {}
    for mid, rows in kb_build.parse_mob_skills(src.read("db/pre-re/mob_skill_db.txt")).items():
        for r in rows:
            if r["skill"] == kb_build.METAMORPHOSIS and str(r["vals"][0]).isdigit():
                out[mid] = int(r["vals"][0])
    return out


def spawn_mix(world: Any, m: str) -> tuple[dict[str, int], list[dict[str, Any]]]:
    """The map's normal spawn lines -> mob id -> amount; boss_monster lines apart (not farmed)."""
    import kb_first_workflow as kf

    mix: dict[str, int] = defaultdict(int)
    bosses = []
    for r in world.on_map.get(m, []):
        if r.type != "monster":
            continue
        s = kf.spawn_entry(r, world.sprites.mobs)
        if s["boss"]:
            bosses.append({"id": s["id"], "amount": s["amount"], "key": s["key"]})
        else:
            mix[str(s["id"])] += int(s["amount"])
    return dict(mix), bosses


def goal_npcs(
    world: Any, placed_shops: Sequence[Mapping[str, Any]]
) -> tuple[dict[str, list[tuple[int, int]]], dict[str, list[tuple[int, int, int]]]]:
    """(shops by map: cells; Kafras by map: cells + storage fee). A Kafra is an NPC whose script
    calls F_Kafra; its 4th argument is the storage fee (npc/kafras/kafras.txt:10-16)."""
    shops: dict[str, list[tuple[int, int]]] = defaultdict(list)
    for s in placed_shops:
        if not s["floating"]:
            shops[str(s["map"])].append((int(s["x"]), int(s["y"])))
    kafras: dict[str, list[tuple[int, int, int]]] = defaultdict(list)
    for r in world.recs:
        if not r.map or r.type not in ("script", "duplicate"):
            continue
        src = world.source(r)
        body = (src.body if src is not None else None) or ""
        m = re.search(r'callfunc\s*\(?\s*"F_Kafra"\s*,([^;]*);', body)
        if not m:
            continue
        args = [a.strip(" )") for a in m[1].split(",")]
        fee = int(args[3]) if len(args) > 3 and args[3].lstrip("-").isdigit() else -1
        where = r.w1.split(",")
        kafras[r.map].append((int(where[1]), int(where[2]), fee))
    return dict(shops), dict(kafras)


def portals_of(world: Any) -> dict[str, list[dict[str, Any]]]:
    """Per map, the ways out a walker uses: portals (a warp line: its trigger area) and
    "transport" NPCs (kb_first_workflow.all_edges: a script warp that tests no variable, e.g. a
    dungeon's entrance / exit NPC: used from within NEAR of the NPC, + 3 s of dialog). Kafra
    teleports and quest-gated NPC warps are left out (a walk trip; doc section 4)."""
    import kb_first_workflow as kf

    out: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for e in kf.all_edges(world):
        if e["via"] == "portal":
            out[e["from"]].append({"x": e["cell"][0], "y": e["cell"][1], "span_x": e["span"][0],
                                   "span_y": e["span"][1], "to_map": e["to"],
                                   "to_x": e["to_cell"][0], "to_y": e["to_cell"][1],
                                   "via": "portal", "extra_s": 0.0})  # fmt: skip
        elif e["via"] == "transport" and e.get("npc_cell"):
            out[e["from"]].append({"x": e["npc_cell"][0], "y": e["npc_cell"][1], "span_x": NEAR,
                                   "span_y": NEAR, "to_map": e["to"], "to_x": e["to_cell"][0],
                                   "to_y": e["to_cell"][1], "via": "transport", "extra_s": 3.0,
                                   "zeny": e.get("zeny")})  # fmt: skip
    return dict(out)


def hops(portals: Mapping[str, Sequence[Mapping[str, Any]]], starts: Iterable[str],
         reverse: bool = False) -> dict[str, int]:  # fmt: skip
    """PURE: portal hops from ``starts`` (BFS over the ways out; ``reverse``: hops TO them)."""
    adj: dict[str, set[str]] = defaultdict(set)
    for m, ps in portals.items():
        for q in ps:
            if reverse:
                adj[q["to_map"]].add(m)
            else:
                adj[m].add(q["to_map"])
    dist = {s: 0 for s in starts}
    front = list(dist)
    while front:
        nxt = []
        for m in front:
            for b in adj.get(m, ()):
                if b not in dist:
                    dist[b] = dist[m] + 1
                    nxt.append(b)
        front = nxt
    return dist


def route_maps(portals: Mapping[str, Sequence[Mapping[str, Any]]], start: str,
               goal_maps: Iterable[str], known: Iterable[str], slack: int = 1,
               cap: int = MAX_HOPS) -> list[str]:  # fmt: skip
    """PURE: the maps on a route from ``start`` to a goal map at most ``slack`` hops longer than
    the fewest (and at most ``cap`` hops), with a map cache. The trip's time search runs on these
    only (a full 5-hop neighbourhood is dozens of 400 x 400 grids)."""
    ok = set(known)
    df = hops(portals, [start])
    dg = hops(portals, [g for g in goal_maps if g in ok], reverse=True)
    if start not in dg or dg[start] > cap:
        return []
    best = dg[start]
    return sorted(m for m in ok if m in df and m in dg and df[m] + dg[m] <= best + slack)


def load_grids() -> dict[str, Any]:
    """The server's map cache (pre-re first, then base; db/import is the empty template), read
    from the pinned tree in RAM and checked against poring_dataset's lock."""
    import hashlib

    from poring_dataset import mapcache

    lock = json.loads(mapcache.LOCK.read_text())["files"]
    caches = []
    for key, path in (("pre-re", "db/pre-re/map_cache.dat"), ("base", "db/map_cache.dat")):
        data = (SRC / path).read_bytes()
        if hashlib.sha256(data).hexdigest() != lock[key]["sha256"]:
            raise SystemExit(f"{path}: sha256 differs from mapcache.lock.json")
        caches.append(mapcache.parse(data))
    return mapcache.merge(caches)


def build(maps: Sequence[str], items_doc: Mapping[str, Any]) -> dict[str, Any]:
    import kb_first_workflow as kf

    src = kf.Src(SRC)
    world = kf.build_world(src)
    conf = server_conf(src)
    attr = {str(b["Level"]): {k: v for k, v in b.items() if k != "Level"}
            for b in _yaml(src.read("db/pre-re/attr_fix.yml"))["Body"]}  # fmt: skip
    mobs = mob_rows(src, items_doc["items"], conf, attr)
    shops, kafras = goal_npcs(world, items_doc["shops"])
    goal_list: dict[str, list[dict[str, Any]]] = {"sell": [], "kafra": []}
    shop_goals: dict[str, list[dict[str, Any]]] = defaultdict(list)
    kafra_goals: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for mm, cells in shops.items():
        for x, y in cells:
            row = {"map": mm, "x": x, "y": y, "label": len(goal_list["sell"])}
            goal_list["sell"].append(row)
            shop_goals[mm].append(row)
    for mm, cells3 in kafras.items():
        for x, y, fee in cells3:
            row = {"map": mm, "x": x, "y": y, "fee": fee, "label": len(goal_list["kafra"])}
            goal_list["kafra"].append(row)
            kafra_goals[mm].append(row)
    portals = portals_of(world)
    grids = load_grids()
    meta = metamorphoses(src)
    out: dict[str, Any] = {}
    for m in maps:
        mix, bosses = spawn_mix(world, m)
        extra = {str(meta[int(s)]) for s in mix if int(s) in meta} - set(mix)
        t0 = time.monotonic()
        trip: dict[str, Any] = {}
        for name, gl in (("sell", shop_goals), ("kafra", kafra_goals)):
            area = route_maps(portals, m, gl, grids)
            lab: dict[str, list[tuple[int, int, int]]] = {}
            for k, rows in gl.items():
                if k in area:
                    lab[k] = [(int(r["x"]), int(r["y"]), int(r["label"])) for r in rows]
            f = trip_fields(grids, portals, lab, area)
            trip[name] = {**trip_summary(f.get(m), goal_list[name],
                                         SELL_S if name == "sell" else KAFRA_S),
                          "maps": area}  # fmt: skip
        trip["compute_s"] = round(time.monotonic() - t0, 1)
        out[m] = {
            "mix": mix, "bosses": bosses,
            "species": {s: mobs[s] for s in [*mix, *sorted(extra)] if s in mobs},
            "metamorphosis_species": sorted(extra),
            "trip": trip,
            "why": CANDIDATES.get(m, "the bot's map" if m.startswith("prt_fild")
                                  else "the Crusader's map"),
        }  # fmt: skip
    return {"meta": {"rathena_ref": src.ref, "built_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                     "conf": {k: v for k, v in conf.items()
                              if k.startswith(("item_", "drop", "drops_", "mob_size"))},
                     "rare_rate": RARE_RATE, "walk_ms": WALK_MS, "change_s": CHANGE_S,
                     "sell_s": SELL_S, "kafra_s": KAFRA_S, "near": NEAR,
                     "max_hops": MAX_HOPS},
            "maps": out}  # fmt: skip


def load(path: Path = OUT) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"{path} missing: run scripts/econ_model.py build")
    doc: dict[str, Any] = json.loads(path.read_text())
    return doc


# --- the model of one map (pure) -----------------------------------------------------------------


def map_model(mdoc: Mapping[str, Any], K: float | None = None, L: float = 1.0,
              C: float | None = None, T_s: float | None = None, cost_h: float = 0.0,
              gear: float | None = None, mix: Mapping[str, float] | None = None,
              oc: bool = False, search_s: float = SEARCH_S) -> dict[str, Any]:  # fmt: skip
    """PURE: one map's model row. K None = the Crusader's rough K_est; C None = the Crusader's
    free capacity at 50 % (0.5 x 4150 - 920 gear = 1155); T_s None = the map's walk trip that
    resets the bag soonest: the nearest NPC that buys, or the nearest Kafra (storage; its fee is
    paid once per trip)."""
    sp = mdoc["species"]
    mx = {str(k): float(v) for k, v in (mix or mdoc["mix"]).items()}
    key = "sell_oc" if oc else "sell"
    drop = mix_stats(sp, mx, 1.0, key)
    picked = mix_stats(sp, mx, L, key)
    ke = k_est(sp, mx, search_s)
    k = ke if K is None else K
    trip = mdoc.get("trip") or {}
    ts = (trip.get("sell") or {}).get("T_s")
    tk = (trip.get("kafra") or {}).get("T_s")
    fee = 0.0
    t: float | None
    if T_s is not None:
        t, via = T_s, "given"
    elif tk is not None and (ts is None or tk < ts):
        t, via = tk, "kafra"
        fee = float(((trip["kafra"].get("goal") or {}).get("fee")) or 0)
    else:
        t, via = ts, "sell"
    c = 0.5 * CRUSADER["max_weight"] - CRUSADER["gear_weight"] if C is None else C
    tot = sum(mx.values())
    hp = sum(float(sp[s]["hp"]) * n for s, n in mx.items() if s in sp) / tot if tot else None
    und = sum(n for s, n in mx.items() if s in sp and undead_or_demon(sp[s]))
    agg = sum(n for s, n in mx.items() if s in sp and sp[s]["aggressive"])
    rare = sum(float(sp[s]["rare_v"]) * n for s, n in mx.items() if s in sp) / tot if tot else 0
    out: dict[str, Any] = {
        "kill_mix_n": tot, "species": len(mx), "missing_species": drop["missing"],
        "hp_mean": None if hp is None else round(hp, 0),
        "V_per_HP": round(drop["ev"] / hp, 3) if hp else None,
        "undead_demon_share": round(und / tot, 3) if tot else None,
        "aggressive_share": round(agg / tot, 3) if tot else None,
        "rare_v": round(rare, 2), "V_core": round(drop["ev_core"], 2),
        "V_tail": round(drop["ev"] - drop["ev_core"], 2),
        "K_est": None if ke is None else round(ke, 1),
        "K_source": "rough K_est (doc 5)" if K is None else "given",
        "C": round(c, 1), "T_s": t, "T_via": via, "T_sell_s": ts, "T_kafra_s": tk,
        "trip_fee": fee, "oc": oc,
    }  # fmt: skip
    if k is None:
        out["why"] = "no K (no estimate for this mix)"
        return out
    out.update(ratios(drop["ev"], drop["ew"], picked["ev2"], k, L, c,
                      None if t is None else t / 3600.0, cost_h, gear,
                      picked["ev"], picked["ew"], fee))  # fmt: skip
    return out


def gear_cost(items_doc: Mapping[str, Any], ids: Sequence[int] = CRUSADER["gear"],
              dc: bool = False) -> int | None:  # fmt: skip
    """The gear's cost at the cheapest loaded NPC shop (crusader-build.md 4a: 310,000)."""
    key = "npc_buy_dc10" if dc else "npc_buy"
    vals = [items_doc["items"].get(str(i), {}).get(key) for i in ids]
    return None if any(v is None for v in vals) else int(sum(vals))


def species_rows(mdoc: Mapping[str, Any], L: float = 1.0, top: int = 3
                 ) -> list[tuple[str, dict[str, Any]]]:  # fmt: skip
    """PURE: value per kill PER SPECIES of a built map (``mdoc``: maps.json's entry), at the NPC
    sell price (V) and at Overcharge Lv 10 (V_oc), with the weight (W), the core part (drops at
    >= 1 %), the rares' value apart (rare_v, NPC sell; never in V) and the ``top`` items by their
    Overcharge value per kill [item id, p, sell, sell_oc]; ``L`` the loot completeness. Then the
    spawn mix (normal lines; boss lines are not farmed) and the same mix without the plants
    (IgnoreMelee species: one damage per hit, struck only when met)."""
    sp = mdoc["species"]
    mix = {str(k): float(v) for k, v in mdoc["mix"].items()}
    rows: list[tuple[str, dict[str, Any]]] = []
    for s in [*mix, *(k for k in sp if k not in mix)]:
        if s not in sp:
            continue
        r, k, ko = sp[s], kill_stats(sp[s]["drops"], L), kill_stats(sp[s]["drops"], L, "sell_oc")
        best = sorted((d for d in r["drops"] if not d.get("rare")),
                      key=lambda d: -float(d["p"]) * float(d["sell_oc"]))[:top]  # fmt: skip
        rows.append((f"{s} {r.get('name')}", {
            "spawns": int(mix.get(s, 0)), "aggressive": bool(r.get("aggressive")),
            "V": round(k["ev"], 2), "V_oc": round(ko["ev"], 2), "W": round(k["ew"], 3),
            "V_core_oc": round(ko["ev_core"], 2), "rare_v": r.get("rare_v"),
            "top_oc": [[d["item_id"], d["p"], d["sell"], d["sell_oc"]] for d in best],
        }))  # fmt: skip
    plants = {s for s in mix if s in sp and "IgnoreMelee" in (sp[s].get("modes") or ())}
    for name, m in (("spawn mix", mix), ("mix, no plants", {s: n for s, n in mix.items()
                                                             if s not in plants})):  # fmt: skip
        a, b = mix_stats(sp, m, L), mix_stats(sp, m, L, "sell_oc")
        rows.append((name, {"spawns": int(sum(m.values())), "V": round(a["ev"], 2),
                            "V_oc": round(b["ev"], 2), "W": round(a["ew"], 3),
                            "V_core_oc": round(b["ev_core"], 2)}))  # fmt: skip
    return rows


def fmt_table(rows: Sequence[tuple[str, Mapping[str, Any]]], keys: Sequence[str],
              first: str = "map") -> str:  # fmt: skip
    """PURE: a box-drawing table, one row per map (``first``: the first column's title)."""
    head = [first, *keys]
    cells = [[name, *("-" if r.get(k) is None else str(r.get(k)) for k in keys)]
             for name, r in rows]  # fmt: skip
    ws = [max(len(h), *(len(c[i]) for c in cells)) for i, h in enumerate(head)]

    def line(a: str, b: str, c: str) -> str:
        return a + b.join("─" * (w + 2) for w in ws) + c

    out = [line("┌", "┬", "┐"), "│ " + " │ ".join(h.ljust(w) for h, w in zip(head, ws,
                                                                          strict=True)) + " │",
           line("├", "┼", "┤")]  # fmt: skip
    for c in cells:
        out.append("│ " + " │ ".join(x.ljust(w) for x, w in zip(c, ws, strict=True)) + " │")
    out.append(line("└", "┴", "┘"))
    return "\n".join(out)


TABLE_KEYS = (
    "species",
    "hp_mean",
    "undead_demon_share",
    "aggressive_share",
    "V",
    "V_core",
    "V_tail",
    "V_per_W",
    "W",
    "V_per_HP",
    "rare_v",
    "K",
    "T_sell_s",
    "T_kafra_s",
    "T_via",
    "fill_h",
    "u",
    "G_h",
    "net_h",
    "payback_h",
    "roe_per_h",
    "sharpe_10min",
)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)  # fmt: skip
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build")
    b.add_argument("maps", nargs="*")
    b.add_argument("--out", type=Path, default=OUT)
    s = sub.add_parser("show")
    s.add_argument("map")
    for t in (sub.add_parser("table"), s):
        t.add_argument("--K", type=float)
        t.add_argument("--L", type=float, default=0.9)
        t.add_argument("--C", type=float)
        t.add_argument("--T-s", type=float, dest="T_s")
        t.add_argument("--cost-h", type=float, default=0.0)
        t.add_argument("--gear", type=float)
        t.add_argument("--oc", action="store_true")
        t.add_argument("--search-s", type=float, default=SEARCH_S)
    sub.choices["table"].add_argument("maps", nargs="*")
    sub.add_parser("screen")
    sp_ = sub.add_parser("species")
    sp_.add_argument("map")
    sp_.add_argument("--L", type=float, default=1.0)
    sp_.add_argument("--top", type=int, default=3)
    a = ap.parse_args()
    import econ_items

    items_doc = econ_items.load()
    if a.cmd == "build":
        maps = a.maps or [*MAPS, *CANDIDATES]
        doc = build(maps, items_doc)
        if a.out.exists():  # keep maps built earlier
            old = json.loads(a.out.read_text())
            doc["maps"] = {**old.get("maps", {}), **doc["maps"]}
        a.out.parent.mkdir(parents=True, exist_ok=True)
        tmp = a.out.with_suffix(".part")
        tmp.write_text(json.dumps(doc, ensure_ascii=False, separators=(",", ":")) + "\n")
        tmp.replace(a.out)
        back = json.loads(a.out.read_text())
        print(json.dumps({m: {"species": len(v["species"]), "trip": v["trip"]}
                          for m, v in back["maps"].items() if m in maps}, indent=1))  # fmt: skip
        return 0
    if a.cmd == "screen":
        return screen(items_doc)
    doc = load()
    if a.cmd == "species":
        if a.map not in doc["maps"]:
            print(f"{a.map}: not built (econ_model.py build {a.map})")
            return 1
        print(fmt_table(species_rows(doc["maps"][a.map], a.L, a.top),
                        ("spawns", "aggressive", "V", "V_oc", "W", "V_core_oc", "rare_v",
                         "top_oc"), first="species"))  # fmt: skip
        return 0
    gear = a.gear if a.gear is not None else gear_cost(items_doc)
    names = [a.map] if a.cmd == "show" else (a.maps or list(doc["maps"]))
    rows = []
    for m in names:
        if m not in doc["maps"]:
            print(f"{m}: not built (econ_model.py build {m})")
            continue
        rows.append((m, map_model(doc["maps"][m], a.K, a.L, a.C, a.T_s, a.cost_h, gear,
                                  oc=a.oc, search_s=a.search_s)))  # fmt: skip
    if a.cmd == "show":
        print(json.dumps(rows[0][1], indent=1))
    else:
        print(fmt_table(rows, TABLE_KEYS))
    return 0


def screen(items_doc: Mapping[str, Any]) -> int:
    """Every map with normal spawn lines: level band, Undead / Demon share, V, V/HP, K_est (no
    trips): the Base-60 Crusader screen behind CANDIDATES."""
    import kb_first_workflow as kf

    src = kf.Src(SRC)
    world = kf.build_world(src)
    conf = server_conf(src)
    attr = {str(b["Level"]): {k: v for k, v in b.items() if k != "Level"}
            for b in _yaml(src.read("db/pre-re/attr_fix.yml"))["Body"]}  # fmt: skip
    mobs = mob_rows(src, items_doc["items"], conf, attr)
    rows = []
    for m in sorted(world.on_map):
        mix, _b = spawn_mix(world, m)
        if not mix or sum(mix.values()) < 20:
            continue
        mdoc = {"mix": mix, "species": {s: mobs[s] for s in mix if s in mobs}, "trip": {}}
        lv = [mobs[s]["level"] for s in mix if s in mobs]
        r = map_model(mdoc, None, 0.9, None, 0.0, 0.0, None)
        r["lv"] = f"{min(lv)}-{max(lv)}" if lv else "-"
        rows.append((m, r))
    rows.sort(key=lambda x: -(x[1].get("G_h") or 0))
    print(fmt_table(rows, ("lv", "species", "kill_mix_n", "hp_mean", "undead_demon_share",
                           "aggressive_share", "V", "V_per_W", "V_per_HP", "rare_v", "K_est",
                           "G_h")))  # fmt: skip
    return 0


if __name__ == "__main__":
    sys.exit(main())
