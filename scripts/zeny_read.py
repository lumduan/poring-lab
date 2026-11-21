"""The zeny from pixels (Batt 2026-11-21: "add SP, the weight as a %, and the zeny too: other jobs
need them, a mage, a merchant whose skill strikes with money").

The client draws ONE line at the bottom of the Basic Information window:
"Weight : 1028 / 2430  Zeny : 33,287". The weight readers (poring_env.weight: the lab's 7 px font;
hp_percent.read_weight_font: a client's own learned font) read its first "N / M". The zeny is the
LAST number on that line, after its label: digit runs (a run = ink columns split by a blank column)
at most DIGIT_GAP blank columns apart, with a comma between groups of three (a short run in the
band's lower half, its own shape: never a learned glyph), right after the label's colon (two
stacked dots) and a space. Shapes and digits only, no word is read (Batt 10-26 / 11-11: Thai and
Korean clients come; a letter may even look like a digit: the lab font's 'Z' reads as '2').

Pixels in, one integer out, or None with a reason; never a guess (rule 1: the screen only):
- an unread run inside the number, a digit-like run in the label, the number touching the line's
  end (the window's border may cut a long zeny), groups that are not 1-3 then 3s: None;
- two fresh frames must read the same value (``read_zeny``), as the weight's two reads.

DISPLAY ONLY (the Run's status line and its tiles): no decision of the runner reads it.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import numpy.typing as npt

Bin = npt.NDArray[np.bool_]

DIGIT_GAP = 3  # hp_percent's: at most this many blank columns between two runs of one number
COMMA_MAX_W = 3  # a comma's run is at most this wide ...
COMMA_MAX_H = 4  # ... and this tall, with its top in the band's lower half
MAX_DIGITS = 12  # rAthena caps zeny at 2,147,483,647 (10 digits)


@dataclass(frozen=True, slots=True)
class Run:
    x0: int  # the run's first column (band px)
    x1: int  # one past its last column
    kind: str | None  # a digit "0".."9", "," a comma, ":" a colon, None any other mark


@dataclass(frozen=True, slots=True)
class ZenyReading:
    value: int | None
    reason: str  # "ok", or why not


def is_colon(run: Bin) -> bool:
    """PURE: a colon's shape: narrow, its ink two stacked dots (two row groups, a blank row
    between)."""
    if run.shape[1] > COMMA_MAX_W:
        return False
    rows = run.any(axis=1)
    groups = int(np.count_nonzero(rows[1:] & ~rows[:-1])) + int(rows[0])
    return groups == 2


def is_comma(run: Bin, band_h: int) -> bool:
    """PURE: a comma's shape: narrow, short, its top in the band's lower half."""
    rows = np.flatnonzero(run.any(axis=1))
    if not rows.size or run.shape[1] > COMMA_MAX_W:
        return False
    return bool(rows[-1] - rows[0] + 1 <= COMMA_MAX_H and rows[0] >= band_h / 2)


def runs_of(band: Bin, x0: int, x1: int, font: Mapping[str, Bin],
            max_dist: float) -> list[Run]:  # fmt: skip
    """PURE: the band's ink runs between columns x0 and x1, each named: a digit of ``font`` (the
    same shape, at most ``max_dist`` of its pixels differing), a comma (its shape), or None."""
    cols = band[:, x0:x1].any(axis=0)
    out: list[Run] = []
    i = 0
    while i < len(cols):
        if not cols[i]:
            i += 1
            continue
        j = i
        while j < len(cols) and cols[j]:
            j += 1
        run = band[:, x0 + i : x0 + j]
        kind: str | None = None
        sc = sorted((float((run != g).mean()), ch) for ch, g in font.items()
                    if ch.isdigit() and g.shape == run.shape)  # fmt: skip
        if sc and sc[0][0] <= max_dist:
            kind = sc[0][1]
        elif is_comma(run, band.shape[0]):
            kind = ","
        elif is_colon(run):
            kind = ":"
        out.append(Run(x0 + i, x0 + j, kind))
        i = j
    return out


def parse(runs: Sequence[Run], end: int) -> ZenyReading:  # noqa: PLR0911
    """PURE: the zeny from the runs right of the weight's M (left to right), the line ending at
    column ``end``. The number is the last chain of digit / comma runs, each at most DIGIT_GAP
    blank columns from the next; before it a space (more than DIGIT_GAP) and the label's colon."""
    if not runs:
        return ZenyReading(None, "no_zeny")
    if runs[-1].x1 >= end - 1:
        return ZenyReading(None, "cut_off")  # ink touches the line's end: a long zeny is cut
    k = len(runs) - 1
    while (k > 0 and runs[k - 1].kind not in (None, ":")
           and runs[k].x0 - runs[k - 1].x1 <= DIGIT_GAP):  # fmt: skip
        k -= 1
    chain = runs[k:]
    if any(r.kind in (None, ":") for r in chain):
        return ZenyReading(None, "unread_mark")  # the last run is not a digit or a comma
    if chain[0].kind == "," or chain[-1].kind == ",":
        return ZenyReading(None, "grouping")
    if k == 0:
        return ZenyReading(None, "no_label")  # nothing before it: no label seen
    if runs[k].x0 - runs[k - 1].x1 <= DIGIT_GAP:
        return ZenyReading(None, "no_space")  # a mark touches the number: part may be hidden
    if runs[k - 1].kind != ":":
        return ZenyReading(None, "no_colon")  # the label's colon is not right before it
    text = "".join(str(r.kind) for r in chain)
    groups = text.split(",")
    if "," in text and (not 1 <= len(groups[0]) <= 3 or any(len(g) != 3 for g in groups[1:])):
        return ZenyReading(None, "grouping")
    digits = text.replace(",", "")
    if len(digits) > MAX_DIGITS:
        return ZenyReading(None, "too_long")
    if len(digits) > 1 and digits[0] == "0":
        return ZenyReading(None, "leading_zero")
    return ZenyReading(int(digits), "ok")


