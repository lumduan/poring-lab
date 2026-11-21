"""The Run's status: SP, the weight as a % and the zeny (Batt 2026-11-21: "add SP, the weight as a
%, and the zeny: other jobs need them, a mage, a merchant whose skill strikes with money").

- scripts/zeny_read.py: the zeny, the last number on Basic Info's weight line, from pixels;
- flow_play.Purse / purse_reads: the zeny read on the runner's own weight frames, carried on the
  once-a-second hp_read record; the runner's weight events mirrored into the player's record;
- flow_run.Live: SP (from every HP read), the weight share, the zeny into the page's summary.
Display only: no decision reads any of them."""

from __future__ import annotations

import sys
import types
from pathlib import Path
from typing import Any

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))  # the sibling test's line drawer

import flow_play as fp  # noqa: E402
import flow_run as fr  # noqa: E402
import hp_percent as hp  # noqa: E402
import zeny_read as zr  # noqa: E402
from test_hp_percent import _thin_font, _weight_line  # noqa: E402

from poring_env import weight as wt  # noqa: E402


def font() -> dict[str, np.ndarray]:
    f = _thin_font()
    f["4"], f["2"] = f["5"][:, ::-1].copy(), f["0"].copy()
    f["2"][4, 2] = True  # distinct from the 0
    return f


def zeny_of(parts: list[tuple[int, str]]) -> zr.ZenyReading:
    return zr.read_font(_weight_line(font(), [(43, "Wx :"), (86, "1505 / 4200"), *parts]), font())


# --- the reader ----------------------------------------------------------------------------------


def test_the_zeny_reads_after_the_weight_with_its_commas() -> None:
    assert zeny_of([(150, "Zy : 15,100")]) == zr.ZenyReading(15100, "ok")
    assert zeny_of([(150, "Zy : 0")]) == zr.ZenyReading(0, "ok")
    assert zeny_of([(150, "Zy : 510")]).value == 510
    assert zeny_of([(150, "Zy : 1,005,510")]).value == 1005510
    assert zeny_of([(150, "Zy : 10510")]).value == 10510  # a client without separators


def test_a_label_letter_that_looks_like_a_digit_does_not_matter() -> None:
    """The lab font's 'Z' reads as '2' (2026-11-21, a real frame): the colon anchors the number."""
    assert zeny_of([(150, "5y : 15,100")]).value == 15100


def test_never_a_guess() -> None:
    assert zeny_of([(150, "Zy : 15,10")]).reason == "grouping"
    assert zeny_of([(150, "Zy : 1510,100")]).reason == "grouping"
    assert zeny_of([(150, "Zy : 15x00")]).reason == "no_space"  # a covered digit touches it
    assert zeny_of([(150, "Zy : 15,10x")]).reason == "unread_mark"  # the line ends in a mark
    assert zeny_of([(150, "Zy 15,100")]).reason == "no_colon"
    assert zeny_of([(150, "Zy : 0150")]).reason == "leading_zero"
    assert zeny_of([]).reason == "no_zeny"
    # the number touching the line's end: the window's border may cut a long zeny
    assert zeny_of([(186, "Zy : 15,100")]).reason == "cut_off"
    # no weight on the line: nothing places the zeny
    no_weight = _weight_line(font(), [(43, "Wx :"), (150, "Zy : 15,100")])
    assert zr.read_font(no_weight, font()).reason == "weight_unread"


def test_parse_rules_on_runs() -> None:
    def runs(*spec: tuple[int, int, str | None]) -> list[zr.Run]:
        return [zr.Run(a, b, k) for a, b, k in spec]

    label = [(10, 15, None), (16, 20, None), (24, 25, ":")]
    ok = runs(*label, (30, 35, "1"), (36, 37, ","), (38, 43, "0"), (44, 49, "0"), (50, 55, "5"))
    assert zr.parse(ok, 100) == zr.ZenyReading(1005, "ok")
    assert zr.parse(ok, 56).reason == "cut_off"
    touch = runs(*label[:2], (24, 25, ":"), (27, 32, "5"))  # 1 blank column after the colon
    assert zr.parse(touch, 100).reason == "no_space"
    assert zr.parse(runs((30, 35, "5")), 100).reason == "no_label"
    assert zr.parse(runs(*label, (30, 35, "5"), (36, 37, ",")), 100).reason == "grouping"


