// The block editor's block TYPES (Blockly's JSON block definitions) and its toolbox. Pure data:
// the converter (blocks.ts) writes and reads exactly these field and input names, and
// blocks.test.ts checks that against this file without loading Blockly. The component
// (components/flows/BlockEditor.tsx) registers them with Blockly in the browser.
//
// Field kinds that SAVE their value: field_input (text), field_number, field_dropdown,
// field_label_serializable. A plain field_label is NOT saved: BADGE (the skill's verification badge)
// and RUN (the last simulate run) are decorations the component fills in after loading.

export type FieldKind = "field_input" | "field_number" | "field_dropdown" | "field_label_serializable" | "field_label";
export type ArgDef =
  | { type: FieldKind; name: string; text?: string; value?: number; options?: [string, string][]; class?: string }
  | { type: "input_value" | "input_statement"; name: string; check?: string | string[] }
  | { type: "input_dummy" };
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
  colour: string;
  tooltip?: string;
  inputsInline?: boolean;
  mutator?: string;
};

export const COLOURS = {
  action: "#4c97ff",
  generic: "#5b80a5",
  control: "#ffab19",
  exit: "#59c059",
  event: "#ff6680",
  hat: "#9966ff",
  expr: "#40bf9f",
  raw: "#8c8c8c",
};

const badge: ArgDef = { type: "field_label", name: "BADGE", text: "", class: "pl-badge" };
const run: ArgDef = { type: "field_label", name: "RUN", text: "", class: "pl-run" };
const label = (name: string): ArgDef => ({ type: "field_label_serializable", name, text: "" });
const text = (name: string, value = ""): ArgDef => ({ type: "field_input", name, text: value });
const num = (name: string, value = 0): ArgDef => ({ type: "field_number", name, value });
const opts = (vals: readonly string[]): [string, string][] => vals.map((v) => [v, v]);
// Blockly only lets a MUTATOR add saveExtraState / loadExtraState (a plain extension that does is
// refused), so the lossless state rides on mutators without a mutator UI.
const STATE = "pl_state";

