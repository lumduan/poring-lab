#!/usr/bin/env python3
"""Build a training frame cache: TAR SHARDS on the NAS (Phase 3 Part D, Batt 2026-10-04).

    build_frame_cache.py --train S [S ...] --val S [S ...] [--test S [S ...]]
                         [--cache-id ID] [--every 15] [--max-per-session N] [--labels v0]
                         [--out /mnt/poring-lab-datasets/.framecache] [--shard-mb 512]
                         [--quality 95]

Batt's rules (2026-10-04): vision reads the NAS READ-ONLY, and a frame cache is SHARDED (large
files), never one file per frame on the shared disk. So:
- this runs on the HOST (it needs poring_dataset + PyAV; vision may not import them, test_guards);
- each session is decoded in ONE sequential pass (H264Session.iter_every: no seeking, the offline
  seek re-measure) or read shard by shard (PNG sessions); every ``--every``-th usable frame
  (freeze spans excluded) is kept;
- labels come from qa_export's Labeler (the same as /qa and label_iou: the backend's camera, the
  packet->frame offset, GM-command windows skipped). Frames on any map other than the session's
  scene maps (prt_fild08, prt_church; orcsdun01 since 2026-10-21) are skipped (p3-outdoor-b's
  stray minutes in prontera);
- frames are written as JPEG q95: the default again since Batt's decision of 2026-10-09 (the
  matched-batch rerun found no detection gain for PNG's ~5x storage; docs/benchmarks/
  v0-png-vs-jpeg.md). ``--image png`` gives the lossless PNG of 2026-10-06..09, which v1png keeps
  as pre-registered. Each frame + YOLO txt + json goes into ~512 MB tar shards under
  ``<out>/<cache_id>/``. That is a dot-directory on the NAS root: dataset_ship's
  sessions/status/prune skip it by design. Each shard is written as ``.part``, renamed, then
  re-hashed from the NAS (read back). Each session closes its own shards, so a session is either
  complete or absent;
- RESUMABLE (Batt, 2026-10-06: daytime caches pause when the IO guard trips, then resume):
  ``progress.json`` is rewritten after every finished session (its arguments, sessions and shard
  hashes). ``--resume`` refuses different arguments, checks every recorded shard's size on the
  NAS, deletes the interrupted session's leftovers (``.part`` and unrecorded shards), and goes on
  with the next session. A SIGINT (the guard's) just stops; nothing recorded is touched;
- the split is BY SESSION (adjacent frames leak). The gold hand-checked session goes to ``test``
  only.

Nothing lands on the root disk: frames are encoded in memory, and the shards go straight to the
NAS.

LABELS v2 (docs/planning/labels-v2-plan.md 3.3 step 1; PROPOSED plan, offline tooling):

    build_frame_cache.py --labels v2 --kb DIR --warp-visibility JSON [--npc-sprites DIR
                         --npc-sprite-names JSON] [--npc-checked JSON] [--npc-extents JSON]
                         [--allow-hold H ...] [--demo-root DIR] [--every-demo 1] [--dry-run] ...

- the labels are scripts/labels_v2.py's ``Session.frame`` (the same path as ``labels_v2.py
  coverage``: v1's players and monsters, our own GM as ``player``, NPCs per sprite, ``warp`` from
  L3 + packets + the person's visibility table, the cut-in as dynamic UI); the manifest's names
  are ``labels_v2.V2_CLASSES`` (player 0, monster 1, npc 2, warp 3);
- every frame is labelled completely or EXCLUDED, never written: ``Frame.excluded``'s reasons
  (npc_unsized, portal_unconfirmed, warp_partial, warp_visibility_unknown, l3_warp_unseen,
  cutin_unmeasured, cutin_region_unavailable, self_dead), plus this builder's FAIL-CLOSED gates:
  * ``map_not_in_kb:<map>``: the scene maps are EVERY map the KB covers (route.json's warp lists:
    an empty list = no portals; a map with no entry is unknown), not v0/v1's two;
  * ``gat_missing:<map>``: the map's GAT is not extracted (the projection would be flat ground);
  * HOLDS, each lifted only by ``--allow-hold`` once a person decides:
    ``gat_unverified:<map>`` (alberta, morocc: the client GAT differs from the server's, plan
    7.6) and ``npc_unchecked:<job>`` (an NPC sprite box no person has judged: plan 1.2's N3; the
    ``--npc-checked`` table, job or "map:job" -> "fit", admits it; any other verdict is
    ``npc_rejected:<job>`` and no hold lifts it);
- sessions: a banked DEMO session under --demo-root (/dev/shm/poring-lab-demo: its snapshots and
  frames/, every --every-demo-th, keyed by position), else the session under --datasets (a
  recorded session, as v0/v1, or a demo session already shipped there);
- ``--dry-run`` (v2 only): no shard, no manifest, no directory; no image is read. Prints per
  session and per split: frames seen / kept / excluded by reason, boxes per class, per species
  and per NPC sprite (ids and counts only, never names or pixels).

PER-SPECIES CLASSES (docs/planning/orcsdun01-detector.md section 4, Batt's default 2026-10-21):

    build_frame_cache.py --labels v2 --classes species [--class-list JSON] --kb DIR
                         [--warp-visibility JSON] ...

- the sprite scale is v1's k 0.14 unless --k says otherwise (the camera check's k);
- the class ids come from a COMMITTED list of ids only (config/detector/classes-v2orc.json: player
  0, npc 1, warp 2, then one class per monster species in the list's order); the names written to
  the cache manifest come from the local KB at run time (classes.json's aegis names);
- v2's labels and exclusions unchanged, plus (every frame labelled completely or EXCLUDED):
  ``species_unlisted:<job>`` (a monster of a species outside the list on screen),
  ``monster_unsized:<job>`` (a monster of a listed species without its sprite: v0's constant box
  would be wrong for it) and ``monster_unknown_species``;
- the warp class: without ``--warp-visibility`` (a person's measurement, labels v2) the table is
  EMPTY, so any frame with a drawn portal on screen is excluded (``warp_visibility_unknown``), never
  half-labelled; ``warp`` keeps its id with no box.

V1 RULES + THE SPECIES SPLIT (Batt, orcsdun01-detector.md 3b item 2, restated 2026-10-22 for 3f:
"v1's prt_fild08 data (v1 rules + species split)"):

    build_frame_cache.py --labels v1 --classes species --kb DIR [--class-list JSON] [--dry-run] ...

- v1's frames and boxes, unchanged (qa_export.Labeler v1: GM windows and off-scene frames skipped,
  no labels-v2 exclusion); only the class ids change: player / npc at the list's fixed ids, a
  monster at its species' id (its job from the frame's world);
- fail closed, the species split's own gates only: a frame with a monster of an unlisted or
  unknown species, or one drawn with v0's constant box (no sprite), is excluded
  (``excluded_species`` per session); v1 has no warp boxes, so ``warp`` stays empty there;
- ``--dry-run``: packets and indexes only (no image read, nothing written).

THE ORCSDUN01 LABEL FIX IN THE CACHE (orcsdun01-detector.md 3b / 3f):

    build_frame_cache.py --labels v2 --classes species --kb DIR --fix PARAMS --rule fix2 ...

- the frozen PARAMS (orc_labels_fix.py freeze; their 1d offset replaces --offset-ms) and the
  facing rule: each frame v2's rules keep is FITTED where its pixels are read
  (orc_labels_fix.FixLabeler, exactly as ``orc_label_sheets.py --fix``): its monster boxes are the
  fitted ones; ANY excluded monster label (1c ``occluded_model``, 2b ``next_move``, 2c
  ``ambiguous_view``, ``unfit``, ``crowd``, ``ui``) excludes the FRAME (``fix_<reason>:<mob>``);
  a frame on another map keeps v2's labels (Batt's 3b item 2); a human demo's frame in another UI
  layout is excluded (``ui_layout_mismatch``);
- ``--dry-run`` reads no pixel, so it applies every rule up to the fit (visibility, 1c, 2b, 2c)
  and counts the labels the fit would judge as PENDING: its kept frames are an UPPER BOUND.

ONE BUILD, TWO LABEL MODES (3f: v1's prt_fild08 data with v1's rules + the species split, the
orcsdun01 blocks with v2 + the fix):

    build_frame_cache.py --labels v2 --classes species --fix PARAMS --rule fix2 ...
                         --v1-species-sessions S [S ...]

- the listed sessions (each also in a split) take the ``--labels v1 --classes species`` path;
  every other session the build's own (v2); one class list, one manifest, one set of shards;
- THE TEST BLOCK: a session named ``*-col2`` (orcsdun01's pre-registered TEST block) is refused
  in train / val always, and in test unless ``--allow-test-block`` (3f: never read before
  training ends).

WARP-AND-WATCH sessions (scripts/warp_watch.py, JPEG tar shards; qa_export.is_warp_watch): every
``--every-jpeg``-th frame (5 Hz recordings; default 3, ~1.7 fps, near v1's ~2 fps), their labels in
the recorded UI layout's rectangles. orcsdun01 is a scene map of v0 / v1 too.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import sys
import tarfile
import time
from collections import Counter
from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass, field, replace
from functools import partial
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
import qa_export  # noqa: E402

from poring_dataset import camera as camera_mod  # noqa: E402
from poring_dataset import labels_v2 as lv  # noqa: E402
from poring_dataset.camera import map_key  # noqa: E402
from poring_dataset.labels import CLASSES  # noqa: E402
from poring_dataset.shards import encode_png, read_shard  # noqa: E402

NAS = Path("/mnt/poring-lab-datasets")
OUT = NAS / ".framecache"
SCENE_MAPS = {"prt_fild08", "prt_church", "orcsdun01"}  # v0 / v1; v2's: the KB's maps (kb_maps)
GOLD = "20261004T103815-console-s2-indoor-v2"
DEMO = Path("/dev/shm/poring-lab-demo")  # banked demo sessions (tmpfs; v2 reads them too)
V2_SIZE = (1280, 720)  # labels_v2.py's game region (scripts/labels_v2.py SIZE)
# The client GAT differs from the server's walkability on this host's GRF (labels-v2-plan 7.6:
# alberta 5,091 cells, morocc 6,999); the projection reads the CLIENT GAT's altitude. Unverified
# until the Dell's kRO data decides it: a HOLD (``--allow-hold gat_unverified`` lifts it).
UNVERIFIED_GAT = frozenset({"alberta", "morocc"})
# Fail-closed gates a person lifts (``--allow-hold``): gat_unverified (above); npc_unchecked: an
# NPC sprite box no person has judged (labels-v2-plan 1.2's N3: "READY FOR A PERSON, not judged").
HOLDS = ("gat_unverified", "npc_unchecked")
NPC_REASONS = ("npc_unsized", "npc_unchecked", "npc_rejected")  # what N2 / N3 alone would admit
# --classes species: the committed class list (ids only; orcsdun01-detector.md section 4)
SPECIES_LIST = Path(__file__).resolve().parents[1] / "config" / "detector" / "classes-v2orc.json"
EVERY_JPEG = 3  # warp_watch sessions are 5 Hz: ~1.7 fps kept (v1 kept ~2 fps of H.264)
SPECIES_K = 0.14  # --classes species without --k: the v1 labels' k (M4; the camera check's)


def session_frames(
    session: Path, manifest: dict[str, Any], every: int, every_png: int,
    every_jpeg: int = EVERY_JPEG,
) -> Iterator[tuple[Any, Any]]:  # fmt: skip
    if qa_export.is_warp_watch(manifest):
        yield from qa_export.jpeg_frames(session, manifest, every_jpeg)
        return
    if (manifest.get("format") or "png") == "h264":
        from poring_dataset.h264 import H264Session

        yield from H264Session(session).iter_every(every)
        return
    n = 0  # PNG sessions were recorded at ~1 fps (Batt 2026-10-04): their own, smaller step
    for shard in manifest["shards"]:
        for meta, img in read_shard(session / shard):
            n += 1
            if not (n - 1) % every_png:
                yield meta, img


def yolo_lines(boxes: list[dict[str, Any]], w: int, h: int,
               class_ids: Sequence[int] | None = None) -> str:  # fmt: skip
    """YOLO lines of v0 / v1 box dicts, clipped to the frame; the class id is v0 / v1's (CLASSES)
    unless ``class_ids`` gives one per box (``--labels v1 --classes species``: species_ids)."""
    if class_ids is not None and len(class_ids) != len(boxes):
        raise ValueError(f"{len(class_ids)} class ids for {len(boxes)} boxes")
    out = []
    for i, b in enumerate(boxes):
        x0, y0 = max(0.0, b["x1"]), max(0.0, b["y1"])
        x1, y1 = min(float(w), b["x2"]), min(float(h), b["y2"])
        if x1 <= x0 or y1 <= y0:
            continue
        cid = CLASSES[b["cls"]] if class_ids is None else class_ids[i]
        out.append(f"{cid} {(x0 + x1) / 2 / w:.6f} {(y0 + y1) / 2 / h:.6f} "
                   f"{(x1 - x0) / w:.6f} {(y1 - y0) / h:.6f}")  # fmt: skip
    return "\n".join(out) + ("\n" if out else "")


def jpeg(img_bgr: np.ndarray, quality: int) -> bytes:
    buf = io.BytesIO()
    Image.fromarray(np.ascontiguousarray(img_bgr[:, :, ::-1])).save(buf, "JPEG", quality=quality)
    return buf.getvalue()


class ShardSink:
    """Rotating tar shards, each written as .part, renamed, and re-hashed from the NAS."""

    def __init__(self, directory: Path, max_bytes: int, start: int = 0,
                 done: dict[str, dict[str, Any]] | None = None) -> None:  # fmt: skip
        self.dir, self.max_bytes = directory, max_bytes
        self.n, self.tar, self.path, self.size = start, None, None, 0
        self.done: dict[str, dict[str, Any]] = dict(done or {})
        self.members = 0

    def _open(self) -> None:
        self.path = self.dir / f"shard-{self.n:06d}.tar"
        self.tar = tarfile.open(self.path.with_suffix(".tar.part"), "w")  # noqa: SIM115
        self.size, self.members = 0, 0
        self.n += 1

    def add(self, key: str, files: dict[str, bytes]) -> str:
        if self.tar is None or self.size >= self.max_bytes:
            self.close()
            self._open()
        assert self.tar is not None and self.path is not None
        for ext, data in files.items():
            info = tarfile.TarInfo(f"{key}.{ext}")
            info.size, info.mtime, info.mode = len(data), int(time.time()), 0o644
            self.tar.addfile(info, io.BytesIO(data))
            self.size += len(data) + 1024
            self.members += 1
        return self.path.name

    def close(self) -> None:
        if self.tar is None or self.path is None:
            return
        self.tar.close()
        part = self.path.with_suffix(".tar.part")
        part.replace(self.path)
        h = hashlib.sha256()
        with self.path.open("rb") as fh:  # read back from the NAS
            for chunk in iter(lambda: fh.read(1 << 20), b""):
                h.update(chunk)
        self.done[self.path.name] = {"sha256": h.hexdigest(), "bytes": self.path.stat().st_size,
                                     "members": self.members}  # fmt: skip
        self.tar, self.path = None, None


RESUME_KEYS = ("labels", "k", "every", "every_png", "max_per_session", "shard_mb", "image",
               "quality", "split", "every_demo", "every_jpeg", "v2")  # fmt: skip


def write_json(directory: Path, name: str, doc: Any) -> None:
    """Atomic (.part, rename) and read back."""
    tmp = directory / f".{name}.part"
    tmp.write_text(json.dumps(doc, indent=1) + "\n")
    tmp.replace(directory / name)
    json.loads((directory / name).read_text())


def resume_state(directory: Path, args: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """(sessions done, shards done) of an interrupted build; refuses another build's arguments and
    a recorded shard whose size differs on the NAS; removes the interrupted session's leftovers."""
    prog_path = directory / "progress.json"
    if not prog_path.exists():
        raise SystemExit(f"{directory}: no progress.json to resume from")
    prog = json.loads(prog_path.read_text())
    diff = [k for k in RESUME_KEYS if prog["args"].get(k) != args.get(k)]
    if diff:
        raise SystemExit(f"--resume refused: arguments differ from the interrupted build: {diff}")
    for name, info in prog["shards"].items():
        size = (directory / name).stat().st_size if (directory / name).exists() else -1
        if size != info["bytes"]:
            raise SystemExit(f"--resume refused: {name} is {size} B on the NAS, {info['bytes']} "
                             "recorded")  # fmt: skip
    for leftover in sorted(directory.glob("shard-*.tar*")):
        if leftover.name not in prog["shards"]:
            leftover.unlink()  # the interrupted session's partial shards
    return prog["sessions"], prog["shards"]


