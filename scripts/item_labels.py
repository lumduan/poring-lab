#!/usr/bin/env python3
"""Floor-item labels for the detector class ``item`` (docs/planning/item-class.md, PRE-REGISTERED
2026-10-23 22:38:40 ICT, a46893d; amendment A 19201ea). Packets are OFFLINE ground truth only
(ADR-0007): they place each floor item; the frames are never an input of a live decision.

    item_labels.py measure --map prt_fild08|orcsdun01 [--table PARAMS]   FIT data only
    item_labels.py freeze                                               params.json + sha256
    item_labels.py label --map M --split train|test                     labels + G1 rows
    item_labels.py check --map M                                        G1 / G2 per map
    item_labels.py pack --seed 5                                        blind round 1

THE RULE (section 3 of the plan): an item is on the floor from its floor_item_appear to its
floor_item_vanish (or our map_change); on a frame (capture time t_f, the file name's t_mono_ns)
it is labelled when t_a + D_APPEAR <= t_f < t_v; the frame is EXCLUDED while any item settles
(t_a <= t_f < t_a + D_APPEAR) or vanishes (t_v <= t_f < t_v + D_GONE). Only frames where our
character stood still for STILL_S. The item's cell = (x + OX[sub_x], y + OY[sub_y]) projected as
the monsters' anchors (labels_v2.project_cell), + the item's anchor; the box = its template's
mask box (+PAD), fitted by masked colour NCC within +-R_FIT (tau per map). Frame exclusions:
item_truth_unknown, self_moving, self_dead, item_settling, item_vanishing, item_untemplated,
ui_partial, edge_partial, stacked, under_self, ui_layout_mismatch, unfit. ROUTE U (the cache):
no unit but our own on screen over [t_f - STILL_S, t_f].

Everything this writes is client-derived (frames, crops, templates): /dev/shm/poring-lab-tmp/
item-r1/ only, never the repo. Item NAMES are never written (ids only).
"""

from __future__ import annotations

import argparse
import bisect
import gzip
import hashlib
import json
import math
import os
import random
import sys
import time
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

ROOT = Path(__file__).resolve().parents[1]
# read-only fallbacks: data/, the generated map cache (the main checkout, its owner's home)
MAIN = Path.home() / "docker" / "poring-lab"
DATASETS = Path("/mnt/poring-lab-datasets")
OUT = Path("/dev/shm/poring-lab-tmp/item-r1")
NS = 10**9

# --- the pre-registered constants (item-class.md section 3, 4) -----------------------------------
STILL_S = 0.8
STEP_S = 0.1
PAD = 1
R_FIT = 4
R_G1 = 1
R_G2 = 8
R_DELAY = 2
STACK_IOU = 0.5
REACH = (-80.0, -40.0, 1360.0, 880.0)  # Route U: a unit's ground anchor inside -> on screen
EVERY = 3
NEG_EVERY = 15
SUBS = (3, 6, 9, 12)
H12 = {s: s / 12 - 0.5 for s in SUBS}
H16 = {s: (s - 8) / 16 for s in SUBS}
# measurement (section 4)
TPL_MIN_AGE_S = 2.5
TPL_BEFORE_VANISH_S = 1.0
ITEM_GAP_PX = 24.0
SELF_MARGIN_PX = 8.0
UNIT_NEAR_CELLS = 1.0
REGION_MARGIN_PX = 44.0
UI_MARGIN_PX = 30.0
PER_INSTANCE = 8
INSTANCE_GAP_S = 1.0
MEASURE_EVERY_S = 0.4
SUB_SEARCH_PX = 10
EMPTY_ITEM_CELLS = 3
EMPTY_UNIT_CELLS = 2
DELAY_MAX_S = 3.0
PLATEAU = (2.0, 3.0)
APPEAR_SHARE = 0.95
APPEAR_UPTO_S = 2.0
GONE_MAX_S = 1.5
GONE_SHARE = 0.10
DELAY_MARGIN_S = 0.2
GONE_MIN_FRAMES = 30
GONE_FALLBACK_S = 1.0
BLIND_ITEMS = 40
BLIND_NEG = 20
PER_FLOOR_ITEM = 3
CROP_HALF = 48
CROP_SCALE = 3

# --- the split (section 2, amendment A) ----------------------------------------------------------
ORC_DEMO = "20261022T184536-demo-human-demo-orcsdun01-crusader"
SPLIT: dict[str, dict[str, Any]] = {
    "prt_fild08": {
        "fit": ["20261020T093755-demo-hunt-flow48", "20261020T104057-demo-hunt-flow48"],
        "train": [
            "20261020T151005-demo-hunt-flow49",
            "20261020T161139-demo-hunt-flow49",
            "20261020T183131-demo-hunt-flow50",
            "20261021T092850-demo-hunt-flow52",
            "20261021T150152-demo-hunt-flow53",
            "20261022T012118-demo-hunt-flow55",
        ],
        "test": ["20261021T223812-demo-hunt-flow54", "20261022T032441-demo-hunt-flow55"],
    },
    "orcsdun01": {  # one session, cut by time (seconds after its first frame)
        "fit": [ORC_DEMO],
        "train": [ORC_DEMO],
        "test": [ORC_DEMO],
        "blocks": {
            "fit": (0.0, 282.913519548),
            "train": (302.913519548, 649.527039097),
            "test": (669.527039097, math.inf),
        },
    },
}
REFUSED = ("-col2",)  # orcsdun01's monster TEST block: never read


def split_of(map_name: str, split: str) -> list[str]:
    sids = list(SPLIT[map_name][split])
    for s in sids:
        if any(s.endswith(r) for r in REFUSED):
            raise SystemExit(f"{s}: the monster TEST block is never read")
    return sids


# --- packets: floor items (PURE) -----------------------------------------------------------------


@dataclass(frozen=True)
class Floor:
    floor_id: int
    item_id: int
    x: int
    y: int
    sub_x: int
    sub_y: int
    kind: str
    t_a: int
    t_v: int
    vanished: bool  # a floor_item_vanish ended it (else our map change or the stream's end)


def floor_items(events: Sequence[Mapping[str, Any]]) -> list[Floor]:
    """Every floor item's span: appear (either kind) .. its vanish, our map change, or the last
    packet. A floor id seen again after an out-of-sight vanish is a new span."""
    evs = sorted(events, key=lambda e: int(e["t_mono_ns"]))
    end = int(evs[-1]["t_mono_ns"]) if evs else 0
    live: dict[int, dict[str, Any]] = {}
    out: list[Floor] = []

    def close(d: dict[str, Any], t: int, vanished: bool) -> None:
        out.append(
            Floor(
                d["floor_id"],
                d["item_id"],
                d["x"],
                d["y"],
                d["sub_x"],
                d["sub_y"],
                d["kind"],
                d["t_a"],
                t,
                vanished,
            )
        )

    for e in evs:
        typ, t = e.get("type"), int(e["t_mono_ns"])
        if typ == "floor_item_appear":
            fid = int(e["floor_id"])
            if fid in live:  # re-sent while live: the first keeps its time
                continue
            live[fid] = {
                "floor_id": fid,
                "item_id": int(e.get("item_id") or -1),
                "x": int(e["x"]),
                "y": int(e["y"]),
                "sub_x": int(e.get("sub_x") or 0),
                "sub_y": int(e.get("sub_y") or 0),
                "kind": str(e.get("kind")),
                "t_a": t,
            }
        elif typ == "floor_item_vanish":
            d = live.pop(int(e["floor_id"]), None)
            if d is not None:
                close(d, t, True)
        elif typ == "map_change":
            for d in live.values():
                close(d, t, False)
            live.clear()
    for d in live.values():
        close(d, end, False)
    return sorted(out, key=lambda f: f.t_a)


def first_map_change(events: Iterable[Mapping[str, Any]]) -> int | None:
    ts = [int(e["t_mono_ns"]) for e in events if e.get("type") == "map_change"]
    return min(ts) if ts else None


