"""The SETTING BLOCKS (docs/planning/live-blocks.md section 12; Batt 2026-11-14 ~15:2x: "there
should be no runner [page] ... make them ALL blocks, no hardcoding like this"): poring_flow.settings
(the registry), its project variables, the name rule (the map node's > Global's > the default),
the Python view's spelling and round trip, the lint's words, the browser's copy."""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path
from typing import Any

from poring_flow import functions
from poring_flow import project as P
from poring_flow import pyproject as V
from poring_flow import settings as st
from poring_flow.lint import settings as ls

sys.path.insert(0, str(Path(__file__).parent))
from project_kit import REPO, XMAS, lit, session, xmas  # noqa: E402

GEN = REPO / "services/frontend/src/lib/flow/settings.gen.ts"


def build(d: dict[str, Any]) -> P.Project:
    return P.validate(d)


def node(d: dict[str, Any], nid: str) -> dict[str, Any]:
    return next(n for n in d["nodes"] if n["id"] == nid)


def tab_of(n: dict[str, Any], name: str) -> dict[str, Any]:
    t = next((t for t in n["tabs"] if t["name"] == name), None)
    if t is None:
        t = {"name": name, "main": None, "defs": [], "vars": {}}
        n["tabs"].append(t)
    return t


def put(d: dict[str, Any], nid: str, var: str, value: Any, tab: str | None = None) -> None:
    f = st.BY_VAR.get(var)
    tab_of(node(d, nid), tab or (f.group if f else "misc"))["vars"][var] = lit(value)


def rules(p: P.Project, *names: str) -> list[tuple[str, str, str]]:
    _c, found = P.project_lint(p)
    return [(f.severity, f.where.path, f.text) for f in found if f.rule in names]


def test_the_browsers_copy_is_the_registry() -> None:
    """lib/flow/settings.gen.ts is typescript_module's text (regenerate: scripts/gen_protocol.sh,
    or python -c "from poring_flow import settings, functions;
    print(settings.typescript_module(functions.RUNNER_MAPS), end='')" > that file)."""
    assert GEN.read_text() == st.typescript_module(functions.RUNNER_MAPS)
    reg = st.registry()
    assert reg["tabs"] == list(st.TABS) == [g for g, _, _ in st.GROUPS if g != "keys"]
    assert {f["name"] for f in reg["fields"] if f["block"]} == {f.name for f in st.BLOCKS}
    assert all(f["default"] == st.DEFAULTS[f["name"]] for f in reg["fields"])


def test_the_one_box_holds_every_setting_block_at_its_default_in_its_groups_tab() -> None:
    p = P.from_json(XMAS.read_text())
    (x,) = p.nodes
    got = {k: (t.name, v.value) for t in x.tabs for k, v in t.vars.items()}
    assert got == {f.var: (f.group, f.default) for f in st.BLOCKS}
    assert len(got) == 121 and not any(f.var in got for f in st.FIELDS if not f.block)
    # the same rule as the browser's withSettingTabs: the box before plus the setting tabs
    before = xmas()
    for t in node(before, "xmas_dun02")["tabs"]:
        t["vars"] = {}
    before["nodes"][0]["tabs"] = [t for t in before["nodes"][0]["tabs"]
                                  if t["name"] in ("main", "keys", "survival", "knife", "exits",
                                                   "monsters")]  # fmt: skip
    before["nodes"][0]["tabs"] = st.with_setting_tabs(before["nodes"][0]["tabs"])
    assert build(before) == p
    # and it lints without an error; every info names a setting the box does not use
    errs = [f for f in P.project_lint(p)[1] if f.severity == "error"]
    assert errs == []


