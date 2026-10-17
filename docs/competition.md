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

The order alternates between rounds (round 0: bot first; round 1: agent first).

**The judge is the same for all:** `flow_judge` from the packets offline. Hard bars (NPC contact,
non-target hit, map change) apply to every session.

## Leaderboard (kills / h; landing within 5 s; loot picked / dropped; hard bars)

| round | BATT (human, pixels) | AGENT (packet-assisted) | BOT median 10' | BOT best 10' | BOT full run |
|---|---|---|---|---|---|
| R0 (bot v20) | 300 / 100 % / 62 of 64 / - | 24.6 / 4 of 5 / 6 of 14 / pass | 120 / 80 % / 2 of 30 / pass | 192 / 90 % / 10 of 57 / pass | 140.9 / 85.2 % / 41 of 218 / 1 non-target |
| R1 (bot v21) | (fixed) | 38.3 / 4 of 5 / 4 of 6 / pass | 96 / 81 % / 4 of 25 / pass | 120 / 76 % / 6 of 30 / pass | 100.8 / 78.8 % / 34 of 156 / pass |
| R2 (bot v22) | (fixed) | pending | pending | pending | pending |

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

## What the agent's play taught (both rounds)

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

**v21: loot by frame difference** (Batt's work order item 1).
- Compare the area around the death spot just before the death and ~0.5-1 s after: new small
  blobs are the drops.
- Hover each blob centre, and click while the cursor is the HAND.
- **Bars:** picked >= 80 % of the drops (packets), kill -> last pickup <= 3 s.
