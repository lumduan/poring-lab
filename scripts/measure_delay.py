#!/usr/bin/env python3
"""Packet -> frame delay (docs/phase1-validation.md): from the server's walk reply leaving
rathena to the first lab frame that shows the character moving.

    measure_delay.py walks N [--as gm|player] [--cells 3]

* Trials: N short click-to-walks, alternating left / right of the character (screen centre), through
  /internal/agent (scripts/ro_agent.py: ASSIST only, waits out a human lease, stops on any refusal;
  in-game input only while the account is online=1 on our rAthena).
* Packet time: the sniffer's kernel receive time of our own ZC_NOTIFY_PLAYERMOVE (0x0087, the
  `self_move` event), mapped onto CLOCK_MONOTONIC (ADR-0007), read back from /captures.
* Frame time: inside the backend container (same X display, same clock) a scene band away from
  the cursor and the UI is grabbed continuously; the first grab after the packet where >10 % of the
  sampled pixels differ by >24 levels from the REFERENCE = the last grab before the packet (the
  scene as it was when the server answered). Cumulative, not frame-to-frame: a frame-to-frame
  threshold detects later at higher delivered fps (smaller steps), which made faster codecs look
  slower (2026-10-01).
* Delay = frame time - packet time: client processing + render + encode/transfer + client decode +
  Xvfb + our grab. Percentiles the SPEC way (docs/benchmarks/SPEC.md, scripts/benchlib.py):
  nearest rank over ALL trials, a trial with no frame within 1.5 s counting as a miss (">1500").
* Raw delays go to --out (default $SCRATCH/delay_raw.json, SCRATCH=/dev/shm/poring-lab-tmp).
"""

import argparse
import base64
import bisect
import gzip
import io
import json
import os
import re
import statistics
import subprocess
import sys
import threading
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import benchlib  # noqa: E402
import ro_agent as r  # noqa: E402

SCRATCH = Path(os.environ.get("SCRATCH", "/dev/shm/poring-lab-tmp"))

WATCH = r"""
import base64, sys, time, mss, numpy as np
x, y, w, h, secs = (float(v) for v in sys.argv[1:6])
reg = {"left": int(x), "top": int(y), "width": int(w), "height": int(h)}
with mss.MSS(display=":99") as s:
    end = time.monotonic() + secs
    while time.monotonic() < end:
        t = time.monotonic_ns(); g = s.grab(reg)
        a = np.frombuffer(g.raw, np.uint8).reshape(g.height, g.width, 4)[::8, ::8, :3]
        thumb = a.max(axis=2).astype(np.uint8)  # brightest channel, 8x8 subsampled
        print(f"{t},{base64.b64encode(thumb.tobytes()).decode()}", flush=True)
        time.sleep(0.004)  # ~200 grabs/s is plenty for a ~5-30 fps stream
"""
MOVED = 0.10


def events_files(since_wall: float) -> list[str]:
    """Only the sniffer's event shards that can hold events after ``since_wall`` (unix time): a
    shard is named by its UTC open time and rotates hourly, so anything opened more than ~1 h
    before the run cannot contain it (the volume keeps up to 7 days)."""
    names = subprocess.run(
        ["docker", "exec", "poring-lab-sniffer-1", "ls", "/captures"],
        capture_output=True, text=True, check=True,
    ).stdout.split()  # fmt: skip
    keep = []
    for name in sorted(names):
        m = re.fullmatch(r"events-(\d{8}T\d{6})Z\.jsonl\.gz", name)
        if m is None:
            continue
        opened = time.mktime(time.strptime(m.group(1), "%Y%m%dT%H%M%S")) - time.timezone
        if opened >= since_wall - 2 * 3600:
            keep.append(f"/captures/{name}")
    return keep


def self_moves(since_ns: int) -> list[dict[str, object]]:
    since_wall = time.time() - (r.ns() - since_ns) / 1e9
    files = events_files(since_wall)
    if not files:
        return []
    raw = subprocess.run(
        ["docker", "exec", "poring-lab-sniffer-1", "cat", *files], capture_output=True, check=True
    ).stdout
    out: list[dict[str, object]] = []
    # Concatenated gzip members; the newest is still open (flushed, not closed).
    with gzip.GzipFile(fileobj=io.BytesIO(raw)) as fh:
        try:
            for line in fh:
                e = json.loads(line)
                if e["type"] == "self_move" and e["t_mono_ns"] >= since_ns:
                    out.append(e)
        except EOFError:
            pass
    return out


