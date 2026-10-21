#!/usr/bin/env python3
"""ECONOMICS, part 1 (Batt 2026-10-21): the ITEM TABLE -- every item's fixed NPC prices, weight
and type on the lab's PRE-RENEWAL server, from the pinned rAthena db and the shops the map-server
loads. OFFLINE; nothing here runs during play.

    econ_items.py build [--src DIR] [--out data/econ/items.json]
    econ_items.py show ID|AEGIS [...] [--items data/econ/items.json]

rAthena is GPL-3.0: the table is DERIVED DATA. It is written at run time to data/econ/ (gitignored)
and is NEVER committed (CLAUDE.md rule 4; THIRD_PARTY.md data rule). Only this code, its tests and
the formulas doc (docs/econ/economics.md) are committed.

THE PRICES (pinned e985006; file:line in src/map unless a path is given):
- value_buy / value_sell: the item_db's Buy / Sell (db/pre-re/item_db_{usable,equip,etc}.yml).
  A missing Sell is Buy / 2 (integer division), a missing Buy is Sell x 2 (itemdb.cpp:1185-1188);
  if value_buy / 124 < value_sell / 75 the sell price becomes 1, the buy-low / sell-high exploit
  guard (itemdb.cpp:1190-1193). Neither given: both 0 (itemdb.cpp:215-216, 234-235).
- NPC SELL (what a shop pays us): value_sell per unit x amount (npc.cpp:3077-3083); only a plain
  `shop` NPC buys (npc.cpp:3040, NPCTYPE_SHOP); Trade NoSell items cannot be sold
  (pc.cpp:1307, itemdb_cansell); MAX_ZENY caps the total (npc.cpp:3116-3119).
- OVERCHARGE lv L (pc.cpp:5708-5719, pc_modifysellvalue): rate = 5 + 2L - (L == 10), so 24 % at
  lv 10; per unit value = (int32)(value_sell x (100 + rate) / 100.) -- a C double TRUNCATED toward
  zero -- then max(min_shop_sell = 0) (conf/battle/items.conf:138). Applied per unit before x
  amount (npc.cpp:3080-3083).
- NPC BUY (what a shop charges): the shop line's price, or value_buy when the line says -1
  (npc.cpp:4146-4148); the cheapest loaded shop is used here.
- DISCOUNT lv L (pc.cpp:5689-5703, pc_modifybuyvalue): rate = 5 + 2L - (L == 10) = 24 % at lv 10;
  per unit value = (int32)(price x (100 - rate) / 100.), truncated, then max(min_shop_buy = 1)
  (items.conf:134); only in a shop whose discount flag is on (npc.cpp:2875-2876,
  npc_shop_discount 4251-4260). A plain `shop` line is discountable unless its first entry is
  `no` (npc.cpp:4091-4105: sscanf of "<id>:<price>" succeeds -> is_discount = 1).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "econ" / "items.json"
SRC = Path("/dev/shm/poring-lab-rathena-src")
ITEM_DBS = (
    "db/pre-re/item_db_usable.yml",
    "db/pre-re/item_db_equip.yml",
    "db/pre-re/item_db_etc.yml",
)
MOB_DB = "db/pre-re/mob_db.yml"
OC_LV = DC_LV = 10
MIN_SHOP_BUY, MIN_SHOP_SELL = 1, 0  # conf/battle/items.conf:134, :138 (no lab override)


# --- the rules (pure) ----------------------------------------------------------------------------


def skill_rate(lv: int) -> int:
    """Discount / Overcharge percent at level ``lv`` (pc.cpp:5693, :5712): 5 + 2 lv - (lv == 10);
    0 below level 1 (no skill)."""
    return 5 + 2 * lv - (1 if lv == 10 else 0) if lv > 0 else 0


def overcharge(value_sell: int, lv: int = OC_LV) -> int:
    """pc_modifysellvalue (pc.cpp:5708-5719): the per-unit NPC sell price with Overcharge lv."""
    rate = skill_rate(lv)
    val = int(float(value_sell) * float(100 + rate) / 100.0) if rate else value_sell
    return max(val, MIN_SHOP_SELL)


def discount(price: int, lv: int = DC_LV) -> int:
    """pc_modifybuyvalue (pc.cpp:5689-5703): the per-unit NPC buy price with Discount lv (the
    Rogue's Compulsion Discount is not ours)."""
    rate = skill_rate(lv)
    val = int(float(price) * float(100 - rate) / 100.0) if rate else price
    return max(val, MIN_SHOP_BUY)


def effective_prices(buy: int | None, sell: int | None) -> tuple[int, int, list[str]]:
    """(value_buy, value_sell, notes) as itemdb.cpp sets them: a missing side derived from the
    other (:1185-1188), then the exploit guard (:1190-1193)."""
    notes = []
    vb, vs = int(buy or 0), int(sell or 0)
    if buy is None and sell is not None:
        vb = vs * 2
        notes.append("buy = sell x 2 (itemdb.cpp:1186)")
    elif buy is not None and sell is None:
        vs = vb // 2
        notes.append("sell = buy / 2 (itemdb.cpp:1188)")
    if vb / 124.0 < vs / 75.0:
        vs = 1
        notes.append("sell forced to 1 by the exploit guard (itemdb.cpp:1190-1193)")
    return vb, vs, notes


def shop_entries(w4: str) -> tuple[bool, list[tuple[int, int]]]:
    """A `shop` line's w4 (`<sprite>[,yes|no],<id>:<price>,...`) -> (discountable, [(id, price)])
    as npc_parse_shop reads it (npc.cpp:4091-4105, :4111-4160)."""
    parts = [p.strip() for p in w4.split(",")[1:]]
    disc = True
    if parts and ":" not in parts[0]:
        flag = parts.pop(0).lower()
        disc = flag == "yes"
    out = []
    for p in parts:
        m = re.match(r"(\d+):(-?\d+)", p)
        if m:
            out.append((int(m[1]), int(m[2])))
    return disc, out


def shop_price(listed: int, value_buy: int) -> int:
    """A shop entry's price: -1 (any negative) means the item's value_buy (npc.cpp:4146-4148)."""
    return value_buy if listed < 0 else listed


def parse_item_db(text: str) -> dict[int, dict[str, Any]]:
    """One item_db YAML -> id -> the fields the economics needs (absent Type = Etc, Weight = 0).
    ``buy`` / ``sell`` stay None when the file does not give them (itemdb.cpp's has_buy /
    has_sell)."""
    import yaml

    doc = yaml.load(text, Loader=getattr(yaml, "CSafeLoader", yaml.SafeLoader))  # noqa: S506
    out: dict[int, dict[str, Any]] = {}
    for e in (doc or {}).get("Body") or []:
        trade = e.get("Trade") or {}
        out[int(e["Id"])] = {
            "aegis": e.get("AegisName"), "name": e.get("Name"),
            "type": str(e.get("Type") or "Etc"), "subtype": e.get("SubType"),
            "weight_db": int(e.get("Weight") or 0),
            "buy_db": None if e.get("Buy") is None else int(e["Buy"]),
            "sell_db": None if e.get("Sell") is None else int(e["Sell"]),
            "no_sell": bool(trade.get("NoSell", False)),
            "trade_override": trade.get("Override"),
        }  # fmt: skip
    return out


def price_item(it: Mapping[str, Any], offers: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """PURE: one item's table row from its db fields and its shop offers ({key, map, x, y,
    listed, discount, floating})."""
    vb, vs, notes = effective_prices(it.get("buy_db"), it.get("sell_db"))
    sellable = not it.get("no_sell")
    if not sellable:
        notes.append("Trade NoSell: no NPC buys it (pc.cpp:1307)")
    offs = []
    for o in offers:
        p = shop_price(int(o["listed"]), vb)
        offs.append({**o, "price": p, "price_dc": discount(p) if o["discount"] else p})
    best = min(offs, key=lambda o: (o["price"], o["floating"], o["key"])) if offs else None
    best_dc = min(offs, key=lambda o: (o["price_dc"], o["floating"], o["key"])) if offs else None
    return {
        "aegis": it.get("aegis"), "name": it.get("name"), "type": it.get("type"),
        "subtype": it.get("subtype"),
        "weight": it["weight_db"] / 10, "weight_db": it["weight_db"],
        "value_buy": vb, "value_sell": vs,
        "sell": vs if sellable else 0,
        "sell_oc10": overcharge(vs) if sellable else 0,
        "npc_buy": best["price"] if best else None,
        "npc_buy_dc10": best_dc["price_dc"] if best_dc else None,
        "shops": [o["key"] for o in sorted(offs, key=lambda o: (o["price"], o["key"]))][:6],
        "n_shops": len(offs), "sellable": sellable, "notes": notes,
    }  # fmt: skip


# --- building (reads the pinned tree; not pure) --------------------------------------------------


def _shops(world: Any) -> tuple[list[dict[str, Any]], dict[int, list[dict[str, Any]]]]:
    """The loaded shops (placed and floating; a placed duplicate of a shop is a shop at its own
    cell) and, per item id, its offers."""
    placed: list[dict[str, Any]] = []
    offers: dict[int, list[dict[str, Any]]] = {}
    for r in world.recs:
        src = world.source(r) if r.type == "duplicate" else r
        if src is None or src.type != "shop" or src.w2.strip().lower() != "shop":
            continue
        floating = r.w1.strip() == "-"
        disc, entries = shop_entries(src.w4)
        where = r.w1.split(",")
        cell = (int(where[1]), int(where[2])) if not floating else (None, None)
        row = {"key": r.key, "map": None if floating else where[0].strip(), "x": cell[0],
               "y": cell[1], "discount": disc, "floating": floating,
               "items": [i for i, _ in entries]}  # fmt: skip
        placed.append(row)
        for iid, listed in entries:
            offers.setdefault(iid, []).append({"key": r.key, "map": row["map"], "x": cell[0],
                                               "y": cell[1], "listed": listed, "discount": disc,
                                               "floating": floating})  # fmt: skip
    return placed, offers


def drop_maps(world: Any, mob_text: str, by_aegis: Mapping[str, int],
              maps: Iterable[str] | None) -> dict[int, dict[str, list[int]]]:  # fmt: skip
    """item id -> {map: [mob ids whose normal drops include it]} for the maps' spawn lines (every
    map with a loaded spawn line when ``maps`` is None)."""
    import kb_first_workflow as kf
    import yaml

    doc = yaml.load(mob_text, Loader=getattr(yaml, "CSafeLoader", yaml.SafeLoader))  # noqa: S506
    drops = {int(e["Id"]): [str(d.get("Item")) for d in e.get("Drops") or []]
             for e in doc["Body"]}  # fmt: skip
    out: dict[int, dict[str, list[int]]] = {}
    want = None if maps is None else set(maps)
    for r in world.recs:
        if r.type != "monster" or (want is not None and r.map not in want):
            continue
        mid = kf.spawn_entry(r, world.sprites.mobs)["id"]
        for aegis in drops.get(mid, []):
            iid = by_aegis.get(aegis)
            if iid is not None:
                lst = out.setdefault(iid, {}).setdefault(str(r.map), [])
                if mid not in lst:
                    lst.append(mid)
    return out


def build(src_root: Path = SRC, maps: Sequence[str] | None = None) -> dict[str, Any]:
    import kb_first_workflow as kf

    src = kf.Src(src_root)
    items: dict[int, dict[str, Any]] = {}
    for p in ITEM_DBS:
        items.update(parse_item_db(src.read(p)))
    world = kf.build_world(src)
    placed, offers = _shops(world)
    by_aegis = {str(v["aegis"]): k for k, v in items.items() if v.get("aegis")}
    dm = drop_maps(world, src.read(MOB_DB), by_aegis, maps)
    table = {}
    for iid, it in sorted(items.items()):
        row = price_item(it, offers.get(iid, []))
        row["drops_on"] = dm.get(iid, {})
        table[str(iid)] = row
    return {
        "meta": {
            "rathena_ref": src.ref, "mode": "pre-re", "oc_level": OC_LV, "dc_level": DC_LV,
            "built_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "maps": "every map with a loaded spawn line" if maps is None else list(maps),
            "units": "weight = in-game weight (db Weight / 10); prices in zeny per unit",
            "inputs": dict(sorted(src.hashes.items())),
            "npc_files": len(world.files),
        },
        "shops": placed,
        "items": table,
    }  # fmt: skip


def load(path: Path = OUT) -> dict[str, Any]:
    """The built table (``build`` first). Raises FileNotFoundError with the command to run."""
    if not path.exists():
        raise FileNotFoundError(f"{path} missing: run scripts/econ_items.py build")
    doc: dict[str, Any] = json.loads(path.read_text())
    return doc


def lookup(table: Mapping[str, Any], key: str) -> tuple[str, Mapping[str, Any]] | None:
    """An item by id or AegisName (case-insensitive)."""
    items = table["items"]
    if key.isdigit() and key in items:
        return key, items[key]
    low = key.lower()
    for k, v in items.items():
        if str(v.get("aegis") or "").lower() == low:
            return k, v
    return None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)  # fmt: skip
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build")
    b.add_argument("--src", type=Path, default=SRC)
    b.add_argument("--out", type=Path, default=OUT)
    s = sub.add_parser("show")
    s.add_argument("keys", nargs="+")
    s.add_argument("--items", type=Path, default=OUT)
    a = ap.parse_args()
    if a.cmd == "build":
        doc = build(a.src)
        a.out.parent.mkdir(parents=True, exist_ok=True)
        tmp = a.out.with_suffix(".part")
        tmp.write_text(json.dumps(doc, ensure_ascii=False, separators=(",", ":")) + "\n")
        tmp.replace(a.out)
        back = json.loads(a.out.read_text())  # read back
        print(json.dumps({"out": str(a.out), "items": len(back["items"]),
                          "shops": len(back["shops"]),
                          "sha256": hashlib.sha256(a.out.read_bytes()).hexdigest()[:16],
                          "dropping_on_maps": sum(1 for v in back["items"].values()
                                                  if v["drops_on"])}, indent=1))  # fmt: skip
        return 0
    table = load(a.items)
    for k in a.keys:
        hit = lookup(table, k)
        if hit is None:
            print(f"{k}: not in the table")
            continue
        iid, it = hit
        print(json.dumps({"id": int(iid), **it}, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
