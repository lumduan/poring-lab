// matpilot round 17 N1: heal and the Fly Wing each showed two thresholds (the survival tab's events
// and the settings) and neither page said which one a live run uses. The pages now say it from the
// engine's takeovers (POST /flows/lint `box`, poring_flow.live.takeovers; its own test is
// services/backend/tests/test_live_player.py). The doc below is that function's output for the one
// box (project_xmas_dun02.json); the settings are its setting blocks (live-blocks.md 12), at our
// defaults.
import assert from "node:assert/strict";
import { test } from "node:test";

import { type BoxDoc, boxNameWords, boxTabNote, boxTabShort } from "./box.ts";
import { xmasProject } from "./project.ts";
import { nodeSettings } from "./settings.ts";
import { stripFoldLine } from "./words.ts";

const ev = (play: string, settings: string[], replaces: string, by: string, tab: string, when: string, until: string | null = null) => ({ play, settings, replaces, kind: "event" as const, by, path: `xmas_dun02/${tab}/${by}`, when, until });
const fnRow = (play: string, settings: string[], replaces: string, by: string | null, tab: string, steps?: string) => ({ play, settings, replaces, kind: "function" as const, by, path: by ? `xmas_dun02/${tab}/${by}` : null, ...(steps ? { steps } : {}) });
const BOX: BoxDoc = {
  // 2026-11-14 (live-blocks.md 10): the drink under 50 %; the box eats ("eat": a play of its own,
  // no takeover row: it switches nothing of the runner's off)
  plays: ["boss_fly", "eat", "fly_hp", "home_end", "knife", "model", "potion", "recipes", "respawn", "weight_home"],
  takeovers: [
    ev("potion", ["potion_below"], "the runner's potion on HP", "drink", "survival", "HP < 50 %", "HP >= 51 %"),
    ev("fly_hp", ["fly_below"], "the runner's Fly Wing on HP", "fly_away", "survival", "a boss is seen or HP < 25 %"),
    ev("boss_fly", [], "the runner's boss fly (a Battle Log boss line)", "fly_away", "survival", "a boss is seen or HP < 25 %"),
    fnRow("knife", [], "the runner's Knife and dagger presses (the swap's moments stay the runner's)", "knife_on", "knife"),
    fnRow("knife", [], "the runner's Knife and dagger presses (the swap's moments stay the runner's)", "knife_back", "knife"),
    fnRow("respawn", ["respawn_at"], "the runner's clicks on the death dialog", "respawn_button", "exits", "a click at 645,481"),
    fnRow("respawn", ["respawn_confirm_at"], "the runner's clicks on the death dialog", "respawn_ok", "exits", "a click at 714,405"),
    ev("weight_home", ["weight_home"], "the runner's weight exit on a read weight (an unread weight drawn red keeps its own rule)", "bag_full", "survival", "weight >= 50 %"),
    fnRow("home_end", [], "the runner's Butterfly Wing press at the end", "fly_home", "exits"),
  ],
  stays: ["fly_rate", "fly_rate_below"],
  playable: true,
};
const values = nodeSettings(xmasProject(), "xmas_dun02").values;

test("the survival tab's note: each event, what it replaces with its setting block and value, and what stays", () => {
  assert.equal(values.potion_below, 0.4); // the setting block's value (our default) the note quotes
  const note = boxTabNote(BOX, "xmas_dun02", "survival", values);
  assert.equal(
    note,
    "In a Run of this project these play inside the hunt core, and the runner's own are off: " +
      "drink replaces the runner's potion on HP (the setting heal at HP under 40 % (potion_below)); " +
      "fly_away replaces the runner's Fly Wing on HP (the setting Fly Wing at HP under 20 % (fly_below)) and the runner's boss fly (a Battle Log boss line); " +
      "bag_full replaces the runner's weight exit on a read weight (an unread weight drawn red keeps its own rule) (the setting go home when the bag is over 50 % (weight_home)). " +
      "The HP-rate fly stays the runner's (the settings or HP falling faster than 150 HP/s (fly_rate) while under 50 % (fly_rate_below)).",
  );
  // the exits tab: the respawn's two functions with their points
  assert.match(boxTabNote(BOX, "xmas_dun02", "exits", values) ?? "", /^In a Run of this project .*respawn_button replaces the runner's clicks on the death dialog \(the setting respawn button at [0-9]+,[0-9]+ \(respawn_at\)\); respawn_ok replaces .*fly_home replaces the runner's Butterfly Wing press at the end\.$/);
  // a tab the box plays nothing of, no box: no note; without the settings: their words only
  assert.equal(boxTabNote(BOX, "xmas_dun02", "keys", values), null);
  assert.equal(boxTabNote(null, "xmas_dun02", "survival", values), null);
  assert.match(boxTabNote(BOX, "xmas_dun02", "survival", null) ?? "", /drink replaces the runner's potion on HP \(the setting heal at HP under \(potion_below\)\)/);
});

test("the /maps inspector's tabs list says what the box plays of each name in a Run", () => {
  assert.equal(boxNameWords(BOX, "xmas_dun02/survival/drink"), "in a Run: replaces the runner's potion on HP (the setting potion_below then counts only in a box without it)");
  assert.equal(boxNameWords(BOX, "xmas_dun02/survival/fly_away"), "in a Run: replaces the runner's Fly Wing on HP and the runner's boss fly (a Battle Log boss line) (the setting fly_below then counts only in a box without it)");
  assert.equal(boxNameWords(BOX, "xmas_dun02/keys/heal"), null);
  assert.equal(boxNameWords(null, "xmas_dun02/survival/drink"), null);
});

// matpilot round 18 #4: on a phone the strip folds to ONE line; the IN A RUN part's short words lead
test("the strip's folded line: IN A RUN in a few words, else the first part", () => {
  const short = boxTabShort(BOX, "xmas_dun02", "survival");
  assert.equal(short, "3 events replace the runner's own");
  assert.equal(boxTabShort(BOX, "xmas_dun02", "exits"), "3 functions replace the runner's own");
  assert.equal(boxTabShort(BOX, "xmas_dun02", "keys"), null);
  assert.equal(boxTabShort(null, "xmas_dun02", "survival"), null);
  assert.match(boxTabShort({ ...BOX, playable: false }, "xmas_dun02", "survival") ?? "", /^once it can play, 3 events replace/);
  const parts = [
    { head: "MAP", text: "xmas_dun02" },
    { head: "IMPORTS", text: "its tabs (keys, survival) and Global" },
    { head: "IN A RUN", text: boxTabNote(BOX, "xmas_dun02", "survival", values) ?? "", short },
  ];
  assert.equal(stripFoldLine(parts), "IN A RUN: 3 events replace the runner's own · 2 more");
  assert.equal(stripFoldLine(parts.slice(0, 2)), "MAP: xmas_dun02 · 1 more");
  assert.equal(stripFoldLine([]), "");
  assert.equal(boxTabShort(BOX, "xmas_dun02", "knife"), "2 functions replace the runner's own");
});
