#!/usr/bin/env python3
"""THE WHITE PLANT FINDER (Batt 2026-10-22 overnight brief, item B: "Batt also kills WHITE PLANT on
purpose: its White Herb sells well. Make sure the patrol passes White Plant spawn areas and that
white plants are engaged when seen (they don't move or attack: the detector or a SWORD read on
them)"). v1 sees White Plants 0-2 % zero-shot (orcsdun01-dungeon-prep.md 1), so the finder looks
for the plant's OWN sprite.

PIXELS IN: the client's White Plant sprite (SPR / ACT, decoded locally at run time like the GAT;
never committed) is rendered at each candidate cell by the camera model (render.predict_sprite)
and scored against the frame by masked NCC with a +-R px search (orc_camera_check.best_offset,
label_check's score). The candidate cells are the White Plant SPAWN AREAS of the map (static map
knowledge: rAthena's spawn lines in data/kb/spawns.json, local only), walkable, in view. Nothing
reads packets at decision time; a candidate is struck only where the cursor then reads SWORD.

    plant_finder.py calibrate SID [--every 5] [--neg 6]   OFFLINE, on a banked session: NCC at the
        plants' true cells (packets) against empty spawn-area cells, on frames where we stood

TAU (the score a candidate needs) is fixed from `calibrate` on Batt's demo before any run uses it.

RESULT 2026-10-22 ~19:3x ICT (Batt's demo, standing frames, packets as truth): NOT SEPARATING.
- R 6 px: the plants' true cells scored median 0.41 (p10 0.27); empty spawn-area cells median 0.36
  (p90 0.46, max 0.57); 195 / 1,824 samples. R 14 px: the empty cells rose to median 0.44.
- The label study (orcsdun01-detector.md 3e) scored clear plants at 0.76-0.78 with the frozen 1b
  anchor and the fit, which this live render leaves out.
- So TAU stays None and the runner does NOT use this finder (dungeon@4 sweeps the spawn areas with
  the cursor instead); the calibration is the record.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

ROOT = Path(__file__).resolve().parents[1]
WHITE_PLANT = 1082
R_PX = int(os.environ.get("PLANT_R_PX", "6"))  # the shift search (px); no 1b anchor offset
TAU: float | None = None  # NOT separating (the module doc's RESULT): never used live
Cell = tuple[int, int]


def spawn_areas(map_name: str, job: int = WHITE_PLANT,
                kb: Path = ROOT / "data" / "kb") -> list[tuple[int, int, int, int]]:  # fmt: skip
    """[(x, y, xs, ys)] of the map's spawn lines for ``job`` with a fixed area (x, y > 0)."""
    doc = json.loads((kb / "spawns.json").read_text())
    rows = doc.get("maps", doc).get(map_name, [])
    return [(int(s["x"]), int(s["y"]), int(s["xs"]), int(s["ys"])) for s in rows
            if int(s["id"]) == job and int(s["x"]) > 0 and int(s["y"]) > 0]  # fmt: skip


def area_cells(areas: Sequence[tuple[int, int, int, int]], walkable: Any) -> list[Cell]:
    """PURE: every walkable cell of the areas (x +- xs, y +- ys), once."""
    h, w = walkable.shape
    out: set[Cell] = set()
    for x, y, xs, ys in areas:
        for cx in range(max(0, x - xs), min(w, x + xs + 1)):
            for cy in range(max(0, y - ys), min(h, y + ys + 1)):
                if walkable[cy, cx]:
                    out.add((cx, cy))
    return sorted(out)


def near_area(areas: Sequence[tuple[int, int, int, int]], here: Cell, d: int) -> int | None:
    """PURE: the index of an area whose rectangle lies within ``d`` cells (Chebyshev) of us."""
    for i, (x, y, xs, ys) in enumerate(areas):
        dx = max(0, abs(here[0] - x) - xs)
        dy = max(0, abs(here[1] - y) - ys)
        if max(dx, dy) <= d:
            return i
    return None


