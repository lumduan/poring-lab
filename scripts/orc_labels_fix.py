#!/usr/bin/env python3
"""THE ORCSDUN01 LABEL FIX, "labels v2orc-fix" (docs/planning/orcsdun01-detector.md section 3b,
PRE-REGISTERED 2026-10-21 16:52 ICT before this was built; the bars are sections 3 and 5's and are
never tuned here).

    orc_labels_fix.py offset SESSION --out JSON          1d: the packet -> frame offset (col3 ONLY)
    orc_labels_fix.py anchor SESSION --offset JSON --out JSON
                                                         1b: the flyers' drawn anchor (col3 ONLY)
    orc_labels_fix.py freeze --offset JSON --anchor JSON --out PARAMS
                                                         the frozen parameters (before col1)
    orc_labels_fix.py check SESSION --params PARAMS --out JSON
                                                         C1 / C2 on col1, judging the PREDICTION
The labels themselves (the fitted boxes) are built by ``orc_label_sheets.py --fix PARAMS`` with
``FixLabeler`` below, which also writes the blind pack.

OFFLINE ONLY (ADR-0007: packets are ground truth for labels, never an agent input): the session's
packets, its JPEG shards (read-only, NAS), the local KB, the decoded sprites and the map's RSW /
RSM models (client data, /dev/shm only; poring_dataset.rsw). No GPU, no client. The TEST block
(col2) is refused by name: it is not read at all.

The fix (3b), as built here:
- 1a FACING: a unit whose last move has ENDED faces that move's direction from -> to, kept until a
  newer turn / attack changes it (timeline.walk_rule_facing); a walking unit, or one with no
  ended move, keeps the Timeline's facing. The best of the 8 drawn views is REPORTED per species
  (agreement with the rule), never used.
- 1b ANCHOR (flyers 1005 / 1042 / 1111): the per-species median best-NCC offset (dx, dy) of
  STANDING units (section 3's standing rule, C2's +-16 px search, facing 1a, time 1d), measured on
  col3. Applied as a screen shift of the rendered sprite, every action.
- 1c OCCLUSION: every RSW model of the map, projected with the same camera (its vertices' screen
  box); a label whose predicted sprite box overlaps one is EXCLUDED (``occluded_model``). The
  check excludes it before scoring; the 1b / 1d measurements on col3 exclude it too.
- 1d OFFSET: moving GROUND walkers (Orc Zombie 1153, Orc Skeleton 1152: no anchor of their own to
  confound it) that walk ONE move through the whole sweep, isolated and clear of UI / edges; per
  offset, the rendered walk sprite at the packet position is searched +-16 px, and the error is
  the best-NCC offset's length; the offset with the smallest MEDIAN error wins (a coarse 50 ms
  sweep 0..1000, then 10 ms within +-50 of its best). It replaces 375.9 ms (RDP v2 baseline p50).
- 0 BOXES FROM SPRITES (labels): the expected sprite (species; the action of the Timeline state;
  facing 1a; the frame of a one-shot action from its elapsed time, a looping one's best-fitting
  frame) at the projected position + 1b at the 1d time; the LABEL box = that frame's rendered box
  shifted by the best masked-NCC offset within +-6 px (ground) / +-10 px (flyers), the NCC over
  the visible pixels only (inside the frame, outside the UI); a fit below tau 0.092, at the search
  edge, or unscorable = EXCLUDED (reason ``crowd`` when its box overlaps another unit's, ``ui``
  when its window touches a UI window, else ``unfit``). A frame with an EXCLUDED monster is not
  labelled completely, so it is excluded (section 5: "labelled completely or EXCLUDED").

FIX 2, "labels v2orc-fix2" (3f, PRE-REGISTERED 2026-10-22 19:33:52 ICT, 8b7d629, before it was
built): ``check --rule fix2`` / ``orc_label_sheets.py --fix PARAMS --rule fix2``. Only the facing
changes (orc_facing_study.fix2_heading, reused): (i) appeared standing -> the Timeline's facing (the
appear heading), (ii) WALKING -> the quadrant diagonal of its move's vector, (iii) after an ended
move (3b's walk rule) -> its map_calc_dir heading taken to the diagonal. Excluded (as unfit):
2b ``next_move``, a unit whose next move packet arrives < 150 ms after the label's timeline time;
2c ``ambiguous_view``, an (iii) unit after a MIXED move whose two candidate images differ. 1b-1d,
tau, k and the fit radius stay 3c's frozen values.

3i (PRE-REGISTERED 2026-10-23 22:46:39 ICT, 0f039b9, before it was built), Batt's decision 5:
- W (``wing``), the Familiar 1005 / Drainliar 1111 only: the union of the PLAUSIBLE frames' boxes
  (own fit >= the best - 0.05, not at the search edge, each at its own offset) + 2 px, clipped;
  it changes the box only.
- the occlusion candidates (``occlusion``): 1c (3b's literal rule), o3 (an under-box label is
  kept when its fit passes, else ``occluded_model``), o3h (o3 with the under-box fit NCC >=
  0.48); ``stack`` (S3): kept labels whose FITTED boxes (before W) overlap by IoU >= 0.30 are
  both excluded (``stacked``). ``check --occlusion`` scores C1 on the standing labels the
  candidate keeps (S3 never changes C1). decide() gives any candidate's verdict from a frame's
  LabelFates (one pass for round 4's pack: orc_label_sheets.py --round4).

C1 / C2 (the check) judge the PREDICTION, never the fitted box: C1 = label_check.score of the
prediction at its projected position; C2 = its best-NCC offset within +-16 px. The standing rule,
the bars and their summary are scripts/orc_camera_check.py's, unchanged.
"""

from __future__ import annotations

import argparse
import bisect
import functools
import hashlib
import json
import math
import statistics
import subprocess
import sys
import time
from collections import Counter, defaultdict
from collections.abc import Iterator, Sequence
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

import numpy as np
import numpy.typing as npt

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import label_check  # noqa: E402
import orc_camera_check as occ  # noqa: E402
import qa_export  # noqa: E402

from poring_dataset import rsw as rswmod  # noqa: E402
from poring_dataset.camera import displayed_direction, map_key  # noqa: E402
from poring_dataset.labels import ONE_SHOT, STATE_ACTION, in_windows  # noqa: E402
from poring_dataset.render import (  # noqa: E402
    Actor,
    MonsterAction,
    Scene,
    SpritePrediction,
    SpriteSheet,
    anchor_and_depth,
    predict_sprite,
)
from poring_dataset.timeline import (  # noqa: E402
    ActorState,
    EntityState,
    FrameWorld,
    Timeline,
    tick_of,
)
from poring_dataset.ui_layout import covered_fraction  # noqa: E402
from poring_packets.world import World, ticks_since  # noqa: E402

MAP = occ.MAP
K = occ.K_V1
TAU = occ.TAU_M4
GROUND, FLYERS = occ.GROUND, occ.FLYERS
WALKERS = (1153, 1152)  # the ground species that move (the plants never do)
FIT_PX = {**{m: 6 for m in GROUND}, **{m: 10 for m in FLYERS}}
SEARCH_PX = occ.SEARCH_PX  # C2's search, also 1b's and 1d's
COARSE_MS = tuple(range(0, 1001, 50))
FINE_STEP_MS, FINE_SPAN_MS = 10, 50
OLD_OFFSET_MS = 375.9  # the 2026-10-02 RDP v2 baseline p50 the fix replaces
RSW_PATH = Path("/dev/shm/poring-lab-tmp/orc/gat/data/orcsdun01.rsw")
MODEL_DIR = Path("/dev/shm/poring-lab-tmp/orc-labels-fix/grf/data/model")
MAP_CELLS = (200, 200)
TEST_BLOCK_SUFFIX = "-col2"  # the pre-registered TEST block: never read here

Box = tuple[float, float, float, float]
UiRects = tuple[tuple[int, int, int, int], ...]


# --- pure parts -------------------------------------------------------------------------------


def refuse_test_block(session: Path) -> None:
    if session.name.endswith(TEST_BLOCK_SUFFIX) or session.name.rstrip("/").endswith("col2"):
        raise SystemExit(f"{session.name}: the pre-registered TEST block (col2) is not read")


def shifted(pred: SpritePrediction, dx: float, dy: float) -> SpritePrediction:
    """The same prediction drawn (dx, dy) px off (1b's anchor, or a fit)."""
    if not dx and not dy:
        return pred
    b = pred.box
    return replace(pred, box=(b[0] + dx, b[1] + dy, b[2] + dx, b[3] + dy),
                   anchor_px=(pred.anchor_px[0] + dx, pred.anchor_px[1] + dy),
                   mask=None, mask_origin=None)  # fmt: skip


def facing_for(st: ActorState, ent_heading: int | None,
               rule: tuple[int, str] | None) -> tuple[int, str]:  # fmt: skip
    """1a: a walking unit keeps the Timeline's facing (its step); else the walk rule when it set
    one; else the Timeline's facing (the appear heading as the last resort)."""
    timeline = (int(st.facing) % 8 if st.facing is not None else int(ent_heading or 0) % 8,
                f"timeline:{st.facing_from}")  # fmt: skip
    if st.state == "walk" or rule is None:
        return timeline
    return int(rule[0]) % 8, rule[1]


# --- fix 2 (3f): the drawn view, and the exclusions 2b / 2c ------------------------------------

RULES = ("1a", "fix2")  # 1a: 3b's frozen walk rule (3c); fix2: 3f, orc_facing_study.fix2_heading
NEXT_MOVE_NS = 150_000_000  # 2b: the 150 ms (timeline time) before a unit's next move packet
NEXT_MOVE, AMBIGUOUS = "next_move", "ambiguous_view"  # 2b / 2c's exclusion reasons (as unfit)
SELF_MOTION_NS = 200_000_000  # the check's report: our camera moved in the 200 ms before a label


