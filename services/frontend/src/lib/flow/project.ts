// THE PROJECT (format 3; docs/planning/project-model.md, Batt 2026-11-13): what /maps and /flows
// edit and save. Nodes on /maps -- login, choose character, one per map, and ONE Global -- each
// with tabs on /flows: exactly one "main" (the node's program; Global has none) and the user's own
// tabs of functions, events and variables. Main imports its node's tabs and Global; a node's name
// OVERRIDES Global's on that node, everywhere (Global's own functions and events included).
//
// The flow engine (packages/poring_flow, project.py) is the source of truth for validation, lint,
// the Python view and the simulator; this file is the browser's copy of the JSON's shape and the
// PURE helpers both pages share: names and overrides, tab names, the Run keys, the ready-made
// projects. The statements and expressions are ir.ts's (IR 2's, with call arguments and return).
//
// THE START (Batt 2026-11-13 ~21:4x: "START > map xmas_dun02, ONE box is enough; login and choosing
// the character come later"): `start` is a login node (the session path, by edges) or a MAP node --
// the run starts where she stands on it (a person put her there), at its first entry; login and
// character nodes are then optional and `edges` may be empty.
import type { ActionStmt, CellRef, Entry, Expr, Handler, Lit, MapRef, MobRef, Stmt, Target, ZonesRef } from "./ir.ts";
import { NAME, RUNTIME_DEFAULT_S, WHERE_BUDGET_DEFAULT } from "./ir.ts";

export const PROJECT_FORMAT = "poring-lab.project";
export const PROJECT_VERSION = 3;
export const GLOBAL_ID = "global";
export const MAIN_TAB = "main";

export type NodeKind = "login" | "character" | "map" | "global";
export type Param = { name: string; default: Lit | null };
/** An event's trigger: IR 2's Handler without its name (the def's) and body (the def's). */
export type Trigger = Omit<Handler, "name" | "body">;
/** A function; with a trigger it is an EVENT (no inputs; its name is the event's key). */
export type Def = { name: string; params: Param[]; varargs: string | null; kwargs: string | null; body: Stmt[]; on: Trigger | null };
export type Tab = { name: string; main: Stmt[] | null; defs: Def[]; vars: Record<string, Lit> };
type NodeBase = { id: string; pos: { x: number; y: number }; tabs: Tab[] };
export type LoginNode = NodeBase & { kind: "login" };
export type CharacterNode = NodeBase & { kind: "character" };
export type MapNode = NodeBase & {
  kind: "map";
  map: MapRef;
  entries: Entry[];
  targets: MobRef[];
  ignore: MobRef[];
  /** ABSENT when there is none (the engine leaves it out of the canonical JSON). */
  zones?: ZonesRef;
  resume_here: boolean;
};
export type GlobalNode = NodeBase & { kind: "global" };
export type PNode = LoginNode | CharacterNode | MapNode | GlobalNode;
/** The session path: login -> character -> the start map (its entry). Map -> map links are exits.
 * A project that starts on a map node needs none. */
export type Edge = { from: string; to: string; entry?: string };
export type Project = {
  format: typeof PROJECT_FORMAT;
  version: typeof PROJECT_VERSION;
  name: string;
  description: string;
  target: Target;
  max_runtime_s: number;
  where_budget: number;
  stop_when: Expr | null;
  assumes: Expr[];
  start: string;
  nodes: PNode[];
  edges: Edge[];
};

// --- nodes and tabs ---------------------------------------------------------------------------
export const nodeById = (p: Project, id: string): PNode | undefined => p.nodes.find((n) => n.id === id);
export const globalOf = (p: Project): GlobalNode | undefined => p.nodes.find((n): n is GlobalNode => n.kind === "global");
export const mapNodes = (p: Project): MapNode[] => p.nodes.filter((n): n is MapNode => n.kind === "map");
export const mainOf = (n: PNode): Tab | undefined => (n.kind === "global" ? undefined : n.tabs.find((t) => t.name === MAIN_TAB));
export const tabOf = (n: PNode, name: string): Tab | undefined => n.tabs.find((t) => t.name === name);

