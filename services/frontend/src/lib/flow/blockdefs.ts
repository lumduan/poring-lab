// The block editor's block TYPES (Blockly's JSON block definitions) and its toolbox. Pure data:
// the converter (blocks.ts) writes and reads exactly these field and input names, and
// blocks.test.ts checks that against this file without loading Blockly. The component
// (components/flows/BlockEditor.tsx) registers them with Blockly in the browser.
//
// Field kinds that SAVE their value: field_input (text), field_number, field_dropdown,
// field_label_serializable, and round 21's pickers (field_pl_text: a text, field_pl_num: a
// number). A plain field_label is NOT saved: BADGE (the skill's verification badge) and RUN (the
// last simulate run) are decorations the component fills in after loading; nor is a field_image
// (the model blocks' eye).
//
// Since 2026-11-09 (the studio, docs/planning/flows-studio.md) the blocks carry MatPilot's words,
// STYLES and categories (theme.ts): only words, colours and the toolbox changed; every type, field,
// input and the IR they convert to stayed. Two blocks were added: the TRAINED MODELS as sensors
// (pl_detect_sees / pl_detect_count, models.ts; ADR-0020 Amendment B).

export type FieldKind = "field_input" | "field_number" | "field_dropdown" | "field_label_serializable" | "field_label" | typeof PICK_NUM | typeof PICK_TEXT;
/** Round 21 (live-blocks.md 12.5, ADR-0020 Amendment K): a field that is not a NAME is a PICKER
 * (components/flows/blockly-pickers.ts): `field_pl_num` saves a number as field_number did,
 * `field_pl_text` a text as field_input did; its `pick` says what opens (lib/flow/pickers.ts). */
export const PICK_NUM = "field_pl_num";
export const PICK_TEXT = "field_pl_text";
import { groupOf, SETTING_BLOCKS, SETTING_GEOMETRY, SETTING_NOTE_ROWS, SETTING_ROW_BUDGET, type SettingField, settingFields, settingRows, settingTooltip, settingType, SETTINGS, unitOf, varText, wrapUnits } from "./settings.ts";
import { MAX_RANK } from "./ir.ts";
import type { PickSpec, RefKind } from "./pickers.ts";
import { BLOCK_STYLE } from "./theme.ts";

export type ArgDef =
  | { type: FieldKind; name: string; text?: string; value?: number; min?: number; max?: number; precision?: number; options?: [string, string][]; class?: string; pick?: PickSpec }
  | { type: "input_value" | "input_statement"; name: string; check?: string | string[] }
  | { type: "input_dummy" }
  | { type: "input_end_row"; name: string }
  | { type: "field_image"; src: string; width: number; height: number; alt: string };
export type BlockDef = {
  type: string;
  message0: string;
  args0?: ArgDef[];
  message1?: string;
  args1?: ArgDef[];
  message2?: string;
  args2?: ArgDef[];
  message3?: string;
  args3?: ArgDef[];
  message4?: string;
  args4?: ArgDef[];
  message5?: string;
  args5?: ArgDef[];
  message6?: string;
  args6?: ArgDef[];
  message7?: string;
  args7?: ArgDef[];
  message8?: string;
  args8?: ArgDef[];
  previousStatement?: null | string;
  nextStatement?: null | string;
  output?: null | string;
  colour?: string;
  style?: string;
  tooltip?: string;
  inputsInline?: boolean;
  mutator?: string;
  extensions?: string[];
};

/** A block type's MatPilot style (theme.ts BLOCK_STYLE). */
const st = (type: string): string => BLOCK_STYLE[type] ?? "mp_setup_blocks";

/** The model blocks' icon: an eye (the "device" of a sensor block), drawn here, no outside file. */
export const EYE_ICON =
  "data:image/svg+xml," +
  encodeURIComponent(
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16"><path d="M1 8s2.6-5 7-5 7 5 7 5-2.6 5-7 5-7-5-7-5z" fill="none" stroke="#fff" stroke-width="1.5"/><circle cx="8" cy="8" r="2.2" fill="#fff"/></svg>',
  );

const badge: ArgDef = { type: "field_label", name: "BADGE", text: "", class: "pl-badge" };
const run: ArgDef = { type: "field_label", name: "RUN", text: "", class: "pl-run" };
const eye: ArgDef = { type: "field_image", src: EYE_ICON, width: 16, height: 16, alt: "detector" };
const label = (name: string): ArgDef => ({ type: "field_label_serializable", name, text: "" });
const text = (name: string, value = ""): ArgDef => ({ type: "field_input", name, text: value });

/** The engine's defaults for a trigger's runaway guard and insert failure limit (poring_flow's
 * Trigger / Handler: max_fires_per_10min 10, max_insert_fails 3; pinned against the Python by
 * project.test.ts). An event block shows them as defaults (an empty field), not as values. */
export const DEFAULT_MAX_10 = 10;
export const DEFAULT_FAILS = 3;
// --- round 21: the pickers (the same saved value as the plain field: a number, a text) ------------
/** A reference: a searchable list of what exists (`optional`: the word an empty field shows). */
const ref = (name: string, kind: RefKind, title: string, value = "", more: { role?: string; optional?: string } = {}): ArgDef => ({ type: PICK_TEXT, name, text: value, pick: { kind: "ref", ref: kind, title, ...more } });
/** Seconds: a stepper with a slider over `hi` (typing may go past it; the field's own min / max
 * stay as they were, so a loaded value is never clamped). */
const secs = (name: string, value: number, title: string, hi = 60, step = 0.5, presets = [0.5, 1, 2, 5, 10], more: { min?: number; max?: number } = {}): ArgDef => ({ type: PICK_NUM, name, value, ...more, pick: { kind: "stepper", lo: 0, hi, step, unit: "s", presets, title } });
/** A map cell's x and y: two steppers, one picker for both. */
const cell = (title: string): ArgDef[] => [
  { type: PICK_NUM, name: "X", value: 0, pick: { kind: "cell", axis: "x", pair: "Y", title } },
  { type: PICK_NUM, name: "Y", value: 0, pick: { kind: "cell", axis: "y", pair: "X", title } },
];
/** A whole number in a TEXT field where empty means none or the default (`empty`: what the empty
 * field shows; `none`: the picker's button). */
const optnum = (name: string, lo: number, hi: number, empty: string, none: string, title: string): ArgDef => ({ type: PICK_TEXT, name, text: "", pick: { kind: "optnum", lo, hi, step: 1, empty, none, title } });
/** An expression's or a call's inputs as text, edited by the condition / inputs picker with the
 * typed fallback that autocompletes. */
const expr = (name: string, mode: "expr" | "args" | "callargs", value: string, title: string): ArgDef => ({ type: PICK_TEXT, name, text: value, pick: { kind: "expr", mode, title } });
const opts = (vals: readonly string[]): [string, string][] => vals.map((v) => [v, v]);
// Blockly only lets a MUTATOR add saveExtraState / loadExtraState (a plain extension that does is
// refused), so the lossless state rides on mutators without a mutator UI.
const STATE = "pl_state";

const stmt = (def: Omit<BlockDef, "previousStatement" | "nextStatement" | "style">): BlockDef => ({
  ...def,
  style: st(def.type),
  previousStatement: null,
  nextStatement: null,
  mutator: STATE,
});
/** A value block; `output` "Boolean" draws a question (a hexagon), "Number" a round reporter. */
const value = (def: Omit<BlockDef, "style">): BlockDef => ({ ...def, style: st(def.type), output: def.output ?? null, mutator: def.mutator ?? STATE });

