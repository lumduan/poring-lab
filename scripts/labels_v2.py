#!/usr/bin/env python3
"""Labels v2 tooling (docs/planning/labels-v2-plan.md, PROPOSED; Batt 2026-10-09 ~16:55: "plan +
tooling only; collection and training wait"). OFFLINE ONLY: banked sessions and the local KB; no
GPU, no client, no NAS walk, nothing written outside --out / stdout.

    labels_v2.py scope [--maps M ...] [--names] [--kb DIR]
        The species scope of the planned maps (KB spawns + metamorphosis, by mob id), each with
        the trained flag and the PROPOSED difficulty class. --names prints the local KB's names
        (stdout only; never paste them into a committed file).
    labels_v2.py budget [--maps M ...] [--kb DIR]
        training-cost.md's estimate (poring_flow.prep.estimate, training_cost.json) per block of
        the plan, NEW species and NEW maps only, in the plan's order, and cumulatively.
    labels_v2.py coverage SESSION [SESSION ...] [--every N] [--out JSON] [common options]
        Per class / species (mob id) / NPC sprite (job): the banked frames where the packets place
        it on screen, the frames a v2 cache could train on, and why the others are excluded.
    labels_v2.py labels SESSION [--limit N] [common options]
        Every banked frame's v2 labels as JSON lines (no pixels).
    labels_v2.py negatives SESSION [SESSION ...] [--scene-log PATH ...] [common options]
        Detector phantoms (the session's detections.jsonl; the HUD scene log over the session's
        window) checked against the packets: unit / warp / ui / cut-in / BACKGROUND, and the
        accepted ones clustered into decoration SITES (map cells).
    labels_v2.py verify-region SESSION [SESSION ...] --region x0,y0,x1,y1 [common options]
        One fixed region (a phantom's box) checked on every banked frame by the same rule.
    labels_v2.py warp-measure SESSION [SESSION ...] [--out-dir DIR] [common options]
        Per confirmed portal on screen in the banked frames: crops aligned on its projected cell
        at one depth, their median and a sheet (PNG in /dev/shm), the bright extent as a hint. A
        person reads them: the warp's visibility and the ring's radius.

    labels_v2.py npc-sheet SESSION [SESSION ...] --npc-sprites DIR --npc-sprite-names JSON
                           [--jobs ID ...] [--per-sprite N] [--tau T] [--out-dir DIR]
                           [common options]
        N3 PREPARATION (labels-v2-plan 1.2): per catalogued NPC sprite on screen in the banked
        frames, a contact sheet of frame crops with predict_sprite's box drawn (PNG in /dev/shm,
        client pixels, never committed) and label_check's NCC per sighting (the M5 metric;
        --tau, default M4's 0.092, is a reference line only). A PERSON judges the sheets.
        --jobs: only those NPC sprite ids. Images: a demo session's frames, or a RECORDED PNG
        session's tar shards (each named session's own shards, every --every-th frame, only the
        frames that show a scored sprite are read). A recorded H.264 session is NOT decoded
        here: it is listed as without images.

Common options: --kb DIR (route.json, classes.json; default <repo>/data/kb), --offset-ms MS (the
packet->frame delay; default: qa_export.auto_offset_ms for the session's backend), --npc-extents
JSON (job -> [x0, y0, x1, y1] sprite px, measured), --npc-sprites DIR + --npc-sprite-names JSON
(job -> sprite file stem; client data decoded into /dev/shm at run time), --cutin-rect
x0,y0,x1,y1 (overrides scripts/ui_mask.py's measured CUTIN_GUIDE, e.g. for a re-measure),
--k K (the sprite scale for monster and NPC sprite boxes; default qa_export's, nostalro; v1's
cache and build_frame_cache's v1 replay use 0.14),
--warp-visibility JSON (warp key "map:x,y" -> visible | occluded | partial; a person's reading of
warp-measure's sheets; local, never committed).

Sessions: a DEMO session (/dev/shm/poring-lab-demo/<id>: packets.jsonl.gz + snapshots referenced
by demo.jsonl FrameRefs, and/or frames/<n>-<t_ns>.png), or a RECORDED H.264 session (manifest +
stream.idx.csv + packets; every --every-th usable frame, read from the index only, never decoded).

Every number this prints is derived from packets + the camera model; no client pixels, names or
menu text leave the machine through it (the scope's --names is stdout only).
"""

from __future__ import annotations

import argparse
import gzip
import json
import re
import statistics
import sys
import tarfile
from collections import Counter, defaultdict
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from poring_dataset import labels_v2 as lv  # noqa: E402
from poring_dataset.camera import map_key  # noqa: E402
from poring_dataset.labels import labels_for  # noqa: E402
from poring_dataset.timeline import FrameWorld  # noqa: E402
from poring_dataset.ui_layout import UI_RECTS  # noqa: E402

SIZE = (1280, 720)
# The plan's blocks, in the collection order (labels-v2-plan.md section 3). The visual-diversity
# maps are kb_build.py's (Batt 2026-10-09): moc_fild12, pay_fild08, xmas, gl_prison.
BLOCKS: dict[str, tuple[str, ...]] = {
    "byalan": ("iz_dun00", "iz_dun01"),
    "payon": ("payon", "pay_fild08"),
    "morroc": ("moc_fild12",),
    "lutie": ("xmas", "xmas_fild01"),
    "glast_heim": ("gl_prison",),
    "byalan_deeper": ("iz_dun02", "iz_dun03", "iz_dun04"),
}
# What v0 / v1 trained on (the v1png-20261008 sessions: prt_fild08 + prt_church; phase3-plan.md
# section 2): the prt_fild08 species and Creamy, seen there (Pupa's metamorphosis).
TRAINED = frozenset({1002, 1063, 1008, 1113, 1018})
PREPARED_MAPS = frozenset({"prt_fild08", "prt_church"})
# Cut-ins by NPC (labels_v2.npc_key: map, job, cell; NO names). "measured": scripts/ui_mask.py
# holds the region (CUTIN_GUIDE); None: measured to show none (ui_mask.py, 2026-10-09).
# The PHANTOM v0-PNG boxed "monster 0.31" on the guide's cut-in (the hand on the spear): measured on
# the banked talk-cal frames, 120 / 120 open frames (ui_mask.py's measurement, 2026-10-09).
CUTIN_PHANTOM_GUIDE = (984.0, 599.0, 1033.0, 644.0)
CUTINS: dict[str, str | None] = {
    "prontera:105:154,187": "measured",  # the prontera city guide
    "prt_church:67:103,76": None,
    "prt_church:120:103,71": None,
}


