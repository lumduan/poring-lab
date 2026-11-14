// THE BLOCKS' WIDTHS at 390 px (round 21, the re-measure of round 20; docs/planning/live-blocks.md
// 12.5): a MODEL of how Blockly's zelos renderer lays a block out in rows, with settings.ts' fitted
// text widths (no browser here: Blockly measures only a rendered workspace). The row rules are
// zelos' own (core/renderers/zelos/info.ts shouldStartNewRow_, Blockly 13.3.0): zelos draws every
// value input INLINE; a row ends after an end-row input, before and after a statement input, and --
// only when the block's inputs are not inline (Block.getInputsInline) -- before every input. A
// message's leftover fields go to an implicit dummy input, so with inputs inline two messages share
// ONE row: round 20's runner block read "call knife_back home (Butterfly Wing):" as one step, and
// the save point "the save point is on geffen x 119 y 40" (the reviewer's re-measure).
//
// Pure functions over the workspace JSON and the block definitions (layout.test.ts): every block
// of the ready-made projects' tabs, nested as it is, must end before Blockly's controls at 390.
import { type ArgDef, type BlockDef, DEF_BY_TYPE, type FieldKind } from "./blockdefs.ts";
import type { WsBlock } from "./blocks.ts";
import { closedText, shortExpr } from "./pickers.ts";
import { rowUnits, SETTING_GEOMETRY as G, textUnits } from "./settings.ts";

/** A statement input's left side, workspace units (zelos draws ~16; taken at 20: the model then errs wide by 8-15 % on the reviewer's three re-measured rows of main, layout.test.ts). */
export const INDENT = 20;
/** An empty value input's socket (zelos: ~40). */
export const EMPTY_INPUT = 48;
/** A text or number field's box around its text (zelos FIELD_BORDER_RECT_X_PADDING 8 on each side
 * = 16; taken at 20). A dropdown keeps settings.ts' fitted field + arrow. */
export const BOX = 20;
/** A reporter's rounded ends around its one text field (zelos: "field in round" 12; one side). */
export const ROUND = 12;

type In = { type: "end" | "dummy" | "value" | "statement"; name: string; fields: number[]; words: string[]; visible: boolean };
/** A row as drawn: its width (workspace units, from the block's left edge at its nesting) and what
 * is on it (the block's type, then its words and fields' names: a test's message). */
export type Row = { w: number; what: string };

/** Whether Blockly draws this block's inputs inline (Block.getInputsInline: set, else its guess). */
export function inputsInline(def: BlockDef, ins: readonly In[]): boolean {
  if (def.inputsInline !== undefined) return def.inputsInline;
  for (let i = 1; i < ins.length; i++) if (ins[i - 1].type === "dummy" && ins[i].type === "dummy") return false;
  for (let i = 1; i < ins.length; i++) if (ins[i - 1].type === "value" && ins[i].type === "dummy") return true;
  return ins.some((x) => x.type === "end");
}

/** A field's width on its block as shown (its value from the workspace, or `label` for a label the
 * editor fills: the badge, the run line, the hat's title). */
function fieldUnits(a: ArgDef, b: WsBlock, labels: Record<string, string>): number {
  if (a.type === "field_image") return a.width;
  if (a.type === "input_dummy" || a.type === "input_end_row" || a.type === "input_value" || a.type === "input_statement") return 0;
  return valueUnits(a as Extract<ArgDef, { type: FieldKind }>, b, labels);
}
function valueUnits(a: Extract<ArgDef, { type: FieldKind }>, b: WsBlock, labels: Record<string, string>): number {
  const raw = b.fields?.[a.name];
  const v = raw === undefined ? (a.type === "field_number" || a.type === "field_pl_num" ? String(a.value ?? 0) : (labels[a.name] ?? a.text ?? "")) : String(raw);
  switch (a.type) {
    case "field_label":
    case "field_label_serializable":
      return v ? textUnits(labels[a.name] ?? v) : 0;
    case "field_number":
    case "field_pl_num":
      return Math.max(40, textUnits(v) + BOX);
    case "field_dropdown": {
      const shown = a.options?.find(([, val]) => val === v)?.[0] ?? v;
      return textUnits(shown) + G.field + G.arrow;
    }
    case "field_pl_text":
      return textUnits(closedText(a.pick, v, v, true, true)) + BOX; // as a phone shows it
    default:
      return textUnits(v) + BOX;
  }
}

/** A block's inputs as Blockly's JSON interpolation makes them: each message's fields go to the
 * next input in it, the leftover ones to an implicit dummy input; `hidden`: the inputs the editor
 * hides (a setting's warning and note rows while empty, the run line while empty). */
