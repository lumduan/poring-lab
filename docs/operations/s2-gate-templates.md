---
doc_type: runbook
hypothesis: "The UI gate's readers (the four window anchors, talk@1's T2 dialog / menu reader, T3's menu glyphs) and the GM fixed-state check (the level lines, the two level-change notices), cut from banked S2 console-stream frames, pass the same bars on held-out S2 frames that their RDP cuts passed on RDP."
status: PROPOSED
role: null
verdict_date: null
verdict_ticket: null
supersedes: null
related: [../planning/labels-v2-plan.md, ../demonstrations.md, ../adr/0014-s2-primary-bot-path.md, ../adr/0009-console-session-capture.md, ../../packages/poring_env/src/poring_env/ui_sets.py, ../../scripts/ui_gate.py, ../../scripts/gm_state.py, ../../scripts/talk_calibrate.py]
next_action: "Built offline 2026-10-09 (branch feat/s2-gate-templates). NOT RUN. The parent runs the ONE S2 clean-room session below, with Batt at the console for the four NPC clicks. Until every needed component PASSES, the S2 path stays refused: no typed line, no gm_state check."
---

# The S2 template set for the UI gate and the GM fixed state (pre-registered 2026-10-09)

## Why

collect@1's preflight (labels-v2-plan 7.6a) found the blocker: the mandatory UI gate refused every
typed line on S2, because its templates were cut on RDP. S2 is the bot's primary path (ADR-0014).

The client's UI is the same on both paths, but its pixels are not: RDP progressive and the S2
stream's H.264 soften text and edges differently. So each template now exists once per path.

## What is built (offline, tested on synthetic frames; nothing cut yet)

**The lock picks the set** (`poring_env/ui_sets.py`):

| lock `BACKEND` | set | root |
|---|---|---|
| `rdp` | rdp | `data/ui_anchors/` (unchanged; no proof file) |
| `console` | s2 | `data/ui_anchors/s2/` (same sub-layout) |
| anything else (`hold`, malformed) | none | refused |

There is never a fallback from one path to the other.

**The s2 set is used ONLY when it is proven.** `data/ui_anchors/s2/proof.json` is written only by
the prove commands. For each component it holds:
- the verdict and the evidence (counts, never a frame);
- the sha256 of every file that component's readers load; `null` means the file was absent.

The reader refuses (fail closed) when:
- a component is missing or not passed;
- any file's bytes differ from the proof: a re-cut, an edit, a swap, or a file added later.

A PASS writes the component. Any other verdict REMOVES it, so a later failure never leaves an
older pass standing. Every prove is also appended to `proof-log.jsonl`.

| component | files (relative to the set root) | needed by |
|---|---|---|
| `windows` | `{status,skills,inventory,equipment}{,_mask}.npy` | the UI gate |
| `t2` | `npc_dialog/params.json` + the dialog / menu / button / arrow templates and masks | the UI gate |
| `t3` | `menu_glyphs.npz` + the t2 files | talk@1 only (it is RDP-only anyway: cursor_gate) |
| `gm_levels` | `gm_state/levels_1_1.npy` | `gm_state` check / restore |
| `gm_notices` | `gm_state/{badge,badge_mask,levelup_icon,levelup_mask}.npy` | `gm_state` notices step |

`python3 scripts/ui_gate.py status` prints the lock's path and each component's state. It is read
only.

**The bars (pre-registered here, before any S2 frame is cut):**

| component | prove command | PASS |
|---|---|---|
| `windows` | `ui_gate.py prove-windows-offline --path s2` | on every held-out frame: its own window's distance at home ≤ max_distance / 2 (3.0); every OTHER window's template ≥ 2 × max_distance (12.0); the home check AND the full-frame locate give exactly the labelled window, or none. Also ≥ 3 open frames per window and ≥ 6 with none open, from rounds the cut did not use. The RDP cut measured own 0.00, nearest other 16.6, nothing open ≥ 20.2 (`ui_anchors.WINDOWS`). |
| `t2` | `talk_calibrate.py prove-t2 --path s2` | the RDP bar unchanged: ≥ 50 packet-labelled frames, EVERY one agrees (dialog present / absent, NEXT / CLOSE / none, menu present / absent), ≥ 1 each of NEXT, CLOSE, menu and no window, from sessions the cut did not use. RDP: 168 / 168. |
| `t3` | `talk_calibrate.py prove-t3 --path s2` | the RDP bar unchanged: every labelled option row read EXACTLY (0 wrong, 0 refused), every option of every menu seen read at least once, the damaged copies never read wrong. RDP: 216 / 216. |
| `gm_levels` | `gm_state.py prove --path s2` | every "fixed" frame ≤ MATCH (4) strongly differing pixels; every "not fixed" ≥ 10. ≥ 4 held-out frames of each. |
| `gm_notices` | `gm_state.py prove --path s2` | `notices()` equals the label on every held-out frame. ≥ 3 frames showing both notices and ≥ 3 showing none. |

