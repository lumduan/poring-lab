#!/usr/bin/env python3
"""FLOOR-ITEM labels on xmas_dun02: the rule ``xmas02-fi-1`` (docs/planning/xmas02-detector.md
Amendment O, sections O.3-O.6 and O.9; ACCEPTED by O1, 2026-11-10 10:29 ICT, with O.12's
defaults: one class ``floor_item``, a SEPARATE item model ``xmas02-fi``). Tools T-O1 and T-O3.

    fi_labels.py freeze [--out PARAMS]                       O.3 (g): the frozen params file, once
    fi_labels.py freeze-v2 --v1 PARAMS --labels FIT.json DEV.json [--out PARAMS_V2]
                                                             O3: v1 + the absent rule's ids, once
    fi_labels.py label PART --split train|val --params PARAMS --out LABELS.json [--workers N]
    fi_labels.py label PART --eval-test --model WEIGHTS --model-sha256 HEX --params PARAMS
                       --out LABELS.json                      O.9: fiT only, after the model froze
    fi_labels.py g2 LABELS.json... --out JSON                O.6's join rule (G2) per session
    fi_labels.py pack LABELS.json... --params PARAMS --seed 61 --out JSON        O.5: T2-items
    fi_labels.py pack LABELS.json... --eval-test --params PARAMS --seed 63 --out JSON    O.9
    fi_labels.py refs LABELS.json... --out REFS.json         predict_dir --refs for the evaluation

THE RULE (O.3, every value fixed on FIT p31 and frozen by ``freeze``):
- (a) an item lies on the floor from its ``floor_item_appear`` to its ``floor_item_vanish`` or our
  map change (item_labels.floor_items); on a frame at capture time t it is LABELLED when t_a + 2.2 s
  <= t < t_v; the FRAME is excluded while one settles (``item_settling``) or vanishes
  (``item_vanishing``, t_v <= t < t_v + 0.6 s). Frames: the monsters' candidate frames
  (map_labels.RecSession, our character still, 1d 120 ms) whose layout is the session's
  (``ui_layout_mismatch``) -- item-free ones too (O.3 (a); the study's dry run skipped that read
  on item-free frames, so its negative count is an upper bound of this one's);
- (b) the cell (x + OX[sub_x], y + OY[sub_y]) of item-class.md 8a, projected like a monster's
  anchor (camera on our cell at tw = t - 120 ms, the GAT altitude), + the ANCHOR (-4, +2) px;
- (c) the box: the item's OWN client sprite (one frame) at scale 1.0, moved by the best masked
  COLOUR NCC (the 3 channels as one vector) within +-10 px; below T_item 0.65 or at the search
  edge: ``item_unfit``;
- (d) frame exclusions: item_settling, item_vanishing, ui_partial / edge_partial, stacked (two
  item boxes IoU >= 0.5), under_self (labels_v2's 34 x 74 self box + 4 px), under_bar (the
  FIT-measured bar (-31, +10, +28, +18) px from our anchor), under_unit (the generic unit box at tw
  and tw - 0.5 s), item_unfit, item_unsprited (an id outside the frozen sprite table; params v2,
  Amendment O3: also an id the ABSENT RULE excludes -- its sprite fits >= T_item on > 1 % of FIT +
  DEV's empty-floor absent points, so a fit cannot show it is there); and, fail closed,
  item_unprojected (a prediction that does not exist). Under a model / terrain box: kept
  only when (c) passes (o3h for items);
- (e) ONE class ``floor_item``; (f) a kept frame with no item label is a NEGATIVE.

ROLES, refused by the part's NAME before anything of it is read (O.6; map_labels.XMAS02's
test_suffixes, Amendment O1): the monster TEST (xw5, xp1, X2), gw3, the floor items' held-out
fiT1-fiT3, and p30 (the GPU video, O.0). FIT (p31) is labelled only as ``--split val`` (VAL,
monitor only); ``--split train`` refuses it, and ``--split val`` takes nothing else. ``--eval-test``
reads fiT and nothing else, under FROZEN params and only once a frozen MODEL exists (its weights
re-hashed against ``--model-sha256``; map_labels' ``--eval-test`` asks FROZEN params the same way).

G2 (O.6's join rule, gef10 round 3 4.3's form): the median |dx|, |dy| of a session's CLEAR views'
colour fits at the anchored prediction <= 3 px on >= 30 fits. A clear view: an item ON the floor
(phase on), wholly clear of the UI, >= 30 px inside the frame and from every UI window, clear of
our self box + 4 px, our bar, every unit box (tw, tw - 0.5 s), every other item on the floor and
every model / terrain box; every fit counts (the study's 184 FIT / 52 DEV fits, O.4). ``label``
records each item's ``g2_clear`` and the session's summary; ``g2`` reads label files.

T2-items (O.5): strata N (within 1 cell of our cell: the runner's case), F (2+ cells, clear of
every model box), M (2+ cells, under a model / terrain box, kept by the fit) -- a partition, N
first -- and E (10 plain absent points by O.1e's rule + 10 HARD ones: the absent points with the
highest colour fit on TRAIN frames); <= 3 crops per floor item; seed 61, salt ``xmas02-fi``; one
seeded order, the strata's sizes not in the pack. ``reference.png`` (the distinct floor sprites of
the map's drop tables, native size x3 on the floor's orange and pale tiles, no names) is generated
at pack time; the instructions are the committed file, pinned by sha256. The evaluation's pack
(O.9, ``--eval-test``, seed 63): every kept fiT label up to 60 (<= 3 a floor item) + 20 E crops.

OFFLINE ONLY (ADR-0007: packets are ground truth for labels, never an agent input): packets, the
recorder's PNG tar shards (read-only, NAS), the client's item sprites and resname table and the
map's RSW / GAT in /dev/shm (client-derived, never committed), the local KB's drop tables
(rAthena-derived, never committed). No GPU, no client, no input. Item NAMES are never written.
"""

from __future__ import annotations

import argparse
import bisect
import dataclasses
import hashlib
import json
import math
import random
import statistics
import sys
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import numpy.typing as npt

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import gef10_items as gi  # noqa: E402
import item_labels as il  # noqa: E402
import label_check  # noqa: E402
import map_labels as ml  # noqa: E402
import orc_camera_check as occ  # noqa: E402
import orc_labels_fix as olf  # noqa: E402
import qa_export  # noqa: E402

from poring_dataset.render import (  # noqa: E402
    Actor,
    SpritePrediction,
    SpriteSheet,
    anchor_and_depth,
    predict_sprite,
)
from poring_dataset.sprites import compose_frame, parse_act, parse_spr  # noqa: E402

Box = tuple[float, float, float, float]
NS = 1_000_000_000
RULE = "xmas02-fi-1"
CLASS_NAME = "floor_item"
FI = Path("/dev/shm/poring-lab-tmp/xmas-fi")  # client-derived inputs and outputs: RAM (rule 7)
NAS = Path("/mnt/poring-lab-datasets")
LAYOUT_TEMPLATES = Path.home() / "docker" / "poring-lab" / "data" / "ui_anchors" / "layout"
INSTRUCTIONS = ROOT / "docs" / "planning" / "xmas02-item-blind-instructions.txt"
INSTRUCTIONS_SHA256 = "cff8ee8b7e738c13357c680072f9ce39762b652403a86a15ef462ff50e5fcdf5"
G2_BAR_PX = 3.0  # O.6: the join rule's median |dx|, |dy|
G2_MIN_FITS = 30  # ... on >= 30 fits
MARGIN_PX = 30.0  # a clear view lies >= 30 px inside the frame and from every UI window
PACK_N = {"N": 15, "F": 15, "M": 10}  # O.5's item strata
PACK_E_PLAIN, PACK_E_HARD = 10, 10  # O.5's E: plain + hard absent points
EVAL_ITEMS, EVAL_E = 60, 20  # O.9: every kept label up to 60 + 20 E crops
PER_FLOOR_ITEM = 3  # O.5 / O.9: at most 3 crops per floor item
HARD_POOL = 200  # absent points fitted to find the hard ones (one per TRAIN frame, seeded)
NEG_DX, NEG_DY = 7, 5  # O.1e (fi_study.py): an absent point within +-7 x +-5 cells of ours ...
NEG_ITEM_CHEB, NEG_UNIT_CHEB = 3, 2  # ... > 3 cells from a floor item, > 2 from a unit ...
NEG_ITEM_SPAN_NS = 3 * NS  # ... alive within +-3 s of the frame
NEG_TRIES = 40
SUBS = (3, 6, 9, 12)
# the floor's colours behind reference.png's sprites: the median RGB of the orange and the pale
# floor pixels in the 33 x 33 windows around 12 of O.1e's absent points on FIT p31 (measured
# 2026-11-10 11:1x ICT: 8,795 orange and 88 pale pixels)
TILE_ORANGE = (202, 125, 86)
TILE_PALE = (224, 202, 172)


@dataclass(frozen=True)
class FiSpec:
    """One map's floor-item rule (only xmas_dun02's exists: Amendment O)."""

    name: str
    mspec: ml.MapSpec
    rule: str
    val_suffixes: tuple[str, ...]  # FIT -> VAL (monitor only)
    refused_suffixes: tuple[str, ...]  # refused by NAME beside the map's monster TEST
    eval_suffixes: tuple[str, ...]  # the held-out, read only by --eval-test
    monster_params: Path  # the frozen monster params: the 1d offset and k
    monster_params_sha256: str
    sprites: Path  # the decoded item SPR / ACT files
    resnames: Path  # idnum2itemresnametable.txt
    params: Path  # O.3 (g)
    anchor_px: tuple[float, float]
    scale: float
    r_label: int
    t_item: float
    bar: Box
    d_appear_s: float
    d_gone_s: float
    stack_iou: float
    pack_seed: int
    eval_seed: int
    salt: str
    plan: str
    # params v2 (Amendment O3): the absent rule's sessions (FIT, DEV) and its output file
    absent_suffixes: tuple[str, ...] = ()
    params_v2: Path | None = None


