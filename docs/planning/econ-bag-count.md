---
doc_type: hypothesis
hypothesis: "The bot can COUNT ITS OWN BAG from pixels -- open the inventory (Alt+E), read every tab's slots (the item by its own icon, the stack by its digits), close it -- exactly enough that a Run's income and costs are the bag's change between its start and its end, with no packets, on any client."
status: PROPOSED
role: null
verdict_date: null
verdict_ticket: null
supersedes: null
related: [../econ/economics.md, ../../scripts/slot_items.py, ../../scripts/hotbar_count.py, ../../scripts/econ_dash.py, ../../packages/poring_env/src/poring_env/panelfind.py]
next_action: "Amendment 8 (Batt 2026-11-24): the item tally -- the item popups counted as they come (the Run's log, /flows), the end census adjusts it, a Run with no end census keeps it as its economy; built on branch feat/item-tally; dev check on the client after the mark A/B, frontend checks, then live on Batt's word (copy the count font to live's data/)."
title: "The economy from the bot's own bag (Economy option b-i): count the inventory at a Run's start and end (pre-registration)"
date: 2026-11-20
owner: Batt
---

# The economy from the bot's own bag (pre-registered 2026-11-20)

## 1. The decision

Batt 2026-11-20, choosing the Economy page's option (b)(i): "do this: it is the way people do it.
But the bot may need to be taught to open the bag: try it OFFLINE first, so that it is exact. Press
Alt+E and try every tab; RO splits the bag into categories (things to eat, clothes, weapons ...)."

Earlier (option b): "option a I could not teach; option b is the way it works in real life, like a
fruit-picking robot or a robot that counts eggs."

So the Run counts its bag at its start and at its end. Per item, the change is what the Run gained
(loot: up) or used (potions, Fly Wings: down). It needs no packets, so it works on every server.

## 2. What the screen offers (measured 2026-11-20 13:1x on the lab's 1920x1080 client)

- The inventory opens with Alt+E (`ui_gate.window_keys("inventory")`; a toggle). RO draws it at
  1:1 on the real screen. It is not one of the virtual view's pasted panels, so it is read on the
  REAL client frame (the virtual view shrinks it with the world).
