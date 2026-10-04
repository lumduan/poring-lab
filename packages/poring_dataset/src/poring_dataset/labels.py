"""Auto-labels from projected ground truth (B5, docs/phase2-plan.md): YOLO boxes per frame.

A box hangs from the entity's projected FOOT point: width w centred on it, height h above it. The
sizes per class are initial constants (v0), refined later from the hand-checked set (B6).

Excluded: the validation (GM) account's own character -- it plays hidden -- and every frame inside
a GM-command window (`gm_command` events), when spawns and warps make the scene non-natural. Also
NPCs the client draws as NOTHING (Post-S2 round B5, 2026-10-04; rAthena's class facts): 111
HIDDEN_NPC and 139 HIDDEN_WARP_NPC are sent but invisible, 32767 INVISIBLE is never meant to show
(-1 FAKENPC is never sent), and 45 WARPNPC is a portal EFFECT, not an NPC sprite.

Each box carries the entity's FACING (B4): the sprite direction the client draws for its heading
under the map's camera (camera.displayed_direction) -- metadata for the dataset, so a rotated
(indoor) camera needs no rotated-sprite training, only the right direction label.
"""

from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass

import numpy as np

from poring_dataset.camera import displayed_direction
from poring_dataset.projection import project
from poring_dataset.timeline import FrameWorld

# objtype (rAthena bl type as sent in 0x09FD/FE/FF): 0 = player, 5 = monster, 6 = NPC.
CLASSES = {"player": 0, "monster": 1, "npc": 2}
OBJTYPE_CLASS = {0: "player", 5: "monster", 6: "npc"}
BOX_PX = {"player": (34, 74), "monster": (44, 40), "npc": (34, 74)}  # (w, h), v0 constants
HIDDEN_NPC_CLASSES = frozenset({111, 139, 32767})  # sent (or never meant to be), drawn as nothing
WARP_PORTAL_CLASS = 45  # a portal effect on the ground, not an NPC sprite


def drawn(objtype: int, job: int) -> bool:
    """False for NPC classes the client never draws as a sprite."""
    return not (OBJTYPE_CLASS.get(objtype) == "npc" and
                (job in HIDDEN_NPC_CLASSES or job == WARP_PORTAL_CLASS))  # fmt: skip


@dataclass(frozen=True, slots=True)
class Label:
    cls: str
    gid: int
    x0: float
    y0: float
    x1: float
    y1: float
    facing: int | None = None  # camera.SPRITE_DIRECTIONS index; None when the heading is unknown

    def yolo(self, width: int, height: int) -> str:
        cx, cy = (self.x0 + self.x1) / 2 / width, (self.y0 + self.y1) / 2 / height
        w, h = (self.x1 - self.x0) / width, (self.y1 - self.y0) / height
        return f"{CLASSES[self.cls]} {cx:.6f} {cy:.6f} {w:.6f} {h:.6f}"


def labels_for(
    frame: FrameWorld,
    h: np.ndarray | Callable[[np.ndarray, tuple[int, int]], np.ndarray],
    size: tuple[int, int],
    *,
    exclude_gids: Iterable[int] = (),
    camera_yaw: float | None = None,
) -> list[Label]:
    """Boxes for every visible entity, in pixels of the game region (width, height = size).
    ``h``: a flat homography, or a projector (camera.projector_for: the perspective camera with the
    map's altitude) called with the cell offsets and the player's cell. ``camera_yaw``: the map's
    camera yaw (camera.map_camera), for each box's facing."""
    if frame.self_pos is None:
        return []
    width, height = size
    skip = set(exclude_gids)
    out: list[Label] = []
    sx, sy = frame.self_pos
    for ent in frame.entities:
        cls = OBJTYPE_CLASS.get(ent.objtype)
        if cls is None or ent.gid in skip or not drawn(ent.objtype, ent.job):
            continue
        offset = np.array([[ent.x - sx, ent.y - sy]])
        if callable(h):
            ((u, v),) = h(offset, (int(round(sx)), int(round(sy))))
        else:
            ((u, v),) = project(h, offset)
        w, bh = BOX_PX[cls]
        facing = None
        if ent.heading is not None and camera_yaw is not None:
            facing = displayed_direction(ent.heading, camera_yaw)
        box = Label(cls, ent.gid, u - w / 2, v - bh, u + w / 2, v)
        clipped = Label(cls, ent.gid, max(box.x0, 0), max(box.y0, 0), min(box.x1, width),
                        min(box.y1, height), facing)  # fmt: skip
        if clipped.x1 - clipped.x0 >= w / 2 and clipped.y1 - clipped.y0 >= bh / 2:
            out.append(clipped)  # at least half the box on screen
    return out


def gm_windows(
    events: Sequence[dict[str, object]], window_ns: int = 2_000_000_000
) -> list[tuple[int, int]]:
    """[t, t + window] around every GM command (events flagged gm_command)."""
    out = []
    for e in events:
        if e.get("gm_command"):
            t = int(str(e["t_mono_ns"]))
            out.append((t, t + window_ns))
    return out


def in_windows(t_ns: int, windows: Sequence[tuple[int, int]]) -> bool:
    return any(a <= t_ns <= b for a, b in windows)
