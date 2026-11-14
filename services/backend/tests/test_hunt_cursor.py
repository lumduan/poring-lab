"""live-blocks 5b-2 (docs/planning/live-blocks.md 14): scripts/dungeon_hunt.py's TICK CURSOR (the
steps as live blocks) and huntstate_check.py's `drive` proof -- with no drive, run() is 5b-1's.

The cursor's tests drive it over FAKE steps (one closure per step name, a scripted state): which
steps a block runs, passes or calls through its guard, where it hands back, its time box, the run's
end and the spin guard. The proof's tests show each kind of wrong drive branch NAMED (a verifier
proves a positive case)."""

from __future__ import annotations

import contextlib
import io
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts"))

import dungeon_hunt as dh  # noqa: E402
import huntstate_check as hc  # noqa: E402


class Clock:
    def __init__(self) -> None:
        self.t = 0.0

    def __call__(self) -> float:
        return self.t


def _state(**kw: Any) -> SimpleNamespace:
    base: dict[str, Any] = {"mode": "search", "lock": None, "box_fight": {}, "box_sp": [None],
                            "bare": None, "kills_seen": [], "counts": {"loot_click": 0},
                            "here": (10, 10)}  # fmt: skip
    base.update(kw)
    return SimpleNamespace(**base)


def _cursor(hs: SimpleNamespace, effects: dict[tuple[int, str], Callable[[], str | None]],
            clock: Clock, t_end: float = 1e9, **kw: Any) -> dh.HuntCursor:  # fmt: skip
    """Fake steps: each a closure that applies ``effects[(tick, step)]`` (or nothing) and advances
    the clock 10 ms (pace: 200 ms)."""
    cur: list[dh.HuntCursor] = []

    def mk(name: str) -> Callable[[], str | None]:
        def step() -> str | None:
            clock.t += 0.2 if name == "pace" else 0.01
            fx = effects.get((cur[0].tick, name))
            return fx() if fx else None

        return step

    c = dh.HuntCursor([(n, mk(n)) for n in dh.STEP_NAMES], dh.HuntView(hs, lambda: {"m": hs.mode},
                      clock), t_end=t_end, clock=clock, trace=True, **kw)  # fmt: skip
    cur.append(c)
    return c


def _called(c: dh.HuntCursor, tick: int) -> list[str]:
    assert c.trace is not None
    return [n for t, n, s in c.trace if t == tick and s != "passed"]


def test_the_tables_name_every_step_once() -> None:
    assert dh.COMMON_STEPS + dh.MODE_STEPS == dh.STEP_NAMES and len(set(dh.STEP_NAMES)) == 20
    assert dh.COMMON_STEPS[-1] == "upkeep" and dh.MODE_STEPS[0] == "fight"
    assert set(dh.HANDBACK_AT) <= set(dh.MODE_STEPS) and set(dh.STEP_GUARD) <= set(dh.MODE_STEPS)
    for owns in dh.BLOCK_OWNS.values():
        assert set(owns) <= set(dh.MODE_STEPS)
    # the canonical loop's blocks own every mode step between them: find_target all but fight, loot
    assert set(dh.BLOCK_OWNS["find_target"]) | {"fight", "loot"} == set(dh.MODE_STEPS)


def test_find_target_runs_a_search_tick_and_hands_back_before_the_fight_step() -> None:
    hs, clock = _state(), Clock()

    def engage() -> None:
        hs.mode, hs.box_sp[0] = "fight", "cookie"
        hs.box_fight.update(spot=[12, 11], box=[1.0, 2.0, 3.0, 4.0])

    c = _cursor(hs, {(2, "engage"): engage}, clock)
    t = c.find_target(max_s=60)
    assert t == dh.HuntTarget((12, 11), "cookie", (1.0, 2.0, 3.0, 4.0))
    assert _called(c, 1) == list(dh.STEP_NAMES)  # a whole search tick: fight / loot no-ops
    assert _called(c, 2) == list(dh.COMMON_STEPS) and c.at == "fight"  # handed back there
    assert not c.passed


def test_a_fight_tick_ends_at_the_fight_step_and_wait_kill_hands_back_after_it() -> None:
    hs, clock = _state(mode="fight"), Clock()
    done = dh.TICK_DONE

    def kill_end() -> str:
        hs.kills_seen.append(1.0)
        hs.mode, hs.lock = "after", None
        return done

    c = _cursor(hs, {(1, "fight"): lambda: done, (2, "fight"): kill_end}, clock)
    assert c.wait_kill() == "killed"
    assert _called(c, 1) == [*dh.COMMON_STEPS, "fight"] and c.tick == 3 and c.at == "fight"
    # loot(t) from there: fight (a no-op now: its guard), hold, loot; hands back before after
    hs.counts["loot_click"] = 0

    def picks() -> None:
        hs.counts["loot_click"] += 2

    c2 = _cursor(_state(mode="after"), {(1, "loot"): picks}, Clock())
    c2.view.hs.counts = hs.counts
    assert c2.loot() == 2 and c2.at == "after"
    assert _called(c2, 1) == [*dh.COMMON_STEPS, "fight", "hold", "loot"]


