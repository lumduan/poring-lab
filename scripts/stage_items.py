#!/usr/bin/env python3
"""Stage Batt's TARGET items on a hunting map's floor, so they can be learnt from pixels (Batt
2026-10-24 ~16:0x, his reply to the 14:10 report: "try training the target drops -- Rough Elunium,
Rough Oridecon, Dead Branch -- for pickup accuracy").

They almost never drop: 0.07-0.75 per 100 kills (thief-payon.md 4c), and 4.03's 69 kills gave one.
So the Thief gives itself one of each (@item) and drops them by the inventory's KNOWN path
(gm_state.clear_loot with this tool's own icon set: only these items are loot). Spots are spread
over the hunt's own search area. At each spot the camera sees the items from OFFSETS (same-map @warp
steps: typed lines only, NO world click), STILL_S on each.

The 1-fps recorder (record_session, started beside this tool) banks the frames and the packets:
the floor items' exact cells and their drop and vanish times are the OFFLINE labels
(item_labels.py; docs/planning/item-class.md). Nothing here reads a packet (rule 1). Immunity is
ON for the whole session (`immune-on`, then a person's look at its frame). A relog clears it
afterwards (@monsterignore does not survive one).

    stage_items.py spots --map pay_fild07 --n 12 --seed S     OFFLINE: the spots (printed)
    stage_items.py cut SPEC                                    OFFLINE: the icon set (ICON_DIR)
    stage_items.py give                                        LIVE: @item each target once
    stage_items.py immune-on                                   LIVE: @monsterignore + a frame
    stage_items.py run --map pay_fild07 --n 12 --seed S --immune-confirmed     LIVE

stage@5 (gef10-eyes-loot.md E3): the item set is PER MAP (MAP_SETS; pay_fild07's is the default
and unchanged). gef_fild10 stages its DROP SET, a balanced group of ``per_spot`` items per spot
(a floor item lives 60 s: eleven drops at one spot would expire before the views), on open ground
only (``canopy`` builds the RSW's tall-model mask), and ends with two @killmonster2 LOOT_LIFE_S
apart (a looter's loot drops even on a no-drop death, then expires):

    stage_items.py canopy --map gef_fild10 --out /dev/shm/.../gef_fild10-canopy.npy   OFFLINE
    stage_items.py spots --map gef_fild10 --n 22 --seed S --open CANOPY --plan          OFFLINE
    stage_items.py give --map gef_fild10 --frames      LIVE: @item each once + an inventory frame
                                                       per tab (for the cut)
    stage_items.py cut SPEC --map gef_fild10           OFFLINE: the map's icon set
    stage_items.py drop --map gef_fild10               LIVE: drop the given set (the icon proof)
    stage_items.py held --map gef_fild10               the DB's last save: none of the set held
    stage_items.py run --map gef_fild10 --n 22 --seed S --open CANOPY --immune-confirmed   LIVE

stage@6 (rogue-gef10.md AK-5): the set's references become MASKED ones, built from the client's
own item icons (the GRF's item BMPs, extracted to /dev/shm) and compared on the item's pixels
only (gm_state.ICON_MATCH_MASKED), so the slot background and the new-item glow stop counting:

    stage_items.py cut-grf --map gef_fild10 --table IDNUM2ITEMRESNAMETABLE --icons ITEM_BMP_DIR
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

ROOT = Path(__file__).resolve().parents[1]
DEMO = Path("/dev/shm/poring-lab-demo")
VERSION = "stage@6"  # @2: --open (target-items.md 9b); @3: refuses while targets are held;
# @4: the character is a ROGUE (job "rogue", data/thief) and watch --spawn (rogue-gef10 A4);
# @5: per-MAP item sets (gef_fild10's drop set, gef10-eyes-loot.md E3): groups per spot, the map's
# offsets, the 3 x 3 pile inside the area, @killmonster2 at the end, canopy / drop / held commands;
# @6: MASKED icon references from the client's own item icons (`cut-grf`, rogue-gef10.md AK-5)
# item id -> icon name (pinned pre-re item_db; Batt's four: Honey is Healing, Dead Branch Usable,
# the Roughs Etc). Dead Branch is NEVER used (it summons a monster): this tool only drags it.
TARGETS: dict[int, str] = {757: "rough_elunium", 756: "rough_oridecon", 604: "dead_branch",
                           518: "honey"}  # fmt: skip
ICON_DIR = ROOT / "data" / "thief" / "stage_icons"  # client pixels: data/, never committed
OFFSETS: list[tuple[int, int]] = [(0, 0), (3, 0), (0, 3), (-3, 0), (0, -3)]
STILL_S = 5.0  # frames at 1 fps: ~5 per offset
SPOT_SEP = 25  # cells between spots (Chebyshev): other ground, other light
WARP_SETTLE_S = 2.5
READY_MAX_S = 20.0  # a map change's loading screen took longer than 2.5 s (prt_fild08 -> 07)
CHAR = "thief"  # the data dir (crusader.py --char)
JOB = "rogue"  # its job since 2026-10-25 (rogue-gef10.md 3c): every identity check reads it

# --- stage@5: the item set per MAP (gef10-eyes-loot.md E3) ---------------------------------------
# gef_fild10's DROP SET: the items its hunts dropped (2026-10-26). Ids from the local KB (built from
# the pinned rAthena e985006, never committed): data/kb/items.json by name, cross-checked against
# data/kb/drops.json (which gef_fild10 species drops it) and docs/planning/gef10-prep.md 1a /
# gef10-detector.md 1e. Axe is 1301, Orc Warrior's drop (1302 / 1303 are other Axes the map never
# drops); Nursing Bottle is 7270 (aegis Milk_Bottle, Orc Baby's drop). Etc tab: 8, Use tab: Milk
# and Green Herb, Eqp tab: Axe (gm_state.clear_loot reads all three tabs).
GEF10_ITEMS: dict[int, str] = {
    7053: "cyfar", 931: "orcish_voucher", 938: "sticky_mucus", 519: "milk", 910: "garlet",
    998: "iron", 7126: "large_jellopy", 756: "rough_oridecon", 511: "green_herb",
    7270: "nursing_bottle", 1301: "axe",
}  # fmt: skip
# The views on gef_fild10 (13j: today's drops lie under our HP bar at our feet, beside another
# item): (0, 0) = the pile of the spot's group in the 3 x 3 at our feet; then two existing
# offsets, the pile beside / below us. (0, -3) puts the pile behind our own sprite, (-3, 0)
# mirrors (3, 0) (an item is one billboard frame), and a 3rd offset would start after most of the
# group expired.
GEF10_OFFSETS: tuple[tuple[int, int], ...] = ((0, 0), (3, 0), (0, 3))
GEF10_PER_SPOT = 6  # drops ~5.5 s apart: the first expires ~32 s after the last, after view (3, 0)
PILE: tuple[tuple[int, int], ...] = tuple((dx, dy) for dy in (-1, 0, 1) for dx in (-1, 0, 1))
LOOT_LIFE_S = 65.0  # a floor item lives 60 s (target-items.md 1: 40 of 48 lived exactly 60.0 s)
SEARCH_MARGIN = 10  # cells: search_area's margin around every warp span (and NPC, npc_keep)
G10_DATA = Path("/dev/shm/poring-lab-tmp/gef10-det/grf/data")  # map_labels.GEF10's client data
PAYF07_DATA = Path("/dev/shm/poring-lab-tmp/payf07/grf/data")  # map_labels.PAYF07's


@dataclass(frozen=True)
class MapSet:
    """One map's staging set. pay_fild07's (DEFAULT_SET) is stage@1-4's behaviour, unchanged."""

    items: dict[int, str]  # item id -> icon name, in the order the @item lines are typed
    icon_dir: Path  # loot-<name>.npy (client pixels: data/, never committed)
    per_spot: int  # items dropped at each spot (every item when >= len(items))
    offsets: tuple[tuple[int, int], ...]  # the camera's still views, (0, 0) first
    pile: bool = False  # a spot needs its 3 x 3 drop pile inside the area too
    needs_open: bool = False  # spots / run refuse without --open (the canopy mask)
    npc_keep: bool = False  # SEARCH_MARGIN cells off every L3 NPC cell too (the Kafra, boards)
    clear: str = "none"  # "end": two @killmonster2 LOOT_LIFE_S apart after the last spot
    rsw: Path | None = None  # the map's RSW and model dir (client data in /dev/shm): `canopy`
    models: Path | None = None


