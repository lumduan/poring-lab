"""The flow IR (ADR-0020 sections 1 and 13.1): valid fixtures validate, invalid ones fail with their
message, IR -> JSON -> IR is byte-identical, imported JSON is hostile input."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

from poring_flow import ir, pyview

sys.path.insert(0, str(Path(__file__).parent))
from flow_synthetic import FIXTURES, farm_flow  # noqa: E402

TARGET = {"client": "kro-20211103-prere", "server": "lab-rathena", "locale": "en"}


def plain(*main: dict[str, Any], **over: Any) -> dict[str, Any]:
    return {
        "ir": 1,
        "name": "t",
        "target": TARGET,
        "max_runtime_s": 600,
        "main": list(main),
        **over,
    }


def act(block: str, concept: str, **params: Any) -> dict[str, Any]:
    return {"kind": "action", "block": block, "concept": concept, "timeout_s": 5, "params": params}


CELL = {"kind": "lit", "value": {"kind": "cell", "map": "m", "x": 1, "y": 2}}
SIT = act("sit", "char.sit")


def valid_fixtures() -> list[ir.Flow]:
    return [
        farm_flow(),
        pyview.parse((FIXTURES / "visit_and_choose.flow").read_text()),
        ir.validate(plain(act("walk_to", "nav.walk_to", cell=CELL), SIT)),
    ]


@pytest.mark.parametrize("flow", valid_fixtures(), ids=["farm_loop", "visit_and_choose", "plain"])
def test_ir_json_ir_is_byte_identical(flow: ir.Flow) -> None:
    text = ir.to_json(flow)
    again = ir.from_json(text)
    assert again == flow
    assert ir.to_json(again) == text
    assert ir.flow_hash(again) == ir.flow_hash(flow)
    assert text == ir.canonical_json(flow)


def test_canonical_json_is_sorted_and_compact() -> None:
    text = ir.canonical_json(farm_flow())
    data = json.loads(text)
    assert text == json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    assert len(ir.flow_hash(farm_flow())) == 64


INVALID = [
    (
        plain(act("walk_to", "nav.walk_to", cell=CELL) | {"on_fail": "retry"}),
        ["main.0: on_fail: Input should be 'stop' or 'continue'"],
    ),
    (plain(SIT) | {"surprise": 1}, ["flow: surprise: Extra inputs are not permitted"]),
    (plain(), ["flow: main needs at least one statement"]),
    (
        plain(SIT) | {"workflow": {"start_block": "a", "start_entry": "b", "blocks": []}},
        ["flow: workflow.blocks: List should have at least 1 item after validation, not 0"],
    ),
    (
        plain(SIT, max_runtime_s=0),
        ["flow: max_runtime_s: Input should be greater than or equal to 1"],
    ),
    (
        plain(
            {
                "kind": "if",
                "cond": {"kind": "lit", "value": True},
                "then": [act("sit", "char.sit") | {"timeout_s": 900}],
            }
        ),
        ["main.0.then.0: timeout_s: Input should be less than or equal to 600"],
    ),
    (
        plain(
            SIT,
            handlers=[
                {
                    "name": "h",
                    "when": {"kind": "lit", "value": True},
                    "priority": "survival",
                    "until": {"kind": "lit", "value": True},
                    "rearm": {"kind": "lit", "value": True},
                    "body": [SIT],
                }
            ],
        ),
        ["h: until (a repeating event) and rearm (a one-shot event) are exclusive"],
    ),
    (
        plain(
            SIT,
            handlers=[
                {
                    "name": "h",
                    "when": {"kind": "lit", "value": True},
                    "priority": "guard",
                    "body": [SIT],
                }
            ],
        ),
        ["h: priority: Input should be 'critical', 'survival' or 'upkeep'"],
    ),
]


@pytest.mark.parametrize(("data", "messages"), INVALID)
def test_invalid_fixtures_fail_with_their_message(
    data: dict[str, Any], messages: list[str]
) -> None:
    with pytest.raises(ir.FlowError) as e:
        ir.validate(data)
    assert e.value.messages == messages


def test_a_death_respawn_exit_is_never_authored() -> None:
    wf = json.loads(ir.to_json(farm_flow()))
    wf["workflow"]["blocks"][2]["main"][1]["exit"] = {
        "kind": "death_respawn",
        "to_block": "town",
        "to_entry": "A",
    }
    with pytest.raises(ir.FlowError) as e:
        ir.validate(wf)
    assert e.value.messages == [
        "farm.1: exit: death_respawn is derived from the dead event, never authored"
    ]


def test_an_exit_takes_exactly_its_own_fields() -> None:
    wf = json.loads(ir.to_json(farm_flow()))
    wf["workflow"]["blocks"][0]["main"][3]["exit"]["item"] = {"kind": "item", "id": 9002}
    with pytest.raises(ir.FlowError) as e:
        ir.validate(wf)
    assert e.value.messages == [
        "town.3: exit: walk_exit takes warp (missing none, not allowed ['item'])"
    ]


def test_map_event_labels_are_filled_by_default() -> None:
    wf = json.loads(ir.to_json(farm_flow()))
    for ev in wf["workflow"]["blocks"][2]["events"]:
        ev.pop("label", None)
    flow = ir.validate(wf)
    farm = flow.workflow.blocks[2]  # type: ignore[union-attr]
    assert [ir.event_label(e, farm) for e in farm.events] == [
        "farm_hp_low",
        "boss_seen",
        "farm_unintended_engagement",
    ]


def test_imported_json_is_size_and_depth_capped() -> None:
    with pytest.raises(ir.FlowError, match="bytes; at most"):
        ir.from_json(" " * (ir.MAX_JSON_BYTES + 1))
    with pytest.raises(ir.FlowError, match="nested deeper than"):
        ir.from_json("[" * 300 + "]" * 300)
    with pytest.raises(ir.FlowError, match="not JSON"):
        ir.from_json("{")


def test_node_paths_follow_section_1_and_13_1() -> None:
    paths = [s.path for s in ir.sites(farm_flow())]
    assert paths[:3] == ["dead.0", "hp_critical.0", "unexpected_map.0"]  # global events by name
    for p in (
        "town.3",
        "farm.0.body.0",
        "farm_engagement.0.then.0",
        "farm_engagement.0.orelse.0",
        "relay_recover.0",
        "farm_hp_low.0",
        "boss_seen.0",
    ):
        assert p in paths, p


def test_text_is_never_stored_only_keys_and_ids() -> None:
    """ADR-0012: the IR holds keys and ids; the only free text is a description, notes and the
    flow's own string constants."""
    data = json.loads(ir.to_json(farm_flow()))
    assert data["description"] == ""

    def strings(o: Any) -> list[str]:
        if isinstance(o, str):
            return [o]
        if isinstance(o, dict):
            return [s for v in o.values() for s in strings(v)]
        if isinstance(o, list):
            return [s for v in o for s in strings(v)]
        return []

    assert all(len(s) <= 48 for s in strings(data))
