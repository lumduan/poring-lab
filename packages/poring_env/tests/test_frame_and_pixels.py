import os

import numpy as np
import pytest

from poring_env.clock import FrameCounter
from poring_env.frame import Frame
from poring_env.x11 import to_pixels


def test_frame_rejects_wrong_buffer_size() -> None:
    with pytest.raises(ValueError, match="expected 32"):
        Frame(frame_id=0, t_capture_ns=0, width=4, height=2, bgra=b"\x00" * 31)


def test_frame_views_share_the_buffer() -> None:
    raw = bytes(range(4 * 2 * 4))
    frame = Frame(frame_id=0, t_capture_ns=0, width=4, height=2, bgra=raw)
    arr = frame.to_numpy()
    assert arr.shape == (2, 4, 4) and arr.dtype == np.uint8
    assert frame.bgr().shape == (2, 4, 3)
    assert arr[1, 3].tolist() == list(raw[28:32])
    assert not arr.flags.writeable


def test_frame_counter_is_strictly_increasing() -> None:
    counter = FrameCounter()
    assert counter.last == -1
    assert [counter.next() for _ in range(3)] == [0, 1, 2]
    assert counter.last == 2


@pytest.mark.parametrize(
    ("x", "y", "expected"),
    [
        (0.0, 0.0, (0, 0)),
        (0.25, 0.5, (320, 360)),  # scripts/smoke_test.sh relies on this exact mapping
        (1.0, 1.0, (1279, 719)),
        (0.9999, 0.0001, (1279, 0)),
    ],
)
def test_to_pixels(x: float, y: float, expected: tuple[int, int]) -> None:
    assert to_pixels(x, y, 1280, 720) == expected


@pytest.mark.skipif(
    not os.environ.get("PORING_TEST_DISPLAY"),
    reason="set PORING_TEST_DISPLAY=:99 inside a container that mounts the X socket",
)
def test_x11_round_trip() -> None:
    from poring_env.protocol import MouseMove
    from poring_env.x11 import X11Env

    with X11Env(os.environ["PORING_TEST_DISPLAY"]) as env:
        frame = env.grab()
        assert frame.width > 0 and frame.height > 0
        env.send_input(MouseMove(t_mono_ns=1, frame_id=frame.frame_id, x=0.25, y=0.5))
        assert env.input.pointer() == to_pixels(0.25, 0.5, env.input.width, env.input.height)
