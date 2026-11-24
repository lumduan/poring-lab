---
doc_type: plan
hypothesis: "On xmas_dun02 at 1920x1080, the Rogue built to Batt's 2026-11-22 numbers (ATK 110 + 25, HIT 354, FLEE 366 + 1, DEF 82 + 120) and fighting with her FISTS (no Knife swap, no weapon worn; Snatcher steals on the punches) kills and steals at least as well as the current base (the Knife swap, tonight's round-10 pilots). ➡️ AMENDMENT 1 (2026-11-23): the lab server is PRE-RENEWAL, so those four values cannot be reached here; the Rogue carries his stat totals and gear choices instead, and her window reads ATK 121 + 0, HIT 179, FLEE 266 + 1, DEF 27 + 23 (section 5)."
status: ACTIVE
role: null
verdict_date: null
verdict_ticket: null
supersedes: null
related: [rogue-xmas02.md, xmas02-items-1080.md, screen-size-ab.md, ../../scripts/screen_ab.py, ../../scripts/stage2_ab.py, ../../scripts/bare_steal.py]
next_action: "2026-11-24 10:5x (Amendment 12): fst4-fst6 played clean (0 weapon changes, 0 deaths, 1,605-1,610 frames); the fists match the Knife-swap base on packet kills/h (75.2 vs 70.7) and steals/h (56.6 vs 53.1) with no swap, gross z/h 28,845 vs 39,955 (noisy). Not an A/B. Batt decides: keep the fists as they are, or an interleaved fists-vs-Knife A/B (pre-registered first)."
title: "The fists at 1080: Batt's build, no Knife swap (a trial, written before any of its data)"
date: 2026-11-22
owner: Batt
---

# The fists at 1080 (written 2026-11-22 23:08 ICT from `date`, before any data)

## 0. What Batt asked (2026-11-22 ~23:0x, after the report's section 6)

> "ตอนนี้ฉันเปลี่ยนกลยุทธ์ไม่สลับมีดแล้ว ใช้หมัดต่อยเอา ฆ่าเร็วอยู่ ขโมยของติดไม่ยาก ลองปรับตัวละครไม่ใช้อาวุธ
> แล้วค่าโจมตีเท่าฉันดูนะ เน้นค่า ATK FLEE HIT DEF ให้เป็นตามนี้เลยนะ แล้วใช้หมัดต่อยแทนการสลับมีดดู"

In English: he no longer swaps the Knife; he punches with his fists, kills fast, and steals easily.
Build our character with no weapon and his attack values (ATK, FLEE, HIT and DEF exactly as on his
status window), and fight with fists instead of the Knife swap.

His status window (a picture he sent): Str 60+9, Agi 99+8, Vit 17+6, Int 1+7, Dex 70+10, Luk 2;
**Atk 110 + 25, Hit 354, Flee 366 + 1, Def 82 + 120**; Matk 52, Mdef 53 + 6, Critical 1, Aspd 176,
status points 0.

## 1. What his numbers are (the RENEWAL rules: his server's, not the lab's)

➡️ **WRONG FOR THE LAB (Amendment 1, section 5): the lab server is PRE-RENEWAL.** `.env`
`RATHENA_PRERE=yes` on both labs overrides the Dockerfile's default `PRERE=no` that this
section read (`.env.example`: Batt 2026-09-30, the Classic ruleset). The table below stays true
of HIS window (his numbers fit the renewal rules exactly): he plays on a renewal server.

| line | renewal rule | his | from |
|---|---|---|---|
| HIT | 175 + BaseLv + DEX + LUK/3 | 175 + 99 + 80 + 0 = **354** | stats alone |
| ATK (left) | STR + DEX/5 + LUK/3 + BaseLv/4 | 69 + 16 + 0.7 + 24.75 = **110** | stats alone |
| ATK (right) | equipment ATK | **25** | not known: read on our window (section 3) |
| DEF (left) | VIT/2 + AGI/5 + BaseLv/2 | 11.5 + 21.4 + 49.5 = **82** | stats alone |
| DEF (right) | equipment DEF (+1 a refine level, refine.yml Armor) | **120** | gear |
| FLEE | 100 + BaseLv + AGI + LUK/5, + Improve Dodge (4 a level for a 2nd Thief class) | 306 + 40 = 346, **+ 20** = 366 | gear (+20) |
| FLEE (+1) | perfect dodge 1 + LUK/10 | **1** | stats |

- The Rogue's job-50 bonus is Str +6, Agi +7, Vit +6, Int +4, Dex +7 (db/re/job_stats.yml). His
  "+" values are that plus Str +3, Int +3, Dex +3 (a Blessing Lv 3 pattern) and Agi +1 (Thief
  Clothes).

## 2. The build (the same totals; his +3 goes into her base stats)

➡️ Built 2026-11-23 01:50-02:01 with two changes (no `@item2`; the dagger's shortcut moved to F7,
not removed), and on this server the same build reads other numbers: Amendment 1 (section 5).

- **Base stats:** Str 63, Agi 99, Vit 17, Int 4, Dex 73, Luk 2. Totals with the job bonus and
  Thief Clothes: Str 69, Agi 107, Vit 23, Int 8, Dex 80, Luk 2. These give HIT 354, ATK 110 and
  DEF 82 by the rules above. The window shows "63 + 6" where his shows "60 + 9"; the four lines
  he named are the same.
- **No weapon worn.** The dagger (Damascus 1222, +8) and the Knife (1201) stay in the bag. Their
  hotbar keys F4 / F5 are cleared, because clear-bag refuses while F5 shows the dagger's icon
  (dungeon_hunt clear_bag_bare_refused).
