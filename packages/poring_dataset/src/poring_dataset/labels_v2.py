"""Labels v2 (docs/planning/labels-v2-plan.md, PROPOSED; docs/planning/labels-v2.md, Batt
2026-10-09): the v1 unit classes, plus town NPCs PER SPRITE, a ``warp`` class from the L3 warp
cells confirmed by the packets, and HARD NEGATIVES (the dialog cut-in, decorations) verified
against the packets.

Everything here is pure and offline (ADR-0007): the packets' world state (``timeline.FrameWorld``)
and the camera model (``render.Scene``) make labels; nothing here is a runtime input to the agent.

The class set (``V2_CLASSES``):
- ``player`` 0, ``monster`` 1, ``npc`` 2: v1's ids, unchanged (v1's weights fine-tune into v2).
  ``npc`` is now labelled PER SPRITE (each NPC's job id is carried; its box comes from its own
  sprite, or a measured extent, never v0's 34 x 74 constant without saying so).
- ``warp`` 3: the ONE new head. A portal is labelled only where L3 lists a warp AND the packets
  show the drawn portal (objtype 6, job 45) at that cell: L3 alone cannot tell a drawn portal
  from a hidden one (job 139) or from one outside the server's view, and the packets alone are not
  L3 (Batt 2026-10-09 ~13:15: "auto-labelled from L3").
- Background, never a head: the NPC dialog's cut-in and decorations (torches, flames). They are
  regions VERIFIED to hold no unit (``verify_region``), carried as metadata for hard-negative
  mining and the phantom rates of the pre-registration.

FAIL CLOSED: a frame the rules cannot label completely is EXCLUDED from training (``Frame.excluded``
says why), never trained with a hole in it. An unlabelled drawn object is a background example:
  * ``npc_unsized:<job>``: an NPC on screen with neither a sprite sheet nor a measured extent;
  * ``portal_unconfirmed:<map>:<x>,<y>``: a drawn portal on screen that L3 does not list (or L3
    lacks the map);
  * ``l3_warp_unseen:<x>,<y>``: an L3 warp on screen, within the server's view range, with NO
    portal entity (neither job 45 nor 139) at its cell: the packets window is incomplete;
  * ``cutin_unmeasured`` / ``cutin_region_unavailable``: a dialog open whose cut-in is not measured,
    or whose measured region the caller did not load (it lives in scripts/ui_mask.py).
"""

from __future__ import annotations

import math
import warnings
from collections import Counter, deque
from collections.abc import Callable, Collection, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import numpy.typing as npt

from poring_dataset.camera import CELL, Camera, map_key
from poring_dataset.labels import BOX_PX, MAX_UI_COVER, WARP_PORTAL_CLASS, drawn
from poring_dataset.render import (
    Actor,
    MonsterAction,
    Scene,
    SpriteSheet,
    focal_px,
    predict_sprite,
)
from poring_dataset.timeline import EntityState, FrameWorld
from poring_dataset.ui_layout import UI_RECTS, covered_fraction

Rect = tuple[float, float, float, float]  # x0, y0, x1, y1, game-region px
Extent = tuple[float, float, float, float]  # x0, y0, x1, y1 around an anchor (units per caller)

V2_CLASSES: dict[str, int] = {"player": 0, "monster": 1, "npc": 2, "warp": 3}
NEW_HEADS = ("warp",)
BACKGROUND_KINDS = ("cutin", "decoration")
PLAYER_OBJTYPE, MONSTER_OBJTYPE, NPC_OBJTYPE = 0, 5, 6
HIDDEN_PORTAL_CLASS = 139  # rAthena HIDDEN_WARP_CLASS: sent, never drawn
# rAthena conf/battle/client.conf area_size (default 14): the server sends units within this many
# cells of the player, so a warp farther away is not drawn even when its cell is on screen.
AREA_CELLS = 14
# The camera model's click-fit error (Phase 2: median 11 px, p95 19 px): a candidate region closer
# than this to a unit's projected box is NOT background (the conservative side).
VERIFY_MARGIN_PX = 20.0


# --- the label --------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class V2Label:
    cls: str
    x0: float
    y0: float
    x1: float
    y1: float
    gid: int | None = None
    job: int | None = None  # the sprite (NPC job / monster species), None for a warp
    kind: str = "v1"  # sprite_opaque | sprite_quad | measured | unsized | portal | v1 | ...
    source: str = "packets"  # packets | l3+packets

    @property
    def box(self) -> Rect:
        return (self.x0, self.y0, self.x1, self.y1)

    def yolo(self, width: int, height: int) -> str:
        cx, cy = (self.x0 + self.x1) / 2 / width, (self.y0 + self.y1) / 2 / height
        w, h = (self.x1 - self.x0) / width, (self.y1 - self.y0) / height
        return f"{V2_CLASSES[self.cls]} {cx:.6f} {cy:.6f} {w:.6f} {h:.6f}"


