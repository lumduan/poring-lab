#!/usr/bin/env python3
"""Are a map's server copies the same map in the CLIENT too? (labels v2, first workflow; Batt
2026-10-09: "map prep per LAYOUT (4), after verifying the copies are visually identical too
(RSW/GND/textures), not only the GAT").

    map_identity.py check [--grf PATH] [--kb data/kb/first_workflow.json | --group a,b,c ...]
                          [--mapcache-dir DIR] [--decode-mixcrypt] [--out JSON]
    map_identity.py gat MAP... [--grf PATH] [--out DIR] [--decode-mixcrypt]

How the client finds a map's files (the facts this tool reads; no client code):
  * it asks for `<map>.rsw`, `<map>.gnd` and `<map>.gat`, under data\\;
  * every resource name first goes through data\\resnametable.txt (`asked#opened#` lines,
    `//` comments): the client opens the right-hand name. The training grounds' 20 server maps
    new_N-M are ALIASES there (new_N-M.rsw -> new_zone0M.rsw, likewise .gnd and .gat);
  * the RSW names its GND and GAT and places models (RSM files under data\\model\\); the GND lists
    its ground textures (under data\\texture\\); an RSM 1.x model lists its own textures.

`check`, per group of copies (default: the KB's clone groups, i.e. maps whose SERVER walkability
grids are byte-identical):
  * IDENTICAL when every copy opens the same archive entries for its RSW, GND and GAT (one archive
    entry is one byte string, so every reference is the same too), or when the entries differ by
    name but their bytes and reference lists are equal;
  * DIFFERS otherwise, naming the file and how (entry, bytes, which references);
  * plus two facts per layout: every referenced texture / model is in the archive (or not), and the
    client GAT's walkable cells against the server's map cache for every copy.

`gat` writes `<out>/<map>.gat` for each server map name, resolved through the same table, so the
tools that look a GAT up by the server's name (poring_dataset.camera, render, kbsheet) find it; and
it says whether the client's indoor table (data\\indoorrswtable.txt) lists the map (indoor camera)
under either name.

Everything read here is CLIENT data: the archive is read in place, read-only (grf_read), only the
entries needed are decoded, and output goes to /dev/shm (rule 7). The JSON holds hashes and names
and stays local; a committed doc quotes verdicts and counts only (CLAUDE.md rule 4).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import struct
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, BinaryIO

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))
from grf_read import (  # noqa: E402
    FLAG_MIXCRYPT,
    Entry,
    GrfError,
    decodable,
    iter_entries,
    norm_name,
    read_entry,
    read_header,
    safe_out_dir,
)

DEFAULT_GRF = Path("/mnt/poring-thai-src/ro_thai/data.grf")  # the host's only client GRF (NAS, ro)
DEFAULT_KB = REPO / "data" / "kb" / "first_workflow.json"
DEFAULT_OUT = Path("/dev/shm/poring-lab-tmp/labels-prep/map_identity.json")
DEFAULT_GAT_OUT = Path("/dev/shm/poring-lab-tmp/gat/data")  # poring_dataset.camera.GAT_DIR
RESNAME = "data/resnametable.txt"
INDOOR = "data/indoorrswtable.txt"
QUADTREE_BYTES = 1365 * 48  # RSW >= 2.1: 1365 nodes of 4 vec3 (max, min, half size, centre)


class FormatError(ValueError):
    """Bytes that are not the format they claim, or a version this reader does not handle."""


# --- resnametable ---


def parse_resnametable(text: str) -> dict[str, str]:
    """`asked#opened#` lines -> {asked: opened}, names normalised (slashes, lower case). The first
    line for a name wins; `//` lines and lines without two fields are skipped."""
    out: dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("//"):
            continue
        parts = line.split("#")
        if len(parts) < 3 or not parts[0].strip() or not parts[1].strip():
            continue
        out.setdefault(norm_name(parts[0].strip()), norm_name(parts[1].strip()))
    return out


def resolve(table: dict[str, str], name: str) -> tuple[str, bool]:
    """The name the client opens for ``name`` (relative to its folder) and whether an alias
    applied."""
    key = norm_name(name.strip())
    if key in table:
        return table[key], table[key] != key
    return key, False


# --- formats (layouts from the public format descriptions; our own code) ---


def _cstr(raw: bytes) -> str:
    return raw.split(b"\x00", 1)[0].decode("cp949", errors="replace")


@dataclass
class Rsw:
    version: tuple[int, int]
    gnd: str
    gat: str
    models: list[str] = field(default_factory=list)  # RSM file names (data\model\...)
    lights: int = 0
    sounds: list[str] = field(default_factory=list)  # wav names
    effects: int = 0


def parse_rsw(data: bytes) -> Rsw:
    """RSW 1.x-2.5 (the object list; water/light/ground skipped by size). The parse must end exactly
    where the quad tree starts (>= 2.1) or at the end of the file, else it fails closed."""
    if data[:4] != b"GRSW":
        raise FormatError(f"magic {data[:4]!r}, not GRSW")
    major, minor = data[4], data[5]
    v = (major, minor)
    if v > (2, 5):
        raise FormatError(f"RSW {major}.{minor}: newer than this reader (2.5)")
    pos = 6
    if v >= (2, 5):
        pos += 4  # build number
    if v >= (2, 2):
        pos += 1  # an unknown byte
    names = []
    for _ in range(4 if v >= (1, 4) else 3):
        names.append(_cstr(data[pos : pos + 40]))
        pos += 40
    gnd, gat = names[1], names[2]
    if v >= (1, 3):
        pos += 4  # water level
        if v >= (1, 8):
            pos += 16  # type, wave height, speed, pitch
            if v >= (1, 9):
                pos += 4  # animation speed
    if v >= (1, 5):
        pos += 32  # longitude, latitude, diffuse 3f, ambient 3f
        if v >= (1, 7):
            pos += 4  # shadow opacity
    if v >= (1, 6):
        pos += 16  # ground top, bottom, left, right
    try:
        (count,) = struct.unpack_from("<i", data, pos)
    except struct.error as exc:
        raise FormatError("RSW ends before its object count") from exc
    pos += 4
    if not 0 <= count <= 200_000:
        raise FormatError(f"RSW object count {count}: corrupt or misread header")
    out = Rsw(v, gnd, gat)
    for i in range(count):
        if pos + 4 > len(data):
            raise FormatError(f"RSW ends inside object {i}")
        (kind,) = struct.unpack_from("<i", data, pos)
        pos += 4
        if kind == 1:  # model
            if v >= (1, 3):
                pos += 40 + 12  # name, anim type, anim speed, block type
            out.models.append(_cstr(data[pos : pos + 80]))
            pos += 80 + 80 + 36  # file name, node name, position, rotation, scale
        elif kind == 2:  # light
            pos += 80 + 12 + 12 + 4
            out.lights += 1
        elif kind == 3:  # sound
            out.sounds.append(_cstr(data[pos + 80 : pos + 160]))
            pos += 80 + 80 + 12 + 4 + 4 + 4 + 4 + (4 if v >= (2, 0) else 0)
        elif kind == 4:  # effect
            pos += 80 + 12 + 4 + 4 + 16
            out.effects += 1
        else:
            raise FormatError(f"RSW object {i}: unknown type {kind}")
    rest = len(data) - pos
    want = QUADTREE_BYTES if v >= (2, 1) else 0
    if rest != want:
        raise FormatError(f"RSW objects end {rest} bytes before the end (want {want})")
    return out


@dataclass
class Gnd:
    version: tuple[int, int]
    width: int
    height: int
    textures: list[str]


def parse_gnd(data: bytes) -> Gnd:
    """The GND header and texture list (the lightmaps / surfaces / cubes after it are not read)."""
    if data[:4] != b"GRGN":
        raise FormatError(f"magic {data[:4]!r}, not GRGN")
    if len(data) < 26:
        raise FormatError("GND shorter than its header")
    major, minor = data[4], data[5]
    width, height, _zoom, count, length = struct.unpack_from("<IIfII", data, 6)
    if not (0 <= count <= 10_000 and 0 < length <= 1024):
        raise FormatError(f"GND texture table {count} x {length}: corrupt")
    pos = 26
    if pos + count * length > len(data):
        raise FormatError("GND ends inside its texture table")
    tex = [_cstr(data[pos + i * length : pos + (i + 1) * length]) for i in range(count)]
    return Gnd((major, minor), width, height, tex)


def rsm_textures(data: bytes) -> tuple[str, list[str] | None]:
    """An RSM's version and its texture names (RSM 1.x); None for RSM 2.x (textures per mesh, not
    read here)."""
    if data[:4] != b"GRSM":
        raise FormatError(f"magic {data[:4]!r}, not GRSM")
    major, minor = data[4], data[5]
    ver = f"{major}.{minor}"
    if major >= 2:
        return ver, None
    pos = 6 + 8 + (1 if (major, minor) >= (1, 4) else 0) + 16
    (count,) = struct.unpack_from("<i", data, pos)
    if not 0 <= count <= 1000:
        raise FormatError(f"RSM texture count {count}: corrupt")
    pos += 4
    return ver, [_cstr(data[pos + 40 * i : pos + 40 * (i + 1)]) for i in range(count)]


# --- the archive ---


class Archive:
    """One GRF, its table indexed by normalised name, entries decoded on demand (memoised)."""

    def __init__(self, f: BinaryIO, entries: list[Entry], *, mixcrypt: bool = False) -> None:
        self.f = f
        self.by_name = {norm_name(e.name): e for e in entries if e.is_file}
        self.mixcrypt = mixcrypt
        self._cache: dict[str, bytes | None] = {}
        self.errors: dict[str, str] = {}

    @classmethod
    def open(cls, f: BinaryIO, *, mixcrypt: bool = False) -> Archive:
        return cls(f, list(iter_entries(f, read_header(f))), mixcrypt=mixcrypt)

    def has(self, name: str) -> bool:
        return norm_name(name) in self.by_name

    def flags(self, name: str) -> int | None:
        e = self.by_name.get(norm_name(name))
        return None if e is None else e.flags

    def read(self, name: str) -> bytes | None:
        """The decoded bytes, or None (missing, or encrypted and not decodable; see .errors)."""
        key = norm_name(name)
        if key in self._cache:
            return self._cache[key]
        e = self.by_name.get(key)
        data = None
        if e is None:
            self.errors[key] = "missing"
        elif not decodable(e, decode_des=True, decode_mixcrypt=self.mixcrypt):
            kind = "MIXCRYPT" if e.flags & FLAG_MIXCRYPT else "encrypted"
            self.errors[key] = f"refused: {kind} (pass --decode-mixcrypt: study only)"
        else:
            try:
                data = read_entry(self.f, e, decode_des=True, decode_mixcrypt=self.mixcrypt)
            except GrfError as exc:
                self.errors[key] = f"unreadable: {exc}"
        self._cache[key] = data
        return data

    def sha256(self, name: str) -> str | None:
        data = self.read(name)
        return None if data is None else hashlib.sha256(data).hexdigest()


# --- one map, one group ---


def map_files(table: dict[str, str], name: str) -> dict[str, dict[str, Any]]:
    """{ext: {"asked", "opens" (archive name), "alias"}} for the map's RSW, GND and GAT."""
    out = {}
    for ext in ("rsw", "gnd", "gat"):
        asked = f"{name}.{ext}"
        opened, alias = resolve(table, asked)
        out[ext] = {"asked": asked, "opens": "data/" + opened, "alias": alias}
    return out


