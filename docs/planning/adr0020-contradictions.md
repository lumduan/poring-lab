---
title: "ADR-0020: the 19 contradictions MW1 found, each with a recommended resolution"
status: PROPOSED
date: 2026-10-08
owner: Batt
extends: docs/adr/0020-block-programming-flows.md
gate: "Batt decides each item (2026-10-08 ~16:00: 'Bring the 19 ADR-0020 contradictions with the MW1 merge; I'll decide them'). Nothing here changes the ADR or the code until he does."
---

# ADR-0020: the 19 contradictions MW1 found

MW1 (`packages/poring_flow`: the IR, the linter, the simulated executor) had to pick ONE reading
wherever ADR-0020 said two things. Each pick is provisional. For each item below:
- what the ADR says;
- what MW1 built;
- the recommendation (Claude's, not a decision);
- what changes if Batt accepts it.

Section numbers are ADR-0020's.

| # | topic | recommendation | changes if accepted |
|---|---|---|---|
| 1 | re-fire bound on handlers | **Keep MW1.** Any bound counts (rearm, until, cooldown_s, max_per_min, max_per_run), and a condition made only of momentary cues (`map_load_seen()`, `engagement_seen()`) is self-bounded. | §5's row: "a re-fire bound" in place of "rearm or cooldown". Code: none. |
| 2 | `in` membership | **Allow it, restricted** (MW1): `x in [...]` / `not in` only against a LITERAL list of typed refs or a list variable; never another expression. Statically checkable, and species / keep lists need it. | §7.2: one line allowing it. Code: none. |
| 3 | node paths | **One grammar:** named nodes by name, statements by index: `main.4`, `handlers.drink.1`, `maps.prt_fild08.events.hp_low.0`, and `global` for the global pairs. Replaces MW1's `drink:` form and §1's `handlers.1.body.0`. | §1, §5, §13.6.9 examples. Code: MW1's path printer (small), messages only. |
| 4 | `assert_save_point` | **A CORE block** (MW1). It sends no input, so it is a check, not an L1 skill. | §13.8: remove it from the new L1 concepts. Code: none. |
| 5 | training-cost contingency and map prep | **Keep MW1's conservative reading:** contingency on every part, and map prep per NEW map (iz_dun00 and iz_dun01 are two maps). Byalan's map prep becomes 10.4 h (the doc says 5.2 h). | §1 / §3 / §5 numbers aligned to MW1's (collect 8.45 h, compute 15.42 h, night 24.5 h, mixed 30.5 h, effective day 44.1 h). |
| 6 | an unsupported binding | **Split the severity.** An unsupported binding is a READINESS item: listed in the report, it blocks the RUN (the run-start check refuses), not the design's approval. Today no real flow lints clean under MW1's ERROR, which would make MW2 useless until every binding exists. | §5 layer 2 + §12 "Today" + §13.4 agree. Code: a `readiness` severity in the linter; the run-start gate refuses on it. |
| 7 | the dialog-close name | **One block, `close_dialog()`** (L1 `npc.close`), idempotent: it closes only if a dialog is open. `close_npc_dialog()` stays a Python-import ALIAS that warns. | §13.6.8: the example renamed. Code: the alias + a warning. |
| 8 | route labels | **Keep MW1:** messages name cells and NPCs. The canvas (MW2) maps them back to its node labels on screen. The IR holds no diagram labels. | §13.5: the example message rewritten. |
| 9 | the weight rule vs the loops rule | **Keep MW1:** one finding per cause. The loops rule defers to the weight WARNING on the same loop; `< 50` gets the INFO, applied literally. | §13.5: a precedence sentence. |
| 10 | `position()` / `current_map()` | **ACTIVE** (MW1, as §2.3's amendment says): they type `/where`, so never in an event condition. A future PASSIVE `minimap_position()` (outdoors only) could be added when needed. | §2.3: the passive entry replaced, not only amended. |
| 11 | `until` + `rearm` on one event | **Mutually exclusive** (MW1): a lint ERROR. `until` means repeating, `rearm` means one-shot (§13.6.7). | §13.6.7: one sentence. |
| 12 | `Exit.item`'s type | **`ItemRef` or a variable TYPED `ItemRef`** (layer 1 checks the variable's type). MW1 accepts any variable today. | §13.1 sketch. Code: the type check (small). |
| 13 | event order within a class | **An explicit rank inside each class**, defaulting to §13.6.3's table order: `unintended_engagement` before `hp_low` (stop the fight before drinking). FIFO only between user events of equal rank. A safety pair should never depend on arrival order. | §13.6.3 + §2.5 rule 4. Code: a `rank` field (the IR schema, versioned) and the queue's ordering. |
| 14 | ties-rule noise | **WARNING only for the same class AND the same rank with overlapping conditions**; INFO otherwise (the order is already decided by #13). This removes the 4 warnings in Batt's example. | §13.6.9. Code: the rule's severity. Depends on #13. |
| 15 | the three safety events | **Always on by construction:** the compiler adds `dead`, `hp_critical` and `unexpected_map` to EVERY flow (workflow or plain main flow), shown as locked global events on the canvas. A flow may only make them STRICTER. The lint check becomes "not weakened". | §13.6.8. Code: the compiler injects them; the lint rule changes. |
| 16 | `repeat` in the Python view | **Keep MW1:** `for _ in range(n)`, the one bare-`_` exception to the underscore rule. | §7.2: documented. |
| 17 | `max_runtime_s` | **Default 4 h (14,400 s), maximum 24 h (86,400 s).** A live run then gets a human look at least every 4 h unless the owner raises it at approval. MW1's provisional default is 24 h. | Q8 closed. Code: the default. |
| 18 | where the linter runs / its routes | **The linter runs in the backend at run time** (L3 data is local, never shipped). It routes with the EXECUTOR's planner (`poring_dataset.walk.walk_path`, the client's own path rules), not MW1's small A*. Until then, a cross-check test on the sheet maps. Two planners that can disagree let a flow lint clean and fail live. | Q15 closed. Code: swap the planner (or the cross-check test first). |
| 19 | "maps a route crosses" | **IR 2, not IR 1:** `walk_to` is per map and exits are explicit, so in IR 1 a route crosses no maps. Mark §13.3's sentence "IR 2". | §13.3: one marker. |

## Also found: gaps in Batt's §13.6.8 example (the linter reports them; not contradictions)
Each needs a choice in the EXAMPLE, not in the ADR:
- `store-all` keeps the Butterfly Wings and potions, NOT the Fly Wings that `hp_critical`'s escape
  uses. Add Fly Wing to the keep list.
- `kafra_store` needs Basic Skill 6 (L1 `storage.deposit`); nothing in the flow gets it. Add a
  precondition, or a `learn_skill` step.
- farm's `while weight_percent() < 50` can never end: no block in farm picks items up (`loot` is
  unsupported today, open question 21). It needs a second bound (time, kills) until loot exists.
- A death before `town.1` respawns at an unknown save point. Add an `assert_save_point` (#4) at the
  start.
- farm's engagement policy decides by species, which today's detector cannot name (one `monster`
  class). It needs the species head (v1+ labels) or a policy by size.
- Boss 9109 (synthetic) is aggressive and on neither list. Add it to IGNORE (flee) or TARGET.
- With the REAL L2 file, `L2.window.death_dialog` and `L2.window.dialog` are not bound. They are
  L2 bindings to cut (anchor templates), a readiness item under #6.

## Order of decisions that unblock the most
1. **#6 (readiness)** unblocks MW2: flows can be designed and simulated today.
2. **#15 (always-on safety events)** fixes a whole class of omissions by construction.
3. **#13, then #14** (rank, then noise).
4. **#18** (one planner): lint must agree with the executor before any live run.
5. The rest are wording or small code.
