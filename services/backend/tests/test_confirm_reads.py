"""A player's Run re-reads before a read that would END it (Batt 2026-11-20: "retry the read: it
may read wrong"): a lone minimap jump comes back doubtful, an empty hotbar slot needs a second
read. The byte-pinned runner is unchanged: the readers do it, only while the Run helper's env flag
is on."""

import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts"))

import flow_run as fr  # noqa: E402
import hotbar_count as hb  # noqa: E402

from poring_env import selfpos  # noqa: E402


def reading(x: int, y: int, mode: str = "base") -> selfpos.Reading:
    return selfpos.Reading((x, y), "ok", mode=mode)


def test_one_env_name_everywhere() -> None:
    assert fr.RUN_CONFIRM_ENV == selfpos.CONFIRM_READS_ENV == hb.CONFIRM_READS_ENV


def test_a_lone_jump_is_doubtful_and_a_real_one_is_believed_on_its_second_read(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(selfpos.CONFIRM_READS_ENV, "1")
    g = selfpos.JumpGuard()
    assert selfpos.guarded(reading(115, 217), 0.0, g).mode == "base"
    assert selfpos.guarded(reading(116, 21), 0.4, g).mode == "light"  # the live PC's misread
    assert selfpos.guarded(reading(115, 217), 0.8, g).mode == "base"  # back: believed at once
    assert selfpos.guarded(reading(30, 40), 1.2, g).mode == "light"  # a real map change ...
    assert selfpos.guarded(reading(30, 40), 1.5, g).mode == "base"  # ... believed one read later
    t, x = 2.0, 30
    for _ in range(15):  # a walk is never doubtful
        assert selfpos.guarded(reading(x, 40), t, g).mode == "base"
        t, x = t + 0.3, x + 1


def test_without_the_env_nothing_changes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(selfpos.CONFIRM_READS_ENV, raising=False)
    g = selfpos.JumpGuard()
    assert selfpos.guarded(reading(115, 217), 0.0, g).mode == "base"
    assert selfpos.guarded(reading(116, 21), 0.4, g).mode == "base"
    lit = reading(5, 5, mode="light")
    assert selfpos.guarded(lit, 0.5, g) is lit


def _empty_slot_frame() -> np.ndarray:
    return np.full((720, 1280), 255.0)  # white: no digit, no icon in any slot


def test_in_a_players_run_an_empty_slot_never_reads_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    """Batt 2026-11-20: a 0 is the player's own to prepare; only a death ends the run."""
    monkeypatch.setenv(hb.CONFIRM_READS_ENV, "1")
    f = _empty_slot_frame()
    assert hb.read_count(f, 7, {}) is None
    assert hb.read_count(f, 7, {}) is None  # again and again: never 0


def test_without_the_env_an_empty_slot_is_zero_at_once(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(hb.CONFIRM_READS_ENV, raising=False)
    assert hb.read_count(_empty_slot_frame(), 7, {}) == 0


def _left_frame(slot: int, text: str, templates: dict[str, np.ndarray]) -> np.ndarray:
    """The live client's layout: the mark, then the count left-aligned (hotbar_count.MARK/LEFT)."""
    f = np.full((720, 1280), 230.0)
    mx0, my0, mx1, my1 = hb.MARK
    f[my0:my1, mx0 + hb.PITCH * slot : mx1 + hb.PITCH * slot] = 0.0
    x = hb.LEFT[0] + hb.PITCH * slot
    for ch in text:
        g = templates[ch]
        f[hb.LEFT[1] : hb.LEFT[1] + g.shape[0], x : x + g.shape[1]][g] = 0.0
        x += g.shape[1] + 1
    return f


def test_the_left_aligned_count_after_the_mark_reads() -> None:
    """2026-11-20: the live client draws a mark, then the count left-aligned (588, 60, 111, 528)."""
    rng = np.random.default_rng(3)
    t = {str(d): rng.random((9, 6)) > 0.45 for d in range(10)}
    for g in t.values():
        g[0, :] = True  # every digit spans the box's height (top and bottom rows)
        g[-1, :] = True
    t["1"] = t["1"][:, :5]
    for slot, text in ((0, "588"), (6, "60"), (8, "111"), (7, "528"), (2, "1")):
        f = _left_frame(slot, text, t)
        assert hb.left_layout(f, slot)
        assert hb.read_count(f, slot, t) == int(text)
    plain = np.full((720, 1280), 230.0)
    assert not hb.left_layout(plain, 0)  # no mark: the lab's layout, as before
