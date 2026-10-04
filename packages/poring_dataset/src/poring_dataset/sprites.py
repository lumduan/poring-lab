"""RO sprite sheets (SPR) and their animation tables (ACT), parsed into numpy (Phase 3 M1).

PORTED (the formats and the layer rule, re-expressed in Python/numpy; no code copied verbatim) from
nmeylan/nostalro-client @ 15b3029 (Apache-2.0, THIRD_PARTY.md):
  * lib/formats/src/spr.rs: SPR 1.0-2.1. "SP" | minor u8 | major u8 | palette-image count u16 |
    RGBA-image count u16 (from 1.2). Palette images are w u16 | h u16 | w*h indices, run-length
    encoded from 2.1 (only index 0 is: 0x00 then a count, a zero count = one pixel). RGBA images are
    w u16 | h u16 | w*h*4 bytes stored A,B,G,R and BOTTOM-UP. The 256-entry palette (R,G,B,unused)
    closes the file from 1.1. Index 0 is transparent, and so is a palette colour on the magenta
    key (R >= 0xFE, G <= 0x01, B >= 0xFE; spr.rs apply_palette).
  * lib/formats/src/act.rs: ACT 2.0-2.5. "AC" | minor | major | action count u16 | 10 reserved;
    per action: motions; per motion: 32 bytes of ranges | layers; per layer: x i32 | y i32 |
    sprite index i32 | mirror u32, then from 2.0 colour (R,G,B,A) | zoom f32 (2.0-2.3) or zoom_x,
    zoom_y f32 (2.4+) | angle i32 (degrees) | sprite type u32 (0 palette image, else RGBA image),
    and from 2.5 the quad's own width, height u32; then an event id i32 (2.0+) and attach points
    (2.3+). After the actions: event names, 40 bytes each (2.1+), and one delay f32 per action
    (2.2+), in units of FRAME_DELAY_UNIT_MS (act.rs:7-13: a missing or sub-unit delay is one unit).
  * lib/renderer/src/sprite.rs build_clip_quad (L842-934): a layer is a quad CENTRED at
    anchor + (x, y), sized w*zoom_x by h*zoom_y (w, h = the ACT's own size when both are set, else
    the image's), rotated by `angle` degrees about its centre, its U coordinates swapped when
    `mirror` is set, tinted by `colour`. Screen y grows downwards, so a negative y is ABOVE the
    anchor (the actor's feet).
Cross-checked against vE5li/korangar @ e14d320 (MIT, THIRD_PARTY.md), korangar/src/loaders/
animation/mod.rs: the same layer fields and colour byte order. It differs in three details: it
centres a layer on integer pixels ((size - 1) / 2) and rounds a zoomed size up (ceil), where
nostalro centres it exactly (size / 2) and keeps the zoom fractional -- at most half a source pixel
per edge; and it sizes a layer from its image only, ignoring the ACT 2.5 width/height. Nostalro is
the rule here.

The data is CLIENT data: SPR/ACT bytes are read from the client's GRF into /dev/shm at run time and
NEVER committed, and neither is anything rendered from them (CLAUDE.md rule 4). The tests build
their sprites from synthetic bytes.
"""

import math
import struct
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
import numpy.typing as npt

RGBA = npt.NDArray[np.uint8]  # (h, w, 4), top-down rows, straight (non-premultiplied) alpha
Box = tuple[float, float, float, float]  # x0, y0, x1, y1; sprite px, relative to the anchor
FRAME_DELAY_UNIT_MS = 24.0  # nostalro act.rs:8
PALETTE_TYPE = 0  # a layer's sprite type: 0 = palette image, anything else = RGBA image


class SpriteFormatError(ValueError):
    """Not an SPR/ACT, a version this parser does not know, or truncated data."""


class MissingImageSize(ValueError):
    """A layer's quad size is unknown: no SPR at hand, and the ACT has no width/height (< 2.5)."""


def _version_at_least(version: tuple[int, int], major: int, minor: int) -> bool:
    return version[0] > major or (version[0] == major and version[1] >= minor)


