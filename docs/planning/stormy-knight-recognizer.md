---
doc_type: design
hypothesis: "From pixels alone, the Orc Lord's CPU recognizer recipe (scripts/mvp_watch.py: the boss AURA rule + the party window detector), refitted on xmas_dun02, tells 'the Stormy Knight (1251) or its summons (Garm Baby 1515, Christmas Goblin 1607) are in view' within 1 s of their first frame in view on >= 95 % of held-out lattice cells, with <= 1 false positive per 10 min of hunting frames, at <= 60 ms p95 per frame -- enough for a Fly Wing at first sight."
status: "ROUND 2 HELD-OUT SCORED 2026-11-09 19:46 (section 12, Batt asked): recall 5 / 16 FAIL, false positives 0.39 / 10 min PASS, latency 33.7 ms PASS -> NOT ADOPTED. Round 1 (section 6): NOT ADOPTED. The kill-before-run schedule stays."
role: null
verdict_date: null
verdict_ticket: null
supersedes: null
related: [rogue-xmas02.md, orclord-recognizer.md, xmas02-detector.md, gpu-recording.md, ../adr/0024-gpu-video-recordings.md, ../../scripts/mvp_watch.py, ../../scripts/mvp_watch_study.py, ../../scripts/stage_items.py, ../../scripts/watch_lattice.py]
next_action: "A round 3 only if Batt wants it: pre-registered first, fresh held-out recordings, 10e's recipe (every room in >= 2 DEV sessions, a leave-one-out threshold)."
title: "A Stormy Knight recognizer for the Rogue's flee rule on xmas_dun02 (pixels only, CPU; the Orc Lord's recipe refitted)"
date: 2026-11-09
owner: Batt
---

# A Stormy Knight recognizer for the Rogue's flee rule on xmas_dun02

**Why** (Batt, 2026-11-09 ~06:3x, rogue-xmas02.md Amendment L 2): "do not disable the MVP; train
the bot to know the boss: seen on the screen -> Fly Wing away at once". The Stormy Knight killed the
Rogue in p18 (2026-11-08 23:16:52-54: 1,170 then 5,912 damage 0.4 s apart, her HP 5,070); the
reactive Battle Log guard (`boss_of`) cannot beat two hits 0.4 s apart. The runner needs, from
PIXELS ONLY at decision time, "the Stormy Knight or its party is in view", as early as possible.
Packets are offline ground truth only (ADR-0007).

**The caution carried over** ([orclord-recognizer.md](orclord-recognizer.md) 12-13): the Orc
Lord's recognizer passed its offline bars, but its LIVE flee proof did not: the Lord could hit
0.97 s after entering view and the aura did not fire in time; the sight-flee was NOT adopted.
So until a Stormy Knight flee proof passes, Amendment K's schedule (`@mobsearch` +
`@killmonster2` before each run, 25-min pilots in the dead window) stays the protection.

## 1. What is known (before any data)

- The party: Stormy Knight (1251, MVP, sprite box ~141 x 133 px, aggressive), its summons Garm
  Baby (1515, ALSO a regular 30-min spawn on this map) and Christmas Goblin (1607, summons only)
  (xmas02-detector.md 1b). `dungeon_hunt.boss_names` already names all three for the boss guard.
- **The live peek (2026-11-09 07:51:45-07:52:5x, the Rogue immune, `@warp xmas_dun02 241 207` onto
  its `@mobsearch` cell; three game-region frames ~1 s apart, kept on the NAS, never committed):**
  - the Knight: a large red-caped figure with ice-white shoulder spikes, ~150 px tall;
  - its party around it: 2 Garm Babies (white, wolf-like) and ~5 Christmas Goblins (orange caps);
  - a green-yellow glow at the Knight's feet in both stills (the boss effect the Orc Lord's AURA
    rule reads: G >= 236, G - R >= 25, G - B >= 25 there) -- to be measured on the watch, not
    assumed;
  - a dark "!!" emotion box above every party member; one frame showed a large white lightning
    burst (a skill) over the party.
- xmas_dun02's floor is orange / tan / teal tiles; saturated bright green is not expected on it
  (to be measured on the hunting negatives).

## 2. The plan

- **B1 (offline code, no live step):** `mvp_watch_study.py` per BOSS: the party ids, the names,
  the map and the negative species become a profile (`orclord` = today's values, its tests
  unchanged; `stormy` = 1251 + 1515 + 1607 on xmas_dun02, negatives Myst Case / Cruiser / Cookie
  / Christmas Cookie). `mvp_watch.py`'s model file names its profile; the runner loads the map's.
  ➡️ **BUILT 2026-11-09 (branch `feat/boss-profiles`; section 2a).**
- **B2 (live data, immune, the lab server only):**
  - the WATCH: `watch_lattice.py` cells on xmas_dun02 (train + test lattices, the three-check
    stand cells), `stage_items.py watch --spawn 1251` (one Stormy Knight per cell beside the
    immune Rogue, a 40-s dwell, `@killmonster2`, the next cell), 16 cells; recorded at 1 fps with
    `--format png` (ADR-0024 decision 4: cue studies need PNG);
  - the HUNTING NEGATIVES: one 25-min explore run on the base recorded with `--format png`, the
    MVP dead by the schedule (its own pilot label; the run's other bars as 4AL's).