def _fs() -> Any:
    """orc_facing_study, which imports this module: imported lazily (no cycle at load time)."""
    import orc_facing_study

    return orc_facing_study


def labels_name(rule: str, occlusion: str = "1c", stack: bool = False,
                wing: bool = False) -> str:  # fmt: skip
    """The labels' name: 3b / 3f's unchanged without 3i's options (old invocations keep it)."""
    base = {"1a": "v2orc-fix", "fix2": "v2orc-fix2"}[rule]
    extra = ([] if occlusion == "1c" else [occlusion]) + (["S3"] if stack else [])
    return base + ("+W" if wing else "") + "".join(f"+{x}" for x in extra)


# --- 3i (PRE-REGISTERED 2026-10-23 22:46:39 ICT, 0f039b9): W, the occlusion candidates, S3 ------

OCCLUSIONS = ("1c", "o3h", "o3")  # 1c: 3b's literal rule; o3h / o3: the fit's evidence (3e O3)
O3H_TAU = 0.48  # o3h: an under-box label's fit NCC (col3's clear-label p5, 0.4775)
STACK_IOU = 0.30  # S3: fitted boxes (before W) of two kept monster labels in one frame
WING_MOBS = (1005, 1111)  # W: the Familiar and the Drainliar only
WING_DELTA = 0.05  # W: a frame is plausible when its own fit >= the best - 0.05 ...
WING_PAD_PX = 2  # ... and the union is grown by 2 px (col3: the drawn pixels' p90 reach)
OCCLUDED, STACKED = "occluded_model", "stacked"
# 3i's six candidates, in its tie-break order
CANDIDATES = ("o3", "o3+S3", "o3h", "o3h+S3", "1c", "1c+S3")


def parse_candidate(name: str) -> tuple[str, bool]:
    """``o3h+S3`` -> ("o3h", True)."""
    occlusion, _, s3 = name.partition("+")
    if occlusion not in OCCLUSIONS or s3 not in ("", "S3"):
        raise SystemExit(f"unknown candidate {name!r} (one of {CANDIDATES})")
    return occlusion, s3 == "S3"


def candidate_name(occlusion: str, stack: bool) -> str:
    return occlusion + ("+S3" if stack else "")


def iou(a: Box, b: Box) -> float:
    ix = min(a[2], b[2]) - max(a[0], b[0])
    iy = min(a[3], b[3]) - max(a[1], b[1])
    if ix <= 0 or iy <= 0:
        return 0.0
    inter = ix * iy
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union > 0 else 0.0


def stacked_gids(boxes: Sequence[tuple[int, Box]], thr: float = STACK_IOU) -> set[int]:
    """S3: the gids whose box has IoU >= ``thr`` with another's (both of a pair)."""
    out: set[int] = set()
    for i, (g1, b1) in enumerate(boxes):
        for g2, b2 in boxes[i + 1 :]:
            if iou(b1, b2) >= thr:
                out.update((g1, g2))
    return out


@dataclass(frozen=True)
class LabelFate:
    """One visible monster's evidence in a frame, for every candidate at once (3i): its model-box
    overlap, fix 2's 2b / 2c reason, its fit and the failure reason a clear label would get."""

    gid: int
    mob: int
    under: bool  # its predicted box overlaps a model's projected box (1c's test)
    pre: str | None  # 2b / 2c (excluded under every candidate)
    fit: tuple[float, int, int, int] | None  # (ncc, dx, dy, motion) of the best frame; None: unfit
    fail: str | None  # None: the fit passes (>= tau, not at the edge, a box); else crowd/ui/unfit
    box: Box | None = None  # the fitted frame's box, clipped (S3 compares these)
    raw: Box | None = None  # unclipped
    wbox: Box | None = None  # W (clipped), for the WING_MOBS
    heading: int = 0
    facing_from: str = ""
    state: str = ""


def decide(fates: Sequence[LabelFate], occlusion: str, stack: bool,
           o3h_tau: float = O3H_TAU,
           ) -> tuple[list[LabelFate], list[tuple[int, int, str]]]:  # fmt: skip
    """PURE: (kept, excluded (gid, mob, reason)) under one candidate (3i). The order: 1c's model
    test, then 2b / 2c, then the fit (an under-box failure is ``occluded_model``), then o3h's
    0.48 (``o3h_tau``: another map's own frozen value, payf07-detector.md 4e), then S3 among the
    kept."""
    if occlusion not in OCCLUSIONS:
        raise SystemExit(f"--occlusion {occlusion!r}: one of {OCCLUSIONS}")
    kept: list[LabelFate] = []
    out: list[tuple[int, int, str]] = []
    for f in fates:
        if f.under and occlusion == "1c":
            out.append((f.gid, f.mob, OCCLUDED))
        elif f.pre is not None:
            out.append((f.gid, f.mob, f.pre))
        elif f.fit is None or f.fail is not None:
            out.append((f.gid, f.mob, OCCLUDED if f.under else (f.fail or "unfit")))
        elif f.under and occlusion == "o3h" and f.fit[0] < o3h_tau:
            out.append((f.gid, f.mob, OCCLUDED))
        else:
            kept.append(f)
    if stack:
        bad = stacked_gids([(f.gid, f.box) for f in kept if f.box is not None])
        out += [(f.gid, f.mob, STACKED) for f in kept if f.gid in bad]
        kept = [f for f in kept if f.gid not in bad]
    return kept, out


def move_vector(world: World, gid: int, t_ns: int) -> tuple[int, int] | None:
    """(x1 - x0, y1 - y0) of the move a unit WALKS, or of the move whose end set 3b's walk rule:
    timeline.walk_rule_facing's own choice (its walk once started, else the walk a stop cut
    short). None when it has none."""
    ent = world.entities.get(gid)
    if ent is None:
        return None
    tick = tick_of(t_ns)
    walk = None
    if ent.walk is not None and ticks_since(tick, ent.walk.start_tick) >= 0:
        walk = ent.walk
    elif ent.motion.cut is not None and ticks_since(tick, ent.motion.cut[1]) >= 0:
        walk = ent.motion.cut[0]
    return None if walk is None else (int(walk.x1 - walk.x0), int(walk.y1 - walk.y0))


def fix2_facing(st: ActorState, ent_heading: int | None, rule: tuple[int, str] | None,
                vector: tuple[int, int] | None) -> tuple[int, str]:  # fmt: skip
    """3f's fix 2, as (heading, source):
    - (ii) a WALKING unit: the quadrant diagonal of its move's vector;
    - (iii) a unit not walking whose ended move set 3b's walk rule: that vector's map_calc_dir
      heading, an axis heading taken to its diagonal (north -> NW, east -> NE, south -> SW,
      west -> NW);
    - (i) and every other unit: the Timeline's facing (the appear heading as the last resort),
      as 1a's fallback.
    The heading is orc_facing_study.fix2_heading (72cb479, confirmed on col3 in 3e), reused."""
    walking = st.state == "walk"
    if vector is not None and (walking or rule is not None):
        row = {"source": "move", "state": "walk" if walking else "stand",
               "move": {"d": [int(vector[0]), int(vector[1])]}}  # fmt: skip
        h = _fs().fix2_heading(row)
        if h is not None:
            return int(h) % 8, "fix2:walk" if walking else "fix2:after_move"
    return facing_for(st, ent_heading, None)


class NextMoves:
    """2b: per unit, the receive times of its MOVE packets (``entity_appear`` of kind ``move``,
    0x09FD: the only appear that carries a destination, which is how the World starts a walk),
    sorted."""

    def __init__(self, events: Sequence[dict[str, Any]]) -> None:
        by: dict[int, list[int]] = defaultdict(list)
        for e in events:
            if e.get("type") == "entity_appear" and (e.get("kind") == "move"
                                                     or e.get("x1") is not None):  # fmt: skip
                by[int(e["gid"])].append(int(e["t_mono_ns"]))
        self.times = {g: sorted(ts) for g, ts in by.items()}

    def soon(self, gid: int, tw: int, ns: int = NEXT_MOVE_NS) -> bool:
        """A move packet of ``gid`` arrives AFTER timeline time ``tw``, less than ``ns`` later."""
        ts = self.times.get(gid, [])
        i = bisect.bisect_right(ts, tw)
        return i < len(ts) and ts[i] - tw < ns


def ambiguous_view(vector: tuple[int, int], heading: int, classes: Sequence[Sequence[int]],
                   yaw: float) -> bool:  # fmt: skip
    """2c: a MIXED move (dx, dy non-zero, |dx| != |dy|) whose vector's quadrant diagonal draws
    another IMAGE than ``heading`` (the (iii) heading) in the action's view ``classes``."""
    fs = _fs()
    dx, dy = vector
    if fs.shape_of(dx, dy) != "mixed":
        return False
    q = fs.quadrant(dx, dy)
    return bool(fs.class_index(classes, displayed_direction(q, yaw))
                != fs.class_index(classes, displayed_direction(heading, yaw)))  # fmt: skip


class ViewClasses:
    """(job, action group) -> orc_facing_study.view_classes of the species' ACT (cached)."""

    def __init__(self) -> None:
        self.cache: dict[tuple[int, int], list[tuple[int, ...]]] = {}

    def __call__(self, sheet: SpriteSheet, job: int, group: int) -> list[tuple[int, ...]]:
        key = (int(job), int(group))
        if key not in self.cache:
            self.cache[key] = _fs().view_classes(sheet, group)
        return self.cache[key]


