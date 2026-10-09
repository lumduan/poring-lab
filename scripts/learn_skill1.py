#!/usr/bin/env python3
"""learn_skill@1 (docs/demonstrations.md 3.34): spend skill points in the skill window. BUILT
OFFLINE 2026-10-09 from the live looks' banked frames; NOT pre-registered, NOT run.

    learn_skill1.py cut   [--banked DIR] [--data DIR]  the run-time templates, cut from the banked
                                                      look frames into data/ui_anchors/learn_skill/
    learn_skill1.py prove [--banked DIR] [--data DIR]  every reader on the banked frames: expected
                                                      vs read; exit 1 on any mismatch
    learn_skill1.py run --n N --seed S --restore skreset|charselect [--skreset-allowed] [--label L]

GEOMETRY: the L2 binding `skill_tree` (packages/poring_skills/.../kro-20211103-prere.yaml), loaded
at run time; absent or incomplete = nothing done (Unbound). Window-relative to the `skills` window's
LOCATED origin (ADR-0011 anchor, searched within HOME_PX of its home as ui_gate does); the confirm
modal is client-relative (the client centres it on its area).

THE READERS (pure: a 1280x720 BGR client frame in, a value or None with a reason out):
* window: the `skills` anchor within HOME_PX of its home (ui_gate's own match and threshold);
* tentative: the red +N right of Basic Skill's icon (red ink, nothing else; its digest changes
  with N, so a raise the client ignored is seen);
* modal: the confirm modal by its OWN pixels (the mask of where it changes the window) against
  its template and against the no-modal reference, at its fixed client place; neither = None;
* points: the points line in the weight readout's font (poring_env.weight's glyphs): the label
  by its template, then the number's cells from first_cell; coloured ink = a tentative raise
  (None, "tentative"); any mark the digits do not explain, a low margin, a '/', a leading zero =
  None. The caller asks two fresh frames to agree;
* level: ink in the box under the icon (the level digit). A digit is CLASSIFIED only as one seen
  live: "1" (look5); any other ink is "unseen", never guessed.

THE RULE (one trial; `learn_skill`, through the Io seam so it is tested offline):
  open the window by its chord if not at home -> the points read P on two fresh frames (= the
  harness's expected 9) -> N clicks on the icon, paced, each followed by a NEW tentative -> APPLY
  -> the modal within MODAL_S -> OK -> the points read P - N within POINTS_S -> close by the chord.
  Every refusal is a recorded decline with its reason. States left behind are closed ONLY by known
  steps (`close_known`: the modal by CANCEL, a tentative raise by RESET, the window by its chord);
  anything unreadable STOPS. The UI gate (ui_gate) does NOT see the tentative or the modal (it
  sees the window and would close it by its chord), so `close_known` runs before every typed line.

THE HARNESS (`run`, rule_run's shape: a DemoLog session, a DemoRecord per rule trial and per
harness action, trials.json, the packets at the end), per trial: close_known -> gm_state's fixed
state -> START STATE (the window open: points 0 and the level box EMPTY; a stale level digit =
the client out of sync -> the restore's sync once, else stop) -> @joblevelup 9 -> the notices
cleared -> the rule (N from the seed: shuffled blocks of 1..9) -> close_known if it declined ->
the restore -> the fixed state again. Two consecutive harness stops end the run.
* restore skreset: @skreset, then @joblevelup -49. @skreset is NOT in group 20 today: refused
  unless --skreset-allowed (Batt's decision, 3.34; groups.yml is his).
* restore charselect: @joblevelup -49, then character select and back in (the full skill list
  comes with a new map-server connection). The in-game route to character select is UNMEASURED
  (no L2 binding for the game option window's button): refused until it is measured.
Packets are never read here (rule 1): learn_skill1_score.py judges the session offline.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import sys
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ro_agent as r  # noqa: E402

RULE = "learn_skill@1"
HARNESS = "rule:harness@1"
CLIENT = "kro-20211103-prere"  # the lab client's L2 build
SKILL = "basic_skill"  # the L2 entry under skill_tree.novice
EXPECTED_POINTS = 9  # @joblevelup 9 from Job Lv 1 (3.34)
START_POINTS = 0  # the fixed state: Job Lv 1, nothing to spend
JOB_UP = "@joblevelup 9"
JOB_DOWN = "@joblevelup -49"
SKRESET = "@skreset"
S = 1_000_000_000

ROOT = r.ROOT
TEMPLATE_SUBDIR = Path("ui_anchors") / "learn_skill"
BANKED = Path("/dev/shm/poring-lab-tmp/learn_skill")
BANKED_REGION = (80, 77, 1280, 720)  # the frozen layout: client px = desktop px - (80, 77)
HOME_PX = 12  # ui_gate.HOME_PX: a window's search box around its home, each side
PARK = ((1250, 380), (1250, 300))  # ui_gate's / talk1's rest points, right of every window

PACE_S = 0.35  # between a raise click and the look at its tentative
OPEN_S = 1.2  # after a window chord
MODAL_S = 2.0  # APPLY -> the modal
POINTS_S = 3.0  # OK -> the points read P - N
STEP_S = 0.8  # after a known closing step
SETTLE_S = 0.6  # the cursor parked (two motions) before a look
STABLE_TRIES = 6  # looks until two in a row agree
MAX_CLOSE_STEPS = 4  # CANCEL, RESET, the chord, and one spare
GM_SETTLE_S = 2.0
INTERLOCK_WAIT_S = 15.0  # /health's interlock view after character select (1 Hz ticks)
BETWEEN_S = 3.0
MAX_STOPS = 2  # consecutive harness stops end the run

# reader thresholds (client pixels; checked by `prove` on the banked frames)
RED_R, RED_GB = 150, 100  # red ink: R >= 150 and G, B < 100 (the +N, measured 255/0/0)
TENT_MIN_RED = 8  # a +N has ~20 red pixels
TENT_MAX_STRAY = 2  # dark, not-red pixels allowed in the tentative box
DARK = 128.0  # grey below this is ink (the level digit is black on white)
LEVEL_MIN_INK = 6  # the "1" seen live has 24 dark pixels
LEVEL_MAX_EMPTY = 1
GLYPH_XOR = 3  # pixels a seen digit may differ from its template
MODAL_DIFF = 40.0  # grey levels: a mask pixel "matches" within this
MODAL_SHARE = 0.85  # share of the modal's own pixels that must match
MASK_DIFF = 30.0  # cut time: where the modal changes the window (its own pixels)
LABEL_FRAC = 0.2  # the points label may score up to this share of its own ink mass
COLOUR_SPREAD = 80  # max(B, G, R) - min(...) above this on an ink pixel = coloured ink
COLOUR_MIN = 3  # this many coloured ink pixels in the band = a tentative raise
INK_PROB = 0.5

SKRESET_REFUSED = (
    "restore skreset refused: @skreset is NOT in the GM's group 20 "
    "(services/rathena/conf/import/groups.yml); adding it is Batt's call (demonstrations 3.34). "
    "Pass --skreset-allowed only after his decision and the groups.yml change are live."
)
CHARSELECT_UNMEASURED = (
    "unmeasured: the in-game route to character select (no L2 binding game_option.char_select: "
    "the game option window's button, opened by the system_menu shortcut). Measure it live "
    "(a banked frame of the open window, the button's box, the char_select signature after it, "
    "the client's skill window after re-entering) before using --restore charselect."
)

Box = tuple[int, int, int, int]
XY = tuple[int, int]


class Unbound(SystemExit):
    """A binding or a template the rule needs is missing: nothing is done."""


# --- geometry (L2) ------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Geometry:
    window: str
    icon: Box  # window-relative
    click: XY
    tentative: Box
    level: Box
    label: Box
    band: Box
    first_cell: int
    apply: Box
    reset: Box
    modal: Box  # client-relative
    ok: Box
    cancel: Box


def _nums(v: Any, n: int) -> list[int]:
    if not isinstance(v, (list, tuple)) or len(v) != n:
        raise ValueError(f"expected {n} numbers, got {v!r}")
    return [int(x) for x in v]


def _box(v: Any) -> Box:
    x, y, w, h = _nums(v, 4)
    return x, y, w, h


def _xy(v: Any) -> XY:
    x, y = _nums(v, 2)
    return x, y


def geometry_from(l2: dict[str, Any], skill: str = SKILL) -> Geometry:
    """The skill window's geometry from an L2 build's `skill_tree`; Unbound when absent."""
    st = l2.get("skill_tree")
    if not isinstance(st, dict):
        raise Unbound(f"L2 {l2.get('client')}: no skill_tree binding: learn_skill@1 does nothing")
    try:
        sk, pts, md = st["novice"][skill], st["points"], st["modal"]
        return Geometry(
            window=str(st["window"]), icon=_box(sk["icon"]), click=_xy(sk["click"]),
            tentative=_box(sk["tentative"]), level=_box(sk["level"]), label=_box(pts["label"]),
            band=_box(pts["band"]), first_cell=int(pts["first_cell"]), apply=_box(st["apply"]),
            reset=_box(st["reset"]), modal=_box(md["box"]), ok=_box(md["ok"]),
            cancel=_box(md["cancel"]),
        )  # fmt: skip
    except (KeyError, TypeError, ValueError) as exc:
        where = l2.get("client")
        raise Unbound(f"L2 {where}: skill_tree incomplete ({exc!r}): nothing done") from None


def load_geometry() -> Geometry:
    from poring_skills.resolve import load_l2

    return geometry_from(load_l2(CLIENT))


def window_keys(window: str = "skills") -> list[str]:
    from poring_skills.resolve import load_l2

    return list(load_l2(CLIENT)["shortcut"]["window"][window]["keys"])


def centre(box: Box) -> XY:
    return box[0] + box[2] // 2, box[1] + box[3] // 2


def at(origin: XY, box: Box) -> Box:
    """A window-relative box in client pixels."""
    return origin[0] + box[0], origin[1] + box[1], box[2], box[3]


# --- templates (data/ui_anchors/learn_skill/, cut locally; never committed) -----------------------


@dataclass(frozen=True)
class Refs:
    window: Any  # the skills anchor (grey), its mask (or None), threshold, offset, home
    window_mask: Any
    window_max: float
    window_offset: XY
    home: XY
    modal: Any  # grey, the modal box
    nomodal: Any  # grey, the same box without the modal
    modal_mask: Any  # bool: the modal's own pixels
    label: Any  # ink probability of the points label
    level_one: Any  # bool: the dark pixels of the level digit "1"
    glyphs: Any  # poring_env.weight.WeightGlyphs
    meta: dict[str, Any] = field(default_factory=dict)


REF_FILES = ("modal.npy", "nomodal.npy", "modal_mask.npy", "label.npy", "level_one.npy")


def load_refs(data: Path) -> Refs:
    """Every template the readers need, or Unbound naming what is missing."""
    from poring_env import ui_anchors as ua
    from poring_env import weight as wt

    d = data / TEMPLATE_SUBDIR
    missing = [f for f in REF_FILES if not (d / f).exists()]
    reg = ua.default_registry(data / "ui_anchors")
    if "skills" not in reg.templates:
        missing.append("ui_anchors/skills.npy")
    glyph_path = data / "ui_anchors" / "weight_glyphs.npz"
    if not glyph_path.exists():
        missing.append("ui_anchors/weight_glyphs.npz")
    if missing:
        raise Unbound(f"learn_skill@1: templates missing in {data}: {missing} (`learn_skill1.py "
                      "cut`; weight_calibrate.py; open_window@1's anchors)")  # fmt: skip
    glyphs = wt.load_weight_glyphs(glyph_path)
    if not glyphs.complete:
        raise Unbound(f"weight glyphs incomplete ({glyphs.missing}): the points are never read")
    spec = reg.windows["skills"]
    meta_path = d / "meta.json"
    return Refs(
        window=reg.templates["skills"], window_mask=reg.masks.get("skills"),
        window_max=spec.max_distance, window_offset=spec.template_offset,
        home=ua.CAPTURE_ORIGINS["skills"],
        modal=np.load(d / "modal.npy"), nomodal=np.load(d / "nomodal.npy"),
        modal_mask=np.load(d / "modal_mask.npy").astype(bool), label=np.load(d / "label.npy"),
        level_one=np.load(d / "level_one.npy").astype(bool), glyphs=glyphs,
        meta=json.loads(meta_path.read_text()) if meta_path.exists() else {},
    )  # fmt: skip


# --- the readers (pure) -------------------------------------------------------------------------


def to_gray(bgr: Any) -> Any:
    f = np.asarray(bgr[..., :3], np.float32)
    return 0.114 * f[..., 0] + 0.587 * f[..., 1] + 0.299 * f[..., 2]


def crop(frame: Any, box: Box) -> Any | None:
    x, y, w, h = box
    if x < 0 or y < 0 or y + h > frame.shape[0] or x + w > frame.shape[1]:
        return None
    return frame[y : y + h, x : x + w]


def window_origin(frame: Any, refs: Refs) -> tuple[XY | None, str]:
    """The skills window's origin when its anchor shows within HOME_PX of its home (ui_gate's
    windows_at_home, returning where it matched)."""
    from poring_env import ui_anchors as ua

    gray = to_gray(frame)
    h, w = gray.shape
    (hx, hy), (ox, oy) = refs.home, refs.window_offset
    th, tw = refs.window.shape
    tx, ty = hx + ox, hy + oy
    x0, y0 = max(0, tx - HOME_PX), max(0, ty - HOME_PX)
    x1, y1 = min(w, tx + tw + HOME_PX), min(h, ty + th + HOME_PX)
    if x1 - x0 < tw or y1 - y0 < th:
        return None, "home_outside_frame"
    m = ua.match_template(gray[y0:y1, x0:x1], refs.window, refs.window_mask)
    if m is None or m.distance > refs.window_max:
        return None, f"not_at_home({'-' if m is None else round(m.distance, 1)})"
    return (x0 + m.origin[0] - ox, y0 + m.origin[1] - oy), "ok"


def red_mask(bgr: Any) -> Any:
    b, g, rr = (bgr[..., i].astype(np.int32) for i in range(3))
    return (rr >= RED_R) & (g < RED_GB) & (b < RED_GB)


def tentative(frame: Any, origin: XY, geo: Geometry) -> tuple[bool | None, str, str | None]:
    """(shown, reason, digest): the red +N right of the icon. Red ink and nothing else = shown;
    no ink = not shown; anything else = None."""
    c = crop(frame, at(origin, geo.tentative))
    if c is None:
        return None, "outside_frame", None
    red = red_mask(c)
    reddish = (c[..., 2].astype(np.int32) - np.maximum(c[..., 0], c[..., 1]).astype(np.int32)) > 60
    stray = int(((to_gray(c) < DARK) & ~red & ~reddish).sum())
    n_red = int(red.sum())
    if stray > TENT_MAX_STRAY:
        return None, f"unexplained_ink(red {n_red}, other {stray})", None
    if n_red >= TENT_MIN_RED:
        return True, "ok", hashlib.sha1(np.packbits(red).tobytes()).hexdigest()[:12]
    if n_red == 0:
        return False, "ok", None
    return None, f"faint_red({n_red})", None


def modal(frame: Any, geo: Geometry, refs: Refs) -> tuple[bool | None, str]:
    """The confirm modal by its own pixels: its template vs the no-modal reference."""
    c = crop(frame, geo.modal)
    if c is None or c.shape[:2] != refs.modal.shape:
        return None, "outside_frame"
    g = to_gray(c)
    m = refs.modal_mask
    on = float((np.abs(g - refs.modal)[m] < MODAL_DIFF).mean())
    off = float((np.abs(g - refs.nomodal)[m] < MODAL_DIFF).mean())
    why = f"modal {on:.2f} / none {off:.2f}"
    if on >= MODAL_SHARE > off:
        return True, why
    if off >= MODAL_SHARE > on:
        return False, why
    return None, f"neither: {why}"


def points(frame: Any, origin: XY, geo: Geometry, refs: Refs) -> tuple[int | None, str]:
    """The points line's number (the weight font), or None with a reason."""
    from poring_env import weight as wt

    glyphs = refs.glyphs
    if not glyphs.complete:
        return None, "incomplete_templates"
    lx, ly, lw, lh = at(origin, geo.label)
    bx, by, bw, bh = at(origin, geo.band)
    ch, cw = glyphs.geometry.cell
    if bh != ch or lh != refs.label.shape[0] or lw != refs.label.shape[1]:
        return None, "geometry_mismatch"
    x0, y0 = min(lx, bx), min(ly, by)
    x1, y1 = max(lx + lw, bx + bw), max(ly + lh, by + bh)
    line = crop(frame, (x0, y0, x1 - x0, y1 - y0))
    if line is None:
        return None, "outside_frame"
    gray = to_gray(line)
    paper = float(np.median(gray))
    if paper < wt.MIN_PAPER or paper - glyphs.ink < 40:
        return None, "no_window"
    prob = np.clip((paper - gray) / (paper - glyphs.ink), 0, 1)
    lab = prob[ly - y0 : ly - y0 + lh, lx - x0 : lx - x0 + lw]
    mass = float((refs.label**2).sum())
    if float(((lab - refs.label) ** 2).sum()) > LABEL_FRAC * mass:
        return None, "no_label"
    band = prob[by - y0 : by - y0 + bh, bx - x0 : bx - x0 + bw]
    bgr = line[by - y0 : by - y0 + bh, bx - x0 : bx - x0 + bw].astype(np.int32)
    spread = bgr.max(axis=-1) - bgr.min(axis=-1)
    if int(((band >= INK_PROB) & (spread > COLOUR_SPREAD)).sum()) >= COLOUR_MIN:
        return None, "tentative"
    tokens = wt._accept(wt.band_scores(band, glyphs), glyphs)  # noqa: SLF001 -- the same font
    if not tokens:
        return None, "no_digits"
    if any(t.symbol == "/" for t in tokens):
        return None, "layout:slash"
    if tokens[0].x != geo.first_cell - geo.band[0]:
        return None, f"misplaced({tokens[0].x})"
    pitch = glyphs.geometry.pitch
    if any(b.x - a.x != pitch for a, b in zip(tokens, tokens[1:], strict=False)):
        return None, "off_pitch"
    covered = np.zeros(band.shape[1], bool)
    for t in tokens:
        covered[t.x : t.x + cw] = True
    marks = np.flatnonzero((band >= wt.MARK_PROB).any(axis=0))
    if marks.size and not covered[marks].all():
        return None, "unexplained_ink"
    if any(t.margin < glyphs.min_margin for t in tokens):
        return None, "ambiguous"
    if len(tokens) > 1 and tokens[0].symbol == "0":
        return None, "leading_zero"
    return int("".join(t.symbol for t in tokens)), "ok"


