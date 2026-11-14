// Blockly's registrations for the /flows block editor, once per page: the mutators that keep what a
// block does not show (lossless), the block types (lib/flow/blockdefs.ts), the run-time hunt type,
// MatPilot's two themes (lib/flow/theme.ts). No CSS and no React here, so the headless Blockly test
// (lib/flow/blockly_headless.test.ts) registers exactly what the page does.
import type * as BlocklyT from "blockly/core";

import { registerPickers } from "./blockly-pickers.ts";
import { BLOCK_DEFS, LABEL_ROWS } from "../../lib/flow/blockdefs.ts";
import { huntDef, type HuntRules } from "../../lib/flow/hunt.ts";
import { noteLines, SETTING_NOTE_ROWS, settingOfType, unitOf } from "../../lib/flow/settings.ts";
import { BLOCK_STYLES, CATEGORY_STYLES, COMPONENT_STYLES, FONT_STYLE } from "../../lib/flow/theme.ts";

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
  // round 21: a badge row and a run-line row show only while they say something
  B.Extensions.register("pl_label_rows", function (this: BlocklyT.Block) {
    syncLabelRows(B, this);
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

