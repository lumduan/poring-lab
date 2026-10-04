#!/usr/bin/env python3
"""The GM's vitals from PIXELS, for the dataset activity driver (Phase 3 Part C, Batt 2026-10-04:
the GM survives, and the driver never clicks a monster). No packets at decision time (rule 1).

    gm_vitals.py cut-dead-signature SESSION FRAME_ID
        Save the death dialog's signature (ro_agent's format, data/ro_agent/signatures/, gitignored:
        client pixels) from a recorded H.264 frame that shows it.

- HP: the basic_info window's HP bar (ui_anchors `hp_bar`; basic_info sits at the game region's
  origin in the frozen layout). Calibrated 2026-10-04 on p3-indoor-b against the packets' HP:
  40/40 fills 0.85 of the crop's columns (the bar's frame takes the rest), 21 -> 0.53, 15 -> 0.37,
  9 -> 0.28, 4 -> the bar turns RED and thin (0.02). So the fraction is monotonic but coarse at the
  bottom.
- DEATH is NOT readable from the bar: after the GM died the client showed 20/40 while it lay dead.
  The signal is the "Game option" death dialog ("move to saved location" / "return to game"),
  game region (505, 450, 280, 70). GM chat commands still work while it is open (p3-indoor-b kept
  spawning), so the recovery is @alive, @heal, then the scene again; if the dialog stays, its
  SECOND button ("return to game") closes it. Never Enter, never the first button (a respawn
  elsewhere).
- A walk target is clicked only when a SECOND fresh frame still shows the ground marker there and
  little moved in the crop between the two frames (a monster walking in): see `motion_fraction`.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import numpy.typing as npt

HP_BAR = (35, 53, 135, 9)  # game-region x, y, w, h (ui_anchors.py hp_bar; basic_info at (0, 0))
HP_FULL_FILL = 0.85  # the share of bar columns lit at 40/40 (calibration above)
HEAL_BELOW = 0.6  # of max HP
DEAD_STATE = "dead_game_option"
DEAD_BOX = [505, 450, 280, 70]  # game region: the death dialog (title + two buttons)
RETURN_TO_GAME = (645, 503)  # game region: its second button's centre ("return to game")
MOTION_DIFF = 40  # grey levels: a pixel that changed between the two frames
MOTION_MAX = 0.08  # share of changed pixels in the crop that rejects a target
CURSOR_BOX = (0, 0, 40, 40)  # the animated cursor, relative to the crop's centre (excluded)

Img = npt.NDArray[np.uint8]


def hp_fraction(game_bgr: Img) -> float:
    """0..1 of max HP from the bar: lit (blue, or red when low) columns over the full-HP share."""
    x, y, w, h = HP_BAR
    col = game_bgr[y : y + h, x : x + w, :3].astype(np.float64).mean(axis=0)  # per column B, G, R
    blue = (col[:, 0] > col[:, 2] + 40) & (col[:, 0] > 100)
    red = (col[:, 2] > col[:, 0] + 40) & (col[:, 2] > 100)
    return float(min(1.0, (blue | red).mean() / HP_FULL_FILL))


def vitals_action(hp: float | None, dead: bool, heal_below: float = HEAL_BELOW) -> str | None:
    """The recovery: "revive" (the death dialog is up), "heal" (HP below the threshold), or None."""
    if dead:
        return "revive"
    if hp is not None and hp < heal_below:
        return "heal"
    return None


def motion_fraction(a: Img, b: Img) -> float:
    """Share of pixels that changed between two crops of the same target, ignoring the animated
    cursor at the centre and the ground marker's own pulse (its mint pixels in either frame)."""
    ga = a[..., :3].astype(np.int16).mean(axis=2)
    gb = b[..., :3].astype(np.int16).mean(axis=2)
    changed = np.abs(ga - gb) > MOTION_DIFF
    keep = ~(marker_mask(a) | marker_mask(b))
    h, w = changed.shape
    cx, cy = w // 2, h // 2
    dx, dy, cw, ch = CURSOR_BOX
    keep[max(0, cy + dy) : cy + dy + ch, max(0, cx + dx) : cx + dx + cw] = False
    n = int(keep.sum())
    return float((changed & keep).sum() / n) if n else 1.0


def marker_mask(crop: Img) -> npt.NDArray[np.bool_]:
    """The ground marker's mint pixels (empty_cell.marker_px's colour rule, as a mask)."""
    px = crop[..., :3].astype(np.int16)
    b, g, r = px[..., 0], px[..., 1], px[..., 2]
    return (g - r > 40) & (b - r > 10) & (g > 110) & (g - b > 10) & (b > 70)  # type: ignore[no-any-return]


def cut_dead_signature(session: Path, frame_id: int) -> Path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import ro_agent as r

    from poring_dataset.h264 import H264Session

    ((_, img),) = list(H264Session(session).frames([frame_id], verify=False))
    x, y, w, h = DEAD_BOX
    path = r.signature_path(DEAD_STATE)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.with_suffix(".json").write_text(json.dumps({"box": DEAD_BOX}))
    np.save(path, r.grey_thumb(np.ascontiguousarray(img[y : y + h, x : x + w])))
    back = np.load(path)
    assert back.size > 0 and json.loads(path.with_suffix(".json").read_text())["box"] == DEAD_BOX
    return path


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    cut = sub.add_parser("cut-dead-signature")
    cut.add_argument("session", type=Path)
    cut.add_argument("frame_id", type=int)
    a = ap.parse_args()
    print(cut_dead_signature(a.session, a.frame_id))
    return 0


if __name__ == "__main__":
    sys.exit(main())
