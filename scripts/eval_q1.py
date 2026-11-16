#!/usr/bin/env python3
"""Q1 / E1 of docs/benchmarks/gef10-eval.md (AMENDMENT R2-2): a per-species detector on the
evaluation pack's crops, scored by the POSITION metric (label_iou.match_position's pairs).

    eval_q1.py refs  KEY.json --out REFS.json [--latency-200 SEED [--latency-out PATH]]
                     [--labels-dir DIR] [--session-root /mnt/poring-lab-datasets]
                     [--host-root /mnt/poring-lab-datasets] [--container-root /datasets]
                     [--no-verify]
    eval_q1.py score KEY.json A.json B.json PRED.json --cache-manifest MANIFEST.json
                     --out SCORE.json [--any-settings]

refs: predict_dir's ``--refs`` input for EXACTLY the frames that carry a pack crop (the key's
crops, evaluated or not: the detections do not depend on the answers). Each frame's bytes are
found through the label files the pack drew from (the key's ``sources``: their sha256 is checked,
fail closed) and named ``frame_key(session, frame_id)``; the host path under the NAS
(/mnt/poring-lab-datasets) becomes the vision container's (/datasets). The refs are verified on
the host (unless ``--no-verify``): each frame's first 8 bytes are a PNG / JPEG signature, and the
tar member's own name states the same frame id (when it states one), or a refusal.
``--latency-200 SEED``: a second refs file, the first 200 of those frames by
``random.Random(SEED).shuffle`` of the frame keys in sorted order (R2-2's latency frames; seed 35).

score: a crop is EVALUATED when BOTH labellers answer q1 = yes, q2 = good and q3 = the letter of
the crop's species (blind_score.py's answer format and letters). Per frame of the evaluated crops,
ONE position match over all its evaluated crops (one-to-one per frame, nearest centre first: the
class of a detection must be the crop species' class). Per stratum (N -> Q1, E -> E1) and species
s:
  * recall    = the evaluated s crops matched / the evaluated s crops;
  * precision = those matches / (those matches + the UNMATCHED class-s detections whose centre lies
    inside any evaluated crop's box of that stratum in the frame). A detection matched to a crop
    counts only for that crop's stratum; detections outside every evaluated box are not scored.
    With one stratum per frame this is gef10-eval.md's "the class-s detections whose centre falls
    inside ANY evaluated crop's box of the frame" exactly; ``strata_overlap`` counts the frames and
    detections where the two strata meet.
  * the bar, for a species with >= 50 evaluated crops: recall >= 0.80 AND precision >= 0.80
    (exact integer comparisons); fewer: reported, no bar. ``all_bars_pass`` is None when no
    species has a bar (stated, never read as a pass).
Reported beside, deciding nothing: the split by session (the TEST part) and by under-a-model; the
look-alike confusion (each evaluated crop's detection by a CLASS-BLIND position match: its class or
"none"); why crops were not evaluated.

Q1c / E1c, the COLLAPSED-class score (docs/planning/xmas02-detector.md 9, T-9: the verdict of a
map-scoped model whose runner collapses its species to ``monster``), beside Q1 / E1 (unchanged):
every detection of ANY of the manifest's monster classes is one class, ``monster:any`` (player,
npc and warp are not); per frame ONE position match of those detections over all its evaluated
crops (nearest centre first). Per stratum and species s:
  * recall    = the evaluated s crops matched by any monster detection / the evaluated s crops;
  * precision = those matches / (those matches + the UNMATCHED monster detections whose centre lies
    inside ANY evaluated crop's box of that stratum): Q1's own rule (``numbers``, unchanged) with
    the classes collapsed, so every species is charged every unmatched monster detection inside
    an evaluated box (the gef10 rule: a class-s detection inside ANY evaluated box counts against
    s; here every monster detection is "class s");
  * REPORTED beside it, deciding nothing: ``precision_own_boxes`` (only the unmatched monster
    detections inside an evaluated s crop's box; one inside the boxes of two species counts
    against both) and ``pooled`` (all species' matches over the same unmatched detections);
  * the bar as Q1's (>= 50 evaluated crops: recall >= 0.80 AND precision >= 0.80).

Q1crowd (docs/planning/xmas02-detector.md Amendment S5, 2026-11-15: the knight's party stands in a
heap, so a correct box on a unit that is not one of the pack's crops was charged as false),
``score ... --units UNITS.json``, beside Q1 (unchanged): the same matches and Q1's scope (the
UNMATCHED class-s detections whose centre lies inside an evaluated box), but such a detection is
FALSE only when it lies on NO unit of species s in its frame by the PACKETS (``units``: its IoU with
a kept s label's fitted box >= 0.5, or its centre inside an s unit's region); the rest are
``absolved``. The false ones are split into "on a unit of another species" and "on no unit".
REPORTED beside it: ``frame_wide`` (every unmatched class-s detection of the evaluated frames,
inside an evaluated box or not, judged the same way). The bar as Q1's.

    eval_q1.py units KEY.json --params PARAMS(FROZEN) --out UNITS.json [--all-frames]
                     [--labels-dir DIR] [--session-root /mnt/poring-lab-datasets]
    eval_q1.py party UNITS.json PRED.json --cache-manifest MANIFEST.json --out PARTY.json

units: per frame of the key's crops (``--all-frames``: every candidate frame of its source label
files), every visible monster of the frame's Timeline world (map_labels.frame_units: the sprite
envelope at the labeller's anchor, grown by the map's fit radius, clipped), each marked with its
label in the source file (``kept`` + its fitted box, the exclusion reason, or ``unlisted``).
Client- and packet-derived: /dev/shm or data/ only, never committed.
party (S5, REPORTED, deciding nothing; the alarm's view): per frame of UNITS x PRED, whether a
Goblin / a party unit is on screen (packets) and whether a Goblin-class box is (conf >= 0.25 /
0.5 / 0.7): the frame recall, the false-alarm frames (no party unit on screen), where every
Goblin-class box lies, and per VISIT (a run of party frames, a gap > 5 s ends it) the delay from
the first Goblin on screen to the first Goblin-class box.

THE ALARM (docs/planning/xmas02-detector.md Amendment S6, 2026-11-16, Batt: "the alarm signal"):

    eval_q1.py alarm --held-out UNITS PRED [--free UNITS PRED ...] --cache-manifest MANIFEST.json
                     --out ALARM.json

judged per VISIT and per frame, the way the runner flies (live-blocks.md 11.2, dungeon@9.53):
  * an ALARM-CLASS box is a box of the Goblin, the knight or Garm Baby (their union: a boss
    sighting, Batt's decision 6). The runner FIRES at a frame holding one at conf >= ALARM_SOLO,
    or holding one at conf >= ALARM_CONF when the previous frame (<= CONFIRM_GAP_S earlier) held
    one too (--garm-confirm 2);
  * a VISIT (the packets, as party): a run of frames with a party unit (Goblin or knight) on
    screen; a gap > VISIT_GAP_S ends it. It is DETECTED when a fire falls within ALARM_WINDOW_S
    of its first frame;
  * an ALARM-FREE frame has no unit of the three species on screen; a fire there is a FALSE fire.
The bar lines (S6) and their minimums are in ``alarm_bars``; the verdict is FAIL when a judged
line fails, INCONCLUSIVE when none fails but one cannot be judged, else PASS. --free sets are
pooled (Goblin-free held-outs whose frames need not be consecutive: there only the solo branch
can fire).

The species <-> class map is EXPLICIT: ``--cache-manifest``, the manifest of the cache the model
trained on (its ``names`` = the model's class names, its ``classes`` = the committed list's mob ids
in id order; build_frame_cache.py SpeciesClasses). A detection class the manifest does not name
is refused (a different model). PRED.json is predict_dir's output; settings other than imgsz 1280
and conf 0.25 are refused unless ``--any-settings``. Labels, crops and keys are client-derived:
they stay in /dev/shm or data/, never committed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import sys
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import blind_score  # noqa: E402
import label_iou  # noqa: E402

from poring_dataset.metrics import Box  # noqa: E402

HOST_ROOT = Path("/mnt/poring-lab-datasets")
CONTAINER_ROOT = Path("/datasets")
LATENCY_N = 200
BAR_MIN_CROPS = 50
SETTINGS = {"imgsz": 1280, "conf": 0.25}
FIXED = ("player", "npc", "warp")
IMAGE_HEADS = (b"\x89PNG\r\n\x1a\n", b"\xff\xd8\xff")
# gef10-eval.md "Reported": the look-alike groups, by mob id
LOOK_ALIKE = {
    "lord_warrior_archer": (1190, 1023, 1189),
    "poporing_poring": (1031, 1002),
    "baby_vs_other_orcs": (1686, 1273, 1023, 1190, 1189),
}
STRATUM_SCORE = {"N": "Q1", "E": "E1"}
# xmas02-detector.md 9 / T-9: the collapsed-class score per stratum, and its one class (a name no
# model class can have: the manifest's names are species names and FIXED)
STRATUM_SCORE_C = {"N": "Q1c", "E": "E1c"}
COLLAPSED = "monster:any"
# REPORTED look-alike groups shown only when one of their species is a class (gef10's output keeps
# its three groups exactly; xmas02 6: the two cookies differ ONLY in colour)
LOOK_ALIKE_IF_CLASS = {"cookie_christmas_cookie": (1265, 1246)}


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


# --- refs ---------------------------------------------------------------------------------------


def frame_key(session: str, frame_id: int) -> str:
    """PURE: one recorded frame's stable key (predict_dir's --refs key = PRED.json's frame key):
    ``<session>.<frame_id, 9 digits>``, the frame caches' own member naming."""
    return f"{session}.{int(frame_id):09d}"


