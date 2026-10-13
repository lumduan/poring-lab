"""The NPC dialog and menu windows from pixels (talk@1 T2, docs/demonstrations.md 3.30).

An NPC's script opens two separate, fixed-size, drag-movable client windows (ADR-0011 layer 1):
  * ``npc_dialog``: the script's text (``mes``), with ONE button at its bottom right: the client's
    NEXT (the server's ``npc_wait``) or CLOSE (``npc_close``), or no button (a menu is up, or the
    server has not answered yet);
  * ``npc_menu``: the script's ``select`` options, 4 visible rows on a 16 px pitch that SCROLL
    (a scrollbar with two arrows), the selected row on a light-blue band, and two buttons, OK and
    Cancel. Their labels are the client's locale: they are found by IMAGE, never by text.

Both are found anywhere in the client area by a template of the WHOLE window under a mask that
keeps only what never changes (the frame, the white margins, the blank edges of the text area); the
text area, the list, the buttons and the corners are masked out, so the text and the locale's
button labels never decide where a window is (ADR-0012). Elements are offsets inside the window
(layer 2). The button images themselves (NEXT, CLOSE, OK, Cancel, the scroll arrows) are compared
at their fixed offsets: they include the locale's labels, which is fine -- they are cut from the
lab's own client and only ever compared as pixels (no text is stored or read).

Templates are cut LOCALLY from the lab's frames, labelled by packet truth (scripts/talk_calibrate.py
``cut``), into ``data/ui_anchors/npc_dialog/`` (client pixels: gitignored, never committed). This
module only reads frames and fails CLOSED: a window whose best match falls between the accept and
the absent distances, a button that is none of the known images (e.g. under the mouse: the client
highlights it), a row background that is neither the plain nor the highlight colour (covered), a
half-seen scrollbar -- all give ``ok=False`` with a reason, never a guess. A caller acts only on an
``ok`` state, and on the SAME state on two fresh frames (``same_state``).

Measured 2026-10-09 on banked RDP frames (the Garnet positive case of 2026-10-08, 1280x720 client
area; the dialog's origin was (201, 101), the menu's (201, 301)): see ``Geometry``.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal

import numpy as np
import numpy.typing as npt

from poring_env.ui_anchors import ELEMENTS, WINDOWS, Gray, to_gray

Box = tuple[int, int, int, int]  # x, y, w, h
Button = Literal["next", "close"]
Verdict = Literal["present", "absent", "uncertain"]

DIALOG, MENU = "npc_dialog", "npc_menu"
NEXT, CLOSE, BLANK = "npc_dialog_next", "npc_dialog_close", "npc_dialog_blank"
# OPTIONAL (Batt 2026-10-13, decision 2): the NEXT button in its blue HOVER / FOCUS look
# (npc-click@1's click arm stopped on it, 3.32a). It reads as NEXT; without its file the reader
# is unchanged.
NEXT_HI = "npc_dialog_next_hi"
# OPTIONAL (Batt 2026-10-13, after npc-click@1's second stop): the CLOSE button in the same sticky
# highlight (a decline's NEXT clicks leave the cursor's hover on the button's place; the last page's
# CLOSE then shows blue). It reads as CLOSE; without its file the reader is unchanged.
CLOSE_HI = "npc_dialog_close_hi"
# Each highlighted look -> the button it shows: two looks of one button never refuse each other.
SAME_BUTTON = {NEXT_HI: NEXT, CLOSE_HI: CLOSE}
OK, CANCEL = "npc_menu_ok", "npc_menu_cancel"
UP, DOWN = "npc_menu_up", "npc_menu_down"
WINDOW_NAMES = (DIALOG, MENU)
BUTTON_NAMES = (NEXT, NEXT_HI, CLOSE, CLOSE_HI, BLANK, OK, CANCEL)
ARROW_NAMES = (UP, DOWN)
# Without these nothing is read; CLOSE may be missing (then a CLOSE button is "unknown": closed).
REQUIRED = (DIALOG, MENU, NEXT, BLANK, OK, CANCEL, UP, DOWN)
TEMPLATE_DIR = Path("data/ui_anchors/npc_dialog")
PARAMS_FILE = "params.json"
FORMAT_VERSION = 1

# The skin's flat colours (RGB, measured 2026-10-09): a row's plain background, the selected
# row's band, the scrollbar's empty track. COLOUR_TOL absorbs the RDP codec's refinement.
PLAIN_RGB = (247, 247, 247)
HIGHLIGHT_RGB = (206, 222, 255)
TRACK_RGB = (214, 222, 222)
COLOUR_TOL = 16
ROW_BG_SHARE = 0.9  # this share of a row's margin samples must be ONE background colour


def _el(name: str) -> Box:
    box = ELEMENTS[name].box
    if box is None:
        raise ValueError(f"{name} has no fixed box")
    return box


@dataclass(frozen=True, slots=True)
class Geometry:
    """Offsets inside the two windows (x, y, w, h), from the ADR-0011 anchor map
    (``poring_env.ui_anchors``: measured 2026-10-09 on RDP frames), plus what only this reader
    needs."""

    dialog_size: tuple[int, int] = WINDOWS[DIALOG].size
    dialog_text: Box = _el("npc_dialog_text")  # the grey text area; ink starts at (12, 15)
    dialog_ink: Box = (12, 14, 257, 135)  # where the text may draw: masked out of the template
    dialog_button: Box = _el(NEXT)  # NEXT / CLOSE, the same place
    menu_size: tuple[int, int] = WINDOWS[MENU].size
    menu_list: Box = (11, 25, 256, 65)  # the rows and the scrollbar
    row_top: int = _el("npc_menu_row_1")[1]
    row_pitch: int = _el("npc_menu_row_2")[1] - _el("npc_menu_row_1")[1]
    row_h: int = _el("npc_menu_row_1")[3]  # the highlight band covers the first 15
    rows: int = 4
    row_text: tuple[int, int] = (_el("npc_menu_row_1")[0], _el("npc_menu_row_1")[2])  # dx, w
    row_margin: tuple[int, int] = (11, 3)  # dx, w: always background (ink starts at dx 14)
    up_arrow: Box = _el(UP)
    track: Box = _el("npc_menu_track")
    track_col: int = 260  # the track's middle column (dx)
    down_arrow: Box = _el(DOWN)
    ok_button: Box = _el(OK)
    cancel_button: Box = _el(CANCEL)
    corner: int = 6  # the rounded corners show the scene: masked out

    def size(self, window: str) -> tuple[int, int]:
        return self.dialog_size if window == DIALOG else self.menu_size

    def row_box(self, k: int) -> Box:
        dx, w = self.row_text
        return (dx, self.row_top + k * self.row_pitch, w, self.row_h)

    def element_box(self, name: str) -> Box:
        return {
            NEXT: self.dialog_button, NEXT_HI: self.dialog_button, CLOSE: self.dialog_button,
            CLOSE_HI: self.dialog_button, BLANK: self.dialog_button,
            OK: self.ok_button, CANCEL: self.cancel_button, UP: self.up_arrow,
            DOWN: self.down_arrow,
        }[name]  # fmt: skip


GEOMETRY = Geometry()


def structural_mask(window: str, g: Geometry = GEOMETRY) -> Gray:
    """1 where a window's template may be compared: everything but the text / list area, the
    buttons and the corners (ADR-0012: the text and the locale's labels never locate a window)."""
    w, h = g.size(window)
    m = np.ones((h, w), np.float32)
    holes = ([g.dialog_ink, g.dialog_button] if window == DIALOG
             else [g.menu_list, g.ok_button, g.cancel_button])  # fmt: skip
    for x, y, bw, bh in holes:
        m[y : y + bh, x : x + bw] = 0
    c = g.corner
    for ys in (slice(0, c), slice(h - c, h)):
        for xs in (slice(0, c), slice(w - c, w)):
            m[ys, xs] = 0
    return m


def edge_mask(window: str, g: Geometry = GEOMETRY) -> Gray:
    """1 on the window's four grey border lines (2 px inside its rect), corners excluded."""
    w, h = g.size(window)
    m = np.zeros((h, w), np.float32)
    c = g.corner
    m[2, c : w - c] = 1
    m[h - 3, c : w - c] = 1
    m[c : h - c, 2] = 1
    m[c : h - c, w - 3] = 1
    return m


@dataclass(frozen=True, slots=True)
class Params:
    """Acceptance rules (scripts/talk_calibrate.py fits them).

    A window is judged at its best place by the share of its masked pixels that differ from the
    template by more than ``pixel_tol`` grey levels (the mean difference does not separate: the
    menu's white margins sit only 8 levels from the dialog's grey text area). Buttons and arrows
    are judged by their mean abs grey difference at their fixed place."""

    pixel_tol: float = 6.0  # a window pixel this far from its template "differs"
    window_accept: float = 0.03  # a window matches with at most this share differing ...
    window_absent: float = 0.25  # ... is absent from this share up; in between: uncertain
    edge_accept: float = 0.05  # the same share on the four border LINES alone (``edge_mask``) ...
    edge_absent: float = 0.3  # ... absent from here: another white window (the hotbar) differs
    #                           from ours in 24 % of the mask but in 55-62 % of these lines
    # The border lines tolerate a LOCALLY UNIFORM shade offset of at most this many grey levels,
    # taken as the running median of (frame - template) over ``edge_offset_run`` px of the line
    # (2026-10-13: an RDP codec tile shifted part of the dialog's bottom line by 7 levels, just over
    # pixel_tol, and the dialog read "uncertain"). A structural difference (another window's white,
    # +57 on these lines) is far beyond it and still differs.
    edge_offset_max: float = 12.0
    edge_offset_run: int = 15
    button_accept: float = 6.0  # a button image matches at most this ...
    button_margin: float = 4.0  # ... and beats the other images of its place by this
    arrow_accept: float = 8.0  # a scroll arrow (masked to its own pixels) matches at most this

    def __post_init__(self) -> None:
        if not 0 < self.window_accept < self.window_absent <= 1:
            raise ValueError("need 0 < window_accept < window_absent <= 1")
        if not 0 < self.edge_accept < self.edge_absent <= 1:
            raise ValueError("need 0 < edge_accept < edge_absent <= 1")


@dataclass
class DialogTemplates:
    """The cut images (grey), their masks (1 = compare) and the rules."""

    images: dict[str, Gray]
    masks: dict[str, Gray] = field(default_factory=dict)
    params: Params = field(default_factory=Params)
    geometry: Geometry = GEOMETRY
    meta: dict[str, Any] = field(default_factory=dict)

    @property
    def missing(self) -> tuple[str, ...]:
        return tuple(n for n in REQUIRED if n not in self.images)

    def save(self, directory: Path) -> None:
        directory.mkdir(parents=True, exist_ok=True)
        for name, img in self.images.items():
            np.save(directory / f"{name}.npy", img.astype(np.float32))
        for name, m in self.masks.items():
            np.save(directory / f"{name}_mask.npy", m.astype(np.float32))
        doc = {"version": FORMAT_VERSION, "params": asdict(self.params),
               "geometry": asdict(self.geometry), "meta": self.meta}  # fmt: skip
        (directory / PARAMS_FILE).write_text(json.dumps(doc, indent=1, sort_keys=True) + "\n")


def load_templates(directory: Path = TEMPLATE_DIR) -> DialogTemplates:
    """The cut templates (plain arrays, never unpickled). Raises when the params file is missing
    or of another format; a missing image is reported by ``missing`` (and refused by ``state``)."""
    doc = json.loads((directory / PARAMS_FILE).read_text())
    if int(doc.get("version", -1)) != FORMAT_VERSION:
        raise ValueError(f"{directory}: format {doc.get('version')}, need {FORMAT_VERSION}")
    stored = {k: tuple(v) if isinstance(v, list) else v for k, v in doc["geometry"].items()}
    geometry = GEOMETRY
    if stored != {k: v for k, v in asdict(GEOMETRY).items()}:
        raise ValueError(f"{directory}: cut with another geometry than this reader's")
    images: dict[str, Gray] = {}
    masks: dict[str, Gray] = {}
    for name in (*WINDOW_NAMES, *BUTTON_NAMES, *ARROW_NAMES):
        path = directory / f"{name}.npy"
        if path.exists():
            images[name] = np.asarray(np.load(path, allow_pickle=False), np.float32)
        mpath = directory / f"{name}_mask.npy"
        if mpath.exists():
            masks[name] = np.asarray(np.load(mpath, allow_pickle=False), np.float32)
    return DialogTemplates(images, masks, Params(**doc["params"]), geometry, doc.get("meta", {}))


# --- the state ----------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Find:
    """One window's best place in the frame, and how much of its mask differs there."""

    name: str
    origin: tuple[int, int] | None  # only when present
    at: tuple[int, int] | None  # the best place searched (present or not)
    distance: float  # mean abs grey difference over the mask there
    mismatch: float  # share of the mask's pixels differing by more than pixel_tol
    edge: float  # the same share on the window's four border lines
    verdict: Verdict


@dataclass(frozen=True, slots=True)
class DialogView:
    rect: Box  # client-area pixels
    button: Button | None
    button_rect: Box
    distance: float
    button_distances: Mapping[str, float]


@dataclass(frozen=True, slots=True)
class MenuView:
    rect: Box
    rows: tuple[Box, ...]  # each row's text part (client-area pixels), top to bottom
    backgrounds: tuple[str, ...]  # "plain" | "highlight", per row
    highlight_row: int | None  # 0-based; None: the selected option is scrolled out of view
    scrollbar: bool
    can_scroll_up: bool
    can_scroll_down: bool
    thumb: tuple[int, int] | None  # [top, bottom) in track rows
    ok_rect: Box
    cancel_rect: Box
    up_rect: Box
    down_rect: Box
    distance: float


@dataclass(frozen=True, slots=True)
class NpcUiState:
    """``ok``: every part was read with certainty. Only then are dialog / menu meaningful (None =
    that window is absent). Otherwise ``reason`` says what could not be read."""

    ok: bool
    reason: str
    confidence: float
    dialog: DialogView | None = None
    menu: MenuView | None = None
    finds: tuple[Find, ...] = ()

    @property
    def gone(self) -> bool:
        """Both windows certainly absent."""
        return self.ok and self.dialog is None and self.menu is None

    def signature(self) -> tuple[Any, ...]:
        """What two frames must agree on to call the state stable."""
        d = None if self.dialog is None else (self.dialog.rect, self.dialog.button)
        m = None if self.menu is None else (
            self.menu.rect, self.menu.highlight_row, self.menu.scrollbar,
            self.menu.can_scroll_up, self.menu.can_scroll_down, self.menu.thumb,
        )  # fmt: skip
        return (self.ok, d, m)

    def summary(self) -> dict[str, Any]:
        """A JSON-able digest for logs."""
        out: dict[str, Any] = {"ok": self.ok, "reason": self.reason,
                               "confidence": round(self.confidence, 3)}  # fmt: skip
        if self.dialog is not None:
            out["dialog"] = {"rect": list(self.dialog.rect), "button": self.dialog.button}
        if self.menu is not None:
            m = self.menu
            out["menu"] = {"rect": list(m.rect), "highlight_row": m.highlight_row,
                           "scrollbar": m.scrollbar, "up": m.can_scroll_up,
                           "down": m.can_scroll_down}  # fmt: skip
        out["finds"] = {f.name: [f.verdict, round(f.mismatch, 4), round(f.edge, 4)]
                        for f in self.finds}  # fmt: skip
        return out


def same_state(a: NpcUiState, b: NpcUiState) -> bool:
    return a.ok and b.ok and a.signature() == b.signature()


def _abs(origin: tuple[int, int], box: Box) -> Box:
    return (origin[0] + box[0], origin[1] + box[1], box[2], box[3])


def _crop(gray: Gray, box: Box) -> Gray | None:
    x, y, w, h = box
    if x < 0 or y < 0 or y + h > gray.shape[0] or x + w > gray.shape[1]:
        return None
    return gray[y : y + h, x : x + w]


def image_distance(crop: Gray, image: Gray, mask: Gray | None = None) -> float:
    """Mean abs grey difference (over the mask's pixels when given)."""
    if crop.shape != image.shape:
        return float("inf")
    d = np.abs(crop - image)
    if mask is None:
        return float(d.mean())
    s = float(mask.sum())
    return float((d * mask).sum() / s) if s > 0 else float("inf")


COARSE = 4  # the search runs on 4x4-pooled pixels, then refines the best few places at full size
CANDIDATES = 5
REFINE = 3  # +-px around each coarse place, at full size


def _pool(a: Gray, f: int) -> Gray:
    h, w = (a.shape[0] // f) * f, (a.shape[1] // f) * f
    return np.asarray(a[:h, :w].reshape(h // f, f, w // f, f).mean(axis=(1, 3)), np.float32)


def _corr(image: Gray, kernel: Gray) -> npt.NDArray[np.float64]:
    """Valid-mode cross-correlation by FFT (as ui_anchors' matcher)."""
    ih, iw = image.shape
    th, tw = kernel.shape
    shape = (ih + th - 1, iw + tw - 1)
    spectrum = np.fft.rfft2(image, shape) * np.fft.rfft2(kernel[::-1, ::-1], shape)
    full = np.fft.irfft2(spectrum, shape)
    return np.asarray(full[th - 1 : ih, tw - 1 : iw], np.float64)


def coarse_places(gray: Gray, tmpl: Gray, mask: Gray, k: int = CANDIDATES,
                  f: int = COARSE) -> list[tuple[int, int]]:  # fmt: skip
    """The k best places (full-size pixels) of a masked SSD on pooled pixels, >= 3 cells apart."""
    img, t, m = _pool(gray, f), _pool(tmpl, f), _pool(mask, f)
    if t.shape[0] > img.shape[0] or t.shape[1] > img.shape[1] or float(m.sum()) == 0:
        return []
    ssd = _corr(img * img, m) - 2 * _corr(img, m * t) + float((m * t * t).sum())
    order = np.argsort(ssd, axis=None)
    out: list[tuple[int, int]] = []
    for idx in order[: 50 * k]:
        y, x = np.unravel_index(int(idx), ssd.shape)
        if all(abs(int(x) - ox) > 2 or abs(int(y) - oy) > 2 for ox, oy in out):
            out.append((int(x), int(y)))
            if len(out) == k:
                break
    return [(x * f, y * f) for x, y in out]


def score_at(gray: Gray, tmpl: Gray, mask: Gray, origin: tuple[int, int],
             pixel_tol: float) -> tuple[float, float] | None:  # fmt: skip
    """(mean abs difference, mismatch share) of the template at ``origin``; None off the frame."""
    crop = _crop(gray, (origin[0], origin[1], tmpl.shape[1], tmpl.shape[0]))
    if crop is None:
        return None
    s = float(mask.sum())
    d = np.abs(crop - tmpl) * mask
    return float(d.sum() / s), float(((d > pixel_tol) * mask).sum() / s)


def edge_share(gray: Gray, tmpl: Gray, origin: tuple[int, int], name: str, p: Params,
               g: Geometry = GEOMETRY) -> float | None:  # fmt: skip
    """The share of the four border lines' pixels (``edge_mask``) that differ from the template by
    more than ``pixel_tol`` AFTER removing a locally uniform offset (the running median of the
    signed difference over ``edge_offset_run`` px, clipped to +-``edge_offset_max``); None off the
    frame."""
    crop = _crop(gray, (origin[0], origin[1], tmpl.shape[1], tmpl.shape[0]))
    if crop is None:
        return None
    w, h = g.size(name)
    c = g.corner
    ax, ay = slice(c, w - c), slice(c, h - c)
    lines = [(crop[2, ax], tmpl[2, ax]), (crop[h - 3, ax], tmpl[h - 3, ax]),
             (crop[ay, 2], tmpl[ay, 2]), (crop[ay, w - 3], tmpl[ay, w - 3])]  # fmt: skip
    k = max(1, int(p.edge_offset_run)) | 1  # odd
    differ = total = 0
    for got, want in lines:
        d = np.asarray(got, np.float32) - np.asarray(want, np.float32)
        pad = np.pad(d, k // 2, mode="edge")
        local = np.median(np.lib.stride_tricks.sliding_window_view(pad, k), axis=-1)
        local = np.clip(local, -p.edge_offset_max, p.edge_offset_max)
        differ += int((np.abs(d - local) > p.pixel_tol).sum())
        total += d.size
    return differ / total


def find_window(gray: Gray, name: str, t: DialogTemplates,
                hint: tuple[int, int] | None = None) -> Find:  # fmt: skip
    """The window's best place: a ``hint`` (where it was) first, else the coarse search's best
    places, each refined +-REFINE px at full size; the least mismatching wins."""
    tmpl, p = t.images[name], t.params
    mask = t.masks.get(name)
    if mask is None:
        mask = structural_mask(name, t.geometry)
    best: tuple[float, float, tuple[int, int]] | None = None

    def refine(places: Sequence[tuple[int, int]]) -> None:
        nonlocal best
        for cx, cy in places:
            for dy in range(-REFINE, REFINE + 1):
                for dx in range(-REFINE, REFINE + 1):
                    got = score_at(gray, tmpl, mask, (cx + dx, cy + dy), p.pixel_tol)
                    if got is not None and (best is None or (got[1], got[0]) < best[:2]):
                        best = (got[1], got[0], (cx + dx, cy + dy))

    if hint is not None:
        refine([hint])
    if best is None or best[0] > p.window_accept:
        refine(coarse_places(gray, tmpl, mask))
    if best is None:
        return Find(name, None, None, float("inf"), 1.0, 1.0, "absent")
    mismatch, distance, at = best
    e = edge_share(gray, tmpl, at, name, p, t.geometry)
    edge = 1.0 if e is None else e
    verdict: Verdict
    if mismatch <= p.window_accept and edge <= p.edge_accept:
        verdict = "present"
    elif mismatch >= p.window_absent or edge >= p.edge_absent:
        verdict = "absent"
    else:
        verdict = "uncertain"
    return Find(name, at if verdict == "present" else None, at, distance, mismatch, edge, verdict)


def find_confidence(f: Find, p: Params) -> float:
    """1 for a perfect match or a far miss; 0.5 at a threshold."""
    if f.verdict == "present":
        return 1.0 - 0.5 * max(f.mismatch / p.window_accept, f.edge / p.edge_accept)
    if f.verdict == "absent":
        return min(1.0, 0.5 * max(f.mismatch / p.window_absent, f.edge / p.edge_absent))
    return 0.0


def classify_button(
    crop: Gray | None,
    candidates: Sequence[str],
    t: DialogTemplates,
    same: dict[str, str] | None = None,
) -> tuple[str | None, dict[str, float]]:
    """The one candidate image within button_accept that beats every candidate of ANOTHER
    button by button_margin; None otherwise. ``same`` maps a look to the button it shows (e.g.
    NEXT_HI -> NEXT): two looks of one button never refuse each other. Returns (name or None,
    distances)."""
    same = same or {}
    dist = {n: (image_distance(crop, t.images[n]) if crop is not None else float("inf"))
            for n in candidates if n in t.images}  # fmt: skip
    if not dist:
        return None, dist
    ranked = sorted(dist.items(), key=lambda kv: kv[1])
    best, d1 = ranked[0]
    group = same.get(best, best)
    d2 = min((d for n, d in ranked[1:] if same.get(n, n) != group), default=float("inf"))
    p = t.params
    if d1 <= p.button_accept and d2 - d1 >= p.button_margin:
        return best, dist
    return None, dist


def colour_is(bgr: npt.NDArray[np.uint8], rgb: tuple[int, int, int],
              tol: int = COLOUR_TOL) -> npt.NDArray[np.bool_]:  # fmt: skip
    """Per pixel: within ``tol`` of ``rgb`` in every channel (``bgr`` is BGR)."""
    ref = np.array(rgb[::-1], dtype=np.int16)
    out: npt.NDArray[np.bool_] = (np.abs(bgr[..., :3].astype(np.int16) - ref) <= tol).all(axis=-1)
    return out


def row_background(bgr: npt.NDArray[np.uint8], origin: tuple[int, int], k: int,
                   g: Geometry = GEOMETRY) -> str | None:  # fmt: skip
    """ "plain" | "highlight" from the row's left margin (always background), None if neither."""
    dx, w = g.row_margin
    y = origin[1] + g.row_top + k * g.row_pitch
    x = origin[0] + dx
    sample = bgr[y : y + g.row_h - 1, x : x + w]
    if sample.size == 0:
        return None
    for name, rgb in (("plain", PLAIN_RGB), ("highlight", HIGHLIGHT_RGB)):
        if float(colour_is(sample, rgb).mean()) >= ROW_BG_SHARE:
            return name
    return None


Scroll = tuple[str, bool, bool, tuple[int, int] | None]


def read_scrollbar(bgr: npt.NDArray[np.uint8], gray: Gray, origin: tuple[int, int],
                   t: DialogTemplates) -> Scroll:  # fmt: skip
    """(why, can_scroll_up, can_scroll_down, thumb). why: "none" (no scrollbar), "ok", or the
    reason it could not be read."""
    g, p = t.geometry, t.params
    found = []
    for name in ARROW_NAMES:
        crop = _crop(gray, _abs(origin, g.element_box(name)))
        d = (image_distance(crop, t.images[name], t.masks.get(name)) if crop is not None
             else float("inf"))  # fmt: skip
        found.append(d <= p.arrow_accept)
    if not any(found):
        return "none", False, False, None
    if not all(found):
        return "scrollbar_partial", False, False, None
    x = origin[0] + g.track_col
    y0 = origin[1] + g.track[1]
    col = bgr[y0 : y0 + g.track[3], x : x + 1]
    if col.shape[0] != g.track[3]:
        return "scrollbar_outside", False, False, None
    is_track = colour_is(col, TRACK_RGB)[:, 0]
    thumb_rows = np.flatnonzero(~is_track)
    if thumb_rows.size < 3:
        return "scrollbar_unread", False, False, None
    top, bottom = int(thumb_rows[0]), int(thumb_rows[-1]) + 1
    if bottom - top != thumb_rows.size:  # the thumb is ONE run
        return "scrollbar_unread", False, False, None
    return "ok", top > 0, bottom < g.track[3], (top, bottom)


def state(
    frame_bgr: npt.NDArray[np.uint8],
    t: DialogTemplates,
    hints: Mapping[str, tuple[int, int]] | None = None,
) -> NpcUiState:  # noqa: PLR0911
    """The dialog and menu windows on one frame (the 1280x720 client area, BGR or BGRA).
    ``hints``: where the windows were last seen (tried first; the search runs anyway when a hint
    does not match, so an absent verdict is always a full search)."""
    if t.missing:
        return NpcUiState(False, "no_templates: " + ",".join(t.missing), 0.0)
    bgr = np.ascontiguousarray(frame_bgr[..., :3])
    gray = to_gray(bgr)
    g, p = t.geometry, t.params
    finds = tuple(find_window(gray, n, t, (hints or {}).get(n)) for n in WINDOW_NAMES)
    unsure = [f.name for f in finds if f.verdict == "uncertain"]
    if unsure:
        return NpcUiState(False, f"{unsure[0]}_uncertain", 0.0, finds=finds)
    conf = [find_confidence(f, p) for f in finds]
    dialog: DialogView | None = None
    menu: MenuView | None = None
    fd, fm = finds
    if fd.origin is not None:
        brect = _abs(fd.origin, g.dialog_button)
        label, dist = classify_button(_crop(gray, brect), (NEXT, NEXT_HI, CLOSE, CLOSE_HI, BLANK),
                                      t, same=SAME_BUTTON)  # fmt: skip
        if label is None:
            return NpcUiState(False, "button_unknown", 0.0, finds=finds)
        conf.append(1.0 - dist[label] / (2 * p.button_accept))
        shown = SAME_BUTTON.get(label, label)
        button: Button | None = "next" if shown == NEXT else "close" if shown == CLOSE else None
        w, h = g.dialog_size
        dialog = DialogView((*fd.origin, w, h), button, brect, fd.distance, dist)
    if fm.origin is not None:
        o = fm.origin
        for name in (OK, CANCEL):
            crop = _crop(gray, _abs(o, g.element_box(name)))
            d = image_distance(crop, t.images[name]) if crop is not None else float("inf")
            if d > p.button_accept:
                return NpcUiState(False, "menu_buttons_unknown", 0.0, dialog, None, finds)
            conf.append(1.0 - d / (2 * p.button_accept))
        backs = [row_background(bgr, o, k, g) for k in range(g.rows)]
        if any(b is None for b in backs):
            return NpcUiState(False, "row_background", 0.0, dialog, None, finds)
        lit = [k for k, b in enumerate(backs) if b == "highlight"]
        if len(lit) > 1:
            return NpcUiState(False, "highlight_ambiguous", 0.0, dialog, None, finds)
        why, up, down, thumb = read_scrollbar(bgr, gray, o, t)
        if why not in ("ok", "none"):
            return NpcUiState(False, why, 0.0, dialog, None, finds)
        w, h = g.menu_size
        menu = MenuView(
            rect=(*o, w, h), rows=tuple(_abs(o, g.row_box(k)) for k in range(g.rows)),
            backgrounds=tuple(str(b) for b in backs), highlight_row=lit[0] if lit else None,
            scrollbar=why == "ok", can_scroll_up=up, can_scroll_down=down, thumb=thumb,
            ok_rect=_abs(o, g.ok_button), cancel_rect=_abs(o, g.cancel_button),
            up_rect=_abs(o, g.up_arrow), down_rect=_abs(o, g.down_arrow), distance=fm.distance,
        )  # fmt: skip
    return NpcUiState(True, "ok", float(max(0.0, min(conf))), dialog, menu, finds)


def centre(box: Box) -> tuple[int, int]:
    x, y, w, h = box
    return x + w // 2, y + h // 2


# --- cutting (host side: scripts/talk_calibrate.py, and the tests) ------------------------------


def border_ok(bgr: npt.NDArray[np.uint8], origin: tuple[int, int], window: str,
              g: Geometry = GEOMETRY, grey: int = 198, tol: int = 12) -> bool:  # fmt: skip
    """Calibration only: the window's grey border lines (2 px inside its rect) are where a window
    at ``origin`` would draw them. Used to accept a frame before any template exists."""
    w, h = g.size(window)
    x0, y0 = origin
    sub = bgr[y0 : y0 + h, x0 : x0 + w, :3].astype(np.int16)
    if sub.shape[:2] != (h, w):
        return False
    c = g.corner
    lines = [sub[2, c : w - c], sub[h - 3, c : w - c], sub[c : h - c, 2], sub[c : h - c, w - 3]]
    return all(float((np.abs(line - grey) <= tol).all(axis=-1).mean()) >= 0.98 for line in lines)


def cut_window(frames: Sequence[npt.NDArray[np.uint8]], origin_of: Sequence[tuple[int, int]],
               window: str, g: Geometry = GEOMETRY, tolerance: float = 4.0
               ) -> tuple[Gray, Gray]:  # fmt: skip
    """(template, mask) from frames that show ``window`` at the given origins: the median grey,
    and the structural mask narrowed to the pixels within ``tolerance`` of it in EVERY frame."""
    w, h = g.size(window)
    crops = np.stack([to_gray(np.ascontiguousarray(f[y : y + h, x : x + w, :3]))
                      for f, (x, y) in zip(frames, origin_of, strict=True)])  # fmt: skip
    tmpl = np.median(crops, axis=0).astype(np.float32)
    stable = (np.abs(crops - tmpl) < tolerance).all(axis=0)
    return tmpl, (structural_mask(window, g) * stable).astype(np.float32)


def cut_element(frames: Sequence[npt.NDArray[np.uint8]], origin_of: Sequence[tuple[int, int]],
                name: str, g: Geometry = GEOMETRY) -> Gray:  # fmt: skip
    """The median grey of one element's box over frames that show it at the given origins."""
    x0, y0, w, h = g.element_box(name)
    crops = np.stack([to_gray(np.ascontiguousarray(f[y + y0 : y + y0 + h, x + x0 : x + x0 + w, :3]))
                      for f, (x, y) in zip(frames, origin_of, strict=True)])  # fmt: skip
    return np.median(crops, axis=0).astype(np.float32)


def arrow_mask(frames: Sequence[npt.NDArray[np.uint8]], origin_of: Sequence[tuple[int, int]],
               name: str, g: Geometry = GEOMETRY) -> Gray:  # fmt: skip
    """1 on an arrow's own pixels: neither row background (the band shows through around it) nor
    white, in every frame."""
    x0, y0, w, h = g.element_box(name)
    keep = np.ones((h, w), bool)
    for f, (x, y) in zip(frames, origin_of, strict=True):
        crop = np.ascontiguousarray(f[y + y0 : y + y0 + h, x + x0 : x + x0 + w, :3])
        bg = (colour_is(crop, PLAIN_RGB, 6) | colour_is(crop, HIGHLIGHT_RGB, 6)
              | colour_is(crop, (255, 255, 255), 6))  # fmt: skip
        keep &= ~bg
    return keep.astype(np.float32)