# --- labels v2 ------------------------------------------------------------------------------------


def sha256_of(path: Path | None) -> str | None:
    return None if path is None else hashlib.sha256(path.read_bytes()).hexdigest()


def kb_maps(kb: Path) -> frozenset[str]:
    """The maps the KB covers: route.json's warp lists (kb_route.py: an EMPTY list = no portals; a
    map with no entry is unknown, so its frames are excluded)."""
    route = json.loads((kb / "route.json").read_text())
    return frozenset(map_key(m) for m in (route.get("warps") or {}))


@dataclass(frozen=True)
class SpeciesClasses:
    """``--classes species``: player / npc / warp at fixed ids, then one class per monster species
    (mob id) in the committed list's order. Ids only in the list; names come from the KB."""

    fixed: dict[str, int]
    monsters: tuple[int, ...]
    first: int
    path: Path
    sha256: str

    @classmethod
    def load(cls, path: Path) -> SpeciesClasses:
        doc = json.loads(path.read_text())
        fixed = {str(k): int(v) for k, v in doc["fixed"].items()}
        monsters = tuple(int(m) for m in doc["monsters"])
        first = int(doc["monster_first_id"])
        ids = [*fixed.values(), *range(first, first + len(monsters))]
        if (
            set(fixed) != {"player", "npc", "warp"}
            or len(set(ids)) != len(ids)
            or (sorted(ids) != list(range(len(ids))))
        ):
            raise SystemExit(f"{path}: the class ids must be player / npc / warp + the monster "
                             f"species, 0..n-1 without a gap or a repeat")  # fmt: skip
        if len(set(monsters)) != len(monsters):
            raise SystemExit(f"{path}: a monster species is listed twice")
        return cls(fixed, monsters, first, path, sha256_of(path) or "")

    @property
    def index(self) -> dict[int, int]:
        return {m: self.first + i for i, m in enumerate(self.monsters)}

    def class_of(self, lab: lv.V2Label) -> int:
        if lab.cls == "monster":
            if lab.job is None or lab.job not in self.index:
                raise KeyError(f"no class for monster species {lab.job}")  # reasons() excluded it
            return self.index[lab.job]
        return self.fixed[lab.cls]

    def reasons(self, labels: Sequence[lv.V2Label]) -> list[str]:
        """Why a frame cannot be labelled completely in this scheme (fail closed)."""
        out = []
        for lab in labels:
            if lab.cls != "monster":
                continue
            if lab.job is None:
                out.append("monster_unknown_species")
            elif lab.job not in self.index:
                out.append(f"species_unlisted:{lab.job}")
            elif lab.kind == "v0":
                out.append(f"monster_unsized:{lab.job}")  # no sprite: v0's 44 x 40 box
        return list(dict.fromkeys(out))

    def names(self, kb: Path) -> dict[int, str]:
        """class id -> name; a monster's name is the KB's aegis name (classes.json, any map;
        monster_sprite_names.json as a fallback), lower case. A listed species the KB cannot name
        stops the build (the names are what the trainer reports)."""
        aegis: dict[int, str] = {}
        sprite_names = kb / "monster_sprite_names.json"
        if sprite_names.exists():
            rows = json.loads(sprite_names.read_text()).get("mobs") or {}
            aegis.update({int(j): str(r["aegis"]) for j, r in rows.items() if r.get("aegis")})
        if (kb / "classes.json").exists():
            for rows in json.loads((kb / "classes.json").read_text()).values():
                aegis.update({int(j): str(r["aegis"]) for j, r in rows.items() if r.get("aegis")})
        missing = [m for m in self.monsters if m not in aegis]
        if missing:
            raise SystemExit(f"the KB ({kb}) has no name for listed species {missing}")
        out = {v: k for k, v in self.fixed.items()}
        out.update({self.index[m]: aegis[m].lower() for m in self.monsters})
        return dict(sorted(out.items()))

    def provenance(self) -> dict[str, Any]:
        return {"mode": "species", "list": str(self.path), "sha256": self.sha256,
                "fixed": self.fixed, "monster_first_id": self.first,
                "monsters": list(self.monsters)}  # fmt: skip


