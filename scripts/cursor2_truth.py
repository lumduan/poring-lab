#!/usr/bin/env python3
"""cursor@2 (docs/demonstrations.md 3.36): the BLIND labelling sets, built from the live sessions'
`cursor_eval.py live` outputs, BEFORE any bar is computed. No reader output on any page.

    cursor2_truth.py sheets --live DIR --out DIR SESSION_DIR...

Two sets, each shuffled with its own pre-registered seed:
- IMAGES (`items.json`, pages `p###.png`, 50 per page): grab 0 of EVERY crop, and every other grab a
  read came from (the gate's and the robust reader's first read in grabs 0-2 and the re-read in
  grabs 3-5; robust2 reads the same grabs): the exact image each read judged (cursor@1's lesson).
  Labels: walk, talk, sword, pickup, noentry, warp, none, unclear.
- SERIES (`strips.json`, pages `s###.png`, 10 per page): every series robust2 calls WALK, plus as
  many series it does not call WALK (seeded sample, so a strip's presence says nothing), each as
  its 6 grabs side by side. The question: does ANY grab show the no-entry sign? yes / no / unclear.

Client pixels: the pages stay in /dev/shm (rule 7), never in git.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path
from typing import Any

import numpy as np

ITEM_SEED = 20261185
STRIP_SEED = 20261186
PER_PAGE, COLS, ZOOM = 50, 10, 2
STRIPS_PER_PAGE = 10
READERS = ("current", "robust")


def read_grabs(shapes: list[str]) -> list[int]:
    """The grabs a reader's two reads came from: the first non-unknown of 0-2 and of 3-5."""
    out = []
    for lo, hi in ((0, 3), (3, 6)):
        g = next((i for i in range(lo, hi) if shapes[i] != "unknown"), None)
        if g is not None:
            out.append(g)
    return out


def image_items(lives: dict[str, dict[str, Any]], seed: int = ITEM_SEED) -> list[list[Any]]:
    items: list[list[Any]] = []
    for ses, live in sorted(lives.items()):
        need: set[tuple[str, int]] = set()
        for r in live["rows"]:
            need.add((r["crop"], 0))
            for name in READERS:
                need.update((r["crop"], g) for g in read_grabs(r[name]["shapes"]))
        items += [[ses, c, g] for c, g in sorted(need)]
    random.Random(seed).shuffle(items)
    return items


def strip_items(lives: dict[str, dict[str, Any]], seed: int = STRIP_SEED) -> list[list[Any]]:
    """Every robust2 WALK series + an equal seeded sample of the others, shuffled."""
    walk, other = [], []
    for ses, live in sorted(lives.items()):
        for r in live["rows"]:
            (walk if r["robust2"]["twice"] == "walk" else other).append([ses, r["crop"]])
    rng = random.Random(seed)
    sample = rng.sample(other, min(len(walk), len(other)))
    items = walk + sample
    rng.shuffle(items)
    return items


def _tile(arr: Any, zoom: int = ZOOM) -> Any:
    from PIL import Image

    rgb = np.ascontiguousarray(np.asarray(arr)[..., ::-1]).astype(np.uint8)  # BGR -> RGB
    t = 64 * zoom
    return Image.fromarray(rgb).resize((t, t), Image.NEAREST)


def write_pages(items: list[list[Any]], strips: list[list[Any]], root: Path, out: Path) -> None:
    from PIL import Image, ImageDraw

    t = 64 * ZOOM
    for page in range(0, len(items), PER_PAGE):
        sub = items[page : page + PER_PAGE]
        rows = (len(sub) + COLS - 1) // COLS
        sheet = Image.new("RGB", (COLS * (t + 4), rows * (t + 16)), (40, 40, 40))
        dr = ImageDraw.Draw(sheet)
        for j, (ses, crop, g) in enumerate(sub):
            a = np.load(root / ses / crop)["a_series"][g]
            x, y = (j % COLS) * (t + 4), (j // COLS) * (t + 16)
            sheet.paste(_tile(a), (x, y + 14))
            dr.text((x + 2, y + 1), str(page + j), fill=(255, 255, 0))
        sheet.save(out / f"p{page // PER_PAGE:03d}.png")
    for page in range(0, len(strips), STRIPS_PER_PAGE):
        sub = strips[page : page + STRIPS_PER_PAGE]
        sheet = Image.new("RGB", (6 * (t + 4) + 60, len(sub) * (t + 6)), (40, 40, 40))
        dr = ImageDraw.Draw(sheet)
        for j, (ses, crop) in enumerate(sub):
            z = np.load(root / ses / crop)["a_series"]
            y = j * (t + 6)
            dr.text((4, y + t // 2), str(page + j), fill=(255, 255, 0))
            for g in range(6):
                sheet.paste(_tile(z[g]), (60 + g * (t + 4), y))
        sheet.save(out / f"s{page // STRIPS_PER_PAGE:03d}.png")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)  # fmt: skip
    ap.add_argument("mode", choices=("sheets",))
    ap.add_argument("--live", type=Path, required=True, help="cursor_eval.py live --out DIR")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("sessions", nargs="+", type=Path)
    a = ap.parse_args()
    lives = {s.name: json.loads((a.live / f"live-{s.name}.json").read_text()) for s in a.sessions}
    roots = {s.parent for s in a.sessions}
    if len(roots) != 1:
        print("cursor2_truth: the sessions must share one root", file=sys.stderr)
        return 2
    items, strips = image_items(lives), strip_items(lives)
    a.out.mkdir(parents=True, exist_ok=True)
    (a.out / "items.json").write_text(json.dumps(items))
    (a.out / "strips.json").write_text(json.dumps(strips))
    write_pages(items, strips, roots.pop(), a.out)
    pages = (len(items) + PER_PAGE - 1) // PER_PAGE
    spages = (len(strips) + STRIPS_PER_PAGE - 1) // STRIPS_PER_PAGE
    print(json.dumps({"images": len(items), "image_pages": pages, "strips": len(strips),
                      "strip_pages": spages}))  # fmt: skip
    return 0


if __name__ == "__main__":
    sys.exit(main())
