#!/usr/bin/env python3
"""The HUNT BLOCK's config: hunt_flow's PARAMS[N] as a block config, and back (Batt 2026-10-21,
item 5: "behaviours are to be expressed as BLOCKS"; docs/planning/blocks-from-hunt-flow.md B1 + B3;
ADR-0020 Amendment A, DRAFT).

    export(params, N)      PARAMS[N] -> a config: every key in its CLASS, the hunt block's
                           parameters as RULE VERSIONS (name@N), the engine's internals apart
    resolve(config)        a config -> the flat dict the decision code reads: exactly PARAMS[N],
                           its key order too (the manifest's params record, session-file parity)
    params_for(params, N)  resolve(export(params, N)), refused unless it equals PARAMS[N] exactly:
                           what `hunt_flow.py run --version N` hands its decision code (B3)
    classify(key)          a key's class and hunt-block parameter, from ORDERED NAME PATTERNS

THE CLASSES (the plan's section 2: "a person's choice is a block parameter; gates, safety and
readers stay in the engine"; tuned constants travel with a RULE VERSION):
- block parameters (2a), each under one hunt-block parameter:
    choice      the switch that selects a rule (``loot_gm``, ``abc_arm``, ``heading_cov``, ...)
    rule        a rule constant: travels with the chosen rule version, read-only to a person
- engine internals (2b), NEVER a block parameter (the deny-list: `resolve` refuses one anywhere
  but under ``engine``):
    gate  safety  reader  constant  recovery
- outside both:
    experiment  an arm flag (``*_ab``) or its block length: the executor's alternation (section 4)
    record      log-only switches (shadows, probes, the route preview): no decision reads them
    retired     a rule NOT carried into blocks (the plan's "Not carried"): old versions' records
    map_node    map-node data: ``map_zones`` (the map node's zones reference, Amendment A 4)

GENERIC (Batt D3, 2026-10-21: PARAMS stay OPEN until B4, new versions keep landing): a key is
classified by the FIRST pattern of `PATTERNS` it fully matches, never by a frozen list of keys, so
a new ``loot_*`` key of a new loot version is a loot rule constant without an edit here. A key no
pattern matches is UNCLASSIFIED: `export` refuses it (fail closed) and the coverage test names it.
Keys first seen after `REVIEWED_THROUGH` were classified by pattern only: `params_export.py
classify` lists them for a person to confirm.

RULE VERSIONS: a hunt-block parameter's value is ``<name>@<N>``. The name comes from its switches
(`RULE_NAMES`); N is the FIRST PARAMS version whose values for that parameter are identical (type
and value; the canonical JSON). So the numbers a person picks with a rule are exactly the ones a
pre-registered version ran. (v19, built and never run, already holds v26's engage numbers: the
engage rule reads ``on_the_way@19``.) The engine's internals carry one id the same way
(``engine@N``).

Pure: no I/O but `load` / `dump` (YAML, imported lazily). Our own numbers only: nothing client-
or GPL-derived ever goes into a config (CLAUDE.md rule 4).
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

KIND = "hunt-config"
FORMAT = 1
CONFIG_DIR = Path(__file__).resolve().parents[1] / "config" / "flows" / "hunt"
# The adopted base (blocks-from-hunt-flow.md section 2): v52 = v51 + "loot_gm_one_pass_ab" False
# + "map_zones" True, ADOPTED 2026-10-21 14:22 (demonstrations.md 3.93). Adoption is a commit that
# moves this number (the plan's section 4: "adoption = a commit moving the adopted config").
# ➡️ v55 since 2026-10-22 04:32 (3.97 ADOPTED by its rule, 549b797): v55 with its live arm off
# (`adopt`: "loot_fast_scan_ab" False) = v52 + the fast scan on every loot step + the NPC sprite
# guard. The next version's PARAMS start from {**PARAMS[55], "loot_fast_scan_ab": False}.
# ➡️ v56 since 2026-11-06 ~11:5x (rogue-xmas02.md 4K, ADOPTED by its rule on runs 1 + 2 pooled:
# K1 nudged 0 / 74 unsent vs 21 / 73 off, K2 both runs, K3 1 / 1,274): v56 with its live arm off
# (`adopt`: "col_nudge_ab" False) = v55 adopted + the walk-click nudge off the GM's own column on
# EVERY such click. 4K's "v57 = v56 with col_nudge_ab off" is exactly this adoption; no PARAMS[57]
# is made. The next version's PARAMS start from {**PARAMS[56], "col_nudge_ab": False}.
ADOPTED_VERSION = 56
# The last PARAMS version whose keys a person reviewed in `PATTERNS` (the table below was written
# against v54, 2026-10-21): later keys are classified by their pattern only and listed for review.
REVIEWED_THROUGH = 54

ENGINE = ("gate", "safety", "reader", "constant", "recovery")
BLOCK = ("choice", "rule")
OTHER = ("experiment", "record", "retired", "map_node")
CLASSES = BLOCK + ENGINE + OTHER
# The hunt block's parameters (the plan's 2a) and Batt's groups (D2: one `hunt` block with groups)
HUNT_PARAMS = ("strike", "engage_on_the_way", "dead", "loot", "search")
GROUPS = {
    "engage": ("strike", "engage_on_the_way"),
    "dead_loot": ("dead", "loot"),
    "search": ("search",),
    "stop": (),  # the enclosing loop's condition / max_s (13.5), not a parameter
}


@dataclass(frozen=True)
class Pattern:
    pattern: str  # a regular expression the key must FULLY match
    cls: str  # one of CLASSES
    param: str | None  # the hunt-block parameter (block classes only)
    why: str  # the plan's line it follows


def _p(pattern: str, cls: str, why: str, param: str | None = None) -> Pattern:
    return Pattern(pattern, cls, param, why)


# ORDER MATTERS: the first full match wins (specific names before their family's catch-all).
PATTERNS: tuple[Pattern, ...] = (
    # --- outside the block and the engine ----------------------------------------------------
    _p(r".+_ab", "experiment", "an arm flag: odd k / odd blocks run the change (section 4)"),
    _p(r".+_ab_min", "experiment", "the arm's block length, minutes (v34's 10-min blocks)"),
    _p(r"belief(_.+)?", "retired", "the belief map: off since v30 (Not carried)"),
    _p(r"fast_dead(_.+)?", "retired", "fast dead, 3.72 (Not carried)"),
    _p(r"loot_race|loot_icons|icon_radius|looter_.+", "retired", "the loot race, 3.73"),
    _p(r"species_own", "retired", "own-frame species, 3.75 (Not carried)"),
    _p(r"loot_retry(_.+)?", "retired", "the loot retry, 3.77 (Not carried)"),
    _p(r"heading_age(_.+)?", "retired", "the age-weighted heading, 3.79 (Not carried)"),
    _p(r"steer_tail|steer_guard_.+", "retired", "the route tail 3.80, the steer guard box 3.83"),
    _p(r"strike_cells_walking", "retired", "walkers struck from 7, 3.82 (Not carried)"),
    _p(r"exp_wait_s", "retired", "the EXP line's checked fallback, 3.87 (Not carried)"),
    _p(
        r"shadow_cursor|species_shadow|dead_probe|publish_route",
        "record",
        "log-only: a shadow read, a probe, the route preview (no decision reads it)",
    ),
    _p(
        r"map_zones",
        "map_node",
        "the map node's zones reference (Amendment A 4), not a hunt parameter",
    ),
    # --- engine internals (2b) whose names a block family would otherwise catch ---------------
    _p(
        r"loot_unit_px|loot_pink_.+|loot_corpse(_.+)?",
        "gate",
        "gate: loot click checks (unit near, pink, own corpse)",
    ),
    _p(r"loot_refix(_.+)?", "reader", "reader: position, the loot re-fix"),
    _p(r"loot_death", "reader", "reader: the death cell"),
    _p(r"dead_end_hyst_s", "reader", "reader: the hunting UI layout's companion (v43)"),
    _p(r"gate_frames_s", "reader", "reader: detector frames the walk gate accepts"),
    _p(r"track_clear(_.+)?", "gate", "gate: the walk gate's predicted-position clearance (v3)"),
    _p(r"steer_stuck_s", "recovery", "recovery: a target steered to too long is dropped"),
    _p(r"loot_hand_still_s", "rule", "the drawn standstill v50's rule reuses", "loot"),
    _p(r"loot_hand(_.+)?", "retired", "HAND 3 x 3, 3.90 (Not carried)"),
    # --- the hunt block's parameters (2a) ------------------------------------------------------
    _p(r"abc|abc_arm", "choice", "strike style: C, B or A", "strike"),
    _p(r"opportunistic|preempt_hyst|retarget", "choice", "engage on the way", "engage_on_the_way"),
    _p(r"opp_.+|preempt_.+|retarget_.+", "rule", "engage on the way", "engage_on_the_way"),
    _p(r"exp_dead|exp_keep", "choice", "the dead rule (the EXP line)", "dead"),
    _p(r"exp_.+", "rule", "the dead rule (the EXP line)", "dead"),
    _p(
        r"loot|loot_sweep|loot_blobs|loot_fixed|loot_gm|loot_gm_one_pass|loot_gm_union"
        r"|loot_fast_scan",
        "choice",
        "the loot rule",
        "loot",
    ),
    _p(r"loot_.+|blob_gm_px", "rule", "the loot rule", "loot"),
    _p(r"heading_search|heading_cov", "choice", "the search heading", "search"),
    _p(r"heading_.+|cov_.+", "rule", "the search heading", "search"),
    # --- engine internals (2b) -----------------------------------------------------------------
    _p(
        r"walk_guard|guard_.+|risk_gate|risk_targets_ok|gate_.+|name_tag|tag_.+|species_skip"
        r"|cursor_sword(_.+)?|ptr_rest_.+|still_.+|unit_clear_px|clear_frames|box_clear_.+"
        r"|walk_clear_.+|max_reads",
        "gate",
        "gate: walk guard, risk gate, species identity, cursor SWORD, pointer rest, clearances",
    ),
    _p(r"col_nudge", "gate", "gate: a walk click off the GM's own screen column (v56)"),
    _p(
        r"bg_check|freeze_guard|false_dead_fix|npc_px_guard",
        "safety",
        "safety: stops, the false-dead fix, the NPC sprite guard (v55)",
    ),
    _p(
        r"frame_cells|track_.+|focus(_.+)?|jump_reanchor|reacquire(_.+)?|ui_layout|burst"
        r"|short_read|hover_settle_s|fresh_s|min_box_px|motion_hz|moving_cells|follow_mouse",
        "reader",
        "reader: detector, tracker, focus, position, the lock arrow, the layout",
    ),
    _p(
        r"walk_every_s|ahead(_.+)?|short|strike_.+|pipelined|queue_depth|moving_penalty"
        r"|plan_every_s|waypoint_every_s|dispatch_.+|continuous|stop_after_s|replan_left"
        r"|click_lead_s(_.+)?|lead_.+|reclick_s|give_up_s|dead_.+|drop_target_s|burst_.+"
        r"|zone(_.+)?|send_gap_s",
        "constant",
        "constant: movement, leads, the planner, strike ranges, burst / re-click timing, pacing",
    ),
    _p(
        r"stall_s|unstall_s|stuck_.+|escape_after_s",
        "recovery",
        "recovery: the stall breaker, unstall, the pocket escape",
    ),
)
_COMPILED = tuple((re.compile(p.pattern), p) for p in PATTERNS)
for _p_ in PATTERNS:
    assert _p_.cls in CLASSES, _p_
    assert (_p_.param is not None) == (_p_.cls in BLOCK), _p_
    assert _p_.param is None or _p_.param in HUNT_PARAMS, _p_


class ConfigError(ValueError):
    """A config that is not exactly what its version ran: refused (fail closed)."""


def classify(key: str) -> Pattern | None:
    """The first pattern ``key`` fully matches, or None (UNCLASSIFIED)."""
    for rx, p in _COMPILED:
        if rx.fullmatch(key):
            return p
    return None


# --- rule names -----------------------------------------------------------------------------------
def _strike(v: Mapping[str, Any]) -> str:
    if v.get("abc_arm"):
        return f"arm_{str(v['abc_arm']).lower()}"
    return "abc_interleaved" if v.get("abc") else "read"


def _engage(v: Mapping[str, Any]) -> str:
    return "on_the_way" if v.get("opportunistic") else "off"


def _dead(v: Mapping[str, Any]) -> str:
    if v.get("exp_keep"):
        return "exp_line"
    return "exp_line_checked" if v.get("exp_dead") else "pixel"


LOOT_NAMES = (  # the first switch that is on names the rule (newest rule first)
    ("loot_fast_scan", "gm_fast_scan"),
    ("loot_gm_union", "gm_union"),
    ("loot_gm_one_pass", "gm_scan_one_pass"),
    ("loot_gm", "gm_scan"),
    ("loot_fixed", "fixed_3x3"),
    ("loot_blobs", "blobs"),
    ("loot_sweep", "sweep"),
)


def _loot(v: Mapping[str, Any]) -> str:
    if not v.get("loot"):
        return "none"
    return next((name for key, name in LOOT_NAMES if v.get(key)), "pickup_scan")


def _search(v: Mapping[str, Any]) -> str:
    if v.get("heading_cov"):
        return "heading_coverage"
    return "heading" if v.get("heading_search") else "route"


RULE_NAMES = {"strike": _strike, "engage_on_the_way": _engage, "dead": _dead, "loot": _loot,
              "search": _search}  # fmt: skip


# --- export ---------------------------------------------------------------------------------------
def canon(obj: Any) -> str:
    """The canonical JSON of a value (sorted keys; a tuple prints as a list): its identity."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def params_sha256(prm: Mapping[str, Any]) -> str:
    """The resolved params' hash: keys IN ORDER with their values (what the manifest records)."""
    pairs = [[k, v] for k, v in prm.items()]
    return hashlib.sha256(json.dumps(pairs, separators=(",", ":")).encode()).hexdigest()


