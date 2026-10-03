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
from pathlib import Path
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
    session_size: str  # SESSION_SIZE: the same session area the backend maps input over
    backend_url: str
    hz: float
    max_vram_fraction: float
    debug_box: bool
    frame_source: str  # VISION_FRAME_SOURCE: auto | bus | x11 (ADR-0014)
    framebus: str

    @classmethod
    def from_env(cls) -> "AgentConfig":
        return cls(
            display=os.environ.get("DISPLAY", ":99"),
            session_size=os.environ.get("SESSION_SIZE", ""),
            backend_url=os.environ.get("BACKEND_AGENT_URL", "ws://backend:8001/internal/agent"),
            hz=float(os.environ.get("AGENT_HZ", "10")),
            max_vram_fraction=float(os.environ.get("VISION_MAX_VRAM_FRACTION", "0.25")),
            debug_box=os.environ.get("VISION_DEBUG_BOX", "false").lower() == "true",
            frame_source=os.environ.get("VISION_FRAME_SOURCE", "auto"),
            framebus=os.environ.get("FRAMEBUS_RING", "/framebus/ring"),
        )


def pick_frame_source(choice: str, ring: str, *, stale_s: float = 2.0) -> str:
    """``bus`` / ``x11`` as configured; ``auto`` = the S2 frame bus when its writer is live (a
    heartbeat under ``stale_s``), else X. Decided once at start: a stream that starts later needs
    a restart of the loop (the bus and X number frames differently)."""
    if choice in ("bus", "x11"):
        return choice
    if choice != "auto":
        raise ValueError(f"VISION_FRAME_SOURCE must be auto, bus or x11, not {choice!r}")
    from poring_env.framebus import FrameBusError, FrameBusReader

    try:
        reader = FrameBusReader(Path(ring), "vision-probe")
    except (FrameBusError, OSError):
        return "x11"
    try:
        return "bus" if reader.writer().heartbeat_age_s < stale_s else "x11"
    except FrameBusError:
        return "x11"
    finally:
        reader.close()


def main() -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    cfg = AgentConfig.from_env()

    from poring_env.remote import make_env
    from poring_vision.gpu import configure_gpu

    configure_gpu(cfg.max_vram_fraction)
    detector: Detector = DebugBoxDetector() if cfg.debug_box else NullDetector()
    source = pick_frame_source(cfg.frame_source, cfg.framebus)
    log.info("agent loop at %.1f Hz, detector=%s, frames from %s", cfg.hz,
             type(detector).__name__, source)  # fmt: skip
    if source == "bus":
        # ADR-0014: the S2 frame bus (the stream's session-sized frames); no X at all.
        env = make_env("gamestream", backend_url=cfg.backend_url, agent_id="vision",
                       version=__version__, ring=cfg.framebus)  # fmt: skip
    else:
        from poring_env.x11 import parse_session_size

        # Grab exactly the area the backend normalises input over, or clicks would land off target.
        session = parse_session_size(cfg.session_size)
        env = make_env("x11", backend_url=cfg.backend_url, agent_id="vision", version=__version__,
                       display=cfg.display, session=session)  # fmt: skip
    with env:
        run(env, detector, IdlePolicy(), hz=cfg.hz)


if __name__ == "__main__":
    main()
