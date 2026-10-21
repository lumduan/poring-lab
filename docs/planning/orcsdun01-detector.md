---
doc_type: design
hypothesis: "Warp-and-watch collection plus packet labels give a per-species detector for orcsdun01 that does not forget prt_fild08 (v1's gold set and held-out sessions no worse)."
status: PROPOSED (collection running from 2026-10-21; the class scheme is Batt's default unless he answers; the evaluation is pre-registered in ../benchmarks/v2orc-vs-v1.md BEFORE training)
role: null
verdict_date: null
verdict_ticket: null
supersedes: null
related: [labels-v2-plan.md, training-cost.md, ../benchmarks/v1-vs-v0png.md, ../phase3-plan.md, ../operations/vision-long-lived.md]
next_action: "The camera check on the first block (col1) FAILED (section 3a: C1 34.7 % bad_label, C2 Black Mushroom); per section 3 no orcsdun01 label trains until the re-measure (M4-style) and Batt's call. The diagnostic points at the sprite's view (the open outdoor facing, phase3-plan 5d-ii), not the camera. The labels, contact sheets and blind pack are built (local) for that work."
title: "orcsdun01 (Orc Dungeon F1): the facts, the collection, the camera check, the class scheme, the labels and the evaluation (plan)"
date: 2026-10-21
owner: Batt
---

# A detector for orcsdun01 (Orc Dungeon F1)

**Batt, 2026-10-21 ~09:1x (verbatim, abridged):** "GPU FREEZE LIFTED (Batt, now). Next big step:
train the detector for a NEW map, ORC DUNGEON F1 (orcsdun01) ... 1. FACTS FIRST (offline) ...
2. COLLECTION WITHOUT WORLD CLICKS ... "warp and watch" ... 3. LABELS from packets offline
(ADR-0007) ... a contact sheet per species checked by two blind labeller agents on a sample before
training, plus a small gold set for this map. 4. CLASS SCHEME (propose; default if I don't answer
by the time labels are ready): PER-SPECIES monster classes ... 5. TRAINING on the GPU ... train on
the combined data (v1's data + the new map) so prt_fild08 isn't forgotten ... 6. EVALUATION,
pre-registered before training ... 7. Then (separate decisions, not today): the GPU detector for
live hunting, and what hunting in a dungeon of AGGRESSIVE monsters needs."

**Batt ~09:3x:** the orcsdun01 work runs IN PARALLEL with the hunting work. The client alternates
blocks: a hunt run, then a ~45-60 min collection block, and so on, never splitting a hunt run.

## 1. The facts (offline, from the pinned rAthena e985006 and the client GRF)

The full record is local only, because it is GPL- and client-derived: `/dev/shm/poring-lab-tmp/orc/FACTS.md`
and its JSON. The summary:

| species (mob id) | Batt's list | the lab server (pinned rAthena) | aggressive | looter | moves |
|---|---|---|---|---|---|
| Orc Zombie (1153) | 10, 3-8 s | **80**: 10 at 3 s + 30 at 60 s + 40 at 120 s | yes | no | 2.5 cells/s |
| Familiar (1005) | 15 | 15, 5 s | yes | no | flies, 6.7 cells/s |
| Steel Chonchon (1042) | 10 | 10, 5 s | **no** | **yes** (+ assist, detector) | flies, 6.7 cells/s |
| Orc Skeleton (1152) | 10, 3-4 min | 10, fixed 180 s | yes | no | 5 cells/s |
| Black Mushroom (1084) | 10, 15-23 min | 10, fixed 900 s, in 2 small areas | no | no | immobile |
| Drainliar (1111) | 5 | 5, 5 s | yes | no | flies, 4 cells/s |
| White Plant (1082) | 5, 3-5 min | 5, fixed 180 s, in 2 small areas | no | no | immobile |

- **Differences from Batt's list:**
  - 135 monsters, not 65: two Orc Zombie spawn lines are missing from the list.
  - The respawns are FIXED on our server (`mob_spawn_variance: 1`). The list's ranges are the
    official variance.
  - Steel Chonchon is a looter, not aggressive.
- **The map:**
  - 200 x 200 cells, 9,356 walkable;
  - client and server agree on every cell, in one connected part;
  - 2 warps and 0 script NPCs;
  - `@warp` is allowed (only `nomemo`);
  - `dynamic_mobs`: the whole population spawns when a player arrives and is removed 300 s after
    the last one leaves.
- **Not indoor:** orcsdun01 is not in the client's indoor table, so the code uses the fitted
  OUTDOOR camera plus the GAT altitude. That is UNMEASURED on this map (section 3).
- **Dark:** the RSW diffuse light is 0.2 / 0.3 / 0.3 (prt_fild08: 1 / 1 / 1), with a dark-green
  fog entry.
- **Familiar and Drainliar share one SPR.** Drainliar differs only by an ACT tint (250, 69, 96).
  Hue augmentation must not cross them, and the light / fog may flatten the tint (the label check
  measures it).
- Three species FLY: Familiar, Drainliar and Steel Chonchon are drawn 38-88 native px above their
  cell. Creamy, the species the old detector missed, flies too.

## 2. The collection: warp and watch (`scripts/warp_watch.py`, 686a4e7)

- **No world click.** Per stand cell: `@warp orcsdun01 x y`, a 2.5-s settle, a 30-s dwell.
  - collect_v2's natural-dwell driver; no `@monster` spawn and no `@killmonster2` (it would also
    kill the slow-respawning natural mobs: 15 min for the Black Mushrooms).
  - Every line goes through ro_agent.gm: the UI gate, the foreground gate and the typing guard
    (each warp line is distinct).
  - The GM is immune (@monsterignore, confirmed for this login).
- **The stands:** a 97-cell lattice, about 11 cells apart (local `lattice.json`).
  - Each stand is a three-check cell: client ∩ server walkable, ≥ 3 cells from a warp area, and
    a fully walkable 5 x 5 around it.
  - 98.7 % of the walkable cells lie within 7 of a stand.
  - Each block takes a new seeded order and fits ~92 dwells in 50 min.
- **The recording:**
  - the game region at 5 Hz, JPEG q80, in 256-MB tar shards straight on the NAS
    (`/mnt/poring-lab-datasets/detector-collection/orcsdun01/<session>/frames/`), never the local
    disk;
  - the sniffer's packets for the window, pseudonymised, beside them.
- **Thin species get their own dwells:** the plants and the mushrooms live in 4 small fixed areas,
  so a later block dwells on the stands that see them (7-17 stands each). Black Mushrooms respawn
  in 15 min, so a killed one is not the issue; their only 10 sprites are.
- **The state at each switch:**
  - for collection: the hunt's state as the runner leaves it (immune, the hunting UI layout), on a
    judged screenshot;
  - for hunting: the runner restores its own (layout, Lv 70 / STR 99, weight).

### 2a. The collection log

| block | session | time (ICT) | dwells | frames (GB) | safety (packets, `warp_watch.py judge`) | units seen on screen / unit-seconds (1 Hz, within 15 x 11 cells of the GM) |
|---|---|---|---|---|---|---|
| col1 | 20261021T103231-orcsdun01-col1 | 10:32-11:22 (seed 1, 30-s dwells) | 80 (all 80 warps landed as typed) | 15,028 (1.77) | no request, no GM act, 0 acts on the GM (3,627 monster moves); 81 / 81 GM lines seen at the server | Orc Zombie 80 / 10,223; Familiar 15 / 2,068; Steel Chonchon 10 / 1,484; Black Mushroom 10 / 1,157 (from 8 stands); Orc Skeleton 10 / 1,074; White Plant 5 / 789 (14 stands); Drainliar 5 / 449 (23 stands) |

- **The live server matches the pinned list exactly:** 135 units of the 7 species.
- **A dwell takes ~40 s, not the planned 32.5 s:** typing a GM line costs ~7 s. So ~73 dwells fit
  in a 50-min block, not 92.
- **The chat input stayed OPEN after the GM lines** (`chat_open` True). It is the chat window's own
  input line, so it shows in col1's frames.
  - It was closed by its known step before the next hunt run.
  - Since 90a15bf, warp_watch closes it after its last line.

## 3. The camera check on the first block (bars fixed HERE, before its frames are read)

The model was fitted on prt_fild08 / prt_church, and orcsdun01 uses the outdoor camera without a
measurement. The check:
- **Data:** the first block's frames, with the packets' STANDING monsters: idle >= 1 s, no other
  unit within 120 px, not under a UI window.
- **C1:** `label_check.py`'s masked NCC of the rendered sprite (k 0.140, the v1 labels' k) at the
  projected anchor.
  - The fixed tau is 0.092 (M4, phase3-plan 5b).
  - **Pass: < 2 % `bad_label` pooled** (the M5 gate), reported per species.