/** Tab names are Python module names (matpilot ADR 0013): the engine's rule (catalogue
 * `tab_name_rule`) is the source; this copy refuses the same so a person is told at once. */
export const TAB_NAME = /^[a-z][a-z0-9_]{0,19}$/;
export const RESERVED_TAB_NAMES: readonly string[] = [
  "main", "global", "and", "as", "assert", "async", "await", "break", "class", "continue", "def", "del", "elif", "else", "except",
  "false", "finally", "for", "from", "if", "import", "in", "is", "lambda", "none", "nonlocal", "not", "or", "pass", "raise",
  "return", "true", "try", "while", "with", "yield", "print", "len", "range", "list", "dict", "set", "str", "int", "float",
  "bool", "type", "object", "time", "math", "random", "sys", "os",
];

/** Why a new or renamed tab cannot have this name on this node, else null. */
export function tabNameProblem(n: PNode, name: string, renaming: string | null = null): string | null {
  if (!TAB_NAME.test(name)) return "a tab name is lower-case English letters, numbers and _ (a letter first, at most 20)";
  if (RESERVED_TAB_NAMES.includes(name)) return `“${name}” is a name Python or the flow already uses`;
  if (n.tabs.some((t) => t.name === name && t.name !== renaming)) return `this ${n.kind === "global" ? "Global node" : "node"} has a tab “${name}” already`;
  if (namesOf(n).has(name)) return `a function or variable of this node is called “${name}”`;
  return null;
}

/** A new tab name: tab2, tab3, ... (matpilot's). */
export function newTabName(n: PNode): string {
  for (let i = 2; ; i++) if (!tabNameProblem(n, `tab${i}`)) return `tab${i}`;
}

// --- names: one namespace per node; a node's OVERRIDES Global's on that node ------------------------
export type Named = { kind: "def" | "event" | "var"; tab: string; def?: Def };

/** Every name a node defines, with its tab (a name twice is the engine's error; the first wins here). */
export function namesOf(n: PNode): Map<string, Named> {
  const out = new Map<string, Named>();
  for (const t of n.tabs) {
    for (const d of t.defs) if (!out.has(d.name)) out.set(d.name, { kind: d.on ? "event" : "def", tab: t.name, def: d });
    for (const v of Object.keys(t.vars)) if (!out.has(v)) out.set(v, { kind: "var", tab: t.name });
  }
  return out;
}

/** The definition a name means ON A NODE: the node's own first, then Global's (virtual dispatch). */
export function resolve(p: Project, nodeId: string, name: string): (Named & { from: "node" | "global" }) | null {
  const n = nodeById(p, nodeId);
  const own = n ? namesOf(n).get(name) : undefined;
  if (own) return { ...own, from: n?.kind === "global" ? "global" : "node" };
  const g = globalOf(p);
  const gl = g ? namesOf(g).get(name) : undefined;
  return gl ? { ...gl, from: "global" } : null;
}

/** The node's names that override Global's (the editor marks them). */
export function overridesOn(p: Project, nodeId: string): string[] {
  const n = nodeById(p, nodeId);
  const g = globalOf(p);
  if (!n || !g || n.kind === "global") return [];
  const gl = namesOf(g);
  return [...namesOf(n).keys()].filter((k) => gl.has(k));
}

/** The nodes where a Global name is overridden (Global's tab says so). */
export function overriddenBy(p: Project, name: string): string[] {
  return p.nodes.filter((n) => n.kind !== "global" && namesOf(n).has(name)).map((n) => n.id);
}

/** The text of a def's inputs, as Python writes them: "key, times=1, *args, **kwargs". */
export function paramsText(d: Pick<Def, "params" | "varargs" | "kwargs">, litText: (l: Lit) => string): string {
  const parts = d.params.map((p) => (p.default ? `${p.name}=${litText(p.default)}` : p.name));
  if (d.varargs) parts.push(`*${d.varargs}`);
  if (d.kwargs) parts.push(`**${d.kwargs}`);
  return parts.join(", ");
}

