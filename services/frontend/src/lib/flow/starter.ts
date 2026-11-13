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
import { type ActionStmt, type Flow, IR_VERSION, RUNTIME_DEFAULT_S, WHERE_BUDGET_DEFAULT } from "./ir.ts";
import type { WorldSource } from "./api.ts";

export const STARTER_NAME = "my_first_workflow";
export const STARTER_WORLD: WorldSource = "sample";

const TARGET: Flow["target"] = { client: "kro-20211103-prere", server: "lab-rathena", locale: "en", path: "s2" };
const rest = { on_fail: "stop" as const, outcome_to: null, note: null };

/** One hotbar key press (the press_key block): a function's whole body, e.g. butterfly_wing. */
export function pressKey(key: string): ActionStmt {
  return { kind: "action", block: "press_key", concept: "ui.press_hotkey", params: { key: { kind: "lit", value: key } }, timeout_s: 2, ...rest };
}

export const XMAS_NAME = "xmas_dun02";
/** The lab's static data (data/kb): xmas_dun02 and Geffen are real lab maps, not the sample's. */
export const XMAS_WORLD: WorldSource = "local";
const GEFFEN_SAVE = { kind: "cell" as const, map: "geffen", x: 119, y: 40 };

/** The Rogue's map as an ordinary flow (Batt 2026-11-13: "why is the xmas_dun02 flow separate? make
 * it like my_first_flow, a map tab; every key a function"): xmas_dun02 hunts with the runner
 * (scripts/dungeon_hunt.py, its other settings on the Run pane) until the bag is half full, then a
 * Butterfly Wing goes home to Geffen, the save point (119, 40). Its keys are the five functions, the
 * Run helper's defaults (F1 heal, F8 Fly Wing, F9 Butterfly Wing, F4 Knife, F5 dagger). Its
 * canonical JSON is fixtures/xmas_dun02_flow.json (the flow engine's tests lint it). */
export function xmasFlow(): Flow {
  return {
    ir: IR_VERSION,
    name: XMAS_NAME,
    description: "The Rogue on xmas_dun02: hunt with the runner until the bag is half full, then a Butterfly Wing home to Geffen. Every key is a function.",
    target: { ...TARGET },
    assumes: [],
    max_runtime_s: 7200,
    where_budget: WHERE_BUDGET_DEFAULT,
    stop_when: null,
    variables: {},
    procedures: {
      heal: [pressKey("F1")],
      fly_wing: [pressKey("F8")],
      butterfly_wing: [pressKey("F9")],
      knife_on: [pressKey("F4")],
      knife_back: [pressKey("F5")],
    },
    handlers: [],
    main: null,
    workflow: {
      start_block: "xmas_dun02",
      start_entry: "here",
      run_until_stopped: false,
      blocks: [
        {
          name: "xmas_dun02",
          map: { kind: "map", map: "xmas_dun02" },
          entries: [{ name: "here", at: null, radius: 2 }],
          targets: [],
          ignore: [],
          events: [],
          resume_here: true,
          main: [
            { kind: "action", block: "assert_save_point", concept: "core.assert_save_point", timeout_s: 1, ...rest, params: { cell: { kind: "lit", value: { ...GEFFEN_SAVE } } } },
            {
              kind: "while",
              cond: { kind: "cmp", op: "<", left: { kind: "sense", sensor: "weight_percent", args: {} }, right: { kind: "lit", value: 50 } },
              body: [
                { kind: "action", block: "dungeon_hunt", concept: "combat.hunt", timeout_s: 600, ...rest,
                  params: { heal: { kind: "lit", value: "heal" }, fly: { kind: "lit", value: "fly_wing" }, knife_on: { kind: "lit", value: "knife_on" }, knife_back: { kind: "lit", value: "knife_back" } } },
              ],
              max_iter: null,
              max_s: null,
            },
            { kind: "take_exit", exit: { kind: "item_warp", warp: null, npc: null, options: [], item: null, proc: "butterfly_wing", to_block: "geffen", to_entry: "save", timeout_s: 120 } },
          ],
        },
        {
          name: "geffen",
          map: { kind: "map", map: "geffen" },
          entries: [{ name: "save", at: { ...GEFFEN_SAVE }, radius: 2 }],
          targets: [],
          ignore: [],
          events: [],
          resume_here: true,
          main: [{ kind: "stop", reason: "home" }],
        },
      ],
    },
  };
}

export function starterFlow(): Flow {
  return {
    ir: IR_VERSION,
    name: STARTER_NAME,
    description: "Town: set the save point, warp to the field. Field: attack 5 times, a wing back (the function butterfly_wing: press F9). The sample's SYNTHETIC maps and keys.",
    target: { ...TARGET },
    assumes: [],
    max_runtime_s: RUNTIME_DEFAULT_S,
    where_budget: WHERE_BUDGET_DEFAULT,
    stop_when: null,
    variables: {},
    // Batt 2026-11-13: "a wing is a function: which key it presses" (the functions tab)
    procedures: { butterfly_wing: [pressKey("F9")] },
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
            { kind: "take_exit", exit: { kind: "item_warp", warp: null, npc: null, options: [], item: null, proc: "butterfly_wing",
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
