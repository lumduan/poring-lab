"""THE FLOW CONFIG: every number and key a person may set for a map's flow (Batt 2026-11-13).

Batt's rules, in his words:
- "remember: the user must be able to set everything again or edit it; nothing is fixed, we only
  put the defaults" (~13:3x);
- "make them a GLOBAL config for every map's flow; a map's flow that sets them again overrides
  it, with that map's config first" (~14:2x, the heal and escape numbers);
- "move them too" (~14:4x: the hotbar keys, the Knife swap, the respawn points) and "all of them"
  (the rest of the runner's numbers: loot, walking, the start minimums ...).

So ONE registry (FIELDS) names each setting: its group on /flows, its kind and range, the words a
person reads, and how the runner takes it -- a flag of its own (the Run settings, 9.41-9.43) or
``--tune NAME=VALUE`` (a runner constant, dungeon@9.44; test_flow_config proves each one is read
when the code runs, never bound at import). ONE file in the human-only settings store holds the
values: ``settings/flowrun/config.json`` = {"v": 2, "global": {name: value}, "maps": {map: {...}}},
written only by the backend (PUT /flows/config, the Settings write gate). Per name, a run takes:
the default < every map's ("global") < its map's own ("map").

PURE and stdlib only: the backend imports it from the read-only scripts mount (as flows_zones
imports map_zones), the Run helper (scripts/flow_run.py) and the export
(scripts/runner_flow_export.py) import it directly.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

VERSION = 2
FILE = "config.json"  # in settings/flowrun/
LEGACY_FILE = "survival.json"  # 8e3ca2df's file (v1: the heal and escape numbers only)
GAME_PX = (1280, 720)  # the game picture: a point lies inside it
KEYS = tuple(f"F{i}" for i in range(1, 10))  # hotbar row 1: the keys the runner reads
MAP_NAME = re.compile(r"[a-z0-9_@-]{1,40}")
KINDS = ("key", "share", "number", "int", "point", "point_or_none")


@dataclass(frozen=True)
class Field:
    name: str  # a Run setting ("fly_key") or a runner constant ("LOOT_TRIM_HOVERS", "vt.D0_PX")
    group: str
    kind: str  # one of KINDS
    words: str  # what a person reads beside it
    lo: float = 0.0
    hi: float = 0.0
    step: float = 0.0  # share / number: the grid (int: 1)
    flag: str = ""  # its own runner flag; "" = a runner constant: --tune NAME=VALUE
    unit: str = ""  # shown after the value: "s", "px", "cells", "HP/s", "%" for a share

    @property
    def tune(self) -> bool:
        return not self.flag


# The groups, in the page's order: (id, title, a line under the title)
GROUPS: tuple[tuple[str, str, str], ...] = (
    ("keys", "hotbar keys", "each its own row-1 key, as on her hotbar"),
    ("knife", "the Knife swap", "Batt's technique: the Knife at idle, the dagger back on"),
    ("survival", "heal and escape", "when she drinks, when she flies away"),
    ("exits", "leaving the map", "the bag's limit for the Butterfly Wing home"),
    ("respawn", "the respawn", "the death menu's button, its confirmation, the waits"),
    ("start", "the start", "what she needs before the first step"),
    ("fight", "the fight", "when a fight starts, when a target died"),
    ("aim", "choosing and striking", "which monster, how to aim, how fast to click"),
    ("loot", "loot", "the loot step after a fight"),
    ("walk", "walking and exploring", "the search between fights"),
    ("safety", "safety and the end", "the guards and the safe end"),
    ("loop", "the loop", "how often the bot looks"),
)

_S = 0.01  # the grid of a time in seconds and of a share given to the hundredth

FIELDS: tuple[Field, ...] = (
    # --- the Run settings (dungeon@9.41-9.43): a flag each ------------------------------------
    Field("heal_key", "keys", "key", "heal item", flag="--heal-key"),
    Field("fly_key", "keys", "key", "Fly Wing", flag="--fly-key"),
    Field("home_key", "keys", "key", "Butterfly Wing", flag="--player-home-key"),
    Field("knife_key", "keys", "key", "Knife", flag="--steal-opener"),
    Field("dagger_key", "keys", "key", "dagger", flag="--dagger-key"),
    Field(
        "knife_max_s",
        "knife",
        "number",
        "dagger back after (or at the steal)",
        0.2,
        20.0,
        0.1,
        "--knife-max-s",
        "s",
    ),  # fmt: skip
    Field(
        "knife_hp_min",
        "knife",
        "share",
        "or at once under HP",
        0.2,
        0.9,
        0.05,
        "--knife-hp-min",
        "%",
    ),  # fmt: skip
    Field(
        "potion_below",
        "survival",
        "share",
        "heal at HP under",
        0.10,
        0.90,
        0.05,
        "--potion-below",
        "%",
    ),  # fmt: skip
    Field(
        "fly_below",
        "survival",
        "share",
        "Fly Wing at HP under",
        0.05,
        0.60,
        0.05,
        "--fly-below",
        "%",
    ),  # fmt: skip
    Field(
        "fly_rate",
        "survival",
        "int",
        "or HP falling faster than",
        50,
        1000,
        1,
        "--fly-rate",
        "HP/s",
    ),  # fmt: skip
    Field(
        "fly_rate_below",
        "survival",
        "share",
        "while under",
        0.20,
        0.90,
        0.05,
        "--fly-rate-below",
        "%",
    ),  # fmt: skip
    Field(
        "weight_home",
        "exits",
        "share",
        "go home when the bag is over",
        0.30,
        0.80,
        0.05,
        "--weight-home",
        "%",
    ),  # fmt: skip
    Field("respawn_at", "respawn", "point", "respawn button at", flag="--respawn-at"),
    Field(
        "respawn_confirm_at",
        "respawn",
        "point_or_none",
        "then confirm (OK) at",
        flag="--respawn-confirm-at",
    ),  # fmt: skip
    # --- the runner's constants (dungeon@9.44): --tune NAME=VALUE ------------------------------
    Field(
        "RESPAWN_SETTLE_S", "respawn", "number", "wait for the death menu", 0.2, 10, _S, unit="s"
    ),  # fmt: skip
    Field(
        "RESPAWN_CONFIRM_WAIT_S",
        "respawn",
        "number",
        "a confirmation shows within",
        0.5,
        15,
        _S,
        unit="s",
    ),  # fmt: skip
    Field(
        "RESPAWN_LOAD_S", "respawn", "number", "the load screen starts within", 1, 30, _S, unit="s"
    ),  # fmt: skip
    Field(
        "RESPAWN_WAIT_S", "respawn", "number", "the save point's map within", 5, 120, _S, unit="s"
    ),  # fmt: skip
    Field("PLAYER_MIN_WINGS", "start", "int", "Fly Wings on the hotbar at least", 1, 99, 1),
    Field("PLAYER_MIN_HEALS", "start", "int", "heal items on the hotbar at least", 0, 99, 1),
    Field("PLAYER_WINGS_KEEP", "start", "int", "end the run at this many Fly Wings", 0, 20, 1),
    Field("PLAYER_POS_S", "start", "number", "her cell must read within", 1, 60, _S, unit="s"),
    Field(
        "WEIGHT_MAX", "start", "share", "refuse to start with the bag at", 0.10, 0.90, _S, unit="%"
    ),  # fmt: skip
    Field(
        "FIGHT_TAKEN_S",
        "fight",
        "number",
        "a hit on her within this = still fighting",
        0.5,
        15,
        _S,
        unit="s",
    ),  # fmt: skip
    Field("HP_DROP_PTS", "fight", "int", "HP points falling ...", 1, 30, 1, unit="%"),
    Field(
        "HP_DROP_S", "fight", "number", "... within = a hit not in the log", 0.2, 10, _S, unit="s"
    ),  # fmt: skip
    Field(
        "EXP_PAIR_S",
        "fight",
        "number",
        "Base + Job EXP lines this close = one kill",
        0.1,
        5,
        _S,
        unit="s",
    ),  # fmt: skip
    Field("KILL_GAP_HITS", "fight", "int", "our hits before a quiet gap means a kill", 1, 40, 1),
    Field(
        "KILL_GAP_S", "fight", "number", "no hit of ours for this = the kill", 0.3, 10, _S, unit="s"
    ),  # fmt: skip
    Field(
        "LOCK_NO_HIT_S",
        "fight",
        "number",
        "locked, no hit for this: let it go",
        0.5,
        20,
        _S,
        unit="s",
    ),  # fmt: skip
    Field(
        "vt.D0_PX",
        "aim",
        "int",
        "the distance that halves a monster's worth",
        20,
        800,
        1,
        unit="px",
    ),  # fmt: skip
    Field(
        "APPROACH_CELLS",
        "aim",
        "int",
        "walk toward a target this far away first",
        2,
        17,
        1,
        unit="cells",
    ),  # fmt: skip
    Field(
        "APPROACH_KEEP", "aim", "int", "... and stop this many cells short", 1, 10, 1, unit="cells"
    ),  # fmt: skip
    Field("APPROACH_MAX", "aim", "int", "approach walks a fight at most", 0, 10, 1),
    Field(
        "STILL_PX",
        "aim",
        "number",
        "the screen moved less than this = still",
        0.5,
        20,
        _S,
        unit="px",
    ),  # fmt: skip
    Field("STILL_N", "aim", "int", "... this many frame pairs in a row", 1, 10, 1),
    Field("STILL_MAX_S", "aim", "number", "wait for a still screen at most", 0, 10, _S, unit="s"),
    Field(
        "WALKER_PX",
        "aim",
        "number",
        "feet moving this far = a walking target",
        1,
        60,
        _S,
        unit="px",
    ),  # fmt: skip
    Field("HOLD_GAP_S", "aim", "number", "a held target: one look every", 0.05, 2, _S, unit="s"),
    Field(
        "HOLD_MAX_S", "aim", "number", "wait for a walker to stand at most", 0.2, 10, _S, unit="s"
    ),  # fmt: skip
    Field(
        "LEAD_PX", "aim", "number", "feet moving this far = aim ahead of it", 1, 80, _S, unit="px"
    ),  # fmt: skip
    Field("LEAD_AGE_S", "aim", "number", "the delay the aim ahead covers", 0, 2, _S, unit="s"),
    Field("LEAD_CAP_CELLS", "aim", "number", "aim ahead at most", 0, 5, _S, unit="cells"),
    Field(
        "FAR_CELLS", "aim", "int", "from this far: one click, no re-click", 1, 17, 1, unit="cells"
    ),  # fmt: skip
    Field("FAR_MAX_S", "aim", "number", "a far click's wait at most", 0.5, 15, _S, unit="s"),
    Field("BURST_GAP_S", "aim", "number", "close up, click again every", 0.1, 5, _S, unit="s"),
    Field(
        "QUIET_SCAN_S",
        "aim",
        "number",
        "scan the cells around her after damage within",
        0.5,
        30,
        _S,
        unit="s",
    ),  # fmt: skip
    Field(
        "SELF_RECHECK_S",
        "aim",
        "number",
        "a sword on her own body: look again after",
        0.05,
        3,
        _S,
        unit="s",
    ),  # fmt: skip
    Field("LOOT_TRIM_HOVERS", "loot", "int", "hovers per loot step at most", 1, 40, 1),
    Field("LOOT_MAX_PICKS", "loot", "int", "pickups per loot step at most", 0, 40, 1),
    Field("LOOT_MAX_S", "loot", "number", "a loot step at most", 2, 120, _S, unit="s"),
    Field(
        "EXPLORE_LEG_MAX_S",
        "walk",
        "number",
        "give up a region not reached by",
        10,
        900,
        _S,
        unit="s",
    ),  # fmt: skip
    Field(
        "WALK_AHEAD", "walk", "int", "walk this many path cells ahead", 2, 15, 1, unit="cells"
    ),  # fmt: skip
    Field("WALK_EVERY_S", "walk", "number", "a walk decision every", 0.3, 10, _S, unit="s"),
    Field("WALK_PICK_TOL", "walk", "int", "the client's pick within", 0, 4, 1, unit="cells"),
    Field(
        "NOENTRY_CARVE_R",
        "walk",
        "int",
        "a no-entry cursor closes this radius",
        0,
        4,
        1,
        unit="cells",
    ),  # fmt: skip
    Field(
        "END_HOT_S",
        "safety",
        "number",
        "at the end: a hit within this = fly first",
        0.5,
        30,
        _S,
        unit="s",
    ),  # fmt: skip
    Field(
        "END_FLY_BELOW",
        "safety",
        "share",
        "at the end: under this HP = fly first",
        0.05,
        0.95,
        _S,
        unit="%",
    ),  # fmt: skip
    Field(
        "STOCK_READ_S",
        "safety",
        "number",
        "read the hotbar count again after",
        0.2,
        10,
        _S,
        unit="s",
    ),  # fmt: skip
    Field(
        "JUMP_CELLS", "safety", "int", "a jump this large = a map change", 5, 80, 1, unit="cells"
    ),  # fmt: skip
    Field(
        "GARM_FRESH_S",
        "safety",
        "number",
        "a Garm Baby alarm at most this old",
        0.2,
        10,
        _S,
        unit="s",
    ),  # fmt: skip
    Field(
        "BOSS_AVOID_S",
        "safety",
        "number",
        "after a boss escape, no box fights for",
        0,
        300,
        _S,
        unit="s",
    ),  # fmt: skip
    Field(
        "UI_EVERY_S", "safety", "number", "check the screen's windows every", 1, 120, _S, unit="s"
    ),  # fmt: skip
    Field(
        "REGEN_STOP",
        "safety",
        "share",
        "the bag share with no natural regen",
        0.10,
        0.99,
        _S,
        unit="%",
    ),  # fmt: skip
    Field(
        "POS_FLY_S",
        "safety",
        "number",
        "no position read for this = a Fly Wing",
        3,
        300,
        _S,
        unit="s",
    ),  # fmt: skip
    Field("POS_FLY_MAX", "safety", "int", "such Fly Wings a run at most", 0, 20, 1),
    Field(
        "NPC_NO_FIGHT",
        "safety",
        "int",
        "no fight click within this of an NPC",
        0,
        30,
        1,
        unit="cells",
    ),  # fmt: skip
    Field("READ_HZ", "loop", "number", "looks a second", 1, 15, _S),
    Field("BOX_EVERY_S", "loop", "number", "the monster detector every", 0.2, 10, _S, unit="s"),
    Field(
        "BOX_FRESH_S",
        "loop",
        "number",
        "a monster box older than this is not used",
        0.2,
        10,
        _S,
        unit="s",
    ),  # fmt: skip
)
BY_NAME: dict[str, Field] = {f.name: f for f in FIELDS}
KEY_FIELDS = tuple(f.name for f in FIELDS if f.kind == "key")


def _on_grid(v: float, f: Field) -> bool:
    return f.step <= 0 or abs(v / f.step - round(v / f.step)) < 1e-6


def problem_of(f: Field, v: Any) -> str | None:
    """PURE: why ``v`` cannot be ``f``'s value (None: it can)."""
    if f.kind == "key":
        return None if v in KEYS else f"{f.words}'s key {v!r} is not a row-1 hotbar key (F1-F9)"
    if f.kind in ("point", "point_or_none"):
        if f.kind == "point_or_none" and v == "none":
            return None
        m = re.fullmatch(r"(\d{1,4}),(\d{1,4})", v) if isinstance(v, str) else None
        if m is None or not (int(m[1]) < GAME_PX[0] and int(m[2]) < GAME_PX[1]):
            return f"{f.words}: {v!r} is not a point X,Y in the {GAME_PX[0]} x {GAME_PX[1]} picture"
        return None
    if isinstance(v, bool) or not isinstance(v, (int, float)) or v != v:
        return f"{f.words}: {v!r} is not a number"
    if f.kind == "int" and float(v) != int(v):
        return f"{f.words}: {v!r} is not a whole number"
    if not f.lo <= float(v) <= f.hi:
        return f"{f.words}: {_shown(f, v)} is not from {_shown(f, f.lo)} to {_shown(f, f.hi)}"
    if not _on_grid(float(v), f):
        return f"{f.words}: {_shown(f, v)} is not a step of {_shown(f, f.step)}"
    return None


