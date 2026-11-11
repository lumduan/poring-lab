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
run); the row says which ("window.source"). ``--live S`` (a HUMAN demo, human_demo.py; Batt
2026-10-22: "the recording counts from my first input"): the manifest's t0_live_ns (his first
input) .. + S s, capped at its t_end_ns (the recording's end).

PER RUN -- from PACKETS (ours = the GM account's block id 2000002, the Crusader's too):
- kills / h: arm_judge.kills_of (a monster's death vanish <= 1.5 s after OUR damaging act);
- deaths / h: our own id's vanish with reason "died" (survive_judge.deaths_of; the hp packet at a
  death can read 1, so hp 0 is not the cue -- hp_zero_packets is reported beside it);
- HP min: the absolute hp packets in the window (and the value in force at its start), and the
  lowest share of MaxHP (the max_hp packet in force at each, else 5,260);
- potions / Fly Wings and per hour: OUR use_item_result successes of 504 / 601 (aid filter);
- Heals cast and per hour: NO skill-use packet is decoded (poring_packets has skill_list /
  skill_update only), so a Heal = our SP falling by EXACTLY 34 (AL_HEAL Lv 8); "confirmed" = an
  HP rise of 544 (+-1), or a smaller one that ends exactly at MaxHP, within 1 s of it (an absolute
  hp packet, or a decoded `recovery` amount). LIVE 2026-10-22: sp 312 -> 278 and hp +544 arrive
  at the same t_mono_ns;
- SP used (the sum of SP falls) and SP min; Auto Guard casts = SP falls of exactly 30 (a toggle:
  on or off, survive_judge's rule), Endure = 10. A fall that comes with a MaxSP change (a level /
  stat / character change) is not a cast and not SP used; one within a GM command's 2-s flag is
  counted and reported. When no SP packet precedes the window, the SP at its start is ASSUMED
  MaxSP 312 (said in "why");
- loot completeness: the hunt's definition (loot_complete: items PICKED / items DROPPED by ALL our
  kills, and net of a looter's re-drop of our own item), with the fates;
- gross / net zeny per hour, costs, cost ratio, Sharpe-like: econ_row.measure on the same kill
  rows (NPC sell prices for the picked drops; OUR consumables at the cheapest NPC's price: White
  Potion 1,200 z, Fly Wing 60 z; a Heal costs no zeny; 10-min windows of booked net zeny);
- Moving HP Recovery: our walk spans (regen_walk.walk_spans: self_move paths) and the regen ticks
  (regen_walk.ticks: natural +33 steps of the hp series, IRP = `recovery` amounts): natural ticks
  WHILE walking (MHR's evidence) and the walking minutes; IRP ticks while walking (must be 0);
- sitting % (our act kind sit, action 2 -> the next stand, action 3; decoded, LIVE-checked
  2026-10-22), the cross-check of the resting spans; natural ticks and regen HP / min while
  sitting (every 3 s instead of 6);
- HARD BARS: map changes to ANOTHER map (a Fly Wing is a same-map teleport: counted apart, and
  set beside the Fly Wings used), npc_contact, our attack requests on a non-monster (its latest
  entity_appear's objtype != 5; a target never seen is "unknown", reported, not a bar). A sit /
  stand request (attack_request kind sit / stand, action 2 / 3, target = our own id) is NOT an
  attack request anywhere here.
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
from collections.abc import Container, Iterable, Mapping, Sequence
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
CHAR_MAX_SP = {"crusader": 312, "thief": 112, "rogue": 336}  # run_start "char" (dungeon@6/@8)
CHAR_MAX_HP = {"crusader": 5260, "thief": 952, "rogue": 2146}  # 4.03 pilot: no max_hp packet
STEAL_SP = 10  # TF_STEAL's SpCost (pinned skill_db): a Thief's SP fall of exactly 10 = a try
PICK_S, STEAL_S = 2.0, 1.5  # a gain this soon after our pickup request / a steal's SP fall
SNATCH_S = 1.0  # dungeon@8: a gain this soon after OUR attack, no pickup / Steal = Snatcher
TARGET_ITEMS = {604: "Dead Branch", 757: "Rough Elunium", 756: "Rough Oridecon", 518: "Honey"}
# A looter killed after taking a STAGED target set (stage_items.py) drops the whole set in one batch
# around its corpse (4.04 s3 and s7). No pay_fild07 species drops more than two of the four target
# ids (Elder Willow 604 + 757, Bigfoot 518 + 756: econ_model's drop lists), so a pile holding
# >= STAGED_MIN_TARGETS different ones is a staged set coming back, not income. rAthena scatters a
# kill's drops within 1 cell of the corpse, so one pile spans <= 2 cells (s3: 324,58 and 326,57).
PILE_S, PILE_CELLS, STAGED_MIN_TARGETS = 0.5, 2, 3


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


def falls(ser: Sequence[tuple[int, int]], cost: int | None = None,
          skip: Container[int] = ()) -> list[tuple[int, int]]:  # fmt: skip
    """PURE: [(t, drop)] of the series' falls (all of them, or exactly ``cost``), leaving out a
    fall whose packet time is in ``skip`` (not_casts: a GM command's or a MaxSP change's)."""
    return [(t, v0 - v) for (_t0, v0), (t, v) in zip(ser, ser[1:], strict=False)
            if v < v0 and (cost is None or v0 - v == cost) and t not in skip]  # fmt: skip


def not_casts(packets: Sequence[Mapping[str, Any]], name: str = "sp", near_ms: int = 1
              ) -> set[int]:  # fmt: skip
    """PURE: the times of our ``name`` packets that are NOT a skill's cost: within ``near_ms`` of
    a change of its maximum (a level / stat / job / character change moves both: v55 run 0017's
    state rebuild by GM commands read as a 301-SP "cast" and an "Auto Guard" before this).
    NOT the gm_command flag: it marks a GM command AND the 2 s after it, which covers real casts
    (T-S2 F f1c's Auto Guard, 1.9 s after a GM spawn: survive_judge's S4 counts it)."""
    mx = [_t(e) for e in packets
          if e.get("type") == "stat_change" and e.get("name") == f"max_{name}"]  # fmt: skip
    return {_t(e) for e in packets
            if e.get("type") == "stat_change" and e.get("name") == name
            and any(abs(_t(e) - m) <= near_ms * 1_000_000 for m in mx)}  # fmt: skip


def gm_flagged(packets: Sequence[Mapping[str, Any]], name: str = "sp") -> set[int]:
    """PURE: the times of our ``name`` packets flagged gm_command (reported, still counted)."""
    return {_t(e) for e in packets if e.get("type") == "stat_change" and e.get("name") == name
            and e.get("gm_command")}  # fmt: skip


def overlap(spans: Iterable[tuple[int, int]], t0: int, t1: int) -> int:
    """PURE: the ns of ``spans`` inside [t0, t1]."""
    return sum(max(0, min(b, t1) - max(a, t0)) for a, b in spans)


def overlap2(a: Sequence[tuple[int, int]], b: Sequence[tuple[int, int]]) -> int:
    """PURE: the ns two span lists share (each list non-overlapping in itself)."""
    return sum(overlap(b, x0, x1) for x0, x1 in a)


def heal_casts(packets: Sequence[Mapping[str, Any]], t0: int, t1: int, sp_start: int | None,
               max_hp: int = MAX_HP, heal_hp: int = HEAL_HP, heal_sp: int = HEAL_SP,
               win_s: float = HEAL_WIN_S, skip: Container[int] = ()) -> dict[str, Any]:  # fmt: skip
    """PURE: our Heals. There is NO decoded skill-use packet, so a cast = our SP falling by
    exactly ``heal_sp``; it is CONFIRMED by an HP rise of ``heal_hp`` (+-1), or a smaller one
    ending exactly at MaxHP (a capped heal; the max_hp packet in force then, else ``max_hp``),
    within ``win_s`` of the fall -- on the HP series with the decoded `recovery` amounts added
    (survive_judge.hp_with_recovery), so a heal sent either way counts. LIVE 2026-10-22 11:4x
    (20261022T113202-demo-crusader-live-sit-heal): a Heal Lv 8 on self = sp 312 -> 278 and an
    absolute hp +544 at the SAME t_mono_ns, nothing else."""
    import survive_judge as sj

    sp = clip(series(packets, "sp"), t0, t1, sp_start)
    casts = [t for t, _d in falls(sp, heal_sp, skip)]
    hp = sj.hp_with_recovery(packets, max_hp)
    mxs = series(packets, "max_hp")
    rises = [(t, v - v0, v) for (_a, v0), (t, v) in zip(hp, hp[1:], strict=False) if v > v0]
    ok = []
    for tc in casts:
        ok.append(any(abs(t - tc) <= win_s * NS
                      and (abs(r - heal_hp) <= 1
                           or (v >= (in_force(mxs, t) or max_hp) and 0 < r < heal_hp))
                      for t, r, v in rises))  # fmt: skip
    return {"casts": len(casts), "confirmed": sum(ok),
            "times_s": [round((t - t0) / NS, 2) for t in casts],
            "via": f"sp fall of exactly {heal_sp} (no skill-use packet is decoded); confirmed = "
            f"hp rise {heal_hp} +-1 or capped at MaxHP within {win_s} s"}  # fmt: skip


def is_attack_request(e: Mapping[str, Any], aid: int = AID) -> bool:
    """PURE: an attack request of ours: attack_request with action 0 / 7 (is_attack). NOT a sit /
    stand request: LIVE 2026-10-22, those arrive as attack_request kind sit / stand, action 2 / 3,
    target_gid = OUR OWN id -- excluded by kind and by target too."""
    return (e.get("type") == "attack_request" and e.get("kind") not in ("sit", "stand")
            and int(e.get("target_gid") or -1) != aid
            and bool(e.get("is_attack") or int(e.get("action", -1)) in (0, 7)))  # fmt: skip


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
    reqs = sorted(_t(e) for e in packets if is_attack_request(e, aid))
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


HOUSE_MATCH_S = 30.0  # --rest house: a map change within this of the runner's own click
HOUSE_CELL_TOL = 1  # ... at the warp's destination cell (rAthena places us there exactly)


def house_allow(events: Sequence[Mapping[str, Any]], map_name: str
                ) -> list[tuple[int, str, tuple[int, int]]]:  # fmt: skip
    """PURE (--rest house, docs/planning/gef10-house-rest.md): the map changes the RUNNER caused
    and recorded -- each ``house_door`` event allows ONE change to in_orcs01 at its ``arrival``,
    each ``house_exit`` event ONE change back to ``map_name`` at its ``back`` cell (the events'
    clicks; matched by hard_bars within HOUSE_MATCH_S). No such events (every other run): []."""
    out: list[tuple[int, str, tuple[int, int]]] = []
    for e in events:
        k = e.get("kind")
        if k == "house_door" and e.get("arrival"):
            a = e["arrival"]
            out.append((int(e["t_ns"]), "in_orcs01", (int(a[0]), int(a[1]))))
        elif k == "house_exit" and e.get("back"):
            b = e["back"]
            out.append((int(e["t_ns"]), map_name.removesuffix(".gat"), (int(b[0]), int(b[1]))))
    return out


def hard_bars(packets: Sequence[Mapping[str, Any]], t0: int, t1: int, map_name: str,
              aid: int = AID, allow: Sequence[tuple[int, str, tuple[int, int]]] = ()
              ) -> dict[str, Any]:  # fmt: skip
    """PURE: map changes to ANOTHER map (the bar) vs same-map teleports (a Fly Wing), NPC
    contacts, and our attack requests on a non-monster / an unknown target, in [t0, t1].
    ``allow`` (house_allow; --rest house only): a map change to the named map at the named cell
    within HOUSE_MATCH_S after a recorded click of the runner is the house trip it planned --
    counted as ``map_changes_house``, each allowance used once; every other one stays a bar."""
    appears = objtypes(packets)
    other: list[str] = []
    same = same_gm = npc = non_mob = unknown = 0
    house = 0
    left = sorted(allow)
    want = map_name.removesuffix(".gat")
    for e in packets:
        t = _t(e)
        if not t0 <= t <= t1:
            continue
        typ = e.get("type")
        if typ == "map_change":
            m = str(e.get("map") or "").removesuffix(".gat")
            xy = (int(e.get("x") or -1), int(e.get("y") or -1))
            hit = next((i for i, (ta, ma, ca) in enumerate(left)
                        if ta <= t <= ta + HOUSE_MATCH_S * NS and ma == m
                        and max(abs(xy[0] - ca[0]), abs(xy[1] - ca[1])) <= HOUSE_CELL_TOL),
                       None)  # fmt: skip
            if hit is not None and not e.get("gm_command"):
                left.pop(hit)
                house += 1
            elif m != want:
                other.append(m)
            else:
                same += 1
                same_gm += bool(e.get("gm_command"))
        elif typ == "npc_contact":
            npc += 1
        elif is_attack_request(e, aid):
            o = objtype_at(appears, int(e.get("target_gid") or -1), t)
            if o is None:
                unknown += 1
            elif o != MOB:
                non_mob += 1
    return {"map_changes_other": len(other), "other_maps": sorted(set(other)),
            "map_changes_same_map": same, "same_map_by_gm_command": same_gm,
            "npc_contacts": npc, "attack_requests_non_monster": non_mob,
            "attack_requests_unknown_target": unknown,
            "pass": not other and npc == 0 and non_mob == 0,
            **({"map_changes_house": house} if allow else {})}  # fmt: skip


def moving_hp_recovery(packets: Sequence[Mapping[str, Any]], t0: int, t1: int,
                       rests: Sequence[tuple[int, int]] = (),
                       sits: Sequence[tuple[int, int]] = ()) -> dict[str, Any]:  # fmt: skip
    """PURE: regen_walk's walk spans and ticks inside the window: natural ticks WHILE walking
    (Moving HP Recovery's evidence: without it natural regen stops while walking) and the walking
    minutes; IRP ticks while walking (must be 0); the regen while resting (``rests``). A
    `recovery` amount above IRP's 155 (a capped tick is smaller) is NOT regen -- e.g. a Heal, if
    one is ever sent as ZC_RECOVERY -- and is counted apart ("recovery_not_regen"). While
    SITTING (``sits``: our act sit -> stand) natural regen ticks every 3 s instead of 6 (LIVE
    2026-10-22: +32 every 3 s; IRP 155 every 10 s unchanged): the ticks and HP / min there."""
    import regen_walk as rw

    spans = rw.walk_spans(packets)
    all_tk = [x for x in rw.ticks(packets) if t0 <= x["t"] <= t1]
    tk = [x for x in all_tk if x["kind"] == "natural" or x["amount"] <= rw.IRP]
    walk_ns = overlap(spans, t0, t1)
    nat = [x for x in tk if x["kind"] == "natural"]
    irp = [x for x in tk if x["kind"] == "irp"]
    rest_ns = sum(b - a for a, b in rests)
    in_rest = [x for x in tk if any(a <= x["t"] < b for a, b in rests)]
    sit_ns = sum(b - a for a, b in sits)
    in_sit = [x for x in tk if any(a <= x["t"] < b for a, b in sits)]
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
        "natural_while_sitting": sum(1 for x in in_sit if x["kind"] == "natural"),
        "sitting_min": round(sit_ns / NS / 60, 3),
        "regen_hp_per_min_sitting": round(sum(x["amount"] for x in in_sit) / (sit_ns / NS / 60),
                                          1) if sit_ns else None,
        "regen_hp": sum(x["amount"] for x in tk),
        "regen_hp_resting": sum(x["amount"] for x in in_rest),
        "regen_hp_sitting": sum(x["amount"] for x in in_sit),
        "recovery_not_regen": len(all_tk) - len(tk),
    }  # fmt: skip


# --- the row -------------------------------------------------------------------------------------


def staged_floor_ids(packets: Sequence[Mapping[str, Any]]) -> set[int]:
    """PURE: the floor ids of the TARGET items in every pile that holds >= STAGED_MIN_TARGETS
    different target ids (a staged set back from a looter; see PILE_S). A pile links
    floor_item_appear entries <= PILE_S and <= PILE_CELLS (Chebyshev) apart, transitively. The
    looter's own drop in the same pile stays income."""
    fl = sorted((e for e in packets if e.get("type") == "floor_item_appear"), key=_t)
    up = list(range(len(fl)))

    def root(i: int) -> int:
        while up[i] != i:
            up[i] = up[up[i]]
            i = up[i]
        return i

    for i, a in enumerate(fl):
        for b_ in range(i + 1, len(fl)):
            b = fl[b_]
            if _t(b) - _t(a) > PILE_S * NS:
                break
            if max(abs(int(a["x"]) - int(b["x"])), abs(int(a["y"]) - int(b["y"]))) <= PILE_CELLS:
                up[root(b_)] = root(i)
    piles: dict[int, list[Mapping[str, Any]]] = defaultdict(list)
    for i, e in enumerate(fl):
        piles[root(i)].append(e)
    out: set[int] = set()
    for pile in piles.values():
        tgt = [e for e in pile if int(e.get("item_id") or 0) in TARGET_ITEMS]
        if len({int(e["item_id"]) for e in tgt}) >= STAGED_MIN_TARGETS:
            out |= {int(e["floor_id"]) for e in tgt}
    return out


def item_gains(packets: Sequence[Mapping[str, Any]], t0: int, t1: int,
               steal_falls: Sequence[int] = (), staged: Container[int] = (),
               attacks: Sequence[int] = ()) -> dict[str, Any]:  # fmt: skip
    """PURE (Batt 2026-10-24: every item collected, per hour): each successful inventory gain
    (pickup_result ok, which fires for EVERY gain) in [t0, t1] by its cause -- "picked" when our
    pickup_request came <= PICK_S before it ("staged" instead when that request's floor id is in
    ``staged``: staged_floor_ids), "stolen" when a Steal's SP fall did <= STEAL_S before it,
    "snatched" when one of OUR attack acts (``attacks``: the Rogue's, dungeon@8; for a human demo
    of the Rogue, own_hits) did <= SNATCH_S before it (Snatcher steals inside the attack), else
    "other" (reported, e.g. a GM @item) -- per item id."""
    req = sorted((_t(e), int(e.get("floor_id") or 0)) for e in packets
                 if e.get("type") == "pickup_request")  # fmt: skip
    reqs = [t for t, _f in req]
    falls_ = sorted(steal_falls)
    atk_ = sorted(attacks)
    by: dict[int, Counter[str]] = defaultdict(Counter)
    for e in packets:
        if e.get("type") != "pickup_result" or not e.get("ok"):
            continue
        t = _t(e)
        if not t0 <= t <= t1:
            continue
        i = bisect.bisect_right(reqs, t)
        j = bisect.bisect_right(falls_, t)
        if i and t - reqs[i - 1] <= PICK_S * NS:
            kind = "staged" if req[i - 1][1] in staged else "picked"
        elif j and t - falls_[j - 1] <= STEAL_S * NS:
            kind = "stolen"
        elif (k := bisect.bisect_right(atk_, t)) and t - atk_[k - 1] <= SNATCH_S * NS:
            kind = "snatched"
        else:
            kind = "other"
        by[int(e.get("item_id") or 0)][kind] += int(e.get("amount") or 1)
    return {str(k): dict(v) for k, v in sorted(by.items())}


def own_hits(packets: Sequence[Mapping[str, Any]], aid: int = AID) -> list[int]:
    """PURE (rogue-gef10.md Amendment L, 2026-10-26): the times of OUR acts that did damage (> 0)
    to another unit, for item_gains' Snatcher rule when no runner event names the character (a
    human demo: Batt's gef_fild10 Rogue). A miss, a pickup, a sit / stand, or an act on ourselves
    is none of them."""
    return sorted(_t(e) for e in packets if e.get("type") == "act"
                  and int(e.get("src_gid") or -1) == aid
                  and int(e.get("target_gid") or -1) != aid
                  and e.get("kind") not in NOT_A_HIT and int(e.get("damage") or 0) > 0)  # fmt: skip


STEAL_TARGET_S = 15.0  # dungeon@7: the robbed monster = the one our next attack hits within this


def steal_by_species(packets: Sequence[Mapping[str, Any]], steal_falls: Sequence[int], aid: int
                     ) -> dict[str, dict[str, int]]:  # fmt: skip
    """PURE (dungeon@7, a Steal on every monster): per Steal (an SP fall of STEAL_SP), the robbed
    monster's name = the target of OUR next attack act within STEAL_TARGET_S (the runner strikes
    the same monster right after its Steal; its name from the entity_appear packets), and whether
    an item came in within STEAL_S with no pickup request of ours just before it."""
    names: dict[int, str] = {}
    acts: list[tuple[int, int]] = []
    gains: list[int] = []
    reqs = sorted(_t(e) for e in packets if e.get("type") == "pickup_request")
    for e in sorted(packets, key=_t):
        ty = e.get("type")
        if ty == "entity_appear" and e.get("name"):
            names[int(e.get("gid") or 0)] = str(e["name"])
        elif (ty == "act" and e.get("src_gid") == aid and e.get("target_gid") != aid
              and e.get("action") in (0, 8, 10)):  # fmt: skip
            acts.append((_t(e), int(e.get("target_gid") or 0)))
        elif ty == "pickup_result" and e.get("ok"):
            t = _t(e)
            i = bisect.bisect_right(reqs, t)
            if not (i and t - reqs[i - 1] <= PICK_S * NS):
                gains.append(t)
    out: dict[str, dict[str, int]] = defaultdict(lambda: {"tries": 0, "stolen": 0})
    act_t = [t for t, _g in acts]
    for f in sorted(steal_falls):
        k = bisect.bisect_left(act_t, f)
        name = "unknown"
        if k < len(acts) and acts[k][0] - f <= STEAL_TARGET_S * NS:
            name = names.get(acts[k][1], "unknown")
        g = bisect.bisect_left(gains, f)  # the item and the SP fall share a packet batch (4.04
        ok = g < len(gains) and gains[g] - f <= STEAL_S * NS  # pilot: the SAME t_mono_ns)
        out[name]["tries"] += 1
        out[name]["stolen"] += int(ok)
    return {k: dict(v) for k, v in sorted(out.items())}


def items_rows(gains: Mapping[str, Mapping[str, int]], hours: float,
               names: Mapping[str, str] | None = None) -> list[dict[str, Any]]:  # fmt: skip
    """PURE: the per-item table (picked / stolen / other, total and per hour), the target items
    flagged, most collected first. "staged" (a staged set back from a looter) is shown but kept
    OUT of the total and the per-hour rate: it is not income."""
    out = []
    for k, c in gains.items():
        tot = sum(int(v) for f, v in c.items() if f != "staged")
        out.append({"item_id": int(k), "name": (names or {}).get(k) or TARGET_ITEMS.get(int(k)),
                    "picked": int(c.get("picked", 0)), "stolen": int(c.get("stolen", 0)),
                    "snatched": int(c.get("snatched", 0)),
                    "other": int(c.get("other", 0)), "staged": int(c.get("staged", 0)),
                    "total": tot,
                    "per_h": round(tot / hours, 2) if hours > 0 else None,
                    "target": int(k) in TARGET_ITEMS})  # fmt: skip
    return sorted(out, key=lambda x: (-x["total"], x["item_id"]))


INCOME = ("picked", "stolen", "snatched")  # the bot's own gains (staged / other are not income)


def items_value(items: Sequence[Mapping[str, Any]], table: Mapping[str, Mapping[str, Any]] | None,
                hours: float) -> dict[str, Any]:  # fmt: skip
    """PURE (rogue-gef10.md section 5, 4.05's PRIMARY measure): the value of every item the bot
    itself gained (picked + stolen + snatched) at NPC sell and at Overcharge Lv 10 (econ_items'
    `sell` / `sell_oc10`, pre-renewal), total and per hour. econ_row's gross counts pickups only."""
    if table is None:
        return {"why": "no item table (econ_items.py build)"}
    v = voc = 0
    unpriced = []
    for it in items:
        n = sum(int(it.get(f, 0)) for f in INCOME)
        t = table.get(str(it["item_id"]))
        if not n:
            continue
        if t is None:
            unpriced.append(int(it["item_id"]))
            continue
        v += n * int(t.get("sell") or 0)
        voc += n * int(t.get("sell_oc10") or 0)
    per = (lambda x: round(x / hours, 1)) if hours > 0 else (lambda x: None)  # noqa: E731
    return {"value": v, "value_oc": voc, "value_h": per(v), "value_oc_h": per(voc),
            "unpriced": unpriced}  # fmt: skip


def kills_loot(packets: Sequence[Mapping[str, Any]], w0: int, w1: int, aid: int = AID
               ) -> tuple[list[dict[str, Any]], dict[int, dict[str, Any]]]:  # fmt: skip
    """PURE: (our kills in [w0, w1] as loot_complete.kill_rows, every floor item's fate as
    arm_judge.item_fates) -- the rows judge() measures the loot and the economics on (econ_dash
    reads the same rows per item)."""
    import arm_judge as aj
    import flow_judge as fj
    import hunt_core as hc
    import loot_complete as lc

    kills = aj.kills_of(packets, aid)
    pos = hc.walk_positions(packets)
    items = aj.item_fates(packets, pos, fj.mob_at)
    krows = lc.kill_rows(kills, items, lambda g, t: fj.mob_at(pos, g, t), [], {}, w0, w1)
    return krows, items


def judge(events: Sequence[Mapping[str, Any]], packets: Sequence[Mapping[str, Any]],
          table: Mapping[str, Mapping[str, Any]] | None, manifest: Mapping[str, Any] | None = None,
          map_name: str | None = None, t0: int | None = None, t1: int | None = None,
          aid: int = AID, drop_order: Mapping[str, Sequence[int]] | None = None,
          ) -> dict[str, Any]:  # fmt: skip
    """PURE: one run's row. ``table``: econ_items' items (None: no economics, said in "why");
    ``t0`` / ``t1``: override the window (the positive cases use the other judges' windows)."""
    import econ_row as er
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
    mxs = series(packets, "max_hp")
    # a human demo has no run_start: its manifest names the character (2026-10-26, Batt's Rogue
    # demo read against the Crusader's 5,260 MaxHP: "HP low 9 %" was 22 %, gef10-time-budget.md 8)
    char = str(rs.get("char") or man.get("character") or "crusader")
    # the run's own MaxHP first (run_start since 2026-11-05: the Rogue at Base 99), else the
    # character's table (older sessions)
    mx = in_force(mxs, w0) or rs.get("max_hp") or CHAR_MAX_HP.get(char, MAX_HP)
    hp = clip(series(packets, "hp"), w0, w1)
    hp_min = min((v for _t, v in hp), default=None)
    hp_pct = [v / (in_force(mxs, t) or mx) for t, v in hp]  # against the MaxHP in force then
    sp_raw = series(packets, "sp")
    sp_start = in_force(sp_raw, w0)
    max_sp = rs.get("max_sp") or CHAR_MAX_SP.get(char, MAX_SP)
    if sp_start is None:
        sp_start = max_sp
        why["sp_start"] = f"no sp packet before the window: its start ASSUMED MaxSP {max_sp}"
    sp = clip(sp_raw, w0, w1, sp_start)
    skip = not_casts(packets, "sp")
    sp_falls = falls(sp, skip=skip)
    n_skip = len(falls(sp)) - len(sp_falls)
    if n_skip:
        why["sp_falls_skipped"] = (f"{n_skip} SP fall(s) with a MaxSP change (a level / stat / "
                                   "character change): not casts, not SP used")  # fmt: skip
    gmf = gm_flagged(packets, "sp")
    n_gm = sum(1 for t, _d in sp_falls if t in gmf)
    if n_gm:
        why["sp_falls_gm_window"] = (f"{n_gm} SP fall(s) within 2 s of a GM command (gm_command "
                                     "flag) COUNTED: the flag also covers real casts")  # fmt: skip
    heals = heal_casts(packets, w0, w1, sp_start, max_hp=mx, skip=skip)
    deaths = [t for t in sj.deaths_of(packets, aid) if w0 <= t <= w1]
    pots = [t for t in sj.items_used(packets, POTION, aid) if w0 <= t <= w1]
    flys = [t for t in sj.items_used(packets, FLY, aid) if w0 <= t <= w1]
    # kills, loot, economics
    krows, items = kills_loot(packets, w0, w1, aid)
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
    # dungeon@6: every item gained per hour, by cause; Steal tries = SP falls of exactly 10 (only a
    # character with Steal on its keys: the Crusader's Endure costs 10 too)
    thief = rs.get("char") in ("thief", "rogue")  # dungeon@8: the Rogue keeps Steal on F3
    st_falls = [t for t, d in sp_falls if d == STEAL_SP] if thief else []
    # dungeon@8: the Rogue's Snatcher steals inside its own attacks (our attack acts' times)
    atks = sorted(_t(e) for e in packets if e.get("type") == "act" and e.get("src_gid") == aid
                  and e.get("target_gid") != aid and e.get("action") in (0, 8, 10)
                  ) if rs.get("char") == "rogue" else []  # fmt: skip
    if not rs and man.get("character") == "rogue":  # Amendment L: a human demo of the Rogue
        atks = own_hits(packets, aid)
        why["snatched"] = ("no runner events (a human demo): Snatcher = a gain <= SNATCH_S after "
                           "our own act with damage > 0 (packets)")  # fmt: skip
    gains = item_gains(packets, w0, w1, st_falls, staged_floor_ids(packets), atks)
    n_stolen = sum(int(c.get("stolen", 0)) for c in gains.values())
    steal_ev = [e for e in ev if e.get("kind") == "steal"]
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
        "hp_min_pct": round(min(hp_pct), 4) if hp_pct else None,
        "potions": len(pots), "potions_h": per_h(len(pots)),
        "fly_wings": len(flys), "fly_wings_h": per_h(len(flys)),
        "heals": heals["casts"], "heals_confirmed": heals["confirmed"],
        "heals_h": per_h(heals["casts"]), "heal_detail": heals,
        "sp_used": sum(d for _t, d in sp_falls), "sp_used_h": per_h(sum(d for _t, d in sp_falls)),
        "sp_min": min((v for _t, v in sp), default=None), "sp_start": sp_start,
        "autoguard": len(falls(sp, AG_SP, skip)),
        "autoguard_h": per_h(len(falls(sp, AG_SP, skip))),
        "endure": len(falls(sp, ENDURE_SP, skip)),
        "char": rs.get("char") or "crusader",
        "items": items_rows(gains, h, item_names()),
        "value": items_value(items_rows(gains, h, item_names()), table, h),
        "steal": {"tries_packets": len(st_falls), "stolen": n_stolen,
                  "per_try": round(n_stolen / len(st_falls), 4) if st_falls else None,
                  "runner_tries": len(steal_ev),
                  "runner_cast": sum(1 for e in steal_ev if e.get("cast")),
                  "runner_ok": sum(1 for e in steal_ev if e.get("ok")),
                  "runner_found": sum(1 for e in steal_ev if e.get("found") is not None),
                  "skipped_sp": sum(1 for e in ev if e.get("kind") == "steal_skip"),
                  "by_species": steal_by_species(packets, st_falls, aid)},
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
        "moving_hp_recovery": moving_hp_recovery(packets, w0, w1, rests, sits),
        "sitting_pct": round(sit_ns / max(1, w1 - w0), 4),
        "hard_bars": hard_bars(packets, w0, w1, mp, aid, house_allow(ev, mp)),
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
            "autoguard": [presses.get("autoguard", 0), len(falls(sp, AG_SP, skip))],
            "endure": [presses.get("endure", 0), len(falls(sp, ENDURE_SP, skip))],
            "sit": [presses.get("sit", 0), len(sits)],
            "deaths": [sum(1 for e in ev if e.get("kind") == "death"), len(deaths)],
        },
        "why": why,
    }  # fmt: skip


