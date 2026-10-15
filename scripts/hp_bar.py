#!/usr/bin/env python3
"""The monster HP BAR as a pixel cue, measured against packet truth (Batt 2026-10-15 overnight:
"verify the attack started (a PROVEN signal: build and validate the pixel cue against packets
first)"). Found 2026-10-16 01:25 in a hunt@2 frame: this 2021 client draws a bar under a monster
once it has taken damage (a Pupa hit earlier still showed one), 5 px tall, ~45-60 px wide: a
dark border, a navy inside, the HP left as a saturated fill from the left (magenta; yellow when
low). A character's own bars (the GM's HP green / SP blue, under it) are not monster bars.

    hp_bar.py measure SESSION [--frames DIR]    per-engagement timing + per-frame separation

The cue (pixels only, so the bot can use it at run time): a bar whose feet-side centre lies within
ZONE_CELLS of the GM's feet = "our target is damaged". The measurement, offline:
- per successful engagement (3.39's judge): the server's first act of ours on G -> the first
  frame with a bar next to the GM; and bars next to the GM BEFORE the first act (false cues);
- per frame of an engagement: "hit" = an act of ours on G already happened and G is alive;
  "fresh" = no act of ours on any mob yet in this engagement. Youden J of bar-present.
Nothing here decides at run time until a measurement like this one is recorded and passes.
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

BAR_MIN_W = 30  # px: the bar is ~60 px; a nearly empty bar still shows its whole border
GM_FEET = (640.8, 361.9)  # client px at the screen centre (walk5.World.project of our own cell)
CELL_PX = (34.0, 21.5)  # one cell east / south at the centre
ZONE_CELLS = 3.0
GM_AID = 2000002
MIN_INSIDE = 0.6  # the inside row: at least this share navy or fill (not just dark)


def _border(a: Any) -> Any:
    """Dark border pixels (not green-dominant shadowed grass). Over the fill the border is the
    fill's dark shade: dark yellow (50, 41, 0), dark magenta (90, 0, 105)."""
    a = a.astype(np.int16)
    mx = a.max(axis=-1)
    green = (a[..., 1] > a[..., 0] + 10) & (a[..., 1] > a[..., 2] + 10)
    return (mx < 115) & ~green


def zone_roi(cells: float = ZONE_CELLS) -> tuple[int, int, int, int]:
    """(x0, y0, x1, y1): where a bar of a monster within ``cells`` of the GM can lie."""
    u, v = GM_FEET
    return (int(u - cells * CELL_PX[0] - 40), int(v - cells * CELL_PX[1] - 10),
            int(u + cells * CELL_PX[0] + 40), int(v + cells * CELL_PX[1] + 30))  # fmt: skip


def _inside(a: Any) -> Any:
    """Navy (unfilled) or a saturated fill (yellow, magenta, ...; sand is not saturated enough)."""
    a = a.astype(np.int16)
    mx = a.max(axis=-1)
    navy = (mx < 125) & (a[..., 2] >= a[..., 1] - 6) & (a[..., 2] >= a[..., 0] - 12)
    return navy | _fill(a)


def _fill(a: Any) -> Any:
    a = a.astype(np.int16)
    mx, mn = a.max(axis=-1), a.min(axis=-1)
    return (mx > 150) & (mx - mn > 110)


def find_bars(rgb: Any, roi: tuple[int, int, int, int] | None = None
              ) -> list[tuple[int, int, int, float]]:  # fmt: skip
    """(x0, x1, y_top, fill fraction) of every bar in an RGB frame (or its ``roi``; frame
    coordinates either way): a border row, a border row 4 px below over the same columns, and an
    inside row between them."""
    if roi is not None:
        x0r, y0r, x1r, y1r = roi
        return [(x0 + x0r, x1 + x0r, y + y0r, f)
                for x0, x1, y, f in find_bars(np.asarray(rgb)[y0r:y1r, x0r:x1r])]  # fmt: skip
    a = np.asarray(rgb)[..., :3]
    h, _w = a.shape[:2]
    if h < 7:
        return []
    b = _border(a)
    ins = _inside(a)
    # the inside row may hold dark columns (the inner edge, the fill / navy boundary)
    both = b[: h - 4] & b[4:] & (ins | b)[2 : h - 2]
    out: list[tuple[int, int, int, float]] = []
    ys, _xs = np.nonzero(both)
    for y in np.unique(ys):
        if y < 1 or y + 5 >= h:
            continue
        idx = np.flatnonzero(both[y])
        # runs of consecutive columns
        splits = np.flatnonzero(np.diff(idx) > 1)
        starts = np.r_[idx[0], idx[splits + 1]]
        ends = np.r_[idx[splits], idx[-1]]
        for x0, x1 in zip(starts, ends, strict=True):
            if x1 - x0 + 1 < BAR_MIN_W:
                continue
            mid = a[y + 2, x0 : x1 + 1].astype(np.int16)
            fill = _fill(mid)
            if float(ins[y + 2, x0 : x1 + 1].mean()) < MIN_INSIDE:
                continue  # mostly dark inside: a shadow or a UI edge, not a bar
            # exactly 5 px tall: the rows just outside are not border over most columns
            if (float(b[y - 1, x0 : x1 + 1].mean()) > 0.5
                    or float(b[y + 5, x0 : x1 + 1].mean()) > 0.5):  # fmt: skip
                continue
            if fill.any():
                fc = mid[fill]
                gb = ((fc[:, 1] > fc[:, 0] + 40) & (fc[:, 1] > fc[:, 2] + 40)) | (
                    (fc[:, 2] > fc[:, 0] + 40) & (fc[:, 2] > fc[:, 1] + 40)
                )
                if float(gb.mean()) > 0.5:
                    continue  # a green / blue fill: a CHARACTER's HP / SP bar (the GM's own)
            frac = float(fill.mean())
            if any(abs(int(y) - oy) <= 2 and min(x1, ox1) - max(x0, ox0) > 10
                   for ox0, ox1, oy, _ in out):  # fmt: skip
                continue
            out.append((int(x0), int(x1), int(y), round(frac, 3)))
    return out


