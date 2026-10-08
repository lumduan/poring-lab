#!/usr/bin/env python3
"""The HUD SCENE process (Batt 2026-10-08, H.264-style): a RETAINED overlay the console draws on
every frame, kept current by DELTAS, whether a rule runs or not (bot idle, or Batt playing).

    hud_scene.py [--hz 10] [--det-period 0.5] [--motion floor|global]   (one at a time: an flock)

- **Screen-anchored objects** (the client's UI windows, the work zone) are sent once and never
  shift.
- **World-anchored objects** (units, signboards) ride ONE global motion per frame, like a motion
  vector (`HudMotion`), plus small per-object corrections (`HudDelta.move`) where the camera's
  PERSPECTIVE moves them differently (2026-10-08 night, the box drift while walking):
  - the scene's measured scroll (`route_preview.scene_shift`, sub-pixel, the UI and our character
    masked out) says WHETHER the scene moved;
  - the FLOOR model says by how much each object moved: the camera's move over the floor (cells)
    from route_preview's floor patches against the camera model (`Ground`, a flat floor), then
    every world object by its OWN projection. Far rows scroll up to ~20 % less than near ones, so
    one 2-D shift drifted off the sprites while walking. Needs no map knowledge: the camera's yaw
    and distance do not change how the floor moves on screen, only its pitch, FOV and centre;
  - the global offset carries the bulk (frame-synced on the console), and an object whose own
    projection is more than `resid_px` (4 px) off it gets a move in that frame's delta.
- **Messages** (`poring_env.protocol`):
  - `HudMotion` (the frame's offset), only while the scene moves;
  - `HudDelta` (add / move / remove), only on changes (and the perspective corrections, only while
    moving);
  - `HudScene`, a full KEYFRAME every KEYFRAME_S.
  So the rate while idle is about zero apart from keyframes. Every message leaves through ONE
  ordered queue, so the console always gets the deltas in their `seq` order.
- **Detection only DISCOVERS changes:** new units in view, moving monsters, units gone, signboards.
  The unit detector runs in its own thread, niced, DET_THREADS threads: every `det_moving_s` while
  the scene moves (at 2 threads that is back to back, ~0.6 s a pass), `det_changed_s` while the
  frame changes, `det_idle_s` when still.
  - A detection is matched to the object it IS (same class, nearest feet on the detected frame,
    one to one); a leftover one near a leftover object of its class (`dedupe_px`, or overlapping
    it) MOVES that object instead of adding a second box (the doubled boxes).
  - An object missed by `misses` passes is removed; while the scene moves, by `misses_moving`.
- **Frames:** the RDP frame bus through ro_agent's screen helper (the `frame_id` the console shows).
  It runs only while the frames come from the bus (never an extra X grab).
- **Output:** the backend's display-only channel (`/internal/display`, the internal listener). It is
  not an agent, works in any mux mode, and sends no input.
- **Log:** every message sent goes to SCENE_LOG (RAM, rotated) for renders and the offline check.
- **Offline:** scripts/hud_scene_sim.py runs this module's SceneTracker / FloorMotion / Cadence over
  recorded frames (`hud_scene_check.py sim`).

Distance in cells needs the map's camera and our cell; that is the DECISION layer's (a rule's
OperatorHud), not this perception layer's.
"""

from __future__ import annotations

import argparse
import contextlib
import fcntl
import json
import os
import queue
import signal
import sys
import threading
import time
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

STATE_DIR = Path(os.environ.get("ROUTE_PLAN_DIR", "/dev/shm/poring-lab-route"))
LOCK = STATE_DIR / "hud_scene.lock"
SCENE_LOG = STATE_DIR / "scene.jsonl"
SCENE_LOG_MAX = 20_000_000  # bytes, then rotated once (.1)
CAMERA_JSON = Path(__file__).resolve().parents[1] / "packages/poring_dataset/src/poring_dataset"
CAMERA_JSON = CAMERA_JSON / "camera_rdp.json"
KEYFRAME_S = 5.0
MOTION_MIN_PX = 0.3  # a smaller frame-to-frame shift is noise: no motion, no message
DET_THREADS = 2
MOVE_PX = 4.0  # a matched object whose box moved more than this gets a move delta
CHANGE_DIFF = 6.0  # mean abs gray difference (downsampled) above which the frame "changed"
SIGN_LIFT_PX = 175.0  # a signboard rides the floor under its NPC's feet: ~this far below the sign
SIGN_NPC_GAP = (40.0, 160.0)  # (poring_env.signboard NPC_GAP / NPC_X) the NPC under a sign
SIGN_NPC_X = 40.0
VIEW_MARGIN_PX = 40.0  # an object's feet this far outside the view still get corrections
# A unit's box size (w, h; median of ~9,000 detections, 2026-10-08 recordings): a box cut by the
# view's edge (within CLIP_PX) is extended to it, so its feet are not the screen's edge (a clipped
# NPC placed on the floor at the bottom edge rode 31 px off its sprite once in view, 19:10 walk)
SPRITE_PX = {"npc": (34.0, 75.0), "monster": (42.0, 40.0)}
CLIP_PX = 3.0


