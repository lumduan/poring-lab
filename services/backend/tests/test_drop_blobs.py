"""LOOT by frame difference (scripts/drop_blobs.py): the pure detector on SYNTHETIC images only (no
client pixels). The properties the bot relies on: a new small item is found where it is; the
dying monster's own colours (its corpse splat) and a big fading sprite are not items; a camera
scroll is registered away; the channel order (RGB recordings vs BGR(A) live grabs) does not
change the answer."""

from __future__ import annotations

import importlib.util
import math
import sys
from pathlib import Path
from types import ModuleType

import numpy as np
import pytest

SCRIPTS = Path(__file__).resolve().parents[3] / "scripts"

SAND = np.array([178, 150, 92])
PINK = np.array([236, 120, 140])
BLUE = np.array([70, 110, 230])
CENTRE = (320.0, 240.0)


@pytest.fixture(scope="module")
def db() -> ModuleType:
    spec = importlib.util.spec_from_file_location("drop_blobs", SCRIPTS / "drop_blobs.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["drop_blobs"] = mod
    spec.loader.exec_module(mod)
    return mod


def ground(seed: int = 7, h: int = 480, w: int = 640) -> np.ndarray:
    """A sand-like texture: low-frequency blotches + per-pixel grain (registrable, JPEG-ish)."""
    rng = np.random.default_rng(seed)
    low = rng.uniform(-18, 18, (h // 8 + 1, w // 8 + 1, 1))
    low = np.kron(low, np.ones((8, 8, 1)))[:h, :w]
    grain = rng.normal(0, 4, (h, w, 1))
    return np.clip(SAND + low + grain, 0, 255).astype(np.uint8)


def paint_disc(img: np.ndarray, u: float, v: float, r: float, colour: np.ndarray) -> None:
    yy, xx = np.mgrid[: img.shape[0], : img.shape[1]]
    img[(xx - u) ** 2 + (yy - v) ** 2 <= r * r] = colour


def near(blobs: list, u: float, v: float, px: float = 4.0) -> bool:
    return any(math.hypot(b.u - u, b.v - v) <= px for b in blobs)


def test_new_small_blob_is_found(db: ModuleType) -> None:
    before = ground()
    after = before.copy()
    paint_disc(after, 345, 252, 6, BLUE)
    blobs = db.drop_blobs(before, after, CENTRE, exclude=None)
    assert len(blobs) == 1
    assert near(blobs, 345, 252, 2.0)


def test_nothing_new_means_no_blob(db: ModuleType) -> None:
    before = ground()
    noisy = np.clip(before.astype(int) + np.random.default_rng(1).normal(0, 3, before.shape),
                    0, 255).astype(np.uint8)  # fmt: skip
    assert db.drop_blobs(before, noisy, CENTRE, exclude=None) == []


def test_dying_monster_is_not_a_drop(db: ModuleType) -> None:
    """BEFORE: a big pink monster on the spot. AFTER: it is gone, its corpse splat (small pieces of
    ITS colour) lies around, and one blue item fell. Only the item is a drop; a big half-faded
    sprite is too big to be one."""
    before = ground()
    paint_disc(before, 320, 240, 20, PINK)
    after = ground()
    for du, dv in ((-22, 6), (-6, 10), (12, 4), (26, 9)):
        paint_disc(after, 320 + du, 240 + dv, 5, PINK)
    paint_disc(after, 300, 222, 6, BLUE)
    blobs = db.drop_blobs(before, after, CENTRE, exclude=None)
    assert near(blobs, 300, 222)
    assert len(blobs) == 1

    fading = ground()
    yy, xx = np.mgrid[:480, :640]
    disc = (xx - 320) ** 2 + (yy - 240) ** 2 <= 20 * 20
    fading[disc] = (0.5 * fading[disc] + 0.5 * np.array([90, 200, 240])).astype(np.uint8)
    assert db.drop_blobs(ground(), fading, CENTRE, exclude=None) == []


def test_camera_scroll_is_registered_away(db: ModuleType) -> None:
    """The GM moved a little: AFTER is BEFORE scrolled by (dx, dy) = (-10, +11) px, plus one item,
    and the caller did not know (same centre). Static scenery (green tufts) must not come out as
    new blobs; without the registration it does."""
    big = ground(seed=3, h=520, w=680)
    for k in range(8):  # the tufts, around the spot (big = before shifted by (20, 20))
        paint_disc(big, 300 + 45 * math.cos(k), 270 + 45 * math.sin(k), 4, np.array([60, 150, 50]))
    before = big[20:500, 20:660].copy()
    after = big[9:489, 30:670].copy()  # after[y, x] = before[y - 11, x + 10]
    paint_disc(after, 330, 230, 6, BLUE)
    blobs = db.drop_blobs(before, after, CENTRE, exclude=None)
    assert len(blobs) == 1
    assert near(blobs, 330, 230, 2.0)
    raw = db.candidates(before, after, CENTRE, max_shift=0)
    assert sum(1 for b in raw if not near([b], 330, 230)) >= 3  # the tufts, unregistered


def test_colour_order_does_not_matter(db: ModuleType) -> None:
    before = ground()
    paint_disc(before, 320, 240, 18, PINK)
    after = ground()
    paint_disc(after, 310, 250, 5, PINK)
    paint_disc(after, 340, 230, 6, BLUE)
    paint_disc(after, 290, 260, 5, np.array([250, 240, 60]))
    rgb = db.drop_blobs(before, after, CENTRE, exclude=None)
    bgr = db.drop_blobs(before[..., ::-1], after[..., ::-1], CENTRE, exclude=None)
    alpha = np.full(before.shape[:2] + (1,), 255, np.uint8)
    bgra = db.drop_blobs(np.concatenate([before[..., ::-1], alpha], -1),
                         np.concatenate([after[..., ::-1], alpha], -1), CENTRE,
                         exclude=None)  # fmt: skip
    assert [(b.u, b.v, b.area) for b in rgb] == [(b.u, b.v, b.area) for b in bgr]
    assert [(b.u, b.v, b.area) for b in rgb] == [(b.u, b.v, b.area) for b in bgra]
    assert near(rgb, 340, 230) and near(rgb, 290, 260)
    assert not near(rgb, 310, 250)  # the monster's own colour


def test_bars_gm_box_and_persistence(db: ModuleType) -> None:
    before = ground()
    after = before.copy()
    after[270:274, 290:340] = BLUE  # a thin HP bar
    paint_disc(after, 350, 225, 6, BLUE)  # inside the excluded box below
    paint_disc(after, 300, 220, 6, BLUE)  # an item
    blobs = db.drop_blobs(before, after, CENTRE, exclude=(340.0, 215.0, 360.0, 235.0))
    assert len(blobs) == 1 and near(blobs, 300, 220)
    later = before.copy()  # the item was a transient (e.g. a swing effect): gone in LATER
    assert db.drop_blobs(before, after, CENTRE, later=later, exclude=None) == []


def test_rejects_non_images(db: ModuleType) -> None:
    with pytest.raises(ValueError):
        db.drop_blobs(np.zeros((10, 10)), np.zeros((10, 10)), (5.0, 5.0))