def item_names(path: Path | None = None) -> dict[str, str]:
    """The KB's item names (data/kb/items.json, run-time GPL-derived data, never committed); {}
    when absent (the table then names only the target items)."""
    p = path or Path(__file__).resolve().parents[1] / "data" / "kb" / "items.json"
    try:
        return {k: str(v.get("name")) for k, v in json.loads(p.read_text()).items()}
    except OSError:
        return {}


def pool_items(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """PURE: the per-item table pooled over runs (counts summed, per hour from the summed hours)."""
    hours = sum(float(r.get("hours") or 0) for r in rows)
    acc: dict[str, Counter[str]] = defaultdict(Counter)
    names: dict[str, str] = {}
    for r in rows:
        for it in r.get("items") or []:
            k = str(it["item_id"])
            for f in ("picked", "stolen", "snatched", "other", "staged"):
                acc[k][f] += int(it.get(f, 0))
            if it.get("name"):
                names[k] = str(it["name"])
    return items_rows({k: dict(v) for k, v in acc.items()}, hours, names)


def items_box(items: Sequence[Mapping[str, Any]], title: str) -> str:
    """The per-item table as a box (Batt 2026-10-24); target items marked *; "staged" is not in
    the total."""
    head = ("item", "picked", "stolen", "snatched", "other", "staged", "total", "per h")
    rows_ = [(("* " if it["target"] else "  ") + str(it["name"] or it["item_id"])[:22],
              str(it["picked"]), str(it["stolen"]), str(it.get("snatched", 0)), str(it["other"]),
              str(it.get("staged", 0)),
              str(it["total"]), _f(it["per_h"], 2)) for it in items]  # fmt: skip
    w = [max(len(h_), *(len(x[i]) for x in rows_)) if rows_ else len(h_)
         for i, h_ in enumerate(head)]  # fmt: skip
    line = lambda a_, m_, b_: a_ + m_.join("─" * (x + 2) for x in w) + b_  # noqa: E731
    fmt = lambda c: "│" + "│".join(f" {v:<{w[i]}} " for i, v in enumerate(c)) + "│"  # noqa: E731
    out = [title, line("┌", "┬", "┐"), fmt(head), line("├", "┼", "┤")]
    out += [fmt(x) for x in rows_] + [line("└", "┴", "┘")]
    return "\n".join(out)


# --- pooling and the tables ----------------------------------------------------------------------

_SUMS = ("hours", "kills", "deaths", "potions", "fly_wings", "heals", "heals_confirmed",
         "sp_used", "autoguard", "endure", "escapes", "runner_kills")  # fmt: skip


def _pool_value(rows: Sequence[Mapping[str, Any]], hours: float) -> dict[str, Any]:
    """PURE: items_value pooled: the runs' values summed, per hour from the summed hours."""
    vals = [r.get("value") or {} for r in rows]
    if not rows or any("value" not in v for v in vals):
        return {"why": "a run without an item value"}
    v, voc = sum(int(x["value"]) for x in vals), sum(int(x["value_oc"]) for x in vals)
    return {"value": v, "value_oc": voc,
            "value_h": round(v / hours, 1) if hours else None,
            "value_oc_h": round(voc / hours, 1) if hours else None}  # fmt: skip


def pool(rows: Sequence[Mapping[str, Any]], label: str = "pooled") -> dict[str, Any]:
    """PURE: several runs pooled: counts / seconds summed, rates re-taken from the sums, minima
    the minimum, the economics by econ_row.pool (all runs' 10-min windows together)."""
    import econ_row as er

    s: dict[str, float] = defaultdict(float)
    for r in rows:
        for k in _SUMS:
            s[k] += float(r.get(k) or 0)
        w = r.get("window") or {}
        if w.get("t0") is not None and w.get("t1") is not None:  # exact, not the rounded hours
            s["hours"] += (int(w["t1"]) - int(w["t0"])) / NS / 3600 - float(r.get("hours") or 0)
        s["rest_s"] += float((r.get("rest") or {}).get("seconds") or 0)
        s["sit_s"] += float((r.get("rest") or {}).get("sitting_seconds") or 0)
        for k, v in (r.get("loot") or {}).items():
            if k in ("items", "picked", "redrops", "recovered"):
                s["loot_" + k] += float(v or 0)
        m = r.get("moving_hp_recovery") or {}
        for k in ("walking_min", "natural_while_walking", "irp_while_walking", "regen_hp",
                  "regen_hp_resting", "regen_hp_sitting"):  # fmt: skip
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
        "value": _pool_value(rows, h),
        "moving_hp_recovery": {
            "walking_min": round(s["walking_min"], 3),
            "natural_while_walking": int(s["natural_while_walking"]),
            "irp_while_walking": int(s["irp_while_walking"]),
            "regen_hp_per_min": round(s["regen_hp"] / (h * 60), 1) if h else None,
            "regen_hp_per_min_resting": round(s["regen_hp_resting"] / (s["rest_s"] / 60), 1)
            if s["rest_s"] else None,
            "regen_hp_per_min_sitting": round(s["regen_hp_sitting"] / (s["sit_s"] / 60), 1)
            if s["sit_s"] else None,
        },
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
        "regen": f"{_f(m.get('regen_hp_per_min'))} / {_f(m.get('regen_hp_per_min_resting'))} "
        f"/ {_f(m.get('regen_hp_per_min_sitting'))}",
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
    ("regen HP / min: all / resting / sitting", "regen"),
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
    """The session's directory: /dev/shm while fresh, else the NAS. A PATH (anything with a "/",
    e.g. an archived session under the NAS's scratch-archive/<date>/demo-sessions/, 2026-11-11
    econ_dash) is taken as the directory itself."""
    if "/" in sid:
        return Path(sid)
    d = DEMO / sid
    return d if (d / "packets.jsonl.gz").exists() else NAS / sid


def load(sid: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    """(events, packets, manifest) of a session id or directory; the manifest's ``sid``
    defaults to the directory's name."""
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
    man.setdefault("sid", d.name)
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


def live_window(man: Mapping[str, Any], seconds: float) -> tuple[int, int]:
    """PURE: a human demo's window: his first input (t0_live_ns) .. + seconds, capped at the
    recording's end (t_end_ns)."""
    t0 = man.get("t0_live_ns")
    if not t0:
        raise ValueError("--live: the manifest has no t0_live_ns (not a played human demo)")
    t1 = int(t0) + int(seconds * NS)
    end = man.get("t_end_ns")
    return int(t0), min(t1, int(end)) if end else t1


def row(sid: str, table: Mapping[str, Mapping[str, Any]] | None, map_name: str | None = None,
        maps_path: Path | None = None, live_s: float | None = None,
        **kw: Any) -> dict[str, Any]:  # fmt: skip
    ev, pk, man = load(sid)
    if live_s is not None:
        kw["t0"], kw["t1"] = live_window(man, live_s)
    mp = (
        map_name
        or next((e.get("map") for e in ev if e.get("kind") == "run_start"), None)
        or man.get("map")
        or MAP
    )
    out = judge(ev, pk, table, man, map_name=mp, drop_order=drop_order_of(mp, maps_path), **kw)
    out["session"] = session_dir(sid).name
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
LIVE = "20261022T113202-demo-crusader-live-sit-heal"  # the parent's live check: a Heal, a sit


def present(sid: str) -> bool:
    return (session_dir(sid) / "packets.jsonl.gz").exists()


def positive(table: Mapping[str, Mapping[str, Any]] | None) -> list[dict[str, Any]]:
    """Each column against the judge that already owns it, on a REAL banked session (the lab's
    rule: a verifier proves a positive case). Returns [{case, got, want, ok}]."""
    import survive_judge as sj

    out: list[dict[str, Any]] = []

    def check(case: str, got: Any, want: Any) -> None:
        out.append({"case": case, "got": got, "want": want, "ok": got == want})

    def skip(sid: str) -> bool:  # an absent session is SKIPPED, never a pass
        if present(sid):
            return False
        out.append({"case": f"{sid}: SKIPPED (not banked here)", "got": None, "want": None,
                    "ok": None})  # fmt: skip
        return True

    for what, sid in SURVIVAL.items():
        if skip(sid):
            continue
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
    if not skip(LIVE):
        live(load(LIVE), table, check)
    if not skip(REGEN):
        regen(load(REGEN), table, check)
    if not skip(HARD):
        ev, pk, man = load(HARD)
        r = judge(ev, pk, table, man, map_name="prt_fild08")
        check("hard bars garnet: map changes to another map (prt_church), NPC contacts",
              (r["hard_bars"]["map_changes_other"], r["hard_bars"]["other_maps"],
               r["hard_bars"]["npc_contacts"]), (1, ["prt_church"], 1))  # fmt: skip
    if table is None:  # skipped, not failed: the GPL-derived table is built locally at run time
        out.append({"case": "hunt v55: kills / economics / loot (SKIPPED: no item table)",
                    "got": None, "want": None, "ok": None})  # fmt: skip
        return out
    if not skip(HUNT):
        hunt(table, check)
    return out


Check = Any  # positive()'s check(case, got, want)


def live(loaded: tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]],
         table: Mapping[str, Mapping[str, Any]] | None, check: Check) -> None:  # fmt: skip
    """The parent's LIVE check (2026-10-22 11:3x, the Crusader on the Heal tree): one Heal Lv 8
    on self (sp 312 -> 278, hp +544 at the same tick), one sit -> stand (act sit / stand of ours;
    the requests arrive as attack_request kind sit / stand with OUR id as the target), natural
    regen every 3 s while sitting."""
    ev, pk, man = loaded
    r = judge(ev, pk, table, man)
    check("live sit-heal: Heals = 1, HP-confirmed (sp -34 and hp +544 at the same tick)",
          (r["heals"], r["heals_confirmed"]), (1, 1))  # fmt: skip
    check("live sit-heal: the runner's heal press vs the packets", r["runner_vs_packets"]["heal"],
          [1, 1])  # fmt: skip
    check("live sit-heal: one sit span (act sit -> stand) vs the sit press",
          r["runner_vs_packets"]["sit"], [1, 1])  # fmt: skip
    sit_s = (r.get("rest") or {}).get("sitting_seconds")
    check("live sit-heal: sitting seconds (act sit 739.72 -> stand 766.43 s: 26.7)", sit_s, 26.7)
    raw = sum(1 for e in pk if e.get("type") == "attack_request"
              and e.get("kind") in ("sit", "stand"))  # fmt: skip
    hb = r["hard_bars"]
    check("live sit-heal: 2 sit / stand requests, 0 counted as attack requests",
          (raw, hb["attack_requests_non_monster"], hb["attack_requests_unknown_target"]),
          (2, 0, 0))  # fmt: skip
    m = r["moving_hp_recovery"]
    check("live sit-heal: natural ticks while sitting (every 3 s: 9 in 26.7 s)",
          m["natural_while_sitting"], 9)  # fmt: skip


