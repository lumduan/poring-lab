"""Loop plumbing, tested on the host without torch (the vision modules import it lazily)."""

from collections.abc import Sequence

from poring_env.clock import FrameCounter
from poring_env.frame import Frame
from poring_env.protocol import Box, InputEvent, Key, Status
from poring_vision.detector import DebugBoxDetector, NullDetector
from poring_vision.loop import run, step
from poring_vision.policy import IdlePolicy


class FakeEnv:
    def __init__(self, fail_first: int = 0) -> None:
        self.counter = FrameCounter()
        self.fail_first = fail_first
        self.published: list[tuple[int, list[Box]]] = []
        self.acted: list[tuple[int, list[InputEvent]]] = []

    def grab(self) -> Frame:
        if self.fail_first > 0:
            self.fail_first -= 1
            raise OSError("display not ready")
        fid = self.counter.next()
        return Frame(frame_id=fid, t_capture_ns=fid, width=2, height=2, bgra=b"\x00" * 16)

    def act(self, frame: Frame, events: Sequence[InputEvent]) -> bool:
        self.acted.append((frame.frame_id, list(events)))
        return True

    def publish_detections(self, frame: Frame, boxes: Sequence[Box]) -> bool:
        self.published.append((frame.frame_id, list(boxes)))
        return True

    def status(self) -> Status | None:
        return None


class PressA:
    def decide(self, frame: Frame, boxes: Sequence[Box], status: Status | None) -> list[InputEvent]:
        return [Key(t_mono_ns=1, frame_id=frame.frame_id, code="KeyA", action="down")]


def test_detections_are_published_for_the_frame_they_came_from() -> None:
    env = FakeEnv()
    result = step(env, DebugBoxDetector(), IdlePolicy())
    assert (result.frame_id, result.boxes, result.events) == (0, 1, 0)
    assert env.published == [(0, [Box(x1=0.4, y1=0.4, x2=0.6, y2=0.6, cls="debug", conf=1.0)])]


def test_idle_policy_never_acts() -> None:
    env = FakeEnv()
    step(env, NullDetector(), IdlePolicy())
    assert env.acted == []


def test_decisions_are_attributed_to_their_frame() -> None:
    env = FakeEnv()
    step(env, NullDetector(), IdlePolicy())
    step(env, NullDetector(), PressA())
    assert [fid for fid, _ in env.acted] == [1]


def test_run_survives_failures_and_paces() -> None:
    env = FakeEnv(fail_first=2)
    sleeps: list[float] = []
    done = run(env, NullDetector(), IdlePolicy(), hz=10, iterations=5, sleep=sleeps.append)
    assert done == 3
    assert sleeps[:2] == [1.0, 1.0]  # back-off after each failure
    assert all(0.0 <= s <= 0.1 for s in sleeps[2:])  # then paced at <= 1/hz


def test_a_stale_frame_skips_the_tick_without_the_error_backoff() -> None:
    """The frame-age guard (2026-10-04): MuxedEnv.act raises StaleFrame on a frozen stream. The loop
    skips that tick at once -- no 1 s back-off -- and acts again on the next fresh frame."""
    from poring_env.freshness import StaleFrame

    class Freezing(FakeEnv):
        def __init__(self) -> None:
            super().__init__()
            self.stale = 2

        def act(self, frame: Frame, events: Sequence[InputEvent]) -> bool:
            if self.stale:
                self.stale -= 1
                raise StaleFrame("the stream is frozen")
            return super().act(frame, events)

    env = Freezing()
    sleeps: list[float] = []
    done = run(env, NullDetector(), PressA(), hz=10, iterations=4, sleep=sleeps.append)
    assert done == 2 and 1.0 not in sleeps and len(env.acted) == 2
