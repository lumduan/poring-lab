---
doc_type: plan
hypothesis: null
status: BUILT (first cut, 2026-11-12; decided by Batt 2026-11-12 "after SQLite"); 9.35b (the boss-map warning, the Butterfly Wing home) BUILT 2026-11-12; 9.46 (the map's name from the minimap) BUILT 2026-11-13, its pre-registered held-out bar PASSED; 9.47 (the items on the keys, from their icons) BUILT 2026-11-13, its pre-registered held-out bar PASSED; NOT live-verified as a run (Batt 11-12: no lab live test of player mode)
role: null
verdict_date: null
verdict_ticket: null
supersedes: null
related: [../adr/0023-learner-mode.md, ../adr/0025-run-records-sqlite.md, ../setup/new-lab-host.md, rogue-xmas02.md]
next_action: "Batt's later steps: Kafra warps, NPC shops, selling. (Batt 2026-11-12, rogue-xmas02.md 4DF: no lab live test of player mode.) Since 9.46 the map's name is read from the minimap's picture: build its references on each host (OMP_NUM_THREADS=2 python3 scripts/minimap_id.py build --decode-mixcrypt) or a player start refuses. Since 9.47 the item on each role's key is read from its icon: build those references too (OMP_NUM_THREADS=2 python3 scripts/slot_items.py build --decode-mixcrypt) or a player start refuses."
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

## Built: the first cut (2026-11-12 12:41 ICT from `date`; dungeon@9.35, `--player-mode`)

`scripts/dungeon_hunt.py run --player-mode` (OFF by default; `fixes.player_mode` =
`[5, 5, 1, "9.35"]` in `run_start` and the manifest only when ON, so a default run's record is
unchanged). Tests: `services/backend/tests/test_player_mode.py`.

**1. No line is ever typed, by construction.**
- Every line the runner types goes through ONE guard, `typed_line`. Under `--player-mode`
  `line_refused` refuses every line before any key: a line starting with "@" is a GM command, and
  any other line would be public chat. The refusal is a Stop, so a path the flag missed stops the
  run instead of leaking a line.
- A source scan fails the tests on any other typing call in the file (crusader's `gm_line`,
  ro_agent's `chat_line` / `gm` / `open_chat` / `say` / `type_line` / `console_*`, the agent's
  `type_text` / `type_secret`). Every `typed_line` call must name its mode.
- A second scan checks that every place `run` could type (`typed_line`, `setup_line`, the chat
  close step) is in a branch the flag never takes, or runs a plan `player_plan` just emptied.
- Mutating the code proved the scans: a raw GM call, the end warp or the death's `@alive` made
  reachable, the plan or the chat check removed, the DB read made unconditional each fail a test.

**2. The "@" call sites found, and what each does under the flag:**

| Where | Lines | Under `--player-mode` |
|---|---|---|
| setup, the stand | the level hold (`@baselevelup -N`), `@heal`, `@item 504` / `@item 601` top-ups | none: `player_plan` empties the list |
| setup, the clear stand | `@warp prt_fild08 268 107` + dropping the Etc tab | never: the bag is not dropped; `etc_hold_refused` stops the run instead |
| setup, the Rogue's hotbar top-up | `@item` from the hotbar count | never: the player's own stock read replaces it |
| setup, the map | `@warp MAP X Y`, `--clear-map`'s `@killmonster2`, `--stage-mob`'s `@monster`, `--stage-at`'s second `@warp` | none: `player_plan` empties the list; the four flags are refused anyway |
| the end, a death | the dialog's button, then `@alive` + `@heal` | none: the death dialog stays open for the person |
| the end, every run | `@warp` to the clear stand | none |
| `clear-bag` (a separate subcommand) | `@warp` + `@item` | the lab's alone: it has no `--player-mode` and passes `player_mode=False` |

- The hunt loop itself types nothing (the scan proves it).
- The runner has no immunity flag: immunity (`@monsterignore`) is toggled OUTSIDE it, by the lab's
  chain through crusader.py, so there was nothing to refuse there.

**3. Nothing is read from the lab's DB.** The setup's three queries (char_id, the inventory's
White Potions and Fly Wings, the base level) run only without the flag. Under it the stock comes
from the hotbar's drawn counts (`hotbar_count`, the same reader the Rogue's top-up uses) and the
weight from Basic Info (`gm_state`).

**4. The start refuses, with a plain message, when:**
- the chat input is open (the setup's chat-close step presses Enter, which would send text left
  there): checked at the start and again right before that step;
- fewer than `PLAYER_MIN_WINGS` = **5 Fly Wings** are on the hotbar (3 for an unread position,
  `POS_FLY_MAX`, one escape, and one kept for the end), or fewer than `PLAYER_MIN_HEALS` = **5
  heal items** (White Potions; with `--heal-candy` the Candy Canes, Candies and potions together),
  or a count does not read;
- the weight does not read, reads red, or is at or over 48 % (`WEIGHT_MAX`; the bag is never
  dropped). At 40 % (`CLEAR_AT`) a character whose bag the lab would clear stops too;
- her cell does not read on the minimap within 5 s (`PLAYER_POS_S`), is off the map, off the
  run's route grid, or in a part from which no walk reaches the search area.

The run starts where she stands: the heading walk walks into the search area, the patrol joins its
loop at the nearest waypoint ahead, and `--explore` takes its regions from HER walk component.
The person's potions are never drunk down at the start (the lab drinks the ones over the stock).

**5. Refused flags:** `--clear-map` (`@killmonster2`), `--stage-mob` (`@monster`), `--stage-at`
(`@warp` + `@monster`), `--start-cell` (the setup's `@warp` goes there), and `--engage melee_ring`
(it strikes every monster in reach; its own rule is the lab server's). Refused before any input.

**6. The loop and the end.**
- The escapes are unchanged: the Fly Wing key and the potions, the HP escape, the unread-position
  and stuck Fly Wings, and the boss guard with `--engage-screen`.
- The run ENDS when the Fly Wings read 1 (`PLAYER_WINGS_KEEP`; reason `stock_keep`), so the end
  always has one. A count of 0 ends it as before (`stock_out`).
- The end types nothing and warps nowhere. The run's own end escape (dungeon@8.5's rule,
  unchanged) presses the Fly Wing when a hit came within 3.5 s, the HP fell, or the HP is under
  50 %.
- A run that ends during a rest stays SEATED (natural regen goes on); it stands only when that
  escape is due, because a Fly Wing cannot be used sitting. ➡️ 9.35b: it stands for the Butterfly
  Wing home too, when one is pressed (below).
- No sit is added after the end's Fly Wing (a key right after a teleport's load is an unverified
  step). A `player_end` event records what she was left as.

## Built: the boss-map warning (dungeon@9.35b; written 2026-11-12 19:40 ICT from `date`)

Batt (rogue-xmas02.md 4DF, translated): "player mode on public servers: a warning only, no
refusal".

- At the start, before any input, a `--player-mode` run reads the map's BOSS spawns from the KB
  (`player_boss_spawns`: `data/kb/spawns.json` + `mobs.json`, the names `--boss-walk` uses,
  `boss_spawn_names`).
- When there is one and the boss guard is off (neither `--engage-screen`, whose Battle Log names
  guard, nor `--garm-fly`, whose detector box guards), it prints ONE plain `WARNING:` line naming
  them. It records `{"kind": "player_boss_warning", "bosses": [...], "guard": false}` right after
  `run_start`.
- A KB that does not read gives the same warning with the bosses unknown (`"bosses": null`).
- **It never refuses:** the run goes on. With the guard on, or with no boss spawn, nothing is
  printed.
- Tests: `test_player_mode.py` (the line, the KB read on made-up names, the block's place before
  the session, no raise in it).

## Built: the Butterfly Wing home at the end (dungeon@9.35b; written 2026-11-12 19:45 ICT from `date`)

