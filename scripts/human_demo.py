#!/usr/bin/env python3
"""A recorded HUMAN demonstration (Batt 2026-10-16 ~09:30): Batt plays the GM himself from the
console (ASSIST, his input takes the lease), and this records it. It is the human baseline for
hunt-flow and Phase 5 data.

THIS SCRIPT NEVER SENDS INPUT. It holds no Agent and opens no ro_agent.session: it reads frames
(ro_agent.Screen, the RDP frame bus) and the backend's /health only (test_human_demo.py checks the
source).

    human_demo.py arm [--minutes 10] [--margin 60] [--tag human-demo] [--end-quiet S]

``--tag`` names the session and its rule (Batt 2026-10-19: "human-ui-setup", his own chat-window
arrangement, recorded so the procedure is learnt). ``--end-quiet S`` also ends the recording S s
after his last input (once he has started), besides the stop file and the time box.
THE STANDING STEP AFTER IT (Batt 2026-10-22, decision 8): the character is taken out of any
dangerous map at once -- `scripts/demo_aftercare.py run <these args>` arms this recorder and, the
moment it returns, warps the character to its safe stand, sends @heal and saves a frame to judge.
``--map`` / ``--character gm|crusader`` label the session (Batt 2026-10-22: his Crusader demo in
orcsdun01; the GM's test state is recorded only for the GM). ``--battle-log`` also runs
battle_log.py's LIVE reader in its own process (pixels of the chat window, no input) into the
session's battle_log_live.jsonl, stopped with the recording.

What it records (all on the host's CLOCK_MONOTONIC):
- the game region as JPEGs at 5 Hz, q80, on the NAS (route_demo._record; it stops itself under
  2 GB free);
- the CPU unit detector's boxes on fresh grabs (boxes.jsonl, the capture time of each frame);
- the session's packets (record_session.write_packets, from arming to the end);
- the mux input log's source=human lines of the window (input_human.jsonl). They stay LOCAL:
  never committed, never on the NAS.

t0_live = the first human input after arming (/health last_human_input_age_s). The recording
ends at t0_live + minutes + margin, on the stop file, or on SIGINT. It then waits until
QUIET_S pass without human input (and no lease) before it returns, so nothing of ours touches
the client while Batt may still play. The analysis t0 is offline: the first self_move_request of
ours after arming (the character's first movement); nothing before it is analysed.
"""

from __future__ import annotations

import argparse
import json
import multiprocessing as mp
import signal
import sys
import time
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

HD_ROOT = Path("/mnt/poring-lab-datasets/human-demos")
STOP_FILE = Path("/dev/shm/poring-lab-tmp/human-demo.stop")
REC_HZ = 5.0
REC_QUALITY = 80
POLL_S = 0.5
QUIET_S = 60.0  # Batt: no client action until 60 s without human input
GM_TEST_STATE = {
    "base_level": 70,
    "str": 99,
    "atk": 197,
    "hit": 71,
    "immune": "confirmed for this login",
    "weight": [130, 4970],
}
CRUSADER_TEST_STATE = {
    "job": "crusader",
    "immune": "off (never made immune)",
    "autoguard": "off at arming (Batt casts it)",
}
NO_INPUT_CAP_S = 45 * 60.0  # armed but never played: give up, nothing recorded is analysed


def last_input_ns(now_ns: int, age_s: float | None) -> int | None:
    """PURE: the time of the last human input from /health's age, or None."""
    return None if age_s is None else now_ns - int(float(age_s) * 1e9)


def first_input_after(t_armed_ns: int, now_ns: int, age_s: float | None) -> int | None:
    """PURE: the last human input's time if it came after arming (a new input), else None."""
    t = last_input_ns(now_ns, age_s)
    return t if t is not None and t > t_armed_ns else None


def quiet(health: Mapping[str, Any], quiet_s: float = QUIET_S) -> bool:
    """PURE: no human input for ``quiet_s`` and no lease held."""
    age = health.get("last_human_input_age_s")
    return age is not None and float(age) >= quiet_s and not health.get("lease_active", True)


