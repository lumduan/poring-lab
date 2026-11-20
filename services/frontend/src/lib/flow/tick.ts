// Live blocks STAGE 5c (docs/planning/live-blocks.md 15; Batt 2026-11-15 ~13:0x: "dungeon_hunt.py
// should be blocks the user sees and can edit himself"): the hunt core as FUNCTIONS IN TABS, the
// browser's half. A map node's main calls hunt_loop() where the runner block stood; the tab hunt
// holds its ROLE BLOCKS (role_<param> = "<function>": which function is heal, the Fly Wing, ...) and
// its loop; the tab tick holds hunt_tick(), run()'s 20 steps as STEP BLOCKS in run()'s order, each
// with its CLASS. The engine's twin is poring_flow.tick (the table) and poring_flow.huntloop (the
// call and the roles); test_runner_functions_ts.py pins this file to them. Pure data, no imports.

/** The function main calls: the hunt core starts there (poring_flow.huntloop HUNT_CALL). */
export const HUNT_CALL = "hunt_loop";
/** A role block is the tab variable role_<the runner block's param>. */
export const ROLE_PREFIX = "role_";
/** The tick's function and its tab (a tab cannot share a function's name). */
export const TICK_FN = "hunt_tick";
export const TICK_TAB = "tick";
/** A step block is step_<run()'s step name>. */
export const STEP_PREFIX = "step_";
/** The runner block's parameters, each a role block's (poring_flow.huntloop HUNT_ROLES; the order
 * of blockdefs.ts RUNNER_ROLES), and the four a hunt core needs (REQUIRED_ROLES). */
export const HUNT_ROLES: readonly string[] = ["heal", "fly", "knife_on", "knife_back", "home", "respawn", "respawn_confirm", "eat"];
export const REQUIRED_ROLES: readonly string[] = ["heal", "fly", "knife_on", "knife_back"];
/** The lowered hunt core's note (poring_flow.huntloop LOWERED_NOTE). */
export const LOWERED_NOTE = "the hunt core of hunt_loop() (live blocks 5c)";

export type StepClass = "safety" | "required" | "optional";
export type TickStep = {
  /** run()'s step name (dungeon_hunt.STEP_NAMES) */
  name: string;
  klass: StepClass;
  /** what it does (the block's words) */
  words: string;
  /** a mode step: the hunt loop's block that plays it ("" a common step: every tick) */
  owner: string;
};

const s = (name: string, klass: StepClass, words: string, owner = ""): TickStep => ({ name, klass, words, owner });
/** run()'s steps in their order, each one's class (== poring_flow.tick STEPS). */
export const TICK_STEPS: readonly TickStep[] = [
  s("begin", "safety", "the tick's clock; the Run's Stop"),
  s("sense", "safety", "the frame, HP, SP, the position"),
  s("hook", "safety", "the box's own tick: its Stop, its events"),
  s("vitals", "safety", "death"),
  s("battle_log", "safety", "the Battle Log: hits, kills, a boss"),
  s("survive", "safety", "the potion, the Fly Wing, Auto Guard"),
  s("engage", "safety", "a fight begins; the alarm monsters (the model's alarm list)"),
  s("ui", "safety", "the UI watch; the weight; home"),
  s("upkeep", "safety", "the Knife's HP floor; overweight; HUD"),
  s("fight", "required", "the fight (the recipe's steps)", "fight_target"),
  s("hold", "required", "a held target waits; the loot recheck", "find_target"),
  s("loot", "optional", "the loot step after a fight", "fight_target"),
  s("after", "required", "a fight's end: rest or search", "find_target"),
  s("ready", "optional", "the Knife while idle; the queue", "find_target"),
  s("rest", "required", "sit until HP is full", "find_target"),
  s("idle", "safety", "stuck: uncarve, or a Fly Wing", "find_target"),
  s("plant", "optional", "the White Plant sweep", "find_target"),
  s("search", "required", "the walk", "find_target"),
  s("position", "safety", "an unread position: a Fly Wing", "find_target"),
  s("pace", "required", "the tick's pace (200 ms)", "find_target"),
];
export const stepBlock = (t: TickStep): string => `${STEP_PREFIX}${t.name}`;
/** The step blocks (catalogue names) in run()'s order. */
export const STEP_BLOCKS: readonly string[] = TICK_STEPS.map(stepBlock);
export const STEP_BY_BLOCK: ReadonlyMap<string, TickStep> = new Map(TICK_STEPS.map((t) => [stepBlock(t), t]));
/** The steps a person may leave out (== dungeon_hunt.DRIVE_OPTIONAL_STEPS). */
export const OPTIONAL_STEPS: readonly string[] = TICK_STEPS.filter((t) => t.klass === "optional").map((t) => t.name);
/** A class as a block shows it. */
export const CLASS_WORDS: Record<StepClass, string> = { safety: "SAFETY", required: "REQUIRED", optional: "optional" };
/** Round 29 (Batt 2026-11-16, live-blocks.md 17 #1: "delete, move: it must be editable; if it cannot
 * run, just Undo or load the saved file"; round 26's lock, which 15.10 Q1 left open, is gone): a
 * SAFETY or REQUIRED step is NEEDED TO RUN -- it can be deleted and dragged like any block (alone,
 * the steps under it closing up), and a Run without it is refused in the lint's words; its head
 * class line says so ("SAFETY · needed to run"), each class keeps its colour (theme.ts). An optional step may be
 * left out. */
