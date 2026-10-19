"""battle_log (the Battle Log chat tab from pixels) and battle_log_judge (its lines vs packets).

Synthetic bitmaps and SYNTHETIC LANGUAGES (made-up words: no client string is committed, the
locale-pack guard refuses them) for the pure functions and the format mechanics; the real
languages' files are local (data/ui_anchors/battle_log/<lang>/) and their tests skip when the
files, frames or templates are not on this host. The reader must NEVER send input."""

from __future__ import annotations

import gzip
import json
import re
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts"))

import battle_log as bl  # noqa: E402
import battle_log_judge as bj  # noqa: E402

SRC = (ROOT / "scripts" / "battle_log.py").read_text()
NS = 1_000_000_000
REAL_SID = "20261019T152849-demo-hunt-flow43"


def test_the_reader_holds_no_input_path() -> None:
    """No Agent, no ro_agent.session, no click / key / chord / move / gm call in the source; the
    only ro_agent use is Screen (frames) and game_region."""
    code = "\n".join(line for line in SRC.splitlines() if not line.lstrip().startswith("#"))
    for pat in (r"\bAgent\(", r"\bsession\(", r"\.click\(", r"\.chord\(", r"\.drag\(",
                r"\.move\(", r"\.send\(", r"\.keys\(", r"\br\.gm\(", r"type_line", r"chat_line",
                r"activate_client", r"send_input", r"/internal/agent"):  # fmt: skip
        assert not re.search(pat, code), pat
    assert set(re.findall(r"\br\.(\w+)", code)) <= {"Screen", "game_region"}


# --- synthetic glyphs -------------------------------------------------------------------------


def _glyph(rows: list[str]) -> np.ndarray:
    """A LINE_PITCH-tall bitmap from rows of '#' / '.', placed from band row 1."""
    w = len(rows[0])
    g = np.zeros((bl.LINE_PITCH, w), bool)
    for y, r in enumerate(rows):
        g[1 + y] = [c == "#" for c in r]
    return g


GLYPHS = {
    "1": _glyph(["..#..", "###..", "..#..", "..#..", "..#..", "..#..", "..#..", "..#..",
                 "#####"]),
    "2": _glyph([".###.", "#...#", "....#", "...#.", "..#..", ".#...", "#....", "#....",
                 "#####"]),
    "'": _glyph(["#", "#", "#"]),
    "[": _glyph(["##", "#.", "#.", "#.", "#.", "#.", "#.", "#.", "#.", "#.", "##"]),
    "]": _glyph(["##", ".#", ".#", ".#", ".#", ".#", ".#", ".#", ".#", ".#", "##"]),
}  # fmt: skip


def _gl() -> bl.Glyphs:
    return bl.Glyphs(list(GLYPHS), [GLYPHS[c] for c in GLYPHS])


def _line_mask(text: str, gap: int = 1, space: int = 4) -> np.ndarray:
    parts = []
    for ch in text:
        if ch == " ":
            parts.append(np.zeros((bl.LINE_PITCH, space - gap), bool))
            continue
        parts += [GLYPHS[ch], np.zeros((bl.LINE_PITCH, gap), bool)]
    return np.concatenate([np.zeros((bl.LINE_PITCH, 4), bool), *parts], 1)


def test_glyphs_decode_with_spaces_and_unknown_runs() -> None:
    m = _line_mask("'12' [21]")
    text, parts = bl.decode(m, _gl())
    assert text == "'12' [21]"
    assert parts[0][0] == 4  # the first ink column
    m2 = np.concatenate([m, np.zeros((bl.LINE_PITCH, 12), bool)], 1)
    m2[2:10, -8:-2] = True  # a blob no template knows
    assert bl.decode(m2, _gl())[0].endswith("?")


def test_touching_glyphs_are_split() -> None:
    m = _line_mask("12", gap=0)  # a speck bridged the gap: one run, two glyphs
    assert len(bl.runs(m)) == 1
    assert bl.decode(m, _gl())[0] == "12"


def test_a_pink_sprite_behind_the_window_is_not_ink() -> None:
    band = np.full((bl.LINE_PITCH, 10, 3), (100, 85, 42), np.uint8)  # the darkened ground
    band[3, 2] = (240, 236, 120)  # yellow text
    band[3, 5] = (172, 142, 132)  # a pink monster's highlight (20261019T152849 frame 374)
    band[3, 8] = (114, 207, 185)  # cyan text
    m = bl.ink_of(band)
    assert m[3, 2] and not m[3, 5] and m[3, 8]
    assert bl.ink_of(band, "yellow")[3].tolist() == [i == 2 for i in range(10)]


