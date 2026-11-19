"""live-blocks 5b-2 (docs/planning/live-blocks.md 14): the box's HUNT LOOP played live -- the player
side (scripts/flow_play.py: the plan, DriveHook, LivePlayer.hunt_drive, fight_target(t)'s recipe
at the lock) and the STEP-TRACE EQUIVALENCE (scripts/hunt_trace.py): run()'s driver against the hunt
loop played as blocks, on scripted mode changes -- with the negative controls that show the
comparison names a program that plays differently (a verifier proves a positive case)."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts"))

import dungeon_hunt as dh  # noqa: E402
import flow_play as fp  # noqa: E402
import hunt_trace as ht  # noqa: E402

FIX = ROOT / "services/frontend/src/lib/flow/fixtures"
NODE = "xmas_dun02"
ONE = (FIX / "project_xmas_dun02.json").read_text()
HUNT = (FIX / "project_xmas_dun02_hunt.json").read_text()


def _prep(text: str) -> fp.Prepared:
    got = fp.prepare(text, NODE, 0)  # no configured maximum (Batt 2026-11-19)
    assert not isinstance(got, str), got
    return got


def _with_loop(body: list[Any]) -> str:
    d = json.loads(HUNT)
    tab = next(t for t in d["nodes"][0]["tabs"] if t["name"] == "hunt")
    tab["defs"][0]["body"] = body
    return json.dumps(d)


def _act(block: str, out: str | None = None, timeout_s: float = 120, **params: Any) -> Any:
    concept = {"find_target": "combat.hunt", "fight_target": "combat.attack_target",
               "strike": "combat.attack_target", "use_skill": "combat.use_skill",
               "loot": "loot.pick_up"}.get(block, f"core.{block}")  # fmt: skip
    return {"kind": "action", "block": block, "concept": concept, "params": params,
            "timeout_s": timeout_s, "on_fail": "stop", "outcome_to": out, "note": None}  # fmt: skip


T = {"kind": "var", "name": "t"}


# --- the plan: the same runner, plus the loop ----------------------------------------------------
def test_the_hunt_box_plays_the_one_boxs_runner_with_its_loop() -> None:
    one, hunt = _prep(ONE).runners[NODE], _prep(HUNT).runners[NODE]
    assert hunt.loop == "hunt_loop" and hunt.skill_keys == ("F1",) and one.loop is None
    # the same runner argv and the same run() arguments: the drive is the hook's, nothing else
    assert hunt.argv("L", Path("/S"), None) == one.argv("L", Path("/S"), None)
    assert hunt.box_kwargs() == one.box_kwargs() and hunt.keys == one.keys
    assert hunt.vals == one.vals
    assert _prep(HUNT).doc()["runners"][NODE]["loop"] == "hunt_loop"
    assert "loop" not in _prep(ONE).doc()["runners"][NODE]


class _NoIO(fp.LiveIO):
    def __init__(self) -> None:
        self.now = 0.0
        self.agent, self.screen = "AGENT", "SCREEN"

    def clock(self) -> float:
        return self.now

    def sleep(self, s: float) -> None:
        self.now += s

    def ns(self) -> int:
        return int(self.now * 1e9)

    def senses(self) -> dict[str, Any]:
        return {"map": "xmas_dun02", "hp_percent": 90}


class _Mem:
    def __init__(self) -> None:
        self.recs: list[dict[str, Any]] = []

    def ev(self, rec: Any) -> None:
        self.recs.append(dict(rec))

    def close(self) -> None:
        return None


def _play(text: str, scn: ht.Scenario,
          press: Any = None) -> tuple[fp.HuntResult, _Mem, list[dict[str, Any]], Any]:  # fmt: skip
    """The hunt core of the box, its run() a fake that drives the FAKE hunt exactly as run() does:
    the drive branch when the hook drives (hunt_drive), else the driver loop."""
    prep = _prep(text)
    log = _Mem()
    runner_recs: list[dict[str, Any]] = []
    seen: dict[str, Any] = {}

    def run_fn(a: Any, *, hook: Any = None, session: Any = None, **box: Any) -> int:
        seen["hook"], seen["box"] = hook, box
        fh = ht.FakeHunt(scn, on_lock=lambda sp: hook.recipe(sp, "lock"))
        fh.hs.reason = "time_box"
        steps = fh.steps()
        t_end = scn.minutes * 60.0
        if dh.hook_drives(hook):
            cur = dh.HuntCursor(steps, dh.HuntView(fh.hs, lambda: {"mode": fh.hs.mode}, fh.clock),
                                t_end=t_end, clock=fh.clock, press=press, trace=True)  # fmt: skip
            seen["cursor"] = cur
            dh.hunt_drive(hook, cur, fh.hs, runner_recs.append)
        else:
            while fh.clock() < t_end:
                if next((s for s in (f() for _n, f in steps) if s is not None), None) == dh.RUN_END:
                    break
        hook.event({"kind": "run_end", "reason": fh.hs.reason, "counts": {}}, 0.0)
        return 0

    pl = fp.LivePlayer(
        prep,
        _NoIO(),
        log,
        stop_file=None,  # type: ignore[arg-type]
        hunt=fp.HuntCore("t", None, run_fn=run_fn, args_fn=lambda argv: argv),
    )
    pl.block = NODE
    res = pl.hunt.play(pl, prep.runners[NODE])  # type: ignore[union-attr]
    return res, log, runner_recs, seen


def test_a_box_without_a_hunt_loop_gets_no_drive() -> None:
    res, log, recs, seen = _play(ONE, ht.hand_scenarios()[0])
    assert not dh.hook_drives(seen["hook"]) and "cursor" not in seen
    assert res.drive is None and recs == []
    assert not any(r.get("kind") in ("drive", "fight_target") for r in log.recs)


def test_the_hunt_loop_drives_the_steps_and_attack_plays_the_locked_species_recipe() -> None:
    scn = ht.hand_scenarios()[0]  # one fight: engage, lock, cue, kill, end, loot
    res, log, recs, seen = _play(HUNT, scn)
    assert dh.hook_drives(seen["hook"]) and isinstance(seen["hook"], fp.DriveHook)
    assert seen["box"] == _prep(ONE).runners[NODE].box_kwargs()  # run() gets the same arguments
    assert [r["what"] for r in recs] == ["start", "end"] and recs[1]["ended"] == "time_box"
    assert res.reason == "time_box" and res.drive is not None and res.drive["passed"] == {}
    kinds = [r["kind"] for r in log.recs]
    assert kinds.count("drive") == 2 and "fight_target" in kinds and "recipe" in kinds
    att = next(r for r in log.recs if r["kind"] == "fight_target")
    rec = next(r for r in log.recs if r["kind"] == "recipe")
    # the lock asked the box's recipe for the struck species; fight_target(t) played THAT recipe
    assert att["species"] == rec["species"] and att["function"] == f"attack_{rec['species']}"
    assert [s[0] for s in att["steps"]] == ["strike", "wait_steal", "knife_back", "wait_kill",
                                            "loot"]  # fmt: skip
    assert att["steps"][0][1] == "struck" and att["steps"][3][1] == "killed"
    assert att["steps"][4][1] == 2  # the fake loot step's two clicks
    # the same steps as the driver's, tick for tick
    drv, _fh = ht.driver_trace(scn)
    assert seen["cursor"].trace == drv


def test_use_skill_presses_a_declared_key_through_the_runner_between_two_steps() -> None:
    body = [{"kind": "while", "cond": {"kind": "lit", "value": True}, "max_iter": None,
             "max_s": None, "body": [_act("find_target", "t"), _act("use_skill", key={"kind":
             "lit", "value": "F1"}), _act("fight_target", timeout_s=300, target=T)]}]  # fmt: skip
    pressed: list[tuple[str, str]] = []
    res, log, _recs, _seen = _play(_with_loop(body), ht.hand_scenarios()[0],
                                   press=lambda k, w: pressed.append((k, w)) or True)  # fmt: skip
    assert pressed and all(k == "F1" and w.startswith("box use_skill") for k, w in pressed)
    assert any(r == {"kind": "key", "key": "F1", "node": r["node"], "in": "hunt"}
               for r in log.recs)  # fmt: skip


def test_a_loop_that_returns_ends_the_run_normally_with_words() -> None:
    body = [_act("find_target", "t"), _act("fight_target", timeout_s=300, target=T)]  # once
    res, _log, recs, seen = _play(_with_loop(body), ht.hand_scenarios()[0])
    assert seen["cursor"].ended is None and recs[-1]["what"] == "end"
    assert res.reason == "drive_end: the box hunt loop ended"


# --- the step-trace equivalence ------------------------------------------------------------------
@pytest.mark.parametrize("scn", ht.hand_scenarios(), ids=lambda s: s.name)
def test_the_hunt_loop_calls_the_drivers_steps_tick_for_tick(scn: ht.Scenario) -> None:
    r = ht.compare(scn, HUNT)
    assert r.same, r.first_diff
    assert r.passed == {}


def test_random_scenarios_and_short_time_boxes_too() -> None:
    for scn in ht.random_scenarios(25):
        r = ht.compare(scn, HUNT)
        assert r.same, (scn.name, r.first_diff)
    short = ht.short_boxes(HUNT)
    for scn in ht.random_scenarios(10):
        r = ht.compare(scn, short)
        assert r.same, (scn.name, "short", r.first_diff)
    total = sum((ht.compare(s, HUNT).effects for s in ht.random_scenarios(10)), start=ht.Counter())
    for fx in (
        "engage_hit",
        "engage_walk_sword",
        "engage_plant",
        "engage_queue",
        "engage_loot",
        "lock",
        "cue",
        "kill",
        "fight_end",
        "loot_step",
        "recheck",
        "box_fly",
        "unreach",
    ):
        assert total[fx] > 0, fx  # the scenarios exercise every transition


# negative controls: a program that plays differently is NAMED by the comparison
def test_a_loop_without_loot_passes_the_loot_step_and_differs() -> None:
    body = [{"kind": "while", "cond": {"kind": "lit", "value": True}, "max_iter": None,
             "max_s": None, "body": [_act("find_target", "t"),
                                     _act("wait_kill", timeout_s=120, target=T)]}]  # fmt: skip
    r = ht.compare(ht.hand_scenarios()[0], _with_loop(body))
    assert not r.same and r.passed == {"loot": 1} and "'loot', 'passed'" in str(r.first_diff)


def test_a_wrong_ownership_or_hand_back_differs(monkeypatch: pytest.MonkeyPatch) -> None:
    recheck = next(s for s in ht.hand_scenarios() if "recheck" in s.name)
    monkeypatch.setitem(dh.BLOCK_OWNS, "loot", ("fight", "loot"))  # loot(t) without hold
    r = ht.compare(recheck, HUNT)
    assert not r.same and "hold" in str(r.first_diff)
    monkeypatch.undo()
    monkeypatch.setattr(dh, "HANDBACK_AT", ("fight",))  # no hand-back before after
    r2 = ht.compare(ht.hand_scenarios()[0], HUNT)
    assert not r2.same and r2.passed
