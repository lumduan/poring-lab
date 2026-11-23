"""Batt 2026-11-19, a Run on any client and any character:

- the HOTBAR is the player's own: "do not lock the bot over this: it is the user's own business
  ... without Fly Wings the bot dies; the user learns and improves -- or a user may use an item
  with a teleport skill" and "do not lock this": the start check's hotbar lines warn, the
  runner's own start refusals on them become warnings inside the live player, and the Knife swap
  is left out of a run whose Knife / dagger slots do not read right;
- a DEATH: "if she died -- the dialog is up and her HP is 0 -- do not enter the hunting loop
  again; very simple": her HP reading 0 % for DEAD_HP0_S with no death dialog recognised ends
  the run (the lab client's recognised dialog keeps the runner's own respawn)."""

from __future__ import annotations

import json
import sys
import types
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[3] / "scripts"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import flow_play as fp  # noqa: E402
import flow_run as fr  # noqa: E402
import test_live_player as tl  # noqa: E402

from poring_flow.runtime import _Halt  # noqa: E402

FAILED_WINGS = {
    "id": "wings",
    "ok": False,
    "refuses": True,
    "words": "the Fly Wings' count on the hotbar did not read: a person first",
}


# -- the hotbar: warnings, never a lock ----------------------------------------------------------


def test_the_hotbar_lines_warn_and_never_refuse() -> None:
    items = [FAILED_WINGS, {"id": "chat", "ok": True, "words": "closed"},
             {"id": "knife", "ok": True, "words": "one Knife on F4"}]  # fmt: skip
    got = fr.hotbar_warnings(items)
    assert got[0]["refuses"] is False and fr.HOTBAR_WARN in got[0]["words"]
    assert got[1] == items[1]  # not a hotbar line: as it was
    assert got[2] == {**items[2], "refuses": False}  # a passing one: no warning words
    assert fr.hotbar_warnings(got) == got  # the words are added once
    assert set(fr.HOTBAR_LINES) == {"wings", "heals", "home", "knife", "dagger"}


def test_the_helper_s_check_does_not_refuse_on_the_hotbar() -> None:
    line = fr.CHECK_MARK + json.dumps({"items": [FAILED_WINGS], "ok": False, "refuses": True})
    got = fr.parse_check_output(line, "any")
    assert got["refuses"] is False and got["items"][0]["refuses"] is False
    chat = {"id": "chat", "ok": False, "refuses": True, "words": "the chat input is open"}
    line = fr.CHECK_MARK + json.dumps({"items": [FAILED_WINGS, chat], "refuses": True})
    assert fr.parse_check_output(line, "any")["refuses"] is True  # another line still refuses


def test_the_run_starts_with_the_hotbar_lines_failed_and_says_they_are_warnings() -> None:
    cell = {"id": "cell", "ok": True, "words": "the minimap is xmas_dun02's"}
    got = {"items": fr.hotbar_warnings([FAILED_WINGS, {**FAILED_WINGS, "id": "dagger"}, cell])}
    assert fp.check_refusal(got) is None
    raw = {"items": [FAILED_WINGS, cell]}  # even with the runner's own flag on the line
    assert fp.check_refusal(raw) is None
    lines = fp.check_lines(got)
    assert lines[0].startswith("check WARN wings:") and lines[2].startswith("check OK   cell")
    summary = fp.check_summary(got)
    assert "WARNING (the Run starts anyway): wings, dagger" in summary and "FAIL" not in summary
    chat = {"id": "chat", "ok": False, "words": "the chat input is open"}
    assert fp.check_refusal({"items": [chat, cell]}) is not None  # not a hotbar line: refuses


def plan(knife_swap: bool) -> fp.RunnerPlan:
    return fp.RunnerPlan(block="field", flow_id="xmas_dun02_rogue", keys={},
                         vals={"knife_swap": knife_swap, "heal_key": "F1"})  # fmt: skip