- **Gear:**
  - FLEE +20: Manteau [1] (2506, DEF 13) with a Whisper Card (4102, FLEE +20) replaces the
    Manteau (2505, DEF 13).
  - DEF 120: Boots 16 + Manteau 13 + Thief Clothes 40 + Goggle 5 + Buckler 40 = 114, plus the Thief
    Clothes refined +6.
  - No Rosaries (2608 x 2: LUK +4 would raise HIT and FLEE).
  - ATK +25: read on her window with no weapon. If it is not 25, the nearest gear is chosen, and
    the difference is reported.
- **Her build before, to restore it:** Str 1, Agi 99, Vit 1, Int 1, Dex 99, Luk 1; Rosary x 2,
  Boots, Manteau (2505), Thief Clothes +0, Goggle, Buckler; Damascus +8 worn (F5), Knife (F4); 688
  status points unspent. GM lines only (`@str` .. `@luk` by difference, `@item2`, `@refine`); the
  equipment window by the client's own clicks.
- **The check:** her status window read on a frame after the build. ATK, HIT, FLEE and DEF must
  equal his, or each difference is written down with its cause.

## 3. When (the dev client is busy until ~01:50)

1. Round 10's pilots end (~01:50). Its eval chain runs offline (the GPU, no client), so the build is
   done on the client meanwhile.
2. Round 10's score waits for no dev detect server, so the trial's runs start after it (~04:00).

## 4. The trial (reported; Batt decides)

➡️ The procedure and the rulers are Amendment 2's (section 6): recorded pilots, 25 min.

- **The block:** `screen_ab.py run --label fst1080 --screen 1080 --runs 3 --minutes 20 --box-set
  knife_swap=false`.
  - It is the base box with the Knife swap off: the runner loses `--bare-steal` and its dependents
    (`--steal-opener F4`, `--dagger-key F5`, the Knife's numbers, `--bare-ready`, `--steal-cue`,
    `--swap-gap`), nothing else.
  - The deployed models (xmas02v1080, items xmas02fi5); stage2_ab's setup, not immune.
  - The popup watcher (item-popup-reader.md Amendment 6) runs beside each run.
- **Code (this commit):**
  - `screen_ab.switch_dependents`: a switch turned off may drop its own dependents' flags.
  - `stage2_ab.swap_in_use`: with the swap off, the setup leaves the weapon as the player set it.
  - Tests for both.
- **Reported against the current base**, tonight's round-10 natural pilots ifH31-ifH36 (the same
  map, model and screen, 25 min each), and against Batt's own run (228.5 kills/h):
  - kills/h;
  - steals/h (packets: a pickup_result with no pickup_request of ours);
  - loot/h and z/h (econ_db);
  - deaths and errors.
- **Not an A/B:** the base runs are not interleaved with the fists' runs, and the build differs too
  (Batt asked for both together). If the fists look at least as good, a pre-registered A/B
  (interleaved, one build) is the next step, and adoption is Batt's word.

## 5. Amendment 1 (2026-11-23 02:02 ICT from `date`): the lab is PRE-RENEWAL; the build as made

**The correction.** Section 1 took the lab server for renewal from the Dockerfile's default
(`ARG PRERE=no`). The lab's `.env` sets `RATHENA_PRERE=yes` (dev and live alike; `.env.example`:
Batt 2026-09-30, "the Ragnarok Classic ruleset the lab's research targets"), and
`docs/planning/rogue-xmas02.md` section 1 says pre-renewal too. Her status window proves it (below).
His window fits the renewal rules exactly, so it comes from the renewal server his own client plays
on (the live lab has no rAthena of its own).

