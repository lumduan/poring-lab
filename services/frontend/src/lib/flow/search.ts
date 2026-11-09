// Searching the blocks: a box at the top of the toolbox (as MatPilot's /blocks and MakeCode have).
// Typing shows every block whose words match, from every category, under its category's name,
// ready to drag. A block is also found by other words ("sleep" finds wait) and by the Python the
// flow engine prints for it ("walk_to", "detector_sees"), for learners who read the Python first.
// This file is the pure part (tested in search.test.ts); the toolbox row itself is Blockly code in
// components/flows/blockly-search.ts.
//
// `normalise`, `matchEntries` and `searchFlyout` are ported from MatPilot
// (https://github.com/lumduan/matpilot at commit d639909, src/lib/blocks/search.ts and words.ts;
// THIRD_PARTY.md), MIT License, Copyright (c) 2026 Sarat Sonsuk:
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
//
// Our own: the synonyms and Python names of OUR blocks.

export type FlyoutItem = Record<string, unknown> & { kind: string };
export type SearchEntry = { category: string; item: FlyoutItem; text: string };

/** At most this many blocks are shown. */
export const MAX_RESULTS = 40;

/** Other words for a block, so a search finds it by what it does. */
export const BLOCK_SYNONYMS: Readonly<Record<string, readonly string[]>> = {
  pl_wait: ["sleep", "pause", "delay", "time", "seconds"],
  pl_wait_until: ["until", "pause", "sleep"],
  pl_repeat: ["loop", "for", "times"],
  pl_while: ["loop", "while", "until"],
  pl_if: ["condition", "decide", "check", "else"],
  pl_compare: ["equal", "greater", "less", "more", "condition"],
  pl_logic: ["and", "or", "condition"],
  pl_not: ["not", "condition"],
  pl_stop: ["end", "exit", "quit", "done"],
  pl_break: ["exit loop"],
  pl_walk_to: ["go", "move", "cell", "position", "drive"],
  pl_hunt: ["fight", "kill", "farm", "monster", "targets"],
  pl_talk_npc: ["speak", "chat", "dialog", "person"],
  pl_choose_menu: ["answer", "option", "dialog", "select"],
  pl_use_item: ["potion", "wing", "drink", "eat"],
  pl_open_window: ["inventory", "status", "skills", "ui"],
  pl_detect_sees: ["see", "detect", "find", "model", "camera", "eyes", "sensor", "condition"],
  pl_detect_count: ["how many", "number", "detect", "model", "sensor"],
  pl_event: ["when", "event", "happens", "trigger"],
  pl_set: ["variable", "store", "remember"],
  pl_call: ["function", "procedure", "run"],
  pl_exit_walk: ["warp", "portal", "leave", "map"],
  pl_exit_npc: ["warp", "teleport", "leave", "map"],
  pl_exit_item: ["wing", "warp", "leave", "map"],
};

/** The Python the engine prints for a block (pyview.py), so a Python reader finds it. */
export const PYTHON_NAMES: Readonly<Record<string, readonly string[]>> = {
  pl_wait: ["wait_until", "False", "timeout_s"],
  pl_wait_until: ["wait_until", "timeout_s"],
  pl_repeat: ["for", "range"],
  pl_while: ["while", "bounded"],
  pl_if: ["if", "elif", "else"],
  pl_walk_to: ["walk_to", "cell"],
  pl_hunt: ["hunt"],
  pl_talk_npc: ["talk_npc", "npc"],
  pl_choose_menu: ["choose_menu", "option"],
  pl_use_item: ["use_item", "item"],
  pl_open_window: ["open_window", "window"],
  pl_detect_sees: ["detector_sees"],
  pl_detect_count: ["detector_count"],
  pl_stop: ["stop"],
  pl_event: ["on"],
  pl_call: ["def"],
  pl_exit_walk: ["take_exit", "walk_exit"],
  pl_exit_npc: ["take_exit", "npc_warp"],
  pl_exit_item: ["take_exit", "item_warp"],
};

/** Lower case, British and American spellings alike, punctuation and "_" as spaces. */
export function normalise(text: string): string {
  return text
    .toLowerCase()
    .replace(/colour/g, "color")
    .replace(/grey/g, "gray")
    .replace(/centre/g, "center")
    .replace(/metre/g, "meter")
    .replace(/[^\p{L}\p{N}]+/gu, " ")
    .trim();
}

/** The entries that match every word of `query`: a query word matches a word of the block (or of
 * its category, its other words, its Python) that starts with it. Blocks whose own words match
 * come first; the toolbox's order is kept otherwise. */
export function matchEntries(query: string, entries: readonly SearchEntry[]): SearchEntry[] {
  const words = normalise(query).split(" ").filter(Boolean);
  if (words.length === 0) return [];
  const hits: { entry: SearchEntry; own: boolean; index: number }[] = [];
  entries.forEach((entry, index) => {
    const own = normalise(entry.text).split(" ");
    const type = String(entry.item.type);
    const other = normalise(
      `${entry.category} ${(BLOCK_SYNONYMS[type] ?? []).join(" ")} ${(PYTHON_NAMES[type] ?? []).join(" ")}`,
    ).split(" ");
    const all = [...own, ...other];
    if (!words.every((word) => all.some((each) => each.startsWith(word)))) return;
    hits.push({ entry, own: words.every((word) => own.some((each) => each.startsWith(word))), index });
  });
  hits.sort((a, b) => Number(b.own) - Number(a.own) || a.index - b.index);
  return hits.map((hit) => hit.entry);
}

/** What the search shows: each category's matches under its name, or a hint. */
export function searchFlyout(query: string, entries: readonly SearchEntry[]): FlyoutItem[] {
  const label = (text: string): FlyoutItem => ({ kind: "label", text });
  if (!normalise(query)) return [label("Type a word: walk, wait, talk, detector, if…")];
  const found = matchEntries(query, entries).slice(0, MAX_RESULTS);
  if (found.length === 0) return [label(`No block matches “${query.trim()}”. Try another word.`)];
  const out: FlyoutItem[] = [];
  for (const name of [...new Set(found.map((entry) => entry.category))]) {
    out.push(label(name));
    for (const entry of found) if (entry.category === name) out.push(entry.item);
  }
  return out;
}
