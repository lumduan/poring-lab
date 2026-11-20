---
doc_type: plan
status: PROPOSED
role: null
verdict_date: null
verdict_ticket: null
supersedes: null
related: [live-blocks.md, flows-studio.md, ../adr/0020-block-programming-flows.md, ../../packages/poring_flow/src/poring_flow/models.yaml, ../../packages/poring_flow/src/poring_flow/settings.py, ../../scripts/slot_items.py, ../../scripts/bag_count.py]
next_action: "Batt reads it; then step 1 (the blocks' words and pickers, no runner change). The ML page is NOT started (Batt 2026-11-20)."
title: "Roles, not names: any weapon for the swap, any monster from the player's own model (plan; the ML page later)"
date: 2026-11-20
owner: Batt
---

# Roles, not names (plan, 2026-11-20)

## 1. What Batt asked (2026-11-20, translated)

> "Try not to lock item names or kinds, like 'knife': this game has many classes and many weapons
> (axe, sword). Locking it like this ties it down. Make it the broad word WEAPON, so other classes
> can use it too: do it once, use it for many classes.
> The same for monster names, like Garm Baby: do not hard-code them into a block; let the user
> take them from the model file that was trained.
> Later I will make an ML page where a user trains a model easily, in steps: record a video (for a
> set time), move the boxes, put the labels. That ties to what I just said: take the monster names
> from the trained model. We did this at the start, when you had me label monsters myself, like the
> Poring. Plan these too, but do not make the ML page now."

The labelling he means is the `/qa` hand-check editor (2026-10-04, "B6"): he dragged boxes and
picked each one's class on the lab's frames. It left the top bar on 11-10; the page remains.

## 2. What is fixed to one name today (the inventory)

| Where | What is fixed | The role it really is |
|---|---|---|
| settings.py group `knife` ("the Knife swap", "Batt's Knife swap") | knife_swap, knife_max_s, knife_hp_min, bare_ready, steal_cue, swap_gap, knife_key | a WEAPON SWAP: an idle weapon, the fighting weapon back on |
| the ready-made flow (project.ts) | tab `knife`: knife_on -> wield_knife (F4), knife_back -> wield_damascus (F5) | wear the idle weapon / wear the fighting weapon |
| the runner's SlotRole "opener" (dungeon_hunt.py) | item 1201 "the Knife" on its key; the start check's "knife" and "dagger" lines | the idle weapon's slot: any weapon the player picks |
| the runner's SlotRole "heal" | the White Potion (the 11-20 live warning: "F1 shows an Orange Potion, not a White Potion") | a HEAL item: any healing item the player picks |
| settings garm_fly, garm_confirm, alarm_fast, alarm_solo, GARM_FRESH_S (labels "Garm Baby alarm ...") | the words "Garm Baby" | an ALARM monster: fly away when seen |
| dungeon_hunt.ALARM_CLASSES | `garm_baby`, the fallback when a model names no `alarm` list | the model's own alarm list (models.yaml `alarm`; the hook exists since dungeon@9.57) |
| fly_first / BOSS_AVOID_S ("a boss seen") | the boss classes of xmas02's model | the model's boss classes |

What is already right:
- **The monsters a box attacks** come from the node's model. They are `use_model`'s classes and
  models.yaml's `strikes`; `mob(<id>)` values are displayed through the local KB.
- **The alarm's classes** come from the model's `alarm` list (dungeon_hunt.alarm_classes), with
  `garm_baby` only as the fallback.
- **Items on the hotbar** are told by their own icons (slot_items, any item of the archive). The
  bag census (bag_count) reads every item in the bag the same way.

## 3. The design: a ROLE with a value the player picks

- **Settings and blocks name the ROLE.** "the weapon swap", "the idle weapon", "the fighting
  weapon", "the heal item", "an alarm monster". The VALUE is the player's pick. Our values stay
  the defaults (the Knife, the White Potion, garm_baby): everything stays user-settable (Batt
  11-13).
