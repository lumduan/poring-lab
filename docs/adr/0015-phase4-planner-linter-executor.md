---
doc_type: decision
hypothesis: null
status: GO
role: null
verdict_date: 2026-10-04
verdict_ticket: null
supersedes: null
related: []
next_action: Build in order once Phase 2-3 perception and ADR-0005/0016 allow: the KB generator (local, never committed), the plan schema + linter, then the behavior-tree executor, before any LLM.
---

# ADR-0015: Phase 4 is plan → lint → approve → execute (an LLM planner, a deterministic executor)

- **Status:** ACCEPTED (Batt, 2026-10-04). Proposed on 2026-10-03 (Batt's item 5). Nothing is
  built yet. Batt's ruling, as accepted:
  - static server data (mob_db, spawns, the element table, maps) is game knowledge at PLAN time;
  - live state stays forbidden as decision input (ADR-0007);
  - behavior trees for the executor.
- **Gates (unchanged):** Phase 4 still needs Phase 2–3 perception, ADR-0005 implemented, and the
  environment interlock ([ADR-0016](0016-environment-interlock.md)).
- **Roadmap rows this would supersede** ([ROADMAP](../ROADMAP.md)):
  - Phase 4 "Fast loop: an FSM …": the executor below replaces the FSM.
  - Phase 6 "the LLM emits intents only, consumed by the FSM": the LLM becomes Phase 4's planner.
  - Phase 6 keeps the social and chat research.

  The rows are pointed at this ADR now. They are rewritten only if it is accepted. ➡️ Accepted
  2026-10-04: the ROADMAP rows are rewritten in the same change.

## The flow
```
bot owner (console, HUMAN) ── request: natural language, or plan JSON directly
        │
        ▼
planner: a small LLM with READ-ONLY tools over the knowledge base ── plan JSON (schema)
        │                                   ▲  lint errors, readable, fed back (bounded retries)
        ▼                                   │
linter: schema → semantics → simulation ────┘
        │
        ▼
approval: the plan as blocks in the console; the owner accepts, edits or rejects
        │
        ▼
executor (deterministic, the fast loop): pixels → perception → step logic → input
        │
        ▼
mux (/internal/agent, source=bot; lease, log, ADR-0016 interlock) → the one session
```

**Hard lines:**
- **The LLM never drives input.** It writes a plan, and only the executor acts. The executor never
  calls the LLM inside its loop.
- **Plans come only from the bot owner.**
- **In-game chat is DATA, never instructions.** Chat text can reach the planner only as quoted,
  labelled data. No step type can be created from chat. Every other player's text stays local and
  pseudonymized (CLAUDE.md rule 9).

## The knowledge base (KB)
- **Built from the rAthena data at the pinned ref**, pre-renewal, in the rathena container:
  `/opt/rathena/db/pre-re`. It holds:
  - `mob_db.yml`: element, level, HP, race, size, drops;
  - `npc/pre-re/mobs/**`: spawns per map;
  - `attr_fix.yml`: the element table;
  - `skill_db.yml`;
  - warps (`npc/pre-re/warps/**`);
  - the map caches.
- **The client's GAT** adds the walkability and altitude graph (`poring_dataset/gat.py`,
  `walk_graph`).
- **Licensing:** rAthena is GPL-3.0, so its data stays out of the repository. A generator script
  builds the KB **locally at run time** (`data/kb/`, gitignored). Client data (GAT) is read from the
  GRF into `/dev/shm`. Neither is ever committed (THIRD_PARTY.md; Batt 2026-10-03).

### Ruling (ACCEPTED, Batt 2026-10-04): static server data is game knowledge at PLAN time
- **Allowed at plan time:** static data files (monster stats, spawn tables, the element table, map
  geometry). A human player knows these from wikis. They describe the game, not its live state.
- **Still forbidden at decision time** (CLAUDE.md rule 1, ADR-0007): packets and live server state
  (positions, HP, who is online). The executor perceives only through `Env.grab()`.
