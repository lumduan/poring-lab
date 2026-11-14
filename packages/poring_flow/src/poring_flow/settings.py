"""THE SETTINGS: every number and switch a person may set for the runner's hunt core (Batt
2026-11-13; as BLOCKS since 2026-11-14 ~15:2x, docs/planning/live-blocks.md section 12).

Batt's rules, in his words:
- "remember: the user must be able to set everything again or edit it; nothing is fixed, we only
  put the defaults" (2026-11-13 ~13:3x);
- "make them a GLOBAL config for every map's flow; a map's flow that sets them again overrides
  it, with that map's config first" (~14:2x), "move them too" (~14:4x), "all of them";
- 2026-11-14 ~15:2x: "there should be no runner [page] ... make them ALL blocks, no hardcoding
  like this; the xmas_dun02 map in /flows may have as many tabs as needed".

ONE registry (FIELDS) names each setting: its group (the TAB it lives in on /flows), its kind and
range, the words a person reads, its DEFAULT (our value: what the lab's Run played on 2026-11-14)
and how the runner takes it -- a flag of its own, or ``--tune NAME=VALUE`` (a runner constant,
dungeon@9.44; test_flow_config proves each one is read when the code runs, never bound at import).

A SETTING IS A PROJECT VARIABLE (Tab.vars, a literal) whose name is a field's ``var``: the field's
own name, but for the three in VAR_NAMES (a dotted constant and two catalogue names). The runner
on a map node takes, per setting: that node's variable (any of its tabs) > Global's > the default
(``node_values``, the project model's name rule). A deleted setting block falls back to the level
below. The hotbar keys (group "keys") are NOT setting blocks: they come from the functions
dungeon_hunt names (project.runner_keys), as before.

PURE and stdlib only: poring_flow's lint and catalogue, the browser (settings.gen.ts, from
``typescript_module``), the Run helper and the stage tools (scripts/flow_config.py re-exports this
module) and the live block player read the same table.
"""

from __future__ import annotations

import difflib
import json
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, replace
from typing import Any

VERSION = 3  # 2026-11-14: the settings are blocks (2: the config file, 1: survival.json)
GAME_PX = (1280, 720)  # the game picture: a point lies inside it
KEYS = tuple(f"F{i}" for i in range(1, 10))  # hotbar row 1: the keys the runner reads
KINDS = ("key", "share", "number", "int", "point", "point_or_none", "switch", "choice")
# A setting's PROJECT VARIABLE name where it is not the field's own (stated in ONE place): a
# dotted runner constant is no variable name, and two field names are catalogue names (a block
# loot(t), the built-in respawn), which a variable may not take.
VAR_NAMES: dict[str, str] = {
    "vt.D0_PX": "D0_PX",
    "loot": "loot_step",
    "respawn": "respawn_on_death",
}


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
    # 2026-11-13 ~15:2x (Batt: the techniques' on/off switches too): a switch's / a choice's
    options: tuple[str, ...] = ()  # a choice's values ("off": no flag at all)
    needs: tuple[tuple[str, Any], ...] = ()  # in use only while these hold (else not passed)
    off: str = ""  # a switch the runner has ON by default: the flag that turns it off
    # a SAFETY switch: what happens while it is off (its block's own row, a lint WARNING and the
    # Python line's comment say it; matpilot round 20 #3)
    warn: str = ""
    # 2026-11-14 (live-blocks.md 12): OUR value (DEFAULTS below): a run takes it when neither the
    # map node nor Global sets the setting; a runner constant's is the runner's own number
    # (test_flow_config pins them equal), so it is passed only when a block sets another
    default: Any = None
    # matpilot round 20 #5: the words the block search finds it by besides its own (its group's,
    # FIND_GROUP, and its own, FIND)
    find: tuple[str, ...] = ()

    @property
    def tune(self) -> bool:
        """A runner constant set with --tune (no flag of its own, and no switch)."""
        return not self.flag and self.kind not in ("switch", "choice")

    @property
    def var(self) -> str:
        """Its project variable's name (VAR_NAMES, else the field's own)."""
        return VAR_NAMES.get(self.name, self.name)

    @property
    def block(self) -> bool:
        """A SETTING BLOCK on /flows: every field but the hotbar keys (those come from the
        functions dungeon_hunt names)."""
        return self.group != "keys"