def _check_value(key: str, v: Any, version: int) -> None:
    ok = (bool, int, float, str)
    if isinstance(v, ok) or (isinstance(v, tuple) and all(isinstance(x, ok) for x in v)):
        return
    raise ConfigError(f"v{version}: {key} = {v!r}: a config holds bools, numbers, strings and "
                      "tuples of them only")  # fmt: skip


def split(prm: Mapping[str, Any], version: int = 0) -> dict[str, dict[str, Any]]:
    """PARAMS[N] by section: hunt.<param>, engine.<class>, experiment, record, retired, map_node.
    Each section keeps PARAMS[N]'s order. An unclassified key is refused."""
    out: dict[str, dict[str, Any]] = {f"hunt.{p}": {} for p in HUNT_PARAMS}
    out.update({f"engine.{c}": {} for c in ENGINE})
    out.update({c: {} for c in OTHER})
    bad = []
    for k, v in prm.items():
        pat = classify(k)
        if pat is None:
            bad.append(k)
            continue
        _check_value(k, v, version)
        sec = f"hunt.{pat.param}" if pat.cls in BLOCK else (
            f"engine.{pat.cls}" if pat.cls in ENGINE else pat.cls)  # fmt: skip
        out[sec][k] = v
    if bad:
        raise ConfigError(f"v{version}: unclassified key(s) {bad}: add a pattern to "
                          "hunt_config.PATTERNS (and review its class)")  # fmt: skip
    return out


