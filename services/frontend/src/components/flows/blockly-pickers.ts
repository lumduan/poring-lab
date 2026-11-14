// THE PICKERS' Blockly fields (round 21; Batt 2026-11-14 ~19:4x ICT, docs/planning/live-blocks.md
// 12.5, ADR-0020 Amendment K): a field that is not a NAME opens a picker in Blockly's DropDownDiv,
// as matpilot's picture fields do (a dial, a lever, steppers), and SAVES exactly what the plain
// field saved: `field_pl_num` is a FieldNumber (a number), `field_pl_text` a FieldTextInput (a
// text), so a workspace, the IR and the Python view are byte for byte what they were, and a loaded
// value the list does not have is kept, shown marked (⚠). What each picker offers is
// lib/flow/pickers.ts (pure, tested); the field's `pick` (blockdefs.ts) says which picker opens:
// - stepper (seconds, counts, ranks, cells' sizes): − / + with a slider over the range and step;
// - percent: a lever bar that fills like an HP bar;
// - point (x, y in the 1280 x 720 game picture): two steppers and the picture with its dot;
// - cell (a map cell's x, y): two steppers;
// - optnum (a text field where empty means none / the default): a "none" switch and a stepper;
// - ref: a searchable list of what exists (typing filters, ranked), a typed word kept if it fits;
// - expr: a condition as sensor ▾ comparison ▾ value, a count as a stepper, a call's inputs as
//   rows, and under them the text itself, which autocompletes while typing;
// - name: a function's name stays free text; on the monsters tab it suggests attack_<class>.
// Every picker works by touch and by keyboard (arrows, Page Up / Down, Home / End, Enter, Escape),
// stays inside the blocks area, and its DOM is built element by element (no innerHTML: the CSP).
//
// The DOM helpers, openPicker / keepInside / closePicker, onDrag and makeSlider are ported from
// matpilot (https://github.com/lumduan/matpilot at commit 4022c870083c38c7ed4c62ff8361ef65a57d41f8,
// src/lib/blocks/fields/common.ts; the lever after throttle.ts; THIRD_PARTY.md), MIT License,
// Copyright (c) 2026 Sarat Sonsuk:
//
//   Permission is hereby granted, free of charge, to any person obtaining a copy of this software
//   and associated documentation files (the "Software"), to deal in the Software without
//   restriction, including without limitation the rights to use, copy, modify, merge, publish,
//   distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the
//   Software is furnished to do so, subject to the following conditions: The above copyright
//   notice and this permission notice shall be included in all copies or substantial portions of
//   the Software. THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
//   IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A
//   PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE
//   LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR
//   OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER
//   DEALINGS IN THE SOFTWARE.
import type * as BlocklyT from "blockly/core";

import { HOTKEYS } from "../../lib/flow/blockdefs.ts";
import { ExprError, exprText, parseExpr } from "../../lib/flow/expr.ts";
import type { Expr } from "../../lib/flow/ir.ts";
import {
  argRows,
  argsWith,
  type ArgRow,
  atFraction,
  callArgsWith,
  callRows,
  type Choice,
  closedText,
  COMPARE_OPS,
  complete,
  completions,
  type Cond,
  condFor,
  condOf,
  condText,
  defOn,
  type FieldAt,
  fraction,
  GAME_PX,
  litOf,
  nodeModel,
  numberOf,
  type NumRange,
  numText,
  OP_WORDS,
  optNumOf,
  paramsOf,
  pickerColours,
  type PickerData,
  pickerList,
  type PickSpec,
  placePicker,
  type Placing,
  pointIn,
  presetsOf,
  recipeNames,
  refChoices,
  refKnown,
  type SensorInfo,
  sensorsOf,
  skillKeysOn,
  sliderKey,
  snap,
  buttonStep,
  niceStep,
  exprProblem,
  GAME_AREAS,
  toViewBox,
  typedProblem,
  valueRange,
} from "../../lib/flow/pickers.ts";

export const PICK_NUM = "field_pl_num";
export const PICK_TEXT = "field_pl_text";

type B_ = typeof BlocklyT;
type RefSpec = Extract<PickSpec, { kind: "ref" }>;
const EMPTY: PickerData = { project: null, node: null, tab: null, catalogue: null, maps: null };
let source: () => PickerData = () => EMPTY;
let BL: B_ | null = null;

/** What the pickers read when they open (BlockEditor sets it for the tab it shows). */
export function setPickerSource(fn: (() => PickerData) | null): void {
  source = fn ?? (() => EMPTY);
}
const data = (): PickerData => {
  try {
    return source();
  } catch {
    return EMPTY;
  }
};

// the field's picker and what it showed last (no class fields: Blockly's constructors configure the
// field before a subclass's own fields would be set, and node's type stripping defines them after)
const specs = new WeakMap<BlocklyT.Field, PickSpec>();
const shown = new WeakMap<BlocklyT.Field, string>();
export const specOf = (f: BlocklyT.Field): PickSpec | undefined => specs.get(f);

// --- the DOM kit (matpilot common.ts) --------------------------------------------------------------
const SVG_NS = "http://www.w3.org/2000/svg";
type Attrs = Readonly<Record<string, string | number>>;

function svgEl<K extends keyof SVGElementTagNameMap>(tag: K, attrs: Attrs = {}, parent?: Element): SVGElementTagNameMap[K] {
  const el = document.createElementNS(SVG_NS, tag);
  for (const [k, v] of Object.entries(attrs)) el.setAttribute(k, String(v));
  parent?.appendChild(el);
  return el;
}
function htmlEl<K extends keyof HTMLElementTagNameMap>(tag: K, attrs: Attrs = {}, parent?: Element, text?: string): HTMLElementTagNameMap[K] {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) el.setAttribute(k, String(v));
  if (text !== undefined) el.textContent = text;
  parent?.appendChild(el);
  return el;
}
function button(parent: Element, label: string, onClick: () => void, attrs: Attrs = {}): HTMLButtonElement {
  const el = htmlEl("button", { type: "button", class: "pl-picker-button", ...attrs }, parent, label);
  el.addEventListener("click", onClick);
  return el;
}

/** The colours of the block the field is on (its parent's, for a shadow block). */
function blockColours(field: BlocklyT.Field): { primary: string; tertiary: string } {
  let block = field.getSourceBlock();
  if (block?.isShadow()) block = block.getParent() ?? block;
  const style = (block as BlocklyT.BlockSvg | null)?.style;
  // round 22: a greyed (not used) block's light slate gave white words 1.5:1: a readable pair
  return style ? pickerColours(style.colourPrimary, style.colourTertiary) : { primary: "#1d4ed8", tertiary: "#1e3a8a" };
}
function blockArea(field: BlocklyT.Field): DOMRect | null {
  const ws = field.getSourceBlock()?.workspace as Partial<BlocklyT.WorkspaceSvg> | undefined;
  return ws?.getInjectionDiv?.()?.getBoundingClientRect() ?? null;
}
/** The field's own box on the screen (its SVG group). */
function fieldBox(field: BlocklyT.Field): DOMRect | null {
  return (field.getSvgRoot() as Element | null)?.getBoundingClientRect() ?? null;
}

