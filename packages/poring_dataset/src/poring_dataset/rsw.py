"""A map's RSW model objects and their RSM meshes, placed in the world and projected with the lab's
camera: the screen box of every map model (orcsdun01 label fix 1c, docs/planning/
orcsdun01-detector.md 3b: "a label whose sprite box overlaps a model's projected box is EXCLUDED").

PORTED (the formats and the placement rule, re-expressed in Python/numpy; no code copied verbatim)
from nmeylan/nostalro-client @ 15b3029 (Apache-2.0, THIRD_PARTY.md):
  * lib/formats/src/rsw.rs: RSW 1.x-2.6. "GRSW" | major u8 | minor u8 | [build u32 from 2.5] |
    [u8 from 2.2] | ini, gnd, gat (40 bytes each) | [source, 40, from 1.4] | water (level 1.3+;
    type, wave height / speed / pitch 1.8+; anim speed 1.9+; none from 2.6) | light (longitude,
    latitude i32, diffuse, ambient vec3 1.5+; shadow alpha f32 1.7+) | ground bounds 4 x i32 (1.6+)
    | object count u32 | objects: type i32 then 1 MODEL (name 40, anim type i32, anim speed f32,
    block type i32 from 1.3; [u8 from 2.6 with build >= 186]; model file 80; node 80; position,
    rotation (degrees), scale vec3), 2 light (name 80, position, colour vec3, range f32), 3 sound
    (name 80, file 80, position, volume f32, width, height u32, range f32, [cycle f32 2.0+]),
    4 effect (name 80, position, type u32, emit speed f32, 4 params f32);
  * lib/formats/src/rsm.rs: RSM 1.x (2.x refused here: none on this map). "GRSM" | major | minor |
    anim length u32 | shade type u32 | [alpha u8 1.4+] | 16 reserved | textures (count, 40 each) |
    the root node's name (40) | nodes: name 40, parent 40, texture ids (count, u32 each), a 3x3
    (9 f32, read as COLUMNS), translation1 vec3, translation2 vec3, rotation angle f32, axis vec3,
    scale vec3, vertices (count, vec3), texture vertices (count; [colour u32 1.2+], u, v f32), faces
    (count; 3 vertex ids u16, 3 texture-vertex ids u16, texture u16, padding u16, two-sided i32,
    smooth group i32), [scale keys 1.6+ (count; frame i32, vec3, f32)], rotation keys (count; frame
    i32, quaternion x y z w);
  * lib/renderer/src/model.rs calc_bounding_box / node_post_matrix / bbox_shift_matrix /
    build_instance_matrix and lib/renderer/src/rsm_anim.rs node_local_matrix (frame 0): a node's
    vertex v is drawn at
        instance * shift * parents...node(T(translation2) R S) * [T(translation1) unless the model
        has ONE node] * M3x3 * v,
    R the first rotation key's quaternion, else the axis-angle; S the first scale key, else the
    node's scale; shift = T(-centre.x, -max.y, -centre.z) of the whole model's box (its bottom on
    the ground: RO's y axis points DOWN); instance = T(position + (map centre x, 0, map centre z))
    Rz Rx Ry S(scale), the angles in degrees, the map centre = half the map in world units.
That world: x = east, y = DOWN (an RO altitude, negative up, as the GAT's), z = north, 5 units per
GAT cell; an entity on cell (cx, cy) stands at ((cx + 0.5) * 5, h, (cy + 0.5) * 5) (nostalro
sprite_projection.rs project_entity_screen). The lab's camera frame (camera.py) is x east, y UP,
z north, relative to the player: ``to_cells`` converts.

The data is CLIENT data: an RSW / RSM is read from the client's GRF into /dev/shm at run time and
NEVER committed, and neither is anything derived from its geometry (CLAUDE.md rule 4). The tests
build theirs from synthetic bytes.
"""

import math
import struct
from dataclasses import dataclass, field

import numpy as np
import numpy.typing as npt

from poring_dataset.camera import CELL
from poring_dataset.render import Scene

Array = npt.NDArray[np.float64]
Box = tuple[float, float, float, float]


class RswError(ValueError):
    """Not an RSW / RSM, or a version this reader does not handle."""