def clip_rect(box: Rect, size: tuple[int, int]) -> Rect:
    w, h = size
    return (max(box[0], 0.0), max(box[1], 0.0), min(box[2], float(w)), min(box[3], float(h)))


def on_screen(box: Rect, size: tuple[int, int]) -> bool:
    """v1's rule: at least half the box's width and height inside the game region."""
    c = clip_rect(box, size)
    return c[2] - c[0] >= (box[2] - box[0]) / 2 and c[3] - c[1] >= (box[3] - box[1]) / 2


def overlaps(a: Rect, b: Rect, margin: float = 0.0) -> bool:
    return not (a[2] < b[0] - margin or a[0] > b[2] + margin
                or a[3] < b[1] - margin or a[1] > b[3] + margin)  # fmt: skip


def inside_share(box: Rect, rect: Rect) -> float:
    """The share of ``box`` inside ``rect`` (scripts/ui_mask.py's rule, repeated here: a package
    never imports scripts/; 0 for an empty box)."""
    area = max(0.0, box[2] - box[0]) * max(0.0, box[3] - box[1])
    if area <= 0:
        return 0.0
    iw = max(0.0, min(box[2], rect[2]) - max(box[0], rect[0]))
    ih = max(0.0, min(box[3], rect[3]) - max(box[1], rect[1]))
    return iw * ih / area


# --- geometry: altitude, projection of a cell, the inverse onto the ground ------------------------


def relative_altitude(scene: Scene, cell: tuple[float, float]) -> float:
    """The cell's ground altitude relative to the player's (world units, up positive), as
    render.anchor_and_depth computes it; 0 without a GAT (flat ground)."""
    if scene.gat is None:
        return 0.0
    px, py = scene.player
    origin = (int(math.floor(px)), int(math.floor(py)))
    pts = np.array([[cell[0] - origin[0], cell[1] - origin[1]],
                    [px - origin[0], py - origin[1]]], dtype=float)  # fmt: skip
    rel = scene.gat.relative_altitude(origin, pts)
    return float(rel[0] - rel[1])


def project_cell(scene: Scene, cell: tuple[float, float]) -> tuple[tuple[float, float], float]:
    """(the cell's anchor in px, its depth z): render.anchor_and_depth's projection."""
    cam = scene.camera
    px, py = scene.player
    alt = relative_altitude(scene, cell)
    offset = np.array([[cell[0] - px, cell[1] - py]], dtype=float)
    ((u, v),) = cam.project(offset, np.array([alt]))
    eye, _r, _u, forward = cam.basis()
    world = np.array([offset[0, 0] * CELL, alt, offset[0, 1] * CELL])
    return (float(u), float(v)), float((world - eye) @ forward)


def px_per_world(scene: Scene, z: float) -> float:
    """Screen px per world unit at depth ``z`` (f / z): what scales a fixed world-size object."""
    return focal_px(scene.camera) / z


def ground_offset(
    cam: Camera, u: float, v: float, altitude: float = 0.0
) -> tuple[float, float] | None:
    """The INVERSE of Camera.project on the plane at ``altitude`` (world units, relative to the
    player's ground): the cell offset (dx, dy) from the player whose ground point is drawn at pixel
    (u, v); None when that pixel's ray never meets the plane in front of the camera."""
    eye, right, up, forward = cam.basis()
    f = (cam.height / 2.0) / math.tan(cam.fov / 2.0)
    d = forward + ((u - cam.cx) / f) * right + ((cam.cy - v) / f) * up
    if abs(float(d[1])) < 1e-12:
        return None
    t = (altitude - float(eye[1])) / float(d[1])
    if t <= 0:
        return None
    p = eye + t * d
    return float(p[0]) / CELL, float(p[2]) / CELL


# --- warps: L3 cells confirmed by the packets -----------------------------------------------------


@dataclass(frozen=True, slots=True)
class WarpCell:
    """One L3 warp (data/kb/route.json "warps"): the portal's cell and its trigger span."""

    x: int
    y: int
    span_x: int = 0
    span_y: int = 0

    def area_contains(self, cx: float, cy: float) -> bool:
        return abs(cx - self.x) <= self.span_x and abs(cy - self.y) <= self.span_y


def l3_warps(route: Mapping[str, Any], map_name: str | None) -> tuple[WarpCell, ...] | None:
    """A map's L3 warps; None when route.json does not list the map (the caller fails closed)."""
    if not map_name:
        return None
    warps = route.get("warps") or {}
    rows = warps.get(map_key(map_name))
    if rows is None:
        return None
    return tuple(WarpCell(int(w["x"]), int(w["y"]), int(w.get("span_x", 0)),
                          int(w.get("span_y", 0))) for w in rows)  # fmt: skip


@dataclass(frozen=True, slots=True)
class PortalShape:
    """The drawn portal: a RING on the ground around its cell centre (radius, world units; 5 per
    cell) and, optionally, a glow up to ``height`` above it. Its box is the bounding box of the
    projected ring at the ground and at ``height``: the camera's pitch and depth come with it (the
    ring is a ground circle, so the indoor camera's rotation leaves its outline unchanged)."""

    radius: float
    height: float
    measured: bool
    source: str


