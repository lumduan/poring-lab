"""poring_vision.train's R3 duty-cycle knob (Batt, 2026-10-07): host-testable, no torch."""

from __future__ import annotations

import time

from poring_vision.train import step_sleeper


def test_the_step_sleeper_sleeps_after_each_batch_and_touches_nothing() -> None:
    class Trainer:
        epoch = 3

    t = Trainer()
    cb = step_sleeper(50)
    t0 = time.monotonic()
    cb(t)
    assert 0.045 <= time.monotonic() - t0 < 0.5
    assert t.epoch == 3
