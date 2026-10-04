"""RO's default camera as a physical model: perspective, looking at the player, a few parameters
(Phase 2, B4 follow-up; Batt 2026-10-03: "port the camera model, fit our calibration as a camera,
keep the winner").

PORTED (the model, re-expressed in numpy; no code copied verbatim) from two permissively licensed
clients, read at these exact commits (THIRD_PARTY.md):
  * nmeylan/nostalro-client @ 15b3029 (Apache-2.0), lib/renderer/src/camera.rs: the eye on a
    sphere around the target (yaw, pitch, distance), look-at, a 15 degree vertical FOV, default
    pitch 55 degrees;
  * vE5li/korangar @ e14d320 (MIT), korangar/src/world/cameras/player.rs: the same rig (pitch -55
    degrees, FOV 15.5 degrees, default distance 400).
Both agree on the rig; the numbers here are FITTED to our client, not taken from either.

World frame (ours): X east = cell dx * 5, Z north = cell dy * 5 (5 world units per GAT cell), Y up
= altitude (a GAT height is negative-up, so up = -height). The target is the player's feet. With
yaw 0 the eye is south of and above the target, looking north; screen v grows downwards.

Why it can beat a homography: a homography maps ONE plane. The camera is a 3-D projection, so a
cell's ALTITUDE (from the map's GAT) moves its pixel the way the client draws it -- the flat-ground
assumption is the first suspect for the projection's residual tail (phase2-plan B4).

INDOOR maps (Post-S2 round B1, 2026-10-04): the client draws them with the camera ROTATED. PORTED
(the rule, re-expressed; no code copied) from nostalro-client @ 15b3029 (Apache-2.0,
THIRD_PARTY.md): a map is indoor iff "<map>.rsw" is listed in the client's
data/indoorrswtable.txt (map_loader.rs:85-90), and an indoor map forces the yaw 45 degrees off the
outdoor default (camera.rs:189-209); pitch, FOV and the default distance are unchanged. The table is
CLIENT data, read from the GRF into /dev/shm at run time (grf_read.py extract), never committed.
The sign in OUR yaw convention is measured (B2, scripts/camera_validate.py) and recorded in
camera_<backend>.json ("indoor"); INDOOR_YAW_DEG is the default until then.

Billboard FACING (B4): the sprite direction a client draws = nostalro act.rs:568-570,
(camera_dir + 12 - heading) % 8, where camera_dir is the camera's look direction as an RO heading
(0 = north, counter-clockwise) -- displayed_direction() below.
"""

import json
import os
from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path

import numpy as np
import numpy.typing as npt

Array = npt.NDArray[np.float64]
# offsets from the player (N, 2) cells, the player's map cell -> pixels (N, 2)
Projector = Callable[[Array, tuple[int, int]], Array]
GAT_DIR = Path(os.environ.get("PORING_GAT_DIR", "/dev/shm/poring-lab-tmp/gat/data"))
CELL = 5.0  # world units per GAT cell
NAMES = ("yaw", "pitch", "distance", "fov", "cx", "cy")
INDOOR_TABLE = "indoorrswtable.txt"  # the client's data/indoorrswtable.txt, extracted into GAT_DIR
INDOOR_YAW_DEG = -45.0  # nostalro camera.rs:189-209; the sign in our convention is B2's to confirm
INDOOR_SOURCE = (
    "nmeylan/nostalro-client@15b3029 (Apache-2.0): map_loader.rs:85-90 (indoorrswtable.txt), "
    "camera.rs:189-209 (indoor yaw 45 degrees off the default; pitch/FOV/distance unchanged)"
)
# The sprite (ACT) directions, as drawn on screen: 0 = facing the viewer ... 4 = the back.
SPRITE_DIRECTIONS = ("S", "SW", "W", "NW", "N", "NE", "E", "SE")


