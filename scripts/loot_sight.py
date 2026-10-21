#!/usr/bin/env python3
"""WHAT THE IMAGE SAYS ABOUT THE CELLS AROUND THE GM AFTER A KILL (Batt 2026-10-20 ~19:5x, his
option C, "measured offline first on v50's frames"). OFFLINE: the recorded frames (NAS) against
the packets (ADR-0007 ground truth); nothing here runs during play.

Batt's rule (v50) hovers all 25 cells of the 5 x 5 around the DRAWN GM, ~177 ms each. Option C
uses the image to ORDER the hovers and to END a pass early when the hands found account for the
items seen -- but NEVER skips a cell the image is unsure about, so completeness cannot drop.

Per kill of ours with the GM standing still (its packet position the same 0.6 s before the kill
and at the stand frame), on the frame BEFORE the kill (``before_s``) and the STAND frame
(``after_s`` after the kill: the scan starts ~1 s after it), each of the 25 cells gets:
- ``seen``: the item matcher (``item_icons``, its tuned thresholds) puts an item there -- these
  cells are hovered FIRST;
- ``unsure``: the GM's own sprite covers it, or its patch CHANGED between the two frames (the
  before frame registered onto the stand frame first): something was drawn or removed -- an
  item, the dying monster, a damage number, the scan's pointer, a passer-by;
- ``empty``: nothing changed and the matcher sees nothing -- the only cells option C may leave
  unhovered. (A LOOSE matcher guard was tried and dropped: ~180 candidates a kill on grass.)
The measures:
- items (any floor item, and our kill's own) lying on ``empty`` cells: the LOSS of skipping them
  (must be ~0);
- ``empty`` cells per kill: the hovers saved (x 0.177 s);
- the matcher's per-item recall (the ORDER and the "items seen" count);
- the NO-DROP check, per kill (Batt: "nothing new drawn around the GM after the kill"): N1 = no
  matcher hit in the 5 x 5; N2 = N1 and no changed cell outside the dying monster's cell, the one
  above it on screen and the GM's sprite -- each with its skip rate on the kills that dropped
  nothing and its FALSE-SKIP rate on the kills that dropped something.

LIVE TIMING (``--from-line``): a runner knows of the kill at the EXP line's first frame (p50
0.33 s after the server's kill; p10 0.09, p90 0.44; 3.91 runs 1-2), so the frames are timed
from it: the before frame ``before_s`` earlier, the stand frame ``after_s`` later (the stand's end,
0.5 s). Before-offsets measured on 3.91 runs 1-2 (the GM still by packets / empty cells a kill /
our items on empty cells): 0.75 s 57 of 159 kills / 8.5 / 0 of 58; 0.6 s 104 / 10.4 / 0 of 97;
0.45 s 132 / 12.0 / 0 of 132; 0.3 s 139 / 13.4 / 0 of 139. The GM one-shots most monsters on
arrival, so an early before frame catches it still walking. PRE-SET for the held-out runs 3-4:
``--from-line --after 0.5 --before 0.45`` (a ~0.3 s margin before the drops are drawn).
A LIVE runner cannot see the packets' "GM still": its own scene odometry between the two frames
must gate the skipping (moved -> skip nothing). ``--all-kills`` keeps the moved kills to show
why: on them the diff alone still called ~5.5 cells a kill empty, and 1 of our items lay on one
(run 2). The registration shift is NO "moved" signal: phase correlation returns (0, 0) when the
true move exceeds its range, and a still GM's camera drifts 0-8 px.

THE CLASSIFIER IS SHARED (2026-10-21, v54 "the fast scan"): ``classify`` (the 25 verdicts from
the two frames, the projected cells and the matcher) is the ONE implementation -- this study and
hunt_flow's live scan (``loot_fast_scan``) both call it; the runner passes its BGR grabs
(``order="BGR"``), the recordings are RGB.

    loot_sight.py SID [SID ...] [--from-line] [--after 1.0] [--before 0.4] [--thr 0.04]
                  [--all-kills] [--json OUT]
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

NS = 1_000_000_000
HOVER_S = 0.177  # v50 run 1: a hover's read, p50 (3.91's run log)
BOX = (24, 22, 20)  # a cell's patch around its projected centre: half width, up, down (px)
DIFF = 40  # a pixel CHANGED when a channel moved by more than this (JPEG q80 noise is far below)
# A cell CHANGED when more than THR of its patch's pixels changed. Set on 3.91 run 1 ALONE
# (20261020T183131, 44 kills with the GM still, 1100 cells): every cell holding an item changed by
# >= 0.079 (n 39); THR = half of that. Runs 2-4 are held out.
THR = 0.04
MATCH_RADIUS = 110  # px: the matcher's square around the GM's projected cell (half side)
GM_PAD = (10.0, 0.0, 10.0, 10.0)  # px around drop_blobs.GM_BOX: the GM's sprite "covers" a cell


def patch(c_uv: Sequence[float], shape: Sequence[int]) -> tuple[int, int, int, int]:
    """PURE: the pixel box (x0, y0, x1, y1) of a cell's patch around its projected centre, clipped
    to the frame -- wide enough for its own items at any sub-cell offset (sub 12 = half a cell
    off) and their sprites."""
    u, v = float(c_uv[0]), float(c_uv[1])
    h, w = int(shape[0]), int(shape[1])
    return (max(0, int(u - BOX[0])), max(0, int(v - BOX[1])),
            min(w, int(u + BOX[0])), min(h, int(v + BOX[2])))  # fmt: skip


def diff_map(before: Any, after: Any, centre: Sequence[float], max_shift: int = 8
             ) -> tuple[Any, tuple[int, int], tuple[int, int]]:  # fmt: skip
    """PURE: the per-pixel change between the two frames over a region around the GM, the BEFORE
    frame first registered onto the AFTER one (drop_blobs.phase_shift: the camera's 1-2 px jitter
    on textured ground otherwise changes every patch), then drop_blobs._min_diff (a 1-px
    neighbourhood: JPEG ringing). Returns the map, its origin (x0, y0) in frame pixels and the
    registration shift (dy, dx)."""
    import drop_blobs as db
    import numpy as np

    h, w = after.shape[:2]
    x0, y0 = max(0, int(centre[0]) - 140), max(0, int(centre[1]) - 120)
    x1, y1 = min(w, int(centre[0]) + 140), min(h, int(centre[1]) + 100)
    a = np.asarray(after[y0:y1, x0:x1, :3])
    b = np.asarray(before[y0:y1, x0:x1, :3])
    dy, dx = db.phase_shift(a.mean(-1), b.mean(-1), max_shift)
    b_al = db._shift(b, -dy, -dx)
    return db._min_diff(a, b_al, r=1), (x0, y0), (dy, dx)


def changed_share(md: Any, origin: Sequence[int], box: Sequence[int]) -> float:
    """PURE: the share of a patch's pixels whose (registered, min-neighbourhood) change exceeds
    DIFF; a patch outside the map counts as changed (unsure)."""
    x0, y0, x1, y1 = (box[0] - origin[0], box[1] - origin[1], box[2] - origin[0],
                      box[3] - origin[1])  # fmt: skip
    h, w = md.shape[:2]
    if x0 < 0 or y0 < 0 or x1 > w or y1 > h or x1 <= x0 or y1 <= y0:
        return 1.0
    return float((md[y0:y1, x0:x1] > DIFF).mean())


def in_box(p: Sequence[float], box: Sequence[float]) -> bool:
    return box[0] <= p[0] <= box[2] and box[1] <= p[1] <= box[3]


def verdicts(cells: Sequence[tuple[int, int]], changed: Mapping[tuple[int, int], float],
             seen: Iterable[tuple[int, int]], covered: Iterable[tuple[int, int]], thr: float
             ) -> dict[tuple[int, int], str]:  # fmt: skip
    """PURE: per cell "seen" (a matcher hit), "unsure" (covered by the GM, or changed by more
    than ``thr``) or "empty" (none of these)."""
    st, cv = set(seen), set(covered)
    out = {}
    for c in cells:
        if c in st:
            out[c] = "seen"
        elif c in cv or changed.get(c, 1.0) > thr:
            out[c] = "unsure"
        else:
            out[c] = "empty"
    return out


def no_drop(v: Mapping[tuple[int, int], str], changed: Mapping[tuple[int, int], float],
            thr: float, allowed: Iterable[tuple[int, int]]) -> tuple[bool, bool]:  # fmt: skip
    """PURE: Batt's "nothing new drawn" check. N1: no matcher hit in the 5 x 5. N2: N1 and no
    changed cell outside ``allowed`` (the dying monster's cell, the one above it on screen, the
    GM's sprite)."""
    al = set(allowed)
    n1 = not any(x == "seen" for x in v.values())
    n2 = n1 and not any(s > thr for c, s in changed.items() if c not in al)
    return n1, n2


def cells_of_points(pts: Iterable[Sequence[float]], cells: Sequence[tuple[int, int]],
                    uv: Sequence[Sequence[float]]) -> set[tuple[int, int]]:  # fmt: skip
    """PURE: the cells whose patch holds each point (a point can touch several patches)."""
    out: set[tuple[int, int]] = set()
    for p in pts:
        for c, cu in zip(cells, uv, strict=True):
            b = patch(cu, (10**6, 10**6))
            if in_box(p, b):
                out.add(c)
    return out


def five_by_five(own: Sequence[int]) -> list[tuple[int, int]]:
    """PURE: the 25 cells around ``own`` (the drawn GM's cell), row by row (dy, then dx) -- index
    12 is ``own`` itself."""
    return [(int(own[0]) + dx, int(own[1]) + dy) for dy in (-2, -1, 0, 1, 2)
            for dx in (-2, -1, 0, 1, 2)]  # fmt: skip


def matcher_ground(img: Any, centre: Sequence[float], tpls: Sequence[Any], order: str = "RGB",
                   radius: int = MATCH_RADIUS) -> list[tuple[float, float]]:  # fmt: skip
    """PURE: the item matcher's hits (``item_icons.find_items``, its tuned thresholds) in the
    square of half side ``radius`` around ``centre``, as GROUND points (the sprite centre minus
    its template's anchor). ``order``: the frame's channel order ('RGB' recordings, 'BGR' live)."""
    import item_icons as ii

    anchors = {t.item_id: t.anchor for t in tpls}
    out = []
    for u, v, iid, *_ in ii.find_items(img, (float(centre[0]), float(centre[1])), radius, tpls,
                                       order=order):  # fmt: skip
        an = anchors.get(int(iid), (0.0, 0.0))
        out.append((float(u) - an[0], float(v) - an[1]))
    return out


def classify(before: Any, after: Any, cells: Sequence[tuple[int, int]],
             uv: Sequence[Sequence[float]], own: Sequence[int], ground: Iterable[Sequence[float]],
             thr: float = THR, max_shift_px: int = 99, gm_box: Sequence[float] | None = None
             ) -> dict[str, Any]:  # fmt: skip
    """PURE -- OPTION C's per-cell classification, the ONE implementation (this study and
    hunt_flow's v54 fast scan). ``before``: the frame ~0.45 s before the EXP line; ``after``: the
    STAND frame; ``cells`` / ``uv``: the cells and their projected centres on ``after`` (the
    camera on the drawn GM, standing on ``own``); ``ground``: the matcher's ground points
    (``matcher_ground`` on ``after``). The before frame is registered onto the after frame
    (``diff_map``, around ``own``'s pixel) and each cell's patch gets its changed share; a
    registration shift above ``max_shift_px`` makes every cell changed. Returns {"verdicts":
    cell -> "seen" | "unsure" | "empty" (``verdicts``), "changed": cell -> share, "covered": the
    cells the GM's sprite covers (``own`` + any centre inside drop_blobs.GM_BOX + GM_PAD),
    "shift": the registration (dy, dx)}."""
    import drop_blobs as db

    own_ = (int(own[0]), int(own[1]))
    centre = next((p for c, p in zip(cells, uv, strict=True) if tuple(c) == own_), uv[0])
    md, org, sh = diff_map(before, after, centre)
    ch = {c: 1.0 for c in cells} if max(abs(sh[0]), abs(sh[1])) > max_shift_px else {}
    if not ch:
        ch = {c: changed_share(md, org, patch(p, after.shape))
              for c, p in zip(cells, uv, strict=True)}  # fmt: skip
    gb = db.GM_BOX if gm_box is None else gm_box
    cov_box = (gb[0] - GM_PAD[0], gb[1] - GM_PAD[1], gb[2] + GM_PAD[2], gb[3] + GM_PAD[3])
    covered = {c for c, p in zip(cells, uv, strict=True) if c == own_ or in_box(p, cov_box)}
    seen = cells_of_points(ground, cells, uv)
    return {"verdicts": verdicts(cells, ch, seen, covered, thr), "changed": ch,
            "covered": covered, "shift": sh}  # fmt: skip


def server_spans(events: Sequence[Mapping[str, Any]]) -> list[tuple[int, int, int, int, int, int]]:
    """PURE: each floor item's (floor_id, item_id, x, y, t_appear, t_vanish) on its SERVER cell
    (the cell the hover must hit; t_vanish a large number while still there at the end)."""
    on: dict[int, tuple[int, int, int, int]] = {}
    out = []
    for e in events:
        t = int(e["t_mono_ns"])
        if e.get("type") == "floor_item_appear":
            on[int(e["floor_id"])] = (int(e.get("item_id") or -1), int(e["x"]), int(e["y"]), t)
        elif e.get("type") == "floor_item_vanish" and int(e["floor_id"]) in on:
            iid, x, y, t0 = on.pop(int(e["floor_id"]))
            out.append((int(e["floor_id"]), iid, x, y, t0, t))
    out += [(f, iid, x, y, t0, 1 << 62) for f, (iid, x, y, t0) in on.items()]
    return out


def line_anchor(kill_t: int, lines: Sequence[int], within_s: float = 3.0) -> int | None:
    """PURE: the first EXP line frame (the runner's ``exp_dead`` line_t_ns) at or after a kill,
    within ``within_s`` -- the moment a LIVE runner knows of the kill (p50 0.33 s after it,
    3.91 runs 1-2)."""
    import bisect

    i = bisect.bisect_left(lines, kill_t)
    if i < len(lines) and lines[i] - kill_t <= within_s * NS:
        return int(lines[i])
    return None


def session(sid: str, after_s: float, before_s: float, thr: float, lag_s: float = 0.5,
            from_line: bool = False, still_only: bool = True, max_shift_px: int = 99,
            limit: int | None = None, bgr: bool = False) -> list[dict[str, Any]]:  # fmt: skip
    """One record per kill of ours with both frames and the GM still. ``from_line``: the frames
    are timed from the EXP line's first frame (as a live runner can: before = line - before_s,
    after = line + after_s), kills without a line skipped; else from the server's kill.
    ``still_only`` False keeps the kills where the GM moved between the frames (packets): a live
    runner cannot tell, so its camera's move must turn the cells UNSURE by itself. ``limit``: the
    first records only (the tests); ``bgr``: the frames handed to ``classify`` in the LIVE
    runner's channel order (BGR, the matcher told so) -- the same verdicts are expected."""
    import drop_blobs as db
    import item_icons as ii
    import numpy as np

    ev = db.load_events(sid)
    lines: list[int] = []
    if from_line:
        bev = (db.DEMO_ROOT / sid / "events.jsonl").read_text().splitlines()
        lines = sorted(int(e["line_t_ns"]) for e in map(json.loads, filter(None, bev))
                       if e.get("kind") == "exp_dead" and e.get("line_t_ns"))  # fmt: skip
    pos = db.Positions(ev)
    proj = db.Projector()
    frames = db.load_frames(sid)
    tpls = ii.load_templates()
    items = server_spans(ev)
    out: list[dict[str, Any]] = []
    for k in db.kills_with_drops(ev, pos):
        if limit is not None and len(out) >= limit:
            break
        t_a = k.t
        if from_line:
            la = line_anchor(k.t, lines)
            if la is None:
                continue
            t_a = la
        fa = db.frame_at(frames, t_a + int(after_s * NS))
        fb = db.frame_before(frames, t_a - int(before_s * NS))
        if fa is None or fb is None or (fa[0] - t_a) > (after_s + 0.4) * NS:
            continue
        o_a = pos.gm_at(fa[0] - int(lag_s * NS))
        o_b = pos.gm_at(fb[0] - int(lag_s * NS))
        if o_a is None or o_b is None:
            continue
        moved = max(abs(o_a[0] - o_b[0]), abs(o_a[1] - o_b[1])) > 0.05
        if moved and still_only:
            out.append({"sid": sid, "t": k.t, "moved": True})
            continue
        r0 = (round(o_a[0]), round(o_a[1]))
        cells = five_by_five(r0)
        uv = [tuple(float(x) for x in p) for p in proj.project(o_a, cells)]
        img_a, img_b = db.read_rgb(fa[1]), db.read_rgb(fb[1])
        if bgr:  # as the runner grabs them
            img_a, img_b = (np.ascontiguousarray(img_a[..., ::-1]),
                            np.ascontiguousarray(img_b[..., ::-1]))  # fmt: skip
        ground_ = matcher_ground(img_a, uv[12], tpls, order="BGR" if bgr else "RGB")
        # --max-shift: tried as a "camera moved" signal and NOT one (see the module doc)
        cl_ = classify(img_b, img_a, cells, uv, r0, ground_, thr, max_shift_px)
        ver, ch, covered, sh = cl_["verdicts"], cl_["changed"], cl_["covered"], cl_["shift"]
        ts = fa[0] - int(lag_s * NS)
        mine = {d.floor_id for d in k.drops}
        present = [((x, y), fid in mine, iid) for fid, iid, x, y, t0, t1 in items
                   if t0 <= ts <= t1]  # fmt: skip
        mc = None if k.cell is None else (round(k.cell[0]), round(k.cell[1]))
        allowed = set(covered) | ({mc, (mc[0], mc[1] + 1)} if mc else set())
        n1, n2 = no_drop(ver, ch, thr, allowed)
        recs = []
        for cell, ours, iid in present:
            c = (int(cell[0]), int(cell[1]))
            if c in ver:
                recs.append({"cell": list(c), "ours": ours, "item_id": iid, "verdict": ver[c]})
        out.append({"sid": sid, "t": k.t, "moved": False, "drops": len(k.drops),
                    "cells": Counter(ver.values()), "items": recs, "n1": n1, "n2": n2,
                    "hits": len(ground_), "gm_moved": moved, "shift": list(sh)})  # fmt: skip
    return out


def summary(recs: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """PURE: the measures over kill records (``session``)."""
    ok = [r for r in recs if not r.get("moved")]
    cells: Counter[str] = Counter()
    it: Counter[str] = Counter()
    for r in ok:
        cells.update(r["cells"])
        for x in r["items"]:
            it[("ours|" if x["ours"] else "other|") + x["verdict"]] += 1
    drop_k = [r for r in ok if r["drops"]]
    none_k = [r for r in ok if not r["drops"]]

    def share(a: int, b: int) -> float | None:
        return round(a / b, 3) if b else None

    ours_n = sum(v for k_, v in it.items() if k_.startswith("ours|"))
    seen = it["ours|seen"]
    return {
        "kills": len(recs), "gm_still": len(ok), "with_drops": len(drop_k), "no_drop": len(none_k),
        "cells": dict(cells), "empty_cells_per_kill": share(cells["empty"], len(ok)),
        "hover_s_saved_per_kill": None if not ok else round(cells["empty"] / len(ok) * HOVER_S, 2),
        "items_by_verdict": dict(it),
        "LOSS_ours_on_empty": it["ours|empty"], "LOSS_any_on_empty": it["ours|empty"]
        + it["other|empty"], "ours_items": ours_n, "ours_seen_share": share(seen, ours_n),
        "N1_skip_on_no_drop": share(sum(r["n1"] for r in none_k), len(none_k)),
        "N1_FALSE_skip_on_drops": share(sum(r["n1"] for r in drop_k), len(drop_k)),
        "N2_skip_on_no_drop": share(sum(r["n2"] for r in none_k), len(none_k)),
        "N2_FALSE_skip_on_drops": share(sum(r["n2"] for r in drop_k), len(drop_k)),
    }  # fmt: skip


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("sids", nargs="+")
    ap.add_argument("--after", type=float, default=1.0, help="the stand frame, s after the kill")
    ap.add_argument("--before", type=float, default=0.4, help="the frame before the kill, s")
    ap.add_argument("--thr", type=float, default=THR, help="a patch's changed share = changed")
    ap.add_argument(
        "--from-line",
        action="store_true",
        help="time the frames from the EXP line (as live), not the server's kill",
    )
    ap.add_argument(
        "--all-kills",
        action="store_true",
        help="keep the kills where the GM moved (as live: the diff must cope)",
    )
    ap.add_argument(
        "--max-shift",
        type=int,
        default=99,
        help="a registration shift above this (px): the camera moved, skip nothing",
    )
    ap.add_argument("--json", default="")
    a = ap.parse_args()
    recs = [r for s in a.sids for r in session(s, a.after, a.before, a.thr,
                                               from_line=a.from_line,
                                               still_only=not a.all_kills,
                                               max_shift_px=a.max_shift)]  # fmt: skip
    out = {
        "args": vars(a),
        "pooled": summary(recs),
        "per_run": {s: summary([r for r in recs if r["sid"] == s]) for s in a.sids},
    }
    if a.json:
        Path(a.json).write_text(json.dumps(recs, default=str))
    print(json.dumps(out, indent=1, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