def level(frame: Any, origin: XY, geo: Geometry, refs: Refs) -> tuple[bool | None, str | None]:
    """(ink under the icon, the digit if SEEN before): False = empty, None = faint ink."""
    c = crop(frame, at(origin, geo.level))
    if c is None:
        return None, None
    dark = to_gray(c) < DARK
    n = int(dark.sum())
    if n <= LEVEL_MAX_EMPTY:
        return False, None
    if n < LEVEL_MIN_INK:
        return None, None
    if dark.shape == refs.level_one.shape and int((dark ^ refs.level_one).sum()) <= GLYPH_XOR:
        return True, "1"
    return True, "unseen"


@dataclass(frozen=True)
class Seen:
    """Everything the rule reads from one frame."""

    window: bool
    origin: XY | None = None
    tentative: bool | None = None
    tent_digest: str | None = None
    modal: bool | None = None
    points: int | None = None
    points_reason: str = "no_window"
    level_ink: bool | None = None
    level_glyph: str | None = None
    why: dict[str, str] = field(default_factory=dict, compare=False)

    def key(self) -> tuple[Any, ...]:
        return (self.window, self.origin, self.tentative, self.tent_digest, self.modal,
                self.points, self.points_reason, self.level_ink, self.level_glyph)  # fmt: skip

    def as_dict(self) -> dict[str, Any]:
        return {"window": self.window, "origin": self.origin, "tentative": self.tentative,
                "tent_digest": self.tent_digest, "modal": self.modal, "points": self.points,
                "points_reason": self.points_reason, "level_ink": self.level_ink,
                "level_glyph": self.level_glyph, "why": self.why}  # fmt: skip