/** Opens a picker under the field or above it -- never over it, its arrow always at it (round 22):
 * when it fits on neither side the workspace scrolls the field to where it fits; when it still
 * does not, the picker opens COMPACT (no title, no presets, a smaller picture), and at last its
 * height is capped to the larger side and it scrolls inside (lib/flow/pickers.ts placePicker).
 * Its footer: Cancel, Done and the keys -- Escape CANCELS the whole session (every value back as
 * it was when it opened, and no undo step left), Done, Enter or a tap outside KEEP. Every key typed
 * in it stays in it (Blockly's shortcuts never see a Backspace there). */
function openPicker(field: BlocklyT.Field, content: HTMLElement, s: Session, onHide?: () => void, beforeDone?: () => void): void {
  const B = BL!;
  const foot = htmlEl("div", { class: "pl-picker-row pl-picker-foot" }, content);
  const cancel = () => {
    s.cancel();
    closePicker(field);
  };
  const keep = () => {
    beforeDone?.();
    closePicker(field);
  };
  button(foot, "Cancel", cancel, { class: "pl-picker-button pl-picker-cancel" });
  button(foot, "Done", keep, { class: "pl-picker-button pl-picker-done" });
  htmlEl("p", { class: "pl-picker-hint" }, content, "Esc: cancel · Enter or Done: keep");
  content.addEventListener("keydown", (e) => {
    const t = e.target as HTMLElement;
    if (e.key === "Escape") {
      e.preventDefault();
      cancel();
    } else if (e.key === "Enter" && !e.defaultPrevented && !(t instanceof HTMLButtonElement) && !(t instanceof HTMLSelectElement)) {
      e.preventDefault();
      keep();
    }
    e.stopPropagation();
  });
  B.DropDownDiv.clearContent();
  B.DropDownDiv.getContentDiv().appendChild(content);
  const { primary, tertiary } = blockColours(field);
  B.DropDownDiv.setColour(primary, tertiary);
  const div = B.DropDownDiv.getContentDiv().parentElement as HTMLElement | null;
  const ws = field.getSourceBlock()?.workspace as BlocklyT.WorkspaceSvg | undefined;
  content.style.overflowY = "auto";
  const measure = (): Placing | null => {
    const area = blockArea(field);
    const box = fieldBox(field);
    if (!area || !box || !div) return null;
    return { fieldTop: box.top, fieldBottom: box.bottom, areaTop: area.top, areaBottom: area.bottom, height: div.getBoundingClientRect().height };
  };
  let m = measure(); // the DropDownDiv is in the page, hidden (visibility): it measures
  if (m && div) {
    let plan = placePicker(m, true, false);
    if (plan.scrollBy !== 0 && ws && typeof ws.scroll === "function") {
      ws.scroll(ws.scrollX, ws.scrollY - plan.scrollBy, false);
      m = measure() ?? m;
      plan = placePicker(m, false, false);
    }
    if (plan.compact) {
      content.classList.add("pl-picker-compact");
      m = measure() ?? m;
      plan = placePicker(m, false, true);
    }
    if (plan.maxHeight !== null) {
      const chrome = div.getBoundingClientRect().height - content.getBoundingClientRect().height;
      content.style.maxHeight = `${Math.max(100, plan.maxHeight - chrome)}px`;
    }
  }
  B.DropDownDiv.showPositionedByField(field, onHide);
}
function closePicker(field: BlocklyT.Field): void {
  BL!.DropDownDiv.hideIfOwner(field, true);
}

/** Calls `onPoint` while the pointer is pressed on the element, in the element's own SVG units;
 * a press and its drag are ONE undo step (matpilot onDrag). Round 22 (the reviewer: a MOUSE drag in
 * the point picture read y from the picker's top): each place is mapped through the SVG's own
 * screen matrix (getScreenCTM: its box, its viewBox, any transform), else its box at that moment
 * (pickers.ts toViewBox), and the picker cannot scroll under the pointer while it drags. */
function onDrag(el: SVGSVGElement, group: () => string, onPoint: (x: number, y: number) => void): void {
  const B = BL!;
  const local = (e: PointerEvent): [number, number] => {
    const ctm = el.getScreenCTM?.();
    if (ctm && typeof el.createSVGPoint === "function") {
      const pt = el.createSVGPoint();
      pt.x = e.clientX;
      pt.y = e.clientY;
      const q = pt.matrixTransform(ctm.inverse());
      return [q.x, q.y];
    }
    const view = el.viewBox.baseVal;
    return toViewBox(e.clientX, e.clientY, el.getBoundingClientRect(), view && view.width ? view : { width: el.clientWidth, height: el.clientHeight });
  };
  el.addEventListener("pointerdown", (e) => {
    if (e.button !== 0) return;
    e.preventDefault();
    e.stopPropagation();
    el.setPointerCapture(e.pointerId);
    const g = group();
    const scroller = el.closest(".blocklyDropDownContent") as HTMLElement | null;
    const top = scroller?.scrollTop ?? 0;
    const at = (ev: PointerEvent) => {
      if (scroller && scroller.scrollTop !== top) scroller.scrollTop = top; // no scroll mid-drag
      const old = B.Events.getGroup();
      B.Events.setGroup(g);
      try {
        onPoint(...local(ev));
      } finally {
        B.Events.setGroup(old);
      }
    };
    at(e);
    const end = () => {
      el.removeEventListener("pointermove", at);
      el.removeEventListener("pointerup", end);
      el.removeEventListener("pointercancel", end);
    };
    el.addEventListener("pointermove", at);
    el.addEventListener("pointerup", end);
    el.addEventListener("pointercancel", end);
  });
}

/** Makes an element a slider for the keyboard and screen readers (matpilot makeSlider); the
 * returned function refreshes its aria values. */
function makeSlider(el: Element, label: string, r: () => NumRange, get: () => number, set: (v: number) => void, describe: (v: number) => string): () => void {
  el.setAttribute("role", "slider");
  el.setAttribute("tabindex", "0");
  el.setAttribute("aria-label", label);
  el.addEventListener("keydown", (e) => {
    const next = sliderKey((e as KeyboardEvent).key, get(), r());
    if (next === null) return;
    e.preventDefault();
    e.stopPropagation();
    set(next);
  });
  return () => {
    const v = get();
    el.setAttribute("aria-valuemin", String(r().lo));
    el.setAttribute("aria-valuemax", String(r().hi));
    el.setAttribute("aria-valuenow", String(v));
    el.setAttribute("aria-valuetext", describe(v));
  };
}

