#!/usr/bin/env python3
"""The clean-room Sunshine experiment (Batt, 2026-10-03; ADR-0009): runner + watchdog.

The session moves to the console ONCE and RDP holds for the whole experiment; only the lab client
varies (V1 Moonlight-qt as-is, V2 + openbox, V3 the S2 spike), one at a time, Windows untouched.
Every lock write goes through scripts/capture_backend.py (the only writer; its flock serialises the
runner, the watchdog and a human).

    cleanroom.py preflight                    lock rdp/steady, one xfreerdp, ASSIST, GM online,
                                              Sunshine paired (s2spike serverinfo), new image
    cleanroom.py start [--hard-cap-min 180]   the watchdog (detached), then to-console --cleanroom
    cleanroom.py variant V1|V1gdb|V2|V3|V3b|S2 [--box-min N] [--knob K=V ...]
                                              stream -> first picture <= 90 s -> 60 s steady ->
                                              hold -> stream again (reliable?) ; black: diagnostics
                                              -> hold. Leaves a RELIABLE variant streaming (for the
                                              functional checks); prints a JSON verdict
    cleanroom.py checks [--box-min 45]        after a reliable variant: a time box for the bench and
                                              the functional checks (the watchdog enforces it; keep
                                              `heartbeat` fresh meanwhile)
    cleanroom.py hold | heartbeat | status
    cleanroom.py rearm                        restart a STOPPED watchdog for the active room, for
                                              the time left to its (absolute) hard cap
    cleanroom.py end                          hold, to-rdp, the exit checks, stop the watchdog
    cleanroom.py watchdog                     (systemd-run --user; never by hand)
    cleanroom.py guard                        (a systemd --user TIMER, every 60 s while a room runs;
                                              never by hand): a room active + its watchdog unit not
                                              running -> `capture_backend.py alarm --set
                                              watchdog_down` (RED on the console, /health.alarms)

The WATCHDOG survives this session: on a variant's box (+5 min), a stale heartbeat (10 min) or the
hard cap it SIGTERMs the runner and runs the clean to-rdp. It defers to a human at the console
(/health lease_active or input in the last 2 min), except at the hard cap. It never loops: one
to-rdp, one --recover after 60 s, then it stops and says so. State: /dev/shm/poring-lab-cleanroom.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import signal
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
STATE = Path(os.environ.get("CLEANROOM_DIR", "/dev/shm/poring-lab-cleanroom"))
STATUS = STATE / "status.json"
HEARTBEAT = STATE / "heartbeat"
PY = str(REPO / ".venv" / "bin" / "python")
CB = [PY, str(REPO / "scripts" / "capture_backend.py")]
GAMESTREAM = "poring-lab-gamestream-1"
UNIT = "poring-cleanroom-watchdog"
BOXES_MIN = {"V1": 20, "V1gdb": 10, "V2": 30, "V3": 60, "V3b": 60, "S2": 60, "checks": 45}
S2_CLIENTS = ("V3", "V3b", "S2")  # the s2spike variants (v3-stats.json, its diagnostics)
WATCHDOG_GRACE_S = 5 * 60  # the runner's own hold-and-advance wins
HEARTBEAT_STALE_S = 10 * 60
HUMAN_RECENT_S = 120
FIRST_PICTURE_S = 90
STEADY_S = 60
TO_RDP_TIMEOUT_S = 15 * 60
ENTRY_GRACE_S = 15 * 60


def say(msg: str) -> None:
    line = f"[{time.strftime('%H:%M:%S')}] {msg}"
    print(line, flush=True)
    with contextlib.suppress(OSError):
        STATE.mkdir(parents=True, exist_ok=True)
        with (STATE / "log.txt").open("a") as fh:
            fh.write(line + "\n")


# --- status ------------------------------------------------------------------------------------


def load_status() -> dict[str, Any]:
    try:
        data: dict[str, Any] = json.loads(STATUS.read_text())
        return data
    except (OSError, ValueError):
        return {}


def save_status(**changes: Any) -> dict[str, Any]:
    STATE.mkdir(parents=True, exist_ok=True)
    status = {**load_status(), **changes, "updated": time.time()}
    tmp = STATUS.with_suffix(".tmp")
    tmp.write_text(json.dumps(status, indent=1))
    tmp.replace(STATUS)
    return status


def new_room_status(**fields: Any) -> dict[str, Any]:
    """A NEW room's status: the previous room's file is archived, never merged. (2026-10-03 17:06:
    a merge kept the earlier room's entered_ts, so the new watchdog read rdp/steady as "over" and
    exited at once; `start` then stopped before any lock write.)"""
    old = load_status()
    if old:
        STATUS.replace(STATE / f"status-{int(float(old.get('updated') or time.time()))}.json")
    return save_status(**fields)


def heartbeat() -> None:
    STATE.mkdir(parents=True, exist_ok=True)
    HEARTBEAT.write_text(f"{time.time()}\n")


def heartbeat_age(now: float) -> float:
    try:
        return now - float(HEARTBEAT.read_text().strip())
    except (OSError, ValueError):
        return float("inf")


# --- the outside world ------------------------------------------------------------------------


def cb(*args: str, timeout: float = 600) -> subprocess.CompletedProcess[str]:
    res = subprocess.run(
        [*CB, *args], capture_output=True, text=True, timeout=timeout, cwd=REPO, check=False
    )
    text = (res.stdout + res.stderr).strip()
    tail = text.splitlines()[-6:]
    # the whole output too (the log keeps 6 lines; a 2026-10-04 to-console failure needed more)
    full = STATE / f"cb-{args[0] if args else 'none'}.log"
    with contextlib.suppress(OSError):
        full.write_text(text + "\n")
    say(f"capture_backend {' '.join(args)}: rc={res.returncode} (full output: {full})")
    for line in tail:
        say(f"  | {line}")
    return res


def health() -> dict[str, Any]:
    here = str(Path(__file__).resolve().parent)
    if here not in sys.path:
        sys.path.insert(0, here)
    from backend_addr import backend_ip  # the DEFAULT network's address (two networks since c2)

    ip = backend_ip() or "127.0.0.1"
    with urllib.request.urlopen(f"http://{ip}:8000/health", timeout=5) as resp:
        data: dict[str, Any] = json.loads(resp.read())
    return data


def lock_state() -> tuple[str, str, str]:
    """(backend, phase, reason) from the host lock file."""
    text = ""
    with contextlib.suppress(OSError):
        text = (REPO / "state" / "capture-backend").read_text()
    kv = dict(line.split("=", 1) for line in text.splitlines() if "=" in line)
    return kv.get("BACKEND", "rdp"), kv.get("PHASE", "steady"), kv.get("REASON", "")


def human_active(h: dict[str, Any]) -> bool:
    age = h.get("last_human_input_age_s")
    return bool(h.get("lease_active")) or (age is not None and age < HUMAN_RECENT_S)


def frame_stats() -> dict[str, float]:
    """The session area of :99 right now: is there a picture (not black)?"""
    sys.path.insert(0, str(REPO / "scripts"))
    import ro_agent as r

    screen = r.Screen()
    try:
        frame = screen.full()
    finally:
        screen.close()
    return classify_frame(frame)


TASKBAR_H = 48  # the Windows taskbar strip at the session's bottom


def classify_frame(bgra: Any) -> dict[str, float]:
    """The STREAM, not just "not black": Moonlight-qt's own Qt window (1280x600 at the top, its
    "no hardware decoder" warning) passed a whole-frame test on 2026-10-03 and made V2 look
    reliable before its stream had shown. Only the stream draws the Windows taskbar at the bottom
    of the session, and the Qt window never reaches it."""
    import numpy as np

    gray = bgra[:, :, :3].astype(np.float32).mean(axis=2)
    bar = gray[-TASKBAR_H:, :]
    return {
        "mean": round(float(gray.mean()), 2),
        "std": round(float(gray.std()), 2),
        "nonblack": round(float((gray > 24).mean()), 4),
        "taskbar_nonblack": round(float((bar > 24).mean()), 4),
        "taskbar_std": round(float(bar.std()), 2),
    }


def is_picture(stats: dict[str, float]) -> bool:
    return stats["taskbar_nonblack"] > 0.30 and stats["taskbar_std"] > 4.0


def shot(name: str) -> str:
    sys.path.insert(0, str(REPO / "scripts"))
    import ro_agent as r

    screen = r.Screen()
    try:
        path = r.to_png(screen.full(), STATE / "frames" / f"{name}.png")
    finally:
        screen.close()
    return str(path)


def gamestream_logs(since: str) -> str:
    res = subprocess.run(["docker", "logs", "--since", since, GAMESTREAM], capture_output=True,
                         text=True, check=False)  # fmt: skip
    return res.stdout + res.stderr


def utc_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


# --- the watchdog's decision (pure) -------------------------------------------------------------


def decide(
    now: float, status: dict[str, Any], lock: tuple[str, str, str], human: bool, hb_age: float
) -> str:
    """'done' | 'wait' | 'defer:<why>' | 'exit:<why>'."""
    backend, phase, _ = lock
    if backend == "rdp" and phase == "steady":
        # Started BEFORE the entry (so a failed entry is covered): rdp/steady means "over" only
        # once the room was entered, the entry failed, or nothing happened for 15 min.
        entered = bool(status.get("entered_ts")) or status.get("phase") in ("enter-failed", "ended")
        if entered or now - float(status.get("entry_ts") or 0) > ENTRY_GRACE_S:
            return "done"
        return "wait"
    hard_cap = float(status.get("hard_cap_ts") or 0)
    if hard_cap and now >= hard_cap:
        return "exit:hard cap"
    why = ""
    box_until = float(status.get("box_until_ts") or 0)
    if box_until and now >= box_until + WATCHDOG_GRACE_S:
        variant = status.get("variant", "a variant")
        why = (
            "the checks box expired"
            if status.get("phase") == "checks"
            else f"{variant}'s box expired"
        )
    elif hb_age >= HEARTBEAT_STALE_S:
        why = f"runner heartbeat stale ({hb_age / 60:.0f} min)"
    if not why:
        return "wait"
    return f"defer:{why} (a human is at the console)" if human else f"exit:{why}"


def watchdog_exit(why: str) -> None:
    save_status(watchdog=f"FIRED: {why}", watchdog_ts=time.time())
    say(f"WATCHDOG EXIT: {why}")
    pid = int(load_status().get("runner_pid") or 0)
    if pid and pid != os.getpid():
        with contextlib.suppress(ProcessLookupError, PermissionError):
            os.kill(pid, signal.SIGTERM)
            say(f"runner {pid}: SIGTERM")
    running = subprocess.run(
        ["docker", "ps", "--filter", f"name=^{GAMESTREAM}$", "--format", "{{.Names}}"],
        capture_output=True, text=True, check=False,
    ).stdout.strip()  # fmt: skip
    if running != GAMESTREAM:
        say("gamestream is stopped (a guard breach?): a guarded start so /cancel can be sent")
        subprocess.run(
            ["python3", "scripts/guarded_build.py", "--sustain", "30", "--spike", "25",
             "start:gamestream@30"], cwd=REPO, check=False, timeout=600,
        )  # fmt: skip
    backend, phase, _ = lock_state()
    args = ["to-rdp", "--recover"] if (backend, phase) == ("rdp", "switching") else ["to-rdp"]
    for attempt, cmd in enumerate((args, ["to-rdp", "--recover"]), start=1):
        try:
            res = cb("--wait-lock", "120", *cmd, timeout=TO_RDP_TIMEOUT_S)
            if res.returncode in (0, 3):
                warn = " (Sunshine revert NOT verified: rc 3)" if res.returncode == 3 else ""
                save_status(watchdog=f"FIRED: {why}; RDP restored{warn}", phase="ended")
                say(f"RDP restored by the watchdog{warn}")
                return
        except subprocess.TimeoutExpired:
            say(f"to-rdp attempt {attempt} timed out after {TO_RDP_TIMEOUT_S} s")
        if attempt == 1:
            time.sleep(60)
    save_status(watchdog=f"FIRED: {why}; to-rdp FAILED twice -- operator needed", phase="stuck")
    say("WATCHDOG: to-rdp failed twice. NOT retrying (never loop). Operator: to-rdp --recover")


def cmd_watchdog() -> int:
    say("watchdog up")
    save_status(watchdog="watching", watchdog_pid=os.getpid())
    while True:
        status = load_status()
        try:
            human = human_active(health())
        except OSError:
            human = False
        verdict = decide(time.time(), status, lock_state(), human, heartbeat_age(time.time()))
        if verdict == "done":
            say("lock is rdp/steady: watchdog done")
            save_status(watchdog="done")
            return 0
        if verdict.startswith("exit:"):
            watchdog_exit(verdict[5:])
            return 0
        if verdict.startswith("defer:") and status.get("watchdog") != verdict:
            say(f"watchdog {verdict}")
            save_status(watchdog=verdict)
        time.sleep(15)


WATCHDOG_MARGIN_S = 45 * 60  # beyond the hard cap: its own to-rdp + one --recover, with room


def watchdog_runtime_s(hard_cap_min: float) -> int:
    """The unit's RuntimeMaxSec: it must OUTLIVE the room. A fixed 4 h killed the watchdog at
    00:16:46 on 2026-10-04 while a 6 h room ran on, its box and hard cap unenforced."""
    return int(hard_cap_min * 60 + WATCHDOG_MARGIN_S)


def watchdog_active() -> bool:
    out = subprocess.run(["systemctl", "--user", "is-active", UNIT], capture_output=True,
                         text=True, check=False).stdout.strip()  # fmt: skip
    return out == "active"


def start_watchdog(hard_cap_min: float) -> None:
    subprocess.run(["systemctl", "--user", "reset-failed", f"{UNIT}.service"], check=False,
                   capture_output=True)  # fmt: skip
    cmd = [
        "systemd-run", "--user", "--unit", UNIT, "--collect",
        "-p", f"RuntimeMaxSec={watchdog_runtime_s(hard_cap_min)}",
        "--setenv=TMPDIR=/dev/shm/poring-lab-tmp", "--setenv=PYTHONDONTWRITEBYTECODE=1",
        "--setenv=TZ=Asia/Bangkok",
        f"--setenv=CLEANROOM_DIR={STATE}", f"--working-directory={REPO}",
        PY, str(REPO / "scripts" / "cleanroom.py"), "watchdog",
    ]  # fmt: skip
    res = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if res.returncode != 0:
        raise SystemExit(f"STOP: the watchdog did not start: {res.stderr.strip()}")
    time.sleep(2)
    active = subprocess.run(["systemctl", "--user", "is-active", UNIT], capture_output=True,
                            text=True, check=False).stdout.strip()  # fmt: skip
    if active != "active":
        raise SystemExit(f"STOP: the watchdog unit is {active!r}, not active")
    say(f"watchdog running as the transient unit {UNIT} (survives this session)")


def rearm_minutes(status: dict[str, Any], now: float) -> float | None:
    """The minutes left to an ACTIVE room's hard cap, or None (no room, or the cap has passed)."""
    if status.get("phase") not in ROOM_ACTIVE:
        return None
    left = float(status.get("hard_cap_ts") or 0) - now
    return left / 60 if left > 0 else None


