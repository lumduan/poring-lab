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

### Amendment 3 (2026-11-20 09:05 ICT from `date`): v1f recorded again; the client left the front; FIT from it

- **v1f, the second recording (08:37-08:59, the default zoom):** 1,296 frames, 22 min,
  `20261120T083735-rdp-xmas02-v1f`, shipped. The watch stopped after 32 stands. Its GM-line
  identity check failed (name_diff 1411) because the fullscreen client was no longer in front.
  - The end picture shows the desktop, the poring-lab shell window in front, and the client
    minimized on the taskbar at 08:59.
  - The input log has NO human input then: only the watch's own Enter keys and pointer moves
    (real 1870, 566). The trigger is on the Windows side, not known.
  - Restored with the client's own taskbar button (an ASSIST desktop window):
    - the first click (the template found the button at x 1230) left the desktop showing;
    - after it the button showed highlighted, and the template no longer matched;
    - one more click at the same place brought the client back in game (09:03), with no relog, so
      immunity holds.
  - A few frames at the recording's end show the desktop; the label tools' layout check drops
    them.
- **FIT runs on this v1f alone** (22 min instead of 30; the first v1f is invalid, Amendment 2). If
  its offset or threshold has too few samples (Amendment G's sizes: 200 offset samples, 1,459 kept
  labels at 720), a second FIT watch is recorded under its own amendment before the freeze.
- **The TRAIN chain** (`chain.sh`): the zoom check (1.000 +- 0.01 at 93,82, against the 11-06
  frame), the chat window standard, `@killmonster2`, then the watch; it stops on any failure.
  v1t1 started at 09:04:31 (zoom 1.000, err 10.53).

### Amendment 4 (2026-11-20 09:09 ICT from `date`): FIT, THE FREEZE, T1 PASSES -- the 720 camera holds at the default zoom

FIT ran 09:04-09:08 (`run-fit.sh`, CPU, nice 10, a 4 GB scope) on `20261120T083735-rdp-xmas02-v1f`.

| step | 1080 (v1f) | 720 (Amendment G) |
|---|---|---|
| 4b offset | **120 ms**; median 3.16 px at 120-160 ms (100: 4.30; 200: 5.39; 0: 11.0); 86 samples, 26 units | 120 ms, 2.24 px; 200 samples, 53 units |
| 4f terrain | **ADOPTED**: n under 57, drop 0.273, p 3.4e-10 | adopted: 96, 0.257, 1.9e-18 |
| 4e T_h (o3h-t) | **0.504** (the p5 of 721 clear kept labels; p50 0.753) | 0.536 (1,363; p50 0.788) |

- **The FREEZE** at 09:07:55: labels `xmas02-o3h-t`, FROZEN, offset 120 ms, o3h-t, T_h 0.504, E0,
  commit 505ba1df.
  - `/dev/shm/poring-lab-tmp/x1080/fit/params-1080.json`, sha256
    `9c73278f8c1aca1fb315673e3ee350db904407349b7655b14dee4d47c8de0331`
    (offset.json f1d97b17..., threshold.json 75ec5a98...).
- **The sizes are about half of 720's.** The offset curve's minimum is still clear, and T_h is a
  p5 over 721 labels. So no second FIT watch (Amendment 3's condition is not met).
- **T1 (`check --c1-rule round2 --allow-fit` on v1f, as section 5 pre-registered): PASS.**
  - C1 pooled 4 / 280 = **0.0143** (bar <= 0.050 on >= 100). Per species: Christmas Cookie 0 / 49,
    Cruiser 0 / 69, Myst Case 0 / 98, Cookie 4 / 64.
  - C2: every species median |dx| 0-1 px, |dy| 1-2 px (bar <= 4). No stop.
  - t1-v1f.json sha256 42b2be5a....
  - At 720 T1 was read on TEST. Here it is in-sample, as pre-registered, so each TRAIN session's own
    C1 (3c) is the out-of-sample check: each must also be <= 0.050, or that session is not TRAIN.
- **So the 1080 virtual picture at the DEFAULT zoom is the 720 camera's picture** (11-18's 1.50
  measurement, now on labels). Every number above came from frames whose zoom was checked.

