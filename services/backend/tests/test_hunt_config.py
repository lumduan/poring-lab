"""hunt_config + params_export (the blocks plan, B1 + B3, 2026-10-21): every PARAMS key classified,
every version exported and resolved back EXACTLY (keys, order, values, types), the adopted base,
the deny-list, the committed configs current, the hunt block's choices real, the session-file
parity of the manifest's params, and the decision code reading only the resolved config."""

from __future__ import annotations

import json
import sys
import types
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts"))
import hunt_config as hcfg  # noqa: E402
import hunt_flow as hf  # noqa: E402
import params_export as pe  # noqa: E402

P = hf.PARAMS


def all_keys() -> dict[str, int]:
    first: dict[str, int] = {}
    for v in sorted(P):
        for k in P[v]:
            first.setdefault(k, v)
    return first


# --- B1: the classes ------------------------------------------------------------------------------
def test_every_key_of_every_version_is_classified() -> None:
    keys = all_keys()
    assert [k for k in keys if hcfg.classify(k) is None] == []
    for v in sorted(P):  # export refuses an unclassified key, so this is the same claim per version
        assert hcfg.split(P[v], v)
    # the plan's count (209 at writing, v51) and the adopted base's (v52: + map_zones)
    assert len(P[51]) == 209 and len(P[52]) == 210
    assert sum(hcfg.classify(k) is not None for k in P[52]) == 210


EXPECTED = {  # the plan's section 2 tables, key by key where it names them
    "gate": ["walk_guard", "guard_gm_px", "risk_gate", "gate_near_gm_px", "name_tag", "tag_wait_s",
             "species_skip", "tag_follow", "cursor_sword", "cursor_sword_wait_s", "loot_unit_px",
             "loot_pink_r", "loot_corpse", "ptr_rest_two", "ptr_rest_ui", "guard_ui_mask",
             "guard_ptr_mask", "track_clear"],
    "safety": ["bg_check", "freeze_guard", "false_dead_fix"],
    "reader": ["frame_cells", "track_near", "focus", "focus_lead_s", "gate_frames_s",
               "jump_reanchor", "loot_refix", "loot_refix_cells", "ui_layout", "dead_end_hyst_s",
               "burst", "loot_death"],
    "constant": ["continuous", "walk_every_s", "ahead", "ahead_order", "click_lead_s",
                 "pipelined", "queue_depth", "strike_cells", "strike_cells_standing", "zone",
                 "zone_radius", "burst_interval_s", "reclick_s", "dead_min_s", "send_gap_s"],
    "recovery": ["stall_s", "unstall_s", "stuck_window_s", "stuck_escape_min"],
    "experiment": ["loot_gm_one_pass_ab", "loot_gm_ab", "exp_dead_ab", "send_gap_ab",
                   "send_gap_ab_min", "cursor_sword_ab"],
    "record": ["shadow_cursor", "species_shadow", "dead_probe", "publish_route"],
    "retired": ["belief", "belief_pd", "fast_dead", "loot_race", "loot_icons", "looter_chain",
                "species_own", "loot_retry", "heading_age", "steer_tail", "steer_guard_box_px",
                "strike_cells_walking", "exp_wait_s", "loot_hand", "loot_hand_wait_s"],
    "map_node": ["map_zones"],
}  # fmt: skip
EXPECTED_BLOCK = {
    "strike": ["abc", "abc_arm"],
    "engage_on_the_way": ["opportunistic", "opp_cells", "preempt_hyst", "retarget",
                          "retarget_margin"],
    "dead": ["exp_dead", "exp_keep", "exp_keep_gone_s", "exp_loot_delay_s"],
    "loot": ["loot", "loot_gm", "loot_gm_one_pass", "loot_gm_stand_s", "loot_gm_burst_gap_s",
             "loot_hand_still_s", "loot_fixed", "loot_interval_s"],
    "search": ["heading_search", "heading_min_run", "heading_cov", "cov_recent_s"],
}  # fmt: skip


def test_the_classes_follow_the_plans_tables() -> None:
    for cls, keys in EXPECTED.items():
        for k in keys:
            got = hcfg.classify(k)
            assert got is not None and got.cls == cls, (k, got)
    for param, keys in EXPECTED_BLOCK.items():
        for k in keys:
            got = hcfg.classify(k)
            assert got is not None and got.cls in hcfg.BLOCK and got.param == param, (k, got)


