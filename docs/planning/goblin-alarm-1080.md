---
doc_type: plan
status: ACTIVE
role: null
verdict_date: null
verdict_ticket: null
supersedes: null
related: [xmas02-1080-detector.md, screen-size-ab.md, cursor-1080.md, xmas02-items-1080.md, roles-not-names.md, ../../scripts/dungeon_hunt.py, ../../scripts/flow_play.py, ../../scripts/stage9_ab.py]
next_action: "The held-out replay (section 5) once the item chain's later pilots have shipped; the play bar after the cursor round's (Batt's order)."
title: "The false alarms at 1920x1080: the fight's neighbour read as a Christmas Goblin (pre-registration)"
date: 2026-11-21
owner: Batt
---

# The false alarms at 1080 (pre-registration, 2026-11-21 00:37 ICT from `date`)

Written before any record of the held-out pilots (section 5) was read. Nothing below is edited
after its commit, except by a labelled, clock-stamped amendment (section 9).

## 0. What Batt asked

- 2026-11-20 ~21:1x: the order is the item model at 1080, the cursor at 1080, then **the false
  goblin alarms**; "long".
- He set the alarm's confirm to 3 on live himself (the garm_confirm block).
- 8c (xmas02-1080-detector.md Amendment 23): 12 of B's 14 false boss Fly Wings were
  g_gobline_xmas boxes; 21.4 false flies an hour at 1080 against 9.1 at 720. The model fired 0 /
  400 times on the held-outs' alarm-free frames: the false sightings come from play frames.

## 1. The facts (the FIT pilots: ifT1, ifT2, ifH1, ifT3 of the item chain, 91.2 min of play)

- The four pilots are 1080 natural-drop play runs (screen_ab.py run, xmas02v1080, stage2_ab's
  setup, not immune, the lab sniffer on). Their play records only were read here (the runner's
  events and the packets); ifH1's frames and item labels stay untouched (the item round's
  held-out).
- `screen_ab.py score --a s11scr-720 --b ifT1-play+ifT2-play+ifH1-play+ifT3-play --json
  --no-econ-update`: 29 alarm Fly Wings; by the packets (stage9_ab.Truth: no alarm-species unit
  on screen, not after a vanish) **23 false (15.1 an hour), 21 of them g_gobline_xmas**, 2
  garm_baby (each within 3 s after a true Garm Baby fly). The same score: kills/h 113.3 +- 1.0
  (49.6 % of Batt's 228.5).
- Each false goblin alarm's sighting (the runner's garm_seen record: its box, score, streak,
  mode) against the packets' world at that time (Timeline, FRAME_LAG_S 0.12 s earlier, the
  runner's camera; `gob_cause.py`, scratch, output sha256 `2f69fe5e628936ac...`):
  - 17 of the 21 have a box record (4 flew from the latch with no record kept);
  - **all 17 lie within 40 px of a real monster ONE cell from her** (Chebyshev 1): Myst Case
    (1249) 13 times, Christmas Cookie (1246) 4 times;
  - 16 of 17 in mode "fight", 1 "search";
  - her body's point (FOOT_PX raised by BODY_UP: 641, 336) within 40 px of the box centre: 10 of
    17; within 60 px: 16 of 17 (the 17th: 137 px, a Cookie four cells away);
  - their scores 0.269-0.785 (none >= 0.80); the boxes 35-68 x 50-89 px;
  - the true alarms (6 sightings with a record): 333-519 px from her body point, scores
    0.824-0.963.
- So **the false goblin is her fight's neighbour, overlapping her sprite in the 1080 picture,
  read as an alarm class**. xmas02v1080's 1080 training frames came from immune lattice watches
  (she stands, nothing fights her), so fights at 1080 are outside its training.

## 2. The question this round answers

Can a rule outside the pinned runner, naming no monster, stop these false alarms without losing a
true one, and does play at 1080 gain from it?

## 3. The fix candidates

- **A, the near-her rule (chosen first):** an alarm box whose centre lies within NEAR_PX of her
  body's point passes the alarm only at a score >= NEAR_SOLO; every other box as today.
  - NEAR_PX = 60, NEAR_SOLO = 0.85, set on the FIT pilots above (16 of 17 false sightings inside
    60 px, the highest false score 0.785, the lowest true score 0.824 far away).
  - It names no monster (roles-not-names): it applies to every alarm class of the box's model. A
    real alarm monster beside her still flies at a high score, and her HP's own Fly Wing rules
    stay as they are.
  - Built as a Run-time patch in flow_play (like role_alarm), on dungeon_hunt.alarm_seen (called
    by name); the runner file stays byte-identical. The same patch for screen_ab's B arm.
- B, hard negatives: 1080 fight frames (packet-labelled) in the next monster model round. Only if
  A fails its bars, or as that round's own item.
- C, the confirm streak: Batt's 3. Reported beside A in the replay, not chosen here.

## 4. The tool