# The groups, in the page's order: (id, title, a line under the title). Each group but "keys" is
# a TAB of the same name on /flows (Global's, and a map node's for the settings it sets itself).
# matpilot round 20 #5 (2026-11-14): in the ready-made box's TAB order (survival before knife), so
# the toolbox's Settings lists them as the tabs show them; "loop" became "timing" (a child read it
# as Control's loop block). A project saved with a "loop" tab still works: a run reads a setting
# from any tab of the node (node_values), only the strip's words are the group's.
GROUPS: tuple[tuple[str, str, str], ...] = (
    ("keys", "hotbar keys", "each its own row-1 key, as on her hotbar"),
    ("survival", "heal and escape", "when she drinks, when she flies away"),
    ("knife", "the Knife swap", "Batt's technique: the Knife at idle, the dagger back on"),
    ("exits", "leaving the map", "when the bag sends her home"),
    ("respawn", "the respawn", "after a death: respawn or not, and the waits"),
    ("start", "the start", "what she needs before the first step"),
    ("fight", "the fight", "when a fight starts, when a target died"),
    ("aim", "choosing and striking", "which monster, how to aim, how fast to click"),
    ("loot", "loot", "the loot step after a fight"),
    ("walk", "walking and exploring", "the search between fights"),
    ("safety", "safety and the end", "the guards and the safe end"),
    ("timing", "timing", "how often the bot looks at the screen"),
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
        "then confirm with the OK button",
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
    # matpilot round 20 #4b/c: each block names its subject (moved or deleted alone, it still says
    # what it belongs to); dungeon_hunt reads HP_DROP_PTS as PERCENT POINTS of her HP bar
    # ((max - now) * 100 >= HP_DROP_PTS): a fall of 2 = 2 % of her max HP
    Field(
        "HP_DROP_PTS",
        "fight",
        "int",
        "a hit the Battle Log missed: her HP falls by at least",
        1,
        30,
        1,
        unit="% of max HP",
    ),  # fmt: skip
    Field(
        "HP_DROP_S",
        "fight",
        "number",
        "a hit the Battle Log missed: that HP fall within",
        0.2,
        10,
        _S,
        unit="s",
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
        "APPROACH_KEEP",
        "aim",
        "int",
        "the walk toward a target stops this far short of it",
        1,
        10,
        1,
        unit="cells",
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
    Field("STILL_N", "aim", "int", "a still screen: this many frame pairs in a row", 1, 10, 1),
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
        "WALK_AHEAD",
        "walk",
        "int",
        "walk this many path cells ahead",
        2,
        15,
        1,
        "--walk-ahead",
        "cells",
    ),  # fmt: skip
    Field(
        "WALK_EVERY_S", "walk", "number", "a walk decision every", 0.3, 10, _S, "--walk-every", "s"
    ),  # fmt: skip
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
    Field(
        "READ_HZ", "timing", "number", "the bot reads the screen", 1, 15, _S, unit="times a second"
    ),  # fmt: skip
    Field(
        "BOX_EVERY_S",
        "timing",
        "number",
        "the monster detector every",
        0.2,
        10,
        _S,
        "--box-every",
        "s",
    ),  # fmt: skip
    Field(
        "BOX_FRESH_S",
        "timing",
        "number",
        "a monster box older than this is not used",
        0.2,
        10,
        _S,
        unit="s",
    ),  # fmt: skip
)
# --- THE TECHNIQUES' SWITCHES (dungeon@9.45; Batt 2026-11-13 ~15:1x: "do all of them": which
# technique runs is the person's too). Each is the runner's own flag; the default is what the flow
# runs today (a FLAG tested off-by-default stays off). A field whose ``needs`` do not hold is NOT
# IN USE: it is not passed, and /flows greys it with the reason -- the value shown is the value
# used.
_ON, _OFF = True, False
SWITCHES: tuple[Field, ...] = (
    # the Knife swap
    Field("knife_swap", "knife", "switch", "Batt's Knife swap", flag="--bare-steal"),
    Field(
        "bare_ready",
        "knife",
        "switch",
        "swap at idle, never at the strike",
        flag="--bare-ready",
        needs=(("knife_swap", _ON),),
    ),  # fmt: skip
    Field(
        "steal_cue",
        "knife",
        "choice",
        "the steal cue",
        flag="--steal-cue",
        options=("popup", "both"),
        needs=(("knife_swap", _ON),),
    ),  # fmt: skip
    Field(
        "swap_gap",
        "knife",
        "switch",
        "a swap restarts the no-hit clocks",
        flag="--swap-gap",
        needs=(("knife_swap", _ON),),
    ),  # fmt: skip
    # leaving the map, the respawn
    Field("weight_exit", "exits", "switch", "go home when the bag is full"),
    Field(
        "respawn",
        "respawn",
        "switch",
        "after a death, respawn at the save point",
        flag="--respawn",
        off="--no-respawn",
        warn="after a death she stays where she fell, and the run ends there",
    ),  # fmt: skip
    # the start
    Field("minutes", "start", "int", "the time box", 5, 600, 1, "--minutes", "min"),
    # the fight
    Field(
        "engage_screen",
        "fight",
        "switch",
        "fight any monster box on the screen",
        flag="--engage-screen",
    ),  # fmt: skip
    Field(
        "reach_check",
        "fight",
        "switch",
        "only boxes the server walks her to in one click",
        flag="--reach-check",
        needs=(("engage_screen", _ON),),
    ),  # fmt: skip
    Field(
        "unreach_escape",
        "fight",
        "switch",
        "3 unreachable attackers in a row: a Fly Wing",
        flag="--unreach-escape",
        needs=(("reach_check", _ON), ("engage_screen", _ON)),
    ),  # fmt: skip
    Field("miss_cue", "fight", "switch", "a Miss drawn at her starts a fight", flag="--miss-cue"),
    Field(
        "late_confirm",
        "fight",
        "switch",
        "a doubtful position read: confirm it at once",
        flag="--late-confirm",
    ),  # fmt: skip
    Field(
        "exp_first",
        "fight",
        "switch",
        "an EXP line in the Battle Log = a kill",
        flag="--exp-first",
        off="--no-exp-first",
    ),  # fmt: skip
    Field(
        "kill_gap",
        "fight",
        "switch",
        "no EXP line: a quiet gap after our hits = a kill",
        flag="--kill-gap",
    ),  # fmt: skip
    Field(
        "quiet_scan",
        "fight",
        "switch",
        "scan the cells around her only after damage",
        flag="--quiet-scan",
    ),  # fmt: skip
    Field(
        "defend_box",
        "fight",
        "switch",
        "a fight started by a hit strikes the live box first",
        flag="--defend-box",
        needs=(("box_strike", _ON),),
    ),  # fmt: skip
    Field(
        "quick_drop",
        "fight",
        "switch",
        "no arrow, no damage after a strike: try the next",
        flag="--quick-drop",
    ),  # fmt: skip
    Field(
        "quick_drop_scaled",
        "fight",
        "switch",
        "the quick drop's wait grows with the distance",
        flag="--quick-drop-scaled",
        needs=(("quick_drop", _ON),),
    ),  # fmt: skip
    # choosing and striking
    Field(
        "value_target", "aim", "switch", "choose the monster worth the most", flag="--value-target"
    ),  # fmt: skip
    Field("box_strike", "aim", "switch", "strike from the detector's box", flag="--box-strike"),
    Field(
        "box_now",
        "aim",
        "switch",
        "a fresh detection right before the strike",
        flag="--box-now",
        needs=(("box_strike", _ON),),
    ),  # fmt: skip
    Field(
        "queue",
        "aim",
        "switch",
        "queue the monsters of the scene, the next one ready",
        flag="--queue",
        needs=(("box_strike", _ON),),
    ),  # fmt: skip
    Field(
        "self_recheck",
        "aim",
        "switch",
        "a sword on her own body: look again first",
        flag="--self-recheck",
    ),  # fmt: skip
    Field(
        "still_strike",
        "aim",
        "switch",
        "a far strike waits for a still screen",
        flag="--still-strike",
    ),  # fmt: skip
    Field(
        "still_target",
        "aim",
        "switch",
        "a walking target: wait until it stands",
        flag="--still-target",
        needs=(("box_strike", _ON), ("box_now", _ON), ("still_strike", _ON)),
    ),  # fmt: skip
    Field(
        "lead_press",
        "aim",
        "switch",
        "a fast walker: aim where it will be",
        flag="--lead-press",
        needs=(("still_target", _ON),),
    ),  # fmt: skip
    Field("far_single", "aim", "switch", "a far strike: one click, then wait", flag="--far-single"),
    Field(
        "near_single",
        "aim",
        "switch",
        "a near strike too (from 2 cells): one click, then wait",
        flag="--near-single",
        needs=(("far_single", _ON),),
    ),  # fmt: skip
    Field(
        "near_single_still",
        "aim",
        "switch",
        "a near strike re-clicks only on a still screen",
        flag="--near-single-still",
        needs=(("near_single", _ON),),
    ),  # fmt: skip
    Field(
        "far_approach", "aim", "switch", "walk toward a far target first", flag="--far-approach"
    ),  # fmt: skip
    Field(
        "skip_own_cells",
        "aim",
        "switch",
        "the scan skips the cells over her own sprite",
        flag="--skip-own-cells",
    ),  # fmt: skip
    Field(
        "walk_stop",
        "aim",
        "switch",
        "a strike that scrolls the screen: stop first",
        flag="--walk-stop",
    ),  # fmt: skip
    Field(
        "box_ignore",
        "aim",
        "int",
        "ignore a box spot after this many empty fights",
        0,
        10,
        1,
        "--box-ignore",
    ),  # fmt: skip
    # loot
    Field(
        "loot",
        "loot",
        "choice",
        "the loot step",
        flag="--loot",
        options=("trim", "v1", "v2", "rhythm"),
    ),  # fmt: skip
    Field(
        "loot_items",
        "loot",
        "choice",
        "look for items with the item model",
        flag="--loot-items",
        options=("xmas02fi5", "xmas02fi4", "xmas02fi3", "off"),
        needs=(("loot", "trim"),),
    ),  # fmt: skip
    Field(
        "loot_memory",
        "loot",
        "switch",
        "remember the items seen after a kill",
        flag="--loot-memory",
        needs=(("loot_items", "!off"),),
    ),  # fmt: skip
    Field(
        "loot_recheck",
        "loot",
        "switch",
        "ask the item model again a moment later",
        flag="--loot-recheck",
        needs=(("loot_items", "!off"),),
    ),  # fmt: skip
    Field(
        "loot_aim",
        "loot",
        "switch",
        "loot only near the kills' boxes",
        flag="--loot-aim",
        needs=(("loot", "trim"), ("box_strike", _ON)),
    ),  # fmt: skip
    Field(
        "loot_first",
        "loot",
        "switch",
        "loot before a box alone starts the next fight",
        flag="--loot-first",
    ),  # fmt: skip
    # walking and exploring
    Field(
        "search",
        "walk",
        "choice",
        "the search between fights",
        flag="--search",
        options=("patrol", "heading"),
    ),  # fmt: skip
    Field(
        "explore",
        "walk",
        "switch",
        "walk to the map's regions worth a visit",
        flag="--explore",
        needs=(("search", "patrol"),),
    ),  # fmt: skip
    Field(
        "explore_cover",
        "walk",
        "switch",
        "exploring favours the regions seen least",
        flag="--explore-cover",
        needs=(("explore", _ON),),
    ),  # fmt: skip
    Field(
        "walk_through",
        "walk",
        "switch",
        "walk on to the next waypoint without stopping",
        flag="--walk-through",
        needs=(("search", "patrol"),),
    ),  # fmt: skip
    Field(
        "walk_pick",
        "walk",
        "switch",
        "walk only to cells the client picks right",
        flag="--walk-pick",
    ),  # fmt: skip
    Field(
        "walk_pick_step",
        "walk",
        "switch",
        "no cell fits: try a shorter step",
        flag="--walk-pick-step",
        needs=(("walk_pick", _ON),),
    ),  # fmt: skip
    Field("walk_trust", "walk", "switch", "trust cells she walked before", flag="--walk-trust"),
    # safety and the end
    Field(
        "npc_guard",
        "safety",
        "switch",
        "no fight click near an NPC",
        flag="--npc-guard",
        warn="a strike near an NPC may open its dialog and stop the run",
    ),  # fmt: skip
    Field(
        "garm_fly",
        "safety",
        "switch",
        "a Garm Baby seen: a Fly Wing",
        flag="--garm-fly",
        warn="she stays when a Garm Baby comes (two killed her, 11-09)",
    ),  # fmt: skip
    Field(
        "garm_confirm",
        "safety",
        "int",
        "Garm Baby alarm: seen in this many detections in a row",
        1,
        5,
        1,
        "--garm-confirm",
        needs=(("garm_fly", _ON),),
    ),  # fmt: skip
    Field(
        "alarm_fast",
        "safety",
        "switch",
        "Garm Baby alarm also read on the HUD's boxes and inside a strike or a wait",
        flag="--alarm-fast",
        needs=(("garm_fly", _ON),),
        warn="the Garm Baby alarm is read only between steps (the knight's party killed her "
        "10 times on 11-13/14 with the alarm never read in time)",
    ),  # fmt: skip
    Field(
        "alarm_solo",
        "safety",
        "share",
        "Garm Baby alarm: one box this sure is enough (0 = off)",
        0.0,
        1.0,
        0.05,
        "--alarm-solo",
        needs=(("alarm_fast", _ON),),
    ),  # fmt: skip
    Field(
        "boss_walk",
        "safety",
        "switch",
        "a boss seen: walk away (before the Fly Wing)",
        flag="--boss-walk",
        needs=(("engage_screen", _ON),),
    ),  # fmt: skip
    Field(
        "unread_step",
        "safety",
        "switch",
        "no position read: a step first, then a Fly Wing",
        flag="--unread-step",
    ),  # fmt: skip
    # timing
    Field(
        "box_detector",
        "timing",
        "choice",
        "the monster detector runs on",
        flag="--box-detector",
        options=("gpu", "cpu"),
    ),  # fmt: skip
    Field(
        "hud",
        "timing",
        "switch",
        "show the boxes on the console's HUD (display only)",
        flag="--hud",
    ),  # fmt: skip
    Field(
        "hud_fast",
        "timing",
        "number",
        "the HUD: a fresh box every",
        0.1,
        0.9,
        _S,
        "--hud-fast",
        "s",
        needs=(("hud", _ON),),
    ),  # fmt: skip
)
# the value settings that are in use only with a technique on
_NEEDS: dict[str, tuple[tuple[str, Any], ...]] = {
    "knife_key": (("knife_swap", _ON),),
    "dagger_key": (("knife_swap", _ON),),
    "knife_max_s": (("knife_swap", _ON),),
    "knife_hp_min": (("knife_swap", _ON),),
    "weight_home": (("weight_exit", _ON),),
    "respawn_at": (("respawn", _ON),),
    "respawn_confirm_at": (("respawn", _ON),),
    "RESPAWN_SETTLE_S": (("respawn", _ON),),
    "RESPAWN_CONFIRM_WAIT_S": (("respawn", _ON),),
    "RESPAWN_LOAD_S": (("respawn", _ON),),
    "RESPAWN_WAIT_S": (("respawn", _ON),),
    "vt.D0_PX": (("value_target", _ON),),
    "LOOT_TRIM_HOVERS": (("loot", "trim"),),
    "EXPLORE_LEG_MAX_S": (("explore", _ON),),
    "NPC_NO_FIGHT": (("npc_guard", _ON),),
    "GARM_FRESH_S": (("garm_fly", _ON),),
}
# OUR VALUES (2026-11-14, live-blocks.md 12): every setting's default. The keys, the Run settings
# and the techniques are what the Run button played on xmas_dun02 (flow_run.FLOWS' defaults before
# 2026-11-14, the night chain's base 4DQ + Batt's numbers of 2026-11-13; that dict is DERIVED from
# this one now); a runner constant's is the runner's own number (test_flow_config pins each equal
# to dungeon_hunt's / value_target's), so a run passes it only when a block sets another.
DEFAULTS: dict[str, Any] = {
    # the hotbar keys (Batt 2026-11-13: "the Butterfly Wing on F9, the Fly Wing on F8"): the
    # functions dungeon_hunt names give them in a project; these are the runner's when none do
    "heal_key": "F1",
    "fly_key": "F8",
    "home_key": "F9",
    "knife_key": "F4",
    "dagger_key": "F5",
    # the Run settings (dungeon@9.41-9.43): the heal and escape numbers are --strategy P2's own
    "knife_max_s": 8.0,
    "knife_hp_min": 0.50,
    "potion_below": 0.40,
    "fly_below": 0.20,
    "fly_rate": 150,
    "fly_rate_below": 0.50,
    "weight_home": 0.50,
    "respawn_at": "645,481",
    "respawn_confirm_at": "714,405",
    # the runner numbers it reads from flags of their own
    "WALK_AHEAD": 7,
    "WALK_EVERY_S": 1.2,
    "BOX_EVERY_S": 1.0,
    # the runner's own constants (--tune only when a block sets another)
    "RESPAWN_SETTLE_S": 1.0,
    "RESPAWN_CONFIRM_WAIT_S": 3.0,
    "RESPAWN_LOAD_S": 4.0,
    "RESPAWN_WAIT_S": 20.0,
    "PLAYER_MIN_WINGS": 5,
    "PLAYER_MIN_HEALS": 5,
    "PLAYER_WINGS_KEEP": 1,
    "PLAYER_POS_S": 5.0,
    "WEIGHT_MAX": 0.48,
    "FIGHT_TAKEN_S": 2.5,
    "HP_DROP_PTS": 2,
    "HP_DROP_S": 1.5,
    "EXP_PAIR_S": 1.0,
    "KILL_GAP_HITS": 5,
    "KILL_GAP_S": 1.5,
    "LOCK_NO_HIT_S": 3.5,
    "vt.D0_PX": 150,
    "APPROACH_CELLS": 9,
    "APPROACH_KEEP": 4,
    "APPROACH_MAX": 2,
    "STILL_PX": 2.0,
    "STILL_N": 3,
    "STILL_MAX_S": 1.5,
    "WALKER_PX": 10.0,
    "HOLD_GAP_S": 0.25,
    "HOLD_MAX_S": 2.5,
    "LEAD_PX": 15.0,
    "LEAD_AGE_S": 0.57,
    "LEAD_CAP_CELLS": 1.0,
    "FAR_CELLS": 4,
    "FAR_MAX_S": 3.5,
    "BURST_GAP_S": 0.6,
    "QUIET_SCAN_S": 5.0,
    "SELF_RECHECK_S": 0.4,
    "LOOT_TRIM_HOVERS": 9,
    "LOOT_MAX_PICKS": 10,
    "LOOT_MAX_S": 25.0,
    "EXPLORE_LEG_MAX_S": 150.0,
    "WALK_PICK_TOL": 1,
    "NOENTRY_CARVE_R": 0,
    "END_HOT_S": 3.5,
    "END_FLY_BELOW": 0.5,
    "STOCK_READ_S": 1.0,
    "JUMP_CELLS": 20,
    "GARM_FRESH_S": 1.5,
    "BOSS_AVOID_S": 30.0,
    "UI_EVERY_S": 10.0,
    "REGEN_STOP": 0.5,
    "POS_FLY_S": 20.0,
    "POS_FLY_MAX": 3,
    "NPC_NO_FIGHT": 8,
    "READ_HZ": 5.0,
    "BOX_FRESH_S": 1.5,
    # every TECHNIQUE (2026-11-13 ~15:2x): the night chain's base, as it ran (4DQ)
    "minutes": 120,
    "knife_swap": True,
    "bare_ready": True,
    "steal_cue": "popup",
    "swap_gap": True,
    "weight_exit": True,
    "respawn": True,
    "engage_screen": True,
    "reach_check": True,
    "unreach_escape": False,
    "miss_cue": True,
    "late_confirm": True,
    "exp_first": True,
    "kill_gap": True,
    "quiet_scan": True,
    "defend_box": False,
    "quick_drop": False,
    "quick_drop_scaled": False,
    "value_target": True,
    "box_strike": True,
    "box_now": True,
    "queue": False,
    "self_recheck": True,
    "still_strike": True,
    "still_target": True,
    "lead_press": True,
    "far_single": True,
    "near_single": False,
    "near_single_still": False,
    "far_approach": True,
    "skip_own_cells": False,
    "walk_stop": False,
    "box_ignore": 2,
    "loot": "trim",
    "loot_items": "xmas02fi5",
    "loot_memory": True,
    "loot_recheck": False,
    "loot_aim": False,
    "loot_first": True,
    "search": "patrol",
    "explore": True,
    "explore_cover": False,
    "walk_through": False,
    "walk_pick": True,
    "walk_pick_step": True,
    "walk_trust": True,
    "npc_guard": True,
    "garm_fly": True,
    "garm_confirm": 2,
    "alarm_fast": True,  # dungeon@9.53 (Batt 2026-11-14: "Fly Wing away"; live-blocks 11)
    "alarm_solo": 0.7,
    "boss_walk": False,
    "unread_step": False,
    "box_detector": "gpu",
    "hud": True,
    "hud_fast": 0.2,
}
# matpilot round 20 #5 (2026-11-14): "knife" found 3 of the 6 knife settings (bare_ready,
# steal_cue and swap_gap lack the word). Every setting block is found by its group's words and by
# its own below, as a learner names what it is about (the toolbox's search; search.ts).
FIND_GROUP: dict[str, tuple[str, ...]] = {
    "survival": ("survival", "heal", "potion", "hp", "fly", "wing", "escape"),
    "knife": ("knife", "dagger", "swap", "steal", "weapon"),
    "exits": ("exits", "home", "bag", "weight", "butterfly", "wing"),
    "respawn": ("respawn", "death", "die", "dead", "save"),
    "start": ("start", "check", "hotbar", "stock"),
    "fight": ("fight", "kill", "hit", "exp", "damage"),
    "aim": ("aim", "target", "click", "strike", "monster"),
    "loot": ("loot", "item", "pick", "drop"),
    "walk": ("walk", "explore", "search", "patrol", "move"),
    "safety": ("safety", "guard", "danger", "end"),
    "timing": ("timing", "speed", "often", "seconds"),
}
FIND: dict[str, tuple[str, ...]] = {
    "potion_below": ("drink",),
    "knife_hp_min": ("hp",),
    "respawn_at": ("click", "button"),
    "respawn_confirm_at": ("click", "button"),
    "minutes": ("minutes", "time", "long"),
    "PLAYER_MIN_WINGS": ("fly", "wing"),
    "PLAYER_WINGS_KEEP": ("fly", "wing"),
    "PLAYER_MIN_HEALS": ("heal", "potion"),
    "WEIGHT_MAX": ("weight", "bag"),
    "HP_DROP_PTS": ("hp",),
    "HP_DROP_S": ("hp",),
    "vt.D0_PX": ("value", "worth"),
    "value_target": ("value", "worth"),
    "LOOT_TRIM_HOVERS": ("hover",),
    "loot_items": ("model",),
    "END_FLY_BELOW": ("fly", "wing", "hp"),
    "END_HOT_S": ("fly", "wing"),
    "POS_FLY_S": ("fly", "wing"),
    "POS_FLY_MAX": ("fly", "wing"),
    "unread_step": ("fly", "wing"),
    "unreach_escape": ("fly", "wing"),
    "garm_fly": ("garm", "alarm", "fly", "wing"),
    "garm_confirm": ("garm", "alarm"),
    "alarm_fast": ("garm", "alarm", "hud"),
    "alarm_solo": ("garm", "alarm"),
    "GARM_FRESH_S": ("garm", "alarm"),
    "npc_guard": ("npc",),
    "NPC_NO_FIGHT": ("npc",),
    "boss_walk": ("boss", "walk"),
    "BOSS_AVOID_S": ("boss",),
    "REGEN_STOP": ("weight", "bag", "hp", "regen"),
    "STOCK_READ_S": ("hotbar", "count"),
    "hud": ("hud", "console", "box"),
    "hud_fast": ("hud", "console", "box"),
    "box_detector": ("detector", "box", "gpu", "model"),
    "BOX_EVERY_S": ("detector", "box", "model"),
    "BOX_FRESH_S": ("detector", "box"),
    "READ_HZ": ("screen", "look"),
}