export const CMP_OPTIONS = ["<", "<=", ">", ">=", "==", "!=", "in", "not in"];
export const PRIORITY_OPTIONS = ["critical", "survival", "upkeep"];
export const MODE_OPTIONS = ["preempt", "insert"];
export const THEN_OPTIONS = ["resume", "skip_block", "restart_flow", "relocate", "stop"];
/** The hotbar keys a press_key block offers (row 1: the keys the runner reads; scripts/flow_config.py
 * KEYS, the catalogue's `options` for press_key). */
export const HOTKEYS = ["F1", "F2", "F3", "F4", "F5", "F6", "F7", "F8", "F9"] as const;
/** The lab's credentials by name (catalogue `credentials`; .env's account prefixes, never secrets). */
export const CREDENTIALS = ["lab_gm", "lab_player"] as const;
/** The Rogue's runner block (blocks.yaml `dungeon_hunt`): each ROLE names the function the runner
 * calls for it (Batt 2026-11-13: "every key a function"), in the block's order. The fifth, `home`
 * (the one box, Batt 2026-11-13 ~21:4x: the runner flies home itself on the Butterfly Wing), is
 * OPTIONAL: an empty field is no home role (the map's item warp by function gives the key). Stage 3
 * (live-blocks.md 3.3, Batt 2026-11-13: "make respawn a function block"): the OPTIONAL respawn
 * roles name the death exit's two functions of click_at (empty: the runner's own points; an empty
 * confirm with a respawn: this server asks no confirmation). 2026-11-14 (live-blocks.md 10): the
 * OPTIONAL eat role names the function the box's events call to eat a food item from the hotbar (one
 * press_key of its input, the item's key; empty: the box eats nothing inside the hunt core). */
export const RUNNER_ROLES = [
  { param: "heal", field: "HEAL", words: "heal", fn: "heal", optional: false },
  { param: "fly", field: "FLY", words: "Fly Wing", fn: "fly_wing", optional: false },
  { param: "knife_on", field: "KNIFE_ON", words: "Knife on", fn: "knife_on", optional: false },
  { param: "knife_back", field: "KNIFE_BACK", words: "Knife back", fn: "knife_back", optional: false },
  { param: "home", field: "HOME", words: "home (Butterfly Wing)", fn: "butterfly_wing", optional: true },
  { param: "respawn", field: "RESPAWN", words: "respawn", fn: "respawn_button", optional: true },
  { param: "respawn_confirm", field: "RESPAWN_OK", words: "respawn confirm", fn: "respawn_ok", optional: true },
  { param: "eat", field: "EAT", words: "eat", fn: "eat", optional: true },
] as const;

/** A runner role's slot: the functions of the node and Global, its usual one first. `value`: the
 * field's default as before round 21 (home's is the Butterfly Wing's function; the other optional
 * roles start empty). */
function role(field: string, value: string): ArgDef {
  const r = RUNNER_ROLES.find((x) => x.field === field)!;
  return ref(field, "role", `the function for ${r.words}`, value, r.optional ? { role: r.param, optional: "none" } : { role: r.param });
}
/** An exit's arrival: a map node of the project, and one of its entries. */
const arrive = (): ArgDef[] => [ref("TO_BLOCK", "node", "the map node she arrives on"), ref("TO_ENTRY", "entry", "where she arrives on it")];

