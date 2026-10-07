"""UI anchor map (ADR-0011): RO's on-screen UI addressed relative to its windows, never as pixels.

Two coordinate systems feed the one pixel space, and both keep the policy free of pixels:
  * world things (mobs, NPCs, players, walk targets): cell -> pixel through the calibrated camera
    projection (fitted offline by scripts/calibrate_projection.py; the constant lives with the
    agent);
  * UI things (HP/SP bars, chat input, hotbar slots, window buttons): window-relative -> pixel
    through this map.

Layer 1 -- WINDOWS. RO windows are drag-movable and FIXED-SIZE (not scaled by the resolution), so
a window is found by template-matching a distinctive strip of it (its title bar) anywhere in the
client area. The match gives the window's origin.

Layer 2 -- ELEMENTS. Each element is a fixed offset (and size) inside its window -- slot 3 of the
hotbar is origin + (dx, dy) -- OR, for things that move between slots (an item or skill icon), a
template of the icon itself, searched inside its window.

The policy says "click chat_input" or "walk to cell offset (2, -1)"; Resolver turns that into
pixels with whatever anchors the current frame shows. A window move, a resolution change or a
different capture backend changes the anchors, never the policy.

Pixels in only: this module reads frames (Env.grab()) and nothing else. Templates are cut from the
lab's own frames and stored with the lab's data (gitignored, like ro_agent's signatures); the
element geometry below is code.

Locale-agnostic (ADR-0012): the map stores KEYS, never text. Window and element names are canonical
identifiers; an element whose meaning is a piece of UI text carries a ``label_key`` -- a message key
(``msg.k`` + 8 hex of sha1 of the normalised Korean source string) or a curated alias (``ui.*``) --
and the text itself lives only in a locale pack outside the repo. Templates are made
locale-invariant by masking: ``stable_masks`` keeps only the pixels that agree across every variant
(other scenes AND other locales), so a title's text drops out of the mask.
"""

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import numpy.typing as npt

Gray = npt.NDArray[np.float32]

# Canonical identifiers (ADR-0012): ASCII snake_case, so a name can never be a locale's text.
CANONICAL_NAME = re.compile(r"[a-z][a-z0-9_]*")
# A message key: "msg.k" + the first 8 hex of sha1(normalised Korean source string). Stable across
# client versions; a per-version key -> line map (in the locale pack) finds it in each table.
MESSAGE_KEY = re.compile(r"msg\.k[0-9a-f]{8}")
# A curated alias: a readable name in code that POINTS AT a message key and never holds text.
ALIAS_KEY = re.compile(r"ui(\.[a-z][a-z0-9_]*)+")


def is_label_key(value: str) -> bool:
    """True for a message key or a curated alias; False for anything else (e.g. display text)."""
    return bool(MESSAGE_KEY.fullmatch(value) or ALIAS_KEY.fullmatch(value))


def _check_name(kind: str, name: str) -> None:
    if not CANONICAL_NAME.fullmatch(name):
        raise ValueError(f"{kind} name {name!r} is not a canonical identifier ([a-z][a-z0-9_]*)")


@dataclass(frozen=True, slots=True)
class WindowSpec:
    """A fixed-size RO window, found by a template of one of its strips (usually the title bar)."""

    name: str
    size: tuple[int, int]  # (w, h) of the whole window, pixels
    template_offset: tuple[int, int] = (0, 0)  # where the template sits inside the window
    max_distance: float = 12.0  # mean abs grey difference accepted as a match
    template_size: tuple[int, int] | None = None  # (w, h) of the strip cut as the template

    def __post_init__(self) -> None:
        _check_name("window", self.name)