# --- the KB ---------------------------------------------------------------------------------------


def load_json(path: Path) -> Any:
    return json.loads(path.read_text())


def difficulty(mob: dict[str, Any] | None, boss: bool) -> str:
    """The PROPOSED d_s class (training-cost.md section 4): a boss / MVP is boss_multi_form; no AI
    type (plants, eggs: no walk, no attack) is static; everything else normal. "similar" (a
    palette / size variant of a trained species) needs the sprite catalog: Batt's call, per
    species."""
    if boss or "Mvp" in ((mob or {}).get("modes") or []):
        return "boss_multi_form"
    if mob is not None and mob.get("ai") is None:
        return "static"
    return "normal"


def scope(kb: Path, maps: Sequence[str]) -> dict[str, Any]:
    import kb_build

    spawns = load_json(kb / "spawns.json")
    mobs = {int(k): v for k, v in load_json(kb / "mobs.json").items()}
    skills = {int(k): v for k, v in load_json(kb / "mob_skills.json").items()}
    classes = kb_build.classes_for(list(maps), spawns, skills, mobs)
    out: dict[str, Any] = {}
    for m in maps:
        bosses = {int(s["id"]) for s in spawns.get(m, []) if s.get("boss")}
        rows = {}
        for mid_s, row in classes.get(m, {}).items():
            mid = int(mid_s)
            rows[mid] = {"slots": row["slots"], "via": row["via"], "trained": mid in TRAINED,
                         "difficulty": difficulty(mobs.get(mid), mid in bosses),
                         "name": row.get("name")}  # fmt: skip
        out[m] = {"in_kb": m in spawns, "species": rows}
    return out


def cmd_scope(a: argparse.Namespace) -> int:
    maps = a.maps or [m for ms in BLOCKS.values() for m in ms]
    sc = scope(a.kb, maps)
    if not a.names:
        for row in sc.values():
            for r in row["species"].values():
                r.pop("name", None)
    print(json.dumps(sc, indent=1, default=str))
    return 0


def cmd_budget(a: argparse.Namespace) -> int:
    from poring_flow.prep import estimate

    blocks = {b: ms for b, ms in BLOCKS.items() if not a.maps or set(ms) & set(a.maps)}
    seen_species: set[int] = set(TRAINED)
    seen_maps: set[str] = set(PREPARED_MAPS)
    total: dict[str, float] = defaultdict(float)
    rows = []
    for name, maps in blocks.items():
        sc = scope(a.kb, maps)
        new: dict[int, str] = {}
        for m in maps:
            for mid, r in sc[m]["species"].items():
                if mid not in seen_species:
                    new[mid] = r["difficulty"]
        new_maps = [m for m in maps if m not in seen_maps]
        est = estimate(new, new_maps)
        seen_species |= set(new)
        seen_maps |= set(new_maps)
        row = {"block": name, "maps": list(maps), "new_maps": new_maps,
               "new_species": {str(k): v for k, v in sorted(new.items())}, "sum_d": est.sum_d,
               "map_prep_h": round(est.map_prep_h, 2), "collect_s2_h": round(est.collect_s2_h, 2),
               "train_compute_h": round(est.train_compute_h, 2),
               "wall_h": {k: round(v, 1) for k, v in est.wall_h.items()},
               "status": est.status}  # fmt: skip
        for k in ("sum_d", "map_prep_h", "collect_s2_h", "train_compute_h"):
            total[k] += float(row[k])  # type: ignore[arg-type]
        rows.append(row)
    print(json.dumps({"blocks": rows, "total": {k: round(v, 2) for k, v in total.items()}},
                     indent=1))  # fmt: skip
    return 0


# --- sessions: frames and their capture times -----------------------------------------------------


def load_events(session: Path) -> list[dict[str, Any]]:
    with gzip.open(session / "packets.jsonl.gz", "rt") as fh:
        return [json.loads(line) for line in fh]


def banked_frames(session: Path, every: int = 15) -> list[tuple[int, Path | None]]:
    """(capture time t_ns, image or None) of every banked frame: frames/<n>-<t_ns>.png, the
    snapshots demo.jsonl references with a t_capture_ns, or a recorded H.264 session's index."""
    out: list[tuple[int, Path | None]] = []
    frames = session / "frames"
    if frames.is_dir():
        for p in sorted(frames.glob("*.png")):
            out.append((int(p.stem.rsplit("-", 1)[1]), p))
    demo = session / "demo.jsonl"
    if demo.exists():
        seen: set[str] = set()
        for line in demo.read_text().splitlines():
            rec = json.loads(line)
            for key in ("frame", "frame_after"):
                f = rec.get(key) or {}
                ref, t = f.get("ref"), f.get("t_capture_ns")
                if ref and t and ref not in seen:
                    seen.add(ref)
                    out.append((int(t), session / ref))
    idx = session / "stream.idx.csv"
    if not out and idx.exists():
        from poring_dataset.h264 import read_index

        units = read_index(idx)
        out = [(u.t_ns, None) for u in units[::every]]
    return sorted(out, key=lambda r: r[0])


