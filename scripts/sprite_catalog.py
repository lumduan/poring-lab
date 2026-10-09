#!/usr/bin/env python3
"""The sprite catalog (Phase 3 M1, docs/phase3-plan.md §0): each candidate monster's SPR/ACT from
the client's GRF -- action groups, 8 directions, frames, delays, native size -- the coverage
checklist for M5-M7 and the frames predict_sprite draws (M2).

    uv run python scripts/sprite_catalog.py [--aegis PORING LUNATIC ...] [--grf PATH]
                                            [--work DIR] [--out data/kb/sprite_catalog.json]

Reads data\\sprite\\몬스터\\<aegis, lower case>.spr and .act READ-ONLY from the GRF with
scripts/grf_read.py (header-only DES decoded by grf_des.py). A MIXCRYPT entry is REFUSED and
REPORTED -- grf_read's C8 stop condition, never worked around -- and the catalog then falls back to
what the ACT alone gives. Extracted files go only under /dev/shm (--work); the catalog itself
(numbers and the ACT's event names, no pixels) goes to data/kb/ (gitignored). Both are
CLIENT-derived and never committed (CLAUDE.md rule 4).

NPC sprites (labels v2 N2, docs/planning/labels-v2-plan.md 1.2): --npc STEM ... or --npc-from
data/kb/npc_sprites.json (scripts/npc_sprites.py, N1) reads data\\sprite\\npc\\<stem>.spr / .act the
same way, into the same --work tree (data/sprite/npc/), and writes the same record format to
data/kb/npc_sprite_catalog.json (records keyed by the file stem, with the NPC ids that use it), so
render.SpriteSheet / predict_sprite and labels_v2.py --npc-sprites take them unchanged. An NPC's
action groups are not a monster's: group 0 is idle, the rest are named group<N>.

Boxes are native sprite px around the anchor (the actor's feet; x right, y down), x0 y0 x1 y1:
  * "opaque": the composed frame's alpha > 0 extent (needs the SPR);
  * "quad": the union of the layer quads from the ACT 2.5 sizes -- the images' extents, their
    transparent margins included, so never smaller than "opaque".
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, BinaryIO

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))
from grf_read import (  # noqa: E402
    FLAG_DES,
    FLAG_MIXCRYPT,
    Entry,
    GrfError,
    decodable,
    iter_entries,
    norm_name,
    read_entry,
    read_header,
    safe_out_dir,
    safe_relpath,
)

from poring_dataset.render import MonsterAction, SpriteSheet  # noqa: E402
from poring_dataset.sprites import (  # noqa: E402
    Act,
    Box,
    MissingImageSize,
    Spr,
    SpriteFormatError,
    parse_act,
    parse_spr,
)

DEFAULT_GRF = Path("/mnt/poring-thai-src/ro_thai/data.grf")  # the Thai client, NAS, read-only
DEFAULT_WORK = Path("/dev/shm/poring-lab-tmp/sprites")
DEFAULT_OUT = REPO / "data" / "kb" / "sprite_catalog.json"
DEFAULT_NPC_OUT = REPO / "data" / "kb" / "npc_sprite_catalog.json"
# prt_fild08 + Byalan F1-F2 (docs/phase3-plan.md §2, the pre-renewal spawn tables) + Creamy (seen)
DEFAULT_AEGIS = ("PORING", "LUNATIC", "PUPA", "DROPS", "CREAMY", "PLANKTON", "MARINA", "HYDRA",
                 "KUKRE", "VADON", "BLACK_MUSHROOM", "CORNUTUS")  # fmt: skip
MONSTER_DIR = "data/sprite/몬스터/"  # norm_name form of data\sprite\몬스터\ (CP949 in the GRF)
NPC_DIR = "data/sprite/npc/"
GROUP_NAMES = {a.value: a.name.lower() for a in MonsterAction}
NPC_GROUP_NAMES = {0: "idle"}  # an NPC ACT: idle first; its other groups are not a monster's


def _r(x: float) -> float:
    return round(float(x), 3)


def _box(b: Box | None) -> list[float] | None:
    return None if b is None else [_r(v) for v in b]


def _size(b: Box | None) -> list[float] | None:
    return None if b is None else [_r(b[2] - b[0]), _r(b[3] - b[1])]


def _read(
    f: BinaryIO, entry: Entry, work: Path | None, mixcrypt: bool = False
) -> tuple[bytes | None, dict[str, Any]]:
    """An entry's bytes (None when refused) and its record. Writes it under ``work`` if given."""
    info: dict[str, Any] = {
        "name": entry.name,
        "bytes": entry.size,
        "flags": f"0x{entry.flags:02x}",
    }
    if not decodable(entry, decode_des=True, decode_mixcrypt=mixcrypt):
        kind = "MIXCRYPT" if entry.flags & FLAG_MIXCRYPT else "encrypted"
        info["status"] = f"refused: {kind} (grf_read C8 stop; not worked around)"
        return None, info
    try:
        data = read_entry(f, entry, decode_des=True, decode_mixcrypt=mixcrypt)
    except GrfError as exc:
        info["status"] = f"unreadable: {exc}"
        return None, info
    info["status"] = "ok" + (
        " (MIXCRYPT decoded: study only)" if entry.flags & FLAG_MIXCRYPT
        else " (DES header decoded)" if entry.flags & FLAG_DES else ""
    )  # fmt: skip
    info["sha256"] = hashlib.sha256(data).hexdigest()
    if work is not None:
        dest = work / safe_relpath(entry.name)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
        info["extracted"] = str(dest)
    return data, info


