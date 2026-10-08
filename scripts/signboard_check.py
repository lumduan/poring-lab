#!/usr/bin/env python3
"""The signboard finder's proof (poring_env.signboard, Batt 2026-10-08): zero false signs on banked
frames, and the real sign found where it is. Read-only over banked sessions; prints JSON.

    signboard_check.py census [GLOB ...]       every frame: signs found, their sizes, and each one's
                                               pixels against the reference sign (an outlier is a
                                               false sign until an eye check says otherwise)
    signboard_check.py oracle SESSION ...      an INDEPENDENT check on demo sessions of one map: fit
                                               the sign's NPC cell from the hits (route start cells
                                               x the camera), then predict for EVERY route-start
                                               frame whether the sign must be in view
    signboard_check.py npc SESSION ...         the NPC rule on the real signs: an NPC detected under
                                               each one wherever one could be seen

The reference is the first sign the finder returns in --ref (a lossless banked frame). Client frames
stay local (CLAUDE.md rule 4): this prints numbers and paths only.
"""

from __future__ import annotations

import argparse
import glob
import json
import sys
from multiprocessing import Pool
from pathlib import Path
from typing import Any

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import route_preview as rp  # noqa: E402

from poring_env.signboard import find_signs  # noqa: E402

SIGN_W, SIGN_H = 160, 32  # the wedding NPC's sign, outline to outline
_REF: np.ndarray | None = None


def load_rgb(path: str) -> np.ndarray:
    from PIL import Image

    return np.asarray(Image.open(path).convert("RGB"))


def signs_in(
    rgb: np.ndarray, npcs: list[tuple[float, float, float, float]] | None = None
) -> list[Any]:
    return find_signs(np.ascontiguousarray(rgb[..., ::-1]), npcs=npcs, exclude=rp.UI_WINDOWS)


def _init(ref: np.ndarray) -> None:
    global _REF
    _REF = ref


def _census_one(path: str) -> tuple[str, list[list[float]] | None]:
    rgb = load_rgb(path)
    if rgb.shape[:2] != (720, 1280):
        return path, None
    out = []
    for s in signs_in(rgb):
        b = s.box
        crop = rgb[b.y0 : b.y1 + 1, b.x0 : b.x1 + 1].astype(np.int16)
        diff = -1.0
        if _REF is not None and crop.shape == _REF.shape:
            diff = float(np.abs(crop - _REF).mean())
        out.append([b.x0, b.y0, b.x1, b.y1, b.w, b.h, round(diff, 1)])
    return path, out


