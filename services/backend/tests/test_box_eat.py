"""The box eats from the hotbar (Batt 2026-11-14 ~14:0x: "Raise the drink. And the moment we get a
Candy Cane or a Candy, eat it to add HP right away; that also cuts the weight";
docs/planning/live-blocks.md section 10; dungeon@9.52).

Offline, no game, no client pixels: the new sensor hotbar_count(key) is read by the REAL player
(flow_play.LivePlayer, through its LiveIO seam) from the runner's tick frame -- here a fake frame
that names each slot's count, read by a fake IO -- and the runner's reader itself
(hotbar_count.read_count) is stubbed or fed synthetic pixels. The REAL player's hook plays the
box's events; a fake hunt loop stands in for dungeon_hunt.run at its survival point (as
test_survival_events.py's), and the runner's own box_press is run from its source with fakes
around it (its AST is checked)."""

from __future__ import annotations

import ast
import copy
import inspect
import json
import sys
import textwrap
from collections import Counter
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts"))

import dungeon_hunt as dh  # noqa: E402
import flow_play as fp  # noqa: E402
import hotbar_count as hb  # noqa: E402

from poring_flow import functions as fn  # noqa: E402
from poring_flow import live  # noqa: E402
from poring_flow import project as pj  # noqa: E402
from poring_flow.trace import Scenario  # noqa: E402

FIX = ROOT / "services/frontend/src/lib/flow/fixtures"
ONE = FIX / "project_xmas_dun02.json"  # the one box: the drink at 50 %, the candies eaten
B4 = FIX / "project_xmas_dun02_stage4.json"  # the box as stage 4a left it (stage4_ab.py's B4)
TICK = 0.4  # the runner's main tick on xmas_dun02 (~2.4 a second)


def lit(v: Any) -> dict[str, Any]:
    return {"kind": "lit", "value": v}


def press(k: Any) -> dict[str, Any]:
    return {"kind": "action", "block": "press_key", "concept": "ui.press_hotkey",
            "params": {"key": k if isinstance(k, dict) else lit(k)}, "timeout_s": 2.0,
            "on_fail": "stop", "outcome_to": None, "note": None}  # fmt: skip


def call(p: str, *args: str) -> dict[str, Any]:
    return {"kind": "call", "proc": p, "args": [lit(a) for a in args], "kwargs": {}}


def hotbar(k: Any) -> dict[str, Any]:
    return {"kind": "sense", "sensor": "hotbar_count", "args": {"key": k if isinstance(k, dict)
                                                                else lit(k)}}  # fmt: skip


def box(path: Path = ONE) -> dict[str, Any]:
    d = json.loads(path.read_text())
    d["max_runtime_s"] = 600
    return d


def tab(d: dict[str, Any], name: str) -> dict[str, Any]:
    return next(t for t in d["nodes"][0]["tabs"] if t["name"] == name)


def fdef(d: dict[str, Any], tab_: str, name: str) -> dict[str, Any]:
    return next(x for x in tab(d, tab_)["defs"] if x["name"] == name)


def hunt_params(d: dict[str, Any]) -> dict[str, Any]:
    return dict(next(s for s in tab(d, "main")["main"] if s.get("block") == "dungeon_hunt")[
        "params"])  # fmt: skip


def prep(tmp_path: Path, d: dict[str, Any]) -> fp.Prepared:
    got = fp.prepare(json.dumps(d), "xmas_dun02", 3600, config_dir=tmp_path)
    assert isinstance(got, fp.Prepared), got
    return got


def refused(tmp_path: Path, d: dict[str, Any]) -> str:
    got = fp.prepare(json.dumps(d), "xmas_dun02", 3600, config_dir=tmp_path)
    assert isinstance(got, str) and "refused before any input" in got, got
    c = pj.compile_project(pj.from_json(json.dumps(d)))
    assert c.flow is not None and live.problems(c.flow)  # the backend's not_live: the same
    return got


