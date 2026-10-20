#!/usr/bin/env python3
"""HELP BATT AUTHOR MAP ZONES (Batt 2026-10-20 ~21:0x, "MAP TRAPS": the bot walks through a NARROW
ENTRANCE into a big room and keeps circling inside it). OFFLINE: the map's walkability and the
banked runs' packets (ADR-0007 ground truth for where the GM was); nothing here runs during play
and nothing here changes the bot -- Batt draws the zones, the runner loads only his reviewed file
(config/map_zones/).

1. The map as an image: client ∩ server walkability (poring_dataset.walkable.both, decision 4),
   one cell = ``--px`` pixels, NORTH UP (map y grows upward, as the minimap readout and the server
   count it), a cell grid every 10 cells with coordinate labels, every 50 heavier; the runner's
   search area (border 20, warps / NPCs + 10) shaded apart; where the bot spent its time (banked
   runs) as a red heat layer; the CANDIDATES outlined with their doors in magenta.
2. CANDIDATES, found automatically:
   - the walkable cells' chessboard distance to the nearest blocked cell; the CORE = cells >= 3
     from a wall (a passage <= 4 cells wide has no core cell);
   - core components, then every walkable cell joins the nearest one (a geodesic Voronoi, 8-way
     with hunt_core.astar's diagonal rule): REGIONS;
   - a DOOR = the boundary between two regions; its width = the fewer of its two sides' cells;
   - a candidate = a POCKET: cut ONE door <= ``--max-door`` cells wide out of the region graph;
     whatever then no longer reaches the largest region (one region or a chain of them, >=
     ``--min-room`` cells) lies behind that door alone. Ranked by the bot's time inside
     (banked runs). (First version, rooms with all doors narrow, missed prt_fild08's south-east
     pocket: a chain of regions behind one 2-cell door, its inner door 6 wide.)
3. Per candidate: its doors (cells, width, a suggested no-cross line across each), its size and
   box, and from the banked runs: seconds per run-hour inside, the share of time, kills per
   minute inside vs outside, the longest single stay.

The image is client-derived (the GAT): it goes to /dev/shm and to Batt, never into the repo.

    map_zone_candidates.py [--map prt_fild08] [--sessions SID ...] [--px 4] [--out DIR]
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, deque
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

NS = 1_000_000_000
DEMO = Path("/dev/shm/poring-lab-demo")
OUT = Path("/dev/shm/poring-lab-tmp/map-zones")
N8 = [(-1, -1), (0, -1), (1, -1), (-1, 0), (1, 0), (-1, 1), (0, 1), (1, 1)]


def chess_distance(ok: Any) -> Any:
    """PURE: per walkable cell, the chessboard distance to the nearest non-walkable cell (or the
    map's edge): 1 next to a wall. 0 on blocked cells."""
    a = np.asarray(ok, dtype=bool)
    d = np.zeros(a.shape, dtype=np.int32)
    cur = a.copy()
    k = 0
    while cur.any():
        k += 1
        d[cur] = k
        p = np.pad(cur, 1, constant_values=False)
        nxt = cur.copy()
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                nxt &= p[1 + dy : 1 + dy + a.shape[0], 1 + dx : 1 + dx + a.shape[1]]
        cur = nxt
    return d


def _steps(ok: Any, x: int, y: int) -> Iterable[tuple[int, int]]:
    """8-way steps from (x, y) on ``ok`` ([y, x]); a diagonal needs both side cells
    (hunt_core.astar's rule)."""
    h, w = ok.shape
    for dx, dy in N8:
        nx, ny = x + dx, y + dy
        if not (0 <= nx < w and 0 <= ny < h) or not ok[ny, nx]:
            continue
        if dx and dy and not (ok[y, nx] and ok[ny, x]):
            continue
        yield nx, ny


def label(mask: Any, ok: Any) -> Any:
    """PURE: connected components of ``mask`` (8-way with the diagonal rule on ``ok``):
    -1 outside, else 0..n-1."""
    m = np.asarray(mask, dtype=bool)
    lab = np.full(m.shape, -1, dtype=np.int32)
    n = 0
    for y0, x0 in zip(*np.nonzero(m), strict=True):
        if lab[y0, x0] >= 0:
            continue
        lab[y0, x0] = n
        q = deque([(int(x0), int(y0))])
        while q:
            x, y = q.popleft()
            for nx, ny in _steps(ok, x, y):
                if m[ny, nx] and lab[ny, nx] < 0:
                    lab[ny, nx] = n
                    q.append((nx, ny))
        n += 1
    return lab


def regions(ok: Any, core_min: int = 3) -> tuple[Any, Any]:
    """PURE: (region label per walkable cell, -1 elsewhere; the distance map). Core components
    (distance >= ``core_min``) grow over the walkable cells breadth first (a geodesic Voronoi)."""
    a = np.asarray(ok, dtype=bool)
    d = chess_distance(a)
    core = label(d >= core_min, a)
    reg = core.copy()
    q = deque((int(x), int(y)) for y, x in zip(*np.nonzero(core >= 0), strict=True))
    while q:
        x, y = q.popleft()
        for nx, ny in _steps(a, x, y):
            if reg[ny, nx] < 0:
                reg[ny, nx] = reg[y, x]
                q.append((nx, ny))
    return reg, d


def doors(reg: Any, ok: Any) -> dict[tuple[int, int, int], dict[str, Any]]:
    """PURE: every DOOR between two regions (a < b): the boundary cells of a region pair, split
    into connected clusters -- two separate passages between the same pair are two doors (else
    cutting "the" door would seal a room that has another way in). Per door (a, b, i): the
    cells of each side, the width (the fewer side's cell count) and all its cells."""
    sides: dict[tuple[int, int], dict[int, set[tuple[int, int]]]] = {}
    for y, x in zip(*np.nonzero(reg >= 0), strict=True):
        ra = int(reg[y, x])
        for nx, ny in _steps(ok, int(x), int(y)):
            rb = int(reg[ny, nx])
            if rb >= 0 and rb != ra:
                key = (min(ra, rb), max(ra, rb))
                sides.setdefault(key, {}).setdefault(ra, set()).add((int(x), int(y)))
    out = {}
    for key, s in sides.items():
        cells = s.get(key[0], set()) | s.get(key[1], set())
        left = set(cells)
        i = 0
        while left:
            seed = left.pop()
            comp, q = {seed}, deque([seed])
            while q:
                x, y = q.popleft()
                for dx, dy in N8:
                    c = (x + dx, y + dy)
                    if c in left:
                        left.discard(c)
                        comp.add(c)
                        q.append(c)
            a_ = comp & s.get(key[0], set())
            b_ = comp & s.get(key[1], set())
            out[(key[0], key[1], i)] = {"width": min(len(a_), len(b_)), "cells": sorted(comp),
                                        "side_a": sorted(a_), "side_b": sorted(b_)}  # fmt: skip
            i += 1
    return out


def door_line(door: dict[str, Any], ok: Any) -> list[list[int]]:
    """PURE: a suggested no-cross line across a door: through its centre, PERPENDICULAR to the
    way through it (side a's centre -> side b's), extended until it meets a blocked cell on each
    side (so the line reaches the walls)."""
    pts = np.asarray(door["cells"], dtype=float)
    c = pts.mean(axis=0)
    a_ = np.asarray(door["side_a"], dtype=float).mean(axis=0)
    b_ = np.asarray(door["side_b"], dtype=float).mean(axis=0)
    p_ = b_ - a_
    n_ = float(np.hypot(*p_))
    v = np.array([1.0, 0.0]) if n_ == 0 else np.array([-p_[1], p_[0]]) / n_
    h, w = ok.shape
    ends = []
    for sgn in (-1.0, 1.0):
        t = 0.0
        p = c
        while True:
            t += 0.5
            q = c + sgn * t * v
            xi, yi = int(round(q[0])), int(round(q[1]))
            if not (0 <= xi < w and 0 <= yi < h) or not ok[yi, xi] or t > 20:
                break
            p = q
        ends.append([int(round(p[0] + sgn * v[0])), int(round(p[1] + sgn * v[1]))])
    return ends


def gm_track(sid: str, step_s: float = 1.0) -> tuple[list[tuple[int, tuple[int, int]]], list[Any]]:
    """The GM's cell once a ``step_s`` over the session's window (packets), and its kills."""
    import arm_judge as aj
    import drop_blobs as db

    man = json.loads((DEMO / sid / "manifest.json").read_text())
    ev = db.load_events(sid)
    pos = db.Positions(ev)
    t0 = int(man.get("t0_mono_ns") or ev[0]["t_mono_ns"])
    t1 = int(man.get("t1_mono_ns") or ev[-1]["t_mono_ns"])
    out = []
    t = t0
    while t <= t1:
        p = pos.gm_at(t)
        if p is not None:
            out.append((t, (int(round(p[0])), int(round(p[1])))))
        t += int(step_s * NS)
    kills = [(t, pos.gm_at(t)) for t, _g in aj.kills_of(ev) if t0 <= t <= t1]
    return out, kills


def dwell(reg: Any, sessions: Sequence[str], step_s: float = 1.0) -> dict[str, Any]:
    """Per region: seconds, kills, the longest single stay (s); the run hours."""
    sec: Counter[int] = Counter()
    kil: Counter[int] = Counter()
    longest: Counter[int] = Counter()
    heat = np.zeros(reg.shape, dtype=np.float64)
    hours = 0.0
    for sid in sessions:
        tr, kills = gm_track(sid, step_s)
        hours += len(tr) * step_s / 3600
        run_r, run_n = None, 0
        for _t, (x, y) in tr:
            if not (0 <= y < reg.shape[0] and 0 <= x < reg.shape[1]):
                continue
            heat[y, x] += step_s
            r = int(reg[y, x])
            sec[r] += step_s
            if r == run_r:
                run_n += 1
            else:
                run_r, run_n = r, 1
            longest[r] = max(longest[r], int(run_n * step_s))
        for _t, p in kills:
            if p is not None:
                x, y = int(round(p[0])), int(round(p[1]))
                if 0 <= y < reg.shape[0] and 0 <= x < reg.shape[1]:
                    kil[int(reg[y, x])] += 1
    return {"sec": sec, "kills": kil, "longest": longest, "heat": heat, "hours": hours}


def pockets(sizes: Counter[int], dr: dict[tuple[int, int, int], dict[str, Any]], max_door: int,
            min_room: int) -> list[tuple[tuple[int, int, int], set[int]]]:  # fmt: skip
    """PURE: (the door, the regions behind it) for every door <= ``max_door`` wide whose removal
    cuts regions of >= ``min_room`` cells in all off from the largest region."""
    if not sizes:
        return []
    main = sizes.most_common(1)[0][0]
    adj: dict[int, set[tuple[int, int, int]]] = {}
    for k in dr:
        adj.setdefault(k[0], set()).add(k)
        adj.setdefault(k[1], set()).add(k)
    out = []
    for cut, v in dr.items():
        if v["width"] > max_door:
            continue
        seen = {main}
        q = deque([main])
        while q:
            r = q.popleft()
            for k in adj.get(r, ()):
                if k == cut:
                    continue
                o = k[1] if k[0] == r else k[0]
                if o not in seen:
                    seen.add(o)
                    q.append(o)
        side = {r for r in cut[:2] if r not in seen}
        if not side:
            continue  # the door is not a cut: the other side is reached another way
        behind, q = set(side), deque(side)
        while q:
            r = q.popleft()
            for k in adj.get(r, ()):
                if k == cut:
                    continue
                o = k[1] if k[0] == r else k[0]
                if o not in seen and o not in behind:
                    behind.add(o)
                    q.append(o)
        if sum(sizes[r] for r in behind) >= min_room:
            out.append((cut, behind))
    return out


def candidates(reg: Any, ok: Any, dr: dict[tuple[int, int, int], dict[str, Any]],
               dw: dict[str, Any], min_room: int, max_door: int
               ) -> list[dict[str, Any]]:  # fmt: skip
    """PURE given the inputs: the candidate POCKETS, ranked by the bot's time inside."""
    sizes = Counter(int(v) for v in reg[reg >= 0].ravel())
    tot_s = sum(dw["sec"].values()) or 1.0
    tot_k = sum(dw["kills"].values())
    out = []
    for cut, behind in pockets(sizes, dr, max_door, min_room):
        m_ = np.isin(reg, list(behind))
        ys, xs = np.nonzero(m_)
        s_in = float(sum(dw["sec"].get(r, 0.0) for r in behind))
        k_in = int(sum(dw["kills"].get(r, 0) for r in behind))
        s_out = tot_s - s_in
        inner = [(k, v) for k, v in dr.items() if k != cut and k[0] in behind and k[1] in behind]
        v = dr[cut]
        out.append({
            "regions": sorted(behind), "cells": int(sum(sizes[r] for r in behind)),
            "box": [int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())],
            "entrance": {"width": v["width"], "cells": [list(c) for c in v["cells"]],
                         "suggested_no_cross": door_line(v, ok)},
            "inner_doors": [{"width": w_["width"], "cells": [list(c) for c in w_["cells"]]}
                            for _k, w_ in inner],
            "bot_s_per_run_hour": round(s_in / max(dw["hours"], 1e-9), 1),
            "bot_time_share": round(s_in / tot_s, 4),
            "kills_per_min_inside": round(k_in / (s_in / 60), 2) if s_in else None,
            "kills_per_min_outside": round((tot_k - k_in) / (s_out / 60), 2) if s_out else None,
            "longest_stay_s_one_region": int(max(dw["longest"].get(r, 0) for r in behind)),
        })  # fmt: skip
    out.sort(key=lambda c: -c["bot_s_per_run_hour"])
    for i, c in enumerate(out, 1):
        c["id"] = f"C{i}"
    return out


