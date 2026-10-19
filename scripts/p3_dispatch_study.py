#!/usr/bin/env python3
"""P3 OFFLINE STUDY (Batt 2026-10-19 ~19:5x, decision 3: "P3: offline study only"): heading-aware
dispatch -- skip a target > 120 deg behind the GM's walk and > 10 cells away while SEARCHING.
What would it cost (kills) and save (time, reversals)? Banked runs; packets are offline truth
(ADR-0007); the bot never imports this module.

    p3_dispatch_study.py SID [SID ...]   (docs/competition.md "P3's offline study")

Per dispatch that SET a target (dispatch valid=True) while the runner was searching:
- the GM's heading = its last walk leg of >= 2 cells before the dispatch (reversals_study.legs,
  the reversal ruler's own legs); its cell (packets);
- the target's angle from that heading and its distance (Chebyshev) from the dispatch's cell;
- the target's FATE: followed through target_reacquired; "engaged" (an engagement on it), or
  "lost" (target_lost), or "replaced" (another target set first);
- its COST: dispatch -> the engagement's end (engaged) or -> the loss / replacement;
- reversals (reversal legs) in that span; a real kill of ours (flow_judge rows' gid, kills_of).
"""

import bisect
import json
import math
import sys
from collections import Counter, defaultdict

sys.path.insert(0, "/home/batt/docker/poring-lab/scripts")
import arm_judge as aj
import flow_judge as fj
import reversals_study as rs
import search_study as ss

NS = 10**9
DEMO = "/dev/shm/poring-lab-demo"
SET_KINDS = ("dispatch", "preempt", "retarget", "looter_engage")


def angdiff(a, b):
    return abs((a - b + 180.0) % 360.0 - 180.0)


rows = []
tot_min = 0.0
tot_kills = 0
tot_rev = 0
for sid in sys.argv[1:]:
    st = rs.study(sid)
    sess = ss.load_session(sid)
    bot = sess.bot_events
    t0, w1 = sess.t0, sess.w1
    tot_min += (w1 - t0) / NS / 60
    legs = st["legs"]
    counted = [lg for lg in legs if lg.counted]
    ct = [lg.t for lg in counted]
    revs = sorted(lg.t for lg in legs if lg.rev)
    tot_rev += len(revs)
    track, _ = fj.gm_track(sess.events)
    with open(f"{DEMO}/{sid}/flow_judge.json") as fh_:
        fjo = json.load(fh_)
    gid_by_k = {int(r["k"]): r.get("gid") for r in fjo["engagements_w"]["rows"]}
    kill_ts = defaultdict(list)
    for t_k, g_k in aj.kills_of(sess.events):
        kill_ts[g_k].append(t_k)
        if t0 <= t_k < w1:
            tot_kills += 1
    engs = sorted(sess.engagements, key=lambda x: int(x["t_first_click"]))
    mt = rs.mode_track(bot)
    loots = rs.loot_spans(bot)
    evs = sorted(bot, key=lambda e: int(e["t_ns"]))
    ets = [int(e["t_ns"]) for e in evs]
    for idx, e in enumerate(evs):
        if e.get("kind") != "dispatch" or not e.get("valid"):
            continue
        t = int(e["t_ns"])
        if not t0 <= t < w1:
            continue
        if rs.mode_at(mt, loots, t - 1) != "search":
            continue
        i = bisect.bisect_left(ct, t) - 1
        if i < 0:
            continue
        lg = counted[i]
        gm = fj.at(track, t) or lg.p1
        cell = e["cell"]
        dist = max(abs(cell[0] - gm[0]), abs(cell[1] - gm[1]))
        tgt_deg = math.degrees(math.atan2(cell[1] - gm[1], cell[0] - gm[0]))
        ang = angdiff(tgt_deg, lg.h_deg)
        cur = int(e["track"])
        fate, t_end, k_eng = "open", None, None
        ei = bisect.bisect_left([int(x["t_first_click"]) for x in engs], t)
        for f in evs[idx + 1 :]:
            tf = int(f["t_ns"])
            # an engagement on the current track first?
            while ei < len(engs) and int(engs[ei]["t_first_click"]) <= tf:
                if int(engs[ei]["track"]) == cur:
                    fate, k_eng = "engaged", int(engs[ei]["k"])
                    t_end = int(engs[ei].get("t_end") or engs[ei]["t_first_click"])
                    break
                ei += 1
            if fate != "open":
                break
            kd = f.get("kind")
            if kd == "target_reacquired" and int(f.get("track", -1)) == cur:
                cur = int(f["as"])
            elif kd == "target_lost" and int(f.get("track", -1)) == cur:
                fate, t_end = "lost", tf
                break
            elif kd == "target_dropped" and int(f.get("track", -1)) == cur:
                fate, t_end = "dropped", tf
                break
            elif (
                kd in SET_KINDS
                and (kd != "dispatch" or f.get("valid"))
                and int(f.get("track", f.get("to", -1)) or -1) != cur
            ):
                fate, t_end = "replaced", tf
                break
        if t_end is None:
            continue
        real = False
        if k_eng is not None:
            g = gid_by_k.get(k_eng)
            if g is not None:
                real = any(t - NS <= tk <= t_end + 3 * NS for tk in kill_ts.get(int(g), []))
        nrev = bisect.bisect_left(revs, t_end) - bisect.bisect_left(revs, t)
        rows.append(
            {
                "sid": sid,
                "t": t,
                "ang": ang,
                "dist": dist,
                "fate": fate,
                "cost_s": (t_end - t) / NS,
                "rev": nrev,
                "kill": real,
            }
        )

