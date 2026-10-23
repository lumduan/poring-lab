#!/usr/bin/env python3
"""CONTACT SHEETS and BLIND PACKS for a warp-and-watch block's per-species labels
(docs/planning/orcsdun01-detector.md section 5: "a contact sheet per species checked by two blind
labeller agents on a sample before training").

    orc_label_sheets.py SESSION_DIR --kb DIR [--every 3] [--seed 0] [--per-sheet 48]
                        [--per-blind 30] [--out-root /dev/shm/poring-lab-tmp/orc-labels]
                        [--warp-visibility JSON] [--npc-sprites DIR --npc-sprite-names JSON]
                        [--npc-checked JSON] [--offset-ms MS]

The labels are EXACTLY the cache's (build_frame_cache.py --labels v2 --classes species: its
``decide`` on every --every-th frame, default the cache's own --every-jpeg): a crop is a monster box
of a frame the cache would write. Excluded frames give no crop. Everything written is client
pixels or derived from them: /dev/shm only, never committed.

Written under ``<out-root>/<session>/``:
- ``labels_summary.json``: frames labelled / excluded (by reason), boxes per species (ids);
- ``sheets/species_<mob>.png`` (+ ``sheets/sheets.json``): per species up to --per-sheet crops
  spread over the session, the label box drawn, the frame id written -- for the PARENT;
- ``blind/``: THE BLIND PACK (what the blind labeller agents get):
  * ``crops/NNN.png``: --per-blind random crops per species (seeded), all species shuffled into
    one numbering, each with its box drawn and NO class name anywhere (file names are numbers);
  * ``reference.png``: the rendered idle sprite of every species in the class list (the 7
    orcsdun01 species + the 5 prt_fild08 ones), each under a LETTER (a seeded order, no name);
  * ``pack.json``: the crop files, the letters and the questions;
  * ``grids/grid_NN.png``: the same crops, 20 to a grid (5 x 4), each under its number;
- ``key/answer_key.json``: THE ANSWER KEY (crop number -> mob id, frame, box; letter -> mob id),
  in a DIFFERENT directory: the blind agents must never be given it.

``--fix PARAMS`` (docs/planning/orcsdun01-detector.md 3b, scripts/orc_labels_fix.py): the monster
boxes are the labels v2orc-fix FITTED boxes instead of v1's (facing 1a, anchor 1b, model occlusion
1c, offset 1d -- the frozen PARAMS' offset replaces --offset-ms). ``--rule fix2`` (3f): labels
v2orc-fix2, the facing of fix 2 and its exclusions ``next_move`` (2b) / ``ambiguous_view`` (2c).
A frame keeps its labels only when every visible monster's label is kept (an excluded one --
``occluded_model``, ``crowd``, ``ui``, ``unfit``, and with fix 2 ``next_move`` /
``ambiguous_view`` -- excludes the frame: ``fix_<reason>``), on top of the cache's own rules.
``labels_summary.json`` then also counts the monster labels kept / excluded per species and reason.
The blind pack and the sheets sample every KEPT fitted label of the frames v2's own rules keep
(``--blind-from kept_labels``, the default: 3b's blind check judges the LABELS), or only the labels
of frames the cache would keep whole (``complete_frames``). ``--workers N`` forks the frames' work.
"""

from __future__ import annotations

import argparse
import json
import random
import string
import sys
from collections import Counter, defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import numpy.typing as npt

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import build_frame_cache as bfc  # noqa: E402
import qa_export  # noqa: E402

OUT_ROOT = Path("/dev/shm/poring-lab-tmp/orc-labels")
BOX_RGB = (0, 255, 0)
TILE_H = 160  # contact sheet tile height
BLIND_MIN_H = 240  # a blind crop is enlarged (nearest) to at least this height, at most x4
GRID_COLS, GRID_ROWS = 5, 4  # the blind grids (the first round's layout)
GRID_TILE = (279, 255)  # w, h of one grid tile, its number bar included
GRID_BAR = 18
QUESTIONS = [
    "Q1: is there a monster inside the green box? (yes / no / unsure)",
    "Q2: the box: good (tight around the monster) / loose (the monster is in it, with much "
    "background) / off (cuts the monster or misses it)",
    "Q3: which species is it? one LETTER from reference.png, or none / unsure",
]


@dataclass(frozen=True)
class Item:
    """One monster label of a frame the cache would write."""

    ref: qa_export.JpegRef
    mob: int
    gid: int | None
    box: tuple[float, float, float, float]
    kind: str


# --- pure parts -------------------------------------------------------------------------------


def crop_box(box: Sequence[float], size: tuple[int, int], margin_frac: float = 0.5,
             min_margin: int = 24) -> tuple[int, int, int, int]:  # fmt: skip
    """The crop window around a label box: the box grown by half its larger side (>= 24 px),
    clipped to the frame."""
    x0, y0, x1, y1 = box
    m = max(min_margin, int(round(margin_frac * max(x1 - x0, y1 - y0))))
    w, h = size
    return (max(0, int(x0) - m), max(0, int(y0) - m), min(w, int(x1) + m + 1),
            min(h, int(y1) + m + 1))  # fmt: skip


