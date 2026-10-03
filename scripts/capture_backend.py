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
        Console -> RDP (or recover from any half-done handover). From console: lock ->
        console/switching, END THE STREAM CLEANLY (Moonlight's `quit` -> Sunshine /cancel; TERM
        only as a reported fallback), wait while the session is still on the console so Sunshine
        can revert its display settings, then lock -> rdp/switching, exactly one xfreerdp, lock ->
        steady, and check Sunshine's log for a pending revert (rc 3 + the remedy if pending).
    capture_backend.py pair PIN          # one-time pairing (private display; ok in rdp)
    capture_backend.py to-console [--yes-tscon] [--external]
        RDP -> console: preflight; with --yes-tscon (after Batt's OK): focus + verify poring-lab's
        own console (open and visible), THEN lock -> console/switching, type `schtasks /run` of
        the SYSTEM task that tscons poring-lab's session (delayed 10 s), TERM xfreerdp until none
        for 5 s, wait out the tscon, lock -> console/steady (only now may gamestream stream), and
        wait for Moonlight's first decoded video packet. --external (S2 step 0): stop after tscon
        with the lock at console/switching, so the lab client holds and an external one streams.
        --cleanroom (Batt, 2026-10-03): the same stop, REASON `cleanroom`, for the clean-room
        experiment: the session stays on the console while lab-client variants take turns:
    capture_backend.py stream --variant V1|V1gdb|V2|V3
        Clean room only (lock console + REASON cleanroom*, phase switching): refuses unless NO lab
        client runs in gamestream (one client at a time, enforced), writes the whitelisted variant
        file `state/gamestream-variant` (CLIENT/WM/GDB_AFTER_S), then console/steady.
    capture_backend.py hold
        Clean room only: console/switching (REASON cleanroom-hold), then end the stream through
        Sunshine (/cancel, as to-rdp does) and reset the variant file. The session stays on the
        console; to-rdp ends the clean room.

Every command that writes holds an EXCLUSIVE flock (/dev/shm, never state/), so the clean-room
runner and its watchdog can never write the lock at the same time (--wait-lock S, default 30).

Writes are atomic (rename) and read back on the host AND inside every running container before a
step counts as done (CLAUDE.md: read back every write). Scratch never goes to host /tmp.
"""

import argparse
import contextlib
import fcntl
import json
import os
import re
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import numpy as np
    from numpy.typing import NDArray

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
RDP_NAMES, STREAM_NAMES = "xfreerdp|xfreerdp3", "moonlight|Moonlight*|AppRun*|s2spike*"


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
    from_console = backend == "console"
    if from_console:
        # End the stream while the session is still on the console, so Sunshine can revert its
        # display settings (it can't once RDP holds the session), THEN let rdp-loop connect.
        verify_everywhere(write_lock("console", "switching", "to-rdp"))
        end = quit_stream()
        if end == "unclean":
            say(
                "UNCLEAN END: Sunshine showed no session end, so its display revert will probably "
                "stay pending (the next console session reverts it)"
            )
        say(f"{SUNSHINE_REVERT_S} s for Sunshine to revert while the session is on the console")
        time.sleep(SUNSHINE_REVERT_S)
    ensure_no_wm()  # BEFORE the lock says rdp: rdp-loop wakes within 1 s and has no WM check
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
    write_variant("V1")  # a later plain to-console streams moonlight-qt, no WM, no gdb
    if not from_console:
        return 0
    verdict = verify_sunshine_revert()
    if verdict == "OK":
        say("Sunshine reverted its display settings (no pending retries in its log)")
        return 0
    say(
        f"SUNSHINE REVERT {verdict}: "
        + (
            "Sunshine is still retrying ('API is available: false' every 5 s) -- the console "
            "display topology is still the stream's (VDD only, the Samsung dark). The next console "
            "session reverts it; or Batt logs in at the Dell."
            if verdict == "PENDING"
            else "could not read Sunshine's log through poring-lab's console (see above); check "
            "it by hand: Get-Content 'C:\\Program Files\\Sunshine\\config\\sunshine.log' -Tail 5"
        )
    )
    return 3


SUNSHINE_PORTS = (47984, 47989, 48010)
MOONLIGHT_CONF = "/home/desk/.config/Moonlight Game Streaming Project/Moonlight.conf"
TSCON_DELAY_S = 10  # the typed command waits so its line completes before RDP drops
# tscon needs privilege: from poring-lab's own console it is "Access is denied" (5), from Batt's
# elevated one it wants poring-lab's password (1326) (2026-10-02). Batt's one-time SYSTEM task runs
# `C:\Program Files\PoringLab\to-console.ps1` (admin-only folder), which finds poring-lab's session
# and tscons it; poring-lab may only RUN the task (read+execute ACE). docs/client/rathena-client.md.
TOCONSOLE_TASK = r"\PoringLab\PoringLab-ToConsole"
TSCON = f'Start-Sleep {TSCON_DELAY_S}; schtasks /run /tn "{TOCONSOLE_TASK}"'
# After the stream ends, Sunshine reverts its display settings (the Samsung back on), but only
# while the session is still on the console: from RDP its display API is unavailable and it retries
# every 5 s indefinitely (2026-10-02). 8 s after a TERM was not enough; 15 s after a clean quit is
# the starting value, to be tuned from the first measured handover.
SUNSHINE_REVERT_S = 15

# Ending the stream CLEANLY (2026-10-02).
# - A TERM-killed Moonlight leaves the app running on Sunshine, so every later connect RESUMED that
#   stale session (<resume>1</resume>).
# - Sunshine noticed the end only after the session had left the console, so its display revert
#   stayed pending.
# - Moonlight's own `quit` CLI asks Sunshine to /cancel the app. It runs on a PRIVATE Xvfb (:51)
#   inside gamestream, like gamestream-pair (:50): the paired key never leaves the gamestream-state
#   volume and nothing appears on the lab display.
# - It is inline here so it works with the current image (no build). Like `pair`, it may linger on
#   its dialog, so success is the streaming client's own log, not the exit code.
QUIT_TIMEOUT_S = 30
STREAM_EXIT_S = 20
QUIT_STREAM = (
    "set -u; gamestream-unpack >/dev/null; mkdir -p /tmp/.X11-unix; "
    "Xvfb :51 -nolisten tcp -screen 0 800x600x24 >/tmp/xvfb51.log 2>&1 & x=$!; "
    "for i in $(seq 1 50); do [ -S /tmp/.X11-unix/X51 ] && break; sleep 0.1; done; "
    'DISPLAY=:51 timeout {t} /tmp/moonlight/AppRun quit "$WIN_HOST"; rc=$?; kill $x; exit $rc'
)
# What the STREAMING client logs once Sunshine ends the session (it sees no TERM before this).
STREAM_END_RX = r"Connection terminated|Quit event received|Stopping input stream"


def quit_stream() -> str:
    """End the console stream through Sunshine, never by killing the client first.
    "clean" = Sunshine ended the session and the client left by itself; "client-killed" = the
    session ended but the client needed a TERM; "unclean" = no sign Sunshine ended it (TERM);
    "external" = no lab client was streaming (an external client's session, e.g. S2 step 0): the
    /cancel is sent anyway, and only the revert check afterwards can tell."""
    since = utc_now()
    lab_streaming = count(GAMESTREAM, STREAM_NAMES) > 0
    try:
        res = sh(
            "docker", "exec", GAMESTREAM, "sh", "-c", QUIT_STREAM.format(t=QUIT_TIMEOUT_S),
            timeout=QUIT_TIMEOUT_S + 15,
        )  # fmt: skip
        last = (res.stdout + res.stderr).strip().splitlines()[-1:]
        say(f"moonlight quit: rc={res.returncode} {last[0][:120] if last else ''}".rstrip())
    except subprocess.TimeoutExpired:
        say(f"moonlight quit: no answer within {QUIT_TIMEOUT_S + 15} s")
    if not lab_streaming:
        say(
            "no lab client was streaming (an external client, or the client had already exited): "
            "the /cancel covers the host's session either way"
        )
        return "external"
    try:
        line = wait_log(GAMESTREAM, STREAM_END_RX, since, STREAM_EXIT_S)
        say(f"Sunshine ended the session: {line.strip()[-100:]}")
        ended = True
    except Stop:
        ended = False
    deadline = time.monotonic() + STREAM_EXIT_S
    while count(GAMESTREAM, STREAM_NAMES) and time.monotonic() < deadline:
        time.sleep(1)
    if count(GAMESTREAM, STREAM_NAMES) == 0:
        return "clean" if ended else "unclean"
    say("the streaming client did not leave by itself: TERM (reported, not the normal path)")
    term_until_zero(GAMESTREAM, STREAM_NAMES, quiet_s=3)
    return "client-killed" if ended else "unclean"


# The revert is checked AFTER the session is back on RDP: while it is on the console the only view
# is the stream being ended. The check is read-only; its answer is a coloured block in poring-lab's
# console (pixels in), red if Sunshine's newest revert line is a recent "API is available: false"
# retry, green otherwise.
SUNSHINE_LOG = r"C:\Program Files\Sunshine\config\sunshine.log"
REVERT_CHECK = (
    f"$l = Get-Content '{SUNSHINE_LOG}' -Tail 60 | Select-String 'revert applied display device' "
    "| Select -Last 1; $p = $false; if ($l) { $t = [datetime]::ParseExact("
    "$l.Line.Substring(1, 23), 'yyyy-MM-dd HH:mm:ss.fff', $null); "
    "$p = ($l.Line -match 'available: false') -and "
    "(((Get-Date) - $t).TotalSeconds -lt 20) }; if ($p) { Write-Host (' ' * 40) -BackgroundColor "
    "DarkRed } else { Write-Host (' ' * 40) -BackgroundColor DarkGreen }"
)
MARKER_MIN_RUN = 150  # px: 40 cells of background colour; game pixels never reach the console area


def classify_marker(rgb: "NDArray[np.uint8]") -> str | None:
    """The bottom-most solid red or green run (>= MARKER_MIN_RUN px) in an RGB region:
    "PENDING" (red), "OK" (green) or None (no marker yet)."""
    import numpy as np

    r, g, b = (rgb[..., i].astype(np.int16) for i in range(3))
    masks = {
        "PENDING": (r > 150) & (g < 70) & (b < 80),  # Campbell DarkRed (197,15,31)
        "OK": (g > 120) & (r < 80) & (b < 80),  # Campbell DarkGreen (19,161,14)
    }
    best: tuple[int, str] | None = None
    for verdict, mask in masks.items():
        for y in range(mask.shape[0] - 1, -1, -1):
            row = np.concatenate(([0], mask[y].astype(np.int8), [0]))
            edges = np.flatnonzero(np.diff(row))
            if len(edges) and (edges[1::2] - edges[::2]).max() >= MARKER_MIN_RUN:
                if best is None or y > best[0]:
                    best = (y, verdict)
                break
    return best[1] if best else None


def verify_sunshine_revert(timeout: float = 15) -> str:
    """Sunshine's revert state: OK, PENDING, or UNVERIFIED (no ASSIST, no console, no marker)."""
    sys.path.insert(0, str(REPO / "scripts"))
    import ro_agent as r

    try:
        with r.session("capture-backend") as (agent, screen):
            ox, oy = r.focus_console(agent, screen)
            r.console_type(agent, screen, "cls; " + REVERT_CHECK)
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                time.sleep(1)
                frame = screen.full()
                region = frame[oy + 20 : oy + 620, max(0, ox - 20) : ox + 1100, 2::-1]
                verdict = classify_marker(region)
                if verdict:
                    return verdict
            return "UNVERIFIED"
    except (r.Stop, Stop) as exc:
        say(f"revert check not run: {exc}")
        return "UNVERIFIED"


def win_host() -> str:
    for line in (REPO / ".env").read_text().splitlines():
        if line.startswith("WIN_HOST="):
            return line.split("=", 1)[1].strip()
    raise Stop("WIN_HOST is not set in .env")


def sunshine_reachable(host: str) -> bool:
    import socket

    for port in SUNSHINE_PORTS:
        try:
            with socket.create_connection((host, port), timeout=3):
                pass
        except OSError:
            return False
    return True


# A host Moonlight has PAIRED with stores the server's certificate ([hosts] N\srvcert). The
# [General] `certificate` is Moonlight's OWN identity, written on first run whether or not anything
# is paired -- the old check grepped that and could say "paired" with nothing paired (2026-10-02).
PAIRED_HOST_RX = r"^[0-9]+\\srvcert=@ByteArray\(-----BEGIN CERTIFICATE"


def paired() -> bool:
    res = sh("docker", "exec", GAMESTREAM, "grep", "-q", "-E", PAIRED_HOST_RX, MOONLIGHT_CONF)
    return res.returncode == 0


def cmd_pair(pin: str) -> int:
    if not re.fullmatch(r"\d{4}", pin):
        raise Stop("the PIN is 4 digits")
    if not running(GAMESTREAM):
        raise Stop("gamestream is not running (guarded start:gamestream first)")
    if not sunshine_reachable(win_host()):
        raise Stop(f"Sunshine is not reachable on {win_host()} {SUNSHINE_PORTS} (firewall?)")
    say(
        f"pairing on gamestream's private display :50 with PIN {pin}; enter it in Sunshine's web UI"
    )
    res = subprocess.run(
        ["docker", "exec", GAMESTREAM, "gamestream-pair", pin], text=True, timeout=240
    )
    # The saved pairing is the truth, not the exit code: after a SUCCESS, moonlight's pair CLI stays
    # on its "paired" dialog until gamestream-pair's timeout kills it (rc=124, 2026-10-02).
    if not paired():
        raise Stop(f"pairing did not complete (rc={res.returncode})")
    say(f"paired: the client key is in the gamestream-state volume (pair CLI rc={res.returncode})")
    return 0


# S2 step 0 (Batt, 2026-10-02): an EXTERNAL Moonlight (Batt's Mac, temporarily paired) streams
# the console. The session goes to the console exactly as usual, but the lock stays
# console/SWITCHING (REASON to-console-external): rdp-loop holds, and the lab's gamestream holds too
# (it streams only on console/steady), so exactly one client streams. to-rdp then ends whatever
# stream runs through Sunshine (/cancel) and checks the revert, as for the lab's own stream.
EXTERNAL_REASON = "to-console-external"


def cmd_to_console(yes_tscon: bool, external: bool = False, cleanroom: bool = False) -> int:
    backend, _, _ = read_host()
    if backend != "rdp":
        raise Stop(f"to-console starts from rdp (the lock is {backend})")
    if count(DESKTOP, RDP_NAMES) != 1:
        raise Stop("exactly one xfreerdp client must be connected (tscon is typed into it)")
    if not running(GAMESTREAM) or not paired():
        raise Stop("gamestream must be running and paired (capture_backend.py pair PIN)")
    host = win_host()
    if not sunshine_reachable(host):
        raise Stop(f"Sunshine is not reachable on {host}")
    if not yes_tscon:
        say(
            f"preflight OK. Next: lock -> console, type `{TSCON}` into the poring-lab console, "
            "TERM xfreerdp. Re-run with --yes-tscon after Batt's OK (a stop point)."
        )
        return 0
    sys.path.insert(0, str(REPO / "scripts"))
    import ro_agent as r

    with r.session("capture-backend", allow_handover=True) as (agent, screen):
        # The console is focused and verified by its tab template BEFORE the lock moves: a missing
        # or covered console stops here with the lock still rdp/steady. (A fixed taskbar offset
        # clicked the RO client's button once the session grew to 1440x900, 2026-10-02.)
        # It must be the SESSION OWNER's (poring-lab's) console: from Batt's elevated console tscon
        # failed with 1326 "user name or password is incorrect" (another user's session).
        r.focus_console(agent, screen)
        since = utc_now()
        # console/SWITCHING: rdp-loop holds, and gamestream holds too (it streams only on steady)
        body = write_lock("console", "switching", "to-console")
        verify_everywhere(body)
        r.console_type(agent, screen, TSCON)
        typed = time.monotonic()
        say(f"tscon typed (runs in {TSCON_DELAY_S} s); disconnecting the RDP client now")
    term_until_zero(DESKTOP, RDP_NAMES)
    line = wait_log(DESKTOP, rf"capture-backend console seq={raw_seq(body)}: holding", since, 60)
    say(f"rdp-loop holds: {line.split('rdp-loop: ', 1)[-1]}")
    # Only once tscon has put the session on the console may the stream start: Sunshine applies
    # its display settings (VDD only, resolution) at stream start and needs a console session for
    # that. A stream started earlier captured an empty display (2026-10-02).
    time.sleep(max(0.0, TSCON_DELAY_S + 5 - (time.monotonic() - typed)))
    if cleanroom:
        write_variant("V1")
        verify_everywhere(write_lock("console", "switching", CLEANROOM_REASON))
        say(
            "CLEAN ROOM: the session is on the console and stays there; RDP and the lab client "
            "hold. Next: stream --variant V1 (then hold, the next variant, ...). End with: to-rdp"
        )
        return 0
    if external:
        verify_everywhere(write_lock("console", "switching", EXTERNAL_REASON))
        say(
            "EXTERNAL mode: the session is on the console; the lock stays console/switching so "
            "the lab's Moonlight holds. Connect the external client now. End with: to-rdp"
        )
        return 0
    since = utc_now()
    body = write_lock("console", "steady", "to-console")
    verify_everywhere(body)
    wait_log(GAMESTREAM, rf"capture-backend console seq={raw_seq(body)}: streaming", since, 60)
    # A Moonlight window alone is not a stream: its "Starting..." window counted on 2026-10-02 while
    # the console still showed the lock screen. Require decoded video.
    wait_log(GAMESTREAM, r"Received first video packet", since, 60)
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        if health().get("stream_window_present") is True:
            break
        time.sleep(2)
    else:
        raise Stop("no Moonlight window on the display within 60 s: run to-rdp --recover")
    say("CONSOLE mode: the stream window is up. Verify one session (qwinsta) through the stream.")
    return 0


# --- the clean room (Batt, 2026-10-03; ADR-0009) --------------------------------------------------
# The session moves to the console ONCE and RDP holds for the whole experiment; only the lab client
# varies (gamestream-loop.sh reads the variant file at each stream start; keyword values only).
CLEANROOM_REASON, HOLD_REASON = "cleanroom", "cleanroom-hold"
VARIANT_NAME = "gamestream-variant"
VARIANTS = {
    "V1": {"CLIENT": "moonlight-qt", "WM": "none", "GDB_AFTER_S": ""},
    "V1gdb": {"CLIENT": "moonlight-qt", "WM": "none", "GDB_AFTER_S": "20"},
    "V2": {"CLIENT": "moonlight-qt", "WM": "openbox", "GDB_AFTER_S": ""},
    "V3": {"CLIENT": "s2spike", "WM": "none", "GDB_AFTER_S": ""},
}
WM_NAMES = "openbox"
FLOCK = Path(
    os.environ.get("CAPTURE_BACKEND_FLOCK", "/dev/shm/poring-lab-tmp/capture-backend.flock")
)


def lock_reason(text: str) -> str:
    match = re.search(r"^REASON=(\S*)$", text, re.M)
    return match.group(1) if match else ""


def lock_phase(text: str) -> str:
    match = re.search(r"^PHASE=(\S*)$", text, re.M)
    return match.group(1) if match else ""


def variant_body(variant: str) -> str:
    if variant not in VARIANTS:
        raise Stop(f"unknown variant {variant!r} (one of {', '.join(VARIANTS)})")
    return "".join(f"{k}={v}\n" for k, v in VARIANTS[variant].items())


def write_variant(variant: str) -> None:
    """Atomic write + read-back on the host and in gamestream (the only reader)."""
    body = variant_body(variant)
    STATE.mkdir(exist_ok=True)
    tmp = STATE / f".{VARIANT_NAME}.tmp"
    tmp.write_text(body, encoding="ascii")
    tmp.replace(STATE / VARIANT_NAME)
    if (STATE / VARIANT_NAME).read_text(encoding="ascii") != body:
        raise Stop("variant read-back on the host differs from what was written")
    if running(GAMESTREAM):
        seen = sh("docker", "exec", GAMESTREAM, "cat", f"/lab-state/{VARIANT_NAME}").stdout
        if seen != body:
            raise Stop(f"gamestream sees a different variant file (stale mount?): {seen!r}")
    say(f"variant -> {variant}: " + " ".join(body.split()))


def ensure_no_wm() -> None:
    """No window manager on :99 when RDP connects: openbox (V2) would decorate and place
    xfreerdp's /size window, and every click would land off target."""
    if running(GAMESTREAM) and count(GAMESTREAM, WM_NAMES):
        say("a window manager still runs in gamestream: TERM")
        term_until_zero(GAMESTREAM, WM_NAMES, quiet_s=2, timeout=30)
    if running(GAMESTREAM) and count(GAMESTREAM, WM_NAMES):
        raise Stop("openbox would not exit: RDP must not connect under a window manager")
    prop = sh("docker", "exec", DESKTOP, "xprop", "-root", "_NET_SUPPORTING_WM_CHECK").stdout
    if "window id" in prop:
        say("a stale _NET_SUPPORTING_WM_CHECK on the root window (dead WM): removing it")
        sh("docker", "exec", DESKTOP, "xprop", "-root", "-remove", "_NET_SUPPORTING_WM_CHECK")
        prop = sh("docker", "exec", DESKTOP, "xprop", "-root", "_NET_SUPPORTING_WM_CHECK").stdout
        if "window id" in prop:
            raise Stop("the root window still advertises a window manager")


def cleanroom_lock() -> tuple[str, str]:
    """(phase, reason) of the clean room's console lock, or Stop."""
    backend, _, text = read_host()
    reason = lock_reason(text)
    if backend != "console" or not reason.startswith(CLEANROOM_REASON):
        raise Stop(f"not in the clean room (lock {backend}, reason {reason or 'none'})")
    return lock_phase(text), reason


def cmd_stream(variant: str) -> int:
    phase, _ = cleanroom_lock()
    if phase != "switching":
        raise Stop("a stream is already on (console/steady): hold first")
    if not running(GAMESTREAM):
        raise Stop("gamestream is not running")
    lab_clients = count(GAMESTREAM, STREAM_NAMES)
    if lab_clients:
        raise Stop(f"{lab_clients} lab client process(es) still run: one client at a time")
    write_variant(variant)
    since = utc_now()
    body = write_lock("console", "steady", CLEANROOM_REASON)
    verify_everywhere(body)
    wait_log(GAMESTREAM, rf"capture-backend console seq={raw_seq(body)}: streaming", since, 60)
    say(f"CLEAN ROOM: {variant} is streaming")
    return 0


def cmd_hold() -> int:
    cleanroom_lock()
    verify_everywhere(write_lock("console", "switching", HOLD_REASON))
    end = quit_stream()
    write_variant("V1")
    say(f"CLEAN ROOM hold: stream end {end}; the session stays on the console")
    return 0


@contextlib.contextmanager
def mutation_lock(wait_s: float):  # type: ignore[no-untyped-def]
    """One writer at a time across processes (the runner, the watchdog, a human)."""
    FLOCK.parent.mkdir(parents=True, exist_ok=True)
    with FLOCK.open("a+") as fh:
        deadline = time.monotonic() + wait_s
        while True:
            try:
                fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    fh.seek(0)
                    holder = fh.read().strip()
                    msg = f"another capture_backend command holds the lock: {holder}"
                    raise Stop(msg) from None
                time.sleep(0.5)
        fh.seek(0)
        fh.truncate()
        fh.write(f"pid={os.getpid()} {' '.join(sys.argv[1:])[:120]}\n")
        fh.flush()
        try:
            yield
        finally:
            fcntl.flock(fh, fcntl.LOCK_UN)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--wait-lock", type=float, default=30.0, help="seconds to wait for the flock")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status")
    sub.add_parser("init")
    drill = sub.add_parser("drill")
    drill.add_argument("--hold-s", type=float, default=20.0)
    to_rdp = sub.add_parser("to-rdp")
    to_rdp.add_argument("--recover", action="store_true")
    to_console = sub.add_parser("to-console")
    to_console.add_argument("--yes-tscon", action="store_true", help="after Batt's OK only")
    to_console.add_argument(
        "--external", action="store_true",
        help="S2 step 0: an external client streams; the lab's Moonlight holds",
    )  # fmt: skip
    to_console.add_argument(
        "--cleanroom", action="store_true",
        help="the clean room: the session stays on the console; then stream/hold",
    )  # fmt: skip
    stream = sub.add_parser("stream")
    stream.add_argument("--variant", required=True, choices=sorted(VARIANTS))
    sub.add_parser("hold")
    pair = sub.add_parser("pair")
    pair.add_argument("pin")
    args = ap.parse_args()
    if args.cmd == "status":
        return cmd_status()
    with mutation_lock(args.wait_lock):
        if args.cmd == "init":
            return cmd_init()
        if args.cmd == "drill":
            return cmd_drill(args.hold_s)
        if args.cmd == "to-rdp":
            return cmd_to_rdp(args.recover)
        if args.cmd == "pair":
            return cmd_pair(args.pin)
        if args.cmd == "stream":
            return cmd_stream(args.variant)
        if args.cmd == "hold":
            return cmd_hold()
        if args.external and args.cleanroom:
            raise Stop("--external and --cleanroom exclude each other")
        return cmd_to_console(args.yes_tscon, args.external, args.cleanroom)


if __name__ == "__main__":
    sys.exit(main())
