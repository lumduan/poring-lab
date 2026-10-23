"""The item class's labels (docs/planning/item-class.md, pre-registered 2026-10-23 a46893d;
scripts/item_labels.py, scripts/item_blind_score.py): the pure parts on SYNTHETIC packets / boxes /
rows, plus a REAL positive case from the banked data (skipped when the NAS or the frozen local
params are absent; client data is never committed)."""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts"))
import item_blind_score as ibs  # noqa: E402
import item_labels as il  # noqa: E402

S = 10**9


def _appear(
    t: float,
    fid: int,
    item: int = 909,
    kind: str = "fall",
    x: int = 10,
    y: int = 20,
    sx: int = 6,
    sy: int = 6,
) -> dict[str, Any]:
    return {
        "type": "floor_item_appear",
        "t_mono_ns": int(t * S),
        "floor_id": fid,
        "item_id": item,
        "kind": kind,
        "x": x,
        "y": y,
        "sub_x": sx,
        "sub_y": sy,
    }


def _vanish(t: float, fid: int) -> dict[str, Any]:
    return {"type": "floor_item_vanish", "t_mono_ns": int(t * S), "floor_id": fid}


# --- floor spans ---------------------------------------------------------------------------------


def test_floor_items_spans_vanish_mapchange_and_end() -> None:
    ev = [
        {"type": "map_change", "t_mono_ns": 0},
        _appear(1, 1),
        _appear(2, 2, kind="in_sight"),
        _appear(2.5, 1),  # re-sent while live: ignored
        _vanish(5, 1),
        _appear(6, 3),
        {"type": "map_change", "t_mono_ns": 8 * S},  # ends 2 and 3
        _appear(9, 4),
        {"type": "time_sync", "t_mono_ns": 12 * S},  # the stream's last packet ends 4
    ]
    fl = {f.floor_id: f for f in il.floor_items(ev)}
    assert (fl[1].t_a, fl[1].t_v, fl[1].vanished) == (1 * S, 5 * S, True)
    assert (fl[2].t_v, fl[2].vanished, fl[2].kind) == (8 * S, False, "in_sight")
    assert (fl[3].t_v, fl[3].vanished) == (8 * S, False)
    assert (fl[4].t_v, fl[4].vanished) == (12 * S, False)
    assert il.first_map_change(ev) == 0


def test_floor_id_seen_again_is_a_new_span() -> None:
    ev = [_appear(1, 7), _vanish(2, 7), _appear(3, 7, kind="in_sight"), _vanish(4, 7)]
    spans = [(f.t_a, f.t_v, f.kind) for f in il.floor_items(ev)]
    assert spans == [(1 * S, 2 * S, "fall"), (3 * S, 4 * S, "in_sight")]


def test_phase_windows() -> None:
    f = il.Floor(1, 909, 0, 0, 6, 6, "fall", 10 * S, 20 * S, True)
    d_app, d_gone = int(0.8 * S), int(0.5 * S)
    assert il.phase(f, int(9.9 * S), d_app, d_gone) == "none"
    assert il.phase(f, 10 * S, d_app, d_gone) == "settling"
    assert il.phase(f, int(10.79 * S), d_app, d_gone) == "settling"
    assert il.phase(f, int(10.8 * S), d_app, d_gone) == "on"
    assert il.phase(f, int(19.99 * S), d_app, d_gone) == "on"
    assert il.phase(f, 20 * S, d_app, d_gone) == "vanishing"
    assert il.phase(f, int(20.5 * S), d_app, d_gone) == "none"
    # ended by a map change / the stream's end: no vanishing window
    g = il.Floor(1, 909, 0, 0, 6, 6, "fall", 10 * S, 20 * S, False)
    assert il.phase(g, 20 * S, d_app, d_gone) == "none"
    # vanished before it settled: settling, then the vanishing window
    h = il.Floor(1, 909, 0, 0, 6, 6, "fall", 10 * S, int(10.3 * S), True)
    assert il.phase(h, int(10.2 * S), d_app, d_gone) == "settling"
    assert il.phase(h, int(10.4 * S), d_app, d_gone) == "vanishing"