# PROVISIONAL (2026-10-09, Claude's reading of the aligned crops `labels_v2.py warp-measure` wrote
# from the banked RDP frames, 19 crops of 3 VISIBLE portals: iz_dun00 (168,173) x 12 at the default
# camera, alberta_in (78,44) x 5 and (64,31) x 2 at the indoor camera): the ring's outer edge is a
# ground circle of ~7 world units (~1.4 cells), the ellipse's height / width ~0.7 = sin(pitch).
# The sparkles above it are sparse and not boxed. A person confirms on the same crops before any
# cache is built (labels-v2-plan.md section 1.3).
PORTAL_PROVISIONAL = PortalShape(
    radius=7.0, height=0.0, measured=False, source="hand-read: 19 aligned crops, 3 visible portals"
)
RING_POINTS = 24


def portal_box(scene: Scene, cell: tuple[float, float], shape: PortalShape) -> Rect | None:
    """The projected ring's bounding box (None when any of it is behind the camera)."""
    cam = scene.camera
    px, py = scene.player
    alt = relative_altitude(scene, cell)
    ang = np.linspace(0.0, 2 * math.pi, RING_POINTS, endpoint=False)
    r = shape.radius / CELL
    dx = cell[0] - px + r * np.cos(ang)
    dy = cell[1] - py + r * np.sin(ang)
    heights = (0.0, shape.height) if shape.height else (0.0,)
    offs = np.concatenate([np.c_[dx, dy] for _ in heights])
    alts = np.concatenate([np.full(RING_POINTS, alt + h) for h in heights])
    eye, _r, _u, forward = cam.basis()
    world = np.c_[offs[:, 0] * CELL, alts, offs[:, 1] * CELL]
    if float(((world - eye) @ forward).min()) <= 0:
        return None
    pts = cam.project(offs, alts)
    return (float(pts[:, 0].min()), float(pts[:, 1].min()),
            float(pts[:, 0].max()), float(pts[:, 1].max()))  # fmt: skip


def warp_key(map_name: str | None, x: float, y: float) -> str:
    return f"{map_key(map_name or '')}:{round(x)},{round(y)}"


# A warp cell's visibility from the default camera, decided by a PERSON on the aligned crops
# (`labels_v2.py warp-measure` writes them): "visible" (the full ring on every crop), "occluded"
# (map geometry hides it on every crop: prontera's doors under their roofs), "partial" (a wall
# cuts it on some crops). The table is local (client pixels + rAthena cells; never committed).
VISIBILITY = ("visible", "occluded", "partial")


def portal_entities(frame: FrameWorld) -> list[EntityState]:
    """The packets' portals the client DRAWS: objtype NPC, job 45, no invisibility option."""
    return [
        e for e in frame.entities
        if e.objtype == NPC_OBJTYPE and e.job == WARP_PORTAL_CLASS and not e.hidden
    ]  # fmt: skip


@dataclass(frozen=True)
class WarpResult:
    labels: tuple[V2Label, ...] = ()
    covered: tuple[V2Label, ...] = ()  # on screen, but mostly behind the UI: not labelled
    occluded: tuple[V2Label, ...] = ()  # on screen, hidden by map geometry (the table): no label
    l3_only: tuple[WarpCell, ...] = ()  # L3 lists it, no DRAWN portal (job 45) at its cell
    excluded: tuple[str, ...] = ()


