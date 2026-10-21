#!/usr/bin/env python3
"""ECONOMICS, part 2 (Batt 2026-10-21): the per-run ECONOMIC ROW -- what a run earned and spent at
FIXED NPC prices, from its packets (OFFLINE ground truth, ADR-0007; nothing here reaches a bot).

    econ_row.py SID [SID ...] [--json] [--pool]      the rows (+ the map model beside each)
    econ_row.py --banked prt_fild08 --json           back-fill: every banked hunt run there
    econ_row.py --trials --json                      every banked Crusader survival trial

Every metric (docs/econ/economics.md section 3 defines each symbol):
- window: the run's judged window (search_study.load_session: a bot run from its first walk to its
  last click + 5 s; Batt's demo 600 s from his first walk; a survival trial its manifest's
  t0_ns..t1_ns); hours h.
- K = our kills / h (arm_judge.kills_of: a monster's death <= 1.5 s after OUR damaging hit).
- the drops of our kills (arm_judge.drops_of_kill through loot_complete.kill_rows): items x count,
  their zeny at the NPC sell price (plain and with Overcharge 10) and their weight.
- V = zeny PICKED per kill (the items of our kills our pickups took, at NPC sell);
  V_theor = zeny DROPPED per kill (all our kills' drops); L = V / V_theor (by VALUE), and L by
  count; L_net leaves a looter's re-drop of our own item out of the dropped value (counted once:
  loot_complete.link_redrops).
- W = weight picked per kill; V / W = zeny per weight unit.
- consumables: OUR use_item_result successes (aid filter: a success is broadcast to the area) at
  the cheapest loaded NPC's price, plain and with Discount 10; deaths / h (our own "died" vanish).
- gross / h = K x V; cost / h; net / h = gross - cost; cost ratio = cost / gross; "best" = sold
  with Overcharge 10 and bought with Discount 10.
- the 10-min windows (full windows only, from the window's start): net zeny booked at each
  pickup / use time, x 6 = zeny / h per window; the Sharpe-like ratio = mean / sample sd of those
  (None below 2 windows: a 10-min demo has one).
- capacity: the max_weight and weight packets (db units / 10) at the window's start; the fill
  time to 50 % (regen stops: natural_heal_weight_rate 50, pre-re default) and to 90 % (no attack:
  major_overweight_rate 90) at this run's weight rate K x W: (x % x C - weight0) / (K x W) hours.
  50 % is the one the model's u uses.
Missing data is None with the reason in "why" -- never invented.
"""

from __future__ import annotations

import argparse
import functools
import gzip
import json
import math
import sys
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

DEMO = Path("/dev/shm/poring-lab-demo")
NS = 1_000_000_000
AID = 2000002  # our block id: the GM account (the Novice GM and the Crusader are characters on it)
WIN_S = 600.0
POTION_TYPES = ("healing",)
FLY, BUTTERFLY = 601, 602


# --- pure parts ----------------------------------------------------------------------------------


def series_at(packets: Sequence[Mapping[str, Any]], name: str, t: int) -> int | None:
    """PURE: our stat ``name`` in force at ``t`` (the last stat_change at or before it; else the
    first one after it -- a run whose first packet of that stat comes later)."""
    before = after = None
    for e in packets:
        if e.get("type") != "stat_change" or e.get("name") != name:
            continue
        if int(e["t_mono_ns"]) <= t:
            before = int(e.get("value") or 0)
        elif after is None:
            after = int(e.get("value") or 0)
    return before if before is not None else after


def kill_species(packets: Sequence[Mapping[str, Any]], kills: Iterable[tuple[int, int]]
                 ) -> dict[int, int]:  # fmt: skip
    """PURE: kill gid -> its species: the job of its latest monster appear before the kill
    (rAthena reuses a dead mob's id)."""
    want = {g: t for t, g in kills}
    last: dict[int, int] = {}
    out: dict[int, int] = {}
    for e in packets:
        if e.get("type") == "entity_appear" and e.get("objtype") == 5 and e.get("gid") is not None:
            g = int(e["gid"])
            if g in want and int(e["t_mono_ns"]) <= want[g]:
                last[g] = int(e.get("job", -1))
    for g in want:
        if g in last:
            out[g] = last[g]
    return out


