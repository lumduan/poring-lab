---
doc_type: hypothesis
hypothesis: "On the lab's own client and rAthena, the bot plays xmas_dun02 at 1920x1080 fullscreen (through the virtual 1280x720 client) as well as at 1280x720 fullscreen: no more deaths, and kills/h and loot/h no lower beyond the per-run noise."
status: PROPOSED
role: null
verdict_date: null
verdict_ticket: null
supersedes: null
related: [fullscreen-client.md, live-blocks.md, teaching-prerun.md, ../../scripts/screen_ab.py, ../../scripts/stage10_ab.py, ../../scripts/stage2_ab.py]
next_action: "Pre-registered 2026-11-19 22:57 ICT, before any of its data. Run the 1080 block, switch the lab client and session to 1280x720 fullscreen, run the 720 block, then score; then fix what plays worse at 1080 (Batt 2026-11-19 ~22:5x: 'tune 1920x1080 to play as well as possible, like I play')."
---

# s11scr: the screen size, 1280x720 against 1920x1080 (pre-registered 2026-11-19 22:57 ICT)

## Why

- Batt 2026-11-19 ~22:4x: "test with the offline server at 1920x1080, like live, to see how the
  bot works, compared with before".
- Then ~22:5x: "make 1920x1080 play as well as possible, like I play myself".
- At 1920x1080 the bot plays through the virtual 1280x720 client (fullscreen-client.md section
  7):
  - the world is scaled 1.5 about the centre;
  - the panels are found by their shape;
  - the cursor's own pixels are pasted unscaled.
- So far only a 2-minute run has played at 1080 on the lab (2026-11-18 15:31). Batt's own client
  played longer runs on the Thai dev server, where no packets give the truth.
- This series measures, on the lab where packets give the truth, what changes at 1080 and how
  much. It is a characterisation, not a switch to adopt: its result says where to work next.

## The arms

- **A = 1280x720 fullscreen**:
  - `.env` SESSION_SIZE 1280x720, GAME_REGION 0,0,1280,720;
  - the lab client's OptionInfo.lua WIDTH/HEIGHT 1280 / 720, ISFULLSCREENMODE 1;
  - the lab's measured 720 layout (fullscreen-client.md section 5).
- **B = 1920x1080 fullscreen**:
  - SESSION_SIZE 1920x1080, GAME_REGION 0,0,1920,1080;
  - OptionInfo.lua 1920 / 1080, ISFULLSCREENMODE 1.
- **The same everything else:**
  - The same code: main at the series' start; the runner byte-pinned.
  - The same box: the ready-made functions box as it is, s10ab's B (xmas02sk; fly_first,
    fly_first_hp, fly_first_land ON), through `flow_play.py play`.
  - The same character: the lab's Rogue, not immune.
  - The same map (xmas_dun02, the MVP alive) and stage2_ab's setup before every run.
- `screen_ab.py run` refuses before any input unless the `.env` screen is the block's and the
  backend's frames are that size.

## The runs

- Two blocks of 3 runs of 20 min: B first (the lab is at 1080 tonight), then one switch, then A.
  - Each block is one `screen_ab.py` series, with its own label: `s11scr-1080`, `s11scr-720`.
  - The switch is made by hand, once: close the client; OptionInfo.lua; `.env` (with
    RO_SHORTCUT / SHELL_SHORTCUT); `recreate:desktop` + `recreate:backend`; `recover gm`.
