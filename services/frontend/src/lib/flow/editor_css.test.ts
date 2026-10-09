// The block editor's CSS pin (docs/planning/mw2-block-editor.md, UI issues #1, Batt 2026-10-09).
// Blockly hides its scrollbars with the SVG presentation attribute display="none"; Tailwind's
// preflight (`svg { display: block }`, @layer base) beats any presentation attribute, so a closed
// flyout's scrollbar stayed drawn over the workspace. flows.css gives the attribute its meaning
// back with an UNLAYERED rule. The behaviour itself was checked in a real headless Chromium (the
// doc's UI issues section); this pins the rule and the property that makes it win.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { test } from "node:test";

const css = readFileSync(join(import.meta.dirname, "..", "..", "components", "flows", "flows.css"), "utf8");
const code = css.replace(/\/\*[\s\S]*?\*\//g, ""); // comments may name what the code must not do

test("flows.css hides every Blockly svg whose display attribute says none", () => {
  assert.match(code, /\.injectionDiv svg\[display="none"\]\s*\{\s*display:\s*none;?\s*\}/);
});

test("flows.css stays unlayered, so its rule beats preflight's @layer base", () => {
  assert.doesNotMatch(code, /@layer|@import/);
});
