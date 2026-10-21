"""The /flows editor's ZONES layer: COMPUTATION ONLY (docs/planning/blocks-from-hunt-flow.md
section 3 and B2; ADR-0020 Amendment A 4, DRAFT; Batt D6 2026-10-21: "export only for now").

- The file ``config/map_zones/<map>.yaml`` and the RUNNER'S OWN loader (``scripts/map_zones.py``)
  stay the source of truth. Everything here calls the loader's functions -- ``parse``, the rasters,
  ``route_grid``, ``sealed_off`` -- and re-implements none of the geometry; the browser draws what
  this returns and computes no cell itself.
- ``check``: the loader's verdict on a YAML TEXT a person drew (never written anywhere): its error
  exactly as the CLI prints it, the sha256 of its bytes (what the loader hashes), the cells each
  item closes as the loader rasterises them, the search-area preview, and the diff against the
  file in ``config/map_zones``.
- ``read_file``: the file as the editor imports it: its items as written, its leading comment,
  the loader's verdict, and what the editor's form would not keep. It never fills ``reviewed_by``:
  the file's review is returned as a REFERENCE (a person types the review of what they export;
  the agent never approves a zone).
- ``provider``: the linter's zones provider (``scripts/flow_zones.py``, B1) for the lint and
  simulate routes.

The loader is imported lazily (``engine``): from the import path when it is there (the tests), else
from ``ZONES_CODE_DIR`` (compose.dev.yaml mounts ``./scripts`` read-only). Without it the zones
routes answer 503 ``zones_engine_unavailable`` and lint says zones references are unchecked.
"""

from __future__ import annotations

import difflib
import hashlib
import importlib
import sys
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]  # no stubs in the dev env

MAX_ITEM_CELLS = 50_000  # per item in a reply (the preview grid shows every cell anyway)
MAX_DIFF_CHARS = 200_000
MAX_GRID = 512 * 512  # as GET /flows/world's walk rows


@dataclass(frozen=True)
class Engine:
    mz: Any  # scripts/map_zones.py
    fz: Any  # scripts/flow_zones.py


def _import() -> Engine:
    mz = importlib.import_module("map_zones")
    fz = importlib.import_module("flow_zones")
    return Engine(mz, fz)


_CACHE: dict[str, Engine | None] = {}


def engine(code_dir: Path | None) -> Engine | None:
    """The runner's zones loader, or None. With ``code_dir`` the import path is restored exactly
    afterwards (map_zones puts its own directory first while it imports hunt_core): nothing in
    the backend ever resolves a module from the scripts directory but these two."""
    key = str(code_dir)
    if key in _CACHE:
        return _CACHE[key]
    out: Engine | None
    try:
        out = _import()
    except ImportError:
        out = None
        if code_dir is not None and (code_dir / "map_zones.py").is_file():
            before = list(sys.path)
            sys.path.append(str(code_dir))
            try:
                out = _import()
            except ImportError:
                out = None
            finally:
                sys.path[:] = before
    _CACHE[key] = out
    return out


def source_of(map_name: str) -> str:
    """How the CLI names the file in its messages, run from the repo: the loader's ``source``."""
    return f"config/map_zones/{map_name}.yaml"


def shape_of(rows: list[str] | None) -> tuple[int, int] | None:
    if not rows or len(rows) * len(rows[0]) > MAX_GRID:
        return None
    return (len(rows), len(rows[0]))


def parse_text(e: Engine, text: str, map_name: str, shape: tuple[int, int] | None) -> Any:
    """The loader on a text, as ``map_zones.load`` reads a file: the name check, YAML from the
    UTF-8 text, then ``parse`` with the map's shape. ZoneError with the CLI's own message."""
    mz = e.mz
    if not mz.MAP_NAME.fullmatch(map_name):
        raise mz.ZoneError(f"map name {map_name!r} is not a file name")
    src = source_of(map_name)
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise mz.ZoneError(f"{src}: not readable YAML ({exc})") from None
    return mz.parse(data, map_name, shape, source=src)


def _cells(mask: Any) -> list[list[int]]:
    import numpy as np

    ys, xs = np.nonzero(mask)
    return [[int(x), int(y)] for x, y in zip(xs, ys, strict=True)]


def _bounds(z: Any) -> tuple[int, int]:
    pts = [p for it in z.no_cross for p in it.points] + [p for it in z.no_enter for p in it.polygon]
    return (max((p[1] for p in pts), default=0) + 2, max((p[0] for p in pts), default=0) + 2)


