#!/usr/bin/env python3
"""Full-scene motion benchmark for the RDP pipeline: how many game frames reach the lab, and at what
desktop CPU (docs/phase0-latency.md "before/after" tables).

    measure_motion.py rotate SECONDS [--label NAME]

* Motion: a bot camera rotation (right-drag sweeps across empty ground, never a click on the world)
  through /internal/agent (scripts/ro_agent.py: ASSIST only, waits for a human lease, stops on
  any refusal). The character never moves.
* Frames reaching the lab: inside the backend container (same clock), a region of the scene is
  grabbed continuously -- from X, or in console mode with a live S2 writer from the frame bus
  (poring_backend.grabsource; V3b never paints X). A "frame" is a grab where >1 % of pixels moved
  by >24 levels from the previous one (rejects the RDP codec's progressive-refinement nudges).
  Per-second counts.
* Lab CPU: cgroup cpu.stat usage of the display-path containers (desktop: Xvfb + xfreerdp;
  gamestream: Moonlight in console mode), cores, per container and in total.
* Windows' RemoteFX Graphics counters (input / output fps, frames skipped for insufficient client
  resources) are taken with typeperf typed into an existing PowerShell console, minimised before the
  run (docs/phase0-latency.md) -- never through the Run dialog (Defender's ClickFix detection).

The scene region and drag row come from GAME_REGION (the client area), so the same command works
before and after a window resize.
"""

import argparse
import json
import statistics
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ro_agent as r  # noqa: E402

COUNTER = r"""
import sys, time
import numpy as np
from poring_backend.grabsource import GrabSource
x, y, w, h, secs = (float(v) for v in sys.argv[1:6])
prev = last = None
sec = int(time.monotonic()); n = grabs = 0
for t, a, source in GrabSource().frames((int(x), int(y), int(w), int(h)), secs, x_period_s=0.003):
    if source != last:
        print(f"#source={source}", flush=True)
        last = source
    if a is not None:  # None = a bus tick (no new frame): the second still ends on time
        cur = a[::2, ::2, :3].astype(np.int16); grabs += 1
        if prev is not None and (np.abs(cur - prev).max(axis=2) > 24).mean() > 0.01:
            n += 1
        prev = cur
    now = int(time.monotonic())
    if now != sec:
        print(f"{now},{n},{grabs}", flush=True)
        sec, n, grabs = now, 0, 0
"""


# The display path's containers (ADR-0009): desktop (Xvfb + xfreerdp) and, in console mode,
# gamestream (Moonlight). Lab-side cost = their cgroup CPU together.
DISPLAY_PATH = ("poring-lab-desktop-1", "poring-lab-gamestream-1")


def container_usage_us(name: str) -> int | None:
    """cgroup cpu.stat usage_usec of a running container; None if it is not running."""
    res = subprocess.run(
        ["docker", "inspect", "-f", "{{.Id}} {{.State.Running}}", name],
        capture_output=True, text=True,
    )  # fmt: skip
    if res.returncode != 0 or not res.stdout.strip().endswith("true"):
        return None
    cid = res.stdout.split()[0]
    stat = Path(f"/sys/fs/cgroup/system.slice/docker-{cid}.scope/cpu.stat").read_text()
    return int(dict(line.split() for line in stat.splitlines())["usage_usec"])


def usage_us(names: tuple[str, ...] = DISPLAY_PATH) -> dict[str, int]:
    return {n: u for n in names if (u := container_usage_us(n)) is not None}


def cores_between(
    before: dict[str, int], after: dict[str, int], seconds: float
) -> dict[str, float]:
    per = {n: (after[n] - before[n]) / 1e6 / seconds for n in before if n in after}
    return {**{n: round(v, 2) for n, v in per.items()}, "total": round(sum(per.values()), 2)}


def desktop_usage_us() -> int:
    usage = container_usage_us("poring-lab-desktop-1")
    assert usage is not None, "the desktop container is not running"
    return usage