def warp_labels(
    frame: FrameWorld,
    scene: Scene,
    size: tuple[int, int],
    warps: Sequence[WarpCell] | None,
    *,
    visibility: Mapping[str, str] | None = None,
    shape: PortalShape = PORTAL_PROVISIONAL,
    ui_rects: tuple[tuple[int, int, int, int], ...] = UI_RECTS,
    match_cells: int = 0,
    area_cells: int = AREA_CELLS,
) -> WarpResult:
    """Each drawn portal (packets) at an L3 warp cell (within ``match_cells``) that the visibility
    table calls "visible" -> a ``warp`` box. FAIL CLOSED, the frame is EXCLUDED when on screen:
    - a drawn portal L3 does not list (``portal_unconfirmed:<map>:<x>,<y>``);
    - a confirmed portal whose cell is "partial" or not in the table
      (``warp_partial:<key>`` / ``warp_visibility_unknown:<key>``);
    - an L3 warp within the server's view with NO portal entity (job 45 or 139) at its cell
      (``l3_warp_unseen:<x>,<y>``: the packets window is incomplete).
    An "occluded" one gets no label (what the frame shows there is the roof or the wall)."""
    if frame.self_pos is None:
        return WarpResult()
    px, py = frame.self_pos
    table = visibility if visibility is not None else {}
    labels: list[V2Label] = []
    covered: list[V2Label] = []
    occluded: list[V2Label] = []
    excluded: list[str] = []
    matched: set[WarpCell] = set()
    for ent in portal_entities(frame):
        hit = next(
            (w for w in (warps or ())
             if abs(ent.x - w.x) <= match_cells and abs(ent.y - w.y) <= match_cells),
            None,
        )  # fmt: skip
        if hit is not None:
            matched.add(hit)
        box = portal_box(scene, (ent.x, ent.y), shape)
        if box is None or not on_screen(box, size):
            continue
        if hit is None:
            excluded.append("portal_unconfirmed:" + warp_key(frame.map, ent.x, ent.y))
            continue
        lab = V2Label("warp", *clip_rect(box, size), gid=ent.gid, job=None, kind="portal",
                      source="l3+packets")  # fmt: skip
        if covered_fraction(box, ui_rects) >= MAX_UI_COVER:
            covered.append(lab)
            continue
        key = warp_key(frame.map, ent.x, ent.y)
        seen_as = table.get(key)
        if seen_as == "visible":
            labels.append(lab)
        elif seen_as == "occluded":
            occluded.append(lab)
        else:
            excluded.append(f"warp_{'partial' if seen_as == 'partial' else 'visibility_unknown'}"
                            f":{key}")  # fmt: skip
    sent = {
        (round(e.x), round(e.y)) for e in frame.entities
        if e.objtype == NPC_OBJTYPE and e.job in (WARP_PORTAL_CLASS, HIDDEN_PORTAL_CLASS)
    }  # fmt: skip
    l3_only: list[WarpCell] = []
    for w in warps or ():
        if w in matched:
            continue
        l3_only.append(w)
        near = abs(w.x - px) <= area_cells and abs(w.y - py) <= area_cells
        seen = any(abs(sx - w.x) <= match_cells and abs(sy - w.y) <= match_cells
                   for sx, sy in sent)  # fmt: skip
        box = portal_box(scene, (float(w.x), float(w.y)), shape)
        if near and not seen and box is not None and on_screen(box, size):
            excluded.append(f"l3_warp_unseen:{w.x},{w.y}")
    return WarpResult(tuple(labels), tuple(covered), tuple(occluded), tuple(l3_only),
                      tuple(excluded))  # fmt: skip


# --- NPCs per sprite ------------------------------------------------------------------------------

# job -> its sprite sheet (client data, decoded into /dev/shm at run time; never committed)
NpcSheet = Callable[[int], SpriteSheet | None]


@dataclass(frozen=True)
class NpcResult:
    labels: tuple[V2Label, ...] = ()
    covered: tuple[V2Label, ...] = ()  # on screen, but mostly behind the UI: not labelled
    excluded: tuple[str, ...] = ()


def drawn_npcs(frame: FrameWorld, exclude_gids: Iterable[int] = ()) -> list[EntityState]:
    """NPC sprites the client draws: objtype 6, a drawn class (not 111 / 139 / 32767), not the
    portal effect (45: the ``warp`` class), no invisibility option."""
    skip = set(exclude_gids)
    return [e for e in frame.entities
            if e.objtype == NPC_OBJTYPE and drawn(e.objtype, e.job) and not e.hidden
            and e.gid not in skip]  # fmt: skip


def npc_labels(
    frame: FrameWorld,
    scene: Scene,
    size: tuple[int, int],
    *,
    sheet: NpcSheet,
    measured: Mapping[int, Extent],
    k: float,
    ui_rects: tuple[tuple[int, int, int, int], ...] = UI_RECTS,
    exclude_gids: Iterable[int] = (),
) -> NpcResult:
    """Each drawn NPC at its packet cell, its box from:
    1. its own sprite (``sheet(job)``): predict_sprite's idle envelope at its heading -- the v1
       monster path (kind ``sprite_opaque`` / ``sprite_quad``);
    2. else a MEASURED native extent (``measured[job]``, sprite px around the feet, scaled by
       f / z x k like a sprite; kind ``measured``);
    3. else v0's 34 x 74 at the feet, kind ``unsized``, and the frame is EXCLUDED
       (``npc_unsized:<job>``): a big sprite (a guild flag is ~95 x 150 px, npc-click-test.md 7)
       would be half background."""
    if frame.self_pos is None:
        return NpcResult()
    labels: list[V2Label] = []
    covered: list[V2Label] = []
    excluded: list[str] = []
    for ent in drawn_npcs(frame, exclude_gids):
        sh = sheet(ent.job)
        box: Rect | None
        if sh is not None:
            pred = predict_sprite(Actor((float(ent.x), float(ent.y)), int(ent.heading or 0) % 8,
                                        MonsterAction.IDLE), sh, scene, k)  # fmt: skip
            if pred is None:
                continue  # the client draws nothing for it
            box, kind = pred.box, f"sprite_{pred.box_kind}"
        else:
            (u, v), z = project_cell(scene, (ent.x, ent.y))
            if z <= 0:
                continue
            if ent.job in measured:
                s = px_per_world(scene, z) * k
                e = measured[ent.job]
                box, kind = (u + s * e[0], v + s * e[1], u + s * e[2], v + s * e[3]), "measured"
            else:
                w, h = BOX_PX["npc"]
                box, kind = (u - w / 2, v - h, u + w / 2, v), "unsized"
        if not on_screen(box, size):
            continue
        lab = V2Label("npc", *clip_rect(box, size), gid=ent.gid, job=ent.job, kind=kind)
        if covered_fraction(box, ui_rects) >= MAX_UI_COVER:
            covered.append(lab)
            continue
        labels.append(lab)
        if kind == "unsized":
            excluded.append(f"npc_unsized:{ent.job}")
    return NpcResult(tuple(labels), tuple(covered), tuple(excluded))


