#!/usr/bin/env python3
"""Design time (NOT a rule): measure re-localisation v2's geometry against the TRUTH.

    reloc_cal.py [--sites 20] [--probes 15] [--seed 20261019] [--out DIR]

relocalise@2 (demonstrations 3.11) was confidently WRONG in 24 / 50: the true cell was eliminated
because what the client drew did not match v2's prediction for it within the 6 px relative margin
-- a margin that had never been measured. Here the truth is known (a seeded @warp; the packets
confirm it offline) and every probe logs, next to each other:
- what the client drew: walk5.classify's kind and the chevron positions (client px);
- reloc2.predict for the TRUE cell: blocked / walk, and the predicted anchors;
- the fit (px) of the observed chevrons to the truth's anchors, and the best fit among the truth's
  8 neighbours (the margin a decision needs).
Outputs <out>/<session>.jsonl (client-derived numbers only; /dev/shm). Pixels in, input out.
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
import reloc2  # noqa: E402
import ro_agent as r  # noqa: E402
import rule_run as rr  # noqa: E402
import walk5 as w5  # noqa: E402

HOVER_S = 0.55  # as relocalise@1/2


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)  # fmt: skip
    ap.add_argument("--sites", type=int, default=20)
    ap.add_argument("--probes", type=int, default=15)
    ap.add_argument("--seed", type=int, default=20261019)
    ap.add_argument("--out", type=Path, default=Path("/dev/shm/poring-lab-tmp/reloc-cal"))
    a = ap.parse_args()
    import bench

    from poring_dataset import camera as cam
    from poring_dataset import gat as gatmod

    rr.HOVER_S = HOVER_S
    mask = np.load(w5.NOENTRY_MASK)
    mapname, sx0, sy0 = rr.SCENES["indoor"]
    gat = gatmod.parse((cam.GAT_DIR / f"{mapname}.gat").read_bytes())
    cj = json.loads((r.ROOT / "packages/poring_dataset/src/poring_dataset/camera_rdp.json")
                    .read_text())  # fmt: skip
    base = cam.camera_from_json(cj["camera"])
    camera = cam.camera_for_map(base, True, cj["indoor"]["yaw_deg"], cj["indoor"]["distance"])
    w = w5.World(camera, gat, (sx0, sy0))
    x0, y0, x1, y1 = rr.ec_band()
    pixels = {}
    for o in reloc2.OFFSETS:
        u, v = w.camera.project(np.array([o], dtype=float), None)[0]
        if x0 <= u <= x1 and y0 <= v <= y1:
            pixels[o] = (float(u), float(v))
    cell_px = reloc2.spacing(w)
    rng = random.Random(a.seed)
    a.out.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%dT%H%M%S")
    path = a.out / f"{stamp}-reloc-cal.jsonl"
    n = 0
    with r.session("claude-demo-reloc-cal") as (agent, screen), path.open("w") as fh:
        r.gm(agent, screen, "@killmonster2")
        for site in range(a.sites):
            for _ in range(200):
                sx, sy = sx0 + rng.randint(-8, 8), sy0 + rng.randint(-8, 8)
                if w.walkable[sy, sx]:
                    break
            r.gm(agent, screen, f"@warp {mapname} {sx} {sy}")
            time.sleep(rr.WARP_SETTLE_S)
            bench.close_chat(agent, screen)
            r.activate_client(agent, screen)
            true = (sx, sy)
            near = [c for c in reloc2.candidates(w, true, 1) if c != true]
            for o in rng.sample(sorted(pixels), min(a.probes, len(pixels))):
                u, v = pixels[o]
                got = w5.probe(agent, screen, u, v, mask)
                kind = w5.classify(got)
                want = reloc2.predict(w, true, o, (u, v))
                row = {"t": r.ns(), "site": site, "true": list(true), "offset": list(o),
                       "kind": kind, "comps": [list(map(float, c)) for c in got["comps"]],
                       "noentry": round(float(got["noentry"]), 3), "marker_px": got["marker_px"],
                       "pred_true": want[0]}  # fmt: skip
                if want[0] == "walk":
                    row["pred_true_cell"] = list(want[1][0])
                    row["fit_true_px"] = reloc2.fit_px(got["comps"], want[1][1])
                fits = []
                for c in near:
                    pc = reloc2.predict(w, c, o, (u, v))
                    if pc[0] == "walk":
                        fits.append(reloc2.fit_px(got["comps"], pc[1][1]))
                row["fit_best_neighbour_px"] = min(fits) if fits else None
                row["cell_px"] = cell_px
                fh.write(json.dumps(row) + "\n")
                n += 1
        r.gm(agent, screen, "@killmonster2")
        bench.close_chat(agent, screen)
    print(json.dumps({"out": str(path), "probes": n}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
