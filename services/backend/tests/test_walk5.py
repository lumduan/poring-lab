"""scripts/walk5.py (walk@5, demonstrations 3.8): A* segments, the hover probe, and re-localisation
by the map's structure -- tested against a fake client that knows the TRUE position."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import numpy as np
import pytest

SCRIPTS = Path(__file__).resolve().parents[3] / "scripts"


@pytest.fixture(scope="module")
def w5() -> ModuleType:
    sys.path.insert(0, str(SCRIPTS))
    spec = importlib.util.spec_from_file_location("walk5", SCRIPTS / "walk5.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["walk5"] = mod
    spec.loader.exec_module(mod)
    return mod


def test_a_path_splits_at_turns_and_every_five_cells(w5: ModuleType) -> None:
    path = [(x, 0) for x in range(1, 8)] + [(7 + k, k) for k in range(1, 3)]
    assert w5.split_segments((0, 0), path) == [(5, 0), (7, 0), (9, 2)]
    assert w5.split_segments((0, 0), []) == []


def test_the_gat_grid_plans_around_a_wall(w5: ModuleType) -> None:
    from poring_dataset.walk import walk_path

    walk = np.ones((10, 10), dtype=bool)
    walk[2:8, 5] = False  # a wall
    path = walk_path(w5.GatGrid(walk), 2, 5, 8, 5)
    assert path is not None and path[-1] == (8, 5)
    assert all(walk[y, x] for x, y in path)
    ends = w5.split_segments((2, 5), path)
    assert ends[-1] == (8, 5) and len(ends) >= 2  # it had to turn


def test_probe_choice_splits_candidates_and_eliminates(w5: ModuleType) -> None:
    walk = np.ones((12, 12), dtype=bool)
    walk[:, 8] = False  # a wall at x = 8
    alt = np.zeros((12, 12))
    cands = [(5, 5), (6, 5)]
    o = w5.best_probe(cands, walk, alt, [(2, 0), (3, 0), (0, 2)])
    assert o in ((2, 0), (3, 0))  # (0, 2) cannot tell them apart
    left = w5.eliminate(cands, walk, (2, 0), walk=False)  # the probe saw the no-entry sign
    assert left == [(6, 5)]


def test_the_ring_score_ignores_a_red_blob(w5: ModuleType) -> None:
    yy, xx = np.mgrid[0:64, 0:64]
    ring = (np.hypot(xx - 36, yy - 44) >= 9) & (np.hypot(xx - 36, yy - 44) <= 12)
    sign = np.zeros((64, 64, 3), np.uint8)
    sign[ring] = (30, 30, 220)  # BGR red
    blob = np.zeros((64, 64, 3), np.uint8)
    blob[38:50, 30:42] = (30, 30, 220)  # hair: a filled patch
    assert w5.noentry_score(sign, ring) == 1.0
    assert w5.noentry_score(blob, ring) < w5.NOENTRY_MIN


# --- the control flow against a fake client --------------------------------------------------
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


RING = None


class Client:
    """Knows the TRUE cell; draws chevrons on the cell under the cursor (or the no-entry ring)."""

    def __init__(self, w5: ModuleType, walk: np.ndarray, true: tuple[int, int]) -> None:
        self.w5, self.walk, self.true = w5, walk, true
        self.cursor = (0, 0)
        self.clicks: list[tuple[int, int]] = []

    def cell_under(self, x: int, y: int) -> tuple[int, int]:
        u, v = x - 80, y - 77
        return (self.true[0] + round((u - 640) / 30), self.true[1] + round((v - 360) / 20))

    def move(self, x: int, y: int) -> None:
        self.cursor = (x, y)

    def click(self, x: int, y: int) -> None:
        self.clicks.append((x, y))
        c = self.cell_under(x, y)
        if self.walk[c[1], c[0]]:
            self.true = c

    def grab(self, x: int, y: int, w: int, h: int) -> tuple[int, np.ndarray]:
        img = np.zeros((h, w, 4), np.uint8)
        cx, cy = self.cursor
        c = self.cell_under(cx, cy)
        if not self.walk[c[1], c[0]]:
            yy, xx = np.mgrid[0:64, 0:64]
            ring = (np.hypot(xx - 36, yy - 44) >= 9) & (np.hypot(xx - 36, yy - 44) <= 12)
            sub = img[28:92, 28:92]
            sub[ring] = (30, 30, 220, 0)
            return 0, img
        rel = np.array([c[0] - self.true[0], c[1] - self.true[1]], dtype=float)
        anchors = Cam().project(rel + np.asarray(self.w5.rr.MARKER_ANCHORS))
        for ax, ay in anchors:
            px, py = round(ax + 80 - x), round(ay + 77 - y)
            img[py - 3 : py + 3, px - 3 : px + 3, :3] = (110, 200, 110)
        return 0, img


@pytest.fixture
def fake(w5: ModuleType, monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    monkeypatch.setattr(w5.time, "sleep", lambda s: None)
    monkeypatch.setattr(w5.r, "game_region", lambda: (80, 77, 1280, 720))
    monkeypatch.setattr(w5.r, "ns", lambda: 0)
    return w5


def mask() -> np.ndarray:
    yy, xx = np.mgrid[0:64, 0:64]
    return (np.hypot(xx - 36, yy - 44) >= 9) & (np.hypot(xx - 36, yy - 44) <= 12)


BAND = (100, 60, 1180, 680)


def test_a_route_with_a_true_belief_walks_its_segments_to_the_goal(fake: ModuleType) -> None:
    walk = np.ones((40, 40), dtype=bool)
    walk[10:25, 20] = False
    client = Client(fake, walk, (15, 18))
    w = fake.World(Cam(), Gat(walk), (15, 18))
    segs: list[tuple] = []
    did = fake.walk_route(client, client, w, (25, 18), mask(), BAND,
                          lambda t, f, e, s: segs.append((f, e, s["clicked"])))  # fmt: skip
    assert did.get("arrived_belief") and client.true == (25, 18) and did["relocs"] == 0
    assert all(c for *_, c in segs) and all(max(abs(e[0] - f[0]), abs(e[1] - f[1])) <= 5
                                            for f, e, _ in segs)  # fmt: skip


def test_a_wrong_belief_is_caught_by_the_no_entry_sign_and_relocalised(fake: ModuleType) -> None:
    """Believed 2 cells west of the truth. The first segment's end, seen from the TRUE cell, lies
    in a wall: no-entry on a GAT-walkable cell -> re-localise (a wall on each axis) -> re-plan."""
    walk = np.ones((40, 40), dtype=bool)
    walk[:, 23] = False  # a wall along x = 23
    walk[11, :] = False  # and one along y = 11
    client = Client(fake, walk, (21, 15))
    w = fake.World(Cam(), Gat(walk), (19, 15))
    did = fake.walk_route(client, client, w, (21, 18), mask(), BAND, lambda *a: None)
    relocs = [e["relocalise"] for e in did["events"] if "relocalise" in e]
    assert len(relocs) == 1 and relocs[0]["ok"] and relocs[0]["to"] == [21, 15]
    assert did["events"][0]["outcome"] == "noentry" and not did["events"][0]["clicked"]
    assert client.true == (21, 18) and did.get("arrived_belief")


def test_a_wrong_belief_whose_cell_is_walkable_is_not_caught(fake: ModuleType) -> None:
    """The stated limit: when the truth + the same offset is walkable too, the client draws a
    consistent marker and the rule clicks; only the packets show the miss."""
    walk = np.ones((40, 40), dtype=bool)
    client = Client(fake, walk, (21, 15))
    w = fake.World(Cam(), Gat(walk), (19, 15))
    did = fake.walk_route(client, client, w, (22, 15), mask(), BAND, lambda *a: None)
    assert did.get("arrived_belief") and client.true == (24, 15)  # 2 cells past the goal
