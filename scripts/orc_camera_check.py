#!/usr/bin/env python3
"""THE CAMERA CHECK on a warp-and-watch block (docs/planning/orcsdun01-detector.md section 3). The
bars were FIXED in that plan before the first block's frames were read: never tune them here.

    orc_camera_check.py SESSION_DIR [--kb DIR] [--every 5] [--offset-ms MS] [--max-frames N]
                        [--out JSON]

OFFLINE ONLY (ADR-0007: packets are ground truth for labels, never an agent input): the session's
packets, its JPEG shards (read-only, NAS) and the local KB / decoded sprites (/dev/shm). No GPU, no
client. JSON to stdout (and --out).

The frames read: every --every-th recorded frame inside a DWELL of the session's timeline
(events.jsonl dwell_start..dwell_end: the GM settled at its stand; --all-frames lifts it), outside
the GM-command windows. The labels checked are the STANDING monsters on the session's map
(orcsdun01):
- Timeline state ``idle`` for >= 1 s (its idle start >= 1 s back; an idle start never seen counts
  only when the unit was idle at the same cell 1 s earlier);
- no other unit (players, our own GM, NPCs, portals, monsters) whose projected anchor lies within
  120 px of its anchor;
- not under a UI window of the RECORDED layout, and inside the frame: the predicted box grown by
  the C2 search radius (16 px) touches neither a UI rectangle nor the frame's edge.

C1: label_check.score -- the masked NCC of the rendered sprite (predict_sprite at the projected
anchor, k 0.140: the v1 labels' k) against the frame, with M4's FIXED tau 0.092 (phase3-plan 5b).
A label below tau is ``occluded`` / ``ui_covered`` / ``bad_label`` (label_check.classify, the
layout's rectangles). PASS: bad_label < 2 % of the scored labels, POOLED (the M5 gate); reported
per species.

C2: the offset (dx, dy) within +-16 px of the projected anchor where the same masked NCC is best
(over the idle action's frames; an FFT correlation, identical to label_check.ncc at each offset).
PASS: per species with >= 20 standing labels, median |dx| and median |dy| <= 4 px for the ground
species (Orc Zombie 1153, Orc Skeleton 1152, White Plant 1082, Black Mushroom 1084) and <= 6 px
for the flyers (Familiar 1005, Steel Chonchon 1042, Drainliar 1111). A species under 20 labels
gets NO verdict (listed); any judged species failing fails C2.

COLOUR: the mean hue of the drawn Familiar vs Drainliar pixels (the frame under the rendered
sprite's opaque mask at its best offset, labels whose best NCC >= tau), the circular gap between
them, and the same for the rendered sprites (their ACT tint, unlit) as the reference.

Frames are handed to label_check in BGR, as M4's H.264 frames were when tau was fixed (its grey
weights are applied in that order); the hue reads true RGB. The JPEG q80 recording is lossy where
M4's frames were H.264: a caveat for C1, recorded in the output.
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
from collections import Counter, defaultdict
from collections.abc import Iterable, Sequence
from functools import lru_cache
from pathlib import Path
from typing import Any

import numpy as np
import numpy.typing as npt

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import label_check  # noqa: E402
import qa_export  # noqa: E402

from poring_dataset import gat as gatmod  # noqa: E402
from poring_dataset.camera import GAT_DIR, map_camera, map_key, projector_for  # noqa: E402
from poring_dataset.labels import in_windows  # noqa: E402
from poring_dataset.render import (  # noqa: E402
    Actor,
    MonsterAction,
    Scene,
    SpritePrediction,
    SpriteSheet,
    anchor_and_depth,
    predict_sprite,
)
from poring_dataset.sprites import compose_frame  # noqa: E402
from poring_dataset.timeline import ActorState, EntityState  # noqa: E402
from poring_dataset.ui_layout import covered_fraction  # noqa: E402

MAP = "orcsdun01"
K_V1 = 0.140  # the v1 labels' k (M4)
TAU_M4 = 0.092  # label_check's tau, fixed from M4's clean standing frames (phase3-plan 5b)
SEARCH_PX = 16
ISOLATION_PX = 120.0
STANDING_NS = 1_000_000_000
C1_MAX_BAD_SHARE = 0.02  # strictly below
C2_MIN_LABELS = 20
GROUND = (1153, 1152, 1082, 1084)
FLYERS = (1005, 1042, 1111)
C2_BAR_PX = {**{m: 4.0 for m in GROUND}, **{m: 6.0 for m in FLYERS}}
FAMILIAR, DRAINLIAR = 1005, 1111
UNIT_OBJTYPES = (0, 5, 6)  # player, monster, NPC (portals included: a drawn effect)
POSITIVE_PER_SPECIES = 3

Rect = tuple[float, float, float, float]
UiRects = tuple[tuple[int, int, int, int], ...]


# --- pure parts -------------------------------------------------------------------------------


def standing(cur: ActorState | None, prev: ActorState | None, min_ns: int = STANDING_NS) -> bool:
    """Idle for >= ``min_ns``: its idle start that long back, or (start never seen) idle at the
    same cell ``min_ns`` earlier too."""
    if cur is None or cur.state != "idle":
        return False
    if cur.since_ns is not None:
        return cur.t_ns - cur.since_ns >= min_ns
    return (prev is not None and prev.state == "idle" and prev.since_ns is None
            and (prev.x, prev.y) == (cur.x, cur.y))  # fmt: skip


def isolated(anchor: tuple[float, float], others: Iterable[tuple[float, float]],
             px: float = ISOLATION_PX) -> bool:  # fmt: skip
    """No other unit's anchor within ``px`` (Euclidean, screen px)."""
    return all(math.hypot(anchor[0] - o[0], anchor[1] - o[1]) > px for o in others)


