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


def _crop(background: int, cursor: str | None, rng: np.random.Generator) -> np.ndarray:
    h, w = 44, 44
    img = np.full((h, w, 4), background, np.uint8)
    img[..., :3] = np.clip(img[..., :3] + rng.integers(-5, 6, (h, w, 3)), 0, 255)
    if cursor == "walk":  # an arrow-ish wedge: a white fill with a dark outline, as cursors are
        for i in range(20):
            width = max(1, i // 2)
            img[6 + i, 5 : 7 + width, :3] = 15
            img[6 + i, 6 : 6 + width, :3] = 250
    elif cursor == "sword":  # a diagonal blade
        for i in range(24):
            img[6 + i, 6 + i : 9 + i, :3] = 20
    return img


def test_the_template_learns_the_walk_cursor_and_rejects_another(ec: ModuleType) -> None:
    rng = np.random.default_rng(1)
    backgrounds = [60, 90, 120, 140, 70, 100]
    on = [_crop(b, "walk", rng) for b in backgrounds]
    off = [_crop(b, None, rng) for b in backgrounds]
    tpl = ec.build_template(on, off)
    assert tpl.mask.sum() >= ec.MIN_MASK_PX and tpl.samples == len(backgrounds)
    assert tpl.is_walk_cursor(_crop(80, "walk", rng))  # a new background
    assert not tpl.is_walk_cursor(_crop(80, "sword", rng))  # an NPC/monster hover
    assert not tpl.is_walk_cursor(_crop(250, None, rng))  # no cursor at all


def test_an_entity_hover_during_calibration_is_dropped(ec: ModuleType) -> None:
    rng = np.random.default_rng(2)
    on = [_crop(b, "walk", rng) for b in (60, 90, 120, 140)] + [_crop(100, "sword", rng)]
    off = [_crop(b, None, rng) for b in (60, 90, 120, 140, 100)]
    tpl = ec.build_template(on, off)
    assert tpl.samples == 4
    assert tpl.is_walk_cursor(_crop(75, "walk", rng))


def test_no_cursor_fails_the_calibration(ec: ModuleType) -> None:
    rng = np.random.default_rng(3)
    on = [_crop(b, None, rng) for b in (60, 90, 120)]
    with pytest.raises(ec.CalibrationFailed):
        ec.build_template(on, on)
    with pytest.raises(ec.CalibrationFailed):
        ec.build_template(on[:2], on[:2])


def test_the_template_round_trips(ec: ModuleType, tmp_path: Path) -> None:
    rng = np.random.default_rng(4)
    on = [_crop(b, "walk", rng) for b in (60, 90, 120)]
    off = [_crop(b, None, rng) for b in (60, 90, 120)]
    tpl = ec.build_template(on, off)
    path = tmp_path / "cursor" / "walk_cursor_console.npz"
    tpl.save(path, {"backend": "console"})
    back = ec.CursorTemplate.load(path)
    assert back.threshold == pytest.approx(tpl.threshold) and (back.mask == tpl.mask).all()


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
