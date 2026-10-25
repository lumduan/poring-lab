"""mvp_watch.py (rogue-gef10 Amendment A4, docs/planning/orclord-recognizer.md): the Orc Lord
recognizer's pure decision on synthetic frames, its loader (fail closed), its isolation (pixels
in only), the study's scoring helpers, and one REAL positive case from the Orc Lord watch that
skips when the recording or the model is absent (both are local, never committed)."""

from __future__ import annotations

import ast
import json
import os
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts"))

import mvp_watch as mw  # noqa: E402
import mvp_watch_study as st  # noqa: E402

GRASS = (40, 90, 80)  # BGR: a dull field green the aura rule never takes
RIM = (150, 250, 180)  # BGR: the aura's saturated light green (G 250, R 180, B 150)


def _title() -> np.ndarray:
    x0, y0, x1, y1 = (v // mw.STEP for v in mw.TITLE_BOX)
    g = np.zeros((y1 - y0, x1 - x0), np.float32)
    g[:, ::4] = 200.0  # any fixed pattern: the game's title bar stands in
    return g


def _model(**kw: object) -> mw.Model:
    base: dict[str, object] = dict(
        body_lut=np.zeros(mw.NBINS, np.float32),
        lin_w=np.zeros((mw.N_FEATURES, *mw.WIN), np.float32), lin_b=-10.0, lin_thr=0.0,
        aura_thr=0.08, title=_title(),
    )  # fmt: skip
    base.update(kw)
    return mw.Model(**base)  # type: ignore[arg-type]


def _frame(model: mw.Model, colour: tuple[int, int, int] = GRASS) -> np.ndarray:
    f = np.zeros((720, 1280, 3), np.uint8)
    f[:, :] = colour
    x0, y0, x1, y1 = mw.TITLE_BOX
    grey = np.repeat(np.repeat(model.title, 2, axis=0), 2, axis=1)
    f[y0:y1, x0:x1] = grey[: y1 - y0, : x1 - x0, None].astype(np.uint8)
    return f


def _ring(f: np.ndarray, foot: tuple[int, int], colour: tuple[int, int, int] = RIM) -> None:
    """Draw the aura's ring (full-frame pixels) around a foot point, the way the client does: a
    thin bright ellipse whose centre sits 16 px above the feet."""
    cx, cy = foot[0], foot[1] - 16
    yy, xx = np.mgrid[0:720, 0:1280]
    r = ((xx - cx) / 54.0) ** 2 + ((yy - cy) / 30.0) ** 2
    f[(r <= 1.0) & (r >= 0.55)] = colour


def test_aura_rule_takes_the_rim_and_not_grass_or_foliage() -> None:
    lut = mw.aura_lut()
    idx = mw.lut_index(np.array([[RIM, GRASS, (60, 200, 170), (250, 250, 250)]], np.uint8))
    # the rim; field grass; sunlit foliage (G 200, low blue); white text or effects
    assert lut[idx].tolist() == [[1.0, 0.0, 0.0, 0.0]]


def test_plain_field_is_not_seen_and_a_ring_is_seen_where_it_is_drawn() -> None:
    m = _model()
    f = _frame(m)
    v = mw.decide(f, m)
    assert v["seen"] is False and v["reason"] is None and v["aura"] == 0.0
    _ring(f, (900, 500))
    v = mw.decide(f, m)
    assert v["seen"] is True and v["cue"] == "aura"
    assert abs(v["where"][0] - 900) <= 12 and abs(v["where"][1] - 500) <= 16
    assert v["score"] >= 0.0


def test_a_ring_under_the_ui_or_on_our_own_character_is_not_seen() -> None:
    m = _model()
    f = _frame(m)
    _ring(f, (300, 600))  # under the chat window (0, 532)-(600, 626)
    assert mw.decide(f, m, ui_rects=mw.HUNT_RECTS)["seen"] is False
    g = _frame(m)
    g[372:384, 612:668] = RIM  # our own HP bar (its top at y 358-396 on 99 % of frames) ...
    g[300:360, 615:665] = RIM  # ... and a potion's green sparkle on our Rogue
    assert mw.decide(g, m)["seen"] is False


def test_loading_screen_and_wrong_size_are_never_seen() -> None:
    m = _model()
    f = _frame(m)
    _ring(f, (900, 500))
    f[0:16, 0:220] = 255  # the title bar is gone (a loading screen)
    v = mw.decide(f, m)
    assert v["seen"] is False and v["reason"] == "no_game_view"
    v = mw.decide(np.zeros((360, 640, 3), np.uint8), m)
    assert v["seen"] is False and v["reason"] == "not_1280x720"


def test_party_window_scores_match_the_window_vectors_and_the_foot_mapping() -> None:
    rng = np.random.default_rng(0)
    feats = rng.normal(size=(mw.N_FEATURES, 45, 80)).astype(np.float32)
    w = rng.normal(size=(mw.N_FEATURES, *mw.WIN)).astype(np.float32)
    s = mw.window_scores(feats, w, 0.5)
    v = mw.window_vectors(feats)
    assert s.shape == v.shape[:2] == (45 - mw.WIN[0] + 1, 80 - mw.WIN[1] + 1)
    assert np.allclose(s[10, 20], v[10, 20] @ w.reshape(-1) + 0.5, atol=1e-3)
    # a foot at the bottom centre of window (10, 20) maps back to it
    fx = (20 + mw.WIN[1] / 2) * mw.CELL
    fy = (10 + mw.WIN[0]) * mw.CELL - 0.5 * mw.CELL
    assert mw.foot_window(fx, fy) == (10, 20)


def test_a_party_window_above_its_threshold_is_seen_with_its_foot() -> None:
    w = np.zeros((mw.N_FEATURES, *mw.WIN), np.float32)
    w[2] = 1.0  # the window's mean red
    m = _model(lin_w=w, lin_b=0.0, lin_thr=20.0)
    f = _frame(m)
    f[300:412, 900:980] = (40, 60, 250)  # a red 80 x 112 unit, its feet at (940, 412)
    v = mw.decide(f, m)
    assert v["seen"] is True and v["cue"] == "party"
    assert abs(v["where"][0] - 940) <= 16 and abs(v["where"][1] - 412) <= 16


def test_cue_selection_aura_alone_ignores_the_party_window() -> None:
    w = np.zeros((mw.N_FEATURES, *mw.WIN), np.float32)
    w[2] = 1.0
    m = _model(lin_w=w, lin_b=0.0, lin_thr=20.0)
    f = _frame(m)
    f[300:412, 900:980] = (40, 60, 250)
    v = mw.decide(f, m, cues=("aura",))
    assert v["seen"] is False and v["party"] is None
    _ring(f, (300, 450))
    v = mw.decide(f, m, cues=("aura",))
    assert v["seen"] is True and v["cue"] == "aura"
    with pytest.raises(ValueError):
        mw.decide(f, m, cues=("nose",))


def test_save_load_round_trip_and_fail_closed(tmp_path: Path) -> None:
    m = _model()
    p = tmp_path / "m.npz"
    sha = mw.save(p, m)
    back = mw.load(p, sha)
    assert back.sha256 == sha and back.aura_thr == m.aura_thr and back.lin_b == m.lin_b
    assert np.array_equal(back.title, m.title)
    with pytest.raises(mw.ModelUnavailable):
        mw.load(p, "0" * 64)
    with pytest.raises(mw.ModelUnavailable):
        mw.load(tmp_path / "missing.npz")


def test_pixels_in_only_the_module_reads_no_packets() -> None:
    src = (ROOT / "scripts" / "mvp_watch.py").read_text()
    mods = set()
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.Import):
            mods |= {n.name.split(".")[0] for n in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            mods.add(node.module.split(".")[0])
    assert mods <= {"__future__", "hashlib", "time", "dataclasses", "pathlib", "typing", "numpy"}


# --- the study's scoring (orclord-recognizer.md section 3) -------------------------------------


def test_cell_scores_delay_within_and_reentries() -> None:
    seq = [(0.0, "pos", False), (1.0, "pos", True), (2.0, "pos", True), (3.0, "neg", False),
           (9.0, "pos", False), (10.0, "pos", False), (11.0, "pos", False)]  # fmt: skip
    eps = st.cell_scores(seq)["episodes"]
    assert [e["delay"] for e in eps] == [1.0, None]
    assert [e["within"] for e in eps] == [True, False]
    assert eps[0]["first_frame"] is False
    late = st.cell_scores([(0.0, "pos", False), (1.0, "pos", False), (2.2, "pos", True)])
    assert late["episodes"][0]["within"] is False  # 2.2 s > 1.1 s


def test_kind_split_and_rates() -> None:
    party = {"job": 1190, "in_view": True, "box": (100, 100, 180, 200)}
    lady = {"job": 1273, "in_view": True, "box": (300, 100, 370, 190)}
    off = {"job": 1189, "in_view": False, "box": (1270, 300, 1330, 390)}  # partly on screen
    assert st.kind_of({"units": [party], "flags": []}) == "pos"
    assert st.kind_of({"units": [lady], "flags": []}) == "neg"
    assert st.kind_of({"units": [lady, off], "flags": []}) == "edge"
    assert st.kind_of({"units": [lady], "flags": ["party_edge"]}) == "edge"
    rows = [{"frame_id": i, "t": int(i * 1e9), "map": "gef_fild10.gat"} for i in range(400)]
    part = st.pilot_part(rows)
    assert part[0] == "dev" and part[299] == "dev" and part[300] == "held"
    assert st.fp_rate(1, 600) == 1.0 and st.fp_rate(0, 0) is None


def test_party_edge_flags_after_a_vanish_and_around_an_appearance() -> None:
    s = 1_000_000_000
    assert st.frame_flags(5 * s, [], [], [2 * s], []) == ["party_edge"]
    assert st.frame_flags(7 * s, [], [], [2 * s], []) == []
    assert st.frame_flags(10 * s, [], [], [], [int(10.4 * s)]) == ["party_edge"]
    assert st.frame_flags(10 * s, [9 * s], [9 * s], [], []) == ["settle", "gm"]


# --- round 2 (orclord-recognizer.md section 10 + Amendment 10a): synthetic cases only -----------

SEC = 1_000_000_000


def _ev(kind: str, t: float, **kw: object) -> dict[str, object]:
    return {"kind": kind, "t_ns": int(t * SEC), **kw}


def _win(warp: float | None, settle: float, end: float | None) -> dict[str, object]:
    return {"i": 0, "j": 0, "at": [], "dist": None,
            "warp": None if warp is None else int(warp * SEC), "settle": int(settle * SEC),
            "end": None if end is None else int(end * SEC)}  # fmt: skip


def _f(t: float, fid: int, kind: str, seen: bool = False,
       lord: bool = False) -> tuple[int, int, str, bool, bool]:  # fmt: skip
    return (int(t * SEC), fid, kind, seen, lord)


def test_round2_recipe_is_the_aura_rule_alone() -> None:
    assert st.ROUND2_CUES == ("aura",)
    assert st.RECALL_S == 1.1 and st.ROUND2_RECALL == 0.95 and st.ROUND2_FP_PER_10MIN == 1.0


def test_hop_windows_run_from_the_settle_to_the_next_warp_or_the_kill() -> None:
    events = [_ev("run_start", 0), _ev("at_cell", 12, i=0, at=[10, 10]), _ev("spawn", 14, i=0),
              _ev("hop", 22, i=0, j=0, at=[27, 10], dist=17),
              _ev("hop", 35, i=0, j=1, at=[24, 10], dist=14),
              _ev("hop", 48, i=0, j=2, at=[21, 10], dist=11),
              _ev("killmonster2", 58, i=0), _ev("at_cell", 70, i=1, at=[50, 50])]  # fmt: skip
    # map changes: at_cell 0, hops 0 and 1, at_cell 1 (hop 2's own @warp is missing)
    w = st.hop_windows(events, [int(t * SEC) for t in (10, 20, 33, 68)])
    assert [(x["i"], x["j"], x["dist"]) for x in w] == [(0, 0, 17), (0, 1, 14), (0, 2, 11)]
    assert [x["warp"] for x in w] == [20 * SEC, 33 * SEC, None]  # 33 s is before hop 1's event
    assert [x["settle"] for x in w] == [22 * SEC, 35 * SEC, 48 * SEC]
    assert [x["end"] for x in w] == [33 * SEC, 58 * SEC, 58 * SEC]  # the next @warp, else the kill


def test_entries_need_not_in_view_before_the_warp_and_in_view_in_the_window() -> None:
    frames = [_f(9.5, 1, "pos", True, True),  # the spawn cell: in view before the far hop's warp
              _f(11.0, 2, "neg"), _f(12.0, 3, "neg"),  # the far hop: out of view
              _f(13.5, 4, "pos", True),  # the next @warp, before its settle: outside the window
              _f(15.0, 5, "neg"), _f(15.5, 6, "edge", True),  # partly on screen, seen: "early"
              _f(16.0, 7, "pos"), _f(16.5, 8, "pos"), _f(17.05, 9, "pos", True, True),
              _f(17.5, 10, "pos", True),
              _f(19.5, 11, "pos", True)]  # fmt: skip
    far, entry, near = st.entries_of([_win(10, 11, 13), _win(13, 15, 19), _win(19, 20, None)],
                                     frames)  # fmt: skip
    assert far["before"] == "pos" and far["entry"] is False and far["frames"] == 2
    assert entry["before"] == "neg" and entry["entry"] is True
    assert entry["first"] == 7 and entry["t_first"] == 16 * SEC and entry["lord_first"] is False
    assert entry["delay"] == 1.05 and entry["within"] is True  # <= 1.1 s (round 1's constant)
    assert entry["within_1s"] is False and entry["first_frame"] is False  # the strict 1.0 s
    assert entry["early"] is True and entry["pre_settle"] == [1, 1] and entry["seen_pos"] == 2
    assert near["before"] == "pos" and near["entry"] is False and near["pre_settle"] == [1, 1]


def test_entry_delays_first_frame_late_never_and_no_warp() -> None:
    frames = [_f(1.0, 1, "pos", True),
              _f(4.5, 2, "neg"), _f(6.0, 3, "pos"), _f(6.5, 4, "pos"), _f(7.0, 5, "pos"),
              _f(7.5, 6, "pos", True),
              _f(9.5, 7, "neg"), _f(11.0, 8, "pos"), _f(11.5, 9, "pos"),
              _f(14.5, 10, "neg"), _f(16.0, 11, "pos", True)]  # fmt: skip
    wins = [_win(0, 1, 5), _win(5, 6, 10), _win(10, 11, 14), _win(None, 16, None)]
    a, b, c, d = st.entries_of(wins, frames)
    assert a["before"] is None and a["entry"] is True  # nothing recorded before: not in view
    assert a["delay"] == 0.0 and a["first_frame"] is True and a["within_1s"] is True
    assert b["entry"] is True and b["delay"] == 1.5 and b["within"] is False
    assert c["entry"] is True and c["delay"] is None and c["within"] is False
    assert d["entry"] is False and d["pos"] == 1  # a hop without its own @warp is never scored


def test_stream_frames_count_the_skipped_unchanged_ticks() -> None:
    assert st.stream_frames([int(t * SEC) for t in (0, 1, 2, 5, 6.02)], 1.0) == [1, 1, 3, 1, 1]
    assert st.stream_frames([int(t * SEC) for t in (0, 0.5, 1.0, 2.5)], 2.0) == [1, 1, 3, 1]
    assert st.stream_frames([], 1.0) == []


def test_pool_hunting_rates_on_the_stream_and_on_stored_frames() -> None:
    p = st.pool_hunting([
        {"fps": 1.0, "neg_frames": 1200, "neg_ticks": 1800, "fp": 1, "fp_ticks": 3},
        {"fps": 1.0, "neg_frames": 600, "neg_ticks": 600, "fp": 0, "fp_ticks": 0},
    ])  # fmt: skip
    assert p["minutes"] == 40.0 and p["fp_ticks"] == 3 and p["fp_per_10min"] == 0.75
    assert p["stored_minutes"] == 30.0 and p["fp_stored"] == 1
    assert p["fp_per_10min_stored"] == round(1 / 30 * 10, 4)
    assert st.pool_hunting([])["fp_per_10min"] is None


def test_truth_map_is_a_parameter() -> None:
    row = {"map": "prt_fild08.gat"}
    assert st.on_map(row, "prt_fild08") is True and st.on_map(row) is False
    lord = {"job": 1190, "in_view": True}
    frames = [{"map": "prt_fild08.gat", "units": [lord], "t": 0, "frame_id": 0},
              {"map": "prt_fild08.gat", "units": []},
              {"map": "gef_fild10.gat", "units": [lord]}]  # fmt: skip
    doc = {"map": "prt_fild08", "frames": frames}
    s = st.summary(doc)
    assert s["on_map"] == 2 and s["lord_frames"] == 1 and s["party_frames"] == 1


# --- the real positive case (skips without the local data) -------------------------------------

WATCH = "20261025T195325-rdp-ow1"
WATCH_DIRS = (Path("/dev/shm/poring-lab-rec") / WATCH, Path("/mnt/poring-lab-datasets") / WATCH)
MODEL = Path(os.environ.get("MVP_WATCH_MODEL", str(mw.DEFAULT_MODEL)))


def test_real_orc_lord_frame_is_seen_near_its_packet_position() -> None:
    """Frame 20 of the watch (cell 0, 19:53 ICT): the Orc Lord and its 5 archers beside the
    immune Rogue; the packets put the Orc Lord's feet at (436, 399) and the archers' at
    x 511-596, y 348-421 (mvp_watch_study.py truth, 1d = 120 ms)."""
    session = next((d for d in WATCH_DIRS if (d / "manifest.json").exists()), None)
    if session is None or not MODEL.exists():
        pytest.skip("the watch recording or the model is not here (local data, never committed)")
    import map_labels as ml

    manifest = json.loads((session / "manifest.json").read_text())
    ref = next(r for r in ml.png_index(session, manifest) if r.frame_id == 20)
    v = mw.decide(ml.read_png(ref), mw.load(MODEL), ui_rects=mw.STANDARD_RECTS)
    assert v["seen"] is True
    x, y = v["where"]
    assert 380 <= x <= 650 and 330 <= y <= 460
