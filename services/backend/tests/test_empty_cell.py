"""scripts/empty_cell.py (Post-S2 round B5): the walk-cursor template and the empty-cell pick."""

import importlib.util
import random
import sys
from pathlib import Path
from types import ModuleType

import numpy as np
import pytest

SCRIPTS = Path(__file__).resolve().parents[3] / "scripts"


@pytest.fixture(scope="module")
def ec() -> ModuleType:
    spec = importlib.util.spec_from_file_location("empty_cell", SCRIPTS / "empty_cell.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["empty_cell"] = module  # its dataclasses resolve annotations through it
    spec.loader.exec_module(module)
    return module


def _crop(
    background: int, marker: bool, rng: np.random.Generator, hp_bar: bool = False
) -> np.ndarray:
    """A 90x90 BGRA crop: floor, optionally the ground marker's four mint chevrons (RGB ~130/210/
    160, as measured live), optionally a monster's HP bar (a purer green, little blue)."""
    img = np.full((90, 90, 4), background, np.uint8)
    img[..., :3] = np.clip(img[..., :3] + rng.integers(-5, 6, (90, 90, 3)), 0, 255)
    if marker:
        for cy, cx in ((15, 45), (75, 45), (45, 15), (45, 75)):
            img[cy - 3 : cy + 3, cx - 6 : cx + 6, :3] = (160, 210, 130)  # BGR of RGB 130/210/160
    if hp_bar:
        img[70:74, 30:80, :3] = (34, 236, 16)  # BGR of RGB 16/236/34
    return img


def _grass(marker: bool, rng: np.random.Generator) -> np.ndarray:
    """Grass (RGB ~118/126/51) with the marker blended in (RGB ~69/170/93), as measured outdoors."""
    img = np.zeros((90, 90, 4), np.uint8)
    img[..., :3] = np.clip(np.array([51, 126, 118]) + rng.integers(-12, 13, (90, 90, 3)), 0, 255)
    if marker:
        for cy, cx in ((15, 45), (75, 45), (45, 15), (45, 75)):
            img[cy - 3 : cy + 3, cx - 6 : cx + 6, :3] = (93, 170, 69)
    return img


def test_the_ground_marker_tells_an_empty_cell_from_an_entity(ec: ModuleType) -> None:
    rng = np.random.default_rng(1)
    for floor in (60, 120, 200, 230):
        assert ec.is_empty_walk_cell(_crop(floor, True, rng)), floor
        assert not ec.is_empty_walk_cell(_crop(floor, False, rng)), floor  # nothing drawn
        assert not ec.is_empty_walk_cell(_crop(floor, False, rng, hp_bar=True)), floor  # monster
    assert ec.marker_px(_crop(120, True, rng)) == 4 * 6 * 12
    assert ec.is_empty_walk_cell(_grass(True, rng))  # outdoors: the blended marker
    assert not ec.is_empty_walk_cell(_grass(False, rng))  # grass alone is not the marker


def _flat_projector(offsets: np.ndarray, _origin: tuple[int, int]) -> np.ndarray:
    return np.c_[640 + offsets[:, 0] * 33, 380 - offsets[:, 1] * 33]


def test_pick_cell_respects_walls_the_click_band_and_the_hover_check(ec: ModuleType) -> None:
    walkable = np.zeros((40, 40), bool)
    walkable[20, 24] = True  # the only walkable cell in reach: (24, 20) = dx +4, dy 0 -> no
    walkable[23, 24] = True  # (24, 23): dx +4, dy +3
    rng = random.Random(7)
    pick = ec.pick_cell(rng, (20, 20), walkable, _flat_projector, tries=500)
    assert pick is not None and pick[:2] == (4, 3)
    assert ec.CLICK_BAND[1] <= pick[3] <= ec.CLICK_BAND[3]
    # the hover check refuses it -> nothing left
    pick = ec.pick_cell(random.Random(7), (20, 20), walkable, _flat_projector,
                        reject=lambda u, v: True, tries=200)  # fmt: skip
    assert pick is None
    # a click that would land on the chat window (far south) is never chosen
    tall = np.ones((40, 40), bool)
    for seed in range(50):
        p = ec.pick_cell(random.Random(seed), (20, 20), tall, _flat_projector, dy_range=(5, 9))
        assert p is None or ec.CLICK_BAND[1] <= p[3] <= ec.CLICK_BAND[3]