def map_record(arc: Archive, table: dict[str, str], name: str) -> dict[str, Any]:
    """Everything the client opens for one server map name, with hashes and references."""
    files = map_files(table, name)
    rec: dict[str, Any] = {"map": name, "files": files, "problems": []}
    for info in files.values():
        info["in_archive"] = arc.has(info["opens"])
        info["sha256"] = arc.sha256(info["opens"])
        if info["sha256"] is None:
            rec["problems"].append(f"{info['opens']}: {arc.errors.get(info['opens'], '?')}")
    rsw_raw = arc.read(files["rsw"]["opens"])
    gnd_name = files["gnd"]["opens"]
    if rsw_raw is not None:
        try:
            rsw = parse_rsw(rsw_raw)
        except FormatError as exc:
            rec["problems"].append(f"rsw: {exc}")
        else:
            rec["rsw"] = {
                "version": f"{rsw.version[0]}.{rsw.version[1]}",
                "gnd": rsw.gnd, "gat": rsw.gat, "lights": rsw.lights, "effects": rsw.effects,
                "models": sorted(set(norm_name(m) for m in rsw.models)),
                "model_instances": len(rsw.models),
                "sounds": sorted(set(norm_name(s) for s in rsw.sounds)),
            }  # fmt: skip
            named = "data/" + resolve(table, rsw.gnd)[0]
            if named != gnd_name:
                rec["problems"].append(f"the RSW names {named}, the alias opens {gnd_name}")
    gnd_raw = arc.read(gnd_name)
    if gnd_raw is not None:
        try:
            gnd = parse_gnd(gnd_raw)
        except FormatError as exc:
            rec["problems"].append(f"gnd: {exc}")
        else:
            rec["gnd"] = {
                "version": f"{gnd.version[0]}.{gnd.version[1]}", "size": [gnd.width, gnd.height],
                "textures": [norm_name(t) for t in gnd.textures],
            }  # fmt: skip
    return rec


