"""Every WORLD click passes the cursor gate (Batt, 2026-10-08, decision 6): where@2's blind harness
click attacked monsters and contacted NPCs. A script may call `.click(` directly only where this
census says why; any new direct click changes a count here and must either use
`scripts/cursor_gate.gated_click` or be added with its reason. Gated world clicks are registered
too (GATED: who calls the gate, how often, why)."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]

ALLOWED = {
    "scripts/cursor_gate.py": (1, "the gate itself: the click after two allowed cursor reads"),
    "scripts/ro_agent.py": (14, "UI only: the client's title bar, login / server / character "
                                "screens, console tabs, the chat input, the operator's click CLI"),
    "scripts/dataset_activity.py": (1, "UI: the death dialog's return button (world clicks gated)"),
    "scripts/survive.py": (1, "UI: the death dialog's return button, its known step (3.96 S6, "
                              "the Crusader's survival trials; no world click)"),
    "scripts/safety_signal_check.py": (11, "deliberate positive cases: sword / talk / pickup "
                                           "read twice by pixels; dialog buttons by screenshot; "
                                           "the cancel measurement's, rec@0's (3.19) and rec@0b's "
                                           "(3.22) deliberate unit click + verified walk click; "
                                           "loot P5's negative case (walk read twice)"),
    "scripts/loot1.py": (2, "loot@1 (3.20a): the kill phase's deliberate attack after two SWORD "
                            "reads; the loot click after two PICKUP reads + walk@11's unit gate"),
    "scripts/rule_run.py": (2, "walk@1-4 RULES (retired): their own marker / cursor gates"),
    "scripts/walk5.py": (1, "the walk@5 RULE's gated click"),
    "scripts/walk6.py": (1, "the walk@6 RULE's gated click (walk@7 reuses it)"),
    "scripts/walk8.py": (3, "walk@8 RULE: confirmed / unnamed-after-fix / portal clicks, gated"),
    "scripts/walk9.py": (3, "walk@9 RULE: the same three, gated"),
    "scripts/walk10.py": (3, "walk@10 RULE: the same three, gated (tier A / B)"),
    "scripts/walk11.py": (3, "walk@11 RULE: walk@10's three + the click-instant unit gate"),
    "scripts/idle_click.py": (1, "idle@1 (3.23): the deliberate walk click after two WALK reads, "
                                 "as walk@12 makes it; the signboard hit-area case"),
    "scripts/walk12.py": (3, "walk@12 RULE: walk@11's three, on work-zone points only, with the "
                             "TALK-cell block"),
    "scripts/talk1.py": (2, "talk@1 (3.30): UI clicks only -- LiveIo.click (NEXT, CLOSE, a menu "
                            "row, OK, Cancel, a scroll arrow; each inside a window T2 read on a "
                            "stable frame, refused outside it) and the dialog logic's call of it; "
                            "the contact click is cursor_gate's (TALK read twice)"),
    "scripts/talk_calibrate.py": (1, "talk@1 calibration: the `click` step, through talk1.LiveIo "
                                     "(a T2-read element); its contact click is cursor_gate's"),
    "scripts/learn_skill1.py": (1, "learn_skill@1 (3.34): UI clicks only -- LiveIo.ui_click, "
                                   "refused outside the box it names: Basic Skill's icon, APPLY, "
                                   "RESET (the skill window found at home), the confirm modal's "
                                   "OK / CANCEL (the modal read on stable frames); no world click"),
    "scripts/farm1.py": (2, "farm@1 (6.2, Batt's 'engage like a player' point 3): the attack "
                            "click after ONE robust2 SWORD read at the target's latest box, and "
                            "the re-click after another SWORD read; no walk click of its own"),
    "scripts/hunt.py": (2, "hunt@N (3.39): the attack / re-click after ONE robust2 SWORD read (as "
                           "farm@1; from hunt@6 only on boxes passing the selection's gates, near "
                           "the GM once it reached the target), and the CONTINUOUS walk click "
                           "while the GM moves, gated by the map (search-area stand cells) and "
                           "the detector (no unit within 60 px on the last 2 fresh frames): "
                           "3.39's recorded deviation (2), option B. A click from a standstill is "
                           "cursor-gated (GATED below)"),
    "scripts/hunt_flow.py": (9, "hunt-flow@N (3.41): the attack / re-click after ONE robust2 SWORD "
                                "read on the target's newest box, only at the stop with the target "
                                "<= 3 cells (as hunt@6's click); and the CONTINUOUS walk click "
                                "while the GM moves, gated by the map and the detector (no unit "
                                "within 60 px on the last 2 fresh frames): 3.39's deviation (2), "
                                "option B. A click from a standstill is cursor-gated (GATED). "
                                "hunt-flow@10+ (Batt 2026-10-16, demonstrations 3.51 / 3.52): the "
                                "RISK-BASED gate -- the attack click skips the SWORD read unless "
                                "the strict rule finds a risk (box overlap, near the GM, conf < "
                                "0.6, an NPC within 12 cells, a non-target species near); every "
                                "attack click logs its branch; hard bars: zero NPC contact, zero "
                                "non-target hit, zero map change. hunt-flow@12+ (Batt 2026-10-16 "
                                "19:4x): the BURST re-click on the freshest box until the client's "
                                "arrow, each one re-checked by the risk gate, bounded 4 / 3 s. "
                                "hunt-flow@17+ (Batt 20:3x): the LOOT click of the sweep -- the "
                                "cursor read PICKUP twice + walk@11's unit check (loot@1's rule), "
                                "one per sweep, <= 8 per kill. hunt-flow@21+ (Batt 2026-10-17): "
                                "the LOOT click on a frame-difference blob, by the same rule. "
                                "hunt-flow@23+ (Batt 2026-10-17, his FIXED loot workflow): the "
                                "loot burst on the death cell, then the 3 x 3 -- NO cursor read "
                                "(an empty cell only steps the GM); skipped near any monster or "
                                "NPC box (30 px), within 2 cells of an NPC, on NEW pink pixels, "
                                "on the UI or off the frame; <= 10 clicks / 4 s a kill. "
                                "hunt-flow@24+: FrameGuard's pass-through -- every hunt-flow click "
                                "goes through it and one OFF the game frame is refused (no click "
                                "of its own)"
                                " 3.90 (Batt 2026-10-20, staged): the HAND scan's loot click, "
                                "only where the client drew its PICKUP cursor at the hovered "
                                "point (cursor_sword pickup recall >= 0.90; a SWORD there is "
                                "never clicked). Batt's loot rule (2026-10-20, staged): the "
                                "scan around the drawn GM's loot click, only on a HAND read at "
                                "the hovered pixel, a fresh read before every burst click"),
    "scripts/agent_play.py": (3, "agent-demo@1 (Batt 2026-10-17, the agent's competition round): "
                                 "the attack click and its burst re-clicks, each only after the "
                                 "client's NAME TAG read a target under the pointer (hunt-flow@16 "
                                 "rule); the walk click while the GM walks, after the walk guard "
                                 "and a 40-px unit check (the bot's moving rule; from a standstill "
                                 "the cursor gate, GATED)"),
    "scripts/gm_state.py": (3, "UI only: an inventory TAB label inside the open window, after two "
                               "motions (clear_loot, Batt 2026-10-16: the GM test state's loot "
                               "rule); the loot leaves by agent.drag onto open ground + Enter on "
                               "the quantity prompt, matched to its OK button first. And STR's "
                               "'+' in the status window (rebuild_hunting, Batt 2026-10-18), after "
                               "two fresh frames show that window ALONE at its home; the '+' lies "
                               "inside it. And the storage window's own CLOSE button (store_loot, "
                               "Batt 2026-10-25: loot kept via @storage), only while its title "
                               "matched, after two motions"),
    "scripts/dungeon_hunt.py": (2, "dungeon@1 (Batt 2026-10-22, demonstrations 3.98, the "
                                   "Crusader on orcsdun01): ONE world-click path (click_at) "
                                   "through FrameGuard (off-frame refused) -- the DEFEND-SCAN "
                                   "strike and its burst only where cursor_sword read SWORD at "
                                   "the hovered point; the loot click only where it read the "
                                   "PICKUP hand; the walk click only where it read clear (WALK / "
                                   "PICKUP) on a zone-free route cell -- or, with --walk-trust "
                                   "(OFF by default, gef10-cursor-unknown.md), where the read "
                                   "stayed UNKNOWN on a cell walk_trust.trust_why trusts; "
                                   "Heal's target click on our own drawn body after F5; with "
                                   "--rest house (OFF by default, gef10-house-rest.md; the count "
                                   "is unchanged: both go through click_at) the door click on a "
                                   "SEALED house's door centre, from a standstill on one of its "
                                   "approach cells, where the read is neither SWORD nor the "
                                   "no-entry ring, and inside in_orcs01 the exit click on its "
                                   "own exit's centre (the indoor camera's point from the "
                                   "arrival cell), refused (STOP) on a SWORD or no-entry read. "
                                   "With --unread-step (OFF by default, dungeon@9.22, "
                                   "rogue-xmas02.md 4BI LF-4; the count is unchanged: it goes "
                                   "through click_at) the 2-cell step back before a pos_unread "
                                   "Fly Wing, at most 2 per stale span: a point relative to her "
                                   "sprite at the screen centre, opposite to her last own move, "
                                   "clicked only where cursor_sword read clear (WALK / PICKUP) "
                                   "with no no-entry ring (never a SWORD or an unknown read), and "
                                   "only when no no-enter / no-cross cell or script NPC lies "
                                   "within 12 cells of the held or the dead-reckoned cell. "
                                   "And the death dialog's known step (its second button), as "
                                   "survive.py"),
    "scripts/client_layout.py": (1, "UI only: the hunting layout's own controls (Batt 2026-10-19): "
                                    "Basic Info's arrow and a chat TAB, two motions, each step "
                                    "verified on pixels (the chat's message area is "
                                    "click-through: only these solid elements)"),
    "scripts/chat_window.py": (1, "UI only: the chat window's PADLOCK (Batt 2026-11-05: lock "
                                  "after docking), at the window found on pixels, two motions "
                                  "from the right (the '-' delete-tab icon is left of it); its "
                                  "drag presses the WHITE INPUT BAR only (solid UI) and both are "
                                  "verified on a fresh read; F10 is a key"),
}  # fmt: skip


# WORLD clicks made ONLY through the gate (`cursor_gate.gated_click(`): every script calling it,
# with how many calls and why (walk@17 item 5, 2026-10-09: a new gated world click is registered).
GATED = {
    "scripts/cursor_gate.py": (1, "the definition"),
    "scripts/calibrate_projection.py": (1, "projection calibration clicks, WALK read twice"),
    "scripts/camera_validate.py": (1, "camera validation clicks, WALK read twice"),
    "scripts/dataset_activity.py": (1, "the dataset activity driver's world clicks"),
    "scripts/measure_delay.py": (1, "the packet->frame benchmark's walk click"),
    "scripts/safety_signal_check.py": (1, "a walk to the plant's neighbour, WALK read twice"),
    "scripts/talk1.py": (1, "talk@1's ONE contact click: TALK read twice"),
    "scripts/talk_calibrate.py": (1, "the calibration drive's contact click: TALK read twice"),
    "scripts/where_run.py": (1, "where@'s harness walk clicks"),
    "scripts/npc_click_test.py": (1, "walk@17 item 5's targeted test: a deliberate click beside "
                                     "an NPC, ONLY where the cursor reads WALK twice (the walk "
                                     "rules' own gate); probes never click"),
    "scripts/farm0.py": (1, "farm@0 (6.1): the attack click, SWORD read twice"),
    "scripts/hunt.py": (1, "hunt@N's walk click from a standstill: WALK by robust2's series"),
    "scripts/agent_play.py": (2, "agent-demo@1: the walk click from a standstill (WALK by "
                                 "robust2's series) and the loot click (PICKUP read twice)"),
    "scripts/hunt_flow.py": (1, "hunt-flow@N's walk click from a standstill (search or steer): "
                                "WALK by robust2's series"),
    "scripts/regen_walk.py": (1, "crusader-regen@1 (3.96f): the W phase's walk click between two "
                                 "checked cells (WALK by robust2's series)"),
}  # fmt: skip


def test_gated_world_clicks_are_registered() -> None:
    files = subprocess.run(["git", "ls-files", "scripts/*.py"], cwd=ROOT, capture_output=True,
                           text=True, check=True).stdout.split()  # fmt: skip
    files += [f for f in GATED if f not in files]  # new, not yet committed
    found = {}
    for f in files:
        path = ROOT / f
        if path.exists():
            n = len(re.findall(r"gated_click\(", path.read_text()))
            if n:
                found[f] = n
    assert found == {f: n for f, (n, _) in GATED.items()}, found


def test_direct_clicks_are_only_where_the_census_says_why() -> None:
    files = subprocess.run(["git", "ls-files", "scripts/*.py"], cwd=ROOT, capture_output=True,
                           text=True, check=True).stdout.split()  # fmt: skip
    files += [f for f in ALLOWED if f not in files]  # new, not yet committed
    found = {}
    for f in files:
        path = ROOT / f
        if path.exists():
            n = len(re.findall(r"\.click\(", path.read_text()))
            if n:
                found[f] = n
    assert found == {f: n for f, (n, _) in ALLOWED.items()}, found