def to_container(path: Path, host_root: Path = HOST_ROOT,
                 container_root: Path = CONTAINER_ROOT) -> str:  # fmt: skip
    """PURE: a host path under the NAS -> the vision container's path (fail closed elsewhere)."""
    try:
        rel = Path(path).relative_to(host_root)
    except ValueError:
        raise SystemExit(f"{path}: not under {host_root}; the vision container reads only the NAS "
                         f"(as {container_root})") from None  # fmt: skip
    return str(container_root / rel)


def resolve_source(file: str, key_path: Path, labels_dir: Path | None) -> Path:
    """A key ``sources`` file: --labels-dir/<name> first, else as written (absolute), else relative
    to the cwd, the key's directory's parent (map_labels.py pack's cwd beside --key-dir) or the
    key's directory."""
    p = Path(file)
    cands = [labels_dir / p.name] if labels_dir is not None else []
    if p.is_absolute():
        cands.append(p)
    else:
        kd = key_path.resolve().parent
        cands += [Path.cwd() / p, kd.parent / p, kd / p]
    for c in cands:
        if c.is_file():
            return c
    raise SystemExit(f"the label file {file} is in none of {[str(c) for c in cands]}")


def frame_rows(key: Mapping[str, Any], key_path: Path, labels_dir: Path | None = None
               ) -> dict[tuple[str, int], dict[str, Any]]:  # fmt: skip
    """(session, frame_id) -> {shard, offset, size}, from the key's ``sources`` (sha256 checked)."""
    rows: dict[tuple[str, int], dict[str, Any]] = {}
    for src in key["sources"]:
        path = resolve_source(str(src["file"]), key_path, labels_dir)
        sha = sha256_file(path)
        if sha != src["sha256"]:
            raise SystemExit(f"{path}: sha256 {sha}, the key recorded {src['sha256']}")
        doc = json.loads(path.read_text())
        for f in doc["frames"]:
            k = (str(doc["session"]), int(f["frame_id"]))
            ref = {"shard": str(f["shard"]), "offset": int(f["offset"]), "size": int(f["size"])}
            if rows.setdefault(k, ref) != ref:
                raise SystemExit(f"{k}: two label files disagree on where its bytes lie")
    return rows


def crop_frames(key: Mapping[str, Any]) -> list[tuple[str, int]]:
    """PURE: the frames that carry a pack crop, sorted by (session, frame_id)."""
    return sorted({(str(c["session"]), int(c["frame_id"])) for c in key["crops"].values()})


def build_refs(frames: Sequence[tuple[str, int]], rows: Mapping[tuple[str, int], Any],
               session_root: Path) -> dict[str, dict[str, Any]]:  # fmt: skip
    """PURE: {frame_key: {path (HOST), offset, size}} for each frame, in the given order."""
    missing = [f for f in frames if f not in rows]
    if missing:
        raise SystemExit(f"{len(missing)} crop frames are in no source label file: {missing[:5]}")
    out: dict[str, dict[str, Any]] = {}
    for s, fid in frames:
        r = rows[(s, fid)]
        out[frame_key(s, fid)] = {"path": str(session_root / s / r["shard"]),
                                  "offset": r["offset"], "size": r["size"]}  # fmt: skip
    return out


def containerise(refs: Mapping[str, Mapping[str, Any]], host_root: Path = HOST_ROOT,
                 container_root: Path = CONTAINER_ROOT) -> dict[str, dict[str, Any]]:  # fmt: skip
    """PURE: the same refs with container paths (predict_dir runs in the vision container)."""
    return {k: {**r, "path": to_container(Path(r["path"]), host_root, container_root)}
            for k, r in refs.items()}  # fmt: skip


def member_frame_id(header: bytes) -> int | None:
    """PURE: the frame id a tar member's name states (the recorder names a frame's members
    ``<frame_id, 9 digits>.<ext>``); None for any other naming."""
    stem = header[:100].split(b"\0", 1)[0].decode("ascii", "replace").rsplit("/", 1)[-1]
    stem = stem.split(".", 1)[0]
    return int(stem) if stem.isdigit() else None


def verify_refs(refs: Mapping[str, Mapping[str, Any]],
                frames: Sequence[tuple[str, int]]) -> dict[str, int]:  # fmt: skip
    """Each HOST ref: an image signature (PNG / JPEG) at its offset, and the tar member's own name
    (the 512-byte header just before it) states the same frame id when it states one; else a
    refusal. Two small reads per frame."""
    named = 0
    for s, fid in frames:
        k = frame_key(s, fid)
        r = refs[k]
        off = int(r["offset"])
        if not Path(r["path"]).is_file():
            raise SystemExit(f"{k}: {r['path']} does not exist (is the session on the NAS?)")
        with open(r["path"], "rb") as fh:
            fh.seek(off - 512)
            header, head = fh.read(512), fh.read(8)
        if not any(head.startswith(sig) for sig in IMAGE_HEADS):
            raise SystemExit(f"{k}: no image at {r['path']}@{off}")
        stated = member_frame_id(header)
        if stated is not None and stated != fid:
            raise SystemExit(f"{k}: the tar member at {r['path']}@{off} is frame {stated}")
        named += stated is not None
    return {"image_signature": len(frames), "member_name_frame_id": named}


def latency_keys(keys: Iterable[str], seed: int, n: int = LATENCY_N) -> list[str]:
    """PURE (R2-2): the first n of the sorted keys after ``random.Random(seed).shuffle``."""
    order = sorted(keys)
    random.Random(seed).shuffle(order)
    return order[:n]


