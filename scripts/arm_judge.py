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
    arm_judge.py deadprobe SID [SID ...] v39's log-only dead_probe against packets: per dead
                                        call's truth and last burst, the would-be "still there"
                                        signals (same monster under a new id, a box near the
                                        predicted pixel) -- the false-dead fix's design (3.81)
    arm_judge.py falsedead SID [SID ...] v40: the risky-burst dead calls per arm (fix = odd k):
                                        called dead with the target alive, skipped, alive targets
                                        killed within 20 s after, loot at our kills, landing
    arm_judge.py walkers SID [SID ...]  v41: walking targets struck from further (fix = odd k):
                                        per target class (a WALKER: its cell changed around the
                                        GM's first moment within 7 cells), near -> first click,
                                        the approach, landing

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
# rAthena AREA_SIZE: a client is sent the floor items within 14 cells (Chebyshev) of its char; one
# that falls out of that square is cleared for THAT client only (clif_outsight ->
# clif_clearflooritem), with the same ZC_ITEM_DISAPPEAR a pickup or an expiry sends to the area.
SIGHT_CELLS = 14
# flow_judge.gm_track replays our walk at GM_MS_CELL and runs up to ~0.2 s behind the server's own
# step (2026-10-19: 65 of 718 out-of-sight vanishes over 12 runs had the track at 14 and at 15
# <= 0.2 s later; of 1215 looter / pickup vanishes, 6 had it at 15 -- picked after coming back
# into view, and 1 out-of-sight one the looter rule took -- and none within 2 s otherwise)
SIGHT_LAG_S = 0.25


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


def out_of_sight(track: Sequence[tuple[int, tuple[int, int]]], t: int, cell: tuple[int, int],
                 ts: Sequence[int] | None = None) -> bool:  # fmt: skip
    """PURE: our GM stood more than SIGHT_CELLS (Chebyshev) from ``cell`` at ``t`` or within
    SIGHT_LAG_S after it (``track`` = flow_judge.gm_track(...)[0], time-sorted; ``ts`` its times,
    when the caller has them): a floor item's vanish then is the server clearing it from OUR view,
    not the item leaving the map."""
    if ts is None:
        ts = [p[0] for p in track]
    i = max(0, bisect.bisect_right(ts, t) - 1)
    j = bisect.bisect_right(ts, t + int(SIGHT_LAG_S * NS))
    return any(max(abs(c[0] - cell[0]), abs(c[1] - cell[1])) > SIGHT_CELLS
               for _t, c in track[i:j])  # fmt: skip


def item_fates(packets: Sequence[Mapping[str, Any]], pos: Mapping[int, Sequence[Any]],
               mob_at: Any, track: Sequence[tuple[int, tuple[int, int]]] | None = None,
               ) -> dict[int, dict[str, Any]]:  # fmt: skip
    """PURE: floor_id -> {t_fall, cell, fate, t_end, t_out}. fate: "picked" (our pickup answered
    ok), "out_of_sight" (it left OUR view while still on the floor -- our GM walked more than
    SIGHT_CELLS away -- and did not come back into it), "looter" (vanished early, a monster within
    LOOTER_CELLS of it then), "gone" (vanished early IN sight, no monster near: another cause),
    "expired" (>= EXPIRE_S after the fall), "left" (still there at the end). An out-of-sight item
    that comes back into view (floor_item_appear kind "in_sight": the same floor id on the same
    cell) is followed on: its next vanish decides; ``t_out`` keeps when it first left our view.
    ``pos`` / ``mob_at`` = hunt_core.walk_positions + flow_judge.mob_at; ``track`` = our GM's
    flow_judge.gm_track(packets)[0], computed here when None.
    2026-10-19 (the judge check of P1's 28 % "gone"): before ``out_of_sight`` existed, ALL 718
    "gone" items of 12 runs (v40, v41, v43) were out-of-sight vanishes -- our GM at 15 cells, or at
    14 and at 15 <= 0.2 s later -- and none had a pickup request, a pickup act or a player near."""
    if track is None:
        import flow_judge as fj

        track = fj.gm_track(packets)[0]
    ts = [p[0] for p in track]
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
                                         "fate": "left", "t_end": None, "t_out": None}  # fmt: skip
        elif typ == "floor_item_appear" and e.get("kind") == "in_sight":
            it = items.get(int(e["floor_id"]))
            if (it is not None and it["fate"] == "out_of_sight"
                    and it["cell"] == (int(e["x"]), int(e["y"]))):  # fmt: skip
                it["fate"], it["t_end"] = "left", None  # back in our view: follow it on
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
            elif out_of_sight(track, t, it["cell"], ts):
                it["fate"] = "out_of_sight"
                if it["t_out"] is None:
                    it["t_out"] = t
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
      landing (flow_judge's why == "hit") and kills;
    - the steer's walk clicks and those the client turned into an attack (the first request
      after it, before our next click, <= 3 s), on a target species or ANOTHER unit (v39 clicks
      nearer the target: the safety side).
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
        # steer walk clicks the client turned into an attack: the first attack request after
        # the click, before our next click of any kind and <= 3 s (the client walks up first and
        # asks only in reach: v38 run 2's Creamy came 1.1 s after), by the unit's job
        cl = sorted((json.loads(x_) for x_ in (DEMO / sid / "clicks.jsonl").read_text()
                     .splitlines() if x_), key=lambda c_: int(c_["t"]))  # fmt: skip
        reqs = [(int(e["t_mono_ns"]), int(e.get("target_gid") or -1)) for e in sess.events
                if e.get("type") == "attack_request"]  # fmt: skip
        rq_t = [t_ for t_, _g in reqs]
        for ci_, c_ in enumerate(cl):
            t_ = int(c_["t"])
            if c_.get("kind") != "walk" or c_.get("why") != "steer" or not (
                    sess.t0 <= t_ < sess.w1):  # fmt: skip
                continue
            arm = "tail" if on(k_at(fcs, t_)) else "base"
            nxt = int(cl[ci_ + 1]["t"]) if ci_ + 1 < len(cl) else t_ + 3 * NS
            j_ = bisect.bisect_right(rq_t, t_)
            turned = j_ < len(reqs) and reqs[j_][0] <= min(nxt, t_ + 3 * NS)
            for c in (rt[arm], tot[arm]):
                c["steer_walk_clicks"] += 1
                if turned:
                    tgt_ = fld.job.get(reqs[j_][1], -1) in TARGET_JOBS
                    c["walk_to_attack_target" if tgt_ else "walk_to_attack_other"] += 1
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
            "steer_walk_clicks": c["steer_walk_clicks"],
            "walk_to_attack_target": c["walk_to_attack_target"],
            "walk_to_attack_other": c["walk_to_attack_other"],
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


