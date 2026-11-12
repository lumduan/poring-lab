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

--player-mode (dungeon@9.35, OFF by default; docs/planning/player-mode.md, Batt 2026-11-12): the
hunt as a NORMAL PLAYER, for a public rAthena that permits bots (ADR-0023's declared mode), where
the account is no GM. The run types NO line (every line this runner types goes through typed_line,
which refuses first), reads nothing from the lab's DB, starts where the person left the character
(her cell read on the minimap readout) with the stock she brought (read on the hotbar: at least
PLAYER_MIN_WINGS Fly Wings and PLAYER_MIN_HEALS heal items), and ends by the run's own Fly Wing
escape: no warp home, no @alive / @heal, no level hold, no top-up, no staging. dungeon@9.35b (Batt
2026-11-12): then ONE Butterfly Wing home (its hotbar key, --player-home-key) when its count reads
>= 1; and on a map whose KB lists a boss spawn, with the boss guard off, one WARNING line at the
start (never a refusal).

    dungeon_hunt.py run --strategy A|B|C|H --minutes 45 --seed S [--label L] [--search patrol]
                        [--char crusader|thief|rogue] [--map M] [--steal] [--bank-tags]
                        [--walk-trust] [--rest spot|house] [--player-mode]
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
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import bare_steal as bs  # noqa: E402 -- dungeon@9.27 (--bare-steal): the pure core

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
# dungeon@9.35b (--player-mode's Butterfly Wing home, Batt 2026-11-12): each character's hotbar key
# for the Butterfly Wing (CHARS_CONF "home_key"), F8 -- the first row-1 key no character uses (F1
# potion, F2 Fly Wing, F3 Steal / Auto Guard, F4 the Knife opener, F5 the dagger / Heal, F6 + F7
# --heal-candy's). It joins the run's keys (keys_["home"]) under --player-mode only, so the lab's
# own key checks (clear-bag's Eqp guard, --steal-opener's) are unchanged
HOME_KEY = "F8"
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
# --still-strike (dungeon@9.4, rogue-xmas02.md 4S, pilot p12; Batt 2026-11-08 chose option b):
# far strikes (2+ cells) clicked WHILE WE WALKED started no attack in 10 of 14 (p10 + p11),
# standing in 6 of 20: moving, the client resolves a click at our SERVER position (~0.5 s ahead
# of the frame). So a far strike first waits for a still scene (STILL_N consecutive frame pairs
# scrolling < STILL_PX, at most STILL_MAX_S) and aims again: the box path's detection is taken
# after it; walk_sword's point is carried by the scroll seen meanwhile and hovered again.
STILL_PX, STILL_N, STILL_MAX_S = 2.0, 3, 1.5
# --lead-strike (dungeon@9.5, rogue-xmas02.md 4V, pilot p14; Batt 2026-11-08 ~18:0x: "aim for the
# monsters that are walking"): box strikes on a target WALKING at the grab were class D in 5 of 6
# (p12 + p13, target_motion.py), on a standing one in 1 of 25; the walker moved ~1 cell between
# the grab and the click. So the box path takes a SECOND detection LEAD_GAP_S after its first,
# matches the same sprite (centre within LEAD_MATCH_PX), and when it moves faster than
# LEAD_MIN_PX_S on a still scene, hovers where it will be: its centre + velocity x LEAD_T_S
# (p13: the hover -> verdict 232 ms + the second detection ~45 ms + the stream ~70 ms), the lead
# at most LEAD_MAX_PX. No SWORD there -> its current point once (the fallback).
LEAD_GAP_S, LEAD_MATCH_PX, LEAD_MIN_PX_S, LEAD_T_S, LEAD_MAX_PX = 0.12, 40.0, 25.0, 0.35, 64.0
# --quick-drop (dungeon@9.6, rogue-xmas02.md 4W, pilot p15; Batt 2026-11-08 ~19:5x: "a strike that
# does not connect within ~1.5 s: give it up and go for a new monster at once"): a missed strike
# held us ~7 s (the burst's 3.0 s, then LOCK_NO_HIT_S 3.5 s without our hits; p12 / p13 / p13r
# 49-89 s a run). Measured on p12-p14's 106 good strikes (K / A): the arrow or our damage line
# shows by 2.0 s in all but 6 (by 1.5 s: all but 23 -- hence 2.0, not 1.5), and after an arrow our
# first VISIBLE hit (the packet + the reader's ~0.5 s) comes within 2.0 s in 57 of 58. So: no arrow
# and no damage QUICK_ARROW_S after the click -> no lock; an arrow but no hit of ours QUICK_HIT_S
# after it -> the lock drops; after either, the box path runs again (the nearest box), at most
# QUICK_RETRY times a fight, before the ring scan.
QUICK_ARROW_S, QUICK_HIT_S, QUICK_RETRY = 2.0, 2.0, 2
# --quick-drop-scaled (dungeon@9.38, rogue-xmas02.md 4DG; Batt 2026-11-12: "test a stricter
# --quick-drop"; 4CY: in 10 of p88 + p89's 28 drops our attack came <= 2 s after the drop): with
# --quick-drop, the lock's NO-HIT window after the arrow grows with the strike's distance (cells,
# Chebyshev, the strike's rel): QUICK_HIT_S + QUICK_PER_CELL x cells, at most QUICK_HIT_MAX_S
# (quick_hit_window). Chosen from those 28 drops (4DG): QUICK_PER_CELL is FAR_PER_CELL_S (the
# walk-up's measured time a cell), and QUICK_HIT_MAX_S is LOCK_NO_HIT_S -- a longer window never
# fires, because the plain "no hits" unlock takes the lock 3.5 s after it anyway. The no-ARROW
# drop (QUICK_ARROW_S / --far-single's window) is unchanged: 5 of the 10 were no-arrow drops.
QUICK_PER_CELL, QUICK_HIT_MAX_S = 0.2, 3.5
QUICK_SCALED_VERSION = "9.38"
# --kill-gap (dungeon@9.13, rogue-xmas02.md 4AF): at Base 99 the Battle Log shows NO exp line, so
# the runner never sees a kill: after the killing blow the lock waited LOCK_NO_HIT_S (3.5 s, ~4.0 s
# with the reader) for "no hits", then the defend scan (~2.3 s) found nobody -- p21: a median 6.46 s
# from the kill (packets) to fight_end, 276.8 s of the run's 1,500 (fight_time.py). Our hits on a
# living target come every 0.47 s (packets, p16-p22: p50 0.47, p90 0.48 s). So after KILL_GAP_HITS
# of our hits on the lock, none for KILL_GAP_S counts as the kill: the lock goes and, when quiet,
# the fight ends. 9.13c (after p24): KILL_GAP_HITS 2 -> 5 -- p24's 17 false kills were mostly short
# contacts (2-4 of our hits, then the target walked off alive); 5 keeps 27 of its 28 real ones and 3
# of the 17 false ones (a real kill took 3-22 hits, median 15).
KILL_GAP_S, KILL_GAP_HITS = 1.5, 5
# dungeon@9.34 (Batt 2026-11-12, rogue-xmas02.md 4CW): an EXP or a Job EXP line in the Battle Log =
# the monster is DEAD, FIRST. One kill prints both lines: the other kind within EXP_PAIR_S of the
# counted one is the same kill. Once the client has printed any exp line in a run, --kill-gap infers
# no kill (the client says it). The Thai dev server prints EXP '0' at Base 99; the lab's 2021 client
# prints no 0-EXP line, so the lab's Base-99 Rogue still relies on --kill-gap (unchanged there).
EXP_PAIR_S = 1.0
# 9.13d (after p37, rogue-xmas02.md 4AR): after a loot step that clicked an item, the next walk
# click waits for a position read taken LOOT_SETTLE_S after the step (the pickup walk moved us; a
# target computed from the stale cell was dropped by the client: 8 of p37's 11 unsent walk
# clicks came 0.7-4.1 s after such a step), at most LOOT_SETTLE_MAX_S
LOOT_SETTLE_S, LOOT_SETTLE_MAX_S = 0.8, 3.0
# --loot-first (dungeon@9.16, rogue-xmas02.md 4AT; Batt 2026-11-09: "fix the looting first").
# p38 (9.13d) showed why kills at Base 99 still left their items:
# (1) after a kill the fight ended ("quiet kill") and on the NEXT tick any box on the screen
#     (--engage-screen) started a new fight BEFORE the loot step ran, so the loot list waited
#     until no box was in view (p38: kills at 102, 118, 131, 147 and 157 s, one loot step at
#     161 s, its 9 hovers around where she stood THEN, 0 picks);
# (2) that new fight had no lock yet, so the quiet-kill rule ended it in the same tick, again
#     and again for 3 s after the kill (157 such pairs in p38's first 3 min), and no box was
#     struck meanwhile;
# (3) a defend scan that read the PICKUP hand passed it by (Batt's clip 2; p38 at 184.9 s: two
#     hands read, then a loot step with an empty list).
# With the flag: (1) a box ALONE starts no fight while a kill's loot step is pending (a hit, an
# HP drop or a Miss still does); (2) the quiet-kill rule ends only a fight that began before
# the kill; (3) a defend scan that found no sword clicks the first hand it read, unless a hit
# came within 1 s, and that spot joins the loot list (the loot step after the fight looks
# around it).
LOOT_FIRST_VERSION = "9.16"
# --quiet-scan (dungeon@9.17, rogue-xmas02.md 4AW; Batt 2026-11-09 ~12:3x, his clip 1: "if no
# damage happened in the last 5 s, there is no need to scan"): the ring scan for an attacker
# ("defend": a fight with no lock, and after a walk stall) runs only when the screen showed
# damage within QUIET_SCAN_S -- a hit line on us, an HP drop, a Miss at us, or a damage line of
# ours. p38-p40 (packets, fight_time Q1): 39 / 28 / 34 defend scans came with no hit on us in the
# 5 s before; they found a monster 7 times in 101 and took ~75-100 s a run.
QUIET_SCAN_S = 5.0
EXPLORE_LEG_MAX_S = 150.0  # --explore (dungeon@9.14): a region not reached by then is given up
# --walk-pick (dungeon@9.15, rogue-xmas02.md 4AM): a walk target fits only when the cell the CLIENT
# picks under its projected pixel (picked_cell: the camera ray's first tile top) is walkable and
# within WALK_PICK_TOL of it. p28-p30 (packets): such clicks went unsent 17 of 39 times, the others
# 17 of 869; p30's stuck Fly Wing was 4 dropped clicks at (161, 116) on raised floors.
WALK_PICK_TOL = 1
# --walk-pick-step (dungeon@9.15c, rogue-xmas02.md 4AU): when NO path cell passes the pick check,
# 9.15b clicked the plain target -- p38 (offline replay of the client's picking): 7 of its 10
# unsent walk clicks were exactly such clicks, one 21-s episode on the ramp at (153-164, 116-122)
# where a raised block (altitude 40) south of her covers the pixels of every cell around her (the
# client picked cells ~6 rows off; no pixel within 160 px picked the target). Instead: the cell
# within WALK_PICK_STEP_R that passes the pick check and that the server walks us to on one click,
# nearest the goal by grid steps and nearer than we are; 9.15b's plain click stays the last resort.
WALK_PICK_STEP_R = 9
# --engage-screen (dungeon@9.7, rogue-xmas02.md 4X, pilot p16; Batt 2026-11-08 ~19:5x: "6 cells is
# still too few: strike within what the screen shows, the nearest monster first"): the patrol
# engaged a box only within BOX_NEAR_PX (~3 cells) and the box path took one within BOX_TARGET_PX
# (~6); with the flag both take ANY monster box on the screen whose body point is in view (not
# under a UI window), the nearest to our feet first (BoxWatch.near already orders by distance).
BOX_SCREEN_PX = 4000.0  # beyond any distance on the 1280 x 720 game region
# The BOSS GUARD of --engage-screen (Batt 2026-11-08 ~21:5x, Amendment J: "on, except the boss and
# its minions"): the xmas02 model has no class for them (Stormy Knight, its summons Garm Baby /
# Christmas Goblin), so they are known by NAME: a Battle Log line whose bracketed name fits one
# (boss_of) -> the runner's own Fly Wing escape, and no box engagement for BOSS_AVOID_S. Every run
# starts with @killmonster2 (the MVP dead; it respawns 60-70 min later), so in a 30-min run this is
# the backstop. The names come from the KB (boss_names: the map's boss spawns + their summons).
BOSS_AVOID_S = 30.0
# --boss-walk (dungeon@9.18, rogue-xmas02.md 4AZ; Batt 2026-11-09 ~19:4x: "flee, the dog hits hard
# too; if you can walk away in another direction, walk"): a guard on one of the boss's SUMMONS
# (a Garm Baby: a regular spawn here too, walk 450 ms a cell, chase 12; the Rogue walks ~150) walks
# away instead of a Fly Wing -- ONE click to the pickable, one-click-reachable cell in view that is
# farthest from us, at least BOSS_WALK_MIN cells -- then no new walk click and no boss line for
# BOSS_WALK_GRACE_S. A boss line after that, or more than BOSS_WALK_MAX walk-aways in
# BOSS_WALK_WINDOW_S, or no cell, takes today's Fly Wing. The boss ITSELF always takes the Fly Wing.
BOSS_WALK_R, BOSS_WALK_MIN, BOSS_WALK_GRACE_S = 14, 8, 2.5
BOSS_WALK_MAX, BOSS_WALK_WINDOW_S = 2, 60.0
# --garm-fly (dungeon@9.19, rogue-xmas02.md 4BA; Batt 2026-11-09 ~20:4x: "fly wing when see garm
# baby i[mmediately]"): the map's detector learns a Garm Baby class (xmas02-detector.md Amendment
# M); a box of an ALARM class in a fresh detection (<= GARM_FRESH_S old) takes the boss guard's Fly
# Wing at once -- before contact, where the Battle Log line came only after it. A model without
# the class (the deployed one until M's evaluation passes) gives no alarm box: the flag is inert.
ALARM_CLASSES = ("garm_baby",)
GARM_FRESH_S = 1.5
# --garm-confirm N (dungeon@9.19b, rogue-xmas02.md 4BD; Batt 2026-11-10 09:2x, option (a)): the
# Fly Wing waits for alarm boxes in N CONSECUTIVE detections (the watcher's ~1-s rhythm). p44's
# one false garm_baby box (a Cruiser under the Rogue) stood in a single detection of 1,568; N = 1
# is 9.19 unchanged.
GARM_CONFIRM = 1
# --far-single (dungeon@9.8, rogue-xmas02.md 4Z, pilot p18; Amendment J item 2a, "why far strikes
# miss"): on p16 the strikes 2-6 cells away missed 5 of 41, 7-8 cells 19 of 30, 9-12 cells 33 of
# 35. The packets: a click on a monster out of reach makes the CLIENT walk to it first (a walk
# request, not an attack), and the burst re-clicked the SAME screen point every BURST_GAP_S while
# the camera scrolled with her: that re-click landed on the floor and cancelled the approach (3-5
# walk requests in 4 s on the far misses; the far hits mostly took ONE click). So a strike FAR_CELLS
# or more away clicks ONCE and waits FAR_BASE_S + FAR_PER_CELL_S a cell (at most FAR_MAX_S) for
# the arrow or our damage line -- the walk-up included -- re-clicking never.
FAR_CELLS, FAR_BASE_S, FAR_PER_CELL_S, FAR_MAX_S = 4, 1.0, 0.2, 3.5
# --near-single (dungeon@9.25, rogue-xmas02.md Study S-LF5 proposal R2; Batt 2026-11-11 "study and
# fix" the (104,192) "misread"): the same one-click rule from 2 cells. In p40-p53 the burst's
# re-click at 2-3 cells never helped (every first click that sent anything sent it within 0.375
# s) but walked her >= 2 cells off a live target 26 times in 68 re-clicks (~21 s a run), and one
# such floor walk, acked inside her attack motion, was cut short by the client: the 2.6-s
# client / server desync of p53. 0-1 cells keep the burst (20 strikes there sent nothing at first).
NEAR_SINGLE_VERSION = "9.25"
NEAR_SINGLE_CELLS = 2
# --near-single-still (dungeon@9.25b, R2b; rogue-xmas02.md 4BT, Batt 2026-11-11 "adjust and
# retry"): R2 dropped EVERY 2-3-cell re-click and its late-failed strikes rose (6 vs 3, p57 + p58).
# The floor walk-off needs the camera to have SCROLLED with her walk-up; a re-click on a still
# scene re-aims at a sprite that is still there. So a 2-3-cell strike re-clicks only while the
# scene moved less than WALK_STOP_PX since its first click; once it scrolled, no more re-clicks.
NEAR_STILL_VERSION = "9.25b"
# --far-approach (dungeon@9.10, rogue-xmas02.md 4AC): p19 (--far-single) still missed 26 of 28
# strikes 9+ cells away (7-8 cells: 6 of 20; 2-6: 4 of 24): too far for one click to carry. So a
# box target APPROACH_CELLS or more away is walked toward first -- a walk click on the cell
# APPROACH_KEEP cells short of it on the line -- and the box path looks again once that walk has
# ended (the settle and the still wait), at most APPROACH_MAX times a fight. No ring scan and no
# fight end while an approach walk is under way.
APPROACH_CELLS, APPROACH_KEEP, APPROACH_MAX, APPROACH_HOLD_S = 9, 4, 2, 3.0
# --skip-own-cells (dungeon@9.9, rogue-xmas02.md 4AB, Amendment J item 2c, "the misses on her own
# sprite"): p16 + p17's 24 own-body strikes (the N / S cells, whose hover point lies on her own
# sprite) missed 10 times, 9 of them south; the packets put the monster ON the clicked cell in only
# 2 of 24 -- the SWORD came from a neighbour's sprite reaching over her, and a click through her
# own sprite often started no attack. So the defend scan skips a cell whose hover point is on her
# sprite (in_self_box) and hovers on: the neighbour is struck where it stands.
CURSOR_WAIT_S = 0.35
LOOT_MAX_HOVERS, LOOT_MAX_PICKS, LOOT_MAX_S = 30, 10, 25.0  # one loot step's bounds
# --loot trim (docs/planning/gef10-idle-study.md, gef10-eyes-loot.md E1): v1's list, nearest first,
# capped at this many cell HOVERS (cells out of view not counted), and no sweep. 80 of 84 pickups
# of c5b-c7 came within the first 9 hovers; 1,180 of 1,379 loot-step seconds came after the last
LOOT_TRIM_HOVERS = 9
# dungeon@9.32 (--loot-aim; rogue-xmas02.md Study S-IDLE, Batt 2026-11-12 "build them"): the trim
# sweep hovers her 3 x 3 nearest-first in coordinate order, but a natural drop lands ON the death
# cell (74 / 77, packets p67-p70), one cell from her (224 / 238 kills). The nearest monster box
# (within LOOT_AIM_R cells) in the watcher's recent detections is mostly that cell (below). So: its
# cell first, then its neighbours, and at most LOOT_AIM_HOVERS hovers a kill when every kill of
# the step has an aim (else today's 9).
LOOT_AIM_VERSION = "9.32"
LOOT_AIM_HOVERS = 5
LOOT_AIM_R = 2  # the box's cell within this many cells (Chebyshev) of her cell
LOOT_AIM_PX = 40.0  # the box's foot within this many px of that cell's projected point
LOOT_AIM_HIST = 4  # the watcher's last detections looked back through (newest first) ...
LOOT_AIM_AGE_S = 4.5  # ... no older than this: a kill is inferred ~1.5 s after the last hit,
# when the dead monster is often gone from the newest detection. Replayed on p69 + p70 + p73 (the
# runner's own aim_rel, flat ground): the last 4 detections, our own sprite NOT left out (a
# monster next to her overlaps it; with self_box 80 kills had no aim, without 39) -> the death cell
# exact 57, within one cell 55, off 11, no aim 39; kills with a natural drop: 42 / 46 within one.
AIM_GRID: list[tuple[int, int]] = [(dx, dy) for dx in range(-LOOT_AIM_R, LOOT_AIM_R + 1)
                                   for dy in range(-LOOT_AIM_R, LOOT_AIM_R + 1)
                                   if (dx, dy) != (0, 0)]  # fmt: skip


def aim_rel(boxes_xyxy: Sequence[Sequence[float]], uv: Any) -> tuple[int, int] | None:
    """PURE (dungeon@9.32): the cell (relative to her) of the nearest monster box -- its foot (the
    box's bottom centre) within LOOT_AIM_PX of an AIM_GRID cell's projected point ``uv`` (one row
    per AIM_GRID entry); the smallest Chebyshev distance wins, then the pixel distance. None: no
    box near her."""
    pts = np.asarray(uv, dtype=float)
    best: tuple[tuple[int, float], tuple[int, int]] | None = None
    for x0, _y0, x1, y1 in boxes_xyxy:
        d = np.hypot(pts[:, 0] - (x0 + x1) / 2, pts[:, 1] - y1)
        i = int(np.argmin(d))
        if float(d[i]) > LOOT_AIM_PX:
            continue
        rel = AIM_GRID[i]
        key = (max(abs(rel[0]), abs(rel[1])), float(d[i]))
        if best is None or key < best[0]:
            best = (key, rel)
    return None if best is None else best[1]


def aim_order(todo: Sequence[Cell], aims: Sequence[Cell]) -> list[Cell]:
    """PURE (dungeon@9.32): the aimed cells first, then their neighbours (Chebyshev 1), then the
    rest; each group keeps ``todo``'s own order (nearest-first)."""

    def group(c: Cell) -> int:
        if c in aims:
            return 0
        return 1 if any(max(abs(c[0] - a_[0]), abs(c[1] - a_[1])) <= 1 for a_ in aims) else 2

    return sorted(todo, key=group)


def aim_cap(n_kills: int, n_aims: int) -> int | None:
    """PURE (dungeon@9.32): the hover cap of a loot step whose ``n_kills`` (<= 55 s old) all have an
    aim: LOOT_AIM_HOVERS a kill, never above LOOT_TRIM_HOVERS; None (today's cap) otherwise."""
    if n_kills <= 0 or n_aims < n_kills:
        return None
    return min(LOOT_TRIM_HOVERS, LOOT_AIM_HOVERS * n_aims)


# dungeon@9.33 (--loot-items MODEL; Batt 2026-11-12: "I see the bot spend time looking for items
# every time"; xmas02-detector.md O22): the loot step asks the floor-item model (a GPU_WEIGHTS name)
# once, on a fresh frame. Item boxes near the step's kills -> hover those cells (each with its
# neighbours, at most LOOT_ITEMS_HOVERS a seen item) and nothing else; none -> the sweep is SKIPPED
# (~70 % of the loot steps found nothing, ~3.7 s each). A failed detection -> today's trim sweep.
LOOT_ITEMS_VERSION = "9.33"
LOOT_ITEMS_CONF = 0.25  # fi_eval.CONF: the operating point the item model's bars were scored at
LOOT_ITEMS_PX = 30.0  # an item box's centre within this many px of a cell's projected point
LOOT_ITEMS_HOVERS = 3  # hovers for one seen item: its cell, then its nearest neighbours
LOOT_ITEMS_CLASS = "floor_item"
ONNX_TAIL = "-last-736x1280.onnx"  # the deployed ONNX name: <GPU_WEIGHTS name> + this
ITEM_GRID: list[tuple[int, int]] = [(dx, dy) for dx in range(-4, 5) for dy in range(-4, 5)]


def item_rels_on(boxes: Sequence[Any], uv: Any, grid: Sequence[tuple[int, int]],
                 conf: float = LOOT_ITEMS_CONF,
                 max_px: float = LOOT_ITEMS_PX) -> list[tuple[int, int]]:  # fmt: skip
    """PURE (dungeon@9.36, 4DA amendment): ``item_rels`` on any cell grid (``uv`` = one projected
    point per ``grid`` entry): the recheck's wider RECHECK_GRID."""
    pts = np.asarray(uv, dtype=float)
    out: list[tuple[int, int]] = []
    for b in boxes:
        if LOOT_ITEMS_CLASS not in (getattr(b, "cls", None), getattr(b, "species", None)):
            continue
        if float(getattr(b, "score", 0.0)) < conf:
            continue
        d = np.hypot(pts[:, 0] - (b.x0 + b.x1) / 2, pts[:, 1] - (b.y0 + b.y1) / 2)
        i = int(np.argmin(d))
        if float(d[i]) <= max_px and grid[i] not in out:
            out.append(grid[i])
    return out


def item_rels(boxes: Sequence[Any], uv: Any, conf: float = LOOT_ITEMS_CONF,
              max_px: float = LOOT_ITEMS_PX) -> list[tuple[int, int]]:  # fmt: skip
    """PURE (dungeon@9.33): the cells (relative to her) of the floor-item boxes -- class
    LOOT_ITEMS_CLASS (or that species), score >= ``conf``, the box centre within ``max_px`` of an
    ITEM_GRID cell's projected point ``uv`` (one row per ITEM_GRID entry); one cell once."""
    pts = np.asarray(uv, dtype=float)
    out: list[tuple[int, int]] = []
    for b in boxes:
        if LOOT_ITEMS_CLASS not in (getattr(b, "cls", None), getattr(b, "species", None)):
            continue
        if float(getattr(b, "score", 0.0)) < conf:
            continue
        d = np.hypot(pts[:, 0] - (b.x0 + b.x1) / 2, pts[:, 1] - (b.y0 + b.y1) / 2)
        i = int(np.argmin(d))
        if float(d[i]) <= max_px and ITEM_GRID[i] not in out:
            out.append(ITEM_GRID[i])
    return out


def items_plan(items: Sequence[Cell], plan: Sequence[Cell] | set[Cell],
               per_item: int = LOOT_ITEMS_HOVERS) -> list[Cell]:  # fmt: skip
    """PURE (dungeon@9.33): the cells to hover for the seen items (absolute), in order -- each
    item's own cell, then its plan neighbours nearest it (Chebyshev, then the cell), at most
    ``per_item`` cells an item, one cell once; an item outside the plan is passed over."""
    pl = set(plan)
    out: list[Cell] = []
    for it in items:
        if it not in pl:
            continue
        near_ = sorted((c for c in pl if max(abs(c[0] - it[0]), abs(c[1] - it[1])) <= 1),
                       key=lambda c: (max(abs(c[0] - it[0]), abs(c[1] - it[1])), c))  # fmt: skip
        for c in near_[:per_item]:
            if c not in out:
                out.append(c)
    return out


# dungeon@9.36 (--loot-recheck; rogue-xmas02.md 4DA, after 4CZ's flag: the loot step asked the item
# model ~2-3 s after the kill, before ~43 % of the drops were drawn -- the settle study saw a fall's
# item by 2 s in 25 / 53, 3 s 30, 4 s 32, 5 s 38, 6 s 42). The loot step stays 9.33. Each kill's
# 5 x 5 cells (the loot list's cells around her at the kill, as the loot step plans them) then stay
# PENDING for RECHECK_S; while one is and she is calm, the main loop asks the same item model on a
# fresh frame at most every RECHECK_EVERY_S (never a sleep: not due -> no check). An item boxed in a
# pending kill's cells -> those cells are looted as the loot step's seen-items path does
# (items_plan's order, the hovers, its caps); that kill is then done. A fight (or a hit) during it
# yields: the kill stays pending until it expires.
LOOT_RECHECK_VERSION = "9.36"
RECHECK_S = 7.0  # a kill's cells stay pending this long after the kill (the study: 42 / 53 by 6 s)
RECHECK_EVERY_S = 1.0  # at most one item detection this often while a kill is pending
# 4DA amendment (BEFORE p94 / p95): the recheck maps items on a WIDER grid than the loot step's
# ITEM_GRID (+-4): she has often walked ~7 cells on by the time a late item shows (the builder's
# risk note), so +-8 cells (about the visible floor) keeps a pending kill's cells mappable
RECHECK_GRID: list[tuple[int, int]] = [(dx, dy) for dx in range(-8, 9) for dy in range(-8, 9)]
RECHECK_R = 2  # a kill's cells: the (2R + 1)^2 around her cell at the kill (the loot step's plan)


@dataclass(eq=False)
class PendingKill:
    """dungeon@9.36: a kill whose cells wait for a late drop -- her cell and the tick at the kill,
    and the rechecks run while it waited. eq=False: two kills in one tick stay two."""

    cell: Cell
    t: float
    checks: int = 0


def kill_cells(cell: Cell, fits: Callable[[Cell], bool] | None = None,
               r: int = RECHECK_R) -> set[Cell]:  # fmt: skip
    """PURE (dungeon@9.36): the (2r + 1)^2 cells around ``cell`` that ``fits`` (the loot step's
    filter: on the map, walkable, outside the no-enter zones); all of them without one."""
    out = {(cell[0] + dx, cell[1] + dy) for dx in range(-r, r + 1) for dy in range(-r, r + 1)}
    return out if fits is None else {c for c in out if fits(c)}


def recheck_split(pending: Sequence[PendingKill], now: float, escape_t: float,
                  max_s: float = RECHECK_S) -> tuple[list[PendingKill],
                                                     list[tuple[PendingKill, str]]]:  # fmt: skip
    """PURE (dungeon@9.36): (the kills still pending, the kills leaving unseen with why) -- "time"
    once ``max_s`` has passed since the kill; "escape" for a kill at or before ``escape_t`` (the
    last Fly Wing, walk-away or door click: she left those cells on purpose)."""
    keep: list[PendingKill] = []
    gone: list[tuple[PendingKill, str]] = []
    for k in pending:
        if k.t <= escape_t:
            gone.append((k, "escape"))
        elif now - k.t >= max_s:
            gone.append((k, "time"))
        else:
            keep.append(k)
    return keep, gone


def recheck_due(now: float, last: float, every_s: float = RECHECK_EVERY_S) -> bool:
    """PURE (dungeon@9.36): the next item detection is due ``every_s`` after the last one (the
    recheck's own, or the loot step's)."""
    return now - last >= every_s


def recheck_calm(mode: str, locked: bool, calm: bool, since_taken: float, avoiding: bool,
                 taken_s: float = FIGHT_TAKEN_S) -> bool:  # fmt: skip
    """PURE (dungeon@9.36): she may recheck now -- hunting (mode "search": where the loot step hands
    her back; never a fight, its "after", a rest), no lock held, the runner's own ``calm`` (no hit
    for CALM_S, not fighting, not sitting, no HP drop), no hit on her within ``taken_s``
    (FIGHT_TAKEN_S), and no boss-avoid window."""
    return mode == "search" and not locked and calm and since_taken > taken_s and not avoiding


def recheck_match(pending: Sequence[PendingKill], seen: Sequence[Cell],
                  fits: Callable[[Cell], bool] | None = None) -> list[PendingKill]:  # fmt: skip
    """PURE (dungeon@9.36): the pending kills (in their order) with a seen item cell (absolute)
    inside their cells (kill_cells, filtered by ``fits``)."""
    return [k for k in pending if any(c in kill_cells(k.cell, fits) for c in seen)]


def recheck_plan(pending: Sequence[PendingKill], seen: Sequence[Cell],
                 fits: Callable[[Cell], bool] | None = None,
                 ) -> tuple[list[PendingKill], list[Cell]]:  # fmt: skip
    """PURE (dungeon@9.36): (the matched kills, the cells to hover) -- the loot step's seen-items
    plan (items_plan: each seen item's cell, then its nearest plan neighbours, at most
    LOOT_ITEMS_HOVERS an item) over the union of the matched kills' cells; ([], []) for none."""
    hits = recheck_match(pending, seen, fits)
    plan: set[Cell] = set()
    for k in hits:
        plan |= kill_cells(k.cell, fits)
    return hits, items_plan(seen, plan)


def recheck_outcome(end: str, picks: int, hovers: int) -> tuple[str, bool]:
    """PURE (dungeon@9.36): (the recheck's end, its kills done?) -- a fight or a hit during it
    YIELDS (they stay pending until they expire); otherwise they are done: "looted" (a pickup),
    "empty" (hovered, no PICKUP hand read), "off" (no cell in view), "escape" (a Fly Wing)."""
    if end in ("fight", "hit"):
        return end, False
    if end == "done":
        end = "looted" if picks else "empty" if hovers else "off"
    return end, True


def loot_recheck_refused(recheck: bool, loot_items: str | None) -> str | None:
    """PURE (dungeon@9.36): why --loot-recheck cannot run (None: it can, or it is off). It re-asks
    --loot-items' model: without that model there is nothing to re-ask."""
    if recheck and not loot_items:
        return "--loot-recheck goes with --loot-items"
    return None


# dungeon@9.37 (--loot-memory; rogue-xmas02.md 4DB, after p94: 9.36's recheck ran ONCE in 71
# pending kills -- its calm rule is almost never true within 7 s of a kill on this dense map, the
# next monster is engaged at once). The item model only LOOKS (no click, no sleep): on a fresh frame
# at most every MEMORY_EVERY_S while any kill is younger than MEMORY_S, in ANY mode but sitting
# (fights included), from the main loop. Item cells inside a young kill's 5 x 5 cells (the loot
# step's plan filter) are REMEMBERED for MEMORY_KEEP_S after their last sighting. The NEXT loot
# step hovers its own seen items PLUS the remembered cells (after its own, items_plan's order, its
# caps) and clears those it visited; a step that saw nothing itself visits the remembered cells
# instead of ending "no_items". Calm (9.36's recheck_calm) with cells left -> 9.36's recheck_visit.
LOOT_MEMORY_VERSION = "9.37"
MEMORY_S = 7.0  # the item model looks while a kill is younger than this (9.36's RECHECK_S)
MEMORY_EVERY_S = 1.0  # at most one look this often
# 4DB amendment (before p96): 12 -> 30 s. Kills come ~18.5 s apart at 194 / h, so a 12-s keep
# expired cells just before the next loot step could take them.
MEMORY_KEEP_S = 30.0  # a remembered cell is kept this long after its last sighting


@dataclass(frozen=True)
class Remembered:
    """dungeon@9.37: a floor-item cell seen inside a young kill's cells -- its last sighting and
    the matched kills' cells (the plan items_plan takes its neighbours from)."""

    t: float
    plan: frozenset[Cell]


def memory_look_due(now: float, last: float, kills: Sequence[PendingKill], sitting: bool,
                    max_s: float = MEMORY_S, every_s: float = MEMORY_EVERY_S) -> bool:  # fmt: skip
    """PURE (dungeon@9.37): the next look is due -- not sitting, a kill younger than ``max_s``,
    and ``every_s`` since the last look (recheck_due's clock rule)."""
    return (not sitting and any(now - k.t < max_s for k in kills)
            and recheck_due(now, last, every_s))  # fmt: skip


def memory_remember(mem: Mapping[Cell, Remembered], seen: Sequence[Cell],
                    kills: Sequence[PendingKill], now: float,
                    fits: Callable[[Cell], bool] | None = None, max_s: float = MEMORY_S,
                    ) -> tuple[dict[Cell, Remembered], list[Cell], list[Cell]]:  # fmt: skip
    """PURE (dungeon@9.37): (the memory after a look, the cells newly remembered, the seen cells
    kept) -- a seen item cell (absolute) inside a kill's cells (kill_cells, filtered by ``fits``)
    of a kill younger than ``max_s`` is remembered at ``now``; one already remembered is re-timed
    (its last sighting) and its plan grows by the newly matched kills' cells; others: passed by."""
    young = [kill_cells(k.cell, fits) for k in kills if now - k.t < max_s]
    out = dict(mem)
    new: list[Cell] = []
    kept: list[Cell] = []
    for c in seen:
        if c in kept:
            continue
        plan = frozenset(x for cells in young if c in cells for x in cells)
        if not plan:
            continue
        kept.append(c)
        if c in out:
            out[c] = Remembered(now, out[c].plan | plan)
        else:
            out[c] = Remembered(now, plan)
            new.append(c)
    return out, new, kept


def memory_expire(mem: Mapping[Cell, Remembered], now: float, escape_t: float,
                  keep_s: float = MEMORY_KEEP_S,
                  ) -> tuple[dict[Cell, Remembered], list[Cell], list[Cell]]:  # fmt: skip
    """PURE (dungeon@9.37): (the cells still remembered, those aged out -- ``keep_s`` since their
    last sighting --, those dropped at an escape: last seen at or before ``escape_t``, a Fly Wing,
    a walk-away or a door click; she left those cells on purpose, as recheck_split)."""
    keep: dict[Cell, Remembered] = {}
    old: list[Cell] = []
    esc: list[Cell] = []
    for c, m in mem.items():
        if m.t <= escape_t:
            esc.append(c)
        elif now - m.t >= keep_s:
            old.append(c)
        else:
            keep[c] = m
    return keep, old, esc


def memory_merge(order: Sequence[Cell], mem: Mapping[Cell, Remembered],
                 here: Cell | None) -> tuple[list[Cell], list[Cell]]:  # fmt: skip
    """PURE (dungeon@9.37): (the hover order: the loot step's own ``order`` first, then each
    remembered cell's items_plan over its own kills' cells -- nearest her first --, one cell once;
    the remembered cells offered, in that order)."""
    rem = sorted(mem, key=lambda c: (cheb2(c, here), c))
    out = list(order)
    for c in rem:
        for x in items_plan([c], mem[c].plan):
            if x not in out:
                out.append(x)
    return out, rem


def memory_clear(mem: Mapping[Cell, Remembered],
                 visited: set[Cell] | Sequence[Cell]) -> dict[Cell, Remembered]:  # fmt: skip
    """PURE (dungeon@9.37): the memory after a loot (the loot step's or the calm path's): every
    remembered cell it visited (hovered, in view or not) is done."""
    done = set(visited)
    return {c: m for c, m in mem.items() if c not in done}


def loot_memory_refused(memory: bool, loot_items: str | None) -> str | None:
    """PURE (dungeon@9.37): why --loot-memory cannot run (None: it can, or it is off). It looks
    with --loot-items' model: without that model there is nothing to look with."""
    if memory and not loot_items:
        return "--loot-memory goes with --loot-items"
    return None


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
                 "potions_to": None, "wings_to": WINGS_TO, "clear_etc": True,
                 "home_key": HOME_KEY},
    "thief": {"job": "thief", "max_hp": 952, "max_sp": 112,  # its status window (thief-payon 4)
              "keys": {"potion": "F1", "fly": "F2", "steal": "F3", "sit": "Insert",
                       "stand": "Insert"},
              "autoguard": False, "potions_to": 10, "wings_to": 10,
              # Rough Oridecon 756 / Rough Elunium 757 are Etc: never dropped by the setup
              "clear_etc": False, "home_key": HOME_KEY},
    # dungeon@8 (Batt 2026-10-25, rogue-gef10.md): the SAME character (data/thief, Thief8fce) after
    # its job change; its status window 2026-10-25 19:3x: HP 2146, SP 336 (Base 62 / Rogue 50).
    # Loot is value now (his Overcharge merchant): never dropped; at 40 % the setup stops ("train
    # until the bag is full first", Batt 2026-10-25)
    # Batt 2026-10-26 ~20:5x: the Rogue levelled 62 -> 63 by hunting (max HP 2146 -> 2209); HOLD
    # it at 63 ("ค้างไว้ที่ 63"): the setup lowers a higher DB level with @baselevelup -N.
    # ➡️ Batt 2026-11-05 (xmas_dun02, docs/planning/rogue-xmas02.md): base AGI 99 + DEX 99, so Base
    # 99 (@baselevelup 36, @agi 17, @dex 59 at 15:04); its status window 15:05: HP 5070, SP 530,
    # HIT 205, FLEE 246+1, ASPD 176. The hold is 99 now (a higher level cannot exist)
    # dungeon@9.27 (Batt 2026-11-11, rogue-xmas02.md 4BX): the dagger sits on F5 (hotbar slot 4;
    # bare_steal.EQUIP_KEY): --bare-steal presses it to put the dagger back on ("equip")
    "rogue": {"job": "rogue", "data": "thief", "max_hp": 5070, "max_sp": 530,
              "keys": {"potion": "F1", "fly": "F2", "steal": "F3", "sit": "Insert",
                       "stand": "Insert", "equip": "F5"},
              "autoguard": False, "potions_to": 10, "wings_to": 10, "clear_etc": False,
              "home_key": HOME_KEY,  # dungeon@9.35b: the Butterfly Wing (--player-mode only)
              "hotbar_stock": True,  # dungeon@8.3: the stock is read from the hotbar
              "level_hold": 99,
              # Batt 2026-11-08 (p11 refused at 40.7 %): the Rogue runs on up to WEIGHT_MAX
              # (48 %) without dropping her Etc tab (it holds Batt's target items)
              "etc_hold_max": 0.48,
              # Batt 2026-11-08 ~15:4x (rogue-xmas02.md Amendment G): "potions are hardly used, 10
              # bottles are enough" -> HER potions_to (10) outranks the strategy's (P2: 30); the
              # Fly Wings still follow the strategy (P2: 20). p13's setup (16:33) still added 30.
              "potions_win": True},
}  # fmt: skip
STOCK_ITEMS = {"potion": 504, "fly": 601}  # the hotbar key -> its item (White Potion, Fly Wing)
# dungeon@9.31 (--heal-candy; Batt 2026-11-11 evening: "we need not carry White Potions: we can eat
# Candy and Candy Cane for HP instead -- it also cuts the weight, because those two do not sell to
# the NPC for as much as Piece of Cake and Well-baked Cookie"). A due potion becomes the Candy Cane
# (530, heals 105-145, weight 4) while its hotbar count is not known 0, then Candy (529, 45-65,
# weight 3), then the White Potion (504, 325-405, weight 15) as the fallback; the White Potions are
# no longer topped up (nor drunk down at the stand). Neither candy has an NPC shop: in a real game
# they come from drops (the dashboard prices them at the NPC sale they forgo); in the lab the setup
# tops them up with @item.
HEAL_CANDY_VERSION = "9.31"
HEAL_CANDY_KEYS = {"cane": "F6", "candy": "F7"}  # hotbar row 1, slots 5 and 6 (dragged once)
HEAL_CANDY_ITEMS = {"cane": 530, "candy": 529}
HEAL_CANDY_TO = {530: 20, 529: 20}  # 20 x 125 + 20 x 55 HP ~ 10 White Potions; weight 140 vs 150
HEAL_ORDER = (("cane", 530), ("candy", 529), ("potion", 504))


def heal_pick(left: Mapping[int, int | None]) -> str:
    """PURE (dungeon@9.31): the key for a due potion -- the first of HEAL_ORDER whose hotbar count
    is not known to be 0 (an unread count counts as stocked: the re-read after the press settles
    it); all known 0 -> "potion" (its own stock guard then ends the run)."""
    for what, item in HEAL_ORDER:
        if left.get(item) != 0:
            return what
    return "potion"


def heal_out(left: Mapping[int, int | None]) -> bool:
    """PURE (dungeon@9.31): under --heal-candy a heal item at 0 ends the run only when EVERY heal
    item (cane, candy, potion) reads 0; an unread count is never 0."""
    return all(left.get(item) == 0 for _, item in HEAL_ORDER)


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


# --- U0's staged setup (TRIAL ONLY: rogue-xmas02.md 4BU, U0 -- the staged unreachable attacker;
# Study S-UA: in p57 she stood on (100,207) and a Cruiser on (98,205) shot her across cliff cells
# she cannot walk). Batt OK'd a staged monster beside her, 2026-11-11.
def cell_arg(s: str) -> Cell:
    """argparse type: "X,Y" -> (X, Y), two non-negative integers."""
    xs, sep, ys = s.partition(",")
    try:
        if not sep:
            raise ValueError(s)
        x, y = int(xs.strip()), int(ys.strip())
    except ValueError:
        raise argparse.ArgumentTypeError(f"{s!r} is not a cell X,Y") from None
    if x < 0 or y < 0:
        raise argparse.ArgumentTypeError(f"{s!r}: a cell is never negative")
    return x, y


def u0_setup_refused(map_: str, start_cell: Cell | None, stage_at: Cell | None,
                     stage_mob: str | None, okr: Any,
                     check: Callable[[str, list[Cell]], str | None]) -> str | None:  # fmt: skip
    """PURE: why --start-cell / --stage-at cannot run (None: they can, or both are off).
    --stage-at moves where --stage-mob's mob spawns, so it needs --stage-mob. The start cell must
    be on the run's route grid ``okr`` AND pass the three stand-cell checks (``check`` =
    map_prep.stand_check: no warp span, no NPC touch area, the server's map cache lets her stand
    there); the stage cell is a @warp stand too, so it must pass the same three."""
    if stage_at is not None and not stage_mob:
        return "--stage-at goes with --stage-mob (it moves where the staged mob spawns)"
    h, w = np.shape(okr)[:2]
    for name, c in (("--start-cell", start_cell), ("--stage-at", stage_at)):
        if c is None:
            continue
        if not (0 <= c[0] < w and 0 <= c[1] < h):
            return f"{name} {c}: off {map_} ({w} x {h})"
        if name == "--start-cell" and not okr[c[1], c[0]]:
            return f"{name} {c}: off the route grid (a wall, a zone or a sealed-off part)"
        if (why := check(map_, [c])) is not None:
            return f"{name} {c}: {why}"
    return None


def map_setup_lines(map_: str, start: Cell, clear_map: bool, stage_mob: str | None,
                    stage_at: Cell | None = None) -> list[str]:  # fmt: skip
    """PURE: the setup's lines on the map, in order. Without --stage-at (as before): @warp to the
    start, @killmonster2 (--clear-map: dungeon@8, Amendment A4 -- the experimenter's step, never
    the bot's), @monster ID N (--stage-mob, 9.18's TRIAL only: spawned on the start cell). With
    --stage-at X,Y (U0's TRIAL only): @warp to X,Y, @killmonster2, @monster ID N (spawned at X,Y,
    not on her), then @warp to the start."""
    if stage_at is not None and not stage_mob:
        raise ValueError("--stage-at goes with --stage-mob")
    at = start if stage_at is None else stage_at
    setup = [f"@warp {map_} {at[0]} {at[1]}"]
    if clear_map:
        setup.append("@killmonster2")
    if stage_mob:
        mob_id, _, n_mob = str(stage_mob).partition(":")
        setup.append(f"@monster {int(mob_id)} {int(n_mob or 1)}")
    if stage_at is not None:
        setup.append(f"@warp {map_} {start[0]} {start[1]}")
    return setup


def potions_target(strat: Mapping[str, Any], conf: Mapping[str, Any]) -> int:
    """PURE: the run's White Potion stock: the strategy's, else the character's, else POTIONS_TO;
    a character with ``potions_win`` (the Rogue, Batt 2026-11-08) keeps her own."""
    if conf.get("potions_win") and conf.get("potions_to"):
        return int(conf["potions_to"])
    return int(strat.get("potions_to") or conf["potions_to"] or POTIONS_TO)


def hotbar_slot(key: str) -> int:
    """PURE: the 1-row hotbar slot of an F-key (F1 = slot 0)."""
    if len(key) == 2 and key[0] == "F" and key[1] in "123456789":
        return int(key[1]) - 1
    raise ValueError(f"not a row-1 hotbar key: {key!r}")


# --- dungeon@9.35 --player-mode (docs/planning/player-mode.md; Batt 2026-11-12: "do player mode
# after SQLite"). On a public rAthena that permits bots (ADR-0023's declared mode) the learner is a
# normal player, not a GM: the lab setup's GM lines would fail there or, worse, show up in public
# chat. Under the flag the run types NO line at all -- not in the setup, the loop or the end. That
# is STRUCTURAL: every line this runner types goes through typed_line, which refuses first (a Stop
# before any key), and a source scan (test_player_mode.py) fails on any other typing call in this
# file. The run reads nothing from the lab's DB; the person brings the character to the map with
# her stock, the run starts where she stands, reads the stock from the hotbar's pixels and refuses
# below these minimums.
PLAYER_MODE_VERSION = "9.35"
# Fly Wings on the hotbar at the start: POS_FLY_MAX (3) wings for an unread position, one escape,
# and PLAYER_WINGS_KEEP for the end's own escape (no @warp takes her home)
PLAYER_MIN_WINGS = 5
PLAYER_MIN_HEALS = 5  # heal items at the start: White Potions (with --heal-candy + canes + candies)
PLAYER_WINGS_KEEP = 1  # the run ENDS when the Fly Wings read this many: one stays for the end
PLAYER_POS_S = 5.0  # the start: her cell must read on the minimap readout within this long
# the flags whose whole point is a GM line or a GM's start (refused under --player-mode). The
# runner itself has no immunity flag: immunity (@monsterignore) is toggled OUTSIDE it, by
# crusader.py's gm command in the lab's chain, never by this runner
PLAYER_REFUSED: tuple[tuple[str, str, str], ...] = (
    ("clear_map", "--clear-map", "it types @killmonster2"),
    ("stage_mob", "--stage-mob", "it types @monster"),
    ("stage_at", "--stage-at", "it types @warp and @monster"),
    ("start_cell", "--start-cell", "the setup's @warp goes there; a player starts where she is"),
)
# the calls that TYPE a line (ro_agent / crusader): in this file only typed_line may make one
TYPING_CALLS = frozenset({"gm_line", "gm", "chat_line", "open_chat", "type_text", "type_secret",
                          "say", "type_line", "console_type", "console_secret"})  # fmt: skip


def line_refused(line: str, player_mode: bool) -> str | None:
    """PURE (dungeon@9.35): why ``line`` must not be typed, or None. Outside --player-mode every
    line passes (crusader.gm_line's own checks follow). Under it NOTHING is typed: a line starting
    with "@" is a GM command a normal player has not got (on a public server it fails, or shows in
    public chat), and any other line would be public chat."""
    if not player_mode:
        return None
    word = line.strip().split(" ", 1)[0]
    if word.startswith("@"):
        return f"--player-mode types no GM command: {word!r} was NOT typed"
    return "--player-mode types no chat line (it would be public chat): nothing was typed"


def typed_line(agent: Any, screen: Any, line: str, job: str, char: str, *, player_mode: bool,
               on_refuse: str = "raise") -> dict[str, Any]:  # fmt: skip
    """dungeon@9.35: THE one path by which this runner types a line (a GM command, through
    crusader.gm_line and its identity check). line_refused decides FIRST: a refusal is a Stop
    before any key is pressed, so a path that --player-mode missed stops the run instead of
    leaking a line into public chat."""
    import ro_agent as r

    why = line_refused(line, player_mode)
    if why is not None:
        raise r.Stop(f"dungeon@{PLAYER_MODE_VERSION} refused: {why}")
    import crusader as cr

    return cr.gm_line(agent, screen, line, job, char, on_refuse=on_refuse)


def player_mode_refused(a: argparse.Namespace) -> str | None:
    """PURE (dungeon@9.35): why --player-mode cannot run with the other flags given (None: it can,
    or it is off). PLAYER_REFUSED's flags exist to type GM lines or to start on a GM's warp;
    --engage melee_ring strikes every monster in reach and is the lab server's alone (its own
    refusal: MR_MAPS, no script NPC, the lab's attested rAthena)."""
    if not getattr(a, "player_mode", False):
        return None
    bad = [f"{flag} ({why})" for attr, flag, why in PLAYER_REFUSED
           if getattr(a, attr, None) not in (None, False)]  # fmt: skip
    if getattr(a, "engage", "defend_scan") == "melee_ring":
        bad.append("--engage melee_ring (the lab server only: it strikes every monster in reach)")
    if not bad:
        return None
    why = "; ".join(bad)
    return f"--player-mode types no GM command and starts where she stands; not with {why}"


def player_plan(lines: Sequence[str], player: bool) -> list[str]:
    """PURE (dungeon@9.35): the setup lines a run types -- all of them, or under --player-mode
    none. Every lab setup line is a GM command (the level hold, @heal, the @item top-ups, the
    @warp to the map, @killmonster2, @monster), and a player types no line at all."""
    return [] if player else list(lines)


def player_stock_refused(counts: Mapping[int, int | None],
                         heal_items: Sequence[int]) -> str | None:  # fmt: skip
    """PURE (dungeon@9.35): why the stock the person brought cannot start a player-mode run (None:
    it can). ``counts`` are the hotbar's drawn counts by item (None: unreadable). At least
    PLAYER_MIN_WINGS Fly Wings, and PLAYER_MIN_HEALS heal items in all (``heal_items``: the White
    Potion, with --heal-candy the Candy Cane and Candy too); an unreadable count refuses, never a
    guess (4.05 a10 hunted with no Fly Wing after a guessed stock)."""
    wings = counts.get(STOCK_ITEMS["fly"])
    if wings is None:
        return "the Fly Wings' count on the hotbar did not read: a person first"
    if wings < PLAYER_MIN_WINGS:
        return (f"{wings} Fly Wings on the hotbar: bring at least {PLAYER_MIN_WINGS} (the run's "
                f"escapes; it ends with {PLAYER_WINGS_KEEP} left for the end's own)")  # fmt: skip
    heals = [counts.get(i) for i in heal_items]
    if any(n is None for n in heals):
        read = dict(zip(heal_items, heals, strict=True))
        return f"a heal item's count on the hotbar did not read ({read})"
    n_heal = sum(int(n or 0) for n in heals)
    if n_heal < PLAYER_MIN_HEALS:
        return (f"{n_heal} heal items on the hotbar (items {list(heal_items)}): bring at least "
                f"{PLAYER_MIN_HEALS}")  # fmt: skip
    return None


def player_weight_refused(share: float | None, red: bool) -> str | None:
    """PURE (dungeon@9.35): a player's bag is never dropped (no clear stand to warp to): the run
    starts only on a READ weight under WEIGHT_MAX (natural regen stops at 50 %)."""
    if share is None or red:
        return "the weight on Basic Info did not read, or reads red (>= 50 %): a person first"
    if share >= WEIGHT_MAX:
        return f"weight {share:.2f} >= {WEIGHT_MAX}: lighten the bag first (a person)"
    return None


def player_start_refused(map_: str, here: Cell | None, okr: Any, area: Any) -> str | None:
    """PURE (dungeon@9.35): why a player-mode run cannot start from ``here``, the cell the
    minimap readout gave (None: it can). She must stand on the run's route grid (walkable, outside
    every zone, not in a sealed-off part) in a walk component that reaches the search area: the
    heading walk, the patrol (its nearest waypoint ahead) and --explore (her component's regions)
    all start from her cell."""
    if here is None:
        return (f"her cell did not read on the minimap readout within {PLAYER_POS_S} s: a "
                "person first")  # fmt: skip
    import explore_map as em_p

    g = np.asarray(okr, dtype=bool)
    h, w = g.shape[:2]
    if not (0 <= here[0] < w and 0 <= here[1] < h):
        return f"her cell {here} is off {map_} ({w} x {h}): is she on {map_}?"
    if not g[here[1], here[0]]:
        return (f"her cell {here} is off {map_}'s route grid (a wall, a zone or a sealed-off "
                f"part): walk her onto the open ground first")  # fmt: skip
    if not (em_p.component(g, here) & np.asarray(area, dtype=bool)).any():
        return f"no walk from her cell {here} reaches {map_}'s search area: walk her nearer first"
    return None


def player_wings_low(item: int, n: int | None, keep: int = PLAYER_WINGS_KEEP) -> bool:
    """PURE (dungeon@9.35): under --player-mode the run ends when the Fly Wings read ``keep`` or
    fewer (an unread count never ends it), so the end's own escape still has one: no @warp takes a
    player home."""
    return item == STOCK_ITEMS["fly"] and n is not None and n <= keep


# dungeon@9.35b (Batt 2026-11-12, rogue-xmas02.md 4DF: "player mode on public servers: a warning
# only, no refusal"): a --player-mode run on a map whose KB lists a BOSS spawn, with the boss guard
# off (no --engage-screen, whose Battle Log names guard; no --garm-fly, whose detector box guards),
# prints ONE plain WARNING line at its start and records player_boss_warning. It never refuses.
def player_boss_spawns(map_: str, kb: Path | None = None) -> tuple[str, ...] | None:
    """dungeon@9.35b: the map's boss spawns by the KB, as --boss-walk names them
    (boss_spawn_names: the spawn's name and the mob table's); None when the KB does not read."""
    kb_ = ROOT / "data" / "kb" if kb is None else kb
    try:
        spawns = json.loads((kb_ / "spawns.json").read_text())
        mobs = json.loads((kb_ / "mobs.json").read_text())
    except (OSError, ValueError):
        return None
    return boss_spawn_names(map_, spawns, mobs)


def player_boss_warning(map_: str, bosses: Sequence[str] | None, guard: bool) -> str | None:
    """PURE (dungeon@9.35b): the WARNING line of a --player-mode start (None: no warning) -- the
    map has a boss spawn in the KB (``bosses``; None: the KB did not read, so they are unknown)
    and the boss guard is off (``guard``: --engage-screen or --garm-fly). A warning only: the run
    goes on."""
    if guard or (bosses is not None and not bosses):
        return None
    off = "the boss guard is off (no --engage-screen / --garm-fly)"
    if bosses is None:
        return (f"WARNING: --player-mode on {map_}: the KB did not read, so its boss spawns are "
                f"unknown, and {off}; the run goes on")  # fmt: skip
    return (f"WARNING: --player-mode on {map_}: the KB lists a boss spawn here "
            f"({', '.join(bosses)}) and {off}: nothing guards her from it; "
            "the run goes on")  # fmt: skip


# dungeon@9.35b (Batt 2026-11-12, rogue-xmas02.md 4DF: "add a Butterfly Wing home at the end"):
# at the END of a --player-mode run, after the run's own end escape, ONE press of the Butterfly
# Wing (to her save point) when its hotbar count reads >= 1 -- a key through press(), the mux,
# never a line. Its key is the character's home_key (HOME_KEY) or --player-home-key. It is
# optional: the start checks nothing for it, and an unread / 0 count, no key, a death or a hard bar
# (an unknown state gets no key, as dungeon@8.5's end escape) mean no press, recorded.
PLAYER_HOME_VERSION = "9.35b"
PLAYER_HOME_ITEM = 602  # the Butterfly Wing (a Use item): to the save point
PLAYER_HOME_LOAD_S = 3.0  # after the press, the load screen (Basic Info unread) starts by then ...
PLAYER_HOME_WAIT_S = WARP_READY_S  # ... and Basic Info reads again (the new map drawn) by then
PLAYER_HOME_POLL_S = 0.2
PLAYER_STAND_S = 0.6  # a seated end stands first: no wing can be used sitting


def player_home_refused(a: argparse.Namespace, conf: Mapping[str, Any], keys: Mapping[str, str],
                        opener: str | None) -> str | None:  # fmt: skip
    """PURE (dungeon@9.35b): why the Butterfly Wing's key cannot be used (None: it can, or there is
    none). --player-home-key goes with --player-mode; the key (it, else the character's
    ``home_key``) is a row-1 hotbar key (F1-F9) that is no other key of the run (``keys``: the
    character's, with --heal-candy's) and not --steal-opener's ``opener``."""
    override = getattr(a, "player_home_key", None)
    if not getattr(a, "player_mode", False):
        return None if override is None else "--player-home-key goes with --player-mode"
    key = override or conf.get("home_key")
    if key is None:
        return None
    try:
        hotbar_slot(key)
    except ValueError:
        return f"the Butterfly Wing key {key!r} is not a row-1 hotbar key (F1-F9)"
    used = sorted(w for w, k in keys.items() if k == key)
    if opener == key:
        used.append("--steal-opener")
    if used:
        return f"the Butterfly Wing key {key} is already the run's ({', '.join(used)})"
    return None


def player_home_skip(reason: str, key: str | None) -> str | None:
    """PURE (dungeon@9.35b): why the end presses no Butterfly Wing before its count is read (None:
    read it). No key configured; a death (the dialog is the person's; no item works dead); a hard
    bar (an unknown UI state gets no key, as dungeon@8.5's end escape)."""
    if key is None:
        return "no Butterfly Wing key configured"
    if reason == "death":
        return "dead: the death dialog is the person's"
    if reason.startswith("hard_bar"):
        return "a hard bar: an unknown state gets no key"
    return None


def player_home_count_why(count: int | None) -> str | None:
    """PURE (dungeon@9.35b): why a read count presses no Butterfly Wing (None: press it once)."""
    if count is None:
        return "the Butterfly Wing's hotbar count did not read"
    if count < 1:
        return f"no Butterfly Wing on the hotbar (count {count})"
    return None


def player_home_end(key: str | None, reason: str, seated: bool, *,
                    read_count: Callable[[], int | None], press: Callable[[], None],
                    stand: Callable[[], None], basic_info: Callable[[], bool],
                    sleep: Callable[[float], None] = time.sleep,
                    now: Callable[[], float] = time.monotonic,
                    rec: dict[str, Any] | None = None) -> dict[str, Any]:  # fmt: skip
    """dungeon@9.35b: the end of a --player-mode run -- the Butterfly Wing home, once, and the
    record of what happened ({"pressed", "why", "key", "count", "stood", "load_s", "back_s",
    "waited_s"}; filled IN PLACE in ``rec`` when given, so a failure midway keeps what was done).
    The count is read up to STOCK_TRIES times STOCK_READ_S apart (an end Fly Wing's dark frames);
    a seated end stands first. After the press it waits for the map change as the runner sees one
    (gef10-house-rest's load gap): Basic Info (``basic_info``: the HP percent reads) gone within
    PLAYER_HOME_LOAD_S, then back, at most PLAYER_HOME_WAIT_S; it never presses again."""
    rec = {} if rec is None else rec
    rec.update(pressed=False, key=key, count=None, stood=False)
    why = player_home_skip(reason, key)
    if why is not None:
        rec["why"] = why
        return rec
    n: int | None = None
    for i in range(STOCK_TRIES):
        n = read_count()
        if n is not None:
            break
        if i + 1 < STOCK_TRIES:
            sleep(STOCK_READ_S)
    rec["count"] = n
    why = player_home_count_why(n)
    if why is not None:
        rec["why"] = why
        return rec
    if seated:
        stand()
        rec["stood"] = True
        sleep(PLAYER_STAND_S)
    press()
    rec.update(pressed=True, why=f"{n} on the hotbar")
    t0 = now()
    load_s: float | None = None
    back_s: float | None = None
    while now() - t0 < PLAYER_HOME_WAIT_S:
        sleep(PLAYER_HOME_POLL_S)
        seen, t_ = basic_info(), now() - t0
        if load_s is None and not seen:
            load_s = round(t_, 2)
        elif load_s is None and t_ > PLAYER_HOME_LOAD_S:
            break  # no load screen: the map did not change (recorded, never a second press)
        elif load_s is not None and seen:
            back_s = round(t_, 2)
            break
    rec.update(load_s=load_s, back_s=back_s, waited_s=round(now() - t0, 2))
    return rec


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
# --late-confirm (dungeon@9.21, LF-2; rogue-xmas02.md 4BI, Amendment R; Study S-LF): a light read
# that PosConfirm held back only because it came > CONFIRM_S after the read before it (the first
# read after a strike, a scan, a loot step: 317 "unconfirmed only" spans in p40-p47) is confirmed
# AT ONCE by a read of a NEWER frame -- another bus frame id, decoded after the one read, waited for
# at most LATE_CONFIRM_WAIT_S -- instead of on the next tick. The second read goes through
# PosConfirm.accept itself (the same reach rule, a base read counting as before), and the cell it
# gives passes the position-jump hard bar like any other read. No frame id (an X grab) or the same
# frame id: nothing is read and the read stays unconfirmed, as today. (9.20 is xmas02-detector.md
# O.10's --loot-sight.)
LATE_CONFIRM_VERSION = "9.21"
LATE_CONFIRM_WAIT_S = 0.25  # the RDP bus sends a frame at least every 0.1 s (its keepalive)


@dataclass(frozen=True)
class Held:
    """A light read PosConfirm held back (LF-1 logs it): its time, its cell and the seconds since
    the read before it (None: no read before it)."""

    t: float
    cell: Cell
    dt: float | None


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
        return self.check(t, rd)[0]

    def check(self, t: float, rd: Any) -> tuple[Cell | None, Held | None]:
        """accept(), and the read it HELD BACK (LF-1), if it held one back; one lock for both."""
        if rd.xy is None:
            return None, None
        p_ = (int(rd.xy[0]), int(rd.xy[1]))
        with self._lock:
            prev, self.last = self.last, (t, p_)
            if getattr(rd, "mode", "base") != "light":
                return p_, None
            dt = t - prev[0] if prev is not None else math.inf
            if (
                prev is not None
                and dt <= CONFIRM_S
                and max(abs(p_[0] - prev[1][0]), abs(p_[1] - prev[1][1]))
                <= dt / WALK_S_PER_CELL + 1
            ):
                return p_, None
            self.unconfirmed += 1
            return None, Held(t, p_, None if prev is None else dt)


def late_confirm_due(held: Held | None) -> bool:
    """PURE (--late-confirm, LF-2): a held-back read that was held only for being LATE (> CONFIRM_S
    after the read before it, or no read before it) -- not one that disagreed with a recent read."""
    return held is not None and (held.dt is None or held.dt > CONFIRM_S)


def late_confirm_refusal(first_id: int, second_id: int, source: str) -> str | None:
    """PURE (LF-2): why the second frame cannot confirm the first -- "no_bus" (an X grab carries no
    frame id: a new frame cannot be proven), "same_frame" (the stream repeated the frame: two reads
    of one picture are one read) -- else None."""
    if source != "bus" or second_id < 0 or first_id < 0:
        return "no_bus"
    if second_id == first_id:
        return "same_frame"
    return None


def newer_frame(
    screen: Any,
    region: tuple[int, int, int, int],
    after_ns: int,
    prev_id: int,
    wait_s: float = LATE_CONFIRM_WAIT_S,
) -> tuple[int, Any, int, str] | None:
    """--late-confirm (LF-2): ``region`` (screen pixels, BGR) from a bus frame decoded after
    ``after_ns`` whose frame id is not ``prev_id``, waiting at most ``wait_s`` (None: none came).
    An X grab (no frame id) returns at once: late_confirm_refusal refuses it."""
    end = time.monotonic() + wait_s
    while True:
        t, img, frame_id, source = screen.grab_meta(*region)
        if source != "bus" or (t > after_ns and frame_id != prev_id):
            return t, np.ascontiguousarray(np.asarray(img)[..., :3]), frame_id, source
        if time.monotonic() > end:
            return None
        time.sleep(0.01)


def late_confirm(
    pc: PosConfirm,
    held: Held | None,
    first: tuple[int, int],
    newer: Callable[[int, int], tuple[int, Any, int, str] | None],
    read: Callable[[Any], Any],
    clock: Callable[[], float],
) -> tuple[Cell | None, dict[str, Any] | None]:
    """--late-confirm (dungeon@9.21, LF-2): when ``held`` is due (late_confirm_due), read a NEWER
    frame -- ``newer(t_ns, frame_id)`` of the frame read (``first``) gives (t_ns, image, frame id,
    source) or None -- and pass that read to PosConfirm.accept at ``clock()``: its reach rule
    decides (a base read counts as always). Returns (the accepted cell or None, the log fields or
    None when not due). Outcomes: "ok" (the newer light read agreed), "base" (the newer read was a
    base read), "differ" (held back again), "no_read", "same_frame", "no_bus", "no_frame"."""
    if not late_confirm_due(held):
        return None, None
    got = newer(*first)
    if got is None:
        return None, {"lf2": "no_frame"}
    t2, img2, id2, src2 = got
    rec: dict[str, Any] = {"lf2_fid": [first[1], id2], "lf2_ms": round((t2 - first[0]) / 1e6)}
    why = late_confirm_refusal(first[1], id2, src2)
    if why is not None:
        return None, {**rec, "lf2": why}
    rd2 = read(img2)
    if rd2 is None or rd2.xy is None:
        return None, {**rec, "lf2": "no_read"}
    pos = pc.accept(clock(), rd2)
    kind = "differ" if pos is None else "ok" if getattr(rd2, "mode", "base") == "light" else "base"
    return pos, {**rec, "lf2": kind, "lf2_xy": [int(rd2.xy[0]), int(rd2.xy[1])]}


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


# --unread-step (dungeon@9.22, LF-4; rogue-xmas02.md 4BI, Amendment R; Study S-LF proposal 4 and
# its note 2f): the pos_unread rule (POS_FLY_S without a fresh position read -> a Fly Wing) first
#  (a) holds the wing while a walk click of OURS is younger than UNREAD_WALK_S (p39 250.96 s: the
#      wing came 0.13 s after a walk click the client sent; "sent" is what the packets showed
#      offline -- at decision time it is our click);
#  (b) then takes up to UNREAD_STEPS steps of UNREAD_STEP_CELLS cells (Chebyshev), SCREEN-RELATIVE,
#      opposite to her last own-command movement (a walk click's to - from, a far strike's walk-up):
#      each step is a walk click through click_at after a CLEAR cursor read at its point, then
#      UNREAD_READ_S for a fresh main read (the runner's own: PosConfirm, the jump bar);
#  (c) a fresh read ends the escape: no wing, the run goes on;
#  (d) still unread after the steps (or no step possible) -> the Fly Wing exactly as before.
# Around a dead cell, fresh reads came back at 2 cells 79 % of the time (S-LF, p36-p47). The step
# is relative to her sprite at the screen centre (the camera follows her), so it needs no map cell;
# the checks that need one are judged from EVERY cell she may be on (unread_candidates) with a
# margin, or skipped (the run_start record and rogue-xmas02.md say which). 9.20 is --loot-sight's,
# 9.21 --late-confirm's.
UNREAD_STEP_VERSION = "9.22"
UNREAD_WALK_S = 2.0  # (a): a walk click of ours this young holds the wing
UNREAD_STEP_CELLS = 2  # (b): each step's length (cells, Chebyshev)
UNREAD_STEPS = 2  # (d): steps before the Fly Wing
UNREAD_READ_S = 2.0  # (b): a step's wait for a fresh read: 2 cells at 150 ms, the frames' ~0.5 s
# lag behind the server, and a light read's confirmation (two reads at READ_HZ)
UNREAD_SAFE_R = 12  # no step while a no-enter / no-cross cell or a script NPC lies within this many
# cells of a cell she may be on: the steps' 4 cells, a click carried ~3 cells along a walk (frames
# lag), and the dead reckoning's own error (p47: 4 cells)
UNREAD_MAX_S = 15.0  # a backstop: the escape holds the wing at most this long after it came due
UNREAD_LAG_S = 0.5  # an own move this soon before the last fresh read may not be in that read yet
UNREAD_WALK_BY = frozenset({"walk", "boss_walk", "approach"})  # the walk clicks among OwnMove.by


@dataclass(frozen=True)
class OwnMove:
    """--unread-step (9.22): one of OUR commands that walks her -- when, the cell it aimed at
    relative to her (screen-relative: the click's own rel, whatever ``here`` said), and which
    (UNREAD_WALK_BY's walk clicks, or "strike": a strike whose target was >= 2 cells away, so the
    client walked her up to it). Loot clicks are not kept: they step her ~1 cell onto an item, not
    the way she came."""

    t: float
    rel: Cell
    by: str


def own_move_disp(m: OwnMove) -> Cell:
    """PURE (9.22): the cells ``m`` moved her by (S-LF's dead reckoning): a walk click its rel; a
    strike's walk-up its rel less one step toward her (she stops beside the target)."""
    dx, dy = m.rel
    if m.by == "strike":
        return (dx - (dx > 0) + (dx < 0), dy - (dy > 0) + (dy < 0))
    return (dx, dy)


def last_own_move(moves: Sequence[OwnMove], fly_at: float) -> OwnMove | None:
    """PURE (9.22): the newest own move after the last Fly Wing (a teleport ends the way she came)
    that aimed somewhere (rel != (0, 0)); None: no step."""
    for m in reversed(moves):
        if m.t <= fly_at:
            return None
        if m.rel != (0, 0):
            return m
    return None


def walk_click_t(moves: Sequence[OwnMove]) -> float:
    """PURE (9.22): when our newest walk click (UNREAD_WALK_BY: the search walk, the boss walk-away,
    the far approach; never LF-4's own steps) was made; -1e9: none."""
    for m in reversed(moves):
        if m.by in UNREAD_WALK_BY:
            return m.t
    return -1e9


def unread_step_rel(moved: Sequence[int], cells: int = UNREAD_STEP_CELLS) -> Cell | None:
    """PURE (9.22): the step back along the way she came -- ``cells`` (Chebyshev) opposite to
    ``moved``, each axis rounded half away from zero ((11, 0) -> (-2, 0); (5, 3) -> (-2, -1);
    (4, 3) -> (-2, -2)); None for (0, 0)."""
    dx, dy = int(moved[0]), int(moved[1])
    n = max(abs(dx), abs(dy))
    if n == 0:
        return None

    def back(d: int) -> int:
        return -int(math.copysign(math.floor(abs(cells * d / n) + 0.5), d))

    return (back(dx), back(dy))


def unread_step_cells(rel: Cell, on_self: Callable[[Cell], bool]) -> list[Cell]:
    """PURE (9.22): the step's cells to hover, in order: ``rel``; or, when its point lies on her own
    sprite (``on_self``: only (0, +2), straight north), the cells one aside, (+1, dy) then (-1, dy):
    S-R1's kind b/c clicks on her sprite walked 1-2 cells or sent nothing."""
    if not on_self(rel):
        return [rel]
    return [c for c in ((rel[0] + 1, rel[1]), (rel[0] - 1, rel[1])) if not on_self(c)]


def unread_candidates(here: Cell | None, moves: Sequence[OwnMove], last_read_t: float,
                      fly_at: float, lag_s: float = UNREAD_LAG_S) -> list[Cell]:  # fmt: skip
    """PURE (9.22): the cells she may be on, for the checks that need one: the HELD cell ``here``
    (the last fresh read) and, when own moves came after that read (less ``lag_s``: the frames lag
    the server), the held cell moved by them (own_move_disp; never a position, never ``here``:
    LF-3 is not built). [] without a held cell."""
    if here is None:
        return []
    out = [(int(here[0]), int(here[1]))]
    since = [m for m in moves if m.t > max(fly_at, last_read_t - lag_s)]
    if since:
        dx = sum(own_move_disp(m)[0] for m in since)
        dy = sum(own_move_disp(m)[1] for m in since)
        if (dx, dy) != (0, 0):
            out.append((out[0][0] + dx, out[0][1] + dy))
    return out


def unread_step_safe(cands: Sequence[Cell], step: Cell, forbid: Any,
                     npcs: Sequence[Sequence[int]], zones: Any,
                     r: int = UNREAD_SAFE_R) -> str | None:  # fmt: skip
    """PURE (9.22): why a step cannot be judged safe from the cells she may be on (``cands``), else
    None: "no_cell" (none), "off_map" (a candidate off the grid), "zone_near" (a cell of ``forbid``
    -- the no-enter and no-cross cells -- within ``r`` of a candidate), "npc_near" (a script NPC
    within ``r``), or the walk click's own segment rule from a candidate ("no_enter" /
    "no_cross", map_zones.segment_violates)."""
    import map_zones as mz

    if not cands:
        return "no_cell"
    fb = np.asarray(forbid, dtype=bool)
    h, w = fb.shape
    for c in cands:
        x, y = int(c[0]), int(c[1])
        if not (0 <= x < w and 0 <= y < h):
            return "off_map"
        if fb[max(0, y - r) : y + r + 1, max(0, x - r) : x + r + 1].any():
            return "zone_near"
        if any(max(abs(x - int(n[0])), abs(y - int(n[1]))) <= r for n in npcs):
            return "npc_near"
        why = mz.segment_violates((x, y), (x + step[0], y + step[1]), zones)
        if why is not None:
            return why
    return None


def unread_step_decide(now: float, t0: float, walk_t: float, steps: int, step_t: float,
                       move: OwnMove | None, have_here: bool) -> tuple[str, str]:  # fmt: skip
    """PURE (--unread-step, 9.22): what the pos_unread rule does on a tick it would press the Fly
    Wing, the escape having come due at ``t0``: ("wait", why) holds the wing this tick, ("step",
    "") takes the next step, ("wing", why) presses it as before. In order: the backstop
    (UNREAD_MAX_S, "max"); a walk click of ours younger than UNREAD_WALK_S ("walk_sent"); a step
    younger than UNREAD_READ_S ("step_read": its fresh read may still come); UNREAD_STEPS taken
    ("steps"); no held cell to judge a step's safety from ("no_here"); no own move since the last
    Fly Wing ("no_move": no way back is known)."""
    if now - t0 > UNREAD_MAX_S:
        return "wing", "max"
    if now - walk_t < UNREAD_WALK_S:
        return "wait", "walk_sent"
    if steps and now - step_t < UNREAD_READ_S:
        return "wait", "step_read"
    if steps >= UNREAD_STEPS:
        return "wing", "steps"
    if not have_here:
        return "wing", "no_here"
    if move is None:
        return "wing", "no_move"
    return "step", ""


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


HUD_EVERY_S = 0.5  # dungeon@9.29: at most 2 HUD messages a second
HUD_FAST_TTL_MS = 600  # dungeon@9.29b: a box lingers at most this long on the HUD


def hud_boxes(got: Sequence[Any]) -> list[Any]:
    """PURE (dungeon@9.29): the runner's boxes for the operator HUD, each labelled by its own
    species (the detector's class before the collapse), our own body left out (self_box)."""
    from types import SimpleNamespace

    out = []
    for b in got:
        if self_box((b.x0 + b.x1) / 2, (b.y0 + b.y1) / 2):
            continue
        out.append(SimpleNamespace(x0=b.x0, y0=b.y0, x1=b.x1, y1=b.y1,
                                   score=getattr(b, "score", 1.0),
                                   cls=box_species(b) or "monster"))  # fmt: skip
    return out


def hud_fresher(a: tuple[float, list[Any]], b: tuple[float, list[Any]]) -> tuple[float, list[Any]]:
    """PURE (dungeon@9.29b): the fresher of two (grab time, boxes) sets."""
    return b if b[0] > a[0] else a


def hud_send(tx: Any, boxes: Any, mode: str, locked: bool) -> bool:
    """dungeon@9.29 (--hud): the boxes the runner holds now, to the console HUD (its own rate
    limit; operator_hud never raises). DISPLAY ONLY: no input, no decision reads it."""
    with boxes.lock:
        _t, got = hud_fresher(boxes.last, getattr(boxes, "hud_last", (0.0, [])))
    line = f"{mode}{' (locked)' if locked else ''}"
    if not tx.log or tx.log[-1] != line:  # a line on each change of mode, not each tick
        tx.note(line)
    return bool(tx.send(boxes=hud_boxes(got)))


def box_species(b: Any) -> str | None:
    """PURE (dungeon@9.28): a box's own species (the detector's class before the collapse to
    "monster"), else its class."""
    sp = getattr(b, "species", None)
    return str(sp) if sp else (str(getattr(b, "cls", "")) or None)


def value_pick(cands: Sequence[tuple[float, Any]],
               values: Mapping[str, float]) -> tuple[float, Any]:  # fmt: skip
    """PURE (dungeon@9.28, rogue-xmas02.md 4CB): the (distance, box) worth the most a kill,
    discounted by distance (value_target.pick); ``cands`` is never empty here."""
    import value_target as vt

    got = vt.pick(cands, values, box_species)
    assert got is not None
    return got


def self_box(cx: float, cy: float) -> bool:
    """PURE: a box centred on OUR drawn Crusader (the camera centres it: foot (641, 362), head ~280)
    -- v1 never saw a Crusader in training and boxes it as a monster (3.98 run 1, 12:11)."""
    x0, y0, x1, y1 = SELF_BOX
    return x0 <= cx <= x1 and y0 <= cy <= y1


# --queue (dungeon@9.30, rogue-xmas02.md 4CC; Batt 2026-11-11 ~19:3x: "when there are many
# monsters, while we hit the current one we can build a QUEUE: the one near and attacking us
# first, then on down the queue until they are all gone, so play is more continuous"). p61-p64
# (264 kills): after a kill the next strike came 7.8-8.2 s later (median) when a box was already
# in view, 15.2 s when none was; from the loot step's end to that strike 2.9 s (median), nearly
# all of it the search walk's click on the loot tick and box_target's settle + still wait after
# it. With the flag, while a fight runs the OTHER monster boxes in view (not the target, not our
# own body) are kept as a queue; once the fight AND its loot step have ended the next target is
# taken from it at once (attacking first, then the nearest), re-found on the next fresh detection
# near its last foot and struck through strike(); an empty queue or a failed re-find -> today's
# search path. QUEUE_STALE_S is detection time: the stale rule runs on the detections the fight's
# bookkeeping takes; the loot step takes none, so the queue it hands to the pick is the fight's
# last, and the re-find on a fresh detection is the pick's freshness check.
QUEUE_VERSION = "9.30"
QUEUE_MAX = 6  # entries kept (the order below decides which)
QUEUE_STALE_S = 2.0  # an entry not seen in the fight's detections for this long drops
QUEUE_MATCH_PX = 60.0  # one sprite across detections / the re-find: its foot within this
QUEUE_ATTACK_CELLS = 2  # an attacked sign marks the nearest entry within this many cells of her


@dataclass
class QEntry:
    """dungeon@9.30 (--queue): one queued monster box -- its foot pixel (the box's bottom centre,
    as BoxWatch.near measures), the detector's own species, the grab times it was first and last
    seen at, its cell relative to her at that detection (None: no position), and whether an
    attacked sign was put on it (bq_mark)."""

    foot: tuple[float, float]
    species: str | None
    t: float
    t0: float
    rel: Cell | None = None
    attacking: bool = False
    seen: int = 1


def bq_foot(b: Any) -> tuple[float, float]:
    """PURE: a box's foot pixel (its bottom centre)."""
    return ((float(b.x0) + float(b.x1)) / 2, float(b.y1))


def bq_d(foot: Sequence[float], px: Sequence[float] = FOOT_PX) -> float:
    """PURE: a foot's distance (px) to our own cell's point (BoxWatch.near's distance)."""
    return math.hypot(foot[0] - px[0], foot[1] - px[1])


def bq_order(queue: Sequence[QEntry], values: Mapping[str, float] | None = None
             ) -> list[QEntry]:  # fmt: skip
    """PURE: the pick order -- the entries marked attacking first (nearest first), then the rest
    nearest first; with ``values`` (--value-target) the rest by value_target.score (ties: the
    nearer), the attacking ones still first."""
    import value_target as vt

    att = sorted((e for e in queue if e.attacking), key=lambda e: bq_d(e.foot))
    rest = [e for e in queue if not e.attacking]
    if values:
        rest.sort(key=lambda e: (-vt.score(vt.value_of(e.species, values), bq_d(e.foot)),
                                 bq_d(e.foot)))  # fmt: skip
    else:
        rest.sort(key=lambda e: bq_d(e.foot))
    return att + rest


def bq_refresh(
    queue: Sequence[QEntry],
    boxes: Sequence[Any],
    t: float,
    *,
    target_px: Sequence[float] | None = None,
    rel_of: Callable[[tuple[float, float]], Cell | None] | None = None,
    keep: Callable[[tuple[float, float]], bool] | None = None,
    values: Mapping[str, float] | None = None,
    match_px: float = QUEUE_MATCH_PX,
    stale_s: float = QUEUE_STALE_S,
    cap: int = QUEUE_MAX,
) -> list[QEntry]:
    """PURE (dungeon@9.30): the queue after one detection (``boxes``, grabbed at ``t``). Our own
    sprite's boxes (self_box) and boxes ``keep`` refuses (not in view) are left out, and so is
    the CURRENT TARGET: the box whose foot is nearest ``target_px`` (the lock's cell projected),
    within ``match_px``. Each entry takes the nearest remaining box within ``match_px`` of its
    foot (pairs by distance, one box per entry): its foot, species, time and cell refreshed;
    every unmatched box is a new entry. Entries last seen more than ``stale_s`` before ``t``
    drop; the first ``cap`` by bq_order stay. A new list (the old one is not changed)."""
    cands: list[tuple[tuple[float, float], Any]] = []
    for b in boxes:
        if self_box((float(b.x0) + float(b.x1)) / 2, (float(b.y0) + float(b.y1)) / 2):
            continue
        f = bq_foot(b)
        if keep is not None and not keep(f):
            continue
        cands.append((f, b))
    if target_px is not None and cands:
        k_t = min(range(len(cands)), key=lambda k: bq_d(cands[k][0], target_px))
        if bq_d(cands[k_t][0], target_px) <= match_px:
            del cands[k_t]
    out = [replace(e) for e in queue]
    pairs = sorted((bq_d(e.foot, f), i, k) for i, e in enumerate(out)
                   for k, (f, _b) in enumerate(cands) if bq_d(e.foot, f) <= match_px)  # fmt: skip
    used_e: set[int] = set()
    used_b: set[int] = set()
    for _d, i, k in pairs:
        if i in used_e or k in used_b:
            continue
        used_e.add(i)
        used_b.add(k)
        f, b = cands[k]
        out[i] = replace(out[i], foot=f, species=box_species(b), t=t,
                         rel=rel_of(f) if rel_of is not None else None,
                         seen=out[i].seen + 1)  # fmt: skip
    for k, (f, b) in enumerate(cands):
        if k not in used_b:
            out.append(QEntry(foot=f, species=box_species(b), t=t, t0=t,
                              rel=rel_of(f) if rel_of is not None else None))  # fmt: skip
    return bq_order([e for e in out if t - e.t <= stale_s], values)[:cap]


def bq_mark(queue: Sequence[QEntry], cells: int = QUEUE_ATTACK_CELLS
            ) -> tuple[list[QEntry], QEntry | None, bool]:  # fmt: skip
    """PURE (dungeon@9.30): an attacked sign was read (a hit line on us, a Miss at us, an HP
    drop): the NEAREST entry within ``cells`` of her (Chebyshev, by its cell at its last
    detection; ties by pixel distance) is marked attacking -- the simple, honest attribution:
    the sign's source is plausibly the nearest monster beside her that is not the target. An
    entry with no cell (no position) is never marked. (the new queue, the marked entry or None,
    True when it was not marked before)."""
    near = [(max(abs(e.rel[0]), abs(e.rel[1])), bq_d(e.foot), i) for i, e in enumerate(queue)
            if e.rel is not None and max(abs(e.rel[0]), abs(e.rel[1])) <= cells]  # fmt: skip
    out = [replace(e) for e in queue]
    if not near:
        return out, None, False
    i = min(near)[2]
    new = not out[i].attacking
    out[i] = replace(out[i], attacking=True)
    return out, out[i], new


def bq_refind(entry: QEntry, boxes: Sequence[Any], match_px: float = QUEUE_MATCH_PX
              ) -> tuple[float, Any] | None:  # fmt: skip
    """PURE: (the distance it moved, the box) -- the box of a fresh detection whose foot is
    nearest the entry's last foot, within ``match_px``, our own sprite's boxes left out; None:
    gone."""
    best: tuple[float, Any] | None = None
    for b in boxes:
        if self_box((float(b.x0) + float(b.x1)) / 2, (float(b.y0) + float(b.y1)) / 2):
            continue
        d = bq_d(bq_foot(b), entry.foot)
        if d <= match_px and (best is None or d < best[0]):
            best = (d, b)
    return best


def bq_pick(order: Sequence[QEntry], boxes: Sequence[Any],
            accept: Callable[[tuple[float, float]], str | None],
            match_px: float = QUEUE_MATCH_PX,
            ) -> tuple[tuple[int, QEntry, Any, float] | None, list[str]]:  # fmt: skip
    """PURE: down the queue in ``order``, the first entry re-found in ``boxes`` (bq_refind) whose
    box ``accept`` passes (None; else its reason: the box path's skips). ((rank, entry, box, px
    moved) or None, the reason for each entry passed over: "gone" or accept's)."""
    why: list[str] = []
    for rank, e in enumerate(order):
        got = bq_refind(e, boxes, match_px)
        if got is None:
            why.append("gone")
            continue
        refused = accept(bq_foot(got[1]))
        if refused is not None:
            why.append(refused)
            continue
        return (rank, e, got[1], got[0]), why
    return None, why


def bq_due_state(mode: str, locked: bool, sitting: bool, flown: bool, boss_avoid: bool,
                 unread: bool, here_known: bool, swap: bool, ready_hold: bool) -> str:  # fmt: skip
    """PURE (dungeon@9.30): whether the pick due after a fight's loot step runs on this tick:
    "go"; "hold" (a bare-steal swap is running or its read-back pending, or --bare-ready's idle
    unequip is due and waiting for its settle: the pick waits for it, never strikes across it);
    "skip:<why>" (the pick is off, today's path follows): not searching (a rest, a fight), a
    lock, sitting, a Fly Wing since the fight's end, the boss guard's avoid window (a walk-away,
    --garm-fly), an --unread-step escape, no position."""
    for bad, why in ((mode != "search", "mode"), (locked, "lock"), (sitting, "sitting"),
                     (flown, "fly"), (boss_avoid, "boss"), (unread, "unread"),
                     (not here_known, "no_position")):  # fmt: skip
        if bad:
            return f"skip:{why}"
    if swap or ready_hold:
        return "hold"
    return "go"


def bq_next(
    queue: Sequence[QEntry],
    values: Mapping[str, float] | None,
    detect: Callable[[], Sequence[Any] | None],
    accept: Callable[[tuple[float, float]], str | None],
    aim: Callable[[Any], tuple[tuple[float, float] | None, list[str]]],
    match_px: float = QUEUE_MATCH_PX,
) -> dict[str, Any]:
    """PURE decision of the pick (dungeon@9.30), its I/O injected: ``detect`` = the next fresh
    detection's boxes (None: none came), ``accept`` = the box path's skips on a foot, ``aim`` =
    the box's hover points hovered for a SWORD ((the point, the verdicts); the point None: no
    SWORD). "empty" (no queue: nothing detected, nothing hovered); "refind_fail" (no detection,
    no entry re-found / passing the skips, or no SWORD: ``why``); "pick" (``point``: strike
    there). ``entry`` is the picked entry, else the head of the order."""
    if not queue:
        return {"what": "empty", "n": 0, "entry": None, "why": []}
    order = bq_order(queue, values)
    rec: dict[str, Any] = {"n": len(order), "entry": order[0], "why": []}
    got = detect()
    if got is None:
        return {**rec, "what": "refind_fail", "why": ["no_detection"]}
    pk, why = bq_pick(order, got, accept, match_px)
    if pk is None:
        return {**rec, "what": "refind_fail", "why": why}
    rank, e, b, moved = pk
    point, verdicts = aim(b)
    rec.update(entry=e, box=b, rank=rank, moved_px=moved, verdicts=verdicts, why=why)
    if point is None:
        return {**rec, "what": "refind_fail", "why": [*why, "verdict"]}
    return {**rec, "what": "pick", "point": point}


def queue_refused(queue: bool, box_strike: bool, boxes: bool, melee_ring: bool) -> str | None:
    """PURE: why --queue cannot run (None: it can, or it is off). It strikes through the box
    path's hover and strike (--box-strike) on the box watcher's detections; melee_ring has no
    box watcher (its own SWORD-cell queue)."""
    if not queue:
        return None
    if melee_ring:
        return "--queue is not for --engage melee_ring (it has its own SWORD-cell queue)"
    if not boxes:
        return "--queue needs the box watcher (--boxes)"
    if not box_strike:
        return "--queue goes with --box-strike (its pick is the box path's hover and strike)"
    return None


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


def etc_hold_refused(share: float | None, red: bool, conf: Mapping[str, Any]) -> str | None:
    """PURE (dungeon@6; Batt 2026-11-08): why a character that never drops its Etc tab must not
    start, or None. Its own ``etc_hold_max`` (the Rogue: 0.48) replaces CLEAR_AT; an unread
    weight or the red (>= 50 %) line always refuses."""
    limit = float(conf.get("etc_hold_max", CLEAR_AT))
    if share is None or red:
        return "unread or red (>= 50 %)"
    return f"at or over {limit}" if share >= limit else None


def still_now(shifts: Sequence[tuple[float, float]], px: float = STILL_PX,
              n: int = STILL_N) -> bool:  # fmt: skip
    """PURE (--still-strike): the last ``n`` frame-to-frame scene shifts are all < ``px``."""
    return len(shifts) >= n and all(math.hypot(dx, dy) < px for dx, dy in shifts[-n:])


def box_centre(b: Sequence[float]) -> tuple[float, float]:
    """PURE: a box's (x0, y0, x1, y1) centre."""
    return ((float(b[0]) + float(b[2])) / 2, (float(b[1]) + float(b[3])) / 2)


def same_box(b1: Sequence[float], later: Sequence[Sequence[float]],
             match_px: float = LEAD_MATCH_PX) -> tuple[float, ...] | None:  # fmt: skip
    """PURE (--lead-strike): the box of ``later`` whose centre is nearest to ``b1``'s, within
    ``match_px`` (the same sprite one detection later), or None."""
    c1 = box_centre(b1)
    best: tuple[float, tuple[float, ...]] | None = None
    for b in later:
        c = box_centre(b)
        d = math.hypot(c[0] - c1[0], c[1] - c1[1])
        if d <= match_px and (best is None or d < best[0]):
            best = (d, tuple(float(x) for x in b[:4]))
    return None if best is None else best[1]


def lead_point(b1: Sequence[float], t1: float, b2: Sequence[float], t2: float,
               lead_t: float = LEAD_T_S, min_px_s: float = LEAD_MIN_PX_S,
               max_px: float = LEAD_MAX_PX) -> dict[str, Any]:  # fmt: skip
    """PURE (--lead-strike): the sprite's velocity between two grabs (px / s) and the hover point:
    ``b2``'s centre, moved by velocity x ``lead_t`` (at most ``max_px``) when the speed is at least
    ``min_px_s``, else ``b2``'s centre itself ({"point", "v", "speed", "lead", "walking"})."""
    c1, c2 = box_centre(b1), box_centre(b2)
    dt = t2 - t1
    v = ((c2[0] - c1[0]) / dt, (c2[1] - c1[1]) / dt) if dt > 0 else (0.0, 0.0)
    speed = math.hypot(*v)
    lead = (0.0, 0.0)
    if speed >= min_px_s:
        lx, ly = v[0] * lead_t, v[1] * lead_t
        n = math.hypot(lx, ly)
        k = max_px / n if n > max_px else 1.0
        lead = (lx * k, ly * k)
    return {"point": (c2[0] + lead[0], c2[1] + lead[1]), "v": v, "speed": speed, "lead": lead,
            "walking": speed >= min_px_s}  # fmt: skip


# --still-target (dungeon@9.23, LS-2; rogue-xmas02.md Study S-LS, "Which first: LS-2" and "LS-2's
# runner change"): 152 of p40-p49's 589 targeted box strikes were LATE (the target moved >= 1 cell
# between the picture and the client's resolve, ~0.88 s), 105 of them failed (a walk or nothing:
# 117 s lost a run), and 117 of the 152 were already WALKING in the picture. So at the box
# target's SWORD, on a still scene with a fresh first detection D1, the runner takes ONE more
# detection D2 and matches the same sprite (same_box). Its foot moved < WALKER_PX: the strike is
# today's. Else the strike waits (hold_still): a detection every HOLD_GAP_S, matched to the last
# box, guard_tick() on each poll, until HOLD_STILL_N foot shifts in a row are < WALKER_PX
# ("still"), at most HOLD_MAX_S ("timeout"), or the sprite is not matched ("lost"). Still: its new
# box's first hover point is hovered and struck only on a SWORD read there. Anything else: no
# strike (box_target returns None, as on no SWORD). A D2 that cannot judge (no detection, no
# match) strikes as today. No new input path: every click is click_at's and SWORD-verified.
# S-LS: the walkers walk a median ~1.0 s more, then STAND 3.3-4.8 s (rAthena's random walk).
STILL_TARGET_VERSION = "9.23"
WALKER_PX = 10.0  # S-LS's walker flag: the foot moved this far between two settled detections
HOLD_GAP_S = 0.25  # a held target's detections: one every this long
HOLD_MAX_S = 2.5  # a hold's backstop (the rest of a walk after the picture: p90 2.56 s)
HOLD_STILL_N = 2  # "still": this many foot shifts in a row under WALKER_PX


def foot_shift(b1: Sequence[float], b2: Sequence[float]) -> float:
    """PURE (--still-target, 9.23): how far (px) a box's FOOT -- its bottom edge's centre, as
    box_target's ``foot`` -- moved from ``b1`` to ``b2``."""
    f1 = ((float(b1[0]) + float(b1[2])) / 2, float(b1[3]))
    f2 = ((float(b2[0]) + float(b2[2])) / 2, float(b2[3]))
    return math.hypot(f2[0] - f1[0], f2[1] - f1[1])


def press_decide(
    b1: Sequence[float], later: Sequence[Sequence[float]], px: float = WALKER_PX
) -> tuple[str, tuple[float, ...] | None, float | None]:
    """PURE (--still-target, 9.23): D2's verdict on the SWORD-read box ``b1`` from the boxes of the
    detection after it (``later``): ("no_match", None, None) when same_box finds none (D2 cannot
    judge: the strike is today's); ("strike", b2, moved) when its foot moved < ``px``; else
    ("hold", b2, moved)."""
    b2 = same_box(b1, later)
    if b2 is None:
        return "no_match", None, None
    moved = foot_shift(b1, b2)
    return ("strike" if moved < px else "hold"), b2, moved


def nearest_centre_px(b1: Sequence[float], later: Sequence[Sequence[float]]) -> float | None:
    """PURE (--still-target, 9.23; logging only): the distance (px, 0.1) from ``b1``'s centre to
    the nearest box centre of ``later`` -- why same_box matched none (a sprite that went beyond
    its match radius, or none detected near) -- None when ``later`` holds no box."""
    c1 = box_centre(b1)
    ds = [math.hypot(box_centre(b)[0] - c1[0], box_centre(b)[1] - c1[1]) for b in later]
    return round(min(ds), 1) if ds else None


def hold_end(shifts: Sequence[float], elapsed_s: float, matched: bool, px: float = WALKER_PX,
             n: int = HOLD_STILL_N, max_s: float = HOLD_MAX_S) -> str | None:  # fmt: skip
    """PURE (--still-target, 9.23): how a hold ends after a poll, in order: "lost" (the poll's
    detection held no box matching the last one), "still" (the last ``n`` foot shifts, one per
    matched detection, all < ``px``), "timeout" (``elapsed_s`` since the hold began >= ``max_s``);
    None: poll again."""
    if not matched:
        return "lost"
    if len(shifts) >= n and all(s < px for s in shifts[-n:]):
        return "still"
    if elapsed_s >= max_s:
        return "timeout"
    return None


def hold_track(
    b: Sequence[float],
    t_b: float,
    detect: Callable[[float], tuple[float, Sequence[Sequence[float]]] | None],
    guard: Callable[[], bool],
    clock: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
    gap_s: float = HOLD_GAP_S,
    max_s: float = HOLD_MAX_S,
    wait_s: float = BOX_TARGET_WAIT_S,
) -> dict[str, Any]:
    """--still-target (dungeon@9.23, LS-2): the hold's polls on the moved sprite ``b`` (grabbed at
    ``t_b``). Each poll: ``guard()`` first (the runner's guard_tick: True once we flew away ->
    "escaped"), then ``gap_s`` after the last matched grab ``detect(timeout)`` -- a fresh
    detection's (grab time, boxes), or None when none came within ``timeout`` (the hold's time
    left, >= 0.1 s, <= ``wait_s``) -- matched to the last box by same_box; hold_end decides after
    each poll. Returns {"end", "box" (the last matched box), "t" (its grab), "shifts" (each poll's
    foot shift; None: no detection came), "polls", "hold_s", "lost_px" (nearest_centre_px of the
    poll that matched nothing, else None)}."""
    t_h = clock()
    last, last_t = tuple(float(x) for x in b[:4]), t_b
    shifts: list[float] = []
    log: list[float | None] = []
    polls = 0
    lost_px: float | None = None
    end: str | None = None
    while end is None:
        if guard():
            end = "escaped"
            break
        sleep(max(0.0, gap_s - (clock() - last_t)))
        left = max_s - (clock() - t_h)
        polls += 1
        got = detect(max(0.1, min(wait_s, left)))
        matched = True
        if got is None:
            log.append(None)
        else:
            t_k, boxes_k = got
            b_k = same_box(last, boxes_k)
            if b_k is None:
                matched = False
                lost_px = nearest_centre_px(last, boxes_k)
            else:
                shifts.append(foot_shift(last, b_k))
                log.append(round(shifts[-1], 1))
                last, last_t = b_k, t_k
        end = hold_end(shifts, clock() - t_h, matched, max_s=max_s)
    return {"end": end, "box": last, "t": last_t, "shifts": log, "polls": polls,
            "hold_s": clock() - t_h, "lost_px": lost_px}  # fmt: skip


def still_target_refused(box_strike: bool, box_now: bool, still_strike: bool,
                         lead_strike: bool) -> str | None:  # fmt: skip
    """PURE (--still-target, 9.23): why the flag cannot work as built (the run would silently be
    the base): it checks the box target's SWORD (--box-strike) against its own fresh detection
    (--box-now) on a still scene (--still-strike); a led point (--lead-strike, dropped after p14)
    would replace the box it compares. None: it can run."""
    if not (box_strike and box_now):
        return "--still-target needs --box-strike --box-now"
    if not still_strike:
        return "--still-target needs --still-strike"
    if lead_strike:
        return "--still-target does not go with --lead-strike"
    return None


# --lead-press (dungeon@9.24, LS-1; rogue-xmas02.md Study S-LS, LS-1 and 4BP: Batt 2026-11-11, "try
# it: with the GPU now, the aim should be faster"), ON TOP OF --still-target (LS-2): when
# press_check's D2 says hold AND the sprite's foot moved >= LEAD_PX since D1, the strike does not
# wait. It clicks where the sprite will be when the client resolves the click: D2's first hover
# point + the foot's velocity between the two grabs x the picture's age at the resolve
# (LEAD_AGE_S, S-LS's ~0.57 s: the stream lag 0.16 + pre_click 0.06 + the client 0.35, as
# sim3.py modelled it; the time already spent since D2's grab is added). The lead is at most ONE
# CELL, Chebyshev on the map grid as S-LS's simulation capped it, measured by the camera's own
# per-cell screen vectors at D2's foot (~34 px across, ~24 px up / down: a flat 32-px cap would
# lead ~1.35 cells up / down and ~0.8 diagonally); LEAD_CAP_PX only when those vectors are unusable.
# The led point must pass box_target's selection gates (LS-2's re-hover's) and stay in view, off
# our own sprite, else LS-2's hold. Shifts in [WALKER_PX, LEAD_PX) hold as LS-2 does; a D2 that
# cannot judge strikes as today. The led point is NOT SWORD-read (the sprite is not there yet):
# LS-1's known risk, recorded in every lead record. It revisits --lead-strike (9.5, dropped after
# p14), which led from the CPU detector's older frames; LS-1 leads from a D2 ~21 ms old. No new
# input path: the click is click_at's, as every strike.
LEAD_PRESS_VERSION = "9.24"
LEAD_PX = 15.0  # S-LS's LS-1 threshold: the foot moved this far between D1 and D2
LEAD_AGE_S = 0.57  # D2's picture -> the client's resolve, beyond the time already spent (S-LS)
LEAD_CAP_CELLS = 1.0  # the lead at most this many cells (Chebyshev; the per-cell screen vectors)
LEAD_CAP_PX = 32.0  # ... or this many px when the per-cell vectors are unusable


def cell_steps(
    camera: Any, foot: Sequence[float], grid: Sequence[Cell] = BOX_GRID
) -> tuple[tuple[float, float], tuple[float, float]]:
    """PURE (--lead-press, 9.24): the screen vectors (px) of one cell step along x and along y at
    the ``grid`` cell (relative to us) whose flat projection by ``camera`` (the runner's: it
    follows us, our cell at FOOT_PX) is nearest ``foot`` -- on flat ground: an altitude moves a
    cell's point, not the size of one step (lead_cap's cell)."""
    g = np.asarray(grid, dtype=float)
    c_ = nearest_rel(camera.project(g, np.zeros(len(g))), grid, foot)
    pts = np.asarray([c_, (c_[0] + 1, c_[1]), (c_[0], c_[1] + 1)], dtype=float)
    uv = np.asarray(camera.project(pts, np.zeros(3)), dtype=float)
    return ((float(uv[1][0] - uv[0][0]), float(uv[1][1] - uv[0][1])),
            (float(uv[2][0] - uv[0][0]), float(uv[2][1] - uv[0][1])))  # fmt: skip


def lead_cap(
    lead: Sequence[float],
    cell_x: Sequence[float] | None = None,
    cell_y: Sequence[float] | None = None,
    cap_cells: float = LEAD_CAP_CELLS,
    cap_px: float = LEAD_CAP_PX,
) -> tuple[tuple[float, float], bool, str]:
    """PURE (--lead-press, 9.24): the screen ``lead`` (px) shortened to at most ``cap_cells``
    cells, Chebyshev, on the map grid whose one-cell steps along x / y are the screen vectors
    ``cell_x`` / ``cell_y`` at the sprite (its direction kept); a lead within it is kept as is.
    Without usable vectors (None, a zero one, or < ~6 degrees apart) at most ``cap_px`` px,
    Euclidean. Returns (the lead, whether it was shortened, the rule used: "cell" / "px")."""
    lx, ly = float(lead[0]), float(lead[1])
    if cell_x is not None and cell_y is not None:
        ax, ay, bx, by = float(cell_x[0]), float(cell_x[1]), float(cell_y[0]), float(cell_y[1])
        det, norms = ax * by - bx * ay, math.hypot(ax, ay) * math.hypot(bx, by)
        if norms > 0 and abs(det) >= 0.1 * norms:
            m = max(abs(lx * by - bx * ly), abs(ax * ly - lx * ay)) / abs(det)  # in cells
            if m <= cap_cells:
                return (lx, ly), False, "cell"
            return (lx * cap_cells / m, ly * cap_cells / m), True, "cell"
    n = math.hypot(lx, ly)
    if n <= cap_px:
        return (lx, ly), False, "px"
    return (lx * cap_px / n, ly * cap_px / n), True, "px"


def press_lead(
    b1: Sequence[float],
    t1: float,
    b2: Sequence[float],
    t2: float,
    t_now: float,
    cell_x: Sequence[float] | None = None,
    cell_y: Sequence[float] | None = None,
    walker_px: float = WALKER_PX,
    lead_px: float = LEAD_PX,
    age_s: float = LEAD_AGE_S,
) -> dict[str, Any]:
    """PURE (--lead-press, 9.24, LS-1): D2's verdict by the foot shift from D1's box ``b1``
    (grabbed at ``t1``) to D2's ``b2`` (``t2``): < ``walker_px`` -> "strike" (today's); <
    ``lead_px`` -> "hold" (LS-2's); else "lead": the foot's velocity v = (foot2 - foot1) / (t2 -
    t1) px / s, the age = ``age_s`` + the time already spent since D2's grab (``t_now`` - ``t2``),
    the lead = v x age shortened by lead_cap (``cell_x`` / ``cell_y``), the led click = D2's first
    hover point + the lead, and the led foot (its cell) = D2's foot + the lead. Grabs not in order
    give no velocity: "hold" (``why`` "dt"). Returns {"decision", "moved", and for "lead": "v",
    "age_s", "raw" (the lead before the cap), "lead", "capped", "cap", "point", "foot"}."""
    moved = foot_shift(b1, b2)
    if moved < walker_px:
        return {"decision": "strike", "moved": moved}
    if moved < lead_px:
        return {"decision": "hold", "moved": moved}
    dt = t2 - t1
    if dt <= 0:
        return {"decision": "hold", "moved": moved, "why": "dt"}
    f1 = ((float(b1[0]) + float(b1[2])) / 2, float(b1[3]))
    f2 = ((float(b2[0]) + float(b2[2])) / 2, float(b2[3]))
    v = ((f2[0] - f1[0]) / dt, (f2[1] - f1[1]) / dt)
    age = age_s + max(0.0, t_now - t2)
    raw = (v[0] * age, v[1] * age)
    lead, capped, rule = lead_cap(raw, cell_x, cell_y)
    hx, hy = box_hover_points(b2)[0]
    return {"decision": "lead", "moved": moved, "v": v, "age_s": age, "raw": raw, "lead": lead,
            "capped": capped, "cap": rule, "point": (hx + lead[0], hy + lead[1]),
            "foot": (f2[0] + lead[0], f2[1] + lead[1])}  # fmt: skip


def lead_press_refused(still_target: bool, lead_strike: bool) -> str | None:
    """PURE (--lead-press, 9.24): why the flag cannot work as built (the run would silently be
    LS-2 alone, or the base): it leads from --still-target's press check, and --lead-strike
    (dropped after p14) would replace the boxes it compares. None: it can run."""
    if not still_target:
        return "--lead-press needs --still-target"
    if lead_strike:
        return "--lead-press does not go with --lead-strike"
    return None


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


def level_lines(level_db: int | None, hold: int | None) -> list[str]:
    """PURE (Batt 2026-10-26 ~20:5x, hold the Rogue at Base 63): the setup line that brings a DB
    base level above ``hold`` back down (@baselevelup -N: it takes back that level's status points
    and zeroes the EXP, pinned atcommand.cpp); never raises a level. An unknown level (None:
    --player-mode reads no DB, dungeon@9.35) holds nothing."""
    if hold is None or level_db is None or level_db <= hold:
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
    if getattr(a, "still_strike", False):  # dungeon@9.4 (rogue-xmas02.md 4S)
        out["still_strike"] = [STILL_PX, STILL_N, STILL_MAX_S]
    if getattr(a, "lead_strike", False):  # dungeon@9.5 (rogue-xmas02.md 4V)
        out["lead_strike"] = [LEAD_GAP_S, LEAD_MATCH_PX, LEAD_MIN_PX_S, LEAD_T_S, LEAD_MAX_PX]
    if getattr(a, "quick_drop", False):  # dungeon@9.6 (rogue-xmas02.md 4W)
        out["quick_drop"] = [QUICK_ARROW_S, QUICK_HIT_S, QUICK_RETRY]
    if getattr(a, "quick_drop_scaled", False):  # dungeon@9.38 (rogue-xmas02.md 4DG)
        out["quick_drop_scaled"] = [QUICK_PER_CELL, QUICK_HIT_MAX_S, QUICK_SCALED_VERSION]
    if getattr(a, "engage_screen", False):  # dungeon@9.7 (rogue-xmas02.md 4X)
        out["engage_screen"] = [BOX_SCREEN_PX]
    if getattr(a, "far_single", False):  # dungeon@9.8 (rogue-xmas02.md 4Z)
        out["far_single"] = [FAR_CELLS, FAR_BASE_S, FAR_PER_CELL_S, FAR_MAX_S]
    if getattr(a, "near_single", False):  # dungeon@9.25 (S-LF5 R2)
        out["near_single"] = [NEAR_SINGLE_CELLS, NEAR_SINGLE_VERSION]
    if getattr(a, "near_single_still", False):  # dungeon@9.25b (R2b)
        out["near_single_still"] = [NEAR_SINGLE_CELLS, FAR_CELLS, WALK_STOP_PX, NEAR_STILL_VERSION]
    if getattr(a, "box_every", BOX_EVERY_S) != BOX_EVERY_S:  # dungeon@9.11 (rogue-xmas02.md 4AD)
        out["box_every"] = float(a.box_every)
    if getattr(a, "far_approach", False):  # dungeon@9.10 (rogue-xmas02.md 4AC)
        out["far_approach"] = [APPROACH_CELLS, APPROACH_KEEP, APPROACH_MAX, APPROACH_HOLD_S]
    if getattr(a, "skip_own_cells", False):  # dungeon@9.9 (rogue-xmas02.md 4AB)
        out["skip_own_cells"] = [SELF_HALF_W, SELF_UP, SELF_DOWN]
    if getattr(a, "explore_cover", False):  # dungeon@9.14b (rogue-xmas02.md 4AO)
        import explore_map as em_c

        out["explore_cover"] = [em_c.COVER_W]
    if getattr(a, "walk_pick_step", False):  # dungeon@9.15c (rogue-xmas02.md 4AU)
        out["walk_pick_step"] = [WALK_PICK_STEP_R, "9.15c"]
    if getattr(a, "walk_pick", False):  # dungeon@9.15 (rogue-xmas02.md 4AM)
        out["walk_pick"] = [WALK_PICK_TOL, "9.15b"]  # b: the plain-fits fallback (after p34)
    if getattr(a, "explore", False):  # dungeon@9.14 (rogue-xmas02.md 4AL)
        import explore_map as em_f

        out["explore"] = [em_f.REGION, em_f.GOOD_HITS, em_f.NOVELTY, em_f.DIST_W, em_f.TEMP,
                          em_f.RECENT_S, EXPLORE_LEG_MAX_S]  # fmt: skip
    if getattr(a, "kill_gap", False):  # dungeon@9.13 (rogue-xmas02.md 4AF)
        out["kill_gap"] = [
            KILL_GAP_S,
            KILL_GAP_HITS,
            "9.13d",
            LOOT_SETTLE_S,
        ]  # b no_miss, c 5 hits, d the loot settle (after p37)
    if getattr(a, "exp_first", True):  # dungeon@9.34 (Batt 11-12, rogue-xmas02.md 4CW): ON
        out["exp_first"] = [EXP_PAIR_S, "9.34"]
    if getattr(a, "garm_fly", False):  # dungeon@9.19 (rogue-xmas02.md 4BA)
        out["garm_fly"] = [list(ALARM_CLASSES), GARM_FRESH_S, "9.19"]
        if getattr(a, "garm_confirm", GARM_CONFIRM) != GARM_CONFIRM:
            out["garm_fly"] = [list(ALARM_CLASSES), GARM_FRESH_S, "9.19b", int(a.garm_confirm)]
    if getattr(a, "boss_walk", False):  # dungeon@9.18 (rogue-xmas02.md 4AZ)
        out["boss_walk"] = [BOSS_WALK_R, BOSS_WALK_MIN, BOSS_WALK_GRACE_S, BOSS_WALK_MAX,
                            BOSS_WALK_WINDOW_S, "9.18"]  # fmt: skip
    if getattr(a, "unreach_escape", False):  # dungeon@9.26 (rogue-xmas02.md Study S-UA)
        out["unreach_escape"] = [UNREACH_K, UNREACH_W_S, UNREACH_TOL, UNREACH_MARK_S,
                                 UNREACH_WALK_R, UNREACH_AWAY, UNREACH_AGAIN_S,
                                 UNREACH_VERSION]  # fmt: skip
    if getattr(a, "stage_mob", None):  # 9.18's trial: a staged encounter (setup only)
        out["stage_mob"] = str(a.stage_mob)
    if getattr(a, "stage_at", None) is not None:  # U0's TRIAL only (rogue-xmas02.md 4BU)
        out["stage_at"] = list(a.stage_at)
    if getattr(a, "start_cell", None) is not None:  # U0's TRIAL only
        out["start_cell"] = list(a.start_cell)
    if getattr(a, "quiet_scan", False):  # dungeon@9.17 (rogue-xmas02.md 4AW)
        out["quiet_scan"] = [QUIET_SCAN_S, "9.17"]
    if getattr(a, "loot_first", False):  # dungeon@9.16 (rogue-xmas02.md 4AT)
        out["loot_first"] = [LOOT_FIRST_VERSION]
    if getattr(a, "reach_check", False):  # dungeon@9.12 (rogue-xmas02.md 4AE)
        out["reach_check"] = [17, 14, "9.12b"]  # walk.py's limits; b: the picked cell (after p25)
    if getattr(a, "late_confirm", False):  # dungeon@9.21 (rogue-xmas02.md 4BI, LF-2)
        out["late_confirm"] = [CONFIRM_S, LATE_CONFIRM_WAIT_S, LATE_CONFIRM_VERSION]
    if getattr(a, "unread_step", False):  # dungeon@9.22 (rogue-xmas02.md 4BI, LF-4)
        out["unread_step"] = [UNREAD_WALK_S, UNREAD_STEP_CELLS, UNREAD_STEPS, UNREAD_READ_S,
                              UNREAD_SAFE_R, UNREAD_MAX_S, UNREAD_STEP_VERSION]  # fmt: skip
    if getattr(a, "still_target", False):  # dungeon@9.23 (rogue-xmas02.md Study S-LS, LS-2)
        out["still_target"] = [WALKER_PX, HOLD_GAP_S, HOLD_MAX_S, STILL_TARGET_VERSION]
    if getattr(a, "lead_press", False):  # dungeon@9.24 (rogue-xmas02.md Study S-LS, LS-1; 4BP)
        out["lead_press"] = [LEAD_PX, LEAD_AGE_S, LEAD_CAP_PX, LEAD_CAP_CELLS, LEAD_PRESS_VERSION]
    if getattr(a, "bare_steal", False) and getattr(a, "steal_cue", "both") != "both":
        out["steal_cue"] = [a.steal_cue, "9.27d"]  # dungeon@9.27d
    if getattr(a, "hud", False):  # dungeon@9.29: display only (the operator HUD)
        out["hud"] = ["9.29"]
    if getattr(a, "hud_fast", None):  # dungeon@9.29b: the HUD-only detection rate
        out["hud_fast"] = [float(a.hud_fast), HUD_FAST_TTL_MS, "9.29b"]
        out["hud_prio"] = ["9.29c"]  # its GPU calls: a HUD twin the detect server serves last
    if getattr(a, "value_target", False):  # dungeon@9.28 (rogue-xmas02.md 4CB; Batt's 100,000 z/h)
        out["value_target"] = ["9.28", 150.0]
    if getattr(a, "loot_items", None):  # dungeon@9.33 (Batt 2026-11-12)
        out["loot_items"] = [str(a.loot_items), LOOT_ITEMS_CONF, LOOT_ITEMS_PX, LOOT_ITEMS_HOVERS,
                             LOOT_ITEMS_VERSION]  # fmt: skip
    if getattr(a, "loot_recheck", False):  # dungeon@9.36 (rogue-xmas02.md 4DA)
        out["loot_recheck"] = [RECHECK_S, RECHECK_EVERY_S, LOOT_RECHECK_VERSION]
    if getattr(a, "loot_memory", False):  # dungeon@9.37 (rogue-xmas02.md 4DB)
        out["loot_memory"] = [MEMORY_S, MEMORY_EVERY_S, MEMORY_KEEP_S, LOOT_MEMORY_VERSION]
    if getattr(a, "loot_aim", False):  # dungeon@9.32 (Study S-IDLE)
        out["loot_aim"] = [LOOT_AIM_HOVERS, LOOT_AIM_R, LOOT_AIM_PX, LOOT_AIM_VERSION]
    if getattr(a, "bare_steal", False) and getattr(a, "swap_gap", False):  # dungeon@9.27e
        out["swap_gap"] = ["9.27e"]
    if getattr(a, "heal_candy", False):  # dungeon@9.31 (Batt 2026-11-11: candies, not potions)
        out["heal_candy"] = [HEAL_CANDY_KEYS, {str(k): v for k, v in HEAL_CANDY_TO.items()},
                             HEAL_CANDY_VERSION]  # fmt: skip
    if getattr(a, "queue", False):  # dungeon@9.30 (rogue-xmas02.md 4CC; Batt 2026-11-11 ~19:3x)
        out["queue"] = [QUEUE_MAX, QUEUE_STALE_S, QUEUE_MATCH_PX, QUEUE_VERSION]
    if getattr(a, "bare_steal", False):  # dungeon@9.27 (rogue-xmas02.md 4BX, Batt 2026-11-11)
        out["bare_steal"] = [bs.BARE_MAX_S, bs.BARE_HP_MIN, bs.EQUIP_KEY, bs.EQUIP_SLOT,
                             bs.BARE_STEAL_VERSION]  # fmt: skip
    if getattr(a, "bare_ready", False):  # dungeon@9.27b (Batt 2026-11-11, after 4BY's p65 / p66)
        out["bare_ready"] = [BARE_READY_VERSION]
    if getattr(a, "steal_opener", None):  # dungeon@9.27c (Batt 2026-11-11 ~19:15: the Knife)
        out["steal_opener"] = [str(a.steal_opener), bs.OPENER_VERSION]
    if getattr(a, "player_mode", False):  # dungeon@9.35 (docs/planning/player-mode.md, Batt 11-12)
        out["player_mode"] = [PLAYER_MIN_WINGS, PLAYER_MIN_HEALS, PLAYER_WINGS_KEEP,
                              PLAYER_MODE_VERSION]  # fmt: skip
    return out


def picked_cell(camera: Any, gat: Any, here: Cell, px: Sequence[float]) -> Cell | None:
    """dungeon@9.12b: the cell the CLIENT picks under game-region pixel ``px`` with the camera on
    ``here`` -- the first tile top the camera ray comes down through (poring_dataset.picking);
    None when the ray hits no top."""
    from poring_dataset import picking as pick_

    pc_ = pick_.pick_cells(camera, gat, here, np.array([[float(px[0]), float(px[1])]]))[0]
    dx_p, dy_p = int(pc_[0]), int(pc_[1])
    return None if dx_p == pick_.NONE else (here[0] + dx_p, here[1] + dy_p)


def walk_pick_ok(picked: Cell | None, target: Cell, okr: Any, tol: int = WALK_PICK_TOL) -> bool:
    """PURE (dungeon@9.15): the client's picked cell under a walk target's pixel is on the route
    grid ``okr`` and within ``tol`` (Chebyshev) of the target."""
    if picked is None:
        return False
    h, w = np.asarray(okr).shape
    if not (0 <= picked[0] < w and 0 <= picked[1] < h) or not okr[picked[1], picked[0]]:
        return False
    return max(abs(picked[0] - target[0]), abs(picked[1] - target[1])) <= tol


def grid_steps(free: Any, goal: Cell, until: Sequence[Cell] = (), max_steps: int = 400) -> Any:
    """PURE (--walk-pick-step, 9.15c): 8-connected step counts to ``goal`` over ``free`` (inf where
    not reached), grown a ring at a time; it stops once every cell of ``until`` has a count."""
    f = np.asarray(free, dtype=bool)
    h, w = f.shape
    dist = np.full((h, w), np.inf)
    if not (0 <= goal[0] < w and 0 <= goal[1] < h) or not f[goal[1], goal[0]]:
        return dist
    front = np.zeros((h, w), dtype=bool)
    front[goal[1], goal[0]] = True
    seen = front.copy()
    dist[goal[1], goal[0]] = 0.0
    want = [c for c in until if 0 <= c[0] < w and 0 <= c[1] < h]
    for step in range(1, max_steps + 1):
        grow = np.zeros_like(front)
        grow[1:, :] |= front[:-1, :]
        grow[:-1, :] |= front[1:, :]
        grow[:, 1:] |= front[:, :-1]
        grow[:, :-1] |= front[:, 1:]
        grow[1:, 1:] |= front[:-1, :-1]
        grow[:-1, :-1] |= front[1:, 1:]
        grow[1:, :-1] |= front[:-1, 1:]
        grow[:-1, 1:] |= front[1:, :-1]
        front = grow & f & ~seen
        if not front.any():
            break
        seen |= front
        dist[front] = float(step)
        if want and all(np.isfinite(dist[c[1], c[0]]) for c in want):
            break
    return dist


def pick_step(here: Cell, dist: Any, fits: Callable[[Cell], bool], reach: Callable[[Cell], bool],
              radius: int = WALK_PICK_STEP_R) -> Cell | None:  # fmt: skip
    """PURE (--walk-pick-step, 9.15c): the cell within ``radius`` of ``here`` that ``fits`` (in
    view, off the UI, the client's pick near it) and ``reach`` (the server walks us there on one
    click), nearest the goal by ``dist`` and nearer than ``here`` (ties: nearer to us); None when
    there is none. Candidates are tried best first, so ``fits`` runs only until one passes."""
    d = np.asarray(dist)
    h, w = d.shape
    d0 = d[here[1], here[0]] if 0 <= here[0] < w and 0 <= here[1] < h else np.inf
    cands = []
    for dy in range(-radius, radius + 1):
        for dx in range(-radius, radius + 1):
            c = (here[0] + dx, here[1] + dy)
            if (dx, dy) == (0, 0) or not (0 <= c[0] < w and 0 <= c[1] < h):
                continue
            dc = d[c[1], c[0]]
            if np.isfinite(dc) and dc < d0:
                cands.append((float(dc), max(abs(dx), abs(dy)), c))
    for _dc, _r, c in sorted(cands):
        if fits(c) and reach(c):
            return c
    return None


def reach_ok(grid: Any, here: Cell, cell: Cell) -> bool:
    """PURE (dungeon@9.12, rogue-xmas02.md 4AE): would the server walk us from ``here`` to the
    monster's ``cell``, or to one of its 8 neighbours (the client walks a melee strike up to the
    target), on ONE click (poring_dataset.walk.click_walk_ok: a walk, <= 17 steps, <= 14 unless the
    straight line is clear). Pilots p16-p21 lost 110-153 s a run clicking monsters it was not."""
    from poring_dataset import walk as wkp

    for dx, dy in ((0, 0), (1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (1, -1), (-1, 1), (-1, -1)):
        if wkp.click_walk_ok(grid, here[0], here[1], cell[0] + dx, cell[1] + dy):
            return True
    return False


def boss_names(map_name: str, spawns: Mapping[str, Any], mobs: Mapping[str, Any],
               skills: Mapping[str, Any]) -> tuple[str, ...]:  # fmt: skip
    """PURE: the map's boss spawns (``boss`` true) and every monster their NPC_SUMMONSLAVE skills
    call, by the names the KB knows (the spawn's name and the mob table's, which may differ:
    1515 is "Garm Baby" in the spawns and "Baby Hatii" in the mob table)."""
    entries = spawns.get(map_name) or []
    by_id: dict[str, set[str]] = {}
    for e in entries:
        by_id.setdefault(str(e.get("id")), set()).add(str(e.get("name")))
    out: set[str] = set()
    for e in entries:
        if not e.get("boss"):
            continue
        ids = {str(e.get("id"))}
        for sk in skills.get(str(e.get("id")), []):
            if str(sk.get("info", "")).endswith("@NPC_SUMMONSLAVE"):
                ids |= {str(v) for v in sk.get("vals", []) if str(v).strip()}
        for i in ids:
            out |= by_id.get(i, set())
            if mobs.get(i, {}).get("name"):
                out.add(str(mobs[i]["name"]))
    return tuple(sorted(out))


def boss_spawn_names(map_name: str, spawns: Mapping[str, Any],
                     mobs: Mapping[str, Any]) -> tuple[str, ...]:  # fmt: skip
    """PURE (--boss-walk, 9.18): the names of the map's BOSS spawns only (the spawn's name and the
    mob table's), without their summons -- the boss itself always takes the Fly Wing."""
    out: set[str] = set()
    for e in spawns.get(map_name) or []:
        if e.get("boss"):
            out.add(str(e.get("name")))
            name = (mobs.get(str(e.get("id"))) or {}).get("name")
            if name:
                out.add(str(name))
    return tuple(sorted(out))


def alarm_seen(alarm: tuple[float, Sequence[Any]], now: float,
               fresh_s: float = GARM_FRESH_S, streak: int = 1,
               need: int = GARM_CONFIRM) -> Any | None:  # fmt: skip
    """PURE (--garm-fly, 9.19): the first box of an alarm class in a detection at most ``fresh_s``
    old (``alarm``: the box watcher's (grab time, alarm boxes)), else None. 9.19b: also None while
    fewer than ``need`` consecutive detections (``streak``, the latest included) held one."""
    t, boxes = alarm
    if not boxes or now - t > fresh_s or streak < need:
        return None
    return boxes[0]


def alarm_streak(prev: int, has_alarm: bool) -> int:
    """PURE (9.19b): consecutive detections with an alarm box, the new detection included."""
    return prev + 1 if has_alarm else 0


def boss_walk_allowed(name: str, boss_only: Sequence[str], walks: Sequence[float], now: float,
                      max_n: int = BOSS_WALK_MAX,
                      window_s: float = BOSS_WALK_WINDOW_S) -> bool:  # fmt: skip
    """PURE (--boss-walk, 9.18): a summon (not the boss itself) with fewer than ``max_n`` walk-aways
    in the last ``window_s``."""
    return name not in boss_only and sum(1 for t in walks if now - t < window_s) < max_n


def walk_away_target(here: Cell, fits: Callable[[Cell], bool], reach: Callable[[Cell], bool],
                     radius: int = BOSS_WALK_R,
                     min_d: int = BOSS_WALK_MIN) -> Cell | None:  # fmt: skip
    """PURE (--boss-walk, 9.18): the cell within ``radius`` (Chebyshev) of ``here``, at least
    ``min_d`` away, that ``fits`` (in view, off the UI and zones, the client's pick near it) and
    ``reach`` (one click the server answers), FARTHEST from us first (ties: the smaller cell, a
    fixed order); None when there is none."""
    cands = [(max(abs(dx), abs(dy)), (here[0] + dx, here[1] + dy))
             for dy in range(-radius, radius + 1) for dx in range(-radius, radius + 1)
             if max(abs(dx), abs(dy)) >= min_d]  # fmt: skip
    for _d, c in sorted(cands, key=lambda dc: (-dc[0], dc[1])):
        if fits(c) and reach(c):
            return c
    return None


# --unreach-escape (dungeon@9.26, rogue-xmas02.md Study S-UA; Batt 2026-11-11, 4BT item 1: "build
# it and set its bars"): p57's UNREACHABLE ATTACKER. A Cruiser (the KB: attack range 7) on
# (98,205) shot the Rogue on (100,207), two cells diagonal across two CLIFF cells (no walk, no wall
# for a shot), for 11 min. Her client sent an attack request every ~1.2 s, the server stopped her
# on her own cell each time (a walk click round the cliff, 4-7 steps, was never tried), and the
# ring scan re-struck it 91 times, every lock ending "no hits". THE TRIGGER (the study's rule):
# UNREACH_K consecutive locks ending "no hits" on cells within UNREACH_TOL of each other, within
# UNREACH_W_S, an attacked sign (a Miss cue, a hit line on us, an HP drop) in each lock's window,
# and none of our damage lines. THE ESCAPE: (c) the chain's cells (+ UNREACH_MARK_R) are skipped by
# the defend scan and the box path for UNREACH_MARK_S, and (a) ONE walk click to the pickable,
# one-click cell in view farthest from them, at least UNREACH_AWAY cells (out of a Cruiser's 7 +
# the pixel cell's 1-cell slip), where the cursor reads clear (the first of UNREACH_TRIES such
# cells); (b) the Fly Wing when there is no such cell, no position, or the trigger fires again
# within UNREACH_AGAIN_S of an unreach walk.
UNREACH_VERSION = "9.26"
UNREACH_K, UNREACH_W_S, UNREACH_TOL = 3, 90.0, 1
UNREACH_MARK_S, UNREACH_MARK_R = 120.0, 1
UNREACH_WALK_R, UNREACH_AWAY = 12, 9
UNREACH_GRACE_S, UNREACH_AGAIN_S, UNREACH_TRIES = 2.5, 120.0, 3


@dataclass(frozen=True)
class NoHitLock:
    """--unreach-escape (9.26): one lock that ended "no hits" -- its start (the lock's clock), its
    end (the unlock), the cell it struck (our cell + the strike's rel; None unknown), the strike
    count after its strike (consecutive locks: + 1 each, no strike between them) and the latest
    attacked sign (a Miss cue read, a hit line on us, an HP drop) at its end."""

    t0: float
    t1: float
    cell: Cell | None
    n: int
    sign_t: float


def unreach_trigger(locks: Sequence[NoHitLock], ours: Sequence[float], k: int = UNREACH_K,
                    w: float = UNREACH_W_S,
                    tol: int = UNREACH_TOL) -> dict[str, Any] | None:  # fmt: skip
    """PURE (--unreach-escape, 9.26): the evidence when the newest ``k`` no-hit locks are ONE
    chain, else None. A chain: consecutive strikes (``n`` + 1 each); every cell known and all
    within ``tol`` of each other (Chebyshev, pairwise: the x and the y spread each <= ``tol``); the
    first lock's start to the last one's end at most ``w`` s; an attacked sign in every lock's
    window (the first: its own span; each other: after the previous lock's end); and none of our
    damage lines (``ours``: their ticks) from the first start to the last end."""
    if k < 1 or len(locks) < k:
        return None
    ch = list(locks)[-k:]
    cells = [c.cell for c in ch if c.cell is not None]
    if len(cells) < k:
        return None
    xs, ys = [c[0] for c in cells], [c[1] for c in cells]
    if max(xs) - min(xs) > tol or max(ys) - min(ys) > tol:
        return None
    if any(b.n != a.n + 1 for a, b in zip(ch, ch[1:], strict=False)):
        return None
    t0, t1 = ch[0].t0, ch[-1].t1
    if t1 - t0 > w:
        return None
    if not ch[0].t0 <= ch[0].sign_t <= ch[0].t1:
        return None
    if any(not a.t1 < b.sign_t <= b.t1 for a, b in zip(ch, ch[1:], strict=False)):
        return None
    if any(t0 <= t <= t1 for t in ours):
        return None
    return {"locks": k, "cells": [list(c) for c in cells], "span_s": round(t1 - t0, 1),
            "n": [c.n for c in ch], "t0": t0, "t1": t1}  # fmt: skip


def unreach_marks(marks: Mapping[Cell, float], cells: Sequence[Sequence[int]], until: float,
                  r: int = UNREACH_MARK_R) -> dict[Cell, float]:  # fmt: skip
    """PURE (9.26, escape (c)): ``marks`` (cell -> until) with every cell within ``r`` of the
    chain's ``cells`` marked until ``until`` (a later until is kept)."""
    out = dict(marks)
    for c in cells:
        for dy in range(-r, r + 1):
            for dx in range(-r, r + 1):
                m = (int(c[0]) + dx, int(c[1]) + dy)
                out[m] = max(out.get(m, -1e9), until)
    return out


def unreach_marked(marks: Mapping[Cell, float], cell: Sequence[int] | None, now: float) -> bool:
    """PURE (9.26, escape (c)): ``cell`` is marked unreachable at ``now``."""
    return cell is not None and marks.get((int(cell[0]), int(cell[1])), -1e9) > now


def unreach_scan_cells(cells: Sequence[Cell], here: Cell | None, marks: Mapping[Cell, float],
                       now: float) -> list[Cell]:  # fmt: skip
    """PURE (9.26, escape (c)): the defend scan's ring cells (relative to ``here``) without the
    marked ones; all of them when our cell is unknown."""
    if here is None:
        return list(cells)
    return [c for c in cells if not unreach_marked(marks, (here[0] + c[0], here[1] + c[1]), now)]


def unreach_walk_targets(here: Cell, cells: Sequence[Sequence[int]], fits: Callable[[Cell], bool],
                         reach: Callable[[Cell], bool], radius: int = UNREACH_WALK_R,
                         away: int = UNREACH_AWAY,
                         limit: int = UNREACH_TRIES) -> list[Cell]:  # fmt: skip
    """PURE (9.26, escape (a)): up to ``limit`` cells within ``radius`` (Chebyshev) of ``here``, at
    least ``away`` from EVERY chain cell, that ``fits`` (in view, off the UI and zones, the
    client's pick near it) and ``reach`` (one click the server answers), in order: the farthest
    from the nearest chain cell first, then the nearest to us, then the smaller cell (a fixed
    order). The runner hovers them in this order and clicks the first that reads clear."""
    if not cells or limit < 1:
        return []

    def gap(c: Cell) -> int:
        return min(max(abs(c[0] - int(a[0])), abs(c[1] - int(a[1]))) for a in cells)

    cands = [(here[0] + dx, here[1] + dy) for dy in range(-radius, radius + 1)
             for dx in range(-radius, radius + 1)]  # fmt: skip
    cands = [c for c in cands if gap(c) >= away]
    order = sorted(cands, key=lambda c: (-gap(c), max(abs(c[0] - here[0]), abs(c[1] - here[1])),
                                         c))  # fmt: skip
    out: list[Cell] = []
    for c in order:
        if fits(c) and reach(c):
            out.append(c)
            if len(out) >= limit:
                break
    return out


def unreach_action(here: Cell | None, walk_to: Cell | None, walks: Sequence[float], now: float,
                   again_s: float = UNREACH_AGAIN_S) -> tuple[str, str]:  # fmt: skip
    """PURE (9.26): the escape when the trigger fires -- ("fly", "again") after an unreach walk
    within ``again_s``; ("fly", "no_position") without our cell; ("fly", "no_cell") without a walk
    target; else ("walk", "away")."""
    if any(now - t < again_s for t in walks):
        return ("fly", "again")
    if here is None:
        return ("fly", "no_position")
    if walk_to is None:
        return ("fly", "no_cell")
    return ("walk", "away")


def unreach_refused(reach_check: bool, engage_screen: bool) -> str | None:
    """PURE (9.26): why the flag cannot work as built -- its box-path skip lives in --reach-check's
    reach test (the box paths of --engage-screen), and its walk needs the server grid. None: it can
    run."""
    if not reach_check:
        return "--unreach-escape needs --reach-check (the server grid; the box path's skip)"
    if not engage_screen:
        return "--unreach-escape needs --engage-screen (its box paths honour the marks)"
    return None


def boss_of(name_read: str | None, bosses: Sequence[str], species: Sequence[str]) -> str | None:
    """PURE: the boss a Battle Log line's bracketed name reads as, or None. The fit is the
    reader's own (battle_log.species_of: '?' = 1-2 unread letters) over the bosses AND the map's
    other species, so a garbled ordinary name can never fit a boss by elimination."""
    if not name_read or not bosses:
        return None
    import battle_log

    fit = battle_log.species_of(str(name_read), tuple(bosses) + tuple(species))
    return fit if fit in bosses else None


def approach_cell(rel: Sequence[int], keep: int = APPROACH_KEEP) -> tuple[int, int]:
    """PURE (--far-approach): the cell ``keep`` cells short of ``rel`` on the line from us."""
    x, y = int(rel[0]), int(rel[1])
    d = max(abs(x), abs(y))
    if d <= keep:
        return (0, 0)
    f = (d - keep) / d
    return (round(x * f), round(y * f))


def far_window(rel: Sequence[int], from_cells: int = FAR_CELLS) -> float | None:
    """PURE (--far-single): how long a strike at ``rel`` waits for its arrow / damage line with
    ONE click, or None when it is nearer than ``from_cells`` (FAR_CELLS; --near-single, 9.25:
    NEAR_SINGLE_CELLS) -- the burst as before."""
    cells = max(abs(int(rel[0])), abs(int(rel[1])))
    if cells < from_cells:
        return None
    return min(FAR_MAX_S, FAR_BASE_S + FAR_PER_CELL_S * cells)


def near_still_cells(rel: Sequence[int], on: bool) -> bool:
    """PURE (--near-single-still, 9.25b): this strike's re-clicks are scroll-gated (2-3 cells)."""
    cells = max(abs(int(rel[0])), abs(int(rel[1])))
    return on and NEAR_SINGLE_CELLS <= cells < FAR_CELLS


def near_still_reclick(shift: tuple[float, float], px: float = WALK_STOP_PX) -> bool:
    """PURE (9.25b): a scroll-gated re-click goes out only while the scene moved < ``px``."""
    return math.hypot(float(shift[0]), float(shift[1])) < px


def quick_no_hit(arrow_t: float | None, last_ours: float, t_click: float, now: float,
                 hit_s: float = QUICK_HIT_S) -> bool:  # fmt: skip
    """PURE (--quick-drop): the lock drops -- the strike's arrow showed at ``arrow_t`` and none of
    our hits was seen since its click for ``hit_s`` after the arrow."""
    return arrow_t is not None and last_ours < t_click and now - arrow_t > hit_s


def quick_hit_window(rel: Sequence[int], far_w: float | None = None) -> float:
    """PURE (--quick-drop-scaled, dungeon@9.38, rogue-xmas02.md 4DG): the no-hit window after the
    arrow of a strike at ``rel`` (cells from us, Chebyshev): QUICK_HIT_S + QUICK_PER_CELL x cells,
    at most QUICK_HIT_MAX_S, and never shorter than --far-single's own window ``far_w`` (so never
    shorter than the default rule's hit_s)."""
    cells = max(abs(int(rel[0])), abs(int(rel[1])))
    w = min(QUICK_HIT_MAX_S, QUICK_HIT_S + QUICK_PER_CELL * cells)
    return w if far_w is None else max(w, float(far_w))


def quick_scaled_refused(a: argparse.Namespace) -> str | None:
    """PURE (dungeon@9.38): --quick-drop-scaled changes --quick-drop's no-hit window, so it needs
    --quick-drop (None: it can run, or it is off)."""
    if getattr(a, "quick_drop_scaled", False) and not getattr(a, "quick_drop", False):
        return "--quick-drop-scaled goes with --quick-drop (it scales that flag's no-hit window)"
    return None


def loot_settling(
    settle_t: float,
    last_pos_t: float,
    now: float,
    settle_s: float = LOOT_SETTLE_S,
    max_s: float = LOOT_SETTLE_MAX_S,
) -> bool:
    """PURE (9.13d): hold walk clicks after a loot step that clicked (``settle_t``) until a position
    read taken ``settle_s`` after it, at most ``max_s``."""
    return now - settle_t < max_s and last_pos_t < settle_t + settle_s


def kill_gapped(hits_on_lock: int, since_last_hit: float, gap_s: float = KILL_GAP_S,
                min_hits: int = KILL_GAP_HITS) -> bool:  # fmt: skip
    """PURE (--kill-gap): the locked target is taken as dead -- at least ``min_hits`` of our hits
    landed on this lock and none for ``gap_s`` since the last."""
    return hits_on_lock >= min_hits and since_last_hit > gap_s


def exp_kill(
    kind: str, tick: float, pair: tuple[str, float] | None, pair_s: float = EXP_PAIR_S
) -> tuple[bool, tuple[str, float] | None]:
    """PURE (dungeon@9.34, exp-first): is this exp line (``kind`` "base_exp" / "job_exp") a NEW
    kill? ``pair`` is the last counted kill's line (kind, tick) while it waits for its other
    half: the other kind within ``pair_s`` is the same kill (the pair closes, no kill); anything
    else (the same kind again, or later) is a new kill whose line opens a pair."""
    if pair is not None and pair[0] != kind and tick - pair[1] <= pair_s:
        return False, None
    return True, (kind, tick)


def scan_needed(now: float, last_taken: float, last_ours: float, last_swing: float,
                hp_drop: bool, window_s: float = QUIET_SCAN_S) -> bool:  # fmt: skip
    """PURE (--quiet-scan, 9.17): the screen showed damage within ``window_s`` -- a hit line on us,
    a damage line of ours, a Miss read at us -- or the HP just dropped; else the scan is skipped."""
    recent = min(now - last_taken, now - last_ours, now - last_swing)
    return hp_drop or recent < window_s


def box_engage_held(loot_first: bool, mode: str, loot_pending: bool) -> bool:
    """PURE (--loot-first, 9.16 part 1): a box alone starts no fight while a kill's loot step is
    pending -- the fight has ended (``after``) and the loot list is not empty."""
    return loot_first and mode == "after" and loot_pending


def quiet_kill_ends(kills: Sequence[float], tick: float, fight_t0: float,
                    loot_first: bool) -> bool:  # fmt: skip
    """PURE: the quiet-kill rule's kill part -- a kill in the last 3 s (as before); with
    --loot-first (9.16 part 2) only a kill that came after this fight began, so a fight started
    right after a kill is not ended by that kill in its first tick."""
    if not kills or kills[-1] <= tick - 3.0:
        return False
    return not loot_first or kills[-1] >= fight_t0


def kill_gap_no_miss(kill_gap: bool, box_fight: Mapping[str, Any]) -> bool:
    """PURE (dungeon@9.13b, --kill-gap): a box-engaged fight the quiet-kill rule closes BEFORE the
    box path looked (``tried`` unset) is no box miss. p24: 14 of its first 15 box misses were such
    fights (a box engaged within 3 s after a kill), and 10 spots went ignored."""
    return kill_gap and not box_fight.get("tried")


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
                 map_name: str | None = None, detector: str = "cpu",
                 every_s: float = BOX_EVERY_S) -> None:  # fmt: skip
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
        self.last_pick: dict[str, Any] | None = None  # dungeon@9.28: --value-target's choice
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
        self.alarm: tuple[float, list[Any]] = (0.0, [])  # 9.19: boxes of ALARM_CLASSES
        self.hist: deque[tuple[float, list[Any]]] = deque(maxlen=LOOT_AIM_HIST)  # 9.32
        self.alarm_n = 0  # 9.19b: consecutive detections that held one (alarm_streak)
        # dungeon@8.9 (--box-now): a detection on demand. kick() numbers the request; the loop's
        # next detection takes it (its grab starts after the kick) and records the number
        self.kick_ev = threading.Event()
        self.kick_seq = 0
        self.kick_prefer: str | None = None
        self.meta: dict[str, Any] = {"kick": 0}
        self.paths: Counter[str] = Counter()  # which path gave each detection
        self.halt = threading.Event()
        self.every_s = float(every_s)  # dungeon@9.11 (--box-every): the watcher's rhythm
        # dungeon@9.29b (--hud-fast, Batt 2026-11-11: "the boxes come late"): HUD-ONLY detections
        # between the rhythm's own, into hud_last; last / alarm / meta / n never see them
        self.hud_every_s: float | None = None
        self.hud_last: tuple[float, list[Any]] = (0.0, [])
        self.n_hud = 0
        # dungeon@9.29c: on the GPU path the HUD-only detections run in their OWN thread
        # (start_hud), on the detector's HUD twin and their own grab helper
        self.hud_det: Any = None
        self.hud_screen: Any = None
        self.hud_th: threading.Thread | None = None
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
                alarm = [b for b in raw if b.cls in ALARM_CLASSES]  # 9.19: never struck
            except Exception:  # noqa: BLE001 -- a dead worker ends the watcher, not the run
                return
            path = str(getattr(self.det, "last_path", "")) or "cpu"
            with self.cond:
                self.last = (t, got)
                self.hist.append((t, got))  # dungeon@9.32 (--loot-aim): the recent detections
                self.alarm = (t, alarm)
                self.alarm_n = alarm_streak(self.alarm_n, bool(alarm))
                self.meta = {"kick": seq, "t": t, "t_done": time.monotonic(), "path": path,
                             "ms": self.det.last_ms, "prefer": prefer,
                             "reason": getattr(self.det, "last_reason", None)}  # fmt: skip
                self.n += 1
                self.paths[path] += 1
                self.cond.notify_all()
            every = getattr(self, "every_s", BOX_EVERY_S)  # (a test builds it without __init__)
            hud_every = getattr(self, "hud_every_s", None)
            while hud_every and not self.halt.is_set():  # dungeon@9.29b: HUD-only detections
                left = every - (time.monotonic() - t)
                if left <= hud_every or self.kick_ev.wait(hud_every):
                    break  # the rhythm's slot is near, or a kick: the regular detection first
                try:
                    t_h = time.monotonic()
                    img_h = np.ascontiguousarray(self.screen.grab(*self.region)[1][..., :3])
                    raw_h = self.det.detect(img_h, prefer="gpu") if self.gpu else \
                        self.det.detect(img_h)  # fmt: skip
                except Exception:  # noqa: BLE001 -- display only: the HUD stream just stops
                    break
                with self.lock:
                    self.hud_last = (t_h, [b for b in raw_h if b.cls == "monster"])
                    self.n_hud += 1
            self.kick_ev.wait(max(0.0, every - (time.monotonic() - t)))
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

    def snapshot(self) -> tuple[float, list[tuple[float, float, float, float]]]:
        """dungeon@9.5 (--lead-strike): the last detection's grab time and its monster boxes
        (x0, y0, x1, y1), our own sprite's boxes left out (as ``near`` does)."""
        with self.lock:
            t, got = self.last
        return t, [(b.x0, b.y0, b.x1, b.y1) for b in got
                   if not self_box((b.x0 + b.x1) / 2, (b.y0 + b.y1) / 2)]  # fmt: skip

    def recent(self, max_age_s: float) -> list[list[tuple[float, float, float, float]]]:
        """dungeon@9.32 (--loot-aim): the monster boxes (x0, y0, x1, y1) of the last detections,
        newest first, none older than ``max_age_s``. Our own sprite's boxes are NOT left out: a
        monster next to her overlaps it (the replay on p69 / p70 / p73)."""
        now = time.monotonic()
        with self.lock:
            h = list(self.hist)
        return [[(b.x0, b.y0, b.x1, b.y1) for b in got] for t, got in reversed(h)
                if now - t <= max_age_s]  # fmt: skip

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
             skip: Any = None, values: Mapping[str, float] | None = None,
             ) -> tuple[float, ...] | None:  # fmt: skip
        """The nearest fresh monster box whose foot is within ``max_px`` of ``px``; a box whose
        foot ``skip`` (dungeon@5: an ignored box spot) refuses is passed over. With ``values``
        (dungeon@9.28, --value-target) the same candidates are ranked by value_target.score
        instead (``last_pick`` records the choice)."""
        with self.lock:
            t, got = self.last
        if time.monotonic() - t > fresh_s:
            return None
        best = None
        cands: list[tuple[float, Any]] = []  # dungeon@9.28: the same candidates, for --value-target
        for b in got:
            if self_box((b.x0 + b.x1) / 2, (b.y0 + b.y1) / 2):
                self.n_self += 1  # 3.98 run 1 (12:11): v1 boxes our OWN Crusader as a monster
                continue
            if skip is not None and skip(((b.x0 + b.x1) / 2, b.y1)):
                self.n_skip += 1
                continue
            d = math.hypot((b.x0 + b.x1) / 2 - px[0], b.y1 - px[1])
            if d <= max_px:
                cands.append((d, b))
            if d <= max_px and (best is None or d < best[0]):
                best = (d, b.x0, b.y0, b.x1, b.y1)
        self.last_pick = None
        if values and cands:  # dungeon@9.28 (--value-target): the box worth the most
            d_v, b_v = value_pick(cands, values)
            self.last_pick = {"species": box_species(b_v), "d": round(d_v),
                              "nearest_d": None if best is None else round(best[0])}  # fmt: skip
            return (b_v.x0, b_v.y0, b_v.x1, b_v.y1)
        return None if best is None else best[1:]

    def start_hud(self, every_s: float, log_path: Path | None = None) -> None:
        """--hud-fast: HUD-only detections every ``every_s`` into hud_last (dungeon@9.29b).

        dungeon@9.29c (Batt 2026-11-11: a fast HUD that does not slow the decisions; s73's D1 p95
        93.5 ms, rogue-xmas02.md 4CI): on the GPU path they run in a thread of their own, with
        their own grab helper (ro_agent.Screen is one pipe), on the detector's HUD twin
        (unit_detector.GpuDetector.hud_twin: a second connection the detect server serves only
        between the decision calls' forwards, skipping a frame that cannot start in time). So a
        kick never waits for a HUD call, and a decision call at most for one HUD forward in
        flight. The twin never runs the CPU. Its calls are logged to ``log_path``, apart from the
        decisions' detections.jsonl. The CPU detector keeps 9.29b's HUD calls between the
        watcher's own (its worker is one pipe)."""
        if not self.gpu:
            self.hud_every_s = float(every_s)
            return
        self.hud_det = self.det.hud_twin()
        self.hud_det.log_path = log_path
        self.hud_screen = self.r.Screen()
        self.hud_th = threading.Thread(target=self._hud_loop, args=(float(every_s),),
                                       name="hud-watch", daemon=True)  # fmt: skip
        self.hud_th.start()

    def _hud_loop(self, every: float) -> None:
        """dungeon@9.29c: the HUD twin's detections, one every ``every`` s, into hud_last only
        (last / alarm / meta / n are the decisions'). A frame the server skipped, or any call
        without GPU boxes, leaves hud_last as it was."""
        while not self.halt.wait(every):
            try:
                t_h = time.monotonic()
                img_h = np.ascontiguousarray(self.hud_screen.grab(*self.region)[1][..., :3])
                raw_h = self.hud_det.detect(img_h)
            except Exception:  # noqa: BLE001 -- display only: the HUD stream just stops
                return
            if self.hud_det.last_path != "gpu":
                continue  # skipped by the server, or no GPU now: the HUD keeps what it has
            with self.lock:
                self.hud_last = (t_h, [b for b in raw_h if b.cls == "monster"])
                self.n_hud += 1

    def hud_info(self) -> dict[str, Any] | None:
        """dungeon@9.29c: for the run's end event, the HUD twin's detections (None without)."""
        if self.hud_det is None:
            return None
        return {"n_hud": self.n_hud, **self.hud_det.info()}

    def stop(self) -> None:
        self.halt.set()
        self.kick_ev.set()
        self.th.join(timeout=3)
        with contextlib.suppress(Exception):
            self.screen.proc.terminate()
        hud_th = getattr(self, "hud_th", None)  # dungeon@9.29c (a test builds it without __init__)
        if hud_th is not None:
            hud_th.join(timeout=3)
            with contextlib.suppress(Exception):
                self.hud_screen.proc.terminate()
            with contextlib.suppress(Exception):
                self.hud_det.close()  # its socket only: the CPU worker is the watcher's


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
    """PURE: the first slot of a tab that is not empty -- every Etc item is loot for the Crusader
    (potions and Fly Wings live in Use, the gear in Eqp); clear-bag empties any tab this way."""
    return next((i for i, k in enumerate(kinds) if k != "empty"), None)


def clear_etc(agent: Any, screen: Any, *, why: str, max_drops: int = 40) -> dict[str, Any]:
    """Drop every stack of the inventory's ETC tab (clear_tab)."""
    return clear_tab(agent, screen, tab="etc", why=why, max_drops=max_drops)


def clear_tab(agent: Any, screen: Any, *, tab: str, why: str,
              max_drops: int = 40) -> dict[str, Any]:  # fmt: skip
    """Drop every stack of the inventory tab ``tab`` (gm_state.INV_TABS: etc / use / eqp) by
    gm_state.clear_loot's own known path (the tab label, two motions; a drag onto open ground;
    Enter on the quantity prompt matched to its OK button first; the tab must change after each
    drop), r.Stop on anything unexpected. Equipped items are not in the inventory's list, so
    the Eqp tab holds only what is NOT worn."""
    import gm_state as gs
    import ro_agent as r
    import ui_gate

    if tab not in gs.INV_TABS:
        raise ValueError(f"tab {tab!r}: one of {sorted(gs.INV_TABS)}")
    refs = gs.load_loot_refs()
    ok_ref = np.load(gs.LOOT_DIR / "prompt_ok.npy")
    region = r.game_region()
    out: dict[str, Any] = {"tab": tab, "dropped": 0}

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
    ui_gate.ensure_clear(agent, screen, why=f"{why}:{tab}-start")
    r.activate_client(agent, screen)
    agent.chord(*ui_gate.window_keys("inventory"))
    time.sleep(1.0)
    try:
        if not inv_open():
            raise r.Stop(f"clear_tab ({why}): the inventory did not read open after its chord")
        gs._tab(agent, screen, tab)
        fails = 0
        n = gs.INV_COLS * gs.INV_ROWS
        while out["dropped"] < max_drops:
            if not inv_open():
                raise r.Stop(f"clear_tab ({why}): the inventory closed during the drops")
            f = frame()
            crops = [gs.icon_crop(f, c % gs.INV_COLS, c // gs.INV_COLS) for c in range(n)]
            i = first_item([gs.classify_icon(c, refs)[0] for c in crops])
            if i is None:
                out["empty"] = True  # every slot of the tab read empty
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
                    raise r.Stop(f"clear_tab ({why}): the quantity prompt stayed open")
            after = [gs.icon_crop(f2, c % gs.INV_COLS, c // gs.INV_COLS) for c in range(n)]
            if not gs.tab_changed(crops, after, i):
                fails += 1
                if fails >= 2:
                    raise r.Stop(f"clear_tab ({why}): slot {i} did not drop twice")
                continue
            out["dropped"] += 1
    finally:
        r.activate_client(agent, screen)
        agent.chord(*ui_gate.window_keys("inventory"))
        time.sleep(1.0)
        ui_gate.ensure_clear(agent, screen, why=f"{why}:{tab}")
    return out


BAG_TABS = ("etc", "use", "eqp")  # clear-bag's order: the loot first, the worn gear never listed


def bag_restock(tabs: Sequence[str], before: dict[int, int | None],
                targets: dict[int, int]) -> dict[int, int]:  # fmt: skip
    """PURE (clear-bag): what to add so the hotbar's stock reaches ``targets``. The Use tab was
    just emptied AND read empty, so its stock is 0 whatever the hotbar draws (an empty slot's
    count may not read); otherwise stock_plan's rule (an unreadable count is a ValueError)."""
    if "use" in tabs:
        return dict(targets)
    return stock_plan(before, targets)


def clear_bag(a: argparse.Namespace) -> int:
    """LIVE (Batt 2026-11-08: "drop everything first; keep only what is needed: potions, 10 is
    enough, and the wings; drop everything else except what is worn"): on the clear stand, empty
    the inventory tabs (clear_tab, every stack), then restock the character's run stock
    (``potions_to`` White Potions, ``wings_to`` Fly Wings: the same @item lines as a run's setup)
    and read the hotbar's counts back. The worn gear is not in the inventory's list."""
    import bench
    import crusader as cr
    import gm_state
    import hotbar_count as hb
    import ro_agent as r
    import ui_gate

    conf = CHARS_CONF[a.char]
    crk = conf.get("data", a.char)
    keys_ = conf["keys"]
    tabs = [t.strip() for t in a.tabs.split(",") if t.strip()]
    if not tabs or any(t not in BAG_TABS for t in tabs):
        raise SystemExit(f"--tabs {a.tabs!r}: from {list(BAG_TABS)}")
    p_to = int(conf["potions_to"] or POTIONS_TO)
    w_to = int(conf["wings_to"])
    targets = {STOCK_ITEMS["potion"]: p_to, STOCK_ITEMS["fly"]: w_to}
    out_dir = Path(a.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    rec: dict[str, Any] = {"char": a.char, "tabs": tabs, "targets": targets,
                           "t0": time.strftime("%FT%T%z")}  # fmt: skip
    region = r.game_region()

    def shot(name: str) -> None:  # the evidence frame (BGR grab -> an RGB PNG in out_dir)
        from PIL import Image

        f = np.asarray(r.grab_after(screen, region, r.ns()))[..., :3]
        Image.fromarray(np.ascontiguousarray(f[..., ::-1])).save(out_dir / f"{name}.png")

    with r.session("rule:dungeon-clear-bag") as (agent, screen):
        agent.wait_for_human()
        got = cr.check(screen, conf["job"], crk)
        if not got["ok"]:
            raise r.Stop(f"identity {got}")
        # dungeon@9.27: the Rogue BARE (the dagger in the bag) would lose the dagger here
        why_bb = clear_bag_bare_refused(
            bs.slot_gray(np.asarray(r.grab_after(screen, region, r.ns()))), keys_)  # fmt: skip
        if why_bb is not None:
            raise r.Stop(why_bb)
        # dungeon@9.27c: nor a weapon the runner swaps to (--steal-opener's opener in the bag)
        g_be = bs.slot_gray(np.asarray(r.grab_after(screen, region, r.ns())))
        why_be = clear_bag_eqp_refused(g_be, keys_, tabs)
        if why_be is not None:
            raise r.Stop(why_be)
        ui_gate.ensure_clear(agent, screen, why="clear-bag")
        # clear-bag is the lab's alone (it warps and tops up): never a player's run
        typed_line(agent, screen, f"@warp {CLEAR_STAND[0]} {CLEAR_STAND[1]} {CLEAR_STAND[2]}",
                   conf["job"], crk, player_mode=False)  # fmt: skip
        t_w = time.monotonic()
        time.sleep(3.0)
        while not cr.check(screen, conf["job"], crk)["ok"]:
            if time.monotonic() - t_w > WARP_READY_S:
                raise r.Stop(f"clear-bag: the identity did not read within {WARP_READY_S} s")
            time.sleep(0.5)
        bench.close_chat(agent, screen)
        rec["weight_before"] = gm_state._weight(gm_state._frames(screen))
        shot("before")
        rec["cleared"] = {}
        for tab in tabs:
            rec["cleared"][tab] = clear_tab(agent, screen, tab=tab, why=f"clear-bag:{tab}")
            if not rec["cleared"][tab].get("empty"):
                raise r.Stop(f"clear-bag: the {tab} tab did not read empty {rec['cleared'][tab]}")
        rec["weight_cleared"] = gm_state._weight(gm_state._frames(screen))
        tpl = hb.load()
        slots = {STOCK_ITEMS[k]: hotbar_slot(keys_[k]) for k in STOCK_ITEMS}
        gx0, gy0, gw, gh = region

        def read_stock() -> dict[int, int | None]:
            time.sleep(0.8)
            g = hb.gray(np.asarray(r.grab_after(screen, (gx0, gy0, gw, gh), r.ns())))
            return {item: hb.read_count(g, slot, tpl) for item, slot in slots.items()}

        before = read_stock()
        try:
            add = bag_restock(tabs, before, targets)
        except ValueError as exc:
            raise r.Stop(f"clear-bag: {exc} {before}") from exc
        for item, n in add.items():
            if n > 0:
                typed_line(agent, screen, f"@item {item} {n}", conf["job"], crk, player_mode=False)
                time.sleep(0.8)
        bench.close_chat(agent, screen)
        after = read_stock()
        rec["stock"] = {"before": before, "added": add, "after": after}
        rec["weight_after"] = gm_state._weight(gm_state._frames(screen))
        shot("after")
        rec["t1"] = time.strftime("%FT%T%z")
        (out_dir / "clear-bag.json").write_text(json.dumps(rec, indent=1, default=str) + "\n")
        print(json.dumps(rec, default=str))
        short = {i: c for i, c in after.items() if c is None or c < targets[i]}
        if short:
            raise r.Stop(f"clear-bag: the stock is short after the restock {rec['stock']}")
    return 0


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


# --- --bare-steal (dungeon@9.27, rogue-xmas02.md 4BX; Batt 2026-11-11) ---------------------------
# Batt's bare-hand steal: on a new target the Rogue takes the dagger OFF (Alt+Q, a double-click on
# the equipment window's weapon slot, Alt+Q again), hits bare-handed (faster, weaker: the monster
# lives until Snatcher steals), and puts it back ON with its hotkey (F5) at the first steal cue
# (bare_steal.BareSteal: a new item popup or a new cyan Battle Log line; language-free), after
# BARE_MAX_S, under BARE_HP_MIN, when the target's fight ends, before any escape and at the run's
# end. The weapon state is READ, never assumed: the F5 slot draws the dagger only while it is in
# the bag (bare_steal.slot_bare against the armed reference cut at the run's start).
BARE_REF_WAIT_S = 3.0  # the run's start: the F5 slot must become readable within this
# --bare-ready (dungeon@9.27b, Batt 2026-11-11 after p65 / p66: "take the dagger off right away
# when the loot is collected, and wait; the next monster is hit bare-handed at once"): the unequip
# runs while IDLE (bare_idle + BareCtl.ready_tick), never at the strike, and a fight ending bare
# STAYS bare. p65 + p66 lost 40 % of the aims during the 1.9 s unequip at the strike (4BY).
BARE_READY_VERSION = "9.27b"
BARE_READY_SETTLE_S = BOX_SETTLE_S  # no world click this long before an idle unequip: a 7-cell
# walk (or a loot click's walk-up) has ended -- nothing in flight; the search walk HOLDS its next
# click meanwhile (ready_tick's "hold"), so the idle moment comes within this long of the loot
BARE_READY_RETRY_S = 5.0  # an idle unequip that did not end bare: no new one (and no hold) sooner


def bare_ready_refused(bare_steal: bool, ready: bool) -> str | None:
    """PURE: why --bare-ready cannot run (None: it can, or it is off). It changes WHEN
    --bare-steal's swap runs, so it is nothing without it."""
    if ready and not bare_steal:
        return "--bare-ready goes with --bare-steal (it moves the bare-steal unequip to idle time)"
    return None


def bare_idle(mode: str, locked: bool, sitting: bool, here_known: bool, since_fly: float,
              boss_avoid: bool, unread: bool) -> bool:  # fmt: skip
    """PURE (dungeon@9.27b): the main loop is IDLE for --bare-ready's unequip: searching (not in
    a fight, not before a pending loot step: the hook runs after the loot step and the rest
    decision, so "after" became "search"; not resting), no lock, not sitting, our position read
    (> 2 s after a Fly Wing: no teleport's dark frames), no boss guard's avoid window, no
    --unread-step escape. BareCtl.ready_tick adds: armed, no read-back pending, no target in hand,
    HP read and >= BARE_HP_MIN, no world click within BARE_READY_SETTLE_S; bare_unequip_seq adds
    its own reads (no window open, the window read open before its click)."""
    return (mode == "search" and not locked and not sitting and here_known and since_fly > 2.0
            and not boss_avoid and not unread)  # fmt: skip


def bare_steal_refused(char: str, steal: bool, keys: Mapping[str, str]) -> str | None:
    """PURE: why --bare-steal cannot run (None: it can). It is the ROGUE's (Snatcher, her auto
    steal); the active Steal opening (--steal) strikes with the dagger; the dagger's key must be
    bare_steal's EQUIP_KEY on EQUIP_SLOT (the hotbar slot the weapon readout reads)."""
    if char != "rogue":
        return f"--bare-steal is the Rogue's (Snatcher), not the {char}'s"
    if steal:
        return "--bare-steal does not go with --steal (its Steal opening strikes with the dagger)"
    key = keys.get("equip")
    if key != bs.EQUIP_KEY or hotbar_slot(key) != bs.EQUIP_SLOT:
        return f"the equip key {key!r} is not {bs.EQUIP_KEY} on hotbar slot {bs.EQUIP_SLOT}"
    return None


def heal_candy_refused(char: str, conf: Mapping[str, Any], keys: Mapping[str, str],
                       opener: str | None) -> str | None:  # fmt: skip
    """PURE (dungeon@9.31): why --heal-candy cannot run (None: it can). It needs the hotbar stock
    read (the Rogue's), and its F6 / F7 must not be another key of the run (the Knife opener's
    F4 / the dagger's F5 stay theirs)."""
    if char != "rogue" or not conf.get("hotbar_stock"):
        return f"--heal-candy reads the hotbar stock (the Rogue's), not the {char}'s"
    taken = {k: v for k, v in keys.items() if v in HEAL_CANDY_KEYS.values()}
    if opener in HEAL_CANDY_KEYS.values():
        taken["opener"] = opener
    if taken:
        return f"--heal-candy's keys {sorted(HEAL_CANDY_KEYS.values())} are taken: {taken}"
    return None


def bare_ref_cut(gray: Any) -> tuple[Any, dict[str, Any], str | None]:
    """PURE (the run's start): (the ARMED reference crop of the F5 slot, its record, a refusal).
    The slot must read EMPTY by hotbar_count's own rule (no icon, no digit): the dagger is worn.
    An icon there = the dagger is in the bag, or F5 holds another item: refused (never fight in
    an unknown weapon state). A dark crop = unreadable: (None, rec, None), the caller reads again.
    An empty F5 cannot tell "worn" from "nothing on F5": the first unequip's read-back (the slot
    must turn BARE after the double-click; else bare_fail_off, FAIL_STOP in a row stop) tells."""
    crop = bs.slot_crop(gray)
    rec: dict[str, Any] = {"empty": None, **bs.slot_stats(crop)}
    if rec["mean"] < bs.SLOT_DARK:
        return None, rec, None
    rec["empty"] = bs.slot_empty(gray)
    if not rec["empty"]:
        k_ = bs.EQUIP_KEY
        return None, rec, (f"the {k_} slot shows an icon: the dagger is in the bag (not worn) or "
                           f"{k_} holds another item -- a person first")  # fmt: skip
    return crop, rec, None


def steal_opener_refused(key: str | None, bare_steal: bool,
                         keys: Mapping[str, str]) -> str | None:  # fmt: skip
    """PURE (dungeon@9.27c): why --steal-opener KEY cannot run (None: it can, or it is off). It
    replaces --bare-steal's bare hands, so it needs --bare-steal; KEY is a row-1 hotbar key
    (F1-F9), never the dagger's (bare_steal.EQUIP_KEY) nor one the character already uses (the
    Rogue's F1 potion, F2 Fly Wing, F3 Steal)."""
    if key is None:
        return None
    if not bare_steal:
        return "--steal-opener goes with --bare-steal (the opener replaces its bare hands)"
    try:
        hotbar_slot(key)
    except ValueError:
        return f"--steal-opener {key!r} is not a row-1 hotbar key (F1-F9)"
    if key == bs.EQUIP_KEY:
        return f"--steal-opener {key}: that is the dagger's key ({bs.EQUIP_KEY})"
    used = sorted(w for w, k in keys.items() if k == key)
    if used:
        return f"--steal-opener {key}: the character already uses it ({', '.join(used)})"
    return None


def opener_ref_cut(gray: Any, key: str) -> tuple[Any, dict[str, Any], str | None]:
    """PURE (the run's start, --steal-opener): (slot ``key``'s "shows the opener" reference crop,
    its record, a refusal). The opener must sit in the BAG: its slot shows an icon and no count
    (equipment has none). EMPTY = the opener is worn, or nothing is on the key; a count = a stack,
    not a weapon: refused (a person first). A dark crop = unreadable: (None, rec, None)."""
    slot = hotbar_slot(key)
    crop = bs.slot_crop(gray, slot)
    rec: dict[str, Any] = {"key": key, "slot": slot, "empty": None, "counted": None,
                           **bs.slot_stats(crop)}  # fmt: skip
    if rec["mean"] < bs.SLOT_DARK:
        return None, rec, None
    rec["empty"], rec["counted"] = bs.slot_empty(gray, slot), bs.slot_counted(gray, slot)
    if rec["empty"]:
        return None, rec, (f"the {key} slot is EMPTY: the opener is worn (not in the bag) or "
                           f"{key} holds nothing -- a person first")  # fmt: skip
    if rec["counted"]:
        # live 2026-11-11 20:19 (ko0): this client draws "1" under ONE equipment item too (the
        # Knife on F4, the Damascus on F5 while in the bag): a count of exactly 1 is a weapon; a
        # count above 1 is a stack; an unreadable count refuses
        import hotbar_count as hb

        rec["count"] = hb.read_count(np.asarray(gray), slot, hb.load())
        if rec["count"] != 1:
            return None, rec, (f"the {key} slot draws a count {rec['count']}: a stack or "
                               "unreadable, not one weapon -- a person first")  # fmt: skip
    return crop, rec, None


def clear_bag_eqp_refused(gray: Any, keys: Mapping[str, str],
                          tabs: Sequence[str]) -> str | None:  # fmt: skip
    """PURE (dungeon@9.27c): clear-bag's Eqp tab must NEVER drop a weapon the runner swaps to.
    --steal-opener's opener (the Knife on F4) sits in the bag with its icon on a key that none of
    the character's own keys names; nothing tells clear-bag that an opener is configured, so it
    reads the hotbar itself: for a character with an equip key (the Rogue), clearing "eqp" is
    refused while any OTHER row-1 slot shows an icon or is unreadable -- a person passes --tabs
    without eqp (e.g. etc,use). No equip key or no eqp tab: None."""
    if "equip" not in keys or "eqp" not in tabs:
        return None
    own: set[int] = set()
    for k in keys.values():
        with contextlib.suppress(ValueError):
            own.add(hotbar_slot(k))
    for slot in range(9):
        if slot in own:
            continue
        key = f"F{slot + 1}"
        if float(bs.slot_crop(gray, slot).mean()) < bs.SLOT_DARK:
            return f"clear-bag refused: the {key} slot is unreadable (a weapon on it unknown)"
        if not bs.slot_empty(gray, slot):
            return (f"clear-bag refused: the {key} slot shows an item none of the {sorted(keys)} "
                    "keys names -- it may be the steal opener (a weapon) in the bag and the Eqp "
                    "tab would drop it; pass --tabs without eqp (e.g. etc,use)")  # fmt: skip
    return None


def clear_bag_bare_refused(gray: Any, keys: Mapping[str, str]) -> str | None:
    """PURE (dungeon@9.27): clear-bag drops EVERY inventory stack, so with the dagger in the bag
    (its key's hotbar slot shows its icon: the Rogue BARE) it would drop the dagger. Refused unless
    that slot reads EMPTY (worn); an unreadable slot is refused too. No equip key: None."""
    key = keys.get("equip")
    if key is None:
        return None
    slot = hotbar_slot(key)
    if float(bs.slot_crop(gray, slot).mean()) < bs.SLOT_DARK:
        return f"clear-bag refused: the {key} slot is unreadable (the dagger's state unknown)"
    if not bs.slot_empty(gray, slot):
        return (f"clear-bag refused: the {key} slot shows the dagger's icon -- it is in the bag "
                f"(bare) and clear-bag would drop it; put it on first ({key})")  # fmt: skip
    return None


def window_origin(frame: Any, reg: Any, name: str, home_px: int = 12) -> tuple[int, int] | None:
    """The window's origin (game-region px) when it shows within ``home_px`` (ui_gate.HOME_PX) of
    its home: ui_gate.home_distances' own match on the same small box, with the position kept.
    None when it does not match (the caller then aims from the home)."""
    from poring_env import ui_anchors as ua

    tmpl = reg.templates.get(name)
    if tmpl is None:
        return None
    spec = reg.windows[name]
    gray = ua.to_gray(np.asarray(frame))
    h, w = gray.shape
    ox, oy = spec.template_offset
    tx, ty = ua.CAPTURE_ORIGINS[name][0] + ox, ua.CAPTURE_ORIGINS[name][1] + oy
    th, tw = tmpl.shape
    x0, y0 = max(0, tx - home_px), max(0, ty - home_px)
    x1, y1 = min(w, tx + tw + home_px), min(h, ty + th + home_px)
    if x1 - x0 < tw or y1 - y0 < th:
        return None
    m = ua.match_template(gray[y0:y1, x0:x1], tmpl, reg.masks.get(name))
    if m is None or m.distance > spec.max_distance:
        return None
    return x0 + m.origin[0] - ox, y0 + m.origin[1] - oy


def ui_double_click(agent: Any, x: int, y: int, desktop: tuple[int, int],
                    ns: Callable[[], int], sleep: Callable[[float], None] = time.sleep,
                    ) -> None:  # fmt: skip
    """dungeon@9.27: a UI double-click at desktop px (x, y) -- two motions first (the client draws
    its cursor only where a SECOND motion leaves it; a cold-jump UI click is ignored:
    gm_state._tab), then the left button down / up twice, 40 ms apart, through agent.send:
    ro_agent.launch_client's double-click exactly (the parent's live check, 2026-11-11).
    test_click_census registers it (RAW_BUTTONS)."""
    agent.move(x + 3, y + 3)
    sleep(0.05)
    agent.move(x, y)
    sleep(0.1)
    w_d, h_d = desktop
    for action in ("down", "up", "down", "up"):
        agent.send([{"type": "mouse_button", "t_mono_ns": ns(), "frame_id": -1, "button": "left",
                     "action": action, "x": x / w_d, "y": y / h_d}])  # fmt: skip
        sleep(0.04)


@dataclass
class BareIo:
    """--bare-steal's I/O: the runner's own reads and inputs, injected (a test simulates them).
    ``chord``: agent.chord of the equipment window's keys (ui_gate.window_keys, a TOGGLE);
    ``double_click``: ui_double_click at a game-region point; ``press``: press("equip", why);
    ``guard``: guard_tick (the HP and the escapes inside a long action; True once we flew);
    ``opener``: --steal-opener's key press (dungeon@9.27c; None without it)."""

    frame: Callable[[], Any]  # a fresh game-region frame (BGR, the runner's frame())
    windows: Callable[[Any], list[str]]  # ui_gate.windows_at_home on that frame
    origin: Callable[[Any], tuple[int, int] | None]  # the equipment window's origin, or None
    chord: Callable[[], None]
    double_click: Callable[[int, int], None]
    press: Callable[[str], None]
    lines: Callable[[], Sequence[Mapping[str, Any]]]  # the Battle Log's lines (a snapshot)
    guard: Callable[[], bool] = lambda: False
    sleep: Callable[[float], None] = time.sleep
    clock: Callable[[], float] = time.monotonic
    opener: Callable[[str], None] | None = None


@dataclass
class OpenerRead:
    """--steal-opener's weapon readout (dungeon@9.27c): the F5 slot against its EMPTY reference
    (the dagger worn; bare_ref_cut's) and the opener's slot against its "shows the opener"
    reference (in the bag; opener_ref_cut's), both cut at the run's start. ``state``:
    bare_steal.weapon_state's "armed" / "opener" / "bare" / "odd" / None."""

    key: str
    ref5: Any  # F5 EMPTY: the dagger worn
    refk: Any  # the opener's slot showing the opener: in the bag

    @property
    def slot(self) -> int:
        return hotbar_slot(self.key)

    def state(self, frame: Any) -> str | None:
        g = bs.slot_gray(frame)
        return bs.weapon_state(bs.slot_bare(bs.slot_crop(g), self.ref5),
                               bs.opener_worn(g, self.slot, self.refk))  # fmt: skip

    def stats(self, frame: Any) -> dict[str, Any]:
        return bs.slot_stats(bs.slot_crop(bs.slot_gray(frame), self.slot), self.refk)


def bare_read(frame: Any, ref: Any) -> bool | None:
    """PURE: the F5 slot on ``frame``: True = bare (the dagger in the bag), False = armed, None =
    unreadable."""
    return bs.slot_bare(bs.slot_crop(bs.slot_gray(frame)), ref)


def bare_poll(io: BareIo, cond: Callable[[Any], bool], limit_s: float, *,
              guard: bool = False) -> tuple[bool, Any, bool]:  # fmt: skip
    """Fresh frames every POLL_S until ``cond(frame)`` or ``limit_s``: (met, the last frame,
    escaped). ``guard``: io.guard() on every poll (the sustain rules keep running inside a swap);
    True from it (we flew away) ends the poll."""
    t0 = io.clock()
    while True:
        f = io.frame()
        if cond(f):
            return True, f, False
        if guard and io.guard():
            return False, f, True
        if io.clock() - t0 >= limit_s:
            return False, f, False
        io.sleep(bs.POLL_S)


def bare_unequip_seq(io: BareIo, ref: Any) -> dict[str, Any]:
    """The UNEQUIP, Batt's way, every step read back: (a) no window open, else nothing (skip_ui);
    (b) the chord, then the equipment window must read OPEN within OPEN_S (else fail_open: one
    that opens within LATE_S more is closed by ONE more chord and read closed); (c) the
    double-click on the weapon slot, offset from where the window was found (its home when the
    locate fails), ONLY after the window read open; (d) the F5 slot must read BARE within OFF_S
    (else fail_off); (e) the chord again: no window may read open within CLOSE_S, else ONE more
    chord while it is still the equipment window, and read again; still open -> ``stop`` (never
    fight with it open). ``bare`` is the slot's LAST READABLE state (the truth kept); ``frame``
    the last frame read."""
    t0 = io.clock()
    out: dict[str, Any] = {"ok": False, "why": None, "fail": None, "stop": None, "bare": False,
                           "escaped": False, "chords": 0, "at": None, "origin": None}  # fmt: skip

    def eq_open(f_: Any) -> bool:
        return bs.EQUIP_WINDOW in io.windows(f_)

    def none_open(f_: Any) -> bool:
        return not io.windows(f_)

    def close() -> Any:
        io.chord()
        out["chords"] += 1
        ok_, f_, _e = bare_poll(io, none_open, bs.CLOSE_S)
        if not ok_ and eq_open(f_):  # ONE more chord, only for the equipment window itself
            io.chord()
            out["chords"] += 1
            ok_, f_, _e = bare_poll(io, none_open, bs.CLOSE_S)
        if not ok_:
            out["stop"] = (f"a window reads open after the closing chord(s): {io.windows(f_)} "
                           f"({out['chords']} chords)")  # fmt: skip
        return f_

    def done(f_: Any) -> dict[str, Any]:
        b_ = out["read"] = bare_read(f_, ref)
        if b_ is not None:
            out["bare"] = b_
        out["frame"], out["ms"] = f_, round((io.clock() - t0) * 1e3)
        out["slot"] = bs.slot_stats(bs.slot_crop(bs.slot_gray(f_)), ref)
        return out

    f = io.frame()
    open0 = io.windows(f)
    if open0:  # (a) never a chord into an unknown UI: the strike goes on armed
        out.update(why="ui_open", fail="bare_skip_ui", windows=open0)
        return done(f)
    io.chord()  # (b)
    out["chords"] += 1
    opened, f, esc = bare_poll(io, eq_open, bs.OPEN_S, guard=True)
    out["escaped"] = esc
    if not opened:
        out.update(why="escaped" if esc else "not_open", fail=None if esc else "bare_fail_open")
        late, f, _e = bare_poll(io, eq_open, bs.LATE_S)  # the re-read: a LATE one is closed again
        if late:
            out["late"] = True
            f = close()
        elif io.windows(f):
            out["stop"] = f"another window reads open after the chord: {io.windows(f)}"
        return done(f)
    org = io.origin(f)  # (c) where the window really is
    out["origin"] = None if org is None else [int(org[0]), int(org[1])]
    ox, oy = org if org is not None else bs.EQUIP_HOME
    x, y = int(ox) + bs.WEAPON_SLOT[0], int(oy) + bs.WEAPON_SLOT[1]
    out["at"] = [x, y]
    io.double_click(x, y)
    off, f, esc = bare_poll(io, lambda f_: bare_read(f_, ref) is True, bs.OFF_S, guard=True)  # (d)
    out["escaped"] = esc
    f = close()  # (e) always, read closed
    done(f)
    if out["read"] is None and off:
        out["bare"] = True  # the closed frame unreadable: the read-back under the window stands
    if out["bare"]:
        out.update(ok=True, why="off" if off else "late_off")
    else:
        out.update(why="escaped" if esc else "not_off", fail=None if esc else "bare_fail_off")
    return out


def bare_state(frame: Any, ref: Any) -> str | None:
    """PURE: the bare-hands readout as a state: "armed" / "bare" (the dagger in the bag) / None."""
    b = bare_read(frame, ref)
    return None if b is None else ("bare" if b else "armed")


def bare_equip_seq(io: BareIo, ref: Any, why: str, *, press: bool = True,
                   opener: OpenerRead | None = None) -> dict[str, Any]:  # fmt: skip
    """The EQUIP: the dagger's hotkey, then the F5 slot must read ARMED within ON_S; a READABLE
    bare read then -> ONE more press and ON_S again. ok: True (armed) / False (still bare) / None
    (no readable frame: a teleport's dark frames -- read again later, never a failure).
    ``press`` False: the read-back alone (after a key-only equip before an escape).
    ``opener`` (--steal-opener): ARMED = F5 empty AND the opener's slot shows the opener again
    (OpenerRead.state "armed"); the second press only while F5 still shows the dagger (readable:
    "opener" / "bare"), never on an unreadable or "odd" read. F5 read empty at the end while the
    opener's slot did not read its icon -> ok all the same (the dagger IS worn: F5 is never
    pressed onto it again), with ``opener_back`` False (counted: bare_opener_back_miss)."""
    t0 = io.clock()
    n = 0
    if press:
        io.press(why)
        n += 1

    def state(f_: Any) -> str | None:
        return bare_state(f_, ref) if opener is None else opener.state(f_)

    def armed(f_: Any) -> bool:
        return state(f_) == "armed"

    ok, f, _e = bare_poll(io, armed, bs.ON_S)
    if not ok and state(f) in ("bare", "opener"):
        io.press(why)
        n += 1
        ok, f, _e = bare_poll(io, armed, bs.ON_S)
    b = state(f)
    if not ok and opener is not None and bare_read(f, ref) is False:
        ok = True  # the dagger worn (F5 empty); the opener's icon not read back (opener_back)
    return {"ok": True if ok else (None if b is None else False), "presses": n,
            "ms": round((io.clock() - t0) * 1e3),
            "slot": bs.slot_stats(bs.slot_crop(bs.slot_gray(f)), ref),
            **({"state": b, "opener_back": b == "armed", "opener_slot": opener.stats(f)}
               if opener is not None else {})}  # fmt: skip


def opener_seq(io: BareIo, opener: OpenerRead, why: str) -> dict[str, Any]:
    """--steal-opener's "unequip" (dungeon@9.27c): the opener's KEY (no Alt+Q, no window, no
    click), then the state must read "opener" (its slot EMPTY: worn; F5 shows the dagger: in the
    bag) within ON_S; a READABLE read with the opener still in the bag ("armed" / "bare") -> ONE
    more press and ON_S again. ok: True / False / None (unreadable). ``bare``: the dagger read in
    the bag on the last readable frame (the truth the runner keeps, as bare_unequip_seq's)."""
    assert io.opener is not None
    t0 = io.clock()
    io.opener(why)
    n = 1
    last: list[str | None] = [None]

    def on(f_: Any) -> bool:
        s_ = opener.state(f_)
        if s_ is not None:
            last[0] = s_
        return s_ == "opener"

    ok, f, _e = bare_poll(io, on, bs.ON_S)
    if not ok and opener.state(f) in ("armed", "bare"):
        io.opener(why)
        n += 1
        ok, f, _e = bare_poll(io, on, bs.ON_S)
    s = opener.state(f)
    return {"ok": True if ok else (None if s is None else False), "presses": n,
            "ms": round((io.clock() - t0) * 1e3), "state": s, "frame": f,
            "bare": last[0] in ("opener", "bare"),
            "slot": bs.slot_stats(bs.slot_crop(bs.slot_gray(f)), opener.ref5),
            "opener_slot": opener.stats(f)}  # fmt: skip


class BareCtl:
    """--bare-steal's runner side (dungeon@9.27): bare_steal.BareSteal's phase, the swaps through
    BareIo, the counters (bare_unequip, bare_equip_<why>, bare_skip_ui / _hp, bare_aim_lost,
    bare_fail_open / _off / _on) and one "bare" event per swap. A TARGET is one engagement: it
    begins at a strike with no lock held (before_strike) and ends when its lock goes (a kill, an
    unlock) or the fight ends (tick); each target gets ONE bare phase. ``stop``: the exception
    that stops the run (r.Stop).

    ``ready`` (--bare-ready, dungeon@9.27b): the unequip runs while IDLE (ready_tick: counters
    bare_ready / bare_ready_fail), a new target struck while bare starts its phase there with no
    swap (_begin: bare_ready_strike), and a target's end while bare STAYS bare (no "fight_end"
    equip; BareSteal.wait_bare). Every other equip (the cues, BARE_MAX_S, BARE_HP_MIN, escape,
    run_end) is unchanged. Off: exactly 9.27.

    ``opener`` (--steal-opener, dungeon@9.27c): the "unequip" is the opener's KEY (opener_seq:
    no Alt+Q, no window, no click; counters bare_opener / bare_opener_fail), read back as the
    opener worn AND the dagger in the bag; every equip stays F5, read back as the dagger worn AND
    the opener in the bag (bare_equip_seq's ``opener``). "Bare" below means the dagger is OFF."""

    def __init__(self, io: BareIo, ref: Any, counts: Counter[str],
                 ev: Callable[[dict[str, Any]], None],
                 stop: type[Exception] = RuntimeError, *, ready: bool = False,
                 opener: OpenerRead | None = None, cue: str = "both") -> None:  # fmt: skip
        self.io, self.ref, self.counts, self.ev, self.stop = io, ref, counts, ev, stop
        self.opener = opener
        self.st = bs.BareSteal(cue=cue)  # 9.27d: --steal-cue
        self.tgt: dict[str, Any] | None = None
        self.pending: str | None = None  # a key-only equip (escape) awaiting its read-back
        self.fails = 0  # failed swaps in a row (FAIL_STOP)
        self.busy = False  # inside a swap: a Fly Wing pressed by guard_tick needs no hook
        self.ready = ready
        self.ready_next = -1e9  # --bare-ready: no idle unequip before this (after a failed one)
        # dungeon@9.27e (--swap-gap): when the last swap (equip / unequip / opener) ENDED -- our
        # hits pause through a swap, so the no-hit clocks restart there (Batt's 22:53 clip, p71)
        self.swap_t = -1e9

    def state_of(self, frame: Any) -> str | None:
        """The weapon state READ on ``frame``: "armed" / "bare" / None (unreadable); with the
        opener OpenerRead.state ("opener" too, and "odd")."""
        return bare_state(frame, self.ref) if self.opener is None else self.opener.state(frame)

    def _failed(self, key: str) -> None:
        self.counts[key] += 1
        self.fails += 1
        if self.fails >= bs.FAIL_STOP:
            raise self.stop(f"--bare-steal: {self.fails} swaps in a row failed (the last: {key}): "
                            "the weapon state is not what the readout expects")  # fmt: skip

    def _equip_done(self, why: str, res: Mapping[str, Any], verify: bool = False) -> None:
        self.ev({"kind": "bare", "what": "equip", "why": why, "ok": res["ok"], "ms": res["ms"],
                 "presses": res["presses"], "slot": res["slot"],
                 **({"state": res["state"], "opener_back": res["opener_back"],
                     "opener_slot": res["opener_slot"]} if "opener_slot" in res else {}),
                 **({"verify": True} if verify else {})})  # fmt: skip
        if res["ok"]:
            self.st.equipped()
            self.pending, self.fails = None, 0
            self.counts[f"bare_equip_{why}"] += 1
            if res.get("opener_back") is False:  # --steal-opener: F5 empty, the icon not back
                self.counts["bare_opener_back_miss"] += 1
        elif res["ok"] is None:
            self.pending = why  # unreadable (dark frames): read again on the next tick
        else:
            self.pending = None
            self._failed("bare_fail_on")

    def equip(self, why: str) -> bool | None:
        """The dagger back on, read back (bare_equip_seq); a no-op while armed."""
        if self.st.armed:
            return True
        self.busy = True
        try:
            res = bare_equip_seq(self.io, self.ref, why, opener=self.opener)
        finally:
            self.busy = False
            self.swap_t = self.io.clock()  # 9.27e: a swap pauses our hit lines
        self._equip_done(why, res)
        return res["ok"]

    def _verify(self) -> None:
        why = self.pending or "safety"
        self.busy = True
        try:
            res = bare_equip_seq(self.io, self.ref, why, press=False, opener=self.opener)
        finally:
            self.busy = False
            self.swap_t = self.io.clock()  # 9.27e: a swap pauses our hit lines
        self._equip_done(why, res, verify=True)

    def escape(self) -> None:
        """Before a Fly Wing or a walk-away while BARE: the equip key at once ("safety"), its
        read-back on the next tick -- the escape is never delayed for a read."""
        if self.st.armed or self.busy or self.pending is not None:
            return
        self.io.press("safety")
        self.pending = "safety"
        self.swap_t = self.io.clock()  # 9.27e
        self.ev({"kind": "bare", "what": "equip", "why": "safety", "ok": None, "ms": 0,
                 "presses": 1, "pending": True})  # fmt: skip

    def unequip(self, by: str, idle: bool = False) -> bool:
        """bare_unequip_seq; the phase starts only when the slot READ bare (BareSteal.unequipped
        with the Battle Log's line count and the popup shown NOW, so neither is a cue). True: bare
        and still here (no escape inside). ``idle`` (--bare-ready): bare with NO phase
        (BareSteal.wait_bare): the next target's first strike begins it. With the opener:
        _opener_on (its key, never the window)."""
        if self.opener is not None:
            return self._opener_on(by, idle)
        self.busy = True
        try:
            res = bare_unequip_seq(self.io, self.ref)
        finally:
            self.busy = False
            self.swap_t = self.io.clock()  # 9.27e: a swap pauses our hit lines
        if res["bare"]:
            if idle:
                self.st.wait_bare()
            else:
                rgb = np.asarray(res["frame"])[: bs.POPUP_BOTTOM + 1, :, ::-1]
                box = bs.popup_box(rgb)
                sig = None if box is None else bs.popup_sig(rgb)
                self.st.unequipped(self.io.clock(), len(self.io.lines()), sig, box)
            self.counts["bare_unequip"] += 1
            if self.tgt is not None:
                self.tgt["phase"] = True
        self.ev({"kind": "bare", "what": "unequip", "ok": res["ok"], "ms": res["ms"],
                 "why": res["why"], "by": by, "chords": res["chords"], "at": res["at"],
                 "origin": res["origin"], "slot": res["slot"], "escaped": res["escaped"],
                 **({"windows": res["windows"]} if "windows" in res else {}),
                 **({"stop": res["stop"]} if res["stop"] else {})})  # fmt: skip
        if res["stop"] is not None:
            raise self.stop(f"--bare-steal: {res['stop']}")
        if res["fail"] == "bare_skip_ui":
            self.counts["bare_skip_ui"] += 1
        elif res["fail"] is not None:
            self._failed(res["fail"])
        elif res["ok"]:
            self.fails = 0
        if res["escaped"] and not self.st.armed:
            self.escape()  # we flew away bare (guard_tick inside the swap): the dagger at once
        return bool(res["ok"]) and not res["escaped"]

    def _opener_on(self, by: str, idle: bool) -> bool:
        """--steal-opener's swap (opener_seq): the phase starts (or, ``idle``, she waits with the
        opener on: wait_bare) when the dagger READ in the bag, as bare_unequip_seq's ``bare``;
        ok = the opener read worn too (else bare_opener_fail, FAIL_STOP in a row stop). True: the
        opener on."""
        assert self.opener is not None
        self.busy = True
        try:
            res = opener_seq(self.io, self.opener, by)
        finally:
            self.busy = False
            self.swap_t = self.io.clock()  # 9.27e: a swap pauses our hit lines
        if res["bare"]:
            if idle:
                self.st.wait_bare()
            else:
                rgb = np.asarray(res["frame"])[: bs.POPUP_BOTTOM + 1, :, ::-1]
                box = bs.popup_box(rgb)
                sig = None if box is None else bs.popup_sig(rgb)
                self.st.unequipped(self.io.clock(), len(self.io.lines()), sig, box)
            if self.tgt is not None:
                self.tgt["phase"] = True
        self.ev({"kind": "bare", "what": "opener", "ok": res["ok"], "ms": res["ms"], "by": by,
                 "presses": res["presses"], "state": res["state"], "slot": res["slot"],
                 "opener_slot": res["opener_slot"]})  # fmt: skip
        if res["ok"]:
            self.counts["bare_opener"] += 1
            self.fails = 0
            return True
        self._failed("bare_opener_fail")
        return False

    def _end(self) -> None:
        """The target's engagement is over: bare -> the dagger back on at once ("fight_end");
        the next target's phase is a new one (BareSteal.fight_end). --bare-ready: bare STAYS
        bare (its phase ends; she waits bare for the next monster)."""
        if not self.st.armed and self.pending is None:
            if self.ready:
                self.st.wait_bare()
                self.counts["bare_ready_wait"] += 1
                self.ev({"kind": "bare", "what": "wait", "why": "target_end"})
            else:
                self.equip("fight_end")
        self.st.fight_end()
        self.tgt = None

    def ready_tick(self, now: float, idle: bool, settled: bool,
                   hp: float | None) -> str | None:  # fmt: skip
        """--bare-ready's idle unequip (dungeon@9.27b): None = nothing due; "hold" = due but a
        world click may still be in flight (``settled`` False: the caller holds its next walk
        click); "swap" = bare_unequip_seq ran (its reads and safety, as at a strike), whatever
        its result. Due = ``ready``, ``idle`` (bare_idle), ARMED, no read-back pending, no swap
        running, no target in hand, not within BARE_READY_RETRY_S of a failed one, the HP read
        and >= BARE_HP_MIN. Never inside a fight."""
        if not (self.ready and idle and self.st.armed and self.pending is None
                and not self.busy and self.tgt is None and now >= self.ready_next
                and hp is not None and hp >= bs.BARE_HP_MIN):  # fmt: skip
            return None
        if not settled:
            return "hold"
        ok = self.unequip("ready", idle=True) and not self.st.armed
        self.counts["bare_ready" if ok else "bare_ready_fail"] += 1
        if not ok:
            self.ready_next = self.io.clock() + BARE_READY_RETRY_S
        return "swap"

    def _begin(self, by: str) -> bool:
        """--bare-ready: a new target's first strike while the dagger is already OFF -- no swap;
        its phase starts HERE (BareSteal.begin: BARE_MAX_S, the Battle Log's line count and the
        popup shown now). The state is READ on a fresh frame first: ARMED after all -> False (the
        caller swaps as without --bare-ready); unreadable -> the last read (bare) stands."""
        f = self.io.frame()
        s = self.state_of(f)
        if s == "armed":
            self.st.equipped()
            self.counts["bare_ready_lost"] += 1
            self.ev({"kind": "bare", "what": "begin", "ok": False, "by": by, "state": s})
            return False
        rgb = np.asarray(f)[: bs.POPUP_BOTTOM + 1, :, ::-1]
        box = bs.popup_box(rgb)
        sig = None if box is None else bs.popup_sig(rgb)
        self.st.begin(self.io.clock(), len(self.io.lines()), sig, box)
        if self.tgt is not None:
            self.tgt["phase"] = True
        self.counts["bare_ready_strike"] += 1
        self.ev({"kind": "bare", "what": "begin", "ok": True, "by": by, "state": s})
        return True

    def before_strike(self, by: str, hp: float | None, aim: Callable[[], bool] | None) -> bool:
        """strike()'s FIRST step (strikes are made with no lock held): the previous target is over
        if its lock went (_end); a new target's first strike, armed, UNEQUIPS; then ``aim`` reads
        the strike point again -- the swap takes ~2 s and the target may have walked: no SWORD
        there -> no click (False, bare_aim_lost; the fight loop's scan finds it again, bare). A
        plant is struck as it is; under BARE_HP_MIN nothing comes off (bare_skip_hp).
        --bare-ready: already bare (the idle unequip) -> NO swap, the phase begins at this strike
        (_begin); under BARE_HP_MIN the dagger goes on first ("hp"); read armed after all -> the
        swap below, as without it."""
        if by == "plant":
            return True
        if self.pending is not None:
            self._verify()
        if self.tgt is not None and self.tgt["locked"]:
            self._end()
        if self.tgt is None:
            self.tgt = {"t": self.io.clock(), "by": by, "locked": False, "phase": False}
        if self.tgt["phase"] or self.pending is not None:
            return True
        if self.ready and not self.st.armed and self.st.t_bare is None:
            if hp is not None and hp < bs.BARE_HP_MIN:
                self.equip("hp")  # never a bare strike under BARE_HP_MIN: armed, as it is
                return True
            if self._begin(by):
                return True  # bare already: struck at once (the point of --bare-ready)
        if self.st.engage() != "unequip":
            return True
        if hp is not None and hp < bs.BARE_HP_MIN:
            self.counts["bare_skip_hp"] += 1
            return True
        if not self.unequip(by):
            return True  # armed (skipped / failed: the strike goes on with the dagger) or flown
        if aim is not None and not aim():
            self.counts["bare_aim_lost"] += 1
            self.ev({"kind": "bare", "what": "aim", "ok": False, "by": by})
            return False
        return True

    def struck(self) -> None:
        """strike() returned True: the caller holds a lock on this target now."""
        if self.tgt is not None:
            self.tgt["locked"] = True

    def tick(self, now: float, locked: bool, fighting: bool, frame: Any,
             hp: float | None) -> None:  # fmt: skip
        """Every main-loop tick, before the fight branch: a pending read-back first; the target's
        end (its lock went, or the fight ended) -> _end; bare outside a fight -> the dagger on
        (the safety net); bare in a fight -> BareSteal.tick's cues (equip at the first).
        --bare-ready: bare with no phase (waiting for a target) -> only BARE_HP_MIN puts the
        dagger on ("hp"); bare outside a fight STAYS bare (the phase, if any, ends)."""
        if self.pending is not None:
            self._verify()
            if self.pending is not None:
                return  # still unreadable: read again on the next tick
        if self.tgt is not None:
            if locked:
                self.tgt["locked"] = True
            elif self.tgt["locked"] or not fighting:
                self._end()
                return
        if self.st.armed:
            return
        if self.ready and self.st.t_bare is None:  # 9.27b: waiting bare (no target struck yet)
            if hp is not None and hp < bs.BARE_HP_MIN:
                self.equip("hp")
            return
        if not fighting:
            if self.ready:  # 9.27b: no "fight_end" equip -- she waits bare for the next monster
                self.st.wait_bare()
                return
            self.equip("fight_end")
            return
        rgb = np.asarray(frame)[: bs.POPUP_BOTTOM + 1, :, ::-1]  # the popup's rows, as RGB
        do, why = self.st.tick(now, self.io.lines(), rgb, hp)
        if do == "equip" and why is not None:
            self.equip(why)

    def run_end(self, dead: bool = False) -> dict[str, Any]:
        """ALWAYS before the run ends: bare -> the dagger back on ("run_end"), read back; the
        final state for run_end's record. Dead: nothing is pressed (the caller retries after
        @alive)."""
        if not dead:
            if self.pending is not None:
                self._verify()
            if not self.st.armed:
                self.equip("run_end")
        f = self.io.frame()
        b = bare_read(f, self.ref)
        return {"armed": self.st.armed, "slot": None if b is None else ("bare" if b else "armed"),
                "dead": dead, "pending": self.pending, "fails": self.fails,
                **({"state": self.opener.state(f)} if self.opener is not None else {})}  # fmt: skip


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
    player = bool(getattr(a, "player_mode", False))  # dungeon@9.35 (docs/planning/player-mode.md)
    why_pm = player_mode_refused(a)  # before any input: the flags that type GM lines
    if why_pm:
        raise SystemExit(f"dungeon@{PLAYER_MODE_VERSION} refused: {why_pm}")
    why_qs = quick_scaled_refused(a)  # dungeon@9.38: before any input
    if why_qs:
        raise SystemExit(f"dungeon@{QUICK_SCALED_VERSION} refused: {why_qs}")
    bosses: tuple[str, ...] = ()  # --engage-screen's boss guard (Amendment J)
    map_species: tuple[str, ...] = ()
    if getattr(a, "engage_screen", False):
        kb_b = ROOT / "data" / "kb"
        sp_doc = json.loads((kb_b / "spawns.json").read_text())
        bosses = boss_names(map_, sp_doc, json.loads((kb_b / "mobs.json").read_text()),
                            json.loads((kb_b / "mob_skills.json").read_text()))  # fmt: skip
        map_species = tuple(sorted({str(e.get("name")) for e in sp_doc.get(map_, [])
                                    if str(e.get("name")) not in bosses}))  # fmt: skip
    boss_until = -1e9
    boss_only: tuple[str, ...] = ()  # dungeon@9.18: the boss itself (no walk-away)
    if bosses:
        boss_only = boss_spawn_names(map_, sp_doc, json.loads((kb_b / "mobs.json").read_text()))
    reach_grid: Any = None  # dungeon@9.12: the server's walkability for --reach-check
    if getattr(a, "reach_check", False):
        from poring_dataset import walkable as wk_r

        try:
            reach_grid = wk_r.server_grid(map_)
        except LookupError as e:  # MapSourceError: walkability unknown -> refuse, never guess
            raise SystemExit(f"dungeon@9.12 refused: --reach-check: {e}") from None
    step_grid: Any = None  # dungeon@9.15c: the server's walkability for --walk-pick-step
    if getattr(a, "walk_pick_step", False):
        if not getattr(a, "walk_pick", False):
            raise SystemExit("dungeon@9.15c refused: --walk-pick-step goes with --walk-pick")
        from poring_dataset import walkable as wk_s

        try:
            step_grid = wk_s.server_grid(map_)
        except LookupError as e:  # walkability unknown -> refuse, never guess
            raise SystemExit(f"dungeon@9.15c refused: --walk-pick-step: {e}") from None
    walk_grid: Any = None  # dungeon@9.18: the server's walkability for --boss-walk
    if getattr(a, "boss_walk", False):
        if not getattr(a, "engage_screen", False):
            raise SystemExit("dungeon@9.18 refused: --boss-walk goes with --engage-screen")
        walk_grid = reach_grid if reach_grid is not None else step_grid
        if walk_grid is None:
            from poring_dataset import walkable as wk_w

            try:
                walk_grid = wk_w.server_grid(map_)
            except LookupError as e:  # walkability unknown -> refuse, never guess
                raise SystemExit(f"dungeon@9.18 refused: --boss-walk: {e}") from None
    if getattr(a, "unreach_escape", False):  # dungeon@9.26: never silently the base run
        why_ua = unreach_refused(getattr(a, "reach_check", False),
                                 getattr(a, "engage_screen", False))  # fmt: skip
        if why_ua:
            raise SystemExit(f"dungeon@9.26 refused: {why_ua}")
    if a.steal and ("steal" not in keys_ or not conf.get("max_sp")):
        raise SystemExit(f"dungeon@7 refused: --steal for the {a.char}, who has no Steal key / SP")
    bare_on = bool(getattr(a, "bare_steal", False))  # dungeon@9.27 (rogue-xmas02.md 4BX)
    if bare_on:
        why_bs = bare_steal_refused(a.char, a.steal, keys_)
        if why_bs:
            raise SystemExit(f"dungeon@9.27 refused: {why_bs}")
    hf_ = getattr(a, "hud_fast", None)  # dungeon@9.29b
    if hf_ is not None and (not getattr(a, "hud", False) or not 0.1 <= hf_ < BOX_EVERY_S):
        raise SystemExit(f"dungeon@9.29b refused: --hud-fast {hf_} goes with --hud, "
                         f"0.1 <= S < {BOX_EVERY_S}")  # fmt: skip
    vt_values: dict[str, float] | None = None  # dungeon@9.28 (--value-target, 4CB)
    if getattr(a, "value_target", False):
        import value_target as vt_mod

        vt_values = vt_mod.species_values(a.map) or None
        if not vt_values:
            raise SystemExit(
                f"dungeon@9.28 refused: no species values for {a.map} "
                "(econ_model.py build MAP first: data/econ/maps.json)"
            )
    bare_ready_on = bool(getattr(a, "bare_ready", False))  # dungeon@9.27b (after 4BY)
    why_bry = bare_ready_refused(bare_on, bare_ready_on)
    if why_bry:
        raise SystemExit(f"dungeon@9.27b refused: {why_bry}")
    opener_key: str | None = getattr(a, "steal_opener", None)  # dungeon@9.27c (the Knife on F4)
    why_so = steal_opener_refused(opener_key, bare_on, keys_)
    if why_so:
        raise SystemExit(f"dungeon@9.27c refused: {why_so}")
    if getattr(a, "loot_items", None) and a.loot != "trim":  # dungeon@9.33
        raise SystemExit("dungeon@9.33 refused: --loot-items goes with --loot trim")
    loot_aim = bool(getattr(a, "loot_aim", False))  # dungeon@9.32 (Study S-IDLE)
    if loot_aim and (a.loot != "trim" or not a.box_strike):
        raise SystemExit("dungeon@9.32 refused: --loot-aim goes with --loot trim and --box-strike")
    kill_aim: dict[float, Cell] = {}  # 9.32: a kill's time -> the aimed cell (absolute)
    rk_on = bool(getattr(a, "loot_recheck", False))  # dungeon@9.36 (rogue-xmas02.md 4DA)
    why_rk = loot_recheck_refused(rk_on, getattr(a, "loot_items", None))
    if why_rk:
        raise SystemExit(f"dungeon@{LOOT_RECHECK_VERSION} refused: {why_rk}")
    rk_pending: list[PendingKill] = []  # 9.36: the kills whose cells wait for a late drop
    rk_st: dict[str, float] = {"last": -1e9}  # 9.36: the last item detection (recheck / loot step)
    lm_on = bool(getattr(a, "loot_memory", False))  # dungeon@9.37 (rogue-xmas02.md 4DB)
    why_lm = loot_memory_refused(lm_on, getattr(a, "loot_items", None))
    if why_lm:
        raise SystemExit(f"dungeon@{LOOT_MEMORY_VERSION} refused: {why_lm}")
    lm_kills: list[PendingKill] = []  # 9.37: the young kills the item model looks at (MEMORY_S)
    lm_mem: dict[Cell, Remembered] = {}  # 9.37: the remembered item cells (MEMORY_KEEP_S)
    lm_st: dict[str, float] = {"last": -1e9}  # 9.37: the last look (or the loot step's detection)
    swap_gap = bool(getattr(a, "swap_gap", False))  # dungeon@9.27e (Batt's 22:53 clip)
    if swap_gap and not bare_on:
        raise SystemExit("dungeon@9.27e refused: --swap-gap goes with --bare-steal")
    heal_candy = bool(getattr(a, "heal_candy", False))  # dungeon@9.31 (Batt: candies, no potions)
    if heal_candy:
        why_hc = heal_candy_refused(a.char, conf, keys_, opener_key)
        if why_hc:
            raise SystemExit(f"dungeon@9.31 refused: {why_hc}")
        keys_ = {**keys_, **HEAL_CANDY_KEYS}
    stock_items = {**STOCK_ITEMS, **(HEAL_CANDY_ITEMS if heal_candy else {})}  # 9.31
    why_hk = player_home_refused(a, conf, keys_, opener_key)  # dungeon@9.35b: before any input
    if why_hk:
        raise SystemExit(f"dungeon@{PLAYER_HOME_VERSION} refused: {why_hk}")
    home_key: str | None = None  # dungeon@9.35b: the Butterfly Wing's key (--player-mode only)
    if player:
        home_key = getattr(a, "player_home_key", None) or conf.get("home_key")
        if home_key is not None:  # press("home") at the end; the lab's keys stay as they were
            keys_ = {**keys_, "home": home_key}
    heal_left: dict[int, int | None] = {}  # 9.31: the heal items' last hotbar reads
    why_box = box_flags_refused(a.box_strike, a.box_now, a.box_detector)
    if why_box:
        raise SystemExit(f"dungeon@8.9 refused: {why_box}")
    q_on = bool(getattr(a, "queue", False))  # dungeon@9.30 (--queue, rogue-xmas02.md 4CC)
    why_q = queue_refused(q_on, a.box_strike, a.boxes, a.engage == "melee_ring")
    if why_q:
        raise SystemExit(f"dungeon@9.30 refused: {why_q}")
    if getattr(a, "still_target", False):  # dungeon@9.23 (LS-2): never silently the base run
        why_st = still_target_refused(a.box_strike, a.box_now,
                                      getattr(a, "still_strike", False),
                                      getattr(a, "lead_strike", False))  # fmt: skip
        if why_st:
            raise SystemExit(f"dungeon@9.23 refused: {why_st}")
    if getattr(a, "near_single_still", False) and getattr(a, "near_single", False):
        raise SystemExit("dungeon@9.25b refused: --near-single-still replaces --near-single "
                         "(R2b keeps the still-scene re-click R2 drops)")  # fmt: skip
    if getattr(a, "near_single", False) and not getattr(a, "far_single", False):
        raise SystemExit("dungeon@9.25 refused: --near-single needs --far-single (it moves its "
                         "one-click rule from 4 cells to 2)")  # fmt: skip
    if getattr(a, "lead_press", False):  # dungeon@9.24 (LS-1): never silently LS-2 alone
        why_lp = lead_press_refused(getattr(a, "still_target", False),
                                    getattr(a, "lead_strike", False))  # fmt: skip
        if why_lp:
            raise SystemExit(f"dungeon@9.24 refused: {why_lp}")
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
    unread_forbid: Any = None  # dungeon@9.22 (--unread-step): the keep-outs a step stays far from
    unread_npcs: list[Cell] = []
    if getattr(a, "unread_step", False):
        unread_forbid = mz.no_enter_mask(zones, ok.shape) | mz.no_cross_mask(zones, ok.shape)
        try:  # fail closed: an NPC the KB does not know could not be kept away from
            unread_npcs = trust_npcs_for(map_)
        except SystemExit as e:
            raise SystemExit(f"dungeon@9.22 refused: --unread-step: {e}") from None
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
    explore_on = bool(getattr(a, "explore", False))
    if getattr(a, "explore_cover", False) and not explore_on:
        raise SystemExit("dungeon@9.14b refused: --explore-cover goes with --explore")
    if explore_on and not patrol:
        raise SystemExit("dungeon@9.14 refused: --explore goes with --search patrol")
    start = hunt.start_cell(area, a.seed, near=hf.area_centre(area))
    if patrol and map_ in PATROL_START:
        import map_prep

        start = patrol_start(map_, okr, map_prep.stand_check)
    start_cell: Cell | None = getattr(a, "start_cell", None)  # U0's TRIAL only (4BU)
    stage_at: Cell | None = getattr(a, "stage_at", None)
    if start_cell is not None or stage_at is not None:
        import map_prep as mp_u0

        why_u0 = u0_setup_refused(map_, start_cell, stage_at, getattr(a, "stage_mob", None),
                                  okr, mp_u0.stand_check)  # fmt: skip
        if why_u0:
            raise SystemExit(f"dungeon@9.26 U0 refused: {why_u0}")
        if start_cell is not None:
            start = start_cell
    ex_anchors: dict[tuple[int, int], Cell] = {}
    ex_reach: Any = None
    ex_know0: Any = None
    if explore_on:  # dungeon@9.14: the start's component of the route grid, in regions
        import explore_map as em

        ex_reach = em.component(np.asarray(okr, dtype=bool), start)
        ex_anchors = em.regions(ex_reach)
        if not ex_anchors:
            raise SystemExit(f"dungeon@9.14 refused: no explore region reachable from {start}")
        ex_know0 = em.load(map_)
    ex_rng = np.random.default_rng(a.seed + 914)  # its own stream: the other draws unchanged
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

    ev_hooks: list[Any] = []  # dungeon@9.14: passive observers of the event stream (--explore)

    def ev(rec: dict[str, Any]) -> None:
        evf.write(json.dumps({"t_ns": r.ns(), **rec}) + "\n")
        evf.flush()
        for hook_ in ev_hooks:
            try:
                hook_(rec, time.monotonic())
            except Exception as e:  # noqa: BLE001 -- an observer never stops the run
                counts["ev_hook_error"] += 1
                if counts["ev_hook_error"] == 1:
                    evf.write(json.dumps({"t_ns": r.ns(), "kind": "ev_hook_error",
                                          "error": repr(e)[:300]}) + "\n")  # fmt: skip

    pb_rec: dict[str, Any] | None = None  # dungeon@9.35b: --player-mode on a boss map, no guard
    if player:
        pb_guard = bool(getattr(a, "engage_screen", False) or getattr(a, "garm_fly", False))
        pb_bosses = player_boss_spawns(map_)
        pb_line = player_boss_warning(map_, pb_bosses, pb_guard)
        if pb_line is not None:  # a warning only (Batt 2026-11-12): the run goes on
            print(pb_line, flush=True)
            pb_rec = {"kind": "player_boss_warning",
                      "bosses": None if pb_bosses is None else list(pb_bosses),
                      "guard": pb_guard}  # fmt: skip
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

        def player_chat_closed(when: str) -> None:
            """dungeon@9.35: the setup's chat-close step (bench.close_chat) presses Enter on an
            open chat input; a player's run never does (text left in it would go to public chat),
            so under --player-mode an open input stops the run before that step can run."""
            if player and r.is_state(screen, "chat_open"):
                raise r.Stop(f"dungeon@9.35 refused: --player-mode: the chat input is open "
                             f"({when}): close it first (a person)")  # fmt: skip

        player_chat_closed("at the start")
        # the Battle Log reader (battle_log.py live) reads the SHOWN chat tab: since 2026-11-05 the
        # window has two (Battle Log | Chat, the replies'), and a client restart shows the first
        # while a typed line's check may leave the replies' shown -- so Battle Log is selected here
        import client_layout as cl_

        cl_.select_tab(agent_raw, screen, "battle")
        # the setup (the experimenter's restore, never a decision): full HP / SP, the stock topped
        # up against the DB's last save (an upper bound of what is carried), the weight checked.
        # dungeon@9.35 (--player-mode): a public server has no DB of ours -- nothing is read from
        # the lab's DB; the stock comes from the hotbar's pixels alone (below)
        inv: dict[int, int] = {}
        level_db: int | None = None
        if not player:
            name = json.loads((cr.data_dir(crk) / "char.json").read_text())["name"]
            q_cid = f"SELECT char_id FROM `char` WHERE name = {r.sql_str(name)};"
            cid = int(r.db_query(q_cid)[0][0])
            inv = {int(i): int(n) for i, n in r.db_query(
                f"SELECT nameid, amount FROM inventory WHERE char_id = {cid} "
                "AND nameid IN (504, 601);")}  # fmt: skip
            q_lv = f"SELECT base_level FROM `char` WHERE char_id = {cid};"
            level_db = int(r.db_query(q_lv)[0][0])
        setup = [*level_lines(level_db, conf.get("level_hold")), "@heal"]  # the hold, then heal
        p_to = potions_target(strat, conf)
        w_to = int(strat.get("wings_to") or conf["wings_to"])
        if inv.get(504, 0) < p_to and not heal_candy:  # 9.31: no White Potion top-up with candies
            setup.append(f"@item 504 {p_to - inv.get(504, 0)}")
        if inv.get(601, 0) < w_to:
            setup.append(f"@item 601 {w_to - inv.get(601, 0)}")
        setup = player_plan(setup, player)  # dungeon@9.35: a player types none of these lines
        import gm_state

        fr0 = gm_state._frames(screen)
        w0 = gm_state._weight(fr0)
        red0 = overweight_red(fr0[0])  # Amendment I: the reader is blind to the red (>= 50 %) line
        cleared: dict[str, Any] | None = None
        if (gm_state.weight_share(w0) or 0.0) >= CLEAR_AT or (w0 is None and red0):
            # dungeon@6: the Thief's Etc tab holds Batt's target items; dungeon@9.35: a player's
            # bag is never dropped (no clear stand to warp to): the same refusal
            if not conf["clear_etc"] or player:
                hold = etc_hold_refused(gm_state.weight_share(w0), red0, conf)
                if hold is not None:
                    raise r.Stop(f"dungeon@6: weight {w0} {hold} for the {a.char}: "
                                 "the setup never drops its Etc tab (a person first)")  # fmt: skip
            else:
                typed_line(agent_raw, screen, f"@warp {CLEAR_STAND[0]} {CLEAR_STAND[1]} "
                           f"{CLEAR_STAND[2]}", conf["job"], crk, player_mode=player)  # fmt: skip
                time.sleep(3.0)
                bench.close_chat(agent_raw, screen)
                cleared = clear_etc(agent_raw, screen, why="dungeon-setup")
        typed: list[str] = []  # every setup line actually sent, in order (the run_start record)

        def setup_line(cmd: str) -> None:
            typed.append(cmd)
            # 4.04 Amendment A: @heal is idempotent -- chat_guard's skip (a refused 3rd @heal in a
            # row is not typed; the HP / SP are full after the pre-run's heal or the relog)
            got_ = typed_line(agent_raw, screen, cmd, conf["job"], crk, player_mode=player,
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
        if player:  # dungeon@9.35: the stock is the person's -- read from the hotbar, never added
            import hotbar_count as hb

            try:
                tpl = hb.load()
            except OSError as exc:
                raise r.Stop(f"dungeon@9.35: no hotbar digit templates ({exc})") from exc
            slots = {stock_items[k]: hotbar_slot(keys_[k]) for k in stock_items}  # 9.31: + candies
            time.sleep(0.8)  # as read_stock: the hotbar redrawn
            g_pm = hb.gray(np.asarray(r.grab_after(screen, (gx0, gy0, gw, gh), r.ns())))
            before = {item: hb.read_count(g_pm, slot, tpl) for item, slot in slots.items()}
            stock = {"before": before, "added": {}, "after": before,
                     "min": {"wings": PLAYER_MIN_WINGS, "heals": PLAYER_MIN_HEALS}}  # fmt: skip
            heal_items = ([i for _, i in HEAL_ORDER] if heal_candy
                          else [STOCK_ITEMS["potion"]])  # fmt: skip
            why_pst = player_stock_refused(before, heal_items)
            if why_pst is not None:
                raise r.Stop(f"dungeon@9.35 refused: --player-mode: {why_pst} {stock}")
            true_potions = int(before.get(STOCK_ITEMS["potion"]) or 0)
            stock_watch = (tpl, slots)  # dungeon@8.4's guard in the run, as the Rogue's
            if heal_candy:  # dungeon@9.31: the heal items' counts, as read
                heal_left.update({i: before.get(i) for _, i in HEAL_ORDER})
        elif conf.get("hotbar_stock"):
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
            slots = {stock_items[k]: hotbar_slot(keys_[k]) for k in stock_items}  # 9.31: + candies
            targets = {504: p_to, 601: w_to}
            if heal_candy:  # dungeon@9.31: the potions are read (the fallback), never topped up
                targets = {601: w_to, **HEAL_CANDY_TO}

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
            short = {i: c for i, c in after.items()
                     if i in targets and (c is None or c < targets[i])}  # fmt: skip
            stock = {"before": before, "added": add, "after": after}
            if short:
                raise r.Stop(f"dungeon@8.3: the stock is short after the top-up {stock}")
            true_potions = int(after[504] or 0)
            setup = []  # the stand lines are typed; the map lines follow
            stock_watch = (tpl, slots)
            if heal_candy:  # dungeon@9.31: the heal items' counts, as read after the top-up
                heal_left.update({i: after.get(i) for _, i in HEAL_ORDER})
        # Amendment I: the potions over the strategy's stock are DRUNK at the stand (its hotkey,
        # paced; outside the measured window): carried weight is loot room before 50 %
        drunk = 0
        excess = 0 if heal_candy else true_potions - p_to  # 9.31: the fallback potions stay
        if player:  # dungeon@9.35: the person's potions are never drunk down at the start
            excess = 0
        if excess > 0:
            ui_gate.ensure_clear(agent_raw, screen, why="dungeon-setup:drink")
            r.activate_client(agent_raw, screen)
            for _ in range(excess):
                agent_raw.keys(keys_["potion"])
                drunk += 1
                time.sleep(0.35)
            time.sleep(1.0)
        # the map's lines: @warp, --clear-map's @killmonster2, --stage-mob's @monster (9.18's
        # TRIAL only), and with --stage-at (U0's TRIAL only) the spawn at X,Y and the @warp back
        setup.extend(map_setup_lines(map_, start, a.clear_map, getattr(a, "stage_mob", None),
                                     getattr(a, "stage_at", None)))  # fmt: skip
        setup = player_plan(setup, player)  # dungeon@9.35: no @warp -- she starts where she stands
        player_chat_closed("before the setup's chat-close step")
        for cmd in setup:
            setup_line(cmd)
        bench.close_chat(agent_raw, screen)
        r.activate_client(agent_raw, screen)
        time.sleep(1.0)

        frame_meta: list[tuple[int, int]] = [(0, -1)]  # 9.21: the last frame()'s (t_ns, frame id)

        def frame() -> Any:
            t_f, img_f, id_f, _src_f = r.grab_after_meta(screen, (gx0, gy0, gw, gh), r.ns())
            frame_meta[0] = (t_f, id_f)
            return np.ascontiguousarray(img_f[..., :3])

        def newer_readout(after_ns: int, prev_id: int) -> tuple[int, Any, int, str] | None:
            """9.21 (LF-2): the readout's rect (game-region pixels -> the screen) from a newer
            frame (newer_frame)."""
            x_r, y_r, w_r, h_r = selfpos.default_rect()
            return newer_frame(screen, (gx0 + x_r, gy0 + y_r, w_r, h_r), after_ns, prev_id)

        def read_readout(img_: Any) -> Any:
            """9.21 (LF-2): the light-enabled read of the readout's rect alone (the same pixels
            the main read crops from the whole frame)."""
            h_i, w_i = np.asarray(img_).shape[:2]
            return selfpos.read_minimap(img_, digits, (0, 0, w_i, h_i), light=True)

        if player:  # dungeon@9.35: she starts where the person left her -- her cell, read
            here0: Cell | None = None  # from the minimap readout (PosConfirm's rule, as the loop)
            t_p0 = time.monotonic()
            while here0 is None and time.monotonic() - t_p0 <= PLAYER_POS_S:
                rd0 = selfpos.read_minimap(frame(), digits, light=True)
                here0 = pos_ok.accept(time.monotonic(), rd0)
                if here0 is None:
                    time.sleep(0.2)
            why_pc = player_start_refused(map_, here0, okr, area)
            if why_pc is not None or here0 is None:
                raise r.Stop(f"dungeon@9.35 refused: --player-mode: {why_pc}")
            start = here0
            if explore_on:  # dungeon@9.14's regions: HER component (the seed's cell was a guess)
                ex_reach = em.component(np.asarray(okr, dtype=bool), start)
                ex_anchors = em.regions(ex_reach)
                if not ex_anchors:
                    raise r.Stop(f"dungeon@9.14 refused: no explore region reachable from {start}")
        fr1 = gm_state._frames(screen)
        w_ = gm_state._weight(fr1)
        share = gm_state.weight_share(w_)
        if share is None and overweight_red(fr1[0]):  # Amendment I: fail closed on the red line
            raise r.Stop("dungeon@4: the weight line reads RED (>= 50 %) after the setup")
        if player:  # dungeon@9.35: a READ weight under WEIGHT_MAX (her bag is never dropped)
            why_pw = player_weight_refused(share, overweight_red(fr1[0]))
            if why_pw is not None:
                raise r.Stop(f"dungeon@9.35 refused: --player-mode: {why_pw}")
        bare_ref: Any = None  # dungeon@9.27: the F5 slot's ARMED look (bare_ref_cut)
        bare_rec: dict[str, Any] | None = None
        bare_reg: Any = None
        bare_keys: list[str] = []
        opener_ref: Any = None  # dungeon@9.27c: the opener's slot SHOWING it (opener_ref_cut)
        if bare_on:  # the slot must read EMPTY (the dagger worn), else no run: a person first
            bare_reg = ui_gate._registry(ui_gate._require_ready())  # the gate's own template set
            bare_keys = ui_gate.window_keys(bs.EQUIP_WINDOW)  # Alt+Q (open_window@1's L2 chord)
            t_br = time.monotonic()
            while True:
                f_br = frame()
                bare_ref, bare_rec, why_br = bare_ref_cut(bs.slot_gray(f_br))
                if why_br is not None:
                    raise r.Stop(f"dungeon@9.27 refused: --bare-steal: {why_br} {bare_rec}")
                if bare_ref is not None:
                    break
                if time.monotonic() - t_br > BARE_REF_WAIT_S:
                    raise r.Stop("dungeon@9.27 refused: --bare-steal: the equip slot stayed "
                                 f"unreadable {BARE_REF_WAIT_S} s {bare_rec}")  # fmt: skip
                time.sleep(0.2)
            bare_rec["windows"] = ui_gate.windows_at_home(f_br, bare_reg)
            if opener_key is not None:  # dungeon@9.27c: the opener sits in the bag, its icon on
                t_op = time.monotonic()  # its key; the dagger worn (F5 empty, just read)
                while True:
                    f_op = frame()
                    opener_ref, op_rec, why_op = opener_ref_cut(bs.slot_gray(f_op), opener_key)
                    if why_op is not None:
                        raise r.Stop(f"dungeon@9.27c refused: --steal-opener: {why_op} {op_rec}")
                    if opener_ref is not None:
                        break
                    if time.monotonic() - t_op > BARE_REF_WAIT_S:
                        raise r.Stop("dungeon@9.27c refused: --steal-opener: the opener's slot "
                                     f"stayed unreadable {BARE_REF_WAIT_S} s {op_rec}")  # fmt: skip
                    time.sleep(0.2)
                if bare_read(f_op, bare_ref) is not False:  # F5 must still read the dagger worn
                    st_op = bs.slot_stats(bs.slot_crop(bs.slot_gray(f_op)), bare_ref)
                    raise r.Stop("dungeon@9.27c refused: --steal-opener: the F5 slot no longer "
                                 f"reads the dagger worn {st_op}")  # fmt: skip
                bare_rec["opener"] = op_rec
        ev({"kind": "run_start", "strategy": a.strategy, "seed": a.seed, "engage": a.engage,
            "version": VERSION if a.engage == "defend_scan" else MR_VERSION,
            "search": a.search, "route": None if rt is None else rt.id, "loot": a.loot,
            "fixes": fixes_of(a), "bosses": list(bosses),
            "char": a.char, "steal": a.steal, "bank_tags": bank, "clear_map": a.clear_map,
            "tag_templates": sorted(tag_tpl), "potions_to_char": conf["potions_to"],
            "wings_to": w_to,
            "minutes": a.minutes, "map": map_, "start": list(start), "inv_db": inv,
            **({"start_cell": list(start_cell)} if start_cell is not None else {}),
            **({"stage_at": list(stage_at)} if stage_at is not None else {}),
            **({"value_target_values": vt_values} if vt_values else {}),
            "level_db": level_db, "level_hold": conf.get("level_hold"),
            # the judge's MaxHP / MaxSP when no packet gives them (2026-11-05: the Rogue at 99)
            "max_hp": conf["max_hp"], "max_sp": conf.get("max_sp"),
            "setup": typed, "stock": stock, "weight": w_, "weight_before": w0,
            "cleared": cleared,
            "potions_to": p_to, "potions_drunk": drunk,
            "params": strat, "rest_spots": spots,
            **({"player_mode": fixes_of(a)["player_mode"]} if player else {}),
            **({"player_home_key": home_key} if player else {}),
            **({"bare_steal": fixes_of(a)["bare_steal"], "bare_ref": bare_rec,
                "bare_keys": bare_keys} if bare_on else {}),
            **({"bare_ready": fixes_of(a)["bare_ready"]} if bare_ready_on else {}),
            **({"steal_opener": fixes_of(a)["steal_opener"]} if opener_key is not None else {}),
            **({"house": house_rec} if house_on else {})})  # fmt: skip
        if pb_rec is not None:  # dungeon@9.35b: the start's boss warning, in the run's record
            ev(pb_rec)
        if share is not None and share >= WEIGHT_MAX:
            raise r.Stop(f"dungeon@1: weight {share:.2f} >= {WEIGHT_MAX} (a person first)")
        blt = hf.BattleLogTail(out / "battle_log_live.jsonl", owner_pid=__import__("os").getpid())
        mr = a.engage == "melee_ring"  # Batt 13:4x: the CURSOR engages, the detector does not
        boxes = None
        item_det: Any = None  # dungeon@9.33 (--loot-items MODEL): the floor-item model's client
        if a.boxes and not mr:
            boxes = BoxWatch(screen, (gx0, gy0, gw, gh), r,
                             None if a.box_model == "v1" else a.map,
                             "cpu" if a.box_detector == "cpu" else "gpu",
                             getattr(a, "box_every", BOX_EVERY_S))  # fmt: skip
            ev({"kind": "box_model", "choice": a.box_model, **boxes.model,
                "every_s": boxes.every_s})  # fmt: skip
            if boxes.gpu:  # dungeon@8.9: each detection's path + wall time (R3's windows, 4N G1)
                boxes.det.log_path = out / "detections.jsonl"
        if getattr(a, "loot_items", None):
            import unit_detector as ud_i

            onnx_i = Path("/dev/shm/poring-lab-detector/model") / f"{a.loot_items}{ONNX_TAIL}"
            if not onnx_i.exists():
                raise r.Stop(f"dungeon@9.33: no CPU fallback for --loot-items ({onnx_i})")
            item_det = ud_i.GpuDetector(ud_i.UnitDetector(model=onnx_i), weights=a.loot_items)
        hud_tx: Any = None  # dungeon@9.29 (--hud; Batt 11-11: "HUD on: lines, no boxes")
        if getattr(a, "hud", False):
            import operator_hud as oh

            hud_fast = getattr(a, "hud_fast", None)  # dungeon@9.29b
            hud_tx = oh.HudSender(agent_raw, (gx0, gy0, gw, gh), r.desktop(),
                                  label=f"dungeon {a.strategy} {a.label or ''}".strip(),
                                  min_interval_s=min(HUD_EVERY_S, hud_fast or HUD_EVERY_S),
                                  ttl_ms=(HUD_FAST_TTL_MS if hud_fast
                                          else oh.DEFAULT_TTL_MS))  # fmt: skip
            if hud_fast and boxes is not None:  # dungeon@9.29c: the GPU's in a thread of its own
                boxes.start_hud(float(hud_fast), out / "detections_hud.jsonl")
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
        loot_settle_t = -1e9  # 9.13d: the end of the last loot step that clicked an item
        loot_first_on = getattr(a, "loot_first", False)  # dungeon@9.16
        quiet_scan_on = getattr(a, "quiet_scan", False)  # dungeon@9.17
        late_confirm_on = getattr(a, "late_confirm", False)  # dungeon@9.21 (LF-2)
        unread_step_on = getattr(a, "unread_step", False)  # dungeon@9.22 (LF-4)
        still_target_on = getattr(a, "still_target", False)  # dungeon@9.23 (LS-2)
        lead_press_on = getattr(a, "lead_press", False)  # dungeon@9.24 (LS-1)
        own_moves: deque[OwnMove] = deque(maxlen=64)  # 9.22: our commands that walked her
        ust: dict[str, Any] = {"t0": None}  # 9.22: the pos_unread escape in progress (t0: due)

        def note_move(rel: Sequence[int], by: str) -> None:
            """9.22: an own command that walks her (bookkeeping only: no input, no event)."""
            own_moves.append(OwnMove(time.monotonic(), (int(rel[0]), int(rel[1])), by))

        def unread_end(event: str, **rec: Any) -> None:
            """9.22: the escape ends -- "fresh" (a fresh read: no wing), "wing" (LF-4's fallback,
            the pos_unread wing follows), "refused" (no safe step: the wing follows), "fly" (another
            Fly Wing took her away). A no-op when no escape runs."""
            if ust["t0"] is not None:
                ev({"kind": "unread_step", "event": event, "steps": ust["steps"],
                    "s": round(time.monotonic() - ust["t0"], 2), **rec})  # fmt: skip
                counts[f"unread_step_{event}"] += 1
            ust["t0"] = None

        boss_walk_on = getattr(a, "boss_walk", False) and bool(bosses)  # dungeon@9.18
        boss_walks: deque[float] = deque(maxlen=16)  # 9.18: the walk-aways' ticks
        boss_grace_until = -1e9  # 9.18: boss lines read while walking away are the dog's last
        fight_t0 = -1e9  # 9.16: when the current fight began (the engage below)
        ours_ticks: deque[float] = deque(maxlen=256)  # dungeon@9.13: our recent hits' ticks
        unreach_on = getattr(a, "unreach_escape", False)  # dungeon@9.26 (Study S-UA)
        ua_locks: deque[NoHitLock] = deque(maxlen=8)  # 9.26: the latest no-hit locks
        ua_marks: dict[Cell, float] = {}  # 9.26 (c): cells the scan and the box path skip, until
        ua_walks: deque[float] = deque(maxlen=8)  # 9.26: the unreach walks' ticks
        ua_drop_t = -1e9  # 9.26: the last tick the HP read as dropped (an attacked sign)

        def ua_lock(lock_: Mapping[str, Any], tick_: float) -> NoHitLock:
            """9.26: the lock that just ended "no hits", as the trigger's record (no input)."""
            c_ = lock_.get("cell")
            sign_ = max(last_swing, last_taken, ua_drop_t)  # a Miss, a hit line, an HP drop
            return NoHitLock(t0=float(lock_["t"]), t1=tick_,
                             cell=None if c_ is None else (int(c_[0]), int(c_[1])),
                             n=n_strike[0], sign_t=sign_)  # fmt: skip

        def unreach_escape(tr: Mapping[str, Any], tick_: float) -> str:
            """dungeon@9.26 (--unreach-escape): the trigger fired. (c) its cells are marked for the
            defend scan and the box path; then (a) ONE walk click through click_at to the first
            of unreach_walk_targets' cells (the boss walk's checks: the route grid, no carve, no
            zone crossing, in view, the client's pick; one click the server answers) where the
            cursor reads clear (the search walk's gate: never a SWORD, a no-entry ring or an
            unknown read), or (b) the Fly Wing (unreach_action). The event; returns the action
            ("walk" / "fly" / "none": a Fly Wing went off < 2 s ago)."""
            nonlocal ua_marks
            ua_marks = unreach_marks({c_: u_ for c_, u_ in ua_marks.items() if u_ > tick_},
                                     tr["cells"], tick_ + UNREACH_MARK_S)  # fmt: skip
            to_: Cell | None = None
            tried_: list[list[Any]] = []  # the walk targets hovered, with their verdicts
            h_ = here
            if h_ is not None and not any(tick_ - t_ < UNREACH_AGAIN_S for t_ in ua_walks):

                def ua_fits(c_: Cell, h: Cell = h_) -> bool:
                    hh, ww = okr.shape
                    if not (0 <= c_[0] < ww and 0 <= c_[1] < hh) or not okr[c_[1], c_[0]]:
                        return False
                    if carved[c_[1], c_[0]] or mz.segment_violates(h, c_, zones) is not None:
                        return False
                    u_, v_ = project(h, [(c_[0] - h[0], c_[1] - h[1])])[0]
                    if not in_view(u_, v_):
                        return False
                    return walk_pick_ok(picked_cell(camera, gat, h, (u_, v_)), c_, okr)

                def ua_reach(c_: Cell, h: Cell = h_) -> bool:
                    from poring_dataset import walk as wkp_u

                    return bool(wkp_u.click_walk_ok(reach_grid, h[0], h[1], c_[0], c_[1]))

                for c_t in unreach_walk_targets(h_, tr["cells"], ua_fits, ua_reach):
                    u_t, v_t = project(h_, [(c_t[0] - h_[0], c_t[1] - h_[1])])[0]
                    vd_ = str(hover(u_t, v_t)["verdict"])  # the walk gate: clear only
                    tried_.append([list(c_t), vd_])
                    if vd_ == "clear":
                        to_ = c_t
                        break
            action, why_ = unreach_action(h_, to_, ua_walks, tick_)
            if action == "walk" and h_ is not None and to_ is not None:
                rel_ = (to_[0] - h_[0], to_[1] - h_[1])
                u_w, v_w = project(h_, [rel_])[0]
                if bare is not None:
                    bare.escape()  # dungeon@9.27: never walk away bare
                click_at(u_w, v_w, "walk")
                note_move(rel_, "walk")  # 9.22's bookkeeping: a walk click (UNREAD_WALK_BY)
                ua_walks.append(tick_)
            elif tick_ - fly_at > 2.0:  # the boss guard's own Fly Wing path
                press("fly", "unreach")
            else:  # a Fly Wing went off < 2 s ago: she is away already
                action, why_ = "none", "fly_recent"
            counts["unreach"] += 1
            counts[f"unreach_{action}"] += 1
            ev({"kind": "unreach", "t0_ns": round(float(tr["t0"]) * 1e9), "locks": tr["locks"],
                "cells": tr["cells"], "span_s": tr["span_s"], "n": tr["n"],
                "here": None if h_ is None else list(h_), "action": action, "why": why_,
                "to": None if to_ is None else list(to_), "tried": tried_,
                "marked": sum(1 for u_ in ua_marks.values() if u_ > tick_),
                "mark_s": UNREACH_MARK_S})  # fmt: skip
            return action

        ex_rec: Any = None  # dungeon@9.14 (--explore): the passive knowledge recorder
        if explore_on:
            ex_rec = em.Recorder(map_, sid, lambda t0_, t1_: sum(
                1 for t_o in ours_ticks if t0_ <= t_o <= t1_))  # fmt: skip
            ev_hooks.append(ex_rec.on_event)
        kills_seen: list[float] = []
        exp_first = bool(getattr(a, "exp_first", True))  # dungeon@9.34 (Batt 11-12)
        exp_seen = False  # 9.34: the client printed an exp line in this run
        exp_pair: tuple[str, float] | None = None  # 9.34: the last exp kill's line, unpaired
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

        bare: BareCtl | None = None  # dungeon@9.27 (--bare-steal): built below, once the I/O exists

        def press(what: str, why: str) -> None:
            if what == "fly" and why != "pos_unread":
                unread_end("fly", why=why)  # 9.22: a teleport ends an escape (no-op without one)
            if what == "fly" and bare is not None:  # dungeon@9.27: never fly away bare -- the
                bare.escape()  # dagger's key first (no read-back here: the wing is not delayed)
            if what == "potion" and heal_candy:  # dungeon@9.31: a candy first while one is left
                what = heal_pick(heal_left)
            agent_raw.keys(keys_[what])
            counts[what] += 1
            ev({"kind": "press", "what": what, "key": keys_[what], "why": why})
            if stock_watch is not None and what in STOCK_ITEMS:  # dungeon@8.4
                stock_due[STOCK_ITEMS[what]] = time.monotonic() + STOCK_READ_S
                stock_tries[STOCK_ITEMS[what]] = 0
            elif stock_watch is not None and what in stock_items:  # dungeon@9.31: the candies
                stock_due[stock_items[what]] = time.monotonic() + STOCK_READ_S
                stock_tries[stock_items[what]] = 0

        last_click_t = [-1e9]  # dungeon@9.27b (--bare-ready): when click_at last clicked

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
            last_click_t[0] = time.monotonic()
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

        ex_st: dict[str, Any] = {"target": None, "t": 0.0, "recent": {}, "blocked": set()}

        def explore_goal(h: Cell) -> Cell | None:
            """dungeon@9.14 (--explore): the aimed region's anchor; on arrival (or after
            EXPLORE_LEG_MAX_S) a new region is chosen -- explore + exploit, sampled
            (explore_map.scores / choose) from the file's knowledge plus this run's."""
            now_ = time.monotonic()
            tg = ex_st["target"]
            if tg is not None and mroutes.reached(h, ex_anchors[tg], WP_TOL):
                ex_rec.arrived(tg)
                ex_st["recent"][tg] = now_
                ev({"kind": "explore", "event": "arrived", "region": list(tg), "at": list(h),
                    "s": round(now_ - ex_st["t"], 1)})  # fmt: skip
                tg = ex_st["target"] = None
            elif tg is not None and now_ - ex_st["t"] > EXPLORE_LEG_MAX_S:
                ex_st["recent"][tg] = now_
                ev({"kind": "explore", "event": "timeout", "region": list(tg), "at": list(h)})
                tg = ex_st["target"] = None
            if tg is None:
                skip_ = (
                    {em.region_of(h)}
                    | set(ex_st["blocked"])
                    | {k_ for k_, t_ in ex_st["recent"].items() if now_ - t_ < em.RECENT_S}
                )
                know_ = em.merge(em.Knowledge(map=map_, regions=ex_know0.regions),
                                 em.Knowledge(map=map_, regions=ex_rec.know.regions))  # fmt: skip
                cover_ = None
                if getattr(a, "explore_cover", False):  # dungeon@9.14b: novelty by coverage
                    vis_ = {**ex_know0.visited, **ex_rec.know.visited}
                    cover_ = em.coverage(vis_, ex_reach)
                sc_ = em.scores(know_, ex_anchors, h, skip_, cover_)
                tg = em.choose(sc_, ex_rng)
                if tg is None:
                    return None
                ex_st["target"], ex_st["t"] = tg, now_
                ev({"kind": "explore", "event": "target", "region": list(tg),
                    "anchor": list(ex_anchors[tg]), "score": round(sc_[tg], 3),
                    "choices": len(sc_), "at": list(h)})  # fmt: skip
            return ex_anchors[tg]

        def explore_block(h: Cell) -> None:
            """No route to the aimed anchor: the region is left out for the run."""
            wp_st["skips"] += 1  # dead_end counts it as a route-less skip
            if ex_st["target"] is not None:
                ex_st["blocked"].add(ex_st["target"])
                ev({"kind": "explore", "event": "blocked", "region": list(ex_st["target"]),
                    "at": list(h)})  # fmt: skip
            ex_st["target"] = None

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

        if bare_on:  # dungeon@9.27: every input is the runner's own (chord, move, send, press)

            def bare_lines() -> list[dict[str, Any]]:
                with blt.lock:
                    return list(blt.lines)

            def bare_dclick(u_: int, v_: int) -> None:
                """The weapon slot's double-click (game-region px): inside the game frame only."""
                if not (0 <= u_ < gw and 0 <= v_ < gh):
                    raise r.Stop(f"--bare-steal: the weapon slot point {(u_, v_)} is off the frame")
                ui_double_click(agent, gx0 + u_, gy0 + v_, r.desktop(), r.ns)
                counts["click_bare_dclick"] += 1

            def bare_opener(why_: str) -> None:
                """--steal-opener (dungeon@9.27c): the opener's hotbar key, sent as press() sends
                a key (agent_raw.keys: the agent's own input path, through the mux)."""
                assert opener_key is not None
                agent_raw.keys(opener_key)
                counts["opener"] += 1
                ev({"kind": "press", "what": "opener", "key": opener_key, "why": why_})

            bare = BareCtl(
                BareIo(frame=frame,
                       windows=lambda f_: ui_gate.windows_at_home(f_, bare_reg),
                       origin=lambda f_: window_origin(f_, bare_reg, bs.EQUIP_WINDOW),
                       chord=lambda: agent_raw.chord(*bare_keys),
                       double_click=bare_dclick,
                       press=lambda why_: press("equip", why_),
                       lines=bare_lines, guard=guard_tick,
                       opener=bare_opener if opener_key is not None else None),
                bare_ref, counts, ev, r.Stop, ready=bare_ready_on,
                opener=None if opener_key is None else OpenerRead(opener_key, bare_ref,
                                                                  opener_ref),
                cue=getattr(a, "steal_cue", "both"))  # fmt: skip

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

        reach_cache: dict[tuple[Cell, Cell], bool] = {}
        reach_logged: dict[Cell, float] = {}
        reach_proj: dict[str, Any] = {"here": None, "uv": None}  # box_spot's projection, per cell
        reach_pick: dict[tuple[Cell, int, int], Cell | None] = {}  # 9.12b: picked cells, 4-px bins

        def unreachable(here_: Cell | None, foot: Sequence[float]) -> bool:
            """dungeon@9.12 (--reach-check): the box's cell is one the server would not walk us to
            on one click (reach_ok); False when unknown (no position, no grid)."""
            if reach_grid is None or here_ is None:
                return False
            # 9.12b (after p25): the cell the CLIENT picks under the box's foot -- the camera ray's
            # first top surface (poring_dataset.picking); on xmas_dun02's raised floors the flat
            # projection was 4-6 cells off (p25: 25 of 33 ignored-start misses caught -> 32)
            kp_ = (here_, round(foot[0] / 4), round(foot[1] / 4))
            if kp_ not in reach_pick:
                if len(reach_pick) > 4000:
                    reach_pick.clear()
                reach_pick[kp_] = picked_cell(camera, gat, here_, foot)
            sp_ = reach_pick[kp_]
            if sp_ is None:  # no top surface hit: the flat projection, as box_spot
                if reach_proj["here"] != here_:  # box_spot's projection (~2.3 ms) once per cell
                    reach_proj.update(here=here_, uv=project(here_, BOX_GRID))
                c_r = nearest_rel(reach_proj["uv"], BOX_GRID, foot)
                sp_ = (here_[0] + c_r[0], here_[1] + c_r[1])  # == box_spot(here_, foot)
            if unreach_on and unreach_marked(ua_marks, sp_, time.monotonic()):
                counts["unreach_skip_box"] += 1  # dungeon@9.26 (c): a marked attacker's cell
                return True
            key_ = (here_, sp_)
            if key_ not in reach_cache:
                if len(reach_cache) > 4000:
                    reach_cache.clear()
                reach_cache[key_] = reach_ok(reach_grid, here_, sp_)
                if not reach_cache[key_]:
                    counts["reach_skip"] += 1
                    now_ = time.monotonic()
                    if now_ - reach_logged.get(sp_, -1e9) >= 30.0:  # rate-limited record
                        reach_logged[sp_] = now_
                        ev({"kind": "reach_skip", "here": list(here_), "spot": list(sp_)})
            return not reach_cache[key_]

        def box_fight_done() -> None:
            """dungeon@5 (decision 4): a box-started fight that ended with no strike is a miss."""
            if box_spots is not None and box_fight.get("spot") is not None \
                    and n_strike[0] == box_fight["n0"]:  # fmt: skip
                sp_ = box_fight["spot"]
                n_ = box_spots.miss(sp_)
                ev({"kind": "box_miss", "spot": list(sp_), "misses": n_,
                    "ignored": box_spots.ignored(sp_)})  # fmt: skip
            box_fight.clear()

        last_strike: dict[str, Any] = {}  # --quick-drop: the last strike's click and arrow times

        def quick_rearm(why: str) -> None:
            """--quick-drop (dungeon@9.6): after a dropped strike the box path runs again (it takes
            the nearest box), at most QUICK_RETRY times a fight; then the ring scan as before."""
            if boxes is None or not a.box_strike:
                return
            n_ = int(box_fight.get("quick_n", 0))
            ev({"kind": "quick_drop", "why": why, "rearm": n_ < QUICK_RETRY, "n": n_ + 1})
            counts[f"quick_drop_{why}"] += 1
            if n_ >= QUICK_RETRY:
                return
            box_fight["quick_n"] = n_ + 1
            box_fight["tried"] = False
            if box_fight.get("box") is None:
                box_fight["box"] = []  # any box: box_target takes the nearest itself

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
            (Batt ~16:0x); the strike then goes to where the target stands beside us.
            dungeon@9.27 (--bare-steal): a new target's first strike takes the dagger off first
            (BareCtl.before_strike); the swap's aim check may drop the click (False: no lock)."""
            if bare is not None:
                hp_b = st.hist[-1][1] if st.hist else None
                if not bare.before_strike(by, hp_b, lambda: hover(u, v)["verdict"] == "sword"):
                    return False  # the target left the point during the swap: the scan finds it
                if escaped[0]:
                    return True  # a Fly Wing inside the swap (guard_tick): the loop takes over
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
            if max(abs(int(rel[0])), abs(int(rel[1]))) >= 2:  # 9.22: the client walks her up
                note_move(rel, "strike")
            t_c = time.monotonic()
            n, arrow, dmg = 1, None, None
            cur = ref
            quick = bool(getattr(a, "quick_drop", False))
            burst_s = QUICK_ARROW_S if quick else BURST_MAX_S
            far_from = NEAR_SINGLE_CELLS if getattr(a, "near_single", False) else FAR_CELLS
            far_w = far_window(rel, far_from) if getattr(a, "far_single", False) else None
            if far_w is not None:  # dungeon@9.8: one click, the walk-up's own time
                burst_s = far_w
            gated = far_w is None and near_still_cells(rel, getattr(a, "near_single_still", False))
            ref_g = np.ascontiguousarray(np.asarray(ref)[..., :3]) if gated else None
            still_rec: dict[str, Any] | None = {"reclicks": 0, "stopped_s": None,
                                                "shift": None} if gated else None  # fmt: skip
            while time.monotonic() - t_c < burst_s:
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
                if far_w is None and n < BURST_MAX and time.monotonic() - t_c >= n * gap:
                    if still_rec is not None and still_rec["stopped_s"] is None:  # 9.25b
                        sh_ = rp.scene_shift(ref_g, np.ascontiguousarray(np.asarray(cur)[..., :3]))
                        still_rec["shift"] = [round(sh_[0], 1), round(sh_[1], 1)]
                        if not near_still_reclick(sh_):
                            still_rec["stopped_s"] = round(time.monotonic() - t_c, 2)
                            counts["near_still_stop"] += 1
                    if still_rec is None or still_rec["stopped_s"] is None:
                        click_at(u, v, "strike_burst")
                        n += 1
                        if still_rec is not None:
                            still_rec["reclicks"] += 1
            # dungeon@9.38 (--quick-drop-scaled): this strike's no-hit window, by its distance
            qh_s = (quick_hit_window(rel, far_w)
                    if quick and getattr(a, "quick_drop_scaled", False) else None)  # fmt: skip
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
                "by": by, "shot": n_shots[0] if n_shots[0] <= MAX_SHOTS else None,
                **({"quick_hit_s": round(qh_s, 2)} if qh_s is not None else {}),
                **({"near_still": still_rec} if still_rec is not None else {})})  # fmt: skip
            if walked is not None:
                time.sleep(WALK_STOP_SETTLE_S)  # our short walk ends before the next scan
                return False  # the click hit the ground: no lock (the caller scans again)
            last_strike.clear()
            last_strike.update(
                t_click=t_c,
                arrow_t=None if arrow is None else t_c + arrow,
                hit_s=QUICK_HIT_S if far_w is None else max(QUICK_HIT_S, far_w),
            )
            if qh_s is not None:  # dungeon@9.38: the fight loop's quick_no_hit reads it from here
                last_strike["hit_s"] = qh_s
            if quick and arrow is None and dmg is None and not escaped[0]:
                quick_rearm("no_arrow")  # dungeon@9.6: nothing connected: no lock, the next box
                return False
            if bare is not None:
                bare.struck()  # dungeon@9.27: the caller holds this target's lock now
            return True

        def box_target() -> tuple[Cell, tuple[float, float]] | None:
            """dungeon@8.8 (rogue-xmas02.md 4M): our walk ends (BOX_SETTLE_S after the last walk
            click), then a box grabbed after that, the nearest to our cell's point within
            BOX_TARGET_PX, is hovered at its box_hover_points; the first SWORD is returned as
            (its cell relative to us, the hover point) for the strike. None: the ring scan."""
            nonlocal last_walk_click
            assert boxes is not None
            t_0 = time.monotonic()
            time.sleep(settle_left(last_walk_click, t_0))
            still_rec: dict[str, Any] = {}
            if getattr(a, "still_strike", False):  # dungeon@9.4: the detection after a still scene
                still_b, waited_b, _sh = wait_still()
                still_rec = {"still": still_b, "still_wait_ms": round(waited_b * 1e3)}
                counts["still_wait"] += 1
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
                                   "wait_ms": round((time.monotonic() - t_set) * 1e3),
                                   **still_rec}  # fmt: skip
            if a.box_now:
                rec["arm"] = arm
            if meta is not None:
                rec.update(path=meta["path"], det_ms=meta["ms"], gpu_reason=meta["reason"],
                           grab_after_ms=round((meta["t"] - t_set) * 1e3),
                           boxes_after_ms=round((meta["t_done"] - t_set) * 1e3))  # fmt: skip
            if getattr(a, "engage_screen", False):  # dungeon@9.7: the nearest box on screen
                near_b = (boxes.near(FOOT_PX, BOX_SCREEN_PX, BOX_TARGET_WAIT_S + 1.0,
                                     lambda f: (not in_view(f[0], f[1] - BODY_UP)
                                                or unreachable(here, f)))
                          if fresh else None)  # fmt: skip
            else:
                near_b = (boxes.near(FOOT_PX, BOX_TARGET_PX, BOX_TARGET_WAIT_S + 1.0) if fresh
                          else None)  # fmt: skip
            if vt_values and fresh and near_b is not None:  # dungeon@9.28 (--value-target, 4CB)
                es_ = getattr(a, "engage_screen", False)
                near_v = boxes.near(  # the SAME candidates and skips, chosen by value
                    FOOT_PX, BOX_SCREEN_PX if es_ else BOX_TARGET_PX, BOX_TARGET_WAIT_S + 1.0,
                    (lambda f: (not in_view(f[0], f[1] - BODY_UP) or unreachable(here, f)))
                    if es_ else None, values=vt_values)  # fmt: skip
                if near_v is not None:
                    near_b = near_v
                    rec["pick"] = boxes.last_pick
            if near_b is None:
                ev({**rec, "box": None, "verdicts": [], "struck": False})
                return None
            foot = ((near_b[0] + near_b[2]) / 2, near_b[3])
            rec.update(
                box=[round(x_, 1) for x_ in near_b],
                d_px=round(math.hypot(foot[0] - FOOT_PX[0], foot[1] - FOOT_PX[1])),
            )
            verdicts: list[str] = []
            if (getattr(a, "far_approach", False) and here is not None
                    and int(box_fight.get("approach_n", 0)) < APPROACH_MAX):  # fmt: skip
                sp_a = box_spot(here, foot)  # dungeon@9.10: too far -> walk toward it first
                rel_a = None if sp_a is None else (sp_a[0] - here[0], sp_a[1] - here[1])
                if rel_a is not None and max(abs(rel_a[0]), abs(rel_a[1])) >= APPROACH_CELLS:
                    cell_a = approach_cell(rel_a)
                    u_a, v_a = project(here, [cell_a])[0]
                    if in_view(u_a, v_a):
                        click_at(u_a, v_a, "approach")
                        last_walk_click = time.monotonic()
                        note_move(cell_a, "approach")  # 9.22: the way she came
                        box_fight["approach_n"] = int(box_fight.get("approach_n", 0)) + 1
                        box_fight["approach_t"] = last_walk_click
                        box_fight["tried"] = False  # the box path looks again after the walk
                        ev({**rec, "verdicts": [], "struck": False, "approach": list(cell_a),
                            "rel_target": list(rel_a), "n": box_fight["approach_n"]})  # fmt: skip
                        counts["far_approach"] += 1
                        return None
            points = box_hover_points(near_b)
            shift = (0.0, 0.0)  # the lead, added to the foot for the strike's cell
            if getattr(a, "lead_strike", False) and meta is not None:
                # dungeon@9.5 (rogue-xmas02.md 4V): a second detection, the same sprite, its motion
                lead_rec: dict[str, Any] = {"why": None}
                if not still_rec.get("still", False):
                    lead_rec["why"] = "not_still"  # a scrolling scene's motion is not the sprite's
                else:
                    time.sleep(max(0.0, LEAD_GAP_S - (time.monotonic() - meta["t"])))
                    meta2 = boxes.fresh_now(arm or "gpu", BOX_TARGET_WAIT_S)
                    t2, got2 = boxes.snapshot() if meta2 is not None else (0.0, [])
                    b2 = same_box(near_b, got2) if meta2 is not None else None
                    if meta2 is None:
                        lead_rec["why"] = "no_detection"
                    elif b2 is None:
                        lead_rec["why"] = "no_match"
                    else:
                        lp = lead_point(near_b, meta["t"], b2, t2)
                        lead_rec.update(
                            gap_ms=round((t2 - meta["t"]) * 1e3), det2_ms=meta2["ms"],
                            path2=meta2["path"], speed=round(lp["speed"], 1),
                            v=[round(x_, 1) for x_ in lp["v"]],
                            lead=[round(x_, 1) for x_ in lp["lead"]], walking=lp["walking"],
                            box2=[round(x_, 1) for x_ in b2])  # fmt: skip
                        now_pt = box_hover_points(b2)[0]
                        points = [lp["point"], now_pt] if lp["walking"] else [now_pt]
                        shift = lp["lead"] if lp["walking"] else (0.0, 0.0)
                        foot = ((b2[0] + b2[2]) / 2, b2[3])
                rec["lead"] = lead_rec
            n_hover = 1 if a.box_now else len(points)
            if "lead" in rec and rec["lead"].get("walking"):
                n_hover = 2  # the led point, then the sprite's current point once
            for k_, (u_, v_) in enumerate(points[:n_hover]):  # dungeon@8.9: ONE hover
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
                    if k_ == 0 and shift != (0.0, 0.0):  # the led point: the cell it predicts
                        foot = (foot[0] + shift[0], foot[1] + shift[1])
                    if still_target_on:  # dungeon@9.23 (LS-2): D2, then a hold for a walker
                        rec["press"], today_p, got_p = press_check(
                            near_b, meta, arm, bool(still_rec.get("still", False)))  # fmt: skip
                        if not today_p and got_p is None:  # no strike: as on no SWORD
                            ev({**rec, "verdicts": verdicts, "struck": False})
                            return None
                        if got_p is not None:  # it stood still and read SWORD again: its box
                            ev({**rec, "verdicts": verdicts, "struck": True,
                                "rel": list(got_p[0])})  # fmt: skip
                            return got_p
                    sp_ = box_spot(here, foot)
                    rel_ = (0, 0) if sp_ is None or here is None else \
                        (sp_[0] - here[0], sp_[1] - here[1])  # fmt: skip
                    ev({**rec, "verdicts": verdicts, "struck": True, "rel": list(rel_)})
                    return rel_, (u_, v_)
            ev({**rec, "verdicts": verdicts, "struck": False})
            return None

        def wait_still() -> tuple[bool, float, tuple[float, float]]:
            """--still-strike: frames every ~60 ms until the scene stops scrolling (still_now) or
            STILL_MAX_S; (still, waited s, the scroll summed over the wait)."""
            t_w = time.monotonic()
            prev = np.ascontiguousarray(np.asarray(frame())[..., :3])
            shifts: list[tuple[float, float]] = []
            while time.monotonic() - t_w < STILL_MAX_S:
                time.sleep(0.06)
                cur_ = np.ascontiguousarray(np.asarray(frame())[..., :3])
                shifts.append(rp.scene_shift(prev, cur_))
                prev = cur_
                if still_now(shifts):
                    break
            total = (sum(x for x, _ in shifts), sum(y for _, y in shifts))
            return still_now(shifts), time.monotonic() - t_w, total

        def still_retarget(u: float, v: float, rel: Cell) -> tuple[float, float] | None:
            """--still-strike for walk_sword: wait for a still scene, carry the point by the scroll
            seen meanwhile, hover there again; the point if a SWORD is still there, else None."""
            still, waited, (dx, dy) = wait_still()
            u2, v2 = u + dx, v + dy
            verdict = "off"
            if in_view(u2, v2):
                verdict = str(hover(u2, v2)["verdict"])
            ev({"kind": "still_retarget", "rel": list(rel), "still": still,
                "waited_ms": round(waited * 1e3), "shift": [round(dx, 1), round(dy, 1)],
                "verdict": verdict})  # fmt: skip
            counts["still_wait"] += 1
            if verdict != "sword":
                counts["still_lost"] += 1
                return None
            return u2, v2

        def press_check(
            b1: Sequence[float], meta_: dict[str, Any] | None, arm_: str | None, still_: bool
        ) -> tuple[dict[str, Any], bool, tuple[Cell, tuple[float, float]] | None]:
            """--still-target (dungeon@9.23, LS-2; rogue-xmas02.md Study S-LS): at the box
            target's SWORD on D1's box ``b1``, ONE more detection D2 (press_decide). Returns (the
            event's "press" record, True when the strike is today's, the re-aimed (rel, point) of
            a held target that stood still and read SWORD again, else None). No still scene or no
            fresh D1 (``meta_``): nothing to compare, today's strike, no D2. --lead-press
            (dungeon@9.24, LS-1): a hold whose shift is >= LEAD_PX is led instead (lead_aim:
            "led", its (rel, point) returned like a re-aim), else LS-2's hold."""
            assert boxes is not None
            t_p = time.monotonic()
            prs: dict[str, Any] = {"moved_px": None, "det2_ms": None, "hold_ms": 0, "polls": 0,
                                   "end": "not_still" if not still_ else "no_d1"}  # fmt: skip
            if lead_press_on:
                prs["lead"] = None  # dungeon@9.24: lead_aim's record, when a lead was computed
            if not still_ or meta_ is None:
                counts[f"still_target_{prs['end']}"] += 1
                return prs, True, None
            meta2 = boxes.fresh_now(arm_ or "gpu", BOX_TARGET_WAIT_S)
            end: str = "no_det2"
            b2: tuple[float, ...] | None = None
            t2 = 0.0
            if meta2 is not None:
                t2, got2 = boxes.snapshot()
                end, b2, moved = press_decide(b1, got2)
                prs.update(det2_ms=meta2["ms"], path2=meta2["path"],
                           wait2_ms=round((time.monotonic() - t_p) * 1e3),
                           gap_ms=round((t2 - meta_["t"]) * 1e3))  # fmt: skip
                if b2 is None:
                    prs["near2_px"] = nearest_centre_px(b1, got2)
                else:
                    assert moved is not None
                    prs.update(moved_px=round(moved, 1), box2=[round(x_, 1) for x_ in b2])
            got: tuple[Cell, tuple[float, float]] | None = None
            today = end != "hold"
            if end == "hold":
                assert b2 is not None
                if lead_press_on:  # dungeon@9.24 (LS-1): a long shift is led, not held
                    got = lead_aim(b1, float(meta_["t"]), b2, t2, prs)
                if got is not None:
                    end = "led"
                else:
                    end, got = hold_still(b2, t2, arm_ or "gpu", float(meta_["t"]), prs)
            prs["end"] = end
            prs["ms"] = round((time.monotonic() - t_p) * 1e3)  # the SWORD read -> the event
            counts[f"still_target_{end}"] += 1
            return prs, today, got

        def hold_still(
            b: Sequence[float], t_b: float, arm_: str, t1: float, prs: dict[str, Any]
        ) -> tuple[str, tuple[Cell, tuple[float, float]] | None]:
            """--still-target (9.23): the strike waits for the moved sprite ``b`` (grabbed at
            ``t_b``) to stand -- hold_track: a fresh detection every HOLD_GAP_S matched to the
            last box, guard_tick() on each poll (the HP, the escapes), until hold_end ends it.
            "still": the new box passes box_target's own selection gate, its first hover point
            is hovered, and only a SWORD read there returns (rel, point) for the strike;
            "timeout" / "lost" / "escaped" (we flew away): None. ``prs`` gets the hold's fields
            (``t1``: D1's grab)."""
            assert boxes is not None
            bw = boxes

            def detect_(timeout: float) -> tuple[float, list[tuple[float, float, float, float]]] \
                    | None:  # fmt: skip
                return bw.snapshot() if bw.fresh_now(arm_, timeout) is not None else None

            hd = hold_track(b, t_b, detect_, guard_tick)
            end, last = str(hd["end"]), hd["box"]
            prs.update(hold_ms=round(hd["hold_s"] * 1e3), polls=hd["polls"], shifts=hd["shifts"],
                       box_end=[round(x_, 1) for x_ in last],
                       end_gap_ms=round((hd["t"] - t1) * 1e3))  # fmt: skip
            if hd["lost_px"] is not None:
                prs["lost_px"] = hd["lost_px"]
            if end != "still":
                return end, None
            foot_e = ((last[0] + last[2]) / 2, last[3])
            lim = BOX_SCREEN_PX if getattr(a, "engage_screen", False) else BOX_TARGET_PX
            if math.hypot(foot_e[0] - FOOT_PX[0], foot_e[1] - FOOT_PX[1]) > lim:
                prs["gate"] = "far"  # box_target's own selection would not take it now
                return end, None
            if getattr(a, "engage_screen", False) and (
                not in_view(foot_e[0], foot_e[1] - BODY_UP) or unreachable(here, foot_e)
            ):
                prs["gate"] = "skip"  # --engage-screen's in-view / --reach-check skip
                return end, None
            u_e, v_e = box_hover_points(last)[0]
            if not in_view(u_e, v_e):
                prs["verdict2"] = "off"
                return end, None
            prs["verdict2"] = str(hover(u_e, v_e)["verdict"])
            if prs["verdict2"] != "sword":
                return end, None
            sp_e = box_spot(here, foot_e)
            rel_e = (0, 0) if sp_e is None or here is None else \
                (sp_e[0] - here[0], sp_e[1] - here[1])  # fmt: skip
            return end, (rel_e, (u_e, v_e))

        def lead_aim(
            b1: Sequence[float], t1: float, b2: Sequence[float], t2: float, prs: dict[str, Any]
        ) -> tuple[Cell, tuple[float, float]] | None:
            """--lead-press (dungeon@9.24, LS-1; rogue-xmas02.md Study S-LS, 4BP): D2 said hold on
            D1's box ``b1`` (grab ``t1``) -> D2's ``b2`` (``t2``). press_lead: a shift < LEAD_PX
            -> None (LS-2's hold, no record). Else the lead (v x age, one cell at most by the
            camera's cell_steps at D2's foot) and its record in ``prs["lead"]``; the led point
            must pass box_target's selection gates (LS-2's re-hover's: "far", --engage-screen's
            "skip"), stay in view ("off") and off our own sprite ("self", as the detector's own
            boxes are dropped); a gate -> None (LS-2's hold). Then (rel, point) for the strike,
            the cell from the LED foot (box_spot). NO SWORD read at the led point -- the sprite
            is not there yet: LS-1's known risk ("sword": "unchecked")."""
            ex, ey = cell_steps(camera, ((b2[0] + b2[2]) / 2, b2[3]))
            pl = press_lead(b1, t1, b2, t2, time.monotonic(), ex, ey)
            if pl["decision"] != "lead":
                return None  # [WALKER_PX, LEAD_PX): LS-2's hold, as without the flag
            foot_l, (u_l, v_l) = pl["foot"], pl["point"]
            lim = BOX_SCREEN_PX if getattr(a, "engage_screen", False) else BOX_TARGET_PX
            gate: str | None = None
            if math.hypot(foot_l[0] - FOOT_PX[0], foot_l[1] - FOOT_PX[1]) > lim:
                gate = "far"  # box_target's own selection would not take it there
            elif getattr(a, "engage_screen", False) and (
                not in_view(foot_l[0], foot_l[1] - BODY_UP) or unreachable(here, foot_l)
            ):
                gate = "skip"  # --engage-screen's in-view / --reach-check skip
            elif not in_view(u_l, v_l):
                gate = "off"
            elif self_box(u_l, v_l):
                gate = "self"  # on our own sprite: a click there walks (--self-recheck's lesson)

            def r1(xs: Sequence[float]) -> list[float]:
                return [round(float(x_), 1) for x_ in xs]

            prs["lead"] = {"v_px_s": r1(pl["v"]), "age_s": round(pl["age_s"], 3),
                           "lead_px": r1(pl["lead"]), "capped": pl["capped"],
                           "point": r1((u_l, v_l)), "raw_px": r1(pl["raw"]), "cap": pl["cap"],
                           "cell_px": [r1(ex), r1(ey)], "foot": r1(foot_l), "gate": gate,
                           "sword": "unchecked"}  # fmt: skip
            if gate is not None:
                counts["lead_press_gated"] += 1
                return None
            sp_l = box_spot(here, foot_l)
            rel_l = (0, 0) if sp_l is None or here is None else \
                (sp_l[0] - here[0], sp_l[1] - here[1])  # fmt: skip
            return rel_l, (u_l, v_l)

        def self_uv() -> tuple[float, float]:
            """Our own feet point on screen (the camera keeps us there): the self box's anchor."""
            u0_, v0_ = project(here, [(0, 0)])[0]
            return float(u0_), float(v0_)

        def scan(purpose: str, cells: Sequence[Cell], stop_on: str
                 ) -> tuple[Cell, Any, dict[str, Any]] | None:  # fmt: skip
            """Hover each cell's point (defend: the body above it; loot: the cell); the first
            ``stop_on`` ("sword" / "pickup") ends the scan. Aborts when a fight starts (loot).
            --loot-first (9.16 part 3): a defend scan that found no sword clicks the first
            PICKUP hand it read (no hit within 1 s), and that spot joins the loot list."""
            nonlocal here, loot_settle_t
            t_s = time.monotonic()
            hand_at: tuple[Cell, float, float] | None = None
            verdicts: Counter[str] = Counter()
            if purpose == "defend" and getattr(a, "walk_stop", False):
                kept = drop_false(cells, false_rel, t_s)
                verdicts["walked_skip"] += len(cells) - len(kept)
                cells = kept
            if purpose == "defend" and unreach_on and ua_marks:  # dungeon@9.26 (c): marked cells
                kept_u = unreach_scan_cells(cells, here, ua_marks, t_s)
                verdicts["unreach_skip"] += len(cells) - len(kept_u)
                counts["unreach_skip_scan"] += len(cells) - len(kept_u)
                cells = kept_u
                if not cells:  # every cell marked: nothing to hover
                    ev({"kind": "scan", "purpose": purpose, "cells": 0, "verdicts": dict(verdicts),
                        "found": None, "found_rel": None, "ms": 0})  # fmt: skip
                    return None
            uv = project(here, cells)
            found = None
            for c, (u, v) in zip(cells, uv, strict=True):
                v_ = v - (BODY_UP if purpose == "defend" else PLANT_UP if purpose == "plant" else 0)
                if not in_view(u, v_):
                    verdicts["off"] += 1
                    continue
                if (purpose == "defend" and getattr(a, "skip_own_cells", False)
                        and in_self_box(u, v_, *self_uv())):  # fmt: skip
                    verdicts["own_skip"] += 1  # dungeon@9.9: never through her own sprite
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
                if vd == "pickup" and purpose == "defend" and loot_first_on and hand_at is None:
                    hand_at = (c, u, v_)
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
            if found is None and hand_at is not None:
                c_h, u_h, v_h = hand_at
                if time.monotonic() - last_taken < 1.0:
                    counts["scan_hand_hit"] += 1  # a hit came: the fight goes first
                else:
                    click_at(u_h, v_h, "loot")
                    counts["loot_click"] += 1
                    counts["scan_hand_click"] += 1
                    ev({"kind": "loot_click", "u": round(u_h, 1), "v": round(v_h, 1),
                        "rel": list(c_h), "cell": None if here is None else
                        [here[0] + c_h[0], here[1] + c_h[1]], "why": "scan_hand"})  # fmt: skip
                    time.sleep(0.45 + 0.2 * max(abs(c_h[0]), abs(c_h[1])))
                    here = read_here() or here
                    loot_settle_t = time.monotonic()  # 9.13d: the next walk waits
                    if here is not None:
                        loot_list.append((here, time.monotonic()))
            return found

        def read_here() -> Cell | None:
            rd = selfpos.read_minimap(frame(), digits, light=True)  # X1b: opt-in, confirmed
            return pos_ok.accept(time.monotonic(), rd)

        # --- --queue (dungeon@9.30, rogue-xmas02.md 4CC): the fight's box queue (q_book, in the
        # fight branch) and the pick after its loot step (queue_next); the rules are bq_* above
        bq_st: dict[str, Any] = {"q": [], "t": 0.0, "fly": fly_at, "due": None}

        def q_rel(foot: Sequence[float]) -> Cell | None:
            """9.30: a foot's cell relative to her (box_spot's projection, cached per cell)."""
            if here is None:
                return None
            if reach_proj["here"] != here:
                reach_proj.update(here=here, uv=project(here, BOX_GRID))
            return nearest_rel(reach_proj["uv"], BOX_GRID, foot)

        def q_target_px() -> tuple[float, float] | None:
            """9.30: the current target's point -- the lock's cell projected from her cell now
            (the strike's rel when the lock has no cell); None: no lock (no target to leave out)."""
            if lock is None:
                return None
            c_, r_ = lock.get("cell"), lock.get("rel")
            if c_ is not None and here is not None:
                rel_t = (int(c_[0]) - here[0], int(c_[1]) - here[1])
            elif r_ is not None:
                rel_t = (int(r_[0]), int(r_[1]))
            else:
                return None
            u_t, v_t = project(here, [rel_t])[0]
            return float(u_t), float(v_t)

        def q_book(sign_: bool) -> None:
            """dungeon@9.30 (--queue): a fight tick's bookkeeping -- no input, no event. A Fly
            Wing since the last one empties the queue; a detection newer than the last one taken
            refreshes it (bq_refresh: the boxes in view, the target and our own body left out);
            an attacked sign read on this tick marks the nearest entry within 2 cells (bq_mark)."""
            assert boxes is not None
            if bq_st["fly"] != fly_at:  # a new spot: the old queue is gone
                bq_st.update(q=[], t=0.0, fly=fly_at)
            with boxes.lock:
                t_b, got_b = boxes.last
            if t_b > bq_st["t"]:
                bq_st["t"] = t_b
                bq_st["q"] = bq_refresh(bq_st["q"], got_b, t_b, target_px=q_target_px(),
                                        rel_of=q_rel, keep=lambda f: in_view(f[0], f[1] - BODY_UP),
                                        values=vt_values)  # fmt: skip
            if sign_ and bq_st["q"]:
                bq_st["q"], _m, new_m = bq_mark(bq_st["q"])
                if new_m:
                    counts["queue_attacking"] += 1

        def queue_next(tick_: float, hold_: bool) -> bool:
            """dungeon@9.30 (--queue): the pick due after a fight's loot step (bq_st["due"]).
            bq_due_state: go / hold / skip on this tick. Then bq_next: the next fresh detection
            (box_target's own way: --box-now asks for one now, else the rhythm's next one), the
            queue in its order re-found within QUEUE_MATCH_PX of its last foot, the box path's
            skips (the screen limit, in view, ignored box spots, --reach-check / --unreach-escape's
            unreachable, --far-approach's far boxes), the box's hover points hovered for a SWORD;
            on a pick ONE strike() (by "queue"), engaged as a box fight. True: struck (the caller
            ends the tick); False: today's path goes on (held, skipped, empty or failed)."""
            nonlocal lock, mode, goal_path, fight_t0, fight_ref
            assert boxes is not None
            due_ = bq_st["due"]
            state_ = bq_due_state(mode, lock is not None, sitting, due_["fly"] != fly_at,
                                  tick_ < boss_until, unread_active(), here is not None,
                                  bare is not None and (bare.busy or bare.pending is not None),
                                  hold_)  # fmt: skip
            if state_ == "hold":
                counts["queue_hold"] += 1  # a bare-steal swap first: the pick waits a tick
                return False
            bq_st["due"] = None
            if state_ != "go":
                counts["queue_" + state_.replace(":", "_")] += 1
                return False
            bw_ = boxes

            def detect_() -> list[Any] | None:
                t_q = time.monotonic()
                if a.box_now:
                    fresh_ = bw_.fresh_now(box_arm(a.box_detector, n_box_target[0]),
                                           BOX_TARGET_WAIT_S) is not None  # fmt: skip
                else:
                    fresh_ = bw_.wait_fresh(t_q, BOX_TARGET_WAIT_S)
                if not fresh_:
                    return None
                with bw_.lock:
                    return list(bw_.last[1])

            def accept_(foot_: tuple[float, float]) -> str | None:
                lim_ = BOX_SCREEN_PX if getattr(a, "engage_screen", False) else BOX_TARGET_PX
                if bq_d(foot_) > lim_:
                    return "far_px"
                if not in_view(foot_[0], foot_[1] - BODY_UP):
                    return "off"
                sp_ = box_spot(here, foot_)
                if box_spots is not None and sp_ is not None and box_spots.ignored(sp_):
                    return "spot"
                if unreachable(here, foot_):
                    return "unreachable"
                far_on = getattr(a, "far_approach", False) and here is not None
                if far_on and sp_ is not None and cheb2(sp_, here) >= APPROACH_CELLS:
                    return "far"  # box_target walks toward it first (today's path)
                return None

            def aim_(b_: Any) -> tuple[tuple[float, float] | None, list[str]]:
                pts_ = box_hover_points((b_.x0, b_.y0, b_.x1, b_.y1))
                vds_: list[str] = []
                for u_, v_ in pts_[: 1 if a.box_now else len(pts_)]:  # box_target's hovers
                    if not in_view(u_, v_):
                        vds_.append("off")
                        continue
                    vds_.append(str(hover(u_, v_)["verdict"]))
                    if vds_[-1] == "sword":
                        return (u_, v_), vds_
                return None, vds_

            got_ = bq_next(bq_st["q"], vt_values, detect_, accept_, aim_)
            e_, b_ = got_["entry"], got_.get("box")
            d_q = None if e_ is None else round(bq_d(e_.foot if b_ is None else bq_foot(b_)))
            rec_: dict[str, Any] = {"kind": "queue", "what": got_["what"], "n": got_["n"],
                                    "attacking": bool(e_ is not None and e_.attacking),
                                    "species": None if e_ is None else e_.species, "d_px": d_q,
                                    "gap_ms": round((time.monotonic() - float(due_["t"])) * 1e3),
                                    "why": got_["why"]}  # fmt: skip
            if "rank" in got_:
                rec_.update(rank=got_["rank"], moved_px=round(got_["moved_px"]),
                            verdicts=got_["verdicts"])  # fmt: skip
            counts[f"queue_{got_['what']}"] += 1
            if got_["what"] != "pick":
                ev(rec_)
                return False
            u_p, v_p = got_["point"]
            sp_p = box_spot(here, bq_foot(b_))
            rel_p = (0, 0) if sp_p is None or here is None else \
                (sp_p[0] - here[0], sp_p[1] - here[1])  # fmt: skip
            bq_st["q"] = [x_ for x_ in bq_st["q"] if x_ is not e_]  # it is the target now
            ev({**rec_, "rel": list(rel_p)})  # gap_ms: the fight's end -> this strike
            box_q = [round(float(x_), 1) for x_ in (b_.x0, b_.y0, b_.x1, b_.y1)]
            ev({"kind": "engage", "by": "queue", "name": None, "box": box_q,
                "spot": None if sp_p is None else list(sp_p)})  # fmt: skip
            box_fight.clear()  # a box fight, its box already tried (box_target's once per fight)
            box_fight.update({"spot": sp_p, "n0": n_strike[0], "box": box_q, "tried": True})
            mode, goal_path = "fight", None
            fight_t0 = time.monotonic()
            if fight_ref is None and here is not None:
                fight_ref = {"img": frame(), "here": here, "t": fight_t0}
            if strike(u_p, v_p, rel_p, "queue"):  # False: --walk-stop / --quick-drop / a swap
                lock = {"t": time.monotonic(), "rel": rel_p,
                        "cell": None if here is None else
                        [here[0] + rel_p[0], here[1] + rel_p[1]]}  # fmt: skip
            else:
                counts["queue_no_lock"] += 1
            return True

        def unread_active() -> bool:
            """9.22: an escape runs for THIS stale span (no fresh read, no Fly Wing since it came
            due): the search walk holds its clicks meanwhile. The pos_unread rule is checked on
            every tick that reaches the walk, so the escape ends there (by its backstop at the
            latest, UNREAD_MAX_S) -- never a walk click on the tick its wing is pressed."""
            return ust["t0"] is not None and ust["span"] == last_pos_t and ust["fly"] == fly_at

        def unread_held(now: float) -> bool:
            """--unread-step (dungeon@9.22, LF-4): called when the pos_unread rule would press the
            Fly Wing. True holds the wing this tick (a wait, or a step was clicked); False lets it
            go (the flag off, or LF-4's fallback: the escape is ended and logged first)."""
            nonlocal last_walk_click
            if not unread_step_on:
                return False
            if ust["t0"] is None or ust["span"] != last_pos_t or ust["fly"] != fly_at:
                ust.update(t0=now, span=last_pos_t, fly=fly_at, steps=0, step_t=-1e9, waits=set())
                counts["unread_step_due"] += 1
            mv = last_own_move(own_moves, fly_at)
            walk_t = walk_click_t(own_moves)
            act_u, why_u = unread_step_decide(now, ust["t0"], walk_t, ust["steps"], ust["step_t"],
                                              mv, here is not None)  # fmt: skip
            if act_u == "wait":
                if why_u not in ust["waits"]:  # one record per reason and escape
                    ust["waits"].add(why_u)
                    ev({"kind": "unread_step", "event": "wait", "why": why_u,
                        "age_s": round(now - (walk_t if why_u == "walk_sent" else ust["step_t"]),
                                       2),
                        "since_read_s": round(now - last_pos_t, 2)})  # fmt: skip
                return True
            if act_u == "wing":
                unread_end("wing", why=why_u)
                return False
            assert mv is not None and here is not None  # unread_step_decide's "step"
            rel_u = unread_step_rel(mv.rel)
            assert rel_u is not None  # last_own_move keeps rel != (0, 0)
            cands = unread_candidates(here, own_moves, last_pos_t, fly_at)
            dir_ = {"by": mv.by, "rel": list(mv.rel), "age_s": round(now - mv.t, 2)}
            why_safe = unread_step_safe(cands, rel_u, unread_forbid, unread_npcs, zones)
            if why_safe is not None:
                unread_end("refused", why=why_safe, rel=list(rel_u), dir=dir_,
                           cands=[list(c_) for c_ in cands])  # fmt: skip
                return False

            def on_self(c_: Cell) -> bool:
                u_s, v_s = project(None, [c_])[0]
                return in_self_box(u_s, v_s, FOOT_PX[0], FOOT_PX[1])

            # SCREEN-RELATIVE: the flat projection about her sprite at the screen centre (the
            # camera follows her) -- the held cell's terrain may be another spot's (p47: 11 off)
            verdicts: list[str] = []
            for c_u in unread_step_cells(rel_u, on_self):
                u_u, v_u = project(None, [c_u])[0]
                if not in_view(u_u, v_u):
                    verdicts.append("off")
                    continue
                res_u = hover(u_u, v_u)
                ring_u = int(res_u["ring"][0]) if res_u.get("noentry_ring") else 0
                act_w, why_w = wtr.decide(res_u["verdict"], ring_u, trusted=False, enabled=False,
                                          noentry_red=RING_IN_MIN)  # fmt: skip
                verdicts.append(why_w)
                if act_w != "click":  # only a CLEAR read: never a SWORD, a ring, an unknown
                    continue
                click_at(u_u, v_u, "unread_step")
                ust["steps"] += 1
                ust["step_t"] = last_walk_click = time.monotonic()  # the idle watchdog, settle
                counts["unread_step"] += 1
                ev({"kind": "unread_step", "event": "step", "n": ust["steps"], "rel": list(c_u),
                    "u": round(u_u, 1), "v": round(v_u, 1), "verdicts": verdicts, "dir": dir_,
                    "held": None if here is None else list(here),
                    "cands": [list(c_) for c_ in cands],
                    "since_read_s": round(now - last_pos_t, 2)})  # fmt: skip
                return True
            unread_end("refused", why="cursor", rel=list(rel_u), dir=dir_, verdicts=verdicts)
            return False

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
                    counts["loot_click"] += 1
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

        def kill_aim_set(t_k: float) -> None:
            """dungeon@9.32 (--loot-aim): at a kill, the nearest monster box's cell in the watcher's
            recent detections (aim_rel over AIM_GRID, projected from our cell; the newest that
            has one), kept for the loot step; nothing kept when no box is near her."""
            if boxes is None or here is None:
                return
            uv_a = project(here, AIM_GRID)
            rel_ = None
            for bx_ in boxes.recent(LOOT_AIM_AGE_S):  # newest first: the first detection with one
                rel_ = aim_rel(bx_, uv_a)
                if rel_ is not None:
                    break
            counts["loot_aim_set" if rel_ is not None else "loot_aim_none"] += 1
            if rel_ is not None:
                kill_aim[t_k] = (here[0] + rel_[0], here[1] + rel_[1])

        # --- --loot-recheck (dungeon@9.36, rogue-xmas02.md 4DA): the deferred item re-check -------

        def loot_fits(c: Cell) -> bool:
            """9.36: the loot step's plan filter -- on the map, walkable, outside the zones."""
            return bool(0 <= c[0] < ok.shape[1] and 0 <= c[1] < ok.shape[0]
                        and ok[c[1], c[0]] and not mz.in_no_enter(zones, c))  # fmt: skip

        def recheck_prune(tick_: float) -> None:
            """9.36 (bookkeeping only, every tick): a pending kill past RECHECK_S, or from before
            an escape (a Fly Wing, a boss / unreach walk-away, a house door click), leaves unseen
            -- its recheck_expired event (why "time" / "escape")."""
            esc_ = max(fly_at, house_click_t, max(boss_walks, default=-1e9),
                       max(ua_walks, default=-1e9))  # fmt: skip
            keep_, gone_ = recheck_split(rk_pending, tick_, esc_)
            for k_, why_ in gone_:
                counts[f"recheck_expired_{why_}"] += 1
                ev({"kind": "recheck_expired", "kill_age_s": round(tick_ - k_.t, 2), "why": why_,
                    "cell": list(k_.cell), "checks": k_.checks})  # fmt: skip
            rk_pending[:] = keep_

        def recheck_visit(c: Cell, rs: dict[str, Any]) -> str:
            """9.36: loot_step_v1's visit(), step for step, for the recheck (the loot step's own
            stays inside it, unchanged): the cell's ground point hovered; a SWORD engages
            ("fight": the loot step's strike and lock), a PICKUP hand is clicked (the walk there
            and the pickup, then a position read); "off" out of view; "escape" after a Fly Wing."""
            nonlocal here, lock, mode
            assert here is not None
            rel = (c[0] - here[0], c[1] - here[1])
            u, v = project(here, [rel])[0]
            rs["hovered"].append(c)
            if not in_view(u, v):
                return "off"
            rs["n_hov"] += 1
            res_r = hover(u, v)
            if guard_tick():
                return "escape"
            if res_r["verdict"] == "sword":
                ev({"kind": "engage", "by": "loot_sword", "name": None, "recheck": True})
                strike(u, v - BODY_UP, rel, "loot_sword")
                lock = {"t": time.monotonic(), "rel": rel, "cell": list(c)}
                mode = "fight"
                return "fight"
            if pickup_seen(res_r["rec"]):
                d_ = max(abs(rel[0]), abs(rel[1]))
                click_at(u, v, "loot")
                counts["loot_click"] += 1
                ev({"kind": "loot_click", "u": round(u, 1), "v": round(v, 1),
                    "rel": list(rel), "cell": list(c), "why": "recheck"})  # fmt: skip
                rs["picks"] += 1
                rs["looted"].append(c)
                time.sleep(0.45 + 0.2 * d_)  # the walk there and the pickup
                here = read_here() or c
            return "ok"

        def recheck_tick(tick_: float, calm_: bool) -> bool:
            """9.36 (--loot-recheck), in the main loop after the fight branch, before the AFTER
            block. While a kill is pending and she is calm (recheck_calm: hunting, no lock, the
            runner's calm, no hit for FIGHT_TAKEN_S, no boss window) and a detection is due
            (RECHECK_EVERY_S since the last, the loot step's included): the item model ONCE on a
            fresh frame. Items in a pending kill's cells -> those kills' cells looted the loot
            step's seen-items way (items_plan's order, recheck_visit, its caps: LOOT_MAX_PICKS,
            LOOT_MAX_HOVERS, LOOT_TRIM_HOVERS, LOOT_MAX_S, a hit in the last 1 s stops); the kills
            are done unless a fight / a hit stopped it (they stay pending). Never sleeps: not due
            -> nothing. True when it made input (the loop starts a fresh tick)."""
            nonlocal loot_settle_t, idle_since
            h_ = here  # (recheck_prune ran this tick, after its escapes: before the HUD send)
            if not rk_pending or h_ is None or item_det is None:
                return False
            if not recheck_calm(mode, lock is not None, calm_, tick_ - last_taken,
                                tick_ < boss_until):  # fmt: skip
                return False
            if not recheck_due(tick_, rk_st["last"]):
                return False
            t_s = time.monotonic()
            rk_st["last"] = t_s
            counts["recheck_checks"] += 1
            for k_ in rk_pending:
                k_.checks += 1
            try:
                found_r = item_rels_on(item_det.detect(frame()), project(h_, RECHECK_GRID),
                                       RECHECK_GRID)  # fmt: skip  # 4DA amendment: +-8 cells
            except Exception:  # noqa: BLE001 -- a failed detection: no recheck this time
                counts["recheck_fail"] += 1
                return False
            seen_r = [(h_[0] + dx_, h_[1] + dy_) for dx_, dy_ in found_r]
            hits_, order_r = recheck_plan(rk_pending, seen_r, loot_fits)
            if not hits_:
                return False
            rs: dict[str, Any] = {"hovered": [], "n_hov": 0, "picks": 0, "looted": []}
            end_ = "done"
            while rs["picks"] < LOOT_MAX_PICKS and len(rs["hovered"]) < LOOT_MAX_HOVERS and not (
                    loot_trim and rs["n_hov"] >= LOOT_TRIM_HOVERS):  # fmt: skip
                todo_ = [c_ for c_ in order_r if c_ not in rs["hovered"]]
                if not todo_ or time.monotonic() - t_s > LOOT_MAX_S:
                    break
                if time.monotonic() - last_taken < 1.0:
                    end_ = "hit"
                    break
                got_r = recheck_visit(todo_[0], rs)
                if got_r in ("fight", "escape"):
                    end_ = got_r
                    break
            end_, done_ = recheck_outcome(end_, rs["picks"], rs["n_hov"])
            if done_:  # a fight / a hit yields: those kills stay pending until they expire
                rk_pending[:] = [k_ for k_ in rk_pending if k_ not in hits_]
            counts[f"recheck_{end_}"] += 1
            counts["recheck_picks"] += rs["picks"]
            if rs["picks"] and getattr(a, "kill_gap", False):
                loot_settle_t = time.monotonic()  # 9.13d: the next walk waits for a fresh read
            if rs["n_hov"]:
                idle_since = time.monotonic()  # Amendment E: a loot is activity, never idle
            ev({"kind": "recheck", "kill_age_s": round(t_s - hits_[0].t, 2),
                "kills": [[list(k_.cell), round(t_s - k_.t, 2), k_.checks] for k_ in hits_],
                "seen": [list(c_) for c_ in seen_r], "hover": [list(c_) for c_ in order_r],
                "hovered": [list(c_) for c_ in rs["hovered"]],
                "looted": [list(c_) for c_ in rs["looted"]], "picks": rs["picks"],
                "hovers": rs["n_hov"], "end": end_, "pending": len(rk_pending),
                "path": getattr(item_det, "last_path", None),
                "ms": round((time.monotonic() - t_s) * 1e3)})  # fmt: skip
            return bool(rs["n_hov"]) or end_ in ("fight", "escape")

        # --- --loot-memory (dungeon@9.37, rogue-xmas02.md 4DB): the item model looks in fights --

        def memory_kill(cell_k: Cell, t_k: float) -> None:
            """9.37 (bookkeeping only): a kill (both kill sites, where the loot list grows) -- the
            item model looks at its 5 x 5 cells for MEMORY_S."""
            lm_kills.append(PendingKill(cell_k, t_k))
            counts["memory_kills"] += 1

        def memory_prune(tick_: float) -> None:
            """9.37 (bookkeeping only, every tick): a kill leaves the looks at MEMORY_S (or at an
            escape after it, as recheck_split); a remembered cell leaves MEMORY_KEEP_S after its
            last sighting (why "time"), or when last seen before an escape (a Fly Wing, a boss /
            unreach walk-away, a house door click: "escape") -- its memory_expired event."""
            esc_t = max(fly_at, house_click_t, max(boss_walks, default=-1e9),
                        max(ua_walks, default=-1e9))  # fmt: skip
            lm_kills[:] = recheck_split(lm_kills, tick_, esc_t, MEMORY_S)[0]
            keep_m, old_m, esc_m = memory_expire(lm_mem, tick_, esc_t)
            for why_, cells_ in (("time", old_m), ("escape", esc_m)):
                if cells_:
                    counts[f"memory_expired_{why_}"] += len(cells_)
                    ev({"kind": "memory_expired", "cells": len(cells_), "why": why_,
                        "list": [list(c_) for c_ in cells_]})  # fmt: skip
            if old_m or esc_m:
                lm_mem.clear()
                lm_mem.update(keep_m)

        def memory_look(tick_: float) -> None:
            """9.37 (--loot-memory), every tick from the main loop BEFORE the fight branch, so it
            runs in any mode (search, fight, after, a walk to rest) but sitting: while a kill is
            younger than MEMORY_S and a look is due (MEMORY_EVERY_S since the last one, the loot
            step's detection included), the item model ONCE on a fresh frame, mapped over
            RECHECK_GRID (+-8 cells) from her current cell; the item cells inside a young kill's
            cells are remembered (memory_remember). It only looks: no click, no hover, no sleep;
            not due -> nothing. A memory_look event only when a cell is NEWLY remembered."""
            h_ = here
            if h_ is None or item_det is None:
                return
            if not memory_look_due(tick_, lm_st["last"], lm_kills, sitting):
                return
            t_l = time.monotonic()
            lm_st["last"] = t_l
            counts["memory_looks"] += 1
            try:
                found_m = item_rels_on(item_det.detect(frame()), project(h_, RECHECK_GRID),
                                       RECHECK_GRID)  # fmt: skip
            except Exception:  # noqa: BLE001 -- a failed detection: no look this time
                counts["memory_fail"] += 1
                return
            ms_l = round((time.monotonic() - t_l) * 1e3)  # the frame's wait + the model's call
            seen_m = [(h_[0] + dx_, h_[1] + dy_) for dx_, dy_ in found_m]
            mem_, new_, kept_ = memory_remember(lm_mem, seen_m, lm_kills, t_l, loot_fits)
            lm_mem.clear()
            lm_mem.update(mem_)
            counts["memory_new"] += len(new_)
            counts["memory_kept"] += len(kept_)
            counts[f"memory_looks_{mode}"] += 1  # where it looked (p94's recheck: search only)
            counts["memory_look_ms"] += ms_l  # the time the looks took from the loop, in all
            path_ = getattr(item_det, "last_path", None)
            if path_:
                counts[f"memory_path_{path_}"] += 1
            if new_:
                ev({"kind": "memory_look", "seen": [list(c_) for c_ in seen_m],
                    "new": [list(c_) for c_ in new_], "kept": len(kept_), "memory": len(lm_mem),
                    "mode": mode, "kills": len(lm_kills), "at": list(h_), "path": path_,
                    "ms": ms_l})  # fmt: skip

        def memory_tick(tick_: float, calm_: bool) -> bool:
            """9.37 (--loot-memory), in the main loop after the fight branch, before the AFTER
            block (beside 9.36's hook): no kill came, she is calm (9.36's recheck_calm: hunting,
            no lock, the runner's calm, no hit for FIGHT_TAKEN_S, no boss window) and remembered
            cells are left -> they are looted 9.36's way (memory_merge's order, recheck_visit, the
            loot step's caps: LOOT_MAX_PICKS, LOOT_MAX_HOVERS, LOOT_TRIM_HOVERS, LOOT_MAX_S, a hit
            in the last 1 s stops). The cells it hovered are done; the rest stay. No detection, no
            sleep of its own. True when it made input (the loop starts a fresh tick)."""
            nonlocal loot_settle_t, idle_since
            h_ = here
            if not lm_mem or h_ is None:
                return False
            if not recheck_calm(mode, lock is not None, calm_, tick_ - last_taken,
                                tick_ < boss_until):  # fmt: skip
                return False
            t_s = time.monotonic()
            order_m, rem_m = memory_merge([], lm_mem, h_)
            rs: dict[str, Any] = {"hovered": [], "n_hov": 0, "picks": 0, "looted": []}
            end_ = "done"
            while rs["picks"] < LOOT_MAX_PICKS and len(rs["hovered"]) < LOOT_MAX_HOVERS and not (
                    loot_trim and rs["n_hov"] >= LOOT_TRIM_HOVERS):  # fmt: skip
                todo_ = [c_ for c_ in order_m if c_ not in rs["hovered"]]
                if not todo_ or time.monotonic() - t_s > LOOT_MAX_S:
                    break
                if time.monotonic() - last_taken < 1.0:
                    end_ = "hit"
                    break
                got_m = recheck_visit(todo_[0], rs)
                if got_m in ("fight", "escape"):
                    end_ = got_m
                    break
            end_ = recheck_outcome(end_, rs["picks"], rs["n_hov"])[0]
            kept_m = memory_clear(lm_mem, rs["hovered"])
            n_done = len(lm_mem) - len(kept_m)
            lm_mem.clear()
            lm_mem.update(kept_m)
            counts[f"memory_calm_{end_}"] += 1
            counts["memory_picks"] += rs["picks"]
            counts["memory_visited"] += n_done
            if rs["picks"] and getattr(a, "kill_gap", False):
                loot_settle_t = time.monotonic()  # 9.13d: the next walk waits for a fresh read
            if rs["n_hov"]:
                idle_since = time.monotonic()  # Amendment E: a loot is activity, never idle
            ev({"kind": "memory_loot", "remembered": [list(c_) for c_ in rem_m],
                "hover": [list(c_) for c_ in order_m],
                "hovered": [list(c_) for c_ in rs["hovered"]],
                "looted": [list(c_) for c_ in rs["looted"]], "picks": rs["picks"],
                "hovers": rs["n_hov"], "end": end_, "done": n_done, "left": len(lm_mem),
                "ms": round((time.monotonic() - t_s) * 1e3)})  # fmt: skip
            return bool(rs["n_hov"]) or end_ in ("fight", "escape")

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
                    counts["loot_click"] += 1
                    ev({"kind": "loot_click", "u": round(u, 1), "v": round(v, 1),
                        "rel": list(rel), "cell": list(c), "why": why})  # fmt: skip
                    picks += 1
                    time.sleep(0.45 + 0.2 * d_)  # the walk there and the pickup
                    here = read_here() or c
                return "ok"

            seen_items: list[Cell] | None = None  # dungeon@9.33 (--loot-items): None = not asked
            order_items: list[Cell] = []
            if item_det is not None:
                try:
                    found_i = item_rels(item_det.detect(frame()), project(here, ITEM_GRID))
                    seen_items = [(here[0] + dx_, here[1] + dy_) for dx_, dy_ in found_i]
                except Exception:  # noqa: BLE001 -- a failed detection: today's trim sweep
                    counts["loot_items_fail"] += 1
                if seen_items is not None:
                    order_items = items_plan(seen_items, plan)
                    out_["items"] = {"seen": [list(c_) for c_ in seen_items],
                                     "hover": [list(c_) for c_ in order_items],
                                     "path": getattr(item_det, "last_path", None)}  # fmt: skip
                    # dungeon@9.37 (--loot-memory, 4DB): the remembered cells after its own
                    # items; with none of its own it visits them (never "no_items" while any)
                    if lm_on and lm_mem:
                        n_own = len(order_items)
                        order_items, lm_rem = memory_merge(order_items, lm_mem, here)
                        out_["items"]["hover"] = [list(c_) for c_ in order_items]
                        out_["items"]["remembered"] = [list(c_) for c_ in lm_rem]
                        counts["memory_merged"] += 1
                        if not n_own:
                            counts["memory_rescued"] += 1
                    if not order_items:  # nothing near the kills: no hover at all
                        counts["loot_items_skip"] += 1
                        ms_i = round((time.monotonic() - t_s) * 1e3)
                        ev({**out_, "hovered": 0, "hovers": 0, "trim": loot_trim, "picks": 0,
                            "end": "no_items", "ms": ms_i})  # fmt: skip
                        return "done"
                    counts["loot_items_seen"] += 1
            aims: list[Cell] = []  # dungeon@9.32 (--loot-aim)
            cap_aim: int | None = None
            if loot_aim and seen_items is None:
                fresh_k = [t_ for _g, t_ in lst if t_s - t_ <= 55.0]
                aims = [kill_aim[t_] for t_ in fresh_k if t_ in kill_aim]
                cap_aim = aim_cap(len(fresh_k), len(aims))
                out_["aim"] = {"aims": [list(c_) for c_ in aims], "kills": len(fresh_k),
                               "cap": cap_aim}  # fmt: skip
            end = "done"
            while picks < LOOT_MAX_PICKS and len(hovered) < LOOT_MAX_HOVERS and not (
                    loot_trim and n_hov >= LOOT_TRIM_HOVERS):  # fmt: skip
                todo = sorted(plan - hovered, key=lambda c: (cheb2(c, here), c))
                if aims:  # 9.32: the aimed cells first, then their neighbours
                    todo = aim_order(todo, aims)
                if seen_items is not None:  # 9.33: only the seen items' cells, in their order
                    todo = [c for c in order_items if c not in hovered]
                if cap_aim is not None and n_hov >= cap_aim:
                    counts["loot_aim_capped"] += 1
                    break
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
            # dungeon@9.37 (--loot-memory): every remembered cell it visited (hovered) is done
            if lm_on and lm_mem:
                kept_lm = memory_clear(lm_mem, hovered)
                out_["memory_done"] = len(lm_mem) - len(kept_lm)
                counts["memory_visited"] += out_["memory_done"]
                lm_mem.clear()
                lm_mem.update(kept_lm)
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
                img_meta = frame_meta[0]  # 9.21 (LF-2): the frame this tick reads
                pct = hpp.read(img, glyphs)
                spp = hpp.read(img, glyphs, hpp.SP_DY)
                if stock_watch is not None and stock_due:  # dungeon@8.4: the stock after a press
                    out_item = None
                    keep_n: int | None = None  # dungeon@9.35: the Fly Wings kept for the end
                    for item_ in [i for i, t_ in stock_due.items() if tick >= t_]:
                        n_ = hb.read_count(hb.gray(img), stock_watch[1][item_], stock_watch[0])
                        stock_tries[item_] = stock_tries.get(item_, 0) + 1
                        if n_ is None and stock_tries[item_] < STOCK_TRIES:
                            stock_due[item_] = tick + STOCK_READ_S  # the teleport's dark frames
                            continue
                        del stock_due[item_]
                        ev({"kind": "stock", "item": item_, "count": n_,
                            "tries": stock_tries[item_]})  # fmt: skip
                        if heal_candy and item_ in heal_left:  # dungeon@9.31: the heal items end
                            heal_left[item_] = n_  # the run only when every one reads 0
                            if out_item is None and heal_out(heal_left):
                                out_item = item_
                        elif out_item is None and stock_out({item_: n_}) is not None:
                            out_item = item_
                        if player and player_wings_low(item_, n_):  # dungeon@9.35
                            keep_n = n_
                    if out_item is not None:  # no escape (or no potion) left: end, warp home
                        reason = f"stock_out: item {out_item} reads 0 on the hotbar"
                        break
                    if keep_n is not None:  # dungeon@9.35: no warp takes a player home, so her
                        # last Fly Wing(s) stay for the end's own escape: the run ends here
                        reason = f"stock_keep: {keep_n} Fly Wing(s) left, kept for the end"
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
                pos, held = pos_ok.check(tick, rd) if rd is not None else (None, None)
                lf_rec: dict[str, Any] = {}  # LF-1 (logging only, always): the held-back read
                if held is not None:
                    dt_h = None if held.dt is None else round(held.dt, 2)
                    lf_rec = {"held": list(held.cell), "held_dt": dt_h}
                if late_confirm_on and held is not None:  # 9.21 (LF-2): a newer frame confirms
                    pos, lf2_ = late_confirm(pos_ok, held, img_meta, newer_readout, read_readout,
                                             time.monotonic)  # fmt: skip
                    if lf2_ is not None:
                        lf_rec.update(lf2_)
                        counts[f"late_confirm_{lf2_['lf2']}"] += 1
                rd_why = read_outcome(rd, pos)
                if pos is not None:
                    p_ = pos
                    if (here is not None and is_jump(here, p_, tick - last_pos_t)
                            and tick - fly_at > FLY_JUMP_S):  # fmt: skip
                        ev({"kind": "jump", "from": list(here), "to": list(p_),
                            "since_s": round(tick - last_pos_t, 2)})  # fmt: skip
                        reason = "hard_bar: position jump (map change?)"
                        break
                    if ust["t0"] is not None:  # 9.22 (--unread-step): (c) a fresh read, no wing
                        unread_end("fresh", at=list(p_), held=None if here is None else list(here))
                    here, last_pos_t = p_, tick
                    if house_on:
                        pos_hist.append((tick, p_))
                ev({"kind": "hp_read", "pct": pct, "sp_pct": spp, "dead": dead, "ag_on": ag_on,
                    "dark": dark, "pos": None if here is None else list(here),
                    "here_age_s": round(tick - last_pos_t, 2), **lf_rec,
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
                boss_hit: str | None = None
                for ln in new:
                    if bosses and ln.get("type") in ("damage", "taken"):  # the boss guard
                        boss_hit = boss_of(ln.get("name_read"), bosses, map_species) or boss_hit
                    typ = ln.get("type")
                    if typ == "taken":
                        last_taken = tick
                        taken_new = taken_new or ln
                    elif typ == "damage":
                        last_ours = tick
                        ours_ticks.append(tick)
                    elif typ == "base_exp" or (exp_first and typ == "job_exp"):
                        if exp_first:  # dungeon@9.34: EXP / Job EXP = dead, one kill per pair
                            if not exp_seen:
                                ev({"kind": "exp_seen", "line": typ})
                            exp_seen = True
                            new_kill, exp_pair = exp_kill(typ, tick, exp_pair)
                            if not new_kill:
                                counts["exp_pair"] += 1
                                continue
                        kills_seen.append(tick)
                        ev({"kind": "kill", "by": "exp_line", "line": typ, "gm": None
                            if here is None else list(here)})  # fmt: skip
                        if here is not None:  # the loot list: the 5 x 5 around us at this death
                            loot_list.append((here, tick))
                            if loot_aim:  # dungeon@9.32: the nearest box's cell at this death
                                kill_aim_set(tick)
                            if rk_on:  # dungeon@9.36: its cells stay pending for a late drop
                                rk_pending.append(PendingKill(here, tick))
                            if lm_on:  # dungeon@9.37: the item model looks at its cells
                                memory_kill(here, tick)
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
                if unreach_on and dropped:
                    ua_drop_t = tick  # dungeon@9.26: an attacked sign
                near_ = None
                if boss_hit is None and getattr(a, "garm_fly", False) and boxes is not None:
                    streak_ = boxes.alarm_n  # 9.19b: --garm-confirm's consecutive detections
                    seen_ = alarm_seen(
                        boxes.alarm, tick, streak=streak_, need=a.garm_confirm
                    )  # dungeon@9.19: a Garm Baby IN VIEW
                    if seen_ is not None:
                        ev({"kind": "garm_seen", "cls": seen_.cls,
                            "score": round(float(seen_.score), 3),
                            "box": [round(float(v_), 1) for v_ in
                                    (seen_.x0, seen_.y0, seen_.x1, seen_.y1)],
                            "age_s": round(tick - boxes.alarm[0], 2),
                            "streak": streak_})  # fmt: skip
                        counts["garm_seen"] += 1
                        boss_hit = "Garm Baby"  # the boss guard's own Fly Wing path below
                if boss_hit is not None and tick < boss_grace_until:
                    counts["boss_walk_grace"] += 1  # 9.18: the dog's last hit as we walk off
                    boss_hit = None
                if boss_hit is not None:  # --engage-screen's boss guard (Amendment J): fly away
                    ev({"kind": "boss_guard", "name": boss_hit, "fly": tick - fly_at > 2.0})
                    counts["boss_guard"] += 1
                    boss_until = tick + BOSS_AVOID_S
                    wa_: Cell | None = None
                    if boss_walk_on and here is not None and not sitting and boss_walk_allowed(
                            boss_hit, boss_only, boss_walks, tick):  # fmt: skip
                        # dungeon@9.18 (Batt): walk away from a summon when we can

                        def wa_fits(c_: Cell, h: Cell = here) -> bool:
                            hh, ww = okr.shape
                            if not (0 <= c_[0] < ww and 0 <= c_[1] < hh) or not okr[c_[1], c_[0]]:
                                return False
                            if (
                                carved[c_[1], c_[0]]
                                or mz.segment_violates(h, c_, zones) is not None
                            ):
                                return False
                            u_, v_ = project(h, [(c_[0] - h[0], c_[1] - h[1])])[0]
                            if not in_view(u_, v_):
                                return False
                            return walk_pick_ok(picked_cell(camera, gat, h, (u_, v_)), c_, okr)

                        def wa_reach(c_: Cell, h: Cell = here) -> bool:
                            from poring_dataset import walk as wkp_w

                            return bool(wkp_w.click_walk_ok(walk_grid, h[0], h[1], c_[0], c_[1]))

                        wa_ = walk_away_target(here, wa_fits, wa_reach)
                    if wa_ is not None and here is not None:
                        u_w, v_w = project(here, [(wa_[0] - here[0], wa_[1] - here[1])])[0]
                        if bare is not None:
                            bare.escape()  # dungeon@9.27: never walk away bare
                        click_at(u_w, v_w, "walk")
                        note_move((wa_[0] - here[0], wa_[1] - here[1]), "boss_walk")  # 9.22
                        boss_walks.append(tick)
                        boss_grace_until = tick + BOSS_WALK_GRACE_S
                        last_walk = tick + BOSS_WALK_GRACE_S  # no other walk click meanwhile
                        counts["boss_walk"] += 1
                        n_w = sum(1 for t in boss_walks if tick - t < BOSS_WALK_WINDOW_S)
                        ev({"kind": "boss_walk", "name": boss_hit, "from": list(here),
                            "to": list(wa_), "n_window": n_w})  # fmt: skip
                        lock, goal_path = None, None
                        loot_list, fight_ref = [], None
                        mode = "search"
                        box_fight.clear()
                        continue
                    if tick - fly_at > 2.0:
                        if sitting:
                            press("stand", "boss")
                            sitting = False
                        press("fly", "boss")
                        fly_at = time.monotonic()
                        lock, goal_path = None, None
                        loot_list, fight_ref = [], None
                        mode = "search"
                        here, last_taken = None, -1e9
                        box_fight.clear()
                        time.sleep(1.0)
                        continue
                if (boxes is not None and mode != "fight" and not sitting
                        and tick >= boss_until):  # a box never  # fmt: skip
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

                    if getattr(a, "engage_screen", False):  # dungeon@9.7: any box on the screen

                        def skip_s(foot: Sequence[float], here_s: Cell | None = here_b) -> bool:
                            return (skip_b(foot) or not in_view(foot[0], foot[1] - BODY_UP)
                                    or unreachable(here_s, foot))  # fmt: skip

                        near_ = boxes.near(FOOT_PX, BOX_SCREEN_PX, BOX_FRESH_S, skip_s)
                    else:
                        near_ = boxes.near(FOOT_PX, BOX_NEAR_PX, BOX_FRESH_S, skip_b)
                if near_ is not None and not (hit_now or dropped or swing_now) \
                        and box_engage_held(loot_first_on, mode, bool(loot_list)):  # fmt: skip
                    counts["loot_first_held"] += 1  # 9.16 part 1: ticks a box waited
                    near_ = None
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
                    fight_t0 = tick  # 9.16 part 2
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
                if rk_on and rk_pending:  # dungeon@9.36: the pending kills age out every tick
                    recheck_prune(tick)
                # dungeon@9.37 (--loot-memory, 4DB): the memory ages out every tick; while a kill
                # is young the item model LOOKS -- here, BEFORE the fight branch, so in any mode
                # (search, fight, after) but sitting; no click, no sleep; not due -> nothing
                if lm_on:
                    memory_prune(tick)
                    if lm_kills and not sitting:
                        memory_look(tick)
                if hud_tx is not None and boxes is not None:  # dungeon@9.29: DISPLAY ONLY
                    hud_send(hud_tx, boxes, mode, lock is not None)
                if bare is not None:  # dungeon@9.27: a pending read-back, a target's end, the cues
                    bare.tick(tick, lock is not None, mode == "fight", img, frac)
                # --- FIGHT: locked, or scan for the attacker
                if mode == "fight":
                    if q_on and boxes is not None:  # dungeon@9.30 (--queue): bookkeeping only
                        if bq_st["due"] is not None:  # a held pick (a swap's tick): a hit / a box
                            counts["queue_skip_fight"] += 1  # started the next fight first
                        bq_st["due"] = None  # a fight runs: no pick is due
                        q_book(taken_new is not None or last_swing == tick or dropped)
                    if lock is not None:
                        if swap_gap and bare is not None and bare.swap_t > last_ours:  # 9.27e
                            last_ours = bare.swap_t  # a swap restarts the no-hit clocks
                        since = tick - lock["t"]
                        idle = tick - max(last_ours, lock["t"])
                        # dungeon@9.34: once the client printed an exp line, it says the kill:
                        # no hit count, so --kill-gap infers none (exp lines first, Batt 11-12)
                        n_lock = (sum(1 for t_o in ours_ticks if t_o >= lock["t"])
                                  if getattr(a, "kill_gap", False) and not exp_seen
                                  else 0)  # fmt: skip
                        if getattr(a, "kill_gap", False) and kill_gapped(n_lock, tick - last_ours):
                            # dungeon@9.13: our hits stopped -> taken as the kill (no exp line)
                            ev({"kind": "unlock", "why": "kill_gap", "s": round(since, 1),
                                "hits": n_lock, "gap_s": round(tick - last_ours, 2)})  # fmt: skip
                            kills_seen.append(tick)
                            ev({"kind": "kill", "by": "hit_gap", "gm": None if here is None
                                else list(here)})  # fmt: skip
                            if here is not None:  # the loot list, as for an exp line's kill
                                loot_list.append((here, tick))
                                if loot_aim:  # dungeon@9.32: the nearest box's cell here
                                    kill_aim_set(tick)
                                if rk_on:  # dungeon@9.36: its cells stay pending, as above
                                    rk_pending.append(PendingKill(here, tick))
                                if lm_on:  # dungeon@9.37: looked at, as above
                                    memory_kill(here, tick)
                            if mr and lock.get("cell"):  # it died: off the queue
                                queue[:] = [q for q in queue
                                            if list(q["cell"]) != list(lock["cell"])]  # fmt: skip
                            lock = None
                        elif since > LOCK_MAX_S or (since > LOCK_NO_HIT_S and idle > LOCK_NO_HIT_S):
                            ev({"kind": "unlock", "why": "no hits" if since <= LOCK_MAX_S
                                else "max", "s": round(since, 1)})  # fmt: skip
                            if unreach_on and since <= LOCK_MAX_S:  # dungeon@9.26 (Study S-UA)
                                ua_locks.append(ua_lock(lock, tick))
                                tr_u = unreach_trigger(ua_locks, ours_ticks)
                                if tr_u is not None:  # an unreachable attacker: get away
                                    ua_locks.clear()
                                    act_u = unreach_escape(tr_u, tick)
                                    lock, goal_path = None, None
                                    loot_list, fight_ref = [], None
                                    mode = "search"
                                    box_fight.clear()
                                    if act_u == "fly":
                                        fly_at = time.monotonic()
                                        here, last_taken = None, -1e9
                                        time.sleep(1.0)
                                    else:  # no other walk click meanwhile
                                        last_walk = tick + UNREACH_GRACE_S
                                    continue
                            lock = None
                        elif getattr(a, "quick_drop", False) and last_strike and quick_no_hit(
                                last_strike.get("arrow_t"), last_ours, last_strike["t_click"],
                                tick, last_strike.get("hit_s", QUICK_HIT_S)):  # fmt: skip
                            ev({"kind": "unlock", "why": "quick", "s": round(since, 1)})
                            lock = None
                            last_strike.clear()
                            quick_rearm("no_hit")
                    quiet = tick - last_taken > FIGHT_TAKEN_S and not hp_dropped(st.hist, tick)
                    if lock is None and quiet and quiet_kill_ends(kills_seen, tick, fight_t0,
                                                                  loot_first_on):  # fmt: skip
                        # pilot 4: after a kill with no hit for 2.5 s, rings 1 + 2 took 8.6 s to
                        # find nobody -- end the fight; the loot step's hovers still see a SWORD
                        mode, swing_floor = "after", tick
                        ev({"kind": "fight_end", "kills": len(kills_seen), "why": "quiet kill"})
                        if kill_gap_no_miss(getattr(a, "kill_gap", False), box_fight):
                            box_fight.clear()  # dungeon@9.13b: never looked at -> not a miss
                        else:
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
                    approaching = (getattr(a, "far_approach", False)
                                   and tick - float(box_fight.get("approach_t", -1e9))
                                   < APPROACH_HOLD_S)  # fmt: skip
                    if lock is None and not approaching:  # dungeon@9.10: no scan mid-approach
                        if quiet_scan_on and not scan_needed(
                                tick, last_taken, last_ours, last_swing,
                                hp_dropped(st.hist, tick)):  # fmt: skip
                            counts["quiet_scan_skip"] += 1  # 9.17: no damage in 5 s
                            found = None
                        else:
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
                # dungeon@9.36 (--loot-recheck): a late drop in a pending kill's cells, while calm
                if rk_on and rk_pending and recheck_tick(tick, calm):
                    continue  # it hovered (or a fight began): a fresh tick reads the signs first
                # dungeon@9.37 (--loot-memory): no kill came, she is calm, remembered cells left
                if lm_on and lm_mem and memory_tick(tick, calm):
                    continue  # it hovered (or a fight began): a fresh tick reads the signs first
                # --- AFTER a fight: loot, then rest or search
                if mode == "after":
                    queue.clear()
                if mode == "after" and (loot_list or fight_ref is not None):
                    clicks0_ = counts["loot_click"]
                    got_ = loot_step(loot_list, fight_ref)
                    if rk_on:  # dungeon@9.36: the loot step just asked the item model (with a
                        rk_st["last"] = time.monotonic()  # position): the recheck waits its 1 s
                    if lm_on:  # dungeon@9.37: the loot step just asked the item model: the
                        lm_st["last"] = time.monotonic()  # next look waits its 1 s
                    if getattr(a, "kill_gap", False) and counts["loot_click"] > clicks0_:
                        loot_settle_t = time.monotonic()  # 9.13d: wait for a fresh position
                    idle_since = time.monotonic()
                    if got_ == "fight":
                        continue
                    loot_list, fight_ref = [], None
                    empty_cells.clear()  # loot v2: a new fight series starts clean
                if q_on and mode == "after":  # dungeon@9.30 (--queue): the fight and its loot step
                    bq_st["due"] = {"t": swing_floor, "fly": fly_at}  # ended: a pick is due
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
                # dungeon@9.27b (--bare-ready): the dagger comes off while IDLE -- right after the
                # loot step (this tick's "after" became "search" above), after a fight with
                # nothing to loot, or on any search tick (bare_idle, BareCtl.ready_tick)
                ready_hold = False  # True: the idle unequip waits for the settle (no walk click)
                if bare is not None and bare.ready:
                    got_r = bare.ready_tick(
                        tick,
                        bare_idle(mode, lock is not None, sitting, here is not None,
                                  tick - fly_at, tick < boss_until, unread_active()),
                        tick - last_click_t[0] >= BARE_READY_SETTLE_S, frac)  # fmt: skip
                    if got_r == "swap":
                        continue  # the swap took ~2 s: a fresh tick reads the fight signs first
                    ready_hold = got_r == "hold"
                # dungeon@9.30 (--queue): the next target from the fight's queue, AFTER its loot
                # step and the rest decision and --bare-ready's idle swap, BEFORE the search walk
                if q_on and bq_st["due"] is not None and queue_next(tick, ready_hold):
                    continue  # struck: a fresh tick reads the fight's signs first
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
                    if patrol and explore_on:
                        goal = explore_goal(here)
                    elif patrol:
                        goal = patrol_goal(here)
                    elif not area[here[1], here[0]]:  # dungeon@4: a rest spot outside the area
                        goal = nearest_in(area & ~carved, here)
                    else:
                        goal = hf.heading_goal(area & ~carved, here, walk_st, rng)
                    goal_path = None if goal is None else route(okr, carved, here, goal)
                    if patrol and explore_on and goal is not None and goal_path is None:
                        explore_block(here)
                    elif patrol and goal is not None and goal_path is None:
                        skip_waypoint(here)  # carved off: the next waypoint ahead
                    elif goal_path:
                        wp_st["skips"] = 0
                    wp_st["through"] = None
                    ni_ = (None if not patrol or explore_on
                           else mroutes.next_index(rt, wp_st["i"]))  # fmt: skip
                    if a.walk_through and ni_ is not None and goal is not None and goal_path:
                        ext_ = through_path(goal_path, route(okr, carved, goal, wps[ni_]))
                        if len(ext_) > len(goal_path):  # a path's last waypoint: no extension
                            goal_path, wp_st["through"] = ext_, goal
                    ev({"kind": "goal", "to": None if goal is None else list(goal),
                        "len": None if goal_path is None else len(goal_path),
                        "turn": walk_st.get("turn"),
                        "wp": None if not patrol else wp_st["i"]})  # fmt: skip
                # 9.22 (--unread-step): no search walk click while a pos_unread escape runs
                if mode in ("search", "rest") and here is not None and goal_path \
                        and tick - last_walk >= a.walk_every and not unread_active() \
                        and not ready_hold \
                        and not loot_settling(loot_settle_t, last_pos_t, tick):  # fmt: skip
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

                        def fits_plain(c: Cell, h: Cell = here) -> bool:
                            u_, v_ = project(h, [(c[0] - h[0], c[1] - h[1])])[0]
                            return in_view(u_, v_) and mz.segment_violates(h, c, zones) is None

                        def fits(c: Cell, h: Cell = here) -> bool:
                            if not fits_plain(c, h):
                                return False
                            if getattr(a, "walk_pick", False):  # dungeon@9.15
                                u_, v_ = project(h, [(c[0] - h[0], c[1] - h[1])])[0]
                                pc_ = picked_cell(camera, gat, h, (u_, v_))
                                if not walk_pick_ok(pc_, c, okr):
                                    counts["walk_pick_skip"] += 1
                                    return False
                            return True

                        ahead_ = MR_WALK_AHEAD if mr else a.walk_ahead
                        wt_ = walk_target(goal_path, ahead_, fits)
                        pick_how = None  # the walk event's record of a fallback
                        if wt_ is None and getattr(a, "walk_pick_step", False):
                            # dungeon@9.15c (4AU): the pickable one-click step nearest the goal

                            def fits_q(c_: Cell, h: Cell = here) -> bool:
                                if not fits_plain(c_, h):
                                    return False
                                u_, v_ = project(h, [(c_[0] - h[0], c_[1] - h[1])])[0]
                                return walk_pick_ok(picked_cell(camera, gat, h, (u_, v_)), c_, okr)

                            def reach_w(c_: Cell, h: Cell = here) -> bool:
                                from poring_dataset import walk as wkp_

                                return bool(wkp_.click_walk_ok(step_grid, h[0], h[1], c_[0], c_[1]))

                            free_ = np.asarray(okr, dtype=bool) & ~np.asarray(carved, dtype=bool)
                            st_ = pick_step(here, grid_steps(free_, goal_path[-1], until=[here]),
                                            fits_q, reach_w)  # fmt: skip
                            if st_ is not None:
                                counts["walk_pick_step"] += 1
                                wt_, pick_how = (1, st_), "step"
                        if wt_ is None and getattr(a, "walk_pick", False):
                            # dungeon@9.15b (p34: 45 s with no click at 143,118 -> an idle Fly
                            # Wing): no cell passed the pick check -> today's click; the stall
                            # / carve path handles a dropped one
                            wt_ = walk_target(goal_path, ahead_, fits_plain)
                            if wt_ is not None:
                                counts["walk_pick_fallback"] += 1
                                pick_how = "plain"
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
                                    # (9.17: only after damage in the last 5 s -- the Miss cue
                                    # reads the misses now)
                                    if quiet_scan_on and not scan_needed(
                                            tick, last_taken, last_ours, last_swing,
                                            hp_dropped(st.hist, tick)):  # fmt: skip
                                        counts["quiet_scan_skip_stall"] += 1
                                        found = None
                                    else:
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
                                note_move(rel, "walk")  # 9.22: the way she came
                                rec_w = {"kind": "walk", "from": list(here), "to": list(c),
                                         "clicked": True, "why": mode, "red": res.get("red"),
                                         "ring": res.get("ring")}  # fmt: skip
                                if dodge is not None:
                                    rec_w["dodge"] = dodge
                                if pick_how is not None:  # 9.15b / 9.15c: which fallback
                                    rec_w["pick"] = pick_how
                                if why_w == "trusted":  # --walk-trust: an UNKNOWN read, clicked
                                    counts["walk_trusted"] += 1
                                    rec_w.update({"gate": "trusted", "red": res.get("red")})
                                ev(rec_w)
                            elif act_ == "engage":
                                ev({"kind": "engage", "by": "walk_sword", "name": None})
                                aim: tuple[float, float] | None = (u, v)
                                if getattr(a, "still_strike", False) and not ring1(rel):
                                    aim = still_retarget(u, v, rel)  # dungeon@9.4 (4S)
                                if aim is not None:
                                    strike(aim[0], aim[1] - BODY_UP / 2, rel, "walk_sword")
                                    lock = {"t": time.monotonic(), "rel": rel, "cell": list(c)}
                                    mode = "fight"
                            else:
                                rec_w = {"kind": "walk", "from": list(here), "to": list(c),
                                         "clicked": False, "why": why_w, "red": res.get("red"),
                                         "ring": res.get("ring")}  # fmt: skip
                                if dodge is not None:
                                    rec_w["dodge"] = dodge
                                if pick_how is not None:
                                    rec_w["pick"] = pick_how
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
                        and pos_flies < POS_FLY_MAX
                        and not unread_held(tick)):  # 9.22: --unread-step first  # fmt: skip
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
            bare_final: dict[str, Any] | None = None
            if bare is not None:  # dungeon@9.27: ALWAYS armed before the run ends, read back
                try:
                    bare_final = bare.run_end(dead=reason == "death")
                except Exception as exc:  # noqa: BLE001 -- recorded; the end steps still run
                    bare_final = {"armed": bare.st.armed, "error": repr(exc)[:300]}
            if rk_on:  # dungeon@9.36: kills still pending at the end (neither looted nor expired)
                counts["recheck_left"] = len(rk_pending)
            if lm_on:  # dungeon@9.37: cells still remembered at the end (not visited, not expired)
                counts["memory_left"] = len(lm_mem)
            ev({"kind": "run_end", "reason": reason, "counts": dict(counts),
                "pos_light_unconfirmed": pos_ok.unconfirmed,
                **({"bare": bare_final} if bare_final is not None else {})})  # fmt: skip
            if ex_rec is not None:  # dungeon@9.14: this run's knowledge, merged into the map's
                (out / "explore-run.json").write_text(json.dumps(ex_rec.know.to_json()))
                merged_ = em.save_merged(ex_rec.know)
                ev({"kind": "explore_saved", "runs": len(merged_.runs),
                    "regions": len(merged_.regions), "visited": len(merged_.visited),
                    "refused": len(merged_.refused)})  # fmt: skip
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
                hud_rec = boxes.hud_info()  # dungeon@9.29c: the HUD twin's calls, when it ran
                if hud_rec is not None:
                    ev({"kind": "hud_watch", **hud_rec})
            if item_det is not None:  # dungeon@9.33 (--loot-items): its client's paths, closed
                ev({"kind": "loot_items_det", "info": item_det.info()})
                item_det.cpu.close()
            # dungeon@9.35 (--player-mode): a run that ends while she rests stays SEATED (natural
            # regen goes on); she stands only for the end's escape (no Fly Wing while sitting). It
            # cannot turn due later: time only ages the hits and the HP reads (end_escape_needed).
            # 9.35b: she stands for the Butterfly Wing home too, when one is pressed (below)
            seated_end = player and sitting and not end_escape_needed(
                time.monotonic(), last_taken, st.hist, reason)  # fmt: skip
            if sitting and not seated_end:
                agent_raw.keys(keys_["stand"])
            if end_escape_needed(time.monotonic(), last_taken, st.hist, reason):  # dungeon@8.5
                press("fly", "end")
                ev({"kind": "end_escape", "how": "fly", "reason": reason,
                    "hp": None if not st.hist else round(st.hist[-1][1], 3)})  # fmt: skip
                time.sleep(1.0)
            if reason == "death" and not player:  # 9.35: a player's death dialog is the person's
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
                    typed_line(agent_raw, screen, cmd, conf["job"], crk, player_mode=player)
                    time.sleep(0.8)
                bench.close_chat(agent_raw, screen)
                if bare is not None and not bare.st.armed:  # dungeon@9.27: alive -> armed again
                    try:
                        ev({"kind": "bare_after_alive", **bare.run_end()})
                    except Exception as exc:  # noqa: BLE001 -- recorded; the warp home follows
                        print(f"bare-steal: the equip after @alive failed: {exc!r}", flush=True)
            # 13:19: a stopped run left the Crusader at 30 % HP among orcs with no runner: after
            # run_end (outside the measured window) it goes home. dungeon@8 (4.05 a1, 2026-10-25
            # 22:04): after a DEATH too -- @alive revives it on the spot, and the Orc Lord that
            # killed it killed it again there
            if not player:  # dungeon@9.35: a player is never warped home (the escape above)
                try:
                    typed_line(agent_raw, screen, f"@warp {CLEAR_STAND[0]} {CLEAR_STAND[1]} "
                               f"{CLEAR_STAND[2]}", conf["job"], crk,
                               player_mode=player)  # fmt: skip
                    time.sleep(3.0)
                    bench.close_chat(agent_raw, screen)
                except Exception as exc:  # noqa: BLE001 -- recorded; the next setup checks again
                    print(f"end warp failed: {exc!r}", flush=True)
            else:  # dungeon@9.35b: the Butterfly Wing home (a count >= 1), once, then what she
                # was left as: seated (a rest, no wing), standing, home, or dead with its dialog
                home_rec: dict[str, Any] = {"pressed": False, "stood": False}  # filled in place
                try:
                    import hotbar_count as hb_h

                    def home_count() -> int | None:
                        if stock_watch is None or home_key is None:
                            return None
                        g_h = hb_h.gray(np.asarray(frame()))
                        return hb_h.read_count(g_h, hotbar_slot(home_key), stock_watch[0])

                    player_home_end(
                        home_key, reason, seated_end, read_count=home_count,
                        press=lambda: press("home", "end"),
                        stand=lambda: agent_raw.keys(keys_["stand"]),
                        basic_info=lambda: hpp.read(frame(), glyphs) is not None,
                        rec=home_rec)  # fmt: skip
                except Exception as exc:  # noqa: BLE001 -- recorded; the end goes on
                    home_rec["error"] = repr(exc)[:300]
                ev({"kind": "player_home", **home_rec})
                ev({"kind": "player_end", "reason": reason,
                    "seated": seated_end and not home_rec.get("stood"),
                    "home": bool(home_rec.get("pressed")), "dead": reason == "death"})  # fmt: skip
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
        "--still-strike",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="dungeon@9.4 (rogue-xmas02.md 4S, pilot p12; OFF by default): a far strike (2+ cells) "
        "waits for a still scene and aims again (the box path: a detection after it; walk_sword: "
        "its point carried by the scroll, hovered again)",
    )
    t.add_argument(
        "--far-approach",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="dungeon@9.10 (rogue-xmas02.md 4AC; OFF by default): a box target 9+ cells away is "
        "walked toward first (to 4 cells short of it), then the box path looks again (twice a "
        "fight at most); no ring scan during that walk",
    )
    t.add_argument(
        "--explore-cover",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="dungeon@9.14b (rogue-xmas02.md 4AO; OFF by default; with --explore): the novelty "
        "bonus from coverage (the share of a region's cells ever walked) instead of arrivals",
    )
    t.add_argument(
        "--walk-pick",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="dungeon@9.15 (rogue-xmas02.md 4AM; OFF by default): a walk target fits only when the "
        "cell the client picks under its pixel (the camera ray's first tile top) is walkable and "
        "within 1 cell of it -- else a nearer path cell (raised floors: the client drops it)",
    )
    t.add_argument(
        "--explore",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="dungeon@9.14 (rogue-xmas02.md 4AL; OFF by default; with --search patrol): walk to "
        "map REGIONS chosen by explore + exploit from data/maps/MAP/explore.json (what the bot "
        "saw: dwell, fights, good fights, stalls) instead of the route loop; the run's knowledge "
        "is merged into that file at its end",
    )
    t.add_argument(
        "--kill-gap",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="dungeon@9.13c (rogue-xmas02.md 4AF; OFF by default): after 5 of our hits on the "
        "lock, none for 1.5 s is taken as the kill (no exp line at Base 99): the lock goes and a "
        "quiet fight ends without the scan",
    )
    t.add_argument(
        "--exp-first",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="dungeon@9.34 (Batt 2026-11-12, rogue-xmas02.md 4CW; ON by default): an EXP or Job "
        "EXP line in the Battle Log is the kill, first (Base + Job of one kill count once, paired "
        "within 1 s); once the client printed any exp line in the run, --kill-gap infers no kill",
    )
    t.add_argument(
        "--walk-pick-step",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="dungeon@9.15c (rogue-xmas02.md 4AU; OFF by default; with --walk-pick): when no "
        "path cell passes the pick check, the pickable one-click step nearest the goal instead "
        "of the plain target",
    )
    t.add_argument(
        "--garm-fly",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="dungeon@9.19 (rogue-xmas02.md 4BA; OFF by default; with the box detector): a box of "
        "an alarm class (garm_baby, xmas02-detector.md Amendment M) in a fresh detection takes "
        "the boss guard's Fly Wing at once; a model without the class gives no alarm",
    )
    t.add_argument(
        "--garm-confirm",
        type=int,
        default=GARM_CONFIRM,
        help="dungeon@9.19b (rogue-xmas02.md 4BD; with --garm-fly): the Fly Wing waits for alarm "
        "boxes in this many CONSECUTIVE detections (default 1 = 9.19 unchanged)",
    )
    t.add_argument(
        "--boss-walk",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="dungeon@9.18 (rogue-xmas02.md 4AZ; OFF by default; with --engage-screen): the boss "
        "guard WALKS AWAY from one of the boss's summons (one click, the farthest pickable "
        "cell >= 8 away) instead of a Fly Wing; a new boss line after 2.5 s, a 3rd walk-away "
        "in 60 s, no cell, or the boss itself -> the Fly Wing as before",
    )
    t.add_argument(
        "--unreach-escape",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="dungeon@9.26 (rogue-xmas02.md Study S-UA; OFF by default; with --reach-check and "
        "--engage-screen): 3 consecutive locks ending 'no hits' on the same cells (within 1) "
        "within 90 s, an attacked sign (Miss cue / hit line / HP drop) in each lock's window "
        "and no damage line of ours = an UNREACHABLE attacker: its cells are skipped by the "
        "defend scan and the box path for 120 s, and ONE walk click takes her >= 9 cells from "
        "them (the farthest pickable one-click cell within 12 whose cursor reads clear, of 3 "
        "tried); no cell, no position, or a 2nd trigger within 120 s of such a walk -> the "
        "Fly Wing",
    )
    t.add_argument(
        "--stage-mob",
        default=None,
        metavar="ID:N",
        help="dungeon@9.18 TRIAL ONLY (rogue-xmas02.md 4AZ): the setup's last line spawns N of "
        "mob ID at the start (@monster ID N; at --stage-at's cell when given), a staged encounter "
        "for a pre-registered trial",
    )
    t.add_argument(
        "--start-cell",
        type=cell_arg,
        default=None,
        metavar="X,Y",
        help="TRIAL ONLY (rogue-xmas02.md 4BU, U0: the staged unreachable attacker): the run "
        "starts on X,Y instead of the map's patrol start (or the seed's cell); the setup's @warp "
        "goes there. Refused unless X,Y is on the run's route grid and passes the three "
        "stand-cell checks (no warp span, no NPC touch area, the server's map cache)",
    )
    t.add_argument(
        "--stage-at",
        type=cell_arg,
        default=None,
        metavar="X,Y",
        help="TRIAL ONLY (rogue-xmas02.md 4BU, U0; refused without --stage-mob): the staged mob "
        "spawns at X,Y, not on her -- the setup types @warp MAP X Y, @killmonster2 (with "
        "--clear-map), @monster ID N, then @warp MAP to the start. X,Y must pass the three "
        "stand-cell checks",
    )
    t.add_argument(
        "--late-confirm",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="dungeon@9.21 (rogue-xmas02.md 4BI, LF-2; OFF by default): a light position read "
        "held back for coming > 1.0 s after the read before it is confirmed at once by a read "
        "of a NEWER bus frame (another frame id, <= 0.25 s), by PosConfirm's own rule, instead "
        "of on the next tick; the position-jump bar is unchanged",
    )
    t.add_argument(
        "--unread-step",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="dungeon@9.22 (rogue-xmas02.md 4BI, LF-4; OFF by default): before the pos_unread Fly "
        "Wing (20 s without a fresh position read), no wing while a walk click of ours is < 2 s "
        "old; then up to 2 screen-relative 2-cell steps back along her last own movement, each a "
        "walk click after a CLEAR cursor read, then 2 s for a fresh read; a fresh read cancels the "
        "wing, else the wing as before",
    )
    t.add_argument(
        "--still-target",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="dungeon@9.23 (rogue-xmas02.md Study S-LS, LS-2; OFF by default; with --box-strike "
        "--box-now --still-strike): at the box target's SWORD, one more detection of the same "
        "sprite; its foot moved < 10 px -> the strike as before; else no click yet: a detection "
        "every 0.25 s until two in a row are still (at most 2.5 s), then its new box is hovered "
        "and struck only on a SWORD read; a timeout or a lost sprite -> no box strike",
    )
    t.add_argument(
        "--lead-press",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="dungeon@9.24 (rogue-xmas02.md Study S-LS, LS-1; 4BP; OFF by default; with "
        "--still-target, not with --lead-strike): when the press check would hold a sprite whose "
        "foot moved >= 15 px between its two detections, it is struck ahead instead: the second "
        "detection's hover point + the foot's velocity x (0.57 s + the time since that grab), "
        "at most one cell; the led point is NOT SWORD-read; a led point outside the box target's "
        "gates -> the hold as before; shifts of 10-15 px hold as before",
    )
    t.add_argument(
        "--quiet-scan",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="dungeon@9.17 (rogue-xmas02.md 4AW; OFF by default): the ring scan for an attacker "
        "runs only after damage on the screen in the last 5 s (a hit line on us, an HP drop, a "
        "Miss at us, a damage line of ours); else a fight with no lock ends at once",
    )
    t.add_argument(
        "--loot-first",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="dungeon@9.16 (rogue-xmas02.md 4AT; OFF by default): after a kill the loot step "
        "runs before a box alone starts the next fight; the quiet-kill rule ends only a fight "
        "that began before the kill; a defend scan that found no sword clicks the first "
        "pickup hand it read",
    )
    t.add_argument(
        "--reach-check",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="dungeon@9.12 (rogue-xmas02.md 4AE; OFF by default; with --engage-screen): a box "
        "whose cell the server would not walk us to on one click (the server's map cache: a walk "
        "<= 17 steps, <= 14 unless the straight line is clear) is passed over by the trigger and "
        "the box path",
    )
    t.add_argument(
        "--skip-own-cells",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="dungeon@9.9 (rogue-xmas02.md 4AB; OFF by default): the defend scan skips a cell "
        "whose hover point lies on her own sprite and hovers on (no strike through her sprite)",
    )
    t.add_argument(
        "--far-single",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="dungeon@9.8 (rogue-xmas02.md 4Z, pilot p18; OFF by default): a strike 4+ cells away "
        "clicks ONCE and waits 1.0 s + 0.2 s a cell (<= 3.5 s) for the arrow / damage, never "
        "re-clicking while the camera scrolls (a re-click landed on the floor)",
    )
    t.add_argument(
        "--near-single-still",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="dungeon@9.25b (rogue-xmas02.md 4BT, R2b; OFF by default): a 2-3-cell strike "
        "re-clicks only while the scene has not scrolled since its first click",
    )
    t.add_argument(
        "--near-single",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="dungeon@9.25 (rogue-xmas02.md Study S-LF5 R2; OFF by default): --far-single's "
        "one click from 2 cells instead of 4 (the 2-3-cell re-click walked her off the target)",
    )
    t.add_argument(
        "--engage-screen",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="dungeon@9.7 (rogue-xmas02.md 4X, pilot p16; OFF by default): the patrol engages ANY "
        "monster box on the screen (its body point in view), and the box path takes the nearest "
        "one on the screen, not only within ~3 / ~6 cells",
    )
    t.add_argument(
        "--quick-drop",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="dungeon@9.6 (rogue-xmas02.md 4W, pilot p15; OFF by default): a strike with no arrow "
        "and no damage 2.0 s after its click takes no lock, and a lock whose arrow brought no hit "
        "of ours in 2.0 s drops; then the box path runs again (nearest box), twice a fight at most",
    )
    t.add_argument(
        "--quick-drop-scaled",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="dungeon@9.38 (rogue-xmas02.md 4DG; OFF by default; needs --quick-drop): the "
        "lock's no-hit window after the arrow grows with the strike's distance: 2.0 s + 0.2 s a "
        "cell, at most 3.5 s (QUICK_HIT_S + QUICK_PER_CELL x cells, QUICK_HIT_MAX_S); the "
        "no-arrow drop is unchanged",
    )
    t.add_argument(
        "--lead-strike",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="dungeon@9.5 (rogue-xmas02.md 4V, pilot p14; OFF by default): the box path takes a "
        "second detection, and a target sprite that moves on a still scene is hovered where it "
        "will be at the click (its velocity x LEAD_T_S); no SWORD there -> its current point once",
    )
    t.add_argument(
        "--plant-sweep",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="dungeon@4's White Plant cursor sweep (dungeon@5: OFF, Batt decision 6)",
    )
    t.add_argument(
        "--box-every",
        type=float,
        default=BOX_EVERY_S,
        help="dungeon@9.11 (rogue-xmas02.md 4AD; default BOX_EVERY_S 1.0): the box watcher's "
        "rhythm in seconds (Batt: 'detect monsters fast'; the GPU call is ~21 ms)",
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
        "--hud",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="dungeon@9.29 (Batt 2026-11-11): send the boxes the runner holds (by species) to the "
        "console's operator HUD, at its own rate limit; DISPLAY ONLY (no input, no decision)",
    )
    t.add_argument(
        "--steal-cue",
        choices=["both", "popup"],
        default="both",
        help="dungeon@9.27d (with --bare-steal; rogue-xmas02.md 4CE): the steal cue -- both (the "
        "popup or a new cyan Battle Log line, as merged) or popup (the item popup only: the live "
        "reader re-emits old cyan lines; p69: 57 %% of cyan equips had no steal)",
    )
    t.add_argument(
        "--hud-fast",
        type=float,
        default=None,
        metavar="S",
        help="dungeon@9.29b (with --hud; Batt 2026-11-11: the boxes come late, sometimes where "
        "the monster was): HUD-ONLY GPU detections every S seconds between the watcher's own, "
        "sent as they come (a box lives 600 ms); the decisions never read them. dungeon@9.29c: on "
        "the GPU they run in a thread of their own on a HUD-only connection, which the detect "
        "server serves only between the decisions' calls (it skips a frame that cannot start in "
        "time); logged to detections_hud.jsonl",
    )
    t.add_argument(
        "--value-target",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="dungeon@9.28 (rogue-xmas02.md 4CB; toward Batt's 2026-11-11 goal of 100,000 z/h; "
        "OFF by default): the box target is the box worth the most a kill (the map model's drops "
        "at Overcharge, data/econ/maps.json, by the detector's own species), discounted by "
        "distance (value / (1 + d / 150 px)), not simply the nearest; the same candidates",
    )
    t.add_argument(
        "--queue",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="dungeon@9.30 (rogue-xmas02.md 4CC; Batt 2026-11-11 ~19:3x: a queue of the monsters "
        "in the scene, the one near and attacking us first, then on down the queue; OFF by "
        "default; with --box-strike): while a fight runs, the OTHER monster boxes in view (not "
        "the target, not our own body) are kept as a queue of at most 6, an entry not seen in "
        "the fight's detections for 2 s dropped, the nearest within 2 cells of her marked "
        "attacking when a hit / Miss / HP drop is read; once the fight AND its loot step have "
        "ended, the next target comes from the queue at once -- attacking first, then the "
        "nearest (with --value-target the rest by value) -- re-found on the next fresh "
        "detection within 60 px of its last foot, passing the box path's skips, hovered for its "
        "SWORD and struck through strike(); an empty queue, a failed re-find or no SWORD -> "
        "today's search path. Never during a loot step, a rest, an escape or a bare-steal swap",
    )
    t.add_argument(
        "--loot-items",
        default=None,
        metavar="MODEL",
        help="dungeon@9.33 (Batt 2026-11-12: the bot spends time looking for items every time; OFF "
        "by default; with --loot trim): the loot step asks the floor-item MODEL (a GPU_WEIGHTS "
        "name, e.g. xmas02fi4; its ONNX in /dev/shm/poring-lab-detector/model as the CPU "
        "fallback) once on a fresh frame; it hovers only the seen items' cells (+ neighbours, at "
        "most 3 an item) near the kills, and SKIPS the sweep when none is seen; a failed "
        "detection -> today's sweep",
    )
    t.add_argument(
        "--loot-recheck",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="dungeon@9.36 (rogue-xmas02.md 4DA, after 4CZ: the loot step asked the item model "
        "2-3 s after the kill, before ~43 %% of the drops were drawn; OFF by default; with "
        "--loot-items): the loot step stays 9.33; each kill's 5 x 5 cells then stay pending for "
        "7 s, and while one is and she is calm (hunting, no lock, no hit for 2.5 s, no boss "
        "window) the same item model runs on a fresh frame at most once a second in the main "
        "loop; an item boxed inside a pending kill's cells -> those cells are looted as the loot "
        "step's seen-items path does (its order, hovers and caps) and that kill is done; a fight "
        "or a hit during it yields (the kill stays pending until it expires)",
    )
    t.add_argument(
        "--loot-memory",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="dungeon@9.37 (rogue-xmas02.md 4DB, after p94: 9.36's recheck ran once in 71 pending "
        "kills, its calm rule almost never true on a dense map; OFF by default; with "
        "--loot-items; independent of --loot-recheck): while any kill is younger than 7 s the "
        "item model LOOKS on a fresh frame at most once a second, in any mode but sitting "
        "(fights included; no click, no sleep); item cells inside a young kill's 5 x 5 cells are "
        "remembered for 12 s after their last sighting; the NEXT loot step hovers its own seen "
        "items plus the remembered cells (its order and caps; a step that saw nothing itself "
        "visits them) and clears those it visited; calm (9.36's rule) with cells left -> 9.36's "
        "recheck path loots them",
    )
    t.add_argument(
        "--loot-aim",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="dungeon@9.32 (rogue-xmas02.md Study S-IDLE; Batt 2026-11-12; OFF by default; with "
        "--loot trim and --box-strike): at a kill, the nearest monster box's cell (within 2 cells "
        "of her, in the watcher's last detection) is kept; the trim loot step hovers it first, "
        "then its neighbours, and at most 5 hovers a kill when every kill of the step has one "
        "(else today's 9). Natural drops land on the death cell (74 / 77)",
    )
    t.add_argument(
        "--swap-gap",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="dungeon@9.27e (with --bare-steal; Batt 2026-11-11 22:53, p71: the dagger went on "
        "after a steal, then the runner called the monster dead and went bare on it again): a swap "
        "(equip / unequip / opener, read back) restarts the no-hit clocks -- our hit lines pause "
        "through a swap, so the kill gap (--kill-gap) and the lock's no-hit timer count from the "
        "swap's end, not from the last hit before it",
    )
    t.add_argument(
        "--heal-candy",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="dungeon@9.31 (Batt 2026-11-11: no White Potions, eat Candy and Candy Cane instead; "
        "OFF by default; the Rogue): a due potion presses the Candy Cane (F6) while its hotbar "
        "count is not 0, then Candy (F7), then the White Potion (F1) as the fallback; the setup "
        "tops the candies up to 20 + 20 and no longer tops up (or drinks down) the potions; the "
        "run ends on the heal stock only when all three read 0",
    )
    t.add_argument(
        "--bare-steal",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="dungeon@9.27 (rogue-xmas02.md 4BX, Batt 2026-11-11; OFF by default; the Rogue only, "
        "not with --steal): a new target is hit BARE-HANDED so Snatcher steals before it dies -- "
        "the dagger comes off first (Alt+Q, a double-click on the equipment window's weapon slot, "
        "Alt+Q; each step read back) and goes back on with F5 at the first steal cue (a new item "
        "popup or a new cyan Battle Log line: no words read), after 8 s, under 50 %% HP, when the "
        "fight ends, before any escape and at the run's end; the F5 slot (its icon = the dagger "
        "in the bag) is the weapon state's readout",
    )
    t.add_argument(
        "--bare-ready",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="dungeon@9.27b (Batt 2026-11-11 after rogue-xmas02.md 4BY's p65 / p66; OFF by "
        "default; with --bare-steal): the dagger comes off while IDLE -- after the loot step, "
        "after a fight with nothing to loot, or on a search tick with no lock, no window open and "
        "no world click in the last 1.2 s (the search walk holds its next click meanwhile) -- so "
        "a new target is hit bare-handed AT ONCE, with no swap at the strike; a fight ending bare "
        "stays bare; the steal cues, 8 s, under 50 %% HP, every escape and the run's end put it "
        "on with F5 as --bare-steal does",
    )
    t.add_argument(
        "--steal-opener",
        default=None,
        metavar="KEY",
        help="dungeon@9.27c (Batt 2026-11-11 ~19:15; OFF by default; with --bare-steal; KEY in "
        "F1-F9, not F5 nor a key the character uses): open with the weak item on hotbar KEY (the "
        "Knife on F4) instead of bare hands -- the swap is that key (no window, no click), read "
        "back as KEY's slot EMPTY (worn) and F5 showing the dagger (in the bag); every equip "
        "stays F5, read back as F5 empty and KEY showing the opener. The run's start needs the "
        "dagger worn and the opener in the bag. With --bare-ready the key goes at the idle "
        "moment, else at a new target's first strike",
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
        "--player-mode",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="dungeon@9.35 (docs/planning/player-mode.md, Batt 2026-11-12; OFF by default): the "
        "hunt as a normal player, for a public rAthena that permits bots (ADR-0023's declared "
        "mode): the run types NO line (no GM command, no chat) in its setup, loop or end, and "
        "reads nothing from the lab's DB. The person brings the character to the map with her "
        "stock; the run starts where she stands (her cell read on the minimap, on the map's "
        "route grid), refuses below 5 Fly Wings / 5 heal items on the hotbar "
        "(PLAYER_MIN_WINGS / PLAYER_MIN_HEALS) or an unread weight / >= 48 %%, never warps, "
        "heals, tops up, drinks down, drops the bag or stages, ends when the Fly Wings read 1 "
        "(PLAYER_WINGS_KEEP), and ends with the run's own Fly Wing escape, then (9.35b) ONE "
        "Butterfly Wing home when its hotbar count reads >= 1 (--player-home-key; without one a "
        "rest stays seated; a death's dialog stays for the person). On a map whose KB lists a "
        "boss spawn, with neither --engage-screen nor --garm-fly, it prints one WARNING line at "
        "the start and goes on (9.35b). Refused with --clear-map, --stage-mob, --stage-at, "
        "--start-cell, --engage melee_ring",
    )
    t.add_argument(
        "--player-home-key",
        default=None,
        metavar="KEY",
        help="dungeon@9.35b (Batt 2026-11-12; with --player-mode): the Butterfly Wing's row-1 "
        "hotbar key (default: the character's home_key, F8). At the end of a --player-mode run, "
        "after its own end escape, it is pressed ONCE when its hotbar count reads >= 1 (a seated "
        "end stands first); no key, an unread or 0 count, a death or a hard bar: no press, "
        "recorded (player_home). The start checks nothing for it",
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
    cb = sub.add_parser("clear-bag", help="LIVE: empty the inventory tabs on the clear stand, "
                        "then restock the run stock (Batt 2026-11-08)")  # fmt: skip
    cb.add_argument("--char", required=True, choices=sorted(CHARS_CONF))
    cb.add_argument("--tabs", default=",".join(BAG_TABS))
    cb.add_argument("--out", required=True, help="the evidence directory (/dev/shm)")
    a = ap.parse_args()
    if a.cmd == "clear-bag":
        return clear_bag(a)
    if a.cmd == "run" and a.ag_match is None:
        import survive as sv

        a.ag_match = sv.AG_MATCH_DUNGEON
    return run(a)


if __name__ == "__main__":
    raise SystemExit(main())