@dataclass(frozen=True)
class Camera:
    yaw: float  # radians, rotation of the eye around the vertical axis
    pitch: float  # radians above the horizon
    distance: float  # eye <-> target, world units
    fov: float  # vertical field of view, radians
    cx: float  # where the target lands on screen (pixels)
    cy: float
    height: int = 720  # the client area's height in pixels (the FOV spans it)

    def vector(self) -> Array:
        return np.array([getattr(self, n) for n in NAMES], dtype=float)

    @classmethod
    def from_vector(cls, v: Array, height: int = 720) -> "Camera":
        yaw, pitch, distance, fov, cx, cy = (float(x) for x in v)
        return cls(yaw, pitch, distance, fov, cx, cy, height=height)

    def basis(self) -> tuple[Array, Array, Array, Array]:
        """(eye, right, up, forward) in the world frame."""
        cp, sp = np.cos(self.pitch), np.sin(self.pitch)
        offset = np.array([-np.sin(self.yaw) * cp, sp, -np.cos(self.yaw) * cp]) * self.distance
        eye = offset  # the target is the origin
        forward = -offset / np.linalg.norm(offset)
        world_up = np.array([0.0, 1.0, 0.0])
        right = np.cross(world_up, forward)
        right /= np.linalg.norm(right)
        up = np.cross(forward, right)
        return eye, right, up, forward

    def project(self, cells: Array, altitude: Array | None = None) -> Array:
        """Cell offsets from the player (N, 2) [+ altitude relative to the player's cell, world
        units, up positive] -> pixels (N, 2) in the client area."""
        cells = np.asarray(cells, dtype=float)
        alt = np.zeros(len(cells)) if altitude is None else np.asarray(altitude, dtype=float)
        world = np.c_[cells[:, 0] * CELL, alt, cells[:, 1] * CELL]
        eye, right, up, forward = self.basis()
        rel = world - eye
        z = rel @ forward
        f = (self.height / 2) / np.tan(self.fov / 2)
        u = self.cx + f * (rel @ right) / z
        v = self.cy - f * (rel @ up) / z
        return np.asarray(np.c_[u, v], dtype=float)


@dataclass(frozen=True)
class CameraFit:
    camera: Camera
    residuals_px: Array
    free: tuple[str, ...]

    @property
    def median_px(self) -> float:
        return float(np.median(self.residuals_px))

    @property
    def p95_px(self) -> float:
        return float(np.percentile(self.residuals_px, 95))


def _residuals(
    cam: Camera, free: tuple[str, ...], x: Array, cells: Array, px: Array, alt: Array | None
) -> Array:
    values = {n: float(v) for n, v in zip(free, x, strict=True)}
    trial = replace(cam, **values)  # type: ignore[arg-type]  # only float fields are free
    return (trial.project(cells, alt) - px).ravel()


def fit_camera(
    cells: Array,
    px: Array,
    *,
    altitude: Array | None = None,
    start: Camera | None = None,
    free: tuple[str, ...] = ("yaw", "pitch", "distance", "cx", "cy"),
    iterations: int = 200,
) -> CameraFit:
    """Levenberg-Marquardt on the pixel residuals (numeric Jacobian). ``free``: the parameters
    fitted; the rest stay at ``start`` (default: the clients' rig, FOV 15 degrees)."""
    cells, px = np.asarray(cells, dtype=float), np.asarray(px, dtype=float)
    best: CameraFit | None = None
    starts = [start] if start is not None else [
        Camera(np.radians(y), np.radians(55), 400.0, np.radians(15), 640.0, 360.0)
        for y in range(0, 360, 45)
    ]  # fmt: skip
    for cam0 in starts:
        x = np.array([getattr(cam0, n) for n in free], dtype=float)
        lam = 1e-3
        r = _residuals(cam0, free, x, cells, px, altitude)
        cost = float(r @ r)
        for _ in range(iterations):
            jac = np.empty((len(r), len(x)))
            for j in range(len(x)):
                step = 1e-6 * max(1.0, abs(x[j]))
                xp = x.copy()
                xp[j] += step
                jac[:, j] = (_residuals(cam0, free, xp, cells, px, altitude) - r) / step
            jtj, jtr = jac.T @ jac, jac.T @ r
            improved = False
            for _ in range(10):
                try:
                    delta = np.linalg.solve(jtj + lam * np.diag(np.diag(jtj) + 1e-12), -jtr)
                except np.linalg.LinAlgError:
                    lam *= 10
                    continue
                xn = x + delta
                rn = _residuals(cam0, free, xn, cells, px, altitude)
                cn = float(rn @ rn)
                if np.isfinite(cn) and cn < cost:
                    x, r, cost, lam, improved = xn, rn, cn, lam / 3, True
                    break
                lam *= 10
            if not improved or float(np.linalg.norm(delta)) < 1e-10:
                break
        fitted = {n: float(v) for n, v in zip(free, x, strict=True)}
        cam = replace(cam0, **fitted)  # type: ignore[arg-type]  # only float fields are free
        res = np.linalg.norm(cam.project(cells, altitude) - px, axis=1)
        if best is None or float(res @ res) < float(best.residuals_px @ best.residuals_px):
            best = CameraFit(cam, res, free)
    assert best is not None
    return best