const stmt = (def: Omit<BlockDef, "previousStatement" | "nextStatement">): BlockDef => ({
  ...def,
  previousStatement: null,
  nextStatement: null,
  mutator: STATE,
});
const value = (def: Omit<BlockDef, "output">): BlockDef => ({ ...def, output: null, mutator: def.mutator ?? STATE });

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
    colour: COLOURS.action,
    inputsInline: true,
    tooltip: "walk_to(cell): walk to a cell of this map",
  }),
  stmt({
    type: "pl_talk_npc",
    message0: "talk to npc %1 %2 %3",
    args0: [text("NPC"), badge, run],
    colour: COLOURS.action,
    tooltip: "talk_npc(npc): walk up to the NPC and open its dialog (an L3 key)",
  }),
  stmt({
    type: "pl_choose_menu",
    message0: "choose menu option %1 %2 %3",
    args0: [text("OPTION"), badge, run],
    colour: COLOURS.action,
    tooltip: "choose_menu(option): an option KEY, matched by its text on screen, never by index",
  }),
  stmt({
    type: "pl_open_window",
    message0: "open window %1 %2 %3",
    args0: [text("WINDOW", "basic_info"), badge, run],
    colour: COLOURS.action,
    tooltip: "open_window(window): an L2 window name (ADR-0011 anchor map)",
  }),
  stmt({
    type: "pl_use_item",
    message0: "use item %1 %2 %3",
    args0: [text("ITEM"), badge, run],
    colour: COLOURS.action,
    tooltip: "use_item(item): an item id, or a variable naming one (e.g. POTION)",
  }),
  stmt({
    type: "pl_wait",
    message0: "wait %1 seconds %2",
    args0: [num("SECONDS", 1), run],
    colour: COLOURS.control,
    tooltip: "wait: the IR's core wait statement (wait_until(False, timeout_s=N)); no input",
  }),
  // --- every other catalogue block, lossless: its parameters by name ---
  stmt({
    type: "pl_action",
    message0: "%1 ( %2 ) %3 %4",
    args0: [label("BLOCK"), text("ARGS"), badge, run],
    colour: COLOURS.generic,
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
    colour: COLOURS.control,
  }),
  stmt({
    type: "pl_while",
    message0: "while %1 %2",
    args0: [{ type: "input_value", name: "COND" }, run],
    message1: "do %1",
    args1: [{ type: "input_statement", name: "BODY" }],
    colour: COLOURS.control,
  }),
  stmt({
    type: "pl_repeat",
    message0: "repeat %1 times %2",
    args0: [{ type: "input_value", name: "TIMES" }, run],
    message1: "do %1",
    args1: [{ type: "input_statement", name: "BODY" }],
    colour: COLOURS.control,
    tooltip: "repeat N (the Python view prints for _ in range(N))",
  }),
  stmt({
    type: "pl_wait_until",
    message0: "wait until %1 at most %2 s %3",
    args0: [{ type: "input_value", name: "COND" }, num("TIMEOUT", 10), run],
    colour: COLOURS.control,
  }),
  stmt({
    type: "pl_set",
    message0: "set %1 to %2",
    args0: [text("VAR", "x"), { type: "input_value", name: "VALUE" }],
    colour: COLOURS.control,
  }),
  stmt({ type: "pl_call", message0: "call %1", args0: [text("PROC")], colour: COLOURS.control }),
  stmt({ type: "pl_stop", message0: "stop %1 %2", args0: [text("REASON", "done"), run], colour: COLOURS.control }),
  stmt({ type: "pl_break", message0: "break", colour: COLOURS.control }),
  stmt({ type: "pl_continue", message0: "continue", colour: COLOURS.control }),
  // --- exits (13.1): they leave the map block ---
  stmt({
    type: "pl_exit_walk",
    message0: "walk exit at %1 x %2 y %3 → %4 . %5 %6",
    args0: [text("MAP"), num("X"), num("Y"), text("TO_BLOCK"), text("TO_ENTRY"), run],
    colour: COLOURS.exit,
    tooltip: "walk_exit: walk onto an L3 warp of this map; arrive at <block>.<entry>",
  }),
  stmt({
    type: "pl_exit_npc",
    message0: "npc warp: talk to %1 choose %2 → %3 . %4 %5",
    args0: [text("NPC"), text("OPTIONS"), text("TO_BLOCK"), text("TO_ENTRY"), run],
    colour: COLOURS.exit,
    tooltip: "npc_warp: talk to the NPC, choose each option key (comma separated) in order",
  }),
  stmt({
    type: "pl_exit_item",
    message0: "item warp: use %1 → %2 . %3 %4",
    args0: [text("ITEM"), text("TO_BLOCK"), text("TO_ENTRY"), run],
    colour: COLOURS.exit,
    tooltip: "item_warp: e.g. a Butterfly Wing, to the SAVE POINT (never 'the previous map')",
  }),
  stmt({
    type: "pl_raw",
    message0: "%1 %2",
    args0: [label("TEXT"), run],
    colour: COLOURS.raw,
    tooltip: "Not editable as blocks in MW2 (kept exactly): edit it in the JSON view",
  }),
  // --- expressions ---
  value({
    type: "pl_raw_expr",
    message0: "%1",
    args0: [label("TEXT")],
    colour: COLOURS.raw,
    tooltip: "Not editable as blocks in MW2 (kept exactly): edit it in the JSON view",
  }),
  value({ type: "pl_expr", message0: "%1", args0: [text("TEXT", "hp_percent() < 50")], colour: COLOURS.expr,
    tooltip: "An expression in the Python view's form, e.g. hp_percent() < 50, sees(mob=mob(9109), within=15)" }),
  value({
    type: "pl_compare",
    message0: "%1 %2 %3",
    args0: [{ type: "input_value", name: "A" }, { type: "field_dropdown", name: "OP", options: opts(CMP_OPTIONS) },
      { type: "input_value", name: "B" }],
    inputsInline: true,
    colour: COLOURS.expr,
  }),
  value({ type: "pl_not", message0: "not %1", args0: [{ type: "input_value", name: "X" }], colour: COLOURS.expr }),
  value({
    type: "pl_logic",
    message0: "%1",
    args0: [{ type: "field_dropdown", name: "OP", options: opts(["and", "or"]) }],
    colour: COLOURS.expr,
    mutator: "pl_logic",
    tooltip: "and / or over its terms (T0, T1, ...)",
  }),
  value({
    type: "pl_do",
    message0: "%1 ( %2 ) %3",
    args0: [label("BLOCK"), text("ARGS"), badge],
    inputsInline: true,
    colour: COLOURS.generic,
    tooltip: "An action used as a value: its outcome (OK, FAILED, ...)",
  }),
  // --- hats ---
  {
    type: "pl_main",
    message0: "%1",
    args0: [{ type: "field_label", name: "TITLE", text: "main flow" }],
    message1: "%1",
    args1: [{ type: "input_statement", name: "DO" }],
    colour: COLOURS.hat,
    mutator: STATE,
    tooltip: "The map block's main flow: every path ends in an exit or a stop",
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
    colour: COLOURS.event,
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
    colour: COLOURS.event,
    mutator: STATE,
    tooltip: "EXTEND: the global event runs with these steps too (after its body if safety-critical)",
  },
  {
    type: "pl_disable",
    message0: "disable event %1 on this map",
    args0: [text("KEY")],
    colour: COLOURS.event,
    mutator: STATE,
    tooltip: "DISABLE: the global event does not run here (never a safety-critical one)",
  },
];

export const DEF_BY_TYPE: Record<string, BlockDef> = Object.fromEntries(BLOCK_DEFS.map((d) => [d.type, d]));

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
      else if (a.type !== "input_dummy") {
        fields.add(a.name);
        if (a.type !== "field_label") saved.add(a.name);
      }
    }
  }
  if (type === "pl_logic") for (let i = 0; i < 100; i++) inputs.add(`T${i}`);
  return { fields, saved, inputs };
}

