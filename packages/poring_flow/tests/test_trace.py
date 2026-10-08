"""SIMULATE for the editor (poring_flow.trace): the trace of a flow against static data and a
scenario. Synthetic sheets only (the committed sample's, and flow_synthetic's)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

from poring_flow import editor, ir, pyview
from poring_flow.trace import MAX_HORIZON_S, Scenario, simulate

sys.path.insert(0, str(Path(__file__).parent))
from flow_synthetic import FIXTURES, farm_flow, farm_world  # noqa: E402

DEATH = {"t": 200, "set": {"is_dead": True, "hp_percent": 0}}


def sample_trace(**scenario: object) -> dict:
    return simulate(editor.sample_flow(), editor.sample_world(), Scenario.model_validate(scenario))


def test_the_sample_walks_warps_farms_and_comes_back() -> None:
    t = sample_trace(horizon_s=300)
    assert t["start"] == {"block": "town", "entry": "spawn", "map": "town_1", "cell": [40, 40]}
    kinds = [(x["kind"], x["from"], x["to"]) for x in t["transitions"]]
    assert kinds[:2] == [("npc_warp", "town", "farm"), ("item_warp", "farm", "town")]
    assert all(x["arrived"] for x in t["transitions"])
    # the Kafra sets the save point at its save cell; the wing returns there
    assert t["save_point"] == {"map": "town_1", "cell": [40, 40]}
    # every town walk follows the walk grid (never through the building)
    town = editor.sample_world().sheet("town_1")
    assert town is not None and town.walk is not None
    for seg in t["paths"]:
        assert not seg["estimated"]
        assert all(town.walk.walkable((x, y)) for x, y in seg["cells"])
    walk = next(p for p in t["paths"] if p["node"] == "town.3")
    assert walk["cells"][0] == [55, 45] and walk["cells"][-1] == [83, 61]
    # per-node outcomes and durations, by MW1's node paths
    assert t["nodes"]["town.5"]["outcomes"] == t["nodes"]["town.5:choose_menu"]["outcomes"]
    assert t["nodes"]["town.5:choose_menu"]["last"] == "ok"
    assert t["nodes"]["farm.0.body.0"]["runs"] >= 20
    assert t["nodes"]["town.9"]["last"] == "exit"
    assert t["end"] == "horizon" and t["input_batches_counted"] > 0


def test_a_death_respawns_at_the_save_point_and_relocates_to_town() -> None:
    t = sample_trace(horizon_s=300, timeline=[DEATH])
    respawn = [x for x in t["transitions"] if x["kind"] == "death_respawn"]
    assert len(respawn) == 1
    assert respawn[0]["from"] == "farm" and respawn[0]["to"] == "town"
    assert respawn[0]["map"] == "town_1"
    assert any(e["kind"] == "fire" and e["what"] == "dead" for e in t["events"])
    assert t["nodes"]["dead.0"]["last"] == "ok"


def test_run_a_single_map_node() -> None:
    t = sample_trace(start_block="farm", single_block=True)
    assert t["start"]["block"] == "farm" and t["start"]["cell"] == [30, 30]
    assert t["end"] == "single_block_exit"
    assert [x["kind"] for x in t["transitions"]] == ["item_warp"]
    assert not any(p.startswith("town.") for p in t["nodes"])
    # town's Kafra never ran: the save point is unknown, and the trace says what the model did
    assert t["save_point"] is None
    assert any("UNKNOWN save point" in n for n in t["notes"])


def test_the_trace_reports_what_the_static_data_refuses() -> None:
    text = (
        (editor._examples() / "town_warp_farm.flow")
        .read_text()
        .replace('option("o_field_info")', 'option("o_not_offered")')
    )
    flow = pyview.parse(text)
    t = simulate(flow, editor.sample_world(), Scenario(horizon_s=60))
    assert t["end"] == "menu_mismatch"  # if choose_menu(...) != OK: stop("menu_mismatch")
    assert t["nodes"]["town.5:choose_menu"]["last"] == "failed"
    assert t["nodes"]["town.5.then.0"]["last"] == "stopped"
    assert any("o_not_offered" in n for n in t["notes"])


def test_without_sheets_the_walks_are_estimates() -> None:
    t = simulate(editor.sample_flow(), None, Scenario(horizon_s=60))
    assert t["paths"] and all(p["estimated"] for p in t["paths"])
    assert t["world"] == {"server": None, "maps": []}


def test_mw1_fixtures_simulate() -> None:
    t = simulate(farm_flow(), farm_world(), Scenario(horizon_s=120))
    assert [x["kind"] for x in t["transitions"]][:2] == ["walk_exit", "npc_warp"]
    plain = pyview.parse((FIXTURES / "visit_and_choose.flow").read_text())
    t2 = simulate(plain, None, Scenario(horizon_s=60))
    assert t2["start"]["block"] is None and "main.0" in t2["nodes"]


@pytest.mark.parametrize(
    "bad",
    [
        {"horizon_s": MAX_HORIZON_S + 1},
        {"weight_per_attack": -1},
        {"timeline": [{"t": 1, "set": {"position": 5}}]},  # not a scenario key
        {"timeline": [{"t": 1, "set": {}}] * 51},
        {"start_entry": "spawn"},  # an entry needs its block
        {"start_block": "farm; rm"},
        {"surprise": 1},
    ],
)
def test_scenarios_are_bounded(bad: dict) -> None:
    with pytest.raises(ValidationError):
        Scenario.model_validate(bad)


def test_an_unknown_start_block_is_refused() -> None:
    with pytest.raises(ValueError, match="no map block"):
        simulate(editor.sample_flow(), None, Scenario(start_block="nowhere"))


def test_the_trace_is_json_and_bounded() -> None:
    t = sample_trace(horizon_s=MAX_HORIZON_S, timeline=[DEATH])
    text = json.dumps(t)
    assert len(text) < 2_000_000
    assert len(t["events"]) <= 400
    assert ir.flow_hash(editor.sample_flow())  # the flow itself is untouched
