---
doc_type: design
hypothesis: null
status: PROPOSED
role: null
verdict_date: null
verdict_ticket: null
supersedes: null
related: [ADR-0020, ADR-0015, ADR-0002, ADR-0007, ADR-0016, ../demonstrations.md, ../competition.md, ../../config/map_zones/README.md, mw2-block-editor.md, adr0020-contradictions.md]
next_action: "B1 and B3 BUILT offline 2026-10-21 18:2x on feat/blocks-b1b3 (section 7a; not merged): the parent reviews and merges. B2 (the editor) is next; B4 waits for Batt to be present. Amendment A's text stays a DRAFT until Batt accepts it."
title: "Behaviours as blocks: hunt-flow's adopted rules become a hunt block in the map node; map zones become map-node data (plan)"
date: 2026-10-21
owner: Batt
extends: docs/adr/0020-block-programming-flows.md
---

# Behaviours as blocks: from hunt-flow's PARAMS to a hunt block

**Batt (2026-10-21, item 5):** "from now on, behaviours are to be expressed as BLOCKS in the flow
editor (/flows, ADR-0020), not as pure code. Hunt-flow's PARAMS versions were the lab for finding
what works; the result should become blocks a person can read and change. ... Plan only: no build
until I approve."

Status: PROPOSED. ~~Nothing here is built, run or pre-registered.~~ ➡️ **2026-10-21 18:2x: B1 and
B3 are BUILT offline** (section 7a, branch feat/blocks-b1b3); nothing is run live or pre-registered.
The ADR side is
[ADR-0020 Amendment A](../adr/0020-block-programming-flows.md#amendment-a-draft-proposed-2026-10-21-not-accepted-behaviours-as-blocks-map-zones-as-map-node-data)
(DRAFT).

## 1. The goal

- `scripts/hunt_flow.py` PARAMS[1..51] were the lab: each version one pre-registered experiment
  (demonstrations.md 3.41-3.92).
- What was ADOPTED becomes ONE task-level `hunt` block inside a map node. Its parameters are what a
  person chooses: targets, strike style, the dead + loot rule, the search rule, the stop.
- HOW it acts safely stays in the engine: gates, safety checks, readers, tuned constants. No block
  parameter reaches them.
- Map zones become map-node data: drawn in the editor, stored as the same YAML.
- The experiment method (one change, interleaved arms, pre-registration, the same judges) keeps
  working, on block configs instead of PARAMS dicts.

## 2. Block parameter or engine internal

**The rule (Batt):** a person's choice is a block parameter; gates, safety and readers stay in the
engine. **Added here:** tuned constants (timings, pixel radii, bounds) belong to a RULE VERSION.
A person picks a version (e.g. loot = `gm_scan_one_pass@51`); its numbers come with it, shown
read-only. A new number is a new version, pre-registered as today (ADR-0020 section 12, "How an
action block becomes verified", point 4).

**The base** is v51 as adopted: PARAMS[51] with `loot_gm_one_pass_ab` False. Resolved through the
merge chain it holds 209 keys (computed from the file on 2026-10-21, 0684d2c).
➡️ **SUPERSEDED 2026-10-21 14:22:** the adopted base is now **v52** = v51 + `"map_zones": True`
(the prt_fild08 zones file, demonstrations 3.93 ADOPTED). Read "v51" below as "the adopted base";
the key count grows by the one key.

**2a. Block parameters (a person chooses)**

| choice | today | adopted by | in the block |
|---|---|---|---|
| targets / ignore | hard-coded: `farm0.TARGETS`, `nametag.TARGET_NAMES` (mob 1002, 1063, 1008, 1113); 1018 counted apart (`hardbar_live.py`) | since v1 / v14 (3.41, 3.56) | the map node's `targets` / `ignore` (ADR-0020 13.3), by mob id. With PER-SPECIES detector classes (Batt 2026-10-21, the orcsdun01 order, item 4: "the hunt code maps species -> monster + target/ignore lists, so the species check comes from the detector"), the lists name classes the detector itself outputs |
| strike style | `abc_arm` C (A the fallback when unsure or crowded) | 3.70's verdict; the default from v32 (3.72) | `strike`: C, B or A |
| engage on the way | `opportunistic`, `opp_cells`, `preempt_*`, `retarget*` | v11, v13, v26 (3.53, 3.55, 3.67), in the base since | `engage_on_the_way`: on / off |
| dead rule | `exp_dead`, `exp_keep*`, `exp_loot_delay_s` (the Battle Log's EXP line; the target kept) | v48, ADOPTED by Batt 2026-10-20 14:58 (3.89) | `dead`: `exp_line@48` |
| loot rule | `loot_gm*`, `loot_gm_one_pass` (stand 0.5 s, the drawn GM's own cell + 3 x 3 + 5 x 5 edge, HAND-only bursts, one pass) | v50 ADOPTED by Batt (3.91); v51 ADOPTED by its rule 2026-10-21 02:5x (3.92) | `loot`: `gm_scan_one_pass@51`, `gm_scan@50` or none |
| search heading | `heading_search`, `heading_min_run`, `heading_drift_p`; `heading_cov`, `cov_*` | v18 (3.60), v22 (3.63), in the base since | `search`: `heading_coverage@22` |
| stop | the runner's `--minutes` | - | the block's `until` (e.g. a duration or `weight_percent()`; 13.5's loop rules) |
| map zones | `config/map_zones/<map>.yaml` | Batt 2026-10-21 decision 1 (0684d2c) | map-node data (section 3) |

**2b. Engine internals (never a block parameter)**

| kind | behaviour | PARAMS key(s) | adopted by |
|---|---|---|---|
| gate | walk guard (pink + the GM's circle) | `walk_guard`, `guard_*` | v16 (3.58), a safety layer for every later version |
| gate | risk-based cursor gate | `risk_gate`, `gate_*` | v10 (3.52; Batt's strict rule, 3.51) |
| gate | species identity: name tag when ambiguous, pixel species check | `name_tag`, `tag_*`, `species_skip`, `tag_follow` | v14, v16, v20, v25 (3.56-3.66) |
| gate | cursor SWORD at loot clicks, untrained-species maps only | `cursor_sword*` | Batt decision 2, 2026-10-18 (base from v38) |
| gate | loot click checks: unit near, pink, own corpse | `loot_unit_px`, `loot_pink_*`, `loot_corpse*` | v25 (3.66), v34 base fix (3.74) |
| gate | the pointer rest the client draws (two motions over the HP bar) | `ptr_rest_two`, `ptr_rest_ui` | v26, v28 (3.67, 3.69) |
| gate | frame guard; UI and pointer masks | `FrameGuard`, `guard_ui_mask`, `guard_ptr_mask` | v24, v17, v21 |
| gate | map-zone enforcement on walk, strike and loot clicks; the exit path | `map_zones.py`, `zone_why` | 0684d2c |
| safety | stops: UI state, HP < 75 %, takeover, ASSIST left, unknown cell, no progress, frozen display | `bg_check`, `freeze_guard`, `HP_STOP`, `STUCK_S` | v1, v5, v10 |
| safety | false-dead fix | `false_dead_fix` | v40 ADOPTED (3.81) |
| reader | detector + tracker + focus (NCC) | `frame_cells`, `track_*`, `focus*`, `gate_frames_s` | v3, v6, v16 |
| reader | position: minimap, floor odometry, re-anchor, loot re-fix | `jump_reanchor`, `loot_refix*` | v9, v33 base fix |
| reader | Battle Log EXP line, with the hunting UI layout it needs | `ui_layout` hunt, `dead_end_hyst_s` | v43 ADOPTED (3.84); the block declares the layout, the engine applies it |
| reader | lock arrow, HAND, death cell | `burst*`, `loot_death` anim, the HAND refs | v12, v31, v50 |
| constant | continuous movement, lead-compensated clicks | `continuous`, `walk_every_s`, `ahead*`, `click_lead_s*` | v5, v7 |
| constant | pipelined planner; strike ranges (standing 7, walking 3); engagement zone | `pipelined`, `queue_depth`, `strike_cells*`, `zone*` | v2, v4, v18 |
| constant | burst and re-click timing | `burst_*`, `reclick_s`, `dead_*` | v12, v15 |
| constant | paced input | `send_gap_s` | v34 ADOPTED (3.74) |
| recovery | stall breaker, unstall, pocket escape | `stall_s`, `unstall_s`, `stuck_*` | v5, v15; pocket escape a bug fix (3.83 amendment 2, Batt 2026-10-19) |

**Not carried** (no block, no choice): belief map (off since v30); fast dead (3.72); loot race
(3.73); own-frame species (3.75); loot retry (3.77); SWORD at every click (3.78); age-weighted
heading (3.79); route tail (3.80); walkers from 7 (3.82); steer guard box (3.83); EXP line with the
checked fallback (3.87); HAND 3 x 3 (3.90). Pre-registered, never run: 3.85, 3.86, 3.88. Built,
never run: item-sprite loot, option B (`feat/gm-pass2`). The fixed 3 x 3 (v23-v31) stays the loot
rule's own fallback when the scan cannot start.

## 3. Map zones as map-node data

- **The file stays the source of truth:** `config/map_zones/<map>.yaml`, the format and the
  fail-closed loader of [config/map_zones/README.md](../../config/map_zones/README.md), unchanged.
  The editor is one more way to write it. `map_zones.py check` stays the validator.
- **Drawing.** The /flows map view (`PathMap`: the walk grid from the local GAT copy, never
  committed) gets a Zones layer:
  - a no-cross line: click cells, double-click to end. A no-enter area: click corners, close on
    the first;
  - each item asks for its `id` and `note`;
  - the preview shows the cells each item closes AS THE LOADER RASTERISES THEM (the supercover for
    lines, centre-in-polygon for areas). The backend computes them with `map_zones`' pure
    functions; the browser does not re-implement the geometry. The largest connected search area
    (the start-cell rule) is shown too;
  - map cells, y north, as the README. `PathMap` already draws y = 0 at the bottom.
- **Validation:** `POST /flows/zones/check` runs the loader on the YAML text, under the /flows
  routes' rules (LAN, Origin + CSRF, 20 / min, 1 MiB). Same errors as the CLI; it returns the
  sha256.
- **Saving (D6).** First, export only: the editor shows the YAML, its sha256 and the diff against
  the committed file, and a person commits it; git is the review record. A save route would need
  `config/map_zones` writable in the backend: a new mount, under the Settings rules.
- **Who approves.** `reviewed_by` names a person. The editor never fills it, and the loader keeps
  refusing agent-like names. The agent never approves a zone on its own. A delegation (as on
  2026-10-21 for prt_fild08) is Batt's explicit word, recorded in the file: the reviewer reads
  exactly `agent (delegated by <person>, YYYY-MM-DD)` and a top-level `delegation:` note cites the
  decision; the loader checks both (13e497d; D7 is answered).
- **The IR reference.** The map node gets `zones: {map, sha256}` (optional; an IR version bump if
  the IR's versioning needs one).
  - Approval binds it: the IR hash covers the sha256.
  - The run-start check refuses (fail closed) when the file's sha256 differs from the approved one,
    when a file exists for the node's map but the node names none, or when the named file is gone.
  - Lint layer 3 routes on the walkable grid minus the zones (the runner's grid). An entry inside
    a no-enter area, or an exit behind a no-cross line, is an error. Targets whose whole spawn area
    is closed are a warning.
  - `hunt_flow.py` keeps "no file = no change". A flow makes the reference explicit.

## 4. The experiment harness under blocks

| today (PARAMS) | under blocks |
|---|---|
| a version = `PARAMS[N] = {**PARAMS[base], change}` | an experiment spec: the adopted hunt config (by hash) + a diff with ONE main change (a rule version) + named base fixes |
| `*_ab` keys and engagement parity | the spec's `alternate`: unit = engagement, loot step or 10-min block; the fix arm on odd, as now. The arm selector sits in the executor, outside the IR; both arm configs are approved |
| a `test_vNN_params_on_*` test ("nothing else moves") | computed: the spec linter checks that the diff is exactly the declared change and fixes |
| pre-registration: demonstrations.md 3.x, committed before runs | unchanged; the spec file goes in the same commit, its hash quoted |
| judges: `flow_judge`, `arm_judge`, `hardbar_live` (session files + packets) | unchanged. The executor writes the same session files and fields (`engagements.json` with `k` and the arm, `clicks.jsonl`, `manifest.json`); a schema parity test holds it |
| adoption: the verdict line; the next PARAMS takes the base | the verdict line unchanged; adoption = a commit moving the adopted config to the new version |
| bytecode proofs for frozen decision code | unchanged: a rule version's code is frozen like a pre-registered rule |

**The history.** A proposed `scripts/params_export.py` classifies every PARAMS key: block choice,
rule constant, gate, reader, experiment flag, or inert. ➡️ BUILT (B1, section 7a): the classes are
finer (2b's five engine kinds; inert split into record and retired; map_node for the zones flag).
- It exports PARAMS[1..51] as block configs for the record (our own numbers only).
- A coverage test fails on an unclassified key, as the catalogue test does for L1.
- The exported v51 config, resolved back through the engine, must EQUAL the adopted base dict
  (exact, offline).
- Old versions are records. They run only while their rule code exists.

## 5. MW3 readiness: what blocks need before they drive the bot

**What ADR-0020 gates on.** No single "walk/talk readiness" line; a chain:
- MW2-live, the first live block (13.8): `walk_to` under walk@11's safety bar, `take_warp` and the
  position read verified alone; insert@1, save@1, escape@1, loot@1, rec@1; `dead` and
  `unexpected_map` each proven by a deliberate positive case.
- MW3 (13.8): every block verified alone on BOTH paths; the farm's training scope trained and
  measured per species; TARGET / IGNORE proven by a deliberate positive case.
- The executor (section 6; mw2-block-editor.md section 4): the run-start check, approval of one
  hash, unverified blocks confirmed one by one, ASSIST with the interlock green.
- Walk readiness is demonstrations.md 3.28, plus the per-map walk-ready rule. Talk readiness is
  talk@1 passing.

| need | state (source) | met? |
|---|---|---|
| ADR-0005 + the interlock | done 2026-10-04 | MET |
| hard bars while hunting (NPC contact, non-target hit, map change) | 0 over v50 + v51: 8 x 60 min on prt_fild08 (3.91, 3.92) | MET: one field map, RDP, immune GM |
| walk readiness (3.28) | walk@15 READY on tuning (186 / 200, 0 safety), NOT on held-out (3.29 / 3.29a: prontera 2 NPC contacts; alberta_in incomplete; iz_dun00 58 %). walk@15 types /ex, refused by the typing policy. walk@17: built, pre-registered (3.32), NOT run | NOT MET |
| per-map walk-ready | prt_fild08: its v1 species. Towns: NPC sprites out of scope. iz_dun00: 6 species out of scope | prt_fild08 only |
| talk (talk@1, 3.30) | T2 168 / 168 and T3 216 / 216 offline; T4 / T5 drives pass; NO scored trial; the TALK read's colour check fails at times; prontera menus unproven; the approach moved to walk@17 (not run) | NOT MET |
| position read | where@2 PASS on RDP (48 / 50 indoor, 50 / 50 outdoor, 0 wrong) | MET (RDP) |
| `take_warp` | never verified alone (3.29's portal run: 0 routes) | NOT MET |
| insert@1, save@1, escape@1, rec@1, loot@1 | none passed: rec@0 and rec@0b INCONCLUSIVE; loot@1 P3 INCONCLUSIVE; rec@1 a draft; the others not pre-registered. The hunt's own loot rule works live (v51: M3 0.878) | NOT MET (hunt evidence only, D8) |
| `dead` / `unexpected_map` positive cases | not staged. The GM is immune in every hunt, so `hp_critical` and `dead` have never fired | NOT MET |
| both paths (RDP + S2) | hunt-flow refuses a console lock (RDP-only cursor references). The S2 UI-gate set is built, not run (docs/operations/s2-gate-templates.md); S2 typing stays refused | NOT MET |
| TARGET / IGNORE; training scope | the targets trained (v1, prt_fild08). The detector does not separate 1018 (a metamorphosis): v51 hit it 4 times in 4 h (3 requests), counted apart, not a stop | NOT MET |
| verified L1 concepts | 39 concepts, 0 verified (docs/knowledge/README.md) | NOT MET |
| the live executor | `poring_flow.runstart` built and tested, called by nothing. No executor, approval route or run messages. /flows is SIMULATE only | NOT MET |
| where the executor runs | section 6: the vision container, S2 only. The hunt runs on the host, RDP, CPU detector | OPEN (D9) |

**Honestly:** hunting on one field map runs for hours with the hard bars at zero. That is not walk
or talk across maps. No walk version is ready on held-out maps under the typing policy, talk@1 has
no scored trial, and nothing is proven on S2. Batt's example end to end (MW3) is far. What is near
is a narrow slice, "MW3-hunt" (D9): one map node (prt_fild08), one hunt block, no exits, RDP,
ASSIST, the immune GM, Batt present. It needs the executor slice (B4) and the A/A check, nothing
from walk or talk.

## 6. The safety story

Every layer below exists today. A block adds none and removes none.

| layer | where | what a block can do to it |
|---|---|---|
| one input writer; the human always wins | the mux (ADR-0002) | nothing |
| the environment interlock | backend (ADR-0016) | nothing |
| the frame-age guard | `poring_env.freshness` | nothing |
| the foreground gate (typed keys) | backend | nothing |
| the UI gate on every typed line | `ui_gate.py` | nothing |
| always-on `dead`, `hp_critical`, `unexpected_map` | `poring_flow.always_on` | only stricter (lint: "not weakened") |
| the hunt engine's gates and stops (2b) | the hunt engine | nothing: they are not parameters |
| map zones | the file + its loader | a person's file adds or tightens; the agent never approves |
| the hard-bar monitor (packets, stop-only) | `hardbar_live.py`, the experimenter's | nothing; proposed as required for every block-driven lab run |
| the click census | `test_click_census.py` | a new click site fails until it passes the gates |

**How "a block cannot turn a gate off" is enforced:**
1. **Schema.** The hunt block's parameters are enums of rule-version ids and bounded numbers;
   `extra="forbid"` refuses any other field. No gate has a field.
2. **A deny-list test.** The exporter's "gate" role is the list. A block parameter, a rule preset
   or an experiment diff that names a gate key fails the test.
3. **A gate change is code**, pre-registered, with Batt's OK, applied to every arm (as v16's walk
   guard and the pocket escape were).
4. **Tighten only.** If a safety number is ever shown as a parameter, the linter refuses a looser
   value (`always_on`'s rule).
5. **One hash.** Approval binds the IR + the engine version + the zones sha256. The run-start check
   refuses a mismatch; the engine refuses an unknown rule version.
6. **The record.** The engine writes its gate table (names, versions) as the run's first event; the
   judge flags a session without it.

## 7. Build proposal (B1 + B3 built 2026-10-21, offline: section 7a)

| step | what | where | acceptance |
|---|---|---|---|
| B0 | Batt decides section 8 and Amendment A | - | the answers recorded in place |
| B1 | the exporter + key classes; the `hunt` block in `blocks.yaml` (+ an L1 `combat.hunt`, unverified); the map node's zones reference; lint with zones | offline; no runtime change | 209 / 209 keys classified; exported v51 resolves to the adopted base exactly; one lint fixture per new rule |
| B2 | editor: the hunt block (groups as lists of rule versions with badges); the Zones layer; the zones check route; YAML export | SIMULATE only | round trips; CSP clean; an editor-made file loads with the sha of its hand-written twin; the loader's error corpus shows in the editor |
| B3 | the engine split: the decision code takes a resolved config; `hunt_flow.py run --version N` unchanged | offline | bytecode proof of the decision code; click census unchanged; session-file parity |
| B4 | MW3-hunt: an approved flow (one map node, one hunt block, `until`) runs through the engine; the run-start check called; the monitor bound | live, lab, ASSIST, Batt present; pre-registered | the A/A check (D5); hard bars 0 |
| B5 | experiments as specs; the next version (e.g. a loot lever from competition.md) as a config diff | live, pre-registered | as any version today |
| later | the NOT MET rows of section 5 (walk@17, talk@1, S2, positive cases, TARGET / IGNORE) | each its own pre-registration | - |

Every step runs under CLAUDE.md rules 1-10: tmpfs worktrees, guarded steps, no disk-heavy work in
the market-open windows, the census and safety tests on any click change.

### 7a. B1 / B3 RESULT (built 2026-10-21 17:44-18:2x, offline; branch feat/blocks-b1b3, NOT merged)

Built by a subagent in a tmpfs worktree, on main 5e5dbcf (v54 merged): commits bb1b867 + 1795b03
(B1) and 1b058c3 (B3). Nothing ran live; no runtime behaviour changed (B3's proofs below).

**B1: what exists now**
- `scripts/hunt_config.py`: the key classes by ORDERED NAME PATTERNS (D3: never a frozen key list;
  a key no pattern names is refused, keys newer than `REVIEWED_THROUGH` = 54 are listed for review);
  `export` / `resolve` / `params_for` / `adopt`. `scripts/params_export.py classify | export | check`.
- `config/flows/hunt/v01.yaml` ... `v54.yaml` (all 51 versions) and `index.yaml` (adopted: 52; each
  version's rule versions and arm flags; each rule version's numbers). Our own numbers only.
- Each hunt parameter's value is a rule version `name@N`, N = the first PARAMS version with exactly
  these numbers. The adopted base v52 reads: strike `arm_c@32`, engage_on_the_way `on_the_way@19`,
  dead `exp_line@48`, loot `gm_scan_one_pass@51`, search `heading_coverage@22`, `engine@42`, zones on.
- `blocks.yaml` `hunt` (groups: engage = strike + engage_on_the_way; dead_loot = dead + loot;
  search; stop = the enclosing loop's condition and max_s, 13.5) and L1 `combat.hunt` (unverified).
  Every parameter is required and takes one of its `choices`.
- IR: `MapBlock.zones = {map, sha256}`; the Python view's `zones=zones("<map>", sha256="...")`;
  `poring_flow.zones` (the provider interface) and `scripts/flow_zones.py` (the provider over
  `map_zones.load` and its own rasters). The run-start check refuses a flow that names zones
  without a provider.

| B1 acceptance | result |
|---|---|
| 209 / 209 keys classified | v51: 209 / 209. v52 (the adopted base): 210 / 210 = choice 15, rule 32, gate 49, safety 3, reader 23, constant 37, recovery 10, experiment 13, record 4, retired 23, map_node 1. All 230 keys of all 51 versions (to v54): 0 unclassified |
| exported v51 resolves to the adopted base exactly | every version's export resolves back to PARAMS[N] EXACTLY (keys, order, values, types: 1, 1.0 and True differ; tuples stay tuples); v51 and v52 also from their committed files. v51 adopted (its live arm flag off) = `{**PARAMS[51], "loot_gm_one_pass_ab": False}`; plus `"map_zones": True` = PARAMS[52] |
| one lint fixture per new rule | 10 new rules (`rule_version`, `needs_targets`, `zones_map`, `zones_unreadable`, `zones_missing`, `zones_changed`, `zones_unreferenced`, `zones_entry`, `zones_exit`, `zones_targets` warning): each a failing fixture with its exact message and a passing twin (`packages/poring_flow/tests/test_lint_zones_hunt.py`); a coverage test names a new rule without one |

**B3: what changed.** `hunt_flow.run()` hands its decision code `hcfg.params_for(PARAMS, version)`:
PARAMS[version] exported as the hunt config and resolved back, refused before any input unless it is
exactly PARAMS[version]. Three lines in `run()` and one import; nothing else in hunt_flow.py.

| B3 acceptance | result |
|---|---|
| bytecode proof of the decision code | `scripts/nested_code_proof.py` (new: every code object by qualified name, closures included, line numbers ignored): 287 of 289 identical. Changed: `<module>` (the import) and `run`'s own body: the params_for call before `cl.select`, `cl.select` reads `prm`, `prm = PARAMS[version]` gone, and one `EXTENDED_ARG` (run's names table grew past 255 entries with `params_for`). Every decision closure inside `run` is identical. `scripts/bytecode_proof.py hunt_flow` vs main 5e5dbcf, `--harness hunt_flow.run`: 498 compared (PARAMS and VERSIONS included), 1 changed (`hunt_flow.run`), 40 added (`hunt_config.*`): PASS |
| click census unchanged | `test_click_census.py` green, unchanged; no new click site |
| session-file parity | the manifest written with the resolved dict is byte-identical to the one PARAMS[N] wrote, for all 51 versions (`DemoLog.start` into a scratch root, a fixed clock). `params` is the only session field that comes from PARAMS |

**Tests** (run in the worktree, the main venv): test_hunt_flow + test_click_census 107 passed;
test_hunt_config (new) 22 passed; poring_flow + poring_skills 337 passed (308 before); routes_flows,
flows_gat, map_zones, client_layout, bytecode_proof 78 passed + 1 skipped. ruff clean; mypy --strict
clean on poring_flow + poring_skills. The full suite was not run.

**Open points**
1. **No IR version bump** for `MapBlock.zones`: an absent reference is left out of the canonical
   JSON, so every existing flow keeps its JSON and hash; an older engine refuses a flow that has one
   (`extra="forbid"`). To confirm against section 1's "a breaking change is a new version".
2. **The run-start check** refuses named zones without a provider, but a flow that names NO zones
   still passes without one. B4's executor must always pass the provider, or a file the node does
   not name is not caught. The backend's /flows routes pass none yet (B2).
3. **The stop.** One `hunt` call is bounded by `timeout_s` (600, the IR's cap); the run's stop is
   the enclosing loop. B4 must keep the engine running across calls (or the cap changes).
4. **Choices offered**: only rule versions that exist. Loot `none`, engage `off` and strike arms B /
   A have no version on the adopted base: each is a new version, pre-registered.
5. **Names from "the first version with these numbers"**: `on_the_way@19` (v19, built and never
   run, holds v26's engage numbers); `engine@42` (v42, not adopted, holds v51's engine numbers);
   v49's loot reads `fixed_3x3@49`, as its HAND rule is retired.
6. **Judgement calls in the pattern table** (reviewed through v54): `track_clear*` gate (2b lists
   `track_*` under reader), `burst` reader and `burst_*` constant, `max_reads` gate, `exp_wait_s`
   and `icon_radius` retired, `loot_hand_still_s` a loot constant (v50 reuses it), `steer_stuck_s`
   recovery. Moving one is a one-pattern edit and a re-export.
7. **A new PARAMS key no pattern names now refuses its own version's run** (fail closed, before any
   input). `params_export.py classify` names it; after a new version, `params_export.py export`
   writes its config (the test checks committed configs only).
8. B2's editor does not know `zones` yet (`ir.ts`); the hunt block shows in the catalogue with
   free-text parameters until B2's lists.

## 8. What Batt needs to decide

**➡️ B0 DONE: Batt answered 2026-10-21 ~16:4x** (verbatim): "BLOCKS: D1 yes; D2 one "hunt" block
with groups; D3 keep PARAMS open until B4; D4 config/flows/ (committed); D5 the live A/A (2 + 2 x 60
min); D6 export only for now; D8 yes; D9 yes for the MW3-hunt slice only. Start B1-B3 (offline); B4
when I'm present."
- So: one `hunt` block with groups; PARAMS stay open until B4's A/A passes; configs and specs are
  committed under `config/flows/`; the first block-driven run is the live A/A, 2 + 2 x 60 min;
  zones from the editor are export-only; hunting evidence may badge the hunt block (D8); MW3-hunt
  may run before walk / talk readiness, for that slice only (D9).
- B1-B3 started 17:4x (offline, a subagent in a tmpfs worktree). B4 waits for Batt to be present.
  ➡️ B1 and B3 BUILT 18:2x (section 7a); B2 not started.
- ADR-0020 Amendment A stays a DRAFT until Batt accepts its text; these answers are its inputs.

The questions as asked:

1. **D1 · The split.** Block parameters = a person's choices, as named rule versions (the
   constants travel with the version). Gates, safety, readers and constants stay in the engine.
   Accept?
2. **D2 · One block or three.** One `hunt` block with groups (search, engage, dead + loot, stop),
   or `search` / `engage` / `loot` blocks in a loop? Proposed: one. v2's pipelined loop (perception,
   planner and executor in parallel, pre-emption on the way) does not split into sequential blocks
   without a loss. And the name: `hunt`?
3. **D3 · Freeze PARAMS when?** At the adopted base now (v51 when written; v52 since 14:22) (new versions only as block configs), or open until B4's
   A/A passes? Proposed: open until B4, so competition.md's loot levers are not held up; frozen
   after.
4. **D4 · Where configs and specs live.** Committed under `config/flows/` (mob ids + our numbers,
   like the zones files; `farm0.TARGETS` already commits ids), or under `data/` like filled flows
   (ADR-0020 7.1)?
5. **D5 · The first block-driven run.** A live A/A of the adopted base (v51 when written; v52 since 14:22): the block runner against
   `hunt_flow.py run --version 51`, alternating whole runs (2 + 2 x 60 min), judged against 3.89's
   null. Or the offline equality check only?
6. **D6 · Zones from the editor.** Export only first (a person commits), or a save route (a new
   writable mount of `config/map_zones` in the backend, under the Settings rules)?
7. ~~**D7 · The delegation record in a zones file.** A YAML comment (no code change), or a
   `delegated:` key (by, at, words) that the loader checks?~~ ➡️ **ANSWERED 2026-10-21 by
   Batt's own decision 1** ("reviewed_by: "agent (delegated by batt, 2026-10-21)", plus a note
   pointing to this decision; keep fail-closed loading"): built as a `delegation:` key the loader
   checks, with the reviewer in that exact form (13e497d, `config/map_zones/README.md`).
8. **D8 · Badges from hunting evidence.** May a pre-registered hunt verdict with the hard bars at 0
   over >= 4 h give the hunt block a "one path (RDP), prt_fild08" badge? Or does it stay unverified
   until an alone-test on both paths?
9. **D9 · MW3-hunt.** Allow the narrow live slice (section 5) before walk / talk readiness? That
   amends 13.8's order and section 6's executor location (host, RDP), for this slice only. Or keep
   MW2-live first?
