#!/usr/bin/env python3
"""An ABSOLUTE position fix from the client's own /where line (Batt's idea, 2026-10-07 ~19:50).

    where_fix.py cut LABELS.json     (design time: cut the chat-font templates from labelled lines)

The client's /where prints `<display name>(<map>) : X, Y` in the chat window, in a flat yellow
bitmap font (RGB 255,252,104; no anti-aliasing), on a 14 px line pitch. Typing it goes through the
normal chat path (and so the typing-only foreground gate); no packet event appeared around it in
the design probe (2026-10-07 21:5x), so it reads as a client-side command. This reads the NEWEST
chat line from pixels and returns (X, Y): the bottom-most yellow line in the chat message area,
cut into glyphs on empty columns, the trailing `X, Y` matched against the templates (digits 0-9
and the comma). Anything that does not parse exactly is None -- never a guess.
Pixels in, keys out: no packets. The templates are client pixels: data/ (gitignored).
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ro_agent as r  # noqa: E402

TEMPLATES = r.ROOT / "data/where/chat_glyphs_rdp.npz"
CHAT_AREA = (0, 545, 640, 600)  # client px (x0, y0, x1, y1): the message area, frozen layout
YELLOW = np.array([104, 252, 255])  # BGR
COLOUR_TOL = 24
LINE_PITCH = 14
SETTLE_S = 0.6
STABLE_POLL_S, STABLE_MAX_S = 0.25, 4.0  # RDP progressive refines over frames: read a STABLE line


def text_mask(area_bgr: Any) -> Any:
    return np.abs(np.asarray(area_bgr)[..., :3].astype(int) - YELLOW).max(-1) <= COLOUR_TOL


def newest_line(mask: Any) -> Any | None:
    """The bottom-most text line (rows), one line pitch tall, or None."""
    rows = np.nonzero(mask.sum(1))[0]
    if len(rows) == 0:
        return None
    bottom = int(rows[-1])
    top = max(0, bottom - LINE_PITCH + 2)
    return mask[top : bottom + 1]


def glyphs(line: Any) -> list[Any]:
    """Column runs separated by empty columns, each cropped to the line's height."""
    cols = line.any(0)
    out, start = [], None
    for x, on in enumerate([*cols, False]):
        if on and start is None:
            start = x
        elif not on and start is not None:
            out.append(line[:, start:x])
            start = None
    return out


def match(g: Any, templates: dict[str, Any]) -> str | None:
    """The template equal to this glyph (same size, at most 1 pixel different), or None."""
    for ch, t in templates.items():
        if t.shape == g.shape and int((t != g).sum()) <= 1:
            return ch
    return None


def parse(area_bgr: Any, templates: dict[str, Any]) -> tuple[int, int] | None:
    """(X, Y) from the newest line's trailing `X, Y`, or None."""
    line = newest_line(text_mask(area_bgr))
    if line is None:
        return None
    chars: list[str | None] = [match(g, templates) for g in glyphs(line) if int(g.sum()) >= 3]
    tail: list[str] = []
    for ch in reversed(chars):
        if ch is None:
            break
        tail.append(ch)
    s = "".join(reversed(tail))
    if s.count(",") != 1:
        return None
    a, b = s.split(",")
    if not (a.isdigit() and b.isdigit() and 0 < len(a) <= 3 and 0 < len(b) <= 3):
        return None
    return int(a), int(b)


def load_templates(path: Path = TEMPLATES) -> dict[str, Any]:
    z = np.load(path)
    return {str(k): z[k].astype(bool) for k in z.files}


def stable_area(screen: Any) -> Any:
    """The chat area once its newest line stops changing: the RDP progressive codec sends a coarse
    picture first and refines it, and a grab ~1 s after the text appeared lost pixels of it
    (2026-10-07 design probe). Two consecutive identical newest lines, or the last grab after
    STABLE_MAX_S."""
    x0, y0, x1, y1 = CHAT_AREA
    gx, gy, _, _ = r.game_region()
    prev, area = None, None
    end = time.monotonic() + STABLE_MAX_S
    while True:
        area = screen.grab(gx + x0, gy + y0, x1 - x0, y1 - y0)[1][..., :3]
        line = newest_line(text_mask(area))
        same = line is not None and prev is not None and line.shape == prev.shape
        if same and bool((line == prev).all()):
            return area
        prev = line
        if time.monotonic() > end:
            return area
        time.sleep(STABLE_POLL_S)


def fix(agent: Any, screen: Any, templates: dict[str, Any]) -> dict[str, Any]:
    """Type /where, read the answer: {"xy": (x, y) | None, "t": the read time}."""
    r.activate_client(agent, screen)
    r.chat_line(agent, screen, "/where")
    time.sleep(SETTLE_S)
    area = stable_area(screen)
    return {"xy": parse(area, templates), "t": r.ns()}


def cut(labels: Path) -> int:
    """Design time: labels.json = [{"npy": a chat-area crop (BGR), "x": X, "y": Y}, ...]: the
    newest line's trailing glyphs are the digits of X, a comma, the digits of Y."""
    found: dict[str, Any] = {}
    for row in json.loads(labels.read_text()):
        area = np.load(row["npy"])
        line = newest_line(text_mask(area))
        assert line is not None, row
        gs = glyphs(line)
        text = f"{row['x']},{row['y']}"
        for ch, g in zip(text, gs[-len(text) :], strict=True):
            if ch in found and (found[ch].shape != g.shape or (found[ch] != g).sum() > 1):
                raise SystemExit(f"glyph {ch!r} differs between samples ({row})")
            found[ch] = g
    TEMPLATES.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(TEMPLATES, **{k: v.astype(np.uint8) for k, v in found.items()})
    print(json.dumps({"templates": sorted(found), "out": str(TEMPLATES)}))
    return 0


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "cut":
        sys.exit(cut(Path(sys.argv[2])))
    raise SystemExit(__doc__)