- **Tabs:** four, on its left: Use, Eqp, Etc, Fav. A tab's label points, relative to the window's
  origin (the title bar's top-left): (10, 45), (10, 100), (10, 154), (10, 205).
- **Slots:** 7 columns x 6 rows on a 32 px pitch.
  - Slot (0, 0)'s icon is a 24 x 24 square at the origin + (44, 21), drawn 1:1. It is the archive's
    item bitmap, its key colour transparent.
  - An EMPTY slot shows a light blue-grey oval (206, 214, 231), 24 x 13 at +(44, 31) of its cell.
    The oval is drawn BEHIND an item too: it shows through a thin icon (the Knife).
- **Counts:** the stack's digits are PURE BLACK (0, 0, 0). The icons' darkest outline is 8, so
  "ink" is max channel <= 3.
  - Left-aligned from the icon's x + 14, rows +18 .. +26, on a 7 px pitch.
  - The glyphs are the hotbar's (`hotbar_count` templates): 8 / 1 / 17 / 13 / 7 / 46 / 37 read
    exactly.
  - Equipment shows "1" too.
- **The footer** "22/100": the number of bag entries, worn equipment included.
- **Worn equipment** is not in the bag's tabs (it is in the equipment window). It is not income.

## 3. The tool (`scripts/bag_count.py`)

- **PURE readers** on a real-client BGR frame.
  - `find_window`: the bag found by the LATTICE of empty-slot ovals (a rule, no template, no
    text, so any language).
  - `read_tab`: each slot is "empty", an "item" (its ids by `slot_items`' pictures composited over
    THIS client's own empty-slot picture, cut from an empty slot at run time; its count), or
    "unread" (with the reason).
- **The census** (live): open with Alt+E (the bag must appear where it was not), each tab by a
  paced two-motion click, then the pointer parked off the grid.
  - Each tab is read twice on fresh frames, and the two must agree.
  - Close with Alt+E (the bag must be gone).
  - A tab whose 42 slots are all items may hold more: version 1 reports it "full: may hold more"
    (a scroll is the next step), never a guessed total.
- **Never guessed:** an unread slot is counted as unread, and the economy says how many there
  were.

## 4. The offline trials (the bar, fixed before any trial)

On the lab, the Rogue in prontera 156,180 (no monster), the truth is the lab database
(`ro_agent.db_query`, read only: the `inventory` rows of the character with `equip = 0`).

- **Bags:** at least 5 different bags, made with GM commands (@item / @clearitem on our own
  character). Together they hold:
  - 1-, 2-, 3- and 4-digit stacks;
  - all three of Use, Eqp, Etc, plus favourites;
  - an unidentified item;
  - two items that share an icon;
  - at least one tab with over 21 entries.
- **The bar, every trial:**
  - **B1:** 0 WRONG reads. A slot named as another item, or a wrong count, fails the trial (a
    wrong number is worse than "unread").
  - **B2:** at least 98 % of the bag's entries read (item + count). An unread entry is allowed but
    counted.
  - **B3:** the census leaves the bag CLOSED and the client as it was (the UI gate's state
    before = after).
  - **B4:** at most 20 s per census for a bag of at most 40 entries.
- A shared-icon group (e.g. Sandals 2401 / 2402) counts as RIGHT when the true item is in the
  group. The economy prices a group only when its items' prices agree, else it is shown as "an
  item of <group>, unpriced".
- **Only after B1-B4 hold on every trial:** the Run integration (a census at its start and end),
  then Batt's live trial.

## Amendment 1 (2026-11-20 14:05 ICT from `date`): take 1 of the trials found five things; take 2 restarts the trials

The bar (section 4) is unchanged. Take 1's trial results are VOID, for reasons a)-b); take 2
runs T2-T6 again from the start.

- **a) The lab database lags the game.** It is written at the server's autosave (<= 5 min,
  rAthena's default `autosave_time`). T2 was judged against the bag from before its adds: a
  "wrong" (Red Potion x5 "not in the bag") that was the census being right.
  - Take 2 waits until the database shows the change and settles (two equal reads 15 s apart).
- **b) `@delitem` was not allowed** in the lab's group 20, so take 1's removals did nothing, and
  (a) hid it. Batt approved it at 13:5x ("Add @delitem"). Applied by a guarded
  `recreate:rathena,sniffer`, read back by a census. An add can fail silently too
  (`@item 601 199` added nothing), so the truth is the database, never the planned adds.
  `@item2` is not allowed either: the unidentified item is the baseline's own Sandals (2402,
  identify 0), present in every trial.
- **c) A NEW item draws a pink glow** (a gradient, 255,131-165,247) where the oval was.
  - Icons are now compared on each picture's own pixels.
  - Guard: the rest of the square must be slot background.
  - On take 1's frames: 29/29 right, the worst distance 5.2, the nearest rival 22+.
- **d) A count's place:** from x+14 (x+15 for a leading '1') unless it would pass x+26; then it
  ENDS at x+26 ("1001" = x+1..26). Take 1's 19 Etc counts, 1 to 1001, all read.
- **e) A bag at the frame's edge:** its outside ring fell outside the frame and the true place was
  dropped. A ring cell beyond the frame now counts as "no oval".
- **Speed (B4):** 21.4 s at first.
  - The fixed 0.9 s wait after a tab click became "until its slots change". This skin draws no
    selected-tab cue.
  - The bag's box only is grabbed once its place is known.
  - 16.8 s for 28 entries.
- **Never twice:** an item in two tabs = a click that did not take. The tab is clicked again,
  else those slots are unread.

## Amendment 2 (2026-11-20 15:23 ICT from `date`): take 2 FAILS B1 twice; two reader fixes; take 3 runs T2-T6 again

Take 2's truth was right this time: the database after the autosave settled, so a silently failed
add (`@item 601 199`, items 927 / 933) simply is not in it.