def _engine_values(sec: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    return {c: dict(sec[f"engine.{c}"]) for c in ENGINE}


def rule_ids(params: Mapping[int, Mapping[str, Any]], version: int) -> dict[str, str]:
    """Each hunt-block parameter's rule version ``name@N`` and the engine's ``engine@N`` for
    PARAMS[version]: N = the first version with identical values (canonical JSON). Another
    version with an unclassified key is left out of the search (it names no rule); this one's
    own unclassified key is refused."""
    me = split(params[version], version)
    secs: dict[int, dict[str, dict[str, Any]]] = {}
    for v in sorted(params):
        try:
            secs[v] = me if v == version else split(params[v], v)
        except ConfigError:
            continue
    out: dict[str, str] = {}
    for p in HUNT_PARAMS:
        mine = canon(me[f"hunt.{p}"])
        first = next(v for v in secs if canon(secs[v][f"hunt.{p}"]) == mine)
        out[p] = f"{RULE_NAMES[p](me[f'hunt.{p}'])}@{first}"
    mine = canon(_engine_values(me))
    first = next(v for v in secs if canon(_engine_values(secs[v])) == mine)
    out["engine"] = f"engine@{first}"
    return out


def export(params: Mapping[int, Mapping[str, Any]], version: int) -> dict[str, Any]:
    """PARAMS[version] as a hunt config (a plain dict, ready for YAML). KeyError for an unknown
    version, as ``PARAMS[version]`` raises."""
    prm = params[version]
    sec = split(prm, version)
    ids = rule_ids(params, version)
    return {
        "kind": KIND,
        "format": FORMAT,
        "version": version,
        "keys": len(prm),
        "params_sha256": params_sha256(prm),
        "hunt": {p: {"rule": ids[p], "values": sec[f"hunt.{p}"]} for p in HUNT_PARAMS},
        "map_node": sec["map_node"],
        "engine": {"id": ids["engine"], **_engine_values(sec)},
        "experiment": sec["experiment"],
        "record": sec["record"],
        "retired": sec["retired"],
        "order": list(prm),
    }


# --- resolve --------------------------------------------------------------------------------------
TOP = ("kind", "format", "version", "keys", "params_sha256", "hunt", "map_node", "engine",
       "experiment", "record", "retired", "order")  # fmt: skip


def _tuple(v: Any) -> Any:
    return tuple(v) if isinstance(v, list | tuple) else v


def _mapping(x: Any, where: str) -> Mapping[str, Any]:
    if not isinstance(x, Mapping):
        raise ConfigError(f"{where}: not a mapping")
    return x


def resolve(config: Mapping[str, Any]) -> dict[str, Any]:
    """The flat dict the decision code reads. Refused (ConfigError) when the config is not
    well-formed, a key sits in a section its class does not allow (the DENY-LIST: a gate,
    safety, reader, constant or recovery key anywhere but under ``engine``, or a block key
    outside its hunt parameter), a key is missing from or doubled in ``order``, or the result's
    ``params_sha256`` differs (a hand edit or a stale file)."""
    cfg = _mapping(config, "config")
    if set(cfg) != set(TOP):
        raise ConfigError(f"config: keys {sorted(cfg)}; a hunt config has {sorted(TOP)}")
    if cfg["kind"] != KIND or cfg["format"] != FORMAT:
        raise ConfigError(f"config: kind {cfg['kind']!r} format {cfg['format']!r}; this engine "
                          f"reads {KIND!r} format {FORMAT}")  # fmt: skip
    where_ok: list[tuple[str, Mapping[str, Any], set[str], str | None]] = []
    hunt = _mapping(cfg["hunt"], "hunt")
    if set(hunt) != set(HUNT_PARAMS):
        raise ConfigError(f"hunt: parameters {sorted(hunt)}; the hunt block has "
                          f"{sorted(HUNT_PARAMS)}")  # fmt: skip
    for p in HUNT_PARAMS:
        blk = _mapping(hunt[p], f"hunt.{p}")
        if set(blk) != {"rule", "values"}:
            raise ConfigError(f"hunt.{p}: takes rule and values")
        where_ok.append((f"hunt.{p}", _mapping(blk["values"], f"hunt.{p}.values"), set(BLOCK), p))
    eng = _mapping(cfg["engine"], "engine")
    if set(eng) != {"id", *ENGINE}:
        raise ConfigError(f"engine: takes id and {', '.join(ENGINE)}")
    for c in ENGINE:
        where_ok.append((f"engine.{c}", _mapping(eng[c], f"engine.{c}"), {c}, None))
    for c in OTHER:
        where_ok.append((c, _mapping(cfg[c], c), {c}, None))
    flat: dict[str, Any] = {}
    for where, values, allowed, param in where_ok:
        for k, v in values.items():
            pat = classify(k)
            if pat is None:
                raise ConfigError(f"{where}.{k}: an unclassified key")
            if pat.cls not in allowed or pat.param != param:
                shown = f"hunt.{pat.param}" if pat.param else pat.cls
                raise ConfigError(f"{where}.{k}: a {pat.cls} key ({pat.why}) belongs under "
                                  f"{shown if pat.cls not in ENGINE else 'engine.' + pat.cls}, "
                                  f"never under {where}")  # fmt: skip
            if k in flat:
                raise ConfigError(f"{where}.{k}: given twice")
            flat[k] = _tuple(v)
    order = cfg["order"]
    if not isinstance(order, list) or len(order) != len(set(order)) or set(order) != set(flat):
        missing = sorted(set(flat) - set(order if isinstance(order, list) else []))
        extra = sorted(set(order if isinstance(order, list) else []) - set(flat))
        raise ConfigError(f"order: must name every key once (missing {missing}, unknown {extra})")
    out = {k: flat[k] for k in order}
    if cfg["keys"] != len(out):
        raise ConfigError(f"keys: {cfg['keys']}, the config holds {len(out)}")
    if params_sha256(out) != cfg["params_sha256"]:
        raise ConfigError("params_sha256: the resolved params differ from the ones exported "
                          "(a hand edit or a stale file: re-export)")  # fmt: skip
    return out


def same(a: Mapping[str, Any], b: Mapping[str, Any]) -> bool:
    """EXACT equality: the same keys in the same order, the same values AND types (1 != 1.0 !=
    True here, unlike ``==``)."""
    return list(a) == list(b) and all(
        type(a[k]) is type(b[k]) and canon(a[k]) == canon(b[k]) for k in a
    )


def params_for(params: Mapping[int, Mapping[str, Any]], version: int) -> dict[str, Any]:
    """B3: what `hunt_flow.py run --version N` hands its decision code -- PARAMS[N] exported as a
    hunt config and resolved back, refused unless it is EXACTLY PARAMS[N] (keys, order, values,
    types). A NEW dict: the decision code never holds PARAMS[N] itself."""
    out = resolve(export(params, version))
    if not same(out, params[version]):
        raise ConfigError(f"v{version}: the resolved config is not PARAMS[{version}]")
    return out


def adopt(config: Mapping[str, Any], arms: list[str] | None = None) -> dict[str, Any]:
    """Adoption under blocks (section 4): the change runs on EVERY engagement -- its arm flag off,
    nothing else touched; the result is re-hashed (a new config). `arms`: the flags to turn off;
    by default every LIVE one: ``X_ab`` on while its change ``X`` is on (an arm left on over a
    change that is off, e.g. v33's ``loot_race_ab`` after 3.73, is inert and stays as it was)."""
    out = json.loads(json.dumps(config))
    exp = out["experiment"]
    flat: dict[str, Any] = {}
    for p in HUNT_PARAMS:
        flat.update(out["hunt"][p]["values"])
    for c in ENGINE:
        flat.update(out["engine"][c])
    for c in OTHER:
        flat.update(out[c])
    if arms is None:
        arms = [k for k, v in exp.items() if v is True and k.endswith("_ab")
                and bool(flat.get(k.removesuffix("_ab")))]  # fmt: skip
    for k in arms:
        if exp.get(k) is not True:
            raise ConfigError(f"adopt: {k} is not an arm flag that is on")
        exp[k] = False
    prm = {k: None for k in out["order"]}
    for p in HUNT_PARAMS:
        prm.update(out["hunt"][p]["values"])
    for c in ENGINE:
        prm.update(out["engine"][c])
    for c in OTHER:
        prm.update(out[c])
    out["params_sha256"] = params_sha256({k: _tuple(v) for k, v in prm.items()})
    return out


# --- files ----------------------------------------------------------------------------------------
HEADER = (
    "# GENERATED by scripts/params_export.py from scripts/hunt_flow.py PARAMS[{v}]: do not\n"
    "# edit, re-export. The hunt block's config (docs/planning/blocks-from-hunt-flow.md B1).\n"
    "# hunt: the block's parameters as rule versions (a person's choices; numbers read-only).\n"
    "# engine: gates, safety, readers, constants, recovery (never a block parameter).\n"
    "# experiment: arm flags. record: log-only. retired: rules not carried.\n"
    "# order: PARAMS[{v}]'s key order. Our own numbers only; scripts/hunt_config.py\n"
    "# resolves it back to PARAMS[{v}] exactly.\n"
)


def path_for(version: int, root: Path = CONFIG_DIR) -> Path:
    return root / f"v{version:02d}.yaml"


def yaml_text(data: Any) -> str:
    """YAML with mappings in block style and every sequence in flow style ([a, b, ...], wrapped
    at 100 columns), keys in their given order."""
    import yaml

    class _Dumper(yaml.SafeDumper):
        pass

    def _seq(d: Any, data: Any) -> Any:
        return d.represent_sequence("tag:yaml.org,2002:seq", list(data), flow_style=True)

    _Dumper.add_representer(list, _seq)
    _Dumper.add_representer(tuple, _seq)
    _Dumper.add_representer(dict, lambda d, data: d.represent_dict(data.items()))
    out: str = yaml.dump(data, Dumper=_Dumper, sort_keys=False, default_flow_style=False,
                         width=100, allow_unicode=True)  # fmt: skip
    return out


def dump(config: Mapping[str, Any]) -> str:
    return HEADER.format(v=config["version"]) + yaml_text(dict(config))


def load(path: Path) -> dict[str, Any]:
    import yaml

    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ConfigError(f"{path}: not a mapping")
    return data