def floor_amounts(packets: Sequence[Mapping[str, Any]]) -> dict[int, int]:
    """PURE: floor id -> the amount that fell (ZC_ITEM_FALL_ENTRY's amount; a monster drop is 1)."""
    return {int(e["floor_id"]): max(1, int(e.get("amount") or 1)) for e in packets
            if e.get("type") == "floor_item_appear" and e.get("kind") == "fall"}  # fmt: skip


def uses(packets: Sequence[Mapping[str, Any]], t0: int, w1: int, aid: int = AID
         ) -> list[tuple[int, int]]:  # fmt: skip
    """PURE: [(t, item id)] of OUR successful item uses in [t0, w1]."""
    return [(int(e["t_mono_ns"]), int(e.get("item_id") or -1)) for e in packets
            if e.get("type") == "use_item_result" and int(e.get("aid") or -1) == aid
            and e.get("ok", True) and t0 <= int(e["t_mono_ns"]) <= w1]  # fmt: skip


def consumable_kind(item: Mapping[str, Any] | None, iid: int) -> str:
    if iid == FLY:
        return "fly_wing"
    if iid == BUTTERFLY:
        return "butterfly_wing"
    if item is not None and str(item.get("type", "")).lower() in POTION_TYPES:
        return "potion"
    return "other"


