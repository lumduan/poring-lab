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
  s("engage", "safety", "a fight begins; the Garm Baby alarm"),
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
/** Round 26 (the reviewer's 5c review; until Batt answers 15.10 Q1 the editor matches the built
 * default): a SAFETY or REQUIRED step in hunt_tick() is LOCKED -- it cannot be deleted or dragged
 * out (blockly-register.ts tickLock); its head row shows a padlock, and each class has a colour of
 * its own (theme.ts). An optional step may be dragged out, alone (the steps under it close up). */
export const LOCKED_CLASSES: readonly StepClass[] = ["safety", "required"];
export const isLockedClass = (k: StepClass): boolean => LOCKED_CLASSES.includes(k);
export const STEP_STYLE: Record<StepClass, string> = { safety: "pl_step_safety_blocks", required: "pl_step_required_blocks", optional: "pl_step_optional_blocks" };
export const PADLOCK = "🔒";
/** The block type of a step block (one per step: its words are its own). */
export const stepType = (t: TickStep): string => `pl_${STEP_PREFIX}${t.name}`;
export const STEP_OF_TYPE: ReadonlyMap<string, TickStep> = new Map(TICK_STEPS.map((t) => [stepType(t), t]));
