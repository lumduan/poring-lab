---
doc_type: design
hypothesis: "On xmas_dun02 (Toy Factory 2F, the lab's pre-renewal server), the Rogue at Base 99 with base AGI 99 / DEX 99 and the gef10 skills, walking the map's EDGE clockwise (Batt's technique) and fighting plain melee so Snatcher steals on its own, gains stolen items per hour that are worth more than at its current build; and the live v1 detector's generic 'monster' class sees this map's species well enough (Q1's bar, section 4) that no new detector is needed first."
status: "X0 DONE 15:05; X1 DONE (merged e777181); pilot p1 15:27-15:32 STOPPED by the runner (the minimap readout is not read over the light floor, section 5); Amendment C (~20:2x): Batt's answers -- the recorder floor is 120 GB (X2 no longer blocked by the disk), the route on trial, the 2nd chat tab renamed Chat, 688 points left; X1b (a light-strip readout reader) pre-registered 4D, its data next. Planned 2026-11-05 (Batt's order ~13:2x, the four answers ~14:0x ICT, section 0). X1b round 1 (20:16-20:43) FAILED B2 (light strips 8/40: the guard refused true reads on mixed strips); round 2 pre-registered 4E (fresh cells). Round 2 (21:49, fresh midpoints) FAILED R2 (light 16/24; the guard refused a seam); round 3 pre-registered 4F (fresh quarter cells). Round 3 FAILED R2 (light 83.3 %, 0 wrong); the iteration stopped. Pilot p2 22:37: 15 min clean, 0 position-unread Fly Wings. X2 RECORDED 22:54 (1,320 frames, 2.03 GB, shipped + verified); its scoring waits for the tooling. 2026-11-06 (Amendment D, Batt): the reader stays ON and improves; the Chat tab name SURVIVED a client restart (06:39); the dead ends = the no-entry cue reading the orange floor (4G); dungeon@8.6 (the ring) pre-registered as pilot p3 (4G). p3 PASSED (0 dead-end Fly Wings, carves 6.3 %); its packets: straight-north clicks send no move request -> dungeon@8.7 (column_dodge) pre-registered as pilot p4 (4H). p4 PASSED: 215 waypoints in 15 min (p2 31), 0 Fly Wings, 3 stalls; the next limit is the fight. p5 (a measurement): the reader gives a position on 96.1 % of live reads (failures 1.4 %, unconfirmed 2.5 %, all on the west leg); 0 strikes from 5 box engagements. X2 SCORED: FAIL (v1 recall 0-0.5 % per species, precision 1.5 %): this map needs its own detector (GPU approved by Batt). hunt_flow v56 run 1 K1 INCONCLUSIVE; run 2 blocked by the up icon until Batt's Alt+S / Alt+A answer (Amendment F, f91ab44); run 2 11:12 -> v56 ADOPTED on the pooled verdict (K1 0/74 vs 21/73, K2, K3). The detector plan ACCEPTED (xmas02-detector.md Amendment A)."
role: null
verdict_date: null
verdict_ticket: null
supersedes: null
related: [rogue-gef10.md, gef10-prep.md, xmas02-prep.md, gef10-detector.md, ../benchmarks/gef10-eval.md, ../demonstrations.md, ../../scripts/dungeon_hunt.py, ../../scripts/dungeon_judge.py, ../../services/rathena/conf/import/groups.yml]
next_action: "p15 (4W, --quick-drop) pre-registered 2026-11-08 20:0x; then p16 = the patrol engages any monster box on screen, nearest first (Amendment I)."
title: "The Rogue on xmas_dun02: AGI 99 / DEX 99, the edge loop clockwise, Snatcher steals (planned)"
date: 2026-11-05
owner: Batt
---

# The Rogue on xmas_dun02 (planned)

## 0. Batt's order and decisions (2026-11-05, ICT)

- ~13:2x (his words, Thai, translated): "Go train on map xmas_dun02 instead. Set the Rogue's stats
  to AGI 99 DEX 99, the same skills as before, because we will focus on stealing items with auto
  steal (Snatcher). Try this first. The map is a bit hard: it is hard to walk, many things block
  the way, but there is a technique: walk along the edge of the map, going clockwise round and
  round. If you meet the boss, run away. You may use YOLO."
- ~14:0x, his four answers:
  1. **BASE AGI 99 + DEX 99**, so the Rogue goes to **Base 99** (the code's hold at Base 63 is
     lifted; `dungeon_hunt.py` `level_hold`).
  2. **Add the stat commands (@str ... @luk) to group 20**, logged like his other additions
     (`groups.yml`), applied with the 2026-11-05 rathena recreate.
  3. **The boss: clear it at setup** (`@killmonster2`, as gef10 Amendment A4) for the first runs,
     **and build a recognizer** from the recordings so "run when you see it" becomes real.
  4. **YOLO: measure the live v1 first** (CPU, no GPU); train a species detector on the GPU (R1-R3,
     the fit-first VTON co-tenant first) only if v1 misses too much (section 4).

## 1. Facts (a read-only research pass, 2026-11-05; the pinned rAthena e985006, pre-renewal)

**Monsters** (`npc/pre-re/mobs/dungeons/xmas_dun.txt:31-38`; every spawn on a random cell of the
whole map; `db/pre-re/mob_db.yml`):

| id | species | n | Lv | HP | AI | steal table (= drop table; % ; NPC sell z) |
|---|---|---|---|---|---|---|
| 1249 | Myst Case | 50 | 38 | 3,450 | passive, teleports when hit "rudely", Hallucination 5 % | Zargon 15 (240), Piece of Cake 8 (1500), Pearl 1.5 (3000), Old Blue Box 0.2 (5000), 2ct Diamond 0.05 (12500), Candy 3.4, Candy Cane 0.9 |
| 1248 | Cruiser | 35 | 35 | 2,820 | **AGGRESSIVE, ranged (7)** | Scell 35 (80), Manacles 9 (329), Iron 3.2, Rough Oridecon 0.87 (275), Rough Wind 0.05, Monk Hat 0.02 (15000) |
| 1265 | Cookie | 20 | 25 | 950 | passive, ASSIST (pulls the others), heals | Well-baked Cookie 10 (500), Candy 3.2, Candy Cane 1.5, Heal Lv3 scroll 1 |
| 1246 | Christmas Cookie | 20 | 28 | 2,090 | passive; Cold Bolt, Lex Aeterna, Reverse Orcish 0.5 % | Red Herb 17, Well-baked Cookie 15 (500), Zargon 2, Pearl 0.45 (3000), Cold Bolt scroll 1 |
| 1515 | Garm Baby | 1 (30 min) | 61 | 20,199 | **aggressive**, Frost Diver | Ice Cubic 43.65 (330), Pinafore 25 (480), Nursing Bottle 15 (550), Frozen Rose 1 (17500) |
| 1251 | **Stormy Knight (MVP)** | 1 (60-70 min) | 77 | 240,000 | **aggressive**, Storm Gust 10, Wide Freeze, Shield Charge, Hallucination; summons Garm Baby + Christmas Goblins | **NOT stealable** (boss class) |

- 127 monsters; 37 aggressive. Walk speed (ms per cell): the Rogue 150; Stormy Knight and Cookie
  200; the rest 400-450.
- **Stormy Knight:** ATK 1425-1585 against the Rogue's ~2,209 HP at Base 63 (two hits); HIT 207
  (~94 % against FLEE 193 now, ~41 % at Base 99 with AGI 107); freeze / stun stop a Fly Wing.

**The map** (the stock server map cache; 260 x 260): 50,183 walkable cells reachable from the
arrival (131,130); a maze of 2 x 2 pillars and wall lines inside. **The edge loop** (clockwise on
a north-up map, every cell checked walkable, 953 cells, 0 blocked):
(7,21) -> (7,253) -> (251,253) -> (251,156) -> (240,156) -> (240,23) -> (11,23) -> (11,21) -> (7,21).
~143 s a lap at the Rogue's 150 ms per cell with no fights; ~28 % of the reachable cells (~36 of
127 monsters) lie within 12 cells of it.
- **The only exit warp** is at 129,130 (a 3 x 3 trigger, cells 128-130 x 129-131): the arrival
  cell 131,130 is ONE step east of it. The setup warps straight to an edge cell instead.
- Mapflags: `nomemo` only: @warp, Fly Wing (same map) and Butterfly Wing work.

**Snatcher** (pre-re): 30.5 % of damaging NORMAL hits proc (Snatcher 10, Steal 10); each proc tries
the table in order at itemRate x rate, rate % = (our DEX - mob DEX)/2 + 64; ONE success per monster;
bosses never. Chance per proc that an item is taken, now (DEX 47) -> at AGI/DEX 99 (DEX 106):
Myst Case 17.5 -> 24.8 %, Christmas Cookie 21.7 -> 30.3 %, Cookie 11.0 -> 15.4 %, Cruiser
19.8 -> 32.1 %, Garm Baby 34.1 -> 51.7 %.
- Packets (offline truth): a success is ZC_USE_SKILL 0x09CB (skill 50, the Rogue -> the mob, result
  1) then the pickup 0x0B41; a failure ZC_ACK_TOUSESKILL 0x0110 (skill 210 cause 0). Our decoder
  has 0x0B41 but not 0x09CB / 0x0110 (X4 adds them, offline only); the server's picklog type 'D'
  is the exact record.

**The Rogue** (Thief8fce, slot 3 of the GM account, group 20): Base 63 (held) / Rogue Job 50; STR
1, AGI 82, VIT 1, INT 1, DEX 40, LUK 1 (DB 2026-11-05 14:0x); skills Double Attack 10, Increase
Dodge 10, Steal 10, Envenom 3, Sword Mastery 10, Snatcher 10 (+ quest skills); +8 Damascus.

**The detector:** the live v1 has the classes player / monster / npc. No xmas_dun02 species is in
any species scheme (v2orc / payf07 / gef10). The CPU detector's RAM environment was removed in the
pause (2026-11-02); it is rebuilt from the NAS before X2.

## 2. Phases

- **X0, setup (live, supervised):**
  - group 20 gains the stat commands, applied with the rathena recreate;
  - switch to the Rogue (the character-select round trip; the chat window check runs at entry);
  - @baselevelup to 99, then base AGI 99 / DEX 99, each line through crusader.gm_line's name + job
    check, each read back (Basic Info / the status window, and the DB);
  - the skills stay; `dungeon_hunt.py`'s `level_hold` goes from 63 to 99 (a code change, tested).