def windows(t0: int, w1: int, events: Iterable[tuple[int, float]], win_s: float = WIN_S
            ) -> list[float]:  # fmt: skip
    """PURE: the zeny per hour of each FULL ``win_s`` window from t0 (booked (t, zeny) events)."""
    n = int((w1 - t0) / (win_s * NS))
    acc = [0.0] * n
    for t, z in events:
        k = int((t - t0) // int(win_s * NS))
        if 0 <= k < n:
            acc[k] += z
    return [a * 3600.0 / win_s for a in acc]


def sharpe(vals: Sequence[float]) -> tuple[float | None, float | None, float | None, str | None]:
    """PURE: (mean, sample sd, mean / sd, why None)."""
    if len(vals) < 2:
        return (vals[0] if vals else None), None, None, "fewer than 2 full 10-min windows"
    m = sum(vals) / len(vals)
    sd = math.sqrt(sum((v - m) ** 2 for v in vals) / (len(vals) - 1))
    return m, sd, (m / sd if sd > 0 else None), (None if sd > 0 else "zero spread")


def split_carry(seq: Sequence[int], order: Sequence[int],
                amounts: Sequence[int] | None = None) -> int:  # fmt: skip
    """PURE: how many of a kill's dropped item ids (``seq``, in the server's creation order =
    floor id order) can be its OWN drops: the longest prefix that is a subsequence of its
    mob_db drop list (``order``) and drops ONE unit each (``amounts``). A monster's own drops are
    created first, in drop-list order, one per entry at most, one unit each (mob_setdropitem(entry,
    1, ...), mob.cpp:3343), and the items a LOOTER carried after them (mob.cpp:2556-2571,
    mob_delay_item_drop: regular list, then the looted list) -- a looter takes a whole stack, so
    an amount > 1 is carried. The rest is CARRY: a lower bound on the looted items (a carried
    single item that happens to fit the order counts as own)."""
    j = 0
    for k, iid in enumerate(seq):
        if amounts is not None and amounts[k] > 1:
            return k
        while j < len(order) and order[j] != iid:
            j += 1
        if j == len(order):
            return k
        j += 1
    return len(seq)


def measure(packets: Sequence[Mapping[str, Any]], t0: int, w1: int,
            kill_rows: Sequence[Mapping[str, Any]], items: Mapping[int, Mapping[str, Any]],
            table: Mapping[str, Mapping[str, Any]], aid: int = AID,
            capacity: tuple[int | None, int | None] | None = None,
            drop_order: Mapping[str, Sequence[int]] | None = None) -> dict[str, Any]:  # fmt: skip
    """PURE: the economic row of one window. ``kill_rows``: loot_complete.kill_rows (our kills in
    the window, their drops' floor ids, re-drop links); ``items``: arm_judge.item_fates;
    ``table``: econ_items' items (id -> prices); ``capacity``: (max_weight, weight0) in game
    units when the packets lack them; ``drop_order``: species -> its mob_db drop list's item ids
    in order (splits each kill's drops into OWN and looter CARRY: split_carry)."""
    why: dict[str, str] = {}
    h = (w1 - t0) / NS / 3600.0
    amt = floor_amounts(packets)

    def it(iid: Any) -> Mapping[str, Any] | None:
        return table.get(str(iid)) if iid is not None else None

    def val(f: int, key: str) -> float:
        i = it(items[f].get("item_id"))
        if i is None:
            return 0.0
        return float(i[key]) * amt.get(f, 1)

    kills = len(kill_rows)
    drops = [f for r in kill_rows for f in r.get("drops", ())]
    redrops = {f for r in kill_rows for f in r.get("redrop_fids", ())}
    picked = [f for f in drops if items[f]["fate"] == "picked"]
    unknown = sorted({str(items[f].get("item_id")) for f in drops
                      if it(items[f].get("item_id")) is None})  # fmt: skip
    if unknown:
        why["unknown_items"] = f"not in the item table, valued 0: {', '.join(unknown[:5])}"
    dv = sum(val(f, "sell") for f in drops)
    dv_oc = sum(val(f, "sell_oc10") for f in drops)
    dw = sum(val(f, "weight") for f in drops)
    pv = sum(val(f, "sell") for f in picked)
    pv_oc = sum(val(f, "sell_oc10") for f in picked)
    pw = sum(val(f, "weight") for f in picked)
    dv_net = dv - sum(val(f, "sell") for f in redrops)
    ours = set(drops)
    other = [f for f, x in items.items() if x["fate"] == "picked" and f not in ours
             and x.get("t_end") is not None and t0 <= int(x["t_end"]) <= w1]  # fmt: skip
    # consumables
    cons: Counter[str] = Counter()
    cost = cost_dc = 0.0
    booked: list[tuple[int, float]] = []
    no_price = set()
    for t, iid in uses(packets, t0, w1, aid):
        i = it(iid)
        cons[consumable_kind(i, iid)] += 1
        if i is None or i.get("npc_buy") is None:
            no_price.add(iid)
            continue
        p = float(i["npc_buy"])
        cost += p
        cost_dc += float(i.get("npc_buy_dc10") or p)
        booked.append((t, -p))
    if no_price:
        why["cost"] = f"no NPC sells item(s) {sorted(no_price)}: left out of the cost"
    for f in picked:
        booked.append((int(items[f]["t_end"] or w1), val(f, "sell")))
    import survive_judge as sj

    deaths = [t for t in sj.deaths_of(packets, aid) if t0 <= t <= w1]
    # species of the kills, and per species: kills, dropped / picked value, dropped weight
    sp = kill_species(packets, [(int(r["t"]), int(r["gid"])) for r in kill_rows])
    mix = Counter(str(sp.get(int(r["gid"]), -1)) for r in kill_rows)
    per: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    own_by_item: dict[str, Counter[str]] = defaultdict(Counter)
    carry_v = carry_n = 0.0
    for r in kill_rows:
        spc = str(sp.get(int(r["gid"]), -1))
        q = per[spc]
        q["kills"] += 1
        fids = sorted(r.get("drops", ()))
        own = len(fids)
        if drop_order is not None and spc in drop_order:
            own = split_carry(
                [int(items[f].get("item_id") or -1) for f in fids],
                drop_order[spc],
                [amt.get(f, 1) for f in fids],
            )
            # each linked re-drop of our own earlier item (loot_complete.link_redrops) is a
            # carried item; the looted list comes last, so the LAST that many are carried
            # (link_redrops may name the own copy of the same item id: count, not position)
            own = min(own, len(fids) - sum(1 for f in fids if f in redrops))
        for k, f in enumerate(fids):
            q["dropped_value"] += val(f, "sell")
            q["dropped_weight"] += val(f, "weight")
            q["dropped_items"] += amt.get(f, 1)
            if k < own:
                q["own_value"] += val(f, "sell")
                q["own_weight"] += val(f, "weight")
                q["own_items"] += amt.get(f, 1)
                own_by_item[spc][str(items[f].get("item_id"))] += amt.get(f, 1)
            else:
                carry_v += val(f, "sell")
                carry_n += amt.get(f, 1)
            if items[f]["fate"] == "picked":
                q["picked_value"] += val(f, "sell")
    if drop_order is None and kill_rows:
        why["carry"] = "no drop lists (map model not built): own / carry not split"
    # capacity
    mw = series_at(packets, "max_weight", t0)
    w0 = series_at(packets, "weight", t0)
    C = mw / 10.0 if mw else (capacity[0] if capacity else None)
    W0 = w0 / 10.0 if w0 is not None else (capacity[1] if capacity else None)
    if not mw:
        why["capacity"] = ("no max_weight packet: the build's value" if capacity
                           else "no max_weight packet and no build value")  # fmt: skip
    K = kills / h if h > 0 else None
    V = pv / kills if kills else None
    Wk = pw / kills if kills else None
    rate_w = K * Wk if K is not None and Wk is not None else None

    def fill(frac: float) -> float | None:
        if C is None or W0 is None or not rate_w:
            return None
        return round(max(0.0, frac * C - W0) / rate_w, 3)

    if not kills:
        why["per_kill"] = "no kills of ours in the window: V, W, L and fill are undefined"
    gross = pv / h if h else None
    cost_h = cost / h if h else None
    wins = windows(t0, w1, booked)
    m_, sd_, sh_, why_s = sharpe(wins)
    if why_s:
        why["sharpe"] = why_s
    top: Counter[str] = Counter()
    for f in picked:
        top[str(items[f].get("item_id"))] += amt.get(f, 1)
    top_v = sorted(((k, n, round(n * float((it(k) or {}).get("sell", 0)), 1))
                    for k, n in top.items()), key=lambda x: -x[2])[:5]  # fmt: skip
    return {
        "window_h": round(h, 4), "kills": kills, "K": None if K is None else round(K, 1),
        "kill_mix": dict(mix),
        "per_species": {k: {kk: round(vv, 1) for kk, vv in v.items()} for k, v in per.items()},
        "own_items_by_species": {k: dict(v) for k, v in own_by_item.items()},
        "dropped_items": sum(amt.get(f, 1) for f in drops),
        "dropped_value": round(dv, 1), "dropped_value_oc": round(dv_oc, 1),
        "dropped_weight": round(dw, 1),
        "picked_items": sum(amt.get(f, 1) for f in picked),
        "picked_value": round(pv, 1), "picked_value_oc": round(pv_oc, 1),
        "picked_weight": round(pw, 1),
        "V": None if V is None else round(V, 2),
        "V_oc": round(pv_oc / kills, 2) if kills else None,
        "V_theor": round(dv / kills, 2) if kills else None,
        "carry_items": None if drop_order is None else int(carry_n),
        "carry_value": None if drop_order is None else round(carry_v, 1),
        "V_carry": round(carry_v / kills, 2) if kills and drop_order is not None else None,
        "L_value": round(pv / dv, 4) if dv else None,
        "L_count": round(len(picked) / len(drops), 4) if drops else None,
        "L_value_net": round(pv / dv_net, 4) if dv_net > 0 else None,
        "W": None if Wk is None else round(Wk, 3),
        "W_theor": round(dw / kills, 3) if kills else None,
        "V_per_W": round(pv / pw, 2) if pw else None,
        "other_pickups": len(other),
        "other_pickups_value": round(sum(val(f, "sell") for f in other), 1),
        "consumables": dict(cons), "cost": round(cost, 1), "cost_dc": round(cost_dc, 1),
        "deaths": len(deaths), "deaths_h": round(len(deaths) / h, 2) if h else None,
        "gross_h": None if gross is None else round(gross, 1),
        "gross_h_oc": round(pv_oc / h, 1) if h else None,
        "cost_h": None if cost_h is None else round(cost_h, 1),
        "net_h": None if gross is None else round(gross - (cost_h or 0.0), 1),
        "net_h_best": round((pv_oc - cost_dc) / h, 1) if h else None,
        "cost_ratio": round(cost / pv, 4) if pv else None,
        "windows_10min": len(wins), "win_z_h": [round(w, 1) for w in wins],
        "win_mean_h": None if m_ is None else round(m_, 1),
        "win_sd_h": None if sd_ is None else round(sd_, 1),
        "sharpe_10min": None if sh_ is None else round(sh_, 2),
        "max_weight": C, "weight0": W0, "weight_h": None if rate_w is None else round(rate_w, 1),
        "fill_h_50": fill(0.5), "fill_h_90": fill(0.9),
        "top_items": top_v, "why": why,
    }  # fmt: skip


def pool(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """PURE: several runs' rows pooled: sums of kills, values, weights, costs, deaths and hours,
    the ratios re-taken from the sums; the 10-min windows pooled (all runs' windows together)."""
    s: dict[str, float] = defaultdict(float)
    for r in rows:
        for key in ("window_h", "kills", "dropped_value", "dropped_value_oc", "dropped_weight",
                    "picked_value", "picked_value_oc", "picked_weight", "cost", "cost_dc",
                    "deaths", "dropped_items", "picked_items", "carry_value",
                    "carry_items"):  # fmt: skip
            s[key] += float(r.get(key) or 0)
    h, k = s["window_h"], s["kills"]
    wins = [w for r in rows for w in (r.get("win_z_h") or [])]
    m_, sd_, sh_, _w = sharpe(wins)
    return {
        "runs": len(rows), "window_h": round(h, 3), "kills": int(k),
        "K": round(k / h, 1) if h else None,
        "V": round(s["picked_value"] / k, 2) if k else None,
        "V_oc": round(s["picked_value_oc"] / k, 2) if k else None,
        "V_theor": round(s["dropped_value"] / k, 2) if k else None,
        "V_carry": round(s["carry_value"] / k, 2) if k else None,
        "carry_items": int(s["carry_items"]),
        "L_value": round(s["picked_value"] / s["dropped_value"], 4) if s["dropped_value"] else None,
        "L_count": round(s["picked_items"] / s["dropped_items"], 4) if s["dropped_items"] else None,
        "W": round(s["picked_weight"] / k, 3) if k else None,
        "V_per_W": round(s["picked_value"] / s["picked_weight"], 2) if s["picked_weight"] else None,
        "gross_h": round(s["picked_value"] / h, 1) if h else None,
        "cost_h": round(s["cost"] / h, 1) if h else None,
        "net_h": round((s["picked_value"] - s["cost"]) / h, 1) if h else None,
        "net_h_best": round((s["picked_value_oc"] - s["cost_dc"]) / h, 1) if h else None,
        "cost_ratio": round(s["cost"] / s["picked_value"], 4) if s["picked_value"] else None,
        "deaths_h": round(s["deaths"] / h, 2) if h else None,
        "windows_10min": len(wins), "win_mean_h": None if m_ is None else round(m_, 1),
        "win_sd_h": None if sd_ is None else round(sd_, 1),
        "sharpe_10min": None if sh_ is None else round(sh_, 2),
    }  # fmt: skip


def vs_model(r: Mapping[str, Any], mdoc: Mapping[str, Any] | None, T_s: float | None = None
             ) -> dict[str, Any]:  # fmt: skip
    """PURE: the map model at this run's measured kill mix, K, L and capacity, beside the
    measurement; error = (measured - model) / model. V_theor / W_theor are compared on the kills
    of species the model has (a species it lacks is counted in ``unmodelled_kills``), and per
    species (with the dropped items per kill: the drop rates' own check)."""
    if mdoc is None:
        return {"why": "the map is not in data/econ/maps.json (econ_model.py build MAP)"}
    import econ_model as em

    mix = {k: v for k, v in (r.get("kill_mix") or {}).items() if k in mdoc["species"]}
    if not mix:
        return {"why": "no kill of a species the map model has"}
    dropped = em.mix_stats(mdoc["species"], mix, 1.0)
    per = r.get("per_species") or {}
    nk = sum(float(per[k]["kills"]) for k in mix if k in per)
    vk = "own_value" if all("own_value" in per[k] for k in mix if k in per) else "dropped_value"
    wk = "own_weight" if vk == "own_value" else "dropped_weight"
    ik = "own_items" if vk == "own_value" else "dropped_items"
    meas_v = sum(float(per[k].get(vk, 0)) for k in mix if k in per) / nk if nk else None
    meas_w = sum(float(per[k].get(wk, 0)) for k in mix if k in per) / nk if nk else None
    obi = r.get("own_items_by_species") or {}
    core_meas = core_mod = 0.0
    for k in mix:
        if k not in per:
            continue
        n = float(per[k]["kills"])
        core = {str(d["item_id"]): float(d["sell"]) for d in mdoc["species"][k]["drops"]
                if d.get("item_id") is not None and not d.get("rare")
                and int(d.get("base") or 0) >= em.CORE_RATE}  # fmt: skip
        core_meas += sum(float(c) * core[i] for i, c in (obi.get(k) or {}).items() if i in core)
        core_mod += n * em.kill_stats(mdoc["species"][k]["drops"])["ev_core"]
    species = {}
    for k in mix:
        if k not in per:
            continue
        ks = em.kill_stats(mdoc["species"][k]["drops"])
        n = float(per[k]["kills"])
        species[k] = {"name": mdoc["species"][k].get("name"), "kills": int(n),
                      "V_theor": round(float(per[k].get(vk, 0)) / n, 2),
                      "V_model": round(ks["ev"], 2),
                      "items_per_kill": round(float(per[k].get(ik, 0)) / n, 3),
                      "items_per_kill_model": round(sum(float(d["p"]) for d in
                                                        mdoc["species"][k]["drops"]
                                                        if not d.get("rare")), 3),
                      "W_theor": round(float(per[k].get(wk, 0)) / n, 3),
                      "W_model": round(ks["ew"], 3)}  # fmt: skip
    spawn = em.mix_stats(mdoc["species"], {k: float(v) for k, v in mdoc["mix"].items()}, 1.0)
    L = float(r.get("L_value") or 0.0)
    C = r.get("max_weight")
    room = None if C is None or r.get("weight0") is None else 0.5 * C - float(r["weight0"])
    m = em.map_model(mdoc, K=r.get("K"), L=L, C=room, T_s=T_s, mix=mix)

    def err(meas: Any, mod: float) -> float | None:
        return None if meas is None or not mod else round((float(meas) - mod) / mod, 4)

    out = {
        "V_theor_model": round(dropped["ev"], 2), "V_core_model": round(dropped["ev_core"], 2),
        "V_theor_model_spawn_mix": round(spawn["ev"], 2),
        "compared": "own drops (looter carry split off)" if vk == "own_value"
        else "all drops",
        "V_theor_meas": None if meas_v is None else round(meas_v, 2),
        "V_core_meas": round(core_meas / nk, 2) if nk else None,
        "V_core_err": err(core_meas / nk if nk else None, core_mod / nk if nk else 0),
        "V_theor_err": err(meas_v, dropped["ev"]),
        "W_theor_model": round(dropped["ew"], 3), "W_theor_meas": None if meas_w is None
        else round(meas_w, 3), "W_theor_err": err(meas_w, dropped["ew"]),
        "gross_h_model": m.get("G_h"), "gross_h_err": err(r.get("gross_h"), m.get("G_h") or 0),
        "fill_h_50_model": m.get("fill_h"), "T_s": m.get("T_s"), "T_via": m.get("T_via"),
        "u": m.get("u"), "net_h_model_incl_trips": m.get("net_h"),
        "sharpe_10min_model": m.get("sharpe_10min"),
        "unmodelled_kills": sum(v for k, v in (r.get("kill_mix") or {}).items() if k not in mix),
        "species": species,
    }  # fmt: skip
    return out


# --- loading (not pure) --------------------------------------------------------------------------


def _packets(sid: str) -> list[dict[str, Any]]:
    with gzip.open(DEMO / sid / "packets.jsonl.gz", "rt") as fh:
        return sorted((json.loads(x) for x in fh), key=lambda e: int(e["t_mono_ns"]))


@functools.cache
def _table() -> Mapping[str, Mapping[str, Any]]:
    """The item table (econ_items.py build), read once per process."""
    import econ_items

    return econ_items.load()["items"]  # type: ignore[no-any-return]


@functools.cache
def _maps() -> Mapping[str, Any]:
    """The map models (econ_model.py build), read once per process; {} when not built."""
    import econ_model

    try:
        return econ_model.load()["maps"]  # type: ignore[no-any-return]
    except FileNotFoundError:
        return {}


def row(sid: str, sess: Any = None, table: Mapping[str, Any] | None = None,
        maps: Mapping[str, Any] | None = None,
        rows_items: Any = None) -> dict[str, Any]:  # fmt: skip
    """A hunt run's or a human demo's economic row (+ the map model beside it). ``sess`` /
    ``rows_items``: search_study.load_session and loot_complete.session_rows_items when the
    caller has them (run_row)."""
    import loot_complete as lc
    import search_study as ss

    if sess is None:
        sess = ss.load_session(sid)
    rows, items = rows_items if rows_items is not None else lc.session_rows_items(sid, sess)
    tbl = _table() if table is None else table
    mp = _maps() if maps is None else maps
    md = mp.get(sess.map_name)
    order = None if md is None else {k: [int(d["item_id"]) for d in v["drops"]
                                         if d.get("item_id") is not None]
                                     for k, v in md["species"].items()}  # fmt: skip
    out = measure(sess.events, sess.t0, sess.w1, rows, items, tbl, drop_order=order)
    out["session"], out["map"] = sid, sess.map_name
    out["model"] = vs_model(out, md)
    return out


def trial_row(sid: str, table: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """A Crusader survival trial (survive.py): the manifest's t0_ns..t1_ns. The Crusader stands
    and does not attack: K = 0, so the row is the COSTS (potions, Fly Wings) and deaths only."""
    man = json.loads((DEMO / sid / "manifest.json").read_text())
    pk = _packets(sid)
    t0, w1 = int(man["t0_ns"]), int(man["t1_ns"])
    tbl = _table() if table is None else table
    out = measure(pk, t0, w1, [], {}, tbl, capacity=(4150, None))
    out["session"], out["map"] = sid, "prt_fild08 (summoned orcsdun01 species)"
    out["model"] = {"why": "no kills: a stand-and-survive trial, not farming"}
    return out


def any_row(sid: str, **kw: Any) -> dict[str, Any]:
    return trial_row(sid) if "crusader-survival" in sid else row(sid, **kw)


# --- the report block (run_row's "economics" block) ----------------------------------------------

BLOCK = (
    ("K kills / h", "K"), ("V picked z / kill (OC)", "V"), ("V_theor dropped z / kill", "V_theor"),
    ("looter carry z / kill (items)", "carry"),
    ("L by value (count) [net]", "L"), ("W picked weight / kill", "W"),
    ("V / W z per weight", "V_per_W"),
    ("gross z / h (OC)", "gross"), ("consumables (cost / h)", "cons"), ("net z / h (best)", "net"),
    ("cost ratio", "cost_ratio"), ("deaths / h", "deaths_h"),
    ("10-min z / h mean +- sd (n)", "win"), ("Sharpe-like (10 min)", "sharpe_10min"),
    ("fill h to 50 % / 90 % (C, w0)", "fill"),
    ("MODEL V own drops / kill (err)", "m_v"), ("MODEL V core >= 1 % (err)", "m_c"),
    ("MODEL W own drops / kill (err)", "m_w"),
    ("MODEL gross z / h (err)", "m_g"), ("MODEL trip T s (via) -> u", "m_t"),
    ("MODEL net z / h incl. trips", "m_n"), ("MODEL Sharpe-like", "m_s"),
)  # fmt: skip


def cells(r: Mapping[str, Any]) -> dict[str, str]:
    """PURE: the economic row as the report's text cells (BLOCK order)."""

    def f(v: Any, nd: int = 1) -> str:
        return "-" if v is None else (f"{v:.{nd}f}" if isinstance(v, float) else str(v))

    def pct(v: Any) -> str:
        return "-" if v is None else f"{100 * float(v):.1f} %"

    m = r.get("model") or {}
    cons = r.get("consumables") or {}
    c_txt = ", ".join(f"{k} {v}" for k, v in sorted(cons.items())) or "none"
    out = {
        "K": f(r.get("K")),
        "V": f"{f(r.get('V'), 2)} ({f(r.get('V_oc'), 2)})",
        "V_theor": f(r.get("V_theor"), 2),
        "carry": f"{f(r.get('V_carry'), 2)} ({f(r.get('carry_items'))})",
        "L": f"{pct(r.get('L_value'))} ({pct(r.get('L_count'))}) [{pct(r.get('L_value_net'))}]",
        "W": f(r.get("W"), 3), "V_per_W": f(r.get("V_per_W"), 2),
        "gross": f"{f(r.get('gross_h'))} ({f(r.get('gross_h_oc'))})",
        "cons": f"{c_txt} ({f(r.get('cost_h'))} / h)",
        "net": f"{f(r.get('net_h'))} ({f(r.get('net_h_best'))})",
        "cost_ratio": pct(r.get("cost_ratio")), "deaths_h": f(r.get("deaths_h"), 2),
        "win": f"{f(r.get('win_mean_h'))} +- {f(r.get('win_sd_h'))} ({r.get('windows_10min')})",
        "sharpe_10min": f(r.get("sharpe_10min"), 2),
        "fill": f"{f(r.get('fill_h_50'), 2)} / {f(r.get('fill_h_90'), 2)} "
                f"({f(r.get('max_weight'))}, {f(r.get('weight0'))})",
        "m_v": f"{f(m.get('V_theor_model'), 2)} ({pct(m.get('V_theor_err'))})",
        "m_w": f"{f(m.get('W_theor_model'), 3)} ({pct(m.get('W_theor_err'))})",
        "m_c": f"{f(m.get('V_core_model'), 2)} ({pct(m.get('V_core_err'))})",
        "m_g": f"{f(m.get('gross_h_model'))} ({pct(m.get('gross_h_err'))})",
        "m_t": f"{f(m.get('T_s'))} ({m.get('T_via') or '-'}) -> {f(m.get('u'), 4)}",
        "m_n": f(m.get("net_h_model_incl_trips")), "m_s": f(m.get("sharpe_10min_model"), 2),
    }  # fmt: skip
    if m.get("why"):
        for k in ("m_v", "m_c", "m_w", "m_g", "m_t", "m_n", "m_s"):
            out[k] = "-"
    return out


def box(cols: Sequence[tuple[str, Mapping[str, Any]]]) -> str:
    """PURE: the economics block as a box-drawing table, one column per run."""
    names = [n for n, _k in BLOCK]
    cc = [(h, cells(r)) for h, r in cols]
    w0 = max(len(n) for n in [*names, "ECONOMICS (fixed NPC prices)"])
    ws = [max(len(h), *(len(c[k]) for _n, k in BLOCK)) for h, c in cc]

    def line(a: str, b: str, c: str) -> str:
        return a + b.join("─" * (w + 2) for w in [w0, *ws]) + c

    out = [line("┌", "┬", "┐"),
           "│ " + " │ ".join(["ECONOMICS (fixed NPC prices)".ljust(w0)]
                            + [h.center(w) for (h, _c), w in zip(cc, ws, strict=True)]) + " │",
           line("├", "┼", "┤")]  # fmt: skip
    for n, k in BLOCK:
        vals = [c[k].ljust(w) for (_h, c), w in zip(cc, ws, strict=True)]
        out.append("│ " + " │ ".join([n.ljust(w0), *vals]) + " │")
    out.append(line("└", "┴", "┘"))
    return "\n".join(out)


def banked(map_name: str | None = None, trials: bool = False) -> list[str]:
    """The banked sessions a back-fill reads: hunt runs (a flow_judge.json beside their packets)
    on ``map_name``, or the Crusader survival trials (packets + manifest)."""
    out = []
    for d in sorted(DEMO.iterdir()):
        if not (d / "packets.jsonl.gz").exists():
            continue
        if trials:
            if "crusader-survival" in d.name and (d / "manifest.json").exists():
                out.append(d.name)
            continue
        if "hunt-flow" not in d.name or not (d / "flow_judge.json").exists():
            continue
        try:
            m = json.loads((d / "manifest.json").read_text()).get("map")
        except (OSError, ValueError):
            continue
        if map_name is None or m == map_name:
            out.append(d.name)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)  # fmt: skip
    ap.add_argument("sessions", nargs="*")
    ap.add_argument("--banked", metavar="MAP", help="every banked hunt run on MAP (back-fill)")
    ap.add_argument("--trials", action="store_true", help="every banked survival trial")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--pool", action="store_true")
    a = ap.parse_args()
    sids = (
        list(a.sessions)
        + (banked(a.banked) if a.banked else [])
        + (banked(trials=True) if a.trials else [])
    )
    if not sids:
        ap.error("no sessions")
    table, maps = _table(), _maps()
    rows = []
    for s in sids:
        try:
            rows.append(trial_row(s, table) if "crusader-survival" in s
                        else row(s, table=table, maps=maps))  # fmt: skip
        except (SystemExit, KeyError, ValueError, OSError) as e:  # a back-fill reports, not dies
            print(f"{s}: skipped ({type(e).__name__}: {e})", file=sys.stderr)
    if a.json:
        out: list[Any] = list(rows)
        if a.pool:
            out.append(pool(rows))
        print(json.dumps(out, indent=1, default=str))
        return 0
    print(box([(str(r["session"])[:15].replace("2026", ""), r) for r in rows]))
    if a.pool:
        print(json.dumps(pool(rows), indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