- Valid run: rc 0 or 130, at least 16 min played (80 %) or a valid end (bag full, home), not
  short (stage10's rule).

## JUDGED (WORSE if a line fails, INCONCLUSIVE if none fails but one cannot be judged, else SAME)

1. Deaths: B <= A over the played runs. Non-strict: two zero blocks pass.
2. Kills/h: mean(B) - mean(A) >= -2 SE.
   - SE is the two blocks' standard error of the difference (Welch).
   - It needs at least 2 valid runs per block, else INCONCLUSIVE.
3. Loot/h: the same rule as kills/h.
4. Errors: no B run ends with a code error or refuses its start, unless an A run does the same.

The lines follow the bar lessons (ab-bar-design-lessons):
- deaths use <=, so 0 = 0 passes;
- -2 SE passes about 98 % of the time when nothing changed;
- with only 3 runs a block the SE is wide (per-run kills/h SD about 12-15 in s9ab / s10ab, so SE
  is about 11). A line can pass and still hide a real 10-15 % loss. So the REPORTED numbers below
  matter as much as the verdict.

## REPORTED only

- openers/h;
- the tick pace (median tick ms);
- the detect ms;
- Fly Wings/h by kind, and false boss Fly Wings/h by the packets' truth (stage9_ab's);
- the economy with steals (z/h);
- the model each run loaded;
- each block's mean +- SE;
- "before": s10ab's B runs (2026-11-17, the same box at the old window size, the code of then):
  r02B 129.5, r03B 133.0, r06B 145.9, r07B 114.7 kills/h (lab.sqlite).
- Batt's bar (batt-benchmark-knife-swap): 228.5 kills/h, 135,737 common z/h.

## Limits

- The blocks are not interleaved: one switch, so drift between blocks (the map's state, the MVP's
  clock) goes into the difference. The setup's warps alternate within each block as usual.
- 3 runs a block: see the SE above.

## Addendum 1 (written 2026-11-19 23:3x ICT, during s11scr-1080's run 1, before any B2 data)

What run 1's first 16 minutes showed (screen_ab.py diag):
- At 1080, 53 box engagements made 17 kills (0.32 per engagement). At 720, s10ab's runs made
  0.66-0.83 (42-49 kills from 59-71 engagements).
- The cursor read "unknown" on 36 % of box targets (720: 0-5 %). A hover took 460 ms from the
  grab to its verdict (720: 254 ms).
- The cause, measured live and read-only:
  - a 64 x 64 read of the virtual client cost 69 ms, because the whole real frame came through the
    grab pipe and the whole virtual picture was built;
  - the cursor check reads every 30 ms inside the runner's CURSOR_WAIT_S of 0.35 s, so it got
    about 4 reads instead of about 10.
- Also seen (reported, not fixed here):
  - Christmas Goblin boxes 0.011 per frame (720: 0.001-0.002), many on the player or a monster;
    the player found 0.87 per frame (720: 0.98);
  - no Miss cue read at 1080: the text is native-size, and shrunk in the virtual picture.
    ➡️ WRONG, corrected 2026-11-20 06:4x ICT from the runs' events: the runner's `miss_cue`
    fired at 1080 too (16-110 an hour per run, scores 0.61-0.78; 720: 39-62 an hour). The
    Miss cue is not a cause.

**B2 = the 1080 block again with `feat/virtual-box-grab`.** A virtual box reads only its real
pixels (64 x 64: 69 -> 3.5 ms), and the world resample is exact by axis takes (the whole picture:
64 -> 19 ms).
- At 1280x720 that code is never used (the identity view: no virtual reads), so block A stays the
  control for B2 too.
- The same judged lines as B, B2 against A.
- Reported, B2 against B: the cursor's "unknown" share on box targets, kills per box engagement,
  the hover time, the tick pace.
- Label `s11scr-1080f`, 3 runs of 20 min, after the 720 block. The branch is merged only after
  block A ends.

## Addendum 2 (written 2026-11-19 23:4x ICT, before any B2 or B3 data): the false alarms

Run 1, scored by stage9's packet truth (an alarm-species unit on screen, outside the post-vanish
windows):
- 17 boss Fly Wings, 16 FALSE:
  - 15 were Christmas Goblin boxes: 9 at 0.27-0.65 with a 2-frame streak, 2 at 0.27 / 0.42 with a
    3-frame streak, and 4 alone at 0.73-0.85;
  - 1 was a Stormy Knight box alone at 0.73.
- The one true alarm was the Stormy Knight (0.998, streak 4).
- That is about 48 false an hour. s10ab at 720 made 15 false in 8 runs (about 5.6 an hour), and
  9 true ones.
