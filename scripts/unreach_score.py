#!/usr/bin/env python3
"""rogue-xmas02.md Study S-UA's tool and the --unreach-escape pilots' scorer (dungeon@9.26): the
UNREACHABLE ATTACKER, judged by the packets.

    unreach_score.py study SESSION_DIR [...] [--ks 2,3,4,5] [--ws 15,20,30,45,60,90] [--out J]
    unreach_score.py score SESSION_DIR [...] [--out J]

OFFLINE ground truth only (packets, ADR-0007): nothing here reaches a runner. One clock: events'
``t_ns``, the Battle Log's ``t_ns`` and the packets' ``t_mono_ns`` are all CLOCK_MONOTONIC; times
are printed in s from the run's ``run_start``. The definitions below were fixed BEFORE the study's
grid was computed (2026-11-11 11:1x ICT, from ``date``):

- TRAP (packets): a span of our ``attack_request``s at ONE monster G -- consecutive requests at
  most GAP_S apart, none of our damaging acts (damage > 0) on G between them -- that lasts at
  least TRAP_S (its first request to its last, or to our first damaging act on G) while G acts on
  us (at least TRAP_ACTS acts with G as the source and us as the target inside it). Reported: its
  seconds, requests, G's acts on us (and hits), our stops on our own cell answering a request
  (same ms), and how it ended (``hit`` our damage on G, ``gone`` G vanished, ``fly`` our Fly Wing,
  ``walked`` a walk of ours that moved us, ``run_end``). SPANS: the same with TRAP_S = SPAN_S, so
  a trap an escape cut short is still seen.
- A NO-HIT LOCK (the runner's own events, rebuilt offline): a ``strike`` followed, before any
  other strike or unlock, by an ``unlock`` with why "no hits". Its start = the strike's
  ``t_end_ns`` (the lock's clock starts when strike() returns), its end = the unlock, its cell =
  the runner's held cell at the strike (the last main ``hp_read`` pos) + the strike's ``rel``,
  ``n`` = the strike's index. Its SIGN = the latest attacked sign up to its end: a ``miss_cue``
  event, a Battle Log ``taken`` line, or an HP drop (dungeon_hunt.hp_dropped over the run's HP
  reads, at each main read more than 2 s after a Fly Wing press). Our damage lines = the Battle
  Log's ``damage`` lines. (Online the runner's Miss tick is the LAST frame of a swing, offline the
  first: the replay is, if anything, stricter.)
- A TRIGGER: dungeon_hunt.unreach_trigger(locks, ours, K, W) after each no-hit lock, re-armed
  (the locks cleared) after it fires.
- ITS JUDGE (packets, over the chain's span [t0, t1]): ``trap`` = our attack requests at some
  monster G, no damaging act of ours on ANY monster, and G acted on us; ``harmful`` = a damaging
  act of ours (the escape would leave a fight she was winning: the Battle Log missed her lines);
  ``helpless`` = no damage of ours and a monster acted on us, but no request at one that did;
  ``quiet`` = the rest. A FALSE trigger is any other than ``trap``.
- THE RULE (Study S-UA, stated before the grid's table was read): a (K, W) is ELIGIBLE when it has
  0 false triggers over the sessions given (the base runs) AND catches p57's trap (every trap
  given, if more) within CATCH_S of its first request. K = the smallest eligible K; W = the
  largest eligible W at that K (the most tolerant of a slower lock cycle, at no false cost). No
  eligible pair: the fewest false triggers among the pairs that catch within CATCH_S, then the
  smaller K, then the smaller W; none catches: say so (no pick).
- ``score`` (the pilots): every ``unreach`` event of the runner judged as above on its own span
  (``t0_ns`` .. ``t_ns``); its action and, from the packets, its OUTCOME: the walk click's request
  (a ``self_move_request`` within REQ_S) and where the walk ended against its ``to``; the trap's
  attacker G (judged ``trap``): its acts on us in (t + AFTER_GRACE_S, t + AFTER_S] (``ended`` =
  none); our first damaging act after t; hits and HP lost on us in the next AFTER_HP_S; a Fly Wing
  within AFTER_S; a death. Beside them the packets' traps and spans, and the offline replay of the
  runner's own K / W (its fixes record) for the same runs, as a check.
"""

from __future__ import annotations

