---
doc_type: research
hypothesis: null
status: ACTIVE
role: null
verdict_date: null
verdict_ticket: null
supersedes: null
related: [demonstrations.md, adr/0007-packet-ground-truth-channel.md]
next_action: "Update after every round: the leaderboard, the round's table, what the agent's play taught and the next bot change."
---

# The three-way competition: Batt vs the agent vs the bot (Batt, 2026-10-17)

**Setup.** On prt_fild08, every competitor plays under the same conditions:
- natural spawns; the GM immune with high STR, its fixed state restored before each session;
- the same seeded start area in each round; mux ASSIST; the HUD as usual.

**The three competitors:**
- **BATT:** his recorded 10-minute demo (`20261016T093835-demo-human-demo`), the fixed human
  reference, pixels only.
- **AGENT:** Claude plays 10 minutes itself (`scripts/agent_play.py`, sessions tagged
  `agent-demo`).
  - It decides step by step from screenshots.
  - Its inputs go through the bot's own path and gates: the name tag before every attack click,
    the walk guard, the cursor gate.
  - **PACKET-ASSISTED** (ADR-0007 Amendment D, Batt's handicap for the agent only): it reads the
    sniffer's archive during play (monster positions and species, our cell, drops, deaths). Its
    numbers are therefore NOT a pixels-only reference.
- **BOT:** the current hunt-flow version, 45-60 min.
  - It is compared on its full run AND on its 10-min windows (`flow_judge.bot_windows`: the
    median and the best by kills / h).

The order alternates between rounds (round 0: bot first; round 1: agent first; round 2: bot
first; round 3: agent first).

**The judge is the same for all:** `flow_judge` from the packets offline. Hard bars (NPC contact,
non-target hit, map change) apply to every session.

## Leaderboard (kills / h; landing within 5 s; loot picked / dropped; hard bars)

| round | BATT (human, pixels) | AGENT (packet-assisted) | BOT median 10' | BOT best 10' | BOT full run |
|---|---|---|---|---|---|
| R0 (bot v20) | 300 / 100 % / 62 of 64 / - | 24.6 / 4 of 5 / 6 of 14 / pass | 120 / 80 % / 2 of 30 / pass | 192 / 90 % / 10 of 57 / pass | 140.9 / 85.2 % / 41 of 218 / 1 non-target |
| R1 (bot v21) | (fixed) | 38.3 / 4 of 5 / 4 of 6 / pass | 96 / 81 % / 4 of 25 / pass | 120 / 76 % / 6 of 30 / pass | 100.8 / 78.8 % / 34 of 156 / pass |
| R2 (bot v22) | (fixed) | 12.3 / 2 of 2 / 0 of 2 / pass | 126 / 75 % / 4 of 30 / pass | 138 / 84 % / 9 of 37 / pass | 123.5 / 80.0 % / 34 of 182 / pass |
| R3 (bot v23) | (fixed) | 25.6 / 4 of 4 / 5 of 13 / pass | 126 / 83 % / 9 of 19 / pass (2 windows: the lower) | 162 / 69 % / 11 of 55 / pass | 145.2 / 76.8 % / 29 of 94 / pass (25.7 min) |
| R4 (bot v24) | (fixed) | 62.0 / 10 of 10 / 10 of 20 / pass | 138 / 63 % / 5 of 34 / pass | 180 / 89 % / 19 of 35 / pass | 146.9 / 77.4 % / 83 of 219 / **1 non-target (Creamy)** |
| R5 (bot v25) | (fixed) | 40.1 / 6 of 6 / 7 of 14 / pass | 108 / 76 % / 15 of 23 / pass | 132 / 80 % / 14 of 23 / pass | 109.9 / 70.9 % / 81 of 131 / **1 non-target (Creamy)** |
| R6 (bot v26) | (fixed) | pending | pending | pending | pending |

## Round 0 (bot v20 from 2026-10-17 04:42 + 05:55; agent 07:55)

- **Sessions:**
  - AGENT `20261017T075512-demo-agent-demo` (seed 20261231, 10 min). Attempt 1,
    `20261017T074930`, was ended by me at 2.5 min: the tool's tag read did not follow a hopping
    Poring (6 of 7 reads empty). Fixed in 8278b7d.
  - BOT v20: `20261017T044222-demo-hunt-flow20` (60 min) and `20261017T055512-demo-hunt-flow20`
    (45 min). Ten 10-min windows, kills / h 102-192.

| metric | BATT | AGENT R0 (packet-assisted) | BOT median 10' | BOT best 10' | BOT full |
|---|---|---|---|---|---|
| kills / h | 300 | 24.6 | 120 | 192 | 140.9 |
| landing <= 5 s | 64/64 | 4/5 | 16/20 | 27/30 | 121/142 |
| seen -> click p50 / p90 s | 1.11 / 4.79 | 19.64 / 21.68 | 4.3 / 8.87 | 7.28 / 22.11 | 4.94 / 18.58 |
| death -> next click s | 1.24 / 1.8 | 27.2 / 39.9 | 1.75 / 9.53 | 4.32 / 7.56 | 4.27 / 9.34 |
| monsters in sight / 10 min | 44 | 10.3 | 27 | 32 | 16 (whole-run ruler; per window 28-30.5) |
| loot picked / dropped | 62 / 64 | 6 / 14 | 2 / 30 | 10 / 57 | 41 / 218 |
| kill -> last pickup s | 1.56 | 57.1 | 0.88 | 0.74 | 5.77 |
| walk clicks while moving | 72.7 % | 0 % | 55.1 % | 52.5 % | 57.4 % |
| click cadence s | 0.6 / 3.44 | 12.4 / 78.7 | 0.97 / 3.3 | 0.97 / 6.34 | 0.97 / 4.73 |
| reversals / min | 3.6 | 0.1 | 4.3 | 3.6 | 3.96 |
| straight run cells | 16.9 | 31.6 | 12.4 | 10.4 | 12.5 |
| unintended attack requests | - | 0 | 2 | 0 | 9 |
| hard bars (NPC / map / non-target) | - | 0/0/0 | 0/0/0 | 0/0/0 | 0/0/1 |

## Round 1 (agent first, 08:12; then bot v21, 08:58)

- **Sessions:**
  - AGENT `20261017T081204-demo-agent-demo` (seed 20270201, 10 min).
  - BOT v21 `20261017T085819-demo-hunt-flow21` (the same seed, 60 min; its attempt 1 was
    stopped at 24 min for a loot bug, demonstrations 3.62).

| metric | BATT | AGENT R1 (packet-assisted) | BOT v21 median 10' | BOT best 10' | BOT full |
|---|---|---|---|---|---|
| kills / h | 300 | 38.3 | 96 | 120 | 100.8 |
| landing <= 5 s | 64/64 | 4/5 | 13/16 | 16/21 | 89/113 |
| seen -> click p50 / p90 s | 1.11 / 4.79 | 9.77 / 15.89 | 5.46 / 12.14 | 3.74 / 8.34 | 4.93 / 13.19 |
| death -> next click s | 1.24 / 1.8 | 26.2 / 30.2 | 3.11 / 11.68 | 5.32 / 12.1 | 4.42 / 11.26 |
| monsters in sight / 10 min | 44 | 11.7 | 29 | 30 | 28.5 (windowed) |
| loot picked / dropped | 62 / 64 | 4 / 6 | 4 / 25 | 6 / 30 | 34 / 156 |
| kill -> last pickup s | 1.56 | 26.3 | 0.93 | 5.52 | 6.22 |
| walk clicks while moving | 72.7 % | 11.5 % | 63.2 % | 44.7 % | 58.8 % |
| click cadence s | 0.6 / 3.44 | 11.4 / 55.9 | 0.97 / 2.74 | 1.0 / 6.33 | 0.97 / 4.22 |
| reversals / min | 3.6 | 0.11 | 8.2 | 3.7 | 4.93 |
| straight run cells | 16.9 | 26.8 | 11.8 | 10.9 | 12.3 |
| unintended attack requests | - | 1 | 1 | 3 | 8 |
| hard bars (NPC / map / non-target) | - | 0/0/0 | 0/0/0 | 0/0/0 | 0/0/0 |

- **What the agent did that the bot did not, and the reverse (round 1):**
  - **Looted what it SAW**, at the GM's feet, by hovering the visible item sprites (4 of 6).
    v21's frame difference missed exactly those (melee drops land at the GM's feet, and its false
    blobs sit on the GM's own animated sprite).
    - **Candidate:** recognise the item sprites themselves (a subagent is building item-icon
      templates from packet-labelled recordings).
  - **Uncovered monsters under the UI windows** (a Lunatic under the inventory window, twice) by
    walking so they came out. The bot loses them.
  - The bot clicks ~10x faster, at a ~1 s cadence, from a moving GM.

## Round 2 (bot v22 first, 10:02; then the agent, 11:22)

- **Sessions:**
  - BOT v22 `20261017T100214-demo-hunt-flow22` (seed 20270301, 60 min; demonstrations 3.63).
  - AGENT `20261017T112240-demo-agent-demo` (the same seed, 10 min).

| metric | BATT | AGENT R2 (packet-assisted) | BOT v22 median 10' | BOT best 10' | BOT full |
|---|---|---|---|---|---|
| kills / h | 300 | 12.3 | 126 | 138 | 123.5 |
| landing <= 5 s | 64/64 | 2/2 | 15/20 | 21/25 | 108/135 |
| seen -> click p50 / p90 s | 1.11 / 4.79 | 19.53 / 20.77 | 2.69 / 9.65 | 3.46 / 19.78 | 3.58 / 11.37 |
| death -> next click s | 1.24 / 1.8 | 19.0 / 19.0 | 2.32 / 10.69 | 3.46 / 7.93 | 3.86 / 10.03 |
| monsters in sight / 10 min | 44 | 3.1 | 24 | 32 | 29 (windowed) |
| loot picked / dropped | 62 / 64 | 0 / 2 | 4 / 30 | 9 / 37 | 34 / 182 |
| kill -> last pickup s | 1.56 | - | 11.12 | 4.66 | 7.39 |
| walk clicks while moving | 72.7 % | 7.1 % | 53.9 % | 55.2 % | 56.5 % |
| click cadence s | 0.6 / 3.44 | 11.2 / 28.6 | 0.97 / 3.17 | 0.97 / 2.93 | 0.97 / 5.14 |
| reversals / min | 3.6 | 0.61 | 6.5 | 4.0 | 5.6 |
| straight run cells | 16.9 | 35.0 | 13.6 | 14.8 | 13.5 |
| unintended attack requests | - | 0 | 5 | 1 | 10 |
| hard bars (NPC / map / non-target) | - | 0/0/0 | 0/0/0 | 0/0/0 | 0/0/0 |

- **What the agent did vs the bot (round 2):**
  - **The agent met almost nothing: 3.1 monsters in sight per 10 min, against the bot's 24-32
    per window on the same seed.**
    - It moves far slower: every walk click from a standstill waits ~3 s for the cursor gate,
      and its steps are 10-20 s apart.
    - It walked into two dead ends (a cliff pocket and a plateau edge) and spent ~2 min getting
      out.
  - The bot's ~1 s cadence and continuous walking are worth ~10x more ground than the agent's
    judgment here.

## Round 3 (agent first, 11:37; then bot v23, 11:57)

- **Sessions:**
  - AGENT `20261017T113727-demo-agent-demo` (seed 20270401, 10 min).
  - BOT v23 (Batt's fixed loot workflow, demonstrations 3.64), the same seed:
    - attempt 1 `20261017T114911-demo-hunt-flow23`, stopped by me at 296 s (5 of 11 kills looted,
      0.7 s a click; fixed in fc41aa5);
    - attempt 2 `20261017T115719-demo-hunt-flow23` stopped ITSELF at 25.7 min: a pre-existing
      off-frame pointer move (read_tag's pre-motion at the top edge). Fixed in v24 (f4a8ebe).
      Two full 10-min windows.

| metric | BATT | AGENT R3 (packet-assisted) | BOT v23 lower 10' | BOT best 10' | BOT full (25.7 min) |
|---|---|---|---|---|---|
| kills / h | 300 | 25.6 | 126 | 162 | 145.2 |
| landing <= 5 s | 64/64 | 4/4 | 19/23 | 22/32 | 53/69 |
| seen -> click p50 / p90 s | 1.11 / 4.79 | 19.47 / 23.29 | 4.17 / 13.3 | 12.61 / 27.81 | 7.3 / 23.56 |
| death -> next click s | 1.24 / 1.8 | 16.0 / 36.3 | 0.53 / 2.6 | 0.61 / 2.61 | 0.56 / 2.84 |
| monsters in sight / 10 min | 44 | 7.5 | 38 | 33 | 35.5 (windowed) |
| loot picked / dropped | 62 / 64 | 5 / 13 | 9 / 19 | 11 / 55 | 29 / 94 |
| kill -> last pickup s | 1.56 | 50.9 | 1.98 | 2.23 | 2.79 |
| walk clicks while moving | 72.7 % | 7.4 % | 55.7 % | 49.4 % | 48.1 % |
| click cadence s | 0.6 / 3.44 | 13.2 / 33.3 | 0.96 / 3.84 | 0.97 / 4.8 | 0.97 / 5.2 |
| reversals / min | 3.6 | 0.32 | 6.8 | 6.9 | 6.56 |
| straight run cells | 16.9 | 34.8 | 12.8 | 10.3 | 11.2 |
| unintended attack requests | - | 0 | 0 | 0 | 0 |
| hard bars (NPC / map / non-target) | - | 0/0/0 | 0/0/0 | 0/0/0 | 0/0/0 |

- "death -> next click" now counts v23's loot clicks as the next click, so it is not comparable
  with earlier rounds.
- **What the agent did vs the bot (round 3):**
  - **Loot:** after a Drops kill the agent SAW 4+ items at the GM's feet and picked 4 by clicking
    them. v23's blind fixed clicks went to the wrong death cell: offline, its first loot click
    lay p50 50 px from the nearest drop, while the bot's own last strike click lay 10-16 px from
    it. That is v24's change.
  - **Landing:** the agent struck only targets standing next to the GM (4 of 4). The bot strikes
    from up to 7 cells at a 0.55 s-old box (76.8 %).
  - **Sight:** the agent met 7.5 monsters per 10 min, the bot 35.5. The agent's slow steps and
    two dead ends (a cliff pocket, a plateau) cost it most of its 10 minutes again.
- **Bot v23 vs v22:** best window 162 kills / h (the bot's best so far); 0 unintended attacks
  (v22 10); loot 30.9 % (v22 18.7 %); kill -> last pickup 2.79 s (v22 7.39 s). But seen ->
  click got slower (7.3 s vs 3.58 s): monsters seen during the 4 s loot step wait for it.

## Round 4 (bot v24 first, 12:30; then the agent, 13:37)

- **Sessions:**
  - BOT v24 `20261017T123018-demo-hunt-flow24` (seed 20270501, 60 min; demonstrations 3.65).
  - AGENT `20261017T133721-demo-agent-demo` (the same seed, 10 min).

| metric | BATT | AGENT R4 (packet-assisted) | BOT v24 median 10' | BOT best 10' | BOT full |
|---|---|---|---|---|---|
| kills / h | 300 | 62.0 | 138 | 180 | 146.9 |
| landing <= 5 s | 64/64 | 10/10 | 12/19 | 25/28 | 113/146 |
| seen -> click p50 / p90 s | 1.11 / 4.79 | 12.04 / 14.24 | 5.89 / 17.94 | 3.63 / 11.15 | 4.21 / 14.18 |
| death -> next click s | 1.24 / 1.8 | 15.8 / 23.4 | 2.18 / 3.83 | 2.56 / 5.67 | 2.39 / 5.67 |
| monsters in sight / 10 min | 44 | 11.4 | 32 | 40 | 37 (windowed) |
| loot picked / dropped | 62 / 64 | 10 / 20 | 5 / 34 | 19 / 35 | 83 / 219 |
| kill -> last pickup s | 1.56 | 32.2 | 2.8 | 3.56 | 3.63 |
| walk clicks while moving | 72.7 % | 0 % | 55.3 % | 46.7 % | 50.3 % |
| click cadence s | 0.6 / 3.44 | 28.2 / 81.2 | 0.96 / 3.98 | 0.96 / 5.45 | 0.96 / 4.14 |
| reversals / min | 3.6 | 0.62 | 7.5 | 6.3 | 6.94 |
| straight run cells | 16.9 | 17.6 | 11.8 | 10.8 | 11.3 |
| unintended attack requests | - | 0 | 5 | 2 | 14 |
| hard bars (NPC / map / non-target) | - | 0/0/0 | 0/0/0 | 0/0/0 | **0/0/1** |

- **The bot's hard bar:** a fast Creamy flew under the resting pointer just as a walk click was
  sent, and the client resolved the walk click as an attack on it (demonstrations 3.65).
  - The walk guard (no pink within 80 px, no box within 60 px) saw nothing.
  - Blind clicks (walk and loot) cannot see an unboxed, unpink Creamy. This is the open safety
    problem.
- **The agent's best round:** 10 kills, 10 of 10 landed, and 10 of 20 drops picked by eye.
  - **A new packet fact: Porings LOOT.** A Poring hopped onto two of our drops and they vanished;
    killing it dropped them again with its own.
    - From pixels: items that vanish while a Poring sits on them. For the bot, the lesson is loot
      speed.

## Round 5 (agent first, 13:50; then bot v25, 14:02)

- **Sessions:**
  - AGENT `20261017T135011-demo-agent-demo` (seed 20270601, 10 min): 6 kills, 6 of 6 landed,
    7 of 14 drops, hard bars passed.
  - BOT v25 `20261017T140228-demo-hunt-flow25` (the same seed, 60 min; demonstrations 3.66).

| metric | BATT | AGENT R5 (packet-assisted) | BOT v25 median 10' | BOT best 10' | BOT full |
|---|---|---|---|---|---|
| kills / h | 300 | 40.1 | 108 | 132 | 109.9 |
| landing <= 5 s | 64/64 | 6/6 | 16/21 | 16/20 | 90/127 |
| seen -> click p50 / p90 s | 1.11 / 4.79 | 13.5 / 29.6 | 2.45 / 8.04 | 3.18 / 8.5 | 4.26 / 11.04 |
| death -> next click s | 1.24 / 1.8 | 20.8 / 21.9 | 3.33 / 6.45 | 2.32 / 4.72 | 2.51 / 6.02 |
| monsters in sight / 10 min | 44 | 7.8 | 29 | 37 | 30 (windowed) |
| loot picked / dropped | 62 / 64 | 7 / 14 | 15 / 23 | 14 / 23 | 81 / 131 |
| kill -> last pickup s | 1.56 | 24.6 | 4.94 | 3.45 | 4.08 |
| walk clicks while moving | 72.7 % | 16.7 % | 58.2 % | 53.2 % | 50.5 % |
| click cadence s | 0.6 / 3.44 | 11.5 / 37.4 | 0.96 / 2.14 | 0.96 / 2.45 | 0.96 / 2.59 |
| reversals / min | 3.6 | 0.56 | 7.1 | 6.7 | 6.96 |
| straight run cells | 16.9 | 21.6 | 12.8 | 14.2 | 12.9 |
| unintended attack requests | - | 0 | 1 | 5 | 13 |
| hard bars (NPC / map / non-target) | - | 0/0/0 | 0/0/0 | 0/0/0 | **0/0/1** |

- **The bot's loot reached 61.8 %** (v24 37.9 %). Loot clicks that became an attack fell from 10
  to 2 with the 70 px margin.
- **Another Creamy from a walk click** (not from v25's tag skip). v26 rests the pointer on the
  UI after every walk click: the hypothesis is that the client attacks a monster that comes
  under the RESTING pointer.
- **The agent:** 6 kills. Again its movement is the limit (7.8 monsters in sight per 10 min).

## What the agent's play taught (rounds 0-5)

- **The agent's own limit is its decision loop.**
  - Each step is a screenshot, a thought and a command: ~10-20 s.
  - So it is far slower than the bot (seen -> click 9.8-19.6 s against 4.3 s) and kills
    25-38 / h.
  - It wins where judgment, not speed, counts: long straight runs (27-32 cells, 0.1 reversals /
    min, against the bot's 12 / ~4) and looting what it SEES.
- **Packet facts that changed the agent's decisions, and whether pixels could give them:**
  1. **A monster behind the inventory or chat window** (on screen under the UI). Packets gave its
     cell; the agent walked so it came out from under the UI, then struck it.
     - From pixels: the bot loses a track that walks under a window. It could keep the track and
       step to uncover it (a candidate change).
  2. **A monster that left the view.** Packets kept its last cell, and the agent followed it.
     - From pixels: the bot's tracks die at the screen edge. Remembering the last heading of a
       track that left the view is pixel-feasible.
  3. **"Dead" before the next look.** Packets showed the death at once, so the agent moved on.
     - From pixels: the bot's "dead" is decided from the box vanishing after >= 1.4 s (v15).
       The client's attack arrow and damage numbers are pixel cues for an earlier decision.
  4. **Drops.**
     - The packets' floor-item list was unreliable in the tool: unordered shards, fixed in
       7dfc469. The agent looted by EYE instead: the dropped items are small sprites right next
       to the GM, clearly visible.
     - From pixels: yes. That is the bot's next change, v21, loot by frame difference.
  5. **(R2) Our OWN cell from packets lags during walks.**
     - The packets' "me" moves only with the walk packets, so a projected monster pixel was off
       by several cells while the GM walked. The agent struck a Lunatic from the SCREEN instead.
     - From pixels: the bot's position (minimap + floor odometry) does not have this lag. The
       packet edge is the monster positions, not ours.
  6. **(R2, R3) A monster just below or behind the view** (a Poring 14 cells south; a Drops and a
     Lunatic left behind while the GM walked on).
     - Packets kept their cells, and the agent turned back for them.
     - From pixels: the belief map (merged 8268666) keeps a track that left the view. Offline,
       its off-screen belief is within 1 cell 70-82 % of the time at 1-5 s: a walk-toward target.
  7. **(R3) Drops at the GM's feet.** A Drops' kill left 4+ items next to the GM. The tool's
     packet item list showed fewer than were there, and the agent looted by EYE: 4 picked, by
     clicking what lay at the feet.
     - This is Batt's method, and v23's fixed loot does it blind on the 3 x 3.
  8. **(R3) A monster hopped INTO the drop pile.** Its box made the agent's loot clicks refuse
     (`unit_near`). The agent killed it first, then looted.
     - The bot's v23 rule is the same: a loot cell near a monster box is skipped, and the monster
       becomes the next engagement.
- **What the bot does that the agent could not:**
  - it clicks while moving, at ~1 s cadence;
  - it reacts in ~4 s;
  - it keeps at it for 60 minutes without a 15 s pause between steps.
- **Tool lessons (agent side):**
  - a strike during the GM's walk reads no tag: the camera scrolls the sprite off the pointer.
    The strike now waits for the GM to stop;
  - a loot click right before a walk click can be cancelled by the walk;
  - the walk guard counted the client's own red no-entry cursor as pink. The agent tool and the
    bot from v21 now leave the pointer out.

## The search gap (bot work order item 2; offline study, `scripts/search_gap.py`, merged f70b417)

**Batt's question:** why does the bot see 13-19 monsters per 10 min where he saw 44?

**Answer:**
- **Half of it was the ruler, not the bot.**
  - rAthena keeps a spawn slot's block id across respawns. So the bot's whole-run count of
    distinct gids, divided by 6, stops growing at the 82-103 mobs met.
  - Per 10-min window (Batt's own basis) the bot meets 27.5 (median; 24-30.5 per run, best
    windows 40-46).
  - The judge now reports the windowed median (`flow_judge.sight_windowed`, 7114e00).
- **Of what is left (x0.62):**
  - **area swept per 10 min: x0.63.** Moving share x0.85; ground swept per cell walked x0.78
    (Batt 22.1, the bot 17.2: more overlap, turning back, shorter net displacement: 59 cells net a
    minute vs Batt's 91). The walk speed is the same.
  - density met per swept cell: x1.07, a wash.
  - **detector recall: no part of it.** Mobs boxed at least once per window 91 % (Batt's session
    98 %); recall is flat by ring. But CREAMY recall is 11 %: a safety point, not a sight one.
- **Where the time goes:**
  - Batt's standing is fighting and looting (0.22 + 0.17).
  - The bot's standing is dead time: next to a mob 0.29 vs 0.11, with nothing in view 0.14 vs
    0.04. It is reads, parks and loot sweeps that pick nothing up.
- **So the search change is sweep GEOMETRY + less non-fight standing:**
  - long straight legs;
  - targets taken in passing;
  - resume the heading without walking back;
  - a coverage memory of the bot's own path, to head away from ground swept in the last minutes;
  - turn rather than reverse at obstacles.

## The next bot change

**v24 (running, round 4): the fixed loot's DEATH CELL** (demonstrations 3.65).
- The cell under the last strike click when it is beside the GM, else the GM's neighbour toward
  it. Offline (340 drops): 63 % of drops in its 3 x 3, 87 % within 2 cells.
- Plus the cadence v23 registered (~0.4 s a click) and `FrameGuard` (no input off the frame).

**Then (work order item 3, the NAME TAG):**
- v23's species shadow was sure on 37 % of the tag reads, agreed with the tag on 37 of 38, and
  disagreed once, on a CROWDED box (the tag Lunatic, the check Drops).
- 19 times it was sure where the tag read nothing.
- **v25 candidate:** skip the tag when the check is sure AND no other monster box is within
  50 px, and start the read while walking in.

**Measured top losers (v22, seconds per hour):**
- server kill -> the bot's "dead", including the loot step: 508;
- selection -> click: 423;
- "dead" -> the next selection: 337;
- in range -> click: 260;
- click -> server kill: 250.