def test_the_selected_tab_has_no_border_under_it() -> None:
    crop = np.zeros((bl.CROP[3] - bl.CROP[1], bl.CROP[2] - bl.CROP[0], 3), np.uint8)
    row = bl.TAB_EDGE_Y - bl.CROP[1]
    crop[row, bl.REGULAR_SPAN[0] - 2 :] = 230  # the border runs under Regular Chat only
    assert bl.tab_is_battle(crop) is True
    crop[row] = 0
    crop[row, : bl.BATTLE_SPAN[1] + 2] = 230  # ... under Battle Log only
    assert bl.tab_is_battle(crop) is False
    crop[row] = 0
    assert bl.tab_is_battle(crop) is None


# --- synthetic languages: the format mechanics -----------------------------------------------
#
# SYN: anchors first (the lab client's English order); ALT: words around trailing anchors and a
# bare count with a unit word after it, a base word that is the tail of the job phrase (the Thai
# client's order). Every word is made up.

SYN_FORMATS: dict[str, Any] = {
    "lang": "syn", "species": ["Zorbo", "Quxa", "Flobberwump"],
    "events": {
        "damage": {"colour": "yellow", "pattern": [
            {"name": "name", "anchor": "bracket"}, {"lit": "blarps"},
            {"num": "n", "anchor": "quoted"}, {"lit": "ouch"}, {"lit": "zaps", "opt": True}]},
        "base_exp": {"colour": "yellow", "pattern": [
            {"num": "n", "anchor": "quoted"}, {"lit": "Flim"}, {"lit": "Flamtastic"},
            {"lit": "gotten", "opt": True}]},
        "job_exp": {"colour": "yellow", "pattern": [
            {"num": "n", "anchor": "quoted"}, {"lit": "Jib"}, {"lit": "Flamtastic"},
            {"lit": "gotten", "opt": True}]},
        "item": {"colour": "cyan", "pattern": [
            {"lit": "Yo"}, {"lit": "snagged"}, {"item": "item"},
            {"num": "count", "anchor": "paren"}]}}}  # fmt: skip
ALT_FORMATS: dict[str, Any] = {
    "lang": "alt", "species": ["Zorbo"], "render": {"band_above": 3, "band_below": 2},
    "events": {
        "damage": {"pattern": [{"name": "name", "anchor": "bracket"}, {"lit": "wubwubwub"},
                               {"num": "n", "anchor": "quoted"}]},
        "base_exp": {"pattern": [{"lit": "XQ"}, {"num": "n", "anchor": "quoted"},
                                 {"lit": "gainz"}]},
        "job_exp": {"pattern": [{"lit": "Jx"}, {"lit": "XQ"}, {"num": "n", "anchor": "quoted"},
                                {"lit": "gainz"}]},
        "item": {"pattern": [{"lit": "gainz"}, {"item": "item"},
                             {"num": "count", "anchor": "bare"}, {"lit": "pcs"}]}}}  # fmt: skip


def _syn(glyphs: bool = True) -> bl.Lang:
    return bl.lang_from_formats(SYN_FORMATS, _gl() if glyphs else None)


def test_a_language_is_data_its_lines_parse_by_the_format() -> None:
    syn = _syn()

    def c(t: str) -> dict[str, Any]:
        return bl.classify(t, "", syn)

    assert c("[Zorbo] blarps '179' ouch zaps.") == {
        "type": "damage", "name_read": "Zorbo", "name": "Zorbo", "n": 179}  # fmt: skip
    assert c("[Zorb?] blarps '1?9' ouch")["name"] == "Zorbo"  # a glyph unknown; zaps optional
    assert c("[Zorb?] blarps '1?9' ouch")["n"] is None  # a digit unread: no number
    assert c("'2' Flim Flamtast?c gotten.") == {"type": "base_exp", "n": 2}  # a spoiled glyph
    assert c("2' Jib Flamtastic gotten.") == {"type": "job_exp", "n": 2}  # the quote lost
    assert c("'2' Jib Flamtastic gotten. ? ?") == {"type": "job_exp", "n": 2}  # sprite specks
    assert c("Yo snagged ????? (12).") == {"type": "item", "count": 12}
    assert c("Yo snagged ???? (1 ).") == {"type": "item", "count": 1}
    assert c("Yo dropzed ??? (6).")["type"] == "other"  # another verb: not an item
    assert c("'2' ???? Flamtastic gotten.")["type"] == "other"  # base or job: unknowable
    assert c("Yonder snagglepuss is here.")["type"] == "other"