DEFAULT_SET = MapSet(TARGETS, ICON_DIR, len(TARGETS), tuple(OFFSETS))
MAP_SETS: dict[str, MapSet] = {
    "pay_fild07": replace(DEFAULT_SET, rsw=PAYF07_DATA / "pay_fild07.rsw",
                          models=PAYF07_DATA / "model"),
    "gef_fild10": MapSet(GEF10_ITEMS, ICON_DIR / "gef_fild10", GEF10_PER_SPOT, GEF10_OFFSETS,
                         pile=True, needs_open=True, npc_keep=True, clear="end",
                         rsw=G10_DATA / "gef_fild10.rsw", models=G10_DATA / "model"),
}  # fmt: skip


def map_set(map_: str) -> MapSet:
    """The map's set; any other map stages pay_fild07's targets (stage@1-4's behaviour)."""
    return MAP_SETS.get(map_, DEFAULT_SET)


def spot_cells(ms: MapSet) -> list[tuple[int, int]]:
    """PURE: the cells (relative to a spot) that must lie in the area: every view, and the 3 x 3
    drop pile when ``ms.pile`` (rAthena scatters a dropped item onto the cells around us)."""
    return sorted(set(ms.offsets) | (set(PILE) if ms.pile else set()))


def item_groups(ids: Sequence[int], n: int, per_spot: int, seed: int) -> list[list[int]]:
    """PURE: ``n`` groups of ``per_spot`` distinct ids, each in ``ids``' order. With per_spot >=
    len(ids) every group is all of ``ids`` (stage@1-4). Otherwise BALANCED: each group takes the
    least-used ids so far (ties in a seeded order), so any two ids' counts differ by <= 1."""
    ids = list(ids)
    if per_spot >= len(ids):
        return [list(ids) for _ in range(n)]
    if per_spot < 1:
        raise SystemExit(f"stage_items: --per-spot {per_spot} (>= 1)")
    rng = np.random.default_rng(seed)
    count = dict.fromkeys(ids, 0)
    out: list[list[int]] = []
    for _ in range(n):
        tie = rng.permutation(len(ids))
        order = sorted(range(len(ids)), key=lambda j: (count[ids[j]], int(tie[j])))
        pick = {ids[j] for j in order[:per_spot]}
        for i in pick:
            count[i] += 1
        out.append([i for i in ids if i in pick])
    return out


def pick_spots(area: Any, n: int, seed: int, sep: int = SPOT_SEP,
               offsets: list[tuple[int, int]] = OFFSETS) -> list[tuple[int, int]]:  # fmt: skip
    """PURE: up to ``n`` cells of ``area`` (bool [y, x]) whose every offset is in ``area`` too, at
    least ``sep`` cells apart (Chebyshev), drawn in a seeded order."""
    h, w = area.shape
    cand = []
    for y, x in zip(*np.nonzero(area), strict=True):
        if all(0 <= x + dx < w and 0 <= y + dy < h and area[y + dy, x + dx] for dx, dy in offsets):
            cand.append((int(x), int(y)))
    order = np.random.default_rng(seed).permutation(len(cand))
    out: list[tuple[int, int]] = []
    for i in order:
        c = cand[int(i)]
        if all(max(abs(c[0] - o[0]), abs(c[1] - o[1])) >= sep for o in out):
            out.append(c)
            if len(out) == n:
                break
    return out


CANOPY_NORTH, CANOPY_AROUND = 6, 3  # cells: a tall model hides what stands NORTH of its base on
# screen (the camera looks north); the target-items study (9b) found 29 % of its items under trees


def open_area(
    area: Any, canopy: Any, north: int = CANOPY_NORTH, around: int = CANOPY_AROUND
) -> Any:
    """PURE: ``area`` minus the tall-model footprints ``canopy`` (bool [y, x]) widened by ``around``
    cells and by ``north`` cells towards +y (north), where an item would be drawn behind a tree."""
    h, w = canopy.shape
    grown = canopy.copy()
    ys, xs = np.nonzero(canopy)
    for dy in range(-around, north + 1):
        for dx in range(-around, around + 1):
            grown[np.clip(ys + dy, 0, h - 1), np.clip(xs + dx, 0, w - 1)] = True
    return area & ~grown


