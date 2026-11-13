"""scripts/flow_config.py: every number and key a person may set (Batt 2026-11-13: "nothing is
fixed, we only put the defaults"; "a global config for every map's flow, a map's own on top";
"all of them") -- and the runner really uses each one."""

from __future__ import annotations

import ast
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts"))

import dungeon_hunt as dh  # noqa: E402
import flow_config as fc  # noqa: E402
import value_target as vt  # noqa: E402

MODS = {"dh": dh, "vt": vt}
SOURCES = {"dh": ROOT / "scripts" / "dungeon_hunt.py", "vt": ROOT / "scripts" / "value_target.py"}
TUNED = [f for f in fc.FIELDS if f.tune]


def _mod_attr(name: str) -> tuple[str, str]:
    key, _, attr = name.rpartition(".")
    return key or "dh", attr


def test_every_field_is_well_formed_and_its_group_exists() -> None:
    groups = {g for g, _, _ in fc.GROUPS}
    assert len(fc.BY_NAME) == len(fc.FIELDS)  # no name twice
    for f in fc.FIELDS:
        assert f.group in groups and f.kind in fc.KINDS and f.words, f.name
        if f.kind in ("share", "number", "int"):
            assert f.lo < f.hi and f.step > 0, f.name
    assert {f.group for f in fc.FIELDS} == groups  # no empty group


@pytest.mark.parametrize("f", TUNED, ids=lambda f: f.name)
def test_a_runner_number_exists_and_its_default_fits_its_range(f: fc.Field) -> None:
    key, attr = _mod_attr(f.name)
    v = getattr(MODS[key], attr)
    assert isinstance(v, (int, float)) and not isinstance(v, bool), f.name
    assert fc.problem_of(f, v) is None, (f.name, v)  # the runner's own value is a valid choice


@pytest.mark.parametrize("key", ["dh", "vt"])
def test_no_runner_number_is_bound_at_import(key: str) -> None:
    """The value --tune sets must be the value used: a constant copied into a default argument,
    another module constant or a class field at import would keep the old number SILENTLY."""
    names = {_mod_attr(f.name)[1] for f in TUNED if _mod_attr(f.name)[0] == key}
    tree = ast.parse(SOURCES[key].read_text())
    bad: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
            for d in [*node.args.defaults, *(x for x in node.args.kw_defaults if x is not None)]:
                bad += [f"{n.id}: a default of {getattr(node, 'name', 'lambda')} (line "
                        f"{node.lineno})" for n in ast.walk(d)
                        if isinstance(n, ast.Name) and n.id in names]  # fmt: skip
        if isinstance(node, ast.ClassDef):
            for st in node.body:
                if isinstance(st, (ast.Assign, ast.AnnAssign)) and st.value is not None:
                    bad += [f"{n.id}: a field of {node.name}" for n in ast.walk(st.value)
                            if isinstance(n, ast.Name) and n.id in names]  # fmt: skip
    for st in tree.body:  # module level: another constant computed from one at import
        if isinstance(st, (ast.Assign, ast.AnnAssign)) and st.value is not None:
            tgt = {t.id for t in (st.targets if isinstance(st, ast.Assign) else [st.target])
                   if isinstance(t, ast.Name)}  # fmt: skip
            bad += [f"{n.id}: copied into {sorted(tgt)} (line {st.lineno})"
                    for n in ast.walk(st.value)
                    if isinstance(n, ast.Name) and n.id in names and n.id not in tgt]  # fmt: skip
    assert bad == []
    # and no other script copies one with "from dungeon_hunt import NAME"
    for p in (ROOT / "scripts").glob("*.py"):
        t = ast.parse(p.read_text())
        for n in ast.walk(t):
            if isinstance(n, ast.ImportFrom) and n.module in ("dungeon_hunt", "value_target"):
                assert not {a.name for a in n.names} & names, p.name


def test_tune_sets_the_number_the_code_then_uses() -> None:
    vals, why = dh.tune_values(["KILL_GAP_HITS=2", "KILL_GAP_S=0.5", "vt.D0_PX=300",
                                "LOOT_TRIM_HOVERS=12"])  # fmt: skip
    assert why is None and vals["KILL_GAP_HITS"] == 2 and vals["vt.D0_PX"] == 300
    assert not dh.kill_gapped(2, 0.6)  # the defaults: 5 hits, 1.5 s
    before = vt.score(100.0, 100.0)
    prev = dh.tune_apply(vals, MODS)
    try:
        assert dh.KILL_GAP_HITS == 2 and isinstance(dh.KILL_GAP_HITS, int)
        assert dh.kill_gapped(2, 0.6)  # the person's 2 hits and 0.5 s, read at call time
        assert vt.score(100.0, 100.0) > before  # a larger D0_PX: a far box keeps more worth
        assert dh.LOOT_TRIM_HOVERS == 12
    finally:
        dh.tune_apply(prev, MODS)
    assert (dh.KILL_GAP_HITS, dh.KILL_GAP_S, vt.D0_PX) == (5, 1.5, 150.0)
    for bad, word in (("NOPE=1", "not a runner number"), ("fly_key=F2", "not a runner number"),
                      ("KILL_GAP_HITS=99", "is not from"), ("KILL_GAP_HITS=2.5", "whole number"),
                      ("KILL_GAP_S=abc", "not a number"), ("KILL_GAP_S", "not a runner number"),
                      ("STILL_PX=1.234", "a step of")):  # fmt: skip
        got, why = dh.tune_values([bad])
        assert got == {} and word in str(why), (bad, why)