# A frame inside a recorded PNG session's tar shard: "<shard path>@<data offset>+<size>".
SHARD_REF = re.compile(r"^(?P<path>.+\.tar)@(?P<offset>\d+)\+(?P<size>\d+)$")


def shard_frames(session: Path, every: int = 1) -> list[tuple[int, str]]:
    """(capture time t_ns, SHARD_REF) of every ``every``-th frame of a RECORDED PNG session (its
    manifest's tar ``shards``, counted in json-member order as build_frame_cache's
    recorded_times does). Only tar headers and the chosen frames' json members are read; no
    image. [] for any other session."""
    mpath = session / "manifest.json"
    manifest = load_json(mpath) if mpath.exists() else {}
    if manifest.get("kind") == "demo" or (manifest.get("format") or "png") != "png":
        return []
    out: list[tuple[int, str]] = []
    n = 0
    for shard in manifest.get("shards") or []:
        path = session / shard
        pngs: dict[str, tuple[int, int]] = {}
        with tarfile.open(path) as tar:
            for m in tar:
                key, _, ext = m.name.partition(".")
                if ext == "png":
                    pngs[key] = (m.offset_data, m.size)
                    continue
                if ext != "json":
                    continue
                n += 1
                if (n - 1) % every or key not in pngs:
                    continue
                fh = tar.extractfile(m)
                assert fh is not None
                meta = json.loads(fh.read())
                off, size = pngs[key]
                out.append((int(meta["t_mono_ns"]), f"{path}@{off}+{size}"))
    return sorted(out, key=lambda r: r[0])


def open_frame(ref: str) -> Any:
    """A frame image (PIL) from a file path or a SHARD_REF (one seek + read of its PNG bytes)."""
    import io

    from PIL import Image

    m = SHARD_REF.match(ref)
    if m is None:
        return Image.open(ref)
    size = int(m["size"])
    with open(m["path"], "rb") as fh:
        fh.seek(int(m["offset"]))
        data = fh.read(size)
    if len(data) != size:
        raise ValueError(f"{ref}: short read ({len(data)} of {size} bytes)")
    return Image.open(io.BytesIO(data))


class Session:
    """A banked session's labeller: qa_export.Labeler (v1, the same camera / offset / GM windows /
    filters) + the v2 additions."""

    def __init__(self, path: Path, a: argparse.Namespace) -> None:
        import qa_export
        import talk_calibrate

        qa_export.KB_CLASSES = a.kb / "classes.json"
        # the client's own sprite stems first (1011, 1051, 1053, 1184 differ from the aegis name)
        qa_export.KB_SPRITE_NAMES = a.kb / "monster_sprite_names.json"
        self.path = path
        manifest = load_json(path / "manifest.json")
        self.backend = str(manifest.get("backend") or "rdp")
        self.events = load_events(path)
        # a RECORDED session (H.264, or PNG shards without an index: its manifest carries the game
        # region) has its own recording manifest; until 2026-10-10 a PNG one fell to the demo
        # branch below, whose console offset lookup has no client name and failed
        if (path / "stream.idx.csv").exists() or "game_region" in manifest:
            self.labeler = qa_export.Labeler(path, labels="v1")
        else:
            offset = a.offset_ms
            if offset is None:
                client = "xfreerdp" if self.backend == "rdp" else None
                cfg = {"backend": self.backend, "client": {"name": client}}
                offset, _ = qa_export.auto_offset_ms(cfg)
            self.labeler = qa_export.Labeler.from_events(self.events, self.backend, SIZE,
                                                         float(offset), labels="v1")  # fmt: skip
        if getattr(a, "k", None) is not None:
            self.labeler.k = float(a.k)  # the sprite scale (monster and NPC sprite boxes)
        self.offset_ns = int(self.labeler.offset_ms * 1e6)
        self.route = load_json(a.kb / "route.json")
        self.dialog = talk_calibrate.dialog_timeline(self.events)
        self.contacts = sorted((int(e["t_mono_ns"]), int(e["npc_gid"])) for e in self.events
                               if e.get("type") == "npc_contact")  # fmt: skip
        self.measured = {int(k): tuple(v) for k, v in (load_json(a.npc_extents).items()
                                                        if a.npc_extents else [])}  # fmt: skip
        self.npc_sheet = npc_sheets(a.npc_sprites, a.npc_sprite_names)
        self.cutin_rect, self.cutin_available = cutin_region(a.cutin_rect)
        self.shape = lv.PORTAL_PROVISIONAL
        self.visibility: dict[str, str] = (load_json(a.warp_visibility) if a.warp_visibility
                                           else {})  # fmt: skip
        aid = self.labeler.timeline.inferred_aid or next(
            (int(e["aid"]) for e in self.events if e.get("type") == "login_accepted"), None
        )
        self.dead = lv.self_dead_spans(self.events, aid)

    def world(self, t: int) -> FrameWorld:
        return self.labeler.timeline.frame_world(t - self.offset_ns)

    def dialog_at(self, tw: int) -> bool:
        cur = None
        for t, lab in self.dialog:
            if t > tw:
                break
            cur = lab
        return bool(cur is not None and (cur.dialog or cur.menu))

    def contact_at(self, tw: int) -> int | None:
        gid = None
        for t, g in self.contacts:
            if t > tw:
                break
            gid = g
        return gid

    def frame(self, t: int) -> tuple[str, lv.Frame | None, Any]:
        """("ok" | "gm_window" | "no_world", the v2 frame, the scene)."""
        from poring_dataset.render import load_scene

        boxes = self.labeler.boxes(t)
        if boxes is None:
            return "gm_window", None, None
        world = self.world(t)
        if world.self_pos is None or not world.map:
            return "no_world", None, None
        lab = self.labeler
        projector, _which, yaw = lab.projectors[world.map]
        scene = load_scene(lab.camera, world.map, world.self_pos, indoor_table=lab.indoor)
        jobs = {e.gid: e.job for e in world.entities}
        units = lv.from_v1(boxes, jobs)
        hidden = [lv.V2Label(b.cls, b.x0, b.y0, b.x1, b.y1, gid=b.gid, job=jobs.get(b.gid),
                             kind="dropped")
                  for b in labels_for(world, projector, SIZE, camera_yaw=yaw, keep_all=True)
                  if b.kind == "dropped" and b.cls != "npc"]  # fmt: skip
        npcs = lv.npc_labels(world, scene, SIZE, sheet=self.npc_sheet, measured=self.measured,
                             k=lab.k)  # fmt: skip
        warps = lv.warp_labels(world, scene, SIZE, lv.l3_warps(self.route, world.map),
                               visibility=self.visibility, shape=self.shape)  # fmt: skip
        tw = t - self.offset_ns
        open_ = self.dialog_at(tw)
        key = None
        if open_:
            gid = self.contact_at(tw)
            ent = next((e for e in world.entities if e.gid == gid), None)
            key = lv.npc_key(world.map, ent) if ent is not None else None
        table = {k: (self.cutin_rect if v == "measured" else None) for k, v in CUTINS.items()}
        missing = () if self.cutin_available else [k for k, v in CUTINS.items() if v == "measured"]
        cut = lv.cutin_for(open_, key, table, unavailable=missing)
        dead = ("self_dead",) if any(a <= tw <= b for a, b in self.dead) else ()
        me = lv.self_label(world, scene)
        units = [*units, me] if me is not None else units  # Batt ~19:30: our GM IS "player"
        return "ok", lv.assemble(t, world, units, npcs, warps, cut, hidden, dead), scene