export const BLOCK_DEFS: BlockDef[] = [
  // --- MW2's palette: one block per skill (section 3) ---
  stmt({
    type: "pl_walk_to",
    message0: "walk to %1 x %2 y %3 %4 %5",
    args0: [ref("MAP", "map", "the map"), ...cell("the cell to walk to"), badge, run],
    inputsInline: true,
    tooltip: "walk_to(cell): walk to a cell of this map",
  }),
  stmt({
    type: "pl_talk_npc",
    message0: "talk to the NPC %1 %2 %3",
    args0: [text("NPC"), badge, run],
    tooltip: "talk_npc(npc): walk up to the NPC and open its dialog (an L3 key)",
  }),
  stmt({
    type: "pl_choose_menu",
    message0: "choose menu option %1 %2 %3",
    args0: [text("OPTION"), badge, run],
    tooltip: "choose_menu(option): an option KEY, matched by its text on screen, never by index",
  }),
  stmt({
    type: "pl_open_window",
    message0: "open window %1 %2 %3",
    args0: [ref("WINDOW", "window", "the window to open", "basic_info"), badge, run],
    tooltip: "open_window(window): an L2 window name (ADR-0011 anchor map)",
  }),
  stmt({
    type: "pl_use_item",
    message0: "use item %1 %2 %3",
    args0: [text("ITEM"), badge, run],
    tooltip: "use_item(item): an item id, or a variable naming one (e.g. POTION)",
  }),
  // --- the shop / Kafra / storage blocks as SENTENCES (2026-11-09 pm, Batt: Actions, not
  // "More skills"): each the same catalogue action as before (the IR is unchanged), its parameters
  // as fields; a parameter the field cannot hold exactly keeps the generic block (SENTENCE below)
  stmt({
    type: "pl_set_save_point",
    message0: "set the save point at the Kafra %1 %2 %3",
    args0: [text("NPC"), badge, run],
    tooltip: "set_save_point(npc): save the respawn point with this Kafra (an L3 key)",
  }),
  stmt({
    type: "pl_kafra_teleport",
    message0: "teleport with the Kafra %1 to %2 %3 %4",
    args0: [text("NPC"), ref("TO", "map", "the map she arrives in"), badge, run],
    tooltip: "kafra_teleport(npc, to=map): pay the Kafra and arrive in that map",
  }),
  stmt({
    type: "pl_kafra_store",
    message0: "store %1 at the Kafra %2, or all but %3 %4 %5",
    args0: [text("ITEMS"), text("NPC"), text("KEEP"), badge, run],
    tooltip: "kafra_store(npc, items=..., all_except=...): item ids or variables, comma separated; leave one of the two empty",
  }),
  stmt({
    type: "pl_kafra_withdraw",
    message0: "take %1 from the Kafra %2 %3 %4",
    args0: [text("ITEMS"), text("NPC"), badge, run],
    tooltip: "kafra_withdraw(npc, items=...): item ids or variables, comma separated",
  }),
  stmt({
    type: "pl_rent_cart",
    message0: "rent a cart from the Kafra %1 %2 %3",
    args0: [text("NPC"), badge, run],
    tooltip: "rent_cart(npc)",
  }),
  stmt({
    type: "pl_buy",
    message0: "buy %1 from %2 %3 %4",
    args0: [text("ITEMS"), text("NPC"), badge, run],
    tooltip: "buy(npc, items=...): item ids or variables, comma separated",
  }),
  stmt({
    type: "pl_sell",
    message0: "sell all but %1 to %2 %3 %4",
    args0: [text("KEEP"), text("NPC"), badge, run],
    tooltip: "sell(npc, keep=...): sells every item NOT listed (irreversible); item ids or variables, comma separated",
  }),
  stmt({
    type: "pl_wait",
    message0: "wait %1 seconds %2",
    args0: [secs("SECONDS", 1, "seconds to wait"), run],
    tooltip: "wait: the IR's core wait statement (wait_until(False, timeout_s=N)); no input",
  }),
  // --- every other catalogue block, lossless: its parameters by name ---
  stmt({
    type: "pl_action",
    message0: "%1 ( %2 ) %3 %4",
    args0: [label("BLOCK"), expr("ARGS", "args", "", "its inputs"), badge, run],
    tooltip: "A catalogue block. Parameters by name, e.g. within=12 or npc=npc(\"n_k1\")",
  }),
  // --- control ---
  stmt({
    type: "pl_if",
    message0: "if %1 %2",
    args0: [{ type: "input_value", name: "COND" }, run],
    message1: "then %1",
    args1: [{ type: "input_statement", name: "THEN" }],
    message2: "else %1",
    args2: [{ type: "input_statement", name: "ELSE" }],
  }),
  stmt({
    type: "pl_while",
    message0: "while %1 %2",
    args0: [{ type: "input_value", name: "COND" }, run],
    message1: "do %1",
    args1: [{ type: "input_statement", name: "BODY" }],
  }),
  stmt({
    type: "pl_repeat",
    message0: "repeat %1 times %2",
    args0: [{ type: "input_value", name: "TIMES" }, run],
    message1: "do %1",
    args1: [{ type: "input_statement", name: "BODY" }],
    tooltip: "repeat N (the Python view prints for _ in range(N))",
  }),
  stmt({
    type: "pl_wait_until",
    message0: "wait until %1 at most %2 s %3",
    args0: [{ type: "input_value", name: "COND" }, secs("TIMEOUT", 10, "seconds to wait at most", 120, 1, [5, 10, 30, 60]), run],
  }),
  stmt({
    type: "pl_set",
    message0: "set %1 to %2",
    args0: [ref("VAR", "variable", "the variable to set", "x"), { type: "input_value", name: "VALUE" }],
  }),
  stmt({ type: "pl_call", message0: "call %1 ( %2 )", args0: [ref("PROC", "function", "the function to call", "my_function"), expr("ARGS", "callargs", "", "its inputs")], inputsInline: true,
    tooltip: "call a function: this node's own, or Global's. Its inputs as in Python: F8, times=2" }),
  stmt({ type: "pl_return", message0: "return %1", args0: [{ type: "input_value", name: "VALUE" }],
    tooltip: "end the function here; with a value, the call gives it back (a function used as a value)" }),
  value({ type: "pl_callv", message0: "%1 ( %2 )", args0: [ref("PROC", "function", "the function whose value it is", "my_function"), expr("ARGS", "callargs", "", "its inputs")], inputsInline: true,
    tooltip: "a function's value: what its return gives back" }),
  // --- the session (the project model, 2026-11-13): a login node's and a character node's main;
  // simulated (the bot's real login is ro_agent's Python); the account is a CREDENTIAL NAME, never a secret
  stmt({
    type: "pl_login",
    message0: "log in to %1 as %2 %3 %4",
    args0: [ref("SERVER", "server", "the server", "lab-rathena"), { type: "field_dropdown", name: "CREDENTIAL", options: opts(CREDENTIALS) }, badge, run],
    tooltip: "login(server, credential): the server's id (the Settings page) and a credential by NAME (as n8n's): the password is never in a block",
  }),
  stmt({
    type: "pl_choose_character",
    message0: "choose the character %1 %2 %3",
    args0: [text("CHAR", ""), badge, run],
    tooltip: "choose_character(name=...): empty = the slot the client remembers (as the bot's login does)",
  }),
  // --- every key a FUNCTION (Batt 2026-11-13: "Fly Wing, Butterfly Wing, the Knife swap, a skill:
  // make each a function whose body says which key F1-F9 to press; share them with Save / Load")
  // the save point, as a sentence (matpilot 2026-11-13 #12: it showed as raw Python)
  stmt({
    type: "pl_save_point",
    // matpilot round 20 #2: two rows, so the main tab's first block shows whole at 390 px
    message0: "the save point is",
    message1: "on %1",
    args1: [ref("MAP", "save_map", "the save point's map (a Kafra's town)", "geffen")],
    message2: "x %1 y %2",
    args2: cell("the save point's cell"),
    message3: "%1",
    args3: [run],
    inputsInline: true,
    tooltip: "assert_save_point(cell): YOU say where the save point is (a Butterfly Wing and a death land there); no input, and it stays a warning at approval",
  }),
  stmt({
    type: "pl_press_key",
    message0: "press key %1 %2 %3",
    args0: [{ type: "field_dropdown", name: "KEY", options: opts(HOTKEYS) }, badge, run],
    tooltip: "press_key(key): press one hotbar key (row 1, F1-F9). Whatever the player put on that slot is used: an item, a skill, a piece of equipment, a wing",
  }),
  stmt({
    type: "pl_press_key_v",
    message0: "press key %1 %2",
    args0: [{ type: "input_value", name: "KEY" }, run],
    inputsInline: true,
    tooltip: "press_key(key) with the key as a value: a function's input (e.g. key) or a text like \"F8\" (F1-F9)",
  }),
  stmt({
    type: "pl_dungeon_hunt",
    // matpilot round 20 #2: one role a row (two where its words are long), so the main tab's
    // program shows whole at 390 px (main's block ran 397 px wide); the fields are the same
    message0: "hunt with the runner",
    message1: "(dungeon_hunt.py) %1 %2 %3 %4",
    args1: [{ type: "input_end_row", name: "ROW_NAME" }, badge, { type: "input_end_row", name: "ROW_BADGE" }, run],
    // round 21: a role is a picker (its ▾ widened "Fly Wing: call fly_wing ▾" to 309 units and
    // "Knife on: call knife_on ▾" to 305, over the 300 budget): "Fly Wing:" and "Knife on:" on rows
    // of their own, as "Knife back:"
    message2: "heal: call %1 %2 Fly Wing: %3 call %4",
    args2: [role("HEAL", "heal"), { type: "input_end_row", name: "ROW_HEAL" }, { type: "input_end_row", name: "ROW_FLY" }, role("FLY", "fly_wing")],
    message3: "Knife on: %1 call %2 %3 Knife back: %4 call %5",
    args3: [{ type: "input_end_row", name: "ROW_KNIFE_ON" }, role("KNIFE_ON", "knife_on"), { type: "input_end_row", name: "ROW_KNIFE" }, { type: "input_end_row", name: "ROW_KNIFE_BACK" }, role("KNIFE_BACK", "knife_back")],
    message4: "home (Butterfly Wing): %1 call %2",
    args4: [{ type: "input_end_row", name: "ROW_HOME" }, role("HOME", "butterfly_wing")],
    message5: "after a death: %1 call %2",
    args5: [{ type: "input_end_row", name: "ROW_RESPAWN" }, role("RESPAWN", "")],
    message6: "then confirm: %1 call %2",
    args6: [{ type: "input_end_row", name: "ROW_RESPAWN_OK" }, role("RESPAWN_OK", "")],
    message7: "eat (from the hotbar): %1 call %2",
    args7: [{ type: "input_end_row", name: "ROW_EAT" }, role("EAT", "")],
    tooltip: "dungeon_hunt(...): the Rogue's runner hunts this map (only a map that has a runner: xmas_dun02). Each role names the function it calls: a function of one key press is the key the runner presses; a function of presses and waits (the Knife swap, the way home) plays at the runner's own moment. home: the Butterfly Wing it flies home on when the bag is half full or on Stop (empty: the map's item warp by function). after a death: the functions that click the death dialog's button and its confirmation (click_at; empty: the runner's own points, the respawn tab's setting blocks). eat: the function your events call to eat a food item from the hotbar, e.g. eat(key) pressing its input, called as eat(\"F6\") (empty: nothing is eaten in the hunt); hotbar_count(key=\"F6\") reads that slot's count. Its other settings: the setting blocks in this node's tabs (the toolbox's Settings)",
  }),
  stmt({ type: "pl_stop", message0: "stop %1 %2", args0: [ref("REASON", "stop", "why it stops (the run's end words)", "done"), run] }),
  stmt({ type: "pl_break", message0: "break" }),
  stmt({ type: "pl_continue", message0: "continue" }),
  // --- exits (13.1): they leave the map block ---
  stmt({
    type: "pl_exit_walk",
    message0: "walk exit at %1 x %2 y %3, arrive on %4 at %5 %6",
    args0: [ref("MAP", "map", "the map of the warp"), ...cell("the warp's cell"), ...arrive(), run],
    tooltip: "walk_exit: walk onto an L3 warp of this map; arrive at <block>.<entry>",
  }),
  stmt({
    type: "pl_exit_npc",
    message0: "npc warp: talk to %1 choose %2, arrive on %3 at %4 %5",
    args0: [text("NPC"), text("OPTIONS"), ...arrive(), run],
    tooltip: "npc_warp: talk to the NPC, choose each option key (comma separated) in order",
  }),
  stmt({
    type: "pl_exit_item",
    message0: "item warp: use %1, arrive on %2 at %3 %4",
    args0: [text("ITEM"), ...arrive(), run],
    tooltip: "item_warp: e.g. a Butterfly Wing, to the SAVE POINT (never 'the previous map')",
  }),
  stmt({
    type: "pl_exit_item_fn",
    message0: "item warp: call %1, arrive on %2 at %3 %4",
    args0: [ref("FN", "function", "the function that presses the wing's key", "butterfly_wing"), ...arrive(), run],
    tooltip: "item_warp by a function: call the function that presses the Butterfly Wing's key; she lands on the SAVE POINT",
  }),
  stmt({
    type: "pl_raw",
    message0: "%1 %2",
    args0: [label("TEXT"), run],
    tooltip: "Not editable as blocks in MW2 (kept exactly): edit it in the JSON view",
  }),
  // --- expressions ---
  value({
    type: "pl_raw_expr",
    message0: "%1",
    args0: [label("TEXT")],
    tooltip: "Not editable as blocks in MW2 (kept exactly): edit it in the JSON view",
  }),
  value({ type: "pl_expr", message0: "%1", args0: [expr("TEXT", "expr", "hp_percent() < 50", "the value")],
    tooltip: "An expression in the Python view's form, e.g. hp_percent() < 50, sees(mob=mob(9109), within=15)" }),
  value({
    type: "pl_compare",
    message0: "%1 %2 %3",
    args0: [{ type: "input_value", name: "A" }, { type: "field_dropdown", name: "OP", options: opts(CMP_OPTIONS) },
      { type: "input_value", name: "B" }],
    inputsInline: true,
  }),
  value({ type: "pl_not", message0: "not %1", args0: [{ type: "input_value", name: "X" }] }),
  value({
    type: "pl_logic",
    message0: "%1",
    args0: [{ type: "field_dropdown", name: "OP", options: opts(["and", "or"]) }],
    mutator: "pl_logic",
    tooltip: "and / or over its terms (T0, T1, ...)",
  }),
  value({
    type: "pl_do",
    message0: "%1 ( %2 ) %3",
    args0: [label("BLOCK"), expr("ARGS", "args", "", "its inputs"), badge],
    inputsInline: true,
    tooltip: "An action used as a value: its outcome (OK, FAILED, ...)",
  }),
  // --- the TRAINED MODELS as sensors (Batt 2026-11-09; models.ts, ADR-0020 Amendment B): the model
  // is the "device", like a colour sensor on a port; the dropdowns' menus come from the catalogue
  value({
    type: "pl_detect_sees",
    extensions: ["pl_detector_menus"], // components/flows/blockly-fields.ts: the menus
    message0: "%1 detector %2 sees %3",
    args0: [eye, { type: "field_dropdown", name: "MODEL", options: [["v1", "v1"]] }, { type: "field_dropdown", name: "CLASS", options: [["monster", "monster"]] }],
    output: "Boolean",
    inputsInline: true,
    tooltip: "detector_sees(model, class): True when the trained model boxes that class in the picture (pixels only)",
  }),
  value({
    type: "pl_detect_count",
    extensions: ["pl_detector_menus"], // components/flows/blockly-fields.ts: the menus
    message0: "%1 detector %2 count of %3",
    args0: [eye, { type: "field_dropdown", name: "MODEL", options: [["v1", "v1"]] }, { type: "field_dropdown", name: "CLASS", options: [["monster", "monster"]] }],
    output: "Number",
    inputsInline: true,
    tooltip: "detector_count(model, class): how many boxes of that class the trained model finds (a detector only)",
  }),
  // --- hats ---
  {
    type: "pl_main",
    // matpilot round 20 #2: the title on up to two rows (titleLines), so it shows whole at 390 px
    message0: "%1 %2 %3 %4",
    args0: [
      { type: "field_label", name: "TITLE", text: "when the program starts" },
      { type: "input_end_row", name: "ROW_TITLE" },
      { type: "field_label", name: "TITLE2", text: "" },
      { type: "input_end_row", name: "ROW_TITLE2" },
    ],
    message1: "%1",
    args1: [{ type: "input_statement", name: "DO" }],
    style: st("pl_main"),
    mutator: STATE,
    tooltip: "The program's start (a map block's: when the flow arrives on its map). Every path ends in an exit or a stop",
  },
  {
    type: "pl_def",
    message0: "function %1 ( %2 )",
    // a function's NAME and its inputs are names it DEFINES: free text (on the monsters tab the name
    // suggests attack_<class> for each monster of the node's model)
    args0: [{ type: PICK_TEXT, name: "NAME", text: "my_function", pick: { kind: "name", title: "the function's name (on the monsters tab: a monster's recipe)" } }, text("PARAMS", "")],
    message1: "%1",
    args1: [{ type: "input_statement", name: "DO" }],
    style: st("pl_def"),
    mutator: STATE,
    inputsInline: true,
    tooltip: "A FUNCTION: any tab of this node (and, in Global, every node) can call it by its name. Its inputs as in Python: key, times=1, *args, **kwargs. The same name on a map replaces Global's there",
  },
  {
    type: "pl_vardecl",
    message0: "variable %1 = %2",
    args0: [text("NAME", "x"), { type: "input_value", name: "VALUE" }],
    style: st("pl_vardecl"),
    mutator: STATE,
    tooltip: "A variable of this tab (in Global: shared by every node); its first value. A map's variable of the same name replaces Global's there",
  },
  {
    // matpilot round 17 N4: EVERY trigger field the Python view writes (@on(..., cooldown_s=0.7,
    // max_per_run=1, ...)) is a field here, one row each (inputsInline false: under the zelos
    // renderer every input starts its own row, so the block is as wide as its widest row, not as
    // all of them in one line: the survival events were 1022-1102 px wide on a 1008 px canvas)
    type: "pl_event",
    message0: "%1 when %2",
    args0: [label("SCOPE"), { type: "input_value", name: "WHEN" }],
    message1: "event %1 class %2 rank %3",
    args1: [text("NAME", "my_event"), { type: "field_dropdown", name: "PRIORITY", options: opts(PRIORITY_OPTIONS) },
      optnum("RANK", 1, MAX_RANK, "auto", "the table order (13.6.3)", "its rank inside its class (1 runs first)")], // IR 2 (ADR-0020 #13): 1..99 inside the class; empty = 13.6.3's table order
    message2: "mode %1 then %2",
    args2: [{ type: "field_dropdown", name: "MODE", options: opts(MODE_OPTIONS) }, { type: "field_dropdown", name: "THEN", options: opts(THEN_OPTIONS) }],
    message3: "until %1",
    args3: [{ type: "input_value", name: "UNTIL" }],
    message4: "rearm %1",
    args4: [{ type: "input_value", name: "REARM" }],
    message5: "pause %1 s after each run · at most %2 a run",
    args5: [secs("COOLDOWN", 0, "the pause after each run", 30, 0.1, [0, 0.5, 1, 3, 10], { min: 0, max: 3600 }), optnum("MAX_RUN", 1, 100, "—", "no limit", "at most this many runs in a run of the flow")],
    // matpilot round 18 #3: the runaway guard and the insert failure limit are the ENGINE's defaults
    // when nobody set them (poring_flow's Trigger: 10 and 3; the Python view omits them then), so
    // their fields stay EMPTY for a default and the row names the default; a number = one a person set
    message6: `at most %1 a minute · %2 per 10 min (default ${DEFAULT_MAX_10})`,
    args6: [optnum("MAX_MIN", 1, 60, "—", "no limit", "at most this many runs a minute"), optnum("MAX_10", 1, 100, "default", `the default (${DEFAULT_MAX_10})`, "the runaway guard: runs per 10 minutes")],
    message7: `%1 failed inserts (default ${DEFAULT_FAILS}): escalate to %2`,
    args7: [optnum("FAILS", 1, 10, "default", `the default (${DEFAULT_FAILS})`, "an insert's failures before it escalates"), ref("ESCALATE", "escalate", "the function it escalates to", "", { optional: "none" })],
    message8: "do %1",
    args8: [{ type: "input_statement", name: "DO" }],
    inputsInline: false,
    style: st("pl_event"),
    mutator: STATE,
    tooltip:
      `when <condition> do: until (repeat until it holds) and rearm (one-shot) are exclusive; rank orders the events of one class (empty: 13.6.3's table order); pause = cooldown_s (seconds after the body's last run), at most … a run / a minute (empty: no limit), … per 10 minutes (the runaway guard; empty: the engine's default, ${DEFAULT_MAX_10}), an insert's failures before it escalates (empty: the default, ${DEFAULT_FAILS}) and the function it escalates to (empty: none)`,
  },
  {
    type: "pl_extend",
    message0: "extend event %1 on this map",
    args0: [text("KEY")],
    message1: "with %1",
    args1: [{ type: "input_statement", name: "DO" }],
    style: st("pl_extend"),
    mutator: STATE,
    tooltip: "EXTEND: the global event runs with these steps too (after its body if safety-critical)",
  },
  {
    type: "pl_disable",
    message0: "disable event %1 on this map",
    args0: [text("KEY")],
    style: st("pl_disable"),
    mutator: STATE,
    tooltip: "DISABLE: the global event does not run here (never a safety-critical one)",
  },
];

