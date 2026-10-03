"""S2 step 3 (ADR-0014): the S2 client's input socket, on the host -- a fake LiSend* library, a real
unix socket, and the backend's own sink (poring_env.s2input) on the other end."""

import ctypes
import json
import socket
import sys
import time
from pathlib import Path
from typing import Any

import pytest

GAMESTREAM = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(GAMESTREAM))

from s2spike import input_socket as isk  # noqa: E402
from s2spike import limelight, presence  # noqa: E402
from s2spike.vk import CODE_TO_VK  # noqa: E402

W, H = 1440, 900


class FakeLib:
    def __init__(self) -> None:
        self.calls: list[tuple[Any, ...]] = []

    def LiSendMousePositionEvent(self, x: int, y: int, w: int, h: int) -> int:  # noqa: N802
        self.calls.append(("move", x, y, w, h))
        return 0

    def LiSendMouseButtonEvent(self, action: bytes, button: int) -> int:  # noqa: N802
        self.calls.append(("button", action[0], button))
        return 0

    def LiSendKeyboardEvent(self, code: int, action: bytes, mods: bytes) -> int:  # noqa: N802
        self.calls.append(("key", ctypes.c_ushort(code).value & 0xFF, action[0], mods[0]))
        return 0

    def LiSendHighResScrollEvent(self, amount: int) -> int:  # noqa: N802
        self.calls.append(("scroll", amount))
        return 0


C = limelight.CONSTANTS
DOWN, UP = C["KEY_ACTION_DOWN"], C["KEY_ACTION_UP"]
PRESS, RELEASE = C["BUTTON_ACTION_PRESS"], C["BUTTON_ACTION_RELEASE"]


@pytest.fixture
def mapper() -> isk.InputMapper:
    return isk.InputMapper(FakeLib(), C, W, H)


def key(code: str, action: str) -> dict[str, Any]:
    return {"type": "key", "code": code, "action": action, "t_mono_ns": 1, "frame_id": -1}


def test_keys_go_by_physical_position_with_their_own_modifier_bit(mapper: isk.InputMapper) -> None:
    """Moonlight-qt (SDL) reports a modifier key's state INCLUDING its own change."""
    mapper.batch([key("ShiftLeft", "down"), key("KeyA", "down"), key("KeyA", "up"),
                  key("ShiftLeft", "up")])  # fmt: skip
    assert mapper.lib.calls == [
        ("key", 0xA0, DOWN, 0x01),  # shift down: shift bit already set
        ("key", CODE_TO_VK["KeyA"], DOWN, 0x01),
        ("key", CODE_TO_VK["KeyA"], UP, 0x01),
        ("key", 0xA0, UP, 0x00),  # shift up: bit cleared
    ]
    assert mapper.keys == set()


def test_both_shifts_keep_the_bit_until_the_last_one_is_released(mapper: isk.InputMapper) -> None:
    mapper.batch([key("ShiftLeft", "down"), key("ShiftRight", "down"), key("ShiftLeft", "up")])
    assert mapper.lib.calls[-1] == ("key", 0xA0, UP, 0x01)


def test_the_key_code_is_sent_as_moonlight_qt_does(mapper: isk.InputMapper) -> None:
    calls: list[int] = []
    mapper.lib.LiSendKeyboardEvent = lambda code, _a, _m: calls.append(code)  # type: ignore[method-assign]
    mapper.apply(key("Enter", "down"))
    assert calls == [ctypes.c_short(0x8000 | 0x0D).value] and calls[0] < 0  # short: wraps negative


def test_moves_buttons_and_the_pointer(mapper: isk.InputMapper) -> None:
    mapper.batch([
        {"type": "mouse_move", "x": 0.5, "y": 1.0},
        {"type": "mouse_button", "button": "right", "action": "down", "x": 0.0, "y": 0.25},
        {"type": "mouse_button", "button": "right", "action": "up", "x": None, "y": None},
    ])  # fmt: skip
    assert mapper.lib.calls == [
        ("move", 720, 899, W, H),  # 1.0 -> the last pixel (poring_env.x11.to_pixels's rule)
        ("move", 0, 225, W, H),  # with x/y: move there first
        ("button", PRESS, C["BUTTON_RIGHT"]),
        ("button", RELEASE, C["BUTTON_RIGHT"]),  # without x/y: wherever the pointer is
    ]


@pytest.mark.parametrize(("dy", "expected"), [(1, [-120]), (-2, [120, 120]), (0, [])])
def test_wheel_down_is_a_negative_windows_delta_per_notch(
    mapper: isk.InputMapper, dy: int, expected: list[int]
) -> None:
    mapper.apply({"type": "wheel", "dy": dy})
    assert [c[1] for c in mapper.lib.calls] == expected


def test_release_all_releases_keys_then_modifiers_then_buttons(mapper: isk.InputMapper) -> None:
    mapper.batch([key("ControlLeft", "down"), key("KeyW", "down"),
                  {"type": "mouse_button", "button": "left", "action": "down"}])  # fmt: skip
    mapper.lib.calls.clear()
    mapper.apply({"type": "release_all"})
    assert mapper.lib.calls == [
        ("key", CODE_TO_VK["KeyW"], UP, 0x02),  # the letter first: no stray chord on the way out
        ("key", 0xA2, UP, 0x00),
        ("button", RELEASE, C["BUTTON_LEFT"]),
    ]
    assert not mapper.keys and not mapper.buttons


