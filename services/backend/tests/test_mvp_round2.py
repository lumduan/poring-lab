"""The Stormy Knight recognizer's ROUND 2 code (docs/planning/stormy-knight-recognizer.md 7 + 9), on
SYNTHETIC fixtures only (no recording, no truth of this study is read): the round-2 split (the whole
watch and every whole hunting session on one side), the model's aura mode (or / and / off: decide()
follows the MODEL), the DEV aura threshold, the memmap parts (rule 7's 1 GB per item), the
memory-lean training (bit-identical to the old code below LOGREG_WHOLE_MAX), and an end-to-end
synthetic fit -> dev -> score whose dev (half-res memmaps) and score (full frames) agree."""

from __future__ import annotations

import argparse
import json
import sys
import zipfile
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts"))

import mvp_profiles as mp  # noqa: E402
import mvp_watch as mw  # noqa: E402
import mvp_watch_study as st  # noqa: E402

S = 1_000_000_000


# --- the split ------------------------------------------------------------------------------------


def _wrow(fid: int, t_s: float, map_: str = "xmas_dun02.gat") -> dict[str, Any]:
    return {"frame_id": fid, "t": int(t_s * S), "map": map_, "units": [], "flags": []}


def test_watch_split_round_1_is_the_old_cells_and_round_2_the_whole_watch() -> None:
    spawns = [int((10 + 40 * c) * S) for c in range(16)]
    rows = {f: _wrow(f, f * 4.0) for f in range(170)}  # cells -1 .. 15, every 4 s
    rows[169] = _wrow(169, 676.0, "prontera.gat")  # off the map
    on = {f for f in rows if f != 169}
    old_dev = {f for f, r in rows.items() if st.on_map(r, "xmas_dun02")
               and st.cell_of(int(r["t"]), spawns) in mp.STORMY.dev_cells | {-1}}  # fmt: skip
    old_held = {f for f, r in rows.items() if st.on_map(r, "xmas_dun02")
                and st.cell_of(int(r["t"]), spawns) in mp.STORMY.held_cells}  # fmt: skip
    assert st.watch_split(rows, spawns, "xmas_dun02", mp.STORMY, 1, "dev") == old_dev
    assert st.watch_split(rows, spawns, "xmas_dun02", mp.STORMY, 1, "held") == old_held
    assert old_dev and old_held and not old_dev & old_held
    assert st.watch_split(rows, spawns, "xmas_dun02", mp.STORMY, 2, "dev") == on
    assert st.watch_split(rows, spawns, "xmas_dun02", mp.STORMY, 2, "held") == on
    with pytest.raises(ValueError):
        st.watch_split(rows, spawns, "xmas_dun02", mp.STORMY, 3, "dev")
    with pytest.raises(ValueError):
        st.watch_split(rows, spawns, "xmas_dun02", mp.STORMY, 2, "test")


def test_hunt_split_round_1_cuts_the_pilot_at_300_s_and_round_2_keeps_it_whole() -> None:
    rows = [_wrow(f, 100.0 + f * 10.0) for f in range(60)]  # 590 s on the map
    part = st.pilot_part(rows, map_name="xmas_dun02")
    dev = {f for f, v in part.items() if v == "dev"}
    assert dev == set(range(30)) and set(part) == set(range(60))
    assert st.hunt_split(rows, "xmas_dun02", True, 1, "dev") == dev
    assert st.hunt_split(rows, "xmas_dun02", True, 1, "held") == set(range(30, 60))
    assert st.hunt_split(rows, "xmas_dun02", False, 1, "dev") == set(range(60))  # --extra: whole
    for pilot in (True, False):
        for part_ in ("dev", "held"):
            assert st.hunt_split(rows, "xmas_dun02", pilot, 2, part_) == set(range(60))