import argparse
import bisect
import gzip
import json
from collections import Counter, deque
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import dungeon_hunt as dh

NS = 1_000_000_000
GAP_S, TRAP_S, SPAN_S, TRAP_ACTS = 10.0, 20.0, 5.0, 2
STOP_NS = 2_000_000  # our entity_stop "answering" a request: within 2 ms of it (the same ms)
CATCH_S = 60.0
FLY_SETTLE_S = 2.0  # dungeon_hunt's main loop: no HP-drop sign within 2 s of a Fly Wing
REQ_S, AFTER_GRACE_S, AFTER_S, AFTER_HP_S = 1.5, 10.0, 60.0, 30.0
KS, WS = (2, 3, 4, 5), (15.0, 20.0, 30.0, 45.0, 60.0, 90.0)


def our_gid(packets: Sequence[dict[str, Any]]) -> int | None:
    """PURE: the gid whose acts land on the targets of our own attack requests (lock_study's)."""
    targets = {p["target_gid"] for p in packets if p.get("type") == "attack_request"}
    src = Counter(p["src_gid"] for p in packets
                  if p.get("type") == "act" and p.get("target_gid") in targets)  # fmt: skip
    return src.most_common(1)[0][0] if src else None


def _dmg(p: dict[str, Any]) -> int:
    return int(p.get("damage") or 0)


def _near(sorted_ts: Sequence[int], t: int, tol: int) -> bool:
    """PURE: some time in ``sorted_ts`` lies within ``tol`` of ``t``."""
    j = bisect.bisect_left(sorted_ts, t - tol)
    return j < len(sorted_ts) and sorted_ts[j] <= t + tol


def traps(packets: Sequence[dict[str, Any]], gid: int | None, min_s: float = TRAP_S,
          gap_s: float = GAP_S, min_acts: int = TRAP_ACTS) -> list[dict[str, Any]]:  # fmt: skip
    """PURE: the TRAPS (module doc): spans of our attack requests at one monster with no damage of
    ours on it, >= ``min_s`` long, while it acts on us >= ``min_acts`` times. Times in ns."""
    if gid is None:
        return []
    reqs: dict[int, list[int]] = {}
    ours: dict[int, list[int]] = {}
    on_us: dict[int, list[tuple[int, int]]] = {}
    stops: list[int] = []
    for p in packets:
        t, ty = p["t_mono_ns"], p.get("type")
        if ty == "attack_request":
            reqs.setdefault(p["target_gid"], []).append(t)
        elif ty == "act" and p.get("src_gid") == gid and _dmg(p) > 0:
            ours.setdefault(p["target_gid"], []).append(t)
        elif ty == "act" and p.get("target_gid") == gid and p.get("src_gid") != gid:
            on_us.setdefault(p["src_gid"], []).append((t, _dmg(p)))
        elif ty == "entity_stop" and p.get("gid") == gid:
            stops.append(t)
    out = []
    for g, ts in reqs.items():
        hits = sorted(ours.get(g, []))
        spans: list[list[int]] = []
        cur = [ts[0]]
        for t in ts[1:]:
            j = bisect.bisect_right(hits, cur[-1])
            if t - cur[-1] > gap_s * NS or (j < len(hits) and hits[j] <= t):
                spans.append(cur)
                cur = [t]
            else:
                cur.append(t)
        spans.append(cur)
        for sp in spans:
            a, b = sp[0], sp[-1]
            j = bisect.bisect_left(hits, a)
            first_hit = hits[j] if j < len(hits) else None
            end = first_hit if first_hit is not None and first_hit <= b else b
            if (end - a) / NS < min_s:
                continue
            acts = [x for x in on_us.get(g, []) if a <= x[0] <= end]
            if len(acts) < min_acts:
                continue
            n_req = sum(1 for t in sp if t <= end)
            stopped = sum(1 for t in sp if t <= end and _near(stops, t, STOP_NS))
            out.append({"gid": g, "start_ns": a, "end_ns": end, "s": round((end - a) / NS, 1),
                        "requests": n_req, "stopped": stopped, "acts_on_us": len(acts),
                        "hits_on_us": sum(1 for x in acts if x[1] > 0),
                        "damage_on_us": sum(x[1] for x in acts)})  # fmt: skip
    return sorted(out, key=lambda r: r["start_ns"])


