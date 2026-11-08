#!/usr/bin/env python3
"""dungeon@1 (Batt 2026-10-22, the day run): the CRUSADER hunts Orc Dungeon F1 (orcsdun01) for
real, immunity OFF, with one of three pre-registered SUSTAIN strategies (docs/demonstrations.md
3.98, pre-registered BEFORE the first scored run):

- A, POTIONS: White Potion (F1) below 60 % HP (3.96's S2 pacing); Fly Wing (F2) below 25 % HP, or
  the HP falling faster than 200 HP/s while under 60 %;
- B, REST: potions and Fly Wings only in an emergency (below 30 % a potion; below 20 %, or mobbed
  = falling faster than 200 HP/s under 40 %, a Fly Wing); after a fight with HP under 60 %, walk to
  the nearest REST SPOT and sit (Insert) until HP reads 100 %; hit while sitting -> stand, fight;
- C, HEAL: B, plus Heal (F5, then a click on the drawn character) below 60 % HP while SP allows
  (34 SP = 11 %), repeated every 1.1 s while under 80 %; rests (as B) only when SP is short.
Every strategy re-casts Auto Guard by 3.96's S4b2 rule (F3, a TOGGLE: only when its icon is off).

ENGAGEMENT WITHOUT A TRAINED DETECTOR ("DEFEND-SCAN", Batt): orcsdun01's monsters are aggressive
and come to us; we fight in melee. A fight starts when the Battle Log shows a hit ON US ("taken",
battle_log.py) or the HP percent falls (2+ points within 1.5 s): the pointer hovers the cells
around the drawn character (ring 1, then ring 2; two motions each, cursor_sword's read) and on a
SWORD clicks there and re-clicks every 0.6 s until the client's lock arrow (arm C), bounded. The
fight then waits for our kill (a Base EXP line) and scans again while hits keep coming. After a
kill, a LOOT hover of the struck cell's 3 x 3 clicks only where the client drew its PICKUP hand.
Between fights the HEADING WALK (hunt_flow.heading_goal) searches; each walk click is made only
where the cursor reads clear (WALK / PICKUP); a SWORD there is engaged (by "walk_sword"). (With
--walk-trust, OFF by default, an UNKNOWN read on a cell walk_trust.trust_why trusts is clicked too:
docs/planning/gef10-cursor-unknown.md.)

PIXELS IN, KEYS AND CLICKS OUT: HP / SP from Basic Info's percent text (hp_percent), the Battle
Log from the chat window (battle_log.py live, its own process), the position from the minimap's
readout (selfpos), the cursor from its pixels (cursor_sword), the Auto Guard icon (survive), the
death dialog's signature (gm_vitals). Nothing reads packets at decision time; the packets of the
run are written afterwards for the offline judge (dungeon_judge.py).

Hard bars (stop the run): a map change (a position jump without our Fly Wing, or a black screen
that stays), an unknown UI state (farm0.client_state, every UI_EVERY_S), an NPC contact (judged
offline; orcsdun01 has no script NPC). A DEATH is a RESULT: the run stops, the cause is recorded,
the dialog closes by its known step (its second button), then @alive + @heal.

dungeon@4 (Batt's overnight brief 2026-10-22, docs/demonstrations.md 4.00; pre-registered before its
runs) changes the BASE for every search, and adds the PATROL search:
- H, B + HEAL (Batt decision 1 + his demo's rhythm): in a fight, Heal below 50 % while SP allows;
  between fights (no hit for CALM_S), Heal below 93 % with SP >= 85 % (his 5 Heals: HP 75-98 %, SP
  89-100 %, 4 of 5 with no hit in the 3 s before); potions only in an emergency (below 30 %); the
  Fly Wing escape as B. REST after a fight when HP < 80 % or SP < 30 % (decision 1b), until HP is
  full and SP >= 40 %; then back INTO the search area (or onto the patrol route);
- the burst of a strike ENDS on our first damage line in the Battle Log (decision 5);
- a walk target the cursor reads NO-ENTRY is carved off the route grid at once (decision 5);
- WHITE PLANTS (Batt: killed on purpose for the White Herb): passing a White Plant spawn area
  (rAthena's spawn lines, static map knowledge), the cursor sweeps its nearest cells (a 2-cell
  lattice, <= PLANT_HOVERS, each area at most every PLANT_EVERY_S); a SWORD there is struck. (v1
  sees plants 0-2 %; the sprite finder, plant_finder.py, did not separate them: not used.)
- --search patrol: Batt's PATROL LOOP (config/routes/orcsdun01.yaml, his demo's circuit, one
  direction): walk its waypoints in order; a fight / loot step / rest interrupts it; afterwards
  resume at the NEXT waypoint AHEAD (map_routes.resume_index), never a passed one. --search heading
  (the default) keeps the heading walk.

dungeon@5 (Batt's decisions on the 2026-10-23 overnight report, riding along with 4.01 as declared
fixes of the BASE, both arms; docs/demonstrations.md 4.01 Amendment A, written before its runs):
- decision 6: NO White Plant cursor sweep (--plant-sweep off); a plant is struck only when met on
  the route (a SWORD read by the walk, a loot hover or a scan, as any monster);
- decision 4: a BOX SPOT (the map cell under a v1 box's foot) whose box-started fights gave no
  SWORD twice is ignored by the box trigger for the rest of the run (4.00's ci5: 120 box fights at
  the Black Mushroom spawn, none struck);
- decision 7: the Auto Guard icon's DUNGEON bar, 40 (survive.AG_MATCH_DUNGEON; 4.00's diagnostic:
  the icon present scored 30.5-35 on the dark dungeon, absent > 45).

dungeon@6 (Batt 2026-10-24, docs/planning/thief-payon.md: the Crusader tests end; a THIEF hunts a
Payon field for economics). The defaults (--char crusader --map orcsdun01, no --steal) are dungeon@5
exactly. New:
- --char thief: the Thief's identity check (crusader.py --char thief), its keys (F1 potion, F2 Fly
  Wing, F3 STEAL; no Auto Guard, no Heal), its max HP (952) and stock (10 potions, 10 Fly Wings);
  the setup never drops the Etc tab for it (Rough Oridecon / Elunium are Etc: it stops instead);
- --map M: the map (its zones file is REQUIRED; rest spots from config/dungeon/M.json when there,
  else the rest sits where it is);
- TAG BANKING (on by default off orcsdun01): at every strike the raw name-tag band under the target
  is saved with its time and box (tags/), for the packet-labelled templates (nametag.py, per map);
- --steal (off by default): STEAL FIRST on a strike whose name tag read Elder Willow or Bigfoot,
  up to 5 tries until the weight rose. ➡️ SUPERSEDED by dungeon@7 below (never run scored).

dungeon@7 (Batt 2026-10-24 ~16:0x, his reply to the 14:10 report: "steal Lv 10 on EVERY monster
once first, no waiting, then attack normally, for speed, until SP runs out; with no SP attack
normally, and once SP is enough for Steal again open with Steal as before"; docs/demonstrations.md
4.04). --steal now means that rule; @6's tag-gated steal (never run scored) is gone:
- every strike on a monster (not a plant) whose spot was not stolen at within STEAL_FORGET_S opens
  with ONE Steal while the Basic Info SP percent (pixels) reads >= steal_sp_pct (Steal costs
  STEAL_SP of the character's max SP); below it, a plain strike;
- the Steal click makes the client walk to range 1 and cast: the cast is read as the SP percent
  falling by >= STEAL_SP_FALL within STEAL_CAST_MAX_S; then the target is beside us, so the strike
  point is FOUND again by hovering ring 1 for the SWORD (the predicted neighbour first:
  steal_ring_order); no SWORD there = no strike click (the fight loop's own scan takes over);
- success = the weight readout rose after the cast (logged; the judge counts it from packets).
  Name tags are no longer needed (--bank-tags still banks them).

dungeon@8 (Batt 2026-10-25, docs/planning/rogue-gef10.md: the Thief became a ROGUE for gef_fild10;
arms "no Steal" (Snatcher Lv 10 alone) vs --steal). New:
- --char rogue: the same character's data (data/thief, the identity check with job "rogue"), its
  max HP 2146 / SP 336 at Base 62 (2209 / 341 at Base 63, held there since 2026-10-26 ~20:5x)
  and the Thief's keys and stock; the setup never drops loot (it is value for
  Batt's Overcharge merchant) and stops at 40 % ("train until the bag is full first");
- the Steal cast is read as an SP-percent fall of half Steal's share of max SP, rounded up
  (steal_sp_fall: Thief 5 points as before, Rogue 10 / 336 SP -> 2 points);
- --clear-map (off by default): the setup types @killmonster2 right after the warp to the map, so
  gef_fild10's natural Orc Lord (MVP, 2 h respawn) is absent from a scored run until the Orc Lord
  flee rule is proven (rogue-gef10.md Amendment A4); every monster respawns.

--rest house (OFF by default; docs/planning/gef10-house-rest.md; gef_fild10 only): the rest walks
to the nearest SEALED orc house (house_rest.py: a room of in_orcs01 from which no dungeon warp is
walkable), makes ONE door click from a standstill on an approach cell, and -- once the pixels say
in_orcs01 (a load gap, then no minimap readout and a dark frame) -- sits at once, never walks,
stands at rest_done, makes ONE click on the room's own exit and expects the field's readout at
that exit's return cell; then the patrol re-joins its loop. Its steps follow house_rest.Trip's
closed table; anything unexpected STOPS the run (never a Fly Wing inside: in_orcs01 is
noteleport). The default (--rest spot) is today's rest.

    dungeon_hunt.py run --strategy A|B|C|H --minutes 45 --seed S [--label L] [--search patrol]
                        [--char crusader|thief|rogue] [--map M] [--steal] [--bank-tags]
                        [--walk-trust] [--rest spot|house]
    (dungeon@7: --steal = Batt's steal-first on every monster, SP permitting)
"""

from __future__ import annotations

import argparse
import contextlib
import json
import math
import sys
import threading
import time
from collections import Counter, deque
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

ROOT = Path(__file__).resolve().parents[1]
DEMO = Path("/dev/shm/poring-lab-demo")
MAP = "orcsdun01"
MR_MAPS = frozenset({"orcsdun01"})  # every spawning species a target, 0 script NPCs (prep doc)
MR_VERSION = "dungeon@3-melee_ring"  # Batt 2026-10-22 13:4x: the cursor-driven engagement
VERSION = "dungeon@8.7"  # @1 = the 11:41 pilot; @2 = + Batt's loot list + sweep; @4 = 4.00's base;
# @5 = @4 + Batt's decisions 4 / 6 / 7 of 2026-10-23 (4.01 Amendment A); @6 = @5 + --char / --map /
# --steal / tag banking (2026-10-24; the defaults are @5's behaviour); @7 = --steal on every monster
# (Batt 2026-10-24 ~16:0x, demonstrations 4.04); @8 = --char rogue + the Steal cast read per max SP
# (Batt 2026-10-25, docs/planning/rogue-gef10.md); @8.1 = a Fly Wing after 20 s without a position;
# @8.2 = no stand toggle after a hit; @8.3 = the stock read from the HOTBAR (Amendment M: a stale DB
# save left 4.05 a10 with 0 Fly Wings); @8.4 = the stock guard in the run (Amendment Y: c7 used its
# 10th Fly Wing at 28.5 min and hunted 7.5 min with no escape): the hotbar count is re-read after
# every potion / Fly Wing press, and a count of 0 ends the run ("stock_out"); @8.5 = a SAFE END
# (Amendment AA: c10's time box ended it inside a 10-orc swarm and it died 0.96 s after run_end,
# during the end warp's typing): under attack or below half HP at the end, a Fly Wing goes first;
# @8.6 = the no-entry sign read by its RING (ring_score: xmas_dun02's orange floor passed the old
# red count), a no-entry carves its one cell, and a dead end forgets the carves before it flies;
# @8.7 = no walk click straight north of us (column_dodge: the client sent no move request for them)
REST_FILE = ROOT / "config" / "dungeon" / "orcsdun01.json"  # rest spots (static map knowledge)
Cell = tuple[int, int]

STRATEGIES: dict[str, dict[str, Any]] = {
    "A": {"potion_below": 0.60, "fly_below": 0.25, "fly_rate": 200.0, "fly_rate_below": 0.60,
          "rest_below": None, "heal_below": None},
    "B": {"potion_below": 0.30, "fly_below": 0.20, "fly_rate": 200.0, "fly_rate_below": 0.40,
          "rest_below": 0.60, "heal_below": None},
    "C": {"potion_below": 0.30, "fly_below": 0.20, "fly_rate": 200.0, "fly_rate_below": 0.40,
          "rest_below": 0.60, "heal_below": 0.60, "heal_until": 0.80, "heal_sp_min": 0.11},
    # Batt 2026-10-26 ~14:5x (rogue-gef10.md Amendment T): "no sitting; keep HP above 20 % with
    # White Potions and hunt continuously -- I want the rate per hour with no rest at all". A
    # potion below 40 % (an Orc Warrior hits up to ~300 = 14 %: two hits from 40 % stay above
    # 20 %), the Fly Wing only below 15 %, and 30 potions stocked (no sitting repays the damage)
    "P": {"potion_below": 0.40, "fly_below": 0.15, "fly_rate": 200.0, "fly_rate_below": 0.25,
          "rest_below": None, "heal_below": None, "potions_to": 30},
    # Amendment U (c5 under P died at 4.5 min to a SWARM: 8 orcs, ~200-250 HP/s, 3 potions eaten
    # within a second each, the last 37 % -> 0 in 0.8 s): P + the swarm escape -- a Fly Wing when
    # HP < 50 % AND dropping >= 150 HP/s over 2 s (c5 would have flown at ~43 %, 5 s before)
    # Amendment Y: 20 Fly Wings (c7 used 10 in 28.5 min, 16.7 / h; was the char's 10)
    "P2": {"potion_below": 0.40, "fly_below": 0.20, "fly_rate": 150.0, "fly_rate_below": 0.50,
           "rest_below": None, "heal_below": None, "potions_to": 30, "wings_to": 20},
    # dungeon@4 (Batt 2026-10-22: decision 1 + 1b, and his demo's Heal rhythm)
    "H": {"potion_below": 0.30, "fly_below": 0.20, "fly_rate": 200.0, "fly_rate_below": 0.40,
          "rest_below": 0.80, "rest_sp_below": 0.30, "rest_until_sp": 0.40,
          "heal_below": 0.50, "heal_until": 0.80, "heal_sp_min": 0.11,
          "heal_calm_below": 0.93, "heal_calm_sp_min": 0.85,
          # 4.00 Amendment I (p1, 2026-10-22 20:59): 50 White Potions weigh 750 of 4,150 and the
          # loot crossed 50 % (no natural regen) at 14.7 min; H drinks potions only below 30 %
          "potions_to": 10},
}  # fmt: skip
KEYS = {"potion": "F1", "fly": "F2", "autoguard": "F3", "heal": "F5", "sit": "Insert",
        "stand": "Insert"}  # fmt: skip
MAX_HP = 5260  # the Crusader's (CHARS_CONF holds each character's)
READ_HZ = 5.0
HEAL_GAP_S = 1.1  # Heal's after-cast delay is 1 s (pinned skill_db AL_HEAL AfterCastActDelay)
SELF_PX = (640, 330)  # the drawn character's body (client px): Heal's target click
FOOT_PX = (641, 362)  # the camera's projection of our own cell
BODY_UP = 26  # a monster's body above its cell's projected point (px): the hover point
FIGHT_TAKEN_S = 2.5  # a hit on us within this long = in a fight
STOCK_READ_S = 1.0  # dungeon@8.4: the hotbar count is re-read this long after a potion / wing
STOCK_TRIES = 5  # an unreadable re-read (the teleport's dark frames) is retried, 1 s apart
END_HOT_S, END_FLY_BELOW = 3.5, 0.5  # dungeon@8.5: still in a fight at the end / HP share
MISS_CUE_RULE = "9.1b"  # --miss-cue: only a Miss read AFTER the last fight's end starts a fight
HP_DROP_PTS, HP_DROP_S = 2, 1.5  # the HP percent falling this much this fast = a hit unseen
LOCK_NO_HIT_S = 3.5  # locked, but none of OUR hits in the log for this long -> scan again
LOCK_MAX_S = 25.0
BURST_GAP_S, BURST_MAX, BURST_MAX_S = 0.6, 4, 3.0  # arm C: re-click until the lock arrow
# --walk-stop (dungeon@9.2, rogue-xmas02.md 4Q, pilot p10): a strike on a RING-1 cell attacks in
# place, so the scene never scrolls; a scroll >= WALK_STOP_PX on WALK_STOP_N polls in a row before
# the lock arrow or our damage line means the click hit the GROUND (p9's class D: 9 of 25 strikes,
# each walking us ~6 cells off the attacker). The burst stops, no lock is taken, and the defend
# scan skips that cell for FALSE_REL_S. Ring-1 bursts re-click every WALK_STOP_GAP_S, so the check
# sees the first click's walk (its request came +0.36 s after the click in p9) before a second.
WALK_STOP_PX, WALK_STOP_N, WALK_STOP_GAP_S, FALSE_REL_S = 10.0, 2, 0.8, 3.0
WALK_STOP_SETTLE_S = 0.4  # after a walked strike: our 1-2 cell walk ends before the next scan
WALK_STOP_BY = ("scan", "stall_scan", "box", "queue")  # the fight paths only
# --self-recheck (dungeon@9.3, rogue-xmas02.md 4R, pilot p11; Batt 2026-11-08 chose option a): the
# defend scan's N / S body points lie ON the Rogue's own sprite (641,312 / 641,288 / 641,360), and
# a SWORD read there was a ground click in 6 of p9's 9 class-D strikes and 4 of p10's 13. Neither
# her aura nor the Miss text alone reads as a sword (0.21-0.55 vs SWORD_MIN 0.75, measured): the
# sword there is TRANSIENT (an attacking monster's frame, or the arrow over her effects). So a
# sword at a point inside her own sprite box counts only if it is still there SELF_RECHECK_S later.
SELF_RECHECK_S, SELF_HALF_W, SELF_UP, SELF_DOWN = 0.4, 20, 95, 6  # the box around her feet point
CURSOR_WAIT_S = 0.35
LOOT_MAX_HOVERS, LOOT_MAX_PICKS, LOOT_MAX_S = 30, 10, 25.0  # one loot step's bounds
# --loot trim (docs/planning/gef10-idle-study.md, gef10-eyes-loot.md E1): v1's list, nearest first,
# capped at this many cell HOVERS (cells out of view not counted), and no sweep. 80 of 84 pickups
# of c5b-c7 came within the first 9 hovers; 1,180 of 1,379 loot-step seconds came after the last
LOOT_TRIM_HOVERS = 9
SWEEP_X, SWEEP_Y = 8, 6  # the sweep's cells: those in view around us (camera_rdp: 34 / 24 px)
SWEEP_DIFF = 15.0  # a cell's 24 x 20 grey patch changed by this mean |diff| since the fight began
SWEEP_MAX = 10  # at most this many changed cells hovered per sweep
# loot v2 (Batt 2026-10-22, decision 4; docs/demonstrations.md 4.01): the CHANGED cells first, the
# plain list cells after, a time budget per FIGHT (the loot steps after one fight share it), and a
# cell hovered empty is skipped unless a kill came within 2 cells of it after that hover
LOOT_FIGHT_BUDGET_S = 10.0
LOOT_V2_MAX_HOVERS = 40
# 4.02 (Batt 2026-10-23, decision 2: his demo's RHYTHM): v2's order, at most 2 pickups and 2.5 s
# per FIGHT (he moved on 2.4 s after a fight, median, with one pickup); the loop recovers the rest
LOOT_RHYTHM_BUDGET_S = 2.5
LOOT_RHYTHM_PICKS = 2
PICKUP_MIN = 0.90  # cursor_sword: a drawn PICKUP hand
WALK_AHEAD = 7  # the walk click's target: this many path cells ahead (in view)
WALK_EVERY_S = 1.2
REST_NEAR = 1  # at the rest spot = within this many cells (Chebyshev)
REST_MAX_S = 300.0
REST_WALK_MAX_S = 120.0  # 3.98 Amendment B: the spot not reached in this long -> sit where we are
UI_EVERY_S = 10.0
FLY_SETTLE_S = 2.5  # Amendment H: the position is not read this long after a Fly Wing ...
FLY_JUMP_S = 15.0  # ... and a jump within this long after one is never a hard bar
JUMP_CELLS = 20  # a position jump this large without our Fly Wing = a map change (stop) ...
WALK_S_PER_CELL, WALK_SLACK = 0.15, 5  # ... and larger than a walk could cover (Amendment J)
WEIGHT_MAX = 0.48  # the setup refuses to start at or over this (natural regen stops at 50 %)
# xmas_dun02 (Batt 2026-11-05: walk the map's EDGE, clockwise; docs/planning/xmas02-prep.md 4): a
# PATROL run starts ON the loop, (start, fallback), never at the search area's centre (there: the
# maze, 11 cells from the only exit warp). The first cell that is on the route grid (walkable,
# outside every zone) and passes the three stand-cell checks is used; none -> refused, no input
PATROL_START: dict[str, tuple[Cell, Cell]] = {"xmas_dun02": ((7, 21), (114, 23))}
WARP_READY_S = 20.0  # dungeon@8: after a setup @warp, Basic Info must read again within this
POS_FLY_S, POS_FLY_MAX = 20.0, 3  # dungeon@8.1: no position read this long -> a Fly Wing (<= 3)
POTIONS_TO, WINGS_TO = 40, 15  # the setup's top-up (by @item, against the DB's last save)
CLEAR_AT = 0.40  # the setup drops the Etc tab (loot only) at or over this weight share ...
CLEAR_STAND = ("prt_fild08", 268, 107)  # ... on the Crusader's open-field stand (no monster)
# dungeon@6: each test character (crusader.py CHARS): its job for the identity check, max HP (the
# HP-rate trigger), keys, Auto Guard or not, stock, and whether the setup may drop the Etc tab
CHARS_CONF: dict[str, dict[str, Any]] = {
    "crusader": {"job": "crusader", "max_hp": 5260, "keys": KEYS, "autoguard": True,
                 "potions_to": None, "wings_to": WINGS_TO, "clear_etc": True},
    "thief": {"job": "thief", "max_hp": 952, "max_sp": 112,  # its status window (thief-payon 4)
              "keys": {"potion": "F1", "fly": "F2", "steal": "F3", "sit": "Insert",
                       "stand": "Insert"},
              "autoguard": False, "potions_to": 10, "wings_to": 10,
              # Rough Oridecon 756 / Rough Elunium 757 are Etc: never dropped by the setup
              "clear_etc": False},
    # dungeon@8 (Batt 2026-10-25, rogue-gef10.md): the SAME character (data/thief, Thief8fce) after
    # its job change; its status window 2026-10-25 19:3x: HP 2146, SP 336 (Base 62 / Rogue 50).
    # Loot is value now (his Overcharge merchant): never dropped; at 40 % the setup stops ("train
    # until the bag is full first", Batt 2026-10-25)
    # Batt 2026-10-26 ~20:5x: the Rogue levelled 62 -> 63 by hunting (max HP 2146 -> 2209); HOLD
    # it at 63 ("ค้างไว้ที่ 63"): the setup lowers a higher DB level with @baselevelup -N.
    # ➡️ Batt 2026-11-05 (xmas_dun02, docs/planning/rogue-xmas02.md): base AGI 99 + DEX 99, so Base
    # 99 (@baselevelup 36, @agi 17, @dex 59 at 15:04); its status window 15:05: HP 5070, SP 530,
    # HIT 205, FLEE 246+1, ASPD 176. The hold is 99 now (a higher level cannot exist)
    "rogue": {"job": "rogue", "data": "thief", "max_hp": 5070, "max_sp": 530,
              "keys": {"potion": "F1", "fly": "F2", "steal": "F3", "sit": "Insert",
                       "stand": "Insert"},
              "autoguard": False, "potions_to": 10, "wings_to": 10, "clear_etc": False,
              "hotbar_stock": True,  # dungeon@8.3: the stock is read from the hotbar
              "level_hold": 99},
}  # fmt: skip
STOCK_ITEMS = {"potion": 504, "fly": 601}  # the hotbar key -> its item (White Potion, Fly Wing)


