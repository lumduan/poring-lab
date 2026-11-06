#!/usr/bin/env python3
"""T2's MULTI-VIEW REFERENCE SHEET on its own (docs/planning/xmas02-detector.md 6, tool gap T-10;
orcsdun01-detector.md 3l): the reference.png that ``map_labels.py pack`` puts in a blind pack,
built for a list of mob ids BEFORE any pack exists, to check that every listed species renders.

    reference_sheet.py --mobs 1249 1248 1265 1246 1515 1607 1251 1002 1062 \\
        --sprites DIR --sprite-names JSON --seed 51 --out PNG [--letters-out JSON]
    reference_sheet.py --preset xmas_dun02 --sprites DIR --sprite-names JSON --seed 51 --out PNG

The drawing is the pack's own, unchanged: ``orc_label_sheets.reference_sheet(..., views="multi")``
(the idle action in four directions, each at its first and middle frame, identical images once;
ACT tint applied, on mid grey, no name) under the letters of
``orc_label_sheets.letters_for(mobs, seed)``. ``map_labels.py pack`` draws the map spec's
``species`` then its ``reference``, in that order: pass ``--mobs`` in that order (``--preset
xmas_dun02`` is plan 6's list: Myst Case, Cruiser, Cookie, Christmas Cookie, Garm Baby, Christmas
Goblin, Stormy Knight, then Poring and Santa Poring) and the seed of the pack, and the letters are
the pack's.

The sprites are looked up by the CLIENT's stem (``--sprite-names``: a monster_sprite_names.json,
e.g. the merged one in /dev/shm/poring-lab-tmp/xmas-det/kb-sprites; Santa Poring 1062's stem is
``poring_``), never guessed: a listed species without a decoded SPR / ACT stops the build, and a
repeated id, an empty list or more ids than letters is refused.

The letters -> mob ids are ANSWER-KEY material (a labeller must never see them): they go to
``--letters-out`` only (keep it outside any pack); stdout prints the image size and the counts.
Client-derived: the sprites are read from /dev/shm at run time, the image is written where
``--out`` says (scratch, never the repository).
"""

from __future__ import annotations

import argparse
import json
import string
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import numpy as np
import numpy.typing as npt

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

# plan 6's reference for xmas_dun02: the map's species (1b; map_labels' spec order), then Poring
# and Santa Poring (the toy models' look-alike)
PRESETS: dict[str, tuple[int, ...]] = {
    "xmas_dun02": (1249, 1248, 1265, 1246, 1515, 1607, 1251, 1002, 1062),
}


def check_mobs(mobs: Sequence[int]) -> list[int]:
    """PURE: the list as drawn, or SystemExit (empty, a repeated id, more ids than letters)."""
    out = [int(m) for m in mobs]
    if not out:
        raise SystemExit("no species to draw")
    if len(set(out)) != len(out):
        raise SystemExit(f"a species is listed twice: {out}")
    if len(out) > len(string.ascii_uppercase):
        raise SystemExit(f"{len(out)} species: more than the {len(string.ascii_uppercase)} letters")
    return out


def build(mobs: Sequence[int], sprites: Path, sprite_names: Path, seed: int,
          views: str = "multi") -> tuple[npt.NDArray[np.uint8], dict[str, int]]:  # fmt: skip
    """(the reference image, letter -> mob id): map_labels.py pack's drawing for ``mobs``."""
    import orc_label_sheets as ols
    import qa_export

    mobs = check_mobs(mobs)
    if not sprite_names.exists():
        raise SystemExit(f"{sprite_names}: no sprite names table (the client stems)")
    sheets = qa_export.Sheets(sprites, stems=qa_export.sprite_stems(sprite_names), aegis={})
    missing = {m: sheets.stem(m)[1] for m in mobs if sheets(m) is None}
    if missing:
        raise SystemExit(f"no decoded sprite for {missing} in {sprites}: {sheets.missing}")
    letters = ols.letters_for(mobs, seed)
    rgb = ols.reference_sheet({m: sheets(m) for m in mobs}, letters, views=views)
    return np.asarray(rgb, dtype=np.uint8), letters


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    who = ap.add_mutually_exclusive_group(required=True)
    who.add_argument("--mobs", type=int, nargs="+", help="mob ids in the pack's order")
    who.add_argument("--preset", choices=sorted(PRESETS), help="a plan's list (xmas02 6)")
    ap.add_argument("--sprites", type=Path, required=True, help="the decoded SPR / ACT directory")
    ap.add_argument("--sprite-names", type=Path, required=True, help="monster_sprite_names.json")
    ap.add_argument("--seed", type=int, required=True, help="the pack's seed (its letters)")
    ap.add_argument("--views", choices=("multi", "one"), default="multi")
    ap.add_argument("--out", type=Path, required=True, help="the PNG (scratch, never the repo)")
    ap.add_argument("--letters-out", type=Path, default=None,
                    help="letters -> mob ids (ANSWER-KEY material: outside any pack)")  # fmt: skip
    a = ap.parse_args(argv)
    import orc_label_sheets as ols

    mobs = list(PRESETS[a.preset]) if a.preset else list(a.mobs)
    rgb, letters = build(mobs, a.sprites, a.sprite_names, a.seed, a.views)
    ols.save_png(a.out, rgb)
    if a.letters_out is not None:
        a.letters_out.parent.mkdir(parents=True, exist_ok=True)
        a.letters_out.write_text(json.dumps({"seed": a.seed, "letters": letters}, indent=1) + "\n")
    summary: dict[str, Any] = {
        "out": str(a.out),
        "size": [int(rgb.shape[1]), int(rgb.shape[0])],
        "species": len(mobs),
        "views": a.views,
        "seed": a.seed,
        "letters_out": None if a.letters_out is None else str(a.letters_out),
    }
    print(json.dumps(summary))
    return 0


if __name__ == "__main__":
    sys.exit(main())