Labels come from what was done, never from the reader under test:
- windows: the chord pressed (`bank-windows`);
- T2 / T3: the packets (`talk_calibrate`'s labeller, as on RDP);
- the GM state: a person's reading of the client at bank time (the RDP `cut` standard).

A wrong label can only make a prove FAIL, never pass.

## The ONE live session

**Who:**
- the parent runs every command and READS every screenshot it takes;
- **Batt is needed at the console for about 15 minutes in phase A**, for four NPC clicks. The
  agent cannot click an NPC on S2, because cursor_gate has no S2 references, so the dialogs are
  opened by a person (`drive --attach`).

**Duration (estimate): about 70 minutes.**

| part | minutes |
|---|---|
| RDP prep | ~8 |
| entering the room | ~7 |
| phase A (no typed line) | ~20 |
| mid-session offline cut + prove of `windows` / `t2` / `t3` | ~12 |
| phase B (typed lines through the now-proven S2 gate) | ~12 |
| the offline GM-state cut + prove | ~3 |
| `cleanroom.py end` | ~5 |

Recommended watchdog limits: `--hard-cap-min 120`, `checks --box-min 90`.

**Setup.**
- Never during 09:30–10:15 or 14:00–14:45 ICT.
- Banks live in RAM; nothing here is disk-heavy.

        cd /home/batt/docker/poring-lab
        PY=.venv/bin/python
        export PYTHONDONTWRITEBYTECODE=1
        B=/dev/shm/poring-lab-tmp/s2-gate/$(TZ=Asia/Bangkok date +%Y%m%d-%H%M)
        mkdir -p "$B"

### 0. Before the room (RDP)

These typed lines go through the RDP gate, which is proven.

1. Pause training if it runs. It is one Windows session; train-day.sh also waits while the lock
   says console. Send SIGINT to the host-side `timeout ... poring_vision.train` by PID:

        ps -eo pid,args | grep 'timeout .*poring_vision.train --cache'

   Resume later with `RESUME=1`.
2. Check the starting conditions:
   - the GM is logged in;
   - ASSIST is on and the interlock is green;
   - the S2 foreground template is installed:

             $PY scripts/foreground_template.py status

     `client_title_active@stream.npy` must NOT say MISSING.
3. Put the GM in the fixed state, and clear the notices:

        $PY scripts/gm_state.py restore

4. Put the GM in prt_church, 3 cells from BOTH Garnet (103, 76) and Henson (103, 71). (100, 73) is
   walkable, and no other NPC is within 2 cells (checked offline on the GAT, 2026-10-09;
   `talk_calibrate.py stand --npc garnet|henson` prints each NPC's own stand cell).

        $PY scripts/ro_agent.py gm "@warp prt_church 100 73"
        $PY scripts/ui_gate.py check

   `check` must decide `clear`.

### 1. Enter the S2 clean room

These are the m4 / collect-v2 runbooks' steps.

    $PY scripts/cleanroom.py preflight
    $PY scripts/cleanroom.py start --hard-cap-min 120
    $PY scripts/cleanroom.py variant S2            # must end RELIABLE, left streaming
    $PY scripts/cleanroom.py checks --box-min 90
    scripts/runbooks/heartbeat.sh "$B/heartbeat.log" &      # stops on the first refusal

- Never run the room across a question to Batt. Ask before `start`; he is at the console for
  phase A.
- Check that the client is on the stream (no input):

        $PY scripts/collect_v2.py --check-client

- Check what the gate says now:

        $PY scripts/ui_gate.py status

  It must show `"path": "s2"` and `"gate_ready_on_s2": false`. Every typed line is refused from
  here until step 3: **do not type anything** (no `ro_agent.py gm` / `say`).

### 2. Phase A: no typed line, no click of ours on the world

1. **Judge the start.**

        $PY scripts/ro_agent.py shot s2gate-start

   READ the PNG it names. It must show:
   - no window open and no dialog;
   - the GM standing in prt_church;
   - Base Lv. 1 / Job Lv. 1;
   - no badge on the first shortcut icon, and no level-up icon.

   Anything else: stop here (`cleanroom.py end`) and fix it over RDP.
2. **The four windows, 4 rounds** (chords only: Alt+A / Alt+S / Alt+E / Alt+Q, each opened then
   closed by its own chord; the cursor parked on the right; ~30 s per round):

        $PY scripts/ui_gate.py bank-windows --out "$B/win" --scene prt_church --rounds 4

   Spot-check `$B/win/frames/` for each window's `-open-` frames, against `labels.json`. A window
   that was already open turns the labels round; the prove then FAILS, it never passes.
3. **The GM state at its start: fixed, no notices.** A person read Lv 1 / 1 on the step-1 shot.

        $PY scripts/gm_state.py bank --out "$B/gm" --levels fixed --notices none --scene prt_church --n 4

4. **NPC dialogs: four `drive --attach` sessions, Batt opens each.**
   - Each command waits, with no input, ≤ 180 s.
   - **Batt clicks the named NPC once** in the console, then moves the mouse away to the right
     edge and lets go. That is the only human input.
   - The drive starts once the dialog shows on two frames AND the ASSIST lease has ended. It then
     pages and chooses with keys only, as on RDP, banks frames after every step and collects the
     session's packets. T5 is n/a (the contact was a person's); T4 must still PASS.

   The cut set:

        $PY scripts/talk_calibrate.py drive --npc garnet --attach --first 1
        $PY scripts/talk_calibrate.py drive --npc henson --attach --first 1

   The proof set (fresh sessions, other choices):

        $PY scripts/talk_calibrate.py drive --npc garnet --attach --first 2
        $PY scripts/talk_calibrate.py drive --npc henson --attach --first 3

   - Each prints its session id (`…-demo-talk-cal-<npc>`), under `/dev/shm/poring-lab-demo/`. Note
     them as `CUT1 CUT2 PRV1 PRV2`.
   - A drive that ends `attach_no_dialog` / `attach_lease_active`: run it again.
   - A drive that ends `unreadable` / `no_effect`: Batt closes the dialog by hand, then run it
     again.
   - Before each new drive, the dialog must be gone. Judge a shot.

### 3. Mid-session, offline: cut and prove `windows`, `t2`, `t3`

Templates go to `data/ui_anchors/s2/` (client pixels, gitignored).

    $PY scripts/ui_gate.py cut-windows --path s2 --cut-rounds 0,1 "$B/win"
    $PY scripts/ui_gate.py prove-windows-offline --path s2 "$B/win"          # rounds 2-3; ~4 min
    D=/dev/shm/poring-lab-demo
    $PY scripts/talk_calibrate.py cut --path s2 "$D/$CUT1" "$D/$CUT2"         # READY?
    $PY scripts/talk_calibrate.py prove-t2 --path s2 "$D/$PRV1" "$D/$PRV2"
    $PY scripts/talk_calibrate.py prove-t3 --path s2 "$D/$PRV1" "$D/$PRV2"
    $PY scripts/ui_gate.py status            # gate_ready_on_s2: true ONLY if windows AND t2 PASS

- **Never `cut --force` for s2.**
- If `cut` is NOT READY, or `windows` / `t2` do not PASS, see "On a FAIL". Phase B cannot run
  then, because it types.

### 4. Phase B: typed GM lines, now through the PROVEN S2 gate

Every `ro_agent.py gm` line passes `ui_gate.ensure_clear` on S2 first. Bank after each step.
`chord AltLeft KeyA` opens the status window, which clears the notices; `ui_gate.py clear` then
closes it by its own chord.

    $PY scripts/ui_gate.py check                                   # must decide clear on S2
    $PY scripts/ro_agent.py gm "@baselevelup 1"                    # Lv 2: both notices appear
    $PY scripts/ro_agent.py shot s2gate-lv2                        # READ: Base Lv. 2, badge + icon
    $PY scripts/gm_state.py bank --out "$B/gm" --levels not_fixed --notices badge,levelup_icon --scene prt_church
    $PY scripts/ro_agent.py chord AltLeft KeyA
    $PY scripts/ui_gate.py clear
    $PY scripts/gm_state.py bank --out "$B/gm" --levels not_fixed --notices none --scene prt_church
    $PY scripts/ro_agent.py gm "@baselevelup -1"                   # back to Lv 1: the notices again
    $PY scripts/ro_agent.py shot s2gate-lv1                        # READ: Base Lv. 1, badge + icon
    $PY scripts/gm_state.py bank --out "$B/gm" --levels fixed --notices badge,levelup_icon --scene prt_church
    $PY scripts/ro_agent.py chord AltLeft KeyA
    $PY scripts/ui_gate.py clear
    $PY scripts/gm_state.py bank --out "$B/gm" --levels fixed --notices none --scene prt_church
    $PY scripts/ro_agent.py gm "@warp prontera 154 190"            # a second scene (outdoor)
    $PY scripts/gm_state.py bank --out "$B/gm" --levels fixed --notices none --scene prontera
    $PY scripts/ui_gate.py bank-windows --out "$B/win-prt" --scene prontera --rounds 1

- Read every shot before the next bank. The labels are that reading; if the client shows anything
  else, stop.
- (154, 190) is the city guide's stand cell (`talk_calibrate.py stand --npc guide`: walkable, no
  NPC within 2 cells).