def stock_plan(counts: dict[int, int | None], targets: dict[int, int]) -> dict[int, int]:
    """PURE (dungeon@8.3, rogue-gef10.md Amendment M): the amount of each item to add so that the
    hotbar's count reaches its target. An unreadable count is a Stop (never a guess): 4.05 a10's
    setup trusted a stale DB save, added no Fly Wing, and the Rogue hunted with none."""
    out = {}
    for item, want in targets.items():
        have = counts.get(item)
        if have is None:
            raise ValueError(f"the hotbar count of item {item} is unreadable")
        out[item] = max(0, want - have)
    return out


NPC_NO_FIGHT = 8  # dungeon@9.0b (c2, 12:53): no fight click within this many cells of an NPC
NPC_GUARDED = frozenset({"strike", "strike_burst", "steal", "loot"})


def npc_guard_blocks(here: Cell | None, npcs: Sequence[Sequence[int]], why: str,
                     radius: int = NPC_NO_FIGHT) -> bool:  # fmt: skip
    """PURE (dungeon@9.0b, rogue-gef10.md Amendment P): a strike / Steal / loot click is refused
    while OUR cell is within ``radius`` (Chebyshev) of an NPC. In c2 (2026-10-26 12:53) a strike on
    a monster standing in front of gef_fild10's bulletin board landed on the board's sprite and
    opened its dialog (a hard bar). NPC sprites stand at most ~5 cells tall, so a click from 8+
    cells away cannot land on one. Walk clicks are not refused here (walk_trust has its own NPC
    distance; the cursor gate reads an NPC as not-walkable)."""
    if why not in NPC_GUARDED or here is None or not npcs:
        return False
    return min(max(abs(here[0] - int(n[0])), abs(here[1] - int(n[1]))) for n in npcs) <= radius


def patrol_start(map_: str, okr: Any, check: Any) -> Cell:
    """The map's PATROL_START cell: the first of (start, fallback) on the route grid ``okr`` whose
    three stand-cell checks pass (``check(map, [cell])`` -> None, else the refusal)."""
    why: list[str] = []
    for c in PATROL_START[map_]:
        if not okr[c[1], c[0]]:
            why.append(f"{c}: off the route grid (a wall or a zone)")
            continue
        if (refusal := check(map_, [c])) is not None:
            why.append(f"{c}: {refusal}")
            continue
        return c
    raise SystemExit(f"dungeon@4 refused: no patrol start for {map_} passes: {why}")


def hotbar_slot(key: str) -> int:
    """PURE: the 1-row hotbar slot of an F-key (F1 = slot 0)."""
    if len(key) == 2 and key[0] == "F" and key[1] in "123456789":
        return int(key[1]) - 1
    raise ValueError(f"not a row-1 hotbar key: {key!r}")


STEAL_FORGET_S = 40.0  # a target stolen at: no new try within 2 cells for this long
# dungeon@7 (Batt ~16:0x: ONE Steal on every monster first, SP permitting)
STEAL_SP = 10  # pinned pre-re skill_db TF_STEAL SpCost (every level)
STEAL_CAST_MAX_S = 3.0  # the walk to range 1 (~0.15 s a cell) + the cast + the SP line redrawn
STEAL_SP_FALL = 5  # SP percent points: the Steal was cast (10 of the Thief's 112 = 8.9 points);
# dungeon@8: steal_sp_fall(max_sp) = half the expected fall, rounded up (Thief 5, Rogue 10/336 -> 2)
STEAL_POLL_S = 0.1
STEAL_SETTLE_S = 0.3  # after the cast: the weight line redrawn before it is read
TAG_BOTTOM = 4  # px below the cell's projected point: the pseudo box's bottom for the tag band
ARROW_UP = 150  # the lock arrow's search band: 150..10 px above the strike point
QUICK_S = 0.25  # guard_tick: an HP read at most this often inside a long action
MAX_SHOTS = 40  # strike frames kept per run (JPEG, the session dir)
AG_DIAG_MAX, AG_DIAG_GAP_S = 30, 5.0  # the Auto Guard icon diagnostic (Batt 2026-10-22, decision 7)
NOENTRY_RED = 25  # red pixels in the 64 x 64 cursor crop (the no-entry cue up to @8.5; logged only)
# dungeon@8.6 (xmas_dun02, 2026-11-06): the no-entry sign is read by its RING, not by any red. The
# old count (R >= 170, G and B <= 90 anywhere in the crop) also counts xmas_dun02's ORANGE floor
# tiles (G 53-90): pilot p2 + X2 carved 254 of 894 walk decisions (28 %) as no-entry; their 5 x 5
# carves sealed the edge loop (12 dead-end Fly Wings in 35 min). The ring (cursor@1's 1,170 ring
# grabs on the NAS): PURE red (G and B <= 40) on a circle of radius 18 px centred (+4.5, +11.5) px
# from the hotspot (fit |d - R| p95 0.93 px). Its score is the pure-red pixels within RING_BAND of
# that circle at the best centre within +-RING_SHIFT px; pure red just OUTSIDE the circle (a red
# carpet, a stocking) refuses it. Design data: cursor@1's ring grabs score >= 188 with 0 outside,
# its 13,800 other grabs 0; X2's recorded frames: 6 rings 194-214 with 0 outside, the red scenery
# <= 101, or >= 16 outside (docs/planning/rogue-xmas02.md 4G).
RING_PURE_R, RING_PURE_GB = 170, 40  # the ring's red: R >= 170, G and B <= 40 (crops are BGR)
RING_CX, RING_CY, RING_R = 4.5, 11.5, 18.0  # the circle's centre from the hotspot, its radius (px)
# on the circle: |d - R| <= RING_BAND; just outside it: RING_GAP < d - R <= RING_OUTER
RING_BAND, RING_GAP, RING_OUTER = 2.5, 3.5, 10.0
RING_SHIFT = 3  # px searched around the expected centre (RDP rounding, the pointer's own pixel)
RING_IN_MIN, RING_OUT_MAX = 120, 20
RING_HALF = 40  # the ring crop: 80 x 80 around the hotspot (the circle reaches 32 px below it)
RING_DIAG_MAX = 40  # crops kept (the session dir) where the ring and the old red count disagree
NOENTRY_CARVE_R = 0  # dungeon@8.6: a no-entry names ONE cell (the stall carve keeps CARVE_R)
UNCARVE_MIN_S = 60.0  # dungeon@8.6: a dead end forgets the carves first (once per this), then flies
COLUMN_DY_MIN = 6  # dungeon@8.7: a walk target >= this far STRAIGHT north moves (column_dodge)
CARVE_R = 2  # Amendment C: a stalled walk target's 5 x 5 leaves the route grid for the run
MR_WALK_AHEAD = 3  # MELEE-RING (Batt 13:4x): short walk legs ("moving slowly") ...
MR_AFTER_HIT_S = 0.3  # ... and while locked, ONE ring cell is read within this of our own hit
IDLE_MAX_S = 45.0  # Amendment D: searching this long with no walk click and no move = stuck


def dead_end(skips_in_row: int, n_waypoints: int) -> bool:
    """PURE (gef10-idle-study.md 4c / 6.2): a full lap of route-less patrol skips in a row = a dead
    end: no waypoint routes from our cell (c7: a whole-run carve sealed the pocket's only exit; it
    skipped 412 times and stood 45.8 s until the IDLE_MAX_S watchdog). Fly at once instead."""
    return n_waypoints > 0 and skips_in_row >= n_waypoints


def dead_end_step(carved_n: int, since_uncarve_s: float) -> str:
    """PURE (dungeon@8.6): what a dead end does. The carves are the run's own guesses on top of
    the map data (a stall's 5 x 5, a no-entry's cell); while any exist and none were forgotten
    within UNCARVE_MIN_S, the dead end forgets them and re-plans on the map's grid ("uncarve");
    else the Fly Wing as before ("fly"). p2 / X2: the false no-entry carves sealed the loop."""
    return "uncarve" if carved_n > 0 and since_uncarve_s >= UNCARVE_MIN_S else "fly"


STUCK_STALLS = 4  # Amendment C: this many stalls within 60 s at one cell = stuck -> a Fly Wing
STALL_CLICKS = 2  # walk clicks from the same cell without moving: turn, re-plan, scan ring 1
BOX_EVERY_S, BOX_FRESH_S = 1.0, 1.5  # the box watcher's rhythm and how old a box may be
BOX_IGNORE_AFTER, BOX_SPOT_R = 2, 1  # dungeon@5 (decision 4): misses within 1 cell -> ignored
BOX_GRID: list[tuple[int, int]] = [(dx, dy) for dx in range(-12, 13) for dy in range(-10, 11)]
SELF_BOX = (610, 268, 672, 375)  # client px: our own drawn Crusader (a box centred here is us)
BOX_NEAR_PX = 110.0  # a box's foot within this of our cell's point = "near" (~3 cells across)
# dungeon@8.8 (rogue-xmas02.md 4M, after p6: 16 of 19 box fights scanned only the 8 cells around
# us while the boxed monster stood 1.5-3.5 cells away, seen on a camera that was still walking):
# a box fight first waits for our walk to end, takes a box grabbed AFTER that (a still camera),
# and hovers THAT box; a SWORD there is the strike. Else the ring scan, as before. --box-strike.
BOX_SETTLE_S = 1.2  # after our last walk click: a 7-cell path at 150 ms a cell has ended
BOX_TARGET_WAIT_S = 1.8  # the wait for a box grabbed after the settle (rhythm 1 s + a detection)
BOX_TARGET_PX = 220.0  # that box's foot within this of our cell's point (~6 cells)
CALM_S = 2.0  # dungeon@4: no hit on us for this long = between fights (H's calm Heal)
REGEN_STOP = 0.50  # Amendment I: at this weight share the server gives NO natural HP / SP regen
WEIGHT_RED_MIN = 50  # Amendment I: red px on the weight line = the client's own >= 50 % colour
# (measured 2026-10-22 21:0x on 4 frames: 0 below 50 %, 281 at 2,110-2,115 / 4,150; the digit
# reader returns None on the red line: "no_label")
PLANT_UP = 12  # px above a White Plant's cell point: its body (a small sprite)
PLANT_NEAR, PLANT_HOVERS, PLANT_EVERY_S = 7, 16, 120.0  # the White Plant sweep (dungeon@4)
WP_TOL = 2  # a patrol waypoint counts as reached within this many cells (map_routes.reached)
# --rest house (docs/planning/gef10-house-rest.md; off by default): a house trip only when the
# nearest sealed door's approach is at most HOUSE_MAX_STEPS route-grid steps away (41 of the 47
# rest decisions of the 8.x runs a2-a8 / a5b / b1) and HP >= HOUSE_MIN_HP (B's potion line: a
# lower HP does not walk 100 cells through orcs); else today's field rest
HOUSE_MAX_STEPS = 120
HOUSE_MIN_HP = 0.30
HOUSE_WALK_MAX_S = 90.0  # the approach not reached in this long -> today's field rest
HOUSE_STILL_S = 0.8  # the door click only from a standstill (the readout unchanged this long)
HOUSE_DOOR_TRIES = 2  # door clicks with no load gap -> today's field rest
HOUSE_REST_MAX_S = 600.0  # inside: stand and leave after this long even if not full
HOUSE_READ_S = 1.0  # inside: one HP / readout check this often
HOUSE_HP_FALL = 2  # inside: the HP percent falling this many points = damage inside: STOP
HOUSE_UNREAD_S = 10.0  # inside: Basic Info unreadable this long = an unknown state: STOP


# --- pure decisions ----------------------------------------------------------------------------


@dataclass
class Sustain:
    hist: deque[tuple[float, float]] = field(default_factory=lambda: deque(maxlen=64))
    pots: list[float] = field(default_factory=list)
    pot_frac: float | None = None
    fly: float = -1e9
    heal: float = -1e9
    healing: bool = False


def rate_hp_s(hist: Sequence[tuple[float, float]], now: float, win: float = 2.0,
              max_hp: float = MAX_HP) -> float | None:  # fmt: skip
    """PURE: HP lost per second over the last ``win`` s (survive.rate_hp_s)."""
    pts = [(t, f) for t, f in hist if now - win <= t <= now]
    if len(pts) < 2 or pts[-1][0] - pts[0][0] < win / 2:
        return None
    (t0, f0), (t1, f1) = pts[0], pts[-1]
    return (f0 - f1) * max_hp / (t1 - t0)


def sustain(st: Sustain, now: float, hp: float, sp: float | None, strat: Mapping[str, Any],
            calm: bool = False) -> list[tuple[str, str]]:  # fmt: skip
    """PURE: the sustain keys to press now with why: the escape first (alone), then a potion,
    then Heal. ``hp`` / ``sp`` are shares (0..1); ``st`` is updated for what is returned.
    ``calm`` (no hit on us for CALM_S, not fighting): H's between-fights Heal may fire."""
    st.hist.append((now, hp))
    rate = rate_hp_s(st.hist, now, max_hp=float(strat.get("max_hp", MAX_HP)))
    if now - st.fly >= 3.0:
        why = None
        if hp < strat["fly_below"]:
            why = f"hp {hp:.2f}"
        elif rate is not None and rate > strat["fly_rate"] and hp < strat["fly_rate_below"]:
            why = f"rate {rate:.0f} at hp {hp:.2f}"
        if why:
            st.fly = now
            return [("fly", why)]
    out: list[tuple[str, str]] = []
    if hp < strat["potion_below"]:
        recent = [t for t in st.pots if now - t <= 2.0]
        rose = st.pot_frac is not None and hp > st.pot_frac + 0.01
        if (not st.pots or now - st.pots[-1] >= 0.7 or rose) and len(recent) < 3:
            st.pots.append(now)
            st.pot_frac = hp
            out.append(("potion", f"hp {hp:.2f}"))
            return out  # a potion this tick: Heal waits for its effect
    hb = strat.get("heal_below")
    if hb is not None and sp is not None and sp >= strat["heal_sp_min"]:
        if hp < hb:
            st.healing = True
        if st.healing and hp >= strat["heal_until"]:
            st.healing = False
        if st.healing and now - st.heal >= HEAL_GAP_S:
            st.heal = now
            out.append(("heal", f"hp {hp:.2f} sp {sp:.2f}"))
    elif hb is not None:
        st.healing = False
    cb_ = strat.get("heal_calm_below")
    if (not out and calm and cb_ is not None and sp is not None and hp < cb_
            and sp >= strat["heal_calm_sp_min"] and now - st.heal >= HEAL_GAP_S):  # fmt: skip
        st.heal = now
        out.append(("heal", f"calm hp {hp:.2f} sp {sp:.2f}"))
    return out


def rest_wanted(strat: Mapping[str, Any], hp: float, sp: float | None) -> bool:
    """PURE: after a fight, go and sit? B: HP under rest_below. C: the same, only when SP cannot
    pay for a Heal (Heal covers it otherwise). A never rests. H (decision 1b): HP under 80 % OR
    SP under 30 %."""
    rb = strat.get("rest_below")
    if "rest_sp_below" in strat:
        return (rb is not None and hp < rb) or (sp is not None and sp < strat["rest_sp_below"])
    if rb is None or hp >= rb:
        return False
    return not (strat.get("heal_below") is not None and sp is not None
                and sp >= strat["heal_sp_min"])  # fmt: skip


def rest_done(strat: Mapping[str, Any], pct: float | None, sp_pct: float | None) -> bool:
    """PURE: stand up? HP full (H: >= 99 %, as read) and, for H, SP back to rest_until_sp."""
    if "rest_until_sp" not in strat:
        return pct is not None and pct >= 100
    return (pct is not None and pct >= 99 and sp_pct is not None
            and sp_pct >= 100 * strat["rest_until_sp"])  # fmt: skip


def nearest_in(mask: Any, here: Cell, max_r: int = 40) -> Cell | None:
    """PURE: the nearest cell of ``mask`` (Chebyshev rings outward), ties by (x, y); None if none
    within ``max_r``. dungeon@4: back INTO the search area after a rest outside it."""
    h, w = mask.shape
    for r_ in range(0, max_r + 1):
        ring_ = [(here[0] + dx, here[1] + dy) for dx in range(-r_, r_ + 1)
                 for dy in range(-r_, r_ + 1) if max(abs(dx), abs(dy)) == r_]  # fmt: skip
        hits = sorted(c for c in ring_ if 0 <= c[0] < w and 0 <= c[1] < h and mask[c[1], c[0]])
        if hits:
            return hits[0]
    return None


def plant_cells(area_: tuple[int, int, int, int], here: Cell, walkable: Any,
                n: int = PLANT_HOVERS) -> list[Cell]:  # fmt: skip
    """PURE: a White Plant spawn area's walkable cells on a 2-cell lattice, nearest to us first,
    at most ``n`` (a plant sprite is ~1-1.5 cells wide: the lattice covers the area)."""
    x, y, xs, ys = area_
    h, w = walkable.shape
    cells = [(cx, cy) for cx in range(max(0, x - xs), min(w, x + xs + 1))
             for cy in range(max(0, y - ys), min(h, y + ys + 1))
             if (cx - x) % 2 == 0 and (cy - y) % 2 == 0 and walkable[cy, cx]]  # fmt: skip
    return sorted(cells, key=lambda c: (cheb2(c, here), c))[:n]


def overweight_red(frame_bgr: Any) -> bool:
    """PURE (Amendment I): the client draws the weight line in RED at >= 50 % weight (no natural
    regen); the digit reader cannot read it (None), the colour itself is the signal. The line is
    Basic Info's (poring_env.weight.rect_at(): x, y, w, h in the game region)."""
    from poring_env import weight as wt

    x, y, w, h = wt.rect_at()
    a = np.asarray(frame_bgr)[y : y + h, x : x + w, :3].astype(np.int16)
    b, g, r_ = a[..., 0], a[..., 1], a[..., 2]
    return int(((r_ >= 150) & (g <= 90) & (b <= 90)).sum()) >= WEIGHT_RED_MIN


CONFIRM_S = 1.0  # X1b round 2: a light-strip (fallback) read counts only when confirmed this soon


class PosConfirm:
    """The minimap readout as the runner uses it (rogue-xmas02 X1b round 2). A BASE read counts as
    before. A read by selfpos's opaque-glyph fallback (mode "light": a pale or mixed strip) counts
    only when the previous read of any mode, at most CONFIRM_S earlier, agrees within the walk's
    reach (WALK_S_PER_CELL a cell, +1): a frame caught while a digit changes lasts one codec
    frame, and two reads 0.3 s apart do not both catch it -- so a one-frame misread can never
    move ``here`` (nor trip the position-jump hard bar). Thread-safe: the main thread's
    read_here() and the HP-read loop share one."""

    def __init__(self) -> None:
        self.last: tuple[float, Cell] | None = None
        self.unconfirmed = 0
        self._lock = threading.Lock()

    def accept(self, t: float, rd: Any) -> Cell | None:
        if rd.xy is None:
            return None
        p_ = (int(rd.xy[0]), int(rd.xy[1]))
        with self._lock:
            prev, self.last = self.last, (t, p_)
            if getattr(rd, "mode", "base") != "light":
                return p_
            dt = t - prev[0] if prev is not None else math.inf
            if (
                prev is not None
                and dt <= CONFIRM_S
                and max(abs(p_[0] - prev[1][0]), abs(p_[1] - prev[1][1]))
                <= dt / WALK_S_PER_CELL + 1
            ):
                return p_
            self.unconfirmed += 1
            return None


def read_outcome(rd: Any, pos: Cell | None) -> str:
    """PURE (2026-11-06, logging only): this HP read's readout outcome -- "settle" (no read after a
    Fly Wing), "base" / "light" (accepted), "unconfirmed" (a light read PosConfirm held back), or
    "<mode>:<reason>" for a read that failed ("light_failed:<the fallback's reason>")."""
    if rd is None:
        return "settle"
    if rd.xy is None:
        mode = getattr(rd, "mode", "base")
        why = getattr(rd, "light_reason", None) if mode == "light_failed" else None
        return f"{mode}:{why or rd.reason}"
    return str(getattr(rd, "mode", "base")) if pos is not None else "unconfirmed"


def is_jump(here: Cell, p_: Cell, since_s: float) -> bool:
    """PURE (4.00 Amendment J, pi3 23:56: a plant strike 13 cells off walked the Crusader 21 cells
    while no position was read -- a false map-change bar, 0 other-map changes in the packets): a
    position change is a JUMP only above JUMP_CELLS AND above what our walk covers since the last
    read (150 ms a cell + WALK_SLACK). A map change teleports at once, so it still trips."""
    d = max(abs(p_[0] - here[0]), abs(p_[1] - here[1]))
    return d > max(JUMP_CELLS, since_s / WALK_S_PER_CELL + WALK_SLACK)


def loot_order(changed: Sequence[tuple[float, Cell]], plan: set[Cell], here: Cell,
               empty: Mapping[Cell, float], kills: Sequence[tuple[Cell, float]]
               ) -> list[tuple[Cell, str]]:  # fmt: skip
    """PURE (loot v2, decision 4): the cells to hover, in order -- the CHANGED cells first (where
    items fell; nearest first, then the larger change), then the plain list cells (nearest first).
    A cell hovered EMPTY is skipped unless a kill within 2 cells of it came after that hover (a new
    drop can land there)."""

    def stale_empty(c: Cell) -> bool:
        t_e = empty.get(c)
        if t_e is None:
            return False
        return not any(cheb2(c, g) <= 2 and t_k > t_e for g, t_k in kills)

    out: list[tuple[Cell, str]] = []
    seen: set[Cell] = set()
    for _d, c in sorted(changed, key=lambda dc: (cheb2(dc[1], here), -dc[0], dc[1])):
        if c not in seen and not stale_empty(c):
            out.append((c, "changed"))
            seen.add(c)
    for c in sorted(plan, key=lambda c: (cheb2(c, here), c)):
        if c not in seen and not stale_empty(c):
            out.append((c, "list"))
            seen.add(c)
    return out


def route(base: Any, carved: Any, here: Cell, goal: Cell) -> list[Cell] | None:
    """A* on ``base`` minus the ``carved`` cells, with OUR cell held and the base grid restored
    within CARVE_R of it (standing there proves the carved block reachable; hunt_flow's
    approach_path holds our cell for the same reason). Amendment D: without it, run 2 stood 20 min
    at 45,60 -- every route from inside a stall's carve came back None."""
    import hunt_core as hc

    b = np.asarray(base, dtype=bool)
    g = b & ~np.asarray(carved, dtype=bool)
    h, w = g.shape
    y0, y1 = max(0, here[1] - CARVE_R), min(h, here[1] + CARVE_R + 1)
    x0, x1 = max(0, here[0] - CARVE_R), min(w, here[0] + CARVE_R + 1)
    g[y0:y1, x0:x1] = b[y0:y1, x0:x1]
    g[here[1], here[0]] = True
    return hc.astar(g, here, goal)  # type: ignore[no-any-return]


def carve(mask: Any, c: Sequence[int], r_: int) -> None:
    """The (2 r_ + 1)^2 square around ``c`` set in ``mask`` (clipped to the map)."""
    h, w = mask.shape
    mask[max(0, c[1] - r_) : min(h, c[1] + r_ + 1), max(0, c[0] - r_) : min(w, c[0] + r_ + 1)] = (
        True
    )


def forward_cells(here: Cell, nxt: Cell) -> list[Cell]:
    """PURE (MELEE-RING): the ring-1 cells AHEAD of our walk, as offsets: the step toward ``nxt``
    and its two 45-degree neighbours (the cells a monster meeting us is drawn on first)."""
    dx = (nxt[0] > here[0]) - (nxt[0] < here[0])
    dy = (nxt[1] > here[1]) - (nxt[1] < here[1])
    if (dx, dy) == (0, 0):
        return []
    order = [(0, 1), (1, 1), (1, 0), (1, -1), (0, -1), (-1, -1), (-1, 0), (-1, 1)]
    i = order.index((dx, dy))
    return [order[i], order[(i + 1) % 8], order[(i - 1) % 8]]


def queue_add(queue: list[dict[str, Any]], cell: Cell, t: float) -> bool:
    """PURE (MELEE-RING): a SWORD cell joins the queue once (by absolute cell); True if added."""
    if any(tuple(q["cell"]) == tuple(cell) for q in queue):
        return False
    queue.append({"cell": tuple(cell), "t": t})
    return True


def turn_heading(st: dict[str, Any]) -> None:
    """The search heading turned by 90 degrees (a wall the client shows, or a stall)."""
    st["ang"] = float(st.get("ang", 0.0)) + math.pi / 2


