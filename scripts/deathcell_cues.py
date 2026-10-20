#!/usr/bin/env python3
"""THE DEATH-CELL CUES (Batt 2026-10-20, the loot block's step 2: "offline study first: target box
at the last hit, death animation, last box at the EXP-line moment, HP-bar position vs the server
death cell"). OFFLINE, packets as ground truth (ADR-0007); nothing here runs during play.

For every kill of ours that a loot step followed (loot_complete.py's owner rule), the target is
followed through the detector's per-frame boxes (``boxes.jsonl``) WITHOUT packets: from the box
nearest the engagement's last strike click (<= 70 px, its frame), then frame to frame the box
nearest the last one (<= 50 px), until the engagement's end. Each cue is that box's foot pixel
(centre x, bottom - loot1.FOOT_LIFT) turned into a cell with the camera on our GM's cell AT THAT
FRAME (packets: flow_judge.gm_track, interpolated, ``--lag`` s earlier: the client draws the
world behind the server; 0.65 s reproduces the runner's own death cell best, 2026-10-20 ~10:1x),
so the cue's own error, not the bot's position error:
- ``last_hit``  the box at the frame nearest before our last damaging act on the target;
- ``at_kill``   ... before the kill (the death vanish);
- ``med_pre_kill`` the median cell of the followed boxes in the 0.6 s before the kill;
- ``at_line``   ... before the kill's base EXP line (battle_log_live.jsonl: the first base EXP
                record 0..3 s after the kill);
- ``line_05``   ... before the line + 0.5 s (v48's loot start);
- ``last_box``  the followed box's last frame (the dying sprite; the runner's "anim" rule today);
- ``bot``       the loot step's own cell (what the runner used, with its own position).
Against the server's death cell (flow_judge.mob_at at the kill): exact, <= 1 cell (Chebyshev), and
the share of the kill's drops inside the 3 x 3 around the cue's cell (the loot step's plan).
The HP bar needs the recorded frames (the NAS): not in this version.

    deathcell_cues.py SID [SID ...]       per run + pooled (JSON)
"""

from __future__ import annotations

import argparse
import bisect
import json
import math
import sys
from collections import defaultdict
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

NS = 1_000_000_000
CUES = ("last_hit", "at_kill", "med_pre_kill", "at_line", "line_05", "last_box", "bot")
START_PX = 70.0
FOLLOW_PX = 50.0
FOOT_LIFT = 4.0  # loot1.FOOT_LIFT


def cheb(a: Sequence[int], b: Sequence[int]) -> int:
    return max(abs(int(a[0]) - int(b[0])), abs(int(a[1]) - int(b[1])))


def foot(b: Sequence[float]) -> tuple[float, float]:
    return ((float(b[0]) + float(b[2])) / 2, float(b[3]) - FOOT_LIFT)


def follow(frames: Sequence[tuple[int, list[Any]]], t0: int, u0: float, v0: float, t_end: int
           ) -> list[tuple[int, tuple[float, float]]]:  # fmt: skip
    """PURE: the target's foot pixels frame by frame -- from the box nearest (u0, v0) within
    START_PX in the first frame at or after t0 that has one, then the box nearest the last foot
    within FOLLOW_PX, until t_end; a frame with no such box is skipped (the track may come back)."""
    out: list[tuple[int, tuple[float, float]]] = []
    last: tuple[float, float] | None = None
    for t, boxes in frames:
        if t < t0:
            continue
        if t > t_end:
            break
        ref, lim = ((u0, v0), START_PX) if last is None else (last, FOLLOW_PX)
        best = min((foot(b) for b in boxes), default=None,
                   key=lambda f: math.hypot(f[0] - ref[0], f[1] - ref[1]))  # fmt: skip
        if best is not None and math.hypot(best[0] - ref[0], best[1] - ref[1]) <= lim:
            out.append((t, best))
            last = best
    return out


def at_or_before(track: Sequence[tuple[int, Any]], t: int) -> Any:
    """PURE: the value of the last point at or before ``t`` (None if none)."""
    ts = [p[0] for p in track]
    i = bisect.bisect_right(ts, t) - 1
    return track[i][1] if i >= 0 else None


def in3x3(items: Sequence[Sequence[int]], c: Sequence[int] | None) -> int:
    return 0 if c is None else sum(cheb(i, c) <= 1 for i in items)


