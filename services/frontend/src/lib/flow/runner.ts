// RUNNER FLOWS on /flows (Batt 2026-11-12, rogue-xmas02.md 4CQ: "make the flows of this map, so I
// can see how the bot works"): a live runner (scripts/dungeon_hunt.py run, the xmas_dun02 Rogue)
// shown as blocks with its Python beside them, the matpilot.org/blocks studio style.
//
// A runner flow is a DESCRIPTION, never a program: scripts/runner_flow_export.py writes it
// (lib/flow/runners/*.gen.ts) from the runner's own code -- the blocks and words from its SPEC,
// every number from the code's constants, every flag's help from `run`'s argparse block. The page
// shows it, and SIMULATES it in the browser on an example (lib/flow/runner_sim.ts). It is not the
// flow IR: it never goes to the backend's lint / simulate / Python routes, and nothing here reaches
// the executor, the mux or any input path. Pure data and functions (no Blockly import): the view
// (components/flows/RunnerView.tsx) and the headless test feed these to Blockly.
import type { ConfigDoc } from "./config.ts";
import { type BlockStyle, CATEGORY_COLOURS } from "./theme.ts";

export type RunnerPart = { text: string } | { param: string; shown: string };
export type RunnerBranch = { parts: RunnerPart[]; body: RunnerNode[] };
export type RunnerKind = "hat" | "step" | "loop" | "if";
export type RunnerNode = {
  id: string;
  kind: RunnerKind;
  style: string;
  parts?: RunnerPart[]; // hat / step / loop: the block's words
  branches?: RunnerBranch[]; // if: one row of words + its blocks per branch
  body?: RunnerNode[]; // hat (its stack) / loop
  head: [number, number]; // its own Python lines (1-based, inclusive)
  lines: [number, number]; // with its body
  why: string;
  flags: string[];
  code: string[];
  params: string[];
  tab?: string; // a stack's tab on /flows (2026-11-13); absent: the stack's id
  gate?: string; // the technique switch (lib/flow/config.ts) it belongs to: greyed while off
};
export type RunnerParam = { value: unknown; source: string; note: string };
export type RunnerFlag = { help: string | null; default: unknown; value: unknown; kind: "bool" | "value"; base: boolean };
export type RunnerOptional = { name: string; title: string; flags: string[]; note: string };
export type RunnerDoc = {
  kind: "runner-flow";
  format: 1;
  generated_by: string;
  description_only: true;
  id: string;
  title: string;
  subtitle?: string; // 2026-11-13: the title is the map's name; this says what the flow is
  map: string;
  char: string;
  script: string;
  version: string;
  feature_version?: string; // the newest technique's version (2026-11-13)
  file: string;
  command: { base: string[]; optional: RunnerOptional[] };
  params: Record<string, RunnerParam>;
  flags: Record<string, RunnerFlag>;
  stacks: RunnerNode[];
  python: string;
  // dungeon@9.41 (2026-11-13): where the map's flow begins and how it leaves the map (absent in an
  // older export)
  entry?: string;
  exits?: RunnerExit[];
  config?: ConfigDoc; // 2026-11-13: every setting a person may set (scripts/flow_config.py)
};
export type RunnerExit = { id: string; kind: "item_warp" | "death_respawn"; when: string; how: string; to: string; flag: string };

/** A block of a technique switched off: a grey that still carries white text (contrast >= 4.5). */
export const OFF_GREY = "#5f6670";

/** The runner view's own block styles, beside MatPilot's (theme.ts): the safety rules in its
 * red (sound), Batt's technique (the Knife swap, in the base since 4DQ) in its purple (light);
 * their hats get the round cap. */
