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


# --- the play list (2026-11-10, the Maps page's map view) -----------------------------------------
def _cheb(a: list[int], b: list[int]) -> int:
    return max(abs(a[0] - b[0]), abs(a[1] - b[1]))


def test_the_play_list_is_the_run_in_order() -> None:
    t = sample_trace(horizon_s=120)
    play = t["play"]
    assert play and not t["play_capped"]
    assert all(s["t0"] <= s["t1"] for s in play)
    assert all(a["t0"] <= b["t0"] for a, b in zip(play, play[1:], strict=False))
    # town: walk to (55, 45), the Kafra (a walk up to it, the talk), ..., the warper, the exit
    kinds = [(s["kind"], s.get("npc"), s.get("action")) for s in play[:4]]
    assert kinds[0] == ("walk", None, None)
    assert play[0]["cells"][0] == [40, 40] and play[0]["cells"][-1] == [55, 45]
    talk = next(s for s in play if s["kind"] == "talk" and s["npc"] == "n_kafra")
    town = editor.sample_world().sheet("town_1")
    assert town is not None and town.walk is not None
    kafra = town.npc("n_kafra")
    assert kafra is not None and talk["at"] == [kafra.x, kafra.y]
    # the walk before a talk ends next to the NPC, and every walked cell is walkable
    i = play.index(talk)
    if play[i - 1]["kind"] == "walk":
        assert _cheb(play[i - 1]["cells"][-1], talk["at"]) == 1
    for s in play:
        if s["kind"] == "walk" and s["map"] == "town_1":
            assert all(town.walk.walkable((x, y)) for x, y in s["cells"])
    menu = next(s for s in play if s["kind"] == "menu" and s["option"] == "o_field_info")
    assert menu["npc"] == "n_guide"
    assert any(s["kind"] == "wait" and s["t1"] - s["t0"] >= 2 for s in play)
    # the exits follow the transitions, and each step names the map it happens on
    exits = [s for s in play if s["kind"] == "exit"]
    assert [(s["exit"], s["from_block"], s["to_block"], s["to_map"]) for s in exits[:2]] == [
        ("npc_warp", "town", "farm", "field_1"),
        ("item_warp", "farm", "town", "town_1"),
    ]
    assert [x["t"] for x in t["transitions"][: len(exits)]] == [s["t1"] for s in exits]
    warp_talk = play[play.index(exits[0]) - 1]
    assert warp_talk["kind"] == "talk" and warp_talk["options"] == ["o_to_field"]
    after = play[play.index(exits[0]) + 1]
    assert after["map"] == "field_1" and after["block"] == "farm"


def test_without_encounters_a_fight_stands_still() -> None:
    t = sample_trace(horizon_s=120)
    fights = [s for s in t["play"] if s["kind"] == "fight"]
    assert fights and all(s["mob"] is None and s["at"] is None for s in fights)
    assert not any(s["kind"] == "walk" and s["purpose"] == "engage" for s in t["play"])
    assert all(s["loot"] for s in fights)  # the loot model adds weight per attack


def test_encounters_place_monsters_and_the_character_walks_up() -> None:
    t = sample_trace(horizon_s=120, encounters=True, seed=7)
    play = t["play"]
    field = editor.sample_world().sheet("field_1")
    assert field is not None and field.walk is not None
    fights = [s for s in play if s["kind"] == "fight"]
    assert len(fights) >= 10
    for f in fights:
        assert f["mob"] in (9101, 9102)  # farm's targets; 9105 is ignored, the boss no target
        assert field.walk.walkable(tuple(f["at"]))
        i = play.index(f)
        engage = play[i - 1]
        if engage["kind"] == "walk" and engage["purpose"] == "engage":
            assert _cheb(engage["cells"][-1], f["at"]) == 1
            assert 2 <= _cheb(engage["cells"][0], f["at"]) <= 12
            assert all(field.walk.walkable((x, y)) for x, y in engage["cells"])
            assert f["seen_t"] == engage["t0"]
    # the same seed places the same monsters; another seed others
    again = sample_trace(horizon_s=120, encounters=True, seed=7)["play"]
    other = sample_trace(horizon_s=120, encounters=True, seed=8)["play"]
    cells = [s["at"] for s in fights]
    assert [s["at"] for s in again if s["kind"] == "fight"] == cells
    assert [s["at"] for s in other if s["kind"] == "fight"] != cells


def test_encounters_take_the_named_species_and_what_the_sheet_spawns() -> None:
    text = (editor._examples() / "town_warp_farm.flow").read_text()
    flow = pyview.parse(text.replace("attack_nearest(within=12)", "attack_nearest(mob(9102))"))
    t = simulate(flow, editor.sample_world(), Scenario(horizon_s=90, encounters=True, seed=1))
    fights = [s for s in t["play"] if s["kind"] == "fight"]
    assert fights and {s["mob"] for s in fights} == {9102}
    # no sheets: the monster still stands near (an estimated walk up), of the block's targets
    sc = Scenario(horizon_s=60, encounters=True, seed=1, start_block="farm")
    t2 = simulate(editor.sample_flow(), None, sc)
    walks = [s for s in t2["play"] if s["kind"] == "walk" and s["purpose"] == "engage"]
    assert walks and all(s["estimated"] for s in walks)
    assert {s["mob"] for s in t2["play"] if s["kind"] == "fight"} <= {9101, 9102}


def test_a_respawn_arrives_on_the_save_points_map() -> None:
    t = sample_trace(horizon_s=300, timeline=[DEATH], encounters=True)
    respawn = next(s for s in t["play"] if s["kind"] == "respawn")
    arrive = t["play"][t["play"].index(respawn) + 1]
    assert arrive["kind"] == "arrive" and arrive["via"] == "respawn"
    assert arrive["map"] == "town_1" and arrive["cell"] == [40, 40]


def test_the_play_list_is_bounded() -> None:
    from poring_flow.trace import MAX_PLAY, MAX_PLAY_CELLS

    t = sample_trace(horizon_s=MAX_HORIZON_S, timeline=[DEATH], encounters=True)
    assert len(t["play"]) <= MAX_PLAY
    assert sum(len(s.get("cells") or []) for s in t["play"]) <= MAX_PLAY_CELLS
    assert len(json.dumps(t)) < 4_000_000
    with pytest.raises(ValidationError):
        Scenario.model_validate({"seed": -1})
    with pytest.raises(ValidationError):
        Scenario.model_validate({"seed": 2**31})