@dataclass(frozen=True)
class V2Inputs:
    """Everything v2's labels depend on beyond the session (validated once, recorded in the
    progress file and the manifest: a resume with any other input is refused)."""

    ns: argparse.Namespace  # scripts/labels_v2.py Session's options
    maps: frozenset[str]
    gat_dir: Path
    checked: dict[str, str]  # N3 verdicts: "<job>" or "<map>:<job>" -> "fit" | anything else
    lifted: frozenset[str]
    k: float | None
    provenance: dict[str, Any]
    classes: SpeciesClasses | None = None

    @classmethod
    def from_args(cls, a: argparse.Namespace) -> V2Inputs:
        species = getattr(a, "classes", "v2") == "species"
        if a.kb is None or (a.warp_visibility is None and not species):
            raise SystemExit("--labels v2 needs --kb DIR and --warp-visibility JSON (a person's "
                             "table; labels-v2-plan 1.3)")  # fmt: skip
        classes = SpeciesClasses.load(getattr(a, "class_list", None) or SPECIES_LIST) if species \
            else None  # fmt: skip
        if classes is not None:
            classes.names(a.kb)  # fail closed before any frame: every listed species has a name
        if (a.npc_sprites is None) != (a.npc_sprite_names is None):
            raise SystemExit("--npc-sprites and --npc-sprite-names go together")
        for p in (a.kb / "route.json", a.warp_visibility, a.npc_sprite_names, a.npc_extents,
                  a.npc_checked):  # fmt: skip
            if p is not None and not p.exists():
                raise SystemExit(f"{p}: not found")
        checked = ({str(k): str(v) for k, v in json.loads(a.npc_checked.read_text()).items()}
                   if a.npc_checked else {})  # fmt: skip
        ns = argparse.Namespace(
            kb=a.kb, offset_ms=a.offset_ms, npc_extents=a.npc_extents, npc_sprites=a.npc_sprites,
            npc_sprite_names=a.npc_sprite_names, cutin_rect=a.cutin_rect,
            warp_visibility=a.warp_visibility,
        )  # fmt: skip
        maps = kb_maps(a.kb)
        gat_dir = camera_mod.GAT_DIR  # the directory load_scene / projector_for read
        shape = lv.PORTAL_PROVISIONAL
        provenance = {
            "kb": str(a.kb), "route_sha256": sha256_of(a.kb / "route.json"), "kb_maps": len(maps),
            "monster_sprite_names_sha256": sha256_of(a.kb / "monster_sprite_names.json")
            if (a.kb / "monster_sprite_names.json").exists() else None,
            "classes_sha256": sha256_of(a.kb / "classes.json")
            if (a.kb / "classes.json").exists() else None,
            "monster_sprites": str(qa_export.SPRITE_DIR),
            "warp_visibility": None if a.warp_visibility is None else str(a.warp_visibility),
            "warp_visibility_sha256": sha256_of(a.warp_visibility),
            "warp_rule": "table" if a.warp_visibility is not None else
            "no table: a drawn portal on screen excludes the frame",
            "npc_sprites": None if a.npc_sprites is None else str(a.npc_sprites),
            "npc_sprite_names_sha256": sha256_of(a.npc_sprite_names),
            "npc_extents_sha256": sha256_of(a.npc_extents),
            "npc_checked_sha256": sha256_of(a.npc_checked),
            "cutin_rect": a.cutin_rect, "offset_ms": a.offset_ms, "gat_dir": str(gat_dir),
            "holds_lifted": sorted(a.allow_hold), "unverified_gat": sorted(UNVERIFIED_GAT),
            "portal_shape": {"radius": shape.radius, "height": shape.height,
                             "measured": shape.measured, "source": shape.source},
            "classes": lv.V2_CLASSES if classes is None else classes.provenance(),
        }  # fmt: skip
        return cls(ns, maps, gat_dir, checked, frozenset(a.allow_hold), a.k, provenance, classes)

    def class_names(self) -> dict[int, str]:
        """The cache manifest's names: v2's four, or the species scheme's (KB names)."""
        if self.classes is None:
            return {v: k for k, v in lv.V2_CLASSES.items()}
        return self.classes.names(self.ns.kb)