def clear_box(box: Rect, rects: UiRects, size: tuple[int, int], margin: float = SEARCH_PX) -> bool:
    """The box grown by ``margin`` lies inside the frame and touches no UI rectangle."""
    g = (box[0] - margin, box[1] - margin, box[2] + margin, box[3] + margin)
    inside = g[0] >= 0 and g[1] >= 0 and g[2] <= size[0] and g[3] <= size[1]
    return inside and covered_fraction(g, rects) == 0.0


def shift_ncc(observed: npt.NDArray[np.float64], template: npt.NDArray[np.float64],
              mask: npt.NDArray[np.bool_], r: int) -> npt.NDArray[np.float64]:  # fmt: skip
    """Masked NCC (label_check.ncc's formula) of ``template`` under ``mask`` against every window
    of ``observed`` (the template's window grown by ``r`` px on each side): grid[r + dy, r + dx] is
    the score with the template drawn (dx, dy) px from its predicted place. NaN where undefined
    (fewer than label_check.MIN_PIXELS mask pixels, or a flat window)."""
    h, w = template.shape
    if observed.shape != (h + 2 * r, w + 2 * r):
        raise ValueError(f"observed {observed.shape} is not template {template.shape} + 2 x {r}")
    out = np.full((2 * r + 1, 2 * r + 1), np.nan)
    m = mask.astype(np.float64)
    n = float(m.sum())
    if n < label_check.MIN_PIXELS:
        return out
    tc = (template - float(template[mask].mean())) * m
    tt = float((tc * tc).sum())
    if tt == 0.0:
        return out
    spec = np.fft.rfft2(observed)
    spec2 = np.fft.rfft2(observed * observed)

    def corr(kernel: npt.NDArray[np.float64], f: npt.NDArray[np.complex128]) -> Any:
        k = np.fft.rfft2(kernel, s=observed.shape)
        return np.fft.irfft2(f * np.conj(k), s=observed.shape)[: 2 * r + 1, : 2 * r + 1]

    num, s1, s2 = corr(tc, spec), corr(m, spec), corr(m, spec2)
    var = s2 - s1 * s1 / n
    ok = var > 1e-9 * np.maximum(s2, 1.0)
    out[ok] = num[ok] / np.sqrt(tt * var[ok])
    return out


