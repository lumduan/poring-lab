---
doc_type: design
hypothesis: "On xmas_dun02 (Toy Factory 2F, the lab's pre-renewal server), the Rogue at Base 99 with base AGI 99 / DEX 99 and the gef10 skills, walking the map's EDGE clockwise (Batt's technique) and fighting plain melee so Snatcher steals on its own, gains stolen items per hour that are worth more than at its current build; and the live v1 detector's generic 'monster' class sees this map's species well enough (Q1's bar, section 4) that no new detector is needed first."
status: "X0 DONE 15:05; X1 DONE (merged e777181); pilot p1 15:27-15:32 STOPPED by the runner (the minimap readout is not read over the light floor, section 5); Amendment C (~20:2x): Batt's answers -- the recorder floor is 120 GB (X2 no longer blocked by the disk), the route on trial, the 2nd chat tab renamed Chat, 688 points left; X1b (a light-strip readout reader) pre-registered 4D, its data next. Planned 2026-11-05 (Batt's order ~13:2x, the four answers ~14:0x ICT, section 0). X1b round 1 (20:16-20:43) FAILED B2 (light strips 8/40: the guard refused true reads on mixed strips); round 2 pre-registered 4E (fresh cells). Round 2 (21:49, fresh midpoints) FAILED R2 (light 16/24; the guard refused a seam); round 3 pre-registered 4F (fresh quarter cells). Round 3 FAILED R2 (light 83.3 %, 0 wrong); the iteration stopped. Pilot p2 22:37: 15 min clean, 0 position-unread Fly Wings. X2 RECORDED 22:54 (1,320 frames, 2.03 GB, shipped + verified); its scoring waits for the tooling. 2026-11-06 (Amendment D, Batt): the reader stays ON and improves; the Chat tab name SURVIVED a client restart (06:39); the dead ends = the no-entry cue reading the orange floor (4G); dungeon@8.6 (the ring) pre-registered as pilot p3 (4G). p3 PASSED (0 dead-end Fly Wings, carves 6.3 %); its packets: straight-north clicks send no move request -> dungeon@8.7 (column_dodge) pre-registered as pilot p4 (4H). p4 PASSED: 215 waypoints in 15 min (p2 31), 0 Fly Wings, 3 stalls; the next limit is the fight. p5 (a measurement): the reader gives a position on 96.1 % of live reads (failures 1.4 %, unconfirmed 2.5 %, all on the west leg); 0 strikes from 5 box engagements. X2 SCORED: FAIL (v1 recall 0-0.5 % per species, precision 1.5 %): this map needs its own detector (GPU approved by Batt). hunt_flow v56 run 1 K1 INCONCLUSIVE; run 2 blocked by the up icon until Batt's Alt+S / Alt+A answer (Amendment F, f91ab44); run 2 11:12 -> v56 ADOPTED on the pooled verdict (K1 0/74 vs 21/73, K2, K3). The detector plan ACCEPTED (xmas02-detector.md Amendment A)."
role: null
verdict_date: null
verdict_ticket: null
supersedes: null
related: [rogue-gef10.md, gef10-prep.md, xmas02-prep.md, gef10-detector.md, ../benchmarks/gef10-eval.md, ../demonstrations.md, ../../scripts/dungeon_hunt.py, ../../scripts/dungeon_judge.py, ../../services/rathena/conf/import/groups.yml]
next_action: "hunt_flow v56 ADOPTED (4K pooled, 11-06 ~11:5x). The xmas_dun02 detector PASSED its evaluation 2026-11-07 00:39 (xmas02-eval.md): Batt decides its deployment (T-11). Then the reader's next round (fresh cells), the X4 steal decoders and the boss recognizer."
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
