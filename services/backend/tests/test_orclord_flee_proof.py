"""orclord_flee_proof: the immunity reply bubble is read from its TEXT pixels only (the bubble is
translucent: the scene behind it must not decide), and an unreadable box is None, never a guess."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))

import orclord_flee_proof as fp  # noqa: E402


def _refs() -> tuple[np.ndarray, np.ndarray]:
    on = np.full((24, 197), 60.0, np.float32)
    off = np.full((24, 197), 60.0, np.float32)
    on[8:16, 10:180:3] = 240.0  # "You are now immune to attacks." -- a wide text
    off[8:16, 40:150:4] = 240.0  # "Returned to normal state." -- a narrower one
    return on, off


def test_each_bubble_reads_as_itself_over_any_scene() -> None:
    on, off = _refs()
    rng = np.random.default_rng(0)
    for ref, want in ((on, "on"), (off, "off")):
        frame = rng.uniform(0, 150, ref.shape).astype(np.float32)  # a scene through the bubble
        frame[ref >= fp.TEXT_LEVEL] = 235.0
        assert fp.bubble_state(frame, on, off) == want


def test_no_bubble_or_both_texts_is_none() -> None:
    on, off = _refs()
    dark = np.full(on.shape, 50.0, np.float32)
    assert fp.bubble_state(dark, on, off) is None
    white = np.full(on.shape, 250.0, np.float32)  # a bright scene lights both texts' pixels
    assert fp.bubble_state(white, on, off) is None
    assert fp.bubble_score(dark[:5], on) == 0.0  # a wrong-shaped box reads nothing


def _thin_refs() -> tuple[np.ndarray, np.ndarray]:
    """1-px strokes, as the client's bubble font draws them: a 1-px drift misses every stroke."""
    on = np.full((24, 197), 60.0, np.float32)
    off = np.full((24, 197), 60.0, np.float32)
    on[8:16:2, 10:180:3] = 240.0
    off[8:16:2, 40:150:4] = 240.0
    return on, off


def _drawn(ref: np.ndarray, x: int, y: int) -> np.ndarray:
    frame = np.full((100, 260), 70.0, np.float32)
    frame[y : y + 24, x : x + 197][ref >= fp.TEXT_LEVEL] = 235.0
    return frame


def test_a_bubble_drawn_one_px_off_its_reference_still_reads() -> None:
    """fp1 (2026-10-26 03:56-04:00): the live "off" bubble drew 1 px LOWER than its reference
    (0.50 at the box, 1.00 one row down); the read searches +-SHIFT_PX."""
    on, off = _thin_refs()
    box = (20, 30, 197, 24)
    for ref, want in ((on, "on"), (off, "off")):
        for dx, dy in ((0, 1), (1, -1), (-2, 2)):
            frame = _drawn(ref, box[0] + dx, box[1] + dy)
            assert fp.bubble_state(frame[30:54, 20:217], on, off) is None  # the fixed box misses
            assert fp.read_bubble(frame, box, on, off) == want


def test_the_shift_search_never_turns_no_bubble_into_a_state() -> None:
    on, off = _thin_refs()
    box = (20, 30, 197, 24)
    assert fp.read_bubble(np.full((100, 260), 50.0, np.float32), box, on, off) is None
    assert fp.read_bubble(np.full((100, 260), 250.0, np.float32), box, on, off) is None
    assert fp.read_bubble(_drawn(off, 20, 37), box, on, off) is None  # 7 px: beyond the search
