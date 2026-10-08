"""The block catalogue (ADR-0020 section 2): generated from L1 plus the registry, honest about
what is unverified or unknown, and covering every L1 concept."""

from __future__ import annotations

import json

from poring_flow.catalogue import build, catalogue, coverage, document, registry
from poring_skills.schema import load_l1


def test_every_l1_concept_is_a_block_a_sensor_or_excluded_with_a_reason() -> None:
    assert coverage() == []
    cat = catalogue()
    assert set(cat.excluded) == {"session.login", "session.select_char", "session.logout"}
    assert all(len(reason) > 20 for reason in cat.excluded.values())


def test_a_new_l1_concept_without_a_block_fails_coverage() -> None:
    l1 = dict(load_l1())
    some = l1["char.sit"]
    l1["char.dance"] = some.model_copy(update={"id": "char.dance"})
    assert coverage(build(l1), l1) == ["char.dance"]


def test_every_action_block_runs_an_l1_concept_or_is_core() -> None:
    l1 = load_l1()
    for name, b in catalogue().blocks.items():
        if b.spec.kind == "core":
            assert b.status == "core" and b.spec.concept.startswith("core."), name
        else:
            assert b.spec.concept in l1, name
            assert b.status in ("verified", "unverified"), name
            assert b.runtime_outcome and b.purpose, name


def test_statuses_are_honest_today() -> None:
    """Section 12 'Today': nothing is verified; sensors without an L1 read concept are UNKNOWN
    (open question 7), never silently treated as available."""
    cat = catalogue()
    assert not [n for n, b in cat.blocks.items() if b.status == "verified"]
    unknown = {n for n, s in cat.sensors.items() if s.status == "unknown"}
    assert {"sees", "engagement_seen", "map_load_seen", "engaged_species", "base_level"} <= unknown
    assert cat.sensors["hp_percent"].status == "unverified"


def test_only_hotbar_use_item_is_insertable() -> None:
    """Batt, 2026-10-08 (open question 17)."""
    assert [n for n, b in registry().blocks.items() if b.insertable] == ["use_item"]


def test_the_new_mw1_concepts_are_written_unverified() -> None:
    l1 = load_l1()
    for cid in ("nav.set_save_point", "nav.escape"):
        assert l1[cid].status == "unverified"
    assert "hover" in " ".join(l1["loot.pick_up"].steps)
    assert "L2.cue.pickup_cursor" in l1["loot.pick_up"].bindings_needed


def test_no_block_is_a_raw_input_a_clipboard_a_chat_or_a_packet_read() -> None:
    """Section 2.1: never a block, in any version."""
    names = set(catalogue().blocks)
    for banned in (
        "click",
        "key",
        "press_key",
        "type_text",
        "paste",
        "clipboard",
        "chat",
        "whisper",
        "send_file",
        "read_packets",
        "login",
    ):
        assert banned not in names


def test_the_catalogue_is_one_json_document() -> None:
    doc = document()
    text = json.dumps(doc, sort_keys=True)
    assert json.loads(text) == doc
    assert set(doc) == {"version", "blocks", "sensors", "excluded", "constants", "helpers"}
    assert doc["blocks"]["walk_to"]["spec"]["concept"] == "nav.walk_to"
