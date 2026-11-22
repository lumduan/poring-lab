#!/usr/bin/env python3
"""The fi7 rule (docs/planning/xmas02-items-1080.md Amendment 22, round 7, pre-registered
2026-11-21 16:11 ICT before any round-7 data): the 1080 item model's boxes, before any use, lose

- A. every ``floor_item`` box under the confidence floor FI7_FLOOR (0.50);
- B. every ``floor_item`` box on the client's no-entry CURSOR RING: the box plus FI7_PAD (6) px
  holds >= FI7_RING_RED (30) PURE-RED pixels (R >= 150, G <= 30, B <= 30) in the virtual frame.

Read on the spent round-6 held-out (Amendment 22, diagnosis only): the 8 ring boxes held 81-115
pure-red px each; all 53 found drops and all 37 other false boxes held 0. The pointer is NOT the
signal (2 of 53 drops lay within 20 px of it).

Every other class's box is untouched. PURE functions (ring_red_px, fi7_drop, apply_rule) and one
loader (load_frame: a recorded frame from a refs.json entry, fi_labels.py refs' format).

➡️ Round 10 (Amendment 36, pre-registered 2026-11-22 21:49 ICT before any round-10 data) adds

- C. the VIEW EDGE: every ``floor_item`` box whose CENTRE lies within FI10_EDGE (12) px of the
  1280 x 720 view's left, right or bottom edge, or within FI10_TOP (32) px of its top
  (``edge_drop`` / ``apply_edge``; a separate pass after A and B, so rounds 7-9 read as before).

Read on the spent rounds 8 and 9 (Amendment 35, diagnosis only): it dropped 3 and 17 false boxes
(a wall ornament at the top edge held 8 frames; an object cut by the right edge 8) and no true item.
"""

from __future__ import annotations

import io
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

import numpy as np

FI7_FLOOR = 0.50
FI7_RING_RED = 30
FI7_PAD = 6
RED_MIN_R = 150  # pure red: R >= 150 ...
RED_MAX_GB = 30  # ... and G, B <= 30
ITEM_CLASS = "floor_item"  # fi_eval.CLASS, dungeon_hunt.LOOT_ITEMS_CLASS
CONTAINER_ROOT = "/datasets"  # fi_labels.py refs --container-root's default
FI10_EDGE = 12  # C: px from the view's left, right and bottom edges (Amendment 36)
FI10_TOP = 32  # C: px from the view's top
VIEW_W, VIEW_H = 1280, 720  # the virtual 1080 view the boxes are in (rec_paths.VIRTUAL_1080)


def ring_red_px(img: Any, box: Sequence[float], pad: int = FI7_PAD) -> int:
    """PURE: the pure-red pixels in ``box`` (x1, y1, x2, y2; virtual px) plus ``pad`` px, the
    window clipped to the image; ``img`` an (H, W, 3) RGB array. The corners are rounded as the
    Amendment 22 reading rounded them (Python's round), the window's far edges exclusive."""
    a = np.asarray(img)
    h, w = a.shape[:2]
    x0, y0, x1, y1 = (int(round(float(v))) for v in box[:4])
    r0, r1 = max(0, y0 - pad), max(0, min(h, y1 + pad))  # never a negative end: no wrap-around
    c0, c1 = max(0, x0 - pad), max(0, min(w, x1 + pad))
    win = a[r0:r1, c0:c1, :3]
    if win.size == 0:
        return 0
    r, g, b = win[..., 0], win[..., 1], win[..., 2]
    return int(((r >= RED_MIN_R) & (g <= RED_MAX_GB) & (b <= RED_MAX_GB)).sum())


def det_box(det: Mapping[str, Any]) -> list[float]:
    return [float(det["x1"]), float(det["y1"]), float(det["x2"]), float(det["y2"])]


def fi7_drop(det: Mapping[str, Any], img: Any | None, floor: float | None = FI7_FLOOR,
             ring_red: int | None = FI7_RING_RED, pad: int = FI7_PAD) -> str | None:  # fmt: skip
    """PURE: why the rule drops this predict_dir detection ("floor" / "ring"), else None. Only a
    ``floor_item`` box is judged; ``floor`` / ``ring_red`` None leave that half out. The ring
    half needs the frame (``img``): a missing one is refused, never "not a ring"."""
    if det.get("cls") != ITEM_CLASS:
        return None
    if floor is not None and float(det.get("conf", 0.0)) < floor:
        return "floor"
    if ring_red is not None:
        if img is None:
            raise ValueError("the ring test needs the frame's pixels")
        if ring_red_px(img, det_box(det), pad) >= ring_red:
            return "ring"
    return None


