#!/usr/bin/env python3
"""Demonstrate the client's window shortcuts, logged (docs/demonstrations.md; Batt 2026-10-07).

    demo_shortcuts.py [--chords AltLeft+KeyA,AltLeft+KeyS,...] [--label shortcuts]

For each chord, with the GM in game and the client in front:
1. snapshot;
2. the chord, paced (ro_agent CHORD_STEP_S; the foreground gate applies to the key downs);
3. snapshot after; the CHANGED region (the largest box of pixels that differ by more than 40
   levels) is recorded;
4. the same chord again (most shortcuts toggle);
5. a third snapshot.

Each is one DemoRecord (actor claude-demo, type menu_shortcut, outcome pending). The demonstrator
LOOKS at the snapshots; the window anchors are cut from them afterwards. The alone-test
(open_window@1) is then judged by those anchors, not by this script's change box.

Never sent: Alt+F4 (quits), Alt+Enter (full screen), Alt+Tab / Alt+Space (Windows), Ctrl+V-style
pastes (the mux refuses them anyway).
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import record_session  # noqa: E402
import ro_agent as r  # noqa: E402
from rule_run import snap  # noqa: E402

from poring_env.demo import Action, DemoLog, DemoRecord, Intended, new_session_id  # noqa: E402

LETTERS = "ASEQVWZGHJRIOUMLTYPBKXCNDF"
DEFAULT = [f"AltLeft+Key{c}" for c in LETTERS] + ["Insert", "Escape", "F12"]
FORBIDDEN = {"AltLeft+F4", "AltLeft+Enter", "AltLeft+Tab", "AltLeft+Space", "ControlLeft+KeyV"}
SETTLE_S = 0.8


def change_box(a: np.ndarray, b: np.ndarray) -> tuple[list[int] | None, float]:
    """(x0, y0, x1, y1) of the pixels that changed by > 40 levels, trimmed to the densest rows and
    columns (>= 30 % changed), and the changed fraction of the client area."""
    d = np.abs(a[:, :, :3].astype(np.int16) - b[:, :, :3].astype(np.int16)).max(axis=2) > 40
    frac = float(d.mean())
    if frac < 0.002:
        return None, frac
    rows = np.flatnonzero(d.mean(axis=1) >= 0.3)
    cols = np.flatnonzero(d.mean(axis=0) >= 0.3)
    if not rows.size or not cols.size:
        ys, xs = np.nonzero(d)
        return [int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1], frac
    return [int(cols.min()), int(rows.min()), int(cols.max()) + 1, int(rows.max()) + 1], frac


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--chords", default=",".join(DEFAULT))
    ap.add_argument("--label", default="shortcuts")
    a = ap.parse_args()
    chords = [c.strip() for c in a.chords.split(",") if c.strip()]
    bad = [c for c in chords if c in FORBIDDEN]
    if bad:
        raise SystemExit(f"refused (never sent): {bad}")
    sid = new_session_id(a.label)
    log = DemoLog(sid)
    lock = record_session.read_lock(r.ROOT / "state")
    log.start(backend=str(lock.backend), lock_seq=lock.seq, server="lab-rathena", account="gm",
              purpose="window shortcut demonstrations")  # fmt: skip
    print(json.dumps({"session": sid, "dir": str(log.dir)}), flush=True)
    t_first = r.ns()
    region = r.game_region()
    with r.session("claude-demo-shortcuts") as (agent, screen):
        for i, chord in enumerate(chords):
            r.activate_client(agent, screen)
            keys = chord.split("+")
            before = screen.grab(*region)[1]
            pre = snap(log, screen, f"{i:02d}-{chord}-before")
            t0 = r.ns()
            agent.chord(*keys) if len(keys) > 1 else agent.keys(*keys)
            time.sleep(SETTLE_S)
            after = r.grab_after(screen, region, t0)
            post = snap(log, screen, f"{i:02d}-{chord}-after", after_ns=t0)
            box, frac = change_box(before, after)
            agent.chord(*keys) if len(keys) > 1 else agent.keys(*keys)
            time.sleep(SETTLE_S)
            closed = r.grab_after(screen, region, r.ns() - 1)
            snap(log, screen, f"{i:02d}-{chord}-toggled", after_ns=t0)
            box2, frac2 = change_box(before, closed)
            ev = {"change_box": box, "changed_frac": round(frac, 4),
                  "after_toggle_frac": round(frac2, 4)}  # fmt: skip
            log.append(DemoRecord(
                session=sid, actor="claude-demo", t_mono_ns=t0, t_done_ns=r.ns(), frame=pre,
                frame_after=post, scene="ingame", cue=f"chord {chord}, paced; window seen on the "
                "after snapshot", action=Action(type="menu_shortcut", keys=[chord],
                                                intended=Intended(kind="window", note=chord)),
                outcome={"status": "pending", "evidence": ev},  # type: ignore[arg-type]
            ))  # fmt: skip
            print(json.dumps({"i": i, "chord": chord, **ev}), flush=True)
    events, anchor = record_session.write_packets(log.dir, t_first, r.ns())
    log.finish(packet_events=len(events), chords=len(chords))
    return 0


if __name__ == "__main__":
    sys.exit(main())
