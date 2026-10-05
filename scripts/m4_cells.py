#!/usr/bin/env python3
"""Phase 3 M4 re-run (phase3-plan §5b): choose the spawn cells BEFORE the session, offline.

    m4_cells.py [--camera console] [--species poring] [--radius 22] [--out data/bench/m4/cells.json]

For each scene spot (outdoor prt_fild08 268,107: open, where the console camera was fitted;
indoor prt_church 104,122, see SPOTS), every walkable cell within --radius is projected with the
fitted camera (the GM standing on the spot) and the species' OPAQUE idle envelope (predict_sprite).
A cell is a
candidate for a condition when:
- its predicted box lies fully inside the 1280x720 game region and covers no UI window;
- its anchor row is in the condition's third (top < 240 <= centre < 480 <= bottom);
- every walkable neighbour within --spread cells satisfies the same (@monster spawns around the GM,
  and the monster then random-walks: the condition must hold where it may stand);
- indoor only, the OCCLUDER PROXY (prt_church's pews and walls are non-walkable cells): no
  non-walkable cell lies IN FRONT of it (its anchor lower on screen, i.e. closer to the camera,
  within --front cells) whose screen column overlaps the predicted box.

Nothing here reads a recording: the choice is made before the data exists. The output lists the
cells per scene and condition with their anchor rows, ordered by distance from the spot.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from poring_dataset import mapcache  # noqa: E402
from poring_dataset.projection import camera_file  # noqa: E402
from poring_dataset.render import (  # noqa: E402
    K_NOSTALRO,
    Actor,
    MonsterAction,
    Scene,
    SpriteSheet,
    anchor_and_depth,
    load_scene,
    predict_sprite,
)
from poring_dataset.ui_layout import covered_fraction  # noqa: E402

# indoor 104,122 (not bench.py's 99,112): of 210 walkable GM spots scanned in prt_church
# (2026-10-05), it has the most occluder-free cells in BOTH the top and bottom thirds (22/9);
# at 99,112 the pews leave 2 top and 0 bottom.
SPOTS = {"outdoor": ("prt_fild08", 268, 107), "indoor": ("prt_church", 104, 122)}
W, H = 1280, 720
TOP, BOTTOM = 240, 480


def third(v: float) -> str:
    return "top" if v < TOP else "bottom" if v >= BOTTOM else "centre"


def cell_ok(scene: Scene, sheet: SpriteSheet, cell: tuple[int, int]) -> dict[str, Any] | None:
    """The cell's predicted box and anchor when the sprite is fully visible and UI-free."""
    pred = predict_sprite(Actor((float(cell[0]), float(cell[1])), 0, MonsterAction.IDLE), sheet,
                          scene, K_NOSTALRO)  # fmt: skip
    if pred is None:
        return None
    x0, y0, x1, y1 = pred.box
    if x0 < 0 or y0 < 0 or x1 > W or y1 > H or covered_fraction(pred.box) > 0:
        return None
    return {"box": [round(v, 1) for v in pred.box], "anchor": [round(v, 1) for v in pred.anchor_px]}


def occluded(scene: Scene, grid: mapcache.MapGrid, cell: tuple[int, int], box: list[float],
             front: int) -> bool:  # fmt: skip
    """True when a non-walkable cell in front of ``cell`` (closer to the camera: its anchor lower on
    screen) projects into the sprite's columns: the pew/wall proxy for occlusion."""
    (_, v0), _ = anchor_and_depth(scene, (float(cell[0]), float(cell[1])))
    for dx in range(-front, front + 1):
        for dy in range(-front, front + 1):
            n = (cell[0] + dx, cell[1] + dy)
            if n == cell or not grid.nopass(*n):
                continue
            (u, v), _ = anchor_and_depth(scene, (float(n[0]), float(n[1])))
            if v > v0 and box[0] - 8 <= u <= box[2] + 8:
                return True
    return False


def choose(scene_name: str, camera: dict[str, Any], sheet: SpriteSheet,
           grids: dict[str, mapcache.MapGrid], radius: int, spread: int,
           front: int) -> dict[str, list[dict[str, Any]]]:  # fmt: skip
    map_name, sx, sy = SPOTS[scene_name]
    grid = grids[map_name]
    scene = load_scene(camera, map_name, (float(sx), float(sy)))
    info: dict[tuple[int, int], dict[str, Any] | None] = {}

    def at(c: tuple[int, int]) -> dict[str, Any] | None:
        if c not in info:
            ok = None if grid.nopass(*c) else cell_ok(scene, sheet, c)
            if ok is not None:
                ok["third"] = third(ok["anchor"][1])
                indoor = scene_name == "indoor"
                ok["clear"] = not indoor or not occluded(scene, grid, c, ok["box"], front)
            info[c] = ok
        return info[c]

    out: dict[str, list[dict[str, Any]]] = {"top": [], "centre": [], "bottom": []}
    for dx in range(-radius, radius + 1):
        for dy in range(-radius, radius + 1):
            c = (sx + dx, sy + dy)
            me = at(c)
            if me is None or not me["clear"] or max(abs(dx), abs(dy)) < 2:
                continue
            hood = [(c[0] + ex, c[1] + ey) for ex in range(-spread, spread + 1)
                    for ey in range(-spread, spread + 1)]  # fmt: skip
            walk = [n for n in hood if not grid.nopass(*n)]
            if not all((o := at(n)) is not None and o["clear"] and o["third"] == me["third"]
                       for n in walk):  # fmt: skip
                continue
            out[me["third"]].append({"cell": list(c), "dist": max(abs(dx), abs(dy)),
                                     "anchor": me["anchor"], "box": me["box"]})  # fmt: skip
    for cond in out.values():
        cond.sort(key=lambda r: (r["dist"], r["cell"]))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--camera", default="console")
    ap.add_argument("--species", default="poring")
    ap.add_argument("--radius", type=int, default=22)
    ap.add_argument("--spread", type=int, default=1)
    ap.add_argument("--front", type=int, default=3)
    ap.add_argument("--out", type=Path, default=None)
    a = ap.parse_args()
    import m4_validate

    camera = json.loads(camera_file(a.camera).read_text())
    sheet = m4_validate.sprite_sheet(a.species, use_spr=True)
    if sheet.box_kind != "opaque":
        raise SystemExit(f"{a.species}: no decoded SPR (opaque boxes needed)")
    grids = mapcache.load(prere=True)
    result = {"camera": a.camera, "species": a.species, "spots": SPOTS,
              "radius": a.radius, "spread": a.spread, "front": a.front,
              "scenes": {s: choose(s, camera, sheet, grids, a.radius, a.spread, a.front)
                         for s in SPOTS}}  # fmt: skip
    summary = {s: {t: len(v) for t, v in c.items()} for s, c in result["scenes"].items()}
    if a.out:
        a.out.parent.mkdir(parents=True, exist_ok=True)
        a.out.write_text(json.dumps(result, indent=1) + "\n")
    print(json.dumps({"candidates": summary,
                      "nearest": {s: {t: v[:3] for t, v in c.items()}
                                  for s, c in result["scenes"].items()}}, indent=1))  # fmt: skip
    return 0


if __name__ == "__main__":
    sys.exit(main())
