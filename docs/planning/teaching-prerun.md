---
doc_type: plan
hypothesis: null
status: "ACTIVE (Batt 2026-11-18: \"adjust the pre-run rules first ... locked like this it is very hard when I teach others and have them build their own along with me\")"
role: null
verdict_date: null
verdict_ticket: null
supersedes: null
related: [../adr/0020-block-programming-flows.md, ../adr/0023-learner-mode.md, ../adr/0006-sanctioned-test-environments.md, fullscreen-client.md, player-mode.md]
next_action: "4f BUILT 2026-11-19 (windows found by their shape; any client, section 4 \"Any client\"); next: the client's own digits, its minimap, 4a. Step 1 BUILT (any character, ADR-0020 Amendment Q) and moved to the Settings page 2026-11-19 (Amendment R: any the default everywhere, the lab too; known = the characters remembered there by its Remember button). Batt tests one step at a time; the next ones in section 4 wait for him."
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
| 5 | The map: the minimap's picture is the node's map | | ➡️ 2026-11-19: a picture that cannot tell WARNS when her cell lies on the node map's open ground; another map still refuses | the project |
| 6 | The start cell: on the map's open ground, reaching its search area | | unchanged: the walk plans from it | needed (see 4c) |
| 7 | The bag under WEIGHT_MAX (48 %) | | a setting (block), 10-90 %; ➡️ 2026-11-19: an UNREAD weight warns (a read or red heavy bag still refuses) | setting |
| 8 | Fly Wings on fly_key, at least PLAYER_MIN_WINGS (5) | | ➡️ 2026-11-19: a WARNING only, the Run starts (below) | the player's own |
| 9 | Heal items on heal_key, at least PLAYER_MIN_HEALS (5) | | ➡️ 2026-11-19: a WARNING only, the Run starts (below); which item counts is still 4a | the player's own |
| 10 | Butterfly Wings on home_key | | never refuses | the player's own |
| 11 | The Knife on knife_key, the dagger worn | | ➡️ 2026-11-19: a WARNING; a run whose Knife / dagger slots do not read right plays WITHOUT the Knife swap | the player's own |
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