export const RUNNER_STYLES: Record<string, BlockStyle> = {
  rd_safety_hat_blocks: { colourPrimary: CATEGORY_COLOURS.sound, hat: "cap" },
  rd_safety_blocks: { colourPrimary: CATEGORY_COLOURS.sound },
  rd_optional_hat_blocks: { colourPrimary: CATEGORY_COLOURS.light, hat: "cap" },
  rd_optional_blocks: { colourPrimary: CATEGORY_COLOURS.light },
  // 2026-11-13 (Batt: "the respawn as a function block"): a function's definition, the Functions
  // colour with the round cap
  rd_function_hat_blocks: { colourPrimary: CATEGORY_COLOURS.functions, hat: "cap" },
  // 2026-11-13 ~15:2x (Batt: the techniques' switches): a block of a technique switched off
  rd_off_blocks: { colourPrimary: OFF_GREY },
  rd_off_hat_blocks: { colourPrimary: OFF_GREY, hat: "cap" },
};

/** A block's row width (characters) before its words wrap onto the next row. */
export const ROW_CHARS = 46;

/** Every node of the doc, in reading order (depth first). */
export function allNodes(doc: RunnerDoc): RunnerNode[] {
  const out: RunnerNode[] = [];
  const walk = (n: RunnerNode) => {
    out.push(n);
    for (const c of n.body ?? []) walk(c);
    for (const b of n.branches ?? []) for (const c of b.body) walk(c);
  };
  for (const s of doc.stacks) walk(s);
  return out;
}

export function findNode(doc: RunnerDoc, id: string | null): RunnerNode | null {
  if (!id) return null;
  return allNodes(doc).find((n) => n.id === id) ?? null;
}

/** The Blockly type of a node: one per node (each block has its own words). */
export const blockType = (doc: RunnerDoc, n: RunnerNode) => `rd_${doc.id}_${n.id}`;

/** The words of a row as plain text (the inspector's title, a tooltip, a test). */
export const textOf = (parts: RunnerPart[]) => parts.map((p) => ("param" in p ? p.shown : p.text)).join("");

/** A node's title: its words, or its first branch's. */
export function titleOf(n: RunnerNode): string {
  return textOf(n.parts ?? n.branches?.[0]?.parts ?? []);
}

/** The Python lines the code view marks for a node: a hat or a loop marks its own header (its
 * body is the whole stack); a step or an if marks everything it holds. */
export function markOf(n: RunnerNode): [number, number] {
  return n.kind === "hat" || n.kind === "loop" ? n.head : n.lines;
}

/** The innermost node whose Python lines hold ``line`` (a click in the code view). */
export function nodeAtLine(doc: RunnerDoc, line: number): RunnerNode | null {
  let best: RunnerNode | null = null;
  for (const n of allNodes(doc)) {
    const [a, b] = markOf(n);
    if (line >= a && line <= b && (!best || b - a <= markOf(best)[1] - markOf(best)[0])) best = n;
  }
  return best;
}

/** Wrap a row of words into rows of at most ``width`` characters (a number never splits). */
export function wrapParts(parts: RunnerPart[], width = ROW_CHARS): RunnerPart[][] {
  type Tok = { text: string } | { param: string; shown: string };
  const toks: Tok[] = [];
  for (const p of parts) {
    if ("param" in p) toks.push(p);
    else for (const w of p.text.split(/(?<= )/)) if (w) toks.push({ text: w });
  }
  const rows: Tok[][] = [[]];
  let len = 0;
  for (const t of toks) {
    const n = "param" in t ? t.shown.length + 2 : t.text.length;
    if (len > 0 && len + n > width && !("text" in t && t.text.trim() === "")) {
      rows.push([]);
      len = 0;
    }
    rows[rows.length - 1].push(t);
    len += n;
  }
  // adjacent words back into one piece of text
  return rows
    .filter((r) => r.length)
    .map((r) => {
      const out: RunnerPart[] = [];
      for (const t of r) {
        const last = out[out.length - 1];
        if ("text" in t && last && "text" in last) last.text += t.text;
        else out.push("text" in t ? { text: t.text } : { ...t });
      }
      return out;
    });
}

