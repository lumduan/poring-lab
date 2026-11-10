#!/usr/bin/env python3
"""rogue-xmas02.md 4O, offline study S1: why every lock ends "no hits", and walking sight (step 1).

    lock_study.py SESSION_DIR [SESSION_DIR ...] [--out OUT.json]

Reads each demo session's events.jsonl (the runner), packets.jsonl.gz (OFFLINE ground truth: it
never feeds the bot), battle_log_live.jsonl (the live Battle Log reader) and, when present,
detections.jsonl (the GPU-path box watcher). One clock: ``t_ns`` / ``t_mono_ns``.

- Per strike: the target is the ``target_gid`` of our first ``attack_request`` within REQ_S after
  the strike's first click. One class, first match wins: K the target died before the runner's
  unlock; A we hit it before the unlock; B our first hit came after the unlock; C requests but no
  hit within HIT_S; D no request.
- The reader: our damage acts (damage > 0) matched in time order to Battle Log damage lines in
  [act, act + READ_S]; the lag; experience packets vs the reader's experience lines.
- Walking sight (p8): each box engagement's triggering detection (the last one logged before it),
  walking when a ``self_move`` of ours came within WALK_S before its grab; per class: engagements,
  strikes, strikes of class K.
- R1-A (rogue-xmas02.md 4BI, Amendment R; Batt 2026-11-10): a class-D strike LOST an attack
  unless the client kept hitting through it -- our damaging act on a monster G within R1A_S before
  the strike's first click, and our next damaging act on G, or G's death, within R1A_S after it.
  Each class-D strike carries ``r1a`` (lost or not, and why); ``self_recheck`` reports
  ``own_body_d_lost`` (R1-A) beside the unchanged ``own_body_d`` (as scored before).
- ``--r1-bar``: the R1-A bar over EXACTLY the sessions given (pass the base runs only): lambda =
  R1-A own-body strikes per run, k = the smallest k with P(Poisson(R1_POOL x lambda) >= k) <=
  R1_ALPHA (Amendment R, 3; R1 fails at >= k).
"""

from __future__ import annotations

import argparse
import gzip
import json
import math
import statistics
from collections import Counter
from collections.abc import Sequence
from pathlib import Path
from typing import Any

REQ_S, HIT_S, READ_S, WALK_S = 2.0, 25.0, 2.0, 1.0
# rogue-xmas02.md 4R (p11): the Rogue's own sprite on screen, around her feet point (dungeon_hunt
# SELF_HALF_W / SELF_UP / SELF_DOWN; the camera keeps her feet at FEET_UV)
FEET_UV, SELF_HALF_W, SELF_UP, SELF_DOWN = (641.0, 362.0), 20, 95, 6
DIED = 1  # entity_vanish reason (rAthena CLR_DEAD)
NS = 1_000_000_000
# R1-A (rogue-xmas02.md 4BI, Amendment R): the window on each side of a class-D strike's first click
# in which our hits on one monster must go on for the strike to have lost nothing; the R1 bar's pool
# of runs and its false-fail probability (Amendment R, 3)
R1A_S = 1.0
R1_POOL, R1_ALPHA = 4, 0.05


def lost_attack(strike_t: int, packets: Sequence[dict[str, Any]],
                gid: int | None) -> dict[str, Any]:  # fmt: skip
    """PURE (R1-A): did a class-D strike LOSE an attack? Not when the client was hitting a monster
    G -- our damaging act on G (damage > 0) within R1A_S before the first click -- and kept on:
    our next damaging act on G, or G's death (an ``entity_vanish`` with reason DIED), within R1A_S
    after the click. ``reason``: "continued" (not lost), "no_hit_before" or "stopped" (lost)."""
    lo, hi = strike_t - R1A_S * NS, strike_t + R1A_S * NS
    hits = [p for p in packets if p.get("type") == "act" and p.get("src_gid") == gid
            and int(p.get("damage") or 0) > 0]  # fmt: skip
    before: dict[int, int] = {}  # G -> our last hit on it in [click - R1A_S, click]
    for p in hits:
        if lo <= p["t_mono_ns"] <= strike_t:
            before[p["target_gid"]] = p["t_mono_ns"]
    if not before:
        return {"lost": True, "reason": "no_hit_before"}
    for g, t_b in sorted(before.items(), key=lambda kv: -kv[1]):  # the latest hit first
        nxt = next((p["t_mono_ns"] for p in hits
                    if p["target_gid"] == g and strike_t < p["t_mono_ns"] <= hi), None)  # fmt: skip
        died = next((p["t_mono_ns"] for p in packets
                     if p.get("type") == "entity_vanish" and p.get("gid") == g
                     and p.get("reason") == DIED and strike_t < p["t_mono_ns"] <= hi),
                    None)  # fmt: skip
        after = min((t for t in (nxt, died) if t is not None), default=None)
        if after is not None:
            return {"lost": False, "reason": "continued", "gid": g,
                    "before_s": round((t_b - strike_t) / NS, 2),
                    "after_s": round((after - strike_t) / NS, 2),
                    "by": "hit" if after == nxt else "death"}  # fmt: skip
    return {"lost": True, "reason": "stopped", "gids": sorted(before)}


