// EVERY KEY A FUNCTION (Batt 2026-11-13): "Fly Wing, Butterfly Wing, the Knife swap, a skill: write
// each as a function whose body says which key F1-F9 to press; Save and Load share them; the
// functions live in a tab of their own." The runner (scripts/dungeon_hunt.py) presses ONE key per
// role, so Run reads each role's key from the function the flow names for it:
//
//   heal_key   <- the runner block's `heal` function      (the heal item's slot)
//   fly_key    <- the runner block's `fly` function       (the Fly Wing's slot)
//   knife_key  <- the runner block's `knife_on` function  (the Knife's slot)
//   dagger_key <- the runner block's `knife_back` function (the dagger's slot)
//   home_key   <- the map block's item warp BY FUNCTION   (the Butterfly Wing's slot)
//
// Each such function must be exactly one `press_key` block (the flow engine's linter says the same:
// packages/poring_flow, the dungeon_hunt block). PURE: no I/O; the Run request carries the result
// and the Run helper checks the keys again (F1-F9, no two roles in use on one key).
import { RUNNER_ROLES } from "./blockdefs.ts";
import { type ActionStmt, canonical, clone, type Flow, type MapBlock, type Stmt } from "./ir.ts";

export type RunnerKeys = { heal_key: string; fly_key: string; home_key: string; knife_key: string; dagger_key: string };
/** Which function each key came from (the Run pane says so). */
export type KeySource = Record<keyof RunnerKeys, string>;
export type KeysResult = { ok: true; keys: RunnerKeys; from: KeySource } | { ok: false; problems: string[] };

const ROLE_KEY: Record<(typeof RUNNER_ROLES)[number]["param"], keyof RunnerKeys> = {
  heal: "heal_key",
  fly: "fly_key",
  knife_on: "knife_key",
  knife_back: "dagger_key",
};

/** Every statement of a body, nested ones too, in order. */
export function* allStmts(stmts: readonly Stmt[]): Generator<Stmt> {
  for (const s of stmts) {
    yield s;
    if (s.kind === "if") {
      yield* allStmts(s.then);
      yield* allStmts(s.orelse);
    } else if (s.kind === "while" || s.kind === "repeat" || s.kind === "for") yield* allStmts(s.body);
  }
}

/** The map block's runner block (the first dungeon_hunt in its main), else null. */
export function runnerBlockOf(block: MapBlock | undefined): ActionStmt | null {
  for (const s of allStmts(block?.main ?? [])) if (s.kind === "action" && s.block === "dungeon_hunt") return s;
  return null;
}

/** The first map block that holds a runner block, else undefined. */
export function runnerMapBlock(flow: Flow): MapBlock | undefined {
  return flow.workflow?.blocks.find((b) => runnerBlockOf(b) !== null);
}

/** The function a map block's item warp calls (its Butterfly Wing home), else null. */
export function homeFunctionOf(block: MapBlock): string | null {
  for (const s of allStmts(block.main)) if (s.kind === "take_exit" && s.exit.kind === "item_warp" && s.exit.proc) return s.exit.proc;
  return null;
}

/** The one key a function presses, or why it is not exactly one press_key block. */
export function keyOf(flow: Flow, name: string): { key: string } | { why: string } {
  const body = flow.procedures[name];
  if (!body) return { why: `there is no function ${name} (the functions tab)` };
  const presses = body.filter((s): s is ActionStmt => s.kind === "action" && s.block === "press_key");
  if (body.length !== 1 || presses.length !== 1) return { why: `${name}() must be exactly one "press key" block (the runner presses one key for it)` };
  const v = presses[0].params.key;
  if (!v || v.kind !== "lit" || typeof v.value !== "string") return { why: `${name}(): its key is not one key` };
  return { key: v.value };
}

/** The five keys a Run of this map block takes, from its functions. */
export function runnerKeys(flow: Flow, block: MapBlock): KeysResult {
  const hunt = runnerBlockOf(block);
  if (!hunt) return { ok: false, problems: [`the map ${block.map.map} has no "hunt with the runner" block`] };
  const problems: string[] = [];
  const keys: Partial<RunnerKeys> = {};
  const from: Partial<KeySource> = {};
  const take = (k: keyof RunnerKeys, fn: string | null, role: string) => {
    if (!fn) return problems.push(`${role}: no function named`);
    const r = keyOf(flow, fn);
    if ("why" in r) return problems.push(`${role}: ${r.why}`);
    keys[k] = r.key;
    from[k] = fn;
  };
  for (const r of RUNNER_ROLES) {
    const v = hunt.params[r.param];
    take(ROLE_KEY[r.param], v && v.kind === "lit" && typeof v.value === "string" ? v.value : null, r.words);
  }
  const home = homeFunctionOf(block);
  if (!home) problems.push('the way home: an "item warp: call ..." exit (the Butterfly Wing\'s function) is missing on this map');
  else take("home_key", home, "the way home (Butterfly Wing)");
  if (problems.length) return { ok: false, problems };
  return { ok: true, keys: keys as RunnerKeys, from: from as KeySource };
}

/** SHARING FUNCTIONS (Batt 2026-11-13: "we have Save and Load, so these can be shared"): the
 * functions of another flow added to this one. A name this flow has already: kept as it is (the
 * file's differs: `kept`; the same body: `same`); a new name: `added`. The rest of the file is not
 * used. PURE. */
export function mergeFunctions(into: Flow, from: Flow): { flow: Flow; added: string[]; same: string[]; kept: string[] } {
  const flow = clone(into);
  const added: string[] = [];
  const same: string[] = [];
  const kept: string[] = [];
  for (const [name, body] of Object.entries(from.procedures)) {
    const mine = flow.procedures[name];
    if (!mine) {
      flow.procedures[name] = clone(body);
      added.push(name);
    } else if (canonical(mine) === canonical(body)) same.push(name);
    else kept.push(name);
  }
  return { flow, added, same, kept };
}