class _Reader:
    """Little-endian reads over bytes; any overrun is a SpriteFormatError (never an IndexError)."""

    def __init__(self, data: bytes, what: str) -> None:
        self.data, self.pos, self.what = data, 0, what

    def take(self, n: int) -> bytes:
        if n < 0 or self.pos + n > len(self.data):
            raise SpriteFormatError(f"{self.what}: truncated at byte {self.pos} (wanted {n} more)")
        out = self.data[self.pos : self.pos + n]
        self.pos += n
        return out

    def unpack(self, fmt: str) -> tuple[int | float, ...]:
        st = struct.Struct("<" + fmt)
        return st.unpack(self.take(st.size))

    def u8(self) -> int:
        return int(self.unpack("B")[0])

    def u16(self) -> int:
        return int(self.unpack("H")[0])

    def u32(self) -> int:
        return int(self.unpack("I")[0])

    def i32(self) -> int:
        return int(self.unpack("i")[0])

    def f32(self) -> float:
        return float(self.unpack("f")[0])


# --- SPR ------------------------------------------------------------------------------------------


@dataclass(frozen=True, eq=False)  # numpy images: compare them explicitly, never with ==
class Spr:
    """A sprite sheet: every image as RGBA, palette images first (``indexed_count`` of them), then
    the RGBA ones -- the index space ACT layers address."""

    version: tuple[int, int]
    images: tuple[RGBA, ...]
    indexed_count: int
    palette: npt.NDArray[np.uint8] | None  # (256, 4) as stored: R, G, B, unused

    def image_index(self, sprite_index: int, sprite_type: int) -> int | None:
        """The image an ACT layer draws (sprite.rs clip_texture_index), or None: nothing drawn."""
        if sprite_index < 0:
            return None
        index = sprite_index if sprite_type == PALETTE_TYPE else self.indexed_count + sprite_index
        return index if index < len(self.images) else None

    def size(self, index: int) -> tuple[int, int]:
        """(width, height) of image ``index``."""
        h, w = self.images[index].shape[:2]
        return int(w), int(h)


def _rle_zero_decode(data: bytes, pixel_count: int) -> npt.NDArray[np.uint8]:
    """SPR 2.1 palette-image RLE: a 0x00 byte is followed by its run length (0 = one pixel); every
    other byte is a literal index (spr.rs decompress_indexed). Output beyond ``pixel_count`` is
    dropped, a short stream leaves the rest transparent."""
    out = np.zeros(pixel_count, np.uint8)
    i = nxt = 0
    n = len(data)
    while i < n and nxt < pixel_count:
        b = data[i]
        if b == 0:
            i += 1
            nxt += max(data[i], 1) if i < n else 1
        else:
            out[nxt] = b
            nxt += 1
        i += 1
    return out


def apply_palette(indices: npt.NDArray[np.uint8], palette: npt.NDArray[np.uint8]) -> RGBA:
    """Palette indices (h, w) -> RGBA. Index 0 and the magenta key are transparent (all zero)."""
    pal = np.asarray(palette, np.uint8)
    keyed = (pal[:, 0] >= 0xFE) & (pal[:, 1] <= 0x01) & (pal[:, 2] >= 0xFE)
    clear = keyed.copy()
    clear[0] = True
    rgba = np.zeros((*indices.shape, 4), np.uint8)
    rgba[..., :3] = pal[indices, :3]
    rgba[..., 3] = 255
    rgba[clear[indices]] = 0
    return rgba


