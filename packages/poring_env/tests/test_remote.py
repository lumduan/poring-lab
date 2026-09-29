import threading
from collections.abc import Iterator

import pytest
from websockets.sync.server import Server, ServerConnection, serve

from poring_env.clock import FrameCounter
from poring_env.frame import Frame
from poring_env.protocol import (
    AgentHello,
    AgentInput,
    Box,
    Detections,
    InputAck,
    Key,
    Message,
    Mode,
    Status,
    parse_agent_to_backend,
)
from poring_env.remote import BackendInputSink, MuxedEnv


class FakeSource:
    def __init__(self) -> None:
        self.counter = FrameCounter()

    def grab(self) -> Frame:
        fid = self.counter.next()
        return Frame(frame_id=fid, t_capture_ns=1000 + fid, width=2, height=1, bgra=b"\x00" * 8)

    def close(self) -> None:
        pass


@pytest.fixture
def backend() -> Iterator[tuple[str, list[Message]]]:
    """A stand-in /internal/agent that records messages and answers each input with an ack."""
    received: list[Message] = []

    def handler(ws: ServerConnection) -> None:
        for raw in ws:
            msg = parse_agent_to_backend(raw)
            received.append(msg)
            if isinstance(msg, AgentHello):
                status = Status(
                    t_mono_ns=1, mode=Mode.BOT, bot_connected=True, capture_fps=0.0, viewers=0
                )
                ws.send(status.model_dump_json())
            elif isinstance(msg, AgentInput):
                ack = InputAck(t_mono_ns=1, frame_id=msg.frame_id, accepted=1, dropped=0)
                ws.send(ack.model_dump_json())

    server: Server = serve(handler, "127.0.0.1", 0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    port = server.socket.getsockname()[1]
    yield f"ws://127.0.0.1:{port}", received
    server.shutdown()


def _wait_for(pred: object, timeout: float = 2.0) -> None:
    import time

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if pred():  # type: ignore[operator]
            return
        time.sleep(0.01)
    raise AssertionError("condition not met in time")


def test_muxed_env_attributes_input_to_the_grabbed_frame(
    backend: tuple[str, list[Message]],
) -> None:
    url, received = backend
    sink = BackendInputSink(url, agent_id="test", version="0")
    env = MuxedEnv(FakeSource(), sink)
    frame = env.grab()
    env.send_input(Key(t_mono_ns=5, frame_id=frame.frame_id, code="KeyA", action="down"))
    env.publish_detections(frame, [Box(x1=0, y1=0, x2=1, y2=1, cls="poring", conf=0.5)])

    _wait_for(lambda: len(received) >= 3)
    hello, batch, dets = received[:3]
    assert isinstance(hello, AgentHello)
    assert isinstance(batch, AgentInput)
    assert (batch.frame_id, batch.t_capture_ns) == (frame.frame_id, frame.t_capture_ns)
    assert isinstance(dets, Detections) and dets.boxes[0].cls == "poring"

    _wait_for(lambda: env.status() is not None and sink.acked_accepted == 1)
    status = env.status()
    assert status is not None and status.mode is Mode.BOT
    env.close()


def test_input_is_dropped_not_queued_when_backend_is_down() -> None:
    sink = BackendInputSink("ws://127.0.0.1:9", agent_id="test", version="0", open_timeout=0.5)
    assert (
        sink.send_batch([Key(t_mono_ns=1, code="KeyA", action="down")], frame_id=0, t_capture_ns=0)
        is False
    )
    assert not sink.connected