**What was done (the GM lines from the server's `atcommandlog`, ICT):**
- 01:50:52-01:51:19 `@str 62`, `@vit 16`, `@int 3`, `@dex -26`, `@luk 1`; 01:51:53 `@refine 16 6`
  (Thief Clothes +6, worn).
- `@item2 2506 1 1 0 0 4102 0 0 0` was NOT run: the server echoed it as plain chat, its answer when
  the group lacks the command. Group 20 has `item`, not `item2`, and each of its permissions is
  Batt's word, so none was added. Instead: 01:55:24 `@item 2506 1` (Manteau [1]), 01:55:32
  `@item 4102 1` (Whisper Card), then the client's own Insert Card window put the card in.
- The client's own clicks at 1920x1080 (each read back on a frame): the equipment window
  (Alt+Q, home (185, 300)) double-clicks took off the Damascus +8 and both Rosaries; the carded
  Manteau [1] was put on from the bag (Battle Log: the Manteau "is taken off", the Manteau [1] "is
  put on"); the plain Manteau (2505) is in the bag.
- The hotbar: a shortcut dragged onto the world is NOT removed by this client ("Item cannot be
  discarded from the window"; nothing dropped, the weight unchanged). The Damascus shortcut was
  moved along the bar from F5 to the empty F7; the Knife stays on F4. On a frame afterwards:
  `clear_bag_bare_refused` passes (F5 empty), `clear_bag_eqp_refused` passes with the series' tabs
  (etc, use) and still refuses with eqp (it guards the Knife and the Damascus).

**Her status window, 02:01 (fullscreen frame):**

| line | hers now | his (renewal) | the pre-renewal rule (rAthena) |
|---|---|---|---|
| Str .. Luk | 63+6, 99+8, 17+6, 4+4, 73+7, 2 | 60+9, 99+8, 17+6, 1+7, 70+10, 2 | the same totals 69 / 107 / 23 / 8 / 80 / 2 |
| Atk | **121 + 0** | 110 + 25 | STR + (STR/10)^2 + DEX/5 + LUK/5 = 69 + 36 + 16 + 0; + weapon ATK (none) |
| Hit | **179** | 354 | BaseLv + DEX = 99 + 80 |
| Flee | **266 + 1** | 366 + 1 | BaseLv + AGI + Improve Dodge 40 + Whisper 20 = 99 + 107 + 40 + 20 |
| Def | **27 + 23** | 82 + 120 | equipment DEF (with the +6) + VIT |
| Aspd | 180 | 176 | bare hands |

Also: Matk 9 + 9, Mdef 0 + 8, Critical 1, Status Point 688, HP 5,828, SP 545, weight 987 / 4,290.
Her old build's window (2026-11-05 15:05, recorded in `scripts/dungeon_hunt.py` CHARS_CONF
"rogue"): HIT 205, FLEE 246 + 1, Aspd 176.

**His four values cannot be reached on this server:** HIT 354 would need DEX ~255 (BaseLv 99 +
DEX; the most DEX is 99 + 7); FLEE 366 is ~100 over this build with its FLEE card; 82 + 120 is not
a pre-renewal DEF. The closest faithful build is his: the same stat totals and gear choices, which
this server turns into its own numbers.

**Options for Batt (the trial runs with option 1 unless he says otherwise; it is a trial):**
1. Keep it: his stats and gear, this server's numbers (the table).
2. Match the fight, not the numbers (e.g. his hit and dodge chances against his monsters): it needs
   his server's monster data; not proposed now.
3. A renewal lab: `RATHENA_PRERE=no` is a rebuild that changes the whole lab's rules (monsters,
   drops, every baseline measured since 2026-09-30). His 2026-09-30 decision; not proposed.

**Restore (section 2's record, updated):** `@str -62`, `@vit -16`, `@int -3`, `@dex 26`,
`@luk -1`, `@refine 16 -6`; the Damascus, both Rosaries and the plain Manteau back on through the
windows; the Damascus shortcut back to F5. The carded Manteau [1] stays in her bag.

## 6. Amendment 2 (2026-11-23 02:25 ICT from `date`, BEFORE any fists data): the trial's procedure and rulers

**The procedure: round 10's own base pilots, with one change.** Section 4's block becomes three
pilots, fst1, fst2, fst3, each one exactly what ifH31-ifH36 were (xmas02-items-1080.md Amendment 36's
`pilot_rec.sh`): `@heal`, `@warp xmas_dun02 114 23`, the zoom check (1.000), the chat-window
standard, the 1 fps PNG recorder beside ONE `screen_ab.py run --runs 1 --minutes 25 --model
xmas02v1080`, then the recording shipped to the NAS; NOT immune. The one change:
`--box-set knife_swap=false` (section 4's switch). So:
- 25 minutes, not section 4's 20: the base pilots' length, one procedure on both sides;
- recorded: each session's packets judge its kills and steals, as for the base.
- Round 10's checks after each pilot: >= 1,400 frames and no PAUSED line, else a stop (a person
  first). A RAM check (>= 3,000 MB) before each.
- When: after round 10's eval chain ends and the dev checkout is fast-forwarded to main (it holds
  6e109461's switch); round 10's score waits for no screen_ab run by its own rule.
- The build: Amendment 1's (option 1, his stats and gear; Batt may still choose otherwise).
- The popup reader's round-4 watcher runs beside each (item-popup-reader.md Amendment 11): these
  recordings are sessions of its set w1080b.

**The rulers, the same on both sides:**
- the runner's own records: `stage10_ab.score_run` per run (kills/h and loot/h over the played
  minutes, deaths, how it ended, errors);
- the packets: `weapon_swap_study.py SESSION` (dungeon_judge's window): kills, kills with a steal
  (an item gain between our first hit on the monster and 1 s after its death, not <= 2 s after a
  pickup request of ours), kills/h and steals/h over the window, the kill time with and without a
  steal;
- z/h: `score_run`'s economy (gross / net per hour);
- Batt's 228.5 kills/h (his Knife-swap run of 2026-11-12) beside.

**The base, computed with those rulers at 02:2x (ifH31-ifH36, the Knife swap at 1080):**

| pilot | runner kills/h | runner loot/h | packet kills/h | steals/h | kills stolen | kill s with / without a steal |
|---|---|---|---|---|---|---|
| ifH31 | 65.6 | 82.6 | 55.4 | 44.4 | 20 / 25 | 20.8 / 5.2 |
| ifH32 | 97.1 | 128.7 | 80.3 | 53.5 | 24 / 36 | 10.4 / 7.7 |
| ifH33 | 82.6 | 131.1 | 70.8 | 55.3 | 25 / 32 | 11.7 / 7.5 |
| ifH34 | 65.6 | 128.7 | 60.0 | 41.4 | 20 / 29 | 14.7 / 8.9 |
| ifH35 | 94.8 | 116.6 | 71.9 | 51.6 | 23 / 32 | 15.2 / 8.7 |
| ifH36 | 114.2 | 140.9 | 86.4 | 73.1 | 33 / 39 | 13.1 / 9.6 |

Pooled by packets: 70.7 kills/h, 53.1 steals/h, 75.1 % of kills stolen. Every base run: 24.7 min
played, 0 deaths, ended by its time box, no error.

**Still not an A/B** (section 4): one block after the other, and the build differs. No verdict; an
interleaved A/B is the next step only on Batt's word.

## 7. Amendment 3 (2026-11-23 07:04 ICT from `date`, after fst1 started, before any fists result): the build applied again; the trial started

- **Why again:** her Knife-swap build was put back at 03:05-03:10 for the item model's round-10
  extension (xmas02-items-1080.md Amendment 38), and the carded Manteau [1] was deleted then (its
  weight). Round 10 is scored (Amendment 40: FAIL), there is no 8c, so the trial runs now.
- **The build, Amendment 1's exactly** (dev client, in Prontera, 06:5x-07:00; the GM lines typed
  through the UI gate, each answered in the Chat tab):
  - `@str 62`, `@vit 16`, `@int 3`, `@dex -26`, `@luk 1` ("Stat changed"); `@refine 16 6` ("1
    item has been refined": the Thief Clothes +6, worn);
  - `@item 2506 1`, `@item 4102 1` ("Item created" x 2), then the client's Insert Card window (the
    card double-clicked in the Etc tab, the Manteau [1] picked, OK): "Compounding has completed
    successfully";
  - the equipment window: the Damascus +8 and both Rosaries taken off, the carded Manteau [1] put
    on (Battle Log: each "taken off" / "put on"); the plain Manteau in the bag;
  - the hotbar: the Damascus shortcut dragged F5 -> F7 (F5 empty, the Knife still on F4).
- **Her status window (07:00, fullscreen frame):** Str 63+6, Agi 99+8, Vit 17+6, Int 4+4, Dex
  73+7, Luk 2; **ATK 121 + 0, HIT 179, FLEE 266 + 1, DEF 27 + 23, Aspd 180**; Status Point 688;
  weight 899 / 4,290. The same as Amendment 1's table.
- **Not immune:** two `@monsterignore` lines, read in the Chat tab ("You are now immune to
  attacks." then "Returned to normal state.").
- **The dev checkout** fast-forwarded to a5984788 (two docs commits after 61a4f913; the switch
  6e109461 in it); `fists/ff.ok` = 1.
- **fst1 started 07:01:39** (`fists_pilots.sh`, Amendment 2's procedure unchanged): heal, warp,
  zoom 1.000, the chat window standard, the recorder, then the run. Its runner config differs from
  round 10's base pilot ifH39 in one key only (`knife_swap` true -> false); the series log: "the
  Knife swap is off ... the weapon is left as it is".
- **After fst3:** her Knife-swap build is put back for the item model's round 11 (its held-out is
  played as rounds 8-10's were), read against the old window.

## 8. Amendment 4 (2026-11-23 07:09 ICT from `date`, BEFORE any fists play): fst1 ABORTED -- the MVP killed her during the pre-run checks; her idle time moves to town

- **What happened:** fst1's pre-run steps warped her to xmas_dun02 (114, 23), then the zoom check
  warped her to its reference cell (93, 82); the chat check, the recorder start and the detect
  server's start followed there, about 1.5 min standing, NOT immune. The **Stormy Knight** (the
  map's MVP; alive, Batt's player mode) and Cruisers hit her: the Battle Log reads 1,129, 1,092 and
  5,615 from the Stormy Knight and 1,331, 125, 138 from Cruisers. The run's setup read HP 0 before
  and after its `@heal` and stopped ("a person first", play rc 2, 07:03:53). **No fists play
  happened.**
- **Aftercare (07:05-07:12):** immunity ON (read: "You are now immune to attacks."), `@alive`,
  `@warp prontera 156 191`, `@heal`; a frame read HP 5,828 / 5,828 and weight 899 / 4,290 (the bag
  unchanged); immunity OFF again in town (read: "Returned to normal state.").
- **fst1's leftovers renamed** (never part of the trial or of the popup reader's w1080b):
  `screen-ab/fst1-play-aborted-0704`, `fists/fst1-aborted-0704`, `popup-w1080b/fst1-aborted-0704`
  and the NAS session `20261123T070246-rdp-xmas02-fst1-ABORTED` (a 1-min recording, shipped
  before the stop was seen).
- **Why the base pilots never met it:** `pilot_rec.sh` (rounds 8-10's natural pilots, the base
  ifH31-ifH36 too) has the same ~1.5-min idle on the map; no base pilot died there. It is an exposure
  of the procedure, not of the fists.
- **The fix (`fist_pilot_rec2.sh`, a new file; `fists_pilots2.sh` runs it):** `@warp prontera 156
  191` first, and again right after the zoom check, so the chat check, the recorder start and the
  detect server's start happen in town. Her time on xmas_dun02 before the run drops to the zoom
  check (~30 s). The run's own setup warps her to its start cell as before, so the PLAY is
  unchanged: the same runner config (ifH39's but `knife_swap`), the same 25 min, the same rulers.
  The recording now opens with ~1 min of town frames (the rulers read packets and the runner's own
  records from the run's start).
- **The trial again:** fst1, fst2, fst3 under the same labels, the round-4 popup watcher beside
  each. The queue waits for `fists/immune_off.ok` = 1 (written after the read above).
- **For the item model's round 11:** its held-out pilots take the same town step (a procedure
  change written into its pre-registration).

## 9. Amendment 5 (2026-11-23 07:21 ICT from `date`, BEFORE any fists play): the second fst1 stopped at the hunt core's start -- the box's recipes need the swap; fixed

- **What happened (07:09-07:13):** `fist_pilot_rec2.sh` worked as Amendment 4 wrote it (both town
  warps, zoom 1.000, the chat window standard, the recorder; the setup warped her to (7, 21), the
  top-ups, the start check 7 of 7). The hunt core then refused before any input of its own: "the
  box's recipes swap the Knife, but this run swaps no Knife (the Run settings' knife swap:
  --bare-steal with --steal-opener)". The run ended after 0.4 min, rc 0; no hunt session, no economy
  record; the series stopped ("ended within 60 s"). She was warped to Prontera at once (not immune,
  HP full).
- **Why:** the box (stage10's B, the base pilots' box) strikes its monsters by RECIPES, and the
  runner (dungeon@9.51 `recipes_refused`) refuses any recipe without the swap: the recipes decide
  the swap per monster. Section 4's switch (6e109461) dropped the swap's runner flags only. The
  live player already drops the swap WHOLE (the Knife functions and the recipes,
  `flow_play.without_knife`) when the start check finds the swap's set-up unreadable (Batt 11-19);
  the Run setting turned off on purpose did not reach it. Amendment 2's plan was checked by
  screen_ab's plan step (which compares the box's arguments and passed) but never played end to end.
