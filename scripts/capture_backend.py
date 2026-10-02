#!/usr/bin/env python3
"""The capture-backend lock (ADR-0009): the ONLY writer, and the handovers between RDP and console.

One Windows session, one display path at a time. The lock file ``state/capture-backend`` (KEY=word,
see poring_backend.capture_lock) is bind-mounted read-only into desktop, backend and gamestream:
rdp-loop.sh connects only while it says ``rdp``; gamestream-loop.sh streams only while it says
``console``; both also refuse while the OTHER client's window is on the display.

    capture_backend.py status            # host file vs containers vs /health; 1 = mismatch
    capture_backend.py init              # create the lock as rdp/steady (idempotent)
    capture_backend.py drill [--hold-s 20]
        Live lock test without Sunshine or tscon: lock -> console, TERM xfreerdp, prove that NO
        client reconnects for --hold-s, lock -> rdp, prove exactly one client comes back.
    capture_backend.py to-rdp [--recover]
        Console -> RDP (or recover from any half-done handover): lock -> rdp/switching, TERM every
        Moonlight client, revive rdp-loop if it idles, exactly one xfreerdp, lock -> steady.
    capture_backend.py to-console        # needs gamestream + Sunshine (Part A, 2026-10-02)
    capture_backend.py pair PIN          # likewise

Writes are atomic (rename) and read back on the host AND inside every running container before a
step counts as done (CLAUDE.md: read back every write). Scratch never goes to host /tmp.
"""

import argparse
import json
import os
import re
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "services" / "backend" / "src"))
sys.path.insert(0, str(REPO / "packages" / "poring_env" / "src"))
from poring_backend.capture_lock import LOCK_NAME, format_lock, parse_lock  # noqa: E402

STATE = Path(os.environ.get("LAB_STATE_HOST_DIR", REPO / "state"))
DESKTOP, BACKEND, GAMESTREAM = (
    "poring-lab-desktop-1",
    "poring-lab-backend-1",
    "poring-lab-gamestream-1",
)
OWNER = "capture_backend"
NO_MOUNT = "<no /lab-state mount: recreate this container>"
HEALTH = "http://{ip}:8000/health"


class Stop(SystemExit):
    def __init__(self, msg: str) -> None:
        super().__init__(f"STOP: {msg}")


def say(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def sh(*cmd: str, check: bool = False, timeout: float = 30) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, capture_output=True, text=True, check=check, timeout=timeout)


# --- the lock file --------------------------------------------------------------------------------


def lock_file() -> Path:
    return STATE / LOCK_NAME


def raw_seq(text: str) -> int:
    match = re.search(r"^SEQ=(\d+)$", text, re.M)
    return int(match.group(1)) if match else 0


def read_host() -> tuple[str, int, str]:
    """(backend, seq, text) from the host file; backend 'rdp' if absent, 'hold' if unreadable."""
    path = lock_file()
    if not path.exists():
        return "rdp", 0, ""
    text = path.read_text(encoding="ascii")
    return parse_lock(text).backend, raw_seq(text), text


def write_lock(backend: str, phase: str, reason: str) -> str:
    """Atomic write + host read-back; returns the body. SEQ always increases."""
    STATE.mkdir(exist_ok=True)
    _, seq, _ = read_host()
    body = format_lock(backend, seq + 1, phase, owner=OWNER, since=int(time.time()), reason=reason)
    tmp = STATE / f".{LOCK_NAME}.tmp"
    tmp.write_text(body, encoding="ascii")
    tmp.replace(lock_file())
    if lock_file().read_text(encoding="ascii") != body:
        raise Stop("lock read-back on the host differs from what was written")
    say(f"lock -> {backend}/{phase} seq={seq + 1} ({reason})")
    return body


def running(container: str) -> bool:
    out = sh("docker", "ps", "--filter", f"name=^{container}$", "--format", "{{.Names}}").stdout
    return out.strip() == container


def container_view(container: str) -> str | None:
    """The lock as the container sees it ('' = no file, None = container not running)."""
    if not running(container):
        return None
    res = sh(
        "docker", "exec", container, "sh", "-c",
        f"[ -d /lab-state ] || exit 3; cat /lab-state/{LOCK_NAME} 2>/dev/null; true",
    )  # fmt: skip
    if res.returncode == 3:
        return NO_MOUNT
    return res.stdout


