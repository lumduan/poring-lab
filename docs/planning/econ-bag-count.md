---
doc_type: hypothesis
hypothesis: "The bot can COUNT ITS OWN BAG from pixels -- open the inventory (Alt+E), read every tab's slots (the item by its own icon, the stack by its digits), close it -- exactly enough that a Run's income and costs are the bag's change between its start and its end, with no packets, on any client."
status: PROPOSED
role: null
verdict_date: null
verdict_ticket: null
supersedes: null
related: [../econ/economics.md, ../../scripts/slot_items.py, ../../scripts/hotbar_count.py, ../../scripts/econ_dash.py, ../../packages/poring_env/src/poring_env/panelfind.py]
next_action: "Build scripts/bag_count.py (section 3), then the offline trials against the lab database (section 4)."
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
