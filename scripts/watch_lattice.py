#!/usr/bin/env python3
"""The STAND LATTICE of an immune lattice watch, split into its TRAIN / TEST stands by a cell rule
fixed before any frame is recorded (docs/planning/xmas02-detector.md 2a and 3a, 2026-11-06).

    watch_lattice.py build --map xmas_dun02 --out-dir /dev/shm/poring-lab-tmp/xmas-det/lattice
        [--step 11] [--min-clear 2] [--snap 3] [--avoid 129,130,16,12] [--test-rule 26,3,5]

OFFLINE ONLY (no client, no packets, no input); the sources are map_prep's: the client GAT in
/dev/shm, the server map cache, L3 (warps, script-NPC touch areas) and the map's zones file.

A STAND is a cell of the stand grid (client AND server walkable, outside every warp span and touch
area: anim_region.stand_grid), outside every no-enter zone, in the main 8-connected component, and
CLEAR: its (2 x min_clear + 1)^2 square all such cells (min_clear 2 = a fully walkable 5 x 5).
- The LATTICE: one stand per node of a ``step``-cell grid (nodes at step // 2 + k x step): the node
  itself when it is a stand, else the nearest stand within ``snap`` cells (Chebyshev; ties by the
  squared distance, then y, then x); a node with none is skipped.
- AVOID (``x,y,dx,dy``): a stand with |x - X| <= dx and |y - Y| <= dy is dropped (xmas_dun02: the
  exit warp (129,130) stays out of view, else its frames are ``warp_in_view``).
- TEST (``block,k,mod``): a stand is TEST when (x // block + k x (y // block)) mod ``mod`` == 0
  (3a: 26 x 26-cell blocks, (bx + 3 by) mod 5 == 0, 20 of the 100 blocks).
- Every stand of both files passes the THREE stand-cell checks in one call
  (map_prep.stand_check -> npc_click_test.check_warps); a refusal writes nothing.

Writes ``lattice-train.json`` and ``lattice-test.json`` (lists of {"x", "y"}: stage_items.py watch
reads them) and ``lattice.json`` (the rule, the sources' sha256, the counts). Client-derived: they
stay under /dev/shm, never in the repo.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

Cell = tuple[int, int]
STEP = 11  # xmas02-detector.md 2a: an ~11-cell lattice
MIN_CLEAR = 2  # a fully walkable 5 x 5
SNAP = 3
AVOID = {"xmas_dun02": (129, 130, 16, 12)}  # 2a: the stands that see the exit warp
TEST_RULE = (26, 3, 5)  # 3a: 26-cell blocks, (bx + 3 by) mod 5 == 0


def stands_mask(ok: Any, no_enter: Any, min_clear: int) -> np.ndarray:
    """PURE: the stand cells (y, x): ``ok`` minus ``no_enter``, its largest 8-connected component,
    and clear by ``min_clear`` on that component."""
    import map_prep as mp
    import map_zones as mz

    m = np.asarray(ok, dtype=bool) & ~np.asarray(no_enter, dtype=bool)
    lab, sizes = mz._label8(m, True)
    main = lab == int(np.argmax(sizes)) if len(sizes) > 1 else np.zeros_like(m)
    return np.asarray(mp.clearance(main, max(min_clear, 1)) >= min_clear) & main


def lattice_points(stands: Any, step: int, snap: int) -> list[Cell]:
    """PURE: one stand per node of the ``step`` grid (the node, else the nearest stand within
    ``snap`` by Chebyshev distance, ties by the squared distance, then y, then x); unique."""
    s = np.asarray(stands, dtype=bool)
    h, w = s.shape
    out: list[Cell] = []
    seen: set[Cell] = set()
    for ny in range(step // 2, h, step):
        for nx in range(step // 2, w, step):
            best: tuple[int, int, int] | None = None
            for y in range(max(0, ny - snap), min(h, ny + snap + 1)):
                for x in range(max(0, nx - snap), min(w, nx + snap + 1)):
                    if not s[y, x]:
                        continue
                    key = ((x - nx) ** 2 + (y - ny) ** 2, y, x)
                    if best is None or key < best:
                        best = key
            if best is not None and (best[2], best[1]) not in seen:
                seen.add((best[2], best[1]))
                out.append((best[2], best[1]))
    return out


def sees(c: Cell, avoid: Sequence[int] | None) -> bool:
    """PURE: ``c`` lies within ``avoid`` = (x, y, dx, dy)."""
    if avoid is None:
        return False
    ax, ay, dx, dy = avoid
    return abs(c[0] - ax) <= dx and abs(c[1] - ay) <= dy


def is_test(c: Cell, rule: Sequence[int] = TEST_RULE) -> bool:
    """PURE: 3a's TEST rule on a cell: (x // block + k * (y // block)) % mod == 0."""
    block, k, mod = rule
    return (c[0] // block + k * (c[1] // block)) % mod == 0


def split(cells: Sequence[Cell], avoid: Sequence[int] | None,
          rule: Sequence[int] = TEST_RULE) -> dict[str, list[Cell]]:  # fmt: skip
    """PURE: {"train", "test", "avoided"} from the lattice ``cells``."""
    out: dict[str, list[Cell]] = {"train": [], "test": [], "avoided": []}
    for c in cells:
        out["avoided" if sees(c, avoid) else "test" if is_test(c, rule) else "train"].append(c)
    return out


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build(map_name: str, out_dir: Path, *, step: int = STEP, min_clear: int = MIN_CLEAR,
          snap: int = SNAP, avoid: Sequence[int] | None = None,
          rule: Sequence[int] = TEST_RULE) -> dict[str, Any]:  # fmt: skip
    import map_prep as mp
    import map_zones as mz
    from anim_region import stand_grid

    from poring_dataset import walkable as wk

    gat, _both = wk.load_both(map_name)
    ok = np.asarray(stand_grid(map_name, gat), dtype=bool)
    try:
        zones = mz.load(map_name, mz.ZONES_DIR, shape=ok.shape)
    except mz.ZoneError as e:
        raise SystemExit(f"watch_lattice refused: the zones file: {e}") from None
    no_enter = (np.zeros_like(ok) if zones is None
                else np.asarray(mz.no_enter_mask(zones, ok.shape), dtype=bool))  # fmt: skip
    stands = stands_mask(ok, no_enter, min_clear)
    cells = lattice_points(stands, step, snap)
    parts = split(cells, avoid, rule)
    keep = parts["train"] + parts["test"]
    why = mp.stand_check(map_name, [list(c) for c in keep]) if keep else "no stand"
    if why:
        raise SystemExit(f"watch_lattice refused (nothing written): {why}")
    out_dir.mkdir(parents=True, exist_ok=True)
    for name in ("train", "test"):
        rows = [{"x": x, "y": y} for x, y in parts[name]]
        (out_dir / f"lattice-{name}.json").write_text(json.dumps(rows) + "\n")
    gat_path = wk.GAT_DIR / f"{map_name}.gat"
    doc = {
        "map": map_name,
        "rule": {
            "step": step,
            "min_clear": min_clear,
            "snap": snap,
            "avoid": list(avoid) if avoid else None,
            "test_rule": list(rule),
        },
        "sources": {
            "gat_sha256": _sha(gat_path),
            "zones_sha256": None if zones is None else zones.sha256,
        },
        "stand_cells": int(stands.sum()),
        "lattice": len(cells),
        "train": len(parts["train"]),
        "test": len(parts["test"]),
        "avoided": len(parts["avoided"]),
        "three_checks": "pass",
        "files": {n: str(out_dir / f"lattice-{n}.json") for n in ("train", "test")},
    }
    for name in ("train", "test"):
        doc[f"{name}_sha256"] = _sha(out_dir / f"lattice-{name}.json")
    (out_dir / "lattice.json").write_text(json.dumps(doc, indent=1) + "\n")
    return doc


def _ints(text: str, n: int) -> tuple[int, ...]:
    v = tuple(int(t) for t in text.split(","))
    if len(v) != n:
        raise argparse.ArgumentTypeError(f"{n} comma-separated integers, not {text!r}")
    return v


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)  # fmt: skip
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build")
    b.add_argument("--map", required=True)
    b.add_argument("--out-dir", type=Path, required=True)
    b.add_argument("--step", type=int, default=STEP)
    b.add_argument("--min-clear", type=int, default=MIN_CLEAR)
    b.add_argument("--snap", type=int, default=SNAP)
    b.add_argument("--avoid", type=lambda t: _ints(t, 4), default=None,
                   help="x,y,dx,dy (default: the map's AVOID entry)")  # fmt: skip
    b.add_argument("--test-rule", type=lambda t: _ints(t, 3), default=TEST_RULE)
    a = ap.parse_args(argv)
    if not str(a.out_dir).startswith("/dev/shm/"):
        raise SystemExit("watch_lattice: --out-dir under /dev/shm (client-derived, never the repo)")
    avoid = a.avoid if a.avoid is not None else AVOID.get(a.map)
    doc = build(a.map, a.out_dir, step=a.step, min_clear=a.min_clear, snap=a.snap, avoid=avoid,
                rule=a.test_rule)  # fmt: skip
    print(json.dumps(doc, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