def parse_spr(data: bytes, palette: npt.NDArray[np.uint8] | None = None) -> Spr:
    """Parse an SPR. ``palette`` (256, 4) overrides the file's own (SPR 1.0 has none: its .pal
    must be given)."""
    r = _Reader(data, "SPR")
    if r.take(2) != b"SP":
        raise SpriteFormatError("SPR: magic is not 'SP'")
    minor, major = r.u8(), r.u8()
    version = (major, minor)
    if not ((1, 0) <= version <= (2, 1)):
        raise SpriteFormatError(f"SPR: version {major}.{minor} (only 1.0-2.1)")
    n_indexed = r.u16()
    n_rgba = r.u16() if _version_at_least(version, 1, 2) else 0
    indexed: list[npt.NDArray[np.uint8]] = []
    for _ in range(n_indexed):
        w, h = r.u16(), r.u16()
        count = w * h
        if count == 0:
            pixels = np.zeros(0, np.uint8)
        elif _version_at_least(version, 2, 1):
            pixels = _rle_zero_decode(r.take(r.u16()), count)
        else:
            pixels = np.frombuffer(r.take(count), np.uint8).copy()
        indexed.append(pixels.reshape(h, w))
    rgba: list[RGBA] = []
    for _ in range(n_rgba):
        w, h = r.u16(), r.u16()
        abgr = np.frombuffer(r.take(w * h * 4), np.uint8).reshape(h, w, 4)
        rgba.append(np.ascontiguousarray(abgr[::-1, :, ::-1]))  # bottom-up ABGR -> top-down RGBA
    own = None
    if _version_at_least(version, 1, 1):
        own = np.frombuffer(r.take(1024), np.uint8).reshape(256, 4).copy()
    pal = own if palette is None else np.asarray(palette, np.uint8).reshape(256, 4)
    if pal is None and indexed:
        raise SpriteFormatError(f"SPR {major}.{minor} carries no palette: pass its .pal")
    images = tuple(apply_palette(ix, pal) for ix in indexed) if pal is not None else ()
    return Spr(version, images + tuple(rgba), len(indexed), pal)


# --- ACT ------------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Layer:
    """One ACT layer ("clip"): an SPR image placed relative to the anchor."""

    x: int
    y: int
    sprite_index: int  # -1 = draws nothing
    mirror: bool
    color: tuple[int, int, int, int]  # R, G, B, A tint
    zoom_x: float
    zoom_y: float
    angle: int  # degrees, clockwise on screen (y down)
    sprite_type: int  # 0 = palette image, else RGBA image
    width: int | None = None  # ACT 2.5+: the quad's own size; None/0 = the image's
    height: int | None = None


@dataclass(frozen=True, slots=True)
class AttachPoint:
    x: int
    y: int
    attribute: int


@dataclass(frozen=True, slots=True)
class Motion:
    """One animation frame: its layers in draw order (later ones on top)."""

    layers: tuple[Layer, ...]
    event_id: int = -1  # index into Act.events, -1 = none
    attach_points: tuple[AttachPoint, ...] = ()


@dataclass(frozen=True, slots=True)
class Act:
    version: tuple[int, int]
    actions: tuple[tuple[Motion, ...], ...]  # action_index = group * 8 + direction
    events: tuple[str, ...] = ()
    delays: tuple[float, ...] = ()  # per action, in FRAME_DELAY_UNIT_MS units (ACT 2.2+)

    @property
    def groups(self) -> int:
        """Action groups (idle, walk, ...): 8 directions each."""
        return len(self.actions) // 8

    def action_index(self, group: int, direction: int) -> int:
        """The action drawn for ``group`` facing sprite ``direction`` (act.rs:568-570; the
        direction is already camera-relative, camera.displayed_direction)."""
        if not self.actions:
            raise SpriteFormatError("ACT has no actions")
        return (int(group) * 8 + int(direction) % 8) % len(self.actions)

    def delay_units(self, action_index: int) -> float:
        """The action's frame delay in 24 ms units; missing or sub-unit = 1 (act.rs:10-13)."""
        d = self.delays[action_index] if action_index < len(self.delays) else 1.0
        return max(float(d), 1.0) if math.isfinite(d) else 1.0

    def delay_ms(self, action_index: int) -> float:
        return self.delay_units(action_index) * FRAME_DELAY_UNIT_MS


def _decode_event(raw: bytes) -> str:
    """A NUL-terminated EUC-KR name (act.rs read_string); undecodable bytes stay visible."""
    return raw.split(b"\x00", 1)[0].decode("cp949", errors="replace")