/** THE SETTING BLOCKS (live-blocks.md 12; Batt 2026-11-14 ~15:2x: "make them ALL blocks"): one
 * block type per setting of the runner's hunt core (settings.ts), a top-level block like a
 * variable's. matpilot round 20 #2: laid out on ROWS so no row is wider than what shows at 390 px
 * (settings.ts settingRows, SETTING_ROW_BUDGET): its words wrapped over one or more label rows; then
 * its value by kind (a number / a share as a percent / a whole number with its range, step and unit;
 * a switch on / off; a choice's options; a point's X and Y, or none) and "· var" (on a row of its
 * own where the value row would be too wide); a safety switch's warning rows (shown while it is off:
 * the pl_setting extension, blockly-register.ts); and SETTING_NOTE_ROWS rows the editor fills with
 * the lint's "not used" words (hidden while empty). The IR is a plain variable of the tab:
 * `knife_hp_min = 0.5`. Only VALUE, X, Y and AT are saved: every label is a decoration. */
export function settingDef(f: SettingField): BlockDef {
  const rows = settingRows(f);
  const args: ArgDef[] = [];
  const endRow = (name: string): ArgDef => ({ type: "input_end_row", name });
  rows.words.forEach((w, i) => args.push({ type: "field_label", name: i === 0 ? "WORDS" : `WORDS${i}`, text: w }, endRow(`ROW_WORDS${i}`)));
  const unit = unitOf(f, f.default);
  const pct = (v: number) => Math.round(v * 100 * 1e6) / 1e6;
  // round 21 (live-blocks.md 12.5): the value's picker -- a share on the lever bar (an HP share fills
  // like an HP bar, the bag's the other way round), a number on a stepper over its range and step;
  // the field's min / max / precision are the registry's, as before
  const bar = /\bbag\b|weight|regen/i.test(`${f.words} ${f.var}`) ? "weight" : /\bHP\b|hp_|fly|potion/.test(`${f.words} ${f.var}`) ? "hp" : "level";
  const step = f.kind === "int" ? Math.max(1, f.step) : f.step;
  const number = (): ArgDef =>
    f.kind === "share"
      ? { type: PICK_NUM, name: "VALUE", value: pct(Number(f.default)), min: pct(f.lo), max: pct(f.hi), precision: pct(f.step), pick: { kind: "percent", lo: pct(f.lo), hi: pct(f.hi), step: pct(f.step), title: f.words, bar } }
      : { type: PICK_NUM, name: "VALUE", value: Number(f.default), min: f.lo, max: f.hi, precision: f.kind === "int" ? 1 : f.step, pick: { kind: "stepper", lo: f.lo, hi: f.hi, step, unit: f.unit, one: SETTINGS.singular[f.unit], title: f.words } };
  const xy: ArgDef[] = [
    { type: "field_label", name: "X_LABEL", text: "x" },
    { type: PICK_NUM, name: "X", value: 0, min: 0, max: SETTINGS.game_px[0] - 1, precision: 1, pick: { kind: "point", axis: "x", pair: "Y", title: f.words } },
    { type: "field_label", name: "Y_LABEL", text: "y" },
    { type: PICK_NUM, name: "Y", value: 0, min: 0, max: SETTINGS.game_px[1] - 1, precision: 1, pick: { kind: "point", axis: "y", pair: "X", title: f.words } },
  ];
  switch (f.kind) {
    case "switch":
      args.push({ type: "field_dropdown", name: "VALUE", options: [["on", "on"], ["off", "off"]] });
      break;
    case "choice":
      args.push({ type: "field_dropdown", name: "VALUE", options: opts(f.options) });
      break;
    case "point":
      args.push(...xy);
      break;
    case "point_or_none":
      args.push({ type: "field_dropdown", name: "AT", options: [["at", "at"], ["none", "none"]] }, endRow("ROW_AT"), ...xy);
      break;
    default:
      args.push(number(), ...(unit ? [{ type: "field_label", name: "UNIT", text: unit } as ArgDef] : []));
  }
  const name: ArgDef = { type: "field_label", name: "VAR", text: varText(f), class: "pl-setting-var" };
  if (rows.varOwnRow) args.push(endRow("ROW_VALUE"), name, endRow("ROW_VAR"));
  else args.push(name, endRow("ROW_VALUE"));
  rows.warn.forEach((w, i) => args.push({ type: "field_label", name: `WARN${i}`, text: w, class: "pl-setting-warn" }, endRow(`ROW_WARN${i}`)));
  for (let i = 0; i < SETTING_NOTE_ROWS; i++) args.push({ type: "field_label", name: `NOTE${i}`, text: "", class: "pl-setting-note" }, endRow(`ROW_NOTE${i}`));
  return {
    type: settingType(f),
    message0: args.map((_, i) => `%${i + 1}`).join(" "),
    args0: args,
    style: "mp_setup_blocks",
    inputsInline: true,
    tooltip: settingTooltip(f),
    extensions: ["pl_setting"],
  };
}
export const SETTING_DEFS: BlockDef[] = SETTING_BLOCKS.map(settingDef);

