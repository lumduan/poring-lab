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


### walk@6, indoor, RDP: **FAIL, 23 / 50** (1 interrupted) — SAFETY held: 0 attack requests, 0 NPC contacts (2026-10-07 18:00:21–18:34:27 ICT / 11:00:21–11:34:27 UTC)
**Session:** `20261007T180021-demo-walk6-alone-indoor`; 56 routes run.
- Route 34 was interrupted: a human `release_all` at 18:20:50 ICT / 11:20:50 UTC, marked by `demo_interruptions`.
  - It was the session's ONLY human event, and it came after console fix A (0ab7521, live
    17:12): a page loaded since then never sends a release with nothing held.
  - Most likely a console tab still running the old script blurred; reloading open console tabs
    applies the fix.
- **Scored:** the first 50 not interrupted, as pre-registered (3.9).

**The bar:** end to end **23 / 50** (needed ≥ 48) → **FAIL**.

**SAFETY:** **0** `attack_request`, **0** `npc_contact`, **0** pickup acts by us, over 235 clicked
runs among 4 Porings per 10 routes and the church's NPCs. The allowlist never clicked an entity.

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

### walk@6, outdoor, RDP: **FAIL, 44 / 50** — SAFETY held: 0 attack requests, 0 NPC contacts (2026-10-07 18:34:27–18:58 ICT / 11:34:27–11:58 UTC)
**Session:** `20261007T183427-demo-walk6-alone-outdoor`; 56 routes run, none interrupted.
- **Scored:** the first 50.
- **The bar:** 44 / 50 (needed ≥ 48) → **FAIL**.
- **SAFETY:** 0 `attack_request`, 0 `npc_contact`, 0 pickup acts over 178 clicked runs. That is with
  4 spawned Porings per 10 routes AND the field's own monsters.

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

### walk@7 (3.12), RDP — **outdoor PASS in both conditions (49 / 50, 49 / 50); indoor FAIL (31 / 50 clean, 34 / 50 crowd)**; SAFETY held in all four (2026-10-07 19:34–21:48 ICT / 12:34–14:48 UTC)

| run | session | scored | end to end | SAFETY | segments (at the click) | re-localisations (v2) | substitutes | patience |
|---|---|---|---|---|---|---|---|---|
| indoor CLEAN | `20261007T193431-…-clean-indoor` | first 50 (2 interrupted) | **31 / 50 FAIL** | 0 / 0 | 243 / 269 (25 one cell off) | 1 correct, **3 WRONG**, 5 undecided | 1 justified, **3 not** | 31 routes, 81.5 s |
| indoor CROWD | `20261007T201618-…-crowd-indoor` | first 50 | **34 / 50 FAIL** | 0 / 0 | 257 / 270 (12 one cell off) | 2 correct, **2 WRONG**, 6 undecided | **2 not** | 37 routes, 93.5 s |
| outdoor CLEAN | `20261007T205645-…-clean-outdoor` | first 50 | **49 / 50 PASS** | 0 / 0 | **184 / 184** | none needed | **1 not** (the one failure) | 15 routes, 23.0 s |
| outdoor CROWD | `20261007T212227-…-crowd-outdoor` | first 50 | **49 / 50 PASS** | 0 / 0 | **199 / 199** | none needed | **1 not** (the one failure) | 22 routes, 29.5 s |

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
- **Still open:** the same check on a normal (non-GM) account.

### walk@8 (3.14), indoor CLEAN, RDP: **FAIL, 42 / 50**; SAFETY held; every `/where` fix correct (2026-10-07 23:40:42 – 2026-10-08 00:16 ICT / 16:40–17:16 UTC)
**Session:** `20261007T234042-demo-walk8-alone-clean-indoor` (seed 20261023); 56 routes, none
interrupted. Scored: the first 50.

**The results:**
- **End to end: 42 / 50** (needed 48) → **FAIL**. For comparison, in the same room CLEAN: walk@7
  31 / 50; walk@6 23 / 50 (with Porings).
- **SAFETY:** 0 `attack_request`, 0 `npc_contact`.
- **The belief fixes (where@2): 11 of 11 CORRECT, 0 WRONG** against the packets. Triggers:
  unconfirmed 7, neighbour 2, no-entry 2; plus a fix at every route's start.
- **Clicks:** 239 / 254 verified. **9 sent no move request at all** (the client did not walk); 5
  walked one cell off, 1 three off.
- **Waits:** 0 s (no unit stood anywhere: patience is for units only, as designed). Substitutes: 0.

**The 8 failures:**

| cause | n | what the logs show |
|---|---|---|
| `relocalise_limit` | 3 | **dead clicks:** from (112,111), two different targets were "confirmed" with the same 43 px of green. That was **static scenery**, not the walk marker; the clicks did not walk, and two `/where` fixes said we had not moved |
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