@dataclass(frozen=True, slots=True)
class ElementSpec:
    """An element inside a window: a box at a fixed offset, or an icon found by template.

    ``label_key``: when the element's meaning is a piece of UI text (a button caption, a field
    label), the KEY of that text -- a message key or a curated alias, never the text itself. The
    locale pack turns it into the string of the language on screen (OCR auto-labels, ADR-0012)."""

    name: str
    window: str
    box: tuple[int, int, int, int] | None = None  # (dx, dy, w, h) relative to the window origin
    icon: bool = False  # True: located by its own template inside the window (moves between slots)
    label_key: str | None = None

    def __post_init__(self) -> None:
        _check_name("element", self.name)
        _check_name("window", self.window)
        if self.label_key is not None and not is_label_key(self.label_key):
            raise ValueError(
                f"{self.name}: label_key {self.label_key!r} is not a message key (msg.k + 8 hex) "
                "or a curated alias (ui.*): the map stores keys, never text"
            )

    def centre(self, origin: tuple[int, int]) -> tuple[int, int]:
        if self.box is None:
            raise ValueError(f"{self.name} has no fixed box (icon element)")
        dx, dy, w, h = self.box
        return origin[0] + dx + w // 2, origin[1] + dy + h // 2


@dataclass(frozen=True, slots=True)
class Match:
    origin: tuple[int, int]  # client-area pixels
    distance: float  # mean abs grey difference of the template at the match


def to_gray(frame_bgr: npt.NDArray[np.uint8]) -> Gray:
    f = frame_bgr[..., :3].astype(np.float32)
    return np.asarray(0.114 * f[..., 0] + 0.587 * f[..., 1] + 0.299 * f[..., 2], np.float32)


def _correlate(image: Gray, kernel: Gray) -> npt.NDArray[np.float64]:
    """Valid-mode cross-correlation by FFT: out[y, x] = sum(image[y:y+h, x:x+w] * kernel)."""
    ih, iw = image.shape
    th, tw = kernel.shape
    shape = (ih + th - 1, iw + tw - 1)
    spectrum = np.fft.rfft2(image, shape) * np.fft.rfft2(kernel[::-1, ::-1], shape)
    full = np.fft.irfft2(spectrum, shape)
    return np.asarray(full[th - 1 : ih, tw - 1 : iw], np.float64)


def match_template(image: Gray, template: Gray, mask: Gray | None = None) -> Match | None:
    """Best position of `template` in `image` by sum of squared differences (FFT, numpy only).

    With a ``mask`` (1 = use the pixel) only the template's STABLE pixels count: RO's windows are
    partly translucent (the chat window almost entirely), so the pixels where the scene shows
    through differ on every background. The distance is the mean abs grey difference over the
    used pixels at the best position."""
    ih, iw = image.shape
    th, tw = template.shape
    if th > ih or tw > iw:
        return None
    m = np.ones_like(template) if mask is None else mask.astype(np.float32)
    if float(m.sum()) == 0:
        return None
    # sum m*(I - T)^2 = corr(I^2, m) - 2 corr(I, m*T) + sum(m*T^2)
    ssd = _correlate(image * image, m) - 2 * _correlate(image, m * template)
    ssd += float((m * template * template).sum())
    y, x = np.unravel_index(int(np.argmin(ssd)), ssd.shape)
    diff = np.abs(image[y : y + th, x : x + tw] - template)
    return Match((int(x), int(y)), float((diff * m).sum() / m.sum()))


