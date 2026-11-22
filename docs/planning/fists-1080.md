---
doc_type: plan
hypothesis: "On xmas_dun02 at 1920x1080, the Rogue built to Batt's 2026-11-22 numbers (ATK 110 + 25, HIT 354, FLEE 366 + 1, DEF 82 + 120) and fighting with her FISTS (no Knife swap, no weapon worn; Snatcher steals on the punches) kills and steals at least as well as the current base (the Knife swap, tonight's round-10 pilots)."
status: ACTIVE
role: null
verdict_date: null
verdict_ticket: null
supersedes: null
related: [rogue-xmas02.md, xmas02-items-1080.md, screen-size-ab.md, ../../scripts/screen_ab.py, ../../scripts/stage2_ab.py, ../../scripts/bare_steal.py]
next_action: "After round 10's pilots (~01:50): the build on the dev Rogue (section 3), its status window read against Batt's numbers; the trial block after round 10's score (section 4)."
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

## 1. What his numbers are (the lab server is RENEWAL: `services/rathena/Dockerfile` PRERE=no)

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