def test_a_new_key_takes_its_familys_class_and_an_unknown_one_is_refused() -> None:
    """D3: PARAMS stay open; classification is by pattern, never a frozen list."""
    fam = {"loot_fast_new_s": ("rule", "loot"), "loot_gm_new": ("rule", "loot"),
           "heading_new_p": ("rule", "search"), "guard_new_px": ("gate", None),
           "stuck_new_s": ("recovery", None), "anything_ab": ("experiment", None)}  # fmt: skip
    for k, (cls, param) in fam.items():
        got = hcfg.classify(k)
        assert got is not None and (got.cls, got.param) == (cls, param), k
    params = {**P, 99: {**P[52], "zzz_new_thing": 1.0}}
    with pytest.raises(hcfg.ConfigError, match=r"unclassified key\(s\) \['zzz_new_thing'\]"):
        hcfg.export(params, 99)
    # an unrelated version's unclassified key never blocks another version's export
    assert hcfg.same(hcfg.resolve(hcfg.export(params, 52)), P[52])


def test_every_version_resolves_back_exactly() -> None:
    for v in sorted(P):
        out = hcfg.params_for(P, v)
        assert hcfg.same(out, P[v]) and out == P[v] and list(out) == list(P[v]), v
        assert out is not P[v]
        for k, val in P[v].items():
            assert type(out[k]) is type(val), (v, k)


def test_exact_means_exact() -> None:
    assert not hcfg.same({"a": 1}, {"a": 1.0}) and not hcfg.same({"a": 1}, {"a": True})
    assert not hcfg.same({"a": 1, "b": 2}, {"b": 2, "a": 1})  # the key order is the manifest's
    assert not hcfg.same({"a": (1, 2)}, {"a": [1, 2]})


# --- B1: v51 and v52, the adopted base ------------------------------------------------------------
def test_v51_and_v52_resolve_from_their_committed_configs_exactly() -> None:
    for v in (51, 52):
        cfg = hcfg.load(hcfg.path_for(v))
        assert hcfg.same(hcfg.resolve(cfg), P[v]), v
        assert cfg["params_sha256"] == hcfg.params_sha256(P[v])


def test_the_adopted_base_is_v56_with_its_arm_off() -> None:
    """The plan's section 2: the base was v51 with loot_gm_one_pass_ab False; from 10-21 14:22, v52
    = that + map_zones; from 10-22 04:32 (3.97 ADOPTED by its rule), v55 with loot_fast_scan_ab
    False; since 2026-11-06 (rogue-xmas02.md 4K, runs 1 + 2 pooled), v56 with col_nudge_ab False.
    Under blocks, adoption turns the live arm flags off (`adopt`)."""
    assert hcfg.ADOPTED_VERSION == 56
    adopted_v56 = hcfg.resolve(hcfg.adopt(hcfg.export(P, 56)))
    assert hcfg.same(adopted_v56, {**P[56], "col_nudge_ab": False})
    assert hcfg.export(P, 56)["experiment"]["col_nudge_ab"] is True  # the run's A / B, as run
    assert hcfg.rule_ids(P, 56)["engine"] == "engine@56"  # the nudge is an engine gate
    # the history: v55 as it was adopted (10-22 04:32 .. 11-06)
    adopted_v55 = hcfg.resolve(hcfg.adopt(hcfg.export(P, 55)))
    assert hcfg.same(adopted_v55, {**P[55], "loot_fast_scan_ab": False})
    assert all(P[55][k] == v for k, v in P[52].items())  # v55 only ADDS keys to v52 (v54 + guard)
    ids55 = hcfg.rule_ids(P, 55)
    assert ids55 == {"strike": "arm_c@32", "engage_on_the_way": "on_the_way@19",
                     "dead": "exp_line@48", "loot": "gm_fast_scan@54",
                     "search": "heading_coverage@22", "engine": "engine@55"}  # fmt: skip
    # the history: v52 as it was adopted (10-21 14:22 .. 10-22 04:32)
    adopted_v51 = hcfg.resolve(hcfg.adopt(hcfg.export(P, 51)))
    assert hcfg.same(adopted_v51, {**P[51], "loot_gm_one_pass_ab": False})
    assert hcfg.same({**adopted_v51, "map_zones": True}, P[52])
    ids = hcfg.rule_ids(P, 52)
    assert ids == {"strike": "arm_c@32", "engage_on_the_way": "on_the_way@19",
                   "dead": "exp_line@48", "loot": "gm_scan_one_pass@51",
                   "search": "heading_coverage@22", "engine": "engine@42"}  # fmt: skip
    assert hcfg.rule_ids(P, 50)["loot"] == "gm_scan@50"
    assert hcfg.export(P, 52)["experiment"]["loot_gm_one_pass_ab"] is False
    assert hcfg.export(P, 51)["experiment"]["loot_gm_one_pass_ab"] is True