def items_of(e: Engine, z: Any, shape: tuple[int, int] | None) -> list[dict[str, Any]]:
    """Each item and the cells it closes, by the loader's own rasters (one item at a time)."""
    mz = e.mz
    sh = shape or _bounds(z)
    out = []
    for kind, items in (("no_cross", z.no_cross), ("no_enter", z.no_enter)):
        for it in items:
            one = replace(z, no_cross=(it,), no_enter=()) if kind == "no_cross" else replace(
                z, no_cross=(), no_enter=(it,))  # fmt: skip
            mask = mz.no_cross_mask(one, sh) if kind == "no_cross" else mz.no_enter_mask(one, sh)
            cells = _cells(mask)
            pts = it.points if kind == "no_cross" else it.polygon
            out.append({
                "kind": kind, "id": it.id, "note": it.note, "points": [list(p) for p in pts],
                "cells": cells[:MAX_ITEM_CELLS], "cell_count": len(cells),
                "truncated": len(cells) > MAX_ITEM_CELLS,
            })  # fmt: skip
    return out


def area_of(e: Engine, z: Any, rows: list[str]) -> dict[str, Any]:
    """The search-area preview on the map's walk grid (the editor's map: the GAT walkability, not
    the runner's stand grid, which also keeps 10 cells off warps and NPCs): the zones' cells, the
    pieces they SEAL off (``sealed_off``) and the LARGEST connected piece left -- the runner draws
    its start cell from it (hunt_flow's start-cell rule). One string per y (rows[y][x], y north):
    ``.`` the largest piece, ``z`` closed by the zones, ``c`` cut off, ``o`` walkable elsewhere,
    `` `` not walkable."""
    import numpy as np

    mz = e.mz
    walk = np.array([[ch == "." for ch in r] for r in rows], dtype=bool)
    shape = walk.shape
    zone = (mz.no_cross_mask(z, shape) | mz.no_enter_mask(z, shape)) & walk
    after = mz.route_grid(walk, z)
    cut = mz.sealed_off(walk, after)
    rest = after & ~cut
    lab, sizes = mz._label8(rest)  # the loader's own 8-connected labelling (as its `prove`)
    main = lab == int(np.argmax(sizes)) if len(sizes) > 1 else np.zeros(shape, dtype=bool)
    grid = np.full(shape, " ", dtype="<U1")
    grid[walk] = "o"
    grid[main] = "."
    grid[cut] = "c"
    grid[zone] = "z"
    return {
        "rows": ["".join(r) for r in grid.tolist()],
        "walkable": int(walk.sum()),
        "zone_cells": int(zone.sum()),
        "cut_cells": int(cut.sum()),
        "main_cells": int(main.sum()),
        "other_cells": int((walk & ~zone & ~cut & ~main).sum()),
        "grid": (
            "the map's walk grid (the GAT walkability the editor shows); the runner's own "
            "search area also keeps 10 cells off warps and NPCs"
        ),
    }


def _diff(old: str | None, new: str, map_name: str) -> str:
    src = source_of(map_name)
    lines = difflib.unified_diff(
        (old or "").splitlines(keepends=True), new.splitlines(keepends=True),
        fromfile=f"a/{src}" if old is not None else "/dev/null",
        tofile=f"b/{src} (the editor's export)",
    )  # fmt: skip
    text = "".join(lines)
    return text if len(text) <= MAX_DIFF_CHARS else text[:MAX_DIFF_CHARS] + "\n... (cut)\n"


def committed(e: Engine, zones_dir: Path, map_name: str, shape: tuple[int, int] | None
              ) -> dict[str, Any]:  # fmt: skip
    """The file in config/map_zones (the checkout the backend sees, read-only): its text, sha256
    and the loader's own verdict (``map_zones.load``: a ``.yml`` beside it is refused too)."""
    mz = e.mz
    path = zones_dir / f"{map_name}.yaml"
    out: dict[str, Any] = {"exists": False, "path": source_of(map_name)}
    try:
        z = mz.load(map_name, zones_dir, shape)
        out["ok"], out["error"] = True, None
    except mz.ZoneError as exc:
        z = None
        out["ok"], out["error"] = False, str(exc).replace(str(path), source_of(map_name))
    if path.is_file():
        raw = path.read_bytes()
        out.update(exists=True, sha256=hashlib.sha256(raw).hexdigest(),
                   text=raw.decode("utf-8", errors="replace"))  # fmt: skip
        if z is not None:
            out["review"] = {"reviewed_by": z.reviewed_by, "reviewed": z.reviewed,
                             "delegation": z.delegation or None}  # fmt: skip
    return out


