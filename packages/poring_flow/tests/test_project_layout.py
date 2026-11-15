"""ROUND 25 (Batt 2026-11-15 ~13:0x ICT: "/flows and /maps must REMEMBER where I placed the blocks";
docs/planning/live-blocks.md 12.9, project-model.md 2.6): a tab's LAYOUT -- where a person put its
top blocks, by "main" / "def:<name>" / "var:<name>" -> [x, y] -- is kept by the project's file and
its JSON round trip, and is outside everything the engine computes: the hash (`project_hash`), the
compiled IR, the lint, the Python view. Python -> project (`pyproject.parse_files`, which never
sees a layout) keeps it through `keep_layout`."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest

from poring_flow import ir, pyproject
from poring_flow import project as P
from poring_flow.catalogue import catalogue

FIX = Path(__file__).resolve().parents[3] / "services/frontend/src/lib/flow/fixtures"
# the ready-made and the FROZEN projects (their files are untouched: the layout is added here)
NAMES = sorted(p.name for p in FIX.glob("project_*.json"))


def with_layout(d: dict[str, Any]) -> dict[str, Any]:
    """Every top block of every tab placed somewhere (the keys the editor makes)."""
    d = copy.deepcopy(d)
    for n in d["nodes"]:
        for i, t in enumerate(n["tabs"]):
            keys = (["main"] if t.get("main") is not None else []) + [
                f"def:{x['name']}" for x in t["defs"]
            ]
            keys += [f"var:{v}" for v in t["vars"]]
            if keys:
                t["layout"] = {
                    k: [20 + 300 * (j % 3) + i, 90 + 400 * (j // 3)] for j, k in enumerate(keys)
                }
    return d


@pytest.mark.parametrize("name", NAMES)
def test_the_layout_is_outside_the_hash_the_ir_the_lint_and_the_python_view(name: str) -> None:
    raw = (FIX / name).read_text(encoding="utf-8")
    p = P.from_json(raw)
    q = P.validate(with_layout(json.loads(raw)))
    assert any(t.layout for n in q.nodes for t in n.tabs)
    # the file keeps it (canonical JSON, the round trip); the hash does not see it
    assert '"layout":' in P.canonical_json(q) and '"layout":' not in P.canonical_json(p)
    assert P.canonical_json(P.from_json(P.to_json(q))) == P.canonical_json(q)
    assert P.project_hash(q) == P.project_hash(p)
    assert P.canonical_json(P.without_layout(q)) == P.canonical_json(p) == raw.rstrip("\n")
    # the engine: the compiled IR, the lint's findings, the Python view are the same
    cp, cq = P.compile_project(p), P.compile_project(q)
    assert (cp.flow is None) == (cq.flow is None)
    if cp.flow is not None and cq.flow is not None:
        assert ir.canonical_json(cq.flow) == ir.canonical_json(cp.flow)
    fp, fq = P.project_lint(p)[1], P.project_lint(q)[1]
    assert [f.text for f in fq] == [f.text for f in fp]
    assert P.lint_doc(q, world=None, resolver=None) == P.lint_doc(p, world=None, resolver=None)
    files_p = [f.doc() for f in pyproject.print_files(p, catalogue())]
    files_q = [f.doc() for f in pyproject.print_files(q, catalogue())]
    assert files_q == files_p and "layout" not in json.dumps(files_q)


def test_python_to_project_keeps_the_layout_of_the_blocks_still_there() -> None:
    raw = (FIX / "project_xmas_dun02.json").read_text(encoding="utf-8")
    q = P.validate(with_layout(json.loads(raw)))
    files = {f.path: f.text for f in pyproject.print_files(q, catalogue())}
    parsed = pyproject.parse_files(files, catalogue())
    assert not any(t.layout for n in parsed.nodes for t in n.tabs)  # the Python view has none
    assert P.canonical_json(P.keep_layout(parsed, q)) == P.canonical_json(q)
    # a function gone from the Python: its place goes with it, the others stay
    keys = next(t for t in q.nodes[0].tabs if t.name == "keys")
    edited = {k: v.replace("def candy():", "def candy_gone():") for k, v in files.items()}
    edited = {k: v.replace("candy()", "candy_gone()") for k, v in edited.items()}
    kept = P.keep_layout(pyproject.parse_files(edited, catalogue()), q)
    lay = next(t for t in kept.nodes[0].tabs if t.name == "keys").layout or {}
    assert "def:candy" not in lay and set(lay) == set(keys.layout or {}) - {"def:candy"}


@pytest.mark.parametrize(
    "layout",
    [{"def:1x": [0, 0]}, {"fn:heal": [0, 0]}, {"def:heal": [0, 2_000_000]}, {"def:heal": [0]},
     {"def:heal": [0, float("nan")]}, {"main": "here"}],
)  # fmt: skip
def test_a_layout_is_checked_as_hostile_input(layout: dict[str, Any]) -> None:
    d = json.loads((FIX / "project_xmas_dun02.json").read_text(encoding="utf-8"))
    d["nodes"][0]["tabs"][1]["layout"] = layout
    with pytest.raises(P.ProjectError):
        P.validate(d)


def test_an_empty_layout_is_no_layout() -> None:
    raw = (FIX / "project_xmas_dun02.json").read_text(encoding="utf-8")
    d = json.loads(raw)
    d["nodes"][0]["tabs"][1]["layout"] = {}
    assert P.canonical_json(P.validate(d)) == raw.rstrip("\n")