### Amendment 5 (2026-11-20 09:20 ICT from `date`): v1t1 stopped on the padlock; the padlock read; v1t1 fails 3c

- **v1t1 (09:04:31-09:09:27, 300 frames) stopped after about 7 stands.** The chat check read the
  padlock as undecided: closed 3.1 / open 15.4 (grey margin 12.3 < 15), shapes 0.213 / 0.223.
  - It was the same on three re-reads; the scene behind (a Myst Case, a bright floor) was static.
  - The chain's next zoom-check warp was refused by the same check, so the chain stopped and
    nothing was typed.
  - Unblocked by one walk click on empty floor. The protocol bans world clicks only inside a watch.
  - The chain restarted with v1t2 at 09:12:42, and **v1t3** (seed 2611210, 30 min) makes up
    v1t1's minutes.
- **The padlock read at 1080, measured on every recorded 1080 frame** (both v1f recordings and
  v1t1, 2,946 frames; nobody touched the padlock, so every frame is truly LOCKED):
  - 2,851 read locked, **45 None (1.5 %)**, 0 open, 50 with no window found (the F10 cycle, the
    desktop);
  - the decided grey margins are >= 12.3 (median 52.2).
  - **Fixed in 0a64a832.** Grey also decides at a margin >= 10, or by a wide separation (the winner
    <= 25, the other >= 2.5x and >= 30 farther), but only when the colour shape does not
    contradict.
  - Result on the same frames: 2,895 locked, 0 open, 0 undecided. The archived 11-05 open frames
    still read open (grey margin >= 39.9). Three boundary asserts moved; all three were truly
    locked frames.
- **v1t1's own C1 (3c's join rule): 11 / 74 = 0.149 > 0.050, so v1t1 does NOT join TRAIN.**
  - The 720 TRAIN sessions on the same lattice scored 0.003 / 0.000 / 0.004.
  - The low rows cluster at two stands (frames 43-81 and 234-289). In the second, the Rogue
    stands on a raised block (her sprite about 75 px above her HP bar).
  - Pictures with the predicted boxes: a Myst Case box on a wall it is hidden behind (frame 60,
    kept "under terrain"), and a Cruiser box on an empty wall top (frame 287, C1 did not flag it).
  - Terrain-under rows: v1f 1 bad of 25; v1t1 15 of 36, plus 11 of 58 other rows.
  - Not decided yet: whether this is a few stands in a 5-min session, or something at 1080 near
    raised terrain. v1t2's and v1t3's own C1 (about 45 stands each) decide. If either fails too,
    no cache is built until the cause is found (raised stands and terrain-under labels first).

### Amendment 6 (2026-11-20 11:12 ICT from `date`, before v1g2 or any held-out records): TRAIN so far; v1g1 out; v1g2

- **The TRAIN watches' own C1 (3c, <= 0.050 on >= 50 standing labels scored):**

| session | recorded (ICT) | frames labelled | kept labels | own C1 | joins |
|---|---|---|---|---|---|
| v1t1 | 09:04-09:09 | 265 | 215 | 11 / 74 = 0.149 | no (Amendment 5) |
| v1t2 | 09:12-09:43 | 1,593 | 1,903 | 10 / 572 = 0.0175 | YES |
| v1t3 | 09:46-10:17 | 1,555 | 1,654 | 8 / 419 = 0.0191 | YES |
| v1g1 | 10:22-10:37 | 735 | 1,455 (Garm Baby 819) | 20 / 356 = **0.0562** | **no** |
| v1k1 | 10:38-10:54 | 716 | 2,927 (knight 344, goblins 1,386) | 0 / 157 = 0.000 | YES (masked in the cache) |
| v1k2 | 10:55-11:10 | (labelling) | | | |

