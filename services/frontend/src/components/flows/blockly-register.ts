// Blockly's registrations for the /flows block editor, once per page: the mutators that keep what a
// block does not show (lossless), the block types (lib/flow/blockdefs.ts), the run-time hunt type,
// MatPilot's two themes (lib/flow/theme.ts). No CSS and no React here, so the headless Blockly test
// (lib/flow/blockly_headless.test.ts) registers exactly what the page does.
import type * as BlocklyT from "blockly/core";

import { registerPickers, wrapLineField } from "./blockly-pickers.ts";
import { ABOUT_FIELDS, BLOCK_DEFS, defAbout, defTooltip, LABEL_ROWS, WHY_FIELDS, whyRows } from "../../lib/flow/blockdefs.ts";
import { exprTooltip } from "../../lib/flow/exprwords.ts";
import { huntDef, type HuntRules } from "../../lib/flow/hunt.ts";
import { wrapExpr } from "../../lib/flow/pickers.ts";
import { noteLines, SETTING_NOTE_ROWS, settingOfType, unitOf } from "../../lib/flow/settings.ts";
import { BLOCK_STYLES, CATEGORY_STYLES, COMPONENT_STYLES, FONT_STYLE } from "../../lib/flow/theme.ts";
import { placeWords, STEP_OF_TYPE, stepBlock, TICK_FN, type TickPlace, tickPlaces } from "../../lib/flow/tick.ts";

let registered = false;
/** Round 21 (the re-measure of round 20): the words a setting block in the FLYOUT or the search
 * shows when the open node's box replaces it (box.ts boxReplaced: the lint's own words); null: live. */
let flyoutNote: (name: string) => string | null = () => null;
export function setFlyoutNotes(fn: ((name: string) => string | null) | null): void {
  flyoutNote = fn ?? (() => null);
}
/** The style a setting block takes while it is not used (theme.ts; BlockEditor UNUSED_STYLE). */
const UNUSED_STYLE = "pl_unused_blocks";
let huntLists: string | null = null; // the hunt lists the pl_hunt type was last defined with

/** The hunt lists the pl_hunt type is defined with now (null: not defined yet). */
export const huntKey = (): string | null => huntLists;
let themes: { light: BlocklyT.Theme; dark: BlocklyT.Theme } | null = null;

/** Define (or redefine, when the catalogue's lists changed) the hunt block's type. */
export function registerHunt(B: typeof BlocklyT, rules: HuntRules | null): boolean {
  if (!rules) return false;
  const key = JSON.stringify(rules.groups);
  if (huntLists !== key) {
    B.common.defineBlocksWithJsonArray([huntDef(rules) as unknown as object]);
    huntLists = key;
  }
  return true;
}

