#!/usr/bin/env python3
"""rogue-xmas02.md Study S-LF's scorer (Amendment Q, 4BH; committed for Amendment R, 4BI, before
any pilot uses it): the light-floor position reader in a dungeon_hunt run, against the packets.

    slf_score.py SESSION_DIR [SESSION_DIR ...] [--out OUT.json]

OFFLINE ground truth only (packets, ADR-0007): nothing here reaches a runner. Our cell over time
is time_budget.Track (the packets' self_move steps and pins). The definitions are slf2.py's (the
study's, NAS scratch-archive/2026-11-10/study-lf-r1/), fixed before its numbers were read:

- a MAIN read is an ``hp_read`` event with ``rd``. It is FRESH (``base`` / ``light``: it moved
  ``here``), FAILED (``unconfirmed``, ``light_failed:*``, ``base:*``, any other) or SETTLE (no read
  after a Fly Wing). The fresh share is fresh / main reads.
- a READER SPAN opens at a failed read after a fresh one and closes at the next fresh read, a Fly
  Wing's request (``use_item_request``) or the run's end. ``attrib_s`` = close - open (the reader's
  seconds), ``gap_s`` = close - the last fresh read. PERSISTENT = >= PERSIST failed reads;
  UNCONFIRMED-ONLY = every failed read ``unconfirmed`` (PosConfirm held a light read back); LATE =
  its first failed read is ``unconfirmed`` and came > LATE_S after the read before it (LF-2's
  case: PosConfirm's dt when the run logs LF-1's ``held_dt``, else the gap to the previous MAIN
  read -- ``late_basis`` says which).
- every clicked ``walk`` is FRESH (the last main read fresh and <= FRESH_AGE_S old), READER (a
  failed read since the last fresh one: a STALE walk), BLOCKED (no read since a fresh one more than
  FRESH_AGE_S old) or none. Its HERE ERROR = Chebyshev(our packet cell at its request, its
  ``from``); its LANDING ERROR = Chebyshev(its request's cell, its ``to``); UNSENT = no
  ``self_move_request`` within REQ_WIN of it (walk_refusals.py's W1 window). In p36-p47 no walk
  was FRESH: a walk event comes >= ~0.7 s after the tick's read (the cursor check before the
  click), so the study's "other" walks are the BLOCKED ones.
- ``reach_skip`` events get the same class at their time and a here error (their ``here``).
- the ``pos_unread`` escapes (``stuck`` events): when, ``here`` against the packets, the seconds
  since the last fresh read, and whether a SENT walk click was < ESCAPE_WALK_S old (LF-4's rule).
- 0 WRONG: a fresh read while STANDING more than WRONG_CELLS from our packet cell; and the
  runner's ``jump`` hard bars. STANDING = our packet cell unchanged (steps AND pins: a server
  ``entity_stop`` that moves us counts) for STAND_GUARD_S before the read. Not the moving
  intervals: the track times a walk as a straight line, so a detour arrives later than it says,
  and a pin moves us without a walk (p44 1497.2 s, p45 793.8 s: the read 0.02-0.05 s after a pin
  still showed the client's cell). Each wrong read lists ``still_s`` (how long the cell had been
  the same) so a person can judge it. p36-p47: 1 of 26,223 standing fresh reads, p46 587.71 /
  587.92 s: two agreeing light reads (93,77), still_s 1.19 after a straight 6-cell walk (the
  server grid has no detour there), a base read (93,73) 0.4 s later -- a light misread that
  PosConfirm accepted (a guard of 2.0 s would have hidden it: 0 of 22,448).
- LF-1 / LF-2 (dungeon@9.21; read when the run logged them): each held-back read's value
  (``held``) against the packets, its ``held_dt``; the LF-2 outcomes (``lf2``) and the cells LF-2
  confirmed against the packets.
- LF-4 (dungeon@9.22, ``--unread-step``; read when the run logged ``unread_step`` events): every
  escape's events (``wait`` / ``step`` / ``fresh`` / ``wing`` / ``refused`` / ``fly``); each STEP
  is SENT when a ``self_move_request`` lies within REQ_WIN of it, and its LANDING ERROR =
  Chebyshev(the request's cell, our packet cell at the step + its ``rel``); each FRESH end's read
  against our packet cell (``err``). An escape that ends ``fresh`` with no step was ended by the
  walk (a) waited for.

Medians and quantiles are the study's: the sorted value at index int(p x n) (the upper median).
The pooled block sums the given sessions (pass the base runs you mean, e.g. p40-p47 without p43).
"""