def test_the_name_rule_the_maps_own_over_globals_over_the_default() -> None:
    d = session()  # login -> character -> xmas_dun02 (a hunt core) -> geffen, a Global
    put(d, "global", "potion_below", 0.3)
    put(d, "global", "LOOT_TRIM_HOVERS", 12)
    put(d, "xmas_dun02", "potion_below", 0.5)
    p = build(d)
    nv = ls.node_values(p, "xmas_dun02")
    assert (nv.vals["potion_below"], nv.src["potion_below"]) == (0.5, "xmas_dun02/survival")
    assert (nv.vals["LOOT_TRIM_HOVERS"], nv.src["LOOT_TRIM_HOVERS"]) == (12, "global/loot")
    assert (nv.vals["fly_below"], nv.src["fly_below"]) == (st.DEFAULTS["fly_below"], "default")
    # the Python view says the map's block replaces Global's (the project model's override line)
    by = {f.path: f.text for f in V.print_files(p)}
    assert "# overrides Global's potion_below (tab survival)\npotion_below = 0.5  # heal at HP " \
           "under (50 %)\n" in by["xmas_dun02/survival.py"]  # fmt: skip
    # a deleted block falls back: the map's -> Global's; Global's too -> the default
    node(d, "xmas_dun02")["tabs"] = [t for t in node(d, "xmas_dun02")["tabs"]
                                     if t["name"] != "survival"]  # fmt: skip
    assert ls.node_values(build(d), "xmas_dun02").vals["potion_below"] == 0.3
    tab_of(node(d, "global"), "survival")["vars"].pop("potion_below")
    nv = ls.node_values(build(d), "xmas_dun02")
    assert (nv.vals["potion_below"], nv.src["potion_below"]) == (0.4, "default")
    # the dict reader (the Run helper's, the player's checked file) agrees with the models'
    assert st.node_values(st.doc_levels(d, "xmas_dun02")) == ls.node_values(build(d), "xmas_dun02")


def test_the_setting_blocks_round_trip_through_the_python_view() -> None:
    d = session()
    for var, v in (("potion_below", 0.45), ("knife_swap", False), ("steal_cue", "both"),
                   ("respawn_confirm_at", "none"), ("D0_PX", 300), ("loot_step", "v1"),
                   ("respawn_on_death", True), ("LOOT_MAX_S", 30.0)):  # fmt: skip
        put(d, "global", var, v)
    put(d, "xmas_dun02", "knife_swap", True)
    p = build(d)
    files = {f.path: f.text for f in V.print_files(p)}
    assert V.parse_files(files) == p
    g = files["global/knife.py"]
    assert "\nknife_swap = False  # Batt's Knife swap (on / off)\n" in g
    assert '\nsteal_cue = "both"  # the steal cue (popup / both)\n' in g
    assert '\nrespawn_confirm_at = "none"  # then confirm (OK) at ("X,Y" in the game picture or ' \
           '"none")\n' in files["global/respawn.py"]  # fmt: skip
    assert "\nLOOT_MAX_S = 30.0  # a loot step at most (s)\n" in files["global/loot.py"]
    # a comment is not the value: the parser reads the assignment, the comment is the words
    loot = files["global/loot.py"]
    files["global/loot.py"] = loot.replace("LOOT_MAX_S = 30.0", "LOOT_MAX_S = 40.0")
    back = V.parse_files(files)
    gl = next(n for n in back.nodes if n.id == "global")
    assert next(t for t in gl.tabs if t.name == "loot").vars["LOOT_MAX_S"].value == 40.0


def test_the_lint_says_each_setting_problem_in_words() -> None:
    d = xmas()
    put(d, "xmas_dun02", "knife_hp_min", 0.95)  # out of range
    put(d, "xmas_dun02", "hud", "yes")  # the wrong kind
    put(d, "xmas_dun02", "potion_bellow", 0.3, tab="survival")  # a typo: a warning
    put(d, "xmas_dun02", "Knife_Swap", True, tab="knife")  # another case: a warning
    put(d, "xmas_dun02", "my_counter", 3, tab="misc")  # an ordinary variable: nothing
    put(d, "xmas_dun02", "heal_key", "F2", tab="keys")  # a hotbar key: not read
    got = rules(build(d), "settings")
    assert ("error", "xmas_dun02/knife/knife_hp_min", "knife_hp_min: or at once under HP: 95 % is "
            "not from 20 % to 90 %") in got  # fmt: skip
    assert ("error", "xmas_dun02/loop/hud", "hud: show the boxes on the console's HUD (display "
            "only): 'yes' is not on or off (True / False)") in got  # fmt: skip
    assert ("warning", "xmas_dun02/survival/potion_bellow", "potion_bellow is not a setting: did "
            "you mean potion_below (heal at HP under)? As written it is an ordinary variable, and "
            "the hunt core does not read it") in got  # fmt: skip
    assert any(w == "xmas_dun02/knife/Knife_Swap" and "did you mean knife_swap" in t
               for _s, w, t in got)  # fmt: skip
    assert not any("my_counter" in w for _s, w, _t in got)
    assert any(s == "warning" and w == "xmas_dun02/keys/heal_key" and "hotbar keys from the "
               "functions" in t for s, w, t in got)  # fmt: skip
    # Run refuses it: a setting error is a lint error
    assert sum(1 for s, _w, _t in got if s == "error") == 2


