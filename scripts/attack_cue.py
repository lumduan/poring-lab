#!/usr/bin/env python3
"""The ATTACK-STARTED cue, measured against packet truth (Batt 2026-10-15 overnight: "verify the
attack started (a PROVEN signal: build and validate the pixel cue against packets first)").

    attack_cue.py measure SESSION [--rec DIR]    per-frame cue values + packet truth -> cue.json

The candidate cue (pixels only, so the bot can use it at run time):
- SWING: the GM's own sprite changes while the SCENE stays still. A standing character shows one
  static frame; a walking one scrolls the whole scene; an attacking one swings in place. The GM is
  always drawn at the screen centre, in box GM_BOX (client px).
  - Per frame pair: the scene shift (phase correlation over the frame, the UI and the GM box
    masked) and the GM box's mean absolute change after that shift is removed.
- Truth from the packets (offline only):
  - a frame is SWINGING when one of our attack acts falls within [-SWING_BEFORE_S,
    +SWING_AFTER_S] of its capture time;
  - IDLE when no act of ours is within +-IDLE_GAP_S and no move of ours is within +-1 s.
- The report: the cue's distribution on each class and the threshold that best separates them.
  At run time "attack started" = the cue over the threshold on a still scene, within T s of a
  click. That T and the threshold are fixed only from a measurement like this one, before any use.
"""

from __future__ import annotations

import argparse
import gzip
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

GM_BOX = (600, 260, 680, 372)  # x0, y0, x1, y1: the GM's sprite at the screen centre (no HP bar)
SWING_BEFORE_S, SWING_AFTER_S = 0.6, 0.2
IDLE_GAP_S = 2.0
STILL_SHIFT_PX = 1.0
GM_AID = 2000002


def scene_shift(a: Any, b: Any) -> tuple[float, float]:
    """Phase correlation of two grey frames (the GM box and the left UI zeroed): b - a in px."""
    fa, fb = np.fft.fft2(a), np.fft.fft2(b)
    cross = fa * np.conj(fb)
    cross /= np.abs(cross) + 1e-9
    r = np.fft.ifft2(cross).real
    y, x = np.unravel_index(int(np.argmax(r)), r.shape)
    h, w = r.shape
    return (float(x if x <= w // 2 else x - w), float(y if y <= h // 2 else y - h))


def gm_change(a: Any, b: Any, box: tuple[int, int, int, int] = GM_BOX) -> float:
    x0, y0, x1, y1 = box
    return float(np.abs(a[y0:y1, x0:x1].astype(np.float32) - b[y0:y1, x0:x1]).mean())


def grey(img: Any) -> Any:
    g = np.asarray(img, dtype=np.float32)
    return g[..., :3].mean(axis=2) if g.ndim == 3 else g


SHIFT_BAND = (540, 10, 1120, 250)  # x0, y0, x1, y1: above the GM, off every UI window


def masked(g: Any) -> Any:
    """The band the scene shift is measured on: no zeroed rectangles (their fixed edges pinned
    the phase correlation at (0, 0): the first measurement called 95 % of pairs still)."""
    x0, y0, x1, y1 = SHIFT_BAND
    return g[y0:y1, x0:x1]


def measure(sid: str, rec: Path | None) -> dict[str, Any]:
    from PIL import Image

    from poring_env.demo import DEMO_ROOT

    d = DEMO_ROOT / sid
    man = json.loads((d / "manifest.json").read_text())
    rec = rec or Path(man["rec_dir"])
    frames = sorted((rec / "frames").glob("*.jpg"))
    with gzip.open(d / "packets.jsonl.gz", "rt") as fh:
        pk = [json.loads(x) for x in fh]
    acts = np.array(sorted(int(e["t_mono_ns"]) for e in pk if e.get("type") == "act"
                           and int(e.get("src_gid", -1)) == GM_AID
                           and e.get("kind") != "pickup"))  # fmt: skip
    moves = np.array(sorted(int(e["t_mono_ns"]) for e in pk if e.get("type") == "self_move"))
    rows = []
    prev = None
    for f in frames:
        t = int(f.stem.split("-")[1])
        g = grey(Image.open(f))
        if prev is not None:
            dx, dy = scene_shift(masked(prev[1]), masked(g))
            change = gm_change(prev[1], g)
            near_act = acts[(acts >= t - SWING_AFTER_S * 1e9) & (acts <= t + SWING_BEFORE_S * 1e9)]
            any_act = acts[np.abs(acts - t) <= IDLE_GAP_S * 1e9]
            any_move = moves[np.abs(moves - t) <= 1e9]
            label = ("swing" if len(near_act) else
                     "idle" if not len(any_act) and not len(any_move) else "other")  # fmt: skip
            rows.append({"t": t, "dx": dx, "dy": dy, "gm": round(change, 2), "label": label})
        prev = (t, g)
    still = [r_ for r_ in rows if abs(r_["dx"]) < STILL_SHIFT_PX and abs(r_["dy"]) < STILL_SHIFT_PX]
    by = {lab: [r_["gm"] for r_ in still if r_["label"] == lab] for lab in ("swing", "idle")}
    best = None
    for thr in np.arange(0.5, 30.0, 0.25):
        tp = sum(v > thr for v in by["swing"])
        fp = sum(v > thr for v in by["idle"])
        if by["swing"] and by["idle"]:
            j = tp / len(by["swing"]) - fp / len(by["idle"])
            if best is None or j > best[0]:
                best = (float(j), float(thr), int(tp), int(fp))
    q = {lab: (np.percentile(v, [5, 25, 50, 75, 95]).round(2).tolist() if v else None)
         for lab, v in by.items()}  # fmt: skip
    out = {"session": sid, "frames": len(frames), "pairs": len(rows), "still_pairs": len(still),
           "n": {k: len(v) for k, v in by.items()}, "quantiles": q,
           "best_youden": None if best is None else {"j": round(best[0], 3), "thr": best[1],
                                                     "tp": best[2], "fp": best[3]}}  # fmt: skip
    (d / "cue.json").write_text(json.dumps({**out, "rows": rows}, default=_plain))
    return out


def _plain(o: Any) -> Any:
    return o.item() if hasattr(o, "item") else str(o)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)  # fmt: skip
    sub = ap.add_subparsers(dest="cmd", required=True)
    m = sub.add_parser("measure")
    m.add_argument("session")
    m.add_argument("--rec", type=Path)
    a = ap.parse_args()
    print(json.dumps(measure(a.session, a.rec), indent=1, default=_plain))
    return 0


if __name__ == "__main__":
    sys.exit(main())
