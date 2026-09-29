"""Agent loop skeleton: grab -> infer -> decide -> act, where "act" goes through the backend mux.

Nothing decides anything yet (NullDetector sees nothing, IdlePolicy does nothing). The loop exists
so the plumbing -- X capture from this container, the internal agent socket, the overlay relay, and
frame ids + monotonic timestamps end to end -- is exercised from day one.
"""

import logging
import os
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Protocol

from poring_env.frame import Frame
from poring_env.protocol import Box, InputEvent, Status
from poring_vision import __version__
from poring_vision.detector import DebugBoxDetector, Detector, NullDetector
from poring_vision.policy import IdlePolicy, Policy

log = logging.getLogger(__name__)


class AgentEnv(Protocol):
    """The slice of poring_env.remote.MuxedEnv the loop uses."""

    def grab(self) -> Frame: ...

    def act(self, frame: Frame, events: Sequence[InputEvent]) -> bool: ...

    def publish_detections(self, frame: Frame, boxes: Sequence[Box]) -> bool: ...

    def status(self) -> Status | None: ...


@dataclass(frozen=True, slots=True)
class StepResult:
    frame_id: int
    boxes: int
    events: int


def step(env: AgentEnv, detector: Detector, policy: Policy) -> StepResult:
    frame = env.grab()
    boxes = detector.detect(frame)
    env.publish_detections(frame, boxes)
    events = policy.decide(frame, boxes, env.status())
    if events:
        env.act(frame, events)
    return StepResult(frame.frame_id, len(boxes), len(events))


def run(
    env: AgentEnv,
    detector: Detector,
    policy: Policy,
    *,
    hz: float,
    iterations: int | None = None,
    sleep: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
) -> int:
    """Run at most ``hz`` steps per second and survive X/backend hiccups. ``iterations`` bounds the
    attempts (tests); returns how many steps completed."""
    period = 1.0 / hz
    attempts = done = 0
    while iterations is None or attempts < iterations:
        attempts += 1
        started = clock()
        try:
            step(env, detector, policy)
        except Exception as exc:
            log.warning("step failed (%s); retrying in 1s", exc)
            sleep(1.0)
            continue
        done += 1
        sleep(max(0.0, period - (clock() - started)))
    return done


@dataclass(frozen=True, slots=True)
class AgentConfig:
    display: str
    backend_url: str
    hz: float
    max_vram_fraction: float
    debug_box: bool

    @classmethod
    def from_env(cls) -> "AgentConfig":
        return cls(
            display=os.environ.get("DISPLAY", ":99"),
            backend_url=os.environ.get("BACKEND_AGENT_URL", "ws://backend:8001/internal/agent"),
            hz=float(os.environ.get("AGENT_HZ", "10")),
            max_vram_fraction=float(os.environ.get("VISION_MAX_VRAM_FRACTION", "0.25")),
            debug_box=os.environ.get("VISION_DEBUG_BOX", "false").lower() == "true",
        )


def main() -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    cfg = AgentConfig.from_env()

    from poring_env.remote import BackendInputSink, MuxedEnv
    from poring_env.x11 import X11Capture
    from poring_vision.gpu import configure_gpu

    configure_gpu(cfg.max_vram_fraction)
    detector: Detector = DebugBoxDetector() if cfg.debug_box else NullDetector()
    sink = BackendInputSink(cfg.backend_url, agent_id="vision", version=__version__)
    log.info("agent loop at %.1f Hz, detector=%s", cfg.hz, type(detector).__name__)
    with MuxedEnv(X11Capture(cfg.display), sink) as env:
        run(env, detector, IdlePolicy(), hz=cfg.hz)


if __name__ == "__main__":
    main()