def human_lines(lines: Iterable[str], t0_ns: int, t1_ns: int) -> list[str]:
    """PURE: the input-log lines of source=human inside [t0, t1] (the window, nothing else)."""
    out = []
    for line in lines:
        try:
            rec = json.loads(line)
        except ValueError:
            continue
        if rec.get("source") == "human" and t0_ns <= int(rec.get("t_mono_ns", -1)) <= t1_ns:
            out.append(line.rstrip("\n"))
    return out


def _detect(path: str, region: tuple[int, int, int, int], stop: Any) -> None:
    """The detector process: boxes of fresh grabs, one JSON line per frame (no input)."""
    import ro_agent as r
    import unit_detector

    screen = r.Screen()
    det = unit_detector.UnitDetector()
    with open(path, "a") as fh:
        while not stop.is_set():
            t, img = screen.grab(*region)
            boxes = det.detect(img)
            fh.write(json.dumps({"t": int(t), "ms": round(det.last_ms, 1),
                                 "boxes": [[round(b.x0, 1), round(b.y0, 1), round(b.x1, 1),
                                            round(b.y1, 1), round(b.score, 3), b.cls]
                                           for b in boxes]}) + "\n")  # fmt: skip
            fh.flush()


def arm(
    minutes: float,
    margin_s: float,
    tag: str = "human-demo",
    end_quiet_s: float | None = None,
    map_: str = "prt_fild08",
    character: str = "gm",
    battle_log: bool = False,
) -> int:
    import os
    import subprocess

    import record_session
    import ro_agent as r
    import route_demo

    from poring_env.demo import DemoLog, new_session_id

    lock = record_session.read_lock(r.ROOT / "state")
    h = r.backend_health()
    env = h.get("environment") or {}
    if str(lock.backend) != "rdp" or h.get("mode") != "ASSIST" or h.get("bot_agents"):
        raise SystemExit(f"refused: lock {lock.backend}, mode {h.get('mode')}, bot agents "
                         f"{h.get('bot_agents')} (needs rdp, ASSIST, no bot)")  # fmt: skip
    if env.get("state") != "green":
        raise SystemExit(f"refused: the interlock is {env.get('state')} ({env.get('reason')})")
    STOP_FILE.unlink(missing_ok=True)
    sid = new_session_id(tag)
    log = DemoLog(sid)
    frames_dir = HD_ROOT / sid / "frames"
    frames_dir.mkdir(parents=True, exist_ok=True)
    region = r.game_region()
    t_armed = r.ns()
    log.start(type=tag, rule=f"{tag}@1", scored=False, actor="human:batt",
              map=map_, account="gm", character=character, minutes=minutes, margin_s=margin_s,
              backend=str(lock.backend), lock_seq=lock.seq, t_armed_ns=t_armed,
              frames_dir=str(frames_dir), rec_hz=REC_HZ, rec_quality=REC_QUALITY,
              battle_log=battle_log,
              test_state=GM_TEST_STATE if character == "gm" else CRUSADER_TEST_STATE)  # fmt: skip
    ctx = mp.get_context("spawn")
    stop_rec, stop_det = ctx.Event(), ctx.Event()
    rec = ctx.Process(target=route_demo._record, args=(str(frames_dir), region, stop_rec, REC_HZ,
                                                       REC_QUALITY), daemon=True)  # fmt: skip
    det = ctx.Process(target=_detect, args=(str(log.dir / "boxes.jsonl"), region, stop_det),
                      daemon=True)  # fmt: skip
    rec.start()
    det.start()
    blog = None
    if battle_log:  # pixels only: the chat window from frames, its own process (nice 10)
        blog = subprocess.Popen(["nice", "-n", "10", sys.executable,
                                 str(Path(__file__).with_name("battle_log.py")), "live",
                                 "--out", str(log.dir / "battle_log_live.jsonl"), "--hz", "10",
                                 "--until-pid", str(os.getpid())],
                                stdout=(log.dir / "battle_log_live.out").open("a"),
                                stderr=subprocess.STDOUT)  # fmt: skip
    print(json.dumps({"session": sid, "armed": time.strftime("%H:%M:%S"),
                      "frames": str(frames_dir)}), flush=True)  # fmt: skip
    interrupted = {"v": False}
    signal.signal(signal.SIGINT, lambda *_: interrupted.__setitem__("v", True))
    t0_live: int | None = None
    ended = "time_box"
    while True:
        time.sleep(POLL_S)
        now = r.ns()
        h = r.backend_health()
        if t0_live is None and h:
            t0_live = first_input_after(t_armed, now, h.get("last_human_input_age_s"))
            if t0_live is not None:
                print(json.dumps({"t0_live": time.strftime("%H:%M:%S"), "ends_in_s":
                                  round(minutes * 60 + margin_s)}), flush=True)  # fmt: skip
        if interrupted["v"]:
            ended = "stopped:sigint"
        elif STOP_FILE.exists():
            ended = "stopped:stop_file"
        elif t0_live is not None and now >= t0_live + int((minutes * 60 + margin_s) * 1e9):
            ended = "time_box"
        elif (end_quiet_s is not None and t0_live is not None and h
              and float(h.get("last_human_input_age_s") or 0.0) >= end_quiet_s):  # fmt: skip
            ended = "quiet"
        elif t0_live is None and now - t_armed > int(NO_INPUT_CAP_S * 1e9):
            ended = "no_input"
        else:
            continue
        break
    t_end = r.ns()
    stop_rec.set()
    stop_det.set()
    rec.join(timeout=10)
    det.join(timeout=10)
    if blog is not None:
        blog.terminate()
        try:
            blog.wait(timeout=10)
        except subprocess.TimeoutExpired:
            blog.kill()
    print(json.dumps({"recording_ended": ended, "at": time.strftime("%H:%M:%S")}), flush=True)
    waited = time.monotonic()
    while True:  # no client action of ours until Batt has stopped (QUIET_S without his input)
        h = r.backend_health()
        if h and quiet(h):
            break
        if time.monotonic() - waited > 30 * 60:
            print("still not quiet after 30 min: finalising without touching the client",
                  flush=True)  # fmt: skip
            break
        time.sleep(1.0)
    events, _anchor = record_session.write_packets(log.dir, t_armed, t_end)
    day_files = sorted((r.ROOT / "data" / "input_log").glob("*.jsonl"))[-2:]
    lines: list[str] = []
    for f in day_files:
        with f.open(encoding="utf-8") as fh:
            lines += human_lines(fh, t_armed, t_end)
    (log.dir / "input_human.jsonl").write_text("\n".join(lines) + ("\n" if lines else ""))
    n_frames = len(list(frames_dir.glob("*.jpg")))
    n_boxes = sum(1 for _ in (log.dir / "boxes.jsonl").open()) \
        if (log.dir / "boxes.jsonl").exists() else 0  # fmt: skip
    log.finish(ended=ended, t0_live_ns=t0_live, t_end_ns=t_end, frames=n_frames,
               detector_frames=n_boxes, packet_events=len(events), human_input_events=len(lines),
               quiet_at=time.strftime("%H:%M:%S"))  # fmt: skip
    print(json.dumps({"session": sid, "ended": ended, "frames": n_frames,
                      "detector_frames": n_boxes, "packets": len(events),
                      "human_input_events": len(lines), "quiet": time.strftime("%H:%M:%S")}),
          flush=True)  # fmt: skip
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)  # fmt: skip
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("arm")
    a.add_argument("--minutes", type=float, default=10.0)
    a.add_argument("--margin", type=float, default=60.0)
    a.add_argument("--tag", default="human-demo", help="the session's name and rule")
    a.add_argument("--end-quiet", type=float, default=None,
                   help="also end S s after the last human input (once started)")  # fmt: skip
    a.add_argument("--map", default="prt_fild08", help="the map played (the session's label)")
    a.add_argument("--character", choices=("gm", "crusader"), default="gm")
    a.add_argument(
        "--battle-log",
        action="store_true",
        help="also run battle_log.py's live reader (pixels only) into the session",
    )
    args = ap.parse_args()
    return arm(args.minutes, args.margin, args.tag, args.end_quiet, args.map, args.character,
               args.battle_log)  # fmt: skip


if __name__ == "__main__":
    sys.exit(main())
