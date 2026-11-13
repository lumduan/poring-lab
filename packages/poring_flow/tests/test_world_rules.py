"""The Maps page's WORLD RULES (Batt 2026-11-13): the save point stated at the run's first step and
the unknown-map rule (a Butterfly Wing home), written by services/frontend/src/lib/maps/rules.ts
as the engine's own blocks. The fixture is rules.ts's output on the two-map starter (rules.test.ts
checks the TypeScript makes exactly this flow)."""

from __future__ import annotations

from pathlib import Path

from poring_flow import editor, ir, lint, pyview

REPO = Path(__file__).resolve().parents[3]
RULES = REPO / "services/frontend/src/lib/flow/fixtures/starter_world_rules.json"


def lint_doc(f: ir.Flow) -> dict:
    return editor.lint_doc(f, world=editor.sample_world(), resolver=lint.default_resolver(f.target))


def save_point_errors(doc: dict) -> list[dict]:
    return [x for x in doc["findings"] if x["rule"] == "save_point" and x["severity"] == "error"]


def test_the_rules_flow_is_canonical_and_lints_without_an_error() -> None:
    text = RULES.read_text(encoding="utf-8")
    f = ir.from_json(text)
    assert text == ir.to_json(f) + "\n"
    doc = lint_doc(f)
    assert doc["counts"]["error"] == 0, doc["findings"]
    # the one save-point finding left is the assertion's own: visible at approval
    sp = [x for x in doc["findings"] if x["rule"] == "save_point"]
    assert [(x["severity"], x["path"]) for x in sp] == [("warning", "town.0")]
    assert "asserted, not set" in sp[0]["message"]
    # the rule is the built-in made stricter (lint/events.py "not weakened"): no events finding
    assert not [x for x in doc["findings"] if x["rule"] == "events"]
    assert pyview.parse(pyview.print_flow(f)) == f


def test_without_the_stated_save_point_the_wing_rule_is_an_error() -> None:
    """Batt's 2026-10-08 rule stands: a wing before the save point is known is an ERROR."""
    f = ir.from_json(RULES.read_text(encoding="utf-8"))
    assert f.workflow is not None
    town = f.workflow.blocks[0]
    assert isinstance(town.main[0], ir.ActionStmt) and town.main[0].block == "assert_save_point"
    town.main.pop(0)
    errs = save_point_errors(lint_doc(f))
    assert [x["path"] for x in errs] == ["unexpected_map"], errs


def test_an_assertion_after_the_first_step_counts_only_from_there() -> None:
    """Only the START block's FIRST step states the run's starting save point."""
    f = ir.from_json(RULES.read_text(encoding="utf-8"))
    assert f.workflow is not None
    town = f.workflow.blocks[0]
    first = town.main.pop(0)
    town.main.insert(1, first)  # after set_save_point's walk-up: step 0 is unknown again
    assert [x["path"] for x in save_point_errors(lint_doc(f))] == ["unexpected_map"]