@dataclass
class FacingRule:
    """The facing a label is drawn with under ``rule``: 1a (3b's) or fix2 (3f's, with 2b / 2c)."""

    rule: str
    moves: NextMoves
    classes: ViewClasses

    @classmethod
    def for_events(cls, rule: str, events: Sequence[dict[str, Any]]) -> FacingRule:
        if rule not in RULES:
            raise SystemExit(f"unknown facing rule {rule!r} (one of {RULES})")
        return cls(rule, NextMoves(events if rule == "fix2" else ()), ViewClasses())

    def choose(self, world: World, e: EntityState, st: ActorState,
               rules: dict[int, tuple[int, str]], tw: int, sheet: SpriteSheet,
               yaw: float) -> tuple[tuple[int, str], str | None]:  # fmt: skip
        """((heading, source), the exclusion reason or None) of entity ``e`` at timeline ``tw``."""
        if self.rule == "1a":
            return facing_for(st, e.heading, rules.get(e.gid)), None
        vec = move_vector(world, e.gid, tw)
        facing = fix2_facing(st, e.heading, rules.get(e.gid), vec)
        if self.moves.soon(e.gid, tw):
            return facing, NEXT_MOVE
        if facing[1] == "fix2:after_move" and vec is not None:
            group = int(STATE_ACTION.get(st.state, MonsterAction.IDLE))
            if ambiguous_view(vec, facing[0], self.classes(sheet, e.job, group), yaw):
                return facing, AMBIGUOUS
        return facing, None


def shift_ncc_valid(observed: npt.NDArray[np.float64], valid: npt.NDArray[np.bool_],
                    template: npt.NDArray[np.float64], mask: npt.NDArray[np.bool_],
                    r: int) -> npt.NDArray[np.float64]:  # fmt: skip
    """label_check.ncc's masked NCC at every offset within ``r`` (grid[r + dy, r + dx]), over the
    mask pixels that land on VALID observed pixels only (inside the frame, outside the UI). With
    every pixel valid it equals orc_camera_check.shift_ncc. NaN where undefined (fewer than
    label_check.MIN_PIXELS pixels, or no variance)."""
    h, w = template.shape
    if observed.shape != (h + 2 * r, w + 2 * r) or valid.shape != observed.shape:
        raise ValueError(f"observed {observed.shape} / valid {valid.shape} is not template "
                         f"{template.shape} + 2 x {r}")  # fmt: skip
    out = np.full((2 * r + 1, 2 * r + 1), np.nan)
    m = mask.astype(np.float64)
    if float(m.sum()) < label_check.MIN_PIXELS:
        return out
    v = valid.astype(np.float64)
    o = np.where(valid, observed, 0.0)
    shape = observed.shape
    f_v, f_o, f_oo = np.fft.rfft2(v), np.fft.rfft2(o), np.fft.rfft2(o * o)

    def corr(kernel: npt.NDArray[np.float64], f: Any) -> Any:
        k = np.fft.rfft2(kernel, s=shape)
        return np.fft.irfft2(f * np.conj(k), s=shape)[: 2 * r + 1, : 2 * r + 1]

    tm = template * m
    n = corr(m, f_v)
    st, stt = corr(tm, f_v), corr(tm * template, f_v)
    so, soo, sto = corr(m, f_o), corr(m, f_oo), corr(tm, f_o)
    n = np.round(n)
    ok = n >= label_check.MIN_PIXELS
    with np.errstate(divide="ignore", invalid="ignore"):
        cov = sto - st * so / n
        vt = stt - st * st / n
        vo = soo - so * so / n
        good = ok & (vt > 1e-9 * np.maximum(stt, 1.0)) & (vo > 1e-9 * np.maximum(soo, 1.0))
        out[good] = cov[good] / np.sqrt(vt[good] * vo[good])
    return out


def at_edge(dx: int, dy: int, r: int) -> bool:
    return abs(dx) >= r or abs(dy) >= r


def pick_offset(curve: dict[int, float | None]) -> int | None:
    """The offset with the smallest median error (a tie: the smaller offset)."""
    vals = [(v, ms) for ms, v in curve.items() if v is not None]
    return min(vals)[1] if vals else None


def fine_grid(best: int, span: int = FINE_SPAN_MS, step: int = FINE_STEP_MS,
              lo: int = COARSE_MS[0], hi: int = COARSE_MS[-1]) -> list[int]:  # fmt: skip
    return [ms for ms in range(best - span, best + span + 1, step) if lo <= ms <= hi]


def median_xy(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        return {"n": 0}
    dx = [r["dx"] for r in rows]
    dy = [r["dy"] for r in rows]
    return {"n": len(rows), "dx": statistics.median(dx), "dy": statistics.median(dy),
            "mad_dx": statistics.median(abs(x - statistics.median(dx)) for x in dx),
            "mad_dy": statistics.median(abs(y - statistics.median(dy)) for y in dy),
            "best_ncc_median": round(statistics.median(r["best"] for r in rows), 3)}  # fmt: skip


def agreement(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """REPORTED, not deciding: the 1a heading vs the best of the 8 drawn views, per species."""
    by: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        if r.get("best_heading") is None:
            continue
        by[str(r["mob"])].append(r)
        by["pooled"].append(r)
    note = ("REPORTED, not deciding: the rule's heading vs the best of the 8 drawn views (biased "
            "upward: a max over 8); agree = the same HEADING (a tie keeps the first: 3e's finding "
            "0), image_agree = the same IMAGE (the view class)")  # fmt: skip
    out: dict[str, Any] = {"note": note}
    for key, rs in sorted(by.items()):
        n = len(rs)
        same = sum(1 for r in rs if r["best_heading"] == r["heading"])
        rule = [r for r in rs if r["facing_from"] in ("walk_rule", "fix2:walk", "fix2:after_move")]
        img = [r for r in rs if r.get("same_image_as_best") is not None]
        img_same = sum(1 for r in img if r["same_image_as_best"])
        out[key] = {
            "n": n, "agree": same, "agree_share": round(same / n, 4) if n else None,
            "image_n": len(img), "image_agree": img_same,
            "image_agree_share": round(img_same / len(img), 4) if img else None,
            "delta": dict(sorted(Counter(str((r["best_heading"] - r["heading"]) % 8)
                                         for r in rs).items())),
            "facing_from": dict(Counter(r["facing_from"] for r in rs)),
            "walk_rule_n": len(rule),
            "walk_rule_agree": sum(1 for r in rule if r["best_heading"] == r["heading"]),
            "low_share_rule": round(sum(1 for r in rs if r["c1"] < TAU) / n, 4) if n else None,
            "low_share_best_of_8": round(sum(1 for r in rs if r["c1_best_of_8"] < TAU) / n, 4)
            if n else None,
        }  # fmt: skip
    return out


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git_head() -> str | None:
    try:
        out = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "--short", "HEAD"],
                             capture_output=True, text=True, check=True)  # fmt: skip
    except (OSError, subprocess.CalledProcessError):
        return None
    return out.stdout.strip() or None


def now_ict() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(time.time() + 7 * 3600)) + " ICT"


# --- the map's models (1c) -------------------------------------------------------------------


class Occluders:
    """Every RSW model of the map, placed (poring_dataset.rsw) once; its screen box per camera
    position (cached: the GM stands still through a dwell)."""

    def __init__(self, rsw_path: Path = RSW_PATH, model_dir: Path = MODEL_DIR,
                 map_cells: tuple[int, int] = MAP_CELLS) -> None:  # fmt: skip
        self.rsw_path, self.model_dir = rsw_path, model_dir
        rsw = rswmod.parse_rsw(rsw_path.read_bytes())
        self.rsw = rsw
        meshes: dict[str, rswmod.Rsm] = {}
        self.files: dict[str, str] = {}
        self.models: list[tuple[int, str, npt.NDArray[np.float64], npt.NDArray[np.float64]]] = []
        for m in rsw.models:
            if m.model_file not in meshes:
                path = model_dir / m.model_file.replace("\\", "/")
                if not path.exists():
                    raise SystemExit(f"{path}: the RSW's model is not extracted (grf_read.py)")
                meshes[m.model_file] = rswmod.parse_rsm(path.read_bytes())
                self.files[m.model_file] = sha256_file(path)
            cells, alt = rswmod.to_cells(rswmod.world_points(meshes[m.model_file], m, map_cells))
            self.models.append((m.index, m.model_file, cells, alt))
        self._cache: dict[tuple[float, float], list[tuple[int, Box]]] = {}

    def boxes(self, scene: Scene, size: tuple[int, int] = (1280, 720)) -> list[tuple[int, Box]]:
        key = (float(scene.player[0]), float(scene.player[1]))
        if key not in self._cache:
            out = []
            for index, _f, cells, alt in self.models:
                b = rswmod.screen_box(scene, cells, alt)
                if b is not None and b[2] > 0 and b[0] < size[0] and b[3] > 0 and b[1] < size[1]:
                    out.append((index, b))
            if len(self._cache) > 4096:
                self._cache.clear()
            self._cache[key] = out
        return self._cache[key]

    def hit(self, scene: Scene, box: Box) -> int | None:
        """The first model whose screen box overlaps ``box`` (its RSW index), else None."""
        for index, b in self.boxes(scene):
            if rswmod.overlaps(box, b):
                return index
        return None

    def provenance(self) -> dict[str, Any]:
        return {"rsw": str(self.rsw_path), "rsw_sha256": sha256_file(self.rsw_path),
                "rsw_version": list(self.rsw.version), "objects": self.rsw.objects,
                "models": len(self.models), "model_dir": str(self.model_dir),
                "model_files_sha256": dict(sorted(self.files.items()))}  # fmt: skip


# --- the session -----------------------------------------------------------------------------


