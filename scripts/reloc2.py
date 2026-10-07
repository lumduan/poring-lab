#!/usr/bin/env python3
"""Re-localisation v2 (docs/demonstrations.md 3.11, relocalise@2): the structure probes WITHOUT
the flatness rule.

v1 (walk5.relocalise) only probes a screen offset whose cells are at the SAME altitude for every
candidate, so that one pixel means the same cell for all of them. Among prt_church's pews (+5 GAT
strips) no such offset exists for most beliefs: relocalise@1 ended attempt after attempt with ZERO
probes, and walk@6 indoors declined 10 routes on it.

v2 makes the altitude the EVIDENCE instead of the obstacle. For every candidate true cell c and
every probe pixel p it PREDICTS what the client will draw, from c's own terrain:
- the hovered cell H(c, p): among the cells around the flat guess, the one whose projected centre
  (at its GAT altitude relative to c) is nearest to p;
- H blocked -> the no-entry sign; H walkable -> the chevrons at H's projected corner anchors
  (rule_run.MARKER_ANCHORS, at H's altitude relative to c) -- a pew moves them by a whole cell.
Each probe goes to the pixel whose predictions split the candidates best (the smallest largest
group). The observation keeps the consistent candidates: chevrons -> the candidates predicting
chevrons within MAX_ANCHOR_FRAC of a cell of the observed ones AND within REL_MARGIN_PX of the best
fit (a pew's height and the next row alias to ~13.5 px on the indoor camera, inside the absolute
tolerance); no-entry -> those predicting a blocked cell; nothing -> no information. The
candidates are the belief +-3 from the start; a unique survivor is the new belief. Ambiguous after
PROBES (or a true alias), or no survivor -> it fails: never a guess.
Pixels in, input out.
"""

from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path
from typing import Any

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ro_agent as r  # noqa: E402
import rule_run as rr  # noqa: E402
import walk5 as w5  # noqa: E402

RADIUS = 3  # candidates: the belief +-3 from the START. Widening only after "nobody fits" was
#             unsafe: a truth just outside a +-2 set left ONE WRONG survivor (test_reloc2).
PROBES = 12
OFFSETS = [(dx, dy) for dy in range(-5, 6) for dx in range(-6, 7) if max(abs(dx), abs(dy)) >= 2]
REL_MARGIN_PX = 6.0  # a chevron fit this much worse than the best one is eliminated (unmeasured:
#                      relocalise@2's WRONG count is its test). Why: on the indoor camera a pew's
#                      +5 lifts the chevrons 36 px while the next diagonal row is 49.5 px up, so the
#                      nearest-cell choice leaves only ~13.5 px -- inside the absolute tolerance
#                      (MAX_ANCHOR_FRAC 0.35 of a 42.6 px cell = 14.9 px).
BUCKET_PX = REL_MARGIN_PX  # predictions closer than this are one outcome when choosing a probe


def candidates(w: w5.World, centre: tuple[int, int], radius: int) -> list[tuple[int, int]]:
    cx, cy = centre
    out = []
    for dy in range(-radius, radius + 1):
        for dx in range(-radius, radius + 1):
            x, y = cx + dx, cy + dy
            if 0 <= y < w.walkable.shape[0] and 0 <= x < w.walkable.shape[1] and w.walkable[y, x]:
                out.append((x, y))
    return out


def predict(w: w5.World, c: tuple[int, int], o: tuple[int, int],
            p: tuple[float, float]) -> tuple[str, Any]:  # fmt: skip
    """What hovering client pixel p shows if we truly stand on c: ("blocked", H) or
    ("walk", (H, the 4 projected corner anchors))."""
    rels = np.array([(o[0] + dx, o[1] + dy) for dy in (-1, 0, 1) for dx in (-1, 0, 1)],
                    dtype=float)  # fmt: skip
    alt = w.gat.relative_altitude(c, rels)
    centres = w.camera.project(rels, alt)
    k = int(np.argmin(np.linalg.norm(centres - np.asarray(p), axis=1)))
    rel = rels[k]
    h = (c[0] + int(rel[0]), c[1] + int(rel[1]))
    if not (0 <= h[1] < w.walkable.shape[0] and 0 <= h[0] < w.walkable.shape[1]):
        return "blocked", h
    if not w.walkable[h[1], h[0]]:
        return "blocked", h
    corners = rel + np.asarray(rr.MARKER_ANCHORS)
    anchors = w.camera.project(corners, np.repeat(alt[k : k + 1], 4))
    return "walk", (h, anchors)