def render(ok: Any, area: Any, reg: Any, cands: Sequence[dict[str, Any]], heat: Any, px: int,
           out: Path, title: str, marks: Sequence[tuple[int, int, str]] = ()) -> None:  # fmt: skip
    """The image, NORTH UP: row 0 = the map's top (the largest y)."""
    from PIL import Image, ImageDraw

    h, w = ok.shape
    m = 34  # margin for the labels
    img = np.zeros((h, w, 3), dtype=np.uint8)
    img[:] = (60, 60, 60)  # blocked
    img[ok] = (205, 195, 165)  # walkable
    img[ok & ~area] = (170, 175, 185)  # walkable but outside the runner's search area
    hv = np.log1p(heat)
    if hv.max() > 0:
        a_ = np.clip(hv / hv.max(), 0, 1)
        sel = a_ > 0
        base = img[sel].astype(float)
        red = np.array([220, 30, 30], dtype=float)
        img[sel] = (base * (1 - 0.75 * a_[sel, None]) + red * 0.75 * a_[sel, None]).astype(np.uint8)
    for r in {r for c in cands for r in c["regions"]}:
        edge = reg == r
        inner = edge.copy()
        for dy, dx in N8:
            inner &= np.roll(np.roll(edge, dy, 0), dx, 1)
        img[edge & ~inner] = (30, 90, 230)  # the candidate room's outline
    for c in cands:
        for x, y in c["entrance"]["cells"]:
            img[y, x] = (230, 0, 200)  # the entrance
    img = img[::-1]  # NORTH UP
    big = np.kron(img, np.ones((px, px, 1), dtype=np.uint8))
    canvas = Image.new("RGB", (w * px + 2 * m, h * px + 2 * m), (255, 255, 255))
    canvas.paste(Image.fromarray(big), (m, m))
    dr = ImageDraw.Draw(canvas)
    for k in range(0, max(w, h) + 1, 10):
        col = (40, 40, 40) if k % 50 == 0 else (120, 120, 120)
        wid = 2 if k % 50 == 0 else 1
        if k <= w:
            xx = m + k * px
            dr.line([(xx, m), (xx, m + h * px)], fill=col, width=wid)
            dr.text((xx - 8, 4), str(k), fill=(0, 0, 0))
            dr.text((xx - 8, m + h * px + 6), str(k), fill=(0, 0, 0))
        if k <= h:
            yy = m + (h - k) * px
            dr.line([(m, yy), (m + w * px, yy)], fill=col, width=wid)
            dr.text((2, yy - 5), str(k), fill=(0, 0, 0))
            dr.text((m + w * px + 4, yy - 5), str(k), fill=(0, 0, 0))
    for c in cands:  # the label beside its entrance
        x0, y0 = c["entrance"]["cells"][0]
        dr.text((m + x0 * px - 26, m + (h - 1 - y0) * px - 4), c["id"], fill=(0, 0, 160))
    for x, y, tag in marks:
        cx, cy = m + x * px + px // 2, m + (h - 1 - y) * px + px // 2
        dr.ellipse([cx - 5, cy - 5, cx + 5, cy + 5], outline=(0, 160, 0), width=2)
        dr.text((cx + 6, cy - 6), tag, fill=(0, 110, 0))
    dr.text((m, h * px + m + 18), title, fill=(0, 0, 0))
    canvas.save(out)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--map", default="prt_fild08")
    ap.add_argument(
        "--sessions",
        nargs="*",
        default=None,
        help="banked runs (default: every hunt-flow v43+ session on the map)",
    )
    ap.add_argument("--px", type=int, default=4)
    ap.add_argument("--min-room", type=int, default=150)
    ap.add_argument("--max-door", type=int, default=4)
    ap.add_argument("--mark", nargs="*", default=[], help="x,y,TAG points to circle (green)")
    ap.add_argument("--out", default=str(OUT))
    a = ap.parse_args()
    import anim_region as ar
    import hunt_core as hc

    from poring_dataset import walkable as wk

    _, both = wk.load_both(a.map)
    ok = np.asarray(both, dtype=bool)
    stand = ar.stand_grid(a.map, None)
    kb = Path(__file__).resolve().parents[1] / "data" / "kb"
    warps = json.loads((kb / "warps.json").read_text()).get(a.map, [])
    npcs = json.loads((kb / "npc_cells.json").read_text())["maps"].get(a.map, {}).get("npcs", [])
    keep = [(w_["x"], w_["y"], w_["span_x"], w_["span_y"]) for w_ in warps]
    keep += [(n["x"], n["y"], 1, 1) for n in npcs]
    area = hc.search_area(stand, keep, margin=10)
    sids = a.sessions
    if sids is None:
        sids = []
        for d in sorted(DEMO.iterdir()):
            nm = d.name
            if "-demo-hunt-flow" not in nm or not (d / "manifest.json").exists():
                continue
            try:
                v = int(nm.rsplit("hunt-flow", 1)[1].rstrip("abcdefgh") or 0)
                man = json.loads((d / "manifest.json").read_text())
            except (ValueError, OSError):
                continue
            if v >= 43 and man.get("map") == a.map and (d / "packets.jsonl.gz").exists():
                sids.append(nm)
    reg, _d = regions(ok)
    dr = doors(reg, ok)
    dw = dwell(reg, sids)
    cands = candidates(reg, ok, dr, dw, a.min_room, a.max_door)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    marks = []
    for s in a.mark:
        x, y, tag = s.split(",", 2)
        marks.append((int(x), int(y), tag))
    title = (f"{a.map}: client & server walkable (beige), outside the search area (grey), the "
             f"bot's time (red, {len(sids)} runs, {dw['hours']:.1f} h), candidate pockets (blue) "
             "and their entrances (magenta); NORTH UP, x right")  # fmt: skip
    render(ok, area, reg, cands, dw["heat"], a.px, out / f"{a.map}.png", title, marks)
    (out / f"{a.map}.candidates.json").write_text(json.dumps(
        {"map": a.map, "sessions": sids, "hours": round(dw["hours"], 2), "candidates": cands},
        indent=1))  # fmt: skip
    for c in cands[:15]:
        print(c["id"], "regions", c["regions"], "cells", c["cells"], "box", c["box"], "s/run-h",
              c["bot_s_per_run_hour"], "share", c["bot_time_share"], "kpm in/out",
              c["kills_per_min_inside"], c["kills_per_min_outside"], "longest",
              c["longest_stay_s_one_region"], "entrance", c["entrance"]["width"],
              c["entrance"]["cells"], "line", c["entrance"]["suggested_no_cross"],
              "inner", [d["width"] for d in c["inner_doors"]])  # fmt: skip
    print(f"{len(cands)} candidates; {len(sids)} runs, {dw['hours']:.1f} h -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
