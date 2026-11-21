#!/usr/bin/env python3
"""The HP read from pixels for the Crusader's survival rules (docs/demonstrations.md 3.96b, S1b,
pre-registered 2026-10-21 18:57 BEFORE this was built): Basic Info prints the HP as a PERCENT right
of its bar ("95%" ... "1%"; the client's floor(100 x HP / MaxHP), checked on six diagnostic frames).
It is black text on the window's white, digits 6 px wide on a 7 px pitch from client x 173, rows
54-62, then a '%'. The bar's LENGTH (gm_vitals.hp_fraction) read only 49 % of reads within 5 %
(3.96 run log).

PIXELS ONLY at run time: ``read(client_bgr, glyphs)`` -> an int 0..100 or None. The glyphs are cut
OFFLINE from frames whose true HP the packets give (ground truth, never at decision time):

    hp_percent.py fit   FRAMES_DIR [--max-hp 5260] [--fresh-s 1.0]
    hp_percent.py prove FRAMES_DIR [--fresh-s 1.0]     the held-out frames (odd index): exact share

FRAMES_DIR holds game-region frames named NNNN-<grab t_ns>.jpg|png and the session's
packets.jsonl.gz (survive.py's diagnostic captures). A frame is LABELLED only where the server's
PERCENT was the same over +-STABLE_S around its grab (3.96b: "where the true percent is stable for
+-0.5 s"; the display lag sits inside that window). With --fresh-s, also only where the last
ABSOLUTE hp packet is that recent: the regen ticks (ZC_RECOVERY 0x0A27) are not decoded, so a stale
label can sit below the screen by one tick (+3 points at 155 HP; found 2026-10-21 19:1x on cap2).
Even-index frames fit, odd-index frames prove.
"""

from __future__ import annotations

import argparse
import gzip
import json
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import numpy as np
import numpy.typing as npt

ROOT = Path(__file__).resolve().parents[1]
GLYPHS = ROOT / "data" / "crusader" / "hp_pct_glyphs.npz"  # client pixels: gitignored
Y0, Y1 = 54, 63  # the text rows (client px, Basic Info at the origin)
X0 = 173  # the first digit's left column
PITCH, DW, PW = 7, 6, 11  # digit pitch, digit width, the '%' width
INK = 110  # grey below this = ink
MAX_DIST = 0.12  # a glyph matches when at most this share of its pixels disagree
STABLE_S = 0.5  # 3.96b's +-0.5 s
FRESH_S = 1.0  # the last ABSOLUTE hp packet at most this old (0x0A27 regen is not decoded)
AID = 2000002

Bin = npt.NDArray[np.bool_]


SP_DY = 14  # 2026-10-22: the SP percent prints one Basic Info line (14 px) below the HP's


def ink(client_bgr: Any, dy: int = 0) -> Bin:
    """PURE: the text band (``dy`` rows below the HP's: SP_DY = the SP line) as ink / paper."""
    g = np.asarray(client_bgr)[Y0 + dy : Y1 + dy, :, :3].astype(np.float32).mean(axis=2)
    return g < INK


def cells(band: Bin, k: int) -> tuple[list[Bin], Bin]:
    """PURE: the k digit cells and the '%' cell of a k-digit reading."""
    ds = [band[:, X0 + PITCH * i : X0 + PITCH * i + DW] for i in range(k)]
    p0 = X0 + PITCH * k
    return ds, band[:, p0 : p0 + PW]


def dist(a: Bin, b: Bin) -> float:
    return 1.0 if a.shape != b.shape else float((a != b).mean())


def read(client_bgr: Any, glyphs: Mapping[str, Bin], dy: int = 0) -> int | None:
    """The percent as an int, or None. The lab's glyphs first (``read_lab``, unchanged); when they
    read nothing, each of THIS client's own fonts (``client_fonts``: 2026-11-20, the live PC's
    client prints the percent in a thinner font -- digits 5 px on a 6 px pitch from x 175 -- so the
    lab's glyphs read None on every frame and the Run played HP-blind)."""
    got = read_lab(client_bgr, glyphs, dy)
    if got is not None:
        return got
    band = ink(client_bgr, dy)
    for font in client_fonts().values():
        got = read_font(band, font)
        if got is not None:
            return got
    return None