def cmd_rearm() -> int:
    """Restart the watchdog of the active room (2026-10-04: the announced red-alarm test stops it
    and restores it). The hard cap stays ABSOLUTE: the watchdog reads hard_cap_ts from the room's
    status; the unit's RuntimeMaxSec covers the time left plus the margin. The guard timer then
    clears the alarm by itself."""
    if watchdog_active():
        say("the watchdog is already up: nothing to re-arm")
        return 2
    minutes = rearm_minutes(load_status(), time.time())
    if minutes is None:
        say("REFUSED: no active room, or its hard cap has passed")
        return 2
    start_watchdog(minutes)
    say(f"watchdog RE-ARMED for the {minutes:.0f} min left to the hard cap")
    return 0


def stop_watchdog() -> None:
    subprocess.run(["systemctl", "--user", "stop", UNIT], check=False, capture_output=True)
    say("watchdog stopped")


# --- the watchdog is watched (2026-10-04) -------------------------------------------------------
# A transient systemd TIMER runs `cleanroom.py guard` every 60 s while a room runs. A timer is no
# long-running process, so no RuntimeMaxSec can kill it the way it killed the watchdog at 00:16:46.
GUARD_UNIT = "poring-cleanroom-guard"


def guard_alarm(phase: object, watchdog_up: bool) -> bool:
    """The alarm condition: a room is active and its watchdog unit is not running."""
    return phase in ROOM_ACTIVE and not watchdog_up