def read_all(frame: Any, geo: Geometry, refs: Refs) -> Seen:
    """Every reader on one client frame. Without the window at home nothing else is read: its
    boxes would show the scene."""
    origin, why_w = window_origin(frame, refs)
    if origin is None:
        return Seen(window=False, why={"window": why_w})
    tent, why_t, digest = tentative(frame, origin, geo)
    mod, why_m = modal(frame, geo, refs)
    pts, why_p = points(frame, origin, geo, refs)
    ink, glyph = level(frame, origin, geo, refs)
    return Seen(True, origin, tent, digest, mod, pts, why_p, ink, glyph,
                why={"tentative": why_t, "modal": why_m})  # fmt: skip


# --- the rule (through the Io seam) ---------------------------------------------------------------


class Io(Protocol):
    def look(self) -> Seen: ...  # a FRESH frame (after the last action), the cursor parked

    def ui_click(self, xy: XY, what: str, inside: Box) -> int: ...  # client px; refused outside

    def chord(self, keys: Sequence[str]) -> int: ...

    def now(self) -> int: ...

    def wait(self, seconds: float) -> None: ...


def stable(io: Io, tries: int = STABLE_TRIES) -> Seen | None:
    """A reading two consecutive fresh frames agree on, or None."""
    prev = io.look()
    for _ in range(tries):
        cur = io.look()
        if cur.key() == prev.key():
            return cur
        prev = cur
    return None


