---
title: "walk@17: the typing policy, warp areas, and long walks (design; pre-registered separately before any run)"
status: "APPROVED by Batt 2026-10-09 (~13:42, ~14:00); BUILT (scripts/walk17.py, b7cf790) and PRE-REGISTERED as demonstrations 3.32; NOT run. SIX points wait for Batt before its tuning runs (3.32 items 1-6: the guard's repeat rule vs /where once per need; iz_dun00 has no L3 warp list; the harness start draw can land in a warp area; the server path across a warp area, measured 0; ADDED 15:05: 3.29a town's 2 NPC contacts with the decision code walk@17 keeps (E); a chain must judge the client's UI state between runs)"
date: 2026-10-09
owner: Batt
extends: docs/demonstrations.md
gate: "Design only. walk@17 is built, pre-registered (its own section in demonstrations.md, with tuning seeds and the readiness bar of 3.28) and tuned BEFORE the visual-diversity set (Batt 2026-10-09) and the tour test (3.31) run with it. walk@15 and its held-out runs stay unchanged."
---

# walk@17: the design

walk@17 = walk@15's decision code + the changes below. Each one answers a finding or a decision from
2026-10-09.

## A. Position: the minimap first, /where only where there is none (Batt, 13:42)
- **The finding:** walk@15 already READS the minimap readout at every route start and before every
  click (`read_position`, `poring_env.selfpos`). The reader read 12 / 12 sampled iz_dun00 route
  snapshots.
  - Its RELOCALISATION, the doubt path (no move, a no-entry cursor, unconfirmed reads), always types
    /where through where@2. That pattern is an "/ex" separator, then /where twice.
  - That is what the 13:42 screenshot shows, with the minimap readout on screen.
- **walk@17:**
  1. The relocalisation reads the MINIMAP readout (two equal reads on fresh frames, passive) on every
     map that shows one.
  2. Only where the client shows no coordinates (indoors) does it use /where: once per need
     (`where_fix.fix_once`), within the run's /where budget, never retyped quickly, no separator
     (the typing guard refuses one).
  3. A miss falls back to dead reckoning and landmarks; the route may decline rather than type again.
- **Checked per map in the visual-diversity set:** the minimap reader on dungeon, desert and snow
  minimaps (different colours behind the readout). Per map: exact / refused / wrong against the
  packets.

## B. Warp areas are not walkable for a walk (held-out guild, route 0)
- The goal (77, 42) lay inside alberta_in's exit warp trigger area (span 2 × 5 around (78, 44)), and
  the GM was warped to alberta.
- **walk@17's planner** blocks every L3 warp trigger area (cell ± span), except for a route whose
  intent IS the portal.
- **Its click step** treats a picked cell inside a warp area as refused.
- The `warp` detector class (labels v2) may add its boxes once it exists (Batt).

## C. Long walks: chained legs through waypoints (Batt, 13:42: the tour test, 3.31)
- **A route longer than one leg** (`PLAN_MAX` = 48 steps) is split into legs at waypoints.
  - The waypoints are on the full A* path, about every 40 steps, each a walkable cell not in a warp
    area.
  - Each leg is walked as today.
  - The per-click distance stays at most 14 server steps (the server's unconditional limit;
    `docs/planning/poring-nav.md`). The rules click at most ~12 cells ahead.
- Until poring_nav lands, the leg split is walk@17's own and is cross-checked against the A* (the
  cross-check test's method).

## D. The harness (already built, 3.29a)
- **CLEAN's `@killmonster2`** only when needed: a monster seen now, or one the previous route saw.
- **The typing guard:**
  - no 3rd identical line in a row;
  - no filler;
  - a minimum interval;
  - /where once per need.
- **`open_chat`** recovers the post-refusal chat state (after the live probe).
- **The detector** logs every batch (class + score).

## E. Not changed
The unit gate's 0.25 threshold (Batt), the NPC clearance (walk@15's D), the side cells (E) and the
TALK-read NPC substitute.

➡️ **2026-10-09 ~15:05: a safety finding against E (demonstrations 3.29a, town re-run).** walk@15's
decision code, which walk@17 keeps, made TWO NPC contacts in 50 routes in prontera.
- Both times the cursor read WALK and the detector envelope held 0 units.
- One came through the TALK-read NPC substitute: its remembered talk cells were one column off the
  NPC.
- Listed for Batt as 3.32 item 5. "Not changed" stays the design until he decides.

➡️ **DECIDED 2026-10-09 ~16:15 (Batt): a static L3 NO-CLICK layer** joins walk@17's gate. The L3 NPC
cells and the neighbours their clickable footprint covers are refused, independent of the detector.
- Batt: "talk@1 finds NPCs from L3 ... + the camera model ... the detector isn't involved. walk@15
  avoided NPCs with the detector (blind to town NPCs) and remembered TALK cells (one column off)."
- The cursor and detector layers stay for moving / hidden NPCs and units.
- The targeted town test (3.32 item 5) measures whether the layer alone removes the contacts.
- It enters walk17.py as a recorded amendment before the tuning runs.
- ➡️ The offline analysis, the layer (`scripts/npc_noclick.py`, PROVISIONAL) and the targeted test:
  `docs/planning/npc-click-test.md` (merged 70e851d). The layer needs a COMPLETE L3 NPC list per map
  (KB extension P1), and the town flags (job 722) are missing today.


**DECIDED by Batt 2026-10-09 ~14:00:** walk@16's F is NOT carried over ("no measurable effect beyond
run-to-run noise; fewer rules"). If goals next to NPCs turn out to matter later, a fix comes with a
targeted test that can measure it. tour@1 (3.31) and the minimap-first relocalisation (A) are approved
as written.

➡️ **BUILT and PRE-REGISTERED (2026-10-09 ~14:30 ICT):** `scripts/walk17.py` at b7cf790, scored by
`scripts/walk17_score.py`, pre-registered as `docs/demonstrations.md` 3.32 (tuning seeds
20261150–53; held-out seeds 20261154–57 reserved, used only if READY). Not run. 3.32 lists what the
build found for Batt before any run: the typing guard's repeat rule leaves walk@17 at most two
/where per run (the expected indoor loss); iz_dun00 has no L3 warp list (walk@17 refuses to start
there); the harness's start draw can land inside a warp area (alberta_in, iz_dun00); and the
server's own path across a warp area (measured: 0 of ~40,000 click cells).
