#!/usr/bin/env python3
"""gef10 ROUND-2 MEASUREMENT (offline, FIT / TRAIN only; docs/planning/gef10-round2-measure.md).

T1 failed on TEST (gef10-detector.md 13r: C1 5 / 61 = 8.2 %). Its two sightings named two holes in
the frozen rule "gef10-o3h-e": the client's TRANSIENT pickup notice drawn over a label, and a label
beside raised terrain. This tool MEASURES two candidate rules on the FIT and TRAIN parts only, so
Batt can decide whether a round 2 is worth it. It changes no rule, no parameter and no label file.

    gef10_r2_measure.py scan     LABELS.json... --out SCAN.json     the notice detector per frame
    gef10_r2_measure.py validate SCAN.json... --out JSON [--sheet PNG]   detector vs packets
    gef10_r2_measure.py heights  --gat GAT --out JSON                the height-step distribution
    gef10_r2_measure.py measure  LABELS.json... --scan SCAN.json... --gat GAT --h H --out JSON

1. THE NOTICE (pure: ``find_notices``). The client draws "<item> - N obtained." for ~4-5 s after
   a pickup: a white rounded box (2 px) with a 1-px neutral grey border line inside it, white
   inside, an item icon and dark text; on these sessions x 541..731 y 76..105 (outer, 1280 x 720
   game frame) for a short name, wider for a longer one. The detector looks for that signature in
   the top band: a grey row with white rows above and below it (the top border), a second one
   18..40 rows lower (the bottom border), and grey border columns at both ends.
2. RAISED TERRAIN (pure: ``step_map``, ``near_step``). The client GAT's cell altitude (the mean of
   its four corners); a cell's STEP is the largest |altitude difference| to its 8 neighbours; a
   label is removed when a cell within R of its cell has a step > H.

READS: the label files (map_labels.py ``labels``, read-only), each frame's PNG by its shard offset
(only the top rows are decoded), the session's packets, the client GAT (/dev/shm, client data,
NEVER committed). TEST is refused by name: the watch's cells 11-14, a7, a8, and every session
recorded after 2026-10-26 03:00 ICT (a5b, a9 and later). No GPU, no client, no input.
"""

from __future__ import annotations

import argparse
import gzip
import json
import statistics
import sys
import zlib
from collections import Counter, defaultdict
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any

import numpy as np
import numpy.typing as npt

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

Box = tuple[float, float, float, float]
NAS = Path("/mnt/poring-lab-datasets")
FRAME_W, FRAME_H = 1280, 720

# --- the split: what may be read (gef10-detector.md 3b, 13p; the brief of 2026-10-26 03:2x) -----

WATCH = "20261025T195325-rdp-ow1"
FIT_WATCH_PART = f"{WATCH}:spots=0,1,2,3,4,5,6,7,8,9,10"
ROLES = {
    FIT_WATCH_PART: "FIT",
    "20261025T200922-rdp-rogue-pilot": "FIT",
    "20261025T203115-rdp-rogue-pilot2": "FIT",
    "20261025T221059-rdp-rogue-a2": "TRAIN",
    "20261025T232619-rdp-rogue-a4": "TRAIN",
    "20261026T014529-rdp-w2": "TRAIN",
    "20261025T204315-rdp-rogue-s1": "OUT",  # labelled, did not join TRAIN (13o, 13p)
    "20261025T213953-rdp-rogue-a1": "OUT",
    "20261025T224840-rdp-rogue-a3": "OUT",
    "20261026T002500-rdp-rogue-a6": "OUT",
}  # fmt: skip
TRAIN_JOINED = tuple(p for p, r in ROLES.items() if r in ("FIT", "TRAIN"))
TEST_SUFFIXES = ("-rdp-rogue-a7", "-rdp-rogue-a8", "-rdp-rogue-a5b", "-rdp-rogue-s7",
                 "-rdp-rogue-s8")  # fmt: skip
TEST_AFTER = "20261026T030000"  # every session recorded after 03:00 ICT tonight is TEST


def refuse_test(part: str) -> str:
    """The part's role (FIT / TRAIN / OUT); SystemExit for TEST or anything not listed."""
    sid, _, spots = part.partition(":spots=")
    if any(sid.endswith(s) for s in TEST_SUFFIXES) or sid[:15] >= TEST_AFTER:
        raise SystemExit(f"{part}: TEST (or recorded after 03:00 ICT): refused")
    if sid == WATCH and part != FIT_WATCH_PART:
        raise SystemExit(f"{part}: the watch is read only as its FIT cells 0-10: refused")
    if part not in ROLES:
        raise SystemExit(f"{part}: not a listed FIT / TRAIN part: refused")
    return ROLES[part]


