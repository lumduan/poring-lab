---
title: "Labels v2: a warp class, verified hard negatives, new species and visual domains"
status: PROPOSED
date: 2026-10-09
owner: Batt
extends: docs/phase3-plan.md
gate: "Batt 2026-10-09 ~13:15 approved the warp class (auto-labelled from L3) and the hard negatives verified against packets, in the v2 label set. The training round itself is a later decision (GPU, R1-R3)."
---

# Labels v2

**Why (Batt, the iz_dun00 held-out run, 2026-10-09 13:03, HUD on):**
- **Two false positives** of the v0-PNG detector:
  - the WARP PORTAL boxed as "monster 25 %";
  - a wall TORCH flame boxed as "monster 29 %".
- **A probable false negative:** a Hydra-like creature next to a pillar had no box.
  - v0 / v1 never saw a Byalan species. The training sessions are prt_fild08 and prt_church only.

## 1. A `warp` class, auto-labelled (approved)
- **What it is:**
  - warp portals look the same on every map;
  - their cells are known from the L3 warp data (`data/kb/route.json` `warps`: cell, span, destination);
  - their position on screen comes from the camera model, the same projection the v1 labels use.
- **How the labels are made:**
  - Each frame's portals are the L3 warp cells on the frame's map, projected through the camera at the
    GM's packet position.
  - Each box is a fixed portal size, measured once on banked frames (like v0's monster 44 × 40).
  - A portal outside the view, or covered by a UI window (`route_preview.UI_WINDOWS`), is not labelled.
- **What it is for:**
  - the detector stops calling portals monsters;
  - warp boxes may feed walk@17's warp-area blocking (Batt), next to the L3 warp cells and spans the
    planner uses.
  - The portal cursor stays the only allowed shape for an intended portal click.
- **Thresholds:** a per-class confidence threshold may follow (e.g. stricter for `warp`). Until then the
  gate keeps 0.25 for every class (Batt 2026-10-09).

## 2. Hard negatives, verified against the packets (approved)
- Torches, flames, animated decorations and other scenery the detector boxed are added as
  BACKGROUND, from banked frames of the maps that have them.
- **Verified:** a candidate background region is accepted only when the packets show NO unit (monster,
  NPC, player) whose projected box overlaps it on that frame. No real unit is ever labelled background.
- **The candidates come from:**
  - the HUD scene log's boxes (`/dev/shm/poring-lab-route/scene.jsonl`: class + confidence);
  - the walk runs' detection logs (from 2026-10-09: every detector batch with scores and classes,
    `detections.jsonl` per session);
  - each matched to the packets' world state at that frame.

## 3. New species and visual domains
- **The training scope:**
  - ADR-0020 13.3: all species on the workflow's maps;
  - 3.28's per-map walk-readiness: a map is walk-ready only when all its L3 species are in scope.
- **The next round adds:**
  - iz_dun00's six species (Plankton, Marina, Kukre, Hydra, Vadon, Black Mushroom);
  - the visual-diversity maps' species (moc_fild, payon / pay_fild, xmas / Lutie, a dark Glast Heim level).
  - Their frames are banked by the held-out and diversity runs.
- Spawn sessions for unseen species, as M4 / M7 did, come where the runs alone are not enough.
- ➡️ **TOWN NPC SPRITES (Batt 2026-10-09 ~16:10):** "The detector does NOT box the town NPCs at all
  ... Bank these frames for the next training round (NPC class from packets)."
  - The NPC class comes from the packets: each NPC's cell (entity_appear, objtype NPC) projected
    through the camera at the GM's packet position, as the v1 labels do.
  - Only units the packets place are labelled. An NPC the packets do not list (a client-side
    decoration) is never labelled NPC.
  - **The frames to bank (2026-10-09, RDP):**
    - the talk@1 calibration drives in prontera (the city guide's surroundings) and prt_church
      (`/dev/shm/poring-lab-demo/20261009T15*-demo-talk-cal-*`, `…T160329-…-guide`);
    - the 3.29 / 3.29a town runs' snapshots and detection logs;
    - Batt's 16:04 frame (the console screenshot).
  - These sessions live in tmpfs, so banking them to durable storage is a parent step, done in a
    quiet IO window (2026-10-09 16:10: an IO-guard trip).
  - The detector's per-sprite recall on them is measured by walk@17 item 5's test (3.32).

## 4. Open (Batt)
- When the v2 round trains (GPU), and on which sessions.
- The warp box size and whether `warp` keeps a separate head or shares the unit classes' head.
- Per-class thresholds.
