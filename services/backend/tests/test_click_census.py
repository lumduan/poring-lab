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
