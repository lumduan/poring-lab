// The Maps page's pure parts (2026-11-10, docs/planning/world-map-flows.md): the session mock and
// its truthful Python, the graph (START -> Login -> Choose character -> the map blocks), placing a
// map node from the static data, and the playback over the simulator's trace (the committed
// fixture is the simulator's own output on the SYNTHETIC sample sheets; poring_flow's
// test_trace.py checks it is current).
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

import type { Trace } from "../flow/api.ts";
import type { Flow } from "../flow/ir.ts";
import { oneMapStarter, starterFlow } from "../flow/starter.ts";
import { addMapNode, blockName, centreCell, oneMapFlow, targetGuess } from "./build.ts";
import { type Ctx, drawGrid, drawScene, FALLBACK_COLOURS, mapSize } from "./draw.ts";
import { mapsGraph } from "./graph.ts";
import { along, approximatePlay, beatAt, beatText, buildTimeline, overlayAt, poseAt, runChecks, trailAt, walkSeconds } from "./play.ts";
import { ACCOUNTS, DEFAULT_SESSION, parseSession, SERVERS, sessionLength, sessionProblems, sessionPython, sessionSteps } from "./session.ts";

const trace = JSON.parse(readFileSync(new URL("./fixtures/starter_trace.json", import.meta.url), "utf8")) as Trace;

// --- the session ---------------------------------------------------------------------------------
// (that the list is config/environments.yaml's, ids and statuses in order, is checked on the host
// by packages/poring_flow/tests/test_maps_page.py: the container serves services/frontend only)
test("only the lab's rAthena can be chosen; every other server says why not", () => {
  assert.deepEqual(SERVERS.filter((s) => s.automatable).map((s) => s.id), ["lab-rathena"]);
  for (const s of SERVERS) assert.ok(s.why.length > 20, s.id);
  assert.deepEqual(SERVERS.filter((s) => s.status === "forbidden").map((s) => s.automatable), [false, false]);
});

test("a stored session is checked field by field; a credential has nowhere to go", () => {
  assert.deepEqual(parseSession(null), DEFAULT_SESSION);
  assert.deepEqual(parseSession("{not json"), DEFAULT_SESSION);
  assert.deepEqual(parseSession(JSON.stringify({ server: "community-bot-testing", account: "root", slot: 99, char: "<b>" })), DEFAULT_SESSION);
  assert.deepEqual(parseSession(JSON.stringify({ server: "lab-rathena", account: "player", slot: 3, char: "Rogue One", password: "x" })), {
    server: "lab-rathena",
    account: "player",
    slot: 3,
    char: "Rogue One",
  });
  assert.deepEqual(Object.keys(DEFAULT_SESSION).sort(), ["account", "char", "server", "slot"]);
  assert.deepEqual(ACCOUNTS.map((a) => a.id), ["gm", "player"]);
});

test("session problems: another server, or a flow for another server", () => {
  assert.deepEqual(sessionProblems(DEFAULT_SESSION, "lab-rathena"), []);
  assert.equal(sessionProblems({ ...DEFAULT_SESSION, server: "official-ro-thai" }, "lab-rathena").length, 2);
  assert.match(sessionProblems(DEFAULT_SESSION, "elsewhere")[0], /the flow targets elsewhere/);
});