def cmd_guard() -> int:
    want = guard_alarm(load_status().get("phase"), watchdog_active())
    have = (REPO / "state" / "cleanroom-alarm").exists()
    if want and not have:
        say("GUARD: a room is active and its watchdog is DOWN -> alarm")
        return cb("alarm", "--set", "watchdog_down", timeout=60).returncode
    if have and not want:
        return cb("alarm", "--clear", timeout=60).returncode
    return 0


def start_guard() -> None:
    subprocess.run(["systemctl", "--user", "stop", f"{GUARD_UNIT}.timer"], check=False,
                   capture_output=True)  # fmt: skip
    subprocess.run(["systemctl", "--user", "reset-failed", f"{GUARD_UNIT}.service"], check=False,
                   capture_output=True)  # fmt: skip
    cmd = [
        "systemd-run", "--user", "--unit", GUARD_UNIT, "--on-active=60", "--on-unit-active=60",
        "--setenv=TMPDIR=/dev/shm/poring-lab-tmp", "--setenv=PYTHONDONTWRITEBYTECODE=1",
        "--setenv=TZ=Asia/Bangkok", f"--setenv=CLEANROOM_DIR={STATE}",
        f"--working-directory={REPO}", PY, str(REPO / "scripts" / "cleanroom.py"), "guard",
    ]  # fmt: skip
    res = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if res.returncode != 0:
        raise SystemExit(f"STOP: the guard timer did not start: {res.stderr.strip()}")
    say(f"guard timer {GUARD_UNIT}.timer: checks the watchdog every 60 s")


