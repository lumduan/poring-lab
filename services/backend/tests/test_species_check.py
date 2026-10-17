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


# --- the stale box (live: the detector's newest box is ~0.6 s old when the check runs) -----------


def scene(rng: np.random.Generator, h: int = 360, w: int = 480) -> np.ndarray:
    """Textured ground (blurred noise: NCC needs structure, as the real field has)."""
    g = rng.normal(0, 1, (h // 4, w // 4, 3))
    g = np.repeat(np.repeat(g, 4, 0), 4, 1)
    return np.clip(GRASS + 25 * g + rng.normal(0, 4, (h, w, 3)), 0, 255).astype(np.uint8)


def moved(rng: np.random.Generator, cam: tuple[int, int], walk: tuple[int, int]
          ) -> tuple[np.ndarray, np.ndarray, tuple[int, int, int, int]]:  # fmt: skip
    """(prev, cur, the sprite's box on prev): the camera scrolls by ``cam`` (the whole picture
    moves) and the sprite walks by ``walk`` on top of that."""
    world = scene(rng, 600, 800)
    spr = sprite(rng, PINK, "blob", 40)
    prev = world[100:460, 150:630].copy()
    bx, by = 200, 160
    prev[by : by + 40, bx : bx + 40] = spr
    cur = world[100 - cam[1] : 460 - cam[1], 150 - cam[0] : 630 - cam[0]].copy()
    nx, ny = bx + cam[0] + walk[0], by + cam[1] + walk[1]
    cur[ny : ny + 40, nx : nx + 40] = spr
    return prev, cur, (bx, by, bx + 40, by + 40)


@pytest.mark.parametrize(("cam", "walk", "max_shift", "coarse"), [
    ((0, 0), (0, 0), 40, 1),
    ((-25, 10), (8, -6), 40, 1),
    ((-70, 30), (12, 9), 120, 4),
    ((90, -45), (-15, 20), 120, 4),
    ((-40, -20), (5, 5), 120, 2),
])  # fmt: skip
def test_recentre_finds_the_sprite_after_scroll_and_walk(
    sc: ModuleType, cam: tuple[int, int], walk: tuple[int, int], max_shift: int, coarse: int
) -> None:
    rng = np.random.default_rng(abs(cam[0]) + 7 * abs(walk[1]))
    prev, cur, b = moved(rng, cam, walk)
    nb, s = sc.recentre(prev, (*b, 0.77), cur, order="rgb", max_shift=max_shift, coarse=coarse)
    dx, dy = cam[0] + walk[0], cam[1] + walk[1]
    assert nb == [b[0] + dx, b[1] + dy, b[2] + dx, b[3] + dy, 0.77]  # extra fields kept
    assert s > 0.95


def test_recentre_on_a_patch_grab_equals_the_whole_frame(sc: ModuleType) -> None:
    """Live, the fresh grab is only a patch around the box: cur_origin maps it back."""
    rng = np.random.default_rng(11)
    prev, cur, b = moved(rng, (-30, 12), (6, -4))
    full = sc.recentre(prev, b, cur, order="rgb", max_shift=60, coarse=4)
    ox, oy = b[0] - 70, b[1] - 70
    patch = cur[oy : b[3] + 70, ox : b[2] + 70]
    assert sc.recentre(prev, b, patch, order="rgb", cur_origin=(ox, oy), max_shift=60,
                       coarse=4) == full  # fmt: skip
    # BGR(A) frames (live) give the same answer as their RGB twins
    bgra = np.concatenate([cur[..., ::-1], np.full((*cur.shape[:2], 1), 255, np.uint8)], 2)
    pbgra = np.concatenate([prev[..., ::-1], np.full((*prev.shape[:2], 1), 255, np.uint8)], 2)
    assert sc.recentre(pbgra, b, bgra, order="bgr", max_shift=60, coarse=4) == full


def test_recentre_beyond_max_shift_cannot_reach_it(sc: ModuleType) -> None:
    rng = np.random.default_rng(12)
    prev, cur, b = moved(rng, (-60, 0), (0, 0))
    nb, s = sc.recentre(prev, b, cur, order="rgb", max_shift=40)
    assert abs(nb[0] - b[0]) <= 40 and nb[0] != b[0] - 60  # stays in the window: score says so
    assert s < 0.9
    nb2, s2 = sc.recentre(prev, b, cur, order="rgb", max_shift=120, coarse=4)
    assert nb2[0] == b[0] - 60 and s2 > 0.95


def test_recentre_degenerate_inputs_leave_the_box(sc: ModuleType) -> None:
    img = np.full((100, 100, 3), 90, np.uint8)
    assert sc.recentre(img, (10, 10, 12, 40), img, order="rgb") == ([10, 10, 12, 40], -1.0)
    assert sc.recentre(img, (10, 10, 50, 50), img, order="rgb") == ([10, 10, 50, 50], -1.0)  # flat
    small = np.zeros((20, 20, 3), np.uint8)
    rng = np.random.default_rng(13)
    tex = rng.integers(0, 255, (100, 100, 3)).astype(np.uint8)
    assert sc.recentre(tex, (10, 10, 50, 50), small, order="rgb")[1] == -1.0


def test_ncc_direct_and_fft_paths_agree(sc: ModuleType, monkeypatch: pytest.MonkeyPatch) -> None:
    rng = np.random.default_rng(14)
    w, t = rng.random((70, 66)), rng.random((41, 37))
    monkeypatch.setattr(sc, "DIRECT_MACS", 0)
    fft = sc.ncc_search(w, t)
    monkeypatch.setattr(sc, "DIRECT_MACS", 10**12)
    direct = sc.ncc_search(w, t)
    assert fft[:2] == direct[:2] and fft[2] == pytest.approx(direct[2], abs=1e-9)
    w2 = w.copy()
    w2[11:52, 20:57] = t * 3 + 5  # an exact (affine) copy scores 1 at its place
    assert sc.ncc_search(w2, t)[:2] == (20, 11)
    assert sc.ncc_search(w2, t)[2] == pytest.approx(1.0)


def test_recentre_is_fast(sc: ModuleType) -> None:
    rng = np.random.default_rng(15)
    prev, cur, b = moved(rng, (-50, 20), (10, 5))
    ox, oy = b[0] - 120, b[1] - 120
    patch = cur[max(0, oy) : b[3] + 121, max(0, ox) : b[2] + 121]
    org = (max(0, ox), max(0, oy))
    for _ in range(3):
        sc.recentre(prev, b, patch, order="rgb", cur_origin=org, max_shift=120, coarse=4)
    n = 30
    t0 = time.perf_counter()
    for _ in range(n):
        sc.recentre(prev, b, patch, order="rgb", cur_origin=org, max_shift=120, coarse=4)
    per_call_ms = (time.perf_counter() - t0) / n * 1000
    assert per_call_ms < 25  # measured ~3 ms p50 on the loaded host; generous


REC = Path("/mnt/poring-lab-datasets/hunt-recordings/20261017T202927-demo-hunt-flow31/frames")
REAL_CASES = [  # (frame, frame ~0.6 s later, the detector's box on the first, its label, the
    # detector's own box of the same monster on the later frame minus the first: hunt-flow31,
    # labelled from packets by species_check.label_session)
    ("09153-987241323829603.jpg", "09156-987241928515865.jpg",
     (778.5, 615.2, 821.7, 663.1, 0.785), "Poring", (-45.3, -35.9)),
    ("01977-985804183279867.jpg", "01980-985804803471491.jpg",
     (1031.2, 502.9, 1064.3, 529.5, 0.762), "Lunatic", (-82.8, -55.4)),
]  # fmt: skip


@pytest.mark.parametrize(("f0", "f1", "box", "label", "ref"), REAL_CASES)
def test_recentre_real_session_positive_case(
    sc: ModuleType, f0: str, f1: str, box: tuple[float, ...], label: str,
    ref: tuple[float, float]
) -> None:  # fmt: skip
    """A REAL stale box (the GM walking: the sprite moved 58 / 100 px in ~0.6 s): the wide
    re-centre lands on the detector's own later box; the +-40 px search cannot reach it. With the
    local model (gitignored), the stale crop is not sure and the re-centred crop says the label."""
    if not (REC / f0).exists() or not (REC / f1).exists():
        pytest.skip("the hunt-flow31 recordings are not mounted")
    from PIL import Image

    img0 = np.asarray(Image.open(REC / f0).convert("RGB"))
    img1 = np.asarray(Image.open(REC / f1).convert("RGB"))
    nb, s = sc.recentre(img0, box, img1, order="rgb", max_shift=sc.RECENTRE_WIDE,
                        coarse=sc.RECENTRE_COARSE)  # fmt: skip
    assert s >= sc.RECENTRE_MIN
    assert np.hypot(nb[0] - box[0] - ref[0], nb[1] - box[1] - ref[1]) <= 3.0
    near, _s40 = sc.recentre(img0, box, img1, order="rgb", max_shift=40)
    assert np.hypot(near[0] - box[0] - ref[0], near[1] - box[1] - ref[1]) > 3.0
    if sc.MODEL_PATH.exists():
        m = sc.load_model()
        assert sc.species_of(img0, m, box, order="rgb")[0] == label  # its own frame
        assert sc.species_of(img1, m, box, order="rgb")[0] != label  # stale: not sure
        assert sc.species_of(img1, m, nb, order="rgb")[0] == label  # re-centred
