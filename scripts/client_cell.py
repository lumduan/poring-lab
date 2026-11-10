#!/usr/bin/env python3
"""Study S-LF5 (rogue-xmas02.md; Batt 2026-11-11 "study and fix" the (104,192) misread): WHERE THE
CLIENT DREW the Rogue, measured from the runner's own monster boxes and the packets' monster cells.
A scorer helper. ANALYSIS ONLY.

    client_cell.py score SESSION_DIR [SESSION_DIR ...] [--gat GAT] [--out OUT.json]

OFFLINE ground truth only (packets, ADR-0007): nothing here reaches a runner. One clock: the
runner's ``t_ns`` and the sniffer's ``t_mono_ns`` are both bot-server's CLOCK_MONOTONIC.

WHY. The client's camera follows the client's OWN position of her, the same position its minimap
readout prints. A monster is drawn at its server cell (shown ~late_strike.FRAME_LAG_S late)
relative to that camera centre. So the centre that projects the server's monsters onto the
detected monster boxes best is the client's cell of her, measured without the readout. When it
differs from the server's cell, the client and the server disagree (a DESYNC); a position read
that equals it read the screen correctly.

- ``fit_centre``: PURE. Every candidate centre within RADIUS of a guess: each box's foot (the box's
  bottom centre) to the nearest projected monster, capped at CAP_PX; the cost is the sum over the
  boxes. ``matched`` = boxes within MATCH_PX under the best centre. The projector is the runner's
  own camera (camera_rdp.json) with the map's GAT altitudes, the same as ``late_strike fit-lag``.
- ``detection_fits``: one fit per detection with monster boxes and server monsters in view
  (VIEW_DX x VIEW_DY cells of our server cell), and whether we stood (server) for STAND_S before.
- ``votes`` / ``verdict``: fits within FIT_WIN_S of an instant on the same server cell. A fit votes
  only when its best centre beats the server cell by MARGIN px (or IS the server cell). A cell is
  ESTABLISHED by >= MIN_EVIDENCE matched boxes over its votes, and more than the other side's.
- ``read_verdicts``: slf_score's WRONG standing reads re-judged: ``desync`` (the client cell is
  established within 1 cell of the read: the reader read what the client drew), ``misread`` (the
  server cell is established: the reader was wrong), else ``unjudged``.
- ``walk_rows``: per server walk (``self_move``), the server's CONFIRMED end (the next walk's
  origin, or our next stop / map change), the client's end (fits from the walk's end + SETTLE_S to
  the next record), ``short`` when the client's end is established >= SHORT_CELLS off the confirmed
  end, ``followed`` when established within 1 of it. Its context: the ack came inside her OWN
  attack motion (an act of hers within its ``src_speed`` ms before), inside a FLINCH (a hit on her
  within its ``dmotion`` ms before), or with a MISS on her within MISS_MS after.
- ``floor_walkoffs``: RE-CLICKED strikes (``clicks`` >= 2) whose request sequence (first click ..
  the strike's end) has an attack request and, after it, a walk request >= 2 cells from that
  target's server cell while the target lived on (no vanish within ALIVE_S): the burst's re-click
  hit the floor after the camera had scrolled with the walk-up, cancelled the attack and walked
  her off (p53 891.0 s). ``next_hit_s``: to her next hit on the same target. One-click strikes are
  left out (a later walk is the client chasing a walker: p40-p53, 9 such, next hit 0.4-2.6 s). The
  measure for S-LF5's proposal R2.
- ``strike_firsts``: per strike, its band (0-1 / 2-3 / 4+ cells), re-clicked or not, and the
  client's first request after its stamp (``first_s``; None = the first click sent nothing). R2's
  no-harm count: in p40-p53 every 2-3-cell first click but one (one-click) sent a request within
  0.38 s, so no strike there needed its re-click.
"""

from __future__ import annotations

import argparse
import bisect
import json
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import numpy.typing as npt