def spacing(w: w5.World) -> float:
    a = w.camera.project(np.array([(0.0, 0.0), (1.0, 0.0)]), None)
    return float(np.linalg.norm(a[1] - a[0])) or 1.0


def fit_px(observed: Any, anchors: Any) -> float:
    """identify_cell's measure: the mean distance of each chevron to its nearest anchor (px)."""
    pts = np.asarray(observed, dtype=float)
    if len(pts) == 0:
        return float("inf")
    return float(np.mean(np.linalg.norm(pts[:, None, :] - anchors[None, :, :], axis=2).min(axis=1)))


def keep_fitting(observed: Any, preds: dict[Any, Any], cands: list[Any],
                 cell_px: float) -> list[Any]:  # fmt: skip
    """The candidates predicting chevrons that fit: within the absolute tolerance AND within
    REL_MARGIN_PX of the best fit."""
    d = {c: fit_px(observed, preds[c][1][1]) for c in cands if preds[c][0] == "walk"}
    if not d:
        return []
    best = min(d.values())
    return [c for c, x in d.items()
            if x / cell_px <= rr.MAX_ANCHOR_FRAC and x <= best + REL_MARGIN_PX]  # fmt: skip


def signature(pred: tuple[str, Any]) -> tuple[Any, ...]:
    if pred[0] == "blocked":
        return ("blocked",)
    c = np.asarray(pred[1][1]).mean(axis=0)
    return ("walk", round(float(c[0]) / BUCKET_PX), round(float(c[1]) / BUCKET_PX))


Pick = tuple[tuple[int, int], dict[Any, Any]]


def choose(w: w5.World, cands: list[tuple[int, int]], pixels: dict[tuple[int, int], Any],
           tried: set[tuple[int, int]]) -> Pick | None:  # fmt: skip
    """The untried offset whose predicted outcomes leave the smallest largest group."""
    best: tuple[int, tuple[int, int], dict[Any, Any]] | None = None
    for o, p in pixels.items():
        if o in tried:
            continue
        preds = {c: predict(w, c, o, p) for c in cands}
        groups = Counter(signature(v) for v in preds.values())
        worst = max(groups.values())
        if worst < len(cands) and (best is None or worst < best[0]):
            best = (worst, o, preds)
    return None if best is None else (best[1], best[2])


def relocalise(agent: r.Agent, screen: r.Screen, w: w5.World, mask: Any,
               band: tuple[int, int, int, int]) -> dict[str, Any]:  # fmt: skip
    """v2: walk5.relocalise's interface ({"ok", "from"/"to" | "left", "probes"})."""
    x0, y0, x1, y1 = band
    pixels: dict[tuple[int, int], Any] = {}
    for o in OFFSETS:
        u, v = w.camera.project(np.array([o], dtype=float), None)[0]
        if x0 <= u <= x1 and y0 <= v <= y1:
            pixels[o] = (float(u), float(v))
    cell_px = spacing(w)
    belief = w.position
    probes: list[dict[str, Any]] = []
    tried: set[tuple[int, int]] = set()
    cands = candidates(w, belief, RADIUS)
    while len(cands) > 1 and len(probes) < PROBES:
        pick = choose(w, cands, pixels, tried)
        if pick is None:
            break  # what is left looks the same from every probe in reach: a true alias
        o, preds = pick
        tried.add(o)
        u, v = pixels[o]
        p = w5.probe(agent, screen, u, v, mask)
        kind = w5.classify(p)
        before = len(cands)
        if kind == "chevrons":
            cands = keep_fitting(p["comps"], preds, cands, cell_px)
        elif kind == "noentry":
            cands = [c for c in cands if preds[c][0] == "blocked"]
        probes.append({"offset": list(o), "kind": kind, "candidates": before,
                       "left": len(cands)})  # fmt: skip
    if len(cands) == 1:
        w.position = cands[0]
        return {"ok": True, "from": list(belief), "to": list(cands[0]), "probes": probes,
                "method": "v2"}  # fmt: skip
    return {"ok": False, "left": len(cands), "probes": probes, "method": "v2"}  # never a guess
