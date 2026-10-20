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
| R6 (bot v26) | (fixed) | 40.0 / 6 of 6 / 3 of 7 / pass | 120 / 87 % / 20 of 26 / pass | 126 / 83 % / 18 of 40 / pass | 129.1 / 85.4 % / 68 of 122 / **pass** (39.8 min) |
| R7 (bot v27) | (fixed) | 41.5 / 6 of 8 / 6 of 8 / pass | 78 / 67 % / 8 of 11 / **1 non-target** (2 windows: the lower) | 168 / 79 % / 21 of 38 / pass | 141.7 / 75.7 % / 52 of 109 / **1 non-target (Creamy)** (28.8 min) |
| R8 (bot v28) | (fixed) | 19.2 / 3 of 4 / 1 of 2 / pass | 144 / 80 % / 19 of 40 / pass | 156 / 72 % / 15 of 31 / pass | **141.9 / 75.3 % / 95 of 179 / pass (full hour)** |
| R8b (bot v29, A/B/C run 1) | (fixed) | - (bot only) | 132 (median of 6) | 156 | 131.9 / 73.6 % / 47 % / pass (full hour) |
| R9 (bot v30, A/B/C run 2) | (fixed) | **66.5 / 10 of 10 / 11 of 20 / pass** (the agent's best) | 114 | 144 | 105.0 / 78.0 % / 49 % / pass (full hour) |
| R10 (bot v31, death cell + A/B/C run 3) | (fixed) | 33.7 / 4 of 4 / 2 of 2 / pass | 99 | 114 | 101.3 / 84.6 % / 58.5 % / pass (45 min) |
| R11 (bot v34 run 2, paced-input blocks; overnight) | (fixed) | 37.2 / 6 of 6 / 5 of 6 / pass | 135 (median of 6 blocks) | 156.5 | 133.6 / 76.5 % / 63.0 % / pass (1 Creamy counted apart) |
| R12 (bot v36, loot retry; overnight) | (fixed) | 19.1 / 3 of 3 / 5 of 6 / pass | - | 12 kills in the best 2 min | 188.8 / 81.9 % / 61.2 % / pass |

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

## Round 6 (bot v26 first, 15:06; then the agent, 15:56)

- **Sessions:**
  - BOT v26 `20261017T150635-demo-hunt-flow26` (seed 20270701; demonstrations 3.67). It stopped
    itself at 39.8 min on a steering deadlock (fixed for v27).
  - AGENT `20261017T155609-demo-agent-demo` (the same seed, 10 min). Its first two starts were
    stopped safely before any input: **the game client had frozen** (no redraw on pointer moves;
    the chat input would not open). Recovered with `ro_agent.py recover gm` at 15:54; immunity
    re-sent and confirmed for the new login (15:55).

| metric | BATT | AGENT R6 (packet-assisted) | BOT v26 median 10' | BOT best 10' | BOT full (39.8 min) |
|---|---|---|---|---|---|
| kills / h | 300 | 40.0 | 120 | 126 | 129.1 |
| landing <= 5 s | 64/64 | 6/6 | 20/23 | 19/23 | 76/89 |
| seen -> click p50 / p90 s | 1.11 / 4.79 | 12.28 / 20.04 | 2.32 / 13.84 | 2.69 / 11.04 | 3.16 / 11.22 |
| death -> next click s | 1.24 / 1.8 | 21.9 / 28.1 | 2.59 / 5.83 | 2.79 / 5.49 | 2.59 / 5.7 |
| monsters in sight / 10 min | 44 | 7.8 | 28 | 30 | 30 (windowed) |
| loot picked / dropped | 62 / 64 | 3 / 7 | 20 / 26 | 18 / 40 | 68 / 122 |
| kill -> last pickup s | 1.56 | 18.0 | 3.68 | 4.59 | 4.31 |
| walk clicks while moving | 72.7 % | 7.7 % | 38.4 % | 48.2 % | 46.5 % |
| click cadence s | 0.6 / 3.44 | 11.9 / 44.4 | 1.01 / 4.31 | 1.01 / 2.29 | 1.01 / 2.77 |
| reversals / min | 3.6 | 0.44 | 5.6 | 6.9 | 7.12 |
| straight run cells | 16.9 | 22.2 | 12.7 | 12.9 | 12.2 |
| unintended attack requests | - | 0 | 1 | 2 | 4 |
| hard bars (NPC / map / non-target) | - | 0/0/0 | 0/0/0 | 0/0/0 | **0/0/0** |

- **The bot's first clean run since v23**, with the best landing of the day (85.4 %). Its median
  10-min window has 20 of 26 drops picked (77 %).
- The pointer rest (v26) halved the walk-click attacks. 40 minutes do not prove it.
- **The agent:** a Poring hopped under the chat window; the agent walked so it came out, then
  killed it (round 1's packet fact again). It also stayed away from a **warp portal** that the
  packets showed near the map edge.

## Round 7 (agent first, 16:09; then bot v27, 16:21)

- **Sessions:**
  - AGENT `20261017T160915-demo-agent-demo` (seed 20270801, 10 min): 6 kills, 6 of 8 drops,
    clean.
  - BOT v27 `20261017T162100-demo-hunt-flow27` (the same seed; Battleship, demonstrations 3.68).
    I stopped it at 28.8 min: my live monitor saw a Creamy hit.

| metric | BATT | AGENT R7 (packet-assisted) | BOT v27 lower 10' | BOT best 10' | BOT full (28.8 min) |
|---|---|---|---|---|---|
| kills / h | 300 | 41.5 | 78 | 168 | 141.7 |
| landing <= 5 s | 64/64 | 6/8 | 12/18 | 23/29 | 56/74 |
| seen -> click p50 / p90 s | 1.11 / 4.79 | 18.64 / 29.84 | 3.39 / 10.96 | 2.26 / 7.82 | 3.13 / 10.96 |
| death -> next click s | 1.24 / 1.8 | 15.4 / 17.9 | 3.77 / 6.0 | 2.35 / 4.26 | 2.48 / 5.44 |
| monsters in sight / 10 min | 44 | 8.1 | 18 | 30 | 24 (windowed) |
| loot picked / dropped | 62 / 64 | 6 / 8 | 8 / 11 | 21 / 38 | 52 / 109 |
| kill -> last pickup s | 1.56 | 35.3 | 3.38 | 3.88 | 4.09 |
| walk clicks while moving | 72.7 % | 32.1 % | 52.7 % | 49.6 % | 48.4 % |
| click cadence s | 0.6 / 3.44 | 11.6 / 47.0 | 1.01 / 1.48 | 1.0 / 3.61 | 1.01 / 2.86 |
| reversals / min | 3.6 | 0.92 | 5.8 | 6.8 | 6.15 |
| straight run cells | 16.9 | 22.4 | 14.3 | 11.3 | 12.6 |
| unintended attack requests | - | 0 | 1 | 1 | 2 |
| hard bars (NPC / map / non-target) | - | 0/0/0 | 0/0/1 | 0/0/0 | **0/0/1** |

- **The Creamy's cause, found:** one pointer jump never moves the CLIENT's own cursor (two
  motions do). So v26 / v27's pointer rest was inert: the client's cursor stayed on the walk
  click's point, a Creamy flew under it, and the client attacked it. v28 rests in two motions.
- **Battleship (v27):** 380 distinct belief goals in 28.8 min; 12 % led to a kill near the goal.
  The map is live and cheap, but as a search goal it fires too often. v28 chases each ghost once.
- **The agent, a packet fact:** a Creamy was 11 cells away next to a Poring. The agent chose the
  other Poring, away from it. The bot has no such fact: the detector boxes a Creamy 8-11 % of
  the time.

## Round 8 (bot v28 first, 16:54; then the agent, 18:00)

- **Sessions:**
  - BOT v28 `20261017T165431-demo-hunt-flow28` (seed 20270901; demonstrations 3.69).
  - AGENT `20261017T175957-demo-agent-demo` (the same seed, 10 min).

| metric | BATT | AGENT R8 (packet-assisted) | BOT v28 median 10' | BOT best 10' | BOT full |
|---|---|---|---|---|---|
| kills / h | 300 | 19.2 | 144 | 156 | 141.9 |
| landing <= 5 s | 64/64 | 3/4 | 20/25 | 21/29 | 119/158 |
| seen -> click p50 / p90 s | 1.11 / 4.79 | 9.78 / 19.79 | 3.0 / 6.75 | 2.28 / 10.6 | 3.47 / 13.4 |
| death -> next click s | 1.24 / 1.8 | 22.5 / 22.5 | 3.4 / 6.91 | 2.38 / 6.03 | 2.38 / 6.19 |
| monsters in sight / 10 min | 44 | 5.3 | 37 | 36 | 33.5 (windowed) |
| loot picked / dropped | 62 / 64 | 1 / 2 | 19 / 40 | 15 / 31 | 95 / 179 |
| kill -> last pickup s | 1.56 | 17.6 | 3.59 | 2.36 | 3.22 |
| walk clicks while moving | 72.7 % | 10.5 % | 34.4 % | 38.6 % | 38.7 % |
| click cadence s | 0.6 / 3.44 | 11.9 / 29.8 | 1.12 / 3.27 | 0.8 / 3.58 | 1.13 / 3.77 |
| reversals / min | 3.6 | 0.43 | 6.4 | 6.4 | 6.21 |
| straight run cells | 16.9 | 26.5 | 12.0 | 10.6 | 11.5 |
| unintended attack requests | - | 0 | 2 | 1 | 7 |
| hard bars (NPC / map / non-target) | - | 0/0/0 | 0/0/0 | 0/0/0 | **0/0/0** |

- **The bot's first clean full hour since v23, after the Creamy cause was fixed** (the two-motion
  pointer rest). It also had the most engagements of the day (159).
- The rest costs walking: walk clicks sent while moving fell from ~50 % to 38.7 %, and the cadence
  rose to 1.13 s.
- **The agent:** 3 kills. Its start area held little, and it spent minutes at the map's southern
  edge, by the warp portal (kept away from it) and in the palm grove.

## Batt's decisions at 18:3x (after the 18:00 update)

1. **The loot's death cell** comes from where the target was when OUR HIT LANDED (or its death
   animation), not the last strike click. Validated offline (3.71): the hit cell has 90 % of drops
   in its 3 x 3, the click 54 %. That is v31.
2. **Battleship off** (inert code): as a search goal ~11 % of goals led to a kill. Off from v30.
3. **A Creamy hit is not a hard bar** until a Creamy-aware detector is trained (GPU frozen). It is
   counted and reported apart. Hard bars stay: NPC contact, map change, unknown UI state, any
   other non-target.
4. **Speed first**, toward 300 kills / h and seen -> click 1.1 s: the A / B / C strike test (3.70),
   then the death-cell loot fix, then the latency budget's top loser. Agent rounds continue.

## Batt's A / B / C strike test (3.70, interleaved per engagement; pooled over runs)

- **The lock arrow, proven against packets:** 93.8 % of arrow-ended bursts mean "the target is
  locked"; 3.4 % false. The arrow comes 0.36 s BEFORE our attack request (p50).
- **Run 1 (v29, 18:11, 141 engagements, hard bars passed):**

| arm | n | arrival -> click | arrival -> attack request p50 / p90 | landing <= 5 s | first click: target / other unit / ground | arrival -> kill p50 |
|---|---|---|---|---|---|---|
| A (confirm first) | 77 | 0.64 s | 1.41 / 1.97 s | 71 % | 55 / 8 / 14 | 2.42 s |
| B (click at once) | 29 | 0.02 s | 0.81 / 1.17 s | 69 % | 20 / 0 / 9 | 1.83 s |
| C (B + nudge) | 32 | 0.11 s | 1.02 / 2.12 s | 81 % | 20 / 0 / 12 | 2.09 s |

  - B and C fall back to A when the species check is unsure or crowded (~45 % of planned B / C).
    So B and C pool more slowly; runs 2+ continue.