def walker_table(sids: Iterable[str], on_of: Any = None, near: int = 7,
                 walk_win_s: float = 0.6, sample_s: float = 0.1) -> dict[str, Any]:  # fmt: skip
    """v41 per arm ("fix" = odd k: a WALKING target struck from ``strike_cells_walking`` cells;
    "base" = even k), from packets on flow_judge's window. Per engagement (its attacked gid,
    flow_judge's join), from ``a`` = the start of the last steer span after the previous
    engagement's end (else that end):
    - ``t_near``: the first sample in [a, first click] with our GM within ``near`` cells of it;
    - a WALKER = its cell changed within +-``walk_win_s`` of ``t_near`` (the moment the strike
      range starts to matter in either arm, so the class does not depend on the arm);
    - per class: engagements, near -> first click (s), approach (a -> first click), landing
      (flow_judge's why == "hit"), kills; ``beyond_near`` = clicked before ever within ``near``.
    ``on_of(k)`` replaces the arm rule (a null split of older runs). Per run: (fix - base) / mean
    of the walkers' near -> click mean and landing share."""
    import conversion_phases as cp
    import search_study as ss

    on = on_of or (lambda k_: k_ % 2 == 1)
    dt, win = int(sample_s * NS), int(walk_win_s * NS)
    arms = ("fix", "base")
    tot: dict[str, Counter[str]] = {arm: Counter() for arm in arms}
    lst: dict[str, dict[str, list[float]]] = {arm: defaultdict(list) for arm in arms}
    per_run: dict[str, Any] = {}
    for sid in sids:
        sess = ss.load_session(sid)
        fld = ss.Field(sess.events)
        engs = sorted(sess.engagements, key=lambda x: int(x["t_first_click"]))
        rows = {int(r_["k"]): r_ for r_ in json.loads(
            (DEMO / sid / "flow_judge.json").read_text())["engagements_w"]["rows"]}  # fmt: skip
        spans = mode_spans(sess.bot_events, "steer", sess.t0, sess.w1)
        rt: dict[str, Counter[str]] = {arm: Counter() for arm in arms}
        rl: dict[str, dict[str, list[float]]] = {arm: defaultdict(list) for arm in arms}
        for i, x in enumerate(engs):
            fc, k = int(x["t_first_click"]), int(x["k"])
            if not sess.t0 <= fc < sess.w1:
                continue
            arm = "fix" if on(k) else "base"
            prev = int(engs[i - 1].get("t_end") or engs[i - 1]["t_first_click"]) if i else sess.t0
            st = [a_ for a_, _b in spans if prev <= a_ < fc]
            a = st[-1] if st else prev
            row = rows.get(k) or {}
            g = row.get("gid")
            cls = "unjoined"
            got: dict[str, float] = {}
            if g is not None:
                tn = cp.first_within(fld, int(g), a, fc, near, sample_s)
                if tn is None:
                    cls = "beyond_near"
                else:
                    cells = {fld.mob(int(g), t) for t in range(tn - win, tn + win + 1, dt)}
                    cls = "walker" if len(cells - {None}) > 1 else "still"
                    got["near_to_click_s"] = (fc - tn) / NS
                got["approach_s"] = (fc - a) / NS
            for c in (rt[arm], tot[arm]):
                c[f"{cls}:eng"] += 1
                c[f"{cls}:landed"] += row.get("why") == "hit"
                c[f"{cls}:kills"] += x.get("result") == "dead"
                c["all:eng"] += 1
                c["all:landed"] += row.get("why") == "hit"
            for name, v in got.items():
                for d_ in (rl[arm], lst[arm]):
                    d_[f"{cls}:{name}"].append(v)
        per_run[sid] = _walker_rel(_walker_arms(rt, rl))
    return {"per_run": per_run, **_walker_arms(tot, lst)}


