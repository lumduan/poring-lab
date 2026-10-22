#!/usr/bin/env python3
"""THE AFTERCARE OF A HUMAN DEMO (Batt 2026-10-22, decision 8: "Every human demo ends with the
character taken out of a dangerous map at once (safe stand, @heal), then judged"). After his
orcsdun01 demo the Crusader stood idle among orcs for 12 minutes, hit, with no one playing.

human_demo.py never sends input (tested), so this is its OWN step, run the moment the recorder
returns (its quiet period over: he has stopped). It warps the demo's character to its safe STAND
(always: no map name is read from pixels, and the stand is safe), waits until the client draws the
character again, sends @heal, closes the chat, and saves a frame for the parent to JUDGE.

    demo_aftercare.py run [human_demo arm args ...]   arm the recorder, then the aftercare
    demo_aftercare.py rescue SID                      the aftercare alone (the session's character)

Every GM line goes through the character's own guarded path: crusader.gm_line (the name + job
check) for the Crusader, ro_agent.gm (the Novice GM must be online) for the GM.
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

ROOT = Path(__file__).resolve().parents[1]
STANDS = {"crusader": ("prt_fild08", 268, 107), "gm": ("prt_fild08", 194, 199)}
DRAWN_WAIT_S = 25.0  # a dungeon -> field warp: the map loads (black) for a few seconds


def character_of(manifest: dict[str, Any]) -> str:
    """PURE: the demo's character (human_demo.py --character; older sessions are the GM's)."""
    c = str(manifest.get("character") or "gm")
    if c not in STANDS:
        raise ValueError(f"no safe stand for character {c!r}")
    return c


def rescue(character: str, label: str = "demo-aftercare") -> dict[str, Any]:
    import bench
    import crusader as cr
    import ro_agent as r
    import ui_gate

    stand = STANDS[character]
    out: dict[str, Any] = {"character": character, "stand": list(stand), "t_ns": r.ns()}
    with r.session(f"rule:{label}") as (agent, screen):
        agent.wait_for_human()

        def line(cmd: str) -> None:
            if character == "crusader":
                cr.gm_line(agent, screen, cmd, "crusader")
            else:
                r.gm(agent, screen, cmd)

        def drawn() -> bool:
            if r.black(screen):
                return False
            return character != "crusader" or bool(cr.check(screen, "crusader")["ok"])

        ui_gate.ensure_clear(agent, screen, why=f"{label}:start")
        line(f"@warp {stand[0]} {stand[1]} {stand[2]}")
        end = time.monotonic() + DRAWN_WAIT_S
        time.sleep(2.0)
        while not drawn():
            if time.monotonic() > end:
                out["shot"] = r.to_png(screen.full(), r.SHOTS / f"{label}-not-drawn.png")
                raise r.Stop(f"{label}: not drawn {DRAWN_WAIT_S:.0f} s after the @warp")
            time.sleep(0.5)
        time.sleep(1.0)
        line("@heal")
        time.sleep(1.0)
        bench.close_chat(agent, screen)
        out["shot"] = str(r.to_png(screen.full(), r.SHOTS / f"{label}.png"))
    out["note"] = "JUDGE the frame: the stand, HP / SP full, no dialog, the layout"
    return out


def manifest_of(sid: str) -> dict[str, Any]:
    for d in (Path("/dev/shm/poring-lab-demo") / sid, Path("/mnt/poring-lab-datasets") / sid):
        if (d / "manifest.json").exists():
            return json.loads((d / "manifest.json").read_text())  # type: ignore[no-any-return]
    raise SystemExit(f"no manifest for {sid}")


def main() -> int:
    if len(sys.argv) < 2 or sys.argv[1] not in ("run", "rescue"):
        print(__doc__)
        return 2
    if sys.argv[1] == "rescue":
        man = manifest_of(sys.argv[2])
        print(json.dumps(rescue(character_of(man)), default=str), flush=True)
        return 0
    cmd = [sys.executable, str(ROOT / "scripts" / "human_demo.py"), "arm", *sys.argv[2:]]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, text=True)
    sid = None
    assert proc.stdout is not None
    for ln in proc.stdout:
        print(ln, end="", flush=True)
        if sid is None and ln.startswith("{"):
            sid = json.loads(ln).get("session")
    rc = proc.wait()
    if sid is None:
        print(json.dumps({"aftercare": "skipped: the recorder named no session", "rc": rc}))
        return rc or 1
    # the recorder returned: its quiet period is over (or it refused / failed after arming) --
    # either way the character may stand in a dangerous map with no one playing: rescue it now
    print(json.dumps({"aftercare": rescue(character_of(manifest_of(sid))), "recorder_rc": rc},
                     default=str), flush=True)  # fmt: skip
    return rc


if __name__ == "__main__":
    sys.exit(main())
