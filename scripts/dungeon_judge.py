#!/usr/bin/env python3
"""THE DUNGEON JUDGE (2026-10-22): one Crusader run on Orc Dungeon F1 (orcsdun01, immunity OFF)
judged OFFLINE from its packets (the server's truth, ADR-0007) and the runner's events, and the
runs POOLED per sustain strategy (A = POTIONS, B = REST, C = HEAL). Nothing here reaches a runner:
no runner imports this module, and it reads only banked session files.

    dungeon_judge.py row SID [--items PATH] [--map orcsdun01]
    dungeon_judge.py table SID [SID ...] [--json] [--items PATH]
    dungeon_judge.py positive [--items PATH]     the positive cases on REAL banked sessions

A session is read from /dev/shm/poring-lab-demo/<sid>/ while fresh, else from the NAS
(/mnt/poring-lab-datasets/<sid>/): events.jsonl, packets.jsonl.gz, manifest.json.

THE WINDOW: run_start -> run_end (events, t_ns = CLOCK_MONOTONIC, the packets' clock). Without
them: the manifest's t0_ns..t1_ns (a survival trial), else its t0_mono_ns..t1_mono_ns (a hunt
run); the row says which ("window.source").

PER RUN -- from PACKETS (ours = the GM account's block id 2000002, the Crusader's too):
- kills / h: arm_judge.kills_of (a monster's death vanish <= 1.5 s after OUR damaging act);
- deaths / h: our own id's vanish with reason "died" (survive_judge.deaths_of; the hp packet at a
  death can read 1, so hp 0 is not the cue -- hp_zero_packets is reported beside it);
- HP min: the absolute hp packets in the window (and the value in force at its start), and its
  share of MaxHP (the max_hp packet in force, else 5,260);
- potions / Fly Wings and per hour: OUR use_item_result successes of 504 / 601 (aid filter);
- Heals cast and per hour: NO skill-use packet is decoded (poring_packets has skill_list /
  skill_update only), so a Heal = our SP falling by EXACTLY 34 (AL_HEAL Lv 8); "confirmed" = an
  HP rise of 544 (+-1), or one that ends exactly at MaxHP, within 1 s of it (an absolute hp
  packet, or a decoded `recovery` amount);
- SP used (the sum of SP falls) and SP min; Auto Guard casts = SP falls of exactly 30 (a toggle:
  on or off, survive_judge's rule), Endure = 10. When no SP packet precedes the window, the SP at
  its start is ASSUMED MaxSP 312 (said in "why");
- loot completeness: the hunt's definition (loot_complete: items PICKED / items DROPPED by ALL our
  kills, and net of a looter's re-drop of our own item), with the fates;
- gross / net zeny per hour, costs, cost ratio, Sharpe-like: econ_row.measure on the same kill
  rows (NPC sell prices for the picked drops; OUR consumables at the cheapest NPC's price: White
  Potion 1,200 z, Fly Wing 60 z; a Heal costs no zeny; 10-min windows of booked net zeny);
- Moving HP Recovery: our walk spans (regen_walk.walk_spans: self_move paths) and the regen ticks
  (regen_walk.ticks: natural +33 steps of the hp series, IRP = `recovery` amounts): natural ticks
  WHILE walking (MHR's evidence) and the walking minutes; IRP ticks while walking (must be 0);
- sitting % (our act kind sit -> stand), the cross-check of the resting spans;
- HARD BARS: map changes to ANOTHER map (a Fly Wing is a same-map teleport: counted apart, and
  set beside the Fly Wings used), npc_contact, our attack requests on a non-monster (its latest
  entity_appear's objtype != 5; a target never seen is "unknown", reported, not a bar).
From the runner's EVENTS: engagements by trigger (battle_log / hp_drop / box); strikes and their
landing (a strike followed within 1.5 s by an attack_request of ours AND our act on a monster);
the resting spans (rest_start -> rest_end, an open one closed at the window's end) and resting %;
escapes; presses; the runner's own kill and death counts; the run's end reason.
Missing data is None with the reason in "why" -- never invented.

POOLED (per strategy): counts and seconds summed, every rate re-taken from the sums; HP / SP min
the minimum; the economics pooled by econ_row.pool (all runs' 10-min windows together).
"""

from __future__ import annotations

import argparse
import bisect
import gzip
import json
import sys
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

DEMO = Path("/dev/shm/poring-lab-demo")
NAS = Path("/mnt/poring-lab-datasets")
NS = 1_000_000_000
AID = 2000002  # our block id: the GM account; the Crusader is a character on it (crusader.py)
MAX_HP, MAX_SP = 5260, 312  # the Crusader's verified MaxHP / MaxSP (crusader-orcsdun01.md 2b)
POTION, FLY = 504, 601
HEAL_SP, HEAL_HP = 34, 544  # AL_HEAL Lv 8: 13 + 3 x 7 SP; (60 + 7) / 8 x (4 + 8 x 8) HP
AG_SP, ENDURE_SP = 30, 10
HEAL_WIN_S = 1.0
LAND_S = 1.5
MOB = 5  # entity_appear objtype of a monster
NOT_A_HIT = ("pickup", "sit", "stand")
MAP = "orcsdun01"


# --- pure helpers --------------------------------------------------------------------------------


def _t(e: Mapping[str, Any]) -> int:
    return int(e["t_mono_ns"])


