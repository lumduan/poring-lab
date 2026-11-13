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
import { mapNodes, nodeById, type Project, sampleProject, xmasProject } from "../flow/project.ts";
import { sessionProject } from "../flow/testkit.ts";
import { addMapNode, centreCell, mapNodeFor, NEW_NODE_DX, newNodePos, targetGuess } from "./build.ts";
import { type Ctx, drawGrid, drawScene, FALLBACK_COLOURS, fitScale, mapSize } from "./draw.ts";
import {
  activeEdgeAt,
  CARD_MAX_PX,
  cardGap,
  entryHandle,
  exitRuns,
  FIT_FLOOR,
  FIT_NAME,
  fitChoice,
  fitLeftOut,
  fitTitle,
  fitViewport,
  followCentre,
  LABEL_CLEAR_PX,
  LABEL_LANE_PX,
  LABEL_LINE_PX,
  LABEL_PAD_PX,
  LABEL_VPAD_PX,
  labelHeight,
  labelLines,
  labelPlace,
  labelWidth,
  mapsGraph,
  NARROW_PX,
  POS_SCALE,
  type Rect,
  type XY,
  START_DX,
  START_DY,
  START_EDGE,
  START_ID,
  toScreen,
  toUnits,
} from "./graph.ts";
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
  assert.deepEqual(n.pos, { x: 460 + NEW_NODE_DX, y: 0 }, "right of the rightmost map");
  assert.deepEqual(newNodePos(r.project), { x: 460 + 2 * NEW_NODE_DX, y: 0 });
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


// --- an exit's label between its cards (matpilot round 15 #13, round 16 #8) -----------------------
// Not measured in a browser here (the reviewer re-measures): the cards are drawn over the labels,
// so the label must fit the GAP between them. At round 16 "+ map geffen" put geffen 230 units
// right (437 px; a 400 px card left 37 px) and "death respawn (derived)" (208 px) was 83 % under.
const DEATH = "death respawn (derived)";

test("a label's width estimate covers what the browser measured (round 16: 208 px)", () => {
  assert.ok(labelWidth(DEATH) >= 208, String(labelWidth(DEATH)));
});

test("an exit's label shows what fits in the gap between its cards, never more", () => {
  assert.deepEqual(labelLines(DEATH, "death", 400), [DEATH], "a wide gap: one line");
  assert.deepEqual(labelLines(DEATH, "death", 160), ["death respawn", "(derived)"], "a lane: wrapped on words");
  assert.deepEqual(labelLines(DEATH, "death", 90), ["death"], "narrow: the short word");
  assert.deepEqual(labelLines(DEATH, "death", 437 - CARD_MAX_PX), [], "round 16's 37 px: no label (the card's port row says it)");
  assert.deepEqual(labelLines(DEATH, "death", Number.NaN), []);
  for (const gap of [30, 60, 90, 120, 160, 200, 240, 400]) {
    for (const l of labelLines(DEATH, "death", gap)) assert.ok(labelWidth(l) + 2 * LABEL_CLEAR_PX <= gap, `${gap}: ${l}`);
  }
});

test("the gap between two cards: either order, overlapping cards have none, an unmeasured card is unknown", () => {
  assert.deepEqual(cardGap({ x: 0, width: 400 }, { x: 570, width: 360 }), { gap: 170, centre: 485 });
  assert.deepEqual(cardGap({ x: 570, width: 360 }, { x: 0, width: 400 }), { gap: 170, centre: 485 }, "a loop back");
  assert.ok(cardGap({ x: 0, width: 400 }, { x: 0, width: 300 })!.gap <= 0, "one under the other");
  assert.equal(cardGap({ x: 0, width: 0 }, { x: 570, width: 360 }), null);
});

