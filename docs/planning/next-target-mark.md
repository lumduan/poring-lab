---
doc_type: hypothesis
hypothesis: "After a kill the bot loses time it need not: it starts looking for its next monster only then, walks past monsters and pauses to choose a way, while Batt has already marked the next one (and its heading) during the fight and walks to it at once. Measured first (this plan), then a 'mark the next target' built from the numbers."
status: PROPOSED
role: null
verdict_date: null
verdict_ticket: null
supersedes: null
related: [fists-1080.md, search-targets.md, ../../scripts/search_gap.py, ../../scripts/time_budget.py, ../../scripts/weapon_swap_study.py]
next_action: "Amendment 3 (Batt 2026-11-24 ~11:0x: start the mark on dev): the runner's own --queue is the mark's body (no player click exists); its 4CN failure was the re-find; diagnostic pilot ntq1 (fists + --queue, 25 min) measures today's re-find; then the player-side re-find (bq_next swap) with tests, and the A/B pre-registered before any A/B run."
title: "Mark the next target while fighting (Batt 2026-11-23): measure the after-kill time first (pre-registration)"
date: 2026-11-23
owner: Batt
---

# Mark the next target while fighting (written 2026-11-23 12:54 ICT from `date`, before any of its numbers)

## 0. What Batt said (2026-11-23 ~12:4x, translated)

"From watching the bot play on live: it still does not see monsters well enough, and it is not
smart enough to queue them. When it attacks the current one and other monsters are on the screen,
once the current one dies it walks off to look for a new target. When I play, I mark in my head
which one I hit next and plan my next walking zone from which one walks where -- sometimes they
walk past the screen's edge or another object hides them. After the kill, if no new one is nearer,
I walk to where the marked one is, find it and hit it at once; at least I know which way to walk to
meet a monster. Watch the recorded video: many times the bot walks past monsters or is slow to
decide where to go next. It can think in parallel while hitting the current one: kill > loot >
walk toward that zone, where the marked monster is. That would raise the kill rate. In a video of
me playing you would see it: I hardly stop walking after a kill."

## 1. The question

How much of the bot's hour is the time between a kill and its next attack, and how much of that
time had a monster ALREADY in view at the kill (the one Batt would have marked)? The same on
Batt's own run. The numbers decide whether a "mark" is worth building and what it must do.

## 2. The measures (fixed before any is computed)