def cmd_refs(a: argparse.Namespace) -> int:
    key = json.loads(a.key.read_text())
    rows = frame_rows(key, a.key, a.labels_dir)
    frames = crop_frames(key)
    host = build_refs(frames, rows, a.session_root)
    checked = None if a.no_verify else verify_refs(host, frames)
    refs = containerise(host, a.host_root, a.container_root)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(refs, indent=1) + "\n")
    done: dict[str, Any] = {"key": str(a.key), "key_sha256": sha256_file(a.key),
                            "frames": len(refs), "crops": len(key["crops"]),
                            "verified": checked, "out": str(a.out)}  # fmt: skip
    if a.latency_200 is not None:
        pick = latency_keys(refs, a.latency_200)
        lat = a.latency_out or a.out.with_name(f"{a.out.stem}-latency200-seed{a.latency_200}.json")
        lat.write_text(json.dumps({k: refs[k] for k in pick}, indent=1) + "\n")
        done["latency"] = {"seed": a.latency_200, "frames": len(pick), "out": str(lat)}
    print(json.dumps(done, indent=1))
    return 0


# --- score --------------------------------------------------------------------------------------


def class_map(manifest: Mapping[str, Any]) -> dict[int, str]:
    """PURE: mob id -> the model's class name, from a per-species training cache's manifest."""
    cl = manifest.get("classes") or {}
    if cl.get("mode") != "species":
        raise SystemExit("the manifest is not a per-species cache's (classes.mode != species)")
    names = {int(k): str(v) for k, v in manifest["names"].items()}
    fixed = {str(k): int(v) for k, v in (cl.get("fixed") or {}).items()}
    if any(names.get(v) != k for k, v in fixed.items()):
        raise SystemExit(f"the manifest's names disagree with its fixed classes {fixed}")
    first = int(cl["monster_first_id"])
    out: dict[int, str] = {}
    for i, mob in enumerate(cl["monsters"]):
        if first + i not in names:
            raise SystemExit(f"species {mob}: class id {first + i} has no name")
        out[int(mob)] = names[first + i]
    if len(set(out.values())) != len(out) or set(out.values()) & set(FIXED):
        raise SystemExit("two species share a class name, or one is named like a fixed class")
    return out


def stratum_of(crop: Mapping[str, Any]) -> str:
    """PURE: the crop's stratum (the key's ``stratum``; a key without strata: by ``engaged``)."""
    st = crop.get("stratum")
    if st in STRATUM_SCORE:
        return str(st)
    return "E" if crop.get("engaged") else "N"


def not_evaluated_reason(x: Mapping[str, Any] | None, mob: int, letters: Mapping[str, int]
                         ) -> str | None:  # fmt: skip
    """PURE: why one labeller's answer does not count (None: it does)."""
    if x is None:
        return "missing_answer"
    if x.get("q1") != "yes":
        return "q1_not_yes"
    if x.get("q2") != "good":
        return "q2_not_good"
    if letters.get(str(x.get("q3", "")).strip().upper()) != mob:
        return "q3_not_the_species"
    return None


def evaluated(key: Mapping[str, Any], a: Mapping[str, Mapping[str, Any]],
              b: Mapping[str, Mapping[str, Any]]) -> tuple[list[str], dict[str, Any]]:  # fmt: skip
    """PURE: the EVALUATED crops (both labellers: q1 yes, q2 good, q3 the species) and, per
    labeller, the reasons the others fell out."""
    letters = {str(k).upper(): int(v) for k, v in key["letters"].items()}
    out: list[str] = []
    why: dict[str, Counter[str]] = {"A": Counter(), "B": Counter()}
    for crop, k in key["crops"].items():
        mob = int(k["mob"])
        ra = not_evaluated_reason(a.get(crop), mob, letters)
        rb = not_evaluated_reason(b.get(crop), mob, letters)
        if ra is None and rb is None:
            out.append(crop)
        for who, r in (("A", ra), ("B", rb)):
            if r is not None:
                why[who][r] += 1
    unknown = sorted((set(a) | set(b)) - set(key["crops"]))
    return out, {"not_evaluated_by": {w: dict(sorted(c.items())) for w, c in why.items()},
                 "answers_for_unknown_crops": unknown}  # fmt: skip


def boxes(items: Iterable[Mapping[str, Any]]) -> list[Box]:
    return [(str(d["cls"]), float(d["x1"]), float(d["y1"]), float(d["x2"]), float(d["y2"]))
            for d in items]  # fmt: skip


Matched = tuple[dict[str, dict[str, Any]], list[dict[str, Any]], dict[str, int]]


def match_frames(key: Mapping[str, Any], crops: Sequence[str],
                 frames: Mapping[str, Sequence[Mapping[str, Any]]], species_cls: Mapping[int, str]
                 ) -> Matched:  # fmt: skip
    """PURE: per evaluated crop {matched, seen_as}; the UNMATCHED detections inside >= 1 evaluated
    box ({cls, crops}); and the strata-overlap counts. One position match per frame over all its
    evaluated crops (class-aware), and one class-blind match for ``seen_as``."""
    by_frame: dict[str, list[str]] = defaultdict(list)
    for c in crops:
        k = key["crops"][c]
        by_frame[frame_key(k["session"], k["frame_id"])].append(c)
    missing = [f for f in by_frame if f not in frames]
    if missing:
        raise SystemExit(f"PRED.json lacks {len(missing)} evaluated frames: {sorted(missing)[:5]}")
    rec: dict[str, dict[str, Any]] = {}
    loose: list[dict[str, Any]] = []
    overlap = Counter(dict.fromkeys(("frames_both_strata",
                                     "matched_detections_also_in_other_stratum",
                                     "unmatched_detections_in_both_strata"), 0))  # fmt: skip
    for fk in sorted(by_frame):
        cs = by_frame[fk]
        mobs = [int(key["crops"][c]["mob"]) for c in cs]
        truth = boxes({"cls": species_cls.get(m, f"unlisted:{m}"),
                       **dict(zip(("x1", "y1", "x2", "y2"), key["crops"][c]["box"], strict=True))}
                      for c, m in zip(cs, mobs, strict=True))  # fmt: skip
        pred = boxes(frames[fk])
        pairs = {i: j for _d, i, j in label_iou.position_pairs(truth, pred)}
        blind = label_iou.position_pairs([("*", *t[1:]) for t in truth],
                                         [("*", *p[1:]) for p in pred])  # fmt: skip
        seen = {i: pred[j][0] for _d, i, j in blind}
        strata = {stratum_of(key["crops"][c]) for c in cs}
        overlap["frames_both_strata"] += len(strata) > 1
        matched_det = {j: i for i, j in pairs.items()}
        for j, p in enumerate(pred):
            inside = [i for i, t in enumerate(truth) if label_iou.centre_inside(p, t)]
            if not inside:
                continue
            in_strata = {stratum_of(key["crops"][cs[i]]) for i in inside}
            if j in matched_det:
                own = stratum_of(key["crops"][cs[matched_det[j]]])
                overlap["matched_detections_also_in_other_stratum"] += bool(in_strata - {own})
                continue
            overlap["unmatched_detections_in_both_strata"] += len(in_strata) > 1
            loose.append({"cls": p[0], "crops": frozenset(cs[i] for i in inside)})
        for i, c in enumerate(cs):
            rec[c] = {"matched": i in pairs, "seen_as": seen.get(i)}
    return rec, loose, dict(overlap)


