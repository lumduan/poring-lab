#!/usr/bin/env python3
"""Per-arm judges for interleaved hunt-flow tests (Batt 2026-10-17; OFFLINE, packets as truth).

Every hunt-flow version since v29 interleaves its main change PER ENGAGEMENT; these tables compare
the arms from the banked session files (`/dev/shm/poring-lab-demo/<sid>/`: packets.jsonl.gz,
engagements.json, clicks.jsonl, and flow_judge.json -- run `flow_judge.bot(sid)` first).

    arm_judge.py strike SID [SID ...]   v29+ A / B / C strike arms (hov["arm_eff"])
    arm_judge.py dead SID [SID ...]     v32+ fast / slow dead rule (eng["dead_rule"])
    arm_judge.py loot SID [SID ...]     per kill: items picked / lost to LOOTERS / expired,
                                        by the loot arm (eng["loot_arm"], v33+) or "all"
    arm_judge.py stray SID [SID ...]    per loot step: the GM walked >= 4 cells off the death
                                        cell (the TREADMILL), by the loot arm
    arm_judge.py blocks SID [SID ...]   v34: the paced / default 10-min blocks (send_gap events)
    arm_judge.py species SID [SID ...]  v35: own-frame (odd k) vs stale-box (even k) species check
    arm_judge.py retry SID [SID ...]    v36: the loot retry (odd k) vs none (even k): item fates at
                                        our kills + the loot steps' clicks / skips / time
    arm_judge.py sword SID [SID ...]    v37: the cursor's SWORD check (odd k) vs none (even k):
                                        its verdicts and time, loot / walk clicks it stopped,
                                        non-target attack requests by the arm of the click before
    arm_judge.py heading SID [SID ...]  v38: the age-weighted search heading's 10-min blocks
                                        (heading_arm events) vs the v22 coverage heading:
                                        kills / h, kills per sighting, the search (search_study's
                                        ruler: no-target time, encounters per no-target minute,
                                        re-swept ground), landing, reversals; per-run differences
    arm_judge.py approach SID [SID ...] v39: the steer's route tail (odd k) vs none (even k): the
                                        GM's moving share while steering, its stops, steer s per
                                        engagement, the approach (steer start -> first click /
                                        -> within 3 cells), landing

Packets are offline ground truth here (ADR-0007); nothing in this module runs during play.
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
NS = 1_000_000_000
TARGET_JOBS = (1002, 1063, 1113, 1008)  # prt_fild08's spawn table (farm0.TARGETS)
EXPIRE_S = 55.0  # a floor item vanishing this long after it fell has expired (server: 60 s)
LOOTER_CELLS = 1  # a monster within this Chebyshev distance at an item's vanish took it


def q(v: Sequence[float], p: float) -> float | None:
    """The p-quantile (nearest rank, lower), rounded to 2; None when empty."""
    if not v:
        return None
    s = sorted(v)
    return round(s[int(p * (len(s) - 1))], 2)


def load(sid: str) -> dict[str, Any]:
    d = DEMO / sid
    with gzip.open(d / "packets.jsonl.gz", "rt") as fh:
        packets = sorted((json.loads(x) for x in fh), key=lambda e: int(e["t_mono_ns"]))
    clicks = sorted((json.loads(x) for x in (d / "clicks.jsonl").read_text().splitlines() if x),
                    key=lambda c: int(c["t"]))  # fmt: skip
    rows = json.loads((d / "flow_judge.json").read_text())["engagements_w"]["rows"]
    return {"sid": sid, "packets": packets, "clicks": clicks,
            "engagements": json.loads((d / "engagements.json").read_text()),
            "gid_by_k": {int(r["k"]): r.get("gid") for r in rows},
            "why_by_k": {int(r["k"]): r.get("why") for r in rows}}  # fmt: skip


# --- loot: where each dropped item went ----------------------------------------------------------


def item_fates(packets: Sequence[Mapping[str, Any]], pos: Mapping[int, Sequence[Any]],
               mob_at: Any) -> dict[int, dict[str, Any]]:  # fmt: skip
    """PURE: floor_id -> {t_fall, cell, fate, t_end}. fate: "picked" (our pickup answered ok),
    "looter" (vanished early, a monster within LOOTER_CELLS of it then), "gone" (vanished early,
    no monster near: another cause), "expired" (>= EXPIRE_S after the fall), "left" (still there
    at the end). ``pos`` / ``mob_at`` = hunt_core.walk_positions + flow_judge.mob_at."""
    items: dict[int, dict[str, Any]] = {}
    ours: set[int] = set()
    pend: int | None = None
    alive: set[int] = set()
    for e in packets:
        t = int(e["t_mono_ns"])
        typ = e.get("type")
        if typ == "entity_appear" and e.get("objtype") == 5 and e.get("gid") is not None:
            alive.add(int(e["gid"]))
        elif typ == "entity_vanish" and e.get("gid") is not None:
            alive.discard(int(e["gid"]))
        elif typ == "floor_item_appear" and e.get("kind") == "fall":
            items[int(e["floor_id"])] = {"t_fall": t, "cell": (int(e["x"]), int(e["y"])),
                                         "fate": "left", "t_end": None}  # fmt: skip
        elif typ == "pickup_request":
            pend = int(e["floor_id"])
        elif typ == "pickup_result" and pend is not None:
            if e.get("ok"):
                ours.add(pend)
            pend = None
        elif typ == "floor_item_vanish":
            f = int(e["floor_id"])
            it = items.get(f)
            if it is None or it["t_end"] is not None:
                continue
            it["t_end"] = t
            if f in ours:
                it["fate"] = "picked"
            elif (t - it["t_fall"]) / NS >= EXPIRE_S:
                it["fate"] = "expired"
            else:
                near = [g for g in alive if (c := mob_at(pos, g, t)) is not None
                        and max(abs(c[0] - it["cell"][0]), abs(c[1] - it["cell"][1]))
                        <= LOOTER_CELLS]  # fmt: skip
                it["fate"] = "looter" if near else "gone"
    for f in ours:  # a pickup can be answered after the vanish line in the archive order
        if f in items:
            items[f]["fate"] = "picked"
    return items


def kills_of(packets: Sequence[Mapping[str, Any]], gm: int = 2000002) -> list[tuple[int, int]]:
    """PURE: [(t_vanish, gid)] of mobs that died (reason 1) <= 1.5 s after our damaging act."""
    hit: dict[int, int] = {}
    out = []
    for e in packets:
        t = int(e["t_mono_ns"])
        if e.get("type") == "act" and e.get("src_gid") == gm and int(e.get("damage") or 0) > 0:
            hit[int(e.get("target_gid") or -1)] = t
        elif (e.get("type") == "entity_vanish" and int(e.get("reason", -1)) == 1
              and t - hit.get(int(e.get("gid") or -1), -(10**18)) <= 1.5 * NS):  # fmt: skip
            out.append((t, int(e["gid"])))
    return out


def drops_of_kill(items: Mapping[int, Mapping[str, Any]], t_kill: int,
                  cell: tuple[int, int] | None) -> list[int]:  # fmt: skip
    """PURE: the floor ids that fell for a kill at ``t_kill`` (the drop comes ~0.25 s before the
    vanish: -0.6 .. +1.5 s), within 4 cells of the dead mob's ``cell`` when known."""
    return [f for f, it in items.items()
            if t_kill - 0.6 * NS <= it["t_fall"] <= t_kill + 1.5 * NS
            and (cell is None or max(abs(it["cell"][0] - cell[0]),
                                     abs(it["cell"][1] - cell[1])) <= 4)]  # fmt: skip