- **B3:** the truth (`mvp_watch_study.py truth`, the projection of the label pipeline with
  xmas_dun02's GAT), the fit on DEV, the score on HELD-OUT once (section 3).
  ➡️ Part 1 (the DEV recipe, the fit, the frozen model) DONE 2026-11-09: section 5.
- **B4 (after B3 passes):** the flee rule in the runner (`seen` -> Fly Wing at once, every ~0.5 s,
  beside the reactive boss guard) and its LIVE proof, pre-registered on its own: spawned Knights
  with immunity OFF, a heal at every trial start, stop after a near-death -- section 13's lessons.

### 2a. B1: what was built (2026-11-09; offline code only, no data of this study touched)

**The profiles** (`scripts/mvp_profiles.py`; the KB derivation `kb_party`, as
`dungeon_hunt.boss_names` but by id, agrees with both against the local `data/kb`):

| field | `orclord` (= the Orc Lord study, unchanged) | `stormy` |
|---|---|---|
| boss + summons (the party) | 1190 + 1189, 1473 | 1251 + 1515, 1607 |
| negatives (the map's other species) | Orc Warrior, Orc Lady, Orc Baby, Poporing, Blue / Green Plant | Myst Case 1249, Cruiser 1248, Cookie 1265, Christmas Cookie 1246 |
| maps (first = the hunting map, the truth's default) | gef_fild10, prt_fild08 (round 2's watch) | xmas_dun02 |
| DEV / HELD-OUT watch cells | 0-7 / 8-14 | 0-7 / 8-15 (section 3) |
| `lone` (party jobs that also spawn alone) | none | 1515 Garm Baby |
| sprites (default) | the gef10 prep dir (`/dev/shm`, gone; NAS copy 2026-11-03) | the X1 archive on the NAS (`scratch-archive/2026-11-05/x1`, all 7 species) |
| aura threshold / ring (a, b; inner a, b) / grid / dy / rim rule | 0.08 / (27, 15, 17, 8) / 3 / 8 / G >= 236, G - R >= 25, G - B >= 25 | **None: PLACEHOLDERS, not fitted.** B3 measures the Knight's own aura on DEV |

**What changed:**
- `mvp_watch_study.py`: `--boss PROFILE` on `truth` / `fit` / `score` / `entries`, default
  `orclord`, so every command line in orclord-recognizer.md 9 and 11 works as written. The party,
  names, map, sprites, cells and the fit's aura recipe come from the profile.
- **Fail closed:**
  - a truth names its boss (`boss`; a truth without one is the Orc Lord's), and fit / score /
    entries refuse another boss's truth;
  - they refuse a watch `events.jsonl` whose spawns are another mob, and a model of another
    profile;
  - `truth` refuses a party species without a decoded sprite (its frames would all read as
    negatives), and a map whose GAT is not extracted (flat ground otherwise, silently);
  - `fit --boss stormy` refuses until every recipe placeholder has a value.
- **The Garm Baby caveat (section 3):** hunting frames with a Garm Baby that are not `neg` are
  left out of the negatives (in fit and score) and reported apart. `score` gives
  `hunting[].lone`: frames, pos, seen, episodes, `episodes_seen` and `episodes_seen_per_10min`
  (the Fly Wings a lone Garm Baby would cost). The Knight or a Goblin in a hunting frame still
  refuses.
- **The chat window of the session's date:** `truth --chat auto` (the default) takes the
  2026-11-05 docked window (0, 585, 600, 720) for sessions from 20261105T12 on, as
  detector_vs_packets score-session does.
  - The in-view rule uses it (the nested notice_left dropped), and the truth records it
    (`chat`).
  - fit / score / entries mask decide()'s UI with the truth's own layout and chat window
    (`mask_rects`).
  - The Orc Lord's sessions all get the legacy window, which IS client_layout's and mvp_watch's:
    unchanged.
- `mvp_watch.py`:
  - a model names its `profile` and its `aura_rule` (the rim rule is now per model; decide()
    reads it through the cached LUT, so its cost is unchanged);
  - `load(path, sha256, profile=P)` raises ModelUnavailable for another profile's model;
  - `default_model(P)` = `data/mvp_watch/<P>-v1.npz` (the default path stays the Orc Lord's);
  - the Orc Lord's v1 file format is kept byte for byte: no `profile` member, so a file without
    one is the Orc Lord's.
- **The Orc Lord stays reproducible.** Re-run on bot-server on 2026-11-09 08:2x ICT with
  orclord-recognizer.md 9's command lines unchanged (no `--boss`). The inputs are archived on the
  NAS: the recordings, `scratch-archive/2026-10-25/orclord/work/*-truth.json`, and ow1's
  events in `scratch-archive/2026-10-26/demo-sessions/`.
  - `score`, with the frozen model (sha256 43179452...): every result key is IDENTICAL to
    `score-supplement.json` (cells, recall 5 / 7, pos frames, watch gap, the pilot's and s1's
    false positives, the bars). Only the latency differs: p95 40.9 ms against 53.5, another
    host.
  - `fit`: the same DEV frames (the three memmaps' frame ids byte-identical to the archive's),
    the same item counts and every number fit3.log reports.
    - The body LUT, the title bar and the ring are bit-identical. The logistic weights differ by
      at most 3e-6 (zone_penalty 6.201293 against 6.201304), so the file hashes `3c7f7003...`,
      not 43179452....
    - The pre-B1 code (99ff12b3 plus only the copy fix below) gives the same `3c7f7003...` on
      this host. So the difference comes from the host's floating point (VM 103 then, bot-server
      now), not from B1.
    - The frozen model stays the archived 43179452....
  - **A fix found on the way:** the pre-B1 fit was OOM-killed twice under `MemoryMax=4G`.
    `train_party` kept views into every frame's window vectors (~4.5 MB a frame); it now keeps
    copies (the same numbers). The fit then ran in 2 min 51 s at ~3.2 GB RSS, 0.85 GB of which
    is its /dev/shm memmaps.

**Still the Orc Lord's, on purpose (one recipe, refitted; section 3 changes only the boss and the
map):**
- our own character's masks (CENTRE_BOX, SELF_ZONE), the title-bar guard;
- the projection's 1d = 120 ms and k = 0.14;
- the party detector's features, window, margin (+ 1.0), body-LUT weights and hard-negative
  rounds;
- RECALL_S 1.1 s, the 3-s episode gap, the hunting recording's first 300 s as DEV, the bars.
- The live tools `orclord_edge_watch.py`, `orclord_flee_proof.py` and `orclord_flee_score.py`
  stay the Orc Lord's (B4 writes the Knight's own flee proof). The runner's wiring is B4's:
  `mvp_profiles.for_map(map)` gives the profile and `mvp_watch.load(profile=...)` its model.

**B3's command lines** (bot-server; `MAIN` in the study still names `/home/batt`, so `--kb` and
`--mapcache-dir` are given; the watch's `--layout` is the layout its frames show). ➡️ Since
2026-11-09 (commit "fix(scripts): the main checkout's default paths follow the owner's home")
`MAIN` is `Path.home() / "docker" / "poring-lab"`: the two flags are no longer needed on
bot-server, and they still work.

    W=/home/bot/docker/poring-lab; python=$W/.venv/bin/python; T=/dev/shm/poring-lab-tmp/stormy
    export PYTHONDONTWRITEBYTECODE=1 OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1
    export PYTHONPATH=$W/scripts:$W/packages/poring_env/src:$W/packages/poring_dataset/src:$W/packages/poring_packets/src
    CAP="systemd-run --user --scope -p MemoryMax=4G -p MemorySwapMax=0 nice -n 15"
    KB="--kb $W/data/kb --mapcache-dir $W/packages/poring_dataset/src/poring_dataset/_generated"
    WATCH=<the watch's PNG session>; WEV=<the watch's demo dir>/events.jsonl; HUNT=<the hunting PNG session>
    # the truth (GAT: /dev/shm/poring-lab-tmp/gat/data/xmas_dun02.gat; sprites: the profile's)
    $CAP $python $W/scripts/mvp_watch_study.py truth --boss stormy $WATCH --layout hunt $KB --out $T/watch-truth.json
    $CAP $python $W/scripts/mvp_watch_study.py truth --boss stormy $HUNT --layout hunt $KB --out $T/hunt-truth.json
    # DEV only: the aura recipe from B3's DEV measurement (or written into mvp_profiles.STORMY first)
    $CAP $python $W/scripts/mvp_watch_study.py fit --boss stormy --watch $WATCH --watch-truth $T/watch-truth.json \
        --events $WEV --pilot $HUNT $T/hunt-truth.json --work $T/fit --out $T/model/stormy-v1.npz \
        --aura-thr X --ring A B AI BI --ring-cell N --ring-dy D --aura-rule G_MIN DIFF
    sha256sum $T/model/stormy-v1.npz        # frozen: record it here BEFORE the score
    # HELD-OUT, once (cells 8-15 and the hunting recording after its first 300 s)
    $CAP $python $W/scripts/mvp_watch_study.py score --boss stormy --model $T/model/stormy-v1.npz --sha256 <HEX> \
        --watch $WATCH --watch-truth $T/watch-truth.json --events $WEV \
        --pilot $HUNT $T/hunt-truth.json --out $T/score-heldout.json

- The fit decodes its DEV frames into `--work` (half resolution, ~0.7 MB a frame, in RAM): keep
  each memmap under 1 GB and the lab's /dev/shm under 4 GB (CLAUDE.md rule 7).
- The study refuses a VIDEO session (ADR-0024): B2 records with `--format png`.

## 3. PRE-REGISTERED: the split, the scores and the bars (2026-11-09, BEFORE any data)

The Orc Lord's section 3 rules, unchanged except the boss and the map:
- **The split (by lattice cell, never by frame):** DEV = the watch's cells 0-7; HELD-OUT = cells
  8-15, scored ONCE with the frozen recognizer (its sha256 recorded). A watch frame belongs to the
  cell whose spawn precedes it. The hunting recording: its first 300 s on xmas_dun02 are DEV, the
  rest HELD-OUT.
- **Positive** = the decision's `seen`. **Episode** = frames with the Knight or a summon in view
  (the truth's rule), split where none is in view for > 3 s; a cell's first episode starts at its
  spawn. **Delay** = t(first positive of the cell's first episode) - t(the episode's first frame,
  the party's first frame -- the stricter start). **False positive** = a positive frame with no
  party box even partly on screen, per 10 min of frames.
- **Bars:** (1) recall within 1 s (delay <= 1.1 s) >= 95 % of the held-out cells (8 / 8);
  (2) false positives <= 1 per 10 min of the hunting recording's held-out frames; (3) latency p95
  <= 60 ms per 1280 x 720 frame, `nice -n 15`, one thread, >= 200 calls.
- A failed bar is reported plainly with what more data would fix it; nothing is refitted on
  HELD-OUT; a second attempt needs a second watch.
- **Garm Baby caveat (reported, not gating):** Garm Baby also spawns WITHOUT the Knight (its own
  30-min spawn). A positive on a lone Garm Baby counts as a true positive by the truth's rule
  (it is in the party list) -- and a flee from it costs one Fly Wing; its rate on the hunting
  recording is reported.

## 4. B2: the data (2026-11-09, recorded BEFORE any fit; nothing below was scored)

- **The hunting negatives:** `20261109T082234-rdp-hunt-xmas02-p31` -- recorded beside pilot p31
  (rogue-xmas02.md 4AL, the explore run on the base), 08:22:34-08:46:34, PNG (`--format png`),
  recorder v7, 1,440 frames at 1 fps, 3.18 GB, stop "duration"; the MVP dead by the schedule
  (killed 07:52:57).
- **The watch:** `stage_items.py watch --map xmas_dun02 --lattice lattice-train.json --seed 1251
  --max-cells 16 --dwell-s 40 --spawn 1251 --label sk1 --immune-confirmed` (immunity judged ON on
  the Chat tab at 08:49:5x: "You are now immune to attacks."), session
  `20261109T085018-watch-xmas_dun02-sk1`, 08:50:18-09:05:04: 16 cells, 16 spawns, 16 dwells, 16
  `@killmonster2`, reason "done". The lattice: `watch_lattice.py build --map xmas_dun02` (343
  train / 88 test stands, train sha256 7305384271101c45..., in /dev/shm, client-derived).
  Its recording `20261109T085010-rdp-sk-watch1`: PNG, recorder v7, 1,036 frames, 2.22 GB, stopped
  by SIGTERM at 09:07 after the watch's end (stop "stopped by signal").
- At cell 0 (08:50:5x, one screenshot) the spawned Knight stood ~6-8 cells from the Rogue with its
  summons around it (Garm Babies, Christmas Goblins); her HP stayed full (5,070 / 5,070 at
  08:51:2x).
- Both recordings stay local until the truth / fit / score are done, then ship (`dataset_ship.py`).

## 5. B3 part 1: the DEV recipe and the frozen model (2026-11-09 09:1x-09:3x ICT, DEV ONLY; written BEFORE the held-out score)

**What was read:**
- DEV only: the watch's cells 0-7 plus the frames before the first spawn (448 frames on
  xmas_dun02), and the hunt's first 300 s on the map (301 frames).
- They were decoded ONCE into the fit's own half-resolution memmaps (`$T/fit/watch-dev.npy`,
  `hunt-0.npy`, the same frame sets `fit` selects). Every measurement below reads only those.
- No held-out frame (cells 8-15, the hunt after 300 s) was decoded or looked at.
- The truths are the parent's (main's code, `--boss stormy --layout hunt`, the 2026-11-05 chat
  window). Nothing called for re-making them.