def numbers(key: Mapping[str, Any], group: Sequence[str], mob: int, cls: str,
            rec: Mapping[str, Mapping[str, Any]], loose: Sequence[Mapping[str, Any]],
            bar: bool) -> dict[str, Any]:  # fmt: skip
    """PURE: one species' recall / precision on a group of evaluated crops (one stratum)."""
    ids = set(group)
    mine = [c for c in group if int(key["crops"][c]["mob"]) == mob]
    n = len(mine)
    tp = sum(bool(rec[c]["matched"]) for c in mine)
    fp = sum(1 for d in loose if d["cls"] == cls and d["crops"] & ids)
    out: dict[str, Any] = {
        "mob": mob, "class": cls, "evaluated": n, "matched": tp, "unmatched_in_boxes": fp,
        "recall": round(tp / n, 4) if n else None,
        "precision": round(tp / (tp + fp), 4) if tp + fp else None,
    }  # fmt: skip
    if bar:
        has_bar = n >= BAR_MIN_CROPS
        out["bar"] = has_bar
        # recall >= 0.80 <=> 5 tp >= 4 n; precision >= 0.80 <=> tp >= 4 fp (and tp > 0)
        out["pass"] = (5 * tp >= 4 * n and tp > 0 and tp >= 4 * fp) if has_bar else None
    return out


def species_order(key: Mapping[str, Any], crops: Iterable[str]) -> list[int]:
    seen = {int(key["crops"][c]["mob"]) for c in crops}
    tier = [int(m) for m in key.get("tier_species", []) if int(m) in seen]
    return tier + sorted(seen - set(tier))


def per_species(key: Mapping[str, Any], group: Sequence[str], species_cls: Mapping[int, str],
                rec: Mapping[str, Mapping[str, Any]], loose: Sequence[Mapping[str, Any]],
                bar: bool) -> dict[str, dict[str, Any]]:  # fmt: skip
    return {species_cls.get(m, f"unlisted:{m}"):
            numbers(key, group, m, species_cls.get(m, f"unlisted:{m}"), rec, loose, bar)
            for m in species_order(key, group)}  # fmt: skip


def split_by(key: Mapping[str, Any], crops: Sequence[str], field: str
             ) -> dict[str, list[str]]:  # fmt: skip
    """PURE: the crops grouped by a key field (``session``; ``under``: under / clear / unknown)."""
    out: dict[str, list[str]] = defaultdict(list)
    for c in crops:
        v = key["crops"][c].get(field)
        if field == "under":
            name = "under" if v is True else "clear" if v is False else "unknown"
        else:
            name = str(v)
        out[name].append(c)
    return dict(sorted(out.items()))


def confusion(key: Mapping[str, Any], crops: Sequence[str], species_cls: Mapping[int, str],
              rec: Mapping[str, Mapping[str, Any]]) -> dict[str, dict[str, int]]:  # fmt: skip
    """PURE: per species, the class each evaluated crop was SEEN AS (class-blind match; none)."""
    out: dict[str, Counter[str]] = defaultdict(Counter)
    for c in crops:
        m = int(key["crops"][c]["mob"])
        out[species_cls.get(m, f"unlisted:{m}")][rec[c]["seen_as"] or "none"] += 1
    return {s: dict(sorted(v.items())) for s, v in sorted(out.items())}


def collapsed_frames(frames: Mapping[str, Sequence[Mapping[str, Any]]],
                     species_cls: Mapping[int, str]
                     ) -> dict[str, list[dict[str, Any]]]:  # fmt: skip
    """PURE (Q1c): the detections with every monster class (``species_cls``'s values) renamed
    COLLAPSED; any other class (player, npc, warp) kept as it is."""
    monster = {str(c) for c in species_cls.values()}
    return {fk: [{**d, "cls": COLLAPSED if str(d["cls"]) in monster else str(d["cls"])}
                 for d in ds]
            for fk, ds in frames.items()}  # fmt: skip


def collapsed_score(key: Mapping[str, Any], crops: Sequence[str],
                    frames: Mapping[str, Sequence[Mapping[str, Any]]],
                    species_cls: Mapping[int, str]) -> dict[str, Any]:  # fmt: skip
    """PURE (xmas02-detector.md 9, T-9): Q1c / E1c per species (the classes COLLAPSED), pooled,
    and split by session. A species the manifest does not list is ``not_a_class`` (its crops
    keep the class ``unlisted:<mob>``, which no detection has), as in Q1."""
    one = {m: COLLAPSED for m in species_cls}
    rec, loose, _overlap = match_frames(key, crops, collapsed_frames(frames, species_cls), one)
    out: dict[str, Any] = {}
    for st, name in STRATUM_SCORE_C.items():
        group = [c for c in crops if stratum_of(key["crops"][c]) == st]

        def species_rows(g: Sequence[str], bar: bool) -> dict[str, dict[str, Any]]:
            rows: dict[str, dict[str, Any]] = {}
            for m in species_order(key, g):
                row = numbers(key, g, m, one.get(m, f"unlisted:{m}"), rec, loose, bar)
                mine = {c for c in g if int(key["crops"][c]["mob"]) == m}
                own = sum(1 for d in loose if d["cls"] == COLLAPSED and d["crops"] & mine)
                tp = int(row["matched"])
                row.update({"unmatched_in_own_boxes": own,
                            "precision_own_boxes": round(tp / (tp + own), 4) if tp + own
                            else None})  # fmt: skip
                rows[species_cls.get(m, f"unlisted:{m}")] = row
            return rows

        res = species_rows(group, True)
        unlisted = {s: v for s, v in res.items() if s.startswith("unlisted:")}
        scored = {s: v for s, v in res.items() if not s.startswith("unlisted:")}
        barred = {s: v["pass"] for s, v in scored.items() if v["bar"]}
        listed = [c for c in group if int(key["crops"][c]["mob"]) in one]
        tp = sum(bool(rec[c]["matched"]) for c in listed)
        fp = sum(1 for d in loose if d["cls"] == COLLAPSED and d["crops"] & set(group))
        out[name] = {
            "stratum": st, "evaluated_crops": len(group), "class": COLLAPSED,
            "classes_collapsed": sorted({str(c) for c in species_cls.values()}),
            "per_species": scored, "not_a_class": unlisted, "species_with_bar": sorted(barred),
            "all_bars_pass": all(barred.values()) if barred else None,
            "pooled": {"evaluated": len(listed), "matched": tp, "unmatched_in_boxes": fp,
                       "recall": round(tp / len(listed), 4) if listed else None,
                       "precision": round(tp / (tp + fp), 4) if tp + fp else None},
            "split_session": {k: species_rows(g, False)
                              for k, g in split_by(key, group, "session").items()},
        }  # fmt: skip
    return out