def make_v2_session(path: Path, v2: V2Inputs) -> Any:
    """scripts/labels_v2.py's Session: the labels of ``labels_v2.py coverage``, frame by frame."""
    import labels_v2 as tool

    s = tool.Session(path, v2.ns)
    if v2.k is not None:
        s.labeler.k = v2.k  # v1's --k: the sprite scale (monsters' and NPCs' predict_sprite)
    return s


TEST_BLOCK_SUFFIX = "-col2"  # orcsdun01's pre-registered TEST block (orc_labels_fix's rule)


def is_test_block(sid: str) -> bool:
    return sid.rstrip("/").endswith(TEST_BLOCK_SUFFIX)


@dataclass(frozen=True)
class FixInputs:
    """``--fix PARAMS --rule R``: the orcsdun01 label fix's frozen parameters and facing rule
    (orc_labels_fix.py; recorded in the progress file and the manifest)."""

    params: dict[str, Any]
    rule: str
    provenance: dict[str, Any]

    @classmethod
    def from_args(cls, a: argparse.Namespace) -> FixInputs | None:
        if getattr(a, "fix", None) is None:
            return None
        import orc_labels_fix as olf

        params = olf.load_params(a.fix)
        want = getattr(a, "fix_sha256", None)
        if want is not None and sha256_of(a.fix) != want:
            raise SystemExit(f"{a.fix}: sha256 {sha256_of(a.fix)}, not the frozen {want}")
        if a.rule not in olf.RULES:
            raise SystemExit(f"--rule {a.rule}: one of {olf.RULES}")
        prov = {"labels": olf.labels_name(a.rule), "rule": a.rule, "params": str(a.fix),
                "params_sha256": sha256_of(a.fix), "measured_on": params.get("measured_on"),
                "offset_ms": float(params["offset_ms"]),
                "rsw_sha256": (params.get("occluders") or {}).get("rsw_sha256")}  # fmt: skip
        return cls(params, a.rule, prov)

    def labeler(self, lab: Any) -> Any:
        import orc_labels_fix as olf

        return olf.FixLabeler(lab, self.params, rule=self.rule)


def apply_fix(fr: lv.Frame, got: Any) -> tuple[lv.Frame | None, list[str]]:
    """PURE: a frame v2's rules keep, under the fix's verdict on it (orc_labels_fix.FixFrame), as
    ``orc_label_sheets.py --fix`` treats it: no world -> excluded; another map -> v2's labels
    unchanged; any excluded monster label -> the FRAME excluded (``fix_<why>:<mob>``); else v2's
    monster boxes are replaced by the fitted ones (kind ``fit``) -- and, without pixels (a dry
    run), by the labels the fit would judge (kind ``fit_pending``, their predicted boxes)."""
    if got is None:
        return None, ["fix_no_world"]
    if not got.applies:
        return fr, []
    if got.excluded:
        return None, [f"fix_{why}:{mob}" for _gid, mob, why in got.excluded]
    monsters = [lv.V2Label("monster", *k.box, gid=k.gid, job=k.mob, kind="fit") for k in got.kept]
    monsters += [lv.V2Label("monster", *box, gid=gid, job=mob, kind="fit_pending")
                 for gid, mob, box in getattr(got, "pending", ())]  # fmt: skip
    labels = tuple(b for b in fr.labels if b.cls != "monster") + tuple(monsters)
    return replace(fr, labels=labels), []


def fixed_frame(fixer: Any, layout: Any, fr: lv.Frame, t: int,
                img: np.ndarray | None) -> tuple[lv.Frame | None, list[str], Any]:  # fmt: skip
    """The fix on ONE frame v2's rules keep: (the frame to write or None, the exclusion reasons,
    the fixer's FixFrame). ``img=None`` (a dry run): every rule up to the fit (apply_fix)."""
    if img is not None and layout is not None and not layout(img):
        return None, ["ui_layout_mismatch"], None  # a human demo in another UI layout (3f)
    got = fixer.frame(t, img)
    fr2, reasons = apply_fix(fr, got)
    return fr2, reasons, got


def map_reasons(map_name: str, v2: V2Inputs) -> list[str]:
    """The map gates (fail closed): not in the KB; its GAT not extracted; a held GAT."""
    mk = map_key(map_name)
    if mk not in v2.maps:
        return [f"map_not_in_kb:{mk}"]
    out = []
    if not (v2.gat_dir / f"{mk}.gat").exists():
        out.append(f"gat_missing:{mk}")
    if mk in UNVERIFIED_GAT and "gat_unverified" not in v2.lifted:
        out.append(f"gat_unverified:{mk}")
    return out


def npc_reasons(fr: lv.Frame, checked: dict[str, str], lifted: frozenset[str]) -> list[str]:
    """N3's gate on every LABELLED NPC with a sprite / measured box (an unsized one is already
    excluded by labels_v2): a person's "fit" admits it; no verdict is ``npc_unchecked`` (the hold);
    any other verdict is ``npc_rejected`` (no hold lifts it)."""
    mk = map_key(fr.map or "")
    out = []
    for lab in fr.labels:
        if lab.cls != "npc" or lab.kind == "unsized":
            continue
        verdict = checked.get(f"{mk}:{lab.job}", checked.get(str(lab.job)))
        if verdict == "fit":
            continue
        if verdict is None:
            if "npc_unchecked" not in lifted:
                out.append(f"npc_unchecked:{lab.job}")
        else:
            out.append(f"npc_rejected:{lab.job}")
    return list(dict.fromkeys(out))


def v2_class(b: lv.V2Label) -> int:
    return lv.V2_CLASSES[b.cls]


def v2_yolo(
    labels: Sequence[lv.V2Label], size: tuple[int, int],
    class_of: Callable[[lv.V2Label], int] = v2_class,
) -> tuple[str, list[lv.V2Label]]:  # fmt: skip
    """YOLO lines with V2_CLASSES ids (or ``class_of``'s: --classes species), clipped to the frame
    (as yolo_lines); the labels written."""
    w, h = size
    lines, written = [], []
    for b in labels:
        x0, y0 = max(0.0, b.x0), max(0.0, b.y0)
        x1, y1 = min(float(w), b.x1), min(float(h), b.y1)
        if x1 <= x0 or y1 <= y0:
            continue
        lines.append(f"{class_of(b)} {(x0 + x1) / 2 / w:.6f} {(y0 + y1) / 2 / h:.6f} "
                     f"{(x1 - x0) / w:.6f} {(y1 - y0) / h:.6f}")  # fmt: skip
        written.append(b)
    return "\n".join(lines) + ("\n" if lines else ""), written


def _keyed(c: Counter[Any]) -> dict[str, int]:
    return {str(k): v for k, v in sorted(c.items(), key=lambda kv: (-kv[1], str(kv[0])))}