def near_gm(bar: tuple[int, int, int, float], cells: float = ZONE_CELLS) -> bool:
    """The bar's centre (taken as a monster's feet just above it) within ``cells`` of the GM."""
    x0, x1, y, _ = bar
    u, v = (x0 + x1) / 2, y - 8
    return bool(((u - GM_FEET[0]) / CELL_PX[0]) ** 2 + ((v - GM_FEET[1]) / CELL_PX[1]) ** 2
                <= cells**2)  # fmt: skip


def measure(sid: str, frames_dir: Path | None) -> dict[str, Any]:
    import hunt
    import hunt_core as hc
    from PIL import Image

    from poring_env.demo import DEMO_ROOT

    d = DEMO_ROOT / sid
    man = json.loads((d / "manifest.json").read_text())
    fdir = frames_dir or Path(man.get("frames_dir") or hunt.REC_ROOT / sid / "frames")
    if not fdir.is_dir():
        fdir = hunt.REC_ROOT / sid / "frames"
    frames = sorted((int(f.stem.split("-")[1]), f) for f in fdir.glob("*.jpg"))
    ts = np.array([t for t, _ in frames])
    engs = json.loads((d / "engagements.json").read_text())
    with gzip.open(d / "packets.jsonl.gz", "rt") as fh:
        pk = [json.loads(x) for x in fh]
    rows, per_frame = [], {"hit": [], "fresh": []}
    for e in engs:
        j = hc.judge_engagement({**e, "t_end": e.get("t_loot_end") or e["t_end"]}, pk)
        t_sel, t_end = int(e["t_select"]), int(e.get("t_loot_end") or e["t_end"])
        ours = sorted(
            int(x["t_mono_ns"])
            for x in pk
            if x.get("type") == "act"
            and int(x.get("src_gid", -1)) == GM_AID
            and x.get("kind") != "pickup"
            and t_sel <= int(x["t_mono_ns"]) <= t_end
        )
        t_act = ours[0] if ours else None
        t_death = j.get("t_death")
        lo, hi = np.searchsorted(ts, t_sel), np.searchsorted(ts, t_end)
        first_bar, early = None, 0
        for k in range(lo, hi):
            t, f = frames[k]
            img = np.asarray(Image.open(f).convert("RGB"))
            bars = [b for b in find_bars(img, zone_roi()) if near_gm(b)]
            if t_act is None or t < t_act:
                per_frame["fresh"].append(bool(bars))
                early += bool(bars)
            elif j.get("success") and t_death is not None and t_act + 0.5e9 <= t < t_death:
                per_frame["hit"].append(bool(bars))
            if bars and t_act is not None and t >= t_act and first_bar is None:
                first_bar = t
        rows.append({"k": e["k"], "why": j["why"], "act": t_act is not None,
                     "act_to_bar_s": None if first_bar is None or t_act is None
                     else round((first_bar - t_act) / 1e9, 2),
                     "bars_before_act": early})  # fmt: skip
    hit, fresh = per_frame["hit"], per_frame["fresh"]
    tpr = float(np.mean(hit)) if hit else None
    fpr = float(np.mean(fresh)) if fresh else None
    out = {"session": sid, "frames": len(frames), "engagements": len(rows),
           "hit_frames": len(hit), "fresh_frames": len(fresh), "tpr": tpr, "fpr": fpr,
           "youden_j": None if tpr is None or fpr is None else round(tpr - fpr, 3),
           "act_to_bar_s": sorted(r_["act_to_bar_s"] for r_ in rows
                                  if r_["act_to_bar_s"] is not None),
           "rows": rows}  # fmt: skip
    (d / "hp_bar.json").write_text(json.dumps(out))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)  # fmt: skip
    sub = ap.add_subparsers(dest="cmd", required=True)
    m = sub.add_parser("measure")
    m.add_argument("session")
    m.add_argument("--frames", type=Path)
    a = ap.parse_args()
    out = measure(a.session, a.frames)
    print(json.dumps({k: v for k, v in out.items() if k != "rows"}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
