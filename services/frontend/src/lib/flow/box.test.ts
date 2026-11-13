// matpilot round 17 N1: heal and the Fly Wing each showed two thresholds (the survival tab's events
// and Before Run's settings) and neither page said which one a live run uses. The pages now say it
// from the engine's takeovers (POST /flows/lint `box`, poring_flow.live.takeovers; its own test is
// services/backend/tests/test_live_player.py). The doc below is that function's output for the one
// box (project_xmas_dun02.json), the settings the generated runner doc's defaults.
import assert from "node:assert/strict";
import { test } from "node:test";

import { type BoxDoc, boxedSettings, boxNameWords, boxTabNote } from "./box.ts";
import { type ConfigDoc, effectiveConfig } from "./config.ts";
import { XMAS_DUN02_ROGUE as DOC } from "./runners/xmas_dun02_rogue.gen.ts";

const ev = (play: string, settings: string[], replaces: string, by: string, tab: string, when: string, until: string | null = null) => ({ play, settings, replaces, kind: "event" as const, by, path: `xmas_dun02/${tab}/${by}`, when, until });
const fnRow = (play: string, settings: string[], replaces: string, by: string | null, tab: string, steps?: string) => ({ play, settings, replaces, kind: "function" as const, by, path: by ? `xmas_dun02/${tab}/${by}` : null, ...(steps ? { steps } : {}) });
const BOX: BoxDoc = {
  plays: ["boss_fly", "fly_hp", "home_end", "knife", "model", "potion", "recipes", "respawn", "weight_home"],
  takeovers: [
    ev("potion", ["potion_below"], "the runner's potion on HP", "drink", "survival", "HP < 30 %", "HP >= 31 %"),
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
const C = DOC.config as ConfigDoc;
const values = effectiveConfig(C, null, "xmas_dun02").values;
const ALONE = "this value is the runner's alone (the old Run path, a box without that event)";

test("Before Run's settings rows say which of them this project's box replaces, and by what", () => {
  const b = boxedSettings(BOX);
  assert.deepEqual(Object.keys(b).sort(), ["fly_below", "potion_below", "respawn_at", "respawn_confirm_at", "weight_home"]);
  assert.equal(b.potion_below, `in this project: replaced by the box's drink event (HP < 30 %, until HP >= 31 %); ${ALONE}`);
  assert.equal(b.fly_below, `in this project: replaced by the box's fly_away event (a boss is seen or HP < 25 %); ${ALONE}`);
  assert.equal(b.weight_home, `in this project: replaced by the box's bag_full event (weight >= 50 %); ${ALONE}`);
  assert.equal(b.respawn_at, "in this project: replaced by the box's respawn_button (a click at 645,481); this value is the runner's alone (the old Run path, a box without that function)");
  // the HP-rate fly stays the runner's: no word on its rows
  assert.equal(b.fly_rate, undefined);
  assert.equal(b.fly_rate_below, undefined);
  // a respawn without a confirmation function presses none
  const noOk: BoxDoc = { ...BOX, takeovers: BOX.takeovers.map((t) => (t.settings[0] === "respawn_confirm_at" ? { ...t, by: null, path: null, steps: "no confirmation function: none is pressed" } : t)) };
  assert.match(boxedSettings(noOk).respawn_confirm_at, /replaced by nothing: the box presses no confirmation/);
  // a box that cannot play says so; no box, no words
  assert.match(boxedSettings({ ...BOX, playable: false }).potion_below, /^in this project, once its box can play \(Run refuses it as it is\): replaced by/);
  assert.deepEqual(boxedSettings(null), {});
  assert.deepEqual(boxedSettings({ plays: [], takeovers: [], stays: ["fly_rate", "fly_rate_below"], playable: true }), {});
});

test("the survival tab's note: each event, what it replaces with Before Run's setting and value, and what stays", () => {
  assert.equal(values.potion_below, 0.4); // the runner's own defaults the note quotes
  const note = boxTabNote(BOX, "xmas_dun02", "survival", C, values);
  assert.equal(
    note,
    "In a Run of this project these play inside the hunt core, and the runner's own are off: " +
      "drink replaces the runner's potion on HP (Before Run: heal at HP under 40 %); " +
      "fly_away replaces the runner's Fly Wing on HP (Before Run: Fly Wing at HP under 20 %) and the runner's boss fly (a Battle Log boss line); " +
      "bag_full replaces the runner's weight exit on a read weight (an unread weight drawn red keeps its own rule) (Before Run: go home when the bag is over 50 %). " +
      "The HP-rate fly stays the runner's (Before Run: or HP falling faster than 150 HP/s while under 50 %).",
  );
  // the exits tab: the respawn's two functions with their points
  assert.match(boxTabNote(BOX, "xmas_dun02", "exits", C, values) ?? "", /^In a Run of this project .*respawn_button replaces the runner's clicks on the death dialog \(Before Run: respawn button at [0-9]+,[0-9]+\); respawn_ok replaces .*fly_home replaces the runner's Butterfly Wing press at the end\.$/);
  // a tab the box plays nothing of, no box: no note; without the settings: their words only
  assert.equal(boxTabNote(BOX, "xmas_dun02", "keys", C, values), null);
  assert.equal(boxTabNote(null, "xmas_dun02", "survival", C, values), null);
  assert.match(boxTabNote(BOX, "xmas_dun02", "survival", null, null) ?? "", /drink replaces the runner's potion on HP \(Before Run: potion_below\)/);
});

test("the /maps inspector's tabs list says what the box plays of each name in a Run", () => {
  assert.equal(boxNameWords(BOX, "xmas_dun02/survival/drink"), "in a Run: replaces the runner's potion on HP (Before Run's potion_below then applies to the runner alone)");
  assert.equal(boxNameWords(BOX, "xmas_dun02/survival/fly_away"), "in a Run: replaces the runner's Fly Wing on HP and the runner's boss fly (a Battle Log boss line) (Before Run's fly_below then applies to the runner alone)");
  assert.equal(boxNameWords(BOX, "xmas_dun02/keys/heal"), null);
  assert.equal(boxNameWords(null, "xmas_dun02/survival/drink"), null);
});
