#!/usr/bin/env python3
"""Phase 3 M4, the analysis: does the sprite render rule predict what the client draws?
(docs/phase3-plan.md §5; the session is recorded by scripts/m4_spawns.py + record_session.py.)

    m4_validate.py SESSION EVENTS.jsonl [--datasets DIR] [--every 5] [--out data/bench/m4/...]
                   [--rows ROWS.jsonl]   every measured frame (for diagnosis; local data/ only)

Per standing monster frame (the spawned species' block id from the packets, its Timeline state
`idle` for >= 1 s, no other actor within 120 px of it):
- PREDICTED: predict_sprite at its cell, heading and the idle action (envelope: the idle loop's
  phase is unknown), from the scene camera at our own cell, k = K_NOSTALRO.
- OBSERVED, independent of the predictor: the pixels that differ (any channel > 24) from the
  block's background clip (the same camera, no monster), opened by 1 px, and the connected
  component containing the predicted anchor's column; its tight box.

Reported per condition (scene outdoor/indoor x the anchor's screen third) and per A/A block:
IoU, the four edge errors, and the scale ratio observed/predicted. The pre-registered thresholds
(§5) are applied to OPAQUE predictions only. While every monster SPR is MIXCRYPT (M1), the
prediction is the ACT's QUAD box (transparent margins included), so IoU/edge verdicts are
reported as not comparable; the ratio tests (top/bottom, indoor/outdoor) and k are valid because a
constant margin ratio cancels in a ratio of ratios.

The re-run (phase3-plan §5b, pre-registered 2026-10-05 BEFORE its session):
- the background is LOCAL: the last background gap before the spawn, and only frames where the GM
  stands on the cell it stood on during that gap (far spawns warp the GM away and back);
- --exclude-merged drops a frame whose observed component touches the ROI border or the screen
  edge, covers a UI window, is larger than 1.5x the predicted envelope, or (indoor) stands on a
  cell that fails m4_cells' occluder proxy;
- conditions are scene/third/SPECIES, each needing >= 5 spawns and >= 20 frames; the ratio tests run
  per species; the A/A compares odd vs even spawns of each condition (pass within 3 %);
- k: per frame, the observed height / (f/z) divided by the median native height of the species'
  idle frames (the unknown idle phase cancels in the medians); the median over all clean frames is
  the ONE scalar, judged against 0.1333 and 0.140 (within 2 %). The width version is reported.
"""

from __future__ import annotations

import argparse
import gzip
import json
import statistics
import sys
from collections import deque
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import numpy.typing as npt

sys.path.insert(0, str(Path(__file__).resolve().parent))
import m4_cells  # noqa: E402
import qa_export  # noqa: E402

from poring_dataset import mapcache  # noqa: E402
from poring_dataset.h264 import H264Session  # noqa: E402
from poring_dataset.projection import camera_file  # noqa: E402
from poring_dataset.render import (  # noqa: E402
    K_NOSTALRO,
    Actor,
    MonsterAction,
    SpriteSheet,
    anchor_and_depth,
    load_scene,
    predict_sprite,
)
from poring_dataset.shards import read_shard  # noqa: E402
from poring_dataset.sprites import parse_act, parse_spr  # noqa: E402
from poring_dataset.timeline import Timeline  # noqa: E402
from poring_dataset.ui_layout import covered_fraction  # noqa: E402

NAS = Path("/mnt/poring-lab-datasets")
ACT_DIR = Path("/dev/shm/poring-lab-tmp/sprites/data/sprite/몬스터")  # sprite_catalog.py --work
JOB = {"poring": 1002, "lunatic": 1063, "drops": 1113, "pupa": 1008}
DIFF = 24
ROI_PAD = 40
CLEAR_PX = 120
Img = npt.NDArray[np.uint8]
Box = tuple[float, float, float, float]