def read_lab(client_bgr: Any, glyphs: Mapping[str, Bin], dy: int = 0) -> int | None:
    """PURE: the percent as an int, or None (no layout of 1-3 digits + '%' matches; a value > 100;
    a leading zero). ``dy`` = SP_DY reads the SP line with the same glyphs (2026-10-22)."""
    band = ink(client_bgr, dy)
    best: tuple[float, int] | None = None
    for k in (1, 2, 3):
        ds, pc = cells(band, k)
        if "%" not in glyphs or dist(pc, glyphs["%"]) > MAX_DIST:
            continue
        txt, worst = "", dist(pc, glyphs["%"])
        for d in ds:
            sc = sorted((dist(d, g), ch) for ch, g in glyphs.items() if ch != "%")
            if not sc or sc[0][0] > MAX_DIST:
                break
            txt += sc[0][1]
            worst = max(worst, sc[0][0])
        else:
            if (len(txt) > 1 and txt[0] == "0") or int(txt) > 100:
                continue
            if best is None or worst < best[0]:
                best = (worst, int(txt))
    return None if best is None else best[1]


# --- this client's own fonts (2026-11-20): a variable-pitch reading -------------------------------
# A font is a set of glyphs cut from THIS client's screen by ``learn-font`` (a line whose text a
# person or the agent reads, e.g. Basic Info's "Weight : 1328 / 4200" or the percent itself): each
# glyph is the ink of one character, cropped to its own columns. The reading segments the percent's
# band into ink runs (columns with ink, split by an empty column) and names each run by the glyph of
# the SAME width that differs least (<= MAX_DIST); the last run must be '%'.
FONT_SEARCH = (X0 - 2, X0 + 44)  # the percent's columns in any font (the bar's end is at x 167-169)
FONT_PREFIX = "hp_pct_glyphs@"  # GLYPHS' folder: hp_pct_glyphs@<name>.npz (client pixels)
_FONTS: dict[str, tuple[float, dict[str, Bin]]] = {}


def runs(band: Bin, x0: int, x1: int) -> list[tuple[int, Bin]]:
    """PURE: the ink runs of ``band`` between columns x0 and x1: (left column, the run's ink)."""
    cols = band[:, x0:x1].any(axis=0)
    out: list[tuple[int, Bin]] = []
    i = 0
    while i < len(cols):
        if not cols[i]:
            i += 1
            continue
        j = i
        while j < len(cols) and cols[j]:
            j += 1
        out.append((x0 + i, band[:, x0 + i : x0 + j]))
        i = j
    return out


def name_run(run: Bin, font: Mapping[str, Bin]) -> tuple[str, float] | None:
    """PURE: the font's character whose glyph (the same width) differs least from ``run``, and by
    how much; None when none is within MAX_DIST."""
    sc = sorted((dist(run, g), ch) for ch, g in font.items() if g.shape == run.shape)
    return (sc[0][1], sc[0][0]) if sc and sc[0][0] <= MAX_DIST else None


def read_font(band: Bin, font: Mapping[str, Bin]) -> int | None:
    """PURE: the percent read with a client's own font, or None (an unknown run, no closing '%',
    a value over 100, a leading zero)."""
    rs = runs(band, *FONT_SEARCH)
    if len(rs) < 2:
        return None
    named = [name_run(r, font) for _x, r in rs]
    if any(n is None for n in named):
        return None
    txt = "".join(n[0] for n in named if n is not None)
    if not txt.endswith("%") or not txt[:-1].isdigit() or len(txt) > 4:
        return None
    if len(txt) > 2 and txt[0] == "0":
        return None
    v = int(txt[:-1])
    return v if v <= 100 else None