def window(events: Sequence[Mapping[str, Any]], manifest: Mapping[str, Any] | None,
           packets: Sequence[Mapping[str, Any]] = ()) -> tuple[int, int, str]:  # fmt: skip
    """PURE: the judged window (t0, t1, source): run_start -> run_end; else the manifest's
    t0_ns..t1_ns (a survival trial) or t0_mono_ns..t1_mono_ns (a hunt run); else the packets'."""
    man = manifest or {}
    rs = next((e for e in events if e.get("kind") == "run_start"), None)
    re_ = next((e for e in reversed(events) if e.get("kind") == "run_end"), None)
    if rs is not None:
        t0 = int(rs["t_ns"])
        if re_ is not None:
            return t0, int(re_["t_ns"]), "events run_start..run_end"
        t1 = int(man.get("t1_ns") or man.get("t1_mono_ns") or events[-1]["t_ns"])
        return t0, t1, "events run_start..(no run_end: manifest t1 or the last event)"
    for a, b in (("t0_ns", "t1_ns"), ("t0_mono_ns", "t1_mono_ns")):
        if man.get(a) and man.get(b):
            return int(man[a]), int(man[b]), f"manifest {a}..{b}"
    if packets:
        return _t(packets[0]), _t(packets[-1]), "packets first..last"
    raise ValueError("no window: no run_start, no manifest times, no packets")


def series(packets: Sequence[Mapping[str, Any]], name: str) -> list[tuple[int, int]]:
    """PURE: [(t, value)] of our stat_change ``name`` in time order."""
    return sorted((_t(e), int(e.get("value") or 0)) for e in packets
                  if e.get("type") == "stat_change" and e.get("name") == name)  # fmt: skip


def in_force(ser: Sequence[tuple[int, int]], t: int) -> int | None:
    """PURE: the series' value at ``t`` (the last change at or before it), or None."""
    i = bisect.bisect_right([x[0] for x in ser], t)
    return ser[i - 1][1] if i else None


def clip(ser: Sequence[tuple[int, int]], t0: int, t1: int,
         start: int | None = None) -> list[tuple[int, int]]:  # fmt: skip
    """PURE: the series inside (t0, t1], led by its value in force at t0 (``start`` when none)."""
    v0 = in_force(ser, t0)
    if v0 is None:
        v0 = start
    head = [(t0, v0)] if v0 is not None else []
    return head + [(t, v) for t, v in ser if t0 < t <= t1]


def falls(ser: Sequence[tuple[int, int]], cost: int | None = None) -> list[tuple[int, int]]:
    """PURE: [(t, drop)] of the series' falls (all of them, or exactly ``cost``)."""
    return [(t, v0 - v) for (_t0, v0), (t, v) in zip(ser, ser[1:], strict=False)
            if v < v0 and (cost is None or v0 - v == cost)]  # fmt: skip


def overlap(spans: Iterable[tuple[int, int]], t0: int, t1: int) -> int:
    """PURE: the ns of ``spans`` inside [t0, t1]."""
    return sum(max(0, min(b, t1) - max(a, t0)) for a, b in spans)


def overlap2(a: Sequence[tuple[int, int]], b: Sequence[tuple[int, int]]) -> int:
    """PURE: the ns two span lists share (each list non-overlapping in itself)."""
    return sum(overlap(b, x0, x1) for x0, x1 in a)


def heal_casts(packets: Sequence[Mapping[str, Any]], t0: int, t1: int, sp_start: int | None,
               max_hp: int = MAX_HP, heal_hp: int = HEAL_HP, heal_sp: int = HEAL_SP,
               win_s: float = HEAL_WIN_S) -> dict[str, Any]:  # fmt: skip
    """PURE: our Heals. There is NO decoded skill-use packet, so a cast = our SP falling by
    exactly ``heal_sp``; it is CONFIRMED by an HP rise of ``heal_hp`` (+-1), or one ending exactly
    at MaxHP (a capped heal), within ``win_s`` of the fall -- on the HP series with the decoded
    `recovery` amounts added (survive_judge.hp_with_recovery), so a heal sent either way counts."""
    import survive_judge as sj

    sp = clip(series(packets, "sp"), t0, t1, sp_start)
    casts = [t for t, _d in falls(sp, heal_sp)]
    hp = sj.hp_with_recovery(packets, max_hp)
    rises = [(t, v - v0, v) for (_a, v0), (t, v) in zip(hp, hp[1:], strict=False) if v > v0]
    ok = []
    for tc in casts:
        ok.append(any(abs(t - tc) <= win_s * NS
                      and (abs(r - heal_hp) <= 1 or (v >= max_hp and 0 < r < heal_hp))
                      for t, r, v in rises))  # fmt: skip
    return {"casts": len(casts), "confirmed": sum(ok),
            "times_s": [round((t - t0) / NS, 2) for t in casts],
            "via": f"sp fall of exactly {heal_sp} (no skill-use packet is decoded); confirmed = "
            f"hp rise {heal_hp} +-1 or capped at MaxHP within {win_s} s"}  # fmt: skip


def objtypes(packets: Sequence[Mapping[str, Any]]) -> list[tuple[int, int, int]]:
    """PURE: [(t, gid, objtype)] of every entity_appear, in time order."""
    return [(_t(e), int(e["gid"]), int(e.get("objtype", -1))) for e in packets
            if e.get("type") == "entity_appear" and e.get("gid") is not None]  # fmt: skip


def objtype_at(appears: Sequence[tuple[int, int, int]], gid: int, t: int) -> int | None:
    """PURE: the objtype of ``gid``'s latest appear at or before ``t`` (ids are reused)."""
    out = None
    for ta, g, o in appears:
        if ta > t:
            break
        if g == gid:
            out = o
    return out


def sit_spans(packets: Sequence[Mapping[str, Any]], t1: int, aid: int = AID
              ) -> list[tuple[int, int]]:  # fmt: skip
    """PURE: [(t_sit, t_stand)] of OUR act kind sit -> stand (an open sit closes at ``t1``)."""
    out: list[tuple[int, int]] = []
    start: int | None = None
    for e in packets:
        if e.get("type") != "act" or int(e.get("src_gid") or -1) != aid:
            continue
        if e.get("kind") == "sit" and start is None:
            start = _t(e)
        elif e.get("kind") == "stand" and start is not None:
            out.append((start, _t(e)))
            start = None
    if start is not None:
        out.append((start, max(start, t1)))
    return out