- **The fix (83645b20, main; the dev checkout fast-forwarded):** `flow_play.knife_swap_set_off` --
  at the Run's start, a hunt core whose settings turn the swap off plays `without_knife` too, with a
  NOTE in the run log. The runner then strikes every monster with its own plain recipe (strike,
  wait for the kill, loot), as Batt's fists do. The runner file is unchanged (byte-pinned). Tests:
  the unit case, and the real fists box through the runner's own `recipes_refused` (refused before,
  accepted after); 325 tests of the 21 files that import flow_play pass.
  - The A/B plan is unchanged (the drop happens at the start, never in `prepare`), so screen_ab's
    box check still compares the box's own arguments.
  - **The live lab does not have it** (live code changes only on Batt's word): a fists Run on live
    would end the same way until it is promoted.
- **Leftovers renamed:** `screen-ab/fst1-play-aborted-0713`, `fists/fst1-aborted-0713`,
  `popup-w1080b/fst1-aborted-0713`, the demo folder `...-play-fst1-play-r01B-aborted-0713` and the
  NAS session `20261123T071112-rdp-xmas02-fst1-ABORTED`.
- **The trial again:** fst1, fst2, fst3, `fists_pilots2.sh` unchanged (Amendment 4's procedure).

## 10. Amendment 6 (2026-11-23 09:08 ICT from `date`): fst1-fst3 are VOID as a fists trial -- she fought with the Damascus; what they did measure

- **What happened:** the box's candy event (`eat_candy`: "hotbar_count(F7) >= 1 -> press F7")
  pressed **F7 0.6 s into fst1**: "box eat_candy (hotbar_count(F7) 1)". Amendment 1 had parked the
  Damascus shortcut on F7 (the client would not remove it), over her **Candy** shortcut, and this
  client draws a "1" under one equipment item. So the box read one candy, pressed F7 and **put the
  +8 Damascus on**. fst2 and fst3 started with it on. Proof: the packets' weapon changes
  (weapon_swap_study `swaps`): fst1 1, fst2 0, fst3 0; the equipment window at 09:0x showed the
  Damascus worn; no other F7 press in any run.
- **So fst1-fst3 measured Batt's stat totals and gear (Amendment 1) + the Damascus +8 + NO Knife
  swap**, not his fists. Each run was otherwise as registered: 25.3 min, rc 0, 0 deaths, ended by
  its time box, >= 1,597 frames, 0 PAUSED, the economy recorded.
- **The numbers (Amendment 2's rulers, `fists/score_fists.py`, which reproduces the base table):**

  | run | runner kills/h | runner loot/h | packet kills/h | steals/h | kills stolen | kill s median (stolen / not) | gross z/h | net z/h | weapon changes |
  |---|---|---|---|---|---|---|---|---|---|
| fst1 | 116.6 | 174.8 | 130.5 | 36.0 | 16 / 58 | 3.71 / 3.96 | 26,040 | 25,311 | 1 |
| fst2 | 119.1 | 150.7 | 125.4 | 40.3 | 18 / 56 | 3.97 / 4.43 | 20,890 | 19,820 | 0 |
| fst3 | 89.8 | 155.3 | 115.5 | 35.5 | 16 / 52 | 4.69 / 3.71 | 25,086 | 24,358 | 0 |
| ifH31 | 65.6 | 82.6 | 55.4 | 44.4 | 20 / 25 | 20.78 / 5.17 | 16,430 | -1,831 | 42 |
| ifH32 | 97.1 | 128.7 | 80.3 | 53.5 | 24 / 36 | 10.42 / 7.71 | 65,297 | 45,875 | 80 |
| ifH33 | 82.6 | 131.1 | 70.8 | 55.3 | 25 / 32 | 11.69 / 7.5 | 69,090 | 67,195 | 56 |
| ifH34 | 65.6 | 128.7 | 60.0 | 41.4 | 20 / 29 | 14.71 / 8.89 | 23,912 | 22,418 | 62 |
| ifH35 | 94.8 | 116.6 | 71.9 | 51.6 | 23 / 32 | 15.21 / 8.69 | 29,168 | 19,206 | 50 |
| ifH36 | 114.2 | 140.9 | 86.4 | 73.1 | 33 / 39 | 13.09 / 9.58 | 35,821 | 34,582 | 70 |

  Pooled: the no-swap Damascus runs **123.8 packet kills/h** (base 70.7), **37.3 steals/h** (base
  53.1), 30.1 % of kills stolen (base 75.1 %), gross **24,007 z/h** (base 39,955; the base's runs
  range 16,430-69,090 z/h). Batt's Knife-swap run: 228.5 kills/h. Not an A/B (one block after the
  other, the build differs too).
- **A side effect in the base pilots, found the same way:** the Candy shortcut on F7 was lost when
  the Damascus was parked there at 01:5x. ifH31-ifH36 pressed F7 (ate a candy) 2, 4, 0, 1, 4, 4
  times; ifH37-ifH39 (the item model's round-10 extension) 0, 0, 0. Their play lacked candy eating
  (HP from candies); no death. Written into xmas02-items-1080.md too. Restored at 09:05 (a Candy
  dragged from the bag onto F7).
- **Her build at 09:0x (for the item model's round 11):** the Knife-swap build put back and read
  (HIT 205, FLEE 246 + 1, Aspd 176; Damascus +8 worn with its shortcut on F5, the Knife on F4, the
  Candy on F7, both Rosaries and the plain Manteau; the carded Manteau [1] deleted).
- **The real fists re-trial (fst4, fst5, fst6), registered now, before any of its data:**
  - the build as Amendment 1 (the stat lines, the carded Manteau [1], the Thief Clothes +6, no
    weapon, no Rosaries), with the Damascus shortcut on **F2**: no key of the box (F1, F4-F9) and
    no event reads F2; the Candy stays on F7;
  - the equipment window read before each pilot (the weapon slot empty);
  - `fist_pilot_rec2.sh` and `fists_pilots2.sh` unchanged but for the labels;
  - **a run with any weapon change in its packets (`swaps` > 0) is void**, and the queue stops;
  - the same rulers and the same base; when: after the item model's round-11 GPU work (its pilots,
    training and evaluation hold the dev client and the dev GPU worker first), so this evening.

## 11. Amendment 7 (2026-11-23 11:15 ICT from `date`): Batt's answers; live already plays fists; a live recording as the fists reference

- **Batt, 11-23 ~11:1x (his words, translated):**
  1. "You may record video on live: the bot there is punching with its fists and stealing now."
  2. "It is being done, go and look; the fix is easy: just do not put the knife on at the start."
  3. On the open choices (this build's option 1, frontend-dev, the steal cue, the 7 x 9 bag, live
     deployment): "look at how live plays first."
- **What live does (its run log, read only; Run `flowplay-poring-lab-live-11231110`, 11:10):** the
  start check reads the knife and dagger slots as NOT the swap's set-up, and the Run plays WITHOUT
  the swap whole: "NOTE: knife, dagger did not read as the weapon swap's set-up: xmas_dun02 plays
  WITHOUT the swap this run (and its Knife functions and its 4 monster recipe(s): the runner
  strikes plainly)" -- the start's `knife_swap_off` path (Batt 11-19, "do not lock this"). So live
  needs no code for fists, and 83645b20 (the same drop when the Run SETTING turns the swap off) is
  not needed there. Seen in the same log: the minimap did not name the map (best match 0.17), the
  bag count failed (the 7 x 9 bag), F1 holds Yellow Potions (a warning, the player's choice).
- **The live recording, `live-fists-1`:** `record_session.py --backend rdp --label live-fists-1
  --seconds 3600 --fps 1 --format png --max-bytes 8G` from the LIVE checkout, started 11:14:24 beside
  the running Run. Frames only: no input, no code change, no Run setting touched. PNG, not the
  default GPU video, so the popup reader can read it offline (a popup lives ~4.75 s, so 1 fps sees
  each one several times). It may stop at its 8 GB cap (~2.4 MB a frame) before the hour.
- **What it is for:** the fists reference on HIS server with HIS stats (renewal, the numbers the lab
  cannot reach, Amendment 1): over the recording's window, the runner's own kills / loot steps per
  hour (its events.jsonl) and the item gains read from the popups offline; no packets on live, so
  steals are read from the screen (a gain not after a loot step of ours), and said so.
- **The dev re-trial fst4-fst6 (Amendment 6) stays registered** for this evening, as the lab's
  pre-renewal side of the same question; Batt may drop it after he sees the live numbers.

## 12. Amendment 8 (2026-11-23 11:28 ICT from `date`): live's item gains come from the popup watcher on its real screen

- **The recording holds the bot's VIRTUAL view:** `live-fists-1`'s frames are 1280 x 720 (the
  recorder grabs GAME_REGION's virtual picture, as on dev: fst1's are 1280 x 720 too). The popup is
  shrunk there with the world (item-popup-reader.md Amendment 6), so the popup reader cannot read
  it from the recording (tried on fst1: 0 events from 1,597 frames). The recording stays as the
  record of the play (route, kills, video review).
- **So the gains are read live:** the popup reader's ROUND-5 watcher (item_popup.py from
  0f35e645, copied to scratch) runs on the live client's REAL frame through the LIVE checkout's own
  ro_agent (its .env, its screen; `slot_items` and `bare_steal` are byte-identical in both
  checkouts), dev's icon pictures and the r4 count font, from 11:26:01 for 3,000 s
  (`popup-live/live-fists-1`). Pixels only: no input, no Run setting, no file the Run reads.
- **Read so far:** the band is the same as on dev (853, 72, 536 x 38); the icons read (distance
  2.4), the AMOUNT did not (live's client may draw the count differently): live counts gains, not
  amounts.
- **The reference** (reported when the watcher ends): over its window, the live Run's own events
  (kills by hit gap, loot clicks), the watcher's gains, a gain <= 3 s after one of our loot clicks
  counted as a pickup and any other as a steal -- a screen estimate, said so.

## 13. Amendment 9 (2026-11-23 12:17 ICT from `date`): the live fists reference

- **The recording `live-fists-1`** ran its full hour (11:14:24-12:14:34): 29 shards, 7.59 GB, the
  bot's virtual 1280 x 720 view at 1 fps. Its last step (the packets) failed -- live has no
  sniffer container (`docker exec poring-lab-live-sniffer-1 ls /captures` rc 1) -- so it wrote
  no manifest; the frames are intact. It goes to the NAS as a recording.
- **The window measured:** the round-5 popup watcher's, 11:26:01-12:16:06 (50.0 min, 11,993 ticks,
  p95 84 ms, 0 grab errors), against the live Run's own events over the same span
  (`flowplay-poring-lab-live-11231110`, its hunt1 and hunt2: one RE-READ at 11:44:35, "position
  jump", hunting again 3 s later; no death).

  | | live, fists (his server, his stats) | dev, Damascus + no swap (fst1-3, void as fists) | dev base, Knife swap (ifH31-36) | Batt, Knife swap (11-12) |
  |---|---|---|---|---|
  | kills/h | **145.2** (121, the runner's exp line) | 123.8 packets / 108.5 runner | 70.7 packets / 86.6 runner | 228.5 |
  | steals/h | **~57.6** (48, screen estimate) | 37.3 packets | 53.1 packets | |
  | item gains/h | 92.4 (77: 29 within 3 s of our loot click, 48 not) | | | |
  | loot clicks/h | 37.2 | | | |
  | deaths | 0 | 0 | 0 | |

- **How the live numbers are read, and their limits:** kills are the runner's own (on live, read
  from the exp line, all 121 here); gains are the popup reader's events (icons read for all 77,
  amounts for none: live's client draws the count differently); a gain <= 3 s after one of our loot
  clicks counts as a pickup, any other as a steal. No packets on live, so neither is the packet
  ground truth the dev columns use. The servers differ (his renewal server and character vs the
  lab's pre-renewal Rogue), so this is a reference, not an A/B.
- Items gained (the watcher's reads): 911 x 26, 539-group x 17, 601-group x 7, 529-group x 7,
  538-group x 4, 722 x 4, 1098 x 4, others <= 2.
- Also seen on live (its log, for Batt's look): the minimap never names the map (best 0.15), the
  bag count fails (7 x 9), F1 holds Yellow Potions.

## 14. Amendment 10 (2026-11-23 12:29 ICT from `date`): Batt's decisions after the look at live

- **Batt, 11-23 ~12:3x (his words, translated), on the three open points:**
  1. The dev re-trial fst4-fst6: "ok" -- read as: it stays queued (after the item model's round-11
     score); he may still say "skip it".
  2. The open choices (this build's option 1, the steal cue, the 7 x 9 bag, live deployment):
     "carry on" -- the agent decides and does them:
     - **option 1 is kept** (his stat totals and gear, the lab's pre-renewal numbers);
     - **the steal cue is dropped**: it timed the Knife swap-back, and live plays fists with no
       swap (Amendment 7);
     - **the 7 x 9 bag**: bag_count learns his bag's size (built and tested on dev; to live only
       between Runs, after a word to Batt);
     - nothing else is ready for live (the item model and the popup reader have not passed).
  3. Live's popup AMOUNTS (unread on live, Amendment 8): "I want it, teach it to read them too. But
     if you record, tell me in advance: I will check the chat window and turn talking off, because
     other users come in and play -- so you do not capture their words." So the count font for
     his client is taught from crops of the popup BAND only (536 x 38 px at the top centre), taken
     only after his "ready".
- **The morning's full-screen recording** (`live-fists-1`, Amendment 9) was taken before this rule
  and may hold other players' chat; it is on the NAS only. Batt was asked: delete it, or keep it
  with the chat area blacked out.

## 15. Amendment 11 (2026-11-24 09:17 ICT from `date`, BEFORE any fst4 data): Batt's answers; the build applied for fst4-fst6

- **Batt, 2026-11-23 ~13:3x:** promote live (done 13:35-13:39), frontend-dev allowed (done), and
  the morning's `live-fists-1` recording **stays on the NAS, not deleted**: "no other people's chat
  in this video, I had it turned off; keep it as the reference to improve the bot". Amendment 10's
  open question is closed.
- **Batt, 2026-11-24 ~09:1x:** "carry on" with fst4-fst6 (the item model's round 11 and its 8c are
  done, xmas02-items-1080.md Amendments 46-49); live's heal item stays the Yellow Potion, "do not
  lock this" (the live player's check is a warning; the agent makes it accept any heal potion).
- **The build, Amendment 1's exactly** (dev client, in town, 09:0x-09:16; the GM lines through the
  UI gate, each answered in the Chat tab):
  - `@str 62`, `@vit 16`, `@int 3`, `@dex -26`, `@luk 1` ("Stat changed"); `@refine 16 6`
    ("Upgrade success!!", "1 item has been refined": the Thief Clothes +6, worn);
  - `@item 2506 1`, `@item 4102 1` ("Item created" x 2); the Insert Card window: "Compounding has
    completed successfully";
  - the equipment window: the Damascus +8 [1] and both Rosaries taken off, the plain Manteau
    taken off, the carded Manteau [1] put on (the Battle Log, each line); the weapon slot, acc.1 and
    acc.2 read EMPTY;
  - the hotbar: the Damascus shortcut dragged F5 -> **F2** (its tooltip "F2 +8 ... [1]: 1"); F5,
    F6, F7 empty; F1 7 White Potions, F4 the Knife, F8 28 Fly Wings, F9 2 Butterfly Wings.
- **Her status window (09:1x, fullscreen frame):** Str 63+6, Agi 99+8, Vit 17+6, Int 4+4, Dex
  73+7, Luk 2; **ATK 121 + 0, HIT 179, FLEE 266 + 1, DEF 27 + 23, Aspd 180**; Status Point 688;
  weight 1,032 / 4,290. Amendment 1's table, unchanged.
- **Not immune:** two `@monsterignore` lines read in the Chat tab ("You are now immune to
  attacks." then "Returned to normal state."). The chat window standard read back (Battle Log
  tab selected).
- **One difference from Amendment 6: NO candy.** F7's Candy and F6's Candy Cane were eaten in the
  item model's round-11 pilots, and the series' setup runs clear-bag (every Use-tab stack dropped)
  whenever the bag reads >= 40 %, so a restock would not hold equally across fst4-fst6 (the same
  reason as xmas02-items-1080.md Amendment 48). The base ifH31-ifH36 had candies at times; ifH37-ifH39
  had none. Reported, not corrected for.
- **The queue:** `fists_pilots3.sh` (registered in Amendment 6), started now with a TRACKED waiter;
  after each pilot, Amendment 2's checks and the packets' weapon changes (`swaps` must be 0, else the
  run is void and the queue stops).

## 16. Amendment 12 (2026-11-24 10:53 ICT from `date`, after fst6 ended at 10:51): the fists re-trial's numbers

- **The three pilots ran as registered** (`fists_pilots3.sh`, Amendment 6's procedure, started
  09:17:47, done 10:51:11):

  | pilot | session (NAS) | played | frames | PAUSED | weapon changes | deaths | end |
  |---|---|---|---|---|---|---|---|
  | fst4 | 20261124T091941-rdp-xmas02-fst4 | 24.68 min | 1,610 | 0 | 0 | 0 | the time box |
  | fst5 | 20261124T095053-rdp-xmas02-fst5 | 24.70 min | 1,605 | 0 | 0 | 0 | the time box |
  | fst6 | 20261124T102154-rdp-xmas02-fst6 | 24.70 min | 1,609 | 0 | 0 | 0 | the time box |

  Each: play rc 0, no runner error, the economy recorded ("economy record done"), the round-5 popup
  watcher beside it (set w1080c: 44, 36, 35 events; 0 grab errors; scored with that reader's own
  plan, not here).
- **The dev checkout moved during fst4** (disclosed): it was fast-forwarded fbecefec -> 1d17a1a9 at
  09:22:53, 1.3 min after fst4's hunt began (09:21:33). 1d17a1a9 changes the player's loot_items
  `auto` and the heal role at the default heal pick; neither reaches these runs. Their runner
  (`runner-5b1.py`, sha256 521e86ac...), project (`project-B.json`, d313eb48...) and runner
  config (`runner-config-B.json`) are byte-identical in fst4, fst5 and fst6.
- **The numbers (Amendment 2's rulers, `fists/score_fists.py`, the same as for fst1-fst3):**

  | run | runner kills/h | runner loot/h | packet kills/h | steals/h | kills stolen | kill s median (stolen / not) | gross z/h | net z/h | weapon changes |
  |---|---|---|---|---|---|---|---|---|---|
  | fst4 | 109.4 | 158.0 | 80.4 | 67.0 | 30 / 36 | 18.08 / 5.98 | 31,175 | 30,202 | 0 |
  | fst5 | 68.0 | 123.9 | 71.5 | 49.2 | 22 / 32 | 16.90 / 10.12 | 35,087 | 33,605 | 0 |
  | fst6 | 94.7 | 143.3 | 73.6 | 53.6 | 24 / 33 | 21.09 / 9.13 | 20,272 | 16,288 | 0 |

- **Pooled, beside the other blocks (packets: kills and steals over the judged windows; items from
  the econ DB's run_items):**

  | | fists (fst4-6) | Knife swap, the base (ifH31-36) | Damascus +8, no swap (fst1-3) | Batt, Knife swap (11-12) | live, fists (his server, Amendment 9) |
  |---|---|---|---|---|---|
  | hours | 1.235 | 2.471 | 1.235 | | 0.83 |
  | packet kills/h | **75.2** (101) | 70.7 | 123.8 | 228.5 | 145.2 (runner, exp line) |
  | steals/h | **56.6** (76) | 53.1 | 37.3 | | ~57.6 (screen estimate) |
  | kills stolen | 75.2 % | 75.1 % | 30.1 % | | |
  | weapon changes / run | 0 | 42-80 | 0 (fst1: 1) | | |
  | items gained / h | 89.9 (111) | 84.6 (209) | 63.1 (78) | | 92.4 (screen) |
  | of which stolen / picked | 72.1 / 17.8 | 68.0 / 16.6 | 39.7 / 23.5 | | |
  | picked of dropped | 22 / 32 (68.8 %) | 41 / 67 (61.2 %) | 29 / 53 (54.7 %) | | |
  | gross z/h (mean of runs) | 28,845 (20,272-35,087) | 39,955 (16,430-69,090) | 24,007 | | |
  | deaths | 0 | 0 | 0 | | 0 |

- **Items per hour, fists (fst4-6, 1.235 h; income = picked + stolen):** Zargon (912) 34 = 27.5/h
  (25 stolen); Scell (911) 26 = 21.1/h (20); Well-baked Cookie (538) 11 = 8.9/h; Red Herb (507),
  Piece of Cake (539), Manacles (1098) 8 each = 6.5/h; Candy (529) 6 = 4.9/h (all stolen); Candy
  Cane (530) 4 = 3.2/h; Level 3 Cold Bolt (688) and Iron (998) 2 each = 1.6/h; Level 3 Heal
  (12001) and Pearl (722) 1 each = 0.8/h.
- **What it says (not an A/B; one block after the other, and the builds differ):**
  - The fists kill and steal **about as well as the Knife swap** (+6 % kills/h, +7 % steals/h, the
    same stolen share), with **no weapon change at all** where the base made 42-80 a run.
  - A kill takes long either way: the fists' stolen kills take 16.9-21.1 s (median), the base's
    10.4-20.8 s; ATK 121 with no weapon. The Damascus without the swap kills 75 % more an hour but
    steals on 30 % of its kills, not 75 %.
  - Gross z/h is lower (28,845 vs 39,955), but the base's own runs range 16,430-69,090: a few rare
    drops decide it, so three runs cannot separate the two.
  - No candy in fst4-fst6 (Amendment 11); the base ate candies at times (Amendment 6). Not
    corrected for.
- **Next, Batt's word:** keep the fists as they are (live already plays them: Amendment 7), or a
  pre-registered interleaved A/B (fists vs the Knife swap, one build, one block) if the z/h gap
  matters to him.