def score(key: Mapping[str, Any], crops: Sequence[str],
          frames: Mapping[str, Sequence[Mapping[str, Any]]], species_cls: Mapping[int, str]
          ) -> dict[str, Any]:  # fmt: skip
    """PURE: Q1 / E1 per species, the splits, the confusion and the look-alike groups (and,
    beside them, the collapsed-class Q1c / E1c: collapsed_score)."""
    rec, loose, overlap = match_frames(key, crops, frames, species_cls)
    out: dict[str, Any] = {}
    for st, name in STRATUM_SCORE.items():
        group = [c for c in crops if stratum_of(key["crops"][c]) == st]
        res = per_species(key, group, species_cls, rec, loose, bar=True)
        unlisted = {s: v for s, v in res.items() if s.startswith("unlisted:")}
        scored = {s: v for s, v in res.items() if not s.startswith("unlisted:")}
        barred = {s: v["pass"] for s, v in scored.items() if v["bar"]}
        conf = confusion(key, group, species_cls, rec)
        out[name] = {
            "stratum": st, "evaluated_crops": len(group), "per_species": scored,
            "not_a_class": unlisted, "species_with_bar": sorted(barred),
            "all_bars_pass": all(barred.values()) if barred else None,
            "split_session": {k: per_species(key, g, species_cls, rec, loose, bar=False)
                              for k, g in split_by(key, group, "session").items()},
            "split_under": {k: per_species(key, g, species_cls, rec, loose, bar=False)
                            for k, g in split_by(key, group, "under").items()},
            "confusion": conf,
            "look_alike": {
                gname: {species_cls[m]: conf[species_cls[m]] for m in mobs
                        if m in species_cls and species_cls[m] in conf}
                for gname, mobs in {**LOOK_ALIKE, **{g: ms for g, ms in LOOK_ALIKE_IF_CLASS.items()
                                                     if any(m in species_cls for m in ms)}}.items()
            },
        }  # fmt: skip
    out["strata_overlap"] = overlap
    out.update(collapsed_score(key, crops, frames, species_cls))
    return out


# --- Q1crowd and the party view (xmas02-detector.md Amendment S5) ----------------------------

CROWD_IOU = 0.5  # a detection lies on a kept label when their IoU reaches this
PARTY_THRESHOLDS = (0.25, 0.5, 0.7)  # predict_dir's conf; 0.5; the live alarm's --alarm-solo
VISIT_GAP_S = 5.0  # party frames this far apart are two visits
GOBLIN, PARTY = 1607, (1607, 1251)  # the Christmas Goblin; the knight's party (Goblin + knight)


def iou(a: Sequence[float], b: Sequence[float]) -> float:
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    union_ = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - ix * iy
    return ix * iy / union_ if union_ > 0 else 0.0


def det_box(d: Mapping[str, Any]) -> tuple[float, float, float, float]:
    return float(d["x1"]), float(d["y1"]), float(d["x2"]), float(d["y2"])


def lies_on(box: Sequence[float], units: Sequence[Mapping[str, Any]]) -> set[int]:
    """PURE: the species of the units a detection box lies on: IoU >= CROWD_IOU with a kept unit's
    fitted box, or its centre inside a unit's region."""
    cx, cy = (box[0] + box[2]) / 2.0, (box[1] + box[3]) / 2.0
    out: set[int] = set()
    for u in units:
        kb, r = u.get("kept_box"), u.get("region")
        if (kb is not None and iou(box, kb) >= CROWD_IOU) or (
                r is not None and r[0] <= cx <= r[2] and r[1] <= cy <= r[3]):  # fmt: skip
            out.add(int(u["mob"]))
    return out


def unmatched_dets(key: Mapping[str, Any], crops: Sequence[str],
                   frames: Mapping[str, Sequence[Mapping[str, Any]]], species_cls: Mapping[int, str]
                   ) -> list[dict[str, Any]]:  # fmt: skip
    """PURE: every detection of an evaluated frame that Q1's class-aware match leaves unmatched:
    {fk, cls, box, inside (the evaluated crops whose box holds its centre)}; match_frames' pairs."""
    by_frame: dict[str, list[str]] = defaultdict(list)
    for c in crops:
        k = key["crops"][c]
        by_frame[frame_key(k["session"], k["frame_id"])].append(c)
    out: list[dict[str, Any]] = []
    for fk in sorted(by_frame):
        cs = by_frame[fk]
        truth = boxes({"cls": species_cls.get(int(key["crops"][c]["mob"]),
                                              f"unlisted:{key['crops'][c]['mob']}"),
                       **dict(zip(("x1", "y1", "x2", "y2"), key["crops"][c]["box"], strict=True))}
                      for c in cs)  # fmt: skip
        pred = boxes(frames[fk])
        matched = {j for _d, _i, j in label_iou.position_pairs(truth, pred)}
        for j, p in enumerate(pred):
            if j in matched:
                continue
            inside = frozenset(cs[i] for i, t in enumerate(truth) if label_iou.centre_inside(p, t))
            out.append({"fk": fk, "cls": p[0], "box": det_box(frames[fk][j]), "inside": inside})
    return out


