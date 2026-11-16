"""dungeon@9.57 --fly-first (docs/planning/live-blocks.md 18; Batt 2026-11-16, 17 item 6: "A boss on
the screen, at ANY distance: press the Fly Wing first, no Knife swap").

Offline, no game. The pure helpers by their values; run()'s closures BY EXECUTION -- each one's
own source, taken from run()'s AST, run in a namespace of fakes (the keys recorded in the order
they would go out); the loop's structure with the flag off and on (huntstate_check.driver_loop);
and the proofs: every fly-first change is a branch whose else is today's code, and a change
outside a branch is refused."""

from __future__ import annotations

import ast
import contextlib
import io
import subprocess
import sys
import textwrap
import time
from collections import Counter
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts"))

import dungeon_hunt as dh  # noqa: E402
import huntstate_check as hc  # noqa: E402
import unit_detector as ud  # noqa: E402

SRC = hc.TARGET.read_text()


def _run_fn() -> ast.FunctionDef:
    return next(
        n for n in ast.parse(SRC).body if isinstance(n, ast.FunctionDef) and n.name == "run"
    )


def closure(name: str, ns: dict[str, Any]) -> Any:
    """run()'s closure ``name``, its own source, defined in ``ns`` (its free names' fakes)."""
    fn = next(n for n in ast.walk(_run_fn()) if isinstance(n, ast.FunctionDef) and n.name == name)
    exec(compile(ast.Module([fn], []), f"<{name}>", "exec"), ns)  # noqa: S102 -- the runner's own
    return ns[name]


def dog(score: float) -> Any:
    return ud.Box(100.0, 200.0, 160.0, 260.0, score, "garm_baby")


# --- the pure helpers ----------------------------------------------------------------------------
def test_the_alarm_classes_hook_takes_a_models_own_alarm_list() -> None:
    assert dh.alarm_classes(None) == dh.ALARM_CLASSES == ("garm_baby",)
    xmas02 = {"classes": ["player", "mystcase", "garm_baby"], "alarm": None}
    assert dh.alarm_classes(xmas02) == ("garm_baby",)
    sk = {"classes": ["player", "garm_baby", "goblin", "knight"], "alarm": ["garm_baby", "goblin",
                                                                           "knight"]}  # fmt: skip
    assert dh.alarm_classes(sk) == ("garm_baby", "goblin", "knight")
    wrong = {"classes": ["player", "garm_baby"], "alarm": ["goblin"]}  # not a class of its model
    assert dh.alarm_classes(wrong) == ("garm_baby",)


def test_a_sighting_is_latched_until_a_newer_one_and_one_fly_takes_it() -> None:
    import threading

    bw = dh.BoxWatch.__new__(dh.BoxWatch)
    bw.lock = threading.Lock()
    bw.alarm, bw.alarm_n, bw.n_alarm_hud = (0.0, []), 0, 0
    dh.ff_latch(bw, need=2, solo=0.7)
    bw._feed_alarm(1.0, [dog(0.45)])  # one weak box: no sighting (the streak is 1)
    assert bw.ff_seen is None
    bw._feed_alarm(1.25, [dog(0.40)], True)  # the second in a row (the HUD twin's): a sighting
    assert bw.ff_seen is not None and bw.ff_seen[0] == 1.25 and bw.ff_seen[2] == 2 and bw.ff_seen[3]
    bw._feed_alarm(1.5, [])  # an empty detection resets the alarm, NOT the latch
    assert bw.alarm == (1.5, []) and bw.alarm_n == 0 and bw.ff_seen[0] == 1.25
    bw._feed_alarm(1.4, [dog(0.9)])  # grabbed before the alarm's own: late, changes nothing
    assert bw.ff_seen[0] == 1.25
    bw._feed_alarm(2.0, [dog(0.74)])  # one box at the solo score: a newer sighting
    assert bw.ff_seen[0] == 2.0 and float(bw.ff_seen[1].score) == 0.74
    # read: fresh up to FF_LATCH_S, and only a sighting grabbed after the last Fly Wing
    assert dh.ff_sighting(bw.ff_seen, 2.1, after=-1e9) is bw.ff_seen
    assert dh.ff_sighting(bw.ff_seen, 2.0 + dh.FF_LATCH_S + 0.01, after=-1e9) is None
    assert dh.ff_sighting(bw.ff_seen, 2.1, after=2.05) is None  # a Fly Wing took it already
    assert dh.ff_sighting(None, 2.1, after=-1e9) is None
    # without --alarm-solo a single box needs the streak
    bw2 = dh.BoxWatch.__new__(dh.BoxWatch)
    bw2.lock = threading.Lock()
    bw2.alarm, bw2.alarm_n, bw2.n_alarm_hud = (0.0, []), 0, 0
    dh.ff_latch(bw2, need=2, solo=None)
    bw2._feed_alarm(1.0, [dog(0.95)])
    assert bw2.ff_seen is None


