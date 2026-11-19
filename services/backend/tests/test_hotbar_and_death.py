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


def test_a_knife_slot_that_does_not_read_right_plays_without_the_knife_swap() -> None:
    prep = types.SimpleNamespace(runners={"field": plan(True)})
    knife = {"id": "knife", "ok": False, "words": "the F4 slot draws a count None"}
    words = fp.knife_swap_off(prep, {"items": [knife]})  # type: ignore[arg-type]
    assert prep.runners["field"].vals == {"knife_swap": False, "heal_key": "F1"}
    assert len(words) == 1 and "WITHOUT the Knife swap" in words[0] and "knife" in words[0]
    assert "--bare-steal" not in fp.fc.argv(prep.runners["field"].vals)
    ok = types.SimpleNamespace(runners={"field": plan(True)})
    assert fp.knife_swap_off(ok, {"items": [{**knife, "ok": True}]}) == []  # type: ignore[arg-type]
    assert ok.runners["field"].vals["knife_swap"] is True
    off = types.SimpleNamespace(runners={"field": plan(False)})
    assert fp.knife_swap_off(off, {"items": [knife]}) == []  # type: ignore[arg-type]


def test_the_runner_s_own_start_lets_the_hotbar_pass_inside_the_player_only() -> None:
    dh = types.SimpleNamespace(
        player_stock_refused=lambda counts, heals: "no Fly Wing read",
        player_slots_refused=lambda states: "F1 shows another item",
    )
    before = (dh.player_stock_refused, dh.player_slots_refused)
    said: list[str] = []
    with fp.hotbar_is_the_players(dh, said.append):
        assert dh.player_stock_refused({601: None}, [504]) is None
        assert dh.player_slots_refused({}) is None
    assert said == ["WARNING (the hotbar, the player's own; the Run plays on): no Fly Wing read",
                    "WARNING (the hotbar, the player's own; the Run plays on): F1 shows another "
                    "item"]  # fmt: skip
    assert (dh.player_stock_refused, dh.player_slots_refused) == before  # restored
    with pytest.raises(RuntimeError), fp.hotbar_is_the_players(dh, said.append):
        raise RuntimeError("the runner failed")
    assert (dh.player_stock_refused, dh.player_slots_refused) == before  # restored on a fault too


def test_the_real_runner_s_refusals_are_the_ones_swapped() -> None:
    import dungeon_hunt as dh

    assert dh.player_stock_refused({601: None}, [504]) is not None  # its CLI keeps its rule
    with fp.hotbar_is_the_players(dh, lambda w: None):
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