def apply_rule(
    pred_doc: Mapping[str, Any],
    refs: Mapping[str, Any],
    load: Callable[[Mapping[str, Any], str], Any],
    floor: float | None = FI7_FLOOR,
    ring_red: int | None = FI7_RING_RED,
    pad: int = FI7_PAD,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """PURE but for ``load(refs, key)`` (a frame's RGB array): predict_dir's document with the
    rule applied to every frame -- the same shape (``frames``: key -> detections, every other
    field kept); a frame is loaded only when one of its ``floor_item`` boxes passed the floor
    (the ring test needs its pixels). Returns (the filtered document, the summary)."""
    dropped = {"floor": 0, "ring": 0}
    kept_items = loaded = 0
    out: dict[str, list[Any]] = {}
    for key, dets in pred_doc["frames"].items():
        img: Any | None = None
        keep: list[Any] = []
        for d in dets:
            if d.get("cls") == ITEM_CLASS and ring_red is not None and img is None and (
                    floor is None or float(d.get("conf", 0.0)) >= floor):  # fmt: skip
                img = load(refs, key)
                loaded += 1
            why = fi7_drop(d, img, floor, ring_red, pad)
            if why is None:
                keep.append(d)
                kept_items += d.get("cls") == ITEM_CLASS
            else:
                dropped[why] += 1
        out[key] = keep
    summary = {"floor": floor, "ring_red": ring_red, "pad": pad, "dropped": dropped,
               "kept_items": kept_items, "frames_loaded": loaded}  # fmt: skip
    return {**pred_doc, "frames": out}, summary


def edge_drop(det: Mapping[str, Any], edge: int = FI10_EDGE, top: int = FI10_TOP,
              w: int = VIEW_W, h: int = VIEW_H) -> bool:  # fmt: skip
    """PURE (C, Amendment 36): True when this predict_dir detection is a ``floor_item`` box whose
    centre lies within ``edge`` px of the view's left, right or bottom edge or within ``top`` px
    of its top (strictly inside the band; a centre exactly on its inner line stays)."""
    if det.get("cls") != ITEM_CLASS:
        return False
    x1, y1, x2, y2 = det_box(det)
    cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
    return cx < edge or cx > w - edge or cy > h - edge or cy < top


def apply_edge(pred_doc: Mapping[str, Any], edge: int = FI10_EDGE, top: int = FI10_TOP,
               w: int = VIEW_W, h: int = VIEW_H) -> tuple[dict[str, Any], int]:  # fmt: skip
    """PURE (C): the document with ``edge_drop``'s boxes removed (the same shape), and how many."""
    out: dict[str, list[Any]] = {}
    n = 0
    for key, dets in pred_doc["frames"].items():
        keep = [d for d in dets if not edge_drop(d, edge, top, w, h)]
        n += len(dets) - len(keep)
        out[key] = keep
    return {**pred_doc, "frames": out}, n


def host_path(path: str, store: Path | None = None, container_root: str = CONTAINER_ROOT) -> Path:
    """A refs.json path (``/datasets/<session>/shard-....tar``, the vision container's) on this
    host: under the storage folder (LAB_STORE_DIR, scripts/lab_env.py; the lab: its NAS)."""
    if store is None:
        import lab_env

        store = lab_env.store_dir()
    root = container_root.rstrip("/") + "/"
    if not path.startswith(root):
        raise ValueError(f"{path}: not under {root}")
    return Path(store) / path[len(root) :]


def load_frame(refs: Mapping[str, Any], key: str, store: Path | None = None) -> Any:
    """A recorded frame as an (H, W, 3) RGB array: refs.json's tar member (path, offset, size).
    A key with no ref is refused (fail closed: the ring test never guesses)."""
    from PIL import Image

    ref = refs.get(key)
    if ref is None:
        raise SystemExit(f"--refs: no frame {key} (the ring test needs every judged frame)")
    with open(host_path(str(ref["path"]), store), "rb") as fh:
        fh.seek(int(ref["offset"]))
        data = fh.read(int(ref["size"]))
    return np.asarray(Image.open(io.BytesIO(data)).convert("RGB"))
