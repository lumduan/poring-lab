// The Maps page's pure parts on the PROJECT (2026-11-13, docs/planning/project-model.md): the
// session nodes (login, choose character) and their mock timeline, the graph (the project's nodes,
// its session connections, the map nodes' exits), placing a map node from the static data, and the
// playback over the simulator's trace (the committed fixture is the simulator's own output on the
// SYNTHETIC sample sheets, whose blocks are the sample project's map node ids; poring_flow's
// test_maps_page.py checks it is current).
import assert from "node:assert/strict";
import { readdirSync, readFileSync } from "node:fs";
import { test } from "node:test";

import type { PlayStep, Trace } from "../flow/api.ts";
import { mapNodes, nodeById, sampleProject, xmasProject } from "../flow/project.ts";
import { sessionProject } from "../flow/testkit.ts";
import { addMapNode, centreCell, mapNodeFor, newNodePos, targetGuess } from "./build.ts";
import { type Ctx, drawGrid, drawScene, FALLBACK_COLOURS, fitScale, mapSize } from "./draw.ts";
import { activeEdgeAt, entryHandle, exitRuns, fitViewport, followCentre, mapsGraph, POS_SCALE, START_DX, START_DY, START_EDGE, START_ID, toScreen, toUnits } from "./graph.ts";
import { makeWanderers, shares, WANDER_CAP, wanderersAt } from "./wander.ts";
import { along, approximatePlay, beatAt, beatText, buildTimeline, overlayAt, poseAt, runChecks, traceHasSession, trailAt, walkSeconds } from "./play.ts";
import { CREDENTIALS, characterOf, loginOf, SERVERS, sessionLength, sessionOf, sessionProblems, sessionSteps, setCharacter, setLogin } from "./session.ts";

const trace = JSON.parse(readFileSync(new URL("./fixtures/starter_trace.json", import.meta.url), "utf8")) as Trace;
const SAMPLE_SESSION = sessionOf(sampleProject());

// --- the session nodes ---------------------------------------------------------------------------
// (that the list is config/environments.yaml's, ids and statuses in order, is checked on the host
// by packages/poring_flow/tests/test_maps_page.py: the container serves services/frontend only)
test("only the lab's rAthena can be chosen; every other server says why not", () => {
  assert.deepEqual(SERVERS.filter((s) => s.automatable).map((s) => s.id), ["lab-rathena"]);
  for (const s of SERVERS) assert.ok(s.why.length > 20, s.id);
  assert.deepEqual(SERVERS.filter((s) => s.status === "forbidden").map((s) => s.automatable), [false, false]);
});

test("the session is read from the login and character nodes: a server and a credential by NAME", () => {
  assert.deepEqual(SAMPLE_SESSION, { server: "lab-rathena", credential: "lab_gm", slot: null, char: "", login: "login", character: "character" });
  assert.deepEqual(CREDENTIALS.map((c) => [c.name, c.account]), [["lab_gm", "gm"], ["lab_player", "player"]]);
  const p = sampleProject();
  const a = setLogin(p, "login", { server: "lab-rathena", credential: "lab_player" });
  assert.ok(a.ok);
  assert.deepEqual(loginOf(nodeById(a.project, "login")), { server: "lab-rathena", credential: "lab_player", plain: true, found: true });
  assert.deepEqual(loginOf(nodeById(p, "login"))?.credential, "lab_gm", "the edit is pure");
  // a forbidden server, or anything that is not a NAME, is refused (a secret has nowhere to go)
  assert.equal(setLogin(p, "login", { server: "official-ro-thai", credential: "lab_gm" }).ok, false);
  assert.equal(setLogin(p, "login", { server: "lab-rathena", credential: "hunter2 pass!" }).ok, false);
  assert.equal(setLogin(p, "character", { server: "lab-rathena", credential: "lab_gm" }).ok, false);
  const c = setCharacter(p, "character", { slot: 3, name: "Rogue One" });
  assert.ok(c.ok);
  assert.deepEqual(characterOf(nodeById(c.project, "character")), { slot: 3, name: "Rogue One", plain: true, found: true });
  const back = setCharacter(c.project, "character", { slot: null, name: "" });
  assert.ok(back.ok);
  assert.deepEqual(back.project, p, "the remembered slot and the account's own: no params");
  assert.equal(setCharacter(p, "character", { slot: 99, name: "" }).ok, false);
  assert.equal(setCharacter(p, "character", { slot: null, name: "<b>" }).ok, false);
});

