"""poring_dataset.deathcell (loot@1 P3): the death cell from synthetic detector boxes and a toy
picking model (40 x 30 px per cell, no camera)."""

from __future__ import annotations

import pytest

from poring_dataset.deathcell import (
    DROP_PATTERN,
    DeathCell,
    Sighting,
    death_cell,
    foot,
    scan_order,
)

MS = 1_000_000


def toy_cell_of(px: tuple[float, float], _frame: int) -> tuple[int, int] | None:
    """A flat toy picking model: 40 px per cell in x, 30 px in y (screen y down = map y down)."""
    x, y = px
    if not (0 <= x < 1280 and 0 <= y < 720):
        return None
    return int(x // 40), int(-(y // 30))


def box_at(cx: float, feet_y: float, score: float = 0.9, w: float = 30, h: float = 28) -> Sighting:
    return Sighting(0, (cx - w / 2, feet_y - h, cx + w / 2, feet_y), score)


def track(*frames: Sighting | None) -> list[Sighting]:
    """Time-stamped frames 100 ms apart; None = the detector did not see the target."""
    return [Sighting(i * 100 * MS, None) if f is None else Sighting(i * 100 * MS, f.box, f.score)
            for i, f in enumerate(frames)]  # fmt: skip


def test_the_last_foot_cell_before_the_target_vanished() -> None:
    frames = track(box_at(300, 400), box_at(305, 401), box_at(306, 401), box_at(306, 402),
                   None, None, None)  # fmt: skip
    d = death_cell(frames, toy_cell_of)
    assert d.reason == "ok" and d.cell == (7, -13)
    assert d.last_seen_ns == 300 * MS and d.gone_ns == 400 * MS
    assert d.confidence == pytest.approx(1.0)
    assert d.cells == ((7, -13), (7, -13), (7, -13))


def test_feet_are_the_box_bottom_centre() -> None:
    assert foot((10.0, 20.0, 30.0, 60.0)) == (20.0, 60.0)


def test_a_one_cell_disagreement_lowers_the_confidence_but_keeps_the_last_cell() -> None:
    frames = track(box_at(275, 400), box_at(281, 400), box_at(285, 400), None, None, None)
    d = death_cell(frames, toy_cell_of)
    assert d.reason == "ok" and d.cell == (7, -13)  # the last sighting's cell
    assert d.confidence == pytest.approx(2 / 3)


def test_a_target_still_moving_at_death_is_unstable() -> None:
    frames = track(box_at(200, 400), box_at(260, 400), box_at(320, 400), None, None, None)
    d = death_cell(frames, toy_cell_of)
    assert d.cell is None and d.reason == "unstable"


@pytest.mark.parametrize(
    ("frames", "reason"),
    [
        (track(None, None, None), "never_seen"),
        (track(box_at(300, 400), box_at(300, 400)), "still_visible"),
        (track(box_at(300, 400), None, None), "gap_too_short"),
        (track(box_at(2000, 400), box_at(2000, 400), None, None, None), "no_cell"),
    ],
)
def test_no_cell_without_a_clean_vanish(frames: list[Sighting], reason: str) -> None:
    d = death_cell(frames, toy_cell_of)
    assert d == DeathCell(None, 0.0, reason, d.last_seen_ns, d.gone_ns, d.cells)
    assert d.cell is None


def test_a_missed_frame_in_the_middle_is_not_the_vanish() -> None:
    frames = track(box_at(300, 400), None, box_at(300, 400), box_at(300, 400), None, None, None)
    d = death_cell(frames, toy_cell_of)
    assert d.reason == "ok" and d.last_seen_ns == 300 * MS


def test_a_weak_last_detection_lowers_the_confidence() -> None:
    frames = track(box_at(300, 400), box_at(300, 400), box_at(300, 400, score=0.25),
                   None, None, None)  # fmt: skip
    assert death_cell(frames, toy_cell_of).confidence == pytest.approx(0.5)


def test_out_of_order_frames_are_refused() -> None:
    frames = [Sighting(2, None), Sighting(1, None)]
    with pytest.raises(ValueError):
        death_cell(frames, toy_cell_of)


def test_the_scan_follows_the_servers_drop_pattern_first() -> None:
    order = scan_order((100, 50))
    assert order[:4] == [(100, 50), (101, 49), (99, 50), (100, 51)]  # centre, SE, W, N
    assert len(order) == 9 and len(set(order)) == 9
    assert set(order) == {(100 + dx, 50 + dy) for dx in (-1, 0, 1) for dy in (-1, 0, 1)}
    assert order[4:6] == [(101, 50), (100, 49)]  # the remaining edge neighbours, then corners
    assert DROP_PATTERN[0] == (0, 0)
    assert scan_order((5, 5), radius=0) == [(5, 5)]