- **Final, pooled over 3 runs (337 engagements, all runs clean, 0 Creamy hits):**

| arm | n | arrival -> attack request p50 / p90 | landing <= 5 s | first click: target / other / ground | arrival -> kill p50 |
|---|---|---|---|---|---|
| A (confirm first) | 194 | 1.42 / 2.17 s | 77 % | 143 / 11 / 40 | 2.46 s |
| B (click at once) | 69 | 0.79 / 1.49 s | 71 % | 46 / 0 / 23 | 1.79 s |
| **C (B + nudge)** | 71 | 0.89 / 1.77 s | **86 %** | 52 / 0 / 19 | 1.88 s |

  - **C wins:** as fast as B (0.5 s faster than A to the attack), the best landing, fewer ground
    misclicks than B, and no click ever went to another unit.
  - So the old-cursor effect Batt suspected is weakly supported. C is the next default for
    confident targets.

## Rounds 9-10 (19:14 agent, 19:26 bot v30; 20:29 bot v31, 21:16 agent)

- **AGENT R9** `20261017T191408-demo-agent-demo` (seed 20271101): **66.5 kills / h**, 10 of 10
  landed, 11 of 20 drops, clean. The agent's best, in a dense start area.
  - **Packet fact:** two monsters in a row walked onto our drop pile, a Poring and then a Drops,
    and took it. Killing each dropped the pile again, with their own.
- **BOT v30** (A/B/C run 2, belief off, seed 20271101): 105.0 kills / h, landing 78 %, loot 49 %,
  clean full hour.
- **BOT v31** (the death cell where the hit landed, seed 20271201, 45 min): 101.3 kills / h,
  landing 84.6 %, loot 58.5 %, clean.
- **AGENT R10** `20261017T211621-demo-agent-demo` (seed 20271201): 33.7 kills / h, 4 of 4,
  clean. A sparse area (5.6 in sight).

## Round 11 (overnight: 03:46 agent, between bot v34 and v35)