def _find(name: str, group: str) -> tuple[str, ...]:
    out: list[str] = []
    for w in (*FIND_GROUP.get(group, ()), *FIND.get(name, ())):
        if w not in out:
            out.append(w)
    return tuple(out)


FIELDS = tuple(
    replace(f, needs=_NEEDS.get(f.name, f.needs), default=DEFAULTS[f.name],
            find=_find(f.name, f.group))
    for f in (*FIELDS, *SWITCHES)
)  # fmt: skip

# The runner's flags that are NOT settings, each with the reason (test_flow_config: every flag of
# `dungeon_hunt.py run` is a field's or listed here)
NOT_SETTINGS: dict[str, str] = {
    "--char": "the flow's character: a map's flow is made for one",
    "--map": "the flow's map: the flow is that map's",
    "--player-mode": "the Run button plays as a player, never as a GM (Batt 2026-11-12)",
    "--strategy": "the heal and escape numbers are settings; P2's rest and heal parts never run",
    "--seed": "the run's random seed (the explore picks repeat with it)",
    "--label": "the Run helper names each run's session",
    "--stop-file": "the Run helper's Stop",
    "--tune": "the way the runner's numbers are set",
    "--engage": "the melee ring is the lab server's only (refused elsewhere): the scan is used",
    "--boxes": "the box watcher is the bot's eyes for monsters: the base needs it",
    "--box-model": "the map's own monster model",
    "--stage-mob": "a GM trial line (refused in player mode)",
    "--start-cell": "a GM trial line (refused in player mode)",
    "--stage-at": "a GM trial line (refused in player mode)",
    "--clear-map": "a GM line (refused in player mode)",
    "--steal": "the Steal skill opening: refused with the Knife swap",
    "--heal-candy": "needs its own hotbar layout (candies on F6 / F7): not a switch yet",
    "--rest": "P2 never rests",
    "--plant-sweep": "an old White Plant sweep, off since dungeon@5",
    "--ag-match": "the Crusader's Auto Guard icon",
    "--bank-tags": "data collection, not play",
    "--lead-strike": "replaced by the lead press (they cannot run together)",
}