def phase(f: Floor, t_f: int, d_appear_ns: int, d_gone_ns: int) -> str:
    """PURE: 'on' (labelled), 'settling', 'vanishing' or 'none' at frame time ``t_f``."""
    if f.vanished and f.t_v <= t_f < f.t_v + d_gone_ns:
        return "vanishing"
    if t_f < f.t_a or t_f >= f.t_v:
        return "none"
    if t_f < f.t_a + d_appear_ns:
        return "settling"
    return "on"


def item_cell(f: Floor, ox: Mapping[int, float], oy: Mapping[int, float]) -> tuple[float, float]:
    """The item's fractional cell under a sub-cell table (cells, keyed by the packet's sub)."""
    return f.x + float(ox.get(f.sub_x, 0.0)), f.y + float(oy.get(f.sub_y, 0.0))


# --- boxes (PURE) --------------------------------------------------------------------------------

Rect = tuple[float, float, float, float]


def tpl_box(centre: tuple[float, float], hw: tuple[int, int], pad: float = PAD) -> Rect:
    """The box of a template (h x w px) whose centre is ``centre``: its pixels' extent + pad."""
    h, w = hw
    cu, cv = centre
    return (
        cu - (w - 1) / 2 - pad,
        cv - (h - 1) / 2 - pad,
        cu + (w + 1) / 2 + pad,
        cv + (h + 1) / 2 + pad,
    )


def area(b: Rect) -> float:
    return max(0.0, b[2] - b[0]) * max(0.0, b[3] - b[1])


def inter(a: Rect, b: Rect) -> float:
    return area((max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3])))


def iou(a: Rect, b: Rect) -> float:
    i = inter(a, b)
    u = area(a) + area(b) - i
    return i / u if u > 0 else 0.0


def ui_status(box: Rect, rects: Sequence[Rect], size: tuple[int, int]) -> str:
    """PURE: 'clear', 'hidden' (wholly inside a UI window or wholly off the region: not drawn, no
    label), 'ui_partial' or 'edge_partial' (frame exclusions). ``rects`` are (x0, y0, x1, y1)."""
    a = area(box)
    region = (0.0, 0.0, float(size[0]), float(size[1]))
    inside = inter(box, region)
    if inside <= 0:
        return "hidden"
    if inside < a - 1e-9:
        return "edge_partial"
    for r in rects:
        s = inter(box, r)
        if s >= a - 1e-9:
            return "hidden"
        if s > 0:
            return "ui_partial"
    return "clear"


def stacked(boxes: Sequence[Rect], thr: float = STACK_IOU) -> bool:
    return any(
        iou(boxes[i], boxes[j]) >= thr for i in range(len(boxes)) for j in range(i + 1, len(boxes))
    )


def in_reach(u: float, v: float, reach: Rect = REACH) -> bool:
    return reach[0] <= u <= reach[2] and reach[1] <= v <= reach[3]


# --- measurement maths (PURE) --------------------------------------------------------------------


def youden(present: Sequence[float], absent: Sequence[float]) -> float:
    """The threshold maximising TPR - FPR (present >= tau counts as found); ties: the lowest."""
    p = np.sort(np.asarray(present, float))
    a = np.sort(np.asarray(absent, float))
    cands = np.unique(np.concatenate([p, a]))
    best, best_t = -2.0, float(cands[0]) if len(cands) else 0.5
    for t in cands:
        tpr = 1.0 - np.searchsorted(p, t, side="left") / max(1, len(p))
        fpr = 1.0 - np.searchsorted(a, t, side="left") / max(1, len(a))
        if tpr - fpr > best + 1e-12:
            best, best_t = tpr - fpr, float(t)
    return best_t


def bin_shares(
    ages_s: Sequence[float], present: Sequence[bool], lo: float, hi: float, step: float = 0.1
) -> list[tuple[float, int, float]]:
    """(bin start, n, present share) per ``step`` bin of [lo, hi)."""
    nb = int(round((hi - lo) / step))
    n = [0] * nb
    k = [0] * nb
    for a, p in zip(ages_s, present, strict=True):
        i = int(math.floor((a - lo) / step + 1e-9))
        if 0 <= i < nb:
            n[i] += 1
            k[i] += bool(p)
    return [
        (round(lo + i * step, 3), n[i], (k[i] / n[i]) if n[i] else float("nan")) for i in range(nb)
    ]


def appear_delay(
    bins: Sequence[tuple[float, int, float]],
    plateau: float,
    upto: float = APPEAR_UPTO_S,
    share: float = APPEAR_SHARE,
    margin: float = DELAY_MARGIN_S,
) -> float | None:
    """The first bin start from which EVERY bin up to ``upto`` has share >= share x plateau, plus
    the margin; empty bins count as failing. None when no bin qualifies."""
    use = [b for b in bins if b[0] < upto - 1e-9]
    for i in range(len(use)):
        if all(b[1] > 0 and b[2] >= share * plateau for b in use[i:]):
            return round(use[i][0] + margin, 3)
    return None


def gone_delay(
    bins: Sequence[tuple[float, int, float]],
    share: float = GONE_SHARE,
    margin: float = DELAY_MARGIN_S,
) -> float | None:
    for i in range(len(bins)):
        if all(b[1] > 0 and b[2] <= share for b in bins[i:]):
            return round(bins[i][0] + margin, 3)
    return None


