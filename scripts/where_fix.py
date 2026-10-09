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

TEMPLATES = r.ROOT / "data/where/chat_glyphs_rdp.npz"  # where@1 (strict colour, exact match)
TEMPLATES_V2 = r.ROOT / "data/where/chat_glyphs_rdp_v2.npz"  # where@2 (yellowish, majority)
CHAT_AREA = (0, 545, 640, 600)  # client px (x0, y0, x1, y1): the message area, frozen layout
YELLOW = np.array([104, 252, 255])  # BGR
COLOUR_TOL = 24
LINE_PITCH = 14
SETTLE_S = 0.6
STABLE_POLL_S, STABLE_MAX_S = 0.25, 4.0  # RDP progressive refines over frames: read a STABLE line


def text_mask(area_bgr: Any) -> Any:
    return np.abs(np.asarray(area_bgr)[..., :3].astype(int) - YELLOW).max(-1) <= COLOUR_TOL


def text_mask_v2(area_bgr: Any) -> Any:
    """where@2: YELLOWISH, not one colour. Over a bright scene behind the semi-transparent chat
    window the codec shifts the text to e.g. (255,255,68) or (240,249,65) -- whole rows of glyph
    pixels fell outside the strict window (where@1's 11 unparsed) -- while the darkened background
    stays near (151,127,110) (diagnosis, 2026-10-07 22:30)."""
    a = np.asarray(area_bgr)[..., :3].astype(int)
    b, g, red = a[..., 0], a[..., 1], a[..., 2]
    return (red > 170) & (g > 170) & (b < red - 70)


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


MATCH_MAX_D, MATCH_MARGIN = 4, 4  # where@2: nearest template, at most 4 px off, 4 px clear
SPACE_COLS = 3  # the space between ':' and X: at least this many empty columns
PLAUSIBLE_CELLS = 6  # a fix farther than this from the dead-reckoned belief is rejected
FIX_TRIES = 3  # pairs of /where reads before giving up (no fix, never a guess)
# The client refuses "the same word/phrase more than 3 times" (red line, 23:25 design pilot): a
# 4th /where in a row is NOT printed. A read-only command between them breaks the repetition:
# /ex lists the whisper block list ("There is no block list.", cyan) and changes nothing.
SEPARATOR = "/ex"


def text_other(area_bgr: Any) -> Any:
    """The chat's OTHER message colours: pure red (the client's refusals), cyan (/ex), green
    (notices such as "Warped."). One dominant channel, which the darkened scene behind the window
    does not produce -- a generic "bright and colourful" mask also caught the scene (16 / 20 good
    reads refused, 23:30)."""
    a = np.asarray(area_bgr)[..., :3].astype(int)
    b, g, red = a[..., 0], a[..., 1], a[..., 2]
    is_red = (red > 200) & (g < 90) & (b < 90)
    is_cyan = (g > 200) & (b > 200) & (red < 90)
    is_green = (g > 200) & (red < 90) & (b < 90)
    return is_red | is_cyan | is_green


def newest_is_yellow(area_bgr: Any) -> bool:
    """The NEWEST line is the yellow one: no red / cyan / green line below it. Otherwise the newest
    yellow line is an OLD /where (a refused or missed one) -- never read it."""
    strict = np.nonzero(text_mask(area_bgr).sum(1))[0]
    if len(strict) == 0:
        return False
    other = np.nonzero(text_other(area_bgr).sum(1) >= 3)[0]
    return len(other) == 0 or int(other[-1]) <= int(strict[-1])


def newest_line_v2(area_bgr: Any) -> Any | None:
    """The newest line for where@2: LOCATED by the strict colour (clean of background: its rows and
    where the text ends), READ with the yellowish mask (which restores the glyph pixels a bright
    scene behind the chat window shifted). The yellowish mask alone let scattered background
    pixels merge every row into one 55-row "line" and put a blob after the text (22:40)."""
    strict = text_mask(area_bgr)
    rows = np.nonzero(strict.sum(1))[0]
    if len(rows) == 0:
        return None
    bottom = int(rows[-1])
    top = max(0, bottom - LINE_PITCH + 2)
    cols = np.nonzero(strict[top : bottom + 1].any(0))[0]
    band = text_mask_v2(area_bgr)[max(0, top - 1) : bottom + 2]
    out = np.zeros_like(band)
    out[:, : int(cols[-1]) + 2] = band[:, : int(cols[-1]) + 2]
    return out


def ink_box(g: Any) -> Any:
    """A glyph cropped to its own ink rows: vertical position never matters."""
    rows = np.nonzero(g.any(1))[0]
    return g[rows[0] : rows[-1] + 1] if len(rows) else g