class FakeIO(fp.LiveIO):
    """A fake clock; every input recorded; a FRAME is a dict naming each slot's count (the fake
    reader below reads it): no client pixels."""

    def __init__(self) -> None:
        self.now = 0.0
        self.out: list[tuple[Any, ...]] = []
        self.reads: list[tuple[float, tuple[str, ...]]] = []  # (time, keys) of each hotbar read
        self.agent, self.screen = "AGENT", "SCREEN"

    def clock(self) -> float:
        return self.now

    def sleep(self, s: float) -> None:
        self.now += s

    def ns(self) -> int:
        return int(self.now * 1e9)

    def senses(self) -> dict[str, Any]:
        return {"hp_percent": 100, "sp_percent": 100, "weight_percent": 10, "is_dead": False,
                "map": "xmas_dun02"}  # fmt: skip

    def open(self) -> None:
        self.out.append(("open",))

    def ui_clear(self) -> None:
        self.out.append(("ui_clear",))

    def tap(self, code: str) -> None:
        self.out.append(("tap", code))

    def release(self) -> None:
        self.out.append(("release",))

    def hotbar_counts(self, frame: Any, keys: Sequence[str]) -> dict[str, int | None]:
        self.reads.append((round(self.now, 2), tuple(keys)))
        return {k: frame.get(k) for k in keys}


def ok_check(_p: Any, _io: Any) -> dict[str, Any]:
    return {"items": [{"id": "cell", "ok": True, "words": "-"}], "ok": True}


# A tick of the fake loop: (HP percent or None, the frame: a slot -> its count)
Tick = tuple[int | None, dict[str, int | None] | None]


class HuntLoop:
    """dungeon_hunt.run(a, hook=..., session=..., **box) at its survival point: ``ticks`` one TICK
    apart, each with its frame. ``port`` is the runner's own press of a box key (box_press: the
    heal, the Fly Wing and the keys the box eats; anything else refused)."""

    def __init__(self, io_: FakeIO, ticks: list[Tick]) -> None:
        self.io, self.ticks = io_, ticks
        self.kw: dict[str, Any] = {}
        self.port: list[tuple[int, str, str, str]] = []  # (tick, role, key, why)
        self.refused: list[str] = []
        self.hook: Any = None

    def __call__(self, a: Any, *, hook: Any = None, session: Any = None, **kw: Any) -> int:
        self.kw, self.hook = kw, hook
        plays = frozenset(kw.get("box_plays", ()))
        roles = {"F1": "potion", "F8": "fly", **{k: "eat" for k in kw.get("box_eat", ())}}
        tick_i = -1

        def port(code: str, why: str) -> str | None:
            role = roles.get(code)
            if role is None:
                self.refused.append(code)
                return None
            self.port.append((tick_i, role, code, why))
            hook.event({"kind": "press", "what": role, "key": code, "why": why}, self.io.now)
            self.io.now += 0.1  # the runner's paced tap (agent.keys)
            return role

        hook.event({"kind": "run_start", "map": "xmas_dun02"}, self.io.now)
        for tick_i, (hp, frame) in enumerate(self.ticks):  # noqa: B007 -- port reads it
            self.io.now += TICK
            view = dh.HuntTick(self.io.now, hp, 60, False, (10, 10), "search", {}, frame)
            assert dh.hook_stop(hook, view) is None
            if plays:
                assert dh.hook_survive(hook, view, port) is None
        hook.event({"kind": "run_end", "reason": "time_box", "counts": {}}, self.io.now)
        hook.event({"kind": "player_end", "reason": "time_box", "home": False, "dead": False,
                    "respawned": False}, self.io.now)  # fmt: skip
        return 0


def play(tmp_path: Path, ticks: list[Tick], d: dict[str, Any] | None = None
         ) -> tuple[HuntLoop, FakeIO, list[dict[str, Any]]]:  # fmt: skip
    p = prep(tmp_path, d if d is not None else box())
    io_ = FakeIO()
    loop = HuntLoop(io_, ticks)
    demo = tmp_path / "demo"
    demo.mkdir()
    fp.play(p, io_, label="eat", stop_file=None, demo=demo, checker=ok_check,
            hunt=fp.HuntCore("eat", None, run_fn=loop))  # fmt: skip
    (s,) = list(demo.iterdir())
    return loop, io_, [json.loads(x) for x in (s / "events.jsonl").read_text().splitlines()]


def eats(loop: HuntLoop) -> list[tuple[int, str]]:
    return [(i, k) for i, r, k, _ in loop.port if r == "eat"]