- **v1g1's failure is all Garm Baby:** 20 / 200 bad, while the four common species are 0 / 156. At
  720, gw1 failed the same way (6.21 %) and stayed out; gw2 passed (4.26 %) and joined (M2).
- **As M2 decided at 720, the rule binds as written.** v1g1 is outside T2's pool and outside
  TRAIN. More Garm Baby data comes from a NEW watch under 3c: **v1g2**, TRAIN-side stands, seed
  2611211, the same spawn options (2 Garm Babies per stand, 40 s, 16 stands, 22 min).
- **The held-outs are recorded now** (the lab is free; nothing reads them before the freeze), in
  this order after v1g2: v1T (seed 2611207), v1Tg (2611208), v1Tk (2611209, sk6a's cells
  `789f23e2...`), as section 4.
- Immunity was judged ON at 10:21 (two toggles read) and again before this chain.

### Amendment 7 (2026-11-20 11:19 ICT from `date`, BEFORE the T2 pack, the cache or any GPU step): T2, the cache, the training

- **TRAIN (1080) = every TRAIN watch that passes 3c,** decided mechanically by its own C1: v1t2,
  v1t3, v1k1, plus v1k2 and v1g2 if they pass. Not v1t1 or v1g1.
- **VAL (1080) = v1f** (FIT, then VAL, like xw1). Its labels use params-1080; no own C1 (a FIT
  part).