def runs(line: Any) -> list[tuple[int, int]]:
    """(start, end) column runs of ink, specks under 3 px dropped."""
    cols = line.any(0)
    out, start = [], None
    for x, on in enumerate([*cols, False]):
        if on and start is None:
            start = x
        elif not on and start is not None:
            if int(line[:, start:x].sum()) >= 3:
                out.append((start, x))
            start = None
    return out


def match_v2(g: Any, templates: dict[str, Any]) -> str | None:
    """The nearest template by Hamming distance (both padded to the wider), if it is within
    MATCH_MAX_D and at least MATCH_MARGIN closer than the second nearest."""
    g = ink_box(g)
    ds = []
    for ch, t in templates.items():
        h, w = max(t.shape[0], g.shape[0]), max(t.shape[1], g.shape[1])
        a = np.zeros((h, w), bool)
        b = np.zeros((h, w), bool)
        a[: g.shape[0], : g.shape[1]] = g
        b[: t.shape[0], : t.shape[1]] = t
        ds.append((int((a != b).sum()), ch))
    ds.sort()
    if ds[0][0] <= MATCH_MAX_D and (len(ds) < 2 or ds[1][0] - ds[0][0] >= MATCH_MARGIN):
        return ds[0][1]
    return None


def parse_v2(area_bgr: Any, templates: dict[str, Any]) -> tuple[int, int] | None:
    """(X, Y) from the newest line: from the right, digits, ONE comma, digits, and then a SPACE
    (>= SPACE_COLS empty columns) before X -- a glyph that fails to match can never shorten a
    number (where@1's 109 -> 9)."""
    line = newest_line_v2(area_bgr)
    if line is None:
        return None
    rs = runs(line)
    text: list[str] = []
    for k in range(len(rs) - 1, -1, -1):
        ch = match_v2(line[:, rs[k][0] : rs[k][1]], templates)
        if ch is None:
            return None  # an unreadable glyph inside "X, Y" (or right after it): no fix
        text.append(ch)
        s = "".join(reversed(text))
        if s.count(",") == 1 and s[0] != "," and k > 0 and rs[k][0] - rs[k - 1][1] >= SPACE_COLS:
            a, b = s.split(",")
            if a.isdigit() and b.isdigit() and 0 < len(a) <= 3 and 0 < len(b) <= 3:
                return int(a), int(b)
            return None
        if len(text) > 8:
            return None
    return None


def fix_v2(agent: Any, screen: Any, templates: dict[str, Any], belief: tuple[int, int],
           walkable: Any) -> dict[str, Any]:  # fmt: skip
    """SUPERSEDED for every NEW rule by `fix_once` (Batt 2026-10-09: no filler separators, /where
    once per need); kept as walk@11-16's frozen code. With the typing guard it can no longer type
    its "/ex" separator, so it now fails closed at that line.
    where@2: TWO consecutive /where reads that agree, each fresh (the stale guard), inside the
    map, on a GAT-walkable cell, within PLAUSIBLE_CELLS of the dead-reckoned belief. Up to
    FIX_TRIES pairs; otherwise no fix. Every rejection is logged by its gate."""
    import chat_guard

    rejects: list[str] = []
    for _ in range(FIX_TRIES):
        reads = []
        for _ in range(2):
            r.activate_client(agent, screen)
            try:
                r.chat_line(agent, screen, SEPARATOR)  # breaks the client's repetition refusal
                time.sleep(SETTLE_S)
                before = text_mask_v2(stable_area(screen))
                r.chat_line(agent, screen, "/where", reason="where_fix.fix_v2")
            except r.Stop as exc:
                rejects.append(f"chat: {exc}")
                break
            except chat_guard.ChatRefused as exc:  # the "/ex" separator is refused: no fix
                rejects.append(f"guard:{exc.rule}")
                break
            time.sleep(SETTLE_S)
            area = stable_area(screen)
            if bool((text_mask_v2(area) == before).all()):
                rejects.append("stale")
                break
            if not newest_is_yellow(area):
                rejects.append("not_newest")
                break
            reads.append(parse_v2(area, templates))
        if len(reads) < 2:
            continue
        a, b = reads
        if a is None or b is None:
            rejects.append("unparsed")
            continue
        if a != b:
            rejects.append("disagree")
            continue
        x, y = a
        if not (0 <= y < walkable.shape[0] and 0 <= x < walkable.shape[1]):
            rejects.append("off_map")
            continue
        if not walkable[y, x]:
            rejects.append("not_walkable")
            continue
        if max(abs(x - belief[0]), abs(y - belief[1])) > PLAUSIBLE_CELLS:
            rejects.append("implausible")
            continue
        return {"xy": (x, y), "rejects": rejects, "t": r.ns()}
    return {"xy": None, "rejects": rejects, "t": r.ns()}


