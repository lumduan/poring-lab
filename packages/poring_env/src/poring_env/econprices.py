"""The /economy page's saved prices (Batt 2026-11-21: "a drop whose price is unknown: leave it blank
or 0 for the user to type, and the system remembers it when Update is pressed, so next time it
need not be typed again").

``settings/econ-prices.json`` holds a person's own NPC prices per item id, in the page's
``PriceEdits`` shape: ``sell`` (what an NPC pays) and ``buy`` (what an NPC asks). Each is
``{"<item id>": zeny per unit}``. They override the item table's prices on every device and visit.
The backend's routes_econprices.py is the only writer, behind the Settings write gate. PURE.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

FILE_NAME = "econ-prices.json"
VERSION = 1
MAX_ENTRIES = 5000  # a side
MAX_PRICE = 1_000_000_000
MAX_ID = 99_999


@dataclass(frozen=True)
class Store:
    revision: int = 0
    sell: dict[str, int] = field(default_factory=dict)
    buy: dict[str, int] = field(default_factory=dict)

    def as_json(self) -> dict[str, Any]:
        return {"revision": self.revision, "sell": dict(self.sell), "buy": dict(self.buy)}


DEFAULT = Store()


def side_problem(side: Any, name: str) -> str | None:
    """PURE: why a side is not {"<id>": price}, or None."""
    if not isinstance(side, dict):
        return f"{name} is not an object"
    if len(side) > MAX_ENTRIES:
        return f"{name} holds more than {MAX_ENTRIES} prices"
    for k, v in side.items():
        if not (isinstance(k, str) and k.isdigit() and 1 <= int(k) <= MAX_ID and str(int(k)) == k):
            return f"{name}: {str(k)[:12]!r} is not an item id"
        if isinstance(v, bool) or not isinstance(v, int) or not 0 <= v <= MAX_PRICE:
            return f"{name}[{k}]: a price is a whole zeny amount 0..{MAX_PRICE}"
    return None


def parse(text: str) -> Store | str:
    """PURE: the store, or why not."""
    try:
        d = json.loads(text)
    except ValueError:
        return "not JSON"
    if not isinstance(d, dict) or d.get("version") != VERSION:
        return f"not version {VERSION}"
    rev = d.get("revision")
    if isinstance(rev, bool) or not isinstance(rev, int) or rev < 0:
        return "revision is not a whole number"
    sell, buy = d.get("sell", {}), d.get("buy", {})
    why = side_problem(sell, "sell") or side_problem(buy, "buy")
    return why if why else Store(rev, dict(sell), dict(buy))


def dumps(s: Store) -> str:
    return json.dumps({"version": VERSION, **s.as_json()}, sort_keys=True, indent=1) + "\n"
