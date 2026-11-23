---
doc_type: plan
hypothesis: "On xmas_dun02 at 1920x1080, the Rogue built to Batt's 2026-11-22 numbers (ATK 110 + 25, HIT 354, FLEE 366 + 1, DEF 82 + 120) and fighting with her FISTS (no Knife swap, no weapon worn; Snatcher steals on the punches) kills and steals at least as well as the current base (the Knife swap, tonight's round-10 pilots). ➡️ AMENDMENT 1 (2026-11-23): the lab server is PRE-RENEWAL, so those four values cannot be reached here; the Rogue carries his stat totals and gear choices instead, and her window reads ATK 121 + 0, HIT 179, FLEE 266 + 1, DEF 27 + 23 (section 5)."
status: ACTIVE
role: null
verdict_date: null
verdict_ticket: null
supersedes: null
related: [rogue-xmas02.md, xmas02-items-1080.md, screen-size-ab.md, ../../scripts/screen_ab.py, ../../scripts/stage2_ab.py, ../../scripts/bare_steal.py]
next_action: "The fists build re-applied and read (Amendment 3, 06:56-07:01); fst1-fst3 running from 07:01 (25 min each, ~08:35); then the report against ifH31-ifH36 (Amendment 2's rulers) and her Knife-swap build put back for the item model's round 11. Batt: keep the build (Amendment 1 options); a fists benchmark run of his own."
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
