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