def test_a_language_with_trailing_anchors_and_a_unit_word() -> None:
    alt = bl.lang_from_formats(ALT_FORMATS)
    assert alt.render.band_above == 3 and alt.render.band_h == bl.LINE_PITCH + 5
    assert alt.render.line_pitch == bl.LINE_PITCH  # the rest keep the defaults

    def c(t: str) -> dict[str, Any]:
        return bl.classify(t, "", alt)

    assert c("[Zorbo] wubwubwub '64'") == {"type": "damage", "name_read": "Zorbo",
                                           "name": "Zorbo", "n": 64}  # fmt: skip
    assert c("XQ '3' gainz") == {"type": "base_exp", "n": 3}
    assert c("Jx XQ '6' gainz") == {"type": "job_exp", "n": 6}  # not base: "Jx XQ" != "XQ"
    assert c("gainz Chrysalid 1 pcs") == {"type": "item", "count": 1}
    assert c("gainz Two Words 12 pcs") == {"type": "item", "count": 12}


def test_a_format_file_is_checked() -> None:
    bad = {"events": {"damage": {"pattern": [{"num": "n", "anchor": "squiggly"}]}}}
    with pytest.raises(ValueError):
        bl.lang_from_formats(bad)
    with pytest.raises(ValueError):
        bl.lang_from_formats({"events": {"explosion": {"pattern": [{"lit": "boom"}]}}})


def test_the_english_file_is_generated_and_parses(monkeypatch: pytest.MonkeyPatch,
                                                  tmp_path: Path) -> None:  # fmt: skip
    """formats-init en writes the four events; a line spelled FROM the generated words parses
    back (no client word in this test)."""
    monkeypatch.setattr(bl, "ANCHORS", tmp_path)
    bl.formats_init("en")
    fm = json.loads((tmp_path / "en" / "formats.json").read_text())
    assert set(fm["events"]) == {"damage", "base_exp", "job_exp", "item"}
    lang = bl.lang_from_formats(fm)
    words = [e["lit"] for e in fm["events"]["base_exp"]["pattern"] if "lit" in e]
    assert bl.classify("'7' " + " ".join(words) + ".", "", lang) == {"type": "base_exp", "n": 7}
    with pytest.raises(SystemExit):
        bl.formats_init("en")  # never overwrites without --force
    with pytest.raises(SystemExit):
        bl.formats_init("xx")  # only English is generated


def test_stacked_marks_get_taller_bands_and_join_their_glyph() -> None:
    r = bl.Render(band_above=3, band_below=2)
    assert bl.band_rows(0, r) == (bl.LINE_Y0 - 3, bl.LINE_Y0 + bl.LINE_PITCH + 2)
    assert r.crop[1] <= bl.LINE_Y0 - 3 and r.crop[3] >= bl.LINE_Y0 + 3 * bl.LINE_PITCH + 2
    assert bl.EN_RENDER.crop == bl.CROP  # English: unchanged
    m = np.zeros((10, 20), bool)
    m[4:8, 2:7] = True  # a base glyph
    m[1:3, 8:9] = True  # a mark one column beside it
    m[4:8, 14:18] = True  # the next glyph, a space away
    assert bl.runs(m) == [(2, 7), (8, 9), (14, 18)]
    assert bl.runs(m, min_w=2) == [(2, 9), (14, 18)]


