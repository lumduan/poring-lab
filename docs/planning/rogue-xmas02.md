---
doc_type: design
hypothesis: "On xmas_dun02 (Toy Factory 2F, the lab's pre-renewal server), the Rogue at Base 99 with base AGI 99 / DEX 99 and the gef10 skills, walking the map's EDGE clockwise (Batt's technique) and fighting plain melee so Snatcher steals on its own, gains stolen items per hour that are worth more than at its current build; and the live v1 detector's generic 'monster' class sees this map's species well enough (Q1's bar, section 4) that no new detector is needed first."
status: "X0 DONE 15:05; X1 DONE (merged e777181); pilot p1 15:27-15:32 STOPPED by the runner (the minimap readout is not read over the light floor, section 5); Amendment C (~20:2x): Batt's answers -- the recorder floor is 120 GB (X2 no longer blocked by the disk), the route on trial, the 2nd chat tab renamed Chat, 688 points left; X1b (a light-strip readout reader) pre-registered 4D, its data next. Planned 2026-11-05 (Batt's order ~13:2x, the four answers ~14:0x ICT, section 0). X1b round 1 (20:16-20:43) FAILED B2 (light strips 8/40: the guard refused true reads on mixed strips); round 2 pre-registered 4E (fresh cells). Round 2 (21:49, fresh midpoints) FAILED R2 (light 16/24; the guard refused a seam); round 3 pre-registered 4F (fresh quarter cells). Round 3 FAILED R2 (light 83.3 %, 0 wrong); the iteration stopped. Pilot p2 22:37: 15 min clean, 0 position-unread Fly Wings. X2 RECORDED 22:54 (1,320 frames, 2.03 GB, shipped + verified); its scoring waits for the tooling. 2026-11-06 (Amendment D, Batt): the reader stays ON and improves; the Chat tab name SURVIVED a client restart (06:39); the dead ends = the no-entry cue reading the orange floor (4G); dungeon@8.6 (the ring) pre-registered as pilot p3 (4G). p3 PASSED (0 dead-end Fly Wings, carves 6.3 %); its packets: straight-north clicks send no move request -> dungeon@8.7 (column_dodge) pre-registered as pilot p4 (4H). p4 PASSED: 215 waypoints in 15 min (p2 31), 0 Fly Wings, 3 stalls; the next limit is the fight. p5 (a measurement): the reader gives a position on 96.1 % of live reads (failures 1.4 %, unconfirmed 2.5 %, all on the west leg); 0 strikes from 5 box engagements. X2 SCORED: FAIL (v1 recall 0-0.5 % per species, precision 1.5 %): this map needs its own detector (GPU approved by Batt). hunt_flow v56 run 1 K1 INCONCLUSIVE; run 2 blocked by the up icon until Batt's Alt+S / Alt+A answer (Amendment F, f91ab44); run 2 11:12 -> v56 ADOPTED on the pooled verdict (K1 0/74 vs 21/73, K2, K3). The detector plan ACCEPTED (xmas02-detector.md Amendment A). 2026-11-08/09 (Amendments G-K): the live GPU detector (p13r PASS); p16 --engage-screen ADOPTED with the boss guard (Batt); p18 DIED to the MVP -> the MVP schedule (Amendment K); the night p17-p27: the walk-refusal finding (the server ignores > 17-step or > 14-step-detour clicks) -> --reach-check ADOPTED after p27 (9.12b); quick-drop, far-single, far-single+far-approach, box-every 0.25, kill-gap NOT adopted (section 5)."
role: null
verdict_date: null
verdict_ticket: null
supersedes: null
related: [rogue-gef10.md, gef10-prep.md, xmas02-prep.md, gef10-detector.md, ../benchmarks/gef10-eval.md, ../demonstrations.md, ../../scripts/dungeon_hunt.py, ../../scripts/dungeon_judge.py, ../../services/rathena/conf/import/groups.yml]
next_action: "2026-11-10 10:2x: p45 PASSES -> `--garm-fly --garm-confirm 2` (9.19b) JOINS THE BASE (G1b C1 1.60 s; P2 0 false; 2 one-detection false dog boxes filtered; P1 no dog met). xmas02-gb stays (p44). Floor items: xmas02-detector.md Amendment O PROPOSED (Batt decides). N1 not run (N2). THE BASE = p16 + reach-check + far-single + far-approach + explore + walk-pick + kill-gap + loot-first + walk-pick-step + quiet-scan + garm-fly + garm-confirm 2."
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

### 4W. Pilot p15 pre-registration: --quick-drop, a strike that does not connect is given up (written BEFORE its run, 2026-11-08 19:57 ICT)

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

### 4X. Pilot p16 pre-registration: --engage-screen, any monster on the screen, nearest first (written BEFORE its run, 2026-11-08 20:35 ICT)

- **Why:** Amendment I item 1 (b), widened by Batt: "strike within what the screen shows, the
  nearest monster first". Batt's clips and p15 above: the 3-cell trigger and the 6-cell box-path
  cap let monsters pass, and the box path found no box in 6-12 of ~20 box engagements.
- **The one change against p13r: `--engage-screen` (dungeon@9.7, behind its flag, 441cc93d):**
  the patrol's box trigger and the box path take ANY monster box whose body point is in view
  (not under a UI window, not an ignored box spot), the nearest to her feet first.
- **Kept from p13r:** the fast detector, `--self-recheck`, `--still-strike`; `--lead-strike` and
  `--quick-drop` OFF (neither adopted: p14, p15); the 10-potion stock; the same map, route, seed
  and flags.
- **The run:** 4U's command with `--label xmas02-p16 --engage-screen`; the same before / beside /
  after steps.
- **Bars:**
  - **S1 (the hypothesis):** box engagements whose box path found no box <= 15 % (p13r 32 %, p15
    55 %).
  - **S2 (it turns into kills):** kills per monster seen >= 0.65 (p13r 0.611, the best so far).
  - **E1:** kills >= 40 / h. **D1:** live detector p50 <= 35 ms. **R1:** own-body class D <= 1.
    **F3:** far clicks while walking <= 2. **E3:** hard bars pass (NPC contacts included: far
    targets mean longer walks), 0 dead-end Fly Wings, stalls <= 39 / h. **Deaths:** 0.
  - Reported: engagements by source, the box path's target distance (d_px), strikes, class D by
    path, the supply.
- **Decisions:**
  - S1 + S2 + E1 pass and no regression bar fails: `--engage-screen` stays ON;
  - S1 passes, S2 fails: more targets but no more kills -> the far strikes' outcome is studied;
  - S1 fails: the walk carries her past the target before the box path looks (Batt's 20:18:10 /
    20:19:32 clips) -> stopping the walk at the engagement is the next change.

### 4X'. Amendment J (2026-11-08 ~21:5x ICT): Batt's answers to the 21:43 report, and the night's plan

Batt's words, translated (before 22:02:46, the turn's first `date`):
1. **`--engage-screen`:** "on, except the boss and its minions" -> ADOPTED for xmas_dun02 runs, with
   a BOSS GUARD (dungeon@9.7b): the map's boss and the monsters its NPC_SUMMONSLAVE skills call,
   from the KB (Stormy Knight; Garm Baby, a.k.a. Baby Hatii; Christmas Goblin). The xmas02 model
   has no class for them, so they are known by NAME: a Battle Log line whose bracketed name fits
   one (the reader's own fuzzy fit, over the bosses and the map's species together) -> the
   runner's Fly Wing escape and no box engagement for 30 s. Every run starts with
   `@killmonster2`, which kills the MVP too (it respawns 60-70 min later), so within a 30-min run
   the guard is the backstop; no boss or summon appeared in p10-p16 (packets). Tested on the
   reader's real reads (none fits a boss) and on garbled boss names.
2. **The next changes:** "approve all" -> (a) why far strikes miss, (b) stop the walk at an
   engagement, (c) the misses on her own sprite.
3. **`--quick-drop`:** "try it again together with --engage-screen" -> p17.
4. **Recordings:** "do it now" -> stage 2, one side-by-side recording (PNG + the GPU encode of the
   same session).
5. **Batt (the night):** "plan everything and work continuously tonight, improving step by step:
   walk without getting stuck, detect monsters fast, walk in and strike at once; keep improving
   until 06:00, then report."

**The night's plan (each pilot pre-registered in its own section BEFORE its run; one change at a
time; a change that passes its bars joins the base, else it is switched off):**
1. p17: the base (fast detector, `--self-recheck`, `--still-strike`, `--engage-screen` + the boss
   guard) + `--quick-drop`. p16's 68 class-D strikes were held 494.8 s, 27 % of its run.
2. p18: + (b) stop the walk at an engagement (its mechanics checked live first: a click on her
   own cell).
3. p19: + (c) the own-sprite misses (R1: 2 in p14, p15, p16), from a study of those strikes.
4. p20: + (a) the far misses (p16: 57 of 106 far strikes class D), from a packets study.
5. p21: + a faster box rhythm while walking ("detect fast"): the detector is 21 ms a call, the
   watcher looks once a second (BOX_EVERY_S).