@dataclass(frozen=True)
class Tuning:
    """What the offline sim varies (hud_scene_check.py sim); the defaults are what runs live.
    LEGACY is the 2026-10-08 first cut's behaviour, for comparison."""

    motion: str = "floor"  # "floor": per-object perspective; "global": one 2-D shift for all
    det_moving_s: float = 0.5  # the detector's period while the scene moves (2 threads: ~nonstop)
    det_changed_s: float = 1.0  # ... while the frame changes (a unit walks in)
    det_idle_s: float = 5.0  # ... when it is still
    moving_hold_s: float = 1.0  # the scene "moves" for this long after its last motion
    match_px: float = 40.0  # a detection within this of an object's feet (detected frame) IS it
    dedupe_px: float = 120.0  # a leftover detection this near a leftover object MOVES it (0: off)
    dedupe_iou: float = 0.1  # ... or overlapping it at least this much (0: off)
    misses: int = 2  # an object missed by this many consecutive passes is removed
    misses_moving: int = 1  # ... while the scene moves (it has drifted or left)
    resid_px: float = 4.0  # floor model: an object this far off the global offset gets a move
    sharp: bool = True  # the scroll's correlation band-passed (SHARP_SHIFT): far fewer false zeros
    fine_px: float = 1.0  # a pass while moving, or the first still one after, re-seats boxes this
    # far off their detection (idle passes keep MOVE_PX: no jitter moves while nothing moves)
    unclip: bool = True  # a unit box cut by the view's edge gets its class's size (SPRITE_PX)


TUNING = Tuning()
LEGACY = Tuning(
    motion="global",
    det_moving_s=1.0,
    dedupe_px=0.0,
    dedupe_iou=0.0,
    misses_moving=2,
    fine_px=MOVE_PX,
    sharp=False,
    unclip=False,
)
# route_preview.scene_shift's band-pass for the HUD (its docstring has the measurement)
SHARP_SHIFT: dict[str, Any] = {"blur": True, "highpass": 9, "power": 0.5}

Box = tuple[float, float, float, float]


@dataclass
class Obj:
    id: int
    kind: str  # unit | window | zone | sign
    anchor: str  # world | screen
    box: Box  # game px, x0 y0 x1 y1; world objects at offset 0
    cls: str = ""
    conf: float | None = None
    misses: int = 0
    floor: np.ndarray | None = field(default=None, repr=False)  # floor model: the cells under it
    lift: float = 0.0  # px from the box's bottom down to the floor point it rides (signs)


@dataclass(frozen=True)
class FrameRef:
    """A frame's motion state, snapshotted with it for the detector (the pass runs later)."""

    offset: np.ndarray
    cam: np.ndarray | None = None


def _foot(box: Box, lift: float = 0.0) -> np.ndarray:
    return np.array([(box[0] + box[2]) / 2, box[3] + lift])


def _shift(box: Box, d: Any) -> Box:
    return (box[0] + float(d[0]), box[1] + float(d[1]), box[2] + float(d[0]), box[3] + float(d[1]))


def _iou(a: Box, b: Box) -> float:
    iw = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    ih = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = iw * ih
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union > 0 else 0.0


