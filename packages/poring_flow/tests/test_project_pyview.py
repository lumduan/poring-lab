"""The project's Python view (format 3, section 4): one file per tab plus project.py, parsed and
never run; every file round-trips, and so does the whole project."""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any

import pytest

from poring_flow import project as P
from poring_flow import pyproject as V
from poring_flow import pyview

sys.path.insert(0, str(Path(__file__).parent))
from project_kit import (  # noqa: E402
    REPO,
    SAMPLE,
    XMAS,
    act,
    add_tab,
    build,
    call,
    callv,
    fdef,
    lit,
    node,
    press,
    tab,
    var,
    xmas,
)


def round_trip(p: P.Project) -> list[V.PyFile]:
    files = V.print_files(p)
    assert V.parse_files({f.path: f.text for f in files}) == p
    for f in files:
        if f.node:
            again = V.parse_tab(p, f.node, f.tab, f.text)
            assert again == p, f.path
            assert V.print_tab(again, again.node(f.node), again.node(f.node).tab(f.tab)) == (  # type: ignore[arg-type, union-attr]
                f.text)  # fmt: skip
    return files


def rich() -> P.Project:
    """Functions with every kind of input, values, returns, an override, a node's own event."""
    body = [
        {"kind": "set", "var": "TOTAL", "value": {"kind": "arith", "op": "+", "left": var("a"),
                                                   "right": var("b")}},
        {"kind": "for", "var": "x", "items": var("rest"), "body": [
            {"kind": "set", "var": "TOTAL", "value": {"kind": "arith", "op": "+",
                                                      "left": var("TOTAL"), "right": var("x")}}]},
        {"kind": "return", "value": var("TOTAL")},
    ]  # fmt: skip
    add = fdef("add", *body, params=["a", {"name": "b", "default": lit(10)}], varargs="rest",
               kwargs="opts")  # fmt: skip
    quit_ = fdef("give_up", {"kind": "return", "value": None})
    d = add_tab(xmas(), "global", tab("lib", add, quit_, vars={"TOTAL": lit(0), "x": lit(0)}))
    d = add_tab(d, "xmas_dun02", tab("keys", fdef("fly_wing", press("F6")),
                                     vars={"TOTAL": lit(5)}))  # fmt: skip
    node(d, "geffen")["tabs"][0]["main"] = [
        call("add", lit(1), lit(2), lit(3), opts_flag=lit(True)),
        {"kind": "if", "cond": {"kind": "cmp", "op": ">", "left": callv("add", lit(5), b=lit(1)),
                                "right": lit(3)},
         "then": [call("give_up")], "orelse": []},
        {"kind": "stop", "reason": "home"},
    ]  # fmt: skip
    return build(d)


def test_both_fixtures_round_trip_per_file_and_whole() -> None:
    for path in (XMAS, SAMPLE):
        files = round_trip(P.from_json(path.read_text()))
        assert files[-1].path == "project.py" and (files[-1].node, files[-1].tab) == ("", "")


def test_the_files_and_their_paths() -> None:
    files = V.print_files(P.from_json(XMAS.read_text()))
    assert [(f.node, f.tab, f.path) for f in files] == [
        ("login", "main", "login/main.py"),
        ("character", "main", "character/main.py"),
        ("xmas_dun02", "main", "xmas_dun02/main.py"),
        ("geffen", "main", "geffen/main.py"),
        ("global", "keys", "global/keys.py"),
        ("global", "safety", "global/safety.py"),
        ("", "", "project.py"),
    ]
    by = {f.path: f.text for f in files}
    assert (
        'def main():\n    login(server="lab-rathena", credential="lab_gm")\n' in by["login/main.py"]
    )
    assert "def main():\n    choose_character()\n" in by["character/main.py"]
    assert "from global_ import *  # Global's tabs\n" in by["xmas_dun02/main.py"]
    assert "from global_ import" not in by["global/keys.py"]
    assert "from .safety import *\n" in by["global/keys.py"]
    assert (
        '@map_node(\n    "xmas_dun02",\n    entries=[entry_anywhere("here")],\n'
        '    zones=zones("xmas_dun02", sha256="89ea7a9c98d5d62b869a99189119548ea114868566bd293d43'
        'd46e3f24ebe345"),\n)\ndef main():\n'
    ) in by["xmas_dun02/main.py"]
    assert "dungeon_hunt(heal=heal, fly=fly_wing, knife_on=knife_on, knife_back=knife_back)" in (
        by["xmas_dun02/main.py"])  # fmt: skip
    assert (
        'take_exit(item_warp(using=butterfly_wing, to=entry("geffen", "save")))'
        in by["xmas_dun02/main.py"]
    )
    assert (
        "@on(hp_percent() < 30, rearm=hp_percent() > 50, priority=SURVIVAL, mode=INSERT)\n"
        "def hp_low():\n    heal()\n"
    ) in by["global/safety.py"]
    assert 'node("xmas_dun02", kind="map", pos=(230, 0), tabs=["main"])' in by["project.py"]
    assert 'edge("character", "xmas_dun02", entry="here")' in by["project.py"]
    for text in by.values():  # the generated comment lines fit the 384 px pane (pyview's rule)
        assert all(len(line) <= pyview.RULE_WIDTH for line in text.splitlines()
                   if line.startswith("#"))  # fmt: skip


