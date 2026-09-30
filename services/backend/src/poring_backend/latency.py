"""Phase 0 latency instrumentation (docs/phase0-latency.md): in-memory rings, never disk.

Everything is converted to the backend's CLOCK_MONOTONIC (ns). Script clients on this host already
share it. A browser tab reports ``ViewerTiming``, whose ``offset_ns`` (Cristian's algorithm on its
min-RTT ping) maps its clock onto ours, with ``offset_uncertainty_ns`` (half that RTT) as the
error bar. Segments:

  inputs   sent (sender) -> arrival -> decided (mux) -> injected (XTest synced)
  frames   captured -> encoded -> sent (first viewer)
  viewers  sent -> received -> decoded -> painted (tab clock, converted)
"""

import statistics
from collections import deque
from dataclasses import asdict, dataclass
from typing import Any, Literal

from poring_env.protocol import FrameMeta, ViewerTiming

Clock = Literal["host", "browser", "unknown"]


@dataclass(slots=True)
class InputRecord:
    kind: str  # "key:KeyA:down", "mouse_move", ...
    clock: Clock
    t_sent: int  # the sender's t_mono_ns, on the sender's clock
    t_sent_host: int | None  # the same moment on our clock (None if unknown)
    t_arrival: int
    t_decided: int | None = None
    t_injected: int | None = None
    accepted: bool | None = None


@dataclass(slots=True)
class FrameRecord:
    frame_id: int
    t_capture: int
    t_encoded: int
    t_sent: int | None = None


@dataclass(slots=True)
class ViewerFrame:
    frame_id: int
    t_recv: int  # our clock
    t_decoded: int
    t_painted: int
    uncertainty_ns: int
    user_agent: str


def pct(values: list[float], q: int) -> float | None:
    if not values:
        return None
    if len(values) == 1:
        return round(values[0], 2)
    return round(statistics.quantiles(values, n=100, method="inclusive")[q - 1], 2)


def p50_p95(values: list[float]) -> dict[str, float | int | None]:
    return {"p50": pct(values, 50), "p95": pct(values, 95), "n": len(values)}


class LatencyRecorder:
    def __init__(self, capacity: int = 4096) -> None:
        self.inputs: deque[InputRecord] = deque(maxlen=capacity)
        self.frames: dict[int, FrameRecord] = {}
        self._frame_order: deque[int] = deque()
        self._capacity = capacity
        self.viewer: deque[ViewerFrame] = deque(maxlen=capacity)
        self.viewer_offset_uncertainty_ns: int | None = None
        self.viewer_user_agent = ""

    # --- inputs -----------------------------------------------------------------------------------

    def input_received(
        self, kind: str, t_sent: int, t_arrival: int, clock: Clock, offset_ns: int | None
    ) -> InputRecord:
        host: int | None = None
        if clock == "host":
            host = t_sent
        elif clock == "browser" and offset_ns is not None:
            host = t_sent + offset_ns
        record = InputRecord(kind, clock, t_sent, host, t_arrival)
        self.inputs.append(record)
        return record

    # --- frames -----------------------------------------------------------------------------------

    def frame_encoded(self, meta: FrameMeta) -> None:
        self.frames[meta.frame_id] = FrameRecord(
            meta.frame_id, meta.t_capture_ns, meta.t_encoded_ns
        )
        self._frame_order.append(meta.frame_id)
        while len(self._frame_order) > self._capacity:
            self.frames.pop(self._frame_order.popleft(), None)

    def frame_sent(self, frame_id: int, t_sent: int) -> None:
        record = self.frames.get(frame_id)
        if record is not None and record.t_sent is None:
            record.t_sent = t_sent

    # --- viewers ----------------------------------------------------------------------------------

    def viewer_timing(self, msg: ViewerTiming) -> None:
        self.viewer_user_agent = msg.user_agent
        if msg.offset_ns is None or msg.offset_uncertainty_ns is None:
            return
        self.viewer_offset_uncertainty_ns = msg.offset_uncertainty_ns
        for f in msg.frames:
            self.viewer.append(
                ViewerFrame(
                    f.frame_id,
                    f.recv_ns + msg.offset_ns,
                    f.decoded_ns + msg.offset_ns,
                    f.painted_ns + msg.offset_ns,
                    msg.offset_uncertainty_ns,
                    msg.user_agent,
                )
            )

    # --- reports ----------------------------------------------------------------------------------

    def summary(self, window_ns: int, now: int) -> dict[str, Any]:
        """p50/p95 in ms over the last ``window_ns``, for /health."""
        since = now - window_ns
        ms = 1e6
        net, decode, paint, send_paint, capture_paint = [], [], [], [], []
        for v in self.viewer:
            if v.t_painted < since:
                continue
            decode.append((v.t_decoded - v.t_recv) / ms)
            paint.append((v.t_painted - v.t_decoded) / ms)
            frame = self.frames.get(v.frame_id)
            if frame is not None:
                capture_paint.append((v.t_painted - frame.t_capture) / ms)
                if frame.t_sent is not None:
                    net.append((v.t_recv - frame.t_sent) / ms)
                    send_paint.append((v.t_painted - frame.t_sent) / ms)
        encode, queue = [], []
        for f in self.frames.values():
            if f.t_capture < since:
                continue
            encode.append((f.t_encoded - f.t_capture) / ms)
            if f.t_sent is not None:
                queue.append((f.t_sent - f.t_encoded) / ms)
        l1: dict[str, list[float]] = {"browser": [], "host": []}
        for i in self.inputs:
            if i.t_arrival < since or i.t_injected is None or i.t_sent_host is None:
                continue
            if i.clock in l1:
                l1[i.clock].append((i.t_injected - i.t_sent_host) / ms)
        unc = self.viewer_offset_uncertainty_ns
        return {
            "window_s": window_ns / 1e9,
            "encode_ms": p50_p95(encode),
            "send_queue_ms": p50_p95(queue),
            "viewer_net_ms": p50_p95(net),
            "viewer_decode_ms": p50_p95(decode),
            "viewer_paint_wait_ms": p50_p95(paint),
            "viewer_send_to_paint_ms": p50_p95(send_paint),
            "viewer_capture_to_paint_ms": p50_p95(capture_paint),
            "viewer_offset_uncertainty_ms": None if unc is None else round(unc / ms, 2),
            "viewer_user_agent": self.viewer_user_agent,
            "input_to_xtest_ms": {k: p50_p95(v) for k, v in l1.items()},
        }

    def dump(self, since_ns: int) -> dict[str, Any]:
        """Raw records newer than ``since_ns`` (our clock), for scripts/latency_probe.py."""
        return {
            "inputs": [asdict(i) for i in self.inputs if i.t_arrival >= since_ns],
            "frames": [asdict(f) for f in self.frames.values() if f.t_capture >= since_ns],
            "viewer": [asdict(v) for v in self.viewer if v.t_painted >= since_ns],
        }