def nearest_rel(uv: Any, grid: Sequence[Cell], px: Sequence[float]) -> Cell:
    """PURE: the grid cell (relative to us) whose projected point is nearest to ``px``."""
    uv_ = np.asarray(uv, dtype=float)
    d = np.hypot(uv_[:, 0] - px[0], uv_[:, 1] - px[1])
    return tuple(grid[int(np.argmin(d))])  # type: ignore[return-value]


@dataclass
class BoxSpots:
    """PURE (Batt 2026-10-23, decision 4: "ignore a box spot that gave no SWORD twice"; 4.00's ci5:
    the v1 box at the Black Mushroom spawn started 120 fights no ring scan could strike). A box
    spot is the map cell under a box's foot; a box-started fight with no strike is a MISS there.
    A spot is ignored once the misses within ``r`` cells (Chebyshev; the foot jitters) reach
    ``after`` -- by the box trigger only: a monster that hits us still starts a fight."""

    after: int = BOX_IGNORE_AFTER
    r: int = BOX_SPOT_R
    misses: Counter[Cell] = field(default_factory=Counter)

    def _near(self, spot: Cell) -> int:
        return sum(n for c, n in self.misses.items()
                   if max(abs(c[0] - spot[0]), abs(c[1] - spot[1])) <= self.r)  # fmt: skip

    def miss(self, spot: Cell) -> int:
        self.misses[(int(spot[0]), int(spot[1]))] += 1
        return self._near(spot)

    def ignored(self, spot: Cell) -> bool:
        return self.after > 0 and self._near(spot) >= self.after


def self_box(cx: float, cy: float) -> bool:
    """PURE: a box centred on OUR drawn Crusader (the camera centres it: foot (641, 362), head ~280)
    -- v1 never saw a Crusader in training and boxes it as a monster (3.98 run 1, 12:11)."""
    x0, y0, x1, y1 = SELF_BOX
    return x0 <= cx <= x1 and y0 <= cy <= y1


def red_px(crop: Any) -> int:
    """PURE: the no-entry ring's red pixels in a cursor crop (BGR): R high, G and B low."""
    a = np.asarray(crop)[..., :3].astype(np.int16)
    b, g, r_ = a[..., 0], a[..., 1], a[..., 2]
    return int(((r_ >= 170) & (g <= 90) & (b <= 90)).sum())


def pure_red(crop: Any) -> Any:
    """PURE (dungeon@8.6): the no-entry ring's own red in a BGR crop (a bool mask)."""
    a = np.asarray(crop)[..., :3].astype(np.int16)
    return (a[..., 2] >= RING_PURE_R) & (a[..., 1] <= RING_PURE_GB) & (a[..., 0] <= RING_PURE_GB)


def ring_score(crop: Any, hx: float, hy: float) -> tuple[int, int, int, int]:
    """PURE (dungeon@8.6): the no-entry ring in a BGR crop whose hotspot is pixel (hx, hy):
    (on, out, dx, dy) -- the pure-red pixels on the ring's circle at the best centre within
    +-RING_SHIFT px of the expected one, the pure-red pixels just outside that circle, the shift."""
    ys, xs = np.nonzero(pure_red(crop))
    best = (0, 0, 0, 0)
    if len(xs) == 0:
        return best
    for dy in range(-RING_SHIFT, RING_SHIFT + 1):
        for dx in range(-RING_SHIFT, RING_SHIFT + 1):
            d = np.hypot(xs - (hx + RING_CX + dx), ys - (hy + RING_CY + dy))
            on = int((np.abs(d - RING_R) <= RING_BAND).sum())
            if on > best[0]:
                out = int(((d > RING_R + RING_GAP) & (d <= RING_R + RING_OUTER)).sum())
                best = (on, out, dx, dy)
    return best


def ring_seen(score: Sequence[int]) -> bool:
    """PURE (dungeon@8.6): a ring_score is the no-entry sign."""
    return score[0] >= RING_IN_MIN and score[1] <= RING_OUT_MAX


def ring(r_: int) -> list[Cell]:
    """PURE: the cells at Chebyshev distance r_ around (0, 0), the orthogonal ones first (a melee
    attacker stands there more often than on a diagonal), then clockwise from north."""
    cells = [(dx, dy) for dx in range(-r_, r_ + 1) for dy in range(-r_, r_ + 1)
             if max(abs(dx), abs(dy)) == r_]  # fmt: skip
    return sorted(cells, key=lambda c: (abs(c[0]) + abs(c[1]),
                                        math.atan2(c[0], c[1]) % (2 * math.pi)))  # fmt: skip


def ring1(rel: Sequence[int]) -> bool:
    """PURE (--walk-stop): one of the eight cells beside us (a melee strike attacks in place)."""
    return max(abs(rel[0]), abs(rel[1])) == 1


def walked_now(shifts: Sequence[tuple[float, float]], px: float = WALK_STOP_PX,
               n: int = WALK_STOP_N) -> bool:  # fmt: skip
    """PURE (--walk-stop): the last ``n`` scene shifts since the click are all >= ``px``."""
    return len(shifts) >= n and all(math.hypot(dx, dy) >= px for dx, dy in shifts[-n:])


def in_self_box(u: float, v: float, u0: float, v0: float) -> bool:
    """PURE (--self-recheck): (u, v) lies on our own sprite, whose feet are at (u0, v0)."""
    return abs(u - u0) <= SELF_HALF_W and v0 - SELF_UP <= v <= v0 + SELF_DOWN


def drop_false(cells: Sequence[Cell], false_rel: Mapping[Cell, float], now: float,
               keep_s: float = FALSE_REL_S) -> list[Cell]:  # fmt: skip
    """PURE (--walk-stop): the scan's cells without those whose strike walked within ``keep_s``."""
    return [c for c in cells if now - false_rel.get(tuple(c), -1e9) > keep_s]


def hp_dropped(hist: Sequence[tuple[float, float]], now: float) -> bool:
    """PURE: the HP percent fell >= HP_DROP_PTS within HP_DROP_S (a hit the log did not show)."""
    pts = [f for t, f in hist if now - HP_DROP_S <= t <= now]
    return len(pts) >= 2 and (max(pts) - pts[-1]) * 100 >= HP_DROP_PTS - 1e-6


def pickup_seen(rec: Mapping[str, float]) -> bool:
    """PURE: the client drew its PICKUP hand (and no SWORD) at the hovered point."""
    import cursor_sword as csw

    return rec.get("pickup", 0.0) >= PICKUP_MIN and rec.get("sword", 0.0) < csw.SWORD_MIN


def cheb2(a: Sequence[int], b: Sequence[int] | None) -> int:
    return 0 if b is None else max(abs(a[0] - b[0]), abs(a[1] - b[1]))


def rest_sit_why(spot: Cell | None, at_spot: bool, waited_s: float) -> str | None:
    """PURE: why to sit now in the REST mode, or None (keep walking to the spot).
    4.03 Amendment C (2026-10-24): a map with NO rest spot sits where it stands at once -- before,
    the missing route sent the mode back to "search" every read, so it never sat (t1: 782 rest_go
    -> rest_route cycles, the walk's goal reset on each)."""
    if spot is None:
        return "no rest spot: sit where we stand"
    if at_spot:
        return "at rest spot"
    if waited_s > REST_WALK_MAX_S:  # Amendment B (3.98)
        return "rest spot not reached"
    return None


def nearest_spot(spots: Sequence[Cell], here: Cell) -> Cell | None:
    return min(spots, key=lambda s: max(abs(s[0] - here[0]), abs(s[1] - here[1])), default=None)


def column_dodge(here: Cell, c: Cell, nxt: Cell | None,
                 usable: Callable[[Cell], bool]) -> tuple[Cell, str | None]:  # fmt: skip
    """PURE (dungeon@8.7): a walk target STRAIGHT NORTH of us (our column, >= COLUMN_DY_MIN cells
    up) is moved one cell sideways -- toward ``nxt`` (a later path cell) first -- or, with neither
    side cell usable, to COLUMN_DY_MIN - 1 cells up; (target, why), why None = unchanged. p3: the
    client sent no move request for 93 of 95 clicks at (0, +7) and 5 of 6 at (0, +6), but for 32 of
    33 at (+-1, +7) (gef_fild10: (0, +7) 108 / 325 unsent, (+-1, +7) 0 / 88; (0, +5) 0 / 24)."""
    dx, dy = c[0] - here[0], c[1] - here[1]
    if dx != 0 or dy < COLUMN_DY_MIN:
        return c, None
    side = -1 if nxt is not None and nxt[0] < c[0] else 1
    for s in (side, -side):
        alt = (c[0] + s, c[1])
        if usable(alt):
            return alt, f"side{s:+d}"
    short = (c[0], here[1] + COLUMN_DY_MIN - 1)
    if usable(short):
        return short, "short"
    return c, "none"


def walk_target(path: Sequence[Cell], ahead: int, fits: Any) -> tuple[int, Cell] | None:
    """PURE: the farthest path cell at most ``ahead`` steps along that ``fits`` (in view, off
    the UI, no zone crossed), else None."""
    for i in range(min(ahead, len(path) - 1), 0, -1):
        if fits(path[i]):
            return i, path[i]
    return None


def level_lines(level_db: int, hold: int | None) -> list[str]:
    """PURE (Batt 2026-10-26 ~20:5x, hold the Rogue at Base 63): the setup line that brings a DB
    base level above ``hold`` back down (@baselevelup -N: it takes back that level's status points
    and zeroes the EXP, pinned atcommand.cpp); never raises a level."""
    if hold is None or level_db <= hold:
        return []
    return [f"@baselevelup -{level_db - hold}"]


def end_escape_needed(now: float, last_taken: float, hist: Sequence[tuple[float, float]],
                      reason: str) -> bool:  # fmt: skip
    """PURE (dungeon@8.5): a Fly Wing before the end warp -- the run ended (not a death, not a
    hard bar: an unknown UI state gets no key) while a hit came within END_HOT_S, the HP fell
    (hp_dropped), or the last HP share read is under END_FLY_BELOW. c10 (19:57:44): the time box
    stopped every reaction inside a swarm; the ~7 s end warp let it die 0.96 s after run_end."""
    if reason == "death" or reason.startswith("hard_bar"):
        return False
    if now - last_taken < END_HOT_S or hp_dropped(hist, now):
        return True
    return bool(hist) and hist[-1][1] < END_FLY_BELOW


def stock_out(counts: Mapping[int, int | None]) -> int | None:
    """PURE (dungeon@8.4): the first item whose hotbar count reads 0, else None. An unreadable
    count (None) is never 0: the run goes on and the re-read is retried."""
    for item, n in counts.items():
        if n == 0:
            return item
    return None


def swing_engages(tick: float, last_swing: float, swing_floor: float) -> bool:
    """PURE (--miss-cue, dungeon@9.1b): a Miss read within FIGHT_TAKEN_S starts a fight only when
    it was read AFTER the last fight's end (``swing_floor``). 4.05 c6 (9.1) restarted a fight every
    0.1 s from a Miss still drawn after a quiet kill (152 engages from 17 swings in its first
    3 min): the quiet-kill end tests hits only, so each restarted fight ended again at once."""
    return tick - last_swing < FIGHT_TAKEN_S and last_swing > swing_floor


def fixes_of(a: argparse.Namespace) -> dict[str, Any]:
    """PURE: the run's recorded fixes (run_start, manifest); ``rest`` only when it is not the
    default, so a default run's record is the one it was before --rest existed."""
    out: dict[str, Any] = {"plant_sweep": a.plant_sweep, "box_ignore": a.box_ignore,
                           "ag_match": a.ag_match, "walk_trust": a.walk_trust,
                           "npc_guard": getattr(a, "npc_guard", False),
                           "miss_cue": getattr(a, "miss_cue", False)}  # fmt: skip
    if out["miss_cue"]:
        out["miss_cue_rule"] = MISS_CUE_RULE
    if getattr(a, "rest", "spot") != "spot":
        out["rest"] = a.rest
    if getattr(a, "walk_ahead", WALK_AHEAD) != WALK_AHEAD:  # the long legs (idle study 6.1)
        out["walk_ahead"] = a.walk_ahead
    if getattr(a, "walk_through", False):
        out["walk_through"] = True
    if getattr(a, "walk_every", WALK_EVERY_S) != WALK_EVERY_S:  # the walk timer (idle study 4a)
        out["walk_every"] = a.walk_every
    if getattr(a, "walk_stop", False):  # dungeon@9.2 (rogue-xmas02.md 4Q)
        out["walk_stop"] = [WALK_STOP_PX, WALK_STOP_N, WALK_STOP_GAP_S, FALSE_REL_S]
    if getattr(a, "self_recheck", False):  # dungeon@9.3 (rogue-xmas02.md 4R)
        out["self_recheck"] = [SELF_RECHECK_S, SELF_HALF_W, SELF_UP, SELF_DOWN]
    return out


def through_path(leg: Sequence[Cell], leg2: Sequence[Cell] | None) -> list[Cell]:
    """PURE (--walk-through, gef10-idle-study.md 6.1): the leg to waypoint i continued along the
    route to waypoint i + 1, so a walk click is not capped at waypoint i (52-56 % of c5b-c7's
    clicks were: the Rogue stood ~0.4 s at nearly every click)."""
    if not leg2 or len(leg2) < 2 or not leg or leg[-1] != leg2[0]:
        return list(leg)
    return [*leg, *leg2[1:]]


def house_trip_why(frac: float | None, choice: tuple[Any, Cell, int] | None) -> str | None:
    """PURE (--rest house): why NOT to walk to a house now (None = go). HP unread or under
    HOUSE_MIN_HP (walking ~100 cells through orcs at that HP is worse than sitting), or no sealed
    door's approach within HOUSE_MAX_STEPS route-grid steps (``choice``: house_rest.choose's)."""
    if frac is None:
        return "hp unread"
    if frac < HOUSE_MIN_HP:
        return f"hp {frac:.2f} < {HOUSE_MIN_HP}"
    if choice is None:
        return f"no sealed door within {HOUSE_MAX_STEPS} steps"
    return None


def still_since(hist: Sequence[tuple[float, Cell]], now: float) -> float:
    """PURE: how long the position reads have shown the cell they show now (0 without reads):
    ``hist`` = (time, cell) reads, oldest first. The door click waits for HOUSE_STILL_S."""
    if not hist:
        return 0.0
    last = hist[-1][1]
    t0 = hist[-1][0]
    for t, c in reversed(hist):
        if c != last:
            break
        t0 = t
    return now - t0


def house_setup(map_: str, kb_dir: Path, ok: Any, okr: Any, zones: Any,
                cj: Mapping[str, Any], view: tuple[int, int], in_ui: Any,
                ) -> tuple[list[Any], dict[str, set[Cell]], dict[str, tuple[float, float]],
                           dict[str, Any]]:  # fmt: skip
    """--rest house's start-up (gef10-house-rest.md section 4.1), fail closed: SystemExit unless
    the map is gef_fild10 and at least one house passes every check -- its room SEALED
    (house_rest.room_check / usable_why, on in_orcs01's client GAT AND server map cache), an
    approach cell on the route grid ``okr``, and its exit click's pixel (the indoor camera of
    ``cj`` + the GAT) inside the game ``view`` (w, h) and off the UI (``in_ui``). Returns (the
    usable houses, their approach cells, their exit pixels, the run_start record). No input."""
    import house_rest as hr

    from poring_dataset import camera as cam
    from poring_dataset import walkable as wk

    if map_ != hr.FIELD:
        raise SystemExit(f"--rest house refused: {map_} (only {hr.FIELD})")
    try:
        kbw = json.loads((kb_dir / "warps.json").read_text())
        hs_all = hr.houses(kbw)
        gat_in, both_in = wk.load_both(hr.HOUSE_MAP)
        both_f = wk.load_both(map_)[1]
        itab = cam.load_indoor_table()
    except (ValueError, OSError) as e:  # MapSourceError / IndoorTableMissing / no pairing
        raise SystemExit(f"--rest house refused: {e}") from None
    icam = cam.map_camera(dict(cj), hr.HOUSE_MAP, itab)
    if icam is None or not cam.is_indoor(hr.HOUSE_MAP, itab):
        raise SystemExit(f"--rest house refused: no indoor camera for {hr.HOUSE_MAP}")
    gw, gh = view
    fb_ = hr.forbidden_warps(kbw)
    refused: dict[str, str] = {}
    houses_ok: list[Any] = []
    house_ap: dict[str, set[Cell]] = {}
    house_px: dict[str, tuple[float, float]] = {}
    for h_ in hs_all:
        chk = hr.room_check(h_, both_in, fb_)
        why_h = hr.usable_why(chk)
        ap_ = [] if why_h else hr.approach_cells(h_, okr, hr.door_free(ok, both_f, h_.door),
                                                 zones)  # fmt: skip
        if why_h is None and not ap_:
            why_h = "no approach cell on the route grid"
        px_ = None
        if why_h is None:
            px_ = hr.exit_point(icam, gat_in, h_, tuple(chk["click"]))
            if not (30 <= px_[0] < gw - 30 and 30 <= px_[1] < gh - 30 and not in_ui(*px_)):
                why_h = f"the exit click {px_} is off the game view"
        if why_h is not None:
            refused[h_.name] = why_h
            continue
        assert px_ is not None
        houses_ok.append(h_)
        house_ap[h_.name] = set(ap_)
        house_px[h_.name] = px_
    if not houses_ok:
        raise SystemExit(f"--rest house refused: no usable house {refused}")
    rec = {"usable": [h_.name for h_ in houses_ok], "refused": refused,
           "exit_px": {k: [round(v[0], 1), round(v[1], 1)] for k, v in house_px.items()},
           "approach_cells": {k: len(v) for k, v in house_ap.items()},
           "max_steps": HOUSE_MAX_STEPS, "min_hp": HOUSE_MIN_HP}  # fmt: skip
    return houses_ok, house_ap, house_px, rec


# --- live ---------------------------------------------------------------------------------------


class BoxWatch:
    """The THIRD trigger (Batt: "or a v1 box is near"): the CPU detector (v1, or the map's own
    model: unit_detector.for_map, 2026-11-07) on a fresh frame every BOX_EVERY_S in its own
    thread (its worker process does the work), the monster boxes kept with their grab time.
    orcsdun01 zero-shot (orcsdun01-dungeon-prep.md 1): within 3 cells recall 8-14 % pooled,
    precision 96-100 %: a box near us is believed, "no box" means nothing."""

    def __init__(self, screen: Any, region: tuple[int, int, int, int], r: Any,
                 map_name: str | None = None, detector: str = "cpu") -> None:  # fmt: skip
        import threading

        import unit_detector

        # Batt 2026-11-07 (T-11, xmas02-detector.md): a map with its own model gets it, its
        # species collapsed to "monster" before NMS (unit_detector.for_map); else v1 as before
        if detector == "cpu":
            self.det: Any = unit_detector.for_map(map_name)
        else:  # dungeon@8.9 (gpu-live-detector.md option A; Batt 2026-11-07): the SAME model's
            # forward pass on the GPU's detect server, the CPU detector behind it (any failure)
            self.det = unit_detector.for_map_gpu(map_name)
        self.gpu = detector != "cpu"
        self.model = {"onnx": self.det.model.name, "collapse": sorted(self.det.collapse),
                      "threads": unit_detector.THREADS, "detector": detector}  # fmt: skip
        if self.gpu:
            self.model.update(gpu_weights=self.det.weights, gpu_sha256=self.det.info()["sha256"])
        # its OWN grab helper: ro_agent.Screen is one pipe, not thread-safe (pilot 3, 12:02: the
        # main loop's grab and this thread's interleaved and the pipe's framing broke)
        self.screen, self.region, self.r = r.Screen(), region, r
        del screen
        self.lock = threading.Lock()
        self.cond = threading.Condition(self.lock)
        self.last: tuple[float, list[Any]] = (0.0, [])
        # dungeon@8.9 (--box-now): a detection on demand. kick() numbers the request; the loop's
        # next detection takes it (its grab starts after the kick) and records the number
        self.kick_ev = threading.Event()
        self.kick_seq = 0
        self.kick_prefer: str | None = None
        self.meta: dict[str, Any] = {"kick": 0}
        self.paths: Counter[str] = Counter()  # which path gave each detection
        self.halt = threading.Event()
        self.n = 0
        self.n_self = 0
        self.n_skip = 0
        self.th = threading.Thread(target=self._loop, name="box-watch", daemon=True)
        self.th.start()

    def _loop(self) -> None:
        while not self.halt.is_set():
            with self.lock:  # the grab time and the kick it serves, together (fresh_now)
                t = time.monotonic()
                seq, prefer = self.kick_seq, self.kick_prefer
                self.kick_prefer = None
            try:
                img = np.ascontiguousarray(self.screen.grab(*self.region)[1][..., :3])
                raw = self.det.detect(img, prefer=prefer or "gpu") if self.gpu else \
                    self.det.detect(img)  # fmt: skip
                got = [b for b in raw if b.cls == "monster"]
            except Exception:  # noqa: BLE001 -- a dead worker ends the watcher, not the run
                return
            path = str(getattr(self.det, "last_path", "")) or "cpu"
            with self.cond:
                self.last = (t, got)
                self.meta = {"kick": seq, "t": t, "t_done": time.monotonic(), "path": path,
                             "ms": self.det.last_ms, "prefer": prefer,
                             "reason": getattr(self.det, "last_reason", None)}  # fmt: skip
                self.n += 1
                self.paths[path] += 1
                self.cond.notify_all()
            self.kick_ev.wait(max(0.0, BOX_EVERY_S - (time.monotonic() - t)))
            self.kick_ev.clear()

    def kick(self, prefer: str) -> int:
        """Ask for a detection NOW by ``prefer``'s path ("gpu" / "cpu"); its request number."""
        with self.lock:
            self.kick_seq += 1
            self.kick_prefer = prefer
            seq = self.kick_seq
        self.kick_ev.set()
        return seq

    def fresh_now(self, prefer: str, timeout: float) -> dict[str, Any] | None:
        """dungeon@8.9 (rogue-xmas02.md 4N): a detection whose grab starts after this call, by
        ``prefer``'s path, instead of the 1-s rhythm's next one; its meta (grab and done times,
        the path that served, its ms), or None after ``timeout``."""
        seq = self.kick(prefer)
        end = time.monotonic() + timeout
        with self.cond:
            while int(self.meta.get("kick", 0)) < seq:
                left = end - time.monotonic()
                if left <= 0:
                    return None
                self.cond.wait(left)
            return dict(self.meta)

    def wait_fresh(self, since: float, timeout: float) -> bool:
        """dungeon@8.8: wait until the watcher holds boxes from a grab started at or after
        ``since`` (a still camera after our walk ended); False after ``timeout``."""
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            with self.lock:
                t = self.last[0]
            if t >= since:
                return True
            time.sleep(0.05)
        return False

    def near(self, px: Sequence[float], max_px: float, fresh_s: float,
             skip: Any = None) -> tuple[float, ...] | None:  # fmt: skip
        """The nearest fresh monster box whose foot is within ``max_px`` of ``px``; a box whose
        foot ``skip`` (dungeon@5: an ignored box spot) refuses is passed over."""
        with self.lock:
            t, got = self.last
        if time.monotonic() - t > fresh_s:
            return None
        best = None
        for b in got:
            if self_box((b.x0 + b.x1) / 2, (b.y0 + b.y1) / 2):
                self.n_self += 1  # 3.98 run 1 (12:11): v1 boxes our OWN Crusader as a monster
                continue
            if skip is not None and skip(((b.x0 + b.x1) / 2, b.y1)):
                self.n_skip += 1
                continue
            d = math.hypot((b.x0 + b.x1) / 2 - px[0], b.y1 - px[1])
            if d <= max_px and (best is None or d < best[0]):
                best = (d, b.x0, b.y0, b.x1, b.y1)
        return None if best is None else best[1:]

    def stop(self) -> None:
        self.halt.set()
        self.kick_ev.set()
        self.th.join(timeout=3)
        with contextlib.suppress(Exception):
            self.screen.proc.terminate()


def box_flags_refused(box_strike: bool, box_now: bool, detector: str) -> str | None:
    """PURE (dungeon@8.9): --box-now changes the box strike (it needs --box-strike), and the ab
    arms differ only in the box target's fresh detection (they need --box-now)."""
    if box_now and not box_strike:
        return "--box-now needs --box-strike"
    if detector == "ab" and not box_now:
        return "--box-detector ab needs --box-now"
    return None