def best_offset(frame: npt.NDArray[np.uint8], sheet: SpriteSheet, pred: SpritePrediction,
                r: int = SEARCH_PX) -> tuple[float, int, int, int] | None:  # fmt: skip
    """(best NCC, dx, dy, motion) over the action's frames (the known one when the phase is
    known) and every offset within ``r``; None when nothing scores. The frame is in the order
    label_check scores (see the module doc)."""
    i0, j0 = math.floor(pred.box[0]), math.floor(pred.box[1])
    i1, j1 = math.ceil(pred.box[2]), math.ceil(pred.box[3])
    h, w = frame.shape[:2]
    if i0 - r < 0 or j0 - r < 0 or i1 + r > w or j1 + r > h or i1 - i0 < 2 or j1 - j0 < 2:
        return None
    observed = frame[j0 - r : j1 + r, i0 - r : i1 + r, :3].astype(float) @ label_check.GREY
    motions = [pred.motion] if pred.motion is not None else range(sheet.motions(pred.action_index))
    best: tuple[float, int, int, int] | None = None
    for mo in motions:
        grey, opaque = label_check.rendered(sheet, pred.action_index, int(mo), pred.anchor_px,
                                            pred.scale, (i0, j0, i1, j1))  # fmt: skip
        grid = shift_ncc(observed, grey, opaque, r)
        if np.isnan(grid).all():
            continue
        a, b = np.unravel_index(int(np.nanargmax(grid)), grid.shape)
        cand = (float(grid[a, b]), int(b) - r, int(a) - r, int(mo))
        if best is None or cand[0] > best[0]:
            best = cand
    return best


def drawn_pixels(frame_rgb: npt.NDArray[np.uint8], sheet: SpriteSheet, pred: SpritePrediction,
                 motion: int, dx: int, dy: int) -> npt.NDArray[np.uint8]:  # fmt: skip
    """The frame's RGB pixels under the rendered sprite's opaque mask, drawn (dx, dy) off."""
    i0, j0 = math.floor(pred.box[0]), math.floor(pred.box[1])
    i1, j1 = math.ceil(pred.box[2]), math.ceil(pred.box[3])
    _grey, opaque = label_check.rendered(sheet, pred.action_index, motion, pred.anchor_px,
                                         pred.scale, (i0, j0, i1, j1))  # fmt: skip
    win = frame_rgb[j0 + dy : j1 + dy, i0 + dx : i1 + dx, :3]
    if win.shape[:2] != opaque.shape:
        return np.zeros((0, 3), np.uint8)
    return np.asarray(win[opaque], np.uint8)


def hue_stats(rgb: npt.NDArray[Any]) -> dict[str, Any]:
    """The pixels' circular mean hue (degrees, weighted by saturation), mean saturation / value,
    the mean RGB and that mean's own hue."""
    px = np.asarray(rgb, float).reshape(-1, 3) / 255.0
    if not len(px):
        return {"n_px": 0}
    mx, mn = px.max(axis=1), px.min(axis=1)
    d = mx - mn
    r, g, b = px[:, 0], px[:, 1], px[:, 2]
    hue = np.zeros(len(px))
    nz = d > 0
    rr = nz & (mx == r)
    gg = nz & (mx == g) & ~rr
    bb = nz & ~rr & ~gg
    hue[rr] = 60.0 * (((g - b)[rr] / d[rr]) % 6.0)
    hue[gg] = 60.0 * ((b - r)[gg] / d[gg] + 2.0)
    hue[bb] = 60.0 * ((r - g)[bb] / d[bb] + 4.0)
    sat = np.where(mx > 0, d / np.where(mx > 0, mx, 1.0), 0.0)
    ang = np.radians(hue)
    sw = float(sat.sum())
    mean_h = (math.degrees(math.atan2(float((sat * np.sin(ang)).sum()),
                                      float((sat * np.cos(ang)).sum()))) % 360.0
              if sw > 0 else None)  # fmt: skip
    mean_rgb = (px.mean(axis=0) * 255.0).round(1)
    return {
        "n_px": len(px),
        "hue_deg": None if mean_h is None else round(mean_h, 1),
        "sat_mean": round(float(sat.mean()), 3),
        "val_mean": round(float(mx.mean()), 3),
        "rgb_mean": mean_rgb.tolist(),
        "hue_of_mean_rgb": hue_stats(mean_rgb[None, :])["hue_deg"] if len(px) > 1 else None,
    }