def _cached_gat(g: Any) -> Any:
    """The same GAT with its altitude grid computed once (Gat.altitude rebuilds the whole grid per
    call, and every projected anchor asks for it; species_check.py's pattern)."""
    import dataclasses
    import functools

    from poring_dataset.gat import Gat

    class _Cached(Gat):
        @functools.cached_property
        def altitude(self) -> Any:  # type: ignore[override]
            return Gat.altitude.fget(self)  # type: ignore[attr-defined]

    return _Cached(**{f.name: getattr(g, f.name) for f in dataclasses.fields(g)})


def _speed_up() -> None:
    """orc_camera_check's scenes take the cached GAT (same values, computed once)."""
    if getattr(occ._gat, "orc_fix_cached", False):
        return
    plain = occ._gat

    @functools.lru_cache(maxsize=8)
    def cached(path: str) -> Any:
        g = plain(path)
        return None if g is None else _cached_gat(g)

    cached.orc_fix_cached = True  # type: ignore[attr-defined]
    occ._gat = cached


@dataclass
class Session:
    """One warp_watch block's packets, frames and dwells (orc_camera_check's reading), or a HUMAN
    DEMO's (3f: its frame files; one span over the whole recording, no dwells; its frames usable
    only where ``layout_ok`` reads the hunting layout from pixels)."""

    path: Path
    lab: qa_export.Labeler
    refs: list[qa_export.JpegRef]
    dwells: list[tuple[int, int]]
    sid: str
    layout: Any = None  # None (a recorded layout) or BGR -> bool (qa_export.layout_check)

    @classmethod
    def open(cls, path: Path, kb: Path, layout_templates: Path | None = None) -> Session:
        refuse_test_block(path)
        qa_export.KB_CLASSES = kb / "classes.json"
        qa_export.KB_SPRITE_NAMES = kb / "monster_sprite_names.json"
        manifest = json.loads((path / "manifest.json").read_text())
        demo = qa_export.is_human_demo(manifest)
        if not (qa_export.is_warp_watch(manifest) or demo):
            raise SystemExit(f"{path}: neither a warp_watch session nor a human demo")
        lab = qa_export.Labeler(path, str(OLD_OFFSET_MS), labels="v1", k=K)
        tl = lab.timeline  # the same events, snapshots 8x denser (the replays dominate the sweeps)
        lab.timeline = Timeline(tl.events, tl.maps, snapshot_every=32, die_ms=tl.die_ms,
                                default_die_ms=tl.default_die_ms)  # fmt: skip
        occ.cache_compose()
        _speed_up()
        refs = qa_export.frame_refs(path, manifest)
        if demo:
            dwells = [(refs[0].t_mono_ns, refs[-1].t_mono_ns)] if refs else []
        else:
            timeline = path / "events.jsonl"
            dwells = occ.dwell_spans(json.loads(x) for x in timeline.read_text().splitlines() if x)
        return cls(path, lab, refs, dwells, qa_export.session_id(manifest),
                   qa_export.layout_check(manifest, layout_templates))  # fmt: skip

    def layout_ok(self, bgr: npt.NDArray[np.uint8]) -> bool:
        return True if self.layout is None else bool(self.layout(bgr))

    def candidates(self, every: int) -> Iterator[qa_export.JpegRef]:
        """Every ``every``-th recorded frame inside a dwell, outside the GM-command windows."""
        for ref in self.refs[::every]:
            if in_windows(ref.t_mono_ns, self.dwells) and not in_windows(
                ref.t_mono_ns, self.lab.windows
            ):
                yield ref

    def scene(self, world: FrameWorld) -> Scene | None:
        if world.self_pos is None or not world.map or map_key(world.map) != MAP:
            return None
        return occ.scene_for(self.lab, world.map, world.self_pos)

    def facing_rule(self, rule: str) -> FacingRule:
        return FacingRule.for_events(rule, self.lab.timeline.events)


def actor_for(e: EntityState, st: ActorState, heading: int) -> Actor:
    action = STATE_ACTION.get(st.state, MonsterAction.IDLE)
    elapsed = st.elapsed_ms if action in ONE_SHOT else None
    return Actor((float(e.x), float(e.y)), heading, int(action), elapsed_ms=elapsed,
                 duration_ms=st.duration_ms)  # fmt: skip


def predict(e: EntityState, st: ActorState, sheet: SpriteSheet, scene: Scene, heading: int,
            anchors: dict[int, tuple[float, float]]) -> SpritePrediction | None:  # fmt: skip
    """The fix's prediction: the action the state shows, facing ``heading``, + the 1b anchor."""
    pred = predict_sprite(actor_for(e, st, heading), sheet, scene, K)
    if pred is None:
        return None
    dx, dy = anchors.get(int(e.job), (0.0, 0.0))
    return shifted(pred, dx, dy)


def unit_anchors(world: FrameWorld, scene: Scene) -> dict[int, tuple[float, float]]:
    """gid -> the projected anchor of every drawn unit (players, monsters, NPCs, not hidden) and
    our own GM (key -1): orc_camera_check.unit_anchor_others' set, projected in ONE call
    (render.anchor_and_depth's numbers)."""
    ents = [e for e in world.entities if e.objtype in occ.UNIT_OBJTYPES and not e.hidden]
    px, py = scene.player
    cells = np.array([[e.x, e.y] for e in ents] + [[px, py]], dtype=float)
    off = cells - np.array([px, py])
    alt = np.zeros(len(cells))
    if scene.gat is not None:
        origin = (int(math.floor(px)), int(math.floor(py)))
        rel = scene.gat.relative_altitude(origin, cells - np.array(origin, dtype=float))
        alt = rel - rel[-1]
    uv = scene.camera.project(off, alt)
    out = {e.gid: (float(uv[i, 0]), float(uv[i, 1])) for i, e in enumerate(ents)}
    out[-1] = (float(uv[-1, 0]), float(uv[-1, 1]))
    return out


def isolated_from(anchor: tuple[float, float], gid: int,
                  anchors: dict[int, tuple[float, float]]) -> bool:  # fmt: skip
    return occ.isolated(anchor, [a for g, a in anchors.items() if g != gid])


Cand = tuple[EntityState, ActorState, SpriteSheet, SpritePrediction, tuple[int, str]]


def standing_candidates(sess: Session, tw: int, anchors: dict[int, tuple[float, float]],
                        occluders: Occluders | None, dropped: Counter[str],
                        facing_rule: FacingRule | None = None,
                        under_out: list[Cand] | None = None,
                        ) -> tuple[FrameWorld, Scene | None, dict[int, ActorState],
                                   list[Cand]]:  # fmt: skip
    """Section 3's STANDING labels at ``tw`` (idle >= 1 s, isolated 120 px, clear of the UI and the
    edges by the C2 margin), facing 1a (or ``facing_rule``'s: fix 2), anchor 1b; 1c's model
    overlap excluded, then fix 2's 2b / 2c (3f). With ``under_out`` (3i's o3 / o3h) a label under
    a model box that 2b / 2c keep is put there instead of being dropped: its fit decides."""
    lab = sess.lab
    replay, world, states, rules = lab.timeline.at_world(tw)
    choice = facing_rule if facing_rule is not None else FacingRule.for_events("1a", ())
    scene = sess.scene(world)
    now = {s.gid: s for s in states}
    if scene is None:
        return world, None, now, []
    prev = {s.gid: s for s in lab.timeline.states(tw - occ.STANDING_NS)}
    units = unit_anchors(world, scene)
    out = []
    for e in world.entities:
        if e.objtype != 5 or e.hidden:
            continue
        st = now.get(e.gid)
        if not occ.standing(st, prev.get(e.gid)):
            dropped["not_standing"] += 1
            continue
        assert st is not None
        sheet = lab.sheets(e.job)
        if sheet is None:
            dropped[f"no_sheet:{e.job}"] += 1
            continue
        facing, why = choice.choose(replay, e, st, rules, tw, sheet, scene.camera.yaw)
        pred = predict(e, st, sheet, scene, facing[0], anchors)
        if pred is None:
            dropped["draws_nothing"] += 1
            continue
        if not isolated_from(pred.anchor_px, e.gid, units):
            dropped["crowded"] += 1
            continue
        if not occ.clear_box(pred.box, lab.ui_rects, lab.size):
            dropped["ui_or_edge"] += 1
            continue
        under = occluders is not None and occluders.hit(scene, pred.box) is not None
        if under and under_out is None:
            dropped["occluded_model"] += 1
            dropped[f"occluded_model:{e.job}"] += 1
            continue
        if why is not None:  # fix 2's 2b / 2c (3f): excluded, as unfit
            dropped[why] += 1
            dropped[f"{why}:{e.job}"] += 1
            continue
        if under and under_out is not None:
            under_out.append((e, st, sheet, pred, facing))
            continue
        out.append((e, st, sheet, pred, facing))
    return world, scene, now, out


# --- forked workers ---------------------------------------------------------------------------

_JOB: dict[str, Any] = {}  # the open session, occluders and parameters, inherited by fork


def _read(ref: qa_export.JpegRef) -> npt.NDArray[np.uint8]:
    """A frame as BGR: warp_watch's JPEG shards here; another map's recorder session sets its own
    reader in _JOB (map_labels.py, payf07-detector.md)."""
    return _JOB.get("reader", qa_export.read_jpeg)(ref)  # type: ignore[no-any-return]


