---
doc_type: plan
status: ACTIVE
role: null
verdict_date: null
verdict_ticket: null
supersedes: null
related: [econ-bag-count.md, ../econ/economics.md, ../../scripts/bare_steal.py, ../../scripts/bag_count.py, ../../scripts/slot_items.py, ../../scripts/econ_screen.py]
next_action: "Round 3 PASSED (RESULT round 3, 2026-11-22 19:25): pre-register section 4's 1080 run-time check on dev (its own amendment); the reader feeds no Run before that check passes."
title: "Every item gained, from the client's item-obtained popup: which item, how many (pre-registration)"
date: 2026-11-21
owner: Batt
---

# The item popup reader (pre-registration, 2026-11-21)

Written before the reader exists. Nothing below is edited after its commit, except by a labelled,
clock-stamped amendment (section 8).

## 0. What Batt asked

2026-11-21 ~20:3x, with a live screenshot: "Every item gained, by a pickup or a Steal, shows its
icon at the same place on the screen every time, and the chat says so too. Build a check for it;
we can use the name shown to make the list of everything gained in each Run." On the order
(20:4x): "the popup first, then the bag count; try it on dev first, how accurate it is, because
it can be compared with the packets."

Why it matters: live has no packet capture, so its /economy page knows no items. The bag count
(econ_bag.py) fails on Batt's client every time ("Alt+E showed no bag": its window is 7 x 9 slots,
and the lattice finder wants 7 x 6). Batt then asked for the lab's page on live: items, NPC prices,
unknown prices typed in and saved with an Update button.

## 1. The facts (measured 2026-11-21)