def test_the_flag_is_off_by_default_and_recorded_when_on() -> None:
    a = dh.build_parser().parse_args(["run", "--strategy", "P2", "--seed", "1"])
    assert a.fly_first is False
    on = dh.build_parser().parse_args(["run", "--strategy", "P2", "--seed", "1", "--fly-first"])
    assert on.fly_first is True
    base = {"plant_sweep": False, "box_ignore": 2, "ag_match": 40.0, "walk_trust": True,
            "rest": "spot", "npc_guard": True, "miss_cue": True,
            "walk_ahead": dh.WALK_AHEAD, "walk_through": False}  # fmt: skip
    assert "fly_first" not in dh.fixes_of(dh.argparse.Namespace(**base))
    rec = dh.fixes_of(dh.argparse.Namespace(**base, fly_first=True))
    assert rec["fly_first"] == [3.0, 1.0, "9.57"] == [dh.FF_LATCH_S, dh.FF_REARM_S,
                                                     dh.FLY_FIRST_VERSION]  # fmt: skip


# --- the press: the Fly Wing FIRST on a boss, by execution ---------------------------------------
def _press_ns(fly_first: bool, keys: list[str], evs: list[dict[str, Any]]) -> dict[str, Any]:
    class Bare:
        st = SimpleNamespace(armed=False)

        def escape(self) -> None:
            keys.append("F5")  # BareCtl.escape: the dagger's key

    return {
        "unread_end": lambda *a, **k: None, "hs": SimpleNamespace(bare=Bare()),
        "heal_candy": False, "heal_pick": None, "heal_left": None,
        "agent_raw": SimpleNamespace(keys=keys.append), "keys_": {"fly": "F8", "potion": "F1"},
        "counts": Counter(), "ev": evs.append, "stock_watch": None, "STOCK_ITEMS": {},
        "stock_due": {}, "stock_tries": {}, "stock_items": {}, "STOCK_READ_S": 1.0, "time": time,
        "fly_first": fly_first,
        "ff": {"after": None, "boss": False, "read_ns": None, "src": None, "sight": None},
        "FF_BOSS_WHYS": dh.FF_BOSS_WHYS, "r": SimpleNamespace(ns=time.monotonic_ns),
    }  # fmt: skip


def test_a_boss_fly_wing_goes_first_and_an_hp_one_keeps_the_dagger_first() -> None:
    keys: list[str] = []
    evs: list[dict[str, Any]] = []
    ns = _press_ns(True, keys, evs)
    press = closure("press", ns)
    press("fly", "garm")  # the alarm's
    assert keys == ["F8"] and ns["ff"]["after"] is not None  # no dagger key; the re-arm due
    rec = [e for e in evs if e["kind"] == "fly_first"]
    assert len(rec) == 1 and rec[0]["what"] == "fly" and rec[0]["why"] == "garm"
    assert isinstance(rec[0]["t_key_ns"], int)
    keys.clear()
    press("fly", "boss")  # the boss line's
    assert keys == ["F8"]
    keys.clear()
    press("fly", "hp 18")  # an HP Fly Wing (no boss this tick): 9.27's order, the dagger first
    assert keys == ["F5", "F8"]
    keys.clear()
    ns["ff"]["boss"] = True  # a tick with a boss line: the box's fly_away (box_press -> press)
    press("fly", "box fly_away (hp_percent 89, sees_boss True)")
    assert keys == ["F8"]
    keys.clear()
    press("potion", "hp 40")  # any other key: unchanged
    assert keys == ["F1"]
    # the flag OFF: today's order for every Fly Wing (r02B's: F5 at -0.050 s, F8 at +0.162 s)
    keys2: list[str] = []
    press_off = closure("press", _press_ns(False, keys2, []))
    press_off("fly", "garm")
    assert keys2 == ["F5", "F8"]