def wait_for(io: Io, want: Callable[[Seen], bool],
             timeout: float) -> tuple[Seen | None, Seen | None]:  # fmt: skip
    """(the first stable reading satisfying ``want`` within ``timeout``, the last stable one)."""
    end = io.now() + int(timeout * S)
    last: Seen | None = None
    while True:
        s = stable(io, tries=2)
        if s is not None:
            last = s
            if want(s):
                return s, last
        if io.now() >= end:
            return None, last
        io.wait(0.2)


def learn_skill(io: Io, geo: Geometry, keys: Sequence[str], n: int,
                expected: int = EXPECTED_POINTS) -> dict[str, Any]:  # fmt: skip
    """learn_skill@1, ONE trial: raise Basic Skill by ``n`` through the skill window. Never raises
    for the client's state: every refusal is ``decline`` (the caller closes what is left with
    close_known). The runtime outcome: the points read ``expected - n`` after OK."""
    out: dict[str, Any] = {"n": n, "expected": expected, "steps": [], "decline": None,
                           "runtime": None, "clicks": [], "chords": []}  # fmt: skip

    def step(do: str, **kw: Any) -> None:
        out["steps"].append({"t": io.now(), "do": do, **kw})

    def decline(why: str, seen: Seen | None = None) -> dict[str, Any]:
        out["decline"] = why
        out["seen_at_decline"] = seen.as_dict() if seen is not None else None
        return out

    def click(xy: XY, what: str, inside: Box) -> int:
        t = io.ui_click(xy, what, inside)
        out["clicks"].append({"t": t, "what": what, "xy": list(xy)})
        step("click", what=what, xy=list(xy))
        return t

    def chord(why: str) -> None:
        t = io.chord(keys)
        out["chords"].append({"t": t, "why": why})
        step("chord", why=why)

    if not 1 <= n <= expected:
        return decline(f"n_out_of_range:{n}")
    s = stable(io)
    if s is None:
        return decline("unstable_start")
    if not s.window:
        chord("open")
        io.wait(OPEN_S)
        s = stable(io)
        if s is None or not s.window:
            return decline("window_not_open", s)
    if s.modal is not False or s.tentative is not False:
        return decline(f"start_state:modal={s.modal},tentative={s.tentative}", s)
    if s.points is None:
        return decline(f"points_unread:{s.points_reason}", s)
    if s.points != expected:
        return decline(f"points_not_expected:{s.points}", s)
    out["points_before"] = s.points
    out["origin"] = list(s.origin) if s.origin else None
    origin = s.origin
    assert origin is not None  # noqa: S101 -- window True always carries its origin
    icon = at(origin, geo.icon)
    prev = s.tent_digest
    for k in range(1, n + 1):
        click((origin[0] + geo.click[0], origin[1] + geo.click[1]), f"raise {k}/{n}", icon)
        io.wait(PACE_S)
        s = stable(io)
        if s is None:
            return decline(f"unstable_after_raise_{k}")
        if not s.window or s.modal is not False:
            return decline(f"unexpected_after_raise_{k}", s)
        if s.tentative is not True:
            return decline(f"no_tentative_after_raise_{k}", s)
        if s.tent_digest == prev:
            return decline(f"tentative_unchanged_after_raise_{k}", s)
        if s.origin != origin:
            return decline(f"window_moved_after_raise_{k}", s)
        prev = s.tent_digest
    apply = at(origin, geo.apply)
    out["t_apply"] = click(centre(apply), "apply", apply)
    s, last = wait_for(io, lambda x: x.modal is True, MODAL_S)
    if s is None:
        return decline("no_modal", last)
    out["t_ok"] = click(centre(geo.ok), "ok", geo.ok)
    want = expected - n

    def settled(x: Seen) -> bool:
        return x.window and x.modal is False and x.tentative is False and x.points == want

    s, last = wait_for(io, settled, POINTS_S)
    if s is None:
        got = "unstable" if last is None else f"{last.points}/{last.points_reason}"
        return decline(f"points_after:{got}", last)
    out["runtime"] = {"points_after": s.points, "level_ink": s.level_ink,
                      "level_glyph": s.level_glyph}  # fmt: skip
    chord("close")
    io.wait(OPEN_S)
    s = stable(io)
    if s is None or s.window:
        return decline("window_not_closed", s)
    out["result_runtime"] = "applied"
    return out