def hue_gap(a: float | None, b: float | None) -> float | None:
    """The circular distance between two hues (degrees, 0..180)."""
    if a is None or b is None:
        return None
    d = abs(a - b) % 360.0
    return round(min(d, 360.0 - d), 1)


def c1_summary(rows: Sequence[dict[str, Any]], tau: float) -> dict[str, Any]:
    scored = [r for r in rows if r["c1"] is not None]
    why = Counter(r["why_low"] for r in scored if r["c1"] < tau)
    bad = why.get("bad_label", 0)
    share = bad / len(scored) if scored else None
    vals = [r["c1"] for r in scored]
    return {"scored": len(scored), "low": sum(why.values()), "occluded": why.get("occluded", 0),
            "ui_covered": why.get("ui_covered", 0), "bad_label": bad,
            "bad_label_share": None if share is None else round(share, 4),
            "ncc_median": round(statistics.median(vals), 3) if vals else None,
            "ncc_p10": round(float(np.percentile(vals, 10)), 3) if vals else None}  # fmt: skip


def c2_summary(rows: Sequence[dict[str, Any]], mob: int) -> dict[str, Any]:
    offs = [r for r in rows if r.get("dx") is not None]
    bar = C2_BAR_PX.get(mob)
    out: dict[str, Any] = {"n": len(offs), "group": "ground" if mob in GROUND else
                           "flyer" if mob in FLYERS else "other", "bar_px": bar}  # fmt: skip
    if not offs:
        out["verdict"] = "NO_VERDICT"
        return out
    adx = statistics.median(abs(r["dx"]) for r in offs)
    ady = statistics.median(abs(r["dy"]) for r in offs)
    out.update({"median_abs_dx": adx, "median_abs_dy": ady,
                "median_dx": statistics.median(r["dx"] for r in offs),
                "median_dy": statistics.median(r["dy"] for r in offs),
                "best_ncc_median": round(statistics.median(r["best"] for r in offs), 3),
                })  # fmt: skip
    if bar is None or len(offs) < C2_MIN_LABELS:
        out["verdict"] = "NO_VERDICT"
    else:
        out["verdict"] = "PASS" if adx <= bar and ady <= bar else "FAIL"
    return out


def summarize(rows: Sequence[dict[str, Any]], tau: float) -> dict[str, Any]:
    """The bars (fixed in the plan) over the scored standing labels."""
    by: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        by[int(r["mob"])].append(r)
    pooled = c1_summary(rows, tau)
    share = pooled["bad_label_share"]
    c1_pass = share is not None and share < C1_MAX_BAD_SHARE
    c2 = {str(m): c2_summary(by[m], m) for m in sorted(by)}
    judged = {m: v for m, v in c2.items() if v["verdict"] != "NO_VERDICT"}
    c2_verdict = (
        "NO_VERDICT"
        if not judged
        else "FAIL"
        if any(v["verdict"] == "FAIL" for v in judged.values())
        else "PASS"
    )
    c1_verdict = "NO_VERDICT" if share is None else "PASS" if c1_pass else "FAIL"
    overall = (
        "FAIL"
        if "FAIL" in (c1_verdict, c2_verdict)
        else "PASS"
        if (c1_verdict, c2_verdict) == ("PASS", "PASS")
        else "NO_VERDICT"
    )
    return {
        "c1": {"bar": f"bad_label share < {C1_MAX_BAD_SHARE} pooled", "pooled": pooled,
               "verdict": c1_verdict,
               "per_species": {str(m): c1_summary(by[m], tau) for m in sorted(by)}},
        "c2": {"bar": f"median |dx|, |dy| <= 4 px ground {list(GROUND)}, <= 6 px flyers "
                      f"{list(FLYERS)}; species with >= {C2_MIN_LABELS} standing labels",
               "per_species": c2, "verdict": c2_verdict,
               "no_verdict": sorted(m for m, v in c2.items() if v["verdict"] == "NO_VERDICT"),
               "listed_species_without_labels": sorted(str(m) for m in (*GROUND, *FLYERS)
                                                       if m not in by)},
        "verdict": {"C1": c1_verdict, "C2": c2_verdict, "overall": overall},
    }  # fmt: skip


