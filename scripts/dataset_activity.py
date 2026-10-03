#!/usr/bin/env python3
"""Scene activity while record_session.py records (Phase 2 datasets, 2026-10-03): the GM walks,
Porings appear, the camera stays at its default so EVERY frame is auto-labelable.

    dataset_activity.py --scene outdoor|indoor --seconds 1200 [--spawn-every 120] [--seed N]

- Start: a camera reset (a map change, as the benchmark's enter_scene) at the scene's spot.
- Every 4-9 s: a walk click 2-6 cells across and 2-4 up/down from the character (seeded, paced
  like a person), and back towards the spot when it drifts more than 12 cells away (a warp back
  on the same map keeps the camera).
- Every --spawn-every s: GM `@monster poring 3` (labels for the monster class).
- End (and on Ctrl-C/SIGTERM): `@killmonster2`, so no spawn outlives the recording.
- No camera rotation or zoom: those make frames `camera_dirty` until the next map change, and these
  sessions exist for the default-camera auto-labels.

Input only through /internal/agent in ASSIST, the GM online (ro_agent's rules). It prints a JSON
summary (counts only).
"""

import argparse
import json
import random
import signal
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import bench  # noqa: E402
import ro_agent as r  # noqa: E402


def safe_gm(agent: "r.Agent", screen: "r.Screen", command: str, counts: dict[str, int]) -> bool:
    """A GM line, retried once when the chat input simply did not open (a frozen stream frame
    after a dropped packet, 2026-10-04 05:58). If the input is left OPEN (a stale half-line in it),
    GM commands stop for the rest of the run: never send a line that was not this one."""
    for attempt in (1, 2):
        try:
            r.gm(agent, screen, command)
            bench.close_chat(agent, screen)
            return True
        except r.Stop as exc:
            counts["gm_failures"] += 1
            r.log(f"activity: {command!r} failed ({exc}); attempt {attempt}")
            if r.is_state(screen, "chat_open"):
                counts["gm_disabled"] = 1
                return False
            time.sleep(3)
    return False


CELL_PX = 33  # ~px per cell at the default camera (camera_rdp.json fit: distance 400, FOV 15)
DRIFT_CELLS = 12


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--scene", choices=sorted(bench.SCENES), required=True)
    ap.add_argument("--seconds", type=float, required=True)
    ap.add_argument("--spawn-every", type=float, default=120.0)
    ap.add_argument("--seed", type=int, default=20261003)
    a = ap.parse_args()
    rng = random.Random(a.seed)
    stop = {"flag": False}
    signal.signal(signal.SIGTERM, lambda *_: stop.update(flag=True))
    counts = {"walks": 0, "spawns": 0, "returns": 0, "gm_failures": 0, "gm_disabled": 0}
    mapname, sx, sy = bench.SCENES[a.scene]
    gx, gy, gw, gh = r.game_region()
    cx, cy = gx + gw // 2, gy + int(gh * 0.53)  # the character's feet (measure_delay's centre)
    drift = [0, 0]  # cells away from the spot, by our own clicks (approximate)
    with r.session("dataset-activity") as (agent, screen):
        bench.enter_scene(agent, screen, a.scene)
        t_end = time.monotonic() + a.seconds
        next_spawn = time.monotonic() + 10
        try:
            while time.monotonic() < t_end and not stop["flag"]:
                if time.monotonic() >= next_spawn and not counts["gm_disabled"]:
                    if safe_gm(agent, screen, "@monster poring 3", counts):
                        counts["spawns"] += 1
                    next_spawn += a.spawn_every
                if (abs(drift[0]) > DRIFT_CELLS or abs(drift[1]) > DRIFT_CELLS) and not counts[
                    "gm_disabled"
                ]:
                    # same map: the camera stays
                    if safe_gm(agent, screen, f"@warp {mapname} {sx} {sy}", counts):
                        counts["returns"] += 1
                    drift = [0, 0]
                    time.sleep(3)
                    continue
                dx = rng.choice([-1, 1]) * rng.randint(2, 6)
                # vertical steps <= 4 cells: the click stays in y 250..514 of the client, clear of
                # the chat window (y >= 531) and the hotbar (y <= 131)
                dy = rng.choice([-1, 1]) * rng.randint(2, 4)
                r.activate_client(agent, screen)
                agent.click(cx + dx * CELL_PX, cy - dy * CELL_PX)
                drift[0] += dx
                drift[1] += dy
                counts["walks"] += 1
                agent.idle(rng.uniform(4.0, 9.0))
        finally:
            if not counts["gm_disabled"]:
                safe_gm(agent, screen, "@killmonster2", counts)  # the runner also does it after
    print(json.dumps({"scene": a.scene, "seconds": a.seconds, **counts}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