NS = 1_000_000_000
OUR_GID = 2000002  # the lab account's Rogue (late_strike.OUR_GID)
RADIUS = 5  # candidate centres: within this many cells of the guess (Chebyshev)
CAP_PX = 60.0  # a box farther than this from every projected monster costs this much
MATCH_PX = 25.0  # a box this close to a projected monster is matched
MARGIN = 30.0  # px: an off-server centre votes only when it beats the server cell by this much
MIN_EVIDENCE = 2  # matched boxes over a cell's votes that establish it
FIT_WIN_S = 1.5  # votes around an instant: fits this close (s)
SETTLE_S = 0.6  # a walk's client end: fits from the walk's end + this (the camera glides ~0.5 s)
STAND_S = 1.0  # standing: our server cell unchanged this long (slf_score.STAND_GUARD_S)
SHORT_CELLS = 2  # the client's end this far off the server's confirmed end: SHORT
VIEW_DX, VIEW_DY = 16, 14  # server monsters within this of our server cell are in view
MISS_MS = 250  # a miss on her this soon after a walk ack is noted
ALIVE_S = 0.5  # a floor walk-off's target lived at least this long after it
LAG_S = 0.16  # late_strike.FRAME_LAG_S: the picture shows the server this long before its grab

Cell = tuple[int, int]
Project = Callable[[npt.NDArray[np.float64], npt.NDArray[np.float64]], npt.NDArray[np.float64]]
Altitude = Callable[[npt.NDArray[np.float64]], npt.NDArray[np.float64]]


def cheb(a: Sequence[float], b: Sequence[float]) -> float:
    """PURE: the Chebyshev distance (cells)."""
    return max(abs(a[0] - b[0]), abs(a[1] - b[1]))


@dataclass(frozen=True)
class Fit:
    best: Cell
    cost: float  # the best centre's cost (px)
    cost_guess: float  # the guess's cost (px)
    matched: int  # boxes within MATCH_PX under the best centre
    n_boxes: int


def fit_centre(feet: Sequence[Sequence[float]], mobs: Sequence[Sequence[float]], guess: Cell,
               project: Project, alt: Altitude, radius: int = RADIUS, cap_px: float = CAP_PX,
               match_px: float = MATCH_PX) -> Fit:  # fmt: skip
    """PURE (given ``project`` and ``alt``): the camera centre among ``guess`` +- ``radius`` cells
    that projects the monsters' cells ``mobs`` (absolute, fractional for walkers) best onto the
    boxes' ``feet`` (pixels). ``project(offsets, altitude)`` maps cell offsets from the centre
    (N, 2) and altitudes relative to the centre's cell (N,) to pixels (N, 2); ``alt(cells)`` gives
    the absolute altitude of absolute cells (N, 2). Ties go to the lower (x, y)."""
    m = np.asarray(mobs, dtype=float).reshape(-1, 2)
    f = np.asarray(feet, dtype=float).reshape(-1, 2)
    offs = np.asarray([(dx, dy) for dx in range(-radius, radius + 1)
                       for dy in range(-radius, radius + 1)], dtype=float)  # fmt: skip
    cs = offs + np.asarray(guess, dtype=float)
    am, ac = alt(m), alt(cs)
    rel = (m[None, :, :] - cs[:, None, :]).reshape(-1, 2)
    uv = project(rel, (am[None, :] - ac[:, None]).reshape(-1)).reshape(len(cs), len(m), 2)
    d = np.hypot(f[None, :, None, 0] - uv[:, None, :, 0], f[None, :, None, 1] - uv[:, None, :, 1])
    dm = d.min(axis=2)  # candidates x boxes
    cost = np.minimum(dm, cap_px).sum(axis=1)
    b = int(np.lexsort((cs[:, 1], cs[:, 0], cost))[0])
    g = int(np.flatnonzero((offs[:, 0] == 0) & (offs[:, 1] == 0))[0])
    return Fit((int(cs[b, 0]), int(cs[b, 1])), round(float(cost[b]), 1),
               round(float(cost[g]), 1), int((dm[b] <= match_px).sum()), len(f))  # fmt: skip


