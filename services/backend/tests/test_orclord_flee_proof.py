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