def parse_act(data: bytes) -> Act:
    r = _Reader(data, "ACT")
    if r.take(2) != b"AC":
        raise SpriteFormatError("ACT: magic is not 'AC'")
    minor, major = r.u8(), r.u8()
    version = (major, minor)
    if not ((1, 0) <= version <= (2, 5)):
        raise SpriteFormatError(f"ACT: version {major}.{minor} (only up to 2.5)")
    v20, v23, v24, v25 = (_version_at_least(version, 2, m) for m in (0, 3, 4, 5))
    n_actions = r.u16()
    r.take(10)
    actions: list[tuple[Motion, ...]] = []
    for _ in range(n_actions):
        motions: list[Motion] = []
        for _ in range(r.u32()):
            r.take(32)  # two legacy rectangles (range1, range2): unused by every client read
            layers: list[Layer] = []
            for _ in range(r.u32()):
                x, y, index, mirror = r.i32(), r.i32(), r.i32(), r.u32()
                color, zx, zy, angle, stype = (255, 255, 255, 255), 1.0, 1.0, 0, PALETTE_TYPE
                if v20:
                    c = r.take(4)
                    color = (c[0], c[1], c[2], c[3])
                    zx = r.f32()
                    zy = r.f32() if v24 else zx
                    angle, stype = r.i32(), r.u32()
                w, h = (r.u32(), r.u32()) if v25 else (None, None)
                layers.append(Layer(x, y, index, mirror != 0, color, zx, zy, angle, stype, w, h))
            event_id = r.i32() if v20 else -1
            points: list[AttachPoint] = []
            if v23:
                for _ in range(r.u32()):
                    _ignored, ax, ay, attr = r.u32(), r.i32(), r.i32(), r.u32()
                    points.append(AttachPoint(ax, ay, attr))
            motions.append(Motion(tuple(layers), event_id, tuple(points)))
        actions.append(tuple(motions))
    events: tuple[str, ...] = ()
    if _version_at_least(version, 2, 1):
        events = tuple(_decode_event(r.take(40)) for _ in range(r.u32()))
    delays: tuple[float, ...] = ()
    if _version_at_least(version, 2, 2):
        delays = tuple(r.f32() for _ in range(n_actions))
    return Act(version, tuple(actions), events, delays)


# --- layer geometry and composition ---------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Quad:
    """A layer's quad in sprite px around the anchor: centre, half size, rotation, mirror."""

    cx: float
    cy: float
    half_w: float
    half_h: float
    cos: float
    sin: float
    mirror: bool

    def corners(self) -> npt.NDArray[np.float64]:
        """(4, 2): top-left, top-right, bottom-right, bottom-left after rotation (sprite.rs
        L904-929: rx = x cos - y sin, ry = x sin + y cos)."""
        local = np.array([[-self.half_w, -self.half_h], [self.half_w, -self.half_h],
                          [self.half_w, self.half_h], [-self.half_w, self.half_h]])  # fmt: skip
        rot = np.array([[self.cos, -self.sin], [self.sin, self.cos]])
        return np.asarray(local @ rot.T + [self.cx, self.cy], dtype=float)

    def extent(self) -> Box:
        c = self.corners()
        x0, y0 = c.min(axis=0)
        x1, y1 = c.max(axis=0)
        return float(x0), float(y0), float(x1), float(y1)


# exact quarter turns: math.cos(pi/2) is 6e-17, enough to grow a canvas by a whole pixel
_QUARTER_TURNS = {0: (1.0, 0.0), 90: (0.0, 1.0), 180: (-1.0, 0.0), 270: (0.0, -1.0)}
_EPS = 1e-9  # canvas sizing tolerance for rotated/zoomed corners (sprite px)


def layer_quad(layer: Layer, image_size: tuple[int, int] | None) -> Quad | None:
    """The quad a layer draws (sprite.rs build_clip_quad). Its size is the ACT's own (2.5+, both
    > 0) else ``image_size``; MissingImageSize when neither is known. None for a degenerate quad
    (a zero size or zoom)."""
    if layer.width and layer.height:
        w, h = float(layer.width), float(layer.height)
    elif image_size is not None:
        w, h = float(image_size[0]), float(image_size[1])
    else:
        raise MissingImageSize(f"layer at ({layer.x}, {layer.y}): no SPR and no ACT 2.5 size")
    hw, hh = w * layer.zoom_x / 2.0, h * layer.zoom_y / 2.0
    if hw == 0 or hh == 0 or not (math.isfinite(hw) and math.isfinite(hh)):
        return None
    cos, sin = _QUARTER_TURNS.get(layer.angle % 360, (math.nan, math.nan))
    if math.isnan(cos):
        a = math.radians(layer.angle)
        cos, sin = math.cos(a), math.sin(a)
    return Quad(float(layer.x), float(layer.y), hw, hh, cos, sin, layer.mirror)


