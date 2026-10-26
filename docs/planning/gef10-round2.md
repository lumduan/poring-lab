---
doc_type: measurement
hypothesis: "Round 2 of the gef_fild10 detector needs only a C1 measurement fix (the pickup notice), not a label change: the notice rule changes C1 on FIT / TRAIN nowhere (no scored row lies under a notice), so the TRAIN labels, T2's pack and its pass stand; and the live detector v1 is NOT accurate on gef_fild10 against the packet truth of Batt's demo, so a gef10 model is worth training (Batt, 2026-10-26: 'if it is not accurate, you may train YOLO on the monsters')."
status: "DRAFT (offline groundwork)"
role: null
verdict_date: null
verdict_ticket: null
supersedes: null
related: [gef10-detector.md, gef10-round2-measure.md, rogue-gef10.md, ../benchmarks/gef10-eval.md, ../../scripts/map_labels.py, ../../scripts/detector_vs_packets.py]
next_action: "The parent commits round 2's pre-registration (TEST2 = a9 + a10 + a11, never read; C1 under `--c1-rule round2`; the same bars), THEN runs T1 on TEST2 once. Measured here (FIT / TRAIN and Batt's demo only): the notice rule excludes 0 of 527 C1 rows on FIT / TRAIN (C1 8 / 527 before and after); v1 finds 8.0 % of the monsters in view on Batt's demo (Orc Lady 1.4 %, Orc Warrior 8.8 %, Poporing 52.5 %), precision 18.7 %."
title: "gef10 round 2: the notice rule in C1 (code, and its effect on FIT / TRAIN), and the live detector's accuracy on Batt's demo"
date: 2026-10-26
owner: Batt
---

# gef10 round 2: the offline groundwork

**Batt, 2026-10-26 ~09:4x ICT** (rogue-gef10.md Amendment L, decision 3): "YOLO round 2 for this
map: go. If it is not accurate, you may train YOLO on the monsters", with his own play as the
minimum bar.

**What this is.** The code for round 2's C1 rule, its effect on the FIT / TRAIN parts, and the
live detector's accuracy on Batt's demo, made offline by a subagent. It decides nothing. The
round-2 pre-registration is the parent's to commit; nothing here is a frozen rule.

**What was read.** The FIT parts (the watch's cells 0-10, pilot, pilot2) and the TRAIN-joined
sessions a2, a4 and w2, all under the frozen `params.json` (sha256 `00ef6383...b0aac1`). Batt's
demo `20261026T095021-demo-human-demo-gef10`: its `boxes.jsonl`, `packets.jsonl.gz`,
`manifest.json`, and for the by-eye check 10 of its NAS frames plus 2 chat-window crops. **No TEST
data was read**: not round 1's TEST (the watch's cells 11-14, a7, a8; spent) and not TEST2 (a9,
a10, a11; never opened, read or listed).

## 1. The notice rule in C1 (code: 8261acf)

- **Switch:** `map_labels.py check --c1-rule round2`. The default, `--c1-rule round1`, is the
  frozen round-1 check. Every check output records `c1_rule` (its name, what it does and, for
  round2, the detector and the counts).
- **The rule:** a standing label whose PREDICTED box overlaps a notice detected in that frame
  is not scored. Overlap means any area > 0. The notices come from
  `gef10_r2_measure.find_notices` on the frame's top 174 rows (validated in
  gef10-round2-measure.md 2: 587 / 595 positives, 0 / 8,156 false).
  - The reason is `notice`, counted per species (`notice:<job>`) like the other exclusions.
  - It applies to the standing candidates, and to the under-model ones BEFORE their o3h fit.
  - It runs after the static UI rule (`ui_or_edge`) and the other packet-side rules. Only a row
    that would otherwise be scored or fitted can become `notice`.
  - REPORTED, deciding nothing: `frame_with_notice` (frames read with a notice), and
    `notice_near` on each scored row of such a frame (its box grown by 16 px touches the notice).
