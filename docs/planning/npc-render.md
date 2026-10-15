---
title: "The NPC render path: every static NPC drawn from game data (L3 + the client's sprites + the camera), its design measurements, and a DRAFT pre-registration"
status: PROPOSED (its check PRE-REGISTERED: demonstrations.md 3.38) -- SCORED 2026-10-15: B FAILS on B-SAFETY (TALK outside 3.56 % vs <= 1 %), A INCONCLUSIVE on n; the region is not used
date: 2026-10-13
owner: Batt
extends: docs/planning/labels-v2-plan.md
related: [npc-click-test.md, cursor-robust.md, ../phase3-plan.md, ../demonstrations.md, ../adr/0015-phase4-planner-linter-executor.md, ../adr/0021-external-servers.md]
gate: "Offline build + measurement on EXISTING (design) data only. Nothing was run live, nothing was clicked, no GPU. The walk gate is NOT changed and labels v2 does NOT use the render yet. Section 6 is a DRAFT pre-registration for the parent to review and commit to docs/demonstrations.md; it binds nothing until then."
---

# The NPC render path

**Batt's direction (2026-10-13, forwarded by the parent, verbatim):** "Batt's point for NPCs: use
the GAME DATA, not the detector. Each NPC line in the server scripts gives map, x, y, FACING
DIRECTION (fixed) and the sprite id. With the client's sprite files (decoded locally, never
committed) and the camera model, render each NPC's exact expected appearance and position on
screen. Use it for: 1. the walk gate's NO-CLICK region = the rendered sprite's pixel mask (union of
its idle animation frames), not a box or a cell guess; measure it against the clickable area found
in item 5's probes; 2. labels v2 for NPCs, generated per frame (exact boxes), replacing most of the
NPC collection; 3. occlusion: compare expected vs observed pixels. Exceptions to handle: animated
idle NPCs (union of frames), hidden/undrawn NPCs (already in L3), moving NPCs (detector + tracker),
camera rotation (the bot keeps the default camera; detect and refuse a rotated camera), external
servers (only when the scripts match, per ADR-0021). This is the 'N1-N3 sprite path' in labels-v2:
make it the first NPC step, with a pre-registered check of the rendered positions/masks against
packet truth and live hovers."

**What the design data says, in one paragraph** (section 3):
- **Positions: the render is right.** Where the packets put our GM on a known cell, the rendered
  NPC sprites sit within a median 1.4 px of where the client draws them outdoors (98.5 % within
  6 px, 134 matches) and 4.1 px indoors (99.5 % within 12 px, 214 matches). Indoors the miss grows
  linearly away from the screen centre (to ~9 px at the edges): a small indoor-camera error.
- **k: 0.14 fits NPC sprites better than 0.1333**, on every one of 348 paired matches (median NCC
  0.76 against 0.58).
- **L3 is the server's truth:** for all 3,214 rendered NPCs the packets showed, the cell, the
  sprite and the FACING agree with the script line.