- Job Lv stays 1 throughout; Job EXP is not touched.

### 5. Offline: cut and prove the GM state; re-prove the windows on both scenes

Pick the cut frames from `$B/gm/labels.json`:
- **L** = the first `fixed` / `none` frame of phase A;
- **W** = the first `fixed` / `badge,levelup_icon` frame of step 4;
- **N** = the first `fixed` / `none` frame banked right after it. W and N show the same place and
  the same level, so the mask holds only the notices' own pixels.

        $PY scripts/gm_state.py cut --path s2 --png "$B/gm/frames/<L>"
        $PY scripts/gm_state.py cut-notices --path s2 --with "$B/gm/frames/<W>" --without "$B/gm/frames/<N>"
        $PY scripts/gm_state.py prove --path s2 "$B/gm"          # gm_levels and gm_notices, each on its bar
        $PY scripts/ui_gate.py prove-windows-offline --path s2 "$B/win" "$B/win-prt"   # indoor + outdoor
        $PY scripts/ui_gate.py status

- The second windows prove replaces the first with the stronger evidence (both scenes). A FAIL
  there REMOVES the windows component: the gate closes again on S2. That is intended. Report it.
- Then:
  - `cleanroom.py end`;
  - stop the heartbeat loop;
  - resume training (`RESUME=1`).