# 2026-11-20: the WEIGHT line in a client's own font -- "Weight : 1685 / 4200  Zeny : 33,287" on the
# live PC's client, rows 119-127 with Basic Info at the origin, in the percent's font (its 1, 0 and
# 5 matched when its 6 was cut from this line). The lab's weight reader (poring_env.weight) knows
# the lab's 7 px font only, so a live Run read no weight and its weight home could never fire.
# The line's runs: label letters (no digit), then N's digits (a '1' leaves 3 blank columns, others
# 1), the '/' (one run, no digit, 6+ rows tall, its top to the right of its bottom), M's digits.
# A number needs more than DIGIT_GAP blank columns on both sides: an unread glyph touching it means
# a digit is hidden (never a shorter number).
WEIGHT_DY = 65  # the weight line's band, this many rows below the HP's (119 - Y0)
WEIGHT_SEARCH = (30, 219)  # the box's columns, left of its right border
DIGIT_GAP = 3  # at most this many blank columns between two digits of one number
SLASH_ROWS = 6  # the '/' spans at least this many rows (a comma 2, a colon's dots apart)


def is_slash(run: Bin) -> bool:
    """PURE: a run drawn as '/': 2-6 columns, SLASH_ROWS+ rows, its top ink right of its bottom."""
    rows = np.where(run.any(axis=1))[0]
    if not 2 <= run.shape[1] <= 6 or len(rows) == 0 or rows[-1] - rows[0] + 1 < SLASH_ROWS:
        return False
    top = np.where(run[rows[0]])[0].mean()
    bottom = np.where(run[rows[-1]])[0].mean()
    return bool(top > bottom)


def read_weight_font(band: Bin, font: Mapping[str, Bin]) -> tuple[int, int] | None:
    """PURE: (N, M) from the weight line's band in a client's own font, or None: the FIRST
    "digits / digits" on the line (the zeny's "33,287" after it has a comma, never a '/')."""
    span = weight_span(band, font)
    return None if span is None else (span[0], span[1])


def weight_span(band: Bin, font: Mapping[str, Bin]) -> tuple[int, int, int] | None:
    """PURE: read_weight_font's (N, M) and the column one past M's last ink (2026-11-21: the zeny
    reader starts there, scripts/zeny_read.py), or None."""
    rs = runs(band, *WEIGHT_SEARCH)
    named = []
    for x, r in rs:
        n = name_run(r, font)
        named.append((x, x + r.shape[1], n[0] if n is not None and n[0].isdigit() else None, r))
    i = 0
    while i < len(named):
        if named[i][2] is None:
            i += 1
            continue
        j = i  # the digit group from i: digits, each at most DIGIT_GAP blank columns apart
        while (j + 1 < len(named) and named[j + 1][2] is not None
               and named[j + 1][0] - named[j][1] <= DIGIT_GAP):  # fmt: skip
            j += 1
        k = j + 1
        if i > 0 and named[i][0] - named[i - 1][1] <= DIGIT_GAP:
            i = k  # an unread glyph right before it: part of a number is hidden
            continue
        if k + 1 < len(named) and named[k][2] is None and is_slash(named[k][3]):
            m0 = m1 = k + 1
            if named[m0][2] is not None:
                while (m1 + 1 < len(named) and named[m1 + 1][2] is not None
                       and named[m1 + 1][0] - named[m1][1] <= DIGIT_GAP):  # fmt: skip
                    m1 += 1
                if m1 + 1 < len(named) and named[m1 + 1][0] - named[m1][1] <= DIGIT_GAP:
                    return None  # an unread glyph right after M: part of it is hidden
                a = "".join(str(t[2]) for t in named[i : j + 1])
                b = "".join(str(t[2]) for t in named[m0 : m1 + 1])
                ok_a = len(a) == 1 or a[0] != "0"
                if ok_a and b[0] != "0" and len(a) <= 6 and len(b) <= 6:
                    return int(a), int(b), int(named[m1][1])
            return None  # the first '/' on the line did not read: never a later pair
        i = k
    return None


def read_weight(client_bgr: Any) -> tuple[int, int] | None:
    """The weight line read with each of this client's own fonts (``client_fonts``), or None."""
    band = ink(client_bgr, WEIGHT_DY)
    for font in client_fonts().values():
        got = read_weight_font(band, font)
        if got is not None:
            return got
    return None


