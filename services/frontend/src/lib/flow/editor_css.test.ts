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

// The studio (2026-11-09, flows-studio.md): studio.css is unlayered too, so its rules beat
// Tailwind's preflight inside the studio; its tokens are MatPilot's, light and dark.
const studio = readFileSync(join(import.meta.dirname, "..", "..", "components", "flows", "studio.css"), "utf8").replace(/\/\*[\s\S]*?\*\//g, "");

test("studio.css stays unlayered and defines the tokens light and dark", () => {
  assert.doesNotMatch(studio, /@layer|@import/);
  for (const [token, light, dark] of [
    ["--bg", "#f6f7f9", "#111418"],
    ["--run-bg", "#1d7a43", "#4cc27a"],
    ["--py-keyword", "#0000ff", "#569cd6"],
  ]) {
    assert.match(studio, new RegExp(`${token}: ${light};`));
    assert.match(studio, new RegExp(`${token}: ${dark};`));
  }
  assert.match(studio, /@media \(prefers-color-scheme: dark\)/);
  assert.match(studio, /\.studio-side \{[^}]*width: clamp\(18rem, 30vw, 28rem\)/);
  assert.match(studio, /@media \(max-width: 48rem\)[\s\S]*\.studio-side \{[^}]*height: 55%/);
});
