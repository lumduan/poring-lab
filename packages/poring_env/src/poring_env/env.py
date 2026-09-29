"""The environment contract (ADR-0003): an agent observes through ``grab`` and acts through
``send_input`` -- nothing else. No memory reading, no packet injection.

Implementations choose the transport, never the contract:
  * ``X11Env``   -- grab from X, inject straight into X via XTest. Only the backend's input mux may
                    use the input half (single-writer invariant, ADR-0002).
  * ``MuxedEnv`` -- grab from X, send input to the backend's mux. What the vision agent uses.
Future: a replay env over recorded frames + input logs, for offline evaluation.
"""

from abc import ABC, abstractmethod
from types import TracebackType
from typing import Protocol, Self

from poring_env.frame import Frame
from poring_env.protocol import InputEvent


class FrameSource(Protocol):
    def grab(self) -> Frame: ...

    def close(self) -> None: ...


class InputSink(Protocol):
    def send_input(self, event: InputEvent) -> None: ...

    def close(self) -> None: ...


class Env(ABC):
    @abstractmethod
    def grab(self) -> Frame:
        """Capture the current screen. Frame ids strictly increase per Env instance."""

    @abstractmethod
    def send_input(self, event: InputEvent) -> None:
        """Act. ``event.frame_id`` should name the frame the decision was based on."""

    def close(self) -> None:  # noqa: B027 -- optional hook, deliberately not abstract
        """Release display / socket resources."""

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()


class CompositeEnv(Env):
    """An Env assembled from a FrameSource and an InputSink."""

    def __init__(self, source: FrameSource, sink: InputSink) -> None:
        self._source = source
        self._sink = sink

    def grab(self) -> Frame:
        return self._source.grab()

    def send_input(self, event: InputEvent) -> None:
        self._sink.send_input(event)

    def close(self) -> None:
        try:
            self._sink.close()
        finally:
            self._source.close()