test("session problems: another server, a project for another server, an unknown credential", () => {
  assert.deepEqual(sessionProblems(SAMPLE_SESSION, "lab-rathena"), []);
  assert.equal(sessionProblems({ ...SAMPLE_SESSION, server: "official-ro-thai" }, "lab-rathena").length, 2);
  assert.match(sessionProblems(SAMPLE_SESSION, "elsewhere")[0], /the project targets elsewhere/);
  assert.match(sessionProblems({ ...SAMPLE_SESSION, credential: "someone" }, "lab-rathena")[0], /not one the lab knows/);
});

test("the mock session steps name the bot's real calls and belong to the project's nodes", () => {
  const steps = sessionSteps(SAMPLE_SESSION);
  assert.deepEqual(steps.map((s) => [s.step, s.node]), [["start", "login"], ["login", "login"], ["character", "character"]]);
  assert.equal(steps[2].t1, sessionLength());
  assert.match(steps[1].call, /^to_char_select\(agent, screen, "gm"\)$/);
  assert.match(steps[2].call, /^enter_game\(agent, screen, "gm"\)$/);
  const other = sessionSteps({ ...SAMPLE_SESSION, credential: "lab_player", slot: 3, char: "Rogue One" });
  assert.match(other[2].call, /enter_game\(agent, screen, "player", char="Rogue One"\)/);
  assert.match(other[2].text, /^Choose slot 3 \(Rogue One\)/);
  for (const s of steps) assert.ok(!/password\s*=|PASSWORD|_USER\b/.test(s.text + s.call), "no credential value or env name in the steps");
});

// --- the graph ---------------------------------------------------------------------------------------
test("the graph: the project's nodes, its session connections onto the start entry, the exits", () => {
  const g = mapsGraph(sampleProject());
  assert.deepEqual(g.nodes.map((n) => [n.id, n.type]), [["login", "login"], ["character", "character"], ["town", "map"], ["field", "map"], ["global", "global"]]);
  const e = (id: string) => g.edges.find((x) => x.id === id);
  assert.deepEqual([e("edge:login>character")?.sourceHandle, e("edge:login>character")?.targetHandle], ["out", "in"]);
  assert.deepEqual([e("edge:character>town")?.target, e("edge:character>town")?.targetHandle], ["town", entryHandle("spawn")]);
  // an edge runs from ITS exit's port onto the ENTRY it lands on (n8n-style ports)
  assert.deepEqual([e("exit:town/main/main.2")?.data.kind, e("exit:town/main/main.2")?.sourceHandle, e("exit:town/main/main.2")?.targetHandle], ["npc_warp", "x:town/main/main.2", "e:arrival"]);
  assert.deepEqual([e("exit:field/main/main.1")?.data.kind, e("exit:field/main/main.1")?.targetHandle], ["item_warp", "e:spawn"]);
  assert.deepEqual([e("respawn:field")?.data.kind, e("respawn:field")?.targetHandle], ["death_respawn", "e:spawn"]); // the save point is set in town
  assert.ok(!g.edges.some((x) => x.source === "global" || x.target === "global"), "Global has no edges");
  assert.deepEqual(g.notes, []);
  // the first map is marked; the saved positions are scaled to the screen (and back when dragged)
  assert.equal(g.nodes.find((n) => n.id === "town")?.data.kind === "map" && (g.nodes.find((n) => n.id === "town")?.data as { first: boolean }).first, true);
  assert.deepEqual(g.nodes.find((n) => n.id === "town")?.position, { x: 230 * POS_SCALE.x, y: 0 });
  assert.deepEqual(toUnits(toScreen({ x: 860, y: 220 })), { x: 860, y: 220 });
  // a broken session path says how to mend it
  const broken = sampleProject();
  broken.edges = broken.edges.filter((x) => x.from !== "character");
  assert.match(mapsGraph(broken).notes[0], /^The session path: the character node is not connected to a map/);
  // the Rogue's login-start project: login, character, two maps, Global; the wing home by its function
  const x = mapsGraph(sessionProject());
  assert.deepEqual(x.edges.map((y) => y.id), ["edge:login>character", "edge:character>xmas_dun02", "exit:xmas_dun02/main/main.2", "respawn:xmas_dun02"]);
  assert.ok(!x.nodes.some((n) => n.id === START_ID), "a login start: no START marker (its Login card says START)");
});