def test_stable_needs_every_frame_to_agree() -> None:
    a, b = zr.ZenyReading(5, "ok"), zr.ZenyReading(6, "ok")
    assert zr.stable([a, a]) == 5
    assert zr.stable([a, b]) is None
    assert zr.stable([a, zr.ZenyReading(None, "cut_off")]) is None
    assert zr.stable([]) is None


def test_the_lab_font_is_cut_from_the_weight_glyphs() -> None:
    """poring_env.weight's 7 px templates (mean ink probability) as run glyphs: each digit at
    INK_PROB, cut to its ink columns; a symbol never seen in calibration is left out."""
    rng = np.random.default_rng(7)
    mean = np.zeros((len(wt.SYMBOLS), 14, 7), np.float32)
    mean[:, 1:12, 0:6] = (rng.random((len(wt.SYMBOLS), 11, 6)) > 0.5) * 0.9  # ink in columns 0-5
    mean[:, 1, 0] = mean[:, 1, 5] = 0.9  # each glyph's ink spans all six
    counts = np.ones(len(wt.SYMBOLS), np.int64)
    counts[wt.SYMBOLS.index("7")] = 0
    g = types.SimpleNamespace(mean=mean, counts=counts)
    f = zr.lab_font(g)
    assert set(f) == set("012345689") and all(v.shape == (14, 6) for v in f.values())
    band = np.zeros((14, 80), bool)
    colon = np.zeros((14, 1), bool)
    colon[3] = colon[9] = True
    comma = np.zeros((14, 2), bool)
    comma[10:13, :] = True
    band[:, 10:11] = colon
    x = 16
    for ch in "1,005":
        gl = comma if ch == "," else f[ch]
        band[:, x : x + gl.shape[1]] = gl
        x += gl.shape[1] + 1
    got = zr.parse(zr.runs_of(band, 0, 80, f, zr.LAB_MAX_DIST), 80)
    assert got == zr.ZenyReading(1005, "ok")


def test_weight_span_gives_ms_end_and_read_weight_font_is_unchanged() -> None:
    img = _weight_line(font(), [(43, "Wx :"), (86, "1505 / 4200"), (150, "Zy : 15,100")])
    band = hp.ink(img, hp.WEIGHT_DY)
    span = hp.weight_span(band, font())
    assert span is not None and span[:2] == (1505, 4200)
    assert hp.read_weight_font(band, font()) == (1505, 4200)
    assert not band[:, span[2] : span[2] + 3].any() and band[:, span[2] - 1].any()


# --- the player -----------------------------------------------------------------------------------


def test_the_purse_keeps_the_last_read_and_never_raises() -> None:
    vals = iter([(1200, "ok"), (None, "cut_off")])
    p = fp.Purse(read=lambda frames: next(vals))
    p.read([1, 2])
    p.read([1, 2])
    assert p.last() == 1200 and p.why == "cut_off" and (p.reads, p.fails) == (2, 1)

    def boom(frames: Any) -> tuple[int | None, str]:
        raise RuntimeError("no")

    q = fp.Purse(read=boom)
    q.read([1])
    assert q.last() is None and q.why == "RuntimeError"