test("+ map leaves a lane beside the widest card for a two-line label", () => {
  const lane = NEW_NODE_DX * POS_SCALE.x - CARD_MAX_PX;
  assert.ok(lane >= LABEL_LANE_PX, String(lane));
  assert.deepEqual(labelLines(DEATH, "death", lane), ["death respawn", "(derived)"]);
  // the reviewer's case: geffen placed by + map beside the one box's xmas_dun02
  const r = addMapNode(xmasProject(), "geffen", null);
  assert.ok(r.ok);
  assert.equal(nodeById(r.project, "geffen")!.pos.x - nodeById(r.project, "xmas_dun02")!.pos.x, NEW_NODE_DX);
  // the card's widest is maps.css's .mp-card max-width
  const css = readFileSync(new URL("../../components/maps/maps.css", import.meta.url), "utf8").replace(/\/\*[\s\S]*?\*\//g, "");
  assert.match(css, new RegExp(`\\.mp-card \\{[^}]*max-width: ${CARD_MAX_PX}px`));
});

test("maps.css: port captions wrap (no cut entry line) and the phone graph has no minimap over the cards", () => {
  const css = readFileSync(new URL("../../components/maps/maps.css", import.meta.url), "utf8").replace(/\/\*[\s\S]*?\*\//g, "");
  const cap = /\.mp-port-cap \{([^}]*)\}/.exec(css)?.[1] ?? "";
  assert.doesNotMatch(cap, /nowrap|ellipsis/);
  assert.match(cap, /overflow-wrap: anywhere/);
  const phone = css.lastIndexOf("@media (max-width: 48rem)");
  assert.ok(phone > 0);
  assert.match(css.slice(phone), /\.maps-graph \.react-flow__minimap \{\s*display: none;/);
  assert.match(css, /\.mp-edge-label \{[^}]*white-space: nowrap/);
});

// --- round 17 (matpilot N6, N7, round 16 #8's leftover): what Fit shows, and the session labels ---
// Not measured in a browser here (the reviewer re-measures): the fixtures' real positions (the
// graph's own: units x POS_SCALE) with the cards' sizes stated, in flow pixels. START pill 80 x 32;
// xmas_dun02's card 380 x 360; a card "+ map" adds 400 x 300 (.mp-card's widest); the sample's Login
// 280 x 182 (the reviewer at 1.19: a 69 px gap under it = 58 flow px, a 188 px gap to town_1 = 158),
// Choose character 280 x 150, its map cards 380 x 340 (the reviewer's 1.19 = 972 / (437 + 380)),
// Global 380 x 250.
type Size = { width: number; height: number };
const SIZE: Record<string, Size> = { start: { width: 80, height: 32 }, login: { width: 280, height: 182 }, character: { width: 280, height: 150 }, map: { width: 380, height: 340 }, global: { width: 380, height: 250 } };
type Card = { id: string; type: string; start: boolean; rect: Rect };
function laidOut(p: Project, sizes: Record<string, Size> = {}): Card[] {
  return mapsGraph(p).nodes.map((n) => ({ id: n.id, type: n.type, start: n.data.kind === "login" && n.data.start, rect: { ...n.position, ...(sizes[n.id] ?? SIZE[n.type]) } }));
}
function union(rs: Rect[]): Rect | null {
  if (!rs.length) return null;
  const x = Math.min(...rs.map((r) => r.x));
  const y = Math.min(...rs.map((r) => r.y));
  return { x, y, width: Math.max(...rs.map((r) => r.x + r.width)) - x, height: Math.max(...rs.map((r) => r.y + r.height)) - y };
}
// what MapsCanvas passes: getNodesBounds of every node, of all but Global, of START + the maps
const setsOf = (cs: Card[]) => ({
  all: union(cs.map((c) => c.rect)),
  path: union(cs.filter((c) => c.type !== "global").map((c) => c.rect)),
  maps: union(cs.filter((c) => c.type === "map" || c.type === "start").map((c) => c.rect)),
});
const fitOf = (box: Size, cs: Card[]) => fitChoice(box, setsOf(cs), 0.85, 1.2, 24);
const titleOf = (box: Size, cs: Card[]) => {
  const c = fitOf(box, cs);
  return fitTitle(c, c ? fitLeftOut(cs, c.what) : [], cs.some((x) => x.type === "start"));
};
const EPS = 1e-9;
function inView(box: Size, vp: { x: number; y: number; zoom: number }, r: Rect): boolean {
  const x = r.x * vp.zoom + vp.x;
  const y = r.y * vp.zoom + vp.y;
  return x >= -EPS && y >= -EPS && x + r.width * vp.zoom <= box.width + EPS && y + r.height * vp.zoom <= box.height + EPS;
}
const mapsAndStart = (cs: Card[]) => cs.filter((c) => c.type === "map" || c.type === "start");
const PHONES: Size[] = [
  { width: 390, height: 700 },
  { width: 390, height: 320 }, // the phone graph's 20rem
];
const XMAS_SIZE = { xmas_dun02: { width: 380, height: 360 } };
const NEW_CARD = { width: 400, height: 300 };

test("N6: on a phone, START and every map card are in view after a load, after + map and after Fit", () => {
  const load = laidOut(xmasProject(), XMAS_SIZE);
  assert.deepEqual(load.map((c) => [c.id, c.rect.x, c.rect.y]), [[START_ID, -START_DX, START_DY], ["xmas_dun02", 0, 0]]);
  const added = addMapNode(xmasProject(), "geffen", null);
  assert.ok(added.ok);
  const plus = laidOut(added.project, { ...XMAS_SIZE, geffen: NEW_CARD });
  assert.deepEqual(plus.find((c) => c.id === "geffen")!.rect.x, NEW_NODE_DX * POS_SCALE.x, "300 units right");
  for (const box of PHONES) {
    assert.ok(box.width <= NARROW_PX);
    for (const [name, cs] of [["load", load], ["+ map", plus]] as const) {
      const c = fitOf(box, cs)!;
      assert.equal(c.what, "maps", `${name} ${box.height}`);
      assert.equal(c.scaled, true, `${name}: below the readable minimum, scaled down`);
      assert.equal(c.overflow, false);
      assert.ok(c.viewport.zoom < 0.85 && c.viewport.zoom >= FIT_FLOOR, String(c.viewport.zoom));
      for (const x of mapsAndStart(cs)) assert.ok(inView(box, c.viewport, x.rect), `${name} ${box.height}: ${x.id} in view at ${JSON.stringify(c.viewport)}`);
      // Fit is the same function on the same numbers: the same view as after the load
      assert.deepEqual(fitOf(box, cs), c);
    }
  }
  // round 17's measure on main was matrix(0.85, 151.5, 57.3) before and after Fit: geffen 0 % in view
  assert.ok(!inView(PHONES[0], { x: 151.5, y: 57.3, zoom: 0.85 }, plus.find((c) => c.id === "geffen")!.rect));
  assert.equal(fitOf(PHONES[0], load)!.viewport.zoom, (390 - 48) / 530, "START + xmas_dun02: 530 flow px into 342");
  assert.equal(titleOf(PHONES[0], plus), "Fit: every card, scaled down to fit this narrow view (zoom in to read).");
});

test("N6: a phone fits START + three maps at the floor; four start at START, at the readable size", () => {
  let p = xmasProject();
  const sizes: Record<string, Size> = { ...XMAS_SIZE };
  for (const m of ["geffen", "payon", "alberta"]) {
    const r = addMapNode(p, m, null);
    assert.ok(r.ok);
    p = r.project;
    sizes[m] = NEW_CARD;
  }
  const four = laidOut(p, sizes);
  const three = four.filter((c) => c.id !== "alberta");
  const box = PHONES[0];
  const c3 = fitOf(box, three)!;
  assert.ok(c3.scaled && c3.viewport.zoom >= FIT_FLOOR, String(c3.viewport.zoom));
  for (const x of three) assert.ok(inView(box, c3.viewport, x.rect), x.id);
  // 2260 flow px: below the floor -> from the left at 0.85 (the minimap is hidden on a phone: a finger pans)
  const c4 = fitOf(box, four)!;
  assert.deepEqual([c4.what, c4.scaled, c4.overflow, c4.viewport.zoom], ["maps", false, true, 0.85]);
  assert.equal(c4.viewport.x, 24 + START_DX * 0.85, "START at the pad");
  assert.equal(titleOf(box, four), "Fit: from START at the left, at a readable size (the cards do not all fit here: pan right).");
});

test("N7: the sample at 1440 fits its maps and says so; wider canvases take the run's path, then every card", () => {
  const cs = laidOut(sampleProject());
  assert.deepEqual(cs.map((c) => [c.id, c.rect.x, c.rect.y]), [["login", 0, 0], ["character", 0, 240], ["town", 437, 0], ["field", 874, 0], ["global", 437, 340]]);
  // the 1440 x 900 page's canvas: the path (1254 flow px) needs 0.775 (10.7 px text): the maps
  const at1440 = { width: 1020, height: 480 };
  const c = fitOf(at1440, cs)!;
  assert.deepEqual([c.what, c.scaled, c.overflow], ["maps", false, false]);
  assert.ok(Math.abs(c.viewport.zoom - 1.19) < 0.005, String(c.viewport.zoom));
  assert.deepEqual(fitLeftOut(cs, "maps"), ["Login (START)", "Choose character", "Global"]);
  assert.equal(titleOf(at1440, cs), "Fit the maps: the map cards. Login (START), Choose character and Global do not fit beside them at a readable size here: pan to them.");
  // a wider canvas: the run's path (Global under the maps left out), then every card
  const wider = { width: 1200, height: 480 };
  assert.equal(fitOf(wider, cs)!.what, "path");
  for (const x of cs.filter((y) => y.type !== "global")) assert.ok(inView(wider, fitOf(wider, cs)!.viewport, x.rect), x.id);
  assert.equal(titleOf(wider, cs), "Fit: the run's path. Global, shared by every node, does not fit beside it at a readable size here: pan to it.");
  const big = { width: 1400, height: 700 };
  assert.equal(fitOf(big, cs)!.what, "all");
  assert.equal(titleOf(big, cs), "Fit: every card.");
  // a wide canvas where not even the maps fit at 0.85: from the left at 0.85 (today's), never scaled
  const low = { width: 900, height: 300 };
  const l = fitOf(low, cs)!;
  assert.deepEqual([l.what, l.scaled, l.overflow, l.viewport.zoom, l.viewport.x], ["maps", false, true, 0.85, 24 - 437 * 0.85]);
  assert.equal(titleOf(low, cs), "Fit the maps: from the left, at a readable size (the map cards do not all fit here: pan right). Login (START), Choose character and Global are left out: pan to them.");
  // the sample on a phone: its two maps scaled down, every one in view
  const ph = fitOf(PHONES[0], cs)!;
  assert.deepEqual([ph.what, ph.scaled], ["maps", true]);
  for (const x of mapsAndStart(cs)) assert.ok(inView(PHONES[0], ph.viewport, x.rect), x.id);
  assert.equal(titleOf(PHONES[0], cs), "Fit the maps: every map card, scaled down to fit this narrow view (zoom in to read). Login (START), Choose character and Global are left out: pan to them.");
  // a map start: the START marker is in the fit, and Login is just Login
  const q = sampleProject();
  q.start = "town";
  const qs = laidOut(q);
  assert.equal(titleOf(at1440, qs), "Fit the maps: START and the map cards. Login, Choose character and Global do not fit beside them at a readable size here: pan to them.");
  assert.equal(fitTitle(null, [], false), FIT_NAME, "before the first fit: the button's name");
});

test("the fit chooser: null for no box or a bad number, an unusable set skipped", () => {
  const cs = laidOut(sampleProject());
  const sets = setsOf(cs);
  assert.equal(fitChoice({ width: 0, height: 0 }, sets, 0.85, 1.2, 24), null, "folded");
  assert.equal(fitChoice({ width: Number.NaN, height: 400 }, sets, 0.85, 1.2, 24), null);
  assert.equal(fitChoice({ width: 800, height: 400 }, {}, 0.85, 1.2, 24), null, "no card");
  assert.equal(fitChoice({ width: 800, height: 400 }, { all: { x: Number.NaN, y: 0, width: 10, height: 10 } }, 0.85, 1.2, 24), null);
  const c = fitChoice({ width: 1400, height: 700 }, { ...sets, all: { x: 0, y: 0, width: Infinity, height: 10 } }, 0.85, 1.2, 24)!;
  assert.equal(c.what, "path", "a bad set is skipped, the next one is tried");
  for (const v of [c.viewport.x, c.viewport.y, c.viewport.zoom]) assert.ok(Number.isFinite(v));
});

// the sample's two session edges, where React Flow's getSmoothStepPath puts its label point: the
// middle of the two ports pushed 20 px out (its offset); Login's port at its right middle, Choose
// character's head at its left middle, town_1's "spawn" entry ~150 px down its left side
const LOGIN = { x: 0, y: 0, width: 280, height: 182 };
const CHARACTER = { x: 0, y: 240, width: 280, height: 150 };
const TOWN = { x: 437, y: 0, width: 380, height: 340 };
const step = (s: XY, t: XY) => ({ x: s.x + 20 + (t.x - 20 - (s.x + 20)) / 2, y: (s.y + t.y) / 2 });
const labelBox = (p: { x: number; y: number; lines: string[] }): Rect => {
  const w = Math.max(...p.lines.map(labelWidth));
  const h = labelHeight(p.lines.length);
  return { x: p.x - w / 2, y: p.y - h / 2, width: w, height: h };
};
const clear = (l: Rect, c: Rect) => l.x + l.width <= c.x || c.x + c.width <= l.x || l.y + l.height <= c.y || c.y + c.height <= l.y;

test("the session labels: stacked cards, in the vertical gap on the line; side by side, wrapped into the gap", () => {
  // "log in, then choose": Choose character UNDER Login, a 58 px gap (the reviewer's 69 at 1.19)
  const lc = step({ x: 280, y: 91 }, { x: 0, y: 315 });
  assert.deepEqual(lc, { x: 140, y: 203 });
  const a = labelPlace(LOGIN, CHARACTER, "log in, then choose", "log in", lc)!;
  assert.deepEqual(a, { x: 140, y: 203, lines: ["log in, then choose"], how: "stacked" });
  const ab = labelBox(a);
  assert.ok(ab.y >= 182 + LABEL_CLEAR_PX && ab.y + ab.height <= 240 - LABEL_CLEAR_PX, JSON.stringify(ab));
  assert.ok(clear(ab, LOGIN) && clear(ab, CHARACTER));
  // "enter the game → spawn" (204 px): Choose character beside town_1, a 157 px gap
  const ct = step({ x: 280, y: 315 }, { x: 437, y: 150 });
  const b = labelPlace(CHARACTER, TOWN, "enter the game → spawn", "enter", ct)!;
  assert.deepEqual(b, { x: 280 + 157 / 2, y: ct.y, lines: ["enter the game", "→ spawn"], how: "beside" });
  for (const c of [LOGIN, CHARACTER, TOWN]) assert.ok(clear(labelBox(b), c));
  // the label's words come from the graph, with the one word it keeps where they do not fit
  const g = mapsGraph(sampleProject());
  const d = (id: string) => g.edges.find((e) => e.id === id)!.data;
  assert.deepEqual([d("edge:login>character"), d("edge:character>town")].map((x) => (x.kind === "session" ? [x.label, x.short] : [])), [["log in, then choose", "log in"], ["enter the game → spawn", "enter"]]);
});

test("a label in a vertical gap: as many lines as its height holds, the short word, else none", () => {
  const top = { x: 0, y: 0, width: 280, height: 100 };
  const under = (gap: number, width = 280) => ({ x: 0, y: 100 + gap, width, height: 100 });
  const at = (gap: number, width = 280) => labelPlace(top, under(gap, width), "log in, then choose", "log in", { x: 140, y: 100 + gap / 2 })!;
  assert.deepEqual(at(30).lines, [], "30 px: not one line (17 + 2 + 2 x 10)");
  assert.deepEqual(at(40).lines, ["log in, then choose"]);
  assert.deepEqual(at(40, 150).lines, ["log in"], "one line, too narrow for the words: the short word");
  assert.deepEqual(at(80, 150).lines, ["log in, then", "choose"], "two lines fit 80 px");
  assert.deepEqual(at(80, 60).lines, [], "narrower than the short word");
  // its line's midpoint outside the gap: the label stays in the gap
  const off = labelPlace(top, under(60), "log in, then choose", "log in", { x: 900, y: 40 })!;
  assert.deepEqual([off.x, off.y], [280, 100 + LABEL_CLEAR_PX + labelHeight(1) / 2]);
  // overlapping cards: none (the port rows say it); not measured, or a bad number: unknown
  assert.deepEqual(labelPlace(top, { ...top, x: 50, y: 50 }, "log in, then choose", "log in", { x: 0, y: 0 })!.lines, []);
  assert.equal(labelPlace({ ...top, height: 0 }, under(60), "x", "x", { x: 0, y: 0 }), null);
  assert.equal(labelPlace(top, under(60), "x", "x", { x: Number.NaN, y: 0 }), null);
  // whatever the gap and the cards, a placed label never lies over either card
  for (const gap of [0, 20, 30, 40, 58, 80, 120, 200]) {
    for (const w of [60, 150, 210, 280, 400]) {
      for (const [p, q] of [[top, under(gap, w)], [top, { x: 280 + gap, y: 30, width: w, height: 100 }], [{ x: 0, y: 0, width: w, height: 90 }, { x: w + gap, y: 200 + gap, width: 200, height: 90 }]] as const) {
        const r = labelPlace(p, q, "enter the game → spawn", "enter", { x: 100, y: 120 })!;
        if (r.lines.length) for (const c of [p, q]) assert.ok(clear(labelBox(r), c), `${gap} ${w} ${JSON.stringify(r)}`);
      }
    }
  }
});

test("maps.css: the label's line box is what labelPlace counts; the session cards are at most 280 px wide", () => {
  const css = readFileSync(new URL("../../components/maps/maps.css", import.meta.url), "utf8").replace(/\/\*[\s\S]*?\*\//g, "");
  const rule = /\.mp-edge-label \{([^}]*)\}/.exec(css)![1];
  const size = Number(/font-size: ([\d.]+)rem/.exec(rule)![1]) * 16;
  const lh = Number(/line-height: ([\d.]+);/.exec(rule)![1]);
  const [pv, ph] = /padding: ([\d.]+)rem ([\d.]+)rem/.exec(rule)!.slice(1).map((x) => Number(x) * 16);
  assert.ok(LABEL_LINE_PX + 1e-9 >= size * lh, `${LABEL_LINE_PX} < ${size * lh}`);
  assert.ok(LABEL_VPAD_PX >= 2 * pv && LABEL_PAD_PX >= 2 * ph);
  // the sample's side-by-side gap (437 - 280 = 157) holds "enter the game" because no session card is wider
  assert.match(css, /\.mp-node \{[^}]*max-width: 280px/);
  assert.doesNotMatch(/\.mp-session \{([^}]*)\}/.exec(css)![1], /width/);
  assert.match(css, /@media \(max-width: 48rem\)/);
  assert.equal(NARROW_PX, 48 * 16);
});

test("the canvas wires the rules: one fit chooser, the button's title, both edges by labelPlace", () => {
  const src = readFileSync(new URL("../../components/maps/MapsCanvas.tsx", import.meta.url), "utf8");
  assert.equal(src.match(/labelPlace\(/g)?.length, 2, "ExitEdge and SessionEdge");
  assert.equal(src.match(/<title>\{label\}<\/title>/g)?.length, 2, "a hidden label's words stay on its line");
  assert.doesNotMatch(src, /- 64\}px/, "no label above the row");
  assert.match(src, /title=\{fitText\} aria-label=\{FIT_NAME\}/);
  assert.match(src, /minZoom=\{FIT_FLOOR\}/);
  assert.doesNotMatch(src, /fitViewport\(/, "the canvas fits only through fitChoice");
});