def run_parallel(func: Any, items: Sequence[Any], workers: int) -> list[Any]:
    """``func`` over ``items`` in ``workers`` forked processes (the job state in _JOB is inherited,
    never pickled); in order."""
    if workers <= 1 or len(items) < 2:
        return [func(x) for x in items]
    import multiprocessing as mp

    with mp.get_context("fork").Pool(workers) as pool:
        return list(pool.map(func, items, chunksize=max(1, len(items) // (workers * 16))))


# --- 1d: the packet -> frame offset (col3) ----------------------------------------------------


def walkers_at(sess: Session, t: int, ms: int, occluders: Occluders,
               ) -> dict[int, tuple[EntityState, SpritePrediction | None, int | None]]:  # fmt: skip
    """{gid: (entity, prediction or None when it fails a rule, its walk's start or None when it is
    not walking)} for the ground walkers at ``t`` - ``ms``."""
    lab = sess.lab
    tw = t - int(ms * 1_000_000)
    world, states, _rules = lab.timeline.at(tw)
    scene = sess.scene(world)
    if scene is None:
        return {}
    now = {s.gid: s for s in states}
    units = unit_anchors(world, scene)
    out: dict[int, tuple[EntityState, SpritePrediction | None, int | None]] = {}
    for e in world.entities:
        if e.objtype != 5 or e.hidden or e.job not in _JOB.get("walkers", WALKERS):
            continue
        st = now.get(e.gid)
        sheet = lab.sheets(e.job)
        if st is None or st.state != "walk" or st.since_ns is None or sheet is None:
            out[e.gid] = (e, None, None)
            continue
        heading = int(st.facing if st.facing is not None else (e.heading or 0)) % 8
        pred = predict(e, st, sheet, scene, heading, {})
        ok = (pred is not None and isolated_from(pred.anchor_px, e.gid, units)
              and occ.clear_box(pred.box, lab.ui_rects, lab.size)
              and occluders.hit(scene, pred.box) is None)  # fmt: skip
        out[e.gid] = (e, pred if ok else None, st.since_ns)
    return out


def walker_samples(sess: Session, t: int, offsets: Sequence[int], occluders: Occluders,
                   ) -> dict[int, dict[int, tuple[EntityState, SpritePrediction]]]:  # fmt: skip
    """{gid: {offset_ms: (entity, prediction)}} for the GROUND walkers that walk the SAME move at
    every offset (so the sample set does not change with the offset), isolated, clear of the UI /
    edges and of the map's models at every one of them."""
    per: dict[int, dict[int, tuple[EntityState, SpritePrediction]]] = defaultdict(dict)
    bad: set[int] = set()
    walk_of: dict[int, set[int | None]] = defaultdict(set)
    for ms in offsets:
        found = walkers_at(sess, t, ms, occluders)
        if not found:
            return {}
        for gid in set(per) - set(found):
            bad.add(gid)
        for gid, (e, pred, walk) in found.items():
            walk_of[gid].add(walk)
            if pred is None or walk is None:
                bad.add(gid)
            else:
                per[gid][ms] = (e, pred)
    return {g: v for g, v in per.items()
            if g not in bad and len(v) == len(offsets) and len(walk_of[g]) == 1}  # fmt: skip


def _offset_coarse(ref: qa_export.JpegRef) -> list[tuple[int, int, dict[int, float]]]:
    """[(frame_id, gid, {offset: error px})] of one frame's samples at the coarse offsets."""
    sess, occluders = _JOB["sess"], _JOB["occluders"]
    found = walker_samples(sess, ref.t_mono_ns, list(COARSE_MS), occluders)
    if not found:
        return []
    bgr = _read(ref)
    out = []
    for gid, by in found.items():
        errs = {}
        for ms, (e, pred) in by.items():
            sheet = sess.lab.sheets(e.job)
            bo = occ.best_offset(bgr, sheet, pred, SEARCH_PX)
            if bo is not None:
                errs[ms] = math.hypot(bo[1], bo[2])
        out.append((ref.frame_id, gid, errs))
    return out


def _offset_fine(job: tuple[qa_export.JpegRef, list[int]]) -> list[tuple[int, dict[int, float]]]:
    """[(gid, {fine offset: error px})] for the given samples of one frame."""
    ref, gids = job
    sess, occluders = _JOB["sess"], _JOB["occluders"]
    bgr = _read(ref)
    out: dict[int, dict[int, float]] = defaultdict(dict)
    for ms in _JOB["fine"]:
        found = walkers_at(sess, ref.t_mono_ns, ms, occluders)
        for gid in gids:
            got = found.get(gid)
            if got is None or got[1] is None:
                continue
            sheet = sess.lab.sheets(got[0].job)
            bo = occ.best_offset(bgr, sheet, got[1], SEARCH_PX)
            if bo is not None:
                out[gid][ms] = math.hypot(bo[1], bo[2])
    return list(out.items())


def cmd_offset(a: argparse.Namespace) -> dict[str, Any]:
    sess = Session.open(a.session, a.kb)
    occluders = Occluders(a.rsw, a.models)
    _JOB.update(sess=sess, occluders=occluders)
    refs = list(sess.candidates(a.every))
    coarse = [row for rows in run_parallel(_offset_coarse, refs, a.workers) for row in rows]
    print(f"1d: {len(coarse)} walker samples from {len(refs)} frames", file=sys.stderr)
    errs: dict[int, list[float]] = defaultdict(list)
    for _fid, _gid, by in coarse:
        for ms, v in by.items():
            errs[ms].append(v)
    curve = {ms: round(statistics.median(errs[ms]), 3) if errs[ms] else None for ms in COARSE_MS}
    best_coarse = pick_offset(curve)
    if best_coarse is None:
        raise SystemExit("1d: no walker sample scored")
    fine = [ms for ms in fine_grid(best_coarse) if ms not in COARSE_MS]
    _JOB["fine"] = fine
    by_ref: dict[int, list[int]] = defaultdict(list)
    for fid, gid, _by in coarse:
        by_ref[fid].append(gid)
    ref_of = {r.frame_id: r for r in refs}
    jobs = [(ref_of[fid], gids) for fid, gids in sorted(by_ref.items())]
    for rows in run_parallel(_offset_fine, jobs, a.workers):
        for _gid, by in rows:
            for ms, v in by.items():
                errs[ms].append(v)
    full = {ms: round(statistics.median(errs[ms]), 3) if errs[ms] else None
            for ms in sorted(set(COARSE_MS) | set(fine))}  # fmt: skip
    best = pick_offset({ms: full[ms] for ms in fine_grid(best_coarse)})
    species: Counter[str] = Counter()
    for fid, gid, _by in coarse:
        ent = next((e for e in sess.lab.timeline.frame_world(ref_of[fid].t_mono_ns).entities
                    if e.gid == gid), None)  # fmt: skip
        species[str(ent.job if ent is not None else "?")] += 1
    return {
        "what": "1d: the packet -> frame offset on this grab path (RDP, frame bus, 5 Hz shards)",
        "session": sess.sid, "measured_at": now_ict(), "commit": git_head(),
        "rule": "moving ground walkers (1153, 1152) walking ONE move through the whole sweep, "
                "isolated 120 px, clear of the UI / edges by 16 px and of the map's models at "
                "every offset; error = |best-NCC offset| within +-16 px of the rendered walk "
                "sprite (Timeline facing, phase unknown: best frame) at the packet position; "
                "the smallest MEDIAN error wins (coarse 50 ms 0..1000, then 10 ms +-50)",
        "every": a.every, "frames_read": len(refs), "samples": len(coarse),
        "frames_with_samples": len(by_ref), "units": len({g for _f, g, _b in coarse}),
        "samples_by_species": dict(sorted(species.items())),
        "curve_median_px": {str(k): v for k, v in full.items()},
        "curve_n": {str(k): len(errs[k]) for k in full},
        "curve_p25_p75_px": {str(k): [round(float(np.percentile(errs[k], 25)), 2),
                                      round(float(np.percentile(errs[k], 75)), 2)]
                             for k in full if errs[k]},
        "best_coarse_ms": best_coarse, "offset_ms": best,
        "old_offset_ms": OLD_OFFSET_MS,
        "old_offset_nearest_median_px": full.get(int(round(OLD_OFFSET_MS / 50.0) * 50)),
        "occluders": occluders.provenance(),
    }  # fmt: skip


# --- 1b: the flyers' anchor (col3) -----------------------------------------------------------


def _anchor_rows(ref: qa_export.JpegRef) -> tuple[list[dict[str, Any]], Counter[str]]:
    sess, occluders, off_ms = _JOB["sess"], _JOB["occluders"], _JOB["offset_ms"]
    dropped: Counter[str] = Counter()
    tw = ref.t_mono_ns - int(off_ms * 1e6)
    _world, scene, _now, cands = standing_candidates(sess, tw, {}, occluders, dropped)
    if scene is None:
        dropped["frame_no_scene"] += 1
    if not cands:
        return [], dropped
    dropped["frame_with_standing"] += 1
    bgr = _read(ref)
    rows = []
    for e, _st, sheet, pred, facing in cands:
        bo = occ.best_offset(bgr, sheet, pred, SEARCH_PX)
        if bo is None:
            dropped["unscored"] += 1
            continue
        rows.append({"frame_id": ref.frame_id, "gid": e.gid, "mob": e.job, "best": bo[0],
                     "dx": bo[1], "dy": bo[2], "facing_from": facing[1]})  # fmt: skip
    return rows, dropped


def cmd_anchor(a: argparse.Namespace) -> dict[str, Any]:
    sess = Session.open(a.session, a.kb)
    offset = json.loads(a.offset.read_text())
    if offset.get("session") != sess.sid:
        raise SystemExit(f"1b and 1d are measured on the same block: {offset.get('session')} vs "
                         f"{sess.sid}")  # fmt: skip
    off_ms = float(offset["offset_ms"])
    occluders = Occluders(a.rsw, a.models)
    _JOB.update(sess=sess, occluders=occluders, offset_ms=off_ms)
    refs = list(sess.candidates(a.every))
    rows: list[dict[str, Any]] = []
    dropped: Counter[str] = Counter()
    for r, d in run_parallel(_anchor_rows, refs, a.workers):
        rows += r
        dropped.update(d)
    by: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        by[int(r["mob"])].append(r)
    anchors = {}
    for mob in FLYERS:
        m = median_xy(by.get(mob, []))
        if m["n"] == 0:
            raise SystemExit(f"1b: no standing {mob} on {sess.sid}")
        anchors[str(mob)] = [float(m["dx"]), float(m["dy"])]
    return {
        "what": "1b: the flyers' drawn anchor (dx, dy) px, the median best-NCC offset of STANDING "
                "units (facing 1a, time 1d, C2's +-16 px search, 1c's model overlap excluded)",
        "session": sess.sid, "measured_at": now_ict(), "commit": git_head(),
        "offset_ms": off_ms, "every": a.every, "frames_read": len(refs),
        "dropped": dict(sorted(dropped.items())),
        "anchors_px": anchors,
        "per_species": {str(m): median_xy(rs) for m, rs in sorted(by.items())},
        "facing_from": {str(m): dict(Counter(r["facing_from"] for r in rs))
                        for m, rs in sorted(by.items())},
        "note": "ground species are listed for reference only: 1b applies to the flyers",
    }  # fmt: skip


# --- the frozen parameters -------------------------------------------------------------------


def cmd_freeze(a: argparse.Namespace) -> dict[str, Any]:
    off = json.loads(a.offset.read_text())
    anc = json.loads(a.anchor.read_text())
    if off["session"] != anc["session"] or float(anc["offset_ms"]) != float(off["offset_ms"]):
        raise SystemExit("1b must be measured on 1d's block at 1d's offset")
    occluders = Occluders(a.rsw, a.models)
    return {
        "labels": "v2orc-fix", "plan": "docs/planning/orcsdun01-detector.md 3b",
        "frozen_at": now_ict(), "commit": git_head(), "measured_on": off["session"],
        "offset_ms": float(off["offset_ms"]),
        "anchors_px": {k: [float(v[0]), float(v[1])] for k, v in anc["anchors_px"].items()},
        "fit_px": {str(k): v for k, v in sorted(FIT_PX.items())},
        "tau": TAU, "k": K, "search_px": SEARCH_PX,
        "facing_rule": "timeline.walk_rule_facing (1a)",
        "occluders": occluders.provenance(),
        "offset_file": str(a.offset), "offset_sha256": sha256_file(a.offset),
        "anchor_file": str(a.anchor), "anchor_sha256": sha256_file(a.anchor),
    }  # fmt: skip


def load_params(path: Path) -> dict[str, Any]:
    p = json.loads(path.read_text())
    if p.get("labels") != "v2orc-fix":
        raise SystemExit(f"{path}: not a v2orc-fix parameter file")
    return p


def anchors_of(params: dict[str, Any]) -> dict[int, tuple[float, float]]:
    return {int(k): (float(v[0]), float(v[1])) for k, v in params["anchors_px"].items()}


def occluders_of(params: dict[str, Any]) -> Occluders:
    occl = Occluders(Path(params["occluders"]["rsw"]), Path(params["occluders"]["model_dir"]))
    if occl.provenance()["rsw_sha256"] != params["occluders"]["rsw_sha256"] or \
            occl.files != params["occluders"]["model_files_sha256"]:  # fmt: skip
        raise SystemExit("the RSW / RSM files differ from the frozen ones")
    return occl


# --- the check on col1 (C1 / C2, judging the prediction) -------------------------------------


def _check_rows(ref: qa_export.JpegRef) -> tuple[list[dict[str, Any]], Counter[str],
                                                   Counter[int]]:  # fmt: skip
    sess, occluders = _JOB["sess"], _JOB["occluders"]
    off_ms, anchors = _JOB["offset_ms"], _JOB["anchors"]
    facing_rule: FacingRule = _JOB["facing_rule"]
    occlusion: str = _JOB.get("occlusion", "1c")
    dropped: Counter[str] = Counter()
    seen: Counter[int] = Counter()
    tw = ref.t_mono_ns - int(off_ms * 1e6)
    under: list[Cand] | None = None if occlusion == "1c" else []
    world, scene, now, cands = standing_candidates(sess, tw, anchors, occluders, dropped,
                                                   facing_rule, under)  # fmt: skip
    if scene is None:
        dropped["frame_no_scene"] += 1
        return [], dropped, seen
    for e in world.entities:
        if e.objtype == 5 and not e.hidden:
            seen[e.job] += 1
    if not cands and not under:
        return [], dropped, seen
    bgr = _read(ref)
    if not sess.layout_ok(bgr):  # a human demo's frame in another UI layout (3f)
        dropped["frame_ui_layout_mismatch"] += 1
        return [], dropped, seen
    if under:  # 3i's o3 / o3h: the fit's evidence decides an under-box label (C1 then scores
        grey = bgr[:, :, :3].astype(float) @ label_check.GREY  # the PREDICTION, as ever)
        valid = valid_map(sess.lab.size, sess.lab.ui_rects)
        tau = float(_JOB.get("tau", TAU))
        fit_px: dict[int, int] = _JOB.get("fit_px", FIT_PX)
        for cand in under:
            e, _st, sheet, pred, _facing = cand
            r = fit_px.get(int(e.job), 6)
            fit = fit_label(grey, valid, sheet, pred, r)
            ok = fit is not None and fit[0] >= tau and not at_edge(fit[1], fit[2], r)
            if ok and occlusion == "o3h":
                ok = fit is not None and fit[0] >= float(_JOB.get("o3h_tau", O3H_TAU))
            if not ok:
                dropped["occluded_model"] += 1
                dropped[f"occluded_model:{e.job}"] += 1
                continue
            dropped["under_model_kept"] += 1
            dropped[f"under_model_kept:{e.job}"] += 1
            cands.append(cand)
    if not cands:
        return [], dropped, seen
    dropped["frame_with_standing"] += 1
    before = sess.lab.timeline.frame_world(tw - SELF_MOTION_NS).self_pos
    self_moving = world.self_pos != before  # our own character (the camera) moved: REPORTED
    rows = []
    for e, st, sheet, pred, facing in cands:
        c1 = label_check.score(bgr, sheet, pred)
        if c1 is None:
            dropped["unscored"] += 1
            continue
        why = None
        if c1 < TAU:
            others = occ.other_boxes(world, scene, e.gid, sess.lab, now, K)
            why = label_check.classify(pred.box, others, sess.lab.ui_rects)
        row: dict[str, Any] = {"frame_id": ref.frame_id, "t_ns": ref.t_mono_ns, "gid": e.gid,
                               "mob": e.job, "cell": [e.x, e.y],
                               "box": [round(v, 1) for v in pred.box], "c1": round(c1, 4),
                               "why_low": why, "heading": facing[0],
                               "facing_from": facing[1], "self_moving": self_moving}  # fmt: skip
        bo = occ.best_offset(bgr, sheet, pred, SEARCH_PX)
        if bo is not None:
            row.update({"best": round(bo[0], 4), "dx": bo[1], "dy": bo[2], "motion": bo[3]})
        # REPORTED, not deciding: the best of the 8 drawn views (same anchor, same time)
        alt = {}
        for h in range(8):
            p = predict(e, st, sheet, scene, h, anchors)
            sc = None if p is None else label_check.score(bgr, sheet, p)
            if sc is not None:
                alt[h] = sc
        if alt:
            hb = max(alt, key=lambda h: alt[h])
            row.update({"best_heading": hb, "c1_best_of_8": round(alt[hb], 4)})
            # by IMAGE, not heading (3e finding 0: the ACT draws its directions in identical pairs)
            classes = facing_rule.classes(sheet, e.job, int(MonsterAction.IDLE))
            yaw = scene.camera.yaw
            fs = _fs()
            row["same_image_as_best"] = bool(
                fs.class_index(classes, displayed_direction(facing[0], yaw))
                == fs.class_index(classes, displayed_direction(hb, yaw)))  # fmt: skip
        rows.append(row)
    return rows, dropped, seen


def cmd_check(a: argparse.Namespace) -> dict[str, Any]:
    params = load_params(a.params)
    sess = Session.open(a.session, a.kb, a.layout_templates)
    if sess.sid == params["measured_on"]:
        raise SystemExit("the check runs on another block than the parameters' (col3)")
    off_ms = float(params["offset_ms"])
    anchors = anchors_of(params)
    occluders = occluders_of(params)
    facing_rule = sess.facing_rule(a.rule)
    occlusion = getattr(a, "occlusion", "1c")
    if occlusion not in OCCLUSIONS:
        raise SystemExit(f"--occlusion {occlusion!r}: one of {OCCLUSIONS}")
    _JOB.update(sess=sess, occluders=occluders, offset_ms=off_ms, anchors=anchors,
                facing_rule=facing_rule, occlusion=occlusion, tau=float(params["tau"]),
                fit_px={int(k): int(v) for k, v in params["fit_px"].items()})  # fmt: skip
    refs = list(sess.candidates(a.every))
    rows: list[dict[str, Any]] = []
    dropped: Counter[str] = Counter()
    seen: Counter[int] = Counter()
    for r, d, sn in run_parallel(_check_rows, refs, a.workers):
        rows += r
        dropped.update(d)
        seen.update(sn)
    rows.sort(key=lambda r: (r["frame_id"], r["gid"]))
    result = occ.summarize(rows, TAU)
    motion: dict[str, Any] = {"note": "REPORTED, not deciding: C1's bad_label share split by "
                              "whether our own character (the camera) moved in the 200 ms before "
                              "the label's timeline time"}  # fmt: skip
    for key, flag in (("self_moving", True), ("self_still", False)):
        sub = [r for r in rows if r.get("self_moving") is flag]
        bad = sum(1 for r in sub if r.get("why_low") == "bad_label")
        motion[key] = {"scored": len(sub), "bad_label": bad,
                       "bad_label_share": round(bad / len(sub), 4) if sub else None,
                       "c2_median_abs_dx": statistics.median(abs(r["dx"]) for r in sub if "dx" in r)
                       if any("dx" in r for r in sub) else None,
                       "c2_median_abs_dy": statistics.median(abs(r["dy"]) for r in sub if "dy" in r)
                       if any("dy" in r for r in sub) else None}  # fmt: skip
    by: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        by[int(r["mob"])].append(r)
    keys = ("frame_id", "gid", "c1", "best", "dx", "dy", "box", "heading", "facing_from")
    positives, low = {}, {}
    for mob, rs in sorted(by.items()):
        positives[str(mob)] = [{k: r.get(k) for k in keys}
                               for r in sorted(rs, key=lambda r: -r["c1"])[:3]]  # fmt: skip
        bad = [r for r in rs if r.get("why_low") == "bad_label"]
        low[str(mob)] = [{k: r.get(k) for k in keys} for r in bad[:: max(1, len(bad) // 8)][:8]]

    def by_species(reason: str) -> dict[str, int]:
        return dict(sorted((k.split(":", 1)[1], v) for k, v in dropped.items()
                           if k.startswith(f"{reason}:")))  # fmt: skip

    excl = by_species("occluded_model")
    if a.rows is not None:
        a.rows.write_text(json.dumps(rows) + "\n")
    return {
        "what": f"C1 / C2 on the labels {labels_name(a.rule, occlusion)} PREDICTION (no fit), "
                "section 3's bars",
        "labels": labels_name(a.rule, occlusion), "facing_rule": a.rule,
        "occlusion": occlusion,
        "occlusion_rule": {"1c": "3b's literal 1c: under a model box -> excluded",
                           "o3": "3i o3: under a model box -> kept when the fit passes (tau, not "
                                 "at the edge), else excluded",
                           "o3h": f"3i o3h: under a model box -> kept when the fit passes and "
                                  f"its NCC >= {O3H_TAU}, else excluded"}[occlusion],
        "under_model_kept_by_species": by_species("under_model_kept"),
        "session": sess.sid, "checked_at": now_ict(), "commit": git_head(),
        "params": str(a.params), "params_sha256": sha256_file(a.params),
        "offset_ms": off_ms, "anchors_px": params["anchors_px"], "k": K, "tau": TAU,
        "every": a.every, "dwells": len(sess.dwells), "frames_read": len(refs),
        "frames_recorded": len(sess.refs),
        "layout_checked_per_frame": sess.layout is not None,
        "standing_rule": {"idle_s": occ.STANDING_NS / 1e9, "isolation_px": occ.ISOLATION_PX,
                          "ui_and_edge_margin_px": SEARCH_PX},
        "dropped": {k: v for k, v in sorted(dropped.items()) if ":" not in k},
        "occluded_model_by_species": excl,
        "next_move_by_species": by_species(NEXT_MOVE),
        "ambiguous_view_by_species": by_species(AMBIGUOUS),
        "monsters_in_sight_by_species": {str(k): v for k, v in sorted(seen.items())},
        "standing_scored_by_species": {str(m): len(rs) for m, rs in sorted(by.items())},
        **result,
        "facing_agreement": agreement(rows),
        "c1_by_self_motion": motion,
        "positive_cases": positives, "bad_label_examples": low,
        "caveats": ["frames are JPEG q80 (warp_watch); M4 fixed tau on H.264 frames",
                    "label_check's grey weights are applied to BGR frames, as in M4"],
    }  # fmt: skip


# --- the labels (0): fitted boxes, for the cache and the blind pack ---------------------------


@dataclass(frozen=True)
class FixLabel:
    gid: int
    mob: int
    box: Box  # the fitted box, clipped to the frame
    raw_box: Box  # unclipped
    ncc: float
    dx: int
    dy: int
    motion: int
    heading: int
    facing_from: str
    state: str
    fit_box: Box | None = None  # the fitted frame's box, clipped, before 3i's W (S3 reads it)


def valid_map(size: tuple[int, int], rects: UiRects) -> npt.NDArray[np.bool_]:
    """True on the frame's pixels outside every UI window (x, y, w, h)."""
    ok = np.ones((size[1], size[0]), bool)
    for x, y, w, h in rects:
        ok[max(0, y) : max(0, y + h), max(0, x) : max(0, x + w)] = False
    return ok


def fit_label_all(grey: npt.NDArray[np.float64], valid: npt.NDArray[np.bool_],
                  sheet: SpriteSheet, pred: SpritePrediction,
                  r: int) -> list[tuple[float, int, int, int]]:  # fmt: skip
    """Every frame's own best (NCC, dx, dy, motion), in frame order: the action's frames (the
    known one when the phase is known), each at its best offset within ``r``, on the visible
    pixels only; frames that score nowhere are left out."""
    i0, j0 = math.floor(pred.box[0]), math.floor(pred.box[1])
    i1, j1 = math.ceil(pred.box[2]), math.ceil(pred.box[3])
    if i1 - i0 < 2 or j1 - j0 < 2:
        return []
    h, w = grey.shape
    wi0, wj0, wi1, wj1 = i0 - r, j0 - r, i1 + r, j1 + r
    obs = np.zeros((wj1 - wj0, wi1 - wi0))
    ok = np.zeros(obs.shape, bool)
    ci0, cj0, ci1, cj1 = max(0, wi0), max(0, wj0), min(w, wi1), min(h, wj1)
    if ci1 <= ci0 or cj1 <= cj0:
        return []
    obs[cj0 - wj0 : cj1 - wj0, ci0 - wi0 : ci1 - wi0] = grey[cj0:cj1, ci0:ci1]
    ok[cj0 - wj0 : cj1 - wj0, ci0 - wi0 : ci1 - wi0] = valid[cj0:cj1, ci0:ci1]
    motions = [pred.motion] if pred.motion is not None else range(sheet.motions(pred.action_index))
    out = []
    for mo in motions:
        tgrey, opaque = label_check.rendered(sheet, pred.action_index, int(mo), pred.anchor_px,
                                             pred.scale, (i0, j0, i1, j1))  # fmt: skip
        grid = shift_ncc_valid(obs, ok, tgrey, opaque, r)
        if np.isnan(grid).all():
            continue
        a_, b_ = np.unravel_index(int(np.nanargmax(grid)), grid.shape)
        out.append((float(grid[a_, b_]), int(b_) - r, int(a_) - r, int(mo)))
    return out


def best_fit(fits: Sequence[tuple[float, int, int, int]]) -> tuple[float, int, int, int] | None:
    """The first frame with the highest NCC (fit_label's choice)."""
    best: tuple[float, int, int, int] | None = None
    for cand in fits:
        if best is None or cand[0] > best[0]:
            best = cand
    return best


def fit_label(grey: npt.NDArray[np.float64], valid: npt.NDArray[np.bool_], sheet: SpriteSheet,
              pred: SpritePrediction, r: int) -> tuple[float, int, int, int] | None:  # fmt: skip
    """(best NCC, dx, dy, motion) over the action's frames (the known one when the phase is
    known) and every offset within ``r``, on the visible pixels only; None when nothing scores."""
    return best_fit(fit_label_all(grey, valid, sheet, pred, r))


def wing_box(sheet: SpriteSheet, pred: SpritePrediction,
             fits: Sequence[tuple[float, int, int, int]], r: int, size: tuple[int, int],
             delta: float = WING_DELTA, pad: float = WING_PAD_PX) -> Box | None:  # fmt: skip
    """3i's W: the union of the boxes of every PLAUSIBLE frame -- its own fit >= the best's NCC -
    ``delta`` and not at the search edge, each at its own best offset; the best frame always in --
    grown by ``pad`` px on every side, clipped to the frame. None when the best draws nothing."""
    best = best_fit(fits)
    if best is None:
        return None
    boxes = []
    for f in fits:
        if f is not best and (f[0] < best[0] - delta or at_edge(f[1], f[2], r)):
            continue
        b = motion_box(sheet, pred, f[3])
        if b is not None:
            boxes.append((b[0] + f[1], b[1] + f[2], b[2] + f[1], b[3] + f[2]))
    if not boxes:
        return None
    w, h = size
    return (max(0.0, min(b[0] for b in boxes) - pad), max(0.0, min(b[1] for b in boxes) - pad),
            min(float(w), max(b[2] for b in boxes) + pad),
            min(float(h), max(b[3] for b in boxes) + pad))  # fmt: skip


def motion_box(sheet: SpriteSheet, pred: SpritePrediction, motion: int) -> Box | None:
    """The rendered box of ONE frame of the predicted action at the prediction's anchor."""
    ext = sheet.extent(pred.action_index, motion)
    if ext is None:
        return None
    ax, ay = pred.anchor_px
    s = pred.scale
    return (ax + s * ext[0], ay + s * ext[1], ax + s * ext[2], ay + s * ext[3])


def visible(box: Box, size: tuple[int, int], rects: UiRects) -> bool:
    """v1's rule for a monster being labelled at all: at least half the box on screen and under
    half of it behind the UI (labels.labels_for_v1)."""
    x0, y0, x1, y1 = box
    bw, bh = x1 - x0, y1 - y0
    cx0, cy0, cx1, cy1 = max(x0, 0), max(y0, 0), min(x1, size[0]), min(y1, size[1])
    on = cx1 - cx0 >= bw / 2 and cy1 - cy0 >= bh / 2
    return on and covered_fraction(box, rects) < 0.5


def overlap(a: Box, b: Box) -> bool:
    return min(a[2], b[2]) > max(a[0], b[0]) and min(a[3], b[3]) > max(a[1], b[1])


@dataclass
class FixFrame:
    t: int
    kept: list[FixLabel]
    excluded: list[tuple[int, int, str]]  # (gid, mob, reason)
    hidden: int  # monsters v1's visibility rule leaves unlabelled (not an exclusion)
    applies: bool = True  # False off orcsdun01: the frame keeps v1's labels (Batt's 3b item 2)
    # without pixels (a dry run): the labels the fit WOULD judge, (gid, mob, predicted box)
    pending: list[tuple[int, int, Box]] = field(default_factory=list)
    # 3i: every visible monster's evidence (decide() gives any candidate's verdict from it)
    fates: list[LabelFate] = field(default_factory=list)


class FixLabeler:
    """The labels v2orc-fix monster boxes of a frame (section 3b, 0 + 1a-1d), with 3i's options:
    ``occlusion`` (1c / o3h / o3), ``stack`` (S3) and ``wing`` (W for the WING_MOBS). Without
    them it is 3b / 3f's labeller, unchanged. ``fit_all`` also fits the labels under a model box
    under 1c (3i's round-4 pack: every candidate's verdict from one pass, ``FixFrame.fates``)."""

    def __init__(self, lab: qa_export.Labeler, params: dict[str, Any],
                 occluders: Occluders | None = None, rule: str = "1a",
                 occlusion: str = "1c", stack: bool = False, wing: bool = False,
                 fit_all: bool = False, map_name: str = MAP) -> None:  # fmt: skip
        if occlusion not in OCCLUSIONS:
            raise SystemExit(f"--occlusion {occlusion!r}: one of {OCCLUSIONS}")
        self.lab = lab
        self.map_name = map_name  # the map whose models the occluders are (payf07-detector.md)
        self.o3h_tau = float(params.get("o3h_tau", O3H_TAU))  # 3i's 0.48 unless frozen per map
        self.params = params
        self.rule = rule
        self.occlusion, self.stack, self.wing, self.fit_all = occlusion, stack, wing, fit_all
        self.facing = FacingRule.for_events(rule, getattr(lab.timeline, "events", ()))
        self.offset_ns = int(float(params["offset_ms"]) * 1e6)
        self.anchors = anchors_of(params)
        self.occluders = occluders if occluders is not None else occluders_of(params)
        self.fit_px = {int(k): int(v) for k, v in params["fit_px"].items()}
        self.tau = float(params["tau"])
        self.valid = valid_map(lab.size, lab.ui_rects)

    def fate(self, e: EntityState, st: ActorState, sheet: SpriteSheet, pred: SpritePrediction,
             facing: tuple[int, str], why: str | None, under: bool,
             grey: npt.NDArray[np.float64],
             unit_boxes: Sequence[tuple[int, Box]]) -> LabelFate:  # fmt: skip
        """One label's evidence: the fit (3b item 0), its failure reason, its boxes and W."""
        lab = self.lab
        base = LabelFate(e.gid, e.job, under, why, None, "unfit", heading=facing[0],
                         facing_from=facing[1], state=st.state)  # fmt: skip
        r = self.fit_px.get(int(e.job), 6)
        fits = fit_label_all(grey, self.valid, sheet, pred, r)
        fit = best_fit(fits)
        if fit is None or fit[0] < self.tau or at_edge(fit[1], fit[2], r):
            crowd = any(g != e.gid and overlap(pred.box, b) for g, b in unit_boxes)
            grown = (pred.box[0] - r, pred.box[1] - r, pred.box[2] + r, pred.box[3] + r)
            ui = covered_fraction(grown, lab.ui_rects) > 0
            return replace(base, fit=fit, fail="crowd" if crowd else "ui" if ui else "unfit")
        raw = motion_box(sheet, pred, fit[3])
        if raw is None:
            return replace(base, fit=fit)  # fail stays "unfit"
        raw = (raw[0] + fit[1], raw[1] + fit[2], raw[2] + fit[1], raw[3] + fit[2])
        w, h = lab.size
        box = (max(0.0, raw[0]), max(0.0, raw[1]), min(float(w), raw[2]), min(float(h), raw[3]))
        wbox = wing_box(sheet, pred, fits, r, lab.size) if int(e.job) in WING_MOBS else None
        return replace(base, fit=fit, fail=None, box=box, raw=raw, wbox=wbox)

    def label(self, f: LabelFate) -> FixLabel:
        """A kept fate as the label written: W's box for the WING_MOBS when ``wing``."""
        assert f.fit is not None and f.box is not None and f.raw is not None
        box = f.wbox if (self.wing and f.wbox is not None) else f.box
        return FixLabel(f.gid, f.mob, box, f.raw, round(f.fit[0], 4), f.fit[1], f.fit[2],
                        f.fit[3], f.heading, f.facing_from, f.state, fit_box=f.box)  # fmt: skip

    def frame(self, t: int, bgr: npt.NDArray[np.uint8] | None) -> FixFrame | None:
        """The frame's fitted labels and exclusions. ``bgr=None`` (a dry run: packets only) runs
        every rule up to the fit -- visibility, 1c (under 1c), 2b, 2c -- and lists the labels the
        fit would judge in ``pending`` (their unfit / crowd / UI / o3 / S3 fates need the
        pixels)."""
        lab = self.lab
        tw = t - self.offset_ns
        replay, world, all_states, rules = lab.timeline.at_world(tw)
        if world.self_pos is None or not world.map:
            return None
        if map_key(world.map) != self.map_name:
            return FixFrame(t, [], [], 0, applies=False)  # the fix (and its models) is the map's
        scene = occ.scene_for(lab, world.map, world.self_pos)
        states = {s.gid: s for s in all_states}
        grey = None if bgr is None else bgr[:, :, :3].astype(float) @ label_check.GREY
        preds: list[tuple[EntityState, ActorState, SpriteSheet, SpritePrediction,
                          tuple[int, str], str | None]] = []  # fmt: skip
        out = FixFrame(t, [], [], 0)
        unit_boxes: list[tuple[int, Box]] = []
        me = anchor_and_depth(scene, scene.player)[0]
        unit_boxes.append((-1, (me[0] - 17, me[1] - 74, me[0] + 17, me[1])))  # our GM (v0 size)
        for e in world.entities:
            if e.objtype == 0 and not e.hidden:
                u, _z = anchor_and_depth(scene, (e.x, e.y))
                unit_boxes.append((e.gid, (u[0] - 17, u[1] - 74, u[0] + 17, u[1])))
            if e.objtype != 5 or e.hidden:
                continue
            st, sheet = states.get(e.gid), lab.sheets(e.job)
            if st is None or sheet is None:
                continue
            facing, why = self.facing.choose(replay, e, st, rules, tw, sheet, scene.camera.yaw)
            pred = predict(e, st, sheet, scene, facing[0], self.anchors)
            if pred is None:
                continue
            if not visible(pred.box, lab.size, lab.ui_rects):
                out.hidden += 1
                continue
            preds.append((e, st, sheet, pred, facing, why))
            unit_boxes.append((e.gid, pred.box))
        fit_under = self.fit_all or self.occlusion != "1c"
        for e, st, sheet, pred, facing, why in preds:
            under = self.occluders.hit(scene, pred.box) is not None
            if (under and not fit_under) or why is not None or grey is None:
                if grey is None and not (under and self.occlusion == "1c") and why is None:
                    out.pending.append((e.gid, e.job, pred.box))  # no pixels: the fit's fate
                    continue
                out.fates.append(LabelFate(e.gid, e.job, under, why, None, None,
                                           heading=facing[0], facing_from=facing[1],
                                           state=st.state))  # fmt: skip
                continue
            out.fates.append(self.fate(e, st, sheet, pred, facing, why, under, grey, unit_boxes))
        kept, out.excluded = decide(out.fates, self.occlusion, self.stack, self.o3h_tau)
        out.kept = [self.label(f) for f in kept]
        return out


# --- CLI --------------------------------------------------------------------------------------


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    def common(p: argparse.ArgumentParser, session: bool = True) -> None:
        if session:
            p.add_argument("session", type=Path)
            p.add_argument("--kb", type=Path, default=ROOT / "data" / "kb")
            p.add_argument("--every", type=int, default=5)
            p.add_argument("--workers", type=int, default=1, help="forked worker processes")
        p.add_argument("--rsw", type=Path, default=RSW_PATH)
        p.add_argument("--models", type=Path, default=MODEL_DIR)
        p.add_argument("--out", type=Path, required=True)

    common(sub.add_parser("offset"))
    p = sub.add_parser("anchor")
    common(p)
    p.add_argument("--offset", type=Path, required=True)
    p = sub.add_parser("freeze")
    common(p, session=False)
    p.add_argument("--offset", type=Path, required=True)
    p.add_argument("--anchor", type=Path, required=True)
    p = sub.add_parser("check")
    common(p)
    p.add_argument(
        "--layout-templates",
        type=Path,
        default=None,
        help="a human demo: client_layout's templates (default its TEMPLATES)",
    )
    p.add_argument("--params", type=Path, required=True)
    p.add_argument("--rule", choices=RULES, default="1a",
                   help="the facing: 1a (3b, as 3c ran) or fix2 (3f, with 2b / 2c)")  # fmt: skip
    p.add_argument("--rows", type=Path, default=None, help="also every scored row (JSON)")
    p.add_argument("--occlusion", choices=OCCLUSIONS, default="1c",
                   help="3i: 1c (3b's literal rule), o3h or o3 (an under-box label's fit "
                        "decides); S3 never changes C1 (the standing rule isolates)")  # fmt: skip
    a = ap.parse_args(argv)
    run = {"offset": cmd_offset, "anchor": cmd_anchor, "freeze": cmd_freeze, "check": cmd_check}
    out = run[a.cmd](a)
    text = json.dumps(out, indent=1)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(text + "\n")
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
