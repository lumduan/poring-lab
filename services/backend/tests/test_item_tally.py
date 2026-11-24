"""The item tally (scripts/item_tally.py; Batt 2026-11-24: "count the items as they come in, live
on /flows and in the Run's log; the count after the Run only adjusts it")."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace as NS
from typing import Any

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts"))

import econ_bag  # noqa: E402
import flow_run as fr  # noqa: E402
import item_popup as ip  # noqa: E402
import item_tally as it  # noqa: E402


class _Marked(ip.Tracker):
    """The Tracker's rules on bands whose first pixel names the item (test_item_popup's)."""

    def read(self, frame_rgb: Any, p: Any) -> Any:
        k = int(frame_rgb[ip.BAND[1], ip.BAND[0], 0])
        return ip.FrameRead(ip.ItemRead((k,), 3.0, None, "ok"), 1, 180)


def test_a_gain_is_keyed_as_the_bag_count_keys_it_and_counted_by_its_amount() -> None:
    assert it.key_of([602, 12324]) == "602|12324" and it.key_of((911,)) == "911"
    assert it.key_of(None) is None and it.key_of([]) is None
    t = it.Tally({911: "Scell", 912: "Zargon", 602: "Butterfly Wing", 12324: "Wing B"})
    r1 = t.add((911,), 1)
    assert r1 == {"kind": "item_gained", "key": "911", "ids": [911], "name": "Scell", "amount": 1,
                  "counted": 1, "count": 1, "total": 1}  # fmt: skip
    r2 = t.add((911,), 3)
    assert (r2["count"], r2["total"]) == (4, 4)
    r3 = t.add((912,), None)  # the amount did not read: one, said so
    assert (r3["counted"], r3["amount"], r3["total"]) == (1, None, 5)
    r4 = t.add(None, 2)  # the item did not read: not counted
    assert r4["key"] is None and r4["counted"] == 0 and r4["unread"] == 1
    assert t.add((602, 12324), 1)["name"] == "Butterfly Wing / Wing B"
    doc = t.doc()
    assert doc["counts"] == {"911": 4, "912": 1, "602|12324": 1} and doc["total"] == 6
    assert doc["no_amount"] == {"912": 1} and doc["unread"] == 1 and doc["gains"] == 5
    assert doc["names"]["912"] == "Zargon" and it.Tally().name("4001") == "item 4001"


def test_the_log_line_of_a_gain() -> None:
    t = it.Tally({912: "Zargon"})
    assert it.words(t.add((912,), 1)) == "+ Zargon x1 (Zargon 1 in all)"
    unread = "+ Zargon x1 (its amount did not read) (Zargon 2 in all)"
    assert it.words(t.add((912,), None)) == unread
    assert it.words(t.add(None, None)) == "+ an item (its picture did not read)"


def test_the_end_count_adjusts_the_tally() -> None:
    adj = it.adjust({"911": 5, "912": 2, "538": 1}, {"911": 5, "912": 3, "601": -2, "507": 1})
    assert adj["rows"] == {"507": [0, 1], "538": [1, 0], "911": [5, 5], "912": [2, 3]}
    assert (adj["popups"], adj["bag"]) == (8, 9)
    assert adj["same"] == ["911"] and adj["bag_more"] == {"507": 1, "912": 1}
    assert adj["popups_more"] == {"538": 1}  # a used item (601 fell) is no gain either way
    assert it.adjust_words(adj).startswith("the bag's count sets the items gained: 9 (the popups "
                                            "counted 8")  # fmt: skip
    same = it.adjust({"911": 2}, {"911": 2})
    assert it.adjust_words(same) == "the bag's count agrees with the popups: 2 item(s)"


def test_the_watcher_emits_each_final_event_and_a_failing_emit_never_stops_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """item_popup.watch hands each FINAL event to ``emit`` as it writes it."""

    bx, by = ip.BAND[0], ip.BAND[1]

    def box_of(f: Any) -> Any:
        return None if f[by, bx, 0] == 0 else ip.Popup(541, 720, b"")

    monkeypatch.setattr(ip, "box_of", box_of)
    seq = [0, 5, 5, 0, 7, 7]
    frames = iter(enumerate(seq))
    done = [False]

    def grab() -> Any:
        try:
            t, k = next(frames)
        except StopIteration:
            done[0] = True
            return 99, np.zeros((38, 536, 4), np.uint8)
        band = np.zeros((38, 536, 4), np.uint8)
        band[0, 0, :3] = k
        return t, band

    got: list[Any] = []

    def emit(e: Any) -> None:
        got.append(e.ids)
        raise RuntimeError("the display broke")  # never the watcher's

    clock = iter(range(0, 10**6))
    out = ip.watch(tmp_path / "w", grab, _Marked(None, None), lambda: done[0],  # type: ignore[arg-type]
                   sleep=lambda s: None, clock=lambda: float(next(clock)) / 100,
                   emit=emit)  # fmt: skip
    assert got == [(5,), (7,)] and out["events"] == 2


def test_watch_tallies_the_reader_s_events_on_its_own_screen_and_stops_cleanly(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    icons = NS(names={911: "Scell"})
    monkeypatch.setattr(ip.Icons, "load", classmethod(lambda cls, path=None: icons))
    monkeypatch.setattr(ip, "load_count", lambda p: "font")
    monkeypatch.setattr(ip, "Tracker", lambda i, f: ("tracker", i, f))
    grabbed: list[Any] = []

    def watch(out_dir: Path, grab: Any, tracker: Any, stop: Any, **kw: Any) -> dict[str, Any]:
        assert tracker == ("tracker", icons, "font")
        grabbed.append(grab())
        for ids, amount in (((911,), 1), ((911,), None)):
            kw["emit"](NS(ids=ids, amount=amount))
        while not stop():
            pass
        return {"events": 2}

    monkeypatch.setattr(ip, "watch", watch)
    screen = NS(grab=lambda *box: ("grab", box), close=lambda: grabbed.append("closed"))
    recs: list[dict[str, Any]] = []
    w = it.Watch(tmp_path / "popups", recs.append, tmp_path / "font.npz",
                 screen_fn=lambda: screen, region_fn=lambda: (0, 0, 1920, 1080))  # fmt: skip
    assert w.start() is None
    doc = w.stop()
    assert grabbed[0] == ("grab", ip.band_box((0, 0, 1920, 1080))) and grabbed[-1] == "closed"
    assert [r["count"] for r in recs] == [1, 2] and recs[1]["amount"] is None
    assert doc is not None and doc["counts"] == {"911": 2} and doc["no_amount"] == {"911": 1}
    assert w.summary == {"events": 2} and w.error is None


def test_a_tally_that_cannot_start_says_why_and_never_raises(tmp_path: Path,
                                                             monkeypatch: pytest.MonkeyPatch,
                                                             ) -> None:  # fmt: skip
    def broken(cls: Any, path: Any = None) -> Any:
        raise OSError("no refs.npz")

    monkeypatch.setattr(ip.Icons, "load", classmethod(broken))
    w = it.Watch(tmp_path / "popups", lambda r: None, screen_fn=lambda: None,
                 region_fn=lambda: (0, 0, 1280, 720))  # fmt: skip
    assert w.start() == "OSError: no refs.npz" and w.stop() is None
    import slot_items as si

    monkeypatch.setattr(si, "REFS", tmp_path / "none.npz")
    assert "no item pictures" in str(it.ready(tmp_path / "font.npz"))


def test_the_economy_from_the_tally_when_no_end_count_came() -> None:
    s = 10**9
    events = [{"kind": "run_start", "t_ns": 0, "map": "xmas_dun02", "version": "1"},
              {"kind": "kill", "t_ns": 5 * s}, {"kind": "kill", "t_ns": 6 * s},
              {"kind": "run_end", "t_ns": 1800 * s}]  # fmt: skip
    doc = {"counts": {"911": 4, "912": 1}, "no_amount": {"912": 1}, "unread": 2, "gains": 7}
    table = {"911": {"name": "Scell", "sell": 80, "type": "etc", "weight": 1},
             "912": {"name": "Zargon", "sell": 240, "type": "etc", "weight": 1}}  # fmt: skip
    run = econ_bag.run_from_tally(doc, events, table, {"911": "Scell"}, session="r1")
    assert run["counted_by"] == "popups" and run["kills"] == 2 and run["minutes"] == 30.0
    assert [(r["item_id"], r["income"], r["picked"]) for r in run["items"]] == [
        (911, 4, 4),
        (912, 1, 1),
    ]
    assert "amounts_unread" in run["why"] and "items_unread" in run["why"]
    assert run["consumables"] == []


def test_the_live_page_tallies_the_gains_and_shows_the_end_count() -> None:
    lv = fr.Live()
    assert "items" not in lv.summary()  # no tally in this Run: nothing shown
    for e in ({"kind": "run_start", "t_ns": 0},
              {"kind": "item_gained", "t_ns": 10**9, "key": "911", "name": "Scell", "amount": 1,
               "counted": 1},
              {"kind": "item_gained", "t_ns": 2 * 10**9, "key": "911", "name": "Scell",
               "amount": None, "counted": 1},
              {"kind": "item_gained", "t_ns": 3 * 10**9, "key": "912", "name": "Zargon",
               "amount": 3, "counted": 3},
              {"kind": "item_gained", "t_ns": 4 * 10**9, "key": None, "counted": 0}):  # fmt: skip
        lv.feed(e)
    s = lv.summary()
    assert s["items"] == [["912", "Zargon", 3], ["911", "Scell", 2]]
    assert (s["items_total"], s["items_kinds"], s["items_unread"]) == (5, 2, 1)
    words = [x["words"] for x in s["story"]]
    assert "+ Scell x1" in words and "+ Scell x1 (amount unread)" in words
    assert "+ Zargon x3" in words and "gains an item (its picture did not read)" in words
    lv.feed({"kind": "items_adjust", "t_ns": 5 * 10**9, "bag": 6, "popups": 5,
             "bag_more": {"911": 1}, "popups_more": {}})  # fmt: skip
    assert lv.summary()["items_census"]["bag"] == 6
    assert any("the bag's count at the end: 6" in x["words"] for x in lv.summary()["story"])


def test_events_json_roundtrip_of_a_gain() -> None:
    rec = it.Tally({911: "Scell"}).add((911,), 2)
    assert json.loads(json.dumps(rec)) == rec
