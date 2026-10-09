"""ADR-0020 #10 (Batt 2026-10-09): position() / current_map() are ACTIVE (they type /where) and
are used as little as possible: a per-run /where budget on the flow, lint warnings, and the
simulator's count with each read's reason."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from poring_flow import ir, pyview

sys.path.insert(0, str(Path(__file__).parent))
from flow_synthetic import FIXTURES, farm_flow  # noqa: E402

HEAD = (
    'flow(ir=2, name="t", max_runtime_s=600{extra}, target=target(client="kro-20211103-prere", '
    'server="lab-rathena", locale="en", path=S2))\n'
)


def test_the_budget_is_a_flow_field_with_a_default() -> None:
    assert farm_flow().where_budget == ir.WHERE_BUDGET_DEFAULT == 12
    flow = pyview.parse(HEAD.format(extra=", where_budget=3") + "sit()\n")
    assert flow.where_budget == 3
    assert "where_budget=3" in pyview.print_flow(flow)
    assert "where_budget" not in pyview.print_flow(farm_flow())  # the default is not printed
    assert pyview.parse(pyview.print_flow(flow)) == flow
    data = json.loads(ir.to_json(farm_flow()))
    for bad in (-1, ir.WHERE_BUDGET_MAX + 1):
        with pytest.raises(ir.FlowError, match="where_budget"):
            ir.validate({**data, "where_budget": bad})
    # an IR 1 file converts with the default budget
    ir1 = json.loads((FIXTURES / "farm_loop.ir1.json").read_text())
    assert "where_budget" not in ir1 and ir.validate(ir1).where_budget == 12


def test_the_static_count_follows_the_longest_path_of_map_blocks() -> None:
    """A workflow's count is the longest simple path of blocks from the start: town -> relay ->
    farm reads twice here (a read in town and one in farm); event bodies are not on a path."""
    from poring_flow.catalogue import catalogue
    from poring_flow.lint import lint
    from poring_flow.lint.common import Ctx, Detector
    from poring_flow.lint.where import static_count

    src = (FIXTURES / "farm_loop.flow").read_text()
    src = src.replace("def town():\n", "def town():\n    read_position()\n", 1)
    src = src.replace("def farm():\n", "def farm():\n    read_position()\n", 1)
    flow = pyview.parse(src)
    assert static_count(Ctx(flow, catalogue(), None, None, Detector())) == 2
    assert not [f for f in lint(flow) if f.rule == "where_budget"]  # 2 <= 12
    tight = pyview.parse(
        src.replace(
            "    max_runtime_s=14400,\n", "    max_runtime_s=14400,\n    where_budget=1,\n", 1
        )
    )
    assert tight.where_budget == 1
    assert [f.message for f in lint(tight) if f.rule == "where_budget"] == [
        "the longest path reads the position 2 times (/where), above the flow's where_budget 1: "
        "use a passive source, or raise the budget"
    ]
