"""BELIEF MAP (scripts/belief_map.py): the pure parts on SYNTHETIC grids only. The properties the
live use relies on: walls bound the spread (geodesic distance, not straight-line), the kernel's
mass moves outward with time and sums to one, association keeps a nearby sighting on its track
and starts a new one far away, a visible empty cell loses belief (and an occluded one keeps it),
the existence mass falls when every reachable cell is looked at and empty, probes are spaced, and
the occluder map marks a cell the camera saw often with no boxes."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import numpy as np
import pytest

SCRIPTS = Path(__file__).resolve().parents[3] / "scripts"
NS = 10**9


@pytest.fixture(scope="module")
def bmod() -> ModuleType:
    sys.path.insert(0, str(SCRIPTS))
    spec = importlib.util.spec_from_file_location("belief_map", SCRIPTS / "belief_map.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["belief_map"] = mod
    spec.loader.exec_module(mod)
    return mod


def _kernel(bmod: ModuleType) -> object:
    # a synthetic monster: still for ~1 s, then about one cell per second outward
    samples = [(t, d) for t in bmod.KERNEL_T for d in range(int(t) + 1) for _ in range(10)]
    return bmod.fit_kernel(samples)


def test_geodesic_respects_walls(bmod: ModuleType) -> None:
    ok = np.ones((9, 9), dtype=bool)
    ok[:8, 4] = False  # a wall with a gap at the bottom row
    d = bmod.geodesic(ok, (2, 2), 20)
    assert d[2, 2] == 0 and d[2, 3] == 1
    assert d[2, 4] == -1  # the wall itself
    # straight-line 4 cells, around the wall's end: down 6, across, up 6
    assert d[2, 6] > 6
    assert bmod.geodesic(ok, (2, 2), 3)[2, 6] == -1  # beyond rmax: unreachable


def test_kernel_rows_sum_to_one_and_spread(bmod: ModuleType) -> None:
    k = _kernel(bmod)
    for t in (0.0, 0.2, 1.0, 3.3, 12.0, 99.0):
        assert k.ring(t).sum() == pytest.approx(1.0)
    assert k.ring(0.0)[0] == 1.0
    assert k.quantile(1.0, 0.5) <= k.quantile(5.0, 0.5) <= k.quantile(20.0, 0.5)
    assert bmod.Kernel.from_json(k.to_json()).ring(4.0) == pytest.approx(k.ring(4.0), abs=1e-4)


def test_association_keeps_near_and_starts_far(bmod: ModuleType) -> None:
    ok = np.ones((60, 60), dtype=bool)
    m = bmod.BeliefMap(ok, _kernel(bmod), [bmod.Variant("kernel")])
    a = m.update(0, [(10.0, 10.0)])
    assert a == [(0, 0, True)]
    a = m.update(NS, [(11.0, 10.0), (40.0, 40.0)])  # one cell later: the same track; far: new
    assert sorted(a) == [(0, 0, False), (1, 1, True)]
    assert m.tracks[0].cell == (11.0, 10.0) and m.tracks[0].n == 2


def test_tracks_drop_after_the_cap(bmod: ModuleType) -> None:
    ok = np.ones((40, 40), dtype=bool)
    m = bmod.BeliefMap(ok, _kernel(bmod), [bmod.Variant("kernel")], cap_s=5.0)
    m.update(0, [(10.0, 10.0)])
    m.update(4 * NS, [])
    assert 0 in m.tracks
    m.update(6 * NS, [])
    assert not m.tracks


def test_negative_evidence_moves_belief_off_visible_cells(bmod: ModuleType) -> None:
    ok = np.ones((60, 60), dtype=bool)
    vis_occ = np.ones((60, 60))
    vis_occ[:31, :] = 0.0  # an occluder over the whole visible half: it tells nothing
    vs = [bmod.Variant("kernel"), bmod.Variant("ne", 0.5),
          bmod.Variant("occ", 0.5, vis=vis_occ)]  # fmt: skip
    m = bmod.BeliefMap(ok, _kernel(bmod), vs)
    m.update(0, [(30.0, 30.0)])
    visible = np.zeros((60, 60), dtype=bool)
    visible[:31, :] = True  # the upper half (with the last-seen row) on screen, empty
    for k in range(1, 10):
        m.update(k * NS // 3, [], visible)
    tr = m.tracks[0]
    t = 3 * NS
    p_k, m_k = m.posterior(tr, t, "kernel")
    p_n, m_n = m.posterior(tr, t, "ne")
    assert m_k == pytest.approx(1.0) and m_n < m_k
    oy = tr.y0
    up_k, up_n = p_k[: 30 - oy].sum(), p_n[: 30 - oy].sum()
    assert up_n < 0.5 * up_k  # the visible, empty half lost most of its share
    _p_o, m_o = m.posterior(tr, t, "occ")
    assert m_o == pytest.approx(1.0)  # every visible cell occluded: no information
    top = m.probes(tr, t, "ne", k=3)
    assert all(c[1] > 30 for c in top)  # the probes go to the unseen half


def test_existence_falls_when_everything_is_seen_empty(bmod: ModuleType) -> None:
    ok = np.ones((50, 50), dtype=bool)
    m = bmod.BeliefMap(ok, _kernel(bmod), [bmod.Variant("ne", 0.5)])
    m.update(0, [(25.0, 25.0)])
    visible = np.ones((50, 50), dtype=bool)
    for k in range(1, 7):
        m.update(k * NS // 3, [], visible)
    _p, mass = m.posterior(m.tracks[0], 2 * NS, "ne")
    assert mass < 0.05


def test_a_box_near_a_cell_is_not_a_miss(bmod: ModuleType) -> None:
    ok = np.ones((50, 50), dtype=bool)
    m = bmod.BeliefMap(ok, _kernel(bmod), [bmod.Variant("ne", 0.5)])
    m.update(0, [(10.0, 10.0)])
    visible = np.ones((50, 50), dtype=bool)
    m.update(NS // 3, [(40.0, 40.0)], visible)  # another monster far away: a new track
    lm = m.tracks[1].lm["ne"]
    assert lm.max() == 0.0  # the new track was seen this frame: no miss on it
    lm0 = m.tracks[0].lm["ne"]
    assert lm0.min() < 0.0


def test_probes_are_spaced(bmod: ModuleType) -> None:
    p = np.zeros((10, 10))
    p[5, 5], p[5, 6], p[2, 2], p[8, 8] = 0.4, 0.3, 0.2, 0.1
    assert bmod.top_cells(p, 3, False) == [(5, 5), (6, 5), (2, 2)]
    assert bmod.top_cells(p, 3, True) == [(5, 5), (2, 2), (8, 8)]
    assert bmod.top_cells(p, 3, True, (100, 200))[0] == (105, 205)


def test_walls_bound_the_belief(bmod: ModuleType) -> None:
    ok = np.ones((60, 60), dtype=bool)
    ok[:, 33] = False  # a full wall three cells east of the last sighting
    m = bmod.BeliefMap(ok, _kernel(bmod), [bmod.Variant("kernel")])
    m.update(0, [(30.0, 30.0)])
    g = m.grid(20 * NS, "kernel")
    assert g[:, 33:].sum() == 0.0
    assert g.sum() == pytest.approx(1.0)


def test_occluder_map_marks_seen_but_empty(bmod: ModuleType) -> None:
    n_obs = np.full((30, 30), 1000.0)
    n_hit = np.full((30, 30), 2.0)
    n_hit[10:13, 10:13] = 0.0  # often in view, never a box: hidden
    vis = bmod.occluder_map(n_obs, n_hit, prior_hits=1.0)
    assert vis[11, 11] < 0.3
    assert vis[25, 25] == pytest.approx(1.0)
    n_obs2 = n_obs.copy()
    n_obs2[20:23, 20:23] = 1.0  # barely seen and empty: stays near the mean (shrinkage)
    n_hit2 = n_hit.copy()
    n_hit2[20:23, 20:23] = 0.0
    assert bmod.occluder_map(n_obs2, n_hit2, prior_hits=1.0)[21, 21] > 0.8


def test_visible_px_screen_and_windows(bmod: ModuleType) -> None:
    px = np.array([[640.0, 400.0], [2.0, 400.0], [100.0, 100.0], [640.0, 719.0]])
    v = bmod.visible_px(px, [(0.0, 0.0, 220.0, 326.0)])
    assert v.tolist() == [True, False, False, False]


def test_heading_needs_a_real_walk(bmod: ModuleType) -> None:
    walk = [(0, (10.0, 10.0)), (NS // 2, (11.0, 10.0)), (NS, (13.0, 10.0))]
    hd = bmod.heading(walk)
    assert hd == pytest.approx((1.0, 0.0))
    still = [(0, (10.0, 10.0)), (NS // 2, (10.4, 10.0)), (NS, (10.8, 10.0))]
    assert bmod.heading(still) is None  # under 1.5 cells: box -> cell noise
    assert bmod.heading(walk[-1:]) is None


def test_walk_on_component_leans_along_the_heading(bmod: ModuleType) -> None:
    ok = np.ones((60, 60), dtype=bool)
    vs = [bmod.Variant("kernel"), bmod.Variant("lead", lead=0.5)]
    m = bmod.BeliefMap(ok, _kernel(bmod), vs)
    for k, x in enumerate((26.0, 27.0, 28.0, 30.0)):
        m.update(k * NS // 3, [(x, 30.0)])
    tr = m.tracks[0]
    assert tr.lead_dist is not None
    t = tr.t + 2 * NS
    cx = 30 - tr.x0
    for v, more_east in (("kernel", False), ("lead", True)):
        p, _m = m.posterior(tr, t, v)
        east, west = p[:, cx + 1 :].sum(), p[:, :cx].sum()
        assert bool(east > 1.3 * west) is more_east


def test_box_means_mean_and_edges(bmod: ModuleType) -> None:
    vals = np.full((100, 100), 7.0)
    valid = np.ones((100, 100), dtype=bool)
    valid[:, 50:] = False
    out = bmod.box_means(vals, valid, [[25.0, 80.0], [80.0, 80.0], [2.0, 80.0]], (-5, -20, 5, -2))
    assert out[0] == pytest.approx(7.0)
    assert np.isnan(out[1])  # no valid pixel in the box
    assert np.isnan(out[2])  # the box leaves the image


def test_floor_residual_flags_what_does_not_move_with_the_floor(bmod: ModuleType) -> None:
    rng = np.random.default_rng(3)
    big = rng.integers(0, 255, (400, 700, 3)).astype(np.uint8)
    big = np.repeat(np.repeat(big, 2, 0), 2, 1)  # 2-px texture: survives the half resolution
    a = big[40 : 40 + 720, 40 : 40 + 1280]
    b = big[40 + 20 : 40 + 20 + 720, 40 + 30 : 40 + 30 + 1280].copy()  # the floor moved
    b[300:400, 600:700] = 0  # a dark "canopy" drawn over b that a does not have there
    res, mag = bmod.floor_residual(a, b, np.zeros((720, 1280), dtype=bool))
    assert mag == pytest.approx(36.0, abs=3.0)
    assert np.median(res[50:120, 50:200]) < 5  # the floor matches
    assert np.median(res[160:190, 310:340]) > 30  # the canopy does not


def test_cover_map_scales_between_floor_and_cover(bmod: ModuleType) -> None:
    n = np.full((30, 30), 10.0)
    s = n * 2.0
    s[10:13, 10:13] = n[10:13, 10:13] * 40.0
    vis = bmod.cover_map(n, s)
    assert vis[11, 11] == 0.0 and vis[25, 25] == 1.0
    assert bmod.cover_map(np.zeros((5, 5)), np.zeros((5, 5))).min() == 1.0


def test_default_kernel_is_a_kernel(bmod: ModuleType) -> None:
    k = bmod.Kernel.default()
    assert k.mass.shape == (len(bmod.KERNEL_T), bmod.RADIUS + 1)
    assert k.ring(3.0).sum() == pytest.approx(1.0)
    assert k.quantile(1.0, 0.5) < k.quantile(10.0, 0.5)
