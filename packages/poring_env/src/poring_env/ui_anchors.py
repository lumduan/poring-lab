"""UI anchor map (ADR-0011): RO's on-screen UI addressed relative to its windows, never as pixels.

Two coordinate systems feed the one pixel space, and both keep the policy free of pixels:
  * world things (mobs, NPCs, players, walk targets): cell -> pixel through the calibrated camera
    projection (poring_dataset.projection fits it offline; the constant lives with the agent);
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


def match_template(image: Gray, template: Gray) -> Match | None:
    """Best position of `template` in `image` by sum of squared differences (FFT, numpy only)."""
    ih, iw = image.shape
    th, tw = template.shape
    if th > ih or tw > iw:
        return None
    shape = (ih + th - 1, iw + tw - 1)
    flipped = template[::-1, ::-1]
    cross = np.fft.irfft2(np.fft.rfft2(image, shape) * np.fft.rfft2(flipped, shape), shape)
    cross = cross[th - 1 : ih, tw - 1 : iw]
    sq = np.cumsum(np.cumsum(np.pad(image * image, ((1, 0), (1, 0))), 0), 1)
    window_sq = sq[th:, tw:] - sq[:-th, tw:] - sq[th:, :-tw] + sq[:-th, :-tw]
    ssd = window_sq - 2 * cross + float((template * template).sum())
    y, x = np.unravel_index(int(np.argmin(ssd)), ssd.shape)
    patch = image[y : y + th, x : x + tw]
    return Match((int(x), int(y)), float(np.abs(patch - template).mean()))


@dataclass
class UiAnchors:
    """The registry: window specs + element specs + the templates captured from lab frames."""

    windows: Mapping[str, WindowSpec]
    elements: Mapping[str, ElementSpec]
    templates: dict[str, Gray] = field(default_factory=dict)  # window name / icon element name

    def locate(self, frame_bgr: npt.NDArray[np.uint8]) -> dict[str, tuple[int, int]]:
        """Origins (client-area pixels) of every registered window visible in this frame."""
        gray = to_gray(frame_bgr)
        found: dict[str, tuple[int, int]] = {}
        for name, spec in self.windows.items():
            template = self.templates.get(name)
            if template is None:
                continue
            m = match_template(gray, template)
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


# --- the elements in use now (scope: what the agent and the tools actually need) ----------------
# Geometry is measured on the lab's client at the frozen Phase 2 resolution (docs/phase2-plan.md);
# the numbers are offsets INSIDE fixed-size RO windows, so they survive window moves.

WINDOWS = {
    "basic_info": WindowSpec("basic_info", size=(220, 240)),
    "hotbar": WindowSpec("hotbar", size=(290, 130)),
    "chat": WindowSpec("chat", size=(596, 90)),
    "game_option": WindowSpec("game_option", size=(280, 138)),
}

ELEMENTS = {
    "hp_bar": ElementSpec("hp_bar", "basic_info", box=(35, 50, 135, 9)),
    "sp_bar": ElementSpec("sp_bar", "basic_info", box=(35, 64, 135, 9)),
    "hp_sp_text": ElementSpec("hp_sp_text", "basic_info", box=(30, 46, 160, 30)),
    "chat_input": ElementSpec("chat_input", "chat", box=(100, 70, 340, 14)),
    **{
        f"hotbar_slot_{i + 1}": ElementSpec(
            f"hotbar_slot_{i + 1}", "hotbar", box=(15 + 29 * i, 3, 26, 26)
        )
        for i in range(9)
    },
    "game_option_close": ElementSpec("game_option_close", "game_option", box=(30, 117, 220, 16)),
}


def default_registry() -> UiAnchors:
    return UiAnchors(WINDOWS, ELEMENTS)


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
