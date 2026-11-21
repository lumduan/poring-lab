"""The item popup reader (docs/planning/item-popup-reader.md; Batt 2026-11-21): the count by the
text's constant tail, the icon pick, and the scorer's match rule and bars. Synthetic pixels only
(client pixels are never committed)."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts"))

import item_popup as ip  # noqa: E402
import item_popup_eval as ev  # noqa: E402

RNG = np.random.default_rng(3)
GLYPH = {ch: RNG.random((ip.TEXT_ROWS[1] - ip.TEXT_ROWS[0], 5)) > 0.45 for ch in "0123456789abc"}
for g in GLYPH.values():
    g[:, 0] = g[:, -1] = True  # every glyph spans its 5 columns


def box(text: str) -> np.ndarray:
    """A white box crop with ``text`` drawn as glyph runs (" " = 4 blank columns)."""
    b = np.full((34, 260, 3), 255, np.uint8)
    x = ip.TEXT_X
    for ch in text:
        if ch == " ":
            x += 4
            continue
        g = GLYPH[ch]
        b[ip.TEXT_ROWS[0] : ip.TEXT_ROWS[1], x : x + g.shape[1]][g] = 0
        x += g.shape[1] + 1
    return b


def test_the_tail_is_what_every_amount_shares_and_the_count_is_left_of_it() -> None:
    boxes = [box("ab 1 cab"), box("ba 1 cab"), box("a 10 cab"), box("bb 1 cab"), box("ab 3 cab")]
    font = ip.learn_count(boxes, [1, 1, 10, 1, 3])
    assert len(font.tail) == 3 and sorted(font.digits) == ["0", "1", "3"]
    assert ip.read_count(box("ba 31 cab"), font) == 31
    assert ip.read_count(box("ab 2 cab"), font) is None  # a digit never learned: unread
    assert ip.read_count(box("ab 1 bab"), font) is None  # no tail: nothing read
    # one amount alone cannot tell its digit from the words: no tail, nothing read
    assert ip.learn_count([box("ab 1 cab"), box("ba 1 cab")], [1, 1]).tail == []


def test_the_icon_pick_needs_a_near_picture_and_a_clear_margin() -> None:
    rgb = np.zeros((3, 24, 24, 3), np.float32)
    rgb[0, ..., 0] = 200
    rgb[1, ..., 1] = 200
    rgb[2, ..., 1] = 195  # nearly the same picture as 1, another item
    icons = ip.Icons(rgb, np.ones((3, 24, 24), bool), ((501,), (912,), (913,)))
    sq = np.zeros((24, 24, 3), np.uint8)
    sq[..., 0] = 202
    got = icons.read(sq)
    assert got.ids == (501,) and got.why == "ok"
    sq2 = np.zeros((24, 24, 3), np.uint8)
    sq2[..., 1] = 198
    assert icons.read(sq2).why == "ambiguous"
    assert icons.read(np.full((24, 24, 3), 255, np.uint8)).why == "far"
    assert icons.read(np.zeros((10, 24, 3), np.uint8)).why == "off_frame"


def test_the_match_rule_and_the_bars() -> None:
    s = 10**9
    truth = [{"t": 10 * s, "id": 912, "amount": 1}, {"t": 11 * s, "id": 501, "amount": 1},
             {"t": 30 * s, "id": 912, "amount": 1}]  # fmt: skip
    events = [{"t": int(10.4 * s), "ids": [912], "amount": 1},
              {"t": int(11.5 * s), "ids": [502], "amount": None},
              {"t": 50 * s, "ids": [912], "amount": 1}]  # fmt: skip
    got = ev.match(events, truth)
    assert (got["matched"], got["id_ok"], got["amount_ok"], got["amount_unread"]) == (2, 1, 1, 1)
    assert got["P_false"] == 1 / 3 and got["R_spaced"] == 1 / 2  # truth 2 is 1 s after truth 1
    v = ev.verdict({"I1_id": 0.98, "I2_amount": 0.96, "P_false": 0.01, "R_spaced": None})
    assert v == {
        "I1_id": "PASS",
        "I2_amount": "FAIL",
        "P_false": "PASS",
        "R_spaced": "INCONCLUSIVE",
    }


# --- round 2 (item-popup-reader.md Amendment 2): one event per popup shown ----------------------
class _Scripted(ip.Tracker):
    """The Tracker's rules on scripted reads: a frame is None (no box) or (ids, amount, width)."""

    def read(self, frame_rgb, p):  # type: ignore[no-untyped-def]
        ids, amount, width = frame_rgb
        item = ip.ItemRead(ids, 5.0 if ids else None, None, "ok" if ids else "far")
        return ip.FrameRead(item, amount, width)


def _run(seq, monkeypatch):  # type: ignore[no-untyped-def]
    monkeypatch.setattr(ip, "box_of", lambda f: None if f is None else ip.Popup(541, 700, b""))
    tr, out = _Scripted(None, None), []  # type: ignore[arg-type]
    for t, f in enumerate(seq):
        out += tr.feed(t, f)
    return out + tr.flush()


def test_round2_one_event_per_popup_shown(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    seq = [None, ((912,), 1, 180), ((912,), 1, 180),
           ((912,), None, 150),  # a cover cut its top edge: no tail, the same popup
           ((912,), 1, 180), None,  # it left the screen
           ((912,), 1, 180),  # the same item again after it left: a new event
           (None, None, 180),  # a cover over the icon: the same popup
           ((501,), 1, 200),  # another item: new
           ((501,), 3, 220)]  # another TRUE width (both read their tail): new  # fmt: skip
    got = _run(seq, monkeypatch)
    assert [(e.t, e.ids, e.amount, e.frames) for e in got] == [
        (1, (912,), 1, 4), (6, (912,), 1, 2), (8, (501,), 1, 1), (9, (501,), 3, 1)]  # fmt: skip


def test_round2_a_later_frame_fills_an_unread_first_read(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    got = _run([(None, None, 150), ((912,), 1, 180), ((913,), 1, 180)], monkeypatch)
    # the first read wins once made: 913 on the third frame is another item, a new event
    assert [(e.ids, e.amount, e.width, e.filled) for e in got] == [
        ((912,), 1, 180, ["item", "amount"]), ((913,), 1, 180, [])]  # fmt: skip


def test_text_box_is_the_boxs_own_columns() -> None:
    f = np.zeros((200, 1280, 3), np.uint8)
    b = ip.text_box(f, ip.Popup(541, 700, b""))
    assert b.shape == (ip.bs.POPUP_BOTTOM + 2 - (ip.bs.POPUP_TOP - 2), 160, 3)


def test_repeats_are_counted_apart() -> None:
    s = 10**9
    truth = [{"t": 10 * s, "id": 912, "amount": 1}, {"t": 13 * s, "id": 912, "amount": 1},
             {"t": 30 * s, "id": 912, "amount": 1}]  # fmt: skip
    got = ev.match([{"t": int(10.4 * s), "ids": [912], "amount": 1}], truth)
    assert (got["repeats"], got["repeats_found"], got["matched"]) == (1, 0, 1)