/** A touch screen (a phone): a text box is not focused when a picker opens, so the keyboard does
 * not cover the list; a tap on the box opens it. */
const coarse = (): boolean => typeof window !== "undefined" && !!window.matchMedia?.("(pointer: coarse)").matches;
function focusFirst(root: Element, selector: string, text = false): void {
  if (text && coarse()) return;
  (root.querySelector(selector) as HTMLElement | SVGElement | null)?.focus();
}

/** The control's range, widened to hold a loaded value outside it (a cell past 400, a wait of 120 s
 * on a 60 s slider): stepping never jumps a value to the slider's end. */
const widen = (r: NumRange, v: number): NumRange => (Number.isFinite(v) ? { ...r, lo: Math.min(r.lo, v), hi: Math.max(r.hi, v) } : r);

/** One edit session of a picker: every change it makes is one undo step; `cancel` (Escape, the
 * Cancel button; round 22) puts every field it may change back as it was when it opened, and the
 * session leaves no undo step behind. */
type Session = { group: () => string; run: (fn: () => void) => void; cancel: () => void; cancelled: () => boolean };
function session(fields: readonly (BlocklyT.Field | null | undefined)[]): Session {
  const B = BL!;
  const g = B.utils.idGenerator.genUid();
  const before = fields.filter((f): f is BlocklyT.Field => !!f).map((f) => [f, f.getValue()] as const);
  let cancelled = false;
  const run = (fn: () => void) => {
    const old = B.Events.getGroup();
    B.Events.setGroup(g);
    try {
      fn();
    } finally {
      B.Events.setGroup(old);
    }
  };
  return {
    group: () => g,
    run,
    cancelled: () => cancelled,
    cancel: () => {
      if (cancelled) return;
      cancelled = true;
      let changed = false;
      run(() => {
        for (const [f, v] of before) {
          if (f.getValue() !== v) {
            f.setValue(v);
            changed = true;
          }
        }
      });
      if (!changed) return;
      // the session's events fire on a timeout: then they leave the undo stack (one group)
      const ws = before[0]?.[0].getSourceBlock()?.workspace;
      setTimeout(() => {
        const stack = ws?.getUndoStack();
        while (stack?.length && stack[stack.length - 1].group === g) stack.pop();
      }, 0);
    },
  };
}

/** The session, for the headless tests (blockly_pickers.test.ts: a cancel restores and leaves no
 * undo step). */
export const pickerSession = session;

/** Where the field is (lib/flow/pickers.ts FieldAt): its block, its siblings, the input its block
 * is plugged into, the inputs of the function around it. */
function fieldAt(f: BlocklyT.Field): FieldAt {
  const b = f.getSourceBlock();
  const parentInput = b?.outputConnection?.targetConnection?.getParentInput()?.name ?? null;
  let params: string[] = [];
  for (let cur: BlocklyT.Block | null = b; cur; cur = cur.getSurroundParent()) {
    if (cur.type === "pl_def") {
      params = paramsOf(String(cur.getFieldValue("PARAMS") ?? ""));
      break;
    }
  }
  return { blockType: b?.type ?? "", field: f.name ?? "", sibling: (n) => String(b?.getFieldValue(n) ?? ""), parentInput, params };
}

// --- the controls ----------------------------------------------------------------------------------
/** A stepper: − value +, a slider under it over the range, presets, and a box to type an exact
 * number. `set` applies (the field's own validation decides); `get` reads the field back. */
function stepper(parent: Element, o: { label: string; unit?: string; range: NumRange; presets?: readonly number[]; get: () => number; set: (v: number) => void; slider?: boolean }): () => void {
  const wrap = htmlEl("div", { class: "pl-picker-stepper" }, parent);
  const row = htmlEl("div", { class: "pl-picker-row" }, wrap);
  // round 22: +/- take a NICE step (about 1 % of the range: END_HOT_S's was 0.01 s), never finer
  // than the field's own; the exact box, the slider and the presets keep the field's step
  const by = niceStep(o.range);
  const minus = button(row, "−", () => o.set(buttonStep(o.get(), -1, o.range)), { "aria-label": `${o.label}: ${by} less` });
  const num = htmlEl("input", { type: "number", inputmode: "decimal", class: "pl-picker-number", step: String(o.range.step || "any"), "aria-label": o.label }, row);
  const plus = button(row, "+", () => o.set(buttonStep(o.get(), 1, o.range)), { "aria-label": `${o.label}: ${by} more` });
  const unit = o.unit ? htmlEl("span", { class: "pl-picker-unit" }, row, o.unit) : null;
  void unit;
  // round 22: a picker with the lever shows no second slider for the same value
  const slider = o.slider === false ? null : htmlEl("input", { type: "range", class: "pl-picker-slider", min: String(o.range.lo), max: String(o.range.hi), step: String(o.range.step || "any"), "aria-label": `${o.label} (slider)` }, wrap);
  slider?.addEventListener("input", () => o.set(Number(slider.value)));
  const apply = () => {
    const v = Number(num.value);
    if (num.value.trim() !== "" && Number.isFinite(v)) o.set(v); // typed: exactly as typed (no clamp)
  };
  num.addEventListener("change", apply);
  // Enter applies the typed number, and the picker keeps it (openPicker: Enter keeps)
  num.addEventListener("keydown", (e) => {
    if (e.key === "Enter") apply();
  });
  if (o.presets?.length) {
    const pr = htmlEl("div", { class: "pl-picker-row pl-picker-presets" }, wrap);
    for (const p of o.presets) button(pr, numText(p, o.unit), () => o.set(p));
  }
  const refresh = () => {
    const v = o.get();
    if (document.activeElement !== num) num.value = Number.isFinite(v) ? String(v) : "";
    if (slider) slider.value = String(Number.isFinite(v) ? snap(v, o.range) : o.range.lo);
    minus.disabled = Number.isFinite(v) && !(v > o.range.lo);
    plus.disabled = Number.isFinite(v) && !(v < o.range.hi);
  };
  refresh();
  return refresh;
}

/** The lever bar: a bar that fills to the value like an HP bar (red low, green high; the bag the
 * other way round), dragged or tapped, the arrows step it (matpilot's throttle, lying down). */