def draw_box(img: npt.NDArray[np.uint8], box: Sequence[float], origin: tuple[int, int],
             colour: tuple[int, int, int] = BOX_RGB) -> npt.NDArray[np.uint8]:  # fmt: skip
    """A copy of the RGB crop with the box (frame px; ``origin`` = the crop's top-left) drawn 1 px
    wide just OUTSIDE the box, so the pixels it bounds stay visible."""
    out = img.copy()
    h, w = out.shape[:2]
    x0 = int(np.floor(box[0])) - origin[0] - 1
    y0 = int(np.floor(box[1])) - origin[1] - 1
    x1 = int(np.ceil(box[2])) - origin[0]
    y1 = int(np.ceil(box[3])) - origin[1]
    cx0, cx1 = max(0, x0), min(w - 1, x1)
    cy0, cy1 = max(0, y0), min(h - 1, y1)
    if 0 <= y0 < h:
        out[y0, cx0 : cx1 + 1] = colour
    if 0 <= y1 < h:
        out[y1, cx0 : cx1 + 1] = colour
    if 0 <= x0 < w:
        out[cy0 : cy1 + 1, x0] = colour
    if 0 <= x1 < w:
        out[cy0 : cy1 + 1, x1] = colour
    return out


def enlarge(img: npt.NDArray[np.uint8], min_h: int = BLIND_MIN_H, max_f: int = 4) -> Any:
    """Nearest-neighbour enlargement by an integer factor (no new colours)."""
    f = max(1, min(max_f, -(-min_h // max(1, img.shape[0]))))
    return np.repeat(np.repeat(img, f, axis=0), f, axis=1)


def letters_for(mobs: Sequence[int], seed: int) -> dict[str, int]:
    """Letter -> mob id in a seeded order (the letters say nothing about the list's order)."""
    order = list(mobs)
    random.Random(f"reference:{seed}").shuffle(order)
    return {string.ascii_uppercase[i]: m for i, m in enumerate(order)}


def blind_sample(items: dict[int, list[Item]], n: int, sid: str, seed: int) -> list[Item]:
    """``n`` random labels per species (seeded per species), then ALL shuffled into one order."""
    chosen: list[Item] = []
    for mob in sorted(items):
        pool = sorted(items[mob], key=lambda it: (it.ref.frame_id, it.gid or 0))
        chosen += random.Random(f"{sid}:{seed}:{mob}").sample(pool, min(n, len(pool)))
    random.Random(f"{sid}:{seed}:order").shuffle(chosen)
    return chosen


def spread(items: Sequence[Item], n: int) -> list[Item]:
    """Up to ``n`` labels spread evenly over the session (first and last included)."""
    items = sorted(items, key=lambda it: (it.ref.t_mono_ns, it.gid or 0))
    if len(items) <= n:
        return list(items)
    step = (len(items) - 1) / (n - 1) if n > 1 else 0
    return [items[round(i * step)] for i in range(n)]


def tile_sheet(tiles: Sequence[npt.NDArray[np.uint8]], cols: int = 8, gap: int = 4) -> Any:
    """Tiles (RGB, one height) on a dark grid."""
    if not tiles:
        return None
    w = max(t.shape[1] for t in tiles)
    h = max(t.shape[0] for t in tiles)
    rows = (len(tiles) + cols - 1) // cols
    sheet = np.full((rows * (h + gap), cols * (w + gap), 3), 40, np.uint8)
    for i, t in enumerate(tiles):
        r, c = divmod(i, cols)
        sheet[r * (h + gap) : r * (h + gap) + t.shape[0],
              c * (w + gap) : c * (w + gap) + t.shape[1]] = t  # fmt: skip
    return sheet


def grid_pages(n: int, per: int = GRID_COLS * GRID_ROWS) -> list[range]:
    """Crop indices (0-based) per grid page, in order."""
    return [range(i, min(n, i + per)) for i in range(0, n, per)]


# --- rendering --------------------------------------------------------------------------------


def blind_grid(crops: Sequence[tuple[str, Any]]) -> Any:
    """The blind crops ``(number, RGB)`` on one white grid (5 x 4), each scaled (nearest) to fit
    its tile under a ``#NNN`` bar -- the first round's layout."""
    from PIL import Image, ImageDraw

    tw, th = GRID_TILE
    rows = (len(crops) + GRID_COLS - 1) // GRID_COLS
    canvas = Image.new("RGB", (GRID_COLS * tw, rows * th), (255, 255, 255))
    d = ImageDraw.Draw(canvas)
    for i, (num, rgb) in enumerate(crops):
        r, c = divmod(i, GRID_COLS)
        x, y = c * tw, r * th
        im = Image.fromarray(np.ascontiguousarray(rgb))
        f = min(tw / im.width, (th - GRID_BAR) / im.height)
        im = im.resize((max(1, int(im.width * f)), max(1, int(im.height * f))),
                       Image.Resampling.NEAREST)  # fmt: skip
        canvas.paste(im, (x, y + GRID_BAR))
        d.text((x + 3, y + 3), f"#{num}", fill=(0, 0, 0))
    return np.asarray(canvas)


def to_tile(img: npt.NDArray[np.uint8], height: int, text: str | None = None) -> Any:
    from PIL import Image, ImageDraw

    im = Image.fromarray(img)
    f = height / max(1, im.height)
    im = im.resize((max(1, round(im.width * f)), height), Image.Resampling.NEAREST)
    if text:
        d = ImageDraw.Draw(im)
        d.rectangle((0, 0, 7 * len(text) + 6, 13), fill=(0, 0, 0))
        d.text((3, 1), text, fill=(255, 255, 0))
    return np.asarray(im.convert("RGB"))


def reference_sheet(sheets: dict[int, Any], letters: dict[str, int], scale: int = 3) -> Any:
    """Each species' rendered idle sprite (direction 0, frame 0; ACT tint applied) on mid grey,
    enlarged, under its letter. No name."""
    from PIL import Image, ImageDraw, ImageFont

    from poring_dataset.render import MonsterAction
    from poring_dataset.sprites import compose_frame

    font = ImageFont.load_default(size=28)
    tiles = []
    for letter, mob in letters.items():
        sheet = sheets.get(mob)
        if sheet is None or sheet.spr is None:
            raise SystemExit(f"no decoded sprite for listed species {mob}: the reference is "
                             "incomplete")  # fmt: skip
        rgba, _ = compose_frame(sheet.spr, sheet.act, sheet.act.action_index(MonsterAction.IDLE,
                                                                             0), 0)  # fmt: skip
        a = rgba[..., 3:4].astype(float) / 255.0
        rgb = (rgba[..., :3] * a + 110.0 * (1 - a)).astype(np.uint8)
        rgb = np.repeat(np.repeat(rgb, scale, axis=0), scale, axis=1)
        tiles.append((letter, rgb))
    tw = max(t.shape[1] for _, t in tiles) + 20
    th = max(t.shape[0] for _, t in tiles) + 50
    cols = 4
    rows = (len(tiles) + cols - 1) // cols
    canvas = Image.new("RGB", (cols * tw, rows * th), (110, 110, 110))
    d = ImageDraw.Draw(canvas)
    for i, (letter, rgb) in enumerate(tiles):
        r, c = divmod(i, cols)
        x, y = c * tw, r * th
        d.rectangle((x, y, x + tw - 1, y + th - 1), outline=(60, 60, 60))
        d.text((x + 8, y + 6), letter, fill=(255, 255, 0), font=font)
        canvas.paste(Image.fromarray(rgb), (x + (tw - rgb.shape[1]) // 2, y + 44))
    return np.asarray(canvas)


def save_png(path: Path, rgb: npt.NDArray[np.uint8]) -> None:
    from PIL import Image

    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(np.ascontiguousarray(rgb)).save(path)


# --- the session ------------------------------------------------------------------------------


def collect(session: Path, a: argparse.Namespace) -> tuple[dict[str, Any], dict[int, list[Item]],
                                                            bfc.V2Inputs, Any]:  # fmt: skip
    """Pass 1 (packets only): the cache's decision on every --every-th frame; the monster labels
    of the frames it would write, per species."""
    fix_params = None
    if getattr(a, "fix", None) is not None:
        import orc_labels_fix as olf

        olf.refuse_test_block(session)
        fix_params = olf.load_params(a.fix)
        a.offset_ms = float(fix_params["offset_ms"])  # 1d replaces the benchmark's offset
    ns = argparse.Namespace(
        kb=a.kb, warp_visibility=a.warp_visibility, npc_sprites=a.npc_sprites,
        npc_sprite_names=a.npc_sprite_names, npc_extents=a.npc_extents,
        npc_checked=a.npc_checked, cutin_rect=None, offset_ms=a.offset_ms, allow_hold=[],
        k=a.k, classes="species", class_list=a.class_list,
    )  # fmt: skip
    v2 = bfc.V2Inputs.from_args(ns)
    assert v2.classes is not None
    manifest = json.loads((session / "manifest.json").read_text())
    if not (qa_export.is_warp_watch(manifest) or qa_export.is_human_demo(manifest)):
        raise SystemExit(f"{session}: neither a warp_watch session nor a human demo")
    layout = qa_export.layout_check(manifest, getattr(a, "layout_templates", None))
    if layout is not None and fix_params is None:
        raise SystemExit(f"{session}: a human demo is labelled with --fix only (its frames' UI "
                         "layout is checked on the pixels the fit reads)")  # fmt: skip
    sess = bfc.make_v2_session(session, v2)
    refs = qa_export.frame_refs(session, manifest)[:: a.every]
    outcomes: Counter[str] = Counter()
    excluded: Counter[str] = Counter()
    excluded_detail: Counter[str] = Counter()
    boxes: Counter[int] = Counter()
    class_boxes: Counter[str] = Counter()
    frames_with: Counter[int] = Counter()
    items: dict[int, list[Item]] = defaultdict(list)
    kept_any: dict[int, list[Item]] = defaultdict(list)  # --fix: every kept label, any frame
    fix_kept: Counter[str] = Counter()
    fix_excl: dict[str, Counter[str]] = defaultdict(Counter)
    fix_hidden = 0
    fix_other_map = 0
    _FIX.clear()
    rule = getattr(a, "rule", "1a")
    occlusion = getattr(a, "occlusion", "1c")
    stack, wing = bool(getattr(a, "stack", False)), bool(getattr(a, "wing", False))
    _FIX.update(sess=sess, v2=v2, layout=layout, fixer=None if fix_params is None else
                olf.FixLabeler(sess.labeler, fix_params, rule=rule, occlusion=occlusion,
                               stack=stack, wing=wing))  # fmt: skip
    if fix_params is not None:
        results = olf.run_parallel(_frame_fate, refs, getattr(a, "workers", 1))
    else:
        results = [_frame_fate(ref) for ref in refs]
    for ref, outcome, reasons, written, fixed in results:
        if fixed is not None and not fixed[0]:
            fixed = None  # another map (prt_fild08 before the first warp): v1's labels
            fix_other_map += 1
        if fixed is not None:
            _applies, kept, excl, hidden = fixed
            fix_hidden += hidden
            for mob, gid, box in kept:
                fix_kept[str(mob)] += 1
                kept_any[mob].append(Item(ref, mob, gid, box, "fit"))
            for _gid, mob, why in excl:
                fix_excl[why][str(mob)] += 1
            if excl:
                outcome = "excluded"
                reasons = [f"fix_{why}:{mob}" for _g, mob, why in excl]
        outcomes[outcome] += 1
        if outcome == "excluded":
            for r in {r.split(":", 1)[0] for r in reasons}:
                excluded[r] += 1
            for r in dict.fromkeys(reasons):
                excluded_detail[r] += 1
        if outcome != "ok":
            continue
        mobs = set()
        for cls, job, gid, box, kind in written:
            if fixed is not None and cls == "monster":
                continue  # replaced by the fitted boxes
            class_boxes[cls] += 1
            if cls != "monster" or job is None:
                continue
            boxes[job] += 1
            mobs.add(job)
            items[job].append(Item(ref, job, gid, box, kind))
            if fix_params is not None:
                kept_any[job].append(Item(ref, job, gid, box, kind))  # v1's, off orcsdun01
        for mob, gid, box in fixed[1] if fixed is not None else []:
            class_boxes["monster"] += 1
            boxes[mob] += 1
            mobs.add(mob)
            items[mob].append(Item(ref, mob, gid, box, "fit"))
        for m in mobs:
            frames_with[m] += 1
    summary = {"session": qa_export.session_id(manifest), "every": a.every,
               "frames_considered": len(refs), "outcomes": dict(outcomes),
               "excluded_frames_by_reason": dict(excluded.most_common()),
               "excluded_detail": dict(excluded_detail.most_common()),
               "boxes_by_class": dict(class_boxes.most_common()),
               "monster_boxes_by_species": {str(k): v for k, v in sorted(boxes.items())},
               "frames_with_species": {str(k): v for k, v in sorted(frames_with.items())},
               "labels": "v2 + --classes species", "classes": v2.classes.provenance(),
               "warp_rule": v2.provenance["warp_rule"],
               "offset_ms": sess.labeler.offset_ms}  # fmt: skip
    if fix_params is not None:
        name = olf.labels_name(rule, occlusion, stack, wing)
        summary["labels"] = f"{name} (fitted monster boxes) + v2's frame rules + --classes species"
        summary["fix"] = {
            "facing_rule": rule,
            "params": str(a.fix), "measured_on": fix_params["measured_on"],
            "offset_ms": fix_params["offset_ms"], "anchors_px": fix_params["anchors_px"],
            "monster_labels_kept_by_species": dict(sorted(fix_kept.items())),
            "monster_labels_excluded_by_reason": {k: dict(sorted(v.items()))
                                                  for k, v in sorted(fix_excl.items())},
            "monsters_not_visible": fix_hidden,
            "frames_off_orcsdun01_v1_labels": fix_other_map,
            "note": "counted on the frames v2's own rules keep; a frame with any excluded "
                    "monster label is excluded (fix_<reason>) from the cache",
            "kept_labels_by_species_any_frame": {str(k): len(v)
                                                 for k, v in sorted(kept_any.items())},
            "blind_and_sheets_from": a.blind_from,
        }  # fmt: skip
        if a.blind_from == "kept_labels":
            return summary, kept_any, v2, sess
    return summary, items, v2, sess


_FIX: dict[str, Any] = {}  # the open v2 session (and --fix's labeller), inherited by fork


def _frame_fate(ref: qa_export.JpegRef) -> tuple[Any, ...]:
    """One frame's fate, small and picklable: (ref, outcome, reasons, v2's written labels as
    (cls, job, gid, box, kind), the fix's (applies, kept (mob, gid, box), excluded (gid, mob,
    reason), hidden) or None)."""
    sess, v2, fixer = _FIX["sess"], _FIX["v2"], _FIX["fixer"]
    outcome, fr, reasons, _mk = bfc.decide(sess, ref.t_mono_ns, v2)
    written: list[tuple[str, int | None, int | None, tuple[float, ...], str]] = []
    fixed: Any = None
    if outcome == "ok" and fr is not None:
        _text, out = bfc.v2_yolo(fr.labels, bfc.V2_SIZE, v2.classes.class_of)
        written = [(b.cls, b.job, b.gid, b.box, b.kind) for b in out]
        if fixer is not None:
            bgr = qa_export.read_jpeg(ref)
            layout = _FIX.get("layout")
            if layout is not None and not layout(bgr):  # a human demo in another UI layout (3f)
                return ref, "excluded", ["ui_layout_mismatch"], written, None
            got = fixer.frame(ref.t_mono_ns, bgr)
            if got is None:
                outcome, reasons = "excluded", ["fix_no_world"]
            elif _FIX.get("round4"):  # 3i: every candidate's verdict comes from the fates
                fixed = (got.applies, got.hidden, list(got.fates))
            else:
                fixed = (got.applies, [(k.mob, k.gid, k.box) for k in got.kept],
                         list(got.excluded), got.hidden)  # fmt: skip
    return ref, outcome, reasons, written, fixed


def write_outputs(session: Path, a: argparse.Namespace) -> dict[str, Any]:
    summary, items, v2, sess = collect(session, a)
    assert v2.classes is not None
    sid = summary["session"]
    base = a.out_root / sid
    sheets_dir, blind_dir, key_dir = base / "sheets", base / "blind", base / "key"
    for d in (sheets_dir, blind_dir / "crops", key_dir):
        d.mkdir(parents=True, exist_ok=True)
    (base / "labels_summary.json").write_text(json.dumps(summary, indent=1) + "\n")
    size = tuple(sess.labeler.size)
    sheet_pick = {mob: spread(its, a.per_sheet) for mob, its in items.items()}
    blind = blind_sample(items, a.per_blind, sid, a.seed)
    need = {it.ref for its in sheet_pick.values() for it in its} | {it.ref for it in blind}
    frames: dict[qa_export.JpegRef, npt.NDArray[np.uint8]] = {}
    for ref in sorted(need, key=lambda r: (str(r.shard), r.offset)):
        frames[ref] = qa_export.read_jpeg(ref)[:, :, ::-1]  # RGB

    def crop(it: Item) -> Any:
        x0, y0, x1, y1 = crop_box(it.box, size)
        return draw_box(frames[it.ref][y0:y1, x0:x1], it.box, (x0, y0))

    sheet_rows = {}
    for mob, its in sorted(sheet_pick.items()):
        tiles = [to_tile(crop(it), TILE_H, str(it.ref.frame_id)) for it in its]
        sheet = tile_sheet(tiles)
        if sheet is not None:
            save_png(sheets_dir / f"species_{mob}.png", sheet)
        sheet_rows[str(mob)] = {"labels": len(items[mob]), "shown": len(its),
                                "sheet": str(sheets_dir / f"species_{mob}.png"),
                                "items": [{"frame_id": it.ref.frame_id, "gid": it.gid,
                                           "box": [round(v, 1) for v in it.box]}
                                          for it in its]}  # fmt: skip
    (sheets_dir / "sheets.json").write_text(json.dumps(sheet_rows, indent=1) + "\n")
    key_crops = {}
    names = []
    enlarged = []
    for i, it in enumerate(blind, 1):
        name = f"{i:03d}.png"
        big = enlarge(crop(it))
        save_png(blind_dir / "crops" / name, big)
        enlarged.append((f"{i:03d}", big))
        names.append(name)
        key_crops[f"{i:03d}"] = {"mob": it.mob, "frame_id": it.ref.frame_id,
                                 "t_ns": it.ref.t_mono_ns, "gid": it.gid, "kind": it.kind,
                                 "box": [round(v, 1) for v in it.box]}  # fmt: skip
    letters = letters_for(v2.classes.monsters, a.seed)
    save_png(
        blind_dir / "reference.png",
        reference_sheet({m: sess.labeler.sheets(m) for m in v2.classes.monsters}, letters),
    )
    grids = []
    for page, idx in enumerate(grid_pages(len(enlarged)), 1):
        gname = f"grids/grid_{page:02d}.png"
        save_png(blind_dir / gname, blind_grid([enlarged[i] for i in idx]))
        grids.append(gname)
    (blind_dir / "pack.json").write_text(json.dumps({
        "crops": names, "grids": grids, "reference": "reference.png", "letters": sorted(letters),
        "box": "the green rectangle drawn just outside the label box",
        "questions": QUESTIONS,
    }, indent=1) + "\n")  # fmt: skip
    key = {"session": sid, "seed": a.seed, "per_blind": a.per_blind,
           "labels": summary.get("labels"), "letters": letters, "crops": key_crops,
           "per_species": dict(Counter(str(v["mob"]) for v in key_crops.values())),
           "note": "THE ANSWER KEY: never give it (or this directory) to a blind labeller",
           }  # fmt: skip
    (key_dir / "answer_key.json").write_text(json.dumps(key, indent=1) + "\n")
    return {"out": str(base), "sheets": str(sheets_dir), "blind_pack": str(blind_dir),
            "answer_key": str(key_dir / "answer_key.json"), "blind_crops": len(names),
            "blind_per_species": key["per_species"], "summary": summary}  # fmt: skip


# --- 3i: blind round 4, every candidate judged on its own 30 from ONE seeded order --------------

ROUND4_PER_SPECIES = 30


def round4_samples(pool: Sequence[Item], keeps: dict[str, set[tuple[int, int | None]]],
                   n: int, sid: str, seed: int, mob: int) -> dict[str, list[Item]]:  # fmt: skip
    """PURE (3i): the pool (o3's kept labels of one species) sorted by (frame, gid) and shuffled
    by ``random.Random(f"{sid}:{seed}:{mob}")``; candidate X's sample = the FIRST ``n`` labels
    in that order that X keeps (``keeps[X]``: (frame_id, gid)), all of them when fewer."""
    order = sorted(pool, key=lambda it: (it.ref.frame_id, it.gid or 0))
    random.Random(f"{sid}:{seed}:{mob}").shuffle(order)
    return {c: [it for it in order if (it.ref.frame_id, it.gid) in kp][:n]
            for c, kp in keeps.items()}  # fmt: skip


def round4(session: Path, a: argparse.Namespace) -> dict[str, Any]:
    """3i's blind round 4 on col1: ONE pass (fix 2 + W, every label fitted), every candidate's
    verdict per frame (orc_labels_fix.decide), the per-candidate counts, the samples, the pack
    (``--pack-dir``: crops, grids, reference, pack.json, the instructions file copied verbatim)
    and the key (``--key-dir``), apart. The summary goes to ``--out-root`` (never the pack)."""
    import hashlib
    import shutil

    import orc_labels_fix as olf

    if a.fix is None or a.rule != "fix2":
        raise SystemExit("--round4 is 3i's: --fix PARAMS --rule fix2")
    olf.refuse_test_block(session)
    instr_sha = None
    if not getattr(a, "counts_only", False):
        instr_sha = hashlib.sha256(a.instructions.read_bytes()).hexdigest()
        if a.instructions_sha256 and instr_sha != a.instructions_sha256:
            raise SystemExit(f"{a.instructions}: sha256 {instr_sha}, not round 2's")
    fix_params = olf.load_params(a.fix)
    a.offset_ms = float(fix_params["offset_ms"])
    ns = argparse.Namespace(
        kb=a.kb, warp_visibility=a.warp_visibility, npc_sprites=a.npc_sprites,
        npc_sprite_names=a.npc_sprite_names, npc_extents=a.npc_extents,
        npc_checked=a.npc_checked, cutin_rect=None, offset_ms=a.offset_ms, allow_hold=[],
        k=a.k, classes="species", class_list=a.class_list,
    )  # fmt: skip
    v2 = bfc.V2Inputs.from_args(ns)
    assert v2.classes is not None
    manifest = json.loads((session / "manifest.json").read_text())
    if not qa_export.is_warp_watch(manifest):
        raise SystemExit(f"{session}: --round4 reads a warp_watch block (col1)")
    sess = bfc.make_v2_session(session, v2)
    sid = qa_export.session_id(manifest)
    refs = qa_export.frame_refs(session, manifest)[:: a.every]
    _FIX.clear()
    _FIX.update(sess=sess, v2=v2, layout=None, round4=True,
                fixer=olf.FixLabeler(sess.labeler, fix_params, rule="fix2", wing=True,
                                     fit_all=True))  # fmt: skip
    results = olf.run_parallel(_frame_fate, refs, getattr(a, "workers", 1))
    cands = olf.CANDIDATES
    outcomes: Counter[str] = Counter()
    kept_any = {c: Counter[int]() for c in cands}
    in_whole = {c: Counter[int]() for c in cands}
    frames_whole = Counter[str]()
    excl: dict[str, dict[str, Counter[int]]] = {
        c: defaultdict(Counter) for c in cands
    }  # reason -> mob -> n
    keeps: dict[int, dict[str, set[tuple[int, int | None]]]] = defaultdict(
        lambda: {c: set() for c in cands}
    )
    pool: dict[int, list[Item]] = defaultdict(list)
    controls: list[Item] = []
    orc_frames = other_map = hidden = 0
    for ref, outcome, _reasons, written, fixed in results:
        outcomes[outcome] += 1
        if outcome != "ok" or fixed is None:
            continue
        applies, hid, fates = fixed
        if not applies:  # prt_fild08 before the first warp: v2's (v1's) labels, the controls
            other_map += 1
            for cls, job, gid, box, kind in written:
                if cls == "monster" and job is not None:
                    controls.append(Item(ref, job, gid, box, kind))
            continue
        orc_frames += 1
        hidden += hid
        by_gid = {f.gid: f for f in fates}
        for c in cands:
            occlusion, stack = olf.parse_candidate(c)
            kept, ex = olf.decide(fates, occlusion, stack)
            for f in kept:
                kept_any[c][f.mob] += 1
                keeps[f.mob][c].add((ref.frame_id, f.gid))
            for _g, mob, why in ex:
                excl[c][why][mob] += 1
            if not ex:
                frames_whole[c] += 1
                for f in kept:
                    in_whole[c][f.mob] += 1
        for f in olf.decide(fates, "o3", False)[0]:  # the pool: o3's kept labels
            box = f.wbox if f.wbox is not None else f.box
            assert box is not None
            pool[f.mob].append(Item(ref, f.mob, f.gid, box, "fit_w" if f.wbox else "fit"))
            assert by_gid[f.gid] is f
    for mob, per in keeps.items():  # every candidate's kept set is inside o3's (3i)
        for c, kp in per.items():
            if not kp <= per["o3"]:
                raise SystemExit(f"{c} keeps a {mob} label o3 does not: the pool is wrong")
    mobs = sorted({m for c in cands for m in kept_any[c]})
    table: dict[str, dict[str, Any]] = {
        c: {"labels_kept_any_frame": {str(m): kept_any[c][m] for m in mobs},
                 "labels_in_whole_frames": {str(m): in_whole[c][m] for m in mobs},
                 "labels_in_whole_frames_total": sum(in_whole[c].values()),
                 "labels_kept_total": sum(kept_any[c].values()),
                 "frames_whole": frames_whole[c],
                 "excluded_by_reason": {w: {str(m): n for m, n in sorted(v.items())}
                                        for w, v in sorted(excl[c].items())}}
        for c in cands}  # fmt: skip
    rank = sorted(cands, key=lambda c: (-table[c]["labels_in_whole_frames_total"],
                                        -table[c]["frames_whole"], cands.index(c)))  # fmt: skip
    if getattr(a, "counts_only", False):  # col3 / the cache's expectation: no pack, no key
        out = {"what": "3i: every candidate's counts (no pack)", "session": sid,
               "made_at": olf.now_ict(), "commit": olf.git_head(), "every": a.every,
               "params_sha256": olf.sha256_file(a.fix), "frames_considered": len(refs),
               "outcomes": dict(outcomes), "orcsdun01_frames_v2_keeps": orc_frames,
               "frames_off_orcsdun01": other_map, "controls": len(controls),
               "control_boxes_by_species": dict(Counter(str(i.mob) for i in controls)),
               "candidates": table, "preference_order_by_3i": rank}  # fmt: skip
        a.out_root.mkdir(parents=True, exist_ok=True)
        (a.out_root / f"counts_{sid}.json").write_text(json.dumps(out, indent=1) + "\n")
        return out
    samples: dict[int, dict[str, list[Item]]] = {
        mob: round4_samples(pool[mob], keeps[mob], a.per_blind, sid, a.seed, mob)
        for mob in sorted(pool)
    }
    chosen: dict[tuple[int, int | None], tuple[Item, set[str]]] = {}
    for per_c in samples.values():
        for cand, members in per_c.items():
            for item in members:
                ck = (item.ref.frame_id, item.gid)
                chosen.setdefault(ck, (item, set()))[1].add(cand)
    crops = [(item, sorted(cs, key=cands.index), False) for item, cs in chosen.values()]
    crops += [(item, list(cands), True) for item in controls]
    random.Random(f"{sid}:{a.seed}:order").shuffle(crops)
    pack, keydir = a.pack_dir, a.key_dir
    if pack.resolve() == keydir.resolve() or keydir.resolve().is_relative_to(pack.resolve()):
        raise SystemExit("the key must live OUTSIDE the pack directory")
    for d in (pack / "crops", pack / "grids", keydir):
        d.mkdir(parents=True, exist_ok=True)
    size = tuple(sess.labeler.size)
    frames: dict[qa_export.JpegRef, npt.NDArray[np.uint8]] = {}
    for ref in sorted({c[0].ref for c in crops}, key=lambda r: (str(r.shard), r.offset)):
        frames[ref] = qa_export.read_jpeg(ref)[:, :, ::-1]
    names: list[str] = []
    enlarged: list[tuple[str, Any]] = []
    key_crops: dict[str, dict[str, Any]] = {}
    for i, (it, cs, control) in enumerate(crops, 1):
        x0, y0, x1, y1 = crop_box(it.box, size)
        big = enlarge(draw_box(frames[it.ref][y0:y1, x0:x1], it.box, (x0, y0)))
        name = f"{i:03d}.png"
        save_png(pack / "crops" / name, big)
        names.append(name)
        enlarged.append((f"{i:03d}", big))
        key_crops[f"{i:03d}"] = {"mob": it.mob, "frame_id": it.ref.frame_id,
                                 "t_ns": it.ref.t_mono_ns, "gid": it.gid, "kind": it.kind,
                                 "box": [round(v, 1) for v in it.box], "samples": cs,
                                 "control": control}  # fmt: skip
    letters = letters_for(v2.classes.monsters, a.seed)
    save_png(
        pack / "reference.png",
        reference_sheet({m: sess.labeler.sheets(m) for m in v2.classes.monsters}, letters),
    )
    grids = []
    for page, idx in enumerate(grid_pages(len(enlarged)), 1):
        gname = f"grids/grid_{page:02d}.png"
        save_png(pack / gname, blind_grid([enlarged[i] for i in idx]))
        grids.append(gname)
    (pack / "pack.json").write_text(json.dumps({
        "crops": names, "grids": grids, "reference": "reference.png", "letters": sorted(letters),
        "box": "the green rectangle drawn just outside the label box",
        "questions": QUESTIONS,
    }, indent=1) + "\n")  # fmt: skip
    shutil.copyfile(a.instructions, pack / "instructions.txt")
    per_sample: dict[str, dict[str, int]] = {
        c: {str(m): len(samples[m][c]) for m in sorted(samples)} for c in cands
    }
    key: dict[str, Any] = {"session": sid, "seed": a.seed, "per_blind": a.per_blind, "round": 4,
           "plan": "docs/planning/orcsdun01-detector.md 3i",
           "labels": "v2orc-fix2+W, six occlusion candidates (3i)", "letters": letters,
           "crops": key_crops, "candidates": list(cands), "per_sample": per_sample,
           "per_species": dict(Counter(str(v["mob"]) for v in key_crops.values())),
           "note": "THE ANSWER KEY: never give it (or this directory) to a blind labeller; "
                   "score each candidate with blind_score.py --sample NAME"}  # fmt: skip
    (keydir / "answer_key.json").write_text(json.dumps(key, indent=1) + "\n")
    summary = {
        "what": "3i: blind round 4's pack and every candidate's counts on col1 (every "
                f"{a.every}rd frame, v2's frame rules, fix 2 + W)",
        "session": sid, "seed": a.seed, "made_at": olf.now_ict(), "commit": olf.git_head(),
        "params": str(a.fix), "params_sha256": olf.sha256_file(a.fix),
        "instructions": str(a.instructions), "instructions_sha256": instr_sha,
        "frames_considered": len(refs), "outcomes": dict(outcomes),
        "orcsdun01_frames_v2_keeps": orc_frames, "frames_off_orcsdun01": other_map,
        "monsters_not_visible": hidden, "candidates": table,
        "preference_order_by_3i": rank,
        "most_keeping": rank[0],
        "pool_o3_by_species": {str(m): len(v) for m, v in sorted(pool.items())},
        "sample_sizes": per_sample,
        "crops_total": len(names), "crops_per_species": key["per_species"],
        "controls": len(controls),
        "pack": str(pack), "key": str(keydir / "answer_key.json"),
    }  # fmt: skip
    a.out_root.mkdir(parents=True, exist_ok=True)
    (a.out_root / "round4_summary.json").write_text(json.dumps(summary, indent=1) + "\n")
    return summary


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("session", type=Path)
    ap.add_argument("--kb", type=Path, default=ROOT / "data" / "kb")
    ap.add_argument("--every", type=int, default=bfc.EVERY_JPEG)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--per-sheet", type=int, default=48)
    ap.add_argument("--per-blind", type=int, default=30)
    ap.add_argument("--out-root", type=Path, default=OUT_ROOT)
    ap.add_argument("--class-list", type=Path, default=bfc.SPECIES_LIST)
    ap.add_argument("--k", type=float, default=0.14, help="the sprite scale (v1's 0.14)")
    ap.add_argument("--offset-ms", type=float, default=None)
    ap.add_argument("--warp-visibility", type=Path, default=None)
    ap.add_argument("--npc-sprites", type=Path, default=None)
    ap.add_argument("--npc-sprite-names", type=Path, default=None)
    ap.add_argument("--npc-extents", type=Path, default=None)
    ap.add_argument("--npc-checked", type=Path, default=None)
    ap.add_argument("--workers", type=int, default=1, help="--fix: forked worker processes")
    ap.add_argument(
        "--layout-templates",
        type=Path,
        default=None,
        help="a human demo: client_layout's templates (default its TEMPLATES)",
    )
    ap.add_argument(
        "--blind-from", choices=("kept_labels", "complete_frames"), default="kept_labels",
        help="--fix: the blind pack and the sheets sample every KEPT fitted label (default), or "
        "only the labels of frames the cache would keep whole",
    )  # fmt: skip
    ap.add_argument(
        "--fix",
        type=Path,
        default=None,
        help="labels v2orc-fix: the frozen parameters (orc_labels_fix.py freeze)",
    )
    ap.add_argument(
        "--rule",
        choices=("1a", "fix2"),
        default="1a",
        help="--fix: the facing, 1a (3b, as round 2) or fix2 (3f: labels v2orc-fix2, with the "
        "exclusions 2b next_move / 2c ambiguous_view)",
    )
    ap.add_argument(
        "--occlusion",
        choices=("1c", "o3h", "o3"),
        default="1c",
        help="--fix: 3i's occlusion candidate (1c: 3b's literal rule)",
    )
    ap.add_argument("--stack", action="store_true", help="--fix: 3i's S3 (IoU >= 0.30)")
    ap.add_argument(
        "--wing", action="store_true", help="--fix: 3i's W box for the Familiar / Drainliar"
    )
    ap.add_argument(
        "--round4",
        action="store_true",
        help="3i's blind round 4: every candidate at once (needs --fix --rule fix2 "
        "--pack-dir --key-dir --instructions); the summary goes to --out-root",
    )
    ap.add_argument("--pack-dir", type=Path, default=None)
    ap.add_argument("--key-dir", type=Path, default=None)
    ap.add_argument(
        "--instructions",
        type=Path,
        default=None,
        help="--round4: round 2's labeller instructions, copied verbatim",
    )
    ap.add_argument(
        "--instructions-sha256",
        default=None,
        help="--round4: refuse unless the instructions have exactly this sha256",
    )
    ap.add_argument(
        "--counts-only",
        action="store_true",
        help="--round4: every candidate's counts only (no pack, no key): col3 / the cache",
    )
    a = ap.parse_args(argv)
    if a.round4:
        if not a.counts_only and (a.pack_dir is None or a.key_dir is None
                                  or a.instructions is None):  # fmt: skip
            raise SystemExit("--round4 needs --pack-dir, --key-dir and --instructions")
        print(json.dumps(round4(a.session, a), indent=1))
        return 0
    out = write_outputs(a.session, a)
    print(json.dumps(out, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