BY_NAME: dict[str, Field] = {f.name: f for f in FIELDS}
BY_VAR: dict[str, Field] = {f.var: f for f in FIELDS}  # a project variable -> its setting
KEY_FIELDS = tuple(f.name for f in FIELDS if f.kind == "key")
BLOCKS = tuple(f for f in FIELDS if f.block)  # the setting blocks, in the page's order
GROUP_IDS = tuple(g for g, _, _ in GROUPS)
TABS = tuple(g for g in GROUP_IDS if g != "keys")  # the setting tabs, in the page's order
# 2026-11-13 (Batt: every hotbar key from a FUNCTION of the flow, e.g. `def fly_wing():
# press_key("F8")`): the project's functions give KEY_FIELDS' five keys (project.runner_keys);
# they go over the defaults for that run or check
KEYS_SRC = {"flow": "the flow's functions", "config": "the settings"}


def flag_defaults() -> dict[str, Any]:
    """Every setting's default but the runner constants' (those the runner keeps unless a block
    sets another): flow_run.FLOWS' ``defaults`` (2026-11-14: derived, no second copy)."""
    return {f.name: f.default for f in FIELDS if not f.tune}


def keys_problem(keys: Any) -> str | None:
    """PURE: why a Run / check request's ``keys`` cannot be used (None: they can): exactly
    KEY_FIELDS' five names, each a row-1 hotbar key (KEYS). Two on one key is clash's, once they
    are over the run's values (a key not in use may share one)."""
    if not isinstance(keys, dict):
        return "the flow's keys must be an object of {name: key}"
    extra = sorted(str(k) for k in set(keys) - set(KEY_FIELDS))
    if extra:
        return f"the flow's keys name {extra[0]!r}: only {', '.join(KEY_FIELDS)}"
    missing = [k for k in KEY_FIELDS if k not in keys]
    if missing:
        return f"the flow's keys lack {missing[0]}: all five are needed ({', '.join(KEY_FIELDS)})"
    for k in KEY_FIELDS:
        why = problem_of(BY_NAME[k], keys[k])
        if why:
            return f"the flow's keys: {why}"
    return None


