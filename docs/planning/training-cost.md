---
doc_type: design
hypothesis: "At a fixed per-species data budget, the detector preparation for a new map scales linearly with its species count, and the constants below predict it within the contingency."
status: ACTIVE (constants ESTIMATED; first measurement due on the first species addition after v1)
role: null
verdict_date: null
verdict_ticket: null
supersedes: null
related: [../benchmarks/v1-vs-v0png.md, ../operations/r3-paired.md, ../phase3-plan.md, ../adr/0020-block-programming-flows.md]
next_action: "On the first species addition after v1: measure collect and fine-tune per species, update the constants, and add a row to the history table. Re-measure availability after mid-epoch checkpoints land."
---

# Training cost per monster species: the planning formula (Batt, 2026-10-08)

Batt (2026-10-08): make "training time per monster species" a real, measured constant, so a new
workflow map can be estimated up front.
- Standardise a DATA BUDGET per species, so training time scales linearly with the number of
  species.
- Report compute hours and wall-clock hours separately.
- Start from what v0 measured, mark the constants as estimates, and measure them on the first
  species addition after v1. Then update them after every addition (the history table below).

## 1. The formula

    new map time = map prep + Σ_species d_s × (collect + train) × contingency

| term | unit | what it covers | competes with |
|---|---|---|---|
| **map prep** | operator/agent hours | GAT + camera + walkability check; sprite-catalog entries for the new species (decoded at run time, never committed); a v1 label check per species on a small hand-checked sample; ~300 background frames of the map | nothing (overlaps training) |
| **collect** (per species) | S2 hours | recording the species at 1 frame/s in the clean room; spawn setup; cache build; label QA | **training** (S2 runs only with training paused) and the RDP walk runs (one Windows session) |
| **train** (per species) | **compute hours** | GPU time with no duty sleep and no pauses (§3) | other GPU work (R2: one model at a time) |
| **d_s** | multiplier | the species' difficulty (§4) | |
| **contingency** | multiplier | re-collects, failed evals, aborts | |

- **Wall-clock = compute / availability** (§3), plus the collect hours, which run serially with
  training. Map prep overlaps.
- **The training strategy assumed:** incremental. Fine-tune from the latest weights on the new
  species' budget plus an equal replay sample of the species already known, for half the epochs.
  - That costs the same compute as B × E × k (2B frames × E/2 epochs), and it keeps the cost
    linear in NEW species.
  - A from-scratch retrain on every species instead costs (all frames) × E × k each time.
  - The assumption is measured on the first addition: forgetting of the old species, checked on
    their test sets.

## 2. The data budget per species (PROPOSED)