// --- the Run keys (section 6): each role's function, resolved on THAT node, to one press_key ------
export type RunnerKeys = { heal_key: string; fly_key: string; home_key: string; knife_key: string; dagger_key: string };
export type KeySource = Record<keyof RunnerKeys, string>;
export type KeysResult = { ok: true; keys: RunnerKeys; from: KeySource } | { ok: false; problems: string[] };
export const RUNNER_ROLE_KEYS = [
  { param: "heal", key: "heal_key", words: "heal" },
  { param: "fly", key: "fly_key", words: "Fly Wing" },
  { param: "knife_on", key: "knife_key", words: "Knife on" },
  { param: "knife_back", key: "dagger_key", words: "Knife back" },
] as const;
/** The runner block's OPTIONAL fifth role (the one box): the Butterfly Wing it flies home on. */
export const HOME_ROLE = "home";
/** Stage 3 (live-blocks.md 3.3): the roles whose function may be a BODY of presses and waits (the
 * hunt core calls it at its own moment; its key for Run is its FIRST press), and the OPTIONAL
 * respawn roles (functions of click_at: the death exit's two presses). */
export const BODY_ROLES: readonly string[] = ["knife_on", "knife_back", HOME_ROLE];
export const RESPAWN_ROLES: readonly string[] = ["respawn", "respawn_confirm"];
const MAX_DEPTH = 6;

/** Every statement of a body, nested ones too. */
export function* allStmts(stmts: readonly Stmt[]): Generator<Stmt> {
  for (const s of stmts) {
    yield s;
    if (s.kind === "if") {
      yield* allStmts(s.then);
      yield* allStmts(s.orelse);
    } else if (s.kind === "while" || s.kind === "repeat" || s.kind === "for") yield* allStmts(s.body);
  }
}

/** Every statement a node holds: its main and every function of its tabs. */
export function* nodeStmts(n: PNode): Generator<Stmt> {
  for (const t of n.tabs) {
    if (t.main) yield* allStmts(t.main);
    for (const d of t.defs) yield* allStmts(d.body);
  }
}

/** The node's runner block (dungeon_hunt), else null. */
export function runnerBlockOn(n: PNode | undefined): ActionStmt | null {
  if (!n) return null;
  for (const s of nodeStmts(n)) if (s.kind === "action" && s.block === "dungeon_hunt") return s;
  return null;
}

/** The first map node holding a runner block. */
export const runnerNode = (p: Project): MapNode | undefined => mapNodes(p).find((n) => runnerBlockOn(n) !== null);

/** The node's way home: the runner block's `home` role first (the runner flies home itself on that
 * Butterfly Wing), else the function its item warp calls; null when neither names one. */
export function homeFunctionOn(n: PNode): string | null {
  const hunt = runnerBlockOn(n);
  const role = hunt?.params[HOME_ROLE];
  if (role && role.kind === "lit" && typeof role.value === "string") return role.value;
  for (const s of nodeStmts(n)) if (s.kind === "take_exit" && s.exit.kind === "item_warp" && s.exit.proc) return s.exit.proc;
  return null;
}

type Env = Record<string, Lit>;

function litOf(e: Expr | undefined, env: Env): Lit | null {
  if (!e) return null;
  if (e.kind === "lit") return e;
  if (e.kind === "var" && e.name in env) return env[e.name];
  return null;
}

/** The one key a function presses when called with these literal arguments, on this node: its
 * body is exactly one press_key (its key a literal or an input), or exactly one call of another
 * function (followed, at most MAX_DEPTH deep). */