/** PURE (matpilot round 20 #2): the main hat's title on one or two rows as narrow as the setting
 * blocks: split after "when the run starts:", else wrapped ("when she arrives on" / "xmas_dun02"). */
export function titleLines(title: string): [string, string] {
  const width = SETTING_ROW_BUDGET - SETTING_GEOMETRY.side;
  const cut = title.indexOf(": ");
  const lines = cut > 0 ? [title.slice(0, cut + 1), title.slice(cut + 2)] : wrapUnits(title, width);
  return [lines[0] ?? "", lines.slice(1).join(" ")];
}
BLOCK_DEFS.push(...SETTING_DEFS);

export const DEF_BY_TYPE: Record<string, BlockDef> = Object.fromEntries(BLOCK_DEFS.map((d) => [d.type, d]));

/** The toolbox's Settings category (matpilot round 20 #5): ONE SUB-CATEGORY PER GROUP, named as its
 * tab and in the tabs' order (the flat list was 121 blocks, ~6,900 px, under a 1,062 px header that
 * was cut at 1440 and ran 877 px wide at 390), each with a short header -- the group's title and its
 * line, wrapped to the blocks' width -- then its setting blocks at our default. A block dragged into
 * a tab that already holds it is refused there ("on this tab twice"); one another tab of the node
 * holds is refused too ("on the tab ... already"). */