- **AGENT R11** `20261018T034638-demo-agent-demo` (seed 20271301): 37.2 kills / h, 6 of 6
  landed, 5 of 6 drops picked, clean (0.21 reversals / min, straight runs of 26.6 cells).
  - A very sparse start: 4.1 monsters in sight per 10 min; the first 2.5 min found one Poring.
  - Seen -> click p50 13.4 s (the decision loop again). Each walk from a standstill costs the
    agent ~3 s (robust2's walk series reads twice).
- **BOT v34 run 2** (`20261018T024036-demo-hunt-flow34`, seed 20271802): 133.6 kills / h,
  landing 76.5 %, loot 63.0 %, one Creamy hit counted apart (3.74).

## Round 12 (overnight: 08:08 agent, after bot v36)

- **AGENT R12** `20261018T080801-demo-agent-demo` (seed 20272201, v36's start cell): 19.1 kills / h,
  3 of 3 landed, 5 of 6 drops picked, clean, 0.11 reversals / min.
  - Again a sparse start: 5.3 monsters in sight per 10 min, the first target after 2.6 min. A
    Poring hopping away took ~2 min of chasing (two "gone" and two off-view strikes).
- **BOT v36** (`20261018T070558-demo-hunt-flow36`, the same seed): 188.8 kills / h, landing 81.9 %,
  loot 61.2 %, clean (3.77).

## What the agent's play taught (rounds 0-10)

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

## Where the day ended (21:30) and the next bot change

**Best bot runs, all pixels only:**
- **v28** (16:54): 141.9 kills / h, a clean full hour, 159 engagements;
- **v24** (12:30): 146.9 kills / h, the highest, but with a Creamy hit; its best window was 180 / h;
- **v29 run 1** (18:11): one 2-min stretch of 11 kills, a 330 / h pace (the phone clip).

**Milestones:** none met.
- M1 needs seen -> click <= 2.2 s (best p50 3.13 s), landing >= 90 % (best 86 % in arm C),
  loot >= 80 % (best 61.8 %), reversals <= 5 / min (best 5.6). The hard bars have been clean
  since v28.

**Top losers, v28's latency budget (seconds per hour):**
- server kill -> the bot's "dead", including the loot: 807;
- selection -> click: 552;
- "dead" -> the next selection: 483;
- in range -> click: 250;
- click -> server kill: 234.

**Next, in Batt's order:** *(➡️ re-numbered overnight: C + fast dead = v32, the loot race =
v33, paced input = v34; see "Overnight 17-18 Oct" below)*
1. **v32: arm C as the default** for confident targets, with A as the fallback.
2. **v33: fast dead** (built and staged as v32's code path, PARAMS[32]: the burst's arrow or
   vanish -> dead after one missed frame). Re-number it after C.
3. **The loot:** items first (item_icons ordering the 3 x 3 clicks), since monsters take our drops.
4. **Immunity OFF** is Batt's call. At STR 99 every kill is one hit, so "stand and fight" could not
   be observed, and 19 % of hit targets had started a walk before they vanished.

## Overnight 17-18 Oct (Batt resting; the 12-hour run, 21:45 -> 09:45)

**Batt's decisions on the 21:33 report:**
1. arm C is the default strike (A the fallback); then cut the "species unsure" fallbacks;
2. fast dead: pre-registered (3.72);
3. LOOT IS A RACE (3.73);
4. measure the UI windows' cover, test a compact layout only if it pays;
5. immunity stays ON;
6. the GPU stays FROZEN.

**Found during the night (each with its evidence):**
- **The loot TREADMILL** (22:0x, `arm_judge.py stray`). The loot step blocks the main loop's
  0.3 s minimap re-anchor; when the floor odometry freezes, every loot click lands at the same
  screen pixels and the GM walks off its pile.
  - v28-v31: 62-77 % of loot steps sent the GM >= 4 cells off the death cell. ➡️ **Overstated,
    corrected 2026-10-18 00:33:** the judge's window also caught the next search walk. By the loot
    clicks' own destinations it is 29-48 % (v28 31 %, v31 48 %, v32 29-32 %).
  - v32 run 1 stopped on it (a 13-cell "position jump"; packets: no map change).
  - Fixed in v33 (both arms): the minimap readout before each loot click.
- **The agent link's dead wait** (22:2x). `ro_agent.Agent.send()` drained the socket for a full
  50 ms before EVERY input. The backend logs each input 51-57 ms after the agent made it.
  - A click is 3 sends, so ~150 ms of a ~0.3 s click was waiting; every pointer move paid 50 ms.
  - v34 tests paced sends: the old 50 ms minimum gap between inputs is kept, the dead wait
    after other work goes. Alternating 10-min blocks within each run.
- **The UI windows' cover** (`scripts/ui_cover.py`, v28-v31 pooled, packets + camera):
  - 10.2 % of in-view monster-seconds lie under a window (targets 10.0 %);
  - the shortcut bar 4.5 %, the chat 4.0 %, basic info + menu 1.6 %;
  - the chat window carries the `/where` read and the typed-line gate, so only the shortcut bar
    (<= 4.5 %) is free to shrink, and two runs cannot resolve a change that small in
    sightings per 10 min. The layout trial is PARKED and the windows stay as they are.
- **The held-out map** (offline pick, read-only): prt_fild06.
  - Poring 60 + Lunatic 60 + Pupa 20 of 185 spawns (76 % targets). Unknown: Thief Bug Egg 20,
    Thief Bug 10, Green Plant 15, all passive.
  - 2 warps, 0 NPCs, one connected search area of 44,104 cells; client and server walkability
    agree exactly; the same Prontera grass tileset.
  - Target density is about 2x prt_fild08's, so per-engagement rates are the primary measures.
  - Prep done offline: its GAT in RAM, L3 touch areas (34 maps; the 33 others identical), the NPC
    block, `hunt_flow.py run --map`, the monitor's `--apart` set for its unknown species.

### Overnight results (17-18 Oct, 21:50 -> 08:23 the last run's end)

**Every bot run** (prt_fild08 unless noted; judge_run / flow_judge; landing = hit within 5 s of
the first click; loot = items picked / fell in the session; Creamy counted apart, Batt 18:3x):

| run | session | seed | min | eng | landing | kills / h | seen -> click p50 | loot | sight / 10 min | rev / min | non-target hits | note |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| v32 run 1 | 20261017T215036 | 20271301 | 10.6 | 21 | 18 / 21 = 85.7 % | 101.3 | 5.6 s | 17 / 23 | 20.6 | 6.66 | 0 | stopped: position jump (the loot TREADMILL) |
| v32 run 2 | 20261017T220855 | 20271401 | 60 | 155 | 125 / 155 = 80.6 % | 148.7 | 4.2 s | 125 / 227 = 55.1 % | 15.3 | 5.62 | 0 | |
| v33 att 1 | 20261017T231438 | 20271501 | 9.0 | 27 | 20 / 27 = 74.1 % | 140.5 | 3.02 s | 24 / 34 | 32.3 | 7.81 | Creamy 1 | stopped by me: the death-cell speed fix |
| v33 run 1 | 20261017T232501 | 20271501 | 60 | 134 | 107 / 134 = 79.9 % | 117.9 | 3.22 s | 75 / 148 = 50.7 % | 13.8 | 6.10 | Creamy 1 | |
| v33 run 2 | 20261018T002803 | 20271601 | 60 | 144 | 119 / 144 = 82.6 % | 133.8 | 3.24 s | 80 / 186 = 43.0 % | 12.6 | 7.20 | Creamy 3 | |
| v34 att 1 | 20261018T013226 | 20271701 | 3.9 | 10 | - | - | - | - | - | - | 0 | excluded: the paced arm was inert (farm0) |
| v34 run 1 | 20261018T013812 | 20271701 | 60 | 143 | 109 / 143 = 76.2 % | 128.9 | 3.28 s | 80 / 148 = 54.1 % | 13.2 | 6.58 | 0 | |
| v34 run 2 | 20261018T024036 | 20271802 | 60 | 153 | 117 / 153 = 76.5 % | 133.6 | 3.41 s | 104 / 165 = 63.0 % | 12.1 | 6.45 | Creamy 1 | |
| v35 run 1 | 20261018T035855 | 20271901 | 60 | 173 | 135 / 173 = 78.0 % | **159.8** | 3.74 s | 104 / 232 = 44.8 % | 15.2 | 6.39 | 0 | the night's best hour |
| v35 run 2 | 20261018T050051 | 20272001 | 60 | 153 | 100 / 153 = 65.4 % | 120.9 | 3.29 s | 83 / 158 = 52.5 % | 12.7 | 7.74 | 0 | |
| v35 HELD-OUT | 20261018T060344 (**prt_fild06**) | 20272101 | 60 | 248 | 174 / 247 = 70.5 % | 220.8 | 4.16 s | 123 / 309 = 39.8 % | 34.8 | 8.04 | Creamy 1 + unknown species 26 (counted apart) | 3.76: 2.5x the density |
| v36 run 1 | 20261018T070558 | 20272201 | 60 | 216 | 176 / 215 = 81.9 % | **188.8** | 3.79 s | 131 / 214 = 61.2 % | 16.8 | 7.29 | 0 | the best prt_fild08 hour (densest field) |

**Agent rounds:** R11 (03:46, seed 20271301): 37.2 kills / h, 6 of 6, 5 of 6 drops, clean.
R12 (08:08, seed 20272201 = v36's start): 19.1 kills / h, 3 of 3, 5 of 6 drops, clean (5.3 monsters seen / 10 min).

**Verdicts (each pre-registered before its run):**
- 3.72 v32, FAST DEAD: kill -> loot start 1.23 s against <= 1.2 s, so FAIL by its rule (the slow
  `nearest_cell` was the likely cause). v15's rule was kept, and with the speed fix it reaches
  0.72 s anyway.
- 3.73 v33, LOOT RACE (items first, looter chain): FAIL on both primaries. Race picked 47.7 % vs
  plain 49.2 %; lost to looters 14.8 vs 8.7 %. The plain 3 x 3 was kept.
- 3.74 v34, PACED INPUT: PASS. The loot step was 1.02 s faster, and the walk, landing and loot
  still registered. Paced for the whole run from v35. Kills / h paced 117.9 vs 144.2 followed the
  density (the same 4.75 kills per sighting).
- 3.75 v35, SPECIES ON THE BOX'S OWN FRAME: the primary PASSED (unsure 27 -> 16 %), but landing
  FAILED (80.5 -> 63.6 %): the stale crop had been a "still there" gate. Not adopted.
- 3.76 the HELD-OUT map (prt_fild06, v35 unchanged): walking, strike and loot CARRY OVER.
  - Landing was 70.5 vs 72.1 %, loot 39.8 vs 47.9 %, reversals +1.0, 1 stall against 11-14.
  - The DETECTOR's closed species list does NOT. 26 unknown-species hits (Thief Bug 16, Green
    Plant 8, Thief Bug Egg 2) were counted apart.
  - 21 of the 29 non-target attack requests came from loot clicks, whose unit check sees only
    detector boxes. Looters took 47.6 % of the drops.
  - Seen -> click was +0.84 s on the 2.5x denser field.
  - Kills / h 220.8 (density).
- 3.77 v36, LOOT RETRY: the primary FAILED (loot clicks per step +0.71 against +1.0). The rest
  passed: 34 % of retried cells were clicked, +0.19 s a step, items picked 72.2 vs 62.4 % (one
  run, underpowered), looters 7 vs 20, safety clean. Not adopted; a confirmation-run candidate.

**Leaderboard (kills / h, full hours):** Batt 300 | held-out v35 on prt_fild06 220.8 (2.5x density) |
bot v36 188.8 (best on prt_fild08) | v35 run 1 159.8 | v32 run 2 148.7 | v24 146.9 | v28 141.9 |
agent best 66.5 (R9). Kills / h follows the field's density (sight / 10 min), so it ranks fields
as much as versions.

**Milestones:** none reached. M1 needs seen -> click <= 2.2 s (best 3.02-3.22 s), landing >= 90 %
(best full hour 82.6 %, v36 81.9 %), loot >= 80 % (best 66.6 % at our kills, v34), reversals <= 5 / min (best
5.62). Hard bars were clean in every run (no NPC contact, no map change, no non-Creamy non-target
hit on prt_fild08).

**Top time losers (v34, s / h; v36 in brackets: selection -> click 728, kill -> dead 623, dead -> next 592):**
1. dead -> next selection 570: the search. 67-75 % of engagement ends had no target within 14
   cells (packets).
2. selection -> click 570: the walk into range ~350, in range -> click ~225-255.
3. server kill -> "dead", including the loot, 415 (665 in v32).
4. click -> server kill 264.
5. in range -> click 224.

**Open:** v35's loot fell to 44 % picked at our kills (v34 67 %) with the same step mechanics
(clicks, unit skips, step time). More items went to looters (18.8 vs 12 %) and more were left
behind (36.8 vs 20.7 %). It holds in both species parities; the cause is not found.

## Search study (2026-10-18, Batt's decision 3; `scripts/search_study.py`, offline packets)

Batt's demo (`20261016T093835-demo-human-demo`, 10 min) against the bot's six full hours on
prt_fild08 (v32-v36). The same ruler is used for both (10-min windows). Numbers come from
`search_study.py compare` (4fdb91e; its tests include real-session positive cases).

**The premise, corrected.**
- On the same ruler the bot sees 66 % as many monsters as Batt (29.0 vs 44.0 per 10 min), not
  35 %. The 35 % compared the bot's whole-run count (12-17), which under-counts ~1.65x
  (`flow_judge.sight_windowed`).
- Kills per sighting (now a standard judge column): Batt 6.82; the bot pooled 5.06, 4.45-5.83 per
  run.
- Kills / h ratio 0.49 = sight ratio 0.66 x kills-per-sighting ratio 0.74.

**Where the gap is.** Per kill, Batt spends 12.0 s and the bot 24.5 s. The 12.5 s splits into:
- 39 % search speed: the bot's no-target stretches average 10.5 s, Batt's 6.3 s;
- 17 % extra no-target stretches: 1.15 vs 0.82 per kill;
- 45 % CONVERSION: 12.4 vs 6.8 s per kill with a target in view. The bot attacks 43 % of free
  targets within 10 s of their entering the view, Batt 78 %. It turns toward them about as often,
  ~0.5 s later.

**Why the bot's search is slower.**
- It re-views ground it has already hunted. 43 % of its newly viewed cells were in view within the
  last 120 s (Batt 27 %).
- Its own kills emptied that ground: a killed mob respawns at a random cell anywhere on the map.
- Target yield per 1000 newly viewed cells:
    never seen 1.26 (Batt 1.28)
    seen <= 10 min ago 0.40-0.47
    10-20 min 0.63
    > 20 min 1.02
- Batt did NOT pick denser regions: all prt_fild08 target spawns are whole-map random; the density
  of his ground was 0.80, the bots' 0.80-0.88.
- He walks no faster (176 cells / min vs 158-184). He turns back half as often (3.6 vs 5.6-7.7
  reversals / min), his straight runs are longer (16.9 vs 11-14 cells), and 73 % of his new ground
  is fresh (bot 57 %).
- At engagement ends, 52 % had no target within 14 cells (at the server kill ~62 %; Batt 56 % at
  his kills). The earlier "67-75 %" was at the kill. The difference is the wait for the next
  target: Batt p50 5.75 s, bot 7.75-13 s.
- After a none-end the bot kept its old search heading 91 % of the time.

**The proposed search change (the study's; a candidate v38, not yet pre-registered): the
AGE-WEIGHTED SEARCH HEADING.**
- Score each candidate heading (keep, +-45, +-90, +-135 deg) by the ground it would bring into
  the bot's own camera footprint along a 40-cell ray.
- Weight each cell by how long since the bot last saw it: <= 10 min 0.32, 10-20 min 0.5,
  > 20 min 0.82, never 1.0. Divide by walking time (a diagonal step 1.4x).
- Remember the swept ground for the whole run (now 180 s).
- Re-score at every re-plan, including when the search resumes after an engagement.
- Expected: encounters per no-target minute +15 % (+10 to +27 %), kills / h +5 to +12 %. Kills per
  sighting is unchanged: that is conversion.
- The study's caution: even Batt's own encounter rate would give ~183 kills / h. The larger lever
  is conversion.
- Testing it needs >= 4 run-hours, interleaved in 10-min blocks within runs: the field drifts
  between runs. v36 run 1 saw 13 Pupas vs 0-1 in the other runs, and its fresh-ground yield was
  2.11 vs 1.07-1.21, so part of its 188.8 kills / h is the field.
- Safety: only the search goal changes. Every click keeps its gates, and the memory is built from
  the bot's own measured position (no packets).

## Sunday 18 Oct (Batt's four decisions on the overnight report; 08:57 -> 12:25)

| run | session | map, seed | eng | landing | kills / h | kills per sighting | loot | sight / 10 min (win) | rev / min | non-target |
|---|---|---|---|---|---|---|---|---|---|---|
| v36 run 2 (confirmation) | 20261018T090851 | prt_fild08, 20272301 | 146 | 104 / 144 = 72.2 % | 114.8 | - | 79 / 132 = 59.8 % | 11.8 (whole run) | 7.55 | 0 |
| v37 run A (held-out rules) | 20261018T101834 | prt_fild06, 20272501 | 200 | 147 / 200 = 73.5 % | 190.8 | 3.21 | 97 / 386 = 25.1 % | 59.5 | 5.44 | unknown species 30 (counted apart) |
| v37 run B | 20261018T112036 | prt_fild08, 20272601 | 161 | 132 / 161 = 82.0 % | 141.0 | 4.62 | 107 / 194 = 55.2 % | 30.5 | 5.35 | 0 |

1. **The loot retry's confirmation** (3.77):
   - The primary passes pooled (+1.14 clicks / step); items picked +3.0 points pooled (runs +9.8 /
     -7.0: unresolved).
   - Run 1's FAIL stands. Adoption is Batt's.
   - **The runner now rebuilds the hunting state itself** (`gm_state.ensure_hunting`: STR from the
     weight cap, STR's '+' in the status window). The hunting state is kept between runs; the
     standard Lv 1 state only at a series' end (done 12:25).
2. **The cursor's SWORD at loot / walk clicks** (3.78, v37):
   - Held-out non-target attacks from loot / walk clicks dropped 20 -> 4. It was right when it
     decided.
   - But in motion the client draws its cursor at the new point only after ~0.35-0.4 s, so 56-78 %
     of checks ended UNKNOWN (fail closed).
   - The time-cost predictions failed; landing on prt_fild08 was -6.4 points. Not adopted as is;
     the options are in 3.78.
3. **The search study** (above): the premise is corrected to 66 % of Batt's sightings on the same
   ruler. The age-weighted heading is STAGED as v38 (PARAMS[38], 5a0870f) and needs >= 4
   run-hours. Kills per sighting is a standard judge column (Batt 6.82; the bot 3.2-5.8).
4. nvtop and the /dev/shm cleanup are Batt's. The GPU stays frozen.

## Sunday 18 Oct, afternoon (Batt's decisions on the series report, received 13:29)

1. **Loot retry: NOT adopted for now** (the pooled primary passed, but the loot gain is not shown
   and each step costs +0.39 s; speed is the priority). It stays staged (PARAMS[36]).
2. **The cursor's SWORD check: option (a).**
   - Loot clicks only, with a 0.6 s wait, and only on maps with species the detector was not
     trained on; walk clicks unchanged.
   - Built 0d4cacb: `UNTRAINED_SPECIES` per map (prt_fild06 on, prt_fild08 off; an unlisted map
     refuses). In the base from v38.
   - Not yet measured live at 0.6 s.
3. **Conversion first, then v38.**
   - A conversion study like the search study (offline, banked sessions + Batt's demo): split the
     extra time into notice -> turn -> in range -> click -> hit -> kill, and say why the bot
     attacks only 43 % of free targets within 10 s (Batt 78 %). Rank the causes and propose the
     next change.
   - Then v38 (the age-weighted heading) for >= 4 run-hours, interleaved: pre-registered as 3.79
     (13:46, c46dc16).
4. nvtop and the /dev/shm cleanup are Batt's. The GPU stays frozen.

## Sunday 18 Oct, 16:2x (Batt's order after v38's first two runs)

1. **After v38's 4 runs: v39, the continuous approach.**
   - The steer must always find a click point on the route and never stop because no route cell
     qualified. Fix the point picker, not the gates.
   - Built fffb751: the route's end is the last resort when even the tail is empty.
   - Pre-registered as 3.80 (16:37, a89d93a): per engagement, 4 x 60 min, the primary is the
     GM's moving share while steering (tail >= 1.15 x base).
2. **Then the FALSE DEAD fix.**
   - A burst ending "risky" must not let the dead rule abandon a target that is still visible /
     alive: re-engage it, or mark it "skipped: risky" explicitly, never "dead".
   - Its first measure: after a "risky" last burst the target really died 58-76 % of the time,
     so the fix needs a pixel signal of "still there" (3.81, sized during v39).
3. **"Dead calls without a real death" per run is a standard column** (flow_judge, 0815c41).

   | run | without death | no unit | target alive | other kill | after a risky burst |
   |---|---|---|---|---|---|
   | v36 run 1 | 42 / 214 = 19.6 % | 8 | 29 (+3 gone) | 2 | 18 |
   | v37 run B | 31 / 160 = 19.4 % | 7 | 22 (+1 gone) | 1 | 10 |
   | v38 run 1 | 47 / 150 = 31.3 % | 17 | 27 | 3 | 21 |
   | v38 run 2 | 28 / 163 = 17.2 % | 12 | 15 | 1 | 11 |

4. Decisions keep reading 4-run pooled results, against the measured null spread.

**v38 (the age-weighted search heading, 3.79): NOT ADOPTED** (pooled read 22:00):
- Re-swept within 120 s: age 0.49 vs cov 0.47 (the primary needed <= 0.90 x).
- Kills / h: 126.6 vs 143.1 (the guard failed: -11.5 %, inside the +-18 % null but the wrong
  way).
- Equal density across the arms (sight 32.3 vs 31.8).
- Without block 0, the same answer.
- The search stays on v22's coverage heading. v39 (3.80) started at 22:01, after a 3.5-h gap
  (the agent's turn after v38's run 4 failed, and Batt retried it).

## Conversion study (2026-10-18 afternoon, Batt's decision 3; offline packets + the bot's logs)

Two judges, merged 3c6180d and 767ee6e, each with real-session positive cases:
- `scripts/conversion_phases.py`: the timeline per free target (Batt vs the bot on one ruler);
- `scripts/conversion_misses.py`: why a free target is not attacked within 10 s.
Data: Batt's 10-min demo vs the bot's 10 full hours on prt_fild08 (v32-v37). Both reproduce
search_study's cohort exactly (free entries: Batt 40, the bot 1801).
- Attacked within 10 s: Batt 0.78; the bot 0.40 pooled over these 10 runs (0.28-0.54). The 43 %
  quoted earlier was the search study's pool.
- **Correction:** frames show the server's state ~0.6 s old (measured; it was ~0.5 s).

**Where the targets drop out (share of free entries reaching each step within 10 s):**

| | noticed | turned toward | clicked | hit | killed |
|---|---|---|---|---|---|
| Batt | 0.80 (pointer proxy) | 0.82 | 0.72 | 0.78 | 0.75 |
| the bot | 0.76 | 0.85 | 0.40 | 0.38 | 0.34 |

The bot notices and turns about as often as Batt. The loss is between the turn and the click.

**The time with a target in view, per kill, split so that it sums (Batt 6.80 s, the bot 13.08 s):**

| label (outcome of the deciding target) | Batt | bot | gap |
|---|---|---|---|
| killed: turn -> within 3 cells (the approach) | 2.23 | 5.45 | **+3.22** |
| never attacked | 0.49 | 2.45 | **+1.96** |
| killed: within 3 cells -> click | 0.81 | 1.31 | +0.50 |
| killed: noticed -> turn | 0.00 | 0.36 | +0.36 |
| killed: click -> hit, the client's walk-up | 0.55 | 0.87 | +0.32 |
| killed: unnoticed | 0.82 | 1.09 | +0.27 |
| attacked, not killed | 0.00 | 0.08 | +0.08 |
| killed: click -> hit at reach | 0.09 | 0.12 | +0.03 |
| killed: hit -> kill | 1.14 | 0.97 | -0.17 |
| loot after a kill | 0.68 | 0.37 | -0.31 |

- Hit -> kill is the same behaviour: 0.91 s p50, 1.30 s between hits, the same character state.
- Both walk up to about 3 cells before clicking. The client sends the attack request only near
  reach (attack request -> melee p50 0.08 s), so the CLICK is the decision.

**1. The approach (+3.22 s per kill): the bot stands still while closing in.**
- Both start ~13 cells away. Batt closes at 3.89 cells / s p50 with his GM moving 92 % of the
  time; the bot closes at 2.05 cells / s, moving 52 %.
- In steer mode (~20 min of every hour) the GM moves only 37-38 % of the time.
- Each GM stop in steer mode, by the click that ended it (v35-v36, 3 runs, per engagement):

| the stop ended by | stop -> click p50 | seconds per engagement |
|---|---|---|
| the strike (the GM stops at 4-7 cells, then the strike) | 1.9-2.2 s | 2.1-2.3 |
| the next walk leg (map + units gate) | 0.8 s | 1.3-2.6 |
| the standstill fallback (cursor gate) | 5.1-5.2 s | 1.0-2.0 |

- Why (the code, and since 14:17 the log-only `cont_fail` counts, 3.79 amendment):
  - The steer walks a ONE-TIME path into a zone around the target: 7 cells for a standing
    target, 4 for a walking one.
  - The continuous click takes candidates only 3-8 cells ahead of the lead point (0.6 s of our
    own commands). Near the path's end there is none, so the GM walks out its leg and stops.
  - The standstill fallback steps from the path's START, which the GM has passed, so it often
    finds no step and waits again.
  - Run 1's first minutes: "no candidate" in 32 of 35 moving steer calls; 38 of 38 standing calls
    had a path <= 3 cells.

**2. Targets never attacked (+1.96 s per kill).**

| cause group | free entries | idle s per kill (sessions) |
|---|---|---|
| walker not reached (late / steering / gone) | 11.8 % | 1.19 (0.72-1.86) |
| strike on a walker missed or landed late | 6.6 % | 0.84 (0.60-1.22) |
| detector: never boxed / lost undetected | 6.9 % | 0.51 (0.27-1.35) |
| selection: never attended / retarget away | 5.2 % | 0.35 (0.12-0.72) |
| lost off screen / other | 2.6 % | 0.26 |
| busy (fight / loot / dead wait) | 10.6 % | 0.17 |
| off screen (edge flicker at 14 cells) | 15.9 % | 0.09 |
| selection gates | 0.2 % | 0.01 |

- "Idle s" = seconds the target was in view while the bot was not converting another mob, per bot
  kill. It is a different ruler from the decomposition above, so do not add the two.
- Walkers: the bot was still 7-9 cells away 10 s after the entry. Its zone and tracker kept
  restarting: 2.9 zone plans and 0.95 target losses per entry, vs 1.8 and 0.5 for targets it
  took.
- First strike click landing (an attack request within 1.5 s):

| GM / target | strikes | landed |
|---|---|---|
| standing / still | 911 | 84 % |
| standing / walking | 312 | 60 % |
| walking / still | 292 | 77 % |
| walking / walking | 42 | 24 % |

- **False "dead" calls: 16.9 %** of joined engagements (260 / 1540; checked again: 16.5 % and
  15.7 % on two runs). The target was alive, mostly after a strike that never landed. That cost
  0.38 s per kill of loot steps on nothing.
- Batt's 9 misses were all targets out of his reach (off screen, or gone within seconds). None
  came while he was busy with another target.

**3. Within 3 cells -> click (+0.50 s per kill).**
- The bot's in range -> click: p50 1.07 s, mean 1.52 s.
- Arm C (the nudge) is 62 % of strikes, p50 0.77 s; arm A for "species unsure" is 33 %, p50
  1.41 s (+0.42 s per kill over arm C).
- Empty name-tag reads cost 0.60-0.77 s per kill, partly inside the rows above. Mostly on still
  mobs, so not a walker effect.

**RANKING (seconds per kill vs Batt) and the proposed next change**
1. The approach: +3.22 (the GM stands between legs, in ~5-s stalls, and ~2 s before each strike).
2. Never attacked: +1.96 (walkers 2.03 idle s / kill; detector 0.51; selection 0.35).
3. Within 3 cells -> click: +0.50 (species-unsure fallbacks, empty tag reads).
4. Notice -> turn +0.36, client walk-up +0.32, unnoticed +0.27.
Also: false "dead" calls on 16.9 % of engagements (0.38 s per kill of looting nothing).

**Proposed v39: THE CONTINUOUS APPROACH.** The GM keeps walking until it is in strike range.
- When the route ahead has no candidate, the steer re-plans from where the GM will be and may
  click the route's tail.
- The standstill fallback steps from the route point nearest the GM.
- No new click kind, and every walk gate is unchanged.
- Expected: it removes most of the ~0.8-s leg stops and the ~5-s stalls, 2.3-4.6 s of standing
  per engagement today. Upper bound kills / h +8-12 %. It should also help the walkers that are
  never reached.
- Interleaved per engagement. Measured by the steer moving share, turn -> 3 cells, and kills / h.
- STAGED 9c75f36 (PARAMS[39], tested, not run). Its design uses the `cont_fail` counts banked
  during the v38 runs. It needs Batt's go.
- **Evidence from v38 run 1** (log-only `cont_fail`, 3.79):
  - 8,617 steer walk-click calls found nothing to click (6,408 while moving), and 96 % of them
    had NO candidate on the route at all;
  - half of those were routes <= 3 cells; on the other half the 0.6-s lead point already lay
    past every candidate;
  - the gates refused little (view 339, guard 216, units 118).
  - So the standing comes from the candidate rule, which is what the tail changes.
- **Its judge is ready (99592bd):** `arm_judge.py approach SID...`, per engagement parity (odd k =
  tail). Each steer span counts for the k the runner holds then: the steer always works toward
  the next engagement. It reports:
  - the GM's moving share while steering, and its stops per steer minute;
  - steer seconds per engagement;
  - the approach (steer start -> first click, and -> within 3 cells, from packets);
  - landing.
- **Null spread** (22 no-change splits of 11 banked runs, 95 % range of a 4-run pooled
  difference; the splits share runs, so this is a rough ruler):

    | measure | 95 % null range |
    |---|---|
    | steer moving share | -8 % .. +6 % |
    | steer s per engagement | -14 % .. +11 % |
    | approach s (mean) | -8 % .. +11 % |
    | steer start -> 3 cells (mean) | -9 % .. +14 % |
    | landing within 5 s | -6 % .. +14 % |

  The bot moves ~37 % of steer time, and Batt 92 %. So a real fix should show far beyond these
  ranges in 4 run-hours. v38 run 1's parity split alone gave landing 76 % vs 54 % (z ~ 2.9) with
  nothing behind it, which is why the decision would read the pooled runs, never one.
- The tail arm logs its own `cont_fail` keys (`steer+tail:...`); the base keeps v38's.

**Next candidates:**
- Strike WALKING targets from 7 cells at a velocity-led aim point (the misses judge's proposal,
  +4-8 %). Riskier: the led point is not on a detector box, so the Creamy guard must be evaluated
  there.
- Fix the false "dead" calls.
- Fewer species-unsure fallbacks and empty tag reads.
- The detector (0.51 s per kill) waits for the GPU.

## Overnight 18-19 Oct (Batt asleep; his 22:2x plan, until Monday 07:00)

Batt's plan:
1. v39: finish runs 2-4, verdict.
2. v40, the false-dead fix: 4 runs, verdict.
3. Then the next top cause, each as its own version, re-ranked after every verdict on the
   bot-vs-Batt table.
4. A version that passes becomes the base; one that fails reverts. Never stack unjudged changes.

The client is kept busy by `scripts/hunt_chain.py`: it queues the CURRENT version's remaining
pre-registered runs only, each time-boxed with the live hard-bar monitor. Judging and
pre-registering stay with the agent.

**v39 (the continuous approach, 3.80): NOT ADOPTED** (pooled read 02:20, 7dd9524):
- Steer moving share: tail 0.370 vs base 0.367 (the primary needed >= 1.15 x).
- Approach: 5.14 vs 4.71 s (needed <= 0.90 x). Landing 74.9 vs 77.1 % (the guard passed).
- Hard bars 0 / 0 / 0 in all 4 runs.
- **The finding:** the picker now finds a point, but on a short route the tail cells lie within
  120 px of the GM's sprite. There the WALK GUARD refuses them (4,477 refusals vs 385): v16's
  Creamy layer. The GM still stands until the 1-s standstill fallback.
- So the approach's remaining cause is a gate, and gates are Batt's call.
- The 5th check ("none" <= 0.10 x) failed its bound; the residual is the design's own arrival
  case (3.80 RESULT).

**The bot against Batt, on the current best base** (v38's base; measured by v39's 4 runs, whose
tail arm changed nothing on the primary):

| measure | Batt | bot (v39, 4 runs) |
|---|---|---|
| kills / h | 300 | 151.1 (130.9-179.8) |
| monsters seen / 10 min (windowed) | 44 | 31.9 |
| kills per sighting | 6.82 | 4.73 |
| s per kill | 12.0 | 23.8 |
| free targets attacked within 10 s | 78 % | 40.5 % (n 741) |
| steer moving share | 92 % | 35-39 % |
| seen -> click (p50) | 1.11 s | 3.47 s |
| death -> next (p50) | 1.24 s | 0.71 s |
| landing within 5 s | 100 % | 76.0 % (517 / 680) |
| loot picked / dropped | 97 % | 56.9 % (444 / 780; 103 lost to looters) |
| reversals / min | 3.6 | 7.77 |
| dead calls without a real death | - | 24.5 % (165 / 674) |
| Creamy hits (requests) | - | 12 (10) |
| hard bars | - | 0 / 0 / 0 |

- Milestones: M1 (seen -> click <= 2.2 s, landing >= 90 %, loot >= 80 %, reversals <= 5 / min,
  hard bars clean) is NOT met: only the hard bars pass. M2 and the stretch are not met.
- The best 2-min stretch of the night so far: v39 run 1, minutes 21-23, 14 kills (a 420 / h
  pace). The phone clip is on the NAS: `hunt-recordings/v39r1-best2min-phone.mp4`.

**Re-ranked after v39** (seconds per kill vs Batt, conversion study):
1. The approach, +3.22. Its remaining cause is the walk guard: Batt's decision.
2. Never attacked, +1.96. Walkers are the largest group (1.19 + 0.84 idle s per kill) ->
   **v41, walking targets struck from 7 cells** (3.82, pre-registered 02:31, 61cf81d). The
   aim stays arm C's on the detector box; it is not the velocity-led point of the earlier
   candidate below. It runs in Batt's next block: v40's four runs fill the night.
3. Within 3 cells -> click, +0.50 (species-unsure fallbacks, empty tag reads).
4. Dead calls without a real death, 24.5 % of dead calls -> **v40, the false-dead fix** (3.81),
   running since 02:26:49.

**v40 (the false-dead fix, 3.81): ADOPTED** (pooled read 06:39):
- After a risky last burst, dead calls with the target still alive: fix 2 vs base 28 (needed
  <= 0.25 x).
- Loot at our kills 0.545 vs 0.556 (the guard -8 passed, -1.1); landing 75.5 vs 70.4 %.
- Hard bars 0 / 0 / 0 in all 4 runs. 47 engagements skipped as "skipped_risky", 23 of them real
  kills.
- The fix joins the base for every engagement from v41 (3.82) on.
- Kills / h 140.9, 152.9, 121.9, 94.0 (mean 127.4; sight 35.0 -> 28.0 / 10 min over the night).

**End of the night (06:41):** nothing runs on the client; the GM is at the standard Lv 1 state;
route_previewd is stopped; /health bot_agents [].

**Decisions for Batt:**
1. The 120-px walk guard near the GM blocks the approach's remaining fix (v39). Loosen it for
   steer clicks only, or keep it: v39 runs 3-4 had 12 Creamy hits through walk / loot / strike
   clicks with the guard ON.
2. v41 (3.82, walkers struck from 7 cells) is pre-registered on v40's base; it needs a 4-run-hour
   block.

## Reversals study (Batt's decision 3, 2026-10-19; offline, `scripts/reversals_study.py`, e17d6c1)

Batt: "Reversals rose back to ~7-8/min (v20 reached ~4). Find out why (engagement turns vs search
heading) from banked runs and report; don't change anything yet." Nothing in the bot was changed.

**The ruler:**
- `reversals_study.py` replays `flow_judge.heading_metrics` one leg at a time and labels each
  reversal by its second leg (the leg that turned):
  - the bot's mode then;
  - the click behind it (search walk, steer walk, strike, loot);
  - the boundary (a new target, an engagement's end, a heading turn);
  - whether the chosen place already pointed back.
- It reconciles exactly with flow_judge on every banked run with a flow_judge.json (39 bot runs +
  Batt's demo). The agent re-checked two runs itself: v20 run 1 238 = 238, v39 run 2 523 = 523,
  and every split sums to the total.
- Data: 42 runs, v20-v40, ~33 h.

**Where the rise (v20 4.28 -> v39 + v40 7.37 / min, +3.09) came from:**

| # | source | + reversals / min | share |
|---|---|---|---|
| 1 | the fixed loot step (v23, the 3 x 3 workflow) | +1.57 | 51 % |
| 2 | the search heading (v22's coverage heading), incl. one ping-pong episode | +0.80 | 26 % |
| 3 | more engagements per minute (2.21 -> 2.69) at the same 1.49 reversals each | +0.72 | 23 % |

- Not the cause: time per mode (unchanged), more or shorter legs (Batt walks 46.8 legs / min and
  reverses 0.077 per leg; the bot 38.3 and 0.192), position lag.
- The steps: v20 -> v22 search-only reversals per search minute 2.25 -> 3.13 (coverage heading);
  v22 -> v23 the loot step appears (+1.97 net); v23-v40 roughly flat.

**Latest runs (v39 + v40, 8 runs), by the leg that turned:**

| cause | / min | share | what it is |
|---|---|---|---|
| steer to a NEW target | 1.89 | 26 % | 1.26 / min the target was behind (p50 14.5 cells, at the view's edge; the planner held only that one target 79 % of the time) |
| search RESUME after an engagement | 1.62 | 22 % | 1.38 / min the remembered heading points back (v18's resume rule) |
| loot step | 1.47 | 20 % | entry from the strike 0.78; within the step 0.68 (the fixed order's SE -> W and NE -> NW hops reverse by design) |
| search heading TURN | 1.21 | 16 % | the coverage heading takes +-135 deg whenever it scores >= 0.8 x the best; 90-deg+ turns per search minute 0.97 (v20) -> 4.8 |
| strike (the client walks up) | 0.61 | 8 % | |
| steer approach / replan | 0.42 | 6 % | |

- Batt: 0.72 reversals per kill; the bot 3.18 (4.4 x).

**A bug found (not fixed, as ordered):** v39 run 2, minutes 46.5-48.3: the search heading
flipped between 135 and 315 deg (two dead-end goals) 52 times in ~110 s, all in search mode.
That episode alone added ~47 reversals; the run's 8.71 / min drops to 7.93 without it. Confirmed
by the agent on the run's own `heading_goal` events.

**Fix proposals (none built; Batt's call, each its own pre-registered version):**
- P1 loot as a ring tour: centre, then the 8 ring cells in 1-cell steps from the GM's side. It
  costs the SE / W / N-first item order; check item fates offline first.
- P2 resume: re-pick the heading from the GM's position, not the remembered angle (changes v18's
  rule, which was Batt's).
- P3 heading-aware dispatch: a turn cost, or skip targets > 120 deg behind and > ~10 cells while
  searching. Needs an offline kills / h trade-off first.
- P4 coverage heading: +-135 only when 0 / 45 / 90 are blocked, or a turn penalty in the score.
- P5 dead-end hysteresis: no second reversal within N s; on a two-sided dead end, the best of 8
  headings. Removes ping-pong episodes like v39 run 2's.

## Pointer diagnosis (Batt's clip 15:53, 2026-10-19; offline: the mux input log + packets)

Batt watched v43 run 1 at 15:53:
- the route preview flipped direction every few seconds;
- the pointer jumped around, once to the bottom-left corner;
- the GM barely moved.

His hypothesis: the pointer rests away (the HP bar, a corner), jumps back and clicks, and the
click lands in the wrong place (the client's cursor not updated after one jump), so the GM walks
back and forth.

**1. Do clicks after a pointer jump land in the wrong place?** (v41's 4 runs, today's input log;
`pointer_diag.py` in scratch). Each walk click's intended cell (clicks.jsonl `to`) vs the cell the
client asked the server for (the next `self_move_request` within 0.5 s):

| walk clicks | n | > 1 cell off | after a jump (pointer >= 150 px away in the last 1.5 s, one motion near the point) | no jump |
|---|---|---|---|---|
| search | 5,131 | 1,071 (20.9 %) | 4,766: 971 off (20.4 %) | 365: 100 off (27.4 %) |
| steer | 1,340 | 205 (15.3 %) | 950: 166 off (17.5 %) | 390: 39 off (10.0 %) |

- 93 % of search walk clicks follow a jump, but a jump does NOT raise the miss rate: 20.4 % vs
  27.4 % without one.
- The rest point is (110, 66), over the HP bar, reached in two motions.

**2. How many reversals do misplaced clicks explain?** Of 1,542 reversals (7.13 / min), the click
behind each turning leg (the latest click <= 1 s before it):
- search walk 604, steer walk 526, loot 262, strike 130, strike burst 18, none 2;
- a walk click more than 1 cell off: **250 (16 %)**, 208 of them after a jump.
- So most walk-click reversals landed where the bot meant: the bot chose to go back.

**3. What Batt saw at 15:53 (v43 run 1, minutes 23.5-25.5):**
- The bottom-left jump was a SEARCH WALK click at (97, 693) at minute 24.94: the route's next
  cell projected into the corner. It was not a rest, and the click was not misplaced.
- The runner's mode flipped search <-> steer 8 times in 17 s (24.86 -> 25.13): a target picked,
  dropped, picked again. Each flip redraws the route preview in another direction, and the GM
  barely advances.
- No /where in that run (the hunting layout's tab switch played no part); the search heading was
  steady (minutes 22-27: 87 of 107 heading goals with no turn; no dead-end escape).

**4. The cause it points to: ABORTED STEERS.**
- v41's 4 runs: 1,019 steer spans (4.7 / min). 526 of them (52 %, 2.4 / min) ended with no attack
  click by their end + 1 s; 443 of those were under 5 s long.
- 627 of the 1,542 reversals (41 %, 2.90 / min) have their turning leg inside an aborted steer or
  within 2 s after it.
- This matches the reversals study (steer to a new target 1.89 / min, with the target behind
  1.26 / min, p50 14.5 cells away at the view's edge; the search resume 1.62 / min).

**Conclusion:**
- The click-mismatch cause is NOT confirmed as the main one: misplaced walk clicks explain at most
  16 % of reversals, and jumps do not make them worse.
- So by Batt's rule the LOCKED-POINTER WALK does not jump ahead of v42; it follows v42 as the
  search-walking change (pre-registered as 3.85).
- The larger lever is the aborted steers (41 % of reversals): targets picked at the view's edge
  and dropped. That is the next cause to size: why a steer is dropped (target lost / retarget /
  preempt / gate), and what Batt does with a monster at the edge.

## The Battle Log reader (Batt's combat-log tab, 2026-10-19; `scripts/battle_log.py`, 8103c54)

The hunting layout shows the chat window's Battle Log tab. Its lines, on the lab client (English
UI; item names in Thai):
- `[Poring] receives '179' damage points.` (yellow: our hit, with the monster's name)
- `'2' Base Experience acquired.` and `'1' Job Experience acquired.` (yellow: a kill of ours)
- `You got <item> (1).` (cyan: a pickup)

**The reader** (built by a subagent, reviewed, tests green, no input path):
- 3 message lines at a 14 px pitch (rows 551-592), the newest at the bottom.
- Ink by luma; sprites behind the translucent window are dropped; each line keeps its own colour.
- Glyphs are matched to templates. The digit templates cut from recorded JPEGs are pixel-identical
  to where_fix's templates cut from live frames. Monster names are mapped to the species list.
- New lines are found by line diffing: the smallest scroll that makes this frame's lines match
  the last frame's. Item names are never read; the count only.
- `battle_log.py replay SID` works on the recorded frames; `battle_log.py live` reads the live
  frames read-only. From 17:19 it logs beside every v43 run at 10 Hz, log-only.

**Validated against packets on v43 run 1** (`battle_log_judge.py`, 60 min, 18,076 frames, 128
kills, 72 pickups; species Poring 79, Lunatic 39, Drops 7):

| line | lines read | packet truth | precision | recall | delay after the packet, p50 / p90 | values right |
|---|---|---|---|---|---|---|
| DAMAGE | 125 | 128 hits | 1.000 | 0.977 | 1.17 / 1.34 s after the act | damage 125 / 125, name 125 / 125 |
| BASE EXP | 126 | 128 kills | 1.000 | 0.984 | 0.33 / 0.47 s after the kill | 125 / 125 |
| JOB EXP | 126 | 128 kills | 1.000 | 0.984 | 0.33 / 0.47 s after the kill | 121 / 121 |
| ITEM | 73 | 72 pickups | 1.000 | 1.000 | 0.40 / 0.71 s after the pickup result | count 73 / 73 |

- Misses (all 5 checked frame by frame):
  - 2 identical repeats: the same damage and EXP as the kill before, nothing in between, so
    nothing on screen changed;
  - 1 overflow: 4 lines inside one 0.2 s frame interval;
  - 1 EXP line "unseen", probably a repeat too.
  The live logger runs at 10 Hz to halve the overflow window.
- **As an authoritative "dead":**
  - The base EXP line confirms a kill: 0 false lines in 126. It comes 0.33 s after the server's
    vanish (p50), and its p90 is 0.48 s against the bot's own dead call's 3.51 s.
  - It does not prove a target alive: 1.6 % of kills are invisible repeats. It also does not
    name the unit: the damage line in the same frame gives the species only.
- **As "landed" and the species struck:** the damage line is right after the fact (value and
  name 125 / 125), but too late for a real-time "landed": 1.17 s after the hit (the client logs
  it as applied). Hits that do not kill have not been seen yet (every hit killed at ATK 197).
- **As the loot count:** the item lines are complete on run 1.
- One session so far: these figures are confirmed only once runs 2-4 agree. Nothing is wired into
  a decision; using it is a pre-registered version of its own (Batt's order: the version after
  v42).
- ➡️ **Confirmed LIVE on v42's 4 runs** (the merged language-independent reader in its own
  process, 10 Hz, log-only; `battle_log_live.jsonl` against packets): base EXP precision 112/112,
  121/122, 147/148, 132/133; recall (kills of ours with a line within 2 s) 0.982 / 0.992 / 0.980 /
  0.985; delay after the kill p50 0.28-0.33 s, p90 0.39-0.47 s. Wired into a decision first by
  v44 (3.87, from 2026-10-20 00:52).
  ➡️ v44 NOT ADOPTED (2026-10-20 04:4x): the EXP line was sure and fast (kill -> loot start
  0.38 x), but its checked pixel fallback failed the truth check (0.72 x) and cost loot (-12.2
  points). See the overnight section below.

## Day run 2026-10-19 (Batt's decisions ~07:00, until 20:00): results

- **v41** (walkers struck from 7 cells, 3.82): NOT ADOPTED (near -> click 0.77 x, needed 0.70;
  walker landing -8.3 points).
- **v43** (Batt's hunting UI layout, 3.84): ADOPTED. Detections in the uncovered area 0.180 (vs
  0.018); detected share 0.946 (vs 0.911, +3.8 %); landing 75.9 %; hard bars clean. The play area
  went from 79.0 % to 86.4 % of the frame. It is restored by `scripts/client_layout.py`.
- **Found and fixed on the way** (all fail-closed stops):
  - the chat left open + the translucent tabs (the tab is read by its white top border);
  - the notice badge under the weight digits (`poring_env.weight.unbadge`).
- **Found, to fix before v42:**
  - run 4's pointer move above the desktop (dropped by the backend's validation; the runner
    stopped safely);
  - the search POCKET (run 2's 53 min): the fix is built and tested offline and rides with v42.
- **Queue (all pre-registered):** v42 (steer guard + tail + the pocket escape) -> v44 (dead = the
  Battle Log's EXP line, 3.87) -> v45 (commit to a target like a player, 3.86) -> v46 (the
  locked-pointer walk, 3.85).

## The loot drop with the hunting layout (Batt's decision 4, 2026-10-19 ~20:00; offline)

Batt: "check the LOOT drop with the new layout (v43 42.3 % vs v41 57.9 %): does any loot step or cue
depend on the Regular Chat tab ...? or the collapsed panel / masks near the loot area? Report the
cause; fix it as a bug if it's the layout."

**No dependency on the layout was found:**
- **The chat tab:** the loot step the base runs (v23's fixed workflow, `loot_fixed_run`) reads
  neither the "You got" chat cue nor the weight. The cue (`loot1.check`) lives only in the older
  blob / sweep loot paths, which `loot_fixed` replaces. Showing Battle Log instead of Regular Chat
  cannot change a loot click. (The "You got" lines do appear in the Battle Log tab: Item get/drop
  is on there.)
- **The masks:** the step skips a click near a monster box, near an NPC, on new pink pixels, or on
  the UI (`loot1.in_ui`). The hunting layout's UI rectangles are SMALLER (the panel and three
  hotbar rows gone; the chat unchanged), so they can only skip fewer clicks.
- **The step's own counts, unchanged across the layouts:**

  | run | loot steps | clicks | unit skips | pink skips | step s p50 |
  |---|---|---|---|---|---|
  | v41 r4 | 120 | 775 | 381 | 41 | 2.19 |
  | v43 r1 | 121 | 781 | 374 | 47 | 2.28 |
  | v43 r3 | 111 | 680 | 382 | 48 | 2.07 |

**What did differ (not attributable: v43 was not interleaved with the standard layout):**
- Items lost to looters, of the drops at our kills: v41 r4 9 %, v43 r1 18 %, v43 r3 25 %.
  ➡️ **SUPERSEDED 2026-10-19 21:16 (the loot-fate check below):** these three shares do not
  reproduce, and their base was not recorded. On the fixed judge (`loot_fates.py runs`, the
  drops of the engagements' kills) they are 14.0 / 12.5 / 20.0 %. Looters barely moved across the
  layouts (v41 14.2 %, v43 15.1 % pooled). **v43's drop is in items LEFT BEHIND, out of our
  sight (43.0 % vs 27.8 %), with a worse death cell (exact 31 % vs 41 %).**
- The death-cell verdict "ok": v41 55 / 50 / 49 % vs v43 42 / 41 / 32 %, with more
  "still_visible". It does not move the loot clicks: the death cell comes from the target's box
  at our hit ("anim") in every run. It feeds only the false-dead fix's "skipped_risky".
- The field was thin today: sight 25.0 / 21.5 / 34.0 per 10 min in v43, against 28-36 in v41.

**Conclusion:** not a layout bug as far as the code and the logs show, so nothing was changed. The
loot share is watched in v42's runs (the same layout, the same loot step). If it stays low, a 10-min
block check of the layout (standard / hunting, the same seeds) is the way to settle it.

**Batt's decisions on the day report (~19:5x):**
1. 3.87's checked pixel fallback: approved.
2. The pocket rule with the 60-s spread: approved.
3. Reversal fixes:
   - P4 yes, pre-registered as 3.88 (v47, after v46);
   - P1 (the loot ring tour): an offline item-fate check first, then a proposal;
   - P2 no;
   - P3 (heading-aware dispatch): an offline study only.
4. The loot drop with the layout: checked, no dependency found (above).
5. The off-screen pointer move: fixed first (ff67e2c). Then the queue in order: v42 (+ the pocket
   escape), v44, v45, v46, then v47 (P4).
6. The Battle Log reader becomes language-independent: in progress (a subagent; English stays
   the validated path; Thai from Batt's lines, local only).

## P1's offline item-fate check (Batt ~19:5x: "P1 offline item-fate check first, then propose")

`p1_itemfates.py` (scratch) over today's 7 runs (v41 x 4, v43 runs 1, 3, 4). Each of our loot steps,
and the items that fell at that kill within 2 cells of the bot's death cell: 710 items.
- **Where the drops lie** (offset from the bot's death cell, share of the items): the centre 31 %,
  (0, +1) 14 %, SE (+1, -1) 12 %, E 6 %, W 5 %, S 5 %, the corners 2-4 % each. 82 % lie inside the
  3 x 3 the step clicks; 18 % outside it (the death cell's own error).
- **Fates:** picked 410 (58 %), "gone" 201 (28 %: vanished early, no monster near; unexplained),
  lost to looters 99 (14 %).
  ➡️ **SUPERSEDED 2026-10-19 21:16 (the loot-fate check below; the judge fixed in 552401e):**
  "gone" was the server clearing an item from OUR view when the GM walked more than 14 cells
  away; the items were LEFT BEHIND on the floor. Without 4 items counted twice: 706 items, picked
  410 (58.1 %), out_of_sight 200 (28.3 %), looters 96 (13.6 %), gone 0.
- **Looter timing:** p25 0.16 s, p50 1.69 s, p75 4.47 s after the loot step's start. A quarter go
  at once, before any order can matter.
- **The order's counterfactual:** for the 72 looter-lost items inside the 3 x 3, the click that
  would have reached their cell before the looter, assuming the step's measured ~0.36 s per click:

  | order | looter-lost items reached first | already-picked items reached later / sooner |
  |---|---|---|
  | today's fixed order (centre x2, SE, W, N, the rest) | 36 | - |
  | P1 ring tour (centre x2, the 8 ring cells in 1-cell steps from the GM's side) | 36 | 107 / 63 |
  | the drops' own frequency (centre x2, (0, +1), SE, E, W, S, corners) | 35 | 86 / 87 |

**Proposal:**
- **Do NOT build P1 for item fates.** The click order inside the 3 x 3 changes nothing for looters
  (36 / 36 / 35), and the ring tour reaches more of today's pickups later. Its only gain would be
  the step's own back-and-forth (0.68 reversals / min); if Batt wants that, it would be a version
  with reversals as the primary and loot as a guard.
- The loot levers the data points to instead:
  1. the 18 % of drops outside the clicked 3 x 3 (the death-cell estimate);
     ➡️ ANSWERED 21:16 (below): 28.4 % on the kill base (P1's 2-cell window missed half), 76 % of
     them because the bot's death cell was off;
  2. the 28 % "gone" (is it real, or our pickups the judge misses?: a judge check first);
     ➡️ ANSWERED 21:16 (below): left behind out of our sight; the judge is fixed;
  3. the time to START the loot (v44, the EXP line, aims at it).

## P3's offline study: heading-aware dispatch (Batt ~19:5x: "P3: offline study only")

`scripts/p3_dispatch_study.py` (offline; packets are ground truth, the bot never imports it), over
11 banked runs: v40 x 4, v41 x 4, and v43 runs 1, 3, 4 (run 2's pocket stall left out). Totals:
630 min, 1,419 kills, 4,376 reversals.

**What it measures.** Every dispatch that SET a target while the runner was searching: 2,264.
- The GM's heading = its last walk leg of >= 2 cells (the reversal ruler's own legs).
- The target's angle from that heading, and its distance in cells.
- The target's fate, followed through re-acquisitions:
  - engaged;
  - lost (target_lost);
  - replaced (another target set first).
- Its cost: dispatch -> the engagement's end, or -> the loss.
- The reversals inside that span, and whether it became a real kill of ours (packets).
- The counterfactual "skip it": its kills are lost; its time is regained at the runs' own pace
  (26.6 s per kill).

**Results:**

| search dispatches | n | share | kills | s each | reversals (/ min of all; share) | skip -> kills / h |
|---|---|---|---|---|---|---|
| all | 2,264 | 100 % | 213 (9 %) | 2.9 | 1,113 (1.77; 25.4 %) | - |
| **> 120 deg behind and > 10 cells (P3)** | **556** | **25 %** | **9 (2 %)** | 1.9 | **516 (0.82; 11.8 %)** | **+2.9** |
| > 120 deg behind, <= 10 cells | 204 | 9 % | 6 (3 %) | 2.6 | 83 (0.13; 1.9 %) | +1.3 |
| side, 60-120 deg | 661 | 29 % | 41 (6 %) | 2.8 | 344 (0.55; 7.9 %) | +2.6 |
| ahead, <= 60 deg | 843 | 37 % | 157 (19 %) | 3.7 | 170 (0.27; 3.9 %) | -3.8 |
| > 120 deg and > 6 cells | 737 | 33 % | 12 | 2.0 | 585 (0.93; 13.4 %) | +4.2 |
| > 120 deg and > 14 cells | 232 | 10 % | 1 | 1.6 | 224 (0.36; 5.1 %) | +1.2 |
| > 150 deg and > 10 cells | 347 | 15 % | 5 | 1.8 | 315 (0.50; 7.2 %) | +1.8 |

- **Fates of P3's group: lost 345, replaced 199, engaged 12.** A target far behind almost never
  becomes a kill: the GM turns, and the target leaves the view or the tracker before the GM
  arrives.
- **P3 as written would remove up to 0.82 reversals / min (11.8 % of all) at no measurable kill
  cost:** 9 kills in 630 min; the estimate is +2.9 kills / h from the time regained.
  - It is an UPPER bound on reversals: some of those turns would happen anyway.
  - The kill estimate assumes the regained time hunts at the runs' average pace.
- **It overlaps the aborted-steer problem** (3.86): 62 % of P3's group ends "lost". So 3.86's
  HOLD (keep a lost target 1.5 s) would hold mostly targets that P3 says should not have been
  taken. That is an interaction to watch in v45's report; it does not change v45's
  pre-registration.

**Proposal (Batt's call; nothing built):** P3 as its own pre-registered version, after v45 and v46:
- while searching, skip a dispatch candidate > 120 deg behind the GM's walk and > 10 cells away
  (the next candidate may go);
- primaries: reversals outside loot / min and kills / h (>= 0.95 x);
- 10-min blocks, as v45 / v46. The threshold stays at 10 cells (> 6 would gain a little more,
  +4.2, but it reaches the near targets the GM can turn to).

## The loot-fate check (Batt's overnight brief, 2026-10-19; offline, a subagent, 20:44-21:15)

Batt: "check the judge's unexplained 28 % 'gone' fate first, then size the 18 % of drops outside
the clicked 3x3 ... Report only; no bot change tonight." Scorer: `scripts/loot_fates.py`
(80c7f55); the judge fix in `arm_judge.item_fates` (552401e). Both are tested on a REAL v43 run 1
case.

**1. "Gone" was the judge's error: those items were LEFT BEHIND, out of our sight.**
- The vanish packet has no reason field. rAthena sends it:
  - to the area when an item is picked up or expires;
  - to ONE client when its character walks more than 14 cells away from the item (AREA_SIZE).
- The archive is our client's view, so it shows all three the same way.
- Over 12 runs (v40, v41, v43; 1,979 drops), all 718 "gone" items had our GM at 15 cells at the
  vanish, or at 14 and at 15 within 0.2 s.
- 50 of P1's 201 came back into view later (the same floor id on the same cell). One fell at
  +352 s and vanished at +412 s: rAthena's 60-s floor lifetime.
- No missed pickups (887 pickup acts = the judge's 887 picked), no other player, no wide looter
  (all 328 looter items had a Poring / Drops within 1 cell).
- The fix: a new fate `out_of_sight`. "Gone" now means "vanished in sight, no monster near": 0
  items in 12 runs. Picked counts are unchanged; looter +16 / -1 over 12 runs.
- Why the step left them (P1's 200): 39 % lay outside the 3 x 3; 87 lay inside, on a cell the step
  skipped (3.3 skips per step: units 3.0); 35 had their cell clicked with no pickup request
  following; 17 fell after the step started. They left our view p50 5.8 s after the step's end.

**2. The drops outside the clicked 3 x 3: 28.4 %, mostly the death cell's fault.**
- The kill base: each loot step matched to its server kill, all the kill's drops; 957 items.
  - Inside the 3 x 3: 71.6 % (picked 484 / 685).
  - Ring 2: 14.4 % (picked 28 / 138).
  - Beyond: 14.0 % (picked 6 / 134).
- The bot's loot cell vs the server's death cell (n 712): exact 37 %, 1 off 28 %, 2 off 14 %, 3 off
  9 %, 4-6 off 12 %.
- 76 % of the outside items lie within 1 cell of the SERVER's death cell. The drops' own scatter is
  tight: 85 % within 1 cell of the real death cell (centre 43 %, SE 17 %, N 9 %).
- **The biggest lever is the death-cell estimate.** With the 3 x 3 on the true death cell, 85 % of
  drops would be inside it instead of 71.6 %: about +14 items / h at today's in-3x3 pick rate, with
  no extra click time. It is an upper bound: the server cell is itself a +-1-cell model.
- Clicking extra cells costs kills. The time is measured at 0.274 s per click and 0.036 s per skip;
  each kill is worth 0.728 items.

  | option | items / h gained (in-sample / held-out) | s per step | kills / h | net items / h |
  |---|---|---|---|---|
  | 5 x 5 (16 ring-2 cells) | 7.4 / 7.7 | 2.25 | -9.0 | +0.9 / +1.1 |
  | top 4 ring-2 cells | 4.2 / 2.6 | 0.78 | -3.1 | +1.9 / +0.3 |
  | item icons outside the 3 x 3 (in-sample only, n 45) | ~5.0 | 0.15-0.33 | -0.6 .. -1.3 | ~+4 |

  - No ring-2 cell is "hot": the outside offsets spread evenly and differ between versions.
- Nothing was built (Batt: report only).

**3. Items lost to looters, per run (the fixed judge; the drops of the engagements' kills):**

| pool | kills | items | picked | looters | left behind | in 3x3 | death cell exact / <= 1 |
|---|---|---|---|---|---|---|---|
| v40 (4 runs) | 500 | 617 | 59.6 % | 13.5 % | 26.7 % | 74.7 % | 41 / 69 % |
| v41 (4 runs) | 456 | 648 | 57.9 % | 14.2 % | 27.8 % | 76.2 % | 41 / 70 % |
| v43 runs 1, 3, 4 | 310 | 405 | 42.0 % | 15.1 % | 43.0 % | 64.8 % | 31 / 58 % |
| v42 (4 runs, the same layout; 2026-10-19 20:21 -> 10-20 00:30) | 454 | 613 | 53.7 % | 13.4 % | 31.0 % | 67.1 % | 39 / 63 % |
| v44 (4 x 55 min, the same layout, both arms; 2026-10-20 00:52 -> 04:39) | 339 | 404 | 58.9 % | 10.9 % | 29.7 % | 75.7 % | 42 / 69 % |

- The v43 drop is NOT looters: it is items left behind, with a worse death cell, and so fewer drops
  inside the clicked 3 x 3.
- The pick rate inside the 3 x 3 is unchanged (70.8 % vs 70.6 %).
- It is not attributable (v43 was not interleaved). v42 has the same layout and will show whether
  it repeats: compare left behind %, in 3x3 % and death cell exact % with looters %
  (`loot_fates.py runs <SID> ...`).
- ➡️ **v42's 4 runs (same layout, same loot step): the drop did NOT repeat at v43's size.** Left
  behind 31.0 % (v43 43.0 %, v40-v41 27-28 %), in the 3 x 3 67.1 % (64.8 %; 75-76 %), picked 53.7 %
  (42.0 %; 58-60 %), looters 13.4 % (15.1 %; 13.5-14.2 %). Per run, looters 4.5 / 14.0 / 17.4 /
  14.3 %: run 1's low share did not repeat. The in-3x3 and death-cell shares are the runs' shares
  weighted by their loot steps. The death cell (exact 39 %) stays the lever named in section 2.
- ➡️ **v44's 4 runs** (both arms; the fix arm's skipped real kills lost their loot, 3.87): looters
  10.9 % (per run 8.0 / 20.7 / 0.0 / 7.0 %), left behind 29.7 %, in the 3 x 3 75.7 %, the death
  cell exact 42 % / <= 1 cell 69 %. Looters swing with the field per run (0 to 21 %), not with
  the version.


## Overnight 19-20 Oct (Batt resting; his brief, until Tuesday 05:00)

Queue: v42 (3.83) -> v44 (3.87) -> v45 (3.86) if time remains. Every run on prt_fild08, natural
spawns, the hunting layout and state applied by the runner, the hard-bar monitor bound to each
runner, a judged screenshot before each run. Full rows and per-arm tables: demonstrations.md 3.83 /
3.87 run logs.

**v42 (3.83: the steer's walk guard from the GM's box + the route tail, with the pocket escape):
4 x 60 min, NOT ADOPTED (check 2).**

| run | kills / h | landing <= 5 s | seen / 10 min | seen -> click p50 | dead calls w/o a death | loot picked (looters) | reversals / min | hard bars |
|---|---|---|---|---|---|---|---|---|
| 1 (20:21) | 113.9 | 76.3 % | 26.0 | 3.36 s | 23.2 % | 62 % (5) | 7.88 | 0 |
| 2 (21:25) | 121.9 | 81.9 % | 27.5 | 3.56 s | 15.8 % | 45 % (17) | 7.91 | 0 |
| 3 (22:26) | 149.9 | 80.8 % | 37.0 | 3.75 s | 15.3 % | 53 % (32) | 6.78 | 0 |
| 4 (23:28) | 133.9 | 72.2 % | 29.5 | 2.96 s | 23.6 % | 55 % (28) | 7.93 | 0 |
| pooled | 129.9 | 77.6 % | 30.0 | 3.41 s | 19.5 % | 54 % (82) | 7.62 | 0 |

- Per arm (pooled): the fix arm moves more while steering (0.434 vs 0.333, 1.30 x: check 1 passes)
  but does not arrive sooner (approach mean 5.29 vs 5.38 s, 0.983 x; the bar was <= 0.90 x).
  Landing 78.0 vs 76.7 %. It clicks twice as often (1,180 steer walk clicks vs 624).
- The base stays v43's + the pocket escape (a bug fix in both arms). The zone rule's gap (run 2:
  16 of 17 zone events did nothing once the GM was already outside) is recorded for a later
  version.
- Creamy hits 2 in 4 h (0.5 / h); hard bars 0 in every run.

**v44 (3.87: dead = the Battle Log's EXP line, with the checked pixel fallback): 4 x 55 min from
00:52** (amendment 2a00832; the chain's `--start-by` 03:50). The first start (00:44) stopped in the
runner's loot clear on two identical equipment items in a row, a false "did not drop"; fixed in
`gm_state.tab_changed` (ee2dec5, tested) before run 1.

| run | kills / h | landing <= 5 s | seen / 10 min | seen -> click p50 | dead calls w/o a death | loot picked (looters) | reversals / min | kill -> loot start mean / p50 | hard bars |
|---|---|---|---|---|---|---|---|---|---|
| 1 (00:52) | 134.0 | 83.8 % | 26.0 | 2.74 s | 13.0 % | 54 % (9) | 7.14 | 1.35 / 0.57 s | 0 |
| 2 (01:49) | 126.6 | 70.3 % | 28.0 | 4.05 s | 21.5 % | 58 % (29) | 6.97 | 0.96 / 0.53 s | 0 |
| 3 (02:45) | 76.3 | 80.8 % | 20.0 | 2.39 s | 10.6 % | 65 % (0) | 6.99 | 1.13 / 0.57 s | 0 |
| 4 (03:42) | 70.8 | 73.8 % | 16.0 | 3.17 s | 22.7 % | 63 % (6) | 7.21 | 1.39 / 0.66 s | 0 (Creamy 7) |
| pooled | 101.9 | 77.1 % | 22.5 | 3.09 s | 17.1 % | 59 % (44) | 7.08 | 1.20 / 0.58 s | 0 (Creamy 7) |

**v44 verdict (04:4x, 4 runs pooled, `arm_judge.py expdead`): NOT ADOPTED.**
- Check 1 PASS: kill -> loot start mean, fix 0.668 s vs base 1.763 s (0.38 x; bar <= 0.60 x).
- Check 2 FAIL: dead calls without a real death, fix 14.3 % vs base 19.9 % (0.72 x; bar <= 0.55
  x; inside the null).
- Check 3 FAIL: loot picked at our kills, fix 50.2 % vs base 62.4 % (-12.2 points; bar -5).
- Check 4 PASS (landing 78.4 vs 75.8 %); check 5 PASS (hard bars 0).
- The rule: faster but not truer, and it costs loot. The EXP line itself is a sure, fast death
  (precision 369/372 on the night; lag p50 0.27-0.35 s). What failed is the CHECKED pixel
  fallback beside it:
  - its death-cell "ok" passed live targets;
  - its 1.0-s wait skipped 24 real kills whose loot was then lost.
- **The base stays v43's + the pocket escape.**
- Kills / h followed the field: runs 3-4 had the sparsest fields of the night (seen 20 and 16 /
  10 min).

**Gap to Batt re-ranked on v44's 4 runs** (`search_study.py` + `conversion_phases.py compare`;
35.3 vs 12.0 s per kill = 23.3 s; v42's split in brackets):

| cause | s per kill | share | v42 |
|---|---|---|---|
| search speed: no-target stretch mean 16.3 vs 6.3 s, x 1.36 stretches per kill | +13.6 | 58 % | +6.7 (43 %) |
| conversion (target-in-view s per kill 13.2 vs 6.8) | +6.4 | 27 % | +6.4 (41 %) |
| extra no-target stretches (1.36 vs 0.82 per kill) x 6.3 s | +3.4 | 15 % | +2.7 (17 %) |

- Conversion is the same as v42's to 0.02 s. Its parts: approach (turn -> in range) +3.57,
  never attacked +2.11, in range -> click +0.47, client walk-up +0.35, notice -> turn +0.31,
  unnoticed +0.14, attacked not killed +0.10, hit -> kill -0.22, loot -0.50.
- Search grew with the sparse fields. Re-swept <= 120 s 47 % vs Batt 27 %; fresh cells / s in
  no-target time 79 vs 102; reversals 7.1 vs 3.6 / min; free targets attacked <= 10 s 40 % vs
  78 %.

**End state (04:41):** the chain done at 04:39:00. Then:
- the standard layout and Base Lv 1 / Job Lv 1 (`@resetstat`, the GM's fixed state confirmed);
- route_previewd stopped;
- a judged screenshot; `/health` ASSIST, no lease, bot_agents [];
- no runner, monitor or chain process.

## Loot block (Batt 2026-10-20 ~09:1x: LOOTING EVERY DROP; reports ~13:00 and ~18:00)

Batt: "the walking and striking are good enough for now; the focus is LOOTING EVERY DROP ... if
the rare item falls and the bot doesn't pick it up before it vanishes, the whole grind is wasted."
The block's primary is LOOT COMPLETENESS (items picked / dropped by our kills, packets, fates
split); kills / h is a guard (>= 0.85 x base).

**The server's rules** (pinned rAthena e985006; demonstrations.md 3.89):
- floor items vanish after 60 s;
- the killer's priority is 3 s, then 2 + 2 s (boss / MVP 10 + 10 + 2), NOT ~30 s;
- monster looters ignore the priority (loot_range 12, oldest first);
- a looter's death drops every item it took.

**The bot-vs-Batt loot line** (`loot_complete.py`, every kill of ours; Batt's demo 61 / 63):

| | completeness | left behind | looters | expired |
|---|---|---|---|---|
| Batt's demo | 96.8 % | 0 % | 3.2 % | 0 % |
| bot v38-v44 (4 runs each) | 46.2-53.5 % | 28.4-37.2 % | 12.6-18.7 % | 0-1.3 % |

- On the kills the bot looted, 30-32 % of the items are still left behind.
- Kills with no loot step hold 11-15 % of the items.
- A loot step started < 0.7 s after the kill loses 3-4 of its 9 cells to the dying sprite.

**Order:**
1. v48 (3.89, pre-registered 09:37): dead = the EXP line alone, the target kept;
2. the death-cell study, then a version;
3. no item left behind (HAND cursor, loot memory), after a study of why items are left;
4. looter recovery;
5. v45, v46, P3, v47.

**Why items are left behind (step 3's question, `scripts/left_behind.py`, read 2026-10-20 ~09:5x;
v42 + v44, 8 runs, every item of our kills: 1,196 items, picked 580 = 48.5 %).** Each item that
was not picked gets the first cause that holds:

| cause | items | of all items | its fate: left behind / looter / expired |
|---|---|---|---|
| in the step's 3 x 3, its cell never clicked (skipped: a unit, pink, the view; or the step's cap) | 193 | 16.1 % | 106 / 81 / 6 |
| outside the 3 x 3, within 1 cell of the SERVER's death cell (the bot's death cell was off) | 159 | 13.3 % | 113 / 43 / 3 |
| no loot step for its kill (skipped, given up, or no engagement owned it) | 132 | 11.0 % | 92 / 40 / 0 |
| outside the 3 x 3, farther from the death cell | 74 | 6.2 % | 56 / 18 / 0 |
| fell after its kill's loot step had ended | 51 | 4.3 % | 40 / 10 / 0 (1 gone) |
| its cell clicked, but the click became a walk (no pickup) | 7 | 0.6 % | 4 / 3 / 0 |

- **The answer: the loot step ends early or looks in the wrong cells.** It is NOT mostly the next
  engagement pulling the GM away.
  - Unclicked cells inside the plan and drops just outside it make 29.4 % of all items, 57 % of
    those not picked.
  - For the left-behind items of looted kills, the first non-loot click after the step was the
    search 243 times, the next engagement's steer 62, and no click before the item left our view
    14.
- **Time:** they left our view p50 5.8-7.9 s after the step's end (p25 3.6-5.1 s). A loot memory
  that returns within the 60-s lifetime has ~50 s.
- **What this means for the order:**
  - step 3's "end the step only when the drop area shows no item" addresses the 16 % unclicked and
    part of the 6 % farther;
  - step 2's death-cell estimate addresses the 13 %;
  - v48 addresses the 11 % with no loot step.

**Step 2's offline study: the death-cell cues** (`scripts/deathcell_cues.py`, read 2026-10-20
~10:0x; v42 + v44, 8 runs, 659 kills of ours a loot step followed).
- **Method:** the target is followed through the detector's per-frame boxes from the
  engagement's last strike click, with no packets. Each cue's box foot becomes a cell with the
  camera on our GM's cell at that frame (packets, interpolated, 0.65 s earlier). The client draws
  the world behind the server: lags of 0 / 0.25 / 0.5 / 0.65 / 0.8 / 1.0 s were tried, and
  0.65 s reproduces the runner's own death cell best (same cell 43 %, within 1 77 %).
- **Results** against the server's death cell (Batt's HP-bar cue needs the recorded frames: not
  in this version):

  | cue | kills | exact | within 1 | drops in its 3 x 3 |
  |---|---|---|---|---|
  | box at our last damaging hit | 484 | 31.2 % | 61.0 % | 64.2 % |
  | box at the kill | 637 | 41.0 % | 69.5 % | 75.7 % |
  | median box cell, 0.6 s before the kill | 325 | 52.6 % | 78.8 % | 87.7 % |
  | box at the EXP line | 606 | 42.9 % | 71.9 % | 76.1 % |
  | box at the line + 0.5 s (v48's loot start) | 611 | 43.0 % | 72.3 % | 76.4 % |
  | the followed box's LAST frame (today's "anim" rule) | 659 | 43.4 % | 72.4 % | 77.2 % |
  | the runner's own loot cell (its own position) | 659 | 40.5 % | 66.5 % | 71.1 % |

- **Paired, on the SAME kills:**
  - The 325 kills with boxes before the kill: last box 61.8 % exact, 90.4 % of drops in its
    3 x 3; the 0.6-s median 52.6 % and 87.7 %; the runner's cell 48.9 % and 77.7 %.
  - All 659: last box 77.2 % against the runner's 71.1 %.
- **Reading:**
  - No box TIMING beats today's last-box rule, and the box at the last hit is the worst.
  - What separates the runner from the same rule offline is the runner's belief of its OWN cell
    (6 points of drops in the 3 x 3 over all kills, 13 on the kills it saw die).
- **Where the loot clicks land** (`left_behind.py --aim`, the same 8 runs: each loot click that
  became a walk, its walk request's cell against the aimed cell):

  | loot clicks | n | exact | within 1 cell |
  |---|---|---|---|
  | the step's FIRST click | 538 | 48.5 % | 82.7 % |
  | every later click | 4,510 | 10.8 % | 52.3 % |
  | our GM walking at the click (packets) | 1,690 | 3.6 % | 28.4 % |
  | our GM standing | 3,358 | 20.5 % | 69.2 % |
  | all | 5,048 | 14.9 % | 55.6 % |

- **The main defect is the aim of the step's LATER clicks, not the death cell.**
  - The first click goes where the dying sprite was, in the frame the runner saw.
  - Each click then walks the GM. The next click is aimed from a position belief that no longer
    matches the drawn camera, which lags the server by ~0.65 s.
  - This is the same mechanism as the steer's "clicks while moving land ahead".
- **What it means for the order:** a death-cell version that changes the box timing has nothing
  to gain. The lever is to aim each later loot click in the CURRENT frame:
  - the items' own icons, or the HAND cursor (Batt's step 3), which the frame shows wherever the
    GM is;
  - or clicking only from a drawn standstill.