def stop_guard() -> None:
    subprocess.run(["systemctl", "--user", "stop", f"{GUARD_UNIT}.timer"], check=False,
                   capture_output=True)  # fmt: skip
    if (REPO / "state" / "cleanroom-alarm").exists():
        cb("alarm", "--clear", timeout=60)
    say("guard timer stopped")


# --- runner commands ----------------------------------------------------------------------------


def cmd_preflight() -> int:
    problems: list[str] = []
    backend, phase, _ = lock_state()
    if (backend, phase) != ("rdp", "steady"):
        problems.append(f"lock is {backend}/{phase}, not rdp/steady")
    h = health()
    if h.get("mode") != "ASSIST":
        problems.append(f"mux is {h.get('mode')}, not ASSIST (Batt sets it)")
    if "lease_active" not in h:
        problems.append("the backend lacks /health lease_active (restart it after the code change)")
    status = cb("status", timeout=60)
    if "xfreerdp=1" not in status.stdout or "RESULT AGREE" not in status.stdout:
        problems.append("capture_backend status: not exactly one xfreerdp / not AGREE")
    sys.path.insert(0, str(REPO / "scripts"))
    import ro_agent as r

    if not r.online_chars("gm"):
        problems.append("the GM is not online (online=1 before any in-game input)")
    info = subprocess.run(
        ["docker", "exec", GAMESTREAM, "sh", "-c", "cd /tmp && python3 -m s2spike serverinfo"],
        capture_output=True, text=True, check=False, timeout=60,
    )  # fmt: skip
    if info.returncode != 0 or "PairStatus = 1" not in info.stderr + info.stdout:
        problems.append("s2spike serverinfo: the lab certificate is not paired (PairStatus != 1)")
    if "currentgame = 0" not in info.stderr + info.stdout:
        problems.append("Sunshine already runs an app (currentgame != 0): cancel it first")
    # V3b (PAINT=bus) needs the frame bus: gamestream writes it, the backend reads it (compose).
    mounts = {
        GAMESTREAM: "test -d /framebus && test -w /framebus",
        "poring-lab-backend-1": "test -d /framebus && ! test -w /framebus",
    }
    for container, test in mounts.items():
        res = subprocess.run(["docker", "exec", container, "sh", "-c", test],
                             capture_output=True, check=False)  # fmt: skip
        if res.returncode != 0:
            problems.append(f"{container}: /framebus missing or wrongly writable (recreate it)")
    if "framebus" not in h:
        problems.append("the backend lacks /health framebus (restart it after the code change)")
    selftest = subprocess.run(
        ["docker", "exec", GAMESTREAM, "sh", "-c", "cd /tmp && python3 -m s2spike selftest"],
        capture_output=True, text=True, check=False, timeout=60,
    )  # fmt: skip
    if selftest.returncode != 0:
        problems.append("s2spike selftest failed (the gamestream image?)")
    say(f"baseline shot: {shot('baseline-rdp')}")
    for p in problems:
        say(f"PREFLIGHT: {p}")
    say("PREFLIGHT OK" if not problems else f"PREFLIGHT FAILED ({len(problems)})")
    return 0 if not problems else 1