CANOPY_MIN_TOP = 10.0  # world units UP: a model whose highest vertex is above this is "tall"


def canopy_mask(models: Iterable[tuple[Any, Any]], shape: tuple[int, int],
                min_top: float = CANOPY_MIN_TOP) -> Any:  # fmt: skip
    """PURE (stage@5): the tall-model footprints as bool [y, x] of ``shape`` (h, w). ``models``:
    (cells (n, 2) fractional x / y, altitude UP (n,)) per placed model (poring_dataset.rsw
    to_cells). A model is tall when its highest vertex is above ``min_top``; its footprint is the
    cell box floor(min) .. ceil(max) of its vertices. This rule reproduces stage@2's pay_fild07
    mask (/dev/shm/poring-lab-tmp/payf07/canopy.npy, 74,319 cells) cell for cell."""
    h, w = shape
    m = np.zeros((h, w), dtype=bool)
    for cells, alt in models:
        c, a = np.asarray(cells, dtype=float), np.asarray(alt, dtype=float)
        if len(c) == 0 or float(a.max()) <= min_top:
            continue
        x0, y0 = (int(v) for v in np.floor(c.min(axis=0)))
        x1, y1 = (int(v) for v in np.ceil(c.max(axis=0)))
        x0, y0, x1, y1 = max(x0, 0), max(y0, 0), min(x1, w - 1), min(y1, h - 1)
        if x0 <= x1 and y0 <= y1:
            m[y0 : y1 + 1, x0 : x1 + 1] = True
    return m


def build_canopy(map_: str, rsw: Path, models: Path) -> Any:
    """OFFLINE: canopy_mask of the map's RSW (client data, /dev/shm), shaped like its GAT."""
    from poring_dataset import camera as cam
    from poring_dataset import gat as gatmod
    from poring_dataset import rsw as rswmod

    gat = gatmod.parse((cam.GAT_DIR / f"{map_}.gat").read_bytes())
    meshes: dict[str, Any] = {}
    placed = []
    for m in rswmod.parse_rsw(rsw.read_bytes()).models:
        if m.model_file not in meshes:
            path = models / m.model_file.replace("\\", "/")
            if not path.exists():
                raise SystemExit(f"{path}: the RSW's model is not extracted (grf_read.py)")
            meshes[m.model_file] = rswmod.parse_rsm(path.read_bytes())
        placed.append(rswmod.to_cells(rswmod.world_points(meshes[m.model_file], m,
                                                          (gat.width, gat.height))))  # fmt: skip
    return canopy_mask(placed, (gat.height, gat.width))


def npc_cells(map_: str, kb: Path | None = None) -> list[tuple[int, int]]:
    """Every script NPC cell of the map from L3 (data/kb/npc_cells.json); refuses (SystemExit)
    when L3 does not list the map as complete: an NPC it does not know could not be kept away."""
    path = (kb or ROOT / "data" / "kb") / "npc_cells.json"
    entry = json.loads(path.read_text())["maps"].get(map_)
    if not entry or not entry.get("complete"):
        raise SystemExit(f"stage_items refused: {path} does not list {map_} as complete")
    return [(int(n["x"]), int(n["y"])) for n in entry.get("npcs", [])]


def search_area(map_: str, npc_keep: bool = False) -> Any:
    """The hunt runner's own search area (dungeon_hunt.run: stand grid, 10 cells off every warp,
    the zones applied, the sealed-off parts cut, the main component). ``npc_keep`` (stage@5,
    gef_fild10): 10 cells off every L3 NPC cell too (the Kafra, the bulletin boards)."""
    import hunt_core as hc
    import hunt_flow as hf
    import map_zones as mz
    from anim_region import stand_grid

    from poring_dataset import camera as cam
    from poring_dataset import gat as gatmod

    gat = gatmod.parse((cam.GAT_DIR / f"{map_}.gat").read_bytes())
    ok = stand_grid(map_, gat)
    warps = json.loads((ROOT / "data" / "kb" / "warps.json").read_text()).get(map_, [])
    keep = [(w["x"], w["y"], w["span_x"], w["span_y"]) for w in warps]
    if npc_keep:
        keep += [(x, y, 0, 0) for x, y in npc_cells(map_)]
    zones = mz.load(map_, shape=ok.shape)
    if zones is None:
        raise SystemExit(f"stage_items refused: no config/map_zones/{map_}.yaml")
    area = mz.apply(ok, hc.search_area(ok, keep, margin=SEARCH_MARGIN), zones)[1]
    cut = mz.sealed_off(ok, mz.route_grid(ok, zones))
    return hf.main_component(area & ~cut)


def stands(spots: Sequence[tuple[int, int]],
           offsets: Sequence[tuple[int, int]]) -> list[list[int]]:  # fmt: skip
    """PURE: every cell the character is @warped onto (each spot plus its views)."""
    return [[x + dx, y + dy] for x, y in spots for dx, dy in offsets]


def plan_spots(map_: str, n: int, seed: int, open_: Path | None) -> list[tuple[int, int]]:
    """The run's spots (``spots`` prints the same list): the search area, the open ground when
    ``open_`` (required where the map's set says so), every spot_cells cell inside, and the stand
    checks of npc_click_test (warp spans, NPC touch areas, the SERVER's walkable cells) as a
    refusal on every stand."""
    import npc_click_test as nct

    ms = map_set(map_)
    if ms.needs_open and open_ is None:
        raise SystemExit(f"stage_items refused: {map_} stages on open ground only (--open)")
    area = search_area(map_, npc_keep=ms.npc_keep)
    if open_ is not None:  # target-items.md 9b: stage on OPEN ground (the RSW's tall models)
        area = open_area(area, np.load(open_))
    spots = pick_spots(area, n, seed, offsets=spot_cells(ms))
    plan = {"npcs": [{"stands": stands(spots, ms.offsets)}], "clicks": []}
    nct.check_warps(map_, plan, clicks=False)
    return spots


CLASH_STOCK = 6.0  # mean grey difference: a staged icon must be FAR from every kept / empty
# reference (2 x gm_state.ICON_MATCH 3.0): clear_loot drops whatever matches the set within 3.0
CLASH_OWN = 3.0  # ... and from the set's other icons (gm_state.ICON_MATCH: they must not merge)