def describe(act: Act, spr: Spr | None, names: dict[int, str] | None = None) -> dict[str, Any]:
    """The catalog record of one parsed sprite: per action group x direction, the motions, delays,
    every motion's box and the envelope."""
    sheet = SpriteSheet(act, spr)
    groups: list[dict[str, Any]] = []
    note = None
    for g in range(act.groups):
        dirs: list[dict[str, Any]] = []
        for d in range(8):
            ai = act.action_index(g, d)
            n = sheet.motions(ai)
            try:
                boxes = [sheet.extent(ai, m) for m in range(n)]
                env = sheet.envelope(ai)
            except MissingImageSize as exc:
                boxes, env, note = [None] * n, None, f"no boxes: {exc}"
            events = [[m, act.events[ev]] for m, ev in
                      ((m, mo.event_id) for m, mo in enumerate(act.actions[ai]))
                      if 0 <= ev < len(act.events)]  # fmt: skip
            dirs.append({
                "action_index": ai, "motions": n, "delay_units": _r(act.delay_units(ai)),
                "delay_ms": _r(act.delay_ms(ai)), "cycle_ms": _r(n * act.delay_ms(ai)),
                "layers": [len(mo.layers) for mo in act.actions[ai]],
                "boxes": [_box(b) for b in boxes], "envelope": _box(env),
                "envelope_size": _size(env), "events": events,
            })  # fmt: skip
        label = (GROUP_NAMES if names is None else names).get(g, f"group{g}")
        groups.append({"group": g, "name": label, "directions": dirs})
    idle = groups[0]["directions"][0] if groups else None
    first = None
    if idle is not None and idle["boxes"]:
        first = idle["boxes"][0]
    return {
        "act_version": f"{act.version[0]}.{act.version[1]}",
        "spr_version": None if spr is None else f"{spr.version[0]}.{spr.version[1]}",
        "image_count": None if spr is None else {
            "palette": spr.indexed_count, "rgba": len(spr.images) - spr.indexed_count},
        "actions": {"count": len(act.actions), "groups": len(act.actions) / 8},
        "events": list(act.events),
        "box_kind": sheet.box_kind,
        "idle_size": None if first is None else [_r(first[2] - first[0]), _r(first[3] - first[1])],
        "idle_box": first,
        "note": note,
        "groups": groups,
    }  # fmt: skip