| trial | entries | B1 | B2 | B3 | B4 | |
|---|---|---|---|---|---|---|
| T2 | 16 | pass | 16/16 | pass | 16.3 s | |
| T3 | 37 (Etc 30) | pass | 37/37 | pass | 18.7 s | |
| T4 | 19 | pass | 19/19 | pass | 16.0 s | |
| T5 | 18 | **FAIL** | 17/18 | pass | **27.3 s** | 938 x123 read **12** |
| T6 | 40 | **FAIL** | 39/40 | pass | 17.7 s | 909 x600 read **60** |

- **The cause (measured on take 2's own frames):** a 3-digit count is drawn from x+14 to x+33
  ("123" = 15-19, 21-26, 28-33), but the band stopped at x+28. Its last digit was cut and the rest
  read as a shorter number. A 4-digit count ENDS at x+26 ("1000" = 1-26), and the next slot's
  4-digit count starts at our x+33.
- **Fix 1:** `count_of_runs` reads only the measured shapes:
  - 1 digit 14/15..19; 2 digits ..26; 3 digits ..33; 4 digits 0/1..26.
  - The runs must be consecutive and all digits, with NO ink within 3 columns before or after the
    group (a covered digit or a neighbour's: unread, never a shorter number).
- **Fix 2:** moving the band to x-2 had also moved the icon compare mask (it reused the band's
  start), so the count digits were compared as icon pixels. The mask now leaves out every column of
  the count's rows.
- **A replay of take 2's saved frames with the fixed reader** (NOT a trial; the frames that found
  the bug): T2-T6 all right, 0 wrong, 0 unread; the worst distance 5.2, the nearest rival 18.5.
- **A known limit, by design:** a 3-digit count (to x+33) touching the next slot's 4-digit count
  (from its x+1 = our x+33) makes both unread; they are said, not guessed.
- **T5's 27.3 s:** the host was loaded at that minute (my frontend test run in the container,
  14:49). Take 3 runs with the host quiet.
- **Take 3:** T2-T6 again, fresh bags with new counts (including 3-digit stacks), the same bar and
  truth. Only when all five pass does the Run integration start.

## Amendment 3 (2026-11-20 17:07 ICT from `date`): take 3 PASSES B1-B4 on every trial; the Run integration starts

| trial | entries | B1 (0 wrong) | B2 (>= 98 %) | B3 (as found) | B4 (<= 20 s) |
|---|---|---|---|---|---|
| T2 | 15 (a 4-digit 1100) | pass | 15/15 | pass | 17.7 s |
| T3 | 37 (Etc 30; 3-digit 101-105) | pass | 37/37 | pass | 17.8 s |
| T4 | 19 (shared icon 2401 / 2402; 3-digit 555) | pass | 19/19 | pass | 16.4 s |
| T5 | 18 (3-digit 456; look-alike wings 602 / 12324) | pass | 18/18 | pass | 16.7 s |
| T6 | 40 (a 4-digit 1000) | pass | 40/40 | pass | 18.3 s |

