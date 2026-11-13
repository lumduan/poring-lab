// SIMULATE for a runner flow (lib/flow/runner_sim.ts): the example tells its story with the code's
// numbers, every step names a block of the description, and each modelled rule behaves as its
// dungeon_hunt.py pure function does (the potion and the Fly Wing of sustain(), hp_dropped(),
// --garm-confirm's streak, kill_gapped(), --loot-first, value_target's score, the safe end).
import assert from "node:assert/strict";
import { test } from "node:test";

import { effectiveConfig, withConfig } from "./config.ts";
import { allNodes, type RunnerDoc } from "./runner.ts";
import { EXAMPLE, hpDropped, killGapped, type Moment, num, pick, quietKillEnds, rateHpS, type Scenario, score, simulate } from "./runner_sim.ts";
import { XMAS_DUN02_ROGUE as DOC } from "./runners/xmas_dun02_rogue.gen.ts";

const ids = new Set(allNodes(DOC).map((n) => n.id));
const sc = (moments: Moment[], values: Record<string, number> = EXAMPLE.values): Scenario => ({ name: "t", note: "", values, moments });
const blocks = (r: { steps: { block: string }[] }) => r.steps.map((s) => s.block);

test("the example run tells its story: a choice by worth, two kills, a loot step, a potion, two escapes, the safe end", () => {
  const r = simulate(DOC, EXAMPLE);
  assert.equal(r.end, "time");
  assert.equal(r.kills, 2);
  assert.equal(r.picks, 2);
  assert.equal(r.potions, 1);
  assert.equal(r.wings, 2); // the Garm Baby, the swarm
  for (const s of r.steps) assert.ok(ids.has(s.block), `${s.block} is a block of the description`);
  for (let i = 1; i < r.steps.length; i++) assert.ok(r.steps[i].t >= r.steps[i - 1].t, "steps in time order");
  const b = blocks(r);
  for (const id of ["identity", "stock", "start_here", "look", "choose", "strike", "lock_on", "kill", "fight_over", "loot", "explore", "walk_click", "garm", "garm_fly", "drink", "lead", "wing_hp_fly", "end", "home"]) assert.ok(b.includes(id), id);
  // the first choice is by worth, not by distance: the farther mystcase beats the near cookie
  const first = r.steps.find((s) => s.block === "choose");
  assert.match(first?.text ?? "", /^the mystcase scores/);
  assert.equal(r.steps[r.steps.length - 1].block, "home");
});

test("its numbers are the doc's: a larger KILL_GAP_HITS makes the first kill wait", () => {
  const base = simulate(DOC, EXAMPLE);
  const firstKill = base.steps.find((s) => s.block === "kill");
  assert.equal(firstKill?.t, 7.8); // 6 hits, then 1.7 s without one
  const d = structuredClone(DOC) as RunnerDoc;
  d.params.KILL_GAP_HITS.value = 7;
  const r = simulate(d, EXAMPLE);
  assert.notEqual(r.steps.find((s) => s.block === "kill")?.t, 7.8);
  assert.throws(() => num(DOC, "NO_SUCH_NUMBER"));
});

test("value_target: worth / (1 + distance / D0_PX), ties to the nearer", () => {
  const d0 = num(DOC, "vt.D0_PX");
  assert.equal(score(300, 2 * d0, d0), 100);
  assert.equal(score(100, 0, d0), 100);
  const got = pick([{ species: "a", dist_px: 2 * d0, cells: 8 }, { species: "b", dist_px: 0, cells: 0 }], { a: 300, b: 100 }, d0);
  assert.equal(got?.box.species, "b"); // equal scores: the nearer one
  assert.equal(pick([], { a: 1 }, d0), null);
  assert.equal(pick([{ species: "zzz", dist_px: 0, cells: 0 }], { "*": 7 }, d0)?.score, 7); // an unknown species takes the mean
});

test("kill_gapped: at least KILL_GAP_HITS hits, then MORE than KILL_GAP_S without one", () => {
  const g = num(DOC, "KILL_GAP_S");
  const h = num(DOC, "KILL_GAP_HITS");
  assert.equal(killGapped(h, g + 0.01, g, h), true);
  assert.equal(killGapped(h, g, g, h), false);
  assert.equal(killGapped(h - 1, g * 3, g, h), false);
});