// --- the toolbox ----------------------------------------------------------------------------------
export type CatBlock = { concept: string; timeout_s: number; badge?: string; kind?: string };
export type ToolboxItem = { kind: "block"; type: string; fields?: Record<string, unknown>; extraState?: unknown; inputs?: unknown };
export type Toolbox = {
  kind: "categoryToolbox";
  contents: { kind: "category"; name: string; colour: string; contents: ToolboxItem[] }[];
};

const PALETTE_TYPES: Record<string, string> = {
  walk_to: "pl_walk_to",
  talk_npc: "pl_talk_npc",
  choose_menu: "pl_choose_menu",
  open_window: "pl_open_window",
  use_item: "pl_use_item",
};

function rest(c: CatBlock) {
  return { rest: { concept: c.concept, timeout_s: c.timeout_s, on_fail: "stop", outcome_to: null, note: null } };
}

const exprBlock = (t: string) => ({ block: { type: "pl_expr", fields: { TEXT: t } } });

/** The toolbox for a scope: the palette, the other catalogue blocks, control, exits, events.
 * `huntFields`: the hunt block's dropdown defaults when its type is registered (hunt.ts), else the
 * hunt block is offered as a generic block with its parameters by name. `huntOmit`: its optional
 * parameters' defaults (hunt.ts `omitted`), left out of the IR at that value. */
export function toolbox(
  blocks: Record<string, CatBlock>,
  scope: "block" | "global" | "main",
  huntFields: Record<string, string> | null = null,
  huntOmit: Record<string, string> = {},
): Toolbox {
  const palette: ToolboxItem[] = [];
  for (const [name, type] of Object.entries(PALETTE_TYPES)) {
    if (blocks[name]) palette.push({ kind: "block", type, extraState: rest(blocks[name]) });
  }
  palette.push({ kind: "block", type: "pl_wait", fields: { SECONDS: 1 } });
  const others: ToolboxItem[] = Object.keys(blocks)
    .filter((n) => !(n in PALETTE_TYPES))
    .sort()
    .map((n) =>
      n === "hunt" && huntFields
        ? {
            kind: "block" as const,
            type: "pl_hunt",
            fields: huntFields,
            extraState: Object.keys(huntOmit).length ? { ...rest(blocks[n]), omit: huntOmit } : rest(blocks[n]),
          }
        : { kind: "block" as const, type: "pl_action", fields: { BLOCK: n, ARGS: "" }, extraState: rest(blocks[n]) },
    );
  const control: ToolboxItem[] = [
    { kind: "block", type: "pl_if", inputs: { COND: exprBlock("hp_percent() < 50") } },
    { kind: "block", type: "pl_repeat", inputs: { TIMES: exprBlock("3") } },
    { kind: "block", type: "pl_while", inputs: { COND: exprBlock("weight_percent() < 50") } },
    { kind: "block", type: "pl_wait_until", inputs: { COND: exprBlock("is_dead()") } },
    { kind: "block", type: "pl_stop" },
    { kind: "block", type: "pl_set", inputs: { VALUE: exprBlock("0") } },
    { kind: "block", type: "pl_break" },
    { kind: "block", type: "pl_continue" },
  ];
  const conditions: ToolboxItem[] = [
    { kind: "block", type: "pl_expr", fields: { TEXT: "hp_percent() < 50" } },
    { kind: "block", type: "pl_compare", inputs: { A: exprBlock("hp_percent()"), B: exprBlock("50") } },
    { kind: "block", type: "pl_logic", fields: { OP: "and" } },
    { kind: "block", type: "pl_not" },
    { kind: "block", type: "pl_expr", fields: { TEXT: "OK" } },
  ];
  if (blocks.choose_menu) {
    conditions.push({ kind: "block", type: "pl_do", fields: { BLOCK: "choose_menu", ARGS: 'option=option("o_key")' },
      extraState: rest(blocks.choose_menu) });
  }
  const exits: ToolboxItem[] = [
    { kind: "block", type: "pl_exit_walk" },
    { kind: "block", type: "pl_exit_npc" },
    { kind: "block", type: "pl_exit_item", fields: { ITEM: "WING" } },
  ];
  const events: ToolboxItem[] = [
    { kind: "block", type: "pl_event", fields: { SCOPE: scope === "global" ? "global" : "map", NAME: "my_event" },
      inputs: { WHEN: exprBlock("hp_percent() < 30") } },
  ];
  if (scope === "block") {
    events.push({ kind: "block", type: "pl_extend" }, { kind: "block", type: "pl_disable" });
  }
  const cats = [
    { kind: "category" as const, name: "Skills", colour: COLOURS.action, contents: palette },
    { kind: "category" as const, name: "More skills", colour: COLOURS.generic, contents: others },
    { kind: "category" as const, name: "Control", colour: COLOURS.control, contents: control },
    { kind: "category" as const, name: "Conditions", colour: COLOURS.expr, contents: conditions },
    { kind: "category" as const, name: "Events", colour: COLOURS.event, contents: events },
  ];
  if (scope === "block") cats.splice(3, 0, { kind: "category", name: "Exits", colour: COLOURS.exit, contents: exits });
  return { kind: "categoryToolbox", contents: cats };
}
