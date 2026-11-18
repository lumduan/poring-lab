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


def find(
    bgra: NDArray[np.uint8], ref: NDArray[np.float32], *, keep: int = 5
) -> tuple[float, int, int]:
    """Where in ``bgra`` the signature ``ref`` is best (distance, x, y of its box's origin): a
    coarse slide of ``ref`` over the picture's own thumbnail (``SIG_SCALE``-px steps), then a
    pixel-exact refinement around the ``keep`` best (docs/planning/fullscreen-client.md: a panel
    found by its picture, wherever a screen size or the player put it). Infinite when it does not
    fit."""
    from numpy.lib.stride_tricks import sliding_window_view

    th, tw = ref.shape
    bh, bw = th * SIG_SCALE, tw * SIG_SCALE
    h, w = bgra.shape[:2]
    if h < bh - SIG_SCALE + 1 or w < bw - SIG_SCALE + 1:
        return float("inf"), 0, 0
    grid = grey_thumb(bgra)
    if grid.shape[0] < th or grid.shape[1] < tw:
        return float("inf"), 0, 0
    windows = sliding_window_view(grid, (th, tw))
    coarse = np.abs(windows - ref).mean(axis=(2, 3))
    order = np.argsort(coarse, axis=None)[:keep]
    best = (float("inf"), 0, 0)
    for flat in order:
        gy, gx = divmod(int(flat), coarse.shape[1])
        for y in range(max(0, gy * SIG_SCALE - SIG_SCALE), gy * SIG_SCALE + SIG_SCALE + 1):
            for x in range(max(0, gx * SIG_SCALE - SIG_SCALE), gx * SIG_SCALE + SIG_SCALE + 1):
                crop = bgra[y : y + bh, x : x + bw]
                d = distance(grey_thumb(crop), ref)
                if d < best[0]:
                    best = (d, x, y)
    return best