def rest_spans(events: Sequence[Mapping[str, Any]], t0: int, t1: int
               ) -> tuple[list[tuple[int, int]], Counter[str]]:  # fmt: skip
    """PURE: [(t_start, t_end)] of the runner's rest_start -> rest_end inside the window (an open
    one closes at t1), and the rest_end reasons."""
    out: list[tuple[int, int]] = []
    why: Counter[str] = Counter()
    start: int | None = None
    for e in events:
        k = e.get("kind")
        t = int(e.get("t_ns") or 0)
        if k == "rest_start" and start is None:
            start = t
        elif k == "rest_end" and start is not None:
            out.append((max(start, t0), min(t, t1)))
            why[str(e.get("why"))] += 1
            start = None
    if start is not None:
        out.append((max(start, t0), t1))
        why["open at the window's end"] += 1
    return [(a, b) for a, b in out if b > a], why


def strikes(events: Sequence[Mapping[str, Any]], packets: Sequence[Mapping[str, Any]],
            t0: int, t1: int, aid: int = AID,
            land_s: float = LAND_S) -> dict[str, Any]:  # fmt: skip
    """PURE: the runner's strikes in the window and their LANDING: within ``land_s`` after the
    strike event, an attack_request of ours (an attack: action 0 / 7) AND our act on a monster
    (any act but pickup / sit / stand, its target's latest appear a monster). "request_only": the
    client asked, no act followed in time."""
    appears = objtypes(packets)
    reqs = sorted(_t(e) for e in packets if e.get("type") == "attack_request"
                  and (e.get("is_attack") or int(e.get("action", -1)) in (0, 7)))  # fmt: skip
    acts = sorted(_t(e) for e in packets if e.get("type") == "act"
                  and int(e.get("src_gid") or -1) == aid and e.get("kind") not in NOT_A_HIT
                  and objtype_at(appears, int(e.get("target_gid") or -1),
                                 _t(e)) == MOB)  # fmt: skip
    st = [e for e in events if e.get("kind") == "strike" and t0 <= int(e["t_ns"]) <= t1]
    landed = req_only = 0
    lim = int(land_s * NS)
    for e in st:
        t = int(e["t_ns"])
        i = bisect.bisect_left(reqs, t)
        has_req = i < len(reqs) and reqs[i] <= t + lim
        j = bisect.bisect_left(acts, t)
        has_act = j < len(acts) and acts[j] <= t + lim
        landed += has_req and has_act
        req_only += has_req and not has_act
    return {"n": len(st), "landed": landed, "request_only": req_only,
            "landed_rate": round(landed / len(st), 4) if st else None,
            "ends": dict(Counter(str(e.get("end")) for e in st))}  # fmt: skip


def hard_bars(packets: Sequence[Mapping[str, Any]], t0: int, t1: int, map_name: str,
              aid: int = AID) -> dict[str, Any]:  # fmt: skip
    """PURE: map changes to ANOTHER map (the bar) vs same-map teleports (a Fly Wing), NPC
    contacts, and our attack requests on a non-monster / an unknown target, in [t0, t1]."""
    appears = objtypes(packets)
    other: list[str] = []
    same = same_gm = npc = non_mob = unknown = 0
    want = map_name.removesuffix(".gat")
    for e in packets:
        t = _t(e)
        if not t0 <= t <= t1:
            continue
        typ = e.get("type")
        if typ == "map_change":
            m = str(e.get("map") or "").removesuffix(".gat")
            if m != want:
                other.append(m)
            else:
                same += 1
                same_gm += bool(e.get("gm_command"))
        elif typ == "npc_contact":
            npc += 1
        elif typ == "attack_request" and (e.get("is_attack")
                                          or int(e.get("action", -1)) in (0, 7)):  # fmt: skip
            o = objtype_at(appears, int(e.get("target_gid") or -1), t)
            if o is None:
                unknown += 1
            elif o != MOB:
                non_mob += 1
    return {"map_changes_other": len(other), "other_maps": sorted(set(other)),
            "map_changes_same_map": same, "same_map_by_gm_command": same_gm,
            "npc_contacts": npc, "attack_requests_non_monster": non_mob,
            "attack_requests_unknown_target": unknown,
            "pass": not other and npc == 0 and non_mob == 0}  # fmt: skip


def moving_hp_recovery(packets: Sequence[Mapping[str, Any]], t0: int, t1: int,
                       rests: Sequence[tuple[int, int]] = ()) -> dict[str, Any]:  # fmt: skip
    """PURE: regen_walk's walk spans and ticks inside the window: natural ticks WHILE walking
    (Moving HP Recovery's evidence: without it natural regen stops while walking) and the walking
    minutes; IRP ticks while walking (must be 0); the regen while resting (``rests``). A
    `recovery` amount above IRP's 155 (a capped tick is smaller) is NOT regen -- e.g. a Heal, if
    one is ever sent as ZC_RECOVERY -- and is counted apart ("recovery_not_regen")."""
    import regen_walk as rw

    spans = rw.walk_spans(packets)
    all_tk = [x for x in rw.ticks(packets) if t0 <= x["t"] <= t1]
    tk = [x for x in all_tk if x["kind"] == "natural" or x["amount"] <= rw.IRP]
    walk_ns = overlap(spans, t0, t1)
    nat = [x for x in tk if x["kind"] == "natural"]
    irp = [x for x in tk if x["kind"] == "irp"]
    rest_ns = sum(b - a for a, b in rests)
    in_rest = [x for x in tk if any(a <= x["t"] < b for a, b in rests)]
    mins = (t1 - t0) / NS / 60
    return {
        "walking_min": round(walk_ns / NS / 60, 3),
        "walking_share": round(walk_ns / max(1, t1 - t0), 4),
        "natural_ticks": len(nat), "natural_while_walking": sum(rw.walking_at(spans, x["t"])
                                                                for x in nat),
        "irp_ticks": len(irp), "irp_while_walking": sum(rw.walking_at(spans, x["t"]) for x in irp),
        "regen_hp_per_min": round(sum(x["amount"] for x in tk) / mins, 1) if mins else None,
        "regen_hp_per_min_resting": round(sum(x["amount"] for x in in_rest) / (rest_ns / NS / 60),
                                          1) if rest_ns else None,
        "recovery_not_regen": len(all_tk) - len(tk),
    }  # fmt: skip