def with_keys(vals: Mapping[str, Any], keys: Mapping[str, Any] | None) -> dict[str, Any]:
    """PURE: the run's values with the flow's keys over them (None: as they are)."""
    return {**vals, **({k: keys[k] for k in KEY_FIELDS} if keys else {})}


def _on_grid(v: float, f: Field) -> bool:
    return f.step <= 0 or abs(v / f.step - round(v / f.step)) < 1e-6


def problem_of(f: Field, v: Any) -> str | None:
    """PURE: why ``v`` cannot be ``f``'s value (None: it can)."""
    if f.kind == "switch":
        return None if isinstance(v, bool) else f"{f.words}: {v!r} is not on or off (True / False)"
    if f.kind == "choice":
        return None if v in f.options else f"{f.words}: {v!r} is not one of {list(f.options)}"
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
        return f"{f.words}: {shown(f, v)} is not from {shown(f, f.lo)} to {shown(f, f.hi)}"
    if not _on_grid(float(v), f):
        return f"{f.words}: {shown(f, v)} is not a step of {shown(f, f.step)}"
    return None


def norm(f: Field, v: Any) -> Any:
    """A valid value in its one spelling (an int a whole number, a number rounded to 4 places)."""
    if f.kind in ("switch", "choice"):
        return v
    if f.kind in ("key", "point", "point_or_none"):
        if f.kind != "key" and v != "none":
            x, y = (int(t) for t in str(v).split(","))
            return f"{x},{y}"
        return v
    if f.kind == "int":
        return int(v)
    return round(float(v), 4)