- **C2:** the best-NCC offset within ±16 px of the projected anchor.
  - **Pass: median |dx| and |dy| <= 4 px for the ground species** (Orc Zombie, Orc Skeleton, White
    Plant, Black Mushroom) **and <= 6 px for the three flyers**, per species with >= 20 standing
    labels.
- **Reported:** the Familiar-vs-Drainliar colour gap as drawn here (the mean hue of their pixels).
- **If C1 or C2 fails,** no orcsdun01 label trains. The camera / k is re-measured first, M4-style,
  and the result goes to Batt.

### 3a. RESULT on the first block, col1 (`scripts/orc_camera_check.py`, run 2026-10-21 11:55 ICT): FAIL

Session `20261021T103231-orcsdun01-col1` (80 dwells, 15,028 frames; every 5th frame inside a dwell,
outside GM windows; 2,985 standing labels scored). The output is local:
`/dev/shm/poring-lab-tmp/orc-labels/<session>/camera_check.json`.

- **C1 FAILS:** `bad_label` 34.7 % pooled (bar < 2 %). Per species: Orc Zombie 36.1 %, Orc Skeleton
  49.6 %, White Plant 12.0 %, Black Mushroom 69.2 %, Familiar 22.0 %, Steel Chonchon 43.9 %,
  Drainliar 19.8 %.
