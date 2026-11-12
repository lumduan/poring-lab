---
doc_type: plan
hypothesis: null
status: PROPOSED (decided by Batt 2026-11-12: build after ADR-0025's SQLite)
role: null
verdict_date: null
verdict_ticket: null
supersedes: null
related: [../adr/0023-learner-mode.md, ../adr/0025-run-records-sqlite.md, ../setup/new-lab-host.md, rogue-xmas02.md]
next_action: "After the SQLite build: a design pass over dungeon_hunt.py's setup (every GM line it types) and a --player-mode that types none."
---

# Player mode: the hunting bot without GM commands

Written 2026-11-12 11:40 ICT from `date`.

## Why (Batt, 2026-11-12, translated)

- The context: ADR-0023's declared mode lets a learner without their own server run the bot on a
  public rAthena whose owner permits bots. But the hunting runner's SETUP types GM commands:
  - `@warp` to the stand and the map;
  - `@item` top-ups and `@heal`;
  - `@monsterignore` for immunity;
  - `@killmonster2` with `--clear-map`.
  A learner is not a GM there, so those lines fail, or show up in public chat.
- Batt: "Understood. In the future we will add it anyway, e.g. warping through the Kafra." And:
  "Do player mode, after SQLite."

## The scope (first cut)

1. **`--player-mode` types NO GM command, ever.** A test scans the setup for "@" lines under it.
   - The person brings the character to the map and stocks potions / Fly Wings themselves.
   - The bot reads the stock from the hotbar and the weight from pixels, as today, and refuses to
     start below a minimum.
2. **The hunt loop is unchanged.** Its escapes use items the player carries: the Fly Wing, the HP
   escape. Every lab-only step stays out:
   - the MVP kill protocol: the bot escapes instead (4CS-4CU);
   - immunity;
   - the clear-bag through `@` lines;
   - stagings.
3. **The run ends safe** by the player's own means: a Fly Wing away from monsters, or sitting. Never
   a `@warp`.
4. **Later (Batt):** walking to a Kafra and warping through its menu (the UI gate's known steps),
   buying from an NPC shop, selling loot.

## Not in scope

- Anything that reads or changes the server beyond pixels and input (CLAUDE.md rule 1).
- Lab research numbers: a player-mode run on a declared server is never counted (ADR-0023
  decision 2).
