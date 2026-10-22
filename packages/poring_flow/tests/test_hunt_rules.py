"""The hunt block's rule versions for the editor (blocks-from-hunt-flow.md B2): groups as lists of
rule versions, their numbers read-only, and badges derived only from the committed index and the
evidence record -- D8's rule (pre-registered, hard bars 0, >= 4 run-hours) decides the hunting-
evidence badge, beside the L1 badge and never in place of it."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest
import yaml  # type: ignore[import-untyped]  # no stubs in the dev env

from poring_flow.catalogue import catalogue
from poring_flow.hunt_rules import D8_MIN_HOURS, RulesError, d8_ok, rules_doc

REPO = Path(__file__).resolve().parents[3]
HUNT = REPO / "config" / "flows" / "hunt"
TS_HUNT = REPO / "services/frontend/src/lib/flow/fixtures/hunt_rules.json"


def index() -> dict[str, Any]:
    return dict(yaml.safe_load((HUNT / "index.yaml").read_text(encoding="utf-8")))


def evidence() -> dict[str, Any]:
    return dict(yaml.safe_load((HUNT / "evidence.yaml").read_text(encoding="utf-8")))


def choice(doc: dict[str, Any], param: str, cid: str) -> dict[str, Any]:
    for g in doc["groups"]:
        for p in g["params"]:
            if p["name"] == param:
                return next(c for c in p["choices"] if c["id"] == cid)  # type: ignore[no-any-return]
    raise KeyError(param)


def test_groups_are_the_registrys_with_the_adopted_rule_as_default() -> None:
    doc = rules_doc(index(), evidence())
    spec = catalogue().blocks["hunt"].spec
    assert [g["name"] for g in doc["groups"]] == ["engage", "dead_loot", "search", "stop"]
    shown = {p["name"]: [c["id"] for c in p["choices"]] for g in doc["groups"] for p in g["params"]}
    # every choice and option, only those
    assert shown == {p.name: p.choices or p.options for p in spec.params}
    defaults = {p["name"]: p["default"] for g in doc["groups"] for p in g["params"]}
    assert defaults == {
        "strike": "arm_c@32", "engage_on_the_way": "on_the_way@19", "dead": "exp_line@48",
        "loot": "gm_fast_scan@54", "search": "heading_coverage@22",
        "engage_source": "detector",  # an OPTION: the registry's default (absent = detector)
        "search_route": "heading",  # an OPTION too (absent = heading: today's heading search)
    }  # fmt: skip
    assert doc["adopted"] == 55 and doc["groups"][-1]["params"] == []  # 52 until 3.97 (10-22 04:32)


def test_engage_source_is_an_option_in_the_engage_group_with_no_version_or_badge() -> None:
    """Batt 2026-10-22: the melee ring is a selectable option, default OFF (detector). A plain
    value, not a rule version: no PARAMS version holds it, so no numbers and no D8 evidence."""
    doc = rules_doc(index(), evidence())
    engage = next(g for g in doc["groups"] if g["name"] == "engage")
    assert [p["name"] for p in engage["params"]] == ["strike", "engage_on_the_way", "engage_source"]
    es = engage["params"][-1]
    assert es["kind"] == "option" and es["required"] is False and es["default"] == "detector"
    assert "melee_ring" in es["note"] and "IGNORE" in es["note"]
    assert [(c["id"], c["is_default"]) for c in es["choices"]] == [
        ("detector", True),
        ("melee_ring", False),
    ]
    for c in es["choices"]:
        assert c["option"] and c["known"] and not c["adopted"]
        assert c["values"] == {} and c["versions"] == [] and c["evidence"] == []
    assert {p["kind"] for p in engage["params"][:2]} == {"rule"}
    assert all(p["required"] for p in engage["params"][:2])


def test_search_route_is_an_option_in_the_search_group_with_no_version_or_badge() -> None:
    """Batt 2026-10-22 (the Crusader's orcsdun01 demo): walk the map's reviewed patrol route, an
    option beside the heading search's rule version; absent = heading, so old flows keep their
    hash. A plain value: no PARAMS version holds it, no numbers, no D8 evidence."""
    doc = rules_doc(index(), evidence())
    search = next(g for g in doc["groups"] if g["name"] == "search")
    assert [p["name"] for p in search["params"]] == ["search", "search_route"]
    sr = search["params"][-1]
    assert sr["kind"] == "option" and sr["required"] is False and sr["default"] == "heading"
    assert "config/routes/<map>.yaml" in sr["note"] and "AHEAD" in sr["note"]
    assert [(c["id"], c["is_default"]) for c in sr["choices"]] == [
        ("heading", True),
        ("patrol_route", False),
    ]
    for c in sr["choices"]:
        assert c["option"] and c["known"] and not c["adopted"]
        assert c["values"] == {} and c["versions"] == [] and c["evidence"] == []
    assert search["params"][0]["kind"] == "rule" and search["params"][0]["required"]


def test_each_rule_version_carries_its_numbers_and_the_versions_that_hold_it() -> None:
    doc = rules_doc(index(), evidence())
    fast = choice(doc, "loot", "gm_fast_scan@54")  # the adopted base's since 3.97 (v55)
    assert fast["adopted"] and fast["known"] and fast["versions"] == [54, 55]
    assert fast["values"]["loot_fast_scan"] is True and fast["values"]["loot_gm_one_pass"] is True
    one = choice(doc, "loot", "gm_scan_one_pass@51")  # v52's, adopted until 3.97
    assert not one["adopted"] and one["known"] and one["versions"] == [51, 52]
    assert one["values"]["loot_gm_one_pass"] is True and one["values"]["loot_gm_stand_s"] == 0.5
    v50 = choice(doc, "loot", "gm_scan@50")
    assert (
        not v50["adopted"] and v50["versions"] == [50] and "loot_gm_one_pass" not in v50["values"]
    )


def test_d8_badges_come_only_from_qualifying_verdicts() -> None:
    doc = rules_doc(index(), evidence())
    assert doc["evidence"]["badges"] == ["one path (RDP), prt_fild08"]
    assert [e["entry"] for e in choice(doc, "loot", "gm_scan@50")["evidence"]] == ["3.91"]
    assert [e["entry"] for e in choice(doc, "loot", "gm_scan_one_pass@51")["evidence"]] == ["3.92"]
    assert [e["entry"] for e in choice(doc, "strike", "arm_c@32")["evidence"]] == [
        "3.91",
        "3.92",
        "3.97",
    ]
    assert [e["entry"] for e in choice(doc, "loot", "gm_fast_scan@54")["evidence"]] == ["3.97"]
    # each D8 condition alone takes the badge away
    for change, why in (
        ({"pre_registered": ""}, "not pre-registered"),
        ({"hard_bars": [0, 1, 0]}, "hard bars"),
        ({"minutes": 59}, "run-hours"),
    ):
        ev = evidence()
        ev["verdicts"] = [{**r, **change} for r in ev["verdicts"]]
        d = rules_doc(index(), ev)
        assert d["evidence"]["badges"] == [] and choice(d, "loot", "gm_scan@50")["evidence"] == []
        assert all(why in r["why_not"] for r in d["evidence"]["verdicts"])
    assert d8_ok({"pre_registered": "x", "hard_bars": [0, 0, 0], "runs": 4, "minutes": 60})[0]
    assert D8_MIN_HOURS == 4.0


def test_no_evidence_file_no_evidence_badge() -> None:
    doc = rules_doc(index(), None)
    assert doc["evidence"]["badges"] == [] and doc["evidence"]["verdicts"] == []
    assert choice(doc, "loot", "gm_fast_scan@54")["adopted"]  # adoption is the index's


def test_a_choice_the_index_does_not_know_is_shown_unknown() -> None:
    idx = index()
    del idx["rules"]["loot"]["gm_scan@50"]
    assert choice(rules_doc(idx, evidence()), "loot", "gm_scan@50")["known"] is False


@pytest.mark.parametrize(
    ("which", "edit", "match"),
    [
        ("index", lambda d: d.update(kind="hunt-config"), "index: kind"),
        ("index", lambda d: d.update(adopted=99), "adopted version 99"),
        ("evidence", lambda d: d.update(format=2), "evidence: kind"),
        ("evidence", lambda d: d["verdicts"][0].pop("gm"), "keys"),
        ("evidence", lambda d: d["verdicts"][0].update(version=999), "not in the index"),
    ],
)
def test_a_document_this_module_does_not_read_is_refused(which: str, edit: Any, match: str) -> None:
    idx, ev = copy.deepcopy(index()), copy.deepcopy(evidence())
    edit(idx if which == "index" else ev)
    with pytest.raises(RulesError, match=match):
        rules_doc(idx, ev)


def hunt_fixture() -> str:
    """The frontend's hunt-block fixture (hunt.test.ts, blocks.test.ts): the committed index and
    evidence through rules_doc, as the catalogue serves it."""
    return json.dumps(rules_doc(index(), evidence()), indent=1, ensure_ascii=False) + "\n"


def test_the_frontends_hunt_fixture_is_current() -> None:
    """Regenerate with: python scripts/gen_zones_fixtures.py"""
    assert TS_HUNT.read_text(encoding="utf-8") == hunt_fixture(), "scripts/gen_zones_fixtures.py"
