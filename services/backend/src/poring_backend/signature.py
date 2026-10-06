"""Pixel signatures: is this screen region the picture we calibrated? ONE implementation for the
backend's typing-only foreground gate (foreground.py) and scripts/ro_agent.py.

A signature is a grey thumbnail of a small desktop box (every ``SIG_SCALE``-th pixel, BT.601
weights on BGRA). Two pictures match when their mean absolute grey difference is at most
``SIG_MATCH`` (0-255 scale). Measured on the lab client's active title bar: true matches score
0-2, an inactive title about 30, near misses about 10.
"""

import numpy as np
from numpy.typing import NDArray

SIG_SCALE = 8
SIG_MATCH = 6.0


def grey_thumb(bgra: NDArray[np.uint8]) -> NDArray[np.float32]:
    small = bgra[::SIG_SCALE, ::SIG_SCALE, :3].astype(np.float32)
    grey: NDArray[np.float32] = (
        small[..., 0] * 0.114 + small[..., 1] * 0.587 + small[..., 2] * 0.299
    ).astype(np.float32)
    return grey


def distance(thumb: NDArray[np.float32], ref: NDArray[np.float32]) -> float:
    """Mean absolute grey difference; infinite when the shapes differ (another box)."""
    if thumb.shape != ref.shape:
        return float("inf")
    return float(np.abs(thumb - ref).mean())
