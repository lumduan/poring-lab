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
"""

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import numpy.typing as npt

Gray = npt.NDArray[np.float32]


@dataclass(frozen=True, slots=True)
class WindowSpec:
    """A fixed-size RO window, found by a template of one of its strips (usually the title bar)."""

    name: str
    size: tuple[int, int]  # (w, h) of the whole window, pixels
    template_offset: tuple[int, int] = (0, 0)  # where the template sits inside the window
    max_distance: float = 12.0  # mean abs grey difference accepted as a match
    template_size: tuple[int, int] | None = None  # (w, h) of the strip cut as the template


@dataclass(frozen=True, slots=True)
class ElementSpec:
    """An element inside a window: a box at a fixed offset, or an icon found by template."""

    name: str
    window: str
    box: tuple[int, int, int, int] | None = None  # (dx, dy, w, h) relative to the window origin
    icon: bool = False  # True: located by its own template inside the window (moves between slots)

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
    templates: Mapping[str, Gray], others: Mapping[str, Gray], tolerance: float = 4.0
) -> dict[str, Gray]:
    """Per template, the pixels that stay within ``tolerance`` grey levels when the SAME window is
    cut over a different background (another scene): the opaque parts."""
    return {
        name: (np.abs(t - others[name]) < tolerance).astype(np.float32)
        for name, t in templates.items()
        if name in others and others[name].shape == t.shape
    }


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
}

# Where the windows sat when the templates were cut (client-area pixels, 1280x720, 2026-10-02).
# Only for cutting templates: at run time windows are LOCATED, wherever they have been dragged.
CAPTURE_ORIGINS = {
    "basic_info": (0, 0),
    "hotbar": (230, 0),
    "chat": (0, 531),
    "game_option": (505, 450),  # open only after Escape
}


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