class _Tracks:
    """late_strike's tracks with their arrival times indexed once (pos_at rebuilds them a call)."""

    def __init__(self, packets: Sequence[Mapping[str, Any]], our_gid: int = OUR_GID) -> None:
        import late_strike as ls

        self.ls = ls
        mobs, ours = ls.tracks(packets, our_gid)
        self.mobs = {g: ([s.t_rx for s in tr], tr) for g, tr in mobs.items()}
        self.ours = ([s.t_rx for s in ours], ours)

    @staticmethod
    def at(ft: tuple[list[int], Any], t: int) -> tuple[float, float, bool] | None:
        i = bisect.bisect_right(ft[0], t) - 1
        if i < 0 or ft[1][i].kind == "gone":
            return None
        p: tuple[float, float, bool] = ft[1][i].at(t)
        return p

    def us(self, t: int) -> tuple[float, float, bool] | None:
        return self.at(self.ours, t)

    def standing(self, t: int, still_s: float = STAND_S) -> bool:
        a, b = self.us(t - int(still_s * NS)), self.us(t)
        if a is None or b is None or a[2] or b[2] or cheb(a, b) > 0:
            return False
        return not self.ls.moves_between(self.ours[1], t - int(still_s * NS), t)

    def mobs_near(self, t: int, me: Sequence[float]) -> list[tuple[float, float]]:
        out = []
        for ft in self.mobs.values():
            p = self.at(ft, t)
            if p is not None and abs(p[0] - me[0]) <= VIEW_DX and abs(p[1] - me[1]) <= VIEW_DY:
                out.append((p[0], p[1]))
        return out


def monster_feet(det: Mapping[str, Any]) -> list[tuple[float, float]]:
    """PURE: the feet (bottom centre) of a detection's monster boxes."""
    return [((b[0] + b[2]) / 2, b[3]) for b in det.get("boxes") or []
            if len(b) <= 5 or b[5] == "monster"]  # fmt: skip


def detection_fits(dets: Sequence[Mapping[str, Any]], packets: Sequence[Mapping[str, Any]],
                   project: Project, alt: Altitude, lag_s: float = LAG_S,
                   tracks: _Tracks | None = None) -> list[dict[str, Any]]:  # fmt: skip
    """One record per detection with monster boxes and server monsters in view: its grab
    (``t_ns``), our server cell (``srv``), ``walking`` / ``standing``, and the fit around
    ``srv``."""
    tr = tracks or _Tracks(packets)
    out = []
    for d in dets:
        tg = int(d["t_ns"] - float(d.get("ms") or 0) * 1e6)
        me = tr.us(tg)
        feet = monster_feet(d)
        if me is None or not feet:
            continue
        mobs = tr.mobs_near(tg - int(lag_s * NS), me)
        if not mobs:
            continue
        srv = (int(round(me[0])), int(round(me[1])))
        f = fit_centre(feet, mobs, srv, project, alt)
        out.append({"t_ns": tg, "srv": srv, "walking": bool(me[2]), "standing": tr.standing(tg),
                    "fit": f})  # fmt: skip
    return out


def votes(fits: Sequence[Mapping[str, Any]], t: int, srv: Cell,
          win_s: float = FIT_WIN_S, margin: float = MARGIN) -> dict[Cell, int]:  # fmt: skip
    """PURE: matched boxes per voted centre, over the fits within ``win_s`` of ``t`` taken on the
    same server cell ``srv``. A fit votes for the server cell when its best IS it, for an off cell
    when it beats the server cell by ``margin`` px; a fit with no matched box does not vote."""
    out: Counter[Cell] = Counter()
    for r in fits:
        f: Fit = r["fit"]
        if abs(int(r["t_ns"]) - t) > win_s * NS or tuple(r["srv"]) != tuple(srv) or not f.matched:
            continue
        if f.best == tuple(srv) or f.cost_guess - f.cost >= margin:
            out[f.best] += f.matched
    return dict(out)