def test_item_cell_h12() -> None:
    f = il.Floor(1, 909, 100, 50, 3, 12, "fall", 0, 1, True)
    assert il.item_cell(f, il.H12, il.H12) == (100 - 0.25, 50 + 0.5)
    assert il.item_cell(f, il.H16, il.H16) == (100 - 5 / 16, 50 + 4 / 16)


# --- boxes ---------------------------------------------------------------------------------------


def test_tpl_box_covers_the_template_pixels() -> None:
    # a 10 x 14 (h x w) template whose top-left pixel is (100, 200): centre (106.5, 204.5)
    b = il.tpl_box((106.5, 204.5), (10, 14), pad=0)
    assert b == (100.0, 200.0, 114.0, 210.0)
    assert il.tpl_box((106.5, 204.5), (10, 14), pad=1) == (99.0, 199.0, 115.0, 211.0)


def test_iou_and_stacked() -> None:
    a = (0.0, 0.0, 10.0, 10.0)
    assert il.iou(a, a) == 1.0
    assert il.iou(a, (10.0, 0.0, 20.0, 10.0)) == 0.0
    assert math.isclose(il.iou(a, (5.0, 0.0, 15.0, 10.0)), 50 / 150)
    assert not il.stacked([a, (5.0, 0.0, 15.0, 10.0)])  # IoU 0.33 < 0.5: two boxes
    assert il.stacked([a, (1.0, 0.0, 11.0, 10.0)])  # IoU 0.82


def test_ui_status() -> None:
    rects = [(0.0, 532.0, 600.0, 626.0)]
    size = (1280, 720)
    assert il.ui_status((700, 300, 716, 316), rects, size) == "clear"
    assert il.ui_status((100, 540, 116, 556), rects, size) == "hidden"  # wholly under the chat
    assert il.ui_status((100, 525, 116, 541), rects, size) == "ui_partial"
    assert il.ui_status((1275, 300, 1291, 316), rects, size) == "edge_partial"
    assert il.ui_status((1300, 300, 1316, 316), rects, size) == "hidden"  # off screen


def test_in_reach() -> None:
    assert il.in_reach(-80, -40) and il.in_reach(1360, 880)
    assert not il.in_reach(-81, 300) and not il.in_reach(600, 881)


# --- measurement maths ---------------------------------------------------------------------------


def test_youden_separates() -> None:
    present = [0.7, 0.8, 0.9, 0.95]
    absent = [0.1, 0.2, 0.3, 0.75]
    t = il.youden(present, absent)
    tpr = np.mean(np.asarray(present) >= t)
    fpr = np.mean(np.asarray(absent) >= t)
    assert tpr - fpr == pytest.approx(0.75)
    assert 0.3 < t <= 0.8


def test_bins_and_delays() -> None:
    ages, pres = [], []
    for i in range(300):  # absent before 0.6 s, present after; plateau 1.0
        a = i * 0.01
        ages.append(a)
        pres.append(a >= 0.6)
    bins = il.bin_shares(ages, pres, 0.0, 3.0)
    assert bins[5][2] == 0.0 and bins[6][2] == 1.0
    assert il.appear_delay(bins, 1.0) == pytest.approx(0.8)  # 0.6 + the 0.2 margin
    # an empty bin later fails the "every bin" rule
    holey = [b if b[0] != 1.5 else (1.5, 0, float("nan")) for b in bins]
    assert il.appear_delay(holey, 1.0) == pytest.approx(1.8)  # the first start after the hole
    assert il.appear_delay([(b[0], b[1], 0.5) for b in bins], 1.0) is None
    gone = il.bin_shares(ages[:150], [a < 0.3 for a in ages[:150]], 0.0, 1.5)
    assert il.gone_delay(gone) == pytest.approx(0.5)