# --- the cut-in: a dynamic UI region, and a hard negative -----------------------------------------

# What is known about one NPC's cut-in: a measured region (client px), or None = measured to show
# none (prt_church's Garnet and Henson, ui_mask.py 2026-10-09). An NPC missing from the table is
# UNMEASURED.
CutinTable = Mapping[str, Rect | None]


def npc_key(map_name: str | None, ent: EntityState) -> str:
    """An NPC's identity WITHOUT its name (names are server text, never committed): map, job,
    cell."""
    return f"{map_key(map_name or '')}:{ent.job}:{round(ent.x)},{round(ent.y)}"


@dataclass(frozen=True)
class Cutin:
    """The cut-in shown on a frame (per the packets' dialog state), or why it is unknown."""

    open: bool  # a dialog or menu is open (packets)
    rect: Rect | None = None  # the region shown (None: no cut-in, or unknown -> see excluded)
    npc: str | None = None
    excluded: tuple[str, ...] = ()


def cutin_for(
    dialog_open: bool,
    npc: str | None,
    table: CutinTable,
    *,
    unavailable: Collection[str] = (),
) -> Cutin:
    """The cut-in of an open dialog with NPC ``npc`` (npc_key): its measured region, none, or an
    exclusion: an unmeasured NPC (``cutin_unmeasured``), or an NPC in ``unavailable`` -- measured,
    but its region is not loaded (scripts/ui_mask.py holds the numbers, this package only the
    interface; ``cutin_region_unavailable``)."""
    if not dialog_open:
        return Cutin(False)
    if npc is not None and npc in unavailable:
        return Cutin(True, None, npc, ("cutin_region_unavailable",))
    if npc is None or npc not in table:
        return Cutin(True, None, npc, ("cutin_unmeasured",))
    return Cutin(True, table[npc], npc)


# --- verification: is a region free of every unit? ------------------------------------------------


@dataclass(frozen=True, slots=True)
class Verdict:
    accepted: bool
    reason: str  # background | unit | warp | ui | cutin | off_screen | excluded
    against: tuple[int, ...] = ()  # the gids it overlapped


def intersect(a: Rect, b: Rect) -> Rect | None:
    """The overlap of two rects (x0, y0, x1, y1), or None when they do not overlap."""
    x0, y0, x1, y1 = max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3])
    return (x0, y0, x1, y1) if x0 < x1 and y0 < y1 else None


def verify_region(
    region: Rect,
    units: Sequence[V2Label],
    size: tuple[int, int],
    *,
    margin: float = VERIFY_MARGIN_PX,
    ui_rects: tuple[tuple[int, int, int, int], ...] = UI_RECTS,
    cutin: Rect | None = None,
    allow_cutin: bool = False,
) -> Verdict:
    """labels-v2.md section 2: a background region is accepted only when NO unit's projected box
    (monster, NPC, player, portal; labelled OR hidden behind the UI) overlaps it, grown by
    ``margin`` (the projection's p95 error). ``units``: every projected box of the frame,
    UI-covered ones included. A region mostly under a static UI window is UI, not scenery; one
    inside the shown cut-in is the cut-in (accepted as such only with ``allow_cutin``)."""
    if not on_screen(region, size):
        return Verdict(False, "off_screen")
    hits = tuple(u.gid if u.gid is not None else -1 for u in units
                 if overlaps(region, u.box, margin))  # fmt: skip
    if hits:
        kinds = {u.cls for u in units if overlaps(region, u.box, margin)}
        return Verdict(False, "warp" if kinds == {"warp"} else "unit", hits)
    if covered_fraction(region, ui_rects) >= MAX_UI_COVER:
        return Verdict(False, "ui")
    if cutin is not None and inside_share(region, cutin) >= 0.5:
        return Verdict(allow_cutin, "cutin")
    return Verdict(True, "background")


# --- our own character: on screen in RDP frames, never labelled by v1 ---------------------------