export function register(B: typeof BlocklyT): void {
  // round 21 (live-blocks.md 12.5): the picker fields the block types name (field_pl_num,
  // field_pl_text), before any block is made; they keep this page's Blockly (a hot reload
  // registers nothing twice)
  registerPickers(B);
  // once per page load; Blockly's registries outlive a hot-reloaded copy of this module
  if (registered || B.Extensions.isRegistered("pl_state")) return;
  registered = true;
  // Every block keeps what it does not show (lossless): the converter's extraState. Blockly lets
  // only a mutator define the state hooks; these have no mutator UI.
  B.Extensions.registerMutator("pl_state", {
    saveExtraState(this: { plState_?: unknown }) {
      return this.plState_ ?? null;
    },
    loadExtraState(this: { plState_?: unknown }, state: unknown) {
      this.plState_ = state;
    },
  });
  // and / or: one value input per term (T0, T1, ...), rebuilt from the saved count.
  B.Extensions.registerMutator(
    "pl_logic",
    {
      saveExtraState(this: { n_?: number }) {
        return { n: this.n_ ?? 2 };
      },
      loadExtraState(this: BlocklyT.Block & { n_?: number }, state: { n?: number }) {
        const n = Math.max(2, Math.min(100, Number(state?.n ?? 2)));
        for (let i = this.n_ ?? 2; i < n; i++) this.appendValueInput(`T${i}`);
        this.n_ = Math.max(this.n_ ?? 2, n);
      },
    },
    function (this: BlocklyT.Block & { n_?: number }) {
      this.n_ = 2;
      this.appendValueInput("T0");
      this.appendValueInput("T1");
    },
  );
  // matpilot round 20 #2, #3: a SETTING block's rows follow its value -- a safety switch's warning
  // rows show while it is off, the note rows while the editor gave them words (the lint's "not
  // used"), the unit is singular at 1 ("1 cell"). Labels are decorations: no event, no undo step.
  B.Extensions.register("pl_setting", function (this: BlocklyT.Block & { plSync?: () => boolean }) {
    this.plSync = () => syncSetting(B, this);
    // round 21: in the flyout and the search, a setting the open node's box replaces says so on its
    // rows (set before the flyout measures it) and is greyed once drawn
    const f = this.workspace.isFlyout ? settingOfType(this.type) : undefined;
    const note = f ? flyoutNote(f.name) : null;
    if (note) {
      noteLines(note).forEach((l, i) => this.getField(`NOTE${i}`)?.setValue(l));
      setTimeout(() => {
        const svg = this as unknown as BlocklyT.BlockSvg;
        if (svg.isDisposed() || !svg.rendered) return;
        svg.setStyle(UNUSED_STYLE);
        svg.getSvgRoot()?.classList.add("pl-setting-unused");
      }, 0);
    }
    this.plSync();
    this.setOnChange(function (this: BlocklyT.Block & { plSync?: () => boolean }, e: BlocklyT.Events.Abstract) {
      if (e.type === B.Events.BLOCK_CHANGE && (e as BlocklyT.Events.BlockChange).blockId === this.id) this.plSync?.();
    });
  });
  // round 22: a long expression wraps onto rows of its own (whole, never shortened)
  B.Extensions.register("pl_expr_wrap", function (this: BlocklyT.Block) {
    syncExprWrap(B, this);
    this.setOnChange(function (this: BlocklyT.Block, e: BlocklyT.Events.Abstract) {
      if (e.type === B.Events.BLOCK_CHANGE && (e as BlocklyT.Events.BlockChange).blockId === this.id) syncExprWrap(B, this);
    });
  });
  // Batt 2026-11-21 ("the weight field's tooltip shows HP"): the expression's own meaning
  B.Extensions.register("pl_expr_tooltip", function (this: BlocklyT.Block) {
    this.setTooltip(() => exprTooltip(String(this.getFieldValue("TEXT") ?? "")));
  });
  // round 21: a badge row and a run-line row show only while they say something
  B.Extensions.register("pl_label_rows", function (this: BlocklyT.Block) {
    syncLabelRows(B, this);
  });
  // round 26: the hunt core's two functions say what they are (blockdefs.ts DEF_ABOUT_WORDS), by
  // their name, in the flyout too
  // round 27 (the reviewer: the rows never showed on the page): the rows follow the NAME field's
  // VALUE through its validator, which Blockly calls whenever the value is set -- also while a
  // workspace or the flyout LOADS a block (with events off: an onchange never fired then, and at
  // init the name is still the default "my_function")
  B.Extensions.register("pl_def_about", function (this: BlocklyT.Block) {
    watchDefAbout(B, this);
  });
  // round 26 (the reviewer's 5c review): any step is dragged out ALONE (tickDrag); ➡️ round 29
  // (Batt, live-blocks.md 17 #1): the lock it also set (SAFETY / REQUIRED) is gone
  B.Extensions.register("pl_tick_drag", function (this: BlocklyT.Block) {
    tickDrag(B, this);
  });
  B.common.defineBlocksWithJsonArray(BLOCK_DEFS as unknown as object[]);
  // The IR has no "disabled" statement: a block the context menu disabled would still be converted
  // and run. Detached stacks are faded by disableOrphans instead (and listed as "Not running").
  try {
    B.ContextMenuRegistry.registry.unregister("blockDisable");
  } catch {
    // not registered in this build: nothing to remove
  }
}

/** PURE of the page (Blockly only): a setting block's rows as its value says (the pl_setting
 * extension; BlockEditor calls it after filling the note rows). True: a row was shown or hidden, so
 * the block's height changed (the editor then pushes a block under it down). */
export function syncSetting(B: typeof BlocklyT, b: BlocklyT.Block): boolean {
  const f = settingOfType(b.type);
  if (!f) return false;
  const was = B.Events.isEnabled();
  if (was) B.Events.disable();
  let rows = false;
  try {
    const show = (name: string, on: boolean) => {
      const input = b.getInput(name);
      if (input && input.isVisible() !== on) {
        input.setVisible(on);
        rows = true;
      }
    };
    const off = f.kind === "switch" && b.getFieldValue("VALUE") === "off";
    for (let i = 0; b.getInput(`ROW_WARN${i}`); i++) show(`ROW_WARN${i}`, off);
    for (let i = 0; i < SETTING_NOTE_ROWS; i++) show(`ROW_NOTE${i}`, String(b.getField(`NOTE${i}`)?.getValue() ?? "") !== "");
    const unit = b.getField("UNIT");
    if (unit) {
      const v = Number(b.getFieldValue("VALUE"));
      const u = unitOf(f, f.kind === "share" ? v / 100 : v);
      if (unit.getValue() !== u) unit.setValue(u);
    }
  } finally {
    if (was) B.Events.enable();
  }
  const svg = b as BlocklyT.BlockSvg;
  if (svg.rendered) void svg.queueRender();
  return rows;
}