- **C2 FAILS on Black Mushroom only** (median |dx| 7.5, |dy| 9 px; bar 4). It passes for Orc Zombie
  (2 / 2), Orc Skeleton (4 / 2), White Plant (1 / 1), Familiar (2 / 5), Steel Chonchon (4 / 3) and
  Drainliar (1 / 3). Every species had >= 20 standing labels (101-1,573).
- **Colour (reported):** the drawn Familiar is a dull grey-brown and the drawn Drainliar a saturated
  red. On well-found bats: hue 53° (saturation 0.26) against 5° (0.69), a 48° gap; 84° in the
  rendered sprites.
- **Diagnostic, NOT a bar:** the sprite's VIEW, not the camera.
  - With the best of the 8 headings, the low share falls from 34.7 % to 5.0 % pooled. The max over 8
    is biased upward, so read it as an upper bound.
  - The Timeline facing differs from the best view on 78 % of the labels, mostly by 45° (±1
    heading), then 90°. 85 % of those facings were set by a walk.
  - This is the outdoor facing that phase3-plan 5d-ii left OPEN: "a wrong view lowers the NCC".
    The symmetric prt_fild08 sprites hid it; the asymmetric orc sprites show it, and their boxes
    shift sideways with the view.
  - The positive cases score 0.6-0.9 at offset (0, 0). Re-measuring decides what to change; this
    diagnostic does not.