def client_fonts(folder: Path | None = None) -> dict[str, dict[str, Bin]]:
    """This client's fonts from GLYPHS' folder (re-read when a file changes; none -> {})."""
    folder = folder or GLYPHS.parent
    out: dict[str, dict[str, Bin]] = {}
    for p in sorted(folder.glob(f"{FONT_PREFIX}*.npz")):
        try:
            mt = p.stat().st_mtime
            cached = _FONTS.get(str(p))
            if cached is None or cached[0] != mt:
                z = np.load(p)
                cached = (mt, {("%" if k == "pct" else k[1:]): z[k].astype(bool) for k in z.files})
                _FONTS[str(p)] = cached
            out[p.stem[len(FONT_PREFIX) :]] = cached[1]
        except (OSError, ValueError, KeyError):
            continue  # a broken font file reads nothing (the lab's glyphs still do)
    return out


def learn_font(client_bgr: Any, row: int, x0: int, x1: int, text: str,
               font: dict[str, Bin]) -> dict[str, Any]:  # fmt: skip
    """Cut glyphs from one line of KNOWN text: the band at rows ``row`` .. ``row`` + (Y1 - Y0),
    columns x0..x1. Its ink runs must be exactly the text's characters (spaces are gaps, not runs),
    or nothing is learned. Only digits and '%' are kept; a character already in ``font`` must match
    it (<= MAX_DIST), else it is reported and kept as it was."""
    g = np.asarray(client_bgr)[row : row + (Y1 - Y0), :, :3].astype(np.float32).mean(axis=2)
    rs = runs(g < INK, x0, x1)
    chars = [c for c in text if not c.isspace()]
    if len(rs) != len(chars):
        return {"learned": [], "error": f"{len(rs)} ink runs for {len(chars)} characters"}
    learned, clashes = [], []
    for (_x, r), ch in zip(rs, chars, strict=True):
        if not (ch.isdigit() or ch == "%"):
            continue
        if ch in font:
            if dist(r, font[ch]) > MAX_DIST:
                clashes.append(ch)
            continue
        font[ch] = r
        learned.append(ch)
    return {"learned": learned, "clashes": clashes, "known": sorted(font)}


# --- offline: labels from the packets, the glyphs, the proof --------------------------------------


def hp_series(packets: Sequence[Mapping[str, Any]]) -> list[tuple[int, int]]:
    return sorted((int(e["t_mono_ns"]), int(e["value"])) for e in packets
                  if e.get("type") == "stat_change" and e.get("name") == "hp")  # fmt: skip