def trap_end(trap: dict[str, Any], packets: Sequence[dict[str, Any]], gid: int | None,
             t_end_ns: int) -> dict[str, Any]:  # fmt: skip
    """PURE: how a trap ended -- the first after its end of: our damaging act on its monster
    (``hit``), the monster's vanish (``gone``), our Fly Wing request (``fly``), a walk of ours that
    moved us (``walked``); else ``run_end``; and the seconds from its end."""
    g, b = trap["gid"], trap["end_ns"]
    for p in packets:
        t = p["t_mono_ns"]
        if t < b:
            continue
        ty = p.get("type")
        how = None
        if ty == "act" and p.get("src_gid") == gid and p.get("target_gid") == g and _dmg(p) > 0:
            how = "hit"
        elif ty == "entity_vanish" and p.get("gid") == g:
            how = "gone"
        elif ty == "use_item_request":
            how = "fly"
        elif ty == "self_move" and (p.get("x0"), p.get("y0")) != (p.get("x1"), p.get("y1")):
            how = "walked"
        if how is not None:
            return {"by": how, "after_s": round((t - b) / NS, 1)}
    return {"by": "run_end", "after_s": round((t_end_ns - b) / NS, 1)}


def signs(events: Sequence[dict[str, Any]], lines: Sequence[dict[str, Any]]) -> list[float]:
    """PURE: the attacked signs' times (s, sorted): ``miss_cue`` events, ``taken`` lines, and the
    HP drops (dungeon_hunt.hp_dropped at each main HP read, > FLY_SETTLE_S after a Fly Wing)."""
    out = [e["t_ns"] / NS for e in events if e.get("kind") == "miss_cue"]
    out += [ln["t_ns"] / NS for ln in lines if ln.get("type") == "taken"]
    hist: deque[tuple[float, float]] = deque()
    fly_at = -1e18
    for e in events:
        if e.get("kind") == "press" and e.get("what") == "fly":
            fly_at = e["t_ns"] / NS
        if e.get("kind") != "hp_read" or e.get("pct") is None:
            continue
        t = e["t_ns"] / NS
        hist.append((t, float(e["pct"]) / 100.0))
        while hist and hist[0][0] < t - dh.HP_DROP_S - 1.0:
            hist.popleft()
        if not e.get("quick") and t - fly_at > FLY_SETTLE_S and dh.hp_dropped(list(hist), t):
            out.append(t)
    return sorted(out)


def no_hit_locks(events: Sequence[dict[str, Any]],
                 lines: Sequence[dict[str, Any]]) -> list[dh.NoHitLock]:  # fmt: skip
    """PURE: the runner's no-hit locks rebuilt from its events (module doc)."""
    sg = signs(events, lines)
    here: tuple[int, int] | None = None
    n = 0
    cur: tuple[float, tuple[int, int] | None, int] | None = None
    out = []
    for e in events:
        k = e.get("kind")
        if k == "hp_read" and not e.get("quick") and e.get("pos"):
            here = (int(e["pos"][0]), int(e["pos"][1]))
        elif k == "strike":
            n += 1
            rel = e.get("rel") or [0, 0]
            cell = None if here is None else (here[0] + int(rel[0]), here[1] + int(rel[1]))
            cur = (float(e.get("t_end_ns", e["t_ns"])) / NS, cell, n)
        elif k == "unlock":
            if cur is not None and e.get("why") == "no hits":
                t1 = e["t_ns"] / NS
                j = bisect.bisect_right(sg, t1)
                out.append(dh.NoHitLock(t0=cur[0], t1=t1, cell=cur[1], n=cur[2],
                                        sign_t=sg[j - 1] if j else -1e18))  # fmt: skip
            cur = None
    return out


def replay(locks: Sequence[dh.NoHitLock], ours: Sequence[float], k: int,
           w: float) -> list[dict[str, Any]]:  # fmt: skip
    """PURE: the triggers dungeon_hunt.unreach_trigger gives over ``locks`` in order, re-armed
    (the locks cleared) after each one fires."""
    got: list[dh.NoHitLock] = []
    out = []
    for lk in locks:
        got.append(lk)
        tr = dh.unreach_trigger(got, ours, k, w)
        if tr is not None:
            out.append(tr)
            got = []
    return out


