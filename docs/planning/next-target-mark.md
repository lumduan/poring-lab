---
doc_type: hypothesis
hypothesis: "After a kill the bot loses time it need not: it starts looking for its next monster only then, walks past monsters and pauses to choose a way, while Batt has already marked the next one (and its heading) during the fight and walks to it at once. Measured first (this plan), then a 'mark the next target' built from the numbers."
status: PROPOSED
role: null
verdict_date: null
verdict_ticket: null
supersedes: null
related: [fists-1080.md, search-targets.md, ../../scripts/search_gap.py, ../../scripts/time_budget.py, ../../scripts/weapon_swap_study.py]
next_action: "Compute M1-M4 (section 2) on the live hour, the dev pilots and Batt's 11-12 run; then the design in an amendment from the numbers."
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
