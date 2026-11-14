// WHAT THE BOX PLAYS in a box run, and which run settings that replaces (matpilot round 17 N1).
//
// Heal and the Fly Wing each showed two thresholds that differ: the survival tab's drink
// (hp_percent() < 30; ➡️ < 50 since 2026-11-14, live-blocks.md 10) and fly_away (sees_boss() or
// hp_percent() < 25), and the settings "heal at HP under 40 %" and "Fly Wing at HP under 20 %".
// Neither page said which one a live run uses. The truth (live-blocks.md stage 2, dungeon@9.49;
// stages 3 and 4a): in a BOX run (Run of a project: the live block player) the box's events and role
// functions decide what they play, and the runner's own handler for it is off (its box_plays); the
// setting then counts only in a box without that event. The rule is the engine's, ONE place: POST
// /flows/lint's `box` (poring_flow.live.takeovers, from hunt_plan, the same plan the live player
// plays), per map node. ➡️ 2026-11-14 (live-blocks.md 12): the settings are SETTING BLOCKS of the
// project (settings.ts; Before Run's settings panel went with the runner page): the words name the
// setting block, and the lint's info on that block says the same. Pure functions; every word renders
// as text.
import { SETTING_BY_NAME, type SettingValue, shownValue, unitOf } from "./settings.ts";

/** One thing the box plays and what of the runner's it replaces (live.takeovers' rows). */
export type BoxTakeover = {
  play: string; // live.PLAYS: potion, fly_hp, boss_fly, weight_home, respawn, knife, home_end, model, recipes
  settings: string[]; // the run settings (scripts/flow_config.py FIELDS) it replaces
  replaces: string; // the runner's own handler, in words
  kind: "event" | "function" | "model";
  by: string | null; // the event, function or model that plays it (null: none, e.g. no confirmation)
  path: string | null; // where it is written ("xmas_dun02/survival/drink")
  when?: string | null; // an event's condition in words ("HP < 50 %")
  until?: string | null;
  steps?: string; // a role function's steps in words ("a click at 645,481")
};
/** A map node's box (POST /flows/lint `box[node]`); `playable` false: Run refuses as it is. */
export type BoxDoc = { plays: string[]; takeovers: BoxTakeover[]; stays: string[]; playable: boolean };

/** "heal at HP under 40 % (potion_below)": a setting's words and the value the next Run takes. */
function settingText(name: string, values: Record<string, SettingValue> | null): string {
  const f = SETTING_BY_NAME.get(name);
  if (!f) return name;
  const v = values?.[name];
  const u = unitOf(f);
  return v === undefined ? `${f.words} (${f.var})` : `${f.words} ${shownValue(f, v)}${u ? ` ${u}` : ""} (${f.var})`;
}

/** PURE: the note on a tab whose events or functions the box plays in a Run of this project
 * ("survival": drink, fly_away, bag_full), or null: what each replaces of the runner's, with the
 * setting block it replaces and its value, and what stays the runner's (the HP-rate fly). `node`
 * and `tab`: the tab shown (its rows' paths start "<node>/<tab>/"); `values`: the node's settings
 * (settings.ts nodeSettings). */
export function boxTabNote(box: BoxDoc | null | undefined, node: string, tab: string, values: Record<string, SettingValue> | null): string | null {
  if (!box) return null;
  const here = box.takeovers.filter((t) => t.path !== null && t.path.startsWith(`${node}/${tab}/`));
  if (!here.length) return null;
  const byName = new Map<string, BoxTakeover[]>();
  for (const t of here) byName.set(t.by ?? "", [...(byName.get(t.by ?? "") ?? []), t]);
  const parts = [...byName].map(([by, ts]) => {
    const each = ts.map((t) => `${t.replaces}${t.settings.length ? ` (the setting ${t.settings.map((s) => settingText(s, values)).join("; ")})` : ""}`);
    return `${by} replaces ${[...new Set(each)].join(" and ")}`;
  });
  const flies = here.some((t) => t.play === "fly_hp");
  const stays = flies && box.stays.length ? ` The HP-rate fly stays the runner's (the settings ${box.stays.map((s) => settingText(s, values)).join(" ")}).` : "";
  const head = box.playable ? "In a Run of this project these play inside the hunt core, and the runner's own are off" : "Once this box can play (Run refuses it as it is), these play inside the hunt core, and the runner's own are off";
  return `${head}: ${parts.join("; ")}.${stays}`;
}

/** PURE (matpilot round 18 #4): the IN A RUN note in one short line, for the strip folded on a
 * phone: "3 events replace the runner's own" (each name counted once, by its takeover's kind);
 * null when boxTabNote has no note for the tab. */
export function boxTabShort(box: BoxDoc | null | undefined, node: string, tab: string): string | null {
  if (!box) return null;
  const kinds = new Map<string, BoxTakeover["kind"]>();
  for (const t of box.takeovers) if (t.path !== null && t.by && t.path.startsWith(`${node}/${tab}/`)) kinds.set(t.by, t.kind);
  if (!kinds.size) return null;
  const count = (word: BoxTakeover["kind"]) => [...kinds.values()].filter((k) => k === word).length;
  const words = (["event", "function", "model"] as const).map((k) => [count(k), k] as const).filter(([n]) => n > 0).map(([n, k]) => `${n} ${k}${n === 1 ? "" : "s"}`);
  return `${box.playable ? "" : "once it can play, "}${words.join(" and ")} replace${kinds.size === 1 ? "s" : ""} the runner's own`;
}

/** PURE: one name's words in a node's list of tabs and names (the /maps inspector), when the box
 * plays it in a Run of this project: "in a Run: replaces the runner's potion on HP (the setting
 * potion_below then counts only in a box without it)"; null: the box plays nothing of it. */
export function boxNameWords(box: BoxDoc | null | undefined, path: string): string | null {
  const here = (box?.takeovers ?? []).filter((t) => t.path === path);
  if (!here.length) return null;
  const settings = [...new Set(here.flatMap((t) => t.settings))];
  const replaces = [...new Set(here.map((t) => t.replaces))].join(" and ");
  return `in a Run: replaces ${replaces}${settings.length ? ` (the setting ${settings.join(", ")} then counts only in a box without it)` : ""}`;
}
