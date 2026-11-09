"""The Python view (ADR-0020 7.2, 7.5): parsed with ast and NEVER run; round trips; a hostile
corpus refused with line numbers and without a crash."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from poring_flow import ir, pyview

sys.path.insert(0, str(Path(__file__).parent))
from flow_synthetic import FIXTURES, farm_flow  # noqa: E402

HEAD = (
    'flow(ir=2, name="t", max_runtime_s=600, target=target(client="kro-20211103-prere", '
    'server="lab-rathena", locale="en", path=S2))\n'
)
SOURCES = sorted(FIXTURES.glob("*.flow"))


def parse_ok(body: str) -> ir.Flow:
    return pyview.parse(HEAD + body)


def refused(body: str) -> list[str]:
    with pytest.raises(pyview.ParseError) as e:
        pyview.parse(HEAD + body)
    return e.value.messages


@pytest.mark.parametrize("path", SOURCES, ids=[p.stem for p in SOURCES])
def test_round_trips(path: Path) -> None:
    """IR -> Python -> IR is identical; Python -> IR -> Python is identical for canonical Python."""
    flow = pyview.parse(path.read_text())
    canonical = pyview.print_flow(flow)
    again = pyview.parse(canonical)
    assert again == flow
    assert ir.canonical_json(again) == ir.canonical_json(flow)
    assert pyview.print_flow(again) == canonical


def test_the_13_6_8_example_maps_onto_the_ir() -> None:
    flow = farm_flow()
    wf = flow.workflow
    assert wf is not None and wf.run_until_stopped
    assert (wf.start_block, wf.start_entry) == ("town", "A")
    assert [b.name for b in wf.blocks] == ["town", "relay", "farm"]
    assert [h.name for h in flow.handlers] == [
        "dead",
        "hp_critical",
        "unexpected_map",
        "hp_low",
        "weight",
        "unintended_engagement",
    ]
    town, relay, farm = wf.blocks
    assert [type(e).__name__ for e in town.events] == ["Disable", "Disable"]
    assert [type(e).__name__ for e in relay.events] == ["Extend"]
    assert [(type(e).__name__, ir.event_key(e), ir.event_label(e, farm)) for e in farm.events] == [
        ("Override", "hp_low", "farm_hp_low"),
        ("Add", "boss_seen", "boss_seen"),
        ("Override", "unintended_engagement", "farm_engagement"),
    ]
    exit_ = farm.main[1]
    assert isinstance(exit_, ir.TakeExit) and exit_.exit.item == ir.Var(name="WING")
    assert flow.variables["BOSS"].value == ir.MobRef(id=9109)


def test_outcomes_and_procedures_and_loops() -> None:
    flow = parse_ok(
        'RESULT = "ok"\nCOUNT = 0\nSPOTS = [cell("m", 1, 2), cell("m", 3, 4)]\n'
        'SPOT = cell("m", 1, 2)\n'
        "def rest():\n    sit()\n    wait_until(hp_percent() > 90, timeout_s=120)\n    stand()\n"
        'RESULT = choose_menu(option("o_1"))\n'
        "for _ in range(3):\n    rest()\n"
        "for SPOT in SPOTS:\n    walk_to(SPOT, timeout_s=30)\n"
        "while bounded(COUNT < 5, max_iter=10):\n    COUNT += 1\n"
        'if RESULT != OK and not known(hp_percent()):\n    stop("menu_mismatch")\n'
        "elif hp_percent() < 10:\n    use_item(item(9001), on_fail=CONTINUE)\nelse:\n    pass\n"
    )
    main = flow.main or []
    assert isinstance(main[0], ir.ActionStmt) and main[0].outcome_to == "RESULT"
    assert isinstance(main[1], ir.Repeat) and isinstance(main[2], ir.ForEach)
    assert isinstance(main[3], ir.While) and main[3].max_iter == 10
    assert isinstance(main[4], ir.If) and isinstance(main[4].orelse[0], ir.If)
    assert pyview.parse(pyview.print_flow(flow)) == flow


HOSTILE = [
    (
        "import os",
        "line 2, col 1: Import is not allowed in a flow (no imports: the block API is flat names)",
    ),
    ("from os import path", "line 2, col 1: ImportFrom is not allowed in a flow"),
    ("walk_to.__class__", "line 2, col 1: Attribute is not allowed in a flow"),
    ("x = [1][0]", "Subscript is not allowed in a flow"),
    ("f = lambda: 1", "Lambda is not allowed in a flow"),
    ("class A:\n    pass", "ClassDef is not allowed in a flow"),
    ("async def a():\n    pass", "AsyncFunctionDef is not allowed in a flow"),
    ("def p():\n    return 1", "Return is not allowed in a flow"),
    ("def p():\n    yield 1", "Yield is not allowed in a flow"),
    ("global X", "Global is not allowed in a flow"),
    ("with x:\n    pass", "With is not allowed in a flow"),
    ("try:\n    sit()\nexcept E:\n    pass", "Try is not allowed in a flow"),
    ("raise E", "Raise is not allowed in a flow"),
    ("assert x", "Assert is not allowed in a flow"),
    ("del x", "Delete is not allowed in a flow"),
    ("match x:\n    case 1:\n        pass", "Match is not allowed in a flow"),
    ("x: int = 1", "AnnAssign is not allowed in a flow"),
    ("(x := 1)", "NamedExpr is not allowed in a flow"),
    ("x = 1 if y else 2", "IfExp is not allowed in a flow"),
    ("x = [i for i in y]", "ListComp is not allowed in a flow"),
    ('x = f"{y}"', "JoinedStr is not allowed in a flow"),
    ("sit(*a)", "Starred is not allowed in a flow"),
    ("x = {}", "Dict is not allowed in a flow"),
    ("x = {1}", "Set is not allowed in a flow"),
    ("x = 2 ** 8", "Pow is not allowed in a flow"),
    ("x = 1 / 2", "Div is not allowed in a flow"),
    ("x = 1 | 2", "BitOr is not allowed in a flow"),
    ("x = 1 << 2", "LShift is not allowed in a flow"),
    ("x = a is b", "Is is not allowed in a flow"),
    ("sit(**k)", "**kwargs is not allowed in a flow"),
    ("@property\ndef p():\n    sit()", "this decorator is not allowed in a flow"),
    ("x = 10 ** 30", "Pow is not allowed in a flow"),
    ("X = 99999999999999999999", "this integer is not allowed in a flow"),
    ("__import__('os')", "name __import__ is not allowed in a flow (a name starting with _"),
    ("exec('sit()')", "exec(...) is not a block, a procedure or a flow statement"),
    ("eval('1')", "eval(...) is not a block, a procedure or a flow statement"),
    ("open('/etc/passwd')", "open(...) is not a block, a procedure or a flow statement"),
    ("print(1)", "print(...) is not a block, a procedure or a flow statement"),
    # NFKC look-alike: ast.parse would read the fullwidth s as "sit" (found by this test)
    ("ｓit()", "line 2, col 1: name 'ｓit' is not allowed in a flow (names are ASCII only)"),
    ("walk_to = 1", "walk_to shadows a catalogue or definition name"),
    ("def walk_to():\n    sit()", "def walk_to shadows a catalogue name"),
    ("def p(a):\n    sit()", "def p with arguments is not allowed in a flow"),
    ("def p():\n    def q():\n        sit()", "def q here is not allowed in a flow"),
    ("while x:\n    sit()\nelse:\n    stand()", "while...else is not allowed in a flow"),
    ("break", "break outside a loop"),
    ("sit(1, 2)", "sit(...) takes at most 0 positional arguments"),
    ("walk_to()", "walk_to(...) needs cell"),
    ('walk_to(cell("m", 1, 2), speed=3)', "walk_to(...) has no parameter speed"),
    ("hp_percent()", "hp_percent() is a sensor: use it in a condition"),
    ("y = 1\ny = 2\nz = 3", "z is not a flow variable: declare it at the top with its value"),
]


@pytest.mark.parametrize(("body", "expected"), HOSTILE, ids=[h[0][:24] for h in HOSTILE])
def test_the_hostile_corpus_is_refused_with_line_numbers(body: str, expected: str) -> None:
    msgs = refused(body)
    assert any(expected in m for m in msgs), msgs
    assert all(m.startswith("line ") for m in msgs), msgs


def test_the_source_and_its_nesting_are_capped() -> None:
    assert "bytes; at most" in refused("# " + "x" * 70_000)[0]
    assert "lines; at most" in refused("\n" * 2100)[0]
    deep = "x = " + "(" * 40 + "1" + ")" * 40
    assert "brackets nested deeper than 32" in refused(deep)[0]
    nest = "".join("    " * i + "if True:\n" for i in range(18)) + "    " * 18 + "sit()\n"
    assert "statements nested deeper than 16" in refused(nest)[0]
    many = "\n".join("sit()" for _ in range(1700))
    assert "more than 5000 syntax nodes" in refused(many)[0]


def test_a_huge_file_is_refused_without_a_crash() -> None:
    with pytest.raises(pyview.ParseError) as e:
        pyview.parse("sit()\n" * 2_000_000)  # ~12 MB
    assert "bytes; at most" in e.value.messages[0]


def test_errors_are_capped_at_50() -> None:
    assert len(refused("\n".join(f"import m{i}" for i in range(80)))) == 50


def test_parse_never_runs_the_source(tmp_path: Path) -> None:
    """A side effect in the source never happens: nothing is executed or imported."""
    marker = tmp_path / "ran"
    src = HEAD + f"open({str(marker)!r}, 'w')\n__import__('os').system('touch {marker}')\n"
    with pytest.raises(pyview.ParseError):
        pyview.parse(src)
    assert not marker.exists()


def test_the_bare_underscore_is_only_repeats_target() -> None:
    """#16 (Batt 2026-10-09): `repeat N` prints as `for _ in range(N)`, the ONE exception to the
    underscore rule; `_` is nothing else (not a variable, not another loop's target)."""
    flow = parse_ok("for _ in range(3):\n    sit()\n")
    assert isinstance((flow.main or [])[0], ir.Repeat)
    assert "    for _ in range(3):\n        sit()" in pyview.print_flow(flow)  # Main in try
    assert refused('SPOTS = [cell("m", 1, 2)]\nfor _ in SPOTS:\n    sit()\n') == [
        "line 3, col 1: for _ in range(n) is the repeat block: one argument"
    ]
    assert refused("for _ in range(1, 3):\n    sit()\n") == [
        "line 2, col 1: for _ in range(n) is the repeat block: one argument"
    ]
    assert refused("X = 1\nfor _ in range(3):\n    X = _\n") == [
        "line 4, col 9: _ is not a flow variable"
    ]
    assert refused("for _x in range(3):\n    sit()\n") == [
        "line 2, col 5: name _x is not allowed in a flow (a name starting with _ is refused)"
    ]


def test_close_npc_dialog_is_an_alias_that_warns() -> None:
    """#7 (Batt 2026-10-09): ONE block, close_dialog (idempotent); close_npc_dialog imports as it,
    with a warning, and nothing prints or stores the old name."""
    seen: list[str] = []
    flow = pyview.parse(HEAD + "close_npc_dialog()\n", warnings=seen)
    a = (flow.main or [])[0]
    assert isinstance(a, ir.ActionStmt) and a.block == "close_dialog" and a.concept == "npc.close"
    assert seen == ["line 2, col 1: close_npc_dialog() is an alias of close_dialog(): imported as "
                    "close_dialog"]  # fmt: skip
    assert "close_npc_dialog" not in pyview.print_flow(flow)
    assert flow == pyview.parse(HEAD + "close_dialog()\n")
    with pytest.warns(pyview.AliasWarning, match="alias of close_dialog"):
        pyview.parse(HEAD + "close_npc_dialog()\n")
    from poring_flow.catalogue import catalogue

    assert "close_npc_dialog" not in catalogue().blocks