# --- 1. the pickup notice (pure) ----------------------------------------------------------------

NOTICE_BAND = (40, 170, 230, 1135)  # y0, y1, x0, x1: the top centre, between hotbar and minimap
WHITE_MIN = 235  # every channel >= this: the notice's white
GREY_LO, GREY_HI, GREY_SPREAD = 160, 222, 14  # its border line: neutral grey (~190-200)
MIN_RUN = 40  # px: the shortest border line taken (the shortest item name still draws ~190 px)
BORDER_GAP = (18, 40)  # rows from the top border line to the bottom one (25 measured)
COL_SHARE = 0.8  # a border column: grey with white beside it on >= 80 % of its inner rows


def notice_masks(img: npt.NDArray[np.uint8]) -> tuple[npt.NDArray[np.bool_], npt.NDArray[np.bool_]]:
    """(white, grey) per pixel; channel order does not matter (min / max over channels)."""
    mn = img.min(axis=2).astype(np.int16)
    mx = img.max(axis=2).astype(np.int16)
    white = mn >= WHITE_MIN
    grey = (mn >= GREY_LO) & (mx <= GREY_HI) & (mx - mn <= GREY_SPREAD)
    return white, grey


def runs(row: npt.NDArray[np.bool_], gap: int = 3) -> list[tuple[int, int]]:
    """(start, end exclusive) of the True runs of a 1-D mask, joining gaps of <= ``gap``."""
    idx = np.flatnonzero(row)
    if idx.size == 0:
        return []
    out: list[tuple[int, int]] = []
    start = prev = int(idx[0])
    for i in idx[1:]:
        i = int(i)
        if i - prev > gap + 1:
            out.append((start, prev + 1))
            start = i
        prev = i
    out.append((start, prev + 1))
    return out


def _border_col(white: npt.NDArray[np.bool_], grey: npt.NDArray[np.bool_], rows: slice,
                cols: Iterable[int], outward: int) -> int | None:  # fmt: skip
    """The first column in ``cols`` that is a vertical border line over ``rows``: grey, white on
    its inner side, white on the 2 px of its outer side (``outward`` -1 left, +1 right)."""
    w = grey.shape[1]
    for x in cols:
        if not (2 <= x < w - 2):
            continue
        g = grey[rows, x]
        inner = white[rows, x - outward]
        outer = white[rows, x + outward] & white[rows, x + 2 * outward]
        if g.mean() >= COL_SHARE and inner.mean() >= COL_SHARE and outer.mean() >= COL_SHARE:
            return x
    return None


def find_notices(img: npt.NDArray[np.uint8],
                 band: tuple[int, int, int, int] = NOTICE_BAND) -> list[Box]:  # fmt: skip
    """PURE: the notice boxes (x0, y0, x1, y1; outer white edge, end exclusive, frame px) in a
    frame's top rows ``img`` (H x W x 3, row 0 = the frame's row 0; H >= band's y1 + 2)."""
    y0, y1, x0, x1 = band
    sub = img[max(0, y0 - 3) : y1 + 3, x0:x1]
    oy = max(0, y0 - 3)
    white, grey = notice_masks(sub)
    h = white.shape[0]
    top = np.zeros_like(white)
    bot = np.zeros_like(white)
    top[2:-1] = grey[2:-1] & white[1:-2] & white[:-3] & white[3:]
    bot[1:-2] = grey[1:-2] & white[2:-1] & white[3:] & white[:-3]
    tops = [(y, r) for y in range(h) for r in runs(top[y]) if r[1] - r[0] >= MIN_RUN]
    bots = [(y, r) for y in range(h) for r in runs(bot[y]) if r[1] - r[0] >= MIN_RUN]
    out: list[Box] = []
    used: set[int] = set()
    for yt, (a0, a1) in tops:
        if yt in used:
            continue
        for yb, (b0, b1) in bots:
            if not (BORDER_GAP[0] <= yb - yt <= BORDER_GAP[1]):
                continue
            inter = min(a1, b1) - max(a0, b0)
            if inter < 0.8 * min(a1 - a0, b1 - b0):
                continue
            rows = slice(yt + 3, yb - 2)
            lo, hi = min(a0, b0), max(a1, b1)
            xl = _border_col(white, grey, rows, range(lo, lo - 12, -1), -1)
            xr = _border_col(white, grey, rows, range(hi - 1, hi + 11), +1)
            if xl is None or xr is None:
                continue
            out.append((float(x0 + xl - 2), float(oy + yt - 2), float(x0 + xr + 3),
                        float(oy + yb + 3)))  # fmt: skip
            used.update(range(yt - 2, yt + 3))
            break
    return out


