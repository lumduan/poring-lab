"""scripts/target_items_r2.py (docs/planning/target-items.md section 10, round 2): the pure parts
on synthetic data (no client pixels): the spot filter, the bar exclusion, the colour variants per
floor item, the direct masked scores against item_icons' FFT maps, the multi-template scan."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))

import item_icons as ii  # noqa: E402
import target_items as ti  # noqa: E402
import target_items_r2 as t2  # noqa: E402

NS = 10**9


def _sprite(tint: float = 1.0) -> np.ndarray:
    s = np.zeros((9, 7, 3), np.float32)
    s[..., 0] = 230
    s[..., 1] = np.linspace(40, 200, 7)[None, :]
    s[..., 2] = np.linspace(20, 160, 9)[:, None]
    s[4, 3] = (10, 10, 250)
    s[..., 1] *= tint  # a per-channel tint: masked NCC is not invariant to it
    return np.clip(s, 0, 255)


def _ground(rng: np.random.Generator, h: int, w: int) -> np.ndarray:
    g = np.empty((h, w, 3), np.uint8)
    g[..., 0] = rng.integers(40, 70, (h, w))
    g[..., 1] = rng.integers(90, 130, (h, w))
    g[..., 2] = rng.integers(30, 60, (h, w))
    return g


def test_spot_frames_keep_only_the_split_spots() -> None:
    wins = [ti.Window(0, (1, 1), 10 * NS, 15 * NS), ti.Window(8, (2, 2), 20 * NS, 25 * NS)]
    rows = [{"t": t * NS} for t in (9, 11, 16, 21, 26)]
    got = t2.spot_frames(wins, rows, (8,))
    assert [int(r["t"]) // NS for _w, r in got] == [21]
    assert [int(r["t"]) // NS for _w, r in t2.spot_frames(wins, rows, (0, 8))] == [11, 21]


def test_bar_box_sits_below_our_feet_and_excludes_touching_items() -> None:
    feet = (640.0, 360.0)
    sb = (feet[0] - 21, feet[1] - 78, feet[0] + 21, feet[1] + ti.SELF_PAD)
    bb = t2.bar_box(sb)
    assert bb == (
        feet[0] + t2.BAR[0],
        feet[1] + t2.BAR[1],
        feet[0] + t2.BAR[2],
        feet[1] + t2.BAR[3],
    )

    def iv(fid: int, c: tuple[float, float]) -> ti.ItemView:
        return ti.ItemView(fid, 756, "on", c, c, ti.square(c, ti.ITEM_BOX))

    under = iv(1, (feet[0] - 32, feet[1] + 19))  # round 1's 756 under the bar
    selfx = iv(2, (feet[0], feet[1] - 10))
    selfx.excl.append("under_self")
    far = iv(3, (feet[0] + 120, feet[1] + 19))
    fr = {"status": "ok", "self_box": sb, "items": [under, selfx, far]}
    t2.add_bar(fr)
    assert under.excl == ["under_self_bar"] and selfx.excl == ["under_self"] and far.excl == []
    assert t2.add_bar({"status": "self_moving", "items": []})["items"] == []


def test_place_variants_are_per_floor_item_medians_of_the_kept_windows() -> None:
    w = np.zeros((7, 3, 2, 3), np.float32)
    w[:3] = 10.0
    w[3:6] = 50.0
    w[6] = 90.0
    tpl = ti.Tpl(757, np.zeros((3, 2, 3), np.float32), np.ones((3, 2), bool), (0.0, 0.0))
    built = ti.Built(tpl, np.array([0, 1, 2, 4, 5, 6, 7]), w)
    inst = [100, 100, 100, 9, 200, 200, 200, 300]  # crop 3 was not kept
    keys, var = t2.place_variants(built, inst, min_n=3)
    assert keys == [100, 200] and var.shape == (2, 3, 2, 3)
    assert float(var[0].mean()) == 10.0 and float(var[1].mean()) == 50.0
    keys, var = t2.place_variants(built, inst, min_n=5)
    assert keys == [] and var.shape == (0, 3, 2, 3)


def test_score_at_equals_item_icons_fft_maps() -> None:
    rng = np.random.default_rng(1)
    img = _ground(rng, 60, 80)
    sp = _sprite()
    img[20:29, 30:37] = sp.astype(np.uint8)
    mask = np.ones(sp.shape[:2], bool)
    mask[0, 0] = mask[-1, -1] = False
    variants = np.stack([sp, _sprite(0.6)])
    ys, xs = np.array([20, 5, 40]), np.array([30, 10, 60])
    ncc, rms, inl = t2.score_at(img, mask, variants, ys, xs)
    for k in range(2):
        icon = ii.IconTemplate(1, variants[k], mask)
        fn, fr = ii.match_maps(img, [icon])[0]
        assert np.allclose(ncc[k], fn[ys, xs], atol=1e-6)
        assert np.allclose(rms[k], fr[ys, xs], atol=1e-4)
    assert ncc[0, 0] > 0.999 and rms[0, 0] < 1.0 and inl[0, 0] == 1.0


def test_scan_multi_takes_the_best_variant_and_drops_boxes() -> None:
    rng = np.random.default_rng(5)
    img = _ground(rng, 200, 300)
    tinted = _sprite(0.45)
    img[96:105, 147:154] = tinted.astype(np.uint8)  # centre (150, 100): a tinted copy
    img[26:35, 17:24] = tinted.astype(np.uint8)  # centre (20, 30): inside the dropped box
    sp = _sprite()
    mask = np.ones(sp.shape[:2], bool)
    pooled = ti.Tpl(757, sp, mask, (0.0, 0.0))
    one = t2.MultiTpl(757, pooled, sp[None], ["pooled"])
    two = t2.MultiTpl(757, pooled, np.stack([sp, tinted]), ["pooled", "c:1"])
    drop = [(0.0, 0.0, 60.0, 60.0)]
    c1 = t2.scan_multi(img, [one], drop)[757]
    c2 = t2.scan_multi(img, [two], drop)[757]
    assert c2.shape[1] == 6
    k = int(np.argmax(c2[:, 2]))
    assert (c2[k, 0], c2[k, 1]) == (150.0, 100.0) and c2[k, 2] > 0.99 and c2[k, 5] == 1.0
    assert c2[k, 3] < 1.0 and c2[k, 4] == 1.0
    at1 = c1[(c1[:, 0] == 150.0) & (c1[:, 1] == 100.0)]
    assert len(at1) == 1 and at1[0, 2] < c2[k, 2] and at1[0, 5] == 0.0
    assert at1[0, 3] > c2[k, 3]  # the pooled colours are far from the tinted copy
    for c in (c1, c2):
        assert not ((c[:, 0] < 60) & (c[:, 1] < 60)).any()
        xy = c[:, :2]
        d = np.hypot(xy[:, None, 0] - xy[None, :, 0], xy[:, None, 1] - xy[None, :, 1])
        assert (d[np.triu_indices(len(c), 1)] > ti.NMS_PX).all()