# --- the row -------------------------------------------------------------------------------------


def judge(events: Sequence[Mapping[str, Any]], packets: Sequence[Mapping[str, Any]],
          table: Mapping[str, Mapping[str, Any]] | None, manifest: Mapping[str, Any] | None = None,
          map_name: str | None = None, t0: int | None = None, t1: int | None = None,
          aid: int = AID, drop_order: Mapping[str, Sequence[int]] | None = None,
          ) -> dict[str, Any]:  # fmt: skip
    """PURE: one run's row. ``table``: econ_items' items (None: no economics, said in "why");
    ``t0`` / ``t1``: override the window (the positive cases use the other judges' windows)."""
    import arm_judge as aj
    import econ_row as er
    import flow_judge as fj
    import hunt_core as hc
    import loot_complete as lc
    import survive_judge as sj

    why: dict[str, str] = {}
    man = manifest or {}
    w0, w1, src = window(events, man, packets)
    if t0 is not None and t1 is not None:
        w0, w1, src = t0, t1, "given"
    rs = next((e for e in events if e.get("kind") == "run_start"), {})
    re_ = next((e for e in reversed(events) if e.get("kind") == "run_end"), {})
    mp = map_name or rs.get("map") or man.get("map") or MAP
    h = (w1 - w0) / NS / 3600
    ev = [e for e in events if w0 <= int(e.get("t_ns") or 0) <= w1]

    def per_h(n: float | None) -> float | None:
        return round(n / h, 2) if n is not None and h > 0 else None

    # HP / SP
    mx = in_force(series(packets, "max_hp"), w0) or MAX_HP
    hp = clip(series(packets, "hp"), w0, w1)
    hp_min = min((v for _t, v in hp), default=None)
    sp_raw = series(packets, "sp")
    sp_start = in_force(sp_raw, w0)
    if sp_start is None:
        sp_start = MAX_SP
        why["sp_start"] = f"no sp packet before the window: its start ASSUMED MaxSP {MAX_SP}"
    sp = clip(sp_raw, w0, w1, sp_start)
    sp_falls = falls(sp)
    heals = heal_casts(packets, w0, w1, sp_start, max_hp=mx)
    deaths = [t for t in sj.deaths_of(packets, aid) if w0 <= t <= w1]
    pots = [t for t in sj.items_used(packets, POTION, aid) if w0 <= t <= w1]
    flys = [t for t in sj.items_used(packets, FLY, aid) if w0 <= t <= w1]
    # kills, loot, economics
    kills = aj.kills_of(packets, aid)
    pos = hc.walk_positions(packets)
    items = aj.item_fates(packets, pos, fj.mob_at)
    krows = lc.kill_rows(kills, items, lambda g, t: fj.mob_at(pos, g, t), [], {}, w0, w1)
    ls = lc.summary(krows)
    econ: dict[str, Any]
    if table is None:
        econ = {"why": {"economics": "no item table (econ_items.py build): no zeny columns"}}
        why["economics"] = econ["why"]["economics"]
    else:
        econ = er.measure(packets, w0, w1, krows, items, table, aid, drop_order=drop_order)
    # events: rests, engagements, strikes
    rests, rest_why = rest_spans(events, w0, w1)
    rest_ns = sum(b - a for a, b in rests)
    sits = [(max(a, w0), min(b, w1)) for a, b in sit_spans(packets, w1, aid) if b > w0 and a < w1]
    sit_ns = sum(b - a for a, b in sits)
    presses = Counter(str(e.get("what")) for e in ev if e.get("kind") == "press")
    if not any(e.get("kind") == "run_start" for e in events):
        why["events"] = "no run_start event: not a dungeon runner session (window from manifest)"
    return {
        "session": man.get("sid") or man.get("session_id"),
        "strategy": rs.get("strategy") or man.get("strategy"),
        "seed": rs.get("seed"), "version": rs.get("version"), "map": mp,
        "window": {"t0": w0, "t1": w1, "source": src},
        "minutes": round((w1 - w0) / NS / 60, 3), "hours": round(h, 4),
        # packets
        "kills": len(krows), "kills_h": per_h(len(krows)),
        "deaths": len(deaths), "deaths_h": per_h(len(deaths)),
        "hp_zero_packets": sum(1 for t, v in hp if v == 0 and t > w0),
        "hp_min": hp_min, "max_hp": mx,
        "hp_min_pct": round(hp_min / mx, 4) if hp_min is not None and mx else None,
        "potions": len(pots), "potions_h": per_h(len(pots)),
        "fly_wings": len(flys), "fly_wings_h": per_h(len(flys)),
        "heals": heals["casts"], "heals_confirmed": heals["confirmed"],
        "heals_h": per_h(heals["casts"]), "heal_detail": heals,
        "sp_used": sum(d for _t, d in sp_falls), "sp_used_h": per_h(sum(d for _t, d in sp_falls)),
        "sp_min": min((v for _t, v in sp), default=None), "sp_start": sp_start,
        "autoguard": len(falls(sp, AG_SP)), "autoguard_h": per_h(len(falls(sp, AG_SP))),
        "endure": len(falls(sp, ENDURE_SP)),
        "loot": {"definition": "loot_complete: picked / dropped by ALL our kills (packets); net "
                 "leaves a looter's re-drop of our own item out of the dropped",
                 **{k: ls[k] for k in ("kills", "items", "picked", "out_of_sight", "looter",
                                       "expired", "left", "gone", "redrops", "recovered",
                                       "completeness", "completeness_net")}},  # fmt: skip
        "loot_completeness": ls["completeness"], "loot_completeness_net": ls["completeness_net"],
        "gross_h": econ.get("gross_h"), "cost_h": econ.get("cost_h"), "net_h": econ.get("net_h"),
        "cost": econ.get("cost"), "picked_value": econ.get("picked_value"),
        "cost_ratio": econ.get("cost_ratio"), "sharpe_10min": econ.get("sharpe_10min"),
        "economics": econ,
        "moving_hp_recovery": moving_hp_recovery(packets, w0, w1, rests),
        "sitting_pct": round(sit_ns / max(1, w1 - w0), 4),
        "hard_bars": hard_bars(packets, w0, w1, mp, aid),
        # events
        "resting_pct": round(rest_ns / max(1, w1 - w0), 4),
        "rest": {"spans": len(rests), "seconds": round(rest_ns / NS, 1),
                 "sitting_seconds": round(sit_ns / NS, 1),
                 "sitting_share_of_rest": round(overlap2(rests, sits) / rest_ns, 4)
                 if rest_ns else None, "end_why": dict(rest_why)},  # fmt: skip
        "engagements": dict(Counter(str(e.get("by")) for e in ev if e.get("kind") == "engage")),
        "strikes": strikes(events, packets, w0, w1, aid),
        "escapes": sum(1 for e in ev if e.get("kind") == "escape"),
        "presses": dict(presses),
        "runner_kills": sum(1 for e in ev if e.get("kind") == "kill"),
        "runner_deaths": sum(1 for e in ev if e.get("kind") == "death"),
        "hp_reads": sum(1 for e in ev if e.get("kind") == "hp_read"),
        "end_reason": re_.get("reason") or man.get("reason") or man.get("ended"),
        "end_counts": re_.get("counts"),
        # [the runner's events, the packets]: a gap is a press that did nothing, a kill the
        # runner believed and the server did not see, a death it missed, ...
        "runner_vs_packets": {
            "kills": [sum(1 for e in ev if e.get("kind") == "kill"), len(krows)],
            "potion": [presses.get("potion", 0), len(pots)],
            "fly": [presses.get("fly", 0), len(flys)],
            "escape_events_vs_fly": [sum(1 for e in ev if e.get("kind") == "escape"), len(flys)],
            "heal": [presses.get("heal", 0), heals["casts"]],
            "autoguard": [presses.get("autoguard", 0), len(falls(sp, AG_SP))],
            "endure": [presses.get("endure", 0), len(falls(sp, ENDURE_SP))],
            "sit": [presses.get("sit", 0), len(sits)],
            "deaths": [sum(1 for e in ev if e.get("kind") == "death"), len(deaths)],
        },
        "why": why,
    }  # fmt: skip