6. Stage-2 recording beside one pilot (declared in that pilot's pre-registration).
7. Further steps chosen from what each result shows, until ~05:30; the report at ~06:00.

### 4Y. Pilot p17 pre-registration: --quick-drop beside --engage-screen (written BEFORE its run, 2026-11-08 22:07 ICT)

- **Why:** Amendment J item 3. With the screen-wide engagement p16 struck 134 times and held its
  68 misses 494.8 s (median 7.25 s): the give-up matters more now than in p15.
- **The base (p16's flags, adopted):** the fast detector, `--self-recheck`, `--still-strike`,
  `--engage-screen` now WITH the boss guard; `--lead-strike` off; 10 potions.
- **The one change against p16: `--quick-drop`** (dungeon@9.6, as in 4W: no arrow / damage 2.0 s
  after the click -> no lock; an arrow but no hit of ours 2.0 s after it -> the lock drops; then
  the box path again, twice a fight at most).
- **The run:** 4X's command with `--label xmas02-p17 --quick-drop`.
- **Bars:**
  - **Q1 (the hypothesis):** time held on class-D strikes (`quick_drop_study.py`): total <= 250 s
    (half of p16's 494.8) AND median <= 4.0 s (p16 7.25).
  - **Q2 (no cost):** quick drops of a strike that started an attack (K / A) <= 5.
  - **E1:** kills >= 80 / h (p16 87.9; it must not lose the gain). **D1** <= 35 ms; **R1**
    own-body class D <= 1; **F3** <= 2; **E3** hard bars pass, 0 dead-end Fly Wings, stalls
    <= 39 / h; **deaths** 0.
  - Reported: kills per monster seen (p16 0.80), the supply, the drops by why, boss_guard events.
- **Decisions:** Q1 + Q2 + E1 pass with no regression bar failing -> `--quick-drop` joins the
  base; Q1 fails -> off (studied); Q2 or E1 fails -> off.

### 4Z. Pilot p18 pre-registration: --far-single, a far strike clicks once and waits for the walk-up (written BEFORE its run, 2026-11-08 22:47 ICT)

- **Why:** Amendment J item 2 (a). The study (p16, packets): far strikes missed by DISTANCE --
  2-6 cells 5 of 41, 7-8 cells 19 of 30, 9-12 cells 33 of 35 -- and on 31 of 57 far misses the
  target stood still. On a far miss the client's first request was a WALK (a monster out of reach
  is walked to first), and the burst re-clicked the same screen point every 0.6 s while the camera
  scrolled: 3-5 walk requests in 4 s, the approach cancelled. Far hits mostly took ONE click.
- **The one change against p16: `--far-single`** (dungeon@9.8, e6f85581): a strike 4+ cells away
  clicks once and waits 1.0 s + 0.2 s a cell (at most 3.5 s) for the arrow or our damage line,
  never re-clicking; nearer strikes burst as before.
- **The base:** p16's (`--engage-screen` with the boss guard); `--quick-drop` OFF (p17).
- **The run:** the base command with `--label xmas02-p18 --far-single`.
- **Bars:**
  - **F1 (the hypothesis):** far strikes (2+ cells, lock_study) that are class D <= 35 % (p16 54 %,
    p17 60 %).
  - **E1:** kills >= 80 / h (p16 87.9). **D1** <= 35 ms; **R1** own-body class D <= 1; **F3** <= 2;
    **E3** hard bars pass, 0 dead-end Fly Wings, stalls <= 39 / h; **deaths** 0.
  - Reported: class D by distance (2-6 / 7-8 / 9+ cells), clicks per far strike, kills per monster
    seen, the supply.
- **Decisions:** F1 + E1 pass with no regression bar failing -> `--far-single` joins the base;
  F1 passes and E1 fails -> the wait costs more than it saves (studied); F1 fails -> off.
- R1 has failed in p14-p17 (2, 2, 2, 8 own-body class D): (c) is studied beside this run.

### 4Z'. Amendment K (2026-11-08 23:20 ICT): p18 died to the MVP -- the boss is avoided by SCHEDULE

- **What happened (p18, 22:52:36-23:16:54, `--far-single`):** at 23:16:52 the MVP Stormy Knight
  (1251) with its summons Garm Baby and Christmas Goblin hit the Rogue: [Stormy Knight] 1170, then
  5912 damage 0.4 s later (more than her 66 % HP); dead at 23:16:54. The Battle Log READ the boss
  ("Stormv ?night", which boss_of fits) 1.5 s before the end, but the reader's ~0.5 s lag cannot beat
  two hits 0.4 s apart: a reactive guard cannot save her from this boss.
- **Why the MVP was alive mid-run:** every run's setup `@killmonster2` kills the MVP only when it is
  ALIVE; it then respawns 60-70 min later (KB: delay 3,600,000 + 600,000 ms). p17's setup (22:12)
  had reset its timer; it came back at ~23:12-23:22, inside p18. p10-p17 never met it (packets).
- **Afterwards:** she is alive on the clear stand (the runner's `@warp`), HP 678 / 5070, bag 637 /
  2430; the setup's `@heal` restores her before the next run.
- **p18 is INVALID** as the test of `--far-single` (an environmental kill, not the change); it is
  repeated.
- **The schedule from now (the boss PREVENTED, not reacted to):**
  1. The experimenter (immunity ON) warps into xmas_dun02, types `@mobsearch Stormy Knight` and
     reads the reply on a screenshot; if the MVP is alive, `@killmonster2` at once: its respawn
     window is then known, [T + 60, T + 70] min.
  2. Two pilots of **25 min** each fit before T + 60 (setup + run + aftercare ~27 min each); the
     time box goes from 30 to 25 min for every pilot from p19 on (rates stay per hour).
  3. Then wait for the respawn (polling `@mobsearch` from T + 60), kill it, and repeat.
  4. The boss guard (Battle Log -> Fly Wing) stays as the backstop for the summons and Garm Baby
     (a regular spawn too, 30-min respawn, ~600-900 a hit: survivable, the guard acts).
- **For Batt (a decision, not taken here):** on the lab server the MVP spawn on xmas_dun02 could be
  disabled (as the MVP tombs were, bdb2f1c4); then the schedule constraint goes away.

### 4AA. Pilot p19 pre-registration: --far-single REPEATED (p18 died to the MVP), 25 min (written BEFORE its run, 2026-11-08 23:22 ICT)

- 4Z's change, base, bars and decisions unchanged; the time box 25 min (Amendment K). The MVP was
  killed at 23:21:23 (`@mobsearch` read "1[dead] Stormy Knight" after `@killmonster2`): its
  respawn window is 00:21-00:31; p19 and p20 end before 00:21.
- p19 is also stage 2's BASELINE pilot (gpu-recording.md 9.3: same map, the GPU detect path, no
  recorder) for p20, which repeats it with the stage-2 recorder beside it.

### 4AB. Pilot p20 pre-registration: p19 again, with the STAGE-2 RECORDER beside it (written BEFORE its run, 2026-11-08 23:24:39 ICT)

- **Why:** Amendment J item 4 (stage 2, gpu-recording.md 9.1, its bars pre-registered 22:46:20).
- **The bot:** p19's flags exactly (`--far-single`, 25 min): a second replicate of 4Z's change.
- **Beside it, not a change of the bot:** `record_session.py --backend rdp --fps 1 --format
  vpp-hevc444-10-q20 --also-png` for the run's 25 min, the media-rec sidecar encoding on the Arc's
  media engine (the detect server uses its compute). The recorder's grab and its PNG writer use the
  host CPU (~0.1-0.16 s a frame at 1 fps).
- **Bars:** 4Z's bars for the bot (F1, E1, D1, R1, F3, E3, deaths); stage 2's bars (9.1) for the
  recording, graded by `media_rec.py check` with p19 as the baseline (9.3).
- **The MVP window:** killed 23:21:23, respawn from 00:21:23; p20 must end by then (its run starts
  by 23:53, or its time box is cut to end before 00:20).

### 4AC. Pilot p21 pre-registration: --far-single + --far-approach, a far target is walked toward, then struck once (written BEFORE its run, 2026-11-09 00:18 ICT)

- **Why (p19 + p20, results in section 5):** `--far-single` fixed the 7-8 cell strikes (class D:
  p16 19 of 30 -> p19 6 of 20, p20 2 of 14) but not 9+ cells (p19 26 of 28, p20 18 of 19); F1 (far
  class D <= 35 %) failed in both (50 %, 51 %), so by 4Z's rule it is off on its own. Kills per
  monster seen were the best yet (0.911, 0.938).
- **The one change against the base (p16's flags): far strikes as ONE mechanism**, `--far-single`
  (dungeon@9.8) + `--far-approach` (dungeon@9.10, bac9c5a8): a box target 9+ cells away is walked
  toward (4 cells short of it on the line), the box path looks again after that walk (twice a fight
  at most), and a strike 4+ cells away clicks once and waits for the walk-up.
- **The run:** the base command with `--label xmas02-p21 --far-single --far-approach`, 25 min
  (Amendment K's MVP schedule).
- **Bars:** **F1** far class-D share <= 35 % (p16 54 %, p19 50 %, p20 51 %); **E1** kills >= 80 / h;
  **D1** <= 35 ms; **R1** own-body class D <= 1; **F3** <= 2; **E3** hard bars pass (NPC contacts:
  the approach walks are longer), 0 dead-end Fly Wings, stalls <= 39 / h; **deaths** 0.
  Reported: class D by distance, the approaches (count, the box path's next target distance),
  kills per monster seen.
- **Decisions:** F1 + E1 pass with no regression bar failing -> both flags join the base; F1
  fails -> both off (studied).

### 4AD. Pilot p22 pre-registration: --box-every 0.25, the box watcher looks four times a second (written BEFORE its run, 2026-11-09 01:01 ICT)

- **Why:** Batt's directive (2026-11-08 ~21:5x): "detect monsters fast; seen, walk in and strike
  at once". The box watcher (the live GPU detector, ~20.6 ms a call since the clock floor) looks
  once a second (BOX_EVERY_S 1.0): a monster that comes into view waits up to 1 s before the box
  path can see it, and the box it strikes is up to 1.5 s old (BOX_FRESH_S). p21: 1,568 calls in 25
  min (1.05 a second), the GPU idle ~98 % of the time.
- **p21's outcome decides the base (4AC):** F1 failed (36.4 %, bar <= 35 %), so `--far-single` and
  `--far-approach` are OFF; the base stays p16's flags (`--engage-screen` + the boss guard).
- **The one change against the base:** `--box-every 0.25` (dungeon@9.11, a39f4c17; BOX_FRESH_S
  unchanged at 1.5 s).
- **The run:** the base command with `--label xmas02-p22 --box-every 0.25`, 22 min (it must end
  before the MVP window opens at 01:32, Amendment K).
- **Bars:** **S2'** kills per monster seen >= 0.85 (the base: p16 0.80, p21 0.804); **E1** kills
  >= 80 / h; **D1** the GPU call p95 <= 35 ms at 4x the rate (p21 21.9); **R1** own-body class D
  <= 1; **E3** hard bars pass, 0 dead-end Fly Wings, stalls <= 39 / h; **deaths** 0.
  Reported: the calls a second, the box targets and struck, `boxes_after_ms` / the verdict p50,
  class D by distance, the supply.
- **Decisions:** S2' + E1 pass with no regression bar failing -> `--box-every 0.25` joins the base;
  otherwise off (studied).

### 4AE. Pilot p23 pre-registration: --reach-check, a box the server would not walk us to is passed over (written BEFORE its run, 2026-11-09 01:27 ICT)

- **Why (packets of p13r-p21, section 5 "the walk refusals"):** the server never answered 326
  standing walk requests of those pilots; p16-p21 (`--engage-screen`) spent 110-153 s a run in
  stuck spans (>= 3 ignored requests in a row: p16 133.9, p17 122.4, p19 110.3, p20 152.8, p21
  132.9 s) and 12-21 class-D box strikes a run began with an ignored request; p13r (before
  `--engage-screen`) 0 s and 0. The rule the server follows was found and measured: a walk within
  32 steps, at most 17 (`max_walk_path: 17`, the running server's conf/battle/client.conf:42) and
  at most 14 unless the straight line is clear -- 2,607 / 2,607 answered requests called accepted,
  325 / 326 ignored ones called refused. Replayed on p16-p21's box strikes, the check would have
  passed over 90 of 205 class-D strikes and 2 of 192 good ones. Monsters behind a wall are on the
  screen, so `--engage-screen` chose them; the client sends a monster click out of reach as a WALK.
- **The one change against the base (p16's flags: `--engage-screen` + the boss guard; p21's far flags and p22's
  `--box-every 0.25` are OFF):** `--reach-check` (dungeon@9.12, 8dd42962): the
  trigger and the box path pass over a box whose cell (and its 8 neighbours) the server would not
  walk us to on one click, from our minimap cell, on the server's map cache
  (`poring_dataset.walk.click_walk_ok`). Static map data and our pixel position only (rule 1).
  The run uses f0d6c75b (01:30, before the run): the same check, its grid projection memoised per
  cell (~2.3 ms a box otherwise).
- **The run:** the base command with `--label xmas02-p23 --reach-check`, 25 min (after the MVP is
  killed, Amendment K).
- **Bars:** **U1** stuck time (`walk_refusals.py`, 656609c2) <= 30 s; **U2** class-D box strikes
  whose first walk request was ignored <= 3; **E1** kills >= 80 / h; **D1** the GPU call p95
  <= 35 ms; **R1** own-body class D <= 1; **E3** hard bars pass, 0 dead-end Fly Wings, stalls
  <= 39 / h; **deaths** 0. Reported: reach_skip events, class D by distance and the F1 share, the
  time held on class D, kills per monster seen, the supply.
- **Decisions:** U1 + U2 + E1 pass with no regression bar failing -> `--reach-check` joins the
  base; otherwise off (studied).

### 4AF. Pilot p24 pre-registration: --kill-gap, a stopped hit stream is the kill (written BEFORE its run, 2026-11-09 02:11 ICT)

- **Why (packets, `fight_time.py` 29cb100f; its K3 3c29013e):** at Base 99 the Battle Log shows no exp line, so the
  runner never sees a kill. After the killing blow the lock waits LOCK_NO_HIT_S (3.5 s; "unlock no
  hits" at ~4.0 s after the death in p21's kill fights), then the defend scan (~2.3 s) finds nobody
  and the fight ends: from the death (packets) to fight_end a median 6.50 s (p16), 6.53 (p19), 6.46
  (p21), 6.47 (p22) -- 276.8 s of p21's 1,500. Our hits on a living target come every 0.47 s (p50
  0.47, p90 0.48 s, packets p16-p22); longer gaps were targets left and met again in a later fight.
- **The one change against the base (p16's flags, `--engage-screen` + the boss guard; `--reach-check` OFF by
  4AE's rule (p23)):** `--kill-gap` (dungeon@9.13, 1f8dc88e): after
  KILL_GAP_HITS (2) of our damage lines on the lock, none for KILL_GAP_S (1.5 s) is taken as the
  kill -- the lock goes (`unlock` why `kill_gap`), a `kill` event by `hit_gap` (the loot list as for
  an exp line), and the existing quiet-kill end closes the fight when nothing hit us for 2.5 s.
- **The run:** the base command with `--label xmas02-p24 --kill-gap`, 25 min.
- **Bars:** **K1** after-the-kill time p50 <= 3.0 s (`fight_time.py`; p16-p22 6.46-6.53 s); **E1**
  kills >= 80 / h; **K3** of the `hit_gap` kill events, those within 3 s after a packet death of a
  monster we hit >= 70 % (the rest are false kills: a target that walked off or teleported);
  **D1** the GPU call p95 <= 35 ms; **R1** own-body class D <= 1; **E3** hard bars pass, 0 dead-end
  Fly Wings, stalls <= 39 / h; **deaths** 0 and the lowest HP >= 30 %. Reported: kills per monster
  seen, the no-kill fights' time, the stuck time (U1 of the base), class D by distance.
- **Decisions:** K1 + E1 + K3 pass with no regression bar failing -> `--kill-gap` joins the base;
  otherwise off (studied).

### 4AG. Pilot p25 pre-registration: --reach-check REPLICATED (written BEFORE its run, 2026-11-09 02:39 ICT)

- **Why (p23, section 5):** `--reach-check` removed the stuck time (U1 133.9 / 132.9 / 133.1 s ->
  0 s), U2 (2) and E1 (86.4 / h) passed, and R1 failed at 2 own-body class D (the base p16's own
  count). All 7 own-body strikes came from the DEFEND SCAN's points on her sprite (cells (0, +-1)),
  a path `--reach-check` does not touch; 5 of the 7 were good (K). `--skip-own-cells` was weighed
  and NOT paired: it would drop those 5 good strikes with the 2 bad ones.
- **The run:** the base (p16's flags, `--engage-screen` + the boss guard; `--kill-gap` OFF by 4AF's
  rule (p24)) with `--label xmas02-p25 --reach-check`, 25 min -- 4AE's
  change, replicated.
- **Bars:** 4AE's, on p25 ALONE and unchanged: **U1** stuck time <= 30 s; **U2** class-D box
  strikes begun ignored <= 3; **E1** kills >= 80 / h; **D1** the GPU call p95 <= 35 ms; **R1**
  own-body class D <= 1; **E3** hard bars pass, 0 dead-end Fly Wings, stalls <= 39 / h; **deaths**
  0. Reported beside p23's: everything 4AE reported, and R1 pooled over p23 + p25.
- **Decisions:** every bar passes on p25 -> `--reach-check` joins the base (the report names p23's
  R1 failure beside it); otherwise it stays off.

### 4AH. Pilot p26 pre-registration: --kill-gap again, with its two fixes (9.13b + 9.13c) (written BEFORE its run, 2026-11-09 03:21 ICT)

- **Why (p24, section 5):** the rule did what it was for -- after a real kill the fight ended
  1.96 s after the death (6.46-6.53 s before) -- but E1 (74.3 / h) and K3 (62.2 %) failed on two
  side effects, each now fixed and checked against p24's own record:
  - 9.13c (9436a75b): KILL_GAP_HITS 2 -> 5; p24's false kills were mostly short contacts (2-4 of
    our hits, the target walked off alive); 5 keeps 27 of its 28 real kills and 3 of 17 false;
  - 9.13b (7ed2d7d8): a box fight the quiet-kill rule closes before the box path looked is no box
    miss (p24: 14 of the first 15 misses, 10 spots ignored).
- **The one change against the base (p16's flags, `--engage-screen` + the boss guard; `--reach-check` OFF (p25
  failed U1 / U2)):** `--kill-gap` as it now stands (9.13c; the run
  record says `"kill_gap": [1.5, 5, "9.13c"]`).
- **The run:** the base command with `--label xmas02-p26 --kill-gap`, 25 min.
- **Bars (4AF's, unchanged):** **K1** after-the-kill p50 <= 3.0 s; **E1** kills >= 80 / h; **K3**
  inferred kills within 3 s after a death of ours >= 70 %; **D1** p95 <= 35 ms; **R1** own-body
  class D <= 1; **E3** hard bars pass, 0 dead-end Fly Wings, stalls <= 39 / h; **deaths** 0, the
  lowest HP >= 30 %. Reported: box misses after a quiet-kill end (9.13b's count: 0 expected),
  fights and no-kill fights, kills per monster seen, the stuck time.
- **Decisions:** K1 + E1 + K3 pass with no regression bar failing -> `--kill-gap` joins the base;
  otherwise off.

### 4AI. Pilot p27 pre-registration: --reach-check 9.12b, the target is the cell the client picks (written BEFORE its run, 2026-11-09 03:49 ICT)

- **Why (p23, p25, section 5):** `--reach-check` cut the stuck time from 110-153 s a run to 0 s
  (p23) and 43.3 s (p25); p25 failed U1 / U2 because on this map's raised floors the box path's
  flat projection put a target 4-6 cells off (p25 426 s: rel (-2, -6) -> (108, 247); the monster
  at (108, 242) by the packets; the client walked toward (108, 243)). The client resolves a pixel
  to the FIRST tile top the camera ray comes down through (poring_dataset.picking; memory "client
  picks raised tops"); the picked cell under the box's foot names the monster's cell.
- **The one change against the base (p16's flags, `--engage-screen` + the boss guard; `--kill-gap` OFF (p26
  failed E1)):** `--reach-check` as it now stands, 9.12b
  (c8544a05; the run record says `"reach_check": [17, 14, "9.12b"]`). Offline over p16 / p21 /
  p23 / p25's box strikes (our packet cell + the strike's pixel): class D begun with an ignored
  request caught 32 of 33 (9.12: 25), good strikes passed over 1 of 167 (9.12: the same 1).
- **The run:** the base command with `--label xmas02-p27 --reach-check`, 25 min.
- **Bars (4AE's, unchanged):** **U1** stuck time <= 30 s; **U2** class-D box strikes begun
  ignored <= 3; **E1** kills >= 80 / h; **D1** the GPU call p95 <= 35 ms; **R1** own-body class D
  <= 1; **E3** hard bars pass, 0 dead-end Fly Wings, stalls <= 39 / h; **deaths** 0. Reported
  beside p23 / p25: reach_skip events, class D by distance, the time held on class D, kills per
  monster seen, the after-kill time.
- **Decisions:** every bar passes -> `--reach-check` (9.12b) joins the base; otherwise off.

### 4AK. Amendment L (2026-11-09 ~06:3x ICT): Batt's answers to the 05:37 report, and the new route work

Batt's answers (quoted, then in English):
1. Recording: "ใช้ การ์ดจอแทนได้เลย" -- use the GPU video in place of PNG. Stage 3 of
   gpu-recording.md is DECIDED (the ADR-0010 amendment; built and recorded there).
2. The MVP spawn: "ไม่ปิด เทรน bot ให้รู้จักบอสด้วย เห็นในหน้าจอ วิงหนีเลย" -- do NOT disable it;
   train the bot to know the boss: seen on the screen -> Fly Wing away at once. A sight-based
   recognizer for the Stormy Knight (and its summons) follows the Orc Lord's (scripts/mvp_watch.py,
   orclord-recognizer.md). Caution carried over: the Orc Lord's sight-flee was NOT adopted on
   10-26 (it hit within ~1 s of entering view). So Amendment K's schedule (@mobsearch +
   @killmonster2) stays the protection until a Stormy Knight flee proof passes.
3. The next pilot: "เดินเข้าใกล้ก่อนตี" -- walk in close before striking: the far mechanism
   (`--far-single --far-approach`) on the new base FIRST (4AJ). `--kill-gap` with the 3-s block
   lifted comes later.
4. `--skip-own-cells`: "ให้คุณตัดสินใจเองข้อนี้" -- my decision: it stays OFF. In p23, 5 of its 7
   own-sprite strikes were HITS (monsters right N / S of her), and own-sprite misses are 0-2 a run
   (p23-p27); skipping those points would lose more hits than it saves.

The new request (Batt, quoted then in English): "อยากให้ลองเพิ่ม การเดินสุ่มใน map นี้ได้เลย
ไม่จำเป็นต้องเดินชิดขอบ ... อยากพยามเดินไปทางใหม่ๆ โดยดูพิกัดบน มินิ map และบันทึกไว้ด้วย ว่าจุดไหน
เดินได้ เดินไม่ได้ เอาข้อมูล map มาจาก data ก่อนก็ได้ พยายามหาเส้นทางที่สามารถ kill ต่อชั่วโมงได้เยอะสุด"
-- add random / new-way walking on this map (not only the edge loop), by the minimap's coordinates;
record where she could and could not walk (seeding from the map data); find the route with the
most kills per hour. Plan (section 4AL, written before its pilots):
- a persistent map-knowledge file per map (our own pixel observations only: positions read from
  the minimap, walk clicks that did / did not move us, boxes seen, fights, landed strikes,
  inferred kills, time spent), seeded from the server map cache's walkable cells;
- a search mode that walks to NEW or productive regions (explore + exploit over map regions),
  every leg routed on the server grid and checked with `click_walk_ok` (the walk-refusal rule);
- route decisions use only what the bot itself saw (rule 1); packets score the runs offline.

### 4AJ. Pilot p28 pre-registration: the far mechanism again (`--far-single --far-approach`), on the base with `--reach-check` (written BEFORE its run, 2026-11-09 06:37 ICT)

- **Why (p16-p22's box strikes on REACHABLE targets only -- `reach_ok` from our packet cell + the
  strike's rel; section 5):** class D at 2-6 cells is low everywhere (p16 4 / 38, p17 5 / 26, p19
  4 / 23, p20 3 / 15, p21 8 / 38, p22 3 / 17). At 7-8 cells it is high WITHOUT `--far-single` (p16
  17 / 28, p17 12 / 24, p22 5 / 16) and low WITH it (p19 2 / 16, p20 0 / 12, p21 3 / 13). At 9+
  cells it is ~90 % without an approach (p16 18 / 20, p17 17 / 22, p19 15 / 17, p20 4 / 5, p22
  10 / 11); p21's approach left 1 such strike (not D). p21 failed F1 by 1.4 points while ~half of
  its far misses were targets the server would not walk us to (12 of 26 class D began with an
  ignored request) -- which `--reach-check` now removes (adopted after p27: U2 0). On the new base p27 still missed 13
  of 16 strikes at 9+ cells and 8 of 23 at 7-8 (F1 35.6 %). Batt chose this pilot first (Amendment L 3).
- **The one change against the base (p16's flags + `--reach-check` 9.12b, Amendment L):** the far mechanism of 4AC as ONE change,
  `--far-single --far-approach` (dungeon@9.8 + 9.10).
- **The run:** the base command with `--label xmas02-p28 --far-single --far-approach`, 25 min.
- **Bars:** **F1** far class-D share <= 25 % (p21 36.4 %, of which 12 of 24 far D began ignored);
  **E1** kills >= 80 / h; **U1** stuck time <= 30 s (the base's own bar holds); **D1** the GPU call
  p95 <= 35 ms; **R1** own-body class D <= 1; **E3** hard bars pass, 0 dead-end Fly Wings, stalls
  <= 39 / h; **deaths** 0. Reported: class D by distance, the approaches, the time held on class D,
  kills per monster seen, reach_skip events.
- **Decisions:** F1 + E1 pass with no regression bar failing -> both flags join the base; otherwise
  off (studied).

### 4AL. Pilots p29-p31 pre-registration: --explore, phase E1 (learning the map) (written BEFORE p29, 2026-11-09 07:08 ICT)

- **Why:** Batt's request (Amendment L): walk new ways (not only the edge loop), record where she
  could and could not walk, find the route with the most kills per hour. `--explore` (dungeon@9.14,
  1da5179a): the route grid's component from the patrol start in 10-cell regions (xmas_dun02: 636
  regions, 50,183 cells); the next region is SAMPLED by good fights per minute (a prior at the map's
  mean) + a novelty bonus - a distance cost; a passive recorder books, per region, the time spent,
  arrivals, engagements, fights and GOOD fights (>= 5 of our damage lines: on p24's packets 27 of 28
  real kills, 3 of 17 false), and per cell the minimap reads and the stalled walk targets; the file
  `data/maps/xmas_dun02/explore.json` grows run by run. Pixels only (rule 1); packets score offline.
- **Phase E1 = learning, three runs (p29, p30, p31), each 25 min inside the MVP schedule:** the
  base (p16's flags + `--reach-check` 9.12b + `--far-single --far-approach`, after p28) + `--explore`. Exploration is expected to cost kills (long legs, empty regions):
  E1 adopts nothing; its bars are SAFETY and REGRESSION only.
- **Bars (each run):** **deaths** 0; **E3** hard bars pass, 0 dead-end Fly Wings, stalls <= 39 / h;
  **U1** stuck time <= 30 s (the base's own bar); **X1** the run's knowledge saved and merged
  (`explore_saved` with the run counted); **X2** no `ev_hook_error`. A run failing a bar stops the
  phase (studied first).
- **Reported (each run and pooled):** kills / h and kills per monster seen (beside p27 / p28, the
  edge loop on the same base); regions targeted / arrived / blocked / timed out; distinct cells
  visited and regions with >= 1 min spent; the good fights per minute by region; refused cells;
  the coverage map (`explore_map.py plot`).
- **Then phase E2 (pre-registered after E1, from E1's numbers):** an exploit run (the learned
  regions, less novelty) against the edge loop on kills / h -- the adoption decision.

### 4AM. Pilot pre-registration: --walk-pick, a walk target the client picks (written BEFORE its run, 2026-11-09 08:48 ICT)

- **Why (p30, section 5; packets of p28-p30):** the client resolves a click to the first tile top
  the camera ray comes down through; on xmas_dun02's raised floors a walk target's pixel can pick
  another cell, and then the client sends NO walk request. Walk clicks whose picked cell was off by
  more than 1 or unwalkable went unsent 17 of 39 times; all other walk clicks 17 of 869. p30's
  `stuck` Fly Wing was 4 dropped clicks in 18 s at (161, 116).
- **The one change against the base (the base after 4AN's verdict: with `--explore` if it joins):** `--walk-pick` (dungeon@9.15, 9e68ae89): `fits`
  takes a walk target only when `picked_cell` under its pixel is on the route grid and within 1
  cell of it; `walk_target` then takes a nearer path cell.
- **The run:** the base command + `--walk-pick`, label `xmas02-p34`, 25 min.
- **Bars:** **W1** walk clicks with no walk request within 1.2 s (packets) <= 1.5 % of the clicked
  walk events (E1: p29 1.7 %, p30 7.2 %); **W2** 0 `stuck` and 0 `dead_end` Fly Wings; **E1**
  kills >= 80 / h; **U1** stuck time <= 30 s; **D1** p95 <= 35 ms; **R1** own-body class D <= 1;
  **E3** hard bars pass, stalls <= 39 / h; **deaths** 0. Reported: `walk_pick_skip` counts, stalls,
  kills per monster seen.
- **Decisions:** W1 + W2 + E1 pass with no regression bar failing -> `--walk-pick` joins the base.

### 4AN. Pilots pre-registration: explore phase E2 -- the adoption test against the edge loop (written BEFORE its runs, 2026-11-09 08:48 ICT)

- **Why:** E1 (p29-p31) is learning only (4AL). Its runs gave 158.4 and 160.8 kills / h (p31:
  146.1) against the edge loop's 124.7 (p28) on the same base, with the same kills per monster
  seen (0.985 / 0.905 vs 0.981) and more monsters seen (26.8 / 29.6 vs 21.2 per 10 min). The time
  of day and the map's state differ between runs; E2 interleaves the two search modes.
- **The runs (25 min each, the base, the MVP schedule):** p32 = the edge loop (the base as is), then
  p33 = `--explore` (the knowledge file as E1 left it, plus what each run adds).
- **The bar (pooled):** explore's mean kills / h over p29, p30, p31 and p33 >= 1.15 x the edge
  loop's mean over p28 and p32; with deaths 0 and the E1 safety bars on p33.
- **Decisions:** the bar passes -> `--explore` joins the base (the edge loop stays selectable);
  otherwise explore stays an option, studied.

### 4AO. Pilot p35 pre-registration: --explore-cover, explore's novelty from coverage (written BEFORE its run, 2026-11-09 11:02 ICT)

- **Why (Batt, 2026-11-09 ~09:5x, on the knowledge map):** "the right side is walked much less
  than the left (the green lines)". E1's east-half share (x >= 130) of each run's visited cells:
  p29 27.0 %, p30 27.6 %, p31 51.4 %, against 48.9 % of the reachable map. Each E1 run added ~600
  new cells (607, 598, 600). The novelty bonus counted ARRIVALS, and most regions walked through
  were never "arrived at" (0 arrivals), so walked and unwalked regions looked equally new.
- **The one change against the base (p16's flags + `--reach-check` + `--far-single --far-approach` + `--explore`, after E2; `--walk-pick` OFF after p34):** `--explore-cover` (dungeon@9.14b, 29a1b7f5): the
  novelty is COVER_W (2.0) x (1 - the share of a region's reachable cells ever read as our
  position: the knowledge file + the run).
- **The run:** the base command + `--explore-cover`, label `xmas02-p35`, 25 min.
- **Bars:** **C1** new cells (not in the knowledge file before the run) >= 700 (E1: ~600 a run; p33 532: 2,337 - 1,805);
  **C2** the east-half share of the run's visited cells within 35-65 %; **E1** kills >= 80 / h;
  the E1 safety bars (deaths 0, E3, U1 <= 30 s, X1, X2). Reported: kills / h beside the explore
  runs, regions targeted / reached, the coverage map.
- **Decisions:** C1 + E1 pass with no safety bar failing -> `--explore-cover` joins the base
  (C2 reported with it).

### 4AP. Pilot p36 pre-registration: --walk-pick again, with its 9.15b fallback (written BEFORE its run, 2026-11-09 11:36 ICT)

- **Why (p34, section 5):** `--walk-pick` took the client's dropped walk clicks from 1.7-7.2 % (p29,
  p30, p33) to 0 of 228, but R1 failed (2) and the run had an `idle` Fly Wing the flag caused: at
  (143, 118) no path cell passed the pick check for 45 s, so no click went out. 9.15b (60ad8935):
  when no candidate passes, the plain fits (today's click) -- the stall / carve path handles it.
- **The one change against the base (p16's flags + `--reach-check` + `--far-single --far-approach` + `--explore`; `--explore-cover` OFF after p35):** `--walk-pick` as it now stands (9.15b; the run
  record says `"walk_pick": [1, "9.15b"]`).
- **The run:** the base command + `--walk-pick`, label `xmas02-p36`, 25 min.
- **Bars (4AM's, unchanged):** **W1** clicked walks never sent <= 1.5 %; **W2** 0 `stuck`, 0
  `dead_end` -- and now also 0 `idle` -- Fly Wings; **E1** kills >= 80 / h; **U1** stuck time <= 30 s;
  **D1** p95 <= 35 ms; **R1** own-body class D <= 1; **E3** hard bars pass, stalls <= 39 / h;
  **deaths** 0. Reported: `walk_pick_skip`, `walk_pick_fallback`, stalls.
- **Decisions:** every bar passes -> `--walk-pick` joins the base.

### 4AQ. Pilot p37 pre-registration: --kill-gap again on the new base -- kills seen from our damage, loot only after them (written BEFORE its run, 2026-11-09 12:08 ICT)

- **Why (Batt, 2026-11-09 ~12:0x, two clips from p36):** "while walking it scans for dropped
  items although it did not fight; scan only after a kill -- if no exp line, use the damage: no
  damage of ours in the last 5 s, no scan" and "after the kill and the drop the scan shows the
  hand, but the bot does not pick the item up". The packets: **at Base 99 the bot has picked up
  almost nothing** -- p28-p36 0-2 pickups for 18-46 floor items a run; every loot step planned 0
  hovers (the loot list is built from exp-line kills, and Base 99 shows no exp line). The clip at
  11:56 was the DEFEND scan (a Cruiser hitting her, its box hidden by her sprite), not a loot scan.
  With `--kill-gap` (kills inferred from our damage lines) the loot list fills and the loot step
  picks: p24 9 of 10 floor items, p26 10 of 16. p26's E1 failure (74.4 / h) ran WITHOUT
  `--reach-check` (208.7 s stuck, the night's worst); the base now has reach-check, the far
  mechanism, explore and walk-pick.
- **The one change against the base (p16's flags + `--reach-check` + `--far-single --far-approach`
  + `--explore` + `--walk-pick`):** `--kill-gap` (9.13c: after 5 of our damage lines on the lock,
  none for 1.5 s = the kill -> the loot list at that cell, the quiet-kill end, the loot step).
  Batt's 5-s rule holds by construction (the inference fires 1.5 s after our last hit).
- **The run:** the base command + `--kill-gap`, label `xmas02-p37`, 25 min.
- **Bars:** **L1** pickups >= 50 % of the floor items that appeared (`fight_time.py` L1; base 0 %);
  **K1** after-the-kill p50 <= 3.0 s; **K3** inferred kills real >= 70 %; **E1** kills >= 80 / h;
  the base's own bars: **U1** stuck <= 30 s, **W1** unsent walk clicks <= 1.5 %, **D1** p95 <=
  35 ms, **R1** own-body class D <= 1, **E3** hard bars pass, 0 dead-end / stuck / idle Fly Wings,
  **deaths** 0. Reported: L2 (hovering loot steps with no death of ours in the 10 s before; p26 13 of
  23), items per hour, the loot time, kills per monster seen.
- **Decisions:** every bar passes -> `--kill-gap` joins the base.

### 4AR. Amendment M (2026-11-09 ~13:0x ICT): Batt's answers to the 12:48 report; R1 pooled; a scorer correction

Batt's answers (quoted, then in English):
1. "ไม่ฆ่าบอส ทำเรื่องเรียกบอสต่อได้เลย" -- not killing the boss as the answer: go on with the
   boss-summoning work (the Stormy Knight recognizer, round 2). Until a recognizer passes its live
   flee proof, the pilots keep Amendment K's kill-before-run as their only protection (stated to
   Batt; he may say otherwise).
2. R1 pooled: "ok". **From the next pre-registration on, R1 = the own-body class D of the pilot and
   its 3 preceding base runs together, <= 1.5 a run on average (<= 6 over the 4 runs).** p23's and
   p34's verdicts stand as made under the old R1.
3. "แก้เรื่องเก็บของก่อน ถ้ามี exp ขึ้นก็ไม่ใช้ exp ถ้าไม่มีก็ให้สังเกตจาก damage หายไป หรือท่าทาง
   ตัวละครที่หยุดไป หาทางอื่นสำรองด้วยอย่ายึดติดกับการดู exp อย่างเดียว" -- fix the looting first;
   use the exp line when it shows, otherwise the damage lines stopping or the character's attack
   stopping; keep other fallbacks; do not rely on the exp line alone.
4. The CPU: Batt's own (closed).

**A scorer correction (be98ad8f), found while studying 3.:** `fight_time.our_kills` mapped each
monster gid to its LAST death; the server reuses gids for later spawns, so a later spawn's death
overwrote the real kill. Re-scored with the fixed scorer (the pre-registered quantities unchanged):

| | K3 as scored | K3 corrected | L2 as scored | L2 corrected | the run's verdict |
|---|---|---|---|---|---|
| p24 (9.13) | 62.2 % | 66.7 % (30 / 45) | 12 / 38 | 12 / 38 | unchanged: E1, K3 fail -> off |
| p26 (9.13c) | 71.0 % | 87.1 % (27 / 31) | 13 / 23 | 9 / 23 | unchanged: E1 fail -> off |
| p37 (9.13c, new base) | 68.9 % | **96.7 % (59 / 61)** | 10 / 33 | **2 / 33** | K3 now PASSES; W1 (3.6 %) still fails -> off |

- So kills inferred from our damage lines were real 59 times in 61 on the new base, and loot scans
  followed a real kill 31 times in 33: Batt's rule ("scan only after a kill") is met by them.
- **p37's remaining failure, W1 (study):** 11 walk clicks never sent; 8 of them came 0.7-4.1 s
  after a loot step that had clicked an item, none landed on a floor item, and no later request
  went to the clicked cell (truly dropped). The likely cause is the stale position after a pickup
  walk (memory "loot treadmill: stale odometry"): the next walk target is computed from where she
  was, not where she is. The fix (9.13d) waits for a fresh position read after a loot step before
  the next walk click -- p38.

### 4AS. Pilot p38 pre-registration: --kill-gap 9.13d -- loot after kills seen from our damage, the walk waits for a fresh position after a pickup (written BEFORE its run, 2026-11-09 13:07 ICT)

- **Why (Amendment M, 4AR):** Batt: fix the looting first; use the exp line when it shows, else the
  damage stopping or the attack stopping, with fallbacks. The cues, in order (all pixels):
  1. the Battle Log's exp line (`base_exp`) when it shows -- the existing kill path, unchanged;
  2. our damage lines stopping after >= 5 on the lock (`--kill-gap`: on p37's packets 59 of 61
     such inferences were real deaths, corrected scorer);
  3. the lock's "no hits" unlock (3.5 s) as the last fallback (no loot from it).
  The attack-motion cue: our damage lines ARE the record of each landed swing (one line a hit,
  every 0.47 s), so "the swings stopped" is cue 2; a sprite-pose reader was not built. The box-gone
  cue was tested offline on p24 / p26 / p37 and does not separate death from departure (precision
  0.59-0.74 either way): not used.
- **The one change against the base (p16's flags + reach-check + far mechanism + explore +
  walk-pick):** `--kill-gap` as it now stands (9.13d, 59a22171; the record says `"kill_gap": [1.5, 5,
  "9.13d", 0.8]`).
- **The run:** the base command + `--kill-gap`, label `xmas02-p38`, 25 min.
- **Bars:** **L1** pickups >= 50 % of floor items; **K1** after-the-kill p50 <= 3.0 s; **K3**
  inferred kills real >= 70 % (the corrected scorer, be98ad8f); **E1** kills >= 80 / h; **W1**
  unsent walk clicks <= 1.5 %; **U1** stuck <= 30 s; **D1** p95 <= 35 ms; **R1 (pooled, Amendment
  M)** own-body class D of p38 + p33 + p35 + p36 <= 6 (those three: 1 + 0 + 1); **E3** hard bars,
  0 dead-end / stuck / idle Fly Wings; **deaths** 0. Reported: L2, the loot time, items / hour.
- **Decisions:** every bar passes -> `--kill-gap` joins the base.

### 4AT. Pilot p39 pre-registration: --loot-first (9.16) on top of --kill-gap -- the loot step right after the kill, no instant-end loop, the scan's hand clicked (written BEFORE its run, 2026-11-09 14:0x ICT)

- **Why (p38's study, section 5; Batt: "fix the looting first"; his clip 2: "the scan finds the
  hand, but the bot does not pick the item up"):**
  - 1,057 of p38's 1,144 engages ended in the same tick (the quiet-kill loop);
  - only 17 of its 53 kills had a loot step within 5 s (median 14.3 s), because a box on the
    screen started the next fight before the loot step ran;
  - 29 pickup hands read by 11 defend scans were passed by.
- **The one change against p38 (the base + `--kill-gap` 9.13d):** `--loot-first` (9.16; the
  record says `"loot_first": ["9.16"]`):
  1. a box ALONE starts no fight while a kill's loot step is pending (a hit, an HP drop or a Miss
     still starts it at once);
  2. the quiet-kill rule ends only a fight that began before the kill;
  3. a defend scan that found no sword clicks the first pickup hand it read (no hit within 1 s);
     that spot joins the loot list, and the 9.13d settle holds the next walk.
  The loot step itself is unchanged (the trim: 9 hovers, nearest first).
- **The run:** the base + `--kill-gap --loot-first`, label `xmas02-p39`, 25 min, the MVP dead by
  the schedule; R2-H2's PNG recording beside it (stormy-knight-recognizer.md 7).
- **Bars:**
  - **L1** pickups >= 50 % of floor items (fight_time.loot_summary);
  - **L3 (new, the mechanism)** kills followed by a loot step with a list within 5 s >= 80 % (the
    runner's events; p38: 17 / 53; 48 of its 53 kills ended a quiet fight at once);
  - **L4 (new)** engages ended by the quiet-kill rule in the same tick (< 50 ms) <= 5 % of engages
    (p38: 1,057 / 1,144);
  - **K1** after-the-kill p50 <= 3.0 s; **K3** inferred kills real >= 70 %; **E1** kills >= 80 / h;
    **W1** unsent walk clicks <= 1.5 %; **U1** stuck <= 30 s; **D1** p95 <= 35 ms;
  - **R1 (pooled)** own-body class D of p39 + p33 + p35 + p36 <= 6 (those three: 1 + 0 + 1);
  - **E3** hard bars, 0 dead-end / stuck / idle Fly Wings; **deaths** 0.
  Reported: L2, the scan-hand clicks (and those held by a hit), `loot_first_held` ticks, the loot
  time, items / hour, boss-guard Fly Wings.
- **Decisions:** every bar passes -> `--kill-gap` and `--loot-first` join the base together (the
  loot needs the inferred kills; `--kill-gap`'s only failed bar in p38 was W1, whose post-hoc is a
  walking-geometry episode). W1 fails again -> both stay off and the walk case (targets the client
  refuses, p38's 7-click episode) goes first.

### 4AU. Pilot p40 pre-registration: --walk-pick-step (9.15c) -- a pickable one-click step instead of the plain fallback (written BEFORE p39's verdict and p40's run, 2026-11-09 14:5x ICT)

- **Why (W1, the walk clicks the client never sends):** an offline replay of the client's picking
  (poring_dataset.picking, the camera and the GAT; every clicked walk of p34-p38):
  - p37's 11 unsent clicks all had a GOOD pick: the stale position after a pickup walk, which
    9.13d's settle fixed (p38: 3 such clicks);
  - **7 of p38's 10 unsent clicks had a BAD pick** (the client picks a cell ~6 rows off), all in one
    21-s episode on the ramp at (153-164, 116-122): a raised block (altitude 40) south of her covers
    the pixels of every cell around her; no pixel within 160 px picks the target. They were 9.15b's
    plain fallback (no path cell passed the pick check). Of the 217 sent clicks, 2 had a bad pick.
  - Offline, the new step finds a pickable one-click cell nearer the goal in 4 of the episode's 5
    situations (the fifth keeps the plain click), in 100-190 ms.
- **The one change:** `--walk-pick-step` (9.15c; with `--walk-pick`; the record says
  `"walk_pick_step": [9, "9.15c"]`): when no path cell passes the pick check, the cell within 9
  that passes it and that the server walks us to on one click (`click_walk_ok`), nearest the goal by
  grid steps and nearer than we are; 9.15b's plain click stays the last resort. Every walk event now
  records which fallback it used (`pick`: `step` / `plain`; a record only, in every run).
- **The run:** the base + `--kill-gap --loot-first --walk-pick-step`, label `xmas02-p40`, 25 min,
  the MVP dead by the schedule (killed 14:34:50).
- **Bars:** **W1** unsent walk clicks <= 1.5 % (the target); the rest as 4AT: **L1** >= 50 %,
  **L3** >= 80 %, **L4** <= 5 %, **K1** p50 <= 3.0 s, **K3** >= 70 %, **E1** >= 80 / h, **U1** <= 30 s,
  **D1** p95 <= 35 ms, **R1 (pooled)** own-body class D of p40 and its 3 preceding base runs <= 6,
  **E3** hard bars, 0 dead-end / stuck / idle Fly Wings (a `pos_unread` Fly Wing is reported, not
  counted, as in p29-p33), **deaths** 0. Reported: the steps and plain fallbacks taken, unsent
  clicks by `pick`, stalls.
- **Decisions (p39's verdict is not known when this is written):**
  - p39 passed every bar (`--kill-gap` + `--loot-first` in the base): every p40 bar passes ->
    `--walk-pick-step` joins the base;
  - p39 failed W1 only: every p40 bar passes -> `--kill-gap`, `--loot-first` and
    `--walk-pick-step` join the base together;
  - p39 failed another bar: p40 reports W1 for 9.15c, and nothing joins on p40 alone.

### 4AV. Pilot p41 pre-registration: the new base, a confirmation run (written BEFORE its run, 2026-11-09 15:3x ICT)

- **Why:** p40 adopted three flags at once (`--kill-gap`, `--loot-first`, `--walk-pick-step`), and
  W1 passed close to its bar (1.04 % vs 1.5 %; p39 2.07 %). One more run of the unchanged base
  shows whether the result holds. Nothing is changed.
- **The run:** the base (p16's flags + `--reach-check --far-single --far-approach --explore
  --walk-pick --kill-gap --loot-first --walk-pick-step`), label `xmas02-p41`, 25 min, the MVP dead
  by the schedule.
- **Bars:** 4AU's, unchanged (W1, L1, L3, L4, K1, K3, E1, U1, D1, R1 pooled over p41 + p40 + p36 +
  p35, E3, deaths). Reported: the no-kill fights (count, time, by engage; p40: 31 / 269.9 s, box
  25 / 196.6 s, strikes ending "arrow" 9 / "bound" 7), boss-guard Fly Wings, items / hour.
- **Decisions:** every bar passes -> the base is confirmed. A bar fails -> the base stays as
  adopted (4AU), the failure is studied first and named as the next pilot's subject.

### 4AW. Pilot p42 (by Amendment N, 4AX) pre-registration: --quiet-scan (9.17) -- no ring scan for an attacker without damage in the last 5 s (written BEFORE its run, 2026-11-09 15:5x ICT; re-queued 16:1x: p41 failed W1, so by 4AV the NEXT pilot is W1's, and this one runs after it)

- **Why (Batt's clip 1, ~12:3x: "why does the bot, walking along, scan around although it did not
  fight a monster ... if no damage happened in the last 5 s, there is no need to scan"):** the
  scan in that clip was the DEFEND scan (a fight with no lock, or after a walk stall). p38-p40
  (packets, `fight_time.py` Q1, committed before this run): 39 / 28 / 34 defend scans started with
  no hit on us in the 5 s before; they found a monster 7 times in 101, at ~2.7 s each (~75-100 s a
  run). In p40, 3 of its first 6 box fights with no kill were a box path that never struck plus
  this scan.
- **The one change against the base:** `--quiet-scan` (9.17; the record says `"quiet_scan": [5.0,
  "9.17"]`): the ring scan runs only when the SCREEN showed damage within 5 s -- a hit line on us,
  an HP drop, a Miss at us, or a damage line of ours (pixels only); else a fight with no lock ends
  at once (and a walk stall re-plans without the scan). The box path, the lock, the quiet-kill end
  and the loot step are unchanged.
- **The run:** the base + `--quiet-scan`, label `xmas02-p42` (Amendment N, 4AX), 25 min, the MVP dead
  by the schedule.
- **Bars:**
  - **Q1 (the mechanism)** defend scans with no act on us in the 5 s before (`fight_time` Q1)
    <= 8 (p38-p40: 39 / 28 / 34; the rule still scans after our own damage lines);
  - **S1 (safety)** damaging hits on us <= 14 per 10 min (`fight_time` S1; p38-p40: 11.2 / 10.8 /
    11.2);
  - the base's bars as 4AU: **W1** <= 1.5 %, **L1** >= 50 %, **L3** >= 80 %, **L4** <= 5 %, **K1**
    <= 3.0 s, **K3** >= 70 %, **E1** >= 80 / h, **U1** <= 30 s, **D1** <= 35 ms, **R1 (pooled)**
    the pilot and its 3 preceding base runs <= 6, **E3**, **deaths** 0.
  Reported: E1 against p40 / p41 (the expected gain is ~5 %), the skips (`quiet_scan_skip`,
  `quiet_scan_skip_stall`), the no-kill fights' time, the lowest HP.
- **Decisions:** every bar passes -> `--quiet-scan` joins the base.

### 4AX. Amendment N (2026-11-09 16:2x ICT, written BEFORE p42): the order of the next pilots; a question to Batt on W1

- **What 4AV said:** a failed bar is studied first and named as the next pilot's subject. p41
  failed W1 (1.57 %); the study is in p41's entry (section 5).
- **What the study found:** the base's W1 is an ~1-2 % residual (p39 2.07, p40 1.04, p41 1.57 %):
  the client ignores the click and sends nothing else; good picks, no fallback, no direction; a
  repeated target explains 9 of 33. Each costs ~1.3 s (~5 s a run). No single-cause fix exists
  yet, so a W1 pilot now would test nothing in particular.
- **The order, therefore:** p42 runs 4AW's `--quiet-scan` (the defend scans without damage, ~75-100
  s a run) with EVERY bar as 4AW wrote it, W1 <= 1.5 % included -- nothing is relaxed. W1 stays
  the open subject; its next pilot is pre-registered when a mechanism is named.
- **The question for Batt (his call, like R1's pooling in Amendment M):** at a residual of ~1-2 %
  a single 25-min run fails W1 about half the time on noise, and every adoption needs it. Options:
  (a) keep W1 <= 1.5 % per run; (b) W1 pooled over the pilot and its 3 preceding base runs, <= 1.5
  % (p39-p41 now: 12 / 784 = 1.53 %); (c) W1 pooled <= 2.0 %. Until he answers, (a) stands.

### 4AY. Amendment O (2026-11-09 ~17:5x ICT): Batt's answers to the 17:26 report

Batt's answers (quoted, then in English):
1. W1 (4AX): "(c) ... ทำตามนี้เลย" -- **W1 is judged POOLED over the pilot and its 3 preceding base runs
   (the set Amendment M uses for R1), <= 2.0 %.** From now on; earlier verdicts stand as made.
   - **p42 by (c): p42 + p41 + p40 + p36 = (5 + 4 + 3 + 4) / (302 + 255 + 288 + 327) = 16 / 1,172 =
     1.37 % -> PASS; every other bar of 4AW passed -> `--quiet-scan` JOINS THE BASE.**
   - A correction: the 17:26 report's option (b) figure (1.57 %) pooled p39-p42; p39 was not a
     base run. With the R1 set the pool is 1.37 % (it would have passed (b) too).
2. The boss guard on lone Garm Babies: "หนี หมา ก็โจมตีแรง ถ้าเดินหนีไปทางอื่นได้ก็เดิน" -- keep
   fleeing (the Garm Baby hits hard too), but WALK away in another direction when that is possible,
   instead of a Fly Wing. A walk-away change is to be pre-registered (the Stormy Knight itself keeps
   the immediate Fly Wing).
3. The recognizer's held-out data: "ทดสอบได้เลย" -- score stormy-v2 on R2-W + R2-H2 now, once
   (stormy-knight-recognizer.md 10d), and record it.
4. The /flows Python: "เพิ่มได้เลย" -- add the import line and try/finally (flows-studio.md).
5. The /flows lint chip: option (b) -- write the lab's missing safety bindings (the death dialog's
   L2 anchor, lab-rathena's L3 map flags), so the chip clears for every flow.

**THE BASE NOW:** p16's flags + `--reach-check --far-single --far-approach --explore --walk-pick
--kill-gap --loot-first --walk-pick-step --quiet-scan`.

### 4AZ. Pilot p43 pre-registration: --boss-walk (9.18) -- walk away from a summon, the Fly Wing only as the fallback; a staged encounter (written BEFORE its run, 2026-11-09 ~19:5x ICT)

- **Why (Amendment O, item 2; Batt: "flee, the dog hits hard too; if you can walk away in another
  direction, walk"):** the boss guard took 4 Fly Wings in p38 and 4 in p40 on lone Garm Babies (a
  regular spawn here as well as the Stormy Knight's summon). Packets: p38 8 Garm Baby attacks on us
  (2 damaging), p40 24 (all misses: her FLEE); our own hits on them 7 / 11. A Garm Baby walks 450 ms
  a cell (the KB) and chases 12 cells; the Rogue walks ~150 ms a cell, so a walk can break contact.
- **The one change against the base (Amendment O's):** `--boss-walk` (9.18; the record says
  `"boss_walk": [14, 8, 2.5, 2, 60.0, "9.18"]`): a guard on a SUMMON clicks ONE walk to the farthest
  pickable, one-click-reachable cell in view >= 8 cells away (offline: 14 cells found from the start
  7,21 and three other spots), then 2.5 s with no walk click and no boss line; a boss line after
  that, a 3rd walk-away within 60 s, or no cell -> today's Fly Wing. The Stormy Knight itself
  (`boss_spawn_names`: "Stormy Knight" only) always takes the Fly Wing.
- **The positive case (a staged encounter; encounters are rare: p39, p41, p42 had none):** the
  trial-only `--stage-mob 1515:2` -- the setup's LAST line spawns 2 Garm Babies at the start
  (`@monster 1515 2`, after `@killmonster2`). The base never carries it.
- **The run:** the base + `--boss-walk --stage-mob 1515:2`, label `xmas02-p43`, 25 min, the MVP dead
  by the schedule (killed 19:48:56).
- **Bars (`fight_time` B1 / B2, committed before the run; packets):**
  - **B1a (the staged encounter):** a `boss_walk` within the run's first 60 s, and it BROKE CONTACT
    (no summon act on us, hit or miss, in the 2.5-10 s after it);
  - **B1b:** of all walk-aways in the run, >= 50 % broke contact;
  - **B2:** the guard's Fly Wings on summons <= the walk-aways (walking is the answer, the wing the
    fallback);
  - the base's bars as Amendment O: **W1 pooled** (p43 + p42 + p41 + p40) <= 2.0 %, **L1** >= 50 %,
    **L3** >= 80 %, **L4** <= 5 %, **K1** <= 3.0 s, **K3** >= 70 %, **E1** >= 80 / h, **U1** <= 30 s,
    **D1** <= 35 ms, **R1 pooled** (p43 + p42 + p41 + p40) <= 6, **Q1** <= 8, **E3** (hard bars, 0
    dead-end / stuck / idle Fly Wings), **deaths** 0.
  Reported: the summons' acts on us and the damaging ones, the lowest HP, S1, items / hour.
- **Decisions:** every bar passes -> `--boss-walk` joins the base (`--stage-mob` never does). B1a
  cannot be judged (the staged dogs never reach us) -> the trial is repeated, nothing decided.

### 4BA. --garm-fly (9.19) pre-registration: a Fly Wing when a Garm Baby is SEEN (written BEFORE its model exists, 2026-11-09 ~22:5x ICT; Batt: "fly wing when see garm baby i[mmediately]", then "Go ahead with (c), including the immune spawns")

- **Why:** the boss guard flies only on a Battle Log line naming a Garm Baby, i.e. after contact
  (p43: the dogs' 29 misses wrote no line; the first named line came 1.7 s in, from our own hit).
  The detector learns a Garm Baby class (xmas02-detector.md Amendment M; training since 22:14).
- **The change:** `--garm-fly` (9.19; record `"garm_fly": [["garm_baby"], 1.5, "9.19"]`): a box of an
  ALARM class (garm_baby) in a detection <= 1.5 s old takes the boss guard's Fly Wing at once (the
  same path: BOSS_AVOID_S, no strike on it; the box thread never offers it as a target). With the
  deployed model (no such class) it is inert.
- **Only if** Amendment M's held-out score passes (M7's bars) and the model is deployed (MAP_MODELS
  xmas_dun02 -> the gb model, its four species collapsed to "monster", garm_baby kept).
- **G0 (a safe positive case first, the Rogue IMMUNE; Batt's immune-spawn OK):** a 3-min run with
  `--garm-fly --stage-mob 1515:1` while immune: a `garm_seen` and a Fly Wing within 5 s of the
  dog's appearance (packets: entity_appear job 1515). Immune, so no damage is possible.
- **The pilot (p44 or the next number):** the base + `--garm-fly`, 25 min, immunity OFF, the MVP dead
  by the schedule, NO staged mob. Bars:
  - **G1:** every lone Garm Baby that comes within 12 cells of us (packets) gets a Fly Wing before
    any act of it on us (a hit or a miss); reported as n / n, judged only if n >= 1;
  - **G2:** false alarms (`garm_seen` with no live Garm Baby within 15 cells, packets) <= 1 a run;
  - the base's bars (Amendment O: W1 pooled <= 2.0 %, L1, L3, L4, K1, K3, E1, U1, D1, R1 pooled,
    Q1, E3, deaths 0).
- **Decisions:** G0 passes and every pilot bar passes -> `--garm-fly` joins the base; G2 fails ->
  off (the model's precision on hunting frames is not good enough).

### 4BB. G0b (written AFTER G0's first run, BEFORE its second, 2026-11-10 ~06:5x ICT): G0's measure fixed for a staged spawn

- **G0 as run (06:54:28-06:58, `xmas02-g0`, the Rogue immune, the deployed xmas02-gb):** the staged
  Garm Baby appeared (packets, `gm_command` true) 4.61 s BEFORE run_start -- the setup's last
  line, before the runner watches; the runner's `garm_seen` (garm_baby, score 0.968) came 1.12 s
  and its Fly Wing 1.33 s after run_start, i.e. 5.94 s after the appearance. **By 4BA's letter
  (<= 5 s from the appearance) G0 FAILS by 0.94 s; 4.61 s of it were the setup.** 0 acts on us.
- **The flaw is the measure, not the mechanism:** with `--stage-mob` the dog always appears before
  the runner exists. **G0b: the same command once more; PASS = a `garm_seen` and a Fly Wing within
  5 s of max(the dog's first appearance, run_start)**, 0 acts of the dog on us. Nothing else
  changes; G0's own verdict stays FAIL as written.

### 4BC. Pilot p44 pre-registration: the base with the newly deployed detector xmas02-gb (written BEFORE its run, 2026-11-10 ~07:1x ICT)

- **Why:** M12 swapped the map's detector (xmas02 -> xmas02-gb: the four species' precision 0.87-0.88
  -> 0.93-0.94; garm_baby its own class, never a target). The base's eyes changed, so one run of the
  unchanged base flags under every base bar. Batt keeps `--garm-fly` off (xmas02-detector.md N).
- **The run:** the base (p16 + `--reach-check --far-single --far-approach --explore --walk-pick
  --kill-gap --loot-first --walk-pick-step --quiet-scan`), label `xmas02-p44`, 25 min, immunity
  OFF, the MVP dead by the schedule (killed 07:00:54). ➡️ As run: killed 08:21:53 (07:00:54 was G0's kill; see the p44 result in section 5).
- **Bars (Amendment O's):** W1 pooled (p44 + p42 + p41 + p40) <= 2.0 %, L1 >= 50 %, L3 >= 80 %, L4 <= 5 %,
  K1 <= 3.0 s, K3 >= 70 %, E1 >= 80 / h, U1 <= 30 s, D1 p95 <= 35 ms, R1 pooled <= 6, Q1 <= 8, E3
  (hard bars, 0 dead-end / stuck / idle Fly Wings), deaths 0. Reported: E1 against p40-p42 (136-154 /
  h), class D strikes, the guard's Fly Wings (Battle Log), any garm_baby boxes (never struck).
- **Decisions:** every bar passes -> xmas02-gb stays deployed for the base. A bar fails -> studied;
  the rollback (MAP_MODELS back to xmas02) is Batt's call.

### 4BD. Amendment P (2026-11-10, Batt's answers received before 09:40 ICT from `date`): N1 stopped, `--garm-fly` with a 2-detection confirmation, a floor-item class

Batt's answers to the 09:21 report (quoted, then in English):
1. "ทำ a ตามที่แนะนำได้เลย" -- do (a) as recommended: **N1 is NOT run now** (xmas02-detector.md
   N2). The deployed xmas02-gb already sees dogs at least half visible; G0b's dog was fully hidden
   (N1.4). Instead, `--garm-fly` is tested again with a **2-detection confirmation** (9.19b, 4BE),
   so a one-frame false box (p44's Cruiser) never takes a wing. Fully hidden dogs stay with the
   Battle Log guard.
2. "สอน เทรนแยกเลย เพื่อความมั่นใจและรวมเร็วในการเก็บของ" -- yes, teach the detector floor items,
   **trained separately** (its own round, not with N1), for confidence and for faster looting. Its
   plan is a new xmas02-detector.md amendment (proposed by a study first, accepted before any data).
3. "ใช้ตามเกณฑ์ที่เสนอ" -- N1's proposed bars stand IF N1 is ever run (N2).

### 4BE. --garm-fly 9.19b pre-registration: the Fly Wing after alarm boxes in 2 CONSECUTIVE detections (written BEFORE its runs, 2026-11-10 09:4x ICT)

- **The change:** `--garm-confirm N` (dungeon@9.19b; default 1 = 9.19 unchanged). The box watcher
  counts consecutive detections that held a garm_baby box (`alarm_streak`), and `alarm_seen` returns
  a box only when the streak reaches N. The `garm_seen` event records the streak; run_start records
  `"garm_fly": [["garm_baby"], 1.5, "9.19b", 2]`. The run uses `--garm-fly --garm-confirm 2`.
- **The offline replay (before any run, from the banked detections; the watcher's rhythm p50 1.0 s):**
  - p44: 1 detection of 1,568 with a dog box, the false one -> N=1 would fly once, N=2 never;
  - G0: dog boxes at 1.06 s and 1.17 s after run_start (two detections in a row) -> N=2 flies at
    1.17 s, 0.11 s after N=1;
  - G0b: the dog was boxed once (36.37 s), and the live wing (36.4 s) ended the view. It shows
    nothing about a second detection.
- **Tests:** `test_garm_confirm_waits_for_consecutive_alarm_detections` (p44's one-detection pattern
  never flies; a dog in consecutive detections flies on the 2nd; N=1 is 9.19; stale never flies).
  test_dungeon_hunt.py + test_click_census.py: 101 passed.
- **G1 (a safe positive case first; the Rogue IMMUNE; Batt's immune-spawn OK, 4BA):** the base +
  `--garm-fly --garm-confirm 2 --stage-mob 1515:1`, 3 min, label `xmas02-g1`.
  - **C1:** a `garm_seen` with streak >= 2, and the boss guard's Fly Wing, within 2.5 s of the FIRST
    detection that boxed the dog (detections.jsonl). Measured from that detection, not from the
    appearance (G0 / G0b's lesson: the setup and a fully hidden dog are not this change's).
  - No detection boxes the dog in the 3 min -> INCONCLUSIVE (the detector, N1.4), one re-run
    (`xmas02-g1b`) allowed; a second inconclusive -> reported, decided by Batt.
- **The pilot p45:** the base + `--garm-fly --garm-confirm 2`, 25 min, immunity OFF, the MVP dead by
  the schedule, NO staged mob. Bars:
  - **P1:** every lone Garm Baby boxed by the detector at least once before its first act on us
    gets a Fly Wing before that act (packets: acts of job 1515 on us; detections.jsonl). Reported
    as n / n, judged only if n >= 1. Dogs never boxed before acting are reported apart (the
    detector's limit, N1.4; the Battle Log guard covers them).
  - **P2:** false alarms (`garm_seen` with no live Garm Baby within 15 cells, packets) = 0.
  - The base's bars (Amendment O): W1 pooled (p45 + p44 + p42 + p41) <= 2.0 %, L1 >= 50 %, L3 >= 80
    %, L4 <= 5 %, K1 <= 3.0 s, K3 >= 70 %, E1 >= 80 / h, U1 <= 30 s, D1 p95 <= 35 ms, R1 pooled <= 6,
    Q1 <= 8, E3, deaths 0.
- **Decisions:** C1 and every p45 bar pass -> `--garm-fly --garm-confirm 2` JOINS THE BASE. P1 with
  n = 0 is NO VERDICT and does not block. P2 fails -> off (studied). C1 fails -> no pilot; studied.

### 4BF. Pilot p46 pre-registration: the base, unchanged, RECORDED as the floor items' held-out fiT1 (written BEFORE its run, 2026-11-10 10:29 ICT from `date`)

- **Why:** xmas02-detector.md O1 needs fresh recorded base pilots as the floor-item model's
  held-out (fiT1, fiT2). The run is the base as it stands since p45 (p16 + `--reach-check
  --far-single --far-approach --explore --walk-pick --kill-gap --loot-first --walk-pick-step
  --quiet-scan --garm-fly --garm-confirm 2`). Nothing in the runner changes.
- **The recorder beside it:** `record_session.py --backend rdp --label hunt-xmas02-fiT1 --seconds 1620
  --fps 1 --format png --max-bytes 6G` (as p38 / p39: R2-H1 / H2), started just before the runner. The
  name is refused by map_labels before it records (O1). The session stays unopened until the item
  model is frozen. It ships to the NAS after its run (`dataset_ship.py`), verified.
- **The run:** label `xmas02-p46`, 25 min, immunity OFF, the MVP dead by the schedule.
- **Bars:** the base's (Amendment O + 4BE): W1 pooled (p46 + p45 + p44 + p42) <= 2.0 %, L1 >= 50 %, L3
  >= 80 %, L4 <= 5 %, K1 <= 3.0 s, K3 >= 70 %, E1 >= 80 / h, U1 <= 30 s, D1 p95 <= 35 ms, R1 pooled <= 6,
  Q1 <= 8, E3, deaths 0, P2 = 0. P1 is reported. The recorder's cost is reported (D1, E1 against
  p44 / p45).
- **Decisions:** none ride on it. It is the base's confirmation run and the item data's held-out. A
  failed bar is studied, as for p41.

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

**Pilot p15 (4W; 20:01:01-20:31:47, its own time box; immunity OFF at 20:00:41, judged "Returned
to normal state."; back ON at 20:32:06, judged "You are now immune to attacks."). VERDICT: Q2,
D1, F3, E3, deaths PASS; Q1 FAILS (held median 3.89 s, total 31.7 s), E1 FAILS (32.0 / h), R1
FAILS (2 own-body class D). `--quick-drop` is NOT adopted (4W's rule: Q1 fails -> studied).**

| | p13r | p14 | **p15** | bar |
|---|---|---|---|---|
| Q1 time held on class-D strikes: median / total | 7.22 / 49.2 s | - | **3.89 / 31.7 s** | <= 3.0 and <= 25: FAIL |
| Q2 good strikes (K / A) given up | - | - | **0** (7 drops: 6 D, 1 C; 5 no arrow, 2 no hit; all re-armed) | <= 3: PASS |
| E1 kills | 22 (44.0 / h) | 16 (32.0) | **16 (32.0 / h)** | >= 40: FAIL |
| R1 own-body class D | 0 | 2 | **2** (5 own-body strikes) | <= 1: FAIL |
| D1 / F3 / E3 / deaths | pass | pass | **20.6 ms / 0 / pass, 0 Fly Wings, 5 stalls / 0** (lowest HP 94.3 %) | PASS |
| supply (/ 10 min); kills per seen | 36 (12.0); 0.611 | 44 (14.7); 0.364 | **39 (13.0); 0.41** | reported |
| box engagements whose box path found NO box | 6 of 19 | 9 of 20 | **12 of 22** | reported |

- **What the drops did:** the held time on misses fell by a third (49 -> 32 s), but the
  "no hits" rule still ended 22 locks (strikes that ended on a damage line carry no arrow time,
  so the quick rule does not see them).
- **Batt's four clips (20:17:35, 20:17:52, 20:18:10, 20:19:32), matched to this run's log:**
  - 20:17:35: a Cruiser passed at 113 px from her feet (one detection a second while she walked),
    just outside the patrol trigger's 110 px (~3 cells): no engagement.
  - 20:17:52: a monster stood ~150 px away (4-5 cells) the whole time: outside the trigger; the
    ring scan after the previous fight found nothing; she walked on.
  - 20:18:10 and 20:19:32 (a Myst Case beside her): she DID engage (boxes at 75 and 50 px), but
    the box path first lets the current walk end (1.2 s): she walked ~3 cells on, and its fresh
    detection put the monster at 230-250 px, beyond BOX_TARGET_PX (220): "no box", a ring scan,
    and she walked on.
  - So the detector saw them; the limits are the 3-cell trigger, the 6-cell box-path cap, the walk
    finishing first and one detection a second. Across runs the "no box" share grew: p12 7 / 26,
    p13 7 / 20, p13r 6 / 19, p14 9 / 20, p15 12 / 22.
- **Items (snatched):** Scell 6, Zargon 2, Candy 1, Well-baked Cookie 1, Manacles 1.
- The bag cleared after it (20:34:04-20:35:33: Etc 3, Use 4; weight 585 -> 520, 10 / 10).

**Pilot p16 (4X; 20:50:48-21:21:35, its own time box; immunity OFF at 20:50:33, judged "Returned
to normal state."; back ON at 21:21:46, judged "You are now immune to attacks."). VERDICT: S1, S2,
E1, D1, F3, E3, deaths PASS; R1 FAILS (2 own-body class D, as in p14 and p15). Kills 87.9 / h, the
best by far.**

| | p12 | p13r | p15 | **p16** | bar |
|---|---|---|---|---|---|
| S1 box engagements with no box found | 7 of 26 | 6 of 19 | 12 of 22 | **10 of 116 (8.6 %)** | <= 15 %: PASS |
| S2 kills per monster seen | 0.58 | 0.611 | 0.41 | **0.80** | >= 0.65: PASS |
| E1 kills | 29 (58.0 / h) | 22 (44.0 / h) | 16 (32.0 / h) | **44 (87.9 / h)** | >= 40 / h: PASS |
| monsters seen (/ 10 min) | 50 (16.7) | 36 (12.0) | 39 (13.0) | **55 (18.3)** | reported |
| strikes; class D | 46; 28 % | 36; 19 % | 28; 25 % | **134; 51 %** (far D 57 of 106) | reported |
| box path's target distance p50 / max | - | - | - | **251 / 491 px** (~7 / ~14 cells) | reported |
| R1 own-body class D | 0 | 0 | 2 | **2** (11 own-body strikes) | <= 1: **FAIL** |
| D1 / F3 / E3 / deaths | | | | **20.6 ms / 0 / pass (NPC contacts 0), 0 Fly Wings, 1 stall / 0** (lowest HP 78.0 %) | PASS |

- **What changed:** 116 box engagements (p13r 19), every fight started by a box; the box path
  struck 105 of them. Half the strikes miss (far ones), but each miss now costs little next to the
  monsters she reaches: kills doubled at the same 30 minutes.
- **Items (snatched):** Scell 8, Zargon 8, Well-baked Cookie 3, Piece of Cake 3, Pearl 2, Candy 1,
  Candy Cane 1, Manacles 1 (27; 54 / h).
- **Decision (as pre-registered):** "S1 + S2 + E1 pass and no regression bar fails" -> stays ON;
  R1 (a regression bar) failed with 2, so keeping `--engage-screen` ON is **Batt's call**
  (recommended: kills x 2; R1 has read 2 in p14, p15 and p16 alike, with 5-11 own-body strikes).
- The bag cleared after it (21:22:16-21:24:03: Etc 4, Use 6; weight 654 -> 520, 10 / 10).

**Pilot p17 (4Y; 22:11:57-22:42:44; immunity OFF at 22:11:34 and ON at 22:42:56, both judged;
the base + `--quick-drop`). VERDICT: E1, Q2, D1, F3, E3, deaths PASS; Q1 FAILS, R1 FAILS (8).
`--quick-drop` stays OFF (4Y's rule).**

| | p16 (base) | **p17 (+ quick-drop)** | bar |
|---|---|---|---|
| Q1 time held on class-D strikes: total / median | 494.8 / 7.25 s | **394.4 / 5.43 s** | <= 250 and <= 4.0: FAIL |
| Q2 good strikes given up | - | **5** (74 drops: 56 no arrow, 18 no hit; 69 re-armed) | <= 5: PASS |
| E1 kills | 44 (87.9 / h) | **44 (88.0 / h)** | >= 80 / h: PASS |
| R1 own-body class D | 2 (of 11) | **8 (of 13)** | <= 1: FAIL |
| kills per monster seen; supply | 0.80; 55 | **0.759; 58 (19.3 / 10 min)** | reported |
| D1 / F3 / E3 / deaths | | **20.5 ms / 0 / pass (NPC 0), 0 dead-end Fly Wings, 3 stalls / 0** | PASS |

- One Fly Wing was the strategy's swarm ESCAPE (HP falling 422 / s at 44 %; lowest HP 39.9 %, 1
  potion), not a dead end. No boss_guard event (no boss or summon met).
- Items (snatched): Zargon 13, Well-baked Cookie 5, Scell 4, Red Herb 2, Piece of Cake 2,
  Manacles 2, Candy 1, Iron 1.
- The bag cleared after it (22:45:16-22:47:02; weight 613 -> 520, 10 / 10).

**Pilot p18 (4Z; 22:52:36-23:16:54): INVALID -- killed by the MVP Stormy Knight at 24 min
(Amendment K).** Not scored for adoption; its evidence is on the NAS (p18-pilot).

**Pilots p19 (4AA; 23:22:42-23:48:4x, 25 min) and p20 (4AB; 23:55:4x-00:17:04, 21 min, the stage-2
recorder beside it): `--far-single` replicated. VERDICT: F1 FAILS in both (50 %, 51 %); E1, D1, R1,
F3, E3, deaths PASS in both. By 4Z's rule `--far-single` alone stays OFF; it returns inside p21's
combined change (4AC).**

| | p16 (base) | **p19** | **p20 (+ recorder)** | bar |
|---|---|---|---|---|
| F1 far class-D share | 54 % (57 / 106) | **50 % (36 / 72)** | **51 % (26 / 51)** | <= 35 %: FAIL |
| class D at 2-6 / 7-8 / 9+ cells | 5 / 41, 19 / 30, 33 / 35 | **4 / 24, 6 / 20, 26 / 28** | **6 / 18, 2 / 14, 18 / 19** | reported |
| E1 kills | 44 (87.9 / h) | **51 (122.4 / h)** | **30 (85.7 / h)** | >= 80 / h: PASS |
| kills per monster seen; supply (/ 10 min) | 0.80; 18.3 | **0.911; 22.4** | **0.938; 15.2** | reported |
| R1 own-body class D | 2 | **0** (4 own-body strikes) | **0** (1) | <= 1: PASS |
| D1 p50; GPU share | 20.6 ms | **20.6 ms; 99.7 %** (5 CPU calls at the server switch, below) | **20.5 ms (p95 22.1); 100 %** | PASS |
| F3 / E3 / deaths | | **0 / pass (NPC 0), 1 Fly Wing (`pos_unread`, not a dead end), 1 stall / 0** | **0 / pass, 0 Fly Wings, 4 stalls / 0** | PASS |

- **The 7-8 cell strikes are fixed** (63 % -> 30 % / 14 % class D), the 9+ cell ones are not (93 %,
  95 %): too far for one click. Hence `--far-approach` (4AC).
- **Process slips (no effect on the bot's flags):** p19's own detect-server step was REFUSED (the
  worker still served p18's 2400-s step); p19 ran its first 10 min on that server (the same flags
  and floor) and its own from 23:32:32 (5 CPU calls between). Editing the runner script while it ran
  killed p19's wrapper after the run (bash reads a script as it goes). p20's runner then refused
  on a buffered start line; its server (23:52:46, f32, floor 2450) served and p20 was started by
  hand on it, its time box cut to 21 min to end before the MVP's window (00:21).
- **Items:** p19 Zargon 9, Piece of Cake 4, Scell 4, Candy 2, Well-baked Cookie 2, Red Herb 1, Candy
  Cane 1, Pearl 1, Iron 1, Sandals 1; p20 Zargon 5, Scell 4, Piece of Cake 3, Red Herb 2, Pearl 2,
  Iron 2, Well-baked Cookie 1, Manacles 1.
- **The stage-2 recording (p20):** 1,200 frames, 1.9 GB (PNG + HEVC), stop "duration"; its check
  (gpu-recording.md 9.1) runs later in the night (CPU-heavy, never beside a pilot).

**(b) the walk stop: the mechanics, measured live (22:43-22:45, immunity ON on the clear stand;
`walkstop_test.py`, its result on the NAS with p17's evidence).** A 6-cell walk click, then 0.4 s
later a second click on her own cell, or 1 / 2 / 3 / 4 cells ahead of the frame's position: in
EVERY trial the second click's walk request was sent only at 1.22-1.43 s -- when the 6-cell walk
had ended -- or not at all (one cell ahead). This client does not let a click interrupt a walk.
So "stop at once" cannot be done by a click; the box path already waits for the walk's end and a
still scene (p16: settle p50 0.51 s + still p50 0.50 s an engagement). The lever left is the leg
length (`WALK_AHEAD` 7; p16's legs median 6 cells): queued as a later pilot.

**Pilot p21 (4AC; 00:32:54-00:58:40, 25 min; the MVP killed 00:32:08; immunity ON at 00:58:52,
judged "You are now immune to attacks."; the base + `--far-single --far-approach`). VERDICT: F1
FAILS (36.4 %, bar <= 35 %); E1, R1, D1, F3, E3, deaths PASS. By 4AC's rule both flags are OFF
(studied below).**

| | p16 (base) | p19 / p20 (`--far-single`) | **p21 (+ `--far-approach`)** | bar |
|---|---|---|---|---|
| F1 far class-D share | 54 % (57 / 106) | 50 % / 51 % | **36.4 % (24 / 66)** | <= 35 %: FAIL |
| class D at 2-6 / 7-8 / 9+ cells | 5 / 41, 19 / 30, 33 / 35 | 4 / 24, 6 / 20, 26 / 28; 6 / 18, 2 / 14, 18 / 19 | **15 / 45, 7 / 18, 2 / 3** | reported |
| time held on class-D strikes: total / median | 494.8 / 7.25 s | | **170.9 / 6.49 s** (26 strikes) | reported |
| E1 kills | 44 (87.9 / h) | 122.4 / 85.7 per h | **45 (108.0 / h)** | >= 80 / h: PASS |
| kills per monster seen; supply (/ 10 min) | 0.80; 18.3 | 0.911; 22.4 / 0.938; 15.2 | **0.804; 22.4** (56 seen) | reported |
| R1 own-body class D | 2 | 0 / 0 | **0** (3 own-body strikes) | <= 1: PASS |
| D1 p50 / p95; GPU share | 20.6 ms | 20.6 / 20.5 ms | **20.6 / 21.9 ms; 100 %** (1,568 calls) | PASS |
| F3 / E3 / deaths | | | **0 / pass (NPC 0), 1 Fly Wing (`pos_unread`, not a dead end), 0 stalls / 0** | PASS |

- **The approaches (31):** 25 sent a walk request (packets, -0.5..+0.2 s of the event; the other 6
  had none in that window). The box path's next look came 1.9-4.6 s later; its target was then 3-6
  cells away 17 times, 8-12 cells 11 times, none 3 times. The 9+ cell strikes fell from 35 (p16) /
  28 / 19 to **3**, and the time held on class-D strikes fell 65 % against p16's (494.8 -> 170.9 s);
  but class D at 2-6 cells rose to 15 of 45 (p19 4 / 24, p20 6 / 18); at 2-8 cells, 7 of 19 within
  6 s after an approach and 15 of 44 otherwise (both near p16's rate).
- **What a class-D strike is (packets, all 26):** every one had a SWORD verdict on its hover (the
  box path's own check), and one click (two had 4, at 0 cells). 24 of 26 sent a walk request and
  NO attack request; 12 walked to the monster's cell (+-1), 10 elsewhere (1-3 cells off the click
  cell), 2 sent nothing. 21 ended at the lock's bound, 5 on an arrow. By species (the monster
  nearest the clicked cell): Christmas Cookie 4 of 9, Cruiser 9 of 22, Myst Case 8 of 34 (Myst Cases
  stand; the others walk). So the click was taken as a walk toward the monster, and the attack never
  followed -- more often on walking monsters.
- **Items (snatched):** Zargon 11, Scell 4, Candy 3, Piece of Cake 3, Red Herb 1, Well-baked Cookie
  1, Level 3 Heal 1.
- **The run procedure:** p21's runner (run_pilot v3) passed its own checks (server listening 00:32:53,
  f32, floor 2450); its server step ended by its time box (rc 124, by design) at 01:00:23.

**Pilot p22 (4AD; 01:03:35-01:26:27, 22 min; immunity OFF at 01:02:02 and ON by 01:26:48, both
judged on the Chat tab: "Returned to normal state." / "You are now immune to attacks."; the base +
`--box-every 0.25`). VERDICT: S2' FAILS (0.531), E1 FAILS (70.7 / h); D1, R1, E3, deaths PASS.
`--box-every 0.25` stays OFF (4AD's rule).**

| | p16 (base) | p21 | **p22 (+ box-every 0.25)** | bar |
|---|---|---|---|---|
| S2' kills per monster seen; supply (/ 10 min) | 0.80; 18.3 | 0.804; 22.4 | **0.531; 22.2** (49 seen) | >= 0.85: FAIL |
| E1 kills | 44 (87.9 / h) | 45 (108.0 / h) | **26 (70.7 / h)** | >= 80 / h: FAIL |
| D1 GPU call p50 / p95; calls | 20.6 ms | 20.6 / 21.9; 1,568 | **20.5 / 21.8 ms; 5,316** (4.0 a second) | p95 <= 35: PASS |
| R1 own-body class D | 2 | 0 | **0** (6 own-body strikes) | <= 1: PASS |
| E3 / deaths | | | **pass (NPC 0), 0 Fly Wings, 0 stalls / 0** | PASS |
| strikes; classes | | 74; D 26 | **89; D 42, K 22, A 11, C 14** | reported |
| class D at 2-6 / 7-8 / 9+ cells; F1 share | 5 / 41, 19 / 30, 33 / 35; 54 % | 15 / 45, 7 / 18, 2 / 3; 36.4 % | **7 / 21, 9 / 21, 20 / 21; 57.1 %** | reported |
| time held on class D: total / median | 494.8 / 7.25 s | 170.9 / 6.49 s | **290.1 / 7.24 s** | reported |
| stuck time (walk_refusals.py) | 133.9 s | 132.9 s | **133.1 s** (17 class-D strikes began ignored) | reported |

- The box path's timings did not move (boxes after the grab p50 44 ms, the verdict p50 278.5 ms;
  67 box targets, 62 struck): a look 4 times a second found MORE targets (89 strikes), and the
  extra ones were far (9+ cells: 21 strikes, 20 class D) -- the same unreachable targets the walk-
  refusal study below names. Faster detection does not help while the bot cannot tell a monster it
  can reach from one behind a wall.
- **Items (snatched):** Zargon 5, Scell 3, Piece of Cake 2, Red Herb 1, Candy 1, Well-baked Cookie
  1, Manacles 1.

**The walk refusals (study, 2026-11-09, between p22's start 01:03:35 and the scorer's commit
01:15; packets of p13r-p21; `walk_refusals.py`,
656609c2).** p21's class-D strikes were taken apart first: 24 of 26 sent a walk request and NO
attack request (each had a SWORD verdict on its hover). The first 9 came from ONE cell, (8, 65):
from 12 s to 108 s into the run the bot sent ~40 walk requests to monsters 4-10 cells east and the
server answered none (no self_move); a request south at 110.8 s was answered at once.
- **The server's rule, found and measured** (2,933 requests made standing, p13r-p21): a walk is
  answered when a path exists within 32 steps (`poring_dataset.walk.walk_path`), it is at most 17
  steps (`max_walk_path: 17`, the running server's conf/battle/client.conf:42) and at most 14
  unless the straight (Bresenham) line is clear. Predicted against the packets: answered 2,607 /
  2,607 called accepted; ignored 325 / 326 called refused (no path 141, longer than 17: 132, a
  blocked line and longer than 14: 52). Not hit stun (1 of 181 "ignored with a path" requests came
  within 0.6 s of a hit before the 14-step rule was applied).
- **What it cost, by pilot** (stuck spans = runs of >= 3 ignored requests; class-D box strikes
  whose first request was ignored):

| | p13r | p16 | p17 | p19 | p20 | p21 |
|---|---|---|---|---|---|---|
| stuck time (s) | 0 | 133.9 | 122.4 | 110.3 | 152.8 | 132.9 |
| ignored requests / all | 1 / 1,020 | 68 / 500 | 72 / 571 | 58 / 446 | 67 / 474 | 58 / 429 |
| class D with an ignored first request | 0 | 14 | 21 | 15 | 13 | 12 |

- **Why it began with p16:** `--engage-screen` takes any box on the screen; monsters behind a wall
  are on the screen. p13r (the 3-cell trigger) never met one. The 9+ cell "far misses" of p16-p20
  were in good part the same thing (a far monster is more often behind a wall).
- **The fix (dungeon@9.12, 8dd42962): `--reach-check`**, pre-registered as p23 (4AE). Replayed on
  p16-p21's box strikes (our packet cell + the strike's rel): it passes over 90 of 205 class-D
  strikes and 2 of 192 good ones.

**Pilot p23 (4AE; 01:44:01-02:09:46, 25 min; the MVP killed 01:43:01 -- "All monsters killed!",
then "1[dead] Stormy Knight"; immunity OFF at 01:43:40 and ON at 02:09:58, both judged on the Chat
tab; the base + `--reach-check`, f0d6c75b). VERDICT: U1, U2, E1, D1, E3, deaths PASS; R1 FAILS
(2). By 4AE's rule `--reach-check` stays OFF; it returns with the own-sprite fix (p25).**

| | p16 (base) | p21 / p22 | **p23 (+ reach-check)** | bar |
|---|---|---|---|---|
| U1 stuck time | 133.9 s | 132.9 / 133.1 s | **0 s** (5 of 533 requests ignored, none in a row of 3) | <= 30 s: PASS |
| U2 class-D box strikes begun ignored | 14 | 12 / 17 | **2** | <= 3: PASS |
| E1 kills | 44 (87.9 / h) | 108.0 / 70.7 per h | **36 (86.4 / h)** | >= 80 / h: PASS |
| R1 own-body class D | 2 | 0 / 0 | **2** (7 own-body strikes) | <= 1: FAIL |
| D1 GPU call p50 / p95 | 20.6 ms | | **20.5 / 21.9 ms; 100 %** (1,532 calls) | PASS |
| E3 / deaths | | | **pass (NPC 0), 0 Fly Wings, 6 stalls (14.4 / h) / 0; lowest HP 58.7 %** | PASS |
| reach_skip events (rate-limited, one per cell per 30 s) | | | **34** | reported |
| class D at 0-1 / 2-6 / 7-8 / 9+ cells; F1 share | | p21 2 / 8, 15 / 45, 7 / 18, 2 / 3 | **7 / 21, 3 / 26, 7 / 17, 12 / 14; 38.6 %** | reported |
| time held on class D: total / median | 494.8 / 7.25 s | 170.9 / 290.1 s | **208.8 / 7.23 s** (29) | reported |
| kills per monster seen; supply (/ 10 min) | 0.80; 18.3 | 0.804 / 0.531 | **0.766; 18.8** (47) | reported |
| after the kill p50 (`fight_time.py`); no-kill fights | 6.50 s | 6.46 / 6.47 s | **6.51 s; 38 fights, 416.5 s** | reported |

- **R1's two:** all 7 own-body strikes came from the DEFEND SCAN's points on her own sprite (cells
  (0, +-1), v 297-360; 5 K, 2 D at (0, 1) v 312.1); none from the box path. p23 had 21 scan strikes
  (box 57): with the far monsters behind walls passed over, more monsters walked up to her. The
  own-sprite fix that removes exactly those scan points is `--skip-own-cells` (dungeon@9.9, fa67f3e0;
  Batt's approved item (c)).
- **What is left of the far misses:** 9+ cells 12 of 14 class D (the server answered their walk
  requests: only 2 class D began ignored) -- the far mechanism (`--far-single --far-approach`) is the
  fix for those (a later pilot).
- **Items (snatched):** Scell 6, Well-baked Cookie 3, Candy 2, Pearl 2, Zargon 2, Red Herb 1,
  Piece of Cake 1, Iron 1, Manacles 1.

**Pilot p24 (4AF; 02:11:45-02:37:32, 25 min; immunity OFF at 02:11:23 and ON at 02:37:46, both
judged on the Chat tab; the base + `--kill-gap`, 9.13 = 1f8dc88e's rule, 2 hits). VERDICT: K1, D1,
R1, E3, deaths PASS; E1 FAILS (74.3 / h), K3 FAILS (62.2 %). `--kill-gap` stays OFF (4AF's rule).**

| | p16 (base) | p21 / p23 | **p24 (+ kill-gap)** | bar |
|---|---|---|---|---|
| K1 after the kill p50 (`fight_time.py`) | 6.50 s | 6.46 / 6.51 s | **1.96 s** (26 kill fights, 101.1 s in all) | <= 3.0 s: PASS |
| E1 kills | 44 (87.9 / h) | 108.0 / 86.4 per h | **31 (74.3 / h)** | >= 80 / h: FAIL |
| K3 inferred kills within 3 s after a death of ours | - | - | **28 of 45 (62.2 %)** | >= 70 %: FAIL |
| fights; no-kill fights (time) | 116; 79 (814.4 s) | 92; 50 (434.1 s) / 67; 38 (416.5 s) | **183; 157 (784.1 s)** | reported |
| R1 own-body class D | 2 | 0 / 2 | **1** (7 own-body strikes) | <= 1: PASS |
| D1 GPU call p50 / p95 | 20.6 ms | | **20.6 / 21.9 ms; 100 %** | PASS |
| E3 / deaths / lowest HP | | | **pass (NPC 0); 1 Fly Wing = the boss guard's escape (Garm Baby, 24.9 min), not a dead end; 1 stall / 0 / 53.9 %** | PASS |
| stuck time (walk_refusals.py); class D begun ignored | 133.9 s; 14 | 132.9 s / 0 s | **121.3 s; 12** (no `--reach-check`) | reported |
| kills per monster seen; supply (/ 10 min) | 0.80; 18.3 | 0.804 / 0.766 | **0.585; 21.2** (53) | reported |

- **What the rule did:** after a real kill the fight ended 1.96 s after the death (6.5 s before):
  the kill-gap unlock, then the quiet-kill end with no scan. Two side effects cost more than it
  saved:
  1. **False kills (17 of 45):** 10 were short contacts -- 2-4 of our hits, then the target walked
     off ALIVE (our acts stopped 2.2-2.7 s before the inference); 3 were reader gaps while we still
     hit; 2 had no hit of ours in 3 s; 2 others. Real inferred kills took 3-22 hits (median 15).
  2. **Spurious box misses:** the quiet-kill rule (end any fight within 3 s after a kill: pilot 4's,
     for the loot step) also closed a NEW box fight engaged in those 3 s, before the box path
     looked -- and booked it as a box miss. At 02:17 14 of the first 15 box misses were such, and
     10 spots went ignored; 183 fights in all.
- **Fixed for a re-test (not run yet):** 9.13b (7ed2d7d8): a quiet-kill end before the box path
  looked is no box miss; 9.13c (9436a75b): 5 of our hits before the gap (on p24: 27 of 28 real
  kills kept, 3 of 17 false ones; share 0.90).
- **Items (snatched):** Scell 14, Zargon 4, Manacles 3, Red Herb 2, Pearl 2, Iron 2, Piece of
  Cake 1, Pinafore 1.

**Pilot p25 (4AG; 02:54:57-03:20:48, 25 min; the MVP killed 02:53:58, "1[dead] Stormy Knight";
immunity OFF at 02:54:36 and ON at 03:21:02, both judged on the Chat tab; the base +
`--reach-check`, replicated). VERDICT: U1 FAILS (43.3 s), U2 FAILS (5); E1, R1, D1, E3, deaths
PASS. `--reach-check` stays OFF (4AG's rule).**

| | p16 (base) | p23 (reach-check) | **p25 (reach-check, again)** | bar |
|---|---|---|---|---|
| U1 stuck time | 133.9 s | 0 s | **43.3 s** (3 spans: 4.1, 10.3, 28.9 s; 25 of 457 requests ignored) | <= 30 s: FAIL |
| U2 class-D box strikes begun ignored | 14 | 2 | **5** | <= 3: FAIL |
| E1 kills | 44 (87.9 / h) | 36 (86.4 / h) | **41 (98.2 / h)** | >= 80 / h: PASS |
| R1 own-body class D | 2 | 2 | **0** (6 own-body strikes); pooled p23 + p25: 2 of 13 | <= 1: PASS |
| D1 / E3 / deaths / lowest HP | | | **20.6 / 21.9 ms; pass (NPC 0), 0 Fly Wings, 1 stall; 0; 95.0 %** | PASS |
| reach_skip events | | 34 | **50** | reported |
| class D at 0-1 / 2-6 / 7-8 / 9+ cells; F1 share | | 7 / 21, 3 / 26, 7 / 17, 12 / 14; 38.6 % | **3 / 21, 6 / 28, 14 / 30, 21 / 23; 50.6 %** | reported |
| time held on class D | 494.8 s | 208.8 s | **307.0 s** (44) | reported |
| kills per monster seen; supply | 0.80; 18.3 | 0.766; 18.8 | **0.745; 22.0** (55) | reported |
| after the kill p50; no-kill fights | 6.50 s | 6.51 s; 38 (416.5 s) | **6.55 s; 55 (575.6 s)** | reported |

- The stuck time fell (133.9 -> 43.3 s) but not to the bar; why the 28.9 s span passed the check is
  studied below (after p26).
- **Items (snatched):** Zargon 6, Scell 5, Piece of Cake 3, Red Herb 1, Candy 1, Well-baked Cookie
  1, Pearl 1.

**Pilot p26 (4AH; 03:22:36-03:48:21, 25 min; immunity OFF at 03:21:50 and ON at 03:48:34, both
judged on the Chat tab; the base + `--kill-gap` 9.13c, `"kill_gap": [1.5, 5, "9.13c"]`). VERDICT:
K1, K3, R1, D1, E3, deaths PASS; E1 FAILS (74.4 / h). `--kill-gap` stays OFF (4AH's rule).**

| | p16 (base) | p24 (9.13) | **p26 (9.13c)** | bar |
|---|---|---|---|---|
| K1 after the kill p50 | 6.50 s | 1.96 s | **2.06 s** (26 kill fights, 110.0 s) | <= 3.0 s: PASS |
| E1 kills | 44 (87.9 / h) | 31 (74.3 / h) | **31 (74.4 / h)** | >= 80 / h: FAIL |
| K3 inferred kills within 3 s after a death of ours | - | 62.2 % | **71.0 %** (22 of 31) | >= 70 %: PASS |
| box misses after a quiet-kill end (9.13b) | - | 14 of the first 15 | **0** (6 box misses in all, 0 spots ignored) | reported |
| fights; no-kill fights (time) | 116; 79 (814.4 s) | 183; 157 (784.1 s) | **579; 553 (752.3 s)** | reported |
| R1 own-body class D / D1 / E3 / deaths | 2 | 1 | **1 (10 own-body strikes) / 20.6 / 21.7 ms / pass, 0 Fly Wings, 0 stalls / 0; lowest HP 87.9 %** | PASS |
| stuck time; class D begun ignored (no `--reach-check`) | 133.9 s; 14 | 121.3 s; 12 | **208.7 s; 21** | reported |
| kills per monster seen; supply (/ 10 min) | 0.80; 18.3 | 0.585; 21.2 | **0.674; 18.4** (46) | reported |
| class D at 9+ cells; F1 share | 33 / 35; 54 % | 25 / 28; 51.8 % | **38 / 40; 70.8 %** | reported |

- **What 9.13b exposed:** with the box miss gone, the quiet-kill rule (pilot 4's: end any fight
  within 3 s after a kill, so the loot step runs) closed a NEW box fight on every tick of those 3 s
  and the trigger opened it again -- 579 "fights", most 0 s long. So after each kill the bot still
  waits ~3 s before it may engage the next monster, then loots: the 4.4 s the rule saves after a
  death goes into that block. The kill rule itself works (K1, K3); the next step, not run tonight,
  is to let a box engagement inside those 3 s take the next target (and loot after).
- This run's stuck time (208.7 s, no `--reach-check`) is the largest of the night: E1 here is not
  `--kill-gap`'s alone.
- **Items (snatched):** Zargon 10, Piece of Cake 5, Red Herb 3, Scell 2, Manacles 2, Candy Cane 1,
  Well-baked Cookie 1, Pearl 1.

**Pilot p27 attempt 1 (04:05:44-04:05:53): REFUSED by the runner's own setup** -- "weight [1202,
2430] at or over 0.48 for the rogue: the setup never drops its Etc tab (a person first)". Nothing
was typed or clicked by the run. The MVP had been killed at 04:05:01 ("1[dead] Stormy Knight");
immunity was OFF from 04:05:24 to 04:16:17 with her standing at 7,21 (HP 5070 / 5070 at 04:16,
full: no harm). The bag was cleared (`clear-bag`, Batt's standing rule: worn gear, 10 potions,
10 Fly Wings; 04:16:40-04:18:52; weight 1202 -> 520; etc 6, use 8, eqp 1 dropped). The bag had last
been cleared after p17 (520 at 22:47): ~76 weight a run over p18-p26. The detect server of attempt
1 served idle until its time box (04:33:10); attempt 2 starts after it, 25 min, ending before the
MVP's window (05:05).

**Pilot p27 attempt 2 (4AI; 04:33:52-04:59:44, 25 min; immunity OFF at 04:33:29 and ON at
04:59:56, both judged on the Chat tab; the base + `--reach-check` 9.12b, `"reach_check": [17, 14,
"9.12b"]`). VERDICT: U1, U2, E1, D1, R1, E3, deaths ALL PASS. `--reach-check` (9.12b) JOINS THE
BASE (4AI's rule).**

| | p16 (base) | p23 (9.12) | p25 (9.12) | **p27 (9.12b)** | bar |
|---|---|---|---|---|---|
| U1 stuck time | 133.9 s | 0 s | 43.3 s | **1.3 s** (4 of 436 requests ignored; one span of 3) | <= 30 s: PASS |
| U2 class-D box strikes begun ignored | 14 | 2 | 5 | **0** | <= 3: PASS |
| E1 kills | 44 (87.9 / h) | 36 (86.4 / h) | 41 (98.2 / h) | **44 (105.4 / h)** | >= 80 / h: PASS |
| R1 own-body class D | 2 | 2 | 0 | **1** (12 own-body strikes) | <= 1: PASS |
| D1 GPU call p50 / p95 | 20.6 ms | 20.5 / 21.9 | 20.6 / 21.9 | **20.7 / 22.1 ms; 100 %** | PASS |
| E3 | | | | **pass (NPC 0); 4 Fly Wings = 3 boss-guard escapes (Garm Baby) + 1 `pos_unread` escape, no dead end; 1 stall** | PASS |
| deaths; lowest HP | | | | **0; 68.5 %** | PASS |
| reach_skip events | | 34 | 50 | **42** | reported |
| class D at 0-1 / 2-6 / 7-8 / 9+; F1 share | | 7/21, 3/26, 7/17, 12/14; 38.6 % | 3/21, 6/28, 14/30, 21/23; 50.6 % | **6/24, 5/34, 8/23, 13/16; 35.6 %** | reported |
| time held on class D | 494.8 s | 208.8 s | 307.0 s | **237.8 s** (32) | reported |
| kills per monster seen; supply (/ 10 min) | 0.80; 18.3 | 0.766; 18.8 | 0.745; 22.0 | **0.657; 26.8** (67) | reported |
| after the kill p50; no-kill fights | 6.50 s | 6.51 s | 6.55 s | **6.49 s; 49 (587.1 s)** | reported |

- **The record across the three reach-check runs is reported together:** p23 failed R1 (2), p25
  failed U1 / U2 (the raised-floor cell error 9.12b fixes), p27 passed every bar. The stuck time
  of the base (p16-p26 without the check: 110-209 s a run) is gone.
- **What is left (the next work):** the far misses on reachable targets (9+ cells 13 of 16; the
  far mechanism, draft 4AJ, is the fix to test ON this base), and the 6.5 s after each kill (the
  kill-gap rule works; the quiet-kill 3-s block must let the next box target through first).
- **Items (snatched):** Scell 6, Zargon 6, Well-baked Cookie 3, Candy 2, Piece of Cake 1, Old Blue
  Box 1, Iron 1, Manacles 1, Nursing Bottle 1.

**The night's base (2026-11-09 05:0x, by the pre-registered rules):** p16's flags (`--engage-screen`
with the boss guard; `--self-recheck --still-strike`; the box path on the GPU detector) **+
`--reach-check` (9.12b)**. Not adopted tonight, each by its own rule: `--quick-drop` (p17),
`--far-single` alone (p19 / p20), `--far-single --far-approach` (p21), `--box-every 0.25` (p22),
`--kill-gap` (p24, p26). Built, not run: `--skip-own-cells` (weighed against p23's data, section 5).

**Pilot p28 (4AJ; 06:41:48-07:07:37, 25 min; the MVP killed 06:40:59, "1[dead] Stormy Knight";
immunity OFF at 06:41:22 and ON at 07:07:52, both judged on the Chat tab; the base (p16's flags +
`--reach-check` 9.12b) + `--far-single --far-approach`). VERDICT: F1, E1, U1, D1, R1, E3, deaths
ALL PASS. `--far-single --far-approach` JOIN THE BASE (4AJ's rule). The best run of the study.**

| | p21 (far, no reach-check) | p27 (base) | **p28 (base + far)** | bar |
|---|---|---|---|---|
| F1 far class-D share | 36.4 % (24 / 66) | 35.6 % (26 / 73) | **13.0 % (7 / 54)** | <= 25 %: PASS |
| E1 kills | 45 (108.0 / h) | 44 (105.4 / h) | **52 (124.7 / h)** | >= 80 / h: PASS |
| U1 stuck time | 132.9 s | 1.3 s | **17.0 s** (one span of 5) | <= 30 s: PASS |
| D1 / R1 / E3 / deaths | | | **20.5 / 21.9 ms / 0 (6 own-body strikes) / pass, 0 Fly Wings, 3 stalls / 0; lowest HP 83.3 %** | PASS |
| class D at 0-1 / 2-6 / 7-8 / 9+ | 2/8, 15/45, 7/18, 2/3 | 6/24, 5/34, 8/23, 13/16 | **1/7, 6/42, 1/11, 0/1** | reported |
| strikes; class D | 74; 26 | 97; 32 | **61; 8** (K 52) | reported |
| time held on class D | 170.9 s | 237.8 s | **47.2 s** | reported |
| kills per monster seen; supply (/ 10 min) | 0.804; 22.4 | 0.657; 26.8 | **0.981; 21.2** (53) | reported |
| approaches; reach_skip events | 31; - | -; 42 | **16; 95** | reported |
| after the kill p50; no-kill fights | 6.46 s; 50 (434.1 s) | 6.49 s; 49 (587.1 s) | **6.56 s (299.9 s); 32 (247.2 s)** | reported |

- With the unreachable targets gone, the approach walk takes a far target into reach: 9+ cell
  strikes 1 (0 missed), 7-8 cells 1 of 11 missed.
- **The next limit is the time after each kill:** 299.9 s of the run (41 kill fights, 6.56 s each)
  -- `--kill-gap` with the quiet-kill block lifted (Amendment L 3, after the explore work).
- **Items (snatched):** Scell 12, Zargon 7, Well-baked Cookie 3, Piece of Cake 3, Candy Cane 2,
  Pearl 2, Candy 1, Manacles 1.

**The base from 2026-11-09 07:1x:** p16's flags + `--reach-check` (9.12b) + `--far-single
--far-approach`.

**Pilot p29 (4AL, explore E1 run 1; 07:09:47-07:35:34, 25 min; immunity OFF at 07:09:24 and ON
at 07:35:47, both judged on the Chat tab; the base + `--explore`). E1's bars: deaths, E3, U1, X1,
X2 ALL PASS. Reported: 66 kills = 158.4 / h, the most of the study.**

| | p27 (edge loop) | p28 (edge loop, the base) | **p29 (explore)** |
|---|---|---|---|
| kills; per hour | 44; 105.4 | 52; 124.7 | **66; 158.4** |
| monsters seen (/ 10 min); kills per monster seen | 67 (26.8); 0.657 | 53 (21.2); 0.981 | **67 (26.8); 0.985** |
| strikes; class D; F1 | 97; 32; 35.6 % | 61; 8; 13.0 % | **77; 10; 12.7 %** |
| stuck time; stalls; Fly Wings | 1.3 s; 1; 4 | 17.0 s; 3; 0 | **0 s; 1; 0** |
| fights; no-kill fights (time); after the kill p50 | 84; 49 (587.1 s); 6.49 s | 73; 32 (247.2 s); 6.56 s | **94; 49 (462.9 s); 6.52 s** |
| deaths; lowest HP | 0; 68.5 % | 0; 83.3 % | **0; 83.7 %** |

- **The exploration (X1 / X2):** 13 regions targeted, 5 reached, 7 legs timed out at 150 s (the
  far ones: fights on the way), 0 blocked; `explore_saved` merged the run (1 run, 145 regions,
  607 cells visited, 1 refused cell); no `ev_hook_error`.
- **The recorder against the packets:** 65 good fights (>= 5 of our damage lines) for 66 packet
  kills; 94 fights (the runner's own count). Its dwell came to 1,021 s of 1,500 (a gap of more than
  5 s -- a loot step, a long scan -- books 5 s only): the rates are comparable between regions,
  not absolute.
- **Why more kills:** the same kills per monster seen as p28 (0.985 vs 0.981), and more monsters
  seen (26.8 vs 21.2 / 10 min): new ground holds monsters the edge loop had already cleared.
  One run; E1 goes on (p30, p31) as pre-registered.
- No region has a minute of dwell yet (145 regions in 25 min, ~7 s each): 10-cell regions learn
  slowly; E2's pre-registration weighs that (larger regions or pooled neighbours).
- **Items (snatched):** Scell 11, Zargon 9, Piece of Cake 7, Well-baked Cookie 5, Manacles 3, Red
  Herb 2, Candy 2, Pearl 2, Iron 2, Sandals 1.

**Pilot p30 (4AL, explore E1 run 2; 07:53:45-08:19:30, 25 min; the MVP killed 07:52:57 after the
boss peek (stormy-knight-recognizer.md 1); immunity OFF at 07:53:20 and ON at 08:19:45; the base +
`--explore`; the stage-3 video-only recording ran beside its minutes 1-6). E1's bars: deaths, U1,
X1, X2 PASS; E3 hard bars pass, 0 dead-end Fly Wings by the bar's definition (why `dead_end`) --
but 1 Fly Wing by the `stuck` escape (below), reported. 67 kills = 160.8 / h: p29 replicated.**

| | p28 (edge loop) | p29 (explore) | **p30 (explore)** |
|---|---|---|---|
| kills; per hour | 52; 124.7 | 66; 158.4 | **67; 160.8** |
| monsters seen (/ 10 min); kills per monster seen | 53 (21.2); 0.981 | 67 (26.8); 0.985 | **74 (29.6); 0.905** |
| strikes; class D; F1 | 61; 8; 13.0 % | 77; 10; 12.7 % | **80; 15; 18.4 %** |
| stuck time; stalls; Fly Wings | 17.0 s; 3; 0 | 0 s; 1; 0 | **7.7 s; 7; 1 (`stuck`)** |
| after the kill p50 (total); no-kill fights (time) | 6.56 s (299.9 s); 32 (247.2 s) | 6.52 s (305.6 s); 49 (462.9 s) | **6.47 s (358.8 s); 35 (347.2 s)** |
| deaths; lowest HP | 0; 83.3 % | 0; 83.7 % | **0; 84.2 %** |

- **The exploration:** 11 regions targeted, 2 reached, 7 timed out, 1 blocked; merged: 2 runs,
  206 regions, 1,205 cells visited, 8 refused cells; no `ev_hook_error`. Its own dwell 1,040 s,
  67 good fights for 67 packet kills.
- **The `stuck` Fly Wing (studied, packets):** at (161, 116) the runner booked 4 stalls in 18 s
  (walk targets (154, 116), (154, 121), (165, 117), (161, 121)) and flew. The packets hold NO walk
  request in those 18 s: the CLIENT dropped the clicks. Of p30's 7 stalls, 6 aimed at a cell the
  client does not pick under the projected pixel (poring_dataset.picking: 4-6 cells off, 2 of them
  unwalkable) -- the raised floors again (9.12b's cause, for WALK clicks). The edge loop's
  waypoints never crossed those spots; explore does. A walk-click fix (the target cell must be the
  one the client picks) is the next walking change, pre-registered on its own.
- **Items (snatched):** Zargon 12, Scell 6, Piece of Cake 4, Manacles 3, Red Herb 2, Well-baked
  Cookie 2, Iron 2, Candy 1, Candy Cane 1, Pearl 1.

**Pilot p31 (4AL, explore E1 run 3; 08:21:44-08:47:38, 25 min; immunity OFF at 08:21:20 and ON at
08:47:53; the base + `--explore`; a 24-min PNG recording beside it, the Stormy Knight study's
hunting negatives `20261109T082234-rdp-hunt-xmas02-p31`: 1,440 frames, 3.18 GB, rc 0). E1's bars:
deaths, E3 (0 dead-end Fly Wings; 1 `pos_unread`), U1, X1, X2 ALL PASS. 61 kills = 146.1 / h.**

| | p28 (edge loop) | p29 | p30 | **p31** | E1 (p29-p31) |
|---|---|---|---|---|---|
| kills; per hour | 52; 124.7 | 66; 158.4 | 67; 160.8 | **61; 146.1** | 194; mean 155.1 |
| monsters seen / 10 min; kills per seen | 21.2; 0.981 | 26.8; 0.985 | 29.6; 0.905 | **22.7; 1.070** | |
| stuck time; stalls; Fly Wings (why) | 17.0 s; 3; 0 | 0 s; 1; 0 | 7.7 s; 7; 1 (stuck) | **9.6 s; 6; 1 (pos_unread)** | |
| D1 p95 | 21.9 ms | 22.1 | 22.2 | **24.2 ms** (the PNG recorder beside it) | |
| lowest HP; deaths | 83.3 %; 0 | 83.7 %; 0 | 84.2 %; 0 | **72.9 %; 0** | 0 |

- **The exploration:** 14 targeted, 7 reached, 6 timed out; merged: 3 runs, 239 regions, 1,805
  cells visited, 13 refused; no `ev_hook_error`. Its own count: 51 good fights for 61 packet kills.
- E1 adopts nothing (4AL). Phase E2 (4AN) is the adoption test.
- **Items (snatched):** Scell 14, Zargon 8, Manacles 4, Candy 3, Piece of Cake 3, Well-baked Cookie
  2, Red Herb 1, Pearl 1.

**Pilot p32 (4AN, E2's edge-loop run; 09:08:13-09:34:02, 25 min; immunity OFF at 09:07:47 and ON at
09:34:15; the base as is: the edge loop + `--reach-check --far-single --far-approach`; the B2 boss
watch ran 08:50-09:05 before it, its `@killmonster2`s also killing the natural MVP). 43 kills =
103.2 / h; deaths 0.**

| | p28 (edge loop) | **p32 (edge loop)** | E1 explore (p29-p31) |
|---|---|---|---|
| kills; per hour | 52; 124.7 | **43; 103.2** | 194; mean 155.1 |
| monsters seen / 10 min; kills per seen | 21.2; 0.981 | **16.8; 1.024** | 26.8 / 29.6 / 22.7 |
| strikes; class D; own-body class D | 61; 8; 0 | **61; 15; 3** | |
| stuck time; stalls; Fly Wings | 17.0 s; 3; 0 | **13.0 s; 3; 1 (`pos_unread`)** | |
| after the kill p50; no-kill fights (time) | 6.56 s; 32 (247.2 s) | **6.52 s; 17 (233.7 s)** | |
| lowest HP; deaths | 83.3 %; 0 | **85.7 %; 0** | |

- The edge loop's E2 mean so far: (124.7 + 103.2) / 2 = 113.95 / h; p33 (explore) follows.
- **Items (snatched):** Zargon 8, Red Herb 3, Candy 2, Candy Cane 2, Well-baked Cookie 2, Piece of
  Cake 2, Scell 2, Manacles 2.

**Pilot p33 (4AN, E2's explore run; 10:06:05-10:32:04, 25 min; the MVP killed 10:02:49, "1[dead]
Stormy Knight"; the bag cleared 10:03:41-10:05:53 (1,139 -> 520); immunity OFF at 10:03:12 and ON
at 10:32:25; the base + `--explore`). 64 kills = 153.6 / h. E1's safety bars on it: deaths 0, E3
(hard bars pass, 0 Fly Wings, 1 stall), U1 18.8 s, X1 (4 runs merged), X2 (no hook error) PASS.**

**E2's VERDICT (4AN): PASS -- `--explore` JOINS THE BASE.**

| | runs | kills / h | mean |
|---|---|---|---|
| explore | p29, p30, p31, p33 | 158.4, 160.8, 146.1, 153.6 | **154.7** |
| the edge loop (same base) | p28, p32 | 124.7, 103.2 | **113.95** |
| ratio | | | **1.358** (bar >= 1.15: PASS) |

- p33 in detail: monsters seen 71 (28.4 / 10 min), kills per seen 0.901; 75 strikes, class D 10
  (F1 11.3 %); stuck 18.8 s; after the kill p50 6.55 s (372.8 s); no-kill fights 30 (310.3 s);
  12 regions targeted, 5 reached, 6 timed out; 612 cells visited, 42.3 % on the east half; the
  knowledge: 4 runs, 270 regions, 2,337 cells, 14 refused. Lowest HP 78.4 %.
- **Items (snatched):** Scell 12, Zargon 11, Piece of Cake 4, Manacles 3, Well-baked Cookie 2,
  Candy 1, Pearl 1.

**The base from 2026-11-09 10:3x:** p16's flags + `--reach-check` (9.12b) + `--far-single
--far-approach` + `--explore` (9.14). The edge loop stays selectable (`--no-explore`).

**Pilot p34 (4AM; 10:34:11-10:59:57, 25 min; immunity OFF at 10:33:42 and ON at 11:00:12; the base
(+ `--explore`, E2) + `--walk-pick`). VERDICT: W1, W2 (by its letter), E1, U1, D1, E3, deaths PASS;
R1 FAILS (2). `--walk-pick` stays OFF (4AM's rule) -- and the run showed a regression of its own.**

| | p29-p33 (explore, no walk-pick) | **p34 (+ walk-pick)** | bar |
|---|---|---|---|
| W1 clicked walks the client never sent (`walk_refusals.py`, 934a0e24) | p29 1.7 %, p30 7.2 %, p33 2.8 % | **0 of 228 (0.0 %)** | <= 1.5 %: PASS |
| W2 `stuck` / `dead_end` Fly Wings | p30: 1 `stuck` | **0 / 0** -- but 1 `idle` Fly Wing caused by walk-pick (below) | PASS by its letter |
| E1 kills | 146.1-160.8 / h | **59 (141.5 / h)** | >= 80 / h: PASS |
| U1 stuck time | 0-18.8 s | **0 s** (0 of 323 requests ignored) | <= 30 s: PASS |
| R1 own-body class D | | **2** (9 own-body strikes) | <= 1: FAIL |
| D1 / E3 / deaths | | **20.6 / 22.4 ms / pass, 1 stall / 0; lowest HP 58.1 %** | PASS |

- **The `idle` Fly Wing:** at (143, 118) the explore goal (194, 144) had a 61-cell route, and for
  45 s no walk click went out at all: every candidate path cell failed the pick check (the raised
  floors east of the centre), so `walk_target` returned none and the idle guard flew. 594 candidate
  cells were skipped over the run. The fix (9.15b, a later pilot): when no candidate passes the
  pick check, fall back to today's click (the stall / carve path handles it).
- R1 note (reported): own-body class D in base runs today: p27 1, p32 3, p33 1 -- the bar fails on
  the base itself in some runs; its use as a per-run regression bar is for Batt to revisit.
- **Items (snatched):** Scell 14, Piece of Cake 4, Zargon 4, Red Herb 3, Manacles 3, Well-baked
  Cookie 1, Pearl 1, Iron 1.

**Pilot p35 (4AO; 11:09:37-11:35:29, 25 min; the MVP killed 11:08:50 after polls at 11:04 (dead)
and 11:08 (alive at 178, 235); immunity OFF at 11:09:13 and ON at 11:35:44; the base + `--explore
--explore-cover`). VERDICT: C1 FAILS (407 new cells); C2, E1, the safety bars PASS.
`--explore-cover` stays OFF (4AO's rule).**

| | E1 / E2 explore runs | p34 | **p35 (+ explore-cover)** | bar |
|---|---|---|---|---|
| C1 new cells (vs the knowledge file before the run) | p29 607, p30 598, p31 600, p33 532 | 495 | **407** (of 533 visited: 76 %) | >= 700: FAIL |
| C2 east-half share of the run's visited cells | 27.0 / 27.6 / 51.4 / 42.3 % | | **43.5 %** | 35-65 %: PASS |
| E1 kills | 146.1-160.8 / h | 141.5 / h | **66 (158.1 / h)** | >= 80 / h: PASS |
| deaths; E3; U1; X1 / X2 | | | **0; pass, 0 Fly Wings, 0 stalls; 0 s; 6 runs merged / no hook error** | PASS |

- New cells fall run by run as the map fills (607 -> 407), and p35's new share of its visited cells
  (76 %) is below p34's (495 of 607: 82 %): the coverage novelty did not find more new ground; legs
  to far low-coverage regions still time out (5 of 12 targets).
- 12 targeted, 6 reached, 5 timed out; monsters seen 71 (28.3 / 10 min), kills per seen 0.93;
  stuck 0 s (0 of 311 requests ignored); lowest HP 72.9 %. The knowledge: 6 runs, 309 regions,
  3,239 cells visited, 15 refused.
- **Items (snatched):** Scell 13, Zargon 11, Piece of Cake 5, Well-baked Cookie 4, Red Herb 2,
  Manacles 2, Candy 1, Candy Cane 1, Pearl 1.

**Pilot p36 (4AP; 11:37:32-12:03:19, 25 min; immunity OFF at 11:37:13 and ON at 12:03:32; the base
(+ `--explore`) + `--walk-pick` 9.15b). VERDICT: W1, W2, E1, U1, D1, R1, E3, deaths ALL PASS.
`--walk-pick` (9.15b) JOINS THE BASE (4AP's rule).**

| | p34 (9.15) | **p36 (9.15b)** | bar |
|---|---|---|---|
| W1 clicked walks never sent | 0 / 228 | **4 / 327 (1.22 %)** | <= 1.5 %: PASS |
| W2 `stuck` / `dead_end` / `idle` Fly Wings | 0 / 0 / 1 | **0 / 0 / 0** (no Fly Wing) | PASS |
| E1 kills | 59 (141.5 / h) | **56 (134.3 / h)** | >= 80 / h: PASS |
| U1 stuck time | 0 s | **8.8 s** | <= 30 s: PASS |
| R1 own-body class D | 2 | **1** (3 own-body strikes) | <= 1: PASS |
| D1 / E3 / deaths | | **20.5 / 21.9 ms / pass, 1 stall / 0; lowest HP 86.7 %** | PASS |
| `walk_pick_skip`; `walk_pick_fallback` | 594; - | **43; 1** | reported |

- 14 regions targeted, 9 reached, 4 timed out; the knowledge: 7 runs. Monsters seen 56 (22.4 / 10
  min), kills per seen 1.0.
- **Items (snatched):** Scell 11, Zargon 9, Piece of Cake 4, Red Herb 1, Candy 1, Well-baked Cookie
  1, Manacles 1.

**The base from 2026-11-09 12:0x:** p16's flags + `--reach-check` (9.12b) + `--far-single
--far-approach` + `--explore` (9.14) + `--walk-pick` (9.15b).

**Pilot p37 (4AQ; 12:20:00-12:45:49, 25 min; the MVP killed 12:19:14 after polls at 12:10 / 12:14
(dead) and 12:19 (alive at 119, 106); the bag cleared 12:14-12:16 (924 -> 520); immunity OFF at
12:19:38 and ON at 12:46:04; the base + `--kill-gap` 9.13c). VERDICT: L1, K1, E1, U1, D1, R1, E3,
deaths PASS; K3 FAILS (68.9 %), W1 FAILS (3.6 %). `--kill-gap` stays OFF (4AQ's rule).**

| | base runs today | p26 (9.13c, no reach-check) | **p37 (9.13c, the new base)** | bar |
|---|---|---|---|---|
| L1 floor items picked up | p28-p36: 0-2 of 18-46 (~0 %) | 10 / 16 | **12 / 23 (52.2 %)** | >= 50 %: PASS |
| K1 after the kill p50 | 6.47-6.56 s | 2.06 s | **1.99 s** (111.2 s in all) | <= 3.0 s: PASS |
| K3 inferred kills real | - | 71.0 % | **68.9 % (42 / 61)** | >= 70 %: FAIL |
| E1 kills | 134.3-160.8 / h (explore) | 74.4 / h | **63 (151.2 / h)** | >= 80 / h: PASS |
| W1 clicked walks never sent | p36 1.22 % | - | **11 / 302 (3.6 %)** | <= 1.5 %: FAIL |
| U1 / D1 / R1 / E3 / deaths | | | **15.2 s / 22.2 ms / 1 / pass, 0 Fly Wings, 3 stalls / 0; lowest HP 74.6 %** | PASS |
| L2 hovering loot steps with no death of ours in 10 s before | - | 13 / 23 | **10 / 33** | reported |
| the loot steps' time; kills per monster seen | | 70 s | **104.6 s; 1.0** | reported |

- **Batt's two clips, answered by this run:** the loot works once kills are seen from our damage
  (12 of 23 floor items, from ~0); loot scans now follow inferred kills -- but 10 of 33 still had no
  real kill behind them: the false kills (a target that took >= 5 hits and walked off). The
  11:56 clip itself was the defend scan (a hidden Cruiser), not a loot scan.
- **The next step (not run):** confirm an inferred kill from pixels -- the target's box gone from
  the box watcher at the lock's cell -- before the loot step (K3 and L2 together). W1's rise (3.6 %
  vs 1.22 % in p36) is unexplained yet.
- **Items (snatched + picked):** Scell 13, Zargon 9, Red Herb 5, Piece of Cake 5, Well-baked Cookie
  4, Candy Cane 3, Manacles 3, Candy 2.

**Pilot p38 (4AS; 13:30:50-13:56:38, 25 min; the MVP dead by the schedule -- the R2-W watch's
`@killmonster2` killed its natural spawn at 13:19:49 at the earliest, `@mobsearch` "1[dead]" at
13:26:25 and 13:30:05, past its window; immunity OFF 13:30:3x, ON 13:58:4x; weight 691 / 2430 at
the start, 0.33 at the end; the base + `--kill-gap` 9.13d). VERDICT: L1, K1, K3, E1, U1, D1, R1,
E3, deaths PASS; W1 FAILS (4.41 %). `--kill-gap` stays OFF (4AS's rule).**

| | p37 (9.13c) | **p38 (9.13d)** | bar |
|---|---|---|---|
| L1 floor items picked up | 12 / 23 | **8 / 16 (50.0 %)** | >= 50 %: PASS (at the bar) |
| K1 after the kill p50 | 1.99 s | **1.99 s** (159.2 s in all) | <= 3.0 s: PASS |
| K3 inferred kills real (corrected scorer) | 96.7 % | **96.2 % (51 / 53)** | >= 70 %: PASS |
| E1 kills | 151.2 / h | **53 (126.8 / h)** | >= 80 / h: PASS |
| W1 clicked walks never sent | 3.6 % | **10 / 227 (4.41 %)** | <= 1.5 %: FAIL |
| U1 stuck | 15.2 s | **0 s** (427 requests, 0 ignored) | <= 30 s: PASS |
| D1 GPU p95 | 22.2 ms | **22.8 ms** (p50 20.7, 1,553 calls) | <= 35 ms: PASS |
| R1 pooled own-body class D (p38 + p33 + p35 + p36) | - | **4 + 1 + 0 + 1 = 6** | <= 6: PASS (at the bound) |
| E3 / deaths | | **hard bars pass; 0 dead-end / stuck / idle Fly Wings; 4 boss-guard Fly Wings (lone Garm Babies, a regular spawn here); 6 stalls / 0 deaths; lowest HP 52 %** | PASS |
| L2 hovering loot steps with no death of ours in 10 s before | 2 / 33 | **5 / 26** | reported |
| the loot steps' time | 104.6 s | **80.3 s** (39 steps, 218 hovers, 8 picks) | reported |

- **Items (snatched + picked):** Scell 12, Zargon 8, Piece of Cake 3, Candy 2, Iron 2, Manacles 2,
  Red Herb, Candy Cane, Well-baked Cookie, Darkgreen Dyestuffs, Rough Wind, Ice Cubic 1 each.
- **POST-HOC on W1 (deciding nothing):** 7 of the 10 unsent clicks were ONE 21-s episode
  (1,284.7-1,305.5 s) at (153-164, 116-122): walk targets 7 cells to the WEST, with the red
  no-entry cue counted at the target (3-218 px) and 2 stalls -- the client refused cells the
  planner took as walkable. The other three: 2 answered at 1.25 / 1.37 s (just past the 1.2-s
  window), 1 at 0.86 s after a walk and 1.59 s after a loot step. Without the episode W1 would be
  3 / 220 (1.36 %). A walking-geometry case, not the loot settle; recorded for the walk work.
- **WHY THE LOOT STILL LAGS (the study that 4AT acts on; Batt's two clips):**
  - **The quiet-kill loop:** 1,057 of the run's 1,144 engages ended in the same tick. After a kill
    the fight ends ("quiet kill"); on the next tick any box on the screen (`--engage-screen`)
    starts a new fight; it has no lock yet, so the quiet-kill rule (a kill in the last 3 s) ends it
    at once -- for 3 s, and no box is struck meanwhile.
  - **The loot step is pushed back:** the box engage runs BEFORE the loot step in the loop, so the
    loot list waits until no box is on the screen: only 17 of the 53 kills had a loot step within
    5 s; the median wait was 14.3 s; one step carried 7 kills. The trim hovers the 9 planned cells
    nearest to where she stands THEN -- not the kill's cells (102-157 s: five kills, one loot step
    at 161 s, 0 picks).
  - **The hand in the defend scan is passed by:** 29 PICKUP verdicts in 11 defend scans (the scan
    stops on a sword only): Batt's clip 2.

**Pilot p39 (4AT; 14:35:44-15:01:36, 25 min; the MVP killed 14:34:50 after polls at 14:20 / 14:24 /
14:27 / 14:31 (dead) and 14:34:36 (alive at 65, 60); immunity OFF 14:35:31, kept OFF into p40;
weight 815 / 2430 at the start; the base + `--kill-gap` 9.13d + `--loot-first` 9.16; R2-H2's PNG
recording beside it, `20261109T143541-rdp-hunt-xmas02-p39`, 1,620 frames, 3.52 GB). VERDICT: every
bar but W1 PASSES; W1 FAILS (2.07 %). By 4AT both stay OFF; by 4AU (written before this verdict)
p40 now decides `--kill-gap` + `--loot-first` + `--walk-pick-step` together.**

| | p38 (9.13d) | **p39 (+ --loot-first)** | bar |
|---|---|---|---|
| L1 floor items picked up | 8 / 16 (50.0 %) | **18 / 22 (81.8 %)** | >= 50 %: PASS |
| L3 kills looted within 5 s | 17 / 53 (32 %) | **50 / 58 (86.2 %)** | >= 80 %: PASS |
| L4 engages ended at once by quiet-kill | 1,057 / 1,144 (92 %) | **0 / 91** | <= 5 %: PASS |
| K1 after the kill p50 | 1.99 s | **1.99 s** (180.2 s in all) | <= 3.0 s: PASS |
| K3 inferred kills real | 96.2 % | **96.6 % (56 / 58)** | >= 70 %: PASS |
| E1 kills | 126.8 / h | **62 (148.7 / h)** | >= 80 / h: PASS |
| W1 clicked walks never sent | 4.41 % | **5 / 241 (2.07 %)** | <= 1.5 %: FAIL |
| U1 stuck | 0 s | **5.2 s** (one span, 4 requests) | <= 30 s: PASS |
| D1 GPU p95 | 22.8 ms | **25.0 ms** (p50 20.5) | <= 35 ms: PASS |
| R1 pooled own-body class D (p39 + p33 + p35 + p36) | 6 | **1 + 1 + 0 + 1 = 3** | <= 6: PASS |
| E3 / deaths | | **hard bars pass; 0 dead-end / stuck / idle Fly Wings; 1 `pos_unread` Fly Wing (the minimap readout unread ~26 s at 129, 41 on a light floor: reported, not counted, as p29-p33); 2 stalls / 0; lowest HP 70 %** | PASS |
| L2 hovering loot steps with no death of ours in 10 s before | 5 / 26 | **6 / 58** | reported |
| loot clicks (list / scan hand) | 8 / - | **18 / 1** | reported |

- **Items (snatched + picked):** Scell 15, Zargon 13, Well-baked Cookie 4, Manacles 4, Piece of Cake
  3, Pearl 3, Candy 2, Candy Cane 2, Red Herb 1, Iron 1.
- **Batt's clips, answered:** after a kill the loot step now runs first (86 % within 5 s, from 32 %);
  the instant-end loop is gone (0 of 91 engages, from 92 %); the floor items picked up went from
  50 % to 81.8 % while kills / h rose (148.7 vs 126.8). A defend scan clicked a hand once.
- **POST-HOC on W1 (deciding nothing):** the replay of the client's picking says all 5 unsent clicks
  had a GOOD pick (not p38's ramp case): 2 were sent at +1.21 / +1.27 s (just past W1's 1.2-s
  window), 2 came 1.7 / 2.2 s after a loot step, 1 had its next request 4.35 s later. 9.15c (p40)
  addresses p38's bad-pick fallback, not these.

**Pilot p40 (4AU; 15:03:56-15:29:50, 25 min; straight after p39, the MVP dead by the schedule
(killed 14:34:50); immunity OFF from 14:35:31, ON 15:31:4x; weight 941 / 2430 at the start; the
base + `--kill-gap` 9.13d + `--loot-first` 9.16 + `--walk-pick-step` 9.15c). VERDICT: EVERY BAR
PASSES. By 4AU (p39 failed W1 only) `--kill-gap`, `--loot-first` and `--walk-pick-step` JOIN THE
BASE together.**

| | p38 | p39 | **p40 (+ --walk-pick-step)** | bar |
|---|---|---|---|---|
| W1 clicked walks never sent | 4.41 % | 2.07 % | **3 / 288 (1.04 %)** | <= 1.5 %: PASS |
| L1 floor items picked up | 50.0 % | 81.8 % | **12 / 12 (100 %)** | >= 50 %: PASS |
| L3 kills looted within 5 s | 32 % | 86.2 % | **51 / 56 (91.1 %)** | >= 80 %: PASS |
| L4 engages ended at once | 92 % | 0 % | **0 / 89** | <= 5 %: PASS |
| K1 after the kill p50 | 1.99 s | 1.99 s | **1.97 s** | <= 3.0 s: PASS |
| K3 inferred kills real | 96.2 % | 96.6 % | **96.4 % (54 / 56)** | >= 70 %: PASS |
| E1 kills | 126.8 / h | 148.7 / h | **57 (136.4 / h)** | >= 80 / h: PASS |
| U1 stuck | 0 s | 5.2 s | **0 s** (381 requests, 2 ignored) | <= 30 s: PASS |
| D1 GPU p95 | 22.8 ms | 25.0 ms | **22.5 ms** | <= 35 ms: PASS |
| R1 pooled own-body class D (p40 + p36 + p35 + p33) | | | **1 + 1 + 0 + 1 = 3** | <= 6: PASS |
| E3 / deaths | | | **hard bars pass; 0 dead-end / stuck / idle Fly Wings; 4 boss-guard Fly Wings (8 guard events, all lone Garm Babies); 1 stall / 0; lowest HP 65.7 %** | PASS |
| L2 hovering loot steps with no death of ours in 10 s before | 5 / 26 | 6 / 58 | **7 / 58** | reported |

- **The walk fallbacks:** 9.15c's step taken 5 times (4 clicks, all sent); 9.15b's plain click 0
  times; the 3 unsent clicks were ordinary targets (no fallback). `loot_first_held` 40 ticks; the
  defend scan clicked 2 hands.
- **Items (snatched + picked):** Scell 8, Red Herb 6, Zargon 6, Piece of Cake 5, Candy 4,
  Well-baked Cookie 4, Candy Cane 2, Iron 2, Manacles 2, Rough Wind 1, Nursing Bottle 1.
- **THE BASE NOW:** p16's flags + `--reach-check` + `--far-single --far-approach` + `--explore` +
  `--walk-pick` + `--kill-gap` + `--loot-first` + `--walk-pick-step`.
- **Seen, not decided (for Batt):** the boss guard took 4 Fly Wings in p38 and 4 in p40 on LONE
  Garm Babies (a regular spawn on this map; the pilots run only while the MVP is confirmed dead).
- **Where the time goes now (fight_time):** fights with no kill 30 taking 306.8 s of the 1,500
  (p39: 28, 259.8 s); class D strikes held 154.7 s in all.

**Pilot p41 (4AV; 15:46:47-16:12:40, 25 min; the MVP killed 15:45:51 after polls at 15:35 / 15:38 /
15:42 (dead) and 15:45:36 (alive at 68, 204); immunity OFF 15:46:35, ON 16:14:3x; weight 1099 /
2430 at the start; THE NEW BASE, unchanged). VERDICT: every bar but W1 PASSES; W1 FAILS (1.57 %,
4 of 255). By 4AV the base stays as adopted; W1 is studied and is the next pilot's subject.**

| | p40 | **p41 (the base)** | bar |
|---|---|---|---|
| W1 clicked walks never sent | 1.04 % | **4 / 255 (1.57 %)** | <= 1.5 %: FAIL |
| L1 / L3 / L4 | 100 % / 91.1 % / 0 | **95.2 % (20 / 21) / 86.2 % / 0 of 88** | PASS |
| K1 / K3 | 1.97 s / 96.4 % | **1.96 s / 96.6 % (56 / 58)** | PASS |
| E1 kills | 136.4 / h | **60 (143.6 / h)** | PASS |
| U1 / D1 | 0 s / 22.5 ms | **8.7 s / 23.4 ms** | PASS |
| R1 pooled (p41 + p40 + p36 + p35) | | **0 + 1 + 1 + 0 = 2** | PASS |
| E3 / deaths | | **hard bars pass; 0 Fly Wings, 0 stalls / 0; lowest HP 85.8 %** | PASS |
| reported: Q1 / S1 (`fight_time`, 4AW's) | 34 / 11.2 | **31 quiet defend scans (2 found) / 6.4 damaging hits per 10 min** | - |
| reported: no-kill fights | 30 / 306.8 s | **29 / 213.5 s** | - |

- **Items (snatched + picked):** Scell 17, Zargon 15, Well-baked Cookie 6, Piece of Cake 6, Manacles 4,
  Red Herb 3, Candy 3, Pearl 1, Iron 1, Level 3 Heal 1. The 9.15c step was taken 8 times (all sent).
- **THE W1 STUDY (after p41; deciding nothing yet):** the 33 unsent walk clicks of p37-p41 --
  - the client sent NO other request for any of them (no attack, pickup, NPC or item request in
    -0.3 .. +1.2 s): it simply ignored the click;
  - p39-p41's 13 all had a GOOD pick (the replay) and none was a fallback; p41's 4 were followed by
    the NEXT click's request at +1.24-1.26 s (the click cadence is ~1.27 s);
  - by direction (p36-p41, 1,640 clicks): row 1.7 %, near-row 3.6 %, diagonal far 3.6 %, other
    1.9 %, column 1.1 %: no direction explains it;
  - a click on the SAME target as the previous one went unsent 9 of 145 times (6.2 %), a new
    target 24 of 1,168 (2.1 %): it explains 9 of 33.
  - So the base runs sit at W1 1.0-2.1 % (p39 2.07, p40 1.04, p41 1.57) with no single cause; each
    unsent click costs about one click interval (~1.3 s, ~5 s a run).

**Pilot p42 (4AW by Amendment N; 16:54:41-17:20:31, 25 min; the MVP killed 16:53:48 after polls at
16:46 / 16:50 (dead) and 16:53:35 (alive at 54, 172); the bag cleared 16:23-16:26 (-> 520 / 2430);
immunity OFF 16:54:28, ON 17:22:3x; weight 570 / 2430 at the start; the base + `--quiet-scan`
9.17). VERDICT: every bar but W1 PASSES; W1 FAILS (1.66 %). ➡️ SUPERSEDED BY AMENDMENT O (4AY, Batt's (c)):
W1 pooled 1.37 % PASSES -> `--quiet-scan` JOINS THE BASE. As written: `--quiet-scan` stays OFF by 4AW's rule
until Batt answers 4AX: under option (c) (W1 pooled <= 2.0 %) it would join; under (a) or (b) it
would not (pooled p39-p42: 17 / 1,086 = 1.57 %).**

| | p40 | p41 | **p42 (+ --quiet-scan)** | bar |
|---|---|---|---|---|
| Q1 defend scans with no hit on us in the 5 s before | 34 | 31 | **5 (found 0)** | <= 8: PASS |
| S1 damaging hits on us per 10 min | 11.2 | 6.4 | **6.4** | <= 14: PASS |
| W1 clicked walks never sent | 1.04 % | 1.57 % | **5 / 302 (1.66 %)** | <= 1.5 %: FAIL |
| L1 / L3 / L4 | 100 % / 91.1 % / 0 | 95.2 % / 86.2 % / 0 | **100 % (22 / 22) / 82.0 % / 0 of 99** | PASS |
| K1 / K3 | 1.97 s / 96.4 % | 1.96 s / 96.6 % | **1.98 s / 98.4 % (60 / 61)** | PASS |
| E1 kills | 136.4 / h | 143.6 / h | **64 (153.6 / h)** | PASS |
| U1 / D1 | 0 s / 22.5 ms | 8.7 s / 23.4 ms | **0 s / 22.8 ms** | PASS |
| R1 pooled (p42 + p41 + p40 + p36) | | | **1 + 0 + 1 + 1 = 3** | PASS |
| E3 / deaths | | | **hard bars pass; 0 Fly Wings; 6 stalls / 0; lowest HP 84.8 %** | PASS |
| reported: defend-scan time / no-kill fights | 215 s / 30, 306.8 s | - / 29, 213.5 s | **77.7 s (30 scans) / 38, 212.3 s** | - |

- **The skips:** 34 fight scans and 6 stall scans skipped; the scans still run after damage (30).
- **Items (snatched + picked):** Scell 17, Zargon 14, Red Herb 9, Well-baked Cookie 4, Candy 3, Piece
  of Cake 3, Pearl 3, Manacles 3, Old Blue Box 1, Level 3 Cold Bolt 1, Iron 1.

**Pilot p43 (4AZ; started 20:13:2x ICT; the MVP killed 19:48:56; immunity OFF 20:12:24; the base
+ `--boss-walk` 9.18 + the staged `--stage-mob 1515:2`). THE ROGUE DIED ~18 s into the run (the
runner's reason "death"). VERDICT: deaths FAIL, B1a / B1b FAIL (0 of 2 walk-aways broke contact)
-> `--boss-walk` NOT adopted; the boss guard keeps its Fly Wing. Recovered: the end path's `@warp
prt_fild08 268 107` (20:13:58) brought her back; `@heal` + immunity ON at 20:15 ("HP, SP
recovered.", "You are now immune to attacks.").**

What happened (packets; t = seconds from run_start):

| t | what |
|---|---|
| -4.0 .. 12.2 | the 2 staged Garm Babies (gids ...089 / ...090) attack from the setup's last line on: 29 attacks, ALL misses (her FLEE) |
| 0.7 | her strike on a dog at rel (1, 0) -- one cell EAST -- lands (our damage line) |
| 2.6 / 3.2 | the guard reads "Garm Baby"; walk-away 1: (7, 21) -> (21, 15), 14 cells EAST -- the dog's side |
| 6.4 / 6.8 | a boss line after the 2.5-s grace; walk-away 2: (21, 15) -> (7, 16), back WEST to the start |
| 13.0 .. 16.1 | 8 hits in 3 s, 565-872 each (~5,700; her HP 5,070) |
| 15.2 / 16.6 | the guard's Fly Wing (the 3rd boss line in 60 s); the HP Fly Wing at 6 % |
| ~18 | dead (the hits at 15.7 and 16.1 landed around the wings) |

- **Why it failed (the design, mine):**
  - walk_away_target chose the cell FARTHEST FROM HER with no idea where the threat was. She had
    just struck the dog at rel (1, 0), so the first walk went past it, and the second came back;
    neither broke contact;
  - TWO dogs staged ON her is a much stronger case than a lone dog met in the field (p40: 24 of 24
    misses);
  - the fallback took the 3rd boss line (15 s in) and ~5,700 damage.
- **What a redesign would need (not pre-registered, for Batt):**
  - the walk away from the THREAT: the last strike's / lock's cell or the Miss text's position,
    the farthest pickable cell on the far side;
  - the Fly Wing at once on the first DAMAGING summon hit, or when the HP falls;
  - a staged case of ONE dog a few cells away, never on her.
- `--stage-mob` stays a trial-only option and must not stage strong monsters next to the character
  again without Batt's OK.

**4BA G0 + 4BB G0b (2026-11-10 06:54-07:04 ICT; the Rogue immune; the deployed xmas02-gb; base + `--garm-fly
--stage-mob 1515:1`, 3 min each). VERDICT: G0 FAILS (4BA's letter), G0b FAILS (4BB's letter) -> by 4BA,
`--garm-fly` is NOT adopted; Batt decides whether its pilot runs at all.**

| | G0 (`xmas02-g0`) | G0b (`xmas02-g0b`) |
|---|---|---|
| the staged dog appeared (packets) | 4.61 s BEFORE run_start, 1 cell from us | 4.57 s before run_start, at (10, 19), 3 cells |
| in view from run_start | yes (seen at once) | 0-4.55 s (3-11 cells, we walked east), out of sight at 4.55 s, back in view at 35.6 s |
| the detector's boxes while in view | garm_baby 0.968 in the first detection | 0.99-4.13 s: ONLY our own player box (no box of any class for the dog); at 36.37 s garm_baby 0.969 |
| `garm_seen` / Fly Wing | 1.12 / 1.33 s after run_start | 36.4 / 36.61 s after run_start (0.8 / 1.0 s after re-entering view) |
| the measure / the bar | 5.94 s from appearance / <= 5 s: FAIL | 36.61 s from max(appearance, start) / <= 5 s: FAIL |
| acts of the dog on us | 0 (immune) | 0 (immune) |

- **What they show:** when the detector boxes a Garm Baby, the guard flies within ~0.2-1.0 s; the
  failures are a measure that counted the setup (G0) and a dog the detector did not box for 4.5 s
  near the start while we walked off (G0b; most likely hidden behind scenery -- the label rule
  excludes ~23 % of dogs as occluded, so the model never learned hidden dogs; not verifiable: no
  recording ran). No false garm_baby box in either run.
  ➡️ SUPERSEDED IN PART by xmas02-detector.md N1.4 (2026-11-10 08:2x-09:2x, offline geometry from
  G0b's packets): in all five detections while on screen the dog was FULLY hidden (visible share
  0.00, behind the +30 terrain block south of (6,17)), so no model could have boxed it. The deployed
  xmas02-gb already boxes dogs that are at least half visible (95-96 % on gw1 / gw2); what it lacks
  is the 5-50 % band. "The model never learned hidden dogs" is true but was NOT the cause here.
- Not re-run again (a third variant would be fishing). The Battle Log guard (fly on the first named
  line) stays the base's protection.

**Pilot p44 (4BC; 08:22:53-08:48:51 ICT, 25 min; the MVP killed 08:21:53 after a poll at 08:21 (alive at
184, 100) -- 4BC's "killed 07:00:54" was the G0 run's kill, not this one's; immunity OFF 08:22:35
("Returned to normal state."), ON 08:49:34 ("You are now immune to attacks."); weight 780 / 2430 at
the start; the base, unchanged, with the deployed xmas02-gb). VERDICT: EVERY BAR PASSES -> xmas02-gb
STAYS DEPLOYED for the base (4BC).**

| | p40 | p41 | p42 | **p44 (base, xmas02-gb)** | bar |
|---|---|---|---|---|---|
| W1 clicked walks never sent | 3 / 288 | 4 / 255 | 5 / 302 | **6 / 289 (2.08 %); pooled p44 + p42 + p41 + p40 = 18 / 1,134 (1.59 %)** | pooled <= 2.0 %: PASS |
| L1 / L3 / L4 | 100 % / 91.1 % / 0 | 95.2 % / 86.2 % / 0 | 100 % / 82.0 % / 0 | **100 % (15 / 15) / 89.1 % (57 / 64) / 0 of 99** | PASS |
| K1 / K3 | 1.97 s / 96.4 % | 1.96 s / 96.6 % | 1.98 s / 98.4 % | **1.97 s / 96.9 % (62 / 64)** | PASS |
| E1 kills | 136.4 / h | 143.6 / h | 153.6 / h | **66 (157.6 / h)** | >= 80 / h: PASS |
| U1 stuck / D1 GPU p95 | 0 s / - | 8.7 s / - | 0 s / 22.8 ms | **0 s / 23.7 ms (p50 20.6; 1,568 calls, all GPU)** | PASS |
| R1 own-body class D, pooled p44 + p42 + p41 + p40 | | | | **2 + 1 + 0 + 1 = 4** | <= 6: PASS |
| Q1 defend scans with no hit in the 5 s before | 34 | 31 | 5 | **5 (found 0)** | <= 8: PASS |
| E3 / deaths | | | | **hard bars pass (0 NPC contacts, 0 other maps); 0 Fly Wings; 1 stall; lowest HP 80.3 %; 0 deaths** | PASS |
| reported: S1 hits on us per 10 min / no-kill fights | 11.2 | 6.4 | 6.4 / 38, 212.3 s | **8.0 / 32, 164.8 s** | - |

- **Class D strikes (reported):** 17 of 82 (61 K, 4 A); far strikes 76, class D 14 (18.4 %); by
  distance 0-1: 3 / 6, 2-6: 5 / 52, 7-8: 8 / 23, 9+: 1 / 1. Held on D: 17, median 6.61 s.
- **Sight:** 59 monsters seen (23.5 / 10 min; Myst Case 23, Cruiser 18, Cookie 10, Christmas Cookie 8);
  kills per sighting 1.12. Box targets 116, struck 73; boxes after the grab p50 45 ms.
- **garm_baby boxes: ONE, and it was FALSE.** 08:39:58.35, 1 detection of 1,568: `garm_baby` 0.768 at
  (621, 330)-(686, 398), just below our own player box. Packets: no Garm Baby (job 1515) appeared
  in the whole run; the Rogue stood at (121, 206) and a Cruiser stood at (121, 205), the cell below
  her, the one she was fighting (the kill by hit gap 5.2 s later, 14 hits). So the box was that
  Cruiser, overlapping her sprite, read as a dog in a single frame. Never struck (garm_baby is not
  a target). With `--garm-fly` ON it would have cost one needless Fly Wing in 25 min: a fact for
  xmas02-detector.md N (a false-alarm bar on frames where a monster overlaps the Rogue).
- **Items (snatched + picked), per hour (x 60 / 25.1):** Scell 13 (31.0 / h), Piece of Cake 11
  (26.3), Zargon 11 (26.3), Manacles 6 (14.3), Red Herb 2 (4.8), Candy 2 (4.8), Well-baked Cookie,
  Pearl, Iron, Sandals 1 each (2.4). Weight share 0.33 -> 0.39 at the end.
- E1 157.6 / h is the base's best 25-min run so far (p40-p42: 136-154 / h); one run, not a claim
  that the new model caused it.

**Study after p44 (2026-11-10 08:5x ICT from `date`; offline, the banked p40 / p41 / p42 / p44 sessions; DECIDES
NOTHING): where the base's time goes now.** `scripts/time_budget.py session SID --map xmas_dun02`
(one label per instant, from the packets; its definitions as committed), then a per-kill split of the
after-fight time (packets: our target's death vanish, the `floor_item_appear` packets of its drop;
events: the runner's `kill` / `loot_step`). The three throwaway scripts: NAS
`scratch-archive/2026-11-10/afterkill-study/` (sha256-verified).

| share of the run | p40 | p41 | p42 | p44 |
|---|---|---|---|---|
| fight / approach / search walk | 17.9 / 12.7 / 19.9 % | 19.1 / 13.6 / 18.7 % | 19.4 / 13.4 / 21.7 % | 21.3 / 14.5 / 20.6 % |
| IDLE in all | 49.3 % | 48.3 % | 45.2 % | 43.6 % |
| - after a fight | 273 s | 264 s | 200 s | 299 s |
| - inside the search | 246 s | 206 s | 221 s | 175 s |
| - loot pauses / before an engage | 85 / 136 s | 142 / 114 s | 155 / 100 s | 101 / 82 s |

The after-fight idle, per kill (kills matched to their death packet: p44 44 of 64, p42 43 of 61):
- **death -> the runner's kill:** median 1.96 s (p42 1.97): the 1.6-s kill gap + the Battle Log's
  lag. Our last damaging hit comes 0.49 s before the death vanish (median, all four runs).
  - A shorter gap does not pay: fights with a gap of > 1.0 s between our hits while the target lived:
    p40 1, p41 5, p42 9, p44 5 (> 1.6 s: 1 / 1 / 4 / 1).
  - 1.0 s would save ~0.6 s x ~62 kills = ~38 s a run, but would end ~4 more live fights a run
    (each a ~3-s loot step + a re-engage, ~20 s).
- **THE LOOT STEP ON AN EMPTY FLOOR:** 68-82 % of kills drop NOTHING on the floor:
  - p40 32 of 39, p41 30 / 44, p42 30 / 43, p44 34 / 44 (Snatcher took what it stole during the
    fight; the floor drop comes 0.25 s before the death vanish).
  - Each still gets the full loot step: 9 hovers, median 2.90-2.99 s (84-98 s a run on the matched
    kills alone, i.e. ~6 % of the run).
  - A kill with a drop: median 4.0 s.
- **What would remove it: the bot seeing that nothing fell.**
  - Floor items are not in the detector's classes, so the loot step must hover all 9 cells of the
    3 x 3 drop area. rAthena puts a drop in a free cell around the death cell.
    ➡️ REFINED by xmas02-detector.md Amendment O (O.1a, the packets of five recorded hunts): 62 of 68
    drops landed ON the death cell; the 6 two-item drops added (+1,-1). The death cell is next to
    the Rogue in 218 / 221 kills, and ~1 in 6 drops lands on (0,+1), behind her own body.
  - A **floor-item class** would let the loot step:
    - skip an empty floor (~2.9 s a kill on ~3 of 4 kills);
    - and hover only the boxed cells on the rest (~4.0 s -> ~1-1.5 s).
  - Estimate: ~110-130 s a run back to the hunt (~8 %).
  - Labels from the packets: `floor_item_appear` gives the cell AND the sub-cell (`sub_x`,
    `sub_y`), offline ground truth used only to make labels, as for the monsters (rule 1).
  - The frames: a pilot recorded at 1 fps (~3.3 GB a 25-min run; ~10-14 drops a run, each on the
    floor for ~3-4 s) or immune watches with staged drops.
  - Then T2 (a blind check on item crops), a retrain and the held-out score, as Amendment M.
  - **Data already banked (counted 08:58):** five 1-fps hunt recordings with packets hold 87
    floor items in 6,180 frames:
    - p20 17 items / 1,200 frames, p30 7 / 300, p31 25 / 1,440, p38 16 / 1,620, p39 22 / 1,620;
    - they are not in the monster detector's splits, but p31 / p38 / p39 are the boss recognizer's
      negatives, DEV and HELD-OUT (stormy-knight-recognizer.md R2);
    - enough for a first label rule and its FIT check. A fresh recorded pilot would be the floor
      items' held-out.
- **The idle inside the search (p44, studied 08:5x):** 174.7 s in 230 spans (median 0.38 s); 219
  of them end with our next walk click.
  - 187 spans with no runner event (77 s): the hand-off between walks. The walk decision runs every
    1.2 s and clicks 7 path cells ahead (`--walk-every`, `--walk-ahead`). The clicks came a median
    1.33 s apart; a straight 7-cell leg takes 1.05 s at 150 ms a cell (median leg, by the
    packets' start and end cells), so the Rogue stands ~0.3 s before the next click.
  - The rest (~98 s) is spread over box waits (`box_target` / `box_miss`, the 1.2-s settle),
    reach-check skips, fight ends and loot steps.
  - **Not proposed:** the two "stand less" levers, longer legs and a faster walk timer, were tried
    on gef_fild10 and failed their kills / h bars (rogue-gef10.md AG: -2.5 / h, more walking per
    kill; AH: the timer failed too). Neither is re-run here without a new reason.
- Proposed to Batt, not pre-registered: (a) teach the detector floor items; it could share N1's
  retrain (one training run, the two new things scored by separate bars) or follow it; (b) leave
  the kill gap at 1.6 s.

**4BE G1 + G1b (2026-11-10 09:47-09:57 ICT; the Rogue IMMUNE since 08:49:34; the MVP alive at
(145,137) at 09:46:45, killed by `@killmonster2`, "1[dead]" at 09:47:19; base + `--garm-fly
--garm-confirm 2 --stage-mob 1515:1`, 3 min each). VERDICT: G1 INCONCLUSIVE, G1b C1 PASSES -> p45 runs
(4BE).**

| | G1 (`xmas02-g1`, 09:47:35) | G1b (`xmas02-g1b`, 09:53:10) |
|---|---|---|
| run_start | `"garm_fly": [["garm_baby"], 1.5, "9.19b", 2]` | the same |
| the staged dog (packets) | appeared at (10,18) 4.53 s before run_start, walked to (17,15); we walked north to (9,35); out of view at 4.1 s | appeared at (7,19) 4.73 s before run_start |
| detections boxing it | none of 189 | 2.13, 3.13, 4.13 s (consecutive) |
| `garm_seen` / Fly Wing | none | 3.73 s (streak 2, score 0.981) / the wing pressed 3.94 s; teleported at 3.84 s to (216,180) |
| C1 (wing <= 2.5 s after the first boxing detection) | INCONCLUSIVE (no box) | +1.60 s: PASS |
| acts of the dog on us | 0 | 0 |

- G1b's second `garm_seen` (5.14 s, streak 3) took no second wing (the boss guard's 2-s rule).
- The 2-detection rule cost here: 1.0 s (the next detection) + 0.6 s until the runner's loop read it.
  G0's 1-detection wing came 0.27 s after its box (box 1.06 s, wing 1.33 s).
- G1's dog was never boxed while in view for ~4 s near the start. Why is not studied (likely the
  start's terrain, as G0b's: N1.4); it is the detector's, not this change's.
- **The P1 / P2 scorer, and one clarification written BEFORE p45 was scored (2026-11-10 10:00 ICT from `date`, p45 running since 09:59:09):**
  - positions are interpolated along each walk (ours: self_move at 150 ms a cell, diagonal x1.4; a
    dog's: its entity_appear move at its `speed`). A first draft used the walk's DESTINATION and
    called G1b's real dog "15+ cells away" (we were walking east, away from it).
  - G1b's second `garm_seen` (5.14 s) came from a detection grabbed at 4.13 s, 0.29 s AFTER our own
    teleport (3.84 s): the screen still showed the old place (frame lag + map load). It took no wing.
  - **Clarification:** a `garm_seen` whose detection was grabbed < 2.0 s after our own map change is
    judged (P2) against the dogs near us just before that change. With it G1b gives P2 = 0 false;
    without it, 1.
  - The scorer: NAS scratch-archive/2026-11-10/garm-confirm/p12.py (with p45's evidence).

**Pilot p45 (4BE; 09:59:09-10:25:00 ICT, 25 min; the MVP killed 09:47 ("1[dead]" at 09:47:19);
immunity OFF 09:58:55 ("Returned to normal state."), ON 10:25:23 ("You are now immune to attacks.");
the base + `--garm-fly --garm-confirm 2`; no staged mob). VERDICT: every judged bar PASSES; P1 NO
VERDICT (n = 0) -> by 4BE, `--garm-fly --garm-confirm 2` JOINS THE BASE.**

| | p44 (base) | **p45 (+ --garm-fly --garm-confirm 2)** | bar |
|---|---|---|---|
| P1 lone dogs boxed before acting -> wing before the act | - | **n = 0** (no dog on the map during the run) | NO VERDICT |
| P2 false alarms (`garm_seen` with no live dog within 15 cells) | - | **0** (2 single false boxes, never confirmed; see below) | = 0: PASS |
| W1 walk clicks never sent | 6 / 289 | **4 / 260 (1.54 %); pooled p45 + p44 + p42 + p41 = 19 / 1,106 (1.72 %)** | pooled <= 2.0 %: PASS |
| L1 / L3 / L4 | 100 % / 89.1 % / 0 | **94.7 % (18 / 19) / 83.6 % (56 / 67) / 0 of 106** | PASS |
| K1 / K3 | 1.97 s / 96.9 % | **1.98 s / 97.0 % (65 / 67)** | PASS |
| E1 kills | 66 (157.6 / h) | **66 (158.4 / h)** | >= 80 / h: PASS |
| U1 stuck / D1 GPU p95 | 0 s / 23.7 ms | **0 s / 26.2 ms (p50 20.8; 1,566 calls, all GPU)** | PASS |
| R1 own-body class D, pooled p45 + p44 + p42 + p41 | | **1 + 2 + 1 + 0 = 4** | <= 6: PASS |
| Q1 quiet defend scans | 5 | **5 (found 1)** | <= 8: PASS |
| E3 / deaths | | **hard bars pass; 0 Fly Wings; 1 stall; lowest HP 46 %; 0 deaths** | PASS |
| reported: S1 hits on us per 10 min / no-kill fights | 8.0 / 32, 164.8 s | **11.2 / 44, 261.3 s** | - |

- **The two garm_baby boxes, both FALSE and both filtered:** at 1315.27 s (0.588, box (626,321)-(704,389))
  and 1498.14 s (0.660, (620,339)-(682,404)), each in ONE detection (the next held none); no Garm Baby
  was alive on the map (packets: the only 1515 appeared 9.3 s before run_start and the setup's
  `@killmonster2` cleared it). Both sat on the Rogue's own spot, as p44's (a Cruiser one cell below
  her). Under 9.19 (one detection) each would have taken a needless Fly Wing.
  - So far: 3 false one-detection dog boxes in 50 min of hunting (p44 1, p45 2), all at our own
    position; 0 confirmed. Recorded for xmas02-detector.md N1 / D10 (hard negatives: a monster
    overlapping the Rogue).
- **Class D strikes (reported):** 22 of 90 (65 K, 2 A, 1 B); far strikes 80, class D 21 (26.3 %); by
  distance 0-1: 1 / 10, 2-6: 16 / 61, 7-8: 5 / 19. Held on D: 22, median 6.13 s, 132.2 s in all.
- **Sight:** 64 monsters seen (25.6 / 10 min; Myst Case 25, Cruiser 17, Christmas Cookie 12, Cookie 10),
  kills per sighting 1.03.
- **Items per hour (x 60 / 25.0):** Scell 17 (40.8 / h), Zargon 12 (28.8), Manacles 6 (14.4), Red Herb 5
  (12.0), Candy 5 (12.0), Well-baked Cookie 3 (7.2), Candy Cane, Piece of Cake, Pearl, Iron 1 each (2.4).
- The lowest HP, 46 %, is the lowest of the base runs reported here (p44 80.3 %); 0 Fly Wings were
  needed. Reported, not a bar.