def decide_close(s: Seen | None) -> dict[str, str]:
    """PURE: the next KNOWN closing step for a reading, or stop."""
    if s is None:
        return {"do": "stop", "why": "unstable"}
    if not s.window:
        return {"do": "clear"}
    if s.modal is None:
        return {"do": "stop", "why": f"modal_unreadable:{s.why.get('modal')}"}
    if s.modal:
        return {"do": "cancel"}
    if s.tentative is None:
        return {"do": "stop", "why": f"tentative_unreadable:{s.why.get('tentative')}"}
    if s.tentative:
        return {"do": "reset"}
    return {"do": "chord"}


def close_known(io: Io, geo: Geometry, keys: Sequence[str],
                on_step: Callable[[dict[str, Any]], None] | None = None,
                ) -> list[dict[str, Any]]:  # fmt: skip
    """Close the skill window's states by KNOWN steps only (the modal by CANCEL, a tentative
    raise by RESET, the window by its chord); r.Stop on anything else."""
    steps: list[dict[str, Any]] = []
    for _ in range(MAX_CLOSE_STEPS + 1):
        s = stable(io)
        d = decide_close(s)
        if d["do"] == "clear":
            return steps
        if d["do"] == "stop" or len(steps) == MAX_CLOSE_STEPS:
            raise r.Stop(f"learn_skill@1 close_known: {d.get('why', 'too_many_steps')} "
                         f"after {[x['do'] for x in steps]}: left for a person")  # fmt: skip
        assert s is not None and s.origin is not None  # noqa: S101 -- decide_close said window
        if d["do"] == "cancel":
            t = io.ui_click(centre(geo.cancel), "cancel", geo.cancel)
        elif d["do"] == "reset":
            box = at(s.origin, geo.reset)
            t = io.ui_click(centre(box), "reset", box)
        else:
            t = io.chord(keys)
        rec = {"do": d["do"], "t": t, "seen": s.as_dict()}
        steps.append(rec)
        if on_step is not None:
            on_step(rec)
        io.wait(STEP_S)
    raise AssertionError("unreachable")


def n_plan(n: int, seed: int) -> list[int]:
    """The trials' N: shuffled blocks of 1..9 (every N equally often), seeded."""
    rng = random.Random(seed)
    out: list[int] = []
    while len(out) < n:
        block = list(range(1, EXPECTED_POINTS + 1))
        rng.shuffle(block)
        out += block
    return out[:n]


def check_restore(restore: str, skreset_allowed: bool, l2: dict[str, Any]) -> dict[str, Any]:
    """Refuse a restore mode that cannot run (before anything is sent)."""
    if restore == "skreset":
        if not skreset_allowed:
            raise SystemExit(SKRESET_REFUSED)
        return {}
    if restore == "charselect":
        go = l2.get("game_option")
        btn = go.get("char_select") if isinstance(go, dict) else None
        if not isinstance(btn, dict) or "box" not in btn:
            raise Unbound(CHARSELECT_UNMEASURED)
        return {"char_select": _box(btn["box"])}
    raise SystemExit(f"unknown restore {restore!r}")


# --- the live parts -----------------------------------------------------------------------------


class LiveIo:
    """The client through ro_agent: the cursor parked away from the windows before a frame is
    judged (two motions), frames decoded after the last action, and THE one UI click of
    learn_skill@1 (test_click_census.py), refused outside the box it names."""

    def __init__(self, agent: Any, screen: Any, geo: Geometry, refs: Refs) -> None:
        self.agent, self.screen, self.geo, self.refs = agent, screen, geo, refs
        self.last_action: int | None = None
        self.parked = False
        self.park_k = 0
        self.frame: Any = None

    def park(self) -> None:
        gx, gy, _, _ = r.game_region()
        pu, pv = PARK[self.park_k % 2]
        self.park_k += 1
        self.agent.move(gx + pu - 3, gy + pv - 3)
        time.sleep(0.05)
        self.agent.move(gx + pu, gy + pv)
        time.sleep(SETTLE_S)
        self.parked = True

    def look(self) -> Seen:
        if not self.parked:
            self.park()
        # a frame decoded after NOW: after the last action, and never the previous look's frame
        frame = np.ascontiguousarray(r.grab_after(self.screen, r.game_region(), r.ns())[..., :3])
        self.frame = frame
        return read_all(frame, self.geo, self.refs)

    def ui_click(self, xy: XY, what: str, inside: Box) -> int:
        x, y = xy
        bx, by, bw, bh = inside
        if not (bx <= x < bx + bw and by <= y < by + bh):
            raise r.Stop(f"learn_skill@1: a {what} click at {x},{y} outside its box {inside}")
        gx, gy, _, _ = r.game_region()
        self.agent.move(gx + x - 3, gy + y - 3)
        time.sleep(0.05)
        self.agent.move(gx + x, gy + y)
        time.sleep(0.15)
        t = r.ns()
        self.agent.click(gx + x, gy + y)  # a UI click: inside a box the readers placed
        self.last_action = t
        self.parked = False
        return t

    def chord(self, keys: Sequence[str]) -> int:
        r.activate_client(self.agent, self.screen)  # clicks the title bar: the cursor moves
        t = r.ns()
        self.agent.chord(*keys)
        self.last_action = t
        self.parked = False
        return t

    def now(self) -> int:
        return r.ns()

    def wait(self, seconds: float) -> None:
        time.sleep(seconds)


@dataclass
class Rig:
    agent: Any
    screen: Any
    io: LiveIo
    geo: Geometry
    keys: list[str]
    log: Any  # poring_env.demo.DemoLog
    restore: str
    restore_info: dict[str, Any]


def _snap(rig: Rig, name: str) -> Any:
    from poring_dataset.shards import encode_png
    from poring_env.demo import FrameRef

    img = r.grab_after(rig.screen, r.game_region(), r.ns())
    ref = rig.log.snapshot(name, encode_png(np.ascontiguousarray(img[:, :, :3])))
    return FrameRef(frame_id=-1, source="x11", t_capture_ns=r.ns(), ref=ref)