def npc_sheets(directory: Path | None, names: Path | None) -> lv.NpcSheet:
    """job -> the NPC's SpriteSheet from ``directory`` (<stem>.act + .spr, decoded at run time into
    /dev/shm; never committed) by ``names`` (job -> stem). Without both: no sheets."""
    if directory is None or names is None:
        return lambda job: None
    from poring_dataset.render import SpriteSheet
    from poring_dataset.sprites import parse_act, parse_spr

    stems = {int(k): str(v) for k, v in load_json(names).items()}
    cache: dict[int, Any] = {}

    def sheet(job: int) -> Any:
        if job not in cache:
            stem = stems.get(job)
            cache[job] = None
            if stem:
                act, spr = directory / f"{stem}.act", directory / f"{stem}.spr"
                if act.exists() and spr.exists():
                    cache[job] = SpriteSheet(parse_act(act.read_bytes()),
                                             parse_spr(spr.read_bytes()))  # fmt: skip
        return cache[job]

    return sheet


def cutin_region(override: str | None) -> tuple[lv.Rect | None, bool]:
    """The guide's measured cut-in: --cutin-rect, else scripts/ui_mask.py's CUTIN_GUIDE (merged
    2834541); unavailable (fail closed: those dialog frames are excluded) if it cannot load."""
    if override:
        x0, y0, x1, y1 = (float(v) for v in override.split(","))
        return (x0, y0, x1, y1), True
    try:
        import ui_mask
    except ImportError:
        return None, False
    x0, y0, x1, y1 = (float(v) for v in ui_mask.CUTIN_GUIDE)
    return (x0, y0, x1, y1), True


def frame_dict(fr: lv.Frame) -> dict[str, Any]:
    def lab(x: lv.V2Label) -> dict[str, Any]:
        return {"cls": x.cls, "box": [round(v, 1) for v in x.box], "gid": x.gid, "job": x.job,
                "kind": x.kind, "source": x.source}  # fmt: skip

    return {"t_ns": fr.t_ns, "map": fr.map, "trainable": fr.trainable,
            "excluded": list(fr.excluded), "labels": [lab(x) for x in fr.labels],
            "shadow": [lab(x) for x in fr.shadow],
            "cutin": {"open": fr.cutin.open, "rect": fr.cutin.rect, "npc": fr.cutin.npc},
            "l3_only": [[w.x, w.y] for w in fr.l3_only]}  # fmt: skip


# --- coverage / labels ----------------------------------------------------------------------------


def session_coverage(s: Session, every: int) -> tuple[lv.Coverage, int]:
    cov = lv.Coverage()
    frames = banked_frames(s.path, every)
    for t, _img in frames:
        status, fr, _ = s.frame(t)
        if fr is None:
            cov.frames += 1
            if status == "gm_window":
                cov.gm_window += 1
            else:
                cov.no_world += 1
            continue
        cov.add(fr)
        if fr.cutin.rect is not None:  # section 2a: the shown cut-in, verified against the packets
            # Batt 2026-10-09 ~19:30: verify the PHANTOM's region, not the whole extent (a guild
            # flag stands behind the guide's cut-in on every open frame: 0 / 120 qualified)
            region = lv.intersect(CUTIN_PHANTOM_GUIDE, fr.cutin.rect)
            if region is not None:
                v = lv.verify_region(region, fr.projected, SIZE, cutin=fr.cutin.rect,
                                     allow_cutin=True)  # fmt: skip
                cov.cutin_verified += int(v.accepted)
    return cov, len(frames)