# --- the session ------------------------------------------------------------------------------


@lru_cache(maxsize=8)
def _gat(path: str) -> gatmod.Gat | None:
    p = Path(path)
    return gatmod.parse(p.read_bytes()) if p.exists() else None


def dwell_spans(events: Iterable[dict[str, Any]]) -> list[tuple[int, int]]:
    """[dwell_start, dwell_end] (host ns) of warp_watch's timeline (events.jsonl), paired by the
    dwell's ref: the GM settled at its stand, the frames the check reads."""
    starts: dict[Any, int] = {}
    spans = []
    for e in events:
        if e.get("event") == "dwell_start":
            starts[e.get("ref")] = int(e["t_mono_ns"])
        elif e.get("event") == "dwell_end" and e.get("ref") in starts:
            spans.append((starts.pop(e.get("ref")), int(e["t_mono_ns"])))
    return sorted(spans)


def scene_for(lab: Any, map_name: str, pos: tuple[float, float]) -> Scene:
    """render.load_scene's Scene, its GAT parsed once per map."""
    cam = map_camera(lab.camera, map_key(map_name), lab.indoor)
    if cam is None:
        raise SystemExit("the camera json has no fitted camera")
    return Scene(
        cam, (float(pos[0]), float(pos[1])), _gat(str(GAT_DIR / f"{map_key(map_name)}.gat"))
    )


def cache_compose() -> None:
    """label_check renders a motion per call: compose each (sheet, action, motion) once."""
    cache: dict[tuple[int, int, int, int], Any] = {}

    def composed(spr: Any, act: Any, action_index: int, motion: int) -> Any:
        key = (id(spr), id(act), action_index, motion)
        if key not in cache:
            cache[key] = compose_frame(spr, act, action_index, motion)
        return cache[key]

    label_check.compose_frame = composed  # type: ignore[attr-defined,assignment]


def reference_hue(sheet: SpriteSheet) -> dict[str, Any]:
    """The rendered idle sprite's own pixels (ACT tint applied, unlit): direction 0, frame 0."""
    if sheet.spr is None:
        return {"n_px": 0}
    rgba, _ = compose_frame(sheet.spr, sheet.act, sheet.act.action_index(MonsterAction.IDLE, 0), 0)
    return hue_stats(rgba[rgba[..., 3] > 0][:, :3])


def unit_anchor_others(world: Any, scene: Scene, gid: int) -> list[tuple[float, float]]:
    out = [anchor_and_depth(scene, scene.player)[0]]  # our own GM (the camera target)
    for e in world.entities:
        if e.gid == gid or e.objtype not in UNIT_OBJTYPES or e.hidden:
            continue
        out.append(anchor_and_depth(scene, (e.x, e.y))[0])
    return out


def other_boxes(world: Any, scene: Scene, gid: int, lab: Any, states: dict[int, ActorState],
                k: float) -> list[Rect]:  # fmt: skip
    """The other monsters' predicted boxes (label_check.classify's occluders)."""
    out: list[Rect] = []
    for e in world.entities:
        if e.gid == gid or e.objtype != 5 or e.hidden:
            continue
        sh = lab.sheets(e.job)
        st = states.get(e.gid)
        if sh is None:
            continue
        heading = st.facing if st is not None and st.facing is not None else (e.heading or 0)
        p = predict_sprite(Actor((float(e.x), float(e.y)), int(heading) % 8), sh, scene, k)
        if p is not None:
            out.append(p.box)
    return out


