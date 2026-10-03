"""ADR-0002 amendment (Batt, 2026-10-03): ASSIST -- and only ASSIST -- survives a GUARDED backend
restart. Every other boot stays HUMAN. The marker's parser is the whole gate, so it is strict."""

import pytest

from poring_backend.mode_restore import MAX_AGE_S, format_marker, judge
from poring_env.protocol import CaptureBackend

NOW = 1_790_000_000.0
LOCK = CaptureBackend(backend="rdp", seq=40, phase="steady")


def marker(**kw: str) -> str:
    values = {"MODE": "ASSIST", "SEQ": "40", "WRITTEN": str(int(NOW) - 10)}
    values["OWNER"] = "guarded_build"
    values.update(kw)
    return "".join(f"{k}={v}\n" for k, v in values.items())


def test_a_fresh_marker_for_the_same_lock_restores_assist() -> None:
    verdict = judge(marker(), LOCK, NOW)
    assert verdict.restore and "seq 40 unchanged" in verdict.why
    assert judge(format_marker(40, int(NOW) - 3), LOCK, NOW).restore  # the writer's own format


@pytest.mark.parametrize(
    ("text", "why"),
    [
        (None, "no marker"),
        (marker(MODE="BOT"), "never restored"),
        (marker(MODE="HUMAN"), "never restored"),
        (marker(OWNER="ro_agent"), "is not guarded_build"),
        (marker(WRITTEN=str(int(NOW) - MAX_AGE_S - 1)), "old"),
        (marker(WRITTEN=str(int(NOW) + 60)), "old"),  # from the future: not this restart's
        (marker(SEQ="41"), "a handover"),
        (marker(WRITTEN="soon"), "malformed"),
        (marker() + "MODE=ASSIST\n", "malformed"),  # a duplicate key
        (marker() + "EXTRA=1\n", "malformed"),
        ("MODE=ASSIST\nSEQ=40\n", "incomplete"),
        ("MODE=ASSIST $(reboot)\n", "malformed"),
        ("", "incomplete"),
    ],
)
def test_anything_else_boots_human(text: str | None, why: str) -> None:
    verdict = judge(text, LOCK, NOW)
    assert not verdict.restore and why in verdict.why


def test_a_hold_lock_never_restores() -> None:
    hold = CaptureBackend(backend="hold", reason="lock directory /lab-state is not mounted")
    assert "hold" in judge(marker(SEQ="0"), hold, NOW).why


def test_the_writer_has_no_way_to_write_another_mode() -> None:
    assert format_marker(7, 1).startswith("MODE=ASSIST\n")
    with pytest.raises(ValueError):
        format_marker(-1, 1)