def poisson_sf(k: int, mean: float) -> float:
    """PURE: P(X >= k) for X ~ Poisson(mean)."""
    if k <= 0:
        return 1.0
    return max(0.0, 1.0 - sum(math.exp(-mean) * mean**i / math.factorial(i) for i in range(k)))


def r1_bar(counts: Sequence[int], pool: int = R1_POOL, alpha: float = R1_ALPHA) -> dict[str, Any]:
    """PURE (Amendment R, 3): lambda = the mean count per run over ``counts`` (the base runs, one
    count each); the pool's bar k = the smallest k with P(Poisson(pool x lambda) >= k) <= alpha
    (R1 fails at >= k); P at k - 1 and at k."""
    lam = sum(counts) / len(counts)
    mean = pool * lam
    k = 0
    while poisson_sf(k, mean) > alpha:
        k += 1
    return {"runs": len(counts), "strikes": sum(counts), "lambda": round(lam, 4), "pool": pool,
            "pool_mean": round(mean, 4), "alpha": alpha, "k": k,
            "p_ge_k_minus_1": round(poisson_sf(k - 1, mean), 4),
            "p_ge_k": round(poisson_sf(k, mean), 4)}  # fmt: skip


def our_gid(packets: Sequence[dict[str, Any]]) -> int | None:
    """PURE: the gid whose acts land on the targets of our own attack requests."""
    targets = {p["target_gid"] for p in packets if p.get("type") == "attack_request"}
    src = Counter(p["src_gid"] for p in packets
                  if p.get("type") == "act" and p.get("target_gid") in targets)  # fmt: skip
    return src.most_common(1)[0][0] if src else None


def first(rows: Sequence[dict[str, Any]], t0: int, t1: float, **eq: Any) -> dict[str, Any] | None:
    for r in rows:
        if t0 <= r["t_mono_ns"] <= t1 and all(r.get(k) == v for k, v in eq.items()):
            return r
    return None


def classify(strike_t: int, unlock_t: int | None, packets: Sequence[dict[str, Any]],
             gid: int | None) -> dict[str, Any]:  # fmt: skip
    """PURE: one strike's target, times (s after the click) and class K / A / B / C / D."""
    reqs = [p for p in packets if p.get("type") == "attack_request"]
    req = first(reqs, strike_t, strike_t + REQ_S * NS)
    rec: dict[str, Any] = {"unlock_s": None if unlock_t is None else
                           round((unlock_t - strike_t) / NS, 2)}  # fmt: skip
    if req is None:
        return {**rec, "class": "D", "target": None}
    tgt = req["target_gid"]
    acts = [p for p in packets if p.get("type") == "act" and p.get("src_gid") == gid
            and p.get("target_gid") == tgt and p["t_mono_ns"] >= strike_t]  # fmt: skip
    hit = next((p for p in acts if int(p.get("damage") or 0) > 0), None)
    gone = first([p for p in packets if p.get("type") == "entity_vanish"], strike_t, float("inf"),
                 gid=tgt)  # fmt: skip

    def s(p: dict[str, Any] | None) -> float | None:
        return None if p is None else round((p["t_mono_ns"] - strike_t) / NS, 2)

    rec.update(
        target=tgt,
        req_s=s(req),
        act_s=s(acts[0] if acts else None),
        hit_s=s(hit),
        vanish_s=s(gone),
        vanish_reason=None if gone is None else gone.get("reason"),
    )
    died = gone is not None and gone.get("reason") == DIED
    before = lambda t: unlock_t is None or t < unlock_t  # noqa: E731
    if died and before(gone["t_mono_ns"]):
        rec["class"] = "K"
    elif hit is not None and before(hit["t_mono_ns"]):
        rec["class"] = "A"
    elif hit is not None and hit["t_mono_ns"] - strike_t <= HIT_S * NS:
        rec["class"] = "B"
    else:
        rec["class"] = "C"
    rec["died_later"] = died and rec["class"] != "K"
    return rec


