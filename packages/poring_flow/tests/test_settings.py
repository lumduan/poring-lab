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


# matpilot round 20 #4a (the parent's decision, 2026-11-14): the five settings the box's own events
# and functions play in a Run hold no block in the box (project.ts BOX_PLAYS_THEM)
BOX_PLAYS_THEM = {"potion_below", "fly_below", "weight_home", "respawn_at", "respawn_confirm_at"}


def test_the_one_box_holds_every_setting_block_it_uses_at_its_default_in_its_groups_tab() -> None:
    from poring_flow import live

    p = P.from_json(XMAS.read_text())
    (x,) = p.nodes
    got = {k: (t.name, v.value) for t in x.tabs for k, v in t.vars.items()}
    assert got == {f.var: (f.group, f.default) for f in st.BLOCKS if f.name not in BOX_PLAYS_THEM}
    assert len(got) == 116 and not any(f.var in got for f in st.FIELDS if not f.block)
    # the five are exactly what the engine's takeovers say this box plays itself (live.takeovers)
    c = P.compile_project(p)
    assert c.flow is not None
    tk = live.takeovers(c.flow, "xmas_dun02")
    assert tk is not None
    assert {s for row in tk["takeovers"] for s in row["settings"]} == BOX_PLAYS_THEM
    ts = (REPO / "services/frontend/src/lib/flow/project.ts").read_text()
    assert ('export const BOX_PLAYS_THEM: readonly string[] = ["potion_below", "fly_below", '
            '"weight_home", "respawn_at", "respawn_confirm_at"];') in ts  # fmt: skip
    # the same rule as the browser's withSettingTabs: the box before plus the setting tabs
    before = xmas()
    for t in node(before, "xmas_dun02")["tabs"]:
        t["vars"] = {}
    before["nodes"][0]["tabs"] = [t for t in before["nodes"][0]["tabs"]
                                  if t["name"] in ("main", "keys", "survival", "knife", "exits",
                                                   "monsters")]  # fmt: skip
    before["nodes"][0]["tabs"] = st.with_setting_tabs(
        before["nodes"][0]["tabs"], only=lambda f: f.name not in BOX_PLAYS_THEM)  # fmt: skip
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
           "under (50 %) · not used here: the hp_low event plays it\n" in by[
               "xmas_dun02/survival.py"]  # fmt: skip
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
    assert '\nrespawn_confirm_at = "none"  # the OK button that confirms the respawn ("X,Y" in ' \
           'the game picture or "none")' in files["global/respawn.py"]  # fmt: skip
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
    assert ("error", "xmas_dun02/timing/hud", "hud: show the boxes on the console's HUD (display "
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
    # the one box as shipped: no clash, no setting error, no safety switch off; the two blocks it
    # holds that are not in use say so (their needs are off by default)
    shipped = P.from_json(XMAS.read_text())
    assert rules(shipped, "settings_clash", "settings", "settings_safety") == []
    c = P.compile_project(shipped)
    assert ls.notes(shipped, c) == {
        "xmas_dun02/fight/quick_drop_scaled": {"unused": "not used while quick_drop is off"},
        "xmas_dun02/aim/near_single_still": {"unused": "not used while near_single is off"},
    }
    assert sorted(w for _s, w, _t in rules(shipped, "settings_use")) == [
        "xmas_dun02/aim/near_single_still", "xmas_dun02/fight/quick_drop_scaled"]  # fmt: skip


def test_a_block_the_box_plays_itself_is_marked_not_used_here_by_lint_block_and_python() -> None:
    """matpilot round 20 #4a: a person ADDS potion_below to the box: the drink event plays it, so
    the block did nothing. The lint's info, the block's row (POST /flows/lint ``settings``) and the
    Python line's comment say it, from one computation (lint/settings.py notes)."""
    d = xmas()
    put(d, "xmas_dun02", "potion_below", 0.3)
    put(d, "xmas_dun02", "respawn_at", "600,400")
    p = build(d)
    info = {w: t for s, w, t in rules(p, "settings_use") if s == "info"}
    assert info["xmas_dun02/survival/potion_below"].startswith(
        "potion_below (heal at HP under) is not used in a Run of this box: drink plays the "
        "runner's potion on HP instead")  # fmt: skip
    notes = ls.notes(p, P.compile_project(p))
    assert notes["xmas_dun02/survival/potion_below"] == {
        "unused": "not used here: the drink event plays it"}  # fmt: skip
    assert notes["xmas_dun02/respawn/respawn_at"] == {
        "unused": "not used here: the respawn_button function plays it"}  # fmt: skip
    by = {f.path: f.text for f in V.print_files(p)}
    assert "\npotion_below = 0.3  # heal at HP under (30 %) · not used here: the drink event " \
           "plays it\n" in by["xmas_dun02/survival.py"]  # fmt: skip
    assert "\nquick_drop_scaled = False  # the quick drop's wait grows with the distance (on / " \
           "off) · not used while quick_drop is off\n" in by["xmas_dun02/fight.py"]  # fmt: skip
    # the lint document sends the same rows for the blocks to show
    doc = P.lint_doc(p, world=None, resolver=None)
    assert doc["settings"] == notes
    assert V.parse_files(by) == p  # a comment is no value: the round trip is exact


def test_a_safety_switch_off_is_a_warning_on_its_block_its_row_and_its_python_line() -> None:
    """matpilot round 20 #3: npc_guard off said nothing (only a setting that needs it got an
    info). Now a WARNING on the block (the chip and the /maps card count it), its warning as the
    block's own row and as the Python line's comment; its dependent setting is not in use."""
    d = xmas()
    put(d, "xmas_dun02", "npc_guard", False)
    p = build(d)
    got = rules(p, "settings_safety")
    want = (
        "npc_guard (no fight click near an NPC) is off: a strike near an NPC may open its "
        "dialog and stop the run"
    )
    assert got == [("warning", "xmas_dun02/safety/npc_guard", want)]
    c, found = P.project_lint(p)
    assert not [f for f in found if f.severity == "error"]  # a warning never blocks a Run
    notes = ls.notes(p, c)
    assert notes["xmas_dun02/safety/npc_guard"] == {
        "safety": "a strike near an NPC may open its dialog and stop the run"}  # fmt: skip
    assert notes["xmas_dun02/safety/NPC_NO_FIGHT"] == {"unused": "not used while npc_guard is off"}
    by = {f.path: f.text for f in V.print_files(p)}
    assert "\nnpc_guard = False  # no fight click near an NPC (on / off) · ⚠ off: a strike " \
           "near an NPC may open its dialog and stop the run\n" in by[
               "xmas_dun02/safety.py"]  # fmt: skip
    # garm_fly off: its own warning; alarm_fast then is not in use (no second warning), its
    # dependents' rows name the ROOT switch
    d2 = xmas()
    put(d2, "xmas_dun02", "garm_fly", False)
    p2 = build(d2)
    assert [w for _s, w, _t in rules(p2, "settings_safety")] == ["xmas_dun02/safety/garm_fly"]
    n2 = ls.notes(p2, P.compile_project(p2))
    assert n2["xmas_dun02/safety/alarm_solo"] == {"unused": "not used while garm_fly is off"}
    assert n2["xmas_dun02/safety/alarm_fast"] == {"unused": "not used while garm_fly is off"}
    # every safety switch is ON by default (a box at its defaults warns of none)
    assert all(f.default is True for f in st.BLOCKS if f.warn)
    assert {f.name for f in st.BLOCKS if f.warn} == {"respawn", "npc_guard", "garm_fly",
                                                       "alarm_fast"}  # fmt: skip
    assert not any(f.warn.startswith("off") for f in st.FIELDS)  # "off: off: ..." (round 20 #3)


def test_one_setting_on_two_tabs_of_a_node_is_refused_naming_both_tabs() -> None:
    """matpilot round 20 #5: does anything stop a SECOND block of a setting on ANOTHER tab of the
    same node? Yes: a node's tabs are one namespace, so the engine refuses the project naming both
    tabs (a run would otherwise take the first tab's silently), and so does the Python view's
    reader; the block editor refuses it on the block itself (blocks.ts, blocks.test.ts)."""
    import pytest

    d = xmas()
    put(d, "xmas_dun02", "D0_PX", 300, tab="loot")
    with pytest.raises(P.ProjectError) as e:
        build(d)
    assert e.value.messages == ["xmas_dun02/loot/D0_PX: D0_PX is defined twice on xmas_dun02: a "
                                "variable in tab aim and a variable in tab loot (a node's tabs are "
                                "one namespace)"]  # fmt: skip
    files = {f.path: f.text for f in V.print_files(P.from_json(XMAS.read_text()))}
    files["xmas_dun02/loot.py"] += "D0_PX = 300\n"
    with pytest.raises(Exception, match="D0_PX is defined twice on xmas_dun02: a variable in tab "
                       "aim and a variable in tab loot"):  # fmt: skip
        V.parse_files(files)
    # a Global and a map node each with their own: no error (the name rule, not a duplicate)
    s2 = session()
    put(s2, "global", "D0_PX", 300)
    put(s2, "xmas_dun02", "D0_PX", 200)
    assert [x for x in rules(build(s2), "settings") if x[0] == "error"] == []


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


def test_each_setting_names_its_subject_and_says_its_unit_right() -> None:
    """matpilot round 20 #4b/c: no block reads as a fragment ("... from 2 cells already"), "at"
    is not said twice, a value of 1 takes a singular unit, the screen reads "5 times a second"."""
    for f in st.FIELDS:
        assert not f.words.startswith(("...", "…")) and not f.words.endswith(("...", "…")), f.name
        # a point-or-none block's menu says "at" itself ("then confirm (OK) at at x 714")
        assert not (f.kind == "point_or_none" and f.words.endswith(" at")), f.name
    assert st.shown(st.BY_NAME["WALK_PICK_TOL"], 1) == "1 cell"
    assert st.shown(st.BY_NAME["WALK_PICK_TOL"], 2) == "2 cells"
    assert st.shown(st.BY_NAME["READ_HZ"], 5.0) == "5 times a second"
    assert st.shown(st.BY_NAME["READ_HZ"], 1.0) == "1 time a second"
    assert st.shown(st.BY_NAME["HP_DROP_PTS"], 2) == "2 % of max HP"
    assert st.comment(st.BY_NAME["NOENTRY_CARVE_R"], 1) == "# a no-entry cursor closes this " \
                                                           "radius (cell)"  # fmt: skip


def test_the_block_search_finds_every_setting_by_its_groups_words() -> None:
    """matpilot round 20 #5: "knife" found 3 of the 6 knife settings."""
    knife = [f.name for f in st.BLOCKS if "knife" in f.find]
    assert knife == [f.name for f in st.BLOCKS if f.group == "knife"]
    assert len(knife) == 6
    for f in st.BLOCKS:
        assert f.group in f.find and len(set(f.find)) == len(f.find), f.name
    assert {"garm"} <= set(st.BY_NAME["alarm_fast"].find)
    assert {"fly", "wing", "heal"} <= set(st.BY_NAME["fly_rate"].find)
    # "loop" names Control's loop block: no setting is found by it (round 20: the group is timing)
    assert not any("loop" in f.find for f in st.FIELDS)
    assert "loop" not in st.TABS and "timing" in st.TABS


def test_every_kind_reads_back_the_value_it_shows() -> None:
    for f in st.BLOCKS:
        assert st.problem_of(f, f.default) is None
        assert st.norm(f, f.default) == f.default or f.kind in ("number", "share")
        assert st.comment(f, f.default).startswith(f"# {f.words}")