def boxed_plan() -> fp.RunnerPlan:
    """A hunt core whose box plays the Knife swap itself (its knife_on / knife_back functions)
    and strikes its monsters by recipes -- Batt's xmas_dun02 project's shape (12:13: the switch
    alone turned off, the runner refused: "the box's recipes swap the Knife")."""
    from poring_flow import recipes as rc

    steps = ("knife_on", "strike", "wait_steal", "knife_back", "wait_kill", "loot")
    return fp.RunnerPlan(
        block="field", flow_id="xmas_dun02_rogue", keys={}, vals={"knife_swap": True},
        plays=frozenset({"knife", "recipes", "model", "potion"}),
        calls={"knife_on": (), "knife_back": (), "home": ()},
        call_names={"knife_on": "knife_on", "knife_back": "knife_back", "home": "home"},
        recipes={"mystcase": rc.Recipe("mystcase", "attack_mystcase", steps)},
    )  # fmt: skip


def test_a_knife_slot_that_does_not_read_right_plays_without_the_knife_swap() -> None:
    prep = types.SimpleNamespace(runners={"field": plan(True)})
    knife = {"id": "knife", "ok": False, "words": "the F4 slot draws a count None"}
    words = fp.knife_swap_off(prep, {"items": [knife]})  # type: ignore[arg-type]
    assert prep.runners["field"].vals == {"knife_swap": False, "heal_key": "F1"}
    assert len(words) == 1 and "WITHOUT the swap" in words[0] and "knife" in words[0]
    assert "--bare-steal" not in fp.fc.argv(prep.runners["field"].vals)
    ok = types.SimpleNamespace(runners={"field": plan(True)})
    assert fp.knife_swap_off(ok, {"items": [{**knife, "ok": True}]}) == []  # type: ignore[arg-type]
    assert ok.runners["field"].vals["knife_swap"] is True
    off = types.SimpleNamespace(runners={"field": plan(False)})
    assert fp.knife_swap_off(off, {"items": [knife]}) == []  # type: ignore[arg-type]


def test_the_knife_swap_goes_whole_its_functions_and_recipes_with_it() -> None:
    """The runner refuses the box's Knife functions and its recipes without the swap
    (box_plays_refused; checked 2026-11-19 on Batt's real project through the runner's own run():
    the switch alone -> refused, the whole swap off -> accepted)."""
    prep = types.SimpleNamespace(runners={"field": boxed_plan()})
    (words,) = fp.knife_swap_off(prep, {"items": [{"id": "dagger", "ok": False}]})  # type: ignore[arg-type]
    got = prep.runners["field"]
    assert got.vals["knife_swap"] is False and got.recipes == {}
    assert got.plays == frozenset({"model", "potion"})
    assert set(got.calls) == set(got.call_names) == {"home"}
    assert "box_recipes" not in got.box_kwargs() and got.box_roles() == {"home": "home"}
    assert "its Knife functions and its 1 monster recipe(s)" in words


def test_the_knife_swap_set_off_in_the_settings_drops_the_box_s_swap_whole() -> None:
    """Batt 11-22, the fists: the Run settings turn the swap off (fst1, 11-23 07:13: the runner
    refused "the box's recipes swap the Knife, but this run swaps no Knife"); the start drops the
    box's Knife functions and recipes as knife_swap_off does."""
    from dataclasses import replace

    prep = types.SimpleNamespace(
        runners={"field": replace(boxed_plan(), vals={"knife_swap": False})}
    )
    (words,) = fp.knife_swap_set_off(prep)  # type: ignore[arg-type]
    got = prep.runners["field"]
    assert got.vals["knife_swap"] is False and got.recipes == {}
    assert got.plays == frozenset({"model", "potion"})
    assert set(got.calls) == set(got.call_names) == {"home"}
    assert "box_recipes" not in got.box_kwargs()
    assert "off in the Run settings" in words
    assert "its Knife functions and its 1 monster recipe(s)" in words
    on = types.SimpleNamespace(runners={"field": boxed_plan()})
    assert fp.knife_swap_set_off(on) == []  # type: ignore[arg-type]  # the swap on: untouched
    assert on.runners["field"].recipes and "knife" in on.runners["field"].plays
    plain = types.SimpleNamespace(runners={"field": plan(False)})
    assert fp.knife_swap_set_off(plain) == []  # type: ignore[arg-type]  # nothing to drop