def catalog(
    grf: Path,
    aegis: list[str],
    work: Path | None,
    mixcrypt: bool = False,
    folder: str = MONSTER_DIR,
) -> dict[str, Any]:
    """The whole catalog: one record per species (``work`` None: extract nothing to disk)."""
    if work is not None:
        work = safe_out_dir(work, allow_out=False)  # /dev/shm only, never the repository
    species: dict[str, Any] = {}
    with grf.open("rb") as f:
        entries = [e for e in iter_entries(f, read_header(f)) if e.is_file]
        by_name = {norm_name(e.name): e for e in entries}
        for name in aegis:
            base = folder + name.lower()
            rec: dict[str, Any] = {"aegis": name, "files": {}}
            data: dict[str, bytes | None] = {}
            for ext in ("act", "spr"):
                entry = by_name.get(f"{base}.{ext}")
                if entry is None:
                    rec["files"][ext] = {"status": "missing"}
                    data[ext] = None
                    continue
                data[ext], rec["files"][ext] = _read(f, entry, work, mixcrypt)
            if data["act"] is None and data["spr"] is None:
                needle = f"/{name.lower()}."
                rec["candidates"] = sorted(e.name for e in entries if needle in norm_name(e.name))
            act = spr = None
            for ext, raw in data.items():
                if raw is None:
                    continue
                try:
                    if ext == "act":
                        act = parse_act(raw)
                    else:
                        spr = parse_spr(raw)
                except SpriteFormatError as exc:
                    rec["files"][ext]["status"] = f"unparsed: {exc}"
            if act is not None:
                rec.update(describe(act, spr, NPC_GROUP_NAMES if folder == NPC_DIR else None))
            species[name] = rec
    return {
        "generated": datetime.now(UTC).isoformat(timespec="seconds"),
        "grf": str(grf),
        "folder": folder,
        "boxes": "native sprite px around the anchor (the feet), x right, y down: x0 y0 x1 y1",
        "species": species,
    }


def npc_jobs(table: dict[str, Any]) -> dict[str, list[int]]:
    """N1's table (scripts/npc_sprites.py) -> {file stem: [NPC ids drawn with it]}, own sprites
    only (a composite or a monster-sprite NPC has no file here)."""
    out: dict[str, list[int]] = {}
    for row in table.get("sprites", []):
        name = row.get("client_sprite")
        if row.get("sprite_class") == "npc" and name:
            out.setdefault(str(name).lower(), []).append(int(row["id"]))
    return out


def names_map(cat: dict[str, Any]) -> dict[str, str]:
    """{job: stem} for every catalogued NPC sprite whose ACT AND SPR were read (the files
    labels_v2.npc_sheets loads)."""
    out: dict[str, str] = {}
    for stem, rec in cat["species"].items():
        files = rec.get("files", {})
        if all(str(files.get(e, {}).get("status", "")).startswith("ok") for e in ("act", "spr")):
            for job in rec.get("jobs", []):
                out[str(job)] = stem
    return out


def _wh(size: list[float] | None) -> str:
    return "-" if size is None else f"{size[0]:g}x{size[1]:g}"


