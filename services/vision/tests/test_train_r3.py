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


def test_the_duty_file_sets_the_sleep_and_an_untrusted_one_is_the_slowest(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """Batt 2026-10-07: the host's level, live; missing / stale / garbled -> 2 s (fail slow)."""
    import json

    from poring_vision.train import DUTY_FALLBACK_MS, read_duty

    f = tmp_path / "duty.json"
    now = time.time()
    assert read_duty(f, now) == DUTY_FALLBACK_MS  # missing
    f.write_text(json.dumps({"level": 1, "sleep_ms": 200, "t_epoch": now}))
    assert read_duty(f, now) == 200
    assert read_duty(f, now + 121) == DUTY_FALLBACK_MS  # stale: the host stopped writing
    f.write_text("{not json")
    assert read_duty(f, now) == DUTY_FALLBACK_MS
    f.write_text(json.dumps({"sleep_ms": -5, "t_epoch": now}))
    assert read_duty(f, now) == DUTY_FALLBACK_MS


def test_the_sleeper_accounts_batches_and_seconds_per_level(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    import io
    import json

    from poring_vision import train

    monkeypatch.setattr(train.time, "sleep", lambda s: None)
    f = tmp_path / "duty.json"
    out = io.StringIO()
    cb = train.step_sleeper(0, f, report_every=3, out=out)
    for ms in (100, 100, 400):
        f.write_text(json.dumps({"level": 0, "sleep_ms": ms, "t_epoch": time.time()}))
        cb(object())
    stats = json.loads(out.getvalue().strip().splitlines()[-1])["duty_stats"]
    assert stats["100ms"]["batches"] == 2 and stats["400ms"]["batches"] == 1
    assert stats["100ms"]["seconds"] >= 0.2 and stats["400ms"]["seconds"] >= 0.4
