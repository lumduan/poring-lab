"""battle_log (the Battle Log chat tab from pixels) and battle_log_judge (its lines vs packets).

Synthetic bitmaps for the pure functions; a REAL session as the positive case (skipped when its
frames or the local glyph templates are not on this host). The reader must NEVER send input."""

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
    band[3, 5] = (172, 142, 132)  # a Poring's highlight (20261019T152849 frame 374)
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


# --- classify ----------------------------------------------------------------------------------


def test_lines_are_classified_by_shape_with_fuzzy_words() -> None:
    def c(t: str) -> dict[str, Any]:
        return bl.classify(t)

    assert c("[Poring] receives '179' damage points.") == {
        "type": "damage", "n": 179, "name_read": "Poring", "name": "Poring"}  # fmt: skip
    assert c("[Cream?] receives '1?2' damage points")["name"] == "Creamy"  # a glyph unknown
    assert c("[Cream?] receives '1?2' damage points")["n"] is None  # a digit unread: no number
    assert c("'2' Base Experience acquii ed.") == {"type": "base_exp", "n": 2}  # a split 'r'
    assert c("1' Job Experience acquired.") == {"type": "job_exp", "n": 1}  # the quote lost
    assert c("You got ????? (12).") == {"type": "item", "count": 12}
    assert c("You got ???? (1 ).") == {"type": "item", "count": 1}
    assert c("Your participation is appreciated.")["type"] == "other"
    assert c("You dropped ??? (6).")["type"] == "other"


def test_species_from_a_partly_read_name() -> None:
    assert bl.species_of("Poring") == "Poring"
    assert bl.species_of("Lunati?") == "Lunatic"
    assert bl.species_of("Crea?") == "Creamy"  # 'my' touching: one unread run
    assert bl.species_of("?") is None
    assert bl.species_of("Porong") is None


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
    base, job = _L("'2' Base"), _L("'1' Job")
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


def _crop() -> np.ndarray:
    return np.zeros((bl.CROP[3] - bl.CROP[1], bl.CROP[2] - bl.CROP[0], 3), np.uint8)


def _feed(monkeypatch: pytest.MonkeyPatch, frames: list[list[bl.Line | None]]
          ) -> list[dict[str, Any]]:  # fmt: skip
    seq = iter(frames)
    monkeypatch.setattr(bl, "read_lines", lambda crop, gl, cache=None: next(seq))
    monkeypatch.setattr(bl, "tab_is_battle", lambda crop: True)
    rd = bl.Reader(_gl())
    out = []
    for k in range(len(frames)):
        out += rd.feed(k * NS // 5, _crop(), frame=k)
    return out + rd.flush()


def test_a_kill_jump_counts_at_once_and_a_spoiled_frame_does_not(monkeypatch: pytest.MonkeyPatch
                                                                ) -> None:  # fmt: skip
    old = [_L("'6' Base Experience acquired."), _L("'2' Job Experience acquired."),
           _L("You got ??? (1).", "cyan")]  # fmt: skip
    kill = [_L("[Poring] receives '186' damage points."), _L("'2' Base Experience acquired."),
            _L("'1' Job Experience acquired.")]  # fmt: skip
    spoiled = [old[0], old[1], _L("You got ??? (7).", "cyan")]  # a misread count, one frame
    recs = _feed(monkeypatch, [old, old, spoiled, old, kill, kill])
    assert [(r["frame"], r["type"], r.get("n")) for r in recs] == [
        (4, "damage", 186), (4, "base_exp", 2), (4, "job_exp", 1)]  # fmt: skip
    assert recs[0]["name"] == "Poring" and recs[0]["overflow"] is True


def test_an_unclean_new_line_is_refined_while_visible(monkeypatch: pytest.MonkeyPatch) -> None:
    a, b = _L("'6' Base Experience acquired."), _L("'2' Job Experience acquired.")
    first = _L("[Poring] receives '1?6' damage points.")  # a coarse first frame
    good = bl.Line("[Poring] receives '186' damage points.", "yellow", first.mask, [
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
    a, b = _L("'6' Base Experience acquired."), _L("'2' Job Experience acquired.")
    c = _L("[Poring] receives '186' damage points.")
    frames = iter([[a, b, None], [a, b, None], [a, b, c], [a, b, c]])
    monkeypatch.setattr(bl, "read_lines", lambda crop, gl, cache=None: next(frames))
    monkeypatch.setattr(bl, "tab_is_battle", lambda crop: True)
    monkeypatch.setattr(bl, "load_glyphs", _gl)
    monkeypatch.setattr(bl, "load_names", lambda: None)
    clock = iter(range(1, 100))
    out = tmp_path / "live.jsonl"
    res = bl.live(out, hz=1000.0, grab=lambda: (next(clock) * NS, _crop()), max_frames=4)
    assert res["frames_read"] == 4
    recs = [json.loads(x) for x in out.read_text().splitlines()]
    assert [(r["type"], r["n"], r["t_ns"]) for r in recs] == [("damage", 186, 3 * NS)]
    res = bl.live(tmp_path / "none.jsonl", hz=1000.0, until_pid=2**22 + 12345,
                  grab=lambda: (0, _crop()))  # fmt: skip
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
        (2, "Poring", 180), (6, "Lunatic", 190)]  # fmt: skip


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
    lines = [{"t_ns": 11 * S + S // 5, "type": "damage", "n": 186, "name": "Poring", "slot": 0},
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


# --- a REAL session ------------------------------------------------------------------------------


def test_real_session_reads_a_lunatic_kill() -> None:
    """20261019T152849-demo-hunt-flow43 (v43 run 1), frames 280-300: the Lunatic kill whose
    lines the design probe read -- damage 193, base 6, job 2 -- shows as ONE jump of three new
    lines in one frame; the packets of the run (when banked) confirm the hit's damage."""
    frames = bl.RECORDINGS / REAL_SID / "frames"
    if not frames.is_dir() or not bl.GLYPHS.exists():
        pytest.skip("the real session's frames or the local glyph templates are not on this host")
    files = bl.frame_files(frames)[280:300]
    rd = bl.Reader(bl.load_glyphs())
    recs = []
    for i, t, p in files:
        recs += rd.feed(t, bl.read_crop(p), frame=i)
    recs += rd.flush()
    got = [(r["type"], r.get("n"), r.get("name")) for r in recs]
    assert got == [("damage", 193, "Lunatic"), ("base_exp", 6, None), ("job_exp", 2, None)]
    assert {r["frame"] for r in recs} == {293}
    pk = bl.DEMO / REAL_SID / "packets.jsonl.gz"
    if pk.exists():  # the packets agree: our hit on a Lunatic for 193, ~1.2 s before the line
        with gzip.open(pk, "rt") as fh:
            packets = sorted((json.loads(x) for x in fh), key=lambda e: int(e["t_mono_ns"]))
        hit = [h for h in bj.hits_of(packets) if 0 <= recs[0]["t_ns"] - h["t"] <= 3 * NS]
        assert any(h["damage"] == 193 and h["species"] == "Lunatic" for h in hit)


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