XMAS02_FI = FiSpec(
    name="xmas_dun02",
    mspec=ml.XMAS02,
    rule=RULE,
    val_suffixes=("-rdp-hunt-xmas02-p31",),
    refused_suffixes=("-rdp-s3-xmas02-p30",),
    eval_suffixes=ml.XMAS02_FIT,
    monster_params=ml.XD / "fit" / "params.json",
    monster_params_sha256="d4cc0a5d9e530e382e31ea9c9ae1fc1087dd31c37577b43b307eff65994fdb6e",
    sprites=FI / "items" / "data" / "sprite" / "아이템",
    resnames=FI / "grf" / "data" / "idnum2itemresnametable.txt",
    params=FI / "params.json",
    anchor_px=(-4.0, 2.0),
    scale=1.0,
    r_label=10,
    t_item=0.65,
    bar=(-31.0, 10.0, 28.0, 18.0),
    d_appear_s=2.2,
    d_gone_s=0.6,
    stack_iou=0.5,
    pack_seed=61,
    eval_seed=63,
    salt="xmas02-fi",
    plan="docs/planning/xmas02-detector.md Amendment O / O1",
    absent_suffixes=("-rdp-hunt-xmas02-p31", "-rdp-hunt-xmas02-p38"),
    params_v2=FI / "params-v2.json",
)  # fmt: skip
FI_MAPS = {"xmas_dun02": XMAS02_FI}


# --- pure parts --------------------------------------------------------------------------------


def role_refusal(spec: FiSpec, sid: str, split: str | None, eval_test: bool) -> str | None:
    """PURE (O.6): why the session NAMED ``sid`` may not be labelled in this role, else None.
    ``split`` train / val (None with ``eval_test``). Checked on the directory's name BEFORE anything
    is read, and again on the manifest's session id."""

    def on(xs: Sequence[str]) -> bool:
        return any(sid.endswith(x) for x in xs)

    if eval_test:
        if on(spec.eval_suffixes):
            return None
        names = ", ".join(spec.eval_suffixes)
        return f"--eval-test reads the held-out only (a name ending in {names})"
    if on(spec.eval_suffixes):
        return "the floor items' held-out (fiT, Amendment O1): --eval-test only"
    if spec.mspec.is_test(sid, None):
        return "shares frames with the map's TEST (3b; gw3, Amendment M)"
    if on(spec.refused_suffixes):
        return "not usable (O.0: p30 is the GPU video recording)"
    if split == "val" and not on(spec.val_suffixes):
        return f"--split val is FIT only ({', '.join(spec.val_suffixes)}; O.6)"
    if split == "train" and on(spec.val_suffixes):
        return "FIT (p31) is VAL only (O.6): --split val"
    if split not in ("train", "val"):
        return f"--split {split}: train or val"
    return None


def at_scale(p: SpritePrediction, s: float) -> SpritePrediction:
    """PURE (O.1b): the prediction drawn at the FIXED scale ``s`` about its anchor (items are
    not billboard-scaled)."""
    a, b = p.anchor_px, p.box
    k = s / p.scale
    box = (a[0] + (b[0] - a[0]) * k, a[1] + (b[1] - a[1]) * k,
           a[0] + (b[2] - a[0]) * k, a[1] + (b[3] - a[1]) * k)  # fmt: skip
    return dataclasses.replace(p, scale=s, box=box, mask=None, mask_origin=None)


def cheb(a: Sequence[float], b: Sequence[float]) -> float:
    return max(abs(float(a[0]) - float(b[0])), abs(float(a[1]) - float(b[1])))


def frame_reasons(
    preds: Mapping[int, Box], phases: Sequence[str], me: tuple[float, float],
    units: Sequence[tuple[float, float]], size: tuple[int, int],
    rects: Sequence[tuple[int, int, int, int]], bar: Box, stack_iou: float,
) -> tuple[list[str], list[int]]:  # fmt: skip
    """PURE (O.3 (d), before the fit): the frame's exclusion reasons and the floor ids to fit.
    ``preds``: floor id -> the ANCHORED box of every item ON the floor; ``phases``: every nearby
    item's phase; ``rects``: UI windows (x, y, w, h). Wholly behind the UI or off the region: not
    drawn, no label."""
    why: list[str] = []
    if "settling" in phases:
        why.append("item_settling")
    if "vanishing" in phases:
        why.append("item_vanishing")
    xyxy = [(float(x), float(y), float(x + w), float(y + h)) for x, y, w, h in rects]
    vis: list[int] = []
    for fid, b in preds.items():
        st = il.ui_status(b, xyxy, size)
        if st == "hidden":
            continue
        if st != "clear":
            why.append(st)
            continue
        vis.append(fid)
    if il.stacked([preds[f] for f in vis], stack_iou):
        why.append("stacked")
    for fid in vis:
        b = preds[fid]
        if gi.overlaps(b, gi.self_box(me)):
            why.append("under_self")
        if gi.overlaps(b, gi.at(me, bar)):
            why.append("under_bar")
        if any(gi.overlaps(b, gi.at(u, gi.UNIT_BOX)) for u in units):
            why.append("under_unit")
    return list(dict.fromkeys(why)), vis


def g2_clear(box: Box, me: tuple[float, float], units: Sequence[tuple[float, float]],
             others: Sequence[Box], size: tuple[int, int],
             rects: Sequence[tuple[int, int, int, int]], bar: Box,
             under: str | None) -> bool:  # fmt: skip
    """PURE (O.4 / O.6): the view is a CLEAR one for G2 (the module docstring)."""
    if gi.overlaps(box, gi.self_box(me)) or gi.overlaps(box, gi.at(me, bar)):
        return False
    if any(gi.overlaps(box, gi.at(u, gi.UNIT_BOX)) for u in units):
        return False
    if any(gi.overlaps(box, o) for o in others):
        return False
    return gi.inside(box, size, rects, MARGIN_PX) and under is None


def g2_summary(fits: Sequence[Mapping[str, Any]], bar: float = G2_BAR_PX,
               min_fits: int = G2_MIN_FITS) -> dict[str, Any]:  # fmt: skip
    """PURE (O.6): the join rule's offset check on a session's clear fits (each with dx, dy):
    PASS when the median |dx| and |dy| are <= ``bar`` on >= ``min_fits`` fits; fewer fits:
    NOT_ENOUGH (not admitted); else FAIL (not admitted)."""
    n = len(fits)
    out: dict[str, Any] = {
        "n": n,
        "bar_px": bar,
        "min_fits": min_fits,
        "floor_items": len({(x.get("session"), x["floor_id"]) for x in fits}),
    }
    if n == 0:
        return {**out, "verdict": "NOT_ENOUGH"}
    mdx = statistics.median(abs(float(x["dx"])) for x in fits)
    mdy = statistics.median(abs(float(x["dy"])) for x in fits)
    out.update({"median_abs_dx": mdx, "median_abs_dy": mdy,
                "within_3px": round(sum(abs(x["dx"]) <= 3 and abs(x["dy"]) <= 3 for x in fits)
                                    / n, 3)})  # fmt: skip
    if n < min_fits:
        return {**out, "verdict": "NOT_ENOUGH"}
    return {**out, "verdict": "PASS" if mdx <= bar and mdy <= bar else "FAIL"}


def g2_rows(frames: Sequence[Mapping[str, Any]], session: str = "") -> list[dict[str, Any]]:
    """PURE: the clear fits of a label file's frames (any status: G2 reads every fitted view)."""
    return [{"session": session, "frame_id": f["frame_id"], "floor_id": it["floor_id"],
             "dx": it["dx"], "dy": it["dy"], "ncc": it["ncc"]}
            for f in frames for it in f.get("items", []) if it.get("g2_clear")]  # fmt: skip