def _norm(f: Field, v: Any) -> Any:
    if f.kind in ("key", "point", "point_or_none"):
        if f.kind != "key" and v != "none":
            x, y = (int(t) for t in str(v).split(","))
            return f"{x},{y}"
        return v
    if f.kind == "int":
        return int(v)
    return round(float(v), 4)


def _shown(f: Field, v: Any) -> str:
    if f.kind == "share":
        return f"{float(v) * 100:g} %"
    return f"{v:g}{(' ' + f.unit) if f.unit else ''}" if isinstance(v, (int, float)) else str(v)


def check_level(raw: Any) -> dict[str, Any] | str:
    """PURE: one level's values ({name: value}), normalised, or why it is not one."""
    if not isinstance(raw, dict):
        return "a level of the config must be an object"
    out: dict[str, Any] = {}
    for k, v in raw.items():
        f = BY_NAME.get(k)
        if f is None:
            return f"unknown setting {k!r}"
        why = problem_of(f, v)
        if why:
            return why
        out[k] = _norm(f, v)
    return out


def read_config(d: Path) -> dict[str, Any] | str:
    """The config ({"global": {...}, "maps": {...}}, empty without a file), or why it cannot be
    used. config.json first; else 8e3ca2df's survival.json (v1, the same shape)."""
    path = d / FILE
    if not path.exists() and (d / LEGACY_FILE).exists():
        path = d / LEGACY_FILE
    try:
        text = path.read_text()
    except FileNotFoundError:
        return {"global": {}, "maps": {}}
    except OSError as e:
        return f"the flow config could not be read ({e.__class__.__name__})"
    try:
        doc = json.loads(text)
    except ValueError:
        return f"the flow config ({path.name}) is not valid JSON"
    if not isinstance(doc, dict) or doc.get("v") not in (1, VERSION):
        return f"the flow config ({path.name}) is not version {VERSION}"
    g = check_level(doc.get("global") or {})
    if isinstance(g, str):
        return f"the flow config's every-map values: {g}"
    maps = doc.get("maps") or {}
    if not isinstance(maps, dict):
        return "the flow config's maps must be an object"
    out: dict[str, Any] = {"global": g, "maps": {}}
    for m, lvl in maps.items():
        if not isinstance(m, str) or not MAP_NAME.fullmatch(m):
            return f"the flow config names a map {m!r} that is not a map name"
        got = check_level(lvl)
        if isinstance(got, str):
            return f"the flow config's {m} values: {got}"
        out["maps"][m] = got
    return out


