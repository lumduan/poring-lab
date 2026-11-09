// The search box at the top of the block editor's toolbox: a toolbox category whose row is a text
// box. Typing fills its flyout with the matching blocks of every category (lib/flow/search.ts);
// Escape clears it. Keys typed in it stay in it (Blockly's shortcuts do not see them). Loaded only
// with the block editor (Blockly is never imported into server-rendered code).
//
// Ported from MatPilot (https://github.com/lumduan/matpilot at commit d639909,
// src/lib/blocks/search.ts: SearchCategory and blockWords; THIRD_PARTY.md), MIT License, Copyright
// (c) 2026 Sarat Sonsuk. Permission is hereby granted, free of charge, to any person obtaining a
// copy of this software and associated documentation files (the "Software"), to deal in the
// Software without restriction, including without limitation the rights to use, copy, modify,
// merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons
// to whom the Software is furnished to do so, subject to the following conditions: The above
// copyright notice and this permission notice shall be included in all copies or substantial
// portions of the Software. THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS
// OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A
// PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE
// LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR
// OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
// THE SOFTWARE.
// Changed here: the toolbox searched is the one the editor shows now (its scope and catalogue), and
// the words come from OUR blocks (no Python-editor vocabulary to load).
import type * as BlocklyT from "blockly/core";

import { type Toolbox, toolboxBlocks } from "../../lib/flow/blockdefs.ts";
import { normalise, searchFlyout, type SearchEntry } from "../../lib/flow/search.ts";

export const SEARCH_KIND = "search";

let registered = false;
const words = new Map<string, string>();

/** Register the search row once per page (Blockly's registries outlive a hot reload). */
export function registerSearch(B: typeof BlocklyT, current: () => Toolbox | null): void {
  if (registered) return;
  registered = true;
  let scratch: BlocklyT.Workspace | null = null;

  /** A block's words as it shows them ("wait 1 seconds"), made once in a hidden workspace. */
  const blockWords = (item: Record<string, unknown>): string => {
    const key = JSON.stringify(item);
    const known = words.get(key);
    if (known !== undefined) return known;
    let text = String(item.type ?? "");
    scratch ??= new B.Workspace();
    const enabled = B.Events.isEnabled();
    if (enabled) B.Events.disable();
    try {
      const { kind: _kind, ...state } = item;
      void _kind;
      const block = B.serialization.blocks.append(state as unknown as BlocklyT.serialization.blocks.State, scratch);
      text = block.toString();
      block.dispose(false);
    } catch {
      // a block that needs its workspace: its type is enough
    } finally {
      if (enabled) B.Events.enable();
    }
    words.set(key, text);
    return text;
  };

  const entries = (): SearchEntry[] => {
    const tb = current();
    if (!tb) return [];
    return toolboxBlocks(tb).map(({ category, item }) => ({ category, item, text: blockWords(item) }));
  };

  class SearchCategory extends B.ToolboxCategory {
    #input: HTMLInputElement | null = null;
    #selected = false;

    protected override createDom_(): HTMLDivElement {
      const dom = super.createDom_();
      const input = document.createElement("input");
      input.type = "search";
      input.placeholder = "Search";
      input.className = "pl-toolbox-search";
      input.setAttribute("aria-label", "Search the blocks");
      input.setAttribute("data-testid", "block-search");
      input.addEventListener("input", () => this.#show());
      input.addEventListener("keydown", (event) => {
        event.stopPropagation();
        if (event.key === "Escape") {
          input.value = "";
          this.parentToolbox_.clearSelection();
        }
      });
      // a click in the box while the results are open must not close them
      input.addEventListener("click", (event) => {
        if (this.#selected) event.stopPropagation();
      });
      this.rowContents_?.replaceChildren(input);
      this.rowDiv_?.classList.add("pl-toolbox-search-row");
      this.#input = input;
      return dom;
    }

    /** No colour strip: the box is not a category of blocks. */
    protected override addColourBorder_(): void {}

    override getClickTarget(): Element {
      return this.#input ?? super.getClickTarget();
    }

    /** Blockly 13 moves keyboard focus to the toolbox item a click selects; for this row that must
     * be the text box, or what a learner types goes to the toolbox instead. */
    override getFocusableElement(): HTMLElement | SVGElement {
      return this.#input ?? super.getFocusableElement();
    }

    override setSelected(selected: boolean): void {
      super.setSelected(selected);
      if (this.rowDiv_) this.rowDiv_.style.backgroundColor = "";
      this.#selected = selected;
      if (!this.#input) return;
      if (selected) {
        this.#input.focus();
        this.#show(false);
      } else {
        this.#input.value = "";
      }
    }

    #show(refresh = true): void {
      const query = this.#input?.value ?? "";
      const toolbox = this.parentToolbox_ as unknown as BlocklyT.Toolbox;
      const found = normalise(query) ? entries() : [];
      this.updateFlyoutContents(searchFlyout(query, found) as unknown as BlocklyT.utils.toolbox.FlyoutDefinition);
      if (!this.#selected) toolbox.setSelectedItem(this);
      else if (refresh) toolbox.refreshSelection();
    }
  }

  B.registry.register(B.registry.Type.TOOLBOX_ITEM, SEARCH_KIND, SearchCategory, true);
}