function lever(parent: Element, o: { label: string; range: NumRange; bar: "hp" | "weight" | "level"; group: () => string; get: () => number; set: (v: number) => void }): () => void {
  const W = 260;
  const H = 56;
  const x0 = 14;
  const x1 = W - 14;
  const svg = svgEl("svg", { viewBox: `0 0 ${W} ${H}`, width: W, height: H, class: "pl-picker-lever" });
  parent.appendChild(svg);
  svgEl("rect", { class: "pl-focus-ring", x: x0 - 4, y: 10, width: x1 - x0 + 8, height: 24, rx: 12, fill: "rgba(0,0,0,0.35)", stroke: "rgba(255,255,255,0.5)" }, svg);
  const fill = svgEl("rect", { x: x0, y: 14, height: 16, rx: 8 }, svg);
  for (let i = 0; i <= 4; i++) {
    const x = x0 + ((x1 - x0) * i) / 4;
    svgEl("line", { x1: x, y1: 36, x2: x, y2: 41, stroke: "#fff", "stroke-width": 1.5, opacity: 0.8 }, svg);
    const t = svgEl("text", { x, y: 53, "text-anchor": "middle", "font-size": 11, fill: "#fff" }, svg);
    t.textContent = String(atFraction(i / 4, o.range));
  }
  const knob = svgEl("circle", { cy: 22, r: 11, fill: "#fff", stroke: "rgba(0,0,0,0.45)", "stroke-width": 1.5 }, svg);
  const colour = (f: number) => {
    const good = o.bar === "weight" ? 1 - f : f;
    return o.bar === "level" ? "#ffffff" : good < 0.3 ? "#ef4444" : good < 0.6 ? "#f59e0b" : "#22c55e";
  };
  const refreshAria = makeSlider(svg, o.label, () => o.range, o.get, o.set, (v) => `${v} percent`);
  onDrag(svg, o.group, (x) => o.set(atFraction((x - x0) / (x1 - x0), o.range)));
  const refresh = () => {
    const f = fraction(o.get(), o.range);
    const x = x0 + f * (x1 - x0);
    fill.setAttribute("width", String(Math.max(0, x - x0)));
    fill.setAttribute("fill", colour(f));
    knob.setAttribute("cx", String(x));
    refreshAria();
  };
  refresh();
  return refresh;
}

/** The searchable list: an input that filters, the list under it (ranked), arrows to move, Enter or
 * a tap to pick. `typed` keeps a word the list does not have (null: it may be kept). */
function searchList(parent: Element, o: { label: string; choices: () => Choice[]; current: string; empty?: string; typed?: (s: string) => string | null; pick: (v: string) => void }): HTMLInputElement {
  const id = BL!.utils.idGenerator.genUid();
  const input = htmlEl("input", { type: "search", class: "pl-picker-search", placeholder: "Type to search", "aria-label": o.label, role: "combobox", "aria-autocomplete": "list", "aria-expanded": "true", "aria-controls": `${id}-list`, autocomplete: "off", autocapitalize: "off", spellcheck: "false" }, parent);
  const list = htmlEl("ul", { class: "pl-picker-list", role: "listbox", id: `${id}-list`, "aria-label": o.label }, parent);
  let items: Choice[] = [];
  let active = 0;
  const draw = () => {
    items = pickerList(input.value, o.choices(), { current: o.current, typed: o.typed, empty: o.empty });
    list.replaceChildren();
    if (!items.length) htmlEl("li", { class: "pl-picker-none" }, list, "nothing matches: try another word");
    items.forEach((c, i) => {
      const li = htmlEl("li", { role: "option", id: `${id}-${i}`, class: `pl-picker-option${c.group === "refused" ? " pl-picker-refused" : ""}`, "aria-selected": String(i === active) }, list);
      htmlEl("span", { class: "pl-picker-label" }, li, c.label);
      if (c.note) htmlEl("span", { class: "pl-picker-note" }, li, c.note);
      if (c.value === o.current && c.group !== "typed") li.classList.add("pl-picker-current");
      li.addEventListener("pointerdown", (e) => e.preventDefault()); // keep the input's focus
      li.addEventListener("click", () => choose(i));
    });
    input.setAttribute("aria-activedescendant", items.length ? `${id}-${active}` : "");
    list.querySelector(`[aria-selected="true"]`)?.scrollIntoView({ block: "nearest" });
  };
  const choose = (i: number) => {
    const c = items[i];
    if (c && c.group !== "refused") o.pick(c.value);
  };
  input.addEventListener("input", () => {
    active = 0;
    draw();
  });
  input.addEventListener("keydown", (e) => {
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      active = Math.max(0, Math.min(items.length - 1, active + (e.key === "ArrowDown" ? 1 : -1)));
      draw();
    } else if (e.key === "Enter") {
      e.preventDefault();
      choose(active);
    }
  });
  active = Math.max(0, pickerList("", o.choices(), { current: o.current, empty: o.empty }).findIndex((c) => c.value === o.current));
  draw();
  return input;
}

/** A native select (a phone shows its own wheel): `options` [value, label], a value not among them
 * kept and marked. */
function select(parent: Element, label: string, options: readonly (readonly [string, string])[], value: string, onChange: (v: string) => void): HTMLSelectElement {
  const el = htmlEl("select", { class: "pl-picker-select", "aria-label": label }, parent);
  const all = options.some(([v]) => v === value) ? options : [[value, `${value || "(none)"} ⚠ not in the list`] as const, ...options];
  for (const [v, l] of all) {
    const opt = htmlEl("option", { value: v }, el, l);
    if (v === value) opt.selected = true;
  }
  el.addEventListener("change", () => onChange(el.value));
  return el;
}

// --- the pickers by kind ---------------------------------------------------------------------------
function rootOf(title: string, kind: string): HTMLDivElement {
  const root = htmlEl("div", { class: `pl-picker pl-picker-${kind}` });
  htmlEl("p", { class: "pl-picker-title" }, root, title);
  return root;
}