# --- the read inside actions and waits, by execution ---------------------------------------------
def _read_ns(seen: Any, fly_at: float, presses: list[tuple[str, str]],
             evs: list[dict[str, Any]]) -> dict[str, Any]:  # fmt: skip
    ns: dict[str, Any] = {
        "ff": {"after": None, "boss": False, "read_ns": None, "src": None, "sight": None},
        "r": SimpleNamespace(ns=time.monotonic_ns), "ev": evs.append, "counts": Counter(),
        "hs": SimpleNamespace(sitting=False, fly_at=fly_at, mode="fight"),
        "press": lambda w, y: presses.append((w, y)), "time": time,
        "boxes": SimpleNamespace(ff_seen=seen), "escaped": [False],
        "st": SimpleNamespace(fly=0.0), "ff_sighting": dh.ff_sighting, "QUICK_S": 0.05,
    }  # fmt: skip
    closure("ff_fly", ns)
    closure("ff_inside", ns)
    closure("ff_wait", ns)
    return ns


def test_the_read_inside_flies_once_on_a_fresh_sighting_and_never_within_two_seconds() -> None:
    now = time.monotonic()
    presses: list[tuple[str, str]] = []
    evs: list[dict[str, Any]] = []
    ns = _read_ns((now - 0.5, dog(0.74), 1, True), -1e9, presses, evs)
    assert ns["ff_inside"](now) is True
    assert presses == [("fly", "garm")] and ns["escaped"] == [True]
    assert ns["hs"].fly_at >= now - 0.01  # the sighting consumed
    assert [e["kind"] for e in evs] == ["garm_seen", "escape"]
    assert evs[0]["latched"] is True and evs[0]["inside"] is True and evs[1]["by"] == "fly_first"
    assert ns["ff"]["sight"]["score"] == 0.74 and ns["ff"]["src"] == "alarm"
    assert ns["counts"]["fly_first_inside"] == 1
    assert ns["ff_inside"](now + 0.1) is False  # escaped: never twice in one action
    for seen, fly_at in (((now - 0.5, dog(0.74), 1, True), now - 1.0),  # a Fly Wing 1 s ago
                         ((now - 3.5, dog(0.74), 1, True), -1e9),  # older than FF_LATCH_S
                         (None, -1e9)):  # fmt: skip
        p2: list[tuple[str, str]] = []
        assert _read_ns(seen, fly_at, p2, [])["ff_inside"](now) is False and not p2
    # a wait that reads it: it stops at the sighting, long before its end
    p3: list[tuple[str, str]] = []
    ns3 = _read_ns(None, -1e9, p3, [])
    t0 = time.monotonic()
    ns3["boxes"].ff_seen = (t0, dog(0.8), 1, False)
    assert ns3["ff_wait"](2.0) is True and time.monotonic() - t0 < 0.5 and p3 == [("fly", "garm")]
    assert _read_ns(None, -1e9, [], [])["ff_wait"](0.12) is False


# --- the boss read FIRST in the tick (step_survive's head), by execution --------------------------
def _head() -> ast.If:
    fn = next(n for n in ast.walk(_run_fn()) if isinstance(n, ast.FunctionDef)
              and n.name == "step_survive")  # fmt: skip
    first = fn.body[1] if isinstance(fn.body[0], ast.Expr) else fn.body[0]  # after the docstring
    if isinstance(first, ast.Nonlocal):
        first = fn.body[fn.body.index(first) + 1]
    assert isinstance(first, ast.If) and ast.unparse(first.test) == "fly_first"
    return first


def _head_fn(ns: dict[str, Any]) -> Any:
    body = textwrap.indent(ast.unparse(ast.Module(_head().body, [])), "    ")
    exec(f"def head():\n{body}\n    return None\n", ns)  # noqa: S102 -- the runner's own lines
    return ns["head"]


def _tick_ns(*, seen: Any, line: str | None, box_boss: bool, fly_at: float,
             flies: list[tuple[Any, str]],
             after: float | None = None) -> dict[str, Any]:  # fmt: skip
    keys: list[str] = []

    class Bare:
        st = SimpleNamespace(armed=False)

        def escape(self) -> None:
            keys.append("F5")

    tick = time.monotonic()
    return {
        "fly_first": True,
        "ff": {"after": after, "boss": False, "read_ns": None, "src": None, "sight": None},
        "boss_hit": line, "tick": tick, "r": SimpleNamespace(ns=time.monotonic_ns),
        "boxes": SimpleNamespace(ff_seen=seen), "ff_sighting": dh.ff_sighting,
        "box_boss": box_boss, "ff_fly": lambda s, n, src, inside: flies.append((s, src)),
        "hs": SimpleNamespace(boss_until=0.0, fly_at=fly_at, bare=Bare(), lock={"t": 1},
                              goal_path=[1], loot_list=[1], fight_ref=1, mode="fight",
                              here=(1, 1), last_taken=tick),
        "st": SimpleNamespace(fly=0.0), "ev": lambda e: None, "box_fight": {"box": 1},
        "time": SimpleNamespace(monotonic=time.monotonic, sleep=lambda s: None),
        "TICK_DONE": dh.TICK_DONE, "BOSS_AVOID_S": dh.BOSS_AVOID_S, "FF_REARM_S": dh.FF_REARM_S,
        "counts": Counter(), "keys": keys,
    }  # fmt: skip


