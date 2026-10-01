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
  sampled pixels moved by >24 levels (the camera follows the character, so the scene scrolls).
* Delay = frame time - packet time: client processing + render + RDP encode/transfer + xfreerdp
  decode + Xvfb + our grab. p50/p95/p99 over the matched trials; unmatched trials are reported.
"""

import argparse
import gzip
import io
import json
import statistics
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ro_agent as r  # noqa: E402

WATCH = r"""
import sys, time, mss, numpy as np
x, y, w, h, secs = (float(v) for v in sys.argv[1:6])
reg = {"left": int(x), "top": int(y), "width": int(w), "height": int(h)}
def arr(s):
    a = np.frombuffer(s.raw, np.uint8).reshape(s.height, s.width, 4)
    return a[::2, ::2, :3].astype(np.int16)
with mss.MSS(display=":99") as s:
    prev = arr(s.grab(reg)); end = time.monotonic() + secs
    while time.monotonic() < end:
        t = time.monotonic_ns(); cur = arr(s.grab(reg))
        frac = float((np.abs(cur - prev).max(axis=2) > 24).mean())
        if frac > 0.005:
            print(f"{t},{frac:.4f}", flush=True)
        prev = cur
"""
MOVED = 0.10


def self_moves(since_ns: int) -> list[dict[str, object]]:
    raw = subprocess.run(
        ["docker", "exec", "poring-lab-sniffer-1", "sh", "-c", "cat /captures/events-*.jsonl.gz"],
        capture_output=True, check=True,
    ).stdout  # fmt: skip
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


def pct(values: list[float], q: float) -> float:
    s = sorted(values)
    return s[min(len(s) - 1, int(round(q * (len(s) - 1))))]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("mode", choices=["walks"])
    ap.add_argument("n", type=int)
    ap.add_argument("--as", dest="who", default="gm", choices=["gm", "player"])
    ap.add_argument("--cells", type=int, default=3)
    ap.add_argument("--px-per-cell", type=int, default=30)
    a = ap.parse_args()
    if not r.online_chars(a.who):
        raise r.Stop(f"{a.who} is not online=1 on our rAthena: no input sent")
    gx, gy, gw, gh = r.game_region()
    cx, cy = gx + gw // 2, gy + int(gh * 0.53)  # the character's feet (screen centre)
    band = (gx + gw // 4, gy + int(gh * 0.12), gw // 2, int(gh * 0.18))  # above the character
    secs = a.n * 2.2 + 6
    with r.session("measure-delay") as (agent, screen):
        r.activate_client(agent, screen)
        if r.find_console(screen) is not None:
            raise r.Stop("a PowerShell console is in front: no input")
        t_start = r.ns()
        watcher = subprocess.Popen(
            ["docker", "exec", "-i", r.BACKEND, "python", "-u", "-c", WATCH,
             *(str(v) for v in band), str(secs)],
            stdout=subprocess.PIPE, text=True,
        )  # fmt: skip
        time.sleep(2)
        clicks: list[int] = []
        for i in range(a.n):
            dx = a.cells * a.px_per_cell * (1 if i % 2 == 0 else -1)
            t0 = r.ns()
            agent.click(cx + dx, cy)
            clicks.append(t0)
            time.sleep(2.1)
        out, _ = watcher.communicate(timeout=120)
    frames = [(int(t), float(f)) for t, f in (ln.split(",") for ln in out.splitlines() if ln)]
    moves = [m for m in self_moves(t_start) if isinstance(m["t_mono_ns"], int)]
    delays, unmatched = [], 0
    for m in moves:
        tp = int(str(m["t_mono_ns"]))
        hit = next((t for t, f in frames if t >= tp and f >= MOVED), None)
        if hit is None or hit - tp > 1_500_000_000:
            unmatched += 1
            continue
        delays.append((hit - tp) / 1e6)
    click_to_packet = []
    for c in clicks:
        tp = next((int(str(m["t_mono_ns"])) for m in moves if int(str(m["t_mono_ns"])) >= c), None)
        if tp is not None and tp - c < 1_000_000_000:
            click_to_packet.append((tp - c) / 1e6)
    result = {
        "trials": a.n, "self_move_packets": len(moves), "matched": len(delays),
        "unmatched": unmatched,
        "packet_to_frame_ms": {
            "p50": round(statistics.median(delays), 1) if delays else None,
            "p95": round(pct(delays, 0.95), 1) if delays else None,
            "p99": round(pct(delays, 0.99), 1) if delays else None,
            "min": round(min(delays), 1) if delays else None,
            "max": round(max(delays), 1) if delays else None,
        },
        "click_sent_to_packet_ms_p50": (
            round(statistics.median(click_to_packet), 1) if click_to_packet else None
        ),
        "band": band, "threshold": MOVED, "t_wall_end": time.strftime("%H:%M:%S"),
    }  # fmt: skip
    print(json.dumps(result))
    Path("/dev/shm/poring-lab-tmp/delay_raw.json").write_text(
        json.dumps({"delays_ms": delays, "click_to_packet_ms": click_to_packet})
    )


if __name__ == "__main__":
    main()