type Arg = { type: string; name?: string; text?: string };
type Def = Record<string, unknown>;

/** A row as a Blockly message and its arguments: words are labels, numbers are text pills
 * (field_input on a non-editable block: shown, never editable). "%" is escaped as "%%". */
export function message(row: RunnerPart[], counter: { n: number }): { message: string; args: Arg[] } {
  const args: Arg[] = [];
  let msg = "";
  for (const p of row) {
    if ("param" in p) {
      args.push({ type: "field_input", name: `P${counter.n++}`, text: p.shown });
      msg += `%${args.length}`;
    } else {
      // a digit right after a reference would join it ("%1" + "0" = "%10"): a space between
      const t = p.text.replaceAll("%", "%%");
      msg += /%\d+$/.test(msg) && /^\d/.test(t) ? ` ${t}` : t;
    }
  }
  return { message: msg.replace(/\s+/g, " ").trim() || " ", args };
}

/** The Blockly JSON type definitions of every node of the doc. */
export function runnerDefs(doc: RunnerDoc): Def[] {
  return allNodes(doc).map((n) => {
    const def: Def = { type: blockType(doc, n), style: n.style, tooltip: n.why, inputsInline: false };
    const counter = { n: 0 };
    let i = 0;
    const row = (r: RunnerPart[]) => {
      const m = message(r, counter);
      def[`message${i}`] = m.message;
      def[`args${i}`] = m.args;
      i++;
    };
    const statement = (name: string) => {
      def[`message${i}`] = "%1";
      def[`args${i}`] = [{ type: "input_statement", name }];
      i++;
    };
    if (n.kind === "if") {
      (n.branches ?? []).forEach((b, k) => {
        for (const r of wrapParts(b.parts)) row(r);
        statement(`B${k}`);
      });
    } else {
      for (const r of wrapParts(n.parts ?? [])) row(r);
      if (n.kind === "loop") statement("BODY");
    }
    if (n.kind !== "hat") def.previousStatement = null;
    def.nextStatement = null;
    return def;
  });
}

type SerBlock = {
  type: string;
  id: string;
  x?: number;
  y?: number;
  movable: false;
  deletable: false;
  editable: false;
  inputs?: Record<string, { block: SerBlock }>;
  next?: { block: SerBlock };
};

/** The view's TABS (Batt 2026-11-13: "I don't see the Knife swap's blocks"): each stack on the
 * tab its export names (the run's own is the map's name), in the doc's order; a tab may hold more
 * than one stack (the Knife swap's two functions). Nothing is placed off-screen any more. */
export type RunnerTab = { name: string; stacks: string[] };
export function runnerTabs(doc: RunnerDoc): RunnerTab[] {
  const out: RunnerTab[] = [];
  for (const s of doc.stacks) {
    const name = s.tab ?? s.id;
    const t = out.find((x) => x.name === name);
    if (t) t.stacks.push(s.id);
    else out.push({ name, stacks: [s.id] });
  }
  return out;
}

/** The stack (its top block's id) that holds a node; null when no stack does. */
export function stackOf(doc: RunnerDoc, id: string | null): string | null {
  if (!id) return null;
  for (const s of doc.stacks) if (allNodes({ ...doc, stacks: [s] }).some((n) => n.id === id)) return s.id;
  return null;
}

/** The tab that shows a node (the simulation's block, a clicked line of Python). */
export function tabOf(doc: RunnerDoc, id: string | null): string | null {
  const s = stackOf(doc, id);
  return s ? (runnerTabs(doc).find((t) => t.stacks.includes(s))?.name ?? null) : null;
}

/** Where each stack of a tab starts before the view lays them out by their drawn size: one under
 * the other. */
export const STACK_X = 24;
export const STACK_Y0 = 24;
export const STACK_GAP_Y = 900;

/** The workspace (Blockly's JSON serialization): the stacks named (every stack when none are),
 * every block fixed in place (not movable, deletable or editable: a description is read, not
 * edited). */