- **Where:** `orc_labels_fix._check_rows` gained an optional per-frame pixel exclusion
  (`_JOB["frame_rule"]`). Without it the path is unchanged, for orcsdun01, pay_fild07 and
  round 1 alike. `map_labels.NoticeRule` is that exclusion.
- **Guards** (`c1_rule_refusals`, before anything is read):
  - `round2` runs on gef_fild10 only.
  - `round2` refuses round 1's spent TEST (the watch's cells 11-14, a7, a8).
  - TEST2 (a9-a11) is checked under `round2` only, so a round-1 check cannot spend it.
  - `MapSpec.test2_suffixes` makes a9, a10 and a11 TEST for `labels`, `pack` and the frame cache
    (`is_test`). Round 1's own TEST is `is_round1_test`.
- **Tests** (`services/backend/tests/test_map_labels.py`, synthetic frames only):
  - a frame with a drawn notice over a label (13r's geometry: box top y 28, notice x 541-800,
    y 76-106) excludes it as `notice` under round2;
  - the same frame without the rule scores it;
  - a box 11 px beside the notice is scored and marked `notice_near`;
  - a frame with no notice changes nothing;
  - under-model candidates are filtered before their fit;
  - the refusals, and the flag's default.

### 1a. RESULT: round2 vs round1 on FIT / TRAIN (2026-10-26 10:49-11:03 ICT, `date`)

Both rules ran on the same six parts, with the frozen params, `--workers 1`, nice 15. The code was
the working tree that became 8261acf (`map_labels.py` and `orc_labels_fix.py` unchanged since).

| part | role | scored | bad | round2: excluded `notice` | frames read with a notice | scored rows within 16 px of a notice (bad) |
|---|---|---|---|---|---|---|
| watch cells 0-10 | FIT | 72 | 0 | 0 | 0 | 0 |
| pilot | FIT | 53 | 1 | 0 | 12 | 1 (0) |
| pilot2 | FIT | 0 | 0 | 0 | 0 | 0 |
| a2 | TRAIN | 64 | 1 | 0 | 7 | 2 (0) |
| a4 | TRAIN | 67 | 0 | 0 | 2 | 0 |
| w2 | TRAIN | 271 | 6 | 0 | 0 | 0 |
| **all** | | **527** | **8** | **0** | **21** | **3 (0)** |

- **C1 before and after: 8 / 527 = 1.5 %, row for row.** On FIT / TRAIN no standing row lies under
  a notice. That agrees with gef10-round2-measure.md 3: "0 of 527 scored rows lie under a notice;
  3 lie within 16 px of one (none bad)". So the rule changes C1 there only where a notice covers a
  scored box, and on these parts that never happens.
- **Round 1 reproduces bit for bit** (10:56-11:03 ICT). Each part was compared with the rows
  the measurement wrote at 03:27-03:33 (commit 2ed1fa7, archived in
  `scratch-archive/2026-10-26/gef10-r2/c1rows/`):
  - every `round1` rows file is **byte-identical** to the archived one, all six parts;
  - every count in its check file is equal. Only the clock, the commit, the paths and the new
    `c1_rule` key differ;
  - the `round2` rows equal the `round1` rows once the REPORTED `notice_near` key is taken out.
- **The positive case is synthetic.** No real FIT / TRAIN row lies under a notice, so none exists
  there. The detector's own positives are real (587 / 595). The OUT sessions (s1, a1, a3, a6:
  neither TRAIN nor TEST) hold 365 frames with a notice and could give a real positive case. They
  were not read here; that is the parent's call.
- **Why T2's pack does not change:** the rule lives in `check` only. `labels`, the label files
  and `pack` do not use it. Under the frozen params the TRAIN label files, and therefore T2's
  seed-31 pack, are byte-identical to round 1's. gef10-round2-measure.md 3 had already found that
  0 of 2,413 kept TRAIN labels overlap a notice: the masked-NCC fit drops a label under the
  notice's opaque white box.

## 2. The live detector on Batt's demo (code: 3428272)