def test_a_step_the_playing_block_does_not_own_is_passed_only_in_its_mode() -> None:
    hs, clock = _state(mode="after"), Clock()
    c = _cursor(hs, {(1, "after"): lambda: setattr(hs, "mode", "search")}, clock)  # type: ignore[func-returns-value]
    assert c.find_target(max_s=0.1) is None  # (its time box)
    assert c.passed == {"loot": 1}  # no loot(t): the loot step of mode after is passed
    assert "fight" in _called(c, 1)  # fight in mode after: its guard is false, so it is called
    # a fight block never passes the fight step; find_target never plays one (it hands back first)
    hs2 = _state(mode="fight")
    c2 = _cursor(hs2, {}, Clock())
    assert c2.find_target(max_s=5) == dh.HuntTarget(None, None, None)
    assert c2.at == "fight" and not c2.passed


def test_the_time_box_and_the_runs_end() -> None:
    hs, clock = _state(), Clock()
    c = _cursor(hs, {}, clock, t_end=1.0)
    assert c.find_target(max_s=0.5) is None and c.ended is None
    assert c.find_target() is None and c.ended == "time_box" and c.at == "begin"
    assert c.strike() == "ended" and c.wait_kill() == "ended"
    hs2 = _state(mode="fight")
    c2 = _cursor(hs2, {(2, "battle_log"): lambda: dh.RUN_END}, Clock())
    assert c2.wait_kill() == "ended" and c2.ended == "run_end"
    assert _called(c2, 2)[-1] == "battle_log"


def test_strike_wait_steal_and_walk_to_target_exits() -> None:
    hs, clock = _state(mode="fight"), Clock()
    bare = SimpleNamespace(st=SimpleNamespace(t_bare=None, stolen=False))

    def lock() -> str:
        hs.lock = {"t": 1.0, "rel": (1, 0), "cell": [11, 10]}
        hs.bare, bare.st.t_bare = bare, 1.0
        return dh.TICK_DONE

    def cue() -> str:
        bare.st.t_bare, bare.st.stolen = None, True
        return dh.TICK_DONE

    c = _cursor(hs, {(1, "fight"): lock, (2, "fight"): lambda: dh.TICK_DONE, (3, "fight"): cue},
                clock)  # fmt: skip
    assert c.strike() == "struck" and c.tick == 2
    assert c.walk_to_target() == "in_reach" and c.tick == 2  # locked: at once
    assert c.wait_steal() == "stolen" and c.tick == 4
    assert c.choose_target() == dh.HuntTarget((11, 10), None, None)
    hs.bare = None
    assert c.wait_steal() == "no_knife"
    hs.mode = "search"
    assert c.strike() == "gone" and c.wait_steal() == "gone" and c.choose_target() is None


def test_look_runs_the_first_ticks_common_steps_and_use_skill_presses_between_steps() -> None:
    hs, clock = _state(), Clock()
    pressed: list[tuple[str, str]] = []
    c = _cursor(hs, {}, clock, press=lambda k, w: pressed.append((k, w)) or k == "F1")
    assert c.look() == {"m": "search"} and c.at == "fight" and c.tick == 1
    assert c.look() == {"m": "search"} and c.tick == 1  # at once now
    assert c.use_skill("F1", "box") == "pressed" and c.use_skill("F2", "box") == "refused"
    assert pressed == [("F1", "box"), ("F2", "box")]


def test_blocks_that_take_no_step_end_the_drive_as_a_spin() -> None:
    hs, clock = _state(mode="fight"), Clock()
    c = _cursor(hs, {}, clock)
    c.find_target()  # (at the start: the common steps run, then it hands back: a step taken)
    for _ in range(dh.DRIVE_SPIN_MAX):
        assert c.find_target() is not None and c.ended is None
    c.find_target()
    assert c.ended == "spin"


def test_loot_with_nothing_to_loot_hands_back_at_once() -> None:
    hs, clock = _state(mode="search"), Clock()
    c = _cursor(hs, {}, clock)
    assert c.loot() == 0 and c.tick == 0
    hs.mode, c.i = "after", dh.STEP_NAMES.index("after")  # mode after, but past the loot step
    n0 = sum(c.calls.values())
    assert c.loot() == 0 and sum(c.calls.values()) == n0 and c.at == "after"
    # a time box bounds the fight loot(t) waits for, never its loot step: after the fight's end
    # it plays on to the step (hunt_trace.py found the pass a time box there made)
    hs2, clock2 = _state(mode="after"), Clock()
    c2 = _cursor(hs2, {(1, "hold"): lambda: dh.TICK_DONE, (2, "hold"): lambda: dh.TICK_DONE},
                 clock2)  # fmt: skip
    assert c2.loot(max_s=0.0001) == 0 and c2.at == "after" and c2.tick == 3
    assert c2.passed == {} and "loot" in _called(c2, 3)