def overlap_area(a: Box, b: Box) -> float:
    w = min(a[2], b[2]) - max(a[0], b[0])
    h = min(a[3], b[3]) - max(a[1], b[1])
    return w * h if w > 0 and h > 0 else 0.0


def covered_share(box: Box, notices: Sequence[Box]) -> float:
    """The share of ``box`` under the notices (they never overlap each other)."""
    area = (box[2] - box[0]) * (box[3] - box[1])
    return 0.0 if area <= 0 else min(1.0, sum(overlap_area(box, n) for n in notices) / area)


def grown(box: Box, px: float) -> Box:
    return (box[0] - px, box[1] - px, box[2] + px, box[3] + px)


# --- 2. raised terrain (pure) ------------------------------------------------------------------


def step_map(alt: npt.NDArray[np.float64]) -> npt.NDArray[np.float64]:
    """PURE: each cell's STEP: the largest |altitude difference| to its 8 neighbours (the map's
    edge counts as the cell itself)."""
    h, w = alt.shape
    pad = np.pad(alt, 1, mode="edge")
    step = np.zeros_like(alt, dtype=float)
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            if dx or dy:
                step = np.maximum(step, np.abs(alt - pad[1 + dy : 1 + dy + h, 1 + dx : 1 + dx + w]))
    return step


def near_step(step: npt.NDArray[np.float64], cell: tuple[int, int], radius: int,
              h: float) -> bool:  # fmt: skip
    """PURE: a cell within ``radius`` (Chebyshev) of ``cell`` (x, y) has a step > ``h``."""
    x, y = cell
    hh, ww = step.shape
    win = step[
        max(0, y - radius) : min(hh, y + radius + 1), max(0, x - radius) : min(ww, x + radius + 1)
    ]
    return bool(win.size and float(win.max()) > h)


def nearest_step(step: npt.NDArray[np.float64], cell: tuple[int, int], h: float,
                 max_r: int = 15) -> int | None:  # fmt: skip
    """PURE: the smallest Chebyshev radius at which ``near_step`` holds (None beyond ``max_r``)."""
    for r in range(max_r + 1):
        if near_step(step, cell, r, h):
            return r
    return None


# --- IO: the top rows of one frame ---------------------------------------------------------------

TOP_ROWS = NOTICE_BAND[1] + 4
READ_STEP = 256 << 10


def read_top_rows(
    shard: Path, offset: int, size: int, rows: int = TOP_ROWS
) -> npt.NDArray[np.uint8]:
    """The first ``rows`` rows of a recorder PNG (8-bit RGB / RGBA, non-interlaced), RGB order:
    reads and inflates only as much of the member's IDAT stream as those rows need."""
    from poring_dataset.shards import _unfilter

    with shard.open("rb") as fh:
        fh.seek(offset)
        if fh.read(8) != b"\x89PNG\r\n\x1a\n":
            raise ValueError(f"{shard}@{offset}: not a PNG")
        end = offset + size
        dec = zlib.decompressobj()
        out = bytearray()
        need = stride = ch = w = h = 0
        while fh.tell() + 8 <= end:
            head = fh.read(8)
            length, kind = int.from_bytes(head[:4], "big"), head[4:8]
            if kind == b"IHDR":
                body = fh.read(length)
                w, h = int.from_bytes(body[:4], "big"), int.from_bytes(body[4:8], "big")
                depth, color, interlace = body[8], body[9], body[12]
                if depth != 8 or color not in (2, 6) or interlace:
                    raise ValueError(f"{shard}@{offset}: depth {depth} colour {color}")
                ch = 3 if color == 2 else 4
                stride = w * ch
                need = min(rows, h) * (stride + 1)
                fh.seek(4, 1)
            elif kind == b"IDAT" and need:
                left = length
                while left > 0 and len(out) < need:
                    piece = fh.read(min(READ_STEP, left))
                    if not piece:
                        raise ValueError(f"{shard}@{offset}: short read")
                    left -= len(piece)
                    out += dec.decompress(piece)
                if len(out) >= need:
                    break
                fh.seek(left + 4, 1)
            else:
                fh.seek(length + 4, 1)
    if not need or len(out) < need:
        raise ValueError(f"{shard}@{offset}: fewer than {rows} rows decoded")
    n = min(rows, h)
    px = _unfilter(bytes(out[:need]), n, stride, ch).reshape(n, w, ch)
    return np.ascontiguousarray(px[:, :, :3])