- Each false Fly Wing costs the teleport and BOSS_AVOID_S (30 s with no box engagement).

The true alarms of s10ab (720), sighting score and streak:
- knight 0.64 (streak 6);
- goblin 0.712 (1), 0.835 (1), 0.903 (3), 0.951 (1);
- knight 0.836 (1), 0.997 (4);
- garm 0.971 (4), 0.978 (1).

Two candidates, NOT adopted (each its own block, after B2):
- **C1, a code candidate: no cursor patch in the detection threads' frames.** The virtual
  client's cursor patch is the real pixels around the pointer, unscaled, so the world inside its
  68 x 68 square is magnified 1.5x over the hovered monster.
  - `ro_agent.NO_CURSOR_THREADS` = the runner's box-watch and hud-watch threads.
  - First a probe (the Rogue immune, moves only): the same real frames detected with and
    without the patch. Adopted into a block only if the probe shows fewer alarm-class boxes
    without it.
- **C2, a setting candidate (Batt decides; safety): garm_confirm 2 -> 3.**
  - On the data above it removes the 9 false sightings with a 2-frame streak (7 of 16 remain).
  - It keeps every s10ab true alarm: each scored >= alarm_solo 0.7 or had a streak >= 3.
  - The cost: a true low-score alarm flies one detection later (about 0.25 s).
  - Measured only in a labelled lab block; the ready-made box changes only by Batt's word.

## Addendum 3 (written 2026-11-20 00:1x ICT, before any B2 data): what B2 carries

- B2 (`s11scr-1080f`) plays `feat/virtual-box-grab` as it stands, merged after block A ends:
  - a1ac2dee, the box-only virtual reads (addendum 1);
  - f65ff6dd, the fullscreen taskbar-absent bar 20 -> 10, in ro_agent's pause gate and the
    backend's key gate (see s11scr-1080's runs); the backend restarted to load it.