function inputsOf(def: BlockDef, b: WsBlock, labels: Record<string, string>, hidden: (name: string) => boolean): In[] {
  const out: In[] = [];
  const d = def as BlockDef & Record<string, unknown>;
  for (let m = 0; m <= 12; m++) {
    const msg = d[`message${m}`] as string | undefined;
    if (msg === undefined) continue;
    const args = (d[`args${m}`] as ArgDef[] | undefined) ?? [];
    let fields: number[] = [];
    let words: string[] = [];
    for (const tok of msg.split(/(%[0-9]+)/).map((x) => x.trim()).filter(Boolean)) {
      const k = /^%([0-9]+)$/.exec(tok);
      const a = k ? args[Number(k[1]) - 1] : null;
      if (!a) {
        fields.push(textUnits(tok));
        words.push(tok);
      } else if (a.type === "input_end_row" || a.type === "input_dummy" || a.type === "input_value" || a.type === "input_statement") {
        const type = a.type === "input_end_row" ? "end" : a.type === "input_dummy" ? "dummy" : a.type === "input_value" ? "value" : "statement";
        const name = "name" in a ? a.name : "";
        out.push({ type, name, fields, words, visible: !hidden(name) });
        fields = [];
        words = [];
      } else {
        const w = fieldUnits(a, b, labels);
        if (w > 0) {
          fields.push(w);
          words.push(`[${"name" in a ? a.name : a.type}]`);
        }
      }
    }
    if (fields.length) out.push({ type: "dummy", name: "", fields, words, visible: true });
  }
  return out;
}

/** The rows a block draws, each one's width in workspace units at `indent`, then the rows of the
 * blocks in its statement inputs (at `indent` + INDENT) and of the blocks after it (`next`). */
export function blockRows(b: WsBlock, labels: Record<string, string> = {}, indent = 0, hidden: (name: string) => boolean = () => false): number[] {
  return rowsOf(b, labels, indent, hidden).map((r) => r.w);
}

/** blockRows with what each row holds. */
export function rowsOf(b: WsBlock, labels: Record<string, string> = {}, indent = 0, hidden: (name: string) => boolean = () => false): Row[] {
  const out: Row[] = [];
  for (let cur: WsBlock | undefined = b; cur; cur = cur.next?.block) {
    const def = DEF_BY_TYPE[cur.type];
    if (!def) continue;
    const all = inputsOf(def, cur, labels, hidden);
    // and / or: one value input per term, added at run time (blockly-register.ts pl_logic)
    if (cur.type === "pl_logic") for (const k of Object.keys(cur.inputs ?? {}).filter((x) => /^T[0-9]+$/.test(x)).sort((x, y) => Number(x.slice(1)) - Number(y.slice(1)))) all.push({ type: "value", name: k, fields: [], words: [], visible: true });
    const inline = inputsInline(def, all);
    // an input the editor hides is not drawn and does not end a row (common/info.ts createRows_)
    const ins = all.filter((x) => x.visible);
    let row: number[] = [];
    let what: string[] = [];
    const close = () => {
      if (row.length) out.push({ w: indent + rowUnits(row), what: `${cur!.type}: ${what.join(" ")}` });
      row = [];
      what = [];
    };
    ins.forEach((inp, i) => {
      const prev = ins[i - 1];
      const fresh = prev !== undefined && (prev.type === "end" || inp.type === "statement" || prev.type === "statement" || !inline);
      if (fresh) close();
      row.push(...inp.fields);
      what.push(...inp.words);
      if (inp.type === "value") {
        const child = cur!.inputs?.[inp.name]?.block;
        row.push(child ? blockWidth(child, labels) : EMPTY_INPUT);
        what.push(child ? `(${child.type === "pl_expr" ? String(child.fields?.TEXT ?? "") : child.type})` : "( )");
      }
      if (inp.type === "statement") {
        close();
        const child = cur!.inputs?.[inp.name]?.block;
        if (child) out.push(...rowsOf(child, labels, indent + INDENT, hidden));
      }
    });
    close();
  }
  return out;
}

/** A value block's width (its widest row; a reporter of one text field: the text and its box). */
export function blockWidth(b: WsBlock, labels: Record<string, string> = {}): number {
  const def = DEF_BY_TYPE[b.type];
  if (b.type === "pl_expr") return textUnits(shortExpr(String(b.fields?.TEXT ?? ""))) + BOX + 2 * ROUND; // as a phone shows it
  if (b.type === "pl_raw_expr") return textUnits(String(b.fields?.TEXT ?? "")) + BOX + 2 * ROUND;
  if (!def) return textUnits(b.type) + G.side;
  return Math.max(0, ...blockRows({ ...b, next: undefined }, labels));
}