def icon_clashes(new: dict[str, Any], stock: dict[str, Any], stock_bar: float = CLASH_STOCK,
                 own_bar: float = CLASH_OWN) -> list[tuple[str, str, float]]:  # fmt: skip
    """PURE (stage@5): (new, other, distance) for every new icon within ``stock_bar`` of a
    kept / empty reference (``stock``: a White Potion or Fly Wing would be DROPPED), or within
    ``own_bar`` of another new icon. Icons of another shape are not compared."""
    out = []
    names = sorted(new)
    for i, a in enumerate(names):
        for b, ref, bar in [*((s, stock[s], stock_bar) for s in sorted(stock)),
                            *((o, new[o], own_bar) for o in names[i + 1 :])]:  # fmt: skip
            if np.shape(ref) != np.shape(new[a]):
                continue
            d = float(np.abs(np.asarray(new[a], np.float32) - np.asarray(ref, np.float32)).mean())
            if d <= bar:
                out.append((a, b, round(d, 2)))
    return out


def cut(spec: Path, map_: str = "pay_fild07") -> dict[str, Any]:
    """OFFLINE: the map's icon set from judged full-desktop PNGs with the inventory at its home.
    ``spec`` (JSON): {"origin": [gx, gy], "icons": [{"png", "col", "row", "name"}]} -- every name
    one of the map set's (a person, or Claude on a judged screenshot, identified the slots). The
    origin is the game region's top left in the PNG (`give --frames` prints it). stage@5: refused,
    nothing written, when an icon clashes with the stock references (icon_clashes)."""
    import gm_state
    from PIL import Image

    ms = map_set(map_)
    sp = json.loads(spec.read_text())
    gx, gy = sp["origin"]
    crops: dict[str, Any] = {}
    for it in sp["icons"]:
        if it["name"] not in ms.items.values():
            raise SystemExit(f"stage_items cut: {it['name']!r} is not in {map_}'s set")
        rgb = np.asarray(Image.open(it["png"]).convert("RGB"))[gy:, gx:]
        f = np.ascontiguousarray(rgb[..., ::-1])
        crops[it["name"]] = gm_state.icon_crop(f, it["col"], it["row"])
    stock = {n: ref for n, (kind, ref) in gm_state.load_loot_refs().items()
             if kind in ("kept", "empty")}  # fmt: skip
    if bad := icon_clashes(crops, stock):
        raise SystemExit(f"stage_items cut refused (nothing written): icons too close {bad}")
    ms.icon_dir.mkdir(parents=True, exist_ok=True)
    for name, crop in crops.items():
        np.save(ms.icon_dir / f"loot-{name}.npy", crop)
    missing = [n for n in ms.items.values() if not (ms.icon_dir / f"loot-{n}.npy").exists()]
    return {"cut": list(crops), "dir": str(ms.icon_dir), "missing": missing,
            "stock_refs": sorted(stock)}  # fmt: skip


# --- stage@6: MASKED references from the client's item icons (rogue-gef10.md AK-5) -------------
ICON_BMP_OFFSET = 3  # icon_crop's column c shows the item BMP's column c - 3, rows aligned:
# measured 2026-10-29 for all 13 icons at hand (the 11 of gef_fild10's set, the White Potion, the
# Fly Wing), each with a far worse second offset
MIN_ITEM_PX = 40  # a masked reference compares at least this many item pixels


def item_resnames(table_text: str, ids: Iterable[int]) -> dict[int, str]:
    """PURE: item id -> the client's resource name, from idnum2itemresnametable.txt's text
    ("id#name#" lines, already decoded)."""
    want, out = set(ids), {}
    for line in table_text.splitlines():
        parts = line.split("#")
        if len(parts) >= 2 and parts[0].strip().isdigit() and int(parts[0]) in want:
            out[int(parts[0])] = parts[1].strip()
    return out


def bmp_template(rgb: Any, shape: tuple[int, int] = (16, 14),
                 offset: int = ICON_BMP_OFFSET) -> tuple[Any, Any]:  # fmt: skip
    """PURE: (grey template, item mask) in gm_state.icon_crop's geometry from a client item BMP
    (RGB; pure magenta is transparent: not the item)."""
    import gm_state

    rgb = np.asarray(rgb)
    trans = (rgb[..., 0] > 240) & (rgb[..., 1] < 15) & (rgb[..., 2] > 240)
    grey = gm_state.to_gray(np.ascontiguousarray(rgb[..., ::-1]))
    h, w = shape
    t, item = np.zeros(shape, np.float32), np.zeros(shape, bool)
    t[:, offset:] = grey[:h, : w - offset]
    item[:, offset:] = ~trans[:h, : w - offset]
    return t, item


def masked_refusals(masked: dict[str, Any], screen: dict[str, Any],
                    stock: dict[str, tuple[str, Any]]) -> list[str]:  # fmt: skip
    """PURE (stage@6): why a masked set must NOT be written ([] = it may). Each item's
    screen-cut reference (`cut`, run conditions: slot background, glow) must classify as that
    item against the masked set (gm_state.classify_icon, as clear_loot does); every kept / empty
    stock reference must classify "unknown" and lie beyond gm_state.ICON_AMBIGUOUS of every masked
    reference; every masked reference needs MIN_ITEM_PX item pixels."""
    import gm_state as gs

    refs = {n: ("loot", m) for n, m in masked.items()}
    why = []
    for n, m in sorted(masked.items()):
        px = int((~np.ma.getmaskarray(m)).sum())
        if px < MIN_ITEM_PX:
            why.append(f"{n}: {px} item pixels < {MIN_ITEM_PX}")
        if n not in screen:
            why.append(f"{n}: no screen-cut reference to prove it on (cut first)")
            continue
        kind, got, d = gs.classify_icon(screen[n], refs)
        if (kind, got) != ("loot", n):
            why.append(f"{n}: its screen reference reads {got or kind} ({d:.2f})")
    for s, (_kind, ref) in sorted(stock.items()):
        kind, got, d = gs.classify_icon(ref, refs)
        near = min((gs.icon_distance(ref, m), n) for n, m in masked.items())
        if kind != "unknown" or near[0] <= gs.ICON_AMBIGUOUS:
            why.append(f"stock {s}: {near[1]} at {near[0]:.2f} (<= {gs.ICON_AMBIGUOUS})")
    return why


