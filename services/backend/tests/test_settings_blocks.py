"""THE RUN READS THE SETTING BLOCKS (docs/planning/live-blocks.md section 12; Batt 2026-11-14
~15:2x: "make them ALL blocks, no hardcoding like this"): scripts/flow_play.py's prepare takes a
hunt core's runner settings from the project's blocks (the map node's > Global's > the default),
the node's keys over them -- and every box that ran before gives exactly the runner argv it gave
then (the frozen A/B arms byte for byte, the one box with its blocks at their defaults)."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts"))

import flow_config as fc  # noqa: E402
import flow_play as fp  # noqa: E402

FIX = ROOT / "services/frontend/src/lib/flow/fixtures"
NODE = "xmas_dun02"
# The runner argv every box gave on main 2d19014d (2026-11-14, before the settings were blocks),
# computed with THAT commit's flow_config / flow_run / flow_play and an empty settings file: the
# one box of then and the three frozen arms gave this same list (label "L", stop file "/S").
TODAY = [
    "--char", "rogue", "--map", "xmas_dun02", "--strategy", "P2", "--seed", "20261105",
    "--label", "L", "--stop-file", "/S", "--player-mode", "--heal-key", "F1", "--fly-key", "F8",
    "--player-home-key", "F9", "--steal-opener", "F4", "--dagger-key", "F5", "--knife-max-s", "8",
    "--knife-hp-min", "0.50", "--potion-below", "0.40", "--fly-below", "0.20", "--fly-rate", "150",
    "--fly-rate-below", "0.50", "--weight-home", "0.50", "--respawn-at", "645,481",
    "--respawn-confirm-at", "714,405", "--walk-ahead", "7", "--walk-every", "1.2", "--box-every",
    "1", "--bare-steal", "--bare-ready", "--steal-cue", "popup", "--swap-gap", "--respawn",
    "--minutes", "120", "--engage-screen", "--reach-check", "--miss-cue", "--late-confirm",
    "--exp-first", "--kill-gap", "--quiet-scan", "--value-target", "--box-strike", "--box-now",
    "--self-recheck", "--still-strike", "--still-target", "--lead-press", "--far-single",
    "--far-approach", "--box-ignore", "2", "--loot", "trim", "--loot-items", "xmas02fi5",
    "--loot-memory", "--loot-first", "--search", "patrol", "--explore", "--walk-pick",
    "--walk-pick-step", "--walk-trust", "--npc-guard", "--garm-fly", "--garm-confirm", "2",
    "--alarm-fast", "--alarm-solo", "0.70", "--box-detector", "gpu", "--hud", "--hud-fast", "0.2",
]  # fmt: skip
# the frozen A/B arms (stage2_ab B2, stage3_ab B3, stage4_ab B4, stage5_ab B4): byte-identical
FROZEN = {
    "project_xmas_dun02_stage2.json": "1d1889f486282302fcd2441dfa7f673a"
    "d5af3c8ff89b25b897059972a20160cc",
    "project_xmas_dun02_stage3.json": "ffab1584713d0a3e9dd606b7ede74333"
    "950691808d109f02edec6f279ee463d6",
    "project_xmas_dun02_stage4.json": "bc2641067396ead53c970017f427b056"
    "30914430229d034903ffd07a2d4c83e4",
}  # fmt: skip


def hunt_argv(text: str) -> list[str] | str:
    prep = fp.prepare(text, NODE, 7200)
    if isinstance(prep, str):
        return prep
    return prep.runners[NODE].argv("L", Path("/S"), None)


def one_box() -> dict[str, Any]:
    return dict(json.loads((FIX / "project_xmas_dun02.json").read_text()))


def set_block(d: dict[str, Any], var: str, value: Any, node: str = NODE) -> None:
    n = next(x for x in d["nodes"] if x["id"] == node)
    f = fc.BY_VAR[var]
    t = next((t for t in n["tabs"] if t["name"] == f.group), None)
    if t is None:
        t = {"name": f.group, "main": None, "defs": [], "vars": {}}
        n["tabs"].append(t)
    t["vars"][var] = {"kind": "lit", "value": value}


@pytest.mark.parametrize("name", sorted(FROZEN))
def test_a_frozen_arm_is_byte_identical_and_plays_todays_argv(name: str) -> None:
    raw = (FIX / name).read_bytes()
    assert hashlib.sha256(raw).hexdigest() == FROZEN[name]
    assert '"vars":{}' in raw.decode() and not any(
        f'"{f.var}":' in raw.decode() for f in fc.BLOCKS if f.var not in ("loot",))  # fmt: skip
    assert hunt_argv(raw.decode()) == TODAY


# matpilot round 20 #4a (the parent's decision, 2026-11-14): the box holds no block of the five
# settings its own events and functions play (drink, fly_away, bag_full, respawn_button, respawn_ok)
BOX_PLAYS_THEM = {"potion_below", "fly_below", "weight_home", "respawn_at", "respawn_confirm_at"}


def test_the_one_box_with_its_blocks_at_their_defaults_plays_todays_argv() -> None:
    d = one_box()
    held = {k for t in d["nodes"][0]["tabs"] for k in t["vars"]}
    assert held == {f.var for f in fc.BLOCKS if f.name not in BOX_PLAYS_THEM}
    assert len(held) == len(fc.BLOCKS) - 5 == 116
    assert hunt_argv(json.dumps(d)) == TODAY


def test_a_setting_the_box_plays_itself_is_unused_by_the_runner_with_or_without_a_block() -> None:
    """The five left the box (round 20 #4a) and the argv is TODAY's: each is still passed, at its
    default (the runner's own flag), and NOT USED -- the box plays it, so the runner's own handler
    for it is off (its plays, which the live player hands to run()). A block a person adds with
    another value changes only that flag's value, never what plays (the lint marks the block "not
    used here")."""
    prep = fp.prepare(json.dumps(one_box()), NODE, 7200)
    assert not isinstance(prep, str), prep
    r = prep.runners[NODE]
    assert {"potion", "fly_hp", "weight_home", "respawn"} <= set(r.plays)
    import poring_flow.live as live

    played = {s for p in r.plays for s in live.PLAY_SETTINGS.get(p, ())}
    assert played == BOX_PLAYS_THEM
    for k in BOX_PLAYS_THEM:
        assert r.vals[k] == fc.DEFAULTS[k], k  # the default stands in: no block holds it
    d = one_box()
    set_block(d, "potion_below", 0.3)
    set_block(d, "respawn_at", "600,400")
    a = hunt_argv(json.dumps(d))
    assert isinstance(a, list)
    changed = [(x, y) for x, y in zip(a, TODAY, strict=True) if x != y]
    assert changed == [("0.30", "0.40"), ("600,400", "645,481")]  # the two values, nothing else
    p2 = fp.prepare(json.dumps(d), NODE, 7200)
    assert not isinstance(p2, str) and set(p2.runners[NODE].plays) == set(r.plays)


def test_a_block_a_person_changes_is_what_the_runner_gets() -> None:
    d = one_box()
    set_block(d, "knife_hp_min", 0.6)
    set_block(d, "LOOT_MAX_S", 30.0)
    set_block(d, "LOOT_TRIM_HOVERS", 12)  # needs the trim loot: switched below, so not passed
    set_block(d, "near_single", True)
    set_block(d, "loot_step", "v1")
    a = hunt_argv(json.dumps(d))
    assert isinstance(a, list)
    assert a[a.index("--knife-hp-min") + 1] == "0.60"
    assert a[a.index("LOOT_MAX_S=30") - 1] == "--tune" and "LOOT_TRIM_HOVERS=12" not in a
    assert "--near-single" in a and a[a.index("--loot") + 1] == "v1"
    assert "--loot-items" not in a  # its need (the trim loot) is gone: not passed
    # a technique switched off takes its settings with it, as the runner needs
    d2 = one_box()
    set_block(d2, "knife_swap", False)
    b = hunt_argv(json.dumps(d2))
    assert isinstance(b, list) and "--bare-steal" not in b and "--knife-max-s" not in b


def test_the_maps_block_over_globals_over_the_default_and_a_deleted_one_falls_back() -> None:
    d = one_box()
    set_block(d, "potion_below", 0.4)  # the map's own blocks (a person adds them back)
    set_block(d, "fly_below", 0.2)
    d["nodes"].append({"id": "global", "kind": "global", "pos": {"x": 0, "y": 200}, "tabs": []})
    set_block(d, "potion_below", 0.3, node="global")
    set_block(d, "fly_below", 0.25, node="global")
    a = hunt_argv(json.dumps(d))
    assert isinstance(a, list)
    assert a[a.index("--potion-below") + 1] == "0.40"  # the map's own block (its default) wins
    # the map's fly_below deleted: Global's applies there
    for t in d["nodes"][0]["tabs"]:
        t["vars"].pop("fly_below", None)
    b = hunt_argv(json.dumps(d))
    assert isinstance(b, list) and b[b.index("--fly-below") + 1] == "0.25"
    # Global's deleted too: the default
    for t in d["nodes"][1]["tabs"]:
        t["vars"].pop("fly_below", None)
    c = hunt_argv(json.dumps(d))
    assert isinstance(c, list) and c[c.index("--fly-below") + 1] == "0.20"


def test_a_block_the_runner_cannot_take_refuses_before_any_input() -> None:
    for var, v, words in (("knife_hp_min", 0.95, "is not from 20 % to 90 %"),
                          ("hud_fast", 1.5, "is not from"),
                          ("knife_swap", "on", "is not on or off")):  # fmt: skip
        d = one_box()
        set_block(d, var, v)
        got = hunt_argv(json.dumps(d))
        assert isinstance(got, str) and "refused before any input" in got and words in got, got
    d = one_box()
    set_block(d, "hud_fast", 0.5)
    set_block(d, "BOX_EVERY_S", 0.5)
    got = hunt_argv(json.dumps(d))
    assert isinstance(got, str) and "faster than the detector" in got


def test_an_ab_series_plans_and_refuses_two_boxes_whose_settings_differ(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import stage5_ab as s5

    doc = s5.plan_doc("s", 1, 20, "alternate", tmp_path / "s")
    assert isinstance(doc, dict), doc
    assert doc["vals"]["minutes"] == 20 and doc["vals"]["knife_hp_min"] == 0.5
    d = one_box()
    set_block(d, "knife_hp_min", 0.6)
    other = tmp_path / "b5.json"
    other.write_text(json.dumps(d))
    monkeypatch.setitem(s5.PROJECTS, "B5", other)
    got = s5.plan_doc("s", 1, 20, "alternate", tmp_path / "s")
    assert isinstance(got, str) and "runner settings differ: knife_hp_min" in got
