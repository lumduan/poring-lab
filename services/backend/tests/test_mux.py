from typing import Literal

import pytest

from poring_backend.mux import Decision, InputMux, Source
from poring_env.protocol import InputEvent, Key, Mode, MouseButton, MouseMove, ReleaseAll, Wheel

S = 1_000_000_000  # 1 s in ns
LEASE = 3 * S
HUMAN, BOT = Source.HUMAN, Source.BOT


def new_mux(mode: Mode = Mode.HUMAN) -> InputMux:
    return InputMux(lease_ns=LEASE, mode=mode)


def key(code: str, action: Literal["down", "up"] = "down") -> Key:
    return Key(t_mono_ns=0, frame_id=1, code=code, action=action)


def button(name: Literal["left", "middle", "right"], action: Literal["down", "up"]) -> MouseButton:
    return MouseButton(t_mono_ns=0, frame_id=1, button=name, action=action, x=0.5, y=0.5)


def move() -> MouseMove:
    return MouseMove(t_mono_ns=0, frame_id=1, x=0.5, y=0.5)


def summary(decision: Decision) -> list[tuple[str, str, str, bool, str]]:
    """(source, what, action, synthetic, reason) per injected event."""
    out = []
    for r in decision.inject:
        event: InputEvent = r.event
        what = event.code if isinstance(event, Key) else getattr(event, "button", event.type)
        action = getattr(event, "action", "")
        out.append((r.source.value, what, action, r.synthetic, r.reason))
    return out


def test_boots_in_human_mode() -> None:
    assert InputMux(lease_ns=LEASE).mode is Mode.HUMAN


def test_human_mode_passes_human_and_drops_bot() -> None:
    mux = new_mux(Mode.HUMAN)
    assert mux.submit(HUMAN, move(), 0).accepted
    dropped = mux.submit(BOT, move(), 0)
    assert (dropped.accepted, dropped.reason, dropped.inject) == (False, "mode=HUMAN", ())


def test_bot_mode_passes_bot_and_drops_human() -> None:
    mux = new_mux(Mode.BOT)
    assert mux.submit(BOT, key("KeyA"), 0).accepted
    dropped = mux.submit(HUMAN, move(), 0)
    assert (dropped.accepted, dropped.reason) == (False, "mode=BOT")


def test_assist_bot_passes_while_no_lease() -> None:
    mux = new_mux(Mode.ASSIST)
    assert mux.submit(BOT, move(), 0).accepted
    assert mux.lease_until_ns(0) is None


def test_assist_human_event_takes_lease_until_it_expires() -> None:
    mux = new_mux(Mode.ASSIST)
    assert mux.submit(HUMAN, move(), 0).accepted
    assert mux.lease_until_ns(1) == LEASE
    for t in (1, S, LEASE - 1):
        decision = mux.submit(BOT, move(), t)
        assert (decision.accepted, decision.reason) == (False, "human_lease"), t
    assert mux.submit(BOT, move(), LEASE).accepted  # boundary: the lease is [t, t + lease)


def test_assist_lease_holds_while_human_holds_a_key() -> None:
    mux = new_mux(Mode.ASSIST)
    mux.submit(HUMAN, key("ShiftLeft"), 0)
    assert not mux.submit(BOT, move(), 10 * S).accepted
    assert mux.lease_until_ns(10 * S) == 10 * S + LEASE  # rolling while held
    mux.submit(HUMAN, key("ShiftLeft", "up"), 11 * S)
    assert not mux.submit(BOT, move(), 11 * S + LEASE - 1).accepted
    assert mux.submit(BOT, move(), 11 * S + LEASE).accepted


def test_assist_lease_holds_while_human_holds_a_button() -> None:
    mux = new_mux(Mode.ASSIST)
    mux.submit(HUMAN, button("right", "down"), 0)
    assert not mux.submit(BOT, move(), 60 * S).accepted


def test_human_takeover_releases_everything_the_bot_holds_first() -> None:
    mux = new_mux(Mode.ASSIST)
    mux.submit(BOT, key("KeyW"), 0)
    mux.submit(BOT, button("right", "down"), 0)
    decision = mux.submit(HUMAN, move(), S)
    assert summary(decision) == [
        ("bot", "KeyW", "up", True, "handoff_release"),
        ("bot", "right", "up", True, "handoff_release"),
        ("human", "mouse_move", "", False, "ok"),
    ]
    assert mux.held(BOT) == (frozenset(), frozenset())


def test_synthetic_button_release_never_moves_the_pointer() -> None:
    mux = new_mux(Mode.ASSIST)
    mux.submit(BOT, button("left", "down"), 0)
    released = mux.submit(HUMAN, move(), S).inject[0].event
    assert isinstance(released, MouseButton)
    assert (released.x, released.y) == (None, None)


def test_bot_key_up_after_handoff_is_dropped_during_lease() -> None:
    mux = new_mux(Mode.ASSIST)
    mux.submit(BOT, key("KeyW"), 0)
    mux.submit(HUMAN, move(), S)
    assert mux.submit(BOT, key("KeyW", "up"), 2 * S).reason == "human_lease"


@pytest.mark.parametrize(
    ("start", "target", "loser"),
    [(Mode.HUMAN, Mode.BOT, HUMAN), (Mode.BOT, Mode.HUMAN, BOT), (Mode.ASSIST, Mode.BOT, HUMAN)],
)
def test_mode_switch_releases_the_losing_source(start: Mode, target: Mode, loser: Source) -> None:
    mux = new_mux(start)
    mux.submit(loser, key("KeyA"), 0)
    mux.submit(loser, button("left", "down"), 0)
    released = mux.set_mode(target, S)
    assert [(r.source, r.synthetic, r.reason) for r in released] == [
        (loser, True, "mode_release"),
        (loser, True, "mode_release"),
    ]
    assert mux.mode is target
    assert not mux.holds_anything(loser)