def _motion(act: Act, action_index: int, motion_index: int) -> Motion:
    if not 0 <= action_index < len(act.actions):
        raise IndexError(f"action {action_index} of {len(act.actions)}")
    motions = act.actions[action_index]
    if not 0 <= motion_index < len(motions):
        raise IndexError(f"motion {motion_index} of {len(motions)} (action {action_index})")
    return motions[motion_index]


def _drawn(spr: Spr | None, motion: Motion) -> list[tuple[Layer, Quad, int | None]]:
    """(layer, quad, image index) for every layer that draws something. Without an SPR every layer
    with a sprite index >= 0 counts and the quad comes from the ACT's own size. A layer tinted to
    alpha 0 draws no pixel, so it is skipped (it would only widen a quad extent)."""
    out: list[tuple[Layer, Quad, int | None]] = []
    for layer in motion.layers:
        if layer.color[3] == 0:
            continue
        if spr is None:
            if layer.sprite_index < 0:
                continue
            quad, index = layer_quad(layer, None), None
        else:
            index = spr.image_index(layer.sprite_index, layer.sprite_type)
            if index is None:
                continue
            quad = layer_quad(layer, spr.size(index))
        if quad is not None:
            out.append((layer, quad, index))
    return out


def union(boxes: Sequence[Box | None]) -> Box | None:
    """The smallest box holding every given box (None entries are skipped)."""
    real = [b for b in boxes if b is not None]
    if not real:
        return None
    return (min(b[0] for b in real), min(b[1] for b in real),
            max(b[2] for b in real), max(b[3] for b in real))  # fmt: skip


def quad_extent(
    act: Act, action_index: int, motion_index: int, spr: Spr | None = None
) -> Box | None:
    """The union of a motion's layer QUADS (sprite px around the anchor) -- what the client draws,
    transparent margins included. Needs no pixels: with ``spr`` None it uses the ACT 2.5 sizes
    (MissingImageSize otherwise). None when the motion draws nothing."""
    return union([q.extent() for _, q, _ in _drawn(spr, _motion(act, action_index, motion_index))])


def compose_frame(
    spr: Spr, act: Act, action_index: int, motion_index: int
) -> tuple[RGBA, tuple[float, float]]:
    """Composite every layer of one motion, in order, around the anchor.

    Returns (rgba, origin): ``rgba`` (h, w, 4) uint8 with straight alpha, and ``origin`` = (ox, oy),
    the ANCHOR's position on that canvas, whose pixel (i, j) covers [i, i+1) x [j, j+1). A sprite
    point (sx, sy) sits at canvas (sx + ox, sy + oy).

    Each canvas pixel CENTRE is mapped back into each layer (inverse rotation, zoom, mirror) and
    takes the nearest source texel (half-open edges, so a texel boundary is never sampled twice);
    tint = texel * colour / 255; layers blend with "over". The canvas grid is aligned to the first
    layer's top-left corner, so an unzoomed, unrotated layer is copied texel for texel. (korangar
    centres on (size - 1) / 2 instead: a half-pixel shift for even sizes, see the module doc.)
    An empty motion gives a (0, 0, 4) canvas and origin (0, 0)."""
    drawn = _drawn(spr, _motion(act, action_index, motion_index))
    if not drawn:
        return np.zeros((0, 0, 4), np.uint8), (0.0, 0.0)
    ext = union([q.extent() for _, q, _ in drawn])
    assert ext is not None
    first = drawn[0][1]
    ax = (first.cx - first.half_w) % 1.0  # the grid phase of the first layer's corner
    ay = (first.cy - first.half_h) % 1.0
    gx0 = ax + math.floor(ext[0] - ax + _EPS)
    gy0 = ay + math.floor(ext[1] - ay + _EPS)
    width = max(1, math.ceil(ext[2] - gx0 - _EPS))
    height = max(1, math.ceil(ext[3] - gy0 - _EPS))
    ox, oy = -gx0, -gy0
    acc = np.zeros((height, width, 4), np.float64)  # premultiplied RGB + alpha, 0..1
    for layer, quad, index in drawn:
        assert index is not None
        _paint(acc, spr.images[index], layer, quad, ox, oy)
    alpha = acc[..., 3]
    rgb = np.divide(acc[..., :3], alpha[..., None], out=np.zeros_like(acc[..., :3]),
                    where=alpha[..., None] > 0)  # fmt: skip
    out = np.empty((height, width, 4), np.uint8)
    out[..., :3] = np.clip(np.rint(rgb * 255.0), 0, 255)
    out[..., 3] = np.clip(np.rint(alpha * 255.0), 0, 255)
    out[out[..., 3] == 0] = 0
    return out, (float(ox), float(oy))