def test_every_number_the_page_shows_is_a_setting_or_says_why_not() -> None:
    """Batt: "nothing is fixed". Every runner constant /flows shows is a field here, or one of
    these, each settable some other way (or not a number a person chooses)."""
    not_fields = {
        "HOME_KEY": "the character's default Butterfly Wing key: home_key is the setting",
        "bs.BARE_MAX_S": "the default of knife_max_s (--knife-max-s)",
        "bs.BARE_HP_MIN": "the default of knife_hp_min (--knife-hp-min)",
        "bs.EQUIP_KEY": "the default of dagger_key (--dagger-key)",
    }
    gen = ROOT / "services" / "frontend" / "src" / "lib" / "flow" / "runners"
    src = (gen / "xmas_dun02_rogue.gen.ts").read_text()
    doc = json.loads(src[src.index("= {") + 2 : src.rindex("};") + 1])
    for pid in doc["params"]:
        if pid.startswith(("cmd.", "char.", "derived.", "PATROL_START", "strategy.")):
            continue  # the command's own values, the character, derived, the start cells
        assert pid in fc.BY_NAME or pid in not_fields, f"{pid} is fixed: make it a field"


def test_the_maps_own_value_first_then_every_maps_then_the_default() -> None:
    d = {"fly_key": "F8", "potion_below": 0.4}
    cfg = {"global": {"potion_below": 0.3, "LOOT_TRIM_HOVERS": 12},
           "maps": {"xmas_dun02": {"potion_below": 0.5}}}  # fmt: skip
    vals, src = fc.effective(d, cfg, "xmas_dun02")
    assert vals == {"fly_key": "F8", "potion_below": 0.5, "LOOT_TRIM_HOVERS": 12}
    assert src == {"fly_key": "default", "potion_below": "map", "LOOT_TRIM_HOVERS": "global"}
    assert fc.effective(d, cfg, "prt_fild08")[0]["potion_below"] == 0.3
    assert fc.effective(d, {}, "xmas_dun02") == (d, {"fly_key": "default", "potion_below": "default"})


def test_keys_clash_and_the_flags() -> None:
    ok = {"heal_key": "F1", "fly_key": "F8", "home_key": "F9", "knife_key": "F4", "dagger_key": "F5"}
    assert fc.clash(ok) is None
    assert "the Knife and the dagger are both on F4" in str(fc.clash({**ok, "dagger_key": "F4"}))
    vals = {**ok, "weight_home": 0.5, "knife_max_s": 8.0, "fly_rate": 150, "LOOT_TRIM_HOVERS": 12,
            "vt.D0_PX": 200, "respawn_confirm_at": "none"}  # fmt: skip
    a = fc.argv(vals)
    assert a[:2] == ["--heal-key", "F1"] and a[a.index("--weight-home") + 1] == "0.50"
    assert a[a.index("--knife-max-s") + 1] == "8" and a[a.index("--fly-rate") + 1] == "150"
    assert ["--tune", "LOOT_TRIM_HOVERS=12"] == a[a.index("LOOT_TRIM_HOVERS=12") - 1 : a.index(
        "LOOT_TRIM_HOVERS=12") + 1]  # fmt: skip
    assert "vt.D0_PX=200" in a and a[a.index("--respawn-confirm-at") + 1] == "none"
    # every flag a field names is a flag of the runner's
    src = SOURCES["dh"].read_text()
    for f in fc.FIELDS:
        assert f'"{f.flag or "--tune"}"' in src, f.name


def test_a_level_is_put_by_group_and_checked(tmp_path: Path) -> None:
    cfg = {"global": {"potion_below": 0.3}, "maps": {}}
    got = fc.put_level(cfg, "map", "xmas_dun02", "loot", {"LOOT_TRIM_HOVERS": 12})
    assert isinstance(got, dict) and got["maps"]["xmas_dun02"] == {"LOOT_TRIM_HOVERS": 12}
    assert got["global"] == {"potion_below": 0.3}  # another group, untouched
    cleared = fc.put_level(got, "map", "xmas_dun02", "loot", None)
    assert isinstance(cleared, dict) and cleared["maps"] == {}
    assert "not in the group" in str(fc.put_level(cfg, "global", None, "loot", {"potion_below": 0.3}))
    assert "unknown group" in str(fc.put_level(cfg, "global", None, "nope", {}))
    assert "map's name" in str(fc.put_level(cfg, "map", None, "loot", {}))
    assert "is not from" in str(fc.put_level(cfg, "global", None, "loot", {"LOOT_TRIM_HOVERS": 99}))
    # the file: config.json, else 8e3ca2df's survival.json (v1, the same shape)
    assert fc.read_config(tmp_path) == {"global": {}, "maps": {}}
    (tmp_path / "survival.json").write_text(json.dumps({"v": 1, "global": {"potion_below": 0.35}}))
    assert fc.read_config(tmp_path) == {"global": {"potion_below": 0.35}, "maps": {}}
    (tmp_path / "config.json").write_text(json.dumps({"v": 2, "maps": {"xmas_dun02": {
        "LOOT_MAX_S": 30}}}))  # fmt: skip
    assert fc.read_config(tmp_path) == {"global": {}, "maps": {"xmas_dun02": {"LOOT_MAX_S": 30.0}}}
    for bad, word in (("{", "not valid JSON"), (json.dumps({"v": 3}), "not version"),
                      (json.dumps({"v": 2, "global": {"x": 1}}), "unknown setting"),
                      (json.dumps({"v": 2, "maps": {"../a": {}}}), "not a map name")):  # fmt: skip
        (tmp_path / "config.json").write_text(bad)
        assert word in str(fc.read_config(tmp_path)), bad
