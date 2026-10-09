"""MW2's engine side (mw2-block-editor.md sections 3-5): verification badges follow L1, lint
findings carry the canvas node that owns them, the sample round-trips, the committed JSON copies
(the sample and the frontend's test fixtures) are exactly MW1's canonical JSON, and a browser's
JSON round trip (integral floats become ints) keeps the flow hash."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

from poring_flow import editor, ir, pyview
from poring_flow.catalogue import build
from poring_skills.schema import VerifiedOn, load_l1

sys.path.insert(0, str(Path(__file__).parent))
from flow_synthetic import FIXTURES, farm_flow, farm_world, resolve_all  # noqa: E402

REPO = Path(__file__).resolve().parents[3]
EXAMPLES = REPO / "packages/poring_flow/src/poring_flow/examples"
TS_FIXTURES = REPO / "services/frontend/src/lib/flow/fixtures"


def committed_json() -> dict[str, ir.Flow]:
    """The flows whose canonical JSON is committed for the frontend's round-trip tests."""
    return {
        "visit_and_choose": pyview.parse((FIXTURES / "visit_and_choose.flow").read_text()),
        "farm_loop": farm_flow(),
        "town_warp_farm": editor.sample_flow(),
    }


def browser(text: str) -> str:
    """What a browser does to JSON: integral floats lose their '.0' (JSON.parse/stringify)."""

    def walk(v: Any) -> Any:
        if isinstance(v, float) and v.is_integer():
            return int(v)
        if isinstance(v, list):
            return [walk(x) for x in v]
        if isinstance(v, dict):
            return {k: walk(x) for k, x in v.items()}
        return v

    return json.dumps(walk(json.loads(text)), separators=(",", ":"))


# --- badges -------------------------------------------------------------------------------------
def test_badges_follow_l1_verified_on() -> None:
    l1 = load_l1()
    doc = editor.catalogue_doc(l1=l1)
    # ui.open_window passed its alone-test on RDP only (l1/ui.yaml, 2026-10-07)
    assert doc["blocks"]["open_window"]["badge"] == "verified_rdp"
    assert {v["path"] for v in doc["blocks"]["open_window"]["verified_on"]} == {"rdp"}
    assert doc["blocks"]["walk_to"]["badge"] in ("unverified", "verified_rdp", "verified_s2")
    assert doc["blocks"]["assert_save_point"]["badge"] == "core"
    assert doc["sensors"]["base_level"]["badge"] == "unknown"  # no L1 read concept yet
    assert set(editor.PALETTE) <= set(doc["blocks"])


def test_flipping_verified_on_flips_the_badge() -> None:
    """Acceptance 5: an alone-test pass recorded in L1 flips the badge (catalogue included)."""
    l1 = load_l1()
    assert editor.badge("npc.talk", l1) == "unverified"
    run = {"client": "kro-20211103-prere", "server": "lab-rathena", "locale": "en",
           "session": "x", "rule": "talk@1", "date": "2026-10-08"}  # fmt: skip
    s2 = {**l1, "npc.talk": l1["npc.talk"].model_copy(
        update={"verified_on": [VerifiedOn(path="s2", **run)]})}  # fmt: skip
    assert editor.badge("npc.talk", s2) == "verified_s2"
    assert editor.catalogue_doc(l1=s2, cat=build(l1=s2))["blocks"]["talk_npc"]["badge"] == (
        "verified_s2"
    )
    runs = [VerifiedOn(path="s2", **run), VerifiedOn(path="rdp", **run)]
    both = {**s2, "npc.talk": s2["npc.talk"].model_copy(update={"verified_on": runs})}
    assert editor.badge("npc.talk", both) == "verified_rdp_s2"


def test_windows_come_from_l2() -> None:
    doc = editor.catalogue_doc(client="kro-20211103-prere")
    assert "basic_info" in doc["windows"]
    assert editor.catalogue_doc(client="no-such-build")["windows"] == []


