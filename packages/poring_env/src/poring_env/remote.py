"""Agent-side Env: pixels straight from X, input through the backend's mux (requires the ``x11``
and ``remote`` extras).

The agent never injects XTest events itself -- that would bypass the mux's HUMAN/BOT/ASSIST
arbitration and the input log (ADR-0002). Input that cannot be delivered (backend down) is dropped,
never queued: stale input is worse than none.
"""

import logging
import time
from collections import OrderedDict
from collections.abc import Sequence
from contextlib import ExitStack
from pathlib import Path
from typing import Literal

from websockets.exceptions import ConnectionClosed, WebSocketException
from websockets.sync.client import ClientConnection, connect

from poring_env.clock import monotonic_ns
from poring_env.env import Env, FrameSource
from poring_env.frame import Frame
from poring_env.freshness import (
    CITED_MAX_AGE_MS,
    STREAM_MAX_AGE_MS,
    StaleFrame,
    age_ms,
    presses,
)
from poring_env.protocol import (
    AgentHello,
    AgentInput,
    Box,
    Detections,
    InputAck,
    InputEvent,
    Message,
    Status,
    parse_backend_to_agent,
)

log = logging.getLogger(__name__)


class BackendInputSink:
    """InputSink that forwards to the backend's ``/internal/agent`` socket."""

    def __init__(
        self,
        url: str,
        *,
        agent_id: str,
        version: str,
        open_timeout: float = 5.0,
        retry_s: float = 2.0,
    ) -> None:
        self._url = url
        self._agent_id = agent_id
        self._version = version
        self._open_timeout = open_timeout
        self._retry_s = retry_s
        # websockets >= 17.1 wants connections used as context managers; the stack holds this
        # long-lived one open across calls.
        self._stack: ExitStack | None = None
        self._ws: ClientConnection | None = None
        self._next_attempt = 0.0
        self._status: Status | None = None
        self.acked_accepted = 0
        self.acked_dropped = 0

    @property
    def connected(self) -> bool:
        return self._ws is not None

    def _connection(self) -> ClientConnection | None:
        if self._ws is not None:
            return self._ws
        now = time.monotonic()
        if now < self._next_attempt:
            return None
        stack = ExitStack()
        try:
            ws = stack.enter_context(
                connect(self._url, open_timeout=self._open_timeout, max_size=2**20)
            )
            hello = AgentHello(
                t_mono_ns=monotonic_ns(), agent_id=self._agent_id, version=self._version
            )
            ws.send(hello.model_dump_json())
        except (OSError, TimeoutError, WebSocketException) as exc:
            stack.close()
            log.warning(
                "backend %s unreachable (%s); retry in %.0fs", self._url, exc, self._retry_s
            )
            self._next_attempt = now + self._retry_s
            return None
        log.info("connected to %s", self._url)
        self._stack, self._ws = stack, ws
        return ws

    def _disconnect(self) -> None:
        stack, self._stack, self._ws = self._stack, None, None
        if stack is not None:
            stack.close()

    def _drop(self, reason: object) -> None:
        log.warning("lost backend connection: %s", reason)
        self._disconnect()
        self._next_attempt = time.monotonic() + self._retry_s

    def _send(self, msg: Message) -> bool:
        ws = self._connection()
        if ws is None:
            return False
        try:
            ws.send(msg.model_dump_json())
        except (ConnectionClosed, OSError) as exc:
            self._drop(exc)
            return False
        return True

    def send_batch(self, events: Sequence[InputEvent], *, frame_id: int, t_capture_ns: int) -> bool:
        """Send one AgentInput. False if it could not be delivered (it is NOT retried)."""
        if not events:
            return True
        return self._send(
            AgentInput(
                t_mono_ns=monotonic_ns(),
                frame_id=frame_id,
                t_capture_ns=t_capture_ns,
                events=list(events),
            )
        )

    def send_input(self, event: InputEvent) -> None:
        self.send_batch([event], frame_id=event.frame_id, t_capture_ns=0)

    def publish(self, detections: Detections) -> bool:
        return self._send(detections)

    def poll(self) -> Status | None:
        """Drain pending backend messages without blocking; return the newest Status seen."""
        ws = self._ws
        if ws is None:
            return self._status
        try:
            while True:
                msg = parse_backend_to_agent(ws.recv(timeout=0))
                if isinstance(msg, Status):
                    self._status = msg
                elif isinstance(msg, InputAck):
                    self.acked_accepted += msg.accepted
                    self.acked_dropped += msg.dropped
        except TimeoutError:
            pass
        except (ConnectionClosed, OSError) as exc:
            self._drop(exc)
        return self._status

    def close(self) -> None:
        self._disconnect()


