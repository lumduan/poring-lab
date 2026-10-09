#!/usr/bin/env python3
"""The GM's FIXED TEST STATE (Batt 2026-10-09 ~16:00): restored at every run start (and at every
loot@1 trial start), checked from pixels, and recorded.

Why: loot@1's pilot 2 killed a Poring and the GM levelled up (Base Lv 1 -> 2; HP 40 -> 45, status
points, the client's level-up icon and badges). "The GM's level is now an uncontrolled variable.
Restore a fixed test state (reset or set the level/points by GM command, clear the badges by known
steps) and record the GM's state at each run start."

The fixed state: Base Lv 1 and Job Lv 1, full HP / SP (@heal). Lowering a level by
`@baselevelup -N` / `@joblevelup -N` takes back that level's status / skill points and sets the EXP
to 0 (pinned rAthena atcommand.cpp, ACMD_FUNC(baselevelup)); group 20 has both commands since
2026-10-09 (groups.yml). At Lv 1 the server answers "can't go any lower" and changes nothing.
Job EXP is NOT fixed (it keeps rising at Job Lv 1): it is recorded, not restored.

The check (pixels, two fresh frames that must agree): the Basic Information window's two level
lines ("Base Lv. N" / "Job Lv. N" text, left of the EXP bars) against a template cut once at
Lv 1 / 1, by the COUNT of strongly differing pixels (`gm_state.py cut`, data/ui_anchors/gm_state/,
client pixels: gitignored). The badges and the
level-up icon cleared when the status window opened (2026-10-09 16:02, ui_gate prove-windows):
the gate's known step, not checked here (no template of them).

The record (every run start): the match distance, whether a restore was needed, the weight readout
(poring_env.weight, two equal reads) and a crop of the Basic Information window (in the session
dir). The packets judge offline: after a restore the server sends the new levels and points.

    gm_state.py check     read only: the level lines vs the template
    gm_state.py restore   ensure_fixed once (types the restore lines only when the check fails)
    gm_state.py cut       cut the Lv 1 / 1 template from the CURRENT frame (a person has checked
                          the screen shows Base Lv. 1 and Job Lv. 1)
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ro_agent as r  # noqa: E402

# client px (basic_info at its home (0, 0)): the "Base Lv. N" / "Job Lv. N" text, left of the
# EXP bars (measured 2026-10-09 on RDP frames: text x 16-72, rows y 87-97 and 98-108)
LEVEL_BOX = (14, 85, 68, 25)  # x, y, w, h
BASIC_INFO_BOX = (0, 0, 220, 140)
TEMPLATE = r.ROOT / "data" / "ui_anchors" / "gm_state" / "levels_1_1.npy"
# A mean difference over the box dilutes one changed digit (~20 ink px of ~1700): count the pixels
# that differ strongly instead. RDP codec noise stays far below DIFF_LEVEL; a changed digit gives
# tens of such pixels.
DIFF_LEVEL = 60.0  # gray levels
MATCH = 4  # at most this many strongly differing pixels
RESTORE = ("@baselevelup -98", "@joblevelup -49", "@heal")
SETTLE_S = 2.0


def to_gray(bgr: Any) -> Any:
    return np.asarray(bgr[..., :3], np.float32) @ np.array([0.114, 0.587, 0.299], np.float32)


def crop(frame: Any, box: tuple[int, int, int, int] = LEVEL_BOX) -> Any:
    x, y, w, h = box
    return to_gray(frame)[y : y + h, x : x + w]


def distance(frame: Any, template: Any) -> float:
    """The number of pixels of the level lines that differ from the template by > DIFF_LEVEL."""
    c = crop(frame)
    if c.shape != template.shape:
        return float("inf")
    return float((np.abs(c - template) > DIFF_LEVEL).sum())


def decide(d1: float, d2: float) -> str:
    """PURE: 'fixed' when both frames match, 'restore' when both differ, 'unstable' otherwise."""
    if d1 <= MATCH and d2 <= MATCH:
        return "fixed"
    if d1 > MATCH and d2 > MATCH:
        return "restore"
    return "unstable"


def _frames(screen: Any) -> tuple[Any, Any]:
    a = np.ascontiguousarray(r.grab_after(screen, r.game_region(), r.ns())[..., :3])
    b = np.ascontiguousarray(r.grab_after(screen, r.game_region(), r.ns())[..., :3])
    return a, b


def _template() -> Any:
    if not TEMPLATE.exists():
        raise r.Stop(f"gm_state: no Lv 1 / 1 template ({TEMPLATE}): run `gm_state.py cut` first")
    return np.load(TEMPLATE)


def check(screen: Any) -> dict[str, Any]:
    t = _template()
    a, b = _frames(screen)
    d1, d2 = distance(a, t), distance(b, t)
    return {"decision": decide(d1, d2), "dist": [round(d1, 2), round(d2, 2)], "frames": (a, b)}


def _weight(frames: tuple[Any, Any]) -> list[int] | None:
    """The weight readout, two equal reads on the two frames (poring_env.weight), or None."""
    from poring_env import weight as wt

    glyphs = wt.load_weight_glyphs(r.ROOT / wt.DEFAULT_TEMPLATES)
    v = wt.stable_value([wt.read_weight(f, glyphs) for f in frames])
    return None if v is None else list(v)


def ensure_fixed(agent: Any, screen: Any, *, why: str,
                 out_dir: Path | None = None) -> dict[str, Any]:  # fmt: skip
    """The fixed state, restored by GM command when the level lines differ; else r.Stop."""
    rec: dict[str, Any] = {"why": why, "t_ns": r.ns(), "restored": False}
    got = check(screen)
    if got["decision"] == "unstable":
        time.sleep(0.5)
        got = check(screen)
    rec["before"] = got["dist"]
    if got["decision"] != "fixed":
        for cmd in RESTORE:
            r.gm(agent, screen, cmd)
        time.sleep(SETTLE_S)
        rec["restored"] = True
        got = check(screen)
        rec["after"] = got["dist"]
        if got["decision"] != "fixed":
            raise r.Stop(f"gm_state ({why}): the GM is not at Base Lv 1 / Job Lv 1 after "
                         f"the restore (differing px {got['dist']}, match <= {MATCH})")  # fmt: skip
    frame = got["frames"][1]
    rec["weight"] = _weight(got["frames"])
    if out_dir is not None:
        out_dir.mkdir(parents=True, exist_ok=True)
        x, y, w, h = BASIC_INFO_BOX
        path = out_dir / f"gm-state-{rec['t_ns']}.png"
        r.to_png(np.ascontiguousarray(frame[y : y + h, x : x + w]), path)
        rec["basic_info_crop"] = str(path)
    rec["fixed"] = True
    return rec


def main() -> int:
    cmd = sys.argv[1:]
    if cmd not in (["check"], ["restore"], ["cut"]):
        print(__doc__)
        return 2
    with r.session("gm-state") as (agent, screen):
        if cmd == ["cut"]:
            frame = np.ascontiguousarray(r.grab_after(screen, r.game_region(), r.ns())[..., :3])
            TEMPLATE.parent.mkdir(parents=True, exist_ok=True)
            np.save(TEMPLATE, crop(frame))
            r.to_png(np.ascontiguousarray(frame[:140, :220]), TEMPLATE.with_suffix(".png"))
            print(json.dumps({"cut": str(TEMPLATE), "check": str(TEMPLATE.with_suffix(".png"))}))
        elif cmd == ["check"]:
            got = check(screen)
            got.pop("frames")
            print(json.dumps(got))
        else:
            rec = ensure_fixed(agent, screen, why="cli")
            print(json.dumps(rec))
    return 0


if __name__ == "__main__":
    sys.exit(main())