- **T5 ran twice.** The first time (15:59) its census never began: the lab client stopped drawing
  (black / minimised; the agent's terminal in front) and the mux refused a key,
  `client_not_foreground`. `ro_agent.py recover gm` relaunched it at 16:04. The leftovers were
  removed and the bag was the baseline again (from the database, saved at the logout); T5 and T6
  then ran fresh.
- **Take 3's T2 tested less than designed.** My weight sums were 10x off: the item table's 70 is a
  weight of 7.0, so Red Potion x120 and White Potion x93 would have overweighted her and were
  refused. The database truth showed it, and T3 / T5 cover the 3-digit stacks.
- **THE VERDICT:** the bag counter meets the pre-registered bar offline.
- **Next, the Run integration** (Batt 2026-11-20, his choice for a Stop: "count, then stop"):
  - a census at the Run's start, before the first hunt;
  - and at its end, including after a Stop: the bot stops hunting, counts (~17 s, keys only),
    closes the bag, then ends. A second Stop skips the count (no economy for that Run);
  - the Run's economy is `econ_bag`'s entry, written for the /economy page;
  - a census that fails warns and the Run plays on (never a lock).

## Amendment 4 (2026-11-20 19:53 ICT from `date`): the wings stay unpriced (Batt)

- Each wing shares its icon with a Novice twin that has no NPC price: the Fly Wing with the
  Novice Fly Wing, the Butterfly Wing with the Novice Butterfly Wing. The bag cannot tell them
  apart, so econ_bag prices a group only when its members' prices agree, and a wing group stays
  unpriced (cost 0).
- Recommended: price a group by its one NPC-sold member. **Batt 2026-11-20: "ปีกไม่ต้องใส่ราคา"
  (do not price the wings).** The rule stays as built. The economy still shows the wings' USED
  counts; they are not in the cost.

## Amendment 5 (2026-11-23 12:52 ICT from `date`): the window's ROWS (Batt's 7 x 9 live bag); on main; the dev trial

- **Why:** live's Run start has always said "the bag did not count at the start: Alt+E showed no
  bag (no oval lattice found)": Batt's bag window is 7 x 9 (dragged taller); section 3's rule
  fitted a fixed 7 x 6, and on a 7 x 9 tab with 21+ items it would fit the ovals three rows LOW
  (a silent wrong place). Batt 11-23 ~12:3x: "carry on" (fists-1080.md Amendment 10).
- **The change** (built 11-22 04:1x on branch `bag-rows`, rebased onto main and merged 11-23 12:39:
  cf8ae9ea, ad19d6d0): the ovals still fix the window's columns and its LAST row (the tail rule,
  the clear ring); its TOP is the first row, going up, that shows no slot (a slot row shows >= 4
  rows of oval or NEW-glow pixels in its oval box: an empty cell 10, an item 6-10, the title bar
  1-2); rows 6..12, else no bag. `find_bag` returns the origin and the rows; the census records
  "rows" and checks every tab at the same place and rows. Tests: 7 x 6 / 7 / 9 / 12 found at any
  fill, a 7 x 9 tab read item for item, a bag cut by the frame's edge, taller than 12 = none.
  35 tests pass (bag_count + ro_agent panels; the panel tests need the checkout's data/).
- **The dev trial (12:49 and 12:5x, the trial command, B1-B4 of section 4):** the lab's 7 x 6 bag
  found with rows 6 at (0, 120); 15 of 15 entries right, 0 wrong, every slot read, as found,
  16.8 s: **PASS, twice**. Nothing regressed for 7 x 6.
- **7 x 9 cannot be made on the dev client:** its inventory window did not grow from its resize
  grip (three drags, fast and slow) -- Batt's client allows it, the lab's does not -- so 7 x 9 is
  checked by the synthetic tests only, and on live by the Run's own start census after the
  promotion (its log line names the rows).
- **Live:** the live branch is 100 commits behind main (31 files: also the route recorder's
  frontend, the fists fix 83645b20, popup round 5, the item rule's part C settings); a promotion is
  Batt's word, between Runs.

## Amendment 6 (2026-11-23 13:39 ICT from `date`): promoted to live (Batt's word)

- **Batt, 11-23 ~13:3x:** "do it, I have stopped live" (the promotion) and "do it" (frontend-dev).
- **Before it:** the frontend's checks in frontend-dev (started for them, removed after): lint OK,
  typecheck OK, unit tests 612 (611 pass, 1 skipped, 0 fail; the route recorder's included).
- **The promotion (13:35-13:39):** the live branch fast-forwarded ffccaef3 -> 2b2e42da (70 files)
  and pushed; the live backend restarted (guarded, ALL STEPS OK), its frontend image rebuilt and
  recreated (guarded, ALL STEPS OK), its Run helper restarted by PID (3512557). After: the live
  console 200, /flows 200, the backend's /health ok (mode HUMAN: a restart boots HUMAN and the guard
  restores only ASSIST; Batt sets the mode for his next Run).
- **Not installed:** the route recorder's host helper (`scripts/host/poring-lab-routerec.service`) is
  a user unit for the DEV checkout; live would need its own, and it records from the live console:
  Batt's word, after his announce-first rule.
- **Next:** the next live Run's start census should name 9 rows; its log line and /economy's items
  are read then (no new capture: logs only).

## Amendment 7 (2026-11-23 15:00 ICT from `date`): live's first census -- the window found, every count missed; two fixes

- **Live's Run at 13:40** (after Amendment 6's promotion) found the bag for the first time but read
  "0 kinds, 27 slot(s) unread"; the line said no more. 5981cd88 makes the line name the window's
  rows and the unread slots' reasons (`flow_play.bag_words`).
- **One census on Batt's client at his ask** (14:39, Batt: "ready", live's Run stopped, the console
  set to ASSIST by him; the live checkout's `bag_count.census` with `frames_dir`: the bag window's
  box only, per tab read): the window **7 x 10** at (873, 130), 20.2 s, left as found; 46 slots
  unread:
  - the icons matched (nearest-picture distances 1.6-3.2);
  - **"the count did not read" on nearly every slot**: his client draws every count **2 px left**
    of the lab's (the digits themselves read right with either font: "89" at x+12 .. 24, "304" at
    x+12 .. 31, a leading '1' at x+13), and the shapes are the lab's (x+14 / x+15);
  - **the tab clicks missed**: a taller window stretches its four tabs (centres ~61 / 144 / 227 /
    310 px, ~83 px each vs the lab's 45 / 100 / 154 / 205), so the "Eqp" click hit cons., "Etc" hit
    equip and "Fav" hit etc.
- **The fixes (1486b645, with tests):** `count_shift` learns a client's count shift from its own
  clean counts (the most common, >= 2 agreeing, within +-4 px; else 0, the lab's); `tab_xy` keeps the
  lab's measured tabs at 6 rows and splits a taller window's strip in four. On the census's own
  pictures: shift +2 (17 votes); the cons. tab 16 of 17 read, every count right (89, 1, 304, 120,
  506, 194, 24, 1, 15, 12, 5, 2, 4, 1, 1, 1); the rest of the 29 distinct slots read except 4 icons
  the lab's pictures lack (his server's items: never guessed). The lab's 7 x 6 is unchanged (shift 0,
  TABS).