def camera_from_json(block: dict[str, float], height: int = 720) -> Camera:
    return Camera.from_vector(np.array([float(block[n]) for n in NAMES]), height)


class IndoorTableMissing(FileNotFoundError):
    """The client's indoor-map table is not extracted: indoor maps cannot be told from outdoor
    ones, and an outdoor camera on an indoor map gives wrong labels (the 2026-10-04 indoor set)."""


def map_key(map_name: str) -> str:
    """'prt_church.gat' / 'PRT_CHURCH.rsw' / 'prt_church' -> 'prt_church'."""
    name = map_name.strip().lower()
    for ext in (".gat", ".rsw"):
        if name.endswith(ext):
            name = name[: -len(ext)]
    return name


def parse_indoor_table(text: str) -> frozenset[str]:
    """One "<map>.rsw" per line (a trailing '#' is the client's terminator), '//' comments."""
    names = set()
    for raw in text.splitlines():
        line = raw.split("//", 1)[0].strip().rstrip("#").strip()
        if line:
            names.add(map_key(line))
    return frozenset(names)


def load_indoor_table(gat_dir: Path = GAT_DIR) -> frozenset[str]:
    """The client's indoor maps. Raises IndoorTableMissing (fail closed) when it is not extracted:
    ``grf_read.py extract <data.grf> data/indoorrswtable.txt`` into the GAT dir."""
    path = gat_dir / INDOOR_TABLE
    if not path.exists():
        raise IndoorTableMissing(
            f"{path} is missing: extract data/indoorrswtable.txt from the client's GRF into "
            f"{gat_dir} (scripts/grf_read.py extract) -- client data, never committed"
        )
    return parse_indoor_table(path.read_bytes().decode("latin-1"))


def is_indoor(map_name: str | None, table: frozenset[str]) -> bool:
    return bool(map_name) and map_key(str(map_name)) in table


def indoor_yaw_deg(camera_json: dict[str, object]) -> float:
    """The measured indoor offset when B2 recorded one (camera_<backend>.json "indoor"), else the
    ported default."""
    block = camera_json.get("indoor")
    if isinstance(block, dict) and isinstance(block.get("yaw_deg"), int | float):
        return float(block["yaw_deg"])
    return INDOOR_YAW_DEG


def camera_for_map(fitted: Camera, indoor: bool, yaw_offset_deg: float = INDOOR_YAW_DEG) -> Camera:
    """The camera the client uses on a map: the fitted (outdoor) default, rotated on indoor maps."""
    return replace(fitted, yaw=fitted.yaw + np.radians(yaw_offset_deg)) if indoor else fitted


