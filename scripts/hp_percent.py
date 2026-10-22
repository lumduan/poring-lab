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
    ap.add_argument("cmd", choices=("fit", "prove"))
    ap.add_argument("frames", type=Path)
    ap.add_argument("--max-hp", type=int, default=5260)
    ap.add_argument("--glyphs", type=Path, default=GLYPHS)
    ap.add_argument(
        "--fresh-s",
        type=float,
        default=None,
        help="label only frames whose last absolute hp packet is this recent",
    )
    a = ap.parse_args()
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
