#!/usr/bin/env python3
"""The NPC RENDER PATH (Batt 2026-10-13; docs/planning/npc-render.md, PROPOSED): every static NPC
drawn from GAME DATA, not from a detector. OFFLINE tooling; nothing here reads packets or sends
input.

    npc_render.py render --map M --cell X,Y --path rdp|s2 [--k K] [--kb DIR] [--sprites DIR]
                         [--names JSON] [--gat-dir DIR]
        The map's L3 NPCs seen from our cell: per drawn NPC its rendered box, mask size and
        anchor (ids, cells and pixels only); conditional and undrawn NPCs listed apart; every NPC
        that cannot be rendered listed with why (fail closed).
    npc_render.py camera-log --input-log FILE --from NS --to NS [--map-change NS ...]
        The offline camera-state check over the backend's input log (byte ranges, never the
        whole file): rotation / zoom inputs and the state they leave.

Per NPC (L3: data/kb/first_workflow.json, every NPC line the server loads; rAthena GPL, local):
map, cell, the SCRIPT's facing (the npc line's dir: 0 N, counter-clockwise), the sprite id and the
drawn mark. With the client's sprite (N1's job -> stem table, N2's decoded SPR/ACT in /dev/shm:
client data, never committed) and the backend's fitted camera, poring_dataset.render.predict_sprite
draws it: Actor(cell, dir, IDLE) with no phase, so the box is the ENVELOPE of every idle frame of
that direction and the mask the UNION of their opaque pixels (Batt: "union of its idle animation
frames"). The anchor is the cell centre at the client GAT's altitude, projected; the sprite is a
billboard scaled by f / z x k about it.

FAIL CLOSED:
- the whole render is refused (``Unsupported``) when the map is not in the KB, its GAT is not
  extracted, the indoor table is missing, or the camera path has no fit;
- an NPC is UNSUPPORTED (listed, never guessed) when L3 gives no facing, its sprite id is not in
  the job -> stem table (N1), or its SPR / ACT is not decoded (N2). ``RenderResult.complete`` is
  False while any unsupported NPC's anchor falls on the screen or within NEAR_MARGIN px of it;
- conditional NPCs (the script hides them at start) are LISTED APART and never rendered; undrawn
  ones (hidden classes, drawn False) and the portal sprite (the ``warp`` class) are not NPC
  sprites here.
- a camera that is not the default (rotated, zoomed) is refused: ``CameraLog`` (the input log,
  offline) and ``pixel_camera_check`` (the rendered NPCs against the frame; its thresholds are
  PROVISIONAL until npc-render.md's measurement fixes them).
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import numpy.typing as npt

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))

from poring_dataset.camera import (  # noqa: E402
    GAT_DIR,
    IndoorTableMissing,
    load_camera_json,
    load_indoor_table,
    map_key,
)
from poring_dataset.projection import camera_file  # noqa: E402
from poring_dataset.render import (  # noqa: E402
    K_KORANGAR,
    Actor,
    MonsterAction,
    Scene,
    SpritePrediction,
    SpriteSheet,
    anchor_and_depth,
    predict_sprite,
)

KB = REPO / "data" / "kb"
SPRITES = Path("/dev/shm/poring-lab-tmp/sprites/data/sprite/npc")  # N2's decoded files
NAMES = KB / "npc_sprite_names.json"  # N2's job -> stem (the files read and decoded)
SCREEN = (1280, 720)  # the game region labels and probes use
NEAR_MARGIN = 160  # px: an unsupported NPC anchored this close to the screen makes it incomplete
PORTAL = 45  # JT_WARPNPC: the `warp` class (labels-v2-plan 1.3), not an NPC sprite
CAMERA_PATHS = {"rdp": "rdp", "s2": "console"}  # path -> projection.camera_file backend
UNVERIFIED_GAT = frozenset({"alberta", "morocc"})  # labels-v2-plan 7.6: client != server GAT
DEFAULT_K = K_KORANGAR  # 0.14: v1's labels and the v1 replay; M4 keeps k OPEN (0.1333 / 0.14)
Cell = tuple[int, int]
Box = tuple[float, float, float, float]
SheetFor = Callable[[int], "tuple[str, SpriteSheet] | None"]


class Unsupported(Exception):
    """The whole render is refused (fail closed): ``reason`` names what is missing."""

    def __init__(self, reason: str, detail: str = "") -> None:
        super().__init__(f"{reason}: {detail}" if detail else reason)
        self.reason = reason


# --- L3: the static NPCs ------------------------------------------------------------------------


@dataclass(frozen=True)
class L3Npc:
    key: str  # file:line (never a name)
    map: str
    cell: Cell
    dir: int | None  # the script's facing, RO heading (0 N, counter-clockwise)
    sprite: int
    drawn: bool | str  # True / False / "conditional"
    sprite_class: str | None = None


def l3_npcs(map_name: str, kb_dir: Path = KB) -> tuple[list[L3Npc], bool]:
    """Every NPC line of ``map_name`` the KB lists (first_workflow.json: every file the server
    loads) and whether that list is declared COMPLETE (npc_cells.json's flag). Unsupported when
    the KB has no entry for the map."""
    doc = json.loads((kb_dir / "first_workflow.json").read_text())
    rec = doc.get("maps", {}).get(map_key(map_name))
    if rec is None:
        raise Unsupported("map_not_in_kb", map_name)
    out = [
        L3Npc(
            str(n["key"]),
            map_key(map_name),
            (int(n["x"]), int(n["y"])),
            None if n.get("dir") is None else int(n["dir"]),
            int(n["sprite"]),
            n.get("drawn", True),
            n.get("sprite_class"),
        )
        for n in rec.get("npcs", [])
    ]
    complete = False
    cells = kb_dir / "npc_cells.json"
    if cells.exists():
        block = json.loads(cells.read_text()).get("maps", {}).get(map_key(map_name)) or {}
        complete = bool(block.get("complete"))
    return out, complete


# --- the sprites ----------------------------------------------------------------------------------


def sheets_from_files(sprites_dir: Path = SPRITES, names: Path = NAMES) -> SheetFor:
    """job -> (stem, SpriteSheet) from N2's decoded files by N1/N2's job -> stem table (client
    data in /dev/shm, never committed). None: the job is not in the table, or a file is missing."""
    from poring_dataset.sprites import parse_act, parse_spr

    stems = {int(k): str(v) for k, v in json.loads(names.read_text()).items()}
    cache: dict[int, tuple[str, SpriteSheet] | None] = {}

    def get(job: int) -> tuple[str, SpriteSheet] | None:
        if job not in cache:
            cache[job] = None
            stem = stems.get(job)
            act, spr = sprites_dir / f"{stem}.act", sprites_dir / f"{stem}.spr"
            if stem and act.exists() and spr.exists():
                sheet = SpriteSheet(parse_act(act.read_bytes()), parse_spr(spr.read_bytes()))
                cache[job] = (stem, sheet)
        return cache[job]

    get.stems = stems  # type: ignore[attr-defined]  # why an unsupported job is unsupported
    return get


# --- one render -----------------------------------------------------------------------------------


@dataclass(frozen=True, eq=False)
class RenderedNpc:
    npc: L3Npc
    stem: str
    pred: SpritePrediction  # anchor, scale, depth, direction, action index; box = idle envelope
    motions: int  # idle frames of that direction (the mask is their union)

    @property
    def box(self) -> Box:
        return self.pred.box

    @property
    def mask(self) -> npt.NDArray[np.bool_]:
        assert self.pred.mask is not None
        return self.pred.mask

    @property
    def origin(self) -> tuple[int, int]:
        assert self.pred.mask_origin is not None
        return self.pred.mask_origin

    def contains(self, u: float, v: float) -> bool:
        """Is screen pixel (u, v) (any point inside the pixel) in the union mask?"""
        i, j = math.floor(u) - self.origin[0], math.floor(v) - self.origin[1]
        h, w = self.mask.shape
        return 0 <= i < w and 0 <= j < h and bool(self.mask[j, i])

    def in_box(self, u: float, v: float) -> bool:
        x0, y0, x1, y1 = self.box
        return x0 <= u < x1 and y0 <= v < y1

    def distance(self, u: float, v: float) -> float:
        """px from (u, v) to the nearest mask pixel centre (0 inside)."""
        if self.contains(u, v):
            return 0.0
        jj, ii = np.nonzero(self.mask)
        if not len(ii):
            return math.inf
        du = ii + self.origin[0] + 0.5 - u
        dv = jj + self.origin[1] + 0.5 - v
        return float(np.sqrt(du * du + dv * dv).min())

    def hit_box(self) -> Box:
        """The PROVISIONAL clickable box (HIT_*): wider than the drawn pixels, see HIT_HALF_W."""
        au, av = self.pred.anchor_px
        return (au - HIT_HALF_W, self.box[1] - HIT_TOP, au + HIT_HALF_W, av + HIT_BELOW)

    def in_hit_box(self, u: float, v: float) -> bool:
        x0, y0, x1, y1 = self.hit_box()
        return x0 <= u <= x1 and y0 <= v <= y1


# The CLICKABLE area is WIDER than the drawn pixels (npc-render.md section 3.3: cursor@2's labelled
# hovers answer TALK a cell beside a slim NPC; its drawn mask holds 39 % of the TALK points).
# PROVISIONAL box, FITTED on that design data (in-sample; the pre-registered check tests it on
# fresh hovers): |u - feet_u| <= HIT_HALF_W screen px, from the idle envelope's top - HIT_TOP down
# to the feet + HIT_BELOW. On the design data it holds 99.3 % of the TALK points (none near an
# unrendered NPC) and 11.8 % of the other answers.
HIT_HALF_W, HIT_TOP, HIT_BELOW = 42.0, 8.0, 16.0


@dataclass
class RenderResult:
    map: str
    cell: tuple[float, float]
    camera_path: str
    k: float
    l3_complete: bool
    rendered: list[RenderedNpc] = field(default_factory=list)
    conditional: list[L3Npc] = field(default_factory=list)  # listed apart, never rendered
    undrawn: list[L3Npc] = field(default_factory=list)
    unsupported: list[tuple[L3Npc, str, tuple[float, float] | None]] = field(default_factory=list)
    off_screen: int = 0
    warnings: list[str] = field(default_factory=list)

    @property
    def complete(self) -> bool:
        """No unsupported NPC near the screen, and the map's L3 list is declared complete."""
        return self.l3_complete and not self.unsupported_near()

    def unsupported_near(self) -> list[tuple[L3Npc, str, tuple[float, float] | None]]:
        """Unsupported NPCs anchored on the screen or within NEAR_MARGIN px of it (an anchor
        behind the camera, None, is never drawn)."""
        w, h = SCREEN
        m = NEAR_MARGIN
        return [
            r
            for r in self.unsupported
            if r[2] is not None and -m <= r[2][0] <= w + m and -m <= r[2][1] <= h + m
        ]

    def no_click(self, u: float, v: float) -> RenderedNpc | None:
        """The NO-CLICK answer for a pixel: the nearest rendered NPC whose drawn mask OR
        PROVISIONAL hit box holds it, else None. Only meaningful when ``complete`` (an unrendered
        NPC near the screen leaves its own area unknown: the caller refuses)."""
        inside = [r for r in self.rendered if r.contains(u, v) or r.in_hit_box(u, v)]
        return min(inside, key=lambda r: r.pred.depth) if inside else None

    def hits(self, u: float, v: float) -> list[RenderedNpc]:
        """The rendered NPCs whose union mask holds (u, v), nearest the camera first (the client
        draws the nearer one on top)."""
        return sorted((r for r in self.rendered if r.contains(u, v)), key=lambda r: r.pred.depth)

    def summary(self) -> dict[str, Any]:
        """Ids, cells and pixels only (what a committed doc may quote)."""
        return {
            "map": self.map,
            "cell": list(self.cell),
            "camera_path": self.camera_path,
            "k": self.k,
            "complete": self.complete,
            "l3_complete": self.l3_complete,
            "rendered": [
                {
                    "sprite": r.npc.sprite,
                    "cell": list(r.npc.cell),
                    "dir": r.npc.dir,
                    "direction": r.pred.direction,
                    "idle_frames": r.motions,
                    "anchor": [round(c, 1) for c in r.pred.anchor_px],
                    "box": [round(c, 1) for c in r.box],
                    "mask_px": int(r.mask.sum()),
                }
                for r in self.rendered
            ],
            "conditional": [{"sprite": n.sprite, "cell": list(n.cell)} for n in self.conditional],
            "undrawn": len(self.undrawn),
            "off_screen": self.off_screen,
            "unsupported_near": [
                {
                    "sprite": n.sprite,
                    "cell": list(n.cell),
                    "why": why,
                    "anchor": None if a is None else [round(c, 1) for c in a],
                }
                for n, why, a in self.unsupported_near()
            ],
            "unsupported_far": len(self.unsupported) - len(self.unsupported_near()),
            "warnings": self.warnings,
        }


def on_screen(box: Box, size: tuple[int, int] = SCREEN) -> bool:
    return box[2] > 0 and box[3] > 0 and box[0] < size[0] and box[1] < size[1]


def render_scene(
    npcs: Iterable[L3Npc],
    scene: Scene,
    sheets: SheetFor,
    k: float = DEFAULT_K,
    *,
    l3_complete: bool = True,
    map_name: str = "",
    camera_path: str = "",
    size: tuple[int, int] = SCREEN,
) -> RenderResult:
    """The pure core: every L3 NPC through predict_sprite (idle, no phase, with the mask)."""
    res = RenderResult(map_name, scene.player, camera_path, k, l3_complete)
    known = getattr(sheets, "stems", None)
    for n in npcs:
        if n.sprite == PORTAL or n.sprite_class == "hidden" or n.drawn is False:
            res.undrawn.append(n)
            continue
        if n.drawn != True:  # noqa: E712  ("conditional": hidden at start, state unknown)
            res.conditional.append(n)
            continue
        anchor, z = anchor_and_depth(scene, (float(n.cell[0]), float(n.cell[1])))
        where = anchor if z > 0 else None
        if n.dir is None:
            res.unsupported.append((n, "no_facing", where))
            continue
        got = sheets(n.sprite)
        if got is None:
            why = (
                "not_in_sprite_table"
                if known is not None and n.sprite not in known
                else "sprite_files_missing"
            )
            res.unsupported.append((n, why, where))
            continue
        stem, sheet = got
        if sheet.spr is None:
            res.unsupported.append((n, "no_spr", where))
            continue
        pred = predict_sprite(
            Actor((float(n.cell[0]), float(n.cell[1])), int(n.dir) % 8, MonsterAction.IDLE),
            sheet,
            scene,
            k,
            with_mask=True,
        )
        if pred is None:
            res.off_screen += 1  # behind the camera, or the idle draws nothing
            continue
        if not on_screen(pred.box, size):
            res.off_screen += 1
            continue
        res.rendered.append(RenderedNpc(n, stem, pred, sheet.motions(pred.action_index)))
    return res


_GATS: dict[tuple[str, float], Any] = {}


def cached_scene(
    cam_json: dict[str, object],
    map_name: str,
    cell: tuple[float, float],
    gat_dir: Path,
    table: frozenset[str],
) -> Scene:
    """render.load_scene's Scene with the map's GAT parsed ONCE per file (a measurement renders
    thousands of cells; a GAT is several MB parsed)."""
    from poring_dataset import gat as gatmod
    from poring_dataset.camera import map_camera

    cam = map_camera(cam_json, map_key(map_name), table)
    if cam is None:
        raise Unsupported("camera_missing", "no fitted camera")
    path = gat_dir / f"{map_key(map_name)}.gat"
    key = (str(path), path.stat().st_mtime)
    if key not in _GATS:
        if len(_GATS) >= 8:
            _GATS.pop(next(iter(_GATS)))
        _GATS[key] = gatmod.parse(path.read_bytes())
    return Scene(cam, (float(cell[0]), float(cell[1])), _GATS[key])


def render(
    map_name: str,
    cell: tuple[float, float],
    camera_path: str,
    *,
    k: float = DEFAULT_K,
    kb_dir: Path = KB,
    sheets: SheetFor | None = None,
    gat_dir: Path = GAT_DIR,
    camera_json: dict[str, object] | None = None,
) -> RenderResult:
    """Load everything one render needs, fail closed (Unsupported) on any missing piece."""
    if camera_path not in CAMERA_PATHS:
        raise Unsupported("camera_path_unknown", camera_path)
    cam_json = camera_json
    if cam_json is None:
        path = camera_file(CAMERA_PATHS[camera_path])
        if not path.exists():
            raise Unsupported("camera_missing", str(path))
        cam_json = load_camera_json(path)
    if not isinstance(cam_json.get("camera"), dict):
        raise Unsupported("camera_missing", f"{camera_path}: no fitted camera")
    npcs, complete = l3_npcs(map_name, kb_dir)
    if not (gat_dir / f"{map_key(map_name)}.gat").exists():
        raise Unsupported("gat_missing", f"{gat_dir}/{map_key(map_name)}.gat")
    try:
        table = load_indoor_table(gat_dir)
    except IndoorTableMissing as exc:
        raise Unsupported("indoor_table_missing", str(exc)) from exc
    scene = cached_scene(cam_json, map_name, cell, gat_dir, table)
    res = render_scene(
        npcs,
        scene,
        sheets or sheets_from_files(),
        k,
        l3_complete=complete,
        map_name=map_key(map_name),
        camera_path=camera_path,
    )
    if map_key(map_name) in UNVERIFIED_GAT:
        res.warnings.append("gat_unverified (labels-v2-plan 7.6: the client GAT differs)")
    if not complete:
        res.warnings.append("l3_not_complete")
    return res


# --- template matching: the rendered sprite against the frame -------------------------------------

GREY = np.array([0.299, 0.587, 0.114])


def _corr(a: npt.NDArray[np.float64], b: npt.NDArray[np.float64]) -> npt.NDArray[np.float64]:
    """Valid cross-correlation out[y, x] = sum b[j, i] a[y + j, x + i] (b no larger than a)."""
    hh, ww = a.shape
    h, w = b.shape
    fa = np.fft.rfft2(a)
    fb = np.fft.rfft2(b, s=(hh, ww))
    full = np.fft.irfft2(fa * np.conj(fb), s=(hh, ww))
    return np.asarray(full[: hh - h + 1, : ww - w + 1])


def masked_ncc(
    image: npt.NDArray[np.float64], template: npt.NDArray[np.float64], mask: npt.NDArray[np.bool_]
) -> npt.NDArray[np.float64]:
    """Masked normalised cross-correlation of ``template`` (its ``mask`` pixels only) at every
    placement inside ``image`` (FFT; NaN where the image has no variance under the mask)."""
    m = mask.astype(np.float64)
    n = float(m.sum())
    if n < 2:
        return np.full(
            (image.shape[0] - mask.shape[0] + 1, image.shape[1] - mask.shape[1] + 1), np.nan
        )
    t0 = (template - float((template * m).sum()) / n) * m
    var_t = float((t0 * t0).sum())
    num = _corr(image, t0)
    s1 = _corr(image, m)
    s2 = _corr(image * image, m)
    var_i = np.maximum(s2 - s1 * s1 / n, 0.0)
    den = np.sqrt(var_t * var_i)
    with np.errstate(invalid="ignore", divide="ignore"):
        out = np.where(den > 1e-6, num / den, np.nan)
    return np.asarray(out)


def rendered_grey(
    sheet: SpriteSheet, pred: SpritePrediction, motion: int, window: tuple[int, int, int, int]
) -> tuple[npt.NDArray[np.float64], npt.NDArray[np.bool_]]:
    """(grey, opaque) of one idle motion over a screen window (label_check.rendered's rule)."""
    import label_check

    return label_check.rendered(
        sheet, pred.action_index, motion, pred.anchor_px, pred.scale, window
    )


@dataclass(frozen=True)
class Match:
    dx: int  # observed - rendered, px (positive: the client draws it further right / down)
    dy: int
    score: float  # masked NCC at the best offset (grey levels)
    score_at_zero: float | None  # at the rendered position itself
    motion: int  # the idle frame that matched best
    edge: bool  # the best offset sits on the search window's border (search too small)


def match_offset(
    frame_rgb: npt.NDArray[np.uint8],
    sheet: SpriteSheet,
    pred: SpritePrediction,
    radius: int = 24,
    max_motions: int = 8,
) -> Match | None:
    """The offset within +-``radius`` px where the rendered sprite best matches the frame (the
    best over up to ``max_motions`` idle frames spread over the loop). None when the rendered box
    is not wholly on screen or draws too little."""
    h, w = frame_rgb.shape[:2]
    i0, j0 = math.floor(pred.box[0]), math.floor(pred.box[1])
    i1, j1 = math.ceil(pred.box[2]), math.ceil(pred.box[3])
    if i0 < 0 or j0 < 0 or i1 > w or j1 > h or i1 - i0 < 4 or j1 - j0 < 4:
        return None
    si0, sj0 = max(0, i0 - radius), max(0, j0 - radius)
    si1, sj1 = min(w, i1 + radius), min(h, j1 + radius)
    image = frame_rgb[sj0:sj1, si0:si1, :3].astype(np.float64) @ GREY
    n = sheet.motions(pred.action_index)
    c = min(n, max_motions)
    motions = sorted({round(i * (n - 1) / max(1, c - 1)) for i in range(c)})  # spread, ends kept
    best: tuple[float, int, int, int] | None = None
    zero: float | None = None
    for m in motions:
        grey, opaque = rendered_grey(sheet, pred, int(m), (i0, j0, i1, j1))
        if int(opaque.sum()) < 30:
            continue
        ncc = masked_ncc(image, grey, opaque)
        z = ncc[j0 - sj0, i0 - si0]
        if np.isfinite(z) and (zero is None or z > zero):
            zero = float(z)
        if not np.isfinite(ncc).any():
            continue
        y, x = np.unravel_index(int(np.nanargmax(ncc)), ncc.shape)
        s = float(ncc[y, x])
        if best is None or s > best[0]:
            best = (s, int(x), int(y), int(m))
    if best is None:
        return None
    s, x, y, m = best
    dx, dy = x - (i0 - si0), y - (j0 - sj0)
    edge = (
        (x == 0 and si0 > 0)
        or (y == 0 and sj0 > 0)
        or (x == si1 - si0 - (i1 - i0) and si1 < w)
        or (y == sj1 - sj0 - (j1 - j0) and sj1 < h)
    )
    return Match(dx, dy, s, zero, m, bool(edge))


# --- the camera-state guard -----------------------------------------------------------------------

# PROVISIONAL (npc-render.md section 3 fixes them from the measured offsets): a default camera puts
# every well-seen NPC within MAX_OFFSET px of its render; a rotation moves anchors by tens to
# hundreds of px and turns the drawn direction, a zoom rescales every sprite.
PIXEL_MIN_SCORE = 0.5  # a match counts as "seen" at or above this NCC
PIXEL_MAX_OFFSET = 12.0  # px
PIXEL_MIN_SEEN = 2  # fewer seen NPCs: "unknown"


def pixel_camera_check(matches: Sequence[Match | None]) -> tuple[str, dict[str, int]]:
    """The runtime check (design, built offline): "default" when at least PIXEL_MIN_SEEN rendered
    NPCs are seen within PIXEL_MAX_OFFSET of their render and none is seen beyond it; "off" when
    one is seen strongly at a larger offset; "unknown" otherwise (too few seen: the gate falls back
    to the conservative L3 footprint and never trusts the rendered masks)."""
    seen = [m for m in matches if m is not None and m.score >= PIXEL_MIN_SCORE and not m.edge]
    near = [m for m in seen if math.hypot(m.dx, m.dy) <= PIXEL_MAX_OFFSET]
    far = [m for m in seen if math.hypot(m.dx, m.dy) > PIXEL_MAX_OFFSET]
    counts = {"seen": len(seen), "near": len(near), "far": len(far)}
    if far:
        return "off", counts
    if len(near) >= PIXEL_MIN_SEEN:
        return "default", counts
    return "unknown", counts


@dataclass(frozen=True)
class CameraEvent:
    t_ns: int
    kind: str  # "rotate" (a right-button drag in the world) | "zoom" (wheel)
    source: str


def camera_events(records: Iterable[dict[str, Any]]) -> list[CameraEvent]:
    """The input log's camera inputs. A RIGHT press is counted as a rotation (the client rotates
    on a right-drag; a right click without motion is counted too: fail closed). Any wheel is a
    zoom (over a window it scrolls instead; counted anyway: fail closed). Dropped inputs never
    reached the client."""
    out = []
    for r in records:
        if not r.get("accepted", True):
            continue
        ev = r.get("event") or {}
        if (
            ev.get("type") == "mouse_button"
            and ev.get("button") == "right"
            and ev.get("action") == "down"
        ):
            out.append(CameraEvent(int(r["t_mono_ns"]), "rotate", str(r.get("source"))))
        elif ev.get("type") == "wheel" and int(ev.get("dy") or 0) != 0:
            out.append(CameraEvent(int(r["t_mono_ns"]), "zoom", str(r.get("source"))))
    return sorted(out, key=lambda e: e.t_ns)


class CameraLog:
    """The camera state at a time from the input log (offline). A rotation lasts until the next
    MAP CHANGE (bench.py: a map change resets it, verified 2026-10-02; a same-map @warp does not).
    A zoom is NOT known to reset on a map change: it lasts to the end of the log (fail closed)."""

    def __init__(self, events: Iterable[CameraEvent], map_changes: Iterable[int]) -> None:
        self.events = sorted(events, key=lambda e: e.t_ns)
        self.map_changes = sorted(int(t) for t in map_changes)

    def state_at(self, t_ns: int) -> tuple[str, CameraEvent | None]:
        """("default" | "rotated" | "zoomed", the event that decided it)."""
        for e in reversed([e for e in self.events if e.t_ns <= t_ns]):
            if e.kind == "zoom":
                return "zoomed", e
            reset = any(e.t_ns < m <= t_ns for m in self.map_changes)
            if not reset:
                return "rotated", e
        return "default", None


LINE_T = re.compile(rb'^\{"t_mono_ns":\s*(\d+)')


def read_input_window(
    path: Path, t0_ns: int, t1_ns: int, slack_ns: int = 5_000_000_000
) -> list[dict[str, Any]]:
    """The input-log records with t0 <= t_mono_ns <= t1, read by a BINARY SEARCH over byte
    offsets and a forward read of that window only (CLAUDE.md rule 5: never a whole-file read;
    the log is ~10-60 MB a day on the shared disk). The log is appended in time order up to small
    reorderings, so the search starts ``slack_ns`` early."""
    out: list[dict[str, Any]] = []
    with path.open("rb") as fh:
        fh.seek(0, 2)
        size = fh.tell()

        def t_at(pos: int) -> tuple[int, int] | None:
            fh.seek(pos)
            if pos:
                fh.readline()
            while True:
                start = fh.tell()
                line = fh.readline()
                if not line:
                    return None
                m = LINE_T.match(line)
                if m:
                    return int(m[1]), start

        lo, hi = 0, size
        target = t0_ns - slack_ns
        while hi - lo > 4096:
            mid = (lo + hi) // 2
            got = t_at(mid)
            if got is None or got[0] >= target:
                hi = mid
            else:
                lo = mid
        fh.seek(lo)
        if lo:
            fh.readline()
        for line in fh:
            m = LINE_T.match(line)
            if not m:
                continue
            t = int(m[1])
            if t > t1_ns + slack_ns:
                break
            if t0_ns <= t <= t1_ns:
                out.append(json.loads(line))
    return out


# --- CLI ------------------------------------------------------------------------------------------


def _cell(text: str) -> tuple[float, float]:
    x, y = (float(v) for v in text.split(","))
    return x, y


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("render")
    p.add_argument("--map", required=True)
    p.add_argument("--cell", required=True, type=_cell)
    p.add_argument("--path", required=True, choices=sorted(CAMERA_PATHS))
    p.add_argument("--k", type=float, default=DEFAULT_K)
    p.add_argument("--kb", type=Path, default=KB)
    p.add_argument("--sprites", type=Path, default=SPRITES)
    p.add_argument("--names", type=Path, default=NAMES)
    p.add_argument("--gat-dir", type=Path, default=GAT_DIR)
    p = sub.add_parser("camera-log")
    p.add_argument("--input-log", type=Path, required=True)
    p.add_argument("--from", dest="t0", type=int, required=True)
    p.add_argument("--to", dest="t1", type=int, required=True)
    p.add_argument("--map-change", type=int, action="append", default=[])
    a = ap.parse_args(argv)
    if a.cmd == "camera-log":
        log = CameraLog(camera_events(read_input_window(a.input_log, a.t0, a.t1)), a.map_change)
        state, ev = log.state_at(a.t1)
        print(
            json.dumps(
                {
                    "events": [e.__dict__ for e in log.events],
                    "state_at_end": state,
                    "decided_by": None if ev is None else ev.__dict__,
                },
                indent=1,
            )
        )
        return 0 if state == "default" else 1
    try:
        res = render(
            a.map,
            a.cell,
            a.path,
            k=a.k,
            kb_dir=a.kb,
            gat_dir=a.gat_dir,
            sheets=sheets_from_files(a.sprites, a.names),
        )
    except Unsupported as exc:
        print(json.dumps({"refused": exc.reason, "detail": str(exc)}))
        return 2
    print(json.dumps(res.summary(), indent=1))
    return 0 if res.complete else 1


if __name__ == "__main__":
    raise SystemExit(main())