def test_the_committed_configs_are_current() -> None:
    """Every committed config equals a fresh export and resolves exactly; the index is current.
    A PARAMS version without a committed config is NOT a failure (D3: PARAMS stay open; run
    `params_export.py export` when a version is added)."""
    root = hcfg.CONFIG_DIR
    for p in sorted(root.glob("v*.yaml")):
        v = int(p.stem[1:])
        assert v in P, p
        assert p.read_text(encoding="utf-8") == hcfg.dump(hcfg.export(P, v)), (
            f"{p.name} is stale: python3 scripts/params_export.py export"
        )
    committed = {int(p.stem[1:]) for p in root.glob("v*.yaml")}
    assert {51, 52, hcfg.ADOPTED_VERSION} <= committed
    index = (root / pe.INDEX).read_text(encoding="utf-8")
    if committed >= set(P):
        assert index == pe.dump_index(pe.index(P))


# --- the deny-list (the plan's section 6, points 1-2) ---------------------------------------------
def _cfg() -> dict[str, Any]:
    return json.loads(json.dumps(hcfg.export(P, 52)))


def _move(cfg: dict[str, Any], key: str, src: list[str], dst: list[str]) -> dict[str, Any]:
    s = cfg
    for part in src:
        s = s[part]
    d = cfg
    for part in dst:
        d = d[part]
    d[key] = s.pop(key)
    return cfg


@pytest.mark.parametrize(
    ("key", "src", "dst", "match"),
    [
        ("walk_guard", ["engine", "gate"], ["hunt", "loot", "values"], "a gate key"),
        ("loot_unit_px", ["engine", "gate"], ["hunt", "loot", "values"], "a gate key"),
        ("false_dead_fix", ["engine", "safety"], ["hunt", "dead", "values"], "a safety key"),
        ("focus", ["engine", "reader"], ["experiment"], "a reader key"),
        ("send_gap_s", ["engine", "constant"], ["experiment"], "a constant key"),
        ("loot_gm_stand_s", ["hunt", "loot", "values"], ["engine", "constant"], "a rule key"),
        ("abc_arm", ["hunt", "strike", "values"], ["hunt", "loot", "values"], "a choice key"),
    ],
)
def test_the_deny_list_refuses_a_key_out_of_its_class(
    key: str, src: list[str], dst: list[str], match: str
) -> None:
    with pytest.raises(hcfg.ConfigError, match=match):
        hcfg.resolve(_move(_cfg(), key, src, dst))


def test_a_hand_edit_or_a_broken_order_is_refused() -> None:
    cfg = _cfg()
    cfg["hunt"]["loot"]["values"]["loot_gm_stand_s"] = 0.4
    with pytest.raises(hcfg.ConfigError, match="params_sha256"):
        hcfg.resolve(cfg)
    cfg = _cfg()
    cfg["order"].pop()
    with pytest.raises(hcfg.ConfigError, match="order"):
        hcfg.resolve(cfg)
    cfg = _cfg()
    cfg["surprise"] = 1
    with pytest.raises(hcfg.ConfigError, match="keys"):
        hcfg.resolve(cfg)
    cfg = _cfg()
    cfg["hunt"]["loot"]["values"]["walk_guard"] = False  # a gate key given twice
    with pytest.raises(hcfg.ConfigError):
        hcfg.resolve(cfg)


# --- B1: the hunt block in the registry -----------------------------------------------------------
def test_the_hunt_blocks_choices_are_exported_rule_versions() -> None:
    from poring_flow.catalogue import registry

    spec = registry().blocks["hunt"]
    params = {p.name: p for p in spec.params if p.choices}  # the RULE-VERSION parameters
    assert set(params) == set(hcfg.HUNT_PARAMS)
    # the OPTION parameters (Batt 2026-10-22: engage_source, search_route) are no PARAMS rule: not
    # exported, not a PARAMS key of any class, never required (absent = the default), in a group
    options = {p.name: p for p in spec.params if not p.choices}
    assert set(options) == {"engage_source", "search_route"}
    for name, p in options.items():
        assert p.options and p.default in p.options and not p.required, name
        assert hcfg.classify(name) is None and p.group in hcfg.GROUPS, name
    assert options["engage_source"].options == ["detector", "melee_ring"]
    assert options["engage_source"].default == "detector"
    sr = options["search_route"]
    assert sr.options == ["heading", "patrol_route"] and sr.default == "heading"
    assert sr.group == "search"
    index = hcfg.load(hcfg.CONFIG_DIR / pe.INDEX)
    adopted = hcfg.rule_ids(P, hcfg.ADOPTED_VERSION)
    for name, p in params.items():
        assert p.required and p.type == "str" and p.choices, name
        assert set(p.choices) <= set(index["rules"][name]), name
        assert adopted[name] in p.choices, name
        assert name in hcfg.GROUPS[p.group or ""], name
    # no block parameter is a PARAMS key of an engine class (the deny-list at the registry)
    for name in params:
        pat = hcfg.classify(name)
        assert pat is None or pat.cls not in hcfg.ENGINE, name
    assert spec.concept == "combat.hunt" and spec.needs_targets and spec.timeout_s <= 600


