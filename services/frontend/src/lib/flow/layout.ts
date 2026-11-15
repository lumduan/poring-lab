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
import { type ArgDef, type BlockDef, DEF_BY_TYPE, type FieldKind, ROLE_OF_TYPE } from "./blockdefs.ts";
import type { WsBlock } from "./blocks.ts";
import { NAME } from "./ir.ts";
import { closedText, wrapExpr } from "./pickers.ts";
import { rowUnits, SETTING_GEOMETRY as G, settingOfType, textUnits } from "./settings.ts";
import { ROLE_PREFIX } from "./tick.ts";

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
      return textUnits(closedText(a.pick, v, v, true)) + BOX;
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
  // round 22: a long expression WRAPS (pickers.ts wrapExpr): its widest line, still one white box
  if (b.type === "pl_expr") return Math.max(...wrapExpr(String(b.fields?.TEXT ?? "")).map((l) => textUnits(l))) + BOX + 2 * ROUND;
  if (b.type === "pl_raw_expr") return textUnits(String(b.fields?.TEXT ?? "")) + BOX + 2 * ROUND;
  if (!def) return textUnits(b.type) + G.side;
  return Math.max(0, ...blockRows({ ...b, next: undefined }, labels));
}

// --- round 23: the blocks' HEIGHTS and the tab's stack ---------------------------------------------
// The reviewer (round 22's re-measure): the survival tab's events OVERLAPPED -- drink / fly_away 78 px
// at 390 (97 at 1440), fly_away / bag_full 131 (164), bag_full / eat_cane 78 (96) -- 8 fields hidden
// under the next block, because the blocks grew taller (a role a row, wrapped conditions, and / or as
// a block) while the tab placed them by an old guess. The editor now stacks a tab's top blocks from
// their MEASURED heights once drawn (BlockEditor settle, stackTops below); this model only places
// them before that (blocks.ts tabToWorkspace) and lets the tests check the stack (layout.test.ts),
// its row heights FITTED to the reviewer's measure (drink 840 units tall, fly_away 928, bag_full 793:
// the model gives +2.1 %, +3.7 %, +2.1 %, so it errs tall).

/** A row of fields (zelos: a 32-unit field and its padding). */
export const ROW_H = 42;
/** A block's own top and bottom. */
export const BLOCK_PAD = 12;
/** A statement input's top and bottom around the blocks in it; an empty one's room. */
export const STMT_PAD = 24;
export const EMPTY_STMT_H = 24;
/** A reporter of one text field, and each further line of a wrapped one (pickers.ts wrapExpr). */
export const REPORTER_H = 40;
export const LINE_H = 26;
/** The hunt block's rows (its type is defined at run time from the catalogue: hunt.ts). */
const HUNT_ROWS = 5;
/** The gap between two top blocks of a tab (workspace units): blocks.ts places them so, the editor
 * keeps them so with the heights Blockly measured (BlockEditor settle). */
export const STACK_GAP = 24;

/** A value block's height (a wrapped expression: its lines). */
function reporterHeight(b: WsBlock, labels: Record<string, string>, hidden: (name: string) => boolean): number {
  if (b.type === "pl_expr") return REPORTER_H + LINE_H * (wrapExpr(String(b.fields?.TEXT ?? "")).length - 1);
  if (b.type === "pl_raw_expr") return REPORTER_H;
  return blockHeight(b, labels, hidden);
}

/** A block's own height in workspace units (its rows, its statement inputs with what they hold),
 * without the blocks after it. */
export function blockHeight(b: WsBlock, labels: Record<string, string> = {}, hidden: (name: string) => boolean = () => false): number {
  const def = DEF_BY_TYPE[b.type];
  if (b.type === "pl_hunt") return HUNT_ROWS * ROW_H + BLOCK_PAD; // the run-time hunt type (hunt.ts): its rule rows
  if (!def) return ROW_H + BLOCK_PAD;
  const all = inputsOf(def, b, labels, hidden);
  if (b.type === "pl_logic") for (const k of Object.keys(b.inputs ?? {}).filter((x) => /^T[0-9]+$/.test(x)).sort((x, y) => Number(x.slice(1)) - Number(y.slice(1)))) all.push({ type: "value", name: k, fields: [], words: [], visible: true });
  const inline = inputsInline(def, all);
  const ins = all.filter((x) => x.visible);
  let total = 0;
  let row = 0; // the height of the row being filled (0: empty)
  const close = () => {
    total += row;
    row = 0;
  };
  ins.forEach((inp, i) => {
    const prev = ins[i - 1];
    if (prev !== undefined && (prev.type === "end" || inp.type === "statement" || prev.type === "statement" || !inline)) close();
    if (inp.type === "statement") {
      const child = b.inputs?.[inp.name]?.block;
      row = Math.max(ROW_H, (child ? stackHeight(child, labels, hidden) : EMPTY_STMT_H) + STMT_PAD);
      close();
      return;
    }
    if (inp.fields.length) row = Math.max(row, ROW_H);
    if (inp.type === "value") {
      const child = b.inputs?.[inp.name]?.block;
      row = Math.max(row, ROW_H, child ? reporterHeight(child, labels, hidden) + 8 : 0);
    }
  });
  close();
  return total + BLOCK_PAD;
}