def test_the_runner_s_own_start_lets_the_hotbar_pass_inside_the_player_only() -> None:
    dh = types.SimpleNamespace(
        player_stock_refused=lambda counts, heals: "no Fly Wing read",
        player_slots_refused=lambda states: "F1 shows another item",
        player_weight_refused=lambda share, red: None,
        PLAYER_MAP_UNREAD="refuse",
    )
    before = (dh.player_stock_refused, dh.player_slots_refused)
    said: list[str] = []
    with fp.player_owns_the_start(dh, said.append):
        assert dh.player_stock_refused({601: None}, [504]) is None
        assert dh.player_slots_refused({}) is None
    assert said == ["WARNING (the hotbar, the player's own; the Run plays on): no Fly Wing read",
                    "WARNING (the hotbar, the player's own; the Run plays on): F1 shows another "
                    "item"]  # fmt: skip
    assert (dh.player_stock_refused, dh.player_slots_refused) == before  # restored
    assert dh.PLAYER_MAP_UNREAD == "refuse"
    with pytest.raises(RuntimeError), fp.player_owns_the_start(dh, said.append):
        raise RuntimeError("the runner failed")
    assert (dh.player_stock_refused, dh.player_slots_refused) == before  # restored on a fault too


def test_the_real_runner_s_refusals_are_the_ones_swapped() -> None:
    import dungeon_hunt as dh

    assert dh.player_stock_refused({601: None}, [504]) is not None  # its CLI keeps its rule
    with fp.player_owns_the_start(dh, lambda w: None):
        assert dh.player_stock_refused({601: None}, [504]) is None
    assert dh.player_stock_refused({601: None}, [504]) is not None


# -- a death: no hunting on ------------------------------------------------------------------------


def test_hp0_watch_dead_after_3_s_at_0_with_no_dialog() -> None:
    w = fp.Hp0Watch()
    assert not w.feed(0.0, 0, False) and not w.feed(2.9, None, False)  # an unread HP keeps it
    assert w.feed(fp.DEAD_HP0_S, 0, False)
    w2 = fp.Hp0Watch()
    assert not w2.feed(0.0, 0, False) and not w2.feed(2.0, 35, False)  # alive again: reset
    assert not w2.feed(4.0, 0, False) and w2.feed(7.0, 0, False)
    w3 = fp.Hp0Watch()  # the lab client's dialog recognised: the runner's own exit has it
    assert not any(w3.feed(t, 0, True) for t in (0.0, 5.0, 10.0))
    assert not fp.Hp0Watch().feed(10.0, None, False)  # never read: never dead by HP


def live_player(tmp_path: Path) -> tuple[fp.LivePlayer, tl.FakeIO]:
    p = tl.prep(tmp_path, [tl.forever([tl.wait(1.0)])])
    io_ = tl.FakeIO()
    demo = tmp_path / "demo"
    demo.mkdir()
    pl = fp.LivePlayer(p, io_, fp.SessionLog(demo, "t", io_.ns), stop_file=None, hunt=None)
    pl.start_world("xmas_dun02")
    return pl, io_


def test_in_the_hunt_her_hp_at_0_stops_the_runner_and_ends_the_run(tmp_path: Path) -> None:
    pl, io_ = live_player(tmp_path)
    res = fp.HuntResult()
    hook = fp.HuntHook(pl, res)
    zero = types.SimpleNamespace(hp_pct=0, dead=False)
    assert hook.tick(zero) is None
    io_.now += 2.9
    assert hook.tick(zero) is None
    io_.now += 0.2
    assert hook.tick(zero) == fp.DEAD_HP0_WORDS and res.dead and res.dead_hp0
    res2 = fp.HuntResult()
    hook2 = fp.HuntHook(pl, res2)
    for _ in range(3):  # the dialog recognised: the runner's own death exit (the respawn) plays
        io_.now += 5.0
        assert hook2.tick(types.SimpleNamespace(hp_pct=0, dead=True)) is None
    assert not res2.dead_hp0