# --- B3: the decision code takes the resolved config ----------------------------------------------
def _codes(c: types.CodeType) -> list[types.CodeType]:
    out = [c]
    for k in c.co_consts:
        if isinstance(k, types.CodeType):
            out += _codes(k)
    return out


def test_the_decision_code_reads_only_the_resolved_config() -> None:
    """run() names PARAMS once -- to hand it to hunt_config.params_for -- and none of its nested
    decision closures names PARAMS at all."""
    import ast

    run = hf.run.__code__
    assert "params_for" in run.co_names and "PARAMS" in run.co_names
    tree = ast.parse(Path(hf.__file__).read_text(encoding="utf-8"))
    fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "run")
    uses = [n for n in ast.walk(fn) if isinstance(n, ast.Name) and n.id == "PARAMS"]
    assert len(uses) == 1
    call = next(n for n in ast.walk(fn) if isinstance(n, ast.Call)
                and ast.unparse(n.func) == "hcfg.params_for")  # fmt: skip
    assert ast.unparse(call) == "hcfg.params_for(PARAMS, version)"
    for c in _codes(run)[1:]:
        assert "PARAMS" not in c.co_names, c.co_qualname
    # the pure decision helpers outside run take prm as an argument, never PARAMS
    for name in ("sword_active", "sword_check_wanted", "strike_range", "exp_dead_on", "hand_on",
                 "gm_passes", "gm_on", "gm_union_on"):  # fmt: skip
        fn = getattr(hf, name)
        assert "PARAMS" not in fn.__code__.co_names, name


def test_an_unknown_version_still_raises_keyerror_first() -> None:
    """Before B3, run() met an unknown version at PARAMS[version] (KeyError) before its
    `version not in VERSIONS` check; params_for raises the same."""
    with pytest.raises(KeyError):
        hcfg.params_for(P, 47)


def test_session_file_parity_the_manifests_params_are_byte_identical(
    tmp_path: Path, monkeypatch: Any
) -> None:
    """run() writes the resolved dict as the manifest's `params`; it is byte-identical to the one
    PARAMS[N] wrote, for every version (dry: DemoLog.start into a scratch root, a fixed clock)."""
    from poring_env import demo

    monkeypatch.setattr(demo.time, "time", lambda: 1_790_000_000.0)
    monkeypatch.setattr(demo.time, "monotonic_ns", lambda: 123)
    for v in sorted(P):
        texts = []
        for i, prm in enumerate((P[v], hcfg.params_for(P, v))):
            sid = f"20261021T1800{i:02d}-demo-hunt-flow{v}"
            log = demo.DemoLog(sid, root=tmp_path / str(v))
            log.start(rule=f"{hf.RULE}@{v}", change=hf.VERSIONS[v], params=prm)
            texts.append((log.dir / "manifest.json").read_text().replace(sid, "SID"))
        assert texts[0] == texts[1], v
        assert json.dumps(hcfg.params_for(P, v), indent=1) == json.dumps(P[v], indent=1), v


# --- the nested bytecode proof (scripts/nested_code_proof.py): its positive cases -----------------
def _proof() -> Any:
    import nested_code_proof as ncp

    return ncp


RULE = (
    "LIMIT = 3\n\n\ndef run(table, v):\n    prm = table[v]\n\n    def decide(x):\n"
    "        return x < prm['lim']\n\n    return decide\n"
)


def test_the_nested_proof_names_a_changed_closure(tmp_path: Path) -> None:
    ncp = _proof()
    old, new, moved, plumb = (tmp_path / n for n in ("old.py", "new.py", "moved.py", "plumb.py"))
    old.write_text(RULE)
    new.write_text(RULE.replace("x < prm", "x <= prm"))
    moved.write_text("# a comment\n\n" + RULE)
    plumb.write_text(RULE.replace("prm = table[v]", "prm = dict(table[v])"))
    bad = ncp.compare(old, new, {"run"}, set())
    assert bad["verdict"] == "FAIL" and bad["undeclared"] == ["run.<locals>.decide"]
    assert ncp.compare(old, moved, set(), set())["changed"] == []
    ok = ncp.compare(old, plumb, {"run"}, set())
    assert ok["verdict"] == "PASS" and ok["changed"] == ["run"]
    assert any("dict" in line for line in ok["diffs"]["run"])


def test_flow_zones_reads_the_real_file_with_the_loaders_own_rasters() -> None:
    import flow_zones
    import map_zones as mz

    z = mz.load("prt_fild08")
    assert z is not None
    info = flow_zones.provider()("prt_fild08")
    assert info is not None and info.sha256 == z.sha256 and info.map == "prt_fild08"
    shape = (400, 400)
    assert len(info.closed) == int(mz.no_cross_mask(z, shape).sum())
    assert info.no_enter == frozenset()
    assert flow_zones.provider()("prt_fild06") is None  # no file: no zones
