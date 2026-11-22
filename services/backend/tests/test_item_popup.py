"""The item popup reader (docs/planning/item-popup-reader.md; Batt 2026-11-21): the count by the
text's constant tail, the icon pick, and the scorer's match rule and bars. Synthetic pixels only
(client pixels are never committed)."""

from __future__ import annotations

import json
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


# --- Amendment 6 (section 4's 1080 run-time check): the watcher and set w1080 --------------------
def _draw_popup(img: np.ndarray, x0: int, width: int = 188) -> np.ndarray:
    """test_bare_steal's popup frame (fiT14's measure), its left edge at x0."""
    t, b, x1 = ip.bs.POPUP_TOP, ip.bs.POPUP_BOTTOM, x0 + width - 1
    img[t + 2 : b - 1, x0 : x0 + 2] = 255
    img[t + 2 : b - 1, x0 + 2] = 190
    img[t + 2 : b - 1, x0 + 3 : x1 - 1] = 254
    img[t, x0 + 3 : x1 - 1] = 255
    img[b, x0 + 3 : x1 - 1] = 255
    img[t + 8 : t + 22, x0 + 8 : x0 + 22] = 40
    return img


def test_amendment6_the_band_is_the_720_place_moved_by_the_centring() -> None:
    bx, by, bw, bh = ip.BAND
    assert (bx, by, bw, bh) == (533, 72, 536, 38)
    assert ip.band_box((0, 0, 1920, 1080)) == (853, 72, 536, 38)  # + (1920 - 1280) / 2
    assert ip.band_box((10, 20, 1920, 1080)) == (863, 92, 536, 38)  # the region's own origin
    assert ip.band_box((0, 0, 1280, 720)) == (533, 72, 536, 38)  # 720: the place itself
    # the band holds the whole box (POPUP_MAX_W from POPUP_LEFT) and the count's rows
    assert bx < ip.bs.POPUP_LEFT - ip.bs.POPUP_LEFT_TOL
    assert bx + bw > ip.bs.POPUP_LEFT + ip.bs.POPUP_MAX_W
    assert by <= ip.bs.POPUP_TOP - 2 and by + bh > ip.bs.POPUP_BOTTOM + 2


def test_amendment6_a_real_1080_band_put_back_reads_as_the_720_popup() -> None:
    real = _draw_popup(np.full((1080, 1920, 3), 120, np.uint8), ip.bs.POPUP_LEFT + 320, 194)
    x, y, w, h = ip.band_box((0, 0, 1920, 1080))
    frame = ip.place_band(real[y : y + h, x : x + w])
    assert frame.shape == (110, 1280, 3)
    p = ip.box_of(frame)
    assert p is not None and (p.left, p.right - p.left + 1) == (ip.bs.POPUP_LEFT, 194)
    flat = _draw_popup(np.full((720, 1280, 3), 120, np.uint8), ip.bs.POPUP_LEFT, 194)
    assert ip.bs.popup_box(flat) == ip.bs.popup_box(frame)
    # the uncentred place on the real frame (the 720 one) shows no popup
    assert ip.box_of(ip.place_band(real[72:110, 533:1069])) is None


class _Marked(ip.Tracker):
    """The Tracker's rules on bands whose first pixel names the item (0: no popup)."""

    def read(self, frame_rgb, p):  # type: ignore[no-untyped-def]
        k = int(frame_rgb[ip.BAND[1], ip.BAND[0], 0])
        return ip.FrameRead(ip.ItemRead((k,), 3.0, None, "ok"), 1, 180)