def verdict(v: Mapping[Cell, int], srv: Cell, read: Cell | None = None,
            min_evidence: int = MIN_EVIDENCE) -> tuple[str, Cell | None]:  # fmt: skip
    """PURE: from ``votes``: (``client``, the established client cell) when the most-voted cell >= 2
    off the server (with ``read``: within 1 of it) and its neighbours within 1 gather >=
    ``min_evidence`` matched boxes and more than the cells within 1 of the server; (``server``,
    srv) the other way round; else (``unjudged``, None). Off votes that scatter do not add up."""
    near = sum(n for c, n in v.items() if cheb(c, srv) <= 1)
    off = {c: n for c, n in v.items() if cheb(c, srv) >= 2 and (read is None or cheb(c, read) <= 1)}
    top = max(off, key=lambda c: (off[c], c)) if off else None
    n_off = 0 if top is None else sum(n for c, n in off.items() if cheb(c, top) <= 1)
    if top is not None and n_off >= min_evidence and n_off > near:
        return "client", top
    if near >= min_evidence and near > n_off:
        return "server", srv
    return "unjudged", None


def read_verdicts(wrong: Sequence[Mapping[str, Any]], fits: Sequence[Mapping[str, Any]],
                  t0: int) -> list[dict[str, Any]]:  # fmt: skip
    """PURE: slf_score's ``wrong`` rows (``t`` s from the run start, ``pos``, ``true``) re-judged:
    ``desync`` / ``misread`` / ``unjudged`` (the module's docstring), with the votes."""
    out = []
    for w in wrong:
        t = t0 + int(round(float(w["t"]) * NS))
        srv, pos = tuple(w["true"]), tuple(w["pos"])
        v = votes(fits, t, srv)
        how, cell = verdict(v, srv, read=pos)
        out.append({**w, "verdict": {"client": "desync", "server": "misread"}.get(how, how),
                    "client_cell": None if cell is None else list(cell),
                    "votes": {f"{c[0]},{c[1]}": n for c, n in sorted(v.items())}})  # fmt: skip
    return out


def walk_rows(packets: Sequence[Mapping[str, Any]], fits: Sequence[Mapping[str, Any]], t0: int,
              t1: int, our_gid: int = OUR_GID) -> list[dict[str, Any]]:  # fmt: skip
    """PURE (given the fits): one row per server walk of ours inside [t0, t1] (the docstring)."""
    import late_strike as ls

    ours = sorted((p for p in packets if p.get("type") in ("self_move", "map_change")
                   or (p.get("type") == "entity_stop" and p.get("gid") == our_gid)),
                  key=lambda p: int(p["t_mono_ns"]))  # fmt: skip
    acts = [p for p in packets if p.get("type") == "act"]
    own = [p for p in acts if p.get("src_gid") == our_gid]
    on = [p for p in acts if p.get("target_gid") == our_gid and p.get("src_gid") != our_gid]
    rows = []
    for i, w in enumerate(ours):
        ts = int(w["t_mono_ns"])
        if w["type"] != "self_move" or not t0 <= ts <= t1:
            continue
        nxt = ours[i + 1] if i + 1 < len(ours) else None
        conf: Cell | None = None
        t_next = t1
        if nxt is not None and nxt["type"] != "map_change":
            conf = ((nxt["x0"], nxt["y0"]) if nxt["type"] == "self_move"
                    else (nxt["x"], nxt["y"]))  # fmt: skip
            t_next = int(nxt["t_mono_ns"])
        seg = ls.Seg(ts, "move", w["x0"], w["y0"], w["x1"], w["y1"],
                     ls._start_ns(w, "server_tick"), float(ls.OUR_SPEED_MS))  # fmt: skip
        t_end = seg.t_start + seg.duration_ns()
        dest = (int(w["x1"]), int(w["y1"]))
        mine = [r for r in fits if t_end + SETTLE_S * NS <= r["t_ns"] < t_next
                and tuple(r["srv"]) == dest]  # fmt: skip
        v: Counter[Cell] = Counter()
        for r in mine:
            v.update(votes([r], int(r["t_ns"]), dest, win_s=0.0))
        outcome = "unknown"
        client: Cell | None = None
        if conf is not None and conf == dest:
            how, client = verdict(v, dest)
            outcome = {"client": "short", "server": "followed"}.get(how, "unknown")
            if how == "client" and client is not None and cheb(client, dest) < SHORT_CELLS:
                outcome = "followed"
        rows.append({
            "t_ns": ts, "from": [w["x0"], w["y0"]], "to": list(dest),
            "confirmed": None if conf is None else list(conf),
            "next_s": round((t_next - ts) / NS, 2), "outcome": outcome,
            "client": None if client is None else list(client),
            "votes": {f"{c[0]},{c[1]}": n for c, n in sorted(v.items())},
            "own_motion_ms": [round((ts - int(p["t_mono_ns"])) / 1e6) for p in own
                              if 0 <= ts - int(p["t_mono_ns"])
                              <= float(p.get("src_speed") or 0) * 1e6],
            "flinch_ms": [round((ts - int(p["t_mono_ns"])) / 1e6) for p in on if p.get("damage")
                          and 0 <= ts - int(p["t_mono_ns"]) <= float(p.get("dmotion") or 0) * 1e6],
            "miss_ms": [round((int(p["t_mono_ns"]) - ts) / 1e6) for p in on if not p.get("damage")
                        and -50e6 <= int(p["t_mono_ns"]) - ts <= MISS_MS * 1e6],
        })  # fmt: skip
    return rows