def crowd_score(key: Mapping[str, Any], crops: Sequence[str],
                frames: Mapping[str, Sequence[Mapping[str, Any]]], species_cls: Mapping[int, str],
                units: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:  # fmt: skip
    """PURE (S5): Q1crowd per stratum and species (the module doc); fails closed when an evaluated
    frame has no units."""
    need = {frame_key(key["crops"][c]["session"], key["crops"][c]["frame_id"]) for c in crops}
    lacking = sorted(need - set(units))
    if lacking:
        raise SystemExit(f"--units lacks {len(lacking)} evaluated frames: {lacking[:5]}")
    rec, _loose, _overlap = match_frames(key, crops, frames, species_cls)
    dets = unmatched_dets(key, crops, frames, species_cls)
    on = [lies_on(d["box"], units[d["fk"]]["units"]) for d in dets]
    out: dict[str, Any] = {}
    for st, name in STRATUM_SCORE.items():
        group = [c for c in crops if stratum_of(key["crops"][c]) == st]
        gset = set(group)
        rows: dict[str, dict[str, Any]] = {}
        for m in species_order(key, group):
            cls = species_cls.get(m)
            if cls is None:
                continue
            mine = [c for c in group if int(key["crops"][c]["mob"]) == m]
            n, tp = len(mine), sum(bool(rec[c]["matched"]) for c in mine)
            frames_g = {frame_key(key["crops"][c]["session"], key["crops"][c]["frame_id"])
                        for c in group}  # fmt: skip

            def judged(scope: list[int], m: int = m) -> dict[str, int]:
                false = [i for i in scope if m not in on[i]]
                return {"unmatched": len(scope), "absolved": len(scope) - len(false),
                        "false": len(false),
                        "false_on_other_species": sum(1 for i in false if on[i]),
                        "false_on_no_unit": sum(1 for i in false if not on[i])}  # fmt: skip

            mine_cls = [i for i, d in enumerate(dets) if d["cls"] == cls and d["fk"] in frames_g]
            inbox = judged([i for i in mine_cls if dets[i]["inside"] & gset])
            wide = judged(mine_cls)
            fp = inbox["false"]
            has_bar = n >= BAR_MIN_CROPS
            rows[cls] = {
                "mob": m, "class": cls, "evaluated": n, "matched": tp,
                "recall": round(tp / n, 4) if n else None,
                "in_boxes": inbox, "precision": round(tp / (tp + fp), 4) if tp + fp else None,
                "bar": has_bar,
                # recall >= 0.80 <=> 5 tp >= 4 n; precision >= 0.80 <=> tp >= 4 fp (and tp > 0)
                "pass": (5 * tp >= 4 * n and tp > 0 and tp >= 4 * fp) if has_bar else None,
                "frame_wide": {**wide, "precision": round(tp / (tp + wide["false"]), 4)
                               if tp + wide["false"] else None},
            }  # fmt: skip
        barred = {k: v["pass"] for k, v in rows.items() if v["bar"]}
        out[name.replace("Q1", "Q1crowd").replace("E1", "E1crowd")] = {
            "stratum": st, "evaluated_crops": len(group), "per_species": rows,
            "species_with_bar": sorted(barred),
            "all_bars_pass": all(barred.values()) if barred else None,
            "iou": CROWD_IOU,
        }  # fmt: skip
    return out


def party_view(units: Mapping[str, Mapping[str, Any]],
               frames: Mapping[str, Sequence[Mapping[str, Any]]], goblin_cls: str,
               party: Sequence[int] = PARTY, goblin: int = GOBLIN) -> dict[str, Any]:  # fmt: skip
    """PURE (S5, REPORTED): the alarm's view of a session, frame by frame (the module doc)."""
    lacking = sorted(set(units) - set(frames))
    if lacking:
        raise SystemExit(f"PRED.json lacks {len(lacking)} units frames: {lacking[:5]}")
    order = sorted(units, key=lambda fk: int(units[fk]["t"]))
    rec: dict[str, Counter[str]] = {str(th): Counter() for th in PARTY_THRESHOLDS}
    where: Counter[str] = Counter()
    visits: list[list[str]] = []
    last_t: int | None = None
    for fk in order:
        us, t = units[fk]["units"], int(units[fk]["t"])
        mobs = {int(u["mob"]) for u in us}
        g_on, p_on = goblin in mobs, bool(mobs & set(party))
        gb = [d for d in frames[fk] if d["cls"] == goblin_cls]
        for th in PARTY_THRESHOLDS:
            hit = any(float(d["conf"]) >= th for d in gb)
            c = rec[str(th)]
            c["frames"] += 1
            c["goblin_frames"] += g_on
            c["goblin_frames_boxed"] += g_on and hit
            c["no_party_frames"] += not p_on
            c["no_party_frames_boxed"] += (not p_on) and hit
        for d in gb:
            lie = lies_on(det_box(d), us)
            where["on_goblin" if goblin in lie else "on_other_party" if lie & set(party)
                  else "on_other_unit" if lie else "on_no_unit"] += 1  # fmt: skip
        if p_on:
            if last_t is None or (t - last_t) / 1e9 > VISIT_GAP_S or not visits:
                visits.append([])
            visits[-1].append(fk)
            last_t = t
    delays: list[float | None] = []
    for v in visits:
        g = [fk for fk in v if goblin in {int(u["mob"]) for u in units[fk]["units"]}]
        if not g:
            continue
        t0 = int(units[g[0]]["t"])
        boxed = [fk for fk in v if int(units[fk]["t"]) >= t0
                 and any(d["cls"] == goblin_cls for d in frames[fk])]  # fmt: skip
        delays.append(round((int(units[boxed[0]]["t"]) - t0) / 1e9, 2) if boxed else None)
    known = sorted(d for d in delays if d is not None)

    def rate(n: int, d: int) -> float | None:
        return round(n / d, 4) if d else None

    frame_rows_ = {th: {**dict(c),
                        "frame_recall": rate(c["goblin_frames_boxed"], c["goblin_frames"]),
                        "false_alarm_rate": rate(c["no_party_frames_boxed"], c["no_party_frames"])}
                   for th, c in rec.items()}  # fmt: skip
    return {"thresholds": frame_rows_, "goblin_boxes_lie": dict(where),
            "visits": len(visits), "visits_with_a_goblin": len(delays),
            "first_box_delay_s": delays,
            "first_box_delay_s_p50": known[len(known) // 2] if known else None,
            "visits_boxed_within_2s": sum(1 for d in known if d <= 2.0),
            "visits_never_boxed": sum(1 for d in delays if d is None),
            "visit_gap_s": VISIT_GAP_S}  # fmt: skip


# --- the alarm bar (xmas02-detector.md Amendment S6) ------------------------------------------

ALARM_SOLO = 0.7  # the live --alarm-solo default (dungeon@9.53, live-blocks.md 11.2)
ALARM_CONF = 0.25  # predict_dir's conf: the --garm-confirm 2 branch takes any box it keeps
CONFIRM_GAP_S = 1.5  # the previous frame of a two-in-a-row pair (1-fps recordings)
ALARM_WINDOW_S = 2.5  # a visit is detected by a fire this soon after its first frame (3 frames)
ALARM_SPECIES = (1607, 1251, 1515)  # the Goblin, the knight, Garm Baby
S6_MIN_VISITS = 30  # fewer visits: the detection line is INCONCLUSIVE
S6_DETECT = (9, 10)  # >= 9 / 10 of the visits detected (10 detected >= 9 visits)
S6_MIN_FREE = 50  # fewer alarm-free frames in a set: its false-fire line is INCONCLUSIVE
S6_FALSE = (1, 100)  # <= 1 / 100 of the alarm-free frames fire (100 false <= 1 free)


def session_of(fk: str) -> str:
    """PURE: a frame key's session (``frame_key``: <session>.<frame id>); "" for a bare key."""
    return fk.rsplit(".", 1)[0] if "." in fk else ""


def alarm_fires(order: Sequence[str], units: Mapping[str, Mapping[str, Any]],
                frames: Mapping[str, Sequence[Mapping[str, Any]]], alarm_cls: Iterable[str]
                ) -> dict[str, str | None]:  # fmt: skip
    """PURE (S6): per frame (``order``: by session, then time), how the runner fires there: "solo"
    (an alarm-class box >= ALARM_SOLO), "confirm" (one >= ALARM_CONF here and in the previous frame
    of the SAME session, <= CONFIRM_GAP_S earlier), else None."""
    cls = set(alarm_cls)
    out: dict[str, str | None] = {}
    prev: tuple[str, int] | None = None
    prev_hit = False
    for fk in order:
        t, sess = int(units[fk]["t"]), session_of(fk)
        confs = [float(d["conf"]) for d in frames[fk] if d["cls"] in cls]
        hit = any(c >= ALARM_CONF for c in confs)
        near = prev is not None and prev[0] == sess and (t - prev[1]) / 1e9 <= CONFIRM_GAP_S
        out[fk] = ("solo" if any(c >= ALARM_SOLO for c in confs)
                   else "confirm" if hit and prev_hit and near else None)  # fmt: skip
        prev, prev_hit = (sess, t), hit
    return out


def alarm_view(units: Mapping[str, Mapping[str, Any]],
               frames: Mapping[str, Sequence[Mapping[str, Any]]], alarm_cls: Iterable[str],
               party: Sequence[int] = PARTY, species: Sequence[int] = ALARM_SPECIES,
               goblin: int = GOBLIN) -> dict[str, Any]:  # fmt: skip
    """PURE (S6): one set's visits (detected or not, the delay to the first fire, and from the
    first GOBLIN on screen: reported) and its alarm-free frames (false fires, and any alarm-class
    box at all: reported)."""
    lacking = sorted(set(units) - set(frames))
    if lacking:
        raise SystemExit(f"PRED.json lacks {len(lacking)} units frames: {lacking[:5]}")
    acls = set(alarm_cls)
    order = sorted(units, key=lambda fk: (session_of(fk), int(units[fk]["t"])))
    fire = alarm_fires(order, units, frames, acls)
    visits: list[list[str]] = []
    last_t: int | None = None
    last_s: str | None = None
    free = false = any_box = 0
    false_keys: list[str] = []
    for fk in order:
        mobs = {int(u["mob"]) for u in units[fk]["units"]}
        t, sess = int(units[fk]["t"]), session_of(fk)
        if mobs & set(party):
            if last_t is None or sess != last_s or (t - last_t) / 1e9 > VISIT_GAP_S:
                visits.append([])
            visits[-1].append(fk)
            last_t, last_s = t, sess
        if not mobs & set(species):
            free += 1
            any_box += any(d["cls"] in acls for d in frames[fk])
            if fire[fk]:
                false += 1
                false_keys.append(fk)
    rows = []
    for v in visits:
        t0 = int(units[v[0]]["t"])
        fired = [fk for fk in v if fire[fk]]
        d = round((int(units[fired[0]]["t"]) - t0) / 1e9, 2) if fired else None
        g = [fk for fk in v if goblin in {int(u["mob"]) for u in units[fk]["units"]}]
        dg = None
        if g:
            tg = int(units[g[0]]["t"])
            after = [fk for fk in v if fire[fk] and int(units[fk]["t"]) >= tg]
            before = any(fire[fk] for fk in v if int(units[fk]["t"]) < tg)
            dg = 0.0 if before else (round((int(units[after[0]]["t"]) - tg) / 1e9, 2)
                                     if after else None)  # fmt: skip
        rows.append({"first": v[0], "frames": len(v), "delay_s": d,
                     "detected": d is not None and d <= ALARM_WINDOW_S,
                     "first_fire": fire[fired[0]] if fired else None,
                     "goblin_delay_s": dg})  # fmt: skip
    return {"visits": rows, "n_visits": len(rows),
            "detected": sum(1 for r in rows if r["detected"]),
            "alarm_free_frames": free, "false_fires": false, "false_fire_frames": false_keys,
            "alarm_free_frames_with_a_box": any_box, "frames": len(order)}  # fmt: skip


def alarm_bars(held: Mapping[str, Any], free: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """PURE (S6): the three bar lines and the verdict (the module doc)."""

    def line(judged: bool, ok: bool, **kw: Any) -> dict[str, Any]:
        return {**kw, "judged": judged, "pass": ok if judged else None}

    n, k = int(held["n_visits"]), int(held["detected"])
    a, b = S6_DETECT
    detect = line(n >= S6_MIN_VISITS, b * k >= a * n, visits=n, detected=k,
                  rate=round(k / n, 4) if n else None,
                  bar=f">= {a}/{b} of >= {S6_MIN_VISITS}")  # fmt: skip
    lines = {"detection": detect}
    fp, fq = S6_FALSE
    pool_free = sum(int(f["alarm_free_frames"]) for f in free)
    pool_false = sum(int(f["false_fires"]) for f in free)
    for name, nf, nfalse in (("false_held_out", int(held["alarm_free_frames"]),
                              int(held["false_fires"])),
                             ("false_goblin_free", pool_free, pool_false)):  # fmt: skip
        lines[name] = line(nf >= S6_MIN_FREE, fq * nfalse <= fp * nf, alarm_free_frames=nf,
                           false_fires=nfalse, rate=round(nfalse / nf, 4) if nf else None,
                           bar=f"<= {fp}/{fq} of >= {S6_MIN_FREE}")  # fmt: skip
    if any(v["pass"] is False for v in lines.values()):
        verdict = "FAIL"
    elif any(not v["judged"] for v in lines.values()):
        verdict = "INCONCLUSIVE"
    else:
        verdict = "PASS"
    return {"lines": lines, "verdict": verdict}


def cmd_alarm(a: argparse.Namespace) -> int:
    manifest = json.loads(a.cache_manifest.read_text())
    species_cls = class_map(manifest)
    missing = [m for m in ALARM_SPECIES if m not in species_cls]
    if missing:
        raise SystemExit(f"{a.cache_manifest}: no class for {missing}")
    acls = [species_cls[m] for m in ALARM_SPECIES]

    def one(pair: Sequence[Path]) -> dict[str, Any]:
        units_p, pred_p = Path(pair[0]), Path(pair[1])
        pred = load_pred(pred_p, manifest["names"].values(), a.any_settings)
        units = json.loads(units_p.read_text())
        return {"units": [str(units_p), sha256_file(units_p)],
                "pred": [str(pred_p), sha256_file(pred_p)],
                **alarm_view(units["frames"], pred["frames"], acls)}  # fmt: skip

    held = one(a.held_out)
    free = [one(p) for p in a.free or []]
    out = {"what": "xmas02-detector.md S6: the alarm bar (per visit, per frame)",
           "alarm_classes": acls, "solo": ALARM_SOLO, "conf": ALARM_CONF,
           "confirm_gap_s": CONFIRM_GAP_S, "window_s": ALARM_WINDOW_S,
           "visit_gap_s": VISIT_GAP_S, "held_out": held, "free": free,
           **alarm_bars(held, free)}  # fmt: skip
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(out, indent=1) + "\n")
    print(json.dumps({"lines": out["lines"], "verdict": out["verdict"]}, indent=1))
    return 0


def cmd_units(a: argparse.Namespace) -> int:
    """S5: the crowd truth (module doc); needs the map's label stack (packets + sprites)."""
    import map_labels as ml

    key = json.loads(a.key.read_text())
    want = None if a.all_frames else {frame_key(s, f) for s, f in crop_frames(key)}
    psha = sha256_file(a.params)
    if psha != key.get("params_sha256"):
        raise SystemExit(f"{a.params}: sha256 {psha}, the key's params {key.get('params_sha256')}")
    out_frames: dict[str, Any] = {}
    sources = []
    for src in key["sources"]:
        path = resolve_source(str(src["file"]), a.key, a.labels_dir)
        if sha256_file(path) != src["sha256"]:
            raise SystemExit(f"{path}: not the key's label file {src['sha256']}")
        doc = json.loads(path.read_text())
        spec = ml.MAPS[str(doc["map"])]
        params = ml.load_params(a.params, spec)
        grow = float(spec.fit_px)
        lab = ml.session_labeler(a.session_root / str(doc["session"]), spec)
        sources.append({"file": str(path), "sha256": src["sha256"], "session": doc["session"]})
        for f in doc["frames"]:
            fk = frame_key(str(doc["session"]), int(f["frame_id"]))
            if "kept" not in f or (want is not None and fk not in want):
                continue
            kept = {int(k["gid"]): k for k in f["kept"]}
            why = {int(g): str(w) for g, _m, w in f["excluded"]}
            us = ml.frame_units(lab, params, int(f["t"]), tuple(lab.size), grow)
            for u in us:
                k = kept.get(u["gid"])
                u["label"] = "kept" if k else why.get(u["gid"], "unlisted")
                u["kept_box"] = [float(v) for v in k["box"]] if k else None
            out_frames[fk] = {"t": int(f["t"]), "units": us}
    if want is not None and set(want) - set(out_frames):
        raise SystemExit(f"units: {len(set(want) - set(out_frames))} crop frames not labelled")
    doc_out = {"what": "xmas02-detector.md S5: the crowd truth (packets), per frame",
               "plan": "docs/planning/xmas02-detector.md Amendment S5", "key": str(a.key),
               "key_sha256": sha256_file(a.key), "params_sha256": psha, "sources": sources,
               "all_frames": bool(a.all_frames), "iou": CROWD_IOU,
               "frames": out_frames}  # fmt: skip
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(doc_out) + "\n")
    print(json.dumps({"out": str(a.out), "frames": len(out_frames),
                      "units": sum(len(v["units"]) for v in out_frames.values())}))  # fmt: skip
    return 0


def cmd_party(a: argparse.Namespace) -> int:
    manifest = json.loads(a.cache_manifest.read_text())
    species_cls = class_map(manifest)
    if GOBLIN not in species_cls:
        raise SystemExit(f"{a.cache_manifest}: no class for the Goblin {GOBLIN}")
    pred = load_pred(a.pred, manifest["names"].values(), a.any_settings)
    units = json.loads(a.units.read_text())
    res = party_view(units["frames"], pred["frames"], species_cls[GOBLIN])
    out = {"what": "xmas02-detector.md S5: the alarm's view (REPORTED, deciding nothing)",
           "units": [str(a.units), sha256_file(a.units)],
           "pred": [str(a.pred), sha256_file(a.pred)], **res}  # fmt: skip
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(out, indent=1) + "\n")
    print(json.dumps({k: v for k, v in out.items() if k != "first_box_delay_s"}, indent=1))
    return 0