class _Reader:
    def __init__(self, data: bytes) -> None:
        self.data, self.pos = data, 0

    def take(self, n: int) -> bytes:
        if self.pos + n > len(self.data):
            raise RswError(f"truncated at byte {self.pos} (+{n} of {len(self.data)})")
        out = self.data[self.pos : self.pos + n]
        self.pos += n
        return out

    def u8(self) -> int:
        return int(self.take(1)[0])

    def u16(self) -> int:
        return int(struct.unpack("<H", self.take(2))[0])

    def i32(self) -> int:
        return int(struct.unpack("<i", self.take(4))[0])

    def u32(self) -> int:
        return int(struct.unpack("<I", self.take(4))[0])

    def f32(self) -> float:
        return float(struct.unpack("<f", self.take(4))[0])

    def vec3(self) -> tuple[float, float, float]:
        x, y, z = struct.unpack("<3f", self.take(12))
        return float(x), float(y), float(z)

    def text(self, n: int) -> str:
        raw = self.take(n).split(b"\0", 1)[0]
        return raw.decode("cp949", errors="replace")


def _at_least(version: tuple[int, int], major: int, minor: int) -> bool:
    return version[0] > major or (version[0] == major and version[1] >= minor)


@dataclass(frozen=True)
class RswModel:
    index: int  # the object's position in the RSW's object list
    name: str
    model_file: str  # relative to data\model\
    node: str
    position: tuple[float, float, float]
    rotation: tuple[float, float, float]  # degrees
    scale: tuple[float, float, float]
    anim_type: int | None = None
    block_type: int | None = None


@dataclass(frozen=True)
class Rsw:
    version: tuple[int, int]
    gnd: str
    gat: str
    models: tuple[RswModel, ...]
    objects: dict[str, int]  # count per object kind


def parse_rsw(data: bytes) -> Rsw:
    r = _Reader(data)
    if r.take(4) != b"GRSW":
        raise RswError("magic is not GRSW")
    version = (r.u8(), r.u8())
    build = r.u32() if _at_least(version, 2, 5) else None
    if _at_least(version, 2, 2):
        r.u8()
    r.text(40)  # ini
    gnd, gat = r.text(40), r.text(40)
    if _at_least(version, 1, 4):
        r.text(40)  # source
    if not _at_least(version, 2, 6):
        if _at_least(version, 1, 3):
            r.f32()
        if _at_least(version, 1, 8):
            r.i32(), r.f32(), r.f32(), r.f32()
        if _at_least(version, 1, 9):
            r.u32()
    if _at_least(version, 1, 5):
        r.i32(), r.i32(), r.vec3(), r.vec3()
    if _at_least(version, 1, 7):
        r.f32()
    if _at_least(version, 1, 6):
        r.take(16)
    count = r.u32()
    models: list[RswModel] = []
    kinds = {"model": 0, "light": 0, "sound": 0, "effect": 0}
    for i in range(count):
        kind = r.i32()
        if kind == 1:
            name, anim, block = "", None, None
            if _at_least(version, 1, 3):
                name = r.text(40)
                anim = r.i32()
                r.f32()
                block = r.i32()
            if _at_least(version, 2, 6) and build is not None and build >= 186:
                r.u8()
            model_file, node = r.text(80), r.text(80)
            pos, rot, scl = r.vec3(), r.vec3(), r.vec3()
            models.append(RswModel(i, name, model_file, node, pos, rot, scl, anim, block))
            kinds["model"] += 1
        elif kind == 2:
            r.text(80), r.vec3(), r.vec3(), r.f32()
            kinds["light"] += 1
        elif kind == 3:
            r.text(80), r.text(80), r.vec3(), r.f32(), r.u32(), r.u32(), r.f32()
            if _at_least(version, 2, 0):
                r.f32()
            kinds["sound"] += 1
        elif kind == 4:
            r.text(80), r.vec3(), r.u32(), r.f32(), r.take(16)
            kinds["effect"] += 1
        else:
            raise RswError(f"object {i}: unknown type {kind} (the list cannot be walked further)")
    return Rsw(version, gnd, gat, tuple(models), kinds)


@dataclass(frozen=True)
class RsmNode:
    name: str
    parent: str
    matrix3: Array  # (3, 3): the file's 9 floats as COLUMNS
    translation1: tuple[float, float, float]
    translation2: tuple[float, float, float]
    rotation_angle: float
    rotation_axis: tuple[float, float, float]
    scale: tuple[float, float, float]
    vertices: Array = field(compare=False)  # (n, 3)
    rot_key0: tuple[float, float, float, float] | None = None  # the first key's x, y, z, w
    scale_key0: tuple[float, float, float] | None = None


@dataclass(frozen=True)
class Rsm:
    version: tuple[int, int]
    root: str
    nodes: tuple[RsmNode, ...]
    trailing: int = 0  # bytes after the last node (not read: 1.x keeps nothing there we need)


