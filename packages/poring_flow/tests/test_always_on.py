"""The ALWAYS-ON safety events (Batt 2026-10-09, ADR-0020 contradictions #15): the compiler adds
dead, hp_critical and unexpected_map to EVERY flow (a workflow or a plain main flow) as global
events; a flow may only make them stricter (the lint matrix holds the "not weakened" cases)."""

from __future__ import annotations

import sys
from pathlib import Path

from poring_flow import always_on, editor, ir, pyview
from poring_flow.catalogue import catalogue
from poring_flow.effective import global_set, merge
from poring_flow.lint import lint
from poring_flow.runtime import Sim, compile_tree

sys.path.insert(0, str(Path(__file__).parent))
from flow_synthetic import FIXTURES, farm_flow, farm_world, resolve_all  # noqa: E402

HEAD = (
    'flow(ir=2, name="t", max_runtime_s=600, target=target(client="kro-20211103-prere", '
    'server="lab-rathena", locale="en", path=S2))\n'
)
PLAIN = HEAD + 'walk_to(cell("m", 10, 10))\nwalk_to(cell("m", 20, 20))\n'


def test_the_built_ins_are_13_6_8s_global_events_and_the_catalogues_blocks() -> None:
    assert tuple(always_on.BUILT_IN) == ir.SAFETY_CRITICAL
    written = {h.name: h for h in farm_flow().handlers}
    for k, h in always_on.BUILT_IN.items():
        assert written[k] == h, k  # Batt's example writes exactly the built-in definitions
        for a in h.body:
            assert isinstance(a, ir.ActionStmt)
            assert catalogue().blocks[a.block].spec.concept == a.concept


def test_a_plain_flow_gets_all_three_and_its_ir_is_unchanged() -> None:
    flow = pyview.parse(PLAIN)
    assert flow.handlers == []  # nothing is written into the IR: the hash is the author's
    g = global_set(flow)
    assert [(e.key, e.state, e.built_in) for e in g.active()] == [
        ("dead", "built_in", True),
        ("hp_critical", "built_in", True),
        ("unexpected_map", "built_in", True),
    ]
    assert [e.key for e in compile_tree(flow).active("")] == list(ir.SAFETY_CRITICAL)
    assert [h.name for h in always_on.global_handlers(flow)] == list(ir.SAFETY_CRITICAL)


def test_a_workflow_that_leaves_one_out_gets_it_and_a_map_may_extend_it() -> None:
    src = (FIXTURES / "farm_loop.flow").read_text()
    block = "@on(map_load_seen(), priority=CRITICAL, then=RELOCATE)\ndef unexpected_map():\n"
    block += "    read_position()\n"
    assert block in src
    text = src.replace(block, "")
    assert "def unexpected_map" not in text
    flow = pyview.parse(text)
    relay = flow.workflow.blocks[1] if flow.workflow else None
    assert relay is not None and relay.name == "relay"
    m = merge(flow, relay)
    assert m.issues == []  # relay EXTENDS unexpected_map: the built-in is global
    um = m.by_key("unexpected_map")
    assert um is not None and um.state == "extended" and um.built_in and um.extension_after
    assert um.handler == always_on.BUILT_IN["unexpected_map"]
    found = lint(flow, world=farm_world(), resolver=resolve_all)
    assert not [f for f in found if f.rule in ("safety_critical", "scope")]
    eff = editor.effective_doc(flow)
    assert {e["key"]: e["built_in"] for e in eff["town"]}["unexpected_map"] is True
    assert {e["key"]: e["built_in"] for e in eff["town"]}["dead"] is False  # written by the flow


def test_a_death_in_a_plain_flow_fires_the_built_in_dead() -> None:
    flow = pyview.parse(PLAIN)
    sim = Sim(flow, world={"hp_percent": 100}, timeline=[(0.15, {"is_dead": True})])
    end = sim.run()
    assert ("fire", "dead") in [(k, d) for _, k, d in sim.log]
    assert "dead" in [e.owner for e in sim.out]  # its respawn batches
    assert end == "relocate_no_block"  # a plain flow has no block to relocate to: it stops


def test_the_built_ins_bindings_are_checked() -> None:
    """A flow that does not write dead still needs dead's bindings to run (#6 + #15)."""
    from poring_flow.lint import default_resolver, readiness

    flow = pyview.parse(PLAIN)
    found = readiness(lint(flow, resolver=default_resolver(flow.target, Path("/nonexistent"))))
    assert {f.path for f in found} >= {"dead.0", "hp_critical.0"}  # read_position resolves
    assert editor.owners(flow)["dead"] == "global"