def floor_walkoffs(events: Sequence[Mapping[str, Any]], packets: Sequence[Mapping[str, Any]],
                   our_gid: int = OUR_GID) -> list[dict[str, Any]]:  # fmt: skip
    """PURE: the strikes whose re-click walked her off a live target (the module's docstring)."""
    import late_strike as ls

    mobs, _ = ls.tracks(packets, our_gid)
    reqs = sorted((p for p in packets if p.get("type") in ("self_move_request", "attack_request")),
                  key=lambda p: int(p["t_mono_ns"]))  # fmt: skip
    rt = [int(p["t_mono_ns"]) for p in reqs]
    hits = [p for p in packets if p.get("type") == "act" and p.get("src_gid") == our_gid]
    gone: dict[int, list[int]] = {}
    for p in packets:
        if p.get("type") == "entity_vanish" and p.get("gid") is not None:
            gone.setdefault(int(p["gid"]), []).append(int(p["t_mono_ns"]))
    out = []
    for e in events:
        if e.get("kind") != "strike" or int(e.get("clicks") or 1) < 2:
            continue  # one click: a later walk is the client chasing, not a re-click
        tc, te = int(e["t_ns"]), int(e.get("t_end_ns") or e["t_ns"])
        i = bisect.bisect_left(rt, tc)
        seq = []
        while i < len(reqs) and rt[i] <= te:
            seq.append(reqs[i])
            i += 1
        ia = next((k for k, p in enumerate(seq) if p["type"] == "attack_request"), None)
        if ia is None:
            continue
        tgt = seq[ia].get("target_gid")
        for p in seq[ia + 1 :]:
            if p["type"] != "self_move_request":
                continue
            ta = int(p["t_mono_ns"])
            mp = ls.pos_at(mobs[tgt], ta) if tgt in mobs else None
            if mp is None or cheb(mp, (p["x"], p["y"])) < 2:
                continue  # unknown target, or the client chasing it (a walk beside it)
            van = next((t for t in sorted(gone.get(int(tgt), [])) if t > ta - int(0.3 * NS)), None)
            if van is not None and van <= ta + ALIVE_S * NS:
                continue
            nh = next((int(h["t_mono_ns"]) for h in hits
                       if h.get("target_gid") == tgt and int(h["t_mono_ns"]) > ta),
                      None)  # fmt: skip
            rel = [int(v) for v in e.get("rel") or (0, 0)]
            to = (p["x"], p["y"])
            out.append({"t_ns": tc, "rel": rel, "dist": int(max(abs(rel[0]), abs(rel[1]))),
                        "clicks": e.get("clicks"), "by": e.get("by"), "target": tgt,
                        "walk_to": list(to), "off_cells": round(cheb(mp, to), 1),
                        "next_hit_s": None if nh is None else round((nh - ta) / NS, 2),
                        "vanish_s": None if van is None else round((van - ta) / NS, 2),
                        })  # fmt: skip
            break
    return out