from __future__ import annotations

import argparse
import bisect
import gzip
import json
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

NS = 1_000_000_000
FRESH = frozenset({"base", "light"})
FRESH_AGE_S = 0.6
PERSIST = 5
REQ_WIN = (-0.3, 1.2)  # walk_refusals.py's W1 window around a walk event (s)
LATE_S = 1.0  # dungeon_hunt.CONFIRM_S: a light read this long after the read before is held back
STAND_GUARD_S = 1.0  # standing = our packet cell unchanged this long before the read
WRONG_CELLS = 2  # a fresh read farther than this from the packets while standing is WRONG
ESCAPE_WALK_S = 2.0  # LF-4: no pos_unread wing while a sent walk click is younger than this
GAP_LONG_S = 20.0  # dungeon_hunt.POS_FLY_S: spans whose gap reaches it


def cheb(a: Sequence[int], b: Sequence[int]) -> int:
    return max(abs(int(a[0]) - int(b[0])), abs(int(a[1]) - int(b[1])))


def q(xs: Sequence[float], p: float) -> float | None:
    """The study's quantile: the sorted value at index int(p x n)."""
    if not xs:
        return None
    s = sorted(xs)
    return s[min(len(s) - 1, int(p * len(s)))]


def status(rd: str | None) -> str:
    """PURE: a main read's outcome as fresh / settle / failed."""
    if rd in FRESH:
        return "fresh"
    if rd == "settle":
        return "settle"
    return "failed"


def read_class(reads: Sequence[Mapping[str, Any]], rt: Sequence[int],
               t: int) -> tuple[str, float | None]:  # fmt: skip
    """PURE: FRESH / READER / BLOCKED / none at ``t`` from the main reads before it, and the age (s)
    of the last fresh read."""
    i = bisect.bisect_right(rt, t) - 1
    if i < 0:
        return "none", None
    j, failed = i, False
    while j >= 0 and status(reads[j]["rd"]) != "fresh":
        failed = failed or status(reads[j]["rd"]) == "failed"
        j -= 1
    if j < 0:
        return "none", None
    age = round((t - reads[j]["t_ns"]) / NS, 2)
    if failed:
        return "reader", age
    if j == i and age <= FRESH_AGE_S:
        return "fresh", age
    return "blocked", age


def reader_spans(reads: Sequence[Mapping[str, Any]], t_end: int,
                 fly_req: Sequence[int]) -> list[dict[str, Any]]:  # fmt: skip
    """PURE: the reader spans (open / close in ns, the failed reads, the last fresh read before,
    what closed it) from the main reads in time order."""
    spans: list[dict[str, Any]] = []
    cur: dict[str, Any] | None = None
    last_fresh: int | None = None
    for r in [*reads, {"t_ns": t_end, "rd": "base", "_end": True}]:
        st, t = status(r["rd"]), int(r["t_ns"])
        if cur is not None:
            fly = next((f for f in fly_req if cur["open"] < f <= t), None)
            if st == "fresh" or fly is not None:
                cur["close"] = fly if fly is not None else t
                cur["closed_by"] = "fly" if fly is not None else "end" if r.get("_end") else "fresh"
                spans.append(cur)
                cur = None
        if st == "failed" and not r.get("_end"):
            if cur is None:
                cur = {"open": t, "last_fresh": last_fresh, "fails": [], "here": r.get("pos")}
            cur["fails"].append(r)
        if st == "fresh" and not r.get("_end"):
            last_fresh = t
    return spans