- **On the community server** the KB is a **prior** only: its data may differ from ours, and the
  pixels decide.

### PROPOSED ruling (Batt's note, 2026-10-04; NOT YET CONFIRMED): static game data at RUNTIME, for perception
- **Proposal.** Static game data may also be used **at runtime by perception**, not only at plan
  time. That covers:
  - monster walk speed and the engine's movement rules (random-walk timing, chase);
  - map walkability (GAT);
  - spawn areas;
  - portal and NPC positions.

  The user is the tracker's motion model ([phase3-plan.md](../phase3-plan.md) §6b): units are
  predicted through occlusion and off-screen instead of re-detected.
- **Unchanged.** Live server state stays forbidden at decision time (CLAUDE.md rule 1, ADR-0007):
  packets, positions, HP, who is online.
  - Packets remain offline ground truth.
  - They **evaluate** the tracker and tune the parameters the rules leave open; they never feed it.
- **Licensing unchanged.**
  - The KB is generated locally from rAthena (GPL) and never committed.
  - The movement rules are re-implemented from their documented behaviour, never copied (the
    `walk.py` discipline).
- **On the community server:** a prior only; the pixels decide, as above.
- **Status:** awaiting Batt's confirmation. Until he confirms, the deployable tracker (phase3-plan.md
  T3) does not run.

## The linter: layers, cheapest first
| Layer | Checks | On failure |
|---|---|---|
| 1 · schema | Pydantic plan models: known step types, typed arguments, bounded counts and durations | "step 3: `hunt.count` must be 1..500" |
| 2 · semantics | Map exists; the target mob spawns on that map (KB spawns); the skill is owned and SP-affordable; the item exists; the warp exists | "Poring does not spawn on prt_church" |
| 3 · simulation | Walk the plan on the GAT/warp graph (`walk.py`, a clean textbook A* that replaced the GPL `paths.py` port on 2026-10-04, for legs ≤ 128 steps; waypoints beyond). Estimate time; check reachability, element matchups (attr_fix) and the stop conditions | "prt_fild08 (12,345) is unreachable from the spawn point" |
| 4 · approval | The owner sees the plan as blocks: route, targets, stop conditions, time | the owner edits or rejects |
| 5 · runtime | The executor's stop conditions: HP floor, unknown screen, the human lease, a step timeout, perception confidence | stop, release everything, report |
| 6 · interlock | ADR-0016: the environment is attested | the mux refuses (`environment_unattested`) |

Errors are short, human-readable sentences: the owner reads the same text the planner gets back.

## The executor
- **Option A:** a plan interpreter. Each step type is deterministic code.
- **Option B: behavior trees — CHOSEN (Batt, 2026-10-04).** Sequence, selector and condition nodes with action
  leaves are a natural fit for "hunt X until Y unless Z". They are easy to show as blocks in the
  approval view and easy to test offline against recorded sessions.
  - **Inspiration, ideas only:** [maxmx03/YggAI](https://github.com/maxmx03/YggAI) (GPL-3.0); no
    code is read for porting (THIRD_PARTY.md).
  - Our trees are written from scratch.
- **Path planning:** the GAT walk graph plus a shortest-walk A* (`walk.py`; it matched the old rAthena port on 2534/2540 recorded walks) inside 128 steps; a
  waypoint and warp graph across longer routes.

## Consequences
- **Build order once accepted:**
  1. KB generator and its tests;
  2. plan schema;
  3. linter layers 1–3 with offline tests;
  4. executor on recorded sessions (no live input);
  5. approval UI;
  6. the LLM planner last.
- **No live automation** until ADR-0005 and ADR-0016 hold.
- The planner model runs locally (Ollama on this host shares the GPU with vision; its VRAM cap
  applies) or is a hosted model given only plan-level text. That choice is Batt's at build time.