def references(arc: Archive, table: dict[str, str], rec: dict[str, Any]) -> dict[str, Any]:
    """The referenced files of one map record: archive names, presence, hashes; models' textures."""
    tex: dict[str, Any] = {}
    models: dict[str, Any] = {}

    def texture(name: str) -> None:
        if name in tex:
            return
        full = "data/texture/" + resolve(table, name)[0]
        tex[name] = {"opens": full, "in_archive": arc.has(full), "sha256": arc.sha256(full)}

    for t in rec.get("gnd", {}).get("textures", []):
        texture(t)
    for m in rec.get("rsw", {}).get("models", []):
        full = "data/model/" + resolve(table, m)[0]
        row: dict[str, Any] = {"opens": full, "in_archive": arc.has(full), "sha256": None}
        data = arc.read(full)
        if data is not None:
            row["sha256"] = hashlib.sha256(data).hexdigest()
            try:
                ver, names = rsm_textures(data)
            except FormatError as exc:
                row["problem"] = str(exc)
            else:
                row["rsm"] = ver
                row["textures"] = None if names is None else [norm_name(n) for n in names]
                for n in names or []:
                    texture(norm_name(n))
        models[m] = row
    return {"textures": tex, "models": models}


def _unread(rows: dict[str, Any]) -> int:
    return sum(1 for r in rows.values() if r["sha256"] is None)