# --- the floor under the camera --------------------------------------------------------------
class Ground:
    """The FLAT floor under the camera model (poring_dataset.camera): client px <-> floor cells
    relative to the camera's target, by the floor homography (exact for a flat floor). Only the
    camera's pitch, FOV and centre shape how the floor moves on screen; its yaw and distance only
    rotate and scale the cells, so the fitted (outdoor) camera serves indoor maps too."""

    def __init__(self, camera: Any) -> None:
        from poring_dataset.camera import CELL

        eye, right, up, fw = camera.basis()
        f = (camera.height / 2) / np.tan(camera.fov / 2)
        cx, cy, c = float(camera.cx), float(camera.cy), CELL
        self.H = np.array([
            [cx * fw[0] * c + f * right[0] * c, cx * fw[2] * c + f * right[2] * c,
             -cx * (eye @ fw) - f * (eye @ right)],
            [cy * fw[0] * c - f * up[0] * c, cy * fw[2] * c - f * up[2] * c,
             -cy * (eye @ fw) + f * (eye @ up)],
            [fw[0] * c, fw[2] * c, -(eye @ fw)],
        ])  # fmt: skip
        self.Hinv = np.linalg.inv(self.H)
        self.target = np.array([cx, cy])

    def to_screen(self, g: Any) -> np.ndarray:
        """Floor cells relative to the camera (N, 2) -> client px (N, 2)."""
        g = np.atleast_2d(np.asarray(g, dtype=float))
        h = np.c_[g, np.ones(len(g))] @ self.H.T
        return np.asarray(h[:, :2] / h[:, 2:3])

    def to_floor(self, px: Any) -> np.ndarray:
        """Client px (N, 2) -> floor cells relative to the camera (N, 2); NaN off the floor."""
        p = np.atleast_2d(np.asarray(px, dtype=float))
        h = np.c_[p, np.ones(len(p))] @ self.Hinv.T
        g = h[:, :2] / h[:, 2:3]
        depth = np.c_[g, np.ones(len(g))] @ self.H[2]
        g[~(depth > 0)] = np.nan
        return np.asarray(g)

    def flow(self, g: Any, d: Any, eps: float = 1e-3) -> tuple[np.ndarray, np.ndarray]:
        """Floor points g (N, 2), the camera moved by d: where they are drawn (N, 2), and how that
        changes per cell of further camera move (N, 2, 2)."""
        g, d = np.atleast_2d(np.asarray(g, dtype=float)), np.asarray(d, dtype=float)
        p = self.to_screen(g - d)
        jx = (self.to_screen(g - d - np.array([eps, 0.0])) - p) / eps
        jy = (self.to_screen(g - d - np.array([0.0, eps])) - p) / eps
        return p, np.stack([jx, jy], axis=2)


def load_ground(path: Path = CAMERA_JSON) -> Ground | None:
    """The Ground of the fitted RDP camera, or None (then the global motion alone)."""
    try:
        from poring_dataset import camera as cam

        block = json.loads(path.read_text())["camera"]
        return Ground(cam.camera_from_json(block, int(block.get("height", 720))))
    except Exception as exc:  # noqa: BLE001 -- display only: the global motion still works
        print(f"{time.strftime('%H:%M:%S')} HUD floor model unavailable ({exc})", flush=True)
        return None


class FloorMotion:
    """The camera's move over the floor between two frames (cells, the Ground's frame): each floor
    patch's shift (route_preview.patch_shifts, around the global shift) against its OWN projection,
    Gauss-Newton with Huber weights. Too few patches: the global shift at the scroll band's
    centre."""

    MIN_PATCHES = 6  # route_preview.PATCH_MIN_N
    HUBER_PX = 2.0
    BAND_CENTRE = (700.0, 400.0)  # route_preview.BAND's centre (x, y), client px

    def __init__(self, ground: Ground, patches: Any = None) -> None:
        if patches is None:
            import route_preview as rp

            patches = rp.PATCHES
        self.ground = ground
        self.pts = np.asarray(patches, dtype=float).reshape(-1, 2)
        self.floor = ground.to_floor(self.pts)
        self.ref = ground.flow(ground.to_floor(np.array([self.BAND_CENTRE])), np.zeros(2))[1][0]

    def from_shift(self, shift: Any) -> np.ndarray:
        return np.asarray(np.linalg.solve(self.ref, np.asarray(shift, dtype=float)))

    def from_patches(self, idx: Any, s: Any, q: Any) -> np.ndarray | None:
        idx = np.asarray(idx, dtype=int).reshape(-1)
        if len(idx) < self.MIN_PATCHES:
            return None
        ok = np.isfinite(self.floor[idx]).all(1)
        if ok.sum() < self.MIN_PATCHES:
            return None
        g, p = self.floor[idx][ok], self.pts[idx][ok]
        s, w0 = np.asarray(s, dtype=float)[ok], np.asarray(q, dtype=float)[ok]
        d, w = np.zeros(2), w0.copy()
        for _ in range(4):
            pred, jac = self.ground.flow(g, d)
            r = s - (pred - p)
            a = np.einsum("n,nij,nik->jk", w, jac, jac)
            b = np.einsum("n,nij,ni->j", w, jac, r)
            try:
                d = d + np.linalg.solve(a, b)
            except np.linalg.LinAlgError:
                return None
            res = np.linalg.norm(s - (self.ground.to_screen(g - d) - p), axis=1)
            w = w0 * np.where(res > self.HUBER_PX, self.HUBER_PX / np.maximum(res, 1e-6), 1.0)
        return d

    def estimate(self, prev: np.ndarray, img: np.ndarray, shift: Any) -> np.ndarray:
        """Live: the camera's move from frame prev to img (BGR(A)), their global shift given."""
        import route_preview as rp

        idx, s, q = rp.patch_shifts(rp.gray(prev), rp.gray(img), shift)
        d = self.from_patches(idx, s, q)
        return self.from_shift(shift) if d is None else d


