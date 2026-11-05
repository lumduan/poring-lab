---
doc_type: design
hypothesis: "On xmas_dun02 (Toy Factory 2F, the lab's pre-renewal server), the Rogue at Base 99 with base AGI 99 / DEX 99 and the gef10 skills, walking the map's EDGE clockwise (Batt's technique) and fighting plain melee so Snatcher steals on its own, gains stolen items per hour that are worth more than at its current build; and the live v1 detector's generic 'monster' class sees this map's species well enough (Q1's bar, section 4) that no new detector is needed first."
status: "X0 DONE 2026-11-05 15:05 (the Rogue at Base 99, AGI 99+8, DEX 99+7; section 5). X1 (the offline prep) running. Planned 2026-11-05 (Batt's order ~13:2x, his four answers ~14:0x ICT, section 0)."
role: null
verdict_date: null
verdict_ticket: null
supersedes: null
related: [rogue-gef10.md, gef10-prep.md, xmas02-prep.md, gef10-detector.md, ../benchmarks/gef10-eval.md, ../demonstrations.md, ../../scripts/dungeon_hunt.py, ../../scripts/dungeon_judge.py, ../../services/rathena/conf/import/groups.yml]
next_action: "X0 setup (the stat commands go in with the 2026-11-05 14:45+ rathena recreate), then the offline prep X1, then the v1 measurement X2 (pre-registered in section 4 BEFORE its recording)."
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