function numberPicker(field: BlocklyT.FieldNumber, spec: Extract<PickSpec, { kind: "stepper" | "percent" | "point" | "cell" }>): void {
  const block = field.getSourceBlock();
  const s = session([field, spec.kind === "point" || spec.kind === "cell" ? block?.getField(spec.pair) : null]);
  const root = rootOf(spec.title, spec.kind);
  const readout = htmlEl("p", { class: "pl-picker-readout", "aria-live": "polite" }, root);
  const refreshers: (() => void)[] = [];
  const refresh = () => refreshers.forEach((r) => r());
  const setOn = (f: BlocklyT.Field | null | undefined, v: number) => s.run(() => f?.setValue(v));
  if (spec.kind === "stepper" || spec.kind === "percent") {
    const get = () => Number(field.getValue());
    const r = widen({ lo: spec.lo, hi: spec.hi, step: spec.step }, get());
    const set = (v: number) => {
      setOn(field, v);
      refresh();
    };
    const unit = spec.kind === "percent" ? "%" : (spec.unit ?? "");
    const one = spec.kind === "stepper" ? spec.one : undefined;
    refreshers.push(() => (readout.textContent = numText(get(), unit, one)));
    if (spec.kind === "percent") refreshers.push(lever(root, { label: spec.title, range: r, bar: spec.bar ?? "level", group: s.group, get, set }));
    refreshers.push(stepper(root, { label: spec.title, unit, range: r, presets: presetsOf(r, spec.presets), get, set, slider: spec.kind !== "percent" }));
  } else {
    // a point or a cell: this field and its pair (X and Y) side by side, one picker for both
    const mine = spec.axis;
    const other = block?.getField(spec.pair) ?? null;
    const xf = mine === "x" ? field : other;
    const yf = mine === "x" ? other : field;
    const val = (f: BlocklyT.Field | null) => Number(f?.getValue() ?? 0);
    const rx = widen(spec.kind === "point" ? { lo: 0, hi: GAME_PX[0] - 1, step: 1 } : { lo: 0, hi: 400, step: 1 }, val(xf));
    const ry = widen(spec.kind === "point" ? { lo: 0, hi: GAME_PX[1] - 1, step: 1 } : { lo: 0, hi: 400, step: 1 }, val(yf));
    refreshers.push(() => (readout.textContent = `x ${val(xf)} · y ${val(yf)}`));
    if (spec.kind === "point") {
      // the game picture, small, with the dot: tap or drag to place it
      const W = 256;
      const H = Math.round((W * GAME_PX[1]) / GAME_PX[0]);
      const svg = svgEl("svg", { viewBox: `0 0 ${W} ${H}`, width: W, height: H, class: "pl-picker-screen", role: "img", "aria-label": "the game picture: tap to place the point" });
      root.appendChild(svg);
      svgEl("rect", { x: 0.5, y: 0.5, width: W - 1, height: H - 1, rx: 4, fill: "rgba(0,0,0,0.35)", stroke: "rgba(255,255,255,0.6)" }, svg);
      // round 22: the client's fixed windows where they usually are (pickers.ts GAME_AREAS: the UI
      // anchors' home places), outlined and named -- no game picture is shown or kept
      const k = W / GAME_PX[0];
      for (const a of GAME_AREAS) {
        const [ax, ay, aw, ah] = a.box;
        svgEl("rect", { x: ax * k + 0.5, y: ay * k + 0.5, width: aw * k - 1, height: ah * k - 1, rx: 2, fill: "rgba(255,255,255,0.08)", stroke: "rgba(255,255,255,0.55)", "stroke-dasharray": "3 2" }, svg);
        const t = svgEl("text", { x: ax * k + 3, y: ay * k + 9, "font-size": 8, fill: "#fff", opacity: 0.85 }, svg);
        t.textContent = a.name;
      }
      const dot = svgEl("circle", { r: 5, fill: "#fff", stroke: "#111", "stroke-width": 1.5 }, svg);
      onDrag(svg, s.group, (x, y) => {
        const [px, py] = pointIn((x * GAME_PX[0]) / W, (y * GAME_PX[1]) / H);
        xf?.setValue(px);
        yf?.setValue(py);
        refresh();
      });
      refreshers.push(() => {
        dot.setAttribute("cx", String((val(xf) * W) / GAME_PX[0]));
        dot.setAttribute("cy", String((val(yf) * H) / GAME_PX[1]));
      });
    }
    for (const [axis, f, r] of [["x", xf, rx], ["y", yf, ry]] as const) {
      const row = htmlEl("div", { class: "pl-picker-axis" }, root);
      htmlEl("span", { class: "pl-picker-axis-name" }, row, axis);
      refreshers.push(stepper(row, { label: `${spec.title}: ${axis}`, range: r, get: () => val(f), set: (v) => (setOn(f, v), refresh()) }));
    }
  }
  refresh();
  openPicker(field, root, s);
  focusFirst(root, ".pl-picker-lever, .pl-picker-slider, .pl-picker-number");
}

function optNumPicker(field: BlocklyT.FieldTextInput, spec: Extract<PickSpec, { kind: "optnum" }>): void {
  const s = session([field]);
  const root = rootOf(spec.title, "optnum");
  const readout = htmlEl("p", { class: "pl-picker-readout", "aria-live": "polite" }, root);
  const r: NumRange = { lo: spec.lo, hi: spec.hi, step: spec.step };
  const text = () => String(field.getValue() ?? "");
  const set = (v: string) => {
    s.run(() => field.setValue(v));
    refresh();
  };
  const toggleRow = htmlEl("div", { class: "pl-picker-row" }, root);
  const none = button(toggleRow, spec.none, () => set(""), { "aria-pressed": "false" });
  const refreshStep = stepper(root, {
    label: spec.title,
    unit: spec.unit,
    range: r,
    presets: presetsOf(r),
    get: () => {
      const n = optNumOf(text());
      return n === null || Number.isNaN(n) ? NaN : n;
    },
    // a step or the slider stays on the grid; a typed whole number is kept as typed (the converter
    // says when it is out of its range)
    set: (v) => set(String(!Number.isFinite(v) ? r.lo : Number.isInteger(v) ? v : snap(v, r))),
  });
  const refresh = () => {
    const n = optNumOf(text());
    readout.textContent = n === null ? spec.none : Number.isNaN(n) ? `${text()} ⚠ (not a whole number ${spec.lo}..${spec.hi})` : numText(n, spec.unit);
    none.setAttribute("aria-pressed", String(n === null));
    refreshStep();
  };
  refresh();
  openPicker(field, root, s);
  focusFirst(root, ".pl-picker-slider");
}

function refPicker(field: BlocklyT.FieldTextInput, spec: RefSpec | null, choices: () => Choice[], title: string, typed: ((s: string) => string | null) | undefined, empty?: string): void {
  const s = session([field]);
  const root = rootOf(title, "ref");
  const current = String(field.getValue() ?? "");
  const input = searchList(root, {
    label: title,
    choices,
    current,
    empty,
    typed,
    pick: (v) => {
      s.run(() => field.setValue(v));
      closePicker(field);
    },
  });
  if (spec && current && refKnown(spec, current, data(), fieldAt(field)) === false) htmlEl("p", { class: "pl-picker-warn" }, root, `“${current}” is not in the list: it is kept as it is, and the lint says why.`);
  openPicker(field, root, s);
  if (!coarse()) input.focus();
}

/** The condition row: sensor ▾ comparison ▾ value (the value's control follows the sensor: the
 * lever for a percent). `emit(text, rebuild)`: a new sensor, comparison or input rebuilds the row;
 * a new value only redraws the controls (a drag on the lever never loses its bar). */