def test_outside_the_hunt_her_hp_at_0_ends_the_run_as_dead(tmp_path: Path) -> None:
    pl, io_ = live_player(tmp_path)
    io_.w["hp_percent"] = 0
    io_.now += 1.0
    pl.read()
    io_.now += fp.DEAD_HP0_S
    with pytest.raises(_Halt) as e:
        pl.read()
    assert e.value.reason == "dead" and pl.words == fp.DEAD_HP0_WORDS


# -- Batt 2026-11-19 ~11:5x (asked): an unread weight warns; an unread map with her cell fitting --


WEIGHT_UNREAD = {"id": "weight", "ok": False, "refuses": True, "value": None,
                 "words": "the weight on Basic Info did not read, or reads red (>= 50 %): a "
                 "person first"}  # fmt: skip
CELL_FITS = {"id": "cell", "ok": None, "value": "(234, 144)",
             "words": "the map is not read from the minimap: look at the game -- is she on "
             "xmas_dun02? (her cell (234, 144) is on xmas_dun02's open ground, in reach of its "
             "search area, if she is)"}  # fmt: skip


def test_an_unread_weight_warns_and_a_read_or_red_one_still_refuses() -> None:
    (got,) = fr.hotbar_warnings([WEIGHT_UNREAD])
    assert got["refuses"] is False and fr.WEIGHT_WARN in got["words"]
    read = {**WEIGHT_UNREAD, "value": "62 %", "words": "weight 0.62 >= 0.5: lighten the bag"}
    assert fr.hotbar_warnings([read]) == [read]  # a weight READ over the limit refuses
    cell = {"id": "cell", "ok": True, "words": "the minimap is xmas_dun02's"}
    assert fp.check_refusal({"items": [got, cell]}) is None
    red = fp.red_weight({"items": [got, cell]}, red=True)
    assert fp.check_refusal(red) is not None and "RED" in str(fp.check_refusal(red))
    assert fp.red_weight({"items": [got]}, red=False) == {"items": [got]}


def test_an_unread_map_starts_only_when_her_cell_fits_the_node_map() -> None:
    assert fp.check_refusal({"items": [CELL_FITS]}) is None
    assert fp.start_warnings({"items": [CELL_FITS]}) == [fp.MAP_WARN]
    no_cell = {"id": "cell", "ok": None, "words": "the map's name did not read"}  # no hunt core
    assert fp.check_refusal({"items": [no_cell]}) is not None
    assert fp.start_warnings({"items": [no_cell]}) == []
    other = {**CELL_FITS, "ok": False, "words": "the minimap reads prontera's"}
    assert fp.check_refusal({"items": [other]}) is not None  # another map: always refuses


def test_the_runner_s_own_start_warns_on_an_unread_weight_and_map_only() -> None:
    import dungeon_hunt as dh

    said: list[str] = []
    assert dh.PLAYER_MAP_UNREAD == "refuse"
    with fp.player_owns_the_start(dh, said.append):
        assert dh.PLAYER_MAP_UNREAD == "warn"
        assert dh.player_weight_refused(None, False) is None and "did not read" in said[-1]
        assert dh.player_weight_refused(None, True) is not None  # drawn red: a heavy bag
        assert dh.player_weight_refused(0.9, False) is not None  # read over the limit
    assert dh.PLAYER_MAP_UNREAD == "refuse"
    assert dh.player_weight_refused(None, False) is not None  # its CLI keeps its rule


def test_the_etc_tab_rule_takes_the_player_s_own_start_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Batt 2026-11-21 21:4x: his live Run was refused at 48 % by the lab Rogue's fixed
    etc_hold_max (0.48) whatever his start tab's "refuse to start with the bag at" said."""
    import dungeon_hunt as dh

    rogue = {"etc_hold_max": 0.48}
    assert dh.etc_hold_refused(0.48, False, rogue) is not None  # its CLI keeps its rule
    with fp.player_owns_the_start(dh, lambda w: None):  # the default limit: as before
        assert dh.etc_hold_refused(0.48, False, rogue) is not None
    monkeypatch.setattr(dh, "WEIGHT_MAX", 0.74)  # his block at 74 %
    with fp.player_owns_the_start(dh, lambda w: None):
        assert dh.etc_hold_refused(0.48, False, rogue) is None
        assert dh.etc_hold_refused(0.60, True, rogue) is None  # read 60 %: the number decides
        assert dh.player_weight_refused(0.60, True) is None
        assert dh.etc_hold_refused(0.80, False, rogue) is not None  # over his own limit
        assert dh.etc_hold_refused(None, True, rogue) is not None  # red and unread: a person
    assert dh.etc_hold_refused(0.48, False, rogue) is not None  # restored


