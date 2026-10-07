#!/usr/bin/env python3
"""Why does the walk cursor read UNKNOWN? A HOVER-ONLY diagnostic, not a rule and not scored.

walk@8-10 indoors (prt_church): the cursor reads UNKNOWN on 75 % of hovers at the altar end and
56 % on the east side, 13 % in the middle, 0 % on the west. Most east unknowns MATCH the shape
(IoU >= 0.6) and fail the colour check. This tool parks, hovers pick-safe points around fixed
spots and saves, per hover, what the classifier saw: the parked crop A, the hover crop B, the
animated mask, the cursor mask, the best reference by IoU and its colour agreement (also when
below the threshold). Nothing is clicked; no key is pressed except the GM's own warp commands.

    cursor_diag.py [--spots east,north,middle,west] [--per-spot 10] [--out /dev/shm/...]

Crops are client pixels: they stay in /dev/shm (CLAUDE.md rule 4), never in the repository.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ro_agent as r  # noqa: E402
import rule_run as rr  # noqa: E402
import walk5 as w5  # noqa: E402
import walk6 as w6  # noqa: E402
import walk10 as w10  # noqa: E402

MAP = "prt_church"
SPOTS = {"east": (111, 124), "north": (103, 76), "middle": (100, 114), "west": (90, 114)}
# the church's visible NPCs (their cells from the packets of walk@10's indoor sessions; design-time
# calibration input only -- the rule never reads them)
NPCS = {"nun": (108, 124), "sister": (111, 112), "henson": (103, 71), "garnet": (103, 76),
        "bishop": (100, 128), "crusader": (95, 127), "pastor": (87, 127), "bard": (89, 108),
        "praying": (113, 103), "wedding": (97, 100), "army": (97, 102)}  # fmt: skip
SPRITE_OFFSETS = ((0, 0), (-6, -12), (6, -12), (0, -24), (-6, -36), (6, -36), (0, -48), (0, -60))
RINGS = ((2, 0), (0, 2), (-2, 0), (0, -2), (2, 2), (-2, 2), (2, -2), (-2, -2), (3, 0), (0, 3),
         (-3, 0), (0, -3))  # fmt: skip


def explain(refs: w6.CursorRefs, a: Any, mask: Any) -> dict[str, Any]:
    """match()'s verdict plus the best-IoU reference's colour agreement, whatever its value."""
    out = refs.match(a, mask)
    m = np.asarray(mask, dtype=bool)
    out["mask_px"] = int(m.sum())
    if m.sum():
        inter = (refs.m & m).reshape(len(refs.cls), -1).sum(1)
        union = (refs.m | m).reshape(len(refs.cls), -1).sum(1)
        iou = inter / np.maximum(union, 1)
        j = int(np.argmax(iou))
        ov = refs.m[j] & m
        diff = np.abs(np.asarray(a)[..., :3].astype(np.int16) - refs.a[j]).max(-1)[ov]
        best: dict[str, Any] = {"cls": refs.cls[j], "iou": round(float(iou[j]), 3), "col": 0.0}
        if ov.any():
            best["col"] = round(float((diff < w6.COL_TOL).mean()), 3)
            best["diff_p50"] = float(np.median(diff))
            best["diff_p90"] = float(np.percentile(diff, 90))
        out["best"] = best
    return out


def capture(
    pr: Any, screen: Any, refs: Any, u: float, v: float
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Hover (u, v) after a park; the classifier's view of it: (record, arrays)."""
    pr.hover(u, v)
    gx, gy, _, _ = r.game_region()
    px, py = gx + round(u), gy + round(v)
    big = screen.grab(px - 60, py - 60, 120, 120)[1][..., :3]
    ca = big[28:92, 28:92]
    cb = pr._crop(pr.background, u, v, 32)[..., :3]
    anim = pr._crop(pr.animated[..., None].astype(np.uint8), u, v, 32)[..., 0] > 0
    mask = w6.cursor_mask(ca, np.where(anim[..., None], ca, cb))
    rec = {"at": [round(u, 1), round(v, 1)], "anim_px": int(anim.sum()), **explain(refs, ca, mask)}
    return rec, {"a": ca, "b": cb, "anim": anim, "mask": mask, "big": big}


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--spots", default="east,north,middle,west")
    ap.add_argument("--per-spot", type=int, default=10)
    ap.add_argument("--npcs", default="", help="comma list of NPCS keys: hover their sprites")
    ap.add_argument("--out", type=Path, default=Path("/dev/shm/poring-lab-tmp/cursor-diag"))
    a = ap.parse_args()
    import bench

    from poring_dataset import camera as cam
    from poring_dataset import gat as gatmod

    a.out.mkdir(parents=True, exist_ok=True)
    refs = w6.CursorRefs.load(w10.CURSOR_REFS_V2)
    gat = gatmod.parse((cam.GAT_DIR / f"{MAP}.gat").read_bytes())
    cj = json.loads((r.ROOT / "packages/poring_dataset/src/poring_dataset/camera_rdp.json")
                    .read_text())  # fmt: skip
    camera = cam.camera_for_map(cam.camera_from_json(cj["camera"]), True,
                                cj["indoor"]["yaw_deg"], cj["indoor"]["distance"])  # fmt: skip
    log = (a.out / "hovers.jsonl").open("a")
    with r.session("rule:cursor-diag") as (agent, screen):
        pr = w10.Prober9(agent, screen, refs)
        for key in [k for k in a.npcs.split(",") if k]:
            nx, ny = NPCS[key]
            w = w5.World(camera, gat, (nx, ny))
            stand = next(((nx + dx, ny + dy) for dy in (-3, -4, -2, 3) for dx in (0, -1, 1, -2, 2)
                          if w.walkable[ny + dy, nx + dx]), None)  # fmt: skip
            if stand is None:
                continue
            r.gm(agent, screen, "@killmonster2")
            r.gm(agent, screen, f"@warp {MAP} {stand[0]} {stand[1]}")
            time.sleep(rr.WARP_SETTLE_S)
            bench.close_chat(agent, screen)
            r.activate_client(agent, screen)
            w.position = stand
            rel = np.array([[nx - stand[0], ny - stand[1]]], dtype=float)
            cu, cv = camera.project(rel, gat.relative_altitude(stand, rel))[0]
            for k, (du, dv) in enumerate(SPRITE_OFFSETS):
                if not pr.park():
                    continue
                rec, arrs = capture(pr, screen, refs, cu + du, cv + dv)
                stem = f"npc-{key}-{k}"
                np.savez_compressed(a.out / f"{stem}.npz", **arrs)
                rec.update({"spot": f"npc:{key}", "npc": [nx, ny], "from": list(stand),
                            "npz": f"{stem}.npz", "t": time.time()})  # fmt: skip
                log.write(json.dumps(rec) + "\n")
                log.flush()
                keys = ("spot", "at", "shape", "iou", "mask_px", "best")
                print(json.dumps({k2: rec.get(k2) for k2 in keys}), flush=True)
        for name in [n for n in a.spots.split(",") if n and not a.npcs]:
            sx, sy = SPOTS[name]
            r.gm(agent, screen, "@killmonster2")
            r.gm(agent, screen, f"@warp {MAP} {sx} {sy}")
            time.sleep(rr.WARP_SETTLE_S)
            bench.close_chat(agent, screen)
            r.activate_client(agent, screen)
            w = w5.World(camera, gat, (sx, sy))
            done = 0
            for dx, dy in RINGS:
                if done >= a.per_spot:
                    break
                end = (sx + dx, sy + dy)
                if not w.walkable[end[1], end[0]]:
                    continue
                pts, tier = w10.pick_points(w, end)
                if not pts or not pr.park():
                    continue
                u, v = pts[0]
                pr.hover(u, v)
                gx, gy, _, _ = r.game_region()
                px, py = gx + round(u), gy + round(v)
                big = screen.grab(px - 60, py - 60, 120, 120)[1][..., :3]
                ca = big[28:92, 28:92]
                cb = pr._crop(pr.background, u, v, 32)[..., :3]
                anim = pr._crop(pr.animated[..., None].astype(np.uint8), u, v, 32)[..., 0] > 0
                b_mod = np.where(anim[..., None], ca, cb)
                mask = w6.cursor_mask(ca, b_mod)
                rec = {"spot": name, "from": [sx, sy], "end": list(end), "tier": tier,
                       "at": [round(u, 1), round(v, 1)], "anim_px": int(anim.sum()),
                       **explain(refs, ca, mask), "t": time.time()}  # fmt: skip
                stem = f"{name}-{done:02d}"
                np.savez_compressed(a.out / f"{stem}.npz", a=ca, b=cb, anim=anim, mask=mask,
                                    big=big)  # fmt: skip
                rec["npz"] = f"{stem}.npz"
                log.write(json.dumps(rec) + "\n")
                log.flush()
                print(json.dumps({k: rec[k] for k in ("spot", "end", "shape", "iou", "mask_px")}
                                 | {"best": rec.get("best")}), flush=True)  # fmt: skip
                done += 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