- **B = 1,500 training frames that contain the species**, with **≥ 3,000 instances**.
- Coverage counts, not just totals: **≥ 50 instances in every pose cell** (8 directions × the
  species' actions: idle, walk, attack, hit, die).
  - A species without walk or attack frames (a plant) has fewer cells: see d_s.
- Validation and test frames in v0's proportion (val : train = 3,242 : 8,193 = 0.40). The
  per-epoch validation cost is already folded into k.
- **Why 1,500:** v0 trained on 8,193 frames over ~6 monster groups (Batt's count), ≈ 1,365 per
  group. 1,500 rounds that up.
- Frames may hold several species. A frame counts toward the budget of every species in it, so
  mixed spawns shorten collection.

## 3. The constants (ESTIMATES until §6's first measurement)

**Machine-readable copy (ADR-0020 13.4, open question 26):** the workflow editor's estimator reads
these values from `packages/poring_flow/src/poring_flow/data/training_cost.json`, never from its own
code. Change this table and that file together: `packages/poring_flow/tests/test_prep.py` fails
when they disagree. The history stays in this document.

| constant | value | source |
|---|---|---|
| **k**, compute per training frame per epoch | **0.146 s** (c = 0.293 s per batch of 2) | **fitted**: v0-JPEG's 12 h night attempt (2026-10-07 17:09 → 10-08 05:09). 21.9 epochs × 4,097 batches over the logged duty levels, R3-paused 10.1 %. It includes each epoch's validation. Hardware: RTX 5060 Ti at `VISION_MAX_VRAM_FRACTION` 0.25, batch 2, workers 1, imgsz 1280, AMP |
| **E**, epochs | 30 | the v0 / v1 standard |
| **train per species** = B × E × k | **≈ 1.8 compute-h** | 1,500 × 30 × 0.146 s |
| **collect per species** | **≈ 1.0 h** (S2) | ESTIMATE. ~25 min of recording at 1 frame/s with the species on screen, + spawn setup, + clean-room start/stop, + cache build and label QA. v0's sessions were not recorded per species, so there is no measurement yet |
| **map prep** | **≈ 4 h** per map | ESTIMATE |
| **contingency** | 1.3 | ESTIMATE |
| **availability**, compute-h per wall-h | **night 0.63, day 0.43** (measured); **effective night 0.61, day 0.35** | `scripts/train_availability.py` on the 10-07/08 guard outputs: night 20:00–05:00, day 05:00–10:30 |

**Cross-check against v0:** 8,193 frames × 30 × 0.146 s ≈ **10.0 compute-h**, i.e. ~1.7 h per group.
Batt's "~15 h" is the RUNNING time at the fastest duty level: the same 10 h plus the 100 ms sleep
per batch (+34 %) and the R3 OFF windows (+11 %).

**Availability, two definitions** (both from the same logs):

| window | running, not R3-paused | compute availability | effective (minus discarded partial epochs) |
|---|---|---|---|
| night 20:00–05:00 | 0.90 | 0.63 | 0.61 |
| day 05:00–10:30 | 0.65 | 0.43 | 0.35 |

- Batt's "~0.9 night, ~0.5 day" is the first column.
- The formula uses **compute availability**, because compute is defined without the duty sleep.
  At the fastest level the sleep alone costs a quarter: c / (c + 0.1 s) = 0.75.
- **Effective** subtracts the partial epochs thrown away by stops (an epoch-level resume restarts
  the epoch). Today's day window lost 0.46 compute-h that way: the 12 h step timeout, an IO pause
  and two camera-drop aborts.
- **Mid-epoch checkpoints** (Batt's decision 2, 2026-10-08) are meant to close the effective gap.
- **Every restart also costs ~24 min of 50 % pairing.** The paired R3 baseline runs 3-min ON/OFF
  windows until it has 4 pairs. That is why the day's paused share (19 %) is nearly twice the
  night's.
- **How to re-measure:** `scripts/train_availability.py --c <c> --day <date> <guard outputs…>
  --window NAME=START..END [--lost START..END]`. c comes from the container's `duty_stats` lines
  (batches and seconds per level) less the sleep and the paused time.
  - The rundev log is overwritten per attempt. Keep a copy per attempt so c can be refitted.

## 4. Difficulty multipliers d_s (ESTIMATES)

| class | d_s | meaning |
|---|---|---|
| similar to a known species | 0.5 | a palette or size variant of a species already trained (half the budget) |
| static | 0.5 | no walk or attack poses (plants, eggs): fewer pose cells |
| normal | 1.0 | a new mobile species |
| large multi-form boss | 2.5 | many poses or forms, rare spawns, large sprites, effects |

## 5. Estimate now: the Byalan workflow map (iz_dun00 + iz_dun01)

**The species** come from the local KB (`data/kb/spawns.json`, generated from the pinned rAthena at
run time; never committed). The union of both maps has 7 species, none of them in v0's training
data:

| species | iz_dun00 / iz_dun01 spawns | ai | d_s | why |
|---|---|---|---|---|
| Plankton | 65 / 10 | 1 | 1.0 | normal |
| Marina | 45 / 15 | 1 | 1.0 | normal |
| Kukre | 15 / 50 | 2 | 1.0 | normal (fast, 150 ms/cell) |
| Hydra | 15 / 30 | 10 (immobile, aggressive) | 1.0 | immobile, but it has attack poses |
| Vadon | 15 / 60 | 17 | 1.0 | normal |
| Cornutus | – / 15 | 17 | 1.0 | normal |
| Black Mushroom | 5 / 10 | – (immobile) | 0.5 | static |

**Σ d_s = 6.5.** With contingency 1.3:

| part | hours | how |
|---|---|---|
| map prep | ≈ 5.2 h (operator/agent) | 4 h × 1.3, overlapping training |
| collect | ≈ **8.5 h of S2** (training paused) | 6.5 × 1.0 h × 1.3 |
| train | ≈ **15.5 compute-h** | 6.5 × 1.83 h × 1.3 |
| train, wall-clock | **≈ 25 h at night only** (0.63), **≈ 31 h around the clock** (a 9 h night + 15 h day mix, 0.50), ≈ 44 h at today's effective day rate (0.35) | compute / availability |
| eval | ≈ 1 h | the held-out session + the gold check, as for v0-JPEG |

- **Calendar:** about **3–4 days after v1's training ends**.
  - The GPU is v1's until then (R2).
  - S2 collection pauses training. If S2 stays after 17:00 on weekdays, as for M4, the 8.5 h is
    about two evenings.
- **Not in the estimate:**
  - the domain shift of a dungeon map (its own lighting and backgrounds; the ~300 background
    frames in prep are the first answer);
  - whether v1's provisional k holds for these sprites.
  - A zero-shot eval of the current detector on one Byalan recording would refine both, before
    any collection.
- **A from-scratch retrain instead:** (8,193 + 6.5 × 1,500) frames × 30 × 0.146 s ≈ 21.8 compute-h.

## 6. Measuring the constants (the first species addition after v1)
- **collect:** the clean-room clock per species (recording, setup, cache build, QA), and the
  frames and instances per pose cell actually reached.
- **train:** the fine-tune's compute-h from its `duty_stats` and pauses (c refitted), its wall-h,
  and its availability per window (`scripts/train_availability.py`).
- **quality:** the new species' mAP on its own test set, and the OLD species' test mAP before and
  after (forgetting).
- Then update §3 and add a row below. Every later addition adds a row.

## History of the constants

| date | event | frames (train) | groups / species | epochs | compute-h | wall-h | k (s / frame-epoch) | availability (night / day) | notes |
|---|---|---|---|---|---|---|---|---|---|
| 2026-10-08 | v0-JPEG matched batch (`v0jpg-20261007`) | 8,193 (+3,242 val) | ~6 groups (Batt) | 30 | ≈ 10.0 (fit) | ≈ 23 expected (2026-10-07 12:39 → ~10-08 11:30) | 0.146 (fit) | 0.63 / 0.43 (effective 0.61 / 0.35) | initial ESTIMATES. 9 stops: 1 paired-R3 latency trip, 2 IO, 5 camera-drop R3-HARD, 1 step timeout (12 h). Fill in the wall-h at TRAIN DONE |