export function runnerWorkspace(doc: RunnerDoc, only: readonly string[] | null = null): { blocks: { languageVersion: 0; blocks: SerBlock[] } } {
  const one = (n: RunnerNode): SerBlock => {
    const b: SerBlock = { type: blockType(doc, n), id: n.id, movable: false, deletable: false, editable: false };
    const inputs: Record<string, { block: SerBlock }> = {};
    if (n.kind === "loop" && n.body?.length) inputs.BODY = { block: chain(n.body) };
    (n.branches ?? []).forEach((br, k) => {
      if (br.body.length) inputs[`B${k}`] = { block: chain(br.body) };
    });
    if (Object.keys(inputs).length) b.inputs = inputs;
    return b;
  };
  const chain = (ns: RunnerNode[]): SerBlock => {
    const first = one(ns[0]);
    let cur = first;
    for (const n of ns.slice(1)) {
      const nx = one(n);
      cur.next = { block: nx };
      cur = nx;
    }
    return first;
  };
  const tops = doc.stacks
    .filter((s) => !only || only.includes(s.id))
    .map((s, k) => {
      const top = one(s);
      if (s.kind === "hat" && s.body?.length) top.next = { block: chain(s.body) };
      return { ...top, x: STACK_X, y: STACK_Y0 + STACK_GAP_Y * k };
    });
  return { blocks: { languageVersion: 0, blocks: tops } };
}

/** A parameter's value as the inspector shows it. */
export function valueText(v: unknown): string {
  if (typeof v === "string") return v;
  if (typeof v === "boolean") return v ? "on" : "off";
  if (v === null || v === undefined) return "-";
  return JSON.stringify(v);
}

/** The command line as text, one flag (with its value) per piece. */
export function commandPieces(tokens: string[]): string[] {
  const out: string[] = [];
  for (let i = 0; i < tokens.length; i++) {
    if (i + 1 < tokens.length && !tokens[i + 1].startsWith("--")) {
      out.push(`${tokens[i]} ${tokens[i + 1]}`);
      i++;
    } else out.push(tokens[i]);
  }
  return out;
}

/** The doc's shape, checked when it is loaded (a generated file, but the view trusts nothing):
 * every node's lines inside the Python, a known style, numbers named by its words known. */
export function checkDoc(doc: RunnerDoc, styles: Record<string, unknown>): string[] {
  const errs: string[] = [];
  if (doc.kind !== "runner-flow" || doc.format !== 1 || doc.description_only !== true) errs.push("not a runner-flow description (format 1)");
  const nLines = doc.python.replace(/\n$/, "").split("\n").length;
  const ids = new Set<string>();
  for (const n of allNodes(doc)) {
    if (ids.has(n.id)) errs.push(`${n.id}: the id is used twice`);
    ids.add(n.id);
    if (!(n.style in styles)) errs.push(`${n.id}: unknown style ${n.style}`);
    for (const r of [n.head, n.lines]) if (!(r[0] >= 1 && r[0] <= r[1] && r[1] <= nLines)) errs.push(`${n.id}: lines ${r.join("-")} outside the Python`);
    if (!(n.lines[0] <= n.head[0] && n.head[1] <= n.lines[1])) errs.push(`${n.id}: its header is not inside its lines`);
    const parts = [...(n.parts ?? []), ...(n.branches ?? []).flatMap((b) => b.parts)];
    for (const p of parts) if ("param" in p && !(p.param in doc.params)) errs.push(`${n.id}: unknown number ${p.param}`);
    for (const p of n.params) if (!(p in doc.params)) errs.push(`${n.id}: unknown number ${p}`);
    for (const f of n.flags) if (!(f in doc.flags)) errs.push(`${n.id}: unknown flag ${f}`);
    if (n.kind === "if" && !n.branches?.length) errs.push(`${n.id}: an if with no branch`);
  }
  return errs;
}
