"""The READINESS severity and the run-start check (Batt 2026-10-09, ADR-0020 contradictions #6):
an unsupported binding is listed in the report and blocks the RUN, not the design."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from poring_flow import ir, runstart
from poring_flow.lint import blocking, default_resolver, errors, lint, readiness
from poring_flow.runtime import Sim

sys.path.insert(0, str(Path(__file__).parent))
from flow_synthetic import farm_flow, farm_world, resolve_all  # noqa: E402

NO_L3 = Path("/nonexistent-l3")


def test_an_unsupported_binding_is_a_readiness_item_not_an_error() -> None:
    flow = farm_flow()
    found = lint(flow, world=farm_world(), resolver=default_resolver(flow.target, NO_L3))
    bindings = [f for f in found if f.rule == "bindings"]
    assert bindings and {f.severity for f in bindings} == {"readiness"}
    assert errors(found) == []  # the design itself is approvable
    assert readiness(found) == bindings
    assert blocking(found) == bindings
    # the report lists readiness items after the errors, before the warnings
    order = [f.severity for f in found if f.layer == 2]
    assert order == sorted(order, key=["error", "readiness", "warning", "info"].index)


def test_the_run_start_check_refuses_on_readiness() -> None:
    flow = farm_flow()
    v = runstart.check(flow, world=farm_world(), resolver=default_resolver(flow.target, NO_L3))
    assert not v.allowed and v.errors == () and len(v.readiness) >= 5
    assert v.summary() == f"run refused: {len(v.readiness)} readiness items"
    with pytest.raises(runstart.RunRefused) as e:
        runstart.require(flow, world=farm_world(), resolver=default_resolver(flow.target, NO_L3))
    assert e.value.verdict == v
    assert "town.0: walk_to is unsupported here: L3 binding L3.map.walkability" in "\n".join(
        v.readiness
    )


def test_the_run_start_check_allows_a_flow_with_warnings_only() -> None:
    flow = farm_flow()
    found = lint(flow, world=farm_world(), resolver=resolve_all)
    assert found and not blocking(found)  # 13.6.8's example: warnings and infos only
    v = runstart.require(flow, world=farm_world(), resolver=resolve_all)
    assert v.allowed and v.summary() == "run allowed" and v.flow_hash == ir.flow_hash(flow)


def test_the_run_start_check_refuses_on_errors_and_fails_closed() -> None:
    flow = farm_flow()
    no_world = runstart.check(flow, world=None, resolver=resolve_all)
    assert no_world.reasons == ("no static data: references and routes are unchecked",)
    no_res = runstart.check(flow, world=farm_world(), resolver=None)
    assert no_res.reasons == ("no resolver: bindings are unchecked",)
    other = runstart.check(flow, world=farm_world(), resolver=resolve_all, approved_hash="0" * 64)
    assert not other.allowed and other.reasons[0].endswith("is not the approved 000000000000")
    bad = ir.validate(
        {
            "ir": ir.IR_VERSION,
            "name": "t",
            "target": {"client": "c", "server": "s", "locale": "en"},
            "max_runtime_s": 60,
            "main": [{"kind": "break"}],
        }
    )
    v = runstart.check(bad, world=farm_world(), resolver=resolve_all)
    assert v.errors == ("main.0: break outside a loop",) and not v.allowed


def test_simulation_is_not_gated() -> None:
    """Design time: a flow with readiness items still simulates."""
    flow = farm_flow()
    assert readiness(lint(flow, world=farm_world(), resolver=default_resolver(flow.target, NO_L3)))
    sim = Sim(flow, world={"map": "map_1", "cell": (150, 180), "hp_percent": 100}, max_ticks=50)
    sim.run()
    assert sim.out  # it ran and emitted (counted, fake) input batches
