// The block editor's block TYPES (Blockly's JSON block definitions) and its toolbox. Pure data:
// the converter (blocks.ts) writes and reads exactly these field and input names, and
// blocks.test.ts checks that against this file without loading Blockly. The component
// (components/flows/BlockEditor.tsx) registers them with Blockly in the browser.
//
// Field kinds that SAVE their value: field_input (text), field_number, field_dropdown,
// field_label_serializable. A plain field_label is NOT saved: BADGE (the skill's verification badge)
// and RUN (the last simulate run) are decorations the component fills in after loading; nor is a
// field_image (the model blocks' eye).
//
// Since 2026-11-09 (the studio, docs/planning/flows-studio.md) the blocks carry MatPilot's words,
// STYLES and categories (theme.ts): only words, colours and the toolbox changed; every type, field,
// input and the IR they convert to stayed. Two blocks were added: the TRAINED MODELS as sensors
// (pl_detect_sees / pl_detect_count, models.ts; ADR-0020 Amendment B).

export type FieldKind = "field_input" | "field_number" | "field_dropdown" | "field_label_serializable" | "field_label";
import { BLOCK_STYLE } from "./theme.ts";

export type ArgDef =
  | { type: FieldKind; name: string; text?: string; value?: number; options?: [string, string][]; class?: string }
  | { type: "input_value" | "input_statement"; name: string; check?: string | string[] }
  | { type: "input_dummy" }
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
const num = (name: string, value = 0): ArgDef => ({ type: "field_number", name, value });
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

