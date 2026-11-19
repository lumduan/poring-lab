---
doc_type: plan
hypothesis: null
status: "ACTIVE (Batt 2026-11-18: \"adjust the pre-run rules first ... locked like this it is very hard when I teach others and have them build their own along with me\")"
role: null
verdict_date: null
verdict_ticket: null
supersedes: null
related: [../adr/0020-block-programming-flows.md, ../adr/0023-learner-mode.md, ../adr/0006-sanctioned-test-environments.md, fullscreen-client.md, player-mode.md]
next_action: "Step 1 BUILT (any character, ADR-0020 Amendment Q) and moved to the Settings page 2026-11-19 (Amendment R: any the default everywhere, the lab too; known = the characters remembered there by its Remember button). Batt tests one step at a time; the next ones in section 4 wait for him."
---

# A Run's start rules, for teaching

**Batt, 2026-11-18 (translated):** "Adjust the pre-run rules first: standing in the safe spot, the
character's name and many other things. Locked like this it is very hard when I teach others and
have them build their own along with me. No need to lock the character's name: a user should be free
to create a character. Teaching many people at once, if all had the same name it would confuse at
once. Think ahead about such things."

The picture to plan for: a class. Each learner has their own install (any hardware, ADR-0026), their
own Windows PC with the game, and their own character on the teacher's server (a declared
environment, ADR-0023), made by themselves: any name, any job, any level, any UI layout, any screen.

## 1. Every rule a Run checks before its first press

Sources: the runner's player start and its read-only check (`scripts/dungeon_hunt.py`,
byte-pinned: `start_check`, `run()`), the player (`scripts/flow_play.py`), the helper
(`scripts/flow_run.py`), the page (`lib/flow/settings.ts` `startChecklist`).