def test_solve_subtable_recovers_a_synthetic_table() -> None:
    rng = np.random.default_rng(3)
    true_dx = {3: 0.05, 6: 0.0, 9: -0.04, 12: 0.1}
    true_dy = {3: -0.02, 6: 0.0, 9: 0.03, 12: -0.06}
    anchors = {909: (1.5, -9.0), 512: (-0.5, -7.0)}
    rows = []
    for i in range(400):
        sx, sy = int(rng.choice(il.SUBS)), int(rng.choice(il.SUBS))
        item = 909 if i % 2 else 512
        j = np.array([[32.0 + rng.normal(0, 1), -1.0], [2.0, 24.0 + rng.normal(0, 1)]])
        r = j @ np.array([true_dx[sx], true_dy[sy]]) + np.array(anchors[item])
        r = r + rng.normal(0, 0.3, 2)
        rows.append({"r": tuple(r), "J": j.tolist(), "sx": sx, "sy": sy, "item": item})
    rows.append({"r": (40.0, 40.0), "J": [[32, 0], [0, 24]], "sx": 3, "sy": 3, "item": 909})
    st = il.solve_subtable(rows)
    for s in il.SUBS:
        assert st["ox"][s] == pytest.approx(il.H12[s] + true_dx[s], abs=0.01)
        assert st["oy"][s] == pytest.approx(il.H12[s] + true_dy[s], abs=0.01)
    assert st["dropped"] >= 1