def test_colour_cells_version_round_and_the_round_flag() -> None:
    assert st.colour_cells(mp.STORMY, 1, [1] * 16, [2] * 16) == list(range(8))
    assert st.colour_cells(mp.STORMY, 2, [1] * 16, [2] * 16) == list(range(16))
    assert st.colour_cells(mp.STORMY, 2, [1] * 16, [2] * 15) == list(range(15))
    assert st.colour_cells(mp.ORCLORD, 1, [1] * 15, [2] * 15) == list(range(8))
    assert [st.version_round(v) for v in ("orclord-v1", "stormy-v1", "stormy-v2")] == [1, 1, 2]
    for bad in ("stormy", "v2", "stormy-vx"):
        with pytest.raises(ValueError):
            st.version_round(bad)
    names1 = st.memmap_names(Path("D/w"), ["D/a", "D/b"], 1)
    assert names1 == ("watch-dev.npy", ["hunt-0.npy", "hunt-1.npy"])
    names2 = st.memmap_names(Path("D/w"), ["D/a", "D/b"], 2)
    assert names2 == ("watch-w.npy", ["hunt-a.npy", "hunt-b.npy"])
    ap = st.parser()
    base = ["--watch", "W", "--watch-truth", "WT", "--events", "E", "--pilot", "P", "PT",
            "--out", "O"]  # fmt: skip
    a = ap.parse_args(["fit", *base, "--work", "K"])
    assert (a.round, a.aura, a.aura_and, a.aura_margin) == (1, "or", 0.5, None)  # round 1's
    b = ap.parse_args(["score", *base, "--model", "M", "--sha256", "H"])
    c = ap.parse_args(["dev", *base, "--work", "K"])
    assert b.round == c.round == 1 and (c.model, c.sha256) == (None, None)
    d = ap.parse_args(["fit", *base, "--work", "K", "--boss", "stormy", "--round", "2",
                       "--aura", "off", "--aura-margin", "0.015"])  # fmt: skip
    assert (d.round, d.aura, d.aura_margin) == (2, "off", 0.015)
    with pytest.raises(SystemExit):
        ap.parse_args(["fit", *base, "--work", "K", "--round", "3"])
    with pytest.raises(SystemExit):
        ap.parse_args(["fit", *base, "--work", "K", "--aura", "xor"])


def test_aura_threshold_is_the_dev_max_plus_margin_rounded_up() -> None:
    assert st.aura_threshold(0.0417, 0.015) == 0.06  # round 1's (stormy 5b)
    assert st.aura_threshold(0.045, 0.015) == 0.06  # exactly on a step: not 0.07
    assert st.aura_threshold(0.4012, 0.015) == 0.42
    assert st.aura_threshold(0.0, 0.015) == 0.02


def test_the_orc_lord_keeps_the_or_mode_and_score_refuses_another_rounds_model(
    tmp_path: Path,
) -> None:
    ns = argparse.Namespace(boss="orclord", round=1, aura="off", aura_and=0.5, aura_margin=None,
                            aura_thr=None)  # fmt: skip
    with pytest.raises(SystemExit, match="v1 format: --aura or"):
        st.cmd_fit(ns)
    ns = argparse.Namespace(boss="stormy", round=2, aura="or", aura_and=0.5, aura_margin=0.015,
                            aura_thr=0.07)  # fmt: skip
    with pytest.raises(SystemExit, match="not with --aura-thr"):
        st.cmd_fit(ns)
    p = tmp_path / "stormy-v1.npz"
    sha = mw.save(p, _model(profile="stormy", version="stormy-v1", aura_rule=(248, 40)))
    sc = argparse.Namespace(boss="stormy", round=2, model=p, sha256=sha)
    with pytest.raises(SystemExit, match="a stormy-v1 model, not a round-2 one"):
        st.cmd_score(sc)


# --- the model's aura mode -----------------------------------------------------------------------

DARK = (40, 90, 10)  # BGR: a field whose red channel is low (the party weights read red)
RIM = (150, 250, 180)  # BGR: the Orc Lord's aura green (its rule takes it)
RED = (40, 60, 250)