/** PURE of the page (Blockly only): the badge row and the run-line row (blockdefs.ts LABEL_ROWS)
 * shown only while their label says something. True: a row was shown or hidden (the block's height
 * changed). A decoration: no event, no undo step. */
export function syncLabelRows(B: typeof BlocklyT, b: BlocklyT.Block): boolean {
  let changed = false;
  const was = B.Events.isEnabled();
  if (was) B.Events.disable();
  try {
    for (const [row, field] of Object.entries(LABEL_ROWS)) {
      const input = b.getInput(row);
      const on = String(b.getField(field)?.getValue() ?? "") !== "";
      if (input && input.isVisible() !== on) {
        input.setVisible(on);
        changed = true;
      }
    }
  } finally {
    if (was) B.Events.enable();
  }
  const svg = b as BlocklyT.BlockSvg;
  if (changed && svg.rendered) void svg.queueRender();
  return changed;
}

/** PURE of the page (Blockly only; round 26): a function's ABOUT rows by its name (hunt_tick: who
 * plays it; hunt_loop: its t is not an input to pass); empty and hidden for any other. True: the
 * rows changed. */
export function syncDefAbout(B: typeof BlocklyT, b: BlocklyT.Block, name?: string): boolean {
  const fn = String(name ?? b.getFieldValue("NAME") ?? "").trim();
  const about = defAbout(fn);
  // (the hunt core's two functions: their own tooltip, in the flyout too; the editor's paint sets
  // every function's, naming Global only where the project has one)
  if (Object.keys(about).length || b.workspace.isFlyout) b.setTooltip(defTooltip(fn, false));
  const was = B.Events.isEnabled();
  if (was) B.Events.disable();
  try {
    for (const f of ABOUT_FIELDS) {
      const v = about[f] ?? "";
      if (b.getField(f) && b.getFieldValue(f) !== v) b.getField(f)?.setValue(v);
    }
  } finally {
    if (was) B.Events.enable();
  }
  return syncLabelRows(B, b);
}

/** Round 27: a function's ABOUT rows follow its NAME field's value (its validator: called on every
 * set of the value, a workspace's or the flyout's load included). */
function watchDefAbout(B: typeof BlocklyT, block: BlocklyT.Block): void {
  block.getField("NAME")?.setValidator((v: unknown) => {
    syncDefAbout(B, block, String(v ?? ""));
    return undefined; // the value as it is
  });
  syncDefAbout(B, block);
}

/** Round 26: is the block inside hunt_tick()'s body (the tick of the hunt core)? */
export function inTick(b: BlocklyT.Block): boolean {
  const root = b.getRootBlock();
  return root !== b && root.type === "pl_def" && String(root.getFieldValue("NAME") ?? "").trim() === TICK_FN;
}

/** Round 28: a block's place in hunt_tick() (tick.ts tickPlaces over the tick's statements, in
 * order; null: not inside the tick). Read fresh each time: a drop, a delete, an undo change it. */
export function stepPlace(b: BlocklyT.Block): TickPlace | null {
  if (!inTick(b)) return null;
  const def = b.getRootBlock();
  const chain: BlocklyT.Block[] = [];
  for (let cur = def.getInputTargetBlock("DO"); cur; cur = cur.getNextBlock()) chain.push(cur);
  const i = chain.indexOf(b);
  if (i < 0) return null; // nested deeper (in another block's input): not a statement of the tick
  const names = chain.map((x) => {
    const t = STEP_OF_TYPE.get(x.type);
    return t ? stepBlock(t) : null;
  });
  return tickPlaces(names)[i];
}

/** Round 28: a step block's WHY rows as its place says (an extra or a misplaced copy: why). True:
 * its rows changed. (➡️ Round 29: the padlock this also set went with the lock; a needed class's
 * "needed to run" is in its class line, true wherever a copy stands.) */
export function syncStepPlace(B: typeof BlocklyT, b: BlocklyT.Block): boolean {
  if (!STEP_OF_TYPE.has(b.type)) return false;
  const place = stepPlace(b);
  const rows = whyRows(placeWords(place));
  const was = B.Events.isEnabled();
  if (was) B.Events.disable();
  try {
    for (const f of WHY_FIELDS) if (b.getField(f) && b.getFieldValue(f) !== rows[f]) b.getField(f)?.setValue(rows[f]);
  } finally {
    if (was) B.Events.enable();
  }
  return syncLabelRows(B, b);
}

/** Round 26: takes a block out of its stack ALONE: the blocks under it go up to where it was,
 * whatever they are (Blockly's own heal keeps an unmovable block under it attached, so it is not
 * used; no block is ever made unmovable). */