def strikes(events: Sequence[dict[str, Any]], packets: Sequence[dict[str, Any]],
            gid: int | None) -> list[dict[str, Any]]:  # fmt: skip
    """PURE: every strike, classed, with the first unlock after it (before the next strike).
    ``owned_s`` (rogue-xmas02.md 4Q, p10): the strike's click to the first of the next strike,
    its unlock and the next fight end -- the time it held the fight, lock or no lock (a
    --walk-stop strike takes none)."""
    sts = [e for e in events if e.get("kind") == "strike"]
    unl = [e["t_ns"] for e in events if e.get("kind") == "unlock"]
    ends = [e["t_ns"] for e in events if e.get("kind") == "fight_end"]
    out = []
    for i, st in enumerate(sts):
        nxt = sts[i + 1]["t_ns"] if i + 1 < len(sts) else float("inf")
        u = next((t for t in unl if st["t_ns"] < t < nxt), None)
        f = next((t for t in ends if st["t_ns"] < t < nxt), None)
        stop = min([t for t in (u, f, nxt) if t is not None])
        owned = None if stop == float("inf") else round((stop - st["t_ns"]) / NS, 2)
        rel = st.get("rel") or [0, 0]
        far = max(abs(rel[0]), abs(rel[1])) >= 2
        walking = any(p.get("type") == "self_move"
                      and st["t_ns"] - WALK_S * NS <= p["t_mono_ns"] <= st["t_ns"]
                      for p in packets)  # fmt: skip
        rec = {"t_ns": st["t_ns"], "by": st.get("by"), "end": st.get("end"),
               "owned_s": owned, "own_body": own_body(st), "far": far, "walking": walking,
               **classify(st["t_ns"], u, packets, gid)}  # fmt: skip
        if rec["class"] == "D":  # R1-A (Amendment R): did it lose an attack?
            rec["r1a"] = lost_attack(st["t_ns"], packets, gid)
        out.append(rec)
    return out


def far_strikes(classed: Sequence[dict[str, Any]],
                events: Sequence[dict[str, Any]]) -> dict[str, Any]:  # fmt: skip
    """PURE (4S, p12): the far strikes (2+ cells) by class and by walking at the click (a
    ``self_move`` of ours within WALK_S before it), and the --still-strike waits."""
    far = [c for c in classed if c.get("far")]
    rt = [e for e in events if e.get("kind") == "still_retarget"]
    return {
        "far": len(far),
        "far_d": sum(1 for c in far if c["class"] == "D"),
        "far_attacked": sum(1 for c in far if c["class"] != "D"),
        "far_d_walking": sum(1 for c in far if c["class"] == "D" and c.get("walking")),
        "far_walking": sum(1 for c in far if c.get("walking")),
        "retargets": len(rt),
        "retarget_lost": sum(1 for e in rt if e.get("verdict") != "sword"),
    }


def own_body(st: dict[str, Any]) -> bool:
    """PURE (4R): the strike's point lies on the Rogue's own sprite."""
    if st.get("u") is None or st.get("v") is None:
        return False
    u0, v0 = FEET_UV
    return abs(st["u"] - u0) <= SELF_HALF_W and v0 - SELF_UP <= st["v"] <= v0 + SELF_DOWN


def self_recheck(classed: Sequence[dict[str, Any]],
                 events: Sequence[dict[str, Any]]) -> dict[str, Any]:  # fmt: skip
    """PURE (4R, p11): the own-body strikes by class, and the --self-recheck second reads.
    ``own_body_d`` is class D as scored since 4R (unchanged); ``own_body_d_lost`` (R1-A, Amendment
    R) only those that lost an attack (``r1a``; a strike without the record counts as lost)."""
    ob = [c for c in classed if c.get("own_body")]
    rc = [e for e in events if e.get("kind") == "self_recheck"]
    ob_d = [c for c in ob if c["class"] == "D"]
    return {"own_body_strikes": len(ob), "own_body_d": len(ob_d),
            "own_body_d_lost": sum(1 for c in ob_d if (c.get("r1a") or {}).get("lost", True)),
            "own_body_attacked": sum(1 for c in ob if c["class"] != "D"),
            "rechecks": len(rc), "transient": sum(1 for e in rc if e.get("verdict2") != "sword"),
            "scan_attacked": sum(1 for c in classed if c.get("by") in ("scan", "stall_scan")
                                 and c["class"] != "D")}  # fmt: skip