def _walker_arms(tot: Mapping[str, Counter[str]],
                 lst: Mapping[str, Mapping[str, list[float]]]) -> dict[str, Any]:  # fmt: skip
    out: dict[str, Any] = {}
    for arm, c in tot.items():
        o: dict[str, Any] = {}
        for cls in ("walker", "still", "beyond_near", "unjoined", "all"):
            n = c[f"{cls}:eng"]
            if not n:
                continue
            o[cls] = {"engagements": n, "landing": f"{c[f'{cls}:landed']}/{n}",
                      "landing_share": round(c[f"{cls}:landed"] / n, 3)}  # fmt: skip
            if cls != "all":
                o[cls]["kills"] = c[f"{cls}:kills"]
            for name in ("near_to_click_s", "approach_s"):
                v = sorted(lst[arm].get(f"{cls}:{name}", []))
                if v:
                    o[cls][f"{name}_n"] = len(v)
                    o[cls][f"{name}_p50"] = round(v[len(v) // 2], 2)
                    o[cls][f"{name}_mean"] = round(sum(v) / len(v), 3)
        out[arm] = o
    return out


def _walker_rel(arms: dict[str, Any]) -> dict[str, Any]:
    """Per run: the arms and (fix - base) / their mean for the walkers' deciding measures."""
    out: dict[str, Any] = {"arms": arms}
    f, b = (arms.get(a_, {}).get("walker") for a_ in ("fix", "base"))
    if f and b:
        for name in ("near_to_click_s_mean", "approach_s_mean", "landing_share"):
            x, y = f.get(name), b.get(name)
            if x is not None and y is not None and x + y:
                out[f"rel_walker_{name}"] = round((x - y) / ((x + y) / 2), 3)
    return out


def deadprobe_table(sids: Iterable[str], radii: Sequence[int] = (30, 45, 60)) -> dict[str, Any]:
    """v39's log-only ``dead_probe`` (the 3.80 amendment) against the server: every probed dead
    call by its truth (flow_judge.dead_call_truth: real / target_alive / target_gone / no_unit /
    other_killed) and its last burst ("risky" or other), with the probe's would-be signals --
    the same monster under a new id (``reacq``), the freshest monster box within r px of the
    engaged track's predicted pixel (``box<=r``), the track still live. For the false-dead fix
    (3.81): how many still-alive targets a signal catches, and how many real kills it would
    hold back."""
    import flow_judge as fj
    import search_study as ss

    agg: dict[str, Counter[str]] = defaultdict(Counter)
    cover: Counter[str] = Counter()
    for sid in sids:
        sess = ss.load_session(sid)
        rows = json.loads((DEMO / sid / "flow_judge.json").read_text())["engagements_w"]["rows"]
        truth = fj.dead_call_truth(sess.events, sess.engagements, rows, sess.t0, sess.w1)
        cover["dead_calls"] += len(truth)
        for p in sess.bot_events:
            if p.get("kind") == "dead_probe_error":
                cover["probe_errors"] += 1
            if p.get("kind") != "dead_probe" or int(p["k"]) not in truth:
                continue
            cover["probed"] += 1
            why, _last = truth[int(p["k"])]
            grp = "risky" if p.get("last_burst") == "risky" else "other"
            a = agg[f"{grp}/{why}"]
            a["n"] += 1
            a["reacq"] += p.get("reacq") is not None
            a["track_live"] += bool(p.get("track_live"))
            bp = p.get("box_px")
            for r_ in radii:
                a[f"box<={r_}"] += bp is not None and float(bp) <= r_
    return {"coverage": dict(cover), **{k: dict(v) for k, v in sorted(agg.items())}}


def falsedead_table(sids: Iterable[str], on_of: Any = None,
                    after_s: float = 20.0) -> dict[str, Any]:  # fmt: skip
    """v40 per arm ("fix" = odd k: after a RISKY last burst the dead call stands only on the
    death-cell fix's "ok", else "skipped_risky"; "base" = even k), from packets on flow_judge's
    window. Over the engagements the runner ended "dead" or "skipped_risky" whose last burst
    ended "risky": how many were called DEAD with the target still alive (the false dead calls
    the fix targets), how many skipped, and -- of those whose target was alive at the
    engagement's end -- how many we killed within ``after_s`` (re-engaged) and the time from the
    engagement's last click to our kill of it (<= 30 s); plus landing and the loot at our kills
    per arm (the drops of OUR kill inside each engagement, whatever the runner called it: a
    skipped real kill's loot counts as not picked). ``on_of(k)`` replaces the arm rule."""
    import flow_judge as fj
    import hunt_core as hc
    import search_study as ss

    on = on_of or (lambda k_: k_ % 2 == 1)
    agg: dict[str, Counter[str]] = {a_: Counter() for a_ in ("fix", "base")}
    lst: dict[str, list[float]] = {a_: [] for a_ in ("fix", "base")}
    per_run: dict[str, Any] = {}
    for sid in sids:
        sess = ss.load_session(sid)
        lst_run: dict[str, list[float]] = {a_: [] for a_ in ("fix", "base")}
        rows = {int(r_["k"]): r_ for r_ in json.loads(
            (DEMO / sid / "flow_judge.json").read_text())["engagements_w"]["rows"]}  # fmt: skip
        deaths: dict[int, list[int]] = defaultdict(list)
        for e in sess.events:
            if e.get("type") == "entity_vanish" and int(e.get("reason", -1)) == 1:
                deaths[fj.gid_of(e)].append(int(e["t_mono_ns"]))
        our_k: dict[int, list[int]] = defaultdict(list)
        for t_, g_ in kills_of(sess.events):
            our_k[g_].append(t_)
        life = fj.alive(sess.events)
        pos = hc.walk_positions(sess.events)
        items = item_fates(sess.events, pos, fj.mob_at)
        rc: dict[str, Counter[str]] = {a_: Counter() for a_ in ("fix", "base")}
        for x in sess.engagements:
            fc, k = int(x["t_first_click"]), int(x["k"])
            if not sess.t0 <= fc < sess.w1:
                continue
            arm = "fix" if on(k) else "base"
            row = rows.get(k) or {}
            g = row.get("gid")
            for c in (rc[arm], agg[arm]):
                c["engagements"] += 1
                c["landed"] += row.get("why") == "hit"
            te_ = int(x.get("t_end") or fc) + NS
            tk_ = None if g is None else next(
                (t_ for t_ in our_k.get(int(g), ()) if fc <= t_ <= te_), None)  # fmt: skip
            if tk_ is not None:  # OUR kill in this engagement, whatever the runner called it
                for f in drops_of_kill(items, tk_, fj.mob_at(pos, g, tk_ - 1)):
                    for c in (rc[arm], agg[arm]):
                        c["items"] += 1
                        c["picked"] += items[f]["fate"] == "picked"
            ends = [(h.get("burst") or {}).get("end") for h in x.get("hovers", [])
                    if h.get("burst")]  # fmt: skip
            if x.get("result") not in ("dead", "skipped_risky") or not ends or ends[-1] != "risky":
                continue
            te = int(x.get("t_end") or fc)
            real = g is not None and any(fc <= d <= te + NS for d in deaths.get(int(g), ()))
            alive_end = g is not None and not real and fj.present(life, int(g), te)
            later = g is not None and any(te < t_ <= te + int(after_s * NS)
                                          for t_ in our_k.get(int(g), ()))  # fmt: skip
            tl_ = int(x.get("t_last_click") or fc)
            nxt = next((t_ for t_ in sorted(our_k.get(int(g), ())) if tl_ < t_ <= tl_ + 30 * NS),
                       None) if alive_end else None  # fmt: skip
            if nxt is not None:
                lst[arm].append((nxt - tl_) / NS)
                lst_run[arm].append((nxt - tl_) / NS)
            for c in (rc[arm], agg[arm]):
                c["risky_ended"] += 1
                c["skipped"] += x.get("result") == "skipped_risky"
                c["skipped_real"] += x.get("result") == "skipped_risky" and real
                c["dead_called_alive"] += x.get("result") == "dead" and alive_end
                c["dead_called_real"] += x.get("result") == "dead" and real
                c["alive_at_end"] += alive_end
                c["alive_killed_after"] += alive_end and later
        per_run[sid] = {a_: {**dict(c), "alive_to_kill_s": [round(v, 2) for v in lst_run[a_]]}
                        for a_, c in rc.items()}  # fmt: skip
    out: dict[str, Any] = {"per_run": per_run}
    for arm, c in agg.items():
        tk = lst[arm]
        out[arm] = {**dict(sorted(c.items())),
                    "alive_to_kill_n": len(tk),
                    "alive_to_kill_s_mean": round(sum(tk) / len(tk), 2) if tk else None,
                    "landing_share": round(c["landed"] / c["engagements"], 3)
                    if c["engagements"] else None,
                    "loot_share": round(c["picked"] / c["items"], 3) if c["items"] else None,
                    "re_engaged_share": round(c["alive_killed_after"] / c["alive_at_end"], 3)
                    if c["alive_at_end"] else None}  # fmt: skip
    return out


V39_TAIL_GUARD_PER_STEER_MIN = 4477 / 41.9  # 3.83 check 5: v39's tail arm, guard refusals


def guard_refusals(events: Iterable[Mapping[str, Any]], prefix: str) -> int:
    """PURE: the steer's continuous-click candidates refused by the walk guard, summed over the
    runner's ``cont_fail`` events for the call key ``prefix`` ("steer+tail+box" = v42's fix arm,
    "steer" = its base; moving and standing)."""
    n = 0
    for e in events:
        if e.get("kind") != "cont_fail":
            continue
        for key, v in (e.get("counts") or {}).items():
            parts = str(key).split(":")
            if len(parts) == 3 and parts[0] == prefix and parts[2] == "guard":
                n += int(v)
    return n


def steerguard_table(sids: Sequence[str]) -> dict[str, Any]:
    """3.83 (hunt-flow@42, e3fc195): approach_table's arms ("tail" = odd k = the fix: the steer's
    box + 20 px guard and route tail; "base" = even k) + the deciding checks 1-4 + check 5 (the
    code ran as built: the box rule refused steer clicks, near_gm_box > 0; the fix arm's guard
    refusals per steer minute < half of v39's tail arm, 4,477 / 41.9 min) + the pocket escape's
    stuck_escape events per run (amendment 2)."""
    out = approach_table(sids)
    ref = {"fix": 0, "base": 0}
    box_n = 0
    pockets: dict[str, Any] = {}
    for sid in sids:
        bev = [json.loads(x) for x in (DEMO / sid / "events.jsonl").read_text().splitlines()
               if x.strip()]  # fmt: skip
        ref["fix"] += guard_refusals(bev, "steer+tail+box")
        ref["base"] += guard_refusals(bev, "steer")
        wg = [e for e in bev if e.get("kind") == "walk_guard"]
        man = json.loads((DEMO / sid / "manifest.json").read_text())
        box_n += int((man.get("walk_guard") or (wg[-1] if wg else {})).get("near_gm_box", 0))
        pockets[sid] = [
            {
                "t_s": round((int(e["t_ns"]) - int(bev[0]["t_ns"])) / NS, 1),
                **{k: e.get(k) for k in ("why", "centre", "goal", "path") if k in e},
            }
            for e in bev
            if e.get("kind") == "stuck_escape"
        ]
    f, b = out.get("tail") or {}, out.get("base") or {}
    per_min = (ref["fix"] / f["steer_min"]) if f.get("steer_min") else None
    hard = {}
    for sid in sids:
        hb = json.loads((DEMO / sid / "flow_judge.json").read_text()).get("hard_bars") or {}
        hard[sid] = [hb.get("npc_contacts"), hb.get("map_changes"),
                     [j for j in hb.get("non_target_jobs_hit", []) if j != 1018]]  # fmt: skip

    def ge(x: Any, y: Any, fac: float) -> bool | None:
        return None if x is None or y is None else x >= fac * y

    out["guard_refusals"] = {**ref, "fix_per_steer_min": None if per_min is None
                             else round(per_min, 1), "near_gm_box": box_n}  # fmt: skip
    out["stuck_escape"] = pockets
    out["checks"] = {
        "1 steer moving share fix >= 1.15 x base": ge(f.get("steer_moving_share"),
                                                      b.get("steer_moving_share"), 1.15),
        "2 approach mean fix <= 0.90 x base": None
        if f.get("approach_s_mean") is None or b.get("approach_s_mean") is None
        else f["approach_s_mean"] <= 0.90 * b["approach_s_mean"],
        "3 landing fix >= base - 8 points": None
        if f.get("landing_share") is None or b.get("landing_share") is None
        else f["landing_share"] >= b["landing_share"] - 0.08,
        "4 hard bars zero": all(v[0] == 0 and v[1] == 0 and not v[2] for v in hard.values()),
        "5 ran as built (near_gm_box > 0, fix guard / steer min < half v39 tail)":
        box_n > 0 and per_min is not None and per_min < V39_TAIL_GUARD_PER_STEER_MIN / 2,
    }  # fmt: skip
    out["hard_bars"] = hard
    return out


def exp_line_kills(
    lines: Sequence[Mapping[str, Any]],
    kill_ts: Sequence[int],
    before_s: float = 2.0,
    after_s: float = 0.2,
) -> tuple[int, int]:
    """PURE (3.87's reported live precision): (base EXP lines, those with a kill of ours behind
    them: a kill (``kill_ts``, arm_judge.kills_of) from ``before_s`` before the line's first frame
    to ``after_s`` after it; each kill backs one line)."""
    ks = sorted(int(t) for t in kill_ts)
    used: set[int] = set()
    n = ok = 0
    for rec in sorted(lines, key=lambda x: int(x["t_ns"])):
        if rec.get("type") != "base_exp":
            continue
        n += 1
        t = int(rec["t_ns"])
        i = bisect.bisect_left(ks, t - int(before_s * NS))
        while i < len(ks) and ks[i] <= t + int(after_s * NS):
            if i not in used:
                used.add(i)
                ok += 1
                break
            i += 1
    return n, ok


def expdead_table(sids: Iterable[str]) -> dict[str, Any]:
    """3.87 (hunt-flow@44, 4d937b4): per arm -- "fix" = odd k (dead = the EXP line, the checked
    fallback), "base" = even k -- over the engagements whose first click lies in flow_judge's
    window, pooled over ``sids``:
    1. kill -> loot start, mean (the kill's vanish -> the loot step's start; "dead" with a loot
       step, as expdead_null.py measured the null);
    2. dead calls without a real death (flow_judge.dead_call_truth, the engagements ended "dead");
    3. loot picked / dropped at OUR kills: every engagement whose target died by our hit between
       its first click - 1 s and its end + 3 s, whatever the runner called it (a skipped real
       kill loses its loot);
    4. landing within 5 s (flow_judge's rows, why "hit");
    reported: items lost to looters, the skipped_unconfirmed count and how many were real kills,
    the fix arm's dead_by, death -> the next engagement p50, and (per run) the live reader's base
    EXP lines with / without a kill of ours behind them; the hard bars per run."""
    import flow_judge as fj
    import hunt_core as hc
    import search_study as ss

    arms: dict[str, dict[str, Any]] = {a: defaultdict(list) for a in ("fix", "base")}
    cnt: dict[str, Counter[str]] = {a: Counter() for a in ("fix", "base")}
    per_run: dict[str, Any] = {}
    for sid in sids:
        sess = ss.load_session(sid)
        fjo = json.loads((DEMO / sid / "flow_judge.json").read_text())
        rows = fjo["engagements_w"]["rows"]
        by_k = {int(r["k"]): r for r in rows if r.get("k") is not None}
        truth = fj.dead_call_truth(sess.events, sess.engagements, rows, sess.t0, sess.w1)
        van: dict[int, list[int]] = defaultdict(list)
        for e in sess.events:
            if e.get("type") == "entity_vanish" and int(e.get("reason", -1)) == 1:
                van[int(e.get("gid") or -1)].append(int(e["t_mono_ns"]))
        kills = kills_of(sess.events)
        kill_ts: dict[int, list[int]] = defaultdict(list)  # rAthena reuses a dead mob's gid
        for t_k, g_k in kills:
            kill_ts[g_k].append(t_k)
        pos = hc.walk_positions(sess.events)
        items = item_fates(sess.events, pos, fj.mob_at)
        firsts = sorted(int(x["t_first_click"]) for x in sess.engagements)
        for x in sess.engagements:
            k = int(x["k"])
            if not sess.t0 <= int(x["t_first_click"]) < sess.w1:
                continue
            arm = "fix" if k % 2 == 1 else "base"
            m, c = arms[arm], cnt[arm]
            c["engagements"] += 1
            c["result:" + str(x.get("result"))] += 1
            if arm == "fix":
                c["dead_by:" + str(x.get("dead_by"))] += x.get("result") == "dead"
                c["exp_arm_flag"] += bool(x.get("exp_arm"))
            r_ = by_k.get(k) or {}
            c["landing_counted"] += 1
            c["landing_hit"] += r_.get("why") == "hit"
            g = r_.get("gid")
            t_end = int(x.get("t_end") or 0)
            t_lo = int(x["t_first_click"]) - NS
            t_kill = next((t_k for t_k in kill_ts.get(int(g), []) if t_lo <= t_k <= t_end + 3 * NS),
                          None) if g is not None else None  # fmt: skip
            died = t_kill is not None
            if x.get("result") == "dead":
                c["dead_calls"] += 1
                tr_ = truth.get(k)
                if tr_ is not None:
                    c["dead_judged"] += 1
                    c["dead_not_real"] += tr_[0] != "real"
                loot = x.get("loot") or {}
                t_l0 = int(x.get("t_last_click") or x["t_first_click"]) - NS
                vs = sorted(t for t in van.get(int(g), []) if t_l0 <= t <= t_end + 3 * NS) if (
                    g is not None) else []  # fmt: skip
                if vs and loot.get("s") is not None and t_end:
                    m["kill_to_loot_start"].append((t_end - vs[0]) / NS - float(loot["s"]))
                    i = bisect.bisect_right(firsts, t_end)
                    if i < len(firsts):
                        m["death_to_next_engagement"].append((firsts[i] - vs[0]) / NS)
            if x.get("result") == "skipped_unconfirmed":
                c["skipped_unconfirmed"] += 1
                c["skipped_unconfirmed_real"] += died
            if t_kill is not None and g is not None:
                c["our_kills"] += 1
                for f in drops_of_kill(items, t_kill, fj.mob_at(pos, g, t_kill - 1)):
                    c["items"] += 1
                    c["picked"] += items[f]["fate"] == "picked"
                    c["looter"] += items[f]["fate"] == "looter"
        bl = DEMO / sid / "battle_log_live.jsonl"
        lines = ([json.loads(x) for x in bl.read_text().splitlines() if x.strip()]
                 if bl.exists() else [])  # fmt: skip
        n_l, ok_l = exp_line_kills(lines, [t for t, _g in kills])
        hb = fjo.get("hard_bars") or {}
        per_run[sid] = {"exp_lines": n_l, "exp_lines_with_our_kill": ok_l,
                        "hard_bars": [hb.get("npc_contacts"), hb.get("map_changes"),
                                      [j for j in hb.get("non_target_jobs_hit", [])
                                       if j != 1018]],
                        "kills_per_hour": fjo.get("kills_per_hour")}  # fmt: skip
    out: dict[str, Any] = {}
    for arm in ("fix", "base"):
        m, c = arms[arm], cnt[arm]
        kl = m["kill_to_loot_start"]
        out[arm] = {
            **dict(sorted(c.items())),
            "kill_to_loot_start_mean": round(sum(kl) / len(kl), 3) if kl else None,
            "kill_to_loot_start_p50_p90": [q(kl, 0.5), q(kl, 0.9)],
            "dead_not_real_share": round(c["dead_not_real"] / c["dead_judged"], 3)
            if c["dead_judged"] else None,
            "loot_picked_share": round(c["picked"] / c["items"], 3) if c["items"] else None,
            "landing": round(c["landing_hit"] / c["landing_counted"], 3)
            if c["landing_counted"] else None,
            "death_to_next_engagement_p50": q(m["death_to_next_engagement"], 0.5),
        }  # fmt: skip
    f, b = out["fix"], out["base"]

    checks = {
        "1 kill -> loot start mean fix <= 0.60 x base": (
            None if f["kill_to_loot_start_mean"] is None or not b["kill_to_loot_start_mean"]
            else f["kill_to_loot_start_mean"] <= 0.60 * b["kill_to_loot_start_mean"]),
        "2 dead calls without a real death fix <= 0.55 x base": (
            None if f["dead_not_real_share"] is None or b["dead_not_real_share"] is None
            else f["dead_not_real_share"] <= 0.55 * b["dead_not_real_share"]),
        "3 loot picked fix >= base - 5 points": (
            None if f["loot_picked_share"] is None or b["loot_picked_share"] is None
            else f["loot_picked_share"] >= b["loot_picked_share"] - 0.05),
        "4 landing fix >= base - 8 points": (
            None if f["landing"] is None or b["landing"] is None
            else f["landing"] >= b["landing"] - 0.08),
        "5 hard bars zero": all(v["hard_bars"][0] == 0 and v["hard_bars"][1] == 0
                                and not v["hard_bars"][2] for v in per_run.values()),
    }  # fmt: skip
    return {"arms": out, "checks": checks, "per_run": per_run}


def keepdead_table(sids: Sequence[str]) -> dict[str, Any]:
    """3.89 (hunt-flow@48, Batt 2026-10-20: the loot block's first version): per arm -- "fix" =
    odd k (dead = the EXP line alone, the target kept until its line or gone_no_line), "base" =
    even k -- pooled over ``sids``:
    P1. LOOT COMPLETENESS (loot_complete.py: items picked / items dropped by OUR kills, every kill
        of ours owned by the arm's engagements), fix - base in points;
    P2. abandoned kills (a kill of ours whose engagement ran no loot step), fix - base in points;
    P3. kill -> loot start, mean (expdead_table's ruler), fix <= 0.70 x base (3.89 as written; the
        judge first had 0.60, corrected 2026-10-20 10:4x before any verdict);
    G4. the kills / h guard: engaged s per kill (sum of the arm's engagements, first click -> end,
        loot step included, / the arm's kills of ours), fix - base <= 0.176 x the pooled run's s
        per kill (= kills / h >= 0.85 x base if every engagement took the fix arm's cost);
    G5. landing within 5 s, fix >= base - 8 points; G6. hard bars zero.
    Reported: the fate split per arm, gone_no_line and how many were real kills of ours (their
    items), the fix arm's dead_by, the reader's live precision per run."""
    import loot_complete as lc
    import search_study as ss

    ed = expdead_table(sids)
    rows = {sid: lc.session_rows(sid) for sid in sids}
    allr = [r for sid in sids for r in rows[sid]]
    lca = lc.arms(allr)
    eng_s = {"fix": 0.0, "base": 0.0}
    window_s = 0.0
    kills_all = 0
    gone: Counter[str] = Counter({k: 0 for k in ("gone_no_line", "gone_no_line_real_kills",
                                                  "gone_no_line_items",
                                                  "gone_no_line_items_picked")})  # fmt: skip
    for sid in sids:
        sess = ss.load_session(sid)
        fjo = json.loads((DEMO / sid / "flow_judge.json").read_text())
        window_s += float(fjo["window_s"])
        kills_all += int(fjo.get("kills") or 0)
        for x in sess.engagements:
            if not sess.t0 <= int(x["t_first_click"]) < sess.w1 or not x.get("t_end"):
                continue
            arm = "fix" if int(x["k"]) % 2 == 1 else "base"
            eng_s[arm] += (int(x["t_end"]) - int(x["t_first_click"])) / NS
            if x.get("result") == "gone_no_line":
                gone["gone_no_line"] += 1
        for r in rows[sid]:
            if r["result"] == "gone_no_line":
                gone["gone_no_line_real_kills"] += 1
                gone["gone_no_line_items"] += len(r["fates"])
                gone["gone_no_line_items_picked"] += r["fates"].count("picked")
    run_s_per_kill = window_s / kills_all if kills_all else None
    out = {}
    for arm in ("fix", "base"):
        a = lca[arm]
        out[arm] = {**{k: a[k] for k in ("kills", "items", "picked", "out_of_sight", "looter",
                                           "expired", "left", "gone", "completeness",
                                           "out_of_sight_share", "looter_share", "expired_share",
                                           "abandoned_kills", "abandoned_share",
                                           "abandoned_items")},
                    "engaged_s": round(eng_s[arm], 1),
                    "engaged_s_per_kill": round(eng_s[arm] / a["kills"], 2) if a["kills"] else None,
                    "kill_to_loot_start_mean": ed["arms"][arm]["kill_to_loot_start_mean"],
                    "kill_to_loot_start_p50_p90": ed["arms"][arm]["kill_to_loot_start_p50_p90"],
                    "landing": ed["arms"][arm]["landing"],
                    "dead_not_real_share": ed["arms"][arm]["dead_not_real_share"],
                    "results": {k[7:]: v for k, v in ed["arms"][arm].items()
                                if k.startswith("result:")},
                    "dead_by": {k[8:]: v for k, v in ed["arms"][arm].items()
                                if k.startswith("dead_by:")}}  # fmt: skip
    out["no_engagement"] = {k: lca["no_engagement"][k] for k in ("kills", "items", "picked",
                                                                  "completeness")}  # fmt: skip
    f, b = out["fix"], out["base"]

    def pts(x: Any, y: Any) -> float | None:
        return None if x is None or y is None else round(100 * (x - y), 1)

    d_c = pts(f["completeness"], b["completeness"])
    d_a = pts(f["abandoned_share"], b["abandoned_share"])
    d_e = (None if f["engaged_s_per_kill"] is None or b["engaged_s_per_kill"] is None
           else round(f["engaged_s_per_kill"] - b["engaged_s_per_kill"], 2))  # fmt: skip
    kl_f, kl_b = f["kill_to_loot_start_mean"], b["kill_to_loot_start_mean"]
    checks = {
        "P1 completeness fix - base >= +6.5 points": None if d_c is None else d_c >= 6.5,
        "P2 abandoned kills fix - base <= -5.5 points": None if d_a is None else d_a <= -5.5,
        "P3 kill -> loot start mean fix <= 0.70 x base": (
            None if kl_f is None or not kl_b else kl_f <= 0.70 * kl_b),
        "G4 engaged s per kill fix - base <= 0.176 x run s per kill": (
            None if d_e is None or run_s_per_kill is None else d_e <= 0.176 * run_s_per_kill),
        "G5 landing fix >= base - 8 points": (
            None if f["landing"] is None or b["landing"] is None
            else f["landing"] >= b["landing"] - 0.08),
        "G6 hard bars zero": ed["checks"]["5 hard bars zero"],
        "completeness fix >= base (the base-step tier)": None if d_c is None else d_c >= 0,
    }  # fmt: skip
    return {"arms": out, "differences": {"completeness_points": d_c, "abandoned_points": d_a,
                                         "engaged_s_per_kill": d_e,
                                         "kill_to_loot_start_ratio": (
                                             None if kl_f is None or not kl_b
                                             else round(kl_f / kl_b, 3)),
                                         "run_s_per_kill": None if run_s_per_kill is None
                                         else round(run_s_per_kill, 2)},
            "gone_no_line": dict(gone), "checks": checks, "per_run": ed["per_run"]}  # fmt: skip


def handloot_table(sids: Sequence[str]) -> dict[str, Any]:
    """3.90 (the HAND scan, Batt's step 3): per arm -- "fix" = odd k (the HAND scan), "base" =
    even k (the blind 3 x 3) -- pooled over ``sids``: keepdead_table's completeness, fates,
    abandoned kills, engaged s per kill, landing and hard bars, plus the HAND scan's mechanics --
    hovers by what they read (hand / empty / sword / unknown), HAND clicks and how many were
    followed by a pickup request within 2 s and before our next click, loot step s p50 per arm."""
    kd = keepdead_table(sids)
    mech: dict[str, Counter[str]] = {"fix": Counter(), "base": Counter()}
    step_s: dict[str, list[float]] = {"fix": [], "base": []}
    for sid in sids:
        d = DEMO / sid
        for x in json.loads((d / "engagements.json").read_text()):
            lo = x.get("loot") or {}
            if not lo:
                continue
            arm = "fix" if int(x["k"]) % 2 == 1 else "base"
            if lo.get("s") is not None:
                step_s[arm].append(float(lo["s"]))
            for k_, v_ in (lo.get("hand") or {}).items():
                mech[arm]["hover:" + k_] += int(v_)
            mech[arm]["steps"] += 1
            mech[arm]["end:" + str(lo.get("end"))] += lo.get("end") is not None
            mech[arm]["extra_cells"] += int(lo.get("extra_cells") or 0)
            mech[arm]["passes"] += int(lo.get("passes") or 0)
        clicks = sorted((json.loads(x) for x in (d / "clicks.jsonl").read_text().splitlines()
                         if x), key=lambda c: int(c["t"]))  # fmt: skip
        import gzip

        with gzip.open(d / "packets.jsonl.gz", "rt") as fh:
            pk = sorted((json.loads(x) for x in fh), key=lambda e: int(e["t_mono_ns"]))
        # a HAND click "became a pickup" when a pickup request follows it within 2 s and before
        # our next click: the client WALKS to an item first when it lies off our cell (v37's
        # loot cursor reads, 2 runs: 21 of 35 HAND clicks whose first request was a walk sent
        # the pickup 0.33 s later, p50; the other 14 were cut by the next blind click)
        cts = [int(c["t"]) for c in clicks]
        preq = [int(e["t_mono_ns"]) for e in pk if e.get("type") == "pickup_request"]
        for c in clicks:
            if c.get("kind") != "loot" or c.get("src") not in ("hand", "gm_hand"):
                continue  # 3.90's HAND scan, Batt's loot rule's scan around the GM
            t_c = int(c["t"])
            i_n = bisect.bisect_right(cts, t_c)
            t_end = min(cts[i_n] if i_n < len(cts) else t_c + 2 * NS, t_c + 2 * NS)
            i_p = bisect.bisect_right(preq, t_c)
            mech["fix"]["hand_clicks"] += 1
            mech["fix"]["hand_clicks_pickup"] += i_p < len(preq) and preq[i_p] <= t_end
    hc_ = mech["fix"]["hand_clicks"]
    prec = round(mech["fix"]["hand_clicks_pickup"] / hc_, 3) if hc_ else None
    f, b = kd["arms"]["fix"], kd["arms"]["base"]
    d_c = kd["differences"]["completeness_points"]
    d_e = kd["differences"]["engaged_s_per_kill"]
    sk = kd["differences"]["run_s_per_kill"]
    checks = {
        "P1 completeness fix - base >= +10 points": None if d_c is None else d_c >= 10.0,
        "M2 HAND clicks that became a pickup request >= 0.90": None if prec is None
        else prec >= 0.90,
        "G3 engaged s per kill fix - base <= 0.176 x run s per kill": (
            None if d_e is None or sk is None else d_e <= 0.176 * sk),
        "G4 landing fix >= base - 8 points": (
            None if f["landing"] is None or b["landing"] is None
            else f["landing"] >= b["landing"] - 0.08),
        "G5 hard bars zero": kd["checks"]["G6 hard bars zero"],
    }  # fmt: skip
    return {"arms": kd["arms"], "differences": kd["differences"],
            "mechanics": {a: dict(sorted(c.items())) for a, c in mech.items()},
            "hand_click_pickup_precision": prec,
            "loot_step_s_p50": {a: q(v, 0.5) for a, v in step_s.items()},
            "loot_step_s_mean": {a: round(sum(v) / len(v), 2) if v else None
                                 for a, v in step_s.items()},
            "checks": checks, "per_run": kd["per_run"]}  # fmt: skip


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
                                     "approach", "deadprobe", "falsedead", "walkers",
                                     "expdead", "steerguard", "keepdead",
                                     "handloot"))  # fmt: skip
    ap.add_argument("sessions", nargs="+")
    a = ap.parse_args()
    if a.what == "heading":  # its own loader (search_study's windows and field)
        print(json.dumps(heading_table(a.sessions), indent=1, default=str))
        return 0
    if a.what == "approach":  # search_study's loader too
        print(json.dumps(approach_table(a.sessions), indent=1, default=str))
        return 0
    if a.what == "deadprobe":  # the same
        print(json.dumps(deadprobe_table(a.sessions), indent=1, default=str))
        return 0
    if a.what == "falsedead":  # the same
        print(json.dumps(falsedead_table(a.sessions), indent=1, default=str))
        return 0
    if a.what == "walkers":  # the same
        print(json.dumps(walker_table(a.sessions), indent=1, default=str))
        return 0
    if a.what == "steerguard":  # 3.83's per-arm judge
        print(json.dumps(steerguard_table(a.sessions), indent=1, default=str))
        return 0
    if a.what == "expdead":  # 3.87's per-arm judge
        print(json.dumps(expdead_table(a.sessions), indent=1, default=str))
        return 0
    if a.what == "keepdead":  # 3.89's per-arm judge
        print(json.dumps(keepdead_table(a.sessions), indent=1, default=str))
        return 0
    if a.what == "handloot":  # 3.90's per-arm judge
        print(json.dumps(handloot_table(a.sessions), indent=1, default=str))
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