- The evidence (client-derived, never committed) is archived on the NAS:
  `scratch-archive/2026-11-09/b3-stormy-dev/` (the analysis scripts, `glow.npz`,
  `neg_hists.npz`, `fit.log`, `gallery/*.png`, a copy of the model; `files.sha256` verified).
  The /dev/shm scratch and the DEV memmaps are deleted.

### 5a. The Knight's aura (the evidence)

- **It exists.** A glowing ellipse lies on the ground at the Knight's feet, as the Orc Lord's
  does.
  - Galleries: 32 crops across the 8 DEV cells (`gallery/knight-dev.png`) and feet zooms
    (`feet1.png`).
  - Its colour runs from mint / white-green on the rim to pale yellow-white inside.
  - It is often covered by the party (white Garm Babies, Christmas Goblins) and by the summon's
    white light bursts.
- **Where.** The pixels that differ from each cell's background, near the foot point (250,268
  px on 301 Knight frames), were binned by offset (`offsets.png`, `offsets_248_40.png`).
  - The rim colours form an elliptical band around a centre ~8 half-res px above the foot point;
    the legs leave its middle empty.
  - Vertical profile at the centre column: arcs at y -12 and -2, a dip at -8 / -9.
  - The dense band lies within 21-24 x 10-12 half-res px outside and 11-14 x 4-5 inside, with
    dy 8 (three candidate rings are drawn on `offsets_248_40.png`).
- **Colour, against xmas_dun02's floors.**
  - The rim pixels the Orc Lord's rule takes at the feet: R median 187 (5-95 %: 131-225),
    G 253, B 162 (95-219). A whiter, saturated mint green.
  - xmas_dun02's GREEN PUZZLE FLOOR under the same rule: R 208 (157-229), G 246, B 142
    (110-208). Yellower and less saturated.
- **The rule, through decide()'s own path.** The DEV negatives are the 301 hunt frames plus the
  80 watch frames of kind `neg`; loading screens are dropped by the title-bar guard. A cell is
  "seen" (aura alone) when its first episode is seen within 1.1 s, at threshold = the negatives'
  max + 0.015.

| rule (G_MIN, DIFF), ring | DEV negatives max (hunt / watch gap) | Knight frames >= threshold | DEV cells seen within 1.1 s, aura alone |
|---|---|---|---|
| (236, 25) = the Orc Lord's, (27, 15, 17, 8) | 0.070 / **0.165** (cell 5's green floor after a warp) | 6.6 % | 0 / 8 |
| (244, 25), (27, 15, 17, 8) | 0.034 / 0.112 | 7.9 % | 0 / 8 |
| (248, 25), (27, 15, 17, 8) | 0.013 / 0.057 | 19.7 % | 0 / 8 |
| (248, 40), (27, 15, 17, 8) | 0.013 / 0.033 | 23.0 % | 0 / 8 |
| **(248, 40), (24, 10, 14, 4)** | **0.019 / 0.042** | **26.3 %** | **2 / 8** |
| (248, 56), (21, 10, 11, 4) | 0.022 / 0.024 | 24.3 % | 2 / 8 |