def _harness(rig: Rig, kind: str, note: str, t0: int, *, keys: Sequence[str] = (),
             points: Sequence[XY] = (), atype: str = "other") -> None:  # fmt: skip
    from poring_env.demo import Action, DemoRecord, Intended

    pts = [(float(x), float(y)) for x, y in points]
    rig.log.append(DemoRecord(
        session=rig.log.session, actor=HARNESS, t_mono_ns=t0, t_done_ns=r.ns(),
        cue=f"harness ({RULE}): {note}"[:300],
        action=Action(type=atype, keys=list(keys), points=pts,  # type: ignore[arg-type]
                      intended=Intended(kind=kind, note=note[:200])),
    ))  # fmt: skip


def harness_gm(rig: Rig, cmd: str) -> None:
    """One GM line, after the skill window's own states are closed (the UI gate is blind to
    them), through ro_agent.gm (the typing guard and the UI gate)."""
    harness_close(rig, "before a typed line")
    t0 = r.ns()
    r.gm(rig.agent, rig.screen, cmd)
    _harness(rig, "gm", cmd, t0, atype="gm")
    time.sleep(GM_SETTLE_S)


def harness_close(rig: Rig, why: str) -> list[dict[str, Any]]:
    def on_step(rec: dict[str, Any]) -> None:
        keys = ["+".join(rig.keys)] if rec["do"] == "chord" else []
        _harness(rig, "window", f"close_known {rec['do']} ({why})", rec["t"], keys=keys,
                 atype="menu_shortcut" if rec["do"] == "chord" else "other")  # fmt: skip

    return close_known(rig.io, rig.geo, rig.keys, on_step)


def start_state(rig: Rig) -> dict[str, Any]:
    """The window open: no modal, no tentative, the points 0, the level box EMPTY. A stale level
    digit (the client missed the server's reset) runs the restore's sync once; else r.Stop."""
    out: dict[str, Any] = {"synced": False}
    for attempt in range(2):
        s = stable(rig.io)
        if s is not None and not s.window:
            t0 = r.ns()
            rig.io.chord(rig.keys)
            _harness(rig, "window", "start state: open the skill window", t0,
                     keys=["+".join(rig.keys)], atype="menu_shortcut")  # fmt: skip
            time.sleep(OPEN_S)
            s = stable(rig.io)
        if s is None or not s.window:
            raise r.Stop(f"learn_skill@1 start state: the skill window did not open ({s})")
        out[f"seen_{attempt}"] = s.as_dict()
        if s.modal is not False or s.tentative is not False:
            raise r.Stop(f"learn_skill@1 start state: modal {s.modal}, tentative {s.tentative}")
        if s.points != START_POINTS:
            raise r.Stop(f"learn_skill@1 start state: points {s.points} ({s.points_reason}), "
                         f"want {START_POINTS}")  # fmt: skip
        if s.level_ink is False:
            harness_close(rig, "start state read")
            return out
        if s.level_ink is None or attempt == 1:
            raise r.Stop(f"learn_skill@1 start state: the level box shows {s.level_glyph} "
                         f"(ink {s.level_ink}) after {'the sync' if attempt else 'the restore'}: "
                         "the client is out of sync with the server")  # fmt: skip
        out["stale_level"] = s.level_glyph
        sync(rig)
        out["synced"] = True
    raise AssertionError("unreachable")


def sync(rig: Rig) -> None:
    """Make the client receive the skill list again (the restore's own mechanism)."""
    if rig.restore == "skreset":
        harness_gm(rig, SKRESET)  # pc_resetskill flag 1 sends the list (3.34)
    else:
        to_char_select_and_back(rig)


def to_char_select_and_back(rig: Rig) -> None:
    """charselect's route: the system menu, its character-select button (the L2 binding that is
    NOT measured yet: check_restore refuses the mode before any trial), character select, and
    back in by ro_agent.enter_game (a new map-server connection sends the full skill list)."""
    from poring_env import ui_anchors as ua
    from poring_skills.resolve import load_l2

    box = rig.restore_info.get("char_select")
    if box is None:
        raise Unbound(CHARSELECT_UNMEASURED)
    harness_close(rig, "before character select")
    reg = ua.default_registry(r.ROOT / "data" / "ui_anchors")
    t0 = r.ns()
    origin = None
    for _ in range(2):  # an open chat input takes the first Escape (measured 2026-10-10)
        rig.io.chord(load_l2(CLIENT)["shortcut"]["system_menu"]["keys"])
        time.sleep(OPEN_S)
        frame = np.ascontiguousarray(r.grab_after(rig.screen, r.game_region(), r.ns())[..., :3])
        origin = reg.locate(frame).get("game_option")
        if origin is not None:
            break
    if origin is None:
        raise r.Stop("learn_skill@1 charselect: the game option window did not open")
    btn = at(origin, box)
    rig.io.ui_click(centre(btn), "char_select", btn)
    _harness(rig, "window", "character select (game option)", t0, points=[centre(btn)])
    r.wait_state(rig.screen, ["char_select"], 20)
    # /health ticks at 1 Hz: right after character select it can still say green, and
    # ensure_window then skips the login window, so enter_game's Enter is refused once the
    # interlock turns red (2026-10-10 03:44, the first scored run). Wait for red first, and for
    # green again before any further input.
    if not wait_interlock(lambda s: s != "green", INTERLOCK_WAIT_S):
        raise r.Stop("learn_skill@1 charselect: the interlock stayed green at character select")
    t1 = r.ns()
    r.enter_game(rig.agent, rig.screen, "gm")
    _harness(rig, "login", "back into the game (enter_game)", t1, atype="login")
    if not wait_interlock(lambda s: s == "green", INTERLOCK_WAIT_S * 2):
        raise r.Stop("learn_skill@1 charselect: the interlock did not turn green after enter_game")
    time.sleep(GM_SETTLE_S)


def wait_interlock(ok: Callable[[str], bool], timeout: float,
                   health: Callable[[], dict[str, Any]] | None = None,
                   sleep: Callable[[float], None] = time.sleep) -> bool:  # fmt: skip
    """Poll /health's interlock state (1 Hz ticks) until ``ok(state)`` or ``timeout`` seconds."""
    get = health or r.backend_health
    end = time.monotonic() + timeout
    while True:
        state = str((get().get("environment") or {}).get("state"))
        if ok(state):
            return True
        if time.monotonic() >= end:
            return False
        sleep(0.5)


def restore_trial(rig: Rig) -> None:
    if rig.restore == "skreset":
        harness_gm(rig, SKRESET)
        harness_gm(rig, JOB_DOWN)
    else:
        harness_gm(rig, JOB_DOWN)  # the pinned server resets the skills (8 or fewer unspent < 9)
        to_char_select_and_back(rig)