def cmd_coverage(a: argparse.Namespace) -> int:
    total = lv.Coverage()
    per: dict[str, Any] = {}
    no_sheet: dict[int, str] = {}  # species on screen whose sprite was not found: v0's box
    for p in a.sessions:
        s = Session(p, a)
        cov, n = session_coverage(s, a.every)
        per[p.name] = cov.as_dict()
        total.merge(cov)
        sheets = getattr(s.labeler, "sheets", None)
        no_sheet.update(getattr(sheets, "missing", {}) or {})
        print(json.dumps({"session": p.name, "frames": n, **cov.as_dict()}), flush=True)
    out = {"total": total.as_dict(), "sessions": per,
           "sprite_lookup_missing": {str(k): v for k, v in sorted(no_sheet.items())}}  # fmt: skip
    if no_sheet:
        print(f"WARNING: {len(no_sheet)} species without a sprite sheet keep v0's box: "
              f"{out['sprite_lookup_missing']}", file=sys.stderr)  # fmt: skip
    print(json.dumps({"total": total.as_dict(), "sprite_lookup_missing":
                      out["sprite_lookup_missing"]}, indent=1))  # fmt: skip
    if a.out:
        a.out.write_text(json.dumps(out, indent=1) + "\n")
    return 0


def cmd_labels(a: argparse.Namespace) -> int:
    s = Session(a.session, a)
    for i, (t, img) in enumerate(banked_frames(a.session, a.every)):
        if a.limit and i >= a.limit:
            break
        status, fr, _ = s.frame(t)
        row: dict[str, Any] = {"t_ns": t, "image": img.name if img else None, "status": status}
        if fr is not None:
            row.update(frame_dict(fr))
        print(json.dumps(row))
    return 0


# --- negatives: phantoms from the logs, checked against the packets -------------------------------


def detections_candidates(session: Path) -> list[lv.Candidate]:
    """detections.jsonl (walk runs from 2026-10-09): each row is logged AFTER its detection; its
    frame came ``ms`` earlier (npc_click_score's reading). Boxes: [x0, y0, x1, y1, score, cls]."""
    p = session / "detections.jsonl"
    out = []
    for line in p.read_text().splitlines() if p.exists() else []:
        d = json.loads(line)
        t = int(d["t_ns"] - float(d.get("ms", 0.0)) * 1e6)
        for b in d.get("boxes") or []:
            out.append(lv.Candidate(t, (float(b[0]), float(b[1]), float(b[2]), float(b[3])),
                                    str(b[5]), float(b[4]), "detections"))  # fmt: skip
    return out


def scene_candidates(
    log: Path, t0: int, t1: int, size: tuple[int, int] = SIZE
) -> list[lv.Candidate]:
    """The HUD scene log (scripts/hud_scene.py; desktop-normalized, world objects drawn at box +
    the frame's motion offset): every unit ADDED or MOVED in [t0, t1], in game px. The zone object
    (kind "zone", the game region) gives the desktop -> game transform."""
    gw, gh = size
    zone: tuple[float, float, float, float] | None = None
    offset = (0.0, 0.0)
    anchors: dict[int, str] = {}
    out: list[lv.Candidate] = []

    def px(box: dict[str, float], anchor: str) -> lv.Rect | None:
        if zone is None:
            return None
        ox, oy = offset if anchor == "world" else (0.0, 0.0)
        x0 = (box["x"] + ox - zone[0]) / zone[2] * gw
        y0 = (box["y"] + oy - zone[1]) / zone[3] * gh
        return (x0, y0, x0 + box["w"] / zone[2] * gw, y0 + box["h"] / zone[3] * gh)

    with log.open() as fh:
        for line in fh:
            try:
                msg = json.loads(line)["msg"]
            except (ValueError, KeyError):
                continue
            t = int(msg.get("t_mono_ns") or 0)
            if t > t1:
                break
            if "offset" in msg:
                offset = (float(msg["offset"]["x"]), float(msg["offset"]["y"]))
            typ = msg.get("type")
            objs: list[dict[str, Any]] = []
            if typ == "hud_scene":
                for o in msg.get("objects") or []:
                    anchors[int(o["id"])] = str(o["anchor"])
                    if o["kind"] == "zone":
                        b = o["box"]
                        zone = (float(b["x"]), float(b["y"]), float(b["w"]), float(b["h"]))
                objs = [o for o in msg.get("objects") or [] if o.get("kind") == "unit"]
            elif typ == "hud_delta":
                for o in msg.get("add") or []:
                    anchors[int(o["id"])] = str(o["anchor"])
                objs = [o for o in msg.get("add") or [] if o.get("kind") == "unit"]
                objs += [{**o, "cls": "", "anchor": anchors.get(int(o["id"]), "world")}
                         for o in msg.get("move") or []]  # fmt: skip
            if t < t0:
                continue
            for o in objs:
                box = px(o["box"], str(o.get("anchor") or anchors.get(int(o["id"]), "world")))
                if box is not None:
                    out.append(lv.Candidate(t, box, str(o.get("cls") or "unit"), o.get("conf"),
                                            "hud_scene"))  # fmt: skip
    return out


def cmd_negatives(a: argparse.Namespace) -> int:
    reasons: Counter[str] = Counter()
    by_source: Counter[str] = Counter()
    points: list[lv.Sighting] = []
    for p in a.sessions:
        s = Session(p, a)
        man = load_json(p / "manifest.json")
        cands = detections_candidates(p)
        for log in a.scene_log or []:
            cands += scene_candidates(log, int(man["t0_mono_ns"]), int(man.get("t1_mono_ns")
                                                                       or 1 << 62))  # fmt: skip
        for c in cands:
            by_source[c.source] += 1
            status, fr, scene = s.frame(c.t_ns)
            if fr is None:
                reasons[status] += 1
                continue
            v = lv.verify_region(c.box, fr.projected, SIZE, cutin=fr.cutin.rect)
            reasons[v.reason] += 1
            if not v.accepted or fr.map is None:
                continue
            world = s.world(c.t_ns)
            foot = ((c.box[0] + c.box[2]) / 2, c.box[3])
            g = lv.ground_offset(scene.camera, *foot)
            if g is None or world.self_pos is None:
                continue
            sx, sy = world.self_pos
            points.append(lv.Sighting(map_key(fr.map), sx + g[0], sy + g[1], float(c.conf or 0.0),
                                      (c.box[2] - c.box[0], c.box[3] - c.box[1]),
                                      (round(sx), round(sy))))  # fmt: skip
    sites = lv.cluster_sites(points)
    print(json.dumps({
        "candidates": dict(by_source), "verdicts": dict(reasons),
        "sites": [{"map": st.map, "cell": [round(st.x, 1), round(st.y, 1)], "n": st.n,
                   "positions": st.positions, "accepted": st.accepted,
                   "conf": [round(min(q.conf for q in st.sightings), 3),
                            round(max(q.conf for q in st.sightings), 3)],
                   "box_wh_median": [round(statistics.median(q.wh[0] for q in st.sightings), 1),
                                     round(statistics.median(q.wh[1] for q in st.sightings), 1)]}
                  for st in sites],
    }, indent=1))  # fmt: skip
    return 0


