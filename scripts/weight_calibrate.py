#!/usr/bin/env python3
"""Calibrate the weight readout reader (loot@1 P1): glyphs cut from banked frames, labelled by a
given value or by packet truth (offline ground truth, ADR-0007 -- it labels, it never feeds the
reader).

    weight_calibrate.py FRAME_DIR [FRAME_DIR ...] (--label N/M | --packets PACKETS.jsonl[.gz])
                        [--settle-ms 1500] [--holdout-every 3] [--origin X,Y]
                        [--out data/ui_anchors/weight_glyphs.npz] [--report OUT.json]

* Frames: <k>-<t_mono_ns>.(jpg|png|npy) in each FRAME_DIR (scripts/route_demo.py's recorder
  names them so; .npy is BGR, the images RGB), or any *.png / *.jpg with --label. Game region,
  1280x720.
* Labels:
  - --label 90/2030: every frame shows that value (Batt's reading of the banked 2026-10-08
    frames);
  - --packets: the server's weight (stat_change var 24) and max weight (var 25) on the host clock,
    as shown = value / 10. Only frames whose weight AND max weight are multiples of 10 (any
    display rounding shows the same digits) and did not change in the --settle-ms before the
    frame (the RDP codec refines a changed region over a few frames) get a label.
* Every --holdout-every-th labelled frame is held out and read after the fit (the reader with
  allow_incomplete=True, so a partial set is still checked; the report says which symbols are
  missing). The reader itself refuses an incomplete set by default: a live check needs a
  calibration whose frames showed every digit, e.g. the weight stepped 90 -> 100 by ten +1 items.

Writes the templates (client-derived pixels: data/ is gitignored, NEVER committed) and prints a
JSON report.
"""

from __future__ import annotations

import argparse
import bisect
import dataclasses
import gzip
import json
import sys
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = ROOT / "data" / "ui_anchors" / "weight_glyphs.npz"
WEIGHT, MAX_WEIGHT = 24, 25  # rAthena SP_WEIGHT / SP_MAXWEIGHT (stat_change var)


def frame_time_ns(path: Path) -> int | None:
    """t_mono_ns from a recorder name <k>-<t_mono_ns>.<ext>; None for any other name."""
    parts = path.stem.split("-")
    return int(parts[1]) if len(parts) == 2 and parts[1].isdigit() else None


def load_frame(path: Path) -> np.ndarray:
    """A recorded frame as BGR."""
    if path.suffix == ".npy":
        return np.asarray(np.load(path, allow_pickle=False))[..., :3]
    from PIL import Image

    return np.asarray(Image.open(path).convert("RGB"))[..., ::-1]


def read_events(path: Path) -> list[dict[str, Any]]:
    with gzip.open(path, "rt") if path.suffix == ".gz" else path.open() as f:
        return [json.loads(line) for line in f if line.strip()]


class WeightTruth:
    """The server's weight and max weight over time, from stat_change events (rAthena units)."""

    def __init__(self, events: Iterable[Mapping[str, Any]]) -> None:
        self.series: dict[int, tuple[list[int], list[int]]] = {
            WEIGHT: ([], []), MAX_WEIGHT: ([], []),
        }  # fmt: skip
        for e in sorted(events, key=lambda e: int(e.get("t_mono_ns", 0))):
            if e.get("type") == "stat_change" and e.get("var") in self.series:
                times, values = self.series[int(e["var"])]
                times.append(int(e["t_mono_ns"]))
                values.append(int(e["value"]))

    def at(self, var: int, t_ns: int) -> tuple[int, int] | None:
        """(value, time it was set) of the last change at or before t_ns; None before any."""
        times, values = self.series[var]
        i = bisect.bisect_right(times, t_ns) - 1
        return None if i < 0 else (values[i], times[i])

    def label(self, t_ns: int, settle_ns: int) -> tuple[int, int] | None:
        """The shown (N, M) at t_ns when it is unambiguous: both values multiples of 10 and
        unchanged for settle_ns before t_ns; else None."""
        w, m = self.at(WEIGHT, t_ns), self.at(MAX_WEIGHT, t_ns)
        if w is None or m is None:
            return None
        if w[0] % 10 or m[0] % 10 or t_ns - max(w[1], m[1]) < settle_ns:
            return None
        return w[0] // 10, m[0] // 10