# --- the box and what it hands over ---------------------------------------------------------------
def test_the_one_box_eats_both_candies_drinks_under_50_and_hands_the_eat_keys_over(
    tmp_path: Path,
) -> None:
    p = pj.from_json(ONE.read_text())
    c, found = pj.project_lint(p)
    assert [f.text for f in found if f.severity == "error"] == []
    # the same four warnings as the stage-4a box (an eat key's press goes through eat(key))
    warn = sorted(f.rule for f in found if f.severity == "warning")
    _c4, found4 = pj.project_lint(pj.from_json(B4.read_text()))
    assert warn == sorted(f.rule for f in found4 if f.severity == "warning") and len(warn) == 4
    assert c.flow is not None and live.problems(c.flow) == []
    plan = live.hunt_plan(c.flow, "xmas_dun02")
    assert plan.events == ("fly_away", "drink", "bag_full", "eat_cane", "eat_candy")
    assert (plan.eat_keys, plan.eat_name, plan.hotbar_keys) == (("F6", "F7"), "eat", ("F6", "F7"))
    assert plan.play_by["eat"] == ("eat_cane", "eat_candy")
    drink = fdef(box(), "survival", "drink")["on"]
    assert (drink["when"]["right"], drink["until"]["right"]) == (lit(50), lit(51))
    rp, rp4 = prep(tmp_path, box()).runners["xmas_dun02"], prep(tmp_path, box(B4)).runners[
        "xmas_dun02"]  # fmt: skip
    assert rp.plays == rp4.plays | {"eat"}
    # the same runner argv (the same five keys: an eat key is no Run key), the box's eat keys
    assert rp.argv("x", None, None) == rp4.argv("x", None, None) and rp.keys == rp4.keys
    kw, kw4 = rp.box_kwargs(), rp4.box_kwargs()
    assert kw == {**kw4, "box_plays": sorted(rp4.plays | {"eat"}), "box_eat": ["F6", "F7"]}
    doc = prep(tmp_path, box()).doc()["runners"]["xmas_dun02"]
    assert (doc["box_eat"], doc["eat"], doc["hotbar_keys"]) == (["F6", "F7"], "eat", ["F6", "F7"])
    assert "box_eat" not in prep(tmp_path, box(B4)).doc()["runners"]["xmas_dun02"]
    assert prep(tmp_path, box()).roles["F6"] == prep(tmp_path, box()).roles["F7"] == "eat"


def test_the_one_box_is_its_stage_4a_self_but_for_the_drink_and_the_eat(tmp_path: Path) -> None:
    """The one box = the stage-4a box with Batt's two answers and nothing else."""
    d, d4 = box(), box(B4)
    for t in (*d["nodes"][0]["tabs"], *d4["nodes"][0]["tabs"]):
        for x in t["defs"]:
            if x["name"] == "drink":
                x["on"]["when"]["right"], x["on"]["until"]["right"] = lit(0), lit(1)
    tab(d, "keys")["defs"] = tab(d, "keys")["defs"][:-3]
    tab(d, "survival")["defs"] = tab(d, "survival")["defs"][:-2]
    hunt = next(s for s in tab(d, "main")["main"] if s.get("block") == "dungeon_hunt")
    del hunt["params"]["eat"]
    d["description"] = d4["description"]
    assert pj.canonical_json(pj.validate(d)) == pj.canonical_json(pj.validate(d4))