export const BLOCK_DEFS: BlockDef[] = [
  // --- MW2's palette: one block per skill (section 3) ---
  stmt({
    type: "pl_walk_to",
    message0: "walk to %1 x %2 y %3 %4 %5",
    args0: [text("MAP"), num("X"), num("Y"), badge, run],
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
    args0: [text("WINDOW", "basic_info"), badge, run],
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
    args0: [text("NPC"), text("TO"), badge, run],
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
    args0: [num("SECONDS", 1), run],
    tooltip: "wait: the IR's core wait statement (wait_until(False, timeout_s=N)); no input",
  }),
  // --- every other catalogue block, lossless: its parameters by name ---
  stmt({
    type: "pl_action",
    message0: "%1 ( %2 ) %3 %4",
    args0: [label("BLOCK"), text("ARGS"), badge, run],
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
    args0: [{ type: "input_value", name: "COND" }, num("TIMEOUT", 10), run],
  }),
  stmt({
    type: "pl_set",
    message0: "set %1 to %2",
    args0: [text("VAR", "x"), { type: "input_value", name: "VALUE" }],
  }),
  stmt({ type: "pl_call", message0: "call %1", args0: [text("PROC")] }),
  stmt({ type: "pl_stop", message0: "stop %1 %2", args0: [text("REASON", "done"), run] }),
  stmt({ type: "pl_break", message0: "break" }),
  stmt({ type: "pl_continue", message0: "continue" }),
  // --- exits (13.1): they leave the map block ---
  stmt({
    type: "pl_exit_walk",
    message0: "walk exit at %1 x %2 y %3 → %4 . %5 %6",
    args0: [text("MAP"), num("X"), num("Y"), text("TO_BLOCK"), text("TO_ENTRY"), run],
    tooltip: "walk_exit: walk onto an L3 warp of this map; arrive at <block>.<entry>",
  }),
  stmt({
    type: "pl_exit_npc",
    message0: "npc warp: talk to %1 choose %2 → %3 . %4 %5",
    args0: [text("NPC"), text("OPTIONS"), text("TO_BLOCK"), text("TO_ENTRY"), run],
    tooltip: "npc_warp: talk to the NPC, choose each option key (comma separated) in order",
  }),
  stmt({
    type: "pl_exit_item",
    message0: "item warp: use %1 → %2 . %3 %4",
    args0: [text("ITEM"), text("TO_BLOCK"), text("TO_ENTRY"), run],
    tooltip: "item_warp: e.g. a Butterfly Wing, to the SAVE POINT (never 'the previous map')",
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
  value({ type: "pl_expr", message0: "%1", args0: [text("TEXT", "hp_percent() < 50")],
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
    args0: [label("BLOCK"), text("ARGS"), badge],
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
    message0: "%1",
    args0: [{ type: "field_label", name: "TITLE", text: "when the program starts" }],
    message1: "%1",
    args1: [{ type: "input_statement", name: "DO" }],
    style: st("pl_main"),
    mutator: STATE,
    tooltip: "The program's start (a map block's: when the flow arrives on its map). Every path ends in an exit or a stop",
  },
  {
    type: "pl_event",
    message0: "%1 when %2",
    args0: [label("SCOPE"), { type: "input_value", name: "WHEN" }],
    message1: "event %1 class %2 rank %3 mode %4 then %5",
    args1: [text("NAME", "my_event"), { type: "field_dropdown", name: "PRIORITY", options: opts(PRIORITY_OPTIONS) },
      text("RANK"), // IR 2 (ADR-0020 #13): 1..99 inside the class; empty = 13.6.3's table order
      { type: "field_dropdown", name: "MODE", options: opts(MODE_OPTIONS) },
      { type: "field_dropdown", name: "THEN", options: opts(THEN_OPTIONS) }],
    message2: "until %1 rearm %2",
    args2: [{ type: "input_value", name: "UNTIL" }, { type: "input_value", name: "REARM" }],
    message3: "do %1",
    args3: [{ type: "input_statement", name: "DO" }],
    style: st("pl_event"),
    mutator: STATE,
    tooltip:
      "when <condition> do: until (repeat until it holds) and rearm (one-shot) are exclusive; rank orders the events of one class (empty: 13.6.3's table order)",
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

export const DEF_BY_TYPE: Record<string, BlockDef> = Object.fromEntries(BLOCK_DEFS.map((d) => [d.type, d]));

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
  for (const args of [d.args0, d.args1, d.args2, d.args3, d.args4, d.args5]) {
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
export function toolbox(
  blocks: Record<string, CatBlock>,
  scope: "block" | "global" | "main",
  huntFields: Record<string, string> | null = null,
  huntOmit: Record<string, string> = {},
  sensors: SensorDefaults = { model: "v1", label: "monster", notes: [] },
): Toolbox {
  const palette = (name: string): ToolboxItem[] =>
    blocks[name] ? [{ kind: "block", type: PALETTE_TYPES[name], extraState: rest(blocks[name]) }] : [];
  const hunt: ToolboxItem[] =
    blocks.hunt && huntFields
      ? [{ kind: "block", type: "pl_hunt", fields: huntFields, extraState: Object.keys(huntOmit).length ? { ...rest(blocks.hunt), omit: huntOmit } : rest(blocks.hunt) }]
      : [];
  const movement: ToolboxItem[] = [...palette("walk_to"), ...hunt];
  if (scope === "block") {
    movement.push(
      lbl("Leave this map (a map block ends with one):"),
      { kind: "block", type: "pl_exit_walk" },
      { kind: "block", type: "pl_exit_npc" },
      { kind: "block", type: "pl_exit_item", fields: { ITEM: "WING" } },
    );
  }
  const actions: ToolboxItem[] = ACTIONS.flatMap(palette);
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
    lbl(scope === "global" ? "When something happens (every map):" : "When something happens:"),
    { kind: "block", type: "pl_event", fields: { SCOPE: scope === "global" ? "global" : "map", NAME: "my_event" },
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
  ];
  const operators: ToolboxItem[] = [
    { kind: "block", type: "pl_expr", fields: { TEXT: "0" } },
    { kind: "block", type: "pl_expr", fields: { TEXT: "1 + 2" } },
    { kind: "block", type: "pl_expr", fields: { TEXT: "hp_percent() < 50" } },
  ];
  const variables: ToolboxItem[] = [{ kind: "block", type: "pl_set", inputs: { VALUE: exprBlock("0") } }];
  const functions: ToolboxItem[] = [{ kind: "block", type: "pl_call" }];
  const others: ToolboxItem[] = Object.keys(blocks)
    .filter((n) => !(n in PALETTE_TYPES) && !(n in SENTENCE) && !(n === "hunt" && huntFields))
    .sort()
    .map((n) => ({ kind: "block" as const, type: "pl_action", fields: { BLOCK: n, ARGS: "" }, extraState: rest(blocks[n]) }));
  const advanced: ToolboxCategory[] = [cat("More skills", "mp_other_category", others)];
  if (scope === "block") {
    advanced.push(cat("Map events", "loop_category", [{ kind: "block", type: "pl_extend" }, { kind: "block", type: "pl_disable" }]));
  }
  return {
    kind: "categoryToolbox",
    contents: [
      { kind: "search", name: "Search", categorystyle: "mp_setup_category" },
      cat("Movement", "mp_movement_category", movement),
      cat("Actions", "mp_output_category", actions),
      cat("Control", "loop_category", control),
      cat("Conditions", "loop_category", conditions),
      cat("Sensors", "mp_sensor_category", sensorItems),
      cat("Operators", "math_category", operators),
      cat("Variables", "variable_category", variables),
      cat("Functions", "mp_function_category", functions),
      cat("Advanced", "mp_setup_category", advanced),
    ],
  };
}