export function keyOfCall(p: Project, nodeId: string, name: string, args: Expr[] = [], kwargs: Record<string, Expr> = {}, env: Env = {}, depth = 0): { key: string } | { why: string } {
  if (depth > MAX_DEPTH) return { why: `${name}(): calls go deeper than ${MAX_DEPTH}` };
  const r = resolve(p, nodeId, name);
  if (!r || r.kind === "var" || !r.def) return { why: `there is no function ${name}` };
  const d = r.def;
  const bound: Env = {};
  for (let i = 0; i < d.params.length; i++) {
    const pr = d.params[i];
    const given = i < args.length ? litOf(args[i], env) : pr.name in kwargs ? litOf(kwargs[pr.name], env) : pr.default;
    if (!given) return { why: `${name}(): its input ${pr.name} is not a plain value here` };
    bound[pr.name] = given;
  }
  if (d.body.length !== 1) return { why: `${name}() must be exactly one "press key" (or one call): the runner presses one key for it` };
  const s = d.body[0];
  if (s.kind === "action" && s.block === "press_key") {
    const k = litOf(s.params.key, bound);
    if (!k || typeof k.value !== "string") return { why: `${name}(): its key is not one key` };
    return { key: k.value };
  }
  if (s.kind === "call") return keyOfCall(p, nodeId, s.proc, s.args, s.kwargs, bound, depth + 1);
  return { why: `${name}() must be exactly one "press key" (or one call): the runner presses one key for it` };
}

/** A role's key (stage 3): `keyOfCall`'s one key; for a knife or home function that is a BODY of
 * presses, waits and calls with plain values, its FIRST press (poring_flow.functions.role_key). */
export function roleKeyOf(p: Project, nodeId: string, name: string, role: string): { key: string } | { why: string } {
  const one = keyOfCall(p, nodeId, name);
  if ("key" in one || !BODY_ROLES.includes(role)) return one;
  const first = (fn: string, args: Expr[], kwargs: Record<string, Expr>, env: Env, depth: number): string | null | undefined => {
    if (depth > MAX_DEPTH) return undefined;
    const r = resolve(p, nodeId, fn);
    if (!r || r.kind === "var" || !r.def) return undefined;
    const d = r.def;
    const bound: Env = {};
    for (let i = 0; i < d.params.length; i++) {
      const pr = d.params[i];
      const given = i < args.length ? litOf(args[i], env) : pr.name in kwargs ? litOf(kwargs[pr.name], env) : pr.default;
      if (!given) return undefined;
      bound[pr.name] = given;
    }
    for (const s of d.body) {
      if (s.kind === "wait_until" && s.cond.kind === "lit" && s.cond.value === false && !s.outcome_to) continue;
      if (s.kind === "action" && s.block === "press_key") {
        const k = litOf(s.params.key, bound);
        return k && typeof k.value === "string" ? k.value : undefined;
      }
      if (s.kind === "call") {
        const inner = first(s.proc, s.args, s.kwargs, bound, depth + 1);
        if (inner !== null) return inner; // a key, or undefined (not a body of presses)
        continue; // waits only: on to the next statement
      }
      return undefined;
    }
    return null;
  };
  const k = first(name, [], {}, {}, 0);
  return typeof k === "string" ? { key: k } : one;
}

/** The five keys a Run of this map node takes, from its functions (overrides first). */
export function runnerKeysOn(p: Project, nodeId: string): KeysResult {
  const n = nodeById(p, nodeId);
  const hunt = runnerBlockOn(n);
  if (!n || !hunt) return { ok: false, problems: [`the node ${nodeId} has no "hunt with the runner" block`] };
  const problems: string[] = [];
  const keys: Partial<RunnerKeys> = {};
  const from: Partial<KeySource> = {};
  const take = (k: keyof RunnerKeys, fn: string | null, role: string, param: string) => {
    if (!fn) return problems.push(`${role}: no function named`);
    const r = roleKeyOf(p, nodeId, fn, param);
    if ("why" in r) return problems.push(`${role}: ${r.why}`);
    keys[k] = r.key;
    from[k] = fn;
  };
  for (const r of RUNNER_ROLE_KEYS) {
    const v = hunt.params[r.param];
    take(r.key, v && v.kind === "lit" && typeof v.value === "string" ? v.value : null, r.words, r.param);
  }
  const home = homeFunctionOn(n);
  if (!home) problems.push('the way home: the runner block\'s "home (Butterfly Wing): call ..." is empty and the map has no "item warp: call ..." exit');
  else take("home_key", home, "the way home (Butterfly Wing)", HOME_ROLE);
  if (problems.length) return { ok: false, problems };
  return { ok: true, keys: keys as RunnerKeys, from: from as KeySource };
}