def measure_walks(
    agent: r.Agent, screen: r.Screen, n: int, cells: int = 3, px_per_cell: int = 30
) -> dict[str, object]:
    """N click-to-walks inside an open ro_agent session; result dict incl. the raw delays."""
    gx, gy, gw, gh = r.game_region()
    cx, cy = gx + gw // 2, gy + int(gh * 0.53)  # the character's feet (screen centre)
    band = (gx + gw // 4, gy + int(gh * 0.12), gw // 2, int(gh * 0.18))  # above the character
    secs = n * 2.2 + 6
    r.activate_client(agent, screen)
    if r.any_console(screen):
        raise r.Stop("a PowerShell console is in front: no input")
    t_start = r.ns()
    watcher = subprocess.Popen(
        ["docker", "exec", "-i", r.BACKEND, "python", "-u", "-c", WATCH,
         *(str(v) for v in band), str(secs)],
        stdout=subprocess.PIPE, text=True,
    )  # fmt: skip
    # Drain stdout continuously: an unread pipe fills at 64 KB and blocks the watcher, which
    # then grabs nothing during the walks (0/40 matched, 2026-10-01).
    lines: list[str] = []
    assert watcher.stdout is not None
    reader = threading.Thread(target=lambda: lines.extend(watcher.stdout), daemon=True)
    reader.start()
    time.sleep(2)
    clicks: list[int] = []
    for i in range(n):
        dx = cells * px_per_cell * (1 if i % 2 == 0 else -1)
        t0 = r.ns()
        agent.click(cx + dx, cy)
        clicks.append(t0)
        time.sleep(2.1)
    watcher.wait(timeout=120)
    reader.join(timeout=10)
    out = "".join(lines)
    grabs: list[tuple[int, np.ndarray]] = []
    for ln in out.splitlines():
        if ln:
            t, b64 = ln.split(",", 1)
            grabs.append((int(t), np.frombuffer(base64.b64decode(b64), np.uint8).astype(np.int16)))
    times = [t for t, _ in grabs]
    moves = [m for m in self_moves(t_start) if isinstance(m["t_mono_ns"], int)]
    delays, unmatched = [], 0
    for m in moves:
        tp = int(str(m["t_mono_ns"]))
        i = bisect.bisect_left(times, tp)  # first grab at/after the packet
        if i == 0 or i >= len(grabs):
            unmatched += 1
            continue
        ref = grabs[i - 1][1]  # the scene as it was just before the packet
        hit = None
        for t, thumb in grabs[i:]:
            if t - tp > 1_500_000_000:
                break
            if float((np.abs(thumb - ref) > 24).mean()) >= MOVED:
                hit = t
                break
        if hit is None:
            unmatched += 1
            continue
        delays.append((hit - tp) / 1e6)
    click_to_packet = []
    for c in clicks:
        tp = next((int(str(m["t_mono_ns"])) for m in moves if int(str(m["t_mono_ns"])) >= c), None)
        if tp is not None and tp - c < 1_000_000_000:
            click_to_packet.append((tp - c) / 1e6)
    return {
        "trials": n, "self_move_packets": len(moves), "matched": len(delays),
        "unmatched": unmatched,
        "packet_to_frame_ms": benchlib.delay_summary(delays, trials=n),
        "click_sent_to_packet_ms_p50": (
            round(statistics.median(click_to_packet), 1) if click_to_packet else None
        ),
        "band": band, "threshold": MOVED, "t_wall_end": time.strftime("%H:%M:%S"),
        "raw": {"delays_ms": delays, "click_to_packet_ms": click_to_packet},
    }  # fmt: skip


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("mode", choices=["walks"])
    ap.add_argument("n", type=int)
    ap.add_argument("--as", dest="who", default="gm", choices=["gm", "player"])
    ap.add_argument("--cells", type=int, default=3)
    ap.add_argument("--px-per-cell", type=int, default=30)
    ap.add_argument("--out", type=Path, default=SCRATCH / "delay_raw.json")
    a = ap.parse_args()
    if not r.online_chars(a.who):
        raise r.Stop(f"{a.who} is not online=1 on our rAthena: no input sent")
    with r.session("measure-delay") as (agent, screen):
        result = measure_walks(agent, screen, a.n, a.cells, a.px_per_cell)
    raw = result.pop("raw")
    print(json.dumps(result))
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(raw))


if __name__ == "__main__":
    main()