def self_label(frame: FrameWorld, scene: Scene) -> V2Label | None:
    """Our own character's box: v0's player box at the camera target (our feet). v1 never labels
    it (the S2 sessions' GM played hidden); the RDP runs' GM is VISIBLE, so a v2 frame carries it
    at least as SHADOW: a background region must not touch it (the HUD boxed it, 2026-10-09).
    DECIDED (Batt 2026-10-09 ~19:30): it is LABELLED ``player`` (kind "self"); hidden behind the UI
    or the cut-in it goes to shadow like any other unit (``assemble``)."""
    if frame.self_pos is None:
        return None
    (u, v), z = project_cell(scene, frame.self_pos)
    if z <= 0:
        return None
    w, h = BOX_PX["player"]
    return V2Label("player", u - w / 2, v - h, u + w / 2, v, gid=frame.aid, kind="self")


# --- one frame, assembled -------------------------------------------------------------------------


@dataclass(frozen=True)
class Frame:
    t_ns: int
    map: str | None
    labels: tuple[V2Label, ...]  # what a training frame carries (YOLO lines)
    shadow: tuple[V2Label, ...]  # on screen but hidden by UI / the cut-in: verification only
    excluded: tuple[str, ...]  # non-empty: NOT a training frame (why)
    cutin: Cutin = field(default_factory=lambda: Cutin(False))
    l3_only: tuple[WarpCell, ...] = ()

    @property
    def trainable(self) -> bool:
        return not self.excluded

    @property
    def projected(self) -> tuple[V2Label, ...]:
        """Every unit box of the frame, labelled or hidden (what a background must not touch)."""
        return self.labels + self.shadow


def from_v1(boxes: Iterable[Mapping[str, Any]], jobs: Mapping[int, int]) -> list[V2Label]:
    """qa_export.Labeler.boxes() dicts (v1) -> V2Labels; NPC boxes are DROPPED (v2 redoes them per
    sprite). ``jobs``: gid -> job from the frame's world state."""
    out = []
    for b in boxes:
        if b["cls"] == "npc":
            continue
        gid = int(b["gid"])
        out.append(V2Label(str(b["cls"]), float(b["x1"]), float(b["y1"]), float(b["x2"]),
                           float(b["y2"]), gid=gid, job=jobs.get(gid),
                           kind=str(b.get("kind") or "v1")))  # fmt: skip
    return out


def assemble(
    t_ns: int,
    frame: FrameWorld,
    units_v1: Sequence[V2Label],
    npcs: NpcResult,
    warps: WarpResult,
    cutin: Cutin,
    hidden_v1: Sequence[V2Label] = (),
    extra_excluded: Sequence[str] = (),
) -> Frame:
    """One v2 frame: v1's players and monsters, the NPCs per sprite, the portals; every box at least
    half inside a SHOWN cut-in is moved to ``shadow`` (hidden by the UI, as v1 does for the fixed
    windows). ``hidden_v1``: v1's units its own rules dropped (``labels_for(keep_all=True)``'s
    kind "dropped": behind the fixed windows, or mostly off screen) -- shadow, for verification."""
    labels: list[V2Label] = []
    # occluded portals too: their sparkles can show above a roof (prt_in, 2026-10-09 crops)
    shadow: list[V2Label] = [*npcs.covered, *warps.covered, *warps.occluded, *hidden_v1]
    for lab in [*units_v1, *npcs.labels, *warps.labels]:
        if cutin.rect is not None and inside_share(lab.box, cutin.rect) >= MAX_UI_COVER:
            shadow.append(lab)
        else:
            labels.append(lab)
    excluded = (*extra_excluded, *npcs.excluded, *warps.excluded, *cutin.excluded)
    # an unsized NPC hidden behind the cut-in no longer leaves a hole: re-derive from what is kept
    kept_unsized = {f"npc_unsized:{lab.job}" for lab in labels if lab.kind == "unsized"}
    excluded = tuple(e for e in excluded if not e.startswith("npc_unsized:") or e in kept_unsized)
    return Frame(t_ns, frame.map, tuple(labels), tuple(shadow), tuple(dict.fromkeys(excluded)),
                 cutin, warps.l3_only)  # fmt: skip


# --- our own character dead: not a training frame -----------------------------------------------


def self_dead_spans(
    events: Iterable[Mapping[str, Any]], aid: int | None, end_ns: int | None = None
) -> list[tuple[int, int]]:
    """Spans (host ns) where OUR character lay dead, from the packets: our own entity_vanish with
    reason 1 (died) starts one; our next map_change (a warp or a respawn) or a GM-command HP raise
    (stat_change "hp" flagged gm_command: @alive / @heal) ends it, else ``end_ns``. A dead GM lies
    on the floor under the client's restart window: not a training frame. The positive case: the
    2026-10-09 12:38 iz_dun00 held-out run, snapshot 003 (the restart window on screen) lies in the
    span of our vanish at 266007.89 s, which its @warp at 266338.58 s ends."""
    if aid is None:
        return []
    start: int | None = None
    spans: list[tuple[int, int]] = []
    for e in sorted(events, key=lambda e: int(e["t_mono_ns"])):
        t, typ = int(e["t_mono_ns"]), e.get("type")
        if start is None:
            if typ == "entity_vanish" and int(e.get("gid") or -1) == aid and e.get("reason") == 1:
                start = t
        elif typ == "map_change" or (
            typ == "stat_change" and e.get("name") == "hp" and bool(e.get("gm_command"))
            and int(e.get("value") or 0) > 0
        ):  # fmt: skip
            spans.append((start, t))
            start = None
    if start is not None:
        spans.append((start, end_ns if end_ns is not None else 1 << 62))
    return spans