def test_draw_items_caps_per_floor_item_and_is_seeded() -> None:
    cands = [{"sid": "A", "floor_id": i // 10, "frame": f"{i}"} for i in range(50)]
    d1 = il.draw_items(cands, 12, 5)
    d2 = il.draw_items(cands, 12, 5)
    assert d1 == d2 and len(d1) == 12
    per: dict[int, int] = {}
    for c in d1:
        per[c["floor_id"]] = per.get(c["floor_id"], 0) + 1
    assert max(per.values()) <= il.PER_FLOOR_ITEM
    assert len(il.draw_items(cands[:4], 12, 5)) == 3  # one floor item: at most 3, all taken


def test_g1_summary_bar() -> None:
    rows = [
        {"item_id": 909, "bad": i < 2, "g2_dx": 1, "g2_dy": -1, "route_u": True} for i in range(60)
    ]
    g = il.g1_summary(rows)
    assert g["scored"] == 60 and g["bad"] == 2 and g["g1_pass"]
    assert g["g2_median_abs_dx"] == 1.0
    few = il.g1_summary(rows[:40])
    assert not few["g1_pass"]  # < 50 scored: no verdict, no training
    worse = il.g1_summary([{**r, "bad": i < 4} for i, r in enumerate(rows)])
    assert not worse["g1_pass"]  # 4 / 60 = 6.7 % > 5 %


def test_crop_pair_shape_and_box() -> None:
    img = np.zeros((720, 1280, 3), np.uint8)
    pair = il.crop_pair(img, (600.0, 300.0, 616.0, 312.0))
    side = (2 * il.CROP_HALF + 1) * il.CROP_SCALE
    assert pair.shape == (side, 2 * side + 8, 3)
    left, right = pair[:, :side], pair[:, side + 8 :]
    assert left.max() == 0  # the plain copy
    assert (right == [0, 255, 255]).all(-1).sum() > 0  # the cyan box


def test_split_refuses_the_monster_test_block() -> None:
    with pytest.raises(SystemExit):
        il.load_session("20261021T122650-orcsdun01-col2")
    fit = set(il.split_of("prt_fild08", "fit"))
    train = set(il.split_of("prt_fild08", "train"))
    test = set(il.split_of("prt_fild08", "test"))
    assert not (fit & train) and not (fit & test) and not (train & test)
    b = il.SPLIT["orcsdun01"]["blocks"]
    assert b["fit"][1] < b["train"][0] and b["train"][1] < b["test"][0]


# --- the blind scorer ----------------------------------------------------------------------------


def _key() -> dict[str, Any]:
    crops = {}
    for i in range(1, 41):
        crops[f"{i:03d}"] = {"map": "prt_fild08", "truth": "item"}
    for i in range(41, 61):
        crops[f"{i:03d}"] = {"map": "prt_fild08", "truth": "none"}
    return {"crops": crops}


def test_item_blind_score_bars() -> None:
    key = _key()
    perfect = {
        c: ({"q1": "yes", "q2": "good"} if k["truth"] == "item" else {"q1": "no"})
        for c, k in key["crops"].items()
    }
    r = ibs.per_map(key, perfect)["prt_fild08"]
    assert r["good_share"] == 1.0 and r["present_right_share"] == 1.0 and r["pass"]
    # 4 of 40 items "loose": 90 % good -> passes; 5 -> 87.5 % fails
    a4 = dict(perfect)
    for c in ("001", "002", "003", "004"):
        a4[c] = {"q1": "yes", "q2": "loose"}
    assert ibs.per_map(key, a4)["prt_fild08"]["pass"]
    a5 = dict(a4)
    a5["005"] = {"q1": "yes", "q2": "off"}
    assert not ibs.per_map(key, a5)["prt_fild08"]["pass"]
    # 3 wrong of 60 on presence = 95 % passes; 4 fails ("unsure" is wrong, a missing answer too)
    p3 = dict(perfect)
    p3["041"] = {"q1": "yes", "q2": "good"}
    p3["042"] = {"q1": "unsure"}
    del p3["043"]
    assert ibs.per_map(key, p3)["prt_fild08"]["present_right_share"] == pytest.approx(57 / 60)
    assert ibs.per_map(key, p3)["prt_fild08"]["pass"]
    p4 = dict(p3)
    p4["001"] = {"q1": "no"}
    assert not ibs.per_map(key, p4)["prt_fild08"]["pass"]
    res = ibs.score(key, {"A": perfect, "B": p4})
    assert res["map_pass"] == {"prt_fild08": False}
    assert res["both_good"] == 39
    assert ibs.both_good(key, perfect, a4) == [f"{i:03d}" for i in range(5, 41)]


# --- a REAL positive case (local / NAS data only) ------------------------------------------------

PARAMS = il.OUT / "params" / "params.json"
POSITIVE = il.OUT / "params" / "positive_case.json"


@pytest.mark.skipif(
    not (PARAMS.exists() and POSITIVE.exists() and il.DATASETS.exists()),
    reason="the frozen params / the positive case / the NAS are not here",
)
def test_real_drop_visible_at_its_predicted_spot() -> None:
    """A fit-session frame (prt_fild08, flow48) where a known fresh drop lies at its predicted
    spot: the frozen params' prediction scores >= tau at +-1 px (G1's own test), and the same
    template at an empty-floor point of the same frame scores < tau."""
    p = il.load_params()
    pc = json.loads(POSITIVE.read_text())
    s = il.load_session(pc["sid"])
    fl = next(f for f in il.floor_items(s.events) if f.floor_id == pc["floor_id"])
    t_f = int(pc["t_ns"])
    assert il.phase(fl, t_f, int(p["D_APPEAR_s"] * S), int(p["D_GONE_s"] * S)) == "on"
    world = il.World(s)
    fws = world.steps(t_f)
    assert il.World.still(fws)
    geo = il.Geo(s.map)
    sc = geo.scene(fws[-1].self_pos)
    m = p["maps"][s.map]
    c = il.predicted_centre(geo, sc, fl, p["table"], {fl.item_id: m["anchors_px"][str(fl.item_id)]})
    tpl = il.load_tpls(il.OUT / "params" / f"templates_{s.map}.npz")[fl.item_id]
    path = next(pth for _k, t, pth in s.frames if t == t_f)
    img = il.read_rgb(path)
    hit = il.best_ncc(img, tpl, c, il.R_G2)
    assert hit is not None and hit["r1"]["ncc"] >= m["tau"]
    empty = il.best_ncc(img, tpl, tuple(pc["empty_centre"]), il.R_FIT)
    assert empty is not None and empty["fit"]["ncc"] < m["tau"]