def test_switching_to_assist_releases_nobody() -> None:
    mux = new_mux(Mode.BOT)
    mux.submit(BOT, key("KeyA"), 0)
    assert mux.set_mode(Mode.ASSIST, S) == ()
    assert mux.held(BOT) == (frozenset({"KeyA"}), frozenset())


def test_same_mode_is_a_no_op() -> None:
    mux = new_mux(Mode.HUMAN)
    mux.submit(HUMAN, key("KeyA"), 0)
    assert mux.set_mode(Mode.HUMAN, S) == ()
    assert mux.holds_anything(HUMAN)


def test_a_new_mode_starts_without_a_lease() -> None:
    mux = new_mux(Mode.ASSIST)
    mux.submit(HUMAN, move(), 0)
    mux.set_mode(Mode.BOT, S)
    mux.set_mode(Mode.ASSIST, S)
    assert mux.submit(BOT, move(), S).accepted


def test_release_all_expands_to_explicit_ups() -> None:
    mux = new_mux(Mode.HUMAN)
    for code in ("KeyB", "KeyA"):
        mux.submit(HUMAN, key(code), 0)
    mux.submit(HUMAN, button("right", "down"), 0)
    decision = mux.submit(HUMAN, ReleaseAll(t_mono_ns=0), S)
    assert summary(decision) == [
        ("human", "KeyA", "up", True, "release_all"),
        ("human", "KeyB", "up", True, "release_all"),
        ("human", "right", "up", True, "release_all"),
    ]
    assert not mux.holds_anything(HUMAN)


@pytest.mark.parametrize("target", ["KeyD", "Enter", "NumpadEnter"])
def test_xfreerdp_hotkey_chords_are_never_delivered(target: str) -> None:
    mux = new_mux(Mode.HUMAN)
    mux.submit(HUMAN, key("ControlLeft"), 0)
    mux.submit(HUMAN, key("AltRight"), 0)
    decision = mux.submit(HUMAN, key(target), 0)
    assert (decision.accepted, decision.reason) == (False, "reserved_chord")
    assert target not in mux.held(HUMAN)[0]


def test_ctrl_d_without_alt_is_fine() -> None:
    mux = new_mux(Mode.HUMAN)
    mux.submit(HUMAN, key("ControlLeft"), 0)
    assert mux.submit(HUMAN, key("KeyD"), 0).accepted


def test_unknown_key_code_is_rejected() -> None:
    decision = new_mux(Mode.HUMAN).submit(HUMAN, key("Fn"), 0)
    assert (decision.accepted, decision.reason) == (False, "unknown_key_code")


def test_windows_key_is_accepted_for_the_toolbar() -> None:
    assert new_mux(Mode.HUMAN).submit(HUMAN, key("MetaLeft"), 0).accepted


def test_wheel_is_not_tracked_as_held() -> None:
    mux = new_mux(Mode.HUMAN)
    mux.submit(HUMAN, Wheel(t_mono_ns=0, dy=2), 0)
    assert not mux.holds_anything(HUMAN)


def test_no_lease_outside_assist() -> None:
    mux = new_mux(Mode.HUMAN)
    mux.submit(HUMAN, key("KeyA"), 0)
    assert not mux.lease_active(0)
    assert mux.lease_until_ns(0) is None


# --- ADR-0004: the bot may never paste ------------------------------------------------------


@pytest.mark.parametrize(
    ("modifier", "target"),
    [
        ("ControlLeft", "KeyV"),
        ("ControlRight", "KeyV"),
        ("MetaLeft", "KeyV"),  # Win+V: Windows clipboard history
        ("MetaRight", "KeyV"),
        ("ShiftLeft", "Insert"),
        ("ShiftRight", "Insert"),
    ],
)
def test_bot_paste_chords_are_refused_in_both_key_orders(modifier: str, target: str) -> None:
    mux = new_mux(Mode.BOT)
    assert mux.submit(BOT, key(modifier), 0).accepted
    refused = mux.submit(BOT, key(target), 0)
    assert (refused.accepted, refused.reason, refused.inject) == (False, "paste_chord_bot", ())
    mux.submit(BOT, key(modifier, "up"), 0)
    # Other order: X autorepeats a held XTest key, so "hold V, then press Ctrl" pastes too.
    assert mux.submit(BOT, key(target), 0).accepted
    late = mux.submit(BOT, key(modifier), 0)
    assert (late.accepted, late.reason) == (False, "paste_chord_bot")


@pytest.mark.parametrize("mode", [Mode.HUMAN, Mode.ASSIST])
def test_the_human_may_paste(mode: Mode) -> None:
    mux = new_mux(mode)
    for event in (key("ControlLeft"), key("KeyV"), key("KeyV", "up"), key("ControlLeft", "up")):
        assert mux.submit(HUMAN, event, 0).accepted


def test_bot_keeps_ordinary_keys_and_copy() -> None:
    mux = new_mux(Mode.BOT)
    assert mux.submit(BOT, key("KeyV"), 0).accepted  # plain V (e.g. a game hotkey)
    assert mux.submit(BOT, key("KeyV", "up"), 0).accepted
    assert mux.submit(BOT, key("ControlLeft"), 0).accepted
    assert mux.submit(BOT, key("KeyC"), 0).accepted  # Ctrl+C copies, it does not paste
    assert mux.submit(BOT, key("Insert"), 0).accepted  # Ctrl+Insert is copy, not paste