- **Yellow-green rules are unusable here.** A rule letting R near G fires on the floors:
  - G >= 236, G - R >= 0-10, G - B >= 25-40 (Orc ring): hunt max 0.18-0.79;
  - (236, 0) and (236, 10) on the chosen ring: hunt max 0.97 / 0.28, watch gap 1.00 / 0.80, so
    no Knight frame clears the threshold.
- **Rings:** 13 sizes were tried with (248, 40). From 21-24 x 9-12 outside / 11-14 x 3-5
  inside, all give 25-26 % of the Knight's frames and 1-2 cells. The measured one,
  (24, 10, 14, 4), is among the best and is kept.
- **Where it fires:** at 0.06, the aura alone sees 75 DEV positive frames. The aura's point lies a median 16 px from
  the Knight's foot, 89 % within 60 px and all within 120 px: it is the Knight's own aura.
- **Verdict.** The aura is real but WEAK on this map. Even as a strict rule it sees ~25 % of the
  Knight's frames and 2 of 8 DEV cells within 1.1 s (the Orc Lord's aura saw ~0.6 of its frames).
  The party window detector has to carry the recipe. The aura stays in it as an OR cue above
  every DEV negative.

### 5b. The frozen recipe (`mvp_profiles.STORMY`, commit 8b27a88e)