# the pre-registered thresholds (phase3-plan §5), for OPAQUE predictions
IOU_MEDIAN, IOU_P10 = 0.85, 0.70
EDGE_MEDIAN, EDGE_P95 = 2.0, 4.0
RATIO_TOL = 0.03
K_TOL = 0.02
K_PRIORS = {"nostalro": 0.1333, "korangar": 0.140}
MIN_SPAWNS, MIN_FRAMES = 5, 20
MERGED_AREA = 1.5
GAME_W, GAME_H = 1280, 720


def changed_mask(frame: Img, background: Img) -> npt.NDArray[np.bool_]:
    diff = np.abs(frame.astype(np.int16) - background.astype(np.int16)).max(axis=2)
    return diff > DIFF  # type: ignore[no-any-return]


def opened(mask: npt.NDArray[np.bool_]) -> npt.NDArray[np.bool_]:
    """A 1 px morphological opening (3x3 erosion, then dilation), numpy only."""

    def shifts(m: npt.NDArray[np.bool_], op: Any) -> npt.NDArray[np.bool_]:
        p = np.pad(m, 1, constant_values=op is np.logical_or)
        out = p[1:-1, 1:-1].copy()
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                out = op(out, p[1 + dy : p.shape[0] - 1 + dy, 1 + dx : p.shape[1] - 1 + dx])
        return out

    eroded = shifts(mask, np.logical_and)
    p = np.pad(eroded, 1, constant_values=False)
    out = eroded.copy()
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            out |= p[1 + dy : p.shape[0] - 1 + dy, 1 + dx : p.shape[1] - 1 + dx]
    return out


def component_box(mask: npt.NDArray[np.bool_], seed_x: int) -> tuple[int, int, int, int] | None:
    """The tight box (x0, y0, x1, y1, exclusive ends) of the connected component (8-neighbour)
    that crosses column ``seed_x`` with the most pixels; None when that column is empty."""
    h, w = mask.shape
    if not 0 <= seed_x < w:
        return None
    seen = np.zeros_like(mask)
    best: tuple[int, tuple[int, int, int, int]] | None = None
    for sy in np.flatnonzero(mask[:, seed_x]):
        if seen[sy, seed_x]:
            continue
        q = deque([(int(sy), seed_x)])
        seen[sy, seed_x] = True
        n, x0, y0, x1, y1 = 0, w, h, -1, -1
        while q:
            y, x = q.popleft()
            n += 1
            x0, y0, x1, y1 = min(x0, x), min(y0, y), max(x1, x), max(y1, y)
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    yy, xx = y + dy, x + dx
                    if 0 <= yy < h and 0 <= xx < w and mask[yy, xx] and not seen[yy, xx]:
                        seen[yy, xx] = True
                        q.append((yy, xx))
        if best is None or n > best[0]:
            best = (n, (x0, y0, x1 + 1, y1 + 1))
    return None if best is None else best[1]


def observed_box(frame: Img, background: Img, predicted: Box, anchor_x: float) -> Box | None:
    h, w = frame.shape[:2]
    x0 = max(0, int(predicted[0]) - ROI_PAD)
    y0 = max(0, int(predicted[1]) - ROI_PAD)
    x1 = min(w, int(predicted[2]) + ROI_PAD + 1)
    y1 = min(h, int(predicted[3]) + ROI_PAD + 1)
    mask = opened(changed_mask(frame[y0:y1, x0:x1], background[y0:y1, x0:x1]))
    box = component_box(mask, int(round(anchor_x)) - x0)
    if box is None:
        return None
    return (box[0] + x0, box[1] + y0, box[2] + x0, box[3] + y0)


def iou(a: Box, b: Box) -> float:
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union > 0 else 0.0


def pct(values: list[float], q: float) -> float:
    s = sorted(values)
    return s[min(len(s) - 1, max(0, int(round(q * (len(s) - 1)))))] if s else float("nan")


def third(y: float) -> str:
    return "top" if y < 240 else "bottom" if y >= 480 else "centre"