test("the START marker (the one box): a pill left of the start map, one connection onto its entry, not a project node", () => {
  const p = xmasProject();
  const g = mapsGraph(p);
  assert.deepEqual(g.nodes.map((n) => `${n.id}:${n.type}`), [`${START_ID}:start`, "xmas_dun02:map"]);
  const m = g.nodes.find((n) => n.id === "xmas_dun02")!;
  const s = g.nodes.find((n) => n.id === START_ID)!;
  assert.deepEqual(s.position, { x: m.position.x - START_DX, y: m.position.y + START_DY });
  assert.deepEqual(s.data, { kind: "start", to: "xmas_dun02", entry: "here" });
  assert.deepEqual(
    g.edges.map((e) => [e.id, e.source, e.target, e.sourceHandle, e.targetHandle, e.data.kind]),
    [[START_EDGE, START_ID, "xmas_dun02", "out", entryHandle("here"), "start"]],
  );
  assert.deepEqual(g.notes, []);
  assert.ok(!p.nodes.some((n) => n.id === START_ID), "never a project node");
  // the session project started on its map: the marker moves there; its session edges stay drawn
  const q = sessionProject();
  q.start = "geffen";
  const h = mapsGraph(q);
  assert.equal(h.edges.find((e) => e.id === START_EDGE)?.target, "geffen");
  assert.equal(h.edges.find((e) => e.id === START_EDGE)?.targetHandle, entryHandle("save"));
  assert.equal(exitRuns(null, h.edges).size, 0);
});

test("the playback lights the connection or exit it last went along; exits are counted", () => {
  const g = mapsGraph(sampleProject());
  const tl = buildTimeline(trace, sessionSteps(SAMPLE_SESSION));
  const at = (kind: string, from = 0) => tl.beats.findIndex((b, i) => i >= from && b.kind === kind);
  assert.equal(activeEdgeAt(tl, 1, g.edges), null, "logging in: no connection yet");
  assert.equal(activeEdgeAt(tl, 2, g.edges), "edge:login>character");
  assert.equal(activeEdgeAt(tl, 3, g.edges), "edge:character>town", "on the first map: the way in");
  assert.equal(activeEdgeAt(tl, at("exit"), g.edges), "exit:town/main/main.2", "an IR 2 path (town.2) is matched by from / kind / to");
  assert.deepEqual([...exitRuns(trace, g.edges)].sort(), [["exit:field/main/main.1", 1], ["exit:town/main/main.2", 2]]);
});

// --- placing a map node ------------------------------------------------------------------------------
test("a map node from the static data: its id, the centre-most entry, a target guess", () => {
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
  const r = addMapNode(sampleProject(), "syn_cave", { rows, spawns });
  assert.ok(r.ok);
  const n = nodeById(r.project, r.id);
  assert.ok(n && n.kind === "map");
  assert.equal(n.id, "syn_cave");
  assert.deepEqual(n.entries[0].at, { kind: "cell", map: "syn_cave", x: 2, y: 1 });
  assert.deepEqual(n.tabs.map((t) => t.name), ["main"], "IRON RULE: every node has a main");
  assert.equal(n.tabs[0].main![0].kind, "repeat");
  assert.equal(n.tabs[0].main!.at(-1)?.kind, "stop");
  assert.deepEqual(n.pos, { x: 690, y: 0 }, "right of the rightmost map");
  assert.deepEqual(newNodePos(r.project), { x: 920, y: 0 });
  const bare = mapNodeFor(sampleProject(), "syn_town", null);
  assert.equal(bare.entries[0].at, null);
  assert.deepEqual(bare.tabs[0].main, [{ kind: "stop", reason: "done" }]);
  assert.ok(!addMapNode(sampleProject(), "no spaces", null).ok);
  const twice = addMapNode(r.project, "syn_cave", null);
  assert.ok(twice.ok && twice.id === "syn_cave_2");
});

