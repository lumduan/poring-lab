"""scripts/walk6.py (walk@6, demonstrations 3.9): the ALLOWLIST gate. The cursor's own mask, the
two-sided match (extra content can never pass as the arrow), every cell of a run probed, the
target re-checked before the click -- tested against a fake client that draws the cursor."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import numpy as np
import pytest

SCRIPTS = Path(__file__).resolve().parents[3] / "scripts"


@pytest.fixture(scope="module")
def w6() -> ModuleType:
    sys.path.insert(0, str(SCRIPTS))
    for name in ("walk5", "walk6"):
        spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
        assert spec and spec.loader
        mod = importlib.util.module_from_spec(spec)
        sys.modules[name] = mod
        spec.loader.exec_module(mod)
    return sys.modules["walk6"]


# --- sprites (BGR), drawn with the hotspot at the cursor ----------------------------------------
def arrow() -> list[tuple[int, int]]:
    return [(dx, dy) for dy in range(0, 20) for dx in range(0, dy // 2 + 1)]


def sword() -> list[tuple[int, int]]:
    return [(k + e, k) for k in range(0, 18) for e in (-1, 0, 1)] + [(dx, 4) for dx in range(-3, 4)]


def ring() -> list[tuple[int, int]]:
    yy, xx = np.mgrid[-16:17, -16:17]
    r = np.hypot(xx - 4, yy - 10)
    return [(int(x), int(y)) for y, x in zip(*np.nonzero((r >= 9) & (r <= 12)), strict=True)
            for x, y in [(x - 16, y - 16)]]  # fmt: skip


WHITE, STEEL, RED = (235, 225, 225), (245, 245, 250), (30, 30, 220)
SPRITES: dict[str, list[tuple[list[tuple[int, int]], tuple[int, int, int]]]] = {
    "walk": [(arrow(), WHITE)],
    "sword": [(sword(), STEEL)],
    "noentry": [(arrow(), WHITE), (ring(), RED)],
}


def paint(img: np.ndarray, hx: int, hy: int, shape: str) -> None:
    for pts, colour in SPRITES[shape]:
        for dx, dy in pts:
            y, x = hy + dy, hx + dx
            if 0 <= y < img.shape[0] and 0 <= x < img.shape[1]:
                img[y, x, :3] = colour


def background(h: int, w: int, x0: int = 0, y0: int = 0) -> np.ndarray:
    yy, xx = np.mgrid[y0 : y0 + h, x0 : x0 + w]
    img = np.zeros((h, w, 4), np.uint8)
    img[..., 0] = 40 + (xx * 7 + yy * 3) % 30  # a textured floor, the same in every grab
    img[..., 1] = 60 + (xx * 5 + yy * 11) % 30
    img[..., 2] = 80 + (xx * 3 + yy * 5) % 30
    return img


def crop_pair(w6: ModuleType, shape: str) -> tuple[np.ndarray, np.ndarray]:
    b = background(64, 64)
    a = b.copy()
    paint(a, 32, 32, shape)
    return a[..., :3], b[..., :3]


def refs_for(w6: ModuleType, shapes: list[str]) -> Any:
    pairs = [crop_pair(w6, s) for s in shapes]
    return w6.CursorRefs([a for a, _ in pairs], [w6.cursor_mask(a, b) for a, b in pairs], shapes)


# --- the pieces -----------------------------------------------------------------------------------
def test_line_cells_are_the_run_without_its_start(w6: ModuleType) -> None:
    assert w6.line_cells((5, 5), (8, 5)) == [(6, 5), (7, 5), (8, 5)]
    assert w6.line_cells((5, 5), (3, 7)) == [(4, 6), (3, 7)]
    with pytest.raises(ValueError):
        w6.line_cells((5, 5), (8, 6))


def test_the_cursor_mask_is_the_sprite_without_the_chevrons(w6: ModuleType) -> None:
    a, b = crop_pair(w6, "walk")
    a = a.copy()
    a[10:16, 10:16] = (110, 200, 110)  # a chevron in the crop
    m = w6.cursor_mask(a, b)
    assert int(m.sum()) == len(arrow()) and not m[10:16, 10:16].any()


def test_the_match_is_two_sided_extra_content_never_passes_as_the_arrow(w6: ModuleType) -> None:
    """The no-entry sign is drawn OVER the arrow: every arrow pixel is there. A one-sided score
    (are the reference's pixels present?) called it the arrow (0.987 on the RDP calibration)."""
    refs = refs_for(w6, ["walk", "sword"])  # no no-entry reference at all
    for shape, want in (("walk", "walk"), ("sword", "sword"), ("noentry", "unknown")):
        a, b = crop_pair(w6, shape)
        got = refs.match(a, w6.cursor_mask(a, b))
        assert got["shape"] == want, (shape, got)
    full = refs_for(w6, ["walk", "sword", "noentry"])
    a, b = crop_pair(w6, "noentry")
    assert full.match(a, w6.cursor_mask(a, b))["shape"] == "noentry"


def test_no_cursor_is_unknown(w6: ModuleType) -> None:
    refs = refs_for(w6, ["walk"])
    b = background(64, 64)[..., :3]
    assert refs.match(b, w6.cursor_mask(b, b))["shape"] == "unknown"


# --- the control flow against a fake client -------------------------------------------------------
class Cam:
    def project(self, cells: np.ndarray, alt: object = None) -> np.ndarray:
        c = np.asarray(cells, dtype=float)
        return np.stack([640 + 30 * c[:, 0], 360 + 20 * c[:, 1]], axis=1)


class Gat:
    def __init__(self, walk: np.ndarray) -> None:
        self.w = walk
        self.altitude = np.zeros(walk.shape)

    def walkable(self) -> np.ndarray:
        return self.w

    def relative_altitude(self, origin: object, cells: object) -> np.ndarray:
        return np.zeros(len(np.asarray(cells)))


GX, GY = 80, 77


class Client:
    """Knows the TRUE cell and where the monsters stand; draws the cursor it would show (the arrow,
    a sword over a monster, the no-entry sign over a wall) and the chevrons on a free floor cell.
    A monster may walk onto a cell after a number of grabs (``arrives``)."""

    def __init__(self, w6: ModuleType, walk: np.ndarray, true: tuple[int, int],
                 monsters: set[tuple[int, int]] | None = None) -> None:  # fmt: skip
        self.w6, self.walk, self.true = w6, walk, true
        self.monsters = set(monsters or ())
        self.arrives: list[tuple[int, tuple[int, int]]] = []
        self.cursor = (0, 0)
        self.lag = 0  # grabs after a move that still show the cursor where it was (RDP lag)
        self.shown = (0, 0)
        self.pending = 0
        self.grabs = 0
        self.clicks: list[tuple[int, int]] = []
        self.attacked: list[tuple[int, int]] = []

    def cell_under(self, x: int, y: int) -> tuple[int, int]:
        u, v = x - GX, y - GY
        return (self.true[0] + round((u - 640) / 30), self.true[1] + round((v - 360) / 20))

    def move(self, x: int, y: int) -> None:
        if self.pending == 0:
            self.shown = self.cursor
        self.cursor = (x, y)
        self.pending = self.lag

    def click(self, x: int, y: int) -> None:
        self.clicks.append((x, y))
        c = self.cell_under(x, y)
        if c in self.monsters:
            self.attacked.append(c)
        elif self.walk[c[1], c[0]]:
            self.true = c

    def shape_at(self, c: tuple[int, int]) -> str:
        if c in self.monsters:
            return "sword"
        return "walk" if self.walk[c[1], c[0]] else "noentry"

    def grab(self, x: int, y: int, w: int, h: int) -> tuple[int, np.ndarray]:
        self.grabs += 1
        for after, cell in list(self.arrives):
            if self.grabs > after:
                self.monsters.add(cell)
                self.arrives.remove((after, cell))
        img = background(h, w, x, y)
        cx, cy = self.cursor
        if self.pending:
            self.pending -= 1
            cx, cy = self.shown
        c = self.cell_under(cx, cy)
        shape = self.shape_at(c)
        if shape == "walk":
            rel = np.array([c[0] - self.true[0], c[1] - self.true[1]], dtype=float)
            for ax, ay in Cam().project(rel + np.asarray(self.w6.rr.MARKER_ANCHORS)):
                px, py = round(ax + GX - x), round(ay + GY - y)
                if 3 <= px < w - 3 and 3 <= py < h - 3:
                    img[py - 3 : py + 3, px - 3 : px + 3, :3] = (110, 200, 110)
        paint(img, cx - x, cy - y, shape)
        return 0, img


@pytest.fixture
def fake(w6: ModuleType, monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    for mod in (w6, w6.w5):
        monkeypatch.setattr(mod.time, "sleep", lambda s: None)
    monkeypatch.setattr(w6.r, "game_region", lambda: (GX, GY, 1280, 720))
    monkeypatch.setattr(w6.r, "ns", lambda: 0)
    return w6


BAND = (100, 60, 1180, 680)


def ring_mask() -> np.ndarray:
    yy, xx = np.mgrid[0:64, 0:64]
    return (np.hypot(xx - 36, yy - 42) >= 9) & (np.hypot(xx - 36, yy - 42) <= 12)


def route(fake: ModuleType, client: Client, start: tuple[int, int], goal: tuple[int, int],
          seg: int = 3) -> tuple[dict[str, Any], Any]:  # fmt: skip
    pr = fake.Prober(client, client, refs_for(fake, ["walk", "sword", "noentry"]))
    w = fake.w5.World(Cam(), Gat(client.walk), start)
    return fake.walk_route(pr, w, goal, BAND, seg, lambda *a: None, ring_mask()), w


def test_a_free_route_walks_runs_of_at_most_the_context_length(fake: ModuleType) -> None:
    walk = np.ones((60, 60), dtype=bool)
    client = Client(fake, walk, (10, 18))
    did, _ = route(fake, client, (10, 18), (19, 18), seg=3)
    assert did.get("arrived_belief") and client.true == (19, 18), did
    runs = [e for e in did["events"] if e.get("clicked")]
    assert len(runs) == 3 and all(len(e["line"]) == 2 for e in runs)  # 2 line cells + the target
    assert all(x["shape"] == "walk" for e in runs for x in e["line"] + e["target"])
    assert all("recheck" in e["target"][-1] for e in runs)


def test_a_monster_on_the_line_is_never_clicked_through_waited_for_then_routed_around(
    fake: ModuleType,
) -> None:
    walk = np.ones((60, 60), dtype=bool)
    client = Client(fake, walk, (10, 18), monsters={(12, 18)})
    did, _ = route(fake, client, (10, 18), (16, 18), seg=3)
    assert did.get("arrived_belief") and client.true == (16, 18), did
    assert client.attacked == [] and did["replans"] == 1
    refused = [e for e in did["events"] if "clicked" in e and not e["clicked"]]
    assert [e["outcome"] for e in refused] == ["line_sword", "line_sword"]  # once, then waited
    assert all(tuple(e["end"]) != (12, 18) for e in did["events"] if e.get("clicked"))


def test_a_monster_walking_onto_the_target_is_caught_by_the_re_check(fake: ModuleType) -> None:
    walk = np.ones((60, 60), dtype=bool)
    client = Client(fake, walk, (10, 18))
    pr = fake.Prober(client, client, refs_for(fake, ["walk", "sword", "noentry"]))
    w = fake.w5.World(Cam(), Gat(walk), (10, 18))
    # grabs: 1-2 the park (before + after), 3 line (11,18), 4 line (12,18), 5 the target
    # (13,18); the monster arrives after the 5th grab: the re-check (the 6th) sees it
    client.arrives.append((5, (13, 18)))
    step = fake.segment_step(pr, w, (13, 18))
    assert not step["clicked"] and step["outcome"] == "recheck_sword", step
    assert client.clicks == [] and client.attacked == []


def test_an_unknown_shape_is_never_safe(fake: ModuleType) -> None:
    """Only a positive WALK match passes: with no sword reference, a monster is UNKNOWN: no
    click."""
    walk = np.ones((60, 60), dtype=bool)
    client = Client(fake, walk, (10, 18), monsters={(11, 18)})
    pr = fake.Prober(client, client, refs_for(fake, ["walk"]))
    w = fake.w5.World(Cam(), Gat(walk), (10, 18))
    step = fake.segment_step(pr, w, (13, 18))
    assert not step["clicked"] and step["outcome"] == "line_unknown"
    assert step["line"][0]["grabs"] == fake.SHAPE_GRABS  # it looked again while unknown


def test_any_entity_shortens_the_runs_for_the_rest_of_the_route(fake: ModuleType) -> None:
    walk = np.ones((60, 60), dtype=bool)
    client = Client(fake, walk, (10, 18), monsters={(12, 17)})
    pr = fake.Prober(client, client, refs_for(fake, ["walk", "sword", "noentry"]))
    w = fake.w5.World(Cam(), Gat(walk), (10, 17))
    client.true = (10, 17)
    did = fake.walk_route(pr, w, (22, 17), BAND, 5, lambda *a: None, ring_mask())
    assert did.get("arrived_belief") and client.attacked == [], did
    seg_max = [e["seg_max"] for e in did["events"] if "seg_max" in e]
    assert seg_max[0] == 5 and seg_max[-1] == fake.SEG_CROWDED


def test_a_stale_parked_frame_is_grabbed_again_until_the_cursor_has_left(
    fake: ModuleType,
) -> None:
    """The pilot (17:36): after a wait-and-retry the parked frame still showed the cursor on the
    cell about to be probed, so |A - B| lost the cursor and the read was UNKNOWN."""
    walk = np.ones((60, 60), dtype=bool)
    client = Client(fake, walk, (10, 18), monsters={(11, 18)})
    pr = fake.Prober(client, client, refs_for(fake, ["walk", "sword", "noentry"]))
    w = fake.w5.World(Cam(), Gat(walk), (10, 18))
    first = fake.segment_step(pr, w, (13, 18))
    assert first["outcome"] == "line_sword"
    client.lag = 2  # the next park: two grabs still show the cursor on (11, 18)
    again = fake.segment_step(pr, w, (13, 18))
    assert again["outcome"] == "line_sword" and again["line"][0]["shape"] == "sword", again
    assert pr.stale == 0
