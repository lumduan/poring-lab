// SIMULATE for a runner flow (lib/flow/runner.ts): an EXAMPLE run of the DESCRIPTION, in the
// browser, so a learner sees the blocks take turns. It models the described rules with the numbers
// the exporter read from the code (KILL_GAP_S, the strategy's potion_below, D0_PX ...), on a
// scripted scenario of what the screen shows. It is NOT the runner: no game, no input, no backend;
// the screen readings and the monsters' worths in EXAMPLE are made up for the lesson (the runner
// reads the real worths at run time and never exports them).
//
// The rules follow dungeon_hunt.py's PURE functions, named beside each port: sustain() + rate_hp_s()
// (the potion and the Fly Wing), hp_dropped(), alarm_seen() with --garm-confirm, kill_gapped(),
// quiet_kill_ends() with --loot-first, scan_needed(), value_target.score() / pick(),
// end_escape_needed(). The fight path is the description's (simpler than run(): e.g. a target is
// chosen afresh whenever there is none, where run() takes the box path once a fight).
import type { RunnerDoc } from "./runner.ts";

export type SimBox = {
  species: string;
  dist_px: number; // its feet from hers, on the screen
  cells: number; // Chebyshev cells away
  walking_px?: number; // its feet moved this far between two detections
  reachable?: boolean; // the server walks her there on one click (--reach-check); default true
};
export type Moment = {
  t: number; // seconds since the run started
  hp: number; // HP share 0..1, as Basic Info reads it
  boxes?: SimBox[];
  hit_on_us?: boolean; // a Battle Log line: a monster hit her
  our_hit?: boolean; // a Battle Log line: her damage
  miss_at_us?: boolean; // a Miss drawn beside her (--miss-cue)
  garm?: boolean; // this detection holds a garm_baby box
  boss_line?: boolean; // a boss name in the Battle Log
  items?: number; // pickup hands the loot step finds
  ring_sword?: boolean; // the ring scan reads a SWORD
  cursor?: "walk" | "sword" | "noentry"; // the walk target's cursor read
  steal_cue?: boolean; // the item popup (the Knife opener's cue)
  note?: string; // a line of the story
};
export type Scenario = { name: string; note: string; values: Record<string, number>; moments: Moment[] };
export type SimTone = "do" | "decide" | "safety" | "look" | "note" | "end";
export type SimStep = { t: number; block: string; text: string; tone: SimTone };
export type SimResult = { steps: SimStep[]; end: string; kills: number; picks: number; potions: number; wings: number; strikes: number };

/** A number of the doc (throws on an unknown id: the tests keep them known). */
export function num(doc: RunnerDoc, id: string): number {
  const p = doc.params[id];
  if (!p || typeof p.value !== "number") throw new Error(`runner_sim: no number ${id}`);
  return p.value;
}

/** value_target.score: a box's worth discounted by distance. */
export const score = (value: number, distPx: number, d0: number) => value / (1 + Math.max(0, distPx) / d0);

/** value_target.pick: the best score (ties: the nearer); null when there is none. */
export function pick(boxes: SimBox[], values: Record<string, number>, d0: number): { box: SimBox; score: number } | null {
  let best: { box: SimBox; score: number } | null = null;
  for (const b of boxes) {
    const s = score(values[b.species] ?? values["*"] ?? 0, b.dist_px, d0);
    if (!best || s > best.score + 1e-9 || (Math.abs(s - best.score) <= 1e-9 && b.dist_px < best.box.dist_px)) best = { box: b, score: s };
  }
  return best;
}

/** dungeon_hunt.rate_hp_s: HP lost a second over the last ``win`` s. */
export function rateHpS(hist: [number, number][], now: number, maxHp: number, win = 2): number | null {
  const pts = hist.filter(([t]) => now - win <= t && t <= now);
  if (pts.length < 2 || pts[pts.length - 1][0] - pts[0][0] < win / 2) return null;
  const [t0, f0] = pts[0];
  const [t1, f1] = pts[pts.length - 1];
  return ((f0 - f1) * maxHp) / (t1 - t0);
}