def summary(cat: dict[str, Any]) -> str:
    """A compact table: per species the versions, groups, frames and sizes (direction 0 = S)."""
    head = ("species", "ACT", "SPR", "actions", "frames i/w/a/h/d", "delay i/w/a/h/d (24ms)",
            "idle WxH", "envelope WxH idle | walk | attack | hurt | die", "box")  # fmt: skip
    rows = [head]
    for name, rec in cat["species"].items():
        spr = rec["files"].get("spr", {}).get("status", "?")
        spr_col = rec.get("spr_version") or ("MIXCRYPT" if "MIXCRYPT" in spr else spr.split(":")[0])
        if "groups" not in rec:
            rows.append(
                (name, "-", spr_col, "-", "-", "-", "-", rec["files"]["act"]["status"], "-")
            )
            continue
        dir0 = [g["directions"][0] for g in rec["groups"][:5]]
        rows.append((
            name, rec["act_version"], spr_col,
            f"{rec['actions']['count']} ({rec['actions']['groups']:g})",
            "/".join(str(d["motions"]) for d in dir0),
            "/".join(f"{d['delay_units']:g}" for d in dir0),
            _wh(rec["idle_size"]),
            " | ".join(_wh(d["envelope_size"]) for d in dir0),
            "none" if rec["note"] else rec["box_kind"],  # ACT < 2.5 and no SPR: no sizes at all
        ))  # fmt: skip
    widths = [max(len(str(r[i])) for r in rows) for i in range(len(head))]
    lines = ["  ".join(str(c).ljust(w) for c, w in zip(r, widths, strict=True)) for r in rows]
    lines.insert(1, "  ".join("-" * w for w in widths))
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--aegis", nargs="+", default=list(DEFAULT_AEGIS), help="AEGIS sprite names")
    ap.add_argument("--grf", type=Path, default=DEFAULT_GRF)
    ap.add_argument("--work", type=Path, default=DEFAULT_WORK, help="extract here (/dev/shm only)")
    ap.add_argument("--no-extract", action="store_true", help="read in memory, write no SPR/ACT")
    ap.add_argument("--out", type=Path, default=None, help=f"default {DEFAULT_OUT.name}, or "
                    f"{DEFAULT_NPC_OUT.name} with --npc / --npc-from")  # fmt: skip
    ap.add_argument(
        "--decode-mixcrypt", action="store_true",
        help="STUDY ONLY (Batt 2026-10-05): MIXCRYPT SPRs via the host-local decoder (grf_read)",
    )  # fmt: skip
    ap.add_argument("--npc", nargs="+", help="NPC sprite file stems (data\\sprite\\npc\\)")
    ap.add_argument("--npc-from", type=Path, help="N1's table (scripts/npc_sprites.py)")
    ap.add_argument("--names-out", type=Path, default=None,
                    help="NPC mode: job -> stem JSON for labels_v2.py --npc-sprite-names "
                         "(default data/kb/npc_sprite_names.json)")  # fmt: skip
    a = ap.parse_args(argv)
    npc_mode = bool(a.npc or a.npc_from)
    jobs: dict[str, list[int]] = {}
    if npc_mode:
        stems = list(a.npc or [])
        if a.npc_from:
            jobs = npc_jobs(json.loads(a.npc_from.read_text()))
            stems += [st for st in jobs if st not in stems]
        names, folder = stems, NPC_DIR
        out = a.out or DEFAULT_NPC_OUT
    else:
        names, folder, out = a.aegis, MONSTER_DIR, a.out or DEFAULT_OUT
    try:
        cat = catalog(a.grf, names, None if a.no_extract else a.work, a.decode_mixcrypt, folder)
    except GrfError as exc:
        print(f"sprite_catalog: {exc}", file=sys.stderr)
        return 2
    for stem, ids in jobs.items():
        if stem in cat["species"]:
            cat["species"][stem]["jobs"] = ids
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(cat, ensure_ascii=False, indent=1) + "\n")
    if npc_mode:
        names_out = a.names_out or out.with_name("npc_sprite_names.json")
        names_out.write_text(json.dumps(names_map(cat), indent=1) + "\n")
        print(f"job -> stem (labels_v2.py --npc-sprite-names): {names_out}")
    print(summary(cat))
    refused = [
        n for n, r in cat["species"].items()
        if any(f.get("status", "").startswith("refused") for f in r["files"].values())
    ]  # fmt: skip
    missing = [n for n, r in cat["species"].items() if "groups" not in r]
    if refused:
        print(f"\nREFUSED (encrypted, not worked around): {' '.join(refused)}")
    if missing:
        print(f"NO ACT: {' '.join(missing)} (see 'candidates' in the catalog)")
    print(f"\ncatalog: {out}")
    return 1 if missing else 0


if __name__ == "__main__":
    raise SystemExit(main())