test("sustain: the Fly Wing first and alone; a slow fall under potion_below is a potion", () => {
  const fly = num(DOC, "strategy.fly_below");
  const low = simulate(DOC, sc([{ t: 1, hp: fly - 0.01 }]));
  assert.ok(blocks(low).includes("wing_hp_fly"));
  assert.ok(!blocks(low).includes("drink"));
  const pb = num(DOC, "strategy.potion_below");
  const slow = simulate(DOC, sc([{ t: 1, hp: pb + 0.02 }, { t: 3, hp: pb - 0.01 }]));
  assert.ok(blocks(slow).includes("drink"));
  assert.ok(!blocks(slow).includes("wing_hp_fly"));
  // the swarm escape: falling faster than fly_rate HP/s while under fly_rate_below
  const maxHp = num(DOC, "char.max_hp");
  const under = num(DOC, "strategy.fly_rate_below") - 0.02;
  const drop = (num(DOC, "strategy.fly_rate") * 1.5) / maxHp; // in one second
  const swarm = simulate(DOC, sc([{ t: 1, hp: under + drop }, { t: 2, hp: under }]));
  assert.ok(blocks(swarm).includes("wing_hp_fly"));
  assert.ok((rateHpS([[1, 0.5], [2, 0.4]], 2, 1000) ?? 0) > 99);
  assert.equal(rateHpS([[2, 0.4]], 2, 1000), null);
});

test("hp_dropped: HP_DROP_PTS points within HP_DROP_S starts a fight with no box", () => {
  const pts = num(DOC, "HP_DROP_PTS");
  const s = num(DOC, "HP_DROP_S");
  assert.equal(hpDropped([[0, 0.9], [0.5, 0.9 - pts / 100]], 0.5, pts, s), true);
  assert.equal(hpDropped([[0, 0.9], [0.5, 0.9 - (pts - 1) / 100]], 0.5, pts, s), false);
  const r = simulate(DOC, sc([{ t: 4, hp: 0.95 }, { t: 4.5, hp: 0.95 - pts / 100 }]));
  assert.ok(r.steps.some((x) => x.block === "fight_on" && /her HP fell/.test(x.text)));
});

test("--garm-confirm: a Garm Baby box in consecutive detections; one alone, or a gap, waits", () => {
  const need = num(DOC, "cmd.garm_confirm");
  assert.equal(need, 2);
  const one = simulate(DOC, sc([{ t: 1, hp: 1, boxes: [], garm: true }, { t: 2, hp: 1, boxes: [] }, { t: 3, hp: 1, boxes: [], garm: true }]));
  assert.ok(!blocks(one).includes("garm_fly"));
  const two = simulate(DOC, sc([{ t: 1, hp: 1, boxes: [], garm: true }, { t: 2, hp: 1, boxes: [], garm: true }]));
  assert.ok(blocks(two).includes("garm_fly"));
  // then no box fights for BOSS_AVOID_S
  const avoid = num(DOC, "BOSS_AVOID_S");
  const box = [{ species: "cookie", dist_px: 60, cells: 2 }];
  const after = simulate(DOC, sc([{ t: 1, hp: 1, boxes: [], garm: true }, { t: 2, hp: 1, boxes: [], garm: true }, { t: 3, hp: 1, boxes: box }, { t: 2 + avoid + 1, hp: 1, boxes: box }]));
  const fights = after.steps.filter((x) => x.block === "fight_on");
  assert.equal(fights.length, 1);
  assert.ok(fights[0].t > 2 + avoid);
});

test("--loot-first: right after a kill a box alone waits for the loot step; a hit does not", () => {
  const box = [{ species: "cookie", dist_px: 60, cells: 1 }];
  const kill: Moment[] = [{ t: 1, hp: 1, boxes: box }, ...[1.5, 2, 2.5, 3, 3.5].map((t) => ({ t, hp: 1, our_hit: true })), { t: 5.2, hp: 1 }];
  const r = simulate(DOC, sc([...kill, { t: 5.4, hp: 1, boxes: box, items: 1 }]));
  assert.ok(blocks(r).includes("fight_over"));
  const held = r.steps.find((x) => x.t === 5.4 && x.block === "fight_on");
  assert.match(held?.text ?? "", /loot comes first/);
  assert.ok(r.steps.some((x) => x.t === 5.4 && x.block === "loot"));
  const hit = simulate(DOC, sc([...kill, { t: 5.4, hp: 1, boxes: box, hit_on_us: true }]));
  assert.ok(hit.steps.some((x) => x.t === 5.4 && x.block === "fight_on" && /a hit on her/.test(x.text)));
});

