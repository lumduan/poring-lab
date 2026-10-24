"""scripts/target_items.py (docs/planning/target-items.md, pre-registered 2026-10-24 17:48:17):
the pure parts on synthetic data (no client pixels): the still windows, the item exclusions, the
seeded template builder, the whole-frame scan, the frame matcher, the threshold grid and choice,
the map spans."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))

import target_items as ti  # noqa: E402

NS = 10**9


def test_still_windows_end_at_the_next_map_change_and_are_capped() -> None:
    evs = [
        {"kind": "warp", "t_ns": 0, "spot": 0},
        {"kind": "still", "t_ns": 10 * NS, "spot": 0, "at": [5, 6]},
        {"kind": "still", "t_ns": 30 * NS, "spot": 1, "at": [7, 8]},
    ]
    w = ti.still_windows(evs, [16 * NS, 9 * NS])
    assert w[0].t0 == int(10.5 * NS) and w[0].t1 == 16 * NS and w[0].at == (5, 6)
    assert w[1].t1 == 30 * NS + int(ti.STILL_MAX_S * NS)  # no later change: the cap
    assert ti.window_of(w, 12 * NS) is w[0] and ti.window_of(w, 10 * NS) is None
    assert ti.split_of_spot(7) == "fit" and ti.split_of_spot(8) == "test"
    with pytest.raises(ValueError):
        ti.split_of_spot(12)


def _iv(fid: int, c: tuple[float, float], side: float = 28.0) -> ti.ItemView:
    return ti.ItemView(fid, 757, "on", c, c, ti.square(c, side))


def test_exclusions_keep_excluded_items_present_and_drop_hidden_ones() -> None:
    rects = [(0.0, 0.0, 100.0, 100.0)]
    views = [
        _iv(1, (50.0, 50.0)),  # wholly under the window: hidden, dropped
        _iv(2, (110.0, 50.0)),  # partly: ui_partial
        _iv(3, (640.0, 330.0)),  # under our own box
        _iv(4, (900.0, 400.0)),  # under a unit
        _iv(5, (400.0, 500.0)),
        _iv(6, (405.0, 503.0)),  # stacked with 5
        _iv(7, (1000.0, 600.0)),  # clear
        _iv(8, (1275.0, 600.0)),  # edge
    ]
    out = ti.exclusions(views, (623.0, 266.0, 657.0, 344.0), [ti.unit_box(900.0, 480.0)], rects)
    got = {v.floor_id: v.excl for v in out}
    assert 1 not in got
    assert got[2] == ["ui_partial"] and got[3] == ["under_self"] and got[4] == ["under_unit"]
    assert got[5] == ["stacked"] and got[6] == ["stacked"]
    assert got[7] == [] and got[8] == ["edge_partial"]
    assert [v.floor_id for v in out if v.labelled] == [7]


def _sprite() -> np.ndarray:
    s = np.zeros((9, 7, 3), np.uint8)
    s[..., 0] = 230
    s[..., 1] = np.linspace(40, 200, 7, dtype=np.uint8)[None, :]
    s[..., 2] = np.linspace(20, 160, 9, dtype=np.uint8)[:, None]
    s[4, 3] = (10, 10, 250)
    return s


def _ground(rng: np.random.Generator, h: int, w: int) -> np.ndarray:
    g = np.empty((h, w, 3), np.uint8)
    g[..., 0] = rng.integers(40, 70, (h, w))
    g[..., 1] = rng.integers(90, 130, (h, w))
    g[..., 2] = rng.integers(30, 60, (h, w))
    return g


def test_build_seeded_finds_the_sprite_and_its_anchor() -> None:
    rng = np.random.default_rng(3)
    sp = _sprite()
    crops = []
    for _ in range(20):
        c = _ground(rng, 89, 89)
        dy, dx = 3 + int(rng.integers(-1, 2)), -6 + int(rng.integers(-1, 2))
        cy, cx = 44 + dy, 44 + dx
        c[cy - 4 : cy + 5, cx - 3 : cx + 4] = sp
        crops.append(c)
    t = ti.build_seeded(np.stack(crops), 757, list(range(20)))
    assert t is not None
    assert abs(t.anchor[0] - -6) <= 1.0 and abs(t.anchor[1] - 3) <= 1.0
    assert 7 <= t.size[0] <= 11 and 5 <= t.size[1] <= 9
    assert t.samples >= 12 and t.instances >= 12
    assert ti.build_seeded(np.stack(crops[:5]), 757, list(range(5))) is None


def test_scan_finds_a_pasted_sprite_and_drops_centres_in_a_rectangle() -> None:
    rng = np.random.default_rng(5)
    sp = _sprite()
    img = _ground(rng, 200, 300)
    img[96:105, 147:154] = sp  # centre (150, 100)
    img[26:35, 17:24] = sp  # centre (20, 30): inside the dropped rectangle
    tpl = ti.Tpl(757, sp.astype(np.float32), np.ones(sp.shape[:2], bool), (0.0, 0.0))
    c = ti.scan(img, [tpl], [(0.0, 0.0, 60.0, 60.0)])[757]
    assert c.shape[1] == 5
    k = int(np.argmax(c[:, 2]))
    assert (c[k, 0], c[k, 1]) == (150.0, 100.0)
    assert c[k, 2] > 0.99 and c[k, 3] < 1.0 and c[k, 4] == 1.0
    assert not ((c[:, 0] < 60) & (c[:, 1] < 60)).any()
    bo = ti.best_offset(img.astype(np.float32), tpl, (148.0, 101.0), 4)
    assert bo is not None and (bo["dx"], bo["dy"]) == (2, -1)


def test_match_frame_splits_found_and_false_candidates() -> None:
    lab = _iv(1, (100.0, 100.0))
    exc = _iv(2, (300.0, 100.0))
    exc.excl.append("under_unit")
    cands = {
        757: np.array(
            [
                [103.0, 99.0, 0.9, 20.0, 0.8],  # on the labelled item
                [300.0, 104.0, 0.8, 30.0, 0.7],  # on the excluded (present) item: not false
                [500.0, 500.0, 0.7, 25.0, 0.6],  # nothing there: false
            ]
        )
    }
    present = [(757, (100.0, 100.0)), (757, (300.0, 100.0)), (604, (500.0, 500.0))]
    m = ti.match_frame(cands, [lab], present)
    assert len(m[757]["pos"]) == 1 and m[757]["pos"][0].tolist() == [[0.9, 20.0, 0.8]]
    assert m[757]["false"].tolist() == [[0.7, 25.0, 0.6]]
    assert m[604]["pos"] == [] and len(m[604]["false"]) == 0


def test_grid_and_choice_take_the_best_recall_under_the_false_cap() -> None:
    pos = [np.array([[0.9, 20.0, 0.9]]), np.array([[0.7, 20.0, 0.9]]), np.zeros((0, 3))]
    neg = np.array([[0.75, 20.0, 0.9], [0.65, 70.0, 0.2]])
    gs = ti.grid_stats(pos, neg, 100)
    s = gs[(float("inf"), 0.0)]
    k = ti.GRID_NCC.index(0.7)
    assert s["recall"][k] == pytest.approx(2 / 3) and s["fp"][k] == 1
    ch = ti.choose(gs, 0.5)  # no false allowed in 100 frames: 1 / 3; ties -> the strictest
    assert (ch["ncc"], ch["rms"], ch["inl"]) == (0.9, 20.0, 0.9)
    assert ch["fit_recall"] == pytest.approx(1 / 3, abs=1e-3) and ch["fit_fp100"] == 0.0
    ch = ti.choose(gs, 1.0)  # one allowed: 0.7 reaches 2 / 3
    assert ch["fit_recall"] == pytest.approx(2 / 3, abs=1e-3) and (ch["ncc"], ch["rms"]) == (
        0.7,
        20.0,
    )
    assert ti.passes(np.array([[0, 0, 0.8, 30, 0.5]]), 0.8, 30, 0.5).tolist() == [True]


def test_near_is_chebyshev_and_map_spans_follow_the_map() -> None:
    assert ti.near([[0, 0]], [[6, 6], [6.5, 0]]).tolist() == [[True, False]]
    ev = [
        {"type": "map_change", "map": "prt_fild08.gat", "t_mono_ns": 0},
        {"type": "map_change", "map": "pay_fild07.gat", "t_mono_ns": 10 * NS},
        {"type": "map_change", "map": "pay_fild07.gat", "t_mono_ns": 30 * NS},
        {"type": "map_change", "map": "prt_fild08.gat", "t_mono_ns": 32 * NS},
        {"type": "chat", "t_mono_ns": 60 * NS},
    ]
    assert ti.map_spans(ev) == [(15 * NS, 30 * NS)]  # the second one is shorter than the settle
    assert ti.in_spans([(1, 3)], 2) and not ti.in_spans([(1, 3)], 3)