def run_trial(rig: Rig, trial: dict[str, Any]) -> None:
    """One trial, filled into ``trial`` as it goes (a stop keeps what was done)."""
    import gm_state

    from poring_env.demo import Action, DemoRecord, Intended

    k, n = int(trial["k"]), int(trial["n"])
    trial["restore"] = rig.restore
    why = f"{RULE} trial {k}"
    trial["close_first"] = len(harness_close(rig, "trial start"))
    gm_dir = rig.log.dir / "gm_state"
    fixed = gm_state.ensure_fixed(rig.agent, rig.screen, why=why, out_dir=gm_dir)
    trial["fixed_before"] = _jsonable(fixed)
    trial["start"] = start_state(rig)
    harness_gm(rig, JOB_UP)
    trial["notices"] = gm_state.clear_notices(rig.agent, rig.screen, why=why)
    pre = _snap(rig, f"{k:03d}-before")
    trial["t_rule_start"] = r.ns()
    res = learn_skill(rig.io, rig.geo, rig.keys, n)
    trial["t_rule_end"] = r.ns()
    post = _snap(rig, f"{k:03d}-after")
    trial["rule"] = res
    rig.log.append(DemoRecord(
        session=rig.log.session, actor=f"rule:{RULE}", t_mono_ns=trial["t_rule_start"],
        t_done_ns=trial["t_rule_end"], frame=pre, frame_after=post, rule=RULE, scene="skill_window",
        cue=f"{RULE}: the skill window by its chord; the icon x N, each a new tentative; APPLY, "
            "the modal, OK; the points read P - N",
        action=Action(type="skill_up", points=[(float(c["xy"][0]), float(c["xy"][1]))
                                               for c in res["clicks"]],
                      keys=["+".join(rig.keys)] * len(res["chords"]),
                      intended=Intended(kind="skill", note=f"{SKILL} +{n} of {EXPECTED_POINTS}")),
        outcome={"status": "pending",  # type: ignore[arg-type]
                 "evidence": {"decline": res["decline"], "runtime": res["runtime"]}},
    ))  # fmt: skip
    if res["decline"] is not None:
        trial["close_after"] = len(harness_close(rig, f"after decline {res['decline']}"))
    restore_trial(rig)
    fixed = gm_state.ensure_fixed(rig.agent, rig.screen, why=why, out_dir=gm_dir)
    trial["fixed_after"] = _jsonable(fixed)
    trial["t_end"] = r.ns()


def ended_by(exc: BaseException) -> tuple[str, int, str]:
    """(how the run ended, the exit code, the reason): walk12.ended_by's mapping."""
    if isinstance(exc, KeyboardInterrupt):
        return "interrupted", 130, str(exc) or "interrupt"
    if isinstance(exc, SystemExit):  # ro_agent's Stop, Unbound, the harness's own SystemExit
        return "harness_stop", 3, str(exc) or type(exc).__name__
    return "exception", 4, f"{type(exc).__name__}: {exc}"


def _jsonable(x: Any) -> Any:
    return json.loads(json.dumps(x, default=str))


def run(n: int, seed: int, restore: str, skreset_allowed: bool, label: str) -> int:
    import record_session

    from poring_env.demo import DemoLog, new_session_id
    from poring_skills.resolve import load_l2

    geo = load_geometry()
    info = check_restore(restore, skreset_allowed, load_l2(CLIENT))
    refs = load_refs(r.ROOT / "data")
    keys = window_keys(geo.window)
    plan = n_plan(n, seed)
    sid = new_session_id(f"{label}-{restore}")
    log = DemoLog(sid)
    lock = record_session.read_lock(r.ROOT / "state")
    log.start(backend=str(lock.backend), lock_seq=lock.seq, server="lab-rathena", rule=RULE,
              account="gm", n=n, seed=seed, plan=plan, restore=restore,
              expected_points=EXPECTED_POINTS, geometry=repr(geo),
              templates=refs.meta)  # fmt: skip
    print(json.dumps({"session": sid, "rule": RULE, "n": n, "seed": seed, "plan": plan,
                      "restore": restore, "dir": str(log.dir)}), flush=True)  # fmt: skip
    t_first = r.ns()
    trials: list[dict[str, Any]] = []
    ended, code, why = "complete", 0, ""
    try:
        with r.session(f"rule:{RULE}") as (agent, screen):
            io = LiveIo(agent, screen, geo, refs)
            rig = Rig(agent, screen, io, geo, keys, log, restore, info)
            stops = 0
            for k, nk in enumerate(plan):
                trial: dict[str, Any] = {"k": k, "n": nk, "t_start": r.ns()}
                try:
                    run_trial(rig, trial)
                    stops = 0
                except r.Stop as exc:
                    stops += 1
                    trial.update(stop=str(exc)[:400], t_end=r.ns())
                    if io.frame is not None:
                        r.to_png(io.frame, log.dir / "stops" / f"{k:03d}.png")
                trials.append(trial)
                rule = trial.get("rule") or {}
                print(json.dumps({"k": k, "n": nk, "decline": rule.get("decline"),
                                  "runtime": rule.get("runtime"), "stop": trial.get("stop")},
                                 default=str), flush=True)  # fmt: skip
                if stops >= MAX_STOPS:
                    ended, code, why = "harness_stop", 3, f"{MAX_STOPS} consecutive harness stops"
                    break
                time.sleep(BETWEEN_S)
    except BaseException as exc:  # noqa: BLE001 -- every way out finishes the session
        ended, code, why = ended_by(exc)
    finally:
        (log.dir / "trials.json").write_text(json.dumps(trials, default=str))
        packets: dict[str, Any]
        try:
            events, anchor = record_session.write_packets(log.dir, t_first, r.ns())
            packets = {"packet_events": len(events), "packet_anchor": anchor}
        except Exception as exc:  # noqa: BLE001 -- the end is written whatever the packets do
            packets = {"packets_error": f"{type(exc).__name__}: {exc}"[:300]}
        log.finish(trials=len(trials), ended=ended, reason=why[:300], exit_code=code, **packets)
    print(json.dumps({"session": sid, "trials": len(trials), "ended": ended, "reason": why[:300],
                      "dir": str(log.dir)}), flush=True)  # fmt: skip
    return code


# --- offline: the templates and the banked-frame proof --------------------------------------------

# which banked frame each template comes from (3.34's looks, 2026-10-09)
CUT_FROM = {"modal": "look4-applied", "nomodal": "look3-click1-away", "label": "look1-skillwin",
            "level_one": "look5-confirmed"}  # fmt: skip