def cmd_start(hard_cap_min: float) -> int:
    if load_status().get("phase") in ("entered", "variant", "streaming", "checks"):
        raise SystemExit("STOP: a clean room is already running (status.json)")
    now = time.time()
    heartbeat()
    new_room_status(phase="starting", entry_ts=now, hard_cap_ts=now + hard_cap_min * 60,
                    runner_pid=os.getpid(), variant=None, box_until_ts=0, history=[])  # fmt: skip
    start_watchdog(hard_cap_min)
    start_guard()
    cap_ts = str(int(now + hard_cap_min * 60))  # shown on the console (state/cleanroom)
    res = cb("to-console", "--yes-tscon", "--cleanroom", "--hard-cap", cap_ts, timeout=300)
    if res.returncode != 0:
        say("to-console failed: the watchdog's next check (or to-rdp --recover) returns RDP")
        save_status(phase="enter-failed")
        return 1
    save_status(phase="entered", entered_ts=time.time())
    cap = time.strftime("%H:%M", time.localtime(now + hard_cap_min * 60))
    say(f"ENTERED the clean room; hard cap {cap}")
    return 0


def cmd_variant(variant: str, box_min: float | None, knobs: list[str] | None = None) -> int:
    box = (box_min or BOXES_MIN[variant]) * 60
    t0 = time.time()
    heartbeat()
    status = save_status(phase="variant", variant=variant, box_until_ts=t0 + box,
                         runner_pid=os.getpid())  # fmt: skip
    box_until = str(int(t0 + box))
    stop = {"flag": False}
    signal.signal(signal.SIGTERM, lambda *_: stop.update(flag=True))
    result: dict[str, Any] = {"variant": variant, "knobs": knobs or [], "started": utc_now()}
    since = utc_now()
    knob_args = [a for k in knobs or [] for a in ("--knob", k)]
    stream_args = ("stream", "--variant", variant, *knob_args, "--box-until", box_until)
    if cb(*stream_args, timeout=120).returncode != 0:
        result["verdict"] = "stream-refused"
        return finish(status, result)
    first = wait_picture(FIRST_PICTURE_S, stop)
    result["first_picture_s"] = first
    if first is None:
        result["verdict"] = "black"
        result["diagnostics"] = diagnostics(variant, since)
        cb("hold", timeout=180)
        return finish(status, result)
    say(f"{variant}: FIRST PICTURE after {first:.1f} s")
    result["steady"] = watch_steady(STEADY_S, stop)
    result["frames"] = [shot(f"{variant}-first")]
    if not result["steady"]["ok"] or stop["flag"]:
        result["verdict"] = "unsteady"
        cb("hold", timeout=180)
        return finish(status, result)
    cb("hold", timeout=180)
    heartbeat()
    if cb(*stream_args, timeout=120).returncode != 0:
        result["verdict"] = "restream-refused"
        return finish(status, result)
    again = wait_picture(FIRST_PICTURE_S, stop)
    result["second_picture_s"] = again
    result["verdict"] = "reliable" if again is not None else "first-only"
    if again is None:
        cb("hold", timeout=180)
    else:
        result["frames"].append(shot(f"{variant}-second"))
    result["v3_stats"] = v3_stats() if variant in S2_CLIENTS else None
    return finish(status, result)