export function settingItems(): ToolboxCategory[] {
  const width = SETTING_ROW_BUDGET - SETTING_GEOMETRY.side; // the setting blocks' own row budget
  return SETTINGS.tabs.map((g) => {
    const grp = groupOf(g);
    const head: ToolboxItem[] = [...wrapUnits(grp?.title ?? g, width), ...wrapUnits(grp?.note ?? "", width)].filter(Boolean).map(lbl);
    const blocks: ToolboxItem[] = SETTING_BLOCKS.filter((x) => x.group === g).map((f) => ({ kind: "block", type: settingType(f), fields: settingFields(f, f.default) }));
    return cat(g, "mp_setup_category", [...head, ...blocks]);
  });
}

/** A sentence block's field: the catalogue parameter it holds and how (blocks.ts converts). */
export type SentenceField = { param: string; field: string; kind: "npc" | "map" | "items"; optional?: boolean };
/** The shop / Kafra / storage actions shown as sentences (2026-11-09 pm), in the toolbox's order. */
export const SENTENCE: Record<string, { type: string; fields: SentenceField[] }> = {
  set_save_point: { type: "pl_set_save_point", fields: [{ param: "npc", field: "NPC", kind: "npc" }] },
  kafra_teleport: { type: "pl_kafra_teleport", fields: [{ param: "npc", field: "NPC", kind: "npc" }, { param: "to", field: "TO", kind: "map" }] },
  kafra_store: {
    type: "pl_kafra_store",
    fields: [
      { param: "npc", field: "NPC", kind: "npc" },
      { param: "items", field: "ITEMS", kind: "items", optional: true },
      { param: "all_except", field: "KEEP", kind: "items", optional: true },
    ],
  },
  kafra_withdraw: { type: "pl_kafra_withdraw", fields: [{ param: "npc", field: "NPC", kind: "npc" }, { param: "items", field: "ITEMS", kind: "items" }] },
  rent_cart: { type: "pl_rent_cart", fields: [{ param: "npc", field: "NPC", kind: "npc" }] },
  buy: { type: "pl_buy", fields: [{ param: "npc", field: "NPC", kind: "npc" }, { param: "items", field: "ITEMS", kind: "items" }] },
  sell: { type: "pl_sell", fields: [{ param: "npc", field: "NPC", kind: "npc" }, { param: "keep", field: "KEEP", kind: "items" }] },
};
export const SENTENCE_BY_TYPE: Record<string, string> = Object.fromEntries(Object.entries(SENTENCE).map(([b, s]) => [s.type, b]));

/** Every field and input name a block type has (the converter's contract). `def`: a type built
 * at run time from the catalogue (the hunt block, hunt.ts). */
export function namesOf(type: string, def?: BlockDef): { fields: Set<string>; saved: Set<string>; inputs: Set<string> } {
  const d = def ?? DEF_BY_TYPE[type];
  const fields = new Set<string>();
  const saved = new Set<string>();
  const inputs = new Set<string>();
  if (!d) return { fields, saved, inputs };
  for (const args of [d.args0, d.args1, d.args2, d.args3, d.args4, d.args5, d.args6, d.args7, d.args8]) {
    for (const a of args ?? []) {
      if (a.type === "input_value" || a.type === "input_statement") inputs.add(a.name);
      else if (a.type !== "input_dummy" && a.type !== "field_image") {
        fields.add(a.name);
        if (a.type !== "field_label") saved.add(a.name);
      }
    }
  }
  if (type === "pl_logic") for (let i = 0; i < 100; i++) inputs.add(`T${i}`);
  return { fields, saved, inputs };
}

// --- the toolbox ----------------------------------------------------------------------------------
// MatPilot's order (Batt 2026-11-09, flows-studio.md section 2): Search, Movement, Actions, Control,
// Conditions, Sensors, Operators, Variables, Functions, then Advanced (folding open, as MakeCode's)
// with every other catalogue block and the map-event blocks. Each category is styled as MatPilot's.
export type CatBlock = { concept: string; timeout_s: number; badge?: string; kind?: string };
export type ToolboxItem =
  | { kind: "block"; type: string; fields?: Record<string, unknown>; extraState?: unknown; inputs?: unknown }
  | { kind: "label"; text: string };
export type ToolboxCategory = { kind: "category"; name: string; categorystyle: string; contents: (ToolboxItem | ToolboxCategory)[] };
export type Toolbox = {
  kind: "categoryToolbox";
  contents: ({ kind: "search"; name: string; categorystyle: string } | ToolboxCategory)[];
};
/** The model blocks' first choice (models.ts firstDetector) and the not-adopted notes. */
export type SensorDefaults = { model: string; label: string; notes: string[] };