# --- the scene ------------------------------------------------------------------------------
class SceneTracker:
    """The retained scene: objects with ids, the global offset, and the deltas that keep a console
    current. Pure (no I/O): every input is game-region px, every output protocol-shaped dicts.
    Thread-safe: the frame loop and the detector thread both change it (``lock``)."""

    def __init__(self, region: tuple[int, int, int, int], desktop: tuple[int, int],
                 windows: list[tuple[int, int, int, int]], ground: Ground | None = None,
                 tuning: Tuning = TUNING) -> None:  # fmt: skip
        self.gx, self.gy, self.gw, self.gh = region
        self.dw, self.dh = desktop
        self.tuning = tuning
        self.ground = ground if tuning.motion == "floor" else None
        self.offset = np.zeros(2)  # game px: the scene's cumulative motion (what consoles get)
        self.cam = np.zeros(2)  # floor model: the camera's cumulative move over the floor (cells)
        self.objects: dict[int, Obj] = {}
        self.next_id = 1
        self.seq = 0
        self.unsettled = False  # the scene moved since the last still detection pass
        self.lock = threading.RLock()
        self._add(Obj(0, "zone", "screen", (0.0, 0.0, float(self.gw), float(self.gh))))
        for x0, y0, x1, y1 in windows:
            self._add(Obj(0, "window", "screen", (float(x0), float(y0), float(x1), float(y1))))

    def _add(self, o: Obj) -> Obj:
        o.id = self.next_id
        self.next_id += 1
        self.objects[o.id] = o
        return o

    # --- protocol shapes ----------------------------------------------------------------------
    def _rect(self, box: Box) -> dict[str, float]:
        x0, y0, x1, y1 = box
        return {"x": (self.gx + x0) / self.dw, "y": (self.gy + y0) / self.dh,
                "w": max(0.0, x1 - x0) / self.dw, "h": max(0.0, y1 - y0) / self.dh}  # fmt: skip

    def _obj(self, o: Obj) -> dict[str, Any]:
        r = self._rect(o.box)  # a world object's box is where it is drawn at motion offset 0
        out: dict[str, Any] = {"id": o.id, "kind": o.kind, "anchor": o.anchor, "box": r,
                               "cls": o.cls[:32]}  # fmt: skip
        if o.conf is not None:
            out["conf"] = round(min(max(o.conf, 0.0), 1.0), 3)
        return out

    def _move(self, o: Obj) -> dict[str, Any]:
        out: dict[str, Any] = {"id": o.id, "box": self._rect(o.box)}
        if o.conf is not None:
            out["conf"] = round(min(max(o.conf, 0.0), 1.0), 3)
        return out

    def _delta(self, add: list[Any], move: list[Any], remove: list[int]) -> dict[str, Any] | None:
        if not (add or move or remove):
            return None
        self.seq += 1
        return {"seq": self.seq, "add": add, "move": move, "remove": remove}

    def offset_norm(self) -> dict[str, float]:
        return {"x": float(self.offset[0]) / self.dw, "y": float(self.offset[1]) / self.dh}

    def keyframe(self) -> dict[str, Any]:
        with self.lock:
            return {"seq": self.seq, "offset": self.offset_norm(),
                    "objects": [self._obj(o) for o in self.objects.values()],
                    "period_ms": int(KEYFRAME_S * 1000)}  # fmt: skip

    def ref(self) -> FrameRef:
        """This frame's motion state, for a detection pass on it."""
        with self.lock:
            return FrameRef(self.offset.copy(), self.cam.copy() if self.ground else None)

    def _in_view(self, p: Any, margin: float = 0.0) -> bool:
        return bool(-margin <= p[0] <= self.gw + margin and -margin <= p[1] <= self.gh + margin)

    # --- inputs -------------------------------------------------------------------------------
    def motion(self, shift: tuple[float, float]) -> bool:
        """The scene moved by ``shift`` (game px) since the last frame: True when it counts (the
        floor model's frames go through ``on_frame``, with the camera's move)."""
        moved, _ = self.on_frame(shift, None)
        return moved

    def on_frame(self, shift: Any, dc: Any = None) -> tuple[bool, dict[str, Any] | None]:
        """One frame's motion: ``shift`` = the scene's scroll (game px), ``dc`` = the camera's move
        over the floor (cells; the floor model). Returns (the offset moved: send a HudMotion, this
        frame's perspective corrections: a delta, or None)."""
        with self.lock:
            if float(np.hypot(*shift)) < MOTION_MIN_PX:
                return False, None
            self.unsettled = True
            if self.ground is None:
                self.offset = self.offset + np.asarray(shift, dtype=float)
                return True, None
            g = self.ground
            if dc is None:  # no floor patches: the scroll read at the band's centre, as FloorMotion
                jref = g.flow(g.to_floor(np.array([FloorMotion.BAND_CENTRE])), np.zeros(2))[1][0]
                dc = np.linalg.solve(jref, np.asarray(shift, dtype=float))
            dc = np.asarray(dc, dtype=float)
            self.cam = self.cam + dc
            on_floor = [o for o in self.objects.values()
                        if o.anchor == "world" and o.floor is not None]  # fmt: skip
            preds: dict[int, np.ndarray] = {}
            if on_floor:
                ps = g.to_screen(np.array([o.floor for o in on_floor]) - self.cam)
                preds = {o.id: p for o, p in zip(on_floor, ps, strict=True)}
            # the offset carries what the objects in view need (their median), else the motion of
            # the camera's target point; the rest goes out as per-object corrections
            need = [preds[o.id] - (_foot(o.box, o.lift) + self.offset) for o in on_floor
                    if self._in_view(preds[o.id], VIEW_MARGIN_PX)]  # fmt: skip
            step = np.median(np.array(need), axis=0) if need else g.to_screen(-dc)[0] - g.target
            self.offset = self.offset + step
            moves = []
            for o in on_floor:
                p = preds[o.id]
                if not self._in_view(p, VIEW_MARGIN_PX):
                    continue
                r = p - (_foot(o.box, o.lift) + self.offset)
                if float(np.hypot(*r)) > self.tuning.resid_px:
                    o.box = _shift(o.box, r)
                    moves.append(self._move(o))
            return True, self._delta([], moves, [])

    def observe(self, found: list[dict[str, Any]], frame_offset: Any,
                frame_cam: Any = None, moving: bool = False) -> dict[str, Any] | None:  # fmt: skip
        """One detection pass on a frame whose motion state was ``frame_offset`` (a FrameRef, or
        the offset alone): ``found`` = boxes in game px with cls / conf / kind ("unit" or "sign").
        ``moving``: the scene moves (stale objects go sooner). Returns a delta, or None."""
        with self.lock:
            if isinstance(frame_offset, FrameRef):
                frame_cam = frame_offset.cam if frame_cam is None else frame_cam
                frame_offset = frame_offset.offset
            off_k = np.asarray(frame_offset, dtype=float)
            cam_k = None if frame_cam is None else np.asarray(frame_cam, dtype=float)
            g = self.ground if cam_k is not None else None
            tu = self.tuning
            world = {i: o for i, o in self.objects.items() if o.anchor == "world"}

            def seen_at(o: Obj) -> np.ndarray:  # its feet as drawn on the DETECTED frame
                if g is not None and cam_k is not None and o.floor is not None:
                    return np.asarray(g.to_screen(o.floor - cam_k)[0])
                return np.asarray(_foot(o.box, o.lift) + off_k)

            at = {i: seen_at(o) for i, o in world.items()}
            dets: list[tuple[Box, str, str, float, np.ndarray, Any]] = []
            for f in found:
                x0, y0, x1, y1 = (float(v) for v in f["box"])
                box: Box = (x0, y0, x1, y1)
                kind, cls = str(f.get("kind", "unit")), str(f.get("cls", ""))
                if kind == "unit" and tu.unclip:
                    box = self._unclip(box, cls)
                lift = self._lift(box, found) if kind == "sign" and g is not None else 0.0
                dets.append((box, kind, cls, lift, _foot(box, lift), f.get("conf")))
            pairs = []
            for di, (box, kind, cls, _lift, foot, _conf) in enumerate(dets):
                for i, o in world.items():
                    if o.kind != kind or o.cls != cls:
                        continue
                    d = float(np.hypot(*(foot - at[i])))
                    if d < tu.match_px:
                        pairs.append((0, d, di, i))
                        continue
                    near = tu.dedupe_px > 0 and d < tu.dedupe_px
                    lap = tu.dedupe_iou > 0 and _iou(box, _shift(o.box, at[i] - _foot(
                        o.box, o.lift))) >= tu.dedupe_iou  # fmt: skip
                    if near or lap:
                        pairs.append((1, d, di, i))  # the doubled-box case: move it, never add
            pairs.sort()
            got: dict[int, int] = {}
            for _, _, di, i in pairs:  # one to one: plain matches first, then the closest
                if di not in got and i not in got.values():
                    got[di] = i
            add, move, remove = [], [], []
            fine = moving or self.unsettled  # the scene moved: re-seat boxes more finely
            thr = tu.fine_px if fine else MOVE_PX
            for di, (box, kind, cls, lift, foot, conf) in enumerate(dets):
                placed, fl = self._place(box, foot, off_k, cam_k)
                if di not in got:
                    o = self._add(Obj(0, kind, "world", placed, cls, conf, floor=fl, lift=lift))
                    add.append(self._obj(o))
                    continue
                o = world[got[di]]
                o.misses, o.floor, o.lift = 0, fl, lift
                o.conf = conf if conf is not None else o.conf
                if float(np.hypot(*(_foot(placed, lift) - _foot(o.box, lift)))) > thr:
                    o.box = placed
                    move.append(self._move(o))
            limit = tu.misses_moving if moving else tu.misses
            taken = set(got.values())
            for i, o in world.items():
                if i in taken:
                    continue
                o.misses += 1
                if not self._in_view(at[i]) or o.misses >= limit:
                    del self.objects[i]
                    remove.append(i)
            if not moving:
                self.unsettled = False
            return self._delta(add, move, remove)

    def _place(self, box: Box, foot: np.ndarray, off_k: np.ndarray,
               cam_k: np.ndarray | None) -> tuple[Box, np.ndarray | None]:  # fmt: skip
        """A box seen on a past frame -> its offset-0 box NOW, and its floor point (floor model)."""
        if self.ground is None or cam_k is None:
            return _shift(box, -off_k), None
        fl = cam_k + self.ground.to_floor(foot[None, :])[0]
        if not np.isfinite(fl).all():
            return _shift(box, -off_k), None
        now = self.ground.to_screen(fl - self.cam)[0]
        return _shift(box, now - foot - self.offset), fl

    def _unclip(self, box: Box, cls: str) -> Box:
        """A unit box cut by the view's bottom, left or right edge -> its class's full size there
        (its feet are past the edge, not on it)."""
        if cls not in SPRITE_PX:
            return box
        w, h = SPRITE_PX[cls]
        x0, y0, x1, y1 = box
        if y1 >= self.gh - CLIP_PX and y1 - y0 < h:
            y1 = y0 + h
        if x0 <= CLIP_PX and x1 - x0 < w:
            x0 = x1 - w
        elif x1 >= self.gw - CLIP_PX and x1 - x0 < w:
            x1 = x0 + w
        return (x0, y0, x1, y1)

    @staticmethod
    def _lift(sign: Box, found: list[dict[str, Any]]) -> float:
        """How far below a sign's bottom the floor it rides is: the feet of its NPC when that NPC
        was detected under it, else SIGN_LIFT_PX."""
        cx = (sign[0] + sign[2]) / 2
        best: float | None = None
        for f in found:
            if f.get("kind", "unit") != "unit" or f.get("cls") != "npc":
                continue
            x0, y0, x1, y1 = (float(v) for v in f["box"])
            gap = y0 - sign[3]
            if abs((x0 + x1) / 2 - cx) <= SIGN_NPC_X and SIGN_NPC_GAP[0] <= gap <= SIGN_NPC_GAP[1]:
                best = y1 - sign[3] if best is None else min(best, y1 - sign[3])
        return SIGN_LIFT_PX if best is None else best