- **The clickable area is NOT the drawn pixels.** On cursor@2's 2,904 usable labelled hovers, the
  drawn mask (union of the idle frames) holds only **39 %** of the points the client answers TALK.
  The client answers TALK about a cell beside a slim NPC and ~16 px below its feet.
  - So Batt's item 1 ("NO-CLICK = the pixel mask") is **not safe as written**: the mask would let
    the walk gate click 61 % of the TALK points.
  - A simple box around the feet fitted on the same data (42 px either side of the feet, from
    8 px above the sprite's top down to 16 px below the feet) holds **98.5 %** of the TALK points
    (none near an unrendered NPC) and 11.8 % of the other answers. It is IN-SAMPLE: the DRAFT
    pre-registration (section 6) tests it on fresh hovers.
- **Prontera's guild flags (job 722) cannot be rendered:** the client draws them from a 3-D model
  (`guildflag90_1.gr2`), not an SPR/ACT. They stay UNSUPPORTED (fail closed).

## 1. What is built (branch feat/npc-render; offline)

| piece | what it does | tested on |
|---|---|---|
| `scripts/npc_render.py` `render` | (map, our cell, camera path rdp / s2) -> every L3 NPC rendered from game data | synthetic sprites, KB, camera fit |
| `npc_render.render_scene` | the pure core: `predict_sprite(Actor(cell, dir, IDLE), with_mask=True)` per drawn NPC | synthetic |
| `RenderedNpc` | the union mask, the envelope box, `contains` / `in_box` / `distance`, the PROVISIONAL `hit_box` | synthetic |
| `RenderResult.no_click(u, v)` | mask OR PROVISIONAL hit box, nearest the camera first; `complete` says whether it may be trusted | synthetic |
| `masked_ncc`, `match_offset` | the rendered sprite (grey, its opaque pixels) against a frame within +-R px, FFT | a shifted synthetic sprite |
| `CameraLog`, `camera_events`, `read_input_window` | the OFFLINE camera guard over the backend's input log, by byte ranges | synthetic logs |
| `pixel_camera_check` | the RUNTIME camera guard's rule, built offline: rendered NPCs vs the frame | synthetic matches |
| `scripts/npc_render_measure.py` `align` / `click` / `camera` | section 3's measurements | the design sessions |
| `npc_sprites.py build --measure-map MAP` | a MEASUREMENT-ONLY sprite table (every drawn NPC of MAP); refused inside any `data/kb` | synthetic |

- **Tests:** `services/backend/tests/test_npc_render.py` (17) and `test_npc_sprites.py` (+2). The
  full Python suite passes.

### 1.1 Per NPC (the data)

- **From L3** (`data/kb/first_workflow.json`, every NPC line the server loads; rAthena GPL, local):
  map, cell, the SCRIPT's facing (the npc line's `dir`, rAthena's 0 = north, counter-clockwise),
  the sprite id, the drawn mark (True / False / conditional), file:line. The map's list is
  declared complete by `npc_cells.json`.
  - The facing is now carried by `npc_cells.json` rows and `npc_noclick.StaticNpc` too (3cb59fc).
- **From the client** (decoded locally into `/dev/shm`, never committed): N1's job -> sprite stem
  (three sources agree) and N2's SPR / ACT.

### 1.2 The render rule

- `predict_sprite(Actor(cell, dir, IDLE))` with no phase: the box is the ENVELOPE of every idle
  frame of the drawn direction, and `with_mask=True` gives the UNION of their opaque pixels.
  That is Batt's "union of its idle animation frames".
- The drawn direction is `camera.displayed_direction(dir, yaw)` = (look_heading(yaw) + 12 - dir)
  % 8 (nostalro act.rs).
- The anchor is the cell centre at the client GAT's altitude, projected through the backend's
  fitted camera (`camera_rdp.json` / `camera_console.json`; indoor maps rotated +45 degrees and
  closer). The sprite is a billboard scaled by f / z x k about it.
- `DEFAULT_K` is 0.14 (korangar; v1's labels). Section 3.2 measures it against 0.1333.

### 1.3 Fail closed

- **The whole render is refused** (`Unsupported`): a map not in the KB, its GAT not extracted, the
  indoor table missing, no camera fit, an unknown camera path.
- **An NPC is unsupported** (listed with why, never guessed): no facing in L3, its sprite id not in
  the job -> stem table, its SPR / ACT not decoded.
  - `complete` is False while an unsupported NPC is anchored on the screen or within 160 px of it,
    or the map's L3 list is not declared complete. The walk gate must refuse then.
- **Conditional NPCs** (the script hides them at start; their state at run time is unknown) are
  listed apart and never rendered. Undrawn ones (hidden classes, drawn False) and the portal
  (the `warp` class) are not NPC sprites.
- **Beyond the server's view area** (more than 14 cells from us, Chebyshev: rAthena's
  `area_size`): never sent, so never drawn and never clickable, even when the cell is on screen
  (measured, 3.2). Listed as `beyond_area`; they never make a render incomplete.
- **Warnings:** alberta and morocc (`gat_unverified`, labels-v2-plan 7.6: the client GAT differs
  from the server's).

## 2. The data used (design data only; exact paths)

- **Sprites:** N1 / N2 as merged (46 sprites) are not enough to render whole views, so a
  MEASUREMENT-ONLY table was built in /dev/shm:
  - `npc_sprites.py build --out /dev/shm/poring-lab-tmp/npc-render/n1-measure.json
    --measure-map prontera --measure-map prt_church --measure-map alberta --measure-map
    alberta_in --measure-map prt_fild08 --measure-map iz_dun00`: **91 sprites**, the three
    sources agree for **90**.
  - The 91st is **722, the guild flag: the client names `guildflag90_1.gr2`**, a 3-D model, and
    there is no SPR / ACT for it. It stays unsupported.
  - `sprite_catalog.py --npc-from <that table> --decode-mixcrypt --out
    /dev/shm/.../n2-measure-catalog.json --names-out /dev/shm/.../n2-measure-names.json`: 90 jobs
    decoded.
  - `data/kb` was NOT widened (the option refuses it; see section 7 for the one slip).
- **(a) alignment:** every 2026-10-09 / 10-10 session on the NAS (62, by name from a plain `ls` of
  `/mnt/poring-lab-datasets`, the list in /dev/shm/poring-lab-tmp/npc-render/align-sessions.txt)
  plus v1's three PNG sessions (20261003T215314-console-s2-outdoor,
  20261004T054429-console-s2-outdoor, 20261004T103815-console-s2-indoor-v2).
- **(b) clickable area:** cursor@2's three probe sessions
  (/mnt/poring-lab-datasets/20261010T142556-demo-npc-click-probe-prontera,
  ...154307-demo-npc-click-probe-prt-church, ...162806-demo-npc-click-probe-alberta).
  - The labels: `/dev/shm/poring-lab-tmp/cursor2/truth/items.json` +
    `/dev/shm/poring-lab-tmp/c2-labellerA/labels.json` (A and B agree on all 8,190 images); the
    label of each probe's grab 0.
- The three probe sessions are the RDP path. The alignment includes the S2 path through v1's PNG
  sessions (64 matches); **S2's clickable area is not measured.**

## 3. The measurements

### 3.1 How to reproduce

    export PYTHONPATH=<worktree>/scripts:<worktree>/packages/poring_dataset/src:...
    D=/dev/shm/poring-lab-tmp/npc-render
    npc_render_measure.py align $(sed 's#^#/mnt/poring-lab-datasets/#' $D/align-sessions.txt) \
      --names $D/n2-measure-names.json --kb <main>/data/kb --out $D/align.json
    npc_render_measure.py click <the three probe sessions> \
      --items /dev/shm/poring-lab-tmp/cursor2/truth/items.json \
      --labels /dev/shm/poring-lab-tmp/c2-labellerA/labels.json \
      --names $D/n2-measure-names.json --kb <main>/data/kb --out $D/click.json
    npc_render_measure.py camera $(sed 's#^#/mnt/poring-lab-datasets/#' $D/align-sessions.txt)

- `align`'s defaults: k 0.14 (and 0.1333 beside it), radius 24 px, at most 15 frames per session
  (spread over time), every 10th frame of a PNG session, a match counts at NCC >= 0.5.

### 3.2 (a) Rendered positions vs the observed pixels (packet truth for our GM's cell)

- **What is matched:** frames where the packets put our GM on the same whole cell for 0.5 s;
  every drawn L3 NPC rendered from that cell whose box lies wholly on screen, clear of the UI
  windows (+24 px), of every other unit (our GM included) and of any unrendered NPC. 241 frames
  from 27 sessions, 373 sightings; **348 confident** (NCC >= 0.5, the best offset not on the
  search window's edge): prt_church 207 (RDP 195, S2 12), alberta 67, prt_fild08 52 (S2),
  prontera 15, alberta_in 7.
- **Excluded before any pixel was read** (sightings): near the UI 934; partly off screen 488;
  near an unrendered NPC (the 722 flags) 487; overlapping a unit 314. Frames: 142 in GM-command
  windows, 17 not standing, 3 on a map outside the KB. Sessions: 16 without banked frames, 5
  without packets.
- **The offsets** (observed - rendered, px; confident matches):

  | group | n | median dx / dy | dx p10..p90 | dy p10..p90 | median distance | within 3 px | within 6 px | within 12 px |
  |---|---|---|---|---|---|---|---|---|
  | **outdoor** | 134 | +1 / -1 | 0..+2 | -3..0 | **1.4** | 0.873 | **0.985** | 0.993 |
  | **indoor** | 214 | +1 / +2 | -6..+4 | -3..+5 | **4.1** | 0.276 | 0.790 | **0.995** |
  | alberta | 67 | 0 / -1 | 0..+1 | -2.4..0 | 1.4 | 0.910 | 1.000 | 1.000 |
  | prt_fild08 (S2) | 52 | +1 / -1 | 0..+2 | -3..0 | 1.4 | 0.788 | 0.962 | 0.981 |
  | prontera | 15 | +1 / -1 | 0..+1.6 | -2..0 | 1.4 | 1.000 | 1.000 | 1.000 |
  | prt_church | 207 | +1 / +2 | -6..+4 | -3..+5 | 4.1 | 0.285 | 0.792 | 0.995 |
  | alberta_in | 7 | +4 / -1 | -0.8..+5.4 | -4.2..+1.4 | 5.1 | 0.000 | 0.714 | 1.000 |

- **By distance from the screen centre** (median distance; within 6 px):
  - outdoor: 0-150 px 1.0 (1.00); 150-300 2.0 (0.98); 300-450 2.2 (1.00); 450+ 2.2 (0.96). Flat.
  - **indoor: 0-150 px 2.2 (1.00); 150-300 4.4 (0.77); 300-450 5.7 (0.69); 450+ 8.6 (0.13).**
  - Indoor by side: left third dx +4 / dy -3; middle +1 / +2; right third **dx -3 / dy +4**
    (p90 10 px).
- **A linear field, not noise** (least squares, offset ~ a + b (u - 640) + c (v - 360)):
  - indoor dx = +0.6 - 0.96 % x (u - 640) - **2.75 % x (v - 360)**; dy = +0.2 + **1.22 % x
    (u - 640)** - 0.34 % x (v - 360); residual SD **0.8 / 0.5 px**. A small rotation and scale
    error of the indoor camera produces exactly this kind of field.
  - outdoor dx = +0.6 + 0.06 % x (u - 640) - 0.26 % x (v - 360); dy = -1.3 + 0.26 % x (u - 640) +
    0.68 % x (v - 360); residual SD 0.6 / 1.2 px: essentially a constant (+0.6, -1.3) px.
  - So the 10-09 N3 reading ("boxes right of the sprite near the edges, alberta_in") is a real
    indoor-camera effect, but its size here is a few px (up to ~10 at the edges), not the ~15-25
    px the 10-09 sheets suggested (those were v1 label boxes, made with the packet heading and
    k nostalro).
- **Per sprite** (n; median dx / dy; within 6 px): alberta 105 (10; 0 / 0; 1.00), 112 (8; 0 / -1;
  1.00), 51 (7; 0 / 0), 837 (8; 0 / -2), 92 (9; 0 / -1), 998 (10; +1 / -2), 116, 874, 89, 84, 71
  (all within 6 px); prt_fild08 51 (26; +1 / -1; 1.00), **909 (26; +1 / -2; 0.92)**; prontera 700
  (7), 99 (5), 105, 50 (all within 3 px); prt_church 120 (39; +1 / +2; 0.95), 67 (32; -3 / +2;
  0.94), 79 (69; +1 / +2; **0.64**), 71 (21; 0 / +3; 0.86), 798 (19; -1 / +4; 0.63), 741 (13;
  +1 / -2; 0.77), 745 (8; +4 / -3; 0.88), 60 (5), 755 (1); alberta_in 59 (2; +5 / -4), 98 (4;
  +4 / 0), 86 (1; -5 / -1).
- **k: 0.14 beats 0.1333 on every one of the 348 paired matches** (median NCC 0.76 against 0.58).
  For NPC sprites k = 0.14 (korangar's) is the better scale. M4's k (monsters) stays OPEN; this is
  evidence for it, not a decision.
- **L3 against the packets** (every rendered NPC on every candidate frame, 3,218 sightings): the
  server showed an NPC object at the L3 cell for 3,214, and **for all 3,214 the sprite and the
  FACING agree with L3** (the script's dir is the heading the server sends). 4 had no object at
  that moment.
- **The server's view area decides what is drawn** (found here, now in the render): an NPC more
  than 14 cells (Chebyshev, rAthena's `area_size`) from our GM is never sent, so never drawn, even
  when its cell is on screen. On 5 sessions: 81 of 82 such NPCs had no packet object, and 518 of
  520 NPCs within 14 cells had one. `npc_render` now skips them (`beyond_area`); the numbers above
  are after that rule.
- **The S2 path:** 64 confident matches (prt_fild08 52 outdoor, prt_church 12 indoor): median
  2.2 px, 0.91 within 6 px. Its probes (3.3) are not measured.
- **The pixel camera rule on these default-camera frames** (PROVISIONAL thresholds): `default` on
  85 frames, `unknown` on 154 (fewer than 2 NPCs seen cleanly), **`off` on 2** (false alarms: a
  798 at the screen's bottom-right corner, 14 px off indoors; a 909 whose 22-frame idle was
  matched on a sampled frame, 12 px off). As built, the rule cannot refuse anything live.

### 3.3 (b) The rendered mask vs the CLICKABLE area (cursor@2's labelled hovers)

- **The probes:** 3,595 hovers (hover only, never clicked), each rendered from our GM's PACKET
  cell (it equals the probe's stand cell in 3,595 / 3,595).
  - 691 are excluded: their target NPC is a guild flag (722, unsupported).
  - 2,904 are usable: 1,225 labelled TALK, 1,679 labelled walk / noentry / sword ("other").
- **Is the point inside a rendered NPC's region?** (mask = the union of the idle frames; box = the
  envelope; hit box = the PROVISIONAL fit below)

  | | TALK inside | other inside |
  |---|---|---|
  | drawn MASK | **479 / 1,225 = 0.391** | 10 / 1,679 = 0.006 (*) |
  | envelope BOX | 673 / 1,225 = 0.549 | 22 / 1,679 = 0.013 |
  | mask + 8 px | 0.631 | 0.024 |
  | mask + 16 px | 0.762 | 0.096 |
  | mask + 24 px | 0.940 | 0.223 |
  | mask + 32 px | 0.984 | 0.329 |
  | **hit box** (fitted, in-sample) | **1,191 / 1,225 = 0.972** | 206 / 1,679 = 0.123 |
  | hit box, points not near an unrendered NPC | **1,151 / 1,169 = 0.985** | 194 / 1,651 = 0.118 |

  - (*) The 10: walk answered ~70 px above the feet of 105 and 112 (the top of the drawn sprite
    is not always clickable), and next to a prontera flag.
- **Per map** (TALK in mask / box / hit box; other in hit box):
  - alberta: 0.407 / 0.589 / 0.991; 0.137.
  - prontera: 0.277 / 0.393 / 0.927; 0.106. Its 722 flags stand among the probed NPCs; 68 of its
    276 TALK points outside every mask lie in an unrendered flag's area.
  - prt_church: 0.553 / 0.718 / 1.000; 0.107.
- **Per target sprite** (TALK in mask; in hit box): alberta 105 0.47 / 0.94, 112 0.37 / 1.00,
  51 0.37 / 1.00, 837 0.37 / 1.00, 92 0.29 / 1.00, 998 0.61 / 1.00; prontera 105 0.30 / 0.87, 700
  0.31 / 1.00, 92 0.23 / 0.93; prt_church 120 0.71 / 1.00, 67 0.42 / 1.00.
- **Where TALK answers beyond the drawn pixels:** 746 TALK points lie outside every mask, at a
  median 13 px from the nearest mask pixel (p90 24 px, max 40 px). By the probe grid around the
  feet (alberta, 6 NPCs x 2 stands x 2 reps; TALK / probes):

  | px above (-) / below (+) the feet | -51 | -34 | -17 | 0 | +17 | +34 | +51 |
  |---|---|---|---|---|---|---|---|
  | -98 | | | | 4 / 24 | | | |
  | -84 | | | | 8 / 22 | | | |
  | -70 | 0 / 24 | 10 / 24 | 18 / 23 | 12 / 24 | 18 / 23 | 20 / 22 | 2 / 22 |
  | -42 | 0 / 23 | 16 / 24 | 24 / 24 | 24 / 24 | 24 / 24 | 23 / 23 | 2 / 22 |
  | -14 | 4 / 24 | 16 / 24 | 23 / 23 | 24 / 24 | 24 / 24 | 23 / 23 | 0 / 23 |
  | 0 | | | | 23 / 23 | | | |
  | +14 | | 15 / 23 | | 20 / 24 | | 20 / 24 | |
  | +28 | | | | 4 / 23 | | | |

  - The drawn sprites are ~32-50 px wide, yet TALK holds at +-34 px from the feet on nearly every
    probe, and still answers ~14 px BELOW the feet. Prontera and prt_church show the same shape.
  - **So the client does not hit-test the drawn pixels, nor the sprite's box.** The probe grid
    (17 px steps) cannot pin the true edges; a fine grid is part of section 6.
- **The PROVISIONAL hit box** (`npc_render.HIT_*`): |u - feet_u| <= 42 screen px, from 8 px
  above the idle envelope's top down to 16 px below the feet. Chosen over the alternatives on the
  same data (TALK / other; points within 60 px across, 170 px above or 30 px below an unrendered
  NPC's feet left out, so the numbers differ slightly from the table's 140 x 190 px rule):
  - H 38 (same top and bottom): 0.979 / 0.080;
  - **H 42: 0.993 / 0.118**;
  - H 42 with 20 px below and 12 px above: 0.995 / 0.127.
  - In sprite px (x the sprite scale) instead of screen px it fits prt_church's larger scale less
    well; the data cannot separate the two (one indoor map).
- **Over-coverage costs walkable floor only**, never safety: the walk gate still reads the cursor
  (WALK read twice) before every click.

### 3.4 The offline camera guard on the design sessions

- `npc_render_measure.py camera` over the 65 sessions: the input log holds **no** rotation or zoom
  input inside any session's window, and the guard says `default` at each start and end (60
  sessions; 5 have no window in their manifest).
- On 2026-10-10 the log holds 23 human right-presses at ~20:20 ICT, after the last probe session:
  a positive case exists in the log, outside the design sessions.

### 3.5 Corrections proposed (NOT applied)

- **The indoor camera: refit it** (yaw, distance, pitch; B2's procedure) on these 214 indoor
  matches plus alberta_in's. The linear field of 3.2 (residual SD under 1 px) is what a small
  rotation / scale error leaves, so a refit should remove most of it. NOT applied: the camera
  json is a committed lab constant that every labeller reads, and a refit changes all of them.
- **Outdoors:** a constant (+0.6, -1.3) px, inside the match's own noise. No correction proposed.
- **k:** the render already uses 0.14 for NPC sprites; whether monsters move to 0.14 is M4's
  question (evidence, not a decision).
- **Applied in code, because it is server mechanics and not a fit:** the 14-cell view area.
- **The hit box (3.3):** in code as PROVISIONAL constants; nothing uses it until section 6 passes.

## 4. Batt's exceptions, and how each is handled

| exception | handled by | state |
|---|---|---|
| animated idle NPCs | the union of every idle frame of the drawn direction (`predict_sprite` with no phase) | BUILT; 909 (22 frames), 741 (45), 798 (21), 755 (33) among the decoded |
| hidden / undrawn NPCs | L3's drawn mark: hidden classes and drawn False are not NPC sprites; **conditional** ones (hidden at start) are listed apart and never rendered | BUILT; a conditional NPC's area stays unknown: the walk gate keeps L3's PROVISIONAL footprint for it |
| moving NPCs | not rendered as static: L3 marks script placements (`movenpc`, run-time `monster`) and the map is then not declared complete; a moving NPC needs the detector + a tracker | NOT BUILT (detector + tracker) |
| camera rotation / zoom | refuse: the offline input-log guard (`CameraLog`), and at run time the rendered NPCs against the frame (`pixel_camera_check`) | the offline guard BUILT and run (3.4); the pixel rule BUILT offline, its thresholds PROVISIONAL; on the 241 default-camera design frames it says `default` 85, `unknown` 154, `off` 2 (false alarms, 3.2): not usable live yet |
| external servers | only where the scripts match (ADR-0021): the render reads THIS lab's L3; another server needs its own scripts or proof that they match | NOT BUILT: `render` refuses a map not in the KB, nothing more |
| a 3-D model instead of a sprite (found: 722 guild flags) | unsupported, fail closed | a gap (section 5) |

## 5. Open gaps

1. **Sprite coverage.** N1 / N2 cover 46 sprites; the KB's 33 maps draw 127 sprite ids. The
   measurement table in /dev/shm covers 90 (six maps), NOT N1's scope. Widening N1 is a decision.
2. **Indoor accuracy** (alberta_in 10-09, prt_church): measured (3.2). Indoor misses grow
   linearly away from the centre (median 4.1 px; 8.6 px beyond 450 px). A camera refit is
   proposed (3.5), not applied.
3. **k** is still OPEN in M4; section 3.2 measures 0.14 against 0.1333 on NPC sprites.
4. **Our position at click time:** whole cells from /where; a sub-cell position while walking and
   the camera's follow smoothing are not modelled. The render holds while we stand still.
5. **The camera at run time:** the pixel rule needs a positive case (a deliberately rotated and a
   zoomed camera) before it may refuse anything live. Section 6 B4.
6. **The clickable area (Batt's gap 6) is answered: it is WIDER than the drawn pixels.** What
   remains: its exact edges (a fine probe grid), whether it scales with the sprite or the screen,
   and whether it differs per sprite.
7. **Outside the ACT:** shadows, effects and name text are not in the mask. The TALK answers
   ~14 px below the feet may be the shadow's area; not tested.
8. **Conditional NPCs:** their run-time state is unknown from static data.
9. **MIXCRYPT at run time.** Every NPC SPR here is MIXCRYPT (flag 0x03). Batt scoped the decoder to
   "study only" on 2026-10-05. The parent reads Batt's 2026-10-13 message ("With the client's
   sprite files (decoded locally, never committed) ... render each NPC") as his OK to use the
   decoded pixels at run time. **That reading is the parent's, to be confirmed by Batt.**
10. **File identity, Thai vs kRO.** The files come from this host's only GRF, the Thai client's on
    the NAS. The lab client draws kRO data. The 12 monster species were byte-identical (Part C);
    these NPC files were never compared. The alignment (3.2) is indirect evidence that the drawn
    sprites match the decoded ones; a hash comparison against the Dell's kRO GRF settles it.
11. **3-D models (722)** cannot be rendered by this path. A measured extent (npc-click-test.md 7:
    ~95 x 150 px) or the PROVISIONAL footprint covers them meanwhile.
12. **The S2 path's clickable area** is not measured (every probe is RDP); its alignment is (3.2).
13. **Labels v2 from rendering:** the boxes would come from this path, but N3's sheets wait for a
    person, and 909 (an NPC drawn as a Poring) needs a class decision.

## 6. DRAFT pre-registration (for the parent to review and commit to docs/demonstrations.md; it binds nothing until then)

> ➡️ **SUPERSEDED 2026-10-13 13:53: COMMITTED as [demonstrations.md](../demonstrations.md) 3.38**, which
> is the binding version. One change was made before any data: B1's spot moved from `--near 150,100` (1 NPC,
> 312 probes) to `--near 70,356` (5 NPCs). B2 / B3's spots were fixed from offline plans: alberta_in
> `--near 53,43`; new_1-2 without `--near`. The draft below is kept as written.

**Claim:** for every drawn, supported NPC in view, (A) its rendered sprite sits where the client
draws it, and (B) the NO-CLICK region (the rendered mask OR the PROVISIONAL hit box, fixed below)
holds every point where the client answers TALK, at a bounded cost in walkable floor.

**Fixed now (from the design data; changed only by a new pre-registration):**
- code: `npc_render.py` / `npc_render_measure.py` at the commit that adds this section;
- k = 0.14; radius 24 px; a match counts at NCC >= 0.5; at most 15 frames per session;
- the hit box: HIT_HALF_W 42, HIT_TOP 8, HIT_BELOW 16 (screen px);
- the pixel camera rule: PIXEL_MIN_SCORE 0.5, PIXEL_MAX_OFFSET 12 px, PIXEL_MIN_SEEN 2;
- sprites: a `--measure-map` table for each map used, built before the first run (its sha256 in
  the run record); an NPC it does not cover is reported, never rendered.

**A. Positions vs packet truth (offline, on FRESH sessions not used in section 3).**
- Data: every banked session recorded AFTER this pre-registration's commit that stands our GM on
  maps with drawn NPCs: at least 300 confident matches outdoor and 100 indoor, from at least 3
  sessions each. Until both counts are met, A is INCONCLUSIVE.
- Bars:
  - A1 (identity, hard): every rendered NPC that the packets show is at the same cell, with the
    same sprite and the same facing. One disagreement FAILS A.
  - A2 (outdoor): >= 95 % of confident matches within 6 px, median <= 2 px.
  - A3 (indoor): >= 95 % within 12 px (the indoor camera is NOT refitted first; a refit would be
    its own pre-registration).
  - A4 (k): k 0.14 scores higher than 0.1333 on >= 75 % of paired matches (reported per map).
  - Reported, not a bar: the pixel camera rule's verdicts per frame (`default` / `unknown` /
    `off`); it gets its own pre-registration once its thresholds are fixed.

**B. Live hovers (fresh npc-click probe runs, hover only, nothing clicked).**
- Runs (`npc_click_test.py probe`, the cursor@2 harness, the UI gate and a judged screenshot
  before each run):
  - B1: prontera `--near 150,100 --seed 20261190` (a spot not used in section 3);
  - B2: alberta_in `--near <the job changer's room> --seed 20261191` (indoor; no design probe);
  - B3: new_1-2 `--near <its NPC group> --seed 20261192` (the training grounds: outdoor, every
    sprite in N1);
  - the spot of each run is fixed from L3 before the run (`plan`, same seed), never moved after.
  - B4 (camera, a positive case; REPORTED, not a bar here): a few frames after a deliberate
    right-drag rotation and after a zoom, by a person (ONLY Batt rotates or zooms), then a map
    change. Both camera guards are run on them: the input-log guard must say rotated / zoomed,
    and the pixel rule's verdicts are reported. This is the positive case the camera rule's own
    pre-registration will need.
- Truth: the cursor@2 labelling (two blind labellers; truth = agreement), grab 0 of every probe.
- n: >= 600 TALK-labelled hover points in total, >= 150 per run; fewer is INCONCLUSIVE.
- Bars (points within 60 px of an unrendered NPC are reported apart, not counted):
  - B-SAFETY (hard): TALK points OUTSIDE the NO-CLICK region <= 1 % overall and <= 2 % in every
    run.
  - B-COST: other points (walk / noentry / sword) inside the region <= 20 % overall.
  - Reported, not bars: the drawn mask's own TALK share; the box's; the dilation curves; TALK
    outside the region per sprite, with its offset from the feet.
- **What PASS unlocks:**
  - the walk gate's NO-CLICK region = the rendered region (mask OR hit box) on maps where the
    render is `complete`, replacing L3's PROVISIONAL footprint there (where it is not complete,
    the footprint stays and the gate refuses as today);
  - labels v2 NPC boxes from rendering (the envelope box per frame) for supported sprites whose N3
    reading is `fit`, replacing most of the NPC collection;
  - occlusion checks (expected vs observed pixels) as a label filter.
- **What FAIL means:** the region is not used; the failing points (offset from the feet, sprite,
  map) are reported and a new hit-box model is pre-registered.

## 7. As built (2026-10-13, Claude; branch feat/npc-render)

- Commits: bc4ef75 (the N1 measurement scope), e425c4a (the render path and the measurement
  tool), then the view-area rule, the hit-box columns and this document.
- **A slip, recorded:** while adding `--measure-map`, its first refusal check compared against the
  WORKTREE's data/kb, so one build with `--measure-map prontera` wrote a widened table to the MAIN
  checkout's `data/kb/npc_sprites.json` (~12:25 ICT). The check now refuses any `.../data/kb/`
  path; the table was rebuilt at once with the plain command (46 sprites; the 38 route rows equal
  the pre-extension backup; the 8 EXTRA rows as merged). `npc_sprite_names.json` and the catalog
  were never touched (sha256 unchanged).