# --- the sensor: read from the tick's frame, rate-limited, unknown when unread ------------------
def test_a_count_on_the_slot_is_eaten_at_once_one_by_one_until_the_slot_reads_empty(
    tmp_path: Path,
) -> None:
    # F6 shows 2 Candy Canes, then 1, then 0 (the client draws each eat); F7 stays empty
    frames: list[dict[str, int | None]] = (
        [{"F6": 2, "F7": 0}] * 4 + [{"F6": 1, "F7": 0}] * 4 + [{"F6": 0, "F7": 0}] * 6
    )
    loop, io_, ev = play(tmp_path, [(100, f) for f in frames])
    got = eats(loop)
    assert [k for _, k in got] == ["F6", "F6"]  # both canes, at full HP, none after the empty read
    assert loop.port[0][3] == "box eat_cane (hotbar_count(F6) 2)"
    # paced by the event's cooldown (1.5 s from its last body run), never every tick
    t = [i * TICK for i, _ in got]
    assert t[1] - t[0] >= 1.5 - 1e-9 and loop.refused == []
    assert not [r for _i, r, _k, _w in loop.port if r != "eat"]  # no potion, no Fly Wing at 100 %
    fired = [(e["event"], e["mode"], e["in"], e["reading"]) for e in ev if e["kind"] == "event"]
    assert fired[0] == ("eat_cane", "insert", "hunt", {"hotbar_count(F6)": 2})
    assert [f[0] for f in fired] == ["eat_cane", "eat_cane"]
    # the press records, mirrored (the live line), and the key records: inside the hunt core
    assert [e["key"] for e in ev if e["kind"] == "press" and e.get("what") == "eat"] == ["F6"] * 2
    assert [e for e in ev if e["kind"] == "key"] and {
        e.get("in") for e in ev if e["kind"] == "key"
    } == {"hunt"}
    start = next(e for e in ev if e["kind"] == "hunt_start")
    assert start["box_eat"] == ["F6", "F7"] and start["hotbar_keys"] == ["F6", "F7"]
    assert loop.kw["box_eat"] == ["F6", "F7"] and "eat" in loop.kw["box_plays"]
    # outside the hunt core the count is unknown again
    world = loop.hook.player.world
    assert world["hotbar:F6"] is None and world["hotbar:F7"] is None
    assert io_.out[-1] == ("release",)


def test_the_count_is_read_at_most_once_a_second_a_key_and_kept_between_reads(
    tmp_path: Path,
) -> None:
    loop, io_, _ev = play(tmp_path, [(100, {"F6": 0, "F7": 0})] * 10)  # 4 s of ticks
    assert fp.HOTBAR_EVERY_S == 1.0
    assert [k for _t, k in io_.reads] == [("F6", "F7")] * 4  # only the keys the events name
    gaps = [b - a for (a, _), (b, _) in zip(io_.reads, io_.reads[1:], strict=False)]
    assert all(g >= fp.HOTBAR_EVERY_S - 1e-9 for g in gaps)
    assert eats(loop) == []  # 0 = an empty slot: nothing to eat
    # the count is kept between reads: a slot that changes between two reads is seen at the next
    (tmp_path / "b").mkdir()
    frames = [{"F6": 0, "F7": 0}, {"F6": 1, "F7": 0}, {"F6": 1, "F7": 0}, {"F6": 1, "F7": 0}]
    loop2, io2, _ = play(tmp_path / "b", [(100, f) for f in frames])
    assert eats(loop2) == [(3, "F6")] and len(io2.reads) == 2  # read at ticks 0 and 3


def test_an_unreadable_count_never_fires_and_a_repeating_eat_pauses_on_it(tmp_path: Path) -> None:
    loop, _io, ev = play(tmp_path, [(100, {"F6": None, "F7": None})] * 8)
    assert eats(loop) == [] and not [e for e in ev if e["kind"] == "event"]
    # 2 canes: one eaten; then the slot cannot be read for 3 s: no press on a stale or unknown
    # count; it reads 1 again: the second
    (tmp_path / "p").mkdir()
    frames = [{"F6": 2, "F7": 0}] + [{"F6": None, "F7": 0}] * 10 + [{"F6": 1, "F7": 0}] * 3
    loop2, io2, _ev2 = play(tmp_path / "p", [(100, f) for f in frames])
    assert eats(loop2) == [(0, "F6"), (eats(loop2)[1][0], "F6")] and eats(loop2)[1][0] >= 11
    assert len(io2.reads) >= 5  # it kept reading while unknown (every second), and saw the 1


