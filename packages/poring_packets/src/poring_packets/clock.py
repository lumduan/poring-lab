"""Map kernel packet timestamps (CLOCK_REALTIME) onto the host's CLOCK_MONOTONIC.

Frames carry `t_mono_ns`. Kernel packet stamps are realtime. `realtime - monotonic` only changes
when the realtime clock is STEPPED (NTP slewing moves both clocks' rate together), so a paired
sample once a second gives the offset to sub-microsecond accuracy, and a jump between two
consecutive samples marks a step: each packet is mapped with the segment its timestamp falls in.
"""

import bisect
import time
from collections.abc import Callable
from dataclasses import dataclass, field

STEP_NS = 2_000_000  # an offset change above 2 ms between samples = a clock step


@dataclass(frozen=True)
class Sample:
    mono_ns: int  # midpoint of the paired monotonic reads
    real_ns: int
    read_ns: int  # m2 - m1: the pairing's own uncertainty

    @property
    def offset_ns(self) -> int:
        return self.real_ns - self.mono_ns


def take_sample(
    mono: Callable[[], int] = time.monotonic_ns, real: Callable[[], int] = time.time_ns
) -> Sample:
    m1 = mono()
    r = real()
    m2 = mono()
    return Sample(mono_ns=(m1 + m2) // 2, real_ns=r, read_ns=m2 - m1)


@dataclass
class ClockMap:
    """Realtime -> monotonic, from 1 Hz samples. Keeps the last `keep` samples."""

    keep: int = 7200
    samples: list[Sample] = field(default_factory=list)
    steps: int = 0

    def add(self, sample: Sample) -> bool:
        """Record a sample; returns True if it reveals a realtime clock step."""
        stepped = (
            bool(self.samples) and abs(sample.offset_ns - self.samples[-1].offset_ns) > STEP_NS
        )
        self.steps += stepped
        self.samples.append(sample)
        if len(self.samples) > self.keep:
            del self.samples[: len(self.samples) - self.keep]
        return stepped

    def to_mono(self, real_ns: int) -> int:
        """Monotonic time of a realtime stamp, using the offset of the segment it falls in."""
        if not self.samples:
            raise ValueError("no clock samples yet")
        reals = [s.real_ns for s in self.samples]
        i = bisect.bisect_right(reals, real_ns) - 1
        return real_ns - self.samples[max(i, 0)].offset_ns