def test_the_log_says_why_the_weight_did_not_read(monkeypatch: pytest.MonkeyPatch) -> None:
    """Batt 2026-11-19 ("digits first"): the weight reader's own reason, in words with the
    symbols it read -- numbers only, no picture -- so another client's line says where it
    differs."""
    import gm_state

    from poring_env import weight as wt

    monkeypatch.setattr(gm_state, "_path", lambda: "rdp")
    monkeypatch.setattr(wt, "load_weight_glyphs", lambda path: "GLYPHS")
    g = [wt.Glyph(0, "1", 1.0, 0.4), wt.Glyph(7, "5", 1.0, 0.05)]
    monkeypatch.setattr(wt, "read_weight",
                        lambda frame, glyphs: wt.WeightReading(None, "ambiguous", 0.0, tuple(g),
                                                               (50, 3)))  # fmt: skip
    io_ = types.SimpleNamespace(frame=lambda: "FRAME")
    (line,) = fp.weight_diagnosis(io_)  # type: ignore[arg-type]
    assert line == (
        "the weight reader says ambiguous (a digit looks like two (another font)): "
        "the symbols read '15', the label at (50, 3), the closest call 0.05"
    )
    assert fp.weight_diagnosis(types.SimpleNamespace()) == [  # type: ignore[arg-type]
        "the weight reader did not run (AttributeError)"]  # fmt: skip


def test_the_heal_and_swap_lines_are_notes_on_the_flow_s_own_keys() -> None:
    """Batt 2026-11-21 ~22:0x: warn only on an EMPTY heal key (any item there is the player's
    choice); the weapon lines say what the flow swaps, on ITS keys -- never F1 / F4 / F5 fixed."""
    import flow_run as fr

    used = {"heal_key": "F2", "knife_key": "F6", "dagger_key": "F7"}
    wrong = {"id": "heals", "ok": False, "refuses": False, "value": "570 on F2",
             "words": "F2 shows a Yellow Potion, not a White Potion"}  # fmt: skip
    got = fr.heal_note(wrong, used)
    assert got["ok"] is True and got["info"] is True and got["words"].startswith("F2 holds 570")
    empty = {"id": "heals", "ok": False, "value": "0 heal items on F2", "words": "under 5"}
    got = fr.heal_note(empty, used)
    assert got["ok"] is False and not got.get("info") and got["words"].startswith("F2 is empty")
    assert fr.heal_note({"id": "heals", "ok": True, "words": "fine"}, used)["words"] == "fine"
    knife = fr.swap_note({"id": "knife", "ok": False, "words": "F6 draws a count None"}, used)
    assert knife["info"] is True and knife["ok"] is False  # ok kept: knife_swap_off reads it
    assert "F6 and F7" in knife["words"] and "plays without the swap" in knife["words"]
    dagger = fr.swap_note({"id": "dagger", "ok": True, "words": "F7 empty"}, used)
    assert "F7: the fighting weapon" in dagger["words"] and "without" not in dagger["words"]
    out = fr.hotbar_notes([wrong, knife, {"id": "wings", "ok": True}], used)
    assert [i.get("info") for i in out] == [True, True, None]


def test_the_log_and_the_summary_call_them_notes() -> None:
    got = {"items": [{"id": "heals", "ok": True, "info": True, "words": "F1 holds 570"},
                     {"id": "knife", "ok": False, "info": True, "refuses": False, "words": "swaps"},
                     {"id": "weight", "ok": False, "words": "heavy"}]}  # fmt: skip
    lines = fp.check_lines(got)
    assert lines[0].startswith("check NOTE heals") and lines[1].startswith("check NOTE knife")
    summary = fp.check_summary(got)
    assert "0 of 1 lines pass; FAIL: weight" in summary and "notes: heals, knife" in summary