def judge(t0_ns: int, t1_ns: int, packets: Sequence[dict[str, Any]],
          gid: int | None) -> dict[str, Any]:  # fmt: skip
    """PURE: a trigger's verdict over its span (module doc): trap / harmful / helpless / quiet."""
    win = [p for p in packets if t0_ns <= p["t_mono_ns"] <= t1_ns]
    ours = [p for p in win if p.get("type") == "act" and p.get("src_gid") == gid and _dmg(p) > 0]
    attackers = {p["src_gid"] for p in win if p.get("type") == "act"
                 and p.get("target_gid") == gid and p.get("src_gid") != gid}  # fmt: skip
    asked = {p["target_gid"] for p in win if p.get("type") == "attack_request"}
    both = sorted(asked & attackers)
    if ours:
        verdict = "harmful"
    elif both:
        verdict = "trap"
    elif attackers:
        verdict = "helpless"
    else:
        verdict = "quiet"
    return {"verdict": verdict, "attacker": both[0] if both else None,
            "our_hits": len(ours), "attackers": len(attackers), "asked": len(asked)}  # fmt: skip


def load(session: Path) -> dict[str, Any]:
    def jl(name: str) -> list[dict[str, Any]]:
        p = session / name
        if not p.exists():
            return []
        return [json.loads(x) for x in p.read_text().splitlines() if x.strip()]

    with gzip.open(session / "packets.jsonl.gz", "rt") as fh:
        packets = sorted((json.loads(x) for x in fh if x.strip()), key=lambda p: p["t_mono_ns"])
    events, lines = jl("events.jsonl"), jl("battle_log_live.jsonl")
    t0 = next((e["t_ns"] for e in events if e.get("kind") == "run_start"), events[0]["t_ns"])
    t_end = max([events[-1]["t_ns"], packets[-1]["t_mono_ns"] if packets else 0])
    return {"name": session.name.rsplit("-", 1)[-1], "events": events, "lines": lines,
            "packets": packets, "t0": t0, "t_end": t_end, "gid": our_gid(packets),
            "ours": [ln["t_ns"] / NS for ln in lines if ln.get("type") == "damage"]}  # fmt: skip


def run_traps(r: dict[str, Any], min_s: float) -> list[dict[str, Any]]:
    """The run's traps (``min_s``), each with its end and times in s from the run start."""
    out = []
    for tp in traps(r["packets"], r["gid"], min_s=min_s):
        tp = {**tp, "end": trap_end(tp, r["packets"], r["gid"], r["t_end"]),
              "start_s": round((tp["start_ns"] - r["t0"]) / NS, 1),
              "end_s": round((tp["end_ns"] - r["t0"]) / NS, 1)}  # fmt: skip
        out.append(tp)
    return out


def triggers(r: dict[str, Any], locks: Sequence[dh.NoHitLock], k: int,
             w: float) -> list[dict[str, Any]]:  # fmt: skip
    """The run's replayed triggers at (K, W), judged, times in s from the run start."""
    out = []
    for tr in replay(locks, r["ours"], k, w):
        j = judge(round(tr["t0"] * NS), round(tr["t1"] * NS), r["packets"], r["gid"])
        out.append({**tr, **j, "t0_s": round((tr["t0"] * NS - r["t0"]) / NS, 1),
                    "t1_s": round((tr["t1"] * NS - r["t0"]) / NS, 1)})  # fmt: skip
    return out


def catch_s(trap: dict[str, Any], trigs: Sequence[dict[str, Any]]) -> float | None:
    """PURE: seconds from the trap's first request to the first trigger fired inside it (its end
    + 2 s at most), else None."""
    a, b = float(trap["start_ns"]) / NS, float(trap["end_ns"]) / NS + 2.0
    for tr in trigs:
        t1 = float(tr["t1"])
        if a <= t1 <= b:
            return round(t1 - a, 1)
    return None


