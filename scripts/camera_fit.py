#!/usr/bin/env python3
"""Fit a calibration's points as RO's perspective camera, with and without the map's GAT altitude,
and compare with the homography on HELD-OUT points (Phase 2 B4; Batt 2026-10-03).

    camera_fit.py CALIB.json --gat MAP.gat [--save]

CALIB.json is calibrate_projection.py's evidence (data/bench/calibration/<stamp>.json): the click
pairs (cell offset -> pixel) and the GM-spawn validation feet. MAP.gat is the spot's map, extracted
to /dev/shm by `grf_read.py extract ... --decode-des` (client data: never committed).

Reported, for the homography, the flat camera and the camera + altitude:
  * in-sample residuals (median / p95 px);
  * leave-one-out over the click pairs (each point predicted by a fit WITHOUT it);
  * the validation feet (all, and the non-moving ones).
Evidence -> data/bench/calibration/<stamp>-camera-fit.json. --save adds the camera block to
packages/poring_dataset/src/poring_dataset/camera_<backend>.json next to the homography (kept as the
fallback when no GAT is at hand), only when camera + altitude wins the leave-one-out median.
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np

from poring_dataset import gat as gatmod
from poring_dataset import projection
from poring_dataset.camera import NAMES, fit_camera

Array = np.ndarray


def stats(errs: Array) -> dict[str, float]:
    return {"median_px": round(float(np.median(errs)), 1),
            "p95_px": round(float(np.percentile(errs, 95)), 1), "n": len(errs)}  # fmt: skip


def compare(calib: dict[str, Any], grid: gatmod.Gat) -> dict[str, Any]:
    spot = (int(calib["spot"][1]), int(calib["spot"][2]))
    cells = np.array([p["cell"] for p in calib["pairs_detail"]], float)
    px = np.array([p["px"] for p in calib["pairs_detail"]], float)
    alt = grid.relative_altitude(spot, cells)
    hfit = projection.fit(cells, px)
    flat = fit_camera(cells, px)
    withalt = fit_camera(cells, px, altitude=alt)

    def loo(predict: Any) -> dict[str, float]:
        errs = []
        for i in range(len(cells)):
            keep = np.arange(len(cells)) != i
            errs.append(float(np.linalg.norm(predict(keep, i) - px[i])))
        return stats(np.array(errs))

    out: dict[str, Any] = {
        "spot": calib["spot"],
        "pairs": len(cells),
        "altitude_range": [round(float(alt.min()), 1), round(float(alt.max()), 1)],
        "in_sample": {
            "homography": stats(hfit.residuals_px),
            "camera_flat": stats(flat.residuals_px),
            "camera_altitude": stats(withalt.residuals_px),
        },
        "leave_one_out": {
            "homography": loo(
                lambda k, i: projection.project(
                    projection.fit_homography(cells[k], px[k]), cells[i : i + 1]
                )[0]
            ),
            "camera_flat": loo(
                lambda k, i: fit_camera(cells[k], px[k], start=flat.camera).camera.project(
                    cells[i : i + 1]
                )[0]
            ),
            "camera_altitude": loo(
                lambda k, i: fit_camera(
                    cells[k], px[k], altitude=alt[k], start=withalt.camera
                ).camera.project(cells[i : i + 1], alt[i : i + 1])[0]
            ),
        },  # fmt: skip
        "camera": {n: float(v) for n, v in zip(NAMES, withalt.camera.vector(), strict=True)},
        "camera_degrees": {
            "yaw": round(float(np.degrees(withalt.camera.yaw)) % 360, 2),
            "pitch": round(float(np.degrees(withalt.camera.pitch)), 2),
            "fov": round(float(np.degrees(withalt.camera.fov)), 2),
        },
    }
    samples = (calib.get("validation") or {}).get("samples") or []
    if samples:
        projected = np.array([s["projected"] for s in samples], float)
        seen = np.array([s["seen"] for s in samples], float)
        static = np.array([not s.get("moving") for s in samples])
        # the samples store H(cell): invert the calibration's own H to get the cells back
        vc = projection.project(np.linalg.inv(np.array(calib["h"], float)), projected)
        vc = np.where(static[:, None], np.round(vc), vc)  # moving ones sit between cells
        valt = grid.relative_altitude(spot, vc)
        preds = {
            "homography": projection.project(hfit.h, vc),
            "camera_flat": flat.camera.project(vc),
            "camera_altitude": withalt.camera.project(vc, valt),
        }
        out["validation"] = {}
        for name, pred in preds.items():
            e = np.linalg.norm(pred - seen, axis=1)
            out["validation"][name] = {"all": stats(e), "static": stats(e[static])}
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("calib", type=Path)
    ap.add_argument("--gat", type=Path, required=True)
    ap.add_argument("--save", action="store_true")
    a = ap.parse_args()
    calib = json.loads(a.calib.read_text())
    grid = gatmod.parse(a.gat.read_bytes())
    if a.gat.stem != calib["spot"][0]:
        raise SystemExit(f"{a.gat.name} is not the calibration's map {calib['spot'][0]}")
    result = {"calibration": a.calib.name, "backend": calib["backend"], **compare(calib, grid)}
    out = a.calib.with_name(a.calib.stem + "-camera-fit.json")
    out.write_text(json.dumps(result, indent=1) + "\n")
    loo = result["leave_one_out"]
    wins = loo["camera_altitude"]["median_px"] < loo["homography"]["median_px"]
    if a.save:
        if not wins:
            raise SystemExit("camera + altitude does not win the leave-one-out median: not saved")
        path = projection.camera_file(calib["backend"])
        current = json.loads(path.read_text())
        if current.get("backend") != calib["backend"]:
            raise SystemExit(f"{path.name} holds another backend's camera")
        if current.get("stamp") != calib["stamp"]:
            raise SystemExit(f"{path.name} is not from {a.calib.name}: calibrate --save it first")
        current["camera"] = {
            **result["camera"], "height": int(calib["game_region"][3]),
            "model": "perspective + GAT altitude (poring_dataset.camera)",
            "fitted_on": a.calib.name, "leave_one_out": loo,
            "validation": result.get("validation"),
        }  # fmt: skip
        path.write_text(json.dumps(current, indent=1) + "\n")
    print(json.dumps({k: result[k] for k in ("leave_one_out", "camera_degrees")} |
                     {"validation": result.get("validation"), "evidence": str(out),
                      "camera_wins": wins, "saved": a.save}, indent=1))  # fmt: skip
    return 0


if __name__ == "__main__":
    sys.exit(main())
