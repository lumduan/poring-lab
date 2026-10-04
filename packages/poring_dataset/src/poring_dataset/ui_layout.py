"""The RO client's fixed UI windows, client-area pixels (x, y, w, h), on the FROZEN 1280x720 layout
(docs/client/rathena-client.md; measured 2026-10-02 for the projection's click grid).

Entities behind these windows are not visible, so an auto-label there is wrong (seen on the
2026-10-04 indoor set's sheet): labels drop a box mostly covered by them. One source for both
users (scripts/calibrate_projection.py never clicks there).
"""

# Basic Information (expanded), the 4-row hotkey bar, the small top window, the chat window, the
# right-anchored notifier and the minimap (outdoor maps).
UI_RECTS: tuple[tuple[int, int, int, int], ...] = (
    (0, 0, 222, 325), (228, 0, 296, 135), (655, 0, 90, 40), (0, 528, 600, 98),
    (965, 560, 175, 36), (1128, 8, 152, 152),
)  # fmt: skip


def covered_fraction(box: tuple[float, float, float, float],
                     rects: tuple[tuple[int, int, int, int], ...] = UI_RECTS) -> float:  # fmt: skip
    """The share of ``box`` (x0, y0, x1, y1) under the UI windows (rectangles may overlap each
    other only at their edges on this layout, so the sum is close enough)."""
    x0, y0, x1, y1 = box
    area = max(0.0, x1 - x0) * max(0.0, y1 - y0)
    if area <= 0:
        return 0.0
    covered = 0.0
    for rx, ry, rw, rh in rects:
        ix = max(0.0, min(x1, rx + rw) - max(x0, rx))
        iy = max(0.0, min(y1, ry + rh) - max(y0, ry))
        covered += ix * iy
    return min(1.0, covered / area)