export const NEEDED_CLASSES: readonly StepClass[] = ["safety", "required"];
export const isNeededClass = (k: StepClass): boolean => NEEDED_CLASSES.includes(k);
export const STEP_STYLE: Record<StepClass, string> = { safety: "pl_step_safety_blocks", required: "pl_step_required_blocks", optional: "pl_step_optional_blocks" };
/** The mark on a needed step's class line (round 26-28's padlock, which a lock no longer backs). */
export const NEED_WORDS = "needed to run";
/** The block type of a step block (one per step: its words are its own). */
export const stepType = (t: TickStep): string => `pl_${STEP_PREFIX}${t.name}`;
export const STEP_OF_TYPE: ReadonlyMap<string, TickStep> = new Map(TICK_STEPS.map((t) => [stepType(t), t]));

/** Round 28 (the reviewer: a SECOND step_survive dropped after step_pace was LOCKED, and the lint
 * said "twice" -- the learner could not delete it): which copy of a step hunt_tick() ACCEPTS, the
 * engine's rule exactly (poring_flow.tick places; the same cases pin both,
 * test_runner_functions.py and tick_lock.test.ts). The copies in their place in the runner's order
 * (the longest run of steps already in order, one copy of a step at most, the earlier copy where two
 * would do) are accepted; another copy of an accepted step is an EXTRA copy; a step with no copy in
 * its place is OUT OF ITS PLACE (its first copy; its other copies extra). The editor shows the
 * lint's words on an extra or a misplaced copy (➡️ round 29: and locks no step). */
export type TickPlace = { kind: "ok" | "extra" | "misplaced" | "other"; where: string };
export const EXTRA_WORDS = "an extra copy: delete it";
const STEP_RANK: ReadonlyMap<string, number> = new Map(STEP_BLOCKS.map((b, i) => [b, i]));

/** PURE: each statement's place in hunt_tick() (`blocks`: its step block's name, null for any
 * other statement). */
export function tickPlaces(blocks: readonly (string | null)[]): TickPlace[] {
  const idx = blocks.flatMap((b, i) => (b !== null && STEP_RANK.has(b) ? [i] : []));
  const rank = (i: number) => STEP_RANK.get(blocks[i]!)!;
  const best = new Map<number, number[]>(); // the longest in-order chain ending at each statement
  for (const i of idx) {
    let chain: number[] = [];
    for (const j of idx) {
      if (j >= i || rank(j) >= rank(i)) continue;
      const c = best.get(j)!;
      // of chains as long, the one ending at the earlier step, then the earlier copy (the first)
      if (c.length > chain.length || (c.length === chain.length && chain.length > 0 && rank(c[c.length - 1]) < rank(chain[chain.length - 1]))) chain = c;
    }
    best.set(i, [...chain, i]);
  }
  let longest: number[] = [];
  for (const c of best.values()) if (c.length > longest.length) longest = c;
  const keep = new Set(longest);
  const accepted = new Set(longest.map((i) => blocks[i]!));
  const present = new Set(idx.map((i) => blocks[i]!));
  const misplaced = new Set<string>();
  return blocks.map((b, i): TickPlace => {
    if (b === null || !STEP_RANK.has(b)) return { kind: "other", where: "" };
    if (keep.has(i)) return { kind: "ok", where: "" };
    if (accepted.has(b) || misplaced.has(b)) return { kind: "extra", where: "" };
    misplaced.add(b);
    return { kind: "misplaced", where: stepWhere(b, present) };
  });
}

/** PURE: where a step goes -- after the step before it in the runner's order, before the one after
 * it, of the steps the tick holds (poring_flow.tick _where). */
export function stepWhere(moved: string, present: ReadonlySet<string>): string {
  const at = STEP_RANK.get(moved)!;
  const have = STEP_BLOCKS.filter((b) => present.has(b) && b !== moved);
  const before = [...have].reverse().find((b) => STEP_RANK.get(b)! < at);
  const after = have.find((b) => STEP_RANK.get(b)! > at);
  if (before && after) return `it goes after ${before}() and before ${after}()`;
  if (after) return `it goes first, before ${after}()`;
  return before ? `it goes last, after ${before}()` : "it goes in its own place";
}

/** What a step block's own rows say about its place (round 28; empty: in its place). */
export function placeWords(p: TickPlace | null): string {
  if (!p || p.kind === "ok" || p.kind === "other") return "";
  return p.kind === "extra" ? `${EXTRA_WORDS} (each step plays once a tick)` : `out of its place: ${p.where}`;
}