// --- building blocks ------------------------------------------------------------------------------
const rest = { on_fail: "stop" as const, outcome_to: null, note: null };
export const pressKey = (key: string): ActionStmt => ({ kind: "action", block: "press_key", concept: "ui.press_hotkey", params: { key: { kind: "lit", value: key } }, timeout_s: 2, ...rest });
export const call = (proc: string, args: Expr[] = [], kwargs: Record<string, Expr> = {}): Stmt => ({ kind: "call", proc, args, kwargs });
export const def = (name: string, body: Stmt[], extra: Partial<Def> = {}): Def => ({ name, params: [], varargs: null, kwargs: null, body, on: null, ...extra });
export const mainTab = (main: Stmt[], defs: Def[] = []): Tab => ({ name: MAIN_TAB, main, defs, vars: {} });
export const tab = (name: string, defs: Def[], vars: Record<string, Lit> = {}): Tab => ({ name, main: null, defs, vars });
const lit = (value: Lit["value"]): Lit => ({ kind: "lit", value });

/** The login node's program (section 5: a server and a credential by NAME, never a secret). */
export const loginMain = (server = "lab-rathena", credential = "lab_gm"): Stmt[] => [
  { kind: "action", block: "login", concept: "session.login", timeout_s: 60, ...rest, params: { server: lit(server), credential: lit(credential) } },
];
/** The character node's program: the remembered slot (as the bot's login does). */
export const characterMain = (): Stmt[] => [{ kind: "action", block: "choose_character", concept: "session.select_char", timeout_s: 60, ...rest, params: {} }];

/** A new map node for /maps "+ map" (one entry, a main that stops at once until written). */
export function newMapNode(p: Project, map: string, pos: { x: number; y: number }): MapNode {
  let id = map.replace(/[^A-Za-z0-9_]/g, "_").replace(/^[^A-Za-z]/, "m");
  for (let i = 2; p.nodes.some((n) => n.id === id); i++) id = `${id.replace(/_\d+$/, "")}_${i}`;
  return { id, kind: "map", pos, map: { kind: "map", map }, entries: [{ name: "arrival", at: null, radius: 2 }], targets: [], ignore: [], resume_here: true, tabs: [mainTab([{ kind: "stop", reason: "done" }])] };
}


export function isName(s: string): boolean {
  return NAME.test(s);
}

// --- the ready-made projects (fixtures project_xmas_dun02.json / project_sample.json) -----------------
const TARGET: Target = { client: "kro-20211103-prere", server: "lab-rathena", locale: "en", path: "s2" };
const GEFFEN_SAVE: CellRef = { kind: "cell", map: "geffen", x: 119, y: 40 };
export const SAVE_NOTE = "the world rule: the save point (where a Butterfly Wing and a death land)";
export const XMAS_ZONES_SHA = "89ea7a9c98d5d62b869a99189119548ea114868566bd293d43d46e3f24ebe345";

const sense = (sensor: string): Expr => ({ kind: "sense", sensor, args: {} });
/** click_at(x, y): one click at a point of the game picture (stage 3; live only in the death exit). */
export const clickAt = (x: number, y: number, note: string | null = null): ActionStmt => ({ kind: "action", block: "click_at", concept: "ui.press_button", params: { x: lit(x), y: lit(y) }, timeout_s: 2, ...rest, note });
const below = (sensor: string, v: number): Expr => ({ kind: "cmp", op: "<", left: sense(sensor), right: lit(v) });
/** An event's trigger with the engine's defaults (a repeating event: `until`; a one-shot: `rearm`,
 * or its condition going false; both paced by `cooldown_s`). */
export const trigger = (when: Expr, extra: Partial<Trigger> = {}): Trigger => ({
  when,
  until: null,
  rearm: null,
  priority: "survival",
  rank: null,
  mode: "insert",
  escalate: null,
  max_insert_fails: 3,
  cooldown_s: 0,
  max_per_min: null,
  max_fires_per_10min: 10,
  max_per_run: null,
  then: "resume",
  ...extra,
});