test("the session's Python names the bot's real calls, marked as a mock, in short comment lines", () => {
  const py = sessionPython(DEFAULT_SESSION);
  assert.match(py, /^# A MOCK/);
  assert.match(py, /ro_agent\.py login gm/);
  assert.match(py, /from ro_agent import enter_game, session/);
  assert.match(py, /to_char_select\(agent, screen, ACCOUNT\)/);
  assert.match(py, /enter_game\(agent, screen, ACCOUNT\)\n/);
  assert.ok(!/password\s*=|PASSWORD|_USER\b/.test(py), "no credential name or value in the code");
  const slot = sessionPython({ ...DEFAULT_SESSION, account: "player", slot: 3, char: "Rogue One" });
  assert.match(slot, /# slot 3: selected first/);
  assert.match(slot, /enter_game\(agent, screen, ACCOUNT, char="Rogue One"\)/);
  for (const line of [...py.split("\n"), ...slot.split("\n")]) if (line.trim().startsWith("#")) assert.ok(line.length <= 46, line);
  // the steps it simulates, with mock times
  const steps = sessionSteps(DEFAULT_SESSION);
  assert.deepEqual(steps.map((s) => s.node), ["start", "login", "character"]);
  assert.equal(steps[2].t1, sessionLength());
  assert.match(steps[1].call, /^to_char_select/);
});

// --- the graph ---------------------------------------------------------------------------------------
test("the graph: START -> Login -> Choose character -> the start block, then the exits", () => {
  const g = mapsGraph(starterFlow(), DEFAULT_SESSION);
  assert.deepEqual(g.nodes.map((n) => n.id), ["start", "login", "character", "block:town", "block:field"]);
  const e = (id: string) => g.edges.find((x) => x.id === id);
  assert.equal(e("session:enter")?.target, "block:town");
  assert.equal(e("exit:town.2")?.data.kind, "npc_warp");
  assert.equal(e("exit:field.1")?.data.kind, "item_warp");
  assert.equal(e("respawn:field")?.data.kind, "death_respawn"); // the save point is set in town
  assert.ok(!g.edges.some((x) => x.data.kind === "attach"), "event nodes stay on /flows");
  // the map nodes sit right of the session; a dragged position wins
  const town = g.nodes.find((n) => n.id === "block:town")!;
  assert.ok(town.position.x > g.nodes.find((n) => n.id === "character")!.position.x);
  assert.deepEqual(mapsGraph(starterFlow(), DEFAULT_SESSION, { "block:town": { x: 5, y: 6 } }).nodes[3].position, { x: 5, y: 6 });
  const plain = mapsGraph(oneMapStarter(), DEFAULT_SESSION);
  assert.deepEqual(plain.nodes.map((n) => n.id), ["start", "login", "character", "main"]);
});

// --- placing a map node ------------------------------------------------------------------------------
test("a map node from the static data: its name, the centre-most entry, a target guess", () => {
  assert.equal(blockName("xmas_dun02", new Set()), "xmas_dun02");
  assert.equal(blockName("xmas_dun02", new Set(["xmas_dun02"])), "xmas_dun02_2");
  assert.equal(blockName("1@tower", new Set()), "tower");
  const rows = ["#####", "#...#", "#.#.#", "#...#", "#####"];
  assert.deepEqual(centreCell(rows), [2, 1]); // (2, 2) is blocked; nearest, lower y first
  assert.equal(centreCell(null), null);
  const spawns = [
    { mob: 9101, count: 20, boss: false },
    { mob: 9102, count: 1, boss: false }, // a single spawn: ignored (a mini boss, often)
    { mob: 9109, count: 1, boss: true },
    { mob: 9105, count: 3, boss: false },
  ];
  assert.deepEqual(targetGuess(spawns), { targets: [9101, 9105], ignore: [9102, 9109] });
  const r = addMapNode(starterFlow(), "syn_cave", { rows, spawns });
  assert.ok(r.ok);
  const b = r.flow.workflow!.blocks.at(-1)!;
  assert.equal(b.name, "syn_cave");
  assert.deepEqual(b.entries[0].at, { kind: "cell", map: "syn_cave", x: 2, y: 1 });
  assert.equal(b.main[0].kind, "repeat");
  assert.equal(b.main.at(-1)?.kind, "stop");
  const bare = addMapNode(starterFlow(), "syn_town", null);
  assert.ok(bare.ok && bare.flow.workflow!.blocks.at(-1)!.entries[0].at === null);
  assert.ok(!addMapNode(oneMapStarter(), "syn_cave", null).ok);
  assert.ok(!addMapNode(starterFlow(), "no spaces", null).ok);
  const one = oneMapFlow("syn_cave", { rows, spawns });
  assert.ok(one.ok);
  assert.equal(one.flow.name, "syn_cave_flow");
  assert.equal(one.flow.workflow!.start_block, "syn_cave");
});

// --- the playback ------------------------------------------------------------------------------------
test("the timeline: the session's mock steps, then the simulator's steps in order", () => {
  const tl = buildTimeline(trace, sessionSteps(DEFAULT_SESSION));
  assert.equal(tl.offset, sessionLength());
  assert.equal(tl.approximate, false);
  assert.deepEqual(tl.beats.slice(0, 3).map((b) => b.node), ["start", "login", "character"]);
  assert.ok(tl.beats.every((b, i) => i === 0 || b.t0 >= tl.beats[i - 1].t0));
  assert.deepEqual(tl.maps, ["town_1", "field_1"]);
  assert.equal(tl.end, sessionLength() + trace.t_end_s);
  // before the flow starts, the character stands at the start entry
  const p0 = poseAt(tl, 0.5)!;
  assert.equal(p0.node, "start");
  const p1 = poseAt(tl, tl.offset + 0.01)!;
  assert.deepEqual([p1.map, Math.round(p1.x), Math.round(p1.y)], ["town_1", 40, 40]);
  // mid-walk, between two cells of the route; at its end, on its last cell
  const walk = tl.beats.find((b) => b.kind === "walk")!;
  const mid = poseAt(tl, (walk.t0 + walk.t1) / 2)!;
  assert.equal(mid.node, "block:town");
  assert.ok(mid.x > 40 && mid.x < 55);
  const end = poseAt(tl, walk.t1)!;
  assert.deepEqual([end.x, end.y], walk.step!.cells!.at(-1));
  // after the NPC warp: on the field, at its entry
  const exit = tl.beats.find((b) => b.kind === "exit")!;
  const after = poseAt(tl, exit.t1)!;
  assert.deepEqual([after.map, after.x, after.y], ["field_1", 30, 30]);
  assert.equal(beatAt(tl, -1), -1);
});

test("a walk is interpolated by RO's step costs", () => {
  const cells: [number, number][] = [[0, 0], [1, 0], [2, 1]];
  assert.ok(Math.abs(walkSeconds(cells) - 0.362) < 1e-9);
  assert.deepEqual(along(cells, 0), { x: 0, y: 0, index: 0 });
  const p = along(cells, 0.15 / 0.362);
  assert.ok(Math.abs(p.x - 1) < 1e-9 && Math.abs(p.y) < 1e-9);
  assert.deepEqual(along(cells, 1), { x: 2, y: 1, index: 2 });
});

test("the map shows the monster met, its fight, its loot, and the NPC talked to", () => {
  const tl = buildTimeline(trace, sessionSteps(DEFAULT_SESSION));
  const fight = tl.beats.find((b) => b.kind === "fight" && b.step?.at)!;
  const engage = tl.beats[fight.i - 1];
  assert.equal(engage.kind, "walk");
  const near = overlayAt(tl, engage.t0 + 0.05, "field_1").monsters;
  assert.equal(near.length, 1);
  assert.equal(near[0].state, "near");
  assert.deepEqual([near[0].x, near[0].y], fight.step!.at);
  const mid = overlayAt(tl, (fight.t0 + fight.t1) / 2, "field_1").monsters[0];
  assert.equal(mid.state, "fight");
  assert.ok(mid.hp > 0.3 && mid.hp < 0.7);
  const down = overlayAt(tl, fight.t1 + 0.1, "field_1");
  assert.equal(down.monsters[0].state, "down");
  assert.equal(down.loot.length, 1);
  assert.equal(overlayAt(tl, fight.t1 + 0.1, "town_1").monsters.length, 0); // another map
  const talk = tl.beats.find((b) => b.kind === "talk")!;
  const o = overlayAt(tl, talk.t0 + 0.1, "town_1", { mobs: {}, npcs: { n_kafra: "Kafra (synthetic)" }, items: {}, options: {} });
  assert.equal(o.talking, "n_kafra");
  assert.match(o.bubble!.text, /^set the save point with Kafra \(synthetic\) \(n_kafra\) at \(56, 44\)/);
  // the trail: the walks done, and the one in progress split at the character
  const tr = trailAt(tl, (engage.t0 + engage.t1) / 2, "field_1");
  assert.ok(tr.walking && tr.ahead);
  assert.equal(trailAt(tl, tl.end, "town_1").walking, null);
});

test("words and checks", () => {
  const tl = buildTimeline(trace, sessionSteps(DEFAULT_SESSION));
  const labels = { mobs: { "9101": "slime A (synthetic)" }, npcs: {}, items: { "9002": "return wing (synthetic)" }, options: {} };
  const texts = tl.beats.map((b) => beatText(b, labels));
  assert.match(texts[1], /^Log in to lab-rathena with the lab GM account/);
  assert.ok(texts.some((t) => /^NPC warp → field \(field_1 30, 30\)$/.test(t)), texts.join("\n"));
  assert.ok(texts.some((t) => /^use return wing \(synthetic\) \(9002\) \(back to the save point\)$/.test(t)));
  assert.ok(texts.some((t) => /^meet (slime A \(synthetic\) \(9101\)|monster 91\d\d) at \(\d+, \d+\): fight, defeat, loot$/.test(t)));
  const checks = runChecks(tl, trace, starterFlow().workflow!.blocks.map((b) => ({ name: b.name, map: b.map.map })), "the simulated time ran out", 3);
  assert.deepEqual(checks.map((c) => c.ok), [true, true, true, true, true, true]);
  assert.match(checks.at(-1)!.text, /^Met \d+ monsters \(placed from seed 3\)$/);
});

test("an older backend (no play list): an approximate timeline from the walked segments", () => {
  const old = { ...trace } as Trace;
  delete old.play;
  delete old.play_capped;
  const tl = buildTimeline(old, null);
  assert.equal(tl.approximate, true);
  assert.equal(tl.offset, 0);
  assert.ok(tl.beats.some((b) => b.kind === "walk") && tl.beats.some((b) => b.kind === "exit"));
  assert.ok(tl.beats.every((b, i) => i === 0 || b.t0 >= tl.beats[i - 1].t1 - 1e-9));
  assert.ok(runChecks(tl, old, [], "x", null).some((c) => /^Approximate/.test(c.text)));
  assert.deepEqual(approximatePlay([], []), []);
});

test("every map block of the starter is a Flow the graph can show", () => {
  const f: Flow = starterFlow();
  assert.equal(mapsGraph(f, DEFAULT_SESSION).nodes.filter((n) => n.type === "map").length, f.workflow!.blocks.length);
});

// --- the map view's drawing (lib/maps/draw.ts) on a recording context -----------------------------
type Call = { fn: string; args: unknown[]; fill: unknown; stroke: unknown };
function recorder(): { ctx: Ctx; calls: Call[] } {
  const calls: Call[] = [];
  const state: Record<string, unknown> = { fillStyle: "", strokeStyle: "", lineWidth: 1, lineJoin: "miter", lineCap: "butt", globalAlpha: 1, font: "" };
  const ctx = new Proxy(state, {
    get(t, k: string) {
      if (k in t) return t[k];
      return (...args: unknown[]) => {
        calls.push({ fn: k, args, fill: t.fillStyle, stroke: t.strokeStyle });
        return k === "measureText" ? { width: 10 * String(args[0]).length } : undefined;
      };
    },
    set(t, k: string, v) {
      t[k] = v;
      return true;
    },
  }) as unknown as Ctx;
  return { ctx, calls };
}

test("the grid: one dark area, then each row's walkable runs in grey (y grows north)", () => {
  const { ctx, calls } = recorder();
  drawGrid(ctx, ["..#", "#.."], 3, 2, 4, FALLBACK_COLOURS);
  assert.deepEqual(calls.map((c) => [c.fn, ...c.args, c.fill]), [
    ["fillRect", 0, 0, 12, 8, FALLBACK_COLOURS.wall],
    ["fillRect", 0, 4, 8, 4, FALLBACK_COLOURS.floor], // row y = 0 is the BOTTOM one
    ["fillRect", 4, 0, 8, 4, FALLBACK_COLOURS.floor],
  ]);
  const plain = recorder();
  drawGrid(plain.ctx, null, 3, 2, 4, FALLBACK_COLOURS);
  assert.equal(plain.calls.length, 1);
  assert.equal(plain.calls[0].fill, FALLBACK_COLOURS.empty);
});

test("the scene at a time: the character where the timeline puts it, the monster, the bubble", () => {
  const tl = buildTimeline(trace, sessionSteps(DEFAULT_SESSION));
  const sheet = { town: false, size: [100, 100] as [number, number], npcs: [], warps: [], spawns: [] };
  const fight = tl.beats.find((b) => b.kind === "fight" && b.step?.at)!;
  const t = (fight.t0 + fight.t1) / 2;
  const { ctx, calls } = recorder();
  const out = drawScene(ctx, { map: "field_1", w: 100, h: 100, scale: 3, sheet, tl, time: t, labels: null, savePoint: null, colours: FALLBACK_COLOURS });
  const p = poseAt(tl, t)!;
  assert.deepEqual(out.bot, { x: p.x * 3 + 1.5, y: (99 - p.y) * 3 + 1.5 });
  assert.equal(out.monsters, 1);
  assert.ok(calls.some((c) => c.fn === "arc" && c.args[0] === fight.step!.at![0] * 3 + 1.5));
  assert.ok(calls.some((c) => c.fn === "fillText" && /^mob 91\d\d$/.test(String(c.args[0]))));
  // on another map nothing of the run is drawn; before a run only the static data
  assert.equal(drawScene(recorder().ctx, { map: "town_1", w: 120, h: 90, scale: 3, sheet: null, tl, time: t, labels: null, savePoint: null, colours: FALLBACK_COLOURS }).bot, null);
  const talk = tl.beats.find((b) => b.kind === "talk")!;
  const town = { ...sheet, size: [120, 90] as [number, number], npcs: [{ key: "n_kafra", x: 56, y: 44, menu: [], kafra: null }] };
  const s2 = drawScene(recorder().ctx, { map: "town_1", w: 120, h: 90, scale: 2, sheet: town, tl, time: talk.t0 + 0.1, labels: null, savePoint: { map: "town_1", cell: [40, 40] }, colours: FALLBACK_COLOURS });
  assert.match(s2.bubble ?? "", /^set the save point with NPC n_kafra at \(56, 44\)/);
  assert.equal(drawScene(recorder().ctx, { map: "town_1", w: 120, h: 90, scale: 2, sheet: town, tl: null, time: 0, labels: null, savePoint: null, colours: FALLBACK_COLOURS }).bot, null);
  assert.deepEqual(mapSize("field_1", null, null, tl).known, false);
  assert.deepEqual(mapSize("x", ["...", "..."], null, null), { w: 3, h: 2, known: true });
});
