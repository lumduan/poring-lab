---
doc_type: plan
status: ACTIVE
role: null
verdict_date: null
verdict_ticket: null
supersedes: null
related: [econ-bag-count.md, ../econ/economics.md, ../../scripts/bare_steal.py, ../../scripts/bag_count.py, ../../scripts/slot_items.py, ../../scripts/econ_screen.py]
next_action: "Build scripts/item_popup.py + item_popup_eval.py; calibrate on the 720 recordings fiT1-fiT20; score once on the rest; then the 1080 run-time check on dev against packets."
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