- **T2:**
  - The pack: `map_labels.py pack --map xmas_dun02 <the 1080 TRAIN label files> --seed 51
    --min-fit 0.504` (the 1080 T_h, as the cache writes), the instructions `dc48fb15...`.
  - 30 per tier species with >= 30 kept labels after the floor.
  - The pack lives in `/dev/shm/poring-lab-tmp/blind-v1-t2/pack`; the key in
    `/dev/shm/poring-lab-tmp/x1080/t2/key`, outside the labellers' tree.
  - Two NEW blind labellers, **AA and AB** (A-Z are spent), with M9's brief and only the paths
    changed (sha256 656f2d61... / 93a8dee2...). At most 2 agents, staggered.
  - Scored ONCE by `blind_score.py`.
  - **The bar per species: each labeller good >= 90 % AND species >= 95 %.**
    - If a common species (1249 / 1248 / 1265 / 1246) fails: STOP, no cache.
    - If Garm Baby, the Christmas Goblin or the Stormy Knight fails: that species' boxes in the
      1080 sessions are MASKED (S4's masked mode, `--mask-sessions`), so the 1080 frames teach
      nothing wrong about it. The 720 TRAIN keeps its passed labels.
- **The cache:** S4.4's form from the main checkout.
  - `--labels map --classes species --class-list config/detector/classes-xmas02-sk.json --kb
    data/kb --map-params params-1080.json --map-params-sha256 9c73278f...`
  - `--map-labels` / `--own-c1` for the 1080 TRAIN sessions, `--train` <them>, `--val` <v1f>
  - `--mask-sessions v1k1 v1k2` (the knight sessions, as sk1a / sk2a), plus any species T2 masks
  - `--link-cache xmas02-sk-mask-o3h-t-20261114` (the 720 TRAIN, 3,613 frames, and its VAL)
  - `--image png --cache-id xmas02-v1080-mix-20261120`
  - The dry run first; the written counts must equal it.
- **The training** (S4.5's recipe; the main checkout's train.py, unchanged):
  - `execdev:vision@43200=python -m poring_vision.train --cache /datasets/.framecache/xmas02-v1080-mix-20261120`
  - `--epochs E --batch 2 --workers 2 --name xmas02-v1080-20261120 --mid-ckpt`
  - `--weights /datasets/archive/train/xmas02-sk-20261114/weights/last.pt` (sha256 0b43ebbf...)
  - `--hsv-s 0.2 --close-mosaic 3 --scale 0.1`
  - Detached by `systemd-run --user`.
  - **E = min(10, floor(28,800 / (0.64 N + 100)))**, N = the cache's TRAIN frames (section 7),
    computed from the cache manifest and written here before the launch.
  - While it trains, the dev lab's detect server is refused (one job per worker). The live copy's
    worker is separate and not touched.

### Amendment 8 (2026-11-20 11:36 ICT from `date`, BEFORE the T2 pack): v1g2 fails too; TRAIN is final

- **v1g2 (11:14-11:30): own C1 32 / 468 = 0.0684.** Fails, so it does not join.
  - Garm Baby is 26 of the 32 bad (26 / 249 = 10.4 %, v1g1: 20 / 200 = 10.0 %).
  - The other species: Christmas Cookie 3 / 51, Cookie 3 / 34, Cruiser 0 / 60, Myst Case 0 / 74.
- **Two Garm watches failing at the same rate look systematic at 1080** (720: gw1 6.21 % out,
  gw2 4.26 % in). So no third Garm watch now; its cause is a question for after the launch.
- **The 1080 TRAIN is final: v1t2, v1t3, v1k1, v1k2** (3,509 frames in the trial dry run).
  - The model still meets Garm Babies: 720 TRAIN 649 boxes, plus 1080's own in the knight sessions
    (the party) 114 + 172, and v1t3's.
  - T2 checks those labels (the pack draws Garm Baby crops from these sessions). Bar A3 on v1Tg
    decides whether that is enough.

### Amendment 9 (2026-11-20 11:48 ICT from `date`, BEFORE the cache): T2 PASSES on every species

- **The pack:** v1t2 + v1t3 + v1k1 + v1k2, seed 51, min-fit 0.504. 210 crops, 30 per species of
  the tier [1249, 1248, 1265, 1246, 1515, 1607, 1251].
  - The pools after the floor: 1,948 / 1,065 / 733 / 740 / 484 / 2,053 / 458.
  - answer_key sha256 7e1148fe...; reference.png d389551c... (byte-identical to the 720 packs).
- **The labellers:** AA (answers 35afd15b...) and AB (caf4c7fb...), NEW, briefs as Amendment 7.
  - Both validated their own JSON with a short script that read only pack.json and their own
    answers. The brief asks for that check.
- **Scored once** (`blind_score.py`):

| species | AA good / species | AB good / species | verdict |
|---|---|---|---|
| Myst Case 1249 | 100 / 100 | 100 / 100 | PASS |
| Cruiser 1248 | 96.7 / 100 | 96.7 / 100 | PASS |
| Cookie 1265 | 100 / 100 | 100 / 100 | PASS |
| Christmas Cookie 1246 | 100 / 100 | 100 / 100 | PASS |
| Garm Baby 1515 | 100 / 100 | 100 / 100 | PASS |
| Christmas Goblin 1607 | 100 / 100 | 90.0 / 100 | PASS (at the bar) |
| Stormy Knight 1251 | 100 / 100 | 96.7 / 100 | PASS |

  - Agreement: q1 210, q2 206, q3 210 of 210.
- **So no species is masked beyond the pre-registered knight-session masks.** The cache and the
  training run as Amendment 7.

### Amendment 10 (2026-11-20 12:07 ICT from `date`, BEFORE the GPU step): the cache as built; E = 6

- **The cache** `xmas02-v1080-mix-20261120` (guarded `cache:` 11:48:34-12:06:41, ALL STEPS OK,
  1,083 s): 4,401 frames written, equal to the dry run (1080 TRAIN 3,509 + v1f VAL 892).
  - With the linked 720 cache: **TRAIN 7,122 frames** (10 sessions) and VAL 1,998 (3 sessions);
    20 shards.
  - manifest.json sha256 3331793f....
- **E = min(10, floor(28,800 / (0.64 x 7,122 + 100))) = floor(6.18) = 6 epochs** (~8 h).
- **The launch** (Amendment 7's command, E = 6), detached as `poring-train-xmas02v1080`:

      python3 scripts/guarded_build.py --threshold 30 --sustain 30 "execdev:vision@43200=python -m poring_vision.train --cache /datasets/.framecache/xmas02-v1080-mix-20261120 --epochs 6 --batch 2 --workers 2 --name xmas02-v1080-20261120 --mid-ckpt --weights /datasets/archive/train/xmas02-sk-20261114/weights/last.pt --hsv-s 0.2 --close-mosaic 3 --scale 0.1"

### Amendment 11 (2026-11-20 12:27 ICT from `date`): the training was killed by the LIVE copy's guard; fixed; resumed

- **12:07:27-12:16:53:** the training ran (args.yaml as Amendment 10; mid.pt at 12:15). Then its
  exec ended rc 137 (SIGKILL). It was not an OOM kill: no kernel OOM, the container's oom_kill is
  0, and its peak was 10.9 of 11.8 GB.
- **The cause:** the live copy's guard ended ITS detect server (execdev:vision in
  poring-lab-live-vision-worker-1) at 12:16:19, when Batt's live Run stopped. It then listed
  "our GPU processes [1689321, 1694058, 1694061]". Those were the DEV worker's training
  (`python -m poring_vision.train`) and its loaders on the shared Arc, matched as "ours by
  command line", and it killed them.
  - Also: the guard's end-of-step report crashed on its log file. flow_run's SERVE_LOG names the
    same path (`poring-guarded-execdev-vision.log`) and unlinks it at a server start. Reported;
    not changed.
- **Fixed in 2d22893e:** `gpu_ours_exec` drops a process whose cgroup names another docker
  container. The live copy runs it (fast-forwarded 12:3x).
  - Run mode (short-lived step containers) is unchanged; that is an open point.
- **Resumed** (Amendment 7's resume form: `--resume` in place of `--weights ... --scale 0.1`),
  from mid.pt (sha256 prefix in the commit). The epochs, data and settings are unchanged.

### Amendment 12 (2026-11-20 12:56 ICT from `date`): the held-outs are recorded and untouched; the resumed training's log

- **The held-outs are all on the NAS:** v1T (11:30), v1Tg (12:04), v1Tk (12:21-12:53, shipped
  12:53). Each had the zoom check at 1.000 and the chat check before it (chain.log).
- **One mistaken labelling call, refused by NAME, no frame read.** At 12:54 my train-side
  labelling script (`run-train.sh`: labels plus own C1) was started on the three held-outs. It
  must not run on them: 3b, nothing reads them before the freeze.
  - `map_labels.py labels` refused each at once: "shares frames with TEST (3b): refused". It
    wrote three 95-byte logs and no labels.
  - They are read after the freeze, by `--eval-test` only (8a).
- **The resumed training** (Amendment 11) runs at ~1.0 batch/s, 3,254 batches an epoch (~54 min).
  At 12:53 it was at epoch 1 of 6, batch 1,474. The ETA for 6 epochs and their validations is
  ~18:30 ICT.
- **Its guard's step log was unlinked at ~12:45** while it ran, by my own test run.
  - The cause: `test_flow_run`'s detect-server tests patched `SCRATCH` but not `SERVE_LOG`
    (built at import), so `detect_up` unlinked the REAL
    `/dev/shm/poring-lab-tmp/poring-guarded-execdev-vision.log`. Fixed in d9d1bb9b.
  - The training is not affected. The guard writes the deleted inode and would read the path back
    at its end, so `x1080/train/logsync.sh` keeps the path a copy of the inode (at most 15 s
    stale) until the guard exits.

### Amendment 13 (2026-11-20 14:27 ICT from `date`, BEFORE the freeze and before any held-out read): the scoring runbook

Fixed now, so section 8 is scored as 720's was (xmas02-detector.md M6 / S4 / S7.4), once.

- **Names:**
  - N=/mnt/poring-lab-datasets; F=/dev/shm/poring-lab-tmp/x1080/fit (params-1080.json, FROZEN;
    classes-none.json); T=/dev/shm/poring-lab-tmp/x1080/eval; E=data/train/eval/x1080 (the
    worker's /data/train/eval/x1080); M=/dev/shm/poring-lab-detector/model.
  - The held-outs: v1T = 20261120T113048-rdp-xmas02-v1T, v1Tg = 20261120T120438-rdp-xmas02-v1Tg,
    v1Tk = 20261120T122115-rdp-xmas02-v1Tk.
  - The cache manifest is Amendment 10's (3331793f...).
- **0. The freeze:** the guard ends `execdev:vision: OK` and results.csv has 6 rows. The
  last.pt sha256 is recorded in the next amendment BEFORE step 2.
- **1. The ONNX export:** M6 step 1's recipe (the temporary RAM env, imgsz (736, 1280),
  simplify, cpu) gives `xmas02v1080-last-736x1280.onnx` + `.names.json` into M. Their sha256
  are recorded; the env is removed.
- **2. The TEST labels** (`--eval-test`; the names are in map_labels' TEST suffixes since
  Amendment 1), each held-out under params-1080:

        map_labels.py labels --map xmas_dun02 --eval-test $N/<held-out> --params $F/params-1080.json \
            --classes $F/classes-none.json --out $T/labels-test/<held-out>.json

- **3. The packs and the blind labellers** (A1-A3):
  - v1T (the four species) and v1Tg (Garm Baby): `map_labels.py pack ... --per-species 60
    --seed 53`, no fit floor (11-07's evaluation pack ran without one).
  - The instructions: docs/planning/xmas02-blind-instructions.txt, sha256 dc48fb15...
  - Two NEW blind labeller agents per pack (at most two at once; each sees its pack, the
    instructions and its own answers path only): AE / AF for v1T, AG / AH for v1Tg.
- **4. The refs and the predictions:**
  - `eval_q1.py refs <key> --out $E/q1-refs-<s>.json --labels-dir $T/labels-test`;
    v1T's also gets `--latency-200 53`.
  - Then ONE guarded GPU step:
    `execdev:vision@1800=python -m poring_vision.predict_dir --weights
    /data/train/xmas02-v1080-20261120/weights/last.pt --refs ... --out ...`.
  - For the alarm: the same over EVERY frame of v1Tk and of v1T / v1Tg's alarm-free frames
    (`units --all-frames`), as S7.4 step 2.
- **5. The scores, once each:**
  - `eval_q1.py score KEY A B PRED --cache-manifest <Amendment 10's> --out ...`.
  - A1 / A2: Q1c.per_species, the four species on v1T, each with >= 50 crops.
  - A3: Q1.per_species.garm_baby (Q1s: the classes agreeing) on v1Tg.
- **6. The alarm** (A4-A6):
  - `eval_q1.py vanishes $N/v1Tk $N/v1T $N/v1Tg --out $E/vanishes.json`.
  - Then `eval_q1.py alarm --held-out UNITS-v1Tk-all PRED-v1Tk-all --free UNITS-v1T PRED-v1T
    --free UNITS-v1Tg PRED-v1Tg --vanishes $E/vanishes.json --post-vanish-s 5.0
    --cache-manifest <Amendment 10's> --out $E/alarm-v1Tk.json`.
  - A4 = its line 1 (visits fired within 2.5 s), A5 = line 2a, A6 = line 2b.
- **7. The latency** (A7):
  - The GPU: predict_dir's own per-call times over v1T's refs, p95 <= 35 ms.
  - The CPU: `eval_latency.py $E/latency-200-refs.json --model x1080=<step 1's onnx> --model
    xmas02sk=$M/<the deployed xmas02sk onnx> --out $E/latency-cpu.json` (nice 10 by itself),
    p95 <= 1.10 x xmas02sk's.
- **8. 8b** (no loss at 720):
  - xmas02sk's own 720 held-out keys, answers and refs are REUSED as archived (TEST xw5 / xp1 /
    X2, gw3, sk6a; nothing re-labelled or re-asked). Only the predictions are new: the 1080 model
    by the same predict_dir step.
  - Scored by the same score / alarm commands against S7's bars (lines 1, 2a, 2b; Q1c >= 0.80 /
    0.80; Garm Baby Q1s >= 0.80 / 0.80), with xmas02sk's own numbers beside them.
- **9. Then:** the worker stopped (verified), the results here, the run archived to the NAS
  (`guarded_build.py archive:`), the scratch shipped the same day. 8c (the play block) only after
  8a and 8b pass; deployment is Batt's decision.

### Amendment 14 (2026-11-20 17:59 ICT from `date`, BEFORE the freeze and before any held-out read): Batt's play is the bar

- **Batt 2026-11-20 ~18:0x** (from his phone, after the report's "the scores against the 720
  bars"): "เอาการเล่นฉันเป็นเกณฑ์" ("use my play as the bar"). It restates his 11-12 rule: his own
  run is the bot's bar, and the bot is reported as a share of it.
- **His run:** `20261112T214008-demo-human-demo-xmas02` (rogue-xmas02.md 4DK; on /economy as
  `batt-xmas02-20261112`): 30.5 min, 228.5 kills/h, common z/h 135,737, gross OC 173,601, 0
  deaths. It was played at the lab's 720 window; no human run at 1080 exists.
- **What changes, decided before any held-out read:**
  - 8a and 8b are UNCHANGED. They are the detector's floors (recall, precision, alarms, latency):
    they say nothing about play, and they only gate the play block.
  - 8c's HEADLINE becomes the share of his run, on the same rulers (series_score.py,
    time_budget.py compare --target his sid --live 1830, econ_dash): kills/h, loot/h and z/h of
    each 1080 run AND of the s11scr-720 A runs, each as a % of his.
  - For scale (recorded before 8c runs): 720 A 129.2 kills/h = 56.5 % of his; 1080 B 72.9 =
    31.9 %; B2 86.9 = 38.0 % (screen-size-ab.md).
  - The registered verdict line (SAME as 720 at -2 SE) stays, so the block is judged as planned.
    A pass line in HIS terms (e.g. ">= N % of his kills/h") needs Batt's number. It was asked on
    2026-11-20; until he gives it, 8c reports his share beside the registered verdict.
  - Optional, Batt's choice: a human run of his at 1080 would make the bar like for like.

### Amendment 15 (2026-11-20 18:44 ICT from `date`, BEFORE step 2 and before any held-out read): THE FREEZE

- **The training ended** 18:40 ICT; its systemd unit is inactive. The guard's last line is
  `execdev:vision: OK` (capture stall 0.0 %), and `ALL STEPS OK`.
- **results.csv has 6 rows** (the validation set v1f, not a held-out):

| epoch | mAP50 | mAP50-95 |
|---|---|---|
| 1 | 0.99357 | 0.92027 |
| 2 | 0.99369 | 0.92222 |
| 3 | 0.99350 | 0.92627 |
| 4 | 0.99372 | 0.92826 |
| 5 | 0.99354 | 0.93037 |
| 6 | 0.99394 | 0.93105 |

- **FROZEN: `data/train/xmas02-v1080-20261120/weights/last.pt`, sha256
  `1a9feeff003842a4625a589287b315d9884140ac989517ffc10b7b95c0cca236`** (5,533,274 bytes). It is
  the model Amendment 13's steps score.
- best.pt (`3f7f75088b14...`) is NOT used (Amendment 13 names last.pt).
- Nothing of v1T, v1Tg or v1Tk has been read: no labels, packs or predictions. The next steps
  are Amendment 13's 1-9, in order.