class Cadence:
    """When the detector runs: every det_moving_s while the scene moves (it moved within
    moving_hold_s), det_changed_s while the frame changes, det_idle_s when still. Times in seconds
    on one clock (the process's monotonic, or a recording's)."""

    def __init__(self, tuning: Tuning = TUNING) -> None:
        self.tuning = tuning
        self.last_motion = -1e18
        self.last_run = -1e18
        self.last_gray: np.ndarray | None = None

    def moving(self, now: float) -> bool:
        return now - self.last_motion < self.tuning.moving_hold_s

    def due(self, now: float, g8: np.ndarray) -> bool:
        tu = self.tuning
        if self.moving(now):
            period = tu.det_moving_s
        else:
            period = tu.det_changed_s if frame_changed_gray(self.last_gray, g8) else tu.det_idle_s
        return now - self.last_run >= period

    def ran(self, now: float, g8: np.ndarray) -> None:
        self.last_run, self.last_gray = now, g8


def gray8(img: np.ndarray) -> np.ndarray:
    """The 1/8 gray frame the cadence compares (mean of B, G, R)."""
    return np.asarray(img[::8, ::8, :3].astype(np.float32).mean(-1))


def frame_changed_gray(a: np.ndarray | None, b: np.ndarray) -> bool:
    if a is None:
        return True
    return float(np.abs(a.astype(np.float32) - b.astype(np.float32)).mean()) > CHANGE_DIFF