def test_auto_picks_the_language_whose_words_fit(monkeypatch: pytest.MonkeyPatch) -> None:
    syn, alt = _syn(), bl.lang_from_formats(ALT_FORMATS, _gl())
    lines = {
        id(syn.render): ["'2' Flim Flamtastic gotten.", "XQ '3' gainz"],
        id(alt.render): ["'2' Flim Flamtastic gotten.", "Jx XQ '6' gainz", "XQ '3' gainz"],
    }

    def fake(crop: Any, gl: Any, cache: Any = None, render: Any = None) -> list[bl.Line | None]:
        return [_L(t) for t in lines[id(render)]]

    monkeypatch.setattr(bl, "read_lines", fake)
    code, score = bl.detect_lang([np.zeros((80, 600, 3), np.uint8)], [syn, alt])
    assert code == "alt" and score["alt"]["typed"] == 2 and score["syn"]["typed"] == 1


def test_real_languages_parse_their_fixture_lines() -> None:
    """Each local language with a fixture (data/ui_anchors/battle_log/<lang>/fixture_lines.json:
    lines of the client's own text with the expected events, e.g. Batt's Thai screenshot) parses
    it -- the classify stage after OCR."""
    found = [c for c in bl.languages() if (bl.lang_dir(c) / "fixture_lines.json").exists()]
    if not found:
        pytest.skip("no local language fixture on this host")
    for code in found:
        lang = bl.lang_from_formats(json.loads((bl.lang_dir(code) / "formats.json").read_text()))
        fx = json.loads((bl.lang_dir(code) / "fixture_lines.json").read_text())
        for x in fx["lines"]:
            got = bl.classify(x["text"], "", lang)
            assert {k: got.get(k) for k in x["expect"]} == x["expect"], (code, x["expect"])


# --- new lines ---------------------------------------------------------------------------------


def _L(text: str, colour: str = "yellow") -> bl.Line:
    """A synthetic line: one run per character, 3 columns each, at fixed columns."""
    parts = [(4 * i, 4 * i + 3, ch) for i, ch in enumerate(text) if ch != " "]
    m = np.zeros((bl.LINE_PITCH, 4 * len(text) + 4), bool)
    for x0, x1, ch in parts:
        m[4 + (ord(ch) % 5), x0:x1] = True
    return bl.Line(text, colour, m, parts)


def test_new_lines_follow_the_scroll() -> None:
    a, b, c, d = _L("'1' A"), _L("'2' B"), _L("'3' C"), _L("'4' D")
    assert bl.new_lines([a, b, c], [a, b, c]) == ([], 0, False)
    assert bl.new_lines([a, b, c], [b, c, d]) == ([2], 1, False)
    assert bl.new_lines([a, b, c], [c, d, a]) == ([1, 2], 2, False)
    assert bl.new_lines([a, b, c], [d, d, d]) == ([0, 1, 2], 3, False)
    # the window still filling: the lines are compared as the non-empty ones
    assert bl.new_lines([a, None, None], [a, b, None]) == ([1], 0, False)


def test_identical_consecutive_lines_count_when_the_scroll_is_seen() -> None:
    """Two kills with the same EXP: [dmg, base 2, job 1] -> [base 2, job 1, dmg'] is ONE new
    line though the old and the new lines repeat; a scroll that brings back exactly the lines
    it pushed out is invisible (the smallest shift: an undercount, flagged when ambiguous)."""
    dmg, dmg2 = _L("[P] 186"), _L("[P] 179")
    base, job = _L("'2' Flim"), _L("'1' Jib")
    assert bl.new_lines([dmg, base, job], [base, job, dmg2]) == ([2], 1, False)
    assert bl.new_lines([base, job, base], [job, base, job]) == ([2], 1, False)
    x = _L("'2' x")
    idx, shift, ambiguous = bl.new_lines([x, x, x], [x, x, x])
    assert (idx, shift, ambiguous) == ([], 0, True)


def test_same_line_tolerates_a_spoiled_glyph_but_not_a_different_digit() -> None:
    a = _L("'186'")
    b = bl.Line("'1?6'", "yellow", a.mask.copy(), [(p[0], p[1], "?" if i == 2 else p[2])
                                                  for i, p in enumerate(a.parts)])  # fmt: skip
    assert bl.same_line(a, b)  # a read and an unread run at the same columns pass
    c = _L("'188'")
    assert not bl.same_line(a, c)
    assert not bl.same_line(a, _L("'186'", colour="cyan"))
    extra = bl.Line(a.text + " ?", "yellow", a.mask, [*a.parts, (40, 44, "?")])
    assert bl.same_line(a, extra)  # a sprite's highlight beside the text is ignored