const PALETTE_TYPES: Record<string, string> = {
  walk_to: "pl_walk_to",
  talk_npc: "pl_talk_npc",
  choose_menu: "pl_choose_menu",
  open_window: "pl_open_window",
  use_item: "pl_use_item",
};
const ACTIONS = ["talk_npc", "choose_menu", "use_item", "open_window"];
/** Catalogue blocks with a block of their own (not repeated under "More skills"). */
const OWN_BLOCK: Record<string, string> = { press_key: "pl_press_key", dungeon_hunt: "pl_dungeon_hunt", login: "pl_login", choose_character: "pl_choose_character", assert_save_point: "pl_save_point" };
/** Live blocks stage 4a (live-blocks.md 3.4): the trained data and a monster's recipe steps,
 * offered only where they play -- use_model in a map node's main, the primitives in its
 * `monsters` tab -- never under "More skills". */
export const RECIPE_TAB = "monsters";
export const RECIPE_STEPS = ["strike", "wait_steal", "wait_kill", "loot"] as const;
const RECIPE_ONLY = new Set<string>([...RECIPE_STEPS, "use_model", "use_skill"]);
/** The model a node's recipes name (its use_model's models.yaml entry): its monsters the runner
 * strikes and their mob ids (the KB names them at run time). */
export type Monsters = { model: string; strikes: string[]; mobs: Record<string, number[]> };

function rest(c: CatBlock) {
  return { rest: { concept: c.concept, timeout_s: c.timeout_s, on_fail: "stop", outcome_to: null, note: null } };
}

const exprBlock = (t: string) => ({ block: { type: "pl_expr", fields: { TEXT: t } } });
const lbl = (text: string): ToolboxItem => ({ kind: "label", text });
const cat = (name: string, categorystyle: string, contents: (ToolboxItem | ToolboxCategory)[]): ToolboxCategory => ({
  kind: "category",
  name,
  categorystyle,
  contents,
});

/** A category of the toolbox by name, nested ones too (Advanced holds some). */
export function categoryOf(tb: Toolbox | ToolboxCategory, name: string): ToolboxCategory | undefined {
  for (const c of tb.contents) {
    if (c.kind !== "category") continue;
    if (c.name === name) return c;
    const inner = categoryOf(c, name);
    if (inner) return inner;
  }
  return undefined;
}

/** The first block of a type a category offers (its own items, not nested categories). */
export function blockOf(c: ToolboxCategory | undefined, type: string): Extract<ToolboxItem, { kind: "block" }> | undefined {
  for (const i of c?.contents ?? []) if (i.kind === "block" && i.type === type) return i;
  return undefined;
}

/** Every block a toolbox offers, with its category's name (the search and the tests). */
export function toolboxBlocks(tb: Toolbox | ToolboxCategory): { category: string; item: Extract<ToolboxItem, { kind: "block" }> }[] {
  const out: { category: string; item: Extract<ToolboxItem, { kind: "block" }> }[] = [];
  for (const c of tb.contents) {
    if (c.kind !== "category") continue;
    for (const i of c.contents) if (i.kind === "block") out.push({ category: c.name, item: i });
    out.push(...toolboxBlocks(c));
  }
  return out;
}

/** The toolbox for a scope. `huntFields`: the hunt block's dropdown defaults when its type is
 * registered (hunt.ts), else the hunt block is offered as a generic block with its parameters by
 * name. `huntOmit`: its optional parameters' defaults (hunt.ts `omitted`), left out of the IR at that
 * value. `sensors`: the model blocks' first model and class, and the not-adopted models' notes. */
/** Which tab the toolbox is for (the project model): the node's kind and whether it is its main;
 * `tab` its name (stage 4a: "monsters" offers the recipes), `model` the node's use_model. */
export type ToolboxScope = { node: "login" | "character" | "map" | "global"; main: boolean; tab?: string; model?: string | null };