# --- pooling and the tables ----------------------------------------------------------------------

_SUMS = ("hours", "kills", "deaths", "potions", "fly_wings", "heals", "heals_confirmed",
         "sp_used", "autoguard", "endure", "escapes", "runner_kills")  # fmt: skip


def pool(rows: Sequence[Mapping[str, Any]], label: str = "pooled") -> dict[str, Any]:
    """PURE: several runs pooled: counts / seconds summed, rates re-taken from the sums, minima
    the minimum, the economics by econ_row.pool (all runs' 10-min windows together)."""
    import econ_row as er

    s: dict[str, float] = defaultdict(float)
    for r in rows:
        for k in _SUMS:
            s[k] += float(r.get(k) or 0)
        s["rest_s"] += float((r.get("rest") or {}).get("seconds") or 0)
        s["sit_s"] += float((r.get("rest") or {}).get("sitting_seconds") or 0)
        for k, v in (r.get("loot") or {}).items():
            if k in ("items", "picked", "redrops", "recovered"):
                s["loot_" + k] += float(v or 0)
        m = r.get("moving_hp_recovery") or {}
        for k in ("walking_min", "natural_while_walking", "irp_while_walking"):
            s[k] += float(m.get(k) or 0)
        hb = r.get("hard_bars") or {}
        for k in ("map_changes_other", "npc_contacts", "attack_requests_non_monster"):
            s[k] += float(hb.get(k) or 0)
        st = r.get("strikes") or {}
        s["strikes"] += float(st.get("n") or 0)
        s["landed"] += float(st.get("landed") or 0)
    h = s["hours"]

    def ph(k: str) -> float | None:
        return round(s[k] / h, 2) if h else None

    def mn(k: str) -> Any:
        v = [r[k] for r in rows if r.get(k) is not None]
        return min(v) if v else None

    ecs = [r["economics"] for r in rows if isinstance(r.get("economics"), dict)
           and "K" in r["economics"]]  # fmt: skip
    econ = er.pool(ecs) if ecs and len(ecs) == len(rows) else {
        "why": "a run without economics (no item table)"}  # fmt: skip
    eng: Counter[str] = Counter()
    ends: Counter[str] = Counter()
    for r in rows:
        eng.update(r.get("engagements") or {})
        ends[str(r.get("end_reason"))] += 1
    items = s["loot_items"]
    return {
        "session": label, "strategy": label, "runs": len(rows), "hours": round(h, 4),
        "minutes": round(h * 60, 2),
        **{k: int(s[k]) for k in _SUMS if k != "hours"},
        "kills_h": ph("kills"), "deaths_h": ph("deaths"), "potions_h": ph("potions"),
        "fly_wings_h": ph("fly_wings"), "heals_h": ph("heals"), "sp_used_h": ph("sp_used"),
        "autoguard_h": ph("autoguard"),
        "hp_min": mn("hp_min"), "hp_min_pct": mn("hp_min_pct"), "sp_min": mn("sp_min"),
        "resting_pct": round(s["rest_s"] / (h * 3600), 4) if h else None,
        "sitting_pct": round(s["sit_s"] / (h * 3600), 4) if h else None,
        "rest": {"seconds": round(s["rest_s"], 1)},
        "loot": {"items": int(items), "picked": int(s["loot_picked"]),
                 "redrops": int(s["loot_redrops"]), "recovered": int(s["loot_recovered"])},
        "loot_completeness": round(s["loot_picked"] / items, 4) if items else None,
        "loot_completeness_net": round(s["loot_picked"] / (items - s["loot_redrops"]), 4)
        if items - s["loot_redrops"] > 0 else None,
        "gross_h": econ.get("gross_h"), "cost_h": econ.get("cost_h"), "net_h": econ.get("net_h"),
        "cost_ratio": econ.get("cost_ratio"), "sharpe_10min": econ.get("sharpe_10min"),
        "economics": econ,
        "moving_hp_recovery": {"walking_min": round(s["walking_min"], 3),
                               "natural_while_walking": int(s["natural_while_walking"]),
                               "irp_while_walking": int(s["irp_while_walking"])},
        "hard_bars": {k: int(s[k]) for k in ("map_changes_other", "npc_contacts",
                                             "attack_requests_non_monster")},
        "strikes": {"n": int(s["strikes"]), "landed": int(s["landed"]),
                    "landed_rate": round(s["landed"] / s["strikes"], 4) if s["strikes"] else None},
        "engagements": dict(eng), "end_reason": ", ".join(f"{k} x{v}" for k, v in ends.items()),
    }  # fmt: skip