@dataclass
class UiAnchors:
    """The registry: window specs + element specs + the templates captured from lab frames."""

    windows: Mapping[str, WindowSpec]
    elements: Mapping[str, ElementSpec]
    templates: dict[str, Gray] = field(default_factory=dict)  # window name / icon element name
    masks: dict[str, Gray] = field(default_factory=dict)  # optional: 1 = a pixel stable in play

    def locate(self, frame_bgr: npt.NDArray[np.uint8]) -> dict[str, tuple[int, int]]:
        """Origins (client-area pixels) of every registered window visible in this frame."""
        gray = to_gray(frame_bgr)
        found: dict[str, tuple[int, int]] = {}
        for name, spec in self.windows.items():
            template = self.templates.get(name)
            if template is None:
                continue
            m = match_template(gray, template, self.masks.get(name))
            if m is not None and m.distance <= spec.max_distance:
                ox, oy = spec.template_offset
                found[name] = (m.origin[0] - ox, m.origin[1] - oy)
        return found

    def resolve(
        self,
        element: str,
        origins: Mapping[str, tuple[int, int]],
        frame_bgr: npt.NDArray[np.uint8] | None = None,
    ) -> tuple[int, int] | None:
        """Client-area pixel of `element`'s centre; None when its window is not on screen."""
        spec = self.elements[element]
        origin = origins.get(spec.window)
        if origin is None:
            return None
        if not spec.icon:
            return spec.centre(origin)
        template = self.templates.get(element)
        if template is None or frame_bgr is None:
            return None
        w, h = self.windows[spec.window].size
        x0, y0 = origin
        region = to_gray(frame_bgr[y0 : y0 + h, x0 : x0 + w])
        m = match_template(region, template)
        if m is None or m.distance > self.windows[spec.window].max_distance:
            return None
        th, tw = template.shape
        return x0 + m.origin[0] + tw // 2, y0 + m.origin[1] + th // 2

    def labelled_boxes(
        self, origins: Mapping[str, tuple[int, int]]
    ) -> dict[str, tuple[tuple[int, int, int, int], str]]:
        """Every visible element that carries a ``label_key``: its box in client-area pixels and
        the key. With a locale pack's key -> text table this labels an OCR crop exactly (ADR-0012,
        docs/locale-packs.md); the text never enters this module."""
        out: dict[str, tuple[tuple[int, int, int, int], str]] = {}
        for name, spec in self.elements.items():
            origin = origins.get(spec.window)
            if spec.label_key is None or spec.box is None or origin is None:
                continue
            dx, dy, w, h = spec.box
            out[name] = ((origin[0] + dx, origin[1] + dy, w, h), spec.label_key)
        return out


def validate_registry(
    windows: Mapping[str, WindowSpec], elements: Mapping[str, ElementSpec]
) -> None:
    """Registry keys equal the specs' canonical names, and every element's window is registered."""
    for key, w in windows.items():
        if key != w.name:
            raise ValueError(f"window registered as {key!r} but named {w.name!r}")
    for key, e in elements.items():
        if key != e.name:
            raise ValueError(f"element registered as {key!r} but named {e.name!r}")
        if e.window not in windows:
            raise ValueError(f"element {key!r} sits in unregistered window {e.window!r}")


def validate_aliases(aliases: Mapping[str, str]) -> None:
    """Each curated alias is a ``ui.*`` name pointing at a message key -- never at text."""
    for alias, key in aliases.items():
        if not ALIAS_KEY.fullmatch(alias):
            raise ValueError(f"alias {alias!r} is not ui.<name>[.<name>...]")
        if not MESSAGE_KEY.fullmatch(key):
            raise ValueError(
                f"alias {alias!r} points at {key!r}, not a message key (msg.k + 8 hex)"
            )


def cut_templates(
    frame_bgr: npt.NDArray[np.uint8],
    origins: Mapping[str, tuple[int, int]],
    windows: Mapping[str, WindowSpec],
) -> dict[str, Gray]:
    """Each window's template strip, cut from a frame where the window is known to be at
    ``origins[name]`` (client-area pixels). Windows without a ``template_size`` are skipped."""
    out: dict[str, Gray] = {}
    for name, (ox, oy) in origins.items():
        spec = windows[name]
        if spec.template_size is None:
            continue
        tx, ty = spec.template_offset
        tw, th = spec.template_size
        out[name] = to_gray(frame_bgr[oy + ty : oy + ty + th, ox + tx : ox + tx + tw])
    return out