# --- candidates (detector phantoms) -> verified sites ---------------------------------------------


@dataclass(frozen=True, slots=True)
class Candidate:
    """A detector box from a log: the walk runs' detections.jsonl, or the HUD scene log."""

    t_ns: int
    box: Rect
    cls: str
    conf: float | None
    source: str


# A decoration site becomes a hard-negative SOURCE only with this many accepted sightings, seen
# from this many distinct positions of ours (PROPOSED, labels-v2-plan.md section 1.4): one
# sighting can be a tracker's drift or a monster the projection missed by more than the margin.
SITE_MIN_SIGHTINGS = 10
SITE_MIN_POSITIONS = 3


@dataclass(frozen=True, slots=True)
class Sighting:
    map: str
    x: float  # the ground cell the box's foot back-projects to
    y: float
    conf: float
    wh: tuple[float, float]  # the box's size, px
    seen_from: tuple[int, int]  # our cell then


@dataclass(frozen=True, slots=True)
class Site:
    """A static decoration seen as a phantom: the ground cell its box's foot back-projects to (for
    wall-mounted scenery an approximation: the camera only translates and its FOV is 15 degrees,
    so it re-projects onto what was seen -- the iz_dun00 torch, 35 sightings, 2026-10-09)."""

    map: str
    x: float
    y: float
    sightings: tuple[Sighting, ...]

    @property
    def n(self) -> int:
        return len(self.sightings)

    @property
    def positions(self) -> int:
        return len({s.seen_from for s in self.sightings})

    @property
    def accepted(self) -> bool:
        return self.n >= SITE_MIN_SIGHTINGS and self.positions >= SITE_MIN_POSITIONS


def cluster_sites(points: Iterable[Sighting], radius: float = 2.0) -> list[Site]:
    """Greedy clustering of sightings within ``radius`` cells of a site's running mean, per map;
    the most-seen first."""
    groups: list[list[Sighting]] = []
    for p in points:
        for g in groups:
            mx = sum(q.x for q in g) / len(g)
            my = sum(q.y for q in g) / len(g)
            if g[0].map == p.map and math.hypot(mx - p.x, my - p.y) <= radius:
                g.append(p)
                break
        else:
            groups.append([p])
    sites = [Site(g[0].map, sum(q.x for q in g) / len(g), sum(q.y for q in g) / len(g), tuple(g))
             for g in groups]  # fmt: skip
    return sorted(sites, key=lambda s: -s.n)


# --- coverage: per class / species / NPC sprite, frames where the packets place it on screen ------


@dataclass
class Coverage:
    frames: int = 0
    trainable: int = 0
    gm_window: int = 0
    no_world: int = 0
    maps: Counter[str] = field(default_factory=Counter)
    excluded: Counter[str] = field(default_factory=Counter)
    class_frames: Counter[str] = field(default_factory=Counter)
    class_instances: Counter[str] = field(default_factory=Counter)
    species_frames: Counter[int] = field(default_factory=Counter)  # monster job
    species_instances: Counter[int] = field(default_factory=Counter)
    npc_frames: Counter[int] = field(default_factory=Counter)  # NPC job (its sprite)
    npc_kinds: Counter[str] = field(default_factory=Counter)
    cutin_frames: int = 0
    cutin_verified: int = 0  # cut-in shown AND no unit's projected box touches it (verify_region)
    trainable_maps: Counter[str] = field(default_factory=Counter)
    only_npc_unsized: int = 0  # frames that NPC sprites / measured extents alone would admit

    def add(self, fr: Frame) -> None:
        self.frames += 1
        self.maps[map_key(fr.map or "?")] += 1
        if fr.trainable:
            self.trainable += 1
            self.trainable_maps[map_key(fr.map or "?")] += 1
        reasons = {e.split(":", 1)[0] for e in fr.excluded}
        for r in reasons:  # frames excluded for each reason (a frame may have several)
            self.excluded[r] += 1
        if reasons == {"npc_unsized"}:
            self.only_npc_unsized += 1
        if fr.cutin.rect is not None:
            self.cutin_frames += 1
        for cls in {lab.cls for lab in fr.labels}:
            self.class_frames[cls] += 1
        species: set[int] = set()
        npcs: set[int] = set()
        for lab in fr.labels:
            self.class_instances[lab.cls] += 1
            if lab.cls == "monster" and lab.job is not None:
                species.add(lab.job)
                self.species_instances[lab.job] += 1
            elif lab.cls == "npc" and lab.job is not None:
                npcs.add(lab.job)
                self.npc_kinds[lab.kind] += 1
        for j in species:
            self.species_frames[j] += 1
        for j in npcs:
            self.npc_frames[j] += 1

    def merge(self, other: Coverage) -> None:
        for name in ("frames", "trainable", "gm_window", "no_world", "cutin_frames",
                     "cutin_verified", "only_npc_unsized"):  # fmt: skip
            setattr(self, name, getattr(self, name) + getattr(other, name))
        for name in ("maps", "excluded", "class_frames", "class_instances", "species_frames",
                     "species_instances", "npc_frames", "npc_kinds", "trainable_maps"):  # fmt: skip
            getattr(self, name).update(getattr(other, name))

    def as_dict(self) -> dict[str, Any]:
        def keyed(c: Counter[Any]) -> dict[str, int]:
            return {str(k): v for k, v in sorted(c.items(), key=lambda kv: (-kv[1], str(kv[0])))}

        return {
            "frames": self.frames, "trainable": self.trainable, "gm_window": self.gm_window,
            "no_world": self.no_world, "cutin_frames": self.cutin_frames,
            "cutin_verified": self.cutin_verified,
            "only_npc_unsized": self.only_npc_unsized,
            "maps": keyed(self.maps), "trainable_maps": keyed(self.trainable_maps),
            "excluded_frames": keyed(self.excluded),
            "class_frames": keyed(self.class_frames),
            "class_instances": keyed(self.class_instances),
            "species_frames": keyed(self.species_frames),
            "species_instances": keyed(self.species_instances),
            "npc_frames": keyed(self.npc_frames), "npc_kinds": keyed(self.npc_kinds),
        }  # fmt: skip