def compare_group(recs: list[dict[str, Any]], refs: list[dict[str, Any]]) -> dict[str, Any]:
    """IDENTICAL / DIFFERS for one group of copies (see the module doc)."""
    first, base = recs[0], refs[0]
    diffs: list[str] = []
    same_entries = all(
        r["files"][ext]["opens"] == first["files"][ext]["opens"]
        for r in recs for ext in ("rsw", "gnd", "gat")
    )  # fmt: skip
    for r, ref in zip(recs[1:], refs[1:], strict=True):
        for ext in ("rsw", "gnd", "gat"):
            a, b = first["files"][ext], r["files"][ext]
            if a["opens"] != b["opens"] and (a["sha256"] is None or a["sha256"] != b["sha256"]):
                how = "unreadable" if a["sha256"] is None or b["sha256"] is None else "bytes"
                diffs.append(f"{r['map']}.{ext}: opens {b['opens']}, not {a['opens']} ({how})")
        for kind in ("textures", "models"):
            ka, kb = set(base[kind]), set(ref[kind])
            if ka != kb:
                diffs.append(
                    f"{r['map']} {kind}: +{sorted(kb - ka)[:5]} -{sorted(ka - kb)[:5]}"
                    f" ({len(kb - ka)} added, {len(ka - kb)} removed)"
                )
            for n in ka & kb:
                if base[kind][n]["sha256"] != ref[kind][n]["sha256"]:
                    diffs.append(f"{r['map']} {kind[:-1]} {n}: bytes differ")
    if same_entries:
        how = "every copy opens the same archive entries: " + ", ".join(
            sorted({first["files"][e]["opens"] for e in ("rsw", "gnd", "gat")})
        )
    else:
        how = "different entries, equal bytes and references"
    missing = sorted(
        {n for ref in refs for kind in ("textures", "models")
         for n, row in ref[kind].items() if not row["in_archive"]}
    )  # fmt: skip
    return {
        "maps": [r["map"] for r in recs],
        "verdict": "DIFFERS" if diffs else "IDENTICAL",
        "how": "; ".join(diffs[:20]) if diffs else how,
        "differences": diffs,
        "aliased": sum(1 for r in recs for e in ("rsw", "gnd", "gat") if r["files"][e]["alias"]),
        "ground_textures": len(first.get("gnd", {}).get("textures", [])),
        "textures": len(base["textures"]),  # ground + the models' own (RSM 1.x), distinct
        "models": len(base["models"]),
        "model_instances": first.get("rsw", {}).get("model_instances"),
        "missing_references": missing,
        "unread_references": _unread(base["textures"]) + _unread(base["models"]),
        "problems": sorted({p for r in recs for p in r["problems"]}),
    }