function condRow(parent: Element, c0: Cond, sensors: SensorInfo[], d: PickerData, emit: (text: string, rebuild: boolean) => void, group: () => string): void {
  let c = c0;
  const sensor = sensors.find((x) => x.name === c.name);
  const row = htmlEl("div", { class: "pl-picker-cond" }, parent);
  const nodeMap = (): string => {
    const n = d.project && d.node ? d.project.nodes.find((x) => x.id === d.node) : undefined;
    return n?.kind === "map" ? n.map.map : "";
  };
  const opts: [string, string][] = sensors.map((x) => [x.name, x.fn ? `${x.name}() (a function)` : `${x.name}()${x.live ? "" : " · not live"}`]);
  if (c.left.kind === "var" && !sensor) opts.unshift([c.name, `${c.name} (a variable)`]);
  select(row, "what it reads", opts, c.name, (v) => {
    const s = sensors.find((x) => x.name === v);
    if (s) emit(condText(condFor(s, c, nodeMap())), true);
  });
  // the sensor's own inputs (hotbar_count's key, window_open's window, ...)
  for (const p of sensor?.params ?? []) {
    const cur = c.left.kind === "sense" ? c.left.args[p.name] : undefined;
    const curText = cur && cur.kind === "lit" && typeof cur.value === "string" ? cur.value : "";
    const withArg = (v: Expr | null) => {
      if (c.left.kind !== "sense") return;
      const args = { ...c.left.args };
      if (v) args[p.name] = v;
      else delete args[p.name];
      emit(condText({ ...c, left: { ...c.left, args } }), true);
    };
    const list = p.options?.length ? p.options : p.type === "window" ? (d.catalogue?.windows ?? []) : null;
    if (list?.length) select(row, p.name, list.map((o) => [o, `${p.name} ${o}`] as const), curText, (v) => withArg({ kind: "lit", value: v }));
    else {
      const t = htmlEl("input", { type: "text", class: "pl-picker-arg", placeholder: `${p.name}=…`, "aria-label": p.name, value: cur ? exprTextOf(cur) : "" }, row);
      t.addEventListener("change", () => {
        try {
          withArg(t.value.trim() ? parseExpr(t.value) : null);
        } catch {
          t.classList.add("pl-picker-bad");
        }
      });
    }
  }
  const bool = sensor?.type === "bool";
  const ops: [string, string][] = bool ? [["true", "is true"], ["false", "is false"]] : COMPARE_OPS.map((o) => [o, `${OP_WORDS[o]} (${o})`]);
  select(row, "the comparison", ops, c.op, (v) => {
    if (v === "true" || v === "false") emit(condText({ ...c, op: v, right: null }), true);
    else emit(condText({ ...c, op: v as Cond["op"], right: c.right ?? { kind: "lit", value: valueRange(sensor).lo } }), true);
  });
  if (c.op === "true" || c.op === "false") return;
  const right = c.right;
  if (sensor?.type === "map") {
    const cur = right?.kind === "lit" && typeof right.value === "object" && right.value !== null && !Array.isArray(right.value) && right.value.kind === "map" ? right.value.map : "";
    const maps = refChoices({ kind: "ref", ref: "map", title: "" }, d).map((m) => [m.value, m.label] as const);
    select(row, "the map", maps, cur, (v) => emit(condText({ ...c, right: { kind: "lit", value: { kind: "map", map: v } } }), true));
    return;
  }
  const num = right?.kind === "lit" && typeof right.value === "number" ? right.value : null;
  if (num === null && right) {
    const t = htmlEl("input", { type: "text", class: "pl-picker-arg", "aria-label": "the value", value: exprTextOf(right) }, row);
    t.addEventListener("change", () => {
      try {
        emit(condText({ ...c, right: parseExpr(t.value) }), true);
      } catch {
        t.classList.add("pl-picker-bad");
      }
    });
    return;
  }
  const r = valueRange(sensor);
  const refreshers: (() => void)[] = [];
  const get = () => (c.right?.kind === "lit" && typeof c.right.value === "number" ? c.right.value : r.lo);
  const set = (v: number) => {
    c = { ...c, right: { kind: "lit", value: v } };
    emit(condText(c), false);
    refreshers.forEach((f) => f());
  };
  const box = htmlEl("div", { class: "pl-picker-value" }, parent);
  if (sensor?.type === "percent") refreshers.push(lever(box, { label: `${c.name} (percent)`, range: r, bar: c.name.startsWith("weight") ? "weight" : c.name.startsWith("hp") ? "hp" : "level", group, get, set }));
  // round 22: the lever is THE slider of a percent (no second one under it)
  refreshers.push(stepper(box, { label: "the value", unit: sensor?.type === "percent" ? "%" : "", range: r, get, set, slider: sensor?.type !== "percent" }));
}
const exprTextOf = (e: Expr): string => exprText(e);

/** One input row of a call (a catalogue block's parameter, a function's input). */
function argRow(parent: Element, row: ArgRow, d: PickerData, onValue: (text: string | null) => void, at: FieldAt | null = null): void {
  const el = htmlEl("div", { class: "pl-picker-argrow" }, parent);
  htmlEl("span", { class: "pl-picker-argname" }, el, `${row.name}${row.required ? " *" : ""}`);
  // live blocks 5b-2 (live-blocks.md 14): a hunt block's target is a variable (the function's
  // inputs, the tab's variables); use_skill's key one of the keys the hunt core declares
  if (row.kind === "variable") {
    const vars = refChoices({ kind: "ref", ref: "variable", title: "" }, d, at).map((c) => [c.value, `${c.label} · ${c.note ?? ""}`] as const);
    const cur = row.text.trim();
    const list = cur && !vars.some(([v]) => v === cur) ? [[cur, cur] as const, ...vars] : vars;
    select(el, row.name, row.required ? list : [["", "(not given)"], ...list], cur, (v) => onValue(v || null));
    htmlEl("span", { class: "pl-picker-note" }, el, "the target: a variable holding find_target()'s value");
    return;
  }
  const skill = row.kind === "key" && at?.sibling("BLOCK") === "use_skill" ? skillKeysOn(d) : [];
  if (skill.length) {
    let cur = row.text;
    try {
      const e = parseExpr(row.text);
      if (e.kind === "lit" && typeof e.value === "string") cur = e.value;
    } catch {
      // a text that does not read stays as it is (the typed field below says why)
    }
    const list = skill.map((k) => [k, `${k} · the hunt core's heal key`] as const);
    select(el, row.name, row.required ? list : [["", "(not given)"], ...list], cur, (v) => onValue(v ? litOf(v) : null));
    htmlEl("span", { class: "pl-picker-note" }, el, "a key the hunt core declares (its start check reads it)");
    return;
  }
  const lit = (t: string) => {
    try {
      const e = parseExpr(t);
      return e.kind === "lit" && typeof e.value === "string" ? e.value : null;
    } catch {
      return null;
    }
  };
  if (row.kind === "model" || row.kind === "key" || row.kind === "options") {
    const list: (readonly [string, string])[] =
      row.kind === "model"
        ? refChoices({ kind: "ref", ref: "model", title: "" }, d).map((c) => [c.value, `${c.label} · ${c.note ?? ""}`] as const)
        : (row.kind === "key" ? [...HOTKEYS] : row.options).map((k) => [k, k] as const);
    const cur = row.text ? (lit(row.text) ?? row.text) : "";
    select(el, row.name, row.required ? list : [["", "(not given)"], ...list], cur, (v) => onValue(v ? litOf(v) : null));
  } else if (row.kind === "int") {
    const n = numberOf(row.text);
    const t = htmlEl("input", { type: "number", inputmode: "numeric", class: "pl-picker-number", "aria-label": row.name, value: n === null ? row.text : String(n) }, el);
    t.addEventListener("change", () => onValue(t.value.trim() ? t.value.trim() : null));
  } else {
    const t = htmlEl("input", { type: "text", class: "pl-picker-arg", "aria-label": row.name, placeholder: row.note, value: row.text, autocapitalize: "off", spellcheck: "false" }, el);
    t.addEventListener("change", () => onValue(t.value.trim() ? t.value : null));
  }
  if (row.note && row.kind !== "text") htmlEl("span", { class: "pl-picker-note" }, el, row.note);
}

