#!/usr/bin/env python3
"""Explore a map by its REGIONS and remember what each one gave (dungeon@9.14, rogue-xmas02.md 4AL;
Batt 2026-11-09: "walk new ways, not only the edge; record where she could and could not walk;
find the route with the most kills per hour").

    explore_map.py summary MAP            # the knowledge file's regions, best first
    explore_map.py plot MAP --out PNG     # the map: walkable, visited, refused, region rates

PIXELS IN ONLY (rule 1): the knowledge holds what the RUNNER itself saw -- its minimap positions,
the walk clicks that did not move it (stalls), its engagements and fights, and how many of its
own damage lines a fight had. Packets score runs offline; they never enter this file.

- Regions: REGION x REGION cell tiles of the map; a tile counts when it holds >= MIN_CELLS cells of
  the start's connected walkable component (the route grid); its ANCHOR is the reachable cell
  nearest the tile's centre (the walk goal).
- Knowledge (data/maps/<map>/explore.json, gitignored; merged across runs): per region the time
  spent (dwell_s), arrivals (visits), engagements (engages, box engages), fights and GOOD fights
  (>= GOOD_HITS of our damage lines: on p24's packets >= 5 hits was a real kill in 27 of 28 / 3 of
  17 false); per cell the minimap reads there (visited) and the walk targets that stalled (refused).
- The choice (explore + exploit): each region's GOOD fights per minute (a prior worth PRIOR_MIN
  minutes at the map's mean rate, so an unvisited region starts at the mean), plus a novelty bonus
  NOVELTY * sqrt(ln(1 + all visits) / (1 + its visits)), minus DIST_W per 100 cells away; regions
  aimed at in the last RECENT_S, the current one and the run's blocked ones are left out; one is
  SAMPLED with probabilities ~ exp(score / TEMP) (Batt's "random walk": not always the best).
"""

from __future__ import annotations

import argparse
import json
import math
import os
from collections import deque
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import numpy.typing as npt

ROOT = Path(__file__).resolve().parents[1]
KNOW_DIR = ROOT / "data" / "maps"  # gitignored (data/): our own observations
REGION = 10  # cells a side
MIN_CELLS = 15  # reachable cells for a tile to count as a region
GOOD_HITS = 5  # our damage lines in a fight that make it a (likely) kill
PRIOR_MIN = 1.0  # minutes of the map's mean rate every region starts with
NOVELTY = 0.6  # the novelty bonus' weight (good fights per minute)
DIST_W = 0.15  # the score lost per 100 cells (Chebyshev) to the anchor
TEMP = 0.25  # the softmax temperature over scores
RECENT_S = 180.0  # a region aimed at this recently is not chosen again
MEAN_FLOOR = 0.2  # good fights per minute assumed before any data (p27: ~44 kills in 25 min)

Cell = tuple[int, int]
Key = tuple[int, int]


def component(walk: npt.NDArray[np.bool_], start: Cell) -> npt.NDArray[np.bool_]:
    """PURE: the 8-connected walkable component of ``walk`` (rows y, cols x) holding ``start``; a
    diagonal step needs both side cells (no corner cutting, as the server walks). Empty when the
    start is not walkable."""
    h, w = walk.shape
    out = np.zeros_like(walk, dtype=bool)
    x0, y0 = start
    if not (0 <= x0 < w and 0 <= y0 < h) or not walk[y0, x0]:
        return out
    out[y0, x0] = True
    q: deque[Cell] = deque([start])
    while q:
        x, y = q.popleft()
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                if not dx and not dy:
                    continue
                nx, ny = x + dx, y + dy
                if not (0 <= nx < w and 0 <= ny < h) or out[ny, nx] or not walk[ny, nx]:
                    continue
                if dx and dy and not (walk[y, nx] and walk[ny, x]):
                    continue
                out[ny, nx] = True
                q.append((nx, ny))
    return out