def parse_rsm(data: bytes) -> Rsm:
    r = _Reader(data)
    if r.take(4) != b"GRSM":
        raise RswError("magic is not GRSM")
    version = (r.u8(), r.u8())
    if _at_least(version, 2, 0):
        raise RswError(f"RSM {version[0]}.{version[1]}: only 1.x is read here")
    r.u32(), r.u32()  # anim length, shade type
    if _at_least(version, 1, 4):
        r.u8()  # alpha
    r.take(16)
    for _ in range(r.u32()):
        r.text(40)
    root = r.text(40)
    nodes = []
    for _ in range(r.u32()):
        name, parent = r.text(40), r.text(40)
        for _ in range(r.u32()):
            r.u32()
        m = np.array(struct.unpack("<9f", r.take(36)), dtype=float).reshape(3, 3).T
        t1, t2 = r.vec3(), r.vec3()
        angle, axis, scl = r.f32(), r.vec3(), r.vec3()
        nv = r.u32()
        verts = np.frombuffer(r.take(12 * nv), dtype="<f4").astype(float).reshape(nv, 3)
        ntv = r.u32()
        r.take(ntv * (12 if _at_least(version, 1, 2) else 8))
        nf = r.u32()
        r.take(nf * (24 if _at_least(version, 1, 2) else 20))
        scale_key0 = None
        if _at_least(version, 1, 6):
            keys = [(r.i32(), r.vec3(), r.f32()) for _ in range(r.u32())]
            scale_key0 = keys[0][1] if keys else None
        rot0: tuple[float, float, float, float] | None = None
        for i in range(r.u32()):
            r.i32()
            q = struct.unpack("<4f", r.take(16))
            if i == 0:
                rot0 = (float(q[0]), float(q[1]), float(q[2]), float(q[3]))
        nodes.append(RsmNode(name, parent, m, t1, t2, angle, axis, scl, verts, rot0, scale_key0))
    return Rsm(version, root, tuple(nodes), len(data) - r.pos)


# --- placement (frame 0) ---------------------------------------------------------------------


def _translate(v: tuple[float, float, float] | Array) -> Array:
    m = np.eye(4)
    m[:3, 3] = np.asarray(v, dtype=float)
    return m


def _scale(v: tuple[float, float, float] | Array) -> Array:
    return np.diag([*np.asarray(v, dtype=float), 1.0])


def _axis_angle(axis: tuple[float, float, float], angle: float) -> Array:
    a = np.asarray(axis, dtype=float)
    n = float(np.linalg.norm(a))
    if n == 0.0:
        return np.eye(4)
    x, y, z = a / n
    c, s, t = math.cos(angle), math.sin(angle), 1.0 - math.cos(angle)
    m = np.eye(4)
    m[:3, :3] = [[t * x * x + c, t * x * y - s * z, t * x * z + s * y],
                 [t * x * y + s * z, t * y * y + c, t * y * z - s * x],
                 [t * x * z - s * y, t * y * z + s * x, t * z * z + c]]  # fmt: skip
    return m


