---
title: "MW2-editor — the block programming editor (workflow canvas + block editor) on MW1's IR"
status: "BUILT as a SKELETON; MERGED 2026-10-08 (2862808) and DEPLOYED 2026-10-09 07:01 ICT (SIMULATE only; section 0); its parked items DECIDED by Batt 2026-10-09 (section 0); renamed MW2-editor"
date: 2026-10-08
owner: Batt
extends: docs/adr/0020-block-programming-flows.md
gate: "~~built AFTER walk@13 passes; stops for approval of the new frontend dependencies~~ ➡️ SUPERSEDED: Batt approved the build and both pinned dependencies on 2026-10-08 ~21:05 (section 0)"
---

# MW2-editor — the block programming editor

➡️ **Renamed 2026-10-09 (Batt):** this plan was "MW2"; it is **MW2-editor**, apart from ADR-0020
13.8's live phase, now **MW2-live** (section 0, "Naming").

**Batt (2026-10-08 ~19:00):** "once walking (walk@13) passes, build the BLOCK PROGRAMMING editor
next, so Batt can test with us. Plan first and stop for approval (new frontend dependencies + pinned
versions)."

## 0. Status: the skeleton is built (2026-10-08 night) ➡️ MERGED 2862808, DEPLOYED 2026-10-09 ~07:00 ICT

**Deployed** (Claude, in the gap after the overnight walk runs; no scored run active):
- **Backend:** a guarded `recreate:backend@90` at 06:59 for the new `poring_flow` / `poring_skills`
  mounts. ASSIST was restored automatically; the worst capture stall was 6.6 %.
  `verify_mount.py backend` passed, and `GET /flows/catalogue` answers 200 from the LAN.
- **Frontend:** a guarded `restart:frontend-dev@120` at 07:01. The lockfile installed blockly
  13.3.0 and @xyflow/react 12.12.0 into tmpfs. `/` and `/flows` both answer 200.
- **The HUD scene process had to be restarted after the backend recreate.** Its websocket stayed on
  the old container, and it kept counting sends. A display-only reconnect is a follow-up.
  ➡️ 2026-10-09: the reconnect is BUILT on `feat/hud-seen-twice`, deployed with the next HUD restart.
  Its re-read of `hud_scene.log` shows a NEW connection at ~06:59, so "stayed on the old
  container" is not established (demonstrations.md, HUD section, 2026-10-09 entry).
- The console's toggles were reset by the frontend restart, as expected.

**Batt (2026-10-08 ~21:05)** approved the build tonight and both dependencies (`blockly` 13.3.0,
`@xyflow/react` 12.12.0), which supersedes this plan's two gates. His scope: the canvas (map nodes,
typed exits incl. `death_respawn`, global and per-map event nodes, loops), double-click → a
MakeCode-style block editor with ~6 blocks plus control, both compiling to MW1's IR, JSON import /
export, the Python view, round-trip tests, lint on the canvas, SIMULATE only with verification
badges, NO live run, the console unchanged. Where this plan and that scope differ, the scope won.

**Where it is:** branch `feat/mw2-editor` (5+ commits on `d5021f2`). Nothing is merged or deployed;
the deploy steps are at the end of this section.