def test_purse_reads_follows_the_runners_weight_read_and_restores(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import gm_state

    seen: list[Any] = []

    def fake_weight(frames: Any) -> list[int]:
        return [10, 20]

    monkeypatch.setattr(gm_state, "_weight", fake_weight)
    p = fp.Purse(read=lambda frames: (seen.append(frames), (777, "ok"))[1])
    with fp.purse_reads(p):
        assert gm_state._weight(("a", "b")) == [10, 20]  # the runner's value, unchanged
    assert seen == [("a", "b")] and p.last() == 777
    assert gm_state._weight is fake_weight  # restored


def test_the_hook_carries_the_zeny_and_mirrors_the_weight() -> None:
    recs: list[dict[str, Any]] = []
    player = types.SimpleNamespace(rec=types.SimpleNamespace(ev=recs.append))
    p = fp.Purse(read=lambda frames: (5000, "ok"))
    hook = fp.HuntHook(player, fp.HuntResult(), purse=p)  # type: ignore[arg-type]
    hook.event({"kind": "hp_read", "pct": 90, "sp_pct": 40}, 1.0)
    assert "zeny" not in recs[-1]  # not read yet: no value
    p.read([0])
    hook.event({"kind": "hp_read", "pct": 90, "sp_pct": 40}, 2.5)
    assert recs[-1]["zeny"] == 5000 and recs[-1]["sp_pct"] == 40
    hook.event({"kind": "weight", "share": 0.4123, "red": False}, 2.6)
    assert recs[-1] == {"kind": "weight", "share": 0.4123, "red": False}
    assert "weight" in fp.MIRROR


# --- the helper's summary -------------------------------------------------------------------------


def test_the_helper_keeps_sp_the_weight_and_the_zeny() -> None:
    lv = fr.Live()
    s = 10**12
    assert {k: lv.summary()[k] for k in ("sp", "weight", "zeny", "zeny_start")} == {
        "sp": None, "weight": None, "zeny": None, "zeny_start": None}  # fmt: skip
    lv.feed({"kind": "hp_read", "t_ns": s, "pct": 100, "sp_pct": 80, "zeny": 33287})
    lv.feed({"kind": "hp_read", "t_ns": s + 1, "pct": 100, "sp_pct": 35, "quick": True})
    lv.feed({"kind": "hp_read", "t_ns": s + 2, "pct": 100, "sp_pct": 60, "zeny": 32100})
    lv.feed({"kind": "weight", "t_ns": s + 3, "share": 0.5123, "red": True})
    lv.feed({"kind": "weight", "t_ns": s + 4, "share": None, "red": True})  # unread: the last kept
    got = lv.summary()
    assert (got["sp"], got["sp_low"]) == (60, 35)
    assert (got["weight"], got["weight_red"]) == (51.2, True)
    assert (got["zeny"], got["zeny_start"]) == (32100, 33287)
    lv.feed({"kind": "hp_read", "t_ns": s + 5, "pct": 100, "sp_pct": True, "zeny": -5})
    assert lv.summary()["sp"] == 60 and lv.summary()["zeny"] == 32100  # never a bad value


def test_the_weight_reads_n_and_m_too() -> None:
    """Batt 2026-11-21: "weight 40 % -- show the real weight in brackets, (xxxx/xxxx)": the runner's
    own read [N, M] (the purse keeps it), on the hp_read record, into the summary."""
    import gm_state

    recs: list[dict[str, Any]] = []
    player = types.SimpleNamespace(rec=types.SimpleNamespace(ev=recs.append))
    p = fp.Purse(read=lambda frames: (None, "no_font"))
    saved = gm_state._weight
    gm_state._weight = lambda frames: [1680, 4200]  # type: ignore[assignment]
    try:
        with fp.purse_reads(p):
            gm_state._weight(("a", "b"))
    finally:
        gm_state._weight = saved  # type: ignore[assignment]
    assert p.last_weight() == (1680, 4200)
    p.keep_weight(None)  # an unread weight keeps the last
    p.keep_weight([5, 0])  # never a zero maximum
    assert p.last_weight() == (1680, 4200)
    hook = fp.HuntHook(player, fp.HuntResult(), purse=p)  # type: ignore[arg-type]
    hook.event({"kind": "hp_read", "pct": 90}, 1.0)
    assert recs[-1]["weight_nm"] == [1680, 4200] and "zeny" not in recs[-1]
    lv = fr.Live()
    lv.feed({"kind": "hp_read", "t_ns": 1, "pct": 90, "weight_nm": [1680, 4200]})
    lv.feed({"kind": "hp_read", "t_ns": 2, "pct": 90, "weight_nm": [3, 0]})  # never a bad value
    assert lv.summary()["weight_nm"] == [1680, 4200]


def test_the_share_comes_from_every_read_not_only_the_change_event() -> None:
    """Batt 2026-11-21 22:5x: the % showed "not read" for minutes -- the runner's weight event comes
    only on a >= 0.5 % change; the N / M of every read sets the share."""
    lv = fr.Live()
    lv.feed({"kind": "hp_read", "t_ns": 1, "pct": 90, "weight_nm": [1386, 4200]})
    got = lv.summary()
    assert got["weight"] == 33.0 and got["weight_nm"] == [1386, 4200] and got["weight_red"] is False
    lv.feed({"kind": "weight", "t_ns": 2, "share": 0.51, "red": True})  # the event: red too
    assert lv.summary()["weight"] == 51.0 and lv.summary()["weight_red"] is True