@dataclass
class V2Tally:
    """Counts only (ids, never names): frames seen / kept / skipped, exclusions by reason, the
    written boxes per class, species (monster id) and NPC sprite (job)."""

    seen: int = 0
    kept: int = 0
    gm_window: int = 0
    no_world: int = 0
    excluded_frames: int = 0
    only_npc: int = 0  # excluded ONLY for NPC sprites (unsized / unchecked / rejected): N2-N3
    excluded: Counter[str] = field(default_factory=Counter)  # reason -> frames
    excluded_detail: Counter[str] = field(default_factory=Counter)  # reason:arg -> frames
    maps_seen: Counter[str] = field(default_factory=Counter)
    maps_kept: Counter[str] = field(default_factory=Counter)
    class_frames: Counter[str] = field(default_factory=Counter)
    class_boxes: Counter[str] = field(default_factory=Counter)
    species_frames: Counter[int] = field(default_factory=Counter)
    species_boxes: Counter[int] = field(default_factory=Counter)
    npc_frames: Counter[int] = field(default_factory=Counter)
    npc_boxes: Counter[int] = field(default_factory=Counter)
    kinds: Counter[str] = field(default_factory=Counter)  # "<class>:<box kind>"
    cutin_kept: int = 0  # kept frames with the cut-in shown (its units in shadow)

    INTS = ("seen", "kept", "gm_window", "no_world", "excluded_frames", "only_npc", "cutin_kept")

    def exclude(self, reasons: Sequence[str]) -> None:
        self.excluded_frames += 1
        heads = {r.split(":", 1)[0] for r in reasons}
        for r in heads:
            self.excluded[r] += 1
        for r in dict.fromkeys(reasons):
            self.excluded_detail[r] += 1
        if heads <= set(NPC_REASONS):
            self.only_npc += 1

    def keep(self, fr: lv.Frame, written: Sequence[lv.V2Label]) -> None:
        self.kept += 1
        self.maps_kept[map_key(fr.map or "?")] += 1
        self.cutin_kept += int(fr.cutin.rect is not None)
        for cls in {b.cls for b in written}:
            self.class_frames[cls] += 1
        for b in written:
            self.class_boxes[b.cls] += 1
            self.kinds[f"{b.cls}:{b.kind}"] += 1
            if b.job is not None and b.cls == "monster":
                self.species_boxes[b.job] += 1
            elif b.job is not None and b.cls == "npc":
                self.npc_boxes[b.job] += 1
        for j in {b.job for b in written if b.cls == "monster" and b.job is not None}:
            self.species_frames[j] += 1
        for j in {b.job for b in written if b.cls == "npc" and b.job is not None}:
            self.npc_frames[j] += 1

    def merge(self, other: V2Tally) -> None:
        for name in self.INTS:
            setattr(self, name, getattr(self, name) + getattr(other, name))
        for name, value in vars(other).items():
            if isinstance(value, Counter):
                getattr(self, name).update(value)

    def as_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {name: getattr(self, name) for name in self.INTS}
        for name, value in vars(self).items():
            if isinstance(value, Counter):
                out[name] = _keyed(value)
        return out


Loader = Callable[[], np.ndarray] | None


def read_bgr(path: Path) -> np.ndarray:
    return np.ascontiguousarray(np.asarray(Image.open(path).convert("RGB"))[:, :, ::-1])


def demo_frames(session: Path, every: int) -> Iterator[tuple[int, int, dict[str, Any], Loader]]:
    """A demo session's banked frames (scripts/labels_v2.py banked_frames: frames/<n>-<t>.png and
    the snapshots demo.jsonl references), every ``every``-th; keyed by position in that list."""
    import labels_v2 as tool

    for i, (t, img) in enumerate(tool.banked_frames(session)):
        if img is None or i % every:
            continue
        yield i, t, {"index": i, "ref": str(img.relative_to(session))}, partial(read_bgr, img)


def recorded_times(
    session: Path, manifest: dict[str, Any], every: int, every_png: int,
    every_jpeg: int = EVERY_JPEG,
) -> Iterator[tuple[int, int]]:  # fmt: skip
    """(frame_id, t_ns) of exactly the frames ``session_frames`` decodes, WITHOUT decoding: the
    H.264 index (usable frames, every n-th, as iter_every), the PNG shards' json members, or a
    warp_watch session's JPEG shard index."""
    if qa_export.is_warp_watch(manifest):
        for ref in qa_export.jpeg_index(session, manifest)[::every_jpeg]:
            yield ref.frame_id, ref.t_mono_ns
        return
    if (manifest.get("format") or "png") == "h264":
        from poring_dataset.h264 import H264Session

        s = H264Session(session, check_versions=False)
        t_of = {u.frame_id: u.t_ns for u in s.units}
        for fid in s.usable()[::every]:
            yield fid, t_of[fid]
        return
    n = 0
    for shard in manifest["shards"]:
        with tarfile.open(session / shard) as tar:
            for m in tar:
                if not m.name.endswith(".json"):
                    continue
                n += 1
                if not (n - 1) % every_png:
                    fh = tar.extractfile(m)
                    assert fh is not None
                    meta = json.loads(fh.read())
                    yield int(meta["frame_id"]), int(meta["t_mono_ns"])


def v2_frames(
    session: Path, manifest: dict[str, Any], a: argparse.Namespace, decode: bool
) -> Iterator[tuple[int, int, dict[str, Any], Loader]]:
    """(key id, t_ns, json extras, image loader) per candidate frame; no loader in a dry run."""
    if manifest.get("kind") == "demo":
        for i, t, extra, load in demo_frames(session, a.every_demo):
            yield i, t, extra, (load if decode else None)
    elif decode:
        for meta, img in session_frames(session, manifest, a.every, a.every_png, a.every_jpeg):
            fid = int(meta["frame_id"])
            yield fid, int(meta["t_mono_ns"]), {"frame_id": fid}, partial(np.asarray, img)
    else:
        for fid, t in recorded_times(session, manifest, a.every, a.every_png, a.every_jpeg):
            yield fid, t, {"frame_id": fid}, None


def extra_roots(a: argparse.Namespace) -> list[Path]:
    """The session roots searched after --datasets: --also-datasets, then each --collection MAP's
    warp_watch directory (<datasets>/detector-collection/<MAP>: a relative name, so the guarded
    cache step -- whose arguments cannot start with "/" -- can name it)."""
    roots = list(getattr(a, "also_datasets", None) or ())
    for name in getattr(a, "collection", None) or ():
        roots.append(a.datasets / "detector-collection" / name)
    return roots


def resolve_session(sid: str, a: argparse.Namespace) -> Path:
    """v2: a banked demo session under --demo-root (RAM) first, else the session under --datasets
    (a recorded session, or a demo session dataset_ship already copied to the NAS), else under an
    --also-datasets root (warp_watch's detector-collection/<map>: a combined cache)."""
    roots = (a.demo_root, a.datasets, *extra_roots(a))
    for root in roots:
        if (root / sid / "manifest.json").exists():
            return root / sid  # type: ignore[no-any-return]
    raise SystemExit(f"{sid}: no manifest under {', '.join(str(r) for r in roots)}")


def dataset_session(sid: str, a: argparse.Namespace) -> Path:
    """v0 / v1: the session under --datasets, else under an --also-datasets root."""
    for root in (a.datasets, *extra_roots(a)):
        if (root / sid / "manifest.json").exists():
            return root / sid  # type: ignore[no-any-return]
    return a.datasets / sid  # type: ignore[no-any-return]


def decide(sess: Any, t: int, v2: V2Inputs) -> tuple[str, lv.Frame | None, list[str], str | None]:
    """One candidate frame's fate: (outcome, the v2 frame, the exclusion reasons, its map key).
    outcome: "ok" (labelled completely) | "excluded" (``reasons``: the map gates, labels_v2's,
    N3's, and --classes species') | "gm_window" | "no_world". The cache, its dry run and the orc
    label sheets (scripts/orc_label_sheets.py) share it."""
    world = sess.world(t)
    mk = map_key(world.map) if world.map else None
    if world.map:
        gate = map_reasons(world.map, v2)
        if gate:
            return "excluded", None, gate, mk
    status, fr, _scene = sess.frame(t)
    if fr is None:
        return status, None, [], mk  # gm_window | no_world
    reasons = [*fr.excluded, *npc_reasons(fr, v2.checked, v2.lifted)]
    if v2.classes is not None:
        reasons += v2.classes.reasons(fr.labels)
    return ("excluded" if reasons else "ok"), fr, reasons, mk


