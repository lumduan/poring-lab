import pytest
from fastapi import FastAPI

from poring_backend.config import Settings
from poring_backend.main import build_config
from poring_backend.stream import Pacer

P = 1 / 30


def test_on_time_frames_sleep_until_the_next_slot() -> None:
    pacer = Pacer(P, now=0.0)
    # work took 10 ms each time -> sleep the rest of the slot
    assert pacer.delay(0.010) == pytest.approx(P - 0.010)
    assert pacer.delay(P + 0.010) == pytest.approx(P - 0.010)
    assert pacer.skipped == 0


def test_late_frame_starts_immediately_and_skips_missed_slots() -> None:
    pacer = Pacer(P, now=0.0)
    # the first slot is due at P; work ends 2.5 slots late -> 2 whole slots missed
    assert pacer.delay(P + 2.5 * P) == 0.0
    assert pacer.skipped == 2
    # back on the original grid: next due at 4P
    assert pacer.delay(3.6 * P) == pytest.approx(0.4 * P)


def test_slightly_late_frame_skips_nothing() -> None:
    pacer = Pacer(P, now=0.0)
    assert pacer.delay(P + 0.3 * P) == 0.0
    assert pacer.skipped == 0
    assert pacer.next_due == pytest.approx(2 * P)


def test_no_drift_over_many_frames() -> None:
    pacer = Pacer(P, now=0.0)
    now = 0.0
    for _ in range(1000):
        now += 0.012  # frame work
        now += pacer.delay(now)  # then sleep exactly as told
    # after 1000 frames we are exactly on the 1000th slot: no accumulated drift
    assert now == pytest.approx(1000 * P)
    assert pacer.skipped == 0


def test_period_must_be_positive() -> None:
    with pytest.raises(ValueError):
        Pacer(0.0, now=0.0)


def test_frontend_origins_parsing() -> None:
    s = Settings(frontend_origins=" http://192.168.1.13:3000/ , http://localhost:3000,,")
    assert s.origins == frozenset({"http://192.168.1.13:3000", "http://localhost:3000"})


def test_frontend_origins_default_is_the_lan_console() -> None:
    assert "http://192.168.1.13:3000" in Settings(_env_file=None).origins  # type: ignore[call-arg]


def test_frontend_origins_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FRONTEND_ORIGINS", "http://a.test:3000,http://b.test:3000")
    assert Settings().origins == frozenset({"http://a.test:3000", "http://b.test:3000"})


def test_server_config_disables_permessage_deflate() -> None:
    config = build_config(FastAPI())
    assert config.ws_per_message_deflate is False
