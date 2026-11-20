import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import type { Project } from "./project.ts";
import { effectiveLimitS, huntMinutes, parseHoursMinutes, storyTime, timeWords, withTimeLimit } from "./runoptions.ts";

const fixture = (name: string) => JSON.parse(readFileSync(new URL(`./fixtures/${name}.json`, import.meta.url), "utf8")) as Project;

test("time words a person reads", () => {
  assert.equal(timeWords(0), "no time limit");
  assert.equal(timeWords(1_800), "30 min");
  assert.equal(timeWords(7_200), "2 h");
  assert.equal(timeWords(5_400), "1 h 30 min");
  assert.equal(timeWords(172_800), "2 days");
  assert.equal(timeWords(90_000), "1 day 1 h");
});

test("ONE time limit: the project's, and every hunt block minutes follows it (Batt 2026-11-19)", () => {
  // the cookie twin is hash-pinned with the old 7200 s and a minutes block of 120
  const old = fixture("project_xmas_dun02_cookie_noswap");
  assert.equal(old.max_runtime_s, 7_200);
  assert.deepEqual(huntMinutes(old), [{ where: "xmas_dun02/start", minutes: 120 }]);
  assert.equal(effectiveLimitS(old), 7_200);
  const none = withTimeLimit(old, 0);
  assert.equal(none.max_runtime_s, 0);
  assert.deepEqual(huntMinutes(none), []);
  assert.equal(effectiveLimitS(none), 0);
  assert.equal(old.max_runtime_s, 7_200); // a copy: the original is untouched
  const three = withTimeLimit(old, 10_800);
  assert.equal(effectiveLimitS(three), 10_800); // not cut at the block's old 120 min
  assert.throws(() => withTimeLimit(old, -1));
  // a box whose minutes block is shorter than its project time stops at the block's
  const short = { ...withTimeLimit(old, 0), max_runtime_s: 7_200 } as Project;
  short.nodes[0].tabs.find((t) => t.name === "start")!.vars.minutes = { kind: "lit", value: 30 };
  assert.equal(effectiveLimitS(short), 1_800);
});

test("a custom time typed as hours and minutes", () => {
  assert.equal(parseHoursMinutes("", ""), 0);
  assert.equal(parseHoursMinutes("36", "30"), 131_400);
  assert.equal(parseHoursMinutes("1", "60"), null);
  assert.equal(parseHoursMinutes("x", ""), null);
  assert.equal(parseHoursMinutes("9000", ""), null); // above the 365-day sanity cap
});

test("a story line's time from the run's start", () => {
  assert.equal(storyTime(null), "");
  assert.equal(storyTime(65), "1:05");
  assert.equal(storyTime(3_600), "60:00");
});

test("what she does: the Run's time or the server's clock (Batt 2026-11-20)", async () => {
  const { storyStamp, STORY_CLOCKS } = await import("./liverun.ts");
  assert.deepEqual([...STORY_CLOCKS], ["run", "clock"]);
  assert.equal(storyStamp({ t_s: 105, words: "x", at: "17:19:06" }, "run"), "1:45");
  assert.equal(storyStamp({ t_s: 105, words: "x", at: "17:19:06" }, "clock"), "17:19:06");
  assert.equal(storyStamp({ t_s: 105, words: "x" }, "clock"), "1:45"); // an older helper: no clock
  assert.equal(storyStamp({ t_s: null, words: "x" }, "run"), "");
});
