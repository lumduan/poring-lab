"""H.264 decode ONCE, in-process: Annex-B access units (moonlight-common-c's decode units) -> PyAV
-> numpy BGRA frames, plus the numbers the clean room records (time to first frame, fps, decode
latency, decode CPU). av/numpy are imported lazily so the host tests run without them."""

from __future__ import annotations

import collections
import resource
import time
from dataclasses import dataclass, field
from typing import Any

AV_CODEC_FLAG_LOW_DELAY = 1 << 19  # libavcodec/avcodec.h


@dataclass
class DecodeStats:
    started_ns: int = field(default_factory=time.monotonic_ns)
    first_frame_ns: int = 0
    frames: int = 0
    units: int = 0
    errors: int = 0
    width: int = 0
    height: int = 0
    cpu_s: float = 0.0
    decode_ms: collections.deque[float] = field(
        default_factory=lambda: collections.deque(maxlen=600)
    )
    recent_ns: collections.deque[int] = field(default_factory=lambda: collections.deque(maxlen=90))

    def snapshot(self) -> dict[str, Any]:
        ms = sorted(self.decode_ms)
        fps = 0.0
        if len(self.recent_ns) >= 2:
            span = (self.recent_ns[-1] - self.recent_ns[0]) / 1e9
            fps = (len(self.recent_ns) - 1) / span if span > 0 else 0.0

        def pct(p: float) -> float | None:
            return round(ms[min(len(ms) - 1, int(p * len(ms)))], 2) if ms else None

        return {
            "first_frame_s": (
                round((self.first_frame_ns - self.started_ns) / 1e9, 3)
                if self.first_frame_ns
                else None
            ),
            "frames": self.frames,
            "decode_units": self.units,
            "decode_errors": self.errors,
            "size": f"{self.width}x{self.height}" if self.width else None,
            "fps_recent": round(fps, 2),
            "decode_ms_p50": pct(0.5),
            "decode_ms_p95": pct(0.95),
            "decode_cpu_s": round(self.cpu_s, 2),
        }


def versions() -> dict[str, str]:
    """PyAV + libavcodec/libswscale versions: a recorded bitstream's determinism is only claimed for
    the same decoder build (h264check.py records the same)."""
    import av

    libs = getattr(av, "library_versions", {}) or {}
    out = {"pyav": str(av.__version__)}
    for name in ("libavcodec", "libswscale", "libavutil"):
        if name in libs:
            out[name] = ".".join(str(v) for v in libs[name])
    return out


class Decoder:
    def __init__(self, threads: int = 2) -> None:
        import av  # lazy: an image-only dependency

        self.ctx = av.CodecContext.create("h264", "r")
        self.ctx.flags |= AV_CODEC_FLAG_LOW_DELAY
        self.ctx.thread_type = "SLICE"
        self.ctx.thread_count = threads
        self._packet = av.Packet
        self.stats = DecodeStats()

    @property
    def low_delay(self) -> bool:
        return bool(int(self.ctx.flags) & AV_CODEC_FLAG_LOW_DELAY)

    def decode(self, access_unit: bytes) -> list[Any]:
        """One complete access unit (Annex B) -> the BGRA frames it yields (usually one)."""
        cpu0 = resource.getrusage(resource.RUSAGE_THREAD)
        t0 = time.monotonic_ns()
        out: list[Any] = []
        self.stats.units += 1
        try:
            for frame in self.ctx.decode(self._packet(access_unit)):
                out.append(frame.to_ndarray(format="bgra"))
        except Exception:  # noqa: BLE001 -- a corrupt unit: count it, ask for an IDR upstream
            self.stats.errors += 1
            raise
        finally:
            cpu1 = resource.getrusage(resource.RUSAGE_THREAD)
            self.stats.cpu_s += (cpu1.ru_utime - cpu0.ru_utime) + (cpu1.ru_stime - cpu0.ru_stime)
        now = time.monotonic_ns()
        if out:
            self.stats.decode_ms.append((now - t0) / 1e6)
            for frame in out:
                self.stats.frames += 1
                self.stats.recent_ns.append(now)
                if not self.stats.first_frame_ns:
                    self.stats.first_frame_ns = now
                self.stats.height, self.stats.width = frame.shape[0], frame.shape[1]
        return out
