// The studio's READY-MADE STARTERS (what a learner sees first, as on matpilot.org/blocks).
//
// - starterFlow(): the FIRST SCREEN since 2026-11-09 (Batt: the map canvas must be the first thing
//   a learner sees): a two-map WORKFLOW that opens on the Map tab. "town" sets the save point at
//   the Kafra, walks to the warper and takes the NPC warp to "field"; "field" attacks the nearest
//   target 5 times, then a Butterfly Wing goes back to the save point in town (a Fly Wing would
//   only teleport on the same map). It runs until stopped. Its maps, NPC keys, option key and ids
//   are the SYNTHETIC ones of Batt's sample (packages/poring_flow examples/sheets/sample), so it is
//   linted and simulated on the sample sheets (STARTER_WORLD): nothing client-derived.
// - oneMapStarter(): the first starter (2026-11-09 morning): one tab, "main": wait 1 second, wait
//   until the v1 detector sees a monster (at most 30 s), stop. Load ▸ "Starter: one map".
//
// Their canonical JSON is fixtures/starter.json and fixtures/starter_one_map.json, which the flow
// engine's tests check are canonical and lint without an error (poring_flow tests/test_models.py);
// studio.test.ts checks these objects equal them.
import { type Flow, IR_VERSION, RUNTIME_DEFAULT_S, WHERE_BUDGET_DEFAULT } from "./ir.ts";
import type { WorldSource } from "./api.ts";

export const STARTER_NAME = "my_first_workflow";
export const STARTER_WORLD: WorldSource = "sample";

const TARGET: Flow["target"] = { client: "kro-20211103-prere", server: "lab-rathena", locale: "en", path: "s2" };
const rest = { on_fail: "stop" as const, outcome_to: null, note: null };

export function starterFlow(): Flow {
  return {
    ir: IR_VERSION,
    name: STARTER_NAME,
    description: "Town: set the save point, warp to the field. Field: attack 5 times, a wing back. The sample's SYNTHETIC maps and keys.",
    target: { ...TARGET },
    assumes: [],
    max_runtime_s: RUNTIME_DEFAULT_S,
    where_budget: WHERE_BUDGET_DEFAULT,
    stop_when: null,
    variables: { WING: { kind: "lit", value: { kind: "item", id: 9002 } } },
    procedures: {},
    handlers: [],
    main: null,
    workflow: {
      start_block: "town",
      start_entry: "spawn",
      run_until_stopped: true,
      blocks: [
        {
          name: "town",
          map: { kind: "map", map: "town_1" },
          entries: [{ name: "spawn", at: { kind: "cell", map: "town_1", x: 40, y: 40 }, radius: 2 }],
          targets: [],
          ignore: [],
          events: [],
          resume_here: true,
          main: [
            { kind: "action", block: "set_save_point", concept: "nav.set_save_point", timeout_s: 60, ...rest,
              params: { npc: { kind: "lit", value: { kind: "npc", key: "n_kafra" } } } },
            { kind: "action", block: "walk_to", concept: "nav.walk_to", timeout_s: 120, ...rest,
              params: { cell: { kind: "lit", value: { kind: "cell", map: "town_1", x: 97, y: 71 } } } },
            { kind: "take_exit", exit: { kind: "npc_warp", warp: null, npc: { kind: "npc", key: "n_warper" }, options: [{ kind: "option", key: "o_to_field" }],
              item: null, to_block: "field", to_entry: "arrival", timeout_s: 120 } },
          ],
        },
        {
          name: "field",
          map: { kind: "map", map: "field_1" },
          entries: [{ name: "arrival", at: { kind: "cell", map: "field_1", x: 30, y: 30 }, radius: 2 }],
          targets: [9101, 9102, 9105, 9109].map((id) => ({ kind: "mob" as const, id })),
          ignore: [],
          events: [],
          resume_here: true,
          main: [
            { kind: "repeat", times: { kind: "lit", value: 5 }, body: [
              { kind: "action", block: "attack_nearest", concept: "combat.attack_target", timeout_s: 120, ...rest,
                params: { within: { kind: "lit", value: 12 } } },
            ] },
            { kind: "take_exit", exit: { kind: "item_warp", warp: null, npc: null, options: [], item: { kind: "var", name: "WING" },
              to_block: "town", to_entry: "spawn", timeout_s: 120 } },
          ],
        },
      ],
    },
  };
}

export function oneMapStarter(): Flow {
  return {
    ir: IR_VERSION,
    name: "my_first_flow",
    description: "",
    target: { ...TARGET },
    assumes: [],
    max_runtime_s: RUNTIME_DEFAULT_S,
    where_budget: WHERE_BUDGET_DEFAULT,
    stop_when: null,
    variables: {},
    procedures: {},
    handlers: [],
    main: [
      { kind: "wait_until", cond: { kind: "lit", value: false }, timeout_s: 1, outcome_to: null },
      {
        kind: "wait_until",
        cond: { kind: "sense", sensor: "detector_sees", args: { label: { kind: "lit", value: "monster" }, model: { kind: "lit", value: "v1" } } },
        timeout_s: 30,
        outcome_to: null,
      },
      { kind: "stop", reason: "done" },
    ],
    workflow: null,
  };
}