def v2_session(
    sid: str, part: str, path: Path, a: argparse.Namespace, v2: V2Inputs, sink: ShardSink | None,
    fix: FixInputs | None = None,
) -> tuple[dict[str, Any], V2Tally]:  # fmt: skip
    """One session's v2 frames: every candidate labelled by labels_v2's Session, gated, and (with a
    sink) written; ``sink=None`` is the dry run (nothing read but packets and indexes). With
    ``fix``: each kept frame fitted on its pixels (apply_fix; in a dry run, up to the fit)."""
    manifest = json.loads((path / "manifest.json").read_text())
    sess = make_v2_session(path, v2)
    fixer = None if fix is None else fix.labeler(sess.labeler)
    layout = None if fix is None else qa_export.layout_check(
        manifest, getattr(a, "layout_templates", None))  # fmt: skip
    fixed: Counter[str] = Counter()
    size = tuple(getattr(sess.labeler, "size", V2_SIZE))
    if size != V2_SIZE:
        raise SystemExit(f"{sid}: game region {size}, labels_v2 labels {V2_SIZE}")
    tally = V2Tally()
    fmt = (
        "demo"
        if manifest.get("kind") == "demo"
        else "jpeg_shards"
        if qa_export.is_warp_watch(manifest)
        else manifest.get("format") or "png"
    )
    row: dict[str, Any] = {"split": part, "path": str(path), "format": fmt, "shards": []}
    class_of = v2_class if v2.classes is None else v2.classes.class_of
    for kid, t, extra, load in v2_frames(path, manifest, a, decode=sink is not None):
        tally.seen += 1
        outcome, fr, reasons, mk = decide(sess, t, v2)
        if mk is not None:
            tally.maps_seen[mk] += 1
        if outcome in ("gm_window", "no_world"):
            setattr(tally, outcome, getattr(tally, outcome) + 1)
            continue
        if outcome == "excluded" or fr is None:
            tally.exclude(reasons)
            continue
        img = None
        if sink is not None:
            assert load is not None
            img = load()
            if img.shape[:2] != (V2_SIZE[1], V2_SIZE[0]):
                raise SystemExit(f"{sid}: frame {kid} is {img.shape[1]}x{img.shape[0]}, the "
                                 f"labels are {V2_SIZE[0]}x{V2_SIZE[1]}")  # fmt: skip
        if fixer is not None:
            fr2, reasons, got = fixed_frame(fixer, layout, fr, t, img)
            if got is not None and got.applies:
                fixed["frames_fitted" if img is not None else "frames_up_to_the_fit"] += 1
                fixed["monsters_not_visible"] += got.hidden
                fixed.update(f"excluded_label:{why}" for _g, _m, why in got.excluded)
                fixed.update(f"kept_label:{k.mob}" for k in got.kept)
                fixed.update(f"pending_label:{mob}" for _g, mob, _b in got.pending)
            if fr2 is None:
                tally.exclude(reasons)
                continue
            if got is not None and got.pending:
                fixed["fit_pending_frames"] += 1  # kept here, decided by the pixels in a build
            fr = fr2
        text, written = v2_yolo(fr.labels, V2_SIZE, class_of)
        tally.keep(fr, written)
        if sink is not None:
            assert img is not None
            info = {"session": sid, "t_mono_ns": t, "map": map_key(fr.map or ""), "labels": "v2",
                    **({} if fix is None else {"fix": fix.provenance["labels"]}),
                    **extra,
                    "boxes": [[class_of(b), b.job, b.kind] for b in written],
                    "shadow": len(fr.shadow),
                    "cutin": None if fr.cutin.rect is None else list(fr.cutin.rect)}  # fmt: skip
            image = ({"png": encode_png(np.ascontiguousarray(img[:, :, :3]))}
                     if a.image == "png" else {"jpg": jpeg(img, a.quality)})  # fmt: skip
            shard = sink.add(f"{sid}.{kid:09d}", {**image, "txt": text.encode(),
                                                  "json": json.dumps(info).encode()})  # fmt: skip
            if shard not in row["shards"]:
                row["shards"].append(shard)
        if a.max_per_session and tally.kept >= a.max_per_session:
            break
    sheets = getattr(sess.labeler, "sheets", None)
    missing = getattr(sheets, "missing", None) or {}
    row.update(tally.as_dict())
    row["boxes"] = sum(tally.class_boxes.values())
    row["sprite_lookup_missing"] = {str(k): v for k, v in sorted(missing.items())}
    if fix is not None:
        row["labels"] = f"v2+{fix.provenance['labels']}"
        row["fix"] = {k: v for k, v in sorted(fixed.items())}
    return row, tally


def dry_run(
    a: argparse.Namespace,
    split: dict[str, list[str]],
    v2: V2Inputs,
    fix: FixInputs | None = None,
    v1_species: frozenset[str] = frozenset(),
) -> int:
    """Counts only: no directory, no shard, no manifest, no image read. With ``fix`` the kept
    orcsdun01 frames are an UPPER BOUND (the fit needs pixels: ``fix.fit_pending_frames``); the
    ``--v1-species-sessions`` are counted on their own path and in ``combined`` (per class id)."""
    parts = {part: V2Tally() for part in split}
    total = V2Tally()
    v1_parts: dict[str, Counter[str]] = {part: Counter() for part in split}
    fix_parts: dict[str, Counter[str]] = {part: Counter() for part in split}
    for part, ids in split.items():
        for sid in ids:
            if sid in v1_species:
                row = v01_session(sid, part, a, None, mode=("v1", True))
                row.pop("shards")
                print(json.dumps({"session": sid, **row}), flush=True)
                for k in ("kept", "gm_window", "off_scene", "boxes"):
                    v1_parts[part][k] += int(row[k])
                v1_parts[part].update({f"boxes:{k}": v for k, v in
                                       row["boxes_by_class_id"].items()})  # fmt: skip
                v1_parts[part].update({f"excluded:{k}": v for k, v in
                                       row["excluded_species"].items()})  # fmt: skip
                continue
            row, tally = v2_session(sid, part, resolve_session(sid, a), a, v2, None, fix)
            row.pop("shards")
            print(json.dumps({"session": sid, **row}), flush=True)
            parts[part].merge(tally)
            total.merge(tally)
            fix_parts[part].update(row.get("fix") or {})
    out: dict[str, Any] = {"dry_run": True, "labels": "v2", "inputs": v2.provenance,
                           "splits": {p: t.as_dict() for p, t in parts.items()},
                           "total": total.as_dict()}  # fmt: skip
    if fix is not None:
        out["fix"] = {
            **fix.provenance,
            "note": "no pixels in a dry run: every rule up to the fit "
            "is applied; a frame with labels the fit would judge counts as kept "
            "(fit_pending_frames): kept is an UPPER BOUND for these sessions",
            "splits": {p: dict(sorted(c.items())) for p, c in fix_parts.items()},
        }
    if v1_species:
        out["v1_species"] = {p: dict(sorted(c.items())) for p, c in v1_parts.items()}
        out["combined"] = combined_counts(parts, v1_parts, v2)
    print(json.dumps(out, indent=1))
    return 0


def combined_counts(parts: dict[str, V2Tally], v1_parts: dict[str, Counter[str]],
                    v2: V2Inputs) -> dict[str, Any]:  # fmt: skip
    """PURE: per split, the frames kept and the boxes per CLASS ID over both label modes (the v2
    sessions' classes by name / species, the v1 ones already by id)."""
    assert v2.classes is not None
    index, fixed = v2.classes.index, v2.classes.fixed
    out: dict[str, Any] = {}
    for part, t in parts.items():
        ids: Counter[int] = Counter()
        for cls, n in t.class_boxes.items():
            if cls != "monster":
                ids[fixed[cls]] += n
        for job, n in t.species_boxes.items():
            ids[index[job]] += n
        v1 = v1_parts.get(part, Counter())
        for k, n in v1.items():
            if k.startswith("boxes:"):
                ids[int(k.split(":", 1)[1])] += n
        out[part] = {"frames_kept": t.kept + int(v1.get("kept", 0)),
                     "frames_kept_v2": t.kept, "frames_kept_v1": int(v1.get("kept", 0)),
                     "boxes_by_class_id": {str(k): v for k, v in sorted(ids.items())}}  # fmt: skip
    return out


def species_ids(boxes: list[dict[str, Any]], jobs: dict[int, int],
                classes: SpeciesClasses) -> tuple[list[int], list[str]]:  # fmt: skip
    """``--labels v1 --classes species`` (Batt, orcsdun01-detector.md 3b item 2: v1's sessions keep
    v1's rules with the species split ONLY): each v1 box's class id in the species scheme (player /
    npc at their fixed ids, a monster at its species' id, its job from the frame's world), and the
    reasons the frame cannot be labelled completely in that scheme (SpeciesClasses.reasons: a
    monster of an unlisted or unknown species, or one without its sprite -- fail closed). No
    labels-v2 exclusion is applied."""
    labs = [lv.V2Label(str(b["cls"]), float(b["x1"]), float(b["y1"]), float(b["x2"]),
                       float(b["y2"]), gid=int(b["gid"]), job=jobs.get(int(b["gid"])),
                       kind=str(b.get("kind") or "v1")) for b in boxes]  # fmt: skip
    reasons = classes.reasons(labs)
    return ([] if reasons else [classes.class_of(lab) for lab in labs]), reasons