/** A stack's height: a block and the blocks after it. */
export function stackHeight(b: WsBlock, labels: Record<string, string> = {}, hidden: (name: string) => boolean = () => false): number {
  let h = 0;
  for (let cur: WsBlock | undefined = b; cur; cur = cur.next?.block) h += blockHeight({ ...cur, next: undefined }, labels, hidden);
  return h;
}

/** A top block's box on the workspace (workspace units). */
export type TopBox = { id: string; x: number; y: number; w: number; h: number };

/** PURE (round 23): the tab's top blocks stacked so no two overlap, IN THEIR ORDER (top to bottom:
 * the order the converter reads, so the project never changes) and at their x. `pack` (a tab just
 * opened): each block right under the ones above it in its column, `gap` apart, from `top`;
 * `push` (a block's height changed since): a block only ever moves DOWN, as far as the ones above
 * it need. Returns each moved block's new y. */
export function stackTops(boxes: readonly TopBox[], mode: "pack" | "push", gap: number, top: number): Map<string, number> {
  const order = boxes.map((b, i) => ({ ...b, i })).sort((a, c) => a.y - c.y || a.x - c.x || a.i - c.i);
  const placed: TopBox[] = [];
  const out = new Map<string, number>();
  let prev = -Infinity;
  for (const b of order) {
    let y = mode === "pack" ? top : b.y;
    for (const p of placed) if (p.x < b.x + b.w && b.x < p.x + p.w) y = Math.max(y, p.y + p.h + gap);
    y = Math.max(y, prev); // never above the block before it: the order stays
    if (mode === "push") y = Math.max(y, b.y);
    if (Math.abs(y - b.y) > 0.5) out.set(b.id, y);
    placed.push({ ...b, y });
    prev = y;
  }
  return out;
}

/** PURE: do two boxes intersect (the no-overlap test)? */
export const overlaps = (a: TopBox, b: TopBox): boolean => a.x < b.x + b.w && b.x < a.x + a.w && a.y < b.y + b.h && b.y < a.y + a.h;

// --- round 25: remembered positions, left to right ---------------------------------------------------
/** Where the first column starts (workspace units; blocks.ts placed every block at x 20). */
export const SHELF_LEFT = 20;
/** What of the canvas's width the shelf leaves to Blockly's zoom buttons and trashcan (px). */
export const SHELF_RIGHT_PX = 72;

/** PURE (round 25): the key a tab's top block is remembered by in `Tab.layout` (project.ts Layout):
 * "main" for the main tab's start block; "def:<name>" for a function or an event (one namespace per
 * node: the name is the definition, and an event's name is its key); "var:<name>" for a variable or
 * a SETTING block (its variable's name). Names, not Blockly's block ids: an id lives only as long
 * as the workspace, a name is what the project, its file and the Python view say. A block with no
 * valid name yet (a function still called "?"), and any other top block -- a loose block, which
 * the converter does not keep -- has none (null): its place cannot be remembered. */
export function layoutKey(type: string, fields: Record<string, unknown> | undefined): string | null {
  if (type === "pl_main") return "main";
  const f = settingOfType(type);
  if (f) return `var:${f.var}`;
  const role = ROLE_OF_TYPE.get(type); // live blocks 5c: a role block is its variable role_<param>
  if (role) return `var:${ROLE_PREFIX}${role.param}`;
  const name = String(fields?.NAME ?? "").trim();
  if (!NAME.test(name)) return null;
  if (type === "pl_vardecl") return `var:${name}`;
  if (type === "pl_def" || type === "pl_event") return `def:${name}`;
  return null;
}

/** PURE (round 25): the top block a PERSON moved, from a Blockly event (its type "move", Blockly's
 * BLOCK_MOVE): a drag -- mouse, touch or the keyboard's move mode, all Blockly's "drag" -- or
 * "Clean up Blocks" ("cleanup"), onto the canvas (no new parent). Blockly's own moves -- a bump, a
 * snap, a connection, a block created -- and the editor's (settle moves with events off) are not a
 * person's. null: not one. */
export function personMoved(e: { type: string; blockId?: string; newParentId?: string; reason?: string[] }): string | null {
  if (e.type !== "move" || e.newParentId || !e.blockId) return null;
  return (e.reason ?? []).some((r) => r === "drag" || r === "cleanup") ? e.blockId : null;
}

/** PURE (round 25): how wide the shelf may be (workspace units) for a canvas `viewPx` wide at
 * `scale`: the visible width less Blockly's controls and the left margin. */
export const shelfWidth = (viewPx: number, scale: number): number => Math.max(0, (viewPx - SHELF_RIGHT_PX) / (scale > 0 ? scale : 1) - SHELF_LEFT);

