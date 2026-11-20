---
doc_type: hypothesis
hypothesis: "xmas02sk's own pipeline (immune lattice watches, packet labels, T1/T2, a frame cache, a YOLO11n fine-tune), repeated on frames of the 1920x1080 client as the bot sees them (the virtual 1280x720 picture) and mixed with the 720 TRAIN, gives ONE xmas_dun02 model that sees at 1080 what xmas02sk sees at 720 (its offline numbers, and in play no more false boss alarms), without losing 720."
status: PROPOSED
role: null
verdict_date: null
verdict_ticket: null
supersedes: null
related: [xmas02-detector.md, screen-size-ab.md, fullscreen-client.md, ../benchmarks/xmas02-eval.md, ../../scripts/map_labels.py, ../../scripts/build_frame_cache.py, ../../scripts/eval_q1.py, ../../scripts/record_session.py, ../../scripts/screen_ab.py]
next_action: "Pre-registered 2026-11-20 07:44:50 ICT (the commit time), before any 1080 recording. Build the tools (section 3), then FIT (section 5)."
title: "xmas02 at 1920x1080: retrain the monster detector on the virtual 1080 picture (pre-registration)"
date: 2026-11-20
owner: Batt
---

# xmas02 at 1920x1080: the detector, retrained (pre-registered 2026-11-20 07:44:50 ICT, commit 30005e1a)

## 0. What Batt asked, and what this plan does not decide

- Batt, 2026-11-20 ~07:3x ICT, after the s11scr report and the 720-vs-1080 opinion: "ทำเรื่องเทรน
  1080 เลย ระยะยาวดีกว่าชัดเจน ตั้งเกณฑ์ขั้นต่ำตามที่ 720 ทำได้ เริ่มตอนนี้ได้เลย" (train for 1080
  now; long term it is clearly better; set the minimum bar at what 720 achieves; start now).
- So: every bar below is the level the 720 side reached, not a new, lower one (section 8).
- Not decided here (Batt's): the C2 alarm rule (garm_confirm 3), making the new model the map's
  default at 720, and the item model's round (section 10).

## 1. The facts this plan stands on

- s11scr (screen-size-ab.md): at 1080 the bot plays WORSE: 72.9 kills/h (B2 86.9) against
  129.2 at 720.
  - Cause 1 by time lost: false alarm boxes (mostly Christmas Goblin), 0.011 per frame against
    0.001-0.002, about 28 boss Fly Wings an hour, nearly all false.
  - Cause 3: the item model sees 1/3-1/2 of the items.
  - Both are models seeing the shrunk 1080 world.
- At 1080 the bot sees the VIRTUAL 1280x720 client (clientview.py):
  - the world is resampled by 1/1.5 about the centre, nearest pixel;
  - the UI panels are pasted at native size at the lab's places (ro_agent.LAB_PANELS);
  - the pointer's patch is pasted unscaled, by the process that moved it.
- The recorder grabs `ro_agent.game_region()`, so at 1080 it records that same virtual picture.
  The manifest then says game_region [100000, 0, 1280, 720].
  - The label and cache tools refuse such a session (map_labels.check_recording,
    detector_vs_packets.check_session: [80, 77, 1280, 720] only).
- The labels come from packets through camera_rdp.json, fitted at 720.
  - At 1080 the world maps to the virtual frame by the measured scale 1.5 about the centre
    (fullscreen-client.md), so the same camera should hold. This plan's T1 is the test of that.
  - The pixel thresholds (offset 120 ms, T_h 0.536) were fitted on native 720 pixels. They are
    re-measured on 1080 FIT data (section 5).
- xmas02sk's chain (xmas02-detector.md): xmas02 (11-06) -> xmas02gb (11-09) -> xmas02sk (11-14).
  - Its last cache, `xmas02-sk-mask-o3h-t-20261114`, holds 3,613 TRAIN frames.
  - Its weights: NAS archive/train/xmas02-sk-20261114/weights/last.pt.
  - All the run-time inputs are intact in /dev/shm/poring-lab-tmp/xmas-det (checked 07:3x by
    sha256): params.json d4cc0a5d..., lattice-train 73053842..., lattice-test 98d3f0d4....

## 2. The approach

- The same pipeline, on 1080 virtual frames:
  - recorded by the same recorder (PNG, 1 fps) beside the same immune watches;
  - labelled by the same rule, re-measured on 1080 FIT;
  - checked by T1 and T2;
  - cached;
  - fine-tuned from xmas02sk's last.pt on 720 TRAIN + 1080 TRAIN mixed. One model for both
    sizes, so no size is locked in (Batt 11-17, "nothing locked").
- The model runs unchanged at run time: the runner feeds it the virtual frame (736x1280), as it
  does xmas02sk today.

## 3. The tools (offline, a tmpfs worktree, tests; merged before FIT records)

- **T-V1 record_session.py v8:** when the virtual client is active, the manifest also carries
  `client_view`: the real rect, mode, world_scale, world_centre and the panels (name, virtual box,
  real position). v8 is v7 plus that field.
- **T-V2 the recording paths:** one rule (`map_labels.check_recording` and
  `detector_vs_packets.check_session` share it) admits:
  - the lab's 720 path (unchanged: rdp, [80,77,1280,720], lab-rathena, png, v5-v8);
  - the virtual 1080 path: rdp, game_region [100000,0,1280,720], lab-rathena, png, v8, and a
    `client_view` with rect 1920x1080, mode fullscreen, world_scale 1.5.
  - Everything else is still refused.
- **T-V3 the UI rectangles of a virtual session:** the layout's rectangles (unchanged) PLUS every
  pasted panel's virtual box from the manifest (not the pointer's), nested windows dropped as
  before.
  - On the virtual picture the panels' boxes are a few pixels larger than the 720 windows. The
    chat panel, for example, is (0,578)-(600,720) against (0,585)-(600,720).
