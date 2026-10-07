#!/usr/bin/env python3
"""Calibrate the walk-marker hover cue per display path (design time; demonstrations.md walk@2).

    walk_marker_calibrate.py --scene outdoor|indoor [--n 30] [--seed 7] --out /dev/shm/...json

The GM stands at the scene spot (this script warps there and closes the chat: an OPEN chat input
suppresses the marker, 2026-10-07). It hovers n WALKABLE cells and n NON-walkable cells (from the
map's GAT) around it, inside the click band, and counts each candidate filter's marker pixels in the
90x90 hover crop. A threshold is usable only if the walkable hovers and the non-walkable hovers
SEPARATE. The output (counts per hover, per filter) goes to /dev/shm. Client-derived crops are
never written.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import bench  # noqa: E402
import empty_cell as ec  # noqa: E402
import ro_agent as r  # noqa: E402
from rule_run import SCENES, walk_projector  # noqa: E402

from poring_dataset import gat as gatmod  # noqa: E402
from poring_dataset.camera import GAT_DIR, click_for_cell  # noqa: E402


def filters(crop: np.ndarray) -> dict[str, int]:
    b, g, rr = (crop[..., i].astype(int) for i in range(3))
    return {
        "mint_v1": ec.marker_px(crop),  # empty_cell's (another path)
        "green_v2": int(((g - rr > 50) & (g - b > 35) & (rr > 60) & (b > 60) & (g > 150)).sum()),
        "green_any": int(((g - rr > 40) & (g - b > 20)).sum()),  # incl. the HP bar: reference only
    }


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--scene", choices=sorted(SCENES), required=True)
    ap.add_argument("--n", type=int, default=30)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args()
    if not str(a.out).startswith("/dev/shm/"):
        raise SystemExit("keep it on /dev/shm (rule 7)")
    mapname, sx, sy = SCENES[a.scene]
    walkable = gatmod.parse((GAT_DIR / f"{mapname}.gat").read_bytes()).walkable()
    proj, _ = walk_projector(a.scene)
    rng = random.Random(a.seed)
    x0, y0, x1, y1 = ec.CLICK_BAND
    rows = []
    with r.session("claude-demo-marker-cal") as (agent, screen):
        r.gm(agent, screen, f"@warp {mapname} {sx} {sy}")
        time.sleep(4)
        bench.close_chat(agent, screen)
        r.activate_client(agent, screen)
        gx, gy, _, _ = r.game_region()
        want = {True: a.n, False: a.n}
        tries = 0
        while any(want.values()) and tries < 2000:
            tries += 1
            dx, dy = rng.randint(-7, 7), rng.randint(-5, 5)
            cx, cy = sx + dx, sy + dy
            if max(abs(dx), abs(dy)) < 2 or not (
                0 <= cy < walkable.shape[0] and 0 <= cx < walkable.shape[1]
            ):
                continue
            ok = bool(walkable[cy, cx])
            if not want[ok]:
                continue
            u, v = click_for_cell(proj, (dx, dy), (sx, sy))
            if not (x0 <= u <= x1 and y0 <= v <= y1):
                continue
            agent.move(gx + round(u) - 3, gy + round(v) - 3)
            time.sleep(0.05)
            agent.move(gx + round(u), gy + round(v))
            time.sleep(0.4)
            crop = screen.grab(*ec.crop_region(gx + round(u), gy + round(v)))[1]
            rows.append(
                {"walkable": ok, "offset": [dx, dy], "pixel": [round(u), round(v)], **filters(crop)}
            )
            want[ok] -= 1
    out = {"scene": a.scene, "map": mapname, "spot": [sx, sy], "path": "rdp", "hovers": rows}
    for f in ("mint_v1", "green_v2", "green_any"):
        pos = sorted(x[f] for x in rows if x["walkable"])
        neg = sorted(x[f] for x in rows if not x["walkable"])
        out[f] = {
            "walkable_min": pos[0] if pos else None,
            "walkable_p10": pos[len(pos) // 10] if pos else None,
            "nonwalkable_max": neg[-1] if neg else None,
            "separate": bool(pos and neg and pos[0] > neg[-1]),
        }
    a.out.write_text(json.dumps(out, indent=1))
    print(json.dumps({k: out[k] for k in ("scene", "mint_v1", "green_v2", "green_any")}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