def windows(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Spawn windows and background clips from m4_spawns.py's timeline."""
    out: list[dict[str, Any]] = []
    background: dict[str, list[tuple[int, int]]] = {}
    open_bg: dict[str, int] = {}
    spawn: dict[str, Any] | None = None
    for e in events:
        block, t = e["block"], int(e["t_mono_ns"])
        if e["event"] == "background_start":
            open_bg[block] = t
        elif e["event"] == "background_end" and block in open_bg:
            background.setdefault(block, []).append((open_bg.pop(block), t))
        elif e["event"] == "spawned":
            spawn = {"block": block, "scene": e["scene"], "species": e["species"], "t0": t,
                     "cell": e.get("cell")}  # fmt: skip
        elif e["event"] == "killed" and spawn is not None:
            spawn["t1"] = t
            out.append(spawn)
            spawn = None
            open_bg[block] = t  # the gap after a kill is background too
    index: dict[tuple[str, str, str], int] = {}
    for w in out:
        w["background"] = background.get(w["block"], [])
        # the LOCAL background: the last gap that ended before this spawn (the re-run, §5b)
        before = [g for g in w["background"] if g[1] <= w["t0"]]
        w["background_local"] = before[-1:] or w["background"][:1]
        key = (w["scene"], w["block"].split("-")[1] if "-" in w["block"] else "", w["species"])
        w["spawn_index"] = index.get(key, 0)
        index[key] = w["spawn_index"] + 1
    return out


class PngSession:
    """A PNG-shard session (RDP mode records PNG, 1 fps) with the slice of H264Session's interface
    measure() uses (2026-10-05: the Thai-data experiment's sprite fidelity runs in RDP mode)."""

    def __init__(self, session: Path, manifest: dict[str, Any]) -> None:
        self._frames: dict[int, tuple[dict[str, Any], npt.NDArray[np.uint8]]] = {}
        self.units: list[Any] = []
        for shard in manifest["shards"]:
            for meta, img in read_shard(session / shard):
                fid = int(meta["frame_id"])
                self._frames[fid] = (meta, img)
                self.units.append(_Unit(int(meta["t_mono_ns"]), fid))

    def usable(self) -> list[int]:
        return [u.frame_id for u in self.units]

    def frames(
        self, ids: list[int], verify: bool = False
    ) -> Iterator[tuple[dict[str, Any], npt.NDArray[np.uint8]]]:
        for fid in ids:
            yield self._frames[fid]


@dataclass(frozen=True)
class _Unit:
    t_ns: int
    frame_id: int


def sprite_sheet(species: str, use_spr: bool) -> SpriteSheet:
    """The species' ACT, plus its decoded SPR when asked and present (2026-10-05: the MIXCRYPT
    study decoder made them; sprite_catalog.py --decode-mixcrypt writes them to ACT_DIR): OPAQUE
    boxes instead of the ACT's quad boxes."""
    act = parse_act((ACT_DIR / f"{species}.act").read_bytes())
    spr_path = ACT_DIR / f"{species}.spr"
    if use_spr and spr_path.exists():
        return SpriteSheet(act, parse_spr(spr_path.read_bytes()))
    return SpriteSheet(act)


def idle_ref(sheet: SpriteSheet, action_index: int) -> tuple[float, float] | None:
    """The median native (sprite px) height and width over the action's frames: the k reference.
    IDLE frames share one ACT delay, so the duration weighting is uniform."""
    ext = [sheet.extent(action_index, m) for m in range(sheet.motions(action_index))]
    boxes = [e for e in ext if e is not None]
    if not boxes:
        return None
    return (statistics.median(b[3] - b[1] for b in boxes),
            statistics.median(b[2] - b[0] for b in boxes))  # fmt: skip


def exclusion(obs: Box, pred: Box, roi: Box, indoor_occluded: bool) -> str | None:
    """The pre-registered merged/occluded exclusions (phase3-plan §5b); None: keep the frame."""
    if obs[0] <= roi[0] or obs[1] <= roi[1] or obs[2] >= roi[2] or obs[3] >= roi[3]:
        return "roi_edge"
    if obs[0] <= 0 or obs[1] <= 0 or obs[2] >= GAME_W or obs[3] >= GAME_H:
        return "screen_edge"
    if covered_fraction(obs) > 0:
        return "ui"
    area_o = (obs[2] - obs[0]) * (obs[3] - obs[1])
    area_p = (pred[2] - pred[0]) * (pred[3] - pred[1])
    if area_p > 0 and area_o > MERGED_AREA * area_p:
        return "merged_area"
    if indoor_occluded:
        return "occluder"
    return None


def roi_of(frame_shape: tuple[int, ...], predicted: Box) -> Box:
    h, w = frame_shape[:2]
    x0, y0 = max(0, int(predicted[0]) - ROI_PAD), max(0, int(predicted[1]) - ROI_PAD)
    x1, y1 = min(w, int(predicted[2]) + ROI_PAD + 1), min(h, int(predicted[3]) + ROI_PAD + 1)
    return (x0, y0, x1, y1)


def measure(  # noqa: PLR0915
    session: Path,
    events_path: Path,
    every: int,
    rows_out: Path | None = None,
    use_spr: bool = False,
    rerun: bool = False,
) -> dict[str, Any]:
    manifest = json.loads((session / "manifest.json").read_text())
    pk = session / ("packets.states.jsonl.gz" if (session / "packets.states.jsonl.gz").exists()
                    else "packets.jsonl.gz")  # fmt: skip
    grids = mapcache.load(prere=True)
    with gzip.open(pk, "rt") as fh:
        tl = Timeline([json.loads(line) for line in fh], grids)
    offset_ms, _ = qa_export.auto_offset_ms(manifest["config"])
    off = int(offset_ms * 1e6)
    camera = json.loads(camera_file(manifest["backend"]).read_text())
    stream: Any = (H264Session(session) if (manifest.get("format") or "png") == "h264"
                   else PngSession(session, manifest))  # fmt: skip
    by_t = [(u.t_ns, u.frame_id) for u in stream.units]
    usable = set(stream.usable())
    events = [json.loads(line) for line in events_path.read_text().splitlines() if line.strip()]
    sheets: dict[str, SpriteSheet] = {}
    rows: list[dict[str, Any]] = []
    skipped: dict[str, int] = {}
    for w in windows(events):
        species = str(w["species"])
        if species not in sheets:
            sheets[species] = sprite_sheet(species, use_spr)
        gaps = w["background_local"] if rerun else w["background"]
        bg_units = [(t, f) for t, f in by_t if any(a <= t <= b for a, b in gaps) and f in usable]
        if not bg_units:
            skipped["no_background"] = skipped.get("no_background", 0) + 1
            continue
        bg_imgs = [img for _, img in stream.frames([f for _, f in bg_units[-15:]], verify=False)]
        background = np.median(np.stack(bg_imgs), axis=0).astype(np.uint8)
        bg_world = tl.frame_world(bg_units[-1][0] - off)
        bg_self = None if bg_world.self_pos is None else tuple(round(v) for v in bg_world.self_pos)
        ids = [f for t, f in by_t if w["t0"] <= t <= w["t1"] and f in usable][::every]
        for meta, frame in stream.frames(ids, verify=False):
            t = int(meta["t_mono_ns"]) - off
            world = tl.frame_world(t)
            gids = [ent.gid for ent in world.entities if ent.job == JOB.get(species)]
            if len(gids) != 1 or world.self_pos is None or world.map is None:
                continue
            if rerun and tuple(round(v) for v in world.self_pos) != bg_self:
                skipped["viewpoint"] = skipped.get("viewpoint", 0) + 1
                continue
            gid = gids[0]
            st = tl.state(gid, t)
            if st is None or st.state != "idle" or st.since_ns is None or t - st.since_ns < 1e9:
                continue
            scene = load_scene(camera, world.map, world.self_pos)
            actor = Actor((float(st.x), float(st.y)), int(st.facing or 0), MonsterAction.IDLE)
            pred = predict_sprite(actor, sheets[species], scene, K_NOSTALRO)
            if pred is None:
                continue
            ax, ay = pred.anchor_px
            near = False  # another actor's anchor within CLEAR_PX would share the crop
            for o in tl.states(t):
                if o.gid != gid and o.job is not None:
                    (ox, oy), _ = anchor_and_depth(scene, (float(o.x), float(o.y)))
                    near |= abs(ox - ax) < CLEAR_PX and abs(oy - ay) < CLEAR_PX
            if near:
                continue
            obs = observed_box(frame, background, pred.box, ax)
            if obs is None:
                continue
            p = pred.box
            excluded = None
            if rerun:
                occl = False
                if w["scene"] == "indoor" and world.map in grids:
                    occl = m4_cells.occluded(scene, grids[world.map], (int(st.x), int(st.y)),
                                             list(p), 3)  # fmt: skip
                excluded = exclusion(obs, p, roi_of(frame.shape, p), occl)
            ref = idle_ref(sheets[species], pred.action_index)
            f_over_z = pred.scale / K_NOSTALRO
            row = {
                "block": w["block"], "scene": w["scene"], "species": species,
                "frame_id": meta["frame_id"], "third": third(ay), "box_kind": pred.box_kind,
                "iou": iou(p, obs), "edges": [abs(p[i] - obs[i]) for i in range(4)],
                "ratio_h": (obs[3] - obs[1]) / max(1e-6, p[3] - p[1]),
                "ratio_w": (obs[2] - obs[0]) / max(1e-6, p[2] - p[0]),
                "scale": pred.scale, "t_ns": t, "spawn": w["spawn_index"],
                "spawn_cell": w.get("cell"), "cell": [int(st.x), int(st.y)],
                "pred": [round(v, 1) for v in p], "obs": [round(v, 1) for v in obs],
                "excluded": excluded,
            }  # fmt: skip
            if ref is not None:
                row["k_h"] = (obs[3] - obs[1]) / f_over_z / ref[0]
                row["k_w"] = (obs[2] - obs[0]) / f_over_z / ref[1]
            rows.append(row)
    if rows_out is not None:
        rows_out.parent.mkdir(parents=True, exist_ok=True)
        rows_out.write_text("".join(json.dumps(r) + "\n" for r in rows))
    result = summarise([r for r in rows if not r.get("excluded")], per_species=rerun)
    if rerun:
        reasons: dict[str, int] = dict(skipped)
        for r in rows:
            if r.get("excluded"):
                reasons[r["excluded"]] = reasons.get(r["excluded"], 0) + 1
        result["excluded"] = reasons
    return result


def group_stats(rs: list[dict[str, Any]], opaque: bool) -> dict[str, Any]:
    ious = [r["iou"] for r in rs]
    edges = [e for r in rs for e in r["edges"]]
    g = {"n": len(rs), "spawns": len({(r["block"], r.get("spawn")) for r in rs}),
         "iou_median": round(statistics.median(ious), 3),
         "iou_p10": round(pct(ious, 0.10), 3),
         "edge_median_px": round(statistics.median(edges), 2),
         "edge_p95_px": round(pct(edges, 0.95), 2),
         "ratio_h_median": round(statistics.median(r["ratio_h"] for r in rs), 4)}  # fmt: skip
    if opaque:
        g["pass_iou"] = g["iou_median"] >= IOU_MEDIAN and g["iou_p10"] >= IOU_P10
        g["pass_edges"] = g["edge_median_px"] <= EDGE_MEDIAN and g["edge_p95_px"] <= EDGE_P95
    return g


def ratio_test(a: dict[str, Any] | None, b: dict[str, Any] | None) -> dict[str, Any] | None:
    if not a or not b:
        return None
    rel = a["ratio_h_median"] / b["ratio_h_median"]
    return {"ratio_of_ratios": round(rel, 4), "pass": abs(rel - 1) <= RATIO_TOL}


def k_verdict(rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    """ONE scalar over all clean frames (height; the width version is reported beside it)."""
    kh = [r["k_h"] for r in rows if "k_h" in r]
    if not kh:
        return None
    k = statistics.median(kh)
    within = [name for name, prior in K_PRIORS.items() if abs(k / prior - 1) <= K_TOL]
    return {"k": round(k, 4), "k_width": round(statistics.median(r["k_w"] for r in rows
                                                              if "k_w" in r), 4),
            "n": len(kh), "within_2pct_of": within, "pass": bool(within),
            "vs": {n: round(k / v - 1, 4) for n, v in K_PRIORS.items()}}  # fmt: skip


def summarise(rows: list[dict[str, Any]], per_species: bool = False) -> dict[str, Any]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for r in rows:
        groups.setdefault(f"{r['scene']}/{r['third']}", []).append(r)
        groups.setdefault(f"block:{r['block']}", []).append(r)
        if per_species:
            groups.setdefault(f"{r['scene']}/{r['third']}/{r['species']}", []).append(r)
    out: dict[str, Any] = {"frames": len(rows), "groups": {}}
    kinds = {r["box_kind"] for r in rows}
    opaque = kinds == {"opaque"}
    for name, rs in sorted(groups.items()):
        out["groups"][name] = group_stats(rs, opaque)
    out["box_kind"] = sorted(kinds)
    out["iou_edge_verdicts"] = "applied" if opaque else "not comparable: quad boxes (SPR MIXCRYPT)"
    gr = out["groups"]
    if not per_species:
        # the 2026-10-05 analysis, unchanged: species pooled
        for scene in ("outdoor", "indoor"):
            t = ratio_test(gr.get(f"{scene}/top"), gr.get(f"{scene}/bottom"))
            if t:
                out[f"{scene}_top_vs_bottom"] = t
        t = ratio_test(gr.get("indoor/centre"), gr.get("outdoor/centre"))
        if t:
            out["indoor_vs_outdoor"] = t
        a1, a2 = gr.get("block:outdoor-1"), gr.get("block:outdoor-2")
        if a1 and a2:
            out["aa_outdoor"] = {"ratio_h": [a1["ratio_h_median"], a2["ratio_h_median"]],
                                 "iou_median": [a1["iou_median"], a2["iou_median"]]}  # fmt: skip
        return out
    # the re-run (§5b): per species, minimum counts, the A/A halves, k
    species = sorted({r["species"] for r in rows})
    out["conditions"] = {}
    for name, g in gr.items():
        if name.count("/") == 2:
            g["enough"] = g["spawns"] >= MIN_SPAWNS and g["n"] >= MIN_FRAMES
            rs = groups[name]
            halves = [[r for r in rs if r.get("spawn", 0) % 2 == h] for h in (0, 1)]
            if all(halves):
                a, b = (statistics.median(r["ratio_h"] for r in hv) for hv in halves)
                g["aa"] = {"ratio_h": [round(a, 4), round(b, 4)],
                           "pass": abs(a / b - 1) <= RATIO_TOL}  # fmt: skip
            out["conditions"][name] = g
    for sp in species:
        for scene in ("outdoor", "indoor"):
            t = ratio_test(gr.get(f"{scene}/top/{sp}"), gr.get(f"{scene}/bottom/{sp}"))
            if t:
                out[f"{scene}_top_vs_bottom/{sp}"] = t
        t = ratio_test(gr.get(f"indoor/centre/{sp}"), gr.get(f"outdoor/centre/{sp}"))
        if t:
            out[f"indoor_vs_outdoor/{sp}"] = t
    out["k"] = k_verdict(rows)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("session")
    ap.add_argument("events", type=Path)
    ap.add_argument("--datasets", type=Path, default=NAS)
    ap.add_argument("--every", type=int, default=5)
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--rows", type=Path, default=None)
    ap.add_argument(
        "--opaque", action="store_true",
        help="use the decoded SPRs (OPAQUE boxes) where present; default: the ACT's quad boxes",
    )  # fmt: skip
    ap.add_argument(
        "--rerun", action="store_true",
        help="the §5b pre-registered rules: local background, same viewpoint, exclusions, per "
             "species, A/A halves, k",
    )  # fmt: skip
    a = ap.parse_args()
    result = measure(a.datasets / a.session, a.events, a.every, a.rows, a.opaque, a.rerun)
    text = json.dumps(result, indent=1)
    if a.out:
        a.out.parent.mkdir(parents=True, exist_ok=True)
        a.out.write_text(text + "\n")
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
