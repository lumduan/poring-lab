---
title: "MW2 — the block programming editor (workflow canvas + block editor) on MW1's IR"
status: PROPOSED
date: 2026-10-08
owner: Batt
extends: docs/adr/0020-block-programming-flows.md
gate: "built AFTER walk@13 passes (Batt, 2026-10-08); this plan stops for approval of the new frontend dependencies and their pinned versions"
---

# MW2 — the block programming editor

**Batt (2026-10-08 ~19:00):** "once walking (walk@13) passes, build the BLOCK PROGRAMMING editor
next, so Batt can test with us. Plan first and stop for approval (new frontend dependencies + pinned
versions)."

## 1. One IR, four views

MW1's `poring_flow` IR (`packages/poring_flow/src/poring_flow/ir.py`) stays the ONLY source of
truth. Its linter, its effective-event-set rule and its simulated executor run underneath, unchanged.

| view | where | edits | built in |
|---|---|---|---|
| workflow canvas (Node-RED / n8n-like) | browser, React Flow | map nodes, typed exits, event nodes | MW2 |
| block editor (MakeCode-like) | browser, Blockly | a map node's main flow + its map events | MW2 |
| JSON | browser (export / import) | the whole flow | MW2 |
| restricted Python | backend (`poring_flow.pyview`) | read-only in MW2 | MW2 shows it; import later (below) |

- **Every view compiles to the IR, and back.** The browser holds the IR JSON. Pure TS converters
  map IR ↔ canvas graph and IR ↔ Blockly workspace JSON. The backend lints, simulates and prints
  Python from the IR.
- **Round trips:** IR → view → IR must be equal by MW1's canonical `flow_hash`, for every view.
- **Python IMPORT is deferred.** MW1's parser is `ast`-only and never runs code, but its subprocess
  sandbox (ADR-0020 F3) is not built. So MW2 shows the Python view read-only; import comes with F3.

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
- **MW2's blocks** (from MW1's catalogue, `blocks.yaml`; their fields are dropdowns from local data):

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
  block carries its outcome. MW2 already returns per-node traces from simulate (MW1's node paths),
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
- **No live run in MW2.** The live executor is MW3, and it gets:
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
- **No storage in MW2:** flows are exported / imported as JSON files by the browser. A server-side
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

## 7. MW2 acceptance (tests; nothing ships without them)

1. MW1's fixtures (`visit_and_choose.flow`, `farm_loop.flow`) load into the canvas and the blocks, and
   export to JSON with the SAME `flow_hash`.
2. Round-trip property tests (TS, `node --test`): random IR within MW2's block set → Blockly JSON →
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

MW2-0 → MW2a → MW2b → MW2c → MW2d → MW2e, roughly 2–3 working days of agent time, built after walk@13
passes.

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
   (an IR change)?
2. **Where flows live:** export / import files only in MW2 (proposed), or a server-side store now
   (human-only writes, like the settings store)?
3. **The Python view read-only until F3's sandbox** (proposed)?
4. **ADR-0020's 19 contradictions** (MW1): the editor surfaces several directly:
   - #3 node paths (what a badge points at);
   - #6 an unsupported binding as an ERROR: today NO real flow lints clean, so every node would be
     red;
   - #2 `in`, #12 `Exit.item`, #16 `repeat`.
   Deciding at least #6 before MW2 avoids an all-red first impression.
5. **Who may open `/flows`:** every LAN viewer (proposed, read-only until MW3) or a toggle like
   "Watch only"?