def by_strategy(rows: Sequence[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    """PURE: the pooled row of each strategy (A, B, C, ... in that order; None as "?")."""
    groups: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for r in rows:
        groups[str(r.get("strategy") or "?")].append(r)
    return {k: pool(v, k) for k, v in sorted(groups.items())}


def _f(v: Any, nd: int = 1) -> str:
    return "-" if v is None else (f"{v:.{nd}f}" if isinstance(v, float) else str(v))


def _pct(v: Any) -> str:
    return "-" if v is None else f"{100 * float(v):.1f} %"


def cells(r: Mapping[str, Any]) -> dict[str, str]:
    """PURE: a row (a run's or a pooled one) as the table's text cells."""
    hb = r.get("hard_bars") or {}
    st = r.get("strikes") or {}
    m = r.get("moving_hp_recovery") or {}
    eng = r.get("engagements") or {}
    ec = r.get("economics") or {}
    wins = ec.get("windows_10min")
    return {
        "runs": f"{r.get('runs', 1)} ({_f(r.get('minutes'))} min)",
        "net": _f(r.get("net_h")), "gross": _f(r.get("gross_h")), "cost": _f(r.get("cost_h")),
        "cost_ratio": _pct(r.get("cost_ratio")),
        "sharpe": f"{_f(r.get('sharpe_10min'), 2)} (n {_f(wins)})",
        "deaths": f"{r.get('deaths')} ({_f(r.get('deaths_h'), 2)})",
        "resting": f"{_pct(r.get('resting_pct'))} ({_pct(r.get('sitting_pct'))})",
        "kills": _f(r.get("kills_h")),
        "potions": f"{r.get('potions')} ({_f(r.get('potions_h'))})",
        "fly": f"{r.get('fly_wings')} ({_f(r.get('fly_wings_h'))})",
        "heals": f"{r.get('heals')} ({_f(r.get('heals_h'))}) [{r.get('heals_confirmed')}]",
        "ag": f"{r.get('autoguard')} ({_f(r.get('autoguard_h'))})",
        "sp": f"{_f(r.get('sp_used_h'))} / {_f(r.get('sp_min'))}",
        "hp_min": f"{_f(r.get('hp_min'))} ({_pct(r.get('hp_min_pct'))})",
        "loot": f"{_pct(r.get('loot_completeness'))} [{_pct(r.get('loot_completeness_net'))}]",
        "landing": f"{st.get('landed')}/{st.get('n')} = {_pct(st.get('landed_rate'))}",
        "eng": " / ".join(str(eng.get(k, 0)) for k in ("battle_log", "hp_drop", "box")),
        "mhr": f"{_f(m.get('natural_while_walking'))} ({_f(m.get('walking_min'), 2)} min)",
        "irp_walk": _f(m.get("irp_while_walking")),
        "bars": f"{hb.get('map_changes_other')} / {hb.get('npc_contacts')} / "
        f"{hb.get('attack_requests_non_monster')}",
        "end": str(r.get("end_reason") or "-")[:40],
    }  # fmt: skip


ROWS = (
    ("runs (minutes)", "runs"), ("NET z / h", "net"), ("gross z / h", "gross"),
    ("cost z / h", "cost"), ("cost ratio", "cost_ratio"), ("Sharpe-like 10 min (n)", "sharpe"),
    ("deaths (/ h)", "deaths"), ("resting % (sitting %, packets)", "resting"),
    ("kills / h", "kills"), ("potions 504 (/ h)", "potions"), ("Fly Wings 601 (/ h)", "fly"),
    ("Heals cast (/ h) [HP-confirmed]", "heals"), ("Auto Guard casts (/ h)", "ag"),
    ("SP used / h / SP min", "sp"), ("HP min (% MaxHP)", "hp_min"),
    ("loot completeness [net]", "loot"), ("strikes landed", "landing"),
    ("engage battle_log / hp_drop / box", "eng"),
    ("MHR natural ticks walking (walk min)", "mhr"), ("IRP ticks walking (0)", "irp_walk"),
    ("HARD map other / NPC / non-mob atk", "bars"), ("end reason", "end"),
)  # fmt: skip


def box(cols: Sequence[tuple[str, Mapping[str, Any]]], title: str) -> str:
    """PURE: a box-drawing table, one column per row (run or strategy), metrics down the left."""
    cc = [(h, cells(r)) for h, r in cols]
    w0 = max(len(n) for n in [*(n for n, _k in ROWS), title])
    ws = [max(len(h), *(len(c[k]) for _n, k in ROWS)) for h, c in cc]

    def line(a: str, b: str, c: str) -> str:
        return a + b.join("─" * (w + 2) for w in [w0, *ws]) + c

    out = [line("┌", "┬", "┐"),
           "│ " + " │ ".join([title.ljust(w0)]
                            + [h.center(w) for (h, _c), w in zip(cc, ws, strict=True)]) + " │",
           line("├", "┼", "┤")]  # fmt: skip
    for n, k in ROWS:
        vals = [c[k].ljust(w) for (_h, c), w in zip(cc, ws, strict=True)]
        out.append("│ " + " │ ".join([n.ljust(w0), *vals]) + " │")
    out.append(line("└", "┴", "┘"))
    return "\n".join(out)


def run_label(r: Mapping[str, Any]) -> str:
    sid = str(r.get("session") or "")
    hhmm = sid[9:13] if len(sid) > 13 and sid[8] == "T" else sid[:8]
    return f"{r.get('strategy') or '?'} {hhmm}"


# --- loading (not pure) --------------------------------------------------------------------------


def session_dir(sid: str) -> Path:
    """The session's directory: /dev/shm while fresh, else the NAS."""
    d = DEMO / sid
    return d if (d / "packets.jsonl.gz").exists() else NAS / sid


def load(sid: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    d = session_dir(sid)
    ev_path = d / "events.jsonl"
    ev = ([json.loads(x) for x in ev_path.read_text().splitlines() if x]
          if ev_path.exists() else [])  # fmt: skip
    ev.sort(key=lambda e: int(e.get("t_ns") or 0))
    with gzip.open(d / "packets.jsonl.gz", "rt") as fh:
        pk = sorted((json.loads(x) for x in fh), key=_t)
    try:
        man = json.loads((d / "manifest.json").read_text())
    except (OSError, ValueError):
        man = {}
    man.setdefault("sid", sid)
    return ev, pk, man


def load_table(path: Path | None) -> Mapping[str, Mapping[str, Any]] | None:
    """The item table (econ_items.py build; GPL-derived, local only), or None when not built."""
    import econ_items

    p = path or econ_items.OUT
    try:
        return econ_items.load(p)["items"]  # type: ignore[no-any-return]
    except FileNotFoundError:
        return None


def drop_order_of(map_name: str, path: Path | None = None) -> Mapping[str, Sequence[int]] | None:
    """The map model's drop lists (econ_row's own / carry split), None when not built."""
    try:
        import econ_model

        md = (econ_model.load(path)["maps"] if path else econ_model.load()["maps"]).get(map_name)
    except (FileNotFoundError, ImportError, TypeError):
        return None
    if md is None:
        return None
    return {k: [int(d["item_id"]) for d in v["drops"] if d.get("item_id") is not None]
            for k, v in md["species"].items()}  # fmt: skip


def row(sid: str, table: Mapping[str, Mapping[str, Any]] | None, map_name: str | None = None,
        maps_path: Path | None = None, **kw: Any) -> dict[str, Any]:  # fmt: skip
    ev, pk, man = load(sid)
    mp = (
        map_name
        or next((e.get("map") for e in ev if e.get("kind") == "run_start"), None)
        or man.get("map")
        or MAP
    )
    out = judge(ev, pk, table, man, map_name=mp, drop_order=drop_order_of(mp, maps_path), **kw)
    out["session"] = sid
    return out


# --- the positive cases on REAL sessions ---------------------------------------------------------

SURVIVAL = {  # 3.96's trials (NAS): potions, a Fly Wing, a death, Auto Guard
    "potions": "20261021T193536-demo-crusader-survival-T-S2-F-f1c",
    "fly": "20261021T200150-demo-crusader-survival-T-S3h-C-h1",
    "death": "20261021T184414-demo-crusader-survival-T-S6-C-t1",
    "autoguard": "20261021T235737-demo-crusader-survival-T-S2-E-g1",
}
REGEN = "20261021T212245-demo-crusader-regen-r1"  # 3.96f
HUNT = "20261022T032441-demo-hunt-flow55"  # 3.97 v55 run 4 (prt_fild08)
HARD = "20261008T073847-demo-safety-check-npc-garnet"  # a warp to prt_church + an NPC contact


def positive(table: Mapping[str, Mapping[str, Any]] | None) -> list[dict[str, Any]]:
    """Each column against the judge that already owns it, on a REAL banked session (the lab's
    rule: a verifier proves a positive case). Returns [{case, got, want, ok}]."""
    import regen_walk as rw
    import survive_judge as sj

    out: list[dict[str, Any]] = []

    def check(case: str, got: Any, want: Any) -> None:
        out.append({"case": case, "got": got, "want": want, "ok": got == want})

    for what, sid in SURVIVAL.items():
        ev, pk, man = load(sid)
        r = judge(ev, pk, table, man, map_name="prt_fild08")
        s = sj.judge(ev, pk, offset_s=0.12, max_hp=(man.get("thresholds") or {}).get("MAX_HP"))
        check(f"{what} {sid[9:15]}: potions == survive_judge S2", r["potions"], s["S2"]["potions"])
        check(f"{what} {sid[9:15]}: Fly Wings == survive_judge S3", r["fly_wings"],
              s["S3"]["escapes"])  # fmt: skip
        check(f"{what} {sid[9:15]}: deaths == survive_judge S6", r["deaths"],
              s["S6"]["server_deaths"])  # fmt: skip
        check(f"{what} {sid[9:15]}: Auto Guard == survive_judge S4", r["autoguard"],
              s["S4"]["casts"])  # fmt: skip
        check(f"{what} {sid[9:15]}: HP min == survive_judge", r["hp_min"], s["hp_min"])
        if what == "fly":
            check("fly: one same-map teleport per Fly Wing, no other map",
                  (r["hard_bars"]["map_changes_same_map"]
                   - r["hard_bars"]["same_map_by_gm_command"],
                   r["hard_bars"]["map_changes_other"]), (r["fly_wings"], 0))  # fmt: skip
        mc = man.get("counts") or {}
        check(f"{what} {sid[9:15]}: potions / flys == the runner's own counts",
              (r["potions"], r["fly_wings"]), (mc.get("potion"), mc.get("fly")))  # fmt: skip
    ev, pk, man = load(REGEN)
    rj = rw.judge(ev, pk)
    keys = ("irp_ticks", "natural_ticks", "irp_while_walking", "natural_while_walking")
    want = {k: sum(int(p[k]) for p in rj["phases"]) for k in keys}
    got = dict.fromkeys(keys, 0)
    walk_got = 0.0
    for ph in (e for e in ev if e.get("kind") == "phase_end"):  # the same windows: its phases
        m = moving_hp_recovery(pk, int(ph["t0"]), int(ph["t1"]) - 1)
        for k in keys:
            got[k] += m[k]
        walk_got += m["walking_min"]
    check("regen r1: per phase, IRP / natural ticks (all, and while walking) == regen_walk",
          got, want)  # fmt: skip
    walk = sum(p["walking_share"] * p["minutes"] for p in rj["phases"])
    check("regen r1: walking minutes ~ regen_walk's phases (+-0.01)",
          abs(walk_got - walk) <= 0.01, True)  # fmt: skip
    r = judge(ev, pk, table, man, map_name="prt_fild08")
    m = r["moving_hp_recovery"]
    check("regen r1 (manifest window): IRP while walking 0, natural while walking 0 (3.96f)",
          (m["irp_while_walking"], m["natural_while_walking"]), (0, 0))  # fmt: skip
    ev, pk, man = load(HARD)
    r = judge(ev, pk, table, man, map_name="prt_fild08")
    check("hard bars garnet: map changes to another map (prt_church), NPC contacts",
          (r["hard_bars"]["map_changes_other"], r["hard_bars"]["other_maps"],
           r["hard_bars"]["npc_contacts"]), (1, ["prt_church"], 1))  # fmt: skip
    if table is None:  # skipped, not failed: the GPL-derived table is built locally at run time
        out.append({"case": "hunt v55: kills / economics / loot (SKIPPED: no item table)",
                    "got": None, "want": None, "ok": None})  # fmt: skip
        return out
    import econ_row as er
    import loot_complete as lc
    import search_study as ss

    root = session_dir(HUNT).parent
    sess = ss.load_session(HUNT, root=root)
    ev, pk, man = load(HUNT)
    r = judge(ev, pk, table, man, map_name="prt_fild08", t0=sess.t0, t1=sess.w1)
    rows, items = lc.session_rows_items(HUNT, sess)
    e = er.measure(sess.events, sess.t0, sess.w1, rows, items, table)
    s = lc.summary(rows)
    check("hunt v55: kills == econ_row (search_study window)", r["kills"], e["kills"])
    check("hunt v55: gross / cost / net z/h == econ_row", (r["gross_h"], r["cost_h"], r["net_h"]),
          (e["gross_h"], e["cost_h"], e["net_h"]))  # fmt: skip
    check("hunt v55: Sharpe-like == econ_row", r["sharpe_10min"], e["sharpe_10min"])
    check("hunt v55: loot completeness (and net) == loot_complete",
          (r["loot_completeness"], r["loot_completeness_net"]),
          (s["completeness"], s["completeness_net"]))  # fmt: skip
    check("hunt v55: hard bars (the map's own warp before the window is not counted)",
          r["hard_bars"]["pass"], True)  # fmt: skip
    return out


# --- the CLI -------------------------------------------------------------------------------------


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)  # fmt: skip
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("row", "table", "positive"):
        p = sub.add_parser(name)
        if name != "positive":
            p.add_argument("sids", nargs="+" if name == "table" else 1)
            p.add_argument("--map", default=None, help="the run's map (default: run_start's)")
        p.add_argument("--items", type=Path, default=None,
                       help="the item table (default: data/econ/items.json)")  # fmt: skip
        if name == "table":
            p.add_argument("--json", action="store_true")
    a = ap.parse_args()
    table = load_table(a.items)
    if a.cmd == "positive":
        res = positive(table)
        for x in res:
            tag = "SKIP" if x["ok"] is None else "PASS" if x["ok"] else "FAIL"
            print(f"{tag}  {x['case']}: got {x['got']} want {x['want']}")
        return 0 if all(x["ok"] is not False for x in res) else 1
    maps = a.items.parent / "maps.json" if a.items else None  # the map model beside the table
    rows = []
    for sid in a.sids:
        try:
            rows.append(row(sid, table, a.map, maps))
        except (OSError, ValueError, KeyError) as e:  # reported, never a silent drop
            print(f"{sid}: skipped ({type(e).__name__}: {e})", file=sys.stderr)
    if not rows:
        return 1
    if a.cmd == "row":
        print(json.dumps(rows[0], indent=1, default=str))
        return 0
    pooled = by_strategy(rows)
    text = (box([(run_label(r), r) for r in rows], "PER RUN (packets + events)") + "\n"
            + box([(f"{k} pooled", v) for k, v in pooled.items()],
                  "BY STRATEGY (pooled)"))  # fmt: skip
    if a.json:
        print(json.dumps({"runs": rows, "pooled": pooled, "text": text}, indent=1, default=str))
    else:
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
