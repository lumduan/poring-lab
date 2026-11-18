"""signature.find (docs/planning/fullscreen-client.md section 7): a panel FOUND by its picture,
wherever the screen size or the player put it."""

import numpy as np

from poring_backend.signature import SIG_MATCH, find, grey_thumb


def test_a_signature_is_found_at_the_exact_pixel_wherever_it_is() -> None:
    rng = np.random.default_rng(5)
    # an interface panel is flat areas, not noise: blocks of one colour (8 px), as a dialog's
    # frame, title and buttons are; the coarse slide then sees it at any sub-step offset
    blocks = rng.integers(0, 255, (8, 36, 4), dtype=np.uint8)
    panel = np.ascontiguousarray(np.repeat(np.repeat(blocks, 8, 0), 8, 1)[:60, :281])
    ref = grey_thumb(panel)
    frame = rng.integers(0, 255, (1080, 1920, 4), dtype=np.uint8)
    frame[596 : 596 + 60, 825 : 825 + 281] = panel  # the 1080p service dialog's place
    d, x, y = find(frame, ref)
    assert (d, x, y) == (0.0, 825, 596)
    frame2 = rng.integers(0, 255, (720, 1280, 4), dtype=np.uint8)
    d2, _, _ = find(frame2, ref)
    assert d2 > SIG_MATCH  # nowhere: no match is invented


def test_a_picture_smaller_than_the_signature_is_no_match() -> None:
    ref = np.zeros((8, 36), np.float32)
    assert find(np.zeros((40, 100, 4), np.uint8), ref)[0] == float("inf")