def pick(rows: Sequence[dict[str, Any]], catch_max: float = CATCH_S) -> dict[str, Any]:
    """PURE: THE RULE (module doc) over grid rows {k, w, false, caught_all (bool: every trap within
    ``catch_max``)}: the chosen (k, w) and how."""
    elig = [r for r in rows if r["false"] == 0 and r["caught_all"]]
    if elig:
        k = min(r["k"] for r in elig)
        w = max(r["w"] for r in elig if r["k"] == k)
        return {"k": k, "w": w, "how": "eligible: 0 false, every trap caught within "
                f"{catch_max:g} s; the smallest K, the largest W at it"}  # fmt: skip
    catching = [r for r in rows if r["caught_all"]]
    if not catching:
        return {"k": None, "w": None, "how": "no pair catches every trap within the limit"}
    best = min(catching, key=lambda r: (r["false"], r["k"], r["w"]))
    return {"k": best["k"], "w": best["w"], "how": f"no eligible pair: the fewest false "
            f"({best['false']}), then the smaller K, then the smaller W"}  # fmt: skip


def study(runs: Sequence[dict[str, Any]], ks: Sequence[int], ws: Sequence[float]) -> dict[str, Any]:
    locks = {r["name"]: no_hit_locks(r["events"], r["lines"]) for r in runs}
    tps = {r["name"]: run_traps(r, TRAP_S) for r in runs}
    rows = []
    for k in ks:
        for w in ws:
            trs = {r["name"]: triggers(r, locks[r["name"]], k, w) for r in runs}
            verdicts = Counter(t["verdict"] for v in trs.values() for t in v)
            catches = [catch_s(tp, trs[n]) for n, v in tps.items() for tp in v]
            false_at = [[n, t["t1_s"], t["verdict"], t["cells"], t["span_s"]]
                        for n, v in trs.items() for t in v if t["verdict"] != "trap"]  # fmt: skip
            rows.append({"k": k, "w": w, "triggers": sum(verdicts.values()),
                         "true": verdicts.get("trap", 0),
                         "false": sum(n for v, n in verdicts.items() if v != "trap"),
                         "by_verdict": dict(verdicts), "catch_s": catches,
                         "caught_all": bool(catches) and all(c is not None and c <= CATCH_S
                                                             for c in catches),
                         "false_at": false_at})  # fmt: skip
    return {"runs": [r["name"] for r in runs],
            "no_hit_locks": {n: len(v) for n, v in locks.items()},
            "traps": {n: [{k: v for k, v in tp.items() if not k.endswith("_ns")} for tp in v]
                      for n, v in tps.items() if v},
            "grid": rows, "pick": pick(rows)}  # fmt: skip


def outcome(ev: dict[str, Any], r: dict[str, Any], attacker: int | None) -> dict[str, Any]:
    """PURE (score): one escape's outcome from the packets (module doc)."""
    t, pk, gid = ev["t_ns"], r["packets"], r["gid"]
    after = [p for p in pk if t <= p["t_mono_ns"] <= t + AFTER_S * NS]
    out: dict[str, Any] = {}
    if ev.get("action") == "walk":
        req = next((p for p in after if p.get("type") == "self_move_request"
                    and p["t_mono_ns"] <= t + REQ_S * NS), None)  # fmt: skip
        out["walk_sent"] = req is not None
        mv = next((p for p in after if p.get("type") == "self_move" and req is not None
                   and p["t_mono_ns"] >= req["t_mono_ns"]), None)  # fmt: skip
        to = ev.get("to")
        out["walk_to"] = None if mv is None else [mv.get("x1"), mv.get("y1")]
        out["walk_err"] = (
            None
            if mv is None or not to
            else max(abs(int(mv["x1"]) - int(to[0])), abs(int(mv["y1"]) - int(to[1])))
        )
    if attacker is not None:
        late = [
            p
            for p in after
            if p.get("type") == "act"
            and p.get("src_gid") == attacker
            and p.get("target_gid") == gid
            and p["t_mono_ns"] > t + AFTER_GRACE_S * NS
        ]
        out["attacker_acts_after"] = len(late)
        out["ended"] = not late
        hit_g = next((p for p in after if p.get("type") == "act" and p.get("src_gid") == gid
                      and p.get("target_gid") == attacker and _dmg(p) > 0), None)  # fmt: skip
        out["hit_attacker_s"] = None if hit_g is None else round((hit_g["t_mono_ns"] - t) / NS, 1)
    first = next((p for p in pk if p["t_mono_ns"] > t and p.get("type") == "act"
                  and p.get("src_gid") == gid and _dmg(p) > 0), None)  # fmt: skip
    out["next_our_hit_s"] = None if first is None else round((first["t_mono_ns"] - t) / NS, 1)
    hp = [
        p
        for p in after
        if p.get("type") == "act"
        and p.get("target_gid") == gid
        and p.get("src_gid") != gid
        and _dmg(p) > 0
        and p["t_mono_ns"] <= t + AFTER_HP_S * NS
    ]
    out["hits_on_us_30s"] = len(hp)
    out["damage_on_us_30s"] = sum(_dmg(p) for p in hp)
    out["fly_60s"] = any(p.get("type") == "use_item_request" for p in after)
    out["death_60s"] = any(e.get("kind") == "death" and t <= e["t_ns"] <= t + AFTER_S * NS
                           for e in r["events"])  # fmt: skip
    return out