def cmd_checks(box_min: float) -> int:
    """A box for the work after a reliable variant (bench, functional checks): the watchdog runs
    the clean to-rdp at its end + 5 min, like a variant's."""
    status = load_status()
    if status.get("phase") not in ("streaming", "entered", "checks"):
        raise SystemExit(f"STOP: no clean room to check in (phase {status.get('phase')})")
    until = time.time() + box_min * 60
    heartbeat()
    save_status(phase="checks", box_until_ts=until)
    say(f"checks box until {time.strftime('%H:%M', time.localtime(until))}")
    return 0


def finish(status: dict[str, Any], result: dict[str, Any]) -> int:
    result["ended"] = utc_now()
    history = [*status.get("history", []), result]
    streaming = result.get("verdict") == "reliable"
    save_status(phase="streaming" if streaming else "entered", history=history, box_until_ts=0)
    heartbeat()
    print(json.dumps(result, indent=1))
    return 0 if streaming else 2


def wait_picture(timeout: float, stop: dict[str, bool]) -> float | None:
    t0 = time.monotonic()
    while time.monotonic() - t0 < timeout and not stop["flag"]:
        heartbeat()
        if is_picture(frame_stats()):
            return time.monotonic() - t0
        time.sleep(2)
    return None


def watch_steady(seconds: float, stop: dict[str, bool]) -> dict[str, Any]:
    samples: list[dict[str, float]] = []
    t0 = time.monotonic()
    while time.monotonic() - t0 < seconds and not stop["flag"]:
        heartbeat()
        samples.append(frame_stats())
        time.sleep(2)
    black = sum(not is_picture(s) for s in samples)
    return {"ok": bool(samples) and black == 0, "samples": len(samples), "black_samples": black}