def box_arm(mode: str, k: int) -> str:
    """PURE (dungeon@8.9): which path the ``k``-th box target's fresh detection takes: the
    --box-detector's own, or with "ab" (the pilot's arms, rogue-xmas02.md 4N) the GPU for even k
    and the CPU for odd k."""
    if mode == "ab":
        return "gpu" if k % 2 == 0 else "cpu"
    return mode


def box_hover_points(box: Sequence[float]) -> list[tuple[float, float]]:
    """PURE (dungeon@8.8): where a box target is hovered, in order: the box's centre (on the
    sprite for any height), then its foot raised by BODY_UP (the defend scan's body point)."""
    x0, y0, x1, y1 = (float(v) for v in box[:4])
    cx = (x0 + x1) / 2
    return [(cx, (y0 + y1) / 2), (cx, y1 - BODY_UP)]


def settle_left(last_walk_click: float, now: float, settle_s: float = BOX_SETTLE_S) -> float:
    """PURE (dungeon@8.8): how long until our last walk has surely ended (0 when it has)."""
    return max(0.0, settle_s - (now - last_walk_click))


def first_item(kinds: Sequence[str]) -> int | None:
    """PURE: the first slot of the ETC tab that is not empty -- every Etc item is loot for the
    Crusader (potions and Fly Wings live in Use, the gear in Eqp)."""
    return next((i for i, k in enumerate(kinds) if k != "empty"), None)


