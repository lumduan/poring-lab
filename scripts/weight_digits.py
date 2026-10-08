#!/usr/bin/env python3
"""The weight readout's missing digits, then the proof on KNOWN totals (loot@1 P1; Batt 2026-10-08:
"generate the missing digits (1, 4, 6, 7, 8) with @item of chosen weights; prove the reader on
known totals").

    weight_digits.py run [--step-s 3.0] [--hz 4]          the live part: GM @item steps, recorded
    then, offline (loot@1's tools; packets label and judge, they never feed the reader):
    weight_calibrate.py OUT/calib --packets SESSION/packets.jsonl.gz    -> READY or not
    weight_resolution.py measure OUT/steps-proof.jsonl --packets SESSION/packets.jsonl.gz

Three phases, each a chain of `@item` steps of known weight (the pinned item_db; rAthena units:
10 = 1.0 shown), STEP_S apart so each readout settles (the reader's 1.5 s):
- **A, calibration** (frames into OUT/calib): 10 x Jellopy 909 (+1.0 each). From the readout of
  205 this walks 206 ... 215, which shows the never-banked 6 7 8 1 4.
- **B, proof on known totals** (OUT/proof, HELD OUT from A): 2 x Knife 1201 (+40.0 each), then
  Jellopy x 5 in one step (+5.0). The totals land on new digit positions (255, 295, 300).
- **C, resolution** (OUT/proof): 10 x Arrow 1750 (+0.1 each): where the number moves, and the
  display rule (floor / round / ceil), checked against the server's own weight.
The step file names the frame just before each step and the last frame before the next one, so
`weight_resolution.py measure` reads both with the reader and compares with the packets.

Pixels in, GM chat out: the harness reads nothing back to decide. Frames are client pixels (RAM,
/dev/shm; never committed). The items stay in the GM's inventory (the weight stays far below 50 %).
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import record_session  # noqa: E402
import ro_agent as r  # noqa: E402

from poring_env.demo import DemoLog, new_session_id  # noqa: E402

OUT_ROOT = Path("/dev/shm/poring-lab-tmp/weight-digits")
JELLOPY, KNIFE, ARROW = 909, 1201, 1750  # rAthena weights 10, 400, 1 (data/kb/items.json)
PHASES: dict[str, list[tuple[int, int]]] = {
    "calib": [(JELLOPY, 1)] * 10,
    "proof": [(KNIFE, 1), (KNIFE, 1), (JELLOPY, 5)] + [(ARROW, 1)] * 10,
}
STEP_S = 3.0
REC_HZ = 4.0


def _record(out: str, region: tuple[int, int, int, int], stop: Any, hz: float) -> None:
    """The recorder process: the game region as <k>-<t_mono_ns>.jpg (quality 95)."""
    from PIL import Image

    screen = r.Screen()
    k = 0
    while not stop.is_set():
        t0 = time.monotonic()
        t, img = screen.grab(*region)
        Image.fromarray(np.ascontiguousarray(img[..., 2::-1])).save(
            Path(out) / f"{k:05d}-{t}.jpg", quality=95
        )
        k += 1
        time.sleep(max(0.0, 1.0 / hz - (time.monotonic() - t0)))


def frame_before(frames: Path, t_ns: int) -> str | None:
    """The newest recorded frame strictly before t_ns."""
    best: tuple[int, Path] | None = None
    for p in frames.glob("*.jpg"):
        t = int(p.stem.split("-")[1])
        if t < t_ns and (best is None or t > best[0]):
            best = (t, p)
    return None if best is None else str(best[1])


def run(step_s: float, hz: float) -> int:
    import multiprocessing as mp

    sid = new_session_id("weight-digits")
    out = OUT_ROOT / sid
    log = DemoLog(sid)
    lock = record_session.read_lock(r.ROOT / "state")
    log.start(backend=str(lock.backend), lock_seq=lock.seq, server="lab-rathena",
              rule="loot@1/P1-weight-digits", account="gm")  # fmt: skip
    t_first = r.ns()
    ctx = mp.get_context("spawn")
    steps: dict[str, list[dict[str, Any]]] = {}
    with r.session("rule:weight-digits") as (agent, screen):
        for phase, items in PHASES.items():
            frames = out / phase
            frames.mkdir(parents=True, exist_ok=True)
            stop = ctx.Event()
            rec = ctx.Process(target=_record, args=(str(frames), tuple(r.game_region()), stop, hz),
                              daemon=True)  # fmt: skip
            rec.start()
            time.sleep(step_s)  # a settled readout before the first step
            times: list[tuple[int, list[int]]] = []
            for item, n in items:
                t = r.ns()
                r.gm(agent, screen, f"@item {item} {n}")
                times.append((t, [item, n]))
                time.sleep(step_s)
            t_end = r.ns()
            stop.set()
            rec.join(timeout=5)
            steps[phase] = []
            for i, (t, it) in enumerate(times):
                t_next = times[i + 1][0] if i + 1 < len(times) else t_end
                steps[phase].append({
                    "before": {"frame": frame_before(frames, t)},
                    "after": {"frame": frame_before(frames, t_next)},
                    "items": [it], "t_before_ns": t, "t_after_ns": t_next,
                })  # fmt: skip
    events, anchor = record_session.write_packets(log.dir, t_first, r.ns())
    for phase, rows in steps.items():
        (out / f"steps-{phase}.jsonl").write_text("".join(json.dumps(s) + "\n" for s in rows))
    result = {"session": sid, "out": str(out), "steps": {p: len(s) for p, s in steps.items()},
              "frames": {p: len(list((out / p).glob("*.jpg"))) for p in steps}}  # fmt: skip
    log.finish(packet_events=len(events), packet_anchor=anchor, result=result)
    print(json.dumps(result, indent=1), flush=True)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    rp = sub.add_parser("run")
    rp.add_argument("--step-s", type=float, default=STEP_S)
    rp.add_argument("--hz", type=float, default=REC_HZ)
    a = ap.parse_args()
    return run(a.step_s, a.hz)


if __name__ == "__main__":
    sys.exit(main())