def test_hunt_drive_refuses_a_hook_without_the_others_and_records_its_end() -> None:
    recs: list[dict[str, Any]] = []
    hs = _state(reason="time_box")
    c = _cursor(hs, {}, Clock(), t_end=0.5)
    dh.hunt_drive(SimpleNamespace(drive=lambda cur: None), c, hs, recs.append)
    assert hs.reason.startswith("drive_refused: a hook with drive but no tick, survive")
    assert recs == [
        {"kind": "drive", "what": "refused", "why": hs.reason[len("drive_refused: ") :]}
    ]

    class Hook:
        def __getattr__(self, name: str) -> Any:
            if name in dh.DRIVE_HOOK:
                return lambda *a: None
            raise AttributeError(name)

        def drive(self, cur: dh.HuntCursor) -> str | None:
            while cur.ended is None:
                cur.find_target()
            return None

    recs.clear()
    hs2 = _state(reason="time_box")
    c2 = _cursor(hs2, {}, Clock(), t_end=0.5)
    assert dh.hook_drives(Hook()) and not dh.hook_drives(None) and not dh.hook_drives(object())
    dh.hunt_drive(Hook(), c2, hs2, recs.append)
    assert hs2.reason == "time_box"  # the run's own time box: as the driver's loop ends
    assert [r["what"] for r in recs] == ["start", "end"] and recs[1]["ended"] == "time_box"
    hs3 = _state(reason="time_box")
    c3 = _cursor(hs3, {}, Clock())
    h3 = Hook()
    h3.drive = lambda cur: "the loop returned"  # type: ignore[method-assign]
    dh.hunt_drive(h3, c3, hs3, lambda r: None)
    assert hs3.reason == "drive_end: the loop returned"


# --- huntstate_check.py drive: with no drive, run() is 5b-1's ------------------------------------
def _five_b1() -> str:
    try:
        return hc.git_show(hc.DRIVE_BASE, hc.TARGET)
    except (subprocess.CalledProcessError, OSError):
        pytest.skip(f"git cannot show {hc.DRIVE_BASE} here (a shallow checkout)")


def _drive(base: str, new: str) -> tuple[int, str]:
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        rc = hc.drive_check(base, new)
    return rc, out.getvalue()


def test_the_committed_runner_without_its_drive_branch_is_5b1s() -> None:
    rc, text = _drive(_five_b1(), hc.TARGET.read_text())
    assert rc == 0, text
    assert (
        "run() without the drive branch == 5b-1's run() (as ASTs, docstrings included): YES" in text
    )
    assert "5b-1's statements unchanged" in text and "STEP_NAMES == hunt_steps' names: YES" in text
    assert "each acts only in its mode" in text


def test_the_drive_proof_names_each_wrong_rewrite() -> None:
    base, good = _five_b1(), hc.TARGET.read_text()
    ind, ind2 = " " * 16, " " * 20
    sleep = f"{ind2}time.sleep(max(0.0, 1.0 / READ_HZ - (time.monotonic() - tick)))\n"
    cases = {
        # a decision changed outside the branch (it would play differently with no drive)
        "run() without the drive branch == 5b-1's run() (as ASTs, docstrings included): NO":
            good.replace('hs.mode = "search"', 'hs.mode = "rest"', 1),
        # the else is not the driver loop
        "else is not exactly 5b-1's driver loop":
            good.replace(f"{ind2}if hunt_tick() == RUN_END:\n{ind2}    break",
                         f"{ind2}hunt_tick()", 1),
        # the branch's condition changed: no branch found
        "no drive branch": good.replace("if hook_drives(hook):", "if hook is not None:", 1),
        # a statement of 5b-1's module changed
        "CHANGED: ['READ_HZ']": good.replace("READ_HZ = ", "READ_HZ = 1 + ", 1),
        # an addition DRIVE_ADDED does not list
        "the added statements are not DRIVE_ADDED": good + "\nSNEAKY = 1\n",
        # a guard broken: the loot step acts outside mode after
        "step_loot:": good.replace(f'{ind}if hs.mode == "after":\n{ind2}queue.clear()',
                                   f"{ind}queue.clear()", 1),
        # the fight step may fall through in mode fight
        "step_fight: its if does not end with return TICK_DONE":
            good.replace(f"{sleep}{ind2}return TICK_DONE\n\n{' ' * 12}def step_hold",
                         f"{sleep}\n{' ' * 12}def step_hold", 1),
    }  # fmt: skip
    for words, bent in cases.items():
        assert bent != good, words
        rc, text = _drive(base, bent)
        assert rc == 1 and words in text, (words, text[-1500:])
