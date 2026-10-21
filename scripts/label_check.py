#!/usr/bin/env python3
"""Phase 3 M5's automatic label check (docs/phase3-plan.md §6): does the client draw the predicted
sprite where a v1 label says it is?

    label_check.py check SESSION --tau T [--k K] [--every 15] [--out data/bench/...json]

The score is a masked normalised cross-correlation (grey levels) between the RENDERED sprite (its
SPR pixels composed by the ACT, scaled about the projected anchor like predict_sprite's mask) and
the frame's pixels under the sprite's opaque mask. NCC ignores a brightness/contrast change (map
lighting, tint). When the frame of the action is unknown (idle/walk: the envelope), the best score
over the action's frames counts.

tau is FIXED BEFORE M5 from M4's clean standing frames (`m4_validate.py --rerun --ncc`: the 5th
percentile), never from the data it then judges. A label scoring below tau is:
- `occluded`: another monster's predicted box overlaps it;
- `ui_covered`: it touches a client UI window;
- `bad_label`: anything else (a timing/offset error, or the client drew nothing there).
`bad_label` labels are dropped and counted; the pre-registered gate is < 2 % of the standing
labels on the M4 session.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import numpy as np
import numpy.typing as npt

sys.path.insert(0, str(Path(__file__).resolve().parent))

from poring_dataset.render import SpritePrediction, SpriteSheet  # noqa: E402
from poring_dataset.sprites import compose_frame  # noqa: E402
from poring_dataset.ui_layout import UI_RECTS, covered_fraction  # noqa: E402

MIN_PIXELS = 30  # fewer opaque pixels on screen than this: no score
GREY = np.array([0.299, 0.587, 0.114])


def rendered(sheet: SpriteSheet, action_index: int, motion: int, anchor: tuple[float, float],
             scale: float, window: tuple[int, int, int, int]
             ) -> tuple[npt.NDArray[np.float64], npt.NDArray[np.bool_]]:  # fmt: skip
    """(grey, opaque) of one motion over the screen pixel window (i0, j0, i1, j1): each pixel centre
    mapped back to sprite px about the anchor, the nearest canvas pixel (as render._screen_mask)."""
    if sheet.spr is None:
        raise ValueError("rendering needs the decoded SPR")
    i0, j0, i1, j1 = window
    rgba, (ox, oy) = compose_frame(sheet.spr, sheet.act, action_index, motion)
    grey = np.zeros((j1 - j0, i1 - i0))
    opaque = np.zeros((j1 - j0, i1 - i0), bool)
    if not rgba.size:
        return grey, opaque
    cx = np.floor((np.arange(i0, i1) + 0.5 - anchor[0]) / scale + ox).astype(np.int64)
    cy = np.floor((np.arange(j0, j1) + 0.5 - anchor[1]) / scale + oy).astype(np.int64)
    okx = (cx >= 0) & (cx < rgba.shape[1])
    oky = (cy >= 0) & (cy < rgba.shape[0])
    sub = rgba[np.ix_(cy[oky], cx[okx])]
    grey[np.ix_(oky, okx)] = sub[..., :3] @ GREY
    opaque[np.ix_(oky, okx)] = sub[..., 3] > 0
    return grey, opaque


def ncc(a: npt.NDArray[np.float64], b: npt.NDArray[np.float64], mask: npt.NDArray[np.bool_]
        ) -> float | None:  # fmt: skip
    """Masked normalised cross-correlation in [-1, 1]; None below MIN_PIXELS or with no variance."""
    if int(mask.sum()) < MIN_PIXELS:
        return None
    x, y = a[mask] - a[mask].mean(), b[mask] - b[mask].mean()
    den = math.sqrt(float((x * x).sum()) * float((y * y).sum()))
    return None if den == 0 else float((x * y).sum() / den)


def score(frame: npt.NDArray[np.uint8], sheet: SpriteSheet, pred: SpritePrediction) -> float | None:
    """The label's NCC: the known frame, else the best over the action's frames."""
    h, w = frame.shape[:2]
    i0, j0 = max(0, math.floor(pred.box[0])), max(0, math.floor(pred.box[1]))
    i1, j1 = min(w, math.ceil(pred.box[2])), min(h, math.ceil(pred.box[3]))
    if i1 - i0 < 2 or j1 - j0 < 2:
        return None
    observed = frame[j0:j1, i0:i1, :3].astype(float) @ GREY
    motions = [pred.motion] if pred.motion is not None else range(sheet.motions(pred.action_index))
    best: float | None = None
    for m in motions:
        grey, opaque = rendered(sheet, pred.action_index, int(m), pred.anchor_px, pred.scale,
                                (i0, j0, i1, j1))  # fmt: skip
        s = ncc(observed, grey, opaque)
        if s is not None and (best is None or s > best):
            best = s
    return best


def classify(box: tuple[float, float, float, float],
             others: list[tuple[float, float, float, float]],
             rects: tuple[tuple[int, int, int, int], ...] = UI_RECTS) -> str:  # fmt: skip
    """Why a low-scoring label scored low (the order is the spec's). ``rects``: the client's UI
    windows (x, y, w, h) of the session's layout (default: the frozen standard set)."""
    for o in others:
        if min(box[2], o[2]) > max(box[0], o[0]) and min(box[3], o[3]) > max(box[1], o[1]):
            return "occluded"
    if covered_fraction(box, rects) > 0:
        return "ui_covered"
    return "bad_label"


def cmd_check(a: argparse.Namespace) -> int:
    import qa_export

    from poring_dataset.h264 import H264Session
    from poring_dataset.labels import ONE_SHOT, STATE_ACTION
    from poring_dataset.render import Actor, load_scene, predict_sprite

    session = a.datasets / a.session
    lab = qa_export.Labeler(session, labels="v1", **({"k": a.k} if a.k is not None else {}))
    stream = H264Session(session)
    counts: dict[str, int] = {"standing": 0, "scored": 0, "low": 0, "occluded": 0,
                              "ui_covered": 0, "bad_label": 0}  # fmt: skip
    usable = set(stream.usable())
    ids = [u.frame_id for u in stream.units if u.frame_id in usable][:: a.every]
    off = int(lab.offset_ms * 1e6)
    for meta, frame in stream.frames(ids, verify=False):
        t = int(meta["t_mono_ns"])
        boxes = lab.boxes(t)
        if not boxes:
            continue
        world = lab.timeline.frame_world(t - off)
        if world.self_pos is None or world.map is None:
            continue
        scene = load_scene(lab.camera, world.map, world.self_pos, indoor_table=lab.indoor)
        ents = {e.gid: e for e in world.entities}
        mons = [b for b in boxes if b["cls"] == "monster" and b["kind"] == "opaque"]
        for b in mons:
            if b["state"] != "idle":
                continue  # the gate counts STANDING labels
            ent, st = ents.get(b["gid"]), lab.timeline.state(b["gid"], t - off)
            sheet = lab.sheets(ent.job) if (ent is not None and lab.sheets) else None
            if ent is None or st is None or sheet is None:
                continue
            counts["standing"] += 1
            action = STATE_ACTION.get(st.state)
            elapsed = st.elapsed_ms if action in ONE_SHOT else None
            pred = predict_sprite(Actor((float(ent.x), float(ent.y)), int(st.facing or 0),
                                        int(action or 0), elapsed_ms=elapsed),
                                  sheet, scene, lab.k)  # fmt: skip
            if pred is None:
                continue
            s = score(frame, sheet, pred)
            if s is None:
                continue
            counts["scored"] += 1
            if s < a.tau:
                counts["low"] += 1
                others = [(o["x1"], o["y1"], o["x2"], o["y2"]) for o in mons if o is not b]
                counts[classify((b["x1"], b["y1"], b["x2"], b["y2"]), others)] += 1
    result = {"session": a.session, "tau": a.tau, "k": lab.k, "every": a.every, **counts,
              "bad_label_share": round(counts["bad_label"] / max(1, counts["scored"]), 4),
              "pass_lt_2pct": counts["bad_label"] < 0.02 * max(1, counts["scored"])}  # fmt: skip
    text = json.dumps(result, indent=1)
    if a.out:
        a.out.parent.mkdir(parents=True, exist_ok=True)
        a.out.write_text(text + "\n")
    print(text)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check")
    c.add_argument("session")
    c.add_argument("--tau", type=float, required=True)
    c.add_argument("--k", type=float, default=None)
    c.add_argument("--every", type=int, default=15)
    c.add_argument("--datasets", type=Path, default=Path("/mnt/poring-lab-datasets"))
    c.add_argument("--out", type=Path, default=None)
    a = ap.parse_args()
    return cmd_check(a)


if __name__ == "__main__":
    sys.exit(main())