def _paint(
    acc: npt.NDArray[np.float64], image: RGBA, layer: Layer, quad: Quad, ox: float, oy: float
) -> None:
    th, tw = image.shape[:2]
    if th == 0 or tw == 0:
        return
    x0, y0, x1, y1 = quad.extent()
    i0, i1 = max(0, math.floor(x0 + ox)), min(acc.shape[1], math.ceil(x1 + ox))
    j0, j1 = max(0, math.floor(y0 + oy)), min(acc.shape[0], math.ceil(y1 + oy))
    if i0 >= i1 or j0 >= j1:
        return
    px = np.arange(i0, i1) + 0.5 - ox - quad.cx  # pixel centres relative to the quad centre
    py = np.arange(j0, j1) + 0.5 - oy - quad.cy
    dx, dy = np.meshgrid(px, py)
    lx = dx * quad.cos + dy * quad.sin  # the inverse rotation
    ly = -dx * quad.sin + dy * quad.cos
    u = (lx + quad.half_w) / (2.0 * quad.half_w)
    v = (ly + quad.half_h) / (2.0 * quad.half_h)
    inside = (u >= 0) & (u < 1) & (v >= 0) & (v < 1)
    if not inside.any():
        return
    tx = np.clip(np.floor(u * tw).astype(np.int64), 0, tw - 1)
    ty = np.clip(np.floor(v * th).astype(np.int64), 0, th - 1)
    if quad.mirror:
        tx = tw - 1 - tx
    texel = image[ty[inside], tx[inside]].astype(np.float64) / 255.0
    tint = np.asarray(layer.color, np.float64) / 255.0
    a = texel[:, 3] * tint[3]
    src = texel[:, :3] * tint[:3] * a[:, None]
    region = acc[j0:j1, i0:i1]
    dst = region[inside]
    dst[:, :3] = src + dst[:, :3] * (1.0 - a[:, None])
    dst[:, 3] = a + dst[:, 3] * (1.0 - a)
    region[inside] = dst


def mask_bbox(mask: npt.NDArray[np.bool_]) -> tuple[int, int, int, int] | None:
    """(x0, y0, x1, y1), the half-open pixel extent of a (h, w) mask; None when it is empty."""
    if mask.size == 0:
        return None
    cols, rows = np.flatnonzero(mask.any(axis=0)), np.flatnonzero(mask.any(axis=1))
    if not len(cols):
        return None
    return int(cols[0]), int(rows[0]), int(cols[-1]) + 1, int(rows[-1]) + 1


def opaque_bbox(rgba: RGBA) -> tuple[int, int, int, int] | None:
    """(x0, y0, x1, y1), half-open canvas pixels with alpha > 0; None when nothing is opaque."""
    return mask_bbox(rgba[..., 3] > 0)


def opaque_extent(spr: Spr, act: Act, action_index: int, motion_index: int) -> Box | None:
    """The opaque pixels' extent of one composed motion, sprite px around the anchor."""
    rgba, (ox, oy) = compose_frame(spr, act, action_index, motion_index)
    bb = opaque_bbox(rgba)
    if bb is None:
        return None
    return bb[0] - ox, bb[1] - oy, bb[2] - ox, bb[3] - oy