# Moonlight-qt's threads: comm, kernel wait channel, state (no ptrace needed: ptrace_scope is 1).
THREADS = (
    'for p in /proc/[0-9]*; do [ "$(cat $p/comm 2>/dev/null)" = moonlight ] || continue; '
    'for t in $p/task/*; do echo "$(cat $t/comm) $(cat $t/wchan) $(cut -d" " -f3 $t/stat)"; '
    "done; done"
)


def diagnostics(variant: str, since: str) -> dict[str, Any]:
    out: dict[str, Any] = {"frame": shot(f"{variant}-black")}
    logs = gamestream_logs(since)
    wanted = ("first video", "decoder", "Received", "error", "Error", "terminated", "s2spike",
              "openbox", "gamestream:")  # fmt: skip
    keep = [line for line in logs.splitlines() if any(k in line for k in wanted)]
    out["log_tail"] = keep[-30:]
    (STATE / "frames").mkdir(parents=True, exist_ok=True)
    (STATE / f"{variant}-gamestream.log").write_text(logs)
    if variant in ("V1", "V2", "V1gdb"):
        wchan = subprocess.run(
            ["docker", "exec", GAMESTREAM, "sh", "-c",
             THREADS],
            capture_output=True, text=True, check=False, timeout=30,
        ).stdout  # fmt: skip
        out["threads"] = wchan.strip().splitlines()[:40]
    if variant in S2_CLIENTS:
        out["v3_stats"] = v3_stats()
    return out


def v3_stats() -> Any:
    res = subprocess.run(["docker", "exec", GAMESTREAM, "cat", "/tmp/s2spike/v3-stats.json"],
                         capture_output=True, text=True, check=False)  # fmt: skip
    with contextlib.suppress(ValueError):
        return json.loads(res.stdout)
    return None