def regen(loaded: tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]],
          table: Mapping[str, Mapping[str, Any]] | None, check: Check) -> None:  # fmt: skip
    """3.96f's regen trial against regen_walk.judge, phase by phase (its own windows)."""
    import regen_walk as rw

    ev, pk, man = loaded
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


def hunt(table: Mapping[str, Mapping[str, Any]], check: Check) -> None:
    """v55 run 4 against econ_row + loot_complete on search_study's window."""
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


# --- the CLI -------------------------------------------------------------------------------------


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)  # fmt: skip
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("row", "table", "positive", "items"):
        p = sub.add_parser(name)
        if name != "positive":
            p.add_argument("sids", nargs="+" if name in ("table", "items") else 1)
            p.add_argument("--map", default=None, help="the run's map (default: run_start's)")
            p.add_argument(
                "--live",
                type=float,
                default=None,
                metavar="S",
                help="a human demo: his first input .. + S s (manifest t0_live_ns)",
            )
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
            rows.append(row(sid, table, a.map, maps, a.live))
        except (OSError, ValueError, KeyError) as e:  # reported, never a silent drop
            print(f"{sid}: skipped ({type(e).__name__}: {e})", file=sys.stderr)
    if not rows:
        return 1
    if a.cmd == "row":
        print(json.dumps(rows[0], indent=1, default=str))
        return 0
    if a.cmd == "items":  # Batt 2026-10-24: every item per hour, per run and pooled
        for r in rows:
            print(items_box(r["items"], f"{run_label(r)}  ({r['hours']:.2f} h)  steal "
                            f"{r['steal']}"))  # fmt: skip
        print(items_box(pool_items(rows), f"POOLED ({sum(r['hours'] for r in rows):.2f} h)"))
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