def server_agreement(gat_bytes: bytes | None, grid: Any) -> dict[str, Any]:
    """The client GAT's walkable cells against the server map cache's (poring_dataset.mapcache)."""
    if gat_bytes is None or grid is None:
        return {"compared": False, "why": "no GAT" if gat_bytes is None else "not in the cache"}
    import numpy as np

    from poring_dataset import gat as gatmod
    from poring_dataset.mapcache import NOT_WALKABLE

    g = gatmod.parse(gat_bytes)
    if (g.width, g.height) != (grid.xs, grid.ys):
        return {"compared": True, "size_match": False, "client": [g.width, g.height],
                "server": [grid.xs, grid.ys]}  # fmt: skip
    server = np.frombuffer(grid.cells, np.uint8).reshape(grid.ys, grid.xs)
    s_walk = ~np.isin(server, list(NOT_WALKABLE))
    c_walk = g.walkable()
    return {
        "compared": True, "size_match": True, "cells": int(server.size),
        "walkable_differ": int(np.count_nonzero(s_walk != c_walk)),
        "type_differ": int(np.count_nonzero(server != g.types)),
    }  # fmt: skip


def groups_from_kb(path: Path) -> list[list[str]]:
    doc = json.loads(path.read_text())
    return [list(g["maps"]) for g in doc.get("clone_groups", [])]


def check(
    grf: Path,
    groups: list[list[str]],
    *,
    mixcrypt: bool = False,
    mapcache_dir: Path | None = None,
) -> dict[str, Any]:
    grids = None
    if mapcache_dir is not None:
        from poring_dataset import mapcache

        grids = mapcache.load(mapcache_dir)
    out_groups = []
    with grf.open("rb") as f:
        arc = Archive.open(f, mixcrypt=mixcrypt)
        raw = arc.read(RESNAME)
        table = parse_resnametable(raw.decode("cp949", errors="replace")) if raw else {}
        for group in groups:
            recs = [map_record(arc, table, m) for m in group]
            refs = [references(arc, table, r) for r in recs]
            res = compare_group(recs, refs)
            res["server"] = {
                r["map"]: server_agreement(
                    arc.read(r["files"]["gat"]["opens"]),
                    None if grids is None else grids.get(r["map"]),
                )
                for r in recs
            }
            res["records"] = recs
            res["references"] = refs[0]
            out_groups.append(res)
    return {
        "grf": str(grf),
        "resnametable": {"read": raw is not None, "entries": len(table)},
        "groups": out_groups,
    }


def _server_cell(srv: dict[str, Any]) -> str:
    rows = list(srv.values())
    if not rows or not all(r.get("compared") for r in rows):
        return "not compared"
    if not all(r.get("size_match") for r in rows):
        return "SIZE DIFFERS"
    worst = max(r["walkable_differ"] for r in rows)
    return f"{len(rows)}/{len(rows)} copies, {worst} walkable cells differ (max)"


def report(doc: dict[str, Any]) -> str:
    """Verdicts and counts only (no hashes, no names beyond the map names)."""
    lines = [f"resnametable: {doc['resnametable']['entries']} entries"]
    for g in doc["groups"]:
        lines.append(
            f"{','.join(g['maps'])}: {g['verdict']} -- {g['how']}\n"
            f"    aliased files {g['aliased']}; textures {g['textures']} (ground "
            f"{g['ground_textures']}, the rest the models' own); RSW models "
            f"{g['models']} ({g['model_instances']} placed); missing references "
            f"{len(g['missing_references'])}; unread references {g['unread_references']}\n"
            f"    client GAT vs server map cache: {_server_cell(g['server'])}"
            + ("".join(f"\n    problem: {p}" for p in g["problems"]))
        )
    return "\n".join(lines)