- **X1, the offline map prep** (gef10-prep.md's recipe; no client, no GPU):
  - the KB gains `npc/pre-re/mobs/dungeons/xmas_dun.txt` and `npc/warps/dungeons/xmas_dun.txt`;
  - the client GAT (`grf_read.py extract` from the NAS GRF) and the client / server walkability;
  - script-NPC cells (the exit warp only), the zones file, the edge loop as the route, start stands
    on the loop (outside the warp's trigger, walkable on the server cache);
  - the outdoor camera model (xmas_dun02 is not in indoorrswtable.txt); the species' sprites.
  - ➡️ **DONE offline 2026-11-05 14:47-15:10 ICT: [xmas02-prep.md](xmas02-prep.md)** (the zones
    and the edge-loop route committed and proved; the KB candidates in /dev/shm, NOT installed;
    the runner needs a start stand on the loop and `level_hold` 99 before a run, section 5; X2's
    open points, section 7, go into section 4 BEFORE its recording).
- **X2, the v1 measurement (pre-registered, section 4):** a supervised recording of the Rogue on
  the edge loop with immunity ON (`@monsterignore`) and the MVP cleared, then v1 scored offline
  against packet labels.
- **X3, the first steal runs:** the edge loop clockwise, plain melee on the species the map has
  (Snatcher), the 8.4 stock guard and 8.5 safe end, the MVP cleared at setup; items per hour by
  item (stolen apart from dropped), the hard bars as before.
- **X4, the boss recognizer:** from X2/X3's recordings (the Stormy Knight seen at a distance, by
  pixels; packets as the offline truth); the flee rule (a Fly Wing at first sight, before it is
  within 10 cells) proven before any run without the setup clearing.
- **X5 (only if X2 fails Q1):** a species detector for xmas_dun02 (gef10-detector.md's pipeline,
  under R1-R3 with fit-first first).

## 3. Risks

- The Stormy Knight (two hits; freeze stops a Fly Wing): cleared at setup until X4 is proven.
- 35 ranged, aggressive Cruisers; Garm Baby (aggressive, 20k HP); Myst Case teleports away when
  hit; Cookies pull each other; Hallucination / Reverse Orcish change the picture.
- The exit warp one step from the arrival cell: never warp to 131,130.
- The interior maze: the edge loop avoids it; a chase into the interior returns to the loop.

## 4. X2 pre-registration: does v1's "monster" class see xmas_dun02's species? (written BEFORE its recording)

- **Data:** one supervised recording, >= 20 min, the Rogue walking the edge loop clockwise (immune,
  the MVP cleared at setup), frames at 1 fps (lossless PNG, 1280 x 720) to the root disk
  (`record_session.py --out /home/batt/poring-lab-rec`, CLAUDE.md rule 7), packets beside it.
- **Labels:** the packet labels of the gef10 method (the monsters the server says are in view,
  projected with the outdoor camera; the same rule and tolerances as gef10-detector.md), species
  from the packets' mob ids.
- **Scored:** v1 (the live CPU ONNX) on every frame; a box matches a label by the gef10 rule.
- **Bar (Q1's, gef10-eval.md):** for EACH of the four common species (Myst Case, Cruiser, Cookie,
  Christmas Cookie) with >= 30 labels: recall >= 0.80 AND precision >= 0.80 of the "monster" class.
  Garm Baby and the MVP are reported (too few to score).
- **Decision:** pass -> X3 runs on v1; fail -> X5 (a species detector) before X3, and the report
  says which species failed and why (missed sprites, boxes merged, hallucination frames).

### 4A. Amendment A to X2 (written BEFORE its recording, at this amendment's commit time; X1's findings, xmas02-prep.md section 7)

- **The recording IS the first supervised patrol run** (unscored as a hunt; its frames and packets
  are X2's data): `dungeon_hunt.py run --char rogue --map xmas_dun02 --strategy P2 --search patrol
  --walk-trust --npc-guard --miss-cue --loot trim --clear-map --minutes 20 --seed 20261105 --label
  xmas02-x2` (gef10's adopted settings, 10-26/27), the Rogue IMMUNE (its own @monsterignore of
  2026-11-05 15:09, this login), the MVP cleared by `--clear-map`. Beside it `record_session.py
  --backend rdp --format png --fps 1 --label xmas02-x2 --out /home/batt/poring-lab-rec --max-bytes
  3G` (rule 7: a recording goes to the root disk; shipped to the NAS after).
  - The runner now starts ON the loop (`PATROL_START`, (7,21) / (114,23)), selects the Battle Log
    tab before its reader starts, and records its MaxHP / MaxSP in run_start.
- **The bar, for a class-agnostic v1** (its classes are player / monster / npc, so a per-species
  precision is undefined): **recall >= 0.80 for EACH of the four common species with >= 30 labels
  (Myst Case, Cruiser, Cookie, Christmas Cookie; the species from the packets' mob ids), AND the
  pooled precision of the "monster" class >= 0.80** (a monster box matched to any monster label).
  Garm Baby, the MVP, the Goblins: reported only.
- **The label rule:** `detector_vs_packets.score_capture`'s gef10 position rule (class-agnostic),
  applied to the recorder's frames (their capture times, the packets' positions, the outdoor
  camera, the GAT heights); boxes and labels inside the UI windows of the session's layout (the
  hunting rows; the chat window of its date, `chat_window.for_sid`) are left out.
- **The tooling is built AFTER the recording without changing this rule or bar** (no CPU tool yet
  writes per-frame boxes for a recorder session; detector_vs_packets reads a human demo's dir).
  Its positive control first: on a banked gef10 human demo it must give back detector_vs_packets'
  own numbers for v1 before it scores X2.
- Hallucination frames (Myst Case, the MVP) are counted and reported, not removed.

### 4B. Amendment B (2026-11-05 ~15:25, BEFORE the pilot below): the recorder is refused by its disk floor

- 15:23 `record_session.py` refused: "only 134 GB free under /home/batt/poring-lab-rec (floor 140
  GB)" (`dataset_ship.MIN_FREE_BYTES`, the shared floor that protects the root disk of live
  capture; `df`: 614 G, 462 G used, 125 G available). The floor is not lowered and the recording is
  not moved to RAM (CLAUDE.md rule 7): **X2's recording waits** until Batt frees the root disk or
  decides on the floor. ➡️ Batt decided a 120 GB floor at ~19:0x (Amendment C, 4C).
- Instead, an **UNRECORDED 15-min pilot** of the runner on the loop (the same command as 4A with
  `--minutes 15 --label xmas02-p1`; the Rogue immune; the MVP cleared). It is not X2 and scores
  nothing: it checks that the runner works on this map (the edge loop walked clockwise, the
  engagements, the Battle Log reader on the docked 6-line window, Snatcher steals in the packets)
  and is reported with the runner's own events and the offline judge.

### 4C. Amendment C (2026-11-05 ~20:2x ICT): Batt's answers to the 15:38 report

Batt's answers (~19:0x ICT, Thai, translated), one per open decision of the report:
1. **The disk:** "Clear it first, go ahead. How much space does a YOLO recording normally take, so
   the floor can be set right?" The sizes (NAS manifests, 25 RDP PNG sessions 2026-10-25..10-29):
   **7.0-8.4 GB per hour at 1 frame/s**, ~16 GB/h at 2 frames/s; X2 is >= 20 min with a 3 GB cap.
   Batt then chose **a 120 GB floor** (was 140): `dataset_ship.MIN_FREE_BYTES`, ADR-0010
   "Amendment 2026-11-05". The image clean-up is HA's (its 10:03 inventory, the owners' answers;
   at most ~10 GB that night, and HA asks Batt directly before removing anything); poring-lab
   removes nothing (rathena-build and vision stay: both are used).
2. **The readout:** "yes" to a reader for light strips, with /where meanwhile (X1b below).
3. **The route and the zone (delegated):** "Try it first to see whether it works, but it does not
   need to hug the edge exactly." Recorded in both files' `delegation` (route sha256 now
   `a3532a338f166844...`, zones `89ea7a9c98d5d62b...`); `reviewed_by` stays the delegation.
4. **The 688 unspent status points:** "No need to add them; leave them as they are."
5. **The second chat tab:** "Give it a name that says what it is for, in case we use it later",
   then (asked how) "double-click the tab": renamed **"Chat"** at 20:03
   (docs/client/rathena-client.md).
6. **Port 8888's unauthenticated load routes on the LAN:** "yes" (accepted as documented).

**X2's recording is no longer blocked by the disk** (129 GB free against the 120 GB floor; X2's
cap is 3 GB). It still waits for X1b: the recording IS the first supervised patrol run (4A), and
the runner stops on unread positions (pilot p1).

### 4D. X1b pre-registration: a readout reader for light strips (written BEFORE its data)

- **The cause** (pilot p1's frame `live1`, 15:32, the readout "79 93" over the pale floor): the
  digits are drawn OPAQUE -- white strokes ~250 with a black drop shadow ~0 -- over a strip the
  scene shows through. `selfpos.strip_background` takes the median of the pixels between the
  shadow level (73.5) and the ink level (183.7), so a pale floor (~200) is left out and the
  estimate came from the magnifier corner (137.9); every floor pixel then reads as half a stroke
  and no digit template fits (`no_glyph`). Over the orange floor the same reader reads.
- **Data:** `scripts/selfpos_light.py collect --map xmas_dun02 --out /dev/shm/poring-lab-tmp/x1b
  --per-stand 8`: the Rogue (immune) is `@warp`ed to each of the edge loop's 85 waypoints in
  order (`@killmonster2` at the first: a still scene, no aggressor), 8 grabs 0.35 s apart after
  1.5 s; each grab keeps the readout rect (+2 px) and the base reader's answer. Then `truth`: the
  sniffer's events of the window; a crop's true cell is the last own `map_change` before it, only
  when it landed where it was sent and did not move after (standing frames only). Crops are
  client-derived pixels: /dev/shm, archived to the NAS, never committed.
- **The split:** EVEN stands are the fitting half: the light-strip design and any fitted numbers
  use only them. ODD stands are HELD OUT: scored ONCE, after the design is committed.
- **Bars on the held-out half (pooled over its crops):**
  - **B1:** 0 wrong reads (a read that is not the truth), on light and dark strips alike.
  - **B2:** >= 90 % exact on the light-strip crops (scene median >= 170, `selfpos_light.
    LIGHT_STRIP`, the opaque glyph pixels left out).
  - **B3:** on the dark-strip crops, exact >= the base reader's on the same crops, 0 wrong.
  - **B4 (T0's guard):** `selfpos_eval.py` on T0's held-out sessions (outdoor-c, outdoor-d,
    indoor-c) with the new reader still passes T0's pre-registered bars (>= 99 % exact standing,
    >= 97 % within one cell walking), and its wrong reads do not rise above the base reader's.
- **Reported beside the bars:** the base reader on the same crops (the baseline), the abstain
  reasons, the scene-median distribution, and the even half's in-sample numbers (not a result).
- **Then, not a bar:** pilot p2 (the pilot p1 command, 15 min, unrecorded): position-unread events
  and Fly Wings against p1's.
- **/where meanwhile:** no run happens before X1b is scored, so the /where fallback is built only if
  X1b fails. It would be bounded anyway: the typing guard refuses a 4th identical line in a row,
  and Batt's 2026-10-09 rule forbids filler lines to get past it.

### 4E. X1b round 2 pre-registration (written BEFORE its data; round 1 FAILED, section 5)

- **The design (frozen at this section's commit):** `selfpos.read_rect(..., light=True)`:
  - the opaque-glyph fallback of round 1 (after a base `no_glyph` / `uncovered_ink` only);
  - its light-cell guard narrowed to a HALF PAIR: a pixel at 41-170 followed by one at least
    max(12, 0.5 x (235 - the cell's floor)) above the floor and short of 235 (a digit fading in or
    out), instead of ANY 41-170 pixel (round 1's guard took the dark floor bands of mixed strips
    for that and refused the true reads);
  - the fallback is OPT-IN (`light=False` stays every caller's default: hunt_flow, the walk tools
    and T0's tools read exactly as before); only `dungeon_hunt` turns it on, and there a "light"
    read is USED only when the previous read (any mode) at most 1.0 s earlier agrees within the
    walk's reach (`dungeon_hunt.PosConfirm`): the synthetic blends show a digit changing over a
    mixed strip's dark band can still be read as a third digit (48 of 1,620), and such a frame
    lasts one codec frame.
- **Designed on:** round 1's 680 crops (all now seen: 616 base, 680 with the fallback, 0 wrong,
  in-sample) and synthetic sets (8 floors x 90 digit pairs x 2 places x 3 weights; still readouts
  320/320; the round-1 guard reads none of three synthetic band-in-cell readouts, this one all).
- **Data, FRESH:** `selfpos_light.py collect --map xmas_dun02 --cells midpoints --out
  /dev/shm/poring-lab-tmp/x1b-r2 --per-stand 8`: the cell halfway along each of the edge loop's 85
  legs (none is a waypoint), the same protocol and truth rule as round 1. ALL its crops are held
  out (nothing is fitted on them); scored ONCE (`score ... --split all`).
- **Bars (pooled over the fresh crops):**
  - **R1:** 0 wrong reads, light-mode reads included, on light and dark strips.
  - **R2:** >= 90 % exact on the light-strip crops (scene median >= 170), with at least 24 such
    crops (3 stands); fewer = INCONCLUSIVE, not a pass.
  - **R3:** dark-strip crops: exact >= the base reader's on the same crops, 0 wrong.
  - **R4 (T0's guard, the fallback ON):** `selfpos_eval.py --light` on T0's held-out sessions
    (outdoor-c, outdoor-d, indoor-c) still passes T0's bars (>= 99 % exact standing, >= 97 %
    within one cell walking), and the fallback's own reads (mode "light") have 0 wrong on
    STANDING frames; its walking-frame misreads are reported (PosConfirm's job, not a bar).
- **Then, not a bar:** pilot p2 (15 min, unrecorded, the runner with PosConfirm): position-unread
  Fly Wings, unconfirmed light reads (`run_end.pos_light_unconfirmed`), position-jump hard bars,
  against pilot p1.

### 4F. X1b round 3 pre-registration (written BEFORE its data; round 2 FAILED, section 5)

- **The design (frozen at this section's commit):** round 2's, with ONE change: a light cell is
  refused only with at least **3** half pairs in it (`selfpos.HALF_PAIRS_MIN`), not one: a
  blended stroke spans its rows, while a floor seam beside bright tiles makes 1-2 (round 2's
  only miss, 7,224, had 2). Still opt-in; still confirmed by a second read in `dungeon_hunt`
  (`PosConfirm`).
- **Designed on:** rounds 1-2 (1,360 crops, all seen: every variant 1,360 / 1,360, 0 wrong) and
  synthetic blends over pale and banded floors (1,080: a third digit read 37 times without the
  guard, 20 at >= 3 pairs, 23 at >= 4, 39 at >= 6). The blend unit test now asks for None or one
  of the two true values (it reads the old value, 166); a new test refuses a cell with a half
  stroke on 9 rows (guard off: it reads).
- **Data, FRESH:** `selfpos_light.py collect --map xmas_dun02 --cells quarters --out
  /dev/shm/poring-lab-tmp/x1b-r3 --per-stand 8`: the cells a quarter and three quarters along
  each leg, none used before (168 cells, ~1,344 crops), the same protocol and truth rule; scored
  ONCE (`--split all`) after the whole collection.
- **Bars:** R1-R3 of round 2 unchanged (0 wrong; >= 90 % exact on light strips with at least 24
  such crops, else INCONCLUSIVE; dark strips >= the base reader, 0 wrong); **R4** re-run with the
  new guard on T0's held-out sessions (T0's bars, 0 wrong fallback reads on standing frames).
- **Then, not a bar:** pilot p2 (as 4E).

### 4D'. Amendment D (2026-11-06 ~06:3x ICT): Batt's answers to the 23:47 report

(Named 4D' because 4D is X1b's pre-registration.) Batt's answers (received at the session's
start, `date` 06:24; Thai, translated):
1. **The position reader:** "Use it like this, and try to make it better too." The round-3 reader
   stays ON in the runner (opt-in + PosConfirm); improving it goes on with fresh cells (a later
   round, pre-registered before its data).
2. **The walk:** "Yes. It need not be exact: any number of cells, no limit, as long as it can walk.
   But since we have the map data, why not make the waypoints in advance, so we know a route that
   walks continuously, and after fighting a monster walk back to the waypoint and walk on?"
   - **That is already how the runner walks:** the 85 waypoints were made in advance from the map
     data (each leg a straight walkable run on the server map cache; xmas02-prep.md section 3),
     every walk click follows an A* path on the map's grid, and after a fight the patrol resumes at
     the next waypoint ahead (`resume_index`).
   - **What broke it is the no-entry cue (4G):** the walk gate read xmas_dun02's ORANGE floor as
     the client's red no-entry ring and cut 5 x 5 blocks out of that map grid, until no waypoint
     routed and the runner flew. The fix keeps the map's route as the ground truth (4G).
   - Moving the loop off the walls (allowed, "no limit") is held until pilot p3 says whether the
     walk still jams with the fix: one change at a time.
3. **The "Chat" tab name across a client restart:** "check it" -> checked 06:38-06:39: it SURVIVED
   (section 5).

### 4G. Pilot p3 pre-registration: the walk with the no-entry RING (written BEFORE its run)

**The diagnosis (offline, design data, 2026-11-06 06:3x-06:5x):**
- p2 + X2: 254 of 894 walk decisions (28.4 %) were no-entry carves (p2 138 / 414, X2 116 / 480;
  p1 33 / 87), each a 5 x 5 block (`CARVE_R` 2) out of the route grid; 12 dead-end Fly Wings in
  35 min. The first p2 dead end (96 s): carves from 12,28, then 891 route-less waypoint skips.
- The picking model names the TARGET cell itself for 226 of p2 + X2's 254 no-entry hovers: the
  client was not refusing a wall.
- X2's recorded frames (1 fps, the nearest within 0.6 s of each hover; 101 of the refused hovers):
  the cursor is a plain walk arrow over xmas_dun02's ORANGE floor tiles (R 177-255, G 53-90, B
  8-40), which pass the old cue (R >= 170, G and B <= 90, >= 25 pixels anywhere in the 64 x 64
  crop). 5 of them show the real ring.
- The real ring is PURE red (its pixels G <= 11, B <= 18 at p95; the floor's G >= 53 at p5) on a
  fixed circle: cursor@1's 1,170 ring grabs (the NAS's prontera / prt_church probe sessions of
  2026-10-09, robust2's ring as the label) fit radius 18.0 px around (+4.5, +11.5) px from the
  hotspot, |d - R| p95 0.93 px.

**The change (dungeon@8.6, at this section's commit):**
1. The no-entry cue is the RING (`ring_score` / `ring_seen`): pure-red pixels (R >= 170, G and B
   <= 40) within 2.5 px of that circle, at the best centre within +-3 px, in an 80 x 80 crop at the
   hotspot; a no-entry when >= 120 of them and <= 20 pure-red pixels just outside the circle
   (3.5-10 px out: a red carpet or a stocking fills it). The old count is still logged (`red`)
   beside the ring (`ring` = [on, out, dx, dy]) on every walk record, and up to 40 crops where the
   two disagree are kept in the session dir.
   - Design data: cursor@1's ring grabs score >= 188 with 0 outside; its 13,800 other grabs 0;
     X2's frames: the 6 rings 194-214 with 0 outside; the red scenery (stockings, carpets) <= 101 on
     the circle, or >= 16 outside it.
2. A no-entry carves its ONE cell (`NOENTRY_CARVE_R` 0; the stall carve keeps 5 x 5).
3. A dead end first forgets every carve and re-plans on the map's grid (`dead_end_step`: at most
   once per 60 s); only a dead end with nothing to forget, or within 60 s of the last forget,
   flies.
- Tests: the ring on an orange floor, over the void and on stone; a 2 / -3 px shift; a red carpet
  refused; the old cue firing on the orange floor alone (the positive case of the bug); the
  one-cell carve; the forget-before-fly order. `walk_judge.py` (new) counts the walk; its positive
  case on the real sessions: p2 7 dead-end Fly Wings and 138 / 414 carves, X2 5 + 2 and 116 / 480.

**The run:** pilot p3, the p2 command with `--label xmas02-p3`: `dungeon_hunt.py run --char rogue
--map xmas_dun02 --strategy P2 --search patrol --walk-trust --npc-guard --miss-cue --loot trim
--clear-map --minutes 15 --seed 20261105 --label xmas02-p3`; the round-3 reader with PosConfirm;
the Rogue immune (`collect_v2.py immune-on`, read on its screenshot: the relog of 06:39 cleared
it); a judged screenshot first; unrecorded. Judged once after the run by `walk_judge.py` and
`dungeon_judge.py row`.

**Bars (each against p2 + X2):**
- **W1 (primary):** dead-end Fly Wings <= 2 in the 15 min (p2 7, X2 5 in 20).
- **W2:** no-entry carves <= 10 % of the walk decisions (p2 33.3 %, X2 24.2 %).
- **W3, the ring's live check:** of the clicks the old cue would have carved (red >= 25, no ring),
  <= 10 % followed by a stall at their cell (a stall = a ring the rule may have missed); judged only
  with >= 20 such clicks, else reported.
- **W4:** the hard bars pass (packets: 0 NPC contact, 0 attack on a non-monster, no map change but
  our own Fly Wings).
- **Reported, not bars:** waypoints reached per minute (p2 2.07, X2 4.45), the forgets, the stalls,
  engagements and kills, the kept crops judged by eye, position None share.
- **A FAIL of W1-W3** leaves dungeon@8.6 un-adopted for the patrol (the runner's default stays
  until a verdict) and is reported with its cause; the route offset (Amendment D 2) is the next
  candidate.

### 4H. Pilot p4 pre-registration: no walk click straight north (written BEFORE its run)

- **Why:** p3's packets (section 5): the client sent no move request for 93 of 95 walk clicks at
  (0, +7) and 5 of 6 at (0, +6), but for 32 of 33 at (+-1, +7); on gef_fild10 (0, +7) 108 / 325
  were unsent, (+-1, +7) 0 / 88, (0, +5) 0 / 24. Those clicks made p3's stalls (38) and forgets.
- **The change (dungeon@8.7, at this section's commit; one change):** `column_dodge`: a walk
  target straight north of us (our column, >= 6 cells up) moves one cell sideways (toward a later
  path cell first) when that cell is on the route grid, not carved, in view and crosses no zone;
  else 5 cells up in the same column; else unchanged. The hover reads the cell that is clicked;
  the walk record carries `dodge`. Tests: both sides, the side toward the path, the one-cell
  corridor's 5-up, nothing usable, every other target unchanged, the hover after the dodge.
- **`walk_judge.py` now also reads the session's packets (offline):** unsent walk clicks and the
  straight-north ones. Positive case on the real sessions: p3 124 unsent of 456, 100 straight
  north of which 98 unsent; X2 49 / 363, 32 (31); p2 42 / 275, 32 (30).
- **The run:** pilot p4, the p3 command with `--label xmas02-p4` (dungeon@8.7); the Rogue still
  immune from its 06:59 `@monsterignore` (no relog since; read on the judged screenshot first);
  unrecorded. Judged once after the run by `walk_judge.py` and `dungeon_judge.py row`.
- **Bars (against p3):**
  - **M1 (primary):** walk clicks without a move request <= 10 % (p3 27.2 %).
  - **M2:** straight-north walk clicks (dx 0, dy >= 6) <= 2 (p3 100).
  - **M3:** stalls <= 19 (p3 38).
  - **M4:** 4G's bars still hold: dead-end Fly Wings <= 2, no-entry carves <= 10 % of the walk
    decisions, hard bars pass.
  - Reported: waypoints reached per minute (p3 5.27), the dodges by kind, forgets, engagements,
    kills, position None share.
- A FAIL keeps dungeon@8.6 as the patrol's runner, with the cause reported.

### 4I. Run p5: the reader's live outcomes (a MEASUREMENT, no bar; written BEFORE its run)

- **Why:** Batt (Amendment D 1): "use it, and try to make it better". Round 3's 16 misses were 2
  cells x 8 crops: at 7,221 the fallback read all four digits right and the half-pair guard refused
  them (an orange object's texture behind the digits); at 7,233 the floor itself reached 249
  (strokes go down to 242), so the "2" lost its template match. Rounds 1-3 are design data now.
  Which failure costs the runner positions LIVE is not known: the HP read logged only the last
  known cell.
- **The change (logging only, no behaviour change; at this section's commit):** every main HP read
  logs `rd`, its readout outcome: `base` / `light` (accepted), `unconfirmed` (PosConfirm held a
  light read back), `settle` (no read after a Fly Wing), or `<mode>:<reason>` for a failed read
  (`light_failed:<the fallback's own reason>`, kept as `Reading.light_reason`).
- **The run:** p5, the p4 command with `--label xmas02-p5` (dungeon@8.7 + this logging); the Rogue
  immune; unrecorded. Reported: the outcomes' counts and where (cells) the failures sit; 4H's
  walk numbers again (a second sample of dungeon@8.7, not a bar). The reader's next round is
  designed from these counts and pre-registered before ITS data, on fresh cells.

### 4E'. Amendment E (2026-11-06 ~08:2x ICT): Batt's answers to the 08:12 report

(Named 4E' because 4E is X1b round 2.) Batt's answers (Thai, translated):
1. **A detector for this map on the GPU, if X2 shows v1 does not see its monsters:** "Go ahead,
   approved." The GPU pause of 2026-10-29 is lifted FOR THIS (training a detector for
   xmas_dun02); every GPU step keeps R1-R3 and the R2 co-tenant rule (fit-first's VTON stays the
   top priority, never touched), through guarded_build only. The training plan is written and
   pre-registered before any GPU step.
2. **The reader:** "Why not look at the minimap? It shows the coordinates all the time." -> the
   reader DOES read exactly those coordinates (the "268 107" under the minimap); what fails is the
   machine read of white digits over a floor as bright as they are (4I, design notes). Answered in
   the report, with the options (the runner never lacked a position in p3-p5).
3. **The straight-north click fix for the other runners:** "ok", with an A/B test before use
   (4K).

### 4J. X2's scoring: the readings fixed BEFORE the score (written before any X2 box or truth is computed)

The tooling (xmas02-prep.md 7, merged from feat/x2-score) needs three readings of 4A that 4A does
not spell out. Fixed here, before the score:
- **"Boxes inside the UI windows are left out"** = a detection at least half behind the session's
  UI windows is left out (`--ui-boxes drop`), the labels' own in-view rule mirrored; the output
  counts the boxes left out and how many of them were true. A window lying wholly inside another
  (notice_left inside the standard chat window) is counted once.
- **The truth is checked BY EYE before the score is read:** the predicted truth boxes (`--pairs`)
  drawn on >= 10 X2 frames spread over the session. If they visibly miss the monsters' sprites
  (the outdoor camera and the GAT heights were only ever checked on gef_fild10), the score is NOT
  read (INVALID) and the projection is fixed first.
- **Hallucination:** X2's packets hold no status_change event, so Hallucination frames cannot be
  flagged; reported as "not observable", never as "none cast".

### 4K. hunt_flow v56: the GM's own screen column, an A / B (written BEFORE its run)

- **Why (Amendment E 3, Batt "ok" with an A / B):** hunt_flow (the prt_fild08 runner; ADOPTED v55)
  clicks the same dead pixels. Its 8 v54 / v55 sessions (2026-10-21/22, packets): walk clicks within
  5 px of the GM's column (u 640.5) sent no move request 217 times of 784 (27.7 %); all other
  walk clicks 17 of 9,055 (0.19 %). Above the GM (v 160-239) within 4 px: 275 of 439; 5-10 px
  aside: 0 of 65. So the dead band is a few px wide, narrower than a cell.
- **The change (v56 at this section's commit):** `PARAMS[56]` = v55 as ADOPTED (its fast scan on
  every k) + `col_nudge`: a walk click within COL_HALF 5 px of the column is put COL_NUDGE_PX 9 px
  east of it (inside the same cell, ~28-32 px wide there) -- in `walk_click`, before its zone
  check, so every walk click passes it. The A / B (`col_nudge_ab`): the column clicks alternate,
  even ones nudged ("nudged"), odd ones as before ("ab_off"); logged as `col` on the click.
- **The judge:** `walk_judge.py <session>` on a hunt_flow session: `column_ab`, each arm's clicks
  with no move request (`self_move_request` within -0.3 .. +0.6 s). Its positive case: the 8 v54 /
  v55 sessions give "column" 217 / 784, "other" 17 / 9,055.
- **The run:** `hunt_flow.py run --version 56 --minutes 30 --seed 20261106` on prt_fild08, the GM
  (the client restarted onto the GM's card; the Rogue logs out), immune (`collect_v2.py immune-on`
  + the screenshot read + `immune-confirm`), the hunting state rebuilt by the runner itself, a
  judged screenshot first, the live hard-bar monitor (`hardbar_live.py watch 56 --pid`) beside
  it; then `flow_judge.py bot` and `walk_judge.py`.
- **Bars:**
  - **K1 (primary):** "nudged" column clicks without a move request <= 5 %, AND "ab_off" >= 15 %
    (the dead band showing in this run), each arm >= 15 clicks; else INCONCLUSIVE (a second run).
  - **K2:** the hard bars (the monitor and flow_judge): 0 NPC contact, 0 map change, 0 unknown UI
    stop, 0 damaging hit on a non-target other than a Creamy (Creamy hits counted apart).
  - **K3:** the other walk clicks without a move request <= 1 % (no side effect).
  - Reported, not bars (one run): kills / h, landing, seen per 10 min.
- **Adoption:** K1-K3 pass -> v57 = v56 with `col_nudge_ab` off, `hunt_config.ADOPTED_VERSION`
  57. A FAIL keeps v55.

### 4F'. Amendment F (2026-11-06 ~10:45 ICT): Batt's answers to the 09:42 report

Batt's words, translated (before 10:49:46, the turn's first `date`):
1. **The bottom-left "up" icon:** "I know: press Alt+S, the skill window comes up and the icon goes.
   If it is the 'up' icon at the bottom-RIGHT, press Alt+A: the status window comes up and the icon
   goes. Then close those windows with the same shortcut again. Test it too."
   - Tested live 10:53 and 10:59 (Alt+S: the Skill Tree opened, the icon went at once; ui_gate
     closed the tree by its own chord; the icon stayed gone). Note: the icon is drawn ON TOP when
     it appears; a later focus on the chat window draws the window over it (dim, half covered).
   - Built (f91ab44): gm_state's skill-point icon template SKILLUP_BOX (0, 676, 44, 44), cut 10:59,
     held out on 18 frames of the morning (`gm_state.py notice-shares`: 9 / 9 with the icon at
     share 1.000, 9 / 9 without at <= 0.481; bar 0.8); clear_notices opens each notice's OWN window
     (skills for this icon; status for the badge and the bottom-right icon), one at a time;
     `gm_line` clears a level line's notices before the next typed line.
   - Live end-to-end 11:04-11:07: both icons made by GM lines (`@baselevelup 1`, `@joblevelup
     1`), then `ensure_hunting`: the first step cleared both (skills, then status), the rebuild's
     `@baselevelup -29` icon went by the status window, the restore's `@joblevelup -49` icon by the
     skill window before `@heal`; the GM back at Base 70 / Job 1, weight 814 / 4970 (STR 99), no
     notice.
2. **The disk:** "unblock it now, tell HA too; I set the margin to 100 GB so we don't bother HA
   often" -> the recorder floor is 100 GB (8b46640, ADR-0010 Amendment 2026-11-06); HA told
   (SendMessage, information only).
3. **The detector plan:** "go ahead, training may start, start the plan now" -> xmas02-detector.md
   Amendment A (2caa8fa).

**hunt_flow v56 run 2 resumes on this fix:** attempt 4 = 4K's command with `--seed 20261107`
(as fixed in section 5 before attempt 1), the immunity of the 09:35 login (still confirmed:
`collect_v2.py immune-status`), the hunting state as left by the 11:04 test, a judged screenshot
(11:12). Attempts 1-3 stopped in setup before any hunting: nothing of theirs is pooled. K1 and K3
are judged on runs 1 + 2 pooled, K2 per run (section 5's rule).

### 4L. Pilot p6 pre-registration: the box watcher on the xmas_dun02 model (written BEFORE its run)

- **Why:** Batt 2026-11-07 ~05:5x: "use it" (xmas02-detector.md Amendment J). With v1 the box
  watcher saw nothing true here: p4's 8 and p5's 5 box engagements found no SWORD (X2: v1's precision
  0.015), so the runner fought only what its walk cursor read; p4 1 kill, p5 0.
- **The change (T-11, at 8d2ab43; the one change):** `BoxWatch` takes `unit_detector.for_map
  ("xmas_dun02")`. That is the xmas02 ONNX (sha256 pinned), its four species collapsed to
  `monster` in one NMS group, at 16 threads (Batt's decision, every UnitDetector). The rhythm
  (BOX_EVERY_S 1.0, BOX_FRESH_S 1.5), the engagement rules and every walk rule are unchanged.
  `--box-model v1` is the rollback.
- **The run:** pilot p6, p4's command with `--label xmas02-p6`: `dungeon_hunt.py run --char rogue
  --map xmas_dun02 --strategy P2 --search patrol --walk-trust --npc-guard --miss-cue --loot trim
  --clear-map --minutes 15 --seed 20261105 --label xmas02-p6`.
  - The Rogue IMMUNE: `collect_v2.py immune-on`, then `immune-confirm` on its screenshot. This
    login (150004) has no confirmed ON.
  - A judged screenshot first; unrecorded.
  - Judged once after the run by `dungeon_judge.py row` and `walk_judge.py`.
- **Bars (against p4 / p5, the same command with v1):**
  - **D1 (primary):** kills (packets) >= 10 in the 15 min (p4 1, p5 0).
  - **D2:** box engagements that end as a box miss (no SWORD found) <= 50 % (p5 5 / 5).
  - **D3:** the hard bars pass (0 NPC contact, 0 attack on a non-monster, no map change but the
    setup's and the end's), and the walk holds: 0 dead-end Fly Wings, stalls <= 10 (p4 3, p5 4).
  - Reported:
    - engagements by kind, strikes and how many landed;
    - the box watcher's frames;
    - waypoints a minute;
    - kills an hour, items picked / stolen.
- A FAIL keeps the deployment as Batt decided. The cause is reported, and any change is
  pre-registered before its own run (never tuned on this one).

### 4M. Pilot p7 pre-registration: dungeon@8.8, the box strike (written BEFORE its run)

- **Why:** p6 (section 5) failed D1 / D2. 16 of 19 box fights hovered only the 8 cells around
  us (the defend ring), while the boxed monster stood 1.5-3.5 cells away (box feet 48-108 px). The
  boxes came from a camera still walking (~6 cells a second, boxes kept up to 1.5 s).
- **The change (dungeon@8.8 at 0056948; the one change, `--box-strike`, off by default):** a
  box-started fight first waits until our walk has ended (BOX_SETTLE_S 1.2 s after the last walk
  click), then for a box GRABBED AFTER that (`BoxWatch.wait_fresh`, <= 1.8 s). It takes the nearest
  one within BOX_TARGET_PX 220 (~6 cells) and hovers its centre, then its body point (foot -
  BODY_UP). A SWORD there is the strike (`by: box`) and the lock; otherwise the ring scan runs as
  before. Once per box fight; a `box_target` event logs it.
- **The run:** pilot p7 = the xmw3 recording (xmas02-detector.md Amendment K: TRAIN-walk; a runner
  change between sessions does not change a session's role). p6's command with `--box-strike
  --minutes 20 --label xmas02-xmw3`, the recorder beside it (Amendment K's chain), the Rogue
  immune (toggled and judged first), a judged screenshot first. Judged once after the run by
  `dungeon_judge.py row` and `walk_judge.py`.
- **Bars (against p6, the same command without `--box-strike`; per hour, the runs' lengths differ):**
  - **E1 (primary):** kills (packets) >= 40 / h (p6 4.0 / h, p4 4.0 / h).
  - **E2:** box fights ending as a box miss <= 50 % (p6 84 %).
  - **E3:** the hard bars pass, 0 dead-end Fly Wings, stalls <= 13 (p6 5 in 15 min).
  - Reported:
    - `box_target` outcomes: fresh / no box / no SWORD / struck, the settle and wait times, the
      distances;
    - strikes by kind and how many landed;
    - waypoints a minute;
    - items stolen / picked.
- A FAIL keeps `--box-strike` off (the runner's default). The cause is reported, and any next change
  is pre-registered before its own run.

### 4N. Pilot p8 pre-registration: dungeon@8.9, a detection on demand + the GPU (written BEFORE its run)

- **Why:** p7 (section 5) failed E1 / E2 because the boxes were right but old by the hover. 13 of
  18 boxed monsters had walked 100-200 px away; a box still sat on its monster 72 % of the time
  at the grab, 50 % 0.4 s later and 28 % from 0.8 s on. The wait was the 1-s rhythm plus a
  200-340 ms CPU detection, then two hovers of ~0.35 s each.
- **The change (dungeon@8.9 at 61a04ca; flags, the defaults unchanged):**
  - `--box-now`: after the settle the box target asks the watcher for a detection NOW
    (`BoxWatch.fresh_now`: its grab starts after the request), and hovers ONCE, at the box
    centre;
  - `--box-detector ab`: the watcher's background detections run on the GPU's detect server
    (gpu-live-detector.md option A, Batt 2026-11-07: "เลือก A", the GPU may replace the CPU),
    the CPU behind it. The box target's fresh detection ALTERNATES by box-target index: even =
    GPU, odd = CPU (`box_arm`).
- **The run:** pilot p8 = p7's command (the xmw chain's runner line) with `--box-now
  --box-detector ab --minutes 30 --label xmas02-p8`:

      nice -n 10 uv run --quiet python scripts/dungeon_hunt.py run --char rogue --map xmas_dun02 \
          --strategy P2 --search patrol --walk-trust --npc-guard --miss-cue --loot trim \
          --clear-map --minutes 30 --seed 20261105 --label xmas02-p8 \
          --box-strike --box-now --box-detector ab

  - Beside it, the detect server as ONE guarded long step (`unit_detector.py serve-cmd
    --seconds 2700`): R2 pre-start, R3's paired 180-s windows by `docker pause` (the GPU arm
    falls back to the CPU in OFF windows: logged per detection), the IO guard
    (`--threshold 30 --sustain 30`), a verified stop. Started first, the runner once it listens.
  - No recorder: the GPU step's IO guard stays quiet. The Rogue immune (checked by the toggle and
    its answer), a judged screenshot first. Judged once after the run by `dungeon_judge.py row`
    and `walk_judge.py`, and the box targets from `events.jsonl`.
  - It runs only if section 6 of gpu-live-detector.md passes P1 (parity) and the acceptance.
- **Bars (against p7, per hour where lengths differ):**
  - **E1 (primary, as 4M):** kills (packets) >= 40 / h (p7 12.0 / h).
  - **E2:** box fights ending as a box miss <= 50 % (p7 76 %).
  - **E3:** the hard bars pass, 0 dead-end Fly Wings, stalls <= 39 / h (4M's 13 in 20 min).
  - **G1 (the GPU live):** the box watcher returns boxes to the end (no dead watcher). Of the
    detections asked of the GPU while the worker was NOT paused (outside R3's OFF windows, by the
    step's `R3 pause` / `R3 unpause` lines), >= 90 % are the GPU's.
  - **G2 (the latency):** the box targets' fresh detection, request to boxes
    (`boxes_after_ms`), p50 <= 100 ms when the GPU served it, and at most half the p50 of those
    the CPU served.
  - Reported per arm and per path (assigned and as served; too few for a verdict): fresh
    detections, a box found, the hover's verdicts (SWORD share), struck, `hover_from_grab_ms`,
    `det_ms`; R3's pairs and verdict over the run; the fallback reasons; relaxed drops.
- **Decisions:**
  - E1-E3 PASS: `--box-strike --box-now` become the runner's defaults (a follow-up commit).
  - G1 + G2 PASS: `--box-detector gpu` becomes the default for runs beside a detect-server
    step (the CPU behind it whenever none runs).
  - A FAIL keeps that default off; the cause is reported, and any next change is pre-registered
    before its own run.

### 4O. Offline study S1 (p7 + p8): why every lock ends "no hits", and walking sight (written BEFORE it is read)

- **Why:** p7 and p8 ended every lock "no hits" (7 / 7, 16 / 16; section 5), while the packets
  count kills (4, 6). Batt 2026-11-07 ("ได้"): study it offline before any runner change.
  Amendment L of xmas02-detector.md (Batt delegated): walking sight is judged from the live runs.
- **Data, read only:** the two sessions' `events.jsonl`, `packets.jsonl.gz` (offline ground
  truth), `battle_log_live.jsonl`, and p8's `detections.jsonl`; one clock (`t_mono_ns`). The
  scorer is committed as `scripts/lock_study.py` with a test, before its numbers are reported.
- **Per strike (p7 7, p8 16):** the target = the `target_gid` of our first `attack_request` within
  2 s after the strike's first click (none: class D). Measured from the click: the first request,
  our first damage act on that target, the runner's unlock, the target's vanish (died or out of
  sight). Each strike gets ONE class, first match wins:
  - **K** the target died before the unlock (a kill);
  - **A** we hit it before the unlock, yet the runner saw "no hits" (the reader or its use);
  - **B** our first hit came only after the unlock (the 3.5-s rule cut an approach);
  - **C** requests but no hit on it within 25 s (it walked off, or we could not reach it);
  - **D** no attack request after the click.
- **The reader:** of our damage acts in both runs, the share with a Battle Log damage line in
  [act, act + 2.0 s], and the lag p50 / p95; experience-gain packets vs the reader's experience
  lines (the runner counts kills from those lines).
- **Walking sight, first step (p8):** each box engagement's triggering detection, classed by
  whether we were walking at its grab (a `self_move` of ours within the 1.0 s before); per class:
  engagements, strikes, kills of the struck target. Monsters in reach that were never boxed need
  the truth projected on screen: a second step, pre-registered on its own.
- **Use:** descriptive, no bar. The class counts name the next runner change (A: the reader, B: the
  lock timer while closing in, C: the target choice, D: the strike click), pre-registered before
  its own run. Nothing live changes from this study.

### 4P. Pilot p9 pre-registration: the Rogue NOT immune, Myst Cases kept (written BEFORE its run)

- **Why:** S1 (4O): 9 of 23 strikes in p7 + p8 hit Myst Cases that TELEPORTED after 2-4 hits
  (rAthena: AL_TELEPORT, idle, on `rudeattacked`; most likely because the immune Rogue cannot be
  targeted). Batt 2026-11-07 ~15:2x: "turn immunity off, and do not skip Myst Case: it is the map's
  important monster; what is stolen from it sells high."
- **The one change against p8: no immunity.** The runner is p8's dungeon@8.9 with
  `--box-strike --box-now` and the GPU box watcher (`--box-detector gpu`, the default since p8's
  G1 / G2). p8's ab arms are not repeated: G2 already measured them. Nothing else changes; the
  2.0-s fight end (S1 follow-ups) is NOT in this run.
- **The run:**

      nice -n 10 uv run --quiet python scripts/dungeon_hunt.py run --char rogue --map xmas_dun02 \
          --strategy P2 --search patrol --walk-trust --npc-guard --miss-cue --loot trim \
          --clear-map --minutes 30 --seed 20261105 --label xmas02-p9 --box-strike --box-now

  - Before it: immunity toggled OFF with `crusader.py --char thief gm --job rogue
    '@monsterignore'`, judged by the answer over the character on a screenshot ("Returned to
    normal state." = now off), then a judged screenshot of the client.
  - Beside it: the detect server as one guarded `execdev:vision` step (2400 s), started first.
  - After it: immunity back ON (toggled and judged), the Rogue's resting state as before.
  - P2 keeps the Rogue alive by itself: a White Potion below 40 % HP, a Fly Wing below 20 % or
    under fast damage; 30 potions and 19 Fly Wings in stock. A death is a RESULT (the run stops,
    the cause recorded), never retried.
- **Bars (E1-E3 as 4M / 4N, per hour):**
  - **E1 (primary):** kills (packets) >= 40 / h (p7 and p8: 12.0 / h).
  - **E2:** box fights ending as a box miss <= 50 % (p8 64.7 %).
  - **E3:** the hard bars pass, 0 dead-end Fly Wings, stalls <= 39 / h.
  - **M1 (the hypothesis):** of the strikes on Myst Cases, <= 20 % end with the Myst Case
    teleporting (vanish reason 3 after our hits). p7 + p8 under immunity: 9 / 9.
  - **D1:** 0 deaths.
  - Reported:
    - the S1 classes (`scripts/lock_study.py`);
    - kills and teleports by species (packets);
    - damage taken and potions drunk;
    - items per hour (the judge's items: snatched / picked);
    - R3 over the detect-server step.
- **Decisions:**
  - M1 passes: immunity stays off for xmas_dun02 runs (Batt's direction), Myst Cases stay targets;
  - E1 / E2 still fail: the next change is the fight end (S1 follow-ups), pre-registered on its
    own;
  - a death, or D1 failing: the next run's survival is studied before any other change.


### 4Q. Pilot p10 pre-registration: --walk-stop for the clicks that started no attack (written BEFORE its run, 2026-11-08 10:57:51 ICT)

- **Why:** Batt 2026-11-07: the no-attack clicks next, not immune. p9's class D = 9 of 25 strikes,
  each holding the fight a median **7.33 s** (67.1 s in all; `lock_study.py` `owned_s`).
- **Diagnosis (p9, offline: events + packets + the strike shots):**
  - **The clicks hit the ground.** In every class-D strike the client sent WALK requests (the
    first +0.36 s after the click), never an attack request. The monster kept hitting (and
    missing) the Rogue while the burst's 4 clicks walked her ~6 cells away from it.
  - **8 of 9 came from the defend scan (`by scan`).**
    - The scan hovers each ring cell's body point (26 px above the cell), north first
      (`ring(1)`'s order).
    - The north cell's body point lies on the Rogue's OWN body, inside the glow and the Miss text
      the client draws while she is attacked. A one-cell scan read SWORD there at the same pixel
      (641, 312) in #07, #08 and #13.
    - The shots: #07 had the Myst Case SOUTH of her, #13 had it ~3 cells away. In #19 (a kill at the
      same point) the Myst Case sprite covered her.
  - **A detector-box gate does not separate them** (tested offline on p9's own detections): the
    real swords were boxed no more often than the false ones (at most 3 of 7 vs 2 of 8). The
    detector misses monsters beside the Rogue, which is Batt's "it still does not see monsters
    well". Not taken.
  - **What does separate them:** a melee strike on a RING-1 cell attacks in place, so the scene
    never scrolls. A ground click walks, so it does. 7 of the 9 were ring-1 strikes.
- **The one change against p9: `--walk-stop` (dungeon@9.2, behind its flag, the fight paths scan /
  stall_scan / box / queue):**
  - after a ring-1 strike's click, `route_preview.scene_shift` (the camera's scroll, our character
    and the UI masked) is read on every poll;
  - >= 10 px on 2 polls in a row, before the lock arrow or our damage line, ends the strike:
    - "walked": no more clicks, no lock, a 0.4-s settle;
    - the defend scan skips that cell for 3 s, and the fight loop scans again;
  - ring-1 bursts re-click every 0.8 s instead of 0.6, so the check sees the first click's walk
    before a second click;
  - nothing else changes: no change to the cursor read, the ring order, the box path's choice,
    loot or walking.
- **The run** (p9's command + `--walk-stop`, label xmas02-p10, same seed):

      nice -n 10 uv run --quiet python scripts/dungeon_hunt.py run --char rogue --map xmas_dun02 \
          --strategy P2 --search patrol --walk-trust --npc-guard --miss-cue --loot trim \
          --clear-map --minutes 30 --seed 20261105 --label xmas02-p10 --box-strike --box-now \
          --walk-stop

  - Before it:
    - immunity toggled OFF with `crusader.py --char thief gm --job rogue '@monsterignore'`,
      judged by the answer ("Returned to normal state." = now off);
    - a judged screenshot of the client.
  - Beside it: the detect server, one guarded `execdev:vision` step (2400 s) in the Intel worker,
    started first. bot-server: no R3 pauses.
  - After it: immunity back ON (toggled and judged), the Rogue's resting state as before.
- **Bars:**
  - **E1 (primary, as p9):** kills (packets) >= 40 / h (p9 34.0).
  - **W1 (the hypothesis):** class-D strikes hold the fight a median <= 2.0 s (`owned_s`; p9
    7.33).
  - **W2 (it sees the walk):** >= 75 % of the ring-1 class-D strikes on the fight paths end
    "walked".
  - **W3 (it costs no real strike):** <= 1 "walked" strike that was not class D (an attack request
    came after all: a real strike cut short).
  - **E3:** the hard bars pass, 0 dead-end Fly Wings, stalls <= 39 / h.
  - **D1:** 0 deaths.
  - Reported:
    - E2 (box fights ending as a box miss; p9 62.5 %);
    - M1 (Myst Case teleports);
    - the S1 classes and each strike's scroll (`shift`);
    - kills by species, items per hour, damage taken, potions.
- **Scorers (committed before the run):**
  - `scripts/dungeon_judge.py`: E1 / E3 / D1, as p9;
  - `scripts/lock_study.py`: the classes, `owned_s`, and `walk_stop` = walked / walked_not_d /
    d_owned_s_p50 (tests in `test_lock_study.py`; p9 re-scored: d 9, d_owned_s_p50 7.33).
- **Decisions:**
  - W1-W3 pass: `--walk-stop` stays ON for xmas_dun02 runs;
  - W3 fails: no reuse until the scrolls of the cut strikes are studied;
  - W2 fails: the logged `shift` series decide the threshold before any reuse;
  - E1 still failing names the next change (sight: the walking-started box fights, 2 strikes of
    15 in p9).


### 4R. Pilot p11 pre-registration: --self-recheck, a sword on the Rogue's own sprite must persist (written BEFORE its run, 2026-11-08 12:04:07 ICT)

- **Why:** Batt 2026-11-08 chose option (a) after p10 (section 5): the defend scan's N / S body
  points lie on the Rogue's own sprite, and SWORD reads there were ground or own-cell clicks:
  - p9: 6 of its 10 own-body strikes were class D;
  - p10: 5 of 7 (`lock_study.py` `self_recheck.own_body_*`; the box is her feet point (641, 362),
    +-20 px wide, 95 px up, 6 px down).
- **What the sword there is NOT (measured, `cursor_sword` on real pixels):**
  - her aura alone reads 0.21-0.32 at the N / S points (p10's immunity shots);
  - the Miss text alone reads 0.37-0.55 (14 frames of the miss_cue template's recordings, with
    the hotspot at its corner, its centre, and 8 px out);
  - SWORD_MIN is 0.75. So a control read without the pointer would not catch it.
  - The sword there is TRANSIENT: an attacking monster's frame reaching her body point, or the
    arrow over her effects. The click 0.07 s later finds ground (p9) or her own cell (p10).
- **The one change against p9: `--self-recheck` (dungeon@9.3, behind its flag):**
  - a defend-scan SWORD at a point inside her own sprite box counts only if a second read
    0.4 s later (`hover` again, two motions) is a SWORD too;
  - else that cell is skipped and the scan goes on;
  - each recheck logs both reads' sword recalls (event `self_recheck`).
  - Not in this run: `--walk-stop` (not adopted after p10), any detector change (the GPU
    preprocessing waits for its own parity check).
- **The run** (p9's command + `--self-recheck`, label xmas02-p11, same seed):

      nice -n 10 uv run --quiet python scripts/dungeon_hunt.py run --char rogue --map xmas_dun02 \
          --strategy P2 --search patrol --walk-trust --npc-guard --miss-cue --loot trim \
          --clear-map --minutes 30 --seed 20261105 --label xmas02-p11 --box-strike --box-now \
          --self-recheck

  - Before it: immunity toggled OFF and judged ("Returned to normal state."), then a judged
    screenshot of the client.
  - Beside it: the OpenVINO detect server, one guarded `execdev:vision` step (2400 s).
  - After it: immunity ON and judged ("You are now immune to attacks."); the Rogue at rest.
- **Bars:**
  - **E1 (primary, as p9 / p10):** kills (packets) >= 40 / h (p9 34.0, p10 24.0).
  - **R1 (the hypothesis):** own-body class-D strikes <= 1 (p9 6, p10 5).
  - **R2 (it costs no real strike):** defend-scan strikes that started an attack >= 7 (p9 7,
    p10 9).
  - **R3:** class D <= 25 % of strikes (p9 36 %, p10 48 %).
  - **E3:** the hard bars pass, 0 dead-end Fly Wings, stalls <= 39 / h.
  - **D1:** 0 deaths.
  - Reported:
    - rechecks and transient ones, with each pair of recalls;
    - class D by path (far `walk_sword` / `box` strikes are NOT this change's: p10 had 8);
    - `owned_s`, E2, kills by species, items, damage taken.
- **Scorers (committed before the run):** `dungeon_judge.py row`, `lock_study.py`
  (`self_recheck` + `walk_stop` + classes; tests in `test_lock_study.py`; p9 / p10 re-scored as
  the baselines above).
- **Decisions:**
  - R1 and R2 pass: `--self-recheck` stays ON for xmas_dun02 runs;
  - R1 passes, R2 fails (real strikes lost): the 0.4-s wait and the box are studied from the
    logged recall pairs before any reuse;
  - R1 fails: the recall pairs show whether the second read still sees the transient sword
    (then a longer wait, or a different point);
  - E1 failing names the next change: the far-target strikes (option b), then sight (c).
- ➡️ **Before the run (2026-11-08 12:35 ICT), two setup notes; the hunt itself is unchanged:**
  - The first start (12:07:20) refused at setup:
    - the Rogue's weight was 989 / 2430 = 40.7 %, at or over CLEAR_AT 40 %, and she never drops
      her Etc tab;
    - Batt chose "allow the Rogue up to 48 %": `CHARS_CONF["rogue"]["etc_hold_max"] = 0.48`
      (WEIGHT_MAX), `etc_hold_refused`, tested;
    - immunity had been toggled OFF for it, and was put back ON (judged) while waiting.
  - The detector's GPU conversion passed its parity run meanwhile (bot-server-migration.md 16a)
    and became the default. As promised above, this run's detect server is started with
    `--ov-preproc cpu`: the same detector as p9 / p10.


### 4S. Pilot p12 pre-registration: --still-strike, a far strike waits for a still scene (written BEFORE its run, 2026-11-08 13:40:22 ICT)

- **Why:** Batt 2026-11-08 chose option (b) after p11: far-target strikes (2+ cells) are the
  largest class-D share.
  - `lock_study.py far_strikes`: p10 13 far strikes (8 D), p11 22 (8 D).
- **Diagnosis (p10 + p11, offline: events + packets):**
  - Every far class-D strike's click sent a WALK request (+0.34 s), never an attack request,
    after a SWORD read at that point: `box_target` 320-360 ms after a fresh detection, or
    `walk_sword` during the walk's own hover.
  - **Walking decides it:** far strikes clicked while we walked (our `self_move` within 1 s
    before the click) started no attack in 10 of 14 (71 %); standing, in 6 of 20 (30 %).
    - box: 5 / 7 walking vs 3 / 11 standing;
    - walk_sword: 5 / 7 vs 3 / 9.
  - Moving, the client resolves a click at our SERVER position, ~0.5 s ahead of the frame we see
    (memory: frames-lag-server-half-second). The click lands cells off the sprite we hovered.
  - The box path's settle is a fixed 1.2 s after our last walk click, not a measured standstill:
    5 of its 7 walking misses came after it.
- **The one change against p11: `--still-strike` (dungeon@9.4, behind its flag):**
  - `wait_still()`: frames ~60 ms apart until 3 consecutive pairs scroll < 2 px
    (`route_preview.scene_shift`), at most 1.5 s;
  - the box path: its detection (box_now) is taken after that wait;
  - `walk_sword` far strikes: after the wait, the point is carried by the scroll seen meanwhile
    (scene_shift's sign tested) and hovered again; no SWORD there means no strike
    (`still_retarget`, logged);
  - ring-1 strikes are unchanged (they attack in place).
- **Kept from p11:**
  - `--self-recheck` ON (4R's decision);
  - the detect server with `--ov-preproc cpu` (as p11; the GPU conversion becomes this map's
    detector only after this run);
  - MVP tombstones off on the lab server (bdb2f1c4);
  - the Rogue's weight limit 48 % (588b4a16).
- **The run:**

      nice -n 10 uv run --quiet python scripts/dungeon_hunt.py run --char rogue --map xmas_dun02 \
          --strategy P2 --search patrol --walk-trust --npc-guard --miss-cue --loot trim \
          --clear-map --minutes 30 --seed 20261105 --label xmas02-p12 --box-strike --box-now \
          --self-recheck --still-strike

  - Before it: immunity OFF, judged ("Returned to normal state."), and a judged screenshot.
  - Beside it: the OpenVINO detect server, 2400 s, `--ov-preproc cpu`.
  - After it: immunity ON, judged.
- **Bars:**
  - **E1 (primary):** kills (packets) >= 40 / h (p11 43.9, p10 24.0).
  - **F1 (the hypothesis):** far class-D strikes <= 3 (p10 8, p11 8).
  - **F2 (it costs no real strike):** far strikes that started an attack >= 10 (p10 5,
    p11 14).
  - **F3 (the mechanism):** far strikes clicked while walking <= 2 (p10 6, p11 8).
  - **R1 (p11's gain holds):** own-body class-D strikes <= 1.
  - **E3:** the hard bars pass, 0 dead-end Fly Wings, stalls <= 39 / h.
  - **D1:** 0 deaths.
  - Reported:
    - the waits (still or capped, waited ms), the retargets and the lost ones;
    - class D by path, `owned_s`, E2, kills by species, items.
- **Scorers (committed before the run):** `dungeon_judge.py row`; `lock_study.py`
  (`far_strikes` = far / far_d / far_attacked / far_d_walking / far_walking / retargets /
  retarget_lost, tested; p10 / p11 re-scored as the baselines above).
- **Decisions:**
  - F1 and F2 pass: `--still-strike` stays ON for xmas_dun02 runs;
  - F3 fails: the still detector misses our motion (its thresholds), studied before reuse;
  - F1 fails with F3 passing: standing is not enough; the next idea is the click's aim (the
    target's own motion);
  - F2 fails: the wait loses real targets, so its cap or the retarget is revisited.

### 4S'. Amendment G (2026-11-08 ~15:4x ICT): Batt's answers to the 15:04 report

Batt's words, translated (before 15:43:36, the turn's first `date`):
1. **`--still-strike`:** "on" -> ADOPTED: it stays ON for xmas_dun02 runs (4S's decision rule
   asked for F1 + F2; F1 failed 6 > 3, so this is Batt's call on the run as a whole: kills 58.0 /
   h, far strikes that attacked 14 -> 23, no far click while walking).
2. **p13's one change:** "do 3" (the GPU detector with the conversion on the card) and "I focus
   on switching to the detector that converts on the card: make it fast" -> the detector path
   is profiled and sped up first (bot-server-migration.md 19: the card's clock floor, FP16, the
   host's decode and copies), each part box-parity checked, then p13 (4T) runs on it.
3. **The Rogue's weight (44.6 %):** "drop everything first, keep only what is needed: potions
   are hardly used, 10 bottles are enough, and the wings; drop everything else except what she
   wears" -> `dungeon_hunt.py clear-bag --char rogue` (new): every stack of the Etc, Use and Eqp
   tabs dropped on the clear stand (clear_etc's known path, generalised as clear_tab; worn gear
   is not in the inventory's list), then the run stock restocked by the run setup's own lines
   (`potions_to` 10 White Potions, `wings_to` 10 Fly Wings) and read back from the hotbar.
   The DB's last save before it (15:5x, read-only): White Potion 30, Fly Wing 19, Red Potion 5,
   Candy 5, Well-baked Cookie 9, Piece of Cake 10, Scell 25, Zargon 18, Iron 1, Manacle 4, one
   unidentified headgear (2251, not worn); worn: 1222 +8, 2103, 2224, 2335, 2405, 2505, 2608 x 2.
   - Done 16:30:34-16:32:25: Etc 4 stacks, Use 6, Eqp 1 dropped, each tab read empty; weight
     1084 -> 320 (the worn gear) -> 520 / 2430 after the restock; the hotbar read 10 / 10.
   - ➡️ A gap found at p13's start (16:33:42): the run's setup topped the stock back up to the
     STRATEGY's (P2: `@item 504 30`, `@item 601 20`), which outranked the Rogue's own 10. So
     p13 carried p12's stock (30 potions). Fixed after p13's start (`potions_win`, tested): from
     p14 on her setup keeps 10 White Potions; the Fly Wings stay at the strategy's 20. The bag is
     cleared again after p13.
4. **The media probe's build cache (~1 GB):** "keep it for now" -> kept (docs/operations/
   disk-audit.md).
5. **GPU-encoded recordings:** "interested, and I think it is the faster way too" -> a design
   (docs/planning/gpu-recording.md, a subagent) with a bench pre-registered before its numbers.

### 4T. Pilot p13 pre-registration: the fast GPU detector (written BEFORE its run, 2026-11-08 16:2x ICT)

- **Why:** Batt 2026-11-08 (Amendment G item 2): "do 3 ... make it fast".
- **The one change against p12: the detector path, faster, with the same boxes**
  (bot-server-migration.md 19):
  - the Arc's clock floor at RP0 (2450 MHz) while the run's detect server serves;
  - the conversion on the card (`--ov-preproc gpu`, 16a's parity), FP32 (fast16 failed its
    parity on v1, 58 / 59);
  - the host's copy-free call and faster decode (byte- and box-identical, tested).
  - p12's live detector: 1,811 calls, p50 64.7 ms (the numpy conversion, the card at ~800 MHz);
    its box path: the boxes 89 ms and the sword verdict 319 ms after the grab (p50, 19 struck).
    So the detector is ~1/4 of the grab -> verdict time; a moving target's miss (p12's 3 far box
    D) can shrink only by that part.
- **Kept from p12:** `--self-recheck` and `--still-strike` ON (Amendment G), MVP tombstones off,
  the weight limit 48 %, the same map, route, seed and flags.
- **Different, not a change of the bot:** the bag was cleared before it (Amendment G item 3;
  `clear-bag`), so the weight starts low; below 50 % weight changes nothing in the fight.
- **The run:**

      nice -n 10 uv run --quiet python scripts/dungeon_hunt.py run --char rogue --map xmas_dun02 \
          --strategy P2 --search patrol --walk-trust --npc-guard --miss-cue --loot trim \
          --clear-map --minutes 30 --seed 20261105 --label xmas02-p13 --box-strike --box-now \
          --self-recheck --still-strike

  - Before it: `clear-bag`, immunity OFF judged ("Returned to normal state."), a judged
    screenshot, the floor read back (`gt_min_freq_mhz` 2450).
  - Beside it: the OpenVINO detect server, 2400 s, `--ov-preproc gpu --ov-precision f32`; its
    start line must show `gpu_clock.min` 2450.
  - After it: immunity ON, judged.
- **Bars:**
  - **D1 (the change):** the live detector's call p50 <= 35 ms (`detections.jsonl`, path gpu;
    p12 64.7), and >= 99 % of the box watcher's detections by the GPU.
  - **D2 (its mechanism):** the box path's boxes after the grab, p50 <= 65 ms (p12 89).
  - **E1:** kills (packets) >= 40 / h (p12 58.0).
  - **R1:** own-body class-D strikes <= 1. **F3:** far strikes clicked while walking <= 2.
  - **E3:** the hard bars pass, 0 dead-end Fly Wings, stalls <= 39 / h. **Deaths:** 0.
  - Reported against p12: far class-D (p12 6, F1's bar 3), class D by path, the sword verdict
    after the grab (p50), still-waits, kills by species, items per hour, the server's stats lines.
- **Scorers:** `dungeon_judge.py row`, `lock_study.py`, and the detections / box_target summary
  as computed for p12 above (path counts, `ms` p50 / p95; `boxes_after_ms`,
  `verdict_from_grab_ms` p50).
- **Decisions:**
  - D1 + D2 pass and no regression bar fails: the fast path is the live detector on bot-server
    (the floor survives a reboot only once Batt installs `scripts/host/poring-lab-gpu-clock.service`);
  - D1 fails: the run's load hides the gain; the server's stats lines and the host's call are
    profiled live before it is reused;
  - a regression bar fails: studied (the detector should change no decision), the fast path kept
    out of the next run until then.

### 4T'. Amendment H (2026-11-08 ~18:0x ICT): Batt's answers to the 17:54 report

Batt's words, translated (before 18:06:52, the turn's first `date`):
1. **The clock-floor unit:** "install it, do it for me" -> installed 18:06:52
   (`scripts/host/poring-lab-gpu-clock.service`, enabled + active; stop -> floor 300, start ->
   2450, proven; bot-server-migration.md 19).
2. **The fast detector:** "use it" -> ADOPTED as the live detector on bot-server (`final`:
   the conversion on the card, FP32, the floor at RP0).
3. **Next pilots:** "aim for the monsters that are walking, and if possible repeat p13 to see the
   result with a normal spawn" -> p13r (4U: p13 unchanged), then p14 (the aim for a moving
   target, pre-registered after p13r with its own study).
4. **GPU-encoded recordings:** "try fixing the colours too" -> round 2 of the bench
   (gpu-recording.md; its amendment is written before its run).

### 4U. Pilot p13r pre-registration: p13 REPEATED, unchanged (written BEFORE its run, 2026-11-08 18:1x ICT)

- **Why:** Amendment H item 3. p13 met 31 monsters in sight against p12's 50 (kills per monster
  seen 0.55 vs 0.58), so its E1 says little about the bot. The same run again shows E1 with a
  normal supply, and is p14's baseline.
- **No change of the bot against p13:** the same code path, flags, map, route and seed; the
  detect server `final` (FP32, the conversion on the card), now with the floor from the installed
  unit.
- **Different, not a bot change:** the stock is the Rogue's 10 White Potions (`potions_win`,
  Amendment G; p13 carried 30, used 0); the bag starts cleared (weight ~21 %).
- **The run:** 4T's command with `--label xmas02-p13r`; before it immunity OFF judged and a judged
  screenshot; beside it the detect server 2400 s (its start line: f32, `gpu_clock.min` 2450);
  after it immunity ON judged, then `clear-bag`.
- **Bars:** 4T's, unchanged (D1 <= 35 ms and >= 99 % GPU; D2 <= 65 ms; E1 >= 40 / h; R1 <= 1;
  F3 <= 2; E3; deaths 0).
- **Reported:** the supply, `scripts/sight_supply.py` (committed before this run; its positive
  case is p12 / p13: 50 and 31 seen, 16.7 and 10.3 / 10 min, kills per seen 0.58 and 0.548), and
  4T's reported items.
- **Decisions:**
  - E1 passes: the fast path's kill rate holds with a normal supply; p13r is p14's baseline.
  - E1 fails with the supply at or above 14 / 10 min: studied before p14 (the bot changed).
  - E1 fails with the supply below 14 / 10 min again: the map's supply is studied (why fewer
    monsters appear) before p14 is compared to anything.

### 4V. Pilot p14 pre-registration: --lead-strike, the box path aims ahead of a walking target (written BEFORE its run, 2026-11-08 18:5x ICT)

- **Why:** Batt 2026-11-08 ~18:0x (Amendment H item 3): "aim for the monsters that are walking".
- **The study (offline, packets; `scripts/target_motion.py`, committed with this; its positive
  case is p12 + p13):** box strikes on a target WALKING at the grab: 6, of which 5 class D; on a
  STANDING target: 25, of which 1 class D (p13r: walking 3 / 1 D, standing 9 / 1 D). The walker
  moved 0.8-1.5 cells between the grab and the click (~1 cell): the click lands where it WAS.
- **The one change against p13r: `--lead-strike` (dungeon@9.5, behind its flag):**
  - after the box path's first fresh detection (on a still scene), a SECOND one `LEAD_GAP_S`
    (0.12 s) later; the same sprite = the box whose centre is nearest, within `LEAD_MATCH_PX` (40);
  - its velocity between the two grabs; at `LEAD_MIN_PX_S` (25 px / s) or faster it is walking
    and the hover point is its centre + velocity x `LEAD_T_S` (0.35 s: p13's hover -> verdict 232
    ms + the second detection ~45 ms + the stream ~70 ms), the lead at most `LEAD_MAX_PX` (64);
  - no SWORD at the led point: the sprite's current centre once (the fallback); a standing
    sprite: its current centre (as before, from the fresher detection);
  - no lead on a scrolling scene (`still` false) or without a match; each case logged.
  - Its cost on every box target: the second detection (~0.16 s).
- **Kept from p13r:** the fast detector, `--self-recheck`, `--still-strike`, the 10-potion stock,
  the same map, route, seed and flags.
- **The run:** 4U's command with `--label xmas02-p14 --lead-strike`; the same before / beside /
  after steps (immunity OFF judged; the detect server 2400 s, f32, floor 2450; immunity ON
  judged; `clear-bag`).
- **Bars:**
  - **M1 (the hypothesis):** box strikes on a target walking at the grab (`target_motion.py`):
    class D in at most 1 of them, with at least 3 such strikes; fewer than 3: INCONCLUSIVE (the
    next run repeats the flag and the two are pooled).
  - **M2 (no cost on standing targets):** box strikes on a standing target: class D <= 2.
  - **M3 (it engages):** the led hovers that read SWORD and were struck >= half of the led hovers
    (the `lead` records: walking, verdicts).
  - **E1:** kills >= 40 / h (p13r 44.0). **D1:** live detector p50 <= 35 ms. **R1:** own-body
    class D <= 1. **F3:** far clicks while walking <= 2. **E3:** hard bars pass, 0 dead-end Fly
    Wings, stalls <= 39 / h. **Deaths:** 0.
  - Reported: the supply and kills per monster seen (`sight_supply.py`), the lead records (speed,
    lead px, why none), the box path's timings (boxes / verdict after the grab), class D by path.
- **Decisions:**
  - M1 + M2 pass and no regression bar fails: `--lead-strike` stays ON for xmas_dun02 runs;
  - M1 fails with M3 passing: the lead lands on the sprite but the click still walks -> the
    timing (LEAD_T_S) or the click's own lag is studied before reuse;
  - M3 fails: the led point misses the sprite (the velocity or the lead is wrong) -> studied;
  - M2 fails: the extra detection costs standing targets -> studied before reuse.

### 4V'. Amendment I (2026-11-08 ~19:5x ICT): Batt's answers to the 19:48 report

Batt's words, translated (before 19:53:09, the turn's first `date`):
1. **p15 / p16 (his clip):** "do (a) first, then (b); and 6 cells is still too few: try striking
   within the range seen on the screen, ordered by the nearest monster" -> p15 = (a) the quick
   give-up (4W); p16 = (b) the patrol engages any monster box on the screen, nearest first
   (pre-registered after p15).
2. **`--lead-strike`:** "stop using it" -> dropped (off; p14's code stays, behind its flag).
3. **Recordings:** "try round 3" -> the GPU scaling / processing step (gpu-recording.md; its
   amendment before its run).

### 4W. Pilot p15 pre-registration: --quick-drop, a strike that does not connect is given up (written BEFORE its run, 2026-11-08 20:0x ICT)

- **Why:** Amendment I item 1, (a). Batt's clip: a missed strike held the Rogue ~7 s (the burst's
  3.0 s, then 3.5 s without hits of ours) while a Myst Case stood in view.
- **The measurement behind the numbers (p12-p14, 106 good strikes K / A, 36 class D):**
  - the arrow or our damage line shows by 2.0 s after the click in all but 6 good strikes; by
    1.5 s (Batt's "~1.5 s") in all but 23 (22 %), so the give-up is 2.0 s;
  - after an arrow, our first VISIBLE hit (the packet + the Battle Log reader's ~0.5 s) comes
    within 2.0 s in 57 of 58;
  - class-D strikes held 4.3-12.3 s (arrow-ended) and ~7 s (no arrow).
- **The one change against p13r: `--quick-drop` (dungeon@9.6, behind its flag):**
  - no arrow and no damage `QUICK_ARROW_S` (2.0 s) after the click: no lock;
  - an arrow, but no hit of ours `QUICK_HIT_S` (2.0 s) after it: the lock drops ("quick");
  - after either: the box path runs again (the nearest box within BOX_TARGET_PX), at most
    `QUICK_RETRY` (2) times a fight, then the ring scan as before. Each drop is logged.
- **Kept from p13r:** the fast detector, `--self-recheck`, `--still-strike`; `--lead-strike` OFF;
  the 10-potion stock; the same map, route, seed and flags.
- **The run:** 4U's command with `--label xmas02-p15 --quick-drop`; the same before / beside /
  after steps.
- **Bars:**
  - **Q1 (the hypothesis):** the time held on class-D strikes (`quick_drop_study.py`, committed
    with this; its positive case is p13r: 7 D, median 7.22 s, total 49.2 s): median <= 3.0 s AND
    total <= 25 s.
  - **Q2 (no cost):** quick drops of a strike that started an attack (K / A by packets) <= 3.
  - **E1:** kills >= 40 / h (p13r 44.0). **D1:** live detector p50 <= 35 ms. **R1:** own-body
    class D <= 1. **F3:** far clicks while walking <= 2. **E3:** hard bars pass, 0 dead-end Fly
    Wings, stalls <= 39 / h. **Deaths:** 0.
  - Reported: the supply and kills per monster seen (p13r 0.611), the drops by why and the
    re-armed box targets, class D by path.
- **Decisions:**
  - Q1 + Q2 pass and no regression bar fails: `--quick-drop` stays ON; p16 (Amendment I's (b))
    builds on it;
  - Q1 fails: the drops do not shorten the held time (the ring scan or the re-armed box path
    takes it) -> studied;
  - Q2 fails: the give-up is too early for good strikes -> the threshold is studied before reuse.

## 5. Results

**X0 (2026-11-05, ICT from `date`):**
- 14:46-14:52: group 20's stat commands went live with the guarded `recreate:rathena,sniffer@240`
  (the same step as the web-server; worst capture stall 9.3 %; the GM re-logged by itself).
- 15:02-15:03: the switch to the Rogue: Escape -> the game option window -> character select ->
  a click on the third card (Thief8fce; the side panel read Rogue, Lv 63, HP 2209, SP 341, AGI 82,
  DEX 40; the login operator window first, the interlock being red at character select) ->
  `ro_agent.enter_game(..., char="Thief8fce")` (new parameter; the chat window check ran) -> in
  game on prt_fild08 215,159. The hotbar kept F1 White Potion x14, F2 Fly Wing x16, F3 Steal (the
  web-server's account settings did not reset it). No red account-settings line.
- 15:04: `@baselevelup 36`, `@agi 17`, `@dex 59`, each through crusader.gm_line's name + job check
  (name 0 / job 0). Read back on the status window (15:05): **Base 99 / Job 50, HP 5070, SP 530,
  AGI 99+8, DEX 99+7**, STR 1+6, VIT 1+6, INT 1+4, LUK 1+4; Atk 147+40, HIT 205, FLEE 246+1, ASPD
  176; **688 status points unspent** (Batt asked for AGI / DEX only). The replies' tab showed
  "Base level raised." and "Stat changed." x2.
- `dungeon_hunt.py`: the Rogue's `level_hold` 63 -> 99, max HP / SP 5070 / 530 (tests updated).

**Pilot p1 attempt 1 (15:24:36-15:25:21):** the setup ran (@heal, the stock topped up, `@warp
xmas_dun02 7 21` = PATROL_START); before the next typed line (`@killmonster2`) the chat window
check could not read the padlock (closed 31.6 / open 78.8 against <= 20): at the west edge the
icon row lies over the black void, and the reader's union mask held background pixels (the open
padlock's shape). It STOPPED as designed: nothing else typed, no hunting input. Fixed in
chat_window.padlock_distances (each template on its own icon pixels: 5.1 / 104.4 on that frame;
all 41 real frames of the day decided, worst own 8.8, nearest other 29.8; a test). Attempt 2
follows with the same command.

**Pilot p1 attempt 2 (session 20261105T152721-demo-dungeon-rogue-xmas_dun02-patrol-P2-xmas02-p1;
setup 15:27:21-15:27:50, the run to 15:32:2x):**
- The setup: @heal, `@warp xmas_dun02 7 21` (PATROL_START), `@killmonster2`; the Battle Log tab
  selected; the chat window check passed at every typed line (the new padlock read).
- **Ended by the runner itself: "position unread for 30 s"** (then my SIGINT cut its end path after
  the home warp; the packets and the manifest were written afterwards from its first / last events,
  `manifest.written_by` says so; 306 packet events).
- The judge (`dungeon_judge.py row`, 4.5 min): 2 engagements (walk_sword), 2 strikes, both landed;
  1 kill (a Cruiser); 4 Fly Wings (1 dead end at 34,30; 3 "pos_unread"); 53 walk clicks, 32 trusted;
  33 no-entry carves; hard bars PASS (0 NPC contact, 0 non-monster attack; the 4 same-map changes
  are the Fly Wings). Steals cannot be counted yet (0x09CB / 0x0110 are not decoded: X4).
- The Battle Log reader works on the docked 6-line window: "[Myst Case] receives '185' damage
  points", "Casts [...] skill" x4, "Skill has failed." (its first live positive case on the new
  geometry).
- **THE BLOCKER, the position:** `selfpos.read_minimap` reads the readout under the minimap only
  over a darker strip. On xmas_dun02 the strip shows the floor through it: over the orange floor it
  reads ("7 40", "268 107" at home), over the PALE floor tiles it reads nothing ("79 93" on screen:
  `no_glyph`; `stroke_probability` gives 0 when the strokes do not stand out). Each unread position
  sent the runner to a Fly Wing (a random cell, often inside the maze), and 30 s unread ended it.
- Next (not started): a readout reader for light strips (the digits keep their 1-px black drop
  shadow; a second template set or a shadow-based mode, calibrated on readout crops with the
  packets' positions as truth), or a /where fallback through the replies' tab; and X2's recording
  once the root disk has >= 140 GB free. ➡️ SUPERSEDED by Amendment C (4C): the floor is 120 GB;
  X2 waits for X1b instead (4D).

**X1b round 1 (2026-11-05 20:16-20:43; pre-registered 4D at 7303972 20:16:03; the design frozen
at 8cbc09c 20:42:38 on the even stands; the odd stands scored once at 20:42:55):**
- The collection (`selfpos_light.py collect`, the Rogue immune): attempt 1 stopped at its 2nd line
  (20:17: the identity check ran during the first warp's loading screen; the collector now waits
  for the check to pass after each warp). Attempt 2 stopped by design at stand 23 (20:24: the
  chat window check could not decide the padlock over the north edge's pink wall, closed 5.8 /
  open 20.1, margin 14.3 < 15 -> fixed in b75de95, the colour shape as a second opinion; all 55
  frames of the day decide). Resumed at stand 23 with the same stand numbers (`--start 23`,
  20:29-20:41). **680 crops at 85 stands, all 680 labelled** (each warp landed where it was sent,
  the Rogue stood still; 170 + 594 sniffer events). The collector's live log printed the BASE
  reader's per-stand result for every stand, odd ones included; no odd crop was inspected or
  scored by any candidate before the freeze.
- The design, on the 43 even stands (344 crops) only: the OPAQUE-GLYPH fallback (after a base
  `no_glyph` / `uncovered_ink`: every pixel that is neither a stroke >= 235 nor a shadow <= 40
  flattened, stroke starts at those levels), guarded twice (never after `ambiguous` / `layout`; a
  light cell with a half shadow 41-170 is None). Even stands: base 312/344, the fallback 344/344,
  0 wrong.

| held-out (42 odd stands, 336 crops) | n | base exact | new exact | none | wrong | bar |
|---|---|---|---|---|---|---|
| light strips (scene median >= 170) | 40 | 8 | 8 (20.0 %) | 32 | 0 | B2 >= 90 %: **FAIL** |
| dark strips | 296 | 296 | 296 | 0 | 0 | B3: pass |
| all | 336 | 304 | 304 | 32 | 0 | B1 0 wrong: pass |

- **Verdict: X1b round 1 FAILS (B2).** B4 was not run (a failed design is not carried to T0's
  sessions).
- Diagnosis (after the verdict): on all 4 failing odd stands (7,125; 7,218; 7,241; 217,23) the
  opaque parse READ the true digits (e.g. "7 125": 7 / 1 / 2 / 5, scores 0.10-0.27, margins
  7.3-18.9 against 3.56 / 1.87) and the HALF-SHADOW guard refused them: those strips are mixed,
  a dark floor band (~60-90) runs through light cells, and the guard took any 41-170 pixel in a
  light cell for a fading digit. No even stand had such a cell. The odd stands are spent as
  held-out data; round 2 (4E) gets fresh cells.

**X1b round 2 (pre-registered 4E at 42d4e57 21:16:13):**
- **R4 (T0's held-out sessions, `selfpos_eval.py --light`, 21:16-21:3x, CPU, nice 10, a 4 GB
  scope): PASS.** Standing 99.36 % exact (2,317 / 2,332; bar 99 %), walking 99.70 % within one
  cell (336 / 337; bar 97 %), 0 wrong on standing frames. The fallback never answered on these
  sessions: every frame it ran on, it abstained (`light_failed`; 1,435 no-minimap frames, 15
  standing, 194 excluded). The one wrong read is the BASE reader's, a walking frame of
  outdoor-d 2 cells off (183,363 read 182,361).
- **The fresh collection** (`--cells midpoints`): part 1, 21:16-21:21, 22 stands (176 crops, all
  labelled), then STOPPED by the chat window check (the padlock undecided over the pink puzzle
  floor, 5.8 / 12.0). Its end path's home warp then ran the check again: a false "seen in
  part" read pressed Enter (the input closed) and "no window found" pressed F10 8 times, cycling
  the window to 9 lines (the input log; nothing sent to chat). Restored by hand 21:24-21:27 (F10
  x6, Enter behind the UI gate, each step judged on a frame). Fixed in 41d5174 (no F10 blind;
  the window found over bright floors; the padlock's colour shape when grey ranks it first; the
  collector's end path types nothing after a failure). No crop was scored before the
  collection is complete. Part 2 resumes at stand 22 (21:37).- Part 2: 21:37-21:49, stands 22-84 (504 crops, all labelled), clean (the home warp typed).
  **680 fresh crops at 85 midpoint cells, all labelled**, scored ONCE at 21:49:43:

| fresh cells (85 midpoints, 680 crops) | n | base exact | new exact | none | wrong | bar |
|---|---|---|---|---|---|---|
| light strips (scene median >= 170) | 24 | 8 | 16 (66.7 %) | 8 | 0 | R2 >= 90 % (n >= 24): **FAIL** |
| dark strips | 656 | 640 | 656 | 0 | 0 | R3: pass |
| all | 680 | 648 (95.3 %) | 672 (98.8 %) | 8 | 0 | R1 0 wrong: pass |

- R4 PASS (above). **Verdict: X1b round 2 FAILS (R2).**
- Diagnosis (after the verdict): the 8 misses are ONE stand (7,224). There the opaque parse read
  the TRUE digits ("7 224": 7 / 2 / 2 / 4, scores 0.11-0.21, margins 9.3-22.4) and the half-pair
  guard refused them again: a floor seam (a dark line 103-119 beside tiles at 216-225) makes a
  half pair in the "2" cell. Both rounds' failures are the light-cell guard refusing true reads
  on textured floors; the opaque parse itself read every stand of both rounds.

**X1b round 3 (pre-registered 4F at acabc38 22:02:50):**
- R4 re-run (22:03-22:2x): **PASS**, identical to round 2 (standing 99.36 %, walking 99.70 %;
  the fallback abstained on every frame it ran on; the one wrong read is the base reader's).
- The fresh collection (`--cells quarters`, 22:03-22:34, clean, no stop): **1,344 crops at 168
  cells, all labelled** (1,376 events); scored ONCE at 22:34:44:

| fresh cells (168 quarter points, 1,344 crops) | n | base exact | new exact | none | wrong | bar |
|---|---|---|---|---|---|---|
| light strips (scene median >= 170) | 96 | 8 (8.3 %) | 80 (83.3 %) | 16 | 0 | R2 >= 90 %: **FAIL** |
| dark strips | 1,248 | 1,206 | 1,248 | 0 | 0 | R3: pass |
| all | 1,344 | 1,214 (90.3 %) | 1,328 (98.8 %) | 16 | 0 | R1 0 wrong: pass |

- **Verdict: X1b round 3 FAILS (R2: 83.3 % < 90 %).** The 16 misses are two stands of the west
  edge's textured pale floor, and at both the opaque parse read the TRUE digits: 7,221 refused by
  the half-pair guard (>= 3 pairs from the floor's texture), 7,233 by `uncovered_ink` (a stroke
  start in the floor left unexplained).
- **The three rounds together (fresh cells each time, 0 wrong reads in 2,704 crops):** light strips
  20.0 % -> 66.7 % -> 83.3 % (base 20.0 / 33.3 / 8.3 %), all crops 90.5 -> 98.8 -> 98.8 %; every
  miss of rounds 2-3 is a check refusing a true read, never a misread. **The X1b iteration stops
  here** (three FAILs of the same bar): whether the round-3 reader is good enough for the runner
  is Batt's decision. Pilot p2 (4E/4F: "then, not a bar") measures it live.

**Pilot p2 (session 20261105T223633-demo-dungeon-rogue-xmas_dun02-patrol-P2-xmas02-p2; the pilot
p1 command with `--minutes 15 --label xmas02-p2`; the round-3 reader with PosConfirm; the Rogue
immune; 22:36:33-22:52:26; unrecorded):**

| | pilot p1 (15:27) | pilot p2 (22:37) |
|---|---|---|
| ran | 4.5 min, stopped: "position unread for 30 s" | **15.0 min, its own time box** |
| Fly Wings for an unread position | 3 | **0** |
| Fly Wings for a dead end | 1 | 7 (28 / h) |
| walk clicks (trusted) | 53 (32) | 275 (180) |
| engagements / strikes | 2 / 2 | 6 / 5 + 9 burst clicks |
| kills (judge) | 1 | 1 (4.0 / h) |
| hard bars (packets) | pass | **pass**: 0 NPC contact, 0 non-monster attack; the 7 same-map changes are the Fly Wings |
| fallback reads waiting for a 2nd read | - | 35 (`pos_light_unconfirmed`) |

- ~~The HP loop's reads held no position 10.4 % of the time (264 of 2,532: after the Fly Wings'
  2.5 s settle, unconfirmed fallback reads, unread strips); none lasted long enough for an
  escape.~~ ➡️ CORRECTED 2026-11-06: that count took in the 211 "quick" HP reads, which never
  carry a position. The main reads with no position: **53 of 2,321 (2.3 %)**, all after a Fly Wing
  (the field is the runner's last known cell, cleared by a Fly Wing; it is not a per-read result).
- **The next limit is the walk, not the position:** 7 dead ends in 15 min (each a Fly Wing to a
  random cell, often inside the maze), and few engagements (the v1 detector's generic class on
  this map's species is what X2 measures).
- Session and judge archived (scratch-archive/2026-11-05/sessions/, sha256 checked).

**X2's recording started 22:54:09** (`record_session.py --backend rdp --format png --fps 1 --label
xmas02-x2 --seconds 1320 --out /home/batt/poring-lab-rec --max-bytes 3G`; the disk 131.8 GB free
against the 120 GB floor), the runner 22:55 (4A's command, 20 min).

**X2's recording (4A; session `20261105T225409-rdp-xmas02-x2`; the runner's
20261105T225543-demo-dungeon-rogue-xmas_dun02-patrol-P2-xmas02-x2):**
- The recorder: 22:54:09 + 22 min, **1,320 frames, 2.03 GB (92.2 MB/min), stop_reason duration**,
  1,361 packet events. **Shipped 23:30-23:32** (`dataset_ship.py ship <session>`, the IO guard on):
  9 files, 2,030,474,135 bytes, re-hashed on the NAS, local copy deleted
  (`/mnt/poring-lab-datasets/20261105T225409-rdp-xmas02-x2`). Root disk 131.8 GB free before,
  130.5 GB after (other tenants keep it moving).
- The runner (4A's command, 20 min): ended by its time box, the home warp typed; the judge
  (packets): **hard bars PASS** (0 NPC contact, 0 non-monster attack; the 7 same-map changes are
  its Fly Wings), 0 deaths, 15 engagements, 11 strikes + 21 burst clicks, 2 kills, 7 Fly Wings
  (5 dead ends, 2 position unread), 363 walk clicks (224 trusted); ~~the HP loop's reads held no
  position 12.6 % of the time~~ (➡️ CORRECTED 2026-11-06: 138 of 3,244 main reads = 4.3 %; the
  12.6 % took in the 310 quick reads, which carry no position); 44 fallback reads waited for a 2nd
  read.
- **X2's scoring waits for its tooling** (4A: a CPU predictor for a recorder session + the scorer,
  its positive control on a banked gef10 human demo first); the rule and the bar stay as
  pre-registered. ➡️ 2026-11-06: the tooling is BUILT (`recorder_boxes.py predict`,
  `detector_vs_packets.py score-session`; branch `feat/x2-score`). Its positive control passed:
  `score` and `score-session` give back the 2026-10-26 reference exactly on Batt's gef10 demo
  (recall 8.0 %, precision 18.7 %), and the CPU predictor matches the live boxes up to the demo's
  JPEG frames (xmas02-prep.md 7). X2's own score waits for the parent.
- Found while shipping: `dataset_ship.py status` walks every NAS session's tree (`tree_bytes`
  over ~550 sessions): it sat > 12 min in NFS calls and was stopped by PID (read-only). Fixed:
  the NAS sizes come from the manifests (a test that fails on the old code).

**2026-11-06 (Amendment D, 4D'):**
- **The "Chat" tab name survived a client restart** (06:38-06:39; judged screenshots before, at
  character select and in game): the Rogue at prt_fild08 268,107 before, `ro_agent.close_client`
  (paced Alt+F4), `launch_client`, `to_char_select gm` (Thief8fce's card was already the selected
  one), `enter_game(..., char="Thief8fce")`; the game-entry chat check: left 0, last row 719, 6
  lines, padlock locked, tabs battle | regular in order. Immunity (`@monsterignore`) does not
  survive a relog: restored before the next run.

**Pilot p3 (4G; session 20261106T070011-demo-dungeon-rogue-xmas_dun02-patrol-P2-xmas02-p3;
dungeon@8.6 at 126a3b5, pre-registered 06:58:15; the run 07:00:11-07:15:58, ended by its own time
box, the home warp typed; unrecorded). VERDICT: PASS, all four bars -> dungeon@8.6 is the patrol's
runner.**

| | p2 (dungeon@8.5) | X2 (8.5, 20 min) | **p3 (8.6)** | bar |
|---|---|---|---|---|
| W1 dead-end Fly Wings | 7 | 5 | **0** (no Fly Wing at all) | <= 2: PASS |
| W2 no-entry carves / walk decisions | 138 / 414 = 33.3 % | 116 / 480 = 24.2 % | **31 / 489 = 6.3 %** | <= 10 %: PASS |
| W3 clicks the old cue would have carved, then a stall | - | - | **6 / 125 = 4.8 %** | <= 10 % (>= 20): PASS |
| W4 hard bars (packets) | pass | pass | **pass**: 0 NPC contact, 0 non-monster attack, 0 map change | PASS |
| waypoints reached (per min) | 31 (2.07) | 89 (4.45) | **79 (5.27)** | reported |
| forgets (uncarve) / stalls | - / 15 | - / 18 | 2 / **38** | reported |
| engagements / strikes (landed) / kills | 6 / 5 / 1 | 15 / 11 / 2 | 4 / 3 (2) / 3 | reported |
| no position in the HP loop's main reads (the last known cell; cleared by a Fly Wing) | 53 / 2,321 = 2.3 % | 138 / 3,244 = 4.3 % | 0 / 1,620 = 0 % | reported |

- **The 40 kept crops** (the ring and the old count disagreeing, of 196): walk arrows (most with the
  client's green walk marker) over the orange floor; scan hovers beside the Rogue, whose red outfit
  the old count also took for the ring; and 5 full rings drawn 20-30 px AWAY from the pointer
  (circle fits at (-24.4, +14.5), (+7.5, -6.5), (+7.5, +31.6) instead of (+4.5, +11.5): the client's
  cursor not yet redrawn at the new pointer, a known lag), which the +-3 px rule rightly does not
  give to the hovered cell. No ring at the pointer was missed.
- **THE NEXT LIMIT, found in p3's packets: clicks STRAIGHT NORTH send no move request.** Of p3's
  456 walk clicks, 124 sent no `self_move_request` (the sniffer): 93 of the 95 clicks at (0, +7)
  (the cell 7 straight north, client pixel (640, 204)) and 5 of 6 at (0, +6), against 1 of 33 at
  (+-1, +7), 1 of 69 straight south and 24 of 253 elsewhere. The stalls (two clicks without moving
  -> a 5 x 5 carve) and the forgets come from them: the west edge's 230-cell leg is all straight
  north.
  - The client draws a walk arrow with its green walk marker there, then the no-entry ring after the
    click (X2's frames at the failed clicks), though every cell of those paths is plain type-0
    floor, flat (x 13, y 26-35 at -8) on the client's own GAT.
  - It is not this map: on gef_fild10 (the 9 patrol sessions of 2026-10-27) (0, +7) failed 108 /
    325, (0, +6) 8 / 26, (0, +12) 14 / 42, while (+-1, +7) failed 0 / 88 and every other direction
    23 / 6,090. Not a repeated pixel either (the same rate after an identical click). The guards of
    our own click path refused nothing (no `refused` / `npc_refused` count).
  - The client's own reason is not known (a hit box above the character is one guess). The
    measured way round it: aim one cell to the side, (+-1, +7) (p3 32 / 33 sent; p2 + p3 + X2
    44 / 46; gef_fild10 88 / 88).
- ➡️ CORRECTED 2026-11-06 07:3x (this table's last row first said 10.4 % / 12.6 % / 17.2 %): those
  counts took in the quick HP reads, which carry no position at all. The field is the runner's last
  known cell, so it says when the runner had NO position (after a Fly Wing), not how often a read
  failed; the per-read outcome is not logged yet.

**Pilot p4 (4H; session 20261106T072839-demo-dungeon-rogue-xmas_dun02-patrol-P2-xmas02-p4;
dungeon@8.7 at 984caa2, pre-registered 07:28:02; the run 07:28:39-07:44:23, ended by its own time
box, the home warp typed; unrecorded). VERDICT: PASS, all four bars -> dungeon@8.7 is the patrol's
runner.**

| | p2 (8.5) | p3 (8.6) | **p4 (8.7)** | bar |
|---|---|---|---|---|
| M1 walk clicks without a move request | 42 / 275 = 15.3 % | 124 / 456 = 27.2 % | **28 / 566 = 4.9 %** | <= 10 %: PASS |
| M2 straight-north walk clicks (dx 0, dy >= 6) | 32 | 100 | **0** (97 dodged: 73 east, 24 west) | <= 2: PASS |
| M3 stalls | 15 | 38 | **3** | <= 19: PASS |
| M4 dead-end Fly Wings / carves / hard bars | 7 / 33.3 % / pass | 0 / 6.3 % / pass | **0 / 2.2 % / pass** (0 NPC contact, 0 non-monster attack, 0 map change) | PASS |
| waypoints reached (per min) | 31 (2.07) | 79 (5.27) | **215 (14.32)**: ~2.5 laps of 85 | reported |
| forgets / Fly Wings | - / 7 | 2 / 0 | 0 / 0 | reported |
| engagements / strikes (landed) / kills | 6 / 5 / 1 | 4 / 3 (2) / 3 | 13 (8 box, 4 walk sword, 1 stall scan) / 6 (2) / 1 | reported |
| no position in the main HP reads | 2.3 % | 0 % | 0 / 1,513 | reported |

- **The walk is no longer the limit:** the Rogue walked the edge loop ~2.5 times in 15 min with no
  Fly Wing. The next limit is the FIGHT: 13 engagements, 6 strikes, 2 landed, 1 kill (X2 measures
  whether v1's boxes see this map's species; its scoring tooling is next).

**Run p5 (4I, a measurement; session 20261106T074624-demo-dungeon-rogue-xmas_dun02-patrol-P2-xmas02-p5;
dungeon@8.7 + the read logging at 7cdbe09; 07:46:24-08:01:5x, its own time box; unrecorded):**
- **The reader, live (1,521 main HP reads):**

  | outcome | reads | share |
  |---|---|---|
  | base (the never-a-guess reader) | 1,361 | 89.5 % |
  | light (the fallback, confirmed) | 100 | 6.6 % |
  | unconfirmed (a fallback read PosConfirm held back) | 38 | 2.5 % |
  | light_failed: uncovered_ink | 11 | 0.7 % |
  | light_failed: half_shadow | 8 | 0.5 % |
  | light_failed: no_glyph | 3 | 0.2 % |

  - A position on 96.1 % of the reads; the fallback was tried on 160 and gave 100 (62.5 %). Every
    failure sits on the west leg (x 6-8, y 116-242; one at 49,26), the area of round 3's two missed
    cells (7,221: half_shadow; 7,233: the floor as bright as the strokes).
  - The confirmation gate costs more reads (2.5 %) than the fallback's own refusals (1.4 %).
- **The walk, a second sample of dungeon@8.7 (not a bar):** 218 waypoints (14.53 / min), 0 Fly
  Wings, 0 dead ends, 4 stalls, 5.0 % of 605 walk clicks without a move request, 0 straight-north
  clicks (98 dodged), carves 4.0 %; hard bars pass (0 NPC contact, 0 non-monster attack, 0 map
  change).
- **The fight:** 5 engagements, all by v1's box; the scans found no SWORD (5 box misses), so 0
  strikes and 0 kills. With p4's 13 engagements / 1 kill, the fight is the limit; X2's scoring
  (does v1 see these species) is being built (a subagent, feat/x2-score).

**The reader's next round: design notes (2026-11-06 08:0x-08:1x; DESIGN DATA ONLY, nothing
pre-registered, nothing changed in the reader):**
- Round 3's two missed cells, read again with the current reader (rounds 1-3 = 1,704 crops with a
  truth, all design data now): 1,688 exact, 16 None, 0 wrong.
  - 7,221: the fallback parsed all four digits right (7 | 2 2 1); the half-pair guard refused it.
    An orange object behind the digits gives many mid-grey pixels next to a 170-220 floor.
  - 7,233: the floor itself reaches 222-249 and the "2"'s strokes go down to 242, so the floor
    pixels >= 235 stay as "strokes", the "2" scores 7.25 against a 3.56 limit and its stroke starts
    are left unexplained (`uncovered_ink`).
- Tried: a stroke pixel kept only within 1-2 px of a dark (glyph outline) pixel. WORSE: 1,640 / 1,704
  exact at 2 px, 1,542 at 1 px (the codec blurs the 1-px outline to ~80, so true strokes lose their
  outline); synthetic blends unchanged (15-18 wrong of 1,350). Not adopted.
- Left for the next round (each pre-registered on fresh cells, e.g. the west leg's x 8 / x 6
  cells that dungeon@8.7's dodge now walks): the uncovered-ink check reads the ORIGINAL grey (not
  the flattened one) in the fallback; a half-pair count that ignores pairs explained by the scene
  around the cell; or no fallback guard at all with PosConfirm as the only gate (its live cost and
  the blends' 37 / 1,080 single-read errors weighed first).
- Live, the reader already gives a position on 96.1 % of reads (p5), and the walk no longer loses
  its position; the fight is the larger limit now.

**X2 SCORED (4A's rule and bar; 4J's readings fixed at 7f6dbf4 08:32:46 before any box or truth
was computed; the tooling merged from feat/x2-score, its positive control on Batt's gef10 demo
reproduced the reference exactly). VERDICT: FAIL -- v1's "monster" class does not see
xmas_dun02's species.**
- The predictor: `recorder_boxes.py predict` on all 1,320 frames (08:33:07-08:44:39, 692 s, CPU,
  nice 19, 200 % quota; complete, no cut shard), model v1png-last-736x1280.onnx sha256 32b448a1...
- 4J's by-eye check (12 frames spread over the session, the truth boxes drawn): the truth sits on
  the Cruisers, Myst Cases and Cookies; a few boxes lie on raised orange blocks (a monster behind
  them: this simple truth rule has no occlusion). The projection is valid: the score is read.

| species (>= 30 labels: in the bar) | labels | hits | recall | bar >= 0.80 |
|---|---|---|---|---|
| 1249 Myst Case | 348 | 0 | 0.000 | FAIL |
| 1248 Cruiser | 208 | 1 | 0.005 | FAIL |
| 1265 Cookie | 174 | 0 | 0.000 | FAIL |
| 1246 Christmas Cookie | 207 | 0 | 0.000 | FAIL |
| pooled "monster" precision | 66 detections | 1 true | 0.015 | FAIL (>= 0.80) |

- 604 captures had a monster in view; 569 of them had no detection at all. 94 sightings, 1 ever
  detected. By distance: 0 / 206 within 5 cells, 0 / 407 at 6-10, 1 / 324 at 11-15.
- Hallucination: not observable (0 status_change events in X2's packets; 4J).
- **What it means for the runs:** the runner's "box" engagements on this map (p4 8, p5 5) were
  false detections; it fought only what hit it or what the walk's cursor read as a SWORD. A
  detector for this map is needed: Batt approved the GPU for it (4E' 1); its plan is written and
  pre-registered before any GPU step.
- ➡️ **The detector's plan: [xmas02-detector.md](xmas02-detector.md)** (PROPOSED 2026-11-06).
  ➡️ **TRAINED AND PASSED 2026-11-07 00:39** ([xmas02-eval.md](../benchmarks/xmas02-eval.md) RESULTS): Q1c recall 0.98-1.00 per species, P4A still precision 0.946 on X2 + xp1, where v1 had 0 / 63; CPU p95 270 ms vs v1's 273. Not deployed: Batt's decision (T-11).

**hunt_flow v56, run 1 (4K; session 20261106T085105-demo-hunt-flow56; v56 at 3f5c63b; the GM
switched to by a client restart 08:48-08:49, immune confirmed 08:50:46; the run 08:51:05-09:21,
its own time box; the live hard-bar monitor bound to its PID). K1 INCONCLUSIVE, K2 and K3 PASS.**

| arm (walk clicks) | clicks | no move request | share | bar |
|---|---|---|---|---|
| "nudged" (in the GM's column, moved 9 px east) | 44 | 0 | 0.0 % | K1: <= 5 % |
| "ab_off" (in the column, as before) | 44 | 6 | 13.6 % | K1: >= 15 % for the dead band to show |
| other walk clicks | 530 | 1 | 0.2 % | K3: <= 1 % PASS |

- K1 by its rule: the nudged arm meets its bar, but the off arm (13.6 %) is short of the 15 % the
  rule asks for to show the dead band in this run -> **INCONCLUSIVE: a second run.**
- K2 PASS: flow_judge's hard bars (0 NPC contact, 0 map change, no non-target job hit); the live
  monitor never stopped the run (0 Creamy hits; its 94 attack requests all at targets).
- Reported: 90 engagements, 85 kills (169.8 / h), hit rate 0.780, sight 37.0 per 10 min (windowed),
  loot 69 / 104.
- **Run 2 (fixed here, BEFORE it starts):** the same command with `--seed 20261107`, immunity as
  this login's; **K1 and K3 are judged on runs 1 + 2 POOLED** (the nudged arm <= 5 %, the off arm
  >= 15 %, each >= 15 clicks); K2 per run. If the pooled off arm is still under 15 %, the verdict is
  NO EFFECT SHOWN (v55 stays; the nudge is not adopted on this evidence).

**hunt_flow v56, run 2 attempt 1 (session 20261106T092511-demo-hunt-flow56, 09:25:11): STOPPED in
its setup after 10 s, by the chat-window check (no hunting; reported, not pooled).**
- Run 1's kills left the client's level-up notice icon ("up", bottom-left), which now covers the
  STANDARD chat window's bottom-left corner (docked at 719 since 11-05; the legacy window ended at
  624 and never met it). The hunting restore types GM lines before clearing notices: the chat check
  read the window "seen in part", took its designed step for that (Enter, the input open: it closed
  it; nothing was sent), saw no effect and stopped. The runner's end path typed nothing after.
- Fixed (tests; each new test fails on the old code or pins the order):
  - `chat_window.next_step`: a window seen in part WHERE IT BELONGS (the standard's left and top
    border) is "unknown" -> stop, never a key. Only a MOVED window seen in part keeps the
    open-input step. (The same step began the 11-05 21:21 F10 cascade.)
  - `gm_state.ensure_fixed` and `ensure_hunting`: the notices are cleared first (the status
    window's chord, no typed line), before any restore line.
- Run 2 attempt 2: the same command (seed 20261107), judged as run 2.

**hunt_flow v56, run 2 attempts 2 and 3: both STOPPED in setup, safely (no key); the A / B is
PAUSED for Batt's answer.**
- Attempt 2 (09:29:42): the chat check found the window seen in part where it belongs -> "unknown"
  -> stop, NO key (the 09:29 fix working). The notice step did not help: `gm_state`'s notice
  templates look for the level-up icon at the BOTTOM-RIGHT (ICON_BOX, measured 2026-10-09); this
  "up" icon sits at the BOTTOM-LEFT, over the standard chat window's corner, and the status
  window's chord (the documented step, tried once at 09:32 behind the UI gate) does NOT clear it.
- A relog (the client restart path, no typing; 09:33-09:34) DID clear it. Attempt 3 (09:36:10,
  immunity re-set 09:35): the restore's first line `@joblevelup -49` went through, and that level
  change brought the icon straight back; the next line found the window covered -> stop, no key.
- So since the 11-05 chat-window standard (docked at 719), EVERY GM level change puts this icon
  over the window's corner, and the GM restores (several typed lines, each a level change) cannot
  finish. Before 11-05 the window ended at 624 and never met it.
- Not guessed: the icon's own handle is unknown (its clearing step is Batt's knowledge or a new
  measurement). Options for Batt: (a) the icon's clearing step; (b) the chat check reads the
  window with that corner masked (the window's other borders and rows are visible; a reader
  change with its own positive case); (c) relog after each level change (slow).
- State left: the GM at prt_fild08 48,195, Base 70 / Job 1 (hunting state), HP full, immune this
  login, the chat input open and empty, the icon shown. route_previewd stopped by PID (09:39).
  K1 stays INCONCLUSIVE on run 1; v55 stays the adopted version.

**hunt_flow v56, run 2 (attempt 4; session 20261106T111229-demo-hunt-flow56; Amendment F's fix
f91ab44; the run 11:12:29-11:42:3x, ended by its own time box, the end restore typed through the new
notice step with no stop; the live hard-bar monitor bound to its PID, ended 11:46:53 "runner gone").
POOLED VERDICT (runs 1 + 2, 4K / section 5's rule): K1 PASS, K2 PASS (both runs), K3 PASS -> v56
ADOPTED.**

| arm (walk clicks) | run 1 | run 2 | **pooled** | bar |
|---|---|---|---|---|
| "nudged" (in the GM's column, moved 9 px east), no move request | 0 / 44 | 0 / 30 | **0 / 74 = 0.0 %** | K1: <= 5 %, >= 15 clicks |
| "ab_off" (in the column, as before), no move request | 6 / 44 | 15 / 29 | **21 / 73 = 28.8 %** | K1: >= 15 % (the dead band shows), >= 15 clicks |
| other walk clicks, no move request | 1 / 530 | 0 / 744 | **1 / 1,274 = 0.08 %** | K3: <= 1 % |

- **K2, run 2:** 0 NPC contact, 0 map change, no unknown-UI stop; the only non-target hit is ONE
  Creamy (mob 1018; `hardbar_live`: 67 attack requests at targets + 1 at a Creamy), which K2
  counts apart. (flow_judge's own `hard_bars.pass` reads false for that Creamy: it does not exempt
  Creamy; the monitor and 4K do.) 2 attack requests outside any engagement window
  (`unintended_attacks`), reported.
- **Reported, not bars:** run 2: 73 engagements, 62 kills (flow_judge, packets; the runner's own
  count 60 dead) = 123.9 / h, hit rate 0.722 (65 / 90), sight 36.0 per 10 min (windowed), loot 64 /
  78 picked (82.1 %). Run 1: 85 kills (169.8 / h), sight 37.0, loot 69 / 104 (66.3 %). The kill
  rates differ by seed and spawns, at the same sight; no bar was set on them.
- **Adopted (4K's rule):** `hunt_config.ADOPTED_VERSION` 56 with its live arm off (`adopt`:
  "col_nudge_ab" False) -- exactly 4K's "v57 = v56 with col_nudge_ab off", by the adoption
  mechanism v55 used (3.97); no PARAMS[57] is made. `config/flows/hunt/v56.yaml` exported.
  Every hunt_flow walk click inside the GM's column now moves 9 px east.

**Pilot p6 (4L; session 20261107T065911-demo-dungeon-rogue-xmas_dun02-patrol-P2-xmas02-p6; T-11 at
8d2ab43, pre-registered 06:54:56; the Rogue immune, toggled and judged 06:57-06:58; the run
06:59:11-07:15:02, its own time box; unrecorded). VERDICT: FAIL (D1, D2); D3 passes. The deployment
stays (Batt's decision); the runner's box rule is the limit.**

| | p4 (v1) | p5 (v1) | **p6 (xmas02)** | bar |
|---|---|---|---|---|
| D1 kills (packets) | 1 | 0 | **1** (4.0 / h) | >= 10: FAIL |
| D2 box engagements ending as a box miss | 8 box | 5 / 5 | **16 / 19 = 84 %** | <= 50 %: FAIL |
| D3 hard bars / dead-end Fly Wings / stalls | pass / 0 / 3 | pass / 0 / 4 | **pass (0 NPC contact, 0 non-monster attack, 0 map change) / 0 / 5** | PASS |
| engagements | 13 (8 box) | 5 (5 box) | 23 (19 box, 4 walk SWORD) | reported |
| strikes / landed | 6 / 2 | 0 / 0 | 10 / 4 (6 from a scan, 4 walk SWORD) | reported |
| waypoints (per min) | 215 (14.32) | 218 (14.53) | 203 (13.53) | reported |
| box watcher | v1 | v1 | 900 frames (1 / s), 4 own-character boxes skipped, 1 spot ignored | reported |

- **The model sees the monsters; the runner does not go to them.** A box engagement (a box foot
  within BOX_NEAR_PX 110 of our cell) starts the DEFEND scan: the 8 cells AROUND US. The 19 box feet
  lay 48-108 px from our cell's point (~1.5-3.5 cells): 16 of them beyond the ring, so no SWORD.
  The 3 that led to a strike lay at 82, 89 and 104 px. The Rogue is immune, so a monster never comes
  to the ring by itself.
- **While walking, the box is also stale on the map:** BoxWatch keeps a box for up to BOX_FRESH_S
  1.5 s, and the Rogue walks ~6 cells a second (150 ms a cell). A box's spot must be placed with
  OUR position at the box's grab, not the current one. Both points belong to the next runner change
  (a strike at the box's own cell, the camera at the grab time), pre-registered before its run.

**Pilot p7 (4M; demo 20261107T080933-...-xmas02-xmw3, recorder `20261107T080929-rdp-xmas02-xmw3`;
dungeon@8.8 at 0056948, pre-registered 07:44:59; `--box-strike`; the Rogue immune since 06:58;
08:09:29-08:30:19, its own time box). VERDICT: FAIL (E1, E2); E3 passes. `--box-strike` stays off.**

| | p6 (no box strike, 15 min) | **p7 (box strike, 20 min)** | bar |
|---|---|---|---|
| E1 kills (packets) | 1 (4.0 / h) | **4 (12.0 / h)** | >= 40 / h: FAIL |
| E2 box fights ending as a box miss | 16 / 19 = 84 % | **19 / 25 = 76 %** | <= 50 %: FAIL |
| E3 hard bars / Fly Wings / stalls | pass / 0 / 5 | **pass / 0 / 3** | PASS |
| strikes / landed | 10 / 4 | 7 / 7 (5 by box, 2 by scan) | reported |
| waypoints (per min) | 203 (13.53) | 262 (13.10) | reported |

- **`box_target` (25, one per box fight):** the box was fresh in all 25 (wait after the settle 301-1,204 ms; the
  settle 0-219 ms); 7 found no box within 220 px; 18 hovered: 5 SWORD (all struck), the rest
  "unknown" (20 hovers) or "clear" (6).
- **Why so few SWORDs, from the packets (offline, `/dev/shm/.../p7/hover_check.py`, reported
  only):** at each of the 18 hovered targets, the truth was projected at the event and 0.4-2.0 s
  before it, with us standing still.
  - 13 boxes MATCHED a monster's predicted sprite when grabbed (IoU >= 0.4, 1.2-1.6 s before the
    event), and that monster was GONE from the hovered spot by the hover (IoU < 0.3, 100-200 px away).
  - 4 monsters stood still the whole time; all of them were struck.
  - The box still on a monster (IoU >= 0.4) as time passes: 13 / 18 at about the grab (1.6 s
    before the event), 9 / 18 0.4 s later, 5 / 18 from 0.8 s later on (only the idle monsters).
  - **So the boxes are right and the time from grab to hover is too long.** The 1-a-second
    rhythm plus a CPU detection makes the wait 0.3-1.2 s, then each hover takes 0.35 s, and a
    wandering monster walks 2-5 cells in that time.
- **What would cut it** (each a new pre-registration; none is tuned on this run):
  - detection without the 1-s rhythm (a fresh detection right after the settle: ~0.1-0.25 s on 16
    CPU threads, a few ms on the GPU if Batt moves it there);
  - one hover instead of two;
  - leading a walking box by its own motion between two fresh detections.


**Pilot p8 (4N; demo 20261107T125651-...-xmas02-p8; dungeon@8.9 at 61a04ca + the detection log
12437f8, pre-registered 12:30:32; `--box-strike --box-now --box-detector ab`; the Rogue immune
(judged 12:52:29: "You are now immune to attacks."); the detect server beside it as one guarded
step 12:56:10-13:36:14; the run 12:56:47-13:27:38, its own time box). VERDICT: E1 and E2 FAIL; E3
PASSES; G1 and G2 PASS. `--box-strike --box-now` stay off; `--box-detector gpu` becomes the
default (the follow-up commit).**

| | p7 (20 min) | **p8 (30 min)** | bar |
|---|---|---|---|
| E1 kills (packets) | 4 (12.0 / h) | **6 (12.0 / h)** | >= 40 / h: FAIL |
| E2 box fights ending as a box miss | 19 / 25 = 76 % | **22 / 34 = 64.7 %** | <= 50 %: FAIL |
| E3 hard bars / dead-end Fly Wings / stalls | pass / 0 / 3 | **pass / 0 / 9 (18 / h)** | PASS (<= 39 / h) |
| G1 GPU-asked detections served by the GPU, outside R3's OFF windows | - | **1,063 / 1,079 = 98.5 %** | >= 90 %: PASS |
| G2 the box target's request -> boxes, p50 | - | **GPU-served 94 ms vs CPU-served 305 ms** | <= 100 and <= half: PASS |
| strikes / landed | 7 / 7 | 16 / 12 (box 10, walk_sword 3, scan 3) | reported |
| waypoints reached (per min) | 262 (13.10) | 359 (11.96) | reported |

- **The box targets (34, one per box fight), per path that served the fresh detection** (too few
  for a verdict, as pre-registered):

  | served by | targets | a box within 220 px | hovered | SWORD | struck | struck / hovered | request -> boxes p50 | hover from the grab p50 |
  |---|---|---|---|---|---|---|---|---|
  | GPU | 11 | 9 | 9 | 4 | 4 | 0.444 | 94 ms | 94 ms |
  | CPU | 23 | 18 | 18 | 6 | 6 | 0.333 | 305 ms | 305 ms |

  By the assigned arm: GPU 17 targets, 5 struck of 13 hovered (0.385); CPU 17, 5 of 14 (0.357).
  Six of the GPU arm's 17 fell back to the CPU in R3's OFF windows (`down`).
- **The GPU live:** the box watcher made 1,820 detections, 1,065 by the GPU (the server counted
  the same 1,065) and 755 by the CPU (738 fallbacks, 17 the CPU arm's). Fallback reasons: R3's
  OFF windows (`down` within the 5-s retry; 118 `BlockingIOError`, a paused server's full backlog;
  12 `TimeoutError`). The watcher never died; the GPU was never turned off.
- **R3 over the run: PASS**, the first verdict for our GPU detector. 4 kept pairs, median ON-OFF
  delta -0.50 ms (+0.21, -1.54, -0.93, -0.06 ms; the trip is +5); then monitoring (27 min ON). No
  relaxed camera drops. Worst capture stall 12.0 %.
- **How heavy:** our process 336 MiB; GPU-wide utilization 15.8 % unpaused vs 12.5 % paused, power
  33.2 vs 32.6 W (confounded by Frigate's own load).
- **Why the kills did not rise (reported only, not tuned on this run):** every lock ended "no
  hits": 16 / 16 in p8 and 7 / 7 in p7. The runner read none of OUR hits in the Battle Log within
  LOCK_NO_HIT_S (3.5 s) after a strike and let the target go. Twelve strikes landed (the lock
  arrow or damage), and the packets count 6 kills. So the time from grab to hover is now short
  (94 ms on the GPU), and the next limit is staying on the target after the strike. The packets
  can tell whether our attacks reached it (attack requests vs damage to it) before any change is
  pre-registered.

**Offline study S1 (4O, pre-registered 14:29:41; scorer `scripts/lock_study.py` 4618413, run
14:3x on p7 + p8): the "no hits" locks are NOT missed hits. Every fight already ended before the
unlock; the runner could not see it end.**

| class (4O) | p7 | p8 | pooled | what happened |
|---|---|---|---|---|
| K the target died before the unlock | 4 | 5 | **9** | Cruiser 3, Christmas Cookie 4, Cookie 2; died 1.1-6.2 s after the click, after 2-11 hits |
| A hit, then gone before the unlock | 3 | 7 | **10** | **9 Myst Cases TELEPORTED** (vanish reason 3, 1.3-2.3 s after the click, after 2-4 of our hits); 1 Cruiser walked out of sight (12.8 s) |
| B first hit after the unlock | 0 | 0 | 0 | |
| C requests, never a hit | 0 | 0 | 0 | |
| D no attack request after the click | 0 | 4 | **4** | the click started no attack |

- **Why the Myst Cases teleport:** rAthena's pre-re mob skills give Myst Case (1249) ONE teleport
  rule, `AL_TELEPORT` in its idle state on `rudeattacked` at 100 %; Cruiser, Cookie and Christmas
  Cookie have none. A rude attack is a hit by an attacker the monster cannot target or reach, and
  the Rogue is immune (`@monsterignore`): monsters ignore it. So most likely the immunity itself
  makes every Myst Case teleport at its first hits (not yet tested without immunity). 9 of 23
  strikes, and 0 Myst Case kills, in the two pilots.
- **The dead time:** after each of the 19 K / A targets was gone, the lock stayed ~3.7-4.6 s more
  until LOCK_NO_HIT_S (3.5 s) ended it "no hits", ~4 s per fight.
- **The reader is not the problem for hits:** it saw 48 / 50 (96 %) and 64 / 66 (97 %) of our hits,
  lag p50 429 / 443 ms, p95 806 / 863 ms. But **experience: 4 and 6 gains in the packets, 0 lines
  read**: this client's Battle Log shows no experience line, so the runner's kill count (from
  those lines) stays 0 and its "quiet kill" fight end never fires.
- **Walking sight, step 1 (p8; Amendment L of xmas02-detector.md):** of 34 box engagements, 11
  started from a detection grabbed while we walked (a `self_move` within 1.0 s before it): 2
  strikes, 1 kill (18 % strikes per engagement). The 23 from a standing grab gave 11 strikes, 4
  kills (48 %). Seeing while walking does limit the box fights.
- **What it names (each a new pre-registration; nothing changed live):**
  1. immunity on xmas_dun02 (Batt's decision): it seems to cost every Myst Case fight;
     or skip Myst Case targets (the map model names the species, `Box.species`);
  2. end a fight when its target is gone, from pixels (the lock arrow or the box gone), and count
     kills that way too: ~4 s back per fight;
  3. the 4 clicks that started no attack (class D);
  4. walking-triggered box fights (2 strikes of 11 engagements).
- **Two follow-up looks (14:4x, exploratory; nothing changed):**
  - The lock arrow is NOT a "target gone" cue here: on p7's 1-fps recording
    (20261107T080929-rdp-xmas02-xmw3), `hunt_flow.arrow_blobs` in a 520 x 380 px box around us
    found as many white arrow-like blobs after the target died or teleported (0-6 a frame) as
    while it lived (0-4): the floor's toys and the damage numbers make them.
  - Our hits while the target lived (19 fights, the packets): every 0.47 s (p95 0.48, longest gap
    0.94 s); the first hit at most 1.41 s after the click. With the reader's lag (p95 0.86 s), "no
    damage line for 2.0 s AFTER the first hit" would end a fight ~2 s sooner than today's 3.5 s
    and would have cut none of these 19. A candidate for the next pre-registration.

**Batt's decisions on S1 (2026-11-07 ~15:0x ICT):** "Turn immunity OFF, and do not skip Myst Case:
it is the map's important monster; what it gives to Steal sells for a high price." So the next
pilot runs the Rogue NOT immune on xmas_dun02 and keeps Myst Cases as targets. Its pre-registration
(next) states the bars, the death handling (the runner's potions, its Fly Wing escape, and what a
death does to the run) and the Myst Case fights' count (by species from the packets).

**Pilot p9 (4P, pre-registered 15:26:49; demo 20261107T154356-...-xmas02-p9; dungeon@8.9 with
`--box-strike --box-now`, the GPU box watcher; immunity OFF from 15:43 (judged "Returned to normal
state."), back ON at 16:15 (judged "You are now immune to attacks."); the run 15:43:51-16:14:47,
its own time box). VERDICT: M1 PASSES (no Myst Case teleported), D1 and E3 PASS; E1 and E2 FAIL.
Kills almost tripled: 34.0 an hour against 12.0.**

| | p8 (immune, 30 min) | **p9 (NOT immune, 30 min)** | bar |
|---|---|---|---|
| E1 kills (packets) | 6 (12.0 / h) | **17 (34.0 / h)** | >= 40 / h: FAIL |
| E2 box fights ending as a box miss | 22 / 34 = 64.7 % | **20 / 32 = 62.5 %** | <= 50 %: FAIL |
| E3 hard bars / dead-end Fly Wings / stalls | pass / 0 / 9 | **pass / 0 / 9 (18 / h)** | PASS |
| M1 Myst Case strikes ending in a teleport | 6 / 6 (p7 + p8: 9 / 9) | **0 / 6** | <= 20 %: PASS |
| D1 deaths | (immune) | **0** (lowest HP 85 %, 0 potions) | PASS |
| strikes / landed | 16 / 12 | 25 / 14 (2 request only) | reported |
| waypoints reached (per min) | 359 (11.96) | 304 (10.13) | reported |

- **By species (packets; the targets we hit that died):** Cruiser 6, Myst Case 4, Cookie 4,
  Christmas Cookie 4. The judge counts 17 kills from the experience packets; 18 of the monsters
  we hit died. Nothing we hit teleported.
- **Strike classes (4O's scorer):** K 12, A 3, B 1, **D 9**. Nine strike clicks started no attack
  (p8: 4); they are now the largest loss. The 3 A's are Myst Cases that died after the 3.5-s
  unlock (no teleport).
- **Damage taken:** 258 monster attacks, 14 landed (the Rogue's FLEE), 2,046 HP in all; 0 potions,
  2 Fly Wings (position unread, not dead ends).
- **Items an hour (all snatched by the Rogue; Steal casts are not decoded yet, X4):** Scell 5
  (10.0 / h), Piece of Cake 2 (4.0 / h), Red Herb 1, Well-baked Cookie 1, Manacles 1 (2.0 / h
  each). p8: 3 items.
- **Engagements:** box 32, Battle Log (our hits on a monster that attacked) 8, the Miss cue 5, an HP
  drop 1. Now the monsters fight back, so the other triggers start fights too.
- **Walking sight (step 1):**
  - 15 box fights started from a detection taken while walking: 2 strikes, 1 kill;
  - 17 from a standing one: 19 strikes, 9 kills.
- **The GPU path:** 1,816 detections, 911 by the GPU, 905 by the CPU (R3's measuring phase pauses
  the worker half the time). G1 again 908 / 922 = 98.5 % outside the pauses. Request to boxes, p50:
  GPU 92.5 ms vs CPU 318.5 ms.
- **The reader:** 152 / 152 of our hits read (lag p50 419 ms, p95 877 ms); 17 experience packets,
  0 experience lines.
- **Decisions (as pre-registered):**
  - M1 passes: immunity stays OFF for xmas_dun02 runs, and Myst Cases stay targets.
  - E1 / E2 fail: 4P named the fight end (S1 follow-ups) as the next change. p9 now shows the 9
    D-class clicks as the larger loss, so the next pre-registration chooses between the two on
    these numbers.

**Batt (2026-11-07 ~16:3x, answering the 16:25 report):** "Yes [the no-attack clicks next, not
immune]. It still does not see monsters well -- I watched the bot play." And: focus on moving to
bot-server first. So the next runner change waits behind the move. The no-attack clicks (class D,
9 of 25) and sight (walking-started box fights strike 2 of 15) are its two candidates; sight is
also what a detector trained on bot-server can improve (xmas02-detector.md Amendment L).

**Pilot p10 (4Q, pre-registered 10:57:51, committed d17e6541 before the run; demo
20261108T105957-...-xmas02-p10, bot-server; dungeon@9.2 `--walk-stop` + p9's flags; immunity OFF
at 10:59 (judged "Returned to normal state."), back ON at 11:30 (judged "You are now immune to
attacks."); the run 10:59:57-11:30:43, its own time box; the OpenVINO detect server in the Intel
worker). VERDICT: E1, W1 and W2 FAIL; W3, E3 and D1 PASS. `--walk-stop` is NOT adopted (it stays
behind its flag, OFF by default). The run found the root cause behind both p9's and p10's class D
(below).**

| | p9 | **p10** | bar |
|---|---|---|---|
| E1 kills (packets) | 17 (34.0 / h) | **12 (24.0 / h)** | >= 40 / h: FAIL |
| W1 class-D median held (`owned_s`) | 7.33 s (9 D) | **7.20 s (13 D)** | <= 2.0 s: FAIL |
| W2 ring-1 fight-path Ds ending "walked" | - | **1 / 5** | >= 75 %: FAIL |
| W3 "walked" strikes that were not D | - | **0** | <= 1: PASS |
| E3 hard bars / dead-end Fly Wings / stalls | pass / 0 / 9 | **pass / 0 / 3 (6 / h)** | PASS |
| D1 deaths | 0 | **0** (lowest HP 91 %, 0 potions) | PASS |
| E2 box fights ending as a box miss (reported) | 20 / 32 = 62.5 % | 10 / 19 = 52.6 % | (<= 50 %) |
| strikes / landed | 25 / 14 | 27 / 13 | reported |

- **What the walk-stop did:**
  - It fired once, on a defend-scan strike on the north cell [0, 1]: the scene scrolled 43.6 px
    by 0.36 s, the burst stopped, and the strike held the fight 2.9 s, not ~7.2.
  - Every ring-1 strike that attacked in place read 0-2 px of scroll, so there were no false
    stops (W3).
- **Why W1 / W2 failed: p10's 13 class-D strikes were a different mix (packets checked):**
  - **8 strikes on FAR targets, outside the change** (`walk_sword` 5 at 5-7 cells, `box` 3 at
    3-6 cells). They clicked 4 times to the bound, ~7.2 s each, ~57 s in all. p9 had 1.
  - **3 clicks on the Rogue's OWN cell:**
    - a defend-scan SWORD at the south cell's body point (641, 360), which lies on her own feet;
    - the client sent no attack and no walk, so there was no scroll to see, and a false lock
      arrow ended each strike;
    - ~19 s in all.
  - **1 click while already attacking:** our hits went on before and after it; class D only
    because no NEW request came. Not a loss.
  - **1 ground click:** the walk-stop caught it.
- **The root cause behind both runs:** the defend scan's north and south body points (641, 312)
  and (641, 360) lie ON the Rogue's own sprite, where her hit and Miss effects animate. A SWORD
  read there clicks her own body:
  - north ([0, 1], [0, 2]): the client walks her on (p9: 5 of its 9 Ds, p10: 1);
  - south ([0, -1]): nothing happens (p9: 1, p10: 3).
  The walk-stop only limits the north case's cost.
- **Kills fell 17 -> 12:** fewer engagements (29 vs 46; box 19 vs 32), not the change, which
  touched 1 strike. The spawns differed; the same seed only fixes the route.
- **The reader:** 102 / 114 of our hits read (89.5 %; p9 100 %), lag p50 397 ms / p95 488 ms.
- **Items per hour (all snatched):** Scell 2 (4.0 / h), Red Herb, Piece of Cake, Zargon 1 each
  (2.0 / h each).
- **Decisions (as pre-registered):**
  - `--walk-stop` is not adopted;
  - W2's shift series show the 10-px threshold is not the problem (43.6 px vs <= 2 px): the
    D population is.
  - The next change is Batt's choice between:
    - **(a) own-body hover points:** never trust a SWORD read inside the Rogue's own sprite box,
      or hover the N / S cells at points clear of her body. This covers 6 of p9's 9 Ds and 4 of
      p10's 13;
    - **(b) far-target strikes:** lead a moving target (frames lag ~0.5 s), and cap the burst
      for far clicks. This covers p10's 8;
    - **(c) sight:** the detector misses monsters beside the Rogue (4Q's offline box test).

**Pilot p11, attempt 1 (4R; 12:35:58-12:42:32, 5.87 min): VOID. A hard bar stopped it, not the
change.**
- **What stopped it:**
  - the setup's `@killmonster2` (12:36:27) killed xmas_dun02's MVP, Stormy Knight;
  - rAthena placed an MVP TOMBSTONE (an NPC) where it died: "Time of death 05:36" = 12:36 ICT;
  - at 351 s a walk click toward (148, 20) opened its dialog ("[Stormy Knight] Has met its
    demise ... Defeated by [Unknown]"). The UI gate stopped the run on the unknown state, and
    the judge counts `npc_contacts` 1: the hard bars FAIL.
  - p9 / p10 had the same tombstone on the map; their clicks missed it.
- **Batt (12:4x): "disable tombs on the lab server".** `mvp_tomb_enabled: no` as a battle_conf
  import (bdb2f1c4), guarded `recreate:rathena,sniffer`. Attempt 2 re-runs 4R unchanged.
- **Reported from the 6 minutes, NOT pooled into attempt 2:**
  - 10 strikes: K 4, C 1, D 5 (far `box` 2, `walk_sword` 1, a diagonal 1, own-body 1);
  - 5 kills; 0 deaths, lowest HP 87.5 %;
  - 356 / 356 detections by the Arc.
- **The two `--self-recheck` reads behaved as designed:**
  - N [0, 1] (641, 312): first 0.795 (sword), 0.4 s later 0.26 (clear). Rejected, the scan went
    on: the transient case.
  - S [0, -1] (641, 360): 0.808 then 0.822. It persisted and was struck, and it was still
    class D. So a persistent own-body sword can still miss; attempt 2's R1 measures how often.

**Pilot p11, attempt 2 (4R unchanged; MVP tombstones off since bdb2f1c4; 12:55:48-13:26:36, its
own time box; immunity OFF at 12:53, judged "Returned to normal state."; back ON at 13:27, judged
"You are now immune to attacks."; the OpenVINO detect server with `--ov-preproc cpu`, as
pre-registered). VERDICT: E1, R1, R2, E3 and D1 PASS; R3 FAILS. `--self-recheck` stays ON for
xmas_dun02 runs. E1 passes for the first time.**

| | p9 | p10 | **p11 (attempt 2)** | bar |
|---|---|---|---|---|
| E1 kills (packets) | 17 (34.0 / h) | 12 (24.0 / h) | **22 (43.9 / h)** | >= 40 / h: PASS |
| R1 own-body class-D strikes | 6 | 5 | **0** (6 own-body strikes, all attacked) | <= 1: PASS |
| R2 defend-scan strikes that started an attack | 7 | 9 | **10** | >= 7: PASS |
| R3 class D share | 9 / 25 = 36 % | 13 / 27 = 48 % | **15 / 39 = 38.5 %** | <= 25 %: FAIL |
| E3 hard bars / dead-end Fly Wings / stalls | pass / 0 / 9 | pass / 0 / 3 | **pass (0 NPC contacts) / 0 / 4 (8 / h)** | PASS |
| D1 deaths | 0 | 0 | **0** (lowest HP 90.7 %, 0 potions) | PASS |
| E2 box fights ending as a box miss (reported) | 62.5 % | 52.6 % | 8 / 26 = 30.8 % | (<= 50 %) |

- **The rechecks:** 9 own-body swords.
  - 3 were transient and rejected (second reads 0.38, 0.465, 0.247 after 0.766-0.932).
  - 6 persisted (second reads 0.758-0.851); all 6 strikes started an attack.
- **The 15 class-D strikes, by path:**
  - 9 far-target strikes: `box` 6 at 1-5 cells, `walk_sword` 3 at 5-7 cells. That is option (b).
  - 6 defend-scan strikes: 5 on the EAST cell [1, 0] at (675, 336) and 1 on [1, 1].
    - (675, 336) lies beside the self box (34 px from her feet point, the box is +-20). It is
      the same pattern one cell over: the glow around her reaches it.
    - Some ended on a damage line after one click: possibly "already attacking", class D only
      by the scorer's rule.
  - In all, 88.8 s of the 30 minutes held by class-D strikes.
- **Kills by species, reader:** 202 / 203 of our hits read (99.5 %, lag p50 393 ms).
- **Items (all snatched):** Scell 4, Piece of Cake 3, Zargon 2, Monk Hat 1.
- **Engagements:** 63 (box 26, Battle Log 21, `walk_sword` 9, Miss cue 6, HP drop 1); p9 46,
  p10 29.
  - A single run's kills swing with the spawns (p10 24 / h with the same seed), so E1's pass is
    one run. The next runs keep the flag on and show whether it holds.
- **Decisions (as pre-registered):**
  - R1 + R2 pass: `--self-recheck` stays ON for xmas_dun02 runs.
  - The next change is Batt's choice:
    - **(b) far-target strikes:** 9 of the 15 Ds;
    - **(a2) the recheck widened to the E / W body points:** 5 of the 15.

**Pilot p12 (4S; 14:13:17-14:43:59, its own time box; immunity OFF at 14:12, judged "Returned to
normal state."; back ON at 14:44, judged "You are now immune to attacks."; the detect server with
`--ov-preproc cpu`; vision now maps only renderD128, 64991a9a). VERDICT: E1, F2, F3, R1, E3 and D1
PASS; F1 FAILS. Kills 58.0 / h, the best so far.**

| | p10 | p11 | **p12** | bar |
|---|---|---|---|---|
| E1 kills (packets) | 12 (24.0 / h) | 22 (43.9 / h) | **29 (58.0 / h)** | >= 40 / h: PASS |
| F1 far class-D strikes | 8 | 8 | **6** | <= 3: FAIL |
| F2 far strikes that started an attack | 5 | 14 | **23** (of 29) | >= 10: PASS |
| F3 far strikes clicked while walking | 6 | 8 | **0** | <= 2: PASS |
| R1 own-body class-D strikes | 5 | 0 | **0** (2 own-body strikes attacked; 7 transient swords rejected) | <= 1: PASS |
| E3 hard bars / dead-end Fly Wings / stalls | pass / 0 / 3 | pass / 0 / 4 | **pass / 0 / 2** (1 Fly Wing: `pos_unread`, not a dead end) | PASS |
| D1 deaths | 0 | 0 | **0** (lowest HP 78.7 %, 0 potions) | PASS |
| class D share (reported) | 48 % | 38.5 % | **28 %** (13 / 46) | |

- **The waits:** 38 (box 26 + `walk_sword` 12).
  - Median 0.99 s, at most 1.6 s; still in 33, capped at 1.5 s in 5.
  - walk_sword retargets: 12, of which 8 still read SWORD and were struck; 4 were lost
    (2 unknown, 2 clear): no strike.
- **The 6 far class-D strikes, all clicked standing:**
  - 3 `box` (3-4 cells): the wait ended still, the hover read SWORD 320-368 ms after the
    grab, and the click still walked. The monster had moved. This is 4S's "standing is not
    enough" case: the target's own motion.
  - 2 defend-scan strikes on ring-2 cells (not this change's path).
  - 1 `walk_sword` that ended on a damage line after one click (likely already attacking).
- **The other 7 class-D strikes** are ring-1 defend-scan strikes, mostly beside the self box
  (option a2's case).
- **Reader:** 341 / 341 of our hits read, lag p50 397 ms.
- **Items (snatched):** Zargon 7, Scell 4, Candy 3, Well-baked Cookie 3, Piece of Cake 2.
- **Engagements:** 61 (box 26, Battle Log 13, walk_sword 12, Miss cue 8, HP drop 2).
- **Decisions (as pre-registered):**
  - F1 fails with F3 passing, so standing is not enough. The next idea for far strikes is the
    click's aim, for the target's own motion.
  - 4S named "stays ON" only for F1 + F2 passing. With E1 at 58.0 / h, F2 at 23 and no click
    while walking, keeping `--still-strike` ON is **Batt's call** (recommended).

**Pilot p13 (4T; 16:33:30-17:04:29, its own time box; the bag cleared 16:30-16:32; immunity OFF
at 16:32:54, judged "Returned to normal state."; back ON, judged "You are now immune to
attacks." at 17:04:46; the detect server `final`: the conversion on the card, FP32, the clock floor 2450 in
its start line). VERDICT: D1, D2, R1, F3, E3 and deaths PASS; E1 FAILS (34.0 / h). The run met
38 % fewer monsters; kills per monster seen are p12's.**

| | p12 | **p13** | bar |
|---|---|---|---|
| D1 the live detector's call, p50 / p95 | 64.7 / 68.3 ms (1,811 calls, all GPU) | **20.6 / 22.1 ms** (1,810, all GPU) | <= 35 ms, >= 99 % GPU: PASS |
| D2 the box path: boxes after the grab, p50 | 89 ms | **45 ms** | <= 65 ms: PASS |
| the sword verdict after the grab, p50 (reported) | 319 ms | **277 ms** | |
| E1 kills (packets) | 29 (58.0 / h) | **17 (34.0 / h)** | >= 40 / h: **FAIL** |
| R1 own-body class-D strikes | 0 | **1** (5 own-body strikes, 4 attacked; 4 transient swords rejected) | <= 1: PASS |
| F3 far strikes clicked while walking | 0 | **0** | <= 2: PASS |
| E3 hard bars / dead-end Fly Wings / stalls | pass / 0 / 2 | **pass / 0 / 1** | PASS |
| deaths | 0 | **0** (lowest HP 91.2 %, 0 potions) | PASS |
| far class-D strikes (reported; F1's bar 3) | 6 of 29 far | **4** of 16 far | |
| class D share (reported) | 28 % (13 / 46) | **31 %** (9 / 29) | |

- **Why E1 failed (studied as 4T's rule asks; packets, offline):**
  - monsters in sight (distinct `entity_appear`, objtype 5, in the run's window): p12 50
    (16.7 / 10 min), **p13 31 (10.3 / 10 min)**; Cruisers 19 -> 7, Myst Cases 21 -> 16;
  - kills per monster seen: p12 0.58, **p13 0.55**; strikes per monster seen 0.92 vs 0.94;
    engagements 61 -> 32;
  - the patrol walked MORE (526 waypoints vs 414) for fewer meetings.
  - So the supply of monsters fell; what the bot did with each one did not. The detector
    cannot change which monsters the server shows. Not proven: why fewer appeared (both runs
    started with `@killmonster2`; p12 ran 1 h 50 min earlier).
- **Box path:** 20 box targets (p12 26), 13 struck; the boxes reach the bot 44 ms sooner
  (89 -> 45) and the verdict 42 ms sooner (319 -> 277). The far class-D strikes fell 6 -> 4,
  but of fewer far strikes (16 vs 29): 25 % vs 21 %, no better.
- **Reader:** 162 / 162 of our hits read. **Items (snatched):** Scell 2, Red Herb 1, Candy 1,
  Well-baked Cookie 1, Piece of Cake 1, Zargon 1 (7; 14 / h).
- **The stock:** the setup added P2's 30 potions / 20 Fly Wings over the cleared bag (Amendment G
  item 3's gap; fixed for p14 by `potions_win`); none was used.
- **Decisions (as pre-registered):**
  - D1 + D2 pass; a regression bar (E1) failed, so it was studied: explained by the monster
    supply (kills per sighting unchanged), not by the detector. Keeping the fast path as the live
    detector is **Batt's call** (recommended: same boxes, ~3 x faster, every other bar passes).
  - After the run the bag was cleared again (17:05:56-17:07:26: Etc 2, Use 6; weight 942 -> 520,
    10 / 10 on the hotbar).

**Pilot p13r (4U; 18:12:32-18:43:17, its own time box; immunity OFF at 18:12:09, judged
"Returned to normal state."; back ON at 18:43:36, judged "You are now immune to attacks."; the
detect server `final` with the floor from the installed unit; the setup added 10 Fly Wings only:
10 White Potions held, `potions_win`). VERDICT: every bar PASSES. E1 44.0 / h.**

| | p12 | p13 | **p13r** | bar |
|---|---|---|---|---|
| D1 live detector p50 / p95 | 64.7 / 68.3 ms | 20.6 / 22.1 | **20.5 / 22.5** (1,810, all GPU) | <= 35, >= 99 % GPU: PASS |
| D2 boxes after the grab | 89 ms | 45 | **44** | <= 65: PASS |
| E1 kills (packets) | 29 (58.0 / h) | 17 (34.0 / h) | **22 (44.0 / h)** | >= 40 / h: PASS |
| R1 own-body class D | 0 | 1 | **0** (3 own-body strikes, all attacked; 8 transient swords) | <= 1: PASS |
| F3 far clicks while walking | 0 | 0 | **0** | <= 2: PASS |
| E3 hard bars / dead-end Fly Wings / stalls | pass / 0 / 2 | pass / 0 / 1 | **pass / 0 / 3** | PASS |
| deaths | 0 | 0 | **0** (lowest HP 66.3 %, 0 potions) | PASS |
| supply: monsters seen (/ 10 min) | 50 (16.7) | 31 (10.3) | **36 (12.0)** | reported |
| kills per monster seen | 0.58 | 0.548 | **0.611** | reported |
| class D share | 28 % (13 / 46) | 31 % (9 / 29) | **19 % (7 / 36)** | reported |
| far class D | 6 of 29 | 4 of 16 | **4 of 19** | reported |

- **Box path** (`target_motion.py`): 13 box strikes; target walking at the grab 3 (1 class D),
  standing 9 (1 class D), no monster within 3 cells 1 (class D).
- **Items (snatched):** Scell 4, Zargon 2, Red Herb 1, Piece of Cake 1, Level 3 Cold Bolt 1 (9;
  18 / h).
- **Decision (as pre-registered):** E1 passes, so the fast path's kill rate holds; p13r is p14's
  baseline. The supply was again below p12's (12.0 vs 16.7 / 10 min); kills per monster seen are
  the best so far.
- The bag cleared after it (18:44:04-18:45:32: Etc 2, Use 5; weight 590 -> 520, 10 / 10).

**Pilot p14 (4V; 19:04:20-19:35:06, its own time box; immunity OFF at 19:04:05, judged "Returned
to normal state."; back ON at 19:35:28, judged "You are now immune to attacks."; the detect server
`final`). VERDICT: M1 INCONCLUSIVE (1 box strike on a target walking at the grab), M2 / M3 / D1 /
F3 / E3 / deaths PASS; E1 FAILS (32.0 / h) and R1 FAILS (2 own-body class D). `--lead-strike` is
NOT adopted.**

| | p13r (baseline) | **p14** | bar |
|---|---|---|---|
| M1 box strikes on a target walking at the grab: class D | 1 of 3 | **1 of 1** | <= 1 of >= 3: INCONCLUSIVE |
| M2 box strikes on a standing target: class D | 1 of 9 | **0 of 7** | <= 2: PASS |
| M3 led hovers that read SWORD and were struck | - | **3 of 3** | >= half: PASS |
| the led strikes' classes (reported) | - | **D, D, A** | |
| E1 kills | 22 (44.0 / h) | **16 (32.0 / h)** | >= 40 / h: **FAIL** |
| D1 live detector p50 | 20.5 ms | **20.6 ms** (1,819, all GPU) | <= 35: PASS |
| R1 own-body class D | 0 | **2** (10 own-body strikes) | <= 1: **FAIL** |
| F3 / E3 (hard bars, Fly Wings, stalls) / deaths | 0 / pass, 0, 3 / 0 | **0 / pass, 0, 5 / 0** (lowest HP 63.7 %) | PASS |
| supply: seen (/ 10 min); kills per seen | 36 (12.0); 0.611 | **44 (14.7); 0.364** | reported |
| class D share | 19 % (7 / 36) | **23 % (7 / 31)** | reported |
| the sword verdict after the grab, p50 | 277 ms | **398 ms** (+ the second detection) | reported |

- **The lead itself:** 11 box targets carried a lead record (9 others found no box to target);
  3 read as walking (53-68 px / s, lead 16-24 px), each hover read SWORD and was struck: 2 ended
  class D, 1 attacked. Packets put one of the two Ds on a walker at the grab (1.3 cells off), the
  other with no monster within 3 cells of the led cell, and the attacked one on a monster the
  packets call standing. So the sprite's measured motion and the server's disagree in 2 of 3; no
  sign that the lead turns a walker's miss into an attack.
- **E1:** more monsters came (44) but fewer died per sighting (0.364). Engagements 47 (box 20,
  Battle Log 11, Miss cue 8, walk_sword 8; p13r 31) and strikes 31: more fights started by being
  hit, fewer finished. Not proven to be the lead's doing (its cost is ~0.12 s a box target).
- **Batt's clip (19:09:47-19:09:56, sent during the run):** "it does not seem to see the Myst
  Case". The detector boxed it every second (0.94-0.97). The Rogue stood because the led strike
  at 19:09:40.9 (53.9 px / s) started no attack and the lock waited for hits until 19:09:48.2
  ("no hits", 7.3 s), then the defend scan of the ring cells (2.7 s); only then the next box
  (19:09:53.6). Locked time on class-D strikes per run: p12 88.9 s, p13 56.5 s, p13r 49.2 s
  (median ~7 s each). And on patrol the walk engages a box only within `BOX_NEAR_PX` (110 px,
  ~3 cells): monsters further away are passed by design.
- **Items (snatched):** Scell 4, Piece of Cake 2, Candy 1, Zargon 1.
- **Decision:** M1's rule says the next run repeats the flag and pools; E1 and R1 failed, so the
  flag is not adopted. Batt chooses the next step (the next report).
- The bag cleared after it (19:36:23-19:37:49: Etc 2, Use 4; weight 598 -> 520, 10 / 10).
