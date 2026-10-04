"""predict_sprite: where an actor's sprite is drawn, how big, and which frame -- the billboard
render rule (Phase 3 M2, docs/phase3-plan.md §3).

PORTED (the rule, re-expressed in numpy; no code copied verbatim) from nmeylan/nostalro-client
@ 15b3029 (Apache-2.0, THIRD_PARTY.md):
  * lib/renderer/src/sprite_projection.rs:154-178 project_entity_screen: the anchor is the cell
    CENTRE at the GAT's height, projected; sprite_scale = perspective_scale(anchor) * zoom / 75;
  * lib/renderer/src/camera.rs:425-432 perspective_scale = proj[1][1] / clip.w * screen_h / 2, the
    screen pixels per world unit at the anchor's depth -- here f / z with f = (h/2) / tan(fov/2)
    and z the anchor's depth along the camera's forward axis (Camera.basis()); with GND zoom 10,
    k = 10 / 75 world units per sprite pixel (K_NOSTALRO);
  * lib/renderer/src/sprite.rs:939-956 build_clip_quad_scaled: every layer quad is then scaled
    about the anchor by that one factor -- the sprite stays screen-aligned and is scaled
    uniformly (no per-vertex perspective);
  * lib/formats/src/act.rs:568-570 the action index (group * 8 + camera-relative direction),
    act.rs:620-633 the walk cycle tied to DISTANCE walked (one frame per delay/24/7.4 cells),
    act.rs:641-679 one-shot actions (attack, hurt, die) that hold their last frame;
  * lib/game/src/entity.rs:1170-1178: a monster's action groups are idle 0, walk 1, attack 2,
    hurt 3, die 4.
Cross-checked against vE5li/korangar @ e14d320 (MIT, THIRD_PARTY.md):
  * korangar/src/world/animation/mod.rs:15-16,287-302: a camera-facing billboard (cameras/mod.rs
    billboard_matrix: the plane spanned by camera right and camera up, so every point of it has
    the anchor's depth -- the same uniform f/z scale) of frame px * SPRITE_SCALE 1.4 / TILE_SIZE 10
    world units: k = 0.14 (K_KORANGAR), its origin -offset.y + 0.5 px below the anchor;
  * the same monster action groups (mod.rs:58-65).
The clients DISAGREE on k (5 %; M4 measures it, docs/phase3-plan.md §5) and on idle timing:
korangar plays a frame per delay * 50 ms (or per delay * speed * 2/15 ms walking, or attack
duration / frames), nostalro per delay * 24 ms (act.rs:8). Nostalro's timing is the rule here; M4's
video decides.

OFFLINE ONLY (ADR-0007): the actor's cell, heading and action come from packets, so this makes
LABELS, checks and synthetic frames -- never a runtime input to the agent.
"""

import math
from dataclasses import dataclass, field
from enum import IntEnum
from pathlib import Path

import numpy as np
import numpy.typing as npt

from poring_dataset import gat as gatmod
from poring_dataset.camera import (
    CELL,
    GAT_DIR,
    Camera,
    displayed_direction,
    load_indoor_table,
    map_camera,
    map_key,
)
from poring_dataset.sprites import (
    FRAME_DELAY_UNIT_MS,
    Act,
    Box,
    Spr,
    compose_frame,
    mask_bbox,
    quad_extent,
    union,
)

K_NOSTALRO = 10.0 / 75.0  # sprite_projection.rs:175: GND zoom (10 world units per tile) / 75
K_KORANGAR = 1.4 / 10.0  # korangar world/animation/mod.rs:15-16: SPRITE_SCALE / TILE_SIZE
WALK_DELAY_UNITS_PER_CELL = 7.4  # act.rs:629-630: a walk frame lasts delay_units / 7.4 cells


class MonsterAction(IntEnum):
    """A monster's ACT action groups (nostalro entity.rs:1170-1178, korangar mod.rs:58-65)."""

    IDLE = 0
    WALK = 1
    ATTACK = 2
    HURT = 3
    DIE = 4


LOOPING = frozenset({MonsterAction.IDLE, MonsterAction.WALK})  # the rest play once and hold


@dataclass(frozen=True)
class Actor:
    """What the packets say about one actor at the moment drawn.

    ``cell``: map cell (x, y), fractional while walking (Walk.position_at). ``heading``: RO heading
    0..7 (0 = north, counter-clockwise). ``elapsed_ms``: time since the action started, None when
    unknown (an idle loop whose start we did not see). ``walked_cells``: distance walked since the
    walk started (WALK only; it drives the walk frame). ``duration_ms``: the whole action's play
    time when the packet gives one (an attack's motion time); else the ACT's own delays."""

    cell: tuple[float, float]
    heading: int
    action: int = MonsterAction.IDLE
    elapsed_ms: float | None = None
    walked_cells: float | None = None
    duration_ms: float | None = None