def stable_masks(
    templates: Mapping[str, Gray],
    others: Mapping[str, Gray] | Sequence[Mapping[str, Gray]],
    tolerance: float = 4.0,
) -> dict[str, Gray]:
    """Per template, the pixels that stay within ``tolerance`` grey levels in EVERY variant: the
    same window cut over other scenes (the translucent parts drop out) and in other locales (the
    title text drops out, ADR-0012). ``others`` is one variant (a mapping, the original two-frame
    call) or a sequence of them. A variant whose strip has another shape is ignored for that name;
    a name no variant covers gets no mask."""
    variants = [others] if isinstance(others, Mapping) else list(others)
    out: dict[str, Gray] = {}
    for name, t in templates.items():
        same = [v[name] for v in variants if name in v and v[name].shape == t.shape]
        if not same:
            continue
        stable = np.ones(t.shape, dtype=bool)
        for other in same:
            stable &= np.abs(t - other) < tolerance
        out[name] = stable.astype(np.float32)
    return out


def save_templates(
    directory: Path, templates: Mapping[str, Gray], masks: Mapping[str, Gray] | None = None
) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    for name, gray in templates.items():
        np.save(directory / f"{name}.npy", gray)
    for name, mask in (masks or {}).items():
        np.save(directory / f"{name}_mask.npy", mask)


def load_templates(directory: Path, names: Mapping[str, object]) -> dict[str, Gray]:
    """The saved templates for the registered names that have one (lab data, gitignored)."""
    return _load(directory, names, "")


def load_masks(directory: Path, names: Mapping[str, object]) -> dict[str, Gray]:
    return _load(directory, names, "_mask")


def _load(directory: Path, names: Mapping[str, object], suffix: str) -> dict[str, Gray]:
    out: dict[str, Gray] = {}
    for name in names:
        path = directory / f"{name}{suffix}.npy"
        if path.exists():
            out[name] = np.asarray(np.load(path), np.float32)
    return out


# --- the elements in use now (scope: what the agent and the tools actually need) ----------------
# Measured 2026-10-02 on the lab's client at the frozen Phase 2 layout: a 1:1 1280x720 client area
# (docs/phase2-plan.md). The numbers are offsets INSIDE fixed-size RO windows, so they survive
# window moves. Each window is found by a strip that does not change in play: a title bar, the
# hotkey bar's row-number column, the chat tabs.

WINDOWS = {
    "basic_info": WindowSpec("basic_info", size=(220, 140), template_size=(200, 15)),
    "hotbar": WindowSpec(
        "hotbar", size=(290, 131), template_offset=(0, 30), template_size=(16, 100)
    ),
    "chat": WindowSpec("chat", size=(597, 93), template_size=(240, 15)),
    "game_option": WindowSpec("game_option", size=(280, 138), template_size=(260, 15)),
    # The minimap (Phase 3 T0, measured 2026-10-04 on the S2 console frames): right-anchored, not
    # draggable. Its dark frame is 128 px wide from the top border at y=18; under the map, a 12 px
    # row holds the magnifier icon, the coordinate readout and the zoom buttons. Found by those
    # buttons (static icons over the translucent row: they need a stable mask). The client draws
    # no minimap on indoor maps (prt_church), so the window -- and our cell -- is absent there.
    "minimap": WindowSpec(
        "minimap", size=(128, 142), template_offset=(72, 127), template_size=(54, 12)
    ),
    # The windows of the demonstrated shortcuts (measured 2026-10-07 on RDP, docs/phase4-ui.md):
    # the same title-bar style as basic_info, so a whole 200x15 title strip cross-matched status /
    # inventory / equipment at 8.8-13.1 (under the default 12). The strip is the title TEXT only
    # (60x13 at dx 14). Over RDP: its own window 0.00 indoors and outdoors (the title bar is
    # opaque), the nearest wrong window 16.6 (equipment over inventory), nothing open >= 20.2 --
    # hence max_distance 6. Not measured on S2 (lossy): re-check there before relying on it.
    # skills: the origin is the title bar's frame; its tab strip hangs 17 px left of it.
    "status": WindowSpec(
        "status", size=(280, 141), template_offset=(14, 1), template_size=(60, 13), max_distance=6.0
    ),
    "skills": WindowSpec(
        "skills", size=(542, 400), template_offset=(14, 1), template_size=(60, 13), max_distance=6.0
    ),
    "inventory": WindowSpec(
        "inventory",
        size=(280, 255),
        template_offset=(14, 1),
        template_size=(60, 13),
        max_distance=6.0,
    ),
    "equipment": WindowSpec(
        "equipment",
        size=(280, 187),
        template_offset=(14, 1),
        template_size=(60, 13),
        max_distance=6.0,
    ),
}