def test_inputs_values_returns_and_overrides_are_python() -> None:
    p = rich()
    by = {f.path: f.text for f in round_trip(p)}
    lib = by["global/lib.py"]
    assert "def add(a, b=10, *rest, **opts):\n" in lib
    assert "    return TOTAL\n" in lib and "def give_up():\n    return\n" in lib
    assert "    add(1, 2, 3, opts_flag=True)\n" in by["geffen/main.py"]
    assert "    if add(5, b=1) > 3:\n        give_up()\n" in by["geffen/main.py"]
    keys = by["xmas_dun02/keys.py"]
    assert "# overrides Global's TOTAL (tab lib)\nTOTAL = 5\n" in keys
    assert "# overrides Global's fly_wing (tab keys)\ndef fly_wing():\n" in keys
    assert "from .keys import *" in by["xmas_dun02/main.py"]


def test_the_parser_ignores_the_override_comment_and_edits_one_tab() -> None:
    p = P.from_json(XMAS.read_text())
    src = V.print_tab(p, p.node("global"), p.node("global").tab("keys"))  # type: ignore[arg-type, union-attr]
    edited = src.replace('press_key("F8")', 'press_key("F7")').replace(
        "def fly_wing", "# a person's comment\ndef fly_wing"
    )
    q = V.parse_tab(p, "global", "keys", edited)
    assert P.runner_keys(q, "xmas_dun02").keys["fly_key"] == "F7"  # type: ignore[index]


def test_a_secret_is_never_printed() -> None:
    d = xmas()
    node(d, "login")["tabs"][0]["main"] = [act("login", server=lit("lab-rathena"),
                                              credential=lit("Hunter2-pass!"))]  # fmt: skip
    doc = V.python_doc(build(d))
    text = "\n".join(f["text"] for f in doc["files"])
    assert "Hunter2" not in text and 'credential="<redacted>"' in text
    assert doc["project_hash"] is None


@pytest.mark.parametrize(
    ("change", "message"),
    [
        (lambda s: "import os\n" + s, "Import is not allowed in a flow (no imports"),
        (lambda s: s + "\nsit()\n", "Expr is not allowed in a flow (a tab holds variables"),
        (lambda s: s + "\n\ndef f(a, /, b):\n    sit()\n", "with / or keyword-only inputs"),
        (lambda s: s + "\n\ndef f(**k):\n    heal(**k)\n", "**kwargs is not allowed in a flow"),
        (lambda s: s + "\n\ndef main():\n    sit()\n", "def main() is the main tab's program"),
        (lambda s: s + "\n\ndef f():\n    nobody()\n", "nobody(...) is not a block, a procedure"),
    ],
)  # fmt: skip
def test_the_parser_refuses_what_a_tab_cannot_hold(change: Any, message: str) -> None:
    p = P.from_json(XMAS.read_text())
    src = V.print_tab(p, p.node("global"), p.node("global").tab("keys"))  # type: ignore[arg-type, union-attr]
    with pytest.raises(pyview.ParseError) as e:
        V.parse_tab(p, "global", "keys", change(src))
    assert any(message in m for m in e.value.messages), e.value.messages
    assert all(m.startswith("global/keys.py: ") for m in e.value.messages)


def test_return_outside_a_def_is_refused() -> None:
    p = P.from_json(XMAS.read_text())
    src = V.print_tab(p, p.node("geffen"), p.node("geffen").tab("main"))  # type: ignore[arg-type, union-attr]
    with pytest.raises(pyview.ParseError, match="return belongs inside a function"):
        V.parse_tab(p, "geffen", "main", src.replace('stop("home")', "return"))


def test_the_session_mock_s_numbers_are_session_ts_s() -> None:
    ts = (REPO / "services/frontend/src/lib/maps/session.ts").read_text(encoding="utf-8")
    m = re.search(r"SESSION_S: Record<\w+, number> = \{ start: (\d+), login: (\d+), "
                  r"character: (\d+) \}", ts)  # fmt: skip
    assert m is not None
    assert [float(x) for x in m.groups()] == [
        P.SESSION_S[k] for k in ("start", "login", "character")
    ]
    assert f"export const MAX_SLOT = {P.MAX_SLOT};" in ts
    assert "export const CHAR_NAME = /^[A-Za-z0-9_][A-Za-z0-9 _]{0,22}$/;" in ts
    assert P.CHAR_NAME.pattern == "^[A-Za-z0-9_][A-Za-z0-9 _]{0,22}$"