**Sources:**
- **live:** the Run `flowplay-poring-lab-live-11231110` over the recording `live-fists-1`'s window
  (11:14:24-12:14:34; fists-1080.md Amendments 7-9): its events (hunt1, hunt2) and the recording's
  frames (the bot's virtual 1280 x 720 view, 1 fps). No packets on live.
- **dev bot:** ifH31-ifH36 (the Knife swap) and fst1-fst3 (the Damascus, no swap): packets and the
  runner's events.
- **Batt:** `20261112T214914-rdp-human-xmas02-batt1112b` (his 228.5 kills/h Knife-swap run on the
  lab): packets.

**M1, the after-kill time:** per kill, from the monster's death to our first attack on the NEXT
monster: packets (dev, Batt: the death, then our next attack_request on another gid); live: the
runner's kill event to its next engage. Reported: median, p75, the share >= 5 s, and its split
into loot, walking and standing (packets: our self_move; live: the walk / loot events).

**M2, a monster in view at the kill:** on the recorded frame nearest after each kill (<= 1.5 s),
the deployed monster detector (its ONNX on the CPU, the Run's own model and threshold) gives the
OTHER monsters in view: how many, and how far from her. Packets sessions also by packets (a mob
alive inside the 1280 x 720 view's cells at the death).

**M3, the mark Batt describes:** the share of kills with >= 1 other monster in view at the kill;
M1 for those kills against kills with none in view; packets sessions: whether the next monster
attacked was one IN VIEW at the kill (its gid), and if not, how long the one in view stayed alive
and reachable.

**M4, walked past (packets sessions):** during the after-kill time, the monsters whose cell came
within 5 cells of her path and were not attacked before the next attack.

Each is reported per source, never pooled across servers or builds. Live has no packets: its M1 and
M2 come from the runner's events and the detector, and are labelled so.

## 3. Then

An amendment from the numbers designs the mark: candidate -- during a fight, keep the other
monsters seen and their heading; after kill + loot, with none nearer, walk to the marked one's
predicted place and attack. Built on the player side (flow_play / the box's hunt loop), never in
the byte-pinned runner; an A/B on dev; live only on Batt's word.

## 4. Privacy

The live frames show other players: they stay on the NAS; only numbers enter this document
(CLAUDE.md rule 9; Batt 11-23: any NEW live capture is announced first and waits for his ready).

## Amendment 1 (2026-11-23 13:25 ICT from `date`): the numbers (M1-M4, section 2's sources, never pooled across them)

Computed offline by one agent (scratch `/dev/shm/poring-lab-tmp/ntm/`: its scripts and per-kill
rows; spot-checked: the medians recompute from the rows). Windows: Batt's demo by the lab's
`--live` rule (30.46 min, 116 kills = his 228.5 kills/h); dev by the runner's run windows (ifH31-36
148.2 min, 193 kills; fst1-3 74.1 min, 166 kills); live by the recording's frames (59.97 min, 136
kills from the exp line).

**M1, the after-kill time (death -> our first attack on the next monster; packets):**

| source | n | median | p75 | >= 5 s | split loot / walking / standing |
|---|---|---|---|---|---|
| Batt | 115 | **4.7 s** | 8.5 s | 47 % | 2 / **61** / 37 % |
| dev, Knife swap | 189 | **17.2 s** | 28.0 s | 95 % | 0.3 / 27 / **72** % |
| dev, Damascus no swap | 165 | **15.2 s** | 26.4 s | 97 % | 0.4 / 27 / **73** % |

- The after-kill time is 40.5 % of Batt's window and 45.8 % / 74.5 % of the dev windows.
- What the dev bot does in it (its own events over the packets' gaps, swap / no swap): waiting
  until the runner registers the death 13 / 12 % (~2.0 s after it: the hit-gap inference), defend
  scans 18 / 22 %, the target box's settle 14 / 16 %, strike 6 / 5 %, loot 2 / 2 %, other
  (its walking included) 48 / 43 %.
- Live, on the events ruler (kill event -> next engage): median 6.8 s, p75 13.6 s, >= 5 s 72 %
  (dev on the same ruler 2.2 / 3.1 s, its kill events come ~2 s late and include false ones: the
  ruler is rough across sites).

**M2, another target monster in view at the kill:** Batt 65.5 %, dev 59.6 / 68.1 % (packets: the
four common species alive, feet on the 1280 x 720 view); the detector on the recorded frame:
Batt 58.6 %, dev 61.1 / 66.9 %, **live 56.6 %** (the deployed xmas02v1080 on the CPU, boxes more
than 1 cell from her; it agrees with the packets' share within ~0.03 on dev, but misses 20-26 % of
in-view monsters one by one). The nearest is ~7 cells away (median) everywhere.

**M3, the mark Batt describes:**
- The after-kill time with >= 1 target in view vs none: Batt **3.5 vs 7.6 s**; dev 13.8 / 12.7 vs
  23.5 / 23.8 s; live (events) 6.0 vs 11.4 s. Every source is ~2x faster with one in view.
- With one in view, the next monster attacked WAS one of them: **Batt 81 %**, dev 67 / 63 %.
- In-view targets not attacked next: about half were still alive in reach at our next attack
  (median ~8 cells).

**M4, walked past (packets; within 5 cells during the after-kill time, not attacked before the
next attack):** per kill Batt 0.26, dev 0.54 / 0.61 (twice as many); per after-kill minute Batt
passes MORE (2.4 vs 1.5 / 1.8): he walks more, through denser ground. Live: not computable.

**Doubts (the agent's, kept):** 57 of live's 136 kill events came with no strike in the 10 s
before (many during search walks), each after a Battle Log damage or exp line -- the cause is not
known from events; live is his own server (its minimap never named the map); Batt's 11-12 camera
zoom is assumed default; "in view" by packets ignores UI windows.

**What the numbers say for the design** (Amendment 2 writes it): the bot does not lack targets --
2 in 3 kills already have the next one in view, as for Batt -- it STANDS: ~11 of its ~15-17 s,
in the death's late registration, defend scans and the next box's settle. Batt walks to the next
one he already chose (81 %). A mark that removes those standing steps on the kills with a target in
view is worth up to ~10 s on 2 kills in 3.

## Amendment 2 (2026-11-23 13:46 ICT from `date`): the design of the mark, from Amendment 1's numbers

**What it must remove** (the dev bot's ~15-17 s after a kill, 73 % standing; Batt 4.7 s, 61 %
walking): the late death (~2 s of hit-gap inference), the defend scans after it, the next box's
settle (waiting for it to stand still), and the search walk when a target was already in view (2
kills in 3).

**The behaviour (Batt's own, in his words: "kill > loot > walk toward the zone where the marked one
is"):**
1. **Mark during the fight.** Every tick of a fight already grabs a frame and runs the detector;
   the OTHER target boxes (not the one being struck) are kept as candidates: their cell (the box's
   feet, as Amendment 1's M2 maps them) and their heading (the cell change across the ticks that saw
   them, matched nearest-first). The mark is the nearest candidate that the walk can reach; it is
   kept up to date each tick and forgotten after MARK_TTL_S without a sighting.
2. **After the kill (and the loot, when a drop is there):** with a fresh mark and no nearer target
   in the new frame, the next goal is the mark's PREDICTED cell (its last cell + its heading x the
   time since), walked at once, with no defend scan and no settle on arrival: the box near the
   predicted cell is struck as soon as it is seen (the click led by its heading, the frames' ~0.5 s
   lag, [[frames-lag-server-half-second]]).
3. **Without a mark** (1 kill in 3): today's search, unchanged.
4. **Safety is not traded:** a survival event (a hit taken, HP low, the boss or an alarm species
   seen) pre-empts the mark exactly as it pre-empts today's search. The defend scan is skipped only
   when the frame shows no attacker and no damage was taken in the fight's last seconds.

**Where it lives:** on the player side only -- the box's hunt loop / the hunt core's tick hook
(live-blocks 5b-2 and 5c: the box may drive the hunt loop and read each tick), never the
byte-pinned runner file. Its settings (MARK_TTL_S, the reach) are player settings with our values
as defaults ([[feedback-everything-user-settable]]); off by default until its A/B passes.

**How it is judged (pre-registered in a later amendment, before any A/B run):** an interleaved A/B
on dev at 1080 (A today, B the mark; the same build and box), packets as the ruler: kills/h
(B >= A + 2 SE), deaths and errors no worse, and beside them M1-M4 on both arms (the after-kill
time, its standing share, the next target in view at the kill). Live only on Batt's word.

**Open, to measure while building:** the death's registration (dev's hit-gap ~2 s vs live's exp
line ~0.3 s): on dev the mark's walk can start at the last strike's death cue only if a faster
death cue exists; otherwise the mark saves the rest and the ~2 s stays.

## Amendment 3 (2026-11-24 11:19 ICT from `date`, before ntq1's data): where the mark can live, the queue's lesson, and a diagnostic pilot

- **Batt, 2026-11-24 ~11:0x:** "start the next-target mark on dev".
- **What the player side can do mid-hunt** (read from dungeon_hunt.py, never edited; a read-only
  trace with line numbers, checked by hand at the points used below):
  - no click and no goal API: the hook's `press` presses only the box's keys, `hook.call`'s click
    is the respawn's, HuntView is read-only, and `leave_out` takes only loot / ready / plant. A
    click of the player's own between cursor steps would bypass the runner's walk settle, its lock
    and its kill reads (a strike it does not know has no hit-gap kill and no loot entry);
  - the defend scan and box_target's settle run inside the fight step (closures of run()):
    not skippable from the player side;
  - **swappable** (module-level, looked up by name when called, the way flow_play already swaps
    `BoxWatch.near` and `alarm_seen` for one hunt core): `bq_next`, `bq_refind`, `bq_pick`,
    `bq_refresh`, `bq_mark`, `scan_needed`, `quiet_kill_ends`, `kill_gapped`, ...;
  - **`--queue` (dungeon@9.30, rogue-xmas02.md 4CC/4CN) is the mark's body already**: during a
    fight it keeps the OTHER monster boxes in view as a queue (attacking first, then nearest); after
    the fight and its loot step it re-finds the head on a fresh detection and strikes it with no
    settle, no still wait and no hold. On its picks the gap from the loot step's end to the strike
    was 2.58 s against 7.67 s. It stayed a flag because picks were rare: p77 16 picks / 48 re-find
    fails / 19 empty, p78 3 / 50 / 15 (the miss reason "gone": no box within QUEUE_MATCH_PX = 60 px
    of the entry's last foot).
- **Why its re-finds failed (offline, p77 + p78's packets and the runner's own detections; scratch
  ntm2/queue_*.py):** in 20 of the 98 misses she had moved >= 2 cells since the fight's end (the
  queue keeps screen pixels, which her own step shifts); in the other 78 she had not moved, 76 had a
  target monster alive within 9 cells, and 86 % of those monsters had not moved either. The runner's
  detection at the re-find held no monster box at all in 39 of the 98 misses. So mainly the
  re-find's single fresh detection missed monsters that were there, plus her own steps. Caveat:
  those runs had the camera at 1.14x zoom (reset 2026-11-20), the 720 window and the Knife swap,
  so the pixel-level comparison is not trusted to the number; hence the pilot below.
- **The mark's design, refined (Amendment 2's behaviour within what the player side can reach):**
  1. turn the runner's `--queue` on (an existing switch: `queue`, needs `box_strike`);
  2. swap its re-find (`bq_next`) for the mark's: each entry anchored to the WORLD (her cell at its
     detection + its rel cell), its foot predicted on the current view from her current cell
     (her step no longer loses it), the re-find matched there; when the fresh detection holds no
     box there, the predicted foot is HOVERED through the runner's own aim (a strike only on a
     SWORD cursor, the box path's skips first: unreachable, ignored spots, far); entries older than
     MARK_TTL_S are dropped. Settings with our values as defaults; off by default until its A/B.
  - Not reachable from the player side, so not in this mark: the dev kill's late registration
    (the hit gap, ~2-3 s; live reads the exp line at ~0.3 s) and the defend scan after a fight in
    which she was hit.
- **The diagnostic pilot ntq1, registered now (before any of its data):** fst4-fst6's procedure
  exactly (`fist_pilot_rec2.sh`: the fists build, town checks, 1 fps recorder, packets, 25 min, not
  immune), copied as `ntq_pilot_rec.sh` with ONE change: `--box-set queue=true` beside
  `knife_swap=false`. One run, not an A/B and no verdict. Reported:
  - the queue's events: picks / re-find fails / empty and the reasons;
  - per miss: her movement since the fight's end (packets), target monsters in view by packets
    against the detector's boxes at the re-find (the runner's detections.jsonl);
  - beside fst4-fst6 (the same build): kills/h and steals/h (packets), Amendment 1's M1 (the
    after-kill time) and its standing share; deaths, errors.
  - Checks as fst4-fst6: >= 1,400 frames, no PAUSED line, 0 weapon changes, else void.