- **Pickers, not text boxes** (Batt 11-14).
  - An item role's picker lists what the player HAS, read from the screen:
    - the hotbar's items (slot_items);
    - the bag (bag_count; once its trials pass);
    - for a weapon, only items whose type is a weapon in the local item table.
  - A monster role's picker lists the CLASSES of the node's model (models.yaml / the model file's
    own names), shown by the KB's display names.
  - Nothing is typed, and a value that is not on the list is refused by the linter.
- **One technique, many classes.** "Batt's Knife swap" becomes "the weapon swap (Batt's
  technique)". A Rogue picks the Knife and the Damascus. A swordsman picks a sword and an axe, or
  whatever the class wears. The runner's timing settings (knife_max_s -> swap_max_s, ...) keep
  their values.
- **Monsters come from the model.** A block that tests "is a Garm Baby in view" becomes
  "is <an alarm monster> in view", the monster picked from the model. A model trained later (the
  ML page) brings its own classes, and the pickers list them without a code change.

## 4. The pinned runner

`dungeon_hunt.py` is byte-pinned by the A/B proofs, so a value it holds (SlotRole's 1201, the
heal item) cannot simply be edited.
- **The path: a NEW runner version** whose new arguments take the role values (the idle weapon's
  item ids, the heal item's ids). Their defaults are today's values.
- **An equivalence proof first:** with the defaults, every pinned A/B argv runs the same
  statements (huntstate_check / the stage proofs re-baselined in ONE commit, recorded).
- It is done in a window with no series running ("never change main's code while a series runs").

## 5. The order

1. **The words and pickers (no runner change).**
   - Settings labels and the ready-made flow's names become roles. The flag names stay, so the
     argv is unchanged; the drift tests are kept or re-pinned.
   - The pickers for item roles read the hotbar's items. The pickers for monster roles read the
     node model's classes.
   - The settings blocks' tests.
2. **The runner version.**
   - The idle weapon / heal item as arguments, defaults = today's.
   - The equivalence proof; the start check's lines say the role ("the idle weapon on F4: the
     Knife").
3. **Monster roles everywhere.** Every alarm / boss / target setting reads the model's lists
   (alarm, strikes, a new `bosses` list). `garm_baby` stays the fallback of the lab's model only.
4. ➡️ **Inserted by Batt 2026-11-20: waypoints and NPC talks, recorded by demonstration**
   ([waypoints-npc-recording.md](waypoints-npc-recording.md)), after steps 1-3 and BEFORE the
   ML page.
5. **(LATER, not now: Batt)** The ML page:
   - record a video for a set time (record_session's time box);
   - move the boxes (the `/qa` editor's drag);
   - put the labels (classes the user names);
   - train (guarded_build execdev:vision);
   - register the model (a models.yaml-like entry with its classes and its alarm / boss lists).
   The pickers of step 3 then list the new model's classes on their own.

## 6. Not in this plan

- No new technique or new class behaviour: the swap's timing is Batt's technique as it is.
- The map-specific runner data (xmas_dun02's routes, stands) stays per map; that is its own work.

## Amendment 1 (2026-11-20 14:29 ICT from `date`): step 2 needs NO runner edit

- **The item roles are module-level TABLES the runner reads at call time:**
  - `dungeon_hunt.SLOT_ROLES`: "opener" = (1201,) the Knife, "potion" = (504,) a White Potion,
    "home", "cane", "candy" (read at line ~1790, `sr = SLOT_ROLES[role]`);
  - `STOCK_ITEMS` = {"potion": 504, "fly": 601};
  - `HEAL_ORDER`.
- **The Run player already patches the runner in-process for a player's Run**
  (`player_owns_the_start`: the refusals become warnings).
- **So step 2 is the same kind of patch, in flow_play (not pinned), for the length of one Run:**
  the picked items replace those table entries (e.g. "opener" = the player's idle weapon's ids,
  "potion" = the heal item's).
  - `dungeon_hunt.py` stays byte-identical, so no proof is re-baselined.
  - The lab's A/B runs (no player's picks) read the tables as they are.
- **The picks' source:** new settings blocks (an item picker over the hotbar's / the bag's items;
  for a weapon, only items whose type is a weapon). They are carried to the Run like the other
  settings.
- **Tests:** a Run with picks plays the runner's own start check and stock rules on the picked
  ids; a Run without picks equals today's (the same tables, an identity test).