## 4. The class scheme (PROPOSED; Batt's default if he does not answer by the time the labels are ready)

| id | class | from |
|---|---|---|
| 0 | `player` | packets objtype 0; our GM labelled `player` (labels v2, Batt 2026-10-09) |
| 1 | `npc` | packets objtype 6 (labels v2) |
| 2 | `warp` | labels v2's warp rule (L3 cell + drawn portal + visible). A frame whose warp cannot be labelled completely is EXCLUDED (labels v2's rule) |
| 3.. | one class per monster species with data | packets objtype 5, by mob id |

- **The monster classes:**
  - the prt_fild08 species: Poring 1002, Lunatic 1063, Pupa 1008, Drops 1113, Creamy 1018 (the
    metamorphosis), plus any other species the labeller finds in v1's sessions;
  - orcsdun01's seven: 1005, 1042, 1082, 1084, 1111, 1152, 1153.
  - That makes about 15 classes.
- **The hunt code maps species to `monster` plus its target / ignore lists.** The species check
  then comes from the detector. Creamy becomes its own class instead of a monster the bot strikes
  by mistake.
- **The live CPU detector stays v1** until Batt decides on the new one (his item 7).
- Two open questions for Batt:
  - **Warp:** if labels v2's warp inputs are not ready for these maps, `warp` is left out of this
    model rather than half-labelled.
  - **Thin classes:** White Plant (5 alive) and Drainliar (5) may stay thin. They train and are
    reported apart, with no bar of their own until they reach 50 held-out labels.

## 5. The labels and the label check

- **The labels** come from packets, offline (ADR-0007):
  - positions -> screen through the camera model (`projector_for`);
  - boxes from the sprite catalog per species (`predict_sprite`; local decoded sprites, never
    committed);
  - occlusion and UI cover handled as labels v1 / v2 do;
  - every frame is labelled completely or EXCLUDED.
- **The contact sheets:** one per species, each crop with its box (the NAS / /dev/shm only).
- **The blind check:** two labeller agents, independently, on a sample of 30 crops per species.
  - They see no predicted class name. They answer: a monster there? the box good / loose / off?
    which species (from a sheet of rendered references)?
  - **The bar for a species to train: >= 90 % "good" from each agent, and the agents' species
    agreeing with the label on >= 95 %.**
  - A species that fails is excluded and reported.
- **The gold set for orcsdun01:**
  - 20 frames from a held-out block on which both agents accept every box;
  - any disagreement is resolved by the parent, recorded, and shown to Batt.

### 5a. RESULT: the blind label check on col1 (2026-10-21 ~12:10 ICT): FAIL for every orcsdun01 species

- **The pack** (`scripts/orc_label_sheets.py`, seed 0):
  - 30 crops per orcsdun01 species + col1's 15 Poring boxes = 225 crops;
  - shown to the labellers as 12 numbered grids, with a reference sheet of 12 rendered sprites
    (A-L);
  - the answer key sat in a separate directory the labellers never opened.
- **The labellers:** two blind agents, A and B, independent; B worked in reverse order. Their
  agreement: Q1 (a monster in the box) 218 / 225, Q2 (the box) 201 / 225, Q3 (the species)
  213 / 225.
- **The bars** (section 5, fixed before): >= 90 % "good" from EACH labeller, and the species right
  on >= 95 %.

| species | crops | A: good / species right | B: good / species right | passes |
|---|---|---|---|---|
| Orc Zombie 1153 | 30 | 86.7 / 96.7 % | 83.3 / 96.7 % | no (good) |
| Orc Skeleton 1152 | 30 | 86.7 / 100 % | 76.7 / 100 % | no (good) |
| White Plant 1082 | 30 | 93.3 / 96.7 % | 86.7 / 93.3 % | no (B) |
| Steel Chonchon 1042 | 30 | 76.7 / 76.7 % | 76.7 / 80.0 % | no |
| Familiar 1005 | 30 | 60.0 / 83.3 % | 53.3 / 70.0 % | no |
| Drainliar 1111 | 30 | 56.7 / 93.3 % | 50.0 / 96.7 % | no |
| Black Mushroom 1084 | 30 | 70.0 / 60.0 % | 60.0 / 60.0 % | no |
| (Poring 1002, prt_fild08 frames) | 15 | 100 / 100 % | 100 / 100 % | yes |