`scripts/detector_vs_packets.py score` takes each `boxes.jsonl` capture time t (the CPU unit
detector `v1png-last-736x1280.onnx`, conf 0.25, on fresh grabs, game-region px). At that t it
projects the monsters the packets put on screen, exactly as `mvp_watch_study.truth` does. That
`truth` was refactored into `truth_stack` + `truth_row`; its JSON is byte-identical on pilot2
(523 frames, 604 units, sha256 `2065daa8...`).

- **The projection:** the Timeline at t - 120 ms; `predict_sprite`'s box; k 0.14; the RDP
  camera; labels_for_v1's in-view rule (at least half the box on screen, under half behind the
  UI).
- **Recall:** an in-view truth box is found when it contains the centre of a v1 `monster` box.
  The one-to-one variant (each detection serves one unit, nearest centre first) is beside it.
- **Precision:** a v1 `monster` box is true when its centre lies in SOME monster's box.
- **Distance:** Chebyshev, in cells, from our character, rounded.

**The window:** `t0_live_ns` + 898 s. 2,628 captures fall in it; 152 are off the map (the orc
house at the end), so **2,476 are scored**.

**The chat window:** Batt dragged it at 09:51:04 (Amendment L), 3.7 s into the window. His frames
show it at y 615-709, where the hunting layout has 532-626 (measured on two frames' row
profiles). So the main run replaces that one rectangle (`--chat-rect 0,615,600,709`). The run with
the layout as briefed changes little: 2,555 in-view rows, recall 7.7 %, the same precision.

**By eye** (10 frames whose capture time equals a recorded frame's, client pixels in `/dev/shm`
only):
- the truth boxes sit on the drawn orcs and Poporings, standing or walking;
- the misses are real: orcs fighting next to the Rogue, drawn plainly, with no v1 box;
- false boxes sit on the village well, small rocks and a skull: static scenery.

### 2a. Recall per species and by distance (rows = unit x capture, in view)

| species | in view | recall | one-to-one | 0-5 cells | 6-10 cells | 11-15 cells |
|---|---|---|---|---|---|---|
| Orc Lady 1273 | 1,600 | 23 = **1.4 %** | 1.2 % | 12 / 1,201 = 1.0 % | 2 / 143 = 1.4 % | 9 / 256 = 3.5 % |
| Orc Warrior 1023 | 658 | 58 = **8.8 %** | 8.8 % | 16 / 464 = 3.4 % | 4 / 70 = 5.7 % | 38 / 124 = 30.6 % |
| Poporing 1031 | 238 | 125 = **52.5 %** | 52.5 % | 13 / 45 = 28.9 % | 76 / 114 = 66.7 % | 36 / 79 = 45.6 % |
| Orc Baby 1686 | 0 | -- | -- | -- | -- | -- |
| others (Green Plant 1080) | 88 | 0 = **0.0 %** | 0.0 % | 0 / 25 | 0 / 51 | 0 / 12 |
| **all** | **2,584** | **206 = 8.0 %** | 7.8 % | 41 / 1,735 = **2.4 %** | 82 / 378 = **21.7 %** | 83 / 471 = **17.6 %** |

- **No row lies at 16+ cells.** At 1280 x 720 the screen shows at most about 15 cells from our
  character, so "at range" means 11-15 here.
- **By the unit's state:**

  | state | rows | recall |
  |---|---|---|
  | attacking | 625 | 0.8 % |
  | hurt | 387 | 2.3 % |
  | idle | 1,043 | 13.5 % |
  | walk | 529 | 9.6 % |

- **By our own motion** (our position changed in the 500 ms before tw):

  | our character | rows | recall |
  |---|---|---|
  | moving | 584 | 1.5 % |
  | still | 2,000 | 9.9 % |

- **Frames:** 1,609 scored captures had a monster in view. In 1,031 of them (64 %) v1 drew no
  monster box at all.