# --- the parts ---------------------------------------------------------------------------------


def load_labels(path: Path) -> dict[str, Any]:
    doc: dict[str, Any] = json.loads(path.read_text())
    role = refuse_test(str(doc["part"]))
    if doc.get("params_status") != "FROZEN" or doc.get("map") != "gef_fild10":
        raise SystemExit(f"{path}: not a FROZEN gef_fild10 label file")
    doc["_role"] = role
    return doc


def session_dir(doc: dict[str, Any]) -> Path:
    return NAS / str(doc["session"])


def packet_events(doc: dict[str, Any]) -> list[dict[str, Any]]:
    with gzip.open(session_dir(doc) / "packets.jsonl.gz", "rt") as fh:
        return [json.loads(line) for line in fh]


def pickup_times(events: Iterable[dict[str, Any]]) -> list[int]:
    """PURE: the times of the inventory gains that draw the notice (``pickup_result`` ok)."""
    return sorted(int(e["t_mono_ns"]) for e in events
                  if e.get("type") == "pickup_result" and e.get("ok"))  # fmt: skip


def last_before(times: Sequence[int], t: int) -> int | None:
    import bisect

    i = bisect.bisect_right(times, t) - 1
    return times[i] if i >= 0 else None


def first_after(times: Sequence[int], t: int) -> int | None:
    import bisect

    i = bisect.bisect_right(times, t)
    return times[i] if i < len(times) else None


# --- scan: the detector over every candidate frame -----------------------------------------------


def cmd_scan(a: argparse.Namespace) -> dict[str, Any]:
    parts = []
    for path in a.labels:
        doc = load_labels(path)
        sdir = session_dir(doc)
        picks = pickup_times(packet_events(doc))
        rows = []
        for f in doc["frames"]:
            t = int(f["t"])
            top = read_top_rows(sdir / str(f["shard"]), int(f["offset"]), int(f["size"]))
            prev, nxt = last_before(picks, t), first_after(picks, t)
            rows.append(
                {
                    "frame_id": f["frame_id"],
                    "t": t,
                    "notices": find_notices(top),
                    "pickup_age_s": None if prev is None else round((t - prev) / 1e9, 3),
                    "next_pickup_s": None if nxt is None else round((nxt - t) / 1e9, 3),
                }
            )
        parts.append({"part": doc["part"], "role": doc["_role"], "label_file": str(path),
                      "pickups": len(picks), "frames": rows})  # fmt: skip
        print(f"{doc['part']}: {len(rows)} frames, {sum(bool(r['notices']) for r in rows)} with a "
              f"notice, {len(picks)} pickups", file=sys.stderr)  # fmt: skip
    return {"what": "the pickup-notice detector on every candidate frame (gef10 round-2)",
            "band": NOTICE_BAND, "parts": parts}  # fmt: skip


# --- validate: the detector against the packets' pickups ----------------------------------------

POS_MAX_S = 4.0  # a pickup <= 4 s before the frame: the notice should be drawn (positive case)
NEG_MIN_S = 10.0  # no pickup in the 10 s before the frame: it should not (negative case)