class MuxedEnv(Env):
    """What the vision agent uses: ``grab`` from a FrameSource (X, or the S2 frame bus),
    ``send_input`` through the backend mux."""

    def __init__(self, source: FrameSource, sink: BackendInputSink, *, history: int = 256) -> None:
        self._source = source
        self.sink = sink
        self._history = history
        self._captured: OrderedDict[int, int] = OrderedDict()  # frame_id -> t_capture_ns
        self.stale_refused = 0  # presses refused by the frame-age guard

    def grab(self) -> Frame:
        frame = self._source.grab()
        self._captured[frame.frame_id] = frame.t_capture_ns
        while len(self._captured) > self._history:
            self._captured.popitem(last=False)
        return frame

    def _check_fresh(self, events: Sequence[InputEvent], cited_t_ns: int | None) -> None:
        """The frame-age guard (poring_env.freshness): presses are refused on a frozen stream or a
        stale cited frame; releases always pass."""
        if not presses(events):
            return
        stream_age = getattr(self._source, "stream_age_ms", None)
        if callable(stream_age):
            age = stream_age()
            if age is not None and age > STREAM_MAX_AGE_MS:
                self.stale_refused += 1
                raise StaleFrame(f"the stream is frozen ({age:.0f} ms > {STREAM_MAX_AGE_MS:.0f})")
        if cited_t_ns:
            cited = age_ms(cited_t_ns)
            if cited > CITED_MAX_AGE_MS:
                self.stale_refused += 1
                raise StaleFrame(
                    f"the cited frame is {cited:.0f} ms old (> {CITED_MAX_AGE_MS:.0f})"
                )

    def send_input(self, event: InputEvent) -> None:
        cited = self._captured.get(event.frame_id, 0)
        self._check_fresh([event], cited or None)
        self.sink.send_batch([event], frame_id=event.frame_id, t_capture_ns=cited)

    def act(self, frame: Frame, events: Sequence[InputEvent]) -> bool:
        """Send a whole decision as one batch, attributed to ``frame``. Raises StaleFrame (sending
        nothing) when the stream is frozen or ``frame`` is too old."""
        self._check_fresh(events, frame.t_capture_ns)
        return self.sink.send_batch(
            events, frame_id=frame.frame_id, t_capture_ns=frame.t_capture_ns
        )

    def publish_detections(self, frame: Frame, boxes: Sequence[Box]) -> bool:
        return self.sink.publish(
            Detections(
                t_mono_ns=monotonic_ns(),
                frame_id=frame.frame_id,
                t_capture_ns=frame.t_capture_ns,
                boxes=list(boxes),
            )
        )

    def status(self) -> Status | None:
        return self.sink.poll()

    def close(self) -> None:
        try:
            self.sink.close()
        finally:
            self._source.close()


FrameSourceKind = Literal["x11", "gamestream"]


def make_env(
    kind: FrameSourceKind,
    *,
    backend_url: str,
    agent_id: str,
    version: str,
    display: str = ":99",
    session: tuple[int, int] | None = None,
    ring: str | Path = "/framebus/ring",
) -> MuxedEnv:
    """The agent's Env. Input ALWAYS goes through the backend's mux (ADR-0002); only the pixels'
    source differs:

    - ``"x11"``: grabs of the lab display (RDP, Moonlight-qt);
    - ``"gamestream"`` (ADR-0014, S2): the S2 frame bus -- every decoded frame, with the writer's
      ``frame_id`` and decode-complete time; no X at all (the mux sends to the S2 input socket).
    """
    sink = BackendInputSink(backend_url, agent_id=agent_id, version=version)
    source: FrameSource
    if kind == "gamestream":
        from poring_env.bus_source import BusFrameSource

        source = BusFrameSource(ring, agent_id)
    elif kind == "x11":
        from poring_env.x11 import X11Capture  # the x11 extra, only when X is the source

        source = X11Capture(display, session=session)
    else:
        raise ValueError(f"unknown env kind {kind!r}")
    return MuxedEnv(source, sink)