# --- the tables -----------------------------------------------------------------------------------


def strike_table(sessions: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """v29+ A / B / C: per EFFECTIVE arm (planned B / C that fell back count as A)."""
    arms: dict[str, dict[str, list[Any]]] = defaultdict(lambda: defaultdict(list))
    planned: Counter[str] = Counter()
    fallbacks: Counter[str] = Counter()
    for s in sessions:
        req: dict[int, list[int]] = defaultdict(list)
        anyreq: list[tuple[int, int]] = []
        walks: list[int] = []
        van: dict[int, list[int]] = defaultdict(list)
        for e in s["packets"]:
            t = int(e["t_mono_ns"])
            typ = e.get("type")
            if typ == "attack_request":
                req[int(e.get("target_gid") or -1)].append(t)
                anyreq.append((t, int(e.get("target_gid") or -1)))
            elif typ == "self_move_request":
                walks.append(t)
            elif typ == "entity_vanish" and int(e.get("reason", -1)) == 1:
                van[int(e.get("gid") or -1)].append(t)
        ats = [a[0] for a in anyreq]
        for x in s["engagements"]:
            h0 = next((h for h in x.get("hovers", []) if h.get("arm")), None)
            if h0 is None:
                continue
            planned[h0["arm"]] += 1
            if h0.get("fallback"):
                fallbacks[f"{h0['arm']}:{h0['fallback']}"] += 1
            m = arms[h0.get("arm_eff") or "A"]
            g = s["gid_by_k"].get(int(x["k"]))
            ta, tc = int(h0["t_arrive"]), int(h0["clicked"])
            m["n"].append(1)
            m["arrive_click"].append((tc - ta) / NS)
            if g is not None:
                rs = [t for t in req.get(g, []) if ta <= t <= ta + 6 * NS]
                if rs:
                    m["arrive_req"].append((rs[0] - ta) / NS)
                vs = [t for t in van.get(g, []) if ta <= t <= ta + 10 * NS]
                if vs:
                    m["arrive_kill"].append((vs[0] - ta) / NS)
            m["land5"].append(s["why_by_k"].get(int(x["k"])) == "hit")
            i = bisect.bisect_left(ats, tc)
            nxt = anyreq[i] if i < len(anyreq) and anyreq[i][0] - tc <= 1.5 * NS else None
            if nxt and nxt[1] == g:
                m["first_target"].append(1)
            elif nxt:
                m["first_other"].append(1)
            elif any(0 <= w - tc <= 1.5 * NS for w in walks):
                m["first_ground"].append(1)
            else:
                m["first_none"].append(1)
    out: dict[str, Any] = {"planned": dict(planned), "fallbacks": dict(fallbacks), "arms": {}}
    for arm in sorted(arms):
        m = arms[arm]
        n = len(m["n"])
        out["arms"][arm] = {
            "n": n, "arrive_click_p50": q(m["arrive_click"], 0.5),
            "arrive_req_p50_p90": [q(m["arrive_req"], 0.5), q(m["arrive_req"], 0.9)],
            "landing": round(sum(m["land5"]) / n, 3) if n else None,
            "first_click": {k_: len(m[f"first_{k_}"]) for k_ in ("target", "other", "ground",
                                                                 "none")},
            "arrive_kill_p50": q(m["arrive_kill"], 0.5)}  # fmt: skip
    return out


def dead_table(sessions: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """v32+: per dead-rule arm -- server kill -> the loot step's start, false deaths (called dead,
    no server vanish of the target within [last click - 1 s, the end + 3 s]), death -> the NEXT
    ENGAGEMENT's first click (search included)."""
    arms: dict[str, dict[str, list[Any]]] = defaultdict(lambda: defaultdict(list))
    for s in sessions:
        van: dict[int, list[int]] = defaultdict(list)
        for e in s["packets"]:
            if e.get("type") == "entity_vanish" and int(e.get("reason", -1)) == 1:
                van[int(e.get("gid") or -1)].append(int(e["t_mono_ns"]))
        firsts = sorted(int(x["t_first_click"]) for x in s["engagements"])
        for x in s["engagements"]:
            if x.get("result") != "dead":
                continue
            m = arms[x.get("dead_rule") or "none"]
            m["n"].append(1)
            g = s["gid_by_k"].get(int(x["k"]))
            t_end = int(x.get("t_end") or 0)
            if g is None:
                m["no_gid"].append(1)
                continue
            t0 = int(x.get("t_last_click") or x["t_first_click"]) - NS
            vs = [t for t in van.get(g, []) if t0 <= t <= t_end + 3 * NS]
            if not vs:
                m["false"].append(1)
                continue
            loot = x.get("loot") or {}
            if loot.get("s") is not None and t_end:
                m["kill_to_loot_end"].append((t_end - vs[0]) / NS)
                m["kill_to_loot_start"].append((t_end - vs[0]) / NS - float(loot["s"]))
            i = bisect.bisect_right(firsts, t_end)
            if i < len(firsts):
                m["death_to_next_eng"].append((firsts[i] - vs[0]) / NS)
    out = {}
    for arm in sorted(arms):
        m = arms[arm]
        judged = len(m["n"]) - len(m["no_gid"])
        out[arm] = {"dead": len(m["n"]), "false": len(m["false"]),
                    "false_share": round(len(m["false"]) / judged, 3) if judged else None,
                    "kill_to_loot_start_p50_p90": [q(m["kill_to_loot_start"], 0.5),
                                                   q(m["kill_to_loot_start"], 0.9)],
                    "death_to_next_engagement_p50": q(m["death_to_next_eng"], 0.5)}  # fmt: skip
    return out


def loot_table(sessions: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """Per loot arm (eng["loot_arm"], else "all"): the fates of the items that fell at OUR kills,
    matched to the engagement whose target died."""
    import flow_judge as fj
    import hunt_core as hc

    arms: dict[str, Counter[str]] = defaultdict(Counter)
    for s in sessions:
        pos = hc.walk_positions(s["packets"])
        items = item_fates(s["packets"], pos, fj.mob_at)
        kills = dict((g, t) for t, g in kills_of(s["packets"]))
        for x in s["engagements"]:
            g = s["gid_by_k"].get(int(x["k"]))
            if x.get("result") != "dead" or g is None or g not in kills:
                continue
            t_k = kills[g]
            cell = fj.mob_at(pos, g, t_k - 1)
            c = arms[str(x.get("loot_arm") or "all")]
            c["kills"] += 1
            for f in drops_of_kill(items, t_k, cell):
                c["items"] += 1
                c[items[f]["fate"]] += 1
    return {arm: dict(c) for arm, c in sorted(arms.items())}


def loot_stray(loot_steps: Iterable[Mapping[str, Any]],
               packets: Sequence[Mapping[str, Any]], far: int = 4) -> dict[str, Any]:  # fmt: skip
    """PURE (the loot TREADMILL, 2026-10-17 22:0x): per loot step (a ``loot_fixed`` event: its end
    ``t_ns``, its duration ``s``, its death ``cell``) the farthest server destination of the GM's
    walks (self_move x1 / y1) from the death cell during the step (+ 0.5 s). A 3 x 3 loot never
    needs >= 2; >= ``far`` cells means the clicks walked the GM off its pile."""
    mv = [(int(e["t_mono_ns"]), (int(e["x1"]), int(e["y1"])))
          for e in packets if e.get("type") == "self_move"]  # fmt: skip
    n = strays = 0
    worst: list[int] = []
    for e in loot_steps:
        t1 = int(e["t_ns"])
        t0 = t1 - int(float(e.get("s") or 0.0) * 1e9)
        c = e["cell"]
        ds = [max(abs(p[0] - c[0]), abs(p[1] - c[1])) for t, p in mv if t0 <= t <= t1 + 500_000_000]
        n += 1
        if ds:
            worst.append(max(ds))
            strays += max(ds) >= far
    worst.sort()
    return {"steps": n, f"stray_ge_{far}": strays,
            "share": round(strays / n, 3) if n else None,
            "max_p50": worst[len(worst) // 2] if worst else None}  # fmt: skip


def loot_stray_clicks(
    loot_steps: Iterable[Mapping[str, Any]],
    clicks: Sequence[Mapping[str, Any]],
    packets: Sequence[Mapping[str, Any]],
    far: int = 4,
) -> dict[str, Any]:
    """PURE (the CORRECTED treadmill measure, 2026-10-18 00:33): per loot step, the farthest
    server destination that answers one of ITS LOOT CLICKS (the first self_move <= 0.6 s after
    the click and before our next click) from the death cell. ``loot_stray``'s window (the step
    + 0.5 s) also caught the bot's NEXT search / steer walk, sent right after the step: it
    overstated the treadmill (v28-v31 62-77 % by the window, 31-48 % by the clicks)."""
    mv = [(int(e["t_mono_ns"]), (int(e["x1"]), int(e["y1"])))
          for e in packets if e.get("type") == "self_move"]  # fmt: skip
    mt = [t for t, _p in mv]
    cl = sorted(clicks, key=lambda c: int(c["t"]))
    ct = [int(c["t"]) for c in cl]
    n = strays = 0
    worst_all: list[int] = []
    for e in loot_steps:
        t1 = int(e["t_ns"])
        t0 = t1 - int(float(e.get("s") or 0.0) * 1e9)
        dc = e["cell"]
        worst = -1
        for i in range(bisect.bisect_left(ct, t0), bisect.bisect_right(ct, t1)):
            if cl[i].get("kind") != "loot":
                continue
            nxt = ct[i + 1] if i + 1 < len(ct) else 1 << 62
            j = bisect.bisect_left(mt, ct[i])
            if j < len(mv) and mv[j][0] - ct[i] <= 600_000_000 and mv[j][0] < nxt:
                d = mv[j][1]
                worst = max(worst, max(abs(d[0] - dc[0]), abs(d[1] - dc[1])))
        n += 1
        if worst >= 0:
            worst_all.append(worst)
            strays += worst >= far
    worst_all.sort()
    return {"steps": n, f"stray_ge_{far}": strays,
            "share": round(strays / n, 3) if n else None,
            "max_p50": worst_all[len(worst_all) // 2] if worst_all else None}  # fmt: skip


def stray_table(sessions: Iterable[dict[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for s in sessions:
        ev = [json.loads(x) for x in (DEMO / s["sid"] / "events.jsonl").read_text().splitlines()
              if x]  # fmt: skip
        by: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for e in ev:
            if e.get("kind") == "loot_fixed":
                by[str(e.get("arm") or "all")].append(e)
        out[s["sid"]] = {arm: {"clicks (corrected)": loot_stray_clicks(st, s["clicks"],
                                                                        s["packets"]),
                               "window (pre-registered, overstated)": loot_stray(st, s["packets"])}
                         for arm, st in sorted(by.items())}  # fmt: skip
    return out


def arm_spans(events: Sequence[Mapping[str, Any]]) -> list[tuple[int, int, bool]]:
    """PURE (v34): the run's paced / default spans [(t0, t1, paced)] from its ``send_gap``
    events, the last one closed by the last event."""
    marks = [(int(e["t_ns"]), bool(e["on"])) for e in events if e.get("kind") == "send_gap"]
    if not marks:
        return []
    t_end = int(events[-1]["t_ns"])
    return [(t, marks[i + 1][0] if i + 1 < len(marks) else t_end, on)
            for i, (t, on) in enumerate(marks)]  # fmt: skip


def blocks_table(sessions: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """v34's time-blocked arms (paced / default): minutes, server kills (ours) per hour,
    engagements, landing within the judge's window, first click -> hit p50, clicks per minute by
    kind, loot items picked / fell."""
    import flow_judge as fj
    import hunt_core as hc

    agg: dict[str, Counter[str]] = defaultdict(Counter)
    hits: dict[str, list[float]] = defaultdict(list)
    loot_s: dict[str, list[float]] = defaultdict(list)
    for s in sessions:
        ev = [json.loads(x) for x in (DEMO / s["sid"] / "events.jsonl").read_text().splitlines()
              if x]  # fmt: skip
        spans = arm_spans(ev)
        kills = [t for t, _g in kills_of(s["packets"])]
        rows = {
            int(r_["k"]): r_
            for r_ in json.loads((DEMO / s["sid"] / "flow_judge.json").read_text())[
                "engagements_w"
            ]["rows"]
        }
        pos = hc.walk_positions(s["packets"])
        items = item_fates(s["packets"], pos, fj.mob_at)
        req_t = sorted(int(e["t_mono_ns"]) for e in s["packets"]
                       if e.get("type") == "self_move_request")  # fmt: skip
        for t0, t1, on in spans:
            a = agg["paced" if on else "default"]
            a["seconds"] += (t1 - t0) // NS
            a["kills"] += sum(t0 <= t < t1 for t in kills)
            for x in s["engagements"]:
                if t0 <= int(x["t_first_click"]) < t1:
                    a["engagements"] += 1
                    r_ = rows.get(int(x["k"])) or {}
                    a["landed"] += r_.get("why") == "hit"
                    if r_.get("why") == "hit" and r_.get("t_hit_s") is not None:
                        hits["paced" if on else "default"].append(float(r_["t_hit_s"]))
            for c in s["clicks"]:
                if t0 <= int(c["t"]) < t1:
                    a[f"clicks_{c.get('kind')}"] += 1
                    if c.get("kind") == "walk":  # did the client act on it within 1 s?
                        j = bisect.bisect_left(req_t, int(c["t"]))
                        a["walk_followed"] += j < len(req_t) and req_t[j] - int(c["t"]) <= NS
            for e in ev:
                if e.get("kind") == "loot_fixed" and t0 <= int(e["t_ns"]) < t1:
                    loot_s["paced" if on else "default"].append(float(e["s"]))
                    a["loot_clicks"] += int(e.get("clicks") or 0)
            for it in items.values():
                if t0 <= int(it["t_fall"]) < t1:
                    a["items"] += 1
                    a["picked"] += it["fate"] == "picked"
    out: dict[str, Any] = {}
    for arm, a in sorted(agg.items()):
        mins = a["seconds"] / 60.0
        hs = sorted(hits[arm])
        out[arm] = {
            "minutes": round(mins, 1), "kills": a["kills"],
            "kills_per_hour": round(a["kills"] * 60.0 / mins, 1) if mins else None,
            "engagements": a["engagements"],
            "landed": f"{a['landed']}/{a['engagements']}",
            "click_to_hit_p50": hs[len(hs) // 2] if hs else None,
            "clicks_per_min": {k[7:]: round(v / mins, 1) for k, v in sorted(a.items())
                               if k.startswith("clicks_") and mins},
            "loot": f"{a['picked']}/{a['items']}",
            "loot_step_s_p50": q(loot_s[arm], 0.5),
            "loot_s_per_click": (round(sum(loot_s[arm]) / a["loot_clicks"], 3)
                                 if a["loot_clicks"] else None),
            "walk_followed": f"{a['walk_followed']}/{a['clicks_walk']}",
        }  # fmt: skip
    return out


def heading_spans(events: Sequence[Mapping[str, Any]],
                  block_min: float = 10.0) -> list[tuple[int, int, bool]]:  # fmt: skip
    """PURE (v38): the run's 10-min CLOCK blocks [(t0, t1, age_on)]. The runner sets the block
    clock at its first ``heading_arm`` event (block 0) and logs each block's arm at the first
    re-plan inside it, so block b is [T0 + b L, T0 + (b + 1) L); a block without its own event
    takes the alternation (the arm flips every block). The last block ends at the last event."""
    marks = [(int(e["t_ns"]), int(e["block"]), bool(e["on"])) for e in events
             if e.get("kind") == "heading_arm"]  # fmt: skip
    if not marks:
        return []
    t_a, b_a, on_a = marks[0]
    if b_a != 0:
        raise ValueError(f"the first heading_arm is block {b_a}, not 0")
    on_by = {b: on for _t, b, on in marks}
    for b, on in on_by.items():
        if on != (on_a if b % 2 == 0 else not on_a):
            raise ValueError(f"block {b}: arm {on} breaks the alternation")
    span = int(block_min * 60 * NS)
    t_end = int(events[-1]["t_ns"])
    out = []
    b = 0
    while t_a + b * span < t_end:
        out.append((t_a + b * span, min(t_a + (b + 1) * span, t_end),
                    on_a if b % 2 == 0 else not on_a))  # fmt: skip
        b += 1
    return out


def slice_scan(sc: Any, a: int, z: int, kills: int) -> Any:
    """search_study.Scan's samples in [a, z) of ONE whole-run scan (so re-sweeps across blocks
    keep their history); the age tables are not sliced."""
    import search_study as ss

    m = (sc.t >= a) & (sc.t < z)
    return ss.Scan(t=sc.t[m], x=sc.x[m], y=sc.y[m], moving=sc.moving[m],
                   n_targets=sc.n_targets[m], new=sc.new[m], reswept=sc.reswept[m],
                   dt_s=sc.dt_s, kills=kills)  # fmt: skip


def heading_table(sids: Iterable[str], spans_of: Any = None) -> dict[str, Any]:
    """v38 per arm ("age" = the age-weighted heading, "cov" = v22's): the arm's minutes, our
    server kills per hour, monsters in sight per 10 min (each block is a 10-min window: the
    duration-weighted mean, the windowed ruler), KILLS PER SIGHTING, the search (presence /
    sweep on one whole-run scan sliced by block), reversals per minute, landing within the
    judge's window (by first click); and per run the relative block difference (age - cov) /
    the run's mean, for kills / h and encounters per no-target minute. ``spans_of(session)``
    replaces the blocks (a test's, or a null split of an older run)."""
    import flow_judge as fj
    import search_study as ss

    by: dict[str, dict[str, Any]] = {
        arm: {"secs": 0.0, "kills": 0, "sight_w": 0.0, "scans": [], "rev": 0, "walked": 0,
              "eng": 0, "landed": 0, "blocks": 0}
        for arm in ("age", "cov")
    }  # fmt: skip
    per_run: dict[str, Any] = {}
    for sid in sids:
        sess = ss.load_session(sid)
        spans = spans_of(sess) if spans_of is not None else heading_spans(sess.bot_events)
        fld = ss.Field(sess.events)
        whole = ss.scan(fld, sess.t0, sess.w1, ss.load_walkable(sess.map_name))
        fjr = json.loads((DEMO / sid / "flow_judge.json").read_text())
        rows = {int(r_["k"]): r_ for r_ in fjr["engagements_w"]["rows"]}
        blk: dict[str, list[dict[str, float]]] = {"age": [], "cov": []}
        for t0, t1, on in spans:
            a, z = max(t0, sess.t0), min(t1, sess.w1)
            if z - a < 60 * NS:  # under a minute inside the judged window
                continue
            arm = "age" if on else "cov"
            g = by[arm]
            secs = (z - a) / NS
            kills = len(ss.kill_times(sess.events, a, z))
            sight = fj.sight_per_10min(sess.events, a, z)
            g["secs"] += secs
            g["kills"] += kills
            g["blocks"] += 1
            g["sight_w"] += sight * secs
            sl = slice_scan(whole, a, z, kills)
            g["scans"].append(sl)
            _runs, rev, walked = ss.straight_runs(fld, a, z)
            g["rev"] += rev
            g["walked"] += walked
            for x in sess.engagements:
                if a <= int(x["t_first_click"]) < z:
                    g["eng"] += 1
                    g["landed"] += (rows.get(int(x["k"])) or {}).get("why") == "hit"
            swb = ss.sweep_summary(sl)
            blk[arm].append({
                "block": (t0 - spans[0][0]) // (600 * NS), "kills_per_hour": kills * 3600 / secs,
                "sight_per_10min": sight,
                "encounters_per_none_min": ss.presence_summary([sl])["encounters_per_none_min"],
                "reswept_120s": swb["reswept_share"]["<=120s"],
                "fresh_per_min": float(swb["fresh_per_min"])})  # fmt: skip
        names = ("kills_per_hour", "sight_per_10min", "encounters_per_none_min", "reswept_120s",
                 "fresh_per_min")  # fmt: skip
        run: dict[str, Any] = {"block_rows": sorted(
            ({"arm": arm, **{k_: round(v_, 3) for k_, v_ in r_.items()}}
             for arm, rs in blk.items() for r_ in rs), key=lambda r_: r_["block"])}  # fmt: skip
        for name in names:
            on_ = [r_[name] for r_ in blk["age"]]
            off = [r_[name] for r_ in blk["cov"]]
            if on_ and off:
                mean = sum(on_ + off) / len(on_ + off)
                run[name] = {"age": round(sum(on_) / len(on_), 3),
                             "cov": round(sum(off) / len(off), 3),
                             "rel_diff": round((sum(on_) / len(on_) - sum(off) / len(off))
                                               / max(1e-9, mean), 3)}  # fmt: skip
        run["blocks"] = {arm: len(v) for arm, v in blk.items()}
        per_run[sid] = run
    out: dict[str, Any] = {"per_run": per_run}
    for arm, g in by.items():
        if not g["secs"]:
            continue
        mins = g["secs"] / 60
        kph = g["kills"] * 3600 / g["secs"]
        sight = g["sight_w"] / g["secs"]
        pres = ss.presence_summary(g["scans"])
        sw = ss.sweep_summary(ss.merge_scans(g["scans"]))
        out[arm] = {
            "blocks": g["blocks"], "minutes": round(mins, 1), "kills": g["kills"],
            "kills_per_hour": round(kph, 1), "sight_per_10min": round(sight, 1),
            "kills_per_sighting": ss.kills_per_sighting(kph, sight),
            "encounters_per_none_min": pres["encounters_per_none_min"],
            "none_s_per_kill": pres["none_s_per_kill"],
            "some_s_per_kill": pres["some_s_per_kill"],
            "stretch_mean_s": pres["stretch_mean_s"],
            "stretches_per_kill": pres["stretches_per_kill"],
            "reswept_120s": sw["reswept_share"]["<=120s"], "fresh_per_min": sw["fresh_per_min"],
            "reversals_per_min": round(g["rev"] / mins, 2),
            "cells_walked_per_min": round(g["walked"] / mins, 1),
            "landing": f"{g['landed']}/{g['eng']}",
            "landing_share": round(g["landed"] / g["eng"], 3) if g["eng"] else None,
        }  # fmt: skip
    return out


def mode_spans(events: Sequence[Mapping[str, Any]], mode: str, w0: int,
               w1: int) -> list[tuple[int, int]]:  # fmt: skip
    """PURE: the [a, b) spans the runner spent in ``mode`` (its ``mode`` events; a span ends at
    the next one, or at w1), clipped to [w0, w1); empty spans dropped."""
    ms = sorted((int(e["t_ns"]), str(e["mode"])) for e in events if e.get("kind") == "mode")
    out = []
    for i, (t, m) in enumerate(ms):
        if m != mode:
            continue
        a, b = max(t, w0), min(ms[i + 1][0] if i + 1 < len(ms) else w1, w1)
        if b > a:
            out.append((a, b))
    return out


def k_at(first_clicks: Sequence[int], t: int) -> int:
    """PURE: the engagement the bot works toward at t = the engagements created (their first
    clicks, sorted) before t. The runner creates engagement k at its first attack click and the
    engaged branch never steers, so every steer belongs to the next engagement's k."""
    return bisect.bisect_left(first_clicks, t)


def approach_table(sids: Iterable[str], on_of: Any = None,
                   sample_s: float = 0.1) -> dict[str, Any]:  # fmt: skip
    """v39 per arm ("tail" = odd k: the steer's walk click may take the route's tail, the
    standstill fallback steps from the nearest route point; "base" = even k), from packets
    (search_study.Field) on flow_judge's window:
    - STEER time (the runner's ``mode`` spans), each span by ``k_at`` its start: seconds, the
      GM's MOVING share (``sample_s`` samples), its stops (moving -> standing) per steer minute,
      steer seconds per engagement;
    - per engagement: the APPROACH = the start of the last steer span after the previous
      engagement's end -> its first click, and -> our GM within 3 cells (Chebyshev, packet
      cells) of the attacked gid (flow_judge's join), with the moving share over that stretch;
      landing (flow_judge's why == "hit") and kills.
    ``on_of(k)`` replaces the arm rule (a null split of older runs). Per run: the arms'
    relative differences (tail - base) / mean."""
    import conversion_phases as cp
    import search_study as ss

    on = on_of or (lambda k_: k_ % 2 == 1)
    dt = int(sample_s * NS)
    arms = ("tail", "base")
    tot: dict[str, Counter[str]] = {arm: Counter() for arm in arms}
    lst: dict[str, dict[str, list[float]]] = {arm: defaultdict(list) for arm in arms}
    per_run: dict[str, Any] = {}
    for sid in sids:
        sess = ss.load_session(sid)
        fld = ss.Field(sess.events)
        engs = sorted(sess.engagements, key=lambda x: int(x["t_first_click"]))
        fcs = [int(x["t_first_click"]) for x in engs]
        rows = {int(r_["k"]): r_ for r_ in json.loads(
            (DEMO / sid / "flow_judge.json").read_text())["engagements_w"]["rows"]}  # fmt: skip
        spans = mode_spans(sess.bot_events, "steer", sess.t0, sess.w1)
        rt: dict[str, Counter[str]] = {arm: Counter() for arm in arms}
        rl: dict[str, dict[str, list[float]]] = {arm: defaultdict(list) for arm in arms}
        for a, b in spans:
            arm = "tail" if on(k_at(fcs, a)) else "base"
            mv = [fld.is_moving(t) for t in range(a, b, dt)]
            for c in (rt[arm], tot[arm]):
                c["steer_ns"] += b - a
                c["samples"] += len(mv)
                c["moving"] += sum(mv)
                c["stops"] += sum(1 for i in range(1, len(mv)) if mv[i - 1] and not mv[i])
        for i, x in enumerate(engs):
            fc, k = fcs[i], int(x["k"])
            if not sess.t0 <= fc < sess.w1:
                continue
            arm = "tail" if on(k) else "base"
            prev = int(engs[i - 1].get("t_end") or fcs[i - 1]) if i else sess.t0
            row = rows.get(k) or {}
            got: dict[str, float] = {}
            st = [a for a, _b in spans if prev <= a < fc]
            if st:
                s0 = st[-1]
                got["approach_s"] = (fc - s0) / NS
                g = row.get("gid")
                t3 = (None if g is None
                      else cp.first_within(fld, int(g), s0, fc + 5 * NS, 3))  # fmt: skip
                if t3 is not None:
                    got["to3_s"] = (t3 - s0) / NS
                    if t3 - s0 >= dt:
                        ts_ = range(s0, t3, dt)
                        got["moving_to3"] = sum(fld.is_moving(t) for t in ts_) / len(ts_)
            for c in (rt[arm], tot[arm]):
                c["eng"] += 1
                c["landed"] += row.get("why") == "hit"
                c["kills"] += x.get("result") == "dead"
                c["no_steer"] += not st
            for name, v in got.items():
                rl[arm][name].append(v)
                lst[arm][name].append(v)
        per_run[sid] = _approach_rel(_approach_arms(rt, rl))
    out: dict[str, Any] = {"per_run": per_run, **_approach_arms(tot, lst)}
    return out


def _approach_arms(tot: Mapping[str, Counter[str]],
                   lst: Mapping[str, Mapping[str, list[float]]]) -> dict[str, Any]:  # fmt: skip
    out: dict[str, Any] = {}
    for arm, c in tot.items():
        if not c["eng"] and not c["samples"]:
            continue
        steer_min = c["steer_ns"] / NS / 60
        ls = lst[arm]

        def mean(v: Sequence[float]) -> float | None:
            return round(sum(v) / len(v), 3) if v else None

        out[arm] = {
            "steer_min": round(steer_min, 1),
            "steer_moving_share": round(c["moving"] / c["samples"], 3) if c["samples"] else None,
            "stops_per_steer_min": round(c["stops"] / steer_min, 2) if steer_min else None,
            "steer_s_per_engagement": (round(c["steer_ns"] / NS / c["eng"], 2)
                                       if c["eng"] else None),
            "engagements": c["eng"], "kills": c["kills"], "no_steer": c["no_steer"],
            "landing": f"{c['landed']}/{c['eng']}",
            "landing_share": round(c["landed"] / c["eng"], 3) if c["eng"] else None,
            "approach_s_p50": q(ls.get("approach_s", []), 0.5),
            "approach_s_mean": mean(ls.get("approach_s", [])),
            "to3_n": len(ls.get("to3_s", [])),
            "to3_s_p50": q(ls.get("to3_s", []), 0.5),
            "to3_s_mean": mean(ls.get("to3_s", [])),
            "moving_to3_mean": mean(ls.get("moving_to3", [])),
        }  # fmt: skip
    return out


def _approach_rel(arms: dict[str, Any]) -> dict[str, Any]:
    """Per run: the arms and (tail - base) / their mean for the deciding measures."""
    out: dict[str, Any] = {"arms": arms}
    t, b = arms.get("tail"), arms.get("base")
    if t and b:
        for name in ("steer_moving_share", "steer_s_per_engagement", "approach_s_mean",
                     "to3_s_mean", "landing_share"):  # fmt: skip
            x, y = t.get(name), b.get(name)
            if x is not None and y is not None and x + y:
                out[f"rel_{name}"] = round((x - y) / ((x + y) / 2), 3)
    return out


def species_table(sessions: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """v35: per engagement parity (odd k = the species check on the box's OWN frame, even k =
    the fresh crop at the stale box): arm C's eligibility (the ``abc`` events: effective arm,
    fallback reasons) and landing within the judge's window."""
    agg: dict[str, Counter[str]] = defaultdict(Counter)
    for s in sessions:
        ev = [json.loads(x) for x in (DEMO / s["sid"] / "events.jsonl").read_text().splitlines()
              if x]  # fmt: skip
        for e in ev:
            if e.get("kind") != "abc":
                continue
            a = agg["own" if int(e["k"]) % 2 == 1 else "stale"]
            a["strikes"] += 1
            a[f"arm_{e.get('arm_eff')}"] += 1
            if e.get("fallback"):
                a[f"fallback_{e['fallback']}"] += 1
        for k, why in s["why_by_k"].items():
            a = agg["own" if k % 2 == 1 else "stale"]
            a["engagements"] += 1
            a["landed"] += why == "hit"
    out: dict[str, Any] = {}
    for arm, a in sorted(agg.items()):
        n = a["strikes"]
        out[arm] = {**dict(sorted(a.items())),
                    "effective_C_share": round(a["arm_C"] / n, 3) if n else None,
                    "unsure_share": round(a["fallback_species_unsure"] / n, 3) if n else None,
                    "landing": f"{a['landed']}/{a['engagements']}"}  # fmt: skip
    return out


def retry_table(sessions: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """v36: per engagement parity (odd k = the LOOT RETRY arm, even k = none): the fates of the
    items that fell at OUR kills (as ``loot_table``) and the loot steps themselves -- clicks,
    unit skips, retries queued / clicked / skipped again, step time."""
    import flow_judge as fj
    import hunt_core as hc

    agg: dict[str, Counter[str]] = defaultdict(Counter)
    step_s: dict[str, list[float]] = defaultdict(list)
    for s in sessions:
        pos = hc.walk_positions(s["packets"])
        items = item_fates(s["packets"], pos, fj.mob_at)
        kills = dict((g, t) for t, g in kills_of(s["packets"]))
        for x in s["engagements"]:
            arm = "retry" if int(x["k"]) % 2 == 1 else "none"
            a = agg[arm]
            lo = x.get("loot") or {}
            if lo:
                a["steps"] += 1
                a["clicks"] += int(lo.get("clicks") or 0)
                a["unit_skips"] += int((lo.get("skipped") or {}).get("unit", 0))
                a["retry_queued"] += int(lo.get("retry_queued") or 0)
                a["retry_clicks"] += int(lo.get("retry_clicks") or 0)
                a["retry_skipped"] += sum((lo.get("retry_skipped") or {}).values())
                a["steps_ge6_unit_skips"] += int((lo.get("skipped") or {}).get("unit", 0)) >= 6
                if lo.get("s") is not None:
                    step_s[arm].append(float(lo["s"]))
            g = s["gid_by_k"].get(int(x["k"]))
            if x.get("result") != "dead" or g is None or g not in kills:
                continue
            t_k = kills[g]
            a["kills"] += 1
            for f in drops_of_kill(items, t_k, fj.mob_at(pos, g, t_k - 1)):
                a["items"] += 1
                a[f"item_{items[f]['fate']}"] += 1
    out: dict[str, Any] = {}
    for arm, a in sorted(agg.items()):
        out[arm] = {**dict(sorted(a.items())),
                    "picked_share": round(a["item_picked"] / a["items"], 3) if a["items"] else None,
                    "step_s_p50": q(step_s[arm], 0.5)}  # fmt: skip
    return out


def sword_table(sessions: Iterable[dict[str, Any]],
                targets: Iterable[int] = TARGET_JOBS) -> dict[str, Any]:  # fmt: skip
    """v37: per arm ("sword" = odd k, the cursor check on; "none" = even k). From the clicks' own
    ``sw`` flag (loot and moving walk clicks) and the ``cursor_sword`` events: the checks'
    verdicts and ms, the loot steps (time, clicks, cursor skips), the walk clicks it refused, and
    the attack requests on NON-targets by the arm of the click just before (apart_why)."""
    import apart_why as aw

    agg: dict[str, Counter[str]] = defaultdict(Counter)
    ms: dict[str, list[float]] = defaultdict(list)
    step_s: dict[str, list[float]] = defaultdict(list)
    for s in sessions:
        ev = [json.loads(x) for x in (DEMO / s["sid"] / "events.jsonl").read_text().splitlines()
              if x]  # fmt: skip
        for x in s["engagements"]:
            arm = "sword" if int(x["k"]) % 2 == 1 else "none"
            a = agg[arm]
            a["engagements"] += 1
            a["landed"] += s["why_by_k"].get(int(x["k"])) == "hit"
            lo = x.get("loot") or {}
            if lo:
                a["loot_steps"] += 1
                a["loot_clicks"] += int(lo.get("clicks") or 0)
                for why, n in (lo.get("skipped") or {}).items():
                    a[f"loot_skip_{why}"] += int(n)
                if lo.get("s") is not None:
                    step_s[arm].append(float(lo["s"]))
        for e in ev:
            if e.get("kind") == "cursor_sword":
                a = agg["sword"]
                a[f"check_{e['where']}_{e['verdict']}"] += 1
                ms[f"{e['where']}"].append(float(e["ms"]))
            elif (e.get("kind") == "walk_click" and e.get("clicked") is False
                  and str(e.get("why", "")).startswith("cursor_")):  # fmt: skip
                agg["sword"]["walk_refused_" + str(e["why"])] += 1
        for c in s["clicks"]:
            if "sw" in c and c.get("kind") in ("walk", "loot"):
                agg["sword" if c["sw"] else "none"][f"clicks_{c['kind']}"] += 1
        for row in aw.classify(s["packets"], s["clicks"], targets):
            i = bisect.bisect_right([int(c["t"]) for c in s["clicks"]], row["t"]) - 1
            c = s["clicks"][i] if i >= 0 else {}
            arm = "sword" if c.get("sw") else "none" if "sw" in c else "other"
            agg[arm][f"nontarget_{row['job']}_{row['kind']}"] += 1
            agg[arm]["nontarget_requests"] += 1
    out: dict[str, Any] = {}
    for arm, a in sorted(agg.items()):
        out[arm] = {**dict(sorted(a.items())),
                    "landing": f"{a['landed']}/{a['engagements']}",
                    "loot_step_s_p50": q(step_s[arm], 0.5)}  # fmt: skip
    out["check_ms"] = {w: {"n": len(v), "p50": q(v, 0.5), "p90": q(v, 0.9)}
                       for w, v in sorted(ms.items())}  # fmt: skip
    return out


def sword_precision(s: dict[str, Any], lag_s: float = 0.45) -> dict[str, Any]:
    """v37, OFFLINE: what was really at each cursor check's point. The point's cell (the camera on
    the GM's packet cell ``lag_s`` earlier: the frames lag the server ~0.5 s), and the nearest
    mob of ANY job then (packets). Per (where, verdict): n, a mob within 1 / 2 cells, and the jobs
    within 1 cell. A SWORD with no mob within 2 cells is a false sword; a CLEAR with a mob within
    1 cell a possible miss (the cursor resolves the sprite, not the cell)."""
    import flow_judge as fj
    import hunt_core as hc
    import hunt_flow as hf
    import walk5 as w5

    from poring_dataset import camera as cam
    from poring_dataset import gat as gatmod

    man = json.loads((DEMO / s["sid"] / "manifest.json").read_text())
    gat = gatmod.parse((cam.GAT_DIR / f"{man.get('map', 'prt_fild08')}.gat").read_bytes())
    cj = json.loads((hf.r.ROOT / "packages/poring_dataset/src/poring_dataset/camera_rdp.json")
                    .read_text())  # fmt: skip
    camera = cam.camera_from_json(cj["camera"])
    pos = hc.walk_positions(s["packets"])
    gm_pts, _mv = fj.gm_track(s["packets"])  # our GM (self_move), not in walk_positions
    seen_at: dict[int, list[tuple[int, bool]]] = defaultdict(list)  # (t, visible from then on)
    for p_ in s["packets"]:
        if p_.get("gid") is None or p_.get("type") not in ("entity_appear", "entity_vanish"):
            continue
        seen_at[int(p_["gid"])].append((int(p_["t_mono_ns"]), p_["type"] == "entity_appear"))

    def visible(gid: int, t: int) -> bool:
        st = [v for tt, v in seen_at.get(gid, ()) if tt <= t]
        return bool(st) and st[-1]

    ev = [json.loads(x) for x in (DEMO / s["sid"] / "events.jsonl").read_text().splitlines()
          if x]  # fmt: skip
    agg: dict[str, Counter[str]] = defaultdict(Counter)
    for e in ev:
        if e.get("kind") != "cursor_sword":
            continue
        t = int(e["t_ns"]) - int(e.get("ms", 0) * 1e6) - int(lag_s * NS)
        gm = fj.at(gm_pts, t)
        if gm is None:
            continue
        g = (int(round(gm[0])), int(round(gm[1])))
        w = w5.World(camera, gat, g)
        c = hf.nearest_cell_frac(w, (float(gm[0]), float(gm[1])), g, float(e["u"]), float(e["v"]))
        best, jobs = 99, []
        for gid, tr in pos.items():
            if gid == fj.GM or not visible(gid, t):
                continue
            m = fj.mob_at(pos, gid, t)
            if m is None:
                continue
            d = max(abs(m[0] - c[0]), abs(m[1] - c[1]))
            if d <= 1:
                jobs.append(tr[-1][2])
            best = min(best, d)
        a = agg[f"{e['where']}_{e['verdict']}"]
        a["n"] += 1
        a["mob_within_1"] += best <= 1
        a["mob_within_2"] += best <= 2
        for j in jobs:
            a[f"job_{j}"] += 1
    return {k: dict(v) for k, v in sorted(agg.items())}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)  # fmt: skip
    ap.add_argument("what", choices=("strike", "dead", "loot", "stray", "blocks", "species",
                                     "retry", "sword", "sword-precision", "heading",
                                     "approach"))  # fmt: skip
    ap.add_argument("sessions", nargs="+")
    a = ap.parse_args()
    if a.what == "heading":  # its own loader (search_study's windows and field)
        print(json.dumps(heading_table(a.sessions), indent=1, default=str))
        return 0
    if a.what == "approach":  # search_study's loader too
        print(json.dumps(approach_table(a.sessions), indent=1, default=str))
        return 0
    sessions = [load(s) for s in a.sessions]
    if a.what == "sword-precision":
        print(json.dumps({s["sid"]: sword_precision(s) for s in sessions}, indent=1))
        return 0
    fn = {
        "strike": strike_table,
        "dead": dead_table,
        "loot": loot_table,
        "stray": stray_table,
        "blocks": blocks_table,
        "species": species_table,
        "retry": retry_table,
        "sword": sword_table,
    }[a.what]
    print(json.dumps(fn(sessions), indent=1, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