def solve_subtable(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Least squares: r_i = J_i (dX[sx], dY[sy]) + A_item, dX[6] = dY[6] = 0 (H12's 6 kept; a
    constant goes into the anchors). ``rows``: {'r': (du, dv) px vs the H12 projection, 'J': 2x2
    px per cell, 'sx', 'sy', 'item'}. One pass, then rows beyond 3 x 1.4826 MAD (>= 2 px) of the
    residual norm are dropped and it is solved again. Returns OX / OY (cells) + the fit's stats."""
    free = [s for s in SUBS if s != 6]
    items = sorted({int(r["item"]) for r in rows})
    col = {("x", s): i for i, s in enumerate(free)}
    col.update({("y", s): len(free) + i for i, s in enumerate(free)})
    base = 2 * len(free)
    icol = {it: base + 2 * k for k, it in enumerate(items)}
    ncol = base + 2 * len(items)

    def build(rs: Sequence[Mapping[str, Any]]) -> tuple[Any, Any]:
        a = np.zeros((2 * len(rs), ncol))
        b = np.zeros(2 * len(rs))
        for i, r in enumerate(rs):
            j = np.asarray(r["J"], float)
            for row in (0, 1):
                k = 2 * i + row
                if int(r["sx"]) != 6:
                    a[k, col[("x", int(r["sx"]))]] = j[row, 0]
                if int(r["sy"]) != 6:
                    a[k, col[("y", int(r["sy"]))]] = j[row, 1]
                a[k, icol[int(r["item"])] + row] = 1.0
                b[k] = float(r["r"][row])
        return a, b

    use = list(rows)
    sol: Any = None
    dropped = 0
    for it in range(2):
        a, b = build(use)
        sol, *_ = np.linalg.lstsq(a, b, rcond=None)
        if it == 0:
            res = (a @ sol - b).reshape(-1, 2)
            nrm = np.hypot(res[:, 0], res[:, 1])
            med = float(np.median(nrm))
            mad = float(np.median(np.abs(nrm - med))) * 1.4826
            lim = max(2.0, med + 3 * mad)
            keep = nrm <= lim
            dropped = int((~keep).sum())
            use = [r for r, k in zip(use, keep, strict=True) if k]
    a, b = build(use)
    res = (a @ sol - b).reshape(-1, 2)
    dx = {s: (float(sol[col[("x", s)]]) if s != 6 else 0.0) for s in SUBS}
    dy = {s: (float(sol[col[("y", s)]]) if s != 6 else 0.0) for s in SUBS}
    n_sub = {f"x{s}": sum(1 for r in use if int(r["sx"]) == s) for s in SUBS}
    n_sub.update({f"y{s}": sum(1 for r in use if int(r["sy"]) == s) for s in SUBS})
    return {
        "ox": {s: round(H12[s] + dx[s], 4) for s in SUBS},
        "oy": {s: round(H12[s] + dy[s], 4) for s in SUBS},
        "dx_vs_h12": {s: round(dx[s], 4) for s in SUBS},
        "dy_vs_h12": {s: round(dy[s], 4) for s in SUBS},
        "rows": len(rows),
        "used": len(use),
        "dropped": dropped,
        "n_per_sub": n_sub,
        "residual_px_median": round(float(np.median(np.hypot(res[:, 0], res[:, 1]))), 3),
    }


# --- sessions ------------------------------------------------------------------------------------


@dataclass
class Session:
    sid: str
    map: str
    manifest: dict[str, Any]
    events: list[dict[str, Any]]
    frames: list[tuple[int, int, Path]]  # (k, t_mono_ns, path), recording order
    block: tuple[float, float] | None = None  # orcsdun01: seconds after the first frame


def load_session(sid: str, block: tuple[float, float] | None = None) -> Session:
    if any(sid.endswith(r) for r in REFUSED):
        raise SystemExit(f"{sid}: the monster TEST block is never read")
    d = DATASETS / sid
    manifest = json.loads((d / "manifest.json").read_text())
    with gzip.open(d / "packets.jsonl.gz", "rt") as fh:
        events = sorted((json.loads(x) for x in fh), key=lambda e: int(e["t_mono_ns"]))
    fd = Path(manifest["frames_dir"])
    frames = []
    for name in os.listdir(fd):  # one directory, no walk
        if name.endswith(".jpg"):
            k, _, t = name[:-4].partition("-")
            frames.append((int(k), int(t), fd / name))
    frames.sort()
    return Session(sid, str(manifest["map"]), manifest, events, frames, block)


def in_block(s: Session, t_f: int) -> bool:
    if s.block is None:
        return True
    t0 = s.frames[0][1]
    rel = (t_f - t0) / NS
    return s.block[0] <= rel < s.block[1]


def read_rgb(path: Path) -> Any:
    import simplejpeg

    return simplejpeg.decode_jpeg(path.read_bytes(), colorspace="RGB")


class Geo:
    """The camera and GAT of one map (the session backend's fitted camera), projecting fractional
    cells with our character's still cell as the camera target (labels_v2.project_cell)."""

    def __init__(self, map_name: str, backend: str = "rdp") -> None:
        from poring_dataset.projection import camera_file
        from poring_dataset.render import load_scene

        self.map = map_name.removesuffix(".gat")
        cj = json.loads(camera_file(backend).read_text())
        self._scene = load_scene(cj, self.map, (0.0, 0.0))

    def scene(self, player: tuple[float, float]) -> Any:
        return replace(self._scene, player=(float(player[0]), float(player[1])))

    def project(self, scene: Any, cell: tuple[float, float]) -> tuple[float, float]:
        from poring_dataset.labels_v2 import project_cell

        (u, v), _z = project_cell(scene, cell)
        return u, v

    def jacobian(self, scene: Any, cell: tuple[float, float], h: float = 0.05) -> Any:
        u0 = np.array(self.project(scene, cell))
        ux = np.array(self.project(scene, (cell[0] + h, cell[1])))
        uy = np.array(self.project(scene, (cell[0], cell[1] + h)))
        return np.stack([(ux - u0) / h, (uy - u0) / h], axis=1)  # columns: d/dx, d/dy


class World:
    """The Timeline of one session + the cheap per-frame questions (still, units on screen)."""

    def __init__(self, s: Session) -> None:
        from poring_dataset import mapcache
        from poring_dataset.labels_v2 import self_dead_spans
        from poring_dataset.timeline import Timeline

        gen = ROOT / "packages/poring_dataset/src/poring_dataset/_generated"
        if not (gen / "map_cache.import.dat").exists():
            gen = MAIN / "packages/poring_dataset/src/poring_dataset/_generated"
        self.tl = Timeline(s.events, mapcache.load(gen, prere=True))
        fw = self.tl.frame_world(int(s.events[-1]["t_mono_ns"]))
        self.aid = fw.aid
        self.dead = self_dead_spans(s.events, self.aid)

    def steps(self, t_f: int) -> list[Any]:
        n = int(round(STILL_S / STEP_S))
        return [self.tl.frame_world(t_f - int((n - i) * STEP_S * NS)) for i in range(n + 1)]

    @staticmethod
    def still(fws: Sequence[Any]) -> bool:
        p = fws[-1].self_pos
        if p is None:
            return False
        return all(
            f.self_pos is not None
            and abs(f.self_pos[0] - p[0]) <= 0.01
            and abs(f.self_pos[1] - p[1]) <= 0.01
            for f in fws
        )

    def is_dead(self, t: int) -> bool:
        return any(a <= t < b for a, b in self.dead)

    def units(self, fws: Sequence[Any], geo: Geo) -> int:
        """Units (any entity but our own) whose ground anchor projects inside REACH at any step."""
        seen: set[int] = set()
        for fw in fws:
            if fw.self_pos is None:
                continue
            sc = geo.scene(fw.self_pos)
            for e in fw.entities:
                if e.gid == self.aid or e.gid in seen:
                    continue
                u, v = geo.project(sc, (e.x, e.y))
                if in_reach(u, v):
                    seen.add(e.gid)
        return len(seen)


def ui_rects() -> list[Rect]:
    import client_layout

    return [tuple(map(float, r)) for r in client_layout.RECTS["hunt"]]  # type: ignore[misc]


class Layout:
    def __init__(self) -> None:
        import client_layout

        root = client_layout.TEMPLATES
        if not root.exists():
            root = MAIN / "data/ui_anchors/layout"
        self.tm = client_layout.load_templates(root)

    def ok(self, rgb: Any, sid: str) -> bool:
        """The recorded frame shows the hunting layout (its chat window: chat_window.for_sid)."""
        import chat_window
        import client_layout

        state = client_layout.read(rgb, self.tm, chat=chat_window.for_sid(sid))
        return bool(client_layout.matches(state, "hunt"))


# --- templates and NCC ---------------------------------------------------------------------------


def best_ncc(img: Any, tpl: Any, centre: tuple[float, float], r: int) -> dict[str, Any] | None:
    """The masked colour NCC of ``tpl`` (item_icons.IconTemplate) with its centre within +-r px of
    ``centre``: the best value at radius 1, R_FIT, r and their offsets; None when the window leaves
    the image."""
    import item_icons

    h, w = tpl.size
    x_tl = int(round(centre[0] - (w - 1) / 2))
    y_tl = int(round(centre[1] - (h - 1) / 2))
    H, W = img.shape[:2]
    y0, x0 = y_tl - r, x_tl - r
    if y0 < 0 or x0 < 0 or y0 + h + 2 * r > H or x0 + w + 2 * r > W:
        return None
    region = img[y0 : y0 + h + 2 * r, x0 : x0 + w + 2 * r]
    ncc = item_icons.match_maps(region, [tpl])[0][0][: 2 * r + 1, : 2 * r + 1]
    ncc = np.where(np.isfinite(ncc), ncc, -1.0)
    out: dict[str, Any] = {"snap": (x_tl + (w - 1) / 2 - centre[0], y_tl + (h - 1) / 2 - centre[1])}
    for name, rr in (("r1", min(R_G1, r)), ("fit", min(R_FIT, r)), ("full", r)):
        sub = ncc[r - rr : r + rr + 1, r - rr : r + rr + 1]
        iy, ix = np.unravel_index(int(np.argmax(sub)), sub.shape)
        out[name] = {
            "ncc": float(sub[iy, ix]),
            "dx": int(ix) - rr,
            "dy": int(iy) - rr,
            "edge": abs(int(ix) - rr) == rr or abs(int(iy) - rr) == rr,
        }
    return out


def save_tpls(tpls: Mapping[int, Any], path: Path) -> None:
    arrs = {}
    for it, t in tpls.items():
        arrs[f"rgb_{it}"] = np.asarray(t.rgb, np.float32)
        arrs[f"mask_{it}"] = np.asarray(t.mask, bool)
    with open(path, "wb") as fh:
        np.savez_compressed(fh, **arrs)


def load_tpls(path: Path) -> dict[int, Any]:
    import item_icons

    z = np.load(path)
    out = {}
    for k in z.files:
        if k.startswith("rgb_"):
            it = int(k[4:])
            out[it] = item_icons.IconTemplate(it, z[k], z[f"mask_{it}"])
    return out


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# --- MEASURE (FIT data only) ---------------------------------------------------------------------


@dataclass
class Clean:
    """One clean template sample: a still frame, a settled item clear of everything."""

    sid: str
    frame: Path
    t_f: int
    fl: Floor
    gm: tuple[float, float]
    q: tuple[float, float]  # the H12 projection
    J: Any
    crop: Any = None
    empty_uv: tuple[float, float] | None = None  # an empty-floor point on the same frame


def _alive(items: Sequence[Floor], t: int) -> list[Floor]:
    return [f for f in items if f.t_a <= t < f.t_v]


def collect_clean(s: Session, geo: Geo, rng: random.Random) -> list[Clean]:
    """Section 4.1's samples (and one empty-floor point per sample for 4.4), every 0.4 s of the
    session's GM-still frames."""
    import drop_blobs as db

    from poring_dataset.labels_v2 import self_label

    world = World(s)
    items = floor_items(s.events)
    mc = first_map_change(s.events)
    rects = ui_rects()
    out: list[Clean] = []
    per: Counter[int] = Counter()
    last_t: dict[int, int] = {}
    last = -10 * NS
    for _k, t_f, path in s.frames:
        if t_f - last < MEASURE_EVERY_S * NS or not in_block(s, t_f):
            continue
        if mc is None or t_f < mc or world.is_dead(t_f):
            continue
        fws = world.steps(t_f)
        if not World.still(fws):
            continue
        last = t_f
        gm = fws[-1].self_pos
        sc = geo.scene(gm)
        alive = _alive(items, t_f)
        pts = {f.floor_id: geo.project(sc, item_cell(f, H12, H12)) for f in alive}
        units = [(e.x, e.y) for e in fws[-1].entities if e.gid != world.aid]
        sl = self_label(fws[-1], sc)
        sbox = sl.box if sl is not None else None
        picked = []
        for f in alive:
            age = (t_f - f.t_a) / NS
            if age < TPL_MIN_AGE_S or (f.vanished and (f.t_v - t_f) / NS < TPL_BEFORE_VANISH_S):
                continue
            if per[f.floor_id] >= PER_INSTANCE or t_f - last_t.get(f.floor_id, -10 * NS) < (
                INSTANCE_GAP_S * NS
            ):
                continue
            u, v = pts[f.floor_id]
            if not (
                REGION_MARGIN_PX <= u <= 1280 - REGION_MARGIN_PX
                and REGION_MARGIN_PX <= v <= 720 - REGION_MARGIN_PX
            ):
                continue
            if any(
                r[0] - UI_MARGIN_PX <= u <= r[2] + UI_MARGIN_PX
                and r[1] - UI_MARGIN_PX <= v <= r[3] + UI_MARGIN_PX
                for r in rects
            ):
                continue
            if sbox is not None and (
                sbox[0] - SELF_MARGIN_PX <= u <= sbox[2] + SELF_MARGIN_PX
                and sbox[1] - SELF_MARGIN_PX <= v <= sbox[3] + SELF_MARGIN_PX
            ):
                continue
            if any(
                g.floor_id != f.floor_id
                and math.hypot(pts[g.floor_id][0] - u, pts[g.floor_id][1] - v) <= ITEM_GAP_PX
                for g in alive
            ):
                continue
            c = item_cell(f, H12, H12)
            if any(max(abs(x - c[0]), abs(y - c[1])) <= UNIT_NEAR_CELLS for x, y in units):
                continue
            picked.append(f)
        if not picked:
            continue
        img = read_rgb(path)
        for f in picked:
            q = pts[f.floor_id]
            crop, _, _ = db._crop(img, q[0], q[1], 44)
            cl = Clean(
                s.sid,
                path,
                t_f,
                f,
                gm,
                q,
                geo.jacobian(sc, item_cell(f, H12, H12)),
                np.ascontiguousarray(crop),
            )
            cl.empty_uv = empty_point(sc, geo, gm, alive, units, sbox, rects, rng)
            out.append(cl)
            per[f.floor_id] += 1
            last_t[f.floor_id] = t_f
    return out


def empty_point(
    sc: Any,
    geo: Geo,
    gm: tuple[float, float],
    alive: Sequence[Floor],
    units: Sequence[tuple[float, float]],
    sbox: Rect | None,
    rects: Sequence[Rect],
    rng: random.Random,
    tries: int = 200,
) -> tuple[float, float] | None:
    """A projected ground point with no floor item within EMPTY_ITEM_CELLS, no unit within
    EMPTY_UNIT_CELLS, clear of our box and the UI, inside the region (random cell + a random
    rAthena sub-cell under H12)."""
    for _ in range(tries):
        cx = int(round(gm[0])) + rng.randint(-12, 12)
        cy = int(round(gm[1])) + rng.randint(-10, 10)
        c = (cx + H12[rng.choice(SUBS)], cy + H12[rng.choice(SUBS)])
        if any(max(abs(f.x - cx), abs(f.y - cy)) <= EMPTY_ITEM_CELLS for f in alive):
            continue
        if any(max(abs(x - c[0]), abs(y - c[1])) <= EMPTY_UNIT_CELLS for x, y in units):
            continue
        u, v = geo.project(sc, c)
        if not (
            REGION_MARGIN_PX <= u <= 1280 - REGION_MARGIN_PX
            and REGION_MARGIN_PX <= v <= 720 - REGION_MARGIN_PX
        ):
            continue
        if any(
            r[0] - UI_MARGIN_PX <= u <= r[2] + UI_MARGIN_PX
            and r[1] - UI_MARGIN_PX <= v <= r[3] + UI_MARGIN_PX
            for r in rects
        ):
            continue
        if sbox is not None and (
            sbox[0] - SELF_MARGIN_PX <= u <= sbox[2] + SELF_MARGIN_PX
            and sbox[1] - SELF_MARGIN_PX <= v <= sbox[3] + SELF_MARGIN_PX
        ):
            continue
        return u, v
    return None


def build_templates(clean: Sequence[Clean]) -> dict[int, Any]:
    import item_icons

    by: dict[int, list[Any]] = {}
    for c in clean:
        by.setdefault(c.fl.item_id, []).append(
            item_icons.Sample(c.fl.floor_id, c.fl.item_id, c.frame.name, c.t_f, c.q, True, c.crop)
        )
    out = {}
    for it, samples in sorted(by.items()):
        tpl = item_icons.build_template(samples)
        if tpl is not None:
            out[it] = tpl
    return out


def by_frame(clean: Sequence[Clean]) -> dict[Path, list[Clean]]:
    out: dict[Path, list[Clean]] = {}
    for c in clean:
        out.setdefault(c.frame, []).append(c)
    return out


def measure_rows(clean: Sequence[Clean], tpls: Mapping[int, Any]) -> list[dict[str, Any]]:
    """Per clean sample with a template: the best-NCC sprite centre within +-SUB_SEARCH_PX of the
    H12 prediction (+ the template's build anchor), its residual vs the H12 projection. Each
    frame is read once (nothing cached)."""
    rows = []
    for path, cs in by_frame(clean).items():
        cs = [c for c in cs if c.fl.item_id in tpls]
        if not cs:
            continue
        img = read_rgb(path)
        for c in cs:
            tpl = tpls[c.fl.item_id]
            # build_template's anchor is relative to the crop centre = the rounded projection
            pred = (round(c.q[0]) + tpl.anchor[0], round(c.q[1]) + tpl.anchor[1])
            m = best_ncc(img, tpl, pred, SUB_SEARCH_PX)
            if m is None or m["full"]["edge"]:
                continue
            cu = pred[0] + m["snap"][0] + m["full"]["dx"]
            cv = pred[1] + m["snap"][1] + m["full"]["dy"]
            rows.append(
                {
                    "r": (cu - c.q[0], cv - c.q[1]),
                    "J": c.J.tolist(),
                    "sx": c.fl.sub_x,
                    "sy": c.fl.sub_y,
                    "item": c.fl.item_id,
                    "ncc": m["full"]["ncc"],
                    "centre": (cu, cv),
                    "c": c,
                }
            )
    return rows


def anchors_from(
    rows: Sequence[Mapping[str, Any]], geo: Geo, ox: Mapping[int, float], oy: Mapping[int, float]
) -> dict[int, tuple[float, float]]:
    by: dict[int, list[tuple[float, float]]] = {}
    for r in rows:
        c = r["c"]
        sc = geo.scene(c.gm)
        u, v = geo.project(sc, item_cell(c.fl, ox, oy))
        by.setdefault(int(r["item"]), []).append((r["centre"][0] - u, r["centre"][1] - v))
    return {
        it: (
            round(float(np.median([p[0] for p in ps])), 3),
            round(float(np.median([p[1] for p in ps])), 3),
        )
        for it, ps in by.items()
    }


def predicted_centre(
    geo: Geo, sc: Any, f: Floor, p: Mapping[str, Any], anchors: Mapping[int, Any]
) -> tuple[float, float]:
    u, v = geo.project(sc, item_cell(f, p["ox"], p["oy"]))
    a = anchors[f.item_id]
    return u + float(a[0]), v + float(a[1])


def table_of(p: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "ox": {int(k): float(v) for k, v in p["ox"].items()},
        "oy": {int(k): float(v) for k, v in p["oy"].items()},
    }


def delay_rows(
    s: Session,
    geo: Geo,
    p: Mapping[str, Any],
    tpls: Mapping[int, Any],
    anchors: Mapping[int, Any],
    tau: float,
) -> dict[str, list[tuple[float, bool]]]:
    """Section 4.5 / 4.6: (age, present) of fresh drops after their appear and of items after
    their vanish, on GM-still frames, clear of our box and of other items."""
    from poring_dataset.labels_v2 import self_label

    world = World(s)
    items = floor_items(s.events)
    mc = first_map_change(s.events)
    tab = table_of(p)
    out: dict[str, list[tuple[float, bool]]] = {"appear": [], "gone": []}
    ts = [t for _k, t, _p in s.frames]
    for f in items:
        if f.item_id not in tpls or f.item_id not in anchors:
            continue
        windows = []
        if f.kind == "fall":
            windows.append(("appear", f.t_a, DELAY_MAX_S))
        if f.vanished:
            windows.append(("gone", f.t_v, GONE_MAX_S))
        for kind, t0, span in windows:
            i = bisect.bisect_left(ts, t0)
            while i < len(ts) and ts[i] < t0 + span * NS:
                _k, t_f, path = s.frames[i]
                i += 1
                if not in_block(s, t_f) or mc is None or t_f < mc or world.is_dead(t_f):
                    continue
                fws = world.steps(t_f)
                if not World.still(fws):
                    continue
                sc = geo.scene(fws[-1].self_pos)
                c = predicted_centre(geo, sc, f, tab, anchors)
                tpl = tpls[f.item_id]
                box = tpl_box(c, tpl.size)
                sl = self_label(fws[-1], sc)
                if sl is not None and inter(box, sl.box) > 0:
                    continue
                others = [g for g in items if g.floor_id != f.floor_id and g.t_a <= t_f < g.t_v]
                if any(
                    math.hypot(*(np.subtract(predicted_centre(geo, sc, g, tab, anchors), c)))
                    <= ITEM_GAP_PX
                    for g in others
                    if g.item_id in anchors
                ):
                    continue
                if ui_status(box, ui_rects(), (1280, 720)) != "clear":
                    continue
                m = best_ncc(read_rgb(path), tpl, c, R_DELAY)
                if m is None:
                    continue
                out[kind].append(((t_f - t0) / NS, m["full"]["ncc"] >= tau))
    return out


def cmd_measure(a: argparse.Namespace) -> int:
    out = OUT / "params"
    out.mkdir(parents=True, exist_ok=True)
    rng = random.Random(20261023)
    m = a.map
    blocks = SPLIT[m].get("blocks", {})
    sessions = [load_session(sid, blocks.get("fit")) for sid in split_of(m, "fit")]
    geo = Geo(m)
    t0 = time.time()
    clean: list[Clean] = []
    for s in sessions:
        cs = collect_clean(s, geo, rng)
        print(
            f"{s.sid}: {len(cs)} clean samples, {len({c.fl.floor_id for c in cs})} floor "
            f"items ({time.time() - t0:.0f} s)",
            flush=True,
        )
        clean += cs
    tpls = build_templates(clean)
    print(f"templates: {sorted(tpls)}", flush=True)
    rows = measure_rows(clean, tpls)
    res: dict[str, Any] = {
        "map": m,
        "fit": [s.sid for s in sessions],
        "clean": len(clean),
        "templates": {
            str(it): {
                "size_hw": list(t.size),
                "mask_px": int(np.asarray(t.mask).sum()),
                "samples": t.samples,
                "instances": t.instances,
            }
            for it, t in tpls.items()
        },
    }
    if a.table:
        tab0 = json.loads(Path(a.table).read_text())["subtable"]
        res["subtable"] = {"from": a.table, "ox": tab0["ox"], "oy": tab0["oy"]}
    else:
        st = solve_subtable(rows)
        # alternatives' residuals (reported): the same solve with the table forced to H12 / H16
        res["subtable"] = st
        for name, hyp in (("h12", H12), ("h16", H16)):
            res[f"anchor_resid_{name}_px"] = _hyp_residual(rows, geo, hyp)
        res["anchor_resid_measured_px"] = _hyp_residual(
            rows,
            geo,
            {int(k): v for k, v in st["ox"].items()},
            {int(k): v for k, v in st["oy"].items()},
        )
    tab = table_of(res["subtable"])
    anchors = anchors_from(rows, geo, tab["ox"], tab["oy"])
    res["anchors_px"] = {str(k): v for k, v in anchors.items()}
    # tau: present = clean samples at the predicted centre, absent = their empty-floor points
    present, absent = [], []
    for path, cs in by_frame(clean).items():
        cs = [c for c in cs if c.fl.item_id in tpls and c.fl.item_id in anchors]
        if not cs:
            continue
        img = read_rgb(path)
        for c in cs:
            tpl = tpls[c.fl.item_id]
            pc = predicted_centre(geo, geo.scene(c.gm), c.fl, tab, anchors)
            mm = best_ncc(img, tpl, pc, R_FIT)
            if mm is not None:
                present.append(mm["fit"]["ncc"])
            if c.empty_uv is not None:
                a_ = anchors[c.fl.item_id]
                me = best_ncc(img, tpl, (c.empty_uv[0] + a_[0], c.empty_uv[1] + a_[1]), R_FIT)
                if me is not None:
                    absent.append(me["fit"]["ncc"])
    tau = youden(present, absent)
    res["tau"] = round(tau, 4)
    res["tau_n"] = {
        "present": len(present),
        "absent": len(absent),
        "tpr": round(float(np.mean(np.asarray(present) >= tau)), 4),
        "fpr": round(float(np.mean(np.asarray(absent) >= tau)), 4),
    }
    # delays
    ages: dict[str, list[tuple[float, bool]]] = {"appear": [], "gone": []}
    for s in sessions:
        d = delay_rows(s, geo, res["subtable"], tpls, anchors, tau)
        for k in ages:
            ages[k] += d[k]
    ab = bin_shares(
        [x for x, _ in ages["appear"]], [p for _, p in ages["appear"]], 0.0, DELAY_MAX_S
    )
    pl = [p for x, p in ages["appear"] if PLATEAU[0] <= x < PLATEAU[1]]
    plateau = float(np.mean(pl)) if pl else float("nan")
    gb = bin_shares([x for x, _ in ages["gone"]], [p for _, p in ages["gone"]], 0.0, GONE_MAX_S)
    d_app = appear_delay(ab, plateau)
    n_gone = sum(b[1] for b in gb)
    d_gone = gone_delay(gb) if n_gone >= GONE_MIN_FRAMES else None
    res["delays"] = {
        "appear_bins": ab,
        "plateau": round(plateau, 4),
        "D_APPEAR_s": d_app,
        "gone_bins": gb,
        "gone_frames": n_gone,
        "D_GONE_s": d_gone if d_gone is not None else GONE_FALLBACK_S,
        "D_GONE_from": "measured" if d_gone is not None else "fallback",
    }
    save_tpls(tpls, out / f"templates_{m}.npz")
    (out / f"measure_{m}.json").write_text(json.dumps(res, indent=1, default=str))
    print(
        json.dumps({k: v for k, v in res.items() if k not in ("delays",)}, indent=1, default=str)[
            :6000
        ]
    )
    print(
        json.dumps(
            {
                "D_APPEAR_s": d_app,
                "plateau": plateau,
                "D_GONE": res["delays"]["D_GONE_s"],
                "gone_from": res["delays"]["D_GONE_from"],
                "gone_frames": n_gone,
            }
        )
    )
    return 0


def _hyp_residual(
    rows: Sequence[Mapping[str, Any]],
    geo: Geo,
    ox: Mapping[int, float],
    oy: Mapping[int, float] | None = None,
) -> float:
    """The median residual (px) of the sprite centres after per-item median anchors, under a
    sub-cell table (reported: H12, H16, the measured one)."""
    oy = ox if oy is None else oy
    anchors = anchors_from(rows, geo, ox, oy)
    res = []
    for r in rows:
        c = r["c"]
        u, v = geo.project(geo.scene(c.gm), item_cell(c.fl, ox, oy))
        a = anchors[int(r["item"])]
        res.append(math.hypot(r["centre"][0] - u - a[0], r["centre"][1] - v - a[1]))
    return round(float(np.median(res)), 3) if res else float("nan")


# --- FREEZE --------------------------------------------------------------------------------------


def cmd_freeze(_a: argparse.Namespace) -> int:
    pdir = OUT / "params"
    ms = {m: json.loads((pdir / f"measure_{m}.json").read_text()) for m in SPLIT}
    pr = ms["prt_fild08"]
    params = {
        "pre_registration": "docs/planning/item-class.md a46893d, amendments A 19201ea, B 62454f8",
        "constants": {
            k: globals()[k]
            for k in (
                "STILL_S",
                "STEP_S",
                "PAD",
                "R_FIT",
                "R_G1",
                "R_G2",
                "STACK_IOU",
                "REACH",
                "EVERY",
                "NEG_EVERY",
                "BLIND_ITEMS",
                "BLIND_NEG",
                "PER_FLOOR_ITEM",
            )
        },
        "subtable": {"ox": pr["subtable"]["ox"], "oy": pr["subtable"]["oy"]},
        # amendment B (62454f8): section 4.5's rule returned no value -> the plateau's 2.0 s +
        # the 0.2 s margin
        "D_APPEAR_s": (
            pr["delays"]["D_APPEAR_s"]
            if pr["delays"]["D_APPEAR_s"] is not None
            else PLATEAU[0] + DELAY_MARGIN_S
        ),
        "D_APPEAR_from": "measured" if pr["delays"]["D_APPEAR_s"] is not None else "amendment B",
        "D_GONE_s": pr["delays"]["D_GONE_s"],
        "maps": {
            m: {
                "tau": ms[m]["tau"],
                "anchors_px": ms[m]["anchors_px"],
                "templates": ms[m]["templates"],
                "templates_sha256": sha256(pdir / f"templates_{m}.npz"),
            }
            for m in SPLIT
        },
        "frozen_at": time.strftime("%Y-%m-%d %H:%M:%S %z"),
    }
    if params["D_APPEAR_s"] is None:
        raise SystemExit("D_APPEAR could not be measured: no freeze (report it)")
    path = pdir / "params.json"
    path.write_text(json.dumps(params, indent=1, default=str))
    print(
        json.dumps(
            {
                "params": str(path),
                "sha256": sha256(path),
                **{f"templates_{m}": params["maps"][m]["templates_sha256"] for m in SPLIT},
                "frozen_at": params["frozen_at"],
            },
            indent=1,
        )
    )
    return 0


def load_params(check_sha: str | None = None) -> dict[str, Any]:
    path = OUT / "params" / "params.json"
    if check_sha and sha256(path) != check_sha:
        raise SystemExit(f"{path}: sha256 differs from the frozen one")
    p = json.loads(path.read_text())
    p["table"] = table_of(p["subtable"])
    return p


# --- LABEL ---------------------------------------------------------------------------------------


@dataclass
class FrameRec:
    sid: str
    frame: str
    k: int
    t_ns: int
    status: str  # keep | exclude | skip (not sampled / out of block)
    reasons: list[str] = field(default_factory=list)
    route_u: bool = False
    units: int = 0
    items: list[dict[str, Any]] = field(default_factory=list)
    self_box: list[float] | None = None


def label_frame(
    s: Session,
    world: World,
    geo: Geo,
    p: Mapping[str, Any],
    tpls: Mapping[int, Any],
    items: Sequence[Floor],
    mc: int | None,
    k: int,
    t_f: int,
    path: Path,
    layout: Layout | None,
    rects: Sequence[Rect],
    g1: list[dict[str, Any]],
    want_neg: bool,
) -> FrameRec | None:
    """One frame by section 3 (None: not a candidate at all -- an item-less frame that is not a
    Route-U negative sample)."""
    from poring_dataset.labels_v2 import self_label

    m = s.map
    mp = p["maps"][m]
    d_app = int(round(float(p["D_APPEAR_s"]) * NS))
    d_gone = int(round(float(p["D_GONE_s"]) * NS))
    rec = FrameRec(s.sid, path.name, k, t_f, "exclude")
    if mc is None or t_f < mc:
        rec.reasons.append("item_truth_unknown")
        return rec
    phases = [(f, phase(f, t_f, d_app, d_gone)) for f in items if f.t_a <= t_f < f.t_v + d_gone]
    on = [f for f, ph in phases if ph == "on"]
    if any(ph == "settling" for _f, ph in phases):
        rec.reasons.append("item_settling")
    if any(ph == "vanishing" for _f, ph in phases):
        rec.reasons.append("item_vanishing")
    fws = world.steps(t_f)
    if not World.still(fws):
        rec.reasons.append("self_moving")
        return rec
    if world.is_dead(t_f):
        rec.reasons.append("self_dead")
        return rec
    sc = geo.scene(fws[-1].self_pos)
    sl = self_label(fws[-1], sc)
    rec.self_box = list(sl.box) if sl is not None else None
    rec.units = world.units(fws, geo)
    rec.route_u = rec.units == 0
    vis: list[tuple[Floor, tuple[float, float], Rect]] = []
    for f in on:
        if f.item_id not in tpls or str(f.item_id) not in mp["anchors_px"]:
            # untemplated: excluded only when it would be drawn (on the region, off the UI)
            u, v = geo.project(sc, item_cell(f, p["table"]["ox"], p["table"]["oy"]))
            if ui_status((u - 8, v - 8, u + 8, v + 8), rects, (1280, 720)) != "hidden":
                rec.reasons.append("item_untemplated")
            continue
        c = predicted_centre(geo, sc, f, p["table"], {f.item_id: mp["anchors_px"][str(f.item_id)]})
        box = tpl_box(c, tpls[f.item_id].size)
        st = ui_status(box, rects, (1280, 720))
        if st == "hidden":
            continue
        if st != "clear":
            rec.reasons.append(st)
            continue
        vis.append((f, c, box))
    if stacked([b for _f, _c, b in vis]):
        rec.reasons.append("stacked")
    if rec.self_box is not None and any(inter(b, tuple(rec.self_box)) > 0 for _f, _c, b in vis):  # type: ignore[arg-type]
        rec.reasons.append("under_self")
    if not vis and not (want_neg and rec.route_u and not rec.reasons):
        return rec if rec.reasons else None
    img = read_rgb(path)
    if layout is not None and not layout.ok(img, s.sid):
        rec.reasons.append("ui_layout_mismatch")
        return rec
    tau = float(mp["tau"])
    clean_before_fit = not rec.reasons
    for f, c, box in vis:
        mm = best_ncc(img, tpls[f.item_id], c, R_G2)
        if mm is None:
            rec.reasons.append("edge_partial")
            continue
        if clean_before_fit:
            g1.append(
                {
                    "sid": s.sid,
                    "frame": path.name,
                    "t_ns": t_f,
                    "floor_id": f.floor_id,
                    "item_id": f.item_id,
                    "route_u": rec.route_u,
                    "ncc_pred": round(mm["r1"]["ncc"], 4),
                    "bad": mm["r1"]["ncc"] < tau,
                    "g2_dx": mm["full"]["dx"],
                    "g2_dy": mm["full"]["dy"],
                    "g2_ncc": round(mm["full"]["ncc"], 4),
                }
            )
        fit = mm["fit"]
        unfit = fit["ncc"] < tau or fit["edge"]
        dx, dy = fit["dx"] + mm["snap"][0], fit["dy"] + mm["snap"][1]
        lab = {
            "floor_id": f.floor_id,
            "item_id": f.item_id,
            "kind": f.kind,
            "box": [
                round(box[0] + dx, 2),
                round(box[1] + dy, 2),
                round(box[2] + dx, 2),
                round(box[3] + dy, 2),
            ],
            "pred_box": [round(x, 2) for x in box],
            "ncc": round(fit["ncc"], 4),
            "dx": fit["dx"],
            "dy": fit["dy"],
            "unfit": unfit,
            "age_s": round((t_f - f.t_a) / NS, 2),
        }
        rec.items.append(lab)
        if unfit:
            rec.reasons.append("unfit")
    rec.reasons = list(dict.fromkeys(rec.reasons))
    rec.status = "keep" if not rec.reasons else "exclude"
    return rec


def cmd_label(a: argparse.Namespace) -> int:
    p = load_params(a.params_sha)
    m = a.map
    tpls = load_tpls(OUT / "params" / f"templates_{m}.npz")
    if sha256(OUT / "params" / f"templates_{m}.npz") != p["maps"][m]["templates_sha256"]:
        raise SystemExit("templates differ from the frozen params")
    blocks = SPLIT[m].get("blocks", {})
    geo = Geo(m)
    layout = Layout()
    rects = ui_rects()
    odir = OUT / "labels" / m / a.split
    odir.mkdir(parents=True, exist_ok=True)
    for sid in split_of(m, a.split):
        t0 = time.time()
        s = load_session(sid, blocks.get(a.split))
        world = World(s)
        items = floor_items(s.events)
        mc = first_map_change(s.events)
        g1: list[dict[str, Any]] = []
        recs = []
        reasons: Counter[str] = Counter()
        for k, t_f, path in s.frames:
            if k % EVERY or not in_block(s, t_f):
                continue
            r = label_frame(
                s,
                world,
                geo,
                p,
                tpls,
                items,
                mc,
                k,
                t_f,
                path,
                layout,
                rects,
                g1,
                want_neg=(k % NEG_EVERY == 0),
            )
            if r is None:
                continue
            recs.append(r)
            for x in r.reasons:
                reasons[x] += 1
        with open(odir / f"{sid}.jsonl", "w") as fh:
            for r in recs:
                fh.write(json.dumps(r.__dict__) + "\n")
        with open(odir / f"{sid}.g1.jsonl", "w") as fh:
            for g in g1:
                fh.write(json.dumps(g) + "\n")
        keep = [r for r in recs if r.status == "keep"]
        summ = {
            "sid": sid,
            "split": a.split,
            "frames_considered": len(recs),
            "kept": len(keep),
            "kept_route_u": sum(r.route_u for r in keep),
            "kept_route_u_with_items": sum(1 for r in keep if r.route_u and r.items),
            "item_labels_kept": sum(len(r.items) for r in keep),
            "item_labels_kept_route_u": sum(len(r.items) for r in keep if r.route_u),
            "floor_items_kept_route_u": len(
                {i["floor_id"] for r in keep if r.route_u for i in r.items}
            ),
            "exclusions": dict(reasons.most_common()),
            "g1_rows": len(g1),
            "g1_bad": sum(g["bad"] for g in g1),
            "seconds": round(time.time() - t0),
        }
        (odir / f"{sid}.summary.json").write_text(json.dumps(summ, indent=1))
        print(json.dumps(summ), flush=True)
    return 0


# --- CHECK (G1 / G2) -----------------------------------------------------------------------------


def g1_summary(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """PURE: G1 pooled (bad / scored), per item id; G2 median |dx|, |dy|."""
    n = len(rows)
    bad = sum(bool(r["bad"]) for r in rows)
    per: dict[str, list[int]] = {}
    for r in rows:
        per.setdefault(str(r["item_id"]), [0, 0])
        per[str(r["item_id"])][0] += 1
        per[str(r["item_id"])][1] += bool(r["bad"])
    return {
        "scored": n,
        "bad": bad,
        "g1": (bad / n) if n else None,
        "g1_pass": (n >= 50 and bad / n <= 0.05) if n else False,
        "per_item": {k: {"n": v[0], "bad": v[1]} for k, v in sorted(per.items())},
        "g2_median_abs_dx": float(np.median([abs(r["g2_dx"]) for r in rows])) if n else None,
        "g2_median_abs_dy": float(np.median([abs(r["g2_dy"]) for r in rows])) if n else None,
    }


def cmd_check(a: argparse.Namespace) -> int:
    out = {}
    for split in ("train", "test"):
        d = OUT / "labels" / a.map / split
        rows = []
        for sid in split_of(a.map, split):
            f = d / f"{sid}.g1.jsonl"
            if f.exists():
                rows += [json.loads(x) for x in f.read_text().splitlines()]
        out[split] = g1_summary(rows)
        out[split]["route_u_only"] = g1_summary([r for r in rows if r["route_u"]])
    (OUT / "labels" / a.map / "check.json").write_text(json.dumps(out, indent=1))
    print(json.dumps(out, indent=1))
    return 0


# --- PACK (blind round 1) ------------------------------------------------------------------------


def draw_items(
    cands: Sequence[Mapping[str, Any]], n: int, seed: int, per_floor: int = PER_FLOOR_ITEM
) -> list[Mapping[str, Any]]:
    """PURE: ``n`` labels drawn by ``seed``, at most ``per_floor`` per (session, floor id); all of
    them when fewer qualify."""
    rng = random.Random(seed)
    order = list(cands)
    rng.shuffle(order)
    out, per = [], Counter()
    for c in order:
        key = (c["sid"], c["floor_id"])
        if per[key] >= per_floor:
            continue
        per[key] += 1
        out.append(c)
        if len(out) >= n:
            break
    return out


def crop_pair(img: Any, box: Sequence[float]) -> Any:
    """The crop around the box centre, enlarged, plain | boxed (cyan, 1 source px)."""
    import drop_blobs as db

    cu, cv = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
    crop, x0, y0 = db._crop(img, cu, cv, CROP_HALF)
    a = np.repeat(np.repeat(crop, CROP_SCALE, 0), CROP_SCALE, 1).copy()
    b = a.copy()
    s = CROP_SCALE
    bx0, by0 = int(round((box[0] - x0) * s)), int(round((box[1] - y0) * s))
    bx1, by1 = int(round((box[2] - x0) * s)) - 1, int(round((box[3] - y0) * s)) - 1
    h, w = b.shape[:2]
    bx0, by0, bx1, by1 = max(bx0, 0), max(by0, 0), min(bx1, w - 1), min(by1, h - 1)
    cyan = np.array([0, 255, 255], np.uint8)
    t = s - 1  # one SOURCE pixel thick, on the box's own boundary pixels (the PAD ring)
    b[by0 : by0 + t + 1, bx0 : bx1 + 1] = cyan
    b[max(by1 - t, 0) : by1 + 1, bx0 : bx1 + 1] = cyan
    b[by0 : by1 + 1, bx0 : bx0 + t + 1] = cyan
    b[by0 : by1 + 1, max(bx1 - t, 0) : bx1 + 1] = cyan
    gap = np.full((h, 8, 3), 255, np.uint8)
    return np.concatenate([a, gap, b], axis=1)


def cmd_pack(a: argparse.Namespace) -> int:
    from PIL import Image

    p = load_params(a.params_sha)
    root = OUT / f"blind-pack-seed{a.seed}"
    keyd = OUT / f"answer-key-seed{a.seed}"
    root.mkdir(parents=True, exist_ok=True)
    keyd.mkdir(parents=True, exist_ok=True)
    rng = random.Random(a.seed)
    entries: list[dict[str, Any]] = []
    for m in SPLIT:
        cands, negframes = [], []
        sizes = [tuple(v["size_hw"]) for v in p["maps"][m]["templates"].values()]
        med_h = float(np.median([s[0] for s in sizes])) if sizes else 16.0
        med_w = float(np.median([s[1] for s in sizes])) if sizes else 16.0
        for sid in split_of(m, a.split):
            f = OUT / "labels" / m / a.split / f"{sid}.jsonl"
            for line in f.read_text().splitlines():
                r = json.loads(line)
                if r["status"] != "keep" or not r["route_u"]:
                    continue
                if r["items"]:
                    for it in r["items"]:
                        cands.append({"sid": sid, "frame": r["frame"], "t_ns": r["t_ns"], **it})
                else:
                    negframes.append(
                        {
                            "sid": sid,
                            "frame": r["frame"],
                            "t_ns": r["t_ns"],
                            "self_box": r["self_box"],
                        }
                    )
        picks = draw_items(cands, BLIND_ITEMS, a.seed)
        negs = negative_points(m, negframes, BLIND_NEG, a.seed, (med_h, med_w), p)
        for x in picks:
            entries.append({"map": m, "truth": "item", **x})
        for x in negs:
            entries.append({"map": m, "truth": "none", **x})
        print(
            f"{m}: {len(cands)} kept Route-U item labels -> {len(picks)} crops; "
            f"{len(negframes)} item-less Route-U frames -> {len(negs)} negatives",
            flush=True,
        )
    rng.shuffle(entries)
    key: dict[str, Any] = {"seed": a.seed, "split": a.split, "crops": {}}
    fdirs = {}
    for i, e in enumerate(entries, 1):
        cid = f"{i:03d}"
        sid = e["sid"]
        if sid not in fdirs:
            fdirs[sid] = Path(
                json.loads((DATASETS / sid / "manifest.json").read_text())["frames_dir"]
            )
        img = read_rgb(fdirs[sid] / e["frame"])
        Image.fromarray(crop_pair(img, e["box"])).save(root / f"crop-{cid}.png")
        key["crops"][cid] = {k: v for k, v in e.items() if k not in ("pred_box",)}
    (root / "instructions.txt").write_text(INSTRUCTIONS)
    (keyd / "answer_key.json").write_text(json.dumps(key, indent=1))
    per_map = Counter(f"{e['map']}:{e['truth']}" for e in entries)
    print(
        json.dumps(
            {
                "pack": str(root),
                "key": str(keyd / "answer_key.json"),
                "crops": len(entries),
                "per_map": dict(per_map),
            },
            indent=1,
        )
    )
    return 0


def negative_points(
    m: str,
    frames: Sequence[Mapping[str, Any]],
    n: int,
    seed: int,
    hw: tuple[float, float],
    p: Mapping[str, Any],
) -> list[dict[str, Any]]:
    """Empty-floor crops (section 5, amendment A 1): kept item-less Route-U frames of the TRAIN
    data; a projected point with no floor item within 3 cells, no unit within 2, clear of our
    box and the UI; the box = the map's median item box."""
    rng = random.Random(seed * 1000 + 7)
    order = list(frames)
    rng.shuffle(order)
    geo = Geo(m)
    rects = ui_rects()
    out: list[dict[str, Any]] = []
    cache: dict[str, tuple[Session, World, list[Floor]]] = {}
    for fr in order:
        if len(out) >= n:
            break
        sid = fr["sid"]
        if sid not in cache:
            s = load_session(sid, SPLIT[m].get("blocks", {}).get("train"))
            cache[sid] = (s, World(s), floor_items(s.events))
        s, world, items = cache[sid]
        fw = world.tl.frame_world(int(fr["t_ns"]))
        if fw.self_pos is None:
            continue
        sc = geo.scene(fw.self_pos)
        alive = [f for f in items if f.t_a <= int(fr["t_ns"]) < f.t_v]
        units = [(e.x, e.y) for e in fw.entities if e.gid != world.aid]
        sb = tuple(fr["self_box"]) if fr.get("self_box") else None
        pt = empty_point(sc, geo, fw.self_pos, alive, units, sb, rects, rng)  # type: ignore[arg-type]
        if pt is None:
            continue
        box = tpl_box(pt, (int(round(hw[0])), int(round(hw[1]))))
        out.append(
            {
                "sid": sid,
                "frame": fr["frame"],
                "t_ns": fr["t_ns"],
                "floor_id": None,
                "item_id": None,
                "box": [round(x, 2) for x in box],
            }
        )
    return out


INSTRUCTIONS = """You are a blind labeller. Each numbered image is a crop of a game screenshot (a
third-person view looking down at the ground), enlarged 3x. Each image shows the
SAME crop twice, side by side: LEFT plain, RIGHT with a thin cyan rectangle drawn
on it. Use the left copy to see what is under the rectangle's lines.

For EVERY crop answer two questions about the RIGHT copy's rectangle:

q1: Is there a DROPPED ITEM inside the rectangle? A dropped item is a small loose
    object lying on the ground (loot), for example a gem, a fruit, a bottle, a
    feather, a bone, a nail, a herb, a card, a weapon. Answer "yes", "no" or
    "unsure". These are NOT dropped items: characters, monsters, monster corpses
    or splats, plants or flowers growing from the ground, rocks, shadows, the mouse
    cursor, and any user-interface element.

q2: Only if q1 is "yes": does the rectangle fit THAT item?
    "good"  = it encloses the item, with at most a few pixels of slack, and cuts
              nothing off;
    "loose" = it encloses the item but with clearly too much empty ground (on
              some side more than about half the item's own size);
    "off"   = it cuts off part of the item, or is shifted so the item is not
              inside it.
    If several items are in the rectangle, judge the most central one.
    If q1 is not "yes", answer "-".

Write your answers to the file named in your task as a JSON list, one entry per
crop, every crop answered, for example:
[{"crop": "007", "q1": "yes", "q2": "good"},
 {"crop": "008", "q1": "no", "q2": "-"}]
Judge only what you see. Do not open any other file, and do not infer anything
from file names or crop order.
"""


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = ap.add_subparsers(dest="cmd", required=True)
    m = sub.add_parser("measure")
    m.add_argument("--map", required=True, choices=sorted(SPLIT))
    m.add_argument("--table", help="the prt_fild08 measure json whose sub-cell table to reuse")
    m.set_defaults(fn=cmd_measure)
    f = sub.add_parser("freeze")
    f.set_defaults(fn=cmd_freeze)
    lab = sub.add_parser("label")
    lab.add_argument("--map", required=True, choices=sorted(SPLIT))
    lab.add_argument("--split", required=True, choices=("train", "test"))
    lab.add_argument("--params-sha", required=True)
    lab.set_defaults(fn=cmd_label)
    c = sub.add_parser("check")
    c.add_argument("--map", required=True, choices=sorted(SPLIT))
    c.set_defaults(fn=cmd_check)
    pk = sub.add_parser("pack")
    pk.add_argument("--seed", type=int, required=True)
    pk.add_argument("--split", default="train", choices=("train", "test"))
    pk.add_argument("--params-sha", required=True)
    pk.set_defaults(fn=cmd_pack)
    a = ap.parse_args(argv)
    return int(a.fn(a))


if __name__ == "__main__":
    sys.exit(main())