def validation(parts: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """PURE: the detector per pickup-age bin, and the POSITIVE / NEGATIVE cases (POS_MAX_S,
    NEG_MIN_S) with every disagreement listed."""
    bins: dict[str, Counter[str]] = defaultdict(Counter)
    cases: dict[str, dict[str, list[str]]] = {"positive": defaultdict(list),
                                              "negative": defaultdict(list)}  # fmt: skip
    widths: Counter[str] = Counter()
    for p in parts:
        for r in p["frames"]:
            age = r["pickup_age_s"]
            hit = bool(r["notices"])
            for n in r["notices"]:
                widths[f"{n[0]:.0f}-{n[2]:.0f} x {n[1]:.0f}-{n[3]:.0f}"] += 1
            key = (
                "none"
                if age is None
                else "10+"
                if age >= NEG_MIN_S
                else f"{int(age)}-{int(age) + 1}"
            )
            bins[key]["frames"] += 1
            bins[key]["detected"] += hit
            ref = f"{p['part']}#{r['frame_id']}"
            if age is not None and age <= POS_MAX_S:
                cases["positive"]["detected" if hit else "missed"].append(ref)
            elif age is None or age >= NEG_MIN_S:
                cases["negative"]["detected" if hit else "clear"].append(ref)
    order = [f"{k}-{k + 1}" for k in range(10)] + ["10+", "none"]
    out: dict[str, Any] = {
        "by_pickup_age_s": {k: dict(bins[k]) for k in order if k in bins},
        "notice_boxes": dict(widths.most_common()),
    }
    for kind, d in cases.items():
        n = sum(len(v) for v in d.values())
        wrong = "missed" if kind == "positive" else "detected"
        out[kind] = {"n": n, **{k: len(v) for k, v in d.items()}, "listed": {wrong: d[wrong]}}
    return out


def cmd_validate(a: argparse.Namespace) -> dict[str, Any]:
    parts = [p for s in a.scan for p in json.loads(s.read_text())["parts"]]
    for p in parts:
        refuse_test(p["part"])
    out: dict[str, Any] = {"what": "the notice detector vs the packets' pickups (gef10 round-2)",
                           "pos_max_s": POS_MAX_S, "neg_min_s": NEG_MIN_S}  # fmt: skip
    out["all"] = validation(parts)
    for role in ("FIT", "TRAIN", "OUT"):
        mine = [p for p in parts if p["role"] == role]
        if mine:
            out[role] = validation(mine)
    if a.sheet is not None:
        sheet(parts, out["all"], a.sheet)
    return out


def sheet(parts: Sequence[dict[str, Any]], val: dict[str, Any], dest: Path, per: int = 8) -> None:
    """A by-eye sheet (scratch, client pixels: /dev/shm only, never committed): the band of up
    to ``per`` detected positives, every missed positive and every detected negative (<= per)."""
    from PIL import Image

    docs = {p["part"]: load_labels(Path(p["label_file"])) for p in parts}
    frames = {(part, f["frame_id"]): f for part, d in docs.items() for f in d["frames"]}
    pos = val["positive"]
    want = [("missed", x) for x in pos["listed"].get("missed", [])[:per]]
    want += [("false", x) for x in val["negative"]["listed"].get("detected", [])[:per]]
    hits = [
        f"{p['part']}#{r['frame_id']}"
        for p in parts
        for r in p["frames"]
        if r["notices"] and r["pickup_age_s"] is not None and r["pickup_age_s"] <= POS_MAX_S
    ]
    step = max(1, len(hits) // per)
    want += [("hit", x) for x in hits[::step][:per]]
    y0, y1, x0, x1 = NOTICE_BAND
    tiles = []
    for _kind, ref in want:
        part, _, fid = ref.rpartition("#")
        f = frames[(part, int(fid))]
        top = read_top_rows(session_dir(docs[part]) / str(f["shard"]), int(f["offset"]),
                            int(f["size"]))  # fmt: skip
        tiles.append(top[y0:y1, x0:x1])
    if not tiles:
        return
    img = np.concatenate([np.pad(t, ((0, 4), (0, 0), (0, 0))) for t in tiles])
    Image.fromarray(img).save(dest)
    (dest.with_suffix(".txt")).write_text("\n".join(f"{k} {r}" for k, r in want) + "\n")


# --- heights: the step distribution (H is chosen from it BEFORE the counts) ----------------------


def load_gat(path: Path) -> Any:
    from poring_dataset import gat

    return gat.parse(path.read_bytes())


def dist(values: npt.NDArray[np.float64]) -> dict[str, Any]:
    qs = (50, 75, 90, 95, 97.5, 99, 99.5, 99.9)
    return {
        "n": int(values.size),
        **{f"p{q}": round(float(np.percentile(values, q)), 2) for q in qs},
        "max": round(float(values.max()), 2),
        "share_gt": {
            str(h): round(float((values > h).mean()), 4) for h in (1, 2, 4, 6, 8, 10, 15, 20)
        },
    }


def cmd_heights(a: argparse.Namespace) -> dict[str, Any]:
    g = load_gat(a.gat)
    alt = g.altitude
    step = step_map(alt)
    ok = g.walkable()
    hist = Counter(round(float(v) * 2) / 2 for v in step[ok])
    return {"what": "gef_fild10 client GAT: each cell's STEP (max |altitude difference| to its 8 "
                    "neighbours, world units; 5 units = one cell's width)",
            "gat_sha256": _sha256(a.gat), "size": [g.width, g.height],
            "walkable_cells": int(ok.sum()),
            "altitude_walkable": dist(alt[ok]), "step_walkable": dist(step[ok]),
            "step_all_cells": dist(step.ravel()),
            "step_walkable_hist_0.5": {str(k): v for k, v in sorted(hist.items())}}  # fmt: skip


def _sha256(path: Path) -> str:
    import hashlib

    return hashlib.sha256(path.read_bytes()).hexdigest()


# --- measure: both rules on the kept labels ----------------------------------------------------

PARAMS = Path("/dev/shm/poring-lab-tmp/gef10-det/params.json")
PARAMS_SHA256 = "00ef6383883927e35991355f7d29597c0f918af73f65751885a53edfb1b0aac1"
CLASSES = ROOT / "config" / "detector" / "classes-v2orc-payf07-gef10.json"
RADII = (1, 2)  # the terrain rule's R, Chebyshev cells (primary: PRIMARY_R)
PRIMARY_R = 2
UI_MARGIN_PX = (
    16.0  # C1's standing rule keeps a label's box this far from the UI (orc_camera_check)
)
TAU_C1 = 0.092  # C1's bad-label tau (olf.TAU)
DIST_BINS = ((0, 2), (3, 5), (6, 10), (11, 15))
FLAG_KEYS = ("notice", "notice_half", "notice_grown16", "terrain_r1", "terrain_r2")


def label_flags(box: Box, notices: Sequence[Box], cell: tuple[int, int] | None,
                step: npt.NDArray[np.float64], h: float) -> dict[str, Any]:  # fmt: skip
    """PURE: one label's flags under both candidate rules."""
    out: dict[str, Any] = {
        "notice": any(overlap_area(box, n) > 0 for n in notices),
        "notice_half": covered_share(box, notices) >= 0.5,
        "notice_grown16": any(overlap_area(grown(box, UI_MARGIN_PX), n) > 0 for n in notices),
        "cell": cell,
    }
    for r in RADII:
        out[f"terrain_r{r}"] = None if cell is None else near_step(step, cell, r, h)
    out["step_dist"] = None if cell is None else nearest_step(step, cell, h)
    return out


def removed(flags: dict[str, Any], rule: str) -> bool:
    """PURE: the label leaves under ``rule``: N (notice), T (terrain at PRIMARY_R), NT (either)."""
    n = bool(flags["notice"])
    t = bool(flags[f"terrain_r{PRIMARY_R}"])
    return {"N": n, "T": t, "NT": n or t}[rule]


def tally(frames: Sequence[dict[str, Any]], floor: float, index: dict[int, int]) -> dict[str, Any]:
    """PURE: per species, kept labels and labels in WRITTEN frames (build_frame_cache.map_frame at
    the floor) before and after each rule; a removed label takes its frame out of the cache, as
    every excluded monster label does (gef10-detector.md 2: a frame is labelled whole or not)."""
    from build_frame_cache import map_frame

    kept: dict[str, Counter[str]] = defaultdict(Counter)
    for f in frames:
        if "kept" not in f:
            continue
        written, _why = map_frame(f, floor, index)
        flags = f["_flags"]
        for k, fl in zip(f["kept"], flags, strict=True):
            c = kept[str(k["mob"])]
            c["kept"] += 1
            for rule in ("N", "T", "NT"):
                c[f"kept_minus_{rule}"] += not removed(fl, rule)
            if written:
                c["written"] += 1
                for rule in ("N", "T", "NT"):
                    c[f"written_minus_{rule}"] += not any(removed(x, rule) for x in flags)
        if written:
            for rule in ("N", "T", "NT"):
                kept["_frames"][f"written_minus_{rule}"] += not any(removed(x, rule) for x in flags)
            kept["_frames"]["written"] += 1
    return {m: dict(v) for m, v in sorted(kept.items())}


def summary(values: Sequence[float]) -> dict[str, Any]:
    if not values:
        return {"n": 0}
    return {"n": len(values), "median": round(statistics.median(values), 3),
            "p10": round(float(np.percentile(values, 10)), 3),
            "p25": round(float(np.percentile(values, 25)), 3),
            "mean": round(statistics.fmean(values), 3)}  # fmt: skip


def mann_whitney(a: Sequence[float], b: Sequence[float]) -> float | None:
    try:
        from scipy.stats import mannwhitneyu
    except ImportError:
        return None
    if len(a) < 3 or len(b) < 3:
        return None
    return round(float(mannwhitneyu(a, b, alternative="two-sided").pvalue), 4)


def cmd_measure(a: argparse.Namespace) -> dict[str, Any]:
    import map_labels as ml

    if _sha256(PARAMS) != PARAMS_SHA256:
        raise SystemExit(f"{PARAMS}: not the frozen params")
    params = json.loads(PARAMS.read_text())
    off = int(float(params["offset_ms"]) * 1e6)
    floor = float(params["o3h_tau"])
    classes = json.loads(CLASSES.read_text())
    index = {
        int(m): int(classes["monster_first_id"]) + i for i, m in enumerate(classes["monsters"])
    }
    g = load_gat(a.gat)
    step = step_map(g.altitude)
    scans = {p["part"]: {r["frame_id"]: r for r in p["frames"]}
             for s in a.scan for p in json.loads(s.read_text())["parts"]}  # fmt: skip
    per_part: dict[str, Any] = {}
    labels: list[dict[str, Any]] = []
    for path in a.labels:
        doc = load_labels(path)
        if doc["part"] not in TRAIN_JOINED:
            raise SystemExit(f"{doc['part']}: did not join TRAIN; measure counts TRAIN only")
        scan = scans[doc["part"]]
        lab = ml.session_labeler(session_dir(doc), ml.GEF10)
        no_cell = 0
        for f in doc["frames"]:
            if "kept" not in f:
                continue
            world = lab.timeline.frame_world(int(f["t"]) - off)
            ents = {e.gid: e for e in world.entities}
            notices = [tuple(n) for n in scan[f["frame_id"]]["notices"]]
            flags = []
            for k in f["kept"]:
                e = ents.get(k["gid"])
                cell = None if e is None else (int(round(e.x)), int(round(e.y)))
                no_cell += cell is None
                fl = label_flags(tuple(k["box"]), notices, cell, step, a.h)  # type: ignore[arg-type]
                flags.append(fl)
                labels.append({"part": doc["part"], "role": doc["_role"], "frame_id": f["frame_id"],
                               "gid": k["gid"], "mob": k["mob"], "ncc": k["ncc"], "dx": k["dx"],
                               "dy": k["dy"], "under": k["under"], "engaged": k.get("engaged"),
                               "box": k["box"], **fl})  # fmt: skip
            f["_flags"] = flags
        per_part[doc["part"]] = {"role": doc["_role"], "no_cell": no_cell,
                                 "tally": tally(doc["frames"], floor, index)}  # fmt: skip
        print(f"{doc['part']}: measured", file=sys.stderr)
    pooled: dict[str, Counter[str]] = defaultdict(Counter)
    for p in per_part.values():
        for m, c in p["tally"].items():
            pooled[m].update(c)
    # the FIT-side check: do labels near a height step (or under a notice) fit worse?
    fitcheck: dict[str, Any] = {}
    for scope in ("FIT", "TRAIN_JOINED"):
        mine = [x for x in labels if scope == "TRAIN_JOINED" or x["role"] == "FIT"]
        near = [float(x["ncc"]) for x in mine if x[f"terrain_r{PRIMARY_R}"]]
        far = [float(x["ncc"]) for x in mine if x[f"terrain_r{PRIMARY_R}"] is False]
        under_n = [float(x["ncc"]) for x in mine if x["notice"]]
        clear_n = [float(x["ncc"]) for x in mine if not x["notice"]]
        by_dist = {}
        for lo, hi in DIST_BINS:
            v = [
                float(x["ncc"])
                for x in mine
                if x["step_dist"] is not None and lo <= x["step_dist"] <= hi
            ]
            by_dist[f"{lo}-{hi}"] = summary(v)
        none = [float(x["ncc"]) for x in mine if x["cell"] is not None and x["step_dist"] is None]
        by_dist["none_within_15"] = summary(none)
        tkey = f"terrain_r{PRIMARY_R}"
        fitcheck[scope] = {
            f"ncc_near_step_r{PRIMARY_R}": summary(near),
            f"ncc_not_near_step_r{PRIMARY_R}": summary(far),
            "mann_whitney_p_terrain": mann_whitney(near, far),
            "abs_dy_near_vs_not": [summary([abs(x["dy"]) for x in mine if x[tkey]]),
                                   summary([abs(x["dy"]) for x in mine if x[tkey] is False])],
            "ncc_under_notice": summary(under_n), "ncc_not_under_notice": summary(clear_n),
            "mann_whitney_p_notice": mann_whitney(under_n, clear_n),
            "ncc_by_step_distance_cells": by_dist,
        }  # fmt: skip
    out: dict[str, Any] = {
        "what": "gef10 round-2 MEASUREMENT: the notice rule (N) and the terrain rule (T) on the "
                "kept labels of the TRAIN-joined parts (FIT + a2, a4, w2); nothing decided",
        "h": a.h, "primary_r": PRIMARY_R, "radii": list(RADII), "params_sha256": PARAMS_SHA256,
        "floor": floor, "offset_ms": params["offset_ms"], "gat_sha256": _sha256(a.gat),
        "per_part": per_part, "pooled": {m: dict(c) for m, c in sorted(pooled.items())},
        "flags_pooled": {k: sum(bool(x[k]) for x in labels) for k in FLAG_KEYS},
        "fit_check": fitcheck,
        "notice_labels": [x for x in labels if x["notice"] or x["notice_grown16"]],
    }  # fmt: skip
    if a.c1rows:
        out["c1_rows"] = c1_check(a.c1rows, scans, step, a.h)
    if a.labels_out is not None:
        a.labels_out.write_text(json.dumps(labels) + "\n")
    return out


def c1_check(paths: Sequence[Path], scans: dict[str, dict[int, dict[str, Any]]],
             step: npt.NDArray[np.float64], h: float) -> dict[str, Any]:  # fmt: skip
    """The standing labels C1 scored on the TRAIN-joined parts (map_labels.py check --rows): do
    the rules catch the BAD ones (c1 < tau, why_low bad_label) more than the rest?"""
    rows = []
    for p in paths:
        for r in json.loads(p.read_text()):
            refuse_test(str(r["part"]))
            if r["c1"] is None:
                continue
            notices = [tuple(n) for n in scans[r["part"]][r["frame_id"]]["notices"]]
            cell = (int(round(r["cell"][0])), int(round(r["cell"][1])))
            fl = label_flags(tuple(r["box"]), notices, cell, step, h)  # type: ignore[arg-type]
            bad = r["c1"] < TAU_C1 and r["why_low"] == "bad_label"
            rows.append({"part": r["part"], "frame_id": r["frame_id"], "gid": r["gid"],
                         "mob": r["mob"], "c1": r["c1"], "why_low": r["why_low"], "bad": bad,
                         **fl})  # fmt: skip
    out: dict[str, Any] = {"scored": len(rows), "bad": sum(r["bad"] for r in rows)}
    for key in ("notice", "notice_grown16", "terrain_r1", "terrain_r2"):
        hit = [r for r in rows if r[key]]
        out[key] = {"scored": len(hit), "bad": sum(r["bad"] for r in hit)}
    out["bad_rows"] = [r for r in rows if r["bad"]]
    out["c1_after"] = {rule: {"scored": sum(not removed(r, rule) for r in rows),
                              "bad": sum(r["bad"] and not removed(r, rule) for r in rows)}
                       for rule in ("N", "T", "NT")}  # fmt: skip
    return out


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("scan")
    p.add_argument("labels", nargs="+", type=Path)
    p.add_argument("--out", type=Path, required=True)
    p = sub.add_parser("validate")
    p.add_argument("scan", nargs="+", type=Path)
    p.add_argument("--sheet", type=Path, default=None, help="a by-eye PNG (/dev/shm only)")
    p.add_argument("--out", type=Path, required=True)
    p = sub.add_parser("heights")
    p.add_argument("--gat", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    p = sub.add_parser("measure")
    p.add_argument("labels", nargs="+", type=Path)
    p.add_argument("--scan", nargs="+", type=Path, required=True)
    p.add_argument("--gat", type=Path, required=True)
    p.add_argument("--h", type=float, required=True, help="the step threshold H (world units)")
    p.add_argument("--c1rows", nargs="*", type=Path, default=None)
    p.add_argument("--labels-out", type=Path, default=None)
    p.add_argument("--out", type=Path, required=True)
    a = ap.parse_args(argv)
    run = {"scan": cmd_scan, "validate": cmd_validate, "heights": cmd_heights,
           "measure": cmd_measure}  # fmt: skip
    out = run[a.cmd](a)
    out["run_at"] = _now_ict()
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(out, indent=1) + "\n")
    brief = {k: v for k, v in out.items() if k not in ("parts", "notice_labels", "per_part")}
    print(json.dumps(brief, indent=1)[:12000])
    return 0


def _now_ict() -> str:
    import datetime

    return datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=7))).strftime(
        "%Y-%m-%d %H:%M:%S ICT"
    )


if __name__ == "__main__":
    sys.exit(main())