def test_amendment6_watch_writes_one_event_per_popup_and_its_summary(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    bx, by = ip.BAND[0], ip.BAND[1]
    monkeypatch.setattr(
        ip, "box_of", lambda f: None if f[by, bx, 0] == 0 else ip.Popup(541, 720, b"")
    )
    seq = [0, 5, 5, None, 5, 0, 7, 7]  # None: a grab that failed
    it = iter(enumerate(seq))
    done = [False]

    def grab():  # type: ignore[no-untyped-def]
        try:
            t, k = next(it)
        except StopIteration:
            done[0] = True
            return 99, np.zeros((38, 536, 4), np.uint8)
        if k is None:
            raise OSError("the pipe broke")
        band = np.zeros((38, 536, 4), np.uint8)
        band[0, 0, :3] = k
        return t, band

    clock = iter(range(0, 10**6))
    got = ip.watch(tmp_path / "w", grab, _Marked(None, None), lambda: done[0], crops=True,  # type: ignore[arg-type]
                   sleep=lambda s: None, clock=lambda: float(next(clock)) / 100)  # fmt: skip
    lines = [json.loads(x) for x in (tmp_path / "w" / "events.jsonl").read_text().splitlines()]
    assert [(e["t"], e["ids"], e["frames"]) for e in lines] == [(1, [5], 3), (6, [7], 2)]
    assert got["events"] == 2 and got["grab_errors"] == 1 and got["ticks"]["n"] == 8
    assert sorted(p.name for p in (tmp_path / "w").glob("crop-*.png")) == [
        "crop-1.png",
        "crop-6.png",
    ]
    assert json.loads((tmp_path / "w" / "summary.json").read_text())["events"] == 2
    assert ip.tick_stats([1.0, 2.0, 3.0, 4.0])["p50"] == 2.0 and ip.tick_stats([])["n"] == 0


def _session(root: Path, name: str, t0: int, n: int) -> Path:
    import gzip

    d = root / name
    d.mkdir()
    s = 10**9
    (d / "manifest.json").write_text(json.dumps({"t0_mono_ns": t0, "t1_mono_ns": t0 + 1000 * s}))
    with gzip.open(d / "packets.jsonl.gz", "wt") as fh:
        # n pickups 10 s apart inside the window, then one outside it
        for t in [t0 + (k + 1) * 10 * s for k in range(n)] + [t0 + 2000 * s]:
            row = {"type": "pickup_result", "ok": True, "t_mono_ns": t, "item_id": 909}
            fh.write(json.dumps({**row, "amount": 1}) + "\n")
    return d


def test_amendment6_score_events_windows_coverage_and_minimums(tmp_path) -> None:  # type: ignore[no-untyped-def]
    s = 10**9
    assert ev.covered((5, 9), [(0, 4), (4, 10)]) and not ev.covered((5, 11), [(0, 10)])
    rows = [{"t": 3}, {"t": 1}, {"t": 12}]
    assert [r["t"] for r in ev.in_window(rows, 1, 10)] == [1, 3]
    assert [r["t"] for r in ev.in_window(rows, 1, 10, pad_s=2e-9)] == [1, 3, 12]
    sessions = [
        _session(tmp_path, f"x-rdp-xmas02-w{k}", (k + 1) * 10_000 * s, 63) for k in range(4)
    ]
    w = tmp_path / "watch1"
    w.mkdir()
    (w / "meta.json").write_text(json.dumps({"t_start_mono_ns": 0}))
    events = [{"t": t["t"] + s // 2, "ids": [909], "amount": 1, "why": "ok"}
              for d in sessions for t in ev.truths(d)]  # fmt: skip
    events[0]["ids"] = [501]  # one wrong item
    (w / "events.jsonl").write_text("".join(json.dumps(e) + "\n" for e in events))
    try:  # still running (no summary): no span covers any session
        ev.score_events(sessions, [w])
    except SystemExit as exc:
        assert "no finished watcher span" in str(exc)
    else:
        raise AssertionError("an unfinished watcher must be refused")
    (w / "summary.json").write_text(json.dumps({"t_end_mono_ns": 10**6 * s, "ticks": {"n": 9}}))
    sizes = ev.score_events(sessions, [w], sizes_only=True)
    assert sizes["truths"] == 252 and sizes["size_ok"]  # 4 x 63, the outside one left out
    try:
        ev.score_events(sessions[:3], [w])
    except SystemExit as exc:
        assert "below its minimums" in str(exc)
    else:
        raise AssertionError("3 sessions must be refused")
    got = ev.score_events(sessions, [w])
    assert got["lines"]["truths"] == 252 and got["lines"]["matched"] == 252
    assert got["lines"]["id_ok"] == 251 and got["verdict"]["I1_id"] == "PASS"
    assert got["lines"]["events"] == 252  # the session windows' events only
    assert got["beside"]["watchers"]["watch1"]["ticks"]["n"] == 9


# --- round 4 (Amendment 10): the merge, the nearest glyph, the 1080 digit staging ----------------
S_NS = 10**9


def _ev(t_s: float, ids: tuple[int, ...] | None = (912,), amount: int | None = 1,
        last_s: float | None = None) -> ip.Event:  # fmt: skip
    t = int(t_s * S_NS)
    return ip.Event(t, ids, "ok", 3.0, amount, 180,
                    t_last=int((t_s if last_s is None else last_s) * S_NS))  # fmt: skip


def test_round4_a_piece_joins_only_the_same_read_soon_after() -> None:
    first = _ev(0.0, last_s=3.0)
    assert ip.joins(first, _ev(3.5))  # 0.5 s after its last frame, 3.5 s after its first
    assert ip.joins(first, _ev(4.25))  # MERGE_GAP_S = 1.25 s: at the edge
    assert not ip.joins(first, _ev(4.3))  # too long after its last frame
    assert not ip.joins(first, _ev(3.5, ids=(913,)))  # another item
    assert not ip.joins(first, _ev(3.5, amount=2))  # another amount
    assert not ip.joins(first, _ev(3.5, amount=None))  # unread only joins unread
    assert ip.joins(_ev(0.0, amount=None, last_s=3.0), _ev(3.5, amount=None))
    late = _ev(0.0, last_s=5.5)
    assert ip.joins(late, _ev(6.0)) and not ip.joins(late, _ev(6.1))  # MERGE_LIFE_S = 6.0 s


def test_round4_the_merger_holds_a_piece_until_nothing_can_join_it() -> None:
    m = ip.Merger()
    assert m.add(_ev(0.0, last_s=3.0)) == []  # pending
    assert m.due(int(3.5 * S_NS), _ev(3.4)) == []  # a box opened 0.4 s after: it may join
    assert m.add(_ev(3.4, last_s=4.8)) == []  # it did: one popup
    assert m.joined == 1 and m.parts == [int(3.4 * S_NS)]
    assert m.pending is not None and m.pending.t_last == int(4.8 * S_NS)
    assert m.pending.frames == 2
    assert m.due(int(5.0 * S_NS), None) == []  # 0.2 s after its last frame: still open to a join
    got = m.due(int(6.1 * S_NS), None)  # 1.3 s after: final
    assert [e.t for e in got] == [0] and m.pending is None
    # another item closes the pending one at once, in order
    assert m.add(_ev(10.0, last_s=12.0)) == []
    assert [e.ids for e in m.add(_ev(12.5, ids=(501,)))] == [(912,)]
    assert m.due(int(13.0 * S_NS), _ev(20.0)) == [_ev(12.5, ids=(501,))]  # a late box: final
    assert m.flush() == [] and m.add(_ev(30.0)) == [] and len(m.flush()) == 1


def test_round4_watch_joins_a_popup_read_again_after_a_lost_tick(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    bx, by = ip.BAND[0], ip.BAND[1]
    monkeypatch.setattr(
        ip, "box_of", lambda f: None if f[by, bx, 0] == 0 else ip.Popup(541, 720, b"")
    )
    # 0.25 s ticks: popup 5, one lost tick, popup 5 again (the same popup), gone 2 s, 5 again (new)
    seq = [0, 5, 5, 5, 0, 5, 5, 0, 0, 0, 0, 0, 0, 0, 0, 5, 5, 0, 0, 0, 0, 0, 0]
    it = iter(enumerate(seq))
    done = [False]

    def grab():  # type: ignore[no-untyped-def]
        try:
            k, v = next(it)
        except StopIteration:
            done[0] = True
            return 99 * S_NS, np.zeros((38, 536, 4), np.uint8)
        band = np.zeros((38, 536, 4), np.uint8)
        band[0, 0, :3] = v
        return k * S_NS // 4, band

    clock = iter(range(0, 10**6))
    got = ip.watch(tmp_path / "w", grab, _Marked(None, None), lambda: done[0], crops=True,  # type: ignore[arg-type]
                   sleep=lambda s: None, clock=lambda: float(next(clock)) / 100)  # fmt: skip
    lines = [json.loads(x) for x in (tmp_path / "w" / "events.jsonl").read_text().splitlines()]
    q = S_NS // 4
    got_lines = [(e["t"], e["frames"], e["t_last"]) for e in lines]
    assert got_lines == [(q, 5, 6 * q), (15 * q, 2, 16 * q)]
    assert got["events"] == 2 and got["joined"] == 1
    assert sorted(p.name for p in (tmp_path / "w").glob("crop-*.png")) == [
        f"crop-{q}.png", f"crop-{15 * q}.png"]  # fmt: skip


def test_round4_read_count_names_the_nearest_glyph() -> None:
    run = GLYPH["3"].copy()
    near, far = run.copy(), run.copy()
    near[0, 1] = not near[0, 1]  # 1 pixel off
    far[0, 1], far[1, 1], far[2, 1] = not far[0, 1], not far[1, 1], not far[2, 1]  # 3 off
    tail = [GLYPH[c] for c in "cab"]
    b = box("ab 3 cab")
    for digits in ({"8": far, "3": near}, {"3": near, "8": far}):  # either order: the nearer
        assert ip.read_count(b, ip.CountFont(tail, digits)) == 3
    assert ip.read_count(b, ip.CountFont(tail, {"8": far})) == 8  # the only one within SAME


def test_round4_the_staging_lines_and_their_events() -> None:
    rows = [{"t_mono_ns": 5, "cmd": "@item 909 7"},  # before the watcher: not the staging
            {"t_mono_ns": 20 * S_NS, "cmd": "@item 909 23"},
            {"t_mono_ns": 10 * S_NS, "cmd": "@item 909 3"},
            {"t_mono_ns": 30 * S_NS, "cmd": "@delitem 909 26"},
            {"t_mono_ns": 40 * S_NS, "cmd": "@monsterignore"}]  # fmt: skip
    lines = ev.staging_lines(rows, t_from=S_NS)
    assert lines == [(10 * S_NS, 3), (20 * S_NS, 23)]
    evs = [{"t": 13 * S_NS}, {"t": 22 * S_NS}, {"t": 50 * S_NS}]
    assert [(e["t"], n) for e, n in ev.pair_lines(lines, evs)] == [(13 * S_NS, 3), (22 * S_NS, 23)]
    import pytest

    with pytest.raises(SystemExit, match="no event"):
        ev.pair_lines([(10 * S_NS, 3), (40 * S_NS, 4)], evs)  # 50 s is > 6 s after 40 s
    with pytest.raises(SystemExit, match="two lines"):
        ev.pair_lines([(10 * S_NS, 3), (11 * S_NS, 4)], [{"t": 13 * S_NS}])