def _strip_ns(rows: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{a: b for a, b in x.items() if not a.endswith("_ns")} for x in rows]


def score(runs: Sequence[dict[str, Any]]) -> dict[str, Any]:
    res = []
    for r in runs:
        start: dict[str, Any] = next((e for e in r["events"] if e.get("kind") == "run_start"), {})
        fx = (start.get("fixes") or {}).get("unreach_escape")
        k, w = (int(fx[0]), float(fx[1])) if fx else (dh.UNREACH_K, dh.UNREACH_W_S)
        esc = []
        for ev in (e for e in r["events"] if e.get("kind") == "unreach"):
            t0n = int(ev.get("t0_ns") or ev["t_ns"] - round(float(ev.get("span_s") or 0) * NS))
            j = judge(t0n, ev["t_ns"], r["packets"], r["gid"])
            esc.append({"t_s": round((ev["t_ns"] - r["t0"]) / NS, 1), "action": ev.get("action"),
                        "why": ev.get("why"), "cells": ev.get("cells"), "to": ev.get("to"),
                        "span_s": ev.get("span_s"), **j,
                        **outcome(ev, r, j["attacker"])})  # fmt: skip
        locks = no_hit_locks(r["events"], r["lines"])
        rep = triggers(r, locks, k, w)
        tps, sps = run_traps(r, TRAP_S), run_traps(r, SPAN_S)
        res.append({"run": r["name"], "unreach_fixes": fx, "k": k, "w": w,
                    "traps": _strip_ns(tps), "trap_s": round(sum(x["s"] for x in tps), 1),
                    "spans": _strip_ns(sps), "span_s": round(sum(x["s"] for x in sps), 1),
                    "escapes": esc,
                    "escapes_false": sum(1 for x in esc if x["verdict"] != "trap"),
                    "replay": [{a: b for a, b in x.items() if a not in ("t0", "t1")}
                               for x in rep]})  # fmt: skip
    pooled = {"runs": len(res), "traps": sum(len(x["traps"]) for x in res),
              "trap_s": round(sum(x["trap_s"] for x in res), 1),
              "spans": sum(len(x["spans"]) for x in res),
              "span_s": round(sum(x["span_s"] for x in res), 1),
              "escapes": sum(len(x["escapes"]) for x in res),
              "escapes_false": sum(x["escapes_false"] for x in res),
              "actions": dict(Counter(f"{e['action']}:{e['why']}" for x in res
                                      for e in x["escapes"]))}  # fmt: skip
    return {"runs": res, "pooled": pooled}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)  # fmt: skip
    ap.add_argument("mode", choices=("study", "score"))
    ap.add_argument("sessions", type=Path, nargs="+")
    ap.add_argument("--ks", default=",".join(str(k) for k in KS))
    ap.add_argument("--ws", default=",".join(f"{w:g}" for w in WS))
    ap.add_argument("--out", type=Path, default=None)
    a = ap.parse_args(argv)
    runs = [load(s) for s in a.sessions]
    if a.mode == "study":
        ks = [int(x) for x in a.ks.split(",")]
        ws = [float(x) for x in a.ws.split(",")]
        res = study(runs, ks, ws)
        for row in res["grid"]:
            print(json.dumps({k: v for k, v in row.items() if k != "false_at"}))
        print(json.dumps({"traps": res["traps"], "pick": res["pick"]}))
    else:
        res = score(runs)
        for x in res["runs"]:
            print(json.dumps({k: v for k, v in x.items() if k not in ("spans", "replay")}))
        print(json.dumps({"pooled": res["pooled"]}))
    if a.out:
        a.out.write_text(json.dumps(res, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
