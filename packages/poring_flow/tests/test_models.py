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
    assert 'wait_until(detector_sees("xmas02", "mystcase"), timeout_s=30)' in src
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
    assert all(len(h) == pyview.RULE_WIDTH <= 42 and h.endswith("-") for h in heads)  # fits 384 px
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


# --- round 2 (2026-11-09): the Python in the blocks' own words, the Config constants -------------
def test_wait_n_seconds_reads_as_wait_and_is_the_same_ir() -> None:
    plain = flow_of('wait(1)\nwait(2.5)\nstop("done")\n')
    long = flow_of(
        'wait_until(False, timeout_s=1)\nwait_until(False, timeout_s=2.5)\nstop("done")\n'
    )
    assert plain == long and ir.flow_hash(plain) == ir.flow_hash(long)
    src = pyview.print_flow(plain)
    assert "\n    wait(1)\n    wait(2.5)\n" in src  # whole seconds without ".0", as the block says
    # an outcome keeps the long form: wait(...) has none
    kept = flow_of('R = "x"\nR = wait_until(False, timeout_s=3)\nstop("done")\n')
    assert "R = wait_until(False, timeout_s=3)" in pyview.print_flow(kept)
    for bad in (
        'R = "x"\nR = wait(1)\n',
        "wait()\n",
        'wait("a")\n',
        "wait(True)\n",
        "wait(1, 2)\n",
    ):
        with pytest.raises(pyview.ParseError):
            flow_of(bad + 'stop("done")\n')
    with pytest.raises(pyview.ParseError, match="shadows a catalogue name"):
        flow_of('def wait():\n    stop("x")\nstop("done")\n')


def test_whole_seconds_print_as_ints_and_read_back_as_the_same_float() -> None:
    f = flow_of(
        "wait_until(hp_percent() > 90, timeout_s=30.0)\nsit(timeout_s=12.0)\nsit(timeout_s=2.5)\n"
        'stop("done")\n'
    )
    src = pyview.print_flow(f)
    assert "timeout_s=30)" in src and "sit(timeout_s=12)" in src and "sit(timeout_s=2.5)" in src
    back = pyview.parse(src)
    assert back == f and ir.canonical_json(back) == ir.canonical_json(f)
    assert '"timeout_s":30.0' in ir.canonical_json(back)  # the IR keeps its float


def test_the_config_constants_and_flow_call_are_the_same_flow() -> None:
    old = (
        'flow(ir=2, name="t", max_runtime_s=600, where_budget=3, '
        'target=target(client="kro-20211103-prere", server="lab-rathena", locale="en", path=S2))\n'
        'POTION = item(9001)\nuse_item(POTION)\nstop("done")\n'
    )
    new = (
        'FLOW_NAME = "t"\nIR_VERSION = 2\nMAX_RUNTIME_S = 600\nWHERE_BUDGET = 3\n'
        'CLIENT = "kro-20211103-prere"\nSERVER = "lab-rathena"\nLOCALE = "en"\nPATH = S2\n'
        'POTION = item(9001)\nuse_item(POTION)\nstop("done")\n'
    )
    a, b = pyview.parse(old), pyview.parse(new)
    assert a == b and ir.flow_hash(a) == ir.flow_hash(b)
    src = pyview.print_flow(a)
    head = "# Made by poring-lab from blocks.\n# Read by the flow engine, never run.\n"
    assert src.startswith(head)
    assert '\nFLOW_NAME = "t"\nIR_VERSION = 2\nMAX_RUNTIME_S = 600\nWHERE_BUDGET = 3\n' in src
    assert '\nPATH = "S2"\n' in src  # a plain string: every Config value is a Python literal
    assert all(len(line) <= 42 for line in src.splitlines() if line.startswith("#"))
    assert "\nPOTION = item(9001)\n" in src and "flow(" not in src
    with pytest.raises(pyview.ParseError, match="SERVER is set twice"):
        pyview.parse(new.replace('LOCALE = "en"', 'SERVER = "x"'))


def test_a_variable_named_like_a_constant_keeps_the_flow_call() -> None:
    src = (
        'flow(ir=2, name="t", max_runtime_s=600, target=target(client="kro-20211103-prere", '
        'server="lab-rathena", locale="en", path=S2))\nSERVER = item(9001)\nuse_item(SERVER)\n'
        'stop("done")\n'
    )
    f = pyview.parse(src)
    out = pyview.print_flow(f)
    assert "\nflow(\n" in out and "\nSERVER = item(9001)\n" in out
    assert pyview.parse(out) == f


def test_every_flow_we_have_round_trips_with_its_hash() -> None:
    """IR -> the new Python -> IR is identical, the hash too, and canonical Python is stable, for
    every committed flow source, the sample and the starter."""
    flows = [
        pyview.parse(p.read_text())
        for p in sorted((REPO / "packages/poring_flow/tests/fixtures").glob("*.flow"))
    ]
    flows += [editor.sample_flow(), ir.from_json(STARTER.read_text(encoding="utf-8"))]
    for f in flows:
        src = pyview.print_flow(f)
        back = pyview.parse(src)
        assert back == f, f.name
        assert ir.flow_hash(back) == ir.flow_hash(f), f.name
        assert pyview.print_flow(back) == src, f.name