# --- lint ---------------------------------------------------------------------------------------
def test_lint_findings_name_their_canvas_node() -> None:
    flow = farm_flow()
    doc = editor.lint_doc(flow, world=farm_world(), resolver=resolve_all, runtime_max_s=86_400)
    assert doc["flow_hash"] == ir.flow_hash(flow)
    owners = {f["path"]: f["owner"] for f in doc["findings"]}
    roots = editor.owners(flow)
    assert roots["town"] == "block:town" and roots["farm_hp_low"] == "block:farm"
    assert roots["dead"] == "global" and roots[""] == "flow"
    for path, own in owners.items():
        assert own == editor.owner_of(path, roots)
    total = sum(sum(v.values()) for v in doc["by_owner"].values())
    assert total == len(doc["findings"])
    assert set(doc["counts"]) == {"error", "readiness", "warning", "info"}
    assert doc["run"] == {"allowed": True, "summary": "run allowed", "reasons": []}
    eff = {e["key"]: e["state"] for e in doc["effective"]["town"]}
    assert eff["hp_low"] == "disabled" and eff["dead"] == "inherited"


def test_readiness_items_are_counted_apart_from_errors() -> None:
    """#6 (Batt 2026-10-09): unsupported bindings are READINESS, apart from the design's errors;
    the run-start gate's verdict travels with the lint."""
    from poring_flow.lint import default_resolver

    flow = farm_flow()
    res = default_resolver(flow.target, Path("/nonexistent-l3"))
    doc = editor.lint_doc(flow, world=farm_world(), resolver=res, runtime_max_s=86_400)
    assert doc["counts"]["error"] == 0 and doc["counts"]["readiness"] >= 5
    assert doc["by_owner"]["block:town"]["readiness"] >= 1
    assert {f["severity"] for f in doc["findings"] if f["rule"] == "bindings"} == {"readiness"}
    n = doc["counts"]["readiness"]
    assert doc["run"] == {
        "allowed": False,
        "summary": f"run refused: {n} readiness items",
        "reasons": [],
    }


def test_the_editor_lints_exactly_like_mw1() -> None:
    """Acceptance 3: the same IR gives exactly MW1's findings (the editor adds owners only)."""
    from poring_flow.lint import lint

    flow = farm_flow()
    mw1 = [f.message for f in lint(flow, world=farm_world(), resolver=resolve_all)]
    mw2 = [f["message"] for f in editor.lint_doc(flow, world=farm_world(),
                                                 resolver=resolve_all)["findings"]]  # fmt: skip
    assert mw2 == mw1


# --- the sample and the committed JSON ---------------------------------------------------------
def test_the_sample_parses_lints_and_round_trips() -> None:
    flow = editor.sample_flow()
    assert flow.workflow is not None and flow.workflow.start_block == "town"
    assert pyview.parse(pyview.print_flow(flow)) == flow
    world = editor.sample_world()
    assert sorted(world.sheets) == ["field_1", "town_1"]
    doc = editor.lint_doc(flow, world=world, resolver=resolve_all)
    assert doc["counts"]["error"] == 0, doc["findings"]
    assert editor.maps_of(flow) == ["field_1", "town_1"]


@pytest.mark.parametrize("name", ["visit_and_choose", "farm_loop", "town_warp_farm"])
def test_committed_json_is_canonical(name: str) -> None:
    """Regenerate with: python scripts/gen_flow_fixtures.py"""
    flow = committed_json()[name]
    text = (TS_FIXTURES / f"{name}.json").read_text(encoding="utf-8")
    assert text == ir.to_json(flow) + "\n", (
        f"{name}.json is stale: run scripts/gen_flow_fixtures.py"
    )
    if name == "town_warp_farm":
        sample = (EXAMPLES / "town_warp_farm.json").read_text(encoding="utf-8")
        assert sample == text


@pytest.mark.parametrize("name", ["visit_and_choose", "farm_loop", "town_warp_farm"])
def test_a_browser_round_trip_keeps_the_hash(name: str) -> None:
    flow = committed_json()[name]
    again = ir.from_json(browser(ir.to_json(flow)))
    assert ir.flow_hash(again) == ir.flow_hash(flow)


def test_a_float_literal_with_an_integral_value_is_the_known_exception() -> None:
    """JSON in a browser cannot keep 2.0 apart from 2: a LITERAL (bool | int | float | ...) holding
    2.0 comes back as the int 2 and the hash changes. Float FIELDS (timeout_s) are safe: the schema
    makes them floats again. Reported for Batt (MW2 report); MW1's canonical form decides."""
    flow = editor.sample_flow()
    data = json.loads(ir.to_json(flow))
    data["variables"]["X"] = {"kind": "lit", "value": 2.0}
    f2 = ir.validate(data)
    assert ir.flow_hash(ir.from_json(browser(ir.to_json(f2)))) != ir.flow_hash(f2)