/** The inputs a condition is plugged into (when, until, rearm, if / while / wait until, not, and / or). */
const COND_INPUTS = new Set(["WHEN", "UNTIL", "REARM", "COND", "X"]);

function exprPicker(field: BlocklyT.FieldTextInput, spec: Extract<PickSpec, { kind: "expr" }>): void {
  const s = session([field]);
  const d = data();
  const at = fieldAt(field);
  const pi = at.parentInput ?? "";
  const isCond = spec.mode === "expr" && (COND_INPUTS.has(pi) || /^T[0-9]+$/.test(pi));
  const loose = spec.mode === "expr" && at.parentInput === null;
  const title = spec.mode !== "expr" ? spec.title : isCond ? "the condition: what it reads, how, and the value" : pi === "TIMES" ? "how many times" : spec.title;
  const root = rootOf(title, "expr");
  const builder = htmlEl("div", { class: "pl-picker-builder" }, root);
  htmlEl("label", { class: "pl-picker-typed-label" }, root, spec.mode === "expr" ? "or type it (it completes as you type):" : "the inputs as text (it completes as you type):");
  const input = htmlEl("input", { type: "text", class: "pl-picker-typed", value: String(field.getValue() ?? ""), autocomplete: "off", autocapitalize: "off", spellcheck: "false", "aria-label": `${title} (text)`, role: "combobox", "aria-autocomplete": "list", "aria-expanded": "false" }, root);
  const sugg = htmlEl("ul", { class: "pl-picker-list pl-picker-suggest", role: "listbox", "aria-label": "suggestions" }, root);
  const err = htmlEl("p", { class: "pl-picker-warn", "aria-live": "polite" }, root);
  const sensors = sensorsOf(d);
  root.setAttribute("tabindex", "-1"); // where the focus waits while a part is drawn again
  let items: { from: number; to: number; choices: Choice[] } = { from: 0, to: 0, choices: [] };
  let active = -1;

  const problem = (t: string): string => {
    // round 22: a condition's problem in a learner's words ("not finished: a value is missing after >=")
    if (spec.mode === "expr") return exprProblem(t);
    if (!t.trim()) return "";
    try {
      if (spec.mode === "args") argsWith(t, "_", null);
      else callArgsWith(null, t, "_", null);
      return "";
    } catch (e) {
      return e instanceof ExprError ? e.message : "it cannot be read";
    }
  };
  const apply = (t: string) => {
    if (t !== String(field.getValue() ?? "")) s.run(() => field.setValue(t));
  };
  const drawCheck = () => {
    err.textContent = problem(input.value);
  };
  /** A picker part changed the text: apply it at once (one undo step for the whole session). */
  const emit = (t: string, rebuild: boolean) => {
    input.value = t;
    apply(t);
    if (rebuild) redraw();
    drawCheck();
  };
  /** Draw the parts again KEEPING the focus (round 22: ArrowDown on a select inside the picker
   * changed it, the select was drawn again, the focus fell to the page and the picker closed): the
   * focus waits on the picker itself, then goes to the new control of the same name. */
  const redraw = () => {
    const was = document.activeElement as HTMLElement | null;
    const name = was && builder.contains(was) ? was.getAttribute("aria-label") : null;
    if (name !== null) root.focus({ preventScroll: true });
    drawBuilder();
    if (name !== null) ([...builder.querySelectorAll("[aria-label]")].find((e) => e.getAttribute("aria-label") === name) as HTMLElement | undefined)?.focus({ preventScroll: true });
  };
  const rowsFail = (e: unknown) => {
    err.textContent = e instanceof ExprError ? e.message : "it cannot be read";
  };
  function drawBuilder(): void {
    builder.replaceChildren();
    const t = input.value;
    if (spec.mode === "expr") {
      const parsed = isCond || loose ? condOf(t) : null;
      const c = parsed ?? (isCond && !t.trim() && sensors.length ? condFor(sensors[0], null) : null);
      const n = numberOf(t);
      if (c && sensors.length) condRow(builder, c, sensors, d, emit, s.group);
      else if (!isCond && n !== null) {
        const r: NumRange = { lo: 0, hi: Math.max(100, n), step: 1 };
        const refresh = stepper(builder, { label: title, range: { ...r, step: 1 }, presets: pi === "TIMES" ? [1, 2, 3, 5, 10] : undefined, get: () => numberOf(input.value) ?? 0, set: (v) => (emit(String(v), false), refresh()) });
      } else if (t.trim()) htmlEl("p", { class: "pl-picker-note" }, builder, "This one is edited as text: and / or, sums and actions stay text (each and / or term is its own block).");
    } else if (spec.mode === "args") {
      const rows = argRows(at.sibling("BLOCK"), t, d.catalogue);
      if (!rows) htmlEl("p", { class: "pl-picker-note" }, builder, "Fix the text below first: then its inputs show here.");
      else if (!rows.length) htmlEl("p", { class: "pl-picker-note" }, builder, "This block takes no inputs.");
      for (const row of rows ?? []) argRow(builder, row, d, (v) => {
        try {
          emit(argsWith(input.value, row.name, v), true);
        } catch (e) {
          rowsFail(e);
        }
      }, at);
    } else {
      const def = defOn(d, at.sibling("PROC"));
      const rows = callRows(def, t);
      if (!rows) htmlEl("p", { class: "pl-picker-note" }, builder, "Fix the text below first: then its inputs show here.");
      else if (!def) htmlEl("p", { class: "pl-picker-note" }, builder, `${at.sibling("PROC") || "This function"} is not a function of this node yet: its inputs are text.`);
      else if (!rows.length) htmlEl("p", { class: "pl-picker-note" }, builder, `${def.name} takes no inputs.`);
      for (const row of def ? (rows ?? []) : []) argRow(builder, row, d, (v) => {
        try {
          emit(callArgsWith(def, input.value, row.name, v), true);
        } catch (e) {
          rowsFail(e);
        }
      });
    }
  }
  const drawSugg = () => {
    sugg.replaceChildren();
    input.setAttribute("aria-expanded", String(items.choices.length > 0));
    items.choices.slice(0, 8).forEach((c, i) => {
      const li = htmlEl("li", { role: "option", class: "pl-picker-option", "aria-selected": String(i === active) }, sugg);
      htmlEl("span", { class: "pl-picker-label" }, li, c.value.trim());
      if (c.note) htmlEl("span", { class: "pl-picker-note" }, li, c.note);
      li.addEventListener("pointerdown", (e) => e.preventDefault()); // keep the input's focus
      li.addEventListener("click", () => accept(i));
    });
  };
  const suggest = () => {
    items = completions(input.value, input.selectionStart ?? input.value.length, d, at);
    active = -1;
    drawSugg();
  };
  const accept = (i: number) => {
    const c = items.choices[i];
    if (!c) return;
    const r = complete(input.value, items, c.value);
    input.value = r.text;
    input.setSelectionRange(r.caret, r.caret);
    input.focus();
    drawBuilder();
    drawCheck();
    suggest();
  };
  input.addEventListener("input", () => {
    suggest();
    drawCheck();
    drawBuilder();
  });
  input.addEventListener("keydown", (e) => {
    const n = Math.min(8, items.choices.length);
    if ((e.key === "ArrowDown" || e.key === "ArrowUp") && n) {
      e.preventDefault();
      active = e.key === "ArrowDown" ? (active + 1) % n : active <= 0 ? n - 1 : active - 1;
      drawSugg();
    } else if ((e.key === "Tab" || e.key === "Enter") && active >= 0) {
      e.preventDefault();
      accept(active);
    } else if (e.key === "Enter") {
      e.preventDefault();
      apply(input.value);
      closePicker(field);
    }
    // (Escape: openPicker cancels the whole session -- the text as it was when the picker opened)
  });
  drawBuilder();
  drawCheck();
  // Done, Enter or a tap outside keep what was typed (as Blockly's own text field does); Escape and
  // Cancel put the text back as it was (round 22: one rule for every picker)
  openPicker(field, root, s, () => {
    if (!s.cancelled()) apply(input.value);
  }, () => apply(input.value));
  if (!coarse()) input.focus();
}

