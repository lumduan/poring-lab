"""The flow IR's JSON Schema is generated from the Pydantic models and drift-tested (ADR-0020
section 1), like the wire protocol's (`test_committed_schema_matches_models`)."""

from __future__ import annotations

import json
from pathlib import Path

from poring_flow import ir

ROOT = Path(__file__).resolve().parents[3]


def test_committed_schema_matches_models() -> None:
    committed = (ROOT / ir.SCHEMA_PATH).read_text()
    assert committed == ir.json_schema(), (
        "regenerate: python -m poring_flow.ir > packages/poring_flow/schema/flow.schema.json"
    )


def test_the_schema_names_every_statement_and_expression_kind() -> None:
    defs = json.loads(ir.json_schema())["$defs"]
    for name in (
        "ActionStmt",
        "If",
        "While",
        "WaitUntil",
        "Repeat",
        "ForEach",
        "SetVar",
        "CallProc",
        "Stop",
        "TakeExit",
        "Lit",
        "Var",
        "Sense",
        "Cmp",
        "Logic",
        "Arith",
        "Do",
        "Handler",
        "Override",
        "Extend",
        "Disable",
        "Add",
        "MapBlock",
        "Exit",
        "Entry",
    ):
        assert name in defs, name
