"""minimap_id (dungeon@9.46; Batt 2026-11-13 "do it"): which MAP the game screen shows, read from
the minimap's own picture. Every picture here is SYNTHETIC (blocks of random grey with a magenta
key area): the real references are client-derived and never in git (CLAUDE.md rule 4)."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts"))

import minimap_id as mi  # noqa: E402
import minimap_id_eval as mie  # noqa: E402

KEY = (255, 0, 255)
ORIGIN = (1136, 18)  # the minimap window's home (poring_env.ui_anchors.CAPTURE_ORIGINS)


def bitmap(seed: int, key_frac: float = 0.3, size: int = 64) -> np.ndarray:
    """A synthetic minimap bitmap (RGB): 8 px blocks of random colour, its left ``key_frac``
    the key colour (transparent in the client)."""
    rng = np.random.default_rng(seed)
    blocks = rng.integers(0, 230, (size // 8, size // 8, 3), dtype=np.uint8)
    img = np.kron(blocks, np.ones((8, 8, 1), np.uint8))
    img[:, : int(size * key_frac)] = KEY
    return img


def refs_of(maps: dict[str, int], copies: dict[str, str] | None = None) -> mi.MapRefs:
    """References from synthetic bitmaps: {picture name: seed}, server names = picture names
    plus ``copies`` ({server map: picture name})."""
    pics = {name: mi.render_picture(bitmap(seed)) for name, seed in maps.items()}
    names = {n: n for n in maps} | (copies or {})
    return mi.MapRefs.from_pictures(pics, names, {"test": True})


def frame_with(bmp: np.ndarray | None, *, alpha: float = 0.6, seed: int = 99,
               marks: bool = True) -> np.ndarray:  # fmt: skip
    """A BGR game region: a busy scene, the bitmap drawn as the client draws it (the key colour
    transparent, the rest translucent over the scene), and opaque NPC marks on top."""
    rng = np.random.default_rng(seed)
    blocks = rng.integers(70, 170, (90, 160, 3), dtype=np.uint8)
    scene = np.kron(blocks, np.ones((8, 8, 1), np.uint8))
    img = scene.astype(np.float32)
    if bmp is not None:
        g, d = mi.render_picture(bmp)
        x, y = ORIGIN[0] + mi.PIC_OFFSET[0], ORIGIN[1] + mi.PIC_OFFSET[1]
        sq = img[y : y + mi.PIC_SIZE, x : x + mi.PIC_SIZE]
        a = alpha * d[..., None]
        sq[:] = a * g[..., None] + (1 - a) * sq
        if marks:  # the NPC marks and her arrow: opaque, white-rimmed
            for mx, my in ((x + 60, y + 30), (x + 90, y + 80), (x + 40, y + 100)):
                img[my : my + 9, mx : mx + 9] = 250
    return np.clip(img, 0, 255).astype(np.uint8)


REFS = refs_of({"xmas_dun02": 1, "geffen": 2, "prt_fild08": 3, "gef_fild10": 4},
               {"pgeffen": "geffen"})  # fmt: skip


# --- the picture as the client draws it -----------------------------------------------------------


def test_the_key_colour_is_not_drawn_and_the_rest_is_box_scaled() -> None:
    bmp = np.zeros((8, 8, 3), np.uint8)
    bmp[:, :4] = KEY
    bmp[:, 4:] = (100, 150, 200)
    g, d = mi.render_picture(bmp, size=4)
    assert not d[:, :2].any() and d[:, 2:].all()
    want = 0.299 * 100 + 0.587 * 150 + 0.114 * 200
    assert np.allclose(g[:, 2:], want, atol=0.01)
    # a scaled pixel half key, half drawn is NOT drawn (COVER_MIN): its colour would be a blend
    g3, d3 = mi.render_picture(bmp, size=3)
    assert d3[:, 0].sum() == 0 and not d3[:, 1].any() and d3[:, 2].all()


def test_identical_pictures_merge_and_mostly_key_pictures_are_left_out() -> None:
    pics = {"a": mi.render_picture(bitmap(1)), "a_copy": mi.render_picture(bitmap(1)),
            "keyed": mi.render_picture(bitmap(2, key_frac=0.95))}  # fmt: skip
    refs = mi.MapRefs.from_pictures(pics)
    assert refs.names == ("a", "a_copy") and len(refs.pic_names) == 1
    assert refs.pic_of == (0, 0) and not refs.has("keyed")
    with pytest.raises(ValueError, match="no usable"):
        mi.MapRefs.from_pictures({"keyed": pics["keyed"]})


def test_the_references_save_and_load(tmp_path: Path) -> None:
    p = tmp_path / "refs.npz"
    REFS.save(p)
    back = mi.MapRefs.load(p)
    assert back.names == REFS.names and back.pic_of == REFS.pic_of
    assert back.meta["format"] == mi.FORMAT and back.meta["test"] is True
    r1 = mi.read_map(frame_with(bitmap(2)), REFS)
    r2 = mi.read_map(frame_with(bitmap(2)), back)
    assert r1.map == r2.map == "geffen" and abs(r1.score - r2.score) < 0.01  # uint8 greys
    z = dict(np.load(p))
    z["meta"] = np.array(json.dumps({"format": mi.FORMAT + 1}))
    np.savez(tmp_path / "old.npz", **z)
    with pytest.raises(ValueError, match="rebuild"):
        mi.MapRefs.load(tmp_path / "old.npz")


# --- the read -------------------------------------------------------------------------------------


def test_the_run_map_is_read_through_the_translucency_the_scene_and_the_marks() -> None:
    for alpha in (0.55, 0.7, 0.9):
        for seed in (5, 6, 7):
            rd = mi.read_map(frame_with(bitmap(1), alpha=alpha, seed=seed), REFS)
            assert rd.map == "xmas_dun02" and rd.names == ("xmas_dun02",), (alpha, seed, rd)
            assert rd.score >= mi.MATCH_MIN and rd.margin >= mi.MARGIN_MIN
            ok, words = mi.map_verdict(rd, "xmas_dun02", REFS)
            assert ok is True and words.startswith("the minimap is xmas_dun02's")


def test_another_map_is_named_with_its_copies_and_crosses_the_run_map() -> None:
    rd = mi.read_map(frame_with(bitmap(2)), REFS)
    assert rd.map == "geffen" and rd.names == ("geffen", "pgeffen")  # the shortest name first
    ok, words = mi.map_verdict(rd, "xmas_dun02", REFS)
    assert ok is False
    assert words.startswith("she is on geffen, not xmas_dun02 (read from the minimap")
    ok2, words2 = mi.map_verdict(rd, "pgeffen", REFS)  # a copy draws the same picture: a tick
    assert ok2 is True and "the same picture as geffen" in words2


def test_no_picture_cannot_tell() -> None:
    flat = np.full((720, 1280, 3), 12, np.uint8)  # a load screen
    rd = mi.read_map(flat, REFS)
    assert rd.map is None and "no minimap picture" in rd.why
    ok, words = mi.map_verdict(rd, "xmas_dun02", REFS)
    assert ok is None and "not read from the minimap" in words
    unknown = mi.read_map(frame_with(bitmap(77)), REFS)  # a map with no reference
    assert unknown.map is None and mi.map_verdict(unknown, "xmas_dun02", REFS)[0] is None
    scene_only = mi.read_map(frame_with(None), REFS)  # an indoor map: no minimap drawn
    assert scene_only.map is None
    small = mi.read_map(np.zeros((100, 100, 3), np.uint8), REFS)
    assert small.map is None and "outside the frame" in small.why


def test_two_alike_pictures_cannot_tell_and_a_weak_match_never_ticks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    a = bitmap(1)
    b = a.copy()
    b[:16, 40:] = bitmap(9)[:16, 40:]  # a quarter differs: two pictures, not one
    refs = mi.MapRefs.from_pictures({"xmas_dun02": mi.render_picture(a),
                                     "xmas_dun01": mi.render_picture(b)})  # fmt: skip
    assert refs.alike(0, 1) < mi.COPY_NCC
    rd = mi.read_map(frame_with(a), refs)
    assert rd.map is None and "alike" in rd.why
    # named, but under MATCH_MIN: no tick (a "?"), never a cross
    monkeypatch.setattr(mi, "MATCH_MIN", 1.01)
    rd2 = mi.read_map(frame_with(bitmap(1)), REFS)
    ok, words = mi.map_verdict(rd2, "xmas_dun02", REFS)
    assert rd2.map == "xmas_dun02" and ok is None and "weakly" in words


def test_no_references_cannot_tell_with_the_build_command() -> None:
    rd = mi.read_map(frame_with(bitmap(1)), REFS)
    ok, words = mi.map_verdict(rd, "xmas_dun02", None)
    assert ok is None and "minimap_id.py build" in words
    ok, words = mi.map_verdict(rd, "orcsdun01", REFS)
    assert ok is None and "no minimap reference for orcsdun01" in words


def test_read_until_stops_at_the_first_named_map_or_the_time() -> None:
    frames = [np.zeros((720, 1280, 3), np.uint8)] * 2 + [frame_with(bitmap(1))]
    it = iter(frames)
    t = [0.0]
    slept: list[float] = []

    def sleep(s: float) -> None:
        slept.append(s)
        t[0] += s

    rd, n = mi.read_until(lambda: next(it), REFS, 5.0, clock=lambda: t[0], sleep=sleep)
    assert rd.map == "xmas_dun02" and n == 3 and len(slept) == 2
    flat = np.zeros((720, 1280, 3), np.uint8)
    t[0] = 0.0
    rd, n = mi.read_until(lambda: flat, REFS, 1.0, poll_s=0.25, clock=lambda: t[0], sleep=sleep)
    assert rd.map is None and n == 5  # 0, 0.25, 0.5, 0.75, 1.0


def test_resnametable_aliases_name_the_picture() -> None:
    table = {"ui/map/new_1-1.bmp": "ui/map/new_zone01.bmp", "ui/map/x.bmp": "ui/map/x.bmp",
             "new_1-1.rsw": "new_zone01.rsw"}  # fmt: skip
    assert mi.bmp_aliases(table) == {"new_1-1": "new_zone01", "x": "x"}


def test_a_saved_session_picture_is_cut_to_the_game_region(tmp_path: Path) -> None:
    from PIL import Image

    bgr = frame_with(bitmap(3))
    full = np.zeros((900, 1440, 3), np.uint8)
    full[77:797, 80:1360] = bgr[..., ::-1]  # on disk: RGB, the whole 1440x900 session
    Image.fromarray(full).save(tmp_path / "end.png")
    got = mi._load_frame(tmp_path / "end.png")
    assert got.shape == (720, 1280, 3) and np.array_equal(got, bgr)
    assert mi.read_map(got, REFS).map == "prt_fild08"


# --- the scorer -----------------------------------------------------------------------------------


def test_the_scorers_true_map_skips_the_load_and_starts_at_the_first_change() -> None:
    ch = [(10 * 10**9, "prt_fild08"), (100 * 10**9, "xmas_dun02")]
    assert mie.true_map(ch, 5 * 10**9) is None  # before any change: unknown
    assert mie.true_map(ch, 9 * 10**9) is None  # the load window before ...
    assert mie.true_map(ch, 14 * 10**9) is None  # ... and after a change
    assert mie.true_map(ch, 50 * 10**9) == "prt_fild08"
    assert mie.true_map(ch, 99 * 10**9) is None
    assert mie.true_map(ch, 106 * 10**9) == "xmas_dun02"


def test_the_confusion_table() -> None:
    rows: list[dict[str, Any]] = [
        {"true": "xmas_dun02", "read": "xmas_dun02"},
        {"true": "xmas_dun02", "read": None},
        {"true": "geffen", "read": "geffen"},
    ]
    t = mie.table(rows).splitlines()
    assert t[0].split()[-1] == "?" and "geffen" in t[0]
    assert t[2].split() == ["xmas_dun02", ".", "1", "1"]
