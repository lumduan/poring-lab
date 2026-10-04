#!/usr/bin/env python3
"""Scene activity while record_session.py records (Phase 2 datasets, 2026-10-03): the GM walks,
Porings appear, the camera stays at its default so EVERY frame is auto-labelable.

    dataset_activity.py --scene outdoor|indoor --seconds 1200 [--spawn-every 120] [--seed N]
                        [--calibrate-cursor] [--hover-check auto|off]

- Start: a camera reset (a map change, as the benchmark's enter_scene) at the scene's spot.
- Every 4-9 s: a walk click 2-6 cells across and 2-4 up/down from the character (seeded, paced
  like a person), and back towards the spot when it drifts more than 12 cells away (a warp back
  on the same map keeps the camera).
- The click pixel comes from the MAP's projector (Post-S2 round B3): on an indoor map the client
  rotates the camera, so "3 cells north" is no longer straight up the screen.
- The target is an EMPTY walkable cell (B5, empty_cell.py): walkable in the map's GAT (client data,
  /dev/shm; required indoors), and -- with a calibrated walk-cursor template -- the cursor hovering
  there is the WALK cursor, not an NPC's or a monster's. --calibrate-cursor builds the template in
  the scene first (before any spawn); it is client-drawn pixels, kept under data/ (gitignored).
  The character's cell is tracked from its own clicks (approximate; the warp back resets it).
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
import empty_cell as ec  # noqa: E402
import ro_agent as r  # noqa: E402

from poring_dataset import camera as cm  # noqa: E402
from poring_dataset import gat as gatmod  # noqa: E402
from poring_dataset.projection import camera_file  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
CURSOR_DIR = ROOT / "data" / "bench" / "cursor"  # gitignored: client-drawn pixels
SETTLE_S = 0.35  # input -> a decoded frame showing it (p95 key->pixel 157-277 ms)
PARK_DX = 160  # px: where the cursor waits while the empty crop is grabbed


def safe_gm(agent: "r.Agent", screen: "r.Screen", command: str, counts: dict[str, int]) -> bool:
    """A GM line, retried once when the chat input simply did not open (a frozen stream frame
    after a dropped packet, 2026-10-04 05:58). If the input is left OPEN (a stale half-line in it),
    GM commands stop for the rest of the run: never send a line that was not this one."""
    for attempt in (1, 2):
        try:
            r.gm(agent, screen, command)
            bench.close_chat(agent, screen)
            return True
        except r.Unattested:
            raise  # ADR-0016: the interlock refused -- never a screen glitch to retry
        except r.Stop as exc:
            counts["gm_failures"] += 1
            r.log(f"activity: {command!r} failed ({exc}); attempt {attempt}")
            if r.is_state(screen, "chat_open"):
                counts["gm_disabled"] = 1
                return False
            time.sleep(3)
    return False


DRIFT_CELLS = 12


def hover_crop(agent: "r.Agent", screen: "r.Screen", x: int, y: int) -> "ec.Img":
    """The cursor crop at screen (x, y), from a frame decoded SETTLE_S after the move."""
    agent.move(x, y)
    t = r.ns()
    time.sleep(SETTLE_S)
    return r.grab_after(screen, ec.crop_region(x, y), t + int(SETTLE_S * 1e9))


def calibrate_cursor(
    agent: "r.Agent", screen: "r.Screen", rng: random.Random, pos: tuple[int, int],
    walkable: "object", projector: "cm.Projector", origin: tuple[int, int], samples: int = 8,
) -> "ec.CursorTemplate":  # fmt: skip
    gx, gy = origin
    on, off = [], []
    for _ in range(samples):
        pick = ec.pick_cell(rng, pos, walkable, projector)  # type: ignore[arg-type]
        if pick is None:
            continue
        x, y = gx + int(round(pick[2])), gy + int(round(pick[3]))
        on.append(hover_crop(agent, screen, x, y))
        agent.move(x + PARK_DX, y)
        t = r.ns()
        time.sleep(SETTLE_S)
        off.append(r.grab_after(screen, ec.crop_region(x, y), t + int(SETTLE_S * 1e9)))
    return ec.build_template(on, off)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--scene", choices=sorted(bench.SCENES), required=True)
    ap.add_argument("--seconds", type=float, required=True)
    ap.add_argument("--spawn-every", type=float, default=120.0)
    ap.add_argument("--seed", type=int, default=20261003)
    ap.add_argument("--calibrate-cursor", action="store_true")
    ap.add_argument("--hover-check", choices=("auto", "off"), default="auto")
    a = ap.parse_args()
    rng = random.Random(a.seed)
    stop = {"flag": False}
    signal.signal(signal.SIGTERM, lambda *_: stop.update(flag=True))
    counts = {
        "walks": 0,
        "spawns": 0,
        "returns": 0,
        "gm_failures": 0,
        "gm_disabled": 0,
        "no_cell": 0,
        "hover_rejects": 0,
    }
    info: dict[str, str] = {}
    mapname, sx, sy = bench.SCENES[a.scene]
    gx, gy, _gw, _gh = r.game_region()
    indoor = cm.load_indoor_table()  # fail closed: the projector must know the map's camera
    gat_path = cm.GAT_DIR / f"{mapname}.gat"
    walkable = gatmod.parse(gat_path.read_bytes()).walkable() if gat_path.exists() else None
    if walkable is None and cm.is_indoor(mapname, indoor):
        raise SystemExit(f"{gat_path} is missing: an indoor walk needs the map's walkability")
    pos = (sx, sy)  # the character's cell, tracked from our own clicks (approximate)
    with r.session("dataset-activity") as (agent, screen):
        camera = cm.load_camera_json(camera_file(agent.backend))
        projector, which = cm.projector_for(camera, mapname, indoor_table=indoor)
        info["projection"] = which
        tpl_path = CURSOR_DIR / f"walk_cursor_{agent.backend}.npz"
        bench.enter_scene(agent, screen, a.scene)
        if a.calibrate_cursor:
            tpl = calibrate_cursor(agent, screen, rng, pos, walkable, projector, (gx, gy))
            tpl.save(tpl_path, {"backend": agent.backend, "map": mapname,
                                "stamp": time.strftime("%Y-%m-%dT%H:%M:%S%z")})  # fmt: skip
            r.log(f"activity: walk cursor calibrated ({tpl.samples} samples, "
                  f"{int(tpl.mask.sum())} px, threshold {tpl.threshold:.1f})")  # fmt: skip
        template = (ec.CursorTemplate.load(tpl_path)
                    if a.hover_check == "auto" and tpl_path.exists() else None)  # fmt: skip
        info["hover_check"] = "on" if template is not None else "off"

        def occupied(u: int, v: int) -> bool:
            if template is None:
                return False
            if template.is_walk_cursor(hover_crop(agent, screen, gx + u, gy + v)):
                return False
            counts["hover_rejects"] += 1
            return True

        t_end = time.monotonic() + a.seconds
        next_spawn = time.monotonic() + 10
        try:
            while time.monotonic() < t_end and not stop["flag"]:
                if time.monotonic() >= next_spawn and not counts["gm_disabled"]:
                    if safe_gm(agent, screen, "@monster poring 3", counts):
                        counts["spawns"] += 1
                    next_spawn += a.spawn_every
                far = max(abs(pos[0] - sx), abs(pos[1] - sy)) > DRIFT_CELLS
                if far and not counts["gm_disabled"]:
                    # same map: the camera stays
                    if safe_gm(agent, screen, f"@warp {mapname} {sx} {sy}", counts):
                        counts["returns"] += 1
                    pos = (sx, sy)
                    time.sleep(3)
                    continue
                r.activate_client(agent, screen)
                # the click band keeps clear of the chat window and the hotbar (empty_cell.py)
                pick = ec.pick_cell(rng, pos, walkable, projector, reject=occupied, tries=12)
                if pick is None:
                    counts["no_cell"] += 1
                else:
                    dx, dy, u, v = pick
                    agent.click(gx + int(round(u)), gy + int(round(v)))
                    pos = (pos[0] + dx, pos[1] + dy)
                    counts["walks"] += 1
                agent.idle(rng.uniform(4.0, 9.0))
        finally:
            if not counts["gm_disabled"]:
                safe_gm(agent, screen, "@killmonster2", counts)  # the runner also does it after
    print(json.dumps({"scene": a.scene, "seconds": a.seconds, **counts, **info}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