def test_the_clash_rule_is_an_error_and_unused_settings_are_info() -> None:
    d = xmas()
    put(d, "xmas_dun02", "hud_fast", 0.5)
    put(d, "xmas_dun02", "BOX_EVERY_S", 0.5)
    put(d, "xmas_dun02", "knife_swap", False)
    p = build(d)
    (clash,) = rules(p, "settings_clash")
    assert clash[:2] == ("error", "xmas_dun02") and "faster than the detector" in clash[2]
    info = {w: t for s, w, t in rules(p, "settings_use") if s == "info"}
    assert "is not in use while Batt's Knife swap (knife_swap) is off" in info[
        "xmas_dun02/knife/knife_max_s"]  # fmt: skip
    # the box replaces the runner's potion with its drink event (live.takeovers)
    assert info["xmas_dun02/survival/potion_below"].startswith(
        "potion_below (heal at HP under) is not used in a Run of this box: drink plays the "
        "runner's potion on HP instead")  # fmt: skip
    # the one box as shipped: no clash, the infos only
    assert rules(P.from_json(XMAS.read_text()), "settings_clash", "settings") == []


def test_settings_on_a_node_without_a_hunt_core_are_said_not_read() -> None:
    d = json.loads((REPO / "services/frontend/src/lib/flow/fixtures/project_sample.json")
                   .read_text())  # fmt: skip
    put(d, "field", "potion_below", 0.3)
    got = rules(build(d), "settings_use")
    assert ("info", "field", "field's settings are not read: only hunt with the runner "
            "(dungeon_hunt) reads them, and this node's main has none") in got  # fmt: skip
    assert rules(build(copy.deepcopy(d)), "settings", "settings_clash") == []


def test_a_setting_variable_is_an_ordinary_variable_to_the_blocks() -> None:
    """A setting is a project variable like any other: a block may read it (functions like real
    Python); its name is never a catalogue name, a Python keyword or a builtin."""
    from poring_flow.catalogue import catalogue

    names = catalogue().names()
    assert not {f.var for f in st.FIELDS} & set(names)
    d = xmas()
    keys = node(d, "xmas_dun02")["tabs"][1]
    keys["defs"].append({"name": "show_floor", "params": [], "varargs": None, "kwargs": None,
                         "body": [{"kind": "set", "var": "floor",
                                   "value": {"kind": "var", "name": "knife_hp_min"}}],
                         "on": None})  # fmt: skip
    keys["vars"]["floor"] = lit(0.0)
    c, found = P.project_lint(build(d))
    assert [f.message for f in found if f.severity == "error"] == []
    assert c.flow is not None


def test_typo_of_finds_near_names_only() -> None:
    assert st.typo_of("potion_bellow") is st.BY_NAME["potion_below"]
    assert st.typo_of("KNIFE_SWAP") is st.BY_NAME["knife_swap"]
    assert st.typo_of("d0_px") is st.BY_NAME["vt.D0_PX"]
    for plain in ("x", "counter", "my_loot", "potion_below", "floor"):
        assert st.typo_of(plain) is None, plain


def test_every_kind_reads_back_the_value_it_shows() -> None:
    for f in st.BLOCKS:
        assert st.problem_of(f, f.default) is None
        assert st.norm(f, f.default) == f.default or f.kind in ("number", "share")
        assert st.comment(f, f.default).startswith(f"# {f.words}")
