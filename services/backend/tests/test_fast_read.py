"""fast_read: the blink point (the pure part of the fast cursor read)."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))
import fast_read as fr  # noqa: E402


def everywhere(u: float, v: float) -> bool:
    return 0 <= u < 1280 and 0 <= v < 720


def test_the_blink_goes_90_px_right_when_nothing_is_there() -> None:
    assert fr.blink_point(600, 300, [], everywhere) == (690, 300)


def test_the_blink_keeps_clear_of_units_and_the_view_edge() -> None:
    # a unit on the right and the left edge too close: the next offset (down) wins
    assert fr.blink_point(60, 300, [(690 - 540, 300)], everywhere) == (60, 390)
    assert fr.blink_point(600, 300, [(690, 300)], everywhere) == (510, 300)


def test_no_blink_point_when_every_offset_is_blocked() -> None:
    assert fr.blink_point(600, 300, [], lambda u, v: False) is None