def test_the_eat_needs_no_hp_read_and_the_drink_still_does(tmp_path: Path) -> None:
    # no HP read on any tick (the HP line hidden): the candy is still eaten from its count; the
    # drink and the Fly Wing decide nothing without an HP read (stage 2's rule)
    loop, _io, ev = play(tmp_path, [(None, {"F6": 0, "F7": 1})] * 3)
    assert eats(loop) == [(0, "F7")]
    assert [e["event"] for e in ev if e["kind"] == "event"] == ["eat_candy"]
    # with HP under 50 % the drink comes first (survival before upkeep), then the candy
    (tmp_path / "h").mkdir()
    loop2, _io2, _ = play(tmp_path / "h", [(45, {"F6": 0, "F7": 1})])
    assert [(r, k) for _i, r, k, _w in loop2.port] == [("potion", "F1"), ("eat", "F7")]
    assert loop2.port[0][3] == "box drink (hp_percent 45)"


def test_a_frame_less_tick_reads_no_count_and_decides_nothing_new(tmp_path: Path) -> None:
    loop, io_, _ev = play(tmp_path, [(100, None)] * 4)
    assert io_.reads == [] and eats(loop) == []


def test_the_reader_is_the_runners_own_on_the_frames_top_rows() -> None:
    """flow_play.read_hotbar: hotbar_count.read_count on hotbar_count.gray of the frame's top rows,
    each key's row-1 slot by dungeon_hunt.hotbar_slot (stubbed here: no client pixels)."""
    seen: list[tuple[tuple[int, ...], int, dict[str, Any]]] = []

    def fake_read(g: Any, slot: int, tpl: dict[str, Any]) -> int | None:
        seen.append((g.shape, slot, tpl))
        return {5: 2, 6: 7}.get(slot)

    frame = np.full((720, 1280, 3), 200, np.uint8)
    saved = hb.read_count
    try:
        hb.read_count = fake_read  # type: ignore[assignment]
        got = fp.read_hotbar(frame, ["F6", "F7", "F1"], {"1": "tpl"})
    finally:
        hb.read_count = saved  # type: ignore[assignment]
    assert got == {"F6": 2, "F7": 7, "F1": None}
    assert [s for _g, s, _t in seen] == [5, 6, 0] and seen[0][0] == (fp.HOTBAR_ROWS, 1280)
    assert seen[0][2] == {"1": "tpl"}
    assert fp.read_hotbar(None, ["F6"], {}) == {"F6": None}


def test_the_real_reader_reads_an_empty_slot_0_and_a_slot_it_cannot_read_none() -> None:
    """Synthetic pixels only (never the client's): a white slot is EMPTY (0); a dark mark in the
    count box that no template matches is unreadable (None, never a guess)."""
    frame = np.full((720, 1280, 3), 230, np.uint8)
    assert fp.read_hotbar(frame, ["F6", "F7"], {}) == {"F6": 0, "F7": 0}
    x0, y0, x1, y1 = hb.box(dh.hotbar_slot("F7"))
    frame[y0:y1, x0 + 4 : x0 + 7] = 0  # a 3-column ink mark, full height: a glyph, no template
    assert fp.read_hotbar(frame, ["F6", "F7"], {}) == {"F6": 0, "F7": None}


def test_pixelio_loads_the_digit_templates_at_run_time_once(monkeypatch: Any) -> None:
    pio = object.__new__(fp.PixelIO)  # its reader only: no Screen, no Agent
    pio._hb_tpl = None
    loads: list[int] = []

    def load() -> dict[str, Any]:
        loads.append(1)
        return {"7": np.ones((9, 4), bool)}

    monkeypatch.setattr(hb, "load", load)
    monkeypatch.setattr(hb, "read_count", lambda g, slot, tpl: len(tpl))
    assert pio.hotbar_counts(np.zeros((720, 1280, 3), np.uint8), ["F6"]) == {"F6": 1}
    assert pio.hotbar_counts(np.zeros((720, 1280, 3), np.uint8), ["F7"]) == {"F7": 1}
    assert loads == [1]  # once, at the first read (data/hotbar/digits.npz: never in git)
    pio2 = object.__new__(fp.PixelIO)
    pio2._hb_tpl = None

    def missing() -> dict[str, Any]:
        raise FileNotFoundError("data/hotbar/digits.npz")

    monkeypatch.setattr(hb, "load", missing)
    assert pio2.hotbar_counts(np.zeros((720, 1280, 3), np.uint8), ["F6"]) == {"F6": 0}
    assert fp.LiveIO().hotbar_counts({}, ["F6"]) == {"F6": None}  # the interface reads none