export function takeOutAlone(b: BlocklyT.Block): void {
  const parent = b.previousConnection?.targetConnection ?? null;
  const next = b.getNextBlock();
  if (next) b.nextConnection?.disconnect();
  if (parent) {
    b.previousConnection?.disconnect();
    if (next?.previousConnection) parent.connect(next.previousConnection);
  }
}

let TickDrag: (new (b: BlocklyT.BlockSvg) => BlocklyT.IDragStrategy) | null = null;
/** Round 26 (the reviewer: "dragging the optional step_loot out took 9 steps and gave 6 errors"):
 * the drag of a block in hunt_tick() -- a step block anywhere, any block inside the tick -- takes
 * it out ALONE (takeOutAlone), as Delete already heals; Undo puts it back (the disconnects are in
 * the drag's own event group). ➡️ Round 29: no step is locked any more (Batt, live-blocks.md 17
 * #1): a SAFETY or REQUIRED step drags and deletes like the others, and a Run without it is
 * refused (the lint, live.problems). */
export function tickDragOf(B: typeof BlocklyT): (new (b: BlocklyT.BlockSvg) => BlocklyT.IDragStrategy) | null {
  if (TickDrag) return TickDrag;
  const Base = B.dragging?.BlockDragStrategy;
  if (!Base) return null;
  class Drag extends Base {
    override startDrag(e?: PointerEvent | KeyboardEvent): BlocklyT.IDraggable {
      // (a block in the flyout has no stack: Blockly makes the copy that is dragged)
      if (inTick(this.block) || STEP_OF_TYPE.has(this.block.type)) takeOutAlone(this.block);
      return super.startDrag(e);
    }
  }
  TickDrag = Drag;
  return TickDrag;
}

/** Round 26: a step block (and, from the editor's paint, any block inside hunt_tick()) gets the
 * tick's one-step drag (tickDragOf). ➡️ Round 29: nothing else -- no lock. */
export function tickDrag(B: typeof BlocklyT, b: BlocklyT.Block): void {
  const svg = b as BlocklyT.BlockSvg;
  const Drag = tickDragOf(B);
  if (Drag && typeof svg.setDragStrategy === "function" && !(svg.getDragStrategy?.() instanceof Drag)) svg.setDragStrategy(new Drag(svg));
}

/** PURE of the page (Blockly only; round 22): a pl_expr's text WRAPPED onto rows (pickers.ts
 * wrapExpr): its field shows the first line, each further line is a label in a row of its own
 * (WRAP1, WRAP2, ...: one field a row, so Blockly still draws the block as ONE white box; the
 * labels dark on it, flows.css). Labels are decorations: not saved, no event, no undo step. True:
 * the rows changed (the block's height changed). */
export function syncExprWrap(B: typeof BlocklyT, b: BlocklyT.Block): boolean {
  if (b.type !== "pl_expr") return false;
  const lines = wrapExpr(String(b.getFieldValue("TEXT") ?? "")).slice(1);
  let changed = false;
  const was = B.Events.isEnabled();
  if (was) B.Events.disable();
  try {
    for (let i = lines.length + 1; b.getInput(`WRAP${i}`); i++) {
      b.removeInput(`WRAP${i}`);
      changed = true;
    }
    lines.forEach((line, k) => {
      const name = `WRAP${k + 1}`;
      const f = b.getField(`${name}_T`);
      if (!f) {
        b.appendDummyInput(name).appendField(wrapLineField(B, line, "pl-expr-wrap"), `${name}_T`); // round 23: tappable
        changed = true;
      } else if (f.getValue() !== line) {
        f.setValue(line);
        changed = true;
      }
    });
  } finally {
    if (was) B.Events.enable();
  }
  const svg = b as BlocklyT.BlockSvg;
  if (changed && svg.rendered) {
    b.getField("TEXT")?.forceRerender();
    void svg.queueRender();
  }
  return changed;
}

/** MatPilot's light and dark themes (lib/flow/theme.ts); the block colours are the same in both. */
export function themesOf(B: typeof BlocklyT): { light: BlocklyT.Theme; dark: BlocklyT.Theme } {
  themes ??= {
    light: B.Theme.defineTheme("poring-studio-light", {
      name: "poring-studio-light",
      base: B.Themes.Classic,
      blockStyles: BLOCK_STYLES,
      categoryStyles: CATEGORY_STYLES,
      fontStyle: FONT_STYLE,
      componentStyles: COMPONENT_STYLES.light,
    } as unknown as BlocklyT.Theme),
    dark: B.Theme.defineTheme("poring-studio-dark", {
      name: "poring-studio-dark",
      base: B.Themes.Classic,
      blockStyles: BLOCK_STYLES,
      categoryStyles: CATEGORY_STYLES,
      fontStyle: FONT_STYLE,
      componentStyles: COMPONENT_STYLES.dark,
    } as unknown as BlocklyT.Theme),
  };
  return themes;
}