def test_every_config_value_is_a_python_literal() -> None:
    """Round 3 (matpilot, 2026-11-09): a learner may run the Config: PATH is the text "S2", START
    a tuple; the old bare S2 and entry(...) still read back as the same flow."""
    import ast

    wf = editor.sample_flow()
    src = pyview.print_flow(wf)
    config = src.split("# --- Config")[1].split("\n# --- ")[0]
    for line in config.splitlines()[1:]:
        if line.strip():
            name, value = line.split(" = ", 1)
            ast.literal_eval(value)  # raises on a call or a bare name
    assert '\nSTART = ("town", "spawn")\n' in src and '\nPATH = "S2"\n' in src
    old = src.replace('PATH = "S2"', "PATH = S2").replace(
        'START = ("town", "spawn")', 'START = entry("town", "spawn")'
    )
    assert (
        old != src
        and pyview.parse(old) == wf
        and ir.flow_hash(pyview.parse(old)) == ir.flow_hash(wf)
    )
    with pytest.raises(pyview.ParseError):
        pyview.parse(src.replace('PATH = "S2"', 'PATH = "S9"'))
    with pytest.raises(pyview.ParseError):
        pyview.parse(src.replace('START = ("town", "spawn")', 'START = ("town",)'))


# --- round 4 (Batt 2026-11-09): the import line and Main's try / finally --------------------------
WRAP_TAIL = "finally:\n    # the engine lets go of all input\n    release_all()\n"


def test_main_runs_in_try_finally_and_the_file_imports_the_stub() -> None:
    f = ir.from_json(STARTER.read_text(encoding="utf-8"))
    src = pyview.print_flow(f)
    assert "\nfrom poring_flow.learner import *\n" in src
    assert "\ntry:\n    wait(1)\n" in src and src.endswith(WRAP_TAIL)
    assert all(len(line) <= 42 for line in src.splitlines() if line.strip().startswith("#"))
    # the older shape (no import, no wrapper) reads back as the same flow and hash
    old = src.replace("from poring_flow.learner import *\n", "").replace(WRAP_TAIL, "")
    old = old.replace("try:\n", "").replace("\n    ", "\n")
    assert "try" not in old and pyview.parse(old) == f
    assert ir.flow_hash(pyview.parse(old)) == ir.flow_hash(f) == ir.flow_hash(pyview.parse(src))


@pytest.mark.parametrize(
    "src",
    [
        HEAD + "import os\nsit()\n",
        "from poring_flow.learner import walk_to\n" + HEAD + "sit()\n",
        HEAD + "from poring_flow.learner import *\nsit()\n",  # not the first statement
        "from poring_flow.learner import * as x\n" + HEAD + "sit()\n",
        HEAD + "try:\n    sit()\nexcept E:\n    pass\n",
        HEAD + "try:\n    sit()\nfinally:\n    sit()\n",  # a different finally
        HEAD + "try:\n    sit()\nfinally:\n    release_all()\nsit()\n",  # not the last statement
        HEAD + "try:\n    sit()\nelse:\n    sit()\nfinally:\n    release_all()\n",
        HEAD + "def p():\n    try:\n        sit()\n    finally:\n        release_all()\np()\n",
        HEAD + "try:\n    def p():\n        sit()\nfinally:\n    release_all()\n",  # a def inside
        HEAD + "try:\n    NEW = 1\nfinally:\n    release_all()\n",  # a new name inside
        HEAD + "sit()\nrelease_all()\n",  # release_all outside the finally
    ],
)
def test_the_learner_shape_is_read_only_where_the_view_prints_it(src: str) -> None:
    with pytest.raises((pyview.ParseError, SyntaxError)):
        pyview.parse(src)


def test_the_learner_shape_reads_back_with_a_flow_call_head() -> None:
    src = "from poring_flow.learner import *\n" + HEAD + "try:\n    sit()\n" + WRAP_TAIL
    assert pyview.parse(src) == flow_of("sit()\n")


def test_the_learner_stub_names_everything_the_view_prints() -> None:
    import ast
    import builtins
    import inspect

    import poring_flow.learner as learner
    from poring_flow.catalogue import CONSTANTS, HELPERS, REF_CONSTRUCTORS, catalogue

    cat = catalogue()
    want = (
        set(cat.blocks) | set(cat.sensors) | set(REF_CONSTRUCTORS) | set(HELPERS) | set(CONSTANTS)
    )
    assert want - {"range"} <= set(learner.__all__) and "range" not in learner.__all__
    with pytest.raises(NotImplementedError, match="poring-lab runs flows itself"):
        learner.walk_to(None)  # type: ignore[attr-defined]
    assert learner.release_all() is None  # nothing ran in the stub: nothing is held
    assert list(inspect.signature(learner.walk_to).parameters)[0] == "cell"  # type: ignore[attr-defined]
    assert learner.OK == "ok"  # type: ignore[attr-defined]
    # every name a printed flow LOADS is defined: by the file itself, the stub, or Python
    flows = [
        pyview.parse(p.read_text())
        for p in sorted((REPO / "packages/poring_flow/tests/fixtures").glob("*.flow"))
    ]
    flows += [editor.sample_flow(), ir.from_json(STARTER.read_text(encoding="utf-8"))]
    for f in flows:
        tree = ast.parse(pyview.print_flow(f))
        stored = {
            n.id for n in ast.walk(tree) if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store)
        }
        stored |= {n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}
        loaded = {
            n.id for n in ast.walk(tree) if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load)
        }
        missing = loaded - stored - set(learner.__all__) - set(dir(builtins))
        assert not missing, (f.name, missing)