# --- the lab's client: poring_env.weight's 7 px font --------------------------------------------


def lab_font(glyphs: Any) -> dict[str, Bin]:
    """PURE: the weight glyphs' digits as run glyphs: each mean template at INK_PROB, cut to its
    ink columns (the band keeps the cell's rows)."""
    from poring_env import weight as wt

    out: dict[str, Bin] = {}
    for i, sym in enumerate(wt.SYMBOLS):
        if not sym.isdigit() or int(glyphs.counts[i]) <= 0:
            continue
        ink = np.asarray(glyphs.mean[i] >= wt.INK_PROB)
        cols = np.flatnonzero(ink.any(axis=0))
        if cols.size:
            out[sym] = ink[:, cols[0] : cols[-1] + 1]
    return out


LAB_MAX_DIST = 0.12  # hp_percent.MAX_DIST: at most this share of a glyph's pixels disagree


def read_lab(frame_bgr: Any, glyphs: Any, origin: tuple[int, int] | None = None) -> ZenyReading:
    """The zeny on a game-region frame, the lab's font: the weight must read (it places M's end
    and the band's rows), then the runs right of M."""
    from poring_env import weight as wt

    wr = wt.read_weight(frame_bgr, glyphs, origin)
    if wr.value is None or wr.label_at is None or not wr.glyphs:
        return ZenyReading(None, f"weight_{wr.reason}")
    x, y, w, h = wt.rect_at(origin)
    gray = wt.to_gray(wt.unbadge(np.asarray(frame_bgr)[y : y + h, x : x + w]))
    prob, _paper = wt.ink_probability(gray, glyphs.ink)
    lx, ly = wr.label_at
    ch, cw = glyphs.geometry.cell
    band = np.asarray(prob[ly : ly + ch] >= wt.INK_PROB)
    after = lx + glyphs.geometry.label[2] + wr.glyphs[-1].x + cw
    return parse(runs_of(band, after, band.shape[1], lab_font(glyphs), LAB_MAX_DIST), band.shape[1])


# --- another client: its own learned font (hp_percent's, 2026-11-20) ----------------------------


def read_font(frame_bgr: Any, font: Mapping[str, Bin]) -> ZenyReading:
    """The zeny on a game-region frame in a client's own font (hp_percent.client_fonts)."""
    import hp_percent as hpp

    band = hpp.ink(frame_bgr, hpp.WEIGHT_DY)
    span = hpp.weight_span(band, font)
    if span is None:
        return ZenyReading(None, "weight_unread")
    end = hpp.WEIGHT_SEARCH[1]
    return parse(runs_of(band, span[2], end, font, hpp.MAX_DIST), end)


# --- the run's read: the same path as gm_state._weight ------------------------------------------


def stable(readings: Sequence[ZenyReading]) -> int | None:
    """PURE: the value when every reading (fresh frames) read the same one; else None."""
    vals = [r.value for r in readings]
    return vals[0] if vals and vals[0] is not None and all(v == vals[0] for v in vals) else None


def read_zeny(frames: Sequence[Any], lab_glyphs: Path | None = None) -> tuple[int | None, str]:
    """The zeny on the runner's two weight frames (gm_state._frames): the lab's font first where
    gm_state._weight reads it, then this client's own fonts; (value, the reason of the first
    frame's last reading)."""
    import gm_state
    import hp_percent as hpp

    from poring_env import weight as wt

    why = "no_font"
    path = gm_state._path() if lab_glyphs is None else "rdp"
    gpath = lab_glyphs or (gm_state.r.ROOT / wt.DEFAULT_TEMPLATES if path == "rdp"
                           else gm_state._root(path) / wt.DEFAULT_TEMPLATES.name)  # fmt: skip
    if path == "rdp" or gpath.exists():
        glyphs = wt.load_weight_glyphs(gpath)
        reads = [read_lab(f, glyphs) for f in frames]
        if (v := stable(reads)) is not None:
            return v, "ok"
        why = reads[0].reason if reads else why
    for font in hpp.client_fonts().values():
        reads = [read_font(f, font) for f in frames]
        if (v := stable(reads)) is not None:
            return v, "ok"
        why = reads[0].reason if reads else why
    return None, why