def cut_grf(map_: str, table: Path, icons: Path) -> dict[str, Any]:
    """OFFLINE (stage@6): the map set's MASKED references (loot-<name>.npz: template + item
    mask) from the client's item BMPs. Refused, nothing written, on any masked_refusals."""
    import gm_state
    from PIL import Image

    ms = map_set(map_)
    res = item_resnames(table.read_bytes().decode("cp949", "replace"), ms.items)
    if missing := [ms.items[i] for i in ms.items if i not in res]:
        raise SystemExit(f"stage_items cut-grf: no resource name for {missing} in {table}")
    masked, screen = {}, {}
    for iid, name in ms.items.items():
        bmp = icons / f"{res[iid]}.bmp"
        if not bmp.is_file():
            raise SystemExit(f"stage_items cut-grf: {bmp} is missing (grf_read.py extract)")
        t, item = bmp_template(np.asarray(Image.open(bmp).convert("RGB")))
        masked[name] = np.ma.MaskedArray(t, mask=~item)
        if (f := ms.icon_dir / f"loot-{name}.npy").exists():
            screen[name] = np.load(f)
    stock = {n: kr for n, kr in gm_state.load_loot_refs().items() if kr[0] in ("kept", "empty")}
    if why := masked_refusals(masked, screen, stock):
        raise SystemExit(f"stage_items cut-grf refused (nothing written): {why}")
    own = {n: round(gm_state.icon_distance(screen[n], m), 2) for n, m in masked.items()}
    for name, m in masked.items():
        np.savez(ms.icon_dir / f"loot-{name}.npz", template=np.asarray(m.data, np.float32),
                 item=~np.ma.getmaskarray(m))  # fmt: skip
    return {"cut": sorted(masked), "dir": str(ms.icon_dir), "screen_ref_distance": own,
            "stock_refs": sorted(stock)}  # fmt: skip


def _session(why: str) -> Any:
    import ro_agent as r

    return r.session(f"rule:stage-items-{why}")


def _check(screen: Any) -> None:
    import crusader as cr
    import ro_agent as r

    if not cr.check(screen, JOB, CHAR)["ok"]:
        raise r.Stop("stage_items: not the Thief")


def _settle(screen: Any, max_s: float = READY_MAX_S) -> float:
    """After a @warp: wait until the Basic Info identity reads again (the first run's 2.5 s fixed
    wait checked the LOADING screen of a map change and stopped). Returns the seconds waited."""
    import crusader as cr
    import ro_agent as r

    t0 = time.monotonic()
    time.sleep(WARP_SETTLE_S)
    while not cr.check(screen, JOB, CHAR)["ok"]:
        if time.monotonic() - t0 > max_s:
            raise r.Stop(f"stage_items: the identity did not read within {max_s} s of a @warp")
        time.sleep(0.5)
    return round(time.monotonic() - t0, 1)


def held_refusal(rows: Iterable[Sequence[Any]], items: dict[int, str] = TARGETS) -> str | None:
    """PURE (stage@3, 2026-10-25): why a staging run must NOT start, or None. gm_state.clear_loot
    drops WHOLE stacks, so a target item already held goes to the floor with the staged copy and
    is lost: run c (2026-10-24 22:23) dropped Dead Branch 5, Rough Elunium 3, Rough Oridecon 2 and
    Honey 2 at its first spot, 4.04's natural Dead Branches and Rough Elunium among them. ``rows``
    = (nameid, amount) from the DB, its LAST SAVE: a pickup since then is not in it. ``items``:
    the map's set (stage@5; on gef_fild10 the hunts' own loot is in it: the store step first)."""
    held = {int(i): int(n) for i, n in rows if int(i) in items and int(n) > 0}
    if not held:
        return None
    return (
        f"stage_items refused: the {CHAR} holds target items {held} (DB last save): "
        "clear_loot drops whole stacks, so they would be staged and lost (a person stores "
        "them first)"
    )


def _held_rows(items: dict[int, str] = TARGETS) -> list[Sequence[Any]]:
    """The Thief's target-item stacks from the lab DB (the experimenter's check, as
    dungeon_hunt's setup reads its stock; never a decision input of the agent)."""
    import crusader as cr
    import ro_agent as r

    name = json.loads((cr.data_dir(CHAR) / "char.json").read_text())["name"]
    cid = int(r.db_query(f"SELECT char_id FROM `char` WHERE name = {r.sql_str(name)};")[0][0])
    ids = ", ".join(str(i) for i in sorted(items))
    return list(r.db_query(f"SELECT nameid, amount FROM inventory WHERE char_id = {cid} "
                           f"AND nameid IN ({ids});"))  # fmt: skip


def give(map_: str = "pay_fild07", frames: bool = False) -> None:
    """LIVE: one of each of the map set's items (for the icon cut, then the inventory frames to
    judge). ``frames`` (stage@5): then one desktop frame per inventory tab (_bank_tabs) and the
    game region's origin, for the cut SPEC."""
    import bench
    import crusader as cr
    import ro_agent as r

    ms = map_set(map_)
    with _session("give") as (agent, screen):
        agent.wait_for_human()
        _check(screen)
        for iid in ms.items:
            cr.gm_line(agent, screen, f"@item {iid} 1", JOB, CHAR)
            time.sleep(0.8)
        bench.close_chat(agent, screen)
        name = "stage-give.png" if map_ == "pay_fild07" else f"stage-give-{map_}.png"
        print(r.to_png(screen.full(), r.SHOTS / name))
        if frames:
            print(json.dumps(_bank_tabs(agent, screen, map_)), flush=True)