- **Live updated at 14:59:52** (Batt: "ok"; 2b2e42da -> 1486b645, two script files, between his
  Runs: the 14:46 Run had ended at 14:59:50); the next Run is the check.

## Amendment 8 (2026-11-24 13:42 ICT from `date`): the item tally -- counted as the items come, the census adjusts

- **Batt, 2026-11-24 ~13:1x (his words, translated):** "Why don't we count each time an item comes
  in, so it updates in real time? Do it on /flows, and in the Run's log too: what was collected.
  The count after the Run is an adjustment. Then a Run ended by HUMAN keeps the count made while
  it played." (His 09:42 Run ended by HUMAN: the end census needs the keys, so it had no count:
  xmas02-items-1080.md Amendment 52.)
- **Built (branch `feat/item-tally`):**
  - `scripts/item_tally.py`: during a Run, the item popup reader (item_popup.py, round 5's code)
    as a thread with its OWN screen pipe, grabbing the popup's band on the real frame 4 times a
    second (as the 11-23 live watcher did: 0 grab errors, ticks p95 84 ms). Each popup read is
    one gain: its key is bag_count's group key, its amount the count font's read (None -> counted
    as 1, said so); a popup whose item did not read is not counted, said so. Display and record
    only: no decision reads it; a failure stops the tally with a WARNING, never the Run.
  - `flow_play.play`: the tally starts after the start census and stops before the end census, in
    the Run's own record (`item_gained`, `items_tally`, `items_adjust`) and the Run's log
    (`+ Zargon x1 (Zargon 12 in all)`). It plays with the Economy's bag count (the Run option, on
    by default); `PORING_ITEM_TALLY=0` turns it off in one process.
  - **The end:** with both censuses, the bag's change is the truth and `items_adjust` records the
    tally beside it per kind (the log says whether they agree); **with no end census** (a HUMAN
    stop, a death, an error) the Run's economy is written FROM THE TALLY (`econ_bag.run_from_tally`,
    `counted_by: popups`; no consumables, since only a census sees what was used).
  - `flow_run` (the Run helper's live tracker): the gains on the Run's story (`+ Zargon x1`, also
    into the Run log on the Settings page), and the tally in the page's summary (`items`,
    `items_total`, `items_kinds`, `items_unread`, `items_census`).
  - /flows: the monitor bar's items tile shows the tally (it showed loot clicks before), and a
    box "Items gained" lists the kinds, most first, with the end's count beside them.
