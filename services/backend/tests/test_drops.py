"""No silent drops (ADR-0004 decision 4): reasons, counters, rate-limited warnings, no content."""

import logging

import pytest
from pydantic import ValidationError

from poring_backend.drops import DropCounter, ReplyThrottle, drop_reason, message_type
from poring_env.protocol import parse_browser_to_backend

SECRET = "SECRET-7f3a9c"


def reason_of(raw: str) -> str:
    with pytest.raises(ValidationError) as info:
        parse_browser_to_backend(raw)
    return drop_reason(info.value)


@pytest.mark.parametrize(
    ("raw", "reason"),
    [
        ('{"type":"key","frame_id":0,"code":"KeyA","action":"down"}', "missing:key.t_mono_ns"),
        ('{"type":"teleport","t_mono_ns":1}', "union_tag_invalid"),
        ("{not json", "json_invalid"),
        ('{"type":"wheel","t_mono_ns":1,"dy":50}', "less_than_equal:wheel.dy"),
    ],
)
def test_reason_names_the_error_type_and_field(raw: str, reason: str) -> None:
    assert reason_of(raw) == reason


def test_reason_never_contains_sender_chosen_text() -> None:
    # An unknown field NAME is chosen by the sender: it must not reach the log either.
    raw = f'{{"type":"ping","t_mono_ns":1,"{SECRET}":1}}'
    assert SECRET not in reason_of(raw)
    too_long = "x" * 70_000 + SECRET
    paste = f'{{"type":"clipboard_paste","t_mono_ns":1,"request_id":0,"text":"{too_long}"}}'
    assert SECRET not in reason_of(paste)


def test_message_type_is_only_reported_when_well_formed() -> None:
    assert message_type('{"type":"key"}') == "key"
    assert message_type('{"type":"Robert\'); DROP"}') is None
    assert message_type("[1,2]") is None
    assert message_type("{nope") is None
    assert message_type(b"\xff\xfe") is None


def test_counter_snapshot_groups_by_channel() -> None:
    drops = DropCounter()
    drops.record("ws_input", "json_invalid", None)
    drops.record("ws_input", "json_invalid", None)
    drops.record("agent", "missing:agent_input.events", "agent_input")
    assert drops.snapshot() == {
        "agent": {"missing:agent_input.events": 1},
        "ws_input": {"json_invalid": 2},
    }


def test_warning_is_rate_limited_per_reason(caplog: pytest.LogCaptureFixture) -> None:
    now = [0.0]
    drops = DropCounter(warn_interval_s=10.0, clock=lambda: now[0])
    with caplog.at_level(logging.WARNING, logger="poring_backend.drops"):
        for _ in range(50):
            drops.record("ws_input", "json_invalid", None)
        drops.record("ws_input", "missing:key.t_mono_ns", "key")  # another reason: own warning
        now[0] = 11.0
        drops.record("ws_input", "json_invalid", None)
    messages = [r.getMessage() for r in caplog.records]
    assert len(messages) == 3
    assert "json_invalid" in messages[0] and "key" in messages[1]
    assert "+49 more since the last warning" in messages[2]
    assert drops.snapshot()["ws_input"]["json_invalid"] == 51


def test_reply_throttle() -> None:
    now = [0.0]
    throttle = ReplyThrottle(min_interval_s=0.2, clock=lambda: now[0])
    assert throttle.allow()
    assert not throttle.allow()
    now[0] = 0.25
    assert throttle.allow()