def cmd_end() -> int:
    backend, phase, reason = lock_state()
    if backend == "console" and phase == "steady":
        cb("hold", timeout=180)
    res = cb("to-rdp", timeout=TO_RDP_TIMEOUT_S)
    checks = exit_checks()
    stop_watchdog()
    stop_guard()
    save_status(phase="ended", exit_checks=checks, to_rdp_rc=res.returncode)
    print(json.dumps(checks, indent=1))
    return 0 if res.returncode == 0 and all(checks.values()) else 1


def exit_checks() -> dict[str, bool]:
    status = cb("status", timeout=60).stdout
    h = health()
    sys.path.insert(0, str(REPO / "scripts"))
    import ro_agent as r

    wm = subprocess.run(["docker", "exec", GAMESTREAM, "sh", "-c",
                         'for p in /proc/[0-9]*; do [ "$(cat $p/comm 2>/dev/null)" = openbox ] '
                         "&& echo wm; done; true"], capture_output=True, text=True,
                        check=False).stdout  # fmt: skip
    prop = subprocess.run(["docker", "exec", "poring-lab-desktop-1", "xprop", "-root",
                           "_NET_SUPPORTING_WM_CHECK"], capture_output=True, text=True,
                          check=False).stdout  # fmt: skip
    backend, phase, _ = lock_state()
    return {
        "lock rdp/steady": (backend, phase) == ("rdp", "steady"),
        "exactly one xfreerdp": "xfreerdp=1" in status,
        "host/containers/health agree": "RESULT AGREE" in status,
        "game display ok": (h.get("game_display") or {}).get("state") == "ok",
        "mux ASSIST": h.get("mode") == "ASSIST",
        "GM online": bool(r.online_chars("gm")),
        "no openbox": "wm" not in wm,
        "no _NET_SUPPORTING_WM_CHECK": "window id" not in prop,
    }


ROOM_ACTIVE = ("entered", "variant", "streaming", "checks")


def cmd_heartbeat(watchdog_up: bool) -> int:
    """A heartbeat only means something while a watchdog enforces the room: refuse (rc 2, loud) when
    a room is active and the watchdog is down, so no loop keeps an unguarded room alive
    (2026-10-04: one did, for 5 hours)."""
    st = load_status()
    if st.get("phase") in ROOM_ACTIVE and not watchdog_up:
        say("WATCHDOG DOWN while a room is active: heartbeat REFUSED -- run `cleanroom.py end`")
        return 2
    save_status(box_until_ts=st.get("box_until_ts", 0))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("preflight")
    st = sub.add_parser("start")
    st.add_argument("--hard-cap-min", type=float, default=180)
    va = sub.add_parser("variant")
    va.add_argument("variant", choices=sorted(BOXES_MIN.keys() - {"checks"}))
    va.add_argument("--box-min", type=float)
    va.add_argument("--knob", action="append", help="S2 only: an experiment knob K=V")
    ch = sub.add_parser("checks")
    ch.add_argument("--box-min", type=float, default=BOXES_MIN["checks"])
    for name in ("hold", "heartbeat", "status", "end", "watchdog", "guard", "rearm"):
        sub.add_parser(name)
    args = ap.parse_args()
    if args.cmd == "watchdog":
        return cmd_watchdog()
    if args.cmd == "guard":
        return cmd_guard()
    heartbeat()
    if args.cmd == "preflight":
        return cmd_preflight()
    if args.cmd == "start":
        return cmd_start(args.hard_cap_min)
    if args.cmd == "variant":
        return cmd_variant(args.variant, args.box_min, args.knob)
    if args.cmd == "checks":
        return cmd_checks(args.box_min)
    if args.cmd == "hold":
        return cb("hold", timeout=180).returncode
    if args.cmd == "end":
        return cmd_end()
    if args.cmd == "rearm":
        return cmd_rearm()
    if args.cmd == "heartbeat":
        return cmd_heartbeat(watchdog_active())
    print(json.dumps(load_status(), indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