@pytest.mark.parametrize(
    ("event", "reason"),
    [
        ({"type": "clipboard_paste", "text": "x"}, "unknown_type"),  # never an input type here
        ({"type": "key", "code": "KeyA", "action": "down", "text": "a"}, "unknown_field"),
        ({"type": "key", "code": "Fn", "action": "down"}, "unknown_key"),
        ({"type": "key", "code": "KeyA", "action": "tap"}, "unknown_key"),
        ({"type": "mouse_move", "x": 1.5, "y": 0.1}, "bad_coordinate"),
        ({"type": "mouse_move", "x": True, "y": 0.1}, "bad_coordinate"),
        ({"type": "mouse_button", "button": "left", "action": "down", "x": 0.1}, "bad_coordinate"),
        ({"type": "mouse_button", "button": "x1", "action": "down"}, "bad_button"),
        ({"type": "wheel", "dy": 11}, "bad_wheel"),
        ({"type": "wheel", "dy": 1.0}, "bad_wheel"),
        (["key"], "not_an_object"),
    ],
)
def test_anything_off_the_whitelist_is_refused_and_nothing_of_it_is_sent(
    mapper: isk.InputMapper, event: Any, reason: str
) -> None:
    applied, refused = mapper.batch([event])
    assert (applied, refused, mapper.lib.calls) == (0, [[0, reason]], [])


def test_a_bad_batch_line_is_refused_whole(mapper: isk.InputMapper) -> None:
    for line in (b"not json", b'{"t": 1}', b'{"t": "1", "events": []}',
                 b'{"t": 1, "events": [], "x": 1}'):  # fmt: skip
        ack = isk.handle_line(mapper, line, lambda: 5)
        assert ack["refused"] == [[-1, "bad_batch"]] and ack["n"] == 0
    too_many = json.dumps({"t": 1, "events": [{"type": "release_all"}] * 513}).encode()
    assert isk.handle_line(mapper, too_many, lambda: 5)["refused"] == [[-1, "too_many"]]
    assert mapper.lib.calls == []


def test_the_counts_never_hold_a_key_identity(mapper: isk.InputMapper) -> None:
    mapper.batch([key("KeyP", "down"), key("KeyP", "up")])
    assert set(mapper.counts) == {"batches", "keys", "buttons", "moves", "wheel", "release_all",
                                  "refused"}  # fmt: skip
    assert "KeyP" not in json.dumps(mapper.counts)


# --- the socket, end to end with the backend's sink -----------------------------------------------


@pytest.fixture
def server(tmp_path: Path):  # type: ignore[no-untyped-def]
    path = tmp_path / "input.sock"
    lines: list[str] = []
    srv = isk.InputServer(path, isk.InputMapper(FakeLib(), C, W, H), lines.append)
    yield srv
    srv.close()


def test_round_trip_through_the_backends_sink(server: isk.InputServer) -> None:
    from poring_env.protocol import Key, MouseButton, MouseMove
    from poring_env.s2input import GameStreamInput

    assert oct(server.path.stat().st_mode & 0o777) == "0o660"
    sink = GameStreamInput(server.path, size=(W, H))
    sink.send_many([
        MouseMove(t_mono_ns=1, x=0.25, y=0.5),
        MouseButton(t_mono_ns=1, button="left", action="down"),
        MouseButton(t_mono_ns=1, button="left", action="up"),
        Key(t_mono_ns=1, code="KeyQ", action="down"),
        Key(t_mono_ns=1, code="KeyQ", action="up"),
    ])  # fmt: skip
    assert sink.acks == 1 and sink.refused == 0 and len(sink.leg_ns) == 1 and sink.leg_ns[0] >= 0
    assert sink.pointer() == (360, 450)
    calls = server.mapper.lib.calls
    assert calls[0] == ("move", 360, 450, W, H) and len(calls) == 5
    sink.close()


def test_a_peer_that_goes_away_has_everything_released(server: isk.InputServer) -> None:
    from poring_env.protocol import Key
    from poring_env.s2input import GameStreamInput

    sink = GameStreamInput(server.path, size=(W, H))
    sink.send_many([Key(t_mono_ns=1, code="KeyW", action="down")])  # a walk key left down
    sink.close()
    deadline = time.monotonic() + 3
    while server.mapper.keys and time.monotonic() < deadline:
        time.sleep(0.02)
    assert server.mapper.keys == set()
    assert server.mapper.lib.calls[-1] == ("key", CODE_TO_VK["KeyW"], UP, 0)


def test_no_ack_in_time_raises(tmp_path: Path) -> None:
    from poring_env.protocol import ReleaseAll
    from poring_env.s2input import GameStreamInput, S2InputError

    path = tmp_path / "silent.sock"
    mute = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    mute.bind(str(path))
    mute.listen(1)
    sink = GameStreamInput(path, timeout_s=0.2)
    with pytest.raises(S2InputError):
        sink.send_many([ReleaseAll(t_mono_ns=1)])
    sink.close()
    mute.close()


def test_a_non_socket_at_the_path_is_never_replaced(tmp_path: Path) -> None:
    path = tmp_path / "input.sock"
    path.write_text("not a socket")
    with pytest.raises(RuntimeError, match="not a socket"):
        isk.InputServer(path, isk.InputMapper(FakeLib(), C, W, H), print)
    assert path.read_text() == "not a socket"


def test_the_presence_marker_is_never_mapped_and_takes_no_input() -> None:
    """It keeps rdp-loop's interlock and /health (WM_CLASS moonlight) and is nothing else."""
    src = Path(presence.__file__).read_text()
    assert presence.WM_CLASS == (b"moonlight", b"S2client")
    for call in ("XMapWindow(", "XMapRaised(", "XSelectInput(", "XPutImage(", "XSetInputFocus("):
        assert call not in src, call