# expected per banked frame (3.34); None = not judged on that frame (the cursor sits on the icon
# and its sprite covers the level box: the live rule parks it first)
EXPECT: dict[str, dict[str, Any]] = {
    "look1-after-joblevelup": {"window": False},
    "look1-skillwin": {"window": True, "tentative": False, "modal": False, "points": 9,
                       "level_ink": False},
    "look2-hover": {"window": True, "tentative": False, "modal": False, "points": 9},
    "look2-hover-2s": {"window": True, "tentative": False, "modal": False, "points": 9},
    "look3-click1": {"window": True, "tentative": True, "modal": False, "points": None,
                     "points_reason": "tentative"},
    "look3-click1-away": {"window": True, "tentative": True, "modal": False, "points": None,
                          "points_reason": "tentative", "level_ink": False},
    "look4-applied": {"window": True, "tentative": True, "modal": True, "points": None,
                      "points_reason": "tentative", "level_ink": False},
    "look5-confirmed": {"window": True, "tentative": False, "modal": False, "points": 8,
                        "level_ink": True, "level_glyph": "1"},
    "look6-skillwin-after-reset": {"window": True, "tentative": False, "modal": False,
                                   "points": 0, "level_ink": True, "level_glyph": "1"},
    "look6-end": {"window": False},
}  # fmt: skip


def banked_frame(path: Path) -> Any:
    from PIL import Image

    img = np.asarray(Image.open(path).convert("RGB"))[..., ::-1]
    x, y, w, h = BANKED_REGION
    if img.shape[0] < y + h or img.shape[1] < x + w:
        raise SystemExit(f"{path}: {img.shape[1]}x{img.shape[0]} is not the frozen desktop")
    return np.ascontiguousarray(img[y : y + h, x : x + w])


def cut(banked: Path, data: Path) -> dict[str, Any]:
    """The run-time templates from the banked looks (client pixels: data/, never committed)."""
    from poring_env import ui_anchors as ua
    from poring_env import weight as wt

    geo = load_geometry()
    reg = ua.default_registry(data / "ui_anchors")
    frames = {k: banked_frame(banked / f"{v}.png") for k, v in CUT_FROM.items()}
    home = ua.CAPTURE_ORIGINS["skills"]
    for k, f in frames.items():
        got = reg.locate(f).get("skills")
        if got != home:
            raise SystemExit(f"{CUT_FROM[k]}: the skill window is at {got}, not its home {home}")
    on = to_gray(crop(frames["modal"], geo.modal))
    off = to_gray(crop(frames["nomodal"], geo.modal))
    mask = np.abs(on - off) > MASK_DIFF
    glyphs = wt.load_weight_glyphs(data / "ui_anchors" / "weight_glyphs.npz")
    lx, ly, lw, lh = at(home, geo.label)
    bx, by, bw, bh = at(home, geo.band)
    x0, y0 = min(lx, bx), min(ly, by)
    line = to_gray(frames["label"][y0 : max(ly + lh, by + bh), x0 : max(lx + lw, bx + bw)])
    paper = float(np.median(line))
    prob = np.clip((paper - line) / (paper - glyphs.ink), 0, 1)
    label = prob[ly - y0 : ly - y0 + lh, lx - x0 : lx - x0 + lw]
    lvl = to_gray(crop(frames["level_one"], at(home, geo.level))) < DARK
    out_dir = data / TEMPLATE_SUBDIR
    out_dir.mkdir(parents=True, exist_ok=True)
    for name, arr in (
        ("modal", on),
        ("nomodal", off),
        ("modal_mask", mask.astype(np.float32)),
        ("label", label.astype(np.float32)),
        ("level_one", lvl.astype(np.float32)),
    ):
        np.save(out_dir / f"{name}.npy", np.asarray(arr, np.float32))
    meta = {"cut_from": {k: f"{v}.png" for k, v in CUT_FROM.items()},
            "sha256": {v: hashlib.sha256((banked / f"{v}.png").read_bytes()).hexdigest()[:16]
                       for v in CUT_FROM.values()},
            "modal_mask_px": int(mask.sum()), "label_mass": float((label**2).sum()),
            "level_one_px": int(lvl.sum()), "geometry": repr(geo),
            "cut_at": time.strftime("%Y-%m-%dT%H:%M:%S%z")}  # fmt: skip
    (out_dir / "meta.json").write_text(json.dumps(meta, indent=1))
    return {"dir": str(out_dir), **meta}


def prove(banked: Path, data: Path) -> dict[str, Any]:
    """Every reader on every banked look frame; each expectation (EXPECT) must hold."""
    geo = load_geometry()
    refs = load_refs(data)
    rows: list[dict[str, Any]] = []
    for name, want in EXPECT.items():
        path = banked / f"{name}.png"
        if not path.exists():
            rows.append({"frame": name, "pass": False, "error": "missing"})
            continue
        seen = read_all(banked_frame(path), geo, refs).as_dict()
        got = {k: seen[k] for k in want}
        held_out = sorted(k for k, v in CUT_FROM.items() if v == name)
        rows.append({"frame": name, "expected": want, "read": got, "pass": got == want,
                     "templates_cut_here": held_out, "why": seen["why"],
                     "points_reason": seen["points_reason"],
                     "level_glyph": seen["level_glyph"]})  # fmt: skip
    return {"pass": all(x["pass"] for x in rows), "frames": len(rows), "rows": rows,
            "templates": refs.meta.get("cut_from")}  # fmt: skip


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)  # fmt: skip
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("cut", "prove"):
        sp = sub.add_parser(name)
        sp.add_argument("--banked", type=Path, default=BANKED)
        sp.add_argument("--data", type=Path, default=ROOT / "data")
    rn = sub.add_parser("run")
    rn.add_argument("--n", type=int, required=True)
    rn.add_argument("--seed", type=int, required=True)
    rn.add_argument("--restore", choices=("skreset", "charselect"), required=True)
    rn.add_argument(
        "--skreset-allowed",
        action="store_true",
        help="only after Batt's decision to add @skreset to group 20",
    )
    rn.add_argument("--label", default="learn-skill1")
    a = ap.parse_args()
    if a.cmd == "cut":
        print(json.dumps(cut(a.banked, a.data), indent=1))
        return 0
    if a.cmd == "prove":
        res = prove(a.banked, a.data)
        for row in res["rows"]:
            print(json.dumps(row, default=str))
        print(json.dumps({"pass": res["pass"], "frames": res["frames"],
                          "templates": res["templates"]}))  # fmt: skip
        return 0 if res["pass"] else 1
    return run(a.n, a.seed, a.restore, a.skreset_allowed, a.label)


if __name__ == "__main__":
    sys.exit(main())
