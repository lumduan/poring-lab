"""One screen grab and cheap views onto its pixels."""

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray


@dataclass(frozen=True, slots=True)
class Frame:
    """A captured frame. ``bgra`` holds tightly packed BGRA rows exactly as X returns them."""

    frame_id: int
    t_capture_ns: int
    width: int
    height: int
    bgra: bytes

    def __post_init__(self) -> None:
        expected = self.width * self.height * 4
        if len(self.bgra) != expected:
            raise ValueError(
                f"frame {self.frame_id}: got {len(self.bgra)} bytes, expected {expected} "
                f"for {self.width}x{self.height} BGRA"
            )

    def to_numpy(self) -> NDArray[np.uint8]:
        """Read-only HxWx4 BGRA view (no copy)."""
        return np.frombuffer(self.bgra, dtype=np.uint8).reshape(self.height, self.width, 4)

    def bgr(self) -> NDArray[np.uint8]:
        """Read-only HxWx3 BGR view -- the OpenCV / ultralytics convention (no copy)."""
        return self.to_numpy()[:, :, :3]