Batt (rogue-xmas02.md 4DF): "add a Butterfly Wing home at the end".

- **The key.** Each character in `CHARS_CONF` names its Butterfly Wing key, `home_key`: `HOME_KEY`
  = **F8**, the first row-1 key no character uses (F1 potion, F2 Fly Wing, F3 Steal / Auto Guard,
  F4 the Knife opener, F5 the dagger / Heal, F6 + F7 `--heal-candy`'s).
  - `--player-home-key KEY` overrides it.
  - It joins the run's keys (`keys_["home"]`) under `--player-mode` only, so the lab's own key
    checks (clear-bag's Eqp guard, `--steal-opener`'s) are unchanged.
  - Refused before any input (`player_home_refused`): `--player-home-key` without
    `--player-mode`, a key that is not row 1 (F1-F9), or a key the run already uses (with the
    candies' keys and the opener).
  - The start record carries `player_home_key`.
- **The end** (`player_home_end`), after the run's own end escape (the 8.5 Fly Wing):
  - Its hotbar count is read up to 5 times, 1 s apart: an end Fly Wing's dark frames.
  - **A count >= 1: ONE press**, through `press("home", "end")`: the runner's key path, the mux.
  - A seated end stands first: no wing works sitting.
  - Then it waits for the map change as the runner can see one, the load gap of
    gef10-house-rest: Basic Info's HP gone within 3 s (`PLAYER_HOME_LOAD_S`), then back within
    20 s (`PLAYER_HOME_WAIT_S`). It never presses again.
  - **No press, recorded:** no key, an unread count, a count of 0, a death (the dialog is the
    person's), or a hard bar (an unknown state gets no key, as the 8.5 escape).
  - The record: `{"kind": "player_home", "pressed", "why", "key", "count", "stood", "load_s",
    "back_s", "waited_s"}` (an exception inside adds `error`; the end goes on). `player_end`
    gains `home`; its `seated` is false once she stood for the wing.
- **The start checks nothing for it:** the Butterfly Wing is optional. Without one the end is
  9.35's.
- **No line is typed:** it is a key. The 9.35 scans stay green, and a new test checks that the one
  `press("home", ...)` sits in the player-only branch.
- Tests: `test_player_mode.py` (the key per character, the refusals, the end with fakes: one press
  at a count >= 1, none at 0 / unread / no key / death / hard bar, a seated end stands first, the
  capped wait).

## The /flows Run button (2026-11-13, Batt: "press run on flows and the bot plays")

- `POST /flows/run` (routes_flowrun.py, the Settings page's write_gate) writes one request into
  `settings/flowrun/`. The host helper `scripts/flow_run.py` consumes it and starts the worker, the
  detect server and `dungeon_hunt.py run --player-mode` with the Knife base (4DQ), `--minutes 120`
  and `--stop-file`. One run at a time; it refuses while the night chain or another runner plays.
- Stop touches the runner's stop file (dungeon@9.40): the run ends at its next tick through its
  NORMAL end, with the packets, the stats in lab.sqlite and a Butterfly Wing home. SIGINT is only
  the backstop after 90 s.
- Smoke tests 2026-11-13 07:36 and 07:42 on the lab server:
  - started, hunted with the Knife swaps, ended 8 s after Stop with rc 0;
  - the run is in the SQLite records.
- The helper is NOT a boot service yet: the auto-mode classifier refused enabling a persistent
  unit. Batt enables it, or it is started by hand after a reboot.

## Built: the map's two exits and the person's Run settings (dungeon@9.41; written 2026-11-13 11:3x ICT)

**Batt (2026-11-13, Thai, translated):** "Write the flow of xmas_dun02 that the bot really plays, in
detail: if the weight is over 50 %, use a Butterfly Wing to go back to town, that is the map's exit;
if she dies, press to respawn, that is an exit too. For testing we can start from this map: put a Run
button next to Simulate, to run it for real on this map." Then: "the Butterfly Wing on F9, the Fly
Wing on F8; don't hard-code them: a user changes them in the blocks too."

- **The flow is the runner's own description** (`scripts/runner_flow_export.py`, made from
  dungeon_hunt.py's code): the IR's `hunt` block describes the older hunt rules, not the Knife base,
  so an IR copy would have shown something other than what Run starts. Its new parts:
  - the UI watch: over `--weight-home` the run ends after its fight (never mid-fight), and the end's
    Butterfly Wing takes her home (`weight_home_due`, reason `weight_home: ...`);
  - a death with `--respawn`: the death dialog's FIRST button "move to saved location" (Korean
    저장된 지역으로 이동), pressed ONCE and only while the dialog reads (`gm_vitals.DEAD_STATE`), then
    the load screen and the save point's map (`respawn_end`; anything else: recorded, the person's).
    Its place `MOVE_TO_SAVE = (645, 481)` (game px) was measured on TWO real deaths of the F1 trial
    recording (`20261112T084927-rdp-flee-xmas02-sk` frames 83 and 108): face rows 473-490, columns
    ~535-755; the second button is the setup's known (645, 503). One more direct click in the
    census (dungeon_hunt.py 2 -> 3).
  - `--fly-key` (new) and `--player-home-key` (9.35b): the keys are the person's; the stock read,
    the presses and the key-conflict checks follow them.
- **The Run settings:** a POST /flows/run start may carry `settings` = {fly_key, home_key,
  weight_home}: F1-F9 keys and a weight in 0.30-0.80; the backend (`RunSettings`, extra fields
  refused) and the helper (`flow_run.settings_of`: two different keys, none the run uses already:
  F1 potion, F3 steal, F4 the Knife, F5 the dagger; weights 0.30, 0.35 ... 0.80) check them; they
  become the three flags, nothing else in a request does. Defaults (Batt): Fly Wing F8, Butterfly
  Wing F9, home over 50 %.
- ➡️ **2026-11-14 ~15:2x (Batt: "no runner [page] ... make them ALL blocks"; live-blocks.md section 12):** the runner page is gone and every setting is a BLOCK of the project (the map node's over Global's over the default); the settings file and GET / PUT /flows/config are gone (the file was empty). The lines here are history.
- **/flows?runner=xmas_dun02:** Run (amber, two presses: the second within 4 s confirms) and Stop
  beside Simulate; a "your run settings" strip (three selects, remembered in this browser; the
  blocks show the chosen keys and percent at once); the binding strip: bound to map xmas_dun02,
  starts where you place her, exits -> the save point (a Butterfly Wing when the bag is over the
  limit; the death dialog's move to saved location after a death).
- **What the person sets up on the hotbar:** the Fly Wings on the Fly Wing key, the Butterfly Wings
  on the Butterfly Wing key (11-13 11:12 her F8 and F9 were EMPTY: the 10:02 test's end read
  "no Butterfly Wing on the hotbar (count 0)").
- **Live checks (2026-11-13, all PASSED; archived on the NAS, scratch-archive/2026-11-13):**
  - 11:34 the weight exit: 0.3107 > 0.30 -> run_end `weight_home` after 11.4 s (F9 empty then:
    no wing, recorded).
  - 11:45 found: the Butterfly Wing's icon tail in F9's count box read `[None, '5']` -> the count
    read None and the wing never pressed. FIXED in hotbar_count (a digit's ink spans the box's
    height; all ten templates do).
  - 11:46-11:47 the full exit (fly F8, home F9, 30 %): weight 0.3111 -> run_end -> F9 "5 on the
    hotbar" pressed once -> load 0.25 s, back 4.14 s, `home: true`.
  - 11:57 the respawn, first try: the menu's press opened a CONFIRMATION this client asks ("Do
    you really want to go back to your savepoint?", OK / Cancel); the function stopped safely
    (no load, recorded). Its signature `respawn_confirm` was cut from that live frame (box game
    505,300,280,119) and its OK measured at (714,405): `--respawn-confirm-at X,Y | none`, a Run
    setting, a step of the respawn function block.
  - 12:01 the respawn with the confirmation (Batt: "@die is easier"; @die + @save added to group
    20): menu pressed -> confirmation read after 1.06 s, OK once -> load 0.25 s, back 4.23 s ->
    Geffen (119, 40), alive (28 HP, healed).
- **The save point (Batt 2026-11-13: "save her at Geffen first"):** `@save` on the Geffen Kafra's
  own save cell (npc/kafras/kafras.txt: savepoint "geffen",119,40) at 11:5x; the reply "Your save
  point has been changed." A Butterfly Wing and a respawn now land in Geffen.
- **Everything is the person's (Batt: "make it editable in the code blocks, don't hard-code"):**
  the Fly Wing key, the Butterfly Wing key, the weight limit, the respawn button's point and the
  confirmation's OK (or none) are Run settings on /flows?runner=xmas_dun02, shown in the blocks;
  the respawn is its own function block, `def respawn(at)`.
- ➡️ **dungeon@9.42 (2026-11-13 ~13:4x; Batt: "remember: the user must be able to set everything
  again or edit it; nothing is fixed, we only put the defaults"):** the heal item's key
  (`--heal-key`, default F1), the Knife's key (`--steal-opener`, F4: no longer a fixed flag of the
  flow), the dagger's key (`--dagger-key`, F5: `bare_steal.configure` moves the key AND the slot
  whose picture says the dagger is worn) and the Knife swap's two numbers (`--knife-max-s`, 8 s,
  0.2-20: Batt's "F4, wait 200 ms, F5" is 0.2; `--knife-hp-min`, 50 %, 20-90 %) are Run settings
  too. The runner checks that no two of its row-1 keys are alike (`keys_clash`, the home key and
  the Knife's included); the Steal skill's F3 is dropped from the key map when `--steal` is off,
  so NO key is the run's own any more (`reserved_keys` empty). The settings list above
  (`fly_key, home_key, weight_home`; "F1 potion, F3 steal, F4 the Knife, F5 the dagger" taken) is
  ➡️ SUPERSEDED by this: ten settings, each from a checked range, none taken.
- ➡️ **dungeon@9.43, the heal and escape numbers (2026-11-13 ~14:2x; Batt: "make them a GLOBAL
  config for every map's flow; a map's flow that sets them again overrides it, with that map's
  config first"):** `--potion-below` (40 %), `--fly-below` (20 %), `--fly-rate` (150 HP/s) and
  `--fly-rate-below` (50 %) replace the strategy's own numbers (`with_survival`; ranges in
  `SURVIVAL_RANGES`). They live in ONE file of the human-only settings store,
  `settings/flowrun/survival.json` = {"v": 1, "global": {...}, "maps": {"<map>": {...}}}, written
  only by the backend (`PUT /flows/survival`, the Settings write gate; audited in
  `survival.jsonl`; a broken file is never written over). At each start the Run helper takes, per
  number, the flow's default < every map's < that map's own (`flow_run.survival_of`) and passes
  them as flags; a request never carries them, and a broken file refuses the run before any input.
  /flows shows a "heal and escape" strip: every map / <map> only, each change saved at once; the
  blocks show the numbers the next Run uses.
- ➡️ **dungeon@9.44, EVERY setting on the bot server (2026-11-13 ~15:0x; Batt: "move them too"
  -- the hotbar keys, the Knife swap, the respawn points -- and "all of them" -- loot, walking, the
  start minimums, the rest):** ONE registry, `scripts/flow_config.py` (70 settings in 12 groups:
  hotbar keys, the Knife swap, heal and escape, leaving the map, the respawn, the start, the fight,
  choosing and striking, loot, walking and exploring, safety and the end, the loop), each with its
  kind, range, words and how the runner takes it: its own flag (the 14 Run settings) or
  `--tune NAME=VALUE` (56 runner constants; `tune_values` checks each against flow_config, then
  `tune_apply` sets it before anything reads one). 21 constants used to be copied into default
  arguments at import (a `--tune` would have been ignored SILENTLY): they are read at call time
  now, and `test_flow_config` fails if any setting is ever bound at import again, or if /flows
  shows a runner number that is neither a setting nor excluded with its reason.
  ➡️ **SUPERSEDED 2026-11-14 (live-blocks.md section 12): the values are the project's SETTING
  BLOCKS now; the file and its PUT are gone.** As they were:
  ➡️ The values: `settings/flowrun/config.json` (v2, the same shape as 8e3ca2df's survival.json,
  which it reads while config.json does not exist), `PUT /flows/config` per GROUP and level
  (every map / one map's own; audited in config.jsonl; refused when a value is off its range or
  two settings would share a hotbar key for a listed flow). A Run request names a flow and NOTHING
  else: the browser's run settings (localStorage) are gone; the helper takes, per setting, the
  default < every map's < the map's own, refuses a broken file or a key clash before any input,
  and passes the flags. ➡️ This SUPERSEDES the per-browser run settings (9.41-9.42) and the
  survival-only file (9.43) above: they are history.
- ➡️ **dungeon@9.45 (registry), the TECHNIQUES' SWITCHES (2026-11-13 ~15:2x; Batt: "do all of
  them"):** 50 switches and choices join flow_config (124 settings in all): every technique of the
  night chain's base (the Knife swap and its parts, the value target, the loot items and its
  model, the box strike chain, still / lead / far / near, the search and exploring, the walk
  pick, the kill gap, the EXP line, the Miss cue, the NPC guard, the Garm Baby escape, the HUD, the
  detector's CPU / GPU, the time box ...) plus the FLAGs tested off-by-default (queue, defend box,
  quick drop, loot recheck / aim, explore cover, boss walk, unread step ...), each defaulting to
  what the flow runs today (the default command equals the old one, six flags now stated
  explicitly at the runner's own defaults). A setting whose NEEDS do not hold (e.g. box_now
  without box_strike, the Knife's keys and numbers with the Knife swap off, the respawn points
  with the respawn off) is NOT IN USE: not passed, greyed on /flows with the reason, and its
  key clashes with nothing. FIXED stays only what `flow_config.NOT_SETTINGS` names (the
  character, the map, player mode, the strategy, the seed, the GM trial lines ...), and
  test_flow_config fails if any runner flag is neither a setting nor listed there.
  ➡️ Found on the way: `BOX_EVERY_S`, `WALK_AHEAD` and `WALK_EVERY_S` are the runner's flag
  DEFAULTS (bound when the parser is built), so 9.44's --tune of them would have been ignored:
  they are settings with their own flags now (--box-every, --walk-ahead, --walk-every), and the
  guard test also refuses a tunable used as an argparse default.
  ➡️ The Run helper says "playing" only after the runner's run_start event (matpilot's finding:
  it said "playing" while the runner was still refusing at its start checks).

## Built: the live ticks and the flow's keys (dungeon@9.45; written 2026-11-13 18:29 ICT from `date`)

**Batt (2026-11-13): "do it"** -- before Run, the page ticks each start-checklist line from the
GAME SCREEN. And every hotbar key comes from a FUNCTION of the flow (e.g. `def fly_wing():
press_key("F8")`): /flows compiles the functions into five keys and sends them with Run.

- **`dungeon_hunt.py check`** (`LIVE_CHECK_VERSION = "9.45"`; the runner's `VERSION` stays
  dungeon@8.7) takes run's OWN flags (its parser is `check`'s parent: no flag of its own), runs
  run()'s whole preamble (every refusal before any input, the same keys, the same route grid) and
  returns before the session: `start_check(screen, ctx)` gets a screen and no agent, and the check's
  process replaces ro_agent's `Agent` and `session` with ones that refuse at construction
  (`no_input_guard`). So it sends NO input: no key, click, move, chat line, window or tab. It
  prints one `CHECK {json}` line and makes no session folder. `--player-mode` only.
