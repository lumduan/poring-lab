"""FAST SPECIES CHECK (scripts/species_check.py): the pure classifier on SYNTHETIC images only (no
client pixels). The properties the bot relies on: the colour order is explicit and does not
change the answer; a crop of any size gives the same-length features; a model learns synthetic
colour/shape classes and says None (read the tag) for "other" or below its threshold; it
round-trips through its file; a call is fast."""

from __future__ import annotations

import importlib.util
import sys
import time
from pathlib import Path
from types import ModuleType

import numpy as np
import pytest

SCRIPTS = Path(__file__).resolve().parents[3] / "scripts"

GRASS = np.array([70, 140, 60])
PINK = np.array([240, 130, 170])
WHITE = np.array([235, 235, 230])
ORANGE = np.array([240, 150, 40])
OLIVE = np.array([150, 140, 80])
PALE = np.array([250, 230, 160])


@pytest.fixture(scope="module")
def sc() -> ModuleType:
    spec = importlib.util.spec_from_file_location("species_check", SCRIPTS / "species_check.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["species_check"] = mod
    spec.loader.exec_module(mod)
    return mod


def field(rng: np.random.Generator, h: int = 120, w: int = 160) -> np.ndarray:
    return np.clip(GRASS + rng.normal(0, 10, (h, w, 3)), 0, 255).astype(np.uint8)


def sprite(rng: np.random.Generator, colour: np.ndarray, shape: str, size: int = 40) -> np.ndarray:
    """A size x size crop: grass with a disc (a blob) or two side lobes (wings) in ``colour``."""
    img = field(rng, size, size)
    yy, xx = np.mgrid[:size, :size]
    c = size / 2 + rng.normal(0, 1.5, 2)
    if shape == "blob":
        m = (xx - c[0]) ** 2 + (yy - c[1] - 3) ** 2 <= (size * 0.33) ** 2
    else:
        m = ((xx - c[0] + 9) ** 2 / 64 + (yy - c[1]) ** 2 / 196 <= 1) | (
            (xx - c[0] - 9) ** 2 / 64 + (yy - c[1]) ** 2 / 196 <= 1
        )
    img[m] = np.clip(colour + rng.normal(0, 8, (int(m.sum()), 3)), 0, 255)
    return img


KINDS = {  # synthetic stand-ins for the six classes
    "Poring": (PINK, "blob"),
    "Lunatic": (WHITE, "blob"),
    "Drops": (ORANGE, "blob"),
    "Pupa": (OLIVE, "blob"),
    "Creamy": (PALE, "wings"),
}


def dataset(sc: ModuleType, n: int, seed: int) -> tuple[np.ndarray, np.ndarray]:
    rng = np.random.default_rng(seed)
    xs, ys = [], []
    for c, name in enumerate(sc.CLASSES):
        for _ in range(n):
            s = int(rng.integers(34, 48))
            crop = field(rng, s, s) if name == "other" else sprite(rng, *KINDS[name], size=s)
            xs.append(sc.features(sc.thumbnail(crop), s, s, 0.8))
            ys.append(c)
    return np.asarray(xs), np.asarray(ys)


@pytest.fixture(scope="module")
def model(sc: ModuleType) -> dict:
    x, y = dataset(sc, 30, 1)
    m = sc.fit(x, y, len(sc.CLASSES), steps=300)
    m["classes"] = tuple(sc.CLASSES)
    m["thr"] = 0.6
    return m


def test_order_is_explicit_and_does_not_change_the_answer(sc: ModuleType, model: dict) -> None:
    rng = np.random.default_rng(3)
    frame = field(rng, 200, 300)
    frame[50:90, 100:140] = sprite(rng, PINK, "blob")
    box = (100, 50, 140, 90, 0.8)
    rgb = sc.species_of(frame, model, box, order="rgb")
    bgra = np.concatenate([frame[..., ::-1], np.full((200, 300, 1), 255, np.uint8)], axis=2)
    assert sc.species_of(bgra, model, box, order="bgr") == rgb
    assert rgb[0] == "Poring"
    # the same pixels read in the WRONG order are a different colour (the argument matters)
    assert sc.species_of(frame, model, box, order="bgr") != rgb
    with pytest.raises(TypeError):
        sc.species_of(frame, model, box)  # no default order
    with pytest.raises(ValueError):
        sc.species_of(frame, model, box, order="hsv")


def test_crop_or_frame_and_box_agree(sc: ModuleType, model: dict) -> None:
    rng = np.random.default_rng(4)
    frame = field(rng, 200, 300)
    frame[60:100, 20:60] = sprite(rng, WHITE, "blob")
    by_box = sc.species_of(frame, model, (20, 60, 60, 100, 0.8), order="rgb")
    by_crop = sc.species_of(frame[60:100, 20:60], model, order="rgb", score=0.8)
    assert by_box == by_crop
    assert by_box[0] == "Lunatic"


def test_box_is_clipped_to_the_frame_and_empty_boxes_raise(sc: ModuleType) -> None:
    img = np.zeros((50, 60, 3), np.uint8)
    assert sc.crop_box(img, (-10, -5, 20, 30), "rgb").shape == (30, 20, 3)
    with pytest.raises(ValueError):
        sc.crop_box(img, (70, 10, 90, 20), "rgb")


def test_thumbnail_is_a_block_mean_and_takes_any_size(sc: ModuleType) -> None:
    a = np.zeros((64, 64, 3), np.uint8)
    a[::2, ::2] = 255  # one bright pixel in every 2 x 2 block
    t = sc.thumbnail(a)
    assert t.shape == (sc.SIZE, sc.SIZE, 3)
    assert np.allclose(t, 255 / 4)
    small = np.full((10, 13, 3), 77, np.uint8)
    assert np.allclose(sc.thumbnail(small), 77)
    f1 = sc.features(sc.thumbnail(small), 13, 10, 0.5)
    f2 = sc.features(sc.thumbnail(np.full((57, 41, 3), 9, np.uint8)), 41, 57, 0.5)
    assert f1.shape == f2.shape and np.isfinite(f1).all() and np.isfinite(f2).all()


def test_learns_synthetic_classes(sc: ModuleType, model: dict) -> None:
    x, y = dataset(sc, 15, 99)  # unseen samples
    p = sc.probabilities(x, model)
    assert (p.argmax(1) == y).mean() >= 0.95
    wings = sprite(np.random.default_rng(5), PALE, "wings")
    assert sc.species_of(wings, model, order="rgb")[0] == "Creamy"


def test_the_linear_variant_learns_too(sc: ModuleType) -> None:
    x, y = dataset(sc, 30, 2)
    m = sc.fit(x, y, len(sc.CLASSES), hidden=0, lr=0.05, steps=300)
    assert "W1" not in m
    xt, yt = dataset(sc, 10, 98)
    assert (sc.probabilities(xt, m).argmax(1) == yt).mean() >= 0.9


def test_other_and_low_confidence_are_ambiguous(sc: ModuleType, model: dict) -> None:
    rng = np.random.default_rng(6)
    grass = field(rng, 40, 40)
    assert sc.species_of(grass, model, order="rgb")[0] is None  # "other" -> read the tag
    pink = sprite(rng, PINK, "blob")
    name, conf = sc.species_of(pink, model, order="rgb", thr=0.0)
    assert name == "Poring"
    assert sc.species_of(pink, model, order="rgb", thr=conf + 1e-6)[0] is None
    assert sc.decide(np.array([0.1, 0, 0, 0, 0, 0.9]), sc.CLASSES, 0.5) == (None, 0.9)
    assert sc.decide(np.array([0.9, 0, 0, 0, 0, 0.1]), sc.CLASSES, 0.5) == ("Poring", 0.9)


def test_model_file_round_trip(sc: ModuleType, model: dict, tmp_path: Path) -> None:
    p = tmp_path / "species" / "model.npz"
    sc.save_model({**model, "classes": np.array(model["classes"])}, p)
    m2 = sc.load_model(p)
    assert m2["classes"] == tuple(sc.CLASSES) and m2["thr"] == pytest.approx(0.6)
    crop = sprite(np.random.default_rng(8), ORANGE, "blob")
    assert sc.species_of(crop, m2, order="rgb") == sc.species_of(crop, model, order="rgb")


def test_a_call_is_fast(sc: ModuleType, model: dict) -> None:
    rng = np.random.default_rng(9)
    frame = field(rng, 720, 1280)
    box = (600, 300, 645, 342, 0.7)
    sc.species_of(frame, model, box, order="rgb")
    n = 50
    t0 = time.perf_counter()
    for _ in range(n):
        sc.species_of(frame, model, box, order="rgb")
    per_call_ms = (time.perf_counter() - t0) / n * 1000
    assert per_call_ms < 25  # measured ~1 ms; generous for a loaded shared host