/** The Rogue's project, ONE BOX (Batt 2026-11-13 ~21:4x: "take every box out: START > map
 * xmas_dun02, one box is enough; login and choosing the character come later; the user puts the
 * character on xmas_dun02 themself"): the run starts where she stands on xmas_dun02. Its main: the
 * save point (Geffen), hunt with the runner (everything the bot has trained), stop -- the runner
 * itself flies home on the Butterfly Wing (the bag half full, or Stop: its settings). Its tab keys:
 * every key a function. Its tab survival (stage 2, Batt 2026-11-13: "Heal: press F1 when HP < 30 %.
 * Fly Wing: press F8 when a boss is seen or HP < 25 %"; live-blocks.md 3.2): two EVENTS that play
 * inside the hunt core on every runner tick -- drink (repeating while HP is under 30 %, a potion
 * every 0.7 s at most, as the runner paces its own) and fly_away (once per sighting or per fall
 * under 25 %, re-armed 3 s after its Fly Wing, the runner's own Fly Wing pace). Stage 3
 * (live-blocks.md 3.3, Batt 2026-11-13: "The Knife swap (Damascus): a function: press F4, wait
 * 100 ms, press F5; the other way back: the same swapped"; "make respawn a function block"):
 * survival's bag_full (the weight home at 50 %: the run stops and the runner flies her home), the
 * tab knife (the swap as two functions at the runner's moments: the Knife before the steal strike,
 * the Damascus back after it -- the runner's own today; the open question is written there) and
 * the tab exits (the way home, the death dialog's two clicks). The keys stay in tab keys. */
export function xmasProject(): Project {
  return {
    format: PROJECT_FORMAT,
    version: PROJECT_VERSION,
    name: "xmas_dun02",
    description: "One box: a person puts the Rogue on xmas_dun02; the runner hunts. Tabs: keys; survival (drink, fly_away, bag_full at 50 % weight); knife (the swap); exits (the way home, the respawn).",
    target: { ...TARGET },
    max_runtime_s: 7200,
    where_budget: WHERE_BUDGET_DEFAULT,
    stop_when: null,
    assumes: [],
    start: "xmas_dun02",
    nodes: [
      {
        id: "xmas_dun02",
        kind: "map",
        pos: { x: 0, y: 0 },
        map: { kind: "map", map: "xmas_dun02" },
        entries: [{ name: "here", at: null, radius: 2 }],
        targets: [],
        ignore: [],
        zones: { map: "xmas_dun02", sha256: XMAS_ZONES_SHA },
        resume_here: true,
        tabs: [
          mainTab([
            { kind: "action", block: "assert_save_point", concept: "core.assert_save_point", timeout_s: 1, on_fail: "stop", outcome_to: null, note: SAVE_NOTE, params: { cell: lit({ ...GEFFEN_SAVE }) } },
            { kind: "action", block: "dungeon_hunt", concept: "combat.hunt", timeout_s: 600, ...rest, params: { heal: lit("heal"), fly: lit("fly_wing"), knife_on: lit("knife_on"), knife_back: lit("knife_back"), home: lit("fly_home"), respawn: lit("respawn_button"), respawn_confirm: lit("respawn_ok") } },
            { kind: "stop", reason: "home" },
          ]),
          tab("keys", [def("heal", [pressKey("F1")]), def("fly_wing", [pressKey("F8")]), def("butterfly_wing", [pressKey("F9")]), def("wield_knife", [pressKey("F4")]), def("wield_damascus", [pressKey("F5")])]),
          tab("survival", [
            def("drink", [call("heal")], { on: trigger(below("hp_percent", 30), { until: { kind: "cmp", op: ">=", left: sense("hp_percent"), right: lit(31) }, cooldown_s: 0.7 }) }),
            def("fly_away", [call("fly_wing")], { on: trigger({ kind: "or", terms: [sense("sees_boss"), below("hp_percent", 25)] }, { cooldown_s: 3, priority: "critical", mode: "preempt" }) }),
            def("bag_full", [{ kind: "stop", reason: "home" }], { on: trigger({ kind: "cmp", op: ">=", left: sense("weight_percent"), right: lit(50) }, { priority: "upkeep", mode: "preempt", max_per_run: 1 }) }),
          ]),
          tab("knife", [def("knife_on", [call("wield_knife")]), def("knife_back", [call("wield_damascus")])]),
          tab("exits", [
            def("fly_home", [call("butterfly_wing")]),
            def("respawn_button", [clickAt(645, 481, "the death dialog's first button: move to the saved location")]),
            def("respawn_ok", [clickAt(714, 405, "this client's confirmation: OK")]),
          ]),
        ],
      },
    ],
    edges: [],
  };
}

