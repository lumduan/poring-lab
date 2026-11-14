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
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

VERSION = 2
FILE = "config.json"  # in settings/flowrun/
LEGACY_FILE = "survival.json"  # 8e3ca2df's file (v1: the heal and escape numbers only)
GAME_PX = (1280, 720)  # the game picture: a point lies inside it
KEYS = tuple(f"F{i}" for i in range(1, 10))  # hotbar row 1: the keys the runner reads
MAP_NAME = re.compile(r"[a-z0-9_@-]{1,40}")
KINDS = ("key", "share", "number", "int", "point", "point_or_none", "switch", "choice")


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
    warn: str = ""  # said beside it while it is off (a safety technique)

    @property
    def tune(self) -> bool:
        """A runner constant set with --tune (no flag of its own, and no switch)."""
        return not self.flag and self.kind not in ("switch", "choice")


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
    Field("READ_HZ", "loop", "number", "looks a second", 1, 15, _S),
    Field(
        "BOX_EVERY_S",
        "loop",
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
        "loop",
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
        warn="off: after a death she stays where she fell, and the run ends there",
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
        "... its wait scaled by the distance",
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
        "... from 2 cells already",
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
        "... favour the regions seen least",
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
        warn="off: a strike near an NPC may open its dialog and stop the run",
    ),  # fmt: skip
    Field(
        "garm_fly",
        "safety",
        "switch",
        "a Garm Baby seen: a Fly Wing",
        flag="--garm-fly",
        warn="off: she stays when a Garm Baby comes (two killed her, 11-09)",
    ),  # fmt: skip
    Field(
        "garm_confirm",
        "safety",
        "int",
        "... seen in this many detections in a row",
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
        "... also read on the HUD's boxes and inside a strike or a wait",
        flag="--alarm-fast",
        needs=(("garm_fly", _ON),),
        warn="off: the Garm Baby alarm is read only between steps (the knight's party killed her "
        "10 times on 11-13/14 with the alarm never read in time)",
    ),  # fmt: skip
    Field(
        "alarm_solo",
        "safety",
        "share",
        "... or one box this sure (0 = off)",
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
    # the loop
    Field(
        "box_detector",
        "loop",
        "choice",
        "the monster detector runs on",
        flag="--box-detector",
        options=("gpu", "cpu"),
    ),  # fmt: skip
    Field(
        "hud", "loop", "switch", "show the boxes on the console's HUD (display only)", flag="--hud"
    ),  # fmt: skip
    Field(
        "hud_fast",
        "loop",
        "number",
        "... a fresh HUD box every",
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
FIELDS = tuple(replace(f, needs=_NEEDS.get(f.name, f.needs)) for f in FIELDS) + SWITCHES

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
KEY_FIELDS = tuple(f.name for f in FIELDS if f.kind == "key")
# 2026-11-13 (Batt: every hotbar key from a FUNCTION of the flow, e.g. `def fly_wing():
# press_key("F8")`): /flows compiles the flow's functions into KEY_FIELDS' five keys and sends them
# with Run / check; they go over the config file's keys for THAT run or check only
KEYS_SRC = {"flow": "the flow's functions", "config": "the settings"}


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
    """PURE: the run's values with the flow's keys over the config's (None: the config's)."""
    return {**vals, **({k: keys[k] for k in KEY_FIELDS} if keys else {})}


def _on_grid(v: float, f: Field) -> bool:
    return f.step <= 0 or abs(v / f.step - round(v / f.step)) < 1e-6


def problem_of(f: Field, v: Any) -> str | None:
    """PURE: why ``v`` cannot be ``f``'s value (None: it can)."""
    if f.kind == "switch":
        return None if isinstance(v, bool) else f"{f.words}: {v!r} is not on or off"
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
        return f"{f.words}: {_shown(f, v)} is not from {_shown(f, f.lo)} to {_shown(f, f.hi)}"
    if not _on_grid(float(v), f):
        return f"{f.words}: {_shown(f, v)} is not a step of {_shown(f, f.step)}"
    return None


def _norm(f: Field, v: Any) -> Any:
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


def in_use(name: str, vals: Mapping[str, Any], _seen: frozenset[str] = frozenset()) -> bool:
    """PURE: a setting is IN USE when every one of its needs holds (and each needed setting is in
    use itself); one not in use is not passed to the runner (/flows greys it with the reason)."""
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
        return f"the HUD's fresh box every {hf:g} s must be faster than the detector ({be:g} s)"
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
    not in use = nothing."""
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
        fv = flag_value(f, v)
        out += [f.flag, fv] if f.flag else ["--tune", f"{f.name}={fv}"]
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
                "flag": f.flag or ("--tune" if f.tune else ""),
                "off": f.off,
                "options": list(f.options),
                "warn": f.warn,
                "needs": [[n, w] for n, w in f.needs],
            }
            for f in FIELDS
        ],  # fmt: skip
        "keys": list(KEYS),
        "game_px": list(GAME_PX),
    }