# --- measuring the portal: aligned crops, their median, the bright component ---------------------


def median_crop(crops: Sequence[npt.NDArray[Any]], min_valid: int = 3) -> npt.NDArray[np.float32]:
    """The per-pixel median of grey crops ALIGNED on one object's projected cell (NaN = masked: the
    GM, other units, the UI); NaN where fewer than ``min_valid`` crops see the pixel. The camera
    only translates, so the world around the cell stays put while the masked things move away."""
    stack = np.stack([np.asarray(c, dtype=np.float32) for c in crops])
    if stack.ndim == 4:
        stack = stack.mean(axis=3)
    valid = np.isfinite(stack).sum(axis=0)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)  # an all-NaN pixel: masked in every crop
        med = np.nanmedian(stack, axis=0)
    return np.where(valid >= min_valid, med, np.nan).astype(np.float32)


def otsu(values: npt.NDArray[Any], bins: int = 64) -> float:
    """Otsu's threshold of ``values`` (finite only)."""
    v = np.asarray(values, dtype=float)
    v = v[np.isfinite(v)]
    hist, edges = np.histogram(v, bins=bins)
    w0 = np.cumsum(hist).astype(float)
    w1 = w0[-1] - w0
    m = np.cumsum(hist * edges[:-1])
    between = (m[-1] * w0 / w0[-1] - m) ** 2 / (np.maximum(w0, 1) * np.maximum(w1, 1))
    return float(edges[int(np.argmax(between))])


def bright_extent(
    med: npt.NDArray[Any],
    anchor: tuple[int, int],
    *,
    threshold: float | None = None,
    reach: int = 12,
) -> tuple[int, int, int, int] | None:
    """The extent (x0, y0, x1, y1 px relative to ``anchor``; x1 / y1 exclusive) of the BRIGHT
    connected component (above ``threshold``, default Otsu's) nearest the anchor, within
    ``reach`` px; None when there is none. A HINT for the person who reads the median crop: a
    lit floor or a bright wall next to the portal joins the component (iz_dun00's shrine light
    did, 2026-10-09)."""
    img = np.nan_to_num(np.asarray(med, dtype=float), nan=-1.0)
    th = otsu(med) if threshold is None else threshold
    mask = img > th
    ys, xs = np.nonzero(mask)
    if not len(xs):
        return None
    d = np.hypot(xs - anchor[0], ys - anchor[1])
    i = int(np.argmin(d))
    if float(d[i]) > reach:
        return None
    comp = _component(mask, (int(ys[i]), int(xs[i])))
    cy, cx = np.nonzero(comp)
    ax, ay = anchor
    return (int(cx.min()) - ax, int(cy.min()) - ay, int(cx.max()) + 1 - ax, int(cy.max()) + 1 - ay)


def _component(mask: npt.NDArray[np.bool_], seed: tuple[int, int]) -> npt.NDArray[np.bool_]:
    """The 8-connected component of ``mask`` holding ``seed`` (y, x)."""
    out = np.zeros_like(mask)
    h, w = mask.shape
    todo = deque([seed])
    out[seed] = True
    while todo:
        y, x = todo.popleft()
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                ny, nx = y + dy, x + dx
                if 0 <= ny < h and 0 <= nx < w and mask[ny, nx] and not out[ny, nx]:
                    out[ny, nx] = True
                    todo.append((ny, nx))
    return out
