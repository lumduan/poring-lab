// Blockly's registrations for a RUNNER FLOW (lib/flow/runner.ts): one block type per node of the
// description, and the runner styles added to the studio's two themes. No CSS and no React here,
// so the headless Blockly test (lib/flow/runner.test.ts) registers exactly what the page does.
// The blocks are shown, never edited: the workspace's blocks are not movable, deletable or
// editable, and their context menus are empty (a description has nothing to duplicate or delete).
import type * as BlocklyT from "blockly/core";

import { RUNNER_STYLES, type RunnerDoc, runnerDefs } from "../../lib/flow/runner.ts";
import { themesOf } from "./blockly-register.ts";

const defined = new Map<string, string>(); // doc id -> the JSON its types were defined with

/** Define (or redefine, when the generated doc changed) the doc's block types. */
export function registerRunner(B: typeof BlocklyT, doc: RunnerDoc): void {
  const defs = runnerDefs(doc);
  const key = JSON.stringify(defs);
  if (defined.get(doc.id) === key) return;
  B.common.defineBlocksWithJsonArray(defs as unknown as object[]);
  for (const d of defs) {
    const type = String(d.type);
    const blockDef = B.Blocks[type] as { init?: () => void } | undefined;
    const init = blockDef?.init;
    if (!blockDef || !init) continue;
    blockDef.init = function (this: BlocklyT.Block & { customContextMenu?: (o: unknown[]) => void }) {
      init.call(this);
      this.customContextMenu = (options: unknown[]) => {
        options.length = 0; // no Duplicate, Comment, Help, Collapse ...: a description is read
      };
    };
  }
  defined.set(doc.id, key);
}

/** The studio's light and dark themes with the runner styles added (both are shared objects). */
export function runnerThemes(B: typeof BlocklyT): { light: BlocklyT.Theme; dark: BlocklyT.Theme } {
  const th = themesOf(B);
  for (const t of [th.light, th.dark]) for (const [name, style] of Object.entries(RUNNER_STYLES)) t.setBlockStyle(name, style as unknown as BlocklyT.Theme.BlockStyle);
  return th;
}