/** The two-map sample on the SYNTHETIC sample sheets (town_1 / field_1; the first screen). */
export function sampleProject(): Project {
  return {
    format: PROJECT_FORMAT,
    version: PROJECT_VERSION,
    name: "my_first_project",
    description: "Town: set the save point, warp to the field. Field: attack 5 times, a wing back (Global's function butterfly_wing: press F9). Runs until stopped. The sample's SYNTHETIC maps and keys.",
    target: { ...TARGET },
    max_runtime_s: RUNTIME_DEFAULT_S,
    where_budget: WHERE_BUDGET_DEFAULT,
    // "run until stopped" (IR 2's run_until_stopped), as the engine spells it in a project
    stop_when: { kind: "lit", value: false },
    assumes: [],
    start: "login",
    nodes: [
      { id: "login", kind: "login", pos: { x: 0, y: 0 }, tabs: [mainTab(loginMain())] },
      { id: "character", kind: "character", pos: { x: 0, y: 120 }, tabs: [mainTab(characterMain())] },
      {
        id: "town",
        kind: "map",
        pos: { x: 230, y: 0 },
        map: { kind: "map", map: "town_1" },
        entries: [{ name: "spawn", at: { kind: "cell", map: "town_1", x: 40, y: 40 }, radius: 2 }],
        targets: [],
        ignore: [],
        resume_here: true,
        tabs: [
          mainTab([
            { kind: "action", block: "set_save_point", concept: "nav.set_save_point", timeout_s: 60, ...rest, params: { npc: lit({ kind: "npc", key: "n_kafra" }) } },
            { kind: "action", block: "walk_to", concept: "nav.walk_to", timeout_s: 120, ...rest, params: { cell: lit({ kind: "cell", map: "town_1", x: 97, y: 71 }) } },
            { kind: "take_exit", exit: { kind: "npc_warp", warp: null, npc: { kind: "npc", key: "n_warper" }, options: [{ kind: "option", key: "o_to_field" }], item: null, to_block: "field", to_entry: "arrival", timeout_s: 120 } },
          ]),
        ],
      },
      {
        id: "field",
        kind: "map",
        pos: { x: 460, y: 0 },
        map: { kind: "map", map: "field_1" },
        entries: [{ name: "arrival", at: { kind: "cell", map: "field_1", x: 30, y: 30 }, radius: 2 }],
        targets: [9101, 9102, 9105, 9109].map((id) => ({ kind: "mob" as const, id })),
        ignore: [],
        resume_here: true,
        tabs: [
          mainTab([
            { kind: "repeat", times: lit(5), body: [{ kind: "action", block: "attack_nearest", concept: "combat.attack_target", timeout_s: 120, ...rest, params: { within: lit(12) } }] },
            { kind: "take_exit", exit: { kind: "item_warp", warp: null, npc: null, options: [], item: null, proc: "butterfly_wing", to_block: "town", to_entry: "spawn", timeout_s: 120 } },
          ]),
        ],
      },
      { id: GLOBAL_ID, kind: "global", pos: { x: 230, y: 170 }, tabs: [tab("keys", [def("butterfly_wing", [pressKey("F9")])])] },
    ],
    edges: [
      { from: "login", to: "character" },
      { from: "character", to: "town", entry: "spawn" },
    ],
  };
}