def projector_for(
    camera_json: dict[str, object],
    map_name: str | None,
    gat_dir: Path = GAT_DIR,
    *,
    indoor_table: frozenset[str] | None = None,
) -> tuple[Projector, str]:
    """(projector, which): the perspective camera + the map's GAT altitude when both exist (the
    held-out winner, 2026-10-03), else the flat homography ``h``. The GAT is client data that
    lives only in /dev/shm (grf_read.py extract --decode-des), never in the repository.

    Indoor maps (B1) ALWAYS use the rotated camera -- flat when the GAT is missing -- never the
    homography, which was fitted on the outdoor default. ``indoor_table``: the client's indoor maps
    (default: load_indoor_table(gat_dir), which fails closed when it is not extracted)."""
    from poring_dataset import gat as gatmod
    from poring_dataset.projection import project

    table = load_indoor_table(gat_dir) if indoor_table is None else indoor_table
    block = camera_json.get("camera")
    if map_name:
        map_name = map_key(map_name)  # the map-change packet names it "prt_fild08.gat"
    indoor = is_indoor(map_name, table)
    path = gat_dir / f"{map_name}.gat" if map_name else None
    if indoor and not isinstance(block, dict):
        raise ValueError(f"{map_name} is indoor and the camera json has no fitted camera")
    if isinstance(block, dict) and (indoor or (path is not None and path.exists())):
        fitted = camera_from_json(block, int(block.get("height", 720)))
        cam = camera_for_map(fitted, indoor, indoor_yaw_deg(camera_json))
        tag = f"{'indoor ' if indoor else ''}{map_name}"
        if path is None or not path.exists():
            return (lambda offsets, _origin: cam.project(offsets)), f"camera(flat):{tag}"
        grid = gatmod.parse(path.read_bytes())

        def perspective(offsets: Array, origin: tuple[int, int]) -> Array:
            return cam.project(offsets, grid.relative_altitude(origin, offsets))

        return perspective, f"camera+gat:{tag}"
    h = np.asarray(camera_json["h"], dtype=float)
    return (lambda offsets, _origin: project(h, offsets)), "homography"


def map_camera(
    camera_json: dict[str, object], map_name: str | None, indoor_table: frozenset[str]
) -> Camera | None:
    """The camera the client uses on ``map_name`` (rotated when indoor), or None without a fit."""
    block = camera_json.get("camera")
    if not isinstance(block, dict):
        return None
    fitted = camera_from_json(block, int(block.get("height", 720)))
    return camera_for_map(fitted, is_indoor(map_name, indoor_table), indoor_yaw_deg(camera_json))


# --- movement and facing under a rotated camera (B3, B4) ------------------------------------------


def screen_vector(cam: Camera, dxdy: tuple[float, float]) -> Array:
    """The on-screen pixel displacement of a flat world step (dx east, dy north, cells) away from
    the player: what "walk 3 cells north" looks like through this camera."""
    pts = cam.project(np.array([[0.0, 0.0], [float(dxdy[0]), float(dxdy[1])]]))
    return np.asarray(pts[1] - pts[0], dtype=float)


def click_for_cell(
    projector: Projector, offset: tuple[int, int], origin: tuple[int, int]
) -> tuple[float, float]:
    """Client-area pixel to click to walk to the cell ``offset`` (cells) away from the player at
    ``origin`` -- through the map's own projector, so rotated (indoor) maps walk where meant."""
    ((u, v),) = projector(np.array([[float(offset[0]), float(offset[1])]]), origin)
    return float(u), float(v)


def look_heading(yaw: float) -> int:
    """The camera's look direction as an RO heading: 0 = north, counter-clockwise in 45 degree
    steps (2 = west, 4 = south, 6 = east). Our yaw 0 looks north; +90 degrees looks east."""
    return int(round(float(-np.degrees(yaw)) / 45.0)) % 8


def displayed_direction(heading: int, yaw: float) -> int:
    """The sprite direction a billboard shows (SPRITE_DIRECTIONS index: 0 = facing the viewer,
    4 = its back) for an entity with RO ``heading`` under a camera at ``yaw``. Ported from
    nostalro act.rs:568-570: (camera_dir + 12 - heading) % 8, camera_dir = look_heading(yaw)."""
    return (look_heading(yaw) + 12 - int(heading)) % 8


def load_camera_json(path: Path) -> dict[str, object]:
    data: dict[str, object] = json.loads(path.read_text())
    return data