def check(session: Path, a: argparse.Namespace) -> dict[str, Any]:
    qa_export.KB_CLASSES = a.kb / "classes.json"
    qa_export.KB_SPRITE_NAMES = a.kb / "monster_sprite_names.json"
    manifest = json.loads((session / "manifest.json").read_text())
    if not qa_export.is_warp_watch(manifest):
        raise SystemExit(f"{session}: not a warp_watch session")
    offset = "auto" if a.offset_ms is None else str(a.offset_ms)
    lab = qa_export.Labeler(session, offset, labels="v1", k=a.k)
    assert lab.sheets is not None
    cache_compose()
    off = int(lab.offset_ms * 1e6)
    size = lab.size
    refs = qa_export.jpeg_index(session, manifest)
    frames: Counter[str] = Counter({"recorded": len(refs)})
    timeline = session / "events.jsonl"
    dwells = (dwell_spans(json.loads(x) for x in timeline.read_text().splitlines() if x)
              if a.dwells_only and timeline.exists() else None)  # fmt: skip
    dropped: Counter[str] = Counter()
    rows: list[dict[str, Any]] = []
    hue_px: dict[int, list[npt.NDArray[np.uint8]]] = defaultdict(list)
    seen_species: Counter[int] = Counter()
    for ref in refs[:: a.every][: a.max_frames or None]:
        frames["read"] += 1
        t = ref.t_mono_ns
        if dwells is not None and not in_windows(t, dwells):
            frames["outside_dwell"] += 1
            continue
        if in_windows(t, lab.windows):
            frames["gm_window"] += 1
            continue
        tw = t - off
        world = lab.timeline.frame_world(tw)
        if world.self_pos is None or not world.map:
            frames["no_world"] += 1
            continue
        if map_key(world.map) != MAP:
            frames["off_map"] += 1
            continue
        scene = scene_for(lab, world.map, world.self_pos)
        now = {s.gid: s for s in lab.timeline.states(tw)}
        prev = {s.gid: s for s in lab.timeline.states(tw - STANDING_NS)}
        cands: list[tuple[EntityState, SpriteSheet, SpritePrediction]] = []
        for e in world.entities:
            if e.objtype != 5 or e.hidden:
                continue
            seen_species[e.job] += 1
            st = now.get(e.gid)
            if not standing(st, prev.get(e.gid)):
                dropped["not_standing"] += 1
                continue
            assert st is not None
            sheet = lab.sheets(e.job)
            if sheet is None:
                dropped[f"no_sheet:{e.job}"] += 1
                continue
            heading = st.facing if st.facing is not None else (e.heading or 0)
            pred = predict_sprite(Actor((float(e.x), float(e.y)), int(heading) % 8,
                                        MonsterAction.IDLE), sheet, scene, a.k)  # fmt: skip
            if pred is None:
                dropped["draws_nothing"] += 1
                continue
            if not isolated(pred.anchor_px, unit_anchor_others(world, scene, e.gid)):
                dropped["crowded"] += 1
                continue
            if not clear_box(pred.box, lab.ui_rects, size):
                dropped["ui_or_edge"] += 1
                continue
            cands.append((e, sheet, pred))
        if not cands:
            continue
        frames["with_standing"] += 1
        bgr = qa_export.read_jpeg(ref)
        rgb = bgr[:, :, ::-1]
        for e, sheet, pred in cands:
            c1 = label_check.score(bgr, sheet, pred)
            if c1 is None:
                dropped["unscored"] += 1
                continue
            why = None
            if c1 < a.tau:
                others = other_boxes(world, scene, e.gid, lab, now, a.k)
                why = label_check.classify(pred.box, others, lab.ui_rects)
            bo = best_offset(bgr, sheet, pred)
            row: dict[str, Any] = {"frame_id": ref.frame_id, "t_ns": t, "gid": e.gid,
                                   "mob": e.job, "cell": [e.x, e.y],
                                   "box": [round(v, 1) for v in pred.box],
                                   "c1": round(c1, 4), "why_low": why}  # fmt: skip
            if bo is not None:
                row.update({"best": round(bo[0], 4), "dx": bo[1], "dy": bo[2], "motion": bo[3]})
                if e.job in (FAMILIAR, DRAINLIAR) and bo[0] >= a.tau:
                    hue_px[e.job].append(drawn_pixels(rgb, sheet, pred, bo[3], bo[1], bo[2]))
            rows.append(row)
    result = summarize(rows, a.tau)
    hue: dict[str, Any] = {}
    for mob in (FAMILIAR, DRAINLIAR):
        px = np.concatenate(hue_px[mob]) if hue_px[mob] else np.zeros((0, 3), np.uint8)
        sheet = lab.sheets(mob)
        hue[str(mob)] = {
            "labels": len(hue_px[mob]),
            "drawn": hue_stats(px),
            "rendered_reference": None if sheet is None else reference_hue(sheet),
        }
    hue["gap_deg_drawn"] = hue_gap(hue[str(FAMILIAR)]["drawn"].get("hue_deg"),
                                   hue[str(DRAINLIAR)]["drawn"].get("hue_deg"))  # fmt: skip
    ref_f = hue[str(FAMILIAR)]["rendered_reference"] or {}
    ref_d = hue[str(DRAINLIAR)]["rendered_reference"] or {}
    hue["gap_deg_rendered"] = hue_gap(ref_f.get("hue_deg"), ref_d.get("hue_deg"))
    positives = {}
    by: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        by[int(r["mob"])].append(r)
    keys = ("frame_id", "gid", "c1", "best", "dx", "dy", "box")
    low = {}
    for mob, rs in sorted(by.items()):
        top = sorted(rs, key=lambda r: -r["c1"])[:POSITIVE_PER_SPECIES]
        positives[str(mob)] = [{k: r.get(k) for k in keys} for r in top]
        bad = [r for r in rs if r.get("why_low") == "bad_label"]
        low[str(mob)] = [{k: r.get(k) for k in keys} for r in bad[:: max(1, len(bad) // 8)][:8]]
    _proj, which = projector_for(lab.camera, MAP, indoor_table=lab.indoor)
    return {
        "session": qa_export.session_id(manifest), "map": MAP, "projection": which,
        "camera": lab.camera_path.name, "k": a.k, "tau": a.tau, "offset_ms": lab.offset_ms,
        "offset_run": lab.offset_run, "every": a.every, "ui_layout": manifest.get("ui_layout"),
        "dwells": None if dwells is None else len(dwells),
        "standing_rule": {"idle_s": STANDING_NS / 1e9, "isolation_px": ISOLATION_PX,
                          "ui_and_edge_margin_px": SEARCH_PX},
        "frames": dict(frames), "dropped": dict(sorted(dropped.items())),
        "monsters_in_sight_by_species": {str(k): v for k, v in sorted(seen_species.items())},
        "standing_scored_by_species": {str(m): len(rs) for m, rs in sorted(by.items())},
        **result, "hue": hue, "positive_cases": positives, "bad_label_examples": low,
        "caveats": ["frames are JPEG q80 (warp_watch); M4 fixed tau on H.264 frames",
                    "label_check's grey weights are applied to BGR frames, as in M4"],
    }  # fmt: skip


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("session", type=Path)
    ap.add_argument("--kb", type=Path, default=ROOT / "data" / "kb")
    ap.add_argument("--every", type=int, default=5, help="every n-th recorded frame (5 Hz)")
    ap.add_argument("--k", type=float, default=K_V1)
    ap.add_argument("--tau", type=float, default=TAU_M4)
    ap.add_argument("--offset-ms", type=float, default=None)
    ap.add_argument("--max-frames", type=int, default=0)
    ap.add_argument(
        "--all-frames",
        dest="dwells_only",
        action="store_false",
        help="also the frames outside the timeline's dwells (default: dwells only, GM settled)",
    )
    ap.add_argument("--out", type=Path, default=None)
    a = ap.parse_args(argv)
    if a.k != K_V1 or a.tau != TAU_M4:
        print(f"WARNING: k {a.k} / tau {a.tau} differ from the plan's fixed {K_V1} / {TAU_M4}",
              file=sys.stderr)  # fmt: skip
    out = check(a.session, a)
    text = json.dumps(out, indent=1)
    if a.out:
        a.out.parent.mkdir(parents=True, exist_ok=True)
        a.out.write_text(text + "\n")
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