def test_the_simulator_reads_hotbar_count_from_the_scenario() -> None:
    p = pj.from_json(ONE.read_text())
    # the simulated hunt core runs 1.2-2.5 s: a cane scripted at 1.5 s is eaten there (F6's press
    # inside it), and the slot scripted empty at 2.2 s ends the repeat (its until)
    sc = Scenario(horizon_s=60, timeline=[{"t": 1.5, "hotbar": {"F6": 2}},
                                          {"t": 2.2, "hotbar": {"F6": 0}}])  # fmt: skip
    doc = pj.simulate(p, None, sc)
    fired = [(e["t"], e["what"]) for e in doc["events"] if e["kind"] == "fire"]
    assert fired == [(1.5, "eat_cane")]
    assert [(e["t"], e["what"]) for e in doc["events"] if e["kind"] == "until"] == [
        (2.2, "eat_cane")]  # fmt: skip
    hunt = next(s for s in doc["play"] if s.get("action") == "dungeon_hunt")
    eat = next(s for s in doc["play"] if s.get("action") == "press_key")
    assert hunt["t0"] <= eat["t0"] <= hunt["t1"]
    # no hotbar scripted: every slot the box reads starts empty (0): nothing is eaten
    quiet = pj.simulate(p, None, Scenario(horizon_s=60))
    assert not [e for e in quiet["events"] if e["kind"] == "fire" and e["what"].startswith("eat")]
    with pytest.raises(ValueError):
        Scenario(timeline=[{"t": 1.0, "hotbar": {"F10": 1}}])


# --- what the box may write: refused before any input, named -------------------------------------
@pytest.mark.parametrize(("key", "role"), [("F1", "heal"), ("F8", "fly"), ("F4", "knife_on"),
                                           ("F5", "knife_back"), ("F9", "home")])  # fmt: skip
def test_an_eat_key_that_is_another_roles_key_is_refused(tmp_path: Path, key: str,
                                                         role: str) -> None:  # fmt: skip
    d = box()
    fdef(d, "keys", "candy_cane")["body"] = [call("eat", key)]
    ev = fdef(d, "survival", "eat_cane")["on"]
    ev["when"]["left"] = ev["until"]["left"] = hotbar(key)
    got = refused(tmp_path, d)
    assert f"eats {key} through eat() inside the hunt core: {key} is dungeon_hunt's {role} key" \
           in got, got  # fmt: skip
    # the editor's lint names it too
    _c, found = pj.project_lint(pj.from_json(json.dumps(d)))
    assert any(f.rule == "hotbar_keys" and f"eats {key}" in f.text for f in found
               if f.severity == "error")  # fmt: skip


def test_an_eat_event_must_eat_from_the_slot_it_reads(tmp_path: Path) -> None:
    d = box()
    fdef(d, "keys", "candy_cane")["body"] = [call("eat", "F3")]  # a person moved the canes ...
    got = refused(tmp_path, d)  # ... and left eat_cane reading F6
    assert ("eat_cane eats F3 but its condition reads hotbar_count of F6: the count it reads is "
            "not the slot it eats from") in got, got  # fmt: skip


def test_the_other_shapes_inside_the_hunt_core_are_refused(tmp_path: Path) -> None:
    cases: list[tuple[Callable[[dict[str, Any]], None], str]] = [
        # a direct press of the candy's key, not through the eat function
        (lambda d: fdef(d, "survival", "eat_cane").update(body=[press("F6")]),
         "presses F6 inside the hunt core: there the box presses only dungeon_hunt's heal (F1) "
         "and fly (F8) keys, and what its eat function eat() eats"),
        # a count read on a key not known before the run
        (lambda d: fdef(d, "survival", "eat_cane")["on"].update(
            when={"kind": "cmp", "op": ">", "left": hotbar({"kind": "var", "name": "k"}),
                  "right": lit(0)}),
         "hotbar_count() inside the hunt core reads a literal row-1 hotbar key"),
        # an eat function that presses two keys
        (lambda d: fdef(d, "keys", "eat").update(body=[press({"kind": "var", "name": "key"}),
                                                       press("F2")]),
         "dungeon_hunt's eat (eat): eat's body is not exactly one press_key"),
        # an eat role naming no function
        (lambda d: next(s for s in tab(d, "main")["main"] if s.get("block") == "dungeon_hunt")[
            "params"].update(eat=lit("nibble")),
         "dungeon_hunt's eat (nibble): there is no function nibble"),
    ]  # fmt: skip
    for i, (mutate, words) in enumerate(cases):
        d = copy.deepcopy(box())
        mutate(d)
        got = fp.prepare(json.dumps(d), "xmas_dun02", 3600, config_dir=tmp_path)
        assert isinstance(got, str) and "refused before any input" in got, (i, got)
        assert words in got, (i, got)
    assert not list(tmp_path.glob("*"))  # pure: no session, no input path


