"""LOOT by recognising the floor item sprites (scripts/item_icons.py): the pure matcher and the
template builder on SYNTHETIC images only (no client pixels). The properties the bot relies on: a
known sprite is found where it is and named right, on grass or on dirt; plain ground gives
nothing; the channel order (RGB recordings vs BGR(A) live grabs) does not change the answer; only
the searched square is reported; the builder recovers a sprite (and its offset from the
projected point) from noisy, misaligned crops on varied ground."""

from __future__ import annotations

import importlib.util
import math
import sys
from pathlib import Path
from types import ModuleType

import numpy as np
import pytest

SCRIPTS = Path(__file__).resolve().parents[3] / "scripts"

GRASS = np.array([96, 140, 60])
DIRT = np.array([178, 150, 92])


@pytest.fixture(scope="module")
def ii() -> ModuleType:
    sys.path.insert(0, str(SCRIPTS))
    spec = importlib.util.spec_from_file_location("item_icons", SCRIPTS / "item_icons.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["item_icons"] = mod
    spec.loader.exec_module(mod)
    return mod


def ground(colour: np.ndarray, seed: int = 3, h: int = 360, w: int = 480) -> np.ndarray:
    """A textured ground: low-frequency blotches + per-pixel grain."""
    rng = np.random.default_rng(seed)
    low = rng.uniform(-14, 14, (h // 6 + 1, w // 6 + 1, 1))
    low = np.kron(low, np.ones((6, 6, 1)))[:h, :w]
    grain = rng.normal(0, 5, (h, w, 1))
    return np.clip(colour + low + grain, 0, 255).astype(np.uint8)


def apple() -> tuple[np.ndarray, np.ndarray]:
    """A 13 x 13 red ball with a white highlight and a dark rim (RGB, mask)."""
    yy, xx = np.mgrid[:13, :13]
    r = np.hypot(yy - 6, xx - 6)
    mask = r <= 6.2
    rgb = np.zeros((13, 13, 3), np.float32)
    rgb[:] = (190, 30, 40)
    rgb[r > 4.8] = (90, 10, 20)
    rgb[np.hypot(yy - 4, xx - 4) <= 1.6] = (250, 240, 240)
    return rgb, mask


def bottle() -> tuple[np.ndarray, np.ndarray]:
    """A 15 x 9 white-grey bottle: a neck and a body (RGB, mask)."""
    mask = np.zeros((15, 9), bool)
    mask[0:5, 3:6] = True
    mask[5:15, 1:8] = True
    rgb = np.zeros((15, 9, 3), np.float32)
    rgb[:] = (215, 220, 230)
    rgb[5:15, 1:3] = (150, 155, 170)
    rgb[0:2, 3:6] = (120, 110, 100)
    return rgb, mask


def paste(img: np.ndarray, rgb: np.ndarray, mask: np.ndarray, u: float, v: float) -> None:
    """The sprite with its centre at (u, v)."""
    h, w = mask.shape
    y0, x0 = int(round(v - (h - 1) / 2)), int(round(u - (w - 1) / 2))
    sub = img[y0 : y0 + h, x0 : x0 + w]
    sub[mask] = rgb[mask].astype(np.uint8)


@pytest.fixture(scope="module")
def templates(ii: ModuleType) -> list:
    a, am = apple()
    b, bm = bottle()
    return [ii.IconTemplate(512, a, am, ncc_min=0.7, rms_max=30.0),
            ii.IconTemplate(713, b, bm, ncc_min=0.7, rms_max=30.0)]  # fmt: skip


@pytest.mark.parametrize("colour", [GRASS, DIRT])
def test_items_found_and_named(ii: ModuleType, templates: list, colour: np.ndarray) -> None:
    img = ground(colour)
    paste(img, *apple(), 230, 170)
    paste(img, *bottle(), 262, 190)
    hits = ii.find_items(img, (240.0, 180.0), 60, templates)
    assert len(hits) == 2
    by = {h[2]: h for h in hits}
    assert math.hypot(by[512][0] - 230, by[512][1] - 170) <= 1.0
    assert math.hypot(by[713][0] - 262, by[713][1] - 190) <= 1.0
    assert all(h[3] > 0.9 for h in hits)


def test_plain_ground_gives_nothing(ii: ModuleType, templates: list) -> None:
    for colour in (GRASS, DIRT):
        assert ii.find_items(ground(colour, seed=11), (240.0, 180.0), 100, templates) == []


def test_channel_order(ii: ModuleType, templates: list) -> None:
    rgb = ground(GRASS)
    paste(rgb, *apple(), 250, 160)
    bgra = np.concatenate([rgb[..., ::-1], np.full(rgb.shape[:2] + (1,), 255, np.uint8)], -1)
    a = ii.find_items(rgb, (240.0, 180.0), 60, templates, order="RGB")
    b = ii.find_items(bgra, (240.0, 180.0), 60, templates, order="BGR")
    assert [h[:3] for h in a] == [h[:3] for h in b]
    assert len(a) == 1 and a[0][2] == 512
    # the wrong order: a blue ball is not an apple
    assert ii.find_items(bgra, (240.0, 180.0), 60, templates, order="RGB") == []


def test_only_the_square_and_not_excluded(ii: ModuleType, templates: list) -> None:
    img = ground(DIRT)
    paste(img, *apple(), 200, 180)
    paste(img, *bottle(), 330, 180)  # outside a 60-px square around (240, 180)
    hits = ii.find_items(img, (240.0, 180.0), 60, templates)
    assert [h[2] for h in hits] == [512]
    assert ii.find_items(img, (240.0, 180.0), 60, templates, exclude=[(190, 170, 210, 190)]) == []


def test_at_the_frame_edge(ii: ModuleType, templates: list) -> None:
    img = ground(GRASS)
    paste(img, *apple(), 8, 8)
    hits = ii.find_items(img, (20.0, 20.0), 40, templates)
    assert len(hits) == 1 and math.hypot(hits[0][0] - 8, hits[0][1] - 8) <= 1.0


def test_builder_recovers_sprite_and_anchor(ii: ModuleType) -> None:
    """Crops around a projected point, the sprite 5 px left and 3 px up of it (the anchor) +- a
    projection error of up to 6 px, on grass or dirt, with JPEG-like noise and a distractor
    pebble now and then."""
    rng = np.random.default_rng(5)
    rgb, mask = apple()
    half = ii.CROP_HALF
    samples = []
    for i in range(39):  # three full cycles of a balanced -6..6 error on both axes
        g = ground(GRASS if i % 2 else DIRT, seed=100 + i, h=2 * half + 1, w=2 * half + 1)
        du, dv = (i * 7) % 13 - 6, (i * 5) % 13 - 6
        paste(g, rgb, mask, half - 5 + du, half - 3 + dv)
        if i % 5 == 0:  # a grey pebble elsewhere
            g[half + 20 : half + 24, half - 25 : half - 21] = (120, 120, 120)
        g = np.clip(g + rng.normal(0, 3, g.shape), 0, 255).astype(np.uint8)
        samples.append(ii.Sample(i // 2, 512, f"f{i}", i, (0.0, 0.0), True, g))
    t = ii.build_template(samples)
    assert t is not None
    assert t.item_id == 512
    assert abs(t.size[0] - 13) <= 2 and abs(t.size[1] - 13) <= 2
    assert t.mask.sum() >= 0.7 * mask.sum()
    assert abs(t.anchor[0] + 5) <= 1.5 and abs(t.anchor[1] + 3) <= 1.5
    # the built template finds a fresh apple
    img = ground(DIRT, seed=77)
    paste(img, rgb, mask, 240, 180)
    t.ncc_min, t.rms_max = 0.7, 35.0
    hits = ii.find_items(img, (240.0, 180.0), 50, [t])
    assert len(hits) == 1 and math.hypot(hits[0][0] - 240, hits[0][1] - 180) <= 1.5


def test_save_load_roundtrip(ii: ModuleType, templates: list, tmp_path: Path) -> None:
    ii.save_templates(templates, tmp_path, {"note": "synthetic"})
    back = ii.load_templates(tmp_path)
    assert [t.item_id for t in back] == [512, 713]
    assert np.array_equal(back[0].mask, templates[0].mask)
    assert np.allclose(back[1].rgb, templates[1].rgb)
    assert back[0].ncc_min == templates[0].ncc_min