def parse_value(text: str) -> tuple[int, int]:
    n, sep, m = text.replace(" ", "").partition("/")
    if not sep or not n.isdigit() or not m.isdigit():
        raise argparse.ArgumentTypeError(f"expected N/M, got {text!r}")
    return int(n), int(m)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("frames", nargs="+", type=Path)
    how = ap.add_mutually_exclusive_group(required=True)
    how.add_argument("--label", type=parse_value)
    how.add_argument("--packets", type=Path)
    ap.add_argument("--settle-ms", type=int, default=1500)
    ap.add_argument("--holdout-every", type=int, default=3)
    ap.add_argument("--origin", default=None, help="basic_info origin X,Y (default: measured)")
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--report", type=Path)
    a = ap.parse_args()

    from poring_env import weight as wt

    origin = None
    if a.origin:
        ox, oy = (int(v) for v in a.origin.split(","))
        origin = (ox, oy)
    x, y, w, h = wt.rect_at(origin)
    paths = sorted(p for d in a.frames for p in (sorted(d.iterdir()) if d.is_dir() else [d])
                   if p.suffix in (".jpg", ".png", ".npy"))  # fmt: skip
    truth = WeightTruth(read_events(a.packets)) if a.packets else None
    labelled: list[tuple[Path, tuple[int, int]]] = []
    unlabelled = 0
    for p in paths:
        if truth is None:
            labelled.append((p, a.label))
            continue
        t = frame_time_ns(p)
        value = truth.label(t, a.settle_ms * 1_000_000) if t is not None else None
        if value is None:
            unlabelled += 1
        else:
            labelled.append((p, value))
    if not labelled:
        print(json.dumps({"error": "no labelled frame", "frames": len(paths)}))
        return 1
    k = max(2, a.holdout_every)
    train = [lv for i, lv in enumerate(labelled) if i % k]
    held = [lv for i, lv in enumerate(labelled) if not i % k]

    def gray(p: Path) -> Any:
        img = load_frame(p)
        return wt.to_gray(np.ascontiguousarray(img[y : y + h, x : x + w]))

    glyphs, stats = wt.fit_weight_glyphs([gray(p) for p, _ in train], [v for _, v in train])
    glyphs = dataclasses.replace(glyphs, meta={
        "frames": len(train), "values": sorted({f"{n}/{m}" for _, (n, m) in train}),
    })  # fmt: skip
    reads: dict[str, int] = {}
    wrong: list[str] = []
    for p, value in held:
        r = wt.read_rect(gray(p), glyphs, allow_incomplete=True)
        reads[r.reason] = reads.get(r.reason, 0) + 1
        if r.value is not None and r.value != value:
            wrong.append(f"{p.name}: read {r.value}, truth {value}")
    a.out.parent.mkdir(parents=True, exist_ok=True)
    glyphs.save(a.out)
    back = wt.load_weight_glyphs(a.out)  # read back
    report = {
        "out": str(a.out), "frames": len(paths), "labelled": len(labelled),
        "unlabelled": unlabelled, "train": len(train), "held_out": len(held),
        "values": sorted({f"{n}/{m}" for _, (n, m) in labelled}),
        "fit": stats, "held_out_reads": reads, "held_out_WRONG": wrong,
        "complete": back.complete, "missing": back.missing,
        "verdict": ("READY" if back.complete and not wrong else
                    "NOT READY: " + (f"missing {back.missing!r}" if not back.complete else "")
                    + (f" {len(wrong)} wrong held-out reads" if wrong else "")),
    }  # fmt: skip
    text = json.dumps(report, indent=1)
    if a.report:
        a.report.write_text(text + "\n")
    print(text)
    return 0 if not wrong else 1


if __name__ == "__main__":
    sys.exit(main())
