"""Decision: (frame, detections, mux status) -> input events. Only a placeholder lives here."""

from collections.abc import Sequence
from typing import Protocol

from poring_env.frame import Frame
from poring_env.protocol import Box, InputEvent, Status


class Policy(Protocol):
    def decide(
        self, frame: Frame, boxes: Sequence[Box], status: Status | None
    ) -> list[InputEvent]: ...


class IdlePolicy:
    """Never acts. The default, so an unconfigured agent is always harmless.

    TODO(policy), deliberately not implemented in the scaffold:
      * decision logic (targeting, movement, skills) from detections only -- pixels in,
        mouse/keyboard out; no memory reading, no packet data at decision time;
      * humanization of timing and pointer paths;
      * any LLM integration.
    Whatever lands here must tag every event with ``frame.frame_id`` so reaction latency can be
    measured, and should back off whenever ``status.mode`` is HUMAN or a human lease is active.
    """

    def decide(self, frame: Frame, boxes: Sequence[Box], status: Status | None) -> list[InputEvent]:
        return []
