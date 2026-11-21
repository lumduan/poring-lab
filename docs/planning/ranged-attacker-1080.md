---
doc_type: plan
status: ACTIVE
role: null
verdict_date: null
verdict_ticket: null
supersedes: null
related: [cursor-1080.md, rogue-xmas02.md, xmas02-items-1080.md, ../../scripts/flow_play.py, ../../scripts/dungeon_hunt.py]
next_action: "Its A/B (A' vs R, 3 + 3, interleaved) on the dev lab after 5b's chain ends (cursor-1080.md Amendment 10's order)."
title: "Shot from afar at 1080: strike the shooter the detector sees, before the ring scan (pre-registration)"
date: 2026-11-21
owner: Batt
---

# Shot from afar at 1080 (pre-registration, 2026-11-21)

Written before any run of this round. Nothing below is edited after its commit, except by a
labelled, clock-stamped amendment (section 7).

## 0. What Batt asked

2026-11-21, with a 5.4 s clip of the dev lab at 19:26 (pilot ifH9): "The character scans around
itself for what attacks it, but it is really attacked from far away, so it never finds it. I
suggest also detecting the monsters around it on the screen, and training it to know which one
attacks." On the order (20:2x): after tonight's 5b test.

## 1. The facts (offline; the 20 finished round-6/7 1080 item pilots, 404 min, packets)

- **Who hits her** (an `act` packet from a monster to her; its cell from the monster's last appear
  or stop, hers from the minimap read):

  | | hits | distance p50 (cells) | from >= 2 cells |
  |---|---|---|---|
  | Cruiser | 6,963 | 6.0 | 79.1 % |
  | Myst Case | 2,710 | 1.0 | 14.5 % |
  | Christmas Cookie | 690 | 1.0 | 17.2 % |
  | Cookie | 385 | 1.0 | 21.8 % |

  The knowledge base's `attack_range`: Cruiser 7; every other monster here 1, the Stormy Knight 2.
- **The defend scans** (the hover ring of the cells around her):
  - 1,152 scans (171 an hour), 3,337 s = 8.3 min of every hour; the attacker found 40 %;
  - with only far hitters (>= 2 cells) in the 3 s before: 464 scans, 1,602 s, found 35 %;
    374 had a Cruiser as the last hitter.
- **The detector already saw the shooter** in 246 of those 464 (53 %): a monster box on the
  attacker's cell (+-1) in the last world read (<= 1.5 s old). Those scans took 934 s, about
  2.3 min an hour. The rest: 200 not boxed, 18 off the view grid.
- **Where those scans sit:** 263 (57 %) in fights a hit started (Battle Log 151, Miss 88, HP drop
  24); 195 in fights a box started.
- **What exists:** `--defend-box` (dungeon@9.39, OFF): in a fight a hit started, it first tries
  the NEAREST box within 110 px of her feet (~3 cells), with one sword hover.
  - 4DP (rogue-xmas02.md, 2026-11-12, at 720) judged it a FLAG: it almost never found a box within
    110 px (21 tries, 1 strike), and kills/h went -6.9 %.
  - A Cruiser shooting from 6 cells is outside that reach by design.
- **Scripts:** `/dev/shm/poring-lab-tmp/ranged_hits.py` and `ranged_boxed.py` (scratch,
  archived with the round).

## 2. The change (arm R)

- **`defend_ranged`**, a player switch on the fight tab, off by default. The live player wraps
  `BoxWatch.near` (flow_play `ranged_defend`); `dungeon_hunt.py` stays byte-identical.
- With `--defend-box` on, the defend box pick (the call with DEFEND_BOX_PX) first takes the
  nearest SHOOTER on the detector's last fresh read:
  - a box of a species whose KB `attack_range` is >= 3 (data, not a name: any map's archers too);
  - its foot projected within that range + 1 cell of her (the flat grid projection);
  - never her own box, and never one the box path's own skip test refuses. That is the last test
    an engage-screen pick passed: out of view, or out of reach from her cell NOW (the reach check,
    4AE).
- Nearest by cells, then by px. The record says `ranged_defend` with its species and distance.
- No shooter: the runner's own defend pick (the nearest box within 110 px), then the ring scan, as
  `--defend-box` does today.
- Arm R = `--box-set defend_box=true --player-set defend_ranged=on`. Everything else is the base.

## 3. The A/B

- A' (the base, as 5b's arm A) vs R, at 1080 on the dev lab's Rogue at xmas_dun02.
- 3 valid runs a side, 25 min, NOT immune (OFF judged on the session first), interleaved
  A' R A' R A' R.
- screen_ab.py one-run series `rng-A1..3` and `rng-R1..3`, and pilot_rec.sh's preamble per run
  (no recorder).
- It runs after 5b's chain ends (cursor-1080.md Amendment 10's order). Its own control A' is
  interleaved with R, never 5b's A from hours before.