- `scripts/alarm_replay.py` (offline, tests first): per runner session, the alarm feed rebuilt
  from detections.jsonl and detections_hud.jsonl in grab order (the runner's alarm_streak and
  alarm_seen, its own need / solo from the session's start record), under today's rule, rule A,
  and confirm 3;
  - an EPISODE: a qualifying detection with none in the 2 s before it;
  - each episode judged by the packets (stage9_ab.Truth.units_at; post-vanish windows excluded as
    S7.1): false (no alarm-species unit on screen) or true.

## 5. The held-out replay (scored once)

- The held-out: the item chain's pilots after the FIT ones: ifT4, ifT5, ifH2, ifT6, ifT7, ifT8,
  ifT9, ifT10 (every one that shipped; a pilot that did not is reported, not replaced).
- Bars, rule A against today's rule:
  - false episodes an hour: A <= 30 % of today's;
  - true episodes: none lost whose unit is >= 2 cells from her; any lost one is reported with its
    distance and score;
  - reported: confirm 3 beside them; the false episodes by class and by the nearest unit's job.

## 6. The play bar (after the cursor round's play, Batt's order; screen_ab.py, 3 valid runs a side)

- A = today's code, B = rule A; both at 1080, xmas02v1080, stage2_ab's setup, not immune.
- false boss Fly Wings / h: B lower than A by more than 2 SE (Poisson);
- kills/h: mean(B) - mean(A) >= -2 SE; deaths B <= A; no new errors.
- Reported: kills/h as a % of Batt's 228.5 (his 56.5 % line), Fly Wings / h by kind, z/h.

## 7. Not in this round

- The cursor at 1080 (its own round, before this one's play).
- Hunt 3 of Batt's live Run 11202100 (position unread, 31 idle Fly Wings): a position question.

## 8. The order

1. alarm_replay.py with tests, offline (now; the lab is the item chain's until ~04:30).
2. The held-out replay once the later pilots have shipped.
3. The flow_play patch with tests, merged between blocks.
4. The play bar, after the cursor round's.

## 9. RESULTS and AMENDMENTS (clock-labelled)

### Amendment 1 (2026-11-21 00:42 ICT from `date`): the replay tool built; its check on the FIT pilots

- `scripts/alarm_replay.py` (branch goblin-alarm, 9 tests; merged after the item chain with the
  flow_play patch's branch, no code change on main while the chain runs).
- **A slip, fixed before any held-out read:** the first FIT run read no start record (the
  runner's first record is `run_start`, the tool asked for `hunt_run_start`) and fell back to
  defaults in silence (garm_baby only, no solo): 5 episodes. The tool now refuses a session
  without its start record (a test).
- **The FIT pilots** (ifT1, ifT2, ifH1, ifT3; 1.526 h; the parameters were set on them, so this
  checks the tool, not the rule; `replay-fit.json` sha256 `0e91a003a39a631a...`):

  | rule | episodes | false | false / h | true | true lost |
  |---|---|---|---|---|---|
  | today (need 2, solo 0.7, the HUD twin fed) | 28 | 22 (all g_gobline_xmas) | 14.41 | 6 | - |
  | A, near-her | 8 | 1 | 0.66 | 7 | 0 |
  | confirm 3 | 13 | 6 | 3.93 | 7 | 0 |

  - today's 22 false episodes: the nearest unit Myst Case (1249) 15, Christmas Cookie (1246) 6,
    1265 once; the score's own count was 23 false flies (21 goblin), so the replay matches it.
  - A and confirm 3 show 7 true episodes where today shows 6: a false near sighting just before a
    true far one joins them into one episode under today's rule.
- The held-out (section 5) is unchanged: ifT4, ifT5, ifH2, ifT6..ifT10.

### Amendment 2 (2026-11-21 01:01 ICT from `date`): rule A built as the player's settings, OFF by default

- Built ahead of the held-out verdict, on branch goblin-alarm, NOT merged (it merges only if
  section 5 passes; the play bar sets it per arm):
  - two OPTIONAL setting blocks in the safety tab: `alarm_near_px` (0-200 px, step 5; **default
    0 = off**, today's alarm) and `alarm_near_score` (0.50-1.00; default 0.85; in use only
    while alarm_near_px is above 0), both needing garm_fly;
  - a new Field attribute `player`: the live player applies the setting, never a runner flag
    nor a --tune constant (the runner is byte-pinned); argv() skips it;
  - `flow_play.near_alarm`: for the hunt core's run, dungeon_hunt.alarm_seen (looked up by name
    at each of its three call sites) is given only the boxes `near_keeps` keeps; the streak and
    the rest of the rule are the runner's; restored after;
  - the ready-made boxes and their fixtures are unchanged (optional blocks are held only when a
    person sets them).
- Tests: test_live_player (off by default, off with the alarm off, the rule, restored, applied by
  the hunt core), test_flow_config / test_flow_run / test_settings_blocks pins, the frontend's
  registry test (130 blocks; run in frontend-dev after the merge), settings.gen.ts regenerated;
  mypy strict clean on settings.py.
- When its bars pass, the default becomes 60 by its own amendment and Batt's report.