// --- the fields --------------------------------------------------------------------------------------
let registered = false;

/** Register the two picker field types (once per page; Blockly's registry outlives a hot reload). */
export function registerPickers(B: B_): void {
  BL = B;
  if (registered || B.registry.hasItem(B.registry.Type.FIELD, PICK_NUM)) return;
  registered = true;

  /** A number (FieldNumber underneath: it saves, validates and loads as before) whose editor is a
   * picker: a stepper, the lever, the point's picture or a cell's two steppers. */
  class PickNumber extends B.FieldNumber {
    protected override configure_(config: BlocklyT.FieldNumberConfig & { pick?: PickSpec }): void {
      super.configure_(config);
      if (config.pick) specs.set(this, config.pick);
    }
    protected override showEditor_(): void {
      const spec = specs.get(this);
      if (spec && (spec.kind === "stepper" || spec.kind === "percent" || spec.kind === "point" || spec.kind === "cell")) numberPicker(this, spec);
    }
  }

  /** A text (FieldTextInput underneath: any text saves and loads as before) whose editor is a
   * picker: the searchable list, the condition / inputs picker, an optional number's stepper. A
   * reference shows ▾ and, when it is not one of what exists, ⚠ (the value stays as it is). */
  class PickText extends B.FieldTextInput {
    protected override configure_(config: BlocklyT.FieldTextInputConfig & { pick?: PickSpec }): void {
      super.configure_(config);
      if (config.pick) specs.set(this, config.pick);
    }
    protected override getDisplayText_(): string {
      shown.set(this, markKey(this));
      return displayOf(this, super.getDisplayText_());
    }
    protected override render_(): void {
      super.render_();
      const spec = specs.get(this);
      const unknown = spec?.kind === "ref" && !this.getSourceBlock()?.isInFlyout && refKnown(spec, String(this.getValue() ?? ""), data(), fieldAt(this)) === false;
      (this.getSvgRoot() as SVGGElement | null)?.classList.toggle("pl-pick-unknown", unknown);
    }
    protected override showEditor_(e?: Event, quiet?: boolean, manage?: boolean): void {
      const spec = specs.get(this);
      const d = data();
      if (!spec) return super.showEditor_(e, quiet, manage);
      if (spec.kind === "optnum") return optNumPicker(this, spec);
      if (spec.kind === "expr") return exprPicker(this, spec);
      if (spec.kind === "ref") {
        const at = fieldAt(this);
        return refPicker(this, spec, () => refChoices(spec, data(), at), spec.title, spec.ref === "model" ? undefined : (w) => typedProblem(spec.ref, w), spec.optional);
      }
      if (spec.kind === "name") {
        const names = recipeNames(d, nodeModel(d));
        if (!names.length) return super.showEditor_(e, quiet, manage); // a plain name: free text
        return refPicker(this, null, () => names, spec.title, (w) => typedProblem("function", w));
      }
      return super.showEditor_(e, quiet, manage);
    }
  }

  B.fieldRegistry.register(PICK_NUM, PickNumber as unknown as BlocklyT.fieldRegistry.RegistrableField);
  B.fieldRegistry.register(PICK_TEXT, PickText as unknown as BlocklyT.fieldRegistry.RegistrableField);
}

/** What a picker text field shows (lib/flow/pickers.ts closedText): a reference with ▾ (⚠ when it
 * is not one of what exists), an empty optional one its word ("none"), an optional number's empty
 * word or ⚠ on a text that is no number. `plain`: Blockly's own display text (truncated). */
export function displayOf(f: BlocklyT.Field, plain: string): string {
  const spec = specs.get(f);
  const v = String(f.getValue() ?? "");
  const flyout = Boolean(f.getSourceBlock()?.isInFlyout);
  const known = spec?.kind === "ref" && !flyout ? refKnown(spec, v, data(), fieldAt(f)) : null;
  const out = closedText(spec, plain, v, known);
  if (spec?.kind === "expr") f.setTooltip(out !== plain ? v : null); // wrapped: the whole text on hover
  return out;
}

/** What a reference field's marks depend on: its value and whether it is known. */
function markKey(f: BlocklyT.Field): string {
  const spec = specs.get(f);
  if (spec?.kind !== "ref") return "";
  const flyout = Boolean(f.getSourceBlock()?.isInFlyout);
  return `${String(f.getValue() ?? "")}\u0000${flyout ? "" : String(refKnown(spec, String(f.getValue() ?? ""), data(), fieldAt(f)))}`;
}

/** After the project, the catalogue or the map list changed: draw again each picker field whose
 * words changed (a function written since, a map list that arrived). A decoration: no event. */
export function refreshPickers(ws: BlocklyT.Workspace): void {
  for (const b of ws.getAllBlocks(false)) {
    for (const input of b.inputList) {
      for (const f of input.fieldRow) {
        if (!specs.has(f) || specs.get(f)?.kind !== "ref") continue;
        const before = shown.get(f);
        if (before !== undefined && before !== markKey(f) && (b as BlocklyT.BlockSvg).rendered) f.forceRerender();
      }
    }
  }
}