@dataclass(frozen=True)
class Scene:
    """The camera the client uses on this map (camera.map_camera: rotated and closer indoors),
    where it looks (the player's cell, fractional while walking) and the map's GAT, if extracted."""

    camera: Camera
    player: tuple[float, float]
    gat: gatmod.Gat | None = None


def load_scene(
    camera_json: dict[str, object],
    map_name: str,
    player: tuple[float, float],
    gat_dir: Path = GAT_DIR,
    *,
    indoor_table: frozenset[str] | None = None,
) -> Scene:
    """The Scene for a map, loaded the way camera.projector_for loads its projector: the fitted
    camera (indoor rule included) plus the map's GAT when it is extracted (else flat ground)."""
    table = load_indoor_table(gat_dir) if indoor_table is None else indoor_table
    cam = map_camera(camera_json, map_key(map_name), table)
    if cam is None:
        raise ValueError("the camera json has no fitted camera")
    path = gat_dir / f"{map_key(map_name)}.gat"
    grid = gatmod.parse(path.read_bytes()) if path.exists() else None
    return Scene(cam, (float(player[0]), float(player[1])), grid)


class SpriteSheet:
    """One species' ACT (+ SPR when readable), with per-motion extents cached.

    Without an SPR the box is the union of the layer QUADS (ACT 2.5 carries their sizes): the
    image extents, transparent margins included ("quad"). With it, the composed frame's opaque
    pixels ("opaque") and an optional mask."""

    def __init__(self, act: Act, spr: Spr | None = None) -> None:
        self.act, self.spr = act, spr
        self._extent: dict[tuple[int, int], Box | None] = {}
        self._alpha: dict[tuple[int, int], tuple[npt.NDArray[np.bool_], float, float]] = {}

    @property
    def box_kind(self) -> str:
        return "quad" if self.spr is None else "opaque"

    def motions(self, action_index: int) -> int:
        return len(self.act.actions[action_index])

    def alpha(self, action_index: int, motion: int) -> tuple[npt.NDArray[np.bool_], float, float]:
        """(opaque mask, ox, oy) of one composed motion (sprites.compose_frame); needs the SPR."""
        if self.spr is None:
            raise ValueError("no SPR: masks need the sprite pixels")
        key = (action_index, motion)
        if key not in self._alpha:
            rgba, (ox, oy) = compose_frame(self.spr, self.act, action_index, motion)
            self._alpha[key] = (rgba[..., 3] > 0, ox, oy)
        return self._alpha[key]

    def extent(self, action_index: int, motion: int) -> Box | None:
        """The motion's box in sprite px around the anchor (None: it draws nothing)."""
        key = (action_index, motion)
        if key not in self._extent:
            if self.spr is None:
                self._extent[key] = quad_extent(self.act, action_index, motion)
            else:
                mask, ox, oy = self.alpha(action_index, motion)
                bb = mask_bbox(mask)
                self._extent[key] = (
                    None if bb is None else (bb[0] - ox, bb[1] - oy, bb[2] - ox, bb[3] - oy)
                )
        return self._extent[key]

    def envelope(self, action_index: int) -> Box | None:
        """The union over every motion of the action: the box when the phase is unknown."""
        return union([self.extent(action_index, m) for m in range(self.motions(action_index))])


