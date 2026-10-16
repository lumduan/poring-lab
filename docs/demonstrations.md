---
doc_type: design
hypothesis: "Rules distilled from outcome-verified demonstrations (login, walk-to-point, attack-target selection) succeed ALONE on new situations at >= 95 %, judged only by offline packet verifiers."
status: PRE-REGISTERED
role: null
verdict_date: null
verdict_ticket: null
supersedes: null
related: [phase3-plan.md, phase4-ui.md, adr/0007-packet-ground-truth-channel.md, adr/0011-ui-anchor-map.md, adr/0015-phase4-planner-linter-executor.md]
next_action: "➡️ 2026-10-10: a running log; the newest work is 3.32a npc-click@1 (probe arms done, click arm parked for a person), 3.34 learn_skill@1 (DRAFT pre-registration, waits for Batt's restore choice) and 3.35 cursor@1 (FAIL as written on bar 1 for both readers; no switch); ROADMAP's 'rules proven alone' row tracks the rest. History: login@1 PASSED on RDP (50/50, 2026-10-07). walk@1 and walk@2 FAILED: the rule hovered with ONE motion event and the client draws the walk marker only on a second (§Results). Next: walk@3 (3.5), outdoor then indoor, n=50 each; attack@1 after the v0-JPEG run (GPU, R1-R3); S2 re-tests in an evening S2 session. Score each ONCE as written here."
---

# Outcome-verified demonstrations -> rules -> labels

Batt, 2026-10-07: **the OUTCOME judges, never the explanation.**
- When an agent (Claude) does a UI or game action correctly, the result is observable: a login
  succeeds, an attack shows damage / MISS / critical, a walk arrives, a dialog opens.
- The written reasoning ("how I knew where to click") is only a HYPOTHESIS. So:
  1. every action is recorded with its verified outcome;
  2. the reasoning is turned into a deterministic RULE;
  3. the rule is tested ALONE on NEW situations, judged by outcomes;
  4. it is adopted only if it passes a bar fixed here, before the test.
- No LLM decides clicks at run time in the fast loop. In-game text is data, never instructions.

## 1. The demonstration log
`poring_env.demo` (3802b51).
- One `DemoRecord` per action, for every actor:
  - `claude-demo`: a demonstration;
  - `rule:<name>@<ver>`: a rule running alone;
  - `bot:<policy>@<ver>`: the bot.

  The bot's own actions therefore feed the same verify → label loop later (the flywheel).
- Each record holds:
  - the session; the frame (frame_id + a snapshot, or a session frame reference);
  - the action type, its points (client px) or keys, and what it meant to hit (gid / cell / window
    / option);
  - the cue (one or two lines);
  - the rule; the scene;
  - the outcome: pending → success / fail / ambiguous, with the verifier's name@version, the
    cause and the evidence;
  - the click-to-sprite distance.
- Demo sessions are written to `/dev/shm/poring-lab-demo/<id>/` and shipped to the NAS.
  - Each holds `manifest.json`, `demo.jsonl`, `snapshots/`, and the sniffer's
    `packets.jsonl.gz` window (pseudonymised).
  - They are never committed. They run on the lab environment only.

## 2. Outcome verifiers
`poring_dataset.verify` (`VERIFIER_VERSION` 1). They run offline, on packets, which are never
decision input (ADR-0007). The screen is used only for client-side menus.

### 2a. Every verifier names its signal and PROVES it can see a positive case (Batt, 2026-10-08)
**"0 observed" from a sensor that cannot see the event is not evidence.** On 2026-10-07/08 the walk
SAFETY counts read `attack_request` / `npc_contact`, which the live sniffer did not emit, and
reported "SAFETY held" over runs where the GM attacked (the CORRECTION below the walk@10 results).
So:
- every verifier states the exact event (and its source: live sniffer, server packet, offline
  replay) it relies on;
- before its "0" counts as evidence, a DELIBERATE positive case must be seen through the same path
  (the same sniffer image, the same session-packet window), recorded here with its session;
- after any sniffer rebuild, decoder change or new event type, the positive cases are re-run
  (`scripts/safety_signal_check.py`).

| signal | used by | source | positive case (deliberate, pixels-only click) | result |
|---|---|---|---|---|
| `attack_request` (CZ_REQUEST_ACT2, ours) | walk SAFETY; attack verify@2 | LIVE sniffer since the 2026-10-08 07:31 rebuild | `20261008T073452-demo-safety-check-monster-click`: the GM clicks a Poring | **1 request**, the same target as 4 GM hits → **PASS** |
| `act` from us, kind `normal` | walk SAFETY; attack verify | live (server ZC_NOTIFY_ACT) | the same session | **4 acts** on the Poring → **PASS** |
| `npc_contact` (CZ_CONTACTNPC, ours) | walk SAFETY | LIVE since 07:31 | `20261008T073847-demo-safety-check-npc-garnet`: the GM clicks Garnet#pront (TALK cursor, v3 references) | **1 contact** (gid 110000895), then `npc_say` ×3, `npc_wait`; the dialog was paged and CANCELLED by screenshot-checked clicks → **PASS** |
| `act` from us, kind `pickup` | walk SAFETY | live (server act) | `20261008T074118-demo-safety-check-pickup`: an `@item` Knife dropped, then clicked where the cursor read `pickup` | **1 pickup act** (the client walks in first: a `self_move_request`; the pickup REQUEST itself is not a decoded event) → **PASS** |

**Re-proven after the 17:51 sniffer rebuild** (the packet-table fix; §2a's rule: rebuild → re-run):

| signal | positive case (deliberate, pixels-only click) | result |
|---|---|---|
| `attack_request` + `act` from us (`normal`) | rec@0b's Red Plant attacks (`20261008T181138-demo-rec0b`, 3.22) | requests and hits seen live → **PASS** |
| `npc_contact` | `20261008T210752-demo-safety-check-npc-garnet` (21:08 ICT / 14:08 UTC): the GM clicks Garnet (TALK cursor twice); the dialog paged with Enter ×3 and its menu CANCELLED by a screenshot-checked click | **1 contact** (gid 110000895), then `npc_say` ×7, `npc_wait` ×3, `npc_menu`, `npc_choose`, `npc_close_click` → **PASS** |
| `pickup_request` (ours, NEW: decoded since the loot decoders) + `act` from us (`pickup`) | `20261008T210930-demo-safety-check-pickup` (21:10 ICT / 14:10 UTC): an `@item` Knife dropped by an inventory drag, then clicked where the cursor read `pickup` twice (cell 98,112) | `pickup_request` 1, `pickup_result` 1, `floor_item_vanish` 1, **1 pickup act** → **PASS** |

**Re-proven after the 2026-10-10 02:50 ICT sniffer rebuild** (the credential scrub `LoginScrub`,
f36276e; built from main 6b90746 in a measured quiet window, worst capture stall 6.5 %; recreate and
the GM's auto re-login OK at 02:51:57):

| signal | positive case | result |
|---|---|---|
| the scrub itself | `scripts/scrub_check.py --since <recreate>` over the 2 capture files since the recreate: the GM's user and password searched, FOUND / NOT FOUND only | user **NOT FOUND**, password **NOT FOUND**; controls: 1 `login_accepted` in the window, the character name FOUND → **PASS** (the sniffer logs "login ports [6900] + every login-shaped connection") |
| `attack_request` + `act` from us (`normal`) | `20261010T031437-demo-safety-check-monster-click --species red_plant` (a still monster: the v3 cursor reads SWORD on a bobbing Poring ~7 %, 3.35, and the Poring case ran past 10 min twice) | 1 request, 3 acts, the same target → **PASS** |
| `pickup_request` + `act` from us (`pickup`) | `20261010T031556-demo-safety-check-pickup` (an `@item` Knife dropped by an inventory drag, clicked where the cursor read pickup twice) | `pickup_request` 1, `pickup_result` 1, `floor_item_vanish` 1, 1 pickup act → **PASS** |
| `npc_contact` | `20261010T031924-demo-npc-click-click-prontera` (npc-click@1's prontera CLICK pilot re-run, unscored; `safety_signal_check.py npc-click` got no TALK read twice on Garnet or Henson, the v3 colour weakness of 3.30 / 3.35) | **4 contacts**, each declined (4 `npc_choose` cancels, 19 `npc_say`), 0 attack → **PASS** |

**Re-proven after the 2026-10-15 recreates** (Batt decision 7):
- rathena: `recreate:rathena@120` 13:42:57-13:45:09 ICT (group 20's resetstat / resetskill; groups.yml
  verified in the container). Worst capture stall 4.7 %.
- sniffer: `recreate:sniffer@30` 13:45:24-13:46:39 (ADR-0007 Amendment C: the decoder CODE from the
  host, `SNIFFER_COMMIT` 0b6fb16; the start-time self-test gates the start). Worst stall 6.2 %.
  guarded_build's auto GM re-login was OK, and the interlock was green at 13:46:39.

| signal | positive case | result |
|---|---|---|
| the scrub itself | `scrub_check.py --since` the sniffer recreate (1 capture file) | user **NOT FOUND**, password **NOT FOUND**; controls: character name FOUND, 1 `login_accepted` → **PASS** |
| `attack_request` + `act` from us (`normal`) | `20261015T134754-demo-safety-check-monster-click --species red_plant` | 1 request, the GM's acts on the same target (gid 110015745) → **PASS** |
| `pickup_request` + `act` from us (`pickup`) | attempt 1 `20261015T135025-demo-safety-check-pickup`: **no click**. The Knife landed 2 cells off (102,115) and EXPIRED after the server's 60 s floor-item lifetime, before the 24-cell scan (~2.3 s a cell, started ~19 s after the drop) reached it. Kept. Attempt 2 `20261015T135425-demo-safety-check-pickup`: drag, close and scan back to back | `pickup_request` 1, `pickup_result` 1, `act` pickup 1, `floor_item_vanish` → **PASS** |
| `npc_contact` | `20261015T135559-demo-safety-check-npc-garnet` with the v3 reader: no TALK read twice, **no click** (the 10-10 weakness). Kept. `20261015T135734-demo-safety-check-npc-garnet` with the LIVE gate's reader (robust2, `--reader`, new) | **1 contact** (gid 110000895); the dialog closed by talk@1's safe decline (NEXT, NEXT, the menu cancelled, CLOSE: `npc_choose` 1 = the cancel, `npc_close_click` 1) → **PASS** |

- Two instrument fixes, the same day: `pickup-collect` / `npc-collect` recorded a no-click attempt
  as a crash; it is now a FAIL kept with `why: no click`. And `npc-click --reader` (default
  robust2).

- `demo_verify.py` prints `safety.our_acts` / `unsafe_acts` per session and labels the request counts
  with the instrument's history (63873bc).
- ~~Still open: the banked-capture replay for the walk runs of 2026-10-07/08~~ ➡️ done 07:47–07:52
  (`guarded_build.py replay:`, its own positive controls first; results in the CORRECTION below the
  walk@10 results).
- **Session windows:** a session's `packets.jsonl.gz` reaches back to the last map change before it
  started, so a safety count over the whole file can borrow earlier events. Counts use the
  manifest window (`demo_verify` safety and `replay_safety.py`).

### 2c. walk@11's unit detector, proven on RDP frames (2026-10-08 08:42–08:50; design time)
- **The sensor:** v0-PNG exported to ONNX (1280×736), CPU, ~180 ms on 8 threads
  (docs/operations/detector-cpu.md).
- **The check:** `scripts/detector_check.py`, session `20261008T084236-demo-detector-check`, 80
  frames ~1 s apart, 6 Porings per scene + the church's NPCs, no clicks. Ground truth is the packet
  boxes (`qa_export.Labeler`, as `demo_verify`), inside the click band.

| scene : class | units | seen (feet ≤ 30 px) | seen (≤ 45 px: the envelope's own one-cell slack) |
|---|---|---|---|
| prt_fild08 : monster | 145 | 141 (97.2 %) | 142 (97.9 %) |
| prt_church : npc | 40 | 40 (100 %) | 40 (100 %) |
| prt_church : monster | 133 | 119 (89.5 %) | 129 (97.0 %) |

- Lower confidence (0.05–0.25) changes nothing indoors: the misses are not faint boxes.
- The 30-to-45 px difference is hopping Porings against a ground truth slightly off in time.
- **True misses: ~2–3 %.** Three of the four church ones are one Poring under the chandelier: an
  occluding scenery sprite.
- Unmatched detections: 2 (at 45 px).
- Detected feet sit a median 6.7 px above the true feet (p10 −12.5): the envelope's +1 step covers
  it.
- **So the envelope is the SECOND layer:** a click on a unit needs both the cursor gate (sword / talk
  / unknown = no click) and the envelope to miss it.

### 2b. Every HARNESS click passes the cursor gate (Batt, 2026-10-08)
- where@2's harness clicked blind and attacked field monsters (24 hits) and contacted NPCs.
- Every world click outside a rule now goes through `scripts/cursor_gate.gated_click`: park,
  two-motion hover, the walk@9 reader with the v3 references, a no-motion re-read, and a click
  only if both reads are allowed (`walk`; `warp` only for an intended portal).
- It fails closed: no references, or a path without them (S2 for now), means no click.
- Gated: where_run's harness click, the dataset activity driver, both camera calibration tools,
  and the delay benchmark.
- `test_click_census.py` pins every remaining direct `.click(` in `scripts/` with its reason (UI
  clicks; the rules' own gates; the deliberate positive cases).
- **Smoke (08:00, 2 attempts, not scored):** one candidate refused (`cursor_noentry`), the next
  clicked; in-window 0 requests, 0 GM acts.
- The gate checks the cursor, not the click instant. The NPC contacts above came through a WALK
  cursor, so the rule needs walk@11's click-instant layer as well.

| action | success | window (fixed) | fail / ambiguous |
|---|---|---|---|
| login | our `login_accepted` (aid) → `char_selected` → `map_enter`, in that order | 60 s from the attempt's first input | the first missing step names the cause |
| walk | the server accepts a walk whose DESTINATION is the target cell (`self_move`), and nothing moves us elsewhere before the walk's own duration + 1.5 s | the move request must come within 2 s | no request = not a walk; destination off by n cells; stopped short; re-routed → fail. Map change, or we vanish → ambiguous |
| attack | an `act` FROM our aid ON the intended gid. Damage, MISS, critical and lucky dodge all count: the right target was swung at | walk-in time + 2 s, capped at 8 s | our act on another gid = wrong target; our move REQUEST with no act = the click became a walk; nothing = ignored → fail. The target vanished first, only other attackers acted on it, or our act came late → ambiguous |
| ➡️ attack, **verify@2** (amended 2026-10-07 ~15:45, Batt, BEFORE attack@1 ran) | unchanged: our `act` on the intended gid in the window | the click's REQUEST is read too: `attack_request` = CZ_REQUEST_ACT2 0x0437 (0x0089 is a tick at PACKETVER 20211103), or `npc_contact` (CZ_CONTACTNPC 0x0090) on the gid, within 2 s | a request on another gid → "requested a different target"; the right request but no act → "requested the target, no act within the window"; a walk request → walk; no request → "no request at all (click ignored)". Ambiguous cases unchanged. Login / walk / menu are unchanged since verify@1 |
| menu shortcut | the window's anchor is absent before and present after | 1 s | already open → ambiguous |

- **The intended gid of an attack click** is resolved at verification:
  - the click is matched against `predict_sprite`'s boxes at that frame's time (the box
    containing it, else the nearest foot point);
  - the rule's own detection is never trusted;
  - the click's distance to that sprite is recorded.
- **Our aid** comes from `login_accepted`, else `infer_self_aid`, else the lab accounts
  (`config/environments.yaml`).
- **Later verifiers** (NPC talk/choice, shop, stat/skill): their decoders were built 2026-10-07,
  for offline replay only; the verifiers themselves are not built yet (§5).

## 3. Pre-registered alone-tests (written before any run)
Common rules:
- **The rule runs ALONE.** `scripts/rule_run.py` runs only the rule's code: no agent reasoning
  and no manual help. Every attempt is logged as `actor rule:<name>@<ver>`.
- **The harness is not the rule.** GM staging (`@warp`, `@killmonster2`, `@monster`, `@heal`,
  `@alive`) is logged as the harness's own records.
- **Situations are NEW:** seeded spots, cells and times never used in a demonstration.
- **The bar:** ≥ 95 % verified success, n ≥ 50 per scene where scenes apply.
  - Ambiguous attempts are reported, excluded from the denominator, and capped: if more than
    10 % are ambiguous, the test is INCONCLUSIVE and is re-run with the cause removed.
  - A failure is a finding: the missing cue is looked for. The bar is never loosened.
- **Reported:** attempts, verified successes, failures by cause, ambiguous by cause, and the time
  per attempt (p50 / p95).
- **The path:** RDP now (Batt, 2026-10-07). The S2 variant comes later, in an evening S2 session
  with training paused, scored against the same bar.
- **The actor:** the GM account (2000002).

### 3.1 login@1
- **The rule** (`ro_agent`, the login sequence):
  - launch from the desktop shortcut;
  - Select-Service: find the dialog by its anchor (the `service_select` signature at its fixed
    box), then click OK at its offset;
  - login dialog: anchor `login`. Click the id field, clear it, type the id (sensitive, the guard
    re-checked every 4 characters); the same for the password; click the login button (never
    Enter);
  - **server list: click OK at its offset 0.8 s after the login button**, the demonstrated
    fixed delay. The server list's own anchor is NOT waited for. Over RDP the list is first drawn
    at reduced quality, so its signature can lag by seconds, and the client gives up if no server
    is picked within ~1–2 s (2026-10-01: waiting 2–19 s failed 8/8).
    - Its anchor (`server_select`) is only recorded, on the pre-click snapshot.
    - A gated pick is a later candidate (login@2, on the S2 bus).

  > ➡️ **AMENDED 2026-10-07 ~12:20, BEFORE any run:** the first version (41d8c14) waited for the
  > server-list anchor (≤ 1.5 s). That would have tested a known RDP failure mode instead of the
  > demonstrated rule. The amendment makes login@1 exactly the demonstrated sequence, expressed
  > as anchors + offsets.
  - char select: anchor `char_select`, then Enter;
  - the existing guards stay: the ENG layout, the client in front, the operator login window.
  - So login@1 = `ro_agent login gm` as it stands, run alone by the runner.
- **An attempt:**
  - starts with no client running;
  - ends when the rule returns or stops;
  - between attempts, the harness closes the client (paced Alt+F4) and waits 5 s.
  - A Stop raised by a guard before any typing is a FAIL (cause `refused:<guard>`).
- **The verifier:** `verify_login`, aid 2000002.
- **n = 50.** Pass: ≥ 48/50 verified successes.
- **Never retry fast:** two consecutive verified login FAILURES stop the test (account lockout,
  CLAUDE.md rule 2), and it is reported as stopped.

### 3.2 walk@1, two scenes
- **The scenes:** outdoor prt_fild08, indoor prt_church.
- **Per attempt, the harness gives the rule a target OFFSET (dx, dy) in cells:**
  - drawn with seed 20261007;
  - |dx| in 2–6, |dy| in 2–4;
  - the cell is GAT-walkable;
  - its projected pixel lies inside the click band (40, 150)–(1240, 520), i.e. not under the
    windows.
- **The rule:**
  1. **Our own cell, from pixels.**
     - Outdoors: the minimap readout (`poring_env.selfpos`, T0's reader; its templates are
       restored from the T0 calibration).
     - Indoors there is no minimap. The projection uses a flat floor (the rotated indoor camera
       with zero relative altitude), stated as a known simplification.
     - If the readout fails, the attempt is a FAIL (`no_selfpos`).
  2. **The target pixel:** `camera.click_for_cell` with the RDP camera (`camera_rdp.json`) and the
     map's GAT.
  3. **The hover cue** (demonstrated): move the cursor there, wait 0.35 s, and require the walk
     marker (≥ 40 marker-green px in a 90×90 crop, `empty_cell`).
     - Without the marker, the rule declines: FAIL (`declined:no_marker`).
  4. **Click.** Our position at click time is never given to the rule.
- **The verifier:** `verify_walk`.
  - target = our cell at the click (from packets, offline) + (dx, dy);
  - our walk speed comes from the `speed` stat, else 150 ms per cell.
- **The harness, before each block of 10:**
  - `@warp` to a seeded walkable spot within 8 cells of the scene's GM spot (outdoor 268,107;
    indoor 104,122);
  - `@killmonster2`;
  - wait 3 s.
  - Between attempts: wait for the previous walk's duration + 1 s.
- **n = 50 per scene.** Pass: ≥ 48/50 per scene. Reported: off-by-n-cells counts and the click
  pixel distance.

### 3.3 attack@1 (runs after the v0-JPEG run ends: GPU, R1–R3)
- **The rule** runs inside the vision container (a guarded `rundev:vision` step: R1–R3, verified
  stops). It reads the frame bus and sends input as the agent (`MuxedEnv`).
  1. Detect: YOLO v0-PNG (`data/train/v0png-20261006/weights/best.pt`), conf 0.25, imgsz 1280.
  2. Choose the `monster` box whose centre is nearest the client centre (640, 400) and outside
     a 60×90 box around it (our own sprite).
  3. Click the box centre (left click).
- **Per attempt:** one click, then the harness waits 3 s.
- **The verifier:** `verify_attack`.
  - The intended gid is resolved from the click and `predict_sprite`'s boxes (§2);
  - walk-in time = (cell distance to the target − 1) × our speed;
  - the click-to-sprite distance is reported.
- **The harness:**
  - per block of 5: `@killmonster2`, then `@monster poring 5` at the scene spot (outdoor, and the
    indoor spot in prt_church), then wait 3 s;
  - `@heal` when the HP bar is below 0.6 (`gm_vitals`); `@alive` + return-to-game on death (the
    GM is level 1).
- **n = 50 per scene.** Pass: ≥ 48/50 per scene.
- ➡️ **Amended 2026-10-07 ~15:45 (Batt), before it runs:**
  - The verifier is **verify@2**: the attack request CZ_REQUEST_ACT2 0x0437 names the failure;
    the act still judges (§2).
  - **Still to build before the run:** `demo_verify`'s `attack_target` branch. It resolves the
    intended gid from the click and `predict_sprite`'s boxes at the frame's time
    (`verify.resolve_click` exists; the session's Timeline does not yet).

### 3.4 walk@2 (pre-registered 2026-10-07 ~13:00, BEFORE its run; replaces walk@1 after §Results)
**What changes from walk@1:**
- **The HARNESS closes the chat after every GM command** (an open chat input suppresses the walk
  marker), then brings the client to the front.
  ➡️ **The parenthesis is WRONG** (found 13:10, §Results walk@2): an open chat does not suppress
  the marker. The change is harmless and walk@3 keeps it as the calibration's UI state.
- **The seed is 20261008**, so the situations are new.
- **The rule's hover cue is re-calibrated for RDP** (`scripts/walk_marker_calibrate.py`, design
  time, chat closed):
  - **Filter `green_v2`:** marker pixels are those with g − r > 50, g − b > 35, r > 60, b > 60,
    g > 150. The HP bar's pure green fails r > 60.
  - **Outdoor calibration:** 30 / 30 walkable hovers gave 129–403 px. No non-walkable cell lay
    in the band around the spot.
  - **Indoor calibration:** 20 / 30 walkable hovers gave > 100 px and the other 10 gave 0;
    2 / 30 non-walkable hovers gave > 100 px.
  - The marker is BIMODAL (≈ 0, or > 100), so the threshold **≥ 60 px** means "a marker is
    drawn". It does not separate walkable from non-walkable indoors; that is the projection's
    job.
- **Unchanged:** the projection. Outdoors it is the minimap origin + GAT altitude; indoors the
  flat floor with the RDP camera's indoor block.
  - That indoor block was carried over from the console fit and is NOT validated on RDP.
  - The indoor calibration's misses (10 / 30 walkable hovers without a marker) are therefore an
    EXPECTED failure source, stated in advance, not a reason to change anything after the run.
- **Unchanged:** the verifier, the bar (≥ 48 / 50 per scene), n = 50 per scene, and the rule
  that a decline is a FAIL.
- **A run is INVALID** (re-run once the cause is removed) only on a harness defect found
  afterwards. A rule failure is reported as is.

### 3.5 walk@3 (pre-registered 2026-10-07 ~13:20, BEFORE its run; replaces walk@2 after §Results)
**What changes from walk@2:**
- **The rule's HOVER is two motion events:** 3 px up-left of the cell, 50 ms, then onto the cell,
  0.4 s, then the crop. That is exactly the calibration's procedure (`rule_run.hover_marker`;
  L2 `cue.walk_marker.hover`, drift-tested). The cue is unchanged: `green_v2` ≥ 60 px.
- **The HARNESS enters the scene once** before attempt 0: a warp onto the scene's map, then 7 s.
  walk@2's attempt 0 declined `no_selfpos`: 2.5 s after the first warp onto the map, the minimap
  was not drawn yet. Warps within the map keep 2.5 s (the probe read the minimap 18 / 18).
- **The seed is 20261009**, so the situations are new. The probes used seeds 4242 and 777, never
  the run's.
- **A systematic stop:** the run stops when the same decline repeats 10 times in a row, and is
  scored as it stands. Otherwise it runs to n = 50.

**Unchanged:**
- The projection: outdoors the minimap origin + GAT altitude; indoors the flat floor with the RDP
  camera's indoor block. That block is still NOT validated on RDP, so indoor misses remain an
  EXPECTED failure source, stated in advance.
- The harness's `close_chat` + `activate_client` before each attempt.
- The verifier (verify@1), the bar (≥ 48 / 50 per scene), n = 50 per scene, and the rule that a
  decline is a FAIL.

**Order:** outdoor, then indoor. Each is scored once by `demo_verify.py`.

**Design-time evidence, for the record (not a test):** the probes' 30 hovers were all outdoors on
prt_fild08. Nothing was probed indoors.

### 3.6 open_window@1 (pre-registered 2026-10-07 ~13:40, BEFORE its run)
**The rule, alone:** press the L2 chord for window W (`kro-20211103-prere.yaml`
`shortcut.window.W`), paced (ro_agent `CHORD_STEP_S`). Nothing else: the rule never looks at the
screen.
- **W** is one of status, skills, inventory, equipment: the four windows with cut anchors.
- **The order** is a seeded shuffle (seed 20261010) of the four, repeated: 12 or 13 attempts each
  per scene.

**The verifier** is the pre-registered menu verifier (§2), offline, from the session's snapshots:
- W's anchor (`poring_env.ui_anchors`, the 2026-10-07 templates) must be ABSENT on a frame
  decoded before the chord, and PRESENT on a frame decoded 1 s after the chord ends.
- Already open before → ambiguous.
- The other three windows' anchors are recorded too. Another of them appearing is a finding, not a
  pass.

**The anchors' own calibration** (design time, RDP, recorded before the run):
- 24 / 24 correct locates over the two shortcut-demonstration sessions (indoor
  `20261007T124649`, outdoor `20261007T132642`; before / after / toggled frames).
- Each window matched itself at 0.00, the nearest other window at 16.6, and `max_distance` is 6.
- The templates are cut from the indoor session. The run uses NEW frames.

**The harness** (logged as `rule:harness@1`, never part of the rule):
- It enters the scene once (a warp, 7 s, chat closed).
- Before each attempt: the client in front (`activate_client`); any of the four windows found
  open is closed with its own chord.
- After each attempt: W is closed with its chord when its anchor is found.

**Scenes:** outdoor prt_fild08, then indoor prt_church. **n = 50 per scene. Pass: ≥ 48 / 50 per
scene**, on RDP.
- A foreground-gate refusal or a guard Stop is a FAIL.
- 10 identical failure causes in a row stop the run, which is scored as it stands.
- A run is INVALID only on a harness defect found afterwards.

**Expected failure sources, stated in advance:**
- a chord the client ignores;
- the client not in front;
- a window opening somewhere its template does not match. Templates match anywhere, but a window
  could overlap another one.

### 3.7 walk@4 (pre-registered 2026-10-07 ~15:15, BEFORE its run; Batt's design, ~14:15)
**Batt's decision:** use BOTH position sources, with clear roles.
1. **The primary position source indoors is DEAD RECKONING.**
   - The arrival cell after a warp is known (L3 warp data). Here the harness's `@warp` cell stands
     in for it.
   - Each confirmed walk then moves the believed cell to its target.
   - The GAT altitude around the believed cell goes into the projection.
2. **The client's drawn walk marker is the pixel-only CONFIRMATION** (and the correction when
   the two disagree), because the game already renders the true 3D cell. S2 is tested
   separately.

**The colour cue was already fixed:** walk@2 replaced the mint filter (2–12 px) with `green_v2`
≥ 60 px, calibrated on RDP; walk@3 outdoor's clicks counted 111–217 px.

**What was new to calibrate is the marker's POSITION.** Design time, scratch, RDP; each trial
hovered, clicked, and the server-accepted cell was read offline from packets:

| session | trials | client picked the target | identified by the bias-corrected centroid |
|---|---|---|---|
| `20261007T144121-demo-walk4-cal-outdoor` | 30 | 30 | 30 / 30 (residual p50 1.0 px, p95 4.8) |
| `20261007T144755-demo-walk4-cal-indoor` | 40 (6 no marker) | 32 / 34 | 33 / 34 (residual p50 3.9 px, p95 12.1; the cell spacing ~42 px) |

- **The model:** marker centroid = projected centre + b0 + β × the cell's relative GAT
  altitude.
  - outdoor: b0 (−1.2, −2.7) px, β (−0.14, 0.20) px per unit;
  - indoor: b0 (−2.3, −4.7), β (−2.8, −0.77).
  - Raised indoor cells (+5) are drawn ~(−16, −9) px off the plain projection; that is why
    walk@3's flat-floor misses happened.
  - The values are in `rule_run.CENTROID_BIAS` and L2 `cue.walk_marker.rdp.centroid_bias`
    (drift-tested). They are IN-SAMPLE: this run is their test.
- **The 6 indoor hovers without a marker** were all legitimate:
  - a model hides part of the marker (31 and 43 px);
  - a wall stands in front of the target (the client shows its "cannot walk" cursor);
  - an NPC stands on the target pixel.
- **Stated in advance, a limit of the confirmation:** the centroid checks that the marker is drawn
  where OUR model expects the target's marker. A misregistration of our whole projection, by
  exactly a cell, would confirm falsely. The packets judge every attempt anyway.

> ➡️ **AMENDED 2026-10-07 ~16:05, BEFORE any scored run. The centroid-bias confirmation above
> and below is SUPERSEDED by the corner-anchor rule in this box** (Batt, 15:20: "prefer a grounded
> fix … a fitted per-altitude offset only if no grounded term exists").
> - **The camera model's altitude term is grounded and CORRECT.** World Y = the GAT altitude at
>   5 world units per cell, the rig ported from nostalro-client 15b3029 / korangar e14d320
>   (THIRD_PARTY.md). Scaling it by s: outdoors 13 cells at nonzero altitude fit best at s = +1
>   (0.9 px vs 5.7 px with no altitude); a look-at height above the feet only hurts.
> - **The "per-altitude bias" was OCCLUSION, not projection.**
>   - The raised indoor cells are PEWS: flat +5 strips, one cell wide.
>   - On them the bench model hides the marker's front chevrons, so the centroid of what is
>     visible moved by ~(−16, −9) px.
>   - The two visible chevrons sit exactly at the target's own back corners. The cursor was on
>     the right cell; the client picked the target in every such trial.
> - **The grounded rule: the marker's geometry.**
>   - The marker is four chevrons at the cell's CORNERS, inset to ~0.4 cell. Measured in cell
>     units on full markers, the two scenes agree; pooled: (−0.42, −0.30), (0.40, −0.30),
>     (0.40, 0.45), (−0.42, 0.45).
>   - Confirmation: green_v2 ≥ 60 px in ≥ 2 chevrons (8-connected components ≥ 6 px). The 3 × 3
>     cell whose projected corners, at THAT cell's own GAT altitude, best explain the visible
>     chevrons is the one the client picked. The mean chevron-to-corner distance must be
>     ≤ 0.35 cell spacing, else "unrecognised" → the next alternate.
>   - The same check against packet truth on the calibration hovers, re-run through the shipped
>     `rule_run.identify_cell`: **outdoor 30 / 30, indoor 33 / 34** (anchor fit p50 0.03 / 0.09,
>     max 0.17 cell). No fitted offset.
>   - The one miss is a stated failure source: only 2 chevrons showed, and the client had picked
>     the DIAGONAL neighbour, whose corners nearly coincide with the target's.
>   - `CENTROID_BIAS` is removed. L2 `cue.walk_marker.rdp.corner_anchors` replaces
>     `centroid_bias` (drift-tested).
> - **The run started at 15:01 with the centroid model** (`20261007T150101-demo-walk4-alone-indoor`)
>   was STOPPED after 5 attempts on Batt's instruction. It is NOT scored and does not count.
> - **The seed becomes 20261012:** that stopped run had seen seed 20261011's first situations.
>   Everything else in this section stands: dead reckoning, the hovers, the correction, the
>   harness, absolute targets, n, the bar, and the order (indoor, then outdoor).

**The rule, alone** (`rule_run.py walk4`, `walk4_rule`):
- **Position:** outdoors the minimap readout; indoors the dead-reckoned cell.
- **Projection:** the RDP camera (the indoor block indoors) plus the GAT altitude relative to the
  position, for the target's 3 × 3 neighbourhood.
- **Hovering:** two motion events per hover, at most 5 hovers per attempt.
  - The order: the target's projected centre, then 4 in-cell alternates (±0.3 cell along each
    grid axis).
  - Each hover: `green_v2` ≥ 60 px in a 120 px crop gives a centroid. The nearest expected
    centroid of the 3 × 3 names the cell the client would pick.
  - **The target → CLICK** at that hover point.
  - **A neighbour K → CORRECTION:** the next hover is moved by the projected difference
    P_target − P_K.
  - **No marker →** the next alternate.
  - **Nothing confirmed after 5 hovers → DECLINE** (a FAIL).
- **Dead reckoning:** after a click, the believed cell becomes the target. After a decline it
  stays.

**The harness** (never part of the rule):
- It enters the scene once.
- Every 5th attempt: a seeded `@warp` to a walkable cell near the scene's spot. The believed cell
  is set to it, so 4 of every 5 attempts start purely dead-reckoned indoors.
- Outdoors: `@killmonster2` every 10 attempts.
- Before each attempt: the chat closed and the client in front.
- The target: an ABSOLUTE walkable cell 2–6 cells (Chebyshev) from the BELIEVED position, inside
  the click band under the rule's own projection.
- After a click, it waits for the walk (0.2 s per cell + 1.2 s).
- **Seed 20261011** (new situations).

**The verifier:** verify@1, with the ABSOLUTE target (`relative=False`). A dead-reckoning error
therefore shows up as "walked to a different cell", a FAIL, as it should.

**Scenes:** indoor prt_church first (the case this design is for), then outdoor prt_fild08 (one
rule version, both scenes). **n = 50 per scene; pass ≥ 48 / 50 per scene**, RDP.
- 10 identical declines in a row stop a run.
- Interrupted attempts (a human lease, `demo_interruptions.py`) are re-run exactly.

**Expected failure sources, stated in advance:**
- targets behind walls (no pixel of the cell is clickable);
- NPCs on the target;
- the in-sample bias model;
- dead-reckoning drift after a walk the server shortened or re-routed.

### 3.8 walk@5 (pre-registered 2026-10-07 ~16:20, BEFORE its run; Batt's design, ~15:30)
**Batt's diagnosis of the indoor failures:**
- Long clicks across pews and walls fail: the server's path limit is 32 steps (MAX_WALKPATH),
  and an unwalkable target does not move the character.
- The cursor turns into a red NO-ENTRY sign over an unwalkable cell.
- So: **walk like the monsters**, in short straight segments, then turn.

**Design-time calibration (RDP; scratch `walk5-cal/`; client pixels stay in /dev/shm):**
- **Three probe outcomes, not two:**
  - green **chevrons** (walkable; their corners name the cell, walk@4's anchors);
  - the **no-entry sign**;
  - **nothing**: a plain arrow, e.g. over a wall top, off the floor, an occluder or an NPC.
    Indoors 6 of 20 GAT-blocked hovers showed that.
- **The no-entry sign** is recognised by SHAPE, not colour: the fraction of a ring mask (220 px,
  from the sign crops, red in ≥ 80 % of them) that is red, in a 64 × 64 crop on the hotspot.
  - Indoors (leave-one-out): walkable hovers ≤ 0.07; sign hovers 0.66–1.0.
  - The two walkable hovers with red pixels were the GM's own red HAIR, which is why a plain
    red count is not used.
  - Outdoors: 16 walkable hovers at 0.0. There is no blocked cell in the band around the spot.
  - **Threshold 0.4.**
- **S2 is NOT calibrated:** the cursor is drawn by the client, but the console path's encode and
  scale may change it. It gets its own calibration in an S2 session.

**The rule, alone** (`scripts/walk5.py`), per ROUTE (believed start → goal):
1. **PLAN** with A* on the GAT (`poring_dataset.walk.walk_path`, ≤ 48 steps).
   - Split the path into **segments**: runs of one step direction, at most **5 cells** each. That
     is far under the server's 32, inside the band where walk@3 and walk@4 were reliable.
   - A segment end outside the click band is shortened along the path.
2. **PROBE every segment end** before clicking: two motions, at most 5 hovers (the centre, then
   4 in-cell alternates at ±0.3 cell).
   - Chevrons naming the target → **click**.
   - Chevrons naming a neighbour → one correction (move by the projected difference); a second
     neighbour counts as a mismatch.
   - No-entry → **never click**.
   - Nothing → the next alternate.
3. **A no-entry sign (or a second neighbour) on a cell the GAT calls walkable = the belief is
   wrong:** stop, RE-LOCALISE, re-plan, continue.
   - Re-localisation **v1 uses the map's STRUCTURE as the landmark.** The camera follows the TRUE
     player, so hovering a screen offset o reports walkable(true + o).
   - The candidates are the believed cell ± 2. Each probe is the offset that best splits them,
     on cells flat for every candidate (so one pixel serves all). At most 8 probes; a unique
     survivor becomes the belief.
   - At most 2 re-localisations and 12 segment attempts per route.
   - ⚠️ **Batt asked for a landmark fix from a STATIC NPC "as proposed".** No such proposal was
     found in the repo. That version needs NPC placements and NPC sprites (the sprite catalog
     covers monsters only); it is **v2**, not built. v1 is what runs.
4. **Arrival:** dead reckoning after each click (wait 0.21 s per cell + 0.8 s); outdoors the
   minimap position is read before each segment.

**Stated in advance, a limit (tested in `test_walk5.py`):** a wrong belief is CAUGHT only when
the probed cell, seen from the TRUE position, is blocked or names a neighbour. If it is walkable
too, the client draws a consistent marker and the rule clicks; only the packets show the miss.

**The harness:**
- It enters the scene once.
- Every 5th route: a seeded `@warp`; the believed cell = the warp cell (the stand-in for L3 warp
  arrival data).
- Goals: seeded walkable cells with an A* path of **8–20 steps** from the BELIEVED position.
  Routes chain on dead reckoning between warps.
- **Seed 20261013.** Indoor prt_church first, then outdoor prt_fild08.
- **56 routes are run per scene; the first 50 NOT interrupted by a human are scored** (Batt:
  interrupted attempts are re-run; a route cannot be replayed exactly, so the spares stand in).

**Verifiers (verify@2):**
- **Segments:** each CLICKED segment by `verify_walk` against its ABSOLUTE end.
- **Routes:** end to end, where the packets put us 0.5 s after the route ended, against the goal.

**The bar:** end to end ≥ 48 / 50 routes per scene.

**Reported without a bar:**
- the segment success rate;
- **how often the probe caught a wrong belief:**
  - re-localisations triggered while the belief WAS wrong (packets) = catches;
  - triggered while it was right = false alarms;
  - wrong beliefs that clicked anyway = misses;
- re-localisation accuracy (its result vs the packets' cell);
- route declines by cause.

10 identical route declines in a row stop a run.

> ➡️ **3.8 SUPERSEDED before scoring (Batt's refinement, ~15:55).** The blocklist run
> (`20261007T154939-demo-walk5-alone-indoor`) was STOPPED after 14 routes and is NOT scored.
> - Batt's refinement:
>   - an ALLOWLIST: every cell on the straight line must show the plain WALK cursor, and the
>     target the chevrons;
>   - any other shape → no click (attack sword, talk bubble, no-entry, pickup hand, vending shop,
>     unknown);
>   - segments of 2–3 cells indoors and in crowded places, longer only in open areas when every
>     cell passes;
>   - the target re-checked right before the click;
>   - templates per cursor shape on RDP and S2 separately;
>   - tested with obstacles (GM-spawned monsters, an NPC, a vending shop if possible).
> - It becomes **walk@6**, pre-registered when its shape calibration is complete. ➡️ **Pre-registered as 3.9 below** (2026-10-07 ~18:05).

**walk@6 cursor-shape calibration, so far (RDP; scratch `walk5-cal/shapes-*`).**
- **The method:** sweep-hover the cells around a known cell; the cursor sprite is |crop with the
  cursor − crop with the cursor parked away|, minus the chevrons; then clustered by mask IoU.
- **The shapes found:**
  - WALK: the arrow, ANIMATED (a rotating arrow seen edge-on as a thin line, and a white
    "card"); 281 of 294 outdoor hovers;
  - ATTACK: a sword over Porings, also animated;
  - TALK: a speech bubble over the static NPC (20 hovers);
  - NO-ENTRY: the ring and slash.
- **Not yet:**
  - PICKUP: no item was hovered; it needs deliberate drops;
  - VENDING SHOP: it needs a second lab character with a Merchant's Vending, which the one
    client cannot provide now;
  - **S2: nothing yet.**
- **The allowlist makes the missing shapes safe:** only a positively matched WALK frame passes,
  so anything uncalibrated is "unknown" → no click.
- **Open design points:** the walk family's frames must be matched per frame (the animation);
  and the parked-cursor difference costs ~0.2 s per probe.

### 3.9 walk@6 (pre-registered 2026-10-07 ~18:05, BEFORE its run; Batt's allowlist refinement, ~15:55)
**The rule is an ALLOWLIST** (`scripts/walk6.py`): only a positively recognised WALK cursor passes.
Anything else (attack sword, talk bubble, no-entry, warp door, pickup hand, vending shop, unknown)
means no click.

**Design-time calibration (RDP; client pixels in `/dev/shm` and `data/walk6/`, never committed).**
- **The references:** 564 hovers (`walk5-cal/shapes-*`, 3 sweeps per scene), labelled per cluster by
  eye, plus 3 per-sample corrections. The corrections were plain arrows that the clustering had put
  with the no-entry signs.
  - Totals: walk 491, sword (the attack cursor) 26, talk 20, no-entry 15, **warp 12**.
  - The WARP cursor (a door ringed by green arrows) is a shape the earlier notes had missed. It was
    found indoors at prt_church 108–109,121–123. A click there would leave the map; the allowlist
    refuses it like any other shape.
  - Frozen as `data/walk6/cursor_refs_rdp.npz`.
- **A one-sided score was REJECTED.** It asked whether the reference's pixels were present, and a
  no-entry hover scored **0.987** against a WALK reference, because the sign is drawn OVER the arrow.
  An uncalibrated shape built the same way could pass as the arrow.
- **The classifier is TWO-SIDED:**
  - the hover's own cursor mask is |A − B|, minus the chevrons, the component on the hotspot;
  - B is ONE parked frame per segment;
  - the best reference must have mask IoU ≥ **0.6**, then a colour match ≥ **0.85** on the overlap
    (|Δ| < 40).
  - **Leave-one-out:** WALK recognised 483 / 491 per single grab (8 → unknown). **0 / 73 non-walk
    hovers → WALK** (their best WALK IoU: 0.0).
- **The design pilots** (6 sessions, `walk6-cal`, 17:33–17:50, not scored) found two machinery faults.
  Both were fixed before this pre-registration:
  1. **The client draws its cursor only where a SECOND motion leaves it,** ~0.41–0.82 s later; one
     motion never moved it (measured 17:46). The one-motion park left the cursor on the very cells
     about to be probed, so |A − B| lost it, and plain floor read as unknown.
     - The park now uses two motions, alternates two park points, and is accepted only once the
       frame shows the cursor AT the park.
     - The hover settle is **0.55 s** (walk@4/5 used 0.4).
  2. A refused target that is the GOAL is waited for, never blocked: blocking it left no plan.
- After the fixes:
  - outdoors: 4 / 4 routes reached the believed goal, with 1 unknown;
  - indoors: 3 / 4. Every refusal had an entity under the cursor: the NPC's talk bubble, Porings.
    One route ran out of segment attempts around the NPC.
  - All 6 pilots: **0 attack requests, 0 NPC contacts** in the packets.
- **Not calibrated, so UNKNOWN, so never a click:**
  - **PICKUP:** the GM's group has only `@killmonster2` (no drops). The level-1 GM died trying to
    kill spawned Porings itself (17:57; revived with `@alive`, the dialog closed).
  - **VENDING SHOP:** not possible with one client.
  - **S2:** a separate calibration.

**The rule, alone, per ROUTE** (believed start → goal):
1. **PLAN** as walk@5: A* on the GAT, at most 48 steps, split into straight or diagonal runs.
   - The run length depends on the context: **3 indoors, 5 in the open.**
   - After any probe in the route shows something other than the walk cursor, runs are **3** for
     the rest of the route.
2. **PROBE EVERY CELL of the run**, start excluded: park once, then hover each cell (two motions,
   0.55 s) and classify.
   - Up to 3 grabs (0.1 s apart) while the shape is unknown.
   - Every line cell must be WALK.
3. **The TARGET** must be WALK and show the chevrons naming it. As walk@5: one correction for a
   neighbour, then in-cell alternates, at most 5 hovers.
4. **RE-CHECK right before the click:** a fresh grab with no motion must still be WALK with the
   chevrons naming the target. Then click.
5. **When a run is refused:**
   - wait 1.0 s and probe it once more;
   - still refused → the cell is blocked for this route, and the route is re-planned (at most 3
     re-plans);
   - the GOAL itself is waited for (at most 3 times), never blocked;
   - a no-entry sign on a GAT-walkable cell means the belief is wrong: re-localise (walk@5's v1,
     at most 2), then re-plan.
6. **Limits and arrival:** at most 16 segment attempts per route. Arrival is dead reckoning; the
   minimap is read outdoors before each run.

**The harness:**
- As walk@5, with seed **20261014**: a seeded `@warp` every 5th route; goals 8–20 A* steps from the
  believed cell.
- **OBSTACLES:** at every 10th route, `@killmonster2` and then `@monster poring 4` around the GM.
  - Porings are passive unless attacked, and the rule never attacks.
  - Indoors, the static NPCs next to the GM spot are the NPC obstacle.
  - A vending shop is not possible.
- **56 routes per scene; the first 50 NOT interrupted by a human are scored.** Indoor first, then
  outdoor.

**Verifiers (verify@2):**
- Segments: each clicked run by `verify_walk` against its absolute end.
- Routes: end to end, where the packets put us 0.5 s after the route ended, against the goal.

**The bar, per scene:**
- end to end ≥ **48 / 50** routes; **AND**
- **SAFETY: zero `attack_request` and zero `npc_contact`** in the session's packets. The rule never
  intends either, so any one FAILS the scene, whatever the rate.
- Pickups are not decoded as a client request. The server's `act` with action pickup from our gid
  is checked instead.

**Reported without a bar:**
- segment success;
- refusals by shape and by place (line / target / re-check);
- **true vs false refusals:** whether the packets put an entity on the refused cell at that moment
  (offline);
- re-check catches, re-plans, goal waits, relocalisations (catches / false alarms / misses, as 3.8),
  stale parks;
- time per route.

10 identical route declines in a row stop a run.

### 3.10 relocalise@1, indoor (pre-registered 2026-10-07 ~18:20, BEFORE its run; Batt's "indoor landmark v1")
**What it tests:** re-localisation **v1, the structure probes**, ALONE.
- walk@5 and walk@6 call it only when a no-entry sign lands on a GAT-walkable cell. That is rare, so
  the method has never been measured on its own.
- Here the harness makes the belief wrong on purpose (`scripts/reloc_run.py`).

**The rule:** `walk5.relocalise`, UNCHANGED.
- The candidates are the belief ±2 cells, GAT-walkable.
- Each probe hovers the screen offset whose walkability best splits the candidates, on cells flat for
  all of them, so one pixel serves every candidate.
  - Chevrons → walkable; the no-entry sign → blocked; nothing → no information.
- A unique survivor becomes the new belief. At most 8 probes.
- **One stated change from walk@5/6:** the probe's settle is **0.55 s** (walk@6's measured lag), not
  0.4. The client draws its cursor ~0.41–0.82 s after the second motion.

**The harness, per attempt** (prt_church; seed **20261015**):
1. A seeded `@warp prt_church X Y` puts us on a walkable cell within ±8 of the GM spot.
2. The rule is handed belief = that cell + a seeded offset from the 24 non-zero offsets in the ±2
   square. The belief cell is GAT-walkable: a real dead-reckoning-sized error.
- **56 attempts; the first 50 NOT interrupted by a human are scored.**

**Scoring** (`reloc_run.py --score`, offline, against where the packets put us before the attempt):
- **correct:** the survivor is the true cell;
- **WRONG:** a survivor elsewhere. This is the dangerous outcome, confidently wrong;
- **undecided:** no unique survivor within 8 probes.

**The bar:** correct ≥ **48 / 50**.
- Reported separately: **wrong**, which is never acceptable silently; undecided; probes per
  attempt; and the share of probes that saw "nothing".

### 3.11 relocalise@2, indoor (pre-registered 2026-10-07 ~19:15, BEFORE its run; Batt's "decisive re-localisation", walk@7 (c))
**Why v2:**
- v1 probes only a screen offset whose cells are at the SAME altitude for every candidate.
- Among prt_church's pews (+5 GAT strips) no such offset exists for most beliefs. relocalise@1 ended
  most attempts with **0 probes**, and walk@6 indoors declined 10 routes on it.

**The rule** (`scripts/reloc2.py`, `reloc2.relocalise`): the altitude is EVIDENCE.
- **Candidates:** the belief ±**3**, GAT-walkable, from the START.
  - Design time: with ±2 plus widening only when nobody fits, a truth just outside the set left ONE
    WRONG survivor (`test_reloc2.py`).
- **Per candidate c and probe pixel p, the PREDICTION from c's own terrain:**
  - the hovered cell is the one among the flat guess ±1 whose projected centre, at its altitude
    relative to c, is nearest to p;
  - blocked → no-entry;
  - walkable → chevrons at its corner anchors (`MARKER_ANCHORS`), projected at that altitude.
- **The probe pixel:** the one whose predictions leave the smallest largest group (6 px buckets).
- **The elimination:**
  - chevrons keep the candidates whose predicted anchors fit within `MAX_ANCHOR_FRAC` (0.35 of a
    cell) **AND within 6 px of the best fit**;
  - no-entry keeps the candidates that predict a blocked cell;
  - "nothing" is no information.
- **Why the 6 px relative margin:**
  - on the indoor camera a pew's +5 lifts the chevrons 36 px, and the next diagonal row is 49.5 px
    up;
  - so the nearest-cell choice leaves ~13.5 px, inside the absolute tolerance (14.9 px);
  - **the 6 px is UNMEASURED: the WRONG count below is its test.**
- **The decision:** at most **12** probes. Exactly one survivor is the new belief. Ambiguous, a true
  alias (e.g. periodic pews: identical from every probe in reach), or no survivor → it fails. Never
  a guess.
- The probe settle is 0.55 s, as 3.10.

**The harness:** EXACTLY 3.10's: `reloc_run.py --method v2`, seed **20261015**.
- The same warps and the same wrong beliefs (within ±2), so the comparison is attempt by attempt.
- 56 attempts; the first 50 not interrupted are scored.

**Scoring** (as 3.10): correct, **WRONG**, undecided, against the packets.

**The bar:** correct ≥ **48 / 50**. Reported separately: WRONG (with each case), undecided, probes
per attempt, and the paired table v1 vs v2.

### 3.12 walk@7 — CLEAN and CROWD, indoor and outdoor (pre-registered 2026-10-07 ~19:15, BEFORE any run; Batt's design, ~18:45)
**Batt's reading of walk@6:** the RULE is right (0 unsafe clicks; 97.9 / 98.9 % of its clicked runs
correct); the ROUTE fails from decision-making under uncertainty.

**The rule** (`scripts/walk7.py`):
- **The gate is UNCHANGED.** It is `walk6.segment_step`: every cell the walk cursor, the target's
  chevrons, the no-motion re-check, with walk@6's frozen RDP references.
  - PICKUP is still uncalibrated there, so it stays UNKNOWN and is never clicked.
  - Pickup references, when made, go into a NEW reference set for a later rule.
- **(a) Patience for what moves.**
  - The grounding: a monster's idle pause between random walks is 4.0–5.0 s (rAthena e985006:
    `mob.hpp:39` MIN_RANDOMWALKTIME 4000; `mob.cpp:1766` next walk = tick + rnd()%1000 + 4000 + the
    walk's own time; `monster.conf` mob_nopc_move_rate 100, so a spotted monster always walks
    again).
  - A cell refused for a sword or an unknown shape is probed again (0.5 s polls) until **6.0 s**
    have passed since its first refusal. All waits of a route together are capped at **24 s**.
  - Only then is it routed around (at most 4 re-plans).
  - Static shapes never move, so they are routed around at once: talk = an NPC, warp = a portal.
    So is an unconfirmed target (an occluder).
- **(b) A blocked GOAL gets a SUBSTITUTE** after its patience: the nearest free cell around it,
  ring 1 then ring 2, the shortest plan first, at most 3 substitutes. The substitution and its time
  are logged.
- **(c) Re-localisation** uses **v2** (3.11). It is triggered by:
  - a no-entry sign or a twice-named neighbour on a GAT-walkable cell (as walk@6);
  - NEW: **2 targets in a row UNCONFIRMED from the same believed cell** (walk@6 routes 21–24).
  - At most 2 per route.
- **(d)** Every segment record's time is the **CLICK**.
- **Limits:** runs of 3 cells indoors, 5 in the open, 3 once crowded (as walk@6); 24 segment
  attempts per route.

**Two conditions, each its own test (Batt):**
- **CLEAN** measures walking: `@killmonster2` before EVERY route. Indoors there are no natural
  spawns, but the church's NPCs stay.
- **SEEDED CROWD** measures decisions: at every 5th route's warp, `@killmonster2` then `@monster
  poring 4`, so a fixed 4 Porings around us. Outdoors the field's own spawns refill over time,
  which is stated, not controlled.
- Both use seed **20261016**, so their first routes match. 56 routes per scene and condition; the
  first 50 not interrupted are scored.
- **Order:** relocalise@2 first, then indoor clean, indoor crowd, outdoor clean, outdoor crowd.

**Verifiers (verify@2):**
- Segments: `verify_walk` at the record's time, the click.
- Routes, end to end: where the packets put us 0.5 s after the route ended, against the goal.
  - OR against the logged SUBSTITUTE, which counts only when the packets put another unit within
    one cell of the goal at the substitution time ±1 s (`demo_verify.goal_taken`).
  - A substitute nobody forced is a FAIL.

**The bar, for each of the 4 runs:**
- end to end ≥ **48 / 50**; **AND**
- **SAFETY:** zero `attack_request`, zero `npc_contact` (and no pickup act by us).

**Reported without a bar:**
- segment success;
- refusals by place and shape;
- patience: waits, seconds, and how each ended (cleared or routed around);
- substitutes (justified or not);
- re-localisations (trigger; correct / WRONG / undecided against the packets);
- route time.

### 3.13 where@1, indoor (pre-registered 2026-10-07 ~22:10, BEFORE its run; Batt's idea, ~19:50)
**The fix:** the client's own **`/where`**: an ABSOLUTE position from pixels, with no packets as
input.

**Design-time facts** (RDP; client pixels in `/dev/shm` and `data/where/`, never committed):
- At 3 known cells (prt_church ×2, prt_fild08), `/where` printed `<display name>(<map>) : X, Y` in
  the chat window: **exactly the warp cell** every time.
  - The display name is Korean text, shown garbled through the Thai codepage; the internal map name
    and the numbers are ASCII.
  - The two lines before it on a map change are the client's own map-load notices.
- **No packet event** (decoded or unknown-id) in any `/where` window, so it reads as a client-side
  command.
  - Stated limit: a known but undecoded packet id would not show in this check.
  - Not yet tried on a non-GM account.
- **The font:** one flat colour (RGB 255,252,104), no anti-aliasing, a 14 px line pitch.
  - BUT the first samples lost pixels: the RDP progressive codec sends a coarse picture first and
    refines it, so a grab ~1 s after the text appears read some glyphs short.
  - So the reader takes a **STABLE** line only: grabs every 0.25 s until two consecutive newest
    lines are identical, at most 4 s.
- **The templates:** `0`–`9` and the comma, cut from 8 stable lines covering every digit.
  - All 8 parse back, but in-sample: this test is the real one.

**The rule** (`scripts/where_fix.py`, `fix()`):
1. Type `/where` through the chat path (the foreground gate applies).
2. Take the stable newest yellow line in the chat area.
3. Cut glyphs on empty columns (specks under 3 px dropped).
4. Read the trailing `X, Y`: each glyph equal to a template within 1 pixel. Anything that does not
   parse exactly is no fix, never a guess.

**The harness** (`scripts/where_run.py`, prt_church, seed **20261020**), per attempt:
- a seeded `@warp` to a walkable cell within ±8 of the GM spot;
- then a seeded click 3–8 cells away, so where we stop is known only to the packets (the "belief in
  doubt" case);
- then the fix.
- 56 attempts; the first 50 NOT interrupted are scored.

**Scoring** (`where_run.py --score`): against the packets' position at the read time.
- correct;
- **WRONG** (another cell: a misread absolute fix, the dangerous outcome);
- no fix.

**The bar:** correct ≥ **48 / 50** AND **WRONG = 0**.
- Reported: no-fix cases, read time (typing + stable wait), and the comparison with relocalise@2
  (16 correct, 24 WRONG / 50) and relocalise@1 (6 correct, 2 WRONG).
- **If it passes**, it is walk@8's indoor fix: at the start of an indoor route and whenever the
  belief is in doubt, not every step (Batt).

> ➡️ **Amended 2026-10-07 ~22:15, BEFORE any scored run completed.** The first run stopped at
> attempt 10 with "the chat input did not open".
> - **The cause was the HARNESS.** Its blind walk click can land on the expanded Basic Information
>   window's menu icons; one opened the client's Shortcut Description panel, which then blocked the
>   chat. The panel was closed with its X at (1099,119).
> - That partial session is **not scored**; no packets were written.
> - **The changes:**
>   1. The harness clicks only GAT-walkable cells projecting into a SAFE box (x 300–980,
>      y 200–520), clear of every UI panel.
>   2. **The rule gets a STALE-READ GUARD.** The chat area must CHANGE after typing, or there is no
>      fix. Without it, a `/where` that did not print would leave the PREVIOUS answer as the newest
>      line, read as a confidently wrong fix. Tested.
>   3. A chat input that will not open is a no-fix for that attempt, not a crash.
> - The seed, n and the bar are unchanged.

### 3.15 where@2, indoor AND outdoor (pre-registered 2026-10-07 ~22:35, BEFORE its runs; Batt's overnight plan, step 1)
**What changed from where@1, and why** (design time, from where@1's result and 20 kept diagnosis
crops):
1. **Colour.** Over a bright scene behind the semi-transparent chat window, the codec shifts glyph
   pixels to e.g. (255,255,68) or (240,249,65), outside where@1's strict window. Whole rows went
   missing: the 11 unparsed.
   - The line is now LOCATED by the strict colour (clean of background: its rows, and where the
     text ends).
   - It is READ with a YELLOWISH mask (R > 170, G > 170, B < R − 70).
   - The yellowish mask alone merged background into a 55-row "line"; that was seen and fixed at
     design time.
2. **Glyphs.** Each glyph is cropped to its own ink box, so vertical position never matters.
   - It is matched to the NEAREST template: at most 4 px different, and at least 4 px clearer than
     the second nearest.
   - The templates are the per-pixel MAJORITY of 8 stable design lines.
3. **Structure.** The number must follow the colon's SPACE (≥ 3 empty columns): digits, ONE comma,
   digits. A glyph that fails can never shorten a number; that was where@1's one WRONG, 109 read
   as 9.
4. **Out-of-sample check** (the 20 diagnosis crops, never used to cut): **20 / 20 correct, 0 wrong.**
   where@1's reader got 18 of the same 20.
5. **The plausibility gates** (Batt), in `where_fix.fix_v2`:
   - **two consecutive fresh reads** that **agree** (each with the stale guard);
   - inside the map; on a GAT-**walkable** cell;
   - within **6 cells** of the rule's own dead-reckoned belief;
   - up to **3** tries; otherwise no fix, never a guess.
   - Every rejection is logged by its gate.

**The harness** (`where_run.py --version 2`), per attempt:
1. `@killmonster2`;
2. a seeded `@warp` within ±8 of the scene's spot;
3. a seeded click on a GAT-walkable cell 3–8 cells away, inside the UI-free box;
4. **the belief = the warp cell + the click offset** (the rule's own dead reckoning);
5. the fix.
- **Indoor:** prt_church, seed **20261021**. **Outdoor:** prt_fild08, seed **20261022**.
- 56 attempts each; the first 50 not interrupted are scored.

**Scoring:** against the packets' position at the read time: correct, **WRONG** (the dangerous
class, reported apart), no fix (unresolved).

**The bar, per scene:** correct ≥ **48 / 50** AND **WRONG = 0**.
- Reported: gate rejections by gate, time per fix, and where@1 / relocalise@2 for comparison.
- **The normal account** (2000001): a separate, unscored confirmation that `/where` prints the same
  line for a non-GM character.

### 3.14 walk@8 — TUNING maps (indoor/outdoor × CLEAN/CROWD) + a HELD-OUT set run once (pre-registered 2026-10-08 ~00:00, BEFORE any scored run; Batt's design ~19:25 + the overnight plan)
**The rule** (`scripts/walk8.py` at the commit of this pre-registration, `--fix where`): walk@6/7 mixed two questions,
and walk@8 separates them.
- **Is the route passable?** Only static structure decides: the GAT.
  - The route is planned **ONCE** (A*) as a waypoint polyline; after each click the rest of that one
    plan is kept.
  - It is re-planned only after a belief fix or the minimap's correction.
  - Units never block movement in RO, so a unit on an intermediate cell refuses nothing.
- **Will this click walk?** Only the click point decides: the walk cursor (walk@6's two-sided
  classifier, references v2 incl. the pickup hand) plus the chevrons naming the cell, re-checked
  with no motion, then the click.
  - A covered click point moves to the next point on the polyline AT ONCE. Unknown is no click.
- **The portal** (held-out): the click whose intent is the portal expects the WARP shape. It is the
  only place that shape is allowed.

**The overnight fixes, each from a walk@7 misfire:**
1. **Patience ONLY for a UNIT** (sword / talk / pickup) at the click points: ≤ 6 s since it was first
   seen (a monster's idle pause ≤ 5.0 s, rAthena e985006), ≤ 24 s per route.
   - An unknown read never waits. walk@7 waited 23–94 s per run on unknown reads in CLEAN rooms.
2. **A substitute ONLY when a UNIT stays on the GOAL** after its patience (ring 1, then 2). walk@7
   substituted for any refusal: 7 of 8 goals nobody had taken.
3. **The belief is fixed by where@2** (3.15; indoor PASSED 48 / 50, 0 WRONG), never by v2:
   - at the START of each route on maps without a minimap readout;
   - **when in doubt**: a no-entry sign on a planned (GAT-walkable) cell, 2 targets unconfirmed from
     one belief, or a named neighbour;
   - never every step; at most 2 fixes per route; no fix = decline.
   - Outdoors the minimap is read before each click.
4. **The structure-probe alignment is OFF:** its geometry is v2's, which failed relocalise@2
   (24 / 50 WRONG).
5. The click time is the record's time. The route preview is on (display only).
- **Lengths:** 3 indoors, 5 in the open (walk@6/7's). At most 30 click attempts per route.


**Design-time pilots** (prt_church / prt_fild08, sessions `walk8-cal`, 23:19–23:58, NOT scored). Each
finding was fixed before this pre-registration:
1. **The client refuses "the same word/phrase more than 3 times".** A 4th `/where` in a row was not
   printed.
   - Every `/where` is now preceded by the read-only **`/ex`** ("There is no block list.").
   - A read counts only if the NEWEST line of all is the yellow one, with no red, cyan or green line
     below it.
   - That check accepts 28 / 28 good frames and refuses a cyan-newest one.
   - where@2's alone-test ran without the separator; walk@8 reports every fix against the packets.
2. **A stale park dropped the last click point.** The same point is now retried (2×).
3. **Pews hide part of the marker** (50–54 px on clear cells). walk@8 names a cell from ≥ 30 px, still
   with ≥ 2 chevrons and the corner-geometry fit.
4. **On a belief `/where` had just CONFIRMED,** pews hid the marker almost entirely (17–27 px).
   - Right after a fix (at the route start, or on doubt), a click point whose walk cursor holds on a
     no-motion re-check may be clicked without readable chevrons, **until the next click**.
   - Unknown or any other shape is still no click.
5. **One unknown in-cell alternate no longer condemns a cell.** A cell counts as covered only if no
   point of it shows the walk cursor.
6. **A moving monster ON the goal often reads unknown** (its sprite merges into the cursor mask).
   - A substitute now needs a UNIT shape seen on the goal **or on a click point next to it** in that
     round, after the patience.
   - The packets' judge still fails a substitute nobody forced.
- **The last pilot, after all fixes:** 7 / 7 routes, 22 / 22 clicks verified by the packets, 0
  attack / NPC requests.

**TUNING runs** (prt_church, prt_fild08), each with its own bar:
- **Conditions:**
  - CLEAN: `@killmonster2` before every route;
  - CROWD: `@killmonster2` + `@monster poring 4` at every 5th route's warp.
- **Fresh seeds:** indoor clean **20261023**, indoor crowd **20261024**, outdoor clean
  **20261025**, outdoor crowd **20261026**.
- 56 routes each; the first 50 not interrupted are scored.

**HELD-OUT runs, ONCE, scored separately, never used to tune**, only if all 4 tuning runs PASS:
- **guild** = alberta_in (60,40), the Merchant Guild room: seed **20261027**;
- **town** = prontera (156,180): seed **20261028**;
- **dungeon** = iz_dun00 (168,168): seed **20261029**;
- **portal** = prt_fild08 → its north portal (170,378) → prontera (156,26): seed **20261030**.
- All CLEAN (`@killmonster2` before every route; `@heal` after each warp; the maps' NPCs stay). 56
  each, the first 50 scored.
- **If a tuning run FAILS:** no held-out run. Diagnose from the packets offline, walk@9, at most 3
  iterations tonight (Batt).

**Verifiers (verify@2):**
- Clicks: `verify_walk` at the click.
- Routes, end to end: the packets' position 0.5 s after the route ended.
  - It must be the goal; or the logged substitute only when another unit stood within 1 cell of the
    goal then; or, for the portal, the other map (`to_map`) at the arrival cell.

**The bar, for every run:**
- ≥ **48 / 50** routes; **AND**
- **SAFETY:** zero `attack_request`, zero `npc_contact`, no pickup act by us. Any one is a HARD FAIL
  of that run.

**Reported:**
- clicks correct;
- covered-and-moved, waits (seconds), substitutes (justified or not);
- fixes (trigger; correct / WRONG vs the packets);
- declines by cause; route time.

### 3.16 walk@9 — TUNING (indoor/outdoor × CLEAN/CROWD), then the HELD-OUT set once (pre-registered 2026-10-08 ~00:25, BEFORE any scored run; iteration 2 of Batt's at most 3)
**The rule:** `scripts/walk9.py` at the commit of this pre-registration = **walk@8 (3.14) unchanged**
plus four fixes. Each fix comes from walk@8's indoor-CLEAN failures (42 / 50).
1. **Static green is not the marker.** Chevron pixels already green in the PARKED frame are
   scenery. In walk@8, from (112,111), the same 43 px of scenery "confirmed" two targets, and the
   clicks did not walk (3 routes).
2. **The scene must SHIFT after a click.**
   - The camera follows the character, so a walk changes most of the scene band (x 200–1080,
     y 140–560).
   - Measured: still scene 0.2–0.7 % changed; real walks ≥ 36.4 % (24 pilot clicks). The threshold
     is **15 %**.
   - No shift = doubt → a `/where` fix. If the fix shows we are still where the click started, that
     target cell is blocked for the route and the route is re-planned around it. walk@8 had 9 clicks
     that sent no move request at all.
3. **An all-unconfirmed round asks `/where`.** Every candidate showed the walk cursor and none was
   named. The unnamed-after-fix rule then applies. In walk@8, a lone unconfirmed goal declined one
   cell short.
4. **Animated scenery is out of the cursor mask.** There are two parked frames 0.25 s apart; pixels
   that changed between them (summed |Δ| > 60) are ignored in |A − B|. In walk@8, the altar end read
   UNKNOWN at every hover.
- Everything else is walk@8's:
  - plan once; only the click point probed; units never refuse a route;
  - patience and substitutes only for units;
  - where@2 at the route start and on doubt (with the `/ex` separator);
  - the warp shape only for an intended portal click;
  - the click time logged; the route preview on.

**The design pilot** (`walk9-cal`, prt_church CLEAN, seed 14, NOT scored): **6 / 6 routes, 24 / 24
clicks** verified by the packets.
- Two fixes, both correct: one for a named neighbour, one for an unconfirmed round.
- 0 attack / NPC requests.

**TUNING runs**, each with its own bar:
- **Conditions:** as 3.14 (CLEAN: `@killmonster2` before every route; CROWD: 4 Porings at every 5th
  route's warp).
- **FRESH seeds:** indoor clean **20261031**, indoor crowd **20261032**, outdoor clean **20261033**,
  outdoor crowd **20261034**.
- 56 routes each; the first 50 not interrupted are scored.

**HELD-OUT runs**, ONCE, scored separately, never used to tune, **only if all 4 tuning runs PASS**:
- guild (alberta_in) **20261035**; town (prontera) **20261036**; dungeon (iz_dun00) **20261037**;
  portal (prt_fild08 → prontera) **20261038**.
- All CLEAN, `@heal` after each warp. 56 each, the first 50 scored.

**Verifiers and the bar:** exactly 3.14's.
- ≥ **48 / 50** per run **AND** zero attack / NPC / pickup requests. Any one is a HARD FAIL.

**Reported:**
- clicks correct; dead clicks caught by the shift check (and confirmed by the fix);
- static-green pixels excluded; fixes (trigger; correct / WRONG);
- waits; substitutes (justified or not); declines by cause; route time.

### 3.17 walk@10 — TUNING (indoor/outdoor × CLEAN/CROWD), then the HELD-OUT set once (pre-registered 2026-10-08 ~01:49 ICT, BEFORE any scored run; iteration 3 of Batt's at most 3)
**The rule:** `scripts/walk10.py` at the commit of this pre-registration = **walk@9 (3.16)
unchanged** plus three changes, each from walk@9's indoor-CLEAN failures (39 / 50; the analysis is in
walk@9's results below).
1. **Click points from the client's PICKING** (`poring_dataset.picking`), not the projected centre.
   - The model: the camera ray against the GAT's TOP surfaces (side walls are passed through).
     Checked offline against the packets on the tuning maps: **480 / 485** indoor clicks (the
     centre: 467), **383 / 383** outdoor.
   - **Tier A:** every pixel within **6 px** picks the target (the model's 5 misses lay 1–5 px from
     its boundary). The usual rule applies: the walk cursor + the chevrons naming the cell, or,
     right after a fix, the walk cursor alone (re-checked with no motion).
   - **Tier B:** only when no tier-A pixel exists (the ~8 px strip behind a kneeler row): a
     **3 px** margin, and the chevrons MUST name the cell; never an unnamed click.
   - **No pixel picks the cell from here:** the next point on the polyline, at once.
   - A neighbour named at a pick-safe point no longer hops to the neighbour's pixel: it is doubt
     (a `/where` fix).
   - **Named again right after a fix** (the model and the marker disagree about that cell; the
     first pilot's route 3 spent all four fixes on one such cell, every fix correct): the cell is
     never clicked; it is blocked for the route and the route re-planned around it. A disputed
     GOAL declines (`goal_disputed`).
2. **One fix trusts the belief for up to 3 clicks** (TRUST_CLICKS), tier A only, while each click
   visibly SHIFTS the scene. No shift, or any doubt, ends the trust at once. In walk@9 the marker
   was hidden cell after cell along a pew corridor, so every step needed its own fix.
3. **4 fixes per route** (RELOCS; walk@8/9: 2). Each fix takes ~10 s; 34 / 34 were correct in
   walk@8/9.
- Everything else is walk@9's (and walk@8's): plan once; only the click point probed; units never
  refuse a route; patience and substitutes only for units; where@2 at the route start and on doubt;
  the scene-shift check; static green and animated pixels out of the cursor mask; the warp shape
  only for an intended portal click; the click time logged; the route preview on.

**The design pilot** (`walk10-cal`, prt_church CLEAN, seed 15, NOT scored): two pilots on prt_church CLEAN, seeds 15 and 16, NOT scored; 0 attack / NPC /
pickup requests.
- `20261008T013535-demo-walk10-cal-clean-indoor` (8 routes): **7 / 8; 34 / 34 clicks verified** by
  the packets (30 named, 4 unnamed after a fix; all tier A; none one cell short). Route 3 declined
  `relocalise_limit`: four fixes, all correct, spent on ONE cell whose every pick-safe point the
  marker named as its east neighbour. → the disputed-cell rule (above).
- `20261008T014420-demo-walk10-cal-clean-indoor` (6 routes, with that rule): **5 / 6; 28 / 28
  clicks verified** (27 named, 1 unnamed). Route 1 declined `no_click_point` one cell short of
  (114,120), a goal against the east wall: the cursor read UNKNOWN at every point (the marker named
  the cell). Unknown = no click stays; this is not changed.

**TUNING runs**, each with its own bar:
- **Conditions:** as 3.14 (CLEAN: `@killmonster2` before every route; CROWD: 4 Porings at every 5th
  route's warp).
- **FRESH seeds:** indoor clean **20261039**, indoor crowd **20261040**, outdoor clean **20261041**,
  outdoor crowd **20261042**.
- 56 routes each; the first 50 not interrupted are scored. **All four are run, in this order,
  whatever the first one scores** (walk@8 and walk@9 stopped after indoor CLEAN failed; this is the
  last iteration tonight, so every condition is measured).

**HELD-OUT runs**, ONCE, scored separately, never used to tune, **only if all 4 tuning runs PASS**:
- guild (alberta_in) **20261043**; town (prontera) **20261044**; dungeon (iz_dun00) **20261045**;
  portal (prt_fild08 → prontera) **20261046**.
- All CLEAN, `@heal` after each warp. 56 each, the first 50 scored.

**Verifiers and the bar:** exactly 3.14's.
- ≥ **48 / 50** per run **AND** zero attack / NPC / pickup requests. Any one is a HARD FAIL.
- **AMENDED 2026-10-08 ~03:15 (a measurement bug; recorded before the two outdoor runs were
  scored):** the live sniffer does not emit `attack_request` / `npc_contact` (offline-only decoders,
  bc1a2e6). Attacks and pickups are measured by the server's `act` packets from the GM (live). NPC
  contact cannot be measured live; it stays "unverified" until the banked-capture replay (parked for
  Batt). The bar is unchanged; only its instrument is. See the CORRECTION below the walk@10 results.

**Reported:**
- clicks correct, by tier and named / unnamed; clicks one cell off (and to which side);
- dead clicks caught by the shift check; fixes (trigger; correct / WRONG);
- waits; substitutes (justified or not); declines by cause (incl. no pick-safe point); route time.

### 3.18 walk@11 — the click-instant UNIT GATE; TUNING (indoor/outdoor × CLEAN/CROWD), then the HELD-OUT set once (pre-registered 2026-10-08 ~09:25 ICT, BEFORE any scored run; Batt's decisions 3 + 4 of 2026-10-08)
**Why:** walk@10 solved the wrong-cell walks, but safety failed. A walk click became an attack (3
hard fails: a unit reached the click point after the cursor re-check). Clicks whose cursor read
WALK beside an NPC's edge contacted the NPC (the replay: walk@8, walk@9, walk@10 crowd).

**The rule:** `scripts/walk11.py` at the commit of this pre-registration = **walk@10 (3.17)
unchanged** plus:
1. **The click-instant unit gate** (`unit_gate.py`; Batt: PREDICTION, not a later check; the
   worst-case envelope, his choice over a tracker).
   - Right after the cursor read and its re-check, a fresh frame goes to the CPU detector
     (`unit_detector.py`: player / monster / npc). The detector is proven on RDP frames in §2c:
     monsters 97.9 % outdoor / 97.0 % indoor, NPCs 40 / 40, feet within 45 px.
   - Each unit's cell is the client's pick under its feet. At the click's arrival it may be
     anywhere within ceil(H / its fastest speed) cells, **+ one more step**. NPCs are static.
   - H = the frame's age at the click + **0.36 s**: frame staleness (RDP packet→frame p95 157 ms) +
     click→server (median 178, **p99 197 ms**, n = 720 walk@10 clicks) + 0.05 s.
   - Speeds are mob_db's fastest over the map's KB spawns and the Poring: **prt_fild08 200 ms /
     cell, prt_church 400, iz_dun00 150, prontera 400, alberta_in 400**; players 150.
   - The click point must lie **≥ 12 px outside every moved box**. Otherwise it is a point covered
     by a UNIT: the next point on the polyline, walk@8's patience and substitute rules.
   - Our own character is excluded. No detector = no click (fail closed).
   - **MEMORY** (Batt's choice after pilot 1 below): every unit seen on any frame the rule grabs
     (each park, each decision) is remembered at its absolute cell for **8 s**. Its envelope grows
     with the time since it was last seen: ceil((age + H) / speed) + 1. A new detection of the same
     class within a remembered unit's reach updates it. The memory resets at every harness warp.
   - **Farther points:** a point refused by the envelope moves FARTHER along the polyline (up to 4
     points beyond seg_max, in the click band; Batt's walk@8 rule) before patience.
2. **The v3 cursor references** (§ the talk calibration): an NPC at the click point reads TALK, a
   unit.
3. **Not included, measured:** the "cancel" walk click after a click that hit a unit
   (`safety_signal_check.py cancel-test`, a static Red Plant; n = 3 clicks that hit). The first
   hit lands 0–245 ms after the request, and after the cancel's walk request the client
   re-requests the attack. Hits continued in 3 / 3. A different cancel (a key, the dialog close)
   is a later study.
- **The detector:** v0-PNG `best.pt` sha256 `b5966feb…`, exported to ONNX 1280×736 (sha256
  `0b5aa3d3…`), confidence 0.25, IoU 0.5, 8 CPU threads, in the RAM environment of
  docs/operations/detector-cpu.md.

**The design pilots** (NOT scored): three, prt_church CROWD, NOT scored; the safety signals were live and proven.
- `20261008T084919-demo-walk11-cal-crowd-indoor` (seed 17, the gate WITHOUT memory): **1 attack**
  (11 hits). The click at (109,118) read WALK with the marker naming the cell, and the envelope saw
  only 2 NPCs. The Poring stood ON that cell, **hidden behind a pew** (a kneeler cell), invisible to
  the detector and to the cursor; the client's hit test found it. → the MEMORY.
- `20261008T090156-demo-walk11-cal-crowd-indoor` (seed 19, memory): **0 requests, 0 GM acts**;
  19 / 19 clicks verified; 4 / 8 routes. After route 5's spawn, routes 5–7 never clicked: every
  point within seg_max lay in some Poring's envelope. → the farther points.
- `20261008T091024-demo-walk11-cal-crowd-indoor` (seed 21, memory + farther points): **0 requests,
  0 GM acts**; 27 / 27 clicks verified; 4 / 10 routes. 48 envelope refusals against 25 clicks; a
  Poring out of view for a few seconds gets a 6–23 cell radius (the whole screen).
- **Batt, 09:23: pre-register as is (safety first)**, run all four tuning runs, and design the
  tracker (T1 motion model) in parallel as walk@12 to win completion back. **Expected:** the CROWD
  runs FAIL by count; the point is safety in every condition, and the clean runs may pass.

**SAFETY instruments, all LIVE and proven by a deliberate positive case (§2a):** `attack_request`,
`npc_contact`, and the server's `act` from the GM (kinds normal, pickup), each counted inside the
session's manifest window. The banked-capture replay (`guarded_build.py replay:`) re-checks every
run afterwards.

**TUNING runs, all four whatever the first scores:**
- Conditions as 3.14. FRESH seeds: indoor clean **20261047**, indoor crowd **20261048**, outdoor
  clean **20261049**, outdoor crowd **20261050**.
- 56 routes each; the first 50 not interrupted are scored.

**HELD-OUT runs**, ONCE, scored separately, never used to tune, **only if all 4 tuning runs PASS**:
guild (alberta_in) **20261051**, town (prontera) **20261052**, dungeon (iz_dun00) **20261053**,
portal (prt_fild08 → prontera) **20261054**. All CLEAN, `@heal` after each warp, 56 each.

**The bar (zero tolerance, unchanged):** ≥ **48 / 50** per run **AND** zero `attack_request`,
zero `npc_contact`, zero `act` from the GM of kind normal or pickup, in the run's window. Any one
is a HARD FAIL.

**Reported:** the 3.17 items, plus per click the envelope (units, nearest class and distance,
horizon, detection ms) and the refusals the gate caused. **Known residual risk:** the detector
misses ~2–3 % of units in a frame (scenery occlusion: one Poring under the church chandelier).
The cursor gate is the first layer; a click on a unit needs both layers to miss.

### walk@12 — DESIGN PROPOSAL: the motion model (T1-lite) inside walk@11's envelope (NOT pre-registered; Batt approves first)
**➡️ Batt's decisions for the next walk version (2026-10-08 ~11:25), from walk@11's runs:**
1. **Click points exclude the client's UI windows.** Their anchors are known (L2): each window's
   rectangle plus a margin. The cursor gate cannot protect there: over a UI window the client shows
   its plain arrow, which reads as WALK. (walk@11 indoor CROWD route 53 clicked the Basic
   Information icon grid.)
2. **The harness finishes its session cleanly when it cannot type** (t1 + packets), instead of
   exiting without them.
3. **A TALK read blocks the whole picked cell:** every band point that picks the same cell is
   refused. (Three NPC contacts, walk@11 clean and crowd: a WALK read 8 px from two TALK reads,
   all three points picking one cell.)

The motion model below stays a proposal: its premise is open for Batt (the looter problem).

➡️ **These three decisions are pre-registered as walk@12 in §3.21, WITHOUT the motion model.** The
motion model below, if adopted, takes a later walk version.

**Why:** walk@11's memory envelope is safe but stalls crowd routes. A unit out of view for a few
seconds gets a 6–23 cell radius, because it may move at its fastest speed the whole time. The
engine says otherwise (phase3-plan §6b, rAthena @e985006, read for mechanics only).
- **The random walk:** a monster walks to a target within ±7 cells, then **stands at least
  4.0–5.0 s** (`MIN_RANDOMWALKTIME 4000 + rnd()%1000`, after the walk ENDS).
- **Who moves or chases, per map** (the KB's `ai` over its spawn list; the detector cannot name
  species, so each map takes its worst species):

| map | species (ai, ms/cell) | worst mobile behaviour |
|---|---|---|
| prt_fild08 | Lunatic (1, 200), Pupa (–, immobile), Poring (2, 400), Drops (2, 400) | passive random walk |
| iz_dun00 | Plankton (1), Marina (1), Kukre (2, 150), Hydra (10, aggressive IMMOBILE), Vadon (17), Black Mushroom (–) | passive random walk |
| prt_church, prontera, alberta_in | no spawns; the crowd's Porings (2) | passive random walk |

  No mobile species on these maps chases unless attacked, and the gate exists to prevent that.

**The proposal:**
1. **Detect while we stand.** A ~3 Hz background detection between our own walks (the camera is
   still): units are tracked in world cells. Only this is new perception.
2. **Per unit, the walk END we saw** (its cell changed, then held). For T < t_end + 4.0 s the unit
   cannot move: radius 0, + the one step. Outside that window, it can complete at most one walk
   per 4 s, so the reach is min(speed reach, 9 cells per possible walk) + 1. That is the ±7 target
   plus 2 for a detour.
3. **Unknown phase** (never seen move): walk@11's speed bound, capped by the per-walk bound.
4. **A map with an aggressive MOBILE species:** walk@11's rule (speed-only, no cap).
5. **Memory:** as walk@11. An occluded unit seen to stop keeps radius 0 + 1 for up to 4 s.

**Its own safety test BEFORE any walk run** (offline, the packets as ground truth): over every
click in walk@10/@11's recorded sessions, the model's envelope at the click's arrival must CONTAIN
every monster's true cell (`Walk.position_at` from the packets). Required: **100 % containment**,
and the refusals it would have caused reported against walk@11's.

**Then** a pilot and a pre-registration under the next free number (3.19 went to rec@0), all four tuning runs.

**Premise check (offline, 2026-10-08 ~09:40; the live packets of walk@10's four runs and walk@11's
three pilots; 2,267 monster moves):**
- **One walk ≤ 7 cells (Chebyshev): HOLDS.** The largest observed displacement is 7.
- **A stand ≥ 4.0 s after a walk ends: does NOT hold for Porings.** Of the walk-to-walk gaps of
  monsters we never touched, short ones occur only for Porings: 35 of 1,805 (1.9 %). Lunatic
  (ai 1): 0 of 81; Drops (ai 2): 0 of 26, too few to tell.
- Porings are ai 2 (passive LOOTER): a looter may walk to an item on the floor without the
  random-walk timer.
- **Consequence:** for Porings, the crowd condition's own monster, the stand guarantee is not a
  safety bound. Chained walks also break the per-walk cap, so for a looter map the model falls back
  to walk@11's speed bound. walk@12 as proposed would gain little on crowd routes. **Open for Batt:**
  a looter-aware model (are items on the floor? the detector has no item class), a different crowd
  species, or keep walk@11's bound.


### 3.19 rec@0 — what really STOPS an attack on our client (pre-registered 2026-10-08 ~11:35 ICT, BEFORE any run; Batt's decision of ~11:25)
**Why:**
- ADR-0020 §13.9's recovery default is "walk away", and Batt's premise was that "a walk click
  cancels an attack in RO". He confirmed it was an assumption, never measured on our client.
- walk@11's cancel test (§3.18 point 3) measured the opposite for one variant: a walk click 2 cells
  away, right after the attack click, against a static Red Plant (n = 3). The client re-requested
  the attack after the walk, and hits continued 3 / 3.
- rec@0 finds which action stops an attack before rec@1 fixes the recovery default. "Walk away"
  stays the default meanwhile, with its caveat.

**The setup:** lab rAthena, RDP, ASSIST, the interlock green, the GM.
- The target is one Red Plant (1078), spawned at the cancel test's spot (`safety_signal_check.py
  cancel-test`'s placement). It is static and never fights back. A plant takes 1 damage per hit,
  so it survives long enough to show whether hits continue.
- The detector finds it, and the attack click on it is DELIBERATE (harness, not a rule).
- `@killmonster2` and a fresh plant between trials.

**The conditions**, n = 10 each, in a seeded interleaved order. Each cancel input comes 400 ms
after the attack click: walk@11 measured the first hit 0–245 ms after the request, so the attack is
under way by then.

| id | the cancel | why |
|---|---|---|
| C0 | NONE | the POSITIVE CONTROL: the instrument must see the attack continue |
| C1 | a walk click 2 cells away (cursor-gated walk point) | walk@11's cancel, replicated |
| C2 | a walk click ≥ 6 cells away, beyond the target's reach (cursor-gated walk point) | Batt's "walk away" |
| C3 | the sit key (L2 `sit`: Insert), then stand 1 s later | sitting is a different state change |
| C4 | a Fly Wing by its hotbar key (the GM is given them with `@item`) | the known hard stop: a teleport |

**The measure:** the live packets, in the run's window; GM = the lab GM's block id.
- the GM's `act` hits (kind normal) on the plant in [t_cancel + 0.3 s, t_cancel + 5 s] (one swing
  already in flight is allowed);
- any `attack_request` after t_cancel.
- **A trial SUCCEEDS** when both are zero.

**The bar:**
- A cancel STOPS an attack if ≥ 9 / 10 of its trials succeed, AND C0 shows the attack continuing
  (≥ 2 hits after t_cancel + 0.3 s) in ≥ 9 / 10. Without C0 the zero means nothing (§2a).
- A cancel that passes is the recovery default for rec@1. With several passes, the one with the
  fewest side effects wins: C2 over C3 over C4.
- If none passes, ADR-0020 §13.9's default falls back to the wing, and a new candidate is studied.

**Also reported:**
- the time from the cancel input to the last hit;
- the end state: moving, sitting, or teleported (position from `/where`);
- side effects: a Fly Wing used, a sitting state left behind.

**When:** after walk@11's outdoor reruns and the route-preview demo (one client).

### 3.20 loot@1 — kill, then loot WITHOUT new training: a hover-scan for the PICKUP cursor, verified by the weight readout (pre-registered 2026-10-08 ~11:40 ICT, BEFORE any run; Batt's Q21 decision; a SMALL alone-test, after rec@0)
**Why:** Batt's decision (ADR-0020 open question 21): loot without a ground-item detector class
first.
1. The tracker knows where a monster died.
2. Hover-scan the cells around that cell for the PICKUP cursor (references v2, calibrated
   2026-10-07).
3. Click it, and verify by the weight readout rising.
- A ground-item class comes later, as an improvement.

**Prerequisites:** each is built and proven by a deliberate POSITIVE case (§2a) BEFORE any trial.
- **P1 · the weight readout, from pixels:** the Basic Information line "Weight : N / M". A new L1
  read concept, since no reader exists yet. Proven when `@item` gives an item of known weight and
  the readout rises by exactly that weight.
  - ➡️ **Batt, 2026-10-08:** P1 also REPORTS the readout's RESOLUTION: the smallest weight change
    that moves the shown number, measured with items of known weight from the pinned item_db.
    Some drops may weigh less than one step, and then the number does not move even on a
    successful pickup.
- **P2 · the offline decoders,** which do not exist yet:
  - the item-on-floor entry (`ZC_ITEM_FALL_ENTRY`: item and cell);
  - the pickup result (`ZC_ITEM_PICKUP_ACK`).
  - Each is proven on a banked capture by `replay:`. They are OFFLINE ground truth only, never
    decision input (rule 1). The GM's live `act` of kind pickup is already decoded and proven
    (§2a).
- **P3 · the death cell, a stand-in for the tracker** (Phase 3 T1 is not built). For the ONE
  deliberate target: its last detected foot cell (the detector + the picking model) on the last
  frame before it vanishes after the kill.
  - Offline truth: its vanish with reason "died", and its last position from the packets.
- **P4 · the drop rates** of the target species, read from the pinned rAthena mob_db (a KB
  extension). They are reported, never committed.
  - Also the item weights (item_db), and the lab server's floor-item lifetime (its pinned config;
    ~60 s is the expected order).
- ➡️ **Built 2026-10-08 (code + host tests only; NONE proven live yet, §2a):**
  - P1: `poring_env/weight.py` (the reader: (N, M) or None + a reason + a confidence; it REFUSES
    templates that lack any digit), `scripts/weight_calibrate.py` (templates cut locally into
    `data/ui_anchors/weight_glyphs.npz`, labelled by packet truth), `scripts/weight_resolution.py`
    (`plan` / `measure`: the resolution and the display rule). The banked frames show only
    0 2 3 9 and '/': the live calibration must step the weight through every digit first.
  - ➡️ **P1 PROVEN LIVE 2026-10-09 06:52–06:56 ICT / 2026-10-08 23:52–23:56 UTC** (session
    `20261009T065204-demo-weight-digits`, after two harness fixes):
    - **The two fixes:** the client refuses a phrase repeated more than 3 times, so the first four
      runs (2026-10-08/09) delivered only 2–3 of 10 identical `@item` steps (the packets show it). A
      `/ex` line between repeats did NOT help (d7abcf7). Every line is now unique: leading zeros on
      the item id, which rAthena reads with `strtoul` (8592426).
    - **The start:** the weight was topped up to a whole 641.0 (server 6410) with arrows, so every
      calibration step lands on a multiple of 10.
    - **Calibration:** 10 × Jellopy (+1.0 each), 642 → 651, all ten digits shown. `weight_calibrate`:
      **READY**: complete, 63 held-out reads OK, 0 wrong.
    - **On known totals** (held out from calibration), `weight_resolution.py measure`:
      - Knife +40.0: **651 → 691**;
      - Knife +40.0: **691 → 731**;
      - Jellopy × 5, +5.0: **731 → 736**;
      - **all three EXACT.**
    - **Resolution:** the display FLOORS, consistent with the server in all 26 readouts checked.
      Ten arrows of +0.1 each: the first nine never moved the number (736), the tenth did (737,
      server 7370). **The resolution is 10 rAthena units = 1.0 shown.** A pickup lighter than 1.0
      may not move the number, which is what P5's chat cue backs up.
    - The templates are installed locally at `data/ui_anchors/weight_glyphs.npz` (client pixels,
      never committed). `data/kb` now holds P4's `items.json` / `drops.json` / `server.json`
      (`kb_build.py`, local, GPL-derived, never committed).
  - P2: the decoders above (§5, "Floor items and pickups"); proven only by a replay of a deliberate
    drop + pickup (`guarded_build.py replaydev:`, the checkout's decoders read-only in the sniffer
    image: no rebuild) and `scripts/loot_truth.py`.
    ➡️ **PROVEN LIVE 2026-10-08 21:10 ICT / 14:10 UTC** (the 17:51 sniffer carries the decoders),
    by a deliberate drop + pickup (`20261008T210930-demo-safety-check-pickup`):
    - `floor_item_appear` (kind fall, floor id 54, item 1201, cell (98, 112));
    - our `pickup_request` (floor id 54);
    - `pickup_result` ok (1201 × 1);
    - our `act` of kind pickup on 54, then 54's vanish.
    - `loot_truth.py --aid 2000002`: **1 pickup "confirmed"**, 1 fall, 0 failed results. No replay
      is needed for P2 any more.
  - P3: `poring_dataset/deathcell.py` (`death_cell`, `scan_order`: the server's drop pattern
    first); its truth is `loot_truth.py`'s death cells (the Timeline's position at the "died"
    vanish).
  - P4: `scripts/kb_build.py` writes `items.json` (weights), `drops.json` (rates, effective on the
    lab server) and `server.json` (`flooritem_lifetime` 60 000 ms, from the pinned drops.conf);
    `--show-drops 1002` prints a species' table. Generated locally, never committed.
- **P5 · the backup "item obtained" cue, from pixels** (Batt, 2026-10-08): the client's own
  item-get notification, or its line in the chat / battle log.
  - ➡️ **BUILT and PROVEN LIVE 2026-10-09 00:42–00:44 ICT** (`scripts/chat_cue.py`, db0f0a6 + the fix
    75778a8).
    - **The reader:** the newest COLOURED chat line must be cyan, its first 48 px must match a
      locally cut "got" mask (not the "dropped" one, IoU ≥ 0.8), and the coloured text must have
      changed.
    - **The fix:** the first live check (00:39–00:41) passed its negative case for the WRONG reason.
      The scrollbar's arrows and the input box's white border read as a newer line, and white scene
      highlights counted as a change. With only those removed, an old "got" line + a walk would have
      cued falsely. 75778a8 reads only the message lines and coloured text.
    - **The re-proof on fresh frames** (session `20261009T004257-demo-safety-check-pickup`):

| case | expected | got |
|---|---|---|
| a known pickup (drag to floor, pickup click; packets: 1 pickup act) | cue | **cue** (got 1.00, dropped 0.54) |
| a cursor-gated walk click that picks nothing up | no cue | **no cue**, read as the OLD got line with 1 px of coloured text changed |
| the drop itself | no cue | **no cue** (read as "dropped") |

  - It is found by its L4 locale key; the text is never committed (rule 4).
  - Proven on a KNOWN pickup: an item dragged from the GM's inventory to the floor, then picked up.
    The cue must appear, and it must not appear on a click that picks nothing up.

**The trial:** lab rAthena, RDP, ASSIST, the interlock green, the GM.
1. `@heal`; a FRESH spot from a seeded list of open cells ≥ 6 cells apart, so no item left on the
   floor by an earlier trial is in reach.
2. `@monster poring 1` beside the GM.
3. DELIBERATE attack clicks until it dies. Death is read from pixels: the target is gone after its
   death animation.
4. **LOOT** (the rule under test):
   - hover-scan the 3 × 3 cells around the death cell, with two motions per hover (the walk-marker
     rule);
   - a click needs the cursor gate with PICKUP as its ONLY allowed shape (two reads), walk@11's
     unit gate, and the client's UI windows excluded;
   - click the first PICKUP point.
5. **The runtime check:** within 5 s of the click, the weight readout rises by ≥ 1 step (P1),
   **OR** the item-obtained cue appears (P5). The combination is pre-registered here:
   - the item's expected weight (offline, P2 + item_db) decides which signal can count;
   - an item lighter than one readout step can only be confirmed by the cue, and the trial is
     marked "sub-resolution";
   - either signal alone is enough at run time;
   - each signal's own recall is reported separately (below).
6. `@killmonster2`, then the next trial.

**Speed: the floor-item lifetime (Batt).** The scan must finish well inside it.
- The order: the death cell first, then its 8 neighbours.
- Each hover is about 1 s (two motions, then the drawn cursor settles).
- **Budget:** ≤ 20 s from the death to the pickup click. A trial past 45 s is a FAILURE ("too
  slow"), even if it then picks the item up.
- Reported: the death → click time (median, p95), and where items actually landed relative to the
  death cell (P2's floor entries), which sets a better scan order next time.

**Counted:**
- trials whose kill DROPPED an item (offline, P2). Run until 20 such trials, at most 40 kills.
- **A drop trial SUCCEEDS** when all three hold:
  - the runtime check says obtained (step 5);
  - the server confirms the pickup (offline: the pickup result, and the GM's pickup act);
  - it was within the speed budget.
- **A runtime "obtained" without a server pickup is a FAILURE** (a false positive of the check).
  So is a server pickup the runtime check missed.

**The bar:** ≥ 19 / 20 drop trials.
- This is the small alone-test Batt asked for.
- The full n = 50 comes before L1 `loot.pick_up` flips to verified.

**SAFETY (zero tolerance), in the LOOT phase only** (from the target's death to the trial's end):
zero `attack_request`, zero `npc_contact`, zero GM `act` of kind normal.
- The kill phase's attacks are deliberate, and are excluded by that window.
- A pickup act is the expected outcome here, not a violation.

**Also reported:**
- each signal's recall on the confirmed pickups: weight alone, the cue alone, and the two combined,
  with sub-resolution items counted apart;
- hovers per success;
- PICKUP reads with no item at that cell (against P2's floor entries);
- time from death to pickup;
- items left behind when a kill dropped several;
- the weight rise against the item's weight.

**When:** after rec@0 (§3.19), and only once P1–P4 hold. ➡️ The run plan is 3.20a (2026-10-09:
P3's positive case first, then the trials).

### 3.20a loot@1 — the RUN PLAN: P3's positive case, then the trials (pre-registered 2026-10-09 ~09:00 ICT / 02:00 UTC at commit, BEFORE any run; Batt 2026-10-09 ~08:30: "loot@1: pre-register and run after walk@16's tuning runs")
3.20 stands as written. This fixes what it left open, before any run. Nothing in 3.20 is moved.

**The harness:** `scripts/loot1.py` at the commit of this section; scored OFFLINE by
`scripts/loot1_score.py` (the packets, `loot_truth.ledger`).

**Place and spots:** prt_fild08. The spots are a seeded list of open cells in x 245–295,
y 85–130, each with its ±4 square walkable (the spawn lands within 3 cells, the scan reaches 1
more), every pair ≥ 6 cells apart (`loot1.spots`; 3.20's "fresh spot").

**One trial:** `@killmonster2`, `@alive`, `@heal`, `@warp` to the spot, `@monster` Poring 1. Then:
- **The target:** the monster box nearest the GM's feet (within 220 px), tracked frame to frame
  (its feet within 45 px) by a sampler thread running the CPU detector on every frame it can.
- **The kill (3.20 step 3, deliberate attack clicks):** a click on the target's box ONLY where the
  cursor reads the SWORD twice. This is the monster positive case's rule (§2a), never a box centre
  (rec@0b: 51 of 53 box-centre clicks walked). It is repeated if the target is still visible 8 s
  after a click, and the kill is "no_kill" if the target has not vanished 30 s after the first
  click. `@alive` + `@heal` start every trial, because the level-1 GM can lose to a Poring.
  - `@killmonster` (WITH drops) was considered and is NOT used: it is not in the GM's command set
    (group 20 in `groups.yml` is deliberately minimal), and adding it is Batt's call.
- **The GM's cell:** where@2 (`/where`, two agreeing reads) once the GM has walked up and fights
  (1.5 s after the first attack click), or after the death. No fix means no loot, never a guess
  (a failure if the kill dropped an item).
  ➡️ **AMENDED 2026-10-09 ~14:00, BEFORE any loot@1 run (the pilot included), Batt's typing policy:**
  - "Players type /where once and are done ... position comes from the MINIMAP readout on every map
    that has one."
  - loot@1 is on prt_fild08, outdoors with a minimap: the GM's cell is the MINIMAP readout
    (`poring_env.selfpos`, T0; read 267, 125 exactly on today's RDP frame), two EQUAL reads on fresh
    frames, walkable, within 6 cells of the spot.
  - **loot@1 types no /where at all.** No read means no loot, never a guess.
- **Death from pixels:** the target seen after the first attack click, then unseen for ≥ 3 frames
  AND ≥ 1.0 s. Its cell: `poring_dataset.deathcell.death_cell` (the last 3 sightings' feet, 4 px up,
  through the picking model from the GM's fixed cell; spread ≤ 1 cell).
- **LOOT and the runtime check:** exactly 3.20 steps 4–5. The 3 × 3 cells in
  `deathcell.scan_order`; one hover per cell, two motions; PICKUP read twice is the only shape that
  clicks; walk@11's unit gate; no point within 12 px of the client's UI windows; the first such point
  is clicked. Within 5 s: the weight readout rises (two equal reads) OR the chat cue reads "got".
  - Every Poring drop weighs ≥ 1.0 shown (the local KB: Jellopy 1.0, Sticky Mucus 1.0, Apple 2.0,
    Empty Bottle 2.0, Knife 40.0, Unripe Apple 5.0, Poring Card 1.0). So no sub-resolution trial
    is expected; any one would be reported apart.

**Step 0 · a PILOT, never scored:** `loot1.py run --n 2 --seed 20261109` (2 kills with loot)
checks the harness end to end on the live client. Any fix it needs is committed BEFORE step 1, and
the pilot's session is reported but counts for nothing.

➡️ **THE PILOT (2026-10-09 15:00–15:01 ICT, session `20261009T150021-demo-loot1-run`; counts for
nothing) and the HARNESS FIXES it needed, committed BEFORE step 1:**
- **Trial 0 (spot 294,121): "no_sword".**
  - The packets show the spawned Poring WANDERING: 2–12 cells from the spot, a step every ~6–7 s.
  - The sampler ran at ~2 fps (116 frames in 60 s, CPU detector).
  - The fixed 45 px track gate lost the Poring after its first step, so 5 of the 6 sword probes
    hovered the SAME stale box, over empty ground (cursor WALK).
- **Trial 1 (spot 264,108): not found.** The Poring appeared 1 cell from the GM 3.2 s before the
  find decision, but that decision judged only the LAST of 3 frames.
- **Found in the code, a policy breach of my own (8a1ac98, 09:00):** the `@monster` line was varied
  with leading zeros per trial (`@monster 01002 1` was typed once, trial 1), a device against the
  client's repeat counter.
  - It was not caught at the 14:00 amendment.
  - Batt's typing policy (~12:15) forbids that kind of evasion, and it served nothing: four other
    lines stand between two `@monster` lines.
- **The fixes (harness only; the kill's safety rule is unchanged: a click only where the cursor reads
  the SWORD twice):**
  1. `@monster 1002 1`, plain, every trial (a test pins it).
  2. The spawn is looked for on EVERY frame for up to `FIND_S` = 6 s, not on one frame.
  3. The track gate grows with the time since the last sighting: `MOVE_PX_S` = 110 px/s, from 45 px
     up to `TRACK_MAX_PX` = 160 px.
  4. A sword probe needs a FRESH and STILL box: seen ≤ 0.5 s ago, its feet moved < 6 px since the
     sighting before it, ≤ 1.5 s earlier. A Poring stands for seconds between steps.
  5. Found but no sword-gated click within 30 s → "no_sword" (probes tried) or "never_still" (none).
     The 6-tries rule stays.
  - Each probe logs the box's age and motion. Unit tests cover the gate, the still rule, the
    every-frame find and the plain line.
- **A SECOND PILOT, also never scored** (`loot1.py run --n 2 --seed 20261112`, a fresh seed),
  checks the fixes end to end before step 1. If it still cannot kill, step 1 does not start, and that
  is reported to Batt.

➡️ **PILOT 2 (2026-10-09 15:05–15:07 ICT, session `20261009T150554-demo-loot1-run`, main at af9693c;
counts for nothing): the chain works end to end once; the kill phase is still fragile.**

| trial | what the pixels did | what the server says |
|---|---|---|
| 1 (spot 255,92) | found on the 2nd frame; probe 1 read WALK (moved-off box); probe 2 read SWORD twice and clicked; "vanished"; death cell (254,97), stable; PICKUP click 3.94 s after the death; runtime: weight rose AND cue "got" | `attack_request` → 11 GM attacks → the Poring DIED at (254,98), 6 cells from the spot; its Jellopy fell ON that cell; then `pickup_request` + the GM's pickup act. A full success; P3 within 1 (pixel 254,97). Scored by the AMENDED scorer below |
| 0 (spot 292,121) | found at once; probe 1 read SWORD twice and clicked; probe 2 (another box) read unknown ×2, WALK | the sword-read click became a WALK (`self_move_request`): the Poring had just started moving. The GM's walk scrolled the camera, so the screen-space track lost the Poring; the pixels then declared a death (cell unstable: no loot). The Poring was alive and was removed by the next trial's `@killmonster2` |

- **Two kill-phase weaknesses are NOT fixed** (P3 and the trials report them; they are not P3's
  verdict):
  1. A target that starts moving between the SWORD read and the click turns the click into a walk.
     This is benign, the mirror of walk's safety case.
  2. The track lives in SCREEN space, so the GM's own walk (the camera follows it) can break it and
     produce a false pixel death. P3 judges only kills that died on the server, so a false death
     costs a judged kill, not a wrong verdict.
- **Step 1 may start:** the pilot killed once, with the server's confirmation. P3 needs ≥ 8 judged
  kills of 10; if the kill phase loses too many, P3 is INCONCLUSIVE and is reported so.
- **Held** until the console layout fix is deployed (Batt 2026-10-09 ~14:57: deploy in a gap with no
  scored client run).

➡️ **SCORER AMENDMENT (2026-10-09 ~15:25 ICT, BEFORE any scored loot@1 run; found by scoring pilot 2,
whose trial 1 is the positive case):** the committed scorer gave pilot 2 "no server death" for
BOTH trials and 0 drop trials, although the packets show trial 1's Poring dying and our pickup.
Two defects, fixed in `loot1_score.py` / `loot_truth.py` with tests built on pilot 2's real event
shapes:
1. **The target rule.** "A Poring death within 5 cells of the spot" missed the chased Poring, which
   died 6 cells away.
   - Now the target is the unit our FIRST `attack_request` after the first attack click names
     (`target_gid`): the server's own record of what the deliberate click attacked.
   - No request means "no attack request" (the click became a walk: pilot 2 trial 0).
   - Other gids we attacked are reported, never guessed between.
   - This replaces 3.20a's "within 5 cells of the spot" for P3 and the trials alike.
2. **The drop link.** The server sent the drop's `fall` 0.24 s BEFORE the "died" vanish, and the
   ledger accepted falls only 0–1.5 s AFTER it.
   - Now from `DROP_BEFORE_S` = 1.0 s before to 1.5 s after, the closest death in time.
- **Re-scored pilot 2:** trial 1 success, P3 within 1, drop offset (0,0), death → click 4.09 s, both
  runtime signals; trial 0 "no attack request". This proves the scorer on a positive case, and the
  pilot still counts for nothing.
- The 3.20 bar, the safety window and every verdict rule are unchanged.

➡️ **THE GM'S FIXED TEST STATE, BEFORE STEP 1 (Batt 2026-10-09 ~16:00):** pilot 2's kill levelled
the GM up (Base Lv 2; HP 45; status points; the level-up icon and badges, which cleared when the
status window opened at 16:02).
- Batt: "the GM's level is now an uncontrolled variable. Restore a fixed test state ... and record the
  GM's state at each run start."
- Every loot@1 trial now starts at **Base Lv 1 / Job Lv 1**, through `scripts/gm_state.py`:
  - the level lines checked from pixels against a Lv 1 / 1 template;
  - `@baselevelup -98`, `@joblevelup -49`, `@heal` typed only when they differ (group 20 got both
    commands in `groups.yml`);
  - the state recorded in `trials.json` (`gm_state`: restored or not, the weight readout, a crop
    of the Basic Information window).
- Job EXP is recorded, not fixed.
- ~~The grant is NOT live yet~~ ➡️ **LIVE since 16:35 (Batt's ordered sequence).**
  - The 16:10 restart was stopped by the IO guard (quant-ticker-engine 47.3 %).
  - At 16:35:24 a guarded `restart:rathena@120` + `restart:sniffer@30` passed (guard worst 4.7 %). The
    GM's auto re-login was OK and the interlock green at 16:38:34.
  - **At 16:39 the GM was restored by command,** from Base Lv 2 (HP 45) to **Base Lv 1 / Job Lv 1**
    (HP 40 / 40, SP 11 / 11, base EXP 0). Job EXP stayed (~78 %); the weight was 738 / 2030 (one
    Jellopy).
  - **The Lv 1 / 1 template was cut** (`data/ui_anchors/gm_state/`).
  - **The check:** the restored frame differs from the template by 0 px; the Lv 2 frame saved before
    the restore by **20 px** (the limit is 4). So a level change is detected: the positive case.
  - P3 may start once Batt clears it (his 16:35 sequence stopped at step 4 on an IO trip).
  - ➡️ **Batt cleared P3 (~16:50).** The level change brings back the client's NOTICES (a badge on
    the first shortcut icon + the level-up icon). The known clearing step (the status window
    opened, then closed by the UI gate) is now part of `gm_state`, judged from pixels.
  - **P3 attempt 0 (16:54:59, session `20261009T165459-demo-loot1-p3`): a HARNESS STOP before trial
    0's kill.** The notice check called the field's grass seen through the shortcut window a
    "badge". Nothing else was typed (only the status chord and its close).
  - Fixed: each notice is judged on its own pixels. Checked on the stored frames: with notices,
    both are found; on the clean prontera and field frames, none.
  - P3 is re-run unchanged with the same seed, 20261110: no trial had run (the walk@13 precedent).

➡️ **P3 RESULT (2026-10-09 16:57–17:09 ICT, session `20261009T165750-demo-loot1-p3`, main at f17edd1;
scored by the amended `loot1_score.py`): INCONCLUSIVE, so loot@1's 40 trials do NOT run (3.20a).**
- **Kills:** 3 of 10 vanished from the pixels and 7 ended "no_sword".
  - Only trial 1 had a server death of our target: **P3 exact** (pixel (261,124) = server (261,124)).
  - Trials 8 and 9 were FALSE pixel deaths. The attack requests reached the server, but those
    Porings never died in their trials.
  - **1 judged kill < 8 → INCONCLUSIVE.**
- **The blocker is the cursor read over a Poring.** Of 105 first reads at the probe points: **unknown
  67 (64 %)**, WALK 35, SWORD 3. 37 probe tries gave 3 clicks.
  - This is the same family as walk@17 item 5's finding for TALK: thin colour margins, and a 1-px
    shift of a reference reproduces "unknown" (docs/planning/npc-click-test.md).
  - Its fix belongs to that analysis (hypotheses C1–C5), not to loot@1.
  - ➡️ **Offline follow-up (2026-10-09 ~20:30, NOT live, the gate unchanged):**
    docs/planning/cursor-robust.md reproduces it (SWORD over a bobbing Poring: the gate's reader
    0 / 150, over a still one 21 / 75; 9 of the 26 SWORD references are mostly Poring motion) and
    builds a robust reader (97 / 150 there, 0 cross-shape errors). Its live acceptance (a SWORD
    probe over Porings + npc-click's probe arm) is a DRAFT for the parent.
- **The GM's fixed state:** no trial needed a restore (Base / Job Lv 1 throughout); no notices.
- **Safety:** no loot phase ran, so there are no loot-phase safety events to count.

➡️ **TYPING TRANSPORT CHANGED BEFORE STEP 1 (2026-10-09 ~16:10; Batt's mandatory item 6):** every
line loot@1 types (its GM commands) now passes the UI gate (`scripts/ui_gate.py`, 3.32 item 6)
first. No decision code changes: the gate either finds the client clear (~1.5 s per line) or stops
the run before typing. A stop is a harness stop (exit 3), never a trial result.

**Step 1 · P3's positive case (BEFORE any loot trial; §2a's rule):** `loot1.py p3 --n 10 --seed
20261110`, the same kills with no loot.
- **Judged per kill whose target died on the server** (its "died" vanish within 5 cells of the
  spot, after the first attack click; never guessed between two):
  - the pixel death cell against the server's cell at that vanish;
  - a missing pixel cell (unstable, no /where fix) counts as a miss.
- **P3 PASSES** with the pixel cell within 1 cell of the server's in ≥ 9 / 10 judged kills, with ≥ 8
  kills judged (the 3 × 3 scan covers ±1). Fewer than 8 judged kills: INCONCLUSIVE.
- **Exact matches are reported too.** Kills that failed (no target found, no sword read, no kill)
  are reported apart. They are the kill phase's failures, not P3's.
- **If P3 does not pass, loot@1 does NOT run,** and that is reported.

**Step 2 · the trials:** `loot1.py run --n 40 --seed 20261111`. All 40 are attempted whatever happens.
- **The scored set:** the FIRST 20 DROP trials in order, where a drop trial is a kill whose server
  death dropped ≥ 1 item (P2).
- **The verdicts are 3.20's:**
  - a success needs the runtime "obtained", the server's confirmation of OUR pickup of one of those
    drops after the loot click, and the click within 45 s of the server's death;
  - a runtime "obtained" without a server pickup is a FAILURE, as is a server pickup the runtime
    check missed.
- **SAFETY** is counted from the server's death to the trial's end: `attack_request`,
  `npc_contact`, and our act of kind normal. The kill phase's attacks are deliberate and excluded.
- **The bar (3.20):** ≥ 19 / 20 AND zero safety events. Fewer than 20 drop trials in the 40:
  INCONCLUSIVE ("not enough drop trials"), never a pass.
- **Reported, as 3.20 lists:**
  - each signal's recall on the confirmed pickups;
  - death → click (median, p95; the 20 s budget);
  - hovers per success, and PICKUP reads with no item;
  - where the items landed against the death cell;
  - the items left behind;
  - the weight rise against the item's weight;
  - the kill phase's outcomes.

**Before each run:** a client screenshot, and the UI as pre-registered (the 3.24 inventory
incident).

**Expected** (Claude's reading; NOT a bar):
- The kill phase is the least proven part: the sword gate on a moving Poring has one positive case
  so far, and the GM may lose a fight.
- /where adds ~4–6 s; the scan ~1.5 s per cell.
- The drop falls ON the death cell first (rAthena's pattern), so most pickups should come from the
  first hover.

### 3.21 walk@12 — walk@11 + the WORK ZONE, the TALK-cell block and a clean harness exit; TUNING (indoor/outdoor × CLEAN/CROWD), then the HELD-OUT set once (pre-registered 2026-10-08 ~14:43 ICT at merge, BEFORE any run; Batt's decisions of 2026-10-08 ~11:25)
**Why:** the walk@11 verdict (0 of 4 tuning runs PASS; its results above).
- **The unit gate held against monsters:** 0 attack requests and 0 GM attacks in 705 rule clicks
  (231 + 212 + 147 + 115) across all four runs. walk@10 attacked in three of its four.
- **What remained, and failed the bar:**
  - one NPC contact in each indoor run, at the cell (112,114) beside Sister Linus. A WALK read 8 px
    from two TALK reads, all three points picking that one cell: the mechanism of every NPC contact
    since walk@8;
  - one rule click on a UI window (indoor CROWD route 53: client (52.9, 295.8), the Basic
    Information icon grid). It opened the Shortcut Description window, the chat input could not
    open again, and the run exited without its end time and packets (finished offline).
- **Completion** (47 / 31 / 39 / 31) is not what this version changes.

**The rule:** `scripts/walk12.py` at the commit of this pre-registration = **walk@11 (3.18)
unchanged** plus exactly Batt's three decisions.
- walk12 does not copy walk@11. Its route loop and its harness ARE walk@11's functions (the same
  code objects), re-bound to walk12's click step, label and session log. `test_walk12.py` checks
  that the code is the same and that walk11's module is untouched.
1. **Click points exclude the client's UI windows** (`scripts/work_zone.py`).
   - The WORK ZONE is the game area minus each `route_preview.UI_WINDOWS` rectangle, grown by
     **12 px**. The windows: basic info + its menu icons, the hotbar, the small top window, the
     minimap, the chat window (client px at the frozen 1280×720 layout).
   - Over a UI window the client shows its plain arrow, which the cursor gate reads as WALK, so the
     gate cannot protect a click there.
   - Every candidate pixel must lie in the work zone: tier A / B, the farther points' and the
     substitutes' (they come from the same function), and the portal's. A refused pixel is never
     hovered.
   - Tier B is used only when no tier-A pixel lies in the work zone (named clicks only, as before).
     A cell with no work-zone pixel is `no_safe_point`: the next point at once (walk@10's rule).
   - Tested: the observed point (52.9, 295.8) is refused, a point 0.5 px outside the margin is
     allowed, and with no window near a cell the points and tier are exactly walk@11's.
   - The same helper is the work zone of the targeting proposal (c) below.
2. **A TALK read blocks the whole picked cell.**
   - Within one click attempt (the points of one target cell): once a point reads TALK, every later
     point that the picking model maps to the same cell is refused without a hover.
   - An attempt that clicks nothing ends **`covered_talk_cell`**: a unit at the click point, so
     walk@8's patience and substitute rules apply.
   - A round tries each cell once, and tier A / B points of different cells never pick the same
     cell, so the block covers the whole round. It does not carry over into a later round: after
     patience, the cell's points are read afresh.
   - Tested on a synthetic band (one TALK point, four WALK points named in the same cell): walk@11
     clicks the cell (the positive control), walk@12 refuses the four unhovered.
3. **The harness finishes its session on any exit.**
   - A Stop (e.g. "the chat input did not open"), any other exception, or an interrupt (SIGINT,
     SIGTERM) still writes the session's packets (the manifest's t0 to the end) and its end time
     t1, through walk@11's finish path. The manifest records `ended`, `reason` and `exit_code`.
     No input is sent after the failure.
   - The run then exits NONZERO: 3 for a Stop, 4 for another exception, 130 for an interrupt. A
     normal end exits 0 with `ended: complete`.
   - A rule decline is not a harness exit: a route declines and the run goes on, as in walk@11.
   - If a harness exit leaves fewer than 50 scored routes, the run is re-run unchanged with its
     pre-registered seed; the partial session is kept and not scored (walk@11's outdoor precedent,
     3.18 results).
- **Everything else is walk@11's:** the click-instant unit gate with its 8 s memory, the farther
  points, the v3 cursor references, the detector (the same ONNX, confidence 0.25, IoU 0.5, 8 CPU
  threads), tiers A / B, the `/where` fixes (4 per route, trust for 3 clicks), patience and
  substitutes, the scene-shift check, the click time logged, the route preview.

**Not included:** the motion model (T1-lite) stays a proposal (the "walk@12 — DESIGN PROPOSAL"
above). Its premise is open for Batt: the looter problem.
- **Expected** (Claude's reading of walk@11's numbers, not Batt's words; not a bar): the CROWD runs and outdoor CLEAN fail by count
  again. What this version must show is zero safety events in every condition: no NPC contact and
  no UI click.

**Design pilot:** none at the time of writing; host tests only (`services/backend/tests/test_walk12.py`).

**SAFETY instruments, all LIVE and proven by a deliberate positive case (§2a):** as 3.18.
`attack_request`, `npc_contact`, and the server's `act` from the GM (kinds normal, pickup), each
counted inside the session's manifest window. The banked-capture replay (`guarded_build.py
replay:`) re-checks every run afterwards.

**TUNING runs, all four whatever the first scores:**
- Conditions as 3.14. FRESH seeds: indoor clean **20261055**, indoor crowd **20261056**, outdoor
  clean **20261057**, outdoor crowd **20261058**.
- 56 routes each; the first 50 not interrupted are scored.
- e.g. `scripts/walk12.py --scene indoor --condition clean --seed 20261055 --label walk12-alone`.

**HELD-OUT runs**, ONCE, scored separately, never used to tune, **only if all 4 tuning runs PASS**:
guild (alberta_in) **20261059**, town (prontera) **20261060**, dungeon (iz_dun00) **20261061**,
portal (prt_fild08 → prontera) **20261062**. All CLEAN, `@heal` after each warp, 56 each, the first
50 scored.

**The bar (zero tolerance, unchanged):** ≥ **48 / 50** per run **AND** zero `attack_request`,
zero `npc_contact`, zero `act` from the GM of kind normal or pickup, in the run's window. Any one
is a HARD FAIL.

**Reported:** 3.18's items, plus:
- **UI-exclusion refusals:** the click attempts with `ui_refused` (the pixels refused), the cells
  left with no work-zone pixel, and the rule clicks whose pixel lies in a grown UI window (0 by
  construction; checked from the logs).
- **TALK-cell refusals:** the `covered_talk_cell` attempts, their refused points (`talk_refused`)
  and cells (`talk_cells`), any later click on such a cell, and any `npc_contact` there.
- **Harness ends:** each run's manifest `ended` and `exit_code`.

**AMENDMENT (2026-10-08 ~15:50, Batt: "allowed, recorded as display-only"): the route preview
becomes the LIVE previewer, applied AFTER the four tuning runs.** The pre-registration lists "the
route preview" among walk@11's parts. That preview was the one-shot screen-pixel picture, which
floated off the character as the camera scrolled; the console stopped drawing it at 15:20 (ffb5b82).
- **What changed** (branch `feat/route-plan-wiring`, merged after the tuning chain):
  - walk@11's `preview` IS `route_plan.preview`: the route in map cells to the previewer daemon
    (`route_previewd.py`), and nothing at all unless a run enables publishing. walk@8-10 get the
    same binding and never enable it (retired: no line).
  - walk@12's `run` enables publishing around walk@11's run (`route_plan.enable` / `disable`).
  - Display-only wrappers publish the engine's walk after each click, each `/where` fix, and the
    clear at each route's end. They change no argument and no result:
    `route_plan.hook_click_step` / `hook_relocalise` / `hook_route_end`.
- **The proof that no decision changed.** Every function's COMPILED code was hashed (bytecode,
  constants, names, argument layout; line numbers ignored) in main (before) and on the branch
  (after), with `decision_hash.py` (scratch; the method is in its docstring). Every file the walk
  imports and the branch does not touch is byte-identical.

| file | functions | identical | differs |
|---|---|---|---|
| walk5.py | 22 | 22 | — |
| walk6.py | 30 | 30 | — |
| rule_run.py | 28 | 28 | — |
| work_zone.py | 2 | 2 | — |
| cursor_gate.py | 3 | 3 | — |
| unit_gate.py | 14 | 14 | — |
| walk11.py | 35 | 34 | `preview` (now the binding above) |
| walk12.py | 20 | 19 | `run` (enable/disable around walk@11's run); `engine_path` added (display) |

  - `test_walk12.py` still checks that walk_route and run11 ARE walk@11's code objects, now
    through the wrapper's `__wrapped__`.
- **The one cost.** The wrapper computes the engine's path for the preview AFTER each click returns.
  Measured over 300 random steps per map: prt_church median 0.00 ms, p95 0.19 ms, max 0.88 ms;
  prontera median 0.04 ms, p95 0.96 ms, max 18.65 ms. That is negligible beside the rule's own
  waits for motion. The publish itself is one non-blocking datagram.
- **The previewer runs in its own process,** reading the RDP frame bus after tonight's backend
  restart. So it does not contend for X grabs with the rule.

**AMENDMENT 2 (2026-10-08 ~18:50, Batt: "wire operator_hud publishing into the walk rules' harness
... display-only, never blocking a decision ... prove decision code is unchanged"): walk@12 publishes
the OPERATOR HUD.** The HUD shows the detector's boxes (class, confidence, distance in cells), each
click's gate verdict (allowed / refused + reason), the work zone, and a plain-words decision log.
- **No work between the gate and the click.** walk@11's unit gate decides at the click instant, and
  its envelope assumes the click follows at once, so its hook only RECORDS the verdict. Everything
  else is published by the click-step hook AFTER the step returned (the click is done).
- **Its own agent connection** ("operator-hud"): an error reply can never stop the rule.
- **The proof** (the same method; `HEAD` 79ffa9f vs 7d23e13): walk5, walk6, walk11, rule_run,
  work_zone, cursor_gate and unit_gate are identical. walk12 differs only in `run` (the enable /
  disable around walk@11's run).
- walk@12 itself is decided (above); the HUD serves walk@13 and the demo runs.

**RESULTS (2026-10-08, the tuning chain 14:52–17:24 ICT, the pre-registered seeds): 0 / 4 PASS by
count, ZERO safety events and ZERO UI clicks in all four.** The held-out set does not run (it runs
only if all four pass).

| run (seed) | session | success / 50 | live safety | replay `20261008T07..T10` | rule clicks that did not walk | harness end |
|---|---|---|---|---|---|---|
| indoor clean (20261055) | `20261008T145202-demo-walk12-alone-clean-indoor` | **43** | 0 / 0 / 0 | 0 / 0 / 0, covered | 1 of 222 | complete |
| indoor crowd (20261056) | `20261008T153151-demo-walk12-alone-crowd-indoor` | **40** | 0 / 0 / 0 | 0 / 0 / 0, covered | 3 of 206 | complete |
| outdoor clean (20261057) | `20261008T162053-demo-walk12-alone-clean-outdoor` | **45** | 0 / 0 / 0 | 0 / 0 / 0, covered | 0 of 144 | complete |
| outdoor crowd (20261058) | `20261008T164736-demo-walk12-alone-crowd-outdoor` | **30** | 0 / 0 / 0 | 0 / 0 / 0, covered | 0 of 118 | complete |

Safety = `attack_request` / `npc_contact` / the GM's `act` (normal or pickup) in the manifest window.
walk@11 for comparison: 47 / 31 / 39 / 31, one NPC contact in each indoor run, and one UI click.
- **Decision 1, the work zone:** pixels refused 0 / 5 / 4 / 7; 9 cells left with no work-zone pixel
  (indoor clean); no rule click on a UI window.
- **Decision 2, the TALK-cell block:** 67 + 156 points refused unhovered and 18 + 43 attempts
  ended `covered_talk_cell` (indoor clean / crowd); no NPC contact anywhere.
- **Decision 3, the harness exit:** every run ended `complete` (no Stop, no exception, no interrupt).
  One indoor-clean route was interrupted by a human mouse move and is not scored (56 routes cover
  it).
- **Why the count fails** (the binding problem is now REFUSALS, Batt):

| cause | indoor clean | indoor crowd | outdoor clean | outdoor crowd |
|---|---|---|---|---|
| declined: unit stays (TALK cells or monsters in the envelope, patience out) | 2 | 7 | 1 | 13 |
| declined: no click point (stopped 1–3 cells short) | 3 | 1 | 1 | 0 |
| declined: /where limit | 2 | 0 | 0 | 0 |
| substituted a goal nobody had taken (an ENVELOPE refusal read as "taken") | 0 | 2 | 3 | 7 |

- **The 4 clicks that did not walk** (WALK read twice, a walkable cell picked, the click delivered:
  move / down / up in the input log, and NO request of any kind):
  - all 4 were the FIRST click of a route: 4 / 158 route-first clicks indoors, 0 / 55 outdoors,
    0 / 322 later clicks;
  - each came 14–35 s after the previous move;
  - one sat 2.5 px below a client-side SIGNBOARD (the wedding NPC's ring sign, drawn from client
    data; no packet: 0 desyncs in 16 h of prt_church replays);
  - the cause is OPEN. idle@1 (3.23) separates idle from chat typing before any fix.
- **Batt's decisions (2026-10-08 ~17:00):** the walk@13 direction is approved:
  - refused cells become temporary obstacles to re-plan around;
  - "goal taken" only when a unit stands ON the goal;
  - the idle test runs before any fix for the first-click failures.
  - The design proposal (walk@13) follows; it is pre-registered before any run.

### 3.22 rec@0b — what stops an attack ALREADY UNDER WAY (pre-registered 2026-10-08 ~15:10 ICT, BEFORE any run; Batt's approval of rec@0b with three adjustments)
**Why:**
- rec@0 (3.19) was INCONCLUSIVE: the C0 control continued in 2 / 8.
- The packets showed that its attack click rarely ENGAGED inside the 0.4 s before the cancel. The
  plant spawns up to 3 cells away (rAthena `@monster`: a random free cell within √n + 2 cells), so
  the client walked up first, or the click missed the small sprite.
- rec@0b makes the attack start AT ONCE, and only counts trials where it did.

**What changes from 3.19:**
1. **ADJACENT before the attack** (Batt).
   - `@monster` cannot place the plant on a given cell (pinned rAthena `atcommand.cpp`), so the GM
     walks next to it.
   - The plant's cell comes from pixels: the detector's foot point, then the picking model, with
     the GM's own cell known from the harness warp.
   - The GM walks to the neighbouring cell on its own side (a cursor-gated walk click: `walk` read
     twice), waits 1.5 s, and re-detects the plant.
   - A plant already adjacent skips the walk.
   - The attack click goes on the re-detected box CENTRE. If no plant is found, one more detection
     follows 0.5 s later.
2. **The cancel comes 0.8 s after the attack click**, so the first hit lands first: the request is
   immediate when adjacent, the first hit 0–245 ms after it (walk@11).
3. **The INCLUSION RULE, identical for every condition and judged OFFLINE from the packets:** a
   trial counts only if an `attack_request` AND the GM's first hit (act, kind normal) both fall
   between the attack click and the cancel time. For C0 the cancel time is the same 0.8 s mark,
   with no input.
4. **Attempts:** 25 per condition, seeded and interleaved (seed **20261064**), in one run.
   - A condition that ends with fewer than 10 included trials gets ONE top-up run of 15 more
     attempts of that condition (seed 20261065).
   - Below 10 even then, it is reported as "not enough engaged trials": inconclusive for that
     condition, never a pass.
   - **Reported per condition: the attempts made and the trials included.**
- **Unchanged from 3.19:**
  - the place: prt_fild08 (268,107), a fresh Red Plant (1078) per attempt;
  - the conditions C0–C4: the walks go AWAY from the plant, 2 / 6 cells; the Fly Wing is on F1;
  - the outcome measures: a trial SUCCEEDS with zero GM hits in [t_cancel + 0.3 s, t_cancel + 5 s]
    and zero `attack_request` after t_cancel;
  - the bar: ≥ 9 / 10 of a condition's included trials, AND C0 continued (≥ 2 hits) in ≥ 9 / 10
    of ITS included trials;
  - the tie-break: several passes → C2 over C3 over C4.
- **When:** after walk@12's tuning runs (Batt).

**RESULT (2026-10-08 18:11–19:06 ICT, session `20261008T181138-demo-rec0b`, seed 20261064): INCONCLUSIVE —
the ENGAGEMENT failed, so no cancel can be judged.** Included trials (an attack request AND the GM's
first hit before the cancel) were C0 0, C1 1, C2 1, C3 3, C4 1, each of 25. The control is not
proven, and every condition is under the bar's 10.

What the harness did (the trials' own fields, judged against the packets):

| step | trials of 125 |
|---|---|
| the plant NOT FOUND from pixels | 44 |
| found, walked adjacent, NO attack click | 28 |
| attack click made | 47 (+ 6 included) |

- **51 of the 53 attack clicks produced a MOVE request** within 3 s. The "attack the box centre"
  click landed on the FLOOR (a walk), not on the plant. Only 20 produced an `attack_request` (median
  1.18 s after the click) and 10 a first hit (median 0.92 s).
- **Not run:** the pre-registered top-up (15 per condition). At about 5 % engagement it could not
  reach 10 included in any condition. This deviation is reported here; Batt can ask for it.
- **What a fix needs (rec@0c, NOT adopted; Batt decides):**
  - re-find the plant AFTER the adjacent walk; the box was measured before it, and the plant's
    screen position changes as the camera follows the GM;
  - click only where the cursor reads the SWORD twice (the monster positive case's own rule), never
    a box centre;
  - find why the pixel finder missed the plant in 35 % of trials.

### rec@1 — DRAFT (NOT pre-registered): can a pending attack be cancelled DURING the walk-up?
**Why:**
- rec@0 stumbled on the real misclick case: a click on a monster a few cells away makes the
  client walk up BEFORE it attacks.
- If the walk-up can be cancelled, a misclick is recoverable before any hit lands. If it cannot,
  the click itself has to be prevented (walk@12's gates).

**The idea:**
- A static plant placed 3–4 cells away: the GM is warped there from the plant's picked cell.
- The attack click, then a cancel DURING the walk-up, 0.2–0.4 s after the click: before the
  character can arrive at 150 ms a cell.
- Candidates: a walk click away, sit, a Fly Wing, Esc.
- **Measured:** whether any hit lands at all, and whether the `attack_request` is followed by an
  arrival.
- **Control:** no cancel, so the walk-up and hits must follow.
- Its own pre-registration comes after rec@0b.

### 3.23 idle@1 — does the client drop the FIRST world click after idle, or after chat typing? (pre-registered 2026-10-08 ~18:10 ICT, BEFORE any run; Batt ~17:00: "run the deliberate idle test (15 s vs 2 s) before building any fix")

**Why:** walk@12 had 4 rule clicks that did not walk (WALK cursor read twice; a walkable cell picked;
the click delivered: move, down, up in the input log; NO request of any kind from the client):
- all 4 were the FIRST click of a route: 4 / 158 route-first clicks indoors, 0 / 55 outdoors, and
  0 / 322 later clicks;
- each came > 10 s after the previous move (14–35 s; later clicks 4–8 s);
- before a route's first click the harness types in the chat (the route-start GM command, the
  `/where` start fix), so IDLE and CHAT TYPING are confounded in walk@12's data;
- one of the 4 sat 2.5 px under a client-side signboard (a separate positive case, below).

**The test: 2 × 2, interleaved, one condition per trial in a seeded shuffled order.**

| condition | before the hover | then |
|---|---|---|
| T15 | type one chat line (`/where`, the rule's own typed line), close the chat | 15 s idle, no input |
| T2 | the same chat line | 2 s idle |
| N15 | no chat line | 15 s idle |
| N2 | no chat line | 2 s idle |

- **Where:** prt_church (where it happened), the GM at a fixed start cell; the target is a walkable
  cell 3 cells away in a seeded direction, inside the work zone, no TALK read, at least 40 px from
  any signboard (by the pixel detector, or the measured sign of route 31).
- **Each trial:** warp back to the start cell (a GM command), wait 3 s, then the condition's
  chat line or not, the idle, and the click EXACTLY as walk@12 makes it: the two-motion hover, the
  cursor read twice (WALK), the click at the read point.
  - The warp is typed in EVERY trial. So the T and N conditions differ by one extra chat line plus
    closing the chat, and the 15 / 2 s idle starts after the last input.
- **n = 30 per condition** (120 trials, ~45 min of client time), seed 20261066.
- **The outcome, judged offline from packets:** a `self_move_request` within 2 s of the click.
  Anything else is a FAILURE: no request, or another request.

**What decides** (pre-registered; walk@12's base rate is about 4 % of route-first clicks, so this is
deliberately a coarse screen):
- a factor is IMPLICATED when its two cells together have ≥ 2 failures and the other factor's
  level without it (N2) has 0;
- a fix is built only for an implicated factor (e.g. a fresh two-motion re-hover after typing or
  idle), and is pre-registered separately;
- 0 failures in all 120: no fix; the walk@12 cases stay unexplained and are reported as such, with
  the binomial upper bound for each cell.

**Display only, during the run** (Batt, 2026-10-08 ~18:50: HUD + route preview from the next run on):
- each trial's target is shown as a live route BEFORE the hover; no input is sent for it;
- the engine's walk and the HUD's line for the trial go out AFTER the click;
- nothing is published or sent between a WALK read and its click, and no input is sent during the
  idle. The harness was built with these before any run.

**Reported:** failures per cell with their exact 95 % upper bounds, each failure's frame before the
click (the recorder at 4 Hz), and the input log's move / down / up for it.

**Signboard positive case (same session, separate trials, n = 5 each):** clicks at 0 (inside),
2.5, 5 and 10 px below a signboard's measured bottom edge. A click inside is expected to produce no
move request, and one at 10 px a move. The edge of the hit area is the smallest distance that
walks in 5 / 5.

**RESULT (2026-10-08 19:19–20:03 ICT, session `20261008T191912-demo-idle1`, seed 20261066): 0 failures in
all 120 trials. No factor is implicated, so NO fix is built.**

| condition | clicked | walked (a move request within 2 s) | failed | 95 % upper bound on the failure rate |
|---|---|---|---|---|
| T15 (a chat line, 15 s idle) | 30 | 30 | 0 | 9.5 % |
| T2 (a chat line, 2 s idle) | 30 | 30 | 0 | 9.5 % |
| N15 (no chat line, 15 s idle) | 30 | 30 | 0 | 9.5 % |
| N2 (no chat line, 2 s idle) | 30 | 30 | 0 | 9.5 % |
| all | 120 | 120 | 0 | 2.5 % |

- Every target read WALK twice, and every click walked.
- Neither idling nor chat typing reproduces walk@12's route-first failures (about 4 % there). Those 4
  cases stay UNEXPLAINED, as pre-registered. walk@13 builds no first-click fix.
- The signboard positive case (the same pre-registration, separate trials) runs next on the free
  client.

**Signboard finder REPLACED before the positive case ran** (Batt, 2026-10-08 ~20:20, from his 20:10
HUD screenshot):
- `idle_click.sign_box` found a sign as the union of every pixel in the sign's orange. The church is
  full of those colours (floor, piano, robes, wood). It drew one giant "sign" over half the scene in
  194 of 224 banked walk@12 frames.
- Its users were the HUD scene (display) and this positive case, which had NOT run. walk@12's
  decision code never used it; idle@1's main trials used a fixed start, not the finder.
- The positive case had measured from the icon's bottom row: 4 px below the bar the clicks go under.
  The new `sign_box` returns the TITLE BAR, so the clicks are measured from the bar's bottom outline,
  as this pre-registration says ("a signboard's measured bottom edge"). This change is pre-run.
- **The replacement, `poring_env.signboard`:** a sign is found by its SHAPE.
  - Both parts, the icon square and the attached title bar, are UI-drawn: a 1-px black outline with
    a 1-px white halo.
  - The icon is 24–40 px with a mostly-orange frame. The bar is attached at the icon's right outline
    and filled with its brown and the title's white.
  - Nothing larger than 400 × 44 px is returned.
  - A sign inside a UI window is the window's.
  - With NPC detections (the HUD), an NPC must stand under the sign wherever one could be seen.
- **The proof** (`scripts/signboard_check.py`; client frames stay local):

| set | frames | signs found | what they are |
|---|---|---|---|
| prt_church, walk@11/12 route starts (lossless) | 223 | 47 | all the wedding NPC's sign: 160 × 32, pixels within 12.7 (mean abs diff) of the reference |
| prt_fild08, walk@11/12 route starts (lossless) | 224 | **0** | — |
| prt_church, route-demo recordings (JPEG) | 7,611 | 4,419 | all the wedding sign (diff ≤ 21.9; the 12 highest checked by eye: our own HP bar or a chat label over it) |
| prt_church, the HUD idle recording (JPEG) | 1,186 | **0** | — |
| prt_church, idle@1's recorder (JPEG) | 10,035 | 13 | the wedding sign, the 13 frames before idle@1's first warp |

- **An INDEPENDENT check: geometry, not pixels** (`signboard_check.py oracle`).
  - Method: the sign's NPC cell was fitted from the hits and the route start cells through the
    camera. It came out at (96, 101), with a worst residual of 5 / 12 px.
  - Then, for every one of the 223 church route starts, the camera says whether the sign must be in
    view:
    - 44 must be in view, and all 44 were found;
    - in 146 the sign is not in view, and nothing was found (**0 false signs**);
    - 33 are partly in view, or within 8 px of a UI window, and are not scored.
  - One sign the finder misses: the inventory window overdraws the icon's top outline (walk@12 crowd
    route 37).
  - A sign crossed by our own HP/SP bar IS found: a bar's left outline is the icon's right one.
- **The NPC rule** (`signboard_check.py npc`, v0 detector): it keeps 46 of the 47 real signs. The one
  it drops (walk@12 clean route 27) has its NPC plainly visible, but the detector missed it.
  - Measured: the NPC box's top is 93–102 px below the sign's bottom, centred (−8 … +10 px).
  - A sign whose NPC would stand off-screen or under a UI window is kept on its shape.
- The HUD scene runs the new finder since 20:40 (a display-only restart of `hud_scene.py`).

**Signboard positive case: RESULT** (2026-10-08 21:11–21:17 ICT / 14:11–14:17 UTC, session
`20261008T211125-demo-idle1-sign`, seed 20261067).
- **The setup:** the wedding NPC's sign, found live by the shape finder at the same place in all 20
  trials (bar `[630, 463, 758, 486]`).
- **Clicks:** at u = the bar's 66 %, after the two-motion hover. The cursor read WALK twice in every
  trial: over a sign, the client shows its plain arrow.

| click point | clicked | walked (a move request within 2 s) |
|---|---|---|
| inside the bar | 5 | **0** |
| 2.5 px below the bar's bottom outline | 5 | **0** |
| 5 px below | 5 | **0** |
| 10 px below | 5 | **5** |

- **The hit area's edge**, as pre-registered (the smallest distance that walks in 5 / 5): **10 px**
  below the outline. The sign swallows a click at least 5 px past its drawn outline, and the cursor
  gate cannot see it.
- **Safety:** 0 `npc_contact`, 0 `attack_request`, 0 acts from the GM in the session window. Clicking
  a sign does nothing.
- **This explains one of walk@12's 4 non-walking clicks:** the one 2.5 px under this sign (3.23,
  "Why"). The other 3 stay unexplained.
- **For walk@13:** the work zone excludes each sign's box grown by **12 px**: the measured 10 px
  edge + 2 px. The same margin is applied on all four sides; the top and sides were not measured.

### 3.24 walk@13 — walk@12 + REFUSALS BECOME ALTERNATIVES; TUNING (indoor/outdoor × CLEAN/CROWD), then the HELD-OUT set once (pre-registered 2026-10-08 ~21:50 ICT / 14:50 UTC at commit, BEFORE any run; Batt's direction approved ~17:00, overnight order ~21:05)
**Why:** walk@12 (3.21) had zero safety events in all four tuning runs. It failed the bar on
REFUSALS (43 / 40 / 45 / 30): `unit_stays`, `no_click_point`, and substitutes for goals nobody had
taken. The design proposal below lists them.

**The rule:** `scripts/walk13.py` at the commit of this pre-registration. It reuses walk@12's code:
- walk@12's click step and walk@11's / walk@12's harness are the SAME code objects, rebound so that
  they call walk@13's work zone, route loop, label and session log;
- `services/backend/tests/test_walk13.py` checks that, and that walk@12's module is untouched.

**The route loop is walk@11's, with exactly these changes:**
1. **Shorter points on the polyline.** After walk@11's candidates (the farthest in-band cell within
   seg_max, its neighbours, then the 4 FARTHER points) come up to **SHORTER = 4** nearer cells of the
   same plan, nearest last.
2. **Re-plan around refusals.** A round that clicks nothing puts its refused cells into a per-route
   BLOCKED set, and the route is planned again around them (`walk6.plan`), **at most 3 times per
   route**.
   - **Lifetimes:** a TALK cell (the NPC's own picked cells too) and a no-safe-point cell stay
     blocked for the route; a unit-envelope refusal for **8 s**, the unit memory's horizon.
   - The route's target is never blocked.
   - When no new plan exists, or 3 are used: walk@12's patience, substitute and decline.
3. **A nearby goal when the goal sits beside an NPC.** This is tried BEFORE the re-plan in a refused
   round.
   - **The trigger:** the goal cell, or a cell next to it, read TALK during the route.
   - **The new target:** the nearest walkable, reachable cell at Chebyshev distance **1–2** from the
     goal that is not next to any TALK cell (ring 1 first, the shortest plan first), recorded as
     `npc_substitute`. Once per route.
4. **"Taken" means a unit stands ON the target.** After patience, walk@8's substitute is used ONLY if
   a sighting in the unit memory, no older than **2 s**, has its feet picked ON the target cell.
   Otherwise the route declines `unit_stays`. walk@12 substituted on any unit envelope within one
   cell of the goal.
5. **Signboards leave the work zone.** Every candidate pixel inside a signboard's box grown by
   **12 px** is refused like a UI-window pixel (tier A first, tier B only if A has none).
   - The 12 px is the measured 10 px edge (the positive case above: 0/5 walked at 5 px, 5/5 at 10)
     + 2 px.
   - The signs come from `poring_env.signboard` (d5021f2: shape only, no NPC requirement, UI windows
     excluded) on a frame grabbed at each click step.
   - The portal click (walk@12's) is unchanged.
6. **No first-click fix** (idle@1: 0 failures in 120).

**Everything else is walk@12's:**
- the click-instant unit gate with its 8 s memory;
- the work zone (UI windows + 12 px) and the TALK-cell block;
- tiers A / B, the v3 cursor references and the detector (the same ONNX, confidence 0.25, IoU 0.5);
- the `/where` fixes (4 per route, trust for 3 clicks) and the scene-shift check;
- the harness exit (3 / 4 / 130);
- the live route preview and the operator HUD (display only).

**SAFETY instruments, all LIVE and proven by a deliberate positive case** (§2a; re-proven on the
17:51 sniffer at 21:08–21:11 ICT):
- `attack_request`, `npc_contact`, `pickup_request`, and the server's `act` from the GM (kinds normal
  and pickup), each counted inside the session's manifest window;
- the banked-capture replay re-checks every run afterwards.

**Scoring** (`demo_verify.py` at this commit):
- A route succeeds when the server puts the GM on the goal at its end.
- A route that ends on a walk@8 substitute succeeds only if another unit stood within one cell of
  the goal when the rule gave it up (walk@7 (b), unchanged).
- **NEW for change 3:** a route that ends on its `npc_substitute` succeeds only if the SERVER shows a
  drawn NPC (objtype 6, not a hidden class) within one cell of the goal at that moment. Otherwise it
  FAILS.
- Both kinds of substitute success are reported APART from plain arrivals.
- A strict count (every substitute a failure) is reported as well, but does not decide.

**TUNING runs, all four whatever the first scores:**
- Conditions as 3.14, with FRESH seeds: indoor clean **20261070**, indoor crowd **20261071**, outdoor
  clean **20261072**, outdoor crowd **20261073**.
- 56 routes each; the first 50 not interrupted are scored.
- e.g. `scripts/walk13.py --scene indoor --condition clean --seed 20261070 --label walk13-alone`.
- A harness exit that leaves fewer than 50 scored routes means the run is re-run unchanged with its
  seed; the partial session is kept, not scored.

**HELD-OUT runs**, ONCE, scored separately, never used to tune, **only if all 4 tuning runs PASS**:
- guild (alberta_in, the Merchant guild on the workflow route) **20261074**;
- town (prontera) **20261075**;
- dungeon (iz_dun00) **20261076**;
- portal (prt_fild08 → prontera) **20261077**.
- All CLEAN, `@heal` after each warp, 56 each, the first 50 scored.

**The bar (zero tolerance, unchanged):** ≥ **48 / 50** per run **AND** zero `attack_request`, zero
`npc_contact`, zero `act` from the GM of kind normal or pickup, in the run's window. Any one is a
HARD FAIL.

**If a tuning run fails** (Batt, overnight order): diagnose; at most 2 more design iterations tonight
(walk@14 / walk@15), each pre-registered before it runs.

**Reported:** 3.21's items, plus:
- per change, how often it acted: shorter points clicked, re-plans (and the cells blocked), NPC
  substitutes (and whether the server shows an NPC), taken checks (ON the target or not), sign
  refusals;
- the remaining declines by cause.

**3.24 run log (kept as written):**
- **21:22 ICT / 14:22 UTC, indoor CLEAN attempt 0** (session `20261008T212248-demo-walk13-alone-clean-indoor`):
  STOPPED by Claude with SIGTERM before its first route (0 routes). The harness finished the session
  (exit 130). It is kept and NOT scored.
  - **Why:** the client's INVENTORY window was still open, left by the pickup positive case
    (`safety_signal_check.py pickup-start` opens it; nothing closed it).
  - That is not the pre-registered UI state. The window reaches past the work zone's grown
    basic-information rectangle (a strip at x 232–280, y 338–375 client px), where a rule click could
    land on it. It also covered the weight readout, which voided the 21:17 weight-digit run.
  - **Fix:** the window was closed (Alt+E, screenshot-checked) and the run restarted UNCHANGED with
    its seed at 21:26 ICT. `pickup-click` now closes the window it opened.

**3.24 walk@13 RESULTS (scored as pre-registered; all four tuning runs FAIL the bar → no held-out run).
ZERO safety events in every run.**

| run | seed | session | success / 50 | walk@12 | failures |
|---|---|---|---|---|---|
| indoor CLEAN | 20261070 | `20261008T212700-…-clean-indoor` (21:27–22:07 ICT) | **46** (1 an NPC substitute, justified) | 43 | `unit_stays` 2, `no_click_point` 2 |
| indoor CROWD | 20261071 | `20261008T220741-…-crowd-indoor` (22:07–23:13) | **40** (2 NPC substitutes, justified) | 40 | `no_click_point` 6, `relocalise_limit` 2, `unit_stays` 1, an NPC substitute the server did not justify 1 |
| outdoor CLEAN | 20261072 | `20261008T231320-…-clean-outdoor` (23:13–23:52) | **45** | 45 | `unit_stays` 4, `no_click_point` 1 |
| outdoor CROWD | 20261073 | `20261008T235223-…-crowd-outdoor` (23:52–00:35) | **41** | 30 | `unit_stays` 7, `relocalise_limit` 1, `no_click_point` 1 |

- **SAFETY:** 0 `attack_request`, 0 `npc_contact`, 0 acts from the GM (normal or pickup) in all four
  windows.
- **Strict count** (every substitute a failure): 45 / 38 / 45 / 41.
- **How often each change acted:**

| change | indoor clean | indoor crowd | outdoor clean | outdoor crowd |
|---|---|---|---|---|
| 2: re-plans (routes) | 5 (3) | 30 (19) | 21 (10) | 23 (11) |
| 3: NPC substitutes | 1 | 3 | 0 | 0 |
| 4: taken checks, nobody ON the target | 2 / 2 | 1 / 1 | 4 / 4 | 7 / 7 |
| 5: steps with a sign in view | 66 | 163 | 0 | 0 |

- **Diagnosis** (offline, from the packets; the scratch scripts are named in 3.25):
  - **Indoor CLEAN:** all 29 monster refusals had no monster on the server. An NPC is read as a
    monster at (87, 127) / (95, 127).
  - **The `no_click_point` routes:** the target's own points were refused for non-unit reasons.
  - **Outdoor `unit_stays`:**
    - At the decline, no monster stood within 2 cells of the goal.
    - Of 207 refusals (clean) and 334 (crowd), the nearest real monster was ≤ 1 cell from the
      refused cell in 2 and 19.
    - The gate refuses within its 4–5-cell radius for prt_fild08's fastest species (200 ms per
      cell). Aged sightings reach 44 cells.
    - The patience step waited only 0.5–1 s: each refusal round itself takes seconds.
- **walk@14 (3.25) addresses the first two causes. It does not change the gate.**

### 3.25 walk@14 — walk@13 + STATIC UNITS, SIDE APPROACH, UNKNOWN READS RE-PLANNED; TUNING, then the HELD-OUT set once (pre-registered 2026-10-09 ~00:20 ICT / 2026-10-08 17:20 UTC at commit, BEFORE any run; Batt's overnight order: "If it fails: diagnose, at most 2 more design iterations tonight (walk@14/15), each pre-registered")
**Why: walk@13's diagnosed failures** (3.24 results below; zero safety events in every run).

| run | score | failures |
|---|---|---|
| indoor CLEAN | 46 / 50 | `unit_stays` 2, `no_click_point` 2 |
| indoor CROWD | 40 / 50 | `no_click_point` 6, `relocalise_limit` 2, `unit_stays` 1, an NPC substitute the server did not justify 1 |
| outdoor CLEAN | 45 / 50 | `unit_stays` 4, `no_click_point` 1 |

1. **An NPC read as a monster.**
   - In indoor CLEAN, **all 29** monster-envelope refusals had NO monster on the server. The NPCs
     there are Pastor#1011 (87, 127) and Crusader (95, 127).
   - A monster's envelope (radius 3 at 400 ms per cell) on an NPC that never moves blocked goals
     (90, 126) / (89, 127) / (91, 127) for 67–95 s, through 3 re-plans and patience.
2. **The TARGET's own points refused for a non-unit reason.** This is 5 of crowd's 6
   `no_click_point` routes and clean's 2: `recheck_unknown`, `covered_unknown`, `no_safe_point`,
   `recheck_walk` at the goal.
   - The route stopped 1–2 cells short. walk@13 never re-plans its target.
3. **Cells read UNKNOWN were not re-planned around** (crowd route 0: two unknown reads at its start,
   then a decline). walk@13 put only talk / unit / no-safe-point cells into the blocked set.
4. **NOT addressed:**
   - **Outdoor `unit_stays` near the field's own monsters** (prt_fild08's fastest species, 200 ms per
     cell, gives the gate a 4–5-cell radius). Only 2 of 207 refusals had a monster within 1 cell of
     the refused cell; most had one 4–6 cells away. The gate's conservatism is what holds the zero
     attacks: **it is NOT changed.**
   - `relocalise_limit`.

**The rule:** `scripts/walk14.py` at the commit of this pre-registration = walk@13 UNCHANGED (its click
step with the sign mask, its route-loop changes 1–4, the harness; the same code objects or a copy of
its route loop) plus exactly:
- **A. A static unit keeps a small envelope.**
  - A sighting that has stayed within **1** cell of where its streak began, for **≥ 8 s** over
    **≥ 3** sightings, gets radius **1** instead of the growing radius.
  - rAthena's monsters pause ≤ 5 s between moves (walk11's `PATIENCE_S`). A unit still for 8 s is
    an immobile monster, an NPC read as a monster, or scenery.
  - Its own box (+ 12 px) is still refused. Radius 1 covers one step within the click latency.
  - The memory's matching and TTL are walk@11's, copied exactly.
- **B. Approach the target from another side.**
  - **When:** a round clicks nothing and the TARGET's own points were refused for a non-unit reason
    (no safe point, a re-check read, an unknown or unconfirmed read).
  - **What:** the rule first walks to a SIDE cell, Chebyshev **1–2** from the target, that is
    walkable, reachable, not next to a TALK cell and not where we stand. From it, the target must
    have work-zone points: tier A, else B, by the picking model. The shortest plan comes first.
  - **Limits:** at most **2** per route, tried before walk@13's NPC substitute, re-plan, patience and
    decline.
- **C. A cell refused by an unknown or re-check read** joins the per-route blocked set, like walk@13's
  no-safe-point cells (not a unit, not TALK), so the re-plan goes around it.

**SAFETY instruments, scoring, the bar:** as 3.24, unchanged.
- **The bar:** ≥ 48 / 50 per run AND zero `attack_request`, zero `npc_contact`, zero `act` from the
  GM of kind normal or pickup. Any one is a HARD FAIL.
- **Scoring:** the NPC substitute counts only with a drawn NPC beside the goal on the server. A
  strict count is reported apart.

**TUNING runs, all four whatever the first scores:**
- FRESH seeds: indoor clean **20261080**, indoor crowd **20261081**, outdoor clean **20261082**,
  outdoor crowd **20261083**.
- 56 routes each; the first 50 not interrupted are scored.
- e.g. `scripts/walk14.py --scene indoor --condition clean --seed 20261080 --label walk14-alone`.

**HELD-OUT, ONCE, only if all 4 PASS:** guild (alberta_in) **20261084**, town (prontera)
**20261085**, dungeon (iz_dun00) **20261086**, portal (prt_fild08 → prontera) **20261087**. All CLEAN,
`@heal` after each warp, 56 each, the first 50 scored.

**Expected** (Claude's reading of walk@13's numbers; NOT a bar):
- indoor CLEAN gains its 4;
- indoor CROWD gains most of its `no_click_point`;
- outdoor CLEAN / CROWD still FAIL on `unit_stays` near native monsters (item 4).

**Reported:** 3.24's items, plus static units (sightings that went static, and refusals avoided),
side approaches (tried, reached, and the goal clicked from the side), and cells blocked by unknown
reads.

**3.25 walk@14 run log** (the full results follow when all four runs end):
- **indoor CLEAN** (`20261009T004436`, 00:44–01:25 ICT): 47 / 50, but **1 `npc_contact` → HARD FAIL**.
  - Route 44 clicked cell (97, 101) from (94, 100). 0.17 s later the client contacted
    "Wedding Staff#w" (gid 110002354), which stands on (97, 100): ONE cell away.
  - Before the click: the cursor read WALK twice, the marker named the cell, tier A, and the gate's
    nearest NPC box was 18.9 px away (≥ 12 margin; an NPC's radius is 0).
  - That route used no walk@14 change (no side approach, no static unit). The click step is
    walk@13's, unchanged since walk@12.
- **indoor CROWD** (`20261009T012518`, 01:25–02:27): 44 / 50, but **1 `npc_contact` → HARD FAIL**.
  - Route 52 clicked cell (108, 125) from (103, 121). 0.20 s later the client contacted "Nun#prt"
    (gid 110001758), which stands on (108, 124): ONE cell away.
  - Before the click: WALK twice, the marker named the cell, and the nearest NPC box was 17.6 px
    away. Again no side approach and no static unit.
- **The mechanism is the same both times:** a click on a cell NEXT TO an NPC, 17–19 px from its
  detected box, contacts it, although the cursor read WALK at that point.
- **Not proven, two hypotheses:** an idle animation frame larger than the hover frame, or a detector
  box smaller than the sprite.
- **Exposure:** walk@11–13 had 0 contacts in 12 runs, with the same click step. Whether walk@14's
  re-routing made such clicks more frequent is not separable from two runs.

**3.25 walk@14 RESULTS (scored as pre-registered).** Two runs are HARD FAILS (an NPC contact each),
one PASSES, and one fails by count. Not all four pass, so there is no held-out run.

| run | seed | session | success / 50 | walk@13 | safety | verdict | failures |
|---|---|---|---|---|---|---|---|
| indoor CLEAN | 20261080 | `20261009T004436` (00:44–01:25 ICT) | 47 (1 NPC substitute, justified) | 46 | **1 `npc_contact`** | **HARD FAIL** | `no_click_point` 1, `relocalise_limit` 1, `relocalise_failed` 1 |
| indoor CROWD | 20261081 | `20261009T012518` (01:25–02:27) | 44 | 40 | **1 `npc_contact`** | **HARD FAIL** | `unit_stays` 5, `no_click_point` 1 |
| outdoor CLEAN | 20261082 | `20261009T022711` (02:27–02:57) | **49** | 45 | 0 | **PASS** | `unit_stays` 1 |
| outdoor CROWD | 20261083 | `20261009T025754` (02:57–03:43) | 44 | 41 | 0 | FAIL | `unit_stays` 6 |

- **How often each change acted:**

| change | indoor clean | indoor crowd | outdoor clean | outdoor crowd |
|---|---|---|---|---|
| A: gate reads with a static radius-1 unit | 3 | 16 | 12 | 14 |
| B: sides tried / reached / that route a success | 3 / 3 / 1 | 1 / 1 / 1 (2 none found) | 0 | 3 / 1 / 1 |
| re-plans (routes) | 1 (1) | 26 (18) | 5 (5) | 24 (14) |

- **The NPC contacts** are described in the run log above. Both clicks went to a cell next to an
  NPC. walk@15 (3.26) addresses them.
- **Count:** walk@14 beats walk@13 in all four conditions (+1 / +4 / +4 / +3).
- **Remaining failure causes, ranked:**
  1. outdoor `unit_stays` near native monsters (7);
  2. indoor crowd `unit_stays` (5);
  3. `relocalise_*` (2);
  4. a goal that reads "unknown" from every side (1).

### 3.26 walk@15 — walk@14 + NPC CLEARANCE + side cells never where we stood (pre-registered 2026-10-09 ~02:35 ICT / 2026-10-08 19:35 UTC at commit, BEFORE any run; the second and last design iteration tonight, Batt's overnight order)
**Why:** the two NPC contacts above. Both clicks went to a cell adjacent to an NPC, and walk@14's
gate gave an NPC radius 0 (its box + 12 px). Also, walk@14 indoor CLEAN route 25 tried, as its
second side cell, the cell it had just come from.

**The rule:** `scripts/walk15.py` at the commit of this pre-registration. It is walk@14 UNCHANGED:
its route loop and its memory are the same code, rebound. The changes are exactly:
- **D. NPC clearance:** an NPC sighting's envelope has radius **1** (it was 0).
  - The NPC's box is moved onto each neighbouring cell, + walk@11's 12 px margin, so no click point
    picks a cell next to a detected NPC.
  - NPCs do not move: walk@13's re-plan and walk@14's side approach route around the refusal.
  - Monsters and players keep walk@14's radii.
- **E.** A side cell is never a cell this route has stood on.

**Scoring, instruments, the bar:** as 3.24 / 3.25, unchanged.
- **The bar:** ≥ 48 / 50 AND zero `attack_request`, `npc_contact`, and GM acts (normal or pickup)
  per run.

**TUNING runs, all four whatever the first scores:**
- FRESH seeds: indoor clean **20261090**, indoor crowd **20261091**, outdoor clean **20261092**,
  outdoor crowd **20261093**.
- 56 routes each; the first 50 not interrupted are scored.
- e.g. `scripts/walk15.py --scene indoor --condition clean --seed 20261090 --label walk15-alone`.

**HELD-OUT, ONCE, only if all 4 PASS:** guild (alberta_in) **20261094**, town (prontera)
**20261095**, dungeon (iz_dun00) **20261096**, portal (prt_fild08 → prontera) **20261097**. All CLEAN,
`@heal` after each warp, 56 each, the first 50 scored.

**Expected** (Claude's reading; NOT a bar):
- zero NPC contacts;
- indoor refusals near NPCs rise (the TALK clusters), recovered in part by re-plans and side
  approaches;
- outdoor still fails on `unit_stays` near native monsters (3.25, item 4: not addressed).

**3.26 walk@15 RESULTS (scored as pre-registered).** ZERO safety events in all four runs: change D
held. Two runs PASS and two fail by count. Not all four pass, so there is no held-out run. walk@15
was the second and last design iteration of the night.

| run | seed | session | success / 50 | walk@14 | safety | verdict | failures |
|---|---|---|---|---|---|---|---|
| indoor CLEAN | 20261090 | `20261009T034716` (03:47–04:30 ICT) | 46 | 47* | 0 | FAIL | `unit_stays` 2, `relocalise_limit` 1, an NPC substitute the server did not justify 1 |
| indoor CROWD | 20261091 | `20261009T043033` (04:30–05:36) | 43 (2 NPC substitutes, justified) | 44* | 0 | FAIL | `relocalise_limit` 3, `unit_stays` 3, `no_click_point` 1 |
| outdoor CLEAN | 20261092 | `20261009T053701` (05:37–06:09) | **49** | 49 | 0 | **PASS** | `unit_stays` 1 |
| outdoor CROWD | 20261093 | `20261009T060936` (06:09–06:52) | **48** | 44 | 0 | **PASS** | `unit_stays` 2 |

\* walk@14's indoor runs were HARD FAILS (an NPC contact each).

- **The trade, as expected:** no contacts, at a cost. walk@15 refuses NPC-adjacent cells through the
  gate's envelope, but walk@13's NPC substitute triggers only on a TALK READ. So a goal beside an
  NPC now declines `unit_stays` (indoor CLEAN route 0: goal (110, 124) in the NPC cluster) instead
  of moving to a nearby cell.
  - **Next version (NOT adopted, not pre-registered):** an NPC-envelope refusal on or next to the
    goal should trigger the NPC substitute too. ➡️ ADOPTED by Batt 2026-10-09 ~08:30 as walk@16
    (3.27, pre-registered; NPC within ONE cell of the goal, the verifier's rule).
- **Remaining failure causes over walk@15's four runs, ranked:**
  1. `unit_stays` (8: indoor near NPCs, outdoor near native monsters);
  2. `relocalise_limit` (4, indoor);
  3. `no_click_point` (1);
  4. an unjustified NPC substitute (1).
- **Counter caveat:** the scorer's "static radius-1" count also counts NPC envelopes under D (241 /
  485 indoor). It is not a measure of change A in walk@15.

### 3.27 walk@16 — walk@15 + an NPC-ENVELOPE REFUSAL AT THE GOAL TRIGGERS THE NPC SUBSTITUTE; TUNING, then the HELD-OUT set once (pre-registered 2026-10-09 ~08:45 ICT / 01:45 UTC at commit, BEFORE any run; Batt 2026-10-09 ~08:30: "walk@16 approved: an NPC-envelope refusal at the goal triggers the nearby-cell substitute (still judged by the server). Pre-register; then, if all four tuning runs pass, the held-out set once.")
**Why:** 3.26's trade. walk@15's NPC clearance (D) refuses a goal BESIDE an NPC through the unit
gate's envelope, but walk@13's NPC substitute triggers only on a TALK cursor read. Such a goal
waits out its patience and declines `unit_stays` (walk@15 indoor CLEAN route 44: goal (95, 126), the
server's "Crusader" one cell away, the gate's nearest box an NPC at 0.0 px three times).

**The rule:** `scripts/walk16.py` at the commit of this pre-registration. It is walk@15 UNCHANGED
(walk@14's route loop rebound, walk@15's memory, side cells and visited set; the same code). The
change is exactly:
- **F.** When the click step refuses the route's GOAL (its own points, walk intent, before any
  substitute) with `covered_unit_envelope` and the gate's nearest unit is an NPC, every remembered
  NPC sighting within **1** cell of the goal (`NPC_SUB_NEAR`) joins the route's TALK set, as if its
  cell had read TALK.
  - walk@13's NPC substitute then runs exactly as for a TALK read: ring 1, then 2, never on or next
    to a TALK/NPC cell, the shortest plan first.
  - An NPC sighting 2 cells away does NOT trigger it: the verifier counts an NPC substitute only with
    a drawn NPC within one cell of the goal on the server (`demo_verify.npc_near`, walk@13; unchanged).
  - A refused waypoint (not the goal) and a monster envelope keep walk@15's handling.
  - The step's record carries `npc_envelope_talk` (the NPC cells used) whenever F fires.

**Scoring, instruments, the bar:** as 3.24–3.26, unchanged.
- **The bar:** ≥ 48 / 50 AND zero `attack_request`, `npc_contact`, and GM acts (normal or pickup)
  per run.
- An NPC substitute counts as a success only when the server confirms a drawn NPC within one cell of
  the goal; otherwise it is a failure ("npc_substitute with no NPC beside the goal").

**TUNING runs, all four whatever the first scores:**
- FRESH seeds: indoor clean **20261100**, indoor crowd **20261101**, outdoor clean **20261102**,
  outdoor crowd **20261103**.
- 56 routes each; the first 50 not interrupted are scored.
- e.g. `scripts/walk16.py --scene indoor --condition clean --seed 20261100 --label walk16-alone`.
- Before each run: a screenshot of the client, and any leftover window closed (the inventory
  incident of 3.24).

**HELD-OUT, ONCE, only if all 4 PASS:** guild (alberta_in) **20261104**, town (prontera)
**20261105**, dungeon (iz_dun00) **20261106**, portal (prt_fild08 → prontera) **20261107**. All CLEAN,
`@heal` after each warp, 56 each, the first 50 scored, reported apart from tuning.

**Expected** (Claude's reading; NOT a bar), from walk@15's four TUNING sessions replayed offline
(`walk16/diag15.py`; tuning data only, the held-out maps never looked at):
- F would have applied to **one** indoor CLEAN failure (route 44, the NPC one cell from the goal) and
  at most one indoor CROWD failure (route 35, "Sister Linus" one cell away; that route declined on
  `relocalise_limit` first).
- Two other NPC-envelope declines had the NPC **2** cells from the goal (CLEAN route 0, "Nun";
  CROWD route 18, "Wedding Staff"). F does not apply to them; they stay `unit_stays`.
- So F alone is expected to add about +1 route per indoor run (CLEAN ≈ 47, CROWD ≈ 43–44): **indoor
  is NOT expected to reach 48 on F alone.** The remaining indoor causes are `relocalise_limit` (4
  over the two runs), the 2-cell NPC goals (2), monster envelopes indoors in CROWD (2), unknown reads
  (1), and a TALK-triggered substitute the server did not justify (1).
- Outdoor: no NPCs, so F never fires there; walk@15's outdoor passes (49, 48) were near the bar,
  and run-to-run spread has been ±3.
- Risk: a remembered NPC cell comes from pixels (belief + the pick under its feet). If it is one cell
  off, F can fire for an NPC really 2 cells away, and the server will score that substitute a
  failure.

**3.27 walk@16 RESULTS (scored as pre-registered; 2026-10-09 08:41–11:55 ICT).** ZERO safety events
in all four runs. One run PASSES the per-run bar and three fail by count. Not all four pass, so there
is no walk@16 held-out run (3.27's own rule).

| run | seed | session | success / 50 | walk@15 | safety | verdict | failures |
|---|---|---|---|---|---|---|---|
| indoor CLEAN | 20261100 | `20261009T084142` (08:41–09:31 ICT) | 43 (2 NPC substitutes, justified) | 46 | 0 | FAIL | `no_click_point` 2, `unit_stays` 2, an NPC substitute the server did not justify 2, `relocalise_limit` 1 |
| indoor CROWD | 20261101 | `20261009T093115` (09:31–10:41) | 40 (2 NPC substitutes, justified) | 43 | 0 | FAIL | `unit_stays` 4, `relocalise_limit` 3, `no_click_point` 2, unjustified NPC substitute 1 |
| outdoor CLEAN | 20261102 | `20261009T104128` (10:41–11:11) | **49** | 49 | 0 | **PASS** | `unit_stays` 1 |
| outdoor CROWD | 20261103 | `20261009T111132` (11:11–11:55) | 47 | 48 | 0 | FAIL | `no_click_point` 1, `relocalise_limit` 1, `unit_stays` 1 |

- **Change F fired 3 times.**
  - Indoor CLEAN, once: a server-justified NPC substitute, and the route a success.
  - Indoor CROWD, twice: the substitute was chosen, and its own route then declined `unit_stays`.
  - Outdoors never (no NPCs), as expected.
  - The unjustified substitutes all came from TALK reads (walk@13's path, unchanged).
- As stated before the runs, F alone did not lift indoor to the bar: indoor went 46 → 43 and
  43 → 40, within the ±3 run-to-run spread seen since walk@13.
- **Failure causes over the four runs, ranked:**
  1. `unit_stays` 8;
  2. `relocalise_limit` 5;
  3. `no_click_point` 5;
  4. unjustified NPC substitutes 3 (TALK-read path).
- **READINESS (3.28):** pooled **179 / 200 = 89.5 %** (95 % CI 84.5–93.0 %), 0 safety events:
  **NOT READY** (under 90 %).

- **Disclosure: test connections during indoor CROWD** (found 2026-10-09 ~12:40 by a subagent).
  - At 10:20 and 10:33 ICT (03:20 / 03:33 UTC), test suites run on the host opened agent links to
    the LIVE backend: `test_walk12`'s `operator_hud.enable()` built a real `ro_agent.Agent`
    ("operator-hud" hellos in the live input log).
  - The input log shows no input from them and no release of any kind. The run's own input pattern
    (its clicks and its typing) continued unchanged around them.
  - What they could reach was display only (HUD / route-preview feeds), which the rule never reads.
    The result stands.
  - Fixed in a9a11ec: the tests' conftest refuses any non-loopback WebSocket connection.

**3.29's version choice, applied mechanically after walk@16's tuning (2026-10-09 11:57 ICT, before
any held-out data):**
- walk@15 is READY (186 / 200 = 93.0 %, 0 safety).
- walk@16 is NOT READY (179 / 200 = 89.5 %).
- ⇒ **the held-out set runs walk@15** (`scripts/walk15.py` at e1299f5's rule; its harness is
  unchanged since: walk@15's import graph was checked before each merge today).

### 3.28 WALKING READINESS — a definition, "good enough to build on" (Batt 2026-10-09 ~09:40; it changes NO past pre-registered verdict)
**Batt (2026-10-09):** "Walking readiness ('good enough to build on'): zero safety events (hard) AND
pooled success >= 90 % with its 95 % CI, over the four tuning conditions. 96 % stays the long-term
target."

**The definition, exactly** (`scripts/walk_readiness.py`):
- A walk version is **READY** when, over its four TUNING runs (indoor/outdoor × clean/crowd, the
  first 50 scored routes each, n = 200 pooled), both hold:
  1. **ZERO safety events** in all four runs: `attack_request`, `npc_contact`, and GM acts normal
     or pickup. Any one event means NOT ready, whatever the success.
  2. **The pooled success rate is ≥ 90 %**, reported with its 95 % Wilson score interval.
- **Claude's reading, stated so Batt can correct it before any held-out data:** the 90 % applies to
  the POOLED POINT ESTIMATE, and the interval is reported with it, not required to clear 90 %.
  ➡️ **CONFIRMED by Batt 2026-10-09 ~10:30 (before any held-out data): "interpretation A is what I
  meant: the pooled POINT estimate >= 90 % with zero safety events, the Wilson CI reported next to
  it (not the lower bound). walk@15 qualifies."**
  The stricter reading (the interval's LOWER bound ≥ 90 %) is computed and reported too
  (`ci_lower_bound_ge_ready`). At n = 200 it needs about 190 / 200.
- **96 %** stays the long-term target (`target_met`, reported).
- The per-run bar of each pre-registration (≥ 48 / 50 per run) is unchanged, and so are the verdicts
  already given under it: walk@13–15's FAILs stay FAILs as pre-registered. Readiness is a separate,
  pooled question.

**PER-MAP WALK-READINESS (Batt 2026-10-09 ~13:15, approved):** a map is **walk-ready** only when
both hold:
- the version is READY (above);
- EVERY species the map's L3 spawn list holds is in the unit detector's TRAINING SCOPE (ADR-0020
  13.3: the training scope = all species on the workflow's maps).

The detector is class-agnostic ("monster"), but it only knows the sprites it was trained on. On a map
whose species it never saw, the unit gate cannot protect walking.
- **Today's scope:** v0 / v1 were trained on prt_fild08 and prt_church sessions only.
- **iz_dun00** spawns Plankton, Marina, Kukre, Hydra, Vadon and Black Mushroom (the local KB): all out
  of scope. So iz_dun00 is NOT walk-ready, and its held-out result (3.29) is reported as
  **PATH-FOLLOWING ONLY, not unit safety** (Batt). Its safety count is still reported.
- A held-out map's own walk-ready status is stated next to its result.
- ➡️ **AMENDED (Batt 2026-10-09 ~16:10, his 16:04 screenshot): a THIRD condition, the map's NPC
  SPRITES.** "The detector does NOT box the town NPCs at all ... v0/v1 never trained on town NPC
  sprites ... per the walk-ready rule, a map is not walk-ready while its NPC sprites are outside the
  detector's training scope."
  - So prontera, alberta and every town are NOT walk-ready today. The two town contacts of 3.29a had
    "0 units in the envelope": the detector was blind there; the gate was not wrong.
  - Measured in walk@17 item 5's targeted test: the detector's recall on town NPCs against packet
    truth, per NPC sprite.
  - Batt ~16:15 added a detector-independent layer for walk@17: the L3 NPC cells (and their
    clickable footprint) as static NO-CLICK cells (3.32 item 5). Whether that layer alone removes the
    town contacts is measured. If it does, whether this third condition still binds the walk-ready
    status is Batt's call; until then it binds.

**Applied to the tuning runs so far** (`walk_readiness.py` over each version's four scorer outputs):

| version | per run (IC / ICr / OC / OCr) | pooled | 95 % CI | safety | READY | lower bound ≥ 90 % |
|---|---|---|---|---|---|---|
| walk@13 | 46 / 40 / 45 / 41 | 172 / 200 = 86.0 % | 80.5–90.1 % | 0 | no (< 90 %) | no |
| walk@14 | 47 / 44 / 49 / 44 | 184 / 200 = 92.0 % | 87.4–95.0 % | **2** (NPC contacts) | **no** (safety) | no |
| walk@15 | 46 / 43 / 49 / 48 | 186 / 200 = 93.0 % | 88.6–95.8 % | 0 | **YES** | no |
| walk@16 | 43 / 40 / 49 / 47 | 179 / 200 = 89.5 % | 84.5–93.0 % | 0 | no (< 90 %) | no |
| walk@17 | pre-registered (3.32), not run | — | — | — | — | — |

### 3.29 walk HELD-OUT under the readiness bar — once, per map, with the best READY version (pre-registered 2026-10-09 ~09:45 ICT / 02:45 UTC at commit, BEFORE any held-out data; Batt 2026-10-09: "Held-out maps NEXT, once, with the best qualifying version: pre-register NOW (before any held-out data) with the new bar, scored separately per map")
**The version (decided by TUNING data only):** among walk@15 and walk@16, the READY version (3.28)
with the higher pooled tuning success. On a tie, walk@16 (walk@15 + Batt's approved F). walk@15 is
READY now. walk@16's tuning runs finish untouched first (3.27), then the choice is applied
mechanically, and stated with its numbers before the first held-out run starts.

**The maps, each run ONCE** (in this order, all CLEAN as the earlier held-out plans: `@heal` after
each warp, 56 routes, the first 50 not interrupted scored):

| scene | map / start | what it adds | seed |
|---|---|---|---|
| guild | alberta_in (60, 40): the Merchant Guild room, on the workflow route (L3 NPC at 53, 43) | a new interior, NPCs | **20261120** |
| town | prontera (156, 180) | a town: NPCs, other players' chat rooms if any (the 17:51 sniffer's length table decodes them) | **20261121** |
| dungeon | iz_dun00 (168, 168) | a dungeon: its own monsters respawn | **20261122** |
| portal | prt_fild08 (170, 368) → the north portal (170, 378) → prontera (156, 26) | the cross-map portal walk (the route must END on prontera) | **20261123** |

These seeds are fresh: 3.26's and 3.27's reserved held-out seeds (20261094–97, 20261104–07) stay
unused.

**The bar, PER MAP, scored separately** (the 3.28 arithmetic on n = 50):
- zero safety events (hard), AND
- success ≥ 45 / 50 (90 %), with its 95 % Wilson interval reported (and whether its lower bound
  clears 90 %).
- A pooled held-out number over the four maps is reported too, with no verdict attached.

**Scoring:** the version's own scorer (`walk15_score.py` / `walk16_score.py`: demo_verify + the
packets, the same instruments as tuning) per map, then `walk_readiness.py` on each map's output.

**Once means once:**
- No map is re-run, and no held-out result tunes anything.
- A run that ENDS EARLY on an infrastructure failure (client crash, disconnect, guard stop) before
  50 scored routes is reported as INCOMPLETE with its routes so far. It is not re-run without
  Batt's word.

**Before each run:** a client screenshot, and the UI as pre-registered (3.24's inventory incident).

### 3.30 talk@1 — talk to an NPC, choose a menu option BY ITS TEXT, close the dialog (pre-registered 2026-10-09 ~10:00 ICT / 03:00 UTC at commit, BEFORE any trial and before its prerequisites are built; Batt 2026-10-09: "Then the next skill: talk_npc + choose_menu + close_dialog. Design and pre-register talk@1")
> ➡️ **DECIDED (Batt, 2026-10-13, decision 4):** "talk@1: approach with the minimap-first walk
> (walk@17 design), no /ex." talk@1's approach step no longer calls walk@15 (it types "/ex" + /where,
> refused by the typing policy). The rework is pre-registered before any scored trial.
> ➡️ **AMENDMENT, BUILT 2026-10-13, before any scored trial** (`talk1.py`; `test_talk1.py`):
> - **The approach:** `--walk walk17` is the default. It is walk@17's route, with B (warp areas)
>   loaded for the map, its /where state reset, and a run budget of (WHERE_PER_ROUTE + 1) x n opened
>   in the typing guard.
> - **The contact fix:** `--contact-fix relocalise` is the default. It is walk@17's own
>   relocalisation: the minimap readout first, /where (where@3) once per need, never "/ex".
> - where@2's fix (`--contact-fix where`) is REFUSED with walk17. `walk15` / `walk16` stay selectable
>   only as the old options.
> - **Stated for the scoring:** walk@17's own tuning runs have not run yet (its readiness is unknown),
>   so talk@1 reports approach failures apart from contact and dialog failures, as 3.30 already
>   does. Everything else in 3.30 is unchanged.
**What it verifies:** the L1 concepts `npc.talk`, `npc.next`, `npc.choose` and `npc.close` on RDP.
When talk@1 PASSES, the /flows blocks `talk_npc`, `next_page`, `choose_menu` and `close_dialog`
become "verified RDP" (the L1 entries' `verified_on` gets the RDP session). The S2 re-test comes
later.

**The targets (L3, static server data; the pinned rAthena, generated locally, never committed):**

| scene | NPC (L3 name, cell) | its first menu (L3, the script's `select`; the strings stay in the local L3 data, GPL-derived, never quoted here) | the options a trial may pick |
|---|---|---|---|
| prt_church | Garnet (103, 76) | 7 options: six that explain an acolyte skill, then an end option | one skill option, then the end option |
| prt_church | Henson (103, 71) | 8 options: seven that explain a skill, then an end option (its text differs from Garnet's) | one skill option, then the end option |
| prontera | Guide#prt (154, 187), the city guide | 4 options: a city-guide submenu, removing the map marks, a notice, cancel | the map-marks or the notice option, then cancel |

- These menus are harmless: information only, no save point, no zeny, no items.
- Options with colour codes, inputs or side effects are never picked (for example the guide's
  city-guide submenu, which marks the mini-map and asks yes / no).
- The menu strings differ in small ways the reader must take as they are: one option has a
  trailing space, and the two church NPCs' end options are spelled differently.
- Only these three NPCs are in scope for talk@1.

**One trial (the rule under test):**
1. `@warp` to a seeded start cell 4–8 cells from the target (walkable, from the GAT). The other
   NPC of the scene stays ≥ 3 cells from the start.
2. **APPROACH with the walk rule:** the READY walk version chosen in 3.29. Its goal is a walkable
   cell 2–3 cells from the NPC, on our side; its NPC clearance and substitutes act as in its own
   pre-registration.
3. **CONTACT, one click:** hover the NPC's projected L3 cell and up its sprite (the monster
   positive case's points: 0, −14, −28 px). Click ONLY where the cursor reads **TALK** twice (no
   motion between the reads).
   - TALK is the allowed shape for this ONE click, as WARP is for the portal walk's last click.
   - Every other click of the trial keeps the walk rule's gates.
4. **The DIALOG, from pixels (T2):** wait for the dialog window. Then loop:
   - the dialog shows NEXT: click its NEXT button;
   - a MENU window shows: read its option lines (T3) and cross-check them against the L3 list;
   - the dialog shows CLOSE: click its CLOSE button.
5. **CHOOSE BY TEXT, never by blind index:**
   - The read lines must equal the L3 options (same count, same order, text matched).
   - Click the line whose text matches the intended option, check (pixels) that the highlight is
     on that line, then click OK.
   - A mismatch, or a line read with low confidence, is a decline: the menu's Cancel, then close.
     The trial is a FAILURE ("menu unread"), but a safe one.
   - The trial's first choice is its seeded option; the second is the end option (End
     Conversation / Cancel).
6. **CLOSE CLEANLY:** the dialog's CLOSE when the server shows it. The trial ends when the dialog
   and menu windows are gone (pixels, two frames).

**Prerequisites:** each is built and proven by a deliberate POSITIVE case (§2a) BEFORE any trial.
- **T1 · L3 for the targets:** `kb_route.py` / `kb_bindings.py` extended with
  npc/cities/prontera.txt and npc/pre-re/guides/guides_prontera.txt (local, regenerated). The three
  NPCs' cells and menu lists come from them, never typed by hand.
- **T2 · the dialog and menu windows from pixels:**
  - L2 anchors for the dialog window and its NEXT / CLOSE buttons, and for the menu window, its
    rows and OK / Cancel;
  - templates cut LOCALLY from live frames into `data/ui_anchors` (client pixels, never committed;
    the L2 YAML keeps names and offsets only).
  - **Proven** on ≥ 50 held-out frames of deliberate dialogs: present / absent and the button
    states agree with the packets (`npc_say`, `npc_wait`, `npc_menu`, `npc_close`) in every frame.
- **T3 · the menu text reader:** glyphs of the dialog font cut locally, labelled by packet truth
  (`npc_menu`'s option strings) at design time, as `weight_calibrate` did.
  - **Proven** on held-out menus: every option line read exactly, 0 wrong, and a refusal (not a
    guess) on a line it cannot read.
- **T4 · the dialog decoders LIVE** on the 17:51 sniffer: `npc_contact`, `npc_say`, `npc_wait`,
  `npc_menu`, `npc_choose`, `npc_next_click`, `npc_close`, `npc_close_click`. One deliberate
  dialog through `safety_signal_check.py`'s NPC path must show each of them live.
- **T5 · the TALK-gated contact click:** `safety_signal_check.py npc-click`, already proven for
  `npc_contact` (§2a). It is re-run on all three targets.

**Design detail from banked frames (2026-10-09 ~10:25, before any trial and before T2/T3 are built):**
- The source is last night's NPC positive case (Garnet; `npc-check` screenshots, local).
- The dialog window and the menu window are separate. The menu window shows **4 lines** and
  SCROLLS: Garnet's 7 options do not fit.
- So the reader (T3) reads the visible lines, scrolls the list, and reads again, until the lines
  it has read cover the whole L3 list in order. The cross-check is on the WHOLE list.
- The intended option is clicked only while it is VISIBLE, read on the current frame. The highlight
  is then checked on that line.
- The menu's OK / Cancel buttons are labelled in the client's own locale. They are found by their
  image anchors (T2), never by text.
- None of this changes a bar or a target.

**Step 0 · a PILOT, never scored:** 3 trials per scene, to check the harness end to end. Any fix
it needs is committed BEFORE the scored runs.

**The scored runs:** 50 trials per scene, RDP, ASSIST, the interlock green, the GM.
- prt_church: Garnet and Henson alternate, seed **20261130** (start cells and options).
- prontera: Guide#prt, seed **20261131**.
- The client's UI as pre-registered, with a screenshot before each run.

**A trial SUCCEEDS** when the packets show (offline, judged by a scorer committed before the runs):
- our `npc_contact` on the TARGET NPC: the NPC on the server at the L3 cell, matched by position;
- its `npc_menu` with the L3 options (otherwise the L3 data is wrong: reported, and a FAILURE);
- our `npc_choose` whose 1-based choice is the INTENDED option's position in that menu, and later
  the end option's;
- the dialog ended by OUR `npc_close_click` after the server's `npc_close` (or, for the end
  option, the script's own end), with no dialog left open at the trial's end;
- the runtime check (pixels) agreeing: the windows gone;
- all within 120 s of the contact click.

**SAFETY (zero tolerance), over the WHOLE trial:**
- any `npc_contact` on another NPC;
- a second contact on the target after its dialog closed;
- any `attack_request`;
- any GM act of kind normal or pickup.

**The bar:** ≥ 48 / 50 PER SCENE AND zero safety events, each scene scored separately.

**Reported:**
- per scene: success with its 95 % Wilson interval, and failures by cause (approach,
  contact, dialog unread, menu unread, wrong choice, close, timeout);
- reads that refused (safe declines) apart from wrong reads;
- the walk approach's own route outcomes;
- the time from the contact to the close (median, p95).

**Order:** after 3.29's held-out runs and loot@1 (3.20a). T1 and the scorer are desk work and come
first; T2–T5 need the client, in its gaps.

➡️ **Built 2026-10-09 (branch `feat/talk1-dialog`; code + host tests only, offline; NONE of T2–T5
proven live yet, §2a).** Nothing above is changed: no bar, no target, no step.
- **T2 · `poring_env/npc_dialog.py`:** `state(frame, templates)` → the dialog (its rect, its button:
  NEXT, CLOSE or none) and the menu (4 row boxes, the highlighted row, the scrollbar: can scroll
  up / down, OK, Cancel and the arrows by image), with a reason and a confidence.
  - The windows `npc_dialog` / `npc_menu` and their elements are registered in the ADR-0011 map
    (`ui_anchors.py`; keys and offsets only).
  - Each window is found anywhere as a WHOLE window under a mask without its text, list and
    buttons. It is judged by the share of differing pixels and of its border lines: present,
    absent, or UNCERTAIN in between (refused).
  - It fails closed: a hovered or unknown button, a covered row, two highlights, a half-seen
    scrollbar or missing templates give `ok=False`. Callers act only on two agreeing frames.
- **T3 · `poring_env/menu_text.py`:** `read_row` reads one option line exactly or refuses
  (coloured text, foreign pixels, an unknown or ambiguous glyph, an unexplained gap, a cut-off or
  indented line). Trailing spaces are invisible, so the expected text is compared without them.
  - `accumulate` merges the reads of successive scroll positions (each aligned by its overlap, one
    shift only) into the WHOLE list, from top to bottom.
  - `cross_check` compares that list with an L3 menu (count, order, every line). `line_of` /
    `align` place the intended line on the current frame.
- **The banked frames' geometry (the 2026-10-08 Garnet positive case, RDP, client px):**
  - dialog 278 × 178 at (201, 101); its text area (9, 9, 260, 140); NEXT / CLOSE at
    (233, 155, 42, 20);
  - menu 278 × 118 at (201, 301); rows at dy 25 + 16k, the text part dx 11, w 243; the highlight
    band covers a row's first 15 px rows;
  - the scrollbar at dx 254 (arrows dy 28 and 77, track dy 38–76); OK (187, 95, 42, 20), Cancel
    (233, 95, 42, 20);
  - the font: black on grey, no anti-aliasing; glyphs 1–7 px wide, 1 blank column inside a word, a
    5-column gap at a space; the first ink on a row's 4th column (dx 14).
  - A development check, NOT a proof (templates cut from the same 8 banked frames): NEXT read on
    4, the hovered NEXT (the cursor on it) refused on 2, the menu frame read (highlight row 0, can
    scroll down; its 4 lines read exactly), the closed frame read as no window.
- **The tools, `scripts/talk_calibrate.py`:**
  - `drive --npc garnet|henson|guide [--first N]`: one deliberate dialog, from the TALK-gated
    contact (cursor_gate, 3.30's points) to the end. It uses KEYS only (Enter, arrows), decided
    from template-free pixels at the windows' default places, and takes frames after every step.
    Then `collect`: T5 (our contact on the NPC at its L3 cell within 5 s) and T4 (each of the 8
    dialog events live).
  - `cut`: T2 and T3 templates from those sessions, labelled by the packets; the menu rows are
    labelled by structure and the scrollbar, never by the reader. It writes nothing unless READY.
  - `prove-t2` / `prove-t3`: on sessions NOT used by `cut`, with the bars above.
- **The harness, `scripts/talk1.py` (`pilot` / `run`):**
  - Trials (L3 read at run time): the start cell, then walk@15's route (or `--walk walk16`) to a
    goal 2–3 cells away on our side.
  - The one TALK-gated click, then the dialog by T2 and the choice by T3 (scroll to the top, read
    the whole list, cross-check it, the intended line visible and re-read, its highlight checked,
    then OK; anything else is Cancel). Then CLOSE, and the windows gone on two frames.
  - It writes `trials.json` in `talk1_score.py`'s contract and the session's packets.
- **What the parent must still run, live, in order:**
  1. T4 + T5 + the cut sessions: `drive` once per NPC (garnet, henson, guide). Each prints T5 /
     T4.
  2. `cut` on those three sessions: READY?
  3. Three fresh `drive` sessions, then `prove-t2` and `prove-t3` on them (≥ 50 held-out frames).
  4. Step 0, the pilot, per scene; `talk1_score.py` on it (never scored).
  5. The scored runs.
- **To confirm before the pilot (not decided by the pre-registration):**
  - The contact projection is placed by ONE `/where` fix after the route (`--contact-fix where`,
    the default; `none` uses the route's belief).
  - The walk version is walk@15 unless 3.29 chooses walk@16.
  - The pilot seeds are fresh: 20261132 (prt_church) and 20261133 (prontera).
  - A row click that chooses by itself (client behaviour not yet seen) is accepted and logged.
  - A window covered over about a quarter or more reads as absent, not uncertain. No client window
    opens over the default places in the lab layout.

➡️ **LIVE STEPS 1–3 DONE (2026-10-09 15:32–15:49 ICT, RDP, ASSIST, GM; main at 5a22d08 for the cut and
the proofs). Merged to main early (ddbf21c): Batt's item 6 (~15:20) needs T2 before any more typing.**

| step | sessions (`/dev/shm/poring-lab-demo/…`) | result |
|---|---|---|
| T4 + T5 drives (cut set) | `20261009T153405-demo-talk-cal-garnet`, `…153614-…-henson`, `…153815-…-guide` | all three **T5 PASS** (our contact on the NPC at its L3 cell within 5 s) and **T4 PASS** (all 8 dialog event types live) |
| `cut` | the three above | 1st: NOT READY (T2: 6 frames labelled "dialog with CLOSE" read as no window); **the LABEL was wrong** (below); after the fix **READY**: T2 held self-check 92/92, T3 136/136 exact |
| fresh drives (proof set) | `…154601-…-henson`, `…154802-…-guide` | T5 + T4 PASS |
| `prove-t2` | the two fresh sessions | **PASS: 168/168** frames agree with the packets (NEXT 54, menu 90, CLOSE 12, no window 12) |
| `prove-t3` | the two fresh sessions | **PASS: 216/216** option rows exact, 0 wrong, 0 refused; damaged copies never read wrong |

- **The label fix (5a22d08):** the city guide's script sends a second ZC_CLOSE_DIALOG 0.5 ms AFTER
  our close click. The client opens no window for it (frames 0054–0059 show none), but the labeller
  marked "dialog with CLOSE". Now a CLOSE with no dialog open labels no window, with a test. The
  reader was right.
- **Contact failures (no click, safe), both Garnet:** `…153202-…-garnet` and the 3rd-round
  `…154531-…-garnet` ended "no_contact": all three probe points read the cursor "unknown". A
  hover-only diagnostic at 15:33 read the same points: TALK at the feet (IoU 0.90, colour 0.85), then
  "unknown" at dv −14 / −28 with IoU 0.86–0.89 but COLOUR 0.0. The shape matched and the colour
  check failed. This is intermittent: the same feet point failed in the first drive. Batt
  (~15:50): measure the TALK read rate per NPC / position / background and find why the colour check
  fails, BEFORE talk@1's scored trials (folded into walk@17 item 5's targeted test).
- **T3 coverage caveat:** the guide's 4-option menu rows found no structure fit in either set (36
  unlabelled rows in the proof), so T3's proof covers the 8-option menus (Garnet / Henson) only. The
  prontera scene's menu reads are therefore unproven. This must be closed before talk@1's prontera
  pilot.
- Templates are in `data/ui_anchors/npc_dialog/` and `data/ui_anchors/menu_glyphs.npz` (client
  pixels, gitignored).

**3.29 HELD-OUT RESULTS (walk@15, 2026-10-09 12:01–13:46 ICT; scored per map, `walk_readiness.py`):**

| map | session | routes scored | success | 95 % CI | safety | ended | walk-ready (3.28) | verdict |
|---|---|---|---|---|---|---|---|---|
| guild (alberta_in) | `20261009T120146` | 5 | 0 / 5 | 0–43 % | 0 | harness stop at route 5 (chat input) | species: none spawn there | **INCOMPLETE** |
| town (prontera) | `20261009T120857` | 45 | 39 / 45 = 86.7 % | 73.8–93.7 % | 0 | harness stop at route 45 (chat input) | no spawns | **INCOMPLETE** |
| dungeon (iz_dun00) | `20261009T123810` | 50 | 29 / 50 = 58.0 % | 44.2–70.6 % | 0 | complete (harness stop after route 50) | **NO** (6 species out of scope) | FAIL; path-following only |
| portal (prt_fild08 → prontera) | `20261009T134557` | 0 | — | — | 0 | harness stop at start: no seeded start cell | — | **INCOMPLETE** |

- **guild:** route 0's goal (77, 42) lay inside alberta_in's exit warp trigger area (span 2 × 5 around
  (78, 44)).
  - The GM was warped to alberta, and every relocalisation after that failed (wrong map).
  - The harness then stopped at its periodic `@warp`. A RULE finding: walk@15 does not avoid warp
    areas (walk@17 B).
- **town:** the failures were `relocalise_failed` 3, an unjustified NPC substitute 1, `no_click_point`
  1, and a route that ended elsewhere 1. The harness stopped at route 45.
- **dungeon:** the failures were `relocalise_limit` 17 and 4 others.
  - The GM walked into iz_dun00's exit warp to izlu2dun 3 times (warp areas again).
  - Monsters hit the GM 7 times (167 damage over 4 episodes; its HP fell to 14–17 of 40 each time, and
    the harness's `@heal` at its warps restored it; no death in the packets).
  - The walk marker never named a cell on the dark floor: every click was "unnamed after fix", and 68
    of them produced no move request.
  - The scorer listed 4 GM "stand" acts (at harness `@warp`s) under SAFETY. They are NOT safety events
    under the definition; `walk_readiness.py` now counts only the defined kinds.
  - **Batt's 13:03 screenshot:** the Hydra he saw unboxed was on the server, 3 cells west and 8 north
    of the GM, at the moment /where read (165, 164). That is a FALSE NEGATIVE: Byalan species were
    never in training.
  - **Gate refusals vs the HUD's boxes:** 44 monster refusals.
    - 37 with a server monster within 15 cells, 7 with none (false positives such as the portal and
      the torch).
    - In 2, the HUD's only monster boxes were below 0.30.
    - The gate's own scores were not logged in this run (logged from now on).
- **portal:** the L3 portal cell (170, 378) is NOT walkable in the GAT; its trigger area (span 4 × 1)
  holds walkable cells such as (170, 377). The harness's start-cell search plans TO the portal cell,
  so it found none. A HARNESS fault.

### 3.29a AMENDMENT — re-run every held-out map that ended INCOMPLETE, once (pre-registered 2026-10-09 ~13:45 ICT / 06:45 UTC, BEFORE any re-run; Batt 2026-10-09 ~13:20 + ~13:40)
**Why:** two held-out maps ended early on a HARNESS stop, "the chat input did not open: nothing
typed" (exit 3):
- guild: 5 routes, 0 / 5;
- town: 45 routes, 39 / 45 = 86.7 %, 0 safety.

Both stops came at the harness's periodic `@warp`, right after its `@killmonster2`. The harness typed
`@killmonster2` before EVERY route, and the client refuses the 4th identical chat line in a row (L2
`chat.repeat`). The stop is a harness fault; the rule is unchanged. The guild run had also met a rule
fault first: route 0's goal lay inside the exit warp's trigger area. That finding stands.

**The re-runs:**
- Each INCOMPLETE map once more, with FRESH seeds: guild **20261124**, town **20261125**. iz_dun00
  **20261126** and the portal walk **20261127** are reserved, and are used only if those runs also end
  INCOMPLETE.
  - ➡️ **Updated 13:50, after the chain, before any re-run:** iz_dun00 COMPLETED (50 scored) and is
    not re-run.
  - The portal walk ended INCOMPLETE with 0 routes, from a different harness fault: its target cell is
    not walkable. It is re-run with **20261127**, after one more HARNESS fix: the harness's portal
    target is the walkable cell of the L3 trigger area nearest the warp's centre (170, 377), for both
    the start-cell search and the route's goal.
  - The bytecode proof must still PASS. The portal target is a harness constant, which the rule only
    receives as its goal.
- The rest exactly as 3.29: CLEAN, the first 50 routes scored, the bar per map (≥ 45 / 50 + zero
  safety), walk-readiness per map stated (3.28).
- **The incomplete runs' data is kept and reported alongside** (Batt), not replaced.

**What changes: the HARNESS only.**
1. `@killmonster2` only when CLEAN needs it: a monster seen in the scene now, or one the previous
   route saw.
2. The typing guard (`scripts/chat_guard.py`, Batt 2026-10-09):
   - no 3rd identical line in a row (a repeated GM command is skipped and logged);
   - no filler line;
   - a minimum interval;
   - /where once per need.
3. `open_chat` recognises and recovers from the post-refusal chat state. This is built after the live
   probe that characterises that state (`chat_repeat_probe.py chat`), BEFORE the re-runs.
4. The detector logs every batch (class + score per box) to the session.

**THE ONE EXEMPTION (Batt, option A):** walk@15's FROZEN where@2 (`where_fix.fix_v2`: an "/ex"
separator, then /where, read twice) may type its pattern inside these re-runs ONLY, so the rule is
tested exactly as pre-registered.
- The re-run chain sets it (`chat_guard.py exempt --id 3.29a`) and clears it when the re-runs end;
  it also expires by itself (≤ 8 h).
- It covers only where@2's own tagged lines. Every line it lets through is logged with id 3.29a.
- **From walk@17 on, every rule follows the policy:** no separator commands, /where once per need,
  passive sources first.

**The proof, before any re-run:** `scripts/bytecode_proof.py walk15 <e1299f5> <the merged tree>`.
➡️ **RESULT (2026-10-09 ~14:10, main at f8064f8): PASS.**
- 1,083 functions, methods and constants were compared.
- **Changed, all declared harness:** `walk11.run` (+ its rebound copies `run11` in walk12–15),
  `ro_agent.chat_line` / `gm` / `say` / `open_chat`, `where_fix.fix` / `fix_v2` (the typing
  transport).
- **Added:** `walk11.portal_goal`, `walk11.scene_has_monsters`, `where_fix.fix_once`,
  `ro_agent.CHAT_RECHECK_S`.
- **Undeclared changes: none.** walk@15's decision code (the route loop, the click step, the gates, the
  unit memory, the planner) is bytecode-identical to e1299f5.

**The post-refusal chat state, as found** (`chat_repeat_probe.py chat`, 13:49, live):
- After the client's repeat refusal, the chat input stays OPEN and EMPTY: chat_open distance 1.2–1.3
  (a match is ≤ 6), and `open_chat` works after it.
- So the three harness stops had ANOTHER cause, still unknown.
- `open_chat` now re-judges on fresh frames for up to 2 s (no key sent), and a real failure saves the
  frame and the distances.

- It must be **PASS**: walk@15's DECISION code is bytecode-identical to its pre-registration.
- Only the declared harness may differ: the run loop, typing, the /where transport and the detector's
  log.
- Its output is recorded here before the first re-run.

#### ➡️ 3.29a RESULTS (2026-10-09 13:54–14:38 ICT, main at a41ad13; scored offline by the packets): NO held-out map passes; walk@15 is NOT walk-ready on held-out

| map (seed) | ended | scored | success | Wilson 95 % | safety | 3.28 verdict |
|---|---|---|---|---|---|---|
| guild, alberta_in (20261124) | INCOMPLETE again, 14:06 (harness stop, exit 3) | 10 | 8 / 10 = 80.0 % | 49.0–94.3 % | 0 | not ready (incomplete; < 90 %) |
| town, prontera (20261125) | COMPLETE, 56 routes, 14:38 | 50 | 48 / 50 = **96.0 %** | 86.5–98.9 % | **2 `npc_contact`** | **FAIL: safety** |
| portal, prt_fild08 (20261127) | INCOMPLETE, 0 routes, 14:38 (harness stop, exit 3) | 0 | — | — | 0 | not run (see the cause) |
| iz_dun00 (3.29, not re-run) | COMPLETE | 50 | 29 / 50 = 58 % | — | 0 | path-following only |

The first runs (3.29) are kept as reported: guild 0 / 5 and town 39 / 45, both INCOMPLETE. The
exemption was set at 13:54:32 and CLEARED at 14:38:47 by the chain's exit trap. The guard's log over
the re-runs: 129 /where, all `where_fix.fix_v2` (the exempted pattern), and 1 refusal (`repeat`, a
harness `@killmonster2` skipped at 14:04:47). The iz_dun00 seed 20261126 is unused.

**guild (20261124): the 3.29 rule fault, again.** In route 9 the rule walked into alberta_in's exit
warp area (3.29's finding; walk@17 B blocks those areas). The harness's `@warp alberta_in 66 42` then
became a cross-map load. Its next typed line came 2.5 s after the warp (`WARP_SETTLE_S`), while the
map was still loading, and the Enter was swallowed: chat_open distance 118 ×8, frame
`/dev/shm/poring-lab-tmp/chat-open-fail/20261009-140611.png`.

**town (20261125): 96 % success, but TWO NPC CONTACTS, so it FAILS (3.28: zero safety).** Both
contacts came from walk@15's own single-click step. Each time:
- the cursor was read as WALK;
- the hover walk marker was drawn;
- the detector envelope had ZERO units;
- yet the server received a contact with an NPC 2 cells away.

| # | when (ICT) | route | clicked cell, screen point | cursor read | NPC contacted (packets) |
|---|---|---|---|---|---|
| 1 | ~14:32:51 | 48, (161,192) → (150,192) | (156,192), (465,361) | WALK, IoU 0.807, marker 63 px | a job-722 NPC at (155,190) |
| 2 | ~14:37:45 | 55, goal (155,191) | (153,189), (568,292) | WALK, IoU 0.615, marker 39 px | the city guide NPC (job 105) at (154,187) |

- **Contact 2 came from walk@15's TALK-read NPC substitute.**
  - The goal (155,191) was refused as a talk cell.
  - The remembered talk cells (155,187…191) were ONE COLUMN off the guide's true cell (154,187).
  - So the substitute (153,189) sat beside the guide, and the client resolved the click to the guide.
- **Contact 1 had no talk-cell memory involved at all:** the rule never saw that NPC as a unit (no
  detector box, no remembered cell), and its walk click 2 cells away became a contact.
- **What follows from it (a fact, not a fix):** walk@15's NPC safety in a town rests on the cursor
  read and the detector. Twice in 50 routes, both said "clear" over an NPC's click area. walk@17
  carries the same decision code (`docs/planning/walk17.md` E), so this is its top safety cause before
  its tuning runs.
- **The aftermath, also bot input.** Contact 2's dialog stayed open. Every Enter the harness pressed
  afterwards went to the dialog, not the chat. Between ~14:37:48 and ~14:38:36 that was 5 "next"
  clicks and 5 menu choices, each choice 1 (the guide's city-guide branch → "mark on the minimap: yes"
  → the first building ×3).
  - Their effect was dialog text and client-side minimap marks only. Both were gone after the 14:47
    rathena restart's re-login (screenshot 14:50: no dialog, a plain minimap). There was no item,
    zeny or position change.
  - They are not in 3.28's safety keys, but they are unintended NPC interactions and are reported as
    such.
  - The town run's closing `@killmonster2` (14:38:03) never reached the server: it is still in the
    chat input on the next screenshot.

**portal (20261127): a HARNESS fault, mine, not a rule result.**
- The town run left the guide's dialog open, and the chain started the portal run on top of it.
- The chain's own pre-run screenshot (`/dev/shm/poring-lab-tmp/shots/heldout-a-portal.png`,
  14:38:16) shows the dialog. The chain took that screenshot but never JUDGED it.
- The portal run's first typed line after its `@warp` found the chat input not open (distance
  11.0 ×8, frame `.../chat-open-fail/20261009-143836.png`) and stopped with 0 routes.
- This breaks the standing rule "screenshot + close leftover windows before any scored run"
  (2026-10-08). A chain must judge the client's UI state between runs, not only record it.

**Not done, waiting for Batt:** any further re-run. Batt allowed ONE re-run per map, and the
where@2 exemption ended with the chain. A third guild run or a second portal run would need a new
decision, and the exemption again.

### 3.31 tour@1 — LONG walks across a map: chained legs through waypoints (pre-registered 2026-10-09 ~14:00 ICT / 07:00 UTC, BEFORE any run; Batt 13:42: "the held-out harness keeps every route within a few cells of one start spot ... it never tests LONG walks across a map, which workflows need")
**Why:**
- 3.24–3.29's routes are 8–20 plan steps from a start the harness warps back to.
- Workflows walk across maps: entrance → Kafra, town → field.

**The rule:** the first walk version that FOLLOWS THE TYPING POLICY and is READY (3.28): walk@17
(`docs/planning/walk17.md`) once its own tuning makes it READY.
- Its long-walk part (walk17 C: legs of at most `PLAN_MAX` = 48 steps chained through waypoints,
  every click at most 14 server steps ahead) is what tour@1 measures.
- tour@1 never runs walk@15 (it types the "/ex" separator, which only 3.29a's re-runs may do).

**Start and goal, chosen MECHANICALLY from the GAT** (a script committed before the first tour; per
map, seeded):
- both cells in the map's LARGEST 8-connected walkable region;
- the A* path between them (the planner's own costs, no length limit) 60–150 cells long;
- **around large obstacles:** at least half of a map's tours have a detour ratio (path steps /
  straight octile steps) ≥ 1.25; the rest are drawn freely in 60–150;
- neither cell within 3 cells of an L3 warp trigger area or an L3 NPC;
- the start reached by `@warp`, CLEAN (3.29a's harness: `@killmonster2` only when needed).
- ➡️ **Amended 2026-10-15, before any tour** (Batt decisions 3 and 4; 3.32 amendments 3 and 4):
  - "the GAT" above means the cells walkable in BOTH the client's GAT and the server's map cache
    (alberta: 4,836 client-walkable cells are server-NOPASS);
  - neither cell lies in the map's measured ANIMATED region.
  - Decision 4 binds only alberta's draws: the other tour maps have no client-walkable /
    server-NOPASS cells. The animated region binds each map as measured. No tour has been drawn yet (the draw script is still to be
    written), so the seeds are unchanged. Each map's tour list is recorded here before its block
    runs.

**Maps and n:**
- **30 tours per map:** prt_fild08 (field), prontera (town), alberta (a workflow town) and iz_dun00
  (dungeon).
- Each map is a block of its own, run once, scored separately.
- **Seeds:** prt_fild08 **20261140**, prontera **20261141**, alberta **20261142**, iz_dun00
  **20261143**.
- The visual-diversity maps get their own tour blocks, pre-registered with that set.

**Scored (offline, the packets):**
- **A tour SUCCEEDS** when the final cell from the packets is the goal (the walk version's own
  substitute rules apply as in its pre-registration), within the time budget: 4 × (path steps × the
  GM's server walk time per cell) + 60 s. Beyond it the tour fails "too slow".
- **SAFETY as usual (zero tolerance):** `attack_request`, `npc_contact`, GM acts of kind normal or
  pickup.
- **The bar, per map:** ≥ 27 / 30 (90 %) AND zero safety, with its 95 % Wilson interval (3.28's
  arithmetic). A map's walk-readiness (3.28) is stated next to it: iz_dun00 reads as path-following
  only.

**Reported, no bar:**
- **The pace:** seconds per cell walked, against the server's own walk time per cell (the character's
  speed) and against a human-like pace (a player clicking ahead, ~1.2 × the server time). Median and
  p95 per map.
- Clicks per 10 cells, legs and waypoints per tour, re-plans, declines by cause.
- Position reads by source: minimap readouts, /where uses (with reasons, against the run's budget),
  dead reckoning.

### 3.32 walk@17 — walk@15 + the TYPING POLICY (minimap first, /where once per need), WARP AREAS, LONG WALKS; TUNING, then READINESS (pre-registered 2026-10-09 ~14:30 ICT / 07:30 UTC at commit, BEFORE any run; design `docs/planning/walk17.md`, approved by Batt 2026-10-09 ~13:42 and ~14:00)
**Why:**
- walk@15 is READY (3.28: 186 / 200, 0 safety), but its relocalisation types where@2's pattern:
  an "/ex" separator, then /where twice. From walk@17 on, no rule may (3.29a, the typing policy).
- 3.29's held-out runs walked into warp areas. Guild route 0's goal lay inside alberta_in's exit
  warp area, and on iz_dun00 the GM walked into the exit warp 3 times.
- A route is one A* plan of at most `PLAN_MAX` = 48 steps. Workflows and tour@1 (3.31) need walks
  across a map.

**The rule:** `scripts/walk17.py` at b7cf790 (this pre-registration's parent commit). It is
walk@15's decision code REBOUND, not copied:
- walk@14's route loop, walk@15's route wrapper (its visited set, E), walk@15's NPC clearance (D),
  walk@13's click step and walk@11's harness are the SAME code objects. They are re-bound so that
  they call walk@17's relocalisation, planner, click step, label and session log.
- walk@11's substitute ring, walk@13's NPC substitute and walk@14's side search are rebound too:
  they PLAN, so B applies to them.
- `services/backend/tests/test_walk17.py` checks the reuse, that every name resolves, and that
  walk@15's module is untouched.
- **The bytecode proof:** `scripts/bytecode_proof.py walk15 <main at 11961fb> <the walk17 tree>`
  → **PASS**. 1,087 functions, methods and constants were compared; nothing changed, nothing was
  removed or added.

**The changes, exactly:**
- **A. Position: the minimap first, /where only where there is none.**
  - Every relocalisation reads the minimap readout first (`poring_env.selfpos`). That is walk@8's
    doubt path, and walk@11's fix at a route's start when the single minimap read gave nothing.
  - The read: two reads on two DISTINCT fresh frames (a new frame-bus id, else a new grab), equal,
    on the map, walkable, within 6 cells of the belief. Nothing is typed.
  - Only when NEITHER read shows a readout (the client draws none indoors) does it type /where.
    That is where@3 (`where_fix.fix_once`): ONE line and one answer, tagged with its reason class
    (ADR-0020 #10): `walk@17 route_start_indoor` before a route, `walk@17 belief_in_doubt` inside
    one.
  - It never prepares a /where within the guard's retry interval (60 s, L2) of its previous one.
    Once the guard refuses one for the run's budget, or as a 3rd identical line in a row, it asks
    no more for the rest of the run.
  - A miss is no fix, and nothing is typed again for that need. A route START goes on dead
    reckoning; a DOUBT declines (`relocalise_failed`: walk@15's route loop, unchanged).
  - A minimap miss (the reads disagree, off the map, not walkable, implausible, no fresh frame) is
    never a reason to type.
  - where@2 (`fix_v2`) and "/ex" are never used (tested).
- **B. Warp areas are not walkable for a walk.**
  - **The planner** blocks every L3 warp trigger area of the run's map (`data/kb/route.json`:
    cell ± span). That covers every `walk6.plan` call of walk@15's decision code and harness: the
    route loop, the re-plan, the substitutes, the side cells, the harness's goal draw and the
    portal scene's start search.
  - Only a plan whose intent IS the portal (`expect_goal="warp"`; the portal scene's start search)
    may enter the area(s) holding its goal. **Claude's reading, stated so Batt can correct it
    before any run:** every OTHER warp area stays blocked for a portal route too.
  - **The click step** refuses a walk click whose cell lies inside a warp area (`no_safe_point`:
    the next point, and the cell is re-planned around). The portal click is unchanged.
  - So **the harness never draws a goal inside a warp area** (its goal check is "a plan exists").
  - A map that route.json does not list FAILS CLOSED: the run refuses to start.
- **C. Long walks: chained legs through waypoints.**
  - A route whose A* path (warp areas blocked, no length limit) is longer than `PLAN_MAX` = 48
    steps is split into legs at waypoints. A waypoint is the nearest walkable cell outside every
    warp area to a mark on that path, about every 40 steps. Each leg is at most 48 steps.
  - Each leg is walk@15's route, walked as a route is today (its own plan, limits, substitutes and
    declines). The route's own intent (a portal) applies to its last leg only.
  - A leg that does not arrive ends the route with its decline. A waypoint's substitute is never
    reported as the goal's.
  - **No click is farther than 14 server steps** (`CLICK_MAX_SAFE`, poring-nav.md §2). The
    farthest candidate is 12 cells along the plan (asserted at import). The click step refuses a
    cell whose server path (the GAT's own A*) is longer than 14 (`no_safe_point`,
    `beyond_click_max`).
  - Until poring_nav lands, the split is walk@17's own. test_walk17.py cross-checks it by the
    cross-check test's method: each leg's own plan exists within 48 steps, and the legs' costs sum
    to the whole A*'s.
  - A route of at most 48 steps is walk@15's route, unchanged. Every tuning route is one (8–20
    steps).
- **D. The harness as on main (3.29a):**
  - walk@11's run, with `@killmonster2` only when CLEAN needs it;
  - the typing guard and `open_chat`'s re-check;
  - the portal target fix;
  - the detector's batch log (`detections.jsonl` in each session).
- **NOT carried: walk@16's F** (Batt ~14:00: "no measurable effect beyond run-to-run noise; fewer
  rules").
- **Everything else is walk@15's:** the unit gate (0.25), the NPC clearance (D), the side cells
  (E), the TALK-read NPC substitute, the work zone and the signs, 4 relocalisations per route, and
  the trust for 3 clicks.

**The typing policy, per run:**
- No separator or filler line. `/where` once per need, its reason logged by the guard.
- **The run's /where BUDGET: 56**, one per route (`WHERE_PER_ROUTE` × 56 routes; Claude's
  proposal).
  - It is opened by `chat_guard.start_run` when the session starts, with the session id as the
    run id.
  - Why one per route: ADR-0020 #10 counts a route start indoors as a need, and walk@15's indoor
    runs fixed every route start. The budget caps that at today's need; the retry interval keeps
    the lines apart.
- **Reported per run** (`walk17_score.py`, from `data/ro_agent/chat_guard.jsonl`):
  - the /where count and its reasons;
  - any other run's /where in the window;
  - the guard's refusals by rule;
  - exemptions in the window (must be 0: walk@17 has none);
  - the relocalisations by method (minimap / where) and outcome against the packets (correct /
    WRONG / undecided).

**Scoring, instruments:** as 3.24–3.27, unchanged: demo_verify and the packets, the substitutes as
there, the strict count reported.
- The scorer is `scripts/walk17_score.py` at b7cf790: walk15_score.py's approach, committed and
  tested on a synthetic session. Its first object is what `walk_readiness.py` reads.
- It also reports B: walk clicks refused in a warp area, and walk routes during which the server
  changed our map.
- And C: routes walked as legs, the legs planned and walked, the leg that declined, clicks
  refused beyond 14, the farthest click.

**TUNING runs, all four whatever the first scores:**
- FRESH seeds: indoor clean **20261150**, indoor crowd **20261151**, outdoor clean **20261152**,
  outdoor crowd **20261153**.
- 56 routes each; the first 50 not interrupted are scored.
- e.g. `scripts/walk17.py --scene indoor --condition clean --seed 20261150 --label walk17-alone`.
- Conditions as 3.24–3.27. 3.33's GM immunity is the visual-diversity block's condition, not
  tuning's.
- Before each run: a client screenshot, and any leftover window closed (3.24's inventory incident).
- A harness exit that leaves fewer than 50 scored routes means the run is re-run unchanged with its
  seed. The partial session is kept, not scored.

**The bar:**
- **Per run** (3.24–3.27's, reported): ≥ 48 / 50 AND zero `attack_request`, zero `npc_contact`,
  zero GM `act` of kind normal or pickup. Any safety event is a HARD FAIL.
- **READINESS** (3.28; it decides what follows):
  - zero safety events in all four runs;
  - AND the pooled point estimate ≥ 90 % (≥ 180 / 200), with its 95 % Wilson interval reported
    (and the stricter lower-bound reading);
  - computed by `walk_readiness.py --label walk@17` over the four scorer outputs.

**Only if walk@17 is READY** (these runs are not pre-registered again here):
- **HELD-OUT:** 3.29's four maps and rules, once each, scored per map (≥ 45 / 50 + zero safety,
  the Wilson CI, walk-readiness per map). NEW seeds, reserved now: guild **20261154**, town
  **20261155**, dungeon **20261156**, portal **20261157**.
- **tour@1:** 3.31 as pre-registered (its seeds 20261140–43), with walk@17.
- A's per-map minimap check (walk17.md A) belongs to the visual-diversity block and is
  pre-registered with it.

> ➡️ **2026-10-13: the CPU detector this rule uses is now v1** (Batt decision 10; deployment parity PASS,
> v1-vs-v0png.md). walk@17's tuning runs, still to come, run with it: recorded here before they run.
>
> ➡️ **AMENDMENTS (2026-10-13, Batt decision 15), built and tested BEFORE any tuning run:**
> 1. **"'/where once per need' wins over the repeat rule"** (`chat_guard.py`; L2
>    `chat.policy.where_need_over_repeat: true`):
>    - a /where typed with a stated need (walk@17's reasons) is not refused as a 3rd identical
>      line; each such line is logged `repeat_waived`;
>    - the 60 s retry interval and the run's budget still apply;
>    - a /where the client then drops (the measured 4th-identical drop) is no fix, as for a miss;
>    - where@2's frozen pattern keeps the repeat rule (`test_chat_guard.py`).
>    The expected indoor loss stated above (the guard's repeat rule) therefore no longer applies as
>    written. The client's own drop now decides, and the runs report the /where answered vs
>    dropped.
> 2. **"Never draw a harness start inside a warp area"** (`walk17.py` `_Walk5`): walk@17's harness
>    sees walk5 through a proxy whose `World` offers no warp-area cell as walkable in a WALK scene,
>    so walk@11's seeded start draw cannot land in a trigger area.
>    - The planner's grid is untouched (B already blocks those cells).
>    - The portal scene's world is unchanged.
>    - walk@15's code objects are reused exactly as before (`test_walk17.py`, including the
>      identity test).
>
> ➡️ **AMENDMENTS (2026-10-15, Batt decisions 3 and 4; PRE-REGISTERED 2026-10-15 BEFORE any tuning
> run; the code and the measurements follow, each recorded here before a run uses it):**
> 3. **Avoid moving scenery** (Batt, decision 3: "don't read through moving scenery, AVOID it. The
>    walk rule (and any hover/click planner) never picks a point inside a measured per-map ANIMATED
>    region; pick another point on the polyline. robust2 stays the live gate. Pre-register the
>    avoidance as part of walk@17, with its effect on Alberta.")
>    - **The region is MEASURED per map**, live, by `scripts/anim_region.py measure --map M` (RDP, the
>      GM, hover-free: only `@warp` lines are typed, through the UI gate and the typing guard).
>      - **Stands, pass 1:** a lattice every 8 cells over the map's walkable cells (client ∩ server,
>        amendment 4). Each stand must pass npc_click_test's three checks (no warp span, no touch
>        area, server-walkable). A lattice point that fails moves to the nearest cell that passes,
>        within 3 cells, or is dropped (logged).
>      - **Per stand (cursor@3's measurement, unchanged):** `@warp`, ~~a 2 s settle~~ ➡️ the
>        harness's settle (rule_run: 2.5 s, 7 s for the first warp onto the map; corrected
>        2026-10-15 before any measurement), the cursor parked by two motions, then 13 grabs 0.2 s
>        apart. `cursor_anim.animated_region`: a pixel differs from
>        the first grab by more than 60 (summed BGR) in any later grab; grown 2 px.
>      - **Excluded before back-projection:** the GM's own sprite box around the stand's projected
>        point (fixed in the tool before its first run); the client's UI rectangles at their L2
>        default places (basic info, minimap, chat); pixels that pick no map cell.
>      - **Transients removed:** a view with any animated pixel is measured AGAIN at least 60 s
>        later. Only pixels animated in BOTH measurements count. The lab towns have no other players.
>        Animated idle NPCs stay in: they animate both times.
>      - **Each counted pixel becomes the cell the client picks there** (`poring_dataset.picking`, the
>        view's camera). A view's animated cells are those cells.
>      - **Pass 2:** a lattice every 3 cells within 12 cells of every stand whose view kept animated
>        cells, measured the same way.
>      - **The map's region:** the UNION of every view's animated cells, grown by 1 cell
>        (8-neighbour). It is saved locally (`data/kb/anim_regions/<map>.json`, gitignored: it is
>        derived from client pixels), with its stands, times, per-view counts and the tool's commit.
>      - Why cells, not pixels: the camera follows the GM, so a screen region is one view's. The
>        rule needs one region per map. The client's click on a cell's safe point picks that cell,
>        so "the point is inside the animated region" is "the cell is in the region".
>    - **The rule (walk@17):**
>      - **The click step** refuses a WALK click whose target cell is in the map's region:
>        `no_safe_point` with `animated_region`. walk@15's route loop then takes the next candidate
>        on the polyline, as for B's warp areas. Every refusal is logged.
>      - ~~**The harness never draws a start or a goal in the region.** The `_Walk5` proxy World hides
>        those cells, as amendment 2 hides warp areas.~~ ➡️ CORRECTED in 3a below (hiding cells in
>        the World would also block PATHS through the region). tour@1's endpoint draw excludes
>        them.
>      - **The PLANNER's grid is unchanged:** a path may cross the region. Only clicking or hovering
>        there is avoided.
>      - **Fail closed:** a walk@17 run on a map with no measured region refuses to start, as
>        route.json's warps do.
>      - The portal click (an intended warp) is not refused; when its cell is in the region, that
>        is logged.
>      - The cursor reader and the gate are unchanged: **robust2 stays the live gate**.
>    - **Other planners** (Claude's reading; ➡️ CONFIRMED by Batt 2026-10-15 13:08: "(a) an
>      intended TALK contact click on an L3 NPC is not refused by the region; (b) 3.38's B runs
>      keep their plans; report their hovers inside a region separately"):
>      - Planners that ACT inherit the rule: talk@1 on walk@17's approach, and any future walk
>        user. A TALK contact click on an L3 NPC is NOT refused by the region. Its NPC rules
>        (the NO-CLICK layer, T2) govern it, because an animated idle NPC would otherwise never be
>        talked to.
>      - The cursor MEASUREMENT probes pre-registered before this decision keep their plans:
>        npc-render 3.38's B runs (B1', B2, B3). Their hover points that fall inside a measured
>        region are reported apart, and B's bars are unchanged.
>    - **Order:** prt_church and prt_fild08 are measured before walk@17's tuning runs. Each held-out
>      or tour map is measured before its block.
>    - **Its effect on Alberta:**
>      - **Reported now, from data already scored** (cursor@3's alberta probe session, both
>        labellers agreeing, WALK truth). The "inside" flag is the same 13 x 0.2 s cycle region
>        at the hotspot. NOT a bar.
>
>        | alberta WALK hovers | n | robust2 (live gate) | robust3 |
>        |---|---|---|---|
>        | all | 372 | 0.667 (248) | 0.626 (233) |
>        | inside the region (the 4 windmill views) | 108 (29 %) | 12 | 0 |
>        | **outside** (what avoidance leaves) | 264 | **0.894 (236)** | 0.883 (233) |
>
>      - prontera, prt_church and morocc have 0 such hovers, so avoidance changes nothing there.
>      - robust2's 28 misses outside the region are mostly not the sails: 13 of them are in ONE view,
>        (123,68), 13 of its 22. That view is a separate question.
>      - **Computed after alberta's region is measured, BEFORE tour@1's alberta block** (3.31, seed
>        20261142), recorded here:
>        - the region's size;
>        - tours whose start or goal falls in it (re-drawn by the rule);
>        - click candidates refused along each tour's A* path;
>        - routes left without a clickable point.
> 3a. **SCOPED, before any measurement** (Batt 2026-10-15 13:08: "amend BEFORE any measurement
>    ... scope each map to the FIRST WORKFLOW's areas (training grounds' 4 layouts, the route to
>    alberta/alberta_in, prontera's and geffen/geffen_in's delivery paths) plus prt_church and
>    prt_fild08's tuning areas; clicks outside a measured area are refused (fail closed). Report
>    the client time it needs."). Replaces "a lattice ... over the map's walkable cells" above;
>    everything else in amendment 3 stands.
>    - **The scope** (`anim_region.py`, `scope_for`), the stands' lattice drawn only inside it:
>      - **the training grounds' 4 layouts:** each layout's WHOLE walkable map, measured on its
>        clone group's first map (new_1-1 .. new_1-4). The region serves the group's 5 copies:
>        the KB's clone groups have identical cells, and map prep (748260d) checked the copies'
>        RSW/GND/textures identical;
>      - **the workflow routes:** the Merchant round trips to the two supported destinations
>        (prontera, geffen_in; decision 4): `npc_sprites.route_stops` / `route_cells` (the
>        arrival in alberta_in, the job changer, the storehouse, alberta, the Kafra hops, the
>        destination and back), shortest paths on client ∩ server walkability, plus a corridor
>        of 6 cells. 0 route problems;
>      - **the tuning areas:** prt_church and prt_fild08, within 68 cells of walk@11's scene
>        anchors (104,122) and (268,107). The harness warps within ±8 every 5th route, and each
>        goal lies within ±12 of its start: 8 + 5 x 12 = 68.
>    - **The measured AREA:** the union over the measured, position-audited, settled views of the
>      cells the client picks anywhere in the view's counted pixels (`coverage`, every 8 px).
>      **A WALK click on a cell outside it is refused** (`no_safe_point`, `"animated":
>      "not_measured"`), as is one in the region (`"animated_region"`). A map never measured
>      refuses to start.
>      - So every block outside this scope fails closed until its own measurement is
>        pre-registered with it: walk@17's held-out town (prontera 156,180), dungeon (iz_dun00)
>        and portal (prt_fild08 170,368, beyond the tuning box), and tour@1's tours.
>      - The guild scene (alberta_in 60,40) lies near the workflow corridor (the job changer is
>        at 53,43): its coverage decides.
>      - For 3.38's B runs (hovers reported, never refused): B2 (alberta_in 53,43) and B3
>        (new_1-2) lie inside the scope. B1' (prontera 148,326) does not, so it gets no region
>        to report against.
>    - **The harness, CORRECTED** (amendment 3 said the World hides region cells; walk6's planner
>      plans on that same grid, so hiding would also block paths THROUGH the region, against
>      "pick another point on the polyline"):
>      - while no route runs, i.e. during walk@11's GOAL draw, walk@17's planner has no plan to a
>        goal in the region or outside the measured area, so the harness draws another;
>      - a route's own plans and the planner's grid are unchanged;
>      - starts are warp targets, never clicked, and stay walk@11's draw.
>    - **Built, tested, before any measurement:**
>      - `anim_region.py`: `plan` / `measure` scoped, `build` writes the region, the measured
>        area and the clone copies (13 tests);
>      - `walk17.py` amendment 3: the click step, the harness goal, fail closed, the manifest's
>        `anim_region_cells` / `anim_measured_cells` (4 new tests in `test_walk17.py`).
>      - walk@15's module is untouched.
>    - **The client time it needs** (`anim_region.py plan`, 13:16:22-13:16:30; pass 1 at ~7 s per stand:
>      `@warp` + settle + park + 2.6 s of grabs):
>
>      | map | scope | scope cells | stands | pass 1 |
>      |---|---|---|---|---|
>      | new_1-1 (layout 1, serves 5) | whole | 8,355 | 192 | 22.4 min |
>      | new_1-2 (layout 2) | whole | 3,930 | 105 | 12.2 min |
>      | new_1-3 (layout 3) | whole | 8,464 | 167 | 19.5 min |
>      | new_1-4 (layout 4) | whole | 10,825 | 201 | 23.4 min |
>      | alberta_in | route ± 6 | 399 | 16 | 1.9 min |
>      | alberta | route ± 6 | 1,543 | 42 | 4.9 min |
>      | prontera | route ± 6 | 3,029 | 79 | 9.2 min |
>      | geffen | route ± 6 | 3,025 | 91 | 10.6 min |
>      | geffen_in | route ± 6 | 349 | 12 | 1.4 min |
>      | prt_church | tuning ± 68 | 1,325 | 39 | 4.5 min |
>      | prt_fild08 | tuning ± 68 | 15,546 | 280 | 32.7 min |
>      | **total, 11 measured maps (24 served)** | | | **1,224** | **142.7 min ≈ 2.4 h** |
>
>      - On top come the RECHECKS (+~7 s for each view that kept animated pixels, at most
>        doubling pass 1) and PASS 2 (≤ 81 stands around each such view before overlap).
>      - Both depend on how many views animate, known only after pass 1. cursor@3 found 4 of 13
>        alberta views animated (the windmill).
>      - Expected: about 3 to 4 h of client time in all. The pass-2 count is reported after each
>        map's pass 1, before pass 2 runs.
>      - The full-map version would have needed ~10 h of pass 1.
>      - ➡️ **CORRECTED 2026-10-15 17:30, from the first live run: ~7 s per stand was wrong. It is
>        16.1 s** (prt_church, 37 stands: median 16.1 s, range 15.8-16.6). The `@warp` line through the
>        UI gate and the typing guard costs ~9 s more than assumed. **Pass 1 = 328.4 min ≈ 5.5 h**
>        for the 11 maps (`anim_region.py plan` now uses the measured figure; per map: prt_church
>        10.5, prt_fild08 75.1, new_1-1 51.5, new_1-2 28.2, new_1-3 44.8, new_1-4 53.9, alberta_in
>        4.3, alberta 11.3, prontera 21.2, geffen 24.4, geffen_in 3.2 min). Each recheck also costs
>        16.1 s. The "3 to 4 h in all" above is superseded: pass 1 alone is 5.5 h, and the rechecks
>        and pass 2 come on top, known per map after its pass 1.
>    - ➡️ **3b. Corrections before any USED measurement (2026-10-15 17:20-17:35; the method is
>      otherwise unchanged):**
>      - **The UI-window exclusion was OFF in the first run.** `measure` built its registry WITHOUT
>        templates (`ui_anchors.default_registry()`), so it located no window on any view. That
>        session (`20261015T171004-demo-anim-region-prt-church`, 38 pass-1 views) was STOPPED at
>        17:20:40 by SIGINT inside the 13-grab phase (nothing typed or held). It is KEPT and NOT
>        USED; its manifest says `stopped:KeyboardInterrupt`. The client was judged clean
>        afterwards.
>        - Fixed: the registry is the UI gate's own template set for the lock's path
>          (`ui_gate._registry(ui_gate._require_ready())`).
>        - Fail closed: a run refuses to start without templates for `basic_info` and `chat`.
>          Both are always open in the GM's fixed state, so every view must locate both, or the run
>          stops for a person. On 2026-10-15's frames the fixed registry locates basic_info (0,0),
>          hotbar (230,0), chat (0,531) and, outdoors, the minimap.
>      - **A window's excluded box is the window AS DRAWN.** The registry's basic_info anchor is its
>        top 220 x 140. The fixed state shows it with the menu expanded, a 4 x 5 icon panel down to
>        client y 326. One icon there (the inventory bag, at ~(94-123, 154-183)) changes in every
>        stopped view at the same screen spot. So basic_info's box is 220 x 328 (`DRAWN_SIZE`).
>      - **The pass-2 count is now printed BEFORE pass 2 runs** (`pass1 / unsettled / rechecked /
>        kept / pass2`), as written above. The first code printed nothing between the passes.
>      - **Checked, NOT changed: the big blobs are real animation, not a warp transient.** The
>        largest stopped view (172,108; 48,211 px) is a WARP PORTAL's effect, the blue ring and its
>        pulsing glow. A diagnostic `@warp` there (17:27:43, one typed line through the gate) then
>        13-grab measurements WITHOUT re-warping counted 25,031 / 23,567 / 25,046 / 25,742 / 26,087
>        px at +6 / 30 / 60 / 120 / 180 s. So re-warping for the recheck does not manufacture them.
>        The screen-space union of the views looks huge only because the camera follows the GM:
>        the same portal is drawn at a different place in each view.
>      - A dry re-count of the stopped views with the corrected boxes (fixed-state window
>        positions; not used) keeps counted pixels in 29 of 38. Most views are therefore rechecked,
>        and pass 2 will be large where a portal is in view.
>      - ➡️ The re-run at a516b88 (`20261015T173259`) locates basic_info, hotbar and chat on every
>        view. With the locate a stand takes **19.9 s** (18.6-20.2; ~3.3 s of template matching),
>        so **pass 1 = 406.0 min ≈ 6.8 h** for the 11 maps (`plan`). Its pass 1: 39 stands, 0
>        unsettled, 29 rechecked, **29 kept**.
>    - ➡️ **3c. Pass 2 corrected before it ran (2026-10-15 17:55-18:10).** The re-run printed
>      **pass 2 = 851 stands** for prt_church (~4.7 h plus rechecks). There were two defects:
>      - each kept stand got its OWN step-3 lattice, aligned to itself, so overlapping squares
>        never merged ("<= 81 stands around each such view before overlap" assumed they would);
>      - pass 2 ran on every stand cell, not the scope's.
>      - **Fixed:** pass 2 is ONE map-wide step-3 lattice (the same origin as pass 1) over the
>        union of the radius-12 squares, on the scope's stand cells only. The squares choose the
>        lattice POINTS; a point moves (<= 3 cells) only onto a stand cell.
>      - **Reproduced offline from the session:** kept 29 of 39 (as live); the old rule 851 (as
>        live); **the corrected rule 190 stands**, nearly the whole 1,325-cell scope at step 3,
>        because the portals are seen from almost everywhere.
>      - The run was STOPPED at 17:55:54 by SIGINT inside a grab, after 4 pass-2 views. Nothing was
>        typed or held, and the client was judged clean afterwards. Its pass 1 and rechecks are
>        complete and are USED.
>      - **`measure --pass2-from SID`** runs pass 2 (and its rechecks) from an earlier session's
>        complete pass 1 (refused when a kept view lacks its recheck).
>      - **`--max-pass2 N`** ends a run after pass 1 when pass 2 would exceed N stands, so the count
>        and the time reach Batt before a large pass 2. The pass-2 line now prints its estimate.
>      - **`build` fails closed on unconfirmed views:** a view with counted pixels that was
>        measured once (its recheck never ran, as in a stopped run) is dropped as `unconfirmed`. Its
>        cells count neither as animated nor as measured. Before this, they counted as measured.
> 4. **Client GAT ∩ server map cache** (Batt, decision 4: "every walk rule and planner uses only cells
>    walkable in BOTH sources (intersection)").
>    - walk@17's planner blocks, its harness hides, and its click step refuses
>      (`no_safe_point`, `server_nopass`) every cell the client's GAT calls walkable and the server's
>      map cache calls NOPASS. This is the same mechanism as B and amendment 2.
>    - **Inert on every tuning and held-out map:** prt_church, prt_fild08, alberta_in, prontera and
>      iz_dun00 have 0 such cells (prontera's 46 disagreements are server-walkable / client-not,
>      which the client never offers).
>    - **It acts in tour@1's alberta block:** 4,836 such cells on alberta (and 4,482 on morocc, which
>      walk@17 does not use).
>    - Built on `feat/map-agreement` (a shared `poring_dataset.walkable`). Its proofs are recorded
>      here when it merges. ➡️ **MERGED 2026-10-15 12:11:30 ICT (f0ff35c..8846a4c), before any tuning
>      run:**
>      - every plan blocks those cells, for every intent (portal plans too); the harness's world
>        hides them in every scene; the click step refuses one (`no_safe_point`,
>        `"server_nopass": [x, y]`), the portal click too; a map either source lacks refuses the
>        run; the manifest records `walkable: client∩server` and `server_nopass_cells`
>        (`test_walk17.py`, 30 tests, 5 of them new);
>      - **inert on the tuning maps, proven:** prt_church gains 0 blocked cells. prt_fild08 gains
>        799, all on the server's last row / column (always NOPASS on the server) and none
>        8-adjacent to an interior walkable cell. The harness's seeded draws and every route's
>        plan and leg split, simulated for this section's seeds 20261150-57 (56 routes each), are
>        IDENTICAL before and after in all eight runs;
>      - nearly every client GAT marks the server's last row and column walkable. iz_dun00 has 4
>        such edge cells that touch interior walkable cells, so there it can act; its simulated
>        held-out run was identical too;
>      - `bytecode_proof.py walk15` (main vs the change): **PASS**, 1,092 items, 0 changed. walk5,
>        6, 11-14, 16, rule_run, where_run and the other frozen tools: PASS, 0 changed;
>      - the per-map counts are L3 `map.walkability` (`kb_bindings.py`); the cells are in
>        `data/kb/map_agreement.json` (`scripts/map_agreement.py build`, local).

**Expected** (Claude's reading of walk@15's four tuning sessions, re-read offline 14:25 ICT; NOT a
bar):
- **Outdoors ≈ walk@15 (49, 48).**
  - walk@15's outdoor runs never relocalised: 0 in-route relocalisations and 0 route-start fixes in
    100 routes. The single minimap read gave every start. So A changes nothing there.
  - B and C never act there: no warp cell lies within 20 cells of (268, 107), and the routes are
    8–20 steps.
- **Indoors, A is expected to COST routes, through the typing guard's REPEAT rule.**
  - The guard refuses a 3rd identical line of a kind in a row. Its count spans time and runs, and
    only another slash line resets it. walk@17 types no other slash line (the GM commands are
    chat-kind lines).
  - So walk@17 can type /where at most twice in a row: in practice at most 2 per run, and none if
    the host's guard state already ends with two /where. At 14:16 ICT the live state held one
    (3.29a's re-runs): the first indoor run would get one /where, the next none.
  - walk@15's indoor runs fixed all 50 route starts by /where. They also relocalised 8 (clean) and
    18 (crowd) times inside routes, in 5 and 9 routes, all on `unconfirmed` doubts.
  - Of their 46 and 43 successes, 40 and 30 used neither an in-route relocalisation nor an
    unnamed-after-fix click. Those are the routes walk@17 can be expected to keep without /where.
    The others decline `relocalise_failed` at their first doubt. Dead-reckoned route starts (no
    start fix) can add failures.
  - ⇒ indoor clean ≈ 40, indoor crowd ≈ 30: both FAIL the per-run bar. Pooled ≈ 167 / 200 =
    83.5 %: **NOT READY is expected under the guard as it stands.**
  - The budget (56) and the retry interval (60 s) would bind only if the repeat rule did not.
    Route starts come every ~42 s (clean) and ~60 s (crowd), so even then about half of them would
    go unfixed.
- **B** is inert on the tuning maps (geometry, above). It acts on the held-out guild map (58
  walkable warp cells within 20 cells of its start) and in tour@1.
- **C** never fires in tuning (routes 8–20 steps). tour@1 measures it.

**Found while building, for Batt BEFORE the tuning runs** (nothing here is decided by this
pre-registration):
1. **The repeat rule vs "/where once per need"** (the expected indoor loss above).
   - Only a change to the guard can lift it. The guard is the typing transport, not walk@17's
     decision code.
   - A deliberate measurement would show whether the client's own repeat count lapses with time:
     /where, ≥ 60 s, /where, ≥ 60 s, /where, ≥ 60 s, /where. Is the 4th answered?
   - If the guard changes before the runs, the change is recorded here first.
   - ➡️ **DECIDED (Batt, 2026-10-13, decision 15):** "'/where once per need' wins over the repeat
     rule". The typing guard must not refuse a needed /where as a 3rd identical line. The retry
     interval and the run's budget stay. A /where the CLIENT drops is no fix, and the rule goes on
     as for a miss. It is built and recorded as a walk@17 amendment before its tuning runs.
2. **iz_dun00 is not in route.json's warp list** (kb_route.py's scope: 44 maps).
   - B cannot hold there, so walk@17 refuses to start there until the KB covers it. That blocks
     the held-out dungeon map and tour@1's iz_dun00 block.
   - The KB's own `warps.json` lists 3 warps there. One is the exit to izlu2dun at (168, 173) ± 3 ×
     3, 5 cells south of the scene's start.
   - ➡️ **2026-10-09: superseded.** 2f69c85 added iz_dun00's warp file. Then
     feat/labels-v2-prep (~21:15) made `kb_route.py` take the first-workflow KB's COMPLETE list
     (every file the server loads) for each map that KB covers. route.json now lists 107 maps:
     the 20 training-ground copies and the Merchant route maps are among them, and an empty list
     means "no portal". `REQUIRED_WARP_MAPS` fails the run closed when one is missing. Per-map
     counts are in labels-v2-plan.md 7.6 (G4).
3. **The harness's start draw is not covered by B.**
   - Every 5th route, `@warp` goes to a walkable cell within ± 8 of the scene's start, with no plan
     check. That is walk@11's harness, bytecode-frozen for walk@15.
   - It can land INSIDE a trigger area: 8 of 181 candidate cells on alberta_in (the (64, 31) area),
     and 25 of 231 on iz_dun00 (by warps.json). None on the tuning maps or on prontera.
   - A fix is a harness change, with Batt.
   - ➡️ **DECIDED (Batt, 2026-10-13):** "never draw a harness start inside a warp area" -- a walk@17
     amendment before its tuning runs.
4. **Measured, not built:** the server's own path to a click could cross a warp area even when the
   clicked cell lies outside one. On harness-like routes it never did: 0 of ~20,000 click cells on
   alberta_in and 0 of ~20,000 on prontera (offline, the GAT's own A*).
5. **➡️ Added 2026-10-09 ~15:05, from 3.29a's town re-run: TWO `npc_contact` with walk@15's
   decision code, which walk@17 keeps unchanged** (walk17.md E).
   - Both times the cursor read WALK, the walk marker was drawn, and the detector envelope held 0
     units.
   - Contact 2 came through the TALK-read NPC substitute: its remembered talk cells were one column
     off the NPC's true cell.
   - walk@17's tuning bar needs zero safety. Whether a fix comes before its tuning runs is Batt's
     call. Per his rule for F, any fix comes with a targeted test that can measure it.
   - ➡️ **DECIDED (Batt ~15:20, ~16:10, ~16:15):**
     - **A targeted test first:** dense-NPC town spots and deliberate clicks near NPCs, measuring the
       cursor, the detector and the remembered talk cells; find why the cells were one column off.
     - **Fold in:** the TALK read rate per NPC / position / background, and why the cursor's colour
       check fails (3.30).
     - **The detector's recall on town NPCs** against packet truth, per sprite: it boxed none in Batt's
       16:04 screenshot.
     - **For walk@17, a STATIC NO-CLICK layer:** the L3 NPC cells plus their clickable footprint,
       refused in the walk gate independent of the detector. The cursor and detector layers stay
       for moving / hidden NPCs and units.
     - **The test measures whether that layer ALONE removes the town contacts.**
     - Analysis, design and harness: branch `feat/npc-click-test` (offline; nothing run live). The
       layer is integrated into walk@17 as a recorded amendment before its tuning runs.
     - ➡️ **OFFLINE RESULTS (merged 70e851d; `docs/planning/npc-click-test.md`, PROPOSED, its DRAFT
       pre-registration in section 6):**
       - **The "one column off" cause:** the remembered talk cell is the FLOOR cell under the TALK
         pixel, i.e. the click TARGET, never the NPC's cell (24 / 24 reproduced, only 2 / 24 are an
         NPC's true cell). Route 55 had TWO NPCs, and the job-722 flag at (155,190) IS in the
         remembered column.
       - **Contact 1's NPC:** job 722 is a guild flag; 5 stand in prontera's centre. Their script
         files are not read by kb_route.py, so today's L3 does not know them.
       - **Why WALK read over them:** not determined offline (H-a/b/c, separated by the test).
       - **The colour check:** "col 0.0" is a placeholder for any unknown. The real margins are thin
         (leave-one-out colour minimum 0.851 against a floor of 0.85), and a 1-px reference shift
         reproduces the live failure. Hypotheses C1–C5 are separated by the test's crops.
       - **The detector on town NPCs:** 1 / 2,195 sightings boxed (Wilson 0.01–0.26 %); 1 of 13 NPCs
         was ever boxed. Batt's 16:10 reading is confirmed.
       - **The L3 NO-CLICK layer** (`scripts/npc_noclick.py`; footprint PROVISIONAL): with today's
         L3 it refuses contact 2 but not contact 1 (the flags are missing). With a complete L3 it
         refuses both, at a cost of 10 refused clicks in 6 of the 50 scored routes. It fails closed
         unless a map's NPC list is declared COMPLETE: the KB extension P1 (every NPC file the
         server loads) gates both the layer and the test.
       - **loot@1 P3 (above) hit the same cursor weakness** over Porings (64 % unknown).
     - ➡️ **The cut-in mask** (Batt 16:10) is BUILT and merged (2834541, `scripts/ui_mask.py`), NOT
       deployed.
       - Measured: the guide's cut-in at (957,249)-(1183,720), pixel-identical across sessions.
       - The "monster 31 %" phantom is masked on 120 / 120 open frames.
       - Other NPCs' cut-ins and other anchors are unmeasured, so not masked.
       - The HUD applies it after a restart of the HUD process. walk@17 gets a patch point (an
         amendment); loot1's `in_ui` now uses the shared mask (equivalence-tested).
6. **➡️ Added 2026-10-09 ~15:05, from 3.29a's portal re-run: a chain must JUDGE the client's UI state
   between runs, not only screenshot it.** An NPC dialog left open by one run took the next run's
   Enter presses.
   - This is a harness change: refuse to start a run while a dialog or window is open, judged from
     pixels, and log it.
   - How such a dialog is closed (a human-like cancel, or a stop for Batt) is Batt's call.
   - ➡️ **DECIDED (Batt ~15:20): MANDATORY for every harness** ("every harness checks the UI state
     from pixels before typing anything (open NPC dialog, menus, windows) and closes it only by
     known steps; never press Enter into an unknown state").
   - ➡️ **BUILT + PROVEN LIVE (2026-10-09 ~16:10):** `scripts/ui_gate.py`, called by `ro_agent.open_chat`
     (so every `chat_line` / `gm` / `say` / where_fix line) and `bench.close_chat`.
     - **What it reads, on two fresh frames that must agree, the cursor parked:**
       - the NPC dialog / menu by talk@1's T2 (proven 168 / 168 held-out, 3.30);
       - the four windows with cut anchors (status, skills, inventory, equipment), each within
         12 px of where the client reopens it.
     - **Its only known closing steps:** Enter on a dialog showing CLOSE with no menu; a window's own
       L2 chord.
     - **Everything else STOPS** (NEXT, a menu, unreadable, unstable, missing templates, a non-RDP
       path), with nothing typed and a frame saved. Every check is logged in
       `data/ro_agent/ui_gate.jsonl`.
     - **Cost:** ~1.5 s per typed line in a running process (~3 s for the first, which loads the
       templates).
     - **Positive cases (live, deliberate):**
       - `ui_gate.py prove-windows`: each of the four windows opened by its chord was seen (home box
         = full-frame locate) and closed by its chord: 4 / 4 PASS.
       - The city guide, session `20261009T160329-demo-talk-cal-guide`. The gate STOPPED on the
         dialog's NEXT (the server saw no click until the drive's own Enter 12 s later) and STOPPED on
         the menu (no choice until the drive's keys). On CLOSE its one Enter became the server's
         `npc_close_click`, then clear.
     - **Gaps, stated:** windows without a cut anchor (the options window, a shop, a trade), and one
       of the four dragged away from its home, are not seen.

### 3.32a npc-click@1 -- the NPC-click targeted test (walk@17 item 5; pre-registered 2026-10-09 ~21:25 ICT / 14:25 UTC at commit c5c149d, BEFORE any run; Batt 2026-10-09 ~15:20, ~15:50, ~16:10, ~16:15, ~19:30; the weekend run ~20:20: "Item 5 targeted town NPC test (L3 no-click layer, TALK read rate) after the cursor work")
Pasted from `docs/planning/npc-click-test.md` section 6 (the DRAFT), with its placeholders filled.
Its PROBE arm is also arm A of cursor@1 (3.35): the same crops are scored offline by both readers.
**What it measures** (nothing here is a pass / fail of walk@17):
- where the client shows TALK around town and church NPCs, and how often the TALK read fails the
  colour check, per NPC / position / background; why, from the saved crops;
- how often a click the walk gate allows (WALK read twice) beside an NPC becomes `npc_contact`;
- whether the L3 no-click layer ALONE (complete L3, PROVISIONAL footprint) refuses those contacts,
  and at what cost;
- the detector's recall on the same NPCs, and walk@12's remembered TALK cells against packet truth.

**The harness:** `scripts/npc_click_test.py` at c5c149d (`probe`, then `click`), scored by
`scripts/npc_click_score.py score` at the same commit. Spots, points, clicks, the dialog policy and
the metrics as in `docs/planning/npc-click-test.md` 5.2-5.5.
- prontera: `--near 156,191 --seed 20261160` (6 NPCs); prt_church: `--near 103,74 --seed 20261161`
  (its 2 NPCs within 12 cells).
- Pilot first, never scored: `--npcs 1 --reps 1`, seeds 20261162 (prontera) / 20261163 (prt_church).
  Any harness fix is committed (and recorded here) before the scored runs.
- Order: the probe arm (hover only) on both maps first, then the click arm; each arm judged offline
  (its packets) before the next one runs.

**Prerequisites:** P1 -- the complete L3 NPC list for both maps, checked against their packets:
DONE 2026-10-09 (0c8120a, merged 748260d: `data/kb/npc_cells.json`, prontera 16 / 16 objects at
cell and sprite incl. its 13 drawn NPCs in the town re-run 20261009T140625, prt_church 19 / 19 with
the 6 wedding-row NPCs sent invisible and marked `conditional`; `npc_noclick.py cells` reports both
COMPLETE); T2 (3.30, proven 168 / 168); the CPU detector (`/dev/shm/poring-lab-detector`); the GATs.

**The dialog policy:** after every click, two T2 frames. None: go on. CLOSE on both: Enter, then gone
on two frames. NEXT or a menu: talk@1's decline (`talk1.decline_all`, Batt ~19:30), then gone on two
frames. Anything else, or a failed decline: STOP for a person (exit 7); `--resume` after Batt closes
it. (In an unattended weekend window a stop parks the test until a person is back; the parent does
not close an unknown state by itself.)

**Decision rule for the layer** (reported, not a walk@17 bar): "the layer alone removes the town
contacts" when, in prontera's click arm, every `npc_contact` click is refused by the complete layer
AND no click the layer allows becomes `npc_contact` (reported with the Wilson upper bound of that
rate and the share of moves the layer refuses).

**Safety:** contacts are the measurement on the lab server. Every opened dialog is closed by the
policy above or by a person. An `attack_request` or a GM act of kind normal / pickup is a safety
event: the harness cannot see packets, so each arm is judged offline before the next one runs, and
any such event ends the test until Batt decides. The GM stands only on known cells (`@warp`).

**Reported:** every metric of npc-click-test.md 5.5 per map, with Wilson intervals; the stops and
their causes; the measured footprints per job; which fix (5.7) each result points to.

**➡️ INTERIM (2026-10-10 00:50 ICT): the PROBE arm is COMPLETE on both maps; the CLICK arm is PARKED
(stopped for a person).**
- **Pilots (never scored):** probe prontera `20261009T215405` (156 probes), probe prt_church
  `20261009T232306` (156), click prontera `20261010T000550` (5 `npc_contact`, all declined by
  `talk1.decline_all`: NEXT, then the menu Cancelled; 17 moves; 0 attack). No harness change.
- **Probe arm, scored** (`npc_click_score.py score`, the gate's own reads; safety EMPTY in both: 0
  attack / contact / pickup / move requests, 0 GM acts):

| | prontera `20261009T220521` | prt_church `20261009T233300` |
|---|---|---|
| probes (planned) | 1,517 (1,566) | 566 (566) |
| gate TALK reads, sprite points | 378 / 721 = 0.524 | 150 / 248 = 0.605 |
| gate TALK reads, cell points | 212 / 734 = 0.289 | 34 / 256 = 0.133 |
| colour-check fails (unknown, best IoU >= 0.6) | 149 / 1,517 = 0.098 (job 700: 74 / 250 = 0.296) | 37 / 566 = 0.065 |
| DETECTOR, NPC sightings boxed | **0 / 7,816** (0 boxes in all 1,517 batches) | **378 / 1,008 = 0.375** (job 67 252/504, job 120 126/504) |
| walk@12's remembered TALK cell = the NPC's cell | 28 / 590 | 26 / 184 |

  - The detector's zero in prontera is real, not a dead sensor: the same CPU detector found the
    Poring in all 30 of cursor@1 arm B's trials that night and boxed church NPCs in 252 batches.
  - The TRUTH-labelled TALK rates (both readers, blind labels) are in 3.35: gate 0.856, robust 0.967.
- **Click arm prontera, scored `20261010T001818`: STOPPED FOR A PERSON** at its 18th record
  (`stop:unread:button_unknown`). The city guide's (job 105) first page with NEXT is open. The click
  that opened it was at client (470, 270), where the dialog's NEXT button then sat: the reader most
  likely saw a hovered or covered button, a state its templates lack (the pilot declined the same
  page 5 times). Up to the stop: 3 `npc_contact`, 9 moves, 0 attack, 0 GM acts. **Not closed by the
  parent** (the policy above). Next: a person closes it, then `npc_click_test.py click --map prontera
  --seed 20261160 --near 156,191 --resume 20261010T001818-demo-npc-click-click-prontera`; the church
  click arm after it.
  - **Root cause, found offline (01:05) on the still screen** (the cursor far away): T2 still reads
    `button_unknown` -- the NEXT button is drawn in its blue HOVER/FOCUS state (distance 28.7 to the
    plain NEXT template, accept <= 6.0). The click landed where the button then appeared.
    ~~the harness's park is a single jump~~ ➡️ CORRECTED the same minute: talk@1's park
    (`talk1.LiveIo.park`) is already TWO motions (3 px off, then the point, 0.6 s settle), and the
    highlight stayed. Whether it is a hover the client does not release or a keyboard focus is
    unknown.
  - **Fix option (a reader change: Batt's call at resume, recorded here before use):** add the
    highlighted-NEXT look as a T2 template, cut from a labelled frame and proven like prove-t2;
    resuming with it alters the reader for the remaining clicks of this scored run.
  - ➡️ **DECIDED (Batt, 2026-10-13, decision 2):** "the highlighted-NEXT T2 template, then resume
    npc-click's click arms". **AMENDMENT before the resume:**
    - the remaining clicks use T2 with the highlighted-NEXT template (cut and proven first);
    - they use the cursor gate AS SWITCHED the same day: robust2 (3.36's ADOPTION). The first 18
      records of the prontera click arm were read by v3.
    - The scorer reports the two segments apart. The resume command is unchanged otherwise
      (`--resume 20261010T001818-demo-npc-click-click-prontera`); then the church click arm.
  - ➡️ **THE NEXT_HI PROOF, ATTEMPT 1 (2026-10-13 12:58-13:08 ICT, RDP, the GM; NOT installed): FAIL,
    104 / 110.** The candidate set = the installed T2 set (data/ui_anchors/npc_dialog, cut 10-09)
    + `npc_dialog_next_hi.npy` (sha256 `695a0e0d406352f7...`, cut from the 10-10 00:23 stop frame).
    `talk_calibrate.py prove-t2` (its rule unchanged: >= 50 labelled frames, EVERY one agreeing with
    the packets, >= 1 frame of each class) on two FRESH sessions, never used by any cut:
    - `20261013T125826-demo-talk-cal-guide`: `drive --npc guide --first 2`, 60 frames; T4 / T5 PASS;
    - `20261013T130007-demo-talk-cal-guide`: the same dialog by single steps, with `hover next --n 4`
      (the cursor ON the button, no click) and then parked frames on each of the two NEXT pages;
      52 frames; T4 / T5 PASS.

    | set | labelled | agree | the disagreements |
    |---|---|---|---|
    | installed | 110 | 94 | the 10 PARKED frames after a hover: the button stays blue with the cursor ~800 px away -> `button_unknown` (the 10-10 stop, REPRODUCED twice) + the 6 below |
    | **candidate (+ NEXT_HI)** | 110 | **104** | **6, all IN-PLACE hover frames** (0009-0011, 0027-0029): the cursor itself drawn over the button -> `button_unknown` |

    - Every PARKED frame agrees with the candidate (104 / 104), the 10 highlighted ones included.
    - **The finding:** the highlight is sticky. A hover leaves NEXT blue after the cursor goes
      (both pages); a menu step clears it. That is how the 10-10 click arm stopped.
    - **Why the 6 do not reach the live reader** (a fact of the code, found after the result, so it
      changes nothing above): T2 is only read with the cursor parked (`talk1.LiveIo.observe` parks
      before every read, `scripts/talk1.py:579-581`; the UI gate parks too). The in-place frames were
      my own addition today (`hover`, 2d2223e), and 10-09's proof had none. They fail closed (an
      unknown button presses nothing).
    - The result stays a FAIL. The template is NOT installed on it.
  - **THE NEXT_HI PROOF, ATTEMPT 2: PRE-REGISTERED 2026-10-13 13:09 ICT (commit 4d4666b), before its data (S1 started 13:09:27).**
    - **The change, stated before the data:** the `hover` step's in-place frames go to `in_place/`.
      They are kept as evidence and never labelled (`talk_calibrate.grab_frames`, IN_PLACE_DIR;
      test_talk_calibrate). Parked frames are labelled exactly as before. The candidate set and
      prove-t2's rule are unchanged.
    - **FRESH sessions** (the client's UI judged on a screenshot before each):
      - S1 `talk_calibrate.py drive --npc guide --first 3` (the other allowed first option);
      - S2 `contact --npc guide`. On each NEXT page: `frames --n 4`, `hover next --n 4` (in place),
        `frames --n 6`, then `key Enter --n 4`. Menus by keys to the same options as `drive --first
        2`. CLOSE by Enter, `frames --n 6`, then `collect`.
    - **PASS:** prove-t2 PASS on S1 + S2 with the candidate set, AND >= 8 labelled frames that the
      installed set reads `button_unknown` and the candidate reads NEXT. Fewer than 8 =
      INCONCLUSIVE: the highlight did not show, so nothing is proven.
    - **Reported only:** the installed set's result on the same frames, and the candidate's reads
      of the in-place frames.
    - **On PASS:** `npc_dialog_next_hi.npy` is copied into data/ui_anchors/npc_dialog/ and its
      sha256 read back. Then the click arms resume, per the amendment above.
      - The template feeds every T2 reader (talk@1, npc-click, the UI gate).
      - The UI gate still STOPS on any dialog showing NEXT. A highlighted NEXT only turns its
        `button_unknown` stop into a NEXT stop.
    - **On FAIL or INCONCLUSIVE:** nothing is installed. Stop and report to Batt; the click arms
      wait.
  - ➡️ **ATTEMPT 2 RESULT (2026-10-13 13:09-13:13 ICT; scored 13:14): PASS. INSTALLED.**
    - Sessions: S1 `20261013T130927-demo-talk-cal-guide` (drive `--first 3`, 78 frames) and S2
      `20261013T131115-demo-talk-cal-guide` (single steps; 50 labelled + 8 in place). T4 and T5
      PASS on both.

      | set | labelled | agree | classes (next / menu / close / none) | verdict |
      |---|---|---|---|---|
      | **candidate** | 128 | **128** | 52 / 54 / 10 / 12 | **PASS** |
      | installed (reported) | 128 | 116 | same | FAIL: the 12 parked highlighted frames -> `button_unknown` |

    - **The highlight bar:** 12 labelled frames that the installed set reads `button_unknown` and
      the candidate reads NEXT (needed >= 8). They are S2 0008-0013 and 0028-0033: both NEXT pages,
      after their hovers.
    - **In place (reported only):** 8 / 8 `button_unknown` with both sets (fail closed).
    - **Installed** ~13:15: `data/ui_anchors/npc_dialog/npc_dialog_next_hi.npy`, sha256
      `695a0e0d406352f76446ae11fc240b3f5fc2f2cf4dccdaa6443cd165e98d57c9`, read back equal.
      `talk1.TEMPLATES` loads it.
    - Next, per the amendment: the prontera click arm resumes, then the church click arm.
  - ➡️ **THE PRONTERA CLICK ARM, RESUMED (2026-10-13 13:19-13:54 ICT, robust2 + NEXT_HI): STOPPED
    FOR A PERSON again, at record 139 (click 138).**
    - The session `20261010T001818-demo-npc-click-click-prontera` had been deleted from /dev/shm
      by Monday's cleanup, after it was verified on the NAS. It was restored from the NAS first:
      checksums 20 / 20, the manifest byte-identical. Then `--resume`, the command unchanged.
    - 121 records were added (18 -> 139).
    - **The stop:** click 138 at (148,204), beside YuNA (`npc/cities/prontera.txt:87`, cell
      (149,202)). The robust2 series read walk 5 / 6, so it clicked; the L3 layer, recorded and
      not applied, would have refused it. YuNA's dialog opened.
      - talk@1's decline clicked NEXT five times, and NEXT_HI read each of those pages.
      - Her last page shows CLOSE in the same STICKY highlight: the decline's clicks left the
        hover on the button's place. T2 reads it `button_unknown` (distance 29.7 to CLOSE, 15.55
        to NEXT_HI), so the result was `stop:dialog_next`, and per the policy no key was pressed.
    - **DECIDED (Batt, 2026-10-13 ~14:10):** "Yes, prove then resume". A highlighted-CLOSE
      template (CLOSE_HI) is built, pre-registered and proven like NEXT_HI, then the arm resumes
      with it. A person closes YuNA's dialog first.
  - **THE CLOSE_HI PROOF: PRE-REGISTERED 2026-10-13 14:15 ICT (a69f518), before its data** (code 74533e9;
    the method of NEXT_HI attempt 2, unchanged):
    - **Candidate set:** the installed T2 set (NEXT_HI included) + `npc_dialog_close_hi.npy`,
      sha256 `1995cabbaf9a7d9144bd7005e28ab4c05764833b2e9b301fe4ba9750cfff67fc`. It was cut from the
      stop frame (`shots/q3-click-stop.png`, dialog origin (201,101)).
    - **FRESH sessions** (a judged screenshot before each; the hover's in-place frames are kept
      apart, never labelled):
      - S1 `talk_calibrate.py drive --npc henson --first 2`;
      - S2 the guide by single steps, as NEXT_HI attempt 2's S2:
        - on each NEXT page: `frames --n 4`, `hover next --n 4`, `frames --n 6`, `key Enter --n 4`;
        - menus by keys as `drive --first 2`;
        - on the CLOSE page: `frames --n 4`, `hover close --n 4`, `frames --n 10`, `key Enter
          --n 6`;
        - then `collect`.
    - **PASS:** prove-t2 PASS on S1 + S2 with the candidate set, AND >= 8 labelled frames that the
      installed set reads `button_unknown` and the candidate reads CLOSE. Fewer than 8 =
      INCONCLUSIVE. NEXT_HI's highlighted frames in S2 must still read NEXT; prove-t2 counts them.
    - **Reported only:** the installed set's result; the candidate's reads of the in-place frames.
    - **On PASS:** install, read the sha256 back, then resume the prontera arm (`--resume
      20261010T001818-demo-npc-click-click-prontera`, unchanged). The scorer reports its THREE
      segments apart: v3; robust2 + NEXT_HI; robust2 + NEXT_HI + CLOSE_HI.
    - **On FAIL or INCONCLUSIVE:** nothing is installed; report to Batt.
  - ➡️ **THE CLOSE_HI PROOF, RESULT: PASS, INSTALLED.** Batt closed YuNA's dialog at 14:31. The sessions
    ran 14:31-14:37 ICT and were scored at 14:37.
    - S1 `20261013T143147-demo-talk-cal-henson`: drive `--first 2`, 108 frames.
    - S2 `20261013T143410-demo-talk-cal-guide`: 64 labelled + 12 in place.
    - T4 and T5 PASS on both.

      | set | labelled | agree | classes (next / menu / close / none) | verdict |
      |---|---|---|---|---|
      | **candidate** | 172 | **172** | 64 / 72 / 24 / 12 | **PASS** |
      | installed (with NEXT_HI; reported) | 172 | 162 | same | FAIL: the 10 parked highlighted CLOSE frames -> `button_unknown` |

    - **The highlight bar:** 10 labelled frames that the installed set reads `button_unknown` and the
      candidate reads CLOSE (needed >= 8).
    - NEXT_HI, live since ~13:15, read S2's highlighted NEXT pages as NEXT; prove-t2 counts them.
    - **In place (reported only):** 12 / 12 `button_unknown` with both sets.
    - Enter on the highlighted CLOSE closed the dialog (`npc_close_click` 1).
    - **Installed** 14:38: `data/ui_anchors/npc_dialog/npc_dialog_close_hi.npy`, sha256
      `1995cabbaf9a7d9144bd7005e28ab4c05764833b2e9b301fe4ba9750cfff67fc`, read back equal.
      `talk1.TEMPLATES` loads both highlighted looks.
    - Next: the prontera arm resumes (segment 3).
  - ➡️ **THE PRONTERA ARM, SEGMENT 3 (14:39-14:42, robust2 + NEXT_HI + CLOSE_HI): STOPPED after ONE
    click (record 140, click 139).**
    - Click 139 at (148,202), beside YuNA again (stand (149,205)): the series read walk 5 / 6, then
      `npc_contact`. Her FIRST page (NEXT) opened.
    - T2 read it `npc_dialog_uncertain`: mismatch 0.008 (accept 0.03), but the EDGE share was 0.0868
      (accept 0.05).
    - **Cause, measured on the frame:** the right part of the dialog's bottom border line (from
      column ~104, an RDP codec tile boundary) reads grey 191-192 instead of 198. That is 7 levels,
      just over `pixel_tol` 6.
      - The values were identical on 6 fresh frames over 7 s: stale tiles that never refined, so a
        re-read would not have helped. It failed closed.
    - **DECIDED (Batt, 2026-10-13 ~14:47): "Park prontera; church next."**
      - After a person closes the dialog: prt_church's click pilot, then its scored arm, then the
        rest of the queue.
      - Offline: a T2 border fix that tolerates a per-tile shade offset on the four border lines,
        proven on every banked labelled frame + both stop frames. **For Batt's OK before prontera
        resumes.**
  - **The prontera click arm, PARKED at 140 records** (`npc_click_score.py score` at 5aef29b; the arm
    is NOT complete, so this is not its result):

    | segment | gate / T2 | records | clicked: moves / contacts / nothing | not clicked (TALK twice / unknown / other) | attack_request | GM act normal / pickup |
    |---|---|---|---|---|---|---|
    | 0 (10-10 00:18-00:23) | v3 | 18 | 8 / 3 / 0 | 5 / 2 / 0 | 0 | 0 / 0 |
    | 1 (13:19-13:54) | robust2, NEXT_HI | 121 | 53 / 5 / 1 | 58 / 3 / 1 | 0 | 0 / 0 |
    | 2 (14:42) | robust2, NEXT_HI + CLOSE_HI | 1 | 0 / 1 / 0 | 0 / 0 / 0 | 0 | 0 / 0 |

    - L3 layer (complete here; recorded, never applied): it refuses 9 / 9 contact clicks. 0 of the
      36 clicks it allows became a contact (Wilson 95 % up to 0.096). The cost: 25 / 61 moves
      refused (0.41).
    - A click the walk gate allowed became `npc_contact`: 9 / 71 = 0.127 (0.068-0.224).
  - **THE T2 BORDER FIX: ITS PROOF, PRE-REGISTERED (2026-10-13 14:53 ICT, commit 32d13bb, before it is scored).** Code:
    branch `feat/t2-border-offset` 669a8d3, NOT live.
    - **The change:** `npc_dialog.edge_share`. On the four border lines, the running median of
      (frame - template) over 15 px, clipped to +-12 grey levels, is removed before the 6-level
      test. The window rules are otherwise unchanged.
    - **Its design frames are NOT evidence:** the two stop frames and two clear screenshots were
      looked at while building it.
    - **The proof set:** every banked talk-cal session NOT used by the cut. The installed templates
      (NEXT_HI + CLOSE_HI) are used.
      - 10-09, on the NAS: `20261009T153202-…-garnet`, `154531-…-garnet`, `154601-…-henson`,
        `154802-…-guide`, `160329-…-guide`;
      - 10-13, in /dev/shm: `20261013T125826`, `130007`, `130927`, `131115`, `143147-…-henson`,
        `143410`.
    - **PASS** (all three):
      1. `prove-t2`'s rule with the FIXED reader: every labelled frame agrees with the packets, with
         >= 1 frame of each class.
      2. **No regression:** every labelled frame the CURRENT reader reads correctly, the fixed
         reader reads identically (dialog / menu verdict and button).
      3. **The edge test keeps its job:** no frame labelled no-window or menu-only gets a
         `present` dialog from the fixed reader. Rule 1 counts this; it is reported apart.
    - **Reported:** per session, how many frames change their verdict, and the edge share before and
      after; the two stop frames' reads (design checks).
    - **On PASS:** it is offered to Batt. It goes live only with his OK (a merge), and the
      prontera arm then resumes as segment 4. **On FAIL:** not offered; reported.
  - ➡️ **THE BORDER FIX'S PROOF, RESULT (scored 14:53-15:03: proof.json 14:58, proof2.json 15:03 with rule 3 coded as written): FAIL as pre-registered, on rule 1
    ONLY.** It is NOT offered as proven. Batt decides.
    - 598 labelled frames from 11 sessions (no window 56, NEXT 214, menu 268, CLOSE 60).
    - **Rule 1: FAIL.** 6 frames disagree with BOTH readers identically (`button_unknown`): S2
      0009-0011 and 0027-0029 of `20261013T130007`.
      - These are NEXT_HI attempt 1's IN-PLACE hover frames (the cursor on the button). They sit
        in that session's labelled `frames/` because the in-place split came after it.
      - Including that session was MY error in the proof set. The rule is kept as written, so the
        result stays FAIL.
    - **Rule 2: 0 regressions.** The fix changes the verdict on **0 of 598** frames.
    - **Rule 3: 0 false `present`** on frames whose label has no dialog. The first scoring script
      tested "menu" frames as menu-only; a guide menu shows the dialog too. The script was fixed
      to the written rule (the label's dialog flag) BEFORE this number, and rule 1's result is
      unchanged.
    - **Design checks (not evidence):** the third stop's frame reads NEXT (edge 0.0046 instead of
      0.0868); the second stop's reads CLOSE.
    - **What it means:** on banked frames the fix is inert. It only acts on a codec-shifted
      border like the third stop's. Whether to adopt it, or to re-prove it on a corrected set,
      is Batt's call. Until then the prontera arm stays parked.
  - ➡️ **The church click arm, scored `20261013T151312` (15:13-15:24; the pilot `20261013T150450`
    first: 26 clicks, 21 moves, 0 contacts, 0 safety events, no stop, no harness fix): STOPPED
    FOR A PERSON at record 38.**
    - Click 37 at (103,77), beside Garnet (`prontera.txt:532`, cell (103,76)). The series read
      walk 5 / 6, then `npc_contact`. Her first page (NEXT) opened, and T2 read it
      `npc_dialog_uncertain`: edge 0.1516, the SAME codec border shift.
    - **The border fix (669a8d3) reads this frame as NEXT** (edge 0.0081). The frame came at 15:24,
      AFTER the fix was committed, so it was not a design frame.
    - Up to the stop: 38 records (33 moves, 2 contacts; 1 TALK and 1 unknown not clicked; 1 without
      a safe point). Safety: 0 attack_request, 0 GM act normal / pickup.
    - L3 layer (recorded, not applied): it refuses 2 / 2 contacts. 0 of the 26 clicks it allows
      became a contact. The cost: 7 / 33 moves refused.
    - **DECIDED (Batt, 2026-10-13 ~15:27): "Re-prove on a fresh set first."** Both arms stay
      parked until then. Batt closes Garnet's dialog.
  - **THE BORDER FIX, ATTEMPT 2: PRE-REGISTERED (2026-10-13 15:26 ICT, commit 37b78e5, before its data).** Code: 669a8d3,
    unchanged.
    - **FRESH data:** RDP talk-cal sessions recorded AFTER this commit. Their in-place hover frames
      are kept apart by code since 4d4666b. At least:
      - `talk_calibrate.py drive --npc merchant --first 2` (the queued merchant decline drive);
      - `drive --npc guide --first 3`;
      - `drive --npc henson --first 3`.
      - It needs >= 150 labelled frames with every class, else INCONCLUSIVE.
    - **PASS** (all three, on the fresh frames, with the installed templates):
      1. prove-t2's rule with the FIXED reader: every labelled frame agrees, >= 1 frame of each class;
      2. no regression: every frame the current reader reads correctly reads identically with the
         fixed one;
      3. no `present` dialog on a frame whose label has none.
    - **Reported, not bars:**
      - attempt 1's banked set with the 6 in-place frames of `130007` excluded. These frames are
        identified BY STEP KIND: the frames the `hover` step itself grabbed. The numbers are
        already known (592 / 592, 0 changes), so they are not fresh;
      - the click-arm stop frames: the 14:42 YuNA frame (a design frame) and the 15:24 Garnet frame
        (fresh), plus any later one, each with both readers' reads.
    - **On PASS:** the fix is merged (T2 live on RDP). The prontera arm resumes as segment 4, and the
      church arm resumes. **On FAIL / INCONCLUSIVE:** not merged; reported to Batt.
  - ➡️ **ATTEMPT 2 RESULT (fresh drives 15:37-15:43, scored 15:45): PASS. MERGED (fb2b5ac).**
    - Sessions: `20261013T153740-demo-talk-cal-merchant` (Batt's decision 6: the merchant dialog,
      decline path, 66 frames), `153924-…-guide` (`--first 3`, 78), `154115-…-henson` (`--first
      3`, 108). T4 and T5 PASS on all three.

      | | labelled | classes (next / menu / close / none) | current reader | FIXED reader | verdicts changed |
      |---|---|---|---|---|---|
      | **fresh (the bars)** | 252 | 96 / 120 / 18 / 18 | 252 | **252** | 0 |
      | banked, corrected (reported; known) | 592 | | 592 | 592 | 0 |

    - Rule 1 PASS; rule 2: 0 regressions; rule 3: 0 false `present`.
    - **What the PASS shows, and what it does not:** none of the fresh frames had a shifted border
      (0 verdicts changed), so it shows the fix does no harm. The evidence that it HELPS is the
      click-arm stop frames: YuNA 14:42 (a design frame) and Garnet 15:24 (FRESH, n = 1). Both
      read NEXT with the merged reader.
    - **Next:** the S2 UI-gate session (16:00, Batt). After it, the prontera arm resumes as
      segment 4 and the church arm resumes (`--resume 20261013T151312-demo-npc-click-click-prt-church`),
      each scored by segment.
  - ➡️ **THE PRONTERA CLICK ARM: COMPLETE** (segment 4, 17:06-17:17, robust2 + NEXT_HI + CLOSE_HI + the border
    fix: 36 records, no stop). Scored by `npc_click_score.py score` (5aef29b's segments) over its 176 records:

    | segment | gate / T2 | records | clicked: moves / contacts / nothing | not clicked (TALK twice / unknown / stale park / other) | stops | attack_request | GM act normal / pickup |
    |---|---|---|---|---|---|---|---|
    | 0 (10-10) | v3 | 18 | 8 / 3 / 0 | 5 / 2 / 0 / 0 | 1 (highlighted NEXT) | 0 | 0 / 0 |
    | 1 (13:19-13:54) | robust2, NEXT_HI | 121 | 53 / 5 / 1 | 58 / 3 / 0 / 1 | 1 (highlighted CLOSE) | 0 | 0 / 0 |
    | 2 (14:42) | + CLOSE_HI | 1 | 0 / 1 / 0 | 0 | 1 (codec border) | 0 | 0 / 0 |
    | 3 (17:06-17:17) | + the border fix | 36 | 15 / 0 / 0 | 14 / 1 / 6 / 0 | 0 | 0 | 0 / 0 |
    | **the arm** | | **176** | **76 / 9 / 1** | 77 / 6 / 6 / 1 | 3 | **0** | **0 / 0** |

    - **The L3 no-click layer** (prontera's L3 is complete, so `l3_kb` = `l3_complete`; recorded,
      never applied):
      - it refuses **9 / 9** contact clicks (Wilson 95 % 0.70-1.00);
      - **0 / 49** of the clicks it allows became `npc_contact` (Wilson upper 0.073);
      - it costs **27 / 76** moves refused (0.36, 0.26-0.47).
      - **3.32a's decision rule is MET in prontera: "the layer alone removes the town contacts".**
        Every contact click is refused, and no click it allows became a contact.
    - **A click the walk gate allowed became `npc_contact`:** 9 / 86 = 0.105 (0.056-0.187).
      - By ring (Chebyshev cells from the NPC): ring 1 5 / 20 (0.25); ring 2 3 / 29 (0.10);
        ring 3 1 / 37 (0.027).
      - So the cursor gate alone does not keep a walk click off an NPC beside it. The layer does.
    - **New in segment 3:** 6 clicks were not made with `stale_background` (Prober9's park found the
      background still changing). They fail closed and are reported.
    - Next: the church arm resumes (`--resume 20261013T151312-demo-npc-click-click-prt-church`).
  - ➡️ **THE CHURCH CLICK ARM: COMPLETE** (`20261013T151312`; segment 2, 17:18-17:23, with the border fix:
    14 records, no stop). 52 records, scored:

    | segment | records | clicked: moves / contacts | not clicked | stops | attack_request | GM act normal / pickup |
    |---|---|---|---|---|---|---|
    | 0 (15:13-15:24) | 38 | 33 / 2 | TALK 1, unknown 1, no safe point 1 | 1 (codec border, Garnet) | 0 | 0 / 0 |
    | 1 (17:18-17:23) | 14 | 13 / 0 | TALK 1 | 0 | 0 | 0 / 0 |
    | **the arm** | **52** | **46 / 2** | 4 | 1 | **0** | **0 / 0** |

    - **L3 layer** (complete; recorded, not applied): it refuses **2 / 2** contact clicks; **0 / 38**
      allowed clicks became `npc_contact` (Wilson upper 0.092); it costs **8 / 46** moves (0.17).
      The decision rule holds here too.
    - A click the walk gate allowed became `npc_contact`: 2 / 48 = 0.042. By ring: ring 1 2 / 18,
      rings 2-3 0 / 30.
  - **npc-click@1, both arms complete (2026-10-13 17:23): every metric above, safety 0 throughout.**
    - The L3 no-click layer refused **11 / 11** contact clicks over both maps.
    - **0 / 87** clicks it allows became a contact.
    - Its cost was **35 / 122** moves.
    - What this means for walk@17 (its L3 no-click amendment, and the NPC render region of 3.38)
      is Batt's call.

### 3.33 The GM's IMMUNITY: a test condition for the visual-diversity block (pre-registered 2026-10-09 ~14:05 ICT / 07:05 UTC, BEFORE the check; Batt: "keep gl_prison; a GM doesn't need to fear monsters. Make the GM safe without changing what the bot sees")
**The condition, PRIMARY:** rAthena's `@monsterignore`, granted to the GM's group 20 (`groups.yml`,
in place; it applies at the next guarded rathena recreate, never during a scored client run).
- In the pinned source (e985006): `atcommand.cpp:9025` toggles `PCBLOCK_IMMUNE`, and
  `battle.cpp:8010` makes an immune player no enemy target ("Global immunity only to Attacks").
- Monsters keep moving. The GM's own clicks still send their requests: a misclick on a monster is
  still an `attack_request`, so the safety signal stays valid.
- The flag lives until the GM logs out. Only the anti-macro captcha paths clear it (`pc.cpp:15730`,
  `15866`, `15962`), not a warp.
- **Nothing visible changes:** no `@hide`, no transparency, no equipment or headgear. The HP bar
  under the feet, the HUD and the detector see the same pixels.

**BACKUP, only if the check below FAILS:** raising the GM's level / stats (`@blvl` / `@allstats`) for
HP headroom. It is not granted now; that would be its own step, with Batt.

**THE CHECK (prt_fild08 (268, 107), one deliberate session,
`safety_signal_check.py immune-check`), right after the recreate and a fresh GM login:**
1. `@monsterignore` ON (a screenshot of the client's own answer).
2. `@monster` Familiar (1005, level 8, AGGRESSIVE) × 3 beside the GM.
3. 60 s waiting.
4. One DELIBERATE attack click where the cursor reads the sword twice (the monster positive case's
   own rule).
5. `@killmonster2`, `@monsterignore` OFF (a screenshot).

**PASS iff** (the packets, offline):
- the 3 Familiars were on the server;
- ZERO acts targeting the GM from the spawn to the click;
- ≥ 1 movement of a Familiar in that window (they moved, so ignoring the GM was not just standing
  still);
- an `attack_request` within 5 s of the click.

FAIL: the backup is raised with Batt, and gl_prison waits.

➡️ **RESULT (2026-10-09 14:51–14:56 ICT): PASS.** Session `20261009T145110-demo-safety-check-immune`.
- **The grant went live first.**
  - `groups.yml` was verified inside the container (`verify_mount.py rathena`: ok).
  - A guarded `restart:rathena@120`, then `restart:sniffer@30` (the sniffer shares rathena's network
    namespace), ran 14:47:01–14:50:15. The worst capture stall was 13.1 % on quant-postgres for 8 s,
    within the tolerant guard.
  - The GM auto re-login was OK and the interlock was green again at 14:50:15.
  - The client was clean on the screenshot after it: `/dev/shm/poring-lab-tmp/shots/after-rathena-restart.png`.
- **ON:** the client's own answer is on the screenshot (`.../npc-check/1791532292-immune-on.png`).
  The answer appears once as a chat line and a transient bubble above the GM; nothing persistent
  changes.
- **The packets:**
  - 3 Familiars on the server;
  - **0 acts on the GM** in the window, and 0 in the whole session (7 acts in all);
  - 50 Familiar movements;
  - 2 `attack_request` within 5 s of the deliberate click.
- **Deviation, disclosed:** the window from the spawn to the click was **263 s, not ~60 s**. The
  sword-twice scan needed 104 hovers before the cursor read the sword twice. The longer window
  is the stricter test: four times as long for a monster to act on the GM.
- **OFF:** `@monsterignore` toggled off at 14:56:10 (`.../1791532571-immune-off.png`).
- **The condition is ready for the visual-diversity block:** ON once after each GM login, judged per
  run offline (zero acts on the GM).

**In the visual-diversity block** (perception + walking, NOT combat), the GM is immune on every map.
- It is applied once after each GM login and confirmed per run offline: zero acts on the GM.
- An act on the GM in a run is reported as a condition failure, not a rule failure.

### 3.35 cursor@1 -- the robust cursor reader: a banked-hover proof, then its LIVE acceptance (pre-registered 2026-10-09 ~21:20 ICT / 14:20 UTC at commit, BEFORE any scoring or run; Batt 2026-10-09 ~20:20: "finish offline, pre-register, prove on banked hovers (hard bar: zero false WALK / cross-shape errors), then the live acceptance. It unblocks loot, attack and talk.")
**The readers:** the gate's (walk6.CursorRefs v3, LIVE, unchanged throughout) and the robust candidate
(`scripts/cursor_robust.py` `RobustRefs` at c5bcb55, OFFLINE only, on the saved crops). Design and
numbers: `docs/planning/cursor-robust.md` (merged c5bcb55). **Nothing changes in the live gate.**
The switch-over (cursor-robust.md 6: a named flag, pre-registered rules keep v3) is Batt's decision
after this result; a default flip is never a side effect.

**STAGE 1 -- banked hovers (offline, scored once at c5bcb55).** Honest scope: every banked hover
was seen during development (the floors were learned leave-one-out on the references; the 78 crops
were replayed before this pre-registration, 0 wrong). Stage 1 is therefore a REPRODUCIBILITY and
SAFETY check at the merged commit, not a fresh test; stage 2 is the fresh test.
- **Sets:** (a) the 78 banked non-reference crops (`cursor_eval.py replay`), labelled TWICE: by
  the subagent at design time and BLIND by Claude (a shuffled contact sheet, no reader output,
  2026-10-09 ~21:10): **78 / 78 agree** (walk 71, talk 3, sword 3, warp 1); (b) the leave-one-out
  perturbation reads (`cursor_eval.py perturb`, seed 20261009, 61 conditions) and (c) the
  leave-neighbours-out reads (`--neighbours 3`, 15 conditions).
- **Bar (hard):** the robust reader makes **0 cross-shape errors** and reads **WALK on 0 crops of
  another label** in all three sets. One error FAILS stage 1: no live run uses the robust reader's
  output for anything but the record.
- **Reported:** read / unknown / wrong per shape for both readers, as cursor-robust.md 3.
- ➡️ **STAGE 1 RESULT (2026-10-09 21:06-21:45 ICT, scored once as written; code at aab9c7f =
  cursor_robust.py / cursor_eval.py b4b7b2f; outputs /dev/shm/poring-lab-tmp/cursor-acc/stage1/):
  PASS.**

  | set | reads | robust: wrong / false WALK / unknown | gate: wrong / false WALK / unknown |
  |---|---|---|---|
  | (a) 78 banked crops (twice-labelled) | 78 | 0 / 0 / 11 (walk 60/71, talk 3/3, sword 3/3, warp 1/1) | 0 / 0 / 18 (walk 54/71, talk 3/3, sword 3/3, warp 0/1) |
  | (b) leave-one-out, 61 conditions | 18,469 | 0 / 0 / 2,415 | 0 / 0 / 9,078 |
  | (c) leave-neighbours-out (3), 15 conditions | 3,795 | 0 / 0 / 371 | 0 / 0 / 1,612 |

  - (b)'s count differs from the design-time 15,433 (cursor-robust.md 1.3): this run used the
    defaults as written (walk sample 100, every condition); the bar holds on all of them.
  - As stated above, this is a reproducibility and safety check on seen data; the fresh test is
    stage 2.

**STAGE 2 -- live, both readers on the same grabs (fresh data).** Cursor-robust.md section 5's
draft, adopted as written, with these values:
- **Arm B, SWORD over a Poring:** `scripts/cursor_probe.py sword --n 10 --seed 20261170` at
  c5bcb55 (or the commit of a pilot fix, recorded here first), RDP, the GM on prt_fild08, hover
  only (NOTHING clicked). Pilot first, never scored: `--n 2 --seed 20261171`.
  - ➡️ **AMENDED 2026-10-09 ~21:06 ICT, after the pilot and BEFORE the scored run: `--n 30`** (was
    10). The pilot (`20261009T210018-demo-cursor-probe-sword`, never scored) gave 13 probes in 2
    trials, 8 of them sword points (the probes wait for a fresh, still box; a Poring rarely stands
    still): ~4 sword points per trial, so n = 10 would give ~40, under the bar's 100 (INCONCLUSIVE
    by construction). No harness change; the pilot's packets hold no attack / contact / pickup /
    move request and no GM act. The seed stays 20261170.
- **Arm A, TALK (and WALK on cells):** npc-click@1's PROBE arm, under its own pre-registration
  (3.32a, pasted from npc-click-test.md 6 once its P1, the complete L3 NPC list for prontera and
  prt_church, is checked): prontera `--near 156,191 --seed 20261160`, prt_church `--near 103,74
  --seed 20261161`; prt_church alone if prontera's P1 is not ready.
- **Scoring:** `cursor_eval.py live SESSION` for both readers (first read = the first non-unknown
  of grabs 0-2; read twice = grabs 0-2 and 3-5 agree).
- **Truth by eye, every label fixed before any bar is computed:** (1) every robust CLAIM, per
  shape (`cursor_eval.py sheet SESSION --verdict S`), every WALK claim looked at, and the gate's
  claims the same way; a SECOND labeller (a second agent, or Batt) checks every flag; (2) a blind
  seeded sample of 200 crops per arm (seed 20261172) from sheets without verdicts; labels walk,
  talk, sword, pickup, noentry, warp, none, unclear (unclear excluded and counted).
- **The bars (the robust reader; the gate's numbers beside them):**
  1. **SAFETY, hard: 0 cross-shape errors** among all labelled crops, first read or read twice,
     both arms; **WALK on a crop labelled anything else: 0.** One error FAILS the acceptance.
  2. **TALK** (arm A sprite points labelled talk): read twice >= 0.85.
  3. **SWORD** (arm B box points labelled sword): read twice >= 0.40 with >= 100 such probes, and
     >= the gate's + 0.25.
  4. **WALK** (arm B controls + arm A cell points labelled walk): read twice >= 0.95 and not below
     the gate's - 0.02.
  - Fewer than 100 labelled sword or 200 labelled talk probes: INCONCLUSIVE.
  - Arm B alone gives bars 1, 3 and part of 4 as an INTERIM report; the acceptance verdict needs
    both arms.
- **Safety of the runs:** arm B never clicks: any `attack_request` or GM act of kind normal /
  pickup in its packets is a harness fault and stops the test. The client's UI state is judged
  before each run (the UI gate, a screenshot), and the GM's fixed state per trial (loot@1's
  machinery).
- **Reported:** both readers per arm, kind, background and grab index; the robust reader's
  best-shift distribution (C1); whether later grabs pass where the first failed (C2); unknown
  reasons; labelling time.

**➡️ ARM B -- INTERIM RESULT (2026-10-09 21:04-22:10 ICT; scored once as written; the acceptance verdict
needs arm A).** Session `20261009T210428-demo-cursor-probe-sword` (`--n 30 --seed 20261170`, code at
58f5e44): 30 trials, 412 probes (290 on the Poring box, 122 controls), every one hovered only.
- **The runs' own safety: CLEAN.** The packets hold 0 `attack_request`, 0 `npc_contact`, 0
  `pickup_request`, 0 `self_move_request` and 0 GM acts.
- **Truth:** all 412 crops (the grab-0 image the sheets show) labelled BLIND twice, by Claude and by a
  second agent: 404 agree (sword 254, walk 150), 8 differ -> unclear (excluded): the 7 crops showing a
  1-2 px diagonal line (the second labeller: the arrow seen edge-on in its rotation; Claude: unclear)
  and one arrow under an HP bar.
- **Bar 1, SAFETY, as written** (each crop's label vs the first read of grabs 0-2): **1 cross-shape
  error, the SAME for both readers**: crop 243 (a control point), labelled sword, first read WALK.
  - Its series shows why: in grab 0 (the labelled image) a Poring passes under the cursor and the
    client draws the SWORD; both readers read grab 0 UNKNOWN. In grabs 1-5 the Poring has moved on and
    the client draws the ARROW; both read WALK, correctly. No image was misread: the label belongs to
    grab 0, the scored read to grab 1. As the bar is written it counts as an error, and it is reported
    so: **bar 1 as written: 1 error for each reader.**
- **The per-grab audit (added after the first scoring, reported beside it, decides nothing by
  itself):** every grab image a read came from that was not grab 0 (362 images) was labelled blind
  and shuffled, again by both labellers: **362 / 362 agree** (walk 183, sword 158, unclear 21; all
  21 unclear are the edge-on thin line). Judging every read against the label of the image it came
  from: **0 cross-shape errors and 0 WALK on another label, for both readers** (gate 309 reads
  judged, robust 540).
  - **Caveat, for Batt:** on the edge-on thin-line images (unclear by both labellers) the robust
    reader reads **WALK 26 times** (3 unknown); the gate reads them all UNKNOWN. Both labellers lean
    walk (the line runs at the arrow's axis angle, ~66 deg, not the sword's ~40 deg, and no sword frame
    is ever thin), but nobody could confirm it from the pixels. The client's own cursor sprite (its
    animation frames) can settle it offline.
    ➡️ **SETTLED the same evening (22:20, offline) by the client's own cursor sprite** (`data\sprite\
    cursors.spr/.act`, read from the host's GRF with the study decoder; local, never committed): the
    default ARROW cursor's animation (ACT action 0) cycles images 0, 1, 2, **3**, 4, 5, and image 3
    is exactly that 1-2 px diagonal line: the arrow seen edge-on. The SWORD cursor (action 5 / 6,
    image 19) has ONE static frame and is never thin. So the robust reader's 26 WALK reads on those
    frames are CORRECT, and the gate's UNKNOWN there is a miss. (The scoring above keeps them
    excluded as the labellers marked them; the sprite is the host's Thai GRF, the lab client draws
    from the kRO data, whose cursor sprite was not compared.)
- **Bar 3, SWORD (box points labelled sword, n = 248):** robust read twice **127 / 248 = 0.512**
  (Wilson 0.450-0.574; first read 155 / 248 = 0.625); the gate **17 / 248 = 0.069** (first 21 =
  0.085). >= 0.40 with >= 100 probes, and +0.44 over the gate (>= +0.25): **met.**
- **Bar 4, WALK, arm B's part (controls labelled walk, n = 109):** read twice robust **103 / 109 =
  0.945**, the gate 103 / 109 = 0.945 (first read 109 / 109 and 108 / 109). The bar (>= 0.95, pooled
  with arm A's cell points) is decided with arm A; on arm B alone it is just under 0.95, equal to
  the gate's.
- Labels, sheets and scores: `/dev/shm/poring-lab-tmp/cursor-acc/armb/` (local).

**➡️ RESULT, BOTH ARMS (2026-10-10 00:45 ICT; scored once as written): FAIL on bar 1 -- for BOTH readers,
by the client's own cursor animations; bars 2, 3 and 4 MET by the robust reader; the robust reader is
never worse than the gate. As pre-registered: no switch.**
- **Arm A** = npc-click@1's probe arm (3.32a): `20261009T220521-demo-npc-click-probe-prontera` (1,517
  probes) + `20261009T233300-demo-npc-click-probe-prt-church` (566), hover only, safety EMPTY in both
  (0 attack / contact / pickup / move requests, 0 GM acts).
- **Truth:** 4,455 images (grab 0 of every crop + every other grab a read came from), shuffled,
  labelled BLIND by two independent agents with the client's own cursor sprite as the reference:
  **4,455 / 4,455 agree** (walk 2,325, talk 1,825, noentry 303, warp 2).

| bar | robust (twice) | gate (twice) | verdict |
|---|---|---|---|
| 1 SAFETY as written (grab-0 label vs first read; any WALK on another label) | arm B 1 (crop 243); arm A first-read noentry->walk 9, read-twice noentry->walk **3** | arm B 1; arm A first 11, twice **4** | **FAIL (both)** |
| 1 per image (the label of the exact grab read) | 0 cross-shape, 0 WALK on another label | 0 / 0 | (reported) |
| 2 TALK, sprite points labelled talk | **590 / 610 = 0.967** (prontera 0.986, church 0.920) | 522 / 610 = 0.856 | MET (>= 0.85) |
| 3 SWORD, box points labelled sword | **127 / 248 = 0.512** | 17 / 248 = 0.069 | MET (>= 0.40, +0.44) |
| 4 WALK, arm B controls + arm A cells labelled walk | **621 / 649 = 0.957** | 586 / 649 = 0.903 | MET (>= 0.95, not below the gate) |

- **Why bar 1 fails (the series show it):** the client's NO-ENTRY cursor is an ANIMATION: a red ring
  and slash drawn over the arrow, growing in, with frames in between that show the BARE ARROW (grab 1 in
  every one of the three series rendered). A reader that sees such a frame reads WALK, correctly for the
  pixels; the client means "no entry". When both read groups (grabs 0-2 and 3-5) land on bare-arrow
  frames, "read twice" passes: 3 times for the robust reader, 4 for the gate, out of 255 no-entry
  probes. Arm B's crop 243 is the other way round (a Poring passing under the cursor). Neither reader
  misread a single image (the per-image audit), and the gate fails in exactly the same way.
- **What it would take (a design change, for Batt; not done):** a WALK verdict that covers the cursor's
  animation period (e.g. no non-WALK shape on ANY of the 6 grabs, or a longer series), re-measured under
  a new pre-registration. The walk rules already add the walk MARKER condition (no marker on a
  non-walkable cell), which refuses these clicks; the npc-click test's gate is cursor-only.
- **Consequence today:** the live gate stays v3 (it was never changed); cursor_robust stays a candidate.
- ➡️ **2026-10-10: the design change is 3.36 (cursor@2, robust2 = the robust reader + the NO-ENTRY
  RING over the series), pre-registered there before any of its data.** The first form named above
  ("no non-WALK shape on ANY of the 6 grabs") was measured on this section's data first and fixed
  NONE of the cases: in each failing series the shape reader read no grab as no-entry.

### 3.36 cursor@2 -- robust2 = the robust reader + the NO-ENTRY RING over the series: a FRESH live proof (pre-registered 2026-10-10 ~13:45 ICT at commit, BEFORE any cursor@2 data; the weekend run, Track 2 item 1: "Cursor classifier robustness: finish offline, pre-register, prove on banked hovers (hard bar: zero false WALK / cross-shape errors), then the live acceptance. It unblocks loot, attack and talk.")
**Why:** cursor@1 (3.35) FAILED bar 1 for both readers on the client's NO-ENTRY ANIMATION. The sign
is a red ring whose slash draws in over the arrow, and a blink frame shows the BARE ARROW. When both
read groups landed on blink frames, "read twice" said WALK (robust 3, the gate 4, of 255 no-entry
probes). 3.35 named the fix as a design change for Batt. **This is that change, built as a
CANDIDATE.** It is pre-registered so its data can be collected this weekend. **Nothing live changes:**
the gate stays v3, pre-registered rules keep v3, and the switch-over (cursor-robust.md 6, a named
flag) is Batt's decision after this result. Batt can stop or redirect it at any point; a run already
made is reported as it stands.

**Design data (cursor@1's three sessions; DESIGN data from now on, never scored for cursor@2):**
- **The first form, "no non-WALK shape on any of the 6 grabs": fixes 0 of the cases.** In every
  failing series the shape reader read NO grab as no-entry. The robust reader reads 175 / 303
  labelled no-entry images as no-entry and the rest UNKNOWN: the slash's in-between lengths and
  the ring's thin arcs match no reference.
- **The ring is a separate, simple cue:** red CURSOR pixels (inside the cursor mask D; colour R >
  170, G < 80, B < 80, the crops being BGR).
  - Every image both labellers called no-entry: **188-284** (303 images). The minimum stays 181-216
    for every colour box tried, from R > 150 / G, B < 100 to R > 210 / G, B < 40.
  - Every other image they agreed on: **0-3** (4,556 images: walk 2,475 max 1, talk 1,825 max 0,
    sword over a Poring 254 max 3, warp 2 max 0).
  - Every grab of the sword arm's series, mostly unlabelled: **max 6** (2,472 grabs).
  - **RING_MIN = 40.**
- **Per series (robust2 = robust's per-grab shapes; any grab >= RING_MIN -> NOENTRY, else read
  twice):**

  | design session | reader | no-entry probes read WALK | no-entry -> noentry | walk kept | talk kept | sword kept |
  |---|---|---|---|---|---|---|
  | npc-click probe prontera | robust | 1 / 155 | 28 / 155 | 610 / 644 | 698 / 718 | -- |
  | | robust2 | **0 / 155** | **155 / 155** | 610 / 644 | 698 / 718 | -- |
  | npc-click probe prt_church | robust | 2 / 100 | 8 / 100 | 244 / 252 | 194 / 212 | -- |
  | | robust2 | **0 / 100** | **100 / 100** | 244 / 252 | 194 / 212 | -- |
  | cursor probe sword | robust = robust2 | -- | -- | 122 / 150 | -- | 129 / 254 |

  - (All probe kinds, grab-0 label, both labellers agreeing; 3.35's bars count subsets of these.)
  - Every no-entry series held the ring on 4-6 of its 6 grabs, so a blink can never cover a series.
  - The ring never fired on a walk, talk, sword or warp series: robust2 costs nothing on bars 2-4
    on this data.
- **Arm B's crop 243 (a Poring passing under a control point at grab 0) stays as it was:** every
  image there was read correctly. The ring is not about it, and no rule is added for it.
- **Code:** `scripts/cursor_robust.py` `ring_pixels`, `series_verdict` (`RING_MIN`, `RING_RED_MIN`,
  `RING_GB_MAX`) and `cursor_eval.py live`'s `robust2` block, at e57a7e7, tested on synthetic
  sprites (`test_cursor_robust.py`: the ring on the no-entry sign only, a blink series never WALK).
  The per-grab reader is cursor@1's, unchanged.

**FRESH DATA (all hover only, nothing clicked; the runs as 3.35's):**
- **Arm B2, SWORD over a Poring:** `scripts/cursor_probe.py sword --n 30 --seed 20261184`.
- **Arm A2, TALK / WALK / NO-ENTRY around NPCs:** `scripts/npc_click_test.py probe` at e57a7e7.
  - prontera `--near 156,191 --seed 20261180`;
  - prt_church `--near 103,74 --seed 20261181`.
  - These are 3.35's scenes with NEW seeds: fresh grabs, other animation phases, other stands.
- **HELD-OUT, once: alberta** `--near 116,57 --seed 20261182`.
  - No cursor reference or design step ever saw alberta. Its L3 NPC list is COMPLETE (48 NPCs).
  - The spot is its densest NPC group (113-120, 53-60). Planned offline at e57a7e7 (`plan`, same
    seed): 6 NPCs, 1,556 probe points, 13 stand warps; the plan takes ~7.5 min to compute.
  - A pilot comes first, never scored: `--npcs 1 --reps 1 --seed 20261183`.
  - If the harness cannot run there (the pilot stops for a harness reason), alberta is DROPPED and
    reported. It is not replaced.
- **Order:** B2, A2 prontera, A2 prt_church, the alberta pilot, A2 alberta.
- **Before each run:** a client screenshot judged, and the UI gate (3.32's item 6).
- **A run that exits early is re-run unchanged with its seed.** The partial session is kept and
  not scored.

**Truth (fixed BEFORE any bar is computed; `scripts/cursor2_truth.py sheets` at e57a7e7):**
- **(i) Images:** grab 0 of every crop, and every other grab a read came from (the gate's and the
  robust reader's; robust2 reads the same grabs).
  - Shuffled with seed 20261185, pages of 50, no reader output.
  - Labelled BLIND by two independent agents, with the client's own cursor sprite as the
    reference: walk, talk, sword, pickup, noentry, warp, none, unclear.
  - The edge-on arrow (cursors.act action 0, image 3) is labelled walk (3.35's settlement).
- **(ii) Series:** every series robust2 calls WALK, plus as many series it does not.
  - The extra series are a seeded sample (seed 20261186), so a strip's presence says nothing.
  - Each is shown as its 6 grabs side by side. The question: "does ANY grab show the no-entry
    sign?" (yes / no / unclear), both labellers, blind.
- **Truth = both labellers agree.** Otherwise the item is unclear: excluded and counted.

**The bars** (`scripts/cursor2_score.py` at e57a7e7; robust2 is judged, robust and the gate are
reported beside it):
1. **SAFETY, hard.** One error FAILS the acceptance, on any map.
   - **(a) Per image:** every read judged against the label of the image it came from: **0
     cross-shape errors and 0 WALK reads on an image labelled anything else.** (3.35's per-grab
     audit, now the bar.)
   - **(b) Per series:** **0 WALK verdicts on a series that both labellers say shows the no-entry
     sign on any grab.** A WALK series without their agreement makes 1b INCONCLUSIVE, never a pass.
   - **(c) 3.35's bar 1 as written** (the grab-0 label vs the series verdict) is REPORTED, each case
     with its series. It is not the bar, because 3.35 showed that it judges a read against another
     grab's image (crop 243).
2. **TALK:** arm A2's sprite points whose grab 0 is labelled talk: read twice >= 0.85.
3. **SWORD:** arm B2's box points labelled sword: >= 0.40 with >= 100 such probes, and >= the gate's
   + 0.25.
4. **WALK:** arm B2's controls + arm A2's cell points labelled walk: >= 0.95, and not below the
   gate's - 0.02.
5. **NO-ENTRY** (reported, not a bar): probes whose grab 0 is labelled noentry, verdict noentry.
- **INCONCLUSIVE:** fewer than 200 labelled talk probes or fewer than 100 labelled sword probes.
- **Pooling:** bars 2-4 are pooled over the maps. Every bar is also reported per map, alberta on its
  own line.
- **The scorer's positive case on REAL data, run before this commit** (cursor@1's arm A design data
  with 3.35's labels): it lists robust's three no-entry -> WALK series under 1c and none for
  robust2 (output in /dev/shm/poring-lab-tmp/cursor2/positive.json). It reproduced 3.35's numbers:
  TALK robust 590 / 610, the gate 522 / 610; arm A's walk cells robust 518 / 540; 1c robust 3 and
  the gate 4 no-entry -> WALK series, robust2 none; 1a 0 / 0 for all three; no-entry robust2
  255 / 255.

**Safety of the runs:** as 3.35's.
- The runs are hover only. Any `attack_request`, `npc_contact`, `pickup_request` or
  `self_move_request`, or a GM act of kind normal / pickup, in a run's packets is a harness fault,
  and it stops the test.
- The GM's fixed state, the typing policy and the UI gate apply.

**Not decided here:**
- The switch-over (Batt). A PASS makes `robust2` the candidate for cursor-robust.md 6's flag
  (`--cursor robust2`).
- The live gate would need the ring per grab over Prober9's 6 grabs. That is part of the switch,
  not built.
- Pre-registered rules keep v3.

**Expected (Claude's reading of the design data; NOT a bar):**
- robust2 = robust on bars 2-4, and bar 1 met: 0 / 0 and 0 WALK on no-entry series.
- **The new risk:** a red sprite moving under the cursor (a red-clad NPC, a red monster) would put
  red pixels in the mask. The verdict is then NOENTRY. That is fail closed: it lowers recall and is
  never WALK.
- On alberta, the NPC sprites are new to the reader: TALK may read lower there.

**➡️ RUNS (2026-10-10, all as pre-registered at b77529d; every run hover only; NO verdict yet: the
blind labels decide).**

| arm | session | time (ICT) | probes / crops | packets |
|---|---|---|---|---|
| B2 sword, prt_fild08 (`--n 30 --seed 20261184`) | `20261010T133737-demo-cursor-probe-sword` | 13:37-14:23 | 30 trials, 379 | SAFE |
| A2 prontera (`--seed 20261180`) | `20261010T142556-demo-npc-click-probe-prontera` | 14:26-15:42 | 1,507 | SAFE |
| A2 prt_church (`--seed 20261181`) | `20261010T154307-demo-npc-click-probe-prt-church` | 15:43-16:10 | 560 | SAFE |
| alberta PILOT (`--npcs 1 --reps 1 --seed 20261183`; never scored) | `20261010T161258-demo-npc-click-probe-alberta` | 16:12-16:20 | 156 | SAFE |
| **HELD-OUT alberta** (`--seed 20261182`), once | `20261010T162806-demo-npc-click-probe-alberta` | 16:28-17:41 | 1,528 | SAFE |

- **SAFE** = 0 `attack_request`, 0 `npc_contact`, 0 `pickup_request`, 0 `self_move_request` and 0 GM
  acts in the run's packets. The same packets carry our own typed GM lines (151, 15, 5, 3 and 13), so
  the sensor saw our client throughout.
- **Before each run:** the client screenshot was judged clean (no dialog, menu or window), and every
  typed line passed the UI gate.
- **No run ended early, and none was re-run.** The alberta pilot completed (3 stands), so alberta
  was not dropped.
- **Truth sets** (`cursor2_truth.py sheets` at e57a7e7, the four scored sessions pooled):
  - 8,190 images (seed 20261185, 164 pages);
  - 2,740 series strips (seed 20261186, 274 pages): every robust2 WALK series plus as many others.
  - Two blind agent labellers started 17:47 ICT, in opposite page orders. Their briefs forbid any
    reader output and any pixel rule deciding a label.

**➡️ RESULT (2026-10-10 ~18:48 ICT; scored once as written, `cursor2_score.py` at e57a7e7, rc 1):
FAIL on bar 4 (WALK 0.848 < 0.95), from the held-out town. The SAFETY bars, the reason for this
version, are MET on fresh data, held-out included: 0 WALK verdicts on any series that shows the
no-entry sign (1,370 judged), and no-entry read as no-entry 0.971 (robust 0.103). As
pre-registered: no switch; the live gate stays v3.**
- **Truth:** the two labellers agree on **8,190 / 8,190 images** (walk 4,097, talk 3,046, noentry
  638, sword 409; no pickup, warp, none or unclear) and **2,740 / 2,740 series** (yes 301, no
  2,439). Each took ~45-55 min.
  - Labeller B used a red-pixel FLAGGER, allowed by the brief: it only picks items to re-view, never
    labels. It flagged one series (index 1696, typed no, corrected to yes by eye). Labeller A, who
    used no such check, also said yes. Reported because the flagger resembles the cue under test.

| bar | robust2 | robust | the gate | verdict |
|---|---|---|---|---|
| 1a per image: cross-shape / WALK on another label | **0 / 0** (6,731 reads) | 0 / 0 (6,731) | 0 / 0 (6,025) | MET |
| 1b WALK series showing the no-entry sign | **0 of 1,370**, 0 unclear | -- | -- | MET |
| 1c 3.35's bar 1 as written: no-entry -> WALK | **0** | 7 | 7 | reported |
| 2 TALK, sprite points labelled talk | **949 / 1,060 = 0.895** (0.875-0.912) | 0.895 | 0.777 | MET (>= 0.85) |
| 3 SWORD, box points labelled sword | **124 / 217 = 0.571** (0.505-0.635) | 0.571 | 0.097 | MET (>= 0.40, +0.47 over the gate) |
| 4 WALK, cell points + controls labelled walk | **849 / 1,001 = 0.848** (0.825-0.869) | 0.848 | 0.759 | **FAIL** (< 0.95; above the gate - 0.02) |
| 5 NO-ENTRY, grab 0 labelled noentry | **530 / 546 = 0.971** (0.953-0.982) | 0.103 | 0.106 | reported |

- **Per map** (robust2; the gate in brackets):

  | map | WALK | TALK | NO-ENTRY |
  |---|---|---|---|
  | prontera | 344 / 365 = 0.943 (0.786) | 435 / 443 = 0.982 (0.815) | 166 / 168 = 0.988 |
  | prt_church | 156 / 157 = 0.994 (0.968) | 153 / 168 = 0.911 (0.863) | 87 / 87 = 1.000 |
  | sword arm's controls | 90 / 99 = 0.909 (0.879) | -- | 1 / 1 |
  | **alberta, HELD-OUT** | **259 / 380 = 0.682** (0.616) | **361 / 449 = 0.804** (0.708) | 276 / 290 = 0.952 |

  - Without alberta, WALK would pool to 590 / 621 = 0.950. That is reported only: the bar pools all
    maps, and alberta is in it as pre-registered.
- **robust2 = robust on bars 1a, 2, 3 and 4:** the ring changed no WALK, TALK or SWORD read twice
  on a series those labels count. Its 12 "as written" items are all walk -> noentry: grab 0 caught
  a blink frame, and the ring is on later grabs of the same series (the client means no-entry).
- **Why WALK fails on alberta** (DIAGNOSIS after scoring, decides nothing): 121 walk cells were not
  read twice.
  - On grab 0 the robust reader says `no_match` 62, `low_score` 14, `no_cursor` 13, and `walk` 32
    (the re-read failed).
  - 12 of the `no_match` crops viewed with their masks: the arrow is drawn normally, but the CURSOR
    MASK (|A - B| against the parked background, animated pixels removed) either FLOODS (most of
    the crop differs from the parked frame) or EMPTIES (the cursor's own pixels fall in the
    "animated" map).
  - The mask's median size is 319 px on alberta's misses vs 267 on prontera's. So the miss lies
    in the background model on that map (the two parked frames), not in the shape reader, and it
    fails closed (UNKNOWN, no click).
  - Hypothesis, unmeasured: something on alberta changes between the parked frames and the hover
    grab.
    - ➡️ **Looked at the same evening:** each crop carries the parked background B and the
      animated map. In 6 of 8 crops viewed, B shows a large white-and-blue ROOF element where the
      hover grab A shows plain cobblestone floor (only the roof's edge left in a corner). So a
      building part is present in one frame and absent in the other.
    - Of the 121 misses, 55 differ from B by more than 60 (summed) over more than 1,500 px (median
      1,328), and 38 have more than 1,000 px marked "animated", the cursor's own pixels among them.
    - The mechanism (the client hiding a model under or near the cursor, or something else) is NOT
      measured; it is the first question for any next version.
    - ➡️ **MEASURED the same evening** (EXPLORATORY, not a rule, never scored; hover only, one
      `@warp`; `/dev/shm/poring-lab-tmp/cursor2/roof_probe.py`, frames in `cursor2/roof/`): **it is
      alberta's WINDMILL.**
      - Its white-and-blue sails rotate continuously, about one cycle in 2 s.
      - With the cursor PARKED, no motion, the game region differs from its first frame by
        20,000-60,000 px at every 0.2 s grab; the difference is the sweeping sails (the left half of
        the view from stand 129,48).
      - Hovering changes nothing: the roof / roof2 / floor hovers show the same cycle.
      - So the "roof element" in the failed crops is a sail. The scene changes by itself, and the
        cursor plays no part. The parked background is stale wherever a sail passes, so the mask
        floods. The two parked frames 0.25 s apart mark the sails' area "animated", so the mask
        empties when the cursor sits there.
      - A next version needs a cursor mask that survives large animated scenery near the cursor.
        That is Batt's design call.
- **What it would take** (a design step, for Batt; not done): a cursor mask that survives big
  animated scenery (alberta's windmill, below). Options, none measured:
  - **(a) Fail closed, then step aside:** detect "animated near the hotspot" (two parked grabs) and
    let the caller pick another point or wait for a calmer phase. Cheapest; it costs clicks, not
    safety.
  - **(b) A fresh background per hover:** re-grab B right before the hover. A sail still moves in
    the ~0.5 s the hover takes, so it only narrows the problem.
  - **(c) Read the cursor on A alone when the mask is implausible.** One-sided: a white talk bubble
    contains the arrow's area in white, so it needs an outline / two-sidedness test of its own
    before it can be trusted with WALK.
  - Any of them is re-measured under a NEW pre-registration, on a held-out map not yet used (alberta
    is now used for cursor@2). alberta is the Merchant guild's town, so the first workflow meets the
    windmill.
- ➡️ **SUPERSEDED 2026-10-13: the live gate SWITCHED to robust2 (Batt; the ADOPTION below).**
- **Consequence today (as of 2026-10-10):** nothing live changes. robust2 is a candidate whose SAFETY property is
  proven on fresh and held-out data; its walk recall is not accepted. The click callers that need
  it (loot, attack, talk) wait for Batt's decision.
- Outputs: `/dev/shm/poring-lab-tmp/cursor2/` (result.json, live/, truth/, the labels in
  c2-labeller{A,B}/; local, client pixels).

**➡️ ADOPTION (Batt, 2026-10-13, decision 3): the live gate SWITCHED to robust2. This is a
SAFETY-DRIVEN adoption that DEPARTS from 3.36's bar 4, by Batt's decision; bar 4 stays the target.**
- **Batt:** "SWITCH the live gate to robust2 now. Its safety bars are all met (0 false WALK / 0
  cross-shape over 6,731 reads; no-entry .971) and the current v3 gate has a measured hole
  (no-entry blink frames read twice as WALK, 4/255). Its lower WALK recall fails closed (UNKNOWN,
  no click), costing speed, not safety. Record it as a safety-driven adoption that departs from
  3.36's bar 4 (my decision), keep bar 4 as the target, and fix the windmill next."
- **What changed** (`scripts/cursor_gate.py`, cursor-robust.md 6 / 6a):
  - `DEFAULT_CLASSIFIER = "robust2"`; `classifier="v3"` stays available by name.
  - A WALK-intent `gated_click` reads the FULL 6-grab series, 0.1 s apart, with no early stop.
    That is cursor@2's measured procedure: the same crop, mask, count and gap as
    `npc_click_test.read_series` (a parity test).
  - It clicks only when `series_verdict` is walk: one ring grab anywhere is NOENTRY.
  - Other intents (TALK, an intended WARP) keep the early-stop reads, now by the robust reader.
- **Who reads with it:** every caller of `cursor_gate.prober()`:
  - npc-click's click arms (3.32a, amended below);
  - talk@1 / talk_calibrate's contact click;
  - where_run, measure_delay, camera_validate, calibrate_projection, dataset_activity;
  - safety_signal_check.
- **Who does NOT:** the pre-registered rules that load `walk6.CursorRefs` themselves (walk@6-17,
  loot@1). They keep v3 as registered.
  - The walk rules also require the walk MARKER (no marker on a non-walkable cell), which refuses
    the no-entry clicks v3's hole would allow.
  - A rule adopts robust2 only through a NEW pre-registration or a recorded amendment (cursor-robust
    6 item 3).
- **Next (Batt):** fix the windmill: per-map ANIMATED regions measured with the cursor parked are
  masked, plus a fresh background per hover. That is cursor@3, pre-registered before it runs.

### 3.37 cursor@3 -- robust3 = robust2 + the per-view ANIMATED REGION (measured with the cursor parked) + a FRESH background per hover: a fresh live proof (pre-registered 2026-10-13 ~12:10 ICT at commit, BEFORE any cursor@3 data; Batt 2026-10-13, decision 3: "fix the windmill next: mask per-map ANIMATED regions (measured with the cursor parked) plus a fresh background per hover; pre-register that as cursor@3")
**Why:** cursor@2 (3.36) met every safety bar but failed bar 4 (WALK 0.848). The loss was on the
held-out alberta (0.682), and it was MEASURED to be the windmill.
- Its sails rotate in about 2 s. With the cursor parked, 20-60k px of the view change every 0.2 s.
- So the cursor mask |A - B| against ONE parked frame floods wherever a sail moved after the park.
- Prober9's 0.25 s "animated" map (two parked frames) catches only the sails' last quarter-second.

robust2 went live anyway (3.36's ADOPTION, safety-driven). **Bar 4 stays the target, and this is the
fix Batt named.** Nothing live changes here: the gate stays robust2 until Batt decides on this
result.

**The reader:** `robust3` = `cursor_anim.ProberAnim`, with robust2's reader unchanged (per-grab
`RobustRefs` + the no-entry ring over the 6-grab series). Code at 5f2f0ef (cursor_anim 223fa82, its scoring deebcaa)
(`scripts/cursor_anim.py`, `cursor_gate` classifier `robust3`). Two changes, nothing else:
1. **The ANIMATED REGION of the view**, measured with the cursor parked:
   - 13 grabs, 0.2 s apart (2.4 s, longer than the windmill's cycle);
   - a pixel is animated if ANY grab differs from the first by more than 60 (summed BGR,
     walk@9's threshold), grown by 2 px;
   - it is unioned with Prober9's 0.25 s map. Animated pixels never count as the cursor;
   - it is measured once per VIEW (`set_view((map, x, y))`: the camera follows the GM, so one GM
     cell is one view) and cached for the session. Batt's "per-map" region is realised per view of
     the map.
2. **A FRESH background:** the background is grabbed again right before each hover (the cursor still
   parked), not kept from the park.
- **Design check (offline, on synthetic frames; NOT data):** a rotating bar's whole sweep is
  covered by the cycle region, and two frames 0.25 s apart cover under 30 % of it
  (`test_cursor_anim.py`). On a synthetic windmill crop, robust2 floods to UNKNOWN and robust3 reads
  WALK (`test_cursor_robust.py`).
- **Its cost, for the switch decision (not a bar):** 2.4 s at the first park in each new view. A
  probe arm visits few views; a walk visits a new view every click.

**FRESH DATA** (all hover only, nothing clicked; the runs and their safety are as 3.36's):
- **The harness records BOTH readers' inputs on the same grabs:**
  - the probe arm runs with `--anim` (ProberAnim; its live log keeps the v3 references, as every
    probe arm does);
  - each crop keeps robust3's background and region AND robust2's own (Prober9's background and
    0.25 s map: `b2` / `anim2`);
  - `cursor_eval.py live` scores robust2, robust3, robust and the v3 gate on the identical grabs.
- **Arm B3, SWORD over a Poring:** `scripts/cursor_probe.py sword --anim --n 30 --seed 20261204`.
- **Arm A3, around NPCs:** `scripts/npc_click_test.py probe --anim` with:
  - **alberta, the windmill map, TARGETED** (not held-out: cursor@2 used it): `--near 116,57
    --seed 20261200`;
  - prontera `--near 156,191 --seed 20261201`;
  - prt_church `--near 103,74 --seed 20261202`.
- **HELD-OUT, once: morocc** `--near 140,111 --seed 20261203`.
  - No cursor test has used morocc. Its L3 NPC list is COMPLETE (39 NPCs).
  - Planned offline at 5f2f0ef (`plan`, the same seed): 4 NPCs (sprites 703, 741, 707, 837),
    990 probe points, 9 stand warps.
  - The spot first tried, (295, 153), held one drawn NPC (314 points): too thin. It was changed
    BEFORE any data.
  - A pilot comes first, never scored: `--npcs 1 --reps 1 --seed 20261207`. If the harness cannot
    run there, morocc is DROPPED and reported, not replaced.
- **Order:** B3, A3 alberta, A3 prontera, A3 prt_church, the morocc pilot, A3 morocc.
- Before each run: a client screenshot judged, and the UI gate.
- A run that exits early is re-run unchanged with its seed; the partial session is kept and not
  scored.

**Runs** (RDP, the GM; times ICT from the manifests; safety = the session's own banked packets
through `replay_safety.judge` over the manifest window: attack_request / npc_contact / act normal /
act pickup from the GM). NOT SCORED: no bar is computed until every arm has run and the truth
sheets are labelled.

| arm | session | time | records | safety |
|---|---|---|---|---|
| B3 sword, prt_fild08 | `20261013T172633-demo-cursor-probe-sword` | 17:26-18:12 | 30 trials, 367 crops | 0 / 0 / 0 / 0 |
| A3 alberta | `20261013T182009-demo-npc-click-probe-alberta` | 18:20-19:33 | 1,495 | 0 / 0 / 0 / 0 |
| A3 prontera | `20261013T193638-demo-npc-click-probe-prontera` | 19:36-20:52 | 1,498 | 0 / 0 / 0 / 0 |
| A3 prt_church | `20261013T205443-demo-npc-click-probe-prt-church` | 20:54-21:22 | 566 | 0 / 0 / 0 / 0 |
| morocc pilot (never scored) | `20261013T213555-demo-npc-click-probe-morocc` | 21:35-21:44 | 156 (3 stands; live reads walk 77 / talk 53 / unknown 26: the harness runs there, morocc is NOT dropped) | 0 / 0 / 0 / 0 |
| A3 morocc (HELD-OUT, once) | `20261013T215522-demo-npc-click-probe-morocc` | 21:55-22:43 | 990 (**188 from two DISPLACED positions**, below) | 0 / 0 / 0 / 0 |

- **A harness change between the pilot and A3 morocc (860871f, merged 21:44:31 by the reflog):** `npc_click_test.py` now
  REFUSES a plan that stands or walks inside a warp's trigger span, or on a map whose warps L3
  does not list (after a (100,56) banking stand warped the GM to prontera, 63e310e). It is a refusal, never a
  filter: a plan that passes is unchanged, so morocc's spots are as pre-registered. 85019f8 then
  limited the click cells to the click arm (a probe arm never walks to them).

- ➡️ **A deviation in the held-out morocc run, found AFTER it (22:43, from the chat log on the
  pre-run screenshot of the next run, then the session's own packets):** the server refused 2 of
  its 9 @warps ("Invalid coordinates, using random target cell") and put the GM on a free cell
  nearby (its map_change packets):
  - the NPC stand (131,116) -> (133,120): 126 records (64 cell, 62 sprite), 22:13-22:19;
  - the CONTROL stand (158,125) -> (154,118): 62 records, 22:40-22:43.
  - **Why:** the plan is built on the CLIENT's GAT; @warp tests the SERVER's map cache
    (CELL_CHKNOPASS), and on morocc they disagree on ~7,000 cells beyond the edge row and column
    (alberta ~5,100, prontera 46, prt_church 0). Both cells are walkable on the client and not on
    the server. collect_v2 already used both sources; npc_click_test did not. ➡️ Read precisely
    (2026-10-15, `scripts/map_agreement.py build`, edge row and column excluded): those totals count
    BOTH directions. Client-walkable / server-NOPASS (the direction that refuses a click or a
    stand): morocc 4,482, alberta 4,836, prontera 0. The reverse: morocc 2,517, alberta 255,
    prontera 46. Since Batt's decision 4 (2026-10-15) every live planner, npc_click_test included,
    draws on cells walkable in both.
  - **Every other @warp today landed where typed:** 202 of the 204 @warps in today's 33 banked
    sessions (each @warp line against the map_change that answered it). Among them: B3 30,
    A3 alberta 13, A3 prontera 13, A3 prt_church 5, the morocc pilot 3, and the npc-click church
    arm's 118. The 2 that did not are these two.
  - **The harness now refuses such a plan** (f275ab6: a stand, the control, or a click-arm cell the
    server will not let the GM stand on; a refusal, never a filter).
  - **How it is scored: AS PRE-REGISTERED, all 990 records.** The run did not exit early, so the
    re-run rule does not apply, and the held-out map is used once. A hover from a displaced position
    is still a real hover, and its truth is the labellers' eye label. The bars condition on that
    label (bar 2: sprite points labelled talk; bar 4: cell points + controls labelled walk), and
    the safety bars are per image. What the displacement changes is WHERE the cursor sat, not
    what truth is. **Reported beside the bars (not a bar):** every morocc number without the 188
    displaced records.
  - **Script-NPC touch areas** (checked 23:05, after npc-render B1 hit one, 3.38): no cursor@3 stand
    and neither displaced morocc position lies inside one (morocc.txt:32's 7x7 area ends one cell
    west of (154,118)); no touch dialog opened in any cursor@3 run.

- **Truth sets built 22:52-22:54** (`cursor2_truth.py sheets --judged robust3 --item-seed 20261205
  --strip-seed 20261206` run at a6a0754, where `cursor2_truth.py`, `cursor_eval.py` and the readers
  are byte-identical to 5f2f0ef; the five scored sessions pooled, the pilot excluded): **10,175
  images (204 pages) and 3,524 series strips (353 pages)**. The readers' live outputs
  (`cursor_eval.py live`, 21:46-22:51) are their input; no bar has been computed.
- **Two blind agent labellers**, briefed with 3.36's brief (paths moved to cursor3/; the page and
  item counts and a no-delete note added), in OPPOSITE page orders: A started 22:55, B 22:55.

**➡️ RESULT (2026-10-14 00:21 ICT; scored ONCE as written, `cursor2_score.py --judged robust3
--gate robust2 --sword-gain -0.02` run at 70b1bf5, the scorer byte-identical to 5f2f0ef; rc 1):
FAIL on bars 3 and 4. The SAFETY bars are MET on fresh data, held-out included. The windmill fix
did NOT help alberta: robust3 reads alberta WORSE than robust2. As pre-registered: no switch; the
live gate stays robust2.**
- **Truth:** the labellers agree on **10,175 / 10,175 images** (walk 5,211, talk 3,748, noentry
  850, sword 366; no pickup, warp, none or unclear) and **3,524 / 3,524 series** (yes 384,
  no 3,140). A took 56 min (22:55-23:51); B 1 h 25 min (22:55-00:20).
  - Labeller B, as in 3.36, used FLAGGERS (red-pixel counts, a 7-nearest-neighbour vote over its own
    labels, an outlier pick) only to choose tiles to re-view by eye (~1,000). It changed 75 labels,
    by its account all typing slips. The brief allows this; it is reported because a red-pixel count
    resembles the cue under test. Labeller A used no such check. Both agree on every item.
- **The bars** (robust3 judged; robust2 = the live gate):

| bar | robust3 | robust2 | v3 (`current`) | |
|---|---|---|---|---|
| 1a per image: cross-shape / WALK on another label | 0 / 0 (8,179 reads) | 0 / 0 (8,473) | 0 / 0 (7,605) | MET |
| 1b per series: WALK on a no-entry series | 0 of 1,762 WALK series (0 unclear) | | | MET |
| 1c as written (reported) | 9 (1 sword->walk, sword arm; 8 walk->noentry) | 8 (the same 8 walk->noentry) | 4 | |
| 2 TALK (>= 0.85) | **0.895** (1,188 / 1,328) | 0.925 | 0.773 | MET |
| 3 SWORD (>= 0.40, >= robust2 - 0.02) | **0.610** (114 / 187) | 0.663 | 0.096 | FAIL (< 0.643) |
| 4 WALK (>= 0.95, >= robust2 - 0.02) | **0.867** (1,085 / 1,252; CI 0.847-0.884) | 0.883 | 0.811 | FAIL (< 0.95) |
| NO-ENTRY (reported) | 0.923 (661 / 716) | 0.980 | 0.120 | |

- **Per map** (robust3 / robust2):
  - **alberta, the question this version answers:** WALK **0.626 / 0.667** (372), TALK 0.700 /
    0.791 (440), NO-ENTRY 0.793 / 0.947 (265). robust3 is lower on every class.
  - prontera: identical (WALK 0.967, TALK 0.982, NO-ENTRY 1.0). prt_church: identical (WALK 0.955,
    TALK 1.0, NO-ENTRY 1.0).
  - **morocc, HELD-OUT:** identical and perfect: WALK 270 / 270, TALK 272 / 272, NO-ENTRY 174 / 174
    (v3: 0.967 / 0.838 / 0.213).
  - sword arm: SWORD 0.610 / 0.663; its walk controls 0.900 / 0.956 (90).
- **The morocc sensitivity (reported, not a bar):** without the 188 displaced records, morocc reads
  WALK 232 / 232, TALK 272 / 272 and NO-ENTRY 96 / 96 for both readers. Pooled WALK becomes 0.862
  (robust3) / 0.879 (robust2), and the verdict is unchanged.
- **Why alberta fell (reported, not a bar; the definitions are Claude's, chosen after the result):**
  the crops keep robust3's region only in the 64-px window around each hover; the full-view size
  was not recorded.
  - In 4 of alberta's 13 views (the windmill views: stands (108,54), (115,57), (116,48), (124,56)),
    the 2.4 s cycle region covers a median **82-100 %** of that window. In every other view of every
    map it covers 0 %, so there robust3 reads exactly as robust2.
  - **Of robust3's 139 alberta WALK misses, 108 had the hotspot pixel inside its masked area; of its
    233 hits, 0.** For robust2: 28 of 124 misses, 1 of 248 hits.
  - So the region masks the cursor ITSELF where the sails sweep: the risk named under "Expected".
    Those reads fail closed to UNKNOWN; that is safe, and it is a recall loss.
  - Masking the windmill's whole sweep removes the cursor with it. A different fix would compare
    against a background at the SAME point of the sails' cycle. That is Claude's reading, not a
    pre-registration. ➡️ **Batt 2026-10-15 (decision 3): AVOID moving scenery instead; robust2
    stays the live gate.** See 3.32 amendments 3 / 3a. On this session's data, robust2 reads 236
    of the 264 alberta WALK hovers outside the cycle region (0.894).
  - ➡️ **PARKED for a later cursor version (Batt 2026-10-15): a reader-CONTRAST question.** Of
    robust2's 28 alberta WALK misses outside the region, 13 are in ONE view, (123,68), out of its
    22 WALK hovers there. The tiles show a clear arrow on PALE GREY COBBLESTONES, and both the
    animated map and the region are empty there: low contrast, not motion. Avoidance does not
    touch it.
- Outputs: `/dev/shm/poring-lab-tmp/cursor3/` (result.json, result-nodisp.json, live/, truth/,
  the labels in c3-labeller{A,B}/; local, client pixels).

**Truth (fixed BEFORE any bar is computed):**
- `scripts/cursor2_truth.py sheets --judged robust3 --item-seed 20261205 --strip-seed 20261206` at
  5f2f0ef (cursor_anim 223fa82, its scoring deebcaa):
  - IMAGES: grab 0 of every crop + every grab any reader's read came from (v3, robust, robust3);
  - SERIES: every robust3 WALK series + as many others (seeded).
- Two blind labellers, with 3.36's brief (eye only; no pixel rule may decide a label).
- Truth = both agree; otherwise unclear.

**The bars** (`scripts/cursor2_score.py --judged robust3 --gate robust2 --sword-gain -0.02` at
5f2f0ef (cursor_anim 223fa82, its scoring deebcaa); robust3 judged, with robust2 (the live gate), robust and v3 beside it):
1. **SAFETY, hard; one error fails, on any map:**
   - (a) per image: 0 cross-shape and 0 WALK on another label;
   - (b) per series: 0 WALK verdicts on a series both labellers say shows the no-entry sign; a WALK
     series without agreement is INCONCLUSIVE;
   - (c) 3.35's "as written": reported.
2. **TALK:** sprite points labelled talk: read twice >= 0.85.
3. **SWORD:** box points labelled sword: >= 0.40 (>= 100 probes) and not below robust2's - 0.02.
4. **WALK, the target Batt kept:** cell points + controls labelled walk: >= 0.95 pooled, and not
   below robust2's - 0.02.
5. **Reported, not bars:**
   - NO-ENTRY;
   - **alberta's WALK for robust3 vs robust2** (the question this version answers);
   - every bar per map;
   - the animated region's size per view, and the share of misses whose cursor fell inside it.
- **INCONCLUSIVE:** fewer than 200 talk or 100 sword probes.

**Not decided here:**
- whether robust3 replaces robust2 live (Batt, with its 2.4 s-per-view cost);
- the rules that would adopt it (each through its own pre-registration or amendment).

**Expected (Claude's reading; NOT a bar):**
- alberta's walk recall rises: the stale-B floods go. Probes whose cursor sits inside the sails'
  sweep stay UNKNOWN (fail closed).
- prontera and prt_church are ~unchanged (little animated scenery).
- **The risk:** on a view with much animated scenery (crowds, a busy fountain), a large region masks
  the cursor itself and lowers recall there. Reported per view.

### 3.38 npc-render@1 -- every static NPC drawn from GAME DATA: its rendered position against packet truth, and its NO-CLICK region against live hovers (pre-registered 2026-10-13 13:53 ICT at commit 3f8831d, BEFORE any of its data; Batt 2026-10-13: "use the GAME DATA, not the detector ... This is the 'N1-N3 sprite path' in labels-v2: make it the first NPC step, with a pre-registered check of the rendered positions/masks against packet truth and live hovers")

> ➡️ **RESULT, scored 2026-10-15 17:50 ICT: B FAILS on B-SAFETY (TALK outside the region 3.56 %
> against <= 1 %; prontera 6.9 %, new_1-2 2.06 %, alberta_in 0 %). B-COST is met (9.2 %), and n is
> met (1,404 TALK).** A is INCONCLUSIVE on n, with every measured bar met. As written, the region
> is NOT used. The failing points are reported below ("B. scored"). A new hit-box model is to be
> pre-registered; the box's form stays Batt's decision ("Not decided here").

**The design, built and measured on design data only:**
[docs/planning/npc-render.md](planning/npc-render.md) (PROPOSED; merged 974bdd7; code
`scripts/npc_render.py`, `scripts/npc_render_measure.py`). For a map, our cell and the camera
path, every L3 NPC that is drawn is rendered from its script line (cell, FACING, sprite) through
`predict_sprite`:
- the MASK is the union of the idle animation frames;
- the envelope is its box.
- Fail closed: unsupported NPCs are listed, never guessed; NPCs beyond the server's 14-cell view
  area are not drawn.

**What the design data already says** (section 3 there; these sessions are NEVER used below):
- **Positions:** outdoor median 1.4 px, indoor 4.1 px. The indoor error is a linear field that grows
  toward the screen edges.
- **Identity:** 3,214 / 3,214 sightings agree with the packets on cell, sprite and facing.
- **The drawn MASK is NOT the clickable area:** it holds 479 / 1,225 = 0.391 of cursor@2's
  TALK-labelled hovers.
  - The client answers TALK up to ~+-34 px from the feet and ~14 px below them.
  - So Batt's "NO-CLICK region = the rendered sprite's pixel mask, not a box or a cell guess",
    measured against item 5's probes as he asked, would leave ~61 % of the TALK points clickable.
  - The region under test is therefore the **mask OR a PROVISIONAL hit box** (|u - feet_u| <= 42
    px, from 8 px above the envelope's top to 16 px below the feet). It was fitted IN-SAMPLE (0.985
    TALK inside, 0.118 other).
  - A box-shaped part departs from Batt's design. **Adopting it is Batt's decision**, open below.

**Fixed now** (changed only by a new pre-registration):
- the code at the commit that adds this section;
- k = 0.14; search radius 24 px; a match counts at NCC >= 0.5; at most 15 frames per session;
- the hit box: HIT_HALF_W 42, HIT_TOP 8, HIT_BELOW 16 (screen px);
- the pixel camera rule PIXEL_MIN_SCORE 0.5 / PIXEL_MAX_OFFSET 12 / PIXEL_MIN_SEEN 2 (its verdicts
  reported only);
- **sprites:** ONE measurement table built before the first run:
  `npc_sprites.py build --measure-map prontera --measure-map alberta_in --measure-map new_1-2
  --out /dev/shm/...` (never data/kb), its sha256 in the run record. An NPC it does not cover is
  reported, never rendered.

**A. Positions vs packet truth** (offline, on FRESH sessions: every banked session recorded AFTER
this commit that stands our GM on maps with drawn NPCs):
- **n:** >= 300 confident matches outdoor and >= 100 indoor, from >= 3 sessions each. Fewer =
  INCONCLUSIVE.
- **A1 (identity, hard):** every rendered NPC the packets show agrees on cell, sprite and facing.
  One disagreement FAILS A.
- **A2 (outdoor):** >= 95 % of matches within 6 px, and the median <= 2 px.
- **A3 (indoor):** >= 95 % within 12 px. The indoor camera is NOT refitted first; a refit is its own
  pre-registration.
- **A4 (k):** k 0.14 scores above 0.1333 on >= 75 % of paired matches (reported per map).

**B. Live hovers** (fresh `npc_click_test.py probe` runs: hover only, nothing clicked; the UI
gate and a judged screenshot before each run; the spots fixed by offline `plan` BEFORE this
commit):
- **B1: prontera `--near 70,356 --seed 20261190`**: 5 NPCs (733 x2, 734 x3), 1,316 probes.
  - The draft's `--near 150,100` planned 1 NPC / 312 probes, short of the 150-TALK floor. It was
    replaced by the densest prontera group in L3 away from cursor@2's spot and from the 722 flags.
    That was decided on the plan alone, before any data.
- **B2: alberta_in `--near 53,43 --seed 20261191`**: 2 NPCs (86, 59), 490 probes. Indoor, no design
  probe.
- **B3: new_1-2 `--seed 20261192`**: 6 NPCs (117, 726, 105, 84, 90, 92), 1,554 probes. The training
  grounds; no `--near`, the seed fixes the choice.
- ➡️ **Warp spans, checked offline 2026-10-13 21:46 (the plans unchanged):** no B stand or control
  stand lies inside a warp's trigger span (B2 has one stand, (65,34), one cell outside alb16-1's
  edge). One B3 CLICK cell, (124,104), is inside newwarp6003a; the B runs only hover, so it is never
  walked to. The harness now refuses a span conflict before any input (860871f; click cells in the
  click arm only, 85019f8).
- **B4 (a positive case for the camera rule; REPORTED, not a bar):** a few frames after a
  deliberate right-drag rotation and after a zoom. ONLY Batt rotates or zooms. A map change follows.
  The input-log guard must say rotated / zoomed; the pixel rule's verdicts are reported.
- **Truth:** cursor@2's labelling. `cursor2_truth.py sheets` on the B sessions, two blind labellers,
  truth = agreement, grab 0 of every probe.
- **n:** >= 600 TALK-labelled points in total and >= 150 per run. Fewer = INCONCLUSIVE.
- **Bars** (`npc_render_measure.py click` at this commit; points within 60 px of an UNRENDERED NPC
  are reported apart, not counted):
  - **B-SAFETY (hard):** TALK points OUTSIDE the NO-CLICK region <= 1 % overall and <= 2 % in every
    run;
  - **B-COST:** other points (walk / noentry / sword) inside the region <= 20 % overall.
  - **Reported, not bars:**
    - the drawn MASK's own TALK share (Batt's design, as asked);
    - the box's share;
    - the dilation curve;
    - per sprite, the TALK points outside the region with their offsets from the feet.
- **Order in the client queue:** after cursor@3 (3.37). A judged screenshot before each run; a run
  that exits early is re-run unchanged with its seed, its partial session kept and never scored.

**What PASS would unlock, if Batt adopts it** (each adoption is his decision; nothing changes on a
PASS alone):
- the walk gate's NO-CLICK region = the rendered region on maps where the render is `complete`
  (L3's PROVISIONAL footprint stays elsewhere);
- labels v2 NPC boxes rendered per frame for sprites whose N3 reading is `fit`;
- occlusion checks (expected vs observed pixels).

**FAIL:** the region is not used. The failing points (offset, sprite, map) are reported, and a new
hit-box model is pre-registered.

**➡️ The sprite table, built 2026-10-13 14:45 (before any run):**
`/dev/shm/poring-lab-tmp/npc-render/n1-measure-3.38.json`. It holds 77 sprites, every sprite B's
plans need (733, 734, 86, 59, 117, 726, 105, 84, 90, 92), and 0 problems. sha256
`690537890ad2728103dc1a8905db3f0e535c0b7f11451b2aa462440929252540`.

**➡️ B runs** (RDP, the GM, hover only; times ICT; the sprite table's sha256 re-checked
`690537890ad2...` at 22:43, before B1). NOT SCORED until every B run is in and labelled.
- **Harness changes since 3f8831d, each a REFUSAL that changes no plan that passes:** a stand or
  walked cell inside a warp span (860871f; click cells in the click arm only, 85019f8); a stand,
  control or click-arm cell the SERVER's map cache will not let the GM stand on (f275ab6). The B
  plans pass both: no stand inside a span (above), and on prontera, alberta_in and new_1-2 no cell
  is client-walkable and server-NOPASS (beyond the edge row and column), so every client-walkable
  stand is one the server accepts. cursor@3's held-out morocc is why the second exists (3.37).

| run | session | time | records | safety |
|---|---|---|---|---|
| B1 prontera `--near 70,356 --seed 20261190` | `20261013T225520-demo-npc-click-probe-prontera` | 22:51-22:55 | **0: STOPPED FOR A PERSON at the first stand** (below) | 0 / 0 / 0 / 0 |
| B1' prontera `--near 148,326 --seed 20261190` | `20261015T140725-demo-npc-click-probe-prontera` | 10-15 14:07-14:55 | 1,000 of 1,000, `complete` | 0 / 0 / 0 / 0 |
| B2 alberta_in `--near 53,43 --seed 20261191` | `20261015T151857-demo-npc-click-probe-alberta-in` | 10-15 15:18-15:42 | 479 of 490, `complete` (11 probes skipped by the harness's stale-park rule) | 0 / 0 / 0 / 0 |
| B3 new_1-2 `--seed 20261192` | `20261015T154644-demo-npc-click-probe-new-1-2` | 10-15 15:46-17:01 | 1,554 of 1,554, `complete` | 0 / 0 / 0 / 0 |

- Safety = attack_request / npc_contact / our act normal / our act pickup over each manifest's
  window (`replay_safety.judge`), and no npc_say / wait / menu in it either. Every typed `@warp`
  (9 / 5 / 13) has its map_change on the planned stand. A judged screenshot came before each run.
- ➡️ **The truth step, 2026-10-15** (as fixed at 14:10 below; NOT SCORED until both labellers are
  in):
  - `cursor_eval.py live` on each session (B3's 17:01-17:09), then the ONE sheet set at 17:10:34:
    `cursor2_truth.py sheets --judged robust2 --item-seed 20261208 --strip-seed 20261209` over the
    three: **6,396 images on 128 pages** (and 2,056 strips on 206 pages, built, not labelled).
  - The four scripts are unchanged since 3f8831d (`git log 3f8831d..HEAD` on them: 0 commits), and
    so is `labels_v2.py`, which the scorer imports. In `poring_dataset`, f0ff35c only ADDS
    `walkable.py`, which nothing in the scorer imports.
  - Two blind labellers (cursor@3's brief, images only; A ascending, B descending) started
    17:12 and 17:15.
  - **The scorer's sprite inputs, made precise BEFORE any label exists** (the 14:10 note says
    "`--sprites` the pre-built table"; `npc_render_measure.py click` takes the table's sprites as
    two arguments):
    - `--names`: the pre-built table's job -> file stem, restricted to its 77 jobs:
      `/dev/shm/poring-lab-tmp/npc-render/names-3.38.json`, 76 jobs, sha256 `429a6f310a98...`.
      722 (the guild flag) has no SPR / ACT and stays unsupported, as the table says.
    - `--sprites`: the decoded files in `/dev/shm/poring-lab-tmp/sprites/data/sprite/npc`, from
      the design decode (npc-render.md section 2; `n2-measure-names.json`). Its stems agree with
      the table's client sprite for every shared job, and both files exist for all 76.
    - So an NPC outside the table is reported, never rendered, as fixed.
    - Smoke check of these inputs on the DESIGN data only (cursor@2's three probe sessions and their
      published labels, not B): rc 0. 943 design probes are `target_unsupported` with the
      restricted names, against 691 with the 90-job design names: NPCs outside the table are
      excluded, not rendered.
- ➡️ **B. scored 2026-10-15 17:50 (`npc_render_measure.py click` at the fixed code, the three B
  sessions, merged labels, the sprite inputs above): FAIL on B-SAFETY.**
  - **The labels.** A (17:12-17:48, ascending) and B (17:14-17:39, descending) labelled all 6,396
    images, with 0 unclear on either side. They **agree on all 6,396**: walk 3,015, talk 2,773,
    noentry 604, warp 4, and no sword, pickup or none. So `merged.json` holds every index
    (sha256 `7dfa9b3527a3...`). cursor@2's labellers also agreed on all of theirs (8,190).
    - Each labeller logged its own fixes by index: A, 3 re-recorded pages + 32 tiles; B, 4 tiles.
    - **Independence check:** B finished at 17:38:41. The last 64 MB of A's transcript (one
      allowed byte range, 17:37:46-17:48:26) has no tool call on B's directory: 274 path uses, all
      `labellerA`. B's working record was last read at 17:39:09, by B's own final copy.
    - The earlier part of A's transcript (208 MB on the shared disk) was not read: the big-file
      rule allows byte ranges, not a chunked whole-file read. A's first pass was complete at
      17:32:28, before B's labels file existed.
  - **n: met.** 3,033 probes, all usable: no unsupported target, no moving GM, 0 points near an
    unrendered NPC. **TALK 1,404** (>= 600): prontera 522, alberta_in 201, new_1-2 681 (each >= 150).
  - **B-SAFETY (hard): FAIL.** TALK points OUTSIDE the region (mask OR hit box): **50 / 1,404 =
    3.56 %** (bar <= 1 %). Per run: prontera **36 / 522 = 6.90 %**, new_1-2 **14 / 681 = 2.06 %**,
    alberta_in 0 / 201 = 0 % (bar <= 2 %).
  - **B-COST: met.** Other points inside the region: **149 / 1,625 = 9.17 %** (walk 89, noentry 60;
    bar <= 20 %). The scorer's own "other" set adds warp: 149 / 1,629 = 9.15 %.
  - **Reported, not bars:**
    - The drawn MASK alone (Batt's design) holds **37.4 %** of TALK (525 / 1,404); the envelope
      box 53.2 %; the region (mask OR hit box) 96.4 %.
    - Mask dilation, TALK / other share at d px: 0: 0.374 / 0.004; 4: 0.473 / 0.008; 8: 0.587 /
      0.022; 12: 0.644 / 0.042; 16: 0.748 / 0.101; 20: 0.863 / 0.125; 24: 0.947 / 0.175; 32: 0.984 /
      0.297.
    - Box dilation: 0: 0.533 / 0.005; 8: 0.692 / 0.039; 16: 0.916 / 0.144; 20: 0.966 / 0.188; 24:
      0.980 / 0.253; 32: 0.984 / 0.396.
    - TALK outside the mask: 879. Their distance to it: median 14.2 px, p90 23.2, max 46.4.
  - **The failing TALK points, per map and target sprite** (offset from the target's feet, du / dv
    screen px; probes repeat some points):

    | map | sprite | TALK | outside | the outside points (du, dv) |
    |---|---|---|---|---|
    | prontera | 734 | 135 | 18 | (32,25) (51,-14) (60,-21) (60,0) (61,23) (62,-26) (63,-2) (66,24) |
    | prontera | 112 | 146 | 18 | (-76,1) (-74,23) (-72,-27) (-71,-23) (-71,0) (-51,-14) (-40,23) (0,-98) |
    | new_1-2 | 105 | 128 | 12 | (-6,26) (-4,26) (0,24) (30,26) (32,26) |
    | new_1-2 | 117 | 111 | 2 | (109,77) |
    | the other 7 (alberta_in 59 / 86; new_1-2 84 / 90 / 92 / 726; prontera 105) | | 884 | 0 | |

    - prontera's 734 (148,326) and 112 (152,326) stand 4 cells apart. Their failing points mostly
      lie in the gap between the two (734 at du +51..+66, 112 at du -71..-76): the client answers
      TALK there, outside both regions.
    - new_1-2's 105 answers down to 24-26.5 px below its feet; the box stops at 16.
    - This is reported, not explained. Explaining it would be a new measurement.
- ➡️ **A. Positions vs packet truth, computed 2026-10-15 17:36-17:37: INCONCLUSIVE (n short).
  Every measured bar is met.**
  - `npc_render_measure.py align` at the fixed defaults (k 0.14 beside 0.1333, radius 24, NCC >= 0.5,
    <= 15 frames per session), with the scorer's sprite inputs above.
  - **Sessions:** every session recorded after 3f8831d up to B3, 38 in all
    (`/dev/shm/poring-lab-tmp/npc-render/partA-sessions.txt`). The NAS holds none of that age.
    - 23 RDP sessions were read.
    - **15 were EXCLUDED:** talk-cal garnet, 10-13 16:13-16:58, 4 frames each, recorded on the
      CONSOLE path during S2 attempt 1. The fixed code has no frame-timing benchmark for
      `('console', None, 'x11')` and stops ("pass --offset-ms"), and `align` takes no offset. The
      code is unchanged.
  - **n:** outdoor **107** confident matches from 7 sessions; indoor **82** from 7. The floor is
    300 / 100, so **INCONCLUSIVE**.
    - Outdoor: alberta 51 (cursor@3), new_1-2 27 (B3), prontera 15 (B1' 9, cursor@3's A3 3, the 10-13 warp-frames session 3), morocc 14.
    - Indoor: prt_church 62 (talk-cal henson 15 + 15, npc-click click 15 + 15, cursor@3's A3 2), alberta_in 20 (talk-cal
      merchant 15, B2 5).
    - Excluded sightings: near UI 264, NPC partly off screen 170, NPC overlapping a unit 147, near
      an unsupported NPC 162, no frames 7. Matches at the search edge: 0.
  - **A1 (identity, hard): met.** 1,242 rendered NPCs against the packets: cell, sprite and facing
    agree on all 1,242, 0 disagreements.
  - **A2 (outdoor): met.** 100 % within 6 px (p95 2.2, max 3.6 px); median 1.0 px.
  - **A3 (indoor): met.** 100 % within 12 px (p95 5.1, max 9.4 px). The indoor camera was not
    refitted.
  - **A4 (k): met on every map.** k 0.14 scores above 0.1333 on 189 of 189 paired matches
    (prt_church 62/62, alberta 51/51, new_1-2 27/27, alberta_in 20/20, prontera 15/15, morocc
    14/14); median NCC 0.69 against 0.48.
  - Reaching n needs more banked RDP frames with drawn NPCs in view: ~190 more outdoors, ~20 more
    indoors. No collection is planned; that is Batt's call.

- ➡️ **B1 STOPPED (22:55), nothing hovered, nothing typed after the stop.** The first @warp put the
  GM on (73,348), inside the TOUCH area of a hidden script NPC (`#tour`, knight_skills.txt, at
  (69,351), span 5,5: cells 64-74 x 346-356). Its OnTouch dialog opened on arrival ("[?]"
  ... with NEXT). The UI gate then refused the next typed line and stopped the run for a person
  (frame `/dev/shm/poring-lab-tmp/ui-gate/20261013-225538.png`). The packets show map_change
  (73,348), then npc_say x4 + npc_wait, and NO npc_contact: the server ran it; we sent nothing.
  - **The dialog is LEFT OPEN for Batt.** The gate says "a person"; Claude does not close it. Its
    script (read from the pinned source) is two NEXT pages, then CLOSE, with no menu. Its only
    state change is KNGT_SK 1 -> 2, for a character on that quest step. ➡️ **Gone since Batt
    CLOSED THE CLIENT** (reported 2026-10-15 10:17 ICT), never clicked through. Nothing changed:
    the GM has no KNGT_SK (DB, 2026-10-15).
  - **B1 cannot be re-run unchanged:** all 5 of its NPCs (72-78 x 352-358) sit in or beside that
    area, and the seeded stands land inside it. The harness now REFUSES such a plan (1d78ee5:
    stands and walked cells inside an L3 touch area). The stopped session's manifest said
    `ended: complete` (a bookkeeping bug, fixed in the same commit); it is KEPT and not scored.
  - **B2 (alberta_in) and B3 (new_1-2) are unaffected:** L3 lists no touch area on either map.
    B1's replacement is Batt's call; a proposal follows when it is planned.
- ➡️ ~~PROPOSED amendment (NOT accepted; Batt decides):~~ ➡️ **ACCEPTED by Batt 2026-10-15 10:17
  ICT ("B1' accepted, then B2, B3"): B1' = prontera `--near 148,326 --seed 20261190`** (B1's seed
  kept). It runs FIRST, then B2 and B3, unchanged. Chosen on the PLAN ALONE, before any B1 hover (B1 has none), by
  B1's own rule: the densest prontera L3 group away from cursor@2/@3's spot (156,191; Chebyshev
  >= 20) and from the 722 flags (> 12). Every candidate (73: each drawn L3 NPC's cell as --near) was
  planned with B1's seed, and those failing any of the three refusals were dropped.
  - B1': 4 NPCs (sprites 112 at (152,326), 734 at (148,326), 105 at (151,330) and (160,330)),
    1,000 probes; 0 conflicts. All 3 sprites are in the pre-built table (no problems).
  - B1 had 5 NPCs / 1,316 probes. The B runs then plan 3,044 probes against 3,360. The n rule is
    unchanged (>= 600 TALK points in total and >= 150 per run; fewer = INCONCLUSIVE).
  - The runners-up (816-814 probes): (29,200), (282,208). (55,350), 812 probes, is refused: one of
    its stands is inside #tour.
  - Search: `/dev/shm/poring-lab-tmp/warpcheck/b1_search.py` (local), 23:04-23:11.
- ➡️ **2026-10-15 10:17-10:45 ICT: the client CANNOT BE RELAUNCHED; the B runs wait for Batt.**
  Nothing was hovered, clicked or typed in game.
  - **Before the launch:**
    - a judged screenshot showed a bare desktop;
    - ASSIST was on, and the interlock was red `no_session`, as expected with no client.
    - The GM's saved cell is prontera (58,361) (DB `last_x/last_y`; last GM login 10-10 02:51 ICT),
      not (73,348).
    - That cell passes the three stand checks (`npc_click_test.check_warps`) and lies 6 cells
      outside #tour's edge. So no touch dialog was expected at login, and the scoped close
      Batt allowed (talk1.decline_all on #tour only) was never needed.
  - **Two launches from the "Ragnarok Offline" shortcut (`ro_agent.py launch`, 10:21 and 10:28,
    the second after the shell was minimised) started nothing.**
    - No client process; the lab watcher killed nothing (0 KILLED lines). No Application error.
    - The Code Integrity log has event 3033 at both moments: `cmd.exe` "attempted to load
      ...\RO-rAthena\client\PoringLab.exe that did not meet the Enterprise signing level
      requirements". These are the only such blocks in 5 days.
    - **Smart App Control is ON** (`HKLM\...\CI\Policy VerifiedAndReputablePolicyState = 1`).
    - `PoringLab.exe` is NotSigned (12,896,256 B, 2026-09-30). `sunshine.exe` is NotSigned too: it is
      running now, but its next start is likely refused the same way, which would stop the S2 path.
  - **A Windows setting, so a person's decision** (ADR-0019; the agent never changes Windows
    security settings or works around them). No further launch was attempted.
  - Deferred with it, because each ends in a GM login: the guarded `restart:rathena` (group 20,
    decision 5) and `recreate:sniffer` (Amendment C). The sniffer shares rathena's network
    namespace, so a rathena restart needs the sniffer step, and that step re-logs the GM by itself.
    The §2a positive cases follow them.
  - Read-only evidence: `/dev/shm/poring-lab-tmp/shots/relaunch-*.png` and
    `/dev/shm/poring-lab-tmp/relaunch/diag*_crop.png`.
- ➡️ **2026-10-15, Batt's decision 4 ("every walk rule and planner uses only cells walkable in
  BOTH sources"): `npc_click_test.py` DRAWS its plans on the client's GAT AND the server's map
  cache** (836cc8b; a map the server's cache lacks is refused). The refusals above stay.
  - **B1', B2 and B3's plans are BYTE-IDENTICAL before and after.** Both the `plan` output and
    the full `make_plan` value were compared, main c7e9c72 against the change. sha256 (first 8
    characters):

    | run | `plan` output | full plan |
    |---|---|---|
    | B1' prontera `--near 148,326 --seed 20261190` | `93ebf840` | `c25f9386` |
    | B2 alberta_in `--near 53,43 --seed 20261191` | `6950c067` | `d0313060` |
    | B3 new_1-2 `--seed 20261192` | `e8a5eb6b` | `4ec64d80` |

  - Decision 3's animated-region avoidance does NOT change these plans: they are cursor
    measurement probes (3.32 amendment 3, Claude's reading, for Batt to correct).
- ➡️ **The truth step, fixed 2026-10-15 at 14:10 while B1' runs, before any B sheet exists** (3.38
  says "cursor@2's labelling ... grab 0 of every probe"; these are the details it left open):
  - `cursor_eval.py live` on each B session, then ONE sheet set over all three:
    `cursor2_truth.py sheets --judged robust2 --item-seed 20261208 --strip-seed 20261209`.
    Both seeds are unused before this.
  - Two blind labellers with cursor@3's brief label the IMAGE pages only. B's bars use grab 0 of
    every probe; the series pages are built by the tool but not labelled or used.
  - Truth = the images both labellers agree on. The scorer's `--labels` is a merged file holding
    ONLY the agreed indices; a disagreement is unclear and is left out. Their count is reported.
  - The scorer: `npc_render_measure.py click --sprites` the pre-built table (sha256
    `690537890ad2...`, re-checked 13:59 before B1').
  - `npc_render_measure.py`, `npc_render.py`, `cursor2_truth.py` and `cursor_eval.py` are
    unchanged since 3f8831d (git log).
  - Reported apart (decision 3, (b)): B2's and B3's hovers inside a measured animated region, once
    those maps are measured. B1' (prontera 148,326) lies outside the measurement scope.

**Not decided here (Batt):**
- the hit box itself (a box, against "not a box or a cell guess");
- ~~decoding MIXCRYPT sprites at RUN time. Claude reads "the client's sprite files (decoded
  locally, never committed)" in Batt's note as the OK; he confirms;~~ ➡️ **DECIDED 2026-10-15
  (Batt, decision 7): "MIXCRYPT at run time: OK, local only, never committed."**
- the indoor camera refit (npc-render.md 3.5);
- widening N1 beyond his scope (46 sprites; the measurement table covers more);
- 909's class.

### 3.34 learn_skill@1 -- spend skill points in the skill window (DESIGN 2026-10-09 ~19:50; NOT pre-registered; Batt ~19:30: "add the new skill the job change needs: allocating skill points (Basic Skill > 8) via the skill window, as an L1 concept with its own alone-test")
> ➡️ **DECIDED (Batt, 2026-10-13, decision 5):** "@streset / @skreset for GM group 20 (lab)".
> They are added to `groups.yml` in place and apply at the next guarded rathena recreate (as
> `@monsterignore`, 3.33), never during a client run. This unblocks allocate_stat@1 (irreversible
> without @streset) and gives learn_skill@1 a server-side restore.
**The concept:** `char.learn_skill` (L1, packages/poring_skills, updated): the first workflow's
Merchant change needs the novice's Basic Skill above 8 (labels-v2-plan section 7.4).

**The alone-test, as designed (to be pre-registered with n, seeds and the bar before any trial):**
- **Start state** (the GM's fixed state, 3.20a): Base / Job Lv 1, Basic Skill 0.
  - `@joblevelup 9` gives the 9 points (Job Lv 10). That is a level change, so the notices come
    back; `gm_state` clears them by the status window.
- **One trial:**
  1. Open the skill window by its L2 shortcut (open_window@1's skills anchor).
  2. Find Basic Skill's row by its icon.
  3. Press its raise control N times (N seeded, 1-9), clicking only on the measured control; apply if
     the build asks.
  4. Close the window by its chord.
  5. Read the row's level and the points left from pixels.
  6. Restore: `@joblevelup -49`. In the pinned server that RESETS the skills when the unspent points
     are fewer (atcommand.cpp joblevelup, pc_resetskill), so the next trial starts at Job Lv 1 with
     Basic Skill 0.
- **Judged offline:** the server's `skill_update` (ZC_SKILLINFO_UPDATE 0x010E, already decoded) for
  skill 1 at level N, and SP_SKILLPOINT. Success = level N exactly, the points dropped by N, and
  no other skill changed.
- **Runtime outcome (pixels):** the row's level digit and the points readout. These need a small
  digit reader, as the weight reader does.

**Prerequisites before pre-registration:**
- The raise control's place in the skill window (an L2 binding), measured from banked frames of a
  live, hover-only look.
- The window's layout for a Novice's tree.
- Whether the 2021 client asks for an "apply" after the raises.
- The click is a NEW UI click: registered in the click census, and only on the measured control.
- A positive case for the offline judge: one deliberate raise, seen as `skill_update`.

**➡️ PREREQUISITES MEASURED LIVE, 2026-10-09 20:39-20:42 ICT (RDP, the GM, v1 training alongside on
the GPU; frames and packets local in `/dev/shm/poring-lab-tmp/learn_skill/`):**
- **Start:** the GM's fixed state recorded (gm_state: Base / Job Lv 1, no notices; DB read-only:
  Novice, all stats 1, 48 unspent status points, 0 skill points, no skills). `@joblevelup 9` ->
  `stat_change` job_level 10 and skill_point 9.
- **The window** (Alt+S, the L2 `skills` chord): "Skill Tree", the Novice column; Basic Skill is the
  first icon (highlighted while points remain), the two quest skills (First Aid, Play Dead) greyed.
  Bottom right: an APPLY button (적용) and a RESET button (초기화); bottom left "Skill Points : 9".
  It opened at desktop (460,280)-(998,676) (the client remembers the last place): the L2 binding
  must be relative to the window's title anchor, not absolute.
- **Hover-only:** no "+" control and no tooltip appear over the icon.
- **The raise is TENTATIVE:** one single click on the icon shows a red "+1" beside it and "Skill
  Points : 8(1) / 9". Nothing is sent (no packet).
- **The 2021 client DOES ask for an apply, and a confirmation:** APPLY opens a modal ("Once used,
  skill points cannot be re-allocated. Would you like to use the skill points?") with OK (확인) and
  Cancel (취소). OK sends the request.
- **THE POSITIVE CASE (proven, live sniffer):** after OK, `skill_up_request` (CZ_UPGRADE_SKILLLEVEL
  0x0112, skill 1) -> `skill_update` (0x010E: skill 1, level 1) + `stat_change` skill_point 8 +
  `skill_list` (0x0B32, the full list) within 1 ms of each other. The window then shows "1" under the
  icon and "Skill Points : 8" (the runtime pixel outcome).
- **The restore has a client-sync gap (pinned pc.cpp `pc_resetskill`):** `@joblevelup -49` gave
  `stat_change` job_level 1 and skill_point 0, and the server reset Basic Skill to 0, but with flag 0
  it sends NO skill list (only flag&1 does). The client kept showing Basic Skill "1" (stale) after
  the restore. The full list is resent only at a login (`connect_new`) or after a raise
  (`pc_skillup`). So a trial after this restore would start from a stale picture (and a seeded N = 9
  could not even be entered: the client believes one level is taken).
  - **Options:** (a) a re-login before each trial (slow, existing tools), or (b) the stock
    `@skreset` (pc_resetskill flag 1, which sends the list) in group 20, lab only, like
    baselevelup / joblevelup: **Batt's call** (CLAUDE.md: group 20's commands are his approvals).
  - The GM's client shows the stale "1" until its next login (the server is at 0; harmless to the
    other rules, which do not read the skill window).
- **New UI states for the harness:** the tentative "+N" and the confirm modal are NOT among the UI
  gate's known states, so `ui_gate` stops on them (fail closed). The harness must close them only by
  known steps: RESET (초기화) for a tentative raise, Cancel for the modal, then the window's chord.
  ➡️ **"stops on them" does not hold** (the gate's own readers on the banked look3 / look4 frames,
  2026-10-09 ~21:10; see "AS BUILT" below): the gate does not see either state. It sees the skill
  window's anchor and would close the window by its chord. The harness's own `close_known` runs
  before every typed line instead.
- **The same design for status points (char.allocate_stat):** the GM has 48 unspent points; a
  reversible restore needs `@streset` (pinned `@baselevelup` lowering resets the stats only when the
  unspent points are fewer than the level's, which 48 never is). Same parked decision.
- **The status window, looked at (20:52, Alt+A, no click):** each of the six stats shows its value,
  a raise arrow and the cost of the next point (2 at value 1, the pre-renewal cost), and "Status
  Point 48". There is NO apply button: a click on an arrow is expected to send the raise at once
  (CZ_STATUS_CHANGE), so allocate_stat@1 has no tentative state, and every click is irreversible
  without `@streset`. NOT clicked: a positive case would change the GM's stats for good.

**➡️ AS BUILT, OFFLINE (2026-10-09 ~21:00-21:30 ICT, branch `feat/learn-skill1`, code 86ede5c;
NOT pre-registered, NOT run live; no input was sent while building it):**
- **What exists:**
  - `scripts/learn_skill1.py`: the readers, the rule, `close_known`, the harness, and the `cut` /
    `prove` tools.
  - `scripts/learn_skill1_score.py`: the offline judge.
  - `services/backend/tests/test_learn_skill1.py`: 15 tests on synthetic frames and packets (and
    the harness's trial sequence through a fake client: nothing is typed while a skill-window state is
    up; a stale digit is synced once).
  - The L2 binding `skill_tree` in `l2/kro-20211103-prere.yaml`: numbers only, status unverified,
    measured on RDP.
  - The click census entry: one direct click, `LiveIo.ui_click`, refused outside the box it names.
- **The geometry** is the L2 binding: window-relative to the `skills` anchor's located origin (within
  `HOME_PX` of its home, as `ui_gate` looks), except the modal, which the client centres on its area.
  Without the binding, nothing runs (`Unbound`).
- **The readers** (pure; each fails closed with a reason):
  - window: the `skills` anchor at its home;
  - tentative: red ink right of the icon and nothing else; its digest changes with N, so a raise the
    client ignored is caught;
  - modal: its OWN pixels against its template and against a no-modal reference;
  - points: the label by template, then the number in the WEIGHT READOUT'S glyphs, unchanged (the same
    bitmap font: score 0.01 on look1's "9"). Coloured ink means a pending raise ("tentative"); an
    unexplained mark, a '/', a low margin or a leading zero is None;
  - level: ink in the box under the icon. Only "1" is ever named (the one digit seen live); any other
    ink is "unseen", never guessed.
- **Templates:** `learn_skill1.py cut` writes them to `data/ui_anchors/learn_skill/` (local, never
  committed):
  - the modal from look4, the no-modal reference from look3-click1-away;
  - the points label from look1, the level "1" from look5.
- **`learn_skill1.py prove`: 10 / 10 banked frames read as expected.** This is a reproducibility check:
  four of the frames gave the templates. What is held out: the "1" on look6, the label on seven
  frames, and the modal's negative on six. The cursor rows are explained below the table.

  | frame | window | tentative | modal (own px: modal / none) | points | level ink, glyph |
  |---|---|---|---|---|---|
  | look1-after-joblevelup | no | – | – | – | – |
  | look1-skillwin | yes | no | no (0.16 / 1.00) | **9** | none |
  | look2-hover, look2-hover-2s (cursor on the icon) | yes | no | no (0.16 / 1.00) | **9** | not judged |
  | look3-click1 (cursor on the icon) | yes | **yes** | no (0.16 / 1.00) | None (tentative) | not judged |
  | look3-click1-away | yes | **yes** | no (0.16 / 1.00) | None (tentative) | none |
  | look4-applied | yes | **yes** | **yes (1.00 / 0.16)** | None (tentative) | none |
  | look5-confirmed | yes | no | no | **8** | **yes, "1"** |
  | look6-skillwin-after-reset | yes | no | no | **0** | **yes, "1" (the stale one)** |
  | look6-end | no | – | – | – | – |

  - On the cursor-on-icon frames the cursor sprite covers the level box: it reads "unseen" ink there.
  - The live rule therefore parks the cursor (two motions, `ui_gate`'s rest points) before every look.
- **The rule, `learn_skill(io, geo, keys, n)`**, one trial: the window by its chord; the points P on two
  fresh frames, which must be 9; N icon clicks, paced 0.35 s, each followed by a NEW tentative; APPLY;
  the modal within 2 s; OK; the points P - N within 3 s; close by the chord. Every refusal is a recorded
  decline with its reason.
- **`close_known`** handles what a trial leaves open, by KNOWN steps only: CANCEL for the modal, then
  RESET for a tentative raise, then the chord. Any unreadable state STOPS, with nothing pressed.
- **The UI gate is blind to the tentative and the modal.** Its `decide` on the banked look3 and look4
  frames says `chord skills`, not stop: the skill window's title anchor is unaffected by either state.
  So `close_known` runs before EVERY typed line of the harness, and the gate never meets these states
  from this harness. Another harness's gate would still press Alt+S on them, an effect never measured.
  Extending the gate is a separate change, not made here.
- **The harness, `learn_skill1.py run --n N --seed S --restore skreset|charselect`.** Per trial:
  1. `close_known`;
  2. `gm_state.ensure_fixed`;
  3. the START STATE: the window open, the points 0, the level box EMPTY. A stale digit runs the
     restore's sync once, else the trial stops;
  4. `@joblevelup 9`, then `gm_state.clear_notices`;
  5. the rule, with N from shuffled blocks of 1..9 (seeded);
  6. `close_known` if the rule declined;
  7. the restore, then `ensure_fixed` again.

  A DemoRecord is written per rule trial and per harness action, plus `trials.json`, the packets at
  the end, and snapshots before and after each trial. Two consecutive harness stops end the run.
  - `skreset`: `@skreset`, then `@joblevelup -49`. **Refused unless `--skreset-allowed`**: `@skreset`
    is not in group 20, and that is Batt's call. `groups.yml` is untouched.
  - `charselect`: `@joblevelup -49`, then character select and back in. **Refused ("unmeasured: the
    in-game route to character select")** until an L2 `game_option.char_select: {box: [...]}` exists.
- **The scorer, `learn_skill1_score.py SESSION`**, judges inside the rule's own window (`t_rule_start`
  .. `t_rule_end`). The checks:
  - exactly N `skill_up_request` for skill 1, and none for any other skill;
  - the last `skill_update` for skill 1 at level N, and none for other skills;
  - the last `skill_point` after the first request equal to 9 - N;
  - no `attack_request` and no `npc_contact`;
  - no request outside the rule's window inside the trial.

  A start other than 9 makes the trial INVALID (a harness problem, not the rule's), and so does a stop
  before the rule. "Success" needs the server AND the rule's runtime claim. The output gives totals,
  the result per N, and false positives.
- **The positive case on REAL packets:** pk + pk5, with the window from pk5's first event, run as
  `learn_skill1_score.py --packets pk/packets.jsonl.gz pk5/packets.jsonl.gz --n 1 --t0 <pk5's first
  t>`. The result is **server_ok**:
  - start points 9, taken from pk's `@joblevelup 9`;
  - 1 request for skill 1, `skill_update` level 1, `skill_point` 8, `skill_list` level 1;
  - nothing unsafe.

  With `--n 2` the same packets FAIL on all three counts.
- **Still UNMEASURED live** (each needed before the pre-registration, or named in it):
  1. RESET and the modal's CANCEL have never been clicked. `close_known` relies on them: CANCEL is
     expected to close the modal and keep the raise, RESET to drop it. Nothing should be sent.
  2. N > 1:
     - the tentative's +2..+9 have never been seen; the rule only requires its red digest to change;
     - one OK is expected to send N `skill_up_request`s, since 0x0112 carries only a skill id.
  3. Level digits 2-9 have never been seen: they read "unseen". The runtime outcome is the points line.
  4. `@skreset`: group 20 (Batt). Also unmeasured: that it resends the list at Job Lv 1 with nothing
     learned (the START-STATE sync).
  5. `charselect`, all of it:
     - a banked frame of the game option window (Escape);
     - its character-select button's box;
     - the `char_select` signature after the click;
     - `ro_agent.enter_game` back in;
     - the skill window's level box EMPTY after re-entry (the list at `connect_new`).
  6. The Alt+S chord's effect while a raise or the modal is up: never measured, and never relied on.
  7. S2: nothing is measured there. All the templates are RDP-cut.
- **Commands:**

      python3 scripts/learn_skill1.py cut                 # once: the templates from the banked looks
      python3 scripts/learn_skill1.py prove               # exit 1 on any mismatch
      python3 scripts/learn_skill1.py run --n N --seed S --restore skreset --skreset-allowed
      python3 scripts/learn_skill1_score.py /dev/shm/poring-lab-demo/<session>

**➡️ UNMEASURED ITEMS 1-2 MEASURED LIVE (2026-10-10 03:30-03:37 ICT, RDP, the GM; never scored; frames
and packets local in `/dev/shm/poring-lab-tmp/learn_skill/look7*`, `look8*`):**
- **A UI click needs the two-motion approach.** look7 clicked the icon with a cold jump (no prior
  motion): 3 and then 9 clicks did NOTHING (no "+N", "Skill Points : 9" unchanged). look8 repeated it
  with the harness's own approach (`LiveIo.ui_click`: 3 px off, then the point, 0.15 s): every click
  counted. (The 2026-10-09 look3 click worked because the cursor already rested on the icon.)
- **Tentative +N:** +3 shows a red "+3" and "Skill Points : 6(3) / 9"; +9 shows "+9", "0(9) / 9" and
  the icon greys out (no point left).
- **RESET** clears any tentative raise (back to "9"); **APPLY** opens the confirm modal even with
  nothing tentative (look7); the modal's **CANCEL** closes it and KEEPS the tentative raise; a second
  RESET clears it. **No skill packet was sent at any step** of either look (no `skill_up_request`).
- Restored: `@joblevelup -49` with no skill learned (no reset needed: the client stays in sync);
  the fixed state checked at the end of both looks.

**➡️ RESTORE OPTION B MEASURED AND PROVEN (2026-10-10 03:33-03:46 ICT, RDP, the GM):** the in-game route
to character select. Escape opens the GAME OPTION window (the `game_option` anchor at its home (505,450);
with the chat input open, the FIRST Escape only closes the input, so the route presses it once more);
its first button (L2 `game_option.char_select`, box (30, 18, 220, 20) from the window's origin; the
bottom button is ui_anchors' `game_option_close`) goes to character select; `ro_agent.enter_game`
comes back. **Proof: 5 / 5 round trips** (`/dev/shm/poring-lab-tmp/learn_skill/cs_proof.py`), each
11.7-14.4 s, the char_select signature within 7.5-8.9 s, the interlock green after every one (e54b9d6).
The re-entry also clears the job-level notices that gm_state's references do not cover (an "N" badge on
the skills shortcut button and an "up" icon at the client's bottom-left, seen after `@joblevelup`).

**➡️ PRE-REGISTERED 2026-10-10 ~03:50 ICT / 20:50 UTC at commit (BEFORE the scored run), from the draft
below, with these settings fixed:** the restore is **B, `--restore charselect`** (no change to group 20
needed; Batt's option A, `@skreset`, stays open and would need its own amendment); the harness and
scorer at e54b9d6 + this commit; **the pilot is DONE**: `20261010T033852-demo-learn-skill1-pilot-charselect`
(`--n 3 --seed 20261180`, never scored): N = 9, 7, 2, all three `server: ok` with the runtime reads
agreeing (one APPLY sends N `skill_up_request`); RESET / CANCEL / +N were measured earlier the same
night (look7 / look8). **The scored run:** `learn_skill1.py run --n 50 --seed 20261181 --restore
charselect --label learn-skill1-alone`, the GM on RDP where it stands (prontera, no monsters), scored
by `learn_skill1_score.py SESSION` once.

**➡️ RESULT OF THE FIRST SCORED RUN (2026-10-10 03:43-03:45 ICT): INCOMPLETE -- a HARNESS fault, not the
rule.** Session `20261010T034329-demo-learn-skill1-alone-charselect`: trial 0 (N = 2) **success** (server
ok: 2 requests, level 2, points 7; the runtime read agrees); then the restore's route reached character
select, and `enter_game`'s Enter was REFUSED by the mux (`environment_unattested`). Trial 1 stopped the
same way before its rule; two harness stops in a row ended the run, as pre-registered. Scored: 1 valid,
1 success, 1 invalid, 0 unsafe, 0 false positives.
- **The cause:** `ro_agent.ensure_window` skips the login window while /health still reports GREEN, and
  /health's interlock view ticks at 1 Hz; right after character select it still said green, so no
  window opened, and the Enter came after the interlock had turned red. The 5 / 5 route proof had
  waited long enough by chance.
- **The fix (committed BEFORE the re-run, below):** the route waits for the interlock to leave green at
  character select (<= 15 s) before `enter_game`, and for green again (<= 30 s) before any further
  input (`learn_skill1.wait_interlock`, tested). The GM was put back in by hand (`ro_agent enter-game
  gm`, 03:46:58; green).
- **➡️ AMENDMENT (pre-registered at this commit, BEFORE the re-run):** a pilot of the fix, never scored
  (`--n 2 --seed 20261183`), then the scored run ONCE more with a FRESH seed: `learn_skill1.py run --n
  50 --seed 20261182 --restore charselect --label learn-skill1-alone`, everything else as above. The
  first run's numbers stay recorded here.

**➡️ RESULT, THE SCORED RE-RUN (2026-10-10 03:50-04:4x ICT; scored once by `learn_skill1_score.py`):
PASS -- 50 / 50.** Session `20261010T035032-demo-learn-skill1-alone-charselect` (`--n 50 --seed
20261182 --restore charselect`, harness at 492d7b3), complete, no harness stop.
- **50 valid, 50 successes** (every N from 1 to 9: 6/5/6/6/6/6/5/5/5 trials): each trial's server
  evidence (exactly N `skill_up_request` for skill 1 in the rule's window, the last `skill_update` at
  level N, `skill_point` 9 - N, the skill list at N, no other skill) and the rule's runtime read
  (points 9 - N on two fresh frames) agree.
- **0 false positives, 0 unsafe events** (attack / contact / pickup requests, GM acts), 0 requests
  outside the rule's window.
- The bar (>= 48 / 50, 0 false positives, 0 unsafe) is MET. `char.learn_skill` records the RDP pass in
  `verified_on`; it stays `unverified` until an S2 alone-test passes too (the plan's rule).
- The pilot (`20261010T034752`, n = 2) and the first, INCOMPLETE run stay recorded above.

**DRAFT pre-registration for learn_skill@1 (2026-10-10 ~01:15 ICT; superseded by the PRE-REGISTERED
settings above):**
- **The rule and harness:** `scripts/learn_skill1.py` at the commit of the pre-registration; scored
  by `scripts/learn_skill1_score.py SESSION` at the same commit.
- **The restore (one of, Batt's choice):** (A) `--restore skreset --skreset-allowed`, after
  `@skreset` is added to group 20 (lab only; groups.yml change by Batt); (B) `--restore charselect`,
  after the in-game route to character select is measured live (an L2 binding:
  `game_option.char_select`) and proven on 5 round trips.
- **Before the scored run:** the unmeasured live steps (3.34 "STILL UNMEASURED") are measured in a
  pilot, never scored: RESET and the modal's CANCEL each clicked once (expected: nothing sent), a
  tentative +2 and +9 seen, one APPLY of N = 3 (expected: 3 `skill_up_request`); the pilot is
  `run --n 3 --seed 20261180`.
- **n = 50, seed 20261181** (N drawn from shuffled blocks of 1..9), RDP, the GM, a town spot with
  no monsters (prt_church 100,73).
- **Success per trial** (the scorer): the server's evidence -- exactly N `skill_up_request` for skill
  1 inside the rule's window, the last `skill_update` for skill 1 at level N, `stat_change`
  skill_point = 9 - N, no other skill changed -- AND the rule's own runtime claim (points read 9 - N
  on two fresh frames) agree. A disagreement counts as a false positive or a miss.
- **Bar:** >= 48 / 50 successes (>= 0.95) with 0 false positives (a runtime claim of success the
  server contradicts), 0 unsafe events (attack / contact / pickup requests, GM acts), and no stop
  of the UI gate on an unknown state left behind. A harness stop (restore or sync failure) is
  INVALID for that trial, counted, and two in a row end the run.

### HUD scene: box drift while walking + doubled boxes — OFFLINE SIM RESULT (2026-10-08 night; branch `feat/hud-drift`, merged 0d6cd79, DEPLOYED 2026-10-09 00:36 ICT; LIVE RE-MEASURE below)

#### 2026-10-09 — SEEN TWICE + the display-only RECONNECT: BUILT on `feat/hud-seen-twice` (merged 9687631), measured offline; ➡️ the plain rule SUPERSEDED by the CONFIRMING PASS (first sub-entry)

##### ➡️ THE CONFIRMING PASS (Batt 2026-10-09 ~09:20) SUPERSEDES the plain rule below. BUILT on `feat/hud-confirm-pass`, NOT deployed yet

**Batt:** "HUD: use the CONFIRMING PASS (re-check a candidate ~1 s after first seen: 37 -> 1 false boxes,
first box 1.3 s, +0.02 cores) instead of plain seen-twice (6.2 s first box is too slow). My earlier 'no
cadence change' didn't anticipate this; approved."

**What runs** (`hud_scene.Tuning.confirm_s = 1.0`, `hud_scene.py --confirm-s 1.0`; `0` = the plain rule;
`--seen-twice off` = draw at once):
- A pass that makes a new candidate asks for ONE extra detector pass, 1 s after that pass started
  (`Cadence.held`).
- Any pass that runs first serves it. If a regular pass comes sooner, the confirming pass is
  cancelled; while the scene moves, the regular passes already run back to back, so it never runs
  there.
- At most one confirming pass is ever asked for.
- It never moves the regular cadence: only a regular pass sets `last_run` / `last_gray`. The regular
  passes stay at 0 / 5 / 10 s on a still scene (tested).
- The candidate is drawn when the confirming pass, or any regular pass within its window of 2 passes,
  matches it. Otherwise it is dropped, never drawn.
- **The port is tighter than the parked sim variant**, which forced a pass every 1 s while ANY
  candidate waited and reset the cadence. The numbers below are re-measured with the live code (the
  sim drives `hud_scene.Cadence` itself).
- The 60-s report counts confirming passes. The sim's `confirm1` is `hud_scene.TUNING`.

**Results, the 7 walks pooled** (5 seeds, the same instrument as below; median / p95 / max px for
offsets):

| | before (drift fix, live) | plain seen twice (merged 9687631, never deployed) | **the confirming pass** |
|---|---|---|---|
| FP drawn: objects / box-frames | 37 / 286 | 13 / 75 | **1 / 6** |
| ghost box-frames: NPC / monster / sign | 2,907 / 122 / 465 | 2,479 / 0 / 465 | **2,771 / 0 / 462** |
| new units' first box, median / p95: s (frames) | 0.83 / 1.47 (8 / 15) | 1.30 / 6.60 (13 / 66) | **1.30 / 2.57 (13 / 26)** |
| new units never drawn (of 310) | 3 | 8 | **5** |
| real units' frames with a box | 97.2 % | 93.4 % | **95.3 %** |
| NPC walking | 2.6 / 10.7 / 111.3 | 2.7 / 10.7 / 66.0 | **2.7 / 10.7 / 111.2** |
| NPC standing | 0.4 / 2.0 / 117.8 | 0.4 / 1.9 / 117.8 | **0.4 / 1.9 / 117.8** |
| sign walking / standing | 5.2 / 12.1 / 47.5 · 0.0 / 6.4 / 22.2 | the same | 5.2 / 12.0 / 48.5 · 0.0 / 6.4 / 22.2 |
| doubled boxes | 0 | 0 | 0 |
| detector passes: regular + confirming | 2,316 | 2,316 | **2,307 + 69** (+3 %) |
| detector cores, moving / still | 2.14 / 0.48 | 2.14 / 0.48 | **2.14 / 0.50** |
| messages per minute while moving | 812 | 809 | 809 |

**The 06:55 live walk** (5 seeds):

| | before | plain | **confirming pass** |
|---|---|---|---|
| new units' first box, median / p95: s (frames) | 1.19 / 5.53 (12 / 55) | 6.22 / 6.82 (62 / 68) | **2.21 / 6.02 (22 / 60)** |
| real units' frames with a box | 94.9 % | 84.3 % | **91.8 %** |
| FP drawn: objects / box-frames | 2 / 12 | 0 / 0 | **0 / 0** |
| NPC walking / standing | 2.7 / 9.0 / 38.2 · 0.4 / 2.2 / 8.6 | 2.6 / 9.1 / 38.2 · 0.5 / 2.4 / 8.5 | **2.6 / 9.2 / 36.8 · 0.5 / 2.4 / 8.6** |
| detector cores, moving / still | 2.15 / 0.47 | 2.15 / 0.47 | **2.21 / 0.49** |
| passes: regular + confirming | 415 | 415 | **415 + 15** |

- **Idle (20:07):** 0.5 deltas/min, unchanged. 0.26 detector cores (0.25 before): one confirming pass
  at the start. Real with a box is back to 100 % (plain: 96.8 %).
- **The trade:** it hides ~6.5 real box-frames for each false one it removes (1,821 vs 280, 5 seeds).
  The plain rule hid ~18.
- **The first-box p95 on the 06:55 walk stays ~6 s** (5.5 s before any rule). A unit that appears on a
  still scene still waits up to the 5-s idle pass for its FIRST sighting; the confirming pass only
  shortens the second.
- **Measured, not adopted:**
  - a window of 1 pass with the confirming pass: the same results (FP 1 / 6, 95.3 %, never 5);
  - `confirm_s` 0.7 s: the first box 1.30 / 2.27 s (06:55 median 1.91 s), the same FP and cost.
  Batt approved ~1 s.
- The 20:09 low-confidence monster is still not drawn by the port (the parked sim variant drew it:
  its passes fell differently).

##### The plain seen-twice rule and the reconnect (2026-10-09 morning; ➡️ the rule's numbers below are HISTORY: the confirming pass above superseded them)

**Batt (2026-10-09):** "HUD: rejection of ask 3 confirmed; add the seen-twice rule; no faster loop for
now." and "Add the display-only reconnect for the HUD process."

**Seen twice** (`hud_scene.Tuning.seen_twice` / `seen_window`; `hud_scene.py --seen-twice units|off`):
- A NEW unit (no drawn object took its detection) is a CANDIDATE. It is never drawn and never in a
  message: candidates have negative ids and are not in keyframes.
- It is drawn when one of the next 2 detector PASSES matches it, by the same one-to-one matching and
  dedupe rules as drawn objects (feet within 40 px on the detected frame first, then 120 px or IoU
  0.1), where its floor point projects now. Never matched again: dropped silently.
- Drawn objects take their detections first, so they behave exactly as before. A test runs the same
  passes with the rule on and off: once both have drawn the units, every message is identical.
- **The window is 2 passes, not seconds.** The cadence runs a pass every ~0.6 s while moving and every
  5 s when still. A time window would either never confirm a unit first seen on a still scene, or wait
  seconds while walking. With 2 passes, one detector miss does not reset a candidate. 3 passes measured
  the same as 2; 1 pass lost 2 more real units (10 never drawn vs 8).
- **Signs are EXEMPT** (drawn at once):
  - The shape finder has no measured false signs: 0 of 146 out-of-view route starts, 0 on 1,186 idle
    frames (above).
  - In the sim, before the rule, no sign object was drawn without a real sign.
  - The rule on signs (`seen2-signs`) removed 606 correct sign box-frames for 32 ghost ones (5 seeds
    pooled).
- The wire messages and the detector cadence are unchanged.

**The instrument** (`hud_scene_check.py simtable --seeds 5`; new columns from
`hud_scene_sim.truth_tracks`):
- **Truth tracks:** each cached detection is linked over the recorded frames: within 30 px of its
  track's predicted feet (the scene's scroll applied), across up to 5 missed frames.
  - A REAL unit is detected on at least 10 frames (~1 s).
  - Shorter tracks cut by the recording's ends are not judged.
- **FP drawn:** drawn objects never paired with a REAL unit in their whole life, and their box-frames.
- **Ghosts** (as before): box-frames with no detection of their class within 120 px. This also counts a
  real unit the detector missed on that frame.
- **New units:** REAL units that appear at least 2 s into a recording, from their first detection to
  their first box.
- **Real with a box:** the REAL units' detection-frames that a drawn box was paired with.
- Live latencies, 5 seeds; "before" is the deployed drift fix (`chosen`).

**Results, the 7 walks pooled** (5 seeds; median / p95 / max px for offsets). ➡️ HISTORY: the plain
rule, never deployed; the confirming pass above superseded it. The PARKED column is the sim-only
variant, since ported with tighter semantics and re-measured above.

| | before (drift fix, live) | **after: seen twice** (`seen2`) | PARKED: + a confirming pass 1 s after a candidate (`seen2+confirm1`, sim only) |
|---|---|---|---|
| FP drawn: objects / box-frames | 37 / 286 | **13 / 75** | 1 / 6 |
| ghost box-frames: NPC / monster / sign | 2,907 / 122 / 465 | **2,479 / 0 / 465** | 2,818 / 13 / 462 |
| new units' first box, median / p95: s (frames) | 0.83 / 1.47 (8 / 15) | **1.30 / 6.60 (13 / 66)** | 1.30 / 2.72 (13 / 27) |
| new units never drawn (of 310) | 3 | **8** | 4 |
| real units' frames with a box | 97.2 % | **93.4 %** | 95.2 % |
| NPC walking | 2.6 / 10.7 / 111.3 | 2.7 / 10.7 / 66.0 | 2.7 / 10.7 / 111.2 |
| NPC standing | 0.4 / 2.0 / 117.8 | 0.4 / 1.9 / 117.8 | 0.4 / 1.9 / 117.8 |
| sign walking / standing | 5.2 / 12.1 / 47.5 · 0.0 / 6.4 / 22.2 | the same | the same |
| doubled boxes | 0 | 0 | 0 |
| messages per minute while moving | 812 | 809 | 808 |
| detector cores, moving / still | 2.14 / 0.48 | 2.14 / 0.48 | 2.14 / 0.50 |

**The 06:55 live walk** (route_demo: each route warps, stands, then walks; 5 seeds):

| | before | **after** | parked confirm1 |
|---|---|---|---|
| new units' first box, median / p95: s (frames) | 1.19 / 5.53 (12 / 55) | **6.22 / 6.82 (62 / 68)** | 1.77 / 6.02 (18 / 60) |
| real units' frames with a box | 94.9 % | **84.3 %** | 92.0 % |
| FP drawn: objects / box-frames | 2 / 12 | 0 / 0 | 0 / 0 |
| NPC walking / standing | 2.7 / 9.0 / 38.2 · 0.4 / 2.2 / 8.6 | 2.6 / 9.1 / 38.2 · 0.5 / 2.4 / 8.5 | — |

- **Idle (20:07):** 0.5 deltas/min and 0.25 detector cores, unchanged. Its 2 NPCs, there from the
  start, are drawn one idle pass later (real with a box 100 → 96.8 %).

**What it means:**
- **The rule does what it says.** Drawn false positives fall by 65 % (objects) and 74 % (box-frames).
  The NPC walking max falls 111 → 66 px; the standing max stays 117.8 px.
- The 20:09 walk's monster is no longer drawn at all: 21 detections at confidence 0.26–0.71, never on
  two passes in a row. Whether it is a real monster is not established (prt_church has no spawns).
- **The cost: one detector pass on every new unit.** When a unit first shows on a STILL scene, the
  next pass is the 5-s idle one. On the 06:55 walk (warps, then still), the median first box goes from
  1.2 s to 6.2 s.
- **On these prt_church recordings the detector's flashes are rare:** 3 tracks of at most 2 frames in
  7 walks. The rule hides ~18 real box-frames for each false one it removes (3,720 vs 211, 5 seeds).
- **PARKED for Batt** (a cadence change, which he ruled out for now): a pass due 1 s after a
  candidate is seen, only while one waits. It keeps the FP cut (37 → 1 objects) at +0.02 cores when
  still, with the first box at 1.3 / 2.7 s. It is in the sim only (`Variant.confirm_s`), not in
  `hud_scene.py`. ➡️ **Batt 2026-10-09 ~09:20: APPROVED.** Ported into `hud_scene.py` as the
  confirming pass, with tighter semantics and re-measured: see "THE CONFIRMING PASS" at the top of
  this entry.
- Monsters: still not measured (the 20:09 one is the only one).

**Display-only reconnect** (`hud_scene.Sender`):
- **Dead** means any of:
  - a send error;
  - the connection's closed state, checked before every send and on a 0.5-s idle tick;
  - a missed WebSocket protocol ping: every 5 s, 5 s timeout. The server's library answers pings; no
    message type of ours is involved.
- **No blocked send:** the Sender opens its own socket with TCP_USER_TIMEOUT 10 s. A send into a black
  hole (the old address gone) then fails in 10 s. Before, it could block the sender thread for TCP's
  ~15 min, and a ping could not help: the library sends while holding the connection's lock.
- **Reconnect:** backoff 1 s, doubling to 30 s, forever. One log line when the channel goes DOWN, one
  when it is UP again (with the attempts and the messages dropped meanwhile).
- **Every connection starts with a KEYFRAME.** It is made under the tracker's lock, so nothing queued
  before it is sent after it, and a console never sees a stale seq. The messages it replaces are
  counted as `superseded`.
- **While down:** messages are dropped and counted (`dropped`), so the queue never grows. The capture
  and detector threads only ever `put()`.
- **The 60-s report line** adds the display state, sent / dropped / superseded / connects, and the
  candidates (held / confirmed / expired).
- **The scene log** keeps every message. Undelivered ones are tagged `link: dropped|superseded`, and
  `hud_scene_check.load_log` skips them, so a replay is what a console received.
- The websockets 17.1 legacy-connect DeprecationWarning is gone (`legacy=True`, the library's own
  direct-connect form).
- **Tests** (`services/backend/tests/test_hud_scene_sender.py`; 20 repeated runs green):
  - a fake link killed, then refused twice: attempts at +1 s and +3 s; on the new link, a keyframe
    first with the tracker's seq; the delta queued before it superseded; a console replay current;
    one DOWN and one UP line; the drops counted and tagged;
  - the backoff ladder 1, 2, 4, 8, 16, 30, 30 s, with one log line;
  - a real websockets server on loopback, shut down and restarted on the same port: pings (5 s) and
    TCP_USER_TIMEOUT (10,000 ms) are on the socket, messages drop while down, and the new server's
    first message is a keyframe.
- **The 06:59 incident, re-read from `hud_scene.log`:** a NEW connection WAS made at ~06:59, and `sent`
  kept rising at the keyframe rate.
  - The evidence: the DeprecationWarning above fires once per connection, on its first send, and it
    printed again. There is no "display channel down" line.
  - So the old code did re-dial once. Why the console showed no scene until the 07:04 restart is NOT
    established. The frontend-dev restart at 07:01 also reset the console's toggles.
  - The new Sender covers what the old one could miss: a silent dead link (pings), a blocked send
    (TCP_USER_TIMEOUT), and the seq gap after a reconnect (keyframe first; the old code waited for the
    next 5-s keyframe).

**Deploy:** a display-only restart of `hud_scene.py`, by default `--seen-twice units`;
`--seen-twice off` restores drawing at once. No protocol, frontend or backend change.
➡️ Merged 9687631 but NOT deployed as such: the confirming pass (top of this entry) goes out with it.

**LIVE RE-MEASURE after the deploy** (2026-10-09 06:55 ICT, a 3-route indoor `route_demo` walk, seed 34,
frames `route-demo/20261009T065545`; `hud_scene_check.py truth` + `rescore` against the live scene log).
It is the same scorer as the "before" row: the 20:09 walk, re-scored by the subagent. Values are
median / p95 / max px.

| NPC boxes | before (20:09, first cut, live) | after (06:55, new code, live) | the sim predicted |
|---|---|---|---|
| walking, on the HUD's own frames | 10.0 / 33.7 / 42.1 | **5.6 / 16.7 / 24.9** (n 80) | 2.6–2.7 / 10.5–11.2 |
| walking, between them | 9.5 / 41.6 / 63.8 | **4.2 / 15.0 / 44.7** (n 245) | — |
| standing | 0.4 / 7.3 / 63.7 | **0.6 / 2.0 / 12.6** (n 2813) | 0.4–0.5 / 2.0–2.1 |
| doubled box-frames | 30 | **0** | 0 |

- **Signs:** standing 1.0 / 10.3 (n 122); walking 7.0 / 21.8 (n 13).
- **Messages while moving:** 784 per minute (13 / s), as the sim said.
- **Live is better than before, and worse than the sim** on the walking p95 (16.7 vs ~11). One walk:
  the cause of the gap is not measured.


**Why** (Batt, 2026-10-08 evening, from the 20:09 walk):
- NPC boxes walking: 9.9 / 33.3 / 42.1 px (median / p95 / max, n 83); standing 0.4 / 14.1 / 63.8.
- Doubled boxes: a drifted box stayed while re-detection added a second one.
- His ask: raise the detector rate while the scene moves (niced, CPU measured); dedupe by id / IoU
  on re-detection; use the route preview's camera estimate when a rule runs; report the offsets
  walking and standing, before and after.

**The instrument** (`scripts/hud_scene_sim.py`; `hud_scene_check.py truth | rescore | sim |
simtable`):
- The detector (2 threads, niced) and the signboard finder were run once on every recorded frame of
  7 route-demo walks (all prt_church) and the 20:07 idle recording. The motion features were cached
  too, all in RAM (`/dev/shm/poring-lab-tmp/hud-sim`, client-derived, never committed).
- The sim runs `hud_scene.py`'s OWN tracker over the frames at their recorded times:
  - the detector thread's cadence, with each pass taking the live 590 ms;
  - the live frame → message latencies, sampled from the live log;
  - the same message stream.
  - It is scored like `offsets`: each drawn box against that frame's detections, nearest foot of its
    class within 120 px.
- Walking = the frame's OWN scroll since the previous recorded frame is at least 1 px.
  - The first cut's `offsets` asked instead "did the process send a motion for this exact frame".
    That filed every walking frame between the process's own frames (about 3 in 4) as STANDING:
    83 walking samples of ~290. `offsets` is fixed the same way.
- **Fidelity, the 20:09 walk:**
  - Live, rescored: walking 10.0 / 33.7 / 42.1 on the frames the process saw, 9.5 / 41.6 / 63.8
    between them; standing 0.4 / 7.3 / 63.7; 30 doubled box-frames.
  - The first cut's code in the sim, over 6 latency seeds: walking 8.9–9.8 / 38–76 / 85–101;
    10–87 doubled box-frames.
  - The first cut is timing-sensitive and bimodal: does a drift cross the 40 px match gate before the
    next detection? The live run sits inside the sim's spread.

**Three causes, each measured:**
1. **Perspective:** one 2-D shift cannot fit near and far rows. The camera model scrolls the floor
   19.6 px per cell at y 100 and 29.4 at y 650 (±20 % around the centre).
   - Floor patches against one shift: 1.3–1.7 px off per 0.1 s frame at the top and bottom rows.
   - Against the perspective fit: 0.5 px.
   - Yaw and distance do not change the screen flow, only pitch, FOV and the centre. So the fitted
     camera serves indoor maps too, with no map knowledge (tested).
2. **The scroll read ~0 on 7–15 % of moving frames:** the NPCs moved 10–15 px and the phase
   correlation said "still".
   - The live process missed the same motion: no `hud_motion` for 20:09 frames 417–420.
   - The raw (lossless) 12:33 frames do it too (8 / 54), so it is not a JPEG artefact.
   - Cause: a fine screen-fixed pattern wins the whitened peak. Full resolution doubled the misses;
     static noise reproduces it in a test.
   - Band-passing the correlation fixes it: 3×3 blur, minus a 9×9 box mean, |R|^0.5.
     - Read-as-zero: 11–17 → 0–2 per walk.
     - Scroll error p95 against the NPCs' own motion, on 4 walks: 6.5–8.9 → 4.2–4.8 px (12:33 raw:
       46.9 → 10.7).
     - Still frames are unchanged (p95 0.37).
3. **Detection:** a box drifted past the 40 px gate and re-detection added a second one; the stale
   one stayed for two misses (up to 10 s at the idle cadence).

**What changed in `hud_scene.py`** (display only; no protocol, frontend or previewer change):
- **The floor model:** the camera's move over a flat floor comes from route_preview's floor patches
  against the camera model (`Ground`, the camera's floor homography). Then every world object moves
  by its own projection.
  - The global `HudMotion` still carries the bulk, frame-synced on the console.
  - An object more than 4 px off it gets a `HudDelta.move` in that frame's delta.
- **The band-passed scroll:** `route_preview.scene_shift(..., blur=True, highpass=9, power=0.5)`.
  The previewer's defaults are unchanged.
- **Dedupe:** one-to-one matching on the detected frame, nearest first.
  - A leftover detection within 120 px (or IoU ≥ 0.1) of a leftover object of its class MOVES that
    object instead of adding a second box.
  - One miss removes an object while the scene moves.
- **The detector:** every 0.5 s while the scene moves (at 2 threads that is back to back, ~0.6 s a
  pass), 1 s while the frame changes, 5 s idle.
  - Passes while moving, and the first still pass after, re-seat boxes at 1 px. Idle passes keep the
    4 px hysteresis.
- **Edge-cut boxes:** a unit box cut by the view's edge gets its sprite's size (NPC 34 × 75: the
  median of ~9,000 detections), so its feet are not the screen's edge. (19:10: walking p95 12.4 → 10.3,
  max 36.6 → 14.3.)
- **One ordered send queue:** deltas from both threads reach consoles in `seq` order.

**Results.** All 7 walks pooled (the raw offsets, not an average of medians), live latencies,
5 seeds. Median / p95 / max px, n per seed:

| | NPC walking | NPC standing | sign walking | sign standing | doubled boxes | ghosts |
|---|---|---|---|---|---|---|
| first cut (deployed) | 9.7–9.8 / 51–55 / 87–101, n ~1,940 | 0.6 / 15–21 / 87–98, n ~12,800 | 6.5–6.6 / 49–50 / 70–74, n ~685 | 0.0 / 23–27 / 72 | 307–380 | 1,345–1,578 |
| **new** (`chosen`) | **2.6–2.7 / 10.5–11.2** / 40–111, n ~1,925 | **0.4–0.5 / 2.0–2.1** / 118, n ~12,660 | **5.1–5.3 / 12.0–12.9** / 21–48, n ~668 | 0.0 / 6.2–6.6 / 22 | **0** | 624–722 |

- The max is set by detector FALSE POSITIVES. A one-off NPC box (by the piano, the top edge) stays
  until it is missed twice and is scored against a real NPC ~115 px away. This happens in every
  variant.
- **Monsters: NOT measured.** All 8 recordings hold 21 monster detections (all in the 20:09 walk).
- **Signs:** the finder's pure outline finds none on the 20:09 JPEGs, so the sign numbers come from
  the other 6 walks.
- **Idle (the 20:07 recording):** 0.5 deltas/min (the first add) + keyframes, the same as live and the
  first cut. Idle detector: 0.25 cores, unchanged.

**What each part buys** (ablations, the same 7 walks, a fixed 76 ms frame → message latency; NPC
walking median / p95):

| variant | NPC walking | doubled | ghosts | messages while moving | detector cores while moving |
|---|---|---|---|---|---|
| first cut | 9.7 / 54.9 | 392 | 1,511 | 9.2 motion + 0.7 delta /s | 1.40 |
| + detector 0.5 s only (Batt's ask 1) | 9.0 / 45.7 | 101 | 897 | 9.2 + 1.4 /s | 2.13 |
| + dedupe only (ask 2) | 9.6 / 52.4 | **0** | 1,323 | 9.2 + 0.7 /s | 1.40 |
| + band-passed scroll only | 7.7 / 28.7 | 22 | 1,449 | 9.9 + 0.7 /s | 1.42 |
| + floor model only | 3.9 / 53.6 | 348 | 1,505 | 9.2 + 2.7 /s | 1.40 |
| new, but ONE 2-D shift | 6.6 / 24.9 | 0 | 730 | 9.9 + 1.6 /s | 2.13 |
| new, but the plain scroll | 3.2 / 44.0 | 0 | 707 | 9.2 + 3.3 /s | 2.13 |
| new, but detector 1 s | 2.9 / 10.5 | 0 | 1,087 | 9.9 + 2.9 /s | 1.42 |
| new, but no dedupe | 2.6 / 9.6 | 0 | 914 | 9.9 + 3.4 /s | 2.13 |
| **new** | **2.6 / 9.3** | **0** | **725** | 9.9 + 3.4 /s (5.8 moves/s) | 2.13 |

- The floor model and the band-passed scroll do most of it.
- The faster detector mostly removes stale and ghost boxes sooner (1,087 → 725). It costs +0.7 cores
  while the scene moves, niced; 0 when still.
- **The CPU of the motion path** (10 Hz, niced, tonight's loaded host):
  - band-passed scroll: 26 ms a frame (plain: 20), so +0.07 cores at idle;
  - floor model: +21 ms a frame, only while moving (+0.2 cores).

**Measured and REJECTED:**
- **The route preview's camera as the motion source** (Batt's ask 3; 19:10 / 19:12 / 20:09, the
  current previewer).
  - Frame to frame (20:09), it is off by 4.1 / 21.7 px (median / p95) against the NPCs' own motion.
    The HUD's own floor patches are off by 1.0 / 2.9.
  - In the sim, NPC walking gets far worse: 19.5–28.4 / 69–71 px on the three walks, against
    2.4–3.3 / 7.2–10.3 without it.
  - Why: its Kalman filter pulls the camera towards the engine's walk model (corrections up to 0.7
    cell, ~23 px), and it samples at ~8 Hz on other frames. That is right for an ABSOLUTE route line
    and wrong for the frame-to-frame motion of boxes.
  - So the HUD does not use it, and there is no coupling between the two processes. ⇒ Batt decides.
    ➡️ **Batt 2026-10-09: rejection CONFIRMED.**
- **A console that extrapolates between motions** (a frontend option).
  - Between frames, at a 5 Hz HUD on the 10 Hz recordings: 6.9 / 20.2 → 5.7 / 17.2 on 20:09, but
    5.7 / 24.7 → 6.6 / 27.4 on 19:12.
  - Standing p95 doubled from overshoot at stops: RO's camera stops and starts.
  - No frontend change was made.

**Left, parked:**
- **Frames between the HUD's own frames.** The console draws them with the last motion.
  - At a 5 Hz HUD over 10 Hz frames: 2.5 / 9.1 on the frames it saw, 7.3 / 21.8 between.
  - Live, at 10 Hz against a ~30 fps console, the gap is about half that.
  - The remaining fix is a faster HUD loop while moving (est. +1 core at 30 Hz), not measurable on
    10 Hz recordings. ➡️ **Batt 2026-10-09: no faster loop for now.**
- **Detector false positives** persist up to two idle passes (10 s): the ghosts and the max.
  ➡️ 2026-10-09: the seen-twice rule keeps one-off detections off the screen (the dated entry at the
  top of this section, with its cost).

**Deploy:** a display-only restart of `hud_scene.py`. No protocol regen, no frontend change. The
previewer's behaviour is unchanged: its `scene_shift` defaults are untouched.

### walk@13 — DESIGN PROPOSAL (direction APPROVED by Batt 2026-10-08 ~17:00; PRE-REGISTERED as 3.24 above, 2026-10-08 ~21:50)

**Why** (Batt, 2026-10-08 ~16:00; the direction APPROVED ~17:00): "walk@12: safety is solved; the binding problem is now refusals.
For walk@13, turn refusals into ALTERNATIVES (another click point on the polyline, approach the goal
from another side, a nearby goal cell when the goal is adjacent to an NPC) before declining."

**walk@12's refusals** (the four tuning runs, 3.21 RESULTS: 43 / 40 / 45 / 30, every one with zero
safety events):
- `unit_stays` (2 / 7 / 1 / 13): every point of the next step's cell refused (TALK cells next to the
  start, or monsters inside the unit-gate envelope), patience ran out, the route declined. The
  plan's other corners and other approaches were never tried.
- `no_click_point` (3 / 1 / 1 / 0): the route stopped 1–3 cells short of the goal; the goal's cell
  had no safe point (UI zone, TALK, or an NPC beside it).
- "substituted a goal nobody had taken" (0 / 2 / 3 / 7): the goal's points were refused by the unit
  ENVELOPE (a monster NEAR the goal) and the rule substituted as if the goal were TAKEN; the server
  shows nobody on it.
- `relocalise_limit` (2 / 0 / 0 / 0): the /where budget (not a refusal; kept).
- TALK cells cluster around two indoor NPCs ((109–111, 124–126) and (112–113, 112–114)).
- 4 clicks did not walk, all route-first clicks after > 10 s (idle@1, 3.23).

**The proposal — refusals become alternatives, tried in this order before any decline:**
1. **Another click point on the polyline.** When a step's target cell is refused (covered TALK /
   unit envelope / no safe point), try the other cells of the SAME planned path at the next shorter
   and longer distances (walk@11's farther points, extended to shorter ones), before patience.
2. **Approach from another side: re-plan around the refusal.** The refused cells join a per-route
   BLOCKED set (TALK cells for the whole route: NPCs do not move; unit-envelope cells for 8 s, the
   unit memory's horizon; no-safe-point cells for the route) and the route is re-planned with
   `walk6.plan(w, goal, blocked)`. At most R = 3 re-plans per route, then walk@12's patience /
   substitute / decline.
3. **A nearby goal cell when the goal sits beside an NPC.** If the goal cell, or a cell adjacent to it,
   read TALK during this route, the goal becomes the nearest walkable cell at Chebyshev distance
   1–2 that is not adjacent to a TALK cell and is reachable. SCORED SEPARATELY ("arrived at an
   NPC-adjacent substitute"), never as a plain success; the verifier checks the server's position.
4. **"Taken" means a unit's own cell IS the goal** (its feet picked to a cell), not a unit
   inside the click-point envelope. An envelope refusal at the goal waits (patience) or uses
   1-2 above; only a unit on the goal cell triggers the substitute.
5. **The work zone also excludes SIGNBOARDS** found from pixels, + 6 px, once a deliberate positive
   case proves the hit area (a click 2–3 px under a sign's edge vs 10 px under it).
   - The finder is `poring_env.signboard` (2026-10-08 ~20:40, Batt): a sign is found by its SHAPE.
     It is an outlined icon square with a title bar attached; both have a 1-px black outline and a
     1-px white halo, plus fill and size limits, and an NPC must be detected under it wherever one
     could be seen. It is NEVER found by colour.
   - The first finder (a union of every sign-coloured pixel, `idle_click.sign_box`) was WITHDRAWN.
     It put one giant false "sign" over half the church in 194 of 224 banked walk@12 frames: it
     would have masked half the clickable area and added refusals. walk@12 never used it. Its proof
     is the signboard section below.
6. **The idle first click** (hypothesis, to be tested first): if a deliberate test shows the client
   drops the first world click after > 10 s idle, the rule re-hovers (two motions) before such a
   click; otherwise nothing changes. ➡️ TESTED by idle@1 (3.23): 0 failures in 120, so NOTHING
   changes; walk@13 builds no first-click fix.

**Kept from walk@12:** everything else (the unit gate, the TALK-cell block, the work zone, the
harness exit, the bar ≥ 48/50 + zero safety events, fresh seeds, held-out only if all four pass).

**To pre-register:** the exact candidate order, R, the blocked-set lifetimes, the substitute rule's
distance and scoring, the signboard finder's version (`poring_env.signboard`, frozen at
pre-registration) and the hit-area margin (from its positive case). The idle-click decision is made
(no fix, idle@1).

### Targeting — DESIGN PROPOSALS (Batt, 2026-10-08; NOT pre-registered: each is pre-registered before it is adopted)
**Provenance:** ideas only, from a screen recording of another RO bot's debug view (unknown origin,
server and licence). No code or assets copied.
- **(a) Target lock with a minimum hold time.** Hysteresis: the rule keeps its target for at least
  H s and never switches between EQUAL targets. It switches only to one strictly better by a margin,
  or when the target is gone or unreachable.
  - The test before adoption: count target switches per kill in a crowd (attack@1's scene), with
    the lock against without. Kills, time to kill, and the safety signals are reported.
- **(b) A FOCUS crop.** Around the locked target, a crop (e.g. 260 × 260 client px) is re-detected
  at a higher input resolution, so small or distant sprites are found more reliably.
  - The test before adoption, OFFLINE: on banked frames with packet ground truth, the recall gain
    for small / distant units against the full-frame pass. Byalan's small species are the case
    that matters (docs/planning/training-cost.md). Plus the extra CPU per frame.
- **(c) A WORK ZONE mask shared by clicking and detection:** the game area minus the client's UI
  windows (`route_preview.UI_WINDOWS` + a margin). It is the same rule as walk@12's UI exclusion
  (Batt's decision 1), applied to detections too, so a "unit" seen through a UI window is never a
  target.
  - The test: a deliberate positive case, a unit drawn under a UI window, ignored by both.

### 3.39 hunt@N: SEARCH and ENGAGE like a player, engagement success >= 95 % (pre-registered 2026-10-15 ~22:10 ICT, BEFORE any hunt data; Batt's overnight brief, 2026-10-15 ~21:55: "A bot that FINDS monsters by itself and KILLS them like a player, with ENGAGEMENT SUCCESS > 95 %")

**Fixed here for every version; never changed after any data.** Batt's definitions, as coded in
`hunt_core.judge_engagement`:
- **Engagement:** the runner SELECTS a target and logs `t_select` and the selected cell. It ends
  when the bot judges the target dead (pixels) and has looted, or when it gives up: 60 s, 10
  clicks, or the target lost before any click. Each give-up records its reason.
- **The selected unit G (packets):** the `target_gid` of the first attack request in the
  engagement, if that unit stood within 5 cells of the selected cell then. Else, the mob nearest
  the selected cell at `t_select`, within 2 cells. With none, the engagement FAILS
  (`no_unit_at_selection`).
- **SUCCESS:** G died (`entity_vanish` reason 1) after `t_select`, with at least one attack act of
  ours on G from `t_select` on.
- **EXCLUDED, only with packet evidence:**
  - G changed species (Pupa -> Creamy);
  - G was killed with no act of ours;
  - G vanished another way (reason not 0 or 1) before any hit of ours.
- **Every other outcome is a failure.** Its reason (`never_hit`, `hit_not_killed`, ...) is
  reported, with the bot's own reason.
- **Rate and bar:** success over the counted (non-excluded) engagements, with a Wilson 95 %
  interval. PASS for a version = success >= 95 % over >= 60 counted engagements in ONE run, AND
  zero safety events, CONFIRMED by a second run of the same version with a fresh seed.
- **Safety events (zero tolerance; each stops the run):** an NPC contact, an NPC dialog, a map
  change, a non-target hit (species at hit time), an unknown UI state. Unintended attack requests
  (outside every engagement window + 3 s) are counted and reported.
- **Also reported per run:**
  - time to first target (the loop start -> the first selection);
  - targets found / 10 min (selections);
  - kills / h (packets); seconds per kill; planned path cells per kill;
  - coverage (distinct search-area cells in view);
  - base / job EXP;
  - the time split (searching, stopping, engaging, fighting, looting, checks);
  - walk clicks by gate.
- **Conditions:**
  - prt_fild08, NATURAL spawns (no `@killmonster2` or `@monster`, ever);
  - the GM immune (collect_v2's confirmed record for this login), in its fixed state before and
    after (level reset);
  - the UI gate on every typed line; HUD + route preview ON;
  - 30-40 min, RDP;
  - every run recorded (game-region JPEGs at 5 Hz, the HUD and route-preview logs) for the
    attack-started cue and the morning MP4;
  - each version briefly pre-registered below BEFORE its run.
- **Recorded deviations, known before any data:**
  - (1) prt_fild08's animated region is NOT built: its measurement yields the client tonight
    (Batt). So decision 3's region gate is not applied in these runs.
  - (2) Continuous walking (Batt's point 5): a click while the GM still moves cannot be
    cursor-read (planning/search-targets.md section 6). So it is gated by the map and the detector
    (option B):
      the cell in the search area (stand cells, 6 cells clear of warps and NPCs, 20-cell border);
      the point clear of the UI;
      no detector unit within 40 px on a frame <= 0.35 s old.
    Every click from a standstill stays robust2-cursor-gated.

**3.39.1 hunt@1 (pre-registered with 3.39, before its run).** `scripts/hunt.py --version 1`. What
changes against farm@1 (6.2), and why:
- SEARCH (planning/search-targets.md): it replaces the random wander that cost farm@1 89 % of its
  time.
  - a coverage plan over the search area (16 x 16-cell tiles, staleness, the sightings memory with
    stationary targets kept);
  - A* routes with a waypoint every 8 cells;
  - continuous walking (the next click when <= 3 cells remain by dead reckoning; the minimap
    corrects it);
  - detection all the time, a target in view interrupting the route.
- ENGAGEMENT is PERSISTENT, so a selection either succeeds or ends with a recorded reason.
  - The selected target is followed frame by frame (acquired within 140 px, then 90, widened to
    200 once attacked).
  - The first click: one robust2 SWORD read at the latest box's centre, on a target still for
    0.5 s, or after 8 s its latest fresh box.
  - Re-clicked the same way every 5 s while alive, up to 10 clicks or 60 s.
  - Dead = no box within 200 px of its last feet for 3 frames and 1.5 s after an attack click.
- farm@1's damage cue is dropped (not usable).
- Seed 20261101, 35 min.
- ➡️ **Attempt 1 (`20261015T220633-demo-hunt1`, 22:06:33) ABORTED at 36 s, kept, not scored: a
  bug.**
  - The route's first fixed waypoint (8 cells south-west) projected under the chat window. "Not in
    view" reset the route, and the same route was re-planned ~15 times a second with no click and
    no input. Stopped by SIGINT. The client was judged clean.
  - Fixed, an implementation fix that keeps the design: each click goes to the FARTHEST path cell
    <= 8 ahead whose point is in view and off the UI, from where the GM is (or will be). Three
    refused cursor clicks give the tile up.
  - An offline simulation on the real map, camera and footprint (no engagements): 49k area cells
    covered in 10 min, 83k of 89k in 30 min, nothing stuck.
  - Attempt 2 runs the same version, seed 20261102.
  - ➡️ **Attempt 2 (`20261015T221003-demo-hunt1`, 22:10:03-22:34:39): STOPPED at 24.2 min (our
    cell unknown).**
    - The minimap reader fails at (122,78) with `uncovered_ink`, and /where failed too.
    - **Engagement success 24 / 52 = 46.2 % (Wilson 33.3-59.5 %): FAIL.**
    - The failures, by the packets: no unit at the selected cell 15, never hit 7, hit but not
      killed 6. 24 of the 28 failures never got a click: the bot "lost" the target before hovering.
      For no-unit-at-selection, the nearest mob was 3-20 cells from the selected cell (mostly 4-7).
      The cell had been reckoned while walking and was projected after the stop to where nothing
      stood. Hit-but-not-killed was mostly Pupas (427 HP): the 60 s limit, or a false pixel death.
    - kills 22 (Poring 12, Lunatic 6, Pupa 2, Drops 2) = **54.5 kills / h** (farm@1: 6.0);
      66 s per kill; time to first target 21.5 s; targets 21.5 / 10 min; coverage 23.8k cells;
      EXP 72 / 41.
    - Time split: fighting 446 s, searching 383 s, looting 271 s, engaging 247 s, checks 56 s,
      stopping 52 s. Walk clicks: 69 cursor-gated, 40 map+units.
    - **Safety:** NPC contacts 0, dialogs 0, map changes 0, non-target hits 0, acts onto the GM 0.
      **1 unintended attack request**: 0.8 s after a map+units walk click (1 in 40), on a mob the
      detector frame did not show. A target species; reported.

**3.39.2 hunt@2 (pre-registered 2026-10-15 ~22:50, before its run).** One main change: the top
failure cause, the selection. Small fixes for the others:
- **MAIN, a FRESH SELECTION after the stop.** A monster seen while walking only stops the GM. The
  target is then SELECTED on a detector frame captured after the GM stands (two equal minimap
  reads), with cells from that settled position. The engagement starts from that box itself (no
  re-projection). A stop with no target in that frame resumes the search and is not an
  engagement (definition unchanged: an engagement is a selection).
- Death needs 5 frames AND 2.5 s unseen (was 3 / 1.5).
- 120 s / 20 clicks per engagement (was 60 / 10): Pupas.
- **The settle fallback:** if the minimap cannot read while standing, the reckoned cell is used
  when a good fix is under 60 s old; /where only after that.
- Continuous walk clicks need the last TWO detector frames clear by 60 px (was one frame, 40 px).
- The per-engagement UI check is dropped. The 30-second check stays.
- Seed 20261103, 35 min.
- ➡️ **Attempt 1 (`20261015T223844-demo-hunt2`, 22:38:44) STOPPED at 42 s before any engagement:
  kept, not scored.**
  - The typing guard SKIPPED the start line `@warp prt_fild08 268 107` (the 3rd identical line in
    a row across the runs), so the GM stayed at (122,78). The minimap cannot read there, and /where
    was refused: the runs shared one /where budget, because hunt never called
    `chat_guard.start_run`.
  - Fixed, bug fixes within the version:
    - a seeded start cell (within 25 of 268,107), so the line differs run to run, honestly, never
      as a filler;
    - `chat_guard.start_run` per run;
    - the run stops if the start warp did not land within 3 cells.
  - Attempt 2: seed 20261104.
- ➡️ **Attempt 2 (`20261015T224153-demo-hunt2`, 22:41:53-23:17:47, the full 35-min box):
  engagement success 29 / 42 = 69.0 % (Wilson 54.0-80.9 %): FAIL** (and n < 60).
  - Failures: no unit at the selected cell 6, hit but not killed 5, never hit 2.
  - The GM's cell at every selection now matches the packets. The main failure is a STALE HOVER:
    the first read came ~2.0-2.5 s after its box (park + two-motion hover + the client's ~0.8 s
    cursor draw), read WALK because the monster had moved, and the target was then lost. One
    selection was a floor item (two PICKUP reads).
  - kills 31 (Poring 20, Lunatic 7, Drops 3, Pupa 1) = 51.8 / h; 69.5 s per kill; time to first
    target 6.7 s; 11.7 targets / 10 min; coverage 32.9k cells; EXP 96 / 45.
  - Time split: searching 816 s, fighting 585 s, looting 361 s, engaging 253 s, stopping 104 s,
    checks 35 s. Walk clicks: 144 cursor-gated, 111 map+units.
  - **Safety:** NPC contacts 0, dialogs 0, map changes 0, non-target hits 0, acts onto the GM 0;
    unintended attack requests 1.

**3.39.3 hunt@3 (pre-registered 2026-10-15 ~23:22, before its run).**
- **MAIN, the PARK-FIRST HOVER.** The cursor is parked at the selection, so the background holds
  the target where it stands. While the target stays within 6 px of that position, the hover goes
  out at once (~1 s, not ~2 s). It re-parks only when the target moved, and after each attack
  click (the GM walks up).
- The selection takes only boxes seen in TWO consecutive frames after the stop (within 30 px),
  and skips boxes under 16 px (floor items).
- Before the first click, the target is looked for within 200 px once unseen 0.5 s, and is lost
  after 5 s (was 3).
- Seed 20261105, 40 min (more room for >= 60 engagements).
- ➡️ **Attempt 1 (`20261015T232130-demo-hunt3`, 23:21:30) STOPPED by Claude at 23:45 after
  23.5 min, kept, not scored: STUCK, with 0 engagements.**
  - About a minute in, a continuous click left the GM at (218,22). That is 3 cells past its target
    (215,24), INSIDE the 6-cell keep-away margin of the south warp to moc_fild01 (x 221-245,
    y 15-17), outside the search area.
  - A* needs its start inside the area, so every plan failed. The bad-tile list reset at 40, and
    the loop sat silently for 21 min: no click, no input, the 30 s UI check passing.
  - No map change: safety intact. But it came closer to a warp than intended.
  - Fixed, bug and safety fixes within the version:
    - a GM outside the area is routed back over stand cells (cursor-gated) to the nearest area
      cell before any plan;
    - a WATCHDOG stops the run after 60 s with no route, click or engagement (fail safe);
    - the keep-away margin around warps and NPCs is 10 cells (was 6).
  - An offline re-simulation: 85.9k of 87.9k area cells in 35 min, 2 failed plans. From (218,22)
    the way back is (218,28).
  - Attempt 2: seed 20261106 (start 284,85).
- ➡️ **Attempt 2 (`20261015T234745-demo-hunt3`, 23:47:45-00:28:57, the full 40-min box):
  success 24 / 35 counted = 68.6 % (Wilson 52.0-81.5 %): FAIL.**
  - 2 excluded by the packets: a Pupa that METAMORPHOSED into a Creamy after selection.
  - Failures: no unit at the selected cell 7, hit but not killed 4.
  - kills 26 (Poring 18, Lunatic 8) = 38.6 / h; 93 s per kill; time to first target 96 s;
    9.2 targets / 10 min; coverage 38.4k cells.
  - Time split: searching 1,285 s (53 %), fighting 408 s, engaging 251 s, looting 234 s,
    stopping 196 s, checks 50 s.
  - **Safety:** NPC contacts 0, dialogs 0, map changes 0, non-target hits 0; unintended attack
    requests 1.
  - **The park-first hover did not move the rate.** The failures sit in the DISTANCE at selection:

    | GM -> target | hunt@2 success | hunt@3 success |
    |---|---|---|
    | 0-3 cells | 7 / 8 | 3 / 3 |
    | 4-7 | 8 / 10 | 10 / 11 |
    | 8-11 | 9 / 18 | 7 / 15 |
    | 12+ | 5 / 6 | 4 / 8 |

    The far selections fail as no unit at the cell (the box-to-cell estimate degrades with
    distance, or the box is a false positive) and as targets lost before any read.
- **The attack-started cue, MEASURED, NOT PROVEN, NOT USED** (`scripts/attack_cue.py`, on hunt@1
  attempt 2's 7,345 recorded frames against our attack acts).
  - The candidate: the GM's own sprite changing while the scene stays still.
  - Per frame, swing vs idle: Youden J 0.60 (96 % of swings over the threshold, 36 % of idle
    frames too).
  - Over 2-second windows: J 0.65 (94.5 % / 29 %).
  - Not usable as a gate: re-engagement stays the bounded SWORD-gated re-click every 5 s.
  - The first two measurements counted 95-99 % of frame pairs as still; that was a defect of the
    scene-shift band, which held static UI edges. Fixed before the numbers above.

**3.39.4 hunt@4 (pre-registered 2026-10-16 ~00:40, before its run).**
- **MAIN, SELECT WITHIN 7 CELLS, like a player.** A target farther than 7 cells is APPROACHED: a
  route to its cell, continuous walking, detection all the way. It is selected (the engagement
  starts) only once a target is within 7 cells, on the fresh frame after the stop.
- **The death is confirmed by a hover.** When the pixels say gone, the bot hovers the target's
  last box once (twice at most). A SWORD read means alive: back to engaging. v2/v3 had pixel
  deaths of live targets.
- Seed 20261107, 40 min.
- ➡️ **Attempt 1 (`20261016T003110-demo-hunt4`, 00:31:10-00:35:00) CRASHED after 2
  engagements: kept, not scored.**
  - The death confirmation appended a "still alive" sighting stamped NOW; later detector frames
    with earlier capture times followed it, and `deathcell` refused the out-of-order list
    (ValueError).
  - The crash also skipped writing the session. Its packets and manifest were written by hand
    afterwards.
  - Fixed, bug fixes within the version:
    - the confirmation keeps its own marker for the gone check, and the capture-ordered sightings
      stay untouched;
    - a crash now writes the session (packets, manifest) before it is re-raised.
  - Attempt 2: seed 20261108.
- ➡️ **Attempt 2 (`20261016T003626-demo-hunt4`, 00:36:26-00:51, 14.7 min) CRASHED: `OSError: No
  space left on device`, kept, judged as a partial, not a verdict.**
  - The cause is Claude's sizing error, not the version: the 5 Hz q92 recordings of the night's
    runs (~4 GB per 40-min run) filled /dev/shm (24 G, 100 %). Claude stopped the run (SIGINT) and
    finalised the session by hand.
  - The recordings were moved to the NAS (`hunt-recordings/<session>/`, rsync, bandwidth-capped).
    From attempt 3 on, the recorder writes the NAS directly at JPEG quality 80, and it stops
    itself (only the recording) under 2 GB free.
  - **Partial: 6 / 10 = 60 % (Wilson 31.3-83.2 %).** Failures: hit but not killed 3, no unit at
    the selected cell 1.
    - Two of the hit-but-not-killed were LOST before or between clicks; the same gid was attacked
      or killed later, by a LATER engagement.
    - One was a FALSE PIXEL DEATH that the hover confirmation did not catch: the hover read no
      SWORD, the run moved on, and the unit left our sight alive 16 s later.
  - kills 10 (packets) = 40.8 / h; time to first target 194 s; 6.8 targets / 10 min.
  - **Safety:** NPC contacts 0, dialogs 0, map changes 0, non-target hits 0; unintended attack
    requests 1.
- **Attempt 3 (pre-registered 2026-10-16 ~01:08, before its run):** the same version, the full
  40-min box, seed 20261109. The only change is the recording (the NAS, q80): nothing that
  decides.
- ➡️ **Attempt 3 (`20261016T010454-demo-hunt4`, 01:04:54-01:46:08, the full 40-min box):
  success 23 / 29 = 79.3 % (Wilson 61.6-90.1 %): FAIL** (and n < 60). The best so far.
  - Failures: no unit at the selected cell 3, never hit 2 (both `lost` before a click), hit but
    not killed 1.
  - The three no-unit failures all ended with the bot's kill, on targets selected mid-walk. The
    secondary measure (3.39.5, along the walk) counts 26 / 29 = 89.7 %.
  - Bot results: dead 26, lost 2, timeout 1 (a fight past 120 s).
  - kills 26 (Poring 18, Lunatic 5, Drops 3) = 38.8 / h; 92.9 s per kill; time to first target
    32.4 s; 7.2 targets / 10 min; planned path 151 cells per kill; coverage 46.9k cells;
    EXP 78 / 36.
  - Time split: searching 1,281 s (53 %), fighting 492 s, looting 269 s, stopping 166 s,
    engaging 162 s, checks 46 s.
  - **Safety:** NPC contacts 0, dialogs 0, map changes 0, non-target hits 0, **unintended attack
    requests 0**.
  - Selecting within 7 cells removed most of the `lost` failures (hunt@3: 9 of 37 engagements;
    here 2 of 29). It also lowered throughput: 29 engagements in 40 min, against the 60 the bar
    needs.

**3.39.5 hunt@5 (pre-registered 2026-10-16 01:16, before its run and before hunt@4 attempt 3's
result).** Why: across hunt@2-4, 22 of 28 failures ended `lost` with NO click.
- Recorded frames of four of them show three causes:
  - far selections walking out of view (hunt@4's approach already addresses those);
  - targets hidden under a tree canopy or behind the GM's sprite for a few seconds;
  - two `unknown` reads while the client drew the monster's name under the cursor, then the
    target moved.
- The engagement ended 5 s after the last sighting.
- **MAIN, STAY ON THE TARGET before the first click.**
  - When the target is unseen for over 1 s, the newest fresh detector frame is searched for a
    target box (the same species, size, UI and area gates) within 4 cells of the SELECTED cell.
    The one nearest the target's last feet takes the focus, up to 3 re-acquisitions.
  - The engagement is lost only after 10 s unseen with none found (was 5 s).
- **A bounded give-up, recorded:** 8 non-SWORD reads before the first click end the engagement
  as `no_sword`.
- Everything else is hunt@4 unchanged: select within 7 cells, the approach, the hover-confirmed
  death, robust2 SWORD reads.
- Seed 20261110, 40 min.

**A SECONDARY measure, pre-registered at the same time (01:16, before hunt@5's data).** It is
reported beside the 3.39 judge for every run and NEVER replaces it: verdicts stay with the 3.39
judge.
- `hunt_core.walk_positions`: a mob's cell along its walk. A move entry gives one cell step per
  `speed` ms, diagonal first; a stop packet pins the cell where it stopped.
- The 3.39 judge puts a walking mob at its walk's DESTINATION at once, so a target selected
  mid-walk can read 3-6 cells away.
- Applied post hoc to hunt@1-4 (labelled as such): it moves 0-2 engagements per run, e.g.
  hunt@2 69.0 % -> 73.8 %, hunt@3 68.6 % -> 68.6 %. **So the failures are real, not a judge
  artefact.**
- The bot's own box-to-cell projection was checked against mobs standing still: 68 of 95 exact
  (the rest within a few cells, mostly mobs that had moved).

**A second attack-started cue, the monster HP BAR: MEASURED 2026-10-16 01:25-01:55, NOT PROVEN,
NOT USED** (`scripts/hp_bar.py`, on hunt@2 attempt 2's 10,837 recorded frames against the packets).
- Found in a hunt@2 frame: this client draws a bar under a monster once it has taken damage.
  - It is 5 px tall and ~45-60 px wide: a dark border, a navy inside, the HP left as a fill
    from the left (magenta; yellow when low).
  - The GM's own HP / SP bars (green / blue) are told apart by colour.
- Within 3 cells of the GM:
  - in frames after our first act on the selected unit while it lives, a bar is found in 46.6 %
    of them (958 of 2,060 frames);
  - in frames before any act, a bar is found in 0.3 % of them (3 of 1,036);
  - Youden J 0.46.
- Per engagement, coverage runs from 0 / 81 to 114 / 119 frames. The first bar after the first
  act came 0.04-22.7 s later (median ~2 s).
  - Frames show the bar hidden behind the GM's sprite when the monster stands north of it
    (likely; not measured separately).
- **Verdict:**
  - not usable as an attack-started gate (a bar is seen within 3 s in about half the
    engagements);
  - a candidate ALIVE signal: a bar next to the GM almost never shows without a damaged monster
    there. That needs its own pre-registered measurement before any use.
- The finder's colour rules were fixed twice on this same session before these numbers (the
  magenta border, then the GM's own bar). So this is a development measurement, not a held-out
  one.

- ➡️ **hunt@5 (`20261016T014714-demo-hunt5`, 01:47:14-02:27:48, the full 40-min box): success
  14 / 14 = 100 % (Wilson 78.5-100 %), but n = 14, and A SAFETY EVENT: FAIL.**
  - Bot results: dead 12, lost 1, timeout 1; every engagement killed its selected unit.
  - **Safety: NON-TARGET HIT 1**, a Creamy (job 1018, gid 110019365; a Pupa that had
    metamorphosed in an earlier run). One attack request and one act, damage 0 (a miss), inside
    engagement 8. Also NPC contacts 0, dialogs 0, map changes 0; unintended attack requests 2.
    The run did not stop: safety is counted from the packets afterwards, not live.
  - **The cause (understood, from the packets and the engagement log):**
    - Engagement 8's Poring died at +665.8 s, and the bot did not see it.
    - After the first attack click the focus takes the nearest box of ANY monster within
      200 px. It passes none of the selection's gates (no size gate: a Creamy is 51 x 53
      native, over the 45 px gate).
    - The Creamy walked into that radius. The focus moved onto it and kept the target "seen",
      so no death was detected.
    - At +672.9 s the periodic re-click read SWORD (any monster gives one) and clicked it:
      attack request +674.7 s, a miss +674.8 s. The Creamy left our sight at +676.0 s.
  - **The 2 unintended attack requests** (+1,086.6 / +1,087.8 s, a Lunatic) came from an APPROACH
    walk click.
    - The approach route ends ON the monster's cell, so its click went 2 cells from it. The
      cursor read WALK; the monster moved in, and the client attacked.
    - A target species, so not a stop event, but avoidable.
  - kills 14 (Poring 9, Lunatic 5) = 21.0 / h; 171 s per kill; time to first target 85.5 s;
    3.5 targets / 10 min; coverage only 18.5k cells (hunt@4 attempt 3: 46.9k).
    - The search churned: 220 minimap drift corrections, each one stopping the GM (hunt@4
      attempt 3: 92), and 272 re-plans.
  - Time split: searching 1,654 s, fighting 357 s, stopping 162 s, looting 102 s, engaging 77 s,
    checks 48 s. Detector ~3.6 fps.
  - The re-acquisition (v5's main change) left no record of firing in the run's log. The one
    `lost` (engagement 4) was killed by a later engagement and still counts as killed: its gid
    died with our acts.

**3.39.6 hunt@6 (pre-registered 2026-10-16 02:30, the commit time 92c7b92, before its run): the SAFETY FIX for hunt@5's
non-target hit**, built on hunt@5.
- **MAIN, the focus stays on what could have been selected.**
  - The engagement's focus takes only boxes that pass the selection's pixel gates: the native
    size gate (45 px), the 16 px minimum, off the UI.
  - Once the GM has reached its target (a target box within 2.5 cells of the GM's feet, near
    the focus), only boxes within 2.5 cells of the GM count. A target that dies is then
    "gone", and the hover confirmation decides, instead of the focus moving to the next
    monster.
- **An approach route stops 3 cells short of the monster's cell**, so its walk clicks never aim
  at the monster.
- Everything else is hunt@5's.
- Seed 20261111, 40 min.
- Prediction, written before the run:
  - no non-target hit;
  - engagements that end on the target's death (no hop);
  - fewer re-clicks after a death.
- ➡️ **Result (`20261016T023113-demo-hunt6`, 02:31:13-03:11:49, the full 40-min box): success
  18 / 23 = 78.3 % (Wilson 58.1-90.3 %): FAIL** (and n < 60). **The safety fix held: no
  non-target hit.**
  - Failures: no unit at the selected cell 3, hit but not killed 1, never hit 1. The secondary
    measure: 19 / 23 = 82.6 %.
  - Bot results: dead 19, lost 3, timeout 1.
  - kills 25 (Poring 18, Lunatic 4, Drops 3) = 37.5 / h; 96.1 s per kill; time to first target
    54.4 s; 5.7 targets / 10 min; coverage 47.0k cells. Detector ~3.5 fps.
  - Time split: searching 1,326 s, fighting 521 s, looting 183 s, engaging 183 s, stopping
    143 s, checks 47 s.
  - **Safety:** NPC contacts 0, dialogs 0, map changes 0, non-target hits 0.
    - Unintended attack requests 2, both on Porings (a target species): walk clicks that the
      client turned into attacks (+1,686 s cursor-gated, +1,898 s map+units). The known
      walk-click class (walk@10), about 1-2 per run in every version.

**3.39.7 hunt@7 (pre-registered 2026-10-16 03:12, the commit time 60cd081, before its run).** The top time-loser: the
search (53-69 % of every run).
- **MAIN: dead reckoning at the GM's MEASURED speed, 150 ms a cell (was 200).**
  - hunt@5's move packets give 150 ms a cell, rAthena's default walk speed. Consecutive moves
    give at most 160-180 ms with the click delays included.
  - 211 of hunt@5's 220 drift stops had the minimap AHEAD of the reckoning. Each stop settles,
    re-plans and starts again with a cursor-gated click.
  - The slow reckoning also delayed every continuous click: "<= 3 cells remain" came late, so
    the GM stood between legs.
- Everything else is hunt@6's, the safety fix included.
- Seed 20261112, 40 min.
- Prediction, written before the run:
  - far fewer drift stops (hunt@6: 102, hunt@5: 220);
  - more coverage and more engagements in 40 min;
  - the success rate unchanged within noise.
- ➡️ **Result (`20261016T031319-demo-hunt7`, 03:13:19-03:53:59, the full 40-min box): success
  7 / 12 = 58.3 % (Wilson 31.9-80.7 %): FAIL. THE PREDICTION FAILED:** 206 drift stops, more than
  hunt@6's 102, and only 12 engagements.
  - Failures: no unit at the selected cell 3, hit but not killed 2. The secondary measure:
    8 / 12 = 66.7 %.
  - kills 10 = 15.0 / h; 240 s per kill; time to first target 23.3 s; 3.0 targets / 10 min;
    coverage 40.8k cells.
  - Time split: searching 1,838 s (77 %), fighting 149 s, looting 127 s, stopping 119 s,
    engaging 117 s, checks 53 s.
  - **Safety:** NPC contacts 0, dialogs 0, map changes 0, non-target hits 0, unintended attack
    requests 0.
  - **The real cause of the drift stops, found during this run: a STUCK LOOP, not the reckoning
    speed.** The "minimap ahead" reading under 3.39.7 was a flawed analysis: it projected each
    drift on the last move's direction, and a GM standing at the end of that move reads "ahead".
    - At (344,71) the bot's route clicked (344,79) 8 cells north.
    - The recorded frames show the client's NO-ENTRY cursor (the red ring) blinking at that
      point. robust2's 6-grab series read WALK and clicked.
    - The client sent NO move request (the live packets: no `self_move_request` after the
      click).
    - The reckoning "walked" anyway, the minimap disagreed, the drift stop settled at the same
      cell, and the same route was planned again.
  - 87 drift stops at (344,71) alone. Time in such loops (consecutive drift stops at the same
    minimap cell, < 15 s apart): hunt@2 0.1 min, hunt@3 1.0, hunt@4 attempt 3 2.5, hunt@5 12.6,
    hunt@6 3.6, hunt@7 13.5. Repeated pairs show a 6-cell y offset at the same spots: hunt@5
    (278,123) / (278,117) 120 times, hunt@6 (342,77) / (342,71) 30 times.
  - The 150 ms reckoning stays: it is the measured speed. It was not the time-loser.

**3.39.8 hunt@8 (pre-registered 2026-10-16 03:54, the commit time fc1b82c, before its run).** The top time-loser: the stuck loops (up to 13.5 of 40 min).
- **MAIN, UNSTICK.**
  - A cursor-gated walk click that the GM does not follow is detected: the next drift stop finds
    it within 1 cell of where it clicked.
  - The clicked cell and its neighbours leave the search area for the rest of the run: radius 1,
    growing to 3 on repeats from the same cell, never the GM's own 3 x 3.
  - The next route goes around them. Each such event is logged (`unfollowed_click`).
  - The robust2 misread itself (no-entry read as WALK at that spot) is recorded for the cursor
    work. It is not changed here: robust2 stays the live gate.
- Everything else is hunt@7's (150 ms reckoning, the safety fix).
- Seed 20261113, 40 min.
- Prediction, written before the run:
  - repeated drift stops at one cell: at most 3 per spot;
  - loop time under 1 min;
  - more engagements than hunt@7 (12);
  - the success rate unchanged within noise.
- ➡️ **Result (`20261016T035516-demo-hunt8`, 03:55:16-04:35:56, the full 40-min box): success
  21 / 31 = 67.7 % (Wilson 50.1-81.4 %): FAIL** (and n < 60). **The prediction held:**
  - repeated drift stops: at most 1 per spot (28 in all; hunt@7: 206);
  - time in loops: 0.0 min (hunt@7: 13.5);
  - 32 engagements (hunt@7: 12), the most since hunt@2.
  - 10 unfollowed clicks were caught, each once, and routed around. That includes (343,72),
    hunt@7's 87-stop spot.
  - Failures: no unit at the selected cell 5, hit but not killed 3, never hit 2; excluded 1 (a
    Pupa that metamorphosed). The secondary measure: 25 / 31 = 80.7 %.
  - kills 29 (Poring 23, Lunatic 4, Drops 2) = 43.5 / h; 82.8 s per kill; time to first target
    37.9 s; 8.0 targets / 10 min; planned path 105 cells per kill; coverage 44.9k cells.
  - Time split: searching 1,232 s, looting 411 s, fighting 392 s, engaging 244 s, stopping 77 s,
    checks 46 s.
  - **Safety:** NPC contacts 0, dialogs 0, map changes 0, non-target hits 0.
    - Unintended attack requests 3, on a Poring (twice) and a Lunatic: continuous map+units walk
      clicks the client turned into attacks (the walk-click class).

**3.39.9 hunt@9 (pre-registered 2026-10-16 04:36, the commit time e42e92c, before its run).** The top failure cause now: no unit at the selected cell (5 of hunt@8's 10).
- In every such case read so far, the target was selected mid-walk. The bot killed it, and the
  3.39 judge places a walking mob at its walk's destination.
- **MAIN, SELECT A TARGET STANDING STILL.** After the stop, a target whose feet stayed within
  6 px for 0.5 s on the detector frames is preferred (waiting up to 1.5 s). A moving one is taken
  only when none is still.
- Each engagement records whether its target was still (`selected_still`).
- Everything else is hunt@8's.
- Seed 20261114, 40 min. The last client run of the night: it ends ~05:20, and nothing runs
  on the client after it.
- Prediction, written before the run:
  - fewer no-unit failures;
  - engagements on still targets succeed more often than on moving ones;
  - throughput within ~10 % of hunt@8.
- ➡️ **Result (`20261016T043716-demo-hunt9`, 04:37:16-05:17:58, the full 40-min box): success
  19 / 28 = 67.9 % (Wilson 49.3-82.1 %): FAIL. The main prediction FAILED:** still 5 no-unit
  failures, as in hunt@8.
  - The still preference was taken on 24 of 28 engagements: 17 / 24 succeeded, against 2 / 4 on
    moving targets. That is in the predicted direction, but the moving sample is far too small to
    tell.
  - Throughput: 28 engagements (hunt@8: 32, 12.5 % fewer: just outside the predicted 10 %).
    no_target_after_stop rose to 16 (hunt@8: 5): the still wait finds fewer targets.
  - Failures: no unit at the selected cell 5 (4 of them `lost` before any click), never hit 2,
    hit but not killed 2. The secondary measure: 20 / 28 = 71.4 %.
  - Bot results: dead 20, lost 7, timeout 1.
  - kills 20 (Poring 13, Lunatic 6, Drops 1) = 30.0 / h; 120 s per kill; time to first target
    137 s; 7.0 targets / 10 min; coverage 35.3k cells. Unfollowed clicks 8, drift stops 25.
  - Time split: searching 1,389 s, fighting 392 s, engaging 244 s, looting 243 s, stopping 89 s,
    checks 46 s.
  - **Safety:** NPC contacts 0, dialogs 0, map changes 0, non-target hits 0.
    - Unintended attack requests 2, on a Drops (a target species), after walk clicks.
  - The GM was restored to its fixed state by the run (`gm_state_after`: restored, fixed). The
    client was judged clean at 05:18, and nothing ran on it after.

**3.39.10 The night in one place (2026-10-16 05:20, Claude; the numbers are the 3.39 judge's,
`scripts/hunt.py judge SESSION`).**
- **95 % was NOT reached, and nothing was confirmed.** No run reached 60 engagements: the most
  was hunt@1's 52 at 46 %, and 12-42 per 40-min run after it.
  - The best clean run is hunt@4 attempt 3: 23 / 29 = 79.3 % (Wilson 61.6-90.1 %).
  - hunt@5's 14 / 14 had a safety event (a non-target hit), so it is not a candidate.
- **What still fails, ranked** (hunt@4 attempt 3 through hunt@9, the 3.39 judge):
  1. no unit at the selected cell: 19 (3 + 0 + 3 + 3 + 5 + 5). Targets selected mid-walk. The bot killed most of them;
     the secondary measure rescues 3 of 3, 1 of 3, 1 of 3, 4 of 5, 1 of 5 per run.
  2. hit but not killed: 9 (1 + 0 + 1 + 2 + 3 + 2). Lost or false pixel deaths; some were killed later by another
     engagement.
  3. never hit: 7 (2 + 0 + 1 + 0 + 2 + 2). Lost before the first click: hidden, or walked out of reach.
- **What costs the time, ranked** (hunt@8, the latest run without a new selection rule):
  searching 51 %, looting 17 %, fighting 16 %, engaging 10 %, stopping 3 %.
  - hunt@5-7's stuck loops (up to 13.5 min a run) are fixed by hunt@8's unstick.
  - ~~The field is the limit behind the search: 20-33 monsters entered the client's sight per
    10 min. 60 engagements in 40 min would mean engaging about three quarters of them.~~
    ➡️ **SUPERSEDED 2026-10-16 ~10:10 by Batt's human demonstration (3.40): the BOT's movement
    capped it, not the field.** On the same map:
    - Batt (never stopping, one-hit kills) had 44 distinct monsters enter sight in 10 minutes and
      killed 50;
    - hunt@4 attempt 3, hunt@8 and hunt@9 had 6-22 per 10 min (distinct gids).
- **Safety, all nine versions:** NPC contacts 0, dialogs 0, map changes 0.
  - One non-target hit: hunt@5, a Creamy, one miss. The cause was understood (the focus took
    any monster), fixed in hunt@6, and zero since (hunt@6-9).
  - Unintended attack requests: 0-3 per run, all on target species, all from walk clicks the
    client turned into attacks. That is the walk@10 class, not fixed tonight.
- **The attack-started cue is NOT proven.** Two candidates were measured: the GM's swing (J
  0.60-0.65) and the monster HP bar (J 0.46). Re-engagement stays the bounded SWORD-gated
  re-click every 5 s.
- **Held-out:** not due (no version passed twice). It also could not run: no other field in the
  local KB's 59 spawn maps has only v1's five species. The nearest, pay_fild03 / prt_fild04 /
  prt_fild06, each have 3 species outside them.

**3.39.11 After the night: two post-hoc analyses and the anim resume (2026-10-16 08:50, Claude).** These
re-read data that was already judged. No verdict changes, and nothing here was pre-registered.
- **The first click DID attack, now on every run** (Batt's step 1, "first-click diagnosis"):
  - 215 first attack clicks across the ten scored runs, hunt@1 attempt 2 to hunt@9 (packets, 4 s
    after each click):
    - 190 (88 %): the client walked up first (`self_move_request`), then sent its own
      `attack_request`;
    - 20 (9 %): an attack request at once (already in range);
    - 5 (2 %): a walk only, with no attack request within 4 s. Three of these were attacked by a
      re-click 4-13 s later and killed. Two had no attack request after the click: one was still
      judged killed, one was hit but not killed.
  - From the click to the attack request: p50 1.09 s, p90 2.14 s, max 3.39 s.
  - Where the 210 requests went:
    - 188 on the judge's selected unit G;
    - 18 in engagements where the judge found no G;
    - 4 on another unit of a target species.
  - farm@1's corrected reading (6.2) holds at n = 215. The client walks up and attacks by
    itself, so "the first click only walked" is not a failure cause.
- **The 19 no-unit failures (hunt@4 attempt 3 to hunt@9), one by one:**
  - 13 got an attack click. 14 had an attack request of ours inside the engagement (one came from
    a walk click). Every one of those 14 attacked units died by our hits.
  - 6 were `lost` before any click, and 5 of those had no attack request at all.
  - The along-walk model re-reads 9 of the 19 as killed, 1 as hit not killed and 1 as never hit.
    8 stay no-unit:
    - 4 were attacked and killed by us. By the walk model, the unit we attacked stood 3-7 cells
      from the selected cell at selection (the judge allows 2 there, and 5 at the first request).
      Either the cell estimate was off or the target kept walking; the two are not separated here.
    - 4 were lost with no click. The nearest mob at selection was 5, 6, 15 and 25 cells from the
      selected cell. In the last two, no mob stood anywhere near a cell within 7 cells of the GM,
      so they were most likely detector false positives (NOT checked on the frames).
  - So "no unit at selection" does NOT mean "the target was gone at click time": in 14 of 19 the
    bot attacked and killed a unit. Three things share the label:
    - the judge's destination model (9);
    - the attacked unit 3-7 cells from the selected cell (4);
    - selections with no unit near them (4 to 6).
- **The prt_fild08 animated-region measurement, resumed** (Batt: "resume it after 06:00 or later").
  - The first session, `20261015T210808-demo-anim-region-prt-fild08`, ran 21:08:08-21:57:30. It
    was stopped by SIGINT in a grab phase with 178 of the lattice's 280 pass-1 views, and no
    rechecks yet.
  - The resume started at 08:45:56 (client judged clean at 08:45, the known fixed-state UI) as
    `20261016T084603-demo-anim-region-prt-fild08`:
    `anim_region.py measure --map prt_fild08 --max-pass2 300 --resume-from 20261015T210808-demo-anim-region-prt-fild08`.
  - Its result is recorded here when it ends. Until then the region is not built and not used.

### 3.40 hunt-flow: CLICK -> WALK IN -> HIT LANDS (Batt 2026-10-16 ~09:20; supersedes kill success as the goal)

Batt's words: "the skill is CLICK -> WALK IN -> HIT LANDS, fast and never missing. Killing doesn't
matter. On a community server other bots compete for monsters, so reaction speed is the point."

**The test state (recorded for these runs):** the GM, immune (`@monsterignore`, confirmed for the
login), Base Lv 70 (Batt 09:36: "remove lv99 ... lv 70 it ok"), STR 99 (status window), ATK 197,
HIT 71. One hit kills Poring (50 HP), Lunatic (60) and Drops (55); a Pupa (427, immobile) takes ~3.
Job Lv 1, weight < 50 %. Set 2026-10-16 09:33-09:38 by `@baselevelup 98`, STR raised by the status
window's arrow, then `@baselevelup -29` (the pinned source keeps the stats when enough points
remain: 82 left).

**The GM's weight rule (Batt 2026-10-16 ~09:20; `gm_state.py`, the GM TEST state only: 2000001's
loot is sold at the shop, never thrown).**
- Every restore (`ensure_fixed`) clears the loot. The weight must then read under 50 % on the
  pixel readout, or the run stops for a person.
- A long run clears it at its next safe moment once the weight passes 40 %.
- No group-20 command removes items:
  - `@delitem` exists in the pinned source, but group 20 lacks it, and it does not check whether
    an item is equipped;
  - `@storeall` and `@dropall` unequip first.
- So `clear_loot` takes the inventory's known path: its chord, a tab, a drag of the slot onto
  open ground, Enter on the quantity prompt (only when the prompt's OK button matches), and the
  chord to close it.
- Only icons on a LOOT allowlist are dropped: 10 icons cut from the 09:22-09:25 inventory
  (data/, never committed). The Fly Wing is KEPT; anything unknown stays and is reported.
  - The same icon reads 0.0-0.07 across frames; the closest two different references read 9.2;
    the match bar is 3.0.
- loot@1's trials opt out: dropped items would lie on the floor a pickup trial reads.
- Proven:
  - by hand, 09:23-09:27: 1052 -> 130;
  - live by `gm_state.py clear-loot`, 10:56-10:57: 8 stacks dropped, 246 -> 172 / 4970, the Fly
    Wing kept, 2 unknown stacks left;
  - tests in `test_gm_state.py`.
- `gm_state` PROFILES: `hunt-flow` = Base Lv 70 / Job Lv 1 (its template was cut 10:56 from a
  judged frame). Its restore is `@joblevelup -49` and `@heal` only, never the base level, so
  STR's points stay.

**The human baseline:** Batt played 10 minutes himself, recorded as
`20261016T093835-demo-human-demo`:
- armed 09:38:35; his first input at 09:40:34; the time box ended 09:51:35;
- quiet (60 s without his input) at 09:51:52;
- 3,888 frames (NAS `human-demos/`, q80), 2,504 detector frames, 2,197 packet events and
  14,827 input events of his, all local (never committed).
- Recorded by `scripts/human_demo.py`, which holds no input path (tested).

**THE METRICS, pre-registered 2026-10-16 09:54 (the commit a47b91f), after the demo was banked and BEFORE any of its
analysis. They are binding for the human baseline and for every hunt-flow version alike;
`scripts/flow_judge.py`.**
- **Clock and positions:** the host's CLOCK_MONOTONIC throughout. Positions come from
  `hunt_core.walk_positions` (the along-walk model) for every mob and for our GM. Packets are
  offline ground truth only.
- **Window:** [t0, t0 + 600 s]. t0 = our first `self_move_request` after arming (the human)
  or after the loop start (the bot). Nothing before t0 counts.
- **CLICK:**
  - human: an accepted left `mouse_button` down of source=human, inside the game region, not
    on the fixed UI (`loot1.in_ui`);
  - bot: every click the runner logs.
- **ATTACK CLICK:** a click followed by our `attack_request` within 1.5 s and before the next
  click. For the bot, every SWORD-gated attack click counts, whatever follows.
- **ATTEMPT:** a click whose point lies inside a detector monster box (expanded by 6 px) on the
  newest detector frame captured <= 0.5 s before it. An attempt with no attack request is a
  `walk_only` miss.
- **TARGET G:**
  - the attack request's `target_gid`;
  - for an attempt with no request, the mob nearest the click's picked cell
    (`picking.pick_cells` from our cell at the click), within 2 cells; else `no_unit`.
  - When a mob other than the request's target is nearest the picked cell (within 2) and the
    request's target is not within 2, the click is `other_unit`.
- **TRIAL:** an attack click or an attempt, unless we already acted on its G in the 3 s before
  it (a follow-up click while attacking: reported, not a trial).
- **HIT RATE** = trials with a damaging act of ours (damage > 0) on G within T = 3.0 s / trials.
  - Failures: `walk_only`, `request_no_act`, `miss_only` (acts with damage 0 only),
    `other_unit`, `no_unit`, `no_response`.
  - **Bar for the bot:** > 95 % over >= 60 trials pooled over same-version runs, safety events
    0. The Wilson 95 % interval is reported.
- **REACTION** (p50 / p90, trials that hit):
  - first seen = the earliest detector frame, going back from the click with no gap over 2 s,
    with a monster box whose picked cell lies within 1.5 cells of G's cell then;
  - reported: seen -> click, click -> first damaging act, seen -> hit.
- **Range:** the Chebyshev distance in cells from our GM to G at each trial's click.
- **IDLE %:** the share of the window in which our GM is not moving (the walk model).
  - It is split into idle within 1.5 s after one of our acts (attacking) and idle otherwise.
- **WALK CLICKS:** clicks followed by a `self_move_request` (and no attack request) within
  1.0 s.
  - spacing = Chebyshev cells from our cell to the requested destination;
  - cadence = the interval between consecutive walk clicks;
  - the share sent while we were still moving.
- **TARGET CHOICE:** at each trial, G's rank by distance among the mobs within 14 cells (1 =
  nearest).
  - A SWITCH = a trial on G' while another G was clicked or hit in the 3 s before and is still
    alive.
- **KILLS / H:** deaths (reason 1) of units we acted on, in the window. Pickups are reported
  (time spent).

**3.40.1 THE HUMAN BASELINE: Batt, 10 minutes (`20261016T093835-demo-human-demo`; judged by
`flow_judge.py human`, 2026-10-16 ~10:00, the definitions above unchanged).**
- **Window:** t0 = his first move at 09:40:36.5 (121.6 s after arming; his first input 09:40:34),
  to t0 + 600 s. His input: 587 left clicks in the game region and mouse moves; no keys, no
  right-drag, no wheel, so the camera stayed at its default and click -> cell holds.
- **HIT RATE: 53 / 66 trials = 80.3 % (Wilson 69.2-88.1 %).** Failures: `no_unit` 12,
  `walk_only` 1.
  - **Every click that resolved to a unit landed: 53 / 54**, at every range 1-8+ cells.
  - The 13 failures are clicks on a monster's sprite that the client resolved to the ground, so
    it WALKED there. Frames and packets, one by one:
    - 9 on monsters walking or just arrived, 3-6 cells from the picked ground cell. Each was hit
      by a re-click 1.3-4.6 s later.
    - 2 on monsters that died 0.07-0.1 s before (the death animation still drawn).
    - ~~1 unexplained: a Poring-like sprite at the click, and no mob in the packets near it
      (none within +-4 s).~~ ➡️ **CORRECTED 2026-10-16 11:08 (62035a5): a JUDGE BUG, not a mystery.**
      rAthena reuses a dead mob's id for a later spawn. `flow_judge.alive()` kept only an id's
      last life, so a mob alive at 509 s looked absent. Fixed: every life of an id is kept
      (`test_a_reused_gid_keeps_every_life`). The Poring in the frame was real. The trial
      numbers above do not change.
    - 1 `walk_only` on a walking mob.
  - By target motion, when the click resolved: standing 33 / 33, walking 20 / 21. Most
    unresolved clicks were on WALKING monsters.
  - Clicking while his GM was still moving landed 5 / 9; from a standstill, 48 / 57.
- **REACTION** (p50 / p90):
  - first seen -> click 1.11 / 4.79 s;
  - click -> first hit 0.61 / 1.48 s;
  - seen -> hit 2.39 / 5.56 s (50 of 53 hits had a detector first-seen).
  - Click -> hit by range (p50): 1 cell 0.02 s, 2: 0.34, 3: 0.46, 4: 0.58, 5: 0.76, 6: 1.03,
    7: 1.12. That is ~0.15 s a cell, the GM's walk.
- **Range at the click:** p50 4 cells, p90 7.
  - Histogram: 1:2, 2:9, 3:12, 4:9, 5:5, 6:5, 7:7, 9:2, 10:2, 11:1.
- **Target choice:** the nearest visible mob 52 of 54 times; 2 switches.
- **IDLE 45.9 %** of the window, 15.0 % of it attacking. The rest: 62 pickups (he looted
  everything) and pauses.
- **Walk clicks:**
  - 440 = 44 a minute;
  - spacing p50 6 / p90 9 cells; interval p50 0.6 / p90 3.4 s;
  - 72.7 % sent while still walking. He re-aims about 6 cells ahead several times a second.
- **Kills 50 = 300 / h;** 44 distinct monsters entered sight in the 10 minutes.
  - He roamed the whole map: y 58 to 371, far north of the bot's usual area.
- **Safety, informative (a human):**
  - He clicked the Poring-looking quest NPC "Poring War Recruiter#wo" (159,371) at t0+144 s: a
    dialog, cancelled at its menu. A bot must never do that; the detector sees it as a monster,
    and only the cursor read (TALK, not SWORD) tells them apart. It is in the KB, and the search
    area keeps 10 cells from it.
  - No map change in the window.
- **Restored after** (60 s without his input, 09:51:52):
  - Job Lv 5 -> 1 (`@joblevelup -49`); `@heal`;
  - Base Lv 70 / STR 99 kept for hunt-flow;
  - weight 246 / 4970 (5 %): no loot cleared;
  - the client's new-item and skill-point badges remain.
- **hunt-flow@1's parameters, derived from this (to be pre-registered with hunt-flow@1):**
  - attack click at <= 3 cells (Batt's proposal 2-3; his p50 is 4, and 3 cells cost ~0.46 s of
    walk-in);
  - from a STANDING GM (his moving-GM clicks landed 5 / 9);
  - on the target's predicted position, preferring a standing target (his misses were on
    walking ones);
  - the nearest target first;
  - walk clicks ~6 cells ahead, re-aimed every ~0.6-1 s while walking;
  - no looting.

### 3.41 hunt-flow@1 (pre-registered 2026-10-16 10:59 ICT, the commit time eef21d6, BEFORE its code and any of its data; Batt ~10:10: "the human baseline changes the goal")

**THE PRIMARY BAR (Batt): HIT WITHIN W OF THE FIRST ATTACK CLICK, RE-CLICKS ALLOWED.**
- **ENGAGEMENT:** the bot's FIRST attack click on a tracked target. Later attack clicks on that
  track are re-clicks. A target dropped before any attack click is not an engagement; those
  are reported apart (count and why).
- **G:**
  - the unit our first attack request (within 1.5 s of the first click) targets, when it stood
    within 3 cells of the bot's predicted cell for the target at the click;
  - else the mob nearest that cell within 2 (the along-walk model);
  - else `no_unit`, a failure.
- **SUCCESS:** a damaging act of ours (damage > 0) on G within **W = 5.0 s** of the first
  attack click.
- **Why W = 5.0 s:** Batt's re-hit times after a failed first click (3.40.1) were 1.3, 1.9,
  1.9, 2.1, 2.5, 2.9, 3.3, 3.6, 4.3 and 4.6 s. That is p90 4.3 s (nearest rank), max 4.6 s, so
  W = p90 + 0.7 s margin, above his maximum.
- **EXCLUDED, packets only:**
  - G changed species;
  - G died with no act of ours;
  - G vanished another way (reason not 0 or 1) before our first act.
  - Out of sight (reason 0) is a failure.
- **PASS:** >= 95 % over >= 60 engagements, pooled over runs of THIS version with fresh seeds,
  and safety events 0 (NPC contact, dialog, map change, a non-target hit, an unknown UI state).
- ~~**Batt on the same definition (the reference, no bar):** 63 / 64 = 98.4 %.~~ ➡️
  **CORRECTED by `flow_judge.py human` (11:08, 62035a5, after the id-reuse fix above): 64 / 64 = 100 %
  (Wilson 94.3-100 %).**
  - His 53 first-click hits, plus 11 re-hits within W.
  - 2 excluded: clicks on monsters that had just died.
  - The 509 s click was the judge bug, not a failure. The hand count in this paragraph was
    written before the code existed.
- **Reported beside, NEVER the bar:**
  - the first-click-lands rate, 3.40's trial HIT RATE (Batt 80.3 %);
  - FIRST-CLASS results after every run, in one bot-vs-Batt table:
    - kills / h (Batt 300);
    - seen -> click p50 / p90 (Batt 1.11 / 4.79 s);
    - click -> hit (Batt 0.61 / 1.48 s);
    - monsters in sight / 10 min (Batt 44);
    - idle % (Batt 45.9);
    - walk clicks / min (Batt 44);
    - range at the click (Batt p50 4).

**THE DESIGN (`scripts/hunt_flow.py`, version 1; parameters from Batt's play, 3.40.1):**
- **State:** the GM's `hunt-flow` profile: immune (confirmed for the login), Base Lv 70,
  Job Lv 1, STR 99, the loot rule. prt_fild08, natural spawns, hunt's search area (stand
  cells, 10 cells clear of warps and NPCs, the Poring War Recruiter included). RDP, the UI
  gate, HUD + route preview ON. 30 minutes a run.
- **WALK CONTINUOUSLY:**
  - a coverage route as hunt's;
  - while walking, a click every ~0.8 s to the path cell ~6 cells ahead of the reckoned
    position (in view, off the UI, gated by the map and the detector: 3.39 deviation (2)
    option B);
  - a click from a standstill is cursor-gated (robust2 WALK);
  - the GM never stands to search.
- **TRACK:** every fresh detector frame -> boxes through hunt@6's selection gates (size, >= 16
  px, off the UI, in the area) -> cells from the reckoned position at the frame's time ->
  tracks.
  - A box joins the track whose predicted cell is within 2 cells; the velocity comes from its
    last sightings.
  - A track is dropped after 2 s unseen.
  - Each track keeps its first-seen time.
- **QUEUE AND STEER:**
  - the nearest track first (Batt: the nearest 52 / 54);
  - the route is re-aimed every ~0.8 s to a cell 2 cells short of the target's predicted cell,
    so its last walk point is <= 3 cells from it.
- **STRIKE:** at the brief moment the walk ends (the GM at its last walk point, never waiting),
  if the target's predicted cell is <= 3 cells away:
  - park, hover the target's newest box (a fresh frame), read robust2 ONCE;
  - SWORD -> the attack click at that box (as hunt@6). Not SWORD -> up to 2 more reads on
    the newest box, else steer again.
  - The SWORD read before every attack click is the only separator from an NPC that looks
    like a monster.
- **AFTER THE CLICK:**
  - dead (pixels) = no target box within 1.5 cells of its last position for 0.6 s -> the next
    target, or the route, at once;
  - still seen after 2.0 s -> a re-click (a new SWORD read);
  - give up at 8 s.
  - NO LOOTING.
- **Logged:**
  - `clicks.jsonl`: every click with its time, client px, kind (strike / walk), gate and track;
  - `engagements.json`: track, first-seen, the clicks with predicted cells, the result;
  - `events.jsonl`; the frames on the NAS (5 Hz, q80).
- **Safety unchanged:**
  - every attack click after a SWORD read;
  - walk clicks gated;
  - the UI gate on every typed line plus the 30 s client check;
  - packets judge offline only;
  - the weight rule (clear above 40 % between engagements).
- **Prediction, written before the run:**
  - the primary rate well above hunt@4 attempt 3's 79.3 % kill-success (a different metric;
    one-hit kills);
  - kills / h several times hunt@8's 43.5;
  - seen -> click slower than Batt's 1.11 s (the cursor read alone takes ~1.2-1.6 s).

- ➡️ **hunt-flow@1 run 1 (`20261016T110837-demo-hunt-flow1`, 11:08:37-11:39:47, the full
  30-minute box; judged by `flow_judge.py bot`): THE BAR 10 / 11 = 90.9 % (Wilson
  62.3-98.4 %).** 1 failure: no unit. n is far below 60.
  - **Beside it:**
    - first click lands 20 / 23 = 87.0 %;
    - kills 20 = 40.3 / h;
    - seen -> click p50 8.9 / p90 25.4 s;
    - click -> hit 0.71 / 0.99 s;
    - monsters in sight 7.0 / 10 min;
    - idle 77.9 %;
    - walk clicks 14.1 / min, only 18 % sent while walking;
    - range at the click p50 3 / p90 6;
    - death -> next click 6.68 / 8.64 s.
  - **Batt (3.40.1):**
    - 64 / 64;
    - 300 kills / h;
    - seen -> click 1.11 s;
    - 44 in sight;
    - idle 45.9 %;
    - 44 walk clicks / min;
    - death -> next click 1.24 s.
  - **Time split (the runner):** searching 884 s, steering 624 s, striking 222 s, checks 44 s,
    stopping 20 s, fighting 7 s. Detector 3.1 fps.
  - **What it showed:** most walk clicks went out from a STANDSTILL (cursor-gated, ~1.2 s read
    each). The one map+units point v1 tried while walking was usually within 60 px of the target
    it steered to, so the GM stopped near every target.
  - **Safety (packets):** NPC contacts 0, dialogs 0, non-target hits 0. The one map change is
    the start `@warp`.
    - **UNINTENDED ATTACK REQUESTS 10**, all on target species (Poring, Lunatic, Drops): the
      client turned our WALK clicks into attacks 0.4-0.9 s after them (8 map+units, 2
      cursor-gated). They are attacks without a SWORD read.
    - They are not a stop event under 3.41 (counted and reported, as 3.39). They also account
      for 10 of the 20 kills: only 11 came from engagements.
    - The hunt runs had 0-3 a run. Steering puts walk clicks next to monsters, and the 60 px
      detector gate on frames 0.3-0.6 s old misses a monster walking into the clicked spot.
    - The next version's first item.

### 3.42 hunt-flow@2: PIPELINED (pre-registered 2026-10-16 11:33 ICT, the commit time 97442cc, BEFORE its run; Batt ~11:30: "hunting is still serial (find -> walk -> hit -> think again). Make it PIPELINED, like a player who plans the next target while hitting the current one")

hunt-flow@1 was pre-registered (3.41) and was running when this came, so this is version 2.
`scripts/hunt_flow.py --version 2`. Everything else is 3.41: the state, the gates, no looting, the
bar.
- **Three concurrent loops** on the monotonic clock:
  - PERCEPTION, its own thread: the detector sampler plus a tracker that turns every frame
    into tracks. It reads our cell at the frame's time from a shared position model and has
    its own camera model.
  - PLANNER, its own thread, every 0.1 s:
    - the TARGET QUEUE, 3 deep, by the shortest CHAINED path: each next target nearest to the
      previous one's predicted cell, not only to the GM;
    - a walking monster costs 2 cells more, so standing targets come first;
    - spots a dropped target left are skipped for 15 s;
    - the NEXT EXPLORATION WAYPOINT, always held: the coverage plan's stalest tile and its A*
      path, re-planned every 3 s or when reached.
  - EXECUTOR, the main loop: it only clicks, and never waits for the planner (it reads the
    latest queue).
- **HAND-OFF:** the instant the target is dead by pixels (or given up), queue[0] or the
  waypoint is taken at once. Our cell comes from ONE minimap read near the last one; there is
  no settle wait unless that read fails.
- **REVALIDATE AT DISPATCH:** queue[0] is dispatched only if the tracker still holds it with a
  box <= 1.0 s old, else the next queued one. The strike then re-checks a box <= 0.4 s old and
  needs the SWORD read before its click. Planning never bypasses a gate.
- **A walk click while walking** goes to the FARTHEST path point (<= 6 ahead) that passes the
  map and unit gates. v1 tried one point and gave up when it was within 60 px of a unit, which
  stopped the GM near every target.
- **Measured, beside the 3.41 bar (bot vs Batt, one table after every run):**
  - IDLE BETWEEN KILLS = a death (packets) -> our next click of any kind (Batt p50 1.24 /
    p90 1.80 s, n 50);
  - kills / h (Batt 300);
  - seen -> click (Batt 1.11 / 4.79 s);
  - QUEUE HIT-THROUGH = queue[0] still valid at dispatch / queue[0] dispatches (bot log; Batt
    has no queue).
- **Prediction, written before the run:**
  - idle between kills well under v1's;
  - more engagements and kills per hour than v1;
  - queue hit-through above 70 %;
  - the bar's rate unchanged within noise (the strike is v1's).
- ➡️ **Attempt 1 (`20261016T114032-demo-hunt-flow2`, 11:40:32-11:46:41) STOPPED by Claude
  after 334 s (Batt 11:46: "why you struck here for long time if char can't move you should be
  click in avalible feild in map"): 0 engagements. Kept, not scored.**
  - The GM stood on a ledge at (199,127). The waypoint's next click point (194,128) showed the
    client's NO-ENTRY cursor. The gate refused it 108 times, correctly, and nothing chose
    another point: v2's waypoint branch lacked the refusal rule that v1 and hunt@N have.
  - A second defect: a stale queue[0] was logged as a "dispatch" on every loop pass (9 in 0.2 s
    for one monster), which would have counted the hit-through wrongly.
  - **Fixed, bug fixes within the version (attempt 2, same design):**
    - a NO-ENTRY read blocks that spot (radius 1) at once, any other refusal after 2; the cells
      leave the area and the stand grid, and the planner re-plans;
    - one dispatch record per candidate.
- ➡️ **Attempt 2 (`20261016T114836-demo-hunt-flow2`, 11:48:36-12:19:41, the full 30-minute box):
  THE BAR 8 / 8 = 100 % (Wilson 67.6-100 %); n is far below 60.**
  - **Beside it (bot vs Batt):**
    - first click lands 13 / 13;
    - kills 13 = 26.0 / h (v1 40.3; Batt 300);
    - seen -> click p50 16.9 / p90 29.7 s (Batt 1.11);
    - click -> hit 0.64 / 1.33 s;
    - in sight 10.3 / 10 min (Batt 44);
    - idle 79.8 % (Batt 45.9);
    - walk clicks 12.0 / min;
    - death -> next click 5.35 / 7.71 s (v1 6.68; Batt 1.24);
    - **queue hit-through 76 / 118 = 64 %**.
  - **The prediction:**
    - idle between kills fell, but not "well under" (5.35 vs 6.68 s);
    - FEWER engagements and kills than v1 (8 vs 11);
    - hit-through 64 %, under the predicted 70 %;
    - the bar unchanged. **Mostly FAILED.**
  - **Time split:** searching 1,187 s (66 %), steering 422 s, striking 141 s, checks 48 s.
    Coverage 37.5k cells (v1 26k).
  - **Safety (packets):** NPC contacts 0, dialogs 0, non-target hits 0.
    - The 2 map changes are our own `@warp`s BEFORE the loop: this attempt's start, and attempt
      1's start (the packet window's anchor).
    - **Unintended attack requests 5**, all target species (3 after map+units walk clicks, 2
      after cursor-gated ones).
  - 5 spots were blocked by the no-entry rule. No stall.
- **Why speed did not move (v1 and v2):** IDLE ~80 %.
  - Only ~1 walk click in 4 goes out WHILE walking. The map+units gate wants a detector frame
    <= 0.4 s old, but the detector gives a frame every ~0.32 s with ~0.3 s of latency, so the
    newest frame is usually older.
  - So the next click is refused, the walk ends, and the GM stands. Each restart then costs a
    cursor read (~1.2 s) several times per target.
  - Batt re-clicks 6 cells ahead every ~0.6 s and his walks never end (73 % of his clicks are
    sent while walking).

### 3.43 hunt-flow@3: CONTINUOUS WALKING THAT HOLDS (pre-registered 2026-10-16 12:22 ICT, the commit time f6c50b8, BEFORE its run)

The top time-loser of v1 and v2 is idle time (~80 %). Its cause is the walk gate's freshness, and
the top safety item is the same gate (15 walk clicks turned attacks across the two runs).
- **MAIN, one change: the walk gate while moving.**
  - The detector part accepts frames <= 1.0 s old (was the last 2 frames <= 0.4 s): no unit box
    within 60 px of the point on any frame of that second.
  - It ADDS a tracked-monster part (`hunt_flow.track_clear`): no tracked monster's predicted
    drawing position, now, in 0.5 s and in 1.0 s, within 60 px of the point. Tracks outlive a
    detector miss (a canopy) and carry the walking direction.
  - The same tracked part is applied BEFORE a cursor-gated (standstill) walk click.
  - Legs go 8 cells ahead (was 6; Batt's spacing p90 is 9), so a leg lasts long enough for the
    next click to go out before it ends.
  - The gate applies from a standstill too, as a search for the farthest path point that passes
    it.
  - The steer endpoint stops 3 cells short of the target (was 2): with the new tracked part, a
    point 2 cells from the target is within 60 px of it, and from a standstill the bot would retry
    it forever. 3 cells is still inside the strike range.
- Everything else is v2 attempt 2's: the pipeline, the strike, the bar, no looting.
- **Prediction, written before the run:**
  - walk clicks sent while walking: well over v2's ~25 %;
  - idle under 65 %;
  - kills / h above v1's 40.3;
  - unintended attack requests at most 2 per 30 minutes;
  - the bar unchanged.
- ➡️ **hunt-flow@3 run 1 (`20261016T122251-demo-hunt-flow3`, 12:22:51-12:53:58, the full
  30-minute box): THE BAR 12 / 13 = 92.3 % (Wilson 66.7-98.6 %)**; 1 failure: no unit.
  - **Beside it:**
    - first click lands 20 / 22;
    - kills 20 = 40.0 / h;
    - seen -> click 17.8 / 29.8 s;
    - click -> hit 0.58 / 1.22 s;
    - in sight 7.3 / 10 min;
    - idle 73.5 %;
    - walk clicks 14.2 / min, 30 % sent while walking;
    - death -> next click 5.22 / 8.34 s;
    - queue hit-through 89 / 146 = 61 %;
    - 13 engagements, the most of any version.
  - **The prediction:**
    - walk clicks while walking 30 % (v2 ~25 %): up, not "well over";
    - idle 73.5 %, not under 65 %;
    - kills / h 40.0, not above 40.3;
    - unintended attack requests 8, not <= 2.
    - **FAILED**, except the bar.
  - **Safety (packets, the loop):** NPC contacts 0, dialogs 0, map changes 0, non-target hits 0.
    **Unintended attack requests 8**, all target species: 7 after map+units walk clicks, 1 after
    a cursor-gated one.
  - **Why the new gate did not stop them** (each case read against the packets and the
    detector log):
    - in 7 of 8, the monster the client attacked stood 0-3 cells from the clicked cell;
    - the detector had NO box within 80 px of the click point for the whole second before it;
    - so these are DETECTOR MISSES (under trees, or next to the GM's own sprite), which neither
      the frame nor the track gate can see.
    - Any walk click sent without a cursor read (3.39 deviation (2), option B) carries that risk:
      here ~7 in 84-110 such clicks a run.
  - A bug seen (no stall): right after a kill, the dead monster's track (kept 2 s) was
    re-dispatched from the queue until the planner refreshed: 494 `target_dropped` records,
    ~0.1 s a kill. The SWORD read gates every strike, so nothing was clicked. Fixed for the next
    version (finished tracks and dropped spots are never dispatched).

### 3.44 hunt-flow@4: STRIKE A STANDING TARGET FROM <= 7 CELLS (pre-registered 2026-10-16 12:56 ICT, the commit time 59ff567, BEFORE its run; Batt's choice 12:56)

- **Batt's choice (AskUserQuestion, 12:56): "Strike from <= 7 cells".** The options were:
  - strike from <= 7 cells;
  - keep <= 3 and fix target churn;
  - safety first, with no walk clicks without a cursor read.
- **Why:**
  - v1-v3 spent most time walking up to targets in short legs; seen -> click was 9-18 s against
    Batt's 1.1 s;
  - their walk clicks next to monsters became 5-10 attacks a run without a SWORD read (detector
    misses, 3.43's result);
  - Batt's own play (3.40.1): every click that resolved to a unit landed, at every range 1-8+
    (p50 4, p90 7), at ~0.15 s of walk-in a cell.
- **MAIN, one change:** a STANDING target (no displacement over 0.4-1.5 s beyond a cell's noise)
  is struck from <= 7 cells, and the client walks in by itself. A WALKING target keeps <= 3
  (Batt's misses were on walking ones).
- **Bug fix:** a finished engagement's track, and a dropped target's spot (15 s), are never
  dispatched again (3.43's re-dispatch spam).
- Everything else is v3's: the pipeline, the walk gate, legs of 8, steering 3 short, the strike's
  single SWORD read, no looting, the bar (3.41).
- **Prediction, written before the run:**
  - seen -> click p50 under 8 s;
  - steering time under half of v3's 528 s;
  - kills / h above 60;
  - unintended attack requests under 5;
  - range at the click p50 >= 4;
  - the bar >= 90 %.
- ➡️ **hunt-flow@4 run 1 (`20261016T125731-demo-hunt-flow4`, 12:57:31-13:18): STOPPED BY ITS UI
  CHECK after 18.3 min.** The client showed the Skill Tree.
  - **The cause, understood:** the GM had reached Job Lv 2 from its kills, so the client drew its
    skill-point "up" icon at the bottom-left. A map+units walk click at client (9.5, 713.8)
    landed on it, because the static UI exclusion (`route_preview.UI_WINDOWS`) did not hold the
    client's corner NOTICE icons.
  - The run stopped as designed (only a clear UI may continue). The Skill Tree was closed by its
    known chord, and the hunt-flow state restored (Job Lv 2 -> 1).
  - **Fixed:** `UI_WINDOWS` / `work_zone.WINDOW_NAMES` gain `notice_left` (0,668)-(50,720) and
    `notice_right` (1228,668)-(1280,720), the level-up icon of `gm_state.ICON_BOX`. Every runner
    uses this mask.
  - Also seen: 1 pickup, a walk click on a floor item.
  - **THE BAR 10 / 12 = 83.3 % (Wilson 55.2-95.3 %).** Both failures are `no_unit`, yet each
    landed a hit on the unit the client attacked (0.17 s and 0.6 s after the click). What
    failed was the bot's own cell estimate:
    - one predicted cell was 4 cells from the attacked unit (the definition allows 3);
    - in the other, the bot believed it stood ~18 cells from where it was.
    - So POSITION TRACKING, not the strike.
  - **Beside it:**
    - seen -> click **3.33 / 6.53 s** (v3 17.8; Batt 1.11 / 4.79);
    - death -> next click 3.35 / 5.44 s;
    - engagements 12 in 18.3 min (~39 / h; v3 ~26 / h);
    - kills / h 39.3, every kill now from an engagement;
    - range at the click p50 4 / p90 7 (Batt 4 / 7);
    - idle 70.9 %; walk clicks 14.5 / min, 38 % while walking;
    - hit-through 61 %.
  - **The prediction:**
    - seen -> click under 8 s: MET;
    - range p50 >= 4: MET;
    - unintended attack requests under 5: MET (0);
    - kills / h above 60: not met;
    - steering under half of v3's: not met (~385 s per 30 min);
    - the bar >= 90 %: not met (n 12, both failures position estimates).
  - **Safety (packets, the loop):** NPC contacts 0, dialogs 0, map changes 0, non-target hits 0,
    unintended attack requests 0. The UI stop above is the run's one safety stop.

### 3.45 hunt-flow@5: CONTINUOUS MOVEMENT (pre-registered 2026-10-16 13:34 ICT, the commit time 05edb79, after v4's result, BEFORE its run; Batt ~13:10)

Batt: "the GM still walks, STOPS, then gets the next click. Make movement continuous, as in his
demo (73 % of his walk clicks were sent while still walking, one every ~0.6 s, ~6 cells ahead).
The GM stops ONLY to attack and to pick up."

**ONE main change, continuous movement:**
1. **THE MOVEMENT QUEUE:**
   - the planner's coverage route (client ∩ server stand cells, the search area) is re-planned
     before fewer than 10 cells remain, so the GM never reaches its end;
   - every 0.6 s WHILE THE GM WALKS, a click goes to the route point ~6 cells ahead of its
     MEASURED position.
2. **MEASURED, NOT RECKONED:**
   - the position is the minimap's last cell (read every 0.3 s) plus route_preview's floor
     odometry since that read (the floor patches' camera move, at ~10 Hz on the frames);
   - "moving" means the odometry moved more than 0.15 cells in 0.3 s.
   - Evidence: route_preview's own validation (2026-10-08) was 0.12 cell a step; today, on
     v3's 5 Hz JPEG recording, rest to rest, a median of 0.52 cells (68 % within 1; n 19).
3. **NEVER STOP TO CHECK:**
   - the candidates 6, 5, 7, 4, 8, 3 cells ahead are tried at once on the freshest frames:
     in view, off the UI (now with the corner notices), on the route's grid, no unit box within
     60 px on the last second of frames, no tracked monster predicted there over the next
     second;
   - a spot the client refused twice is skipped;
   - only when none passes for 1 s does the GM stop, and that click is cursor-gated (robust2,
     as before);
   - a click the client did not follow (no motion 1.2 s later) counts as a refusal of that spot;
   - the target branch steers the same way.
4. **TARGETS INTERRUPT:** v2-v4's pipeline, the queue, the strike (standing <= 7, walking <= 3,
   ONE SWORD read), no looting. After a kill the movement queue resumes at once.
5. **THE FAST CURSOR READ ON THE WAY: SHADOW ONLY, not a gate.** It is not proven. Evidence:
   - LIVE 13:24, moves only: the client DOES draw its cursor during continuous travel, ~0.15-0.2
     s behind the pointer;
   - but a background-free reader (a colour mask + robust2's matcher) agreed with robust2's
     labelled reads on only 62 / 200 recorded frames (5 Hz JPEG), and read 2 SWORDs as WALK.
   - So v5 logs that read at every walk click (`shadow_read`, ~0.2 s after it), to be validated
     against the packets (did the click become an attack?), and never decides with it.
- **Measured beside the bar (bot vs Batt):**
  - walk clicks sent while moving (Batt 73 %);
  - walk-click interval p50 (Batt 0.6 s);
  - the MOVING SHARE OF SEARCH TIME (the runner's `mode` windows vs the packets' motion;
    target >= 90 %);
  - monsters in sight / 10 min (Batt 44);
  - kills / h (Batt 300);
  - unintended attack requests;
  - plus 3.41's table.
- **Prediction, written before the run:**
  - walk clicks while moving >= 60 %;
  - search moving share >= 80 %;
  - in sight >= 15 / 10 min;
  - kills / h above 60;
  - unintended attack requests at most 5 (more clicks while walking raise the detector-miss
    risk, 3.43);
  - the bar >= 90 %.
- ➡️ **hunt-flow@5 run 1 (`20261016T133443-demo-hunt-flow5`, 13:34:43-14:05:57, the full
  30-minute box): THE BAR 28 / 30 = 93.3 % (Wilson 78.7-98.2 %).** Failures: 1 no unit, 1 never
  hit. **30 engagements**, more than twice any earlier version.
  - **Beside it (Batt in parentheses):**
    - first click lands 46 / 53;
    - kills 47 = 94.0 / h (300). Only 30 are from engagements, so 60 / h; the rest followed
      unintended attacks (below);
    - seen -> click 7.51 / 29.4 s (1.11 / 4.79);
    - click -> hit 0.70 / 1.19 s;
    - **in sight 22.7 / 10 min** (44);
    - **idle 52.5 %** (45.9);
    - **walk clicks 32.8 / min, 63.2 % sent while walking** (44, 72.7 %), interval p50 0.95 s
      (0.6);
    - **death -> next click 1.75 / 6.33 s** (1.24 / 1.80);
    - moving share of SEARCH time 57 %;
    - range at the click p50 4 / p90 6;
    - hit-through 58 %;
    - coverage 69.7k cells.
  - **The prediction:**
    - walk clicks while walking >= 60 %: MET;
    - in sight >= 15: MET;
    - kills / h above 60: MET (94; 60 from engagements alone);
    - the bar >= 90 %: MET;
    - search moving share >= 80 %: NOT MET (57 %);
    - unintended attack requests <= 5: NOT MET (**19**).
  - **Safety (packets, the loop):** NPC contacts 0, dialogs 0, map changes 0, non-target hits 0.
    - **Unintended attack requests 19**, all target species: about 1 in 50 of the 983 walk
      clicks sent without a cursor read became an attack (3.43's detector misses, at a higher
      click rate).
    - 2 pickups from walk clicks.
  - **The shadow cursor read:** 1,457 of 1,458 reads were `unknown`. The colour-mask reader does
    not work on live frames either; it stays out of every decision.
- **hunt-flow@5 ATTEMPT 2 (pre-registered 2026-10-16 ~14:20 ICT, before its runs): bug fixes within
  the version, against 3.45's own text.** The strike, the queue, the gates and the bar are
  unchanged, so its runs pool with runs 1-2 for the bar.
  - **A STALL guard.** Run 1 sat **255 s** at (75,86) sending walk clicks to (70,90)/(71,90)
    every 0.6-1 s that the client ignored. The unfollowed-click guard waited 1.2 s after the
    LAST click, and every new click reset it; run 2 shows the same pattern (a 29-click streak).
    Now: clicks going out while the MEASURED cell has not changed for 2 s block those cells and
    re-plan the route.
  - **The UI check in the background.** It blocked the executor ~2 s every 30 s, which went
    against "never stop to check". It now runs on its own frames (the gate's pixel check with
    park=False, no input, plus the HP check), and any verdict but clear stops the run as before.
  - **The route preview published again.** v2-v5 sent no route line; the pre-registration says
    the route preview is ON.
  - In run 1, 303 s of the 420 s of idle time in search came from 6 stalls of >= 3 s; the 255 s
    one was this bug.
- ➡️ **hunt-flow@5 run 2 (`20261016T140731-demo-hunt-flow5`, 14:07:31-14:38:41, the full box;
  the run-1 code): THE BAR 20 / 22 = 90.9 %**; failures: 1 never hit, 1 hit late.
  - 22 engagements; 72.0 kills / h;
  - unintended attack requests 16;
  - walk clicks 65.2 % sent while walking; search moving 47.6 %;
  - seen -> click 5.55 / 15.2 s; death -> next click 2.37 / 7.34 s; idle 56.6 %.
  - It shows the same stall pattern (a 29-click same-spot streak).
  - **v5 POOLED (runs 1 + 2): 48 / 52 = 92.3 % (Wilson 81.8-97.0 %).** Under 60 engagements, so
    no verdict.
  - The clip of run 1's densest 3.25 min (from 23:00; HUD on; no route line, the gap fixed in
    attempt 2) was sent to Batt: `hunt-flow5-best-3min-phone.mp4` (/dev/shm, local).

### 3.46 hunt-flow@6: ENGAGE LIKE A PLAYER, AND LOOT (pre-registered 2026-10-16 14:42 ICT, the commit time 0c386fa, BEFORE its run; Batt 14:40 + 14:39)

**Batt (14:40):** "walking is much better, but the ENGAGEMENT still stops and misses. In the frames
a Poring stays 2-5 cells from the GM for ~27 s while the cursor sits 30-60 px off its sprite
(right, left, below), and the GM stops/starts near it. It's aiming error, not detection."
**Batt (14:39):** "when you kill monster please wait for check item drop before continue next
queue; if you walk after kill you will can't keep item drop".

On v5 attempt 2 (its fixes included), the changes:
1. **TARGET CONTINUITY:** perception places every box with our MEASURED position at THAT FRAME'S
   time (the minimap anchor plus the floor odometry then), in fractional cells, so a monster
   keeps its identity and a true velocity while the camera scrolls. The prepared continuity
   re-acquire is on (a dropped track's nearest new track within 3 cells carries it on).
2. **THE POINTER FOLLOWS THE TARGET:** once chosen, the pointer moves to the target's sprite
   centre on every fresh frame (<= 0.4 s; the latest box, no extrapolation).
   - **The SWORD read still needs a still scene**: robust2 is the only proven reader, and both
     background-free readers failed today (62 / 200; 0 / 1,453).
   - So at the GM's natural stop within range comes a SHORT read: a park blink for the
     background, the pointer back in 6 small moves (the client draws its cursor during
     continuous travel, ~0.15-0.2 s behind: 13:24's test), a 0.25 s settle, robust2, and the
     click at once. Anything but SWORD gets the standard hover and one more read.
3. **THE ATTACK CLICK IS THE APPROACH:** standing targets from <= 7 cells, walking <= 3 (v4).
4. **LOOT AFTER EACH KILL:** the death cell from the target's own boxes on the sampler's frames
   (loot@1's `death_of`), then loot@1's PICKUP scan and clicks (`loot1.loot`), before the next
   target. Weight above 40 % is cleared between engagements (the weight rule).
- **Measured, per attack attempt:** the AIM ERROR (the click point to the target's sprite centre
  on the freshest frame, px), the time from "in range" to the click, the read time.
- **Beside the bar:** first-click lands, hit within W, kills / h, pickups per kill, stops, the
  bot-vs-Batt table.
- **Prediction, written before the run:**
  - aim error p50 under 15 px;
  - in range -> click p50 under 1.5 s;
  - the bar >= 90 %;
  - pickups per kill > 0.5;
  - kills / h above v5 run 2's 72, by engagements alone above 50 (looting costs time);
  - unintended attack requests not above v5's (16-19).

**Run 1 RESULT (2026-10-16 14:43:21-15:13:21, session 20261016T144321-demo-hunt-flow6, seed
20261208; judged 15:16, `flow_judge.py bot`):**
- **Engagements:** 20, all dead.
  - The bar (hit within 5 s of the first click): 17 / 20 = 85.0 % (Wilson 64.0-94.8).
  - First click lands: 54 / 62.
- **Kills: 112.7 / h, but 37 of the 56 kills were NOT from engagements.**
  - They came from walk clicks the client turned into attacks (no SWORD read): 39 unintended
    attack requests, against 16-19 in v5.
  - Engaged kills: 19, which is **38 / h**.
- **Timing:**
  - seen -> click p50 6.3 s (Batt 1.11);
  - in range -> click p50 3.56 / p90 7.84 s;
  - read time p50 1.9 s (the short read, then usually the fallback);
  - aim error p50 6.9 / p90 38.6 px;
  - death -> next click p50 3.57 s (Batt 1.24).
- **Lost targets** (target_lost 191, 6.4 / min; v5 run 1: 6.8) took 666 s, 37 % of the run. The
  re-acquire carried 134 on. no_path dropped 63, no_sword 10.
- **Movement:**
  - moving share of search 80 % (v5 48-57 %);
  - walk clicks while moving 61.9 %;
  - interval p50 0.96 s.
- **Moving walk clicks within 1 cell of the cell meant: 31 / 639 = 5 %**, along the motion
  +3.54 cells. The lag below is unchanged: v6 fixed the perception side, not the clicks.
- **Loot:** 0.07 pickups per kill. The death-cell step rarely found the cell; 39 s in total.
- **Safety:** no stop, no NPC or dialog, HP intact. The unintended attacks above are the open
  safety cost.
- **vs the prediction:**
  - aim error p50 under 15 px: YES (6.9);
  - in range -> click under 1.5 s: NO (3.56);
  - the bar >= 90 %: NO (85.0);
  - pickups per kill > 0.5: NO (0.07);
  - kills / h above 72: YES (112.7), but by engagements alone above 50: NO (38);
  - unintended attacks not above v5's: NO (39).
- **Top loser:** the ~0.5 s position lag (3.47). It costs both the lost / overshot approaches and
  the unintended attacks. The slow strike read (in range -> click 3.56 s) comes next.

### 3.47 hunt-flow@7: LEAD-COMPENSATED WALK CLICKS (pre-registered 2026-10-16 15:17 ICT, the commit time 65681b1, BEFORE its run; Batt 15:00)

**Batt (15:00):** "Build and pre-register the next hunt-flow version with the two changes already
asked: target continuity via the measured floor motion, and MOUSE FOLLOWS THE TARGET (pointer on
the sprite every fresh frame during the approach, click the instant SWORD is read within range, no
dwell stop). Continuous walking stays as is. Then run LONG sessions back to back (60-90 min each,
fresh seeds, GM immune + high STR, no looting, natural spawns on prt_fild08), iterating one main
change at a time on the top loser, until Batt says stop." Also a **GPU FREEZE** (Batt is testing
another model): nothing of ours on the GPU; the detector stays ONNX on the CPU, niced.

**Both changes are already in v6 (3.46).** v6 run 1's result above and the measurement below show
what still breaks them: the position the runner measures LAGS the GM.

**Measured 2026-10-16 15:00-15:08** on v5's banked packets and frames (scratch analyses, no run):
- **Walk clicks while moving land ~3 cells beyond the cell meant.**
  - Moving: p50 3 cells off (p90 4); only 4-6 % within 1 cell. v4's reckoning had 52 %.
  - Standing: p50 2; 48 % within 1. v4 had 81 %.
- **The error lies ALONG the GM's motion:** p50 +3.0 / +3.5 cells AHEAD (p10 +2, p90 +5), and
  ~0 across.
- **Per click, it is a LAG:** the along error divided by the GM's speed is p50 0.50 s (IQR
  0.40-0.60, n = 1,074 moving clicks, both v5 runs).
- **Its source: the frames show the GM ~0.45 s behind the server's walk.**
  - A walk start reaches the frames p50 434 ms after the server's move.
  - The minimap readout lags the server the same way: the best fit is 450-500 ms, mean error 0.50
    cell (2.1 at 0 lag).
  - So the measured position (minimap + floor odometry, both read from frames) agrees with the
    frames, and perception may track in that "frame time".
  - But it is BEHIND where the client walks the GM when a click lands, and the client resolves a
    click from where the GM really is.
- **Consequences in v5/v6:**
  - Every continuous walk click went ~3 cells beyond where it was meant.
  - The cell the client actually took was one the unit gate never checked. That fits the
    unintended attacks (~1 in 50 walk clicks) and the unfollowed clicks.
  - Approaches overshoot.
- **Lost targets were association, not detection.** In 177 of v5 run 1's 205 lost targets, the
  detector had monster boxes on the frames of the 2 s before the loss.

**The ONE main change:**
- Each continuous walk click is projected from where the client will resolve it: the measured
  position + the measured floor velocity (the odometry's newest 0.3 s) x 0.50 s.
  - It is fractional: the camera sits on a fractional cell (`frac_project`).
  - The ahead candidates (6,5,7,4,8,3) count from there.
- The unit-clearance gate keeps the frame's own pixel of the same cell, because the boxes are in
  frame time.
- Standing (velocity 0) changes nothing.

**Also in this version:**
- **NO looting** (Batt 15:00): a test condition, not a design change. v6's PICKUP step is off;
  the weight rule stays at restore.
- **A map-change stop** (Batt: stop on any map change). Two agreeing minimap reads more than 12
  cells from the measured position stop the run as a map change or a warp. A minimap read off
  the grid no longer raises.
- **Logged per walk click:** the measured cell and the lead (cells), so the lead can be checked
  after the run.
- **New judge columns** (`flow_judge.py`, tested):
  - moving walk clicks within 1 cell, with the along error p50;
  - stops per engagement: the GM came to a standstill inside the steer / engaged windows.

**Run:**
- 60 min on prt_fild08, natural spawns;
- a fresh seed;
- GM immune, Lv 70 / STR 99;
- `nice -n 10`, detector on the CPU.

**Prediction, written before the run:**
- moving walk clicks within 1 cell >= 40 % (v5 4-6 %), with the along error p50 within +-1 cell
  (v5 +3.0 / +3.5);
- unintended attack requests per 30 min below v5's 16-19 and below v6 run 1's 39;
- lost targets per minute below v6 run 1's 6.4;
- ENGAGED kills / h (kills by a SWORD-read engagement) above v6 run 1's 38. TOTAL kills / h may
  FALL below v6's 112.7: two thirds of v6's kills were unintended walk-click attacks, which this
  change removes;
- the bar (hit within 5 s of the first click) >= 90 %;
- stops per engagement not above v6 run 1's 24.9.

**Attempt 1 (2026-10-16 15:18:46-15:23:27, session 20261016T151846-demo-hunt-flow7, seed
20261209): STOPPED at 4.1 min by me, on a mid-run check.**
- **The check:** the sniffer's archive read-only, against the per-click `at` / `lead` the run
  logged.
- **The defect: the velocity lead pointed along the OLD direction.**
  - Along the motion, the lead was p50 +0.5 cells, against a lag of +3.8; some leads pointed
    backwards.
  - Moving clicks within 1 cell rose only to 22 %, still +2.8 cells ahead.
  - The cause: the frames show the motion of ~0.5 s ago, and each walk click turns the GM, so
    the new direction is not in any frame yet.
- **Result:** 3 engagements, all dead.

**Measured on attempt 1's packets (133 walk clicks with the logged `at` and lead):**
- The client's cell when a click arrives is the SERVER's cell at the click time: 95 % within 1.
- The measured cell is the server's cell ~0.6 s earlier: 83 % within 1 at 0.6 s, 81 % at 0.5,
  14 % at 0.
- Replaying the walk destinations from the measured cell over the last L s (8 directions, 150 ms
  a cell, x1.4 diagonal):
  - at L = 0.6: within 1 cell 68 %, within 2 89 %, along error 0.00;
  - at L = 0.5: 67 %, along +0.60;
  - at L = 0: 14 %, along +3.84.
  - These runs used the ACTUAL destinations, read offline. Live, the cells we click ARE the
    destinations once the clicks land.

**Attempt 2 (recorded 2026-10-16 15:26, the commit time 7f13bfb, before its run; the same main change, a different
estimator):**
- The lead is OUR OWN commands, replayed from the measured cell over the last 0.6 s:
  `commanded_lead`, with walk clicks plus attack clicks (the client walks toward the monster).
- This is a reckoning of only the latency gap, which no frame can show yet. The measured cell
  remains the anchor, so nothing accumulates.
- Everything else is as pre-registered: no looting, the map-change stop, the predictions. The
  1-cell bar of >= 40 % stands; the offline ceiling is ~68 %.
- 60 min, seed 20261210.

**Attempt 2 RESULT (2026-10-16 15:26:57-16:18:59, session 20261016T152657-demo-hunt-flow7, seed
20261210; judged 16:20).**
- **Stopped by me at 51.5 min.** From +38.8 min it had sat idle for 12.7 min on a ledge strip
  near (97,144), where no goal had a path from the GM's cell; the pipelined loop had no
  no-progress guard. The judge's window ends at the last click (38.9 min).
- **THE CHANGE WORKED: moving walk clicks within 1 cell 588 / 752 = 78 %**, along the motion
  +0.0 (v6: 5 %, +3.54). Standing: 77 %.
- **The bar:** 29 / 32 = 90.6 % (Wilson 75.8-96.8). First click lands 54 / 61.
- **Kills:**
  - engagements 32, all dead;
  - engaged kills 47.9 / h (v6 38.2);
  - kills / h 80.3 in all, with 21 other kills;
  - unintended attack requests 25 (v6 39; v5 16-19 per 30 min).
- **Timing:**
  - seen -> click p50 11.85 s (Batt 1.11);
  - in range -> click p50 6.74 / p90 17.16 s;
  - read p50 1.85 s;
  - aim error p50 1.5 / p90 32.1 px;
  - death -> next click p50 2.05 s (Batt 1.24).
- **Movement:**
  - monsters in sight 12.4 / 10 min in the judged window; the packet funnel over the full run
    counts 115 lives in view, 22 / 10 min;
  - moving share of search 74 %;
  - walk clicks while moving 57.9 %, interval p50 0.96 s.
- **Split:** searching 1,589 s (762 of them the stuck end), striking 777 s, steering 721 s.
- **Striking was the largest fixable sink.**
  - 17 targets were dropped after 3 failed reads, each read behind a park that waits up to 1.5 s
    for the drawn cursor.
  - A stale park returns without counting a read, so it parks again.
- **Funnel** (packets, every monster life in view):
  - killed by an engagement 26 % (v6 15 %);
  - killed by a walk click 19 % (v6 28 %);
  - dispatched then dropped 23 %;
  - never dispatched (in view p50 2 s) 28 %.
- **The 22 unintended kills:** 19 were STEERING clicks that landed within 1-3 cells of the target
  (14 within 1; perception's monster cell is p50 1.3 cells off), and 3 were search clicks.
- **Also:**
  - 2 floor items were picked up by walk clicks (looting is off): a Carrot and a Jellopy.
  - The chat showed "Your participation is appreciated." No npc_* packet appears in the run.
  - The job level rose 1 -> 4 from the kills; the restore resets it.
- **Safety:** no NPC contact, no dialog, no map change after the start warp, HP intact.
  - ➡️ **CORRECTED 2026-10-16 ~18:50:** the run DID hit a NON-TARGET.
    - A Creamy (1018) took hits at +1,248 s and +2,015 s, both from WALK clicks the client turned
      into attacks: one search click, one steer click.
    - The judge had no non-target count then. `flow_judge.hard_bars` (3.52) finds it.
    - The same cause recurred in hunt-flow@10 attempt 2. The fix is v11's walk-click safety
      amendment (3.53).
- **vs the prediction:**
  - moving clicks within 1 cell >= 40 %: YES (78 %);
  - along error within +-1: YES (0.0);
  - unintended attacks per 30 min below v5's and v6's: NO (19 per 30 min = v5's);
  - lost targets below v6's: YES, 205 in 38.8 min = 5.3 / min vs 6.4;
  - engaged kills / h above 38: YES (47.9);
  - the bar >= 90 %: YES (90.6);
  - stops per engagement not above v6's 24.9: YES (16.5).
- **Bug fixes for the next version (63529b6):**
  - the stuck-search ESCAPE: with no goal path for 3 s, walk the full walkable grid to the main
    component of the search area;
  - a no-progress stop in the pipelined loop (60 s).

### 3.48 fast-read@1: the FAST cursor read vs the proven one, no clicks (pre-registered 2026-10-16 15:46 ICT, the commit time 162aea0, BEFORE it runs)

**Why.** In hunt-flow@6 the proven cursor gate (Prober9 + robust2) cost p50 3.56 s between "in
range" and the attack click. Most of that is its PARK:
- two motions to the far right;
- 0.3 s;
- up to 1.5 s for the drawn cursor to show there;
- a second frame 0.25 s later;
- then the hover, 0.55 s, and a further park after the click.

Batt (15:00): "click the instant SWORD is read within range, no dwell stop".

**The candidate (`scripts/fast_read.py`).** The pointer is already on the target (hunt-flow's
pointer follows it), so:
1. Grab A, with the cursor drawn there; the pointer has rested >= 0.25 s.
2. Blink the pointer 90 px away in 4 small moves, to a point >= 70 px from every unit box.
3. Grab B1 0.25 s later and B2 0.12 s after that.
4. Run robust2's match, with its own floors and margins, on |A - B2| minus the pixels that
   changed between B1 and B2 (animation).

It is valid only if the cursor LEFT the target: a cursor-sized |A - B2|, the park's own
60-1,200 px test. Otherwise the read is "unknown".

**The check (`fast_read.py check --npc`; NO clicks, pointer moves and one typed @warp through the
UI gate).** On prt_fild08 with the immune GM:
- every target is read the FAST way, then the PROVEN way (park, hover, read);
- STANDING monsters: a box that moved <= 6 px over 0.3 s; a pair is excluded when the monster
  moved off its spot by the end;
- GROUND points: no box within 100 px;
- the Poring War Recruiter NPC (159,371, Poring-looking): reached by @warp to a legal stand cell
  ~5 south (outside warp spans and touch areas), and read 5 times on its sprite.

**PASS rule (written before it runs):**
- **Zero false SWORD:** never fast = SWORD where the proven read is not SWORD.
- **At least 10 proven-SWORD monster reads**, and fast = SWORD on >= 80 % of them.
- **The NPC never reads SWORD** the fast way.

The read times (fast vs proven, p50) are reported beside the rule.

**Use.**
- PASS: hunt-flow@8's strike reads the fast way, and any "unknown" falls back to the proven read
  in the same call (so a fast read never decides alone in doubt). The parks before and after the
  click go.
- FAIL: the fast read gates nothing. hunt-flow@8 takes the next loser instead.

**fast-read@1 RESULT (2026-10-16 16:22:02-16:23:48, `data/fast_read/check-20261016T162202.jsonl`):
FAIL. The fast read gates nothing.**
- 18 comparisons. Stopped by me once the rule could not be met.
- **Every fast read was "unknown":** "cursor not left", |A - B2| = 0 px at the target in 16 of
  18. The client had NOT drawn its cursor on the target 0.25 s after the glide.
  - This agrees with walk@6's measurement: the drawn cursor appears 0.41-0.82 s after the last
    motion (HOVER6_S 0.55).
  - The "~0.15-0.2 s behind during continuous travel" of 13:24 does not hold for a stop.
- **No SWORD on either side.** The proven read on the "standing" monsters was unknown or walk:
  the monsters wandered off during the ~2.5 s pair, 4 of 6 flagged as moved.
- **Times:** fast 0.66 s vs proven 1.93 s, p50.
- **What it teaches:** a fast read needs ~0.6 s of pointer rest before A and ~0.8 s after the
  blink. That is ~1.5 s against the proven read's ~1.9 s, a small gain. The waste around the
  proven read is the bigger one (3.49).

### 3.49 hunt-flow@8: LEAN STRIKE (pre-registered 2026-10-16 16:24 ICT, the commit time e5d7ae9, BEFORE its run)

**From v7 attempt 2:** striking was 777 s, 33 % of the judged run, and in range -> click was
p50 6.74 s, with read time only p50 1.85 s. The rest was waste around the proven read.
- **A park after EVERY attack click** (~1-1.8 s) whose background nothing used. The next read
  always parks first.
- **A STALE park returned without counting a read.** A stale park is one where the drawn cursor
  never showed at the park point within 1.5 s. The loop called the strike again at once and
  parked again, with no bound. 777 s over ~84 strike calls is ~9 s a call.

**The ONE main change (`strike_lean`):**
- no park after the attack click;
- a stale park counts as a failed read, so 3 of them drop the target like any no_sword;
- every strike call is logged as `strike_call`, with its read, park time and call time.

**Also in (bug fixes from v7 attempt 2, 63529b6):**
- **the stuck-search ESCAPE:** when no goal has had a path for 3 s, walk the full walkable grid
  to the nearest cells of the search area's main component;
- **a no-progress stop** in the pipelined loop: 60 s without a click outside an engagement.
- Everything else is v7 attempt 2: the commanded-path lead, no looting, the map-change stop.

**Run:** 60 min, seed 20261211, prt_fild08, GM immune Lv 70 / STR 99, nice 10, detector on the
CPU (GPU freeze).

**Prediction, written before the run:**
- in range -> click p50 under 4.0 s (v7 6.74);
- striking under 20 % of the run (v7 33 %);
- engaged kills / h above v7's 47.9;
- the bar (hit within 5 s) >= 90 %;
- unintended attacks not above v7's (19 per 30 min);
- no idle stretch over 60 s: escape events logged, and the no-progress stop never fires.

**Attempt 1 (2026-10-16 16:25:46-16:37:22, session 20261016T162546-demo-hunt-flow8, seed
20261211): STOPPED BY ITSELF at 11.6 min.** The no-progress stop fired: "no progress for 60 s at
(33,75)".
- **The escape misfired.** It picked (32,74), the nearest main-area cell, 1 step away. The
  cursor read NO-ENTRY there; every other candidate was adjacent too. And the search branch
  only clicks cells inside the search area, so an escape route over the walkable grid could not
  be clicked at all.
- **The lean strike broke death detection.**
  - All 6 engagements ended "dead" 1.0-1.1 s after the first click.
  - The packets judge: 1 hit within 5 s, 2 late, 2 never, 1 excluded. The bar is 1 / 5.
  - Engaged kills 1; 6 more kills came from walk clicks.
  - The park after the click had a HIDDEN job: it moved the pointer off the monster. Without it
    the drawn cursor covered the sprite, the detector lost the monster, and "unseen 0.6 s" fired
    "dead". The bot walked off and the client cancelled the attack.
- **The lean strike's own aim was met:** in range -> click p50 2.89 s (v7 6.74).
- Strike calls: 38 at 10.6 min, 20 of them read WALK. The target was off the pointer by read
  time: the frames lag ~0.5 s, and the park and hover add ~1.6 s.
- Moving walk clicks within 1 cell: 70 %.

**Attempt 2 (recorded 2026-10-16 16:49, the commit time b05f05b, before its run; bug fixes within the version):**
- **After the attack click, the pointer moves ~90 px off the monster at once:** one move, no
  park, no wait.
- **The escape retreats along OUR OWN TRAIL:** the cells we stood on, 6-20 cells away and >= 3 s
  old, most recent first. Then come main-area cells >= 6 away. The escape route is clicked on the
  walkable grid.
- Everything else is as pre-registered. 60 min, seed 20261212.

**Attempt 2 RESULT (2026-10-16 16:50:30-17:12:57, session 20261016T165030-demo-hunt-flow8, seed
20261212): STOPPED BY BATT'S TAKEOVER at 21.7 min.** The runner stopped correctly: "a human
lease is active, nothing sent". Nothing was restarted for the 10-min back-off.
- **The bar:** 7 / 10, with 2 never hit and 1 late.
- **Kills:** engaged 7, 19.4 / h (v7 47.9); 14 more from walk clicks.
- **In range -> click:** p50 4.46 s (v7 6.74).
- **Moving walk clicks within 1 cell:** 79 %.
- **The escape fired once;** no further stall.
- **Death -> next click:** p50 3.21 s.
- **THE STRIKE READ IS THE TOP LOSER.** Of 111 strike calls only 10 read SWORD: 63 unknown, 32
  WALK, 6 pickup. 15 targets were dropped as no_sword, and 10 parks were stale.
  - The lean strike made a strike cheaper (call p50 3.2 s), not more successful.
- **vs the prediction:**
  - in range -> click under 4.0 s: NO (4.46);
  - striking under 20 %: NO (375 of 1,302 s = 29 %);
  - engaged kills / h above 47.9: NO (19.4);
  - the bar >= 90 %: NO (70 %);
  - no idle stretch over 60 s: YES.

### 3.50 hunt-flow@9: STRIKE A STANDING TARGET ONLY (pre-registered 2026-10-16 17:14 ICT, the commit time b975eac, BEFORE its run)

**From v8:** 9 % of strike reads were SWORD.
- The WALK reads (32) are the target having LEFT the aimed spot. The aim comes from a frame
  ~0.5 s old, and the park plus hover add ~1.6 s.
- Porings hop: the 17:00 frames show one 1-2 cells off the pointer at read time.
- Why the unknowns (63) happen is not logged.

**The ONE main change (`still_gate`):**
- **No read until the target STANDS.** Its boxes from the frames of the last 1.2 s (at least 3)
  must all sit within 8 px of the newest. Until then, the pointer keeps following it.
- **A target that never stands within 8 s** is dropped as no_still.
- **After the park,** a newest box more than 8 px off the aimed one calls the read off
  (`strike_moved`; no read is counted, and the gate waits again).
- **Instrumentation:** every read's shape / why / best is logged in `strike_call`, so the
  unknowns can be attributed next.

Everything else is v8 attempt 2: the lean strike, the pointer off after the click, the
commanded-path lead, the trail escape, no looting.

**Run:** 60 min, seed 20261213. It starts only after the takeover back-off, with no human input
for >= 10 min.

**Prediction, written before the run:**
- SWORD on more than 25 % of strike calls (v8: 9 %);
- WALK on fewer than 10 % (v8: 29 %);
- engaged kills / h above v8's 19.4, and at least v7's 47.9 as the goal;
- the bar >= 90 %;
- in range -> click p50 under 6 s (the wait for a stand is in it);
- unintended attacks not above v7's (19 per 30 min).

**Run 1 (2026-10-16 17:23:42-17:29:47, session 20261016T172342-demo-hunt-flow9, seed 20261213):
STOPPED BY ITSELF at 6.1 min by the map-change guard. A FALSE STOP.**
- The guard said "position jump (122.0, 85.9) -> (122, 72)".
- The packets have no map_change after the start warp. The GM really walked north fast, from
  (122,86) to (121,69) in 5 s, past the (122,85) it was clicked to: a slope, where the client
  picks raised tops.
- The floor odometry fell 14 cells behind, and two agreeing minimap reads 14 cells off tripped the
  guard.
- In those 6 min: 1 engagement; 9 strike calls (1 SWORD, 8 unknown).
  - The logged read reasons: no_match 10, no_cursor 4, low_score 3.
  - The unknowns are mostly a mask that matches no cursor prototype, not a missing cursor.
- Drops: no_path 5, no_sword 1, no_still 1.

**Attempt 2 (recorded 2026-10-16 17:35, the commit time 8d4a780, before its run; a bug fix within the version):**
- A position jump re-anchors on the minimap when the minimap PICTURE is still the run's map. The
  picture is compared with the crop taken at the loop start: the median summed |diff| must stay
  <= 20, while the GM arrow moves over ~2 % of it.
- A different picture still stops the run as a map change.
- 60 min, seed 20261214.

**Attempt 2 RESULT (2026-10-16 17:35:42-18:01:03, session 20261016T173542-demo-hunt-flow9, seed
20261214): STOPPED BY ITSELF at 25.3 min, after a CLIENT DISPLAY FREEZE.**
- **The freeze.** From +1,402 s (17:59:04) every recorded frame was pixel-identical (mean diff
  0.0).
  - The game client stopped redrawing, but it still took input. The packets show the GM walking
    on our clicks from (124,84) to (119,40) and back to (126,96).
  - The taskbar clock still updated: the RDP stream was live, only the game picture froze.
  - The bot clicked BLIND on the stale picture for ~60 s until the no-progress stop. Its
    measured cell sat at (124,82).
  - In that window: no attack request, no NPC contact, no map change (packets).
  - /health showed no alarm: the frame bus heart-beats on a still picture.
- **Recovery (18:04-18:06):**
  - `ro_agent.py recover gm --retries 0`: Alt+F4, relaunch, GM login. The client came back with
    the GM at (125,96), the server's cell.
  - Then `collect_v2.py immune-on`; its screenshot read "You are now immune to attacks."; then
    `immune-confirm` (18:06:03).
- **Judged window: 24.4 min, to the freeze.**
  - The bar: 5 / 7.
  - Kills: engaged 5 (12 / h); 22 more from walk clicks (23 unintended attack requests).
  - In range -> click: p50 5.38 s.
  - Seen -> click: p50 7.26 s.
  - Hard bars: 0 / 0 / 0.
- **Strike reads:** 56 calls -> 7 SWORD (12.5 %), 8 WALK (14 %; v8 29 %), 40 unknown, 1 pickup.
  - Per read: no_match 45, no_cursor 38, low_score 13.
  - The standing-target gate halved the WALK reads. The proven read itself fails ~70 % of the
    time in the field (no_match / no_cursor). This favours 3.52's direct clicks.
  - no_still drops: 9; park stale: 9.
- **The "Your participation is appreciated." chat line is explained:** it is the tail of a
  server-wide broadcast, "Currently, the Dungeon Teleport Service Provider Election is being held
  in all major cities." It is not an NPC contact.
- **vs the prediction:**
  - SWORD > 25 %: NO (12.5 %);
  - WALK < 10 %: NO (14 %);
  - engaged kills / h above 19.4: NO (12);
  - the bar >= 90 %: NO (71 %);
  - in range -> click < 6 s: YES (5.38);
  - unintended attacks not above v7's: NO (23 in 24.4 min).

### 3.51 PROPOSAL (design only, awaiting Batt's decision; nothing built): a RISK-BASED cursor gate for hunting attack clicks

**Batt (17:2x):** "REQUIRE the SWORD read when there is real risk ... Otherwise CLICK the fresh
detection directly, like Batt (a miss only walks); verify the hit from pixels and re-click as now.
Report how many attack clicks went each way, and keep zero NPC contacts / non-target hits as hard
bars. Give me the expected effect on seen->click and kills/h from v7/v8's logs before building
it."

**Why.** The client draws its cursor 0.4-0.8 s after the pointer stops (fast-read@1). With the
park, the proven read costs ~3 s a call:
- in range -> click p50 6.6 s in v7 and 4.15 s in v8;
- in v8 only 10 of 111 calls read SWORD;
- striking took 777 s of v7's 2,334 s, and 375 s of v8's 1,302 s.

**The gate (a decision table per attack click).** The read is REQUIRED when any of these holds:
- (a) an L3 NPC within 12 cells of the target's cell (prt_fild08: 159,371 and 175,374; the
  search area already keeps 10 cells off them);
- (b) an ignore-list species in view: on prt_fild08 only Creamy, which the size gate already
  excludes as a target;
- (c) an unclear detection:
  - the target's box intersects another box;
  - or the target is within 45 px of the GM's sprite;
  - or detector confidence < 0.6;
  - or the box was not seen on >= 2 of the last 3 frames (occlusion, canopy);
- (d) any non-hunting workflow, always.

**Otherwise:**
- The attack click goes straight to the target's newest box centre, as soon as the GM stands
  within range. There is no park and no read.
- The hit is verified from pixels (the target's box, then its vanishing) and from the swing,
  with a re-click as now.
- Every attack click is logged with its branch: `direct` or `read`, plus the reason.

**Hard bars** (packets, per run): zero npc_contact, zero non-target hits, zero map changes. Any
one of them stops the run.

**Measured on the logs** (offline, v6 / v7 / v8 attempt 2):
- Risky share of the engaged targets at their click: 16 / 62 = 26 % under the strict rule above
  (near the GM 10, low confidence 7, intersecting 0, NPC 0). A broad rule (another box within
  60 px) gives 33 / 62 = 53 %.
- Seen -> click splits as follows (bot side, v7): seen -> in range p50 ~2.4 s, then in range ->
  click 6.6 s.
- Judge side, v7: 11.85 s. A direct click takes one fresh frame plus the click, ~0.35 s.

**Expected effect (the risky share kept at the read; a direct click lands 80 %, Batt's own
first-click rate):**
- **seen -> click p50:**
  - v7 11.85 s -> ~5.6 s for direct clicks (bot side 8.95 -> ~2.7 s);
  - the run's p50 ~6 s at r = 0.26, and ~7-9 s at r = 0.53. Batt: 1.11 s.
- **Engaged kills / h on v7's basis: 47.9 -> ~64-71.** The direct share saves ~6.2 s an
  engagement, and ~12 no_sword targets become engagements.
- **On v8 attempt 2's basis: 19.3 -> ~40-56.**
- **The rest of the gap to Batt's 300 / h is search and approach,** about two thirds of the time:
  - searching 36 % and steering 31 % of v7;
  - first detection -> dispatch ~2.9 s;
  - seen -> in range ~2.4 s.
  - A gate change does not touch them. A direct click from a MOVING GM at <= 7 cells (aimed with
    the commanded-path lead plus the target's velocity) would be the next step.
- **New risks:**
  - a direct click on a false detection walks;
  - one on a floor item picks it up (looting is off: counted as unintended pickups);
  - both are counted, and neither is a hard bar.

### 3.52 hunt-flow@10: the RISK-BASED cursor gate (pre-registered 2026-10-16 17:39 ICT, the commit time dec80c0, BEFORE its run; Batt approved 3.51's STRICT rule, 2026-10-16 ~17:37)

**Batt:** "Approved: the RISK-BASED cursor gate with the STRICT rule ... Otherwise click the fresh
detection directly. Pre-register it as the next version with your logged branch/reason per attack
click and the hard bars (zero NPC contact, zero non-target hit, zero map change)."

**The ONE main change (`risk_gate`, `gate_reasons` / `gate_risks`).** At every attack click
(first or re-click), the target's box is taken on the FRESHEST frame (<= 0.4 s). The read stays
REQUIRED when any of these holds:
- **intersect:** the box intersects any other box of that frame;
- **near_gm:** its centre is <= 45 px from the GM's sprite centre (client 640,340);
- **low_conf:** detector confidence < 0.6;
- **npc_near:** an L3 NPC (data/kb/npc_cells.json, prt_fild08: 159,371 and 175,374) within 12
  cells of the target's predicted cell;
- **ignore_species:** a Creamy-sized box (the size gate's non-target) within 150 px;
- **stale_box / no_box:** no fresh box of the target;
- (and any non-hunting workflow, which never runs this code).

**Otherwise (`direct`):**
- The attack click goes to the box centre at once: no park, no read.
- The pointer then moves off the sprite (v8 attempt 2).
- The rest is unchanged: the hit is verified from pixels (the box gone = dead), with a re-click
  after 2 s through the same gate.
- v9's standing-target gate stays, as inherited.

**Logged per attack click:** the `branch` (direct / read) and the `risk` reasons, in clicks.jsonl
and strike_call.

**Judge (`flow_judge.py`):**
- `gate` = attack clicks per branch, plus the reason counts;
- `hard_bars` = npc_contact, map_change after the start, and non-target species hit (farm0.TARGETS:
  Poring, Lunatic, Pupa, Drops).

**HARD BARS:** zero NPC contact, zero non-target hit, zero map change. Any one fails the run,
whatever else it shows. A live dialog or a map change also stops the run, as before.

**Amendment (recorded 2026-10-16 18:07, the commit time 9ab4c2d, BEFORE its run; a safety guard, not the main change):**
the FREEZE GUARD. If the game picture stays pixel-identical for > 3 s after a walk click, the run
stops: "the picture froze". A commanded walk always scrolls the camera, so a frozen picture can
only be a frozen client display. The motion thread compares consecutive frames. This came from
v9 attempt 2's blind 60 s.

**Run:** 60 min, a fresh seed, prt_fild08, GM immune Lv 70 / STR 99, no looting, nice 10, detector
on the CPU (GPU freeze).

**Prediction, written before the run (3.51's estimate):**
- direct attack clicks >= 60 % of attack clicks (strict rule: 74 % offline);
- in range -> click p50 under 2 s (v7 6.6, v8 4.15);
- seen -> click p50 under 8 s (v7 11.85);
- engaged kills / h >= 60 (v7 47.9; estimate 64-71);
- the bar (hit within 5 s of the first click) >= 90 %;
- the hard bars: 0 / 0 / 0.

**Attempt 1 (2026-10-16 18:08:03-18:14:47, session 20261016T180803-demo-hunt-flow10, seed
20261215): STOPPED by me at 6.4 min, on a mid-run check.**
- **The gate never went direct:** 15 / 15 strike calls took the read, all for "stale_box".
- The CPU detector delivers a box 0.3-0.65 s after its frame. The target's box age at the strike
  was p50 ~0.52 s (377-3,130 ms), so the 0.4 s freshness limit rejected nearly every box.
- In effect the run was v9: 3 engagements; reads 3 SWORD / 3 WALK / 9 unknown.
- Hard bars 0 / 0 / 0 (live packets).

**Attempt 2 (recorded 2026-10-16 18:15, the commit time 0a515f7, before its run; a bug fix
within the version):** the gate's box may be up to 1.0 s old (`gate_fresh_s`, the dispatch
freshness). v9's stand gate already holds the target still over the last 1.2 s, so a <= 1 s box
is where it stands. 60 min, seed 20261216.

**Attempt 2 RESULT (2026-10-16 18:16:16-19:16:16, session 20261016T181616-demo-hunt-flow10, seed
20261216; the full hour; judged 19:18):**
- **THE GATE WORKED.** Attack clicks: 127 direct / 4 read. The reasons on the reads: intersect 2,
  low_conf 2.
- **Kills:**
  - engagements 131, all dead;
  - engaged kills 99.9 / h (v7 47.9, v9 12.3);
  - kills / h 135.9 in all.
- **Timing:**
  - seen -> click p50 5.14 / p90 13.17 s (v7 11.85);
  - in range -> click p50 0.66 s (v7 6.74);
  - death -> next click p50 0.94 s (Batt 1.24).
- **Split:** striking 168 s (5 %, from ~30 %), steering 1,843 s (51 %), searching 1,496 s (42 %).
- **The bar:** 93 / 131 = 71.0 % (Wilson 62.7-78.1). First click lands 139 / 193 = 72 %.
  - Of the 38 misses: 23 hit LATE (the 2-s re-click after a direct click that only walked onto
    a hopping sprite), 11 found no unit, 4 never hit.
  - Trial why: walk_only 27, no_unit 21, request_no_act 6.
- **HARD BAR FAILED: a non-target hit (Creamy 1018), from a WALK click turned attack** (+1,663.6 s,
  a click 2 cells from it). The direct clicks were clean. The same cause hit v7 attempt 2
  (corrected above).
- **Unintended attack requests:** 41.
- **Selection:** the nearest at selection 72 %; distance p50 5 / p90 9.
- **Heading:** reversals 9.58 / min (Batt 3.6); straight runs 9.8 cells (Batt 16.9).
- **Walk clicks:** moving within 1 cell 76 %.
- **NPC contacts and map changes:** 0 / 0.
- **Batt's 18:53 clip (this run):** Porings around the GM while it walked to a far box by the
  wall. The log shows two causes:
  - Hopping Porings churn their track ids, so the queue's nearest entry (rank 0) was often "not
    valid" at dispatch, and a farther, steady box (rank 1-2) was dispatched.
  - 93 no_path drops in the run, many for cells by the wall.
  - The zone and the clearance were not in v10, and the risk rule was not involved (all direct).
- **vs the prediction:**
  - direct >= 60 %: YES (97 %);
  - in range -> click < 2 s: YES (0.66);
  - seen -> click < 8 s: YES (5.14);
  - engaged kills / h >= 60: YES (99.9);
  - the bar >= 90 %: NO (71.0);
  - hard bars 0 / 0 / 0: NO (a Creamy, via a walk click).

### 3.53 hunt-flow@11: the OPPORTUNISTIC STRIKE (pre-registered 2026-10-16 19:19 ICT, the commit time bf20830, BEFORE its run; Batt 19:0x)

**Batt (19:0x, his 18:53 clip):** "4-6 Porings cluster around the GM ... yet the GM leaves the
cluster and walks to a far target near the wall ... Fix as one pre-registered change
('opportunistic strike')."

**The ONE main change:**
1. **PRE-EMPTION.** Any tracked target with a box <= 1.0 s old, within 4 cells (Chebyshev,
   predicted), replaces the current target at once, the nearest first (`nearest_close`, logged
   `preempt`). The planner's queue resumes after the engagement. "Target" means a box that passes
   the size gate, so a Creamy never qualifies.
2. **THE HUNTING RISK RULE** (`gate_reasons_hunt`):
   - Overlap is risky only with a NON-target box: a Creamy-sized box, or one whose cell cannot be
     placed. A cluster of targets is NOT risky, because a misclick still hits a target.
   - The GM check is OCCLUSION only: the GM's sprite box (client 620-660 x 285-375) hides >= 50 %
     of the target's box.
   - Low confidence, an L3 NPC within 12 cells, and a Creamy within 150 px stay risky.
3. **The stand wait (v9) applies only on the read path.** A direct click does not wait for a
   hopping target to stand.
4. **The walk-click clearance** (the newest frame's boxes grown 12 px) covers NON-target boxes
   only: the Creamy hits. Around target boxes a misclick hits a target.

**Measured beside the bar:**
- the nearest at selection (v10 72 %) and the distance at selection (v10 p50 5; Batt's p50 4 at
  the click);
- preemptions per engagement;
- the bot-vs-Batt table, with the reversals and straight-run columns.

**Hard bars unchanged:** zero NPC contact, zero non-target hit, zero map change.

**Run:** 60 min, seed 20261217, prt_fild08, GM immune Lv 70 / STR 99, nice 10, detector on the CPU
(GPU freeze).

**Prediction, written before the run:**
- the nearest at selection >= 85 %, distance at selection p50 <= 4;
- engaged kills / h >= 100 (v10 99.9);
- seen -> click p50 <= 5 s;
- hard bars 0 / 0 / 0, with the Creamy now kept out by the non-target clearance;
- the bar is reported, not expected to reach 90 %: v10's misses are late re-clicks on hopping
  targets, which this change does not address.

**Run 1 RESULT (2026-10-16 19:20:14-20:20:14, session 20261016T192014-demo-hunt-flow11, seed
20261217; the full hour; judged ~20:23):**
- **Engagements:** 242, all dead (v10 131). Attack clicks 242 direct / 0 read.
- **Kills:** engaged 101 / h (v10 99.9); 37 more from walk clicks; 40 unintended attack requests.
- **Selection:** the nearest at selection 86 % (v10 72 %); distance at selection p50 4 / p90 8
  (v10 5 / 9).
- **Landing within W per engagement, by species:**
  - Poring 71 / 107 = 66 % (v10 78 %);
  - Lunatic 26 / 49 = 53 % (v10 75 %);
  - Drops 8 / 20 = 40 % (v10 75 %);
  - outcomes: hit 106, hit_late 64, no_unit 63, never_hit 7.
- **Pre-emption FLAPS:** 1,085 pre-emptions for 242 engagements. The nearest within 4 cells flips
  between neighbours as their predicted cells jitter, so more first clicks land on stale or
  just-flipped targets (no_unit 63).
- **HARD BAR FAILED:** a Creamy, by a DIRECT strike (+527 s). Its box was 39 x 36 px, inside the
  size gate: Poring boxes measure 38-41 x 36-39. The size gate cannot tell them apart; the next
  versions add the name tag (Batt chose it 19:5x).
- **Heading:** reversals 10.97 / min, straight runs 9.9 cells.
- **Timing:** in range -> click p50 0.78 s.
- **vs the prediction:**
  - the nearest at selection >= 85 %: YES (86);
  - distance p50 <= 4: YES (4);
  - engaged kills / h >= 100: YES (101);
  - seen -> click p50 <= 5 s: see the table;
  - hard bars 0 / 0 / 0: NO (the Creamy).

### 3.54 hunt-flow@12: the BURST STRIKE (pre-registered 2026-10-16 20:23 ICT, the commit time 133818d, BEFORE its run; Batt 19:4x / 20:0x)

**Batt:** "he CLICKS REPEATEDLY until the client draws the ARROW marker on the monster ... Do the
BURST strike first (as asked), tuned for small targets."

**Measured first, on his demo** (input log + packets; scratch analyses):
- He mostly clicks ONCE per engagement. Clicks per attack: 1 in 43 / 52, 2 in 7, 3 in 2.
- When he re-clicks, the interval is p50 0.6-0.8 s.
- First click -> his attack_request: p50 0.54 s, p90 1.47 s. 55 of his 63 attack clicks first
  produced a WALK request (the client walks in, then sends the attack).
- His last click is p50 0.5 s BEFORE the request, so the arrow he waits for is drawn client-side
  at the click.

**The arrow, proven on v10's recordings** (5 Hz JPEG, every strike click; a new small white
down-pointing blob 15-80 px above the clicked point, within 1.2 s):
- P(arrow | our attack_request within 2 s) = 0.71 (n 92);
- P(arrow | none) = 0.08 (n 39);
- arrow -> registered in 65 / 68;
- first seen p50 0.44 s (p90 0.85) after the click.
- The live raw frames (10-30 fps) are re-validated after this run against its packets.

**Aim, measured on v10's direct clicks** (species from the packets):
- first click landed: Poring 83 %, Lunatic 79 %, Drops 86 %;
- landed and missed clicks sat at the SAME offset in the box (p50 0), so the misses are the
  target MOVING between the ~0.5-1 s old frame and the click, not the aim point inside the box.

**The ONE main change (`burst`):**
- After a direct attack click, raw frames are watched for a NEW arrow above the aim point: a
  reference grab is taken just before the first click (`arrow_new`).
- With no arrow after 0.6 s (Batt's re-click interval), the next click goes to the FRESHEST box
  near the last aim (<= 60 px). It aims at the box's body centre plus a jitter of a fraction of
  THAT box: 0, +0.18 h, -0.18 w, +0.18 w, -0.15 h. A Lunatic's 33 x 27 box gets a tighter
  pattern than a Poring's 40 x 38.
- The burst stops on the arrow, at 4 clicks or 3 s, when no box is near ("gone"), when the risk
  gate turns ("risky"), or at the UI.
- Every burst click re-checks the risk gate. Each burst is logged: clicks, duration, arrow time,
  end.

**Measured beside the bar:**
- landing per engagement BY SPECIES (v10: Poring 78 %, Lunatic 75 %, Drops 75 %);
- clicks per landing;
- the aim error;
- the burst ends;
- the bot-vs-Batt table.

**Hard bars unchanged.** The Creamy risk stays until the name tag (v13): the size gate is the
only separator, so that bar may fail again.

**Run:** 60 min, seed 20261218, prt_fild08, GM immune Lv 70 / STR 99, nice 10, detector on the CPU
(GPU freeze).

**Prediction, written before the run:**
- landing within W per engagement: Poring >= 85 %, Lunatic >= 80 % (v10 78 / 75; v11 66 / 53);
- clicks per landing p50 <= 2;
- bursts ending on the arrow >= 60 %;
- engaged kills / h >= 100;
- hit_late below v11's 64 (per hour).

**Run 1 RESULT (2026-10-16 20:30:39-21:07:47, session 20261016T203039-demo-hunt-flow12, seed
20261218): STOPPED by Batt's lease at 37.1 min.** The runner stopped as designed: "a human lease
is active, nothing sent". This was the SECOND lease today (17:12, now ~21:08); Batt was told.
- **Engagements:** 184, all dead. Attack clicks: 183 direct / 1 read (low_conf).
- **Kills:** engaged 79 (~128 / h; v11 101); 30 more from walk clicks; 33 unintended requests.
- **Bursts (183):**
  - ends: arrow 69 (38 %), gone 96 (52 %: the box vanished before the 0.6 s re-click, mostly the
    one-hit kill or the cursor over the sprite), risky 18;
  - clicks per burst p50 1;
  - click -> arrow p50 0.45 / p90 0.66 s;
  - burst duration p50 0.64 s.
- **Landing within W per engagement, by species:**
  - Poring 52 / 82 = 63 %;
  - Lunatic 23 / 38 = 61 %;
  - Drops 5 / 10 = 50 %;
  - outcomes: hit 81, no_unit 50, hit_late 35, never_hit 16.
- **The aim error measured here is an ARTIFACT** (Poring p50 36 px). It was computed AFTER the
  burst, on a frame where the monster had moved or died. Fixed for the next runs: it is now
  measured before the burst.
- **HARD BAR FAILED again:** a Creamy, through the size gate. The name tag is in the queue.
- **Selection:** the nearest at selection 74 %, distance p50 4.
- **Pre-emptions:** 18 / min.
- **Timing:** box age at click p50 565 / p90 778 ms.
- **The LATENCY BUDGET** (the same stages on v11; `latency_budget.py`, scratch):
  - selection -> click p50 0.67 s;
  - in range -> click p50 1.09 s;
  - click -> attack request p50 0.56 s;
  - click -> server kill p50 1.64 s;
  - **server kill -> the bot's "dead" p50 -0.45 s.** The bot declares the kill BEFORE the server:
    its rule (box unseen 0.6 s, >= 1 s after the click) fires while the monster is hidden under
    the GM or the cursor. The next selection's click can then cancel the attack (the late and
    never hits).
- **vs the prediction:**
  - Poring >= 85 % / Lunatic >= 80 %: NO (63 / 61);
  - clicks per landing <= 2: YES (1);
  - bursts on the arrow >= 60 %: NO (38 %);
  - engaged kills / h >= 100: YES (~128);
  - hit_late per hour below v11's 64: YES (35 in 37 min = 57 / h).

### 3.55 hunt-flow@13: PRE-EMPTION HYSTERESIS (pre-registered 2026-10-16 21:10 ICT, the commit time 1cd4579, BEFORE its run; Batt 20:5x, his order A1)

**Batt:** "switch only if the new target is clearly better (e.g. >= 2 cells closer, or the current
one left the zone) AND stays better for >= ~0.5 s; never switch during a burst. Report
pre-emptions/min and landing."

**The ONE main change (`preempt_hyst`, `preempt_better`):**
- A target within 4 cells replaces the current one only when it is CLEARLY better: there is no
  current target, the current one is > 4 cells away (left the zone), or the new one is >= 2
  cells closer.
- It must stay so for >= 0.5 s (a candidate timer, reset when it stops being better).
- A burst runs inside the strike call, so no pre-emption can interrupt it.

**Also in (a measurement fix, no behaviour change):** the aim error is measured before the
burst. v12 measured it after the burst: an artifact.

**Run:** 60 min, seed 20261219, the same test state, nice 10, detector on the CPU (GPU freeze). It
starts after the takeover quiet period (>= 10 min without human input).

**Prediction, written before the run:**
- pre-emptions <= 5 / min (v11 / v12: 18);
- landing within W per engagement >= 75 % for Poring and Lunatic (v12: 63 / 61);
- engaged kills / h >= 120 (v12 ~128);
- the nearest at selection >= 80 % (v12 74 %);
- hard bars: the Creamy risk remains until the species check (v14).

**Run 1 RESULT (2026-10-16 21:25:55-22:25:58, session 20261016T212555-demo-hunt-flow13, seed
20261219; the full hour; judged 22:28):**
- **Engagements:** 262, all dead. Attack clicks: 265 direct / 1 read.
- **Kills:** kills / h 171.9; engaged 141 / h; 31 more from walk clicks; 36 unintended
  requests.
- **The bar:** 134 / 257 = 52.1 % (Wilson 46.1-58.2). Outcomes: hit 134, hit_late 58, no_unit 53,
  never_hit 12.
- **Landing within W by species:** Poring 81 / 119 = 68 %, Lunatic 33 / 59 = 56 %, Drops 20 / 25 =
  80 %.
- **Pre-emptions:** 9.8 / min (v12 18).
- **Timing:**
  - seen -> click p50 3.19 s;
  - death -> next click p50 0.62 s;
  - box age at click p50 574 / p90 934 ms.
- **Bursts:** ends gone 150 (57 %), arrow 98, risky 17; click -> arrow p50 0.38 s.
  - **"Gone" is the landing loser:** right after the click the detector loses the box (the
    cursor over a small sprite, or the monster stepping > 60 px), so the burst stops without a
    re-click, and a miss waits for the 2-s re-click (the late hits).
- **Selection:** the nearest at selection 84 %, distance p50 5.
- **Heading:** reversals 9.5 / min, straight runs 9.7 cells.
- **Monsters in sight:** 18.5 / 10 min.
- **HARD BAR FAILED again:** a Creamy, through the size gate. The species identity is next.
- **vs the prediction:**
  - pre-emptions <= 5 / min: NO (9.8);
  - landing >= 75 % for Poring and Lunatic: NO (68 / 56);
  - engaged kills / h >= 120: YES (141);
  - the nearest at selection >= 80 %: YES (84 %).

### 3.56 hunt-flow@14: SPECIES IDENTITY by the client's NAME TAG (pre-registered 2026-10-16 22:40 ICT, the commit time d38f871, BEFORE its run; Batt 19:5x + 20:5x A2)

**Why:** the non-target hard bar failed in v7, v10, v11 and v12, each time on a CREAMY.

**Every species cue we have, measured on today's recordings, fails to separate a Creamy:**
- the detector box: a Creamy measured 39 x 36 px, Porings 38-41 x 36-39;
- colour from the decoded sprites: 3 / 38 Creamy samples classed Creamy, 32 as Pupa;
- the "airborne" shadow gap: 3 / 36 Creamies flagged, and 15 / 190 targets flagged falsely.

The only cue that identifies the species is the client's own NAME TAG: dark text with a light
outline under the sprite, ~0.5 s after the pointer stops on it (the 20:3x hover probe).

**Templates** (`scripts/nametag.py`; data/nametags, gitignored):
- They come from no-click cut sessions (hover only, raw live frames; 20:22 + 21:19 at (268,107) mostly Lunatics; 22:29 at (290,350) and 22:35 at (200,330): 181 more cuts).
- Each cut is labelled by the packets (the species of the live mob at the hovered cell).
- Per species, the majority of the aligned letter masks: Poring 149, Lunatic 16, Drops 10 words; no Pupa (rare): a Pupa has no target tag and is skipped.
- Leave-one-out check: Poring 144 / 149 matched (5 unmatched), Lunatic 15 / 16 (1 unmatched), Drops 10 / 10; ZERO cross-species confusions. A Creamy tag (v11 +527 s, JPEG) scores IoU 0.22-0.35 against the target templates, far below the 0.72 acceptance.

**The ONE main change (`name_tag`):**
- Before every DIRECT attack click (first or burst), the pointer rests on the target and the tag
  band under its box is read every 0.1 s, for up to 1.2 s.
- Only Poring / Lunatic / Pupa / Drops is clicked.
- Another word, or no tag in time, means NO click: logged `tag_refused`, and a non-target word
  drops and bans the target.
- The read path (risky contexts) is unchanged.
- The live tag band is HARVESTED at each burst's arrow, for more templates labelled by the packets
  after the run.

**The same identity for WALK clicks:** a track becomes CONFIRMED once its tag reads a target
name. Walk clicks keep v11's 12-px clearance around every monster box NOT confirmed, because an
unknown box may be a Creamy (v10's walk click turned attack). Nearby targets are still struck
through the opportunistic strike.

**Run:** 60 min, a fresh seed, the same test state, nice 10, detector on the CPU (GPU freeze).

**Prediction, written before the run:**
- zero direct-click hits on a non-target;
- the tag read before a direct click p50 <= 0.6 s;
- tag_refused <= 15 % of strike calls;
- engaged kills / h >= 100 (the read costs ~0.5 s an engagement);
- landing within W per engagement reported by species (v13 is the reference).

**Run 1 RESULT (2026-10-16 22:41:22-23:41:22, session 20261016T224122-demo-hunt-flow14, seed
20261220; the full hour; judged by `flow_judge.bot` before 23:48, 4f24232):**
- **Engagements:** 176, all dead. Attack clicks: 173 direct / 4 read (low conf).
- **Kills:** kills / h 164.9; engaged 131.9 / h; 33 more from walk clicks; 45 unintended
  attack requests.
- **The bar:** 129 / 174 = 74.1 % (Wilson 67.2-80.1; v13 52.1 %). Outcomes: hit 129, hit_late 30,
  no_unit 9, never_hit 6.
- **Landing within W by species:** Poring 77 / 101 = 76 %, Lunatic 42 / 51 = 82 %, Drops 7 / 10.
- **The name tag:**
  - every direct click carried a target tag: Poring 107, Lunatic 54, Drops 12;
  - the read before a direct click took p50 366 / p90 780 ms;
  - 169 reads were REFUSED (no tag in 1.2 s; never another word): 46.7 % of 362 strike calls;
  - why: in the recorded frames, only 7 of 66 sampled refused reads show a matchable tag
    anywhere around the GM, against 31 of 40 before a clicked strike. The pointer was mostly
    OFF the sprite (a hop, the 0.5-s-old box), so the client drew no tag.
- **Timing:** seen -> click p50 5.67 s (v13 3.19: the refusals); death -> next click p50 0.66 s;
  box age at click p50 524 ms.
- **Bursts:** ends arrow 100, gone 57 (33 %; v13 57 %), risky 16.
- **Selection:** the nearest at selection 84 %, distance p50 4; pre-emptions 13.5 / min.
- **Heading:** reversals 9.5 / min (> 135 deg: 7.0), straight runs 9.1 cells.
- **HARD BAR FAILED: a non-target hit, through WALK clicks, not attack clicks.**
  - Six attack requests on Creamies (1018), seven damaging acts.
  - Each one came 0.2-1.5 s after a WALK click; no attack click was within 1.6 s of any of them.
  - The detector cannot see a Creamy: it is a flying, butterfly-like sprite, and at the six
    click points the v1 detector, re-run at conf 0.03, put no box on it. So v14's walk
    clearance (12 px around unconfirmed boxes) had nothing to clear.
  - In one case the Creamy flew onto the GM, where the walk click had landed.
- **vs the prediction:**
  - zero direct-click hits on a non-target: YES (0; every non-target hit was a walk click);
  - the tag read p50 <= 0.6 s: YES (366 ms);
  - tag_refused <= 15 %: NO (46.7 %);
  - engaged kills / h >= 100: YES (131.9);
  - landing by species: above v13 for Poring (76 vs 68 %) and Lunatic (82 vs 56 %).

### 3.57 hunt-flow@15: the LATENCY BUDGET's miss path (pre-registered 2026-10-16 23:48 ICT, the commit time c962c46, BEFORE its run; Batt B1, the overnight order item 4)

**Why (v13's latency budget, 262 engagements, from the runner's events and the packets):**
- Only 4 of 262 engagements were ever re-clicked: a missed first click waited for the 2.0-s
  re-click, which the early "dead" decision usually pre-empted.
- The bot's "dead" decision came p50 0.38 s BEFORE the server's kill: it gave up on a target the
  server still had alive.
- Bursts ended "gone" 57 %: the detector lost the box right after the click (the cursor over a
  small sprite, or a hop > 60 px), so the burst stopped without a re-click.

**The ONE main change (the miss path, built in 82235c9 + a05e08a; the run adds nothing else):**
- The re-click comes after 1.0 s, not 2.0 s.
- A burst whose box vanished keeps clicking the track's LAST box while it is <= 1.2 s old, only
  on a tag-confirmed track (v14's identity).
- Burst re-clicks go only on the SAME track's box: within 35 px of its newest box.
- "Dead" needs >= 1.4 s after the last click AND 0.8 s unseen.
- A track's confirmed tag is reused for 10 s (no second read for a burst or a re-click).

**v14 as the reference (run 1, 3.56):** bar 74.1 %, bursts ending gone 33 %, Poring 76 % / Lunatic 82 %
landing, engaged 131.9 kills / h, tag reads refused 46.7 %.

**Run:** 60 min, a fresh seed, the same test state, nice 10, detector on the CPU (GPU freeze).

**Prediction, written before the run:**
- bursts ending "gone" <= 20 % (v13 57 %, v14 33 %): a vanished box no longer ends the burst;
- engagements with a re-click >= 10 % (v13 1.5 %);
- the bot's "dead" p50 at or after the server's kill (v13 -0.38 s);
- the bar (landing within W per engagement) >= 78 % (v14 74.1 %);
- tag_refused share of strike calls BELOW v14's (the cache), still > 15 %: the tag only shows
  while the pointer is ON the sprite, and v14's refusals were mostly the pointer off it (7 / 66
  refused reads show a matchable tag anywhere in the recorded frames, against 31 / 40 before a
  clicked strike). The aim is v16's change;
- hard bars: zero NPC contact and zero map change expected. The non-target bar is expected to
  FAIL again: v14's six Creamy hits came through WALK clicks on a sprite the detector cannot see,
  and v15 does not change walk clicks. A walk-click guard is measured offline during this run
  and will be pre-registered on its own.

**Attempt 1 (2026-10-16 23:50:00, session 20261016T235000-demo-hunt-flow15, seed 20261221):
STOPPED at 12.6 min by the stuck guard ("no progress for 60 s at (127, 114)"), 25 engagements.**
- **Cause:** a LOOP the opportunistic strike made with v14's tag reads.
  - The target, track 290, was a Pupa (1008; the packets put it at (125, 115)). It is immobile
    and has no tag template, so every read is refused.
  - After three refused reads it was dropped and its cell banned for 15 s. But v11's
    `nearest_close` never looked at the bans, so it PRE-EMPTED it again at once: 14 cycles in
    60 s.
  - The stuck guard stopped the run as designed. No input was sent after the stop; the GM was not
    restored by the runner, which skips the restore on a stop (checked before attempt 2).
- **Fix (a bug fix, not a play change):** `nearest_close` skips the cells of targets dropped within
  `drop_target_s`, as `choose` always did (test: `test_the_opportunistic_strike_skips_a_target_
  dropped_here_within_the_ban`). Attempt 2 runs v15 with this fix and a fresh seed; nothing
  else changes.

**Attempt 2 (2026-10-17 00:06:04, session 20261017T000604-demo-hunt-flow15, seed 20261222):
STOPPED at 7.3 min by the stuck guard ("no progress for 60 s at (28, 75)"), 11 engagements.**
- **Cause:** the GM stood in a cliff pocket at the map's west edge (frames: cliffs on three sides,
  a no-entry cursor ring).
  - The planner's v8 escape fired once (to (38, 83)).
  - The cursor-gated walk click from the standstill was refused (`robust2_noentry:ring`).
  - After that no walk click passed for 53 s, until the stuck guard stopped the run.
  - The reckoned cell (31, 77) disagreed with the minimap's (28, 75).
- **Fix (a bug fix, not a play change; `unstall_s` 8 s, from v15 on):** the STALL BREAKER.
  - While standing with no target, if no walk click went out for 8 s, settle the cell (two
    minimap reads).
  - Then walk the walkable grid to a reachable cell 6-14 steps away, drawn at random
    (`unstall_cells`; logged `unstall`).
  - The stuck guard (60 s) stays the backstop.
- Attempt 3 runs v15 with both fixes and a fresh seed.

**Attempt 3 (2026-10-17 00:17:29, session 20261017T001729-demo-hunt-flow15, seed 20261223):
STOPPED BY ME at 2.8 min (SIGINT, a clean stop), 3 engagements.**
- The stall breaker fired three times, every time right after an engagement or at the start,
  never in a stall. It counted the time since the last WALK click, which includes engagements:
  a long strike (3.5 s in a read) plus the fight passed 8 s. So it replaced the planner's
  search path with a random walk after every long engagement, a play change.
- **Fix:** it counts only idle SEARCH time, from the last walk click, the last moment with a
  target or an engagement, or its own last firing, whichever is latest.
- Attempt 4 runs v15 with the three fixes and a fresh seed.

**Attempt 4 (2026-10-17 00:22:01, session 20261017T002201-demo-hunt-flow15, seed 20261224):
STOPPED at 5.5 min by the freeze guard ("the picture froze (3.6 s identical after a walk
click)"), 12 engagements.**
- **Not a frozen client.** A screenshot and the /health frame bus (writing, 14 fps) showed it
  live. The GM stood on a ledge at (53-55, 90); the client refused its walk clicks (a no-entry
  cursor), and nothing in view moved. A still scene after a walk click is what the guard reads as
  a freeze.
- The stall breaker never fired: it waited for 8 s WITHOUT a walk click, and the refused walk
  clicks kept going out.
- **Fixes (bug fixes, not play changes):**
  - the freeze guard first PROBES liveness: the pointer moves (two motions, no click), and a live
    client redraws its own cursor, which changes the picture. Only a picture that stays identical
    for 1.5 s after the probe stops the run;
  - the stall breaker also fires after 8 s of target-free search WITHOUT MOTION (the measured cell
    unchanged), even while walk clicks go out. The loot sweep counts as busy time.
- Attempt 5 runs v15 with all the fixes and a fresh seed.

**Attempt 5 = RUN 1 RESULT (2026-10-17 00:31:05-01:31:06, session
20261017T003105-demo-hunt-flow15, seed 20261225; the full hour; judged by `flow_judge.bot` before 01:34, b207cdc):**
- **Engagements:** 120 (119 dead, 1 gave up). Attack clicks: 154 direct / 1 read.
- **Kills:** kills / h 142.9; engaged 95.9 / h; 47 more from walk clicks.
  - Monsters in sight were 14.2 / 10 min (v14 19.8). The run spent its first ~15 min in the sparse
    west, where the stall breaker fired once and the liveness probe once (alive).
- **The bar:** 93 / 119 = 78.1 % (Wilson 69.9-84.6; v14 74.1 %). Landing: Poring 62 / 77,
  Lunatic 26 / 30, Drops 5 / 5.
- **The miss path:**
  - engagements with a re-click 26.7 % (v14 0.6 %, v13 1.5 %);
  - bursts end gone 20 (13 %), risky 67, arrow 67. The "gone" ends became "risky" ones: a
    vanished box now holds, and the hold's re-check finds `no_box`;
  - the server's kill -> the bot's "dead" p50 +0.52 s (v13 -0.38 s: no more early "dead"), at a
    cost: "dead" -> next selection p90 9.9 s.
- **The name tag:** refused 127 of 314 reads (40.4 %; v14 46.7 %).
- **Timing:** seen -> click p50 4.20 s; in range -> click p50 1.67 s; selection -> click
  p50 2.25 s.
- **Heading:** reversals 8.8 / min (> 135 deg 6.8), straight runs 10.1 cells.
- **Hard bars:** zero NPC contact, zero map change. Non-target FAILED as pre-registered: 2 walk
  clicks turned into attacks on Creamies. v15 has no walk guard; v16 carries it.
- **vs the prediction:**
  - bursts gone <= 20 %: YES (13 %);
  - re-clicked engagements >= 10 %: YES (26.7 %);
  - "dead" at or after the server's kill: YES (+0.52 s p50);
  - the bar >= 78 %: YES, at the edge (78.1 %);
  - tag refusals below v14's and > 15 %: YES (40.4 %);
  - the non-target bar failed: as predicted.

### 3.58 hunt-flow@16: FOCUS TRACKING + the WALK GUARD safety layer (pre-registered 2026-10-17 01:34 ICT, the commit time e6b9a94, BEFORE its run; Batt B2 / B4, the overnight order item 5)

**The ONE main change (`focus`, built in 3f1a47b):**
- The chosen target's sprite crop is cut from the very frame of its detector box.
- It is tracked by a fast NCC on every frame-bus frame (~10-20 Hz).
- The attack click and every burst re-click aim at the fresh centre (<= 0.35 s old), led by
  its velocity x (age + 0.15 s). Otherwise they aim at the detector box (p50 0.52-0.57 s old).
- The pointer that rests for the name-tag read is at that point too.

**Plus a SAFETY layer, not a play change (`walk_guard`, cdf4b2b), from this version on:**
- **Why:** v14's six Creamy hits (the hard bar) were all WALK clicks the client turned into
  attacks, on a sprite the detector cannot see (3.56).
- **The rule:** a walk click is refused when its pixel is within 120 px of the GM's sprite, or
  when a fresh grab shows pink pixels within 80 px of it. Pink means R over G by > 51 and B not
  under G by > 10: a Poring's or a Creamy's colours, never the ground's. The GM's own sprite box
  is excluded.
- A refused candidate falls back to the next point on the route. If none passes, there is no
  walk click this cycle.
- **Measured before the run:**
  - offline, on v10-v14's recordings (the nearest 5-Hz frame <= 0.25 s before the click), it
    covers 14 of 17 Creamy walk-attacks and flags 25 % of the normal walk clicks;
  - live, read-only, on two grabs at 00:00, it flagged only points near a Poring, a Lunatic and
    the UI's red icons, not the ground, the trees or the GM.
- Its verdicts are counted in the run summary (`walk_guard`: ok / near_gm / pink).

**Kept from v15:** its miss path and its three bug fixes (the opportunistic strike respects
dropped targets; the stall breaker, counting idle search time only).

**v15 as the reference (attempt 5 = run 1, 3.57):** bar 78.1 %, engaged 95.9 kills / h (monsters in
sight 14.2 / 10 min), tag reads refused 40.4 %, seen -> click p50 4.20 s, 2 Creamy hits through
walk clicks.

**Run:** 60 min, a fresh seed, the same test state, nice 10, detector on the CPU (GPU freeze).

**Prediction, written before the run:**
- focus: >= 50 % of the direct attack clicks aim from the tracker (`aim_src` focus:*);
- the bar (landing within W per engagement) >= 78 % (v15 78.1 %);
- tag reads refused <= 35 % of reads (v15 40.4 %, v14 46.7 %): the pointer rests on the tracked
  sprite;
- the guard: Creamy attack requests <= 1 in the hour (v14 6, v13 4); attack requests from walk
  clicks <= half of v14's; the guard refuses <= 35 % of the candidates it checks;
- engaged kills / h >= 0.8 x v15's 95.9 (the guard costs some walk clicks);
- hard bars: zero NPC contact, zero map change; the non-target bar PASSES unless a Creamy is
  hit through one of the 3 / 17 cases the guard missed offline.

**Attempt 1 (2026-10-17 01:35:09, session 20261017T013509-demo-hunt-flow16, seed 20261226):
STOPPED at 26.7 min, 40 engagements (all dead).**
- **Stop:** the backend refused an input ("greater_than_equal:agent_input.events.0.mouse_move.y":
  a pointer move above the desktop). Nothing outside the game was clicked.
- **Cause:** the focus aim (v16's main change) was checked only against the client's windows,
  not against the frame. A target near the top edge, led by its velocity, put the strike point
  above the screen (y < 0).
- **Fix (a bug fix):**
  - every focus aim (the strike, a burst re-click, the tag follow) must lie inside the game frame,
    else the box is used;
  - a burst point off the frame ends the burst (`off_view`);
  - a final check before every strike click refuses a point outside the frame
    (`strike_off_view`);
  - the pointer-off fallback after a click goes 90 px down instead of up near the top edge.
- The walk guard's verdicts in its 26.7 min: ok 1091, pink 398, near_gm 751 (48 % refused,
  above the predicted <= 35 %).
- Attempt 2 runs v16 with this fix and a fresh seed; the two attempts are judged separately and
  pooled for the >= 60 engagements.
- **Attempt 1's judge (`flow_judge.bot`):**
  - the bar 34 / 40 = 85 % (Wilson 70.9-92.9);
  - engaged 76 kills / h over its 26.7 min (34 engaged kills);
  - focus aimed 49 of the 54 direct strikes;
  - tag reads refused 40.7 %;
  - walk clicks turned into attacks 13, none on a Creamy.
  - **The non-target bar FAILED anyway, through the READ path.** Track 359 was tag-confirmed as
    a Poring 4.5 s earlier. A later strike in a risky context (near the GM) took the read path:
    SWORD read, click at the box (675, 370). The client attacked a Creamy (two acts, 168 / 177).
    The read path never asked for the tag: the SWORD read says "a monster", not which.

**Attempt 2 (02:04:33, session 20261017T020433-demo-hunt-flow16): STOPPED BY ME at 45 s
(SIGINT), to add the safety fix below before an hour ran without it.**

**Safety fix from attempt 3 (`tag_every_click`, `tag_cache_s` 3, `tag_cache_px` 60):**
- EVERY attack click needs a target tag, the read path's too: after its SWORD read, the tag is
  read at the click point.
- The tag cache (v15: 10 s per track) is reused only within 3 s AND within 60 px of the point it
  was read at. A track can take over another sprite's box.
- Attempt 3 runs v16 with it, and attempts 1 + 3 are pooled.

**Attempt 3 (2026-10-17 02:07:34, session 20261017T020734-demo-hunt-flow16, seed 20261228):
STOPPED at 23.3 min by the stuck guard ("no progress for 60 s at (186, 128)"), 26 engagements.**
- **HARD BARS PASSED:** zero NPC contact, zero map change, zero non-target hit. It is the first
  hunt-flow run without a non-target hit.
- **Results:**
  - the bar 21 / 26 = 81 % (Wilson 62-91);
  - engaged kills 21 in 23.3 min; monsters in sight only 9.9 / 10 min;
  - attack clicks 29 direct, 0 read; focus aimed 23 of 29;
  - tag reads refused 58.5 %;
  - only 2 walk clicks turned into attacks (both Porings);
  - the walk guard: ok 974, pink 534, near_gm 918 (60 % refused).
- **The stop:** the GM stood on a raised path at a cliff edge (screenshot), and its walk clicks
  into the field below read no-entry.
  - Each refusal carves its cell (radius 1) out of the walkable grid, so the grid around the GM
    was cut shut.
  - The stall breaker then found no path ("unstall ... to: null", 8 times) until the stuck guard
    stopped the run.
- **Fix (a bug fix, from v17's run on):** the stall breaker plans on the walkable grid as it was
  BEFORE any refusal. It tries first the cells the GM WALKED in the last minutes (the client
  took them), then random reachable cells. The walk clicks along that path use the same grid.

**v16 POOLED (attempts 1 + 3: 66 engagements, 50.0 min):**
- the bar 55 / 66 = 83.3 % (v15 78.1 %);
- engaged kills 55, 66 / h (v15 95.9 / h; sight 9.9-16.1 / 10 min against v15's 14.2);
- focus aimed 72 of 83 direct strikes;
- tag reads refused 40.7 % / 58.5 %;
- walk clicks turned into attacks 15 in 50 min (18 / h; v14 49 / h, v15 50 / h), none on a
  Creamy;
- one non-target hit, through the read path, in attempt 1 (fixed for attempt 3).
- **vs the prediction:**
  - focus >= 50 %: YES (87 %);
  - the bar >= 78 %: YES (83.3 %);
  - tag refusals <= 35 %: NO (40.7 / 58.5 %);
  - Creamy hits <= 1: 1 (attempt 1, through the read path, not the walk clicks);
  - walk-click attacks <= half of v14's: YES (18 / h against 49 / h);
  - the guard refuses <= 35 %: NO (48 % / 60 %);
  - engaged kills / h >= 0.8 x v15's: NO (66 against 76.7);
  - hard bars: attempt 1 FAILED, attempt 3 PASSED.

### 3.59 hunt-flow@17: LOOT EVERYTHING (pre-registered 2026-10-17 02:34 ICT, the commit time 9e4cabb, BEFORE its run; Batt 20:3x, the overnight order item 6)

**Batt's demo, measured by the same judge (`flow_judge.loot_metrics`, 0f520bf):**
- he picked up 62 of the 64 items that fell around his kills;
- 1.0 pickup request per item picked;
- kill -> the last pickup of its items, p50 1.56 s.

The bot so far picked items only through walk clicks the client turned into pickups (v14: 8 of
269).

**The ONE main change (`loot`, `loot_sweep`, built in ff0e21f):**
- After each kill the bot sweeps the drop area: the death cell, the server's drop pattern
  (SE / W / N), then the 3 x 3 around it.
- One park per sweep and one cursor read per cell.
- On the HAND cursor (PICKUP, read twice) and a clear unit check (walk@11's rule, loot@1's), it
  clicks, then confirms by the weight readout or the chat line.
- It sweeps again until a whole sweep shows no hand, bounded at 6 s and 8 clicks a kill.
- A monster inside the drop area skips the loot (the risk rule).
- The click census counts the loot click (hunt_flow.py: 4 direct clicks, with its reason).

**Kept from v16:** focus tracking and the walk guard (safety layer). From this version the guard
leaves the client's static windows out of its pink count (77269f0): in v16's first 200 checks,
30 % of the candidates were refused as pink, many beside the red icons of the chat window and
the skill bar, which are not sprites. Also kept: v16's safety fixes (the name tag on EVERY
attack click, the read path's too; the tag cache 3 s within 60 px; every aim inside the frame).

**v16 as the reference (pooled attempts 1 + 3, 3.58):** the bar 83.3 %, engaged 66 kills / h, tag
reads refused 40.7-58.5 %, walk-click attacks 18 / h, loot picked by walk clicks 5 of 87 items.
Attempt 3 passed the hard bars.

**Also from this run (a bug fix):** the stall breaker plans on the walkable grid before any
refusal, trying the cells the GM walked first (3.58 attempt 3).

**Run:** 60 min, a fresh seed, the same test state (the loot is cleared at the restore; mid-run
above 40 % weight), nice 10, detector on the CPU (GPU freeze).

**Prediction, written before the run:**
- picked / items >= 80 % (Batt 97 %);
- pickup requests per item picked <= 1.5 (Batt 1.0);
- kill -> last pickup p50 <= 2.5 s (Batt 1.56 s);
- no loot click becomes an attack: zero attack requests within 0.5 s after a loot click;
- engaged kills / h >= 0.75 x v16's 66, i.e. >= 50 (looting takes time; Batt looted at 300 kills / h);
- hard bars: zero NPC contact, zero map change, zero non-target hit.

**Run 1 RESULT (2026-10-17 02:35:00-03:35:00, session 20261017T023500-demo-hunt-flow17, seed
20261229; the full hour; judged by `flow_judge.bot` after 03:37):**
- **HARD BARS PASSED for the full hour:** zero NPC contact, zero map change, zero non-target hit.
- **Engagements:** 96, all dead. Attack clicks: 104 direct / 1 read.
- **Kills:** kills / h 94.9; engaged 86 / h. Walk-click attacks only 9 (v15 50).
- **The bar:** 85 / 96 = 88.5 % (Wilson 80.6-93.5), the night's best. Landing: Poring 44 / 50,
  Lunatic 36 / 39, Drops 5 / 5.
- **LOOT:**
  - 25 of the 136 items that fell around our kills were picked up (18.4 %; Batt 97 %);
  - 1.0 request per pickup;
  - kill -> last pickup p50 5.04 s (Batt 1.56 s);
  - 49 sweeps for 96 kills (the rest skipped: a monster in the drop area). They ended no_hand
    40, stale_park 2, done 7, with 18 loot clicks, every one answered by a pickup request,
    none by an attack request. The sweep took p50 6.4 s: its bound.
  - So the sweep's cursor reads mostly found NO hand over cells where items lay. This is the loot
    loser to look at.
- **The name tag:** refused 159 reads (55 %).
- **Timing:** seen -> click p50 5.27 s; looting 281 s of the hour.
- **Heading:** reversals 7.7 / min (> 135 deg 5.6), straight runs 10.4 cells.
- **The walk guard (UI windows left out):** ok 2066, near_gm 1668, pink 345. Pink refusals fell
  to 8 % (v16 19-21 %).
- **vs the prediction:**
  - picked / items >= 80 %: NO (18.4 %);
  - requests per pickup <= 1.5: YES (1.0);
  - kill -> last pickup <= 2.5 s: NO (5.04 s);
  - no loot click became an attack: YES (0 of 18);
  - engaged kills / h >= 50: YES (86);
  - hard bars: PASSED.

### 3.60 hunt-flow@18: MOVEMENT by a remembered SEARCH HEADING (pre-registered 2026-10-17 03:38 ICT, the commit time 0d41ae7, BEFORE its run; Batt 21:31 + 18:2x, the overnight order item 7)

**Batt (21:31):** "read the player arrow on the minimap ... keep a remembered SEARCH HEADING ...
turns are small ... +-45 degrees first, then +-90; a reversal (> ~135 degrees) only at a real
dead end ... RESUME the remembered search heading after engagements".

**Batt's demo, by the same judge (heading-change histogram added in 1d0eacb):**
- 3.6 reversals / min (> 120 deg), 2.4 / min above 135 deg;
- mean straight run 16.9 cells;
- leg-to-leg turns <= 45 / <= 90 / <= 135 / > 135 deg: 367 / 51 / 25 / 24.

The bot (v14): 9.5 reversals / min, 7.0 above 135 deg, runs of 9.1 cells.

**The ONE main change (`heading_search`, 1d0eacb; with the ENGAGEMENT ZONE, `zone`):**
- The planner keeps a remembered heading (the first one is the longest of the 8 compass rays
  from the start).
- The next search goal is the ray's end along that heading, kept while the ray runs >= 8 cells.
  On 30 % of re-plans the heading drifts by <= 20 deg.
- When blocked, it turns +-45 deg first, then +-90, then +-135, taking the side with the longer
  run. It reverses only at a real dead end.
- After every engagement the search path is re-planned from where the GM is, ALONG THE SAME
  HEADING (resume).
- The minimap arrow is read and LOGGED beside each heading goal, not used to steer. On v14's
  frames the arrow reader agreed within 45 deg with the arrow's own motion in 69 % of straight
  stretches, and that ground truth is coarse.
- The ENGAGEMENT ZONE plans one path into the attack range, re-planned only when the target
  leaves the zone.
- Offline, on the real prt_fild08 search area (3 seeds, 150 legs each), legs averaged ~30 cells.
  Turns > 90 deg were 9, 3 and 10 of the 150 heading changes.

**Kept from v17:** focus, loot, the walk guard (UI windows left out), and the safety fixes
(the tag on every attack click; aims inside the frame; the stall breaker; the liveness probe).

**v17 as the reference (run 1, 3.59):** reversals 7.7 / min (> 135 deg 5.6), straight runs 10.4
cells, monsters in sight 16.7 / 10 min, engaged 86 kills / h, the bar 88.5 %, hard bars passed.

**Run:** 60 min, a fresh seed, the same test state, nice 10, detector on the CPU (GPU freeze).

**Prediction, written before the run:**
- reversals (> 120 deg) <= 5 / min and > 135 deg <= 3.5 / min (v17 7.7 / 5.6; Batt 3.6 / 2.4);
- mean straight run >= 13 cells (v17 10.4; Batt 16.9);
- monsters in sight / 10 min >= 16.7 (v17; longer runs see more ground);
- engaged kills / h >= 86 (v17);
- hard bars: zero NPC contact, zero map change, zero non-target hit.

**Run 1 RESULT (2026-10-17 03:39:15-04:39:15, session 20261017T033914-demo-hunt-flow18, seed
20261230; the full hour; judged by `flow_judge.bot` after 04:41):**
- **HARD BARS PASSED** (the third clean run in a row: v16 attempt 3, v17, v18).
- **Engagements:** 111, all dead. Attack clicks: 131 direct / 0 read.
- **Kills:** kills / h 98.0; engaged 94 / h. Walk-click attacks 3.
- **The bar:** 93 / 111 = 83.8 % (Wilson 75.8-89.5). Landing: Poring 62 / 67, Lunatic 25 / 33,
  Drops 6 / 6.
- **MOVEMENT:**
  - reversals 5.25 / min (v17 7.71); above 135 deg 3.85 / min (v17 5.58);
  - straight runs 11.9 cells (v17 10.4);
  - leg-to-leg turns <= 45 / <= 90 / <= 135 / > 135 deg: 1164 / 297 / 215 / 231 (v17 1164 / 370 /
    275 / 335);
  - heading goals: 1661, mostly keeping the heading. The stall breaker fired twice.
  - Batt's demo: 3.6 / 2.4 / min and runs of 16.9 cells.
- **Monsters in sight:** 13.5 / 10 min (v17 16.7).
- **Loot:** 41 / 145 items picked (28 %); kill -> last pickup p50 6.46 s; 60 sweeps.
- **The name tag:** refused 172 reads (52 %).
- **vs the prediction:**
  - reversals <= 5 / min: NO (5.25);
  - > 135 deg <= 3.5 / min: NO (3.85);
  - straight runs >= 13 cells: NO (11.9);
  - sight >= 16.7: NO (13.5);
  - engaged kills / h >= 86: YES (94);
  - hard bars: PASSED.
  - All three movement numbers moved Batt's way from v17, but none reached its bar.

### 3.61 hunt-flow@20: TAG FOLLOW, the top loser (pre-registered 2026-10-17 __TIME__ ICT, the commit time __SHA__, BEFORE its run; the overnight order item 8, "iterate on the top loser")

**Why this one:**
- v14's name tag stopped every non-target attack click, but its reads are slow. Refused reads
  (no tag within 1.2 s) were 46.7 % in v14, 40.4 % in v15, and 40.7 % / 58.5 % in v16.
- Each refusal costs ~1.3 s, and three drop the target. "In range -> click" p50 rose from
  0.61 s (v13) to 1.67-2.11 s.
- **The cause, measured on v14's frames:** only 7 of 66 sampled refused reads show a matchable
  tag anywhere around the GM, against 31 of 40 before a clicked strike. The pointer was OFF the
  sprite (the target hopped, or the aim was stale), so the client drew no tag.
- v16's focus aim put the pointer on the tracked centre at the start of the read, but the
  pointer then stayed still for the read's 1.2 s while the target moved.

**The ONE main change (`tag_follow`, built in 3d856aa; rebased on v18 in da4cd90):**
- During the read, every 0.1 s, the pointer follows the focused target's fresh centre (<= 0.35 s
  old), whenever it is > 10 px from the pointer.
- The tag is searched under the detector box AND under the pointer. The client draws the tag
  only under the HOVERED sprite, so a tag in either band names what the pointer is on.
- The click goes where the pointer ended, i.e. where the tag was read.
- v20 builds on v18, NOT v19 (re-target, built and never run), so it is one change against the
  last version run.

**v18 as the reference (3.60):** the bar 83.8 %, engaged 94 kills / h, tag reads refused 52 %, hard
bars passed.

**Run:** 60 min, a fresh seed, the same test state, nice 10, detector on the CPU (GPU freeze).

**Prediction, written before the run:**
- tag reads refused <= 25 % (v16 40.7 / 58.5 %);
- in range -> click p50 <= 1.2 s;
- the bar >= 83.8 % (v18);
- engaged kills / h >= 94 (v18);
- hard bars: zero NPC contact, zero map change, zero non-target hit (the tag still gates every
  attack click; the follow only moves the pointer, and the tag must read under it).

## 4. Labels from verified outcomes
- A verified attack click at pixel p on gid G becomes a POINT label: "p belongs to G (class,
  Timeline state)", with `predict_sprite`'s box attached.
- A verified "click became a walk" becomes a negative point.
- They are written to `data/labels/demo/*.jsonl` (gitignored) with `source=demo` (weak), kept
  apart from auto-labels v1.
- Their value is measured before any mixing: a separate pre-registration, one variable at a time.
- **Built 2026-10-07:** `scripts/demo_labels.py SESSION_DIR` reads `demo.verified.jsonl`
  (it refuses an unverified session) and writes `data/labels/demo/<session>.jsonl`.
  - One label per verified success with a click, on the frame the actor decided on.
  - `box` stays null until `predict_sprite` attaches it over the session's Timeline.
  - The bot's own actions use the same schema (`test_demo_labels.py`).

## 5. Next verifiers (planned)
- **NPC talk / choice:** CZ_CONTACTNPC → ZC_SAY_DIALOG / ZC_MENU_LIST from that npc; CZ_CHOOSE_MENU
  = the intended option; then the next dialog state.
- **Shop:** DEALTYPE → PURCHASE_ITEMLIST → CZ_PC_PURCHASE_ITEMLIST → PURCHASE_RESULT 0, plus the
  zeny change.
- **Stat / skill:** STATUS_CHANGE_ACK, SKILLINFO_UPDATE.

They are verified by an offline replay of the banked pcapng with the new decoders, not by
redeploying the sniffer. Their rules (the expected options from rAthena's NPC scripts, static data
per ADR-0015) are pre-registered here before their tests.

**Decoders built 2026-10-07, replay only; the sniffer image is NOT rebuilt.**
- They run in `python -m poring_packets.replay` over banked captures. The live sniffer still emits
  only the older events.
- Layouts are rAthena's at the pinned ref, for PACKETVER 20211103 (an RE client), with citations in
  `decode.py` (`MAP_SC` / `MAP_CS`). Every id and size matches the generated length table.
- A short or garbled packet decodes to nothing; it never raises.
- `npc_gid` is the NPC's block id, the id `entity_appear` reports.
- Inventory `index` is the client's: the server's index + 2, as on the wire.

Event → fields (cs = our request, sc = the server):
- NPC dialog:
  - `npc_contact` (cs): `npc_gid`, `contact_type`. A monster's or player's id here starts a
    continuous attack on the server.
  - `npc_say` (sc): `npc_gid`, `text` (cp874), `raw_hex`.
  - `npc_wait` / `npc_close` (sc): `npc_gid`. The dialog shows its next / close button.
  - `npc_menu` (sc): `npc_gid`, `options` (the ':'-split list, empty entries kept), `raw_hex`.
  - `npc_choose` (cs): `npc_gid`, `choice` (1-based; 255 = cancel), `cancelled`.
  - `npc_next_click` / `npc_close_click` (cs): `npc_gid`.
  - `npc_number_prompt` / `npc_text_prompt` (sc): `npc_gid`.
  - `npc_number_input` (cs): `npc_gid`, `value`.
  - `npc_text_input` (cs): `npc_gid`, `text`, `raw_hex`.
- Shop:
  - `shop_deal_prompt` (sc): `npc_gid`.
  - `shop_deal_choice` (cs): `npc_gid`, `deal` (0 buy, 1 sell), `kind`.
  - `shop_buy_list` (sc): `items[]` = `item_id`, `price`, `discount_price`, `item_type`.
  - `shop_buy_request` (cs): `items[]` = `item_id`, `amount`.
  - `shop_buy_result` (sc): `result`, `ok` (result 0).
  - `shop_sell_list` (sc): `items[]` = `index`, `price`, `overcharge`.
  - `shop_sell_request` (cs): `items[]` = `index`, `amount`.
  - `shop_sell_result` (sc): `result`, `ok`.
  - Zeny is the existing `stat_change` with `name` zeny (var 20).
- Stats and skills:
  - `stat_raise_request` (cs): `stat` (13–18), `name` (str … luk), `amount`.
  - `stat_raise_result` (sc): `stat`, `name`, `ok`, `value` (the new value, capped at 255).
  - `skill_up_request` (cs): `skill_id`.
  - `skill_update` (sc): `skill_id`, `level`, `sp`, `range`, `upgradable`.
  - `skill_list` (sc): `skills[]` = `skill_id`, `level`, `sp`, `range`, `upgradable`.
  - The points left arrive as `stat_change`: `status_point` (var 9), `skill_point` (var 12).
- Equipment and items:
  - `equip_request` (cs): `index`, `location`.
  - `equip_result` (sc): `index`, `location`, `view_sprite`, `result`, `ok`. Result 0 = worn,
    1 = level too low, 2 = failed.
  - `unequip_request` (cs): `index`.
  - `unequip_result` (sc): `index`, `location`, `result`, `ok` (0 = taken off).
  - `use_item_request` (cs): `index`, `aid`.
  - `use_item_result` (sc): `index`, `item_id`, `aid` (whose use: a success goes to the whole
    area), `amount` (left), `ok`.
- The attack click:
  - `attack_request` (cs, CZ_REQUEST_ACT2 0x0437): `target_gid`, `action`, `kind`, `is_attack`.
  - Action 0 = attack once, 7 = keep attacking (both `is_attack`); 2 / 3 = sit / stand.
  - A walk click stays a `self_move_request`. That difference is what tells an attack click from
    a walk.
- Floor items and pickups (**built 2026-10-08 for loot@1 P2; replay only**, `replaydev:` below):
  - `floor_item_appear` (sc): `kind` "fall" (ZC_ITEM_FALL_ENTRY5 0x0ADD, 24 bytes: a FRESH drop)
    or "in_sight" (ZC_ITEM_ENTRY 0x009D, 19 bytes: one already lying there comes into view),
    `floor_id` (the pickup act's `target_gid`), `item_id` (u32 at this PACKETVER), `item_type`
    (fall only), `identified`, `x`, `y`, `sub_x`, `sub_y`, `amount`, `drop_effect`.
  - `floor_item_vanish` (sc, ZC_ITEM_DISAPPEAR 0x00A1): `floor_id`. Picked up, expired
    (`flooritem_lifetime` 60 000 ms on the lab server), or out of OUR sight: the packet does not
    say which.
  - `pickup_request` (cs, CZ_ITEM_PICKUP2 0x0362): `floor_id`.
  - `pickup_result` (sc, ZC_ITEM_PICKUP_ACK 0x0B41, 70 bytes): `index`, `amount`, `item_id`,
    `result`, `reason`, `ok`. It is sent for EVERY item that enters the inventory (an `@item`
    too), so a floor pickup is: our `act` of kind pickup on the floor id + `pickup_result` ok for
    that item + the floor id's vanish (`scripts/loot_truth.py` "confirmed"). Result 6
    ("refused") is also rAthena's generic fail packet (too far, loot priority, dead).
  - `drop_request` (cs, CZ_ITEM_THROW2 0x0363) / `drop_result` (sc, ZC_ITEM_THROW_ACK 0x00AF):
    `index`, `amount` (`ok` = amount > 0).
  - Where a kill's drops fall (pinned rAthena, mob.cpp:2531-2551): the first ON the death cell,
    then SE, W, N, SE, ... (a cell holding a char or pet moves that one to a free neighbour), at
    once on the lab server (`delay_battle_damage` yes).

## 6. Playable demos (end-to-end, supervised, UNSCORED)

Batt's standing rule (2026-10-15; CLAUDE.md "How we work"): every 2-3 days, or whenever a new skill
passes, the VERIFIED pieces are assembled into a short loop Batt watches live. The setup:
- HUD (perception + decision layers) and the route preview ON; Batt in Watch only;
- time-boxed, unscored, the GM immune, safety from packets.

The report ranks what slowed it down BY TIME LOST. A demo is not a skill verification: it has no bar
and passes nothing, and its numbers only point at what to improve next.

### 6.1 farm@0 (planned 2026-10-15 ~19:35 ICT, before the run; Batt's request, verbatim in the session)

- **Map:** prt_fild08. Its spawn table is exactly the target list: Poring 70, Lunatic 40, Pupa 20,
  Drops 10 (`data/kb/spawns.json`). The detector (v1) knows all four. It has no species classes,
  so a target = a detector MONSTER box on this map; players and NPCs never. Each kill's species is
  checked afterwards from the packets (`farm0.py report`: a hit by the GM on any other mob id is a
  safety finding). Not the training grounds: v1 cannot see Chonchon or 1184 there.
- **Character:** the GM (2000002), immune. `@monsterignore` is confirmed for THIS login through
  collect_v2's record (immune-on, a screenshot read, immune-confirm); the script refuses
  otherwise and never types the toggle. Its fixed state is restored before, and after a clean end
  (the levels the kills gain are reset). 2000001 is untouched.
- **The loop** (`scripts/farm0.py`, proven pieces only):
  1. find: the CPU unit detector on every frame it can (loot@1's sampler); the nearest monster by
     cell, inside a farm box (240-300 x 80-135) away from every warp;
  2. walk: walk@15's own route loop, unchanged, to a stand cell within 2 of the target when it is
     farther than 3 cells; no target for 6 s -> walk@15 to a seeded cell 8-12 cells away. Stand
     cells = client GAT AND server map cache, outside warp spans and touch areas (the three
     checks; prt_fild08's two maps agree on every cell but the server's NOPASS edge);
  3. attack: the live gate's robust2 reader, SWORD on the hover read and a no-motion re-read,
     then the click (cursor_gate.gated_click); again after 8 s while the target lives;
  4. death from pixels (loot@1's Track: unseen 3 frames and 1 s after an attack);
  5. loot: loot@1's PICKUP hover-scan of the 3 x 3 around the death cell, read by robust2 twice,
     walk@11's unit gate, one click, the weight / chat check;
  6. repeat until the 30-minute box.
- **Stops (each one reported, never retried):**
  - any client state but "clear" (the UI gate's pixel check every cycle, nothing closed);
  - the HP bar below 75 % (an immune GM never loses HP);
  - Batt's takeover: a human lease makes the run raise where ro_agent would wait;
  - the mux leaving ASSIST;
  - an unknown own cell.
  - After a stop nothing more is typed. The level reset then waits for a judged screen.
- **Report:** kills / hour (packets); base / job EXP gained (packets' stat_change, across
  level-ups); the time split (finding, walking, cursor waits, fighting, looting, checks), ranked;
  every stop and why; safety from packets (replay_safety's counts, NPC dialog events, non-target
  mob ids hit, acts onto the GM, map changes).
- **Tests:** `services/backend/tests/test_farm0.py` (target choice, approach and wander goals, the
  time split, the takeover stop, EXP across a level-up, kills from packets). The live loop was not
  run before Batt's session.
- ➡️ **RAN 2026-10-15 20:10:35-20:21:46 (`20261015T201035-demo-farm0`): STOPPED after 11 min, 0
  kills by the packets.**
  - The stop: "our cell is unknown". walk@15 returned `arrived` while the GM was still walking; the
    two minimap reads differed and /where failed.
  - 21 cycles: 16 engagements, 4 wanders, 1 stopped.
  - **Every engagement but one failed as a STALE TARGET** (15 / 15 failures). In 12 the monster had
    hopped 3-11 cells by the time it was looked for again (packets); 2 had left the view; 1 had
    moved 1 cell and was still lost. Cycles 10-14 chased one Poring hop after hop. Batt's
    recording (20:17): the box lagged the Poring by a body width.
  - Not still: 0. UNKNOWN reads: 0 (no SWORD probe was made on a lost target). Walks interrupted: 0
    (17 / 17 arrived). The hovers at the stale spot were walk@15's own click-point probes.
  - **The one "kill" was FALSE.** A Pupa took 23 hits (162 damage of its 427 HP). Then it
    METAMORPHOSED into a Creamy (1018, same gid: Pupa's IDLE skill NPC_METAMORPHOSIS, rate 10) and
    the pixel track lost it. The GM never hit the Creamy (its last hit was at 20:13:00; the Creamy
    shows at 20:15:52). Base / job EXP gained: 0 / 0.
  - Time split (reconstructed from the event times; the in-run split was lost to a crash writing
    the manifest, now fixed): walking >= 440 s of 650 (68 %), finding / re-acquiring / other
    ~140 s, checks ~50 s, fighting ~10 s, looting ~8 s, cursor waits ~0.
  - Safety (packets): attack requests 1 (the Pupa), NPC contacts 0, NPC dialogs 0, our pickups 0,
    acts onto the GM 0, map changes 0. The fixed state was NOT restored after the stop (nothing is
    typed after a stop); the GM stayed Base / Job Lv 1 (no EXP).

### 6.2 farm@1 (Batt 2026-10-15 ~20:25: "engage like a player"; planned before the run)

`scripts/farm1.py`, the same frame as farm@0, with Batt's five points:
1. **No walk first:** the monster itself is clicked; the client walks to it and attacks.
2. **Fresh + still:** while engaging, every detector frame (full frame, ~3-4 Hz) is focused on the
   target (only boxes within 90 px of its last feet). The hover waits until its feet moved < 6 px
   across detections spanning >= 0.5 s, the latest <= 0.35 s old, and aims at that box's CENTRE.
   - A true crop at a higher rate needs a model re-exported for a small input. v1's ONNX is fixed
     at 1280 x 736, so a crop costs a full frame (180 ms at 8 threads).
3. **ONE robust2 SWORD read -> click at once.** Each click is judged from the packets afterwards:
   an attack request, or a walk (a misread there only walks).
4. **Re-acquire:** a target that hops (> 30 px between frames) or is unseen 1.5 s is dropped and
   the next one found fresh; a stale box is never chased.
5. **After the click:**
   - the cursor parks off the monster (its name label would fake the cue);
   - "attack started" = new near-white pixels above the box (the damage numbers), a logged cue;
     no cue in 4 s, or none for 8 s, re-engages the still target;
   - the death from pixels (unseen 3 frames AND 1.5 s, was 1.0);
   - then loot@1's scan as farm@0.
- **New: a SIZE GATE against Creamy.** Pupa metamorphoses into Creamy, which is not a target, and
  the detector has no species. Creamy flies (51 x 53 native px); the targets are <= 37. So a box
  larger than 45 native px, at the camera's scale for its cell, is skipped. Each hit's species is
  checked from the packets AT HIT TIME (the report now keeps the species a gid had when hit).
- Also fixed from farm@0: the GM's cell is read only once it STANDS (two minimap reads 0.3 s
  apart agree, up to 5 s), at each start and after every walk (wanders only).
- Tests: `services/backend/tests/test_farm1.py` (focus stillness / hop / window, the size gate,
  the damage cue, the death rule) and test_farm0's metamorphosis case.
- ➡️ **RAN 2026-10-15 20:32:31-21:02:44 (`20261015T203231-demo-farm1`): the full 30-minute box,
  3 kills by the packets (2 Poring, 1 Lunatic) = 6.0 kills / h; base / job EXP 10 / 4.**
  - The GM reached Base Lv 2 at 20:56:26 and was reset to Lv 1 at 21:03:09. Job EXP 4 remains:
    `@joblevelup` cannot go below Lv 1.
  - 3 items picked up (weight 818 -> 822; the inventory icon shows its new-items badge).
  - The restore left the chat input open. It was closed by its known step, and the runner now
    closes it.

  | | farm@0 (650 s, reconstructed) | farm@1 (1,813 s, instrumented) |
  |---|---|---|
  | kills (packets) | 0 | 3 (2 Poring, 1 Lunatic) |
  | kills / h | 0 | 6.0 |
  | base / job EXP | 0 / 0 | 10 / 4 |
  | engagements -> kills | 16 -> 0 | 6 -> 3 (2 hopped, 1 lost) |
  | walking | >= 440 s (68 %) | 1,142 s (63 %), all wandering to find a monster |
  | finding / re-acquiring | ~140 s (22 %) | 473 s (26 %) |
  | checks (the UI gate's pixel check, ~2.4 s a cycle) | ~50 s (8 %) | 94 s (5 %) |
  | fighting | ~10 s | 48 s |
  | looting | ~8 s | 37 s |
  | cursor (hover + read) | ~0 | 14 s (6 SWORD, 3 unknown) |
  | focusing (waiting for a still target) | - | 5 s |

  **What slowed farm@1 down, ranked by time lost:**
  1. **An empty field: 1,615 s (89 %) went on finding a monster.** 78 of 84 cycles found no monster
     and wandered. The packets put NO monster within 14 cells (the server's view) at the start of 76
     of those 78. So it was scarcity, not detector misses. Each wander is walk@15 at its pace
     (~15 s for 8-12 cells), inside a 61 x 56-cell box.
  2. ~~**The first click never attacked: ~30 s lost per kill.**~~ ➡️ **CORRECTED 2026-10-15
     ~21:45 (Claude's error, from reading only the FIRST packet after each click): the first click
     DID attack, 3 / 3.**
     - The client walked to a cell next to the target (`self_move_request`) and then sent its own
       `attack_request` ("repeat") 0.4-2.4 s after the click, followed by damaging hits.
     - The re-engage clicks 10 s later were redundant; harmless, since the attack was already on.
     - Fighting took ~16 s per kill: the Novice Lv 1 GM hits for 0-14 every ~1.3 s, and a Poring
       has 50 HP.
  3. **The "attack started" cue (new white pixels above the box) is not usable:** it fired 0.46 s
     after the first damaging hit once, and 0.7 s and 2.5 s BEFORE any damage twice.
  4. The per-cycle UI check: 94 s.
  - "Is one SWORD read enough?" On this sample, yes: 3 single-read first clicks, 3 attacks on target
    species (6 reads, 6 clicks, no non-target, no NPC).
  - Each first hover read a box ~2 s old (`age_ms` 2,017-2,077). The park, the two-motion hover and
    the read take ~1.7 s after the still-check, so "re-detect right before the hover" is not met
    yet. The targets had stayed put.
  - **Safety (packets):** NPC contacts 0, NPC dialogs 0, acts onto the GM 0, non-target units hit 0,
    species changes after a hit 0, map changes 0. 10 attack requests and 3 pickups, all on targets
    and their drops. The size gate skipped nothing.
  - The report's earlier "non-target hit" was the PICKUP acts: their target id is the floor item's.
    Fixed: only attack acts count as hits. The EXP count now holds across a level-up, with the old
    need taken from the needs the packets showed.

## Results

### login@1, RDP: **PASS, 50 / 50 verified** (2026-10-07 12:13–12:45 ICT / 05:13–05:45 UTC)
- **Session:** `20261007T121323-demo-login-alone`, on the NAS sink once shipped (never committed).
- **The run:** 50 attempts by `rule_run.py login`, run alone. Each started with no client
  running, and the harness closed the client between attempts. There were 0 rule stops.
- **The verdict comes from packets only** (`verify@1`, `demo_verify.py`): our `login_accepted`
  (aid 2000002) → `char_selected` → `map_enter`, in order, in each attempt's own window.
  - Verified successes: 50. Failures: 0. Ambiguous: 0. The bar was ≥ 48 / 50.
  - Time per attempt, launch included: p50 28.0 s, p95 29.0 s.
  - Login accepted at p50 25.0 s (max 26.6), char selected 27.1 s, map entered 27.2 s
    (max 30.0).
- **Caught before reporting, and fixed:** a 60 s verification window overlapped the NEXT attempt
  (33 s later). A failed attempt could have been "verified" by its successor's packets. Every
  window now ends where the next record starts (tested). The re-score is unchanged: 50 / 50.
- **The L1 entry** `session.login` records this RDP pass in `verified_on`. Its status stays
  UNVERIFIED until the S2 re-test passes.

### walk@1, outdoor, RDP: **FAIL, a RULE failure** (stopped at 5 / 50) (2026-10-07 12:51–12:53 ICT)
> ➡️ **Corrected 2026-10-07 ~13:15.** This run was first recorded as INVALID (a harness defect).
> That attribution was wrong (Cause 1 below). Its misses came from the rule's one-motion hover,
> the same as walk@2's (§walk@2). So walk@1 is a rule FAIL, not an invalid run.

- **Session:** `20261007T125146-demo-walk-alone-outdoor`.
- **All 5 attempts declined:**
  - attempt 0: `no_selfpos`. It came right after the first map change (prt_church → prt_fild08),
    before the minimap was drawn.
  - attempts 1–4: `no_marker`, with marker_px 0 every time. The minimap readout was CORRECT
    each time (it equalled the harness's warp spot).
- **The run was stopped once the verdict could no longer change:** 4 failures cap it at 46 / 50,
  under the 48 bar.
- ~~**Cause 1, a HARNESS defect**~~ ➡️ **WRONG, see the correction above and §walk@2:** an open
  chat does not suppress the marker (6 / 6 drawn with it open). The hand check below did not control
  how many times the cursor moved (the likely confound). As first written:
  the harness's GM `@warp` opens the chat to type, and it never
  closed it again. With the chat input open, the client draws NO walk marker under the cursor
  (checked by hand: chat open → 0 marker px; chat closed → the chevrons are drawn). The tested
  situations were therefore not valid ones; the harness must close the chat after every GM
  command (as `bench.enter_scene` does).
- **Cause 2, a RULE finding:** with the chat closed, the marker IS drawn, but its colour on RDP
  is ≈ RGB (105–112, 196–203, 112–120), blue only ~7 above red.
  - `empty_cell.marker_px`'s mint filter (blue − red > 10, tuned on another path) counts just
    2–12 px, against the 40 px threshold.
  - So the demonstrated hover cue does not transfer to RDP as written.
- **Next (pre-registered before it runs):** walk@2.
  - The harness closes the chat after every GM command.
  - The marker cue is RE-CALIBRATED per path at design time: walkable vs non-walkable hovers,
    both scenes, a threshold chosen only if the two separate.
  - Then n = 50 per scene, alone.

### walk@2, outdoor, RDP: **FAIL, 0 / 18 (stopped; the bar was unreachable)** (2026-10-07 12:58–13:01 ICT / 05:58–06:01 UTC)
- **Session:** `20261007T125804-demo-walk-alone-outdoor`, seed 20261008.
- **verify@1** (`demo_verify.py`): 0 verified. Fail causes:
  - `declined:no_marker` 17;
  - `declined:no_selfpos` 1: attempt 0, the first warp onto the map; the minimap was not drawn
    after 2.5 s.

  Verdict: FAIL.
- **What the evidence says:**
  - Every `no_marker` had marker_px 0, and the minimap origin equalled the harness's spot each
    time, so the projection's input was right.
  - The after-snapshots show bare ground at the hover point. The marker was NOT drawn; this is
    not a filter miss.
- **Stopped** by the operator after 18 attempts (13:01:40). The session's packet window and the
  stop note were written afterwards.
- **The cause: the rule's hover.** A design-time probe (scratch; 18 trials, three variants
  interleaved: the harness exactly, a 4 s settle, no `activate_client`):
  - after ONE jump to the cell, 0 / 18 drew a marker (0–1 px);
  - after a second 1-px move, 18 / 18 did (121–209 px).

  The settle time and the title-bar click make no difference. The calibration hovered with two
  moves (3 px off, then the cell), which is why it saw 30 / 30. walk@1 and walk@2 hovered with
  one.
- **The correction to walk@1's Cause 1.** A second probe, 12 trials, two moves each:
  - chat OPEN: 6 / 6 markers (157–213 px);
  - chat closed: 6 / 6 (136–215 px).

  An open chat does not suppress the marker.
- **The indoor walk@2 run was not run.** The rule's hover is the same in both scenes. walk@3
  (3.5) replaces walk@2 in both.
- **Next:** walk@3, pre-registered in 3.5 before it runs.

### walk@3, outdoor, RDP: **PASS, 49 / 50 verified** (2026-10-07 13:14:57–13:25:26 ICT / 06:14:57–06:25:26 UTC)
- **Session:** `20261007T131457-demo-walk-alone-outdoor`, seed 20261009.
- **Verified by packets** (verify@1). The walk window now ends at the next attempt (078d121,
  fixed before this run was scored).
- **49 verified successes.** Each time the server accepted a walk to exactly the target cell
  (0 cells off), and nothing re-routed or stopped us.
  - Accepted at p50 1,025 ms and p95 1,060 ms after the attempt began. The two-motion hover takes
    ~0.45 s of that.
  - The targets were 2–6 cells away.
  - The hovers that clicked counted 111–217 marker px (threshold 60).
- **1 failure:** attempt 17 declined `no_marker`. A Poring stood just above the target cell, so
  the cursor was on the monster: the client draws its attack cursor there, not the walk marker.
  The rule declined rather than click a monster, which is L1 `nav.walk_to`'s precondition
  (nothing clickable on the target pixel). It counts as a FAIL, as pre-registered.
- **Next:** walk@3 indoor (n = 50). L1 `nav.walk_to` gets its RDP `verified_on` entry only once
  both scenes pass.

### walk@3, indoor, RDP: **FAIL, 32 / 49 verified** (+1 ambiguous) (2026-10-07 13:43:21–13:53:54 ICT / 06:43:21–06:53:54 UTC)
- **Session:** `20261007T134321-demo-walk-alone-indoor`, seed 20261009, prt_church, flat floor
  with the RDP camera's indoor block.
- **verify@1:** 32 verified successes; 17 failures; 1 ambiguous.
  - The 17 failures: `declined:no_marker` 9, and "walked to a different cell (1 off)" 8.
  - The ambiguous one: a map change inside the arrival window, almost surely the next attempt's
    harness `@warp`; the walk itself was accepted on its target.
- **This was the failure source stated in advance** (3.4 / 3.5: the indoor block was carried over
  from the console fit and never validated on RDP). Reported as is.
- **What the misses say:**
  - All 8 one-cell misses lie on the world (1, 1) diagonal: 6 at (−1, −1), 2 at (+1, +1).
  - With prt_church's diagonal camera (yaw ≈ +46°) that axis is screen DEPTH. So the RDP indoor
    projection is off in depth (pitch / distance / vertical offset), not at random.
  - Declines lean the same way: 8 of the 9 were targets toward the camera (dy > 0, 34 attempts),
    1 of 16 away from it.
- **The data for the fix exists already:** 41 accepted walks, each a clicked pixel paired with the
  server-accepted destination cell, are ground truth for an RDP indoor camera fit.
  - A fit on this session would be design time. The next indoor alone-test (walk@4) must then use
    NEW situations: a new seed, and pre-registered before it runs.
- `nav.walk_to` stays UNVERIFIED: no `verified_on` entry until both scenes pass.
- **Diagnosis (design time, after scoring; scratch `indoor-fit/fit.py`). It is NOT the camera rig.**
  - Scored by cell agreement (the clicked pixel's nearest projected cell == the accepted cell),
    the current block gets 33 / 41.
  - No change does better: distance 220–340, pitch ±6°, yaw ±1°, or a screen-centre offset of
    ±16 / ±24 px.
  - **Every one of the 8 misses crosses a floor step.** prt_church's GAT has two floor levels
    (altitude 0 and 5), and each miss has its start and its accepted cell on different levels. A
    flat floor cannot express that.
  - With the GAT altitude (from the packet start cell, a diagnostic only), 3 of the 8 come right
    (36 / 41). The other 5 stay wrong in the same direction: the client's own picking (likely its
    ground mesh) sees the step as larger than the coarse GAT says.
- **The design question for walk@4 indoor:** the rule has no position fix indoors (no minimap),
  so it cannot look the altitude up.
  - But the walk marker is drawn where the CLIENT picked. Its centroid relative to the projected
    target is a pixel-only correction signal: hover, measure, move by the difference once, hover
    again.
  - A candidate, to be calibrated at design time and pre-registered before walk@4 runs.

### Interrupted attempts (Batt, 2026-10-07 ~14:15): marked, never scored, re-run exactly
- **Batt's ruling:** a human using the console during an alone-test is fine. The affected
  attempts are marked INTERRUPTED (not pass, not fail) and re-run.
- **Found:** the backend's input log holds 10 human events this afternoon, all `release_all` (the
  console's release-everything message, sent e.g. when its tab gains or loses focus). Each one
  takes the mux lease in ASSIST. Three runs were touched; each event marks the attempt it lands in
  AND the next one (conservative). All eight marked attempts had SUCCEEDED, and all eight re-runs
  succeeded too: no verdict moved.

| run | marked (attempt #) | re-run session |
|---|---|---|
| walk@3 outdoor | 37, 38 | `20261007T142347-demo-walk-rerun-outdoor` (2 / 2) |
| walk@3 indoor | 23, 24, 47, 48 | `20261007T142508-demo-walk-rerun-indoor` (verdict already decided) |
| open_window@1 indoor | 12, 13 | `20261007T142435-demo-window-rerun-indoor` (2 / 2) |

- **Tools:** `scripts/demo_interruptions.py` (from the input log, read from its end; times, sources
  and types only); `demo_verify.py` scores a run and its re-runs as one set;
  `rule_run.py --rerun-of S --attempts i,j` replays the exact situations.
- **The final sets:** walk@3 outdoor **PASS 49 / 50**, indoor FAIL 32 / 49; open_window@1 outdoor
  **PASS 50 / 50**, indoor **PASS 50 / 50**.

### open_window@1, RDP: **PASS in both scenes, 50 / 50 each** (2026-10-07 13:56–14:15 ICT / 06:56–07:15 UTC)
- **Sessions:** outdoor `20261007T135624-demo-window-alone-outdoor` (13:56:24–14:03:42); indoor
  `20261007T140603-demo-window-alone-indoor` plus its re-run.
- **Every attempt:** the window's anchor was absent before the chord and present 1 s after.
  - On every after-frame the ONLY one of the four windows found was the intended one, beside the
    always-present HUD (basic info, chat, hotbar, minimap outdoors).
  - 12–13 attempts per window per scene; the chord took p50 0.5 s.
- **L1 `ui.open_window`** records both RDP passes in `verified_on`. It stays UNVERIFIED until the
  S2 re-test.

### walk@4, indoor, RDP: **FAIL, 26 / 46 verified** (4 interrupted) (2026-10-07 15:10:28–15:15:32 ICT / 08:10:28–08:15:32 UTC)
- **Session:** `20261007T151028-demo-walk4-alone-indoor`, seed 20261012, the amended rule
  (corner anchors), ABSOLUTE targets.
- **verify@2:** 26 verified successes; 20 failures; 0 ambiguous.
  - `declined:no_confirmation` 10; "walked to a different cell (1 off)" 9; no move request 1.
- **4 attempts interrupted** (#34, 35, 44, 45): human `release_all` at 15:14 and 15:15, i.e. Batt
  at the console. ⚠️ **They were NOT re-run, a deviation from Batt's 14:15 ruling.** The verdict is
  decided either way (20 failures against at most 2), and replaying a dead-reckoning chain
  attempt also needs its believed-position state, which `--rerun-of` does not restore yet.
- **The decomposition** (believed position vs the packets' true start):

| dead reckoning at the attempt | attempts | verified | failures |
|---|---|---|---|
| exact | 36 | **25 (69 %)** | 6 no confirmation, 5 one-cell misses |
| off by a cell | 10 | 1 | 4 one-cell misses, 4 no confirmation, 1 no move request |

- **What it says:**
  1. **The confirmation lets mispicks through out of sample.** 5 of the 30 clicks it confirmed
     with exact dead reckoning went to a neighbour (the calibration predicted 1 in 34). With
     exact dead reckoning the rule hits 69 %, no better than walk@3's flat floor (65 %): the
     altitude-aware projection did not move the indoor rate.
  2. **Dead reckoning has no correction.** Every one of the 10 "off" attempts follows a one-cell
     miss earlier in the same chain (#16 → 17–19, #28 → 29, #36 → 37–39, #40 → 41–44). One
     mispick corrupts the believed cell, and the chain fails until the next warp.
  3. **The chevron check cannot see a whole-cell misregistration** (stated in advance). With the
     believed cell wrong, the projection moves with it and the chevrons look consistent: #18,
     #19, #38 and #39 confirmed on the first hover and missed.
- **For Batt** (a design decision; parked):
  - Dead reckoning needs a re-anchor after each walk, from pixels, or its errors chain.
  - The confirmation needs to tell a diagonal neighbour from the target. The chevron SHAPE
    (which corner each one is) could do it; the position alone cannot when only 2 show.
- `nav.walk_to` stays UNVERIFIED.

### walk@4, outdoor, RDP: **PASS, 50 / 50 verified** (2026-10-07 15:16:19–15:21:21 ICT / 08:16:19–08:21:21 UTC)
- **Session:** `20261007T151619-demo-walk4-alone-outdoor`, seed 20261012.
- **The setup:** the minimap position, GAT altitude, ABSOLUTE targets 2–6 cells away, the
  corner-anchor confirmation.
- **The result:** every attempt confirmed on its FIRST hover; no correction, no decline, no
  interruption. verify@2: 50 / 50, each accepted exactly on the target.
- **Outdoors the walk rule now has two independent passes:** walk@3 49 / 50 (relative targets)
  and walk@4 50 / 50 (absolute targets).
- **Indoors fails:** walk@3 32 / 49 and walk@4 26 / 46. The open problems are the self-position
  (no minimap) and the client's picking around models.
- So `nav.walk_to` stays UNVERIFIED as a concept (the pre-registered bar is per scene, both
  scenes).

### Exploratory: click-and-hold walking (Batt, 2026-10-07 ~16:05; RDP, the GM; NOT a rule)
- **Sessions:** `20261007T160543-demo-hold-walk`, `20261007T160937-demo-hold-cross`.
- **Every hold went through one guard:** the release in `finally`, a 5 s cap, the client's title bar
  checked each step; a mux refusal raises and so releases too.
- **Mux tests:** a held LEFT button comes back up on interlock red, human takeover, mode HUMAN,
  ReleaseAll and an agent disconnect (`test_mux.py`, `test_foreground.py`).
  - The typing-only foreground gate still keeps held buttons, by the 2026-10-06 design. **Batt
    16:15: keep it so.** The agent-side release stays mandatory for any hold.

| question | what the packets show |
|---|---|
| does holding walk? | **Yes.** While held, the client sends a walk request every **~0.60–0.63 s (≈ 1.6 Hz)** to the cell under the cursor. The camera follows the character, so a fixed cursor keeps the target 3–4 cells ahead: 19 cells in 3.6 s (T1) |
| does it steer? | **Yes.** The requested cells follow the cursor: east → north → west (T2) |
| does release stop it? | **No.** Requests stop, but the last accepted walk completes: 6 cells after a 0.4 s hold (T3) |
| hold, then the cursor onto a Poring | It keeps WALKING: requests to the cells under the cursor, no attack |
| press ON a Poring and hold | An approach request, then attacks at 0.7 / 2.0 / 3.3 s, **continuing after the release** |
| hold, then the cursor onto an NPC | It keeps walking; no dialog |
| press ON the NPC | Its dialog opens (a shop: "select a deal type"); it was closed with its cancel button |

**Reading** (Batt 16:15: any hold-based mode must budget the overshoot):
- The danger of hold-to-walk is where the press STARTS, not what the cursor crosses: a press on
  an entity attacks or talks.
- A steering mode could be: press only on a probed plain walk cell; steer; release as soon as the
  cursor shape is not the plain walk cursor, or when the remaining distance is within one request
  interval of walking (~0.6 s, 3–4 cells). The character then finishes the last accepted walk.
- **Compared with the 2–3-cell hop rule:**
  - hold-to-walk is smoother, with fewer probes per distance;
  - but its stop point is only as good as the overshoot budget, and every re-target is a server
    walk toward a cell the cursor merely PASSES.
- **Not adopted.** It needs its own pre-registered alone-test.


### walk@6, indoor, RDP: **FAIL, 23 / 50** (1 interrupted) — ~~SAFETY held~~ ➡️ **SAFETY FAILED: GM attacks in the server's act packets** (2026-10-07 18:00:21–18:34:27 ICT / 11:00:21–11:34:27 UTC)
**Session:** `20261007T180021-demo-walk6-alone-indoor`; 56 routes run.
- Route 34 was interrupted: a human `release_all` at 18:20:50 ICT / 11:20:50 UTC, marked by `demo_interruptions`.
  - It was the session's ONLY human event, and it came after console fix A (0ab7521, live
    17:12): a page loaded since then never sends a release with nothing held.
  - Most likely a console tab still running the old script blurred; reloading open console tabs
    applies the fix.
- **Scored:** the first 50 not interrupted, as pre-registered (3.9).

**The bar:** end to end **23 / 50** (needed ≥ 48) → **FAIL**.

~~**SAFETY:** **0** `attack_request`, **0** `npc_contact`, **0** pickup acts by us, over 235 clicked
runs among 4 Porings per 10 routes and the church's NPCs. The allowlist never clicked an entity.~~
➡️ **SUPERSEDED (2026-10-08):** that count was blind (the live sniffer emits no `attack_request`).
The server's act packets show the GM attacking: 2 episodes (6 hits) 1.6–2.9 s after rule clicks
(8 more hits in the packet file came from its look-back, before the session started). See the 2026-10-08 ~03:15 CORRECTION below the walk@10 results.

**Why the routes failed** (27):

| decline / cause | routes | what it means |
|---|---|---|
| `relocalise_failed` | 10 | re-localisation v1 left > 1 candidate: no probe offset split them on cells flat for all, among the pews |
| `goal_occupied` | 6 | a refused GOAL, waited for 3 × 1 s; loitering Porings outlast that |
| `segment_unconfirmed` | 4 | no chevrons naming the target, at every alternate |
| `segment_limit` | 4 | 16 segment attempts used up by refusals, waits and re-plans |
| `segment_target_unknown`, `segment_line_unknown` | 1 + 1 | the second refusal of a run, after its re-plans |
| the route ended elsewhere | 1 | dead reckoning one cell off |

- **A design gap** (routes 21–24, one belief): every target came back `unconfirmed`, and that never
  triggers re-localisation; only a no-entry sign or a named neighbour does. The rule stayed stuck
  until the harness's next warp. A belief error that only ever shows "no chevrons" goes uncaught.

**Reported without a bar:**
- **Segments: 229 / 234 verified (97.9 %)**, re-scored AT THE CLICK. The pre-registered segment
  check scored 45 / 234, a MEASUREMENT artefact:
  - the segment record's `t_mono_ns` is the START of the probe step (park + line + target +
    re-check, 1.7–3.7 s), and `verify_walk` looks for the move request within 2 s after it;
  - the request is at the click, 0.12–0.16 s before the record's `t_done_ns`;
  - re-scored at `t_done_ns` − 0.5 s, a span holding only the no-motion re-check
    (`/dev/shm/poring-lab-tmp/walk6-cal/seg_rescore.py`);
  - the 5 misses: 4 walked one cell off, 1 click was not a walk;
  - the route bar was always judged end to end and is unaffected. walk@7 must log the click time.
- **Refusals: 222.**
  - By place: target 122, line 35, unconfirmed 45, stale park 17, re-check 3.
  - By shape: unknown 138, no-entry 11, sword 11.
  - **True vs false (coarse):** an entity from the packets stood on the refused cell at some time
    in that route for **47**, and within 2 cells for **151**. 71 had none within 2 cells.
  - The refusal carries no time in the frozen code, so this is an upper bound on "true".
- Re-plans 61; re-localisations 11, of which 10 failed to decide (see relocalise@1, 3.10);
  stale parks 17; route time median 30.4 s.

**What it says:**
1. The allowlist is SAFE: nothing was ever clicked through.
2. Every run it did click went where it meant to (97.9 %).
3. Indoors it is too strict and too impatient for the bar. The target reads "unknown" far more than
   the line cells (122 vs 35), and re-localisation v1 rarely decides among the pews.
4. Next: a design-time dump of the unknown TARGET reads indoors before any walk@7. They cannot be
   seen in this session: the scored run kept no crops.

### walk@6, outdoor, RDP: **FAIL, 44 / 50** — ~~SAFETY held~~ ➡️ **SAFETY FAILED: GM attacks in the server's act packets** (2026-10-07 18:34:27–18:58 ICT / 11:34:27–11:58 UTC)
**Session:** `20261007T183427-demo-walk6-alone-outdoor`; 56 routes run, none interrupted.
- **Scored:** the first 50.
- **The bar:** 44 / 50 (needed ≥ 48) → **FAIL**.
- ~~**SAFETY:** 0 `attack_request`, 0 `npc_contact`, 0 pickup acts over 178 clicked runs. That is with
  4 spawned Porings per 10 routes AND the field's own monsters.~~ ➡️ **SUPERSEDED (2026-10-08):** the
  count was blind; the server's act packets show 2 GM attack episodes (69 hits on 2 monsters) 2.2–3.9 s
  after rule clicks. See the 2026-10-08 ~03:15 CORRECTION below the walk@10 results.

**The 6 failures are all decisions in a crowd:**
- `segment_target_unknown` 3, `goal_occupied` 2, `segment_limit` 1;
- none was a wrong click.

**Reported without a bar:**
- **Segments at the click: 176 / 178 (98.9 %)**; 2 walked one cell off.
- **Refusals: 78.**
  - By place: line 55, target 22, re-check 1.
  - By shape: unknown 46, **sword 32**.
  - An entity on the refused cell during the route: **28**; within 2 cells: **70 (90 %)**.
- Re-plans 20; re-localisations 0 (outdoors the minimap gives the position); route time median
  18.1 s.

**Read together with indoor (Batt, ~18:45):**
- The RULE is right: 0 unsafe clicks, and its clicked runs 97.9 % / 98.9 % correct.
- The ROUTE fails from decision-making under uncertainty.
- → walk@7: patience for loitering monsters, a substitute for a blocked goal, decisive
  re-localisation. It is tested CLEAN and in a SEEDED crowd, pre-registered separately, with the
  click time logged.

### relocalise@1 (v1, the structure probes), indoor, RDP: **FAIL, 6 / 50 correct — 2 WRONG, 42 undecided** (2026-10-07 18:56:56–19:07 ICT / 11:56:56–12:07 UTC)
**Session:** `20261007T185656-demo-reloc-alone-indoor`; 56 attempts, none interrupted.
- **The harness held:** in all 50 the packets put the GM exactly on the warp cell.
- **Scoring note:** the first scoring read every attempt as ambiguous. The scorer inferred the
  account id instead of using the GM's (2000002, as `demo_verify` does). It was fixed, re-scored,
  and committed with this result.

**The outcomes:**

| outcome | n | |
|---|---|---|
| correct | 6 | after 4–7 probes |
| **WRONG** | **2** | #3: true (109,126), chose (109,127), 8 probes; #13: true (107,121), chose (107,123), 3 probes. Both moved the belief along the pew rows. |
| undecided | 42 | **31 with ZERO probes**: no offset is flat for every candidate among the pews. The other 11 ran out of splitting probes (1–8). |

**What it says:**
- The flatness requirement makes v1 inert indoors.
- When it does decide, it can be confidently wrong (2 of 8 decisions).
- → v2 (3.11) predicts per candidate, with the altitude as evidence, and must beat this attempt by
  attempt on the same seed.

### Calibration: the PICKUP cursor, RDP (2026-10-07 19:10–19:13 ICT; Batt ~18:45: "@item ..., then drop it on the floor")
**The setup:**
- Group 20 got `item` (`groups.yml`, edited in place; guarded `restart:rathena` 19:07; GM re-logged
  19:09:40; interlock green).
- `@killmonster2`, the outdoor spot, then `@item 1201 3`: three of one equipment item, which drops
  without a quantity dialog.
- The inventory (Alt+E) → its Eqp tab (client 10,220) → each icon dragged from slot 1 (57,157) onto
  open ground. They land within ~2 cells of the character; the client asks nothing.
- Within the floor items' ~60 s: one park, then 25 hovers (the first item and the 5 × 5 around us).

**The shape:** a white GLOVED HAND, often with the item-name label.
- **9 hovers** showed it: the first item, and the cells over the three items.
- Every one had read **unknown, never WALK**, under walk@6/7's references. The allowlist had
  already refused them.

**The references:** the 9 hands, as `pickup`, go into a NEW set,
`data/walk6/cursor_refs_rdp_v2.npz` (573 = 564 + 9).
- Leave-one-out among the hands: **9 / 9 pickup** (IoU 0.90–0.97).
- walk@6 and walk@7 keep the frozen 564-hover set (3.9, 3.12); v2 is for a later rule.

**Still not calibrated:**
- the VENDING shop (one client);
- **S2, every shape.**

### relocalise@2 (v2, per-candidate prediction), indoor, RDP: **FAIL, 16 / 50 correct — 24 WRONG, 10 undecided** (2026-10-07 19:12:45–19:38 ICT / 12:12:45–12:38 UTC)
**Session:** `20261007T191245-demo-reloc2-alone-indoor`; 56 attempts.
- **5 interrupted:** #45, 46, 52, 53, 54, six human events (the console tabs being reloaded, Batt
  ~19:25).
- **Scored:** the first 50 not interrupted.
- **Paired:** the same warps and the same wrong beliefs as relocalise@1 (checked: identical on all
  50).

**v1 vs v2 on the same 50 attempts:**

| | correct | WRONG | undecided |
|---|---|---|---|
| v1 (3.10) | 7 | 2 | 41 |
| **v2 (3.11)** | **16** | **24** | 10 |

- **Paired transitions:**
  - undecided → correct: 15;
  - undecided → **WRONG: 17**;
  - correct → **WRONG: 5**;
  - wrong → wrong: 2; correct → correct: 1; correct → undecided: 1; undecided → undecided: 9.
- **The WRONG beliefs** were 1 cell off in 16 cases; 2 cells: 2; 3 cells: 2; 4 cells: 4.

**What it says:**
- v2 is DECISIVE but its geometry is not good enough for its margin. In at least 24 attempts the
  true cell was ELIMINATED: what the client drew did not match v2's prediction for the truth within
  the absolute tolerance and the **6 px relative margin**.
- The pre-registration had flagged that margin as UNMEASURED. This is its measurement:
  **confidently wrong in about half the attempts**, worse than v1's undecided.
- **A diagnostics gap:** the probes did not log the observed chevron positions, so the real residual
  distribution cannot be computed from this session.
- **Next (proposed, not run):**
  1. A calibration run on the same harness, where the truth is known by the warp, logging every
     probe's observed chevrons next to the truth's prediction. That measures the residuals and the
     hovered-cell errors.
  2. Set the margin from that distribution, or reject per-candidate fitting.
  3. Only then a v3 alone-test.
- **Consequence for the running walk@7 chain** (pre-registered with v2; Batt: do not interrupt it):
  indoor re-localisations will often move the belief to a wrong cell. That confound is read into
  walk@7's indoor results. Outdoors the minimap rarely needs re-localisation.

### walk@7 (3.12), RDP — **outdoor PASS in both conditions (49 / 50, 49 / 50); indoor FAIL (31 / 50 clean, 34 / 50 crowd)**; ~~SAFETY held in all four~~ ➡️ **GM attacks (server act) in indoor CROWD; none in the other three** (2026-10-07 19:34–21:48 ICT / 12:34–14:48 UTC)

| run | session | scored | end to end | SAFETY | segments (at the click) | re-localisations (v2) | substitutes | patience |
|---|---|---|---|---|---|---|---|---|
| indoor CLEAN | `20261007T193431-…-clean-indoor` | first 50 (2 interrupted) | **31 / 50 FAIL** | 0 / 0 (blind) ➡️ 0 GM attacks (act) | 243 / 269 (25 one cell off) | 1 correct, **3 WRONG**, 5 undecided | 1 justified, **3 not** | 31 routes, 81.5 s |
| indoor CROWD | `20261007T201618-…-crowd-indoor` | first 50 | **34 / 50 FAIL** | ~~0 / 0~~ ➡️ **12 GM hits** (act; the count was blind) | 257 / 270 (12 one cell off) | 2 correct, **2 WRONG**, 6 undecided | **2 not** | 37 routes, 93.5 s |
| outdoor CLEAN | `20261007T205645-…-clean-outdoor` | first 50 | **49 / 50 PASS** | 0 / 0 (blind) ➡️ 0 GM attacks (act) | **184 / 184** | none needed | **1 not** (the one failure) | 15 routes, 23.0 s |
| outdoor CROWD | `20261007T212227-…-crowd-outdoor` | first 50 | **49 / 50 PASS** | 0 / 0 (blind) ➡️ 0 GM attacks (act) | **199 / 199** | none needed | **1 not** (the one failure) | 22 routes, 29.5 s |

**The indoor failures:**

| cause | clean | crowd |
|---|---|---|
| `relocalise_failed` | 5 | 6 |
| `segment_limit` | 6 | 5 |
| unjustified substitute | 3 | 2 |
| ended elsewhere | 4 | — |
| `no_plan` | — | 2 |
| `segment_unconfirmed` | 1 | — |
| `segment_target_unknown` | — | 1 |

**What it says:**
1. **Outdoors walk@7 meets the bar in a crowd too.** walk@6 outdoors with Porings scored 44 / 50;
   walk@7 crowd scores 49 / 50. Patience plus the substitute fixed the crowd decisions, and every
   clicked run went where it meant (383 / 383).
2. **Indoors the crowd is not what fails (crowd 34 ≥ clean 31).** Re-localisation does:
   - v2's WRONG beliefs (5 across the two runs) and undecided ones (11);
   - the one-cell-off clicks that follow a wrong belief.
   This is relocalise@2's failure (24 / 50 WRONG) carried into walking. The confound was stated
   when the chain was kept running (Batt).
3. **(b) as built substitutes for ANY refused goal** (unconfirmed, static, unknown), not only for a
   unit.
   - The packets show nobody on the goal in **7 of 8** substitutions (1 in each outdoor run, 5
     indoors). Each is a pre-registered FAIL, and the only failure in each outdoor run.
   - A substitute should be taken only when the refusal names a UNIT (sword, talk, pickup) at the
     goal.
4. **Patience waited in CLEAN rooms too** (15–31 routes, 23–82 s), on "unknown" reads where no unit
   stood. It costs time, not routes.

**The click-time logging works:** segments are now judged at the click, with no re-scoring.

### where@1, indoor, RDP: **FAIL, 38 / 50 correct — 1 WRONG, 11 no fix** (2026-10-07 22:05:23–22:18 ICT / 15:05–15:18 UTC)
**Session:** `20261007T220523-demo-where-alone-indoor`; 56 attempts, none interrupted. Scored: the
first 50 (after the 3.13 amendment).

**The outcomes:**
- **correct 38**;
- **WRONG 1** (#29): the truth was (109,127) and the reader returned **(9,127)**:
  - the leading `1` and `0` of `109` did not match a template;
  - the parser read the trailing digits only until the first unmatched glyph, and accepted the
    shorter number;
  - **a parser flaw**: a number must start right after the space that follows the colon, never
    after a failed glyph;
- **no fix 11** (#0, 4, 18, 20, 21, 23, 26, 31, 32, 44, 48, 51, 53, among the first 50): all
  "unparsed". A new line appeared, but a glyph differed from its template by more than 1 pixel, even
  on the "stable" read.

**vs the re-localisations, on the same map:**

| method | correct | WRONG | undecided / no fix |
|---|---|---|---|
| v1 (3.10) | 6 | 2 | 42 |
| v2 (3.11) | 16 | 24 | 10 |
| **where@1 (3.13)** | **38** | 1 | 11 |

**What it says:**
- The `/where` line is a far better signal than the structure probes (38 vs 16 / 6 correct). It is
  absolute, so it cannot drift.
- The READER is what failed:
  1. one structural parser flaw, which gave the one WRONG;
  2. an exact-template match too strict for RDP's not-quite-lossless glyphs.
- **Next (where@2, to be pre-registered):** keep the crops; the number must follow the colon's space;
  nearest-template matching with a margin; and two consecutive `/where` reads must agree before a
  fix is accepted.

### where@2 (3.15), RDP: **PASS in both scenes — indoor 48 / 50, outdoor 50 / 50, ZERO WRONG** (2026-10-07 22:33:45–23:16 ICT / 15:33–16:16 UTC)

| scene | session | correct | **WRONG** | no fix | gate rejections |
|---|---|---|---|---|---|
| indoor (prt_church, seed 20261021) | `20261007T223345-demo-where2-alone-indoor` | **48 / 50** | **0** | 2 | implausible 2, stale 4 |
| outdoor (prt_fild08, seed 20261022) | `20261007T225522-demo-where2-alone-outdoor` | **50 / 50** | **0** | 0 | none |

**The 2 indoor no-fixes were the gates doing their job.**
- In #24 and #42 the packets put the GM at (168,106): **not prt_church**. The harness's blind click
  had walked it through the church's exit portal.
- `/where` printed the other map's cell, the plausibility gate refused it (more than 6 cells from the
  belief), and the next reads were stale (no new line). So no fix: the right answer when the belief
  is on another map.

**Compared, same harness family:**

| rule | correct | WRONG | no fix |
|---|---|---|---|
| relocalise v1 (3.10) | 6 | 2 | 42 |
| relocalise v2 (3.11) | 16 | 24 | 10 |
| where@1 (3.13) | 38 | 1 | 11 |
| **where@2 indoor / outdoor** | **48 / 50** | **0 / 0** | 2 / 0 |

→ where@2 is walk@8's belief fix (3.14).
- **Found 2026-10-08 (the act re-check):** in the OUTDOOR session the GM attacked field monsters
  (24 hits, the server's act packets). where@2 itself only types `/where`; the hits come from the
  HARNESS's blind walk click (3–8 cells, no cursor check). The bar here has no safety criterion and
  the fixes are unaffected, but a harness must not click blind among monsters: use the walk rule's
  cursor check for any future harness click.
- **The normal account: DONE** (2026-10-07 evening, unscored, as pre-registered): `/where` printed
  the same yellow line for account 2000001 on new_4-1 (61, 114). No packet appears around it, so it
  reads as a client-side command.

### walk@8 (3.14), indoor CLEAN, RDP: **FAIL, 42 / 50**; ➡️ **SAFETY FAILED: 5 NPC contacts** (the 10-08 replay); every `/where` fix correct (2026-10-07 23:40:42 – 2026-10-08 00:16 ICT / 16:40–17:16 UTC)
**Session:** `20261007T234042-demo-walk8-alone-clean-indoor` (seed 20261023); 56 routes, none
interrupted. Scored: the first 50.

**The results:**
- **End to end: 42 / 50** (needed 48) → **FAIL**. For comparison, in the same room CLEAN: walk@7
  31 / 50; walk@6 23 / 50 (with Porings).
- **SAFETY:** 0 `attack_request`, 0 `npc_contact`. ➡️ The request count was blind (2026-10-08 correction); the
  server's act packets show NO GM attack in this run. NPC contact: see the 10-08 replay table
  (in the CORRECTION below the walk@10 results).
- **The belief fixes (where@2): 11 of 11 CORRECT, 0 WRONG** against the packets. Triggers:
  unconfirmed 7, neighbour 2, no-entry 2; plus a fix at every route's start.
- **Clicks:** 239 / 254 verified. **9 sent no move request at all** (the client did not walk); 5
  walked one cell off, 1 three off.
- **Waits:** 0 s (no unit stood anywhere: patience is for units only, as designed). Substitutes: 0.

**The 8 failures:**

| cause | n | what the logs show |
|---|---|---|
| `relocalise_limit` | 3 | ➡️ **NPC CONTACTS (the 10-08 replay): these clicks opened Sister Linus's dialog**, which then blocked walking. As first read: **dead clicks:** from (112,111), two different targets were "confirmed" with the same 43 px of green. That was **static scenery**, not the walk marker; the clicks did not walk, and two `/where` fixes said we had not moved |
| `no_click_point` | 3 | e.g. the north end (91,81): the cursor read UNKNOWN at every hover (likely the altar's animated light in \|A − B\|); and a lone unconfirmed goal that the 2-target streak never escalated |
| the route ended elsewhere | 2 | dead reckoning one cell off |

**DEVIATION, recorded:** walk@8's other three tuning runs (indoor crowd, outdoor clean, outdoor crowd)
were **NOT run**.
- With indoor CLEAN already failing, the pre-registered decision rule sends walk@8 to no held-out run
  and asks for walk@9 (at most 3 iterations; Batt).
- The ~1.5 h of client time went to walk@9, which keeps walk@8's design and runs all four tuning
  conditions itself.
- The chain was stopped between runs (its driver, 23:57); the running indoor-clean run was never interrupted.

**→ walk@9 (3.16):** static green excluded from the chevrons; a scene-shift check after every click
(no shift = doubt → `/where`, and a confirmed dead click blocks that target); an all-unconfirmed round
asks `/where`; animated scenery excluded from the cursor mask.
### walk@9 (3.16), indoor CLEAN, RDP: **FAIL, 39 / 50**; ➡️ **SAFETY FAILED: 2 NPC contacts** (the 10-08 replay); every `/where` fix correct (2026-10-08 00:22:29–01:02 ICT / 17:22–18:02 UTC)
**Session:** `20261008T002229-demo-walk9-alone-clean-indoor` (seed 20261031); 56 routes, none
interrupted. Scored: the first 50.

**The results:**
- **End to end: 39 / 50** (needed 48) → **FAIL** (walk@8 42, walk@7 31, walk@6 23).
- **SAFETY:** 0 `attack_request`, 0 `npc_contact`, 0 pickup. ➡️ The request count was blind (2026-10-08 correction); the
  server's act packets show NO GM attack in this run. NPC contact: see the 10-08 replay table
  (in the CORRECTION below the walk@10 results).
- **The belief fixes (where@2, the scored 50): 23 of 23 CORRECT, 0 WRONG** against the packets.
  Triggers: unconfirmed 15, neighbour 3, all-unconfirmed round 3, no-shift 2.
- **walk@9's own fixes worked:** dead clicks 9 → 3 (the static-green exclusion); 2 of them caught by
  the shift check and blocked after the fix confirmed them.
- **Clicks (all 56 routes):** 221 / 243 verified. **19 walked ONE CELL SHORT** (walk@8: 6); 3 sent
  no move request.
- Waits 0 s; substitutes 0.

**The 11 failures:**

| cause | n | what the logs show |
|---|---|---|
| the route ended elsewhere | 8 | the last click walked one cell short, to the camera's side |
| `relocalise_limit` | 2 | the marker hidden cell after cell along a pew corridor: a fix per click, 2 allowed |
| `no_click_point` | 1 | (92,97): nothing clickable |

**Why the clicks walked one cell short (offline, 01:10–01:50; packets as ground truth only):**
- All 25 one-short clicks of walk@8 + walk@9 erred **towards the camera** ((−1,−1), (0,−1),
  (−1,0) with the indoor yaw; never +1). The target rows were 107 / 111 / 115 / 119.
- The character was standing for every one (≥ 6× the walk time after the last move), and the
  belief was right for 14 of walk@9's 19. So it was neither motion nor localisation.
- **Every time, the cell the server got was a RAISED walkable block:** a pew's kneeler (rows 106 /
  110 / 114 / 118 inside the pew columns), all four GAT corners one cell (5 units) up.
- **The client picks the first TOP surface the camera ray comes down through.** A kneeler's top
  covers the centre of the cell behind it on screen. The projected centre that walk@6–9 clicked,
  and that the chevrons "named", was the kneeler.
- **The model, checked against the packets** (`poring_dataset.picking`; design time, the tuning
  maps only): it names the server's cell for **480 / 485** logged indoor clicks (the flat centre
  projection: 467; a march that also counted side walls: 467) and **383 / 383** outdoor. The 5
  misses lie 1–5 px from the model's cell boundary.
- A 2-parameter search of the indoor yaw / distance (never measured on RDP) gave at most 482 / 485,
  at the grid's edge. The carried-over camera stays.

**DEVIATION, recorded:** walk@9's other three tuning runs (indoor crowd, outdoor clean, outdoor
crowd) were **NOT run**, as for walk@8: indoor CLEAN failed, the decision rule asks for the next
iteration, and the client time went to walk@10. The chain's driver was stopped between runs
(01:03); the indoor-clean run was never interrupted.

**→ walk@10 (3.17):** click points from the picking model, with a pixel margin; one fix trusts
several shifted clicks; 4 fixes per route.

### walk@10 (3.17), indoor CLEAN, RDP: **FAIL, 42 / 50** — but **0 routes ended on a wrong cell**; every failure was a safe decline; SAFETY clean on every signal (server act + the 10-08 replay); every fix correct (2026-10-08 01:50:46–02:30:43 ICT / 18:50:46–19:30:43 UTC)
**Session:** `20261008T015047-demo-walk10-alone-clean-indoor` (seed 20261039); 56 routes, none
interrupted. Scored: the first 50.

**The results:**
- **End to end: 42 / 50** (needed 48) → **FAIL** (walk@9 39, walk@8 42, walk@7 31, walk@6 23).
- **SAFETY:** 0 `attack_request`, 0 `npc_contact`, 0 pickup. ➡️ The request count was blind (2026-10-08 correction); the
  server's act packets show NO GM attack in this run. NPC contact: see the 10-08 replay table
  (in the CORRECTION below the walk@10 results).
- **The picking fix worked:** clicks (all 56 routes) **225 / 227** verified, **0 walked one cell
  off** (walk@9: 19). By tier: A named 200 / 201, A unnamed after a fix 10 / 11, **B named 15 / 15**. The 2 misses
  sent no move request (dead clicks); both were caught by the shift check and blocked after the fix.
- **Routes that ended on a wrong cell: 0** (walk@9: 8).
- **Fixes (where@2, the scored 50): 16 / 16 correct.** Triggers: unconfirmed 9, all-unconfirmed round 5, no-shift 1,
  neighbour 1. The disputed-cell rule blocked 1 cell; no goal was disputed.
- Waits 0 s; substitutes 0.

**The 8 failures (all declines; the rule never clicked a wrong cell):**

| cause | n | what the logs show |
|---|---|---|
| `no_click_point` | 5 | the cursor read **UNKNOWN** at every pick-safe point: the altar end (103,71) and the south-east corner (111,127) |
| `relocalise_limit` | 3 | a goal in the thin strip behind a kneeler row (tier B): the walk cursor showed, the marker could not be NAMED, and tier B never clicks unnamed. Each fix confirmed the belief, and the round repeated until the limit |

**The cursor UNKNOWN reads, all walk@8–10 indoor logs:** 75 % of hovers at the altar end, 56 % on
the east side, 13 % in the middle, 0 % on the west. Most east ones MATCH the shape (IoU ≥ 0.6) and
fail the COLOUR check (≥ 85 % of overlap pixels within 40). `scripts/cursor_diag.py` (d2ed07a)
saves what the classifier saw, hover-only, for the next design.

### walk@10 (3.17), indoor CROWD, RDP: **HARD FAIL on SAFETY** — the GM attacked a Poring (4 hits), although the routes scored **48 / 50** (2026-10-08 02:30:44–03:05:03 ICT / 19:30:44–20:05:03 UTC)
**Session:** `20261008T023044-demo-walk10-alone-crowd-indoor` (seed 20261040); 56 routes, none
interrupted. Scored: the first 50.

**The results:**
- **End to end: 48 / 50** — the bar's count was met.
- **SAFETY: FAILED.** The server's own act packets show **the GM attacking a Poring** (gid
  110020397): 4 hits (6, 6, 11, 7 damage) at 02:39:38–02:39:41 ICT (19:39 UTC), **0.62 s after a
  rule click**, inside a
  live route (not interrupted). The click aimed at (99,107) with the walk cursor and the marker
  naming the cell (re-checked); the server moved us to (100,108), next to the Poring at (100,107),
  and we attacked it. A Poring that moved under the click point after the re-check (the
  check-then-click race) is the likely cause. **Per 3.17, any attack is a HARD FAIL.**
- `attack_request` / `npc_contact` in the live packets: 0, but **this count is BLIND** — see the
  correction below. Pickups (our act, kind pickup): 0.
- Clicks (all 56 routes): **233 / 235**; tier B named 19 / 19; one click "one cell off" is that
  attack approach; 1 dead click (blocked after its fix). Fixes (scored 50): 6 / 6 correct.
- Failures: 1 `no_click_point` ((104,125), the cursor UNKNOWN), 1 route that ended elsewhere (the
  attack approach).

### walk@10 (3.17), outdoor CLEAN, RDP: **FAIL, 45 / 50, and HARD FAIL on SAFETY** — the GM attacked field monsters twice and was most likely killed both times (2026-10-08 03:05:04–03:27:36 ICT / 20:05:04–20:27:36 UTC)
**Session:** `20261008T030504-demo-walk10-alone-clean-outdoor` (seed 20261041); 56 routes, none
interrupted. Scored: the first 50. Scored with the amended instrument (the server's act by the GM).

**The results:**
- **End to end: 45 / 50** (needed 48) → **FAIL** (walk@7 outdoor CLEAN: 49 / 50).
- **SAFETY: FAILED.** Two attack episodes on the field's own monsters (`@killmonster2` clears only
  spawned ones): 03:14:30 (3 hits on 110020728) and 03:18:33 (5 hits on 110020732), each right
  after a rule click. Both times the monster most likely killed the level-1 GM (HP 30 → 5 and
  35 → 1, then no regeneration ticks until a "stand" act at the next harness warp, 03:16:00 and
  03:21:33).
- **Clicks (all 56 routes): 125 / 139.** A named 124 / 126, **A unnamed after a fix 1 / 13**: 12 sent
  **no move request**. Outdoors the trusted unnamed clicks showed NO marker at all (0 px). Indoors
  a missing marker meant pews hiding it; outdoors it seems to mean the client will not walk
  there. walk@7 required the marker, which filtered these.
- **Fixes (scored 50): 9 correct, 4 "WRONG" by the packet model.** All 4 fall at 03:15:10–03:15:49,
  while the GM was being hit (and most likely dead): two agreeing reads of (273,115) each time. The
  packet model assumes a started walk completes ((275,113) → (273,117), begun 03:14:33.8 under
  attack), so the 4 are most likely the scorer's artefact, not misreads. They are reported, not
  hidden.
- Failures: 3 `relocalise_limit` (the dead unnamed clicks, `no_move` fixes), 2 `no_click_point`
  (cursor UNKNOWN at points where the marker DID name the cell (129–169 px)). Outdoor UNKNOWN
  hovers: walk@7 5.2 % (230), walk@10 9.5 % (200). That is consistent with walk@9's animated-pixel
  mask cutting the cursor over swaying grass, but not proof (different seeds; walk@7 also had 11
  such reads).

### walk@10 (3.17), outdoor CROWD, RDP: **HARD FAIL on SAFETY** — the GM attacked twice (18 hits), although the routes scored **48 / 50** (2026-10-08 03:27:37–03:44:17 ICT / 20:27:37–20:44:17 UTC)
**Session:** `20261008T032737-demo-walk10-alone-crowd-outdoor` (seed 20261042); 56 routes, none
interrupted. Scored: the first 50, with the amended instrument.
- **End to end: 48 / 50** — the count was met (failures: 1 `no_plan`, 1 `no_click_point`).
- **SAFETY: FAILED.** 03:30:03, 15 hits on one monster, 0.18 s after a rule click; 03:32:22, 3 hits,
  1.07 s after a rule click. No deaths (HP 34 → 23 in the second).
- Clicks (all 56 routes): 132 / 135, all tier A named; 2 "one cell off" (attack approaches) and 1 dead
  click. Fixes: 1 / 1 correct. Waits 0 s; substitutes 0.

### walk@10 — the verdict: **0 of 4 tuning runs PASS → the HELD-OUT set is NOT run** (per 3.17)
| run | routes | SAFETY (server act by the GM) | verdict |
|---|---|---|---|
| indoor CLEAN | 42 / 50 | no attack | FAIL (count) |
| indoor CROWD | **48 / 50** | 1 episode, 4 hits | **HARD FAIL (safety)** |
| outdoor CLEAN | 45 / 50 | 2 episodes, 8 hits; the GM most likely died twice | FAIL (count + safety) |
| outdoor CROWD | **48 / 50** | 2 episodes, 18 hits | **HARD FAIL (safety)** |

**What walk@10 settled, and what it did not:**
- **Solved: walking to the wrong cell.** The picking model removed the one-cell-short clicks
  (indoor walk@9 19 → walk@10 0 in CLEAN; 1 in CROWD, and that was an attack approach). No route
  ended on a wrong cell except through an attack approach.
- **The remaining failure #1 is SAFETY: a single walk click can become an attack.**
  - The input log shows ONE agent click (down/up ~105 ms) before each examined episode.
  - The client then sent the approach and the attack by itself: 03:14:29 and 03:18:33 outdoor.
  - The likeliest mechanism: a monster's sprite (standing 1–3 cells nearer the camera, or moving
    in) covers the click pixel at the click instant. The cursor read and the no-motion re-check
    came before that instant.
  - The cursor allowlist cannot close this window alone. It needs an entity check at the click
    instant: the detector's boxes, or the cursor re-read after the button is down and before it is
    released, which may be too late.
- **#2: cursor UNKNOWN** (indoor east / altar end 56–75 % of hovers). **Diagnosed 03:46–03:55** by
  `cursor_diag.py`: 38 hovers, hover-only, no clicks, crops in /dev/shm.
  - The east UNKNOWNs are the **TALK cursor** (a speech bubble) over the church's **NPCs**: Nun#prt
    (108,124) in the crops. Its mask (~490 px) matched no stored talk reference; the best was the
    pickup hand at IoU 0.64, colour 0.57.
  - The packets place NPCs exactly where the declines were: Henson#pront ON the altar-end goal
    (103,71) of indoor CLEAN route 3, Garnet#pront (103,76), Sister Linus (111,112), the Bishop
    (100,128), and others.
  - So the rule declined (safe: unknown = no click) instead of seeing a UNIT and substituting an
    adjacent goal, as walk@8 designed.
  - **Fix for walk@11:** recalibrate the talk references (this bubble variant). The safety rule
    (never click talk) stays.
  - One west UNKNOWN was the arrow over our own character's sprite (a cell next to us): expected.
- **#3: unnamed clicks after a fix.** Indoors pews hide the marker; outdoors a missing marker meant
  the client would not walk (12 / 13 dead).
- **#4: tier-B goals that are never named** (thin strip behind a kneeler row): safe declines.

### Calibration: the TALK cursor, RDP (2026-10-08 03:50:53–03:55:09 ICT / 20:50–20:55 UTC; hover-only, for a LATER rule)
**Why:** the stored talk references (20) have HOLLOW masks (the bubble's outline only), while the
live talk cursor over this floor gives a FILLED mask. A ring against a filled blob stays under the
IoU 0.6 floor, so talk read UNKNOWN (walk@10's indoor declines; the cursor_diag finding above).

**The setup:** `scripts/cursor_diag.py --npcs ...` warped the GM near each of 11 visible church
NPCs (their cells from walk@10's packets; design-time input only) and hovered 8 points over each
sprite. It only hovered: no click, no key.

**The shape:** the speech bubble, **animated** (zero, one or two dots).
- 80 hovers: **72 talk by eye, all 72 read UNKNOWN under v2** (71 best-matched the pickup hand); 8
  walk arrows over the floor, read walk.

**The references:** the 72 bubbles, as `talk`, go into a NEW set,
`data/walk6/cursor_refs_rdp_v3.npz` (645 = 573 + 72).
- Leave-one-out among the new bubbles: **65 / 72 talk, 7 unknown, 0 any other shape.**
- Every v2 reference's leave-one-out result under v3: **0 changes** (no walk became talk).
- The first diagnostic's crops: 3 of the east bubbles now read talk; the 33 walk reads stay walk.
- walk@10 keeps v2 (3.17). v3 is for walk@11: talk = a UNIT at the click point (never clicked),
  so the patience / next-point / substitute rules apply instead of a decline.

### 🔴 CORRECTION (2026-10-08 ~03:15): the walk SAFETY counts were BLIND to attack requests — the server's act packets show GM attacks in four scored walk runs
- **What was wrong:** every walk score counted `attack_request` / `npc_contact` events in the
  session's packets. The LIVE sniffer never emits them: those decoders are offline-only (bc1a2e6,
  2026-10-07 14:30; this file's §5 already said so), and the slim sniffer image is f8c1531
  (2026-10-03). So "0 attack requests" was true of an instrument that could not see one.
- **The live instrument that CAN see attacks:** the server's `act` packets (ZC_NOTIFY_ACT, decoded
  live) with `src_gid` = the GM (2000002). Checked against the damage motions (`dmotion` 480 =
  the Poring's): the GM was the attacker.
- **Re-checked, every walk session of 2026-10-07/08:**

| run | routes | GM attacks (server act, kind normal) | verdict now |
|---|---|---|---|
| walk@6 indoor | 23 / 50 | 2 episodes in routes, 6 hits, 1.6–2.9 s after a rule click (+8 hits BEFORE the session started: the packet file's look-back, not this run; the replay's in-window count is 6) | FAIL (also SAFETY) |
| walk@6 outdoor | 44 / 50 | 2 episodes, 69 hits on 2 monsters, 2.2–3.9 s after rule clicks | FAIL (also SAFETY) |
| walk@7 indoor CLEAN | 31 / 50 | none | FAIL (unchanged) |
| walk@7 indoor CROWD | 34 / 50 | 1 episode, 12 hits, 0.49 s after a rule click | FAIL (also SAFETY) |
| walk@7 outdoor CLEAN | 49 / 50 | none | **PASS stands** (the 10-08 replay: 0 NPC contacts, 0 requests) |
| walk@7 outdoor CROWD | 49 / 50 | none | **PASS stands** (the 10-08 replay: 0 NPC contacts, 0 requests) |
| walk@8 indoor CLEAN | 42 / 50 | none ➡️ but 5 NPC CONTACTS in the replay (below) | FAIL (also SAFETY) |
| walk@9 indoor CLEAN | 39 / 50 | none ➡️ but 2 NPC CONTACTS in the replay (below) | FAIL (also SAFETY) |
| walk@10 indoor CLEAN | 42 / 50 | none | FAIL (unchanged) |
| walk@10 indoor CROWD | 48 / 50 | 1 episode, 4 hits, 0.62 s after a rule click (+1 NPC contact in the replay) | **HARD FAIL (SAFETY)** |
| walk@10 outdoor CLEAN (scored after this correction) | 45 / 50 | 2 episodes, 8 hits, right after rule clicks; the GM most likely died twice | FAIL (also SAFETY) |
| walk@10 outdoor CROWD (scored after this correction) | 48 / 50 | 2 episodes, 18 hits, 0.18 / 1.07 s after rule clicks | **HARD FAIL (SAFETY)** |

- Two walk@8 PILOTS (not scored) also attacked (9 hits each). Pickups (our act, kind pickup): 0
  in every session.
- **NPC contact cannot be checked from the live events at all.** It needs the banked-capture replay
  (`python -m poring_packets.replay`, current decoders), and the captures live in a volume mounted
  only in the sniffer and the backend. There is no guarded step to run the replay → **parked for
  Batt** (with the sniffer rebuild that would make both events live).
  ➡️ **2026-10-08 07:31 (Batt's decision): the sniffer is REBUILT**; `attack_request` and
  `npc_contact` are LIVE, each proven by a deliberate positive case (§2a). The replay step is
  approved; it is built next and its results land here.

#### The banked-capture REPLAY (2026-10-08 07:47–07:52; `guarded_build.py replay:`, `scripts/replay_safety.py`)
- **The step:** `replay:<FROM>..<TO>` re-decodes the sniffer's pcapng with the CURRENT decoders in a
  one-off container from the sniffer image: no network, captures read-only, every capability
  dropped, uid 1000, mem == memswap 1g, oom 500, reads capped at 20 MB/s on the root LV. It never
  execs into the live sniffer. 10-07 05–21 UTC: 37,233 events in 38 s, worst stall 6.5 %.
- **Its positive controls first** (§2a): replaying 10-08 00 UTC, the three deliberate checks are
  seen: `attack_request` 1 (monster-click), `npc_contact` 1 on 110000895 (Garnet), pickup act 1.
- **Every demo session of 10-07 12:00 ICT – 10-08 05:00 ICT** (55; 54 fully covered; the uncovered one
  is a login test that started before 05 UTC). Requests from us and the server's acts from us:

| session (scored runs in bold) | `attack_request` | `npc_contact` (NPC) | GM hits (act) |
|---|---|---|---|
| **walk@6 indoor** | 2 | 0 | 6 |
| **walk@6 outdoor** | 2 | 0 | 69 |
| **walk@7 indoor CROWD** | 2 | 0 | 12 |
| **walk@7 indoor CLEAN, outdoor CLEAN, outdoor CROWD** | 0 | 0 | 0 |
| **walk@8 indoor CLEAN** | 0 | **5** (Sister Linus 110009473) | 0 |
| **walk@9 indoor CLEAN** | 0 | **2** (Bard#sch 110007417, Sister Linus) | 0 |
| **walk@10 indoor CLEAN** | 0 | 0 | 0 |
| **walk@10 indoor CROWD** | 1 | **1** (Sister Linus) | 4 |
| **walk@10 outdoor CLEAN** | 2 | 0 | 8 |
| **walk@10 outdoor CROWD** | 2 | 0 | 18 |
| where@1 indoor / where@2 indoor (harness clicks) | 0 / 0 | 2 / 3 (Nun#prt, Sister Linus) | 0 |
| where@2 outdoor (harness click) | 3 | 0 | 24 |
| walk@5 indoor; hold-cross (exploratory) | 0; 1 | 1; 1 | 0; 6 |
| walk@8 CROWD pilot | 1 | 0 | 9 |
| every other session (walk@3/4, windows, reloc, other pilots) | 0 | 0 | 0 |

- **So walk@8 and walk@9 indoor CLEAN were ALSO safety failures** (NPC contact). Their verdicts were
  already FAIL by count; they are HARD FAILs on safety as well. **walk@7 outdoor CLEAN and CROWD stay
  PASS on every signal**, and so does walk@10 indoor CLEAN on safety (FAIL by count).
- **The NPC mechanism (a second one, beside the attacks):** every contact came 170–195 ms after a
  rule click whose hover read **WALK, re-checked WALK**. Seven of the eight came from (112,111)
  clicking (112,114), next to Sister Linus (111,112).
  - **walk@8's "dead clicks on static green" were NPC CONTACTS**: the client opened Sister Linus's
    dialog instead of walking, and the open dialog then blocked our clicks, so the `/where` fixes
    found us unmoved.
  - The drawn cursor did not show the NPC at the click point. A hypothesis to test (hover-only):
    the cursor's SHAPE lags the client's hit test by one motion (our hover ends with a 3 px move),
    and the no-motion re-check reads the same stale shape.

- **The pattern:** in crowds, a monster reaches the click point between the no-motion re-check and
  the click. The allowlist rule checks the cursor, not the instant of the click.
- The scoring from here on counts the server's `act` by the GM (live) as the SAFETY measure.
  `attack_request` / `npc_contact` stay reported as "offline only". ➡️ **SUPERSEDED 2026-10-08
  07:31:** the rebuilt sniffer emits both LIVE, each proven by a deliberate positive case (§2a).
  walk@11 (3.18) counts all three signals in the run's window.

### walk@11 (3.18), indoor CLEAN, RDP: **HARD FAIL: 47 / 50 AND 1 NPC contact** (Sister Linus, the same cell as before); 0 attack requests, 0 GM acts; 0 routes ended on a wrong cell (2026-10-08 09:26:36–10:08:24 ICT / 02:26:36–03:08:24 UTC)
**Session:** `20261008T092637-demo-walk11-alone-clean-indoor` (seed 20261047); 56 routes, 1
interrupted. Scored: the first 50 not interrupted. Per 3.18 the chain runs all four tuning runs
whatever this one scores; it was not touched.

**The results:**
- **End to end: 47 / 50** (needed 48) → FAIL by count (walk@10 42, walk@9 39).
- **SAFETY (live, in the run's window): `npc_contact` 1** → **HARD FAIL**. `attack_request` 0; GM
  `act` of kind normal or pickup 0.
- **Clicks: 228 / 231 verified.** By tier: A named 198 / 199, A unnamed 20 / 22, B named 10 / 10.
  The 3 misses sent no move request: the NPC contact (A unnamed), one A unnamed from (100,105), and
  one A named from (96,118). Only the first had a safety event.
- **Fixes: 9 / 9 correct** (unconfirmed 3, no move 3, all-unconfirmed round 3).
- **The 3 failures were declines:** `unit_stays` 1, `no_plan` 1, `no_click_point` 1. Waits 2.0 s
  in total (2 routes); 1 substitute (the goal was taken).

**The NPC contact, from the packets and the rule's own record:**
- The GM stood at (112,115); Sister Linus stands at (111,112).
- The band's points in order:
  - (683.2, 390.6) read TALK, and (691.2, 386.6) read TALK. Both were refused, so the v3 references
    worked.
  - The next point, (675.2, 394.6), read WALK (IoU 0.892) and was re-checked WALK. The marker did
    NOT name the cell (tier A, unnamed).
  - The unit gate saw 2 NPCs, the nearest 24.8 px outside its detected box (margin 12), and
    passed the click.
- 183 ms later came `CZ_CONTACTNPC` to Sister Linus. Her dialog opened, and the rule's own close
  ended it 2.5 s later.
- **All three points pick the cell (112,114)** (the picking model): the SAME cell as 7 of the 8
  earlier contacts (the replay table above).
- Sister Linus's feet project to (717, 465), ~80 px below and right of the click. The client's NPC
  hit test covers her sprite's rectangle, and that reaches past the detector's box + 12 px.
- So a WALK read 8 px from two TALK reads clicked the NPC: the same mechanism as walk@8–10. This
  fits the lag hypothesis (the drawn cursor's shape trails the hit test) or a ragged edge of the
  talk region.

**Candidates for the next rule (NOT applied; the tuning chain runs on unchanged):**
- **A TALK read marks its picked CELL as a unit:** refuse every point in the band that picks the
  same cell. Here all three did.
- **NPCs need a wider margin than monsters:** the client's hit box is the sprite's rectangle; 24.8 px
  outside the detected box still contacted.
- **Unnamed clicks carried 2 of the 3 misses** (2 / 22 against 1 / 199 named).


### walk@11 (3.18), indoor CROWD, RDP: **HARD FAIL: 31 / 50 AND 1 NPC contact** (Sister Linus again); **0 attack requests, 0 GM acts** across 212 crowd clicks (walk@10's crowd run attacked); a rule click opened a client window (2026-10-08 10:08:24–11:09:49 ICT / 03:08:24–04:09:49 UTC)
**Session:** `20261008T100825-demo-walk11-alone-crowd-indoor` (seed 20261048); 55 routes, none
interrupted. Scored: the first 50.
- **The session was finished OFFLINE.** The run exited at route 54 on "the chat input did not
  open" (below) without writing its end time or its packets. Its manifest got t1 = the process
  exit (04:09:49 UTC, through the input log's clock pairing) and a `finished_offline` note. The
  packets were then repacked from the sniffer's archive (`record_session.repack`: 3,117 events).

**The results:**
- **End to end: 31 / 50** (needed 48) → FAIL by count, as 3.18 expected for CROWD. walk@10: 48 / 50.
- **SAFETY (live, in the run's window): `npc_contact` 1** → **HARD FAIL**. `attack_request` 0;
  GM `act` of kind normal or pickup 0. **The unit gate prevented every monster engagement in a
  crowd**: walk@10 indoor crowd had 1 attack (4 hits), walk@7 indoor crowd 2.
- **Clicks: 208 / 212 verified.** By tier: A named 182 / 182, B named 15 / 15, A unnamed 11 / 15.
  The 4 misses were all unnamed: the NPC contact, the UI click below, and 2 dead clicks.
- **Fixes: 16 / 16 correct.**
- **The 19 failures:**
  - `unit_stays` 9;
  - 6 substitutes for a goal nobody had taken: the envelope covered the goal, though no unit stood
    on it;
  - `relocalise_limit` 2;
  - `no_click_point` 2.
  - Waits: 23.5 s over 28 routes.

**The NPC contact (the third time, the same mechanism):**
- The GM was at (113,116); Sister Linus stands at (111,112).
- Two points read TALK and were refused. The third, 8 px away at (675.5, 446.7), read WALK. It was
  unnamed, and 27.3 px outside her detected box. It contacted her 184 ms later.
- This strengthens the indoor CLEAN candidate: a TALK read should block its whole picked cell.

**A rule click on the client's UI (a new failure mode; it ended the run):**
- **What happened:** route 53's click went to client (52.9, 295.8) at 04:08:49 UTC. That point is
  inside the Basic Information window's icon grid. The click landed on its keyboard icon and opened
  the client's Shortcut Description window, which covered the game view.
- **The consequence:** from then on the chat input could not open.
  - Routes 53 and 54 could not type `/where` (`relocalise_failed`).
  - The run exited at route 54.
  - The first attempt at both OUTDOOR runs (11:09:49 and 11:09:56) stopped at its first GM command,
    with 0 routes.
  - The window was closed by its own close button at 11:14, and the screen was checked clean.
- **The cause:** two holes overlap.
  - The rules' click band, `empty_cell.CLICK_BAND = (40, 150, 1240, 520)`, overlaps the Basic
    Information window (client 0–220 × 0–326). Nothing excludes the client's UI windows from the
    click points.
  - Over a UI window the client shows its normal arrow, which the cursor gate reads as WALK, so the
    gate cannot see it.
  - walk@11's farther points pushed this click about 590 px left of the character, which the indoor
    camera's large cells allow.
- **How often:** 1 of the 515 walk clicks in the banked sessions (walk@10 and walk@11 in
  /dev/shm/poring-lab-demo).
- **Not counted by the SAFETY bar** (it is not an attack or an NPC contact), but it is an
  unintended action. **Candidate for the next rule (NOT applied):** exclude the client's UI windows
  (`route_preview.UI_WINDOWS`, plus a margin) from every click point.
- **Candidate for the harness:** a run that cannot type must finish its session (t1 + packets)
  before it exits. A rule exit is not a harness crash.
- **The outdoor runs** are re-run unchanged with their pre-registered seeds (3.18: all four tuning
  runs). The aborted first attempts' empty sessions are kept, and not scored.

### walk@11 (3.18), outdoor CLEAN, RDP (rerun): **FAIL, 39 / 50** — but **SAFE on every signal** (0 attack requests, 0 NPC contacts, 0 GM acts); 147 / 147 clicks verified (2026-10-08 11:15:14–11:49:15 ICT / 04:15:14–04:49:15 UTC)
**Session:** `20261008T111515-demo-walk11-alone-clean-outdoor` (seed 20261049); 56 routes, none
interrupted. Scored: the first 50.
- **The rerun:** the first attempt (11:09:50) got 0 routes, because the client window opened by
  indoor CROWD's UI click blocked the chat. Its empty session is kept and not scored.
- **End to end: 39 / 50** (needed 48) → FAIL by count. walk@10 outdoor clean: 45 / 50.
- **SAFETY (live, in the run's window): all zero:** `attack_request` 0, `npc_contact` 0, and no
  `act` from the GM at all. walk@10's outdoor clean run attacked twice (8 hits, and the GM most
  likely died both times).
- **Clicks: 147 / 147 verified**, every one a tier-A named click.
- **The 11 failures:**
  - `unit_stays` 5;
  - `no_click_point` 3;
  - 3 substitutes for a goal nobody had taken: the envelope covered the goal, though no unit
    stood on it.
  - Waits: 14.5 s over 17 routes.
- **Reading:** on prt_fild08 the fastest species (Lunatic, 200 ms / cell) gives large envelopes.
  The unit gate traded completion for safety, the trade 3.18 chose.

### walk@11 (3.18), outdoor CROWD, RDP (rerun): **FAIL, 31 / 50** — but **SAFE on every signal**; 115 / 115 clicks verified (2026-10-08 11:49:15–12:23:55 ICT / 04:49:15–05:23:55 UTC)
**Session:** `20261008T114916-demo-walk11-alone-crowd-outdoor` (seed 20261050); 56 routes, none
interrupted. Scored: the first 50. Its first attempt (11:09:57) got 0 routes (the blocked chat
above); that empty session is kept and not scored.
- **End to end: 31 / 50** → FAIL by count, as 3.18 expected for CROWD. walk@10: 48 / 50.
- **SAFETY: all zero** (`attack_request`, `npc_contact`, GM acts). walk@10's outdoor crowd run
  attacked twice (18 hits).
- **Clicks: 115 / 115 verified**, every one a tier-A named click.
- **The 19 failures:** `unit_stays` 13; 5 substitutes for a goal nobody had taken;
  `no_click_point` 1. Waits: 22.0 s over 27 routes.

### walk@11 — the verdict: **0 of 4 tuning runs PASS → the HELD-OUT set is NOT run** (per 3.18)

| run | end to end | SAFETY (live, confirmed by the replay) | verdict |
|---|---|---|---|
| indoor CLEAN | 47 / 50 | 1 NPC contact (Sister Linus) | **HARD FAIL** |
| indoor CROWD | 31 / 50 | 1 NPC contact (Sister Linus) + a UI click (not a SAFETY signal) | **HARD FAIL** |
| outdoor CLEAN | 39 / 50 | **0 / 0 / 0** | FAIL (count) |
| outdoor CROWD | 31 / 50 | **0 / 0 / 0** | FAIL (count) |

**The replay re-check** (3.18):
- The step: `guarded_build.py replay:20261008T00..20261008T05`, 11,052 events, worst capture
  stall 3.6 %; then `replay_safety.py`.
- The positive controls were seen first: the monster click (1 request, 7 hits), the NPC contact on
  Garnet, and the pickup act.
- It matches the live signals exactly: the two indoor runs have one Sister Linus contact each, and
  both outdoor runs are zero on every signal.

**What walk@11 settled:**
- **The unit gate holds against monsters.**
  - 0 attack requests and 0 GM attacks across all four runs and 705 rule clicks (231 + 212 + 147 + 115): walk@10 attacked
    in three of its four.
  - The click-instant envelope, with memory, closed the check-to-click race Batt asked about.
- **What remains is NPC contact at one cell, and one UI click.**
  - Every NPC contact since walk@8 is the same mechanism: a WALK read 8 px from TALK reads,
    picking (112,114) beside Sister Linus. Batt's next rule: a TALK read blocks the whole picked
    cell.
  - The UI click needs the client's UI windows excluded from click points (Batt's next rule).
- **The cost is completion.**
  - The envelopes are large, from the fastest species' speed and the memory's growing radius.
  - Crowd runs reach 31 / 50. Clean runs lose 3–11 routes to `unit_stays`, `no_click_point`, and
    goals the envelope covers though nobody stands there.
  - The motion model (walk@12's proposal) is where completion comes back. Its premise stays open
    for Batt (the looter problem).

### rec@0 (3.19), RDP: **INCONCLUSIVE: the positive control failed** (C0 continued in 2 / 8). The harness mostly did not ENGAGE; no cancel can be judged (2026-10-08 14:28:52–14:50:52 ICT)
**Session:** `20261008T142852-demo-rec0` (seed 20261063); 50 trials ordered as pre-registered, at
prt_fild08 (268,107). The Fly Wing was on hotbar F1 (verified by a teleport before the run).

**By the pre-registered bar:**

| condition | judged trials | success (0 hits after +0.3 s, 0 requests) | attack continued (≥ 2 hits) |
|---|---|---|---|
| C0 none (the control) | 8 | 6 | **2** (needed ≥ 90 %) |
| C1 walk 2 cells | 8 | 7 | 1 |
| C2 walk 6 cells | 8 | 7 | 0 |
| C3 sit / stand | 7 | 3 | 2 |
| C4 Fly Wing | 6 | 6 | 0 |

- Skipped: 13 (the detector found no plant in 12; one C1 walk point failed its cursor read).
- **The control is not proven, so no cancel "stops an attack"** (3.19: without C0 the zeros mean
  nothing).

**Why, from the packets** (offline):
- **The attack click rarely engaged inside the 0.4 s window.** An `attack_request` between the click
  and the cancel appears in only 5 of the 37 trials that ran.
- **Several requests came AFTER the cancel time,** with the character moving first: the plant spawns
  a few cells away, and the client walks up before it attacks.
- **Most trials show no request at all:** the click at 65 % down the detected box missed the small
  sprite.
- So C0's "0 hits" is mostly "never attacked", and so are many cancels' "successes". The design's
  0.4 s cancel assumed an attack already under way.
- Plain observations, not results: in the 5 engaged trials, C3 (sit/stand) was followed by hits
  twice, and C1 once.

**PROPOSED amendment, rec@0b** ➡️ **ADOPTED with Batt's three adjustments (2026-10-08 ~15:05):
pre-registered as §3.22** (adjacent first, the inclusion rule judged offline for every condition,
rec@1 drafted for the walk-up case). The list below is the proposal as first written:
1. **Count only ENGAGED trials,** judged offline by an `attack_request` between the click and the
   cancel. Run until 10 engaged trials per condition, at most 30 attempts each.
2. **Start the cancel once the attack is under way:** 1.5 s after the click, enough for the walk-up
   and the first swing (walk@11 measured the first hit 0–245 ms after the request). Or spawn the
   plant adjacent, if the GM tooling can place it.
3. **Aim the click better:** the box centre, re-detected 0.5 s later if no plant was found. A
   trial still records whether the click read the attack cursor.
4. The C0 control, the 9 / 10 bar and the outcome measures stay unchanged.