def cmd_verify_region(a: argparse.Namespace) -> int:
    """One fixed screen region (e.g. a phantom's box on the cut-in) on every banked frame: the
    labels-v2.md section 2 verdict (background / cutin / unit / warp / ui / off_screen), split by
    whether the cut-in is shown."""
    x0, y0, x1, y1 = (float(v) for v in a.region.split(","))
    counts: Counter[str] = Counter()
    for p in a.sessions:
        s = Session(p, a)
        for t, _img in banked_frames(p, a.every):
            status, fr, _ = s.frame(t)
            if fr is None:
                counts[status] += 1
                continue
            v = lv.verify_region((x0, y0, x1, y1), fr.projected, SIZE, cutin=fr.cutin.rect,
                                 allow_cutin=True)  # fmt: skip
            shown = "cutin_shown" if fr.cutin.rect is not None else "no_cutin"
            counts[f"{shown}:{v.reason}:{'accepted' if v.accepted else 'rejected'}"] += 1
    print(json.dumps(dict(sorted(counts.items())), indent=1))
    return 0


# --- warp-measure: the portal's extent from the banked frames -------------------------------------


GM_MASK = (-60, -140, 60, 30)  # around the camera target (our feet): the GM, its bubble, its bars


def aligned_crop(img: np.ndarray, anchor: Sequence[float], scale: float, half: int,
                 masks: Sequence[lv.Rect]) -> np.ndarray | None:  # fmt: skip
    """A (2 half + 1)^2 grey crop centred on ``anchor``, each output pixel sampled at anchor +
    offset x ``scale`` (nearest): every crop at the reference depth. NaN outside the frame and
    where ``masks`` cover (the GM, units, UI); None when the anchor itself is off the frame."""
    h, w = img.shape[:2]
    if not (0 <= anchor[0] < w and 0 <= anchor[1] < h):
        return None
    grey = img.astype(np.float32).mean(axis=2) if img.ndim == 3 else img.astype(np.float32)
    offs = np.arange(-half, half + 1, dtype=np.float32) * scale
    xs = np.round(anchor[0] + offs).astype(int)
    ys = np.round(anchor[1] + offs).astype(int)
    crop = np.full((len(ys), len(xs)), np.nan, dtype=np.float32)
    okx, oky = (xs >= 0) & (xs < w), (ys >= 0) & (ys < h)
    crop[np.ix_(oky, okx)] = grey[np.ix_(ys[oky], xs[okx])]
    for x0, y0, x1, y1 in masks:
        cols = (xs >= x0) & (xs <= x1)
        rows = (ys >= y0) & (ys <= y1)
        crop[np.ix_(rows, cols)] = np.nan
    return crop


class _AllVisible(dict[str, str]):
    """warp-measure looks at EVERY confirmed portal on screen, whatever the table says."""

    def get(self, key: str, default: Any = None) -> str:  # type: ignore[override]
        return "visible"


def cmd_warp_measure(a: argparse.Namespace) -> int:
    """Per confirmed portal (L3 + packets) on screen in the banked frames: the crops aligned on its
    projected cell at one depth (the GM, other units and the UI masked), their median, a sheet of
    the crops (PNG, --out-dir in /dev/shm: client pixels, never committed), and the bright
    component's extent as a HINT. A PERSON reads the sheet and the median: the warp's visibility
    ("visible" / "occluded" / "partial", the --warp-visibility table) and the ring's radius
    (PortalShape)."""
    from PIL import Image

    out_dir = a.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    # warp key -> [(image, anchor px, px per world unit, masks)]
    Item = tuple[Path, tuple[float, float], float, list[lv.Rect]]
    stacks: dict[str, list[Item]] = defaultdict(list)
    for p in a.sessions:
        s = Session(p, a)
        s.visibility = _AllVisible()
        for t, img_path in banked_frames(p):
            if img_path is None:
                continue
            _status, fr, scene = s.frame(t)
            if fr is None or scene is None:
                continue
            world = s.world(t)
            cam = scene.camera
            masks = [(cam.cx + GM_MASK[0], cam.cy + GM_MASK[1], cam.cx + GM_MASK[2],
                      cam.cy + GM_MASK[3])]  # fmt: skip
            masks += [(u.x0 - 10, u.y0 - 10, u.x1 + 10, u.y1 + 10)
                      for u in fr.projected if u.cls != "warp"]  # fmt: skip
            masks += [(float(x), float(y), float(x + w), float(y + h)) for x, y, w, h in UI_RECTS]
            for lab in (x for x in fr.labels if x.cls == "warp"):
                ent = next(e for e in world.entities if e.gid == lab.gid)
                (u, v), z = lv.project_cell(scene, (ent.x, ent.y))
                key = lv.warp_key(fr.map, ent.x, ent.y)
                stacks[key].append((img_path, (u, v), lv.px_per_world(scene, z), masks))
    result = []
    for key, items in sorted(stacks.items()):
        s_ref = float(np.median([it[2] for it in items]))
        crops = []
        for img_path, anchor, s_px, masks in items:
            img = np.asarray(Image.open(img_path).convert("RGB"))
            crop = aligned_crop(img, anchor, s_px / s_ref, a.half, masks)
            if crop is not None:
                crops.append(crop)
        row: dict[str, Any] = {"warp": key, "frames": len(items), "crops": len(crops),
                               "px_per_world_ref": round(s_ref, 3)}  # fmt: skip
        if crops:
            med = lv.median_crop(crops, min_valid=min(3, len(crops)))
            ext = lv.bright_extent(med, (a.half, a.half))
            row["bright_extent_px"] = ext
            if ext is not None:
                row["bright_extent_world"] = [round(v / s_ref, 2) for v in ext]
                row["bright_half_width_world"] = round((ext[2] - ext[0]) / 2 / s_ref, 2)
            name = key.replace(":", "_").replace(",", "_")
            grey = [np.nan_to_num(c, nan=0.0) for c in crops[:12]]
            sheet = np.concatenate([np.nan_to_num(med, nan=0.0), *grey], axis=1)
            Image.fromarray(np.clip(sheet, 0, 255).astype(np.uint8)).save(out_dir / f"{name}.png")
            row["sheet"] = str(out_dir / f"{name}.png")
        result.append(row)
    pv = lv.PORTAL_PROVISIONAL
    print(json.dumps({"warps": result, "provisional_radius_world": pv.radius}, indent=1))
    return 0