def _quat(q: tuple[float, float, float, float]) -> Array:
    """A quaternion (x, y, z, w) as a rotation, as glam's from_quat (the raw key: unit in the
    files; normalised here only to be safe)."""
    x, y, z, w = q
    n = math.sqrt(x * x + y * y + z * z + w * w)
    if n == 0.0:
        return np.eye(4)
    x, y, z, w = x / n, y / n, z / n, w / n
    m = np.eye(4)
    m[:3, :3] = [[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                 [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                 [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]]  # fmt: skip
    return m


def _rot(axis: str, deg: float) -> Array:
    c, s = math.cos(math.radians(deg)), math.sin(math.radians(deg))
    m = np.eye(4)
    i, j = {"x": (1, 2), "y": (2, 0), "z": (0, 1)}[axis]
    m[i, i], m[i, j], m[j, i], m[j, j] = c, -s, s, c
    return m


def node_local(node: RsmNode) -> Array:
    """T(translation2) R S at frame 0 (rsm_anim.rs node_local_matrix)."""
    rot = (_quat(node.rot_key0) if node.rot_key0 is not None
           else _axis_angle(node.rotation_axis, node.rotation_angle))  # fmt: skip
    scl = node.scale_key0 if node.scale_key0 is not None else node.scale
    return _translate(node.translation2) @ rot @ _scale(scl)


def node_post(node: RsmNode, only: bool) -> Array:
    m = np.eye(4) if only else _translate(node.translation1)
    m3 = np.eye(4)
    m3[:3, :3] = node.matrix3
    return m @ m3


def _accumulated(rsm: Rsm) -> dict[int, Array]:
    """Each REACHABLE node's parent chain from the root (model.rs node_accum_matrices)."""
    out: dict[int, Array] = {}
    names = {n.name: i for i, n in enumerate(rsm.nodes)}
    roots = [names[rsm.root]] if rsm.root in names else [0] if rsm.nodes else []

    def walk(i: int, parent: Array) -> None:
        if i in out:
            return
        node = rsm.nodes[i]
        out[i] = parent @ node_local(node)
        for j, child in enumerate(rsm.nodes):
            if j != i and child.parent == node.name and node.name != node.parent:
                walk(j, out[i])

    for i in roots:
        walk(i, np.eye(4))
    return out


def _apply(m: Array, pts: Array) -> Array:
    return np.asarray(pts @ m[:3, :3].T + m[:3, 3], dtype=float)


def model_space(rsm: Rsm) -> Array:
    """Every reachable vertex in the model's own space, shifted so its box's x/z centre is 0 and
    its BOTTOM (max y: RO's y points down) is at 0 (model.rs bbox_shift_matrix)."""
    only = len(rsm.nodes) == 1
    acc = _accumulated(rsm)
    parts = [_apply(acc[i] @ node_post(n, only), n.vertices) for i, n in enumerate(rsm.nodes)
             if i in acc and len(n.vertices)]  # fmt: skip
    if not parts:
        return np.zeros((0, 3))
    pts = np.concatenate(parts)
    lo, hi = pts.min(axis=0), pts.max(axis=0)
    centre = lo + (hi - lo) / 2.0
    return np.asarray(pts - np.array([centre[0], hi[1], centre[2]]), dtype=float)


def instance_matrix(model: RswModel, map_cells: tuple[int, int]) -> Array:
    """The RSW instance's placement (model.rs build_instance_matrix; GND zoom 10, so the scale
    factor is 1 and the map centre is half the map in world units)."""
    cx, cz = map_cells[0] * CELL / 2.0, map_cells[1] * CELL / 2.0
    p = model.position
    return (_translate((p[0] + cx, p[1], p[2] + cz)) @ _rot("z", model.rotation[2])
            @ _rot("x", model.rotation[0]) @ _rot("y", model.rotation[1])
            @ _scale(model.scale))  # fmt: skip


def world_points(rsm: Rsm, model: RswModel, map_cells: tuple[int, int]) -> Array:
    """The model's vertices in the RO world (x east, y DOWN, z north; 5 units per cell)."""
    return _apply(instance_matrix(model, map_cells), model_space(rsm))


def to_cells(world: Array) -> tuple[Array, Array]:
    """RO-world points -> (fractional cells (n, 2) in the frame entity cells use: cell (cx, cy)
    stands at its centre, (cx + 0.5) * 5; the altitude UP, world units (n,))."""
    w = np.asarray(world, dtype=float)
    cells = np.c_[w[:, 0] / CELL - 0.5, w[:, 2] / CELL - 0.5]
    return cells, -w[:, 1]


def player_altitude(scene: Scene) -> float:
    """The altitude (up) at the player's position: bilinear over cell centres, as
    render.anchor_and_depth's reference."""
    if scene.gat is None:
        return 0.0
    px, py = scene.player
    origin = (int(math.floor(px)), int(math.floor(py)))
    rel = scene.gat.relative_altitude(origin, np.array([[px - origin[0], py - origin[1]]]))
    return float(rel[0] + scene.gat.altitude_at(*origin))


def project_points(scene: Scene, cells: Array, alt_up: Array,
                   near: float = 1.0) -> tuple[Array, npt.NDArray[np.bool_]]:  # fmt: skip
    """(pixels (n, 2), in front of the camera (n,)) with the lab's camera at the scene's player:
    the same projection as render.anchor_and_depth (cell offsets, altitude relative to the
    player's)."""
    cam = scene.camera
    px, py = scene.player
    off = np.c_[cells[:, 0] - px, cells[:, 1] - py]
    alt = alt_up - player_altitude(scene)
    eye, _r, _u, forward = cam.basis()
    world = np.c_[off[:, 0] * CELL, alt, off[:, 1] * CELL]
    z = (world - eye) @ forward
    front = z > near
    uv = np.full((len(off), 2), np.nan)
    if front.any():
        uv[front] = cam.project(off[front], alt[front])
    return uv, front


def screen_box(scene: Scene, cells: Array, alt_up: Array) -> Box | None:
    """The 2-D box of a model's projected vertices (only those in front of the camera); None
    when none is."""
    uv, front = project_points(scene, cells, alt_up)
    if not front.any():
        return None
    p = uv[front]
    return (float(p[:, 0].min()), float(p[:, 1].min()), float(p[:, 0].max()),
            float(p[:, 1].max()))  # fmt: skip


def overlaps(a: Box, b: Box) -> bool:
    return min(a[2], b[2]) > max(a[0], b[0]) and min(a[3], b[3]) > max(a[1], b[1])