def test_without_the_eat_role_the_box_eats_nothing_and_plays_as_stage_4a(tmp_path: Path) -> None:
    d = box()
    next(s for s in tab(d, "main")["main"] if s.get("block") == "dungeon_hunt")["params"].pop("eat")
    tab(d, "survival")["defs"] = tab(d, "survival")["defs"][:-2]
    rp, rp4 = prep(tmp_path, d).runners["xmas_dun02"], prep(tmp_path, box(B4)).runners[
        "xmas_dun02"]  # fmt: skip
    assert rp.box_kwargs() == rp4.box_kwargs()  # no box_eat, no "eat": exactly 9.51's run() call
    assert (rp.eat_keys, rp.hotbar_keys) == ((), ())
    assert "eat" in hunt_params(box()) and "eat" not in hunt_params(d)


# --- the runner: its own press path for the eat keys, every other key refused -------------------
def _box_press() -> Callable[..., Any]:
    """run()'s box_press, from its own source, with fakes for what it closes over."""
    bp = next(n for n in ast.walk(ast.parse(textwrap.dedent(inspect.getsource(dh.run))))
              if isinstance(n, ast.FunctionDef) and n.name == "box_press")  # fmt: skip
    src = ("def make(box_keys, press, counts, ev, agent_raw, box_pressed):\n"
           "    sitting = False\n" + textwrap.indent(ast.unparse(bp), "    ") +
           "\n    return box_press\n")  # fmt: skip
    ns: dict[str, Any] = {}
    exec(compile(src, "dungeon_hunt.run.box_press", "exec"), ns)  # noqa: S102 -- its own source
    return ns["make"]  # type: ignore[no-any-return]


def test_box_press_eats_through_the_runners_key_path_and_still_refuses_any_other_key() -> None:
    sent: list[str] = []
    pressed: list[tuple[str, str]] = []
    counts: Counter[str] = Counter()
    evs: list[dict[str, Any]] = []

    class Agent:
        def keys(self, code: str) -> None:
            sent.append(code)

    box_pressed: list[tuple[str, str]] = []
    bp = _box_press()({"F1": "potion", "F8": "fly", "F6": "eat", "F7": "eat"},
                      lambda what, why: pressed.append((what, why)), counts, evs.append, Agent(),
                      box_pressed)  # fmt: skip
    assert bp("F6", "box eat_cane (hotbar_count(F6) 2)") == "eat"
    assert sent == ["F6"] and pressed == []  # the key path itself, not press(): no stock read
    assert (counts["eat"], counts["box_eat"]) == (1, 1)
    assert evs == [{"kind": "press", "what": "eat", "key": "F6",
                    "why": "box eat_cane (hotbar_count(F6) 2)"}]  # fmt: skip
    assert box_pressed == [("eat", "box eat_cane (hotbar_count(F6) 2)")]
    assert bp("F1", "box drink (hp_percent 45)") == "potion"
    assert pressed == [("potion", "box drink (hp_percent 45)")] and counts["box_potion"] == 1
    assert bp("F3", "box x") is None and sent == ["F6"]  # any other key: refused, not pressed
    assert counts["box_refused"] == 1 and evs[-1] == {"kind": "box_refused", "key": "F3",
                                                      "why": "box x"}  # fmt: skip