# matpilot round 20 #4c: "1 cells" / "in steps of 1 cells": a unit said of ONE is singular
SINGULAR: dict[str, str] = {"cells": "cell", "times a second": "time a second"}


def unit_of(f: Field, v: Any = None) -> str:
    """The unit after a value ("%" for a share), singular for a value of 1 ("1 cell")."""
    u = "%" if f.kind == "share" else f.unit
    one = isinstance(v, (int, float)) and not isinstance(v, bool) and float(v) == 1.0
    return SINGULAR.get(u, u) if one else u


def shown(f: Field, v: Any) -> str:
    """A value as a person reads it: a share as a percent, a number with its unit."""
    if f.kind == "share" and isinstance(v, (int, float)) and not isinstance(v, bool):
        return f"{float(v) * 100:g} %"
    if isinstance(v, bool):
        return "on" if v else "off"
    if isinstance(v, (int, float)):
        u = unit_of(f, v)
        return f"{v:g}{(' ' + u) if u else ''}"
    return str(v)


def check_level(raw: Any) -> dict[str, Any] | str:
    """PURE: values by setting NAME ({name: value}), normalised, or why they are not (a check
    request's values: the backend computed them from a project's blocks; the helper checks them
    again)."""
    if not isinstance(raw, dict):
        return "the settings must be an object of {name: value}"
    out: dict[str, Any] = {}
    for k, v in raw.items():
        f = BY_NAME.get(k)
        if f is None:
            return f"unknown setting {k!r}"
        why = problem_of(f, v)
        if why:
            return why
        out[k] = norm(f, v)
    return out