def motion_at(act: Act, action_index: int, actor: Actor) -> int | None:
    """The motion (frame) drawn, or None when the phase is unknown (-> the envelope).

    WALK: by distance walked (act.rs:620-633). IDLE: a loop at the ACT delay (24 ms units). ATTACK,
    HURT, DIE and anything else: played once from the action's start, at ``duration_ms`` / frames
    when given, else the ACT delay, then the last frame is held (act.rs:641-679)."""
    n = len(act.actions[action_index])
    if n == 0:
        return None
    units = act.delay_units(action_index)
    if actor.action == MonsterAction.WALK:
        if actor.walked_cells is None:
            return None
        if actor.walked_cells < 0:
            raise ValueError(f"walked_cells {actor.walked_cells} < 0")
        frame_cells = units / WALK_DELAY_UNITS_PER_CELL
        return int((actor.walked_cells % (frame_cells * n)) // frame_cells) % n
    if actor.elapsed_ms is None:
        return None
    if actor.elapsed_ms < 0:
        raise ValueError(f"elapsed_ms {actor.elapsed_ms} < 0")
    if actor.action == MonsterAction.IDLE:
        return int(actor.elapsed_ms // (units * FRAME_DELAY_UNIT_MS)) % n
    per_frame = actor.duration_ms / n if actor.duration_ms else units * FRAME_DELAY_UNIT_MS
    return min(int(actor.elapsed_ms // per_frame), n - 1)


@dataclass(frozen=True)
class SpritePrediction:
    """Where the client draws one actor (game-region pixels, the client area the camera spans)."""

    box: Box  # x0, y0, x1, y1
    anchor_px: tuple[float, float]  # the actor's feet: the cell centre at GAT height, projected
    scale: float  # screen px per sprite px = f / z * k
    depth: float  # z, world units along the camera's forward axis
    action: int  # the action group (MonsterAction)
    direction: int  # sprite direction after the camera rotation (camera.SPRITE_DIRECTIONS)
    action_index: int  # the ACT action drawn = group * 8 + direction
    motion: int | None  # the frame; None when phase_known is False
    phase_known: bool  # False: ``box`` is the ENVELOPE over the action's frames
    box_kind: str  # "opaque" (SPR pixels) or "quad" (ACT layer quads; no SPR)
    mask: npt.NDArray[np.bool_] | None = field(default=None, compare=False)
    mask_origin: tuple[int, int] | None = None  # the mask's top-left pixel (game region)


def anchor_and_depth(scene: Scene, cell: tuple[float, float]) -> tuple[tuple[float, float], float]:
    """The actor's anchor in pixels and its depth z. The projection is the one Phase 2 fitted
    (camera.projector_for's camera+gat path): offsets from the player in cells, altitude relative
    to the player's cell; for an integer player cell the result is identical."""
    cam = scene.camera
    px, py = scene.player
    offset = np.array([[cell[0] - px, cell[1] - py]], dtype=float)
    alt = np.zeros(1)
    if scene.gat is not None:
        origin = (int(math.floor(px)), int(math.floor(py)))
        pts = np.array([[cell[0] - origin[0], cell[1] - origin[1]],
                        [px - origin[0], py - origin[1]]], dtype=float)  # fmt: skip
        rel = scene.gat.relative_altitude(origin, pts)
        alt = np.array([rel[0] - rel[1]])
    ((u, v),) = cam.project(offset, alt)
    eye, _right, _up, forward = cam.basis()
    world = np.array([offset[0, 0] * CELL, alt[0], offset[0, 1] * CELL])
    z = float((world - eye) @ forward)
    return (float(u), float(v)), z


def focal_px(cam: Camera) -> float:
    """f: screen px per world unit at depth 1 (camera.rs perspective_scale: proj[1][1] * h/2)."""
    return (cam.height / 2.0) / math.tan(cam.fov / 2.0)


def predict_sprite(
    actor: Actor,
    sheet: SpriteSheet,
    scene: Scene,
    k: float = K_NOSTALRO,
    *,
    with_mask: bool = False,
) -> SpritePrediction | None:
    """The billboard rule for one actor: None when its anchor is behind the camera or the action
    draws nothing. ``k``: world units per sprite pixel (K_NOSTALRO or K_KORANGAR until M4 measures
    it). ``with_mask``: also the opaque pixels on screen (needs the SPR)."""
    anchor, z = anchor_and_depth(scene, actor.cell)
    if z <= 0:
        return None
    scale = focal_px(scene.camera) / z * k
    direction = displayed_direction(int(actor.heading) % 8, scene.camera.yaw)
    action_index = sheet.act.action_index(int(actor.action), direction)
    motion = motion_at(sheet.act, action_index, actor)
    frames = [motion] if motion is not None else list(range(sheet.motions(action_index)))
    extent = union([sheet.extent(action_index, m) for m in frames])
    if extent is None:
        return None
    ax, ay = anchor
    box = (ax + scale * extent[0], ay + scale * extent[1],
           ax + scale * extent[2], ay + scale * extent[3])  # fmt: skip
    mask, mask_origin = None, None
    if with_mask:
        mask, mask_origin = _screen_mask(sheet, action_index, frames, anchor, scale, box)
    return SpritePrediction(
        box, anchor, scale, z, int(actor.action), direction, action_index, motion,
        motion is not None, sheet.box_kind, mask, mask_origin,
    )  # fmt: skip


def _screen_mask(
    sheet: SpriteSheet,
    action_index: int,
    frames: list[int],
    anchor: tuple[float, float],
    scale: float,
    box: Box,
) -> tuple[npt.NDArray[np.bool_], tuple[int, int]]:
    """The opaque pixels on screen over the box's pixel window: each screen pixel centre mapped back
    to sprite px (/ scale about the anchor), nearest canvas pixel; the union over ``frames``."""
    i0, j0 = math.floor(box[0]), math.floor(box[1])
    i1, j1 = math.ceil(box[2]), math.ceil(box[3])
    sx = (np.arange(i0, i1) + 0.5 - anchor[0]) / scale
    sy = (np.arange(j0, j1) + 0.5 - anchor[1]) / scale
    out = np.zeros((j1 - j0, i1 - i0), bool)
    for m in frames:
        alpha, ox, oy = sheet.alpha(action_index, m)
        if not alpha.size:
            continue
        cx = np.floor(sx + ox).astype(np.int64)
        cy = np.floor(sy + oy).astype(np.int64)
        okx = (cx >= 0) & (cx < alpha.shape[1])
        oky = (cy >= 0) & (cy < alpha.shape[0])
        hit = np.zeros_like(out)
        hit[np.ix_(oky, okx)] = alpha[np.ix_(cy[oky], cx[okx])]
        out |= hit
    return out, (i0, j0)
