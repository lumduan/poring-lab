#!/usr/bin/env python3
"""--value-target (dungeon@9.28, rogue-xmas02.md 4CB; toward Batt's 2026-11-11 goal "more than
100,000 zeny / h, as I make myself"): choose the box worth the most, not the nearest.

The runner strikes the NEAREST monster box (BoxWatch.near). On xmas_dun02 the species differ
~3.4x in value a kill (econ_model.py species, Overcharge 10; drops only): Myst Case 262 z,
Christmas Cookie 125, Cookie 100, Cruiser 76. A steal draws from the same table, so the gap counts
twice for the Rogue. With this rule the candidates stay exactly the runner's (the same skips), and
only the CHOICE changes: the box with the highest

    score = value(species) / (1 + distance_px / D0_PX)

wins (ties: the nearer). D0_PX = 150: a Myst Case 300 px away beats a Cruiser at her feet, one
450 px away does not.

VALUES ARE READ AT RUN TIME from data/econ/maps.json (econ_model.py build; GPL-derived, never
committed): value = sum over the species' drops of p x the Overcharge NPC price. A box's species is
the detector's own class name (unit_detector.Box.species, e.g. "mystcase"), matched to the server's
monster AEGIS name in lower case. Language-free: ids and class names only, never a displayed name.
A species with no known value takes the map's spawn-weighted mean (it is never preferred blind).
"""

from __future__ import annotations

import json
import math
from collections.abc import Callable, Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

VALUE_TARGET_VERSION = "9.28"
D0_PX = 150.0
MAPS_JSON = Path(__file__).resolve().parents[1] / "data/econ/maps.json"


def species_values(map_name: str, path: Path = MAPS_JSON) -> dict[str, float]:
    """{species class name (aegis, lower case): value a kill at Overcharge} for ``map_name``, plus
    "*" = the spawn-weighted mean. Empty when the map is not built (the caller refuses)."""
    if not path.exists():
        return {}
    maps = json.loads(path.read_text()).get("maps", {})
    m = maps.get(map_name)
    if not m:
        return {}
    out: dict[str, float] = {}
    weights: dict[str, float] = {}
    for mob_id, sp in m.get("species", {}).items():
        v = sum(float(d.get("p") or 0) * float(d.get("sell_oc") or 0) for d in sp.get("drops", []))
        key = str(sp.get("aegis", "")).lower()
        if key:
            out[key] = round(v, 2)
            weights[key] = float(m.get("mix", {}).get(str(mob_id), 0))
    tot = sum(weights.values())
    if out:
        mean = sum(out[k] * weights[k] for k in out) / tot if tot else min(out.values())
        out["*"] = round(mean, 2)
    return out


def value_of(species: str | None, values: Mapping[str, float]) -> float:
    """PURE: a box's value: its species' value, else the map mean."""
    if species and species in values:
        return float(values[species])
    return float(values.get("*", 0.0))


def score(value: float, dist_px: float, d0: float | None = None) -> float:
    """PURE: value discounted by distance."""
    d0 = D0_PX if d0 is None else d0  # 9.44: at call time (--tune)
    return value / (1.0 + max(0.0, dist_px) / d0)


Cand = tuple[float, Any]


def pick(cands: Iterable[Cand], values: Mapping[str, float],
         species_of: Callable[[Any], str | None],
         d0: float | None = None) -> Cand | None:  # fmt: skip
    """PURE: from (distance_px, box) candidates, the best by ``score`` (ties: the nearer); None when
    there are none."""
    d0 = D0_PX if d0 is None else d0  # 9.44: at call time (--tune)
    best: tuple[float, float, Any] | None = None
    for d, b in cands:
        s = score(value_of(species_of(b), values), d, d0)
        if best is None or s > best[0] + 1e-9 or (abs(s - best[0]) <= 1e-9 and d < best[1]):
            best = (s, d, b)
    return None if best is None else (best[1], best[2])


def record(values: Mapping[str, float]) -> list[Any]:
    """The run_start record: the version, D0 and the values used (rounded)."""
    return [VALUE_TARGET_VERSION, D0_PX, {k: round(v) for k, v in sorted(values.items())}]


def distances(boxes: Sequence[Any], px: Sequence[float]) -> list[tuple[float, Any]]:
    """PURE helper: (foot distance to ``px``, box) for boxes with x0, y0, x1, y1."""
    return [(math.hypot((b.x0 + b.x1) / 2 - px[0], b.y1 - px[1]), b) for b in boxes]
