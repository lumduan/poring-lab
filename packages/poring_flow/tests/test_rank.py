"""IR 2: an explicit RANK inside each event class (Batt 2026-10-09, ADR-0020 contradictions #13),
defaulting to 13.6.3's table order; first in, first out only between events of equal rank. The IR
is versioned for it: IR 1 converts on load, any other version is refused with a message."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

from poring_flow import ir, pyview
from poring_flow.effective import global_set
from poring_flow.lint import lint
from poring_flow.runtime import Sim, owners

sys.path.insert(0, str(Path(__file__).parent))
from flow_synthetic import FIXTURES, farm_flow, farm_world, resolve_all  # noqa: E402

HEAD = (
    'flow(ir=2, name="t", max_runtime_s=600, target=target(client="kro-20211103-prere", '
    'server="lab-rathena", locale="en", path=S2))\n'
)
WALK = 'walk_to(cell("m", 10, 10))\n'


# --- the IR version ---------------------------------------------------------------------------
def test_an_ir_1_file_converts_to_ir_2() -> None:
    """The committed IR 1 copy of Batt's example (its canonical JSON before #13) loads, converted:
    only `ir` and the handlers' `rank` (None: the table order) differ."""
    text = (FIXTURES / "farm_loop.ir1.json").read_text()
    assert json.loads(text)["ir"] == 1
    flow = ir.from_json(text)
    assert flow.ir == 2 and flow == farm_flow()
    assert all(h.rank is None for h in flow.handlers)
    # the hash is the converted flow's, not the IR 1 text's
    assert ir.flow_hash(flow) == ir.flow_hash(farm_flow())
    assert ir.canonical_json(flow) != text.strip()
    # the frontend keeps the same IR 1 copy for its own converter's test
    frontend = FIXTURES.parents[3] / "services/frontend/src/lib/flow/fixtures/farm_loop.ir1.json"
    assert frontend.read_text() == text
    # and the Python view still reads ir=1, converted the same way
    src = (FIXTURES / "farm_loop.flow").read_text().replace("ir=2,", "ir=1,", 1)
    assert pyview.parse(src) == farm_flow()


@pytest.mark.parametrize(("v", "shown"), [(3, "3"), (0, "0"), ("1", '"1"'), (True, "true")])
def test_another_ir_version_is_refused_with_a_message(v: Any, shown: str) -> None:
    data = json.loads(ir.to_json(farm_flow()))
    data["ir"] = v
    with pytest.raises(ir.FlowError) as e:
        ir.validate(data)
    assert e.value.messages == [
        f"flow: ir: IR version {shown} is not supported: this engine reads IR 2 (and converts IR 1)"
    ]


def test_rank_is_bounded_and_round_trips_through_the_python_view() -> None:
    src = (
        HEAD + "@on(hp_percent() < 30, rearm=hp_percent() > 60, priority=SURVIVAL, rank=3)\n"
        "def hurt():\n    stand()\n\n\n" + WALK
    )
    flow = pyview.parse(src)
    assert flow.handlers[0].rank == 3
    assert "priority=SURVIVAL, rank=3)" in pyview.print_flow(flow)
    assert pyview.parse(pyview.print_flow(flow)) == flow
    assert ir.from_json(ir.to_json(flow)) == flow
    for bad in (0, 100):
        with pytest.raises(pyview.ParseError, match="rank"):
            pyview.parse(src.replace("rank=3", f"rank={bad}"))


# --- the order --------------------------------------------------------------------------------
def test_the_default_rank_is_13_6_3s_table_order() -> None:
    assert ir.DEFAULT_RANK == {
        "dead": 1,
        "hp_critical": 2,
        "unexpected_map": 3,
        "unintended_engagement": 4,
        "hp_low": 5,
        "weight": 6,
    }
    hs = {h.name: h for h in farm_flow().handlers}
    assert ir.rank_of(hs["unintended_engagement"]) < ir.rank_of(hs["hp_low"])
    # the global set: unintended_engagement leads survival although declared last
    keys = [e.key for e in global_set(farm_flow()).active()]
    assert keys.index("unintended_engagement") < keys.index("hp_low")