def census(globs: list[str], ref: str, workers: int) -> int:
    rgb = load_rgb(ref)
    (s, *_) = signs_in(rgb)
    b = s.box
    ref_crop = rgb[b.y0 : b.y1 + 1, b.x0 : b.x1 + 1].astype(np.int16)
    rep: dict[str, Any] = {}
    with Pool(workers, initializer=_init, initargs=(ref_crop,)) as pool:
        for g in globs:
            files = sorted(glob.glob(g))
            out = pool.map(_census_one, files, chunksize=32)
            boxes = [(p, h) for p, hs in out if hs for h in hs]
            diffs = sorted(h[6] for _, h in boxes)
            rep[g] = {
                "frames": len(files),
                "skipped (not 1280x720)": sum(hs is None for _, hs in out),
                "frames with a sign": sum(bool(hs) for _, hs in out),
                "box sizes": sorted({(h[4], h[5]) for _, h in boxes}),
                "diff vs reference p50/p99/max": [
                    diffs[len(diffs) // 2],
                    diffs[int(len(diffs) * 0.99)],
                    diffs[-1],
                ]
                if diffs
                else None,  # fmt: skip
                "largest diffs": [
                    [p, h[:4], h[6]] for p, h in sorted(boxes, key=lambda x: -x[1][6])[:5]
                ],
            }
            print(json.dumps({g: rep[g]}), flush=True)
    return 0


def _route_starts(session: Path) -> list[tuple[str, tuple[int, int]]]:
    rows = []
    for line in (session / "demo.jsonl").read_text().splitlines():
        r = json.loads(line)
        if r["action"]["intended"]["kind"] != "route":
            continue
        ev = r["outcome"]["evidence"]
        fix = ev.get("start_fix") or {}
        start = fix.get("to") or ev["start_believed"]
        rows.append((str(session / r["frame"]["ref"]), (int(start[0]), int(start[1]))))
    return rows


def _overlaps(a: tuple[float, ...], b: tuple[float, ...]) -> bool:
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


def oracle(sessions: list[Path], map_name: str, margin: float) -> int:
    from poring_dataset import camera as cam

    cj = cam.load_camera_json(
        Path(__file__).resolve().parents[1]
        / "packages/poring_dataset/src/poring_dataset/camera_rdp.json"
    )
    proj, which = cam.projector_for(cj, map_name)
    rows = []
    for s in sessions:
        for path, start in _route_starts(s):
            got = signs_in(load_rgb(path))
            rows.append((path, start, got[0].box if got else None))
    hits = [r for r in rows if r[2] is not None]
    if not hits:
        print(json.dumps({"error": "no sign found in any frame: nothing to fit"}))
        return 1

    def at(cell: tuple[int, int], start: tuple[int, int]) -> tuple[float, float]:
        ((u, v),) = proj(np.array([[cell[0] - start[0], cell[1] - start[1]]], float), start)
        return float(u), float(v)

    x0s = [h[1][0] for h in hits]
    y0s = [h[1][1] for h in hits]
    best: tuple[float, tuple[int, int], np.ndarray, np.ndarray] | None = None
    for cx in range(min(x0s) - 20, max(x0s) + 21):
        for cy in range(min(y0s) - 25, max(y0s) + 26):
            res = np.array([((b.x0 + b.x1) / 2 - at((cx, cy), st)[0], b.y1 - at((cx, cy), st)[1])
                            for _, st, b in hits])  # fmt: skip
            sd = float(res.std(0).sum())
            if best is None or sd < best[0]:
                best = (sd, (cx, cy), res.mean(0), np.abs(res - res.mean(0)).max(0))
    assert best is not None
    _, cell, off, worst = best
    tab = {"expected, found": 0, "expected, MISSED": 0, "not in view, found (FALSE)": 0,
           "not in view, none": 0, "partly in view / at a UI window (not scored)": 0}  # fmt: skip
    listed: list[dict[str, Any]] = []
    for path, st, b in rows:
        u, v = at(cell, st)
        u, v = u + off[0], v + off[1]
        box = (u - SIGN_W / 2, v - SIGN_H + 1, u + SIGN_W / 2, v)
        grown = (box[0] - margin, box[1] - margin, box[2] + margin, box[3] + margin)
        clear = not any(_overlaps(grown, w) for w in rp.UI_WINDOWS)
        whole = grown[0] >= 0 and grown[1] >= 0 and grown[2] <= 1280 and grown[3] <= 720
        if whole and clear:
            key = "expected, found" if b else "expected, MISSED"
        elif not _overlaps(box, (0, 0, 1280, 720)):
            key = "not in view, found (FALSE)" if b else "not in view, none"
        else:
            key = "partly in view / at a UI window (not scored)"
        tab[key] += 1
        if key in ("expected, MISSED", "not in view, found (FALSE)"):
            listed.append({"case": key, "frame": path, "start": st,
                           "predicted": [round(x) for x in box]})  # fmt: skip
    print(json.dumps({"projector": which, "fitted NPC cell": cell, "n hits fitted": len(hits),
                      "sign offset px": [round(float(x), 1) for x in off],
                      "worst fit residual px": [round(float(x), 1) for x in worst],
                      "frames": len(rows), "table": tab, "listed": listed}, indent=1))  # fmt: skip
    return 0


def npc_rule(sessions: list[Path], threads: int) -> int:
    import unit_detector

    det = unit_detector.UnitDetector(threads=threads)
    n = kept = 0
    dropped: list[str] = []
    try:
        for s in sessions:
            for path in sorted(glob.glob(str(s / "snapshots/*.png"))):
                rgb = load_rgb(path)
                if not signs_in(rgb):
                    continue
                bgr = np.ascontiguousarray(rgb[..., ::-1])
                npcs = [(b.x0, b.y0, b.x1, b.y1) for b in det.detect(bgr) if b.cls == "npc"]
                n += 1
                if signs_in(rgb, npcs=npcs):
                    kept += 1
                else:
                    dropped.append(path)
    finally:
        det.close()
    print(json.dumps({"real signs": n, "kept with the NPC rule": kept, "dropped": dropped},
                     indent=1))  # fmt: skip
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("census")
    c.add_argument("globs", nargs="+")
    c.add_argument("--ref", required=True, help="a lossless banked frame with the sign in view")
    c.add_argument("--workers", type=int, default=2)
    o = sub.add_parser("oracle")
    o.add_argument("sessions", nargs="+", type=Path)
    o.add_argument("--map", default="prt_church")
    o.add_argument("--margin", type=float, default=8.0, help="px the prediction must clear")
    n = sub.add_parser("npc")
    n.add_argument("sessions", nargs="+", type=Path)
    n.add_argument("--threads", type=int, default=2)
    a = ap.parse_args()
    if a.cmd == "census":
        return census(a.globs, a.ref, a.workers)
    if a.cmd == "oracle":
        return oracle(a.sessions, a.map, a.margin)
    return npc_rule(a.sessions, a.threads)


if __name__ == "__main__":
    sys.exit(main())