# --- npc-sheet: N3's material for a person -------------------------------------------------------

M5_TAU = 0.092  # label_check's tau, fixed from M4's clean standing frames (phase3-plan.md)
SHEET_MARGIN = 24  # px of context around a box in a crop
TILE_H = 220  # every crop scaled to this height on the sheet


def pick_spread(items: Sequence[Any], n: int) -> list[Any]:
    """Up to ``n`` items spread evenly over the (time-sorted) list, first and last included."""
    if n <= 0 or not items:
        return []
    if len(items) <= n:
        return list(items)
    step = (len(items) - 1) / (n - 1) if n > 1 else 0
    return [items[round(i * step)] for i in range(n)]


def sighting_rows(items: Sequence[dict[str, Any]], tau: float) -> dict[str, Any]:
    """The per-sprite numbers: sightings, scored, the NCC median, how many fall below tau and why
    (label_check.classify's order: occluded, ui_covered, else low)."""
    scores = [it["ncc"] for it in items if it["ncc"] is not None]
    low = [it for it in items if it["ncc"] is not None and it["ncc"] < tau]
    return {
        "sightings": len(items),
        "sessions": len({it["session"] for it in items}),
        "maps": sorted({str(it.get("map")) for it in items}),
        "scored": len(scores),
        "ncc_median": round(statistics.median(scores), 3) if scores else None,
        "ncc_p10": round(float(np.percentile(scores, 10)), 3) if scores else None,
        "below_tau": len(low),
        "below_tau_occluded": sum(1 for it in low if it["why_low"] == "occluded"),
        "below_tau_ui": sum(1 for it in low if it["why_low"] == "ui_covered"),
    }