- **The popup** is a white rounded box with the item's icon, its name and the count. It sits at a
  fixed place and has a left-aligned width (bare_steal.popup_box: rows 76-105 of the 1280 x 720
  region, its left edge at x 541).
  - On the 720 recording fiT20 (a Zargon, #912, at +0.4 / +1.4 / +2.4 s after its pickup_result),
    the box is (541, 728) on all three frames, and the icon's ink is x 557-571, y 84-100.
  - The text, after the icon: the dev client "<name> - 1 obtained."; Batt's Thai client
    "Scell 1 ชิ้น".
- **At 1080** the client draws it 1:1 on the REAL frame, as every UI window. The 1080 recordings
  hold the virtual 1280 x 720 view, where it is shrunk to 2/3 (ifH10: the icon ~11 px, blurred).
  So the reader works on 1:1 pixels:
  - offline on the 720 recordings;
  - at run time on a real-frame grab of the popup's place.
- **The truth:** every item that lands in the bag is a `pickup_result` packet (ok, item_id, amount,
  t_mono_ns), from a floor pickup, a Steal, or a GM `@item`. The frames' t_mono_ns is the same clock.
- **The icons:** slot_items.SlotRefs (the GRF's item pictures, cut locally, never committed) are
  what the bag count matches. Over the popup's white they compare as over the bag's empty slot.

## 2. The reader (scripts/item_popup.py, pure)

1. The box: bare_steal.popup_box (presence, width), its place set per client size. A NEW popup:
   the box appears, or its contents change (bare_steal's POPUP_CHANGE / width rule).
2. **Which item:** the icon square at a fixed offset in the box (calibrated, section 4) against
   SlotRefs composited over the box's white. The nearest picture's ids, under a distance bar and a
   margin over the runner-up. A shared icon is a group; ambiguous or far means "unread".
3. **How many:** the LAST group of digit runs in the text. Glyphs are learned from popups with
   known amounts (packets) by hp_percent's run method; digits and shapes only, no word is read.
4. **The name shown:** the item's name by its id (the KB / the client's table).
   - Reading Thai text is not needed: the icon gives the exact id in any language.
   - An icon no picture explains is listed as "unknown item" with its count.

## 3. The check (scripts/item_popup_eval.py)

- A reader event at frame time t_f MATCHES a pickup_result at t when t <= t_f <= t + 3.0 s, its
  id is in the event's group and the amounts are equal. Each truth and each event matches at most
  once, in time order.
- Over a session set:
  - **I1** identification: events matched in time whose ids are right;
  - **I2** amount right;
  - **P** precision: events with no pickup_result in their window (false items);
  - **R** recall at 1 fps: truths with a matched event. 1 fps misses popups replaced within a
    second; R is reported by the gap to the previous truth.

## 4. The split and the bars (scored ONCE)

- **Calibration** (the icon offset, the distance bar and margin, the digit glyphs, the box's
  place): the 720 recordings `*-rdp-hunt-xmas02-fiT1` .. `fiT20`, by their number.
- **Score:** every other fiT session on the NAS (fiT21 .. ), once, by a scorer committed before
  it runs.
- **Bars:**
  - I1 >= 97 % (unread counts against);
  - I2 >= 97 %;
  - P: false events <= 2 % of events;
  - R: >= 85 % of truths whose previous truth is >= 2 s before.
- **Then, at 1080 on dev:** the run-time version (a real-frame grab of the popup's place) on dev
  runs, against their packets, with the same four lines. That check is pre-registered as an
  amendment before it runs.

## 5. What it feeds (after the bars pass)

- Each Run's item list: (id, name, count, by: pickup / steal), into the screen record of the Run
  (econ_screen), so /economy shows income at NPC prices.
- An item with no NPC price shows blank, for the person to type. Update saves it on the server
  (the Settings store, behind the write gate, audited), for every device and visit.

## 6. Not in this round

- The bag count for Batt's 7 x 9 window (next, his order).
- Reading Thai item names (OCR): not needed while every icon is known.

## 7. Where it runs

- Offline: CPU, niced, the NAS recordings read-only, scratch in /dev/shm. Beside 5b's chain on dev
  (no GPU, no input).

## 8. RESULTS and AMENDMENTS (clock-labelled)

### Amendment 1 (2026-11-21 21:32 ICT from `date`, BEFORE the score): the calibration, the count method

- **The calibration** (fiT1-fiT20, `item_popup_eval.py calibrate`): 1,071 popups of a known item
  (the first frame with the box <= 3 s after each pickup_result).
  - The box's left edge: 541 on 1,067, 542 on 4.
  - The icon square at (12, 4) from (left, POPUP_TOP): the true picture was the nearest of the
    occurring items' on 1,069 / 1,071.
  - Its distance p50 7.4 / p95 8.9 (one outlier at 125.7). The nearest WRONG picture of all 2,381
    is >= 29.0 further at p05 (p50 35.4).
  - => ICON_MAX 15.0, ICON_MARGIN 10.0.
- **The count:**
  - The text's TAIL is the run suffix that popups of different amounts share. A digit differs
    between amounts, so it never joins the tail; on the lab client the tail is the 9 runs of
    "obtained.".
  - The count group is the runs just left of the tail, <= 3 blank columns apart. Each run is named
    by a digit learned from popups whose amount the packets give.
  - On fiT1-fiT8 (417 popups: 414 x 1, 3 x 10) only "0" and "1" were seen. Any other digit reads
    as unread, never guessed; natural drops and Steals give 1.
  - On the other half of those boxes, 200 / 206 one-piece popups read 1, 6 read unread; the 10
    read 10.
  - The font is saved in the lab's data/ (client pixels, never committed).
- **The scorer** pools the raw counts of every session (not per-session rates). The bars are
  unchanged.

### RESULT (2026-11-21 23:03 ICT from `date`): the one score -- I1 and R PASS, I2 and P FAIL: the reader is NOT used yet

`item_popup_eval.py score` on every fiT session outside fiT1-fiT20 (45 sessions, ca92dbf7, the
count font of Amendment 1), pooled counts:

| line | got | bar | |
|---|---|---|---|
| I1 the right item | 2,510 / 2,552 = **98.4 %** (39 unread) | >= 97 % | PASS |
| I2 the right amount | 2,446 / 2,552 = **95.8 %** (96 unread) | >= 97 % | **FAIL** |
| P false events | 202 / 2,754 = **7.3 %** | <= 2 % | **FAIL** |
| R recall (spaced truths) | 2,515 / 2,581 = **97.4 %** | >= 85 % | PASS |

- 2,620 truths (pickup_result). The worst sessions for P: fiT56 18.5 %, fiT55 15.1 %, fiT49 14.5 %.
- **The cause of P (read after the score, fiT56):** of its extra events, 5 were the SAME item
  <= 6 s after the previous event and 2 came 3-8 s after a pickup. They are the same popup counted
  again: is_new's coarse ink test fires on a change over a box that never left the screen (a
  cursor or a damage number over it).
- **Not used:** no item list reaches live from this round.
- **Round 2 (pre-registered here, before any change):**
  - A NEW popup needs the box to have LEFT the screen since the last event, or a different item or
    width. An item gained twice in a row while the box stays up is then one event, so the
    recall of such repeats is reported apart.
  - The amount: the 96 unread are diagnosed (unseen digits, the tail cut by a long name, a cover)
    on the calibration sessions only. Any new digit glyphs come from those sessions too.
  - **A NEW held-out**, since every fiT session is used: the other 720 recordings with packets on
    the NAS (rdp-xmas02-xw*, -fs*, -fsTn*, rdp-rogue-*, rdp-thief-*), scored once, with the same
    four bars.

### Amendment 2 (2026-11-22 04:19 ICT from `date`, BEFORE the round-2 held-out is read): round 2's reader, its font, its held-out

- **The unread amounts, diagnosed on the calibration sessions only** (fiT1-fiT8's 417 boxes, round
  1's font: 13 unread, every one "- 1 obtained."):
  - **12: the box's own right border.** Over a dark scene the border is dark enough to read as a
    last "letter", so the text did not end with the tail. The code already drops the crop's last 4
    columns as the border (`text_runs`), but round 1 padded every crop to 260 px of white, so that
    cut hit the pad, not the border. The same pad also cut any name longer than 260 px.
  - **1: a cover over the box's top or bottom edge** made the box narrower than its text, so the
    final "." fell in the border cut.
- **The changes** (scripts/item_popup.py, item_popup_eval.py; tests in test_item_popup.py):
  - `text_box`: the count reads the box's OWN columns (left .. right), no pad. With it, 416 of
    those 417 read; the 13th needs a later frame (next rule).
  - **One event per popup SHOWN** (`Tracker`, `same_popup`), the round-2 rule of the RESULT:
    - an event opens when a box appears after none, and closes when the box leaves (a frame with
      no box) or another popup replaces it;
    - another popup = both frames' icons read and share no id, OR another width where BOTH widths
      are true ones (each frame read its text's tail, so a cover's short width never counts);
    - while the same popup stays, an unread item or amount is read again on its later frames; the
      first read wins (`filled` says which);
    - the event's time is its first frame's.
  - **Repeats are reported apart:** a truth whose previous truth is the same item <= 6.0 s before
    (`REPEAT_S`). While the box stays up, such a pickup is the same event, so it is missed.
- **The count font, learned again** on all 20 calibration sessions (`learn-count`, fiT1-fiT20,
  text_box crops): 1,071 popups (amounts 1 x 1,063, 10 x 6, 2 x 2), tail 9 runs, digits 0, 1, 2.
  It reads its own 1,071 right. Saved as data/ui_anchors/item_popup_count_r2.npz (sha256
  ade6a384...; client pixels, never committed).
- **The calibration sessions under round 2's reader** (a development check, not a score):
  1,075 truths, 1,056 events: I1 99.05 %, I2 100 %, P 0.19 % (2 events), R 98.1 %; repeats 24,
  found 8.
- **The held-out (set `r2`), fixed now:** every NAS session matching
  `-rdp-(xmas02-(xw|fs)[\w-]*|rogue-[\w-]+|thief-[\w-]+)$` with a packets file and at least one
  frame shard, 77 sessions: rogue 44, xmas02 fs* 17 (fsTa / fsTn / fsH and the ABORTED ones
  included), thief 10, xmas02 xw* 6. The list is `r2-sessions.txt` (scratch, sha256 35f0935f...).
- **Scored ONCE**, the same four bars, at this commit:

      item_popup_eval.py score --set r2 --refs data/slot_items/refs.npz \
          --count data/ui_anchors/item_popup_count_r2.npz --out <scratch>/score-r2.json

- The round-1 held-out (fiT21+) is not used to tune. It is run again AFTER the r2 score, reported
  only.

### RESULT round 2 (2026-11-22 05:59 ICT from `date`): the one score -- I2, P and R PASS; I1 FAILS (94.2 %): the reader is NOT used yet

`item_popup_eval.py score --set r2` at 935c777e (Amendment 2), 04:19-05:58, the 77 sessions of
set r2; `score-r2.json` sha256 5e2322a7...; pooled counts:

| line | got | bar | |
|---|---|---|---|
| I1 the right item | 1,503 / 1,595 = **94.2 %** (88 unread, 4 wrong) | >= 97 % | **FAIL** |
| I2 the right amount | 1,560 / 1,595 = 97.8 % (14 unread) | >= 97 % | PASS |
| P false events | 3 / 1,598 = 0.19 % | <= 2 % | PASS |
| R recall (spaced truths) | 1,546 / 1,629 = 94.9 % | >= 85 % | PASS |

- 1,692 truths. Repeats (the same item <= 6 s after the last): 70, found 12, as the one-event
  rule predicts.
- **Round 2 fixed what it aimed at:** false events 7.3 % -> 0.19 %, amounts 95.8 % -> 97.8 %.
- **Where I1 fails (read after the score):**

  | family | matched | right item | unread |
  |---|---|---|---|
  | thief-* (natural play) | 201 | 98.0 % | 0.5 % |
  | rogue-* (natural play) | 559 | 97.5 % | 2.3 % |
  | xmas02 fs* (item stagings) | 835 | 91.1 % | 8.9 % (74 of the 88) |
  | xmas02 xw* | 0 pickups | | |

  The unread items sit in the STAGINGS (staged piles picked up in quick runs). Their cause is not
  read yet (which ids, far or ambiguous, covered or not).
- **Not used:** no item list reaches live from this round. Set r2 is spent.
- **Next (round 3, pre-registered before any change):** diagnose the stagings' unread items on
  set r2 (now spent); any fix is scored on a NEW held-out (the 1080 runs' real-frame grabs on dev,
  section 4's run-time check, or new 720 recordings).

### Amendment 3 (2026-11-22 06:12 ICT from `date`): round 2's unread items read (diagnosis on the spent set r2; scores nothing)

- Two stagings (fs1, fsH1; `diag/diag_unread.py`, scratch): 16 unread events.
  - **12 are one item, 12001 "Level 3 Heal" (a magic scroll), read AMBIGUOUS.** Its own picture
    matches at 1.6-5.9, but every magic scroll has the same shape in another tint: the Cold Bolt
    scrolls' picture is 3.3 away, the Soul Strike scrolls' 4.3. The margin (10.0, calibrated on
    xmas_dun02's items) refuses that.
  - 4 are FAR (539, 529, 998, 530: their own pictures 34-84 away), not read further.
  - Of all 2,381 pictures, 39 pairs are closer than 3.0.
- Natural play (thief-*, rogue-*) read 97.5-98.0 % right. The FAIL comes from the stagings' staged
  items, scrolls above all.
- Round 3's candidates (not pre-registered yet): a colour-aware compare for pictures of one shape
  (the scrolls), or a group for pictures closer than the true-read spread; each scored on a NEW
  held-out.

### Amendment 4 (2026-11-22 07:35 ICT from `date`): Batt's decision on same-looking icons

- Batt, on the round-2 result: "That is fine: the pictures are the same, so they can count as the
  same kind of item. If the colour can tell them apart, OK: try the colour first. If not, count
  them as one kind, so we do not spend much time; it is a rough estimate anyway, and scrolls are
  not the main items we sell to the NPC."
- **Round 3, in this order** (its details pre-registered before it is built):
  1. Try a colour-aware compare for pictures of one shape (the magic scrolls first), measured on
     the spent set r2 and the calibration sessions.
  2. If the colour does not separate them reliably, pictures that look the same become ONE group
     (the reader says "one of these ids"), and the economy page prices the group as one kind.
- Time-boxed: a rough estimate is the use. Scored on a new held-out, the same four bars; a group
  read counts right when the true id is in it (the scorer's rule since round 1).


### Amendment 5 (2026-11-22 17:36 ICT from `date`, BEFORE round 3's held-out is read): round 3 pre-registered -- the colour, its numbers, its held-out

- **The diagnosis** (spent sets only: r2, the calibration fiT1-fiT20, round 1's fiT21+; scratch
  `popup-r3-diag/`, scores nothing). Every frame from 2 s before to 10 s after each pickup_result
  was cached (the box, a 28 x 28 icon patch, round 2's count read), and round 2's `Tracker` was
  replayed on the cache under each candidate rule. The cache is checked: today's rule gives
  `score-r2.json`'s counts on 77 / 77 sessions, and Amendment 2's development check on the
  calibration (I1 99.05 %). P is not measured (frames outside the windows are not seen).
  - **Pictures that look the same** under today's compare (mean |RGB| over a picture's own pixels):
    of the 2,381 pictures, 94 pairs are closer than the margin (10.0): 24 groups, 68 pictures,
    155 ids.
    - Only two of them occur in the three sets, and today every such read is "ambiguous": the
      Level 3 Heal picture (12001; 26 ids, with Sealed Scroll and Level 1 Teleport): r2 71,
      calib 2, fiT21+ 6; the Level 3 Cold Bolt picture (688; 6 ids, with Frost Diver and Storm
      Gust): calib 5, fiT21+ 7.
  - **The magic scrolls** share one shape (355 px). They differ only on a 5 x 6 seal at rows 3-8,
    columns 9-13: 20-25 pixels, by 54-84 levels (Heal orange, Cold Bolt bluish).
  - **The colour, by the pair lead** (`slot_items.SlotRefs.pair`, the hotbar reader's rule since
    2026-11-13): on the pixels where two pictures differ by more than 30, the read's lead of one
    over the other, (|o - q| - |o - p|) / |p - q| (1: it is p; -1: it is q).

    | picture | frames (events) | its lead over every rival scroll, min / p50 |
    |---|---|---|
    | 12001 Heal, r2 | 330 (70) | 0.855 / 0.97 (1 covered frame, 38.8 away, is "far" first) |
    | 12001 Heal, calib + fiT21+ | 40 (8) | 0.856 / 0.97 |
    | 688 Cold Bolt, calib + fiT21+ | 56 (12) | 0.829 / 0.834 |

    - The weakest rival is always the other scroll.
    - A whole-icon colour distance (chroma) is too thin: its margin is 0.59-0.61 on Cold Bolt and
      1.33-1.61 on Heal, so a bar of 1.0 leaves every Cold Bolt unread.
  - **Nothing right today breaks.** The lead is asked only when another picture is within the
    margin. Every other frame with such a rival (285 in the three sets) is covered (its nearest
    picture >= 32 away) and stays "far". Not one frame is turned wrong.
  - **A development check, not a score** (events, the scorer's match):

    | set | today | round 3 | change |
    |---|---|---|---|
    | r2 | 94.2 % (1,503 / 1,595) | 98.6 % (1,573) | +70 Heal, 0 new wrong, 0 right lost |
    | calib | 99.05 % (1,044 / 1,054) | 99.72 % (1,051) | +7 (5 Cold Bolt, 2 Heal) |
    | fiT21+ | 99.02 % (2,526 / 2,551) | 99.53 % (2,539) | +13 (7 Cold Bolt, 6 Heal) |

    - The counts are the same for any lead bar from 0.3 to 0.7. One group per set of close
      pictures gives the same counts too, but with a 50-id read for the scrolls.
    - Unchanged: r2's other 18 unread (with fsH1's 4 "far" items) and the wrong reads already
      there (r2 4, calib 1, fiT21+ 1).
- **=> The colour is used** (Amendment 4: "try the colour first"). Groups stay only where the
  colour has nothing to test:
  1. A read with no other picture within ICON_MARGIN (10.0) of the best is unchanged.
  2. Otherwise the close set is the best picture and every picture within ICON_MARGIN of it. Two of
     them TELL APART on the pixels where their pictures (composited over the box's white) differ
     by more than DIFF_PX = 30.
  3. The read names the member whose lead is >= PAIR_LEAD = 0.5 over every other member it differs
     from on at least DISCRIM_MIN = 6 pixels, at a distance <= ICON_MAX (15.0). Members with fewer
     than 6 such pixels are the same picture to the eye: their ids join the read (one group).
     Otherwise the read is "ambiguous".
  - The three numbers are slot_items' own (the hotbar reader, 2026-11-13), not tuned here. 0.5
    sits 0.33 under the least lead measured (0.829).
  - Still one group under this rule: 43 of the 94 close pairs (0-4 telling pixels), e.g. the 10
    arrow quivers, Silver and Platinum Coin, Plant Nutrient and Spicy Sauce, two FB hats. None
    occurs in any recording. The economy page prices such a read as one kind (Amendment 4).
- **The held-out (set `r3`), fixed now:** every NAS session matching

      -rdp-(stage-items-[bc]|stage-gef10-e3[bx]?|watch-w\d+|ow\d+|w\d+|fp\d+[a-z]?|s2-xmas_dun02-p\d+|sk-watch\d+|gb-gw\d+|flee-xmas02-sk|human-xmas02-batt\w+|hunt-xmas02-(p\d+|bs\d+|fiH\d+(-ABORTED)?)|xmas02-(x\d+|xp\d+|xmw\d+|sk\d+a))$

  with a packets file and at least one frame shard.
  - **41 sessions**, all 720 recordings (region 80,77,1280,720, PNG); none in r2 or fiT*, none read
    by rounds 1-2 of this reader. The list (names in name order, one per line, each ending in a
    newline) has sha256 **d2bf7aa0fb4c67d033a0e233bf462460cfe32e602b396ec00bf70c2a264cc2b7**
    (recomputed by the parent from the NAS listing, 17:3x). The code pins it: `--set r3` refuses
    when the matching list's sha256 differs, so a later recording cannot change the set.
  - Its stagings were used before by OTHER work only (the detectors, the minimap, the loot step);
    the popup reader never read them.
  - From the packets only (no frame read): 673 pickups of 29 items in 20 sessions. Stagings 246
    (stage-items-b/c, stage-gef10-e3/e3b), Batt's own play 152, natural play 275. The other 21
    sessions have no pickup and count for P only.
  - **It holds no magic scroll.** Only Darkgreen Dyestuffs (979, once) has a picture within the
    margin. So r3 tests that round 3's reader reads NEW recordings and breaks nothing; the
    scrolls' evidence is the measurement above (spent data). Their live check is section 4's
    1080 run-time check on dev, pre-registered by its own amendment. (The scrolls in the 1080 if*
    recordings cannot be read offline: those frames are a 2/3 shrink.)
  - Two amounts (a 7 and a 4) use digits the count font never learned: they read as unread
    amounts (2 of ~673 for I2). No new digit is learned this round.
- **Scored ONCE**, the same four bars (I1 >= 97 %, I2 >= 97 %, P <= 2 %, R >= 85 %). A read is
  right when the true id is in it. Run at the commit that builds this rule:

      item_popup_eval.py score --set r3 --refs data/slot_items/refs.npz \
          --count data/ui_anchors/item_popup_count_r2.npz --out <scratch>/score-r3.json

- **Reported beside (not bars):** I1 apart for the stagings, natural play and Batt's own session;
  the reads the lead made and the group reads, each with how many were right; after the score,
  sets r2, calib and fiT21+ again under round 3's reader (reported only).
- **The build** (the next commit, before the score): `item_popup.Icons.read` gains the close-set
  step (reusing slot_items' DIFF_PX / DISCRIM_MIN / PAIR_LEAD and its pair formula on the whole
  24 x 24 square: the popup has no count box over its icon); `ItemRead.why` says "lead" or "same";
  `item_popup_eval` gains set `r3` (the regex, the packets and shard rule, the sha256 pin);
  synthetic tests (one shape with a tinted 6-pixel seal: a lead >= 0.5 is named; fewer than 6
  telling pixels joins the ids; no rival inside the margin = unchanged).
- **If it passes:** section 4's 1080 run-time check on dev is pre-registered next (its own
  amendment); the reader feeds a Run's item list (section 5) only after that check.
  **If it fails:** a round 4, pre-registered from its diagnosis.

### RESULT round 3 (2026-11-22 19:25 ICT from `date`): the one score -- all four bars PASS; the reader feeds no Run yet (section 4's check first)

`item_popup_eval.py score --set r3` (scratch `popup-r3/score_r3.sh`), 41 sessions, the build's
inputs: the count font `item_popup_count_r2.npz` (sha256 ade6a384801e...) and slot_items' pictures
`refs.npz` (1bb96813ff49...).

1. **The development check first** (the spent calibration set, 17:41-18:28): 1,051 right ids
   (1,054 matched, I1 99.72 %), the diagnosis' 1,051 exactly; the lead read 7 times, 7 right. So
   r3 was read.
2. **The one score** (18:28-19:23); `score-r3.json` sha256 34756563...:

   | line | got | bar | |
   |---|---|---|---|
   | I1 the right item | 656 / 658 = **99.70 %** (1 unread, 1 wrong) | >= 97 % | **PASS** |
   | I2 the right amount | 656 / 658 = **99.70 %** (2 unread amounts) | >= 97 % | **PASS** |
   | P false events | 4 / 662 = **0.60 %** | <= 2 % | **PASS** |
   | R recall (spaced truths) | 651 / 665 = **97.9 %** | >= 85 % | **PASS** |

   - 673 truths, the packets' count in Amendment 5. Repeats (<= 6 s after the last of the same
     item): 12, found 2, as the one-event rule predicts.
- **The commit.** score_r3.sh checked that the worktree was at the build 0dcfd84f and clean at its
  start (17:41). At 17:53 a flow_play fix (28009d6e: the pause-time count and its test) was
  committed in the same worktree, so the r3 process (started 18:28) ran at HEAD 28009d6e.
  `git diff 0dcfd84f 28009d6e` changes only `scripts/flow_play.py` and
  `services/backend/tests/test_live_player.py`. The scorer never imports either (item_popup ->
  bare_steal, slot_items -> hotbar_count; ro_agent lazily). So the score ran the build's code byte
  for byte.
- **Reported beside (not bars):**
  - I1 by part: the stagings 246 / 246 = 100 %; natural play 269 / 270 = 99.6 %; Batt's own
    session (human-xmas02-batt1112b) 141 / 142 = 99.3 %.
  - The reads by why: "lead" 1, right 1; "same" (a group read) 0, none occurred; "far" 1, right 0
    (the one unread id); "ok" 656, right 655 (the one wrong id).
  - Where they sit, by session (counts only; no frame read):
    - hunt-xmas02-p38: the unread id, the one lead read and 1 false event;
    - batt1112b: the wrong id, 3 false events and 9 of the 14 missed spaced truths;
    - xmas02-x2 and hunt-xmas02-p39: one unread amount each. Amendment 5 predicted 2 unread
      amounts from the packets (a 7 and a 4 the font never learned); that these are the two was
      not checked frame by frame;
    - the other missed spaced truths: hunt-xmas02-fiH2 2, p39 1, fp1 1, fp2 1.
- **What it shows.** r3 holds no magic scroll (Amendment 5). So this pass shows that round 3's
  reader reads NEW 720 recordings and breaks nothing. The scrolls' own evidence is still the
  measurement on spent data (Amendment 5's table), and their live check is section 4's.
- **Not used yet.** As Amendment 5 says, section 4's 1080 run-time check on dev is pre-registered
  next (its own amendment), and the reader feeds a Run's item list (section 5) only after that
  check passes. Set r3 is spent.
- **After the score, reported only:** sets r2 and old (fiT21+) again under round 3's reader
  (`popup-r3/again_r3.sh`, started 19:25, refusing unless the scorer files equal 0dcfd84f's). The
  calibration set's run is item 1 above. Their counts go in a labelled note when they end.