def _title() -> np.ndarray:
    x0, y0, x1, y1 = (v // mw.STEP for v in mw.TITLE_BOX)
    g = np.zeros((y1 - y0, x1 - x0), np.float32)
    g[:, ::4] = 200.0
    return g


def _model(**kw: Any) -> mw.Model:
    w = np.zeros((mw.N_FEATURES, *mw.WIN), np.float32)
    w[2] = 1.0  # the window's mean red: ~34 for a red unit, ~1.4 on DARK
    base: dict[str, Any] = dict(body_lut=np.zeros(mw.NBINS, np.float32), lin_w=w, lin_b=0.0,
                                lin_thr=20.0, aura_thr=0.08, title=_title())  # fmt: skip
    base.update(kw)
    return mw.Model(**base)


def _full(model: mw.Model, ring: bool = False, unit: str | None = None) -> np.ndarray:
    """A 1280 x 720 frame: DARK, the title bar, an aura ring at (300, 450) and / or a red unit
    at x 900-980 (``big``: 112 px tall, a whole window; ``small``: 56 px, about half)."""
    f = np.zeros((720, 1280, 3), np.uint8)
    f[:, :] = DARK
    x0, y0, x1, y1 = mw.TITLE_BOX
    grey = np.repeat(np.repeat(model.title, 2, axis=0), 2, axis=1)
    f[y0:y1, x0:x1] = grey[: y1 - y0, : x1 - x0, None].astype(np.uint8)
    if ring:
        yy, xx = np.mgrid[0:720, 0:1280]
        r = ((xx - 300) / 54.0) ** 2 + ((yy - 434) / 30.0) ** 2
        f[(r <= 1.0) & (r >= 0.55)] = RIM
    if unit == "big":
        f[300:412, 900:980] = RED
    elif unit == "small":
        f[356:412, 900:980] = RED
    return f


def test_decide_follows_the_models_aura_mode() -> None:
    orm, off, andm = _model(), _model(aura_mode="off"), _model(aura_mode="and")
    assert mw.model_cues(orm) == ("aura", "party") and mw.model_cues(off) == ("party",)
    assert mw.and_threshold(andm) == 10.0 and mw.and_threshold(_model(aura_and=0.25)) == 5.0
    ring, small, big = _full(orm, ring=True), _full(orm, unit="small"), _full(orm, unit="big")
    both = _full(orm, ring=True, unit="small")
    v = mw.decide(small, orm)
    assert 10.0 <= v["party"] < 20.0 and v["seen"] is False  # the fixture's regime: between
    assert mw.decide(ring, orm)["aura"] >= 0.08 > mw.decide(small, orm)["aura"]
    seen = {name: [bool(mw.decide(f, m)["seen"]) for f in (ring, small, both, big)]
            for name, m in (("or", orm), ("off", off), ("and", andm))}  # fmt: skip
    assert seen == {"or": [True, False, True, True], "off": [False, False, False, True],
                    "and": [False, False, True, True]}  # fmt: skip
    v = mw.decide(both, andm)
    assert v["cue"] == "aura" and v["score"] >= 0  # the AND path won: the aura's margin
    assert mw.decide(ring, andm)["score"] < 0  # the aura alone: the party's AND margin < 0
    v = mw.decide(ring, off)
    assert v["cue"] == "party" and v["aura"] >= 0.08 and v["seen"] is False
    # an explicit ("aura",) still means the aura rule alone, whatever the mode
    assert mw.decide(ring, off, cues=("aura",))["seen"] is True
    assert mw.decide(ring, andm, cues=("aura",))["seen"] is True
    # the fit's seen_rule is decide()'s
    for name, m in (("or", orm), ("off", off), ("and", andm)):
        for f in (ring, small, both, big):
            v = mw.decide(f, m)
            assert st.seen_rule(v["party"], v["aura"], m.lin_thr, m.aura_thr, name,
                                m.aura_and) is v["seen"], name  # fmt: skip
    with pytest.raises(ValueError, match="aura_mode"):
        mw.decide(ring, _model(aura_mode="xor"))


def test_decide_on_the_half_res_view_is_decide_on_the_full_frame() -> None:
    rng = np.random.default_rng(3)
    for m in (_model(), _model(aura_mode="and")):
        f = _full(m, ring=True, unit="small")
        f[100:700:7, 300:1200:5] = rng.integers(0, 255, (86, 180, 3), dtype=np.uint8)
        assert mw.decide(f, m) == mw.decide_half(np.ascontiguousarray(f[::2, ::2]), m)


B1_MEMBERS = {"body_lut.npy", "lin_w.npy", "title.npy", "scalars.npy", "ring.npy", "version.npy",
              "profile.npy", "aura_rule.npy"}  # fmt: skip


def test_aura_mode_round_trip_and_the_older_formats_kept(tmp_path: Path) -> None:
    kw: dict[str, Any] = dict(profile="stormy", aura_rule=(248, 40), version="stormy-v2")
    p_or, p_off, p_and = (tmp_path / f"{n}.npz" for n in ("or", "off", "and"))
    sha_or = mw.save(p_or, _model(**kw))
    assert set(zipfile.ZipFile(p_or).namelist()) == B1_MEMBERS  # an "or" model: B1's bytes
    mw.save(p_off, _model(aura_mode="off", **kw))
    assert set(zipfile.ZipFile(p_off).namelist()) == B1_MEMBERS | {"aura_mode.npy"}
    mw.save(p_and, _model(aura_mode="and", aura_and=0.25, **kw))
    assert set(zipfile.ZipFile(p_and).namelist()) == B1_MEMBERS | {"aura_mode.npy",
                                                                   "aura_and.npy"}  # fmt: skip
    assert mw.load(p_or, sha_or).aura_mode == "or"
    assert mw.load(p_off).aura_mode == "off"
    back = mw.load(p_and, profile="stormy")
    assert (back.aura_mode, back.aura_and, back.version) == ("and", 0.25, "stormy-v2")
    with pytest.raises(ValueError, match="v1 format: aura_mode"):
        mw.save(tmp_path / "o.npz", _model(aura_mode="off"))  # the Orc Lord's: v1 only
    with pytest.raises(ValueError, match="aura_mode"):
        mw.save(tmp_path / "x.npz", _model(aura_mode="xor", **kw))
    z = dict(np.load(p_off))
    z["aura_mode"] = np.array("xor")
    bad = tmp_path / "bad.npz"
    with bad.open("wb") as fh:
        np.savez(fh, **z)
    with pytest.raises(mw.ModelUnavailable, match="aura_mode 'xor'"):
        mw.load(bad)


# --- the memmap parts -----------------------------------------------------------------------------


def test_half_frames_in_parts_and_reused(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import map_labels

    session = tmp_path / "sess"
    session.mkdir()
    (session / "manifest.json").write_text("{}")
    refs = [SimpleNamespace(frame_id=f, t_mono_ns=f * S) for f in range(12)]
    reads: list[int] = []

    def read_png(r: Any) -> np.ndarray:
        reads.append(r.frame_id)
        return np.full((720, 1280, 3), r.frame_id * 10, np.uint8)

    monkeypatch.setattr(st, "png_index", lambda s, m: refs)
    monkeypatch.setattr(map_labels, "read_png", read_png)
    keep = set(range(10))
    out = tmp_path / "work" / "hunt-sess.npy"
    out.parent.mkdir()
    arr, ids = st.half_frames(session, keep, out, part_frames=4)
    assert ids == list(range(10)) and len(arr) == 10 and isinstance(arr, st.Frames)
    assert [len(p) for p in arr.parts] == [4, 4, 2]
    names = ["hunt-sess.npy.ids.json", "hunt-sess.p0.npy", "hunt-sess.p1.npy", "hunt-sess.p2.npy"]
    assert sorted(q.name for q in out.parent.iterdir()) == names
    assert [int(arr[i][0, 0, 0]) for i in range(10)] == [f * 10 for f in range(10)]
    assert [int(x[1, 1, 1]) for x in arr] == [f * 10 for f in range(10)]
    assert int(arr[-1][0, 0, 0]) == 90 and arr[5].shape == (360, 640, 3)
    with pytest.raises(IndexError):
        arr[10]
    n = len(reads)
    again, _ = st.half_frames(session, keep, out, part_frames=4)
    assert len(reads) == n and len(again) == 10  # reused, nothing decoded
    st.half_frames(session, keep | {10}, out, part_frames=4)
    assert len(reads) == n + 11  # another frame set: decoded again
    one, ids1 = st.half_frames(session, keep, tmp_path / "work" / "one.npy")  # round 1's
    assert isinstance(one, np.memmap) and one.shape == (10, 360, 640, 3) and ids1 == ids


# --- the training: bit-identical below LOGREG_WHOLE_MAX, lean above -------------------------------


def _old_logreg(x: np.ndarray, y: np.ndarray, wts: np.ndarray, l2: float = 1.0,
                iters: int = 12) -> tuple[np.ndarray, float]:  # fmt: skip
    """mvp_watch_study.logreg before round 2, verbatim."""
    mu, sd = x.mean(0), x.std(0) + 1e-3
    z = np.hstack([(x - mu) / sd, np.ones((len(x), 1), np.float32)]).astype(np.float64)
    w = np.zeros(z.shape[1])
    reg = l2 * np.r_[np.ones(len(w) - 1), 0.0]
    for _ in range(iters):
        p = 1.0 / (1.0 + np.exp(-np.clip(z @ w, -30, 30)))
        g = z.T @ (wts * (p - y)) + reg * w
        hess = (z * (wts * p * (1 - p))[:, None]).T @ z + np.diag(reg)
        w -= np.linalg.solve(hess, g)
    wf = (w[:-1] / sd).astype(np.float32)
    return wf, float(w[-1] - (w[:-1] * mu / sd).sum())


def _xy(n: int, d: int = 12, seed: int = 0) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    rng = np.random.default_rng(seed)
    x = rng.normal(size=(n, d)).astype(np.float32)
    x[:, 3] *= 40.0
    y = (x[:, 0] + 0.02 * x[:, 3] + rng.normal(size=n) > 0.5).astype(np.float64)
    wts = np.where(y > 0, 3.0, 1.0)
    return x, y, wts


def test_logreg_whole_is_the_old_code_and_blocks_agree(monkeypatch: pytest.MonkeyPatch) -> None:
    x, y, wts = _xy(3000)
    w, b = st.logreg(x, y, wts)
    w0, b0 = _old_logreg(x, y, wts)
    assert np.array_equal(w, w0) and b == b0  # bit for bit
    wb, bb = st.logreg(x, y, wts, chunk=257)
    assert np.allclose(wb, w0, rtol=1e-6, atol=1e-7) and abs(bb - b0) < 1e-6
    calls: list[int] = []
    real = st._logreg_blocks
    monkeypatch.setattr(st, "_logreg_blocks", lambda *a: calls.append(a[-1]) or real(*a))
    monkeypatch.setattr(st, "LOGREG_WHOLE_MAX", 2000)
    monkeypatch.setattr(st, "LOGREG_CHUNK", 700)
    st.logreg(x, y, wts)
    assert calls == [700]  # above the size: blocks
    st.logreg(x[:2000], y[:2000], wts[:2000])
    assert calls == [700]  # at it: whole


def _old_train_party(items: Any, rounds: int = 2, seed: int = 0,
                     l2: float = 1.0) -> tuple[np.ndarray, float]:  # fmt: skip
    """mvp_watch_study.train_party before round 2 (with B1's copies), verbatim."""
    rng = np.random.default_rng(seed)
    xp, xn = [], []
    for it in items:
        wv = mw.window_vectors(it.feats)
        oh, ow = wv.shape[:2]
        near = np.zeros((oh, ow), bool)
        for cy, cx in it.party:
            near[max(0, cy - 2) : cy + 3, max(0, cx - 2) : cx + 3] = True
            for dy, dx in ((0, 0), (1, 0), (-1, 0), (0, 1), (0, -1)):
                if 0 <= cy + dy < oh and 0 <= cx + dx < ow:
                    xp.append(wv[cy + dy, cx + dx].copy())
        if it.kind == "edge":
            continue
        cand = np.argwhere(it.valid & ~near)
        if len(cand):
            n = 60 if it.kind == "pos" else 150
            pick = cand[rng.choice(len(cand), min(len(cand), n), replace=False)]
            xn.extend(wv[pick[:, 0], pick[:, 1]])
    pos, neg = np.array(xp, np.float32), np.array(xn, np.float32)
    w, b = np.zeros(1, np.float32), 0.0
    for r in range(rounds + 1):
        x = np.vstack([pos, neg])
        y = np.r_[np.ones(len(pos)), np.zeros(len(neg))]
        wts = np.r_[np.full(len(pos), len(neg) / len(pos) * 0.5), np.ones(len(neg))]
        w, b = _old_logreg(x, y, wts, l2)
        if r == rounds:
            break
        hard = []
        for it in items:
            if it.kind not in ("neg", "hunt"):
                continue
            sm = mw.window_scores(it.feats, w.reshape(mw.N_FEATURES, *mw.WIN), b)
            sm[~it.valid] = -np.inf
            wv = mw.window_vectors(it.feats)
            for j in np.argsort(sm, axis=None)[-20:]:
                yy, xx = divmod(int(j), sm.shape[1])
                if sm[yy, xx] > -2:
                    hard.append(wv[yy, xx].copy())
        if hard:
            neg = np.vstack([neg, np.array(hard, np.float32)])
    return w.reshape(mw.N_FEATURES, *mw.WIN), b


def test_train_party_is_bit_identical_to_the_old_code() -> None:
    rng = np.random.default_rng(7)
    items = []
    for i, kind in enumerate(("pos", "pos", "neg", "hunt", "hunt", "edge", "pos", "hunt")):
        feats = rng.normal(size=(mw.N_FEATURES, 45, 80)).astype(np.float32)
        party = [(10 + i, 20 + 3 * i), (30, 60)] if kind in ("pos", "edge") else []
        for cy, cx in party:  # the party's windows stand out
            feats[:, cy : cy + mw.WIN[0], cx : cx + mw.WIN[1]] += 1.5
        valid = np.ones((45 - mw.WIN[0] + 1, 80 - mw.WIN[1] + 1), bool)
        valid[:3] = False
        items.append(st.Item(feats, valid, kind, party, 0.0, np.zeros_like(valid)))
    stats: dict[str, Any] = {}
    w, b = st.train_party(items, stats=stats)
    w0, b0 = _old_train_party(items)
    assert np.array_equal(w, w0) and b == b0
    assert stats["pos"] == 4 * 2 * 5 and stats["neg"] == 3 * 60 + 4 * 150
    assert len(stats["hard"]) == 2


# --- end to end: a synthetic round-2 fit, dev and score -------------------------------------------

UNIT_BOX = (800.0, 300.0, 880.0, 412.0)  # the Knight's predicted box (full px) while it is out
WARPS = (0.5, 13.5)  # each cell's @warp (s)
CELLS = ((6.0, 12.0), (19.0, 25.0))  # (spawn, @killmonster2) per cell


def _half(title: np.ndarray, unit: bool = False, shade: int = 0) -> np.ndarray:
    f = np.zeros((360, 640, 3), np.uint8)
    f[:, :] = (40 + shade, 90, 10 + shade)
    x0, y0, x1, y1 = (v // mw.STEP for v in mw.TITLE_BOX)
    f[y0:y1, x0:x1] = title[:, :, None].astype(np.uint8)
    if unit:
        a, b, c, d = (int(v / 2) for v in UNIT_BOX)
        f[b:d, a:c] = RED
    return f


def _synthetic(tmp_path: Path) -> dict[str, Any]:
    """A two-cell watch (1 fps, 31 s) and two hunting sessions of 41 frames each 10 s apart
    (400 s: the pilot runs past round 1's 300-s cut), their truths and the watch's events."""
    title = _title()
    wrows, wframes = [], {}
    for f in range(31):
        t = float(f)
        out = any(s <= t < k for s, k in CELLS)
        units = [{"gid": 9, "job": 1251, "box": UNIT_BOX, "state": "idle", "cell": (1.0, 1.0),
                  "in_view": True}] if out else []  # fmt: skip
        wrows.append({"frame_id": f, "t": int(t * S), "map": "xmas_dun02.gat", "units": units,
                      "flags": [], "self": [1, 1], "camera": [1, 1], "players": 0})  # fmt: skip
        wframes[f] = _half(title, unit=out)
    hunts = {}
    for name in ("hA", "hB"):
        rows, frames = [], {}
        for f in range(41):
            rows.append({"frame_id": f, "t": int((50 + 10 * f) * S), "map": "xmas_dun02.gat",
                         "units": [], "flags": [], "self": [1, 1], "camera": [1, 1],
                         "players": 0})  # fmt: skip
            frames[f] = _half(title, shade=(f % 5) * 3 + (7 if name == "hB" else 0))
        hunts[name] = (rows, frames)
    chat = {"rect": [0, 585, 600, 720], "how": "test", "nested_dropped": []}

    def write(name: str, rows: list[dict[str, Any]]) -> Path:
        p = tmp_path / f"{name}-truth.json"
        p.write_text(json.dumps({"boss": "stormy", "layout": "hunt", "map": "xmas_dun02",
                                 "frames": rows, "chat": chat}))  # fmt: skip
        return p

    events = tmp_path / "events.jsonl"
    ev = []
    for s, k in CELLS:
        ev += [{"kind": "spawn", "t_ns": int(s * S), "mob": 1251},
               {"kind": "killmonster2", "t_ns": int(k * S)}]  # fmt: skip
    events.write_text("".join(json.dumps(e) + "\n" for e in ev))
    return {"watch": (tmp_path / "W", write("watch", wrows), wframes), "events": events,
            **{n: (tmp_path / n, write(n, r), fr) for n, (r, fr) in hunts.items()}}  # fmt: skip


def _patch(monkeypatch: pytest.MonkeyPatch, syn: dict[str, Any]) -> list[tuple[str, set[int]]]:
    """half_frames from the synthetic frames (recording each call), the watch's @warps, and
    score's full frames (the half view upsampled: decide() takes back exactly the half view)."""
    by_session = {str(v[0]): v[2] for k, v in syn.items() if k != "events"}
    times = {str(v[0]): {int(r["frame_id"]): int(r["t"])
                         for r in json.loads(v[1].read_text())["frames"]}
             for k, v in syn.items() if k != "events"}  # fmt: skip
    calls: list[tuple[str, set[int]]] = []

    def half_frames(session: Path, keep: set[int], out: Path,
                    part_frames: int | None = None) -> tuple[Any, list[int]]:  # fmt: skip
        calls.append((out.name, set(keep)))
        ids = sorted(keep)
        return [by_session[str(session)][f] for f in ids], ids

    def full_frames(session: Path, keep: set[int]) -> Any:
        for f in sorted(keep):
            h = by_session[str(session)][f]
            yield f, times[str(session)][f], np.repeat(np.repeat(h, 2, axis=0), 2, axis=1)

    monkeypatch.setattr(st, "half_frames", half_frames)
    monkeypatch.setattr(st, "_changes", lambda s: [int(w * S) for w in WARPS])
    monkeypatch.setattr(st, "_full_frames", full_frames)
    return calls


def _ns(syn: dict[str, Any], tmp_path: Path, **kw: Any) -> argparse.Namespace:
    w, wt, _ = syn["watch"]
    a, at, _ = syn["hA"]
    base: dict[str, Any] = dict(boss="stormy", round=2, watch=w, watch_truth=wt,
                                events=syn["events"], pilot=(str(a), str(at)), extra=None,
                                work=tmp_path / "work", out=tmp_path / "m.npz", aura="or",
                                aura_and=0.5, aura_margin=None, aura_thr=None, ring=None,
                                ring_cell=None, ring_dy=None, aura_rule=None, model=None,
                                sha256=None, supplement=None)  # fmt: skip
    base.update(kw)
    return argparse.Namespace(**base)


def test_a_synthetic_round_2_fit_dev_and_score(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    syn = _synthetic(tmp_path)
    calls = _patch(monkeypatch, syn)
    b, bt, _ = syn["hB"]
    out = tmp_path / "model" / "stormy-v2.npz"
    rep = st.cmd_fit(_ns(syn, tmp_path, aura="off", aura_margin=0.015, out=out,
                         extra=[(str(b), str(bt))]))  # fmt: skip
    # round 2 took the WHOLE watch and both WHOLE hunting sessions (the pilot past 300 s too)
    assert calls == [("watch-W.npy", set(range(31))), ("hunt-hA.npy", set(range(41))),
                     ("hunt-hB.npy", set(range(41)))]  # fmt: skip
    assert rep["dev_items"] == {"pos": 12, "neg": 19, "hunt": 82}
    assert (rep["round"], rep["version"], rep["aura_mode"]) == (2, "stormy-v2", "off")
    assert rep["dev_frames"] == {"watch": 31, "hA": 41, "hB": 41}
    assert rep["aura_thr"] == st.aura_threshold(rep["dev_neg_max_aura"], 0.015)
    assert rep["train_rows"]["pos"] > 0 and len(rep["train_rows"]["hard"]) == 2
    m = mw.load(out, rep["sha256"], profile="stormy")
    assert (m.version, m.aura_mode, m.aura_thr) == ("stormy-v2", "off", rep["aura_thr"])
    assert "aura_mode.npy" in zipfile.ZipFile(out).namelist()
    # dev: the same frames, decided from the half-res arrays (in-sample here)
    calls.clear()
    dev = st.cmd_dev(_ns(syn, tmp_path, model=out, sha256=rep["sha256"],
                         extra=[(str(b), str(bt))]))  # fmt: skip
    assert [c[0] for c in calls] == ["watch-W.npy", "hunt-hA.npy", "hunt-hB.npy"]
    assert (dev["split"], dev["round"], dev["aura_mode"]) == ("dev", 2, "off")
    assert dev["cells_n"] == 2 and dev["cells_within"] == 2 and dev["first_frame"] == 2
    assert [h["session"] for h in dev["hunting"]] == ["hA", "hB"]
    assert all(h["fp"] == 0 and h["frames"] == 41 for h in dev["hunting"])
    assert dev["hunting"][0]["lone"]["frames"] == 0  # stormy's lone report, none here
    assert dev["watch_gap"]["n"] == 19 and dev["watch_gap"]["fp"] == 0
    assert dev["pos_frames"] == {"n": 12, "seen": 12, "lord_n": 12, "lord_seen": 12}
    # score --round 2 (synthetic: the whole watch and the whole pilot are its held-out side)
    sc = st.cmd_score(_ns(syn, tmp_path, model=out, sha256=rep["sha256"]))
    assert (sc["round"], sc["held_cells"], sc["aura_mode"]) == (2, "all", "off")
    assert sc["cells_n"] == 2 and sc["cells_within"] == 2
    assert sc["hunting"][0]["frames"] == 41 and sc["hunting"][0]["fp"] == 0
    # dev on the half view and score on the full frames decide alike
    assert sc["pos_frames"] == dev["pos_frames"] and sc["cells"] == dev["cells"]
    assert sc["watch_gap"]["n"] == dev["watch_gap"]["n"]
    with pytest.raises(SystemExit, match="not a round-1 one"):
        st.cmd_score(_ns(syn, tmp_path, round=1, model=out, sha256=rep["sha256"]))
    # decode only: no model, the counts
    assert st.cmd_dev(_ns(syn, tmp_path))["decoded"] == {"watch": 31, "hA": [41, 0]}


def test_round_1_fit_keeps_its_split_names_and_version(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import dataclasses

    syn = _synthetic(tmp_path)
    calls = _patch(monkeypatch, syn)
    # two cells here: cell 0 DEV (and the frames before it), cell 1 HELD-OUT, as 0-7 / 8-15
    two = dataclasses.replace(mp.STORMY, dev_cells=frozenset({0}), held_cells=frozenset({1}))
    monkeypatch.setitem(mp.PROFILES, "stormy", two)
    rep = st.cmd_fit(_ns(syn, tmp_path, round=1))
    # round 1: cell 0 and before (t < 19 s), the pilot's first 300 s (50 .. 340 s), the old names
    assert calls == [("watch-dev.npy", set(range(19))), ("hunt-0.npy", set(range(30)))]
    assert rep["dev_items"] == {"neg": 13, "pos": 6, "hunt": 30}
    assert (rep["round"], rep["version"], rep["aura_mode"]) == (1, "stormy-v1", "or")
    assert rep["aura_thr"] == mp.STORMY.aura_thr  # the profile's frozen 0.06
    m = mw.load(tmp_path / "m.npz", rep["sha256"])
    assert (m.version, m.aura_mode) == ("stormy-v1", "or")
    assert set(zipfile.ZipFile(tmp_path / "m.npz").namelist()) == B1_MEMBERS