def clear_etc(agent: Any, screen: Any, *, why: str, max_drops: int = 40) -> dict[str, Any]:
    """Drop every stack of the inventory's ETC tab by gm_state.clear_loot's own known path (the
    tab label, two motions; a drag onto open ground; Enter on the quantity prompt matched to its
    OK button first; the tab must change after each drop), r.Stop on anything unexpected."""
    import gm_state as gs
    import ro_agent as r
    import ui_gate

    refs = gs.load_loot_refs()
    ok_ref = np.load(gs.LOOT_DIR / "prompt_ok.npy")
    region = r.game_region()
    out: dict[str, Any] = {"dropped": 0}

    def frame() -> Any:
        return np.ascontiguousarray(r.grab_after(screen, region, r.ns())[..., :3])

    def prompt_shown(f: Any) -> bool:
        x, y, w, h = gs.PROMPT_OK_BOX
        return float(np.abs(gs.to_gray(f)[y : y + h, x : x + w] - ok_ref).mean()) <= gs.PROMPT_MATCH

    def inv_open() -> bool:
        return "inventory" in ui_gate.windows_at_home(
            frame(), ui_gate._registry(ui_gate._require_ready())
        )

    # the chord is a TOGGLE (11:5x: a run of this opened on an open inventory, CLOSED it, and its
    # tab click and drag went to the field): start clear, open, and READ it open before a click
    ui_gate.ensure_clear(agent, screen, why=f"{why}:etc-start")
    r.activate_client(agent, screen)
    agent.chord(*ui_gate.window_keys("inventory"))
    time.sleep(1.0)
    try:
        if not inv_open():
            raise r.Stop(f"clear_etc ({why}): the inventory did not read open after its chord")
        gs._tab(agent, screen, "etc")
        fails = 0
        n = gs.INV_COLS * gs.INV_ROWS
        while out["dropped"] < max_drops:
            if not inv_open():
                raise r.Stop(f"clear_etc ({why}): the inventory closed during the drops")
            f = frame()
            crops = [gs.icon_crop(f, c % gs.INV_COLS, c // gs.INV_COLS) for c in range(n)]
            i = first_item([gs.classify_icon(c, refs)[0] for c in crops])
            if i is None:
                break
            cx, cy = gs.slot_centre(i % gs.INV_COLS, i // gs.INV_COLS)
            x1, y1 = r.at(cx, cy)
            x2, y2 = r.at(*gs.DROP_AT)
            agent.move(x1 + 3, y1 + 3)
            time.sleep(0.15)
            agent.move(x1, y1)
            time.sleep(0.6)
            agent.drag(x1, y1, x2, y2, steps=12)
            time.sleep(1.0)
            f2 = frame()
            if prompt_shown(f2):
                r.activate_client(agent, screen)
                agent.chord("Enter")
                time.sleep(1.0)
                f2 = frame()
                if prompt_shown(f2):
                    raise r.Stop(f"clear_etc ({why}): the quantity prompt stayed open")
            after = [gs.icon_crop(f2, c % gs.INV_COLS, c // gs.INV_COLS) for c in range(n)]
            if not gs.tab_changed(crops, after, i):
                fails += 1
                if fails >= 2:
                    raise r.Stop(f"clear_etc ({why}): slot {i} did not drop twice")
                continue
            out["dropped"] += 1
    finally:
        r.activate_client(agent, screen)
        agent.chord(*ui_gate.window_keys("inventory"))
        time.sleep(1.0)
        ui_gate.ensure_clear(agent, screen, why=f"{why}:etc")
    return out


def load_rest_spots(path: Path = REST_FILE) -> list[Cell]:
    doc = json.loads(path.read_text())
    return [(int(c[0]), int(c[1])) for c in doc["rest_spots"]]


def rest_spots_for(map_name: str, root: Path = ROOT) -> list[Cell]:
    """dungeon@6: config/dungeon/<map>.json's rest spots; REQUIRED on orcsdun01 (dungeon@5), else
    an absent file = no spots (the rest sits where it is: rest_spot_not_reached at once)."""
    path = root / "config" / "dungeon" / f"{map_name}.json"
    if map_name == "orcsdun01" or path.exists():
        return load_rest_spots(path)
    return []


def trust_npcs_for(map_name: str, root: Path = ROOT) -> list[Cell]:
    """--walk-trust (docs/planning/gef10-cursor-unknown.md): every script NPC cell of the map from
    L3 (data/kb/npc_cells.json, generated locally); the option refuses to run (SystemExit) when L3
    does not list the map as complete: an NPC it does not know could not be kept away from."""
    path = root / "data" / "kb" / "npc_cells.json"
    try:
        entry = json.loads(path.read_text())["maps"].get(map_name)
    except (OSError, ValueError, KeyError) as e:
        raise SystemExit(f"--walk-trust refused: {path} unreadable ({e})") from None
    if not entry or not entry.get("complete"):
        raise SystemExit(f"--walk-trust refused: {path} does not list {map_name} as complete")
    return [(int(n["x"]), int(n["y"])) for n in entry.get("npcs", [])]


def steal_sp_pct(max_sp: int) -> int:
    """PURE: the lowest Basic Info SP percent that still pays for a Steal (STEAL_SP) whether the
    client floors or rounds the percent: ceil(100 * (STEAL_SP + 1) / max_sp). Thief: 10."""
    return -(-100 * (STEAL_SP + 1) // max_sp)


def steal_ready(sp_pct: int | None, max_sp: int | None) -> bool:
    """PURE: dungeon@7's gate: open with Steal only when the SP percent was READ and pays for it."""
    return sp_pct is not None and max_sp is not None and sp_pct >= steal_sp_pct(max_sp)


def steal_sp_fall(max_sp: int) -> int:
    """PURE: the SP-percent fall that says a Steal was cast: half of STEAL_SP's share of max SP,
    rounded up (dungeon@8). Thief (112): 5 = STEAL_SP_FALL; Rogue (336): 2."""
    return -(-100 * STEAL_SP // (2 * max_sp))


def steal_cast(sp0: int | None, sp1: int | None, max_sp: int = 112) -> bool:
    """PURE: the SP percent fell by >= steal_sp_fall(max_sp) points = the Steal was cast."""
    return sp0 is not None and sp1 is not None and sp0 - sp1 >= steal_sp_fall(max_sp)


def _sgn(x: int) -> int:
    return (x > 0) - (x < 0)


def steal_ring_order(rel: Cell) -> list[Cell]:
    """PURE: where the target stands after the client walked us to range 1 of it, most likely
    first. A target already within 1 cell stays where it was. Else the walk ends one cell short on
    the target's side: the major axis's neighbour (both axes on a diagonal), then the neighbour
    that also keeps the minor axis's sign (the other path shape), then the rest of ring 1 by
    distance to the first."""
    dx, dy = rel
    ring1 = [(x, y) for x in (-1, 0, 1) for y in (-1, 0, 1) if (x, y) != (0, 0)]
    if max(abs(dx), abs(dy)) <= 1:
        first: list[Cell] = [(dx, dy)] if (dx, dy) != (0, 0) else []
    else:
        sx, sy = _sgn(dx), _sgn(dy)
        pred = (sx if abs(dx) >= abs(dy) else 0, sy if abs(dy) >= abs(dx) else 0)
        first = [pred]
        alt = (sx, sy)
        if alt != pred:
            first.append(alt)
    p0 = first[0] if first else (0, 0)
    rest = sorted((c for c in ring1 if c not in first),
                  key=lambda c: (max(abs(c[0] - p0[0]), abs(c[1] - p0[1])), c))  # fmt: skip
    return first + rest


def steal_forgotten(done: Sequence[tuple[Cell, float]], cell: Cell | None, now: float) -> bool:
    """PURE: True when no target near ``cell`` (Chebyshev <= 2) was stolen from / given up within
    STEAL_FORGET_S (a monster is stolen from ONCE: pc_steal_item's steal_flag)."""
    if cell is None:
        return True
    return not any(
        now - t <= STEAL_FORGET_S and max(abs(c[0] - cell[0]), abs(c[1] - cell[1])) <= 2
        for c, t in done
    )


def stolen(w0: Sequence[int] | None, w1: Sequence[int] | None) -> bool | None:
    """PURE: the weight readout rose (= an item stolen: every stealable item weighs >= 1);
    None when either read failed."""
    if not w0 or not w1:
        return None
    return int(w1[0]) > int(w0[0])


def run(a: argparse.Namespace) -> int:  # noqa: PLR0915, C901
    import bench
    import crusader as cr
    import cursor_sword as csw
    import farm0 as f0
    import gm_vitals as gv
    import hp_percent as hpp
    import hunt
    import hunt_core as hc
    import hunt_flow as hf
    import loot1
    import map_zones as mz
    import record_session as rs
    import ro_agent as r
    import route_preview as rp  # --walk-stop: the scene's scroll after a strike click
    import survive as sv
    import ui_gate
    from anim_region import stand_grid

    from poring_dataset import camera as cam
    from poring_dataset import gat as gatmod
    from poring_env import selfpos

    conf = CHARS_CONF[a.char]  # dungeon@6
    crk = conf.get("data", a.char)  # dungeon@8: the crusader.py data dir (the Rogue is data/thief)
    map_ = a.map
    keys_ = conf["keys"]
    strat = {**STRATEGIES[a.strategy], "max_hp": conf["max_hp"]}
    if a.steal and ("steal" not in keys_ or not conf.get("max_sp")):
        raise SystemExit(f"dungeon@7 refused: --steal for the {a.char}, who has no Steal key / SP")
    why_box = box_flags_refused(a.box_strike, a.box_now, a.box_detector)
    if why_box:
        raise SystemExit(f"dungeon@8.9 refused: {why_box}")
    import nametag

    tag_tpl = nametag.load_templates(nametag.map_dir(ROOT, map_) / "templates.npz")
    bank = a.bank_tags if a.bank_tags is not None else map_ != "orcsdun01"
    if a.engage == "melee_ring":
        # Batt 13:4x: melee-ring strikes EVERY monster in melee range -- only on a map whose every
        # spawning species is a target and that has no script NPC, on the lab server (the hunt
        # block's lint / run start: poring_flow lint/hunt.py; this runner hunts map_ only, on the
        # lab, where the interlock attests the lab rAthena)
        kb_ = ROOT / "data" / "kb"
        npcs_ = (
            json.loads((kb_ / "npc_cells.json").read_text())["maps"].get(map_, {}).get("npcs", [])
        )
        if map_ not in MR_MAPS or npcs_:
            raise SystemExit(f"dungeon@3 refused: melee_ring on {map_} (allowed {sorted(MR_MAPS)}, "
                             f"{len(npcs_)} script NPCs)")  # fmt: skip
    z = np.load(hpp.GLYPHS)
    glyphs = {("%" if k == "pct" else k[1:]): z[k] for k in z.files}
    agz = np.load(sv.AG_ICON)
    ag_t, ag_m = agz["template"], agz["mask"].astype(bool)
    sword_refs = csw.SwordRefs.load()
    digits = selfpos.load_digit_templates()
    pos_ok = PosConfirm()  # X1b round 2: the fallback's reads need a second read's agreement
    gat = gatmod.parse((cam.GAT_DIR / f"{map_}.gat").read_bytes())
    ok = stand_grid(map_, gat)
    kb = ROOT / "data" / "kb"
    warps = json.loads((kb / "warps.json").read_text()).get(map_, [])
    keep = [(w["x"], w["y"], w["span_x"], w["span_y"]) for w in warps]
    try:
        zones = mz.load(map_, shape=ok.shape)
    except mz.ZoneError as e:
        raise SystemExit(f"dungeon@1 refused: map zones: {e}") from None
    if zones is None:
        raise SystemExit(f"dungeon@1 refused: no config/map_zones/{map_}.yaml (the warp zones)")
    area = mz.apply(ok, hc.search_area(ok, keep, margin=10), zones)[1]
    okr = mz.route_grid(ok, zones)
    cut = mz.sealed_off(ok, okr)
    area = hf.main_component(area & ~cut)
    okr = okr & ~cut
    import walk_trust as wtr

    trust_npcs = trust_npcs_for(map_) if a.walk_trust else []  # --walk-trust (off by default)
    guard_npcs = trust_npcs_for(map_) if a.npc_guard else []  # --npc-guard (off by default)
    import miss_cue as mcue

    miss_tpl = None
    if a.miss_cue:  # dungeon@9.1 (docs/planning/gef10-miss-cue.md): the template, or no run
        try:
            miss_tpl = mcue.load_template()
        except OSError as e:
            raise SystemExit(f"dungeon@9.1 refused: no Miss-cue template ({e})") from None
    spots = rest_spots_for(map_)  # dungeon@6: per map (orcsdun01's required, as before)
    for s_ in spots:
        if not okr[s_[1], s_[0]]:
            raise SystemExit(f"dungeon@1 refused: rest spot {s_} is not on the route grid")
    import plant_finder as pfm

    plant_areas = pfm.spawn_areas(map_)  # White Plant spawn lines (static map knowledge)
    patrol = a.search == "patrol"
    rt: Any = None
    wps: list[Cell] = []
    if patrol:
        import map_routes as mroutes

        try:
            routes_ = mroutes.load(map_, shape=ok.shape)
        except Exception as e:  # noqa: BLE001 -- fail closed: no input before this
            raise SystemExit(f"dungeon@4 refused: the patrol route: {e}") from None
        if routes_ is None or not routes_.routes:
            raise SystemExit(
                f"dungeon@4 refused: --search patrol with no config/routes/{map_}.yaml"
            )
        rt = routes_.routes[0]
        wps = [(int(c[0]), int(c[1])) for c in rt.waypoints]
        for c_ in wps:
            if not okr[c_[1], c_[0]]:
                raise SystemExit(f"dungeon@4 refused: waypoint {c_} is not on the route grid")
    start = hunt.start_cell(area, a.seed, near=hf.area_centre(area))
    if patrol and map_ in PATROL_START:
        import map_prep

        start = patrol_start(map_, okr, map_prep.stand_check)
    cj = json.loads((ROOT / "packages/poring_dataset/src/poring_dataset/camera_rdp.json")
                    .read_text())  # fmt: skip
    camera = cam.camera_from_json(cj["camera"])
    gx0, gy0, gw, gh = r.game_region()
    rng = np.random.default_rng(a.seed)
    house_on = a.rest == "house"  # --rest house (docs/planning/gef10-house-rest.md; off by default)
    house_rec: dict[str, Any] | None = None
    house_ap: dict[str, set[Cell]] = {}  # usable house -> its approach cells (the door click's)
    house_px: dict[str, tuple[float, float]] = {}  # usable house -> the exit click's pixel
    houses_ok: list[Any] = []
    if house_on:
        import house_rest as hr

        houses_ok, house_ap, house_px, house_rec = house_setup(
            map_, kb, ok, okr, zones, cj, (gw, gh), loot1.in_ui
        )

    def in_view(u: float, v: float) -> bool:
        return 30 <= u < gw - 30 and 30 <= v < gh - 30 and not loot1.in_ui(u, v)

    def project(here: Cell | None, rel: Sequence[Cell]) -> Any:
        rel_ = np.asarray(rel, dtype=float)
        alt = (gat.relative_altitude(here, rel_) if here is not None
               else np.zeros(len(rel_)))  # fmt: skip
        return camera.project(rel_, alt)

    mr_tag = "-mr" if a.engage == "melee_ring" else ""
    if (a.char, map_) != ("crusader", "orcsdun01"):  # dungeon@6: the session name says who / where
        mr_tag = f"-{a.char}-{map_}{mr_tag}"
    pt_tag = "-patrol" if a.search == "patrol" else ""
    sid = f"{time.strftime('%Y%m%dT%H%M%S')}-demo-dungeon{mr_tag}{pt_tag}-{a.strategy}-{a.label}"
    out = DEMO / sid
    out.mkdir(parents=True, exist_ok=False)
    evf = (out / "events.jsonl").open("a")

    def ev(rec: dict[str, Any]) -> None:
        evf.write(json.dumps({"t_ns": r.ns(), **rec}) + "\n")
        evf.flush()

    counts: Counter[str] = Counter()
    reason = "time_box"
    t0 = r.ns()
    with r.session(f"rule:dungeon-{a.strategy}") as (agent_raw, screen):
        agent_raw.wait_for_human()
        agent = hf.FrameGuard(agent_raw, (gx0, gy0, gw, gh), counts)
        got = cr.check(screen, conf["job"], crk)
        if not got["ok"]:
            raise r.Stop(f"identity {got}")
        ui_gate.ensure_clear(agent_raw, screen, why="dungeon-start")
        # the Battle Log reader (battle_log.py live) reads the SHOWN chat tab: since 2026-11-05 the
        # window has two (Battle Log | Chat, the replies'), and a client restart shows the first
        # while a typed line's check may leave the replies' shown -- so Battle Log is selected here
        import client_layout as cl_

        cl_.select_tab(agent_raw, screen, "battle")
        # the setup (the experimenter's restore, never a decision): full HP / SP, the stock topped
        # up against the DB's last save (an upper bound of what is carried), the weight checked
        name = json.loads((cr.data_dir(crk) / "char.json").read_text())["name"]
        cid = int(r.db_query(f"SELECT char_id FROM `char` WHERE name = {r.sql_str(name)};")[0][0])
        inv = {int(i): int(n) for i, n in r.db_query(
            f"SELECT nameid, amount FROM inventory WHERE char_id = {cid} "
            "AND nameid IN (504, 601);")}  # fmt: skip
        level_db = int(r.db_query(f"SELECT base_level FROM `char` WHERE char_id = {cid};")[0][0])
        setup = [*level_lines(level_db, conf.get("level_hold")), "@heal"]  # the hold, then heal
        p_to = int(strat.get("potions_to") or conf["potions_to"] or POTIONS_TO)
        w_to = int(strat.get("wings_to") or conf["wings_to"])
        if inv.get(504, 0) < p_to:
            setup.append(f"@item 504 {p_to - inv.get(504, 0)}")
        if inv.get(601, 0) < w_to:
            setup.append(f"@item 601 {w_to - inv.get(601, 0)}")
        import gm_state

        fr0 = gm_state._frames(screen)
        w0 = gm_state._weight(fr0)
        red0 = overweight_red(fr0[0])  # Amendment I: the reader is blind to the red (>= 50 %) line
        cleared: dict[str, Any] | None = None
        if (gm_state.weight_share(w0) or 0.0) >= CLEAR_AT or (w0 is None and red0):
            if not conf["clear_etc"]:  # dungeon@6: the Thief's Etc tab holds Batt's target items
                raise r.Stop(f"dungeon@6: weight {w0} at or over {CLEAR_AT} for the {a.char}: "
                             "the setup never drops its Etc tab (a person first)")  # fmt: skip
            cr.gm_line(agent_raw, screen, f"@warp {CLEAR_STAND[0]} {CLEAR_STAND[1]} "
                       f"{CLEAR_STAND[2]}", conf["job"], crk)  # fmt: skip
            time.sleep(3.0)
            bench.close_chat(agent_raw, screen)
            cleared = clear_etc(agent_raw, screen, why="dungeon-setup")
        typed: list[str] = []  # every setup line actually sent, in order (the run_start record)

        def setup_line(cmd: str) -> None:
            typed.append(cmd)
            # 4.04 Amendment A: @heal is idempotent -- chat_guard's skip (a refused 3rd @heal in a
            # row is not typed; the HP / SP are full after the pre-run's heal or the relog)
            got_ = cr.gm_line(agent_raw, screen, cmd, conf["job"], crk,
                              on_refuse="skip" if cmd == "@heal" else "raise")  # fmt: skip
            if not got_.get("typed", True):
                counts["setup_heal_skipped"] += 1
            time.sleep(3.0 if "@warp" in cmd else 0.8)
            if "@warp" in cmd:  # dungeon@8 (4.05 pilot2): a map load can outlast the 3 s, and the
                # next line's identity check then read the LOADING screen and refused (nothing sent)
                t_w = time.monotonic()
                while not cr.check(screen, conf["job"], crk)["ok"]:
                    if time.monotonic() - t_w > WARP_READY_S:
                        raise r.Stop(f"dungeon@8: the identity did not read within {WARP_READY_S}"
                                     " s of the setup's @warp")  # fmt: skip
                    time.sleep(0.5)

        stock: dict[str, Any] | None = None
        stock_watch: tuple[Any, dict[int, int]] | None = None  # 8.4: (templates, item -> slot)
        stock_due: dict[int, float] = {}  # 8.4: item -> when its count is re-read
        stock_tries: dict[int, int] = {}
        true_potions = inv.get(504, 0)
        if conf.get("hotbar_stock"):
            # dungeon@8.3 (Amendment M): the DB lines above are a first guess only; the hotbar's
            # drawn count is the truth -- read it on the stand, top up from it, read it again
            import hotbar_count as hb

            for cmd in setup:
                setup_line(cmd)
            bench.close_chat(agent_raw, screen)
            try:
                tpl = hb.load()
            except OSError as exc:
                raise r.Stop(f"dungeon@8.3: no hotbar digit templates ({exc})") from exc
            slots = {STOCK_ITEMS[k]: hotbar_slot(keys_[k]) for k in STOCK_ITEMS}
            targets = {504: p_to, 601: w_to}

            def read_stock() -> dict[int, int | None]:
                time.sleep(0.8)
                g = hb.gray(np.asarray(r.grab_after(screen, (gx0, gy0, gw, gh), r.ns())))
                return {item: hb.read_count(g, slot, tpl) for item, slot in slots.items()}

            before = read_stock()
            try:
                add = stock_plan(before, targets)
            except ValueError as exc:
                raise r.Stop(f"dungeon@8.3: {exc} {before}") from exc
            for item, n in add.items():
                if n > 0:
                    setup_line(f"@item {item} {n}")
            bench.close_chat(agent_raw, screen)
            after = read_stock()
            short = {i: c for i, c in after.items() if c is None or c < targets[i]}
            stock = {"before": before, "added": add, "after": after}
            if short:
                raise r.Stop(f"dungeon@8.3: the stock is short after the top-up {stock}")
            true_potions = int(after[504] or 0)
            setup = []  # the stand lines are typed; the map lines follow
            stock_watch = (tpl, slots)
        # Amendment I: the potions over the strategy's stock are DRUNK at the stand (its hotkey,
        # paced; outside the measured window): carried weight is loot room before 50 %
        drunk = 0
        excess = true_potions - p_to
        if excess > 0:
            ui_gate.ensure_clear(agent_raw, screen, why="dungeon-setup:drink")
            r.activate_client(agent_raw, screen)
            for _ in range(excess):
                agent_raw.keys(keys_["potion"])
                drunk += 1
                time.sleep(0.35)
            time.sleep(1.0)
        setup.append(f"@warp {map_} {start[0]} {start[1]}")
        if a.clear_map:  # dungeon@8, Amendment A4: the experimenter's step, never the bot's
            setup.append("@killmonster2")
        for cmd in setup:
            setup_line(cmd)
        bench.close_chat(agent_raw, screen)
        r.activate_client(agent_raw, screen)
        time.sleep(1.0)

        def frame() -> Any:
            return np.ascontiguousarray(r.grab_after(screen, (gx0, gy0, gw, gh), r.ns())[..., :3])

        fr1 = gm_state._frames(screen)
        w_ = gm_state._weight(fr1)
        share = gm_state.weight_share(w_)
        if share is None and overweight_red(fr1[0]):  # Amendment I: fail closed on the red line
            raise r.Stop("dungeon@4: the weight line reads RED (>= 50 %) after the setup")
        ev({"kind": "run_start", "strategy": a.strategy, "seed": a.seed, "engage": a.engage,
            "version": VERSION if a.engage == "defend_scan" else MR_VERSION,
            "search": a.search, "route": None if rt is None else rt.id, "loot": a.loot,
            "fixes": fixes_of(a),
            "char": a.char, "steal": a.steal, "bank_tags": bank, "clear_map": a.clear_map,
            "tag_templates": sorted(tag_tpl), "potions_to_char": conf["potions_to"],
            "wings_to": w_to,
            "minutes": a.minutes, "map": map_, "start": list(start), "inv_db": inv,
            "level_db": level_db, "level_hold": conf.get("level_hold"),
            # the judge's MaxHP / MaxSP when no packet gives them (2026-11-05: the Rogue at 99)
            "max_hp": conf["max_hp"], "max_sp": conf.get("max_sp"),
            "setup": typed, "stock": stock, "weight": w_, "weight_before": w0,
            "cleared": cleared,
            "potions_to": p_to, "potions_drunk": drunk,
            "params": strat, "rest_spots": spots,
            **({"house": house_rec} if house_on else {})})  # fmt: skip
        if share is not None and share >= WEIGHT_MAX:
            raise r.Stop(f"dungeon@1: weight {share:.2f} >= {WEIGHT_MAX} (a person first)")
        blt = hf.BattleLogTail(out / "battle_log_live.jsonl", owner_pid=__import__("os").getpid())
        mr = a.engage == "melee_ring"  # Batt 13:4x: the CURSOR engages, the detector does not
        boxes = None
        if a.boxes and not mr:
            boxes = BoxWatch(screen, (gx0, gy0, gw, gh), r,
                             None if a.box_model == "v1" else a.map,
                             "cpu" if a.box_detector == "cpu" else "gpu")  # fmt: skip
            ev({"kind": "box_model", "choice": a.box_model, **boxes.model})
            if boxes.gpu:  # dungeon@8.9: each detection's path + wall time (R3's windows, 4N G1)
                boxes.det.log_path = out / "detections.jsonl"
        queue: list[dict[str, Any]] = []  # MELEE-RING: SWORD cells seen while fighting
        qscan_i = 0
        ours_used = -2e9
        watch_i = 0
        st = Sustain()
        ag_last = sv.load_ag_last()
        ag_absent: float | None = None
        here: Cell | None = None
        last_pos_t = time.monotonic()
        seen_lines = 0
        last_taken = -1e9
        last_swing = -1e9  # dungeon@9.1 (--miss-cue): the last Miss read at our attacker
        swing_floor = -1e9  # 9.1b: the last fight's end; a Miss read before it starts no fight
        last_ours = -1e9
        kills_seen: list[float] = []
        mode = "search"
        lock: dict[str, Any] | None = None
        sitting = False
        rest_since = 0.0
        w_share: float | None = share  # Amendment I: the weight share, re-read every UI_EVERY_S
        red_seen = False  # Amendment I: the weight line drawn red (>= 50 %) on the last read
        rest_skip_t = -1e9
        last_ui = time.monotonic()
        last_walk = 0.0
        walk_st: dict[str, Any] = {"ang": float(rng.uniform(0, 2 * math.pi))}
        walk_from: Cell | None = None
        stall = 0
        carved = np.zeros_like(okr, dtype=bool)  # Amendment C: cells the client would not walk to
        last_uncarve = -1e9  # dungeon@8.6: when a dead end last forgot the carves (dead_end_step)
        idle_pos: Cell | None = None
        idle_since = time.monotonic()
        last_walk_click = time.monotonic()
        stalls_here: list[float] = []
        noentry_n = 0
        goal_path: list[Cell] | None = None
        fly_at = -1e9
        pos_flies = 0  # dungeon@8.1: Fly Wings pressed because the position did not read
        n_reads = 0
        loot_list: list[tuple[Cell, float]] = []  # Batt 11:5x: the GM's cell at EVERY kill
        fight_ref: dict[str, Any] | None = None  # the frame + our cell when the fight began
        t_end = time.monotonic() + a.minutes * 60.0
        # --rest house (gef10-house-rest.md): the trip's closed transition table and its state
        trip = hr.Trip() if house_on else None
        hplan: dict[str, Any] | None = None  # the chosen house, its approach cell, the steps
        house_fb = False  # this rest sits in the field (today's rule): no house in reach
        house_tries = 0  # door clicks of this rest with no load gap
        house_click_t = -1e9  # our last door / exit click (an expected load follows it)
        gap_since: float | None = None  # on the field: Basic Info unread since (house mode only)
        pos_hist: deque[tuple[float, Cell]] = deque(maxlen=32)  # position reads (house mode)

        def press(what: str, why: str) -> None:
            agent_raw.keys(keys_[what])
            counts[what] += 1
            ev({"kind": "press", "what": what, "key": keys_[what], "why": why})
            if stock_watch is not None and what in STOCK_ITEMS:  # dungeon@8.4
                stock_due[STOCK_ITEMS[what]] = time.monotonic() + STOCK_READ_S
                stock_tries[STOCK_ITEMS[what]] = 0

        def click_at(u: float, v: float, why: str) -> None:
            """Every world click of this runner: FrameGuard refuses one off the game frame."""
            if npc_guard_blocks(here, guard_npcs, why):  # dungeon@9.0b, --npc-guard
                counts["npc_guard_refused"] += 1
                ev({"kind": "npc_guard", "why": why, "at": None if here is None else list(here)})
                return
            x, y = gx0 + round(u), gy0 + round(v)
            agent.move(x + 4, y + 3)
            time.sleep(0.02)
            agent.move(x, y)
            time.sleep(0.05)
            agent.click(x, y)
            counts[f"click_{why}"] += 1

        def heal_self(why: str) -> None:
            press("heal", why)
            time.sleep(0.25)
            click_at(SELF_PX[0], SELF_PX[1], "heal_self")

        n_ring_diag = [0]  # dungeon@8.6: ring-vs-red evidence crops kept

        def hover(u: float, v: float) -> dict[str, Any]:
            res = csw.check(agent, screen, sword_refs, gx0, gy0, u, v, wait_s=CURSOR_WAIT_S)
            # pilot 3 (12:0x): the client's NO-ENTRY cursor (its arrow inside a red ring) read
            # "clear" over a cliff, and 4 walk clicks sent no request: the ring decides --
            # dungeon@8.6: the RING itself (ring_score), not any red in the crop (the old count,
            # logged beside it, read xmas_dun02's orange floor as the ring)
            x_r, y_r = gx0 + round(u) - RING_HALF, gy0 + round(v) - RING_HALF
            big = np.ascontiguousarray(
                screen.grab(x_r, y_r, 2 * RING_HALF, 2 * RING_HALF)[1][..., :3])  # fmt: skip
            h0 = RING_HALF - 32  # the old 64 x 64 crop inside it (csw.crop_at's)
            red = red_px(big[h0 : h0 + 64, h0 : h0 + 64])
            sc = ring_score(big, RING_HALF, RING_HALF)
            seen = ring_seen(sc)
            res.update(red=red, ring=list(sc), noentry_ring=seen)
            if seen and res["verdict"] == "clear":
                res["verdict"] = "noentry"
            if (red >= NOENTRY_RED) != seen:
                counts["ring_vs_red"] += 1
                if n_ring_diag[0] < RING_DIAG_MAX:  # evidence crops for the judge's eye
                    n_ring_diag[0] += 1
                    from PIL import Image

                    name_ = f"ring-{n_ring_diag[0]:03d}-red{red}-on{sc[0]}-out{sc[1]}.png"
                    Image.fromarray(big[..., ::-1]).save(out / name_)
            return res

        def above(img: Any, u: float, v: float) -> Any:
            """Where the client draws its lock arrow over the target: an orc's head is higher than
            a Poring's (the pilot's 11:41 strikes never saw it in hunt_flow's 80..15 px band)."""
            a_ = np.asarray(img)
            return a_[max(0, int(v) - ARROW_UP): max(0, int(v) - 10),
                      max(0, int(u) - 50): max(0, int(u) + 50), :3]  # fmt: skip

        wp_st: dict[str, Any] = {"i": None, "last": None, "resume": False, "laps": 0, "fly": -1e9,
                                 "through": None, "skips": 0}  # fmt: skip

        def patrol_goal(h: Cell) -> Cell:
            """--search patrol: the waypoint to walk to (joins the loop at the nearest waypoint
            ahead; after a fight / loot / rest resumes at the NEXT one AHEAD; never turns back)."""
            if wp_st["i"] is None or wp_st["fly"] != fly_at:
                wp_st["i"], wp_st["last"], wp_st["fly"] = mroutes.entry_index(rt, h), None, fly_at
                wp_st["resume"] = False
                ev({"kind": "patrol", "event": "join", "i": wp_st["i"], "at": list(h)})
            elif wp_st["resume"]:
                wp_st["resume"] = False
                i0 = wp_st["i"]
                wp_st["i"] = (mroutes.entry_index(rt, h) if wp_st["last"] is None
                              else mroutes.resume_index(rt, h, wp_st["last"]))  # fmt: skip
                ev({"kind": "patrol", "event": "resume", "from": i0, "i": wp_st["i"],
                    "last": wp_st["last"], "at": list(h)})  # fmt: skip
            for _ in range(len(wps)):
                if not mroutes.reached(h, wps[wp_st["i"]], WP_TOL):
                    break
                wp_st["last"], wp_st["i"] = wp_st["i"], mroutes.next_index(rt, wp_st["i"])
                if wp_st["i"] == 0:
                    wp_st["laps"] += 1
                ev({"kind": "patrol", "event": "reached", "i": wp_st["last"], "next": wp_st["i"],
                    "laps": wp_st["laps"]})  # fmt: skip
            return wps[wp_st["i"]]

        def skip_waypoint(h: Cell) -> None:
            wp_st["skips"] += 1  # route-less skips in a row (dead_end)
            ev({"kind": "patrol", "event": "skip", "i": wp_st["i"], "at": list(h)})
            wp_st["last"], wp_st["i"] = wp_st["i"], mroutes.next_index(rt, wp_st["i"])

        def pass_waypoint(h: Cell) -> None:
            """--walk-through: the leg's waypoint is no longer ahead on the path (walked past, or
            the re-route from our cell no longer goes through it): the next one is the goal."""
            wp_st["last"], wp_st["i"] = wp_st["i"], mroutes.next_index(rt, wp_st["i"])
            if wp_st["i"] == 0:
                wp_st["laps"] += 1
            wp_st["through"] = None
            ev({"kind": "patrol", "event": "reached", "i": wp_st["last"], "next": wp_st["i"],
                "laps": wp_st["laps"], "passed": True, "at": list(h)})  # fmt: skip

        plant_last: dict[int, float] = {}

        escaped = [False]
        last_quick = [0.0]

        def guard_tick() -> bool:
            """Sustain INSIDE a long action (a scan's hovers, a strike's burst): a fresh HP / SP
            read and the strategy's keys at most every QUICK_S; True once we flew away (the caller
            stops). The same Sustain state as the main loop's reads."""
            now_ = time.monotonic()
            if now_ - last_quick[0] < QUICK_S:
                return escaped[0]
            last_quick[0] = now_
            img_ = frame()
            p_, s_ = hpp.read(img_, glyphs), hpp.read(img_, glyphs, hpp.SP_DY)
            ev({"kind": "hp_read", "pct": p_, "sp_pct": s_, "quick": True})
            if p_ is None:
                return escaped[0]
            for what_, why_ in sustain(st, now_, p_ / 100.0, None if s_ is None else s_ / 100.0,
                                       strat):  # fmt: skip
                if what_ == "fly":
                    press("fly", why_)
                    ev({"kind": "escape", "how": "fly", "why": why_, "inside": True})
                    escaped[0] = True
                elif what_ == "heal":
                    heal_self(why_)
                else:
                    press(what_, why_)
            return escaped[0]

        n_shots = [0]
        n_strike = [0]  # dungeon@5: strikes so far (a box-started fight with none = a miss)
        false_rel: dict[Cell, float] = {}  # --walk-stop: ring cells whose strike walked
        n_box_target = [0]  # dungeon@8.9: box targets so far (box_arm alternates by it)
        box_spots = (
            BoxSpots(after=a.box_ignore) if a.box_ignore > 0 else None
        )  # NOT `spots`: the rest spots (4.01 Amendment C)
        box_fight: dict[str, Any] = {}
        spot_logged: dict[Cell, float] = {}

        def box_spot(here_: Cell | None, foot: Sequence[float]) -> Cell | None:
            if here_ is None:
                return None
            c_ = nearest_rel(project(here_, BOX_GRID), BOX_GRID, foot)
            return (here_[0] + c_[0], here_[1] + c_[1])

        def box_fight_done() -> None:
            """dungeon@5 (decision 4): a box-started fight that ended with no strike is a miss."""
            if box_spots is not None and box_fight.get("spot") is not None \
                    and n_strike[0] == box_fight["n0"]:  # fmt: skip
                sp_ = box_fight["spot"]
                n_ = box_spots.miss(sp_)
                ev({"kind": "box_miss", "spot": list(sp_), "misses": n_,
                    "ignored": box_spots.ignored(sp_)})  # fmt: skip
            box_fight.clear()

        n_ag_diag, ag_diag_t = [0], [-1e9]

        steal_done: list[tuple[Cell, float]] = []  # dungeon@6: targets stolen from / given up
        n_tags = [0]
        tags_dir = out / "tags"
        tags_log = None
        if bank:
            tags_dir.mkdir()
            tags_log = (tags_dir / f"cuts-{sid}.jsonl").open("a")

        def read_tag(img_: Any, rel: Cell, u: float, v: float, t_img: int, by: str
                     ) -> str | None:  # fmt: skip
            """dungeon@6: the name tag under the target (the band under its cell's projected point,
            nametag.band's), matched against this map's templates; the band is BANKED (raw, with
            its time and box: nametag's cut record) for the packet-labelled templates."""
            if here is not None:
                uc, vc = (float(x) for x in project(here, [rel])[0])
            else:
                uc, vc = u, v + BODY_UP
            box = type("Box", (), {"x0": uc - 20.0, "x1": uc + 20.0, "y1": vc + TAG_BOTTOM})()
            reg = nametag.band(img_, box)
            m = nametag.letter_mask(reg)
            wb = nametag.word_box(m)
            if wb is None:
                return None
            word, iou = nametag.match(m, tag_tpl) if tag_tpl else (None, 0.0)
            if tags_log is not None and wb[2] - wb[0] >= nametag.MIN_WORD_W:
                n_tags[0] += 1
                name_ = f"tag-{sid}-{n_tags[0]:04d}"
                np.save(tags_dir / f"{name_}.npy", np.asarray(reg))
                tags_log.write(
                    json.dumps(
                        {
                            "name": name_,
                            "t": int(t_img),
                            "u": round(uc, 1),
                            "v": round(vc, 1),
                            "box": [
                                round(box.x0, 1),
                                round(box.y1 - 50, 1),
                                round(box.x1, 1),
                                round(box.y1, 1),
                            ],
                            "word": list(wb),
                            "read": word,
                            "iou": round(iou, 3),
                            "by": by,
                            "rel": list(rel),
                            "here": None if here is None else list(here),
                        }
                    )
                    + "\n"
                )
                tags_log.flush()
            return word

        def sp_now(img_: Any) -> int | None:
            return hpp.read(img_, glyphs, hpp.SP_DY)

        def do_steal(u: float, v: float, rel: Cell, cell_: Cell | None, sp0: int, by: str
                     ) -> tuple[Cell, tuple[float, float]] | None:  # fmt: skip
            """dungeon@7, Batt's steal-first: F3 (Steal) + ONE click on the target. The client
            walks to range 1 and casts; the cast = the SP percent falling (steal_cast). Then the
            target is beside us: ring 1 is hovered for its SWORD (steal_ring_order). Returns the
            strike's new (rel, (u, v)), or None (no cast, or no SWORD beside us: no strike)."""
            w0 = gm_state._weight(gm_state._frames(screen))
            press("steal", f"{by} rel {rel[0]},{rel[1]} sp {sp0}")
            time.sleep(0.12)
            click_at(u, v, "steal")
            counts["steal_try"] += 1
            t_c = time.monotonic()
            sp1, cast = sp0, False
            while time.monotonic() - t_c < STEAL_CAST_MAX_S:
                time.sleep(STEAL_POLL_S)
                sp1_ = sp_now(frame())
                if sp1_ is not None:
                    sp1 = sp1_
                if steal_cast(sp0, sp1, conf["max_sp"]):
                    cast = True
                    break
                if guard_tick():
                    break
            cast_s = round(time.monotonic() - t_c, 2)
            got = None
            if cast:
                time.sleep(STEAL_SETTLE_S)
                got = stolen(w0, gm_state._weight(gm_state._frames(screen)))
                counts["steal_cast"] += 1
                if got:
                    counts["steal_ok"] += 1
            steal_done.append((cell_ if cell_ is not None else (-999, -999), time.monotonic()))
            found = None
            if cast and not escaped[0]:
                found = scan("defend", steal_ring_order(rel), "sword")
            ev({"kind": "steal", "by": by, "rel": list(rel),
                "cell": None if cell_ is None else list(cell_), "sp0": sp0, "sp1": sp1,
                "cast": cast, "cast_s": cast_s, "w0": w0,
                "ok": got, "found": None if found is None else list(found[0])})  # fmt: skip
            if found is None:
                return None
            c_, uv_, _res = found
            return c_, (float(uv_[0]), float(uv_[1]))

        def strike(u: float, v: float, rel: Cell, by: str) -> bool:
            """arm C: click the SWORD point, re-click every BURST_GAP_S until the lock arrow --
            dungeon@4 (decision 5): or until OUR first damage line in the Battle Log; the HP is
            read between the clicks (guard_tick). dungeon@6: the name tag read + banked first.
            dungeon@7: with --steal, ONE Steal first on every monster while the SP pays for it
            (Batt ~16:0x); the strike then goes to where the target stands beside us."""
            ref = frame()
            if bank:
                read_tag(ref, rel, u, v, r.ns(), by)
            if a.steal and by != "plant":
                cell_ = None if here is None else (here[0] + rel[0], here[1] + rel[1])
                sp0 = sp_now(ref)
                if not steal_forgotten(steal_done, cell_, time.monotonic()):
                    counts["steal_skip_done"] += 1
                elif not steal_ready(sp0, conf["max_sp"]):
                    counts["steal_skip_sp"] += 1
                    ev({"kind": "steal_skip", "why": "sp", "sp": sp0, "by": by})
                else:
                    assert sp0 is not None
                    moved = do_steal(u, v, rel, cell_, sp0, by)
                    if escaped[0]:
                        return True
                    if moved is None:
                        return True  # the fight loop's own scan finds the target (lock timeout)
                    rel, (u, v) = moved
                    ref = frame()
            # --walk-stop (dungeon@9.2): a ring-1 strike on a fight path watches the scene scroll
            stop_walk = bool(getattr(a, "walk_stop", False)) and ring1(rel) and by in WALK_STOP_BY
            ref3 = np.ascontiguousarray(np.asarray(ref)[..., :3]) if stop_walk else None
            shifts: list[tuple[float, float]] = []
            walked: float | None = None
            gap = WALK_STOP_GAP_S if stop_walk else BURST_GAP_S
            t_click = r.ns()
            with blt.lock:
                n_lines0 = len(blt.lines)
            click_at(u, v, "strike")
            n_strike[0] += 1
            t_c = time.monotonic()
            n, arrow, dmg = 1, None, None
            cur = ref
            while time.monotonic() - t_c < BURST_MAX_S:
                time.sleep(0.06)
                cur = frame()
                if hf.arrow_new(above(ref, u, v), above(cur, u, v)):
                    arrow = round(time.monotonic() - t_c, 2)
                    break
                with blt.lock:
                    hit_ = any(ln.get("type") == "damage" for ln in blt.lines[n_lines0:])
                if hit_:
                    dmg = round(time.monotonic() - t_c, 2)
                    break
                if stop_walk:
                    cur3 = np.ascontiguousarray(np.asarray(cur)[..., :3])
                    shifts.append(rp.scene_shift(ref3, cur3))
                    if walked_now(shifts):
                        walked = round(time.monotonic() - t_c, 2)
                        false_rel[(int(rel[0]), int(rel[1]))] = time.monotonic()
                        counts["walk_stop"] += 1
                        break
                if guard_tick():
                    break
                if n < BURST_MAX and time.monotonic() - t_c >= n * gap:
                    click_at(u, v, "strike_burst")
                    n += 1
            if n_shots[0] < MAX_SHOTS:  # evidence frames for the judge's eye (the session dir)
                n_shots[0] += 1
                from PIL import Image

                Image.fromarray(np.asarray(cur)[..., ::-1]).save(
                    out / f"strike-{n_shots[0]:03d}.jpg", quality=80)  # fmt: skip
            # stamped at the FIRST click (the judge's landing window starts there), the end
            # time beside it (pilot 11:42: the end stamp put the attack before the window)
            ev({"t_ns": t_click, "t_end_ns": r.ns(), "kind": "strike", "u": round(u, 1),
                "v": round(v, 1), "rel": list(rel),
                "clicks": n, "arrow_s": arrow, "damage_s": dmg, "walked_s": walked,
                "shift": [round(x_, 1) for x_ in shifts[-1]] if shifts else None,
                "end": "arrow" if arrow is not None else "damage" if dmg is not None else
                "walked" if walked is not None else ("escape" if escaped[0] else "bound"),
                "by": by, "shot": n_shots[0] if n_shots[0] <= MAX_SHOTS else None})  # fmt: skip
            if walked is not None:
                time.sleep(WALK_STOP_SETTLE_S)  # our short walk ends before the next scan
                return False  # the click hit the ground: no lock (the caller scans again)
            return True

        def box_target() -> tuple[Cell, tuple[float, float]] | None:
            """dungeon@8.8 (rogue-xmas02.md 4M): our walk ends (BOX_SETTLE_S after the last walk
            click), then a box grabbed after that, the nearest to our cell's point within
            BOX_TARGET_PX, is hovered at its box_hover_points; the first SWORD is returned as
            (its cell relative to us, the hover point) for the strike. None: the ring scan."""
            assert boxes is not None
            t_0 = time.monotonic()
            time.sleep(settle_left(last_walk_click, t_0))
            t_set = time.monotonic()
            meta: dict[str, Any] | None = None
            arm = None
            if a.box_now:  # dungeon@8.9: a detection now, not the rhythm's next (rogue 4N)
                arm = box_arm(a.box_detector, n_box_target[0])
                n_box_target[0] += 1
                meta = boxes.fresh_now(arm, BOX_TARGET_WAIT_S)
                fresh = meta is not None
            else:
                fresh = boxes.wait_fresh(t_set, BOX_TARGET_WAIT_S)
            rec: dict[str, Any] = {"kind": "box_target", "fresh": fresh,
                                   "settle_ms": round((t_set - t_0) * 1e3),
                                   "wait_ms": round((time.monotonic() - t_set) * 1e3)}  # fmt: skip
            if a.box_now:
                rec["arm"] = arm
            if meta is not None:
                rec.update(path=meta["path"], det_ms=meta["ms"], gpu_reason=meta["reason"],
                           grab_after_ms=round((meta["t"] - t_set) * 1e3),
                           boxes_after_ms=round((meta["t_done"] - t_set) * 1e3))  # fmt: skip
            near_b = (boxes.near(FOOT_PX, BOX_TARGET_PX, BOX_TARGET_WAIT_S + 1.0) if fresh
                      else None)  # fmt: skip
            if near_b is None:
                ev({**rec, "box": None, "verdicts": [], "struck": False})
                return None
            foot = ((near_b[0] + near_b[2]) / 2, near_b[3])
            rec.update(
                box=[round(x_, 1) for x_ in near_b],
                d_px=round(math.hypot(foot[0] - FOOT_PX[0], foot[1] - FOOT_PX[1])),
            )
            verdicts: list[str] = []
            points = box_hover_points(near_b)
            for u_, v_ in points[:1] if a.box_now else points:  # dungeon@8.9: ONE hover
                if not in_view(u_, v_):
                    verdicts.append("off")
                    continue
                t_h = time.monotonic()
                res_ = hover(u_, v_)
                if meta is not None and "hover_from_grab_ms" not in rec:
                    rec["hover_from_grab_ms"] = round((t_h - meta["t"]) * 1e3)
                    rec["verdict_from_grab_ms"] = round((time.monotonic() - meta["t"]) * 1e3)
                verdicts.append(str(res_["verdict"]))
                if res_["verdict"] == "sword":
                    sp_ = box_spot(here, foot)
                    rel_ = (0, 0) if sp_ is None or here is None else \
                        (sp_[0] - here[0], sp_[1] - here[1])  # fmt: skip
                    ev({**rec, "verdicts": verdicts, "struck": True, "rel": list(rel_)})
                    return rel_, (u_, v_)
            ev({**rec, "verdicts": verdicts, "struck": False})
            return None

        def self_uv() -> tuple[float, float]:
            """Our own feet point on screen (the camera keeps us there): the self box's anchor."""
            u0_, v0_ = project(here, [(0, 0)])[0]
            return float(u0_), float(v0_)

        def scan(purpose: str, cells: Sequence[Cell], stop_on: str
                 ) -> tuple[Cell, Any, dict[str, Any]] | None:  # fmt: skip
            """Hover each cell's point (defend: the body above it; loot: the cell); the first
            ``stop_on`` ("sword" / "pickup") ends the scan. Aborts when a fight starts (loot)."""
            t_s = time.monotonic()
            verdicts: Counter[str] = Counter()
            if purpose == "defend" and getattr(a, "walk_stop", False):
                kept = drop_false(cells, false_rel, t_s)
                verdicts["walked_skip"] += len(cells) - len(kept)
                cells = kept
            uv = project(here, cells)
            found = None
            for c, (u, v) in zip(cells, uv, strict=True):
                v_ = v - (BODY_UP if purpose == "defend" else PLANT_UP if purpose == "plant" else 0)
                if not in_view(u, v_):
                    verdicts["off"] += 1
                    continue
                res = hover(u, v_)
                if guard_tick():
                    break
                vd = "pickup" if pickup_seen(res["rec"]) else res["verdict"]
                if (
                    vd == "sword"
                    and purpose == "defend"
                    and getattr(a, "self_recheck", False)
                    and in_self_box(u, v_, *self_uv())
                ):
                    # --self-recheck (dungeon@9.3): on our own sprite a sword must persist
                    time.sleep(SELF_RECHECK_S)
                    res2 = hover(u, v_)
                    ev({"kind": "self_recheck", "rel": list(c), "u": round(u, 1),
                        "v": round(v_, 1), "first": round(res["rec"].get("sword", 0.0), 3),
                        "second": round(res2["rec"].get("sword", 0.0), 3),
                        "verdict2": res2["verdict"]})  # fmt: skip
                    counts["self_recheck"] += 1
                    if res2["verdict"] != "sword":
                        counts["self_transient"] += 1
                        verdicts["self_transient"] += 1
                        continue
                    res = res2
                verdicts[vd] += 1
                if vd == stop_on or (stop_on == "pickup" and vd == "sword"):
                    found = (c, (u, v_), res)
                    break
                if purpose in ("loot", "plant") and time.monotonic() - last_taken < 1.0:
                    break
            ev({"kind": "scan", "purpose": purpose, "cells": sum(verdicts.values()),
                "verdicts": dict(verdicts), "found": None if found is None else
                [round(found[1][0], 1), round(found[1][1], 1)],
                "found_rel": None if found is None else list(found[0]),
                "ms": round((time.monotonic() - t_s) * 1e3)})  # fmt: skip
            return found

        def read_here() -> Cell | None:
            rd = selfpos.read_minimap(frame(), digits, light=True)  # X1b: opt-in, confirmed
            return pos_ok.accept(time.monotonic(), rd)

        def grey(img_: Any) -> Any:
            return np.asarray(img_)[..., :3].astype(np.float32).mean(axis=2)

        def patch(g_: Any, u: float, v: float) -> Any:
            """A cell's 24 x 20 patch of a GREY frame. 4.01 Amendment B (its pilot, 22:3x): this
            converted the WHOLE frame on every call (~44 ms; two calls a cell, ~200 cells), ~10-14 s
            before a loot step's first hover; now grey() runs once per frame."""
            y0_, x0_ = int(v) - 14, int(u) - 12
            if y0_ < 0 or x0_ < 0 or y0_ + 20 > g_.shape[0] or x0_ + 24 > g_.shape[1]:
                return None
            return g_[y0_ : y0_ + 20, x0_ : x0_ + 24]

        loot_v2 = a.loot in ("v2", "rhythm")
        loot_trim = a.loot == "trim"  # gef10-eyes-loot.md E1: v1 capped at LOOT_TRIM_HOVERS
        rhythm = a.loot == "rhythm"  # 4.02: v2's order with Batt's per-fight bounds
        fight_budget = LOOT_RHYTHM_BUDGET_S if rhythm else LOOT_FIGHT_BUDGET_S
        loot_used: dict[float, float] = {}  # loot v2: the fight (its ref's time) -> seconds used
        loot_picked: dict[float, int] = {}  # 4.02: the fight -> pickups so far (rhythm's bound)
        empty_cells: dict[Cell, float] = {}  # loot v2: cells hovered empty -> when

        def changed_cells(
            ref: dict[str, Any] | None, skip: Any = frozenset()
        ) -> list[tuple[float, Cell]]:
            """Every cell in view whose image changed since the fight began (the sweep's rule);
            ``skip``: cells not to consider (v1's sweep: those its list already hovered). 4.01
            Amendment B: the two frames go grey ONCE and the cells are projected in one batch
            (the same cells, the same diffs)."""
            if ref is None or here is None:
                return []
            g_now, g_ref = grey(frame()), grey(ref["img"])
            h0 = ref["here"]
            cells: list[Cell] = []
            for dx in range(-SWEEP_X, SWEEP_X + 1):
                for dy in range(-SWEEP_Y, SWEEP_Y + 1):
                    c = (here[0] + dx, here[1] + dy)
                    if (
                        c in skip
                        or (dx, dy) == (0, 0)
                        or not (0 <= c[0] < ok.shape[1] and 0 <= c[1] < ok.shape[0])
                    ):
                        continue
                    if not ok[c[1], c[0]] or mz.in_no_enter(zones, c):
                        continue
                    cells.append(c)
            if not cells:
                return []
            uv_now = project(here, [(c[0] - here[0], c[1] - here[1]) for c in cells])
            uv_ref = project(h0, [(c[0] - h0[0], c[1] - h0[1]) for c in cells])
            out_c: list[tuple[float, Cell]] = []
            for c, (u, v), (u0, v0) in zip(cells, uv_now, uv_ref, strict=True):
                if not in_view(u, v):
                    continue
                pa, pb = patch(g_ref, u0, v0), patch(g_now, u, v)
                if pa is None or pb is None:
                    continue
                diff = float(np.abs(pa - pb).mean())
                if diff >= SWEEP_DIFF:
                    out_c.append((diff, c))
            return out_c

        def loot_step(lst: list[tuple[Cell, float]], ref: dict[str, Any] | None) -> str:
            if loot_v2:
                return loot_step_v2(lst, ref)
            return loot_step_v1(lst, ref)

        def loot_step_v2(lst: list[tuple[Cell, float]], ref: dict[str, Any] | None) -> str:
            """loot v2 (Batt decision 4): the changed cells first, then the plain list cells; one
            time budget per FIGHT (LOOT_FIGHT_BUDGET_S, shared by the steps after one fight); a cell
            hovered empty is skipped unless a kill came near it after that hover."""
            nonlocal here, lock, mode
            t_s = time.monotonic()
            key = ref["t"] if ref is not None else t_s
            left = fight_budget - loot_used.get(key, 0.0)
            max_picks = (LOOT_RHYTHM_PICKS - loot_picked.get(key, 0)) if rhythm else LOOT_MAX_PICKS
            out_: dict[str, Any] = {"kind": "loot_step", "loot": a.loot, "list_kills": len(lst),
                                    "budget_left_s": round(left, 2)}  # fmt: skip
            if here is None or left <= 0 or max_picks <= 0:
                ev({**out_, "end": "no_position" if here is None else "budget" if left <= 0
                    else "picks", "ms": round((time.monotonic() - t_s) * 1e3)})  # fmt: skip
                return "none"
            plan = {(g[0] + dx, g[1] + dy) for g, t_ in lst if t_s - t_ <= 55.0
                    for dx in range(-2, 3) for dy in range(-2, 3)}  # fmt: skip
            plan = {c for c in plan if 0 <= c[0] < ok.shape[1] and 0 <= c[1] < ok.shape[0]
                    and ok[c[1], c[0]] and not mz.in_no_enter(zones, c)}  # fmt: skip
            changed = changed_cells(ref)
            order = loot_order(changed, plan, here, empty_cells, lst)
            out_.update(
                planned=len(plan),
                changed=len(changed),
                ordered=len(order),
                skipped_empty=len(plan | {c for _d, c in changed}) - len(order),
            )
            picks, hovered, n_changed = 0, 0, 0
            end = "done"
            for c, why in order:
                if picks >= max_picks or hovered >= LOOT_V2_MAX_HOVERS:
                    end = "bound"
                    break
                if time.monotonic() - t_s > left:
                    end = "budget"
                    break
                if time.monotonic() - last_taken < 1.0:
                    end = "hit"
                    break
                assert here is not None
                rel = (c[0] - here[0], c[1] - here[1])
                u, v = project(here, [rel])[0]
                if not in_view(u, v):
                    continue
                hovered += 1
                n_changed += why == "changed"
                res = hover(u, v)
                if guard_tick():
                    end = "escape"
                    break
                if res["verdict"] == "sword":
                    ev({"kind": "engage", "by": "loot_sword", "name": None})
                    strike(u, v - BODY_UP, rel, "loot_sword")
                    lock = {"t": time.monotonic(), "rel": rel, "cell": list(c)}
                    mode = "fight"
                    end = "fight"
                    break
                if pickup_seen(res["rec"]):
                    d_ = max(abs(rel[0]), abs(rel[1]))
                    click_at(u, v, "loot")
                    ev({"kind": "loot_click", "u": round(u, 1), "v": round(v, 1),
                        "rel": list(rel), "cell": list(c), "why": why})  # fmt: skip
                    picks += 1
                    time.sleep(0.45 + 0.2 * d_)
                    here = read_here() or c
                    empty_cells.pop(c, None)
                else:
                    empty_cells[c] = time.monotonic()
            used = time.monotonic() - t_s
            loot_used[key] = loot_used.get(key, 0.0) + used
            loot_picked[key] = loot_picked.get(key, 0) + picks
            ev({**out_, "hovered": hovered, "hovered_changed": n_changed, "picks": picks,
                "end": end, "ms": round(used * 1e3)})  # fmt: skip
            return "fight" if end == "fight" else "done"

        def loot_step_v1(lst: list[tuple[Cell, float]], ref: dict[str, Any] | None) -> str:
            """Batt 2026-10-22 11:5x (his 11:44 clip: an item left in a mob fight). After the
            fight: (1) the LOOT LIST -- the union of the 5 x 5 around our cell at EVERY kill of
            the fight (items do not move; <= 55 s old), walkable and outside the zones, nearest
            first; (2) the SWEEP -- every cell in view whose image changed since the fight began
            (the fight's first frame, re-projected from our cell then). Each cell is hovered at
            its ground point; a PICKUP hand is clicked, a SWORD engaged ("fight"), anything else
            passed. Bounded by LOOT_MAX_HOVERS / LOOT_MAX_PICKS / LOOT_MAX_S."""
            nonlocal here, lock, mode
            t_s = time.monotonic()
            hovered: set[Cell] = set()
            picks = 0
            n_hov = 0  # cells actually hovered (in view); --loot trim caps this
            out_: dict[str, Any] = {"kind": "loot_step", "list_kills": len(lst)}
            if here is None:
                ev({**out_, "end": "no_position"})
                return "none"
            plan = {(g[0] + dx, g[1] + dy) for g, t_ in lst if t_s - t_ <= 55.0
                    for dx in range(-2, 3) for dy in range(-2, 3)}  # fmt: skip
            plan = {c for c in plan if 0 <= c[0] < ok.shape[1] and 0 <= c[1] < ok.shape[0]
                    and ok[c[1], c[0]] and not mz.in_no_enter(zones, c)}  # fmt: skip
            out_["planned"] = len(plan)

            def visit(c: Cell, why: str) -> str:
                nonlocal here, lock, mode, picks, n_hov
                assert here is not None
                rel = (c[0] - here[0], c[1] - here[1])
                u, v = project(here, [rel])[0]
                hovered.add(c)
                if not in_view(u, v):
                    return "off"
                n_hov += 1
                res = hover(u, v)
                if guard_tick():
                    return "escape"
                if res["verdict"] == "sword":
                    ev({"kind": "engage", "by": "loot_sword", "name": None})
                    strike(u, v - BODY_UP, rel, "loot_sword")
                    lock = {"t": time.monotonic(), "rel": rel, "cell": list(c)}
                    mode = "fight"
                    return "fight"
                if pickup_seen(res["rec"]):
                    d_ = max(abs(rel[0]), abs(rel[1]))
                    click_at(u, v, "loot")
                    ev({"kind": "loot_click", "u": round(u, 1), "v": round(v, 1),
                        "rel": list(rel), "cell": list(c), "why": why})  # fmt: skip
                    picks += 1
                    time.sleep(0.45 + 0.2 * d_)  # the walk there and the pickup
                    here = read_here() or c
                return "ok"

            end = "done"
            while picks < LOOT_MAX_PICKS and len(hovered) < LOOT_MAX_HOVERS and not (
                    loot_trim and n_hov >= LOOT_TRIM_HOVERS):  # fmt: skip
                todo = sorted(plan - hovered, key=lambda c: (cheb2(c, here), c))
                if not todo or time.monotonic() - t_s > LOOT_MAX_S:
                    break
                if time.monotonic() - last_taken < 1.0:
                    end = "hit"
                    break
                got = visit(todo[0], "list")
                if got in ("fight", "escape"):
                    end = got
                    break
            out_["list_hovered"] = len(hovered)
            sweep_n, changed = 0, []
            if end == "done" and ref is not None and here is not None and not loot_trim:
                changed = changed_cells(ref, skip=hovered)  # 4.01 Amendment B: the shared helper
                changed.sort(key=lambda dc: (cheb2(dc[1], here), -dc[0]))
                for _diff, c in changed[:SWEEP_MAX]:
                    if picks >= LOOT_MAX_PICKS or time.monotonic() - t_s > LOOT_MAX_S:
                        break
                    if time.monotonic() - last_taken < 1.0:
                        end = "hit"
                        break
                    got = visit(c, "sweep")
                    sweep_n += 1
                    if got in ("fight", "escape"):
                        end = got
                        break
            ev({**out_, "hovered": len(hovered), "hovers": n_hov, "trim": loot_trim, "picks": picks,
                "sweep_changed": len(changed), "sweep_hovered": sweep_n, "end": end,
                "ms": round((time.monotonic() - t_s) * 1e3)})  # fmt: skip
            return "fight" if end == "fight" else "done"

        # --- --rest house (docs/planning/gef10-house-rest.md; reached only with house_on) -----

        def tadv(event: str) -> str:
            """The trip's next state (house_rest.Trip's closed table); an event the table does not
            allow in the current state STOPS the run (r.Stop, so run_end names it)."""
            assert trip is not None
            try:
                nxt = trip.advance(event)
            except hr.TripStop as e:
                raise r.Stop(str(e)) from None
            ev({"kind": "house_trip", "event": event, "state": nxt})
            return nxt

        def house_reads() -> tuple[float, int | None, int | None, Cell | None, float, Any]:
            """ONE fresh frame: (time, HP %, SP %, the minimap readout, the frame's mean, frame)."""
            img_ = frame()
            xy_ = pos_ok.accept(time.monotonic(), selfpos.read_minimap(img_, digits, light=True))
            return (time.monotonic(), hpp.read(img_, glyphs), hpp.read(img_, glyphs, hpp.SP_DY),
                    xy_, float(np.asarray(img_).mean()), img_)  # fmt: skip

        def taken_since(n0: int) -> bool:
            with blt.lock:
                return any(ln.get("type") == "taken" for ln in blt.lines[n0:])

        def house_stop(img_: Any, why: str) -> None:
            from PIL import Image

            Image.fromarray(np.asarray(img_)[..., ::-1]).save(out / "stop-house.jpg", quality=90)
            raise r.Stop(f"--rest house: {why}")

        def house_wait(tr: Any, why: str, field_ok: bool) -> tuple[str, Cell | None]:
            """Fresh reads into ``tr`` (house_rest.Transition) at READ_HZ until it decides. Before
            any load gap we still stand on the field (``field_ok``): a hit there = "hit". A
            "stop:" verdict STOPS the run (its frame kept)."""
            with blt.lock:
                n0 = len(blt.lines)
            last: tuple[str, bool, bool] | None = None
            while True:
                t_, p_, _s, xy_, m_, img_ = house_reads()
                got_ = tr.step(t_, p_ is not None, xy_, m_)
                key = (got_, tr.gap_t0 is not None, tr.gap_t1 is not None)
                if key != last:  # one record per change of the tracker's state
                    ev({"kind": "house_read", "why": why, "state": got_, "hp": p_,
                        "pos": None if xy_ is None else list(xy_), "mean": round(m_, 1),
                        "gap": key[1], "loaded": key[2]})  # fmt: skip
                    last = key
                if got_ == "wait":
                    if field_ok and tr.gap_t0 is None and tr.gap_t1 is None and taken_since(n0):
                        return "hit", None
                    time.sleep(max(0.0, 1.0 / READ_HZ - (time.monotonic() - t_)))
                    continue
                if got_.startswith("stop:"):
                    house_stop(img_, f"{why}: {got_[5:]}")
                return got_, xy_

        def plan_house(here_: Cell, frac_: float | None) -> dict[str, Any] | None:
            """The house of this rest (house_rest.choose: the fewest route-grid steps to an
            approach cell), or None = today's field rest (house_trip_why says why)."""
            ch = None
            if frac_ is not None and frac_ >= HOUSE_MIN_HP:
                ch = hr.choose(here_, [(h_, sorted(house_ap[h_.name])) for h_ in houses_ok], okr,
                               HOUSE_MAX_STEPS)  # fmt: skip
            why_ = house_trip_why(frac_, ch)
            ev({"kind": "house_plan", "at": list(here_), "pct": pct, "why_not": why_,
                "house": None if ch is None else ch[0].name,
                "approach": None if ch is None else list(ch[1]),
                "steps": None if ch is None else ch[2]})  # fmt: skip
            if why_ is not None or ch is None:
                return None
            return {"house": ch[0], "approach": ch[1], "steps": ch[2]}

        def house_door(h: Any, here_: Cell) -> str:
            """The ONE door click, from a standstill on one of the house's approach cells: the
            door's centre (its own no-enter area is the only zone this click may enter), after a
            cursor read that is not a SWORD (a monster on the door is engaged instead) nor the
            no-entry ring. Then the expected load INTO the house (pixels). Returns "inside" /
            "none" (no load gap) / "hit" (hit before any gap) / "fight" / "noentry" / "off"."""
            nonlocal lock, mode, house_click_t
            rel_ = (h.door.cell[0] - here_[0], h.door.cell[1] - here_[1])
            u_, v_ = (float(x_) for x_ in project(here_, [rel_])[0])
            if not in_view(u_, v_):
                return "off"
            res_ = hover(u_, v_)
            if res_["verdict"] == "sword":
                ev({"kind": "engage", "by": "house_door_sword", "name": None})
                strike(u_, v_ - BODY_UP / 2, rel_, "walk_sword")
                lock = {"t": time.monotonic(), "rel": rel_, "cell": list(h.door.cell)}
                mode = "fight"
                return "fight"
            if res_["verdict"] == "noentry":
                return "noentry"
            assert trip is not None
            tadv("door_click")
            click_at(u_, v_, "house_door")
            house_click_t = time.monotonic()
            ev({"kind": "house_door", "house": h.name, "from": list(here_),
                "door": list(h.door.cell), "u": round(u_, 1), "v": round(v_, 1),
                "verdict": res_["verdict"], "arrival": list(h.arrival)})  # fmt: skip
            got_, _xy = house_wait(hr.Transition("inside", house_click_t), "door", field_ok=True)
            tadv(got_)  # inside / none / hit (anything else raised TripStop)
            return got_

        def house_inside(h: Any) -> str:
            """In the house (the pixels said so): sit AT ONCE, never walk; rest until rest_done
            (or HOUSE_REST_MAX_S); a minimap readout, damage, a falling HP, death or an unknown
            UI state inside STOPS the run (nothing should touch us there). Never a Fly Wing,
            never a potion (in_orcs01 is noteleport; nothing hits us). "done" / "time_box"."""
            nonlocal sitting
            assert trip is not None
            press("sit", f"house {h.name}")
            sitting = True
            tadv("sat")
            t_in = time.monotonic()
            ev({"kind": "rest_start", "cell": list(h.arrival), "map": hr.HOUSE_MAP,
                "house": h.name, "pct": pct, "sp_pct": spp, "spot": None, "fallback": False,
                "why": "house"})  # fmt: skip
            time.sleep(0.6)
            cs_ = f0.client_state(agent_raw, screen)
            if cs_["decision"]["do"] != "clear":
                house_stop(cs_["frame"], f"unknown UI state inside {cs_['decision']}")
            with blt.lock:
                n0 = len(blt.lines)
            best: int | None = None
            unread: float | None = None
            p_: int | None = None
            s_: int | None = None
            why_ = "full"
            while True:
                t_, p_, s_, xy_, _m, img_ = house_reads()
                if r.is_state(screen, gv.DEAD_STATE):
                    house_stop(img_, "dead inside the house")
                if xy_ is not None:
                    house_stop(img_, f"a minimap readout {list(xy_)} inside the house")
                if taken_since(n0):
                    house_stop(img_, "a hit on us inside the house")
                if p_ is None:
                    unread = t_ if unread is None else unread
                    if t_ - unread > HOUSE_UNREAD_S:
                        house_stop(img_, f"Basic Info unread {HOUSE_UNREAD_S:.0f} s inside")
                else:
                    unread = None
                    best = p_ if best is None else max(best, p_)
                    if p_ <= best - HOUSE_HP_FALL:
                        house_stop(img_, f"HP fell {best} -> {p_} inside the house")
                    if rest_done(strat, p_, s_):
                        break
                if t_ - t_in > HOUSE_REST_MAX_S:
                    why_ = "max"
                    break
                if t_ >= t_end:
                    ev({"kind": "house_time_box", "house": h.name, "pct": p_})
                    return "time_box"
                time.sleep(max(0.0, HOUSE_READ_S - (time.monotonic() - t_)))
            press("stand", why_)
            sitting = False
            ev({"kind": "rest_end", "why": why_, "pct": p_, "sp_pct": s_, "map": hr.HOUSE_MAP,
                "house": h.name})  # fmt: skip
            tadv("done")
            time.sleep(0.5)
            return "done"

        def house_leave(h: Any) -> tuple[Cell, bool]:
            """Standing at the arrival cell: hover + ONE click on the house's own exit (its centre,
            projected from the arrival by the indoor camera; house_px), then the expected load back
            to the field at the exit's return cell. A SWORD or the no-entry ring at that point,
            or no load after HOUSE_DOOR_TRIES clicks, STOPS the run. Returns (our cell, read)."""
            nonlocal house_click_t
            assert trip is not None
            u_, v_ = house_px[h.name]
            for k_ in range(HOUSE_DOOR_TRIES):
                res_ = hover(u_, v_)
                if res_["verdict"] in ("sword", "noentry"):
                    house_stop(frame(), f"the exit point of {h.name} reads {res_['verdict']}")
                tadv("exit_click")
                click_at(u_, v_, "house_exit")
                house_click_t = time.monotonic()
                ev({"kind": "house_exit", "house": h.name, "u": round(u_, 1), "v": round(v_, 1),
                    "try": k_ + 1, "verdict": res_["verdict"], "back": list(h.back)})  # fmt: skip
                tr_ = hr.Transition("back", house_click_t, back=h.back)
                got_, xy_ = house_wait(tr_, "exit", field_ok=False)
                if got_ == "back":
                    tadv("back")
                    return (xy_, True) if xy_ is not None else (h.back, False)
            house_stop(frame(), f"the exit of {h.name}: no load after {HOUSE_DOOR_TRIES} clicks")
            raise AssertionError("unreachable")  # house_stop raised

        try:
            while time.monotonic() < t_end:
                tick = time.monotonic()
                if escaped[0]:  # a Fly Wing inside a scan or a strike (guard_tick)
                    escaped[0] = False
                    fly_at = tick
                    lock, goal_path = None, None
                    loot_list, fight_ref = [], None
                    mode = "search"
                    here, last_taken = None, -1e9  # Amendment F: a new spot, the old hits gone
                    last_swing = -1e9
                img = frame()
                pct = hpp.read(img, glyphs)
                spp = hpp.read(img, glyphs, hpp.SP_DY)
                if stock_watch is not None and stock_due:  # dungeon@8.4: the stock after a press
                    out_item = None
                    for item_ in [i for i, t_ in stock_due.items() if tick >= t_]:
                        n_ = hb.read_count(hb.gray(img), stock_watch[1][item_], stock_watch[0])
                        stock_tries[item_] = stock_tries.get(item_, 0) + 1
                        if n_ is None and stock_tries[item_] < STOCK_TRIES:
                            stock_due[item_] = tick + STOCK_READ_S  # the teleport's dark frames
                            continue
                        del stock_due[item_]
                        ev({"kind": "stock", "item": item_, "count": n_,
                            "tries": stock_tries[item_]})  # fmt: skip
                        if out_item is None and stock_out({item_: n_}) is not None:
                            out_item = item_
                    if out_item is not None:  # no escape (or no potion) left: end, warp home
                        reason = f"stock_out: item {out_item} reads 0 on the hotbar"
                        break
                if miss_tpl is not None and not sitting and mode != "after":  # dungeon@9.1:
                    # a missed swing AT us (drawn above the attacker, beside us); 9.1b: not read
                    # on the tick after a fight's end, so a Miss still drawn goes to the loot step
                    mc_ = mcue.read(img, miss_tpl)
                    if mc_.score >= mcue.THRESHOLD:
                        if tick - last_swing > 1.0:  # one record per swing, not per frame
                            ev({"kind": "miss_cue", "score": round(mc_.score, 3), "x": mc_.x,
                                "y": mc_.y})  # fmt: skip
                        last_swing = tick
                n_reads += 1
                dark = sv.dark_screen(img)
                ag_on = (sv.ag_present(img, ag_t, ag_m, a.ag_match)
                         if conf["autoguard"] and n_reads % sv.AG_EVERY == 1 and not dark
                         else None)  # fmt: skip
                dead = r.is_state(screen, gv.DEAD_STATE)
                # Amendment H (r4 15:49): the minimap's coordinates still showed the OLD cell 0.25 s
                # after a Fly Wing -- no read for FLY_SETTLE_S after one, and no jump bar for
                # FLY_JUMP_S (a Fly Wing is a same-map teleport; packets judge map changes)
                fresh = tick - fly_at >= FLY_SETTLE_S
                rd = selfpos.read_minimap(img, digits, light=True) if fresh else None
                pos = pos_ok.accept(tick, rd) if rd is not None else None
                rd_why = read_outcome(rd, pos)
                if pos is not None:
                    p_ = pos
                    if (here is not None and is_jump(here, p_, tick - last_pos_t)
                            and tick - fly_at > FLY_JUMP_S):  # fmt: skip
                        ev({"kind": "jump", "from": list(here), "to": list(p_),
                            "since_s": round(tick - last_pos_t, 2)})  # fmt: skip
                        reason = "hard_bar: position jump (map change?)"
                        break
                    here, last_pos_t = p_, tick
                    if house_on:
                        pos_hist.append((tick, p_))
                ev({"kind": "hp_read", "pct": pct, "sp_pct": spp, "dead": dead, "ag_on": ag_on,
                    "dark": dark, "pos": None if here is None else list(here),
                    "rd": rd_why})  # fmt: skip
                if dead:
                    reason = "death"
                    ev(
                        {
                            "kind": "death",
                            "last_reads": [
                                [round(t, 2), round(f, 3)] for t, f in list(st.hist)[-40:]
                            ],
                        }
                    )
                    break
                if house_on:  # gef10-house-rest.md: on the FIELD a load screen nobody asked for
                    # (no door / exit click of ours, no Fly Wing) is a map change: a hard bar
                    gap_since = None if pct is not None else (tick if gap_since is None
                                                              else gap_since)  # fmt: skip
                    if gap_since is not None and hr.gap_unexpected(
                            tick - gap_since, gap_since - fly_at, gap_since - house_click_t,
                            FLY_JUMP_S):  # fmt: skip
                        ev({"kind": "house_gap", "s": round(tick - gap_since, 2),
                            "since_fly_s": round(gap_since - fly_at, 1)})  # fmt: skip
                        reason = "hard_bar: an unexpected load screen (map change?)"
                        break
                # the Battle Log's new lines (its own process; pixels only)
                with blt.lock:
                    new = blt.lines[seen_lines:]
                    seen_lines = len(blt.lines)
                taken_new = None
                for ln in new:
                    typ = ln.get("type")
                    if typ == "taken":
                        last_taken = tick
                        taken_new = taken_new or ln
                    elif typ == "damage":
                        last_ours = tick
                    elif typ == "base_exp":
                        kills_seen.append(tick)
                        ev({"kind": "kill", "by": "exp_line", "gm": None if here is None
                            else list(here)})  # fmt: skip
                        if here is not None:  # the loot list: the 5 x 5 around us at this death
                            loot_list.append((here, tick))
                        if mr and lock is not None and lock.get("cell"):  # it died: off the queue
                            queue[:] = [q for q in queue if list(q["cell"]) != list(lock["cell"])]
                        lock = None
                if not blt.alive():
                    reason = "battle_log_reader_died"
                    break
                frac = None if pct is None else pct / 100.0
                spf = None if spp is None else spp / 100.0
                # sustain first (every strategy), then Auto Guard (S4b2)
                if sitting and (tick - last_taken <= FIGHT_TAKEN_S or hp_dropped(st.hist, tick)):
                    # dungeon@8.2: damage stands a sitting player up on the server (pc_damage ->
                    # pc_setstand); never press "stand" (a toggle) after it -- just know it
                    sitting = False
                    ev({"kind": "rest_end", "why": "damage (the server stood us up)", "pct": pct,
                        "sp_pct": spp})  # fmt: skip
                calm = (tick - last_taken > CALM_S and mode != "fight" and not sitting
                        and not hp_dropped(st.hist, tick))  # fmt: skip
                if frac is not None:
                    for what, why in sustain(st, tick, frac, spf, strat, calm):
                        if what == "fly":
                            if sitting:
                                press("stand", "escape")
                                sitting = False
                            press("fly", why)
                            fly_at = time.monotonic()
                            ev({"kind": "escape", "how": "fly", "why": why})
                            lock, goal_path = None, None
                            loot_list, fight_ref = [], None  # far away now
                            mode = "search"
                            here, last_taken = None, -1e9  # Amendment F
                            time.sleep(1.0)
                        elif what == "heal":
                            if sitting:
                                press("stand", "heal")
                                sitting = False
                            heal_self(why)
                        else:
                            press(what, why)
                diag_due = n_ag_diag[0] < AG_DIAG_MAX and tick - ag_diag_t[0] >= AG_DIAG_GAP_S
                if ag_on is False and ag_last >= 0 and tick - ag_last < sv.AG_RECAST_S and diag_due:
                    # the DIAGNOSTIC CAPTURE (Batt decision 7; 3.96's S4b2 open point): the icon
                    # reads ABSENT while our cast is remembered -- keep the frame, find the cause
                    n_ag_diag[0] += 1
                    ag_diag_t[0] = tick
                    from PIL import Image

                    Image.fromarray(np.asarray(img)[..., ::-1]).save(
                        out / f"ag-absent-{n_ag_diag[0]:03d}.jpg", quality=90)  # fmt: skip
                    ev({"kind": "ag_absent_capture", "n": n_ag_diag[0],
                        "since_cast_s": round(tick - ag_last, 1)})  # fmt: skip
                if ag_on is not None:
                    if ag_on:
                        ag_absent = None
                        if ag_last < 0:
                            ag_last = time.monotonic()
                    else:
                        ag_absent = ag_absent if ag_absent is not None else tick
                        if tick - ag_absent >= sv.AG_ABSENT_S and tick - ag_last >= sv.AG_RECAST_S:
                            press("autoguard", "first cast" if ag_last < 0 else "recast")
                            ag_last = time.monotonic()
                            sv.save_ag_last(ag_last)
                            ag_absent = None
                # a fight?
                hit_now = tick - last_taken < FIGHT_TAKEN_S
                swing_now = swing_engages(tick, last_swing, swing_floor)  # 9.1b, --miss-cue
                dropped = hp_dropped(st.hist, tick) and tick - fly_at > 2.0
                near_ = None
                if boxes is not None and mode != "fight" and not sitting:  # a box never
                    here_b = here  # stands us up

                    def skip_b(foot: Sequence[float], here_b: Cell | None = here_b,
                               tick_b: float = tick) -> bool:  # fmt: skip
                        sp_ = box_spot(here_b, foot) if box_spots is not None else None
                        if sp_ is None or not box_spots.ignored(sp_):  # type: ignore[union-attr]
                            return False
                        if tick_b - spot_logged.get(sp_, -1e9) >= 30.0:  # rate-limited record
                            spot_logged[sp_] = tick_b
                            ev({"kind": "box_ignored", "spot": list(sp_)})
                        return True

                    near_ = boxes.near(FOOT_PX, BOX_NEAR_PX, BOX_FRESH_S, skip_b)
                if (hit_now or dropped or swing_now or near_ is not None) and mode != "fight":
                    # ONE engage event per fight, by what started it
                    box_fight.clear()
                    if taken_new is not None:
                        ev({"kind": "engage", "by": "battle_log", "name": taken_new.get("name"),
                            "n": taken_new.get("n")})  # fmt: skip
                    elif hit_now:
                        ev({"kind": "engage", "by": "battle_log", "name": None, "late": True})
                    elif dropped:
                        ev({"kind": "engage", "by": "hp_drop", "name": None})
                    elif swing_now:
                        ev({"kind": "engage", "by": "miss_cue", "name": None})
                    else:
                        sp_e = (None if near_ is None else
                                box_spot(here, ((near_[0] + near_[2]) / 2, near_[3])))  # fmt: skip
                        ev({"kind": "engage", "by": "box", "name": None,
                            "box": [round(x_, 1) for x_ in near_ or ()],
                            "spot": None if sp_e is None else list(sp_e)})  # fmt: skip
                        box_fight.update(
                            {
                                "spot": sp_e,
                                "n0": n_strike[0],
                                "box": None if near_ is None else list(near_),
                            }
                        )
                    if sitting:  # dungeon@8.2: the SERVER stood us up (pc_damage -> pc_setstand,
                        # pinned pc.cpp); a stand press here is a TOGGLE and sat us back down
                        # (4.05 a6: then every potion / Fly Wing was refused while sitting)
                        sitting = False
                        ev({"kind": "rest_end", "why": "hit", "pct": pct, "sp_pct": spp})
                    mode, goal_path = "fight", None
                    if fight_ref is None and here is not None:  # the sweep's "before"
                        fight_ref = {"img": img, "here": here, "t": tick}
                # UI watch (the hard bar: an unknown UI state)
                if tick - last_ui >= UI_EVERY_S and mode != "fight":
                    last_ui = tick
                    cs = f0.client_state(agent_raw, screen)
                    if cs["decision"]["do"] != "clear":
                        r.to_png(cs["frame"], out / "stop-ui.png")
                        reason = f"hard_bar: unknown UI state {cs['decision']}"
                        break
                    # Amendment I: the weight, read with the UI watch (no regen at >= 50 %)
                    frs = gm_state._frames(screen)
                    w_now = gm_state.weight_share(gm_state._weight(frs))
                    red_now = overweight_red(frs[0])
                    if red_now != red_seen or (w_now is not None and (
                            w_share is None or abs(w_now - w_share) >= 0.005)):  # fmt: skip
                        ev({"kind": "weight", "share": None if w_now is None else round(w_now, 4),
                            "red": red_now})  # fmt: skip
                    w_share = w_now if w_now is not None else w_share
                    red_seen = red_now
                overweight = red_seen or (w_share is not None and w_share >= REGEN_STOP)
                # Amendment E: a fight, a loot step or a rest is activity, never idle (run 3: a
                # fight in place + a 25-s loot step read as 45 s of idle and cost a Fly Wing)
                if mode != "search":
                    idle_since = tick
                    if patrol:
                        wp_st["resume"] = True
                # --- FIGHT: locked, or scan for the attacker
                if mode == "fight":
                    if lock is not None:
                        since = tick - lock["t"]
                        idle = tick - max(last_ours, lock["t"])
                        if since > LOCK_MAX_S or (since > LOCK_NO_HIT_S and idle > LOCK_NO_HIT_S):
                            ev({"kind": "unlock", "why": "no hits" if since <= LOCK_MAX_S
                                else "max", "s": round(since, 1)})  # fmt: skip
                            lock = None
                    quiet = tick - last_taken > FIGHT_TAKEN_S and not hp_dropped(st.hist, tick)
                    if lock is None and quiet and kills_seen and kills_seen[-1] > tick - 3.0:
                        # pilot 4: after a kill with no hit for 2.5 s, rings 1 + 2 took 8.6 s to
                        # find nobody -- end the fight; the loot step's hovers still see a SWORD
                        mode, swing_floor = "after", tick
                        ev({"kind": "fight_end", "kills": len(kills_seen), "why": "quiet kill"})
                        box_fight_done()
                        continue
                    if mr and lock is not None and here is not None and last_ours != ours_used \
                            and tick - last_ours <= MR_AFTER_HIT_S:  # fmt: skip
                        # MELEE-RING 2, 3.99 Amendment G (the pilot: 1 retarget in 4 hover
                        # windows): ONE ring cell right after our own hit (the Battle Log damage
                        # line, between swings), then the pointer goes back onto the locked target
                        lrel = tuple(lock.get("rel") or ())
                        cells_q = [c for c in ring(1) if c != lrel]
                        c_q = cells_q[qscan_i % len(cells_q)]
                        qscan_i += 1
                        ours_used = last_ours  # one hover per swing (the lock's clock untouched)
                        t_q = time.monotonic()
                        u_q, v_q = project(here, [c_q])[0]
                        v_q -= BODY_UP
                        added_q, verdict_q = False, "off"
                        if in_view(u_q, v_q):
                            res_q = hover(u_q, v_q)
                            verdict_q = res_q["verdict"]
                            if verdict_q == "sword":
                                added_q = queue_add(
                                    queue, (here[0] + c_q[0], here[1] + c_q[1]), tick
                                )
                            if lrel:  # back onto the locked target (moves only, no click)
                                u_l, v_l = project(here, [lrel])[0]
                                agent.move(gx0 + round(u_l), gy0 + round(v_l - BODY_UP))
                        ev({"kind": "queue_scan", "hovers": 1, "added": int(added_q),
                            "verdict": verdict_q, "queue": len(queue), "rel": list(c_q),
                            "lock_cell": lock.get("cell"),
                            "ms": round((time.monotonic() - t_q) * 1e3)})  # fmt: skip
                    if mr and lock is None and queue and here is not None:
                        # MELEE-RING 2: the current target died -> the next queued SWORD at once
                        t_h = time.monotonic()
                        while queue and lock is None:
                            q = queue.pop(0)
                            rel_q = (q["cell"][0] - here[0], q["cell"][1] - here[1])
                            if max(abs(rel_q[0]), abs(rel_q[1])) > 1:
                                continue  # it was beside where we stood, not beside us now
                            u_q, v_q = project(here, [rel_q])[0]
                            v_q -= BODY_UP
                            if not in_view(u_q, v_q):
                                continue
                            res_q = hover(u_q, v_q)
                            if res_q["verdict"] != "sword":
                                continue
                            if not strike(u_q, v_q, rel_q, "queue"):
                                continue  # --walk-stop: it walked, no lock
                            lock = {"t": time.monotonic(), "rel": rel_q, "cell": list(q["cell"])}
                            ev({"kind": "handoff", "from_kill_ms": None if not kills_seen else
                                round((t_h - kills_seen[-1]) * 1e3), "cell": list(q["cell"]),
                                "queue_left": len(queue)})  # fmt: skip
                    if (
                        lock is None
                        and a.box_strike
                        and boxes is not None
                        and box_fight.get("box") is not None
                        and not box_fight.get("tried")
                    ):
                        box_fight["tried"] = True  # dungeon@8.8: once per box fight
                        got_b = box_target()
                        if got_b is not None:
                            rel_b, (u_b, v_b) = got_b
                            if strike(u_b, v_b, rel_b, "box"):  # False: --walk-stop, it walked
                                lock = {"t": time.monotonic(), "rel": rel_b,
                                        "cell": None if here is None else
                                        [here[0] + rel_b[0], here[1] + rel_b[1]]}  # fmt: skip
                    if lock is None:
                        found = scan("defend", ring(1), "sword")
                        if found is None and not quiet:  # ring 2 only while hits still come
                            found = scan("defend", ring(2), "sword")
                        if found is not None:
                            c, (u, v), _res = found
                            if strike(u, v, c, "scan"):  # False: --walk-stop, it walked
                                cell_c = None if here is None else [here[0] + c[0], here[1] + c[1]]
                                lock = {"t": time.monotonic(), "rel": c, "cell": cell_c}
                        elif tick - last_taken > FIGHT_TAKEN_S and not hp_dropped(st.hist, tick):
                            mode, swing_floor = "after", tick
                            ev({"kind": "fight_end", "kills": len(kills_seen)})
                            box_fight_done()
                    time.sleep(max(0.0, 1.0 / READ_HZ - (time.monotonic() - tick)))
                    continue
                if mode == "fight" or (lock is not None):
                    continue
                # --- AFTER a fight: loot, then rest or search
                if mode == "after":
                    queue.clear()
                if mode == "after" and (loot_list or fight_ref is not None):
                    got_ = loot_step(loot_list, fight_ref)
                    idle_since = time.monotonic()
                    if got_ == "fight":
                        continue
                    loot_list, fight_ref = [], None
                    empty_cells.clear()  # loot v2: a new fight series starts clean
                if sitting and overweight:  # Amendment I: sitting regenerates nothing
                    press("stand", "overweight")
                    sitting = False
                    ev({"kind": "rest_end", "why": "overweight", "pct": pct, "sp_pct": spp})
                    mode, goal_path = "search", None
                if mode in ("after", "search") and frac is not None and not sitting \
                        and tick - st.heal > 2.0 and rest_wanted(strat, frac, spf) \
                        and overweight and tick - rest_skip_t > 30.0:  # fmt: skip
                    rest_skip_t = tick
                    ev({"kind": "rest_skip", "why": "overweight", "share": round(w_share or 0, 4),
                        "pct": pct, "sp_pct": spp})  # fmt: skip
                if trip is not None and trip.state == "walk" and mode not in ("rest", "after"):
                    tadv("left_rest")  # a fight (or a Fly Wing) took the walk to the door
                    hplan = None
                if mode in ("after", "search") and frac is not None and not sitting \
                        and not overweight \
                        and tick - st.heal > 2.0 and rest_wanted(strat, frac, spf):  # fmt: skip
                    mode, goal_path = "rest", None
                    rest_since = tick
                    ev({"kind": "rest_go", "pct": pct, "sp_pct": spp})
                    if trip is not None:  # --rest house: a new rest decides its house again
                        if trip.state == "walk":
                            tadv("left_rest")
                        tadv("rest_wanted")
                        hplan, house_fb, house_tries = None, False, 0
                if mode == "after":
                    mode = "search"
                # --- REST (B / C): to the nearest spot, sit until HP 100 %
                if mode == "rest":
                    if sitting:
                        full = rest_done(strat, pct, spp)
                        if full or tick - rest_since > REST_MAX_S:
                            press("stand", "full" if full else "rest max")
                            sitting = False
                            ev({"kind": "rest_end", "why": "full" if full else "max",
                                "pct": pct, "sp_pct": spp})  # fmt: skip
                            mode, goal_path = "search", None  # dungeon@4: back into the area
                        time.sleep(max(0.0, 1.0 / READ_HZ - (time.monotonic() - tick)))
                        continue
                    if here is not None and trip is not None and not house_fb:
                        # --rest house (gef10-house-rest.md): walk to the chosen house's approach
                        # cell on the route grid, ONE door click from a standstill there, rest
                        # inside, ONE exit click, back on the patrol; anything else -> field rest
                        fb_why: str | None = None
                        if hplan is None:
                            hplan = plan_house(here, frac)
                            if hplan is None:
                                fb_why = "plan"
                        if hplan is not None:
                            h_ = hplan["house"]
                            still_ = (pos is not None
                                      and still_since(pos_hist, tick) >= HOUSE_STILL_S)  # fmt: skip
                            if here in house_ap[h_.name] and still_:
                                got_h = house_door(h_, here)
                                if got_h == "inside":
                                    end_h = house_inside(h_)
                                    if end_h == "time_box":
                                        continue  # the time box ended inside: run_end, warp home
                                    cell_h, read_h = house_leave(h_)
                                    here, last_pos_t, last_taken = cell_h, time.monotonic(), -1e9
                                    pos_hist.clear()
                                    loot_list, fight_ref, goal_path, lock = [], None, None, None
                                    idle_pos, idle_since = None, time.monotonic()
                                    mode, hplan, house_tries = "search", None, 0
                                    tadv("resumed")
                                    if patrol:  # re-join the loop AHEAD of the return cell
                                        wp_st["i"] = None
                                    ev({"kind": "house_back", "house": h_.name, "at": list(here),
                                        "read": read_h, "expected": list(h_.back)})  # fmt: skip
                                    continue
                                if got_h == "none":
                                    house_tries += 1
                                    if house_tries >= HOUSE_DOOR_TRIES:
                                        fb_why = "the door did not fire"
                                elif got_h in ("noentry", "off"):
                                    tadv("fallback")
                                    hplan, house_fb = None, True
                                    ev({"kind": "house_fallback", "why": f"door {got_h}"})
                                if got_h in ("hit", "fight"):
                                    hplan = None  # the fight first; the rest decides again
                                    continue
                            elif tick - rest_since > HOUSE_WALK_MAX_S:
                                fb_why = "approach not reached"
                            elif goal_path is None or goal_path[-1] != hplan["approach"]:
                                goal_path = route(okr, carved, here, hplan["approach"])
                                n_r = None if goal_path is None else len(goal_path)
                                ev({"kind": "rest_route", "to": list(hplan["approach"]),
                                    "house": h_.name, "len": n_r})  # fmt: skip
                                if goal_path is None:
                                    fb_why = "no route"
                        if fb_why is not None:
                            if trip.state == "walk":
                                tadv("fallback")
                            hplan, house_fb, goal_path = None, True, None
                            ev({"kind": "house_fallback", "why": fb_why})
                    if here is not None and not (trip is not None and hplan is not None):
                        spot = nearest_spot(spots, here)
                        at_spot = spot is not None and cheb2(spot, here) <= REST_NEAR
                        sit_why = rest_sit_why(spot, at_spot, tick - rest_since)
                        if sit_why is not None:
                            press("sit", sit_why)
                            sitting = True
                            rest_since = tick
                            ev({"kind": "rest_start", "cell": list(here), "pct": pct,
                                "sp_pct": spp, "spot": None if spot is None else list(spot),
                                "fallback": not at_spot, "why": sit_why})  # fmt: skip
                            continue
                        if goal_path is None or goal_path[-1] != spot:
                            goal_path = route(okr, carved, here, spot) if spot else None
                            ev(
                                {
                                    "kind": "rest_route",
                                    "to": list(spot) if spot else None,
                                    "len": None if goal_path is None else len(goal_path),
                                }
                            )
                            if goal_path is None:
                                mode = "search"
                # Amendment D: the IDLE watchdog -- searching with no walk click, no fight and no
                # move for IDLE_MAX_S = stuck (the routing fails, or the client will not walk)
                if here != idle_pos or mode != "search":
                    idle_pos, idle_since = here, tick
                elif tick - max(idle_since, last_walk_click) > IDLE_MAX_S or (
                        patrol and dead_end(wp_st["skips"], len(wps))):  # fmt: skip
                    why_s = "dead_end" if patrol and dead_end(wp_st["skips"], len(wps)) else "idle"
                    if why_s == "dead_end" and dead_end_step(
                            int(carved.sum()), tick - last_uncarve) == "uncarve":  # fmt: skip
                        # dungeon@8.6: the map's grid routes the loop; forget our own carves first
                        ev({"kind": "uncarve", "at": None if here is None else list(here),
                            "cells": int(carved.sum()), "why": why_s})  # fmt: skip
                        counts["uncarve"] += 1
                        carved[:] = False
                        last_uncarve = tick
                        wp_st["skips"] = 0
                        idle_pos, idle_since, goal_path = None, tick, None
                        continue
                    ev({"kind": "stuck", "at": None if here is None else list(here), "why": why_s})
                    press("fly", why_s)
                    fly_at = time.monotonic()
                    wp_st["skips"] = 0
                    ev({"kind": "escape", "how": "fly", "why": why_s})
                    idle_pos, idle_since, goal_path = None, tick, None
                    loot_list, fight_ref = [], None
                    here, last_taken = None, -1e9  # Amendment F
                    time.sleep(1.0)
                    continue
                # --- dungeon@4: the WHITE PLANT sweep when passing a spawn area (both searches)
                if mode == "search" and here is not None and lock is None and plant_areas \
                        and a.plant_sweep and (frac is None or frac >= 0.6):  # fmt: skip
                    i_p = pfm.near_area(plant_areas, here, PLANT_NEAR)
                    if i_p is not None and tick - plant_last.get(i_p, -1e9) >= PLANT_EVERY_S:
                        plant_last[i_p] = tick
                        cells_p = plant_cells(plant_areas[i_p], here, ok)
                        found_p = scan("plant", [(c_[0] - here[0], c_[1] - here[1])
                                                 for c_ in cells_p], "sword")  # fmt: skip
                        if found_p is not None:
                            c_p, (u_p, v_p), _rp = found_p
                            ev({"kind": "engage", "by": "plant", "name": None,
                                "rel": list(c_p), "area": i_p})  # fmt: skip
                            if fight_ref is None:
                                fight_ref = {"img": img, "here": here, "t": tick}
                            strike(u_p, v_p, c_p, "plant")
                            lock = {"t": time.monotonic(), "rel": c_p,
                                    "cell": [here[0] + c_p[0], here[1] + c_p[1]]}  # fmt: skip
                            mode, goal_path = "fight", None
                        continue
                # --- SEARCH: the heading walk (or dungeon@4's patrol route)
                near_end = (here is not None and goal_path is not None and len(goal_path) >= 2
                            and max(abs(goal_path[-1][0] - here[0]),
                                    abs(goal_path[-1][1] - here[1])) <= 2)  # fmt: skip
                if mode == "search" and here is not None and (
                        goal_path is None or len(goal_path) < 2 or near_end):  # fmt: skip
                    if patrol and near_end and wp_st["through"] is not None:
                        # --walk-through: the leg ran THROUGH its waypoint to the next one, whose
                        # end we reached; the waypoint is passed (the offline sim: without this the
                        # replan routed back to it and the walk oscillated at gef_fild10 wp 64)
                        pass_waypoint(here)
                    if patrol:
                        goal = patrol_goal(here)
                    elif not area[here[1], here[0]]:  # dungeon@4: a rest spot outside the area
                        goal = nearest_in(area & ~carved, here)
                    else:
                        goal = hf.heading_goal(area & ~carved, here, walk_st, rng)
                    goal_path = None if goal is None else route(okr, carved, here, goal)
                    if patrol and goal is not None and goal_path is None:
                        skip_waypoint(here)  # carved off: the next waypoint ahead
                    elif goal_path:
                        wp_st["skips"] = 0
                    wp_st["through"] = None
                    ni_ = None if not patrol else mroutes.next_index(rt, wp_st["i"])
                    if a.walk_through and ni_ is not None and goal is not None and goal_path:
                        ext_ = through_path(goal_path, route(okr, carved, goal, wps[ni_]))
                        if len(ext_) > len(goal_path):  # a path's last waypoint: no extension
                            goal_path, wp_st["through"] = ext_, goal
                    ev({"kind": "goal", "to": None if goal is None else list(goal),
                        "len": None if goal_path is None else len(goal_path),
                        "turn": walk_st.get("turn"),
                        "wp": None if not patrol else wp_st["i"]})  # fmt: skip
                if mode in ("search", "rest") and here is not None and goal_path \
                        and tick - last_walk >= a.walk_every:  # fmt: skip
                    last_walk = tick
                    # the path from where we are now
                    if here in goal_path:
                        goal_path = goal_path[goal_path.index(here) :]
                    else:
                        goal_path = route(okr, carved, here, goal_path[-1])
                    if wp_st["through"] is not None and (
                            not goal_path or wp_st["through"] not in goal_path):  # fmt: skip
                        pass_waypoint(here)  # --walk-through: its waypoint is behind us now
                    if goal_path and len(goal_path) >= 2:

                        def fits(c: Cell, h: Cell = here) -> bool:
                            u_, v_ = project(h, [(c[0] - h[0], c[1] - h[1])])[0]
                            return in_view(u_, v_) and mz.segment_violates(h, c, zones) is None

                        wt_ = walk_target(goal_path, MR_WALK_AHEAD if mr else a.walk_ahead, fits)
                        if wt_ is not None:
                            _i, c = wt_

                            def usable(c_: Cell, h: Cell = here) -> bool:
                                hh, ww = okr.shape
                                return (0 <= c_[0] < ww and 0 <= c_[1] < hh
                                        and bool(okr[c_[1], c_[0]]) and not carved[c_[1], c_[0]]
                                        and fits(c_))  # fmt: skip

                            # dungeon@8.7: never a click straight north of us (no move request)
                            nxt_ = goal_path[min(_i + 3, len(goal_path) - 1)]
                            c, dodge = column_dodge(here, c, nxt_, usable)
                            if dodge is not None:
                                counts["column_dodge"] += 1
                            rel = (c[0] - here[0], c[1] - here[1])
                            u, v = project(here, [rel])[0]
                            res = hover(u, v)
                            tw_ = None  # --walk-trust (off by default): why the cell is untrusted
                            if a.walk_trust and res["verdict"] == "unknown":
                                bx_ = boxes is not None and boxes.near(
                                    (u, v), wtr.BOX_NEAR_PX, BOX_FRESH_S) is not None  # fmt: skip
                                tw_ = wtr.trust_why(here, c, route_ok=okr, carved=carved,
                                                    zones=zones, npcs=trust_npcs,
                                                    box_near=bx_)  # fmt: skip
                            # dungeon@8.6: the RING's score stands for the red (0 without
                            # the ring), so walk_trust's "unknown + red" carve is the ring's too
                            ring_on = int(res["ring"][0]) if res.get("noentry_ring") else 0
                            act_, why_w = wtr.decide(res["verdict"], ring_on,
                                                     trusted=tw_ is None,
                                                     enabled=a.walk_trust,
                                                     noentry_red=RING_IN_MIN)  # fmt: skip
                            if act_ == "click":
                                stall = stall + 1 if walk_from == here else 0
                                if walk_from != here:
                                    stalls_here.clear()
                                walk_from = here
                                if stall >= STALL_CLICKS:  # clicks that did not move us
                                    ev({"kind": "stall", "at": list(here), "to": list(c)})
                                    turn_heading(walk_st)
                                    goal_path, stall = None, 0
                                    # Amendment C (run 1, 12:3x: 57 stalls at 27,75 -- the turn was
                                    # undone by the next goal's same route): the target the client
                                    # will not walk to leaves the route grid for the run
                                    carve(carved, c, CARVE_R)
                                    stalls_here.append(tick)
                                    if (
                                        sum(1 for t_ in stalls_here if tick - t_ <= 60.0)
                                        >= STUCK_STALLS
                                    ):
                                        ev({"kind": "stuck", "at": list(here)})
                                        press("fly", "stuck")
                                        fly_at = time.monotonic()
                                        ev({"kind": "escape", "how": "fly", "why": "stuck"})
                                        stalls_here.clear()
                                        loot_list, fight_ref = [], None
                                        here, last_taken, goal_path = None, -1e9, None
                                        last_swing = (
                                            -1e9
                                        )  # dungeon@9.1: a jump, the old swings gone
                                        time.sleep(1.0)
                                        continue
                                    # monsters that only MISS write no log line: look around
                                    found = scan("defend", ring(1), "sword")
                                    if found is not None:
                                        c2, (u2, v2), _r2 = found
                                        ev({"kind": "engage", "by": "stall_scan", "name": None})
                                        if strike(u2, v2, c2, "stall_scan"):  # False: walked
                                            lock = {"t": time.monotonic(), "rel": c2, "cell": None}
                                        mode = "fight"
                                    continue
                                click_at(u, v, "walk")
                                last_walk_click = tick
                                rec_w = {"kind": "walk", "from": list(here), "to": list(c),
                                         "clicked": True, "why": mode, "red": res.get("red"),
                                         "ring": res.get("ring")}  # fmt: skip
                                if dodge is not None:
                                    rec_w["dodge"] = dodge
                                if why_w == "trusted":  # --walk-trust: an UNKNOWN read, clicked
                                    counts["walk_trusted"] += 1
                                    rec_w.update({"gate": "trusted", "red": res.get("red")})
                                ev(rec_w)
                            elif act_ == "engage":
                                ev({"kind": "engage", "by": "walk_sword", "name": None})
                                strike(u, v - BODY_UP / 2, rel, "walk_sword")
                                lock = {"t": time.monotonic(), "rel": rel, "cell": list(c)}
                                mode = "fight"
                            else:
                                rec_w = {"kind": "walk", "from": list(here), "to": list(c),
                                         "clicked": False, "why": why_w, "red": res.get("red"),
                                         "ring": res.get("ring")}  # fmt: skip
                                if dodge is not None:
                                    rec_w["dodge"] = dodge
                                if a.walk_trust:
                                    rec_w["trust"] = tw_
                                ev(rec_w)
                                if act_ == "carve":
                                    # dungeon@4 (decision 5): the client calls it a wall -- the
                                    # target leaves the route grid at once and the walk re-plans
                                    # (dungeon@8.6: that cell alone -- the ring names one cell)
                                    noentry_n += 1
                                    carve(carved, c, NOENTRY_CARVE_R)
                                    ev({"kind": "noentry_carve", "at": list(here),
                                        "to": list(c), "r": NOENTRY_CARVE_R})  # fmt: skip
                                    if not patrol:
                                        turn_heading(walk_st)
                                    goal_path = None
                elif (mr and mode == "search" and here is not None and goal_path
                        and len(goal_path) >= 2 and lock is None):  # fmt: skip
                    # MELEE-RING 1 (between walk clicks): the pointer rests on a ring cell AHEAD of
                    # our walk (rotating over three); a SWORD there = a strike at once (arm C)
                    fwd = forward_cells(here, goal_path[1])
                    if fwd:
                        c_w = fwd[watch_i % len(fwd)]
                        watch_i += 1
                        u_w, v_w = project(here, [c_w])[0]
                        v_w -= BODY_UP
                        if in_view(u_w, v_w):
                            res_w = hover(u_w, v_w)
                            if res_w["verdict"] == "sword":
                                ev({"kind": "engage", "by": "cursor", "name": None,
                                    "rel": list(c_w)})  # fmt: skip
                                if fight_ref is None:
                                    fight_ref = {"img": img, "here": here, "t": tick}
                                strike(u_w, v_w, c_w, "cursor")
                                lock = {"t": time.monotonic(), "rel": c_w,
                                        "cell": [here[0] + c_w[0], here[1] + c_w[1]]}  # fmt: skip
                                mode, goal_path = "fight", None
                # dungeon@8.1 (4.05 a5, 2026-10-26 00:21): the readout sat over a bright roof and
                # never read, and the run stopped at 30 s; s2's had failed over sunlit grass. A
                # Fly Wing (a same-map teleport) gives the readout a new background: after
                # POS_FLY_S without a read, at most POS_FLY_MAX a run, POS_FLY_S apart
                if (tick - last_pos_t > POS_FLY_S and tick - fly_at > POS_FLY_S
                        and pos_flies < POS_FLY_MAX):  # fmt: skip
                    ev({"kind": "stuck", "at": None if here is None else list(here),
                        "why": "pos_unread"})  # fmt: skip
                    press("fly", "pos_unread")
                    fly_at = time.monotonic()
                    pos_flies += 1
                    ev({"kind": "escape", "how": "fly", "why": "pos_unread"})
                    idle_pos, idle_since, goal_path = None, tick, None
                    loot_list, fight_ref = [], None
                    here, last_taken = None, -1e9  # Amendment F
                # every Fly Wing restarts the 30 s (s2: a fly after a read gap ended the run)
                if here is None and tick - max(last_pos_t, fly_at) > 30.0:
                    reason = "position unread for 30 s"
                    break
                time.sleep(max(0.0, 1.0 / READ_HZ - (time.monotonic() - tick)))
        except r.Stop as exc:
            reason = f"stop: {exc}"
            raise
        except KeyboardInterrupt:  # the parent's SIGINT (a run stopped by hand): say so
            reason = "stopped_by_parent"
            raise
        finally:
            ev({"kind": "run_end", "reason": reason, "counts": dict(counts),
                "pos_light_unconfirmed": pos_ok.unconfirmed})  # fmt: skip
            blt.stop()
            if tags_log is not None:
                tags_log.close()
                ev({"kind": "tags_banked", "n": n_tags[0]})
            if boxes is not None:
                boxes.stop()
                ev({"kind": "box_watch", "frames": boxes.n, "self_boxes_skipped": boxes.n_self,
                    "spot_boxes_skipped": boxes.n_skip, "paths": dict(boxes.paths),
                    "gpu": boxes.det.info() if boxes.gpu else None,
                    "spots_ignored": [list(c) for c in (box_spots.misses if box_spots else {})
                                      if box_spots and box_spots.ignored(c)]})  # fmt: skip
            if sitting:
                agent_raw.keys(keys_["stand"])
            if end_escape_needed(time.monotonic(), last_taken, st.hist, reason):  # dungeon@8.5
                press("fly", "end")
                ev({"kind": "end_escape", "how": "fly", "reason": reason,
                    "hp": None if not st.hist else round(st.hist[-1][1], 3)})  # fmt: skip
                time.sleep(1.0)
            if reason == "death":
                x, y = gx0 + gv.RETURN_TO_GAME[0], gy0 + gv.RETURN_TO_GAME[1]
                agent_raw.move(x + 4, y + 3)
                time.sleep(0.08)
                agent_raw.move(x, y)
                time.sleep(0.3)
                agent_raw.click(x, y)  # the death dialog's known step (its second button)
                time.sleep(1.5)
                if r.is_state(screen, gv.DEAD_STATE):
                    raise r.Stop("dungeon@1: the death dialog stayed after its known step")
                for cmd in ("@alive", "@heal"):
                    cr.gm_line(agent_raw, screen, cmd, conf["job"], crk)
                    time.sleep(0.8)
                bench.close_chat(agent_raw, screen)
            # 13:19: a stopped run left the Crusader at 30 % HP among orcs with no runner: after
            # run_end (outside the measured window) it goes home. dungeon@8 (4.05 a1, 2026-10-25
            # 22:04): after a DEATH too -- @alive revives it on the spot, and the Orc Lord that
            # killed it killed it again there
            try:
                cr.gm_line(agent_raw, screen, f"@warp {CLEAR_STAND[0]} {CLEAR_STAND[1]} "
                           f"{CLEAR_STAND[2]}", conf["job"], crk)  # fmt: skip
                time.sleep(3.0)
                bench.close_chat(agent_raw, screen)
            except Exception as exc:  # noqa: BLE001 -- recorded; the next setup checks again
                print(f"end warp failed: {exc!r}", flush=True)
            print(r.to_png(screen.full(), out / "end.png"), flush=True)
    t1 = r.ns()
    evf.close()
    n_pk = -1
    try:
        events, _anchor = rs.write_packets(out, t0, t1)
        n_pk = len(events)
    except Exception as exc:  # noqa: BLE001 -- the run is still recorded; the judge says so
        print(f"packets not written: {exc!r}")
    man = {"sid": sid, "version": VERSION if a.engage == "defend_scan" else MR_VERSION,
           "engage": a.engage, "search": a.search, "loot": a.loot, "strategy": a.strategy,
           "fixes": fixes_of(a),
           "seed": a.seed, "char": a.char, "map": map_, "steal": a.steal, "bank_tags": bank,
           "minutes": a.minutes, "reason": reason, "counts": dict(counts), "t0_ns": t0,
           "t1_ns": t1, "packets": n_pk, "params": strat}  # fmt: skip
    (out / "manifest.json").write_text(json.dumps(man, indent=1))
    print(json.dumps({"sid": sid, "reason": reason, "counts": dict(counts), "packets": n_pk}),
          flush=True)  # fmt: skip
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)  # fmt: skip
    sub = ap.add_subparsers(dest="cmd", required=True)
    t = sub.add_parser("run")
    t.add_argument("--strategy", required=True, choices=sorted(STRATEGIES))
    t.add_argument("--minutes", type=float, default=45.0)
    t.add_argument("--seed", type=int, required=True)
    t.add_argument("--label", default="r")
    t.add_argument(
        "--engage",
        choices=["defend_scan", "melee_ring"],
        default="defend_scan",
        help="the engagement source (Batt 13:4x): defend_scan (3.98) or melee_ring",
    )
    t.add_argument(
        "--loot",
        choices=["v1", "v2", "rhythm", "trim"],
        default="v1",
        help="the loot step: v1 (3.98's list + sweep), v2 (Batt decision 4: changed cells first, "
        "a budget per fight, no re-hover of empty cells; 4.01), rhythm (4.02: v2's order, 2.5 s "
        "and 2 pickups per fight) or trim (gef10-eyes-loot.md E1: v1's list, nearest first, at "
        "most LOOT_TRIM_HOVERS hovers, no sweep)",
    )
    t.add_argument(
        "--search",
        choices=["heading", "patrol"],
        default="heading",
        help="dungeon@4: the heading walk (default) or Batt's patrol loop (config/routes/MAP.yaml)",
    )
    t.add_argument(
        "--boxes",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="the box watcher (the third trigger, 1 Hz in its own thread; --box-model)",
    )
    t.add_argument(
        "--box-model",
        choices=["map", "v1"],
        default="map",
        help="the box watcher's model (Batt 2026-11-07, T-11): map = the map's own model when "
        "unit_detector.MAP_MODELS has one (xmas_dun02), else v1; v1 = v1 everywhere (rollback)",
    )
    t.add_argument(
        "--box-strike",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="dungeon@8.8 (rogue-xmas02.md 4M; OFF by default, switched on by a pre-registration): "
        "a box fight first waits for our walk to end, then hovers a box grabbed after that and "
        "strikes on its SWORD; else the ring scan as before",
    )
    t.add_argument(
        "--walk-stop",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="dungeon@9.2 (rogue-xmas02.md 4Q, pilot p10; OFF by default): a ring-1 strike whose "
        "first click scrolls the scene before the lock arrow / our damage line hit the ground: "
        "stop the burst, take no lock, and skip that cell in the defend scan for a few seconds",
    )
    t.add_argument(
        "--self-recheck",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="dungeon@9.3 (rogue-xmas02.md 4R, pilot p11; OFF by default): a defend-scan SWORD at "
        "a point on our own sprite (the N / S cells' body points) counts only if a second read "
        "0.4 s later is a SWORD too; else the scan goes on",
    )
    t.add_argument(
        "--plant-sweep",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="dungeon@4's White Plant cursor sweep (dungeon@5: OFF, Batt decision 6)",
    )
    t.add_argument(
        "--box-detector",
        choices=["cpu", "gpu", "ab"],
        default="gpu",
        help="dungeon@8.9 (gpu-live-detector.md option A, Batt 2026-11-07): the box watcher's "
        "detections on the vision worker's GPU detect server with the CPU behind it (gpu, the "
        "DEFAULT since pilot p8 passed G1 / G2, rogue-xmas02.md 4N: without a detect-server step "
        "the CPU serves), on the CPU only (cpu), or ab: the GPU in the background and each box "
        "target's fresh detection alternating GPU / CPU (the pilot's arms; needs --box-now)",
    )
    t.add_argument(
        "--box-now",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="dungeon@8.9 (rogue-xmas02.md 4N; needs --box-strike): after the settle the box "
        "target asks for a detection NOW instead of waiting for the 1-s rhythm, and hovers ONCE "
        "(the box centre)",
    )
    t.add_argument(
        "--box-ignore",
        type=int,
        default=BOX_IGNORE_AFTER,
        help="dungeon@5 (decision 4): ignore a box spot after this many no-SWORD box fights "
        "(0 = off)",
    )
    t.add_argument(
        "--ag-match",
        type=float,
        default=None,
        help="the Auto Guard icon bar (default survive.AG_MATCH_DUNGEON, Batt decision 7)",
    )
    t.add_argument(
        "--char",
        default="crusader",
        choices=sorted(CHARS_CONF),
        help="dungeon@6: the test character (crusader.py --char)",
    )
    t.add_argument("--map", default=MAP, help="dungeon@6: the map (its zones file is required)")
    t.add_argument(
        "--steal",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="dungeon@7: Batt's steal-first, ONE Steal on every monster while the SP pays for it",
    )
    t.add_argument(
        "--clear-map",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="dungeon@8 (rogue-gef10.md Amendment A4): the setup types @killmonster2 "
        "after the warp to the map, so its MVP (gef_fild10's Orc Lord, 2 h "
        "respawn) is absent until the flee rule is proven; everything respawns",
    )
    t.add_argument(
        "--walk-ahead",
        type=int,
        default=WALK_AHEAD,
        help="the walk click's target, this many path cells ahead (default 7; the long legs of "
        "gef10-idle-study.md 6.1 use more, so the next click lands before the walk ends)",
    )
    t.add_argument(
        "--walk-every",
        type=float,
        default=WALK_EVERY_S,
        help="seconds between walk decisions, from a decision's START (default 1.2). One decision "
        "takes ~0.9 s and a 5-6 cell path ~0.9 s, so at 1.2 s the Rogue stands before the next "
        "click (gef10-idle-study.md 4a); a shorter timer re-clicks before the walk ends",
    )
    t.add_argument(
        "--walk-through",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="--search patrol: continue a leg along the route to the NEXT waypoint, so the click "
        "is not capped at the current one (gef10-idle-study.md 6.1; OFF by default)",
    )
    t.add_argument(
        "--walk-trust",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="the trusted walk cell (docs/planning/gef10-cursor-unknown.md; OFF by default, "
        "switched on by a pre-registration): a walk target whose cursor read stays UNKNOWN is "
        "clicked when walk_trust.trust_why trusts its cell (route grid + the landing cells "
        "beyond it, the zones, >= NPC_MIN cells from every NPC, no fresh box near); SWORD still "
        "engages, NO-ENTRY (or an UNKNOWN with the ring's red) still carves",
    )
    t.add_argument(
        "--miss-cue",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="dungeon@9.1 (docs/planning/gef10-miss-cue.md; OFF by default): a monster's missed "
        "swing at us (the 'Miss' text drawn at the attacker beside us, miss_cue.read) starts a "
        "fight like a hit does; ignored while sitting (no stand toggle on a miss)",
    )
    t.add_argument(
        "--npc-guard",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="dungeon@9.0b (rogue-gef10.md Amendment P; OFF by default): no strike / Steal / loot "
        "click while our cell is within NPC_NO_FIGHT cells of an L3 NPC (c2: a strike opened the "
        "bulletin board's dialog)",
    )
    t.add_argument(
        "--rest",
        choices=["spot", "house"],
        default="spot",
        help="where a rest sits: spot (the default, as before: config/dungeon/MAP.json's rest "
        "spots, else where it stands) or house (docs/planning/gef10-house-rest.md; OFF by "
        "default, switched on by a pre-registration; gef_fild10 only): walk to the nearest SEALED "
        "orc house, ONE click on its door, sit inside in_orcs01 at once, stand, ONE click on the "
        "house's own exit; any unexpected map change stops the run",
    )
    t.add_argument("--bank-tags", action=argparse.BooleanOptionalAction, default=None,
                   help="dungeon@6: bank the raw name-tag band at every strike (default: on off "
                   "orcsdun01)")  # fmt: skip
    a = ap.parse_args()
    if a.cmd == "run" and a.ag_match is None:
        import survive as sv

        a.ag_match = sv.AG_MATCH_DUNGEON
    return run(a)


if __name__ == "__main__":
    raise SystemExit(main())