- **The aura:**
  - rim rule G >= 248, G - R >= 40, G - B >= 40 (judged at the 5-bit bin centres, as
    `aura_lut`);
  - ring (24, 10, 14, 4) half-res px, grid 3, centre 8 px above the foot;
  - threshold **0.06** = the DEV negatives' max 0.042 (cell 5's green floor, a watch gap frame)
    + 0.015 (Amendment B's margin over its DEV max), rounded up.
- **The party detector:** the Orc Lord's recipe, unchanged. That means the 11 cell features, the
  7 x 5 window, the hard-negative rounds (2), the body-LUT weights (hunting x 10, other species
  x 5), the margin + 1.0, SELF_ZONE and its own threshold, and the title-bar guard.
- The UI mask comes from the truths' layout (hunt) with the 2026-11-05 chat window.

### 5c. The fit (DEV only) and the frozen model

    W=<checkout at 8b27a88e>; T=/dev/shm/poring-lab-tmp/stormy   (OMP / OPENBLAS threads 1)
    systemd-run --user --scope -p MemoryMax=4G -p MemorySwapMax=0 nice -n 15 $python $W/scripts/mvp_watch_study.py fit --boss stormy \
        --watch /home/bot/poring-lab-rec/20261109T085010-rdp-sk-watch1 --watch-truth $T/watch-truth.json \
        --events /dev/shm/poring-lab-demo/20261109T085018-watch-xmas_dun02-sk1/events.jsonl \
        --pilot /home/bot/poring-lab-rec/20261109T082234-rdp-hunt-xmas02-p31 $T/hunt-truth.json \
        --work $T/fit --out $T/model/stormy-v1.npz

- **Run:** 2026-11-09 09:23:10-09:24:41 ICT (from `date`), 1 min 31 s, max RSS 1.7 GB.
- **The DEV items:** 325 positive, 70 watch-negative, 43 edge and 301 hunting frames. No Garm
  Baby frame was left out of the hunt (its DEV part has no party unit).
- **The party threshold:** **4.5493** = the DEV negatives' max outside SELF_ZONE (3.5493) + 1.0.
  Inside SELF_ZONE it is + `zone_penalty` 1.9063, so the zone threshold is 6.4556.
- **The aura:** 0.06 against a DEV max of 0.0417.
- **Colour pixels:** party 1,097,843; other species 372,167; background 22,497,972; hunting
  58,199,253.
- **THE MODEL:**
  - `/dev/shm/poring-lab-tmp/stormy/model/stormy-v1.npz`, 138,278 bytes;
  - profile `stormy`, version `stormy-v1`;
  - **sha256 `a1287571e26447b64f0a1b7620c49d90368510193e177e935c6bb0fbde8f8caf`**;
  - client-derived pixel statistics: never committed;
  - a copy, sha256 verified, is on the NAS: `scratch-archive/2026-11-09/b3-stormy-dev/model/`.
- **In-sample on DEV (optimistic, for reference; the same decide() on the DEV memmaps):**
  - 7 / 8 DEV cells were seen within 1.1 s of their first episode: six on its first frame,
    cell 7 at 0.97 s.
  - **Cell 1 was seen at 5.0 s.** The party spawned ON our Rogue: the Knight's box was at
    (589-689, 182-305), so its window's foot lies in SELF_ZONE. The party scores of 4.2 / 3.0
    clear the outside threshold (4.55) but not the zone's (6.46). This is the Orc Lord's
    SELF_ZONE trade-off (orclord-recognizer.md 4b), and the same miss mode can recur in a
    held-out cell.
  - Per frame: 293 / 325 positive frames, 282 / 304 of the Knight's.
  - No positive on the 80 watch-gap and 301 hunting DEV frames (by construction).
- **Nothing is refitted after the score.**

### 5d. The held-out score (the parent, ONCE)

Score with the frozen model's sha256, at a time outside the market-open windows: it reads
~1,650 full PNG frames from the root disk.

    W=/home/bot/docker/poring-lab; python=$W/.venv/bin/python; T=/dev/shm/poring-lab-tmp/stormy
    export PYTHONDONTWRITEBYTECODE=1 OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1
    export PYTHONPATH=$W/scripts:$W/packages/poring_env/src:$W/packages/poring_dataset/src:$W/packages/poring_packets/src
    sha256sum $T/model/stormy-v1.npz      # a1287571e26447b64f0a1b7620c49d90368510193e177e935c6bb0fbde8f8caf
    systemd-run --user --scope -p MemoryMax=4G -p MemorySwapMax=0 nice -n 15 $python $W/scripts/mvp_watch_study.py score --boss stormy \
        --model $T/model/stormy-v1.npz --sha256 a1287571e26447b64f0a1b7620c49d90368510193e177e935c6bb0fbde8f8caf \
        --watch /home/bot/poring-lab-rec/20261109T085010-rdp-sk-watch1 --watch-truth $T/watch-truth.json \
        --events /dev/shm/poring-lab-demo/20261109T085018-watch-xmas_dun02-sk1/events.jsonl \
        --pilot /home/bot/poring-lab-rec/20261109T082234-rdp-hunt-xmas02-p31 $T/hunt-truth.json \
        --out $T/score-heldout.json

- `score --boss stormy` scores watch cells 8-15 (section 3) and the hunt after its first 300 s.
  It decides each FULL frame with the model's own recipe, so it is independent of the code's
  profile values.
- Bars (section 3): recall within 1.1 s on 8 / 8 held-out cells; <= 1 false positive per 10 min
  of the hunt's held-out frames; latency p95 <= 60 ms.
- Any lone Garm Baby frames in the held-out hunt are reported in `hunting[0].lone` (the caveat).

## 6. RESULT: the held-out score, run ONCE (2026-11-09 09:52:07-09:54:16 ICT; the parent; model sha256 a1287571e26447b6..., verified before the run)

Command: section 5's (B3 part 1) exact line; out `/dev/shm/poring-lab-tmp/stormy/score-heldout.json`
(archived with the evidence).

| bar | measured | rule | |
|---|---|---|---|
| 1. recall within 1 s (held-out cells 8-15) | **8 / 8 (1.0)**; first-frame recall 1.0; re-entries 3, 1 within 1 s, 0 never | >= 95 % | **PASS** |
| 2. false positives, the hunting recording's held-out frames | **186 of 1,139 frames = 98.0 per 10 min** | <= 1 per 10 min | **FAIL** |
| 3. latency p95 | **28.6 ms** (p50 26.4, max 37.6; 1,712 calls) | <= 60 ms | **PASS** |

- Reported, not gating: the watch's held-out gap frames (after `@killmonster2`, before the next
  spawn) fired 29 of 200 (87 per 10 min); positive frames seen 277 of 319 (the Knight's 266 of 290).
- **VERDICT: NOT ADOPTED (bar 2).** Nothing is refitted on HELD-OUT (section 3); Amendment K's
  schedule stays the protection.

**POST-HOC (after the score; deciding nothing):** two held-out hunting false positives looked at.
- Frame 500 (and its run 498-507, party scores ~70, aura ~0.4): a PALE-GREEN PUZZLE FLOOR with dice
  decoration (the map's north-west rooms): the aura rule fires on the floor and the party detector
  on the decor. DEV's hunting minutes (the first 300 s) never crossed that floor; the explore mode
  (rogue-xmas02.md 4AL) now walks the whole map, so the negatives must too.
- Frame 368 (party score 4.6, just over 4.55): a red ground-skill circle around the Rogue.

**What would fix it (a second round, pre-registered on its own):** hunting negatives from the WHOLE
map (several explore runs recorded with `--format png`, every region crossed), the aura rule
dropped or bound to the party detector (it fires on this map's floors), a new watch for new
held-out cells, and the DEV negatives drawn from every floor type before the threshold is set.

## 7. PRE-REGISTERED: round 2 (2026-11-09 ~13:1x ICT, Batt "go on with the boss-summoning work"; BEFORE any round-2 data)

Round 1 failed bar 2 on floors its DEV data never crossed (section 6 post-hoc). Round 2 changes the
DATA, and lets DEV decide the cues again; the bars are round 1's.
- **New data:**
  - R2-H1, R2-H2: two 1-fps PNG hunting recordings beside explore pilots on the base (`--explore`
    walks the whole map), the MVP dead by the schedule; R2-H1 first.
  - R2-W: a second immune watch, 16 cells drawn from the TEST lattice (`lattice-test.json`, cells
    round 1 never used), `--spawn 1251`, 40-s dwells, PNG.
- **The split:**
  - DEV = round 1's watch (all 16 cells) + round 1's hunting recording (all of it; scored once,
    so no longer held out) + R2-H1 (all of it).
  - HELD-OUT = R2-W (all 16 cells) + R2-H2 (all of it), scored ONCE with the frozen model.
- **What DEV may change:** the aura rule (dropped, or ANDed with the party detector, or a tighter
  colour), the party detector's training negatives (every floor type in DEV), its threshold (the
  DEV negatives' max + margin, as Amendment B). Nothing is tuned on held-out data.
- **The bars (round 1's, section 3):** recall within 1.1 s >= 95 % of R2-W's cells; false positives
  <= 1 per 10 min on R2-H2; latency p95 <= 60 ms. Reported: lone Garm Baby positives.
- **After a pass:** the flee rule (seen -> Fly Wing at once) and its live proof are pre-registered
  on their own; until that proof passes the kill-before-run schedule stays.

## 8. Round 2: the data (recorded BEFORE any round-2 fit; nothing below was scored)

- **R2-W (HELD-OUT):** `stage_items.py watch --map xmas_dun02 --lattice lattice-test.json --seed
  2511 --max-cells 16 --max-minutes 24 --dwell-s 40 --spawn 1251 --label sk2 --immune-confirmed`
  (immunity judged ON on the Chat tab at 13:08: "You are now immune to attacks."; the test lattice
  sha256 98d3f0d4ec3b1574..., 88 stands, none used by round 1). Session
  `20261109T131033-watch-xmas_dun02-sk2`, 13:10:33-13:25:27 ICT: 16 cells, 16 spawns, 16 dwells,
  16 `@killmonster2`, reason "done". Cells in order: 50,223 192,49 93,248 118,72 203,170 214,248
  104,59 60,49 93,104 104,192 182,49 137,16 192,27 170,225 194,170 115,60.
  Its recording `20261109T131023-rdp-sk-watch2`: PNG, recorder v7, 918 frames, 1.97 GB, stopped by
  SIGTERM at 13:25:4x after the watch's end (stop "stopped by signal").
- The natural MVP: `@mobsearch` at 13:26:25 said "1[dead]" (its window from the 12:19:14 kill runs
  to 13:29:14; the watch's `@killmonster2` would have killed a natural spawn too).
- **R2-H1 (DEV):** `record_session.py --backend rdp --label hunt-xmas02-p38 --seconds 1620 --fps 1
  --format png --max-bytes 6G`, session `20261109T133046-rdp-hunt-xmas02-p38`, beside pilot p38
  (rogue-xmas02.md 4AS: the explore base + `--kill-gap`), from 13:30:46 ICT; the MVP dead by the
  schedule (killed by the watch's `@killmonster2` at 13:19:49 at the earliest, so no respawn before
  14:19:49).
- Both stay local until the fit / the held-out score are done, then ship (`dataset_ship.py`).
- **R2-H1 done:** stop "duration" at 13:57:4x ICT, PNG, recorder v7, 1,620 frames (1,548 on
  xmas_dun02), 3.51 GB, 14 shards, unchanged_skipped 0. Its truth (13:58:07-13:58:20, round 1's
  command, main a2181a74, `/dev/shm/poring-lab-tmp/stormy/r2h1-truth.json`): no Knight or Goblin
  on screen; Garm Baby in view on 32 frames in 3 episodes (its own spawn: the lone caveat).
- **R2-H2 (HELD-OUT):** `record_session.py --backend rdp --label hunt-xmas02-p39 --seconds 1620
  --fps 1 --format png --max-bytes 6G`, session `20261109T143541-rdp-hunt-xmas02-p39`, beside pilot
  p39 (rogue-xmas02.md 4AT: the base + `--kill-gap --loot-first`), 14:35:41-15:02:4x ICT, stop
  "duration", 1,620 frames, 3.52 GB; the MVP killed 14:34:50 (alive at 65, 60 at 14:34:36). Not
  opened since.

## 9. Round 2 DEV recipe -- written before the fit (2026-11-09 13:5x ICT; no round-2 fit run yet, no held-out frame read)

**The code** (commit 388700b0, tested on synthetic fixtures only):
- `mvp_watch_study.py fit / score / dev --round 2`: the whole watch (every cell, and the frames
  before the first spawn) and every whole hunting session are DEV for `fit` / `dev`, HELD-OUT for
  `score`. `--round 1` (the default) keeps round 1's split and command lines.
- `fit --aura or|and|off` is recorded in the model (`aura_mode`), so decide() and `score` follow
  the model. `--aura-margin M`: the aura threshold = the DEV negatives' max + M, rounded up to
  0.01 (round 1's recipe, done by hand in 5b).
- `dev`: decides exactly the frames `fit` takes, from the fit's half-res memmaps (the same
  decision as on the full frame). It gives the in-sample and leave-one-out numbers below.
- The model's version names its round: `stormy-v2`. `score --round 2` refuses a round-1 model.

**DEV (section 7):** round 1's watch sk1 (all 16 cells), p31 (all 1,440 frames), R2-H1 (p38, all
of it, once its manifest shows a stop reason). The two round-1 truths are used as they are.
R2-H1's truth is made with round 1's command (`truth --boss stormy --layout hunt`).
**Never read:** R2-W (sk2) and R2-H2.

**A regression check first:** round 1's fit command (5c) is re-run with the new code. It must give
round 1's model bit for bit (sha256 a1287571...). It reads only round-1 DEV frames.

**The inner check: leave one hunting session out (LOO).** Two folds:
- fold A: fit on the watch + p31, measured on R2-H1;
- fold B: fit on the watch + R2-H1, measured on p31.

Each fold sets its own thresholds from its own training negatives (the party: max + LIN_MARGIN
1.0; the aura, where used: max + 0.015, rounded up to 0.01). `dev` measures each fold on the watch
and both hunting sessions:
- **LOO false-positive rate** = false positives / frames x 600 on the left-out session's negatives
  (hunt_negatives: lone Garm Baby frames are reported apart, never counted). The criterion is the
  mean of the two folds' rates.
- **Watch cells seen within 1.1 s (in-sample):** each fold's first-episode delays on the 16 cells.

**The candidates.** All keep round 1's party detector recipe (5b) and its aura colour rule
(248, 40) with ring (24, 10, 14, 4); the aura's share is also one of the detector's features.
- (a) `--aura off`: the party detector alone.
- (b) `--aura or --aura-margin 0.015`: round 1's OR, the threshold from DEV.
- (c) `--aura and --aura-and 0.5 --aura-margin 0.015`: the aura counts only when the frame's best
  party window also reaches half the party threshold.
- (d) Only if (b)'s mean LOO rate is above (a)'s (the aura adds false positives out of sample):
  (b) with round 1's tightest colour, `--aura-rule 248 56 --ring 21 10 11 4` (5a, last row). The
  colour also changes the detector's aura feature, so (d) is its own fit.
- (a), (b) and (c) train the SAME party detector in a fold (the aura mode and threshold do not
  enter the training). So in a fold their false positives nest, (a) <= (c) <= (b), and so do
  their cells.

**The choice:**
1. A candidate QUALIFIES when BOTH folds see >= 15 of 16 watch cells within 1.1 s (in-sample).
2. Among those, the lowest mean LOO rate wins. Rates within 0.2 per 10 min of the lowest (under
   half a false positive per ~25-min fold) are a tie, and a tie goes to the simpler one, in the
   order (a), (b), (c), (d).
3. If none qualifies: the one with the most cells (the worse fold), then the lowest mean rate. This
   is reported to the parent as a failed DEV filter before any held-out score.

**The final model:** the chosen recipe fitted on ALL DEV (`--pilot` p31, `--extra` R2-H1, the whole
watch), its thresholds from all DEV negatives (party max + 1.0; aura max + 0.015 rounded up, where
used). It is saved as `stormy-v2.npz`, and its sha256 is recorded here before any held-out score.
Its DEV numbers come from `dev` and are labelled in-sample.

**Caveats, written now:**
- Bar 1 on 16 held-out cells: ">= 95 %" means 16 / 16 (15 / 16 is 93.75 %). The DEV filter
  (>= 15 / 16 in-sample) is looser than the bar.
- In round 1, cell 1 was seen only at 5.0 s in-sample: the party spawned on the Rogue, inside
  SELF_ZONE. Every candidate shares that miss mode.
- Each LOO rate rests on one ~25-min session: one false positive is ~0.4 per 10 min.
- How it runs: the memmaps are decoded once by `dev` without a model, in their own memory scope
  (a tmpfs page counts against the scope that writes it), under `/dev/shm/poring-lab-tmp/stormy-r2/`,
  in parts of <= 1,000 frames (<= 0.69 GB each). Each fit runs alone (`systemd-run --user --scope
  -p MemoryMax=4G -p MemorySwapMax=0 nice -n 19`, one thread), beside the live pilot.
- Nothing is tuned on held-out data. Nothing is refitted after the held-out score.

## 10. Round 2: the frozen model (2026-11-09 13:52-15:09 ICT; DEV ONLY, written BEFORE any held-out score)

**The DEV filter FAILED (section 9, step 3).** No candidate kept >= 15 of 16 watch cells within
1.1 s in both folds; the best fold saw 5. The fallback (the most cells in the worse fold, then the
lowest mean rate; all three tied) is (a), aura off. Its all-DEV model, stormy-v2, sees 8 of 16 cells
within 1.1 s even IN-SAMPLE. This is reported to the parent before any held-out score.

**What was read:** only DEV: round 1's watch sk1 (all 1,021 on-map frames), p31 (1,440) and R2-H1
(1,548 on the map: 1,511 negatives, 37 lone Garm Baby frames reported apart). They were decoded
once (13:58:29-14:02:28, `dev` without a model, its own scope) into half-res memmaps under
`/dev/shm/poring-lab-tmp/stormy-r2/work` (7 parts, 2.6 GB, each <= 0.69 GB). Every number below
reads only those. R2-W and R2-H2 were not opened, listed, decoded or summarised.

### 10a. The regression check (round 1 reproduced)

Round 1's fit command (5c), re-run at 13:52:35-13:54:54 with commit 388700b0, gave
`a1287571e26447b64f0a1b7620c49d90368510193e177e935c6bb0fbde8f8caf`: round 1's model bit for bit
(the same 325 / 70 / 43 / 301 items, lin_thr 4.5493, zone_penalty 1.9063; 2 min 19 s, max RSS
1.5 GB).

### 10b. The leave-one-out table (section 9; DEV only)

Fold A fits the watch + p31 and leaves R2-H1 out. Fold B fits the watch + R2-H1 and leaves p31
out. Cells and "in" are IN-SAMPLE; "LOO" is the left-out session.

| cand | fold | cells within 1.1 s (in-sample) | on the 1st frame | LOO false positives | LOO / 10 min | in-fit hunt FP | watch-gap FP | party thr | aura thr | lone episodes seen |
|---|---|---|---|---|---|---|---|---|---|---|
| (a) off | A | 5 / 16 | 5 | 0 / 1,511 | 0.00 | 0 / 1,440 | 0 / 280 | 6.8316 | (unused) | 0 / 3 |
| (a) off | B | 4 / 16 | 4 | 56 / 1,440 | 23.33 | 0 / 1,511 | 0 / 280 | 11.9270 | (unused) | 0 / 3 |
| (b) or | A | 5 / 16 | 5 | 0 / 1,511 | 0.00 | 0 / 1,440 | 0 / 280 | 6.8316 | 0.46 | 0 / 3 |
| (b) or | B | 4 / 16 | 4 | 56 / 1,440 | 23.33 | 0 / 1,511 | 0 / 280 | 11.9270 | 0.12 | 0 / 3 |
| (c) and | A | 5 / 16 | 5 | 0 / 1,511 | 0.00 | 0 / 1,440 | 0 / 280 | 6.8316 | 0.46 (AND 3.4158) | 0 / 3 |
| (c) and | B | 4 / 16 | 4 | 56 / 1,440 | 23.33 | 0 / 1,511 | 0 / 280 | 11.9270 | 0.12 (AND 5.9635) | 0 / 3 |

- Mean LOO rate: 11.67 per 10 min for (a), (b) and (c); the worse fold's cells: 4 for each. None
  qualifies. (d) was not run: (b)'s mean rate is not above (a)'s (section 9).
- As section 9 expected, (a), (b) and (c) trained the same detector in each fold (the same
  lin_thr). The aura added nothing:
  - fold A's aura threshold is 0.46, because p31's puzzle floor reaches 0.4375;
  - fold B's is 0.12 (R2-H1's max 0.1024), and no positive frame reaches it;
  - every p31 frame above 0.12 was already a party false positive.
- Fold B's 56 false positives are p31 frames 498-517 and 774-776 (party scores 63-76): the
  pale-green puzzle room of section 6's post-hoc. R2-H1 did not cross it: its negatives never
  score above 10.93 in fold B.
- Per positive frame, in-sample: fold A 226 / 644, fold B 195 / 644 (round 1: 293 / 325).
- Each fit: 6.0-6.3 min, max RSS 3.4-3.5 GB (that RSS counts the shared memmap pages; the fit's
  own scope was charged 1.33 GB, peak 1.67 GB, sampled in fold A-a). Each `dev`: 2.1 min.
- Fold models' sha256 (DEV evidence, archived): A-a 333b4875..., A-b aa164f36..., A-c 37999082...,
  B-a b98afd29..., B-b ea2add2e..., B-c 78156d85....

### 10c. The frozen model (the fallback recipe (a) on ALL DEV)

    W=<checkout at 388700b0 or later>; python=/home/bot/docker/poring-lab/.venv/bin/python
    T=/dev/shm/poring-lab-tmp/stormy; R=/dev/shm/poring-lab-tmp/stormy-r2   (OMP / OPENBLAS threads 1)
    systemd-run --user --scope -p MemoryMax=4G -p MemorySwapMax=0 nice -n 19 $python $W/scripts/mvp_watch_study.py fit \
        --boss stormy --round 2 --watch /home/bot/poring-lab-rec/20261109T085010-rdp-sk-watch1 \
        --watch-truth $T/watch-truth.json --events /dev/shm/poring-lab-demo/20261109T085018-watch-xmas_dun02-sk1/events.jsonl \
        --pilot /home/bot/poring-lab-rec/20261109T082234-rdp-hunt-xmas02-p31 $T/hunt-truth.json \
        --extra /home/bot/poring-lab-rec/20261109T133046-rdp-hunt-xmas02-p38 $T/r2h1-truth.json \
        --work $R/work --out $T/model/stormy-v2.npz --aura off

- **Run:** 2026-11-09 14:52:39-15:03:04 ICT (from `date`), 10 min 25 s. Max RSS 5.5 GB, which
  counts the 2.6 GB of shared memmap pages; the fit's own scope was charged 2.42 GB at
  14:55:4x, and it ran under MemoryMax=4G without an OOM.
- **The DEV items:** 644 positive, 268 watch-negative, 97 edge and 2,948 hunting frames (p31 1,439,
  R2-H1 1,509). The title-bar guard dropped 3 hunting and 12 watch frames (loading screens). R2-H1's 37 lone Garm Baby frames
  were left out of the negatives. Training windows: 19,731 positive, 521,040 random negative, and
  63,829 + 62,624 hard negatives.
- **The thresholds:**
  - party **6.4700** = the DEV negatives' max outside SELF_ZONE (5.4700, p31 frame 1151) + 1.0;
  - zone_penalty 0.0 (the zone's max + 1.0 is 6.2268, under the party threshold);
  - the aura is OFF as a cue (aura_mode `off`). Its colour rule (248, 40) and ring (24, 10, 14, 4)
    stay one of the detector's features. The stored aura_thr 0.06 is unused; the DEV negatives'
    aura max was 0.4375.
- **THE MODEL:**
  - `/dev/shm/poring-lab-tmp/stormy/model/stormy-v2.npz`, 138,540 bytes;
  - profile `stormy`, version `stormy-v2`, aura_mode `off`;
  - **sha256 `ee896970c8eccddf92e03d84070d241980882cdaafafa19eb1722e0bf30fea02`**;
  - client-derived pixel statistics: never committed;
  - a copy, sha256 verified, is on the NAS: `scratch-archive/2026-11-09/b3-stormy-r2-dev/model/`.
- **In-sample on ALL DEV (optimistic; `dev`, 15:03:04-15:05:11):**
  - **8 / 16 watch cells within 1.1 s** (6 on the first frame; cells 6 and 12 at 1.0 s). The rest
    were seen late: cells 4, 5, 7 and 9 at ~5.0 s, cells 1, 3, 8 and 10 at 11.0-12.0 s.
  - Per frame: 268 / 644 positive frames (all of them the Knight's frames: 268 / 594).
  - 0 false positives on the 1,440 + 1,511 hunting and 280 watch-gap DEV frames (by construction).
  - Lone Garm Baby: 0 of R2-H1's 3 episodes seen (no Fly Wing on a lone summon).
- **Nothing is refitted after a held-out score.**

### 10d. The held-out score (the parent, ONCE, if it is run at all: see 10e)

Run it at a time outside the market-open windows: it reads ~2,500 full PNG frames from the root disk.
Both truths are made first, as round 1's (truth.sh), with the layout the frames show (round 1's
watch: hunt).

    W=<checkout at 388700b0 or later>; python=$W/.venv/bin/python; T=/dev/shm/poring-lab-tmp/stormy
    export PYTHONDONTWRITEBYTECODE=1 OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1
    export PYTHONPATH=$W/scripts:$W/packages/poring_env/src:$W/packages/poring_dataset/src:$W/packages/poring_packets/src
    CAP="systemd-run --user --scope -p MemoryMax=4G -p MemorySwapMax=0 nice -n 15"
    KB="--kb /home/bot/docker/poring-lab/data/kb --mapcache-dir /home/bot/docker/poring-lab/packages/poring_dataset/src/poring_dataset/_generated"
    R2W=/home/bot/poring-lab-rec/20261109T131023-rdp-sk-watch2
    R2WEV=/dev/shm/poring-lab-demo/20261109T131033-watch-xmas_dun02-sk2/events.jsonl
    # 1. the truths (R2-W now; R2-H2 once recorded, its manifest showing a stop reason)
    $CAP $python $W/scripts/mvp_watch_study.py truth --boss stormy $R2W --layout hunt $KB --out $T/r2w-truth.json
    $CAP $python $W/scripts/mvp_watch_study.py truth --boss stormy <R2-H2 SESSION> --layout hunt $KB --out <R2-H2 TRUTH>
    # 2. the frozen model
    sha256sum $T/model/stormy-v2.npz      # ee896970c8eccddf92e03d84070d241980882cdaafafa19eb1722e0bf30fea02
    # 3. HELD-OUT, once: R2-W's 16 cells (the whole watch) and R2-H2 (all of it)
    $CAP $python $W/scripts/mvp_watch_study.py score --boss stormy --round 2 \
        --model $T/model/stormy-v2.npz --sha256 ee896970c8eccddf92e03d84070d241980882cdaafafa19eb1722e0bf30fea02 \
        --watch $R2W --watch-truth $T/r2w-truth.json --events $R2WEV \
        --pilot <R2-H2 SESSION> <R2-H2 TRUTH> --out $T/score-r2-heldout.json

- `score --round 2` scores every on-map frame of R2-W (its 16 cells; the frames before the first
  spawn and after the last kill count as gap frames, reported only) and every on-map frame of R2-H2.
  It decides each FULL frame with the model's own recipe (aura off), whatever the code's profile
  says, and refuses a model that is not a round-2 one.
- Bars (section 7): recall within 1.1 s on >= 95 % of R2-W's cells (16 / 16); <= 1 false positive
  per 10 min on R2-H2 (`hunting[0]`); latency p95 <= 60 ms. R2-H2's lone Garm Baby frames are in
  `hunting[0].lone`.

### 10e. What the DEV data says (POST-HOC on DEV, deciding nothing)

`posthoc_sweep.py` (archived) ran each fold's party detector (A-a, B-a) on every DEV frame and swept
its threshold.

| threshold | fold A cells (in-sample) | fold A LOO FP on R2-H1 (/ 10 min) | fold B cells (in-sample) | fold B LOO FP on p31 (/ 10 min) |
|---|---|---|---|---|
| 3.0 | 16 / 16 | 52 (20.6) | 16 / 16 | 116 (48.3) |
| 4.0 | 15 / 16 | 11 (4.4) | 15 / 16 | 85 (35.4) |
| 4.5 | 15 / 16 | 5 (2.0) | 15 / 16 | 80 (33.3) |
| 5.0 | 14 / 16 | 0 (0.0) | 14 / 16 | 75 (31.3) |
| 6.0 | 10 / 16 | 0 | 13 / 16 | 67 (27.9) |
| the fold's own (6.83 / 11.93) | 5 / 16 | 0 | 4 / 16 | 56 (23.3) |

- **The threshold rule costs the recall.** "DEV negatives' max + 1.0" was set on 371 negatives in
  round 1. Over ~1,700-3,000 whole-session negatives the max climbs, while the median positive
  frame's party score in-sample is only 6.1 (fold A). With the puzzle room in its training (fold A), a threshold
  near 4.5-5.0 would have held 14-15 cells at 0-2 false positives per 10 min on the left-out
  session.
- **One session per floor is not enough.** Without the puzzle room in training (fold B), the room
  scores up to 75.9, and no threshold works. Only p31 crossed it, so a leave-one-session-out check
  can never see it in both folds.
- **The aura** is no help on this map: the Knight's own aura never reaches a threshold above the
  floors.
- What could fix it (a round 3, pre-registered on its own, before any of its data):
  - more DEV hunting sessions, so that every room (the puzzle room above all) is in >= 2 of them;
  - a threshold rule chosen on the leave-one-out check, not "max + 1.0";
  - a persistence rule (seen on 2 frames in a row). Today it would cost 1 s of the 1.1-s budget.
- **R2-W and R2-H2 are still unread.** Scoring stormy-v2 on them would most likely fail bar 1 (it
  sees 8 / 16 cells even in-sample) and would use up the only fresh held-out watch. Whether to score
  it, or to keep them for a round-3 recipe, is the parent's / Batt's decision.

**The evidence** (client-derived, never committed) is on the NAS:
`scratch-archive/2026-11-09/b3-stormy-r2-dev/` (the chain's scripts, logs, every fold's fit and
`dev` report, the LOO table, the post-hoc sweep, the fold models and a copy of stormy-v2;
`files.sha256` verified). The DEV memmaps are deleted. `r2h1-truth.json` and the model stay in
`/dev/shm/poring-lab-tmp/stormy/` for the parent.

## 11. The parent's decision: round 2 stops at DEV; the held-out data stays unread (2026-11-09 15:4x ICT)

- **NOT SCORED.** The DEV filter (section 9) failed, and stormy-v2 sees 8 / 16 watch cells even
  in-sample (bar 1 needs 16 / 16 held-out). Scoring it would use up R2-W and R2-H2 -- the only
  fresh held-out watch and hunt -- on a model that cannot pass. They stay unread, for a round 3
  pre-registered first along 10e's lines (every room in >= 2 DEV sessions, a leave-one-out
  threshold rule, perhaps a persistence rule). Batt may decide otherwise; the command is in 10d.
- The code is merged (c764ef5f; round 1's model reproduces bit for bit). The flee rule does not
  exist; **the kill-before-run schedule (rogue-xmas02.md Amendment K) stays the only protection.**
- Local data kept until a decision: R2-W (`20261109T131023-rdp-sk-watch2`, 1.97 GB), R2-H1
  (3.51 GB), R2-H2 (3.52 GB), round 1's watch and hunt (2.22 + 3.18 GB) in ~/poring-lab-rec; they
  ship to the NAS after 17:00 (`dataset_ship.py`), unread.

## 12. RESULT: round 2's held-out score, run ONCE (Batt 2026-11-09 ~19:4x: "ทดสอบได้เลย" -- score it now; the parent, 19:41-19:46 ICT; model sha256 ee896970c8eccddf..., verified before the run)

Section 11's hold was lifted by Batt. The truths were made first (round 1's command, `--layout hunt`,
the recordings read from the NAS since they shipped at 17:11: R2-W 19:41:13-19:41:51, R2-H2
19:41:51-19:42:34), then 10d's score line once (out `/dev/shm/poring-lab-tmp/stormy/score-r2-heldout.json`).

| bar | measured | rule | |
|---|---|---|---|
| 1. recall within 1.1 s (R2-W, all 16 cells) | **5 / 16 (31.3 %)**; first-frame 25 %; re-entries 2 (1 within, 1 never) | >= 95 % (16 / 16) | **FAIL** |
| 2. false positives, R2-H2 (all of it) | **1 frame = 0.39 per 10 min** (1,549 frames decided, 2 without a game view) | <= 1 per 10 min | **PASS** |
| 3. latency p95 | **33.7 ms** (p50 28.1, max 39.9; 2,452 calls) | <= 60 ms | **PASS** |

- Reported: positive frames seen 315 of 596 (the Knight's 315 of 573); the watch's gap frames 0 of
  202 false; R2-H2 had no lone Garm Baby on screen.
- **VERDICT: NOT ADOPTED (bar 1).** Round 2's data fixed round 1's failure (false alarms 98 -> 0.39
  per 10 min) but the threshold it needed ("max + 1.0" over whole-session negatives) costs the
  recall, as 10e predicted from DEV. **The kill-before-run schedule (rogue-xmas02.md Amendment K)
  stays the only boss protection.**
- R2-W and R2-H2 are now spent as held-out data; a round 3 needs fresh held-out recordings (10e's
  recipe: every room in >= 2 DEV sessions, a leave-one-out threshold, perhaps persistence).