/** dungeon_hunt.hp_dropped: the HP percent fell >= pts within ``s`` seconds. */
export function hpDropped(hist: [number, number][], now: number, pts: number, s: number): boolean {
  const f = hist.filter(([t]) => now - s <= t && t <= now).map(([, v]) => v);
  return f.length >= 2 && (Math.max(...f) - f[f.length - 1]) * 100 >= pts - 1e-6;
}

/** dungeon_hunt.kill_gapped. */
export const killGapped = (hits: number, sinceLastHit: number, gapS: number, minHits: number) => hits >= minHits && sinceLastHit > gapS;

/** dungeon_hunt.quiet_kill_ends with --loot-first: a kill in the last 3 s that came in THIS fight. */
export function quietKillEnds(kills: number[], now: number, fightT0: number): boolean {
  if (!kills.length || kills[kills.length - 1] <= now - 3) return false;
  return kills[kills.length - 1] >= fightT0;
}

const pct = (x: number) => `${Math.round(x * 100)} %`;
const s1 = (x: number) => `${Math.round(x * 10) / 10} s`;

type Lock = { t: number; hits: number; lastHit: number; species: string };

/** Run the description on a scenario. ``knife``: with the optional Knife opener flag set. */
export function simulate(doc: RunnerDoc, sc: Scenario, opts: { knife?: boolean } = {}): SimResult {
  const N = (id: string) => num(doc, id);
  const minutes = N("cmd.minutes");
  const tEnd = minutes * 60;
  const steps: SimStep[] = [];
  const say = (t: number, block: string, text: string, tone: SimTone = "do") => steps.push({ t, block, text, tone });
  let potions = N("derived.potions");
  let wings = N("derived.wings");
  const p0 = potions;
  const w0 = wings;

  // --- the setup (the run hat's first blocks)
  say(0, "run", `the run starts: ${doc.script} on ${doc.map}`, "note");
  say(0, "identity", `the status window names the ${doc.char}: go on`);
  say(0, "stock", `the hotbar shows ${potions} potions and ${wings} Fly Wings (at least ${N("PLAYER_MIN_HEALS")} and ${N("PLAYER_MIN_WINGS")}): go on`);
  say(0, "weight", `the bag is under ${pct(N("WEIGHT_MAX"))}: go on`, "decide");
  say(0, "start_here", "she starts where you left her, on the map's open ground (no warp, no GM command)");
  say(0, "timebox", `the time box: ${minutes} minutes`);

  let mode: "search" | "fight" | "after" = "search";
  let lock: Lock | null = null;
  let fightT0 = 0;
  const kills: number[] = [];
  let lootKills = 0;
  let lastTaken = -1e9;
  let lastOurs = -1e9;
  let lastSwing = -1e9;
  let lastWalk = -1e9;
  let flyT = -1e9;
  let bossUntil = -1e9;
  let garmStreak = 0;
  const pots: number[] = [];
  let potFrac: number | null = null;
  const hist: [number, number][] = [];
  let picks = 0;
  let strikes = 0;
  let approaches = 0;
  let searching = false;
  let knifeOn = false;
  let knifeT = 0;
  let end = "time";
  const knife = Boolean(opts.knife);

  const dagger = (t: number, why: string) => {
    if (!knife || !knifeOn) return;
    knifeOn = false;
    say(t, "press_dagger", `the dagger back on (${doc.params["bs.EQUIP_KEY"]?.value ?? "F5"}): ${why}`);
    say(t, "swap_gap", "the swap restarts the no-hit clocks");
    lastOurs = Math.max(lastOurs, t);
  };
  const flyAway = (t: number, block: string, why: string): boolean => {
    dagger(t, "never fly with the Knife on");
    wings -= 1;
    say(t, block, `Fly Wing (F2): ${why}; ${wings} left`, "safety");
    flyT = t;
    mode = "search";
    lock = null;
    lootKills = 0;
    searching = false;
    lastTaken = -1e9;
    if (wings <= 0) {
      say(t, "stock_stop", "the hotbar reads 0 Fly Wings: the run ends (no escape left)", "end");
      end = "stock_out";
      return true;
    }
    return false;
  };

  for (const m of sc.moments) {
    if (m.t > tEnd) break;
    const t = m.t;
    if (m.note) say(t, "loop", m.note, "note");
    // --- look
    hist.push([t, m.hp]);
    if (m.hit_on_us) lastTaken = t;
    if (m.miss_at_us) lastSwing = t;
    if (m.our_hit) {
      lastOurs = t;
      if (lock) {
        lock.hits += 1;
        lock.lastHit = t;
      }
    }
    const seen = [m.hit_on_us && "a hit on her", m.our_hit && "her hit", m.miss_at_us && "a Miss at her"].filter(Boolean).join(", ");
    say(t, "look", `look: HP ${pct(m.hp)}${seen ? `; the Battle Log: ${seen}` : ""}`, "look");

    // --- the safety rules (sustain: the escape first, alone; then a potion)
    const rate = rateHpS(hist, t, N("char.max_hp"));
    if (t - flyT >= 3) {
      let why: string | null = null;
      if (m.hp < N("strategy.fly_below")) why = `HP ${pct(m.hp)} is under ${pct(N("strategy.fly_below"))}`;
      else if (rate !== null && rate > N("strategy.fly_rate") && m.hp < N("strategy.fly_rate_below"))
        why = `HP falls ${Math.round(rate)} HP/s (over ${N("strategy.fly_rate")}) under ${pct(N("strategy.fly_rate_below"))}`;
      if (why) {
        if (flyAway(t, "wing_hp_fly", why)) break;
        continue;
      }
    }
    if (m.hp < N("strategy.potion_below")) {
      const recent = pots.filter((x) => t - x <= 2).length;
      const rose = potFrac !== null && m.hp > potFrac + 0.01;
      if ((!pots.length || t - pots[pots.length - 1] >= 0.7 || rose) && recent < 3) {
        pots.push(t);
        potFrac = m.hp;
        potions -= 1;
        say(t, "drink", `HP ${pct(m.hp)} is under ${pct(N("strategy.potion_below"))}: a potion (F1); ${potions} left`, "safety");
        if (potions <= 0) {
          say(t, "stock_stop", "the hotbar reads 0 potions: the run ends", "end");
          end = "stock_out";
          break;
        }
      }
    }
    if (m.boxes !== undefined || m.garm) {
      garmStreak = m.garm ? garmStreak + 1 : 0; // alarm_streak: consecutive detections
      const need = N("cmd.garm_confirm");
      if (m.garm && garmStreak < need) say(t, "garm", `a Garm Baby box (${garmStreak} of ${need} detections in a row): wait for the next`, "decide");
      if (m.garm && garmStreak >= need) {
        bossUntil = t + N("BOSS_AVOID_S");
        say(t, "garm_avoid", `a Garm Baby in ${garmStreak} detections in a row: no box fights until ${s1(bossUntil)}`, "safety");
        garmStreak = 0;
        if (flyAway(t, "garm_fly", "the boss's summon is on the screen")) break;
        continue;
      }
    }
    if (m.boss_line) {
      bossUntil = t + N("BOSS_AVOID_S");
      say(t, "boss_avoid", `a boss name in the Battle Log: no box fights until ${s1(bossUntil)}`, "safety");
      if (flyAway(t, "boss_fly", "a boss line")) break;
      continue;
    }

    // --- the boxes
    const boxes = m.boxes ?? [];
    const reach = boxes.filter((b) => b.reachable !== false);
    if (boxes.length) say(t, "boxes", `the detector: ${boxes.map((b) => `${b.species} ${b.cells} cell${b.cells === 1 ? "" : "s"}${b.reachable === false ? " (out of reach)" : ""}`).join(", ")}`, "look");

    // --- a fight starts?
    const dropped = hpDropped(hist, t, N("HP_DROP_PTS"), N("HP_DROP_S")) && t - flyT > 2;
    const hitNow = t - lastTaken < N("FIGHT_TAKEN_S");
    const swingNow = t - lastSwing < 1;
    if (mode !== "fight") {
      const boxOk = reach.length > 0 && t >= bossUntil;
      const held = boxOk && !hitNow && !dropped && !swingNow && mode === "after" && lootKills > 0; // --loot-first
      if (reach.length > 0 && t < bossUntil && !hitNow) say(t, "engage", `a box, but no box fights until ${s1(bossUntil)} (the boss guard)`, "decide");
      if (held) say(t, "fight_on", "a box waits: this fight's loot comes first (--loot-first)", "decide");
      if (hitNow || dropped || swingNow || (boxOk && !held)) {
        const by = hitNow ? "a hit on her" : dropped ? "her HP fell" : swingNow ? "a Miss at her" : "a box she can reach";
        mode = "fight";
        fightT0 = t;
        approaches = 0;
        searching = false;
        say(t, "fight_on", `a fight starts: ${by}`, "decide");
      }
    }

    if (mode === "fight") {
      let killedNow = false;
      if (lock) {
        if (killGapped(lock.hits, t - lock.lastHit, N("KILL_GAP_S"), N("KILL_GAP_HITS"))) {
          say(t, "kill", `${lock.hits} hits, then none for ${s1(t - lock.lastHit)}: the ${lock.species} died; its cells join the loot list`, "decide");
          kills.push(t);
          lootKills += 1;
          lock = null;
          killedNow = true;
          dagger(t, "the target died");
        } else if (t - Math.max(lock.lastHit, lock.t) > N("LOCK_NO_HIT_S")) {
          say(t, "unlock", `no hit of hers for ${s1(t - Math.max(lock.lastHit, lock.t))}: let it go`, "decide");
          lock = null;
          dagger(t, "the fight lost its target");
        }
      }
      if (!lock && !killedNow) {
        const cands = t >= bossUntil ? reach : [];
        const got = pick(cands, sc.values, N("vt.D0_PX"));
        if (got) {
          const tb = got.box;
          const others = cands.filter((b) => b !== tb).map((b) => `${b.species} ${Math.round(score(sc.values[b.species] ?? 0, b.dist_px, N("vt.D0_PX")))}`);
          say(t, "choose", `the ${tb.species} scores ${Math.round(got.score)} (worth ${sc.values[tb.species] ?? 0}, ${tb.dist_px} px away)${others.length ? `; beats ${others.join(", ")}` : ""}`, "decide");
          if (tb.cells >= N("APPROACH_CELLS") && approaches < N("APPROACH_MAX")) {
            approaches += 1;
            say(t, "approach_walk", `${tb.cells} cells away: walk to ${N("APPROACH_KEEP")} cells short of it, then look again`);
          } else {
            const w = tb.walking_px ?? 0;
            if (w >= N("LEAD_PX")) say(t, "lead", `its feet moved ${w} px (a walker): aim where it will be`, "decide");
            else if (w >= N("WALKER_PX")) say(t, "still", `its feet moved ${w} px: wait until it stands (${N("HOLD_MAX_S")} s at most)`, "decide");
            else say(t, "still", "a still screen, a still target: aim at it", "decide");
            if (knife && !knifeOn) {
              knifeOn = true;
              knifeT = t;
              say(t, "press_knife", `the Knife on (${doc.params["cmd.steal_opener"]?.value ?? "F4"}) for the new target`);
            }
            const far = tb.cells >= N("FAR_CELLS");
            say(t, "strike", far ? `strike: a SWORD cursor, ONE click (${tb.cells} cells away: the client walks her there, ${N("FAR_MAX_S")} s at most)` : `strike: a SWORD cursor, click (every ${N("BURST_GAP_S")} s until it connects)`);
            if (knife) say(t, "knife_hit", "hit with the Knife: Snatcher may steal before it dies");
            say(t, "lock_on", `locked on the ${tb.species}: her hits count from now`);
            lock = { t, hits: 0, lastHit: t, species: tb.species };
            strikes += 1;
          }
        } else {
          const recent = Math.min(t - lastTaken, t - lastOurs, t - lastSwing);
          if (dropped || recent < N("QUIET_SCAN_S")) {
            say(t, "ring_scan", m.ring_sword ? "no box: hover the 8 cells around her; a SWORD: strike there" : "no box: hover the 8 cells around her; no SWORD", "decide");
            if (m.ring_sword) {
              lock = { t, hits: 0, lastHit: t, species: "monster" };
              strikes += 1;
            }
          }
        }
      }
      if (knife && knifeOn && lock) {
        if (m.steal_cue) dagger(t, "a steal cue (the item popup)");
        else if (t - knifeT > N("bs.BARE_MAX_S")) dagger(t, `${N("bs.BARE_MAX_S")} s with no steal`);
        else if (m.hp < N("bs.BARE_HP_MIN")) dagger(t, `HP under ${pct(N("bs.BARE_HP_MIN"))}`);
      }
      const quiet = t - lastTaken > N("FIGHT_TAKEN_S") && !dropped;
      if (!lock && quiet && quietKillEnds(kills, t, fightT0)) {
        mode = "after";
        say(t, "fight_over", `no hit on her for ${s1(t - Math.max(lastTaken, fightT0))} and her target died: the fight is over`, "decide");
      } else if (!lock && quiet && !reach.length && !killedNow) {
        mode = "after";
        say(t, "fight_over", "nobody left to fight: the fight is over", "decide");
      }
      continue;
    }

    if (mode === "after") {
      if (lootKills > 0) {
        const got = Math.min(m.items ?? 0, N("LOOT_MAX_PICKS"));
        picks += got;
        say(t, "loot", `loot: ${N("LOOT_TRIM_HOVERS")} hovers at most, nearest first, around ${lootKills} kill${lootKills === 1 ? "" : "s"}: ${got} pickup hand${got === 1 ? "" : "s"}, ${got} picked`);
      }
      lootKills = 0;
      mode = "search";
      say(t, "search_again", "back to searching");
      continue;
    }

    // --- search
    if (!searching) {
      searching = true;
      say(t, "explore", "explore: aim for a region worth a visit");
    }
    if (t - lastWalk >= N("WALK_EVERY_S")) {
      lastWalk = t;
      const c = m.cursor ?? "walk";
      say(t, "walk_pick", `the walk target ${N("WALK_AHEAD")} cells ahead; the cursor there reads ${c.toUpperCase()}`, "look");
      if (c === "walk") say(t, "walk_click", "click: she walks");
      else if (c === "sword") {
        say(t, "walk_sword", "a monster under the walk target: strike it");
        mode = "fight";
        fightT0 = t;
        lock = { t, hits: 0, lastHit: t, species: "monster" };
        strikes += 1;
      } else say(t, "carve", "a wall: the cell leaves the route; plan again");
    }
  }

  if (end === "time") {
    say(tEnd, "loop", `${minutes} minutes are up: the loop ends`, "note");
    const last = hist[hist.length - 1];
    const hot = tEnd - lastTaken < N("END_HOT_S") || hpDropped(hist, tEnd, N("HP_DROP_PTS"), N("HP_DROP_S")) || (last !== undefined && last[1] < N("END_FLY_BELOW"));
    dagger(tEnd, "the run's end");
    if (hot) {
      wings -= 1;
      say(tEnd, "end_fly", "still in a fight (or HP under half): a Fly Wing first", "safety");
    } else say(tEnd, "end", `no hit in the last ${N("END_HOT_S")} s and HP over ${pct(N("END_FLY_BELOW"))}: no Fly Wing needed`, "decide");
    say(tEnd, "home", `a Butterfly Wing (${String(doc.params["HOME_KEY"]?.value ?? "F8")}) home, if the hotbar shows one: the run is over`, "end");
  }
  return { steps, end, kills: kills.length, picks, potions: p0 - potions, wings: w0 - wings, strikes };
}