// =================================================================================================
// ADDED BY /maps (2026-11-13, the project-maps branch): pure helpers both pages may use. Nothing
// above this line was changed.
// =================================================================================================

/** Every statement a node holds, with its ENGINE PATH "<node>/<tab>/<site>" (the lint findings'
 * `path`, api.ts sitePath): a tab's main is the site root "main", a function its own name, nested
 * bodies as IR 2's paths (`main.2.body.0`, `heal.0.then.1`). */
export function* nodeSites(n: PNode): Generator<{ path: string; tab: string; site: string; stmt: Stmt }> {
  function* walkSites(stmts: readonly Stmt[], prefix: string): Generator<[string, Stmt]> {
    for (let i = 0; i < stmts.length; i++) {
      const site = `${prefix}.${i}`;
      const s = stmts[i];
      yield [site, s];
      if (s.kind === "if") {
        yield* walkSites(s.then, `${site}.then`);
        yield* walkSites(s.orelse, `${site}.orelse`);
      } else if (s.kind === "while" || s.kind === "repeat" || s.kind === "for") yield* walkSites(s.body, `${site}.body`);
    }
  }
  for (const t of n.tabs) {
    if (t.main) for (const [site, stmt] of walkSites(t.main, MAIN_TAB)) yield { path: `${n.id}/${t.name}/${site}`, tab: t.name, site, stmt };
    for (const d of t.defs) for (const [site, stmt] of walkSites(d.body, d.name)) yield { path: `${n.id}/${t.name}/${site}`, tab: t.name, site, stmt };
  }
}

/** THE SESSION PATH (section 2, Edge): from `start` along `edges` -- login -> character -> the
 * start map node and its entry; a MAP start is that map node at its first entry (no login, no
 * character: `isMapStart`). Each step is the node's ONE outgoing edge; `problems` says in words
 * where the path breaks (Simulate starts at `start`, the save point rule reads the start map). */
export type SessionPath = { login: LoginNode | null; character: CharacterNode | null; map: MapNode | null; entry: string | null; problems: string[] };

/** The start when it is a MAP node (the run starts where she stands on it), else null. */
export function startMap(p: Project): MapNode | null {
  const n = nodeById(p, p.start);
  return n?.kind === "map" ? n : null;
}
export const isMapStart = (p: Project): boolean => startMap(p) !== null;
export function sessionPath(p: Project): SessionPath {
  const out: SessionPath = { login: null, character: null, map: null, entry: null, problems: [] };
  const next = (id: string) => p.edges.filter((e) => e.from === id);
  const start = nodeById(p, p.start);
  if (!start) return { ...out, problems: [`the start ${p.start} is not a node`] };
  // a MAP start (the one box): the map node itself at its first entry, no session
  if (start.kind === "map") return { ...out, map: start, entry: start.entries[0]?.name ?? null, problems: start.entries.length ? [] : [`${start.id} has no entry`] };
  if (start.kind !== "login") return { ...out, problems: [`the start ${p.start} is neither a login node nor a map node`] };
  out.login = start;
  const a = next(start.id);
  if (a.length !== 1) return { ...out, problems: [a.length ? "the login node has more than one connection" : "the login node is not connected to a character node"] };
  const ch = nodeById(p, a[0].to);
  if (!ch || ch.kind !== "character") return { ...out, problems: ["the login node must connect to a character node"] };
  out.character = ch;
  const b = next(ch.id);
  if (b.length !== 1) return { ...out, problems: [b.length ? "the character node has more than one connection" : "the character node is not connected to a map"] };
  const m = nodeById(p, b[0].to);
  if (!m || m.kind !== "map") return { ...out, problems: ["the character node must connect to a map node"] };
  out.map = m;
  out.entry = b[0].entry && m.entries.some((e) => e.name === b[0].entry) ? b[0].entry : null;
  if (!out.entry) out.problems.push(b[0].entry ? `${m.id} has no entry ${b[0].entry}` : `the connection into ${m.id} names no entry`);
  return out;
}