def in_use(name: str, vals: Mapping[str, Any], _seen: frozenset[str] = frozenset()) -> bool:
    """PURE: a setting is IN USE when every one of its needs holds (and each needed setting is in
    use itself); one not in use is not passed to the runner (its block says why: not_in_use_why)."""
    f = BY_NAME.get(name)
    if f is None or name in _seen:
        return False
    for other, want in f.needs:
        v = vals.get(other)
        if not in_use(other, vals, _seen | {name}):
            return False
        if want == "!off":
            if v in (None, "off", False):
                return False
        elif v != want:
            return False
    return True


def not_in_use_why(name: str, vals: Mapping[str, Any]) -> str | None:
    """PURE: why a setting is not in use, in words (its first unmet need: "Batt's Knife swap
    (knife_swap) is off"); None: it is in use."""
    f = BY_NAME.get(name)
    if f is None or in_use(name, vals):
        return None
    for other, want in f.needs:
        o = BY_NAME[other]
        v = vals.get(other)
        met = in_use(other, vals) and (v not in (None, "off", False) if want == "!off"
                                       else v == want)  # fmt: skip
        if met:
            continue
        if not in_use(other, vals):
            return f"{o.words} ({o.var}) is not in use itself ({not_in_use_why(other, vals)})"
        if want is True:
            return f"{o.words} ({o.var}) is off"
        if want == "!off":
            return f"{o.words} ({o.var}) is off"
        return f"{o.words} ({o.var}) is {shown(o, v)}, not {shown(o, want)}"
    return "not in use"


def unmet_need(name: str, vals: Mapping[str, Any]) -> tuple[Field, Any] | None:
    """PURE: the ROOT of why a setting is not in use: the setting whose value stops it and the
    value it needs (garm_fly off stops alarm_fast and, through it, alarm_solo); None: in use."""
    f = BY_NAME.get(name)
    if f is None or in_use(name, vals):
        return None
    for other, want in f.needs:
        if not in_use(other, vals):
            return unmet_need(other, vals)
        v = vals.get(other)
        if not (v not in (None, "off", False) if want == "!off" else v == want):
            return BY_NAME[other], want
    return None


def unused_words(name: str, vals: Mapping[str, Any]) -> str | None:
    """PURE (matpilot round 20 #4a): a setting block's short row while it is not in use: "not
    used while npc_guard is off", "not used while loot_step is v1, not trim"; None: in use. The
    lint's info (not_in_use_why: the long words), the block's row and the Python line's comment
    read the same need (lint/settings.py notes)."""
    got = unmet_need(name, vals)
    if got is None:
        return None
    o, want = got
    v = vals.get(o.name)
    if want is True or want == "!off" or v is False:
        return f"not used while {o.var} is off"
    return f"not used while {o.var} is {shown(o, v)}, not {shown(o, want)}"


def clash(vals: Mapping[str, Any]) -> str | None:
    """PURE: why these values cannot run together (None: they can): each hotbar key in use its
    own; the HUD's fast box faster than the detector (the runner refuses it otherwise)."""
    seen: dict[str, str] = {}
    for k in KEY_FIELDS:
        v = vals.get(k)
        if v is None or not in_use(k, vals):
            continue
        if v in seen:
            return f"the {BY_NAME[seen[v]].words} and the {BY_NAME[k].words} are both on {v}: " \
                   "each needs its own key"  # fmt: skip
        seen[v] = k
    hf, be = vals.get("hud_fast"), vals.get("BOX_EVERY_S")
    if hf is not None and be is not None and in_use("hud_fast", vals) and not hf < be:
        return f"the HUD's fresh box every {hf:g} s (hud_fast) must be faster than the detector " \
               f"({be:g} s, BOX_EVERY_S)"  # fmt: skip
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
    """PURE: the runner flags of these values, in FIELDS' order: a flag's own, or --tune; a switch
    on = its flag (off = its off flag, if the runner has one); a choice "off" = nothing; a setting
    not in use = nothing; a runner constant at its default = nothing (the runner's own number:
    2026-11-14, so a box whose blocks hold every default runs exactly today's command)."""
    out: list[str] = []
    for f in FIELDS:
        if f.name not in vals or not in_use(f.name, vals):
            continue
        v = vals[f.name]
        if f.kind == "switch":
            if v and f.flag:
                out.append(f.flag)
            elif not v and f.off:
                out.append(f.off)
            continue
        if f.kind == "choice" and v == "off":
            continue
        if f.tune and v == f.default:
            continue
        fv = flag_value(f, v)
        out += [f.flag, fv] if f.flag else ["--tune", f"{f.name}={fv}"]
    return out


# --- a PROJECT's settings (the blocks; live-blocks.md 12) ----------------------------------------
@dataclass(frozen=True)
class Level:
    """One place a project sets settings: a node's tab (``where`` "xmas_dun02/knife") and its
    variables there ({var: the literal's value})."""

    where: str
    node: str
    tab: str
    vars: Mapping[str, Any]


@dataclass(frozen=True)
class NodeValues:
    """The settings a run on one map node takes: ``vals`` by setting NAME (every field: the keys
    at their defaults, the flow's keys go over them), ``src`` each one's level ("default", or
    "<node>/<tab>"), ``problems`` the setting blocks whose values cannot be used (words; a run
    refuses before any input while there is one)."""

    vals: dict[str, Any]
    src: dict[str, str]
    problems: tuple[str, ...]


def doc_levels(doc: Mapping[str, Any], node: str) -> list[Level]:
    """PURE: the levels a run on ``node`` reads, highest first: that node's tabs, then Global's
    (the project's JSON as a dict: the Run helper's and the player's checked file)."""
    nodes = [n for n in (doc.get("nodes") or []) if isinstance(n, dict)]
    order = [n for n in nodes if n.get("id") == node] + [
        n for n in nodes if n.get("kind") == "global" and n.get("id") != node
    ]
    out: list[Level] = []
    for n in order:
        for t in n.get("tabs") or []:
            if not isinstance(t, dict):
                continue
            vs = {k: (v.get("value") if isinstance(v, dict) else v)
                  for k, v in (t.get("vars") or {}).items()}  # fmt: skip
            out.append(Level(f"{n.get('id')}/{t.get('name')}", str(n.get("id")),
                             str(t.get("name")), vs))  # fmt: skip
    return out