def fix_once(agent: Any, screen: Any, templates: dict[str, Any], belief: tuple[int, int],
             walkable: Any, reason: str) -> dict[str, Any]:  # fmt: skip
    """where@3 (Batt 2026-10-09): ONE /where per need, the way a player types it. No separator line
    (where@2's "/ex" is refused by the typing guard), no second /where to confirm, no retype on a
    miss: the caller falls back to passive sources (the minimap readout, dead reckoning,
    landmarks) and may ask again only after the guard's long retry interval, within its run's
    /where budget. The one answer is read on a STABLE chat area (two identical grabs: a
    frame-level double read, nothing typed) and accepted only if it is fresh, the newest line,
    parsed exactly, on the map, on a walkable cell and within PLAUSIBLE_CELLS of ``belief``."""
    import chat_guard

    r.activate_client(agent, screen)
    before = text_mask_v2(stable_area(screen))
    try:
        r.chat_line(agent, screen, "/where", reason=reason)
    except chat_guard.ChatRefused as exc:
        return {"xy": None, "rejects": [f"guard:{exc.rule}"], "t": r.ns()}
    except r.Stop as exc:
        return {"xy": None, "rejects": [f"chat: {exc}"], "t": r.ns()}
    time.sleep(SETTLE_S)
    area = stable_area(screen)
    if bool((text_mask_v2(area) == before).all()):
        return {"xy": None, "rejects": ["stale"], "t": r.ns()}
    if not newest_is_yellow(area):
        return {"xy": None, "rejects": ["not_newest"], "t": r.ns()}
    xy = parse_v2(area, templates)
    if xy is None:
        return {"xy": None, "rejects": ["unparsed"], "t": r.ns()}
    x, y = xy
    if not (0 <= y < walkable.shape[0] and 0 <= x < walkable.shape[1]):
        return {"xy": None, "rejects": ["off_map"], "t": r.ns()}
    if not walkable[y, x]:
        return {"xy": None, "rejects": ["not_walkable"], "t": r.ns()}
    if max(abs(x - belief[0]), abs(y - belief[1])) > PLAUSIBLE_CELLS:
        return {"xy": None, "rejects": ["implausible"], "t": r.ns()}
    return {"xy": (x, y), "rejects": [], "t": r.ns()}


def cut_v2(labels: Path) -> int:
    """Design time: where@2 templates under the yellowish mask, the per-pixel MAJORITY of every
    instance of each glyph (labels.json as for cut)."""
    inst: dict[str, list[Any]] = {}
    for row in json.loads(labels.read_text()):
        line = newest_line_v2(np.load(row["npy"]))
        assert line is not None, row
        rs = runs(line)
        text = f"{row['x']},{row['y']}"
        for ch, (a, b) in zip(text, rs[-len(text) :], strict=True):
            inst.setdefault(ch, []).append(ink_box(line[:, a:b]))
    out = {}
    for ch, gs in inst.items():
        h, w = max(g.shape[0] for g in gs), max(g.shape[1] for g in gs)
        stack = np.zeros((len(gs), h, w), bool)
        for i, g in enumerate(gs):
            stack[i, : g.shape[0], : g.shape[1]] = g
        maj = stack.mean(0) >= 0.5
        out[ch] = ink_box(maj)[:, : int(np.nonzero(maj.any(0))[0][-1]) + 1].astype(np.uint8)
    TEMPLATES_V2.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(TEMPLATES_V2, **out)
    print(json.dumps({"templates": sorted(out), "instances": {k: len(v) for k, v in inst.items()},
                      "out": str(TEMPLATES_V2)}))  # fmt: skip
    return 0


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
    """Type /where, read the answer: {"xy": (x, y) | None, "why": ..., "t": the read time}.
    STALE GUARD (2026-10-07 22:10): the chat area must CHANGE after typing -- if the /where line
    did not appear, the newest yellow line is the PREVIOUS answer, and reading it would be a
    confidently wrong fix. A chat input that will not open is no fix, never a crash."""
    r.activate_client(agent, screen)
    before = text_mask(stable_area(screen))
    try:
        r.chat_line(agent, screen, "/where", reason="where_fix.fix")
    except r.Stop as exc:
        return {"xy": None, "why": f"chat: {exc}", "t": r.ns()}
    time.sleep(SETTLE_S)
    area = stable_area(screen)
    if bool((text_mask(area) == before).all()):
        return {"xy": None, "why": "no new chat line", "t": r.ns()}
    xy = parse(area, templates)
    return {"xy": xy, "why": None if xy else "unparsed", "t": r.ns()}


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
    if len(sys.argv) == 3 and sys.argv[1] == "cut-v2":
        sys.exit(cut_v2(Path(sys.argv[2])))
    raise SystemExit(__doc__)