def session(sid: str, lag_s: float = 0.0) -> dict[str, Any]:
    import arm_judge as aj
    import flow_judge as fj
    import hunt_core as hc
    import loot_complete as lc
    import search_study as ss
    import walk5 as w5
    from hunt_flow import nearest_cell_frac

    from poring_dataset import camera as cam
    from poring_dataset import gat as gatmod

    d = aj.DEMO / sid
    sess = ss.load_session(sid)
    man = json.loads((d / "manifest.json").read_text())
    gat = gatmod.parse((cam.GAT_DIR / f"{man.get('map', 'prt_fild08')}.gat").read_bytes())
    cj = json.loads((Path(__file__).resolve().parents[1] / "packages/poring_dataset/src/"
                     "poring_dataset/camera_rdp.json").read_text())  # fmt: skip
    camera = cam.camera_from_json(cj["camera"])
    world = w5.World(camera, gat, (0, 0))
    frames = [
        (int(x["t"]), x["boxes"])
        for x in (json.loads(y) for y in (d / "boxes.jsonl").read_text().splitlines() if y)
    ]
    frames.sort(key=lambda f: f[0])
    clicks = sorted((json.loads(x) for x in (d / "clicks.jsonl").read_text().splitlines() if x),
                    key=lambda c: int(c["t"]))  # fmt: skip
    strikes = [c for c in clicks if str(c.get("kind") or c.get("why") or "").startswith("strike")]
    st_ts = [int(c["t"]) for c in strikes]
    bl = d / "battle_log_live.jsonl"
    lines = sorted(int(x["t_ns"]) for x in (json.loads(y) for y in bl.read_text().splitlines()
                                            if y.strip()) if x.get("type") == "base_exp") if (
        bl.exists()) else []  # fmt: skip
    engs = json.loads((d / "engagements.json").read_text())
    rows = json.loads((d / "flow_judge.json").read_text())["engagements_w"]["rows"]
    gid_by_k = {int(r["k"]): r.get("gid") for r in rows}
    pk = sess.events
    pos = hc.walk_positions(pk)
    items = aj.item_fates(pk, pos, fj.mob_at)
    gm = fj.gm_track(pk)[0]
    hits: dict[int, list[int]] = defaultdict(list)
    for e in pk:
        if e.get("type") == "act" and e.get("src_gid") == 2000002 and int(e.get("damage") or 0):
            hits[int(e.get("target_gid") or -1)].append(int(e["t_mono_ns"]))

    gts = [p_[0] for p_ in gm]

    def gm_at(t: int) -> tuple[float, float] | None:
        """Our GM's server cell at ``t``, linear between the track's per-cell points."""
        i_ = bisect.bisect_right(gts, t) - 1
        if i_ < 0:
            return None
        (ta, ca) = gm[i_]
        if i_ + 1 >= len(gm):
            return (float(ca[0]), float(ca[1]))
        (tb, cb) = gm[i_ + 1]
        if tb <= ta or cheb(ca, cb) > 1:
            return (float(ca[0]), float(ca[1]))
        w_ = min(1.0, (t - ta) / (tb - ta))
        return (ca[0] + w_ * (cb[0] - ca[0]), ca[1] + w_ * (cb[1] - ca[1]))

    def cell_of(t: int, f: tuple[float, float] | None) -> tuple[int, int] | None:
        if f is None:
            return None
        g_ = gm_at(t - int(lag_s * NS))
        if g_ is None:
            return None
        o = (int(round(g_[0])), int(round(g_[1])))
        return nearest_cell_frac(world, g_, o, f[0], f[1], radius=14)

    out: dict[str, dict[str, list[Any]]] = {c: {"err": [], "in3": [], "n_items": []} for c in CUES}
    n = 0
    agree: list[int] = []
    kills_rows: list[dict[str, Any]] = []
    for t_k, g in aj.kills_of(pk):
        if not sess.t0 <= t_k <= sess.w1:
            continue
        e = lc.owner_of(g, t_k, engs, gid_by_k)
        if not lc.looted(e) or e is None:
            continue
        dc = fj.mob_at(pos, g, t_k - 1)
        if dc is None:
            continue
        drops = [items[f]["cell"] for f in aj.drops_of_kill(items, t_k, dc)]
        i = bisect.bisect_right(st_ts, t_k) - 1
        if i < 0 or int(strikes[i]["t"]) < int(e["t_first_click"]) - NS:
            continue
        sc = strikes[i]
        lo = e.get("loot") or {}
        t_step = int(e["t_end"]) - int(float(lo.get("s") or 0.0) * NS)  # the loot step's start
        trk = follow(frames, int(sc["t"]), float(sc["u"]), float(sc["v"]), t_step)
        if not trk:
            continue
        n += 1
        t_hit = max((t for t in hits.get(g, []) if t <= t_k), default=t_k)
        t_line = next((t for t in lines if t_k <= t <= t_k + 3 * NS), None)
        cue_t = {"last_hit": t_hit, "at_kill": t_k, "at_line": t_line,
                 "line_05": None if t_line is None else t_line + NS // 2}  # fmt: skip
        cells: dict[str, Any] = {}
        for c, t_ in cue_t.items():
            if t_ is None:
                continue
            ts_ = [p[0] for p in trk]
            j = bisect.bisect_right(ts_, t_) - 1
            cells[c] = cell_of(trk[j][0], trk[j][1]) if j >= 0 else None
        cells["last_box"] = cell_of(trk[-1][0], trk[-1][1])
        pre = [cell_of(t_, f_) for t_, f_ in trk if t_k - int(0.6 * NS) <= t_ <= t_k]
        pre = [c_ for c_ in pre if c_ is not None]
        if pre:  # the median cell of the 0.6 s before the kill (a denoised box cue)
            xs, ys = sorted(c_[0] for c_ in pre), sorted(c_[1] for c_ in pre)
            cells["med_pre_kill"] = (xs[len(xs) // 2], ys[len(ys) // 2])
        cells["bot"] = tuple(lo["cell"]) if lo.get("cell") else None
        if cells.get("last_box") is not None and cells["bot"] is not None:
            agree.append(cheb(cells["last_box"], cells["bot"]))
        kr: dict[str, Any] = {}
        for c in CUES:
            if c not in cells or cells[c] is None:
                continue
            out[c]["err"].append(cheb(cells[c], dc))
            out[c]["in3"].append(in3x3(drops, cells[c]))
            out[c]["n_items"].append(len(drops))
            kr[c] = (cheb(cells[c], dc), in3x3(drops, cells[c]), len(drops))
        kills_rows.append(kr)
    return {"kills": n, "cues": out, "last_box_vs_bot": agree, "rows": kills_rows}


def table(per: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """PURE: per cue -- n, exact, <= 1 cell, <= 2, and the drops in its 3 x 3."""
    res = {}
    for c in CUES:
        err = [x for p in per for x in p["cues"][c]["err"]]
        i3 = sum(x for p in per for x in p["cues"][c]["in3"])
        ni = sum(x for p in per for x in p["cues"][c]["n_items"])
        if not err:
            continue
        res[c] = {"n": len(err), "exact": round(sum(e == 0 for e in err) / len(err), 3),
                  "within1": round(sum(e <= 1 for e in err) / len(err), 3),
                  "within2": round(sum(e <= 2 for e in err) / len(err), 3),
                  "drops_in_3x3": round(i3 / ni, 3) if ni else None, "items": ni}  # fmt: skip
    return res


def paired(rows: Sequence[Mapping[str, Any]], a: str, b: str) -> dict[str, Any]:
    """PURE: cue ``a`` against cue ``b`` on the SAME kills (both present)."""
    both = [r for r in rows if a in r and b in r]
    ni = sum(r[a][2] for r in both)

    def m(c: str) -> dict[str, Any]:
        return {"exact": round(sum(r[c][0] == 0 for r in both) / max(1, len(both)), 3),
                "within1": round(sum(r[c][0] <= 1 for r in both) / max(1, len(both)), 3),
                "drops_in_3x3": round(sum(r[c][1] for r in both) / max(1, ni), 3)}  # fmt: skip

    return {"kills": len(both), "items": ni, a: m(a), b: m(b)}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--lag", type=float, default=0.0, help="the display lag behind the server, s")
    ap.add_argument("sids", nargs="+")
    a = ap.parse_args()
    per = {s: session(s, a.lag) for s in a.sids}
    ag = [x for v in per.values() for x in v["last_box_vs_bot"]]
    print(json.dumps({"per_run": {s: {"kills": v["kills"], **table([v])} for s, v in per.items()},
                      "pooled": table(list(per.values())),
                      "paired": {f"{a_} vs {b_}": paired(
                          [r for v in per.values() for r in v["rows"]], a_, b_)
                          for a_, b_ in (("med_pre_kill", "bot"), ("med_pre_kill", "last_box"),
                                         ("last_box", "bot"), ("line_05", "bot"))},
                      "calibration_last_box_vs_bot": {
                          "n": len(ag), "same": round(sum(x == 0 for x in ag) / max(1, len(ag)), 3),
                          "within1": round(sum(x <= 1 for x in ag) / max(1, len(ag)), 3)}},
                     indent=1))  # fmt: skip
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