def effective(defaults: Mapping[str, Any], cfg: Mapping[str, Any],
              map_: str) -> tuple[dict[str, Any], dict[str, str]]:  # fmt: skip
    """PURE: the values a run on ``map_`` takes and where each came from: the default, then every
    map's ("global"), then the map's own ("map") -- the map's config first (Batt). A runner
    constant nobody set is absent (the runner keeps its own value)."""
    vals, src = dict(defaults), {k: "default" for k in defaults}
    for level, lvl in (("global", cfg.get("global") or {}),
                       ("map", (cfg.get("maps") or {}).get(map_) or {})):  # fmt: skip
        for k, v in lvl.items():
            if k in BY_NAME:
                vals[k], src[k] = v, level
    return vals, src


def clash(vals: Mapping[str, Any]) -> str | None:
    """PURE: why these values cannot run together (None: they can): each hotbar key its own."""
    seen: dict[str, str] = {}
    for k in KEY_FIELDS:
        v = vals.get(k)
        if v is None:
            continue
        if v in seen:
            return f"the {BY_NAME[seen[v]].words} and the {BY_NAME[k].words} are both on {v}: " \
                   "each needs its own key"  # fmt: skip
        seen[v] = k
    return None


def flag_value(f: Field, v: Any) -> str:
    """A value as the runner's flag takes it (a share with two decimals, as 9.41 did)."""
    if f.kind == "share":
        return f"{float(v):.2f}"
    if f.kind == "int":
        return str(int(v))
    if f.kind == "number":
        return f"{float(v):g}"
    return str(v)