- Not in B2: C1 (not supported) and C2 (Batt's decision).
- The same judged lines as B, B2 against A. Reported, B2 against B: the cursor's "unknown" share,
  kills per box engagement, the hover time, the tick pace, the pauses.

## Runs

### s11scr-1080 (B), 2026-11-19 23:14 - 2026-11-20 00:00 ICT: 1 valid run of 3; the series STOPPED

- Main 3513eda2 + docs (the play code as pre-registered). The lab client was already at 1920x1080
  fullscreen (OptionInfo.lua 1920 / 1080 since 11-19 11:41). The Rogue Thief8fce (slot 3) was
  chosen at character select by judged steps; the relog cleared her immunity.
- **r01B**: rc 0, 19.9 min, the time box. 22 kills (packets) = 66.4 kills/h, 81.5 loot/h, 0 deaths.
  17 boss Fly Wings, 16 FALSE by the packet truth (addendum 2). 71,341 z/h net.
- **r02B**: played 22 min, then ended by the series' own Stop while paused.
  - The pauses: "the game off the screen", 3 in all, 4 s. The fullscreen taskbar box read 19.52,
    under the bar of 20, at one dark corner.
  - The session has no packets.jsonl.gz and no normal end record: not scoreable (found false).
- **r03B**: the setup's F5 (the dagger on) was refused `client_not_foreground`, for the same
  reason. The series STOPPED: a person first.
  - The Rogue stood unattended under a Cruiser (HP 42 %). The agent pressed the Fly Wing in an
    ASSIST desktop window, typed `@monsterignore` (read back "You are now immune to attacks"),
    and later typed it again ("Returned to normal state") before the next series.
- Probe (immune, moves only, 76 hovers): the same real frames with and without the cursor patch
  gave 0 / 0 alarm-class boxes, and 186 / 195 monster boxes. **C1 is not supported for alarms
  and is not adopted.**
- Probe (25 Fly Wing spots): the taskbar box read 33-181 in game at 1080 (median 89.4), and the
  shown taskbar 0.0-1.3. A fix candidate is on `feat/virtual-box-grab` (f65ff6dd: the bar
  20 -> 10); it is not in A or B.
- B is completed by **s11scr-1080b** (2 more runs, the same code), started 00:08:35.

### s11scr-1080b (B, completed), 2026-11-20 00:08-00:51 ICT: 2 valid runs

- The same code as s11scr-1080 (main; the play code unchanged since 3513eda2).
- **r01B**: 19.7 min, the time box, 0 deaths; 24 kills = 73.1 kills/h; 124.9 loot/h. 8 boss Fly
  Wings, 7 FALSE.
- **r02B**: 19.7 min, the time box, 0 deaths; 26 kills = 79.3 kills/h; 82.3 loot/h. 5 boss Fly
  Wings, 5 FALSE.
- B's valid runs: 66.4, 73.1 and 79.3 kills/h.

### The switch to A, 00:52-00:56 ICT

1. `ro_agent.py close`.
2. OptionInfo.lua 1920 / 1080 -> 1280 / 720 (OLD_* too), a byte-exact Latin-1 edit with a backup
   `OptionInfo.lua.bak-20261119-1080`, read back.
3. `.env` SESSION_SIZE 1280x720, GAME_REGION 0,0,1280,720, RO_SHORTCUT 37,568, SHELL_SHORTCUT
   112,568 (the desktop read at 720).
4. `recreate:desktop@60` and `recreate:backend@30`: ALL STEPS OK; ASSIST came back by itself.
5. `recover gm`: Thief8fce in game; the relog cleared the immunity.
6. s11scr-720 started 00:56:11 with the same box (project hash acc1ebb7...).

### s11scr-720 (A), 2026-11-20 00:56-01:55 ICT: 3 runs, 2 valid by the bar

- **r01A**: 19.8 min, 0 deaths; 40 kills = 121.5 kills/h; 130.6 loot/h. 8 boss Fly Wings, 5 false.
- **r02A**: 19.7 min, 0 deaths; 45 kills = 136.8 kills/h; 179.4 loot/h. 2 boss Fly Wings, 1 false.
- **r03A**: 14.4 min, 0 deaths; 32 kills = 133.7 kills/h.
  - It ended "relocate_no_block: she is on geffen": the runner's way home took her off the map.
  - That is not one of the bar's valid ends (home / weight_home), so the bar leaves it out.
  - Reported: counted, A is 130.7 kills/h, and nothing changes.
- The runner's records (diag), r01A:
  - the cursor read "sword" on 97.6 % of box targets; 62.5 % of targets struck;
  - 27 missed targets an hour;
  - 0.30 items picked per loot step (1080: 0.02), and 0.21 items seen by the item model per step
    (1080: 0.05-0.11).

### THE VERDICT (scored 2026-11-20 01:55 ICT, `screen_ab.py score --a s11scr-720 --b s11scr-1080`, B with s11scr-1080b's runs): WORSE

    line        A (720)          B (1080)        bar                      result
    deaths      0                0               B <= A                   PASS
    kills/h     129.2 +- 7.7     72.9 +- 3.7     diff -56.2 +- 8.5 >= -2 SE   FAIL
    loot/h      155.0 +- 24.4    96.2 +- 14.3    diff -58.8 +- 28.3 >= -2 SE  FAIL
    errors      0                0               none new in B            PASS
    valid runs  2 (of 3)         3 (of 5)

- Reported:
  - false boss Fly Wings: B 28 of 30 (three runs, about 59 min); A 6 of 10 (the two valid
    runs, about 39 min; with r03A, 6 of 11);
  - s10ab's B runs (11-17, before): 114.7-145.9 kills/h; Batt's bar: 228.5 kills/h.
- So at 1080 the bot kills 44 % fewer an hour. The causes, in the order of the time they cost:
  1. the false alarms (about 28 an hour, each a Fly Wing plus 30 s with no box engagement): both
     models see the shrunk 1080 world worse;
  2. the cursor reads (fixed in B2);
  3. the item model, which sees a third to a half of the items it sees at 720.

### s11scr-1080f (B2 = B + the read speed-up + the taskbar bar 10), 2026-11-20 02:01-02:49 ICT

- Main da68c941 (merged feat/virtual-box-grab); the backend recreated with the bar 10 (/health
  threshold 10.0); the switch back to 1080 done by the same steps, reversed.
- Every run ended with "stock_keep: 1 Fly Wing(s) left". The setup tops the Fly Wings up to 10
  (TOPUP), and the false alarms burned them.
- **r01B**: 9.2 min; 14 kills = 91.8 kills/h; 8 boss Fly Wings, 7 false. Not valid (under 16 min).
- **r02B**: 18.1 min; 23 kills = 76.3 kills/h; 9 boss Fly Wings, 7 false.
- **r03B**: 16.0 min; 26 kills = 97.5 kills/h; 8 boss Fly Wings, 8 false.
- **B2 against A:**
  - kills/h 86.9 +- 13.1 against 129.2 +- 7.7 (diff -42.3): FAIL;
  - loot/h 125.6 against 155.0 (diff -29.5 +- 26.2): PASS;
  - deaths 0 / 0 and errors 0 / 0: PASS.
  - Verdict: WORSE.
- **Reported, B2 against B:**
  - kills/h +19 % (72.9 -> 86.9); loot steps/h 96 -> 126;
  - the hover check 293-326 ms (B 460, A 254);
  - the cursor's "unknown" on box targets still 37-48 % (B 33-57 %, A 2 %);
  - kills per box engagement 0.35-0.38 (B 0.32, A ~0.7).
- **Probe (immune, standing, moves only, 40 hovers at 1080):** the sword read on 34 hovers, the
  first at a median of 110 ms (p90 112), all within 350 ms; 6 never in 1.5 s; the best sword
  recall median 0.872.
  - So the client draws the sword in time when she stands. The runs' "unknown" comes from play
    in motion, which the opt-in trace (`PORING_CURSOR_TRACE`, 77626cdf) measures in
    `s11scr-diag` (1 run, reported only).

### s11scr-diag (1 run at 1080, reported only), 2026-11-20 02:56-03:13 ICT

- Main 77626cdf with `PORING_CURSOR_TRACE` on; the Rogue not immune. 15.1 min of hunting, 24 kills
  = 95.4 kills/h; it ended "stock_keep: 1 Fly Wing(s) left" like every B2 run (9 escapes, 8 of
  them the goblin alarm: 31.8 an hour).
- The runner's own counts: the cursor on box targets sword 50 %, unknown 39 %, clear 11 %; on
  scan hovers clear 65 %, unknown 28 %, sword 5 %.
- **The trace, 589 checks** (sword 61, clear 280, unknown 248):
  - the first read comes a median 150 ms after the second motion (p90 157-167), and the reads
    are 49-50 ms apart, not 30: 3 reads by 250 ms, 5 by the 350 ms end;
  - sword checks: the sword (>= 0.75) shows first at a median 250 ms (p90 305), 54 % by 250 ms;
  - unknown checks see NEITHER cursor: the best sword read is a median 0.357 (151 of 248 under
    0.40, only 11 in 0.60-0.75), the best walk read a median 0.485 (86 in 0.60-0.85, 2 above);
    the sword rose by more than 0.1 inside the window in only 32 of 248;
  - unknown targets lie farther from the screen centre: a median 160 px (sword 62, clear 59);
  - 29 % of the reads 50 ms apart repeat the previous read exactly (the same frame): clear 41 %,
    unknown 24 %, sword 19 %. The RDP bus gave 14.5 frames/s with the Rogue standing after the
    run (10.3 on damage + 4.2 keepalives); no 720 figure in motion to compare yet.
- **What it says:** a longer cursor window would rescue few unknowns (11 near misses, 32
  rising). The unknown checks are far targets with no clear cursor in the crop at all, and the
  picture repeats often. Two leads, not yet measured: (a) the frame rate in motion at 1080
  against 720 (the bus counters during a run, both sizes); (b) when the cursor does show for a
  far target in motion (a reads-to-1 s probe; the runner's 0.35 s is byte-pinned, so a probe).