print(f"runs {len(sys.argv) - 1}, window {tot_min:.1f} min, kills {tot_kills}, reversals {tot_rev}")
s_per_kill = tot_min * 60 / tot_kills
print(
    f"search-mode dispatches that set a target: {len(rows)}; the runs' s per kill {s_per_kill:.1f}"
)


def grp(name, sel):
    g = [r for r in rows if sel(r)]
    if not g:
        print(name, "n 0")
        return
    k = sum(r["kill"] for r in g)
    c = sum(r["cost_s"] for r in g)
    rv = sum(r["rev"] for r in g)
    fates = Counter(r["fate"] for r in g)
    # the counterfactual: skip them -> lose their kills, regain their time at the runs' s per kill
    regained = c / s_per_kill
    net_h = (regained - k) / (tot_min / 60)
    print(
        f"{name}: n {len(g)} ({100 * len(g) / len(rows):.0f} %), kills {k} "
        f"({100 * k / len(g):.0f} %), time {c / 60:.1f} min ({c / len(g):.1f} s each), "
        f"reversals {rv} ({rv / (tot_min):.2f} / min of all runs, {100 * rv / tot_rev:.1f} % "
        f"of all), fates {dict(fates)}; s per kill in the group "
        f"{(c / k if k else float('nan')):.1f}; skip -> kills/h {net_h:+.1f} "
        f"(lose {k}, regain {regained:.1f} at the runs' rate)"
    )


grp("ALL search dispatches", lambda r: True)
grp("BEHIND >120 deg & >10 cells (P3)", lambda r: r["ang"] > 120 and r["dist"] > 10)
grp("behind >120 deg, <=10 cells", lambda r: r["ang"] > 120 and r["dist"] <= 10)
grp("side 60-120 deg", lambda r: 60 < r["ang"] <= 120)
grp("ahead <=60 deg", lambda r: r["ang"] <= 60)
for d in (6, 8, 12, 14):
    grp(f"behind >120 deg & >{d} cells", lambda r, d=d: r["ang"] > 120 and r["dist"] > d)
grp("behind >150 deg & >10 cells", lambda r: r["ang"] > 150 and r["dist"] > 10)