/** A top block to place: its box, where a person put it (`at`; null: nowhere yet), and `alone`: it
 * takes a row of its own (the main tab's start block: its title row is filled in by the editor). */
export type ShelfItem = { id: string; w: number; h: number; at?: readonly [number, number] | null; alone?: boolean };

/** The widest badge a block shows (api.ts BADGE_TEXT, "●" and the words; layout.test.ts pins it):
 * the shelf leaves room for it, so a badge that arrives with the lint widens no block into the
 * next column. */
export const WIDEST_BADGE = "● verified RDP + S2";

/** PURE (round 25, Batt 2026-11-15: "lay the functions out LEFT TO RIGHT, as in the monsters tab,
 * so I see which functions the tab has without scrolling"): the tab's top blocks with no
 * remembered place go LEFT TO RIGHT, in their order, while they fit `width` (shelfWidth), then on
 * a new row under the tallest of the row; `gap` apart both ways. A remembered block stays where the
 * person put it, and a block that would land on one goes down its column under it. A phone's
 * canvas holds one block a row, so it stays one column. `width` 0: one column (round 23's list). */
export function shelf(items: readonly ShelfItem[], width: number, gap: number = STACK_GAP, top = 90, left = SHELF_LEFT): Map<string, [number, number]> {
  const out = new Map<string, [number, number]>();
  const taken: TopBox[] = [];
  for (const it of items) {
    if (!it.at) continue;
    out.set(it.id, [it.at[0], it.at[1]]);
    taken.push({ id: it.id, x: it.at[0], y: it.at[1], w: it.w, h: it.h });
  }
  let x = left;
  let rowTop = top;
  let rowBottom = top;
  let alone = false; // the row holds a block that wants it alone
  for (const it of items) {
    if (it.at) continue;
    if (x > left && (alone || it.alone || x + it.w > left + width)) {
      x = left;
      rowTop = rowBottom + gap;
      rowBottom = rowTop;
    }
    alone = !!it.alone;
    let y = rowTop;
    for (let moved = true; moved; ) {
      moved = false;
      for (const p of taken) {
        // (half a unit short of the gap: the row's own neighbour, exactly `gap` to the left, is not
        // "in the column" by a floating-point hair)
        if (p.x < x + it.w + gap - 0.5 && x < p.x + p.w + gap - 0.5 && p.y < y + it.h + gap - 0.5 && y < p.y + p.h + gap - 0.5) {
          y = p.y + p.h + gap; // down its column, under the one already there
          moved = true;
        }
      }
    }
    out.set(it.id, [x, y]);
    taken.push({ id: it.id, x, y, w: it.w, h: it.h });
    rowBottom = Math.max(rowBottom, y + it.h);
    x += it.w + gap;
  }
  return out;
}

/** PURE (round 25: remembered places WIN): after some blocks grew (taller or wider than `prev`), the
 * blocks the growth now REACHES go out of its way, `gap` from it: under a taller block, down its
 * column; beside a wider one, to the right along its row -- and a block moved so moves the ones it
 * now reaches in turn. A block the grown one did not reach before (it was not under its old bottom,
 * or not right of its old right edge: beside it, above it, or dropped ONTO it by a person, so it
 * overlapped already) stays exactly where it was. Returns each moved block's new [x, y]. */
export function pushGrown(boxes: readonly TopBox[], prev: ReadonlyMap<string, { w: number; h: number }>, gap: number = STACK_GAP): Map<string, [number, number]> {
  const at = new Map(boxes.map((b) => [b.id, { ...b }]));
  const out = new Map<string, [number, number]>();
  type Grew = { id: string; oldBottom: number; oldRight: number };
  const queue: Grew[] = [];
  for (const b of boxes) {
    const was = prev.get(b.id);
    if (was && (b.h > was.h + 0.5 || b.w > was.w + 0.5)) queue.push({ id: b.id, oldBottom: b.y + was.h, oldRight: b.x + was.w });
  }
  for (let guard = 0; queue.length && guard < 10_000; guard++) {
    const { id, oldBottom, oldRight } = queue.shift()!;
    const g = at.get(id)!;
    const bottom = g.y + g.h;
    const right = g.x + g.w;
    for (const b of at.values()) {
      if (b.id === id) continue;
      const column = b.x < right && g.x < b.x + b.w;
      const row = b.y < bottom && g.y < b.y + b.h;
      const was = { bottom: b.y + b.h, right: b.x + b.w };
      if (column && b.y >= oldBottom - 0.5 && b.y < bottom + gap - 0.5) {
        b.y = bottom + gap; // it was under the old bottom: it stays under, the gap kept
      } else if (row && b.x >= oldRight - 0.5 && b.x < right + gap - 0.5) {
        b.x = right + gap; // it was right of the old edge: it stays right of it
      } else continue;
      out.set(b.id, [b.x, b.y]);
      queue.push({ id: b.id, oldBottom: was.bottom, oldRight: was.right });
    }
  }
  return out;
}
