"""Auto-labels from projected ground truth (B5, docs/phase2-plan.md): YOLO boxes per frame.

A box hangs from the entity's projected FOOT point: width w centred on it, height h above it. The
sizes per class are initial constants (v0), refined later from the hand-checked set (B6).

Excluded: the validation (GM) account's own character -- it plays hidden -- and every frame inside
a GM-command window (`gm_command` events), when spawns and warps make the scene non-natural.
"""

from collections.abc import Iterable, Sequence
from dataclasses import dataclass

import numpy as np

from poring_dataset.projection import project
from poring_dataset.timeline import FrameWorld

# objtype (rAthena bl type as sent in 0x09FD/FE/FF): 0 = player, 5 = monster, 6 = NPC.
CLASSES = {"player": 0, "monster": 1, "npc": 2}
OBJTYPE_CLASS = {0: "player", 5: "monster", 6: "npc"}
BOX_PX = {"player": (34, 74), "monster": (44, 40), "npc": (34, 74)}  # (w, h), v0 constants


@dataclass(frozen=True, slots=True)
class Label:
    cls: str
    gid: int
    x0: float
    y0: float
    x1: float
    y1: float

    def yolo(self, width: int, height: int) -> str:
        cx, cy = (self.x0 + self.x1) / 2 / width, (self.y0 + self.y1) / 2 / height
        w, h = (self.x1 - self.x0) / width, (self.y1 - self.y0) / height
        return f"{CLASSES[self.cls]} {cx:.6f} {cy:.6f} {w:.6f} {h:.6f}"


def labels_for(
    frame: FrameWorld,
    h: np.ndarray,
    size: tuple[int, int],
    *,
    exclude_gids: Iterable[int] = (),
) -> list[Label]:
    """Boxes for every visible entity, in pixels of the game region (width, height = size)."""
    if frame.self_pos is None:
        return []
    width, height = size
    skip = set(exclude_gids)
    out: list[Label] = []
    sx, sy = frame.self_pos
    for ent in frame.entities:
        cls = OBJTYPE_CLASS.get(ent.objtype)
        if cls is None or ent.gid in skip:
            continue
        ((u, v),) = project(h, np.array([[ent.x - sx, ent.y - sy]]))
        w, bh = BOX_PX[cls]
        box = Label(cls, ent.gid, u - w / 2, v - bh, u + w / 2, v)
        clipped = Label(cls, ent.gid, max(box.x0, 0), max(box.y0, 0), min(box.x1, width),
                        min(box.y1, height))  # fmt: skip
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