def frame_changed(a: np.ndarray | None, b: np.ndarray) -> bool:
    return frame_changed_gray(None if a is None else gray8(a), gray8(b))


def frame_messages(tracker: SceneTracker, t: int, fid: int, moved: bool,
                   delta: dict[str, Any] | None) -> list[dict[str, Any]]:  # fmt: skip
    """A frame's messages, in order: its motion, then its perspective corrections."""
    out = []
    if moved:
        out.append({"type": "hud_motion", "t_mono_ns": int(t), "frame_id": int(fid),
                    "offset": tracker.offset_norm()})  # fmt: skip
    if delta is not None:
        out.append({"type": "hud_delta", "t_mono_ns": int(t), "frame_id": int(fid), **delta})
    return out


def detect_found(units: list[Any], signs: list[Any]) -> list[dict[str, Any]]:
    """The detector's units (never our player) and the signboards, as SceneTracker.observe takes
    them."""
    found = [{"kind": "unit", "cls": b.cls, "conf": b.score,
              "box": [b.x0, b.y0, b.x1, b.y1]} for b in units if b.cls != "player"]  # fmt: skip
    for sign in signs:
        sb = sign.box
        found.append({"kind": "sign", "cls": "sign", "conf": None,
                      "box": [sb.x0, sb.y0, sb.x1 + 1, sb.y1 + 1]})  # fmt: skip
    return found