**The hotbar is the player's own (Batt 2026-11-19 ~11:0x):** "do not lock the bot over this: it is
the user's own business"; "without Fly Wings the bot dies: the user learns and improves -- or a user
may use an item with a teleport skill"; "do not lock this". Built: the start check's hotbar lines
(wings, heals, home, knife, dagger) WARN and the Run starts (`flow_run.hotbar_warnings`; the Run log
marks them WARN); inside the live player the runner's own start refusals on them
(`player_stock_refused`, `player_slots_refused`) become warnings (`flow_play.hotbar_is_the_players`,
for the run only: the runner file is unchanged, its CLI keeps its rules); a run whose Knife or dagger
line fails plays without the Knife swap (`flow_play.knife_swap_off`: swapping from an unknown weapon
state could equip anything). In the run nothing new: an unread count never ends it (a teleport-skill
key has no count), a count read 0 still ends it (the end's own escape).

**The weight and the map on another client (Batt 2026-11-19 ~11:5x, asked after his Run refused on
both):** an UNREAD weight warns and the Run starts (its bag-full exit cannot work until it reads; a
weight read over the limit or drawn red still refuses); a minimap picture that cannot tell its map
warns and starts when her cell lies on the node map's open ground (another map still refuses). The
proper fix comes next: the client's own digits, then its minimap.

**A death ends the hunt (Batt 2026-11-19 ~11:0x):** "we have the death and the respawn at Geffen on
the maps; but here simply: if she died -- the dialog is up and her HP is 0 -- do not enter the
hunting loop again; very simple." The lab client's death dialog is recognised and its respawn plays
as before; on any client her HP reading 0 % for 3 s with no dialog recognised ends the run as
"dead" -- no respawn press, no hunting on (`flow_play.Hp0Watch`, in the hunt core's tick hook and
in the player's own reads). The HP is read from Basic Info's digits (the lab font: the client's own
digits are the next step).

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
  ➡️ **BUILT 2026-11-19** (see "Any client" below): Basic Info, the hotbar and the chat window
  found by their shape anywhere, moved to the lab's places in the bot's view.

### Any client (Batt 2026-11-19)

Batt, after four Runs were refused on another client (09:28-09:31: the weight, the hotbar counts and
the minimap did not read): **"Agree, do all of them"** -- 4f, the digits of the client itself, the
minimap of the client itself, 4a -- and **"no need to look [at my client]: just make the system
work with every client. When teaching we cannot ask to see every user's client, but we know what
RO's main UI looks like: start from that."** Never by the sniffer or the client's background
(memory: screen only).

| Step | What it gives | Status |
|---|---|---|
| 4f windows found by their shape | Basic Info, the hotbar, the chat window anywhere | BUILT 2026-11-19: offline proof on the lab's frames, 80 of 80 random layouts (1280x720 and 1920x1080) found and read exactly as the original (weight 876 / 2430, the 9 counts, the cell); 0 false windows on 3 login/desktop frames |
| the client's own digits | the hotbar counts and the weight read in another font or skin | next |
| the client's own minimap | which map she is on, on another client | after it |
| 4a any heal item | a beginner's Red Potions start a Run | after it |

**The first test on another client (Batt, 2026-11-19 10:33, a Thai-UI client on another server,
fullscreen 1920x1080; his screenshot, scaled 0.92):** all three windows NOT found. Compared with
the lab's own frames (the causes, to be proven on OUR Thai client before the fix ships):

| Window | His client vs the lab's | Why the 4f rule missed it |
|---|---|---|
| Basic Info | the same skin; a Thai title (ข้อมูลพื้นฐาน, tails below the line), a Job EXP bar (Job 48), the red "N" notice badge | rows 16 / 20 sit against the TITLE TEXT (a language's glyphs reach them); row 131 under the "N" badge. ➡️ The EXP bar is NOT a cause: the live test 11:39-11:41 (the lab client, Valcd8bd6, Base 70 / Job 1, both EXP bars drawn) found Basic Info with the FIRST rules too, 11 of 11 (the bars sit between the rows). The title and the badge cannot be shown on our client (an English title; the badge needs a notice): the new cues keep clear of both by design |
| the hotbar | no 1/2 row selector on the left, a dark top border, the counts under the icons, a "1" and a grip on the right | its four top-row lumas are the lab skin's. ➡️ 12:3x (Batt: "just look for the UI with 9 slots in a row; RO's hotbar is fixed"): the overlay of his screenshot on the lab's frame showed the SAME 29 px slot pitch, the bar ~46 px further right; the rule is now 9 square boxes on one row (each a left line and a top edge, uniform and standing out, any colour; pitch 28-30); the lab's frames: found exactly, 30 of 30 random moves at each size, none on login/desktop frames |
| the chat window | 4 lines, wider default tabs (Battle Message, General Message) | `chat_window.find` knows sizes 3/6/9/12/15 and the lab's tab widths (TOP_START). ➡️ Built `find_any` (any lines, any width, any tabs); live 11:40 on the lab client: F10 through every size, 9 / 12 / 15 / hidden / bar / 3 / 6, each read right, the standard back (`chat_window.py read`: standard true). A 4-line window or wider tabs cannot be made on our 2021 client (F10 sizes only): synthetic tests cover them |

~~The lab's Thai client (`C:\RO-rAthena-th`) still points at 192.168.1.13: a test there needs its
clientinfo moved to the lab host first.~~ ➡️ WRONG (corrected 2026-11-19 ~11:4x): that copy and its
shortcut were REMOVED from the Windows PC on 2026-10-06 (ADR-0019, "the Thai-data decision is
final"); the lab has no Thai client. Batt's approval to move its address was not used; nothing on
Windows changed. Our tests use the main client only.

The Run log now names each window and where it was found ("the hotbar found at (700, 600) (13 of 13
of its shape's cues): moved to the lab's place in the bot's view"; "Basic Info NOT found ...: the
lab's place is assumed"), numbers only: a learner's refused Run says which window was missing.