export function toolbox(
  blocks: Record<string, CatBlock>,
  scope: ToolboxScope,
  huntFields: Record<string, string> | null = null,
  huntOmit: Record<string, string> = {},
  sensors: SensorDefaults = { model: "v1", label: "monster", notes: [] },
  monsters: Monsters | null = null,
): Toolbox {
  const palette = (name: string): ToolboxItem[] =>
    blocks[name] ? [{ kind: "block", type: PALETTE_TYPES[name], extraState: rest(blocks[name]) }] : [];
  const hunt: ToolboxItem[] =
    blocks.hunt && huntFields
      ? [{ kind: "block", type: "pl_hunt", fields: huntFields, extraState: Object.keys(huntOmit).length ? { ...rest(blocks.hunt), omit: huntOmit } : rest(blocks.hunt) }]
      : [];
  const onMap = scope.node === "map";
  const movement: ToolboxItem[] = onMap ? [...palette("walk_to"), ...hunt] : [];
  if (onMap && blocks.dungeon_hunt) {
    movement.push(lbl("The Rogue's runner (a map with a runner: xmas_dun02):"), { kind: "block", type: "pl_dungeon_hunt", extraState: rest(blocks.dungeon_hunt) });
  }
  if (onMap && blocks.assert_save_point) movement.push({ kind: "block", type: "pl_save_point", fields: { MAP: "geffen", X: 119, Y: 40 }, extraState: rest(blocks.assert_save_point) });
  if (onMap && scope.main && blocks.use_model) {
    movement.push(lbl("The trained data (before the runner: its monsters are the recipes' names):"), { kind: "block", type: "pl_action", fields: { BLOCK: "use_model", ARGS: `model=${JSON.stringify(monsters?.model ?? "xmas02")}` }, extraState: rest(blocks.use_model) });
  }
  // stage 4a: the monsters tab -- one function per monster of the model, a recipe of the steps the
  // runner plays with its own code (knife_on / knife_back: the hunt core's Knife functions)
  const recipes: ToolboxItem[] = [];
  if (scope.tab === RECIPE_TAB && (onMap || scope.node === "global")) {
    if (monsters) {
      recipes.push(lbl(`The monsters of ${monsters.model}: one function each (the runner asks it when it locks that monster):`));
      for (const sp of monsters.strikes) recipes.push({ kind: "block", type: "pl_def", fields: { NAME: `attack_${sp}`, PARAMS: "t, priority=1" } });
      recipes.push(lbl("A monster as a value:"));
      for (const sp of monsters.strikes) recipes.push(lbl(sp), { kind: "block", type: "pl_expr", fields: { TEXT: `mob(${monsters.mobs[sp]?.[0] ?? 1})` } });
    } else {
      recipes.push(lbl("use_model(...) in the main names the monsters (a trained model)"));
    }
    recipes.push(lbl("A recipe's steps, in this order (no Knife on a monster: leave out knife_on, wait_steal, knife_back):"));
    recipes.push({ kind: "block", type: "pl_call", fields: { PROC: "knife_on", ARGS: "" } });
    for (const s of RECIPE_STEPS) {
      if (s === "wait_kill") recipes.push({ kind: "block", type: "pl_call", fields: { PROC: "knife_back", ARGS: "" } });
      if (blocks[s]) recipes.push({ kind: "block", type: "pl_action", fields: { BLOCK: s, ARGS: "target=t" }, extraState: rest(blocks[s]) });
    }
    if (blocks.use_skill) recipes.push(lbl("A skill before the strike (checked, not played live yet: 4b):"), { kind: "block", type: "pl_action", fields: { BLOCK: "use_skill", ARGS: 'key="F6"' }, extraState: rest(blocks.use_skill) });
  }
  if (onMap) {
    movement.push(
      lbl("Leave this map (a map's main ends with one):"),
      { kind: "block", type: "pl_exit_walk" },
      { kind: "block", type: "pl_exit_npc" },
      { kind: "block", type: "pl_exit_item_fn", fields: { FN: "butterfly_wing" } },
      { kind: "block", type: "pl_exit_item", fields: { ITEM: "WING" } },
    );
  }
  const pressKey: ToolboxItem[] = blocks.press_key ? [{ kind: "block", type: "pl_press_key", fields: { KEY: "F1" }, extraState: rest(blocks.press_key) }] : [];
  const session: ToolboxItem[] = [];
  if (scope.node === "login" && blocks.login) session.push(lbl("Log in (a credential by name, never a password):"), { kind: "block", type: "pl_login", fields: { SERVER: "lab-rathena", CREDENTIAL: "lab_gm" }, extraState: rest(blocks.login) });
  if (scope.node === "character" && blocks.choose_character) session.push(lbl("Choose the character:"), { kind: "block", type: "pl_choose_character", fields: { CHAR: "" }, extraState: rest(blocks.choose_character) });
  const actions: ToolboxItem[] = [...session, ...pressKey, ...(scope.node === "global" || onMap ? ACTIONS.flatMap(palette) : [])];
  const sentences = Object.entries(SENTENCE).filter(([name]) => blocks[name]);
  if (sentences.length) actions.push(lbl("At a shop or a Kafra:"));
  for (const [name, sb] of sentences) actions.push({ kind: "block", type: sb.type, extraState: rest(blocks[name]) });
  const control: ToolboxItem[] = [
    { kind: "block", type: "pl_wait", fields: { SECONDS: 1 } },
    { kind: "block", type: "pl_wait_until", inputs: { COND: exprBlock("hp_percent() > 90") } },
    { kind: "block", type: "pl_repeat", inputs: { TIMES: exprBlock("3") } },
    { kind: "block", type: "pl_while", inputs: { COND: exprBlock("weight_percent() < 50") } },
    { kind: "block", type: "pl_stop" },
    { kind: "block", type: "pl_break" },
    { kind: "block", type: "pl_continue" },
    lbl(scope.node === "global" ? "An EVENT, a function that runs by itself when … (every node; a map's of the same name replaces it there):" : "An EVENT, a function that runs by itself when … (this node; it replaces Global's of the same name here):"),
    { kind: "block" as const, type: "pl_event", fields: { SCOPE: scope.node === "global" ? "global" : "map", NAME: "my_event" },
      inputs: { WHEN: exprBlock("hp_percent() < 30") } },
  ];
  const conditions: ToolboxItem[] = [
    { kind: "block", type: "pl_if", inputs: { COND: exprBlock("hp_percent() < 50") } },
    { kind: "block", type: "pl_compare", inputs: { A: exprBlock("hp_percent()"), B: exprBlock("50") } },
    { kind: "block", type: "pl_logic", fields: { OP: "and" } },
    { kind: "block", type: "pl_not" },
    { kind: "block", type: "pl_expr", fields: { TEXT: "OK" } },
  ];
  if (blocks.choose_menu) {
    conditions.push({ kind: "block", type: "pl_do", fields: { BLOCK: "choose_menu", ARGS: 'option=option("o_key")' },
      extraState: rest(blocks.choose_menu) });
  }
  const model = { MODEL: sensors.model, CLASS: sensors.label };
  const sensorItems: ToolboxItem[] = [
    { kind: "block", type: "pl_detect_sees", fields: model },
    { kind: "block", type: "pl_detect_count", fields: model },
    { kind: "block", type: "pl_wait_until", inputs: { COND: { block: { type: "pl_detect_sees", fields: model } } } },
    ...sensors.notes.map(lbl),
    lbl("More sensors, written as an expression:"),
    { kind: "block", type: "pl_expr", fields: { TEXT: "hp_percent()" } },
    { kind: "block", type: "pl_expr", fields: { TEXT: "weight_percent()" } },
    { kind: "block", type: "pl_expr", fields: { TEXT: "is_dead()" } },
    { kind: "block", type: "pl_expr", fields: { TEXT: 'hotbar_count(key="F6")' } },
  ];
  const operators: ToolboxItem[] = [
    { kind: "block", type: "pl_expr", fields: { TEXT: "0" } },
    { kind: "block", type: "pl_expr", fields: { TEXT: "1 + 2" } },
    { kind: "block", type: "pl_expr", fields: { TEXT: "hp_percent() < 50" } },
  ];
  const variables: ToolboxItem[] = [
    lbl("A function's input, or a variable, by its name (inside a function: its inputs):"),
    { kind: "block", type: "pl_expr", fields: { TEXT: "key" } },
    lbl(scope.node === "global" ? "A variable every node shares:" : "A variable of this tab:"),
    { kind: "block", type: "pl_vardecl", fields: { NAME: "x" }, inputs: { VALUE: exprBlock("0") } },
    { kind: "block", type: "pl_set", inputs: { VALUE: exprBlock("0") } },
  ];
  const functions: ToolboxItem[] = [
    lbl("A function: write it once, call it from any tab (Global's: from every node):"),
    { kind: "block", type: "pl_def", fields: { NAME: "my_function", PARAMS: "" } },
    { kind: "block", type: "pl_call", fields: { PROC: "my_function", ARGS: "" } },
    { kind: "block", type: "pl_return" },
    { kind: "block", type: "pl_callv", fields: { PROC: "my_function", ARGS: "" } },
    ...pressKey,
    ...(blocks.press_key ? [{ kind: "block" as const, type: "pl_press_key_v", inputs: { KEY: exprBlock("key") }, extraState: rest(blocks.press_key) }] : []),
  ];
  const others: ToolboxItem[] = Object.keys(blocks)
    .filter((n) => !(n in PALETTE_TYPES) && !(n in SENTENCE) && !(n === "hunt" && huntFields) && !(n in OWN_BLOCK) && !RECIPE_ONLY.has(n))
    .sort()
    .map((n) => ({ kind: "block" as const, type: "pl_action", fields: { BLOCK: n, ARGS: "" }, extraState: rest(blocks[n]) }));
  const advanced: ToolboxCategory[] = [cat("More skills", "mp_other_category", others)];
  // (the project model: a map replaces Global's event by writing its own of the same name; no extend /
  // disable blocks any more)
  return {
    kind: "categoryToolbox",
    contents: [
      { kind: "search", name: "Search", categorystyle: "mp_setup_category" },
      cat("Movement", "mp_movement_category", movement),
      ...(recipes.length ? [cat("Monsters", "mp_sensor_category", recipes)] : []),
      cat("Actions", "mp_output_category", actions),
      cat("Control", "loop_category", control),
      cat("Conditions", "loop_category", conditions),
      cat("Sensors", "mp_sensor_category", sensorItems),
      cat("Operators", "math_category", operators),
      cat("Variables", "variable_category", variables),
      ...(onMap || scope.node === "global" ? [cat("Settings", "mp_setup_category", settingItems())] : []),
      cat("Functions", "mp_function_category", functions),
      cat("Advanced", "mp_setup_category", advanced),
    ],
  };
}