def v01_frames(
    path: Path, manifest: dict[str, Any], a: argparse.Namespace, decode: bool
) -> Iterator[tuple[int, int, Any]]:
    """(frame_id, t_ns, BGR or None) of exactly the frames v0 / v1 label; no image in a dry run."""
    if decode:
        for meta, img in session_frames(path, manifest, a.every, a.every_png, a.every_jpeg):
            yield int(meta["frame_id"]), int(meta["t_mono_ns"]), img
    else:
        for fid, t in recorded_times(path, manifest, a.every, a.every_png, a.every_jpeg):
            yield fid, t, None


def dry_run_v1(a: argparse.Namespace, split: dict[str, list[str]]) -> int:
    """``--labels v1 --classes species --dry-run``: counts only (packets and indexes; no image, no
    directory, no shard)."""
    names = SpeciesClasses.load(a.class_list).names(a.kb)
    totals: dict[str, Counter[str]] = {part: Counter() for part in split}
    for part, ids in split.items():
        for sid in ids:
            row = v01_session(sid, part, a, None)
            row.pop("shards")
            print(json.dumps({"session": sid, **row}), flush=True)
            for k in ("kept", "gm_window", "off_scene", "boxes"):
                totals[part][k] += int(row[k])
            totals[part].update({f"boxes:{k}": v for k, v in row["boxes_by_class_id"].items()})
            totals[part].update({f"excluded:{k}": v for k, v in row["excluded_species"].items()})
    print(json.dumps({"dry_run": True, "labels": "v1", "classes": "species", "names": names,
                      "splits": {p: dict(sorted(c.items())) for p, c in totals.items()}},
                     indent=1))  # fmt: skip
    return 0