| # | Rule | Before | Now | Kind |
|---|---|---|---|---|
| 1 | Identity: the name plate and the job | the lab Rogue's pictures (Thief8fce, rogue); any other character refused | the Settings page, "who may play a Run" (Amendment R): any (the default), known (the characters remembered there), mine | UNLOCKED (step 1), a Settings choice |
| 2 | The game on the screen | misread the desktop | the Run waits for it (ADR-0020 Amendment P) | safety |
| 3 | The console in ASSIST or BOT | | unchanged | safety |
| 4 | The chat input closed | | unchanged (text left in it would go to public chat) | safety |
| 5 | The map: the minimap's picture is the node's map | | unchanged: the project's map node, the user's choice | the project |
| 6 | The start cell: on the map's open ground, reaching its search area | | unchanged: the walk plans from it | needed (see 4c) |
| 7 | The bag under WEIGHT_MAX (48 %) | | a setting (block), 10-90 % | setting |
| 8 | Fly Wings on fly_key, at least PLAYER_MIN_WINGS (5) | | a setting, 1-99 (the run's escape: never 0) | setting + safety |
| 9 | Heal items on heal_key, at least PLAYER_MIN_HEALS (5) | | the COUNT a setting (0-99); the ITEM fixed: White Potion (or the Christmas candies with heal_candy) | still LOCKED (see 4a) |
| 10 | Butterfly Wings on home_key | | never refuses | setting |
| 11 | The Knife on knife_key, the dagger worn | | only with the knife_swap switch on | setting |
| 12 | The keys (F1 heal, F8 fly, F9 home, F4 knife, F5 dagger) | | settings (the project's functions) | setting |

Not checked before the run, but assumed by it (a learner meets them in the first minutes):

| # | Assumption | Today | Kind |
|---|---|---|---|
| 13 | The interface layout: Basic Info, the hotbars, the chat window, the minimap where the lab's are | the lab's measured places (LAB_PANELS) | still LOCKED (fullscreen plan, milestone 3: find the panels by their picture) |
| 14 | The chat window's tabs: Battle Log, then Chat | the lab's standard (docs/client/rathena-client.md) | a setup step for each learner |
| 15 | The map: xmas_dun02 only | the hunt core knows xmas_dun02 (its route grid, its monster model) | still LOCKED (4d) |
| 16 | The character's numbers: max HP 5070, max SP 530 (`--char rogue`) | the HP-rate escape (fly_rate, HP per second) uses the max HP | still LOCKED (4b) |
| 17 | The Rogue's Knife swap | a Rogue skill's trick; another job gains nothing but loses nothing | switch it off (knife_swap) |
| 18 | Words that assume who plays ("she stands on xmas_dun02", "her cell") | the block titles and the runner's lines | wording (4e) |

**The game's language (Batt 2026-11-18 ~22:1x, restating 10-26 and 11-11: "I do not want
poring-lab tied to the English interface only: Korean, Thai and others too; the project is public,
people may try it on rAthena servers in other languages").** No cue may read English UI text: cues
come from sprites, shapes, colours, places and digits; only the console's own UI stays English.
The first non-English client a Run saw was rog101's (Thai, 21:55 and 21:57; another server's
character, refused before any input). Known English-bound pieces and what to verify:

| # | Piece | Bound to the language how | Status |
|---|---|---|---|
| 19 | The Battle Log reader (`battle_log.py`) | an English line grammar ("inflicts ... damage points") | KNOWN (gef10-eyes-loot.md section 4); bare_steal reads a line's COLOUR instead |
| 20 | The chat window's tab check | the tab LABELS' pictures ("Battle Log", "Chat") | KNOWN: per language, or by place and order instead of label |
| 21 | Screen signatures (login, dialogs, death dialog) | pictures cut on the English client | `state@locale` variants exist (`signature_variants`); each language needs its cut |
| 22 | The job line (cut-job pictures) | the job's NAME in the client's language | not compared under any / known (the Settings page); the name line under known is a PICTURE, any script |
| 23 | Basic Info's weight, the hotbar counts, the minimap's picture | digits and pictures, maybe anchored on labels or places | TO VERIFY on a Thai client: rog101's start check read none of them (its layout differed too) |

## 2. Step 1, built 2026-11-18 (ADR-0020 Amendment Q)

- ➡️ **SUPERSEDED IN PART 2026-11-19 (ADR-0020 Amendment R, Batt): the choice is on the SETTINGS
  PAGE ("who may play a Run"), saved and used at once with no restart; `.env`'s `RUN_IDENTITY` is
  no longer read.** `any` is the default of every install, the lab's too. `known` plays only the
  characters remembered on that page: a person types a name for the list and presses Remember
  with the character in front (Basic Info open at the top left); the Run helper reads the name
  line once (pixels only). No terminal step, no slot limit (up to 50). The lines below are the
  history of step 1.
- `RUN_IDENTITY` in `.env`: `any` (empty = any) for every new install; `mine` for an install that
  wants only its own character. An unknown word = `mine`.
- `crusader.check(db=False)` (the player path only) compares no name and no job under `any`; a
  black game region still fails. A GM line always checks the lab's character.
- The identity line reads "any character: a Run does not check the name or the job" on the
  page's checklist, in the Run's own check and in its log.
- ➡️ **2026-11-18 ~22:1x (Batt chose it): the lab runs `known`** -- any character THIS install
  knows (its name plate cut once: `crusader.py --char K init --name N`, then `cut-name`); another
  server's character has no reference here and is refused at the first line. The reason: a Run
  was pressed twice (21:55, 21:57) while rog101, a character of another server, was in front;
  under `any` only its different interface stopped it. Batt also wants the bot on rog101's
  server: that is an ADR-0006 decision of its own, not made by this.
- ~~The lab keeps `mine`~~ ➡️ SUPERSEDED 2026-11-18 ~21:2x (Batt: "any, so I can test it myself
  too"): the lab runs `any` too. The known risk: the community client shares its Windows PC
  (ADR-0006), and the name plate was the Run's only pixel proof that the lab's client is in front;
  the map and start-cell checks remain (ADR-0020 Amendment Q). `mine` again is one line.

## 3. Many learners at once

- Names: a server refuses a second character of the same name, so a class never needs one name;
  with step 1 nothing in a Run asks for one.
- Each learner's install keeps its own settings, its own runs and logs (`settings/`, `data/`):
  nothing is shared between installs, so learners never see each other's runs.
- Other players on the same map: the bot sees them as players, not monsters (the detector's
  classes); several bots on one map compete for the same monsters. A class is better spread over
  maps or channels (a teaching choice, not a rule).
- Other players' names and chat stay local and pseudonymized (CLAUDE.md rule 9): a learner's
  install records only what its own Run needs.

## 4. Next steps, for Batt to pick (recommended order)

- **4a. Any heal item (rule 9):** count and check Red / Orange / Yellow / White Potions (and
  others) on heal_key, the item read from its icon. A beginner has Red Potions. It changes the
  runner's player start: a dungeon@ step with its own proof (the runner is byte-pinned).
- **4b. The character's numbers from the screen (rule 16):** max HP and SP read from Basic Info
  (its digits are read already), so the HP-rate escape fits any character. A dungeon@ step.
- **4c. A friendlier start cell (rule 6):** say which cells are fine ("step off the portal") and
  show the map's open ground on the page's path map; the rule itself stays (the walk needs it).
- **4d. Other maps (rule 15):** a hunt core per map needs its route grid (from the learner's own
  client data, generated locally) and a monster model for its monsters. The biggest piece.
- **4e. Neutral words (rule 18):** "the character" for "she / her" on the page and in the block
  titles (the runner's own lines stay until its next step).
- **4f. Any interface layout (rule 13):** the panels found by their picture, as the login
  dialogs already are (fullscreen plan, milestone 3).
