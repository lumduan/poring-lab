#!/usr/bin/env python3
"""The by-eye check of a truth timing (xmas02-detector.md Amendment K, K2): MOVING captures drawn
with two truths and the detections, to judge which truth sits on the sprites.

    truth_draw.py SESSION_DIR --a PAIRS_120.json --b PAIRS_LSELF.json --out DIR [--n 12] [--seed 71]

``--a`` / ``--b`` are two ``detector_vs_packets.py score-session --pairs`` files of the SAME session
and boxes (e.g. the camera at 120 ms and at L_self). The pool: the captures that are MOVING in both
files and have at least one scored unit in --a; ``random.Random(seed).sample`` of ``--n`` (in time
order first). Each frame is drawn whole: --a's truth boxes RED, --b's GREEN, the kept detections
YELLOW. ``draw.json`` lists what was drawn; the judgement itself is a person's (or the report's)
reading of the PNGs. Offline only: packets are ground truth here, never an input of the bot.
"""

from __future__ import annotations

import argparse
import io
import json
import random
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

RED, GREEN, YELLOW = (255, 40, 40), (40, 230, 40), (255, 230, 0)


def load_pairs(path: Path) -> list[dict[str, Any]]:
    doc = json.loads(path.read_text())
    return list(doc if isinstance(doc, list) else doc["pairs"])


def pool(a: Sequence[dict[str, Any]], b: Sequence[dict[str, Any]]) -> list[int]:
    """PURE: the capture times moving in BOTH files with >= 1 scored unit in ``a``, sorted."""
    moving_b = {int(p["t"]) for p in b if p.get("moving")}
    return sorted(int(p["t"]) for p in a
                  if p.get("moving") and p.get("units") and int(p["t"]) in moving_b)  # fmt: skip


def draw_sample(times: Sequence[int], n: int, seed: int) -> list[int]:
    """PURE: ``n`` of ``times`` (all when fewer), by random.Random(seed).sample, in time order."""
    return sorted(random.Random(seed).sample(list(times), min(n, len(times))))


def boxes(pair: dict[str, Any]) -> list[list[float]]:
    return [[float(v) for v in u["box"][:4]] for u in pair.get("units") or []
            if u.get("box") is not None]  # fmt: skip


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)  # fmt: skip
    ap.add_argument("session", type=Path)
    ap.add_argument("--a", type=Path, required=True, help="pairs: truth drawn RED")
    ap.add_argument("--b", type=Path, required=True, help="pairs: truth drawn GREEN")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--n", type=int, default=12)
    ap.add_argument("--seed", type=int, default=71)
    a = ap.parse_args(argv)
    import recorder_boxes as rb
    from PIL import Image, ImageDraw

    pa, pb = load_pairs(a.a), load_pairs(a.b)
    by_a, by_b = {int(p["t"]): p for p in pa}, {int(p["t"]): p for p in pb}
    times = pool(pa, pb)
    pick = set(draw_sample(times, a.n, a.seed))
    a.out.mkdir(parents=True, exist_ok=True)
    manifest = json.loads((a.session / "manifest.json").read_text())
    rows = []
    for meta, png in rb.iter_session(a.session, manifest):
        t = int(meta["t_mono_ns"])
        if t not in pick:
            continue
        img = Image.open(io.BytesIO(png)).convert("RGB")
        d = ImageDraw.Draw(img)
        for colour, bs in (
            (RED, boxes(by_a[t])),
            (GREEN, boxes(by_b[t])),
            (YELLOW, [list(map(float, k[:4])) for k in by_a[t].get("kept") or []]),
        ):
            for x0, y0, x1, y1 in bs:
                d.rectangle([x0, y0, x1, y1], outline=colour, width=2)
        name = f"walk-{len(rows):02d}.png"
        img.save(a.out / name)
        rows.append({"png": name, "t": t, "frame_id": int(meta["frame_id"]),
                     "truth_a": boxes(by_a[t]), "truth_b": boxes(by_b[t]),
                     "verdicts_a": by_a[t].get("verdicts"),
                     "verdicts_b": by_b[t].get("verdicts")})  # fmt: skip
    (a.out / "draw.json").write_text(json.dumps(
        {"session": manifest.get("session_id"), "a": str(a.a), "b": str(a.b), "seed": a.seed,
         "pool": len(times), "drawn": rows}, indent=1))  # fmt: skip
    print(json.dumps({"pool": len(times), "drawn": len(rows), "out": str(a.out)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
