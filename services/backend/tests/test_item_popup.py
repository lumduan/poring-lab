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
    # round 3 (Amendment 5): pictures 1 and 2 differ by 5 levels, on no pixel by more than DIFF_PX:
    # one picture to the eye, so the read names both ids (a group), no longer "ambiguous"
    same = icons.read(sq2)
    assert (same.ids, same.why) == ((912, 913), "same")
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


# --- round 3 (item-popup-reader.md Amendment 5): the colour of one shape --------------------------
HEAL, BOLT = (221, 164, 132), (201, 196, 209)  # the two scroll seals' colours (Amendment 5)


def scrolls() -> ip.Icons:
    """Two pictures of ONE shape (a grey scroll on the key colour) that differ only on a 5 x 6
    seal at rows 3-8, columns 9-13, plus a far third picture."""
    rgb = np.zeros((3, 24, 24, 3), np.float32)
    own = np.zeros((3, 24, 24), bool)
    for k, seal in enumerate((HEAL, BOLT)):
        own[k, 2:22, 4:20] = True
        rgb[k, 2:22, 4:20] = 150
        rgb[k, 3:9, 9:14] = seal
    own[2] = True
    rgb[2] = 30
    return ip.Icons(rgb, own, ((12001, 12002), (688,), (501,)))


def popup_square(icons: ip.Icons, k: int, blend: float = 0.0, other: int = 1) -> np.ndarray:
    """Picture ``k`` as the popup shows it (over white), its seal moved ``blend`` of the way to
    picture ``other``'s."""
    sq = icons.comp[k].copy()
    sq[3:9, 9:14] = (1 - blend) * icons.comp[k][3:9, 9:14] + blend * icons.comp[other][3:9, 9:14]
    return np.clip(np.rint(sq), 0, 255).astype(np.uint8)


def test_round3_the_seal_colour_names_the_scroll() -> None:
    icons = scrolls()
    d = icons.distances(popup_square(icons, 0))
    assert d[1] - d[0] < ip.ICON_MARGIN  # inside the margin: round 2 said "ambiguous"
    heal = icons.read(popup_square(icons, 0))
    assert (heal.ids, heal.why) == ((12001, 12002), "lead")
    bolt = icons.read(popup_square(icons, 1, other=0))
    assert (bolt.ids, bolt.why) == ((688,), "lead")
    n, lead = icons.lead(popup_square(icons, 0), 0, 1)
    assert n == 30 and lead == 1.0  # the 30 seal pixels tell them apart; the read IS picture 0
    assert icons.lead(popup_square(icons, 0), 1, 0)[1] == -1.0


def test_round3_a_read_halfway_between_the_seals_stays_ambiguous() -> None:
    icons = scrolls()
    half = icons.read(popup_square(icons, 0, blend=0.5))
    assert (half.ids, half.why) == (None, "ambiguous")
    near = icons.read(popup_square(icons, 0, blend=0.2))  # lead 0.6 >= PAIR_LEAD
    assert near.ids == (12001, 12002) and near.why == "lead"


def test_round3_fewer_than_six_telling_pixels_is_one_group() -> None:
    icons = scrolls()
    icons.rgb[1, 3:9, 9:14] = HEAL  # the same seal ...
    icons.rgb[1, 3, 9:14] = BOLT  # ... but for 5 pixels: fewer than DISCRIM_MIN
    icons.__post_init__()
    got = icons.read(popup_square(icons, 0))
    assert (got.ids, got.why) == ((688, 12001, 12002), "same")


def test_round3_no_rival_inside_the_margin_is_unchanged() -> None:
    icons = scrolls()
    sq = np.full((24, 24, 3), 30, np.uint8)  # the far third picture
    got = icons.read(sq)
    assert (got.ids, got.why) == ((501,), "ok")


def test_round3_set_is_pinned_and_the_beside_counts() -> None:
    names = ["20261101T000000-rdp-stage-items-b", "20261102T000000-rdp-hunt-xmas02-p31"]
    sha = ev.names_sha256(names)
    ev.pinned(names, sha)  # the same list passes
    try:
        ev.pinned([*names, "20261201T000000-rdp-hunt-xmas02-p99"], sha)
    except SystemExit as exc:
        assert "refused" in str(exc)
    else:
        raise AssertionError("a changed list must be refused")
    assert [ev.part_of(n) for n in (*names, "x-rdp-human-xmas02-batt1112b")] == [
        "stagings",
        "natural",
        "own_play",
    ]
    assert ev.R3_FAMILY.search(names[0]) and ev.R3_FAMILY.search(names[1])
    assert not ev.R3_FAMILY.search("20261122T155206-rdp-xmas02-ifH21")  # no 1080 session
    assert not ev.R3_FAMILY.search("x-rdp-hunt-xmas02-fiT3")  # no calibration session
    s = 10**9
    truth = [{"t": 10 * s, "id": 12001, "amount": 1}, {"t": 20 * s, "id": 501, "amount": 1}]
    events = [{"t": 10 * s, "ids": [12001, 12002], "amount": 1, "why": "lead"},
              {"t": 20 * s, "ids": [502], "amount": 1, "why": "ok"}]  # fmt: skip
    got = ev.match(events, truth)
    assert got["by_why"] == {"lead": [1, 1], "ok": [1, 0]}
    b = ev.beside({names[0]: got, names[1]: got})
    assert b["reads_by_why"]["lead"] == {"matched": 2, "right": 2}
    assert b["I1_by_part"]["stagings"]["I1"] == 0.5