const hits = (t0: number, n: number, gap = 0.5): Moment[] => Array.from({ length: n }, (_, i) => ({ t: Math.round((t0 + i * gap) * 10) / 10, hp: 1, our_hit: true }));

/** The example scenario: made-up screen readings and made-up worths (the lesson's numbers, NOT
 * the map's). The story: a choice by worth, two kills by the hit gap, a potion, a loot step, a
 * Garm Baby escape, a swarm escape, the safe end. */
export const EXAMPLE: Scenario = {
  name: "an example run",
  note: "Made-up screen readings and made-up worths (mystcase 300, cookie_xmas 150, cookie 100, cruiser 50): the lesson's numbers, not the map's. The runner reads the real worths at run time.",
  values: { mystcase: 300, cookie_xmas: 150, cookie: 100, cruiser: 50 },
  moments: [
    { t: 0.5, hp: 1, note: "She stands on the patrol loop. Nothing on the screen yet." },
    { t: 1.7, hp: 1 },
    { t: 2.9, hp: 1, boxes: [{ species: "cookie", dist_px: 90, cells: 3 }, { species: "mystcase", dist_px: 300, cells: 8 }], note: "Two monsters come into view." },
    ...hits(3.6, 6).map((m, i) => ({ ...m, hp: i < 2 ? 1 : 0.97, hit_on_us: i === 1 || i === 3, steal_cue: i === 1 })),
    { t: 7.8, hp: 0.95, hit_on_us: true, boxes: [{ species: "cookie", dist_px: 45, cells: 1 }], note: "Her hits stop: the Myst Case is gone. The cookie still bites." },
    { t: 8.3, hp: 0.95, boxes: [{ species: "cookie", dist_px: 45, cells: 1 }] },
    ...hits(8.8, 6).map((m, i) => ({ ...m, hp: 0.95 - 0.01 * i, hit_on_us: i === 2 })),
    { t: 13.0, hp: 0.9, note: "Her hits stop again, and nothing has bitten her for 3 s." },
    { t: 13.5, hp: 0.9, items: 2, note: "The loot step: the cells around the two kills." },
    { t: 15.0, hp: 0.9 },
    { t: 18.5, hp: 0.9 },
    { t: 19.7, hp: 0.9, boxes: [], garm: true, note: "The detector sees a Garm Baby (the boss's summon)." },
    { t: 20.7, hp: 0.9, boxes: [], garm: true },
    { t: 23.0, hp: 0.9, boxes: [{ species: "cruiser", dist_px: 200, cells: 5 }], note: "Somewhere else on the map after the teleport." },
    { t: 24.2, hp: 0.9, boxes: [{ species: "cruiser", dist_px: 160, cells: 4 }] },
    { t: 300, hp: 0.43, note: "(later) Her HP is low after a long fight, and still falling slowly." },
    { t: 302, hp: 0.41 },
    { t: 304, hp: 0.39 },
    { t: 306, hp: 0.46 },
    { t: 400, hp: 0.5, boxes: [{ species: "cookie_xmas", dist_px: 120, cells: 4, walking_px: 18 }], note: "(later) A walking cookie_xmas: the lead press." },
    { t: 401, hp: 0.44, hit_on_us: true, note: "A swarm arrives: her HP falls fast." },
    { t: 402.5, hp: 0.44 },
    { t: 1499, hp: 0.85, note: "(the rest of the 25 minutes: more of the same)" },
  ],
};