def v01_session(sid: str, part: str, a: argparse.Namespace, sink: ShardSink | None,
                mode: tuple[str, bool] | None = None) -> dict[str, Any]:  # fmt: skip
    """One session, labels v0 / v1 (unchanged): qa_export.Labeler, v0 / v1's scene maps. With
    ``--classes species`` (labels v1 only) the same frames and boxes, the classes split per species
    (``species_ids``). ``sink=None``: a dry run (packets and indexes only, no image read). ``mode``
    = (labels, species) overrides the build's own (``--v1-species-sessions``: ("v1", True))."""
    labels, species = mode if mode is not None else (a.labels, a.classes == "species")
    path = dataset_session(sid, a)
    manifest = json.loads((path / "manifest.json").read_text())
    if getattr(a, "kb", None) is not None:  # the sprite names / species of --kb (as v2 reads them)
        qa_export.KB_CLASSES = a.kb / "classes.json"
        qa_export.KB_SPRITE_NAMES = a.kb / "monster_sprite_names.json"
    labeler = qa_export.Labeler(path, labels=labels,
                                **({"k": a.k} if a.k is not None else {}))  # fmt: skip
    classes = SpeciesClasses.load(a.class_list) if species else None
    w, h = labeler.size
    row: dict[str, Any] = {"split": part, "format": manifest.get("format") or "png", "kept": 0,
                           "gm_window": 0, "off_scene": 0, "boxes": 0, "shards": []}  # fmt: skip
    excluded: Counter[str] = Counter()
    class_boxes: Counter[int] = Counter()
    for fid, t, img in v01_frames(path, manifest, a, decode=sink is not None):
        world = labeler.timeline.frame_world(t - int(labeler.offset_ms * 1e6))
        world_map = (world.map or "").removesuffix(".gat")  # packets say prt_fild08.gat
        if world_map not in SCENE_MAPS:
            row["off_scene"] += 1
            continue
        boxes = labeler.boxes(t)
        if boxes is None:
            row["gm_window"] += 1
            continue
        ids: list[int] | None = None
        if classes is not None:
            ids, reasons = species_ids(boxes, {e.gid: e.job for e in world.entities}, classes)
            if reasons:
                excluded.update(dict.fromkeys(reasons, 1))
                continue
            class_boxes.update(ids)
        row["kept"] += 1
        row["boxes"] += len(boxes)
        if sink is not None:
            key = f"{sid}.{fid:09d}"
            info: dict[str, Any] = {"session": sid, "frame_id": fid, "t_mono_ns": t,
                                    "map": world_map, "labels": labels}  # fmt: skip
            if ids is not None:
                info["classes"] = "species"
            image = ({"png": encode_png(np.ascontiguousarray(img[:, :, :3]))}
                     if a.image == "png" else {"jpg": jpeg(img, a.quality)})  # fmt: skip
            shard = sink.add(key, {**image,
                                   "txt": yolo_lines(boxes, w, h, ids).encode(),
                                   "json": json.dumps(info).encode()})  # fmt: skip
            if shard not in row["shards"]:
                row["shards"].append(shard)
        if a.max_per_session and row["kept"] >= a.max_per_session:
            break
    if classes is not None:
        row["excluded_species"] = _keyed(excluded)
        row["boxes_by_class_id"] = {str(k): v for k, v in sorted(class_boxes.items())}
    if mode is not None:
        row["labels"] = f"{labels}+species" if species else labels
    return row


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--train", nargs="*", default=[])
    ap.add_argument("--val", nargs="*", default=[])
    ap.add_argument("--test", nargs="*", default=[])
    ap.add_argument("--cache-id", default=None)
    ap.add_argument("--labels", choices=("v0", "v1", "v2"), default="v0")
    ap.add_argument("--k", type=float, default=None, help="v1/v2: M4's k (default: nostalro)")
    ap.add_argument("--every", type=int, default=15)  # H.264 (~32 fps): ~2 fps kept
    ap.add_argument("--every-png", type=int, default=1)  # PNG sessions (~1 fps): every frame
    ap.add_argument("--every-jpeg", type=int, default=EVERY_JPEG, help="warp_watch (5 Hz) sessions")
    ap.add_argument("--max-per-session", type=int, default=None)
    ap.add_argument("--datasets", type=Path, default=NAS)
    ap.add_argument(
        "--also-datasets",
        type=Path,
        nargs="*",
        default=[],
        help="more session roots, searched after --datasets (e.g. "
        "/mnt/poring-lab-datasets/detector-collection/orcsdun01 for a combined cache)",
    )
    ap.add_argument("--out", type=Path, default=OUT)
    ap.add_argument("--shard-mb", type=int, default=512)
    ap.add_argument(
        "--image",
        choices=("png", "jpeg"),
        default="jpeg",
        help="jpeg: q95 (Batt 2026-10-09: every future cache); png: lossless (v1png)",
    )
    ap.add_argument("--quality", type=int, default=95, help="jpeg only")
    ap.add_argument(
        "--resume",
        action="store_true",
        help="continue an interrupted build of the same --cache-id (same arguments)",
    )
    g = ap.add_argument_group("labels v2 (docs/planning/labels-v2-plan.md; local inputs, never "
                              "committed)")  # fmt: skip
    g.add_argument(
        "--kb",
        type=Path,
        default=None,
        help="v2, required: the KB dir (route.json, classes.json, sprite names)",
    )
    g.add_argument(
        "--warp-visibility",
        type=Path,
        default=None,
        help="v2, required: warp key -> visible|occluded|partial (a person's table)",
    )
    g.add_argument(
        "--npc-sprites",
        type=Path,
        default=None,
        help="v2: decoded NPC SPR/ACT dir (without it every NPC is unsized: excluded)",
    )
    g.add_argument("--npc-sprite-names", type=Path, default=None, help="v2: job -> sprite stem")
    g.add_argument(
        "--npc-extents",
        type=Path,
        default=None,
        help="v2: job -> [x0, y0, x1, y1] measured sprite px",
    )
    g.add_argument(
        "--npc-checked",
        type=Path,
        default=None,
        help='v2: N3 verdicts, "<job>" or "<map>:<job>" -> "fit" (else rejected)',
    )
    g.add_argument("--cutin-rect", default=None, help="v2: x0,y0,x1,y1 (default: ui_mask's)")
    g.add_argument(
        "--offset-ms",
        type=float,
        default=None,
        help="v2 demo sessions: packet->frame ms (default: the backend's benchmark)",
    )
    g.add_argument("--demo-root", type=Path, default=DEMO)
    g.add_argument("--every-demo", type=int, default=1, help="v2: every n-th banked demo frame")
    g.add_argument(
        "--allow-hold",
        nargs="*",
        default=[],
        choices=HOLDS,
        help="v2: lift a fail-closed hold once a person has decided it",
    )
    g.add_argument(
        "--classes",
        choices=("v2", "species"),
        default="v2",
        help="v2: player/monster/npc/warp; species: player/npc/warp + one class per monster "
        "species (--class-list; orcsdun01-detector.md section 4)",
    )
    g.add_argument(
        "--class-list",
        type=Path,
        default=SPECIES_LIST,
        help="--classes species: the committed list of ids (names come from --kb)",
    )
    g.add_argument(
        "--dry-run",
        action="store_true",
        help="v2: count only; no directory, shard or manifest; no image read",
    )
    g.add_argument(
        "--fix",
        type=Path,
        default=None,
        help="v2 + --classes species: the orcsdun01 label fix's frozen parameters "
        "(orc_labels_fix.py freeze); every kept frame is fitted on its pixels",
    )
    g.add_argument(
        "--fix-sha256",
        default=None,
        help="--fix: refuse unless the parameter file has exactly this sha256 (the frozen one)",
    )
    g.add_argument(
        "--collection",
        nargs="*",
        default=[],
        help="session roots <--datasets>/detector-collection/<MAP> searched after --datasets "
        "(e.g. orcsdun01: the warp_watch blocks), a name the guarded cache step accepts",
    )
    g.add_argument(
        "--rule",
        default="1a",
        help="--fix: the facing rule (1a: 3b; fix2: 3f, with 2b / 2c)",
    )
    g.add_argument(
        "--v1-species-sessions",
        nargs="*",
        default=[],
        help="v2 + --classes species: these sessions (each in a split) take the --labels v1 "
        "--classes species path instead (v1's rules + the species split; one cache)",
    )
    g.add_argument(
        "--allow-test-block",
        action="store_true",
        help="admit a *-col2 session (orcsdun01's TEST block) in --test: only after training ends",
    )
    g.add_argument(
        "--layout-templates",
        type=Path,
        default=None,
        help="--fix on a human demo: client_layout's templates (default its TEMPLATES)",
    )
    a = ap.parse_args(argv)
    split = {"train": a.train, "val": a.val, "test": a.test}
    seen = [s for ss in split.values() for s in ss]
    if not seen:
        raise SystemExit("no session: give --train/--val/--test (a test-only cache is for eval)")
    if len(seen) != len(set(seen)):
        raise SystemExit("a session is in two splits: the split is BY SESSION")
    if GOLD in a.train or GOLD in a.val:
        raise SystemExit(f"{GOLD} is the hand-checked gold set: test only")
    blocks = [s for s in seen if is_test_block(s)]
    if [s for s in blocks if s not in a.test] or (blocks and not a.allow_test_block):
        raise SystemExit(f"{blocks}: orcsdun01's pre-registered TEST block (3f) -- never in "
                         "train / val, in test only after training ends "
                         "(--allow-test-block)")  # fmt: skip
    v1_species = frozenset(a.v1_species_sessions)
    if v1_species:
        if a.labels != "v2" or a.classes != "species":
            raise SystemExit("--v1-species-sessions belongs to a --labels v2 --classes species "
                             "build")  # fmt: skip
        missing = sorted(v1_species - set(seen))
        if missing:
            raise SystemExit(f"--v1-species-sessions {missing}: not in any split")
    if a.fix is not None and (a.labels != "v2" or a.classes != "species"):
        raise SystemExit("--fix belongs to a --labels v2 --classes species build")
    fix = FixInputs.from_args(a)
    if fix is not None:
        off = float(fix.params["offset_ms"])
        if a.offset_ms is not None and float(a.offset_ms) != off:
            raise SystemExit(f"--offset-ms {a.offset_ms} vs the fix's frozen 1d {off} ms")
        a.offset_ms = off  # 1d replaces the benchmark's offset (orc_label_sheets.py --fix)
    if a.classes != "v2" and a.labels not in ("v1", "v2"):
        raise SystemExit("--classes species builds on --labels v1 (v1's rules, the species split "
                         "only) or --labels v2")  # fmt: skip
    if a.labels == "v1" and a.classes == "species" and a.kb is None:
        raise SystemExit("--labels v1 --classes species needs --kb (the class names)")
    if a.classes == "species" and a.k is None:
        a.k = SPECIES_K  # recorded as the build's k (args, manifest)
    v2 = V2Inputs.from_args(a) if a.labels == "v2" else None
    if a.dry_run:
        if a.resume or (v2 is None and not (a.labels == "v1" and a.classes == "species")):
            raise SystemExit("--dry-run is for --labels v2 or --labels v1 --classes species, "
                             "without --resume")  # fmt: skip
        if v2 is None:
            return dry_run_v1(a, split)
        return dry_run(a, split, v2, fix, v1_species)
    cache_id = a.cache_id or f"{a.labels}-{time.strftime('%Y%m%dT%H%M%S')}"
    directory = a.out / cache_id
    args = {"labels": a.labels, "k": a.k, "every": a.every, "every_png": a.every_png,
            "max_per_session": a.max_per_session, "shard_mb": a.shard_mb, "image": a.image,
            "quality": a.quality if a.image == "jpeg" else None, "split": split}  # fmt: skip
    if v2 is not None:  # v0 / v1 progress files keep their keys (a missing key resumes as None)
        args.update({"every_demo": a.every_demo, "every_jpeg": a.every_jpeg, "v2": v2.provenance})
    elif a.classes == "species":  # v1 + the species split (a v1 cache without it keeps its keys)
        args.update({"classes": SpeciesClasses.load(a.class_list).provenance()})
    extra = {}  # a build without them keeps its keys (old invocations byte-identical)
    if fix is not None:
        extra["fix"] = fix.provenance
    if v1_species:
        extra["v1_species_sessions"] = sorted(v1_species)
    args.update(extra)
    sessions: dict[str, Any] = {}
    shards: dict[str, Any] = {}
    if a.resume:
        if not a.cache_id:
            raise SystemExit("--resume needs the --cache-id of the interrupted build")
        sessions, shards = resume_state(directory, args)
        print(json.dumps({"resume": cache_id, "sessions_done": list(sessions)}), flush=True)
    elif directory.exists():
        raise SystemExit(f"{directory} exists: pick another --cache-id (or --resume it)")
    else:
        directory.mkdir(parents=True)
    start = 1 + max((int(n[6:12]) for n in shards), default=-1)
    sink = ShardSink(directory, a.shard_mb << 20, start, shards)
    t0 = time.monotonic()
    for part, ids in split.items():
        for sid in ids:
            if sid in sessions:
                continue  # done before the interruption (its shards were checked)
            if sid in v1_species:
                row = v01_session(sid, part, a, sink, mode=("v1", True))
            elif v2 is not None:
                row, _ = v2_session(sid, part, resolve_session(sid, a), a, v2, sink, fix)
            else:
                row = v01_session(sid, part, a, sink)
            sink.close()  # a session owns its shards: complete, or absent after a resume
            sessions[sid] = row
            write_json(directory, "progress.json",
                       {"args": args, "sessions": sessions, "shards": sink.done})  # fmt: skip
            print(json.dumps({sid: row}), flush=True)
    sink.close()
    manifest = {
        "cache_id": cache_id, "labels": a.labels, "k": a.k, "every": a.every,
        "every_png": a.every_png,
        "image": a.image, "quality": a.quality if a.image == "jpeg" else None,
        "names": (v2.class_names() if v2 is not None
                  else SpeciesClasses.load(a.class_list).names(a.kb) if a.classes == "species"
                  else {v: k for k, v in sorted(CLASSES.items(), key=lambda kv: kv[1])}),
        "split": split, "sessions": sessions, "shards": sink.done, "gold": GOLD,
        "built_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "seconds": round(time.monotonic() - t0, 1),
    }  # fmt: skip
    if v2 is not None:
        manifest.update(
            {"every_demo": a.every_demo, "every_jpeg": a.every_jpeg, "v2": v2.provenance}
        )
    manifest.update(extra)
    for name, doc in (("manifest.json", manifest), ("split.json", split)):
        write_json(directory, name, doc)
    print(json.dumps({"cache": str(directory), "frames": sum(r["kept"] for r in sessions.values()),
                      "shards": len(sink.done), "seconds": manifest["seconds"]}))  # fmt: skip
    return 0


if __name__ == "__main__":
    sys.exit(main())