## On a FAIL (any component)

- **Nothing is installed.** The component is absent from `proof.json`, or removed from it. The S2
  gate keeps refusing every typed line, and gm_state keeps refusing on S2. That is the designed
  outcome, not a fault.
- **Never in the session:**
  - change a bar or a threshold (`OWN_SHARE`, `OTHER_FACTOR`, `MATCH`, `NOT_FIXED_MIN`,
    `npc_dialog.Params`, `COLOUR_TOL`). A change is a code change with its own review and a new
    pre-registration;
  - `cut --force`;
  - hand-edit `proof.json`.
- **Do:**
  - keep the banks (`$B`, `/dev/shm/poring-lab-demo/…`): they are RAM, so copy them to
    `data/s2-gate/` (gitignored) before a reboot if they are wanted;
  - report the prove's JSON (`fails` / `disagree` / `wrong`, `own_max` / `other_min`);
  - judge the failing frames by eye;
  - end the room cleanly.
- **A wrong label** (a window that was already open, a person's misread): re-bank that part after a
  judged shot, then cut and prove again. Re-banking is allowed; changing a bar is not.
- **T2 NOT READY** or disagreeing: the likely cause is the H.264 colours against
  `npc_dialog.COLOUR_TOL` (16), or the window masks. The RDP fit cannot be assumed on S2. Report
  it; do not tune live.

## What only the live session can tell (the risks)

- **The H.264 stream's colours and edges.**
  - `npc_dialog`'s flat colours (PLAIN / HIGHLIGHT / TRACK ± 16) and the T3 ink map were measured
    on RDP.
  - The windows' title text is 60 × 13 px; the stable masks drop the pixels that move > 4 grey
    levels between S2 frames, and `stable_share` in the cut's output shows how much is left.
  - The level digits are judged at DIFF_LEVEL 60.
- **The ASSIST lease after Batt's click.** The drive waits ≤ 30 s for `/health lease_active` to
  turn false.
- **The weight readout on S2 is not cut here.** `gm_state` records `null` for it on S2 (a record,
  not a gate); `weight_glyphs.npz` for s2 would be a separate cut.
- **Not covered, and still RDP-only:**
  - learn_skill1's templates;
  - cursor_gate's references, which block talk@1 and every world click on S2;
  - the minimap readers.