def test_an_unread_glyph_grown_into_its_neighbour_is_still_the_same() -> None:
    """v43 run 2 frames 12191 / 17864: a Thai glyph of an item name grew into the '(' after it
    for 2-3 frames -- compared over the columns both runs cover, it is the same line."""
    m = np.zeros((bl.LINE_PITCH, 40), bool)
    m[4:10, 2:8] = True  # an unread glyph ...
    m[4:10, 12:14] = True  # ... the '(' after it
    m[4:10, 20:24] = True
    a = bl.Line("? ( 1", "cyan", m, [(2, 8, "?"), (12, 14, "("), (20, 24, "1")])
    m2 = m.copy()
    m2[6, 8:12] = True  # a speck bridges the glyph and the '('
    b = bl.Line("? 1", "cyan", m2, [(2, 14, "?"), (20, 24, "1")])
    assert bl.same_line(a, b) and bl.same_line(b, a)
    c = bl.Line("? ( 7", "cyan", m, [(2, 8, "?"), (12, 14, "("), (20, 24, "7")])
    assert not bl.same_line(a, c)  # a different digit still never passes


def _crop() -> np.ndarray:
    return np.zeros((bl.CROP[3] - bl.CROP[1], bl.CROP[2] - bl.CROP[0], 3), np.uint8)


def _fake_reads(monkeypatch: pytest.MonkeyPatch, frames: list[list[bl.Line | None]]) -> None:
    seq = iter(frames)
    monkeypatch.setattr(bl, "read_lines", lambda crop, gl, cache=None, render=None: next(seq))
    monkeypatch.setattr(bl, "tab_is_battle", lambda crop, render=None: True)