def test_the_tick_reads_the_boss_first_and_flies_before_any_press() -> None:
    now = time.monotonic()
    flies: list[tuple[Any, str]] = []
    ns = _tick_ns(seen=(now - 0.3, dog(0.74), 1, True), line=None, box_boss=True, fly_at=-1e9,
                  flies=flies)  # fmt: skip
    assert _head_fn(ns)() == dh.TICK_DONE  # the tick ends: no box event, no sustain this tick
    assert [src for _s, src in flies] == ["alarm"]
    hs = ns["hs"]
    assert (hs.lock, hs.goal_path, hs.loot_list, hs.fight_ref, hs.mode, hs.here) == (
        None, None, [], None, "search", None) and ns["box_fight"] == {}  # fmt: skip
    assert hs.boss_until > now  # no box engagement for BOSS_AVOID_S
    # a boss line with no box boss fly: the runner's own Fly Wing, first
    flies.clear()
    ns2 = _tick_ns(seen=None, line="Stormy Knight", box_boss=False, fly_at=-1e9, flies=flies)
    assert _head_fn(ns2)() == dh.TICK_DONE and [s for _x, s in flies] == ["line"]
    # a boss line the box decides (it plays the boss fly): the box's event runs next, its Fly
    # Wing first (the tick's boss flag); the runner does not fly itself
    flies.clear()
    ns3 = _tick_ns(seen=None, line="Christmas Goblin", box_boss=True, fly_at=-1e9, flies=flies)
    assert _head_fn(ns3)() is None and not flies and ns3["ff"]["boss"] is True
    # within 2 s of a Fly Wing: no fly (the teleport lands), the boxes still avoided
    flies.clear()
    ns4 = _tick_ns(seen=(now - 0.3, dog(0.9), 1, False), line=None, box_boss=True,
                   fly_at=now - 1.0, flies=flies)  # fmt: skip
    assert _head_fn(ns4)() is None and not flies and ns4["hs"].boss_until > now
    # nothing seen; the dagger back on FF_REARM_S after a fly-first Fly Wing
    ns5 = _tick_ns(seen=None, line=None, box_boss=True, fly_at=-1e9, flies=flies,
                   after=now - 1.5)  # fmt: skip
    assert _head_fn(ns5)() is None and ns5["keys"] == ["F5"] and ns5["ff"]["after"] is None
    assert ns5["counts"]["fly_first_rearm"] == 1
    ns6 = _tick_ns(seen=None, line=None, box_boss=True, fly_at=-1e9, flies=flies,
                   after=time.monotonic())  # fmt: skip
    assert _head_fn(ns6)() is None and ns6["keys"] == [] and ns6["ff"]["after"] is not None


# --- the loop's structure, the flag off and on ---------------------------------------------------
def _fn_in(tree: ast.AST, name: str) -> ast.FunctionDef:
    """run()'s closure ``name`` (run() first: a class of the module may have a method so named)."""
    run = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "run")
    return next(n for n in ast.walk(run) if isinstance(n, ast.FunctionDef) and n.name == name)


def test_off_the_loop_is_todays_and_on_the_boss_read_comes_before_every_press_of_the_tick() -> None:
    off = hc.driver_loop(ast.parse(SRC))
    on = hc.driver_loop(ast.parse(SRC), fly_first=True)
    assert "ff_fly" not in ast.unparse(off) and "fly_first" not in ast.unparse(off)
    body = on.body
    head = next(
        i for i, x in enumerate(body) if "ff_fly(seen_t, tick, src_t, False)" in ast.unparse(x)
    )
    box = next(i for i, x in enumerate(body) if isinstance(x, ast.If)
               and ast.unparse(x.test) == "box_on"
               and "hook_survive(hook" in ast.unparse(x))  # fmt: skip
    own = next(i for i, x in enumerate(body) if isinstance(x, ast.If)
               and ast.unparse(x.test) == "frac is not None"
               and "sustain(" in ast.unparse(x))  # fmt: skip
    assert head < box < own  # the boss read, then the box's events, then the runner's sustain
    # every press of the tick before the head is none: the steps before it press nothing
    assert not any("press(" in ast.unparse(x) for x in body[:head])
    # step_engage leaves the alarm to the head; --boss-walk is off
    engage = [x for x in body if "garm_now = True" in ast.unparse(x)]
    assert not engage  # the alarm's old block is the flag's else
    assert "boss_walk_on = False" in ast.unparse(_fn_in(ast.parse(textwrap.dedent(
        ast.unparse(hc._Unflag(take_body=True).visit(ast.parse(SRC))))), "run"))  # fmt: skip


