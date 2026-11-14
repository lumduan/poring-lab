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

// matpilot round 16 #6 (phone 390 x 844, Before Run open): the context bar (a scroll box, so its
// flex minimum was 0) shrank under an open pane and the tab row covered ◂ Maps and "Inside the
// runner"; the checklist scrolled inside a 333 px pane body in the scrolling page. Not measured in
// a browser here: these pin the rules (the reviewer re-measures).
/** The declarations of the rule whose selector list has `selector` (after `from`), or null. */
function ruleWith(css: string, selector: string, from = 0): { at: number; body: string } | null {
  const re = /([^{}]+)\{([^{}]*)\}/g;
  re.lastIndex = from;
  for (let m = re.exec(css); m; m = re.exec(css)) {
    if (m[1].split(",").some((s) => s.trim() === selector)) return { at: m.index, body: m[2] };
  }
  return null;
}

test("the studio's rows above and below the body never shrink (the node row stays whole)", () => {
  for (const row of [".studio > .studio-bar", ".studio > .device-bar", ".studio > .studio-problems", ".studio > .studio-status"]) {
    assert.match(ruleWith(studio, row)?.body ?? "", /flex-shrink:\s*0/, row);
  }
});

test("on a phone the drawer is as tall as its panes and the page is the one scroller", () => {
  const phone = studio.lastIndexOf("@media (max-width: 48rem)");
  const drawer = ruleWith(studio, '.studio[data-testid="flows-app"] .studio-drawer[data-panes]', phone);
  assert.ok(drawer, "the phone rule for the flows page's drawer");
  assert.match(drawer.body, /height:\s*auto/);
  assert.match(drawer.body, /overflow:\s*visible/);
  // it comes after the older phone rule that gave the drawer 45vh (and a scroll)
  assert.ok(drawer.at > studio.indexOf("height: 45vh"));
  const body = ruleWith(studio, '.studio[data-testid="flows-app"] .pane-body', phone);
  assert.match(body?.body ?? "", /flex:\s*none/);
  assert.doesNotMatch(body?.body ?? "", /max-height|(^|[^-])height:/);
  assert.match(ruleWith(studio, '.studio[data-testid="flows-app"] > .studio-status', phone)?.body ?? "", /position:\s*sticky/);
});

// matpilot round 20 #1 (390 x 844): the footer's Python sheet (331 px) gave its 14 file buttons
// 295 px in wrapped rows and the code box 0 px, with no way to scroll to it. Not measured in a
// browser here: these pin the rules (the reviewer re-measures).
test("on a phone the Python file buttons are one row that scrolls sideways; the sheet scrolls; the code keeps its room", () => {
  const sheet = studio.indexOf("height: 55%");
  assert.ok(sheet > 0, "the phone's Python sheet");
  const side = ruleWith(studio, ".studio-side", studio.lastIndexOf(".studio-side {", sheet) - 1);
  assert.match(side?.body ?? "", /overflow-y:\s*auto/);
  const files = ruleWith(studio, '.studio[data-testid="flows-app"] .python-files', sheet);
  assert.ok(files, "the phone's rule for the file buttons");
  assert.match(files.body, /flex-wrap:\s*nowrap/);
  assert.match(files.body, /overflow-x:\s*auto/);
  const code = ruleWith(studio, ".studio-side .code-view", sheet);
  assert.match(code?.body ?? "", /min-height:\s*12rem/);
  // round 21 (the re-measure of round 20): the code box scrolls inside, the file row and the × stay
  assert.match(code?.body ?? "", /flex:\s*1 1 0/);
  assert.match(code?.body ?? "", /overflow:\s*auto/);
  for (const sel of [".studio-side > .studio-panel-header", ".studio-side > .python-files"]) assert.match(ruleWith(studio, sel, sheet)?.body ?? "", /position:\s*sticky/, sel);
  // still inside the phone's media block (not a wide screen's rule)
  const media = studio.lastIndexOf("@media (max-width: 48rem)", files.at);
  assert.ok(media > 0 && studio.indexOf("@media", media + 1) > files.at);
});

// matpilot round 20 #6 (1440 x 900): after a click selected the xmas_dun02 card the PAGE was 1,064 px
// tall: the inspector's visually hidden words (position: absolute) had the stage's body as their
// containing block, outside the side panel's scroll box.
test("the /maps side panel's scroll box contains what sits in it absolutely; the body never grows the page on a wide screen", () => {
  const maps = readFileSync(join(import.meta.dirname, "..", "..", "components", "maps", "maps.css"), "utf8").replace(/\/\*[\s\S]*?\*\//g, "");
  const body = ruleWith(maps, ".maps-side-body");
  assert.match(body?.body ?? "", /position:\s*relative/);
  assert.match(body?.body ?? "", /overflow-y:\s*auto/);
  assert.match(ruleWith(maps, ".maps-body")?.body ?? "", /overflow:\s*hidden/);
  const phone = maps.indexOf("@media (max-width: 48rem)");
  assert.match(ruleWith(maps, ".maps-body", phone)?.body ?? "", /overflow:\s*visible/); // a phone's page scrolls
  // the lint chip's scrollIntoView moves the page on a phone only
  const app = readFileSync(join(import.meta.dirname, "..", "..", "components", "maps", "MapsApp.tsx"), "utf8");
  assert.match(app, /if \(narrow\) requestAnimationFrame\(\(\) => sideRef\.current\?\.scrollIntoView/);
});