- **T-V4 the names:** the new 1080 sessions in `XMAS02`:
  - FIT by name: `-rdp-xmas02-v1f`;
  - the held-outs refused by NAME like TEST, and read only by `--eval-test`: `-rdp-xmas02-v1T`,
    `-rdp-xmas02-v1Tg`, `-rdp-xmas02-v1Tk`.
- Each with tests and a positive case (a real v8 manifest from a short 1080 recording, admitted;
  a v7 virtual one, refused).

## 4. The data (immune lattice watches at 1080 fullscreen; the Rogue Thief8fce)

The protocol is xmas02-detector.md 2a / Amendment D / S7.3's, unchanged:
- immunity ON and judged ("You are now immune to attacks.");
- the aura off;
- no toast;
- a judged screenshot of the layout and the standard chat window;
- `@killmonster2` at setup; typed GM lines only, no world click;
- after each watch, the recorder stopped by its own PID and the session shipped, before the
  next watch;
- immunity OFF at the end, read back ("Returned to normal state.").

| session | role | stands (lattice) | spawns | seed | time |
|---|---|---|---|---|---|
| v1f | FIT, then VAL | TRAIN side | natural | 2611201 | 30 min |
| v1t1 | TRAIN | TRAIN side | natural | 2611202 | 30 min |
| v1t2 | TRAIN | TRAIN side | natural | 2611203 | 30 min |
| v1g1 | TRAIN | TRAIN side, 16 stands | 2 Garm Babies (1515) per stand, 40 s | 2611204 | ~15 min |
| v1k1 | TRAIN (masked) | TRAIN side, 16 stands | 1 Stormy Knight (1251) per stand, 40 s | 2611205 | ~15 min |
| v1k2 | TRAIN (masked) | TRAIN side, 16 stands | the same | 2611206 | ~15 min |
| v1T | HELD-OUT | TEST side (lattice-test) | natural | 2611207 | 30 min |
| v1Tg | HELD-OUT | TEST side, 16 stands | 2 Garm Babies, 40 s | 2611208 | ~15 min |
| v1Tk | HELD-OUT | sk6a's 32 TEST cells | 1 Stormy Knight, 40 s | 2611209 | ~30 min |

- About 120 MB/min of PNG: about 3.6 GB per 30-min watch. The root disk keeps its 30 GB floor
  (74.7 GB free at 07:3x), and each session is shipped before the next.
- The held-outs are recorded while the GPU trains. Nothing reads them before the model is frozen,
  and they are scored ONCE.

## 5. FIT, the freeze and T1

- `map_labels.py offset`, then `threshold`, then `freeze` on v1f: the same steps and rules as
  Amendment G. The result is params-1080.json, its sha256 recorded before any TRAIN label.
- 4f's terrain test runs again on v1f. If it does not adopt terrain, the rule is `o3h` and is
  named so.