// --- the playback ------------------------------------------------------------------------------------
test("the timeline: the session's mock steps, then the simulator's steps in order", () => {
  const tl = buildTimeline(trace, sessionSteps(SAMPLE_SESSION));
  assert.equal(tl.offset, sessionLength());
  assert.equal(tl.approximate, false);
  assert.deepEqual(tl.beats.slice(0, 3).map((b) => b.node), ["login", "login", "character"]);
  assert.ok(tl.beats.every((b, i) => i === 0 || b.t0 >= tl.beats[i - 1].t0));
  assert.deepEqual(tl.maps, ["town_1", "field_1"]);
  assert.equal(tl.end, sessionLength() + trace.t_end_s);
  // before the map steps start, the character stands at the start entry
  const p0 = poseAt(tl, 0.5)!;
  assert.equal(p0.node, "login");
  const p1 = poseAt(tl, tl.offset + 0.01)!;
  assert.deepEqual([p1.map, Math.round(p1.x), Math.round(p1.y)], ["town_1", 40, 40]);
  // mid-walk, between two cells of the route; at its end, on its last cell
  const walk = tl.beats.find((b) => b.kind === "walk")!;
  const mid = poseAt(tl, (walk.t0 + walk.t1) / 2)!;
  assert.equal(mid.node, "town", "a beat belongs to the map NODE (the trace's block)");
  assert.ok(mid.x > 40 && mid.x < 55);
  const end = poseAt(tl, walk.t1)!;
  assert.deepEqual([end.x, end.y], walk.step!.cells!.at(-1));
  // after the NPC warp: on the field, at its entry
  const exit = tl.beats.find((b) => b.kind === "exit")!;
  const after = poseAt(tl, exit.t1)!;
  assert.deepEqual([after.map, after.x, after.y], ["field_1", 30, 30]);
  assert.equal(beatAt(tl, -1), -1);
});