# --- the process --------------------------------------------------------------------------------
class Sender:
    """The display channel (the internal listener), reconnecting; every message is also logged.
    ONE thread sends everything, in the order it was queued, so deltas reach consoles in their seq
    order whichever thread made them."""

    def __init__(self) -> None:
        self.ws: Any = None
        self.retry_at = 0.0
        self.sent = 0
        self.q: queue.SimpleQueue[dict[str, Any] | None] = queue.SimpleQueue()

    def put(self, msg: dict[str, Any] | None) -> None:
        self.q.put(msg)

    def run(self) -> None:
        while (msg := self.q.get()) is not None:
            self.send(msg)

    def _url(self) -> str:
        import ro_agent as r

        return r.backend_ws().replace("/internal/agent", "/internal/display")

    def send(self, msg: dict[str, Any]) -> None:
        text = json.dumps(msg)
        with contextlib.suppress(Exception):  # logged with the moment it left (the replay's order)
            if SCENE_LOG.exists() and SCENE_LOG.stat().st_size > SCENE_LOG_MAX:
                SCENE_LOG.replace(SCENE_LOG.with_suffix(".jsonl.1"))
            with open(SCENE_LOG, "a") as fh:
                fh.write(json.dumps({"logged_ns": time.monotonic_ns(), "msg": msg}) + "\n")
        if self.ws is None and time.monotonic() >= self.retry_at:
            try:
                from websockets.sync.client import connect

                self.ws = connect(self._url(), open_timeout=5, max_size=2**20)
            except Exception as exc:  # noqa: BLE001 -- display only
                print(f"{time.strftime('%H:%M:%S')} display channel down ({exc})", flush=True)
                self.retry_at = time.monotonic() + 5.0
                return
        if self.ws is None:
            return
        try:
            self.ws.send(text)
            self.sent += 1
            with contextlib.suppress(Exception):  # an ErrorReply would mean a protocol bug: log it
                while True:
                    reply = self.ws.recv(timeout=0)
                    print(
                        f"{time.strftime('%H:%M:%S')} display reply: {str(reply)[:200]}", flush=True
                    )
        except Exception:  # noqa: BLE001
            with contextlib.suppress(Exception):
                self.ws.close()
            self.ws, self.retry_at = None, time.monotonic() + 5.0