- **What it is NOT yet:** the reader has passed its bars at 720 (round 3) but not yet at 1080
  (round 4 failed P by one re-read: 2.07 % against 2 %; round 5's set w1080c is not complete).
  On live its icons read and its AMOUNTS do not (his client's digits; a count font from crops of
  the popup band needs Batt's "ready" first). So on live each gain counts as 1 until then, and the
  end census stays the truth whenever it runs.
- **Checks:** tests for the tally, the watcher's emit, the play() wiring (both ends counted; no end
  count -> the tally's economy), the helper's summary and the economy from the tally; the related
  Python suites pass. The frontend's checks (lint, typecheck, unit tests) run in frontend-dev after
  the mark's A/B chain ends (no CPU burst during its runs), then a dev Run on the client, then
  live on Batt's word (with the count font copied into live's data/ui_anchors).

## Amendment 9 (2026-11-24 16:47 ICT from `date`, before its run): the branch's checks; the tally's check on the dev client registered

- **Checks run after the mark's A/B chain ended (16:08):**
  - the full Python suite on the branch (its worktree, the main .venv): every test passes but six
    whose failures are the worktree's alone -- five need the gitignored `data/` (UI templates,
    loot icons, GAT; they pass with the dev checkout's data folders linked in: 15 of 15), and
    `test_collect_v2::test_preflight_fails_closed_then_passes`, the order dependence of its own
    (next-target-mark.md Amendment 4; it passes alone); mypy clean (150 files); ruff format clean;
    ruff check: 2 E501 lines that main has too (`routes_econprices.py` and its test, since
    57b963e6 on 11-21), not this branch's;
  - the frontend in frontend-dev (started through guarded_build for the checks, removed after):
    lint clean; typecheck found one error in this branch's new test (`itemRows(base)`: a summary
    sharing no field with `Pick<LiveSummary, "items">`), fixed (866cc59f); then lint, typecheck
    and the unit tests clean: 613 tests, 612 pass, 0 fail, 1 skipped. The same run found main's two
    registry-count tests red since the next-target mark's three optional blocks (771cf35b: 137 ->
    140); fixed on main (5300e4a2: main alone 611 pass, 0 fail, 1 skipped).
- **The check on the dev client (registered now, before its run): itc1.** One 10-min screen_ab run
  of today's fists box (`--box-set knife_swap=false`; mk_run.sh's procedure: town, heal, the zoom
  check, town, the chat-window standard) from the dev checkout with this branch merged, its series
  run with the Run's bag count ON (screen_ab's measured series turn it off, `PORING_BAG_COUNT=0`;
  a scratch wrapper drops that one variable from stage2_ab's child environment, the series' code
  unchanged), so the tally starts after the start count. Not immune; no recording; no picture is
  saved (the watcher's crops are off in a Run; the census saves none without `--frames`).
- **Scored once after it** by the committed `docs/records/scorers/item_tally_check.py itc1`:
  - PLUMBING (all three -> PASS): P1 the run ended rc 0; P2 the tally started (its start line, no
    off / did-not-start / stopped-early line) and wrote >= 1 `item_gained` while the packets show
    >= 1 gain in its window; P3 its totals recorded at the end (`items_tally`; `items_adjust`
    reported when both counts read);
  - REPORTED, not judged (the reader's 1080 accuracy bar is item-popup-reader.md's round 5):
    each packet gain (`pickup_result` ok) matched to a tally gain with that item among its ids
    from 1.0 s before to 3.0 s after it -- recall, precision, amounts equal, item / amount unread,
    totals (tally vs packets), the end count's adjustment, the median lag.
- **After:** a PASS -> main pushed with the branch; live only on Batt's word (and the count font
  copied into live's `data/ui_anchors`). A FAIL -> fixed before main is pushed.