def check(e: Engine, text: str, map_name: str, rows: list[str] | None, zones_dir: Path
          ) -> dict[str, Any]:  # fmt: skip
    """The loader's verdict on the editor's YAML text, the preview and the diff (module doc)."""
    mz = e.mz
    shape = shape_of(rows)
    out: dict[str, Any] = {"map": map_name, "shape": [shape[1], shape[0]] if shape else None}
    try:
        raw = text.encode("utf-8")
    except UnicodeEncodeError:
        return {**out, "ok": False, "error": f"{source_of(map_name)}: not UTF-8 text"}
    out.update(sha256=hashlib.sha256(raw).hexdigest(), bytes=len(raw))
    if not mz.MAP_NAME.fullmatch(map_name):
        return {**out, "ok": False, "error": f"map name {map_name!r} is not a file name"}
    file = committed(e, zones_dir, map_name, shape)
    old = file.get("text") if file["exists"] else None
    out["committed"] = {k: v for k, v in file.items() if k != "text"}
    out["committed"]["same"] = file.get("sha256") == out["sha256"]
    out["diff"] = _diff(old, text, map_name)
    try:
        z = parse_text(e, text, map_name, shape)
    except mz.ZoneError as exc:
        return {**out, "ok": False, "error": str(exc)}
    out.update(ok=True, error=None, items=items_of(e, z, shape),
               review={"reviewed_by": z.reviewed_by, "reviewed": z.reviewed,
                       "delegation": z.delegation or None})  # fmt: skip
    out["area"] = area_of(e, z, rows) if shape is not None and rows else None
    if shape is None:
        out["notes"] = ["no walk grid for this map here: points are not bounded by the map and "
                        "the search-area preview is off (the CLI checks the bounds)"]  # fmt: skip
    return out


def _comment(text: str) -> tuple[list[str], list[str]]:
    """The leading comment block (consecutive ``#`` lines from the first line) as the editor's
    lines, and the lines its form would not keep the same."""
    lines = text.split("\n")
    out: list[str] = []
    notes: list[str] = []
    for i, ln in enumerate(lines):
        if not ln.startswith("#"):
            break
        if ln == "#":
            out.append("")
        elif ln.startswith("# "):
            out.append(ln[2:])
        else:
            out.append(ln[1:])
            notes.append(f"line {i + 1}: a comment the editor writes as '# ' + text")
    return out, notes


def read_file(e: Engine, zones_dir: Path, map_name: str, rows: list[str] | None
              ) -> dict[str, Any]:  # fmt: skip
    """The committed file for the editor to start from (module doc). The items come from the
    YAML as written (exact notes and points); the loader's verdict beside them."""
    shape = shape_of(rows)
    file = committed(e, zones_dir, map_name, shape)
    if not file["exists"]:
        return {"map": map_name, "file": file, "model": None, "notes": []}
    text = str(file["text"])
    comment, notes = _comment(text)
    model: dict[str, Any] | None = None
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError:
        data = None
    if isinstance(data, dict):
        items: list[dict[str, Any]] = []
        for kind, field in (("no_cross", "points"), ("no_enter", "polygon")):
            for it in data.get(kind) or []:
                if not isinstance(it, dict):
                    continue
                pts = it.get(field)
                if not isinstance(pts, list) or not all(
                    isinstance(p, list) and len(p) == 2 and all(type(c) is int for c in p)
                    for p in pts
                ):
                    notes.append(f"{kind} {it.get('id')!r}: points the editor cannot read")
                    continue
                pts = [list(p) for p in pts]
                if kind == "no_enter" and len(pts) > 3 and pts[-1] == pts[0]:
                    pts = pts[:-1]
                    why = "the explicit closing point is dropped (the editor's form, as the loader)"
                    notes.append(f"no_enter {it.get('id')!r}: {why}")
                items.append({"kind": kind, "id": str(it.get("id", "")),
                              "note": str(it.get("note", "")), "points": pts})  # fmt: skip
        body = text.split("\n")[len(comment) :]
        if any(ln.lstrip().startswith("#") for ln in body):
            notes.append("comments after the leading block are not kept by the editor")
        model = {"map": map_name, "comment": comment, "items": items}
    return {"map": map_name, "file": file, "model": model, "notes": notes}


def provider(e: Engine, zones_dir: Path, shapes: dict[str, tuple[int, int]]) -> Any:
    """The linter's zones provider over the committed files (scripts/flow_zones.py, B1)."""
    return e.fz.provider(zones_dir, shapes)