def test_the_runner_hands_the_box_its_eat_keys_and_never_reads_them_as_its_own() -> None:
    run_src = textwrap.dedent(inspect.getsource(dh.run))
    tree = ast.parse(run_src)
    built = next(n for n in ast.walk(tree) if isinstance(n, ast.If)
                 and ast.unparse(n.test) == "'eat' in box_set")  # fmt: skip
    assert ast.unparse(built.body[0]) == "box_keys.update({k: 'eat' for k in box_eat_})"
    # no key map, slot read or stock of the run is built from the eat keys
    for n in ast.walk(tree):  # box_eat feeds only its own copy and the refusal check
        if isinstance(n, ast.Assign) and "box_eat" in ast.unparse(n.value):
            assert [ast.unparse(t) for t in n.targets] in (["box_eat_"], ["why_bx"], ["version"]), (
                ast.unparse(n)
            )
    for name in ("keys_", "stock_items", "slot_roles", "stock_watch"):
        for n in ast.walk(tree):
            if isinstance(n, ast.Assign) and name in [ast.unparse(t) for t in n.targets]:
                assert "eat" not in ast.unparse(n.value), ast.unparse(n)
    rec = next(n for n in ast.walk(tree) if isinstance(n, ast.Dict)
               and "'box_eat'" in [ast.unparse(k) for k in n.keys if k is not None])  # fmt: skip
    assert "BOX_EAT_VERSION" in ast.unparse(rec)  # run_start: box_eat and its version
    # the slot check reads its own roles only
    assert dh.slot_role_keys({"potion": "F1", "fly": "F8", "home": "F9", "equip": "F5"}, False,
                             "F4", True) == {"fly": "F8", "potion": "F1", "home": "F9",
                                             "opener": "F4"}  # fmt: skip


def test_eat_refused_names_each_refusal_before_any_input() -> None:
    class Hook:
        def survive(self, view: Any, press: Any) -> str | None:
            return None

    keys = {"potion": "F1", "fly": "F8", "sit": "Insert", "stand": "Insert", "equip": "F5",
            "home": "F9"}  # fmt: skip
    kw: dict[str, Any] = {"heal_candy": False, "boss_walk": False, "bosses": ("Stormy Knight",),
                          "keys": keys, "opener": "F4"}  # fmt: skip
    ok = dh.box_plays_refused(["eat", "potion"], Hook(), eat=["F6", "F7"], **kw)
    assert ok is None
    assert "goes with box_eat" in str(dh.box_plays_refused(["eat"], Hook(), **kw))
    assert "goes with box_eat" in str(dh.box_plays_refused(["potion"], Hook(), eat=["F6"], **kw))
    assert "not a row-1 hotbar key" in str(dh.box_plays_refused(["eat"], Hook(), eat=["F10"],
                                                                **kw))  # fmt: skip
    assert "each key once" in str(dh.box_plays_refused(["eat"], Hook(), eat=["F6", "F6"], **kw))
    assert "one candy eater" in str(dh.box_plays_refused(["eat"], Hook(), eat=["F6"],
                                                         **{**kw, "heal_candy": True}))  # fmt: skip
    for k, who in (("F1", "potion"), ("F8", "fly"), ("F5", "equip"), ("F9", "home"),
                   ("F4", "--steal-opener")):  # fmt: skip
        why = str(dh.box_plays_refused(["eat"], Hook(), eat=[k], **kw))
        assert why.startswith("the box's eat keys: ") and f"{k} is set for" in why, why
        assert who in why and "the box's eat" in why
    assert dh.eat_refused([], [], keys, "F4", heal_candy=False) is None  # the CLI: none


def test_the_cli_and_the_old_run_path_are_unchanged() -> None:
    sig = inspect.signature(dh.run)
    assert sig.parameters["box_eat"].default == ()
    assert "return run(a)" in inspect.getsource(dh.main)  # no hook, no box
    assert dh.VERSION == "dungeon@8.7" and dh.BOX_EAT_VERSION == live.VERSION == "9.52"
    assert dh.BOX_PLAYS == live.PLAYS and "eat" in dh.BOX_PLAYS
    assert dh.HEAL_CANDY_KEYS == {"cane": "F6", "candy": "F7"}  # the runner's own flag: untouched
    import runner_flow_export as rfe

    assert "BOX_EAT_VERSION" in rfe.NOT_FEATURES
    assert fn.EAT_ROLE == "eat" and fn.HOTBAR_SENSOR == "hotbar_count"