- **Its lines** (ids = `CHECK_IDS` = the page's `CHECKLIST_IDS`, test-pinned), each decided by the
  same function the runner's start uses (the start now calls the shared pieces too:
  `player_chat_refused`, `read_start_cell`, `explore_from`, `etc_hold_due`, `stock_slots`,
  `hotbar_counts`, `player_heal_items`, and `player_stock_refused` = `player_wings_refused` or
  `player_heals_refused`):
  - `identity`: `crusader.check(..., db=False)` (the name plate and the job, no DB);
  - `cell`: the minimap readout (`read_start_cell`, PosConfirm) + `player_start_refused` (+ the
    explore regions from her cell);
  - `chat`: the `chat_open` signature;
  - `weight`: the Etc-hold rule then `player_weight_refused` (under WEIGHT_MAX, read, not red);
  - `wings`, `heals`: the hotbar counts on fly_key / heal_key (heal candies with --heal-candy);
  - `home`: the Butterfly Wings' count on home_key with `player_home_count_why`. The start
    never refuses on it (it is a warning line, `refuses: false`); the way home reads it again;
  - `knife`, `dagger` (Knife swap on): READ FROM THE HOTBAR, no window opened, by the start's own
    `opener_ref_cut` (one item, no stack, on knife_key: the Knife in the bag; its icon is not
    matched) and `bare_ref_cut` (dagger_key's slot empty: worn; an empty slot cannot tell
    "worn" from "nothing there", the first swap tells).
  Each line: `{id, ok: true | false | null, words, value, refuses}`; a read that raises (a frozen
  stream, a missing template) is that line's `null`.