def load_pred(path: Path, names: Iterable[str], any_settings: bool) -> dict[str, Any]:
    pred: dict[str, Any] = json.loads(path.read_text())
    bad = {k: pred.get(k) for k, v in SETTINGS.items() if pred.get(k) != v}
    if bad and not any_settings:
        raise SystemExit(f"{path}: settings {bad}, not the pre-registered {SETTINGS}")
    known = set(names)
    odd = sorted({str(d["cls"]) for ds in pred["frames"].values() for d in ds} - known)
    if odd:
        raise SystemExit(f"{path}: detection classes {odd} are not the manifest's: another model?")
    return pred


def cmd_score(a: argparse.Namespace) -> int:
    key = json.loads(a.key.read_text())
    manifest = json.loads(a.cache_manifest.read_text())
    species_cls = class_map(manifest)
    pred = load_pred(a.pred, manifest["names"].values(), a.any_settings)
    ans_a, ans_b = blind_score.load_answers(a.a), blind_score.load_answers(a.b)
    crops, why = evaluated(key, ans_a, ans_b)
    in_pack: Counter[str] = Counter()
    for k in key["crops"].values():
        mob = int(k["mob"])
        in_pack[f"{species_cls.get(mob, f'unlisted:{mob}')}:{stratum_of(k)}"] += 1
    res = score(key, crops, pred["frames"], species_cls)
    units = None
    if a.units is not None:  # S5: Q1crowd beside Q1 (the units' key must be this key)
        udoc = json.loads(a.units.read_text())
        if udoc.get("key_sha256") != sha256_file(a.key):
            raise SystemExit(f"{a.units}: built from another key ({udoc.get('key_sha256')})")
        units = {"path": str(a.units), "sha256": sha256_file(a.units)}
        res.update(crowd_score(key, crops, pred["frames"], species_cls, udoc["frames"]))
    q1 = res["Q1"]
    out = {
        "what": "gef10-eval.md Q1 / E1 (AMENDMENT R2-2): position metric on the evaluated crops",
        "key": str(a.key), "key_sha256": sha256_file(a.key), "labels": key.get("labels"),
        "seed": key.get("seed"),
        "answers": {"A": [str(a.a), sha256_file(a.a)], "B": [str(a.b), sha256_file(a.b)]},
        "pred": {"path": str(a.pred), "sha256": sha256_file(a.pred), "weights": pred.get("weights"),
                 "imgsz": pred.get("imgsz"), "conf": pred.get("conf"),
                 "frames": len(pred["frames"])},
        "cache_manifest": {"path": str(a.cache_manifest), "sha256": sha256_file(a.cache_manifest),
                           "cache_id": manifest.get("cache_id"),
                           "classes": {k: manifest["classes"].get(k) for k in ("list", "sha256")}},
        "class_map": {str(m): c for m, c in species_cls.items()},
        "crops_in_pack": len(key["crops"]), "crops_in_pack_per_class_stratum": dict(in_pack),
        "evaluated_crops": len(crops), **why,
        "bar": {"min_evaluated_crops": BAR_MIN_CROPS, "recall": 0.80, "precision": 0.80},
        "q1_species_with_bar": q1["species_with_bar"], "q1_all_bars_pass": q1["all_bars_pass"],
        "q1c_species_with_bar": res["Q1c"]["species_with_bar"],
        "q1c_all_bars_pass": res["Q1c"]["all_bars_pass"],
        **({"units": units} if units is not None else {}),
        **res,
    }  # fmt: skip
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(out, indent=1) + "\n")
    print(json.dumps({"out": str(a.out), "evaluated_crops": len(crops),
                      "Q1": {s: [v["evaluated"], v["recall"], v["precision"], v["pass"]]
                             for s, v in q1["per_species"].items()},
                      "E1": {s: [v["evaluated"], v["recall"], v["precision"], v["pass"]]
                             for s, v in res["E1"]["per_species"].items()},
                      "q1_species_with_bar": q1["species_with_bar"],
                      "q1_all_bars_pass": q1["all_bars_pass"],
                      "Q1c": {s: [v["evaluated"], v["recall"], v["precision"], v["pass"]]
                              for s, v in res["Q1c"]["per_species"].items()},
                      "Q1c_pooled": res["Q1c"]["pooled"],
                      "q1c_species_with_bar": res["Q1c"]["species_with_bar"],
                      "q1c_all_bars_pass": res["Q1c"]["all_bars_pass"],
                      **({"Q1crowd": {s: [v["evaluated"], v["recall"], v["precision"], v["pass"]]
                                      for s, v in res["Q1crowd"]["per_species"].items()}}
                         if "Q1crowd" in res else {})},
                     indent=1))  # fmt: skip
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("refs", help="predict_dir --refs for the frames that carry a crop")
    p.add_argument("key", type=Path)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--latency-200", type=int, default=None, metavar="SEED")
    p.add_argument("--latency-out", type=Path, default=None)
    p.add_argument("--labels-dir", type=Path, default=None)
    p.add_argument("--session-root", type=Path, default=HOST_ROOT)
    p.add_argument("--host-root", type=Path, default=HOST_ROOT)
    p.add_argument("--container-root", type=Path, default=CONTAINER_ROOT)
    p.add_argument("--no-verify", action="store_true", help="skip the 8-byte image check")
    p = sub.add_parser("score", help="Q1 / E1 on the evaluated crops")
    p.add_argument("key", type=Path)
    p.add_argument("a", type=Path, help="labeller A's answers")
    p.add_argument("b", type=Path, help="labeller B's answers")
    p.add_argument("pred", type=Path, help="predict_dir's output on the refs")
    p.add_argument(
        "--cache-manifest",
        type=Path,
        required=True,
        help="the manifest of the cache the model trained on (the class names)",
    )
    p.add_argument("--out", type=Path, required=True)
    p.add_argument(
        "--any-settings",
        action="store_true",
        help="accept imgsz / conf other than 1280 / 0.25 (not the evaluation)",
    )
    p.add_argument("--units", type=Path, default=None,
                   help="S5: the units file of THIS key (eval_q1.py units): + Q1crowd")  # fmt: skip
    p = sub.add_parser("units", help="S5: the crowd truth (packets) per crop frame")
    p.add_argument("key", type=Path)
    p.add_argument("--params", type=Path, required=True, help="the FROZEN params of the labels")
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--all-frames", action="store_true",
                   help="every candidate frame of the label files")  # fmt: skip
    p.add_argument("--labels-dir", type=Path, default=None)
    p.add_argument("--session-root", type=Path, default=HOST_ROOT)
    p = sub.add_parser("party", help="S5: the alarm's view (reported)")
    p.add_argument("units", type=Path)
    p.add_argument("pred", type=Path)
    p.add_argument("--cache-manifest", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--any-settings", action="store_true")
    p = sub.add_parser("alarm", help="S6: the alarm bar (per visit, per frame)")
    p.add_argument("--held-out", type=Path, nargs=2, required=True, metavar=("UNITS", "PRED"))
    p.add_argument("--free", type=Path, nargs=2, action="append", metavar=("UNITS", "PRED"),
                   help="a Goblin-free held-out (pooled)")  # fmt: skip
    p.add_argument("--cache-manifest", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--any-settings", action="store_true")
    a = ap.parse_args(argv)
    run = {"refs": cmd_refs, "score": cmd_score, "units": cmd_units, "party": cmd_party,
           "alarm": cmd_alarm}  # fmt: skip
    return run[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