| Plan section | Built |
|---|---|
| 1 · four views | canvas, blocks, JSON (import / export), Python (read-only, MW1's printer). IR → canvas → IR and IR → blocks → IR are exact (tests below) |
| 2 · canvas | `services/frontend/src/components/flows/FlowCanvas.tsx`, `lib/flow/canvas.ts`: map nodes with typed exit ports, the start marker, global + per-map event nodes (a lock on `dead` / `hp_critical` / `unexpected_map`), Node-RED-style status lines (lint, then the last run), drawing / deleting an exit edits the IR, double-click opens the blocks, "simulate this node only" |
| 2 · `death_respawn` | DERIVED and read-only (this plan's proposal, open question 1): a dashed edge from every block to the save point's block, when a `dead` event exists and the flow sets (or asserts) the save point on ONE map. The IR is unchanged |
| 3 · blocks | `BlockEditor.tsx`, `lib/flow/blocks.ts`, `blockdefs.ts`: Blockly `zelos`; the palette `walk_to`, `talk_npc`, `choose_menu`, `open_window`, `use_item`, `wait`; every other catalogue block by name; if / while / repeat / wait until / set / call / stop / break / continue; the three exits; event hats (global, override, add), extend, disable. Each skill block shows its BADGE (L1 `verified_on`: verified RDP / S2 / both, unverified, unknown, core), its lint findings (⚠) and its last run |
| 4 · simulate | `poring_flow/trace.py`: MW1's `runtime.Sim` (unchanged) driven by the map sheets (routes on the walk grid, NPCs and menu keys checked, the Kafra sets the save point, a wing / a respawn go there) and a bounded SCENARIO (vitals, a loot model, a timeline, e.g. a death at t = 200 s). Returns the cells per map, the exits taken (death_respawn included), per-node outcomes and durations, the events. Input batches are COUNTED, never built or kept |
| 4 · MW2-0 | `poring_flow/kbsheet.py`, at RUN TIME and in memory (see deviation 1) |
| 5 · backend | `services/backend/src/poring_backend/routes_flows.py`: GET `/flows/catalogue`, `/flows/world`, `/flows/sample`; POST `/flows/lint`, `/flows/simulate`, `/flows/python`. Public listener, LAN viewer, Origin; POST also the CSRF token and 20 a minute per client; the IR through MW1's `ir.from_json` (1 MiB, depth 256, the schema); one computation at a time in a worker thread; no input, no mux, no storage; 503 when `poring_flow` is not installed |
| 6 · dependencies | pinned exact; licences read at those versions and recorded in THIRD_PARTY.md; Blockly's peer `jsdom` removed by a pnpm override (pnpm 10 installs peers even under `ignoreMissing`); media self-hosted in `public/blockly-media`, sounds off; no `eval` / `new Function` in either library; the CSP is unchanged |

**Deviations from this plan** (each reported, for Batt):
1. **MW2-0 is a run-time builder, not a file generator.** For the maps a flow names, the sheet is
   built in memory from what `kb_build` / `kb_route` / `kb_bindings` already extracted (L3 warps,
   NPC positions and menus, Kafras, spawns, mobs) plus the map's GAT when its directory is
   readable; a generated `data/kb/maps/<server>/<map>.json` still wins. Nothing is written. Not
   extracted yet, so the linter fails closed: map flags, Kafra services and save cell, NPC warp
   targets, items.
2. **`wait(seconds)` is `wait_until(False, timeout_s=N)`**, the IR's only wait statement (section 3's
   "core wait statement" does not exist in MW1's IR). No IR change.
3. **Blocks outside the palette:** one generic block per catalogue block (parameters by name, in
   the Python view's expression form), and a read-only block (kept exactly) for what MW2-editor has no
   block for (`for` loops, an action inside a sensor argument).
4. **Conditions are typed** in the Python view's expression form (`hp_percent() < 50`), parsed by our
   own parser and never evaluated; compare / and / or / not / an action used as a value have blocks.
5. **Unsupported bindings are listed apart** in the UI ("N unsupported"), so the first impression is
   not all red; MW1's severity (ERROR) is unchanged. Open question 4 (#6) stays Batt's.
   ➡️ SUPERSEDED 2026-10-09: Batt decided #6; the linter's own `readiness` severity replaces the
   side-count (db27d76), and the UI shows "N not ready" apart from errors.
6. **TS types:** `flow.gen.ts` is generated (json2ts, in `scripts/gen_protocol.sh`), but json2ts
   makes defaulted fields optional; the editor uses hand-written canonical types, pinned to the
   generated ones at typecheck (`lib/flow/check.ts`).
7. **The rate limit** (20 a minute) covers lint, simulate and the Python view together; the editor
   lints 2.5 s after the last change.
8. **Layout** (node positions) is not stored: it is not in the IR, so not in the hash or the export.

**Acceptance (section 7):**
1. MW1's fixtures and the sample load into the canvas and the blocks and export with the same
   canonical JSON (node tests); a browser's JSON round trip keeps `flow_hash` (pytest).
2. Round trips: IR → canvas → IR and IR → blocks → IR exact for the 3 fixtures and 200 / 300 seeded
   random flows; 400 random expressions; and in the REAL Blockly (headless Chromium, production
   build) load → save → IR was identical for the sample's town, farm and global-events scopes. In
   the browser, an exit drawn on the canvas appeared in the blocks as a placeholder, a field edited
   in Blockly reached the IR on Apply, and a selected exit was deleted from the IR.
3. The editor's lint equals MW1's for the same IR (`test_the_editor_lints_exactly_like_mw1`).
4. Simulate: the sample on its synthetic sheets (town → npc_warp → farm loop → item_warp, a death at
   t = 200 s → death_respawn → town); and a LOCAL demo on the lab's real data (prontera ↔
   prt_fild08 by walk exits, routes on the real GAT), kept in /dev/shm, never committed.
5. Flipping an L1 concept's `verified_on` flips the badge (test).
6. Hostile input refused with a message: oversize, too deep, not JSON, wrong shape (browser and
   backend); a foreign Origin, no CSRF token, `:8001`, the agent network, a compose peer (backend).
7. Production build: no CSP violation on `/flows`, requests only to the page's origin and the
   backend, the console page's scripts the same total size as on `main` (639,845 B, 8 chunks; 5
   byte-identical, 3 re-split), Blockly and React Flow only in chunks `/flows` loads on demand.
8. Targeted suites green (poring_flow, the /flows routes, settings, qa, app; ruff, mypy; the
   frontend's typecheck, lint, tests). The full Python suite is the parent's run.

**Known limit:** JSON in a browser cannot keep `2.0` apart from `2`, so a LITERAL holding an integral
float (`Lit(2.0)`) comes back as an int and the hash changes (float FIELDS such as `timeout_s` are
safe). Test `test_a_float_literal_with_an_integral_value_is_the_known_exception`; MW1's canonical
form decides. ➡️ **DECIDED by Batt 2026-10-09: recorded, not fixed.** The guard is that test (it
fails the day the round trip changes). The fix is NOT trivial: the int / float difference is
meaningful in the IR (layer 1 refuses a float into a variable declared with an int, so `X = 2.0`
then `X = 2.5` is valid and `X = 2` then `X = 2.5` is not), so MW1's canonical form cannot fold
`2.0` into `2`; keeping it would need the browser to carry float-ness (an IR encoding change).

**Naming:** this plan's "MW2" (the editor) is not ADR-0020 13.8's "MW2 · One map block and its exits,
live". One of the two needs another name (for Batt). ➡️ **DECIDED by Batt 2026-10-09: two names.**
This plan's milestone is **MW2-editor**; ADR-0020 13.8's live phase is **MW2-live**. Both documents
say so from now on (older text keeps "MW2" where it is history). The editor's own steps keep their
labels (MW2-0, MW2a-MW2e, section 8): they are MW2-editor's steps.

**Parked for Batt:** `death_respawn` authored vs derived (Q1, derived built); flows stored only as
files (Q2, as proposed); the Python view read-only (Q3, as proposed); #6 unsupported bindings as
errors (Q4); who may open `/flows` (Q5: every LAN viewer today); the PROVISIONAL NPC / option key
scheme of `kbsheet.py` and whether such keys may be committed (ADR-0020 Q11); the GAT directory is
not mounted into the backend container (without it routes there are estimates) ➡️ **DECIDED by
Batt 2026-10-09: mount it read-only. BUILT: `./data/gat:/lab-gat:ro` + `PORING_GAT_DIR` (a local
disk copy made by `scripts/flows_gat.py`, not a bind of the /dev/shm extraction, which the boot-time
backend start would create root-owned); it takes effect with the next guarded `recreate:backend`
(not during a scored client run).** The other parked items go with ADR-0020 (Batt, 2026-10-09); the MW2 naming;
the float-literal hash limit.

➡️ **DECIDED by Batt 2026-10-09** ("ADR-0020: confirmed, resolve in your order #6 -> #15 -> #13/#14
-> #18, with the MW2 parked items"), each as this plan proposed. The text above is kept as history.
- **Q1 `death_respawn`:** DERIVED and read-only, as built (the IR is unchanged). Since #15 (`dead`
  is always on) the derived edges no longer need a written `dead`: they follow the save point
  alone (`lib/flow/canvas.ts`).
- **Q2 where flows live:** files only (JSON export / import in the browser), as proposed. No
  server-side store; it is a later decision.
- **Q3 the Python view:** read-only until ADR-0020 F3's sandbox, as proposed (`POST /flows/python`
  prints; nothing parses user Python on the backend).
- **Q4 (= ADR-0020 contradictions #6):** an unsupported binding is a READINESS item: listed apart,
  it blocks the run, not the design. BUILT in db27d76 (deviation 5 above is superseded).
- **Q5 who may open `/flows`:** every LAN viewer, as today: the page is served to the LAN like the
  console, its GET routes take a LAN viewer with an allowlisted Origin, its POST routes also the
  CSRF token and 20 a minute (section 5). It computes only and sends no input; a "Watch only"
  style toggle comes with MW3's live run if Batt wants one.
- **ADR-0020 Q11, the PROVISIONAL key scheme and committing keys:** the ADR's own proposal applies:
  L3-derived NPC / option keys, and every filled flow holding them, stay LOCAL (under `data/`,
  never committed); committed flows and fixtures hold synthetic keys only. The scheme stays as
  `kbsheet.py` builds it (`n_` / `o_` + 8 hex digits of sha256, one-way); as no derived key is ever
  committed, a later change of the scheme only re-resolves local flows (ADR-0020 section 4, the
  re-pick). ADR-0020 Q11 is marked decided.
- **The naming:** MW2-editor (this plan) and MW2-live (ADR-0020 13.8), above.
- **The float-literal hash limit:** recorded with its guard, not fixed (above).

**To deploy** (the parent, in an operator-chosen window):
1. Merge `feat/mw2-editor`.
2. frontend-dev: a guarded restart (its entry runs `pnpm install --frozen-lockfile` into tmpfs, so
   the two new packages arrive from the lockfile); the production frontend image needs a guarded
   rebuild (its Dockerfile now also copies `public/`).
3. Backend, dev mode: `poring_flow` and `poring_skills` are not in the backend image. This branch's
   `compose.dev.yaml` mounts their `src` read-only on the dev backend's `PYTHONPATH`; a guarded
   `recreate:backend` applies it (a restart does not pick up new mounts; check with
   `scripts/verify_mount.py backend`). Until then the routes answer 503 `flow_engine_unavailable`
   and the page says the engine is not reachable. Production: add `poring-flow` to the backend's
   dependencies (`uv lock`), copy the two packages in its Dockerfile, and a guarded image rebuild.
4. ~~Optional: mount the GAT directory read-only into the backend for real routes on lab maps.~~
   ➡️ Batt approved 2026-10-09; built (see "Parked" above): run `scripts/flows_gat.py`, then a
   guarded `recreate:backend@90` at a gap with no scored client run, then `verify_mount.py backend`.

## 1. One IR, four views

MW1's `poring_flow` IR (`packages/poring_flow/src/poring_flow/ir.py`) stays the ONLY source of
truth. Its linter, its effective-event-set rule and its simulated executor run underneath, unchanged.

| view | where | edits | built in |
|---|---|---|---|
| workflow canvas (Node-RED / n8n-like) | browser, React Flow | map nodes, typed exits, event nodes | MW2-editor |
| block editor (MakeCode-like) | browser, Blockly | a map node's main flow + its map events | MW2-editor |
| JSON | browser (export / import) | the whole flow | MW2-editor |
| restricted Python | backend (`poring_flow.pyview`) | read-only in MW2-editor | MW2-editor shows it; import later (below) |

- **Every view compiles to the IR, and back.** The browser holds the IR JSON. Pure TS converters
  map IR ↔ canvas graph and IR ↔ Blockly workspace JSON. The backend lints, simulates and prints
  Python from the IR.
- **Round trips:** IR → view → IR must be equal by MW1's canonical `flow_hash`, for every view.
- **Python IMPORT is deferred.** MW1's parser is `ast`-only and never runs code, but its subprocess
  sandbox (ADR-0020 F3) is not built. So MW2-editor shows the Python view read-only; import comes with F3.

## 2. Level 1 — the workflow canvas

- **Map nodes:** one per map block. The title is the map's name from the active locale pack. Each
  shows a status badge (Node-RED style):
  - lint state: ok / warnings / errors;
  - after a simulate run, its outcome and duration (n8n's execution-view idea).
- **Typed exit edges:** `walk_exit`, `npc_warp`, `item_warp`, drawn from a port per exit type.
  Loops are allowed (the map graph may have cycles).
- **`death_respawn` (needs Batt's decision):** MW1's IR REFUSES an authored `death_respawn` (ADR-0020:
  the respawn map is DERIVED from `set_save_point`). Proposed: draw it as a read-only, dashed edge
  from every map node to the save point's map, computed, never drawn by hand. The alternative is to
  allow an authored one, which changes the IR.
- **Event nodes:** a GLOBAL event node (the flow's global handlers), plus per-map event nodes attached
  to their map node.
  - Each shows its mode (OVERRIDE / EXTEND / DISABLE) and its priority class.
  - A lock marks the safety-critical events (`dead`, `hp_critical`, `unexpected_map`: extend-only).
  - The EFFECTIVE event set of a map (MW1's `effective.py`) is shown on demand.
- **Double-click a map node** → the block editor for that map.
- **Run a single map node:** simulate only that map block, from a chosen start cell.

## 3. Level 2 — the block editor (Blockly)

- **Look:** Blockly's `zelos` renderer (Scratch / MakeCode style). Tabs: `main`, then one per map
  event.
- **MW2-editor's blocks** (from MW1's catalogue, `blocks.yaml`; their fields are dropdowns from local data):

| block | IR | field source |
|---|---|---|
| `walk_to(cell)` | `walk_to` | x, y; later a "pick on the map" picker |
| `talk_npc(npc)` | `talk_npc` | the map sheet's NPCs (L3) |
| `choose_menu(option)` | `choose_menu` | the NPC's menu keys (L3); the text comes from the L4 locale pack |
| `open_window(window)` | `open_window` | the L2 window names |
| `use_item(item)` | `use_item` | the KB items (data/kb, local) |
| `wait(seconds)` | the IR's core wait statement (not a registry block) | number |

  Plus the structure blocks the IR needs: the event hat ("when … do"), `if` / `else`, and `repeat N`
  (MW1 prints it as `for _ in range(n)`).
- **Each block shows its skill's verification status from the catalogue:** verified on RDP / verified
  on S2 / unverified / unknown. The badge follows L1's `verified_on`: when an alone-test flips a
  concept, the badge flips.
- **Runtime highlighting (MW3):** the active block glows during a live run, and after a run every
  block carries its outcome. MW2-editor already returns per-node traces from simulate (MW1's node paths),
  so MW3 only adds the live feed.

## 4. Safe testing: SIMULATE, no game

- `POST /flows/simulate`: MW1's simulated executor runs the IR against STATIC server data. It returns:
  - the path cells per map;
  - the exits taken;
  - per-node simulated outcomes and durations;
  - the lint findings.
  The canvas and the blocks show them.
- **The static data:** the L3 MAP SHEETS (`data/kb/maps/<server>/<map>.json`): the walk graph from
  the map cache, NPCs, warps, menu keys, Kafra options. MW1 built only the sheet INTERFACE.
  - **Prerequisite MW2-0:** the sheet GENERATOR from `kb_build` / `kb_route` + the map cache. It is
    GPL-derived, so it is generated locally and never committed (CLAUDE.md rule 4).
- **No live run in MW2-editor.** The live executor is MW3, and it gets:
  - an explicit confirmation listing every UNVERIFIED block before a live run;
  - live runs only on an `allowed` environment with the interlock green, in ASSIST (ADR-0016);
  - the agent never confirms environments.

## 5. The backend: computation only

New routes on the PUBLIC port, for LAN viewers only:

| route | does |
|---|---|
| `GET /flows/catalogue` | blocks, params, field sources, verification status |
| `POST /flows/lint` | IR → findings with node paths (MW1's linter, layers 1–3) |
| `POST /flows/simulate` | IR + start → trace |
| `POST /flows/python` | IR → the Python view (MW1's printer) |

Rules for these routes:
- **Hostile input:** every body is user-authored, so MW1's caps apply (1 MiB, depth 256, its
  validation). Plus the console's Origin, the CSRF token (as `/settings`), and 20 requests/min per
  client.
- **Never on `:8001`, never to the mux:** the routes compute and return; nothing they do sends input.
- **No storage in MW2-editor:** flows are exported / imported as JSON files by the browser. A server-side
  store is a later decision (open question 2).
- **TS types** from `packages/poring_flow/schema/flow.schema.json` via json2ts (in frontend-dev,
  drift-tested like the protocol).

## 6. New frontend dependencies (PINNED; licences read at these versions)

All of them were checked on 2026-10-08 from the npm registry. Each LICENSE file was read from its
tarball (the tarballs were opened in RAM only).

| package | version (exact) | licence | why |
|---|---|---|---|
| `blockly` | **13.3.0** (2026-09-10) | Apache-2.0 (LICENSE read: "Apache License, Version 2.0") | the block editor |
| `@xyflow/react` | **12.12.0** (2026-09-24) | MIT (LICENSE read: © webkid GmbH) | the workflow canvas |

Transitive packages (all permissive; `pnpm licenses list` is recorded in THIRD_PARTY.md at install):

| package | version | licence |
|---|---|---|
| `@xyflow/system` | 0.0.83 | MIT |
| `zustand` | 4.5.7 | MIT |
| `classcat` | 5.0.5 | MIT |
| `use-sync-external-store` | 1.x | MIT |
| `d3-drag`, `d3-zoom`, `d3-selection`, `d3-interpolate`, `d3-transition` + `d3-dispatch` / `d3-color` / `d3-ease` / `d3-timer` | 3.x | ISC |

- **Blockly's peer `jsdom` is NOT installed.** It serves headless Node use only, and the browser
  build does not need it: `pnpm.peerDependencyRules.ignoreMissing: ["jsdom"]`.
- **Install and build:**
  - installed in frontend-dev's tmpfs (never on the host disk); the lockfile is committed;
  - the production image rebuild is an operator-chosen window (guarded).
- **No outside requests:**
  - Blockly's media are SELF-HOSTED (copied into `public/`) and its sounds are OFF;
  - the CSP is unchanged (`default-src 'self'`, script nonce + `strict-dynamic`);
  - styles already allow inline (Blockly injects its CSS);
  - acceptance includes checking that neither library needs `eval` / `new Function`.
- **Only the new route grows:** both libraries are lazy-loaded client components on a new `/flows`
  page; the console's bundle is unchanged.
- **Ideas only, no code or assets:**
  - Node-RED (Apache-2.0): status badges under nodes, typed ports.
  - n8n (Sustainable Use License: NOT OSI open source): per-node run data after a run, run a single
    node.
  - MakeCode: the block look comes from Blockly's own `zelos` renderer.

## 7. MW2-editor acceptance (tests; nothing ships without them)

1. MW1's fixtures (`visit_and_choose.flow`, `farm_loop.flow`) load into the canvas and the blocks, and
   export to JSON with the SAME `flow_hash`.
2. Round-trip property tests (TS, `node --test`): random IR within MW2-editor's block set → Blockly JSON →
   IR is equal; IR → canvas → IR is equal.
3. A flow built in the editor lints with EXACTLY the findings MW1's linter gives the same IR (a
   subset of Batt's 13.6.8 example).
4. Simulate `visit_and_choose` on lab-rathena's sheets: the path, the per-node outcomes and the lint
   are shown on nodes (badges) and blocks.
5. Verification badges follow the catalogue: flipping an L1 concept's `verified_on` flips the badge
   (test).
6. Hostile import: oversize / too-deep / invalid JSON is refused with a message and no crash; the
   routes refuse a foreign Origin, a missing CSRF token, `:8001`.
7. No CSP violation on `/flows`, no outside request (media self-hosted), the console page bundle
   unchanged (size check).
8. The full Python suite, ruff, mypy, the frontend's lint / typecheck / tests stay green;
   THIRD_PARTY.md lists every new package with its licence.

## 8. Order and size

MW2-editor's steps (labels kept): MW2-0 → MW2a → MW2b → MW2c → MW2d → MW2e, roughly 2–3
working days of agent time, built after walk@13 passes.

| step | content | needs |
|---|---|---|
| MW2-0 | the L3 map-sheet generator (local, GPL-derived) | kb_build / kb_route, the map cache |
| MW2a | deps install + licences + TS types + `/flows/catalogue` + `/flows/lint` | Batt's approval of §6 |
| MW2b | the canvas (map / event nodes, typed exits, badges, double-click) | MW2a |
| MW2c | Blockly: the 6 blocks + structure blocks + converters + round-trip tests | MW2a |
| MW2d | `/flows/simulate` + the trace on nodes and blocks + run-single-node | MW2-0, MW2b, MW2c |
| MW2e | export / import, the Python view, acceptance (§7) | all |

## 9. Open questions for Batt

1. **`death_respawn` on the canvas:** derived and read-only (IR unchanged, proposed), or authored
   (an IR change)? ➡️ DECIDED by Batt 2026-10-09: derived, as built (section 0).
2. **Where flows live:** export / import files only in MW2 (proposed), or a server-side store now
   (human-only writes, like the settings store)? ➡️ DECIDED by Batt 2026-10-09: files only, as
   proposed (section 0).
3. **The Python view read-only until F3's sandbox** (proposed)? ➡️ DECIDED by Batt 2026-10-09:
   read-only, as proposed (section 0).
4. **ADR-0020's 19 contradictions** (MW1): the editor surfaces several directly:
   - #3 node paths (what a badge points at);
   - #6 an unsupported binding as an ERROR: today NO real flow lints clean, so every node would be
     red;
   - #2 `in`, #12 `Exit.item`, #16 `repeat`.
   Deciding at least #6 before MW2 avoids an all-red first impression.
   ➡️ DECIDED by Batt 2026-10-09: #6 (readiness), #13, #14, #15 and #18, each as recommended
   ([adr0020-contradictions.md](adr0020-contradictions.md)); #2, #3, #12 and #16 stay open there.
   ➡️ Later the same day all 19 were decided (round 2, ~11:20): see adr0020-contradictions.md.
5. **Who may open `/flows`:** every LAN viewer (proposed, read-only until MW3) or a toggle like
   "Watch only"? ➡️ DECIDED by Batt 2026-10-09: every LAN viewer, as today (section 0).

## 10. UI issues (Batt's testing of the deployed editor, from 2026-10-09)

Batt tests the deployed `/flows` and sends findings (screenshots); each one is fixed at its cause and
checked in a real browser before it is listed as fixed. Fixed = committed on the branch named; deployed =
the frontend-dev hot reload after the parent's merge (CSS / TSX only: no restart).

| # | date | reporter | issue | cause | fix commit | status |
|---|---|---|---|---|---|---|
| 1 | 2026-10-09 09:23 | Batt | Open a category (Events), drag a block onto the workspace: the flyout closes but a **vertical line stays at its old edge**, drawn over the workspace and the dropped block. | Blockly hides a scrollbar with the SVG presentation attribute `display="none"` on its outer `<svg>`; Tailwind's preflight `svg { display: block }` (`@layer base`) beats any presentation attribute. So the flyout's scrollbar (z-index 30) stayed drawn after the flyout closed, and also while it was open when Blockly wanted none (the line Batt saw as the flyout's divider). Measured: attribute `none`, computed `block`. The main workspace's scrollbars hide the same way. | `aab6963` (branch `fix/flows-flyout-scrollbar`): an unlayered `.injectionDiv svg[display="none"] { display: none; }` in `flows.css`, pinned by `lib/flow/editor_css.test.ts` | **fixed** on the branch; checked in headless Chromium (dev and production build): 75/75 checks after, 39/75 before (all 36 fails this scrollbar). Covered: drag from a flyout, a category clicked closed, a category whose blocks overflow (Blockly shows the scrollbar, and it is drawn), a window resize, zoom in/out, the trashcan's flyout, the editor closed and reopened 3 times (two map blocks, global events); no CSP violation. Deploy pending (parent) |
| 2 | 2026-10-09 | Claude (seen during #1's check) | An open flyout **closes by itself** when a lint result arrives while the editor is open, e.g. the editor opened within ~2.5 s of loading a sample, importing, or applying an edit. | `BlockEditor.tsx` calls `updateToolbox` in the same effect as the badge/lint decoration, so every new lint re-renders the toolbox (Blockly's `Toolbox.render` disposes and rebuilds the categories, which closes the open flyout). The toolbox depends only on the catalogue and the scope. Measured (production build): Events open at page t = 3111 ms, the lint response at 3212 ms, the categories rebuilt at 3250 ms, the flyout closed ~260 ms after it opened. Since #1's fix this close leaves no line. | none yet | **open**, not fixed here: the fix is in `BlockEditor.tsx`'s effects (update the toolbox only when the catalogue or scope changes), where the ADR-0020 work is editing in parallel; for the parent to schedule |
| 3 | 2026-10-09 14:24 | Batt (recording) | Console (not `/flows`): the **HUD status panel re-flows every few seconds**. When the yellow staleness lines appear the decision log drops BELOW the status block; when they go, it jumps back UP into a right-hand column and the status rows stretch to its height; everything below moves with it. Batt also wants the Packet timeline next to the decision log. | `HudPanel.tsx` was a `md:grid-cols-[1fr_2fr]` grid whose staleness `<ul>` spanned both columns only while present, so its appearance pushed the log into the next row; the log box grew with its lines (`min-h`, no fixed height), and the waiting state was a different, shorter section. Measured BEFORE (headless Chromium, stand-in backend, 60 s at 250 ms): the log moved \|dx\| 469 / \|dy\| 136 px at 1440x900 and \|dy\| 168 px / \|dh\| 192 px at 1280x720; the Packet timeline and Paste panel moved \|dy\| 136 px (1440) and 360 px (1280). | `c963499` (branch `feat/console-layout`): fixed grid (status 24rem, log fixed height with its own scroll that follows only from the newest line), a RESERVED 3-line feed slot, one-line rows; order stream -> HUD -> Packet timeline -> Paste -> Files; the timeline's blocks and list fixed-height, stable row keys, the reader's row kept in place | **fixed on the branch; deploy pending (parent)**. AFTER: every max \|dx\| \|dy\| \|dw\| \|dh\| = 0 for the status block, log, timeline and Paste panel at 1440x900, 1280x720 and 390x844 (the < md breakpoint stacks the columns deliberately), over full cycles of feed lines idle/stale/fresh and packet bursts; scroll check: reader kept when scrolled up, newest followed when at it, packet row pinned (0 px); no CSP violation, no console error |
| 4 | 2026-10-09 ~14:40 | Batt | The Packet timeline must show its **SOURCE STATE**: lab sniffer live = packets as today; sniffer not attesting / stale = "Sniffer offline (no packets since HH:MM:SS)", never an empty list; external environment (when one exists) = "External server: packet log not available (not captured by design)". | The panel showed only "/ws/packets disconnected" or the rows: a dead sniffer and an idle GM both looked like an empty list. | `1ffe91e` (backend `PacketSource` line on `/ws/packets`, at connect + 1 Hz: live only while the sniffer's 1 Hz heartbeat -- its PacketStats AND Attestation -- is <= 5 s old and its ingest socket is open; wall-clock receipt times for HH:MM:SS; `external` only through the inert hook `packets.external_environment_active()`, False until the PROPOSED external-environment ADR is accepted) + `c963499` (the panel's source line, and the same line inside the list whenever it would be empty or its rows are history) | **fixed on the branch; deploy pending (parent)**: needs the guarded backend restart (the line is the backend's) and the frontend hot reload. Until the restart, the new console says "Packet source: not reported (restart pending)"; an OLD console tab open across the restart lists the new line as a junk row until reloaded |
| 5 | 2026-10-09 14:57 | Batt | The feed lines mislead: "HUD scene: last message 3 s ago ... stopped or idle" is NORMAL for the delta-coded scene (nothing is sent while the scene is still). Use the 5 s keyframe as the heartbeat (stale after ~2.5 intervals); tell grey "idle: no rule running" from yellow "stopped/stale while a rule runs"; show the HUD and route-preview channels neutral when no rule runs. | `feedLine` judged every channel by "any message within 3 s": the scene sends only deltas on change plus a keyframe every `KEYFRAME_S` = 5 s (`scripts/hud_scene.py`); HUD and route are sent only while a rule runs (and the route only while a route is active), so silence was normal most of the time. | `c963499` (`lib/feeds.ts`): scene stale after 2.5 x the keyframe's `period_ms` (12.5 s) without a KEYFRAME (deltas do not count); HUD / route grey "idle (no rule running)" while `Status.bot_agents` has no `rule:` agent, route grey "idle (no route active)" after the previewer's clear; yellow only while a rule runs, after max(5 s, the rule's HUD ttl 8 s) for the HUD and 5 s mid-route for the route, with one threshold of grace from the rule's start; fresh again only after a new heartbeat (hysteresis) | **fixed on the branch; deploy pending (parent)** (frontend only). Checked live in the browser over idle -> rule running -> stale -> fresh -> idle with zero layout movement (#3); 11 unit tests on the transitions |

**How #1 was checked** (scripts kept in `/dev/shm`, not in the repo: a browser test needs a Chromium and two
local servers, outside the repo's `node --test` conventions): `chrome-headless-shell` copied into `/dev/shm`
and driven over CDP with Node's own WebSocket; the worktree's own `next dev` and `next start` on
`127.0.0.1`; and a local stand-in for the `/flows` GET routes, built in memory from the worktree's
`poring_flow` (never the real backend). The CSS domain's `getMatchedStylesForNode` named the winning rule:
preflight before the fix, the unlayered rule after it.

**How #3-5 were checked** (same approach as #1; the scripts stay in `/dev/shm/poring-lab-console-check/`,
reused by the parent for the live check after deploy): the worktree's own `next dev` on `127.0.0.1`, an
IN-MEMORY stand-in for the backend's console sockets built from the worktree's own Pydantic models (never
the real backend, never the game): Status at 1 Hz with `bot_agents` (a `rule:walk@17` that starts and
stops), operator HUD messages with a silent stretch mid-run, live route previews with clears and a stall
mid-route, HUD scene keyframes that stop while deltas go on, packet bursts, and the three source states.
`layout_check.mjs` records `getBoundingClientRect` of the status block, the decision log, the Packet
timeline and the Paste panel every 250 ms for 60 s per viewport and reports the max |dx| |dy| |dw| |dh|.
BEFORE used the first schedule (HUD / route / scene gaps across the 3 s and 5 s lines, no rules); AFTER
the rule-aware one. Screenshots: `/dev/shm/poring-lab-console-shots/` (`before-*`, `final-*`).