def span_row(sp: Mapping[str, Any], reads: Sequence[Mapping[str, Any]], rt: Sequence[int],
             fights: Sequence[tuple[int, int]], t0: int, track: Any) -> dict[str, Any]:  # fmt: skip
    """PURE (given the track): one span's record."""
    a, b = int(sp["open"]), int(sp["close"])
    lf = sp["last_fresh"] if sp["last_fresh"] is not None else a
    fails = sp["fails"]
    i = bisect.bisect_left(rt, a)
    prev_raw = (a - rt[i - 1]) / NS if i > 0 else None  # compared unrounded (1.004 s is late)
    prev_gap = None if prev_raw is None else round(prev_raw, 2)
    first = fails[0]
    if "held_dt" in first:  # LF-1 logged PosConfirm's own dt (None = no read before it)
        dt = first["held_dt"]
        late_by, basis = dt is None or dt > LATE_S, "lf1"
    else:
        late_by, basis = prev_raw is None or prev_raw > LATE_S, "main_gap"
    unconfirmed_only = all(r["rd"] == "unconfirmed" for r in fails)
    true0 = track.us(first["t_ns"]) if track is not None else None
    return {
        "t": round((a - t0) / NS, 2), "attrib_s": round((b - a) / NS, 2),
        "gap_s": round((b - lf) / NS, 2), "closed_by": sp["closed_by"], "n_failed": len(fails),
        "why": dict(Counter(r["rd"] for r in fails)), "persistent": len(fails) >= PERSIST,
        "unconfirmed_only": unconfirmed_only,
        "late": first["rd"] == "unconfirmed" and late_by, "late_basis": basis,
        "prev_read_gap_s": prev_gap, "here": sp["here"],
        "true": None if true0 is None else list(true0),
        "fight_s": round(sum(max(0, min(b, fb) - max(a, fa)) for fa, fb in fights) / NS, 2),
        "_open": a, "_close": b,
    }  # fmt: skip


def fights_of(events: Sequence[Mapping[str, Any]]) -> list[tuple[int, int]]:
    """PURE: (engage, fight_end) intervals."""
    out: list[tuple[int, int]] = []
    op: int | None = None
    for e in events:
        if e["kind"] == "engage" and op is None:
            op = int(e["t_ns"])
        elif e["kind"] == "fight_end" and op is not None:
            out.append((op, int(e["t_ns"])))
            op = None
    return out


def request_at(reqs: Sequence[Mapping[str, Any]], req_t: Sequence[int],
               t: int) -> Mapping[str, Any] | None:  # fmt: skip
    """PURE: the first self_move_request within REQ_WIN of ``t`` (W1's window), else None."""
    i = bisect.bisect_left(req_t, t + int(REQ_WIN[0] * NS))
    if i < len(reqs) and req_t[i] <= t + int(REQ_WIN[1] * NS):
        return reqs[i]
    return None


def change_times(points: Sequence[tuple[int, Sequence[int]]]) -> list[int]:
    """PURE: the times at which our track's cell changes (its first point included)."""
    out: list[int] = []
    prev: tuple[int, int] | None = None
    for t, c in points:
        cell = (int(c[0]), int(c[1]))
        if cell != prev:
            out.append(int(t))
            prev = cell
    return out


def still_s(changes: Sequence[int], t: int) -> float | None:
    """PURE: seconds our packet cell has been the same at ``t`` (None before the first point)."""
    i = bisect.bisect_right(changes, t) - 1
    return None if i < 0 else round((t - changes[i]) / NS, 2)