- **🔴 The map's NAME is not read from the screen (a gap).** No pixel read tells which map she is
  on: the minimap readout gives a cell, and `hunt_flow.map_same` only compares the minimap picture
  with the run's OWN start crop. The live read below proves it matters: in GEFFEN at (119, 40) the
  cell falls on xmas_dun02's open ground, so the cell line passes, and the runner's own start
  would accept that cell too. The line's words say so ("IF she is on xmas_dun02: the map's name is
  not read from the screen"), and the checklist line asks the person to check the map. A map
  recogniser was NOT built (out of this task's scope).
  ➡️ **SUPERSEDED the same evening by dungeon@9.46** ("The map's name from the minimap", below):
  the map is read from the minimap's picture; the line ticks only on the run's map, and a player
  start refuses another map (and one it cannot tell) before any input.
- **The Run helper** (`flow_run.py`): action `check` -- refused while a run starts, runs or stops,
  or another runner / the night chain plays (the start's busy rule); one at a time; it builds the
  start's argv with "check" for "run" (`check_command`), runs it in its own process group, time-
  boxed at `CHECK_TIMEOUT_S` (20 s), and puts the result into status.json's `check` = {state
  (checking | done | refused | failed | timeout | cancelled), at (ISO), flow, items, ok, refuses,
  detail, keys, keys_src, used (the values it applied: the page greys a result its settings
  outdated)}. A Run pressed meanwhile ends the check first. Its log: `/dev/shm/poring-lab-tmp/
  flowcheck/check.log` (overwritten by the next check).
- **The flow's keys:** POST /flows/run `{action: "start" | "check", flow, keys?: {heal_key,
  fly_key, home_key, knife_key, dagger_key}}`: when given, ALL FIVE, each F1-F9, nothing else
  (`flow_config.keys_problem`; the backend refuses with 400 `keys_refused` and the words, the
  helper refuses the same). They go over the config file's for THAT run or check only (the file
  is not written), then the clash rule runs as before. The status says `keys_src` ("the flow's
  functions" / "the settings"); the run's record (runs.jsonl `start`, `config_src` = "flow" for
  the five) and the backend's requests.jsonl name them. A check needs no ASSIST (it reads only).
- **The page** (LiveRun): each line ✓ / ✗ / ? with the value read, a red ✗ with its words, a
  "Check the game" button (also once by itself when the panel opens and the helper can check), the
  time of the last check, greyed lines once the settings it used changed. Run stays pressable with
  a ✗ (Batt: warnings, not locks); its title then says the runner will refuse. `keys` (from the
  flow's functions) go with every start and check, and the checklist states them.
- **Live read (read only, the lab's screen, 2026-11-13 18:23:20-18:23:24 ICT, 4.0 s):** the Rogue
  in Geffen (119, 40), HP 100 %. Every line ✓: identity (her name plate, rogue), cell (119, 40)
  "IF she is on xmas_dun02 ...", chat closed, weight 825 / 2430 (34 %), 10 Fly Wings on F8, 10
  heal items on F1, 3 Butterfly Wings on F9, one item on F4 (the Knife), F5 empty (the dagger
  worn). An earlier attempt (18:22:51) stopped in the preamble before any read (the worktree lacked
  the generated map cache).

## The map's name from the minimap (dungeon@9.46; Batt 2026-11-13 "do it")

### The cue (studied 2026-11-13 19:39-20:04 ICT from `date`)

- **What the screen offers.** The client writes no map name in play: the readout under the
  minimap is the cell only, and `/where` would type a line (rule 1: no input). But the minimap
  draws THE MAP'S OWN PICTURE: the archive's per-map minimap bitmap (`<texture folder>/map/
  <map>.bmp`, the name through `data/resnametable.txt` like every resource; the training grounds'
  `new_N-M` are aliases of `new_zone0M` there). At the lab's zoom it is the WHOLE map, scaled into
  a 127 px square at the minimap window's origin (1136, 18) + (1, -1). Its magenta key colour
  (255, 0, 255) is transparent (the scene shows), every other pixel is drawn translucent over the
  scene (xmas_dun02's orange floor bleeds through), and the NPC marks and her arrow are on top.
- **Why this cue.** It is drawn on every map that has a minimap, whatever the floor, the light or
  the monsters; it does not depend on her cell; and a reference exists for every map in the
  client's archive without a frame recorded there (references cut from recorded frames would
  cover only the maps the lab has played). The other candidates: the scene's floor palette is
  local to her stand and changes with effects and light; the GAT's walk grid is not what the
  bitmap paints.
- **How** (`scripts/minimap_id.py`, numpy only): grey; the normalised cross-correlation of the
  square with every reference over the reference's own DRAWN pixels (its key pixels show the
  scene); a correlation is blind to the translucency (a gain) and to a flat scene (an offset).
  - The best picture is NAMED when it scores >= NAME_MIN (0.40) and beats the next DIFFERENT
    picture by >= MARGIN_MIN (0.15). Two pictures >= 0.95 alike are one (a copy group: prontera
    and pprontera draw the same picture; every server map that draws it is in the read).
  - The run's map is TICKED only when it draws the named picture AND the score is >= MATCH_MIN
    (0.60). Another map named: a cross ("she is on geffen, not xmas_dun02"). Else "cannot tell".
- **The references** (`minimap_id.py build`; client-derived, `data/minimap_refs/refs.npz`,
  gitignored, never committed): every server map of the lab's pre-re map cache (1,296) -> its
  bitmap through resnametable -> rendered as the client draws it (the key out, box-scaled).
  2026-11-13 20:00: 668 pictures read, 599 maps with a picture drawn on >= 10 % of the square,
  422 distinct pictures, 1 min 14 s (with every BLAS thread; 28 s and the same pictures with
  `OMP_NUM_THREADS=2`, the way to run it on a host that plays). 629 of the archive's 731 minimap bitmaps (xmas_dun02's,
  orcsdun01's and gef_fild10's among them) are MIXCRYPT: they need `--decode-mixcrypt`, the lab's
  host-local study decoder (grf_read, never in the repo). Without it those maps have no reference
  and read "cannot tell".
- **The geometry** was fitted on 4 frames each of 6 maps (xmas_dun02, gef_fild10, pay_fild07,
  prt_fild08, orcsdun01, alberta): every size 122-132 x 122-132 at every offset +-4 px; the best
  mean correlation is 127 x 127 at (1137, 17) (0.832; the next, 129 x 127 at (1136, 17), 0.826).

### The development set (seen while designing; `docs/records/minimap-id-dev-20261113.json`)

12 NAS sessions + 7 pictures of today's 5 runs + the live frame: 88 frames. The true map is the
session's packets' last map change (offline ground truth only; a frame 2 s before to 5 s after a
change is not labelled: 3 here). Of the 85 labelled, 84 named right, 0 named wrong, 1 "cannot
tell" (new_1-1: the lab client's picture of the training grounds is closer to the Thai archive's
`new_event` (0.86) than to its `new_zone01` (0.74)). With `--expect xmas_dun02`: 34 / 34
xmas_dun02 frames ticked; the 51 others 50 crossed, 1 "?". Scores (the true picture; the best
OTHER picture's at most): xmas_dun02 0.80-0.89 (0.35), gef_fild10 0.87-0.89 (0.42), pay_fild07
0.82-0.83 (0.49), prt_fild08 0.87-0.89 (0.52), orcsdun01 0.82 (0.26), alberta 0.79-0.80 (0.45),
morocc 0.57-0.62 (0.25), prontera 0.55-0.58 (0.29), geffen 0.47 (0.15: her stand, in the live
frame and the 15:18 flowrun's end picture alike). Towns score lower: their NPC marks cover the
picture. MATCH_MIN 0.60 sits over every wrong-picture score seen (<= 0.52) and under every
dungeon / field score (>= 0.79); a town can be NAMED (a cross) but never TICKED.

### PRE-REGISTERED (2026-11-13, commit 9c1a1ba1 at 20:04:47 ICT, before the held-out set is read)

- **The held-out set:** `docs/records/minimap-id-heldout-20261113.json` (78 items, none in the
  development set): 24 xmas_dun02 recordings (11-05 .. 11-13; their prt_fild08 stand at the
  start / end too), 10 gef_fild10, 6 pay_fild07, 10 prt_fild08 / prontera / prt_church
  recordings (2 frames from each of 3 shards), 22 demo sessions' stand frames (prontera,
  prt_church, alberta, alberta_in, morocc, new_1-2) and 24 orcsdun01 strike frames of 6 hunts.
  Scored ONCE by `minimap_id.py eval` (`scripts/minimap_id_eval.py`) with the constants above
  frozen, `--expect xmas_dun02`, the references of 20:00.
- **The bar** (labelled frames only):
  - **B1 (the danger):** 0 frames of another map, or of no minimap, TICKED as xmas_dun02.
  - **B2:** of the xmas_dun02 frames, >= 97 % ticked and 0 crossed.
  - **B3:** named WRONG (a map read that is neither the true map nor its copy) <= 1 % of all
    frames, and never as xmas_dun02.
  - **B4:** of the frames of maps with a minimap (every true map but prt_church and alberta_in,
    indoor maps the client draws no minimap on), >= 90 % named right.
  - **B5:** prt_church / alberta_in frames: none named.
  - Plus the live case (read only): the live Geffen frames read "she is on geffen, not
    xmas_dun02".
- **The runner's "cannot tell" rule, decided by B2:** when B2 passes with at most 3 % of the
  xmas_dun02 frames "cannot tell" (frames taken IN PLAY: fights, effects, windows; a standing
  start is the easy case, and the start reads frames for up to PLAYER_MAP_S), the runner REFUSES
  a start that cannot tell. Otherwise it warns in the run's log and goes on.

### The result: PASS (scored once, 2026-11-13 20:04:55-20:12:12 ICT from `date`, 436 s)

`minimap_id.py eval docs/records/minimap-id-heldout-20261113.json --expect xmas_dun02`, the 20:00
references, the constants above unchanged: 1,024 frames (the demo sessions held more stand frames
than the 2-per-shard recordings), 999 labelled (25 in a load window). Map read (columns, "?" =
cannot tell) by the true map (rows):

    true \ read  alberta gef_fild10 morocc orcsdun01 pay_fild07 prontera prt_fild08 xmas_dun02    ?
    alberta           26          .      .         .          .        .          .          .    .
    alberta_in         .          .      .         .          .        .          .          .   71
    gef_fild10         .         46      .         .          .        .          .          .    .
    morocc             .          .      9         .          .        .          .          .    .
    new_1-2            .          .      .         .          .        .          .          .   13
    orcsdun01          .          .      .        24          .        .          .          .    .
    pay_fild07         .          .      .         .         32        .          .          .    .
    prontera           .          .      .         .          .      289          .          .    .
    prt_church         .          .      .         .          .        .          .          .  334
    prt_fild08         .          .      .         .          .        .         35          .    .
    xmas_dun02         .          .      .         .          .        .          .        120    .

| Bar | Registered | Result | |
|---|---|---|---|
| B1 | 0 other frames ticked as xmas_dun02 | 0 of 879 | PASS |
| B2 | >= 97 % of xmas_dun02 ticked, 0 crossed | 120 / 120 (100 %), 0 crossed, 0 "?" | PASS |
| B3 | named wrong <= 1 %, never xmas_dun02 | 0 of 999 | PASS |
| B4 | >= 90 % named right where a minimap is drawn | 581 / 594 (97.8 %) | PASS |
| B5 | prt_church / alberta_in never named | 0 of 405 | PASS |

- **The 13 not named in B4** are new_1-2 (the training grounds): the client draws its minimap
  BLACK there (her arrow only; the Thai archive's `new_zone02` bitmap is blank, so it is no
  reference). "Cannot tell" is the right answer.
- **The scores:** xmas_dun02 0.756-0.889 (5th percentile 0.809, median 0.855; the next picture at
  most 0.374); gef_fild10 0.85-0.89, prt_fild08 0.86-0.89, orcsdun01 0.79-0.84, alberta 0.78-0.82,
  pay_fild07 0.77-0.83, morocc 0.59-0.62, prontera 0.52-0.60. The highest WRONG-picture score on
  any labelled frame was 0.515 (prt_fild08's runner-up); on the no-minimap frames the best picture
  reached 0.513 (prt_church's scene against `pvp_n_1-2`), held off by the margin rule. MATCH_MIN
  (0.60) is 0.085 over both. No other map's frame had xmas_dun02 as its best or second picture.
- **The 25 unlabelled frames** (inside a load window): 22 named the map before or after, 3 "?".
- **The rows** (one per frame: the session, the true map, the read, scores, words), the dev
  rows, the live check's output and the live frame: the NAS
  `scratch-archive/2026-11-13/minimap-id/` (SHA256SUMS, README.txt).
- **The runner's rule, as registered:** B2 passed with 0 % "cannot tell", so `PLAYER_MAP_UNREAD =
  "refuse"`: a player start that cannot tell its map within `PLAYER_MAP_S` (3.0 s of frames)
  refuses, as one that reads another map does.

### The live case (read only, the lab's screen; pixels only, no input)

She stands in Geffen at (119, 40) (19:02's position; the lab database said last_map geffen 119 40).
- 19:39:17 ICT: one game-region frame grabbed (study): the minimap shows Geffen's picture.
- **20:13:13.98-20:13:18.37 ICT (4.4 s), `dungeon_hunt.py check` with the flow's own argv**
  (`flow_run.check_command`, the worktree, the 20:00 references): the map line is a red ✗,
  `ok: false, refuses: true`, value "(119, 40)": "she is on geffen, not xmas_dun02 (read from the
  minimap: 0.47; xmas_dun02 is not that picture): walk or warp her to xmas_dun02 first". Every
  other line ✓ as at 18:23 (Thief8fce / rogue, chat closed, 825 / 2430 = 34 %, 10 Fly Wings on
  F8, 10 heal items on F1, 3 Butterfly Wings on F9, one item on F4, F5 empty); the check's verdict
  `ok: false, refuses: true`.
- **20:13:26.34-20:13:27.85 ICT, the runner's own start function** `player_start_map` (its own
  screen, no Agent, no session; `no_input_guard` on): "dungeon@9.46 refused: --player-mode: the
  screen shows geffen, not xmas_dun02: walk or warp her there first (a person) [read from the
  minimap: 0.47, the next map 0.15]".

### Wired in (dungeon@9.46; `MAP_IDENTITY_VERSION = "9.46"`, `VERSION` stays dungeon@8.7)

- **The check's map line** (`CHECK_IDS` "cell"; `start_check`): the map FIRST (`read_start_map`:
  frames for up to `PLAYER_MAP_S` until one names a map; `player_map_verdict`), then her cell:
  - ✓ only when the minimap is the run's map AND her cell passes `player_start_refused` (+ the
    explore regions): "the minimap is xmas_dun02's (0.85; the next map 0.33); her cell (7, 21) is
    on xmas_dun02's open ground, in reach of its search area";
  - ✗ (`refuses: true`) on another map, before the cell rule: "she is on geffen, not xmas_dun02
    (read from the minimap: ...): walk or warp her to xmas_dun02 first"; a cell off the grid is
    the cell rule's ✗ as before;
  - ? when it cannot tell: "the map is not read from the minimap: <why>: look at the game -- is
    she on xmas_dun02? (her cell ... if she is) (the runner refuses a start that cannot tell)".
  The value stays the cell. Without references: "? -- no minimap reference for xmas_dun02 (build
  them: python3 scripts/minimap_id.py build)".
  ➡️ **The words since matpilot's round 16 #10 (2026-11-14, `minimap_id.map_verdict`):** a bare
  score ("0.47") said nothing to a reader, so every score is said with what it is and what it is
  measured against: "she is on geffen, not xmas_dun02 (the minimap shows geffen's map picture with
  a match score of 0.47, where 1.00 is the same picture and a map is named at 0.40 or more, 0.15
  ahead of the next; xmas_dun02's picture scores at most 0.21): walk or warp her to xmas_dun02
  first"; the tick: "the minimap is xmas_dun02's (it matches xmas_dun02's map picture with a match
  score of 0.85, where 1.00 is the same picture and the run's map needs 0.60 or more; the next
  map's picture scores 0.33); her cell ...". The quotes above and in "The live case" are the
  words printed at the time. Still bare: the runner's own start refusal
  (`dungeon_hunt.player_map_refused`, "[read from the minimap: 0.47, the next map 0.15]"), left
  for the branch that owns dungeon_hunt.py.
- **The runner's player start** (`run()`, `player_start_map`): after the check's branch and BEFORE
  the session folder and the session -- a screen of its own, no Agent -- it reads the map and
  refuses with "dungeon@9.46 refused: --player-mode: the screen shows <map>, not <run map>: walk
  or warp her there first (a person)", or, cannot tell, "... the screen does not show that she is
  on <run map> (<why>) within 3.0 s: a person first". Missing references refuse the same way
  (with the build command). `PLAYER_MAP_UNREAD = "warn"` would print a WARNING line instead (not
  used). `run_start` records the read (`player_map`) and `fixes.player_map` = [MATCH_MIN,
  NAME_MIN, MARGIN_MIN, PLAYER_MAP_S, PLAYER_MAP_UNREAD, "9.46"], player mode only.
- The /flows checklist text says the map is read from the minimap (config.ts); the runner export
  is regenerated (feature_version dungeon@9.46).
- Tests: `test_minimap_id.py` (the reader on SYNTHETIC bitmaps: translucency, marks, the key
  colour, copies, alike pictures, no picture, read_until, the scorer's labels), `test_live_check.py`
  (the three map-line outcomes through a fake screen's pixels, no input), `test_player_mode.py`
  (the start refuses another map and a start that cannot tell before any session or Agent; the
  order in run(); the records).

### What is left

- **The references are per host and per client.** They are built from the Thai archive (the lab's
  maps are byte-identical to kRO there); a client whose minimap bitmaps differ reads "cannot tell"
  (or, if a different picture matches better, the other picture's map -- seen once, new_1-1's
  frame matched `new_event` best in the development set). 629 of 731 bitmaps need the lab's study
  decoder; a learner without it has references for the 102 plain ones only, so a player start on
  an encrypted map refuses. A reference cut from the client's own frames (the median minimap of a
  recorded stand) would close that; not built.
- **Zoom:** only the whole-map view is modelled (the lab's). A zoomed-in minimap reads "cannot
  tell" (a refusal at a player start): zoom out first.
- **Towns are named, never ticked** (their NPC marks keep them at 0.47-0.62 < MATCH_MIN): a run
  that starts IN a town would refuse. No such run exists.
- The thresholds are constants, not Run settings (a person loosening them would loosen the
  safety line); `PLAYER_MAP_S` could be one.
- Maps without a minimap (indoor) always "cannot tell".

## The items on the keys (dungeon@9.47; matpilot's review 2026-11-13, round 15 #1)

**The gap (safety).** The runner presses ONE hotbar key per role: the heal item (`heal_key`, the
White Potion 504; with `--heal-candy` also the Candy Cane 530 on F6 and the Candy 529 on F7), the
Fly Wing (`fly_key`, 601), the Butterfly Wing (`home_key`, 602), the Knife (`knife_key`, 1201) and
the dagger (`dagger_key`). Since the keys come from the person's flow functions (any F1-F9), a key
can point at the wrong slot. The start (the check, and run()'s player start) read only the stack
COUNT under each key (`hotbar_count.py`), never WHAT ITEM is there: with `fly_key` = F1 (the
potions' slot) the check said "✓ at least 5 Fly Wings on F1 · read: 10 Fly Wings on F1", Run stayed
enabled, and the runner's escape would have drunk a potion instead of flying.

### The cue (studied 2026-11-13 21:31-21:42 ICT from `date`)

- **What the screen offers.** The 1-row hotbar draws the item's OWN ICON: the archive's 24 x 24
  item bitmap (`data/texture/<the UI folder>/item/<resource name>.bmp`, the name through
  `data/idnum2itemresnametable.txt`), 1:1, at game-region (246 + 29 k, 4) for slot k (F1 = 0). Its
  magenta key colour is transparent over the slot's white face (255; the face's top row is the
  frame line, 198). The stack count's black digits are drawn over the icon's lower right
  (hotbar_count's count box). Equipment in the bag shows its icon (the Knife on F4, the Damascus on
  F5); worn equipment is not drawn (an empty slot: bare_steal's readout). A skill (F3, Steal) is
  not an item bitmap. Measured on the live frame (21:31:06): each role icon's bitmap at (246, 4)
  read 0.8-4.2 (mean colour difference); one pixel off read >= 38.
- **How** (`scripts/slot_items.py`, numpy only; the same `read_slot` for the check, the start and
  the scorer):
  1. the slot's 24 x 24 square, in COLOUR (four potions share one bottle);
  2. every reference picture composited as the client draws it (the key colour = the white face),
     compared by the mean absolute colour difference over the square minus the count box and the
     frame's top line (`COMPARE`);
  3. the best picture is NAMED when its distance is <= `NAME_MAX` (20) and it beats every RIVAL
     (a picture within `RIVAL_RANGE` 30 of it) on the pixels that tell the two apart (where the two
     pictures differ by > `DIFF_PX` 30) by a LEAD >= `PAIR_LEAD` (0.5): (the read's difference from
     the rival - from the best) / the pictures' own difference there (1 = the best picture, 0 =
     halfway). Two pictures that differ on fewer than `DISCRIM_MIN` (6) pixels are ONE picture (a
     copy group: the Knife's 1201 / 1202 / 1203). The lead is what separates the colour variants:
     the White Potion is 11.3 from the Blue Potion as whole squares but leads it by 0.96; the
     Butterfly Wing (10.8 from the Green Butterfly Wing, whose picture differs by only 37 on 74
     pixels) leads by 0.81;
  4. EMPTY = hotbar_count's empty rule (no digit, no dark icon pixel) AND the slot's white face
     (`FACE_MIN` 250: a load screen's flat picture also has no digit and no dark pixel);
  5. otherwise "cannot tell": a dark frame (< 40), no face, no picture within `NAME_MAX`, or a
     rival too close.
- **The references** (`build`; CLIENT-derived, `data/slot_items/refs.npz`, gitignored, never
  committed; ~8 s): every item of the server's KB (`data/kb/items.json`, 6,169 ids; 4,456 of them
  in the archive's table, 4,449 with a bitmap) -> its resource name -> its bitmap. 2026-11-13
  21:35: 2,381 distinct pictures; 4,275 of the archive's 6,497 item bitmaps are MIXCRYPT (the
  lab's host-local study decoder, `--decode-mixcrypt`). The words' names are the KB's English
  ones. Rebuild (once per host; the NAS Thai archive read in place, read-only):

      OMP_NUM_THREADS=2 python3 scripts/slot_items.py build --decode-mixcrypt

### The development set (seen while designing)

`NAME_MAX`, `PAIR_LEAD`, `DIFF_PX`, `DISCRIM_MIN` and `RIVAL_RANGE` were set on the live frame
alone; `FACE_MIN` on these recordings. 18 NAS recordings, 2,076 frames: 12 sessions 11-06 .. 11-13,
every 5th frame of their first, middle and last shards (788), and 6 of them again, EVERY frame of
the first and last shards (1,288). Labels: a recording keeps one layout, so a slot's item is the
one its reads name in >= 3 frames (checked by eye on enlarged strips of 4 recordings). The
confusion, true item -> read:

    true \ read     itself   empty   cannot tell   ANOTHER item
    White Potion     2,032       .            44              0
    Fly Wing         2,032       .            44              0
    Knife            1,399     301 (worn)     40              0
    Damascus           301     564 (worn)     15              0
    Candy Cane         615     580 (used up)  32              0
    Candy              789     406 (used up)  32              0
    F3 (a skill)         -       .         2,076   0 (never named an item)

The "cannot tell" frames are whole-hotbar events: the client dims the screen before a map change
and then draws its load screen (no hotbar). Before `FACE_MIN`, 11 load-screen frames read all nine
slots "empty" (the flat sky has no digit and no dark pixel). START windows (3 consecutive frames,
1 s apart; a live start reads ~4 frames a second for `PLAYER_SLOT_S` 3 s): 1,252 of 1,266 decided
every layout slot; the 14 others are 7 map changes (the setup's warp, the end's warp, a respawn;
3 of them seen by eye: a dimmed hotbar, then the load screen). Own distances <= 5.1, the next
picture >= 11.1, the least lead over a rival 0.84 (the bar 0.5).

### PRE-REGISTERED (2026-11-13, commit 53c18e16 at 22:13:49 ICT, before the held-out set is read)

- **The held-out set:** 7 NAS recordings none of the development set read: 20261028T151136-rdp-
  stage-gef10-e3 (gef_fild10, 10-28), 20261111T041708-rdp-xmas02-fsTn3, 20261111T160248-rdp-hunt-
  xmas02-bs0, 20261112T005615-rdp-hunt-xmas02-fiT26, 20261112T072541-rdp-xmas02-sk2a,
  20261112T170954-rdp-hunt-xmas02-fiT44, 20261113T031511-rdp-hunt-xmas02-fiT61. EVERY frame of the
  first and last shards. Scored ONCE by `slot_items.py eval SESSION... --shards first,last`
  (`scripts/slot_items_eval.py`) with the constants above frozen and the 21:35 references. Before
  the scores count, a person (Claude, from the `--strips` pictures) confirms each recording's
  layout; a layout item that is not what the strip shows makes all its reads WRONG.
- **The bar:**
  - **S1 (the danger):** 0 reads name an item that is not the slot's (layout slots and the
    never-item slots: a skill named as an item is wrong too).
  - **S2:** >= 97 % of the 3-frame start windows decide every layout slot, and every undecided
    window is a map change (a frame with >= 7 of the 9 slots unread).
  - **S3:** of the layout slots' reads, >= 95 % name their item or "empty".
- **The runner's "cannot tell" rule, decided by S1 and S2:** both pass -> `PLAYER_SLOT_UNREAD =
  "refuse"` (a player start that cannot tell what a key shows within `PLAYER_SLOT_S` refuses, as
  it does on another item; a map change is no legitimate start). Either fails -> "warn" (the start
  prints a WARNING line and goes on; another item still refuses).

### The result: PASS (scored once, 2026-11-13 22:13:57-22:17:11 ICT from `date`, 194 s)

`slot_items.py eval <the 7 sessions> --shards first,last`, the 21:35 references, the constants as
committed: 1,451 frames. The layouts, confirmed by eye on one fetched frame per labelled slot
(every label matches what the strip shows): F1 White Potion and F2 Fly Wing in all 7; F4 the Knife
in 4; F5 the Damascus (in the bag) in bs0; F6 the Candy Cane in 3; F7 the Candy in 4. F3 is a
skill in all 7, and fsTn3 has two more skills on F4 and F5 (a person icon, a heart with a cross).
True item (rows) -> read:

    true \ read     itself   empty   cannot tell   ANOTHER item
    White Potion     1,414       .            37              0
    Fly Wing         1,414       .            37              0
    Knife              909       .            20              0
    Damascus            27     145 (worn)      8              0
    Candy Cane         495     164 (used up)  15              0
    Candy              588     321 (used up)  20              0
    the never-item slots (empty slots, 3 kinds of skill): 5,554 empty, 1,891 cannot tell, 0 items

| Bar | Registered | Result | |
|---|---|---|---|
| S1 | 0 reads name an item that is not the slot's | 0 of 13,059 slot reads | PASS |
| S2 | >= 97 % of the 3-frame windows decide; every undecided one a map change | 1,409 / 1,423 (99.0 %); the 14 others all map changes (7 events: the first / last frames of a shard, the warps) | PASS |
| S3 | >= 95 % of the layout slots' reads name their item or "empty" | 5,477 / 5,614 (97.6 %) | PASS |

- **The runner's rule, as registered:** S1 and S2 passed, so `PLAYER_SLOT_UNREAD = "refuse"`
  stays: a player start that cannot tell what a role's key shows within `PLAYER_SLOT_S` (3.0 s of
  frames) refuses, as one whose key shows another item does. Its only undecided windows, here and
  in the development set, are map changes, where no legitimate start happens.
- **The rows** (one per frame: the session, every slot's read and words), the development rows,
  the live check's outputs, the live frame and the layout strips: the NAS
  `scratch-archive/2026-11-13/slot-items/` (SHA256SUMS, README.txt).

### The live case (read only, the lab's screen; pixels only, no input)

She stands in Geffen at (119, 40); her hotbar (read by eye on the 21:31 frame): F1 10 White
Potions, F2 empty, F3 a skill (Steal, 10), F4 the Knife (1), F5 empty (the dagger worn), F6 empty,
F7 4 Candies, F8 10 Fly Wings, F9 3 Butterfly Wings.
- 21:31:06-08 ICT: one game-region frame (study). `slot_items.py read`: F1 White Potion (0.9, lead
  0.96), F4 Knife (0.8, 0.99), F7 Candy (3.6, 0.92), F8 Fly Wing (3.0, 0.95), F9 Butterfly Wing
  (4.2, 0.81), F2 / F5 / F6 empty, F3 cannot tell (nearest picture 76.7).
- **21:52:43-47 ICT, `dungeon_hunt.py check` with the flow's own argv** (`flow_run.check_command`,
  the worktree, the 21:35 references): wings ✓ "10 Fly Wings on F8: at least 5; F8 shows a Fly
  Wing (read from its icon)"; heals ✓ "10 heal items on F1 ...; F1 shows a White Potion"; home ✓
  "3 Butterfly Wings on F9 ...; F9 shows a Butterfly Wing"; knife ✓ "F4 shows the Knife (read from
  its icon) with no stack count"; the map line ✗ (Geffen), so `ok: false, refuses: true`.
- **21:52:58-21:53:02 ICT, the WRONG mapping through the real check** (the same argv with the
  flow's keys swapped: `--fly-key F1 --heal-key F8`; one key for each role, so the preamble's clash
  rule passes): wings ✗ `refuses: true`, value "10 on F1": "F1 shows a White Potion, not a Fly Wing:
  set the Fly Wing's key to the Fly Wing's slot"; heals ✗ "F8 shows a Fly Wing, not a White Potion:
  set the heal item's key to the White Potion's slot"; home and knife ✓.
- **21:53:16-17 ICT, the runner's own start function** `player_start_slots` with the same wrong
  keys (its own screen, no Agent, no session; `no_input_guard` on): "dungeon@9.47 refused:
  --player-mode: F1 shows a White Potion, not a Fly Wing: set the Fly Wing's key to the Fly Wing's
  slot; F8 shows a Fly Wing, not a White Potion: set the heal item's key to the White Potion's
  slot".

### Wired in (dungeon@9.47; `SLOT_ITEMS_VERSION = "9.47"`, `VERSION` stays dungeon@8.7)

- **The roles read** (`slot_role_keys`): the Fly Wing, the heal item (+ the Candy Cane and the
  Candy with `--heal-candy`), the Butterfly Wing (when there is a key) and the Knife (`--bare-steal`
  with `--steal-opener`). The dagger's key is read EMPTY by bare_ref_cut (worn: no icon to name).
- **The check's lines** (`start_check`: `read_role_slots`, frames until every role's slot reads,
  for up to `PLAYER_SLOT_S`; `slot_role_state`): ANOTHER item first -- ✗ `refuses: true`, "<key>
  shows <item>, not <role's item>: <fix>", the value the count ("10 on F1"); then the count rule as
  before; then "cannot tell" -- ? "<n> on <key>: at least 5, but cannot tell whether <key> shows a
  Fly Wing (<why>) (the runner refuses a start that cannot tell)"; else ✓ with "<key> shows a Fly
  Wing (read from its icon)". An EMPTY slot is no item: the count rules speak (0 Fly Wings refuse; a
  used-up Candy Cane does not; an empty Knife slot is opener_ref_cut's "the opener is worn"). The
  home line, which never refused on its count, refuses on another item (its way home would use it).
  Without references the four lines are ? with the build command.
- **The runner's player start** (`run()`, `player_start_slots`): after the check's branch and the
  map read, BEFORE the session folder and the session -- a screen of its own, no Agent -- it refuses
  with "dungeon@9.47 refused: --player-mode: <key> shows <item>, not <role's item>: <fix>" (every
  wrong key in one line), or, cannot tell, "... cannot tell whether <key> shows <item> (<why>) --
  within 3.0 s: a person first". Missing references refuse the same way. `run_start` records the
  reads (`player_slots`: per role its key, the verdict and the read) and `fixes.player_slots` =
  [NAME_MAX, PAIR_LEAD, PLAYER_SLOT_S, PLAYER_SLOT_UNREAD, "9.47"], player mode only.
- The runner export is regenerated (feature_version dungeon@9.47). The /flows checklist's own text
  is unchanged (the check's words say what each slot shows).
- Tests (SYNTHETIC icons only): `test_slot_items.py` (the reader: where the client draws, a copy
  group, two potions that differ only in the liquid and a half-covered one, empty / flat / dark /
  unknown slots, read-until-decisive, the references' round trip; the role words; the refusal rule
  both ways; the start refuses a wrong key and a start that cannot tell before any session or
  Agent, goes on with every role right; the order in run(); the records), `test_live_check.py`
  (matpilot's swapped keys through the check; the three outcomes of each of wings / heals / home /
  knife; no references; the heal candies each on its own key).

### What is left

- **The references are per host and per client** (the Thai archive's bitmaps; 4,275 of 6,497 need
  the lab's study decoder). An item of the server's KB with no line in the archive's table (1,713
  of 6,169: the newer items, which the 2021 client names in its iteminfo instead) has no reference:
  on a role key it reads "cannot tell" (a refusal), never a false "right".
- Only the 1-row hotbar at its home is modelled; a moved or 2-row hotbar reads "cannot tell" (a
  refusal at a player start).
- The thresholds are constants, not Run settings (a person loosening them would loosen the safety
  line); `PLAYER_SLOT_S` could be one.
- In the run itself the keys are not re-read: a person who drags another item onto a key mid-run
  is not caught (the count guards still read their counts).

## Not built yet

- **The map's name from the screen** (the 9.45 live read's gap, above): the cell rule passes on
  another map whose cell falls on this map's open ground; a person checks the map.
  ➡️ dungeon@9.46 (above): read from the minimap's picture.

- **Batt's later steps:** walking to a Kafra and warping through its menu (the UI gate's known
  steps), buying from an NPC shop, selling loot.
- **The MVP.** The lab kills it before every run with `@killmonster2`. A player cannot, so the
  only protection is the runner's boss guard: a Fly Wing on a boss or minion Battle Log line,
  active only with `--engage-screen`. Its live flee proof against Stormy Knight (rogue-xmas02.md
  4CS) FAILS as registered: F1 died in the runner's own setup before the loop ran (4CU), so the
  escape itself is unproven. A player-mode run on a map with an MVP is protected by nothing
  proven. Since 9.35b the start WARNS on such a map when the guard is off (above); it does not
  refuse (Batt).
- ~~**A "go home" item at the end:** a Butterfly Wing on a hotbar key would be a player's own way to
  the save point. Nothing presses one today.~~ ➡️ BUILT in 9.35b (above).
- **A learner's own character and data:** the identity check needs that character's name and job
  references (crusader.py's cut steps), and the hotbar digits, the KB, the GATs and the map's zones
  and route are local files built on the lab. None of that comes from the server.
  ➡️ PARTLY BUILT 2026-11-12 (found 20:1x, second-install-gaps.md row R): the start's identity
  check read the lab DB (`r.online_chars`) even under the flag, so a run on a server of someone
  else's refused at its start. dungeon@9.35c passes `db=False` under `--player-mode`.
  `crusader.py --char <c> init --name` writes the learner's `char.json`, and `--no-db` on check /
  cut-name / cut-job cuts the references without the lab DB (a printed warning, no lock;
  new-lab-host.md 11.1). Still open: the runner's per-character numbers and keys (`CHARS_CONF`).
- **ADR-0023 decision 2 in the judges:** a player-mode run carries `fixes.player_mode`, but no
  judge or the economy page filters on it yet.
- **No live run has been made** (the build had no live access): the first one should be on the
  LAB server, where the packets can confirm that no GM line was typed. ➡️ Batt 2026-11-12
  (rogue-xmas02.md 4DF): no lab live test of player mode.

## Not in scope

- Anything that reads or changes the server beyond pixels and input (CLAUDE.md rule 1).
- Lab research numbers: a player-mode run on a declared server is never counted (ADR-0023
  decision 2).
