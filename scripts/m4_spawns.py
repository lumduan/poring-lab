#!/usr/bin/env python3
"""Phase 3 M4: the GM-spawn protocol that PROVES (or refutes) the sprite render rule
(docs/phase3-plan.md §5), driven while record_session.py records H.264.

    m4_spawns.py --out EVENTS.jsonl [--blocks outdoor-1 outdoor-2 indoor-1]
                 [--species poring lunatic] [--per-species 5] [--hold 40] [--background 5]
                 [--count 1]
    m4_spawns.py --check-client      rc 0 only if the RO client's title bar is on screen

--check-client runs BEFORE the recorder starts: no input, no screenshot, just the title bar's
signature distance (active <= 6, inactive ~30). On 2026-10-04 a console stream showed the Windows
sign-in screen (tscon never ran) and a minute of it was recorded before anyone saw it; it was
deleted, never shipped. Now nothing is recorded unless the client is what the stream shows.

Per block (a scene, entered via the other map: a camera reset):
  1. `@killmonster2`, then a --background clip with no monster (the reference for differencing);
  2. per species, --per-species times: `@monster <species> 1`, hold --hold seconds while it
     wanders and stands (rAthena: a random walk, then >= 4 s standing), `@killmonster2`, and
     another background gap.
--count N spawns N per command (`@monster <species> N`): Phase 3 M7's CROWD blocks (occlusion),
recorded under their own label; M4 itself is --count 1 (m4_validate measures single monsters).
The GM never clicks and never moves, so nothing is provoked; its vitals are still checked between
spawns (gm_vitals: @heal / @alive). `outdoor-1` and `outdoor-2` are the A/A pair: the same
condition measured on disjoint spawn sets.

Every step is a JSON line (t_mono_ns, wall time, block, scene, species, event) in --out, the
timeline that scripts/m4_validate.py splits the recording by. The truth of where each monster
stood comes from the session's packets, offline; nothing here reads packets (rule 1).
"""

from __future__ import annotations

import argparse
import json
import signal
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import bench  # noqa: E402
import dataset_activity as act  # noqa: E402
import gm_vitals as gv  # noqa: E402
import ro_agent as r  # noqa: E402

CLIENT_TITLE_MAX = 40.0  # client_title_active distance: active <= 6, inactive ~30 (2026-10-04)


def client_on_screen(screen: r.Screen) -> tuple[bool, float]:
    """Is the RO client's title bar where the game region says (active or not)? No input."""
    d = r.distance(screen, "client_title_active", after_ns=r.ns())
    return d <= CLIENT_TITLE_MAX, d


def check_client() -> int:
    screen = r.Screen()
    try:
        ok, d = client_on_screen(screen)
    finally:
        screen.close()
    print(json.dumps({"client_on_screen": ok, "title_distance": round(d, 1)}), flush=True)
    return 0 if ok else 1


def main() -> int:
    if "--check-client" in sys.argv[1:]:
        return check_client()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--blocks", nargs="+", default=["outdoor-1", "outdoor-2", "indoor-1"])
    ap.add_argument("--species", nargs="+", default=["poring", "lunatic"])
    ap.add_argument("--per-species", type=int, default=5)
    ap.add_argument("--count", type=int, default=1, choices=range(1, 21), metavar="1..20")
    ap.add_argument("--hold", type=float, default=40.0)
    ap.add_argument("--background", type=float, default=5.0)
    a = ap.parse_args()
    stop = {"flag": False}
    signal.signal(signal.SIGTERM, lambda *_: stop.update(flag=True))
    counts = {"gm_failures": 0, "gm_disabled": 0, "spawns": 0, "heals": 0, "revives": 0}
    gx, gy, gw, gh = r.game_region()

    with a.out.open("a") as log, r.session("m4-spawns") as (agent, screen):

        def note(block: str, scene: str, event: str, species: str | None = None) -> None:
            rec = {"t_mono_ns": r.ns(), "t_wall": time.strftime("%H:%M:%S"), "count": a.count,
                   "block": block,
                   "scene": scene, "species": species, "event": event}  # fmt: skip
            log.write(json.dumps(rec) + "\n")
            log.flush()

        def vitals(scene: str) -> None:
            dead = r.is_state(screen, gv.DEAD_STATE)
            frame = r.grab_after(screen, (gx, gy, gw, gh), r.ns())
            action = gv.vitals_action(gv.hp_fraction(frame), dead)
            if action == "heal" and act.safe_gm(agent, screen, "@heal", counts):
                counts["heals"] += 1
            elif action == "revive":
                act.safe_gm(agent, screen, "@alive", counts)
                act.safe_gm(agent, screen, "@heal", counts)
                counts["revives"] += 1
                bench.enter_scene(agent, screen, scene)

        r.minimize_consoles(agent, screen)
        try:
            for block in a.blocks:
                scene = block.split("-", 1)[0]
                if scene not in bench.SCENES:
                    raise SystemExit(f"{block}: the scene must be one of {sorted(bench.SCENES)}")
                bench.enter_scene(agent, screen, scene)
                note(block, scene, "scene_entered")
                act.safe_gm(agent, screen, "@killmonster2", counts)
                note(block, scene, "background_start")
                agent.idle(a.background)
                note(block, scene, "background_end")
                for species in a.species:
                    for _ in range(a.per_species):
                        if stop["flag"] or counts["gm_disabled"]:
                            raise KeyboardInterrupt
                        if act.safe_gm(agent, screen, f"@monster {species} {a.count}", counts):
                            counts["spawns"] += 1
                            note(block, scene, "spawned", species)
                        agent.idle(a.hold)
                        act.safe_gm(agent, screen, "@killmonster2", counts)
                        note(block, scene, "killed", species)
                        agent.idle(a.background)
                        note(block, scene, "background_end", species)
                        vitals(scene)
        except KeyboardInterrupt:
            r.log("m4: stopped")
        finally:
            if not counts["gm_disabled"]:
                act.safe_gm(agent, screen, "@killmonster2", counts)
    print(json.dumps({"blocks": a.blocks, "species": a.species, **counts}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
