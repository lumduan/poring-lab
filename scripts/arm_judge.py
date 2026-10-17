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


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)  # fmt: skip
    ap.add_argument("what", choices=("strike", "dead", "loot", "stray", "blocks", "species",
                                     "retry"))  # fmt: skip
    ap.add_argument("sessions", nargs="+")
    a = ap.parse_args()
    sessions = [load(s) for s in a.sessions]
    fn = {
        "strike": strike_table,
        "dead": dead_table,
        "loot": loot_table,
        "stray": stray_table,
        "blocks": blocks_table,
        "species": species_table,
        "retry": retry_table,
    }[a.what]
    print(json.dumps(fn(sessions), indent=1, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