test("a trace with its OWN login and character steps is played as it is (no mock)", () => {
  const own = structuredClone(trace);
  const steps = [
    { kind: "login", t0: 0, t1: 5, block: "login", map: null, outcome: "ok" },
    { kind: "character", t0: 5, t1: 8, block: "character", map: null, outcome: "ok" },
  ] as unknown as PlayStep[];
  own.play = [...steps, ...(own.play ?? []).map((st) => ({ ...st, t0: st.t0 + 8, t1: st.t1 + 8 }))];
  assert.ok(traceHasSession(own) && !traceHasSession(trace));
  const tl = buildTimeline(own, sessionSteps(SAMPLE_SESSION));
  assert.equal(tl.offset, 0);
  assert.deepEqual(tl.beats.slice(0, 2).map((b) => [b.kind, b.node]), [["session", "login"], ["session", "character"]]);
  assert.equal(tl.beats[2].node, "town");
  assert.equal(beatText(tl.beats[0], null), "Log in (simulated)");
  assert.deepEqual([poseAt(tl, 8)?.map, Math.round(poseAt(tl, 8)?.x ?? 0)], ["town_1", 40]);
  const checks = runChecks(tl, own, mapNodes(sampleProject()).map((n) => ({ id: n.id, map: n.map.map })), "x", null);
  assert.equal(checks[0].text, "Logged in and entered the game (simulated, nothing ran)");
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
  const tl = buildTimeline(trace, sessionSteps(SAMPLE_SESSION));
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
  const tl = buildTimeline(trace, sessionSteps(SAMPLE_SESSION));
  const labels = { mobs: { "9101": "slime A (synthetic)" }, npcs: {}, items: { "9002": "return wing (synthetic)" }, options: {} };
  const texts = tl.beats.map((b) => beatText(b, labels));
  assert.match(texts[1], /^Log in to lab-rathena with the credential lab_gm \(the lab GM account/);
  assert.ok(texts.some((t) => /^NPC warp → field \(field_1 30, 30\)$/.test(t)), texts.join("\n"));
  // the sample's wing is the function butterfly_wing (press F9)
  assert.ok(texts.some((t) => /^call butterfly_wing\(\): press F9 \(the Butterfly Wing: back to the save point\)$/.test(t)), texts.join("\n"));
  assert.ok(texts.some((t) => /^meet (slime A \(synthetic\) \(9101\)|monster 91\d\d) at \(\d+, \d+\): fight, defeat, loot$/.test(t)));
  const checks = runChecks(tl, trace, mapNodes(sampleProject()).map((n) => ({ id: n.id, map: n.map.map })), "the simulated time ran out", 3);
  assert.deepEqual(checks.map((c) => c.ok), [true, true, true, true, true, true]);
  assert.match(checks[1].text, /^Reached town \(town_1\): 2 visits$/);
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
  const tl = buildTimeline(trace, sessionSteps(SAMPLE_SESSION));
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

// --- round 2 (2026-11-10, matpilot's headless-Chrome review) ----------------------------------------
test("the map fills its stage: the largest scale that fits, its aspect kept", () => {
  // a 922 x 360 stage: town_1 (120 x 90) is as tall as the stage, a square 260 map too
  assert.equal(fitScale(924, 364, 120, 90), 4);
  assert.ok(Math.abs(fitScale(924, 364, 260, 260) * 260 - 360) < 1e-9);
  assert.ok(fitScale(2000, 400, 100, 100) * 100 <= 396); // never past the height
  assert.equal(fitScale(0, 0, 100, 100), 1); // not measured yet
  assert.equal(fitScale(10, 10, 2048, 2048), 0.5);
});

test("the Maps components draw no glyph Chromium on Linux lacks, and label their icon buttons", () => {
  const dir = new URL("../../components/maps/", import.meta.url);
  for (const name of readdirSync(dir).filter((f) => f.endsWith(".tsx"))) {
    const src = readFileSync(new URL(name, dir), "utf8");
    // the media-control block U+23E9..U+23FA (two of them rendered as empty boxes) and every
    // character that defaults to an emoji (it needs an emoji font)
    assert.ok(!/[\u23e9-\u23fa]|\p{Emoji_Presentation}/u.test(src), `${name} draws a glyph that may be a box`);
  }
  const bar = readFileSync(new URL("SidePanels.tsx", dir), "utf8");
  for (const label of ["Back to the start", "The step before", "The next step"]) assert.ok(bar.includes(`aria-label="${label}"`), label);
  assert.match(bar, /aria-label=\{playing \? "Pause" : "Play"\}/);
});

// --- round 3 (2026-11-10, matpilot's re-run) -------------------------------------------------------
test("the graph's smallest text stays >= 11 px at the fit's 0.85 zoom; the playback bar is opaque", () => {
  const css = readFileSync(new URL("../../components/maps/maps.css", import.meta.url), "utf8").replace(/\/\*[\s\S]*?\*\//g, "");
  const graph = /^(\.mp-node|\.mp-title|\.mp-mock|\.mp-line|\.mp-muted|\.mp-key|\.mp-call|\.mp-button|\.mp-status|\.mp-run|\.mp-pill|\.mp-edge-label|\.mp-name|\.mp-names-tab|\.mp-override|\.maps-graph)\b/;
  let checked = 0;
  for (const m of css.matchAll(/([^{}]+)\{([^{}]*)\}/g)) {
    const selectors = m[1].split(",").map((x) => x.trim());
    const size = /font-size:\s*([\d.]+)rem/.exec(m[2]);
    if (!size || !selectors.some((x) => graph.test(x))) continue;
    checked++;
    assert.ok(Number(size[1]) * 16 * 0.85 >= 11, `${m[1].trim()}: ${size[1]}rem is ${(Number(size[1]) * 16 * 0.85).toFixed(1)} px at zoom 0.85`);
  }
  assert.ok(checked >= 8, `only ${checked} graph rules with a font size`);
  const bar = /\.mat-playback\s*\{([^}]*)\}/.exec(css)![1];
  assert.match(bar, /background:\s*var\(--surface\);/);
  assert.match(css, /\.maps-page\[data-run="true"\] \.maps-bar-spacer\s*\{[^}]*height:\s*calc\(2\.5rem \+ 16px \+ env\(safe-area-inset-bottom, 0px\)\)/);
});

// --- round 4 (2026-11-10): the graph's view never animates over a zero-size (folded) box ---------
test("the fit: within the zoom limits, START at the left when too wide; null for no box or NaN", () => {
  const bounds = { x: 0, y: 70, width: 1300, height: 300 };
  const wide = fitViewport({ width: 1400, height: 400 }, bounds, 0.85, 1.2, 24);
  assert.ok(wide && !wide.overflow && wide.viewport.zoom <= 1.2 && wide.viewport.zoom >= 0.85);
  const narrow = fitViewport({ width: 390, height: 320 }, bounds, 0.85, 1.2, 24)!;
  assert.equal(narrow.overflow, true);
  assert.deepEqual(narrow.viewport.zoom, 0.85);
  assert.equal(narrow.viewport.x, 24); // the graph's left edge (START) at the pad
  // folded (display: none) or not laid out: nothing to fit
  assert.equal(fitViewport({ width: 0, height: 0 }, bounds, 0.85, 1.2, 24), null);
  assert.equal(fitViewport({ width: 40, height: 40 }, bounds, 0.85, 1.2, 24), null); // smaller than the pads
  assert.equal(fitViewport({ width: 800, height: 400 }, { ...bounds, width: 0 }, 0.85, 1.2, 24), null);
  for (const bad of [NaN, Infinity]) {
    assert.equal(fitViewport({ width: bad, height: 400 }, bounds, 0.85, 1.2, 24), null);
    assert.equal(fitViewport({ width: 800, height: 400 }, { ...bounds, x: bad }, 0.85, 1.2, 24), null);
  }
});

test("following the playback's node: a pan only when it is out of view and every number is finite", () => {
  const box = { width: 800, height: 300 };
  const vp = { x: 0, y: 0, zoom: 1 };
  assert.equal(followCentre(box, vp, { x: 100, y: 50, width: 220, height: 120 }), null); // in view
  assert.deepEqual(followCentre(box, vp, { x: 900, y: 50, width: 220, height: 120 }), { x: 1010, y: 110, zoom: 1 });
  // the folded graph: a 0 x 0 box never pans (an animated pan over it made the zoom NaN)
  assert.equal(followCentre({ width: 0, height: 0 }, vp, { x: 900, y: 50, width: 220, height: 120 }), null);
  for (const bad of [NaN, Infinity, -Infinity]) {
    assert.equal(followCentre(box, { ...vp, zoom: bad }, { x: 900, y: 50, width: 220, height: 120 }), null);
    assert.equal(followCentre(box, vp, { x: bad, y: 50, width: 220, height: 120 }), null);
    assert.equal(followCentre({ width: bad, height: 300 }, vp, { x: 900, y: 50, width: 220, height: 120 }), null);
  }
  assert.equal(followCentre(box, { ...vp, zoom: 0 }, { x: 900, y: 50, width: 220, height: 120 }), null);
  // every pan target it does give is finite
  const c = followCentre(box, { x: -500, y: 20, zoom: 0.85 }, { x: 40, y: 70, width: 210, height: 140 })!;
  assert.ok([c.x, c.y, c.zoom].every(Number.isFinite));
});

// --- round 5 (2026-11-10, Batt: "make it an option"): the map's other monsters, decoration --------
// a synthetic 40 x 30 field with a wall and a pillar
const FIELD = Array.from({ length: 30 }, (_, y) => Array.from({ length: 40 }, (_, x) => ((x === 20 && y < 25) || (x >= 5 && x <= 7 && y >= 5 && y <= 7) ? "#" : ".")).join(""));
const SPAWNS = [
  { mob: 9101, count: 20, boss: false },
  { mob: 9102, count: 15, boss: false, area: [25, 2, 35, 12] as [number, number, number, number] },
  { mob: 9109, count: 1, boss: true },
];
const walk = (x: number, y: number) => FIELD[y]?.[x] === ".";

test("other monsters: capped, in proportion, at least one of each", () => {
  assert.deepEqual(shares(SPAWNS), [20, 15, 1]);
  const big = shares([{ mob: 1, count: 20 }, { mob: 2, count: 20 }, { mob: 3, count: 35 }, { mob: 4, count: 50 }, { mob: 5, count: 1 }, { mob: 6, count: 1 }]);
  assert.ok(big.reduce((a, b) => a + b, 0) <= WANDER_CAP);
  assert.ok(big.every((k) => k >= 1));
  assert.equal(makeWanderers(FIELD, [{ mob: 1, count: 500 }], 1, "syn").list.length, WANDER_CAP);
  assert.equal(makeWanderers(null, SPAWNS, 1, "syn").list.length, 0); // no walk grid: none
});

test("other monsters: deterministic from the seed, always on walkable cells, inside their areas", () => {
  const a = makeWanderers(FIELD, SPAWNS, 7, "syn");
  const b = makeWanderers(FIELD, SPAWNS, 7, "syn");
  const c = makeWanderers(FIELD, SPAWNS, 8, "syn");
  assert.equal(a.list.length, 36);
  assert.deepEqual(a.list.map((w) => [...w.path]), b.list.map((w) => [...w.path]));
  assert.notDeepEqual(a.list.map((w) => [...w.path]), c.list.map((w) => [...w.path]));
  for (const w of a.list) {
    for (let i = 0; i < w.n; i++) {
      const [x, y] = [w.path[2 * i], w.path[2 * i + 1]];
      assert.ok(walk(x, y), `(${x}, ${y})`);
      if (w.mob === 9102) assert.ok(x >= 25 && x <= 35 && y >= 2 && y <= 12, `9102 left its area: (${x}, ${y})`);
      if (i > 0) {
        const [px, py] = [w.path[2 * i - 2], w.path[2 * i - 1]];
        assert.ok(Math.max(Math.abs(x - px), Math.abs(y - py)) <= 1); // one cell a step
        if (x !== px && y !== py) assert.ok(walk(x, py) && walk(px, y), "a diagonal through a corner");
      }
    }
  }
  // every frame: the same positions for the same time, each rounding to a walkable cell
  for (let t = 0; t < 120; t += 0.37) {
    const k = wanderersAt(a, t);
    const k2 = wanderersAt(b, t);
    assert.equal(k, k2);
    for (let i = 0; i < k; i++) {
      assert.deepEqual([a.out[i].x, a.out[i].y], [b.out[i].x, b.out[i].y]);
      assert.ok(walk(Math.round(a.out[i].x), Math.round(a.out[i].y)), `t=${t}`);
    }
  }
  const out = a.out; // made once: a frame writes into it, no new objects
  wanderersAt(a, 3.3);
  assert.equal(a.out, out);
  assert.equal(wanderersAt(a, NaN), 0);
});

test("other monsters are never where the run's monster stands, at its meeting time", () => {
  const st = makeWanderers(FIELD, SPAWNS, 3, "syn");
  const all = wanderersAt(st, 10);
  const c: [number, number] = [Math.round(st.out[0].x), Math.round(st.out[0].y)];
  const k = wanderersAt(st, 10, [c]);
  assert.ok(k < all);
  for (let i = 0; i < k; i++) assert.ok(Math.max(Math.abs(Math.round(st.out[i].x) - c[0]), Math.abs(Math.round(st.out[i].y) - c[1])) > 1);
  // through the drawing, on the fixture's run: during every meeting, no decoration at the met cell
  const tl = buildTimeline(trace, sessionSteps(SAMPLE_SESSION));
  const rows = Array.from({ length: 100 }, () => ".".repeat(100)); // field_1's size; open
  const decor = makeWanderers(rows, [{ mob: 9101, count: 40 }], 3, "field_1");
  for (const f of tl.beats.filter((b) => b.kind === "fight" && b.step?.at)) {
    const at = f.step!.at!;
    for (let t = (f.step!.seen_t ?? f.step!.t0) + tl.offset; t <= f.t1; t += 0.1) {
      const r = drawScene(recorder().ctx, { map: "field_1", w: 100, h: 100, scale: 2, sheet: null, tl, time: t, labels: null, savePoint: null, colours: FALLBACK_COLOURS, decor });
      for (let i = 0; i < r.decor; i++) assert.ok(Math.max(Math.abs(Math.round(decor.out[i].x) - at[0]), Math.abs(Math.round(decor.out[i].y) - at[1])) > 1, `t=${t.toFixed(1)}`);
    }
  }
  // and it is drawing only: off (null) draws none, the run's words do not change
  assert.equal(drawScene(recorder().ctx, { map: "field_1", w: 100, h: 100, scale: 2, sheet: null, tl, time: 20, labels: null, savePoint: null, colours: FALLBACK_COLOURS, decor: null }).decor, 0);
});