def serve(hz: float, tuning: Tuning) -> int:
    import ro_agent as r
    import route_preview as rp

    STATE_DIR.mkdir(parents=True, exist_ok=True)
    lock = open(LOCK, "w")  # noqa: SIM115 -- held for the process's life
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        print(f"{time.strftime('%H:%M:%S')} another HUD scene process runs: exiting", flush=True)
        return 0
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    os.nice(10)  # display only: below every rule (its detector included; children inherit it)
    region, desktop = tuple(r.game_region()), tuple(r.desktop())
    ground = load_ground() if tuning.motion == "floor" else None
    floor = FloorMotion(ground) if ground is not None else None
    windows = [tuple(w) for w in rp.UI_WINDOWS]
    tracker = SceneTracker(region, desktop, windows, ground, tuning)  # type: ignore[arg-type]
    cadence = Cadence(tuning)
    out = Sender()
    threading.Thread(target=out.run, name="hud-sender", daemon=True).start()
    screen: Any = None
    latest: dict[str, Any] = {}
    stop = threading.Event()
    stats: dict[str, Any] = {"det": 0, "det_ms": [], "frames": 0, "motion": 0, "corr": 0,
                             "floor_ms": []}  # fmt: skip

    def detector() -> None:
        import unit_detector

        from poring_env.signboard import find_signs

        try:
            det = unit_detector.UnitDetector(threads=DET_THREADS)
        except Exception as exc:  # noqa: BLE001
            print(f"{time.strftime('%H:%M:%S')} HUD detector unavailable ({exc})", flush=True)
            return
        try:
            while not stop.is_set():
                got = latest.get("frame")
                now = time.monotonic()
                if got is None:
                    stop.wait(0.1)
                    continue
                t, fid, img, ref = got
                g8 = gray8(img)
                if not cadence.due(now, g8):
                    stop.wait(0.1)
                    continue
                t0 = time.monotonic()
                units = [b for b in det.detect(img) if b.cls != "player"]
                # signboards by their SHAPE, with an NPC under each wherever one could be seen
                npcs = [(b.x0, b.y0, b.x1, b.y1) for b in units if b.cls == "npc"]
                found = detect_found(units, find_signs(img, npcs=npcs, exclude=rp.UI_WINDOWS))
                stats["det_ms"].append(1000 * (time.monotonic() - t0))
                stats["det"] += 1
                cadence.ran(now, g8)
                with tracker.lock:  # made and queued together: the seq order is the send order
                    delta = tracker.observe(found, ref, moving=cadence.moving(time.monotonic()))
                    if delta is not None:
                        out.put({"type": "hud_delta", "t_mono_ns": t, "frame_id": fid, **delta})
        finally:
            with contextlib.suppress(Exception):
                det.close()

    threading.Thread(target=detector, name="hud-detector", daemon=True).start()
    prev: np.ndarray | None = None
    t_key, t_report = 0.0, time.monotonic()
    print(
        f"{time.strftime('%H:%M:%S')} HUD scene: {hz:g} Hz frames, "
        f"{'floor' if floor is not None else 'global'} motion, detector every "
        f"{tuning.det_moving_s:g} s moving / {tuning.det_changed_s:g} s changing / "
        f"{tuning.det_idle_s:g} s idle, keyframe every {KEYFRAME_S:g} s",
        flush=True,
    )
    try:
        while True:
            t_loop = time.monotonic()
            try:
                if screen is None:
                    screen = r.Screen()
                t, img, fid, src = screen.grab_meta(*region)
            except Exception as exc:  # noqa: BLE001 -- e.g. a backend restart killed the helper
                print(f"{time.strftime('%H:%M:%S')} grab failed ({type(exc).__name__}); "
                      "a new screen helper in 1 s", flush=True)  # fmt: skip
                with contextlib.suppress(Exception):
                    if screen is not None:
                        screen.close()
                screen, prev = None, None
                time.sleep(1.0)
                continue
            if src != "bus":  # never an extra X grab: wait for the frame bus
                prev = None
                time.sleep(1.0)
                continue
            stats["frames"] += 1
            if prev is not None:
                shift = rp.scene_shift(prev, img, **(SHARP_SHIFT if tuning.sharp else {}))
                dc = None
                if floor is not None and float(np.hypot(*shift)) >= MOTION_MIN_PX:
                    t1 = time.monotonic()  # only while the scene moves: idle costs nothing more
                    dc = floor.estimate(prev, img, shift)
                    stats["floor_ms"].append(1000 * (time.monotonic() - t1))
                with tracker.lock:
                    moved, delta = tracker.on_frame(shift, dc)
                    for msg in frame_messages(tracker, t, fid, moved, delta):
                        out.put(msg)
                if moved:
                    cadence.last_motion = time.monotonic()
                    stats["motion"] += 1
                    stats["corr"] += int(delta is not None)
            prev = img
            latest["frame"] = (int(t), int(fid), img, tracker.ref())
            if time.monotonic() - t_key >= KEYFRAME_S:
                t_key = time.monotonic()
                with tracker.lock:
                    out.put({"type": "hud_scene", "t_mono_ns": int(t), "frame_id": int(fid),
                             **tracker.keyframe()})  # fmt: skip
            if time.monotonic() - t_report >= 60:
                ms = sorted(stats["det_ms"]) or [0.0]
                fm = sorted(stats["floor_ms"]) or [0.0]
                print(f"{time.strftime('%H:%M:%S')} HUD scene: frames {stats['frames'] / 60:.1f}"
                      f" Hz, motion msgs {stats['motion'] / 60:.2f}/s (with corrections "
                      f"{stats['corr'] / 60:.2f}/s, floor median {fm[len(fm) // 2]:.0f} ms), "
                      f"detector {stats['det'] / 60:.2f} Hz (median {ms[len(ms) // 2]:.0f} ms), "
                      f"objects {len(tracker.objects)}, sent {out.sent}", flush=True)  # fmt: skip
                stats.update(det=0, det_ms=[], frames=0, motion=0, corr=0, floor_ms=[])
                t_report = time.monotonic()
            time.sleep(max(0.0, 1.0 / hz - (time.monotonic() - t_loop)))
    finally:
        stop.set()
        out.put(None)
        with contextlib.suppress(Exception):
            if screen is not None:
                screen.close()
        lock.close()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--hz", type=float, default=10.0)
    ap.add_argument("--det-period", type=float, default=TUNING.det_moving_s,
                    help="the detector's period while the scene moves (s)")  # fmt: skip
    ap.add_argument("--motion", choices=("floor", "global"), default=TUNING.motion)
    a = ap.parse_args()
    return serve(a.hz, replace(TUNING, det_moving_s=a.det_period, motion=a.motion))


if __name__ == "__main__":
    sys.exit(main())