# --- gat ---


def extract_gats(
    grf: Path, maps: list[str], out: Path, *, mixcrypt: bool = False
) -> list[dict[str, Any]]:
    """Write `<out>/<map>.gat` for each server map name (resolved through resnametable), and say
    whether the client's indoor table lists the map under the asked or the opened name."""
    out = safe_out_dir(out, allow_out=False)
    rows: list[dict[str, Any]] = []
    with grf.open("rb") as f:
        arc = Archive.open(f, mixcrypt=mixcrypt)
        raw = arc.read(RESNAME)
        table = parse_resnametable(raw.decode("cp949", errors="replace")) if raw else {}
        indoor_raw = arc.read(INDOOR)
        indoor = _indoor_names(indoor_raw) if indoor_raw is not None else None
        for m in maps:
            files = map_files(table, m)
            opened = files["gat"]["opens"]
            data = arc.read(opened)
            row: dict[str, Any] = {"map": m, "opens": opened, "alias": files["gat"]["alias"]}
            rsw_opened = files["rsw"]["opens"].removeprefix("data/").removesuffix(".rsw")
            row["indoor"] = None if indoor is None else bool({m, rsw_opened} & indoor)
            if data is None:
                row["error"] = arc.errors.get(opened, "?")
            else:
                dest = out / f"{m}.gat"
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(data)
                row.update(bytes=len(data), written=str(dest))
            rows.append(row)
        if indoor_raw is not None:
            (out / "indoorrswtable.txt").write_bytes(indoor_raw)
    return rows


def _indoor_names(raw: bytes) -> set[str]:
    """data\\indoorrswtable.txt: one `<map>.rsw#` per line, `//` comments (camera.py's reader)."""
    names = set()
    for line in raw.decode("latin-1").splitlines():
        s = line.split("//", 1)[0].strip().rstrip("#").strip().lower()
        if s:
            names.add(s.removesuffix(".rsw"))
    return names


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    pc = sub.add_parser("check")
    pc.add_argument("--grf", type=Path, default=DEFAULT_GRF)
    pc.add_argument("--kb", type=Path, default=DEFAULT_KB, help="clone_groups from this KB")
    pc.add_argument("--group", action="append", help="comma-separated copies (overrides --kb)")
    pc.add_argument("--mapcache-dir", type=Path, help="the server map caches (poring_dataset)")
    pc.add_argument("--out", type=Path, default=DEFAULT_OUT)
    pc.add_argument("--decode-mixcrypt", action="store_true", help="STUDY ONLY (grf_read)")
    pg = sub.add_parser("gat")
    pg.add_argument("maps", nargs="+")
    pg.add_argument("--grf", type=Path, default=DEFAULT_GRF)
    pg.add_argument("--out", type=Path, default=DEFAULT_GAT_OUT)
    pg.add_argument("--decode-mixcrypt", action="store_true", help="STUDY ONLY (grf_read)")
    a = ap.parse_args(argv)
    try:
        if a.cmd == "check":
            groups = [g.split(",") for g in a.group] if a.group else groups_from_kb(a.kb)
            if not groups:
                print("map_identity: no groups (pass --group or a KB with clone_groups)")
                return 2
            doc = check(a.grf, groups, mixcrypt=a.decode_mixcrypt, mapcache_dir=a.mapcache_dir)
            out = safe_out_dir(a.out.parent, allow_out=False) / a.out.name
            out.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n")
            print(report(doc))
            print(f"\nlocal JSON (hashes, client names; never committed): {out}")
            return 0 if all(g["verdict"] == "IDENTICAL" for g in doc["groups"]) else 1
        rows = extract_gats(a.grf, a.maps, a.out, mixcrypt=a.decode_mixcrypt)
        for r in rows:
            where = r.get("written") or f"NOT WRITTEN: {r.get('error')}"
            alias = f" (alias of {r['opens']})" if r["alias"] else ""
            print(f"{r['map']:12} indoor={r['indoor']}  {where}{alias}")
        return 0 if all("written" in r for r in rows) else 1
    except (GrfError, FormatError) as exc:
        print(f"map_identity: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