- **T1 (the geometric check, C1):** on v1f, C1 pooled <= 0.050 on >= 100 scored rows (5's bar);
  C2 per species median |dx|, |dy| <= 4 px.
  - A C2 failure is a STOP: the 720 camera does not hold at 1080, and I tell Batt before any
    cache.

## 6. T2 (the blind check)

- Two NEW blind labellers (subagents that see only the pack and xmas02-blind-instructions.txt),
  on a pack from the 1080 TRAIN labels (seed 51).
- The bar is unchanged: each labeller >= 90 % good AND species right >= 95 %.

## 7. The cache and the training

- The cache: the 1080 TRAIN sessions' labels under params-1080, v1k1 and v1k2 masked
  (`--mask-sessions`), the class list classes-xmas02-sk.json, and `--link-cache
  xmas02-sk-mask-o3h-t-20261114` (the 720 TRAIN, 3,613 frames). VAL is v1f.
  - The dry run first; the written counts must equal it.
- The training: `poring_vision.train` in the vision worker (execdev), detached.
  - Init xmas02sk last.pt; YOLO11n; imgsz 1280; batch 2; workers 2; `--mid-ckpt`; `--hsv-s 0.2
    --close-mosaic 3 --scale 0.1` (S4.5's settings); seed 20261004.
  - EPOCHS = min(10, floor(28,800 / (0.64 N + 100))), N = the cache's TRAIN frames. That is at
    most about 8 h at the measured 0.64 s per frame-epoch.
- The scored checkpoint is last.pt. Its sha256 is recorded (the FREEZE) before any held-out file
  is read.
- The GPU is shared with the live copy's detect server (poring-lab-live-vision-worker-1). The
  training never stops or touches it.

## 8. The bars ("the minimum is what 720 achieved"), each scored ONCE

### 8a. At 1080, the new model on the 1080 held-outs, against xmas02sk's 720 results
xmas02sk's and xmas02gb's results are in xmas02-detector.md M11 and S7.6.

| line | measure | 720 achieved | bar at 1080 |
|---|---|---|---|
| A1 | the four species, Q1c on v1T: recall, each | 0.98-1.00 | >= 0.95, >= 50 crops each |
| A2 | the four species, Q1c on v1T: precision, each | 0.93-0.94 | >= 0.90 |
| A3 | Garm Baby, Q1s on v1Tg: recall / precision | 1.000 / 0.922 | >= 0.95 / >= 0.88 |
| A4 | the alarm on v1Tk (S7's rule, post-vanish 5 s): visits fired within 2.5 s | 33 / 33 | at most 1 visit missed, of >= 30 |
| A5 | false fires on v1Tk's alarm-free frames (>= 50) | 0 / 98 | <= 1 % |
| A6 | false fires on v1T + v1Tg's alarm-free frames | 0 / 265 (TEST + gw3) | <= 1 % |
| A7 | latency: D1 server p95 / CPU p95 | xmas02sk | <= 35 ms / <= 1.10 x xmas02sk |

### 8b. At 720, the same model (no loss at 720)
- On xmas02sk's own 720 held-outs (pooled TEST + gw3 + sk6a), xmas02sk's bars: S7's alarm lines
  1, 2a and 2b; Q1c >= 0.80 / 0.80 per species; Garm Baby Q1s >= 0.80 / 0.80.
- Reported beside them: xmas02sk's own numbers on the same files.

### 8c. In play at 1080 (the decisive bar)
- A block of 3 valid 1080 runs with the new model named (screen_ab.py's protocol, s11scr's
  setup), against s11scr-720's A runs.
- Judged as s11scr: kills/h, loot/h, deaths and errors, each SAME at -2 SE.
- Plus a new line: false boss Fly Wings per hour no higher than A's beyond Poisson noise (2 SE).
- Reported: goblin boxes per frame (720: 0.001-0.002), the player found per frame (720: 0.98),
  the cursor's unknown share.
- 8a and 8b pass first, else no play block.
- If 8c fails while the false alarms meet A's level, the remaining causes (the cursor at 1080, the
  item model) are named by time lost and each gets its own round (section 10).

## 9. The order and the times (estimates)

1. The tools (T-V1 to T-V4), merged: ~1.5 h.
2. v1f recorded and shipped: ~40 min. FIT + freeze + T1: ~30 min.
3. The TRAIN watches (v1t1, v1t2, v1g1, v1k1, v1k2): ~2.5 h with the ships. Their labels: ~1 h.
4. T2: ~30 min.
5. The cache: ~20 min. The training: <= 8 h. Meanwhile the held-outs v1T, v1Tg and v1Tk are
   recorded (~1.5 h), and the cursor-at-1080 measurements run (screen-size-ab.md's leads).
6. The freeze; then the export, the registration and 8a / 8b: ~1.5 h.
7. The play block 8c: ~1.5 h.

## 10. Not in this round
- The item model (cause 3): its own round at 1080 (xmas02-fi's pipeline, Amendment O / round 5),
  pre-registered after this one's T1 tells whether the 720 camera holds.
- The cursor at 1080 (cause 2): screen-size-ab.md's leads (a) frame rate in motion, (b) a reads-to-1 s
  probe. They run while the GPU trains.

## 11. RESULTS and AMENDMENTS (clock-labelled; nothing above is edited after this commit except by a labelled amendment)

### Amendment 1 (2026-11-20 07:54 ICT from `date`, before any 1080 recording): the tools as built; the ghosts

- **T-V1 to T-V4 merged:** d5ba886a (feat a588a390) and aed717c8.
  - `scripts/rec_paths.py` holds the two paths; map_labels.check_recording and
    detector_vs_packets.check_session share it.
  - record_session v8 writes `client_view` (captured at the recording's start).
  - The names: v1f is FIT by name; v1T, v1Tg and v1Tk are held out by name.
  - Tests: test_rec_paths.py; 35 related test files pass on main.
  - d5ba886a went in with one NAS-reading test red: it was skipped in the tmpfs worktree, which has
    no `.env` for LAB_STORE_DIR. aed717c8 fixed it. Tests that read the NAS run from the main
    checkout.
- **A finding before recording (a picture of the client at about 07:50, the virtual picture):**
  - At 1920x1080 the real client keeps its windows at their SAVED 720 pixels. panels.json found
    the chat window at real (0, 578).
  - The world behind a real window is unknown, so every virtual frame shows a black GHOST where the
    world transform puts the real window: about (0, 385)-(400, 480) for the chat, and
    (496, 0)-(556, 24) for hotbar2 (half under the hotbar panel).
  - So T-V3's UI is the panels' virtual boxes PLUS their ghosts (`rec_paths.panel_rects`, a test
    built through ClientView.virtual_frame). A unit under a ghost is UI to the label rule.
  - The runner sees the same ghosts at 1080: in play the bot is blind there, as a person at 1080
    would be behind the real chat window. Reported; this round does not change it.

### Amendment 2 (2026-11-20 08:36 ICT from `date`, before the next recording): the camera ZOOM; v1f invalid; the chat finder

- **v1f (07:57-08:20) stopped after 34 stands.** The watch's chat-window check failed at
  xmas_dun02 236,248. Its F10 step then cycled the window to 9 lines, and it stopped without
  typing. 1,350 frames were shipped.
  - **The cause:** at 1080, over the pink wall, `chat_window.find_any` took the hotbar's white edge
    as a 1-line chat window above the real one. It returned the first candidate from the top, and
    the re-check at that place kept it.
  - **Fixed in bd9664fa:** the fullest candidate wins, and none overlapping the found Basic Info or
    hotbar is taken. On the real failure frame it reads the 9-line window (26.7 ms). A test was
    added.
  - The window was put back to 6 lines with F10 (12 -> 15 -> hidden -> bar -> 3 -> 6, a picture
    after each press), then read standard (08:26).
- **FIT on v1f did not fit:**
  - the offset curve was flat at ~16 px median error at every offset (720: 2.2 px at 120 ms);
  - T_h was 0.111 (720: 0.536), and terrain was not adopted;
  - the freeze refused the name.
- **The cause: the client's CAMERA ZOOM, not the size.**
  - On v1f's well-fitting samples (NCC >= 0.5, n 17), the sprites lie 13 % (x) / 15 % (y) farther
    from the centre than the 720 camera predicts.
  - Against two 11-06 xw2 frames (default zoom, the 720 camera's 2.2 px), the same cells now
    (184,205 and 93,82) fit at scale **1.138 / 1.140**.
  - One wheel step down took it to 1.226. Three steps up then gave **1.000**, at both cells
    (pixel error 10.5 / 9.9, the best of all fits).
  - The input log shows people's wheel steps to the lab client from the console: 26 down and 7
    up, between 11-18 14:08 and 11-19 21:25 ICT. The bot sends none.
  - The zoom survives client restarts: the s11scr switches restarted the client after the last
    wheel step, and it was still 1.14 this morning.
- **So the s11scr runs (2026-11-19 23:14 to 11-20 03:13, A and B alike) played at a zoom of 1.14,**
  not the default that camera_rdp.json was fitted at.
  - The runner's cell <-> pixel geometry (walk clicks, reach and stand cells, loot cells) used
    that camera too.
  - Both arms had the same zoom, so the verdict between sizes stands. Each arm's own level may
    have been held back. The s10ab baseline (11-17) predates the wheel steps.
  - Reported here; screen-size-ab.md gets a pointer.
- **The protocol from now on (every recording of this round):**
  - before each watch, a zoom check: a virtual picture at one of the two reference cells, fitted
    against its 11-06 frame by `zoomfit.py` (scratch);
  - scale 1.000 +- 0.01 to proceed; otherwise wheel steps back to it, read again.
- **v1f is marked INVALID** (`dataset_ship.py mark-invalid`: kept, refused by the label tools). It
  is recorded again as v1f at the default zoom. The seed and stands are the same.