def regions(reach: npt.NDArray[np.bool_], size: int = REGION,
            min_cells: int = MIN_CELLS) -> dict[Key, Cell]:  # fmt: skip
    """PURE: region key (rx, ry) -> its anchor, for every tile with >= ``min_cells`` reachable
    cells; the anchor is the reachable cell nearest the tile's centre (ties: the first in y, x)."""
    h, w = reach.shape
    out: dict[Key, Cell] = {}
    for ry in range((h + size - 1) // size):
        for rx in range((w + size - 1) // size):
            sub = reach[ry * size : (ry + 1) * size, rx * size : (rx + 1) * size]
            if int(sub.sum()) < min_cells:
                continue
            ys, xs = np.nonzero(sub)
            cy, cx = (sub.shape[0] - 1) / 2, (sub.shape[1] - 1) / 2
            i = int(np.argmin((ys - cy) ** 2 + (xs - cx) ** 2))
            out[(rx, ry)] = (rx * size + int(xs[i]), ry * size + int(ys[i]))
    return out


def region_of(c: Cell, size: int = REGION) -> Key:
    return (c[0] // size, c[1] // size)


def key_s(k: Key) -> str:
    return f"{k[0]},{k[1]}"


def empty_region() -> dict[str, float]:
    return {"dwell_s": 0.0, "visits": 0, "engages": 0, "box_engages": 0, "fights": 0, "good": 0}


@dataclass
class Knowledge:
    """The map's accumulated observations (``to_json`` / ``from_json``; merged by addition)."""

    map: str
    region: int = REGION
    runs: list[str] = field(default_factory=list)
    regions: dict[str, dict[str, float]] = field(default_factory=dict)
    visited: dict[str, int] = field(default_factory=dict)
    refused: dict[str, int] = field(default_factory=dict)

    def reg(self, k: Key) -> dict[str, float]:
        return self.regions.setdefault(key_s(k), empty_region())

    def to_json(self) -> dict[str, Any]:
        return {"map": self.map, "region": self.region, "runs": self.runs,
                "regions": self.regions, "visited": self.visited,
                "refused": self.refused}  # fmt: skip

    @classmethod
    def from_json(cls, d: Mapping[str, Any]) -> Knowledge:
        return cls(map=str(d["map"]), region=int(d.get("region", REGION)),
                   runs=list(d.get("runs", [])),
                   regions={k: {**empty_region(), **v} for k, v in d.get("regions", {}).items()},
                   visited={k: int(v) for k, v in d.get("visited", {}).items()},
                   refused={k: int(v) for k, v in d.get("refused", {}).items()})  # fmt: skip


def merge(base: Knowledge, add: Knowledge) -> Knowledge:
    """PURE: the two by addition (a run's own knowledge onto the file's)."""
    if base.map != add.map or base.region != add.region:
        raise ValueError(f"cannot merge {add.map}/{add.region} into {base.map}/{base.region}")
    out = Knowledge.from_json(base.to_json())
    out.runs = [*base.runs, *[r for r in add.runs if r not in base.runs]]
    for k, v in add.regions.items():
        dst = out.regions.setdefault(k, empty_region())
        for f, x in v.items():
            dst[f] = dst.get(f, 0) + x
    for name in ("visited", "refused"):
        d = getattr(out, name)
        for k, n in getattr(add, name).items():
            d[k] = d.get(k, 0) + n
    return out


def path_for(map_name: str, root: Path = KNOW_DIR) -> Path:
    return root / map_name / "explore.json"


def load(map_name: str, root: Path = KNOW_DIR) -> Knowledge:
    p = path_for(map_name, root)
    if not p.exists():
        return Knowledge(map=map_name)
    return Knowledge.from_json(json.loads(p.read_text()))


def save_merged(run: Knowledge, root: Path = KNOW_DIR) -> Knowledge:
    """The file's knowledge + this run's, written atomically (tmp + rename); returns the merge."""
    p = path_for(run.map, root)
    p.parent.mkdir(parents=True, exist_ok=True)
    merged = merge(load(run.map, root), run)
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(merged.to_json(), separators=(",", ":")))
    os.replace(tmp, p)
    return merged


def rates(know: Knowledge, keys: Iterable[Key]) -> dict[Key, float]:
    """PURE: each region's good fights per minute with the PRIOR_MIN-minute prior at the mean."""
    tot_good = sum(v["good"] for v in know.regions.values())
    tot_min = sum(v["dwell_s"] for v in know.regions.values()) / 60.0
    mean = max(MEAN_FLOOR, tot_good / tot_min) if tot_min > 1.0 else MEAN_FLOOR
    out = {}
    for k in keys:
        v = know.regions.get(key_s(k), empty_region())
        out[k] = (v["good"] + mean * PRIOR_MIN) / (v["dwell_s"] / 60.0 + PRIOR_MIN)
    return out


def scores(know: Knowledge, anchors: Mapping[Key, Cell], here: Cell,
           skip: Iterable[Key] = ()) -> dict[Key, float]:  # fmt: skip
    """PURE: the explore + exploit score of every region not in ``skip``."""
    left = [k for k in anchors if k not in set(skip)]
    rt = rates(know, left)
    n_all = sum(int(v["visits"]) for v in know.regions.values())
    out = {}
    for k in left:
        n_k = int(know.regions.get(key_s(k), empty_region())["visits"])
        nov = NOVELTY * math.sqrt(math.log(1 + n_all) / (1 + n_k)) if n_all else NOVELTY
        a = anchors[k]
        dist = max(abs(a[0] - here[0]), abs(a[1] - here[1]))
        out[k] = rt[k] + nov - DIST_W * dist / 100.0
    return out


def choose(sc: Mapping[Key, float], rng: np.random.Generator,
           temp: float = TEMP) -> Key | None:  # fmt: skip
    """The region SAMPLED with probabilities ~ exp(score / temp); None when there is none."""
    if not sc:
        return None
    keys = sorted(sc)
    s = np.array([sc[k] for k in keys], dtype=float)
    p = np.exp((s - s.max()) / max(temp, 1e-6))
    p /= p.sum()
    return keys[int(rng.choice(len(keys), p=p))]


class Recorder:
    """The runner's passive observer: fed every event (``on_event``), it books dwell time and
    visited cells from ``hp_read``'s position, arrivals at the aimed region, engagements, fights
    (and their count of our damage lines, via ``hits_between``), and stalled walk targets."""

    def __init__(self, map_name: str, run_id: str, hits_between: Any,
                 size: int = REGION) -> None:  # fmt: skip
        self.know = Knowledge(map=map_name, region=size, runs=[run_id])
        self.size = size
        self.hits_between = hits_between  # (t0, t1) -> our damage lines read in that window
        self.last_t: float | None = None
        self.last_cell: Cell | None = None
        self.fight_t0: float | None = None
        self.fight_key: Key | None = None

    def on_event(self, rec: Mapping[str, Any], t: float) -> None:
        kind = rec.get("kind")
        if kind == "hp_read":
            pos = rec.get("pos")
            if pos is not None:
                c = (int(pos[0]), int(pos[1]))
                if self.last_t is not None and self.last_cell is not None:
                    dt = max(0.0, min(5.0, t - self.last_t))  # a gap (a load) books <= 5 s
                    self.know.reg(region_of(self.last_cell, self.size))["dwell_s"] += dt
                if c != self.last_cell:
                    ks = key_s(c)
                    self.know.visited[ks] = self.know.visited.get(ks, 0) + 1
                self.last_cell = c
            self.last_t = t
        elif kind == "engage" and self.last_cell is not None:
            k = region_of(self.last_cell, self.size)
            r = self.know.reg(k)
            r["engages"] += 1
            if rec.get("by") == "box":
                r["box_engages"] += 1
            if self.fight_t0 is None:
                self.fight_t0, self.fight_key = t, k
        elif kind == "fight_end" and self.fight_t0 is not None and self.fight_key is not None:
            r = self.know.reg(self.fight_key)
            r["fights"] += 1
            if int(self.hits_between(self.fight_t0, t)) >= GOOD_HITS:
                r["good"] += 1
            self.fight_t0, self.fight_key = None, None
        elif kind == "stall" and rec.get("to") is not None:
            ks = key_s((int(rec["to"][0]), int(rec["to"][1])))
            self.know.refused[ks] = self.know.refused.get(ks, 0) + 1

    def arrived(self, k: Key) -> None:
        self.know.reg(k)["visits"] += 1


def summary(know: Knowledge, top: int = 15) -> list[dict[str, Any]]:
    """PURE: regions by good fights per minute (with >= 1 minute spent), best first."""
    rows = []
    for k, v in know.regions.items():
        mins = v["dwell_s"] / 60.0
        gpm = round(v["good"] / mins, 3) if mins >= 1.0 else None
        rows.append({"region": k, "minutes": round(mins, 1), "visits": int(v["visits"]),
                     "fights": int(v["fights"]), "good": int(v["good"]),
                     "good_per_min": gpm})  # fmt: skip
    rows.sort(key=lambda r: (r["good_per_min"] is None, -(r["good_per_min"] or 0.0)))
    return rows[:top]


def plot(know: Knowledge, walk: npt.NDArray[np.bool_], out: Path, scale: int = 3) -> None:
    """The map as a PNG: grey walkable, green visited, red refused targets, and each visited
    region's rate as a blue tint (stronger = more good fights per minute)."""
    from PIL import Image

    h, w = walk.shape
    img = np.zeros((h, w, 3), np.uint8)
    img[walk] = (70, 70, 70)
    best = max([v["good"] / (v["dwell_s"] / 60.0) for v in know.regions.values()
                if v["dwell_s"] >= 60.0] or [1.0])  # fmt: skip
    for k, v in know.regions.items():
        if v["dwell_s"] < 60.0:
            continue
        rx, ry = (int(x) for x in k.split(","))
        a = min(1.0, (v["good"] / (v["dwell_s"] / 60.0)) / best)
        sl = (slice(ry * know.region, (ry + 1) * know.region),
              slice(rx * know.region, (rx + 1) * know.region))  # fmt: skip
        sub = img[sl]
        sub[walk[sl]] = (70, 70, int(70 + 185 * a))
    for name, colour in (("visited", (60, 200, 60)), ("refused", (230, 40, 40))):
        for ks in getattr(know, name):
            x, y = (int(t) for t in ks.split(","))
            if 0 <= x < w and 0 <= y < h:
                img[y, x] = colour
    Image.fromarray(img[::-1].repeat(scale, 0).repeat(scale, 1)).save(out)  # north up


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    s1 = sub.add_parser("summary")
    s1.add_argument("map")
    s2 = sub.add_parser("plot")
    s2.add_argument("map")
    s2.add_argument("--out", type=Path, required=True)
    a = ap.parse_args(argv)
    know = load(a.map)
    if a.cmd == "summary":
        print(json.dumps({"map": know.map, "runs": know.runs, "regions": len(know.regions),
                          "visited_cells": len(know.visited), "refused_cells": len(know.refused),
                          "best": summary(know)}, indent=1))  # fmt: skip
        return 0
    from poring_dataset import walkable as wk
    from poring_dataset.mapcache import NOT_WALKABLE

    g = wk.server_grid(a.map)
    cells = np.frombuffer(g.cells, dtype=np.uint8).reshape(g.ys, g.xs)
    plot(know, ~np.isin(cells, list(NOT_WALKABLE)), a.out)
    print(json.dumps({"out": str(a.out)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