def verify_everywhere(body: str) -> None:
    for container in (DESKTOP, BACKEND, GAMESTREAM):
        view = container_view(container)
        if view is None:
            continue
        if view != body:
            raise Stop(f"{container} sees a different lock (stale mount? recreate it): {view!r}")
    say("lock read back identically on the host and in every running container")


def backend_ip() -> str:
    res = sh(
        "docker", "inspect", "-f", "{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}",
        BACKEND,
    )  # fmt: skip
    return res.stdout.strip() or "127.0.0.1"


def health() -> dict[str, object]:
    with urllib.request.urlopen(HEALTH.format(ip=backend_ip()), timeout=5) as resp:
        data: dict[str, object] = json.loads(resp.read())
    return data


# --- the clients ----------------------------------------------------------------------------------

COUNT = (
    'n=0; for p in /proc/[0-9]*; do case "$(cat $p/comm 2>/dev/null)" in {names}) n=$((n+1));; '
    "esac; done; echo $n"
)
TERM = (
    'for p in /proc/[0-9]*; do case "$(cat $p/comm 2>/dev/null)" in {names}) '
    'kill -TERM "${{p#/proc/}}";; esac; done; true'
)
RDP_NAMES, STREAM_NAMES = "xfreerdp|xfreerdp3", "moonlight|Moonlight*|AppRun*"


def count(container: str, names: str) -> int:
    if not running(container):
        return 0
    res = sh("docker", "exec", container, "sh", "-c", COUNT.format(names=names))
    return int(res.stdout.strip() or 0)


def term_until_zero(container: str, names: str, quiet_s: float = 5, timeout: float = 90) -> None:
    """TERM every matching client until none has existed for ``quiet_s`` seconds."""
    deadline = time.monotonic() + timeout
    zero_since: float | None = None
    while time.monotonic() < deadline:
        if count(container, names) == 0:
            zero_since = zero_since or time.monotonic()
            if time.monotonic() - zero_since >= quiet_s:
                say(f"{container}: no {names} client for {quiet_s:.0f}s")
                return
        else:
            zero_since = None
            sh("docker", "exec", container, "sh", "-c", TERM.format(names=names))
        time.sleep(0.5)
    raise Stop(f"{container}: a {names} client kept coming back for {timeout:.0f}s")


def wait_log(container: str, pattern: str, since: str, timeout: float) -> str:
    deadline = time.monotonic() + timeout
    rx = re.compile(pattern)
    while time.monotonic() < deadline:
        logs = sh("docker", "logs", "--since", since, container).stderr
        logs += sh("docker", "logs", "--since", since, container).stdout
        for line in logs.splitlines():
            if rx.search(line):
                return line
        time.sleep(1)
    raise Stop(f"{container}: no log line matching {pattern!r} within {timeout:.0f}s")


def utc_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def revive_rdp_loop_if_idle(since: str) -> None:
    """rdp-loop's idle_forever (auth/licensing exits) never re-reads the lock: restart the program
    through supervisord -- the same path as scripts/rdp_reconnect.sh --reload (0 clients first)."""
    logs = sh("docker", "logs", "--since", since, DESKTOP).stderr
    if "NOT retrying" not in logs:
        return
    say("rdp-loop is idling (NOT retrying): restarting it through supervisord")
    sup = ["supervisorctl", "-c", "/etc/supervisor/supervisord.conf"]
    sh("docker", "exec", DESKTOP, *sup, "stop", "rdp")
    term_until_zero(DESKTOP, RDP_NAMES, quiet_s=2)
    sh("docker", "exec", DESKTOP, *sup, "start", "rdp")


# --- commands -------------------------------------------------------------------------------------