def stable_label(
    hp: Sequence[tuple[int, int]],
    t: int,
    max_hp: int,
    stable_s: float = STABLE_S,
    fresh_s: float | None = None,
) -> int | None:
    """PURE: floor(100 x HP / MaxHP) at ``t`` when that percent held over +-``stable_s`` around it
    (a value in force at the window's start, and every change inside it keeps the percent), else
    None."""
    w0, w1 = t - int(stable_s * 1e9), t + int(stable_s * 1e9)
    before = [v for ti, v in hp if ti <= w0]
    if not before:
        return None
    if fresh_s is not None:
        last = max((ti for ti, _v in hp if ti <= t), default=None)
        if last is None or t - last > int(fresh_s * 1e9):
            return None  # an unseen regen tick (ZC_RECOVERY 0x0A27, not decoded) may sit in between
    pcts = {int(100 * before[-1] // max_hp)} | {
        int(100 * v // max_hp) for ti, v in hp if w0 < ti <= w1
    }
    return pcts.pop() if len(pcts) == 1 else None


def load_frames(d: Path) -> list[tuple[int, Path]]:
    fs = [p for p in d.iterdir() if p.suffix in (".jpg", ".png") and "-" in p.stem]
    return sorted((int(p.stem.split("-")[1]), p) for p in fs)


def labelled(d: Path, max_hp: int, fresh_s: float | None = None) -> list[tuple[int, Path, int]]:
    with gzip.open(d / "packets.jsonl.gz", "rt") as fh:
        hp = hp_series([json.loads(x) for x in fh])
    out = []
    for i, (t, p) in enumerate(load_frames(d)):
        lab = stable_label(hp, t, max_hp, fresh_s=fresh_s)
        if lab is not None:
            out.append((i, p, lab))
    return out


def bgr(p: Path) -> Any:
    from PIL import Image

    return np.asarray(Image.open(p).convert("RGB"))[..., ::-1]


def fit(rows: Sequence[tuple[int, Path, int]]) -> dict[str, Bin]:
    acc: dict[str, list[Bin]] = {}
    for _i, p, lab in rows:
        s = str(lab)
        ds, pc = cells(ink(bgr(p)), len(s))
        for ch, d in zip(s, ds, strict=True):
            acc.setdefault(ch, []).append(d)
        acc.setdefault("%", []).append(pc)
    return {ch: np.mean(v, axis=0) >= 0.5 for ch, v in acc.items()}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)  # fmt: skip
    ap.add_argument("cmd", choices=("fit", "prove", "learn-font"))
    ap.add_argument("frames", type=Path, help="fit/prove: the frames folder; learn-font: one frame")
    ap.add_argument("--font", default=None, help="learn-font: the font's name (this client's)")
    ap.add_argument(
        "--row", type=int, default=Y0, help="learn-font: the line's top row (client px)"
    )
    ap.add_argument("--x0", type=int, default=FONT_SEARCH[0])
    ap.add_argument("--x1", type=int, default=FONT_SEARCH[1])
    ap.add_argument("--text", default=None, help="learn-font: the line's text as the screen shows")
    ap.add_argument("--max-hp", type=int, default=5260)
    ap.add_argument("--glyphs", type=Path, default=GLYPHS)
    ap.add_argument(
        "--fresh-s",
        type=float,
        default=None,
        help="label only frames whose last absolute hp packet is this recent",
    )
    a = ap.parse_args()
    if a.cmd == "learn-font":
        if not a.font or a.text is None:
            raise SystemExit("learn-font needs --font NAME and --text")
        path = GLYPHS.parent / f"{FONT_PREFIX}{a.font}.npz"
        font = dict(client_fonts(GLYPHS.parent).get(a.font, {}))
        res = learn_font(bgr(a.frames), a.row, a.x0, a.x1, a.text, font)
        if res.get("learned"):
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_name(f".{path.stem}.tmp.npz")
            np.savez(tmp, **{("pct" if k == "%" else f"d{k}"): v for k, v in font.items()})
            tmp.replace(path)
        print(json.dumps({**res, "file": str(path)}))
        return 0 if not res.get("error") else 2
    rows = labelled(a.frames, a.max_hp, a.fresh_s)
    if a.cmd == "fit":
        g = fit([r for r in rows if r[0] % 2 == 0])
        a.glyphs.parent.mkdir(parents=True, exist_ok=True)
        np.savez(a.glyphs, **{("pct" if k == "%" else f"d{k}"): v for k, v in g.items()})
        print(json.dumps({"fit_frames": sum(r[0] % 2 == 0 for r in rows), "glyphs": sorted(g)}))
        return 0
    z = np.load(a.glyphs)
    glyphs = {("%" if k == "pct" else k[1:]): z[k] for k in z.files}
    test = [r for r in rows if r[0] % 2 == 1]
    got = [(lab, read(bgr(p), glyphs)) for _i, p, lab in test]
    exact = sum(g == lab for lab, g in got)
    none = sum(g is None for _lab, g in got)
    wrong = [(lab, g) for lab, g in got if g is not None and g != lab]
    print(json.dumps({"held_out": len(got), "exact": exact,
                      "exact_share": round(exact / len(got), 4) if got else None, "none": none,
                      "wrong": wrong[:20], "glyphs": sorted(glyphs)}))  # fmt: skip
    return 0


if __name__ == "__main__":
    sys.exit(main())