- **First sight** (a unit's consecutive in-view captures, gaps <= 2 s):
  - 80 episodes; **v1 hit the unit at least once in 29 (36 %)**;
  - the median first hit came 3.2 s after the unit entered view (p90 7.2 s);
  - 68 of the 80 episodes began at 11-15 cells.

  | species | episodes detected / all |
  |---|---|
  | Orc Lady | 13 / 43 |
  | Orc Warrior | 9 / 21 |
  | Poporing | 7 / 10 |
  | Green Plant | 0 / 6 |

### 2b. Precision

| | boxes | share |
|---|---|---|
| v1 `monster` boxes | 1,087 | |
| on a monster (true) | 203 | **18.7 %** |
| on a unit in its die animation | 7 | 0.6 % |
| on our own character | 6 | 0.6 % |
| within 16 px of a monster's box | 26 | 2.4 % |
| elsewhere (scenery) | 845 | 77.7 % |

- **The true boxes by species:** Poporing 125, Orc Warrior 57, Orc Lady 21.
- **Confidence:** the median true box scores 0.72 and the median false one 0.54. Raising the
  threshold trades recall for precision without reaching either:

  | conf >= | recall | precision | boxes |
  |---|---|---|---|
  | 0.25 (live) | 8.0 % | 18.7 % | 1,087 |
  | 0.4 | 6.9 % | 22.3 % | 794 |
  | 0.5 | 6.6 % | 25.4 % | 670 |
  | 0.6 | 5.8 % | 31.0 % | 484 |

- v1 drew 9 `npc` boxes and no `player` box: it does not see the Rogue as a player.

### 2c. Latency (the `ms` field: the detector's inference time per grab)

- **Median 263 ms, p95 404 ms**, max 704 ms (2,628 captures).
- This is the CPU ONNX model at 1280 x 736 with 8 threads, run during the demo beside the 5 Hz
  frame recorder.

### 2d. What it means (no decision)

**v1 is not accurate on gef_fild10.** Against its own prt_fild08 numbers (gold set P 0.902 /
R 0.830):
- it finds 1.4 % of the Orc Ladies in view and 8.8 % of the Orc Warriors;
- those two species were 38 + 18 of Batt's 58 kills;
- with 1 to 3 % recall at 0-5 cells, the fights are effectively invisible to it;
- at 11-15 cells it finds 3.5 % of the Orc Ladies and 31 % of the Orc Warriors;
- three of its four boxes are scenery.

Only the Poporing (a Poring look-alike, which v1 knows) is found about half the time. Batt's
condition for training a gef_fild10 model is met by these numbers. The scored runs' 42.6 kills/h
against his 232.7 (Amendment L) is consistent with a bot that rarely sees its targets, though this
measurement does not show that the detector is the cause.

## 3. Where the outputs live (client-derived pixels and data: `/dev/shm` and the NAS, never committed)

- `/dev/shm/poring-lab-tmp/gef10-r2b/` holds:
  - `c1/`: both rules' check and rows files for the six parts;
  - `demo/`: `score-chat.json` (the main run), `score-hunt.json` (as briefed), `pairs-chat.json`
    (every scored capture), the 5 by-eye sheets and the 2 chat crops;
  - `refactor/`: the truth() equivalence run.
- A same-day copy is on the NAS at `/mnt/poring-lab-datasets/scratch-archive/2026-10-26/gef10-r2b/`
  (65 files, about 6.5 MB). Its `checksums.sha256` was verified at 11:03:43 ICT (`date`).
- Re-run:

      W=<worktree>; T=/dev/shm/poring-lab-tmp/gef10-det
      python $W/scripts/map_labels.py check --map gef_fild10 <FIT / TRAIN part> --params $T/params.json \
          --c1-rule round2 [--allow-fit] --rows rows.json --out check.json
      python $W/scripts/detector_vs_packets.py score /dev/shm/poring-lab-demo/20261026T095021-demo-human-demo-gef10 \
          --map gef_fild10 --layout hunt --window-s 898 --chat-rect 0,615,600,709 --out score.json
