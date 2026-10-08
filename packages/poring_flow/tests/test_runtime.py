"""The pre-emption rules (2.5) and MW1's insert / pre-empt / escalation / relocation, table-tested
against a scripted sensor timeline and a fake clock, asserting the emitted AgentInput sequence."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from poring_env.protocol import AgentInput, Key, MouseButton, ReleaseAll
from poring_flow import ir, pyview
from poring_flow.runtime import TICK_S, Emitted, Plan, Sim, compile_tree, default_plan, owners

sys.path.insert(0, str(Path(__file__).parent))
from flow_synthetic import farm_flow  # noqa: E402

HEAD = (
    'flow(ir=1, name="t", max_runtime_s=600, target=target(client="kro-20211103-prere", '
    'server="lab-rathena", locale="en", path=S2))\n'
)
WALK = 'walk_to(cell("m", 10, 10))\n'


def run(
    body: str,
    *,
    world: dict[str, Any] | None = None,
    timeline: list[tuple[float, dict[str, Any]]] | None = None,
    plans: dict[str, Plan] | None = None,
    **kw: Any,
) -> Sim:
    flow = pyview.parse(HEAD + body)

    def planner(a: ir.ActionStmt, sim: Sim) -> Plan:
        return (plans or {}).get(a.block) or default_plan(a, sim)

    sim = Sim(
        flow,
        world={"hp_percent": 100, "weight_percent": 0, "sp_percent": 100, **(world or {})},
        timeline=timeline,
        planner=planner,
        **kw,
    )
    sim.run()
    return sim


def by(sim: Sim, owner: str) -> list[Emitted]:
    return [e for e in sim.out if e.owner == owner]


def is_release(e: Emitted) -> bool:
    return isinstance(e.batch.events[0], ReleaseAll)


def assert_wellformed(sim: Sim) -> None:
    """Every batch is an AgentInput; time never runs backwards; every pre-empt (and escalation)
    starts with a ReleaseAll immediately followed by the handler's own first batch; the end of a
    halted run releases."""
    assert all(isinstance(e.batch, AgentInput) for e in sim.out)
    times = [e.batch.t_mono_ns for e in sim.out]
    assert times == sorted(times)
    for i, label in sim.preempts:
        assert is_release(sim.out[i]), (i, label)
        assert sim.out[i + 1].owner == label, (i, label, sim.out[i + 1].owner)
    if sim.end != "done":
        assert is_release(sim.out[-1])


# --- 2.5: classes, queueing, re-arm, cooldown, the runaway stop, ReleaseAll on every halt --------
def test_a_preempt_releases_first_and_resume_restarts_the_interrupted_block() -> None:
    sim = run(
        "@on(is_dead(), priority=CRITICAL, max_per_run=1)\ndef dead():\n    respawn()\n\n\n"
        + WALK
        + 'walk_to(cell("m", 20, 20))\n',
        timeline=[(0.15, {"is_dead": True})],
    )
    assert sim.end == "done"
    assert owners(sim.out) == ["main", "RELEASE", "dead", "main"]
    assert len(by(sim, "dead")) == 3
    assert len(by(sim, "main")) == 2 + 3 + 3  # 2 ticks, interrupted; restarted: 3; the next: 3
    assert (0.2, "interrupted", "main") in [(round(t, 2), k, d) for t, k, d in sim.log]
    assert_wellformed(sim)


CLASSES = (
    "@on(weight_percent() >= 90, rearm=weight_percent() < 50, priority=UPKEEP)\n"
    "def heavy():\n    sit()\n\n\n"
    "@on(hp_percent() < 30, rearm=hp_percent() > 60, priority=SURVIVAL)\n"
    "def hurt():\n    stand()\n\n\n"
    "@on(sp_percent() < 10, rearm=sp_percent() > 50, priority=SURVIVAL)\n"
    "def tired():\n    stand()\n\n\n" + WALK
)


def test_a_higher_class_preempts_a_lower_one_and_equal_classes_queue() -> None:
    sim = run(
        CLASSES,
        timeline=[
            (0.1, {"weight_percent": 95}),
            (0.25, {"hp_percent": 20}),
            (0.35, {"sp_percent": 5}),
        ],
    )
    # upkeep pre-empts main; survival pre-empts upkeep; the second survival QUEUES behind the
    # first, then pre-empts the resumed upkeep; upkeep restarts; main restarts
    assert owners(sim.out) == [
        "main",
        "RELEASE",
        "heavy",
        "RELEASE",
        "hurt",
        "RELEASE",
        "tired",
        "heavy",
        "main",
    ]
    assert len(by(sim, "hurt")) == 3 and len(by(sim, "tired")) == 3
    assert_wellformed(sim)


def test_a_lower_class_never_preempts_a_higher_one() -> None:
    sim = run(CLASSES, timeline=[(0.1, {"hp_percent": 20}), (0.2, {"weight_percent": 95})])
    assert owners(sim.out) == ["main", "RELEASE", "hurt", "RELEASE", "heavy", "main"]
    assert_wellformed(sim)


def test_rearm_is_a_hysteresis_pair() -> None:
    sim = run(
        "@on(hp_percent() < 35, rearm=hp_percent() > 60, priority=SURVIVAL)\n"
        "def drink():\n    use_item(item(9001))\n\n\n"
        "wait_until(hp_percent() > 1000, timeout_s=3)\n",
        world={"hp_percent": 80},
        timeline=[
            (0.2, {"hp_percent": 30}),
            (0.5, {"hp_percent": 40}),
            (0.7, {"hp_percent": 30}),
            (1.0, {"hp_percent": 70}),
            (1.3, {"hp_percent": 30}),
        ],
    )
    fires = [round(t, 1) for t, kind, d in sim.log if kind == "fire" and d == "drink"]
    assert fires == [0.2, 1.3]  # 0.7 is an edge, but the event is not re-armed until > 60
    assert_wellformed(sim)


def test_cooldown_keeps_the_event_disarmed() -> None:
    sim = run(
        "@on(hp_percent() < 35, priority=SURVIVAL, cooldown_s=2)\n"
        "def drink():\n    use_item(item(9001))\n\n\n"
        "wait_until(hp_percent() > 1000, timeout_s=4)\n",
        world={"hp_percent": 80},
        timeline=[
            (0.2, {"hp_percent": 30}),
            (0.4, {"hp_percent": 50}),
            (0.6, {"hp_percent": 30}),
            (1.0, {"hp_percent": 50}),
            (2.8, {"hp_percent": 30}),
        ],
    )
    fires = [round(t, 1) for t, kind, d in sim.log if kind == "fire" and d == "drink"]
    assert fires == [0.2, 2.8]


def test_the_runaway_bound_stops_the_run_and_releases() -> None:
    sim = run(
        "@on(hp_percent() < 50, until=hp_percent() > 80, priority=SURVIVAL, mode=INSERT, "
        "max_fires_per_10min=3)\ndef hp_low():\n    use_item(item(9001))\n\n\n"
        "wait_until(hp_percent() > 1000, timeout_s=10)\n",
        world={"hp_percent": 40},  # the potions never lift HP above 80
    )
    assert sim.end == "handler_runaway"
    assert len(by(sim, "hp_low")) == 3
    assert is_release(sim.out[-1])  # ReleaseAll on every halt


def test_max_per_run_stops_at_the_second_death() -> None:
    sim = run(
        "@on(is_dead(), priority=CRITICAL, max_per_run=1)\ndef dead():\n    respawn()\n\n\n"
        + WALK * 4,
        timeline=[(0.15, {"is_dead": True}), (1.0, {"is_dead": True})],
    )
    assert sim.end == "death_limit"
    assert is_release(sim.out[-1])


def test_guards_stop_or_pause_and_release() -> None:
    red = run(WALK * 3, timeline=[(0.25, {"interlock": "red"})])
    assert red.end == "interlock_red" and is_release(red.out[-1])
    human = run(WALK * 3, timeline=[(0.25, {"human": True})])
    assert human.end == "human_pause" and is_release(human.out[-1])
    held = run(
        WALK * 3,
        plans={"walk_to": Plan(ticks=6, hold=True)},
        timeline=[(0.25, {"interlock": "red"})],
    )
    assert held.end == "interlock_red" and is_release(held.out[-1])


def test_then_skip_block_fails_the_interrupted_block() -> None:
    sim = run(
        "@on(hp_percent() < 30, rearm=hp_percent() > 60, priority=SURVIVAL, then=SKIP_BLOCK)\n"
        "def hurt():\n    stand()\n\n\n" + 'walk_to(cell("m", 1, 1), on_fail=CONTINUE)\n' + WALK,
        timeline=[(0.15, {"hp_percent": 20})],
    )
    assert sim.end == "done"
    assert len(by(sim, "main")) == 2 + 3  # the interrupted walk is NOT re-run; the next one is


# --- 13.6.4: INSERT vs PRE-EMPT -----------------------------------------------------------------
INSERT = (
    "@on(hp_percent() < 50, until=hp_percent() > 80, priority=SURVIVAL, mode=INSERT, "
    "max_per_min=6)\ndef hp_low():\n    use_item(item(9001))\n\n\n"
)
POTION = Plan(ticks=1, effects={"hp_percent": 90})


def test_an_insert_runs_between_ticks_and_the_block_continues() -> None:
    sim = run(
        INSERT + WALK,
        plans={"walk_to": Plan(ticks=6), "use_item": POTION},
        timeline=[(0.25, {"hp_percent": 40})],
    )
    assert owners(sim.out) == ["main", "hp_low", "main"]
    assert len(by(sim, "main")) == 6  # continued at its next tick, NOT restarted
    assert not any(is_release(e) for e in sim.out)  # nothing was held: no ReleaseAll
    assert [k for _, k, d in sim.log if d == "hp_low"] == ["fire", "insert", "until"]
    potion = by(sim, "hp_low")[0].batch.events
    assert [type(ev) for ev in potion] == [Key, Key] and potion[0].code == "F1"  # the hotbar


def test_an_insert_releases_first_when_something_is_held() -> None:
    sim = run(
        INSERT + WALK,
        plans={"walk_to": Plan(ticks=6, hold=True), "use_item": POTION},
        timeline=[(0.25, {"hp_percent": 40})],
    )
    assert owners(sim.out) == ["main", "RELEASE", "hp_low", "main", "RELEASE"]  # held at the end


def test_an_insert_never_runs_inside_an_atomic_section() -> None:
    sim = run(
        INSERT + 'choose_menu(option("o_1"))\n' + WALK,
        plans={"use_item": POTION},
        timeline=[(0.05, {"hp_percent": 40})],
    )
    seq = [(e.owner, e.why) for e in sim.out]
    assert seq[:4] == [("main", "choose_menu")] * 3 + [("hp_low", "use_item")]


def test_a_preempt_waits_for_the_atomic_section_too() -> None:
    sim = run(
        "@on(hp_percent() < 30, rearm=hp_percent() > 60, priority=SURVIVAL)\n"
        "def hurt():\n    stand()\n\n\n" + 'choose_menu(option("o_1"))\n',
        timeline=[(0.05, {"hp_percent": 20})],
    )
    seq = [(e.owner, e.why) for e in sim.out]
    assert seq[:3] == [("main", "choose_menu")] * 3
    assert is_release(sim.out[3]) and sim.out[4].owner == "hurt"


def no_potions(a: ir.ActionStmt, sim: Sim) -> Plan:
    item = a.params.get("item")
    if a.block == "use_item" and isinstance(item, ir.Lit) and item.value == ir.ItemRef(id=9001):
        return Plan(ticks=1, outcome="failed")  # the bar does not rise: no potions left
    return default_plan(a, sim)


def test_escalation_runs_the_procedure_as_a_preempt() -> None:
    flow = pyview.parse(
        HEAD + "def leave():\n    use_item(item(9002))\n\n\n"
        "@on(hp_percent() < 50, until=hp_percent() > 80, priority=SURVIVAL, mode=INSERT, "
        "escalate=leave, max_insert_fails=2, then=STOP)\ndef hp_low():\n    use_item(item(9001))"
        "\n\n\n" + WALK * 3
    )
    sim = Sim(
        flow, world={"hp_percent": 100}, timeline=[(0.15, {"hp_percent": 40})], planner=no_potions
    )
    sim.run()
    seq = owners(sim.out)
    assert seq[:6] == ["main", "hp_low", "main", "hp_low", "RELEASE", "hp_low.escalate"]
    assert [k for _, k, d in sim.log if d == "hp_low"].count("insert_failed") == 2
    assert sim.end == "hp_low.escalate_stop"
    assert_wellformed(sim)


def test_a_failed_insert_without_escalation_stops_the_run() -> None:
    sim = run(
        "@on(hp_percent() < 50, until=hp_percent() > 80, priority=SURVIVAL, mode=INSERT, "
        "max_insert_fails=1)\ndef hp_low():\n    use_item(item(9001))\n\n\n" + WALK,
        plans={"use_item": Plan(ticks=1, outcome="failed")},
        timeline=[(0.15, {"hp_percent": 40})],
    )
    assert sim.end == "insert_failed" and is_release(sim.out[-1])


# --- 13.6.6: relocation, on Batt's example ------------------------------------------------------
def farm_sim(timeline: list[tuple[float, dict[str, Any]]], **world: Any) -> Sim:
    sim = Sim(
        farm_flow(),
        world={
            "map": "map_1",
            "cell": (150, 180),
            "hp_percent": 100,
            "weight_percent": 0,
            "wing:9002": "butterfly",
            **world,
        },
        timeline=timeline,
        save_point=("map_1", (150, 180)),
    )
    sim.run()
    return sim


def test_the_weight_wing_relocates_to_the_save_point_block() -> None:
    # town (4 statements x 3 ticks) -> relay -> farm by t = 1.8; weight 95 at t = 3.0
    sim = farm_sim([(3.0, {"weight_percent": 95}), (5.0, {"human": True})])
    log = [(k, d) for _, k, d in sim.log]
    assert ("block", "relay") in log and ("block", "farm") in log
    assert ("fire", "weight") in log and ("relocate", "town") in log
    seq = owners(sim.out)
    i = seq.index("weight")
    assert seq[i - 2 : i + 3] == ["farm", "RELEASE", "weight", "executor", "town"]
    read = [e for e in sim.out if e.owner == "executor" and not is_release(e)][0]
    assert read.why == "relocate: read position" and isinstance(read.batch.events[0], Key)
    # after the relocation town runs from its FIRST step
    town_after = [e.why for e in sim.out[sim.out.index(read) + 1 :] if e.owner == "town"]
    assert town_after[:3] == ["walk_to"] * 3
    assert sim.end == "human_pause"
    assert_wellformed(sim)


def test_an_unknown_map_stops_safely() -> None:
    sim = farm_sim([(0.45, {"map": "map_9", "cell": (5, 5)})])
    assert ("fire", "unexpected_map") in [(k, d) for _, k, d in sim.log]
    assert sim.end == "relocate_no_block"
    assert is_release(sim.out[-1])
    seq = owners(sim.out)
    assert seq[-4:] == ["RELEASE", "unexpected_map", "executor", "RELEASE"]


def test_an_exit_is_an_expected_map_change() -> None:
    sim = farm_sim([(2.5, {"human": True})])
    assert ("fire", "unexpected_map") not in [(k, d) for _, k, d in sim.log]
    assert [d for _, k, d in sim.log if k == "block"] == ["relay", "farm"]


def test_the_extension_of_a_safety_critical_event_runs_after_its_body() -> None:
    """On relay, unexpected_map is EXTENDED with close_dialog: the global read_position first."""
    sim = Sim(
        farm_flow(),
        world={"map": "map_2", "cell": (40, 300), "hp_percent": 100},
        timeline=[(0.05, {"map": "map_2b"})],
        save_point=("map_1", (150, 180)),
    )
    sim.block = "relay"
    sim.run()
    whys = [e.why for e in sim.out if e.owner == "unexpected_map"]
    steps = [w for i, w in enumerate(whys) if i == 0 or whys[i - 1] != w]  # 3 ticks per block
    assert steps == ["read_position", "close_dialog"]
    assert sim.end == "relocate_no_block"  # map_2b has no block: stop safely
    assert_wellformed(sim)


def test_the_compiled_tree_keeps_the_effective_sets_per_block() -> None:
    tree = compile_tree(farm_flow())
    assert [e.key for e in tree.active("town")] == [
        "dead",
        "hp_critical",
        "unexpected_map",
        "unintended_engagement",
    ]
    assert [e.key for e in tree.active("farm")][-1] == "weight"


def test_batches_carry_the_fake_clock_and_frame_ids() -> None:
    sim = run(WALK)
    assert [e.batch.t_mono_ns for e in sim.out] == [0, int(TICK_S * 1e9), int(2 * TICK_S * 1e9)]
    assert [e.batch.frame_id for e in sim.out] == [1, 2, 3]
    assert isinstance(sim.out[0].batch.events[1], MouseButton)
