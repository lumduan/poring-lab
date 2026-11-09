// Blockly's registrations for the /flows block editor, once per page: the mutators that keep what a
// block does not show (lossless), the block types (lib/flow/blockdefs.ts), the run-time hunt type,
// MatPilot's two themes (lib/flow/theme.ts). No CSS and no React here, so the headless Blockly test
// (lib/flow/blockly_headless.test.ts) registers exactly what the page does.
import type * as BlocklyT from "blockly/core";

import { BLOCK_DEFS } from "../../lib/flow/blockdefs.ts";
import { huntDef, type HuntRules } from "../../lib/flow/hunt.ts";
import { BLOCK_STYLES, CATEGORY_STYLES, COMPONENT_STYLES, FONT_STYLE } from "../../lib/flow/theme.ts";

let registered = false;
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
  B.common.defineBlocksWithJsonArray(BLOCK_DEFS as unknown as object[]);
  // The IR has no "disabled" statement: a block the context menu disabled would still be converted
  // and run. Detached stacks are faded by disableOrphans instead (and listed as "Not running").
  try {
    B.ContextMenuRegistry.registry.unregister("blockDisable");
  } catch {
    // not registered in this build: nothing to remove
  }
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

