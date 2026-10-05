"""Auto-labels from projected ground truth (B5, docs/phase2-plan.md): YOLO boxes per frame.

A box hangs from the entity's projected FOOT point: width w centred on it, height h above it. The
sizes per class are initial constants (v0), refined later from the hand-checked set (B6).

Excluded: the validation (GM) account's own character -- it plays hidden -- and every frame inside
a GM-command window (`gm_command` events), when spawns and warps make the scene non-natural. Also
NPCs the client draws as NOTHING (Post-S2 round B5, 2026-10-04; rAthena's class facts): 111
HIDDEN_NPC and 139 HIDDEN_WARP_NPC are sent but invisible, 32767 INVISIBLE is never meant to show
(-1 FAKENPC is never sent), and 45 WARPNPC is a portal EFFECT, not an NPC sprite. And any unit
sent with an invisibility OPTION (HIDE/CLOAK/INVISIBLE in its effectState; 2026-10-04: the
church's six "Single Army" event NPCs, ordinary sprite classes the client did not draw).

Boxes mostly behind the client's fixed UI windows (ui_layout.UI_RECTS: the frozen 1280x720 layout)
are dropped too: the entity is not visible there (the 2026-10-04 indoor sheet).

Each box carries the entity's FACING (B4): the sprite direction the client draws for its heading
under the map's camera (camera.displayed_direction) -- metadata for the dataset, so a rotated
(indoor) camera needs no rotated-sprite training, only the right direction label.
"""

from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass

import numpy as np

from poring_dataset.camera import displayed_direction
from poring_dataset.projection import project
from poring_dataset.render import Actor, MonsterAction, Scene, SpriteSheet, predict_sprite
from poring_dataset.timeline import ActorState, FrameWorld
from poring_dataset.ui_layout import UI_RECTS, covered_fraction

# objtype (rAthena bl type as sent in 0x09FD/FE/FF): 0 = player, 5 = monster, 6 = NPC.
CLASSES = {"player": 0, "monster": 1, "npc": 2}
OBJTYPE_CLASS = {0: "player", 5: "monster", 6: "npc"}
BOX_PX = {"player": (34, 74), "monster": (44, 40), "npc": (34, 74)}  # (w, h), v0 constants
MAX_UI_COVER = 0.5  # a box at least this much under the client's UI windows is not a visible entity
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
    kind: str = "v0"  # the box: "v0" (a class constant) or predict_sprite's "opaque"/"quad"
    state: str | None = None  # v1: the Timeline state the box was drawn for
    phase_known: bool | None = None  # v1: False = the action's envelope (idle/walk phase unknown)

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
    ui_rects: tuple[tuple[int, int, int, int], ...] = UI_RECTS,
    keep_all: bool = False,
) -> list[Label]:
    """Boxes for every visible entity, in pixels of the game region (width, height = size).
    ``keep_all`` (v1's use): also return the entities whose v0 box fails the on-screen/UI rules,
    marked kind="dropped", so v1 can judge its own box instead.
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
        if cls is None or ent.gid in skip or ent.hidden or not drawn(ent.objtype, ent.job):
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
        on_screen = clipped.x1 - clipped.x0 >= w / 2 and clipped.y1 - clipped.y0 >= bh / 2
        hidden_by_ui = covered_fraction((box.x0, box.y0, box.x1, box.y1), ui_rects) >= MAX_UI_COVER
        if on_screen and not hidden_by_ui:
            out.append(clipped)  # at least half the box on screen, and not behind the UI
        elif keep_all:
            out.append(Label(cls, ent.gid, clipped.x0, clipped.y0, clipped.x1, clipped.y1, facing,
                             kind="dropped"))  # fmt: skip
    return out


# v1 (Phase 3 M5): the Timeline state -> the monster's ACT action group. Attack, hurt and die play
# once from the state's start (their phase is the time since); idle and walk use the envelope.
STATE_ACTION = {"idle": MonsterAction.IDLE, "sit": MonsterAction.IDLE, "walk": MonsterAction.WALK,
                "attacking": MonsterAction.ATTACK, "hurt": MonsterAction.HURT,
                "dying": MonsterAction.DIE}  # fmt: skip
ONE_SHOT = frozenset({MonsterAction.ATTACK, MonsterAction.HURT, MonsterAction.DIE})


def labels_for_v1(
    frame: FrameWorld,
    h: np.ndarray | Callable[[np.ndarray, tuple[int, int]], np.ndarray],
    size: tuple[int, int],
    *,
    scene: Scene,
    state: Callable[[int], ActorState | None],
    sheet: Callable[[int], SpriteSheet | None],
    k: float,
    exclude_gids: Iterable[int] = (),
    camera_yaw: float | None = None,
    ui_rects: tuple[tuple[int, int, int, int], ...] = UI_RECTS,
) -> list[Label]:
    """v1 labels: v0's filters and its player/NPC boxes, but every monster of a catalogued species
    gets predict_sprite's box (its sprite, at its projected anchor, scaled by the camera and ``k``)
    for the action its Timeline state shows. A monster the client draws nothing for gets no box; an
    uncatalogued species keeps the v0 box (kind "v0")."""
    if frame.self_pos is None:
        return []
    width, height = size
    v0 = {lab.gid: lab for lab in labels_for(frame, h, size, exclude_gids=exclude_gids,
                                             camera_yaw=camera_yaw, ui_rects=ui_rects,
                                             keep_all=True)}  # fmt: skip
    out: list[Label] = []
    for ent in frame.entities:
        base = v0.get(ent.gid)
        if base is None:
            continue  # filtered by v0's rules (class, own GM, hidden, never drawn)
        sh = sheet(ent.job) if base.cls == "monster" else None
        st = state(ent.gid) if sh is not None else None
        if sh is None or st is None:
            if base.kind != "dropped":
                out.append(base)
            continue
        action = STATE_ACTION.get(st.state, MonsterAction.IDLE)
        elapsed = st.elapsed_ms if action in ONE_SHOT else None
        heading = st.facing if st.facing is not None else (ent.heading or 0)
        pred = predict_sprite(Actor((float(ent.x), float(ent.y)), int(heading), action,
                                    elapsed_ms=elapsed, duration_ms=st.duration_ms),
                              sh, scene, k)  # fmt: skip
        if pred is None:
            continue  # the client draws nothing for it now
        x0, y0, x1, y1 = pred.box
        bw, bh = x1 - x0, y1 - y0
        clipped = (max(x0, 0), max(y0, 0), min(x1, width), min(y1, height))
        on_screen = clipped[2] - clipped[0] >= bw / 2 and clipped[3] - clipped[1] >= bh / 2
        if not on_screen or covered_fraction(pred.box, ui_rects) >= MAX_UI_COVER:
            continue
        out.append(Label("monster", ent.gid, *clipped, facing=base.facing, kind=pred.box_kind,
                         state=st.state, phase_known=pred.phase_known))  # fmt: skip
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
