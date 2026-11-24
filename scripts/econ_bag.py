#!/usr/bin/env python3
"""THE ECONOMY FROM THE BAG (Economy option b-i; docs/planning/econ-bag-count.md; Batt 2026-11-20:
"count the bag at the Run's start and end -- the way people do it"). One Run's entry for the
/economy page from TWO bag censuses (scripts/bag_count.py, at the Run's start and its end) and the
Run's own events (its hours, its kills) -- no packets, so any server.

    econ_bag.py export START.json END.json --events EVENTS.jsonl --name NAME [--data DIR]
                [--out-dir DIR]

START / END: bag_count.py census outputs ({"census": {...}} or the census itself). EVENTS: the
hunt core's events.jsonl (run_start .. run_end; its "kill" records). The entry has the page's
schema (econ_dash.SCHEMA), so the page shows it as any export:

- an item whose count ROSE is income: ``picked`` = ``income`` = the rise. The bag cannot tell a
  pickup from a Steal, so ``stolen`` is 0 and "why" says so;
- an item whose count FELL is used: a consumables row, ``used`` = the fall (a potion drunk, a
  Fly Wing flown). A non-consumable that fell (dropped, sold) is listed in "why", not priced;
- a shared icon (bag_count's group key, e.g. "602|12324") is one row: priced only when every item
  of the group has the same price, else its price is null and "why" names it;
- an unread slot in either census, or a tab full at either end (it may hold more), makes the
  change unknown for what it hid: "why" says how many, and the totals count only what was read.

Prices and names come from the same tables as econ_dash (data/econ/items.json, data/kb): written to
data/ only, never committed.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
NS = 1_000_000_000
CONSUMABLE_TYPES = frozenset({"healing", "usable", "delayconsume", "cash"})


def census_of(doc: Mapping[str, Any]) -> Mapping[str, Any]:
    return doc.get("census", doc)


def changes(start: Mapping[str, int], end: Mapping[str, int]) -> dict[str, int]:
    """PURE: per bag key, end - start (0s left out)."""
    keys = set(start) | set(end)
    out = {k: int(end.get(k, 0)) - int(start.get(k, 0)) for k in keys}
    return {k: v for k, v in out.items() if v}


def _ids(key: str) -> list[int]:
    return [int(i) for i in key.split("|")]


def consumable(key: str, table: Mapping[str, Mapping[str, Any]]) -> bool:
    """PURE: every item of the key is a consumable (by the table's type)."""
    types = {str((table.get(str(i)) or {}).get("type", "")).lower() for i in _ids(key)}
    return bool(types) and types <= CONSUMABLE_TYPES


def one_price(key: str, table: Mapping[str, Mapping[str, Any]], field: str) -> int | None:
    """PURE: the group's price in ``field`` when every item has the same one, else None."""
    vals = {(table.get(str(i)) or {}).get(field) for i in _ids(key)}
    if len(vals) != 1:
        return None
    v = next(iter(vals))
    return None if v is None else int(v)


def _name(key: str, names: Mapping[str, str], table: Mapping[str, Mapping[str, Any]]) -> str:
    parts = []
    for i in _ids(key):
        n = names.get(str(i)) or (table.get(str(i)) or {}).get("name") or f"item {i}"
        if n not in parts:
            parts.append(str(n))
    return " / ".join(parts)


def window(events: Sequence[Mapping[str, Any]]) -> tuple[int, int] | None:
    """PURE: (run_start, run_end) t_ns, or None."""
    t0 = next((int(e["t_ns"]) for e in events if e.get("kind") == "run_start"), None)
    t1 = next((int(e["t_ns"]) for e in reversed(events) if e.get("kind") == "run_end"), None)
    if t0 is None or t1 is None or t1 <= t0:
        return None
    return t0, t1


def run_from_bags(
    start: Mapping[str, Any],
    end: Mapping[str, Any],
    events: Sequence[Mapping[str, Any]],
    table: Mapping[str, Mapping[str, Any]],
    names: Mapping[str, str],
    session: str | None = None,
) -> dict[str, Any]:
    """PURE: the /economy run entry (econ_dash's schema) from two censuses and the events."""
    import econ_dash as ed
    import econ_row as er

    a, b = census_of(start), census_of(end)
    win = window(events)
    if win is None:
        raise ValueError("the events have no run_start .. run_end window")
    why: dict[str, Any] = {
        "source": "the bag's change between two censuses (bag_count.py) at the Run's start and "
        "end: no packets; a pickup and a Steal look alike (stolen = 0)",
    }
    unread = int(a.get("unread") or 0) + int(b.get("unread") or 0)
    if unread:
        why["unread_slots"] = (f"{unread} bag slot(s) unread at the start / end: what they hid "
                               "is not counted")  # fmt: skip
    full = sorted(set(a.get("full_tabs") or []) | set(b.get("full_tabs") or []))
    if full:
        why["full_tabs"] = f"tab(s) {full} full at a census: they may hold more, not counted"
    ch = changes(a.get("totals") or {}, b.get("totals") or {})
    items, cons, lost, unpriced = [], [], {}, []
    for key, n in sorted(ch.items()):
        ids = _ids(key)
        t0 = table.get(str(ids[0]))
        if n > 0:
            sell, sell_oc = one_price(key, table, "sell"), one_price(key, table, "sell_oc10")
            if sell is None and len(ids) > 1:
                unpriced.append(key)
            items.append({
                "item_id": ids[0], "ids": ids, "name": _name(key, names, table),
                "type": None if t0 is None else t0.get("type"),
                "weight": None if t0 is None else t0.get("weight"),
                "sellable": None if t0 is None else bool(t0.get("sellable", True)),
                "sell": sell, "sell_oc": sell_oc, "picked": n, "stolen": 0, "stolen_steal": 0,
                "stolen_snatcher": 0, "income": n, "other": 0, "staged": 0, "dropped": 0,
                "picked_of_dropped": 0,
            })  # fmt: skip
        elif consumable(key, table):
            buy = one_price(key, table, "npc_buy")
            cons.append({
                "item_id": ids[0], "ids": ids, "name": _name(key, names, table),
                "type": None if t0 is None else t0.get("type"),
                "kind": er.consumable_kind(t0, ids[0]), "used": -n, "npc_buy": buy,
                "npc_buy_dc": one_price(key, table, "npc_buy_dc10") if buy is not None else None,
                "price_basis": "npc_buy" if buy is not None else None,
            })  # fmt: skip
        else:
            lost[key] = -n
    if lost:
        why["fell_not_used"] = (f"non-consumables that fell (dropped, sold, traded?): {lost}; "
                                "not priced")  # fmt: skip
    if unpriced:
        why["shared_icons_unpriced"] = (f"{unpriced}: items alike on screen with different "
                                        "prices: price null")  # fmt: skip
    items.sort(key=lambda r: (-r["income"], r["item_id"]))
    cons.sort(key=lambda r: (-r["used"], r["item_id"]))
    t0_ns, t1_ns = win
    kills = sum(1 for e in events if e.get("kind") == "kill")
    out: dict[str, Any] = {
        "session": session, "dir": None, "map": next((e.get("map") for e in events
                                                      if e.get("kind") == "run_start"), None),
        "char": None, "strategy": next((e.get("strategy") for e in events
                                        if e.get("kind") == "run_start"), None),
        "version": next((e.get("version") for e in events if e.get("kind") == "run_start"), None),
        "window": {"t0_ns": t0_ns, "t1_ns": t1_ns, "source": "the hunt's run_start .. run_end"},
        "minutes": round((t1_ns - t0_ns) / NS / 60, 1),
        "hours": (t1_ns - t0_ns) / NS / 3600,
        "hours_are": "the hunt's run_start .. run_end; every count here is divided by it",
        "kills": kills, "deaths": 0, "items": items, "species": [], "consumables": cons,
        "econ_row": {}, "econ_row_is": "none: a bag-counted run (no packets)",
        "judge_value": {}, "why": {**why, "species": "kills by the bot's own records; the "
                                   "species are not counted from the bag"},
        "counted_by": "bag",
    }  # fmt: skip
    out["totals"] = ed.totals(out)
    return out


def run_from_tally(
    tally: Mapping[str, Any],
    events: Sequence[Mapping[str, Any]],
    table: Mapping[str, Mapping[str, Any]],
    names: Mapping[str, str],
    session: str | None = None,
) -> dict[str, Any]:
    """PURE: the /economy run entry from the Run's ITEM TALLY (scripts/item_tally.py: the item
    popups read during the Run; Batt 2026-11-24) when no end census came (a stop by HUMAN, a death,
    an error). Each tallied key is income (``picked`` = ``income``; a pickup and a Steal look alike
    on the popup too); no consumables (only a census sees what was used)."""
    import econ_dash as ed

    win = window(events)
    if win is None:
        raise ValueError("the events have no run_start .. run_end window")
    why: dict[str, Any] = {
        "source": "the item popups read during the Run (item_popup.py through item_tally.py): no "
        "end census; a pickup and a Steal look alike (stolen = 0); nothing used is counted",
    }
    no_amt = {k: v for k, v in (tally.get("no_amount") or {}).items() if v}
    if no_amt:
        why["amounts_unread"] = (f"{sum(no_amt.values())} gain(s) whose amount did not read, "
                                 f"each counted as 1: {no_amt}")  # fmt: skip
    if tally.get("unread"):
        why["items_unread"] = f"{tally['unread']} popup(s) whose item did not read: not counted"
    items, unpriced = [], []
    for key, n in sorted((tally.get("counts") or {}).items()):
        if n <= 0:
            continue
        ids = _ids(key)
        t0 = table.get(str(ids[0]))
        sell, sell_oc = one_price(key, table, "sell"), one_price(key, table, "sell_oc10")
        if sell is None and len(ids) > 1:
            unpriced.append(key)
        items.append({
            "item_id": ids[0], "ids": ids, "name": _name(key, names, table),
            "type": None if t0 is None else t0.get("type"),
            "weight": None if t0 is None else t0.get("weight"),
            "sellable": None if t0 is None else bool(t0.get("sellable", True)),
            "sell": sell, "sell_oc": sell_oc, "picked": int(n), "stolen": 0, "stolen_steal": 0,
            "stolen_snatcher": 0, "income": int(n), "other": 0, "staged": 0, "dropped": 0,
            "picked_of_dropped": 0,
        })  # fmt: skip
    if unpriced:
        why["shared_icons_unpriced"] = (f"{unpriced}: items alike on screen with different "
                                        "prices: price null")  # fmt: skip
    items.sort(key=lambda r: (-r["income"], r["item_id"]))
    t0_ns, t1_ns = win
    kills = sum(1 for e in events if e.get("kind") == "kill")
    out: dict[str, Any] = {
        "session": session, "dir": None, "map": next((e.get("map") for e in events
                                                      if e.get("kind") == "run_start"), None),
        "char": None, "strategy": None,
        "version": next((e.get("version") for e in events if e.get("kind") == "run_start"), None),
        "window": {"t0_ns": t0_ns, "t1_ns": t1_ns, "source": "the Run's run_start .. run_end"},
        "minutes": round((t1_ns - t0_ns) / NS / 60, 1),
        "hours": (t1_ns - t0_ns) / NS / 3600,
        "hours_are": "the Run's run_start .. run_end; every count here is divided by it",
        "kills": kills, "deaths": 0, "items": items, "species": [], "consumables": [],
        "econ_row": {}, "econ_row_is": "none: a popup-counted run (no packets, no end census)",
        "judge_value": {}, "why": {**why, "species": "kills by the bot's own records; the "
                                   "species are not counted from the popups"},
        "counted_by": "popups",
    }  # fmt: skip
    out["totals"] = ed.totals(out)
    return out


def _read_events(path: Path) -> list[dict[str, Any]]:
    out = []
    for line in path.read_text().splitlines():
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def main(argv: list[str] | None = None) -> int:
    import econ_dash as ed

    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("cmd", choices=("export",))
    ap.add_argument("start", type=Path)
    ap.add_argument("end", type=Path)
    ap.add_argument("--events", type=Path, required=True)
    ap.add_argument("--name", required=True)
    ap.add_argument("--data", type=Path, default=DATA)
    ap.add_argument("--out-dir", type=Path, default=DATA / "econ" / "dashboard")
    a = ap.parse_args(argv)
    if not ed.valid_name(a.name):
        raise SystemExit(f"bad --name {a.name!r}")
    tpath, tdoc, names, mobs = ed.sources(a.data)
    run = run_from_bags(json.loads(a.start.read_text()), json.loads(a.end.read_text()),
                        _read_events(a.events), tdoc["items"], names,
                        session=a.events.parent.name)  # fmt: skip
    doc = ed.document([run], a.name, tpath, tdoc, names, mobs)
    doc["sources"]["judges"] = "bag_count censuses (start, end) + the hunt's events (kills, hours)"
    path = ed.write(doc, a.out_dir)
    print(json.dumps({"file": str(path), "totals": run["totals"], "why": run["why"]}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