def node_values(levels: Sequence[Level]) -> NodeValues:
    """PURE: the name rule (project-model.md section 3) for the settings: per setting block, the
    first level that sets its variable (the node's own over Global's), else its default. A value a
    setting cannot take is a problem (and the default stands in for it in ``vals``)."""
    vals: dict[str, Any] = {f.name: f.default for f in FIELDS}
    src: dict[str, str] = {f.name: "default" for f in FIELDS}
    probs: list[str] = []
    for f in BLOCKS:
        lvl = next((x for x in levels if f.var in x.vars), None)
        if lvl is None:
            continue
        v = lvl.vars[f.var]
        why = problem_of(f, v)
        if why:
            probs.append(f"{lvl.where}: {f.var}: {why}")
            continue
        vals[f.name], src[f.name] = norm(f, v), lvl.where
    return NodeValues(vals, src, tuple(probs))


def with_setting_tabs(tabs: Sequence[Mapping[str, Any]], values: Mapping[str, Any] | None = None,
                      only: Any = None) -> list[dict[str, Any]]:  # fmt: skip
    """PURE: a node's tabs (the project JSON's dicts) with every setting block put in the tab of
    its group -- an existing tab of that name, else a new one after the others, in the page's
    order -- each at ``values[name]`` or its default; ``only(field)`` keeps the settings it says
    yes to (a map node: only those it sets differently). The browser's settings.ts
    withSettingTabs is the same rule (the ready-made one box is built with it on both sides)."""
    out = [{**t, "vars": dict(t.get("vars") or {})} for t in tabs]
    for f in BLOCKS:
        if only is not None and not only(f):
            continue
        t = next((x for x in out if x.get("name") == f.group), None)
        if t is None:
            t = {"name": f.group, "main": None, "defs": [], "vars": {}}
            out.append(t)
        v = (values or {}).get(f.name, f.default)
        t["vars"][f.var] = {"kind": "lit", "value": lit_value(f, v)}
    return out


def typo_of(var: str) -> Field | None:
    """PURE: the setting an ordinary variable's name looks like a typo of (another spelling of
    the case, or a near name), else None (an ordinary variable)."""
    if var in BY_VAR:
        return None
    low = {f.var.lower(): f for f in FIELDS}
    if var.lower() in low:
        return low[var.lower()]
    near = difflib.get_close_matches(var, list(BY_VAR), n=1, cutoff=0.85)
    return BY_VAR[near[0]] if near else None


def comment(f: Field, v: Any) -> str:
    """The Python view's comment after a setting's assignment: its words and how to read the
    value ("# or at once under HP (50 %)", "# Batt's Knife swap (on / off)")."""
    if f.kind == "switch":
        how = "on / off"
    elif f.kind == "choice":
        how = " / ".join(f.options)
    elif f.kind == "share":
        how = shown(f, v) if problem_of(f, v) is None else "a share: 0.5 = 50 %"
    elif f.kind in ("point", "point_or_none"):
        how = '"X,Y" in the game picture' + (' or "none"' if f.kind == "point_or_none" else "")
    else:
        how = unit_of(f, v)
    return f"# {f.words}" + (f" ({how})" if how else "")


def lit_value(f: Field, v: Any) -> Any:
    """A value as a project literal holds it: a number or a share a float, an int an int."""
    if f.kind in ("number", "share") and isinstance(v, (int, float)) and not isinstance(v, bool):
        return float(v)
    return v


def registry() -> dict[str, Any]:
    """The registry as data (the browser's settings.gen.ts; GET /flows/catalogue's ``settings``)."""
    return {
        "version": VERSION,
        "groups": [{"id": g, "title": t, "note": n} for g, t, n in GROUPS],
        "fields": [
            {
                "name": f.name,
                "var": f.var,
                "group": f.group,
                "block": f.block,
                "kind": f.kind,
                "words": f.words,
                "lo": f.lo,
                "hi": f.hi,
                "step": f.step,
                "unit": f.unit,
                "flag": f.flag or ("--tune" if f.tune else ""),
                "off": f.off,
                "options": list(f.options),
                "warn": f.warn,
                "needs": [[n, w] for n, w in f.needs],
                "default": f.default,
                "find": list(f.find),
            }
            for f in FIELDS
        ],  # fmt: skip
        "keys": list(KEYS),
        "game_px": list(GAME_PX),
        "tabs": list(TABS),
        "singular": dict(SINGULAR),
    }


TS_BANNER = ("/* GENERATED from packages/poring_flow/src/poring_flow/settings.py "
             "(typescript_module; scripts/gen_protocol.sh). DO NOT EDIT. */")  # fmt: skip


def typescript_module(runner_maps: Iterable[str] = ()) -> str:
    """The browser's copy of the registry (services/frontend/src/lib/flow/settings.gen.ts;
    test_settings pins the committed file to this text)."""
    reg = registry()
    reg["runner_maps"] = sorted(runner_maps)
    rows = ["{"]
    for k, v in reg.items():  # one group / one field a line (a diff names the setting that moved)
        if isinstance(v, list) and v and isinstance(v[0], dict):
            rows += [f"  {json.dumps(k)}: [", *(f"    {json.dumps(x, ensure_ascii=False)},"
                                                for x in v), "  ],"]  # fmt: skip
        else:
            rows.append(f"  {json.dumps(k)}: {json.dumps(v, ensure_ascii=False)},")
    body = "\n".join([*rows, "}"])
    return (
        f"{TS_BANNER}\n"
        'import type { SettingsRegistry } from "./settings.ts";\n\n'
        f"export const SETTINGS_REGISTRY: SettingsRegistry = {body};\n"
    )