ELEMENTS = {
    "hp_bar": ElementSpec("hp_bar", "basic_info", box=(35, 53, 135, 9)),
    "sp_bar": ElementSpec("sp_bar", "basic_info", box=(35, 68, 135, 9)),
    "hp_sp_text": ElementSpec("hp_sp_text", "basic_info", box=(30, 51, 190, 27)),
    "chat_input": ElementSpec("chat_input", "chat", box=(80, 72, 400, 14)),
    **{
        f"hotbar_slot_{i + 1}": ElementSpec(
            f"hotbar_slot_{i + 1}", "hotbar", box=(15 + 29 * i, 3, 26, 26)
        )
        for i in range(9)
    },
    "game_option_close": ElementSpec("game_option_close", "game_option", box=(30, 113, 220, 20)),
    # Our own cell as "x y" (no label_key: digits, not UI text). Strokes on window rows 130-138
    # (y 148-156 on the frame), first digit cell at dx 22, 7 px per digit; the box keeps 2 rows
    # above and below the 11-row digit cell for the reader's baseline search, and stops where the
    # zoom buttons start (dx 72). poring_env.selfpos reads it (T0).
    "minimap_xy": ElementSpec("minimap_xy", "minimap", box=(16, 127, 56, 15)),
}

# Where the windows sat when the templates were cut (client-area pixels, 1280x720, 2026-10-02).
# Only for cutting templates: at run time windows are LOCATED, wherever they have been dragged.
CAPTURE_ORIGINS = {
    "basic_info": (0, 0),
    "hotbar": (230, 0),
    "chat": (0, 531),
    "game_option": (505, 450),  # open only after Escape
    "minimap": (1136, 18),  # right-anchored; outdoor maps only (measured 2026-10-04, S2 console)
    # where the shortcuts opened them (2026-10-07, RDP; the client reopens a window where it was)
    "status": (185, 300),
    "skills": (378, 200),
    "inventory": (0, 120),
    "equipment": (185, 300),
}


# Curated aliases (ADR-0012): readable names in code -> message keys. Text never lives here. The
# keys are filled in from the kRO reference once it is on the NAS. Committing them is allowed
# (Batt, 2026-10-02): keys only; the pre-commit guard still blocks pack text.
ALIASES: dict[str, str] = {}

validate_registry(WINDOWS, ELEMENTS)
validate_aliases(ALIASES)


def default_registry(template_dir: Path | None = None) -> UiAnchors:
    anchors = UiAnchors(WINDOWS, ELEMENTS)
    if template_dir is not None:
        anchors.templates.update(load_templates(template_dir, {**WINDOWS, **ELEMENTS}))
        anchors.masks.update(load_masks(template_dir, {**WINDOWS, **ELEMENTS}))
    return anchors


class Resolver:
    """Policy-side seam: semantic targets -> client-area pixels, given the current frame."""

    def __init__(self, anchors: UiAnchors, camera: npt.NDArray[np.float64] | None = None) -> None:
        self.anchors = anchors
        self.camera = camera  # 3x3 cell-offset -> pixel homography (the calibrated default camera)

    def ui(self, element: str, frame_bgr: npt.NDArray[np.uint8]) -> tuple[int, int] | None:
        return self.anchors.resolve(element, self.anchors.locate(frame_bgr), frame_bgr)

    def cell(self, dx: float, dy: float) -> tuple[int, int]:
        """Pixel of the cell (dx, dy) from the player, under the default camera."""
        if self.camera is None:
            raise ValueError("no calibrated camera: run scripts/calibrate_projection.py --save")
        u, v, w = self.camera @ np.array([dx, dy, 1.0])
        return int(round(u / w)), int(round(v / w))
