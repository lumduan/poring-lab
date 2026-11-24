"""THE ITEM TALLY (Batt 2026-11-24: "count the items as they come in, live on /flows and in the
Run's log; the count after the Run only adjusts it -- so a Run ended by HUMAN still has its real
count").

During a Run the item popup reader (scripts/item_popup.py, docs/planning/item-popup-reader.md)
watches the popup the client shows for every item gained (a pickup or a Steal): its own grab of the
popup's band on the REAL frame (its own screen pipe, never the runner's), four times a second. Each
popup it reads is one gain: the item (its icon) and the amount (its count font; None when the count
does not read, e.g. another client's digits -- counted as 1 and said so). DISPLAY AND RECORD ONLY:
nothing the Run decides reads it, and any failure only stops the tally (a WARNING), never the Run.

At the Run's end the bag census (bag_count.py, when it ran) is the truth; ``adjust`` puts the two
side by side. Without an end census (a stop by HUMAN, a death, an error) the tally stands as the
Run's count (econ_bag.run_from_tally).
"""

from __future__ import annotations

import contextlib
import threading
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
COUNT_FONT = ROOT / "data" / "ui_anchors" / "item_popup_count_r4.npz"
JOIN_S = 10.0  # the watcher thread's join at the end (it stops within one grab period)


def key_of(ids: Sequence[int] | None) -> str | None:
    """PURE: the tally's key of a popup's ids -- bag_count's group key ("602|12324": items whose
    pictures are alike, in the pictures' own order, as bag_count joins them), so the tally and the
    census name the same rows. None: no item read."""
    if not ids:
        return None
    return "|".join(str(int(i)) for i in ids)


class Tally:
    """The items gained so far (thread-safe): per key, the count; the gains whose amount did not
    read (each counted as 1); the popups with no item read."""

    def __init__(self, names: Mapping[int, str] | None = None) -> None:
        self.lock = threading.Lock()
        self.counts: dict[str, int] = {}
        self.no_amount: dict[str, int] = {}
        self.unread = 0
        self.gains = 0
        self.names = dict(names or {})

    def name(self, key: str) -> str:
        parts: list[str] = []
        for i in key.split("|"):
            n = self.names.get(int(i)) or f"item {i}"
            if n not in parts:
                parts.append(n)
        return " / ".join(parts)

    def add(self, ids: Sequence[int] | None, amount: int | None) -> dict[str, Any]:
        """One popup: its record for the Run's events (kind item_gained)."""
        key = key_of(ids)
        with self.lock:
            self.gains += 1
            if key is None:
                self.unread += 1
                return {"kind": "item_gained", "key": None, "ids": None, "name": None,
                        "amount": amount, "counted": 0, "total": sum(self.counts.values()),
                        "unread": self.unread}  # fmt: skip
            n = int(amount) if amount is not None and amount > 0 else 1
            self.counts[key] = self.counts.get(key, 0) + n
            if amount is None:
                self.no_amount[key] = self.no_amount.get(key, 0) + 1
            return {"kind": "item_gained", "key": key, "ids": [int(i) for i in key.split("|")],
                    "name": self.name(key), "amount": amount, "counted": n,
                    "count": self.counts[key], "total": sum(self.counts.values())}  # fmt: skip

    def doc(self) -> dict[str, Any]:
        with self.lock:
            return {"counts": dict(self.counts), "no_amount": dict(self.no_amount),
                    "unread": self.unread, "gains": self.gains,
                    "total": sum(self.counts.values()),
                    "names": {k: self.name(k) for k in self.counts}}  # fmt: skip


def words(rec: Mapping[str, Any]) -> str:
    """PURE: a gain in the Run's log: "+ Zargon x1 (Zargon 12 in all)"; an unread amount counts as
    1 and says so; a popup with no item read says that."""
    if rec.get("key") is None:
        return "+ an item (its picture did not read)"
    amt = rec.get("amount")
    a = f"x{amt}" if amt is not None else "x1 (its amount did not read)"
    return f"+ {rec.get('name')} {a} ({rec.get('name')} {rec.get('count')} in all)"


