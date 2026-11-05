#!/usr/bin/env python3
"""loot@1 P5: the client's own "item obtained" line in the chat log, from PIXELS (Batt 2026-10-08:
the backup cue for a pickup, next to the weight readout).

The client writes a CYAN line when an item ENTERS the inventory (a pickup, an `@item`), and a cyan
line too when one LEAVES it (a drop). The two differ only in their first words. So:
- the newest COLOURED line of the log is found first (cyan, green, yellow or red; white is left
  out: the scene behind the window has white highlights); it must be cyan;
- its leading glyphs (PREFIX_PX from its first ink column) are matched against two masks cut
  LOCALLY from known frames (`cut`): a "got" line and a "dropped" line. They are client pixels in
  data/ (gitignored), never committed. The text itself is never stored (rule 4);
- the cue fires only when the chat area CHANGED between the frame before the click and the frame
  after it, AND the newest line is a "got" line.

    chat_cue.py cut GOT_FRAME DROPPED_FRAME [--out data/ui_anchors/chat_cues.npz]
    chat_cue.py check BEFORE_FRAME AFTER_FRAME [--cues ...]   -> {"cue": bool, ...}

Frames: client-area PNGs (1280 x 720, RGB as saved by ro_agent.to_png).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
CUES = ROOT / "data/ui_anchors/chat_cues.npz"
# client px: the message lines only, chat_window.active().cue_area: (0, 545, 570, 593) in the
# frozen layout, (0, 598, 570, 688) in the chat window's 2026-11-05 standard. NOT where_fix's area:
# that one holds the scrollbar's white arrows (x ~585) and the input box's white border, which a
# text mask reads as a newer "line" (the 2026-10-09 00:41 negative case, in demonstrations.md)
LINE_PITCH = 14
PREFIX_PX = 48  # "<first word> <second word>" of the two cues, from the first ink column
MATCH_IOU = 0.8  # the best shifted IoU a line's prefix must reach against a template
SHIFT = 1  # px: the template is tried at +-SHIFT in x and y
CHANGED_PX = 40  # coloured text pixels that must differ for "a new line"


def _area() -> tuple[int, int, int, int]:
    sys.path.insert(0, str(ROOT / "scripts"))
    import chat_window

    return chat_window.active().cue_area


def area_of(rgb: np.ndarray) -> np.ndarray:
    x0, y0, x1, y1 = _area()
    return np.asarray(rgb)[y0:y1, x0:x1, :3].astype(np.int32)


def cyan(area: np.ndarray) -> np.ndarray:
    r, g, b = area[..., 0], area[..., 1], area[..., 2]
    return (g > 190) & (b > 190) & (r < 130)


def coloured(area: np.ndarray) -> np.ndarray:
    """The client's COLOURED message text: cyan (items), green (notices), yellow, red. Never white:
    the darkened scene behind the semi-transparent window has white highlights that move while we
    walk (1,039 changed white pixels on one walk click, 2026-10-09 00:41, with no new line)."""
    r, g, b = area[..., 0], area[..., 1], area[..., 2]
    green = (g > 200) & (r < 120) & (b < 120)
    yellow = (r > 200) & (g > 200) & (b < 120)
    red = (r > 200) & (g < 100) & (b < 100)
    return cyan(area) | green | yellow | red


def _bottom(mask: np.ndarray) -> int | None:
    rows = np.nonzero(mask.sum(1) >= 3)[0]
    return int(rows[-1]) if len(rows) else None


def newest_prefix(area: np.ndarray) -> tuple[np.ndarray | None, str]:
    """The newest line's leading PREFIX_PX columns as a cyan mask (LINE_PITCH x PREFIX_PX), or
    (None, why)."""
    bottom = _bottom(coloured(area))
    if bottom is None:
        return None, "no_text"
    cy = cyan(area)
    cb = _bottom(cy)
    if cb is None or abs(cb - bottom) > 2:
        return None, "newest_not_cyan"
    top = max(0, bottom - LINE_PITCH + 1)
    line = cy[top : bottom + 1]
    cols = np.nonzero(line.any(0))[0]
    if len(cols) == 0:
        return None, "no_ink"
    x0 = int(cols[0])
    out = np.zeros((LINE_PITCH, PREFIX_PX), bool)
    part = line[:, x0 : x0 + PREFIX_PX]
    out[LINE_PITCH - part.shape[0] :, : part.shape[1]] = part
    return out, "ok"


def iou(a: np.ndarray, t: np.ndarray) -> float:
    """The best IoU of a against t over +-SHIFT px."""
    best = 0.0
    for dy in range(-SHIFT, SHIFT + 1):
        for dx in range(-SHIFT, SHIFT + 1):
            s = np.roll(np.roll(t, dy, axis=0), dx, axis=1)
            union = int((a | s).sum())
            if union:
                best = max(best, int((a & s).sum()) / union)
    return best


def classify(area: np.ndarray, cues: dict[str, np.ndarray]) -> dict[str, Any]:
    p, why = newest_prefix(area)
    if p is None:
        return {"kind": None, "why": why}
    scores = {k: round(iou(p, t), 3) for k, t in cues.items()}
    best = max(scores, key=lambda k: scores[k])
    kind = best if scores[best] >= MATCH_IOU else "other_cyan"
    return {"kind": kind, "scores": scores}


def check(before_rgb: np.ndarray, after_rgb: np.ndarray, cues: dict[str, np.ndarray]
          ) -> dict[str, Any]:  # fmt: skip
    a, b = area_of(before_rgb), area_of(after_rgb)
    # COLOURED text pixels only: the scene scrolls behind the semi-transparent window while we
    # walk, and moves thousands of raw (and white) pixels without any new line
    changed = int((coloured(a) ^ coloured(b)).sum())
    got = classify(b, cues)
    return {"cue": bool(changed >= CHANGED_PX and got["kind"] == "got"), "changed_px": changed,
            **got}  # fmt: skip


def load_cues(path: Path = CUES) -> dict[str, np.ndarray]:
    with np.load(path) as z:
        return {k: z[k].astype(bool) for k in z.files}


def _rgb(path: str) -> np.ndarray:
    from PIL import Image

    return np.asarray(Image.open(path).convert("RGB"))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("cut")
    c.add_argument("got")
    c.add_argument("dropped")
    c.add_argument("--out", type=Path, default=CUES)
    k = sub.add_parser("check")
    k.add_argument("before")
    k.add_argument("after")
    k.add_argument("--cues", type=Path, default=CUES)
    a = ap.parse_args()
    if a.cmd == "cut":
        got, why_g = newest_prefix(area_of(_rgb(a.got)))
        dropped, why_d = newest_prefix(area_of(_rgb(a.dropped)))
        if got is None or dropped is None:
            print(json.dumps({"error": "no cyan newest line", "got": why_g, "dropped": why_d}))
            return 1
        a.out.parent.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(a.out, got=got, dropped=dropped)
        print(json.dumps({"out": str(a.out), "got_px": int(got.sum()),
                          "dropped_px": int(dropped.sum()),
                          "got_vs_dropped_iou": round(iou(got, dropped), 3)}))  # fmt: skip
        return 0
    print(json.dumps(check(_rgb(a.before), _rgb(a.after), load_cues(a.cues))))
    return 0


if __name__ == "__main__":
    sys.exit(main())
