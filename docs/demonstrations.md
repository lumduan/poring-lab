---
doc_type: design
hypothesis: "Rules distilled from outcome-verified demonstrations (login, walk-to-point, attack-target selection) succeed ALONE on new situations at >= 95 %, judged only by offline packet verifiers."
status: PRE-REGISTERED
role: null
verdict_date: null
verdict_ticket: null
supersedes: null
related: [phase3-plan.md, phase4-ui.md, adr/0007-packet-ground-truth-channel.md, adr/0011-ui-anchor-map.md, adr/0015-phase4-planner-linter-executor.md]
next_action: "login@1 PASSED on RDP (50/50, 2026-10-07). walk@1 and walk@2 FAILED: the rule hovered with ONE motion event and the client draws the walk marker only on a second (§Results). Next: walk@3 (3.5), outdoor then indoor, n=50 each; attack@1 after the v0-JPEG run (GPU, R1-R3); S2 re-tests in an evening S2 session. Score each ONCE as written here."
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

### 3.34 learn_skill@1 -- spend skill points in the skill window (DESIGN 2026-10-09 ~19:50; NOT pre-registered; Batt ~19:30: "add the new skill the job change needs: allocating skill points (Basic Skill > 8) via the skill window, as an L1 concept with its own alone-test")
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