def walk_stop(classed: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """PURE (rogue-xmas02.md 4Q, p10): the --walk-stop ends, the ones that cut a REAL strike short
    (an attack request came after all: not class D), and the class-D strikes' held time."""
    walked = [c for c in classed if c.get("end") == "walked"]
    d_owned = [c["owned_s"] for c in classed if c["class"] == "D" and c["owned_s"] is not None]
    return {"walked": len(walked), "walked_not_d": sum(1 for c in walked if c["class"] != "D"),
            "d": sum(1 for c in classed if c["class"] == "D"),
            "d_owned_s_p50": statistics.median(d_owned) if d_owned else None,
            "d_owned_s_sum": round(sum(d_owned), 2)}  # fmt: skip


def reader(packets: Sequence[dict[str, Any]], lines: Sequence[dict[str, Any]],
           gid: int | None) -> dict[str, Any]:  # fmt: skip
    """PURE: our damage acts matched (time order, one to one) to Battle Log damage lines."""
    acts = sorted(p["t_mono_ns"] for p in packets
                  if p.get("type") == "act" and p.get("src_gid") == gid
                  and int(p.get("damage") or 0) > 0)  # fmt: skip
    dmg = sorted(ln["t_ns"] for ln in lines if ln.get("type") == "damage")
    used: set[int] = set()
    lags = []
    for t in acts:
        j = next((k for k, d in enumerate(dmg) if k not in used and t <= d <= t + READ_S * NS),
                 None)  # fmt: skip
        if j is not None:
            used.add(j)
            lags.append((dmg[j] - t) / 1e6)
    q = sorted(lags)
    return {"our_hits": len(acts), "matched": len(lags),
            "share": round(len(lags) / len(acts), 3) if acts else None,
            "lag_ms_p50": round(q[len(q) // 2]) if q else None,
            "lag_ms_p95": round(q[min(len(q) - 1, int(0.95 * len(q)))]) if q else None,
            "damage_lines": len(dmg),
            "exp_packets": sum(1 for p in packets if p.get("type") == "stat_change"
                               and p.get("name") == "base_exp"),
            "exp_lines": sum(1 for ln in lines if ln.get("type") == "base_exp")}  # fmt: skip


def walking(
    events: Sequence[dict[str, Any]],
    packets: Sequence[dict[str, Any]],
    dets: Sequence[dict[str, Any]],
    classed: Sequence[dict[str, Any]],
) -> dict[str, Any]:
    """PURE: box engagements by whether we walked at their triggering detection's grab."""
    moves = sorted(p["t_mono_ns"] for p in packets if p.get("type") == "self_move")
    fights = [e for e in events if e.get("kind") in ("engage", "fight_end")]
    out: dict[str, Counter[str]] = {"walking": Counter(), "standing": Counter(),
                                    "no_detection": Counter()}  # fmt: skip
    for i, e in enumerate(fights):
        if e.get("kind") != "engage" or e.get("by") != "box":
            continue
        end = next((f["t_ns"] for f in fights[i + 1:] if f.get("kind") == "fight_end"),
                   float("inf"))  # fmt: skip
        det = next((d for d in reversed(dets) if d["t_ns"] <= e["t_ns"]), None)
        if det is None:
            key = "no_detection"
        else:
            grab = det["t_ns"] - float(det.get("ms") or 0.0) * 1e6
            key = "walking" if any(grab - WALK_S * NS <= m <= grab for m in moves) else "standing"
        out[key]["engagements"] += 1
        for c in classed:
            if e["t_ns"] <= c["t_ns"] <= end:
                out[key]["strikes"] += 1
                out[key]["kills"] += c["class"] == "K"
    return {k: dict(v) for k, v in out.items()}


def load(session: Path) -> dict[str, Any]:
    def jl(name: str) -> list[dict[str, Any]]:
        p = session / name
        return [json.loads(x) for x in p.read_text().splitlines() if x] if p.exists() else []

    with gzip.open(session / "packets.jsonl.gz", "rt") as fh:
        packets = sorted((json.loads(x) for x in fh if x.strip()), key=lambda p: p["t_mono_ns"])
    events, lines, dets = jl("events.jsonl"), jl("battle_log_live.jsonl"), jl("detections.jsonl")
    gid = our_gid(packets)
    classed = strikes(events, packets, gid)
    return {"session": session.name, "our_gid": gid, "strikes": classed,
            "classes": dict(Counter(c["class"] for c in classed)),
            "unlock_s_p50": statistics.median([c["unlock_s"] for c in classed
                                               if c["unlock_s"] is not None] or [0]),
            "walk_stop": walk_stop(classed),
            "self_recheck": self_recheck(classed, events),
            "far_strikes": far_strikes(classed, events),
            "reader": reader(packets, lines, gid),
            "walking": walking(events, packets, dets, classed) if dets else None}  # fmt: skip


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)  # fmt: skip
    ap.add_argument("sessions", type=Path, nargs="+")
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--r1-bar", action="store_true",
                    help="R1-A's bar over EXACTLY these sessions (the base runs only)")  # fmt: skip
    a = ap.parse_args(argv)
    res = [load(s) for s in a.sessions]
    text = json.dumps(res, indent=1)
    if a.out:
        a.out.write_text(text)
    for r in res:
        print(json.dumps({k: v for k, v in r.items() if k != "strikes"}))
    if a.r1_bar:
        runs = [[r["session"], r["self_recheck"]["own_body_d"],
                 r["self_recheck"]["own_body_d_lost"]] for r in res]  # fmt: skip
        print(json.dumps({"r1_bar": r1_bar([n for _s, _d, n in runs]),
                          "runs (session, own_body_d, own_body_d_lost)": runs}))  # fmt: skip
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