def test_an_explicit_rank_reorders_the_effective_set() -> None:
    data = json.loads(ir.to_json(farm_flow()))
    for h in data["handlers"]:
        if h["name"] == "hp_low":
            h["rank"] = 2  # drink before leaving a fight, by the author's choice
    flow = ir.validate(data)
    keys = [e.key for e in global_set(flow).active()]
    assert keys.index("hp_low") < keys.index("unintended_engagement")


def test_a_safety_critical_rank_is_fixed() -> None:
    data = json.loads(ir.to_json(farm_flow()))
    data["handlers"][0]["rank"] = 9  # dead
    found = [
        f.message
        for f in lint(ir.validate(data), world=farm_world(), resolver=resolve_all)
        if f.rule == "safety_critical"
    ]
    assert found == ["handlers.dead: dead is safety-critical: its rank is fixed (1, 13.6.3), not 9"]
    data["handlers"][0]["rank"] = 1  # its own rank, written out: allowed
    assert not [
        f
        for f in lint(ir.validate(data), world=farm_world(), resolver=resolve_all)
        if f.rule == "safety_critical"
    ]


# --- the queue (2.5 rule 4) -------------------------------------------------------------------
QUEUE = (
    "@on(weight_percent() >= 90, rearm=weight_percent() < 50, priority=UPKEEP)\n"
    "def heavy():\n    sit()\n\n\n"
    "@on(hp_percent() < 30, rearm=hp_percent() > 60, priority=SURVIVAL)\n"
    "def hurt():\n    stand()\n\n\n"
    "@on(sp_percent() < 10, rearm=sp_percent() > 50, priority=SURVIVAL{rank})\n"
    "def tired():\n    stand()\n\n\n"
    "@on(engagement_seen(), priority=SURVIVAL, max_per_min=4)\n"
    "def fight():\n    stand()\n\n\n" + WALK
)


def run(body: str, timeline: list[tuple[float, dict[str, Any]]]) -> Sim:
    sim = Sim(
        pyview.parse(HEAD + body),
        world={"hp_percent": 100, "weight_percent": 0, "sp_percent": 100},
        timeline=timeline,
    )
    sim.run()
    return sim


def test_equal_ranks_queue_first_in_first_out() -> None:
    """hurt and tired are user events (rank 50 each): the one that fired first runs first."""
    sim = run(
        QUEUE.format(rank=""),
        [(0.1, {"weight_percent": 95}), (0.25, {"hp_percent": 20}), (0.35, {"sp_percent": 5})],
    )
    seq = owners(sim.out)
    assert seq[:7] == ["main", "RELEASE", "heavy", "RELEASE", "hurt", "RELEASE", "tired"]


def test_a_lower_rank_overtakes_the_queue() -> None:
    """While hurt runs, fight (user rank 50) and tired (rank 4) queue in that order; the rank, not
    the arrival, decides: tired runs first. Neither pre-empts hurt (equal classes never do)."""
    sim = run(
        QUEUE.format(rank=", rank=4"),
        [
            (0.1, {"hp_percent": 20}),
            (0.15, {"engagement_seen": True}),
            (0.25, {"sp_percent": 5, "engagement_seen": False}),
        ],
    )
    seq = owners(sim.out)
    assert seq[:3] == ["main", "RELEASE", "hurt"]
    assert seq.index("tired") < seq.index("fight")
    assert seq[seq.index("hurt") + 1 : seq.index("hurt") + 3] == ["RELEASE", "tired"]


def test_the_table_order_decides_without_any_rank_written() -> None:
    """13.6.3: unintended_engagement (4) before hp_low (5): stop the fight before drinking, even
    when hp_low fired first and both wait behind a running survival event."""
    body = (
        "@on(sp_percent() < 10, rearm=sp_percent() > 50, priority=SURVIVAL)\n"
        "def tired():\n    stand()\n\n\n"
        "@on(hp_percent() < 30, rearm=hp_percent() > 60, priority=SURVIVAL)\n"
        "def hp_low():\n    sit()\n\n\n"
        "@on(engagement_seen(), priority=SURVIVAL, max_per_min=4)\n"
        "def unintended_engagement():\n    stand()\n\n\n" + WALK
    )
    sim = run(
        body,
        [
            (0.1, {"sp_percent": 5}),
            (0.15, {"hp_percent": 25}),
            (0.25, {"engagement_seen": True}),
        ],
    )
    seq = owners(sim.out)
    assert seq.index("unintended_engagement") < seq.index("hp_low")