- **Bars, scored once** (scorer committed before the first run):
  - **R1** kills/h: mean(R) - mean(A') > +2 SE (Welch);
  - **R2** defend-scan seconds an hour: mean(R) < mean(A') x 0.75;
  - **R3** deaths R <= A'; errors none new.
  - R joins the base when R1-R3 pass. R2 alone passing is reported as "faster, not more".
- **Reported:**
  - `ranged_defend` picks an hour and their species / distance;
  - what each pick became (packets: an attack request on that monster, walks only, nothing);
  - Cruiser hits on her an hour;
  - potions and Fly Wings an hour; z/h (economy, every run).

## 4. Not in this round

- Training "which one attacks" (Batt's second half). The labels exist on dev: each `act` packet
  names the monster that hit her, and the 1 fps pilot recordings show it. It comes next if R leaves
  a large remainder.
  - 47 % of the far shooters were NOT boxed, which points at the detector's recall at range first.
- Box-started fights (42 % of the far-hit scans): the defend pick does not run there.

## 5. What it runs beside

- 5b's chain has the dev lab first. Batt's live Runs may run beside: dev does not wait for live
  (Amendment 10). A live slowdown is fine (Batt).

## 6. Scored by

- `scripts/ranged_ab_score.py`, committed before the first run.

## 7. RESULTS and AMENDMENTS (clock-labelled)

### Amendment 1 (2026-11-22 03:23 ICT from `date`, BEFORE the first run): merged; the chain; when it starts

- **Merged into main** (84d5256c) after origin/main's evening work: the focused tests pass with the
  branch's packages first (105: test_ranged_defend, the block pins, flow_play / flow_run, the 5b
  scorer).
- **The chain** (docs/records/scorers/rng_chain.sh, verbatim) starts after 5b's fifth C run
  (cursor-1080.md Amendment 12), fast-forwards the dev checkout to origin/main, then plays
  A' R A' R A' R.
- **A valid run is the SCORER's rule** (`screen_ab.valid`: >= 80 % of the 25 min, or a home end;
  rc 0). An arm short of 3 valid runs gets more runs at the end, at most 2 more, and every run of
  the arm counts. 5b's chain counted only runs 1-3 and judged by played seconds; that is fixed
  here.
- **Immunity:** OFF was judged before 5b on this game session, and the session has run on since
  (no re-login), so the A/B plays NOT immune.
- **Seen during 5b** (cursor-1080.md Amendment 12): run c5b-C3 ran out of potions at 15 min after a
  Cruiser's shots (454 damage a minute; the other runs 157-248). This round reports potions an
  hour (section 3), which shows it.

### Amendment 2 (2026-11-22 04:21 ICT from `date`, BEFORE any R run): R1 refused by the harness; screen_ab fixed between runs; the order of the rest

- **rng-A1 played** (03:47-04:13). **rng-R1 was refused at 04:15:39 before any input:** "the
  settings changed the runner's argv beyond ['--defend-box']'s value".
  - screen_ab's pre-check lets a `--box-set` change only a runner flag's VALUE. `defend_box` is a
    SWITCH, a flag with no value: on adds `--defend-box`, so the argv grew by one and was refused.
  - No R run has played. The A' runs never use this check (no box setting), so A1 and A2 stand.
- **The fix** (scripts/screen_ab.py, tested): a switch box setting may add or leave out its OWN
  flag; every other argument must still match. Tests cover that, the old refusals, and the plan of
  arm R itself (`--box-set defend_box=true --player-set defend_ranged=on`).
- **The chain was stopped by its STOP file at 04:20**, so it ends after rng-A2 (04:16-04:42).
  The fix reaches the dev checkout only after that, between runs. A follow-on chain
  (docs/records/scorers/rng_chain2.sh, verbatim) then plays the rest: **R1, A3, R2, R3**, with the
  same preamble, flags, validity rule and up to 2 make-up runs per arm.
- The scorer and the bars are unchanged.

### Amendment 3 (2026-11-22 06:16 ICT from `date`, BEFORE the score): A3 and R2 never played; the make-up runs; the arms scored

- **rng-A3 (05:15) and rng-R2 (05:17) were stopped by screen_ab's setup before any input:** "after
  @heal her HP reads 0, not 95 % or more (a person first)". Both reads before and after the typed
  @heal said 0 %. The chain was stopped by its STOP2 file at 05:19, as rng-R3 began; that marker
  was retired by hand (renamed) once R3's setup read 7 % -> 100 % after @heal and R3 played (05:22).
  - No arm code ran in either (the setup is the same for both arms). They are VOID, as 5b's C1
    was. The cause is not established: the Rogue is not immune between runs, and the preamble's
    warp-in spot (114, 23) is where she waits ~1 min. The sniffer capture is not read (it sits in
    a Docker volume).
- **Valid so far:** A1, A2, A4 (the make-up run, 05:48-06:16); R1, R3. R4 (the make-up) plays
  06:17-06:43.
- **Scored once, after R4:**

      ranged_ab_score.py score --arm A=rng-A1+rng-A2+rng-A4 --arm R=rng-R1+rng-R3+rng-R4

  If R4 is not valid, R has 2 valid runs and the scorer judges on them (said in the result).
- **The shooter pick fires:** R1's player record (the `-play-` session, which the scorer reads)
  holds 4 picks, all Cruisers, at 6, 4, 1 and 8 cells.