def count_labels(frames: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """PURE (O.4's table): kept frames with >= 1 item label, the labels, the floor items, by id,
    the frame exclusions (a frame may carry several), the negatives."""
    with_near = [f for f in frames if f.get("n_near")]
    kept = [f for f in frames if f["status"] == "keep" and f["items"]]
    labels = [it for f in kept for it in f["items"]]
    rel: Counter[str] = Counter()
    for it in labels:
        r = it.get("rel")
        d = None if r is None else cheb(r, (0, 0))
        rel["within_1" if d is not None and d <= 1 else "2_5" if d is not None and d <= 5
            else "farther"] += 1  # fmt: skip
    return {
        "frames": len(frames),
        "frames_with_items_near": len(with_near),
        "kept_frames_with_items": len(kept),
        "item_labels": len(labels),
        "floor_items": len({it["floor_id"] for it in labels}),
        "by_item_id": dict(Counter(str(it["item_id"]) for it in labels).most_common()),
        "by_distance": dict(rel),
        "under_model_kept": sum(1 for it in labels if it.get("under")),
        "frame_exclusions": dict(Counter(r for f in frames for r in f["reasons"]).most_common()),
        "negatives": sum(1 for f in frames if f["status"] == "keep" and not f["items"]),
        "excluded_frames": sum(1 for f in frames if f["status"] == "exclude"),
    }  # fmt: skip


def stratum_of(item: Mapping[str, Any]) -> str:
    """PURE (O.5): N within 1 cell of our cell (any cover), else M under a model / terrain box,
    else F. A label without a position (no self cell) is F or M by its cover."""
    rel = item.get("rel")
    if rel is not None and cheb(rel, (0, 0)) <= 1:
        return "N"
    return "M" if item.get("under") else "F"


def draw_strata(cands: Sequence[Mapping[str, Any]], sizes: Mapping[str, int], seed: int,
                salt: str, per_floor: int = PER_FLOOR_ITEM) -> list[dict[str, Any]]:  # fmt: skip
    """PURE (O.5): per stratum (in ``sizes``' order) its first ``sizes[s]`` candidates in a
    seeded order (sorted by session, frame, floor id; ``random.Random(f"{salt}:{seed}:{s}")``),
    at most ``per_floor`` crops per (session, floor id) over the whole pack."""
    per: Counter[tuple[str, int]] = Counter()
    out: list[dict[str, Any]] = []
    for s, n in sizes.items():
        pool = sorted(
            (c for c in cands if c["stratum"] == s),
            key=lambda c: (c["session"], int(c["frame_id"]), int(c["floor_id"])),
        )
        random.Random(f"{salt}:{seed}:{s}").shuffle(pool)
        k = 0
        for c in pool:
            if k >= n:
                break
            key = (str(c["session"]), int(c["floor_id"]))
            if per[key] >= per_floor:
                continue
            per[key] += 1
            out.append(dict(c))
            k += 1
    return out


def hard_pick(points: Sequence[Mapping[str, Any]], n: int) -> list[dict[str, Any]]:
    """PURE (O.5's HARD negatives): the ``n`` absent points with the highest colour fit, one per
    frame (ties: session, frame)."""
    order = sorted(
        (p for p in points if p.get("ncc") is not None),
        key=lambda p: (-float(p["ncc"]), p["session"], int(p["frame_id"])),
    )
    out, seen = [], set()
    for p in order:
        key = (p["session"], int(p["frame_id"]))
        if key in seen:
            continue
        seen.add(key)
        out.append(dict(p))
        if len(out) >= n:
            break
    return out


def absent_cell(me_cell: tuple[float, float], items: Sequence[tuple[float, float]],
                units: Sequence[tuple[float, float]], rng: random.Random
                ) -> tuple[int, int] | None:  # fmt: skip
    """PURE (O.1e, fi_study.py's controls): a cell within +-7 x +-5 of ours, not ours or next to
    it, > 3 cells (Chebyshev) from every floor item alive within +-3 s and > 2 from every unit;
    None after NEG_TRIES tries."""
    for _ in range(NEG_TRIES):
        c = (int(round(me_cell[0])) + rng.randint(-NEG_DX, NEG_DX),
             int(round(me_cell[1])) + rng.randint(-NEG_DY, NEG_DY))  # fmt: skip
        if cheb(c, me_cell) <= 1 or any(cheb(c, x) <= NEG_ITEM_CHEB for x in items):
            continue
        if any(cheb(c, u) <= NEG_UNIT_CHEB for u in units):
            continue
        return c
    return None


def cell_box(scene: Any, cell: tuple[float, float], half: float) -> Box:
    """The pixel bbox of the projected square of +-``half`` cells around ``cell`` (corners and
    edge midpoints, the GAT altitude): a cell neighbourhood on screen."""
    pts = [anchor_and_depth(scene, (cell[0] + dx * half, cell[1] + dy * half))[0]
           for dx in (-1, 0, 1) for dy in (-1, 0, 1)]  # fmt: skip
    us, vs = [p[0] for p in pts], [p[1] for p in pts]
    return (round(min(us), 1), round(min(vs), 1), round(max(us), 1), round(max(vs), 1))


def kill_rows(deaths: Sequence[Mapping[str, Any]], floors: Sequence[il.Floor],
              before_s: float = 1.5, after_s: float = 1.0, cells: float = 2.5
              ) -> list[dict[str, Any]]:  # fmt: skip
    """PURE (O.1a, the study's pk_stats.py): each of OUR kills (``deaths``: t, gid, job, cell)
    with its drops: the ``fall`` floor items appearing from ``before_s`` before to ``after_s``
    after the death within ``cells`` cells (Chebyshev) of the death cell."""
    out = []
    for d in deaths:
        t, cell = int(d["t"]), d.get("cell")
        drops = [f.floor_id for f in floors if cell is not None and f.kind == "fall"
                 and -before_s <= (f.t_a - t) / NS <= after_s
                 and cheb((f.x, f.y), cell) <= cells]  # fmt: skip
        out.append({"t": t, "gid": d["gid"], "job": d.get("job"), "cell": cell,
                    "drops": drops})  # fmt: skip
    return out


# --- the colour fit (O.1e / O.3 (c); the study's fi_refit.py) ----------------------------------


def rendered_rgb(sheet: SpriteSheet, p: SpritePrediction, window: tuple[int, int, int, int]
                 ) -> tuple[npt.NDArray[np.float64], npt.NDArray[np.bool_]]:  # fmt: skip
    """The sprite's frame (action ``p.action_index``, frame 0) drawn at ``p``'s anchor and scale
    over the pixel window (i0, j0, i1, j1): its RGB and its opaque pixels (nearest canvas pixel of
    each screen pixel centre)."""
    i0, j0, i1, j1 = window
    rgba, (ox, oy) = compose_frame(sheet.spr, sheet.act, p.action_index, 0)  # type: ignore[arg-type]
    rgb = np.zeros((j1 - j0, i1 - i0, 3))
    op = np.zeros((j1 - j0, i1 - i0), bool)
    cx = np.floor((np.arange(i0, i1) + 0.5 - p.anchor_px[0]) / p.scale + ox).astype(np.int64)
    cy = np.floor((np.arange(j0, j1) + 0.5 - p.anchor_px[1]) / p.scale + oy).astype(np.int64)
    okx = (cx >= 0) & (cx < rgba.shape[1])
    oky = (cy >= 0) & (cy < rgba.shape[0])
    sub = rgba[np.ix_(cy[oky], cx[okx])]
    rgb[np.ix_(oky, okx)] = sub[..., :3]
    op[np.ix_(oky, okx)] = sub[..., 3] > 0
    return rgb, op


def _corr_terms(obs: npt.NDArray[np.float64], valid: npt.NDArray[np.bool_],
                tpl: npt.NDArray[np.float64], mask: npt.NDArray[np.bool_],
                r: int) -> list[npt.NDArray[np.float64]]:  # fmt: skip
    shape = obs.shape
    m = mask.astype(float)
    v = valid.astype(float)
    o = np.where(valid, obs, 0.0)
    f_v, f_o, f_oo = np.fft.rfft2(v), np.fft.rfft2(o), np.fft.rfft2(o * o)

    def corr(k: npt.NDArray[np.float64], f: Any) -> npt.NDArray[np.float64]:
        kk = np.fft.rfft2(k, s=shape)
        return np.fft.irfft2(f * np.conj(kk), s=shape)[: 2 * r + 1, : 2 * r + 1]

    tm = tpl * m
    return [np.round(corr(m, f_v)), corr(tm, f_v), corr(tm * tpl, f_v), corr(m, f_o),
            corr(m, f_oo), corr(tm, f_o)]  # fmt: skip


def ncc_grid(chans_obs: Sequence[npt.NDArray[np.float64]], valid: npt.NDArray[np.bool_],
             chans_tpl: Sequence[npt.NDArray[np.float64]], mask: npt.NDArray[np.bool_],
             r: int) -> npt.NDArray[np.float64]:  # fmt: skip
    """The joint zero-mean masked NCC over the channels (3 = colour as one vector) at every
    offset in +-r (row = dy + r, column = dx + r); NaN where < MIN_PIXELS per channel score."""
    tot: list[npt.NDArray[np.float64]] | None = None
    for o, t in zip(chans_obs, chans_tpl, strict=True):
        terms = _corr_terms(o, valid, t, mask, r)
        tot = terms if tot is None else [a + b for a, b in zip(tot, terms, strict=True)]
    assert tot is not None
    n, st, stt, so, soo, sto = tot
    out = np.full(n.shape, np.nan)
    ok = n >= label_check.MIN_PIXELS * len(chans_obs)
    with np.errstate(divide="ignore", invalid="ignore"):
        cov = sto - st * so / n
        vt = stt - st * st / n
        vo = soo - so * so / n
        good = ok & (vt > 1e-9 * np.maximum(stt, 1.0)) & (vo > 1e-9 * np.maximum(soo, 1.0))
        out[good] = cov[good] / np.sqrt(vt[good] * vo[good])
    return out


def colour_fit(bgr: npt.NDArray[np.uint8], valid_full: npt.NDArray[np.bool_],
               sheet: SpriteSheet, p: SpritePrediction,
               r: int) -> tuple[float, int, int] | None:  # fmt: skip
    """(NCC, dx, dy): the best masked COLOUR NCC of the sprite drawn at ``p`` within +-``r`` px,
    on the frame's valid (non-UI) pixels; None when nothing scores (off the frame)."""
    i0, j0 = math.floor(p.box[0]), math.floor(p.box[1])
    i1, j1 = math.ceil(p.box[2]), math.ceil(p.box[3])
    rgb_t, op = rendered_rgb(sheet, p, (i0, j0, i1, j1))
    h, w = bgr.shape[:2]
    wi0, wj0, wi1, wj1 = i0 - r, j0 - r, i1 + r, j1 + r
    shp = (wj1 - wj0, wi1 - wi0)
    ci0, cj0, ci1, cj1 = max(0, wi0), max(0, wj0), min(w, wi1), min(h, wj1)
    if ci1 <= ci0 or cj1 <= cj0:
        return None
    ok = np.zeros(shp, bool)
    ok[cj0 - wj0 : cj1 - wj0, ci0 - wi0 : ci1 - wi0] = valid_full[cj0:cj1, ci0:ci1]
    rgb = bgr[cj0:cj1, ci0:ci1, 2::-1].astype(float)
    obs = []
    for c in range(3):
        z = np.zeros(shp)
        z[cj0 - wj0 : cj1 - wj0, ci0 - wi0 : ci1 - wi0] = rgb[..., c]
        obs.append(z)
    grid = ncc_grid(obs, ok, [rgb_t[..., c] for c in range(3)], op, r)
    if np.isnan(grid).all():
        return None
    a_, b_ = np.unravel_index(int(np.nanargmax(grid)), grid.shape)
    return round(float(grid[a_, b_]), 4), int(b_) - r, int(a_) - r


# --- the client's item sprites, the frozen params ------------------------------------------------


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def drop_ids(spec: FiSpec, drops: Path | None = None) -> list[int]:
    """The map's floor items: every item id in its species' drop tables (the local KB's
    drops.json, rAthena-derived, never committed)."""
    d = json.loads((drops or ROOT / "data" / "kb" / "drops.json").read_text())
    return sorted({int(x["item_id"]) for s in spec.mspec.species for x in (d.get(str(s)) or [])})


def sprite_table(ids: Iterable[int], sprites: Path, resnames: Path) -> dict[str, Any]:
    """Item id -> its resname and the sha256 of its ACT / SPR (None when missing)."""
    names = gi.parse_resnames(resnames.read_bytes())
    out: dict[str, Any] = {}
    for i in sorted(set(ids)):
        n = names.get(i)
        act, spr = (sprites / f"{n}.act", sprites / f"{n}.spr") if n else (None, None)
        if n is None or act is None or spr is None or not act.exists() or not spr.exists():
            out[str(i)] = None
            continue
        out[str(i)] = {"resname": n, "act_sha256": sha256_bytes(act.read_bytes()),
                       "spr_sha256": sha256_bytes(spr.read_bytes())}  # fmt: skip
    return out


class FrozenSheets:
    """Item id -> its SpriteSheet, ONLY for the ids of the frozen table and only when the files'
    sha256 still match it (checked once, at load: a changed sprite refuses the run). ``excluded``
    (params v2, Amendment O3): ids treated as ``item_unsprited`` -- never labelled (``__call__``
    and ``sheets`` leave them out), though their sprite is still drawn where a box is only
    predicted (``any``: the evaluation's floor targets, G2's other items) and on reference.png
    (``all``)."""

    def __init__(self, table: Mapping[str, Any], sprites: Path,
                 excluded: Iterable[int] = ()) -> None:  # fmt: skip
        self.all: dict[int, SpriteSheet] = {}
        for k, v in table.items():
            if v is None:
                continue
            act = (sprites / f"{v['resname']}.act").read_bytes()
            spr = (sprites / f"{v['resname']}.spr").read_bytes()
            if sha256_bytes(act) != v["act_sha256"] or sha256_bytes(spr) != v["spr_sha256"]:
                raise SystemExit(f"item {k}: its sprite files differ from the frozen params")
            self.all[int(k)] = SpriteSheet(parse_act(act), parse_spr(spr))
        self.excluded = frozenset(int(i) for i in excluded)
        self.sheets = {k: v for k, v in self.all.items() if k not in self.excluded}

    def __call__(self, item_id: int) -> SpriteSheet | None:
        return self.sheets.get(int(item_id))

    def any(self, item_id: int) -> SpriteSheet | None:
        return self.all.get(int(item_id))


def frozen_sheets(prm: Mapping[str, Any]) -> FrozenSheets:
    """The params' sprites (v2: without the ids its absent rule excluded)."""
    return FrozenSheets(prm["items"], Path(prm["sprites_dir"]), prm.get("items_excluded", ()))


def freeze_params(spec: FiSpec, table: Mapping[str, Any], monster: Mapping[str, Any],
                  monster_sha: str, provenance: Mapping[str, Any]) -> dict[str, Any]:  # fmt: skip
    """PURE (O.3 (g)): the frozen params document (O-D2's values, O1)."""
    if monster_sha != spec.monster_params_sha256 or monster.get("status") != "FROZEN":
        raise SystemExit(
            f"{spec.monster_params}: not the frozen monster params "
            f"({spec.monster_params_sha256[:8]}...): the 1d offset comes from it"
        )
    return {
        "rule": spec.rule, "status": "FROZEN", "map": spec.name, "plan": spec.plan,
        "accepted_by": "Amendment O1 (2026-11-10 10:29 ICT): O-D2, frozen when T-O1 first "
                       "writes this file",
        "class": CLASS_NAME, "anchor_px": list(spec.anchor_px), "scale": spec.scale,
        "fit": "masked colour NCC (the 3 channels as one vector), the best offset",
        "r_label": spec.r_label, "t_item": spec.t_item, "bar_px": list(spec.bar),
        "self_box": {"w": gi.SELF_W, "h": gi.SELF_H, "pad": gi.SELF_PAD},
        "unit_box": list(gi.UNIT_BOX), "unit_back_s": gi.UNIT_BACK_NS / NS,
        "stack_iou": spec.stack_iou, "d_appear_s": spec.d_appear_s, "d_gone_s": spec.d_gone_s,
        "sub_table": {"OX": gi.OX, "OY": gi.OY}, "offset_ms": float(monster["offset_ms"]),
        "k": olf.K, "min_pixels": label_check.MIN_PIXELS,
        "monster_params": str(spec.monster_params), "monster_params_sha256": monster_sha,
        "g2": {"bar_px": G2_BAR_PX, "min_fits": G2_MIN_FITS, "margin_px": MARGIN_PX},
        "items": dict(table),
        "items_unsprited": sorted(int(k) for k, v in table.items() if v is None),
        **provenance,
    }  # fmt: skip


ABSENT_POINTS = 60  # O3 (params v2): the absent points drawn on FIT + DEV's kept frames ...
ABSENT_SEED = "per-sprite"  # ... in this seeded order (O2's per-sprite check, reproduced)
ABSENT_MAX_RATE = 0.01  # an id whose sprite fits >= T_item on MORE than 1 % of them is excluded


def absent_groups(table: Mapping[str, Any]) -> dict[int, list[int]]:
    """PURE: each distinct sprite (ACT + SPR sha256) -> its ids, keyed by its smallest id."""
    groups: dict[tuple[str, str], list[int]] = {}
    for k, v in sorted(table.items(), key=lambda kv: int(kv[0])):
        if v is not None:
            groups.setdefault((v["act_sha256"], v["spr_sha256"]), []).append(int(k))
    return {ids[0]: ids for ids in groups.values()}


def absent_rule(fits: Mapping[int, Sequence[float]], groups: Mapping[int, Sequence[int]],
                t_item: float, max_rate: float = ABSENT_MAX_RATE
                ) -> tuple[list[int], dict[str, Any]]:  # fmt: skip
    """PURE (Amendment O3, params v2): per sprite (its representative id -> the colour fits at
    the empty-floor absent points) the share of fits >= ``t_item``; every id of a sprite whose
    share is > ``max_rate`` is EXCLUDED (treated as item_unsprited). A sprite with no fit is
    kept (nothing measured). Returns the excluded ids and the per-sprite rows."""
    excluded: list[int] = []
    rows: dict[str, Any] = {}
    for rep_id, ids in sorted(groups.items()):
        v = [float(x) for x in fits.get(rep_id, [])]
        n, k = len(v), sum(x >= t_item for x in v)
        rate = k / n if n else 0.0
        out = n > 0 and rate > max_rate
        rows[str(rep_id)] = {
            "ids": list(ids),
            "n": n,
            "pass": k,
            "rate": round(rate, 4),
            "max": round(max(v), 4) if v else None,
            "excluded": out,
        }
        if out:
            excluded += list(ids)
    return sorted(excluded), rows


def load_params(path: Path, spec: FiSpec) -> dict[str, Any]:
    d: dict[str, Any] = json.loads(path.read_text())
    if d.get("rule") != spec.rule or d.get("map") != spec.name:
        raise SystemExit(f"{path}: not {spec.rule} params of {spec.name}")
    if d.get("status") != "FROZEN":
        raise SystemExit(f"{path}: {d.get('status')}: FROZEN params only")
    return d


# --- the label pass (forked workers read olf._JOB) ----------------------------------------------


def _units(sess: ml.RecSession, world: Any, scene: Any, tw: int) -> list[tuple[float, float]]:
    out = []
    for when in (tw, tw - gi.UNIT_BACK_NS):
        fw = world if when == tw else sess.lab.timeline.frame_world(when)
        for e in fw.entities:
            if e.objtype in occ.UNIT_OBJTYPES and not e.hidden:
                out.append(anchor_and_depth(scene, (e.x, e.y))[0])
    return out


def _predict(sheet: SpriteSheet, cell: tuple[float, float], scene: Any,
             prm: Mapping[str, Any]) -> SpritePrediction | None:  # fmt: skip
    p = predict_sprite(Actor(cell, 0, 0), sheet, scene, olf.K)
    if p is None:
        return None
    return gi.anchored(at_scale(p, float(prm["scale"])), prm["anchor_px"])


def _label_frame(ref: qa_export.JpegRef) -> dict[str, Any]:
    J = olf._JOB
    sess: ml.RecSession = J["sess"]
    floors: list[il.Floor] = J["floors"]
    sheets: FrozenSheets = J["sheets"]
    occl: olf.Occluders = J["occluders"]
    prm: dict[str, Any] = J["params"]
    eval_test: bool = J["eval_test"]
    d_a, d_g = int(float(prm["d_appear_s"]) * NS), int(float(prm["d_gone_s"]) * NS)
    t = ref.t_mono_ns
    base: dict[str, Any] = {"frame_id": ref.frame_id, "t": t, "shard": ref.shard.name,
                            "offset": ref.offset, "size": ref.size}  # fmt: skip
    tw = t - int(float(prm["offset_ms"]) * 1e6)
    world = sess.lab.timeline.frame_world(tw)
    scene = sess.scene(world)
    if scene is None:
        return {**base, "status": "exclude", "reasons": ["no_scene"], "items": [], "n_near": None}
    bgr = ml.read_png(ref)
    if not sess.layout_ok(bgr):
        return {**base, "status": "exclude", "reasons": ["ui_layout_mismatch"], "items": [],
                "n_near": None}  # fmt: skip
    me = anchor_and_depth(scene, scene.player)[0]
    sp = world.self_pos
    near = [(f, ph) for f in floors if (ph := il.phase(f, t, d_a, d_g)) != "none"]
    base.update({"me": [round(me[0], 1), round(me[1], 1)], "n_near": len(near),
                 "self_cell": None if sp is None else [float(sp[0]), float(sp[1])]})  # fmt: skip
    if eval_test:
        base["around_box"] = cell_box(scene, scene.player, 2.5)
    if not near:
        if eval_test:
            base["floor"] = []
        return {**base, "status": "keep", "reasons": [], "items": []}
    units = _units(sess, world, scene, tw)
    reasons: list[str] = []
    preds: dict[int, tuple[il.Floor, SpriteSheet, SpritePrediction, tuple[float, float]]] = {}
    present: dict[int, Box] = {}  # every item on the floor (on or settling): G2's other items
    floor_rows = []
    unsprited: list[int] = []
    for f, ph in near:
        cell = il.item_cell(f, gi.OX, gi.OY)
        sheet = sheets(f.item_id)  # None: unsprited, or excluded by v2's absent rule (O3)
        draw = sheets.any(f.item_id)  # its sprite even when excluded: a predicted box only
        p = None if draw is None else _predict(draw, cell, scene, prm)
        if eval_test:
            floor_rows.append({"floor_id": f.floor_id, "item_id": f.item_id, "phase": ph,
                               "pred_box": None if p is None else [round(x, 1) for x in p.box],
                               "near_box": cell_box(scene, cell, 1.5)})  # fmt: skip
        if p is not None and ph in ("on", "settling"):
            present[f.floor_id] = p.box
        if ph == "on" and sheet is None:
            reasons.append("item_unsprited")
            unsprited.append(f.item_id)
            continue
        if ph == "on" and p is None:
            reasons.append("item_unprojected")
            continue
        if ph == "on" and p is not None and sheet is not None:
            preds[f.floor_id] = (f, sheet, p, cell)
    if eval_test:
        base["floor"] = floor_rows
    size, rects = sess.lab.size, sess.lab.ui_rects
    why, vis = frame_reasons({k: v[2].box for k, v in preds.items()}, [ph for _f, ph in near], me,
                             units, size, rects, tuple(prm["bar_px"]),
                             float(prm["stack_iou"]))  # fmt: skip
    reasons += why
    valid = olf.valid_map(size, rects)
    r, t_item = int(prm["r_label"]), float(prm["t_item"])
    items = []
    for fid in vis:
        f, sheet, p, cell = preds[fid]
        fr = colour_fit(bgr, valid, sheet, p, r)
        if fr is None:
            reasons.append("edge_partial")
            continue
        ncc, dx, dy = fr
        unfit = ncc < t_item or olf.at_edge(dx, dy, r)
        b = p.box
        under = occl.under(scene, b, cell)
        others = [x for k, x in present.items() if k != fid]
        items.append({
            "floor_id": f.floor_id, "item_id": f.item_id, "kind": f.kind,
            "box": [round(b[0] + dx, 1), round(b[1] + dy, 1), round(b[2] + dx, 1),
                    round(b[3] + dy, 1)],
            "pred_box": [round(x, 1) for x in b], "ncc": ncc, "dx": dx, "dy": dy,
            "unfit": unfit, "under": under,
            "rel": None if sp is None else [round(f.x - sp[0], 1), round(f.y - sp[1], 1)],
            "age_s": round((t - f.t_a) / NS, 2),
            "g2_clear": g2_clear(b, me, units, others, size, rects, tuple(prm["bar_px"]), under),
        })  # fmt: skip
        if unfit:
            reasons.append("item_unfit")
    reasons = list(dict.fromkeys(reasons))
    if unsprited:  # which ids made it item_unsprited (v2: the absent rule's, O3)
        base["unsprited_ids"] = sorted(set(unsprited))
    return {**base, "status": "exclude" if reasons else "keep", "reasons": reasons,
            "items": items}  # fmt: skip


def our_deaths(sess: ml.RecSession) -> tuple[int | None, list[dict[str, Any]]]:
    """Our character's id and the deaths of the units it hit (the study's pk_stats.py: an
    ``entity_vanish`` reason 1 of a gid with our ``act`` of damage > 0), each with its cell 50 ms
    before (Timeline)."""
    tl = sess.lab.timeline
    evs = tl.events
    aid = tl.frame_world(sess.refs[-1].t_mono_ns).aid if sess.refs else None
    ours = {e.get("target_gid") for e in evs
            if e.get("type") == "act" and aid is not None and e.get("src_gid") == aid
            and (e.get("damage") or 0) > 0}  # fmt: skip
    out = []
    for e in evs:
        if e.get("type") != "entity_vanish" or e.get("reason") != 1 or e.get("gid") not in ours:
            continue
        td = int(e["t_mono_ns"])
        ent = [x for x in tl.frame_world(td - 50_000_000).entities if x.gid == e["gid"]]
        out.append({"t": td, "gid": e["gid"], "job": ent[0].job if ent else None,
                    "cell": [ent[0].x, ent[0].y] if ent else None})  # fmt: skip
    return aid, out


def kills_for_eval(
    sess: ml.RecSession, floors: Sequence[il.Floor], prm: Mapping[str, Any]
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Our kills with their drops (kill_rows), the death cell relative to us, and for I4 the first
    recorded frame 2.0-3.0 s after the death with the death cell's 3 x 3 on screen (None when the
    frame has no scene)."""
    aid, deaths = our_deaths(sess)
    rows = kill_rows(deaths, floors)
    off = int(float(prm["offset_ms"]) * 1e6)
    tl = sess.lab.timeline
    times = [x.t_mono_ns for x in sess.refs]
    for k in rows:
        me = tl.frame_world(int(k["t"])).self_pos
        k["rel"] = (
            None
            if me is None or k["cell"] is None
            else [round(k["cell"][0] - me[0], 1), round(k["cell"][1] - me[1], 1)]
        )
        k["i4"] = None
        i = bisect.bisect_left(times, int(k["t"]) + 2 * NS)
        if i < len(times) and times[i] < int(k["t"]) + 3 * NS and k["cell"] is not None:
            ref = sess.refs[i]
            scene = sess.scene(tl.frame_world(ref.t_mono_ns - off))
            k["i4"] = {
                "frame_id": ref.frame_id,
                "t": ref.t_mono_ns,
                "shard": ref.shard.name,
                "offset": ref.offset,
                "size": ref.size,
                "box3": None if scene is None else cell_box(scene, tuple(k["cell"]), 1.5),
            }
    return rows, {"aid": aid, "kills": len(rows),
                  "with_drop": sum(1 for k in rows if k["drops"])}  # fmt: skip


def cmd_freeze(a: argparse.Namespace) -> dict[str, Any]:
    spec = FI_MAPS[a.map]
    out: Path = a.out or spec.params
    if out.exists():
        raise SystemExit(f"{out} exists: the params are frozen ONCE (O.3 (g)); a change is a new "
                         "amendment and a new file")  # fmt: skip
    if out.resolve().is_relative_to(ROOT):
        raise SystemExit(f"{out}: client-derived (sprite hashes): never inside the repo")
    mraw = spec.monster_params.read_bytes()
    ids = drop_ids(spec, a.drops)
    table = sprite_table(ids, a.sprites or spec.sprites, a.resnames or spec.resnames)
    occl = ml.occluders(spec.mspec)
    tool = Path(__file__).resolve()
    prov = {
        "drops": str(a.drops or ROOT / "data" / "kb" / "drops.json"),
        "drops_sha256": olf.sha256_file(a.drops or ROOT / "data" / "kb" / "drops.json"),
        "sprites_dir": str(a.sprites or spec.sprites),
        "resnames": str(a.resnames or spec.resnames),
        "resnames_sha256": olf.sha256_file(a.resnames or spec.resnames),
        "occluders": {"rsw_sha256": occl.provenance()["rsw_sha256"],
                      "terrain": spec.mspec.terrain},
        "tool": str(tool.relative_to(ROOT)), "tool_sha256": olf.sha256_file(tool),
        "frozen_at": olf.now_ict(), "commit": olf.git_head(),
    }  # fmt: skip
    doc = freeze_params(spec, table, json.loads(mraw), sha256_bytes(mraw), prov)
    out.parent.mkdir(parents=True, exist_ok=True)
    raw = (json.dumps(doc, indent=1, ensure_ascii=False) + "\n").encode()
    out.write_bytes(raw)
    return {"what": "O.3 (g): the frozen xmas02-fi-1 params", "out": str(out),
            "sha256": sha256_bytes(raw), "items": len(table),
            "items_unsprited": doc["items_unsprited"],
            "distinct_sprites": len({(v["act_sha256"], v["spr_sha256"]) for v in table.values()
                                     if v}), "frozen_at": prov["frozen_at"],
            "commit": prov["commit"]}  # fmt: skip


def cmd_label(a: argparse.Namespace) -> dict[str, Any]:
    spec = FI_MAPS[a.map]
    split = None if a.eval_test else a.split
    path = ml.parse_part(a.part)[0]
    if ml.parse_part(a.part)[1] is not None:
        raise SystemExit(f"{a.part}: whole sessions only (no spots on {spec.name})")
    why = role_refusal(spec, path.name, split, a.eval_test)  # the NAME, before anything is read
    if why is not None:
        raise SystemExit(f"{a.part}: {why}: refused")
    params_raw = a.params.read_bytes()
    prm = load_params(a.params, spec)
    model: dict[str, Any] | None = None
    if a.eval_test:  # O.9: the held-out is read only after the model is frozen
        if a.model is None or a.model_sha256 is None:
            raise SystemExit("--eval-test needs --model WEIGHTS and --model-sha256 HEX (the frozen "
                             "item model, its sha256 recorded before fiT is read)")  # fmt: skip
        if not a.model.is_file():
            raise SystemExit(f"{a.model}: no frozen model: fiT stays unread")
        got = olf.sha256_file(a.model)
        if got != a.model_sha256:
            raise SystemExit(f"{a.model}: sha256 {got}, not the frozen {a.model_sha256}")
        model = {"weights": str(a.model), "sha256": got, "bytes": a.model.stat().st_size}
    elif a.model is not None or a.model_sha256 is not None:
        raise SystemExit("--model / --model-sha256 belong to --eval-test")
    sheets = frozen_sheets(prm)
    occl = ml.occluders(spec.mspec)
    if occl.provenance()["rsw_sha256"] != prm["occluders"]["rsw_sha256"]:
        raise SystemExit("the map's RSW differs from the frozen params'")
    sess = ml.RecSession.open(a.part, spec.mspec, a.layout_templates)
    why = role_refusal(spec, sess.sid, split, a.eval_test)  # by the manifest's id too
    if why is not None:
        raise SystemExit(f"{sess.sid}: {why}: refused")
    refs = sess.candidates_at(float(prm["offset_ms"]))
    floors = il.floor_items(sess.lab.timeline.events)
    olf._JOB.update(sess=sess, floors=floors, sheets=sheets, occluders=occl, params=prm,
                    eval_test=bool(a.eval_test))  # fmt: skip
    frames = olf.run_parallel(_label_frame, refs, a.workers)
    out: dict[str, Any] = {
        "what": f"the {spec.rule} floor-item labels (no pixels): per candidate frame",
        "rule": spec.rule, "class": CLASS_NAME, "map": spec.name, "part": a.part,
        "session": sess.sid, "split": "eval" if a.eval_test else split,
        "eval_test": bool(a.eval_test), "params": str(a.params),
        "params_sha256": sha256_bytes(params_raw), "params_status": prm["status"],
        "labelled_at": olf.now_ict(), "commit": olf.git_head(),
        "frames_recorded": len(sess.refs), "candidates": len(refs),
        "candidate_drops": dict(sorted(sess.dropped.items())),
        "floor_items_in_packets": len(floors),
        "floor_items_by_kind": dict(Counter(f.kind for f in floors)),
        "counts": count_labels(frames),
        "g2": g2_summary(g2_rows(frames, sess.sid)),
    }  # fmt: skip
    if model is not None:
        out["model"] = model
        out["kills"], out["kills_summary"] = kills_for_eval(sess, floors, prm)
    out["frames"] = frames
    return out


def absent_fits(
    docs: Sequence[Mapping[str, Any]],
    spec: FiSpec,
    prm: Mapping[str, Any],
    sheets: FrozenSheets,
    layout: Path,
    n: int = ABSENT_POINTS,
    seed: str = ABSENT_SEED,
) -> tuple[list[dict[str, Any]], dict[int, list[float]]]:
    """Params v2's measurement (O3; O2's per-sprite check as a tool): ``n`` absent points of
    O.1e's rule on the docs' kept frames (absent_points, ``random.Random(seed)``), and at each
    one the colour fit (+-r_label, the params' scale and anchor) of EVERY distinct sprite of the
    table, its sub-cell drawn by ``random.Random(frame_id)`` / ``random.Random(frame_id + 1)``.
    Returns the points (their provenance and fits) and the fits per sprite (its smallest id)."""
    sessions: dict[str, ml.RecSession] = {}
    pts = absent_points(docs, spec, prm, sheets, sessions, layout, n, random.Random(seed),
                        fit=False)  # fmt: skip
    groups = absent_groups(prm["items"])
    off = int(float(prm["offset_ms"]) * 1e6)
    r = int(prm["r_label"])
    fits: dict[int, list[float]] = {k: [] for k in groups}
    rows = []
    for pt in pts:
        sess = sessions[pt["session"]]
        bgr = ml.read_png(_ref(sess, pt))
        valid = olf.valid_map(sess.lab.size, sess.lab.ui_rects)
        scene = sess.scene(sess.lab.timeline.frame_world(int(pt["t"]) - off))
        fid = int(pt["frame_id"])
        sub = (random.Random(fid).choice(SUBS), random.Random(fid + 1).choice(SUBS))
        cell = (pt["cell"][0] + gi.OX[sub[0]], pt["cell"][1] + gi.OY[sub[1]])
        row: dict[str, Any] = {"session": pt["session"], "frame_id": fid, "t": pt["t"],
                               "cell": pt["cell"], "sub": list(sub), "fits": {}}  # fmt: skip
        for rep_id in groups:
            sh = sheets.any(rep_id)
            pr = None if sh is None or scene is None else _predict(sh, cell, scene, prm)
            fr = None if pr is None or sh is None else colour_fit(bgr, valid, sh, pr, r)
            if fr is not None:
                fits[rep_id].append(fr[0])
                row["fits"][str(rep_id)] = fr[0]
        rows.append(row)
    return rows, fits


def cmd_freeze_v2(a: argparse.Namespace) -> dict[str, Any]:
    """Params v2 (Amendment O3): v1 + the ids its absent rule excludes, frozen ONCE in a new file
    (v1 stays the record of the positive cases)."""
    spec = FI_MAPS[a.map]
    out: Path | None = a.out or spec.params_v2
    if out is None:
        raise SystemExit(f"{spec.name}: no params v2 path")
    if out.exists():
        raise SystemExit(f"{out} exists: params v2 is frozen ONCE (O3); a change is a new file")
    if out.resolve().is_relative_to(ROOT):
        raise SystemExit(f"{out}: client-derived (sprite hashes): never inside the repo")
    raw1 = a.v1.read_bytes()
    v1 = load_params(a.v1, spec)
    if v1.get("version", 1) != 1 or "items_excluded" in v1:
        raise SystemExit(f"{a.v1}: v2 is built from the v1 params")
    v1_sha = sha256_bytes(raw1)
    docs, files = [], []
    for path in a.labels:
        doc = json.loads(path.read_text())
        sid = str(doc.get("session"))
        if doc.get("rule") != spec.rule or doc.get("params_sha256") != v1_sha:
            raise SystemExit(f"{path}: not {spec.rule} labels under {a.v1}")
        if doc.get("eval_test") or role_refusal(spec, sid, doc.get("split"), False):
            raise SystemExit(f"{path}: {sid}: not a FIT / DEV label file")
        docs.append(doc)
        files.append({"file": str(path), "sha256": olf.sha256_file(path), "session": sid,
                      "split": doc["split"]})  # fmt: skip
    got = sorted(next((x for x in spec.absent_suffixes if f["session"].endswith(x)), "")
                 for f in files)  # fmt: skip
    if got != sorted(spec.absent_suffixes):
        raise SystemExit(f"--labels: one label file each of {', '.join(spec.absent_suffixes)} "
                         "(O3: the rule is fixed on FIT + DEV)")  # fmt: skip
    sheets = frozen_sheets(v1)
    rows, fits = absent_fits(docs, spec, v1, sheets, a.layout_templates)
    excluded, per = absent_rule(fits, absent_groups(v1["items"]), float(v1["t_item"]))
    tool = Path(__file__).resolve()
    doc = dict(v1)
    doc.update({
        "version": 2, "plan": f"{spec.plan} / O3",
        "accepted_by": "Amendment O3 (2026-11-10 11:30 ICT): O2 finding 7.2, a per-id rule fixed "
                       "on FIT + DEV's empty-floor absent points; frozen when this tool first "
                       "writes this file",
        "v1": str(a.v1), "v1_sha256": v1_sha, "v1_frozen_at": v1.get("frozen_at"),
        "v1_commit": v1.get("commit"),
        "absent_rule": {
            "what": "an id whose sprite fits >= t_item on MORE than max_rate of the absent points "
                    "is treated as item_unsprited (never labelled; its frames excluded)",
            "t_item": float(v1["t_item"]), "max_rate": ABSENT_MAX_RATE,
            "points_drawn": ABSENT_POINTS, "points": len(rows), "seed": ABSENT_SEED,
            "point_rule": "O.1e via fi_labels.absent_points on the label files' kept frames",
            "sub_rule": "random.Random(frame_id) / random.Random(frame_id + 1) over 3, 6, 9, 12",
            "fit": f"colour NCC +-{v1['r_label']} px, scale {v1['scale']}, anchor "
                   f"{v1['anchor_px']}", "label_files": files, "per_sprite": per,
            "point_rows": rows},
        "items_excluded": excluded,
        "frozen_at": olf.now_ict(), "commit": olf.git_head(),
        "tool": str(tool.relative_to(ROOT)), "tool_sha256": olf.sha256_file(tool),
    })  # fmt: skip
    out.parent.mkdir(parents=True, exist_ok=True)
    raw = (json.dumps(doc, indent=1, ensure_ascii=False) + "\n").encode()
    out.write_bytes(raw)
    return {"what": "O3: the frozen xmas02-fi-1 params v2", "out": str(out),
            "sha256": sha256_bytes(raw), "v1_sha256": v1_sha, "points": len(rows),
            "items_excluded": excluded,
            "excluded_rates": {k: {x: r[x] for x in ("ids", "n", "pass", "rate", "max")}
                               for k, r in per.items() if r["excluded"]},
            "kept_max_rate": max((r["rate"] for r in per.values() if not r["excluded"]),
                                 default=None),
            "frozen_at": doc["frozen_at"], "commit": doc["commit"]}  # fmt: skip


def cmd_g2(a: argparse.Namespace) -> dict[str, Any]:
    per = {}
    for p in a.labels:
        doc = json.loads(p.read_text())
        per[doc["session"]] = {"file": str(p), "split": doc["split"],
                               "params_sha256": doc["params_sha256"],
                               "floor_items_in_packets": doc["floor_items_in_packets"],
                               **g2_summary(g2_rows(doc["frames"], doc["session"]))}  # fmt: skip
    return {"what": "O.6: the join rule's G2 per session (median |dx|, |dy| <= 3 px on >= 30 "
                    "clear fits)", "checked_at": olf.now_ict(), "commit": olf.git_head(),
            "per_session": per}  # fmt: skip


# --- T2-items (O.5) and the evaluation's pack (O.9) ----------------------------------------------


def pool_labels(docs: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """PURE: every kept item label of the label files, with its stratum and frame reference."""
    out = []
    for doc in docs:
        for f in doc["frames"]:
            if f["status"] != "keep":
                continue
            for it in f["items"]:
                out.append({"session": doc["session"], "split": doc["split"],
                            "frame_id": f["frame_id"], "t": f["t"], "shard": f["shard"],
                            "offset": f["offset"], "size": f["size"], "floor_id": it["floor_id"],
                            "item_id": it["item_id"], "box": it["box"], "rel": it.get("rel"),
                            "under": it.get("under"), "ncc": it["ncc"],
                            "stratum": stratum_of(it)})  # fmt: skip
    return out


def check_pack_docs(spec: FiSpec, docs: Sequence[Mapping[str, Any]], eval_test: bool,
                    params_sha: str) -> None:  # fmt: skip
    """O.5 / O.9: T2-items pools FIT (val) + TRAIN label files; the evaluation's pack pools the
    held-out's ``--eval-test`` label files only; one frozen params file for all."""
    for doc in docs:
        sid = str(doc["session"])
        if doc.get("rule") != spec.rule or doc.get("params_sha256") != params_sha:
            raise SystemExit(f"{sid}: not {spec.rule} labels under the given frozen params")
        if eval_test:
            if doc.get("eval_test") is not True or role_refusal(spec, sid, None, True):
                raise SystemExit(f"{sid}: the evaluation's pack takes --eval-test fiT labels only")
        else:
            why = role_refusal(spec, sid, doc.get("split"), False)
            if doc.get("eval_test") or why is not None:
                raise SystemExit(f"{sid}: not in T2-items' pool ({why or 'evaluation labels'})")


def _open(sid: str, spec: FiSpec, layout: Path, cache: dict[str, ml.RecSession]
          ) -> ml.RecSession:  # fmt: skip
    if sid not in cache:
        cache[sid] = ml.RecSession.open(str(NAS / sid), spec.mspec, layout)
    return cache[sid]


def _ref(sess: ml.RecSession, row: Mapping[str, Any]) -> qa_export.JpegRef:
    return qa_export.JpegRef(int(row["frame_id"]), int(row["t"]), sess.path / str(row["shard"]),
                             int(row["offset"]), int(row["size"]))  # fmt: skip


def absent_points(docs: Sequence[Mapping[str, Any]], spec: FiSpec, prm: Mapping[str, Any],
                  sheets: FrozenSheets, sessions: dict[str, ml.RecSession], layout: Path,
                  n: int, rng: random.Random, fit: bool) -> list[dict[str, Any]]:  # fmt: skip
    """O.1e's absent points on the docs' KEPT frames (one per frame, frames in a seeded order):
    the box of a random drop sprite of the map at a random sub-cell of an absent cell, inside
    the frame (>= 30 px from the UI and the edge), clear of our self box, our bar and every unit
    box. ``fit``: also its best colour fit (the HARD negatives' score) and the fitted box."""
    frames = [(str(doc["session"]), str(doc["split"]), f) for doc in docs for f in doc["frames"]
              if f["status"] == "keep"]  # fmt: skip
    frames.sort(key=lambda x: (x[0], int(x[2]["frame_id"])))
    rng.shuffle(frames)
    ids = sorted(sheets.sheets)  # the labelled ids (v1: every sprited id; v2: not the excluded)
    off = int(float(prm["offset_ms"]) * 1e6)
    out: list[dict[str, Any]] = []
    for sid, split, f in frames:
        if len(out) >= n:
            break
        sess = _open(sid, spec, layout, sessions)
        t = int(f["t"])
        tw = t - off
        world = sess.lab.timeline.frame_world(tw)
        scene = sess.scene(world)
        if scene is None or world.self_pos is None:
            continue
        floors = il.floor_items(sess.lab.timeline.events)
        live = [(fl.x, fl.y) for fl in floors if fl.t_a - NEG_ITEM_SPAN_NS <= t
                < fl.t_v + NEG_ITEM_SPAN_NS]  # fmt: skip
        ucells = [(float(e.x), float(e.y)) for e in world.entities
                  if e.objtype in occ.UNIT_OBJTYPES and not e.hidden]  # fmt: skip
        sp = world.self_pos
        c = absent_cell((float(sp[0]), float(sp[1])), live, ucells, rng)
        if c is None:
            continue
        iid = rng.choice(ids)
        sub = (rng.choice(SUBS), rng.choice(SUBS))
        cell = (c[0] + gi.OX[sub[0]], c[1] + gi.OY[sub[1]])
        sheet = sheets(iid)
        p = None if sheet is None else _predict(sheet, cell, scene, prm)
        if p is None or sheet is None:
            continue
        me = anchor_and_depth(scene, scene.player)[0]
        units = _units(sess, world, scene, tw)
        b = p.box
        if not gi.inside(b, sess.lab.size, sess.lab.ui_rects, MARGIN_PX) or \
                gi.overlaps(b, gi.self_box(me)) or gi.overlaps(b, gi.at(me, tuple(prm["bar_px"]))) \
                or any(gi.overlaps(b, gi.at(u, gi.UNIT_BOX)) for u in units):  # fmt: skip
            continue
        row: dict[str, Any] = {"session": sid, "split": split, "frame_id": f["frame_id"],
                               "t": t, "shard": f["shard"], "offset": f["offset"],
                               "size": f["size"], "floor_id": None, "item_id": None,
                               "sprite_of": iid, "cell": list(c), "box": [round(x, 1) for x in b],
                               "under": occl_under(spec, scene, b, cell)}  # fmt: skip
        if fit:
            bgr = ml.read_png(_ref(sess, f))
            fr = colour_fit(bgr, olf.valid_map(sess.lab.size, sess.lab.ui_rects), sheet, p,
                            int(prm["r_label"]))  # fmt: skip
            if fr is None:
                continue
            row.update({"ncc": fr[0], "dx": fr[1], "dy": fr[2],
                        "box": [round(b[0] + fr[1], 1), round(b[1] + fr[2], 1),
                                round(b[2] + fr[1], 1), round(b[3] + fr[2], 1)]})  # fmt: skip
        out.append(row)
    return out


_OCCL: dict[str, olf.Occluders] = {}


def occl_under(spec: FiSpec, scene: Any, box: Box, cell: tuple[float, float]) -> str | None:
    if spec.name not in _OCCL:
        _OCCL[spec.name] = ml.occluders(spec.mspec)
    return _OCCL[spec.name].under(scene, box, cell)


def reference_sheet(sheets: Mapping[int, SpriteSheet], scale: int = 3,
                    tiles: Sequence[tuple[int, int, int]] = (TILE_ORANGE, TILE_PALE)
                    ) -> tuple[npt.NDArray[np.uint8], int]:  # fmt: skip
    """O.5's reference.png: each DISTINCT floor sprite (its one frame; identical images once) at
    native size x ``scale``, once on each floor colour, side by side, in a grid; no names. Returns
    the image and the number of distinct sprites."""
    seen: set[tuple[tuple[int, ...], bytes]] = set()
    imgs = []
    for _iid, sh in sorted(sheets.items()):
        rgba = compose_frame(sh.spr, sh.act, 0, 0)[0]  # type: ignore[arg-type]
        k = (tuple(rgba.shape), np.ascontiguousarray(rgba).tobytes())
        if k in seen:
            continue
        seen.add(k)
        imgs.append(rgba)
    cell_w = max(x.shape[1] for x in imgs) * scale + 12
    cell_h = max(x.shape[0] for x in imgs) * scale + 12
    cols = 4
    rows = (len(imgs) + cols - 1) // cols
    canvas = np.full((rows * cell_h, cols * cell_w * len(tiles), 3), 90, np.uint8)
    for i, rgba in enumerate(imgs):
        r, c = divmod(i, cols)
        a = rgba[..., 3:4].astype(float) / 255.0
        for j, bg in enumerate(tiles):
            rgb = (rgba[..., :3] * a + np.array(bg, float) * (1 - a)).astype(np.uint8)
            big = np.repeat(np.repeat(rgb, scale, axis=0), scale, axis=1)
            y0 = r * cell_h
            x0 = (c * len(tiles) + j) * cell_w
            canvas[y0 + 2 : y0 + cell_h - 2, x0 + 2 : x0 + cell_w - 2] = np.array(bg, np.uint8)
            oy = y0 + (cell_h - big.shape[0]) // 2
            ox = x0 + (cell_w - big.shape[1]) // 2
            canvas[oy : oy + big.shape[0], ox : ox + big.shape[1]] = big
    return canvas, len(imgs)


def order_entries(entries: Sequence[Mapping[str, Any]], seed: int, salt: str
                  ) -> list[dict[str, Any]]:  # fmt: skip
    """PURE: the pack's ONE seeded order of every crop (items and E mixed)."""
    out = sorted((dict(e) for e in entries),
                 key=lambda e: (e["stratum"], e["session"], int(e["frame_id"]),
                                -1 if e.get("floor_id") is None else int(e["floor_id"]),
                                e.get("kind", "")))  # fmt: skip
    random.Random(f"{salt}:{seed}:order").shuffle(out)
    return out


def cmd_pack(a: argparse.Namespace) -> dict[str, Any]:
    from PIL import Image

    spec = FI_MAPS[a.map]
    want = spec.eval_seed if a.eval_test else spec.pack_seed
    if a.seed != want:
        raise SystemExit(f"--seed {a.seed}: the pre-registered seed is {want} "
                         f"({'O.9' if a.eval_test else 'O.5'})")  # fmt: skip
    raw = INSTRUCTIONS.read_bytes()
    if sha256_bytes(raw) != INSTRUCTIONS_SHA256:
        raise SystemExit(f"{INSTRUCTIONS}: not the pinned instructions ({INSTRUCTIONS_SHA256[:8]})")
    params_raw = a.params.read_bytes()
    prm = load_params(a.params, spec)
    docs = [json.loads(p.read_text()) for p in a.labels]
    check_pack_docs(spec, docs, a.eval_test, sha256_bytes(params_raw))
    sheets = frozen_sheets(prm)
    cands = pool_labels(docs)
    if a.eval_test:
        picks = draw_strata([{**c, "stratum": "X"} for c in cands], {"X": EVAL_ITEMS}, a.seed,
                            spec.salt)  # fmt: skip
        for p in picks:
            p["stratum"] = stratum_of(p)
    else:
        picks = draw_strata(cands, PACK_N, a.seed, spec.salt)
    sessions: dict[str, ml.RecSession] = {}
    rng = random.Random(f"{spec.salt}:{a.seed}:E")
    plain = absent_points(docs, spec, prm, sheets, sessions, a.layout_templates, PACK_E_PLAIN,
                          rng, fit=False)  # fmt: skip
    hard_docs = docs if a.eval_test else [d for d in docs if d["split"] == "train"]
    hard_pool = absent_points(hard_docs, spec, prm, sheets, sessions, a.layout_templates,
                              HARD_POOL, rng, fit=True)  # fmt: skip
    plain_keys = {(p["session"], int(p["frame_id"])) for p in plain}
    hard = hard_pick(
        [p for p in hard_pool if (p["session"], int(p["frame_id"])) not in plain_keys],
        (EVAL_E if a.eval_test else PACK_E_PLAIN + PACK_E_HARD) - len(plain),
    )
    entries = (
        [{**p, "truth": "item", "kind": "item"} for p in picks]
        + [{**p, "truth": "none", "stratum": "E", "kind": "plain"} for p in plain]
        + [{**p, "truth": "none", "stratum": "E", "kind": "hard"} for p in hard]
    )
    entries = order_entries(entries, a.seed, spec.salt)
    tag = "eval" if a.eval_test else "t2"
    root = a.pack_dir or FI / f"pack-{tag}-seed{a.seed}"
    keyd = a.key_dir or FI / f"key-{tag}-seed{a.seed}"
    for d in (root, keyd):
        if d.resolve().is_relative_to(ROOT):
            raise SystemExit(f"{d}: client pixels never go inside the repo")
        if d.exists() and any(d.iterdir()):
            raise SystemExit(f"{d} is not empty: a pack is built once")
        d.mkdir(parents=True, exist_ok=True)
    ref_img, n_sprites = reference_sheet(sheets.all)  # every floor sprite of the drop tables
    Image.fromarray(ref_img).save(root / "reference.png")
    (root / "instructions.txt").write_bytes(raw)
    key: dict[str, Any] = {"what": f"{'O.9' if a.eval_test else 'O.5'}: the answer key",
                           "rule": spec.rule, "seed": a.seed, "salt": spec.salt,
                           "eval_test": bool(a.eval_test),
                           "params_sha256": sha256_bytes(params_raw),
                           "instructions_sha256": INSTRUCTIONS_SHA256,
                           "reference_sha256": olf.sha256_file(root / "reference.png"),
                           "label_files": [{"file": str(p), "sha256": olf.sha256_file(p)}
                                           for p in a.labels], "crops": {}}  # fmt: skip
    for i, e in enumerate(entries, 1):
        cid = f"{i:03d}"
        sess = _open(e["session"], spec, a.layout_templates, sessions)
        rgb = np.ascontiguousarray(ml.read_png(_ref(sess, e))[:, :, 2::-1])
        Image.fromarray(il.crop_pair(rgb, e["box"])).save(root / f"crop-{cid}.png")
        key["crops"][cid] = {
            k: e.get(k)
            for k in (
                "truth",
                "stratum",
                "kind",
                "session",
                "frame_id",
                "floor_id",
                "item_id",
                "box",
                "rel",
                "under",
                "ncc",
                "sprite_of",
            )
        }
    (keyd / "answer_key.json").write_text(json.dumps(key, indent=1))
    by = Counter(e["stratum"] for e in entries)
    return {"what": key["what"], "pack": str(root), "key": str(keyd / "answer_key.json"),
            "crops": len(entries), "by_stratum": dict(sorted(by.items())),
            "items": len(picks), "e_plain": len(plain), "e_hard": len(hard),
            "hard_pool": len(hard_pool),
            "hard_ncc": [p["ncc"] for p in hard], "short": {
                s: n - by.get(s, 0) for s, n in ({"X": EVAL_ITEMS} if a.eval_test else PACK_N
                                                 ).items() if by.get(s, 0) < n},
            "pool": dict(Counter(c["stratum"] for c in cands)),
            "reference_sprites": n_sprites, "reference_sha256": key["reference_sha256"],
            "instructions_sha256": INSTRUCTIONS_SHA256, "built_at": olf.now_ict(),
            "commit": olf.git_head()}  # fmt: skip


def cmd_refs(a: argparse.Namespace) -> dict[str, Any]:
    """predict_dir's --refs for the evaluation: every judged frame (scene and layout read) and
    every I4 frame of the ``--eval-test`` label files, keyed ``<session>.<frame_id:09d>``, paths
    as the worker sees the NAS (``--container-root``)."""
    out: dict[str, Any] = {}
    for p in a.labels:
        doc = json.loads(p.read_text())
        if not doc.get("eval_test"):
            raise SystemExit(f"{p}: refs are for --eval-test label files only")
        sid = doc["session"]
        rows = [
            f for f in doc["frames"] if f["reasons"] not in (["no_scene"], ["ui_layout_mismatch"])
        ]
        rows += [k["i4"] for k in doc.get("kills", []) if k.get("i4")]
        for f in rows:
            out[f"{sid}.{int(f['frame_id']):09d}"] = {
                "path": f"{a.container_root.rstrip('/')}/{sid}/{f['shard']}",
                "offset": int(f["offset"]),
                "size": int(f["size"]),
            }
    a.refs_out.parent.mkdir(parents=True, exist_ok=True)
    a.refs_out.write_text(json.dumps(out, indent=0))
    return {
        "what": "predict_dir --refs for the evaluation",
        "refs": str(a.refs_out),
        "frames": len(out),
    }


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("freeze")
    p.add_argument("--map", default="xmas_dun02", choices=sorted(FI_MAPS))
    p.add_argument("--sprites", type=Path, default=None)
    p.add_argument("--resnames", type=Path, default=None)
    p.add_argument("--drops", type=Path, default=None)
    p.add_argument("--out", type=Path, default=None, help="default: the map's O.3 (g) path")
    p.add_argument("--report", type=Path, default=None)
    p = sub.add_parser("freeze-v2")
    p.add_argument("--map", default="xmas_dun02", choices=sorted(FI_MAPS))
    p.add_argument("--v1", type=Path, required=True, help="the v1 params (FROZEN)")
    p.add_argument("--labels", type=Path, nargs="+", required=True,
                   help="FIT p31 and DEV p38's label files under v1")  # fmt: skip
    p.add_argument("--layout-templates", type=Path, default=LAYOUT_TEMPLATES)
    p.add_argument("--out", type=Path, default=None, help="default: the map's params v2 path")
    p.add_argument("--report", type=Path, default=None)
    p = sub.add_parser("label")
    p.add_argument("part")
    p.add_argument("--map", default="xmas_dun02", choices=sorted(FI_MAPS))
    p.add_argument("--split", choices=("train", "val"), default=None)
    p.add_argument("--eval-test", action="store_true")
    p.add_argument("--model", type=Path, default=None)
    p.add_argument("--model-sha256", default=None)
    p.add_argument("--params", type=Path, required=True)
    p.add_argument("--workers", type=int, default=1)
    p.add_argument("--layout-templates", type=Path, default=LAYOUT_TEMPLATES)
    p.add_argument("--out", type=Path, required=True)
    p = sub.add_parser("g2")
    p.add_argument("labels", type=Path, nargs="+")
    p.add_argument("--out", type=Path, required=True)
    p = sub.add_parser("pack")
    p.add_argument("labels", type=Path, nargs="+")
    p.add_argument("--map", default="xmas_dun02", choices=sorted(FI_MAPS))
    p.add_argument("--params", type=Path, required=True)
    p.add_argument("--seed", type=int, required=True)
    p.add_argument("--eval-test", action="store_true")
    p.add_argument("--pack-dir", type=Path, default=None)
    p.add_argument("--key-dir", type=Path, default=None)
    p.add_argument("--layout-templates", type=Path, default=LAYOUT_TEMPLATES)
    p.add_argument("--out", type=Path, required=True)
    p = sub.add_parser("refs")
    p.add_argument("labels", type=Path, nargs="+")
    p.add_argument("--container-root", default="/datasets")
    p.add_argument("--refs-out", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    a = ap.parse_args(argv)
    if a.cmd == "label" and not a.eval_test and a.split is None:
        raise SystemExit("label: --split train|val, or --eval-test")
    if a.cmd == "label" and a.eval_test and a.split is not None:
        raise SystemExit("label: --eval-test has no --split")
    out = {"freeze": cmd_freeze, "freeze-v2": cmd_freeze_v2, "label": cmd_label, "g2": cmd_g2,
           "pack": cmd_pack, "refs": cmd_refs}[a.cmd](a)  # fmt: skip
    dest = a.report if a.cmd in ("freeze", "freeze-v2") else a.out
    if dest is not None:
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(json.dumps(out) + "\n")
    summary = {k: v for k, v in out.items() if k != "frames"}
    print(json.dumps(summary, indent=1)[:8000])
    return 0


if __name__ == "__main__":
    sys.exit(main())