def draw_sheet(items: Sequence[dict[str, Any]], path: Path, cols: int = 4) -> None:
    """Crops (box + SHEET_MARGIN) with the predicted box in green and the NCC as a number."""
    from PIL import Image, ImageDraw

    tiles = []
    for it in items:
        img = open_frame(it["image"]).convert("RGB")
        x0, y0, x1, y1 = it["box"]
        cx0, cy0 = max(0, int(x0) - SHEET_MARGIN), max(0, int(y0) - SHEET_MARGIN)
        cx1 = min(img.width, int(x1) + SHEET_MARGIN)
        cy1 = min(img.height, int(y1) + SHEET_MARGIN)
        crop = img.crop((cx0, cy0, cx1, cy1))
        d = ImageDraw.Draw(crop)
        d.rectangle((x0 - cx0, y0 - cy0, x1 - cx0, y1 - cy0), outline=(0, 255, 0), width=1)
        f = TILE_H / max(1, crop.height)
        crop = crop.resize((max(1, round(crop.width * f)), TILE_H), Image.Resampling.NEAREST)
        label = "-" if it["ncc"] is None else f"{it['ncc']:.2f}"
        d = ImageDraw.Draw(crop)
        d.rectangle((0, 0, 8 + 7 * len(label), 15), fill=(0, 0, 0))
        d.text((3, 2), label, fill=(255, 255, 0))
        tiles.append(crop)
    if not tiles:
        return
    w = max(t.width for t in tiles)
    rows = (len(tiles) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * (w + 4), rows * (TILE_H + 4)), (40, 40, 40))
    for i, t in enumerate(tiles):
        sheet.paste(t, ((i % cols) * (w + 4), (i // cols) * (TILE_H + 4)))
    path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(path)


def s_k(a: argparse.Namespace) -> float | str:
    """The sprite scale the sheets were drawn at (--k, else qa_export's default)."""
    k = getattr(a, "k", None)
    return float(k) if k is not None else "default (qa_export, nostalro)"


def cmd_npc_sheet(a: argparse.Namespace) -> int:
    """N3 material: per NPC sprite (job) seen in the banked frames, its sightings scored with M5's
    NCC and a contact sheet for a person. Uses the labels' own path (Session.frame), so a sheet
    shows exactly the boxes a v2 cache would train on."""
    import label_check

    from poring_dataset.render import Actor, MonsterAction, predict_sprite

    if a.npc_sprites is None or a.npc_sprite_names is None:
        print("npc-sheet needs --npc-sprites DIR and --npc-sprite-names JSON", file=sys.stderr)
        return 2
    out_dir: Path = a.out_dir
    jobs = frozenset(getattr(a, "jobs", None) or ())
    by_job: dict[int, list[dict[str, Any]]] = defaultdict(list)
    skipped: list[str] = []
    no_images: list[str] = []  # a recorded H.264 session: its index only, never decoded here
    for p in a.sessions:
        if not (p / "packets.jsonl.gz").exists():
            skipped.append(p.name)  # no packets: no labels to show
            continue
        frames = [(t, str(i)) for t, i in banked_frames(p) if i is not None]
        frames = frames or shard_frames(p, a.every)
        if not frames:
            no_images.append(p.name)
            continue
        s = Session(p, a)
        for t, img_path in frames:
            _status, fr, scene = s.frame(t)
            if fr is None or scene is None:
                continue
            world = s.world(t)
            ents = {e.gid: e for e in world.entities}
            img = None
            for lab in fr.labels:
                if lab.cls != "npc" or not lab.kind.startswith("sprite_") or lab.gid not in ents:
                    continue
                ent = ents[lab.gid]
                if jobs and int(ent.job) not in jobs:
                    continue
                sheet = s.npc_sheet(ent.job)
                pred = predict_sprite(Actor((float(ent.x), float(ent.y)),
                                            int(ent.heading or 0) % 8, MonsterAction.IDLE),
                                      sheet, scene, s.labeler.k)  # fmt: skip
                if pred is None:
                    continue
                if img is None:
                    img = np.asarray(open_frame(img_path).convert("RGB"))
                ncc = label_check.score(img, sheet, pred)
                others = [(u.x0, u.y0, u.x1, u.y1) for u in fr.projected if u.gid != lab.gid]
                why = label_check.classify(pred.box, others) if ncc is not None else None
                by_job[int(ent.job)].append({
                    "session": p.name, "t_ns": t, "image": img_path,
                    "map": map_key(fr.map or ""), "key": lv.npc_key(fr.map, ent),
                    "box": [round(v, 1) for v in pred.box],
                    "ncc": None if ncc is None else round(ncc, 3), "why_low": why,
                })  # fmt: skip
    result = []
    for job, items in sorted(by_job.items()):
        items.sort(key=lambda it: (it["session"], it["t_ns"]))
        row = {"job": job, **sighting_rows(items, a.tau)}
        chosen = pick_spread(items, a.per_sprite)
        sheet_path = out_dir / f"npc_{job}.png"
        draw_sheet(chosen, sheet_path)
        row["sheet"] = str(sheet_path)
        row["shown"] = [{k: it[k] for k in ("session", "t_ns", "key", "ncc")} for it in chosen]
        result.append(row)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "npc_sheet.json").write_text(
        json.dumps({"tau": a.tau, "k": s_k(a), "sessions_without_images": no_images,
                    "sprites": result, "sightings": by_job}, indent=1, default=str)
        + "\n"
    )  # fmt: skip
    print(json.dumps({"tau_reference": a.tau, "sessions_without_packets": len(skipped),
                      "sessions_without_images": no_images,
                      "sprites": [{k: v for k, v in r.items() if k != "shown"} for r in result]},
                     indent=1))  # fmt: skip
    print(f"sheets + JSON (client pixels; never committed): {out_dir}")
    return 0


# --- main -----------------------------------------------------------------------------------------


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--kb", type=Path, default=ROOT / "data" / "kb")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("scope")
    p.add_argument("--maps", nargs="*")
    p.add_argument("--names", action="store_true")
    p = sub.add_parser("budget")
    p.add_argument("--maps", nargs="*")

    def common(q: argparse.ArgumentParser) -> None:
        q.add_argument("--offset-ms", type=float, default=None)
        q.add_argument("--npc-extents", type=Path, default=None)
        q.add_argument("--npc-sprites", type=Path, default=None)
        q.add_argument("--npc-sprite-names", type=Path, default=None)
        q.add_argument("--cutin-rect", default=None)
        q.add_argument("--warp-visibility", type=Path, default=None)
        q.add_argument("--every", type=int, default=15)
        q.add_argument("--k", type=float, default=None, help="sprite scale (default nostalro)")

    p = sub.add_parser("coverage")
    p.add_argument("sessions", nargs="+", type=Path)
    p.add_argument("--out", type=Path, default=None)
    common(p)
    p = sub.add_parser("labels")
    p.add_argument("session", type=Path)
    p.add_argument("--limit", type=int, default=0)
    common(p)
    p = sub.add_parser("negatives")
    p.add_argument("sessions", nargs="+", type=Path)
    p.add_argument("--scene-log", nargs="*", type=Path, default=[])
    common(p)
    p = sub.add_parser("verify-region")
    p.add_argument("sessions", nargs="+", type=Path)
    p.add_argument("--region", required=True, help="x0,y0,x1,y1 client px")
    common(p)
    p = sub.add_parser("npc-sheet")
    p.add_argument("sessions", nargs="+", type=Path)
    p.add_argument("--per-sprite", type=int, default=8)
    p.add_argument("--tau", type=float, default=M5_TAU)
    p.add_argument("--jobs", nargs="*", type=int, default=None, help="only these NPC sprite ids")
    p.add_argument("--out-dir", type=Path,
                   default=Path("/dev/shm/poring-lab-tmp/labels-prep/n3"))  # fmt: skip
    common(p)
    p = sub.add_parser("warp-measure")
    p.add_argument("sessions", nargs="+", type=Path)
    p.add_argument("--half", type=int, default=110)
    p.add_argument("--out-dir", type=Path, default=Path("/dev/shm/poring-lab-tmp/labels-v2/warps"))
    common(p)
    a = ap.parse_args(argv)
    return {"scope": cmd_scope, "budget": cmd_budget, "coverage": cmd_coverage,
            "labels": cmd_labels, "negatives": cmd_negatives, "verify-region": cmd_verify_region,
            "warp-measure": cmd_warp_measure, "npc-sheet": cmd_npc_sheet}[a.cmd](a)  # fmt: skip


if __name__ == "__main__":
    sys.exit(main())