def band(dist: int) -> str:
    """PURE: a strike's distance band for S-LF5 (cells): 0-1, 2-3, 4+ (``--far-single``'s)."""
    return "0-1" if dist <= 1 else "2-3" if dist <= 3 else "4+"


def strike_firsts(events: Sequence[Mapping[str, Any]],
                  packets: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:  # fmt: skip
    """PURE: per strike, its band, whether it was re-clicked (``clicks`` >= 2), and the client's
    first request (a walk or an attack request) after its stamp, until its end (``first_s``, s;
    None = the first click sent nothing). R2's no-harm count: one-click strikes 2-3 cells away
    with ``first_s`` None."""
    reqs = sorted(int(p["t_mono_ns"]) for p in packets
                  if p.get("type") in ("self_move_request", "attack_request"))  # fmt: skip
    out = []
    for e in events:
        if e.get("kind") != "strike":
            continue
        tc, te = int(e["t_ns"]), int(e.get("t_end_ns") or e["t_ns"])
        i = bisect.bisect_left(reqs, tc)
        first = reqs[i] if i < len(reqs) and reqs[i] <= te + int(0.3 * NS) else None
        rel = [int(v) for v in e.get("rel") or (0, 0)]
        out.append({"t_ns": tc, "band": band(max(abs(rel[0]), abs(rel[1]))),
                    "reclicked": int(e.get("clicks") or 1) >= 2,
                    "first_s": None if first is None else round((first - tc) / NS, 3)})  # fmt: skip
    return out


def summary(runs: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """PURE: the counts over one or more runs' rows."""
    walks = [w for r in runs for w in r["walks"]]
    reads = [x for r in runs for x in r["reads"]]
    floors = [x for r in runs for x in r["floor_walkoffs"]]
    strikes = [x for r in runs for x in r.get("strikes", [])]
    fits = sum(r["n_fits"] for r in runs)
    short = [w for w in walks if w["outcome"] == "short"]

    def motion(w: Mapping[str, Any]) -> bool:
        return bool(w["own_motion_ms"] or w["flinch_ms"])

    decided = [w for w in walks if w["outcome"] in ("short", "followed")]
    nh = sorted(x["next_hit_s"] for x in floors if x["next_hit_s"] is not None)
    return {
        "runs": len(runs), "standing_fits": fits,
        "standing_fits_within1": sum(r["n_within1"] for r in runs),
        "walks": len(walks), "walks_decided": len(decided), "walks_short": len(short),
        "short_in_motion": sum(1 for w in short if motion(w)),
        "decided_in_motion": sum(1 for w in decided if motion(w)),
        "wrong_reads": len(reads), "wrong_verdicts": dict(Counter(x["verdict"] for x in reads)),
        "floor_walkoffs": len(floors),
        "floor_walkoffs_by_dist": dict(sorted(Counter(band(x["dist"]) for x in floors).items())),
        "floor_next_hit_p50_s": _p50(nh),
        "floor_next_hit_sum_s": round(sum(nh), 1),
        "strikes": {b: {"n": len(xs), "reclicked": sum(1 for x in xs if x["reclicked"]),
                        "no_request": sum(1 for x in xs if x["first_s"] is None),
                        "first_p50_s": _p50([x["first_s"] for x in xs if x["first_s"] is not None]),
                        "first_max_s": max((x["first_s"] for x in xs if x["first_s"] is not None),
                                           default=None)}
                    for b in ("0-1", "2-3", "4+") for xs in [[x for x in strikes
                                                              if x["band"] == b]]},
    }  # fmt: skip


def _p50(xs: Sequence[float]) -> float | None:
    """PURE: the upper median (slf_score's quantile)."""
    s = sorted(xs)
    return s[len(s) // 2] if s else None


def score_session(session: Path, project: Project, alt: Altitude) -> dict[str, Any]:
    import late_strike as ls
    import slf_score as sl

    ev, pk, det = ls.load(session)
    ev.sort(key=lambda e: int(e["t_ns"]))
    t0 = next(int(e["t_ns"]) for e in ev if e.get("kind") == "run_start")
    t1 = next((int(e["t_ns"]) for e in ev if e.get("kind") == "run_end"), int(ev[-1]["t_ns"]))
    fits = detection_fits(det, pk, project, alt)
    stand = [r for r in fits if r["standing"] and r["fit"].matched]
    wrong = sl.analyse(ev, pk, session.name.rsplit("-", 1)[-1])["wrong"]
    walks = walk_rows(pk, fits, t0, t1)

    def rel(t: int) -> float:
        return round((t - t0) / NS, 2)

    return {
        "session": session.name, "label": session.name.rsplit("-", 1)[-1],
        "n_fits": len(stand),
        "n_within1": sum(1 for r in stand if cheb(r["fit"].best, r["srv"]) <= 1),
        "reads": read_verdicts(wrong, fits, t0),
        "walks": [{"t": rel(int(w["t_ns"])), **{k: v for k, v in w.items() if k != "t_ns"}}
                  for w in walks],
        "floor_walkoffs": [{"t": rel(int(x["t_ns"])), **{k: v for k, v in x.items() if k != "t_ns"}}
                           for x in floor_walkoffs(ev, pk)],
        "strikes": [{"t": rel(int(x["t_ns"])), **{k: v for k, v in x.items() if k != "t_ns"}}
                    for x in strike_firsts(ev, pk)],
    }  # fmt: skip


def runner_projector(gat_path: Path) -> tuple[Project, Altitude]:
    """The runner's camera (camera_rdp.json) and the map's GAT (client-derived run-time data in
    /dev/shm, never committed), as late_strike's fit-lag uses them."""
    from poring_dataset import camera as cam
    from poring_dataset import gat as gatmod

    root = Path(__file__).resolve().parents[1]
    cj = json.loads((root / "packages/poring_dataset/src/poring_dataset/camera_rdp.json")
                    .read_text())  # fmt: skip
    camera = cam.camera_from_json(cj["camera"])
    gat = gatmod.parse(gat_path.read_bytes())
    base = float(gat.altitude[0, 0])

    def alt(cells: npt.NDArray[np.float64]) -> npt.NDArray[np.float64]:
        return np.asarray(gat.relative_altitude((0, 0), np.asarray(cells, dtype=float)) + base)

    def project(off: npt.NDArray[np.float64],
                a: npt.NDArray[np.float64]) -> npt.NDArray[np.float64]:  # fmt: skip
        return camera.project(off, a)

    return project, alt


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    sc = sub.add_parser("score", help="desyncs, re-judged wrong reads, floor walk-offs")
    sc.add_argument("sessions", type=Path, nargs="+")
    sc.add_argument(
        "--gat", type=Path, default=Path("/dev/shm/poring-lab-tmp/gat/data/xmas_dun02.gat")
    )
    sc.add_argument("--out", type=Path, default=None, help="every row of every session (JSON)")
    a = ap.parse_args(argv)
    project, alt = runner_projector(a.gat)
    res = [score_session(s, project, alt) for s in a.sessions]
    for r in res:
        print(json.dumps({"label": r["label"], **summary([r])}))
    if len(res) > 1:
        print(json.dumps({"label": "pooled", **summary(res)}))
    if a.out is not None:
        a.out.write_text(json.dumps(res))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