def _bank_tabs(agent: Any, screen: Any, map_: str) -> dict[str, Any]:
    """LIVE (stage@5): the inventory opened by its chord and READ open (ui_gate's window check,
    as dungeon_hunt.clear_etc since its toggle incident), one desktop frame per tab after
    gm_state's known tab click, then closed by its chord and the UI gate. UI clicks only, inside
    the window read open; nothing is dragged."""
    import gm_state as gs
    import ro_agent as r
    import ui_gate

    region = r.game_region()

    def inv_open() -> bool:
        f = np.ascontiguousarray(r.grab_after(screen, region, r.ns())[..., :3])
        return "inventory" in ui_gate.windows_at_home(
            f, ui_gate._registry(ui_gate._require_ready())
        )

    ui_gate.ensure_clear(agent, screen, why="stage-frames-start")
    r.activate_client(agent, screen)
    agent.chord(*ui_gate.window_keys("inventory"))
    time.sleep(1.0)
    out: dict[str, str] = {}
    try:
        if not inv_open():
            raise r.Stop("stage_items: the inventory did not read open after its chord")
        for tab in gs.INV_TABS:
            gs._tab(agent, screen, tab)
            if not inv_open():
                raise r.Stop(f"stage_items: the inventory closed at its {tab} tab")
            out[tab] = str(r.to_png(screen.full(), r.SHOTS / f"stage-give-{map_}-{tab}.png"))
    finally:
        r.activate_client(agent, screen)
        agent.chord(*ui_gate.window_keys("inventory"))
        time.sleep(1.0)
        ui_gate.ensure_clear(agent, screen, why="stage-frames-end")
    return {"origin": [region[0], region[1]], "frames": out}


def drop(map_: str) -> int:
    """LIVE (stage@5): drop what `give` gave, by gm_state.clear_loot with the map's NEW icon set:
    the set's positive case (every item classified and dropped, nothing else) before a timed run,
    and it empties the bag of the given copies (run's held check refuses while the DB holds any)."""
    import bench
    import gm_state
    import ro_agent as r
    import ui_gate

    ms = map_set(map_)
    missing = [n for n in ms.items.values() if not (ms.icon_dir / f"loot-{n}.npy").exists()]
    if missing:
        raise SystemExit(f"stage_items drop refused: no icon for {missing} in {ms.icon_dir} (cut)")
    with _session("drop") as (agent, screen):
        agent.wait_for_human()
        _check(screen)
        bench.close_chat(agent, screen)
        ui_gate.ensure_clear(agent, screen, why="stage-drop-start")
        res = gm_state.clear_loot(agent, screen, why="stage-drop", refs_dir=ms.icon_dir)
        print(r.to_png(screen.full(), r.SHOTS / f"stage-drop-{map_}.png"), flush=True)
    names = sorted(d["item"] for d in res["dropped"])
    ok = names == sorted(ms.items.values())
    print(json.dumps({"dropped": names, "unknown": res["unknown"], "kept": res["kept"],
                      "all_and_only_the_set": ok}))  # fmt: skip
    return 0 if ok else 1


def held(map_: str) -> int:
    """READ-ONLY: the map set's stacks in the DB's last save, and whether run would refuse."""
    ms = map_set(map_)
    rows = _held_rows(ms.items)
    why = held_refusal(rows, ms.items)
    print(json.dumps({"rows": [[int(i), int(n)] for i, n in rows], "refusal": why}))
    return 0 if why is None else 1


def immune_on() -> None:
    """LIVE: @monsterignore (a TOGGLE: run it only on a fresh login, where it is off) + a frame
    for a person to read the confirmation line in the chat."""
    import crusader as cr
    import ro_agent as r

    with _session("immune") as (agent, screen):
        agent.wait_for_human()
        _check(screen)
        cr.gm_line(agent, screen, "@monsterignore", JOB, CHAR)
        time.sleep(1.2)
        print(r.to_png(screen.full(), r.SHOTS / "stage-immune.png"))


END_KILL_TODO = (
    "stage_items: the END @killmonster2 pair is incomplete. Before the next hunt a person types "
    "@killmonster2, waits >= 65 s, and types it again: a Poporing that took staged items drops "
    "them at its death (also a no-drop one) and they expire 60 s later"
)


