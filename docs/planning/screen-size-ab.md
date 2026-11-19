---
doc_type: hypothesis
hypothesis: "On the lab's own client and rAthena, the bot plays xmas_dun02 at 1920x1080 fullscreen (through the virtual 1280x720 client) as well as at 1280x720 fullscreen: no more deaths, and kills/h and loot/h no lower beyond the per-run noise."
status: PROPOSED
role: null
verdict_date: null
verdict_ticket: null
supersedes: null
related: [fullscreen-client.md, live-blocks.md, teaching-prerun.md, ../../scripts/screen_ab.py, ../../scripts/stage10_ab.py, ../../scripts/stage2_ab.py]
next_action: "Pre-registered 2026-11-19 22:57 ICT, before any of its data. Run the 1080 block, switch the lab client and session to 1280x720 fullscreen, run the 720 block, then score; then fix what plays worse at 1080 (Batt 2026-11-19 ~22:5x: 'tune 1920x1080 to play as well as possible, like I play')."
---

# s11scr: the screen size, 1280x720 against 1920x1080 (pre-registered 2026-11-19 22:57 ICT)

## Why

- Batt 2026-11-19 ~22:4x: "test with the offline server at 1920x1080, like live, to see how the
  bot works, compared with before".
- Then ~22:5x: "make 1920x1080 play as well as possible, like I play myself".
- At 1920x1080 the bot plays through the virtual 1280x720 client (fullscreen-client.md section
  7):
  - the world is scaled 1.5 about the centre;
  - the panels are found by their shape;
  - the cursor's own pixels are pasted unscaled.
- So far only a 2-minute run has played at 1080 on the lab (2026-11-18 15:31). Batt's own client
  played longer runs on the Thai dev server, where no packets give the truth.
- This series measures, on the lab where packets give the truth, what changes at 1080 and how
  much. It is a characterisation, not a switch to adopt: its result says where to work next.

## The arms

- **A = 1280x720 fullscreen**:
  - `.env` SESSION_SIZE 1280x720, GAME_REGION 0,0,1280,720;
  - the lab client's OptionInfo.lua WIDTH/HEIGHT 1280 / 720, ISFULLSCREENMODE 1;
  - the lab's measured 720 layout (fullscreen-client.md section 5).
- **B = 1920x1080 fullscreen**:
  - SESSION_SIZE 1920x1080, GAME_REGION 0,0,1920,1080;
  - OptionInfo.lua 1920 / 1080, ISFULLSCREENMODE 1.
- **The same everything else:**
  - The same code: main at the series' start; the runner byte-pinned.
  - The same box: the ready-made functions box as it is, s10ab's B (xmas02sk; fly_first,
    fly_first_hp, fly_first_land ON), through `flow_play.py play`.
  - The same character: the lab's Rogue, not immune.
  - The same map (xmas_dun02, the MVP alive) and stage2_ab's setup before every run.
- `screen_ab.py run` refuses before any input unless the `.env` screen is the block's and the
  backend's frames are that size.

## The runs

- Two blocks of 3 runs of 20 min: B first (the lab is at 1080 tonight), then one switch, then A.
  - Each block is one `screen_ab.py` series, with its own label: `s11scr-1080`, `s11scr-720`.
  - The switch is made by hand, once: close the client; OptionInfo.lua; `.env` (with
    RO_SHORTCUT / SHELL_SHORTCUT); `recreate:desktop` + `recreate:backend`; `recover gm`.
- Valid run: rc 0 or 130, at least 16 min played (80 %) or a valid end (bag full, home), not
  short (stage10's rule).

## JUDGED (WORSE if a line fails, INCONCLUSIVE if none fails but one cannot be judged, else SAME)

1. Deaths: B <= A over the played runs. Non-strict: two zero blocks pass.
2. Kills/h: mean(B) - mean(A) >= -2 SE.
   - SE is the two blocks' standard error of the difference (Welch).
   - It needs at least 2 valid runs per block, else INCONCLUSIVE.
3. Loot/h: the same rule as kills/h.
4. Errors: no B run ends with a code error or refuses its start, unless an A run does the same.

The lines follow the bar lessons (ab-bar-design-lessons):
- deaths use <=, so 0 = 0 passes;
- -2 SE passes about 98 % of the time when nothing changed;
- with only 3 runs a block the SE is wide (per-run kills/h SD about 12-15 in s9ab / s10ab, so SE
  is about 11). A line can pass and still hide a real 10-15 % loss. So the REPORTED numbers below
  matter as much as the verdict.

## REPORTED only

- openers/h;
- the tick pace (median tick ms);
- the detect ms;
- Fly Wings/h by kind, and false boss Fly Wings/h by the packets' truth (stage9_ab's);
- the economy with steals (z/h);
- the model each run loaded;
- each block's mean +- SE;
- "before": s10ab's B runs (2026-11-17, the same box at the old window size, the code of then):
  r02B 129.5, r03B 133.0, r06B 145.9, r07B 114.7 kills/h (lab.sqlite).
- Batt's bar (batt-benchmark-knife-swap): 228.5 kills/h, 135,737 common z/h.

## Limits

- The blocks are not interleaved: one switch, so drift between blocks (the map's state, the MVP's
  clock) goes into the difference. The setup's warps alternate within each block as usual.
- 3 runs a block: see the SE above.

## Runs

(none yet)