def adjust(tally: Mapping[str, int], census: Mapping[str, int]) -> dict[str, Any]:
    """PURE: the tally beside the census's change (both per key, the items that rose): per key
    (popups, bag), and what the bag adds (it saw more) or takes away (the popups said more)."""
    keys = sorted(set(tally) | {k for k, v in census.items() if v > 0})
    rows = {k: [int(tally.get(k, 0)), max(0, int(census.get(k, 0)))] for k in keys}
    return {"rows": rows,
            "popups": sum(r[0] for r in rows.values()), "bag": sum(r[1] for r in rows.values()),
            "same": [k for k, r in rows.items() if r[0] == r[1]],
            "bag_more": {k: r[1] - r[0] for k, r in rows.items() if r[1] > r[0]},
            "popups_more": {k: r[0] - r[1] for k, r in rows.items() if r[0] > r[1]}}  # fmt: skip


def adjust_words(adj: Mapping[str, Any]) -> str:
    """PURE: the end's adjustment in a line of the Run's log."""
    if adj["popups"] == adj["bag"] and not adj["bag_more"]:
        return f"the bag's count agrees with the popups: {adj['bag']} item(s)"
    return (f"the bag's count sets the items gained: {adj['bag']} (the popups counted "
            f"{adj['popups']}; the bag has more of {len(adj['bag_more'])} kind(s), fewer of "
            f"{len(adj['popups_more'])})")  # fmt: skip


def ready(count_font: Path = COUNT_FONT) -> str | None:
    """Why the tally cannot run on this install (None: it can): the reader's pictures
    (slot_items' refs.npz) and its count font must be here (both made from this install's client:
    never committed)."""
    import slot_items as si

    def shown(p: Path) -> str:
        try:
            return str(Path(p).relative_to(ROOT))
        except ValueError:  # a folder outside the repo: its whole path
            return str(p)

    if not Path(si.REFS).exists():
        return f"no item pictures ({shown(si.REFS)}: slot_items build)"
    if not count_font.exists():
        return f"no popup count font ({shown(count_font)})"
    return None


class Watch:
    """The popup watcher as a thread for one Run: its own screen pipe (ro_agent.Screen: one pipe a
    thread), the band of the real frame, item_popup.watch's loop; each final event -> the tally ->
    ``emit(record)``. ``start`` and ``stop`` never raise; a failure is ``self.error``."""

    def __init__(self, out_dir: Path, emit: Callable[[dict[str, Any]], None],
                 count_font: Path = COUNT_FONT,
                 screen_fn: Callable[[], Any] | None = None,
                 region_fn: Callable[[], Sequence[int]] | None = None) -> None:  # fmt: skip
        self.out_dir, self.emit, self.count_font = out_dir, emit, count_font
        self.screen_fn, self.region_fn = screen_fn, region_fn
        self.halt = threading.Event()
        self.th: threading.Thread | None = None
        self.tally: Tally | None = None
        self.error: str | None = None
        self.summary: dict[str, Any] | None = None
        self.screen: Any = None

    def start(self) -> str | None:
        """Start it (None), or why not (it never starts then)."""
        try:
            import item_popup as ip
            import ro_agent as r

            icons = ip.Icons.load(None)
            font = ip.load_count(self.count_font)
            self.tally = Tally(icons.names)
            region = self.region_fn() if self.region_fn else r.real_game_region()
            box = ip.band_box(region)
            self.screen = self.screen_fn() if self.screen_fn else r.Screen()
            tracker = ip.Tracker(icons, font)
        except Exception as e:  # noqa: BLE001 -- the tally only: the Run plays on
            self.error = f"{type(e).__name__}: {str(e)[:200]}"
            return self.error
        tally, emit, screen = self.tally, self.emit, self.screen

        def on_event(ev: Any) -> None:
            emit(tally.add(ev.ids, ev.amount))

        def loop() -> None:
            try:
                self.summary = ip.watch(self.out_dir, lambda: screen.grab(*box), tracker,
                                        self.halt.is_set, emit=on_event)  # fmt: skip
            except Exception as e:  # noqa: BLE001
                self.error = f"{type(e).__name__}: {str(e)[:200]}"

        self.th = threading.Thread(target=loop, name="item-tally", daemon=True)
        self.th.start()
        return None

    def stop(self) -> dict[str, Any] | None:
        """Stop it and close its screen; the tally's doc (None: it never ran)."""
        self.halt.set()
        if self.th is not None:
            self.th.join(JOIN_S)
        if self.screen is not None:
            with contextlib.suppress(Exception):
                self.screen.close()
        return None if self.tally is None else self.tally.doc()