def run(a: argparse.Namespace) -> int:
    import bench
    import crusader as cr
    import gm_state
    import ro_agent as r
    import ui_gate

    ms = map_set(a.map)
    per_spot = ms.per_spot if a.per_spot is None else a.per_spot
    clear = ms.clear if a.clear is None else a.clear
    if not a.immune_confirmed:
        raise SystemExit(
            "stage_items refused: --immune-confirmed (a person read immune-on's frame)"
        )
    missing = [n for n in ms.items.values() if not (ms.icon_dir / f"loot-{n}.npy").exists()]
    if missing:
        raise SystemExit(f"stage_items refused: no icon for {missing} in {ms.icon_dir} (cut)")
    why = held_refusal(_held_rows(ms.items), ms.items)
    if why:
        raise SystemExit(why)
    spots = plan_spots(a.map, a.n, a.seed, a.open)
    groups = item_groups(list(ms.items), len(spots), per_spot, a.seed)
    sid = f"{time.strftime('%Y%m%dT%H%M%S')}-stage-items-{a.map}-{a.label}"
    out = DEMO / sid
    out.mkdir(parents=True)
    evf = (out / "events.jsonl").open("a")

    def ev(rec: dict[str, Any]) -> None:
        evf.write(json.dumps({"t_ns": r.ns(), **rec}) + "\n")
        evf.flush()

    start = {"kind": "run_start", "version": VERSION, "map": a.map, "seed": a.seed, "spots": spots,
             "open": None if a.open is None else str(a.open),
             "offsets": ms.offsets, "still_s": STILL_S, "targets": ms.items}  # fmt: skip
    if per_spot < len(ms.items) or clear != "none":  # stage@5's fields (pay_fild07: none)
        start |= {"per_spot": per_spot, "groups": groups, "clear": clear}
    ev(start)
    reason = "done"
    kills: list[str] = []  # ICT clock times: the Orc Lord dies at the first if alive (the D)
    staged = False  # an item may be on the floor from the first clear_loot on

    def kill_all(agent: Any, screen: Any, i: int) -> None:
        """@killmonster2: every monster dies, no drops of its own; a looter still drops what it
        took (mob.cpp mob_dead "Loot MUST drop!", rathena e985006), and that expires in 60 s."""
        cr.gm_line(agent, screen, "@killmonster2", JOB, CHAR)
        kills.append(datetime.now(ZoneInfo("Asia/Bangkok")).strftime("%Y-%m-%d %H:%M:%S"))
        ev({"kind": "killmonster2", "i": i, "ict": kills[-1]})
        bench.close_chat(agent, screen)

    with _session("run") as (agent, screen):
        agent.wait_for_human()
        _check(screen)
        try:
            for k, (x, y) in enumerate(spots):
                want = sorted(ms.items[i] for i in groups[k])
                cr.gm_line(agent, screen, f"@warp {a.map} {x} {y}", JOB, CHAR)
                ev({"kind": "warp", "spot": k, "at": [x, y], "settle_s": _settle(screen)})
                bench.close_chat(agent, screen)
                for iid in groups[k]:
                    cr.gm_line(agent, screen, f"@item {iid} 1", JOB, CHAR)
                    time.sleep(0.8)
                bench.close_chat(agent, screen)
                staged = True
                res = gm_state.clear_loot(agent, screen, why=f"stage-{k}", refs_dir=ms.icon_dir)
                names = sorted(d["item"] for d in res["dropped"])
                ev({"kind": "dropped", "spot": k, "at": [x, y], "items": names,
                    "unknown": res["unknown"]})  # fmt: skip
                if names != want:
                    reason = f"spot {k}: dropped {names}, not {want}"
                    break
                for dx, dy in ms.offsets:
                    if (dx, dy) != (0, 0):
                        cr.gm_line(agent, screen, f"@warp {a.map} {x + dx} {y + dy}", JOB, CHAR)
                        _settle(screen)
                        bench.close_chat(agent, screen)
                    ev({"kind": "still", "spot": k, "at": [x + dx, y + dy], "s": STILL_S})
                    time.sleep(STILL_S)
                print(f"spot {k + 1}/{len(spots)} at {x},{y}: {names}", flush=True)
            if clear == "end" and staged:  # also after a wrong drop: earlier spots may be looted
                kill_all(agent, screen, 0)
                time.sleep(LOOT_LIFE_S)  # what the looters dropped expires; re-looters drop it now
                kill_all(agent, screen, 1)
        except r.Stop as exc:
            reason = f"stop: {exc}"
        finally:
            if clear == "end" and staged and len(kills) < 2:
                print(END_KILL_TODO, file=sys.stderr, flush=True)  # first: a UI stop may follow
            ui_gate.ensure_clear(agent, screen, why="stage-end")
            if clear == "end" and staged and not kills:
                try:
                    kill_all(agent, screen, 0)
                except r.Stop as exc:
                    ev({"kind": "killmonster2_failed", "why": str(exc)})
            print(r.to_png(screen.full(), r.SHOTS / f"stage-end-{a.label}.png"), flush=True)
    end: dict[str, Any] = {"kind": "run_end", "reason": reason}
    if clear != "none":
        end["killmonster2"] = kills
    ev(end)
    evf.close()
    print(json.dumps({"sid": sid, "reason": reason, "spots": len(spots),
                      **({"killmonster2_ict": kills} if clear != "none" else {})}))  # fmt: skip
    return 0 if reason == "done" and (clear == "none" or not staged or len(kills) == 2) else 1


WATCH_DWELL_S = 30.0  # payf07-detector.md: still frames of monsters around an immune Thief


def watch_cells(lattice: list[dict[str, Any]], seed: int, max_cells: int) -> list[tuple[int, int]]:
    """PURE: the lattice's cells in a seeded order, cut at ``max_cells`` (successive seeds cover the
    map evenly when a time box cuts the list, as warp_watch's plan does)."""
    cells = [(int(c["x"]), int(c["y"])) for c in lattice]
    if len(set(cells)) != len(cells) or not cells:
        raise SystemExit("watch: an empty lattice or a repeated cell")
    order = np.random.default_rng(seed).permutation(len(cells))
    return [cells[int(i)] for i in order[:max_cells]]


def watch(a: argparse.Namespace) -> int:
    """LIVE (payf07-detector.md, Elder Willow is the thinnest class): the IMMUNE Thief warps over a
    lattice of three-check stand cells and dwells WATCH_DWELL_S at each while the 1-fps recorder
    (started beside this tool) banks the frames. Typed @warp lines only, no world click; the same
    recording path as the staged session, so its frames join TRAIN by the 3c rule."""
    import bench
    import crusader as cr
    import ro_agent as r
    import ui_gate

    if not a.immune_confirmed:
        raise SystemExit("stage_items watch refused: --immune-confirmed (a person read the frame)")
    cells = watch_cells(json.loads(a.lattice.read_text()), a.seed, a.max_cells)
    sid = f"{time.strftime('%Y%m%dT%H%M%S')}-watch-{a.map}-{a.label}"
    out = DEMO / sid
    out.mkdir(parents=True)
    evf = (out / "events.jsonl").open("a")

    def ev(rec: dict[str, Any]) -> None:
        evf.write(json.dumps({"t_ns": r.ns(), **rec}) + "\n")
        evf.flush()

    ev({"kind": "run_start", "version": VERSION, "what": "watch", "map": a.map, "seed": a.seed,
        "cells": cells, "dwell_s": a.dwell_s, "lattice": str(a.lattice),
        "spawn": a.spawn, "spawn_n": a.spawn_n})  # fmt: skip
    reason = "done"
    t_end = time.monotonic() + a.max_minutes * 60
    with _session("watch") as (agent, screen):
        agent.wait_for_human()
        _check(screen)
        try:
            for k, (x, y) in enumerate(cells):
                if time.monotonic() > t_end:
                    reason = "time_box"
                    break
                cr.gm_line(agent, screen, f"@warp {a.map} {x} {y}", JOB, CHAR)
                settle = _settle(screen)
                if a.spawn is not None:  # stage@4: the practice monster beside us (Amendment A4)
                    cr.gm_line(agent, screen, f"@monster {a.spawn} {a.spawn_n}", JOB, CHAR)
                    ev({"kind": "spawn", "i": k, "mob": a.spawn, "n": a.spawn_n})
                bench.close_chat(agent, screen)
                ev({"kind": "dwell", "i": k, "at": [x, y], "settle_s": settle, "s": a.dwell_s})
                time.sleep(a.dwell_s)
                if a.spawn is not None:  # it (and every monster here) dies, no drops; all respawn
                    cr.gm_line(agent, screen, "@killmonster2", JOB, CHAR)
                    ev({"kind": "killmonster2", "i": k})
                    bench.close_chat(agent, screen)
                print(f"cell {k + 1}/{len(cells)} at {x},{y}", flush=True)
        except r.Stop as exc:
            reason = f"stop: {exc}"
        finally:
            ui_gate.ensure_clear(agent, screen, why="watch-end")
            print(r.to_png(screen.full(), r.SHOTS / f"watch-end-{a.label}.png"), flush=True)
    ev({"kind": "run_end", "reason": reason})
    evf.close()
    print(json.dumps({"sid": sid, "reason": reason, "cells": len(cells)}))
    return 0 if reason in ("done", "time_box") else 1