class PlantFinder:
    """Scores the White Plant sprite at candidate cells of one frame (RGB, the game region)."""

    def __init__(self, map_name: str, job: int = WHITE_PLANT) -> None:
        import orc_camera_check as occ
        import qa_export

        from poring_dataset import camera as cam
        from poring_dataset import gat as gatmod

        self.sheet = qa_export.Sheets()(job)
        if self.sheet is None:
            raise FileNotFoundError(f"no decoded sprite for {job} (sprite_catalog --work)")
        cj = json.loads((ROOT / "packages/poring_dataset/src/poring_dataset/camera_rdp.json")
                        .read_text())  # fmt: skip
        self.camera = cam.map_camera(cj, cam.map_key(map_name), cam.load_indoor_table())
        self.gat = gatmod.parse((cam.GAT_DIR / f"{cam.map_key(map_name)}.gat").read_bytes())
        self.k = occ.K_V1

    def score(self, rgb: Any, here: Sequence[float], cells: Sequence[Cell],
              ) -> list[tuple[float, Cell, tuple[float, float]]]:  # fmt: skip
        """[(NCC, cell, the anchor px it was found at)] for the cells that scored, best first.
        Both of the plant's images (mirrored) are tried; the better counts."""
        import orc_camera_check as occ

        from poring_dataset.render import Actor, MonsterAction, Scene, predict_sprite

        scene = Scene(self.camera, (float(here[0]), float(here[1])), self.gat)
        out = []
        for c in cells:
            best: tuple[float, tuple[float, float]] | None = None
            seen: set[int] = set()
            for heading in range(0, 8, 2):
                pred = predict_sprite(
                    Actor((float(c[0]), float(c[1])), heading, int(MonsterAction.IDLE)),
                    self.sheet,
                    scene,
                    self.k,
                )
                if pred is None or pred.action_index in seen:
                    continue
                seen.add(pred.action_index)
                bo = occ.best_offset(rgb, self.sheet, pred, R_PX)
                if bo is not None and (best is None or bo[0] > best[0]):
                    best = (bo[0], (pred.anchor_px[0] + bo[1], pred.anchor_px[1] + bo[2]))
            if best is not None:
                out.append((round(best[0], 4), c, best[1]))
        return sorted(out, key=lambda r: -r[0])


# --- the offline calibration (packets as truth) ----------------------------------------------


def calibrate(sid: str, every: int = 5, n_neg: int = 6, seed: int = 1) -> dict[str, Any]:
    import dungeon_judge as dj
    import flow_judge as fj
    from anim_region import stand_grid
    from PIL import Image

    ev, pk, man = dj.load(sid)
    mp = man.get("map") or "orcsdun01"
    pf = PlantFinder(mp)
    ok = stand_grid(mp, pf.gat)
    cells = set(area_cells(spawn_areas(mp), ok))
    track, moving = fj.gm_track(pk)
    lives: dict[int, list[tuple[int, int | None, Cell]]] = {}
    for e in pk:
        if e.get("type") == "entity_appear" and int(e.get("job", -1)) == WHITE_PLANT:
            lives.setdefault(int(e["gid"]), []).append((int(e["t_mono_ns"]), None,
                                                        (int(e["x"]), int(e["y"]))))  # fmt: skip
        elif e.get("type") == "entity_vanish" and int(e.get("gid", -1)) in lives:
            t0_, _n, c_ = lives[int(e["gid"])][-1]
            lives[int(e["gid"])][-1] = (t0_, int(e["t_mono_ns"]), c_)
    frames_dir = Path(str(man.get("frames_dir") or ""))
    refs = sorted(frames_dir.glob("*.jpg"))[::every]
    rng = np.random.default_rng(seed)
    pos, neg = [], []
    for ref in refs:
        t = int(ref.stem.split("-")[1])
        if any(a <= t <= b for a, b in moving) or any(a <= t - 300_000_000 <= b for a, b in moving):
            continue  # stood still >= 0.3 s: the camera is centred on our cell
        here = fj.at(track, t)
        if here is None:
            continue
        live = [c for ls in lives.values() for a, b, c in ls if a <= t and (b is None or t < b)]
        vis = [c for c in live if abs(c[0] - here[0]) <= 14 and abs(c[1] - here[1]) <= 10]
        empty = [c for c in cells if abs(c[0] - here[0]) <= 14 and abs(c[1] - here[1]) <= 10
                 and all(max(abs(c[0] - v[0]), abs(c[1] - v[1])) > 2 for v in live)]  # fmt: skip
        if not vis and not empty:
            continue
        rgb = np.asarray(Image.open(ref).convert("RGB"))
        pick = [empty[i] for i in rng.choice(len(empty), min(n_neg, len(empty)), replace=False)] \
            if empty else []  # fmt: skip
        for s, c, _uv in pf.score(rgb, here, vis):
            pos.append({"t": t, "cell": list(c), "here": list(here), "ncc": s})
        for s, c, _uv in pf.score(rgb, here, pick):
            neg.append({"t": t, "cell": list(c), "here": list(here), "ncc": s})
    ps = sorted(r["ncc"] for r in pos)
    ns_ = sorted(r["ncc"] for r in neg)

    def q(xs: list[float], f: float) -> float | None:
        return None if not xs else xs[min(len(xs) - 1, int(f * (len(xs) - 1)))]

    return {"session": sid, "frames_read": len(refs), "positives": len(pos), "negatives": len(neg),
            "pos_q": {f: q(ps, f) for f in (0.05, 0.1, 0.25, 0.5)},
            "neg_q": {f: q(ns_, f) for f in (0.5, 0.9, 0.95, 0.99, 1.0)},
            "pos_rows": pos, "neg_top": sorted(neg, key=lambda r: -r["ncc"])[:10]}  # fmt: skip


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)  # fmt: skip
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("calibrate")
    c.add_argument("sid")
    c.add_argument("--every", type=int, default=5)
    c.add_argument("--neg", type=int, default=6)
    a = ap.parse_args()
    print(json.dumps(calibrate(a.sid, a.every, a.neg), indent=1, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
