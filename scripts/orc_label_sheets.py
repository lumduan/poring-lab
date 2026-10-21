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
1c, offset 1d -- the frozen PARAMS' offset replaces --offset-ms). A frame keeps its labels only
when every visible monster's label is kept (an excluded one -- ``occluded_model``, ``crowd``,
``ui``, ``unfit`` -- excludes the frame: ``fix_<reason>``), on top of the cache's own rules.
``labels_summary.json`` then also counts the monster labels kept / excluded per species and reason.
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
    sess = bfc.make_v2_session(session, v2)
    manifest = json.loads((session / "manifest.json").read_text())
    if not qa_export.is_warp_watch(manifest):
        raise SystemExit(f"{session}: not a warp_watch session")
    refs = qa_export.jpeg_index(session, manifest)[:: a.every]
    outcomes: Counter[str] = Counter()
    excluded: Counter[str] = Counter()
    excluded_detail: Counter[str] = Counter()
    boxes: Counter[int] = Counter()
    class_boxes: Counter[str] = Counter()
    frames_with: Counter[int] = Counter()
    items: dict[int, list[Item]] = defaultdict(list)
    fixer = None
    fix_kept: Counter[str] = Counter()
    fix_excl: dict[str, Counter[str]] = defaultdict(Counter)
    fix_hidden = 0
    if fix_params is not None:
        fixer = olf.FixLabeler(sess.labeler, fix_params)
    for ref in refs:
        outcome, fr, reasons, _mk = bfc.decide(sess, ref.t_mono_ns, v2)
        fixed = None
        if outcome == "ok" and fr is not None and fixer is not None:
            fixed = fixer.frame(ref.t_mono_ns, qa_export.read_jpeg(ref))
            if fixed is None:
                outcome, reasons = "excluded", ["fix_no_world"]
            else:
                fix_hidden += fixed.hidden
                for lab in fixed.kept:
                    fix_kept[str(lab.mob)] += 1
                for _gid, mob, why in fixed.excluded:
                    fix_excl[why][str(mob)] += 1
                if fixed.excluded:
                    outcome = "excluded"
                    reasons = [f"fix_{why}:{mob}" for _g, mob, why in fixed.excluded]
        outcomes[outcome] += 1
        if outcome == "excluded":
            for r in {r.split(":", 1)[0] for r in reasons}:
                excluded[r] += 1
            for r in dict.fromkeys(reasons):
                excluded_detail[r] += 1
        if outcome != "ok" or fr is None:
            continue
        labels = fr.labels if fixed is None else [b for b in fr.labels if b.cls != "monster"]
        _text, written = bfc.v2_yolo(labels, bfc.V2_SIZE, v2.classes.class_of)
        mobs = set()
        for b in written:
            class_boxes[b.cls] += 1
            if b.cls != "monster" or b.job is None:
                continue
            boxes[b.job] += 1
            mobs.add(b.job)
            items[b.job].append(Item(ref, b.job, b.gid, b.box, b.kind))
        for lab in fixed.kept if fixed is not None else []:
            class_boxes["monster"] += 1
            boxes[lab.mob] += 1
            mobs.add(lab.mob)
            items[lab.mob].append(Item(ref, lab.mob, lab.gid, lab.box, "fit"))
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
        summary["labels"] = (
            "v2orc-fix (fitted monster boxes) + v2's frame rules + --classes species"
        )
        summary["fix"] = {
            "params": str(a.fix), "measured_on": fix_params["measured_on"],
            "offset_ms": fix_params["offset_ms"], "anchors_px": fix_params["anchors_px"],
            "monster_labels_kept_by_species": dict(sorted(fix_kept.items())),
            "monster_labels_excluded_by_reason": {k: dict(sorted(v.items()))
                                                  for k, v in sorted(fix_excl.items())},
            "monsters_not_visible": fix_hidden,
            "note": "counted on the frames v2's own rules keep; a frame with any excluded "
                    "monster label is excluded (fix_<reason>), so its kept labels are NOT in "
                    "the crops",
        }  # fmt: skip
    return summary, items, v2, sess


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
    ap.add_argument(
        "--fix",
        type=Path,
        default=None,
        help="labels v2orc-fix: the frozen parameters (orc_labels_fix.py freeze)",
    )
    a = ap.parse_args(argv)
    out = write_outputs(a.session, a)
    print(json.dumps(out, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