def spots_plan(map_: str, spots: Sequence[tuple[int, int]], seed: int,
               per_spot: int | None = None) -> dict[str, Any]:  # fmt: skip
    """PURE (stage@5): what a run on these spots would stage: the groups (names), each item's
    count, the views and the stands."""
    ms = map_set(map_)
    k = ms.per_spot if per_spot is None else per_spot
    groups = [[ms.items[i] for i in g] for g in item_groups(list(ms.items), len(spots), k, seed)]
    counts = {n: sum(n in g for g in groups) for n in ms.items.values()}
    return {"map": map_, "seed": seed, "spots": [list(s) for s in spots], "per_spot": k,
            "offsets": [list(o) for o in ms.offsets], "groups": groups, "counts": counts,
            "floor_items": sum(counts.values()), "stands": len(stands(spots, ms.offsets)),
            "clear": ms.clear}  # fmt: skip


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)  # fmt: skip
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("spots")
    p.add_argument("--map", default="pay_fild07")
    p.add_argument("--n", type=int, default=12)
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--open", type=Path, default=None)
    p.add_argument("--per-spot", type=int, default=None)
    p.add_argument("--plan", action="store_true",
                   help="stage@5: the groups, counts and stands too (a JSON object)")  # fmt: skip
    p = sub.add_parser("canopy")
    p.add_argument("--map", required=True)
    p.add_argument("--rsw", type=Path, default=None, help="default: the map set's (/dev/shm)")
    p.add_argument("--models", type=Path, default=None, help="default: the map set's (/dev/shm)")
    p.add_argument("--out", type=Path, required=True, help="a .npy under /dev/shm (client-derived)")
    p = sub.add_parser("cut")
    p.add_argument("spec", type=Path)
    p.add_argument("--map", default="pay_fild07")
    p = sub.add_parser("cut-grf")
    p.add_argument("--map", required=True)
    p.add_argument("--table", type=Path, required=True,
                   help="the client's item resource-name table (in /dev/shm)")  # fmt: skip
    p.add_argument("--icons", type=Path, required=True,
                   help="the extracted item BMP directory (/dev/shm)")  # fmt: skip
    p = sub.add_parser("give")
    p.add_argument("--map", default="pay_fild07")
    p.add_argument("--frames", action="store_true",
                   help="stage@5: then one inventory frame per tab, for the cut SPEC")  # fmt: skip
    p = sub.add_parser("drop")
    p.add_argument("--map", required=True)
    p = sub.add_parser("held")
    p.add_argument("--map", default="pay_fild07")
    sub.add_parser("immune-on")
    p = sub.add_parser("watch")
    p.add_argument("--map", default="pay_fild07")
    p.add_argument("--lattice", type=Path, required=True)
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--max-cells", type=int, default=200)
    p.add_argument("--max-minutes", type=float, default=40.0)
    p.add_argument("--dwell-s", type=float, default=WATCH_DWELL_S)
    p.add_argument("--label", default="w")
    p.add_argument("--immune-confirmed", action="store_true")
    p.add_argument(
        "--spawn",
        type=int,
        default=None,
        help="stage@4: a mob id spawned at each cell after the warp (@monster), removed "
        "after the dwell by @killmonster2 (rogue-gef10.md Amendment A4)",
    )
    p.add_argument("--spawn-n", type=int, default=1)
    p = sub.add_parser("run")
    p.add_argument("--map", default="pay_fild07")
    p.add_argument("--n", type=int, default=12)
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--label", default="s")
    p.add_argument("--immune-confirmed", action="store_true")
    p.add_argument("--open", type=Path, default=None,
                   help="a canopy mask .npy (client-derived, /dev/shm): open ground")  # fmt: skip
    p.add_argument("--per-spot", type=int, default=None,
                   help="stage@5: items per spot (default: the map set's)")  # fmt: skip
    p.add_argument("--clear", choices=("none", "end"), default=None,
                   help="stage@5: 'end' = two @killmonster2 65 s apart after the last spot "
                        "(default: the map set's)")  # fmt: skip
    a = ap.parse_args()
    if a.cmd == "spots":
        spots = plan_spots(a.map, a.n, a.seed, a.open)
        if a.plan:
            print(json.dumps(spots_plan(a.map, spots, a.seed, a.per_spot)))
        else:
            print(json.dumps(spots))
    elif a.cmd == "canopy":
        ms = map_set(a.map)
        rsw, models = a.rsw or ms.rsw, a.models or ms.models
        if rsw is None or models is None:
            raise SystemExit(f"stage_items canopy: no RSW / model dir known for {a.map}")
        out = a.out.resolve()
        if not out.is_relative_to("/dev/shm") or out.is_relative_to(ROOT):
            raise SystemExit("stage_items canopy refused: client-derived output goes to /dev/shm, "
                             "outside the repo")  # fmt: skip
        mask = build_canopy(a.map, rsw, models)
        a.out.parent.mkdir(parents=True, exist_ok=True)
        np.save(a.out, mask)
        print(json.dumps({"out": str(a.out), "cells": int(mask.sum()), "shape": list(mask.shape),
                          "sha256": hashlib.sha256(mask.tobytes()).hexdigest()}))  # fmt: skip
    elif a.cmd == "cut":
        print(json.dumps(cut(a.spec, a.map)))
    elif a.cmd == "cut-grf":
        print(json.dumps(cut_grf(a.map, a.table, a.icons)))
    elif a.cmd == "give":
        give(a.map, a.frames)
    elif a.cmd == "drop":
        return drop(a.map)
    elif a.cmd == "held":
        return held(a.map)
    elif a.cmd == "immune-on":
        immune_on()
    elif a.cmd == "watch":
        return watch(a)
    elif a.cmd == "run":
        return run(a)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