def argv(vals: Mapping[str, Any]) -> list[str]:
    """PURE: the runner flags of these values, in FIELDS' order: a flag's own, or --tune."""
    out: list[str] = []
    for f in FIELDS:
        if f.name not in vals:
            continue
        v = flag_value(f, vals[f.name])
        out += [f.flag, v] if f.flag else ["--tune", f"{f.name}={v}"]
    return out


def put_level(cfg: Mapping[str, Any], scope: str, map_: str | None, group: str,
              values: Mapping[str, Any] | None) -> dict[str, Any] | str:  # fmt: skip
    """PURE: the config with ``group``'s names at that level replaced by ``values`` (None or {}:
    removed -- the next level down applies), or why it cannot be. Only ``group``'s names change."""
    if group not in {g for g, _, _ in GROUPS}:
        return f"unknown group {group!r}"
    names = {f.name for f in FIELDS if f.group == group}
    got = check_level(dict(values or {}))
    if isinstance(got, str):
        return got
    stray = sorted(set(got) - names)
    if stray:
        return f"{stray[0]} is not in the group {group!r}"
    maps = {m: dict(v) for m, v in (cfg.get("maps") or {}).items()}
    doc: dict[str, Any] = {"v": VERSION, "global": dict(cfg.get("global") or {}), "maps": maps}
    if scope == "global":
        lvl = doc["global"]
    elif scope == "map" and map_ and MAP_NAME.fullmatch(map_):
        lvl = doc["maps"].setdefault(map_, {})
    else:
        return "a map's values need the map's name"
    for k in names:
        lvl.pop(k, None)
    lvl.update(got)
    if scope == "map" and not lvl:
        doc["maps"].pop(map_, None)
    return doc


def registry() -> dict[str, Any]:
    """The registry as data (the export gives it to /flows: the groups and their fields)."""
    return {
        "groups": [{"id": g, "title": t, "note": n} for g, t, n in GROUPS],
        "fields": [
            {
                "name": f.name,
                "group": f.group,
                "kind": f.kind,
                "words": f.words,
                "lo": f.lo,
                "hi": f.hi,
                "step": f.step,
                "unit": f.unit,
                "flag": f.flag or "--tune",
            }
            for f in FIELDS
        ],  # fmt: skip
        "keys": list(KEYS),
        "game_px": list(GAME_PX),
    }