def analyse(events: Sequence[Mapping[str, Any]], packets: Sequence[Mapping[str, Any]],
            label: str = "") -> dict[str, Any]:  # fmt: skip
    """PURE: one run's rows and summary (events and packets each in time order)."""
    import time_budget as tb

    t0 = next(int(e["t_ns"]) for e in events if e["kind"] == "run_start")
    t1 = next((int(e["t_ns"]) for e in events if e["kind"] == "run_end"), int(events[-1]["t_ns"]))
    tr = tb.Track(packets)
    reads = [e for e in events if e["kind"] == "hp_read" and "rd" in e]
    rt = [int(e["t_ns"]) for e in reads]
    fly_req = [int(p["t_mono_ns"]) for p in packets if p.get("type") == "use_item_request"]
    reqs = [p for p in packets if p.get("type") == "self_move_request"]
    req_t = [int(p["t_mono_ns"]) for p in reqs]
    fights = fights_of(events)

    def rel_s(t: int) -> float:
        return round((t - t0) / NS, 2)

    spans = [span_row(sp, reads, rt, fights, t0, tr)
             for sp in reader_spans(reads, t1, fly_req)]  # fmt: skip

    walks = []
    for e in events:
        if e["kind"] != "walk" or not e.get("clicked"):
            continue
        t = int(e["t_ns"])
        r = request_at(reqs, req_t, t)
        k, age = read_class(reads, rt, t)
        true = tr.us(int(r["t_mono_ns"]) if r else t)
        sp = next((s for s in spans if s["_open"] <= t < s["_close"]), None)
        walks.append({
            "t": rel_s(t), "t_ns": t, "class": k, "age_s": age, "from": e.get("from"),
            "to": e.get("to"), "sent": r is not None,
            "req": None if r is None else [r["x"], r["y"]],
            "here_err": None if true is None or e.get("from") is None else cheb(true, e["from"]),
            "err": None if r is None or e.get("to") is None else cheb((r["x"], r["y"]), e["to"]),
            "span_t": None if sp is None else sp["t"],
            "in_unconfirmed_only": sp is not None and sp["unconfirmed_only"],
            "in_late": sp is not None and sp["late"],
        })  # fmt: skip
    reach = []
    for e in events:
        if e["kind"] != "reach_skip":
            continue
        t = int(e["t_ns"])
        k, age = read_class(reads, rt, t)
        true = tr.us(t)
        here = e.get("here")
        reach.append({"t": rel_s(t), "class": k, "age_s": age,
                      "here_err": None if true is None or here is None
                      else cheb(true, here)})  # fmt: skip
    escapes = []
    fresh_t = [int(r["t_ns"]) for r in reads if status(r["rd"]) == "fresh"]
    for e in events:
        if e["kind"] != "stuck" or e.get("why") != "pos_unread":
            continue
        t = int(e["t_ns"])
        j = bisect.bisect_right(fresh_t, t) - 1
        true = tr.us(t)
        sp = next((s for s in spans if s["_open"] <= t <= s["_close"] + NS), None)
        sent = [w for w in walks if w["sent"] and 0 <= t - w["t_ns"] < ESCAPE_WALK_S * NS]
        escapes.append({
            "t": rel_s(t), "at": e.get("at"), "true": None if true is None else list(true),
            "here_err": None if true is None or e.get("at") is None else cheb(true, e["at"]),
            "since_fresh_s": None if j < 0 else round((t - fresh_t[j]) / NS, 2),
            "span": None if sp is None else {k: v for k, v in sp.items() if not k.startswith("_")},
            "walk_sent_lt_2s": bool(sent),
        })  # fmt: skip
    changes = change_times(tr.points)
    wrong, n_stand = [], 0
    for r in reads:
        if status(r["rd"]) != "fresh" or r.get("pos") is None:
            continue
        t = int(r["t_ns"])
        true, still = tr.us(t), still_s(changes, t)
        if true is None or still is None or still < STAND_GUARD_S:
            continue
        n_stand += 1
        if cheb(true, r["pos"]) > WRONG_CELLS:
            wrong.append({"t": rel_s(t), "rd": r["rd"], "pos": r["pos"], "true": list(true),
                          "still_s": still, "lf2": r.get("lf2")})  # fmt: skip
    held = []
    for r in reads:
        if r.get("held") is None:
            continue
        true, still = tr.us(int(r["t_ns"])), still_s(changes, int(r["t_ns"]))
        held.append({"t": rel_s(int(r["t_ns"])), "held": r["held"], "held_dt": r.get("held_dt"),
                     "lf2": r.get("lf2"), "rd": r["rd"],
                     "err": None if true is None else cheb(true, r["held"]),
                     "standing": still is not None and still >= STAND_GUARD_S})  # fmt: skip
    lf2 = Counter(str(r["lf2"]) for r in reads if r.get("lf2") is not None)
    lf4 = []
    for e in events:
        if e["kind"] != "unread_step":
            continue
        t = int(e["t_ns"])
        true = tr.us(t)
        row: dict[str, Any] = {"t": rel_s(t), "event": e.get("event"), "why": e.get("why"),
                               "steps": e.get("steps", e.get("n"))}  # fmt: skip
        if e.get("event") == "step":
            r = request_at(reqs, req_t, t)
            rel = e.get("rel") or [0, 0]
            aim = None if true is None else (true[0] + rel[0], true[1] + rel[1])
            got = None if r is None else (r["x"], r["y"])
            row.update(rel=rel, sent=r is not None, true=None if true is None else list(true),
                       req=None if got is None else list(got),
                       err=None if got is None or aim is None else cheb(got, aim))  # fmt: skip
        elif e.get("event") == "fresh":
            at = e.get("at")
            row.update(at=at, true=None if true is None else list(true),
                       err=None if true is None or at is None else cheb(true, at))  # fmt: skip
        lf4.append(row)
    for s in spans:
        s.pop("_open")
        s.pop("_close")
    for w in walks:
        w.pop("t_ns")
    rows = {"reads": [{"rd": r["rd"]} for r in reads], "spans": spans, "walks": walks,
            "reach_skips": reach, "escapes": escapes, "wrong": wrong, "standing_fresh": n_stand,
            "held": held, "lf2": dict(lf2), "lf4": lf4,
            "jumps": sum(1 for e in events if e["kind"] == "jump"),
            "minutes": round((t1 - t0) / NS / 60, 2)}  # fmt: skip
    return {"label": label, "minutes": rows["minutes"], "summary": summary([rows]), **rows}