def _feed(monkeypatch: pytest.MonkeyPatch, frames: list[list[bl.Line | None]]
          ) -> list[dict[str, Any]]:  # fmt: skip
    _fake_reads(monkeypatch, frames)
    rd = bl.Reader(_syn())
    out = []
    for k in range(len(frames)):
        out += rd.feed(k * NS // 5, _crop(), frame=k)
    return out + rd.flush()


BASE6, JOB2 = "'6' Flim Flamtastic gotten.", "'2' Jib Flamtastic gotten."
DMG = "[Zorbo] blarps '186' ouch zaps."


def test_a_kill_jump_counts_at_once_and_a_spoiled_frame_does_not(monkeypatch: pytest.MonkeyPatch
                                                                ) -> None:  # fmt: skip
    old = [_L(BASE6), _L(JOB2), _L("Yo snagged ??? (1).", "cyan")]
    kill = [_L(DMG), _L("'2' Flim Flamtastic gotten."), _L("'1' Jib Flamtastic gotten.")]
    spoiled = [old[0], old[1], _L("Yo snagged ??? (7).", "cyan")]  # a misread count, one frame
    recs = _feed(monkeypatch, [old, old, spoiled, old, kill, kill])
    assert [(r["frame"], r["type"], r.get("n")) for r in recs] == [
        (4, "damage", 186), (4, "base_exp", 2), (4, "job_exp", 1)]  # fmt: skip
    assert recs[0]["name"] == "Zorbo" and recs[0]["overflow"] is True


def test_an_unclean_new_line_is_refined_while_visible(monkeypatch: pytest.MonkeyPatch) -> None:
    a, b = _L(BASE6), _L(JOB2)
    first = _L(DMG.replace("186", "1?6"))  # a coarse first frame
    good = bl.Line(DMG, "yellow", first.mask, [
        (x0, x1, "8" if c == "?" else c) for x0, x1, c in first.parts])  # fmt: skip
    recs = _feed(monkeypatch, [[a, b, None], [a, b, first], [a, b, good]])
    assert len(recs) == 1
    r = recs[0]
    assert (r["frame"], r["type"], r["n"], r.get("refined")) == (1, "damage", 186, True)
    assert r["t_emit_ns"] == 2 * NS // 5  # returned at the clean read, timed at the first


def test_live_reads_until_the_watched_process_exits(monkeypatch: pytest.MonkeyPatch,
                                                    tmp_path: Path) -> None:  # fmt: skip
    """The live loop with a fake grab (no Screen, no backend): records appended to --out, and it
    stops at once when --until-pid is gone."""
    a, b, c = _L(BASE6), _L(JOB2), _L(DMG)
    _fake_reads(monkeypatch, [[a, b, None], [a, b, None], [a, b, c], [a, b, c]])
    monkeypatch.setattr(bl, "load_lang", lambda code=None, glyphs=None: _syn())
    clock = iter(range(1, 100))
    out = tmp_path / "live.jsonl"
    res = bl.live(out, hz=1000.0, grab=lambda box: (next(clock) * NS, _crop()), max_frames=4)
    assert res["frames_read"] == 4 and res["lang"] == "syn"
    recs = [json.loads(x) for x in out.read_text().splitlines()]
    assert [(r["type"], r["n"], r["t_ns"]) for r in recs] == [("damage", 186, 3 * NS)]
    res = bl.live(tmp_path / "none.jsonl", hz=1000.0, until_pid=2**22 + 12345,
                  grab=lambda box: (0, _crop()))  # fmt: skip
    assert res["frames_read"] == 0


# --- the judge ---------------------------------------------------------------------------------


def test_hits_take_the_species_of_the_latest_appearance() -> None:
    ev = [{"t_mono_ns": 1, "type": "entity_appear", "objtype": 5, "gid": 9, "job": 1002},
          {"t_mono_ns": 2, "type": "act", "src_gid": 2000002, "target_gid": 9, "damage": 180},
          {"t_mono_ns": 3, "type": "entity_vanish", "gid": 9, "reason": 1},
          {"t_mono_ns": 4, "type": "entity_appear", "objtype": 5, "gid": 9, "job": 1063},
          {"t_mono_ns": 5, "type": "act", "src_gid": 2000002, "target_gid": 9, "damage": 0},
          {"t_mono_ns": 6, "type": "act", "src_gid": 2000002, "target_gid": 9, "damage": 190},
          {"t_mono_ns": 7, "type": "act", "src_gid": 2000002, "target_gid": 0, "damage": 1,
           "kind": "pickup"}]  # fmt: skip
    assert [(h["t"], h["species"], h["damage"]) for h in bj.hits_of(ev)] == [
        (2, bj.SPECIES[1002], 180), (6, bj.SPECIES[1063], 190)]  # fmt: skip


def test_exp_deltas_and_kills() -> None:
    ev = [{"t_mono_ns": 0, "type": "stat_change", "name": "base_exp", "value": 10,
           "gm_command": True},
          {"t_mono_ns": 4 * NS, "type": "act", "src_gid": 2000002, "target_gid": 9, "damage": 9},
          {"t_mono_ns": 5 * NS - NS // 4, "type": "stat_change", "name": "base_exp", "value": 12},
          {"t_mono_ns": 5 * NS - NS // 4, "type": "stat_change", "name": "job_exp", "value": 1},
          {"t_mono_ns": 5 * NS, "type": "entity_vanish", "gid": 9, "reason": 1}]  # fmt: skip
    assert bj.exp_deltas(ev, "base_exp") == [(5 * NS - NS // 4, 2)]
    assert bj.kills_with_exp(ev) == [{"t": 5 * NS, "gid": 9, "base": 2, "job": None}]


def test_lines_match_the_earliest_unmatched_truth_preferring_the_value() -> None:
    truth = [{"t": 10 * NS, "v": 5}, {"t": 11 * NS, "v": 7}, {"t": 30 * NS, "v": 1}]
    lines = [{"t_ns": 11 * NS + NS // 2, "n": 7}, {"t_ns": 12 * NS, "n": 5},
             {"t_ns": 20 * NS, "n": 1}]  # fmt: skip
    assert bj.match(lines, truth, "n", "v") == [(0, 1), (1, 0), (2, None)]


def test_judge_tables_on_a_synthetic_session() -> None:
    S = NS
    ev = [{"t_mono_ns": 0, "type": "entity_appear", "objtype": 5, "gid": 9, "job": 1002},
          {"t_mono_ns": 0, "type": "stat_change", "name": "base_exp", "value": 0},
          {"t_mono_ns": 10 * S, "type": "act", "src_gid": 2000002, "target_gid": 9,
           "damage": 186},
          {"t_mono_ns": 10 * S + 7 * S // 10, "type": "stat_change", "name": "base_exp",
           "value": 2},
          {"t_mono_ns": 11 * S, "type": "entity_vanish", "gid": 9, "reason": 1},
          {"t_mono_ns": 13 * S, "type": "pickup_result", "ok": True, "amount": 3},
          {"t_mono_ns": 20 * S, "type": "act", "src_gid": 2000002, "target_gid": 9,
           "damage": 150}]  # a hit with no line  # fmt: skip
    lines = [{"t_ns": 11 * S + S // 5, "type": "damage", "n": 186, "name": bj.SPECIES[1002],
              "slot": 0},
             {"t_ns": 11 * S + S // 5, "type": "base_exp", "n": 2, "slot": 1},
             {"t_ns": 13 * S + S // 2, "type": "item", "count": 3, "slot": 2}]  # fmt: skip
    trace = [{"t": k * S // 5} for k in range(0, 200)]
    out = bj.judge(ev, lines, trace)
    d = out["damage"]
    assert (d["n_lines"], d["precision"], d["n_truth"], d["recall"]) == (1, 1.0, 2, 0.5)
    assert d["value"]["equal"] == 1 and d["name"]["equal"] == 1
    assert d["latency_p50_p90_s"][0] == 1.2
    assert d["miss_reasons"] == {"unseen": 1}
    assert out["base_exp"]["kills_with_line"] == 1.0 and out["base_exp"]["value"]["equal"] == 1
    assert out["item"]["count"]["equal"] == 1 and out["item"]["recall"] == 1.0


# --- a REAL session (English, the local files) ----------------------------------------------------


def test_real_session_reads_a_lunatic_kill() -> None:
    """20261019T152849-demo-hunt-flow43 (v43 run 1), frames 280-300, read with the LOCAL English
    files: the kill whose lines the design probe read -- damage 193, base 6, job 2 -- shows as
    ONE jump of three new lines in one frame; the packets of the run (when banked) confirm the
    hit's damage and species."""
    frames = bl.RECORDINGS / REAL_SID / "frames"
    if not frames.is_dir() or not (bl.lang_dir("en") / "formats.json").exists():
        pytest.skip("the real session's frames or the local English files are not on this host")
    lang = bl.load_lang("en")
    if lang.glyphs is None:
        pytest.skip("no English glyph templates on this host")
    files = bl.frame_files(frames)[280:300]
    rd = bl.Reader(lang)
    recs = []
    for i, t, p in files:
        recs += rd.feed(t, bl.read_crop(p, lang.render), frame=i)
    recs += rd.flush()
    got = [(r["type"], r.get("n"), r.get("name")) for r in recs]
    assert got == [("damage", 193, bj.SPECIES[1063]), ("base_exp", 6, None),
                   ("job_exp", 2, None)]  # fmt: skip
    assert {r["frame"] for r in recs} == {293}
    pk = bl.DEMO / REAL_SID / "packets.jsonl.gz"
    if pk.exists():  # the packets agree: our hit for 193, ~1.2 s before the line
        with gzip.open(pk, "rt") as fh:
            packets = sorted((json.loads(x) for x in fh), key=lambda e: int(e["t_mono_ns"]))
        hit = [h for h in bj.hits_of(packets) if 0 <= recs[0]["t_ns"] - h["t"] <= 3 * NS]
        assert any(h["damage"] == 193 and h["species"] == recs[0]["name"] for h in hit)


def test_dead_vs_the_bots_own_call() -> None:
    """The BASE EXP line against the bot's dead call (its loot step's start)."""
    kills = [{"t": 10 * NS}, {"t": 40 * NS}]
    lines = [{"t_ns": 10 * NS + 3 * NS // 10, "type": "base_exp"}]
    eng = [{"result": "dead", "t_end": 14 * NS, "loot": {"s": 2.0}},  # called at 12 s
           {"result": "dead", "t_end": 44 * NS, "loot": {"s": 1.0}},  # kill at 40, no line
           {"result": "dead", "t_end": 30 * NS, "loot": {"s": 1.0}},  # no kill near: false
           {"result": "gave_up", "t_end": 50 * NS, "loot": {"s": 1.0}}]  # fmt: skip
    d = bj.dead_vs_bot(eng, kills, lines)
    assert (d["bot_dead_calls_with_kill"], d["no_kill_near"], d["no_exp_line"]) == (2, 1, 1)
    assert d["line_after_kill_p50_p90_s"] == [0.3, 0.3]
    assert d["line_earlier_than_bot_p10_p50_p90_s"] == [1.7, 1.7, 1.7]