def test_on_the_waits_and_the_strike_read_the_sighting() -> None:
    tree = hc._Unflag(take_body=True).visit(ast.parse(SRC))
    bt = ast.unparse(_fn_in(tree, "box_target"))
    assert "ff_wait(settle_left(hs.last_walk_click, t_0))" in bt
    assert bt.index("ff_wait(") < bt.index("wait_still()") < bt.index("if escaped[0]:\n")
    assert bt.index("wait_fresh(t_set") < bt.index("if ff_inside(time.monotonic()):")
    assert "if ff_inside(time.monotonic()):" in ast.unparse(_fn_in(tree, "wait_still"))
    sk = _fn_in(tree, "strike")
    first = sk.body[1] if isinstance(sk.body[0], ast.Expr) else sk.body[0]
    assert ast.unparse(first).startswith("if ff_inside(time.monotonic()):")  # before the opener
    gt = ast.unparse(_fn_in(tree, "guard_tick"))
    assert gt.index("ff_inside(now_)") < gt.index("hpp.read(")
    off = hc._Unflag().visit(ast.parse(SRC))
    assert "time.sleep(settle_left(hs.last_walk_click, t_0))" in ast.unparse(
        _fn_in(off, "box_target")
    )
    assert "alarm_inside(now_)" in ast.unparse(_fn_in(off, "guard_tick"))


# --- the proofs ---------------------------------------------------------------------------------
def _quiet(f: Any, *a: Any, **k: Any) -> tuple[int, str]:
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        rc = f(*a, **k)
    return int(rc), out.getvalue()


def _bases() -> tuple[str, str]:
    try:
        return hc.git_show(hc.DRIVE_BASE, hc.TARGET), hc.git_show(hc.BASE_REV, hc.TARGET)
    except (subprocess.CalledProcessError, OSError):
        pytest.skip("git cannot show the bases here (a shallow checkout)")


def test_every_fly_first_change_is_a_branch_whose_else_is_todays_code() -> None:
    text, n = hc.unflag(SRC)
    assert n >= 15 and "fly_first" not in text and "ff_latch" not in text
    assert all(f"def {x}(" not in text and f"{x} =" not in text for x in hc.FLY_FIRST_ADDED)
    drive_base, check_base = _bases()
    rc_d, out_d = _quiet(hc.drive_check, drive_base, SRC)
    rc_c, out_c = _quiet(hc.check, check_base, SRC, drive_ok=True)
    assert rc_d == 0 and rc_c == 0, out_d + out_c
    assert f"fly-first branches read as their else (live-blocks 18): {n}" in out_d


def test_a_change_outside_a_branch_is_refused_by_both_proofs() -> None:
    drive_base, check_base = _bases()
    old = 'press("fly", "boss")\n                        hs.fly_at = time.monotonic()'
    assert SRC.count(old) == 1  # the boss guard's own Fly Wing (step_engage), outside a branch
    bent = SRC.replace(
        old, 'press("fly", "boss!")\n                        hs.fly_at = time.monotonic()'
    )
    assert _quiet(hc.drive_check, drive_base, bent)[0] == 1
    assert _quiet(hc.check, check_base, bent, drive_ok=True)[0] == 1
    # a condition that only CONTAINS the flag is no branch: it stays, and the proof sees it
    toy = "def f(x):\n    if fly_first and x:\n        return 1\n    return 0\n"
    assert hc.unflag(toy) == (toy, 0)
    toy2 = "def f(x):\n    if fly_first:\n        return 1\n    else:\n        return 0\n"
    assert ast.dump(ast.parse(hc.unflag(toy2)[0])) == ast.dump(
        ast.parse("def f(x):\n    return 0\n")
    )
    with pytest.raises(ValueError, match="empty"):
        hc.unflag("def f(x):\n    if fly_first:\n        return 1\n")