- **When a monster is in the box, its species is right.** The wrong-species answers are mostly
  "none / unsure": nothing visible in the box. Black Mushroom accounts for 12-13 of them, Steel
  Chonchon 6-7. Real confusions are few: Familiar read as White Plant or Pupa in 3-4 crops.
- **The failures are in WHERE the box is, and in occlusion:**
  1. The bats' boxes sit next to the bat: both labellers called Drainliar and Familiar "off" in 5-8
     crops each. The flyers' anchor (drawn 38-88 native px above the cell) and the facing (3a)
     shift them.
  2. The orcs are cut along one side: the facing model's asymmetric idle box (3a's diagnostic).
  3. Black Mushrooms under tree canopy or map models: the packets place one there, and the client
     draws nothing visible (FACTS 9.4: the RSW models were not read). Those labels need an
     occlusion exclusion.
- **=> No orcsdun01 label trains** (section 3's gate and this one). The fix is a labelling
  hypothesis, pre-registered (the facing, the flyers' anchor, model occlusion), then both checks
  re-run. That is Batt's call.
- 157 of the 225 crops were "good" for both labellers with the right species. They are the
  candidates for this map's small gold set once the labels are fixed.
- The answers are local only (`/dev/shm/poring-lab-tmp/blind-A|B/answers.json`, client-derived).

## 6. Training and evaluation

- **Training** runs on the combined cache: v1's sessions re-labelled per species + the orcsdun01
  blocks (split by block).
  - ⚠️ **Measured 2026-10-21 (a dry run, packets only):** `build_frame_cache.py --labels v2
    --classes species` on v1's 10 sessions KEEPS 566 of 16,995 candidate frames (3.3 %). The rest
    are excluded by labels v2's own rules:
    - `npc_unchecked`, 15,560 frames: no person's N3 verdicts yet (prt_fild08's NPCs 51 and 909,
      prt_church's);
    - `warp_visibility_unknown`, 9,914: no warp table (prt_fild08 170,378 alone is 7,143);
    - `self_dead`, 4,130.
  - No species outside the class list appears in v1's data, and Creamy has 0 boxes.
  - So the "not forgotten" half needs those inputs, or a decision on how v1's sessions are
    re-labelled, before the combined cache is built.
  - The setup is v1's: `train-day.sh` in the long-lived vision worker, `MID_CKPT=1`, the adaptive
    duty cycle, the IO guard, VRAM 25 %, batch 2 / workers 1.
  - Cache building stays outside 09:30-10:15 and 14:00-14:45.
  - **CPU contention (Batt ~09:3x):** the hunt's CPU detector fps / latency is measured while
    training runs (the runner's `det_fps`, v51 2.87-3.08). If it drops, the loader's workers or
    nice go down first; the hunt is never slowed.
- **The evaluation** is pre-registered in `docs/benchmarks/v2orc-vs-v1.md` BEFORE training. Its
  outline:
  - per-species recall / precision on the held-out orcsdun01 block;
  - v1's gold set (Batt's 27 frames, the position metric, monsters collapsed) and held-out
    prt_fild08 sessions no worse than v1 (P 0.902 / R 0.830);
  - Creamy recall reported;
  - latency per frame on GPU vs CPU.

## 7. Not today (Batt's item 7)

Two later decisions:
- the GPU detector for live hunting;
- what hunting among AGGRESSIVE monsters needs: HP watch, potions, retreat / death handling.
  Immunity comes off only after those exist.