test("quiet_kill_ends with --loot-first: only a kill of THIS fight, within 3 s", () => {
  assert.equal(quietKillEnds([10], 12, 5), true);
  assert.equal(quietKillEnds([10], 13, 5), false);
  assert.equal(quietKillEnds([10], 12, 11), false); // the fight began after that kill
  assert.equal(quietKillEnds([], 12, 0), false);
});

test("a far target is approached first; a near one is struck at once", () => {
  const far = num(DOC, "APPROACH_CELLS");
  const r = simulate(DOC, sc([{ t: 1, hp: 1, boxes: [{ species: "cookie", dist_px: 400, cells: far }] }]));
  assert.ok(blocks(r).includes("approach_walk"));
  assert.ok(!blocks(r).includes("strike"));
  const near = simulate(DOC, sc([{ t: 1, hp: 1, boxes: [{ species: "cookie", dist_px: 40, cells: 1 }] }]));
  assert.ok(blocks(near).includes("strike"));
  // out of the server's one-click reach: no fight at all (--reach-check)
  const unreach = simulate(DOC, sc([{ t: 1, hp: 1, boxes: [{ species: "cookie", dist_px: 40, cells: 1, reachable: false }] }]));
  assert.ok(!blocks(unreach).includes("fight_on"));
});

test("Batt's Knife swap (in the base): on at idle, back to the dagger on the cue and before every escape", () => {
  const r = simulate(DOC, EXAMPLE);
  const b = blocks(r);
  assert.ok(b.includes("press_knife"));
  assert.ok(b.includes("knife_hit"));
  assert.ok(r.steps.some((s) => s.block === "press_dagger" && /steal cue/.test(s.text)));
  for (const i of b.flatMap((x, k) => (x === "wing_hp_fly" || x === "garm_fly" ? [k] : []))) {
    const before = r.steps.slice(0, i).filter((s) => s.block === "press_knife" || s.block === "press_dagger").pop();
    assert.ok(!before || before.block === "press_dagger", "never a Fly Wing with the Knife on");
  }
  assert.ok(b.includes("knife_on_call") && b.includes("knife_back_call")); // the main loop's calls light up
  assert.ok(b.indexOf("knife_on_call") < b.indexOf("press_knife"));
  assert.ok(!blocks(simulate(DOC, EXAMPLE, { knife: false })).includes("press_knife")); // the comparison without it
  // the person's Knife settings (2026-11-13): Batt's "F4, wait 200 ms, F5" is a Knife time of 0.2 s
  const c = DOC.config;
  assert.ok(c);
  const vals = { ...effectiveConfig(c, null, DOC.map).values, knife_key: "F6", dagger_key: "F7", knife_max_s: 0.2 };
  const fast = simulate(withConfig(DOC, c, vals), EXAMPLE);
  assert.ok(fast.steps.some((x) => x.block === "press_knife" && x.text.includes("F6")));
  assert.ok(fast.steps.some((x) => x.block === "press_dagger" && x.text.includes("F7")));
  assert.ok(fast.steps.some((x) => x.block === "press_dagger" && /0\.2 s with no steal/.test(x.text)), "the 0.2 s Knife time ends the Knife");
});

test("the time box ends the loop; the safe end flies only when still hit or under END_FLY_BELOW", () => {
  const end = num(DOC, "cmd.minutes") * 60;
  const calm = simulate(DOC, sc([{ t: end - 10, hp: 0.9 }, { t: end + 5, hp: 0.1 }]));
  assert.equal(calm.wings, 0); // the moment after the time box never happens
  assert.ok(blocks(calm).includes("end"));
  const hot = simulate(DOC, sc([{ t: end - 1, hp: 0.9, hit_on_us: true }]));
  assert.ok(blocks(hot).includes("end_fly"));
});