def rotate(agent: r.Agent, seconds: float, x0: int, y: int) -> None:
    """Right-drag sweeps of +-150 px around x0 on row y; re-grip every 20 s."""
    nx = 1 / r.desktop()[0]
    ny = 1 / r.desktop()[1]

    def button(action: str, x: int) -> None:
        agent.send([{"type": "mouse_button", "t_mono_ns": r.ns(), "frame_id": -1,
                     "button": "right", "action": action, "x": x * nx, "y": y * ny}])  # fmt: skip

    t0 = time.monotonic()
    held, last_grip = False, 0.0
    try:
        while (el := time.monotonic() - t0) < seconds:
            if not held or time.monotonic() - last_grip > 20:
                if held:
                    button("up", x0)
                agent.move(x0, y)
                time.sleep(0.05)
                button("down", x0)
                held, last_grip = True, time.monotonic()
            phase = el % 4.0
            dx = int(150 * (phase if phase < 2.0 else 4.0 - phase) / 2.0)
            agent.move(x0 - dx, y)
            time.sleep(0.016)
    finally:
        if held:
            button("up", x0)


def regions() -> tuple[tuple[int, int, int, int], tuple[int, int]]:
    """(scene band, drag point) from GAME_REGION: the middle band of the client, clear of the side
    windows and the chat box; the drag on empty ground at 78 %/78 %."""
    gx, gy, gw, gh = r.game_region()
    region = (gx + gw // 4, gy + int(gh * 0.52), gw // 2, int(gh * 0.30))
    return region, (gx + int(gw * 0.78), gy + int(gh * 0.78))


def measure_rotation(
    agent: r.Agent, screen: r.Screen, seconds: float, label: str = "run"
) -> dict[str, object]:
    """One rotation inside an open ro_agent session; returns the result dict (see module doc)."""
    region, (drag_x, drag_y) = regions()
    r.activate_client(agent, screen)
    if r.any_console(screen):
        raise r.Stop("a PowerShell console is in front: no rotation (right-click pastes)")
    counter = subprocess.Popen(
        ["docker", "exec", "-i", r.BACKEND, "python", "-u", "-c", COUNTER,
         *(str(v) for v in region), str(seconds + 8)],
        stdout=subprocess.PIPE, text=True,
    )  # fmt: skip
    time.sleep(4)  # idle baseline seconds first
    cpu0, t0 = usage_us(), time.monotonic()
    rotate(agent, seconds, drag_x, drag_y)
    cpu1, t1 = usage_us(), time.monotonic()
    out, _ = counter.communicate(timeout=60)
    sources = [ln.split("=", 1)[1] for ln in out.splitlines() if ln.startswith("#source=")]
    rows = [
        tuple(int(v) for v in line.split(","))
        for line in out.splitlines()
        if line and not line.startswith("#")
    ]
    moving = [n for _, n, _ in rows[5:-4]]  # skip the idle lead-in and the tail
    cores = cores_between(cpu0, cpu1, t1 - t0)
    q = statistics.quantiles(moving, n=10) if len(moving) >= 10 else [float("nan")] * 9
    return {
        "label": label, "seconds": seconds, "region": region,
        "frames_per_s_median": statistics.median(moving) if moving else None,
        "frames_per_s_p10": q[0], "frames_per_s_p90": q[8],
        "frames_per_s": moving,
        "idle_lead_in": [n for _, n, _ in rows[:4]],
        "grabs_per_s_median": statistics.median(g for _, _, g in rows) if rows else None,
        "frame_sources": sources,
        "desktop_cores": cores.get("poring-lab-desktop-1"),
        "lab_cores": cores,
        "t_wall_end": time.strftime("%H:%M:%S"),
    }  # fmt: skip


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("mode", choices=["rotate"])
    ap.add_argument("seconds", type=float)
    ap.add_argument("--label", default="run")
    a = ap.parse_args()
    if r.any_online() < 1:
        raise r.Stop("no character online=1 on our rAthena: no in-game input sent")
    with r.session("measure-motion") as (agent, screen):
        result = measure_rotation(agent, screen, a.seconds, a.label)
    result.pop("frames_per_s")
    print(json.dumps(result))


if __name__ == "__main__":
    main()
