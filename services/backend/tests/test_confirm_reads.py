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


def test_an_empty_slot_reads_zero_only_twice_seen(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(hb.CONFIRM_READS_ENV, "1")
    hb._ZEROS.clear()
    clock = iter([100.0, 101.0, 200.0, 200.2, 201.0])
    monkeypatch.setattr(hb.time, "monotonic", lambda: next(clock))
    f = _empty_slot_frame()
    assert hb.read_count(f, 7, {}) is None  # the first empty read: unreadable this time
    assert hb.read_count(f, 7, {}) == 0  # 1 s later, still empty: 0
    assert hb.read_count(f, 7, {}) is None  # a new episode
    assert hb.read_count(f, 7, {}) is None  # 0.2 s later: too soon to count
    assert hb.read_count(f, 7, {}) == 0


def test_without_the_env_an_empty_slot_is_zero_at_once(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(hb.CONFIRM_READS_ENV, raising=False)
    hb._ZEROS.clear()
    assert hb.read_count(_empty_slot_frame(), 7, {}) == 0
