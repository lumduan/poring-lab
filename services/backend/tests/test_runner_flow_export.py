"""runner_flow_export (Batt 2026-11-12, rogue-xmas02.md 4CQ: "make the flows of this map, so I can
see how the bot works"): the description of dungeon_hunt.py's xmas_dun02 Rogue as blocks and an
outline -- its Python outline is valid Python, its numbers are the module's own, its flags are
`run`'s real flags, and it carries no GPL-derived value (the species' worth stays at run time).
➡️ 2026-11-14 (live-blocks.md 12): the /flows runner page and its generated runners/*.gen.ts went
(their drift test with them); the outline stays for stage 5b and the docs (`show`)."""

from __future__ import annotations

import contextlib
import io
import json
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts"))

import dungeon_hunt as dh  # noqa: E402
import runner_flow_export as rfe  # noqa: E402
import value_target as vt  # noqa: E402


@pytest.fixture(scope="module")
def doc() -> dict[str, Any]:
    return rfe.build()


def _nodes(doc: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []

    def walk(n: dict[str, Any]) -> None:
        out.append(n)
        for c in n.get("body", []):
            walk(c)
        for b in n.get("branches", []):
            for c in b["body"]:
                walk(c)

    for s in doc["stacks"]:
        walk(s)
    return out


def test_the_outline_is_python_and_every_block_owns_its_lines(doc: dict[str, Any]) -> None:
    compile(doc["python"], "outline.py", "exec")
    n_lines = len(doc["python"].rstrip("\n").split("\n"))
    ids = [n["id"] for n in _nodes(doc)]
    assert len(ids) == len(set(ids))
    for n in _nodes(doc):
        a, b = n["lines"]
        h0, h1 = n["head"]
        assert 1 <= a <= h0 <= h1 <= b <= n_lines, n["id"]
    lines = doc["python"].split("\n")
    kill = next(n for n in _nodes(doc) if n["id"] == "killgap")
    assert "exp_kill(" in lines[kill["head"][0] - 1]  # dungeon@9.34: Batt's rule FIRST (11-12)
    k0, k1 = kill["lines"]
    assert any("kill_gapped(" in ln for ln in lines[k0 - 1 : k1])  # the gap rule, after it


def test_the_numbers_are_the_modules_own(doc: dict[str, Any]) -> None:
    p = doc["params"]
    assert p["KILL_GAP_S"]["value"] == dh.KILL_GAP_S
    assert p["KILL_GAP_HITS"]["value"] == dh.KILL_GAP_HITS
    assert p["LOOT_TRIM_HOVERS"]["value"] == dh.LOOT_TRIM_HOVERS
    assert p["vt.D0_PX"]["value"] == vt.D0_PX
    strat, conf = dh.STRATEGIES["P2"], dh.CHARS_CONF["rogue"]
    assert p["strategy.potion_below"]["value"] == strat["potion_below"]
    assert p["strategy.fly_rate"]["value"] == strat["fly_rate"]
    assert p["derived.potions"]["value"] == dh.potions_target(strat, conf)
    assert p["PATROL_START.x"]["value"] == dh.PATROL_START["xmas_dun02"][0][0]
    assert p["cmd.garm_confirm"]["value"] == 2  # the base's --garm-confirm 2
    # the Run button's cap (scripts/flow_run.py FLOWS; Batt 2026-11-13: until Stop, at most 2 h)
    import flow_run as fr

    assert p["cmd.minutes"]["value"] == float(fr.FLOWS["xmas_dun02_rogue"].minutes) == 120.0
    # the outline defines each constant with that value
    for pid, v in p.items():
        name = pid.split(".")[-1]
        if name.isupper() and not pid.startswith("PATROL_START"):
            assert f"\n{name} = {rfe.py_lit(v['value'])}  #" in doc["python"], name


def test_the_flags_are_runs_real_flags_with_their_help(doc: dict[str, Any]) -> None:
    out = io.StringIO()
    argv = sys.argv
    sys.argv = ["dungeon_hunt.py", "run", "--help"]
    try:
        with contextlib.redirect_stdout(out), pytest.raises(SystemExit):
            dh.main()
    finally:
        sys.argv = argv
    printed = out.getvalue()
    for f, fl in doc["flags"].items():
        assert f in printed, f"{f} is not a flag of dungeon_hunt.py run"
        assert fl["base"] == (f in rfe.BASE_COMMAND)
    assert doc["flags"]["--kill-gap"]["help"].startswith("dungeon@9.13c")
    assert doc["flags"]["--value-target"]["value"] is True
    # every block's flags are in the commands, and its code symbols exist
    for n in _nodes(doc):
        assert set(n["flags"]) <= set(doc["flags"]), n["id"]


def test_an_unknown_flag_or_symbol_fails_the_export() -> None:
    flags = rfe.run_flags(dh, ROOT / "scripts" / "dungeon_hunt.py")
    with pytest.raises(SystemExit, match="not a flag"):
        rfe.parse_command(["--no-such-flag"], flags)
    b = rfe.Builder({}, {}, set(), {"run"})
    with pytest.raises(SystemExit, match="not in the code"):
        b.emit(rfe.step("x", rfe.S_SETUP, "words", ["pass"], "why", code=["no_such_function"]), 0)
    with pytest.raises(SystemExit, match="unknown number"):
        b.emit(rfe.step("y", rfe.S_SETUP, "{NO_SUCH}", ["pass"], "why"), 0)


def test_no_gpl_derived_value_is_exported(doc: dict[str, Any]) -> None:
    """The species' worth (econ_model from rAthena's drops) is read by the runner at run time from
    data/econ/maps.json and never written into the committed description."""
    assert "SPECIES_VALUES = {}" in doc["python"]
    assert not any("species" in pid for pid in doc["params"])
    assert all("maps.json" not in p["source"] for p in doc["params"].values())
    text = json.dumps(doc)
    assert "sell_oc" not in text and 'maps.json"' not in text