def cmd_status() -> int:
    backend, seq, text = read_host()
    print(f"host file      : {lock_file()}  backend={backend} seq={seq}")
    ok = True
    for container in (DESKTOP, BACKEND, GAMESTREAM):
        view = container_view(container)
        if view is None:
            print(f"{container:<24}: not running")
            continue
        same = view == text
        ok &= same
        print(f"{container:<24}: {'same' if same else 'DIFFERENT: ' + repr(view[:80])}")
    try:
        lock = health().get("capture_backend")
        print(f"/health        : {lock}")
        if isinstance(lock, dict) and (lock.get("backend"), lock.get("seq")) != (backend, seq):
            ok = ok and not text  # no file yet: /health reports the default rdp/0
    except OSError as exc:
        print(f"/health        : unreachable ({exc})")
    print(
        f"clients        : xfreerdp={count(DESKTOP, RDP_NAMES)} "
        f"moonlight={count(GAMESTREAM, STREAM_NAMES)}"
    )
    print("RESULT", "AGREE" if ok else "MISMATCH")
    return 0 if ok else 1


def cmd_init() -> int:
    backend, _, text = read_host()
    if text and backend in ("rdp", "console"):
        say(f"lock exists ({backend}); nothing to do")
        verify_everywhere(text)
        return 0
    verify_everywhere(write_lock("rdp", "steady", "init"))
    return 0


def cmd_drill(hold_s: float) -> int:
    backend, _, _ = read_host()
    if backend != "rdp":
        raise Stop(f"drill needs the lock at rdp (it is {backend})")
    if count(DESKTOP, RDP_NAMES) != 1:
        raise Stop("drill needs exactly one xfreerdp client to start from")
    since = utc_now()
    body = write_lock("console", "switching", "drill")
    verify_everywhere(body)
    seq = raw_seq(body)
    term_until_zero(DESKTOP, RDP_NAMES)
    line = wait_log(DESKTOP, rf"capture-backend console seq={seq}: holding", since, 60)
    say(f"rdp-loop obeyed: {line.split('rdp-loop: ', 1)[-1]}")
    deadline = time.monotonic() + hold_s
    while time.monotonic() < deadline:
        if count(DESKTOP, RDP_NAMES):
            raise Stop("an xfreerdp client reconnected while the lock said console")
        time.sleep(1)
    say(f"no RDP reconnect for {hold_s:.0f}s under the console lock")
    since = utc_now()
    body = write_lock("rdp", "switching", "drill-back")
    verify_everywhere(body)
    wait_log(DESKTOP, rf"capture-backend rdp seq={raw_seq(body)}: resuming", since, 60)
    wait_log(DESKTOP, r"connecting to ", since, 60)
    time.sleep(8)
    clients = count(DESKTOP, RDP_NAMES)
    if clients != 1:
        raise Stop(f"{clients} xfreerdp clients after the drill (expected exactly 1)")
    verify_everywhere(write_lock("rdp", "steady", "drill-done"))
    say("DRILL PASS: hold obeyed, no reconnect, exactly one client back")
    return 0


def cmd_to_rdp(recover: bool) -> int:
    backend, _, _ = read_host()
    if backend == "rdp" and not recover:
        say("already rdp (use --recover to re-run the handover steps anyway)")
        return 0
    since = utc_now()
    body = write_lock("rdp", "switching", "recover" if recover else "to-rdp")
    verify_everywhere(body)
    term_until_zero(GAMESTREAM, STREAM_NAMES, quiet_s=3)
    revive_rdp_loop_if_idle("24h")
    wait_log(DESKTOP, r"connecting to ", since, 120)
    time.sleep(8)
    clients = count(DESKTOP, RDP_NAMES)
    if clients != 1:
        raise Stop(f"{clients} xfreerdp clients (expected exactly 1)")
    verify_everywhere(write_lock("rdp", "steady", "to-rdp-done"))
    say("RDP mode: exactly one xfreerdp client")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status")
    sub.add_parser("init")
    drill = sub.add_parser("drill")
    drill.add_argument("--hold-s", type=float, default=20.0)
    to_rdp = sub.add_parser("to-rdp")
    to_rdp.add_argument("--recover", action="store_true")
    sub.add_parser("to-console")
    pair = sub.add_parser("pair")
    pair.add_argument("pin")
    args = ap.parse_args()
    if args.cmd == "status":
        return cmd_status()
    if args.cmd == "init":
        return cmd_init()
    if args.cmd == "drill":
        return cmd_drill(args.hold_s)
    if args.cmd == "to-rdp":
        return cmd_to_rdp(args.recover)
    raise Stop(f"{args.cmd}: not available until gamestream + Sunshine exist (Part A)")


if __name__ == "__main__":
    sys.exit(main())