def summary(runs: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """PURE: the measures over one or more runs' rows (the pre-registration's list, S-LF)."""
    reads = [r["rd"] for run in runs for r in run["reads"]]
    spans = [s for run in runs for s in run["spans"]]
    walks = [w for run in runs for w in run["walks"]]
    reach = [x for run in runs for x in run["reach_skips"]]
    n = len(reads)
    out_c = Counter(reads)
    fresh = sum(v for k, v in out_c.items() if status(k) == "fresh")

    def spans_of(ss: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
        return {"n": len(ss), "s": round(sum(s["attrib_s"] for s in ss), 1),
                "max_s": max((s["attrib_s"] for s in ss), default=None),
                "p50_s": q([s["attrib_s"] for s in ss], 0.5)}  # fmt: skip

    def walks_of(ws: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
        he = [w["here_err"] for w in ws if w["here_err"] is not None]
        le = [w["err"] for w in ws if w["err"] is not None]
        uns = sum(1 for w in ws if not w["sent"])
        return {"n": len(ws), "here_err_p50": q(he, 0.5), "here_err_ge5": sum(e >= 5 for e in he),
                "landing_p50": q(le, 0.5), "landing_n": len(le),
                "landing_ge5": sum(e >= 5 for e in le),
                "landing_ge5_share": round(sum(e >= 5 for e in le) / len(le), 4) if le else None,
                "unsent": uns, "unsent_share": round(uns / len(ws), 4) if ws else None}  # fmt: skip

    stale = [w for w in walks if w["class"] == "reader"]
    held = [h for run in runs for h in run["held"]]
    lf4 = [x for run in runs for x in run.get("lf4", [])]
    lf4_steps = [x for x in lf4 if x["event"] == "step"]
    lf4_fresh = [x for x in lf4 if x["event"] == "fresh"]
    lf2: Counter[str] = Counter()
    for run in runs:
        lf2.update(run["lf2"])
    return {
        "runs": len(runs), "minutes": round(sum(run["minutes"] for run in runs), 2),
        "reads": n, "fresh_share": round(fresh / n, 4) if n else None,
        "base_share": round(out_c.get("base", 0) / n, 4) if n else None,
        "light_share": round(out_c.get("light", 0) / n, 4) if n else None,
        "failures": {k: v for k, v in out_c.most_common() if status(k) == "failed"},
        "spans": spans_of(spans),
        "persistent": {**spans_of([s for s in spans if s["persistent"]]),
                       "fight_s": round(sum(s["fight_s"] for s in spans if s["persistent"]), 1),
                       "with_fight": sum(1 for s in spans if s["persistent"] and s["fight_s"] > 0)},
        "unconfirmed_only": spans_of([s for s in spans if s["unconfirmed_only"]]),
        "late": spans_of([s for s in spans if s["late"]]),
        "late_unconfirmed_only": spans_of([s for s in spans
                                           if s["late"] and s["unconfirmed_only"]]),
        "gap_max_s": max((s["gap_s"] for s in spans), default=None),
        "gaps_ge_20s": sum(1 for s in spans if s["gap_s"] >= GAP_LONG_S),
        "walks": {k: walks_of([w for w in walks if w["class"] == k])
                  for k in ("fresh", "reader", "blocked", "none")},
        "stale_walks": walks_of(stale),
        "stale_walks_in_unconfirmed_only": walks_of([w for w in stale
                                                     if w["in_unconfirmed_only"]]),
        "stale_walks_in_late": walks_of([w for w in stale if w["in_late"]]),
        "other_walks": walks_of([w for w in walks if w["class"] != "reader"]),
        "reach_skips": {k: {"n": len(xs), "here_err_p50": q([x["here_err"] for x in xs
                                                            if x["here_err"] is not None], 0.5),
                            "here_err_ge5": sum(1 for x in xs if (x["here_err"] or 0) >= 5)}
                        for k in ("fresh", "reader", "blocked")
                        for xs in [[x for x in reach if x["class"] == k]]},
        "pos_unread_escapes": sum(len(run["escapes"]) for run in runs),
        "wrong_standing": sum(len(run["wrong"]) for run in runs),
        "standing_fresh_reads": sum(run["standing_fresh"] for run in runs),
        "jumps": sum(run["jumps"] for run in runs),
        "held": {"n": len(held), "late": sum(1 for h in held if h["held_dt"] is None
                                             or h["held_dt"] > LATE_S),
                 "within1": sum(1 for h in held if h["err"] is not None and h["err"] <= 1),
                 "err_p50": q([h["err"] for h in held if h["err"] is not None], 0.5)},
        "lf2": dict(lf2),
        "lf4": {"events": dict(Counter(str(x["event"]) for x in lf4)),
                "steps": len(lf4_steps), "steps_sent": sum(1 for x in lf4_steps if x["sent"]),
                "step_err_p50": q([x["err"] for x in lf4_steps if x["err"] is not None], 0.5),
                "fresh_after_step": sum(1 for x in lf4_fresh if (x["steps"] or 0) > 0),
                "fresh_in_wait": sum(1 for x in lf4_fresh if not x["steps"]),
                "fresh_err_gt2": sum(1 for x in lf4_fresh if (x["err"] or 0) > WRONG_CELLS),
                "wings": sum(1 for x in lf4 if x["event"] == "wing"),
                "refused": dict(Counter(str(x["why"]) for x in lf4 if x["event"] == "refused"))},
    }  # fmt: skip


def load(session: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    ev = [json.loads(x) for x in (session / "events.jsonl").read_text().splitlines() if x.strip()]
    ev.sort(key=lambda e: e["t_ns"])
    with gzip.open(session / "packets.jsonl.gz", "rt") as fh:
        pk = sorted((json.loads(x) for x in fh if x.strip()), key=lambda p: p["t_mono_ns"])
    return ev, pk


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)  # fmt: skip
    ap.add_argument("sessions", type=Path, nargs="+")
    ap.add_argument("--out", type=Path, default=None)
    a = ap.parse_args(argv)
    res = []
    for s in a.sessions:
        ev, pk = load(s)
        res.append({"session": s.name, **analyse(ev, pk, s.name.rsplit("-", 1)[-1])})
    pooled = summary(res)
    if a.out:
        a.out.write_text(json.dumps({"runs": res, "pooled": pooled}))
    for r in res:
        print(json.dumps({"label": r["label"], **r["summary"]}))
    print(json.dumps({"label": "pooled", **pooled}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
