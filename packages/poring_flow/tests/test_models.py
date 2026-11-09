"""The trained models as sensor devices (Batt 2026-11-09; ADR-0020 Amendment B): the catalogue
matches where the repo records each fact, the two detector sensors lint, simulate and round-trip
like any sensor, the Python view's sections, and the studio's starter program."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

from poring_flow import editor, ir, lint, pyview
from poring_flow.models import detector_keys, document, models
from poring_flow.trace import Scenario, simulate

REPO = Path(__file__).resolve().parents[3]
STARTER = REPO / "services/frontend/src/lib/flow/fixtures/starter.json"
HEAD = (
    'flow(ir=2, name="t", max_runtime_s=600, target=target(client="kro-20211103-prere", '
    'server="lab-rathena", locale="en", path=S2))\n'
)


def flow_of(body: str) -> ir.Flow:
    return pyview.parse(HEAD + body)


def rules(f: ir.Flow) -> list[tuple[str, str, str]]:
    return [(x.rule, x.severity, x.path) for x in lint.lint(f) if x.rule.startswith("detector")]


# --- the catalogue matches its sources -----------------------------------------------------------
@pytest.fixture(scope="module")
def scripts() -> object:
    sys.path.insert(0, str(REPO / "scripts"))
    import mvp_profiles
    import mvp_watch
    import unit_detector

    return type("S", (), {"ud": unit_detector, "mp": mvp_profiles, "mw": mvp_watch})


def test_the_detectors_match_unit_detector(scripts: object) -> None:
    ud = scripts.ud  # type: ignore[attr-defined]
    cat = models().models
    v1, xmas = cat["v1"], cat["xmas02"]
    assert v1.classes == list(ud.NAMES) and not v1.maps and v1.status == "live"
    assert v1.file == ud.GPU_WEIGHTS["v1"].onnx == ud.MODEL.name
    assert v1.sha256 == ud.GPU_WEIGHTS["v1"].onnx_sha256[:12]
    mm = ud.MAP_MODELS["xmas_dun02"]
    assert xmas.maps == ["xmas_dun02"] and xmas.status == "live"
    assert xmas.file == mm.onnx == ud.GPU_WEIGHTS["xmas02"].onnx
    assert xmas.sha256 == mm.sha256[:12] == ud.GPU_WEIGHTS["xmas02"].onnx_sha256[:12]
    # the model's own class order: the fixed classes by id, then the species (collapse's order)
    classes = json.loads((REPO / "config/detector/classes-xmas02.json").read_text())
    fixed = sorted(classes["fixed"], key=classes["fixed"].get)
    order = [*fixed, *mm.collapse]
    assert [c for c in order if c in xmas.classes] == xmas.classes
    assert sorted(xmas.classes + xmas.untrained) == sorted(order)
    assert xmas.untrained == ["npc", "warp"]  # EMPTY fixed classes (xmas02-detector.md H)
    species = list(mm.collapse)
    assert [xmas.mobs[s] for s in species] == [[m] for m in classes["monsters"]]


def test_the_boss_recognizers_match_their_profiles(scripts: object) -> None:
    mp, mw = scripts.mp, scripts.mw  # type: ignore[attr-defined]
    for mid, prof in (("stormy-v1", mp.STORMY), ("orclord-v1", mp.ORCLORD)):
        m = models().models[mid]
        assert m.kind == "boss_recognizer" and m.classes == ["party"]
        assert m.file == mw.default_model(prof.name).name
        assert m.maps == [prof.map] and m.mobs["party"] == list(prof.party)
        assert m.status == "not_adopted" and not m.available


def test_the_editor_gets_the_models() -> None:
    doc = editor.catalogue_doc()
    assert doc["models"] == document()
    assert doc["models"]["v1"]["available"] and doc["models"]["v1"]["counts"]
    assert not doc["models"]["stormy-v1"]["available"]
    assert not doc["models"]["stormy-v1"]["counts"]  # a recognizer does not count
    assert {"detector_sees", "detector_count"} <= set(doc["sensors"])


# --- lint -----------------------------------------------------------------------------------------
def test_a_live_model_and_one_of_its_classes_lints_clean() -> None:
    f = flow_of(
        'wait_until(detector_sees("v1", "monster"), timeout_s=30)\n'
        'if detector_count("xmas02", "cookie_xmas") > 2:\n    stop("many")\nstop("done")\n'
    )
    assert rules(f) == []
    assert detector_keys(f) == ["v1/monster", "xmas02/cookie_xmas"]


@pytest.mark.parametrize(
    ("cond", "rule"),
    [
        ('detector_sees("v9", "monster")', "detector_model"),
        ('detector_sees("v1", "dragon")', "detector_class"),
        ('detector_sees("xmas02", "npc")', "detector_class"),  # trained on no example
        ('detector_sees("stormy-v1", "party")', "detector_not_adopted"),
        ('detector_sees("orclord-v1", "party")', "detector_not_adopted"),
    ],
)
def test_each_rule_has_its_positive_case(cond: str, rule: str) -> None:
    f = flow_of(f'if {cond}:\n    stop("x")\nstop("done")\n')
    assert (rule, "error", "main.0") in rules(f)


def test_a_recognizer_does_not_count_and_text_is_required() -> None:
    f = flow_of(
        'M = "v1"\nif detector_count("stormy-v1", "party") > 0:\n    stop("x")\n'
        'if detector_sees(M, "monster"):\n    stop("y")\nstop("done")\n'
    )
    found = rules(f)
    assert ("detector_count_kind", "error", "main.0") in found
    assert ("detector_literal", "error", "main.1") in found


def test_a_map_scoped_model_on_another_map_warns() -> None:
    def block_on(map_id: str) -> ir.Flow:
        return pyview.parse(
            'flow(ir=2, name="t", max_runtime_s=600, start=entry("farm", "a"), '
            'target=target(client="kro-20211103-prere", server="lab-rathena", locale="en", '
            f'path=S2))\n@map_block(map_id("{map_id}"), entries=[entry_anywhere("a")])\n'
            'def farm():\n    wait_until(detector_sees("xmas02", "cookie"), timeout_s=5)\n'
            '    stop("done")\n'
        )

    assert ("detector_map", "warning", "farm.0") in rules(block_on("prt_fild08"))
    assert rules(block_on("xmas_dun02")) == []


def test_events_read_detectors_too() -> None:
    f = flow_of(
        '@on(detector_sees("stormy-v1", "party"), priority=CRITICAL)\ndef boss():\n    escape()\n'
        'stop("done")\n'
    )
    assert ("detector_not_adopted", "error", "boss") in rules(f)


# --- the Python view and SIMULATE ---------------------------------------------------------------
def test_the_python_view_round_trips_a_detector() -> None:
    f = flow_of('wait_until(detector_sees("xmas02", "mystcase"), timeout_s=30)\nstop("done")\n')
    src = pyview.print_flow(f)
    assert 'wait_until(detector_sees("xmas02", "mystcase"), timeout_s=30.0)' in src
    assert pyview.parse(src) == f


def test_simulate_takes_the_counts_from_the_scenario() -> None:
    f = flow_of(
        'wait_until(detector_sees("v1", "monster"), timeout_s=60)\n'
        'if detector_count("v1", "monster") > 1:\n    stop("many")\nstop("one")\n'
    )
    seen = simulate(f, None, Scenario.model_validate(
        {"horizon_s": 120, "timeline": [{"t": 7, "detects": {"v1/monster": 3}}]}
    ))  # fmt: skip
    assert seen["end"] == "many" and seen["t_end_s"] == pytest.approx(7.0, abs=0.5)
    assert seen["nodes"]["main.1"]["runs"] == 1 and "main.2" not in seen["nodes"]
    # no sighting in the scenario: the detector sees nothing (0 boxes), the wait times out
    none = simulate(f, None, Scenario.model_validate({"horizon_s": 120}))
    assert none["end"] == "one" and none["nodes"]["main.0"]["total_s"] == pytest.approx(60, abs=1)


def test_the_scenario_refuses_a_bad_detector_key() -> None:
    for bad in ({"v1": 1}, {"V1/monster": 1}, {"v1/monster": -1}, {"v1/monster": 1000}):
        with pytest.raises(ValidationError):
            Scenario.model_validate({"timeline": [{"t": 1, "detects": bad}]})


def test_the_python_view_is_in_sections() -> None:
    f = flow_of(
        "POTION = item(9001)\n"
        "def rest():\n    sit()\n"
        "@on(hp_percent() < 30, priority=SURVIVAL)\ndef hp_low():\n    use_item(POTION)\n"
        'rest()\nstop("done")\n'
    )
    src = pyview.print_flow(f)
    heads = [line for line in src.splitlines() if line.startswith("# --- ")]
    assert [h.split()[2] for h in heads] == ["Config", "Setup", "Functions", "Events", "Main"]
    assert all(len(h) == 76 and h.endswith("-") for h in heads)
    assert pyview.parse(src) == f and pyview.print_flow(pyview.parse(src)) == src
    workflow = pyview.parse(
        (REPO / "packages/poring_flow/tests/fixtures/farm_loop.flow").read_text()
    )
    titles = [
        ln[6:].rstrip(" -")
        for ln in pyview.print_flow(workflow).splitlines()
        if ln.startswith("# --- ")
    ]
    assert titles == ["Config", "Setup", "Map blocks", "Events"]


# --- the studio's starter program ---------------------------------------------------------------
def test_the_starter_is_canonical_and_has_no_error() -> None:
    text = STARTER.read_text(encoding="utf-8")
    f = ir.from_json(text)
    assert text == ir.to_json(f) + "\n"
    assert f.main is not None and f.workflow is None
    assert not lint.errors(lint.lint(f))
    assert pyview.parse(pyview.print_flow(f)) == f
