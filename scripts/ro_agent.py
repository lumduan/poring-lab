#!/usr/bin/env python3
"""The agent's operator tool for the lab's rAthena client: log in, create a character, recover a
black client, run GM validation queries and short measurement moves. There is NO play loop.

Rules it enforces (CLAUDE.md, ADR-0002/0006):
  * input only through the backend's /internal/agent (source=bot), so every event passes the mux;
  * refuses unless the mux is in ASSIST (Batt sets it); waits while a human lease is active;
    stops at once (exit 3) on any refusal -- it never fights the human;
  * credentials come from .env and are typed as SENSITIVE batches (the input log keeps only counts
    and timing); they are never printed, logged or passed on a command line;
  * before typing: the target must be verified in front -- the client by its active title bar,
    a dialog by its signature, a PowerShell console by its tab template; secrets are re-verified
    every 4 characters, and the keyboard layout must be ENG (tray signature);
  * in-game input only while OUR rAthena shows the account online=1;
  * no Run-dialog commands (Defender's ClickFix detection, 2026-10-01): the client is launched
    from the desktop shortcut and closed with Alt+F4; it touches PoringLab.exe only (the
    community-server client is never touched).

    ro_agent.py status
    ro_agent.py shot NAME                       full screen -> /dev/shm/.../shots/NAME.png
    ro_agent.py calibrate STATE [DX DY W H]     save STATE's signature (box: client-relative)
    ro_agent.py where                           best-matching calibrated state
    ro_agent.py click DX DY [--right] [--abs]   client-area-relative click (GAME_REGION origin)
    ro_agent.py drag X1 Y1 X2 Y2 [--right] [--abs]  paced press-move-release (RO camera: --right)
    ro_agent.py open-terminal                   the agent's own NON-elevated "poring-lab shell"
    ro_agent.py calibrate-shell                 once: its tab template + the shortcut's signature
    ro_agent.py calibrate-shell --stream        the same tab, cut from the console stream's frames
    ro_agent.py close-extra-shells              ONE "poring-lab shell" window (others get WM_CLOSE)
    ro_agent.py minimize-consoles               Win+Down each visible console (before the client)
    ro_agent.py watch-status                    the lab-client watcher task: state + log tail (crop)
    ro_agent.py file-check "C:\\path"           BEFORE asking Batt for a file drop: size, time and
                                                sha256 on Windows + his ready Copy-Item line
    ro_agent.py keys CODE...                    key taps (50 ms holds)
    ro_agent.py chord CODE...                   press in order, release in reverse
    ro_agent.py type TEXT                       US-layout ASCII into the focused field (+ \\n)
    ro_agent.py login player|gm                 login screen -> character in game, online=1
    ro_agent.py create-char player|gm           on an empty char-select slot (name from .env)
    ro_agent.py gm "@where"                     GM account only; logged to data/ro_agent/gm.jsonl
    ro_agent.py say [--thai-keys] TEXT          chat line (Thai: Kedmanee key positions)
    ro_agent.py close | launch | recover [player|gm] [--retries N] [--agent-id ID]
                                                (guarded_build runs `recover gm --retries 0
                                                --agent-id auto_recover` after a sniffer restart)

Coordinates: GAME_REGION (.env, "x,y,w,h") is the client area; clicks are relative to its origin
(the same region the backend's black-screen detector watches).
"""

import argparse
import contextlib
import json
import os
import random
import re
import struct
import subprocess
import sys
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from websockets.sync.client import ClientConnection, connect

from poring_backend.capture_lock import read_lock, read_window

ROOT = Path(__file__).resolve().parents[1]
STATE_DIR = ROOT / "data" / "ro_agent"  # gitignored (rule 4): signatures + GM command log
SHOTS = Path("/dev/shm/poring-lab-tmp/shots")
LAB_STATE = ROOT / "state"  # the capture-backend lock + the interlock window, read FRESH
BACKEND = "poring-lab-backend-1"
DB = "poring-lab-db-1"
HOLD_S = 0.05  # 50 ms holds: 20 ms registers 6/6 in the client (docs/client/rathena-client.md)
# A chord's steps, paced: one instantaneous batch (down,down,up,up) is ignored by the client --
# Alt+F4 first (2026-10-01), then Alt+E/Q/S in game (2026-10-05, Batt). 60 ms closed it at once.
CHORD_STEP_S = 0.06
SHORTCUT_BOX = (80, 106, 64, 84)  # the "Ragnarok Offline" desktop icon + label
CLIENT = r"C:\RO-rAthena\client"
EXE = "PoringLab"  # the rAthena copy ONLY (ADR-0006: the community client is never touched)


# Client PROFILES (2026-10-05, the Thai-data experiment): which client copy, desktop shortcut,
# accounts and database. `kro` is the lab client and its rathena (everything as before); `th` is
# C:\RO-rAthena-th (the same exe + the Thai data.grf) and rathena-th/db-th, ONE AT A TIME with
# rathena. Picked by --profile or $RO_PROFILE. Signatures cut on the th client are `@thdata`
# variants of the same states (a state matches if any of its variants does).
@dataclass(frozen=True)
class Profile:
    name: str
    client: str
    db: str
    account_prefix: str  # <prefix>_AGENT_USER / _GM_USER / ... in .env
    shortcut_env: str  # "x,y" of the profile's desktop shortcut in .env
    variant: str | None  # the signature variant cut on this client


PROFILES = {
    "kro": Profile("kro", CLIENT, "poring-lab-db-1", "RATHENA", "RO_SHORTCUT", None),
    "th": Profile("th", r"C:\RO-rAthena-th\client", "poring-lab-db-th-1", "RATHENA_TH",
                  "RO_SHORTCUT_TH", "thdata"),
}  # fmt: skip
PROFILE = PROFILES["kro"]


def use_profile(name: str | None) -> Profile:
    """Select the client profile for this process (default: $RO_PROFILE, else kro)."""
    global PROFILE, DB
    key = name or os.environ.get("RO_PROFILE") or "kro"
    if key not in PROFILES:
        raise Stop(f"unknown client profile {key!r} (known: {', '.join(sorted(PROFILES))})")
    PROFILE = PROFILES[key]
    DB = PROFILE.db
    return PROFILE


SIG_SCALE = 8
SIG_MATCH = 6.0  # mean abs grey difference (0-255): true matches 0-2, near-misses ~10

SHIFTED = {
    "!": "Digit1", "@": "Digit2", "#": "Digit3", "$": "Digit4", "%": "Digit5", "^": "Digit6",
    "&": "Digit7", "*": "Digit8", "(": "Digit9", ")": "Digit0", "_": "Minus", "+": "Equal",
    "{": "BracketLeft", "}": "BracketRight", "|": "Backslash", ":": "Semicolon", '"': "Quote",
    "<": "Comma", ">": "Period", "?": "Slash", "~": "Backquote",
}  # fmt: skip
PLAIN = {
    " ": "Space", "-": "Minus", "=": "Equal", "[": "BracketLeft", "]": "BracketRight",
    "\\": "Backslash", ";": "Semicolon", "'": "Quote", ",": "Comma", ".": "Period", "/": "Slash",
    "`": "Backquote", "\n": "Enter", "\t": "Tab",
}  # fmt: skip


class Stop(SystemExit):
    """A refusal, a wrong screen or a failed check: stop, report, never retry against a human."""


use_profile(None)  # $RO_PROFILE also applies when another script imports this module


def ns() -> int:
    return time.monotonic_ns()


def log(msg: str) -> None:
    print(f"{time.strftime('%H:%M:%S')} {msg}", file=sys.stderr, flush=True)


# --- .env (never printed) -------------------------------------------------------------------------


def env() -> dict[str, str]:
    out: dict[str, str] = {}
    for line in (ROOT / ".env").read_text().splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            k, v = line.split("=", 1)
            out[k.strip()] = v.strip()
    return out


def account(which: str) -> tuple[str, str, str]:
    e = env()
    prefix = f"{PROFILE.account_prefix}_" + {"player": "AGENT", "gm": "GM"}[which]
    user, pw, char = e.get(f"{prefix}_USER"), e.get(f"{prefix}_PASSWORD"), e.get(f"{prefix}_CHAR")
    if not (user and pw and char):
        raise Stop(f"{prefix}_USER/_PASSWORD/_CHAR missing in .env")
    return user, pw, char


def game_region() -> tuple[int, int, int, int]:
    raw = env().get("GAME_REGION", "")
    if not raw:
        raise Stop("GAME_REGION is not set in .env (the client area, x,y,w,h)")
    x, y, w, h = (int(v) for v in raw.split(","))
    return x, y, w, h


# --- database checks (read-only; credentials via stdin, never argv) -------------------------------


def db_query(sql: str) -> list[list[str]]:
    script = (
        'MYSQL_PWD="$MARIADB_PASSWORD" exec mariadb -u"$MARIADB_USER" -N -B "$MARIADB_DATABASE"'
    )
    out = subprocess.run(
        ["docker", "exec", "-i", DB, "sh", "-c", script],
        input=sql, capture_output=True, text=True, check=True,
    ).stdout  # fmt: skip
    return [line.split("\t") for line in out.splitlines() if line]


def sql_str(value: str) -> str:
    if not value.replace("_", "").isalnum():
        raise Stop("unexpected characters in an account value")
    return f"'{value}'"


def online_chars(which: str) -> list[str]:
    user = account(which)[0]
    rows = db_query(
        "SELECT c.name FROM `char` c JOIN login l ON l.account_id = c.account_id "
        f"WHERE l.userid = {sql_str(user)} AND c.online = 1;"
    )
    return [r[0] for r in rows]


def any_online() -> int:
    return int(db_query("SELECT COUNT(*) FROM `char` WHERE online = 1;")[0][0])


# --- screen (a persistent grab helper inside the backend container: same X, same clock) -----------

# Console mode with a LIVE S2 writer (V3b): the frame bus, not X -- the same decoded frames the
# console and the bot see, stamped with the writer's decode time; X would show the never-painted
# input window (black). Anything else: X, as always. ONE rule: poring_backend.grabsource.
_HELPER = r"""
import struct, sys
import numpy as np
from poring_backend.grabsource import GrabSource
src = GrabSource()
out = sys.stdout.buffer
for line in sys.stdin:
    x, y, w, h = map(int, line.split())
    t, img, source = src.grab((x, y, w, h))
    out.write(struct.pack("<qIIqB", t, img.shape[1], img.shape[0], src.last_frame_id,
                          1 if source == "bus" else 0))
    out.write(np.ascontiguousarray(img).tobytes())
    out.flush()
"""
HELPER_HEADER = "<qIIqB"  # t_mono_ns, w, h, bus frame_id (-1 = X), source (1 = bus)


_DESKTOP: tuple[int, int] | None = None


def desktop() -> tuple[int, int]:
    """The Windows session's REAL size (w, h) at the screen's top-left, queried once per process
    inside the backend: its SESSION_SIZE clipped to the running Xvfb, never what .env says (between
    an .env write and a recreate the two differ). Clicks are normalised by it, and the backend maps
    them back over the same area (ADR-0009 amendment: the canvas may be larger than the session)."""
    global _DESKTOP
    if _DESKTOP is None:
        probe = (
            "import os, mss; from poring_env.x11 import parse_session_size, session_extent; "
            "m = mss.MSS(display=':99').monitors[0]; "
            "s = parse_session_size(os.environ.get('SESSION_SIZE', '')); "
            "print(*session_extent(s, m['width'], m['height']))"
        )
        out = subprocess.run(
            ["docker", "exec", BACKEND, "python", "-c", probe],
            capture_output=True, text=True, check=True,
        ).stdout.split()  # fmt: skip
        _DESKTOP = (int(out[0]), int(out[1]))
    return _DESKTOP


def tray_lang() -> tuple[int, int, int, int]:
    """The ENG / ไทย indicator left of the clock: anchored to the bottom-right corner (1098,764 on
    the 1280x800 desktop)."""
    w, h = desktop()
    return w - 182, h - 36, 36, 22


def tray_strip() -> tuple[int, int, int, int]:
    """Where the ENG/ไทย indicator can sit (it moves with the tray's icons)."""
    w, h = desktop()
    return w - 380, h - 36, 340, 22


class Screen:
    def __init__(self) -> None:
        self.proc = subprocess.Popen(
            ["docker", "exec", "-i", BACKEND, "python", "-u", "-c", _HELPER],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        )  # fmt: skip

    def grab(self, x: int, y: int, w: int, h: int) -> tuple[int, np.ndarray]:
        t, img, _, _ = self.grab_meta(x, y, w, h)
        return t, img

    def grab_meta(self, x: int, y: int, w: int, h: int) -> tuple[int, np.ndarray, int, str]:
        """(t_mono_ns, BGRA, the bus writer's frame_id or -1, "bus" | "x11"). A bus frame's t is
        its decode-complete time; an X grab's is the moment of the grab."""
        assert self.proc.stdin is not None and self.proc.stdout is not None
        self.proc.stdin.write(f"{x} {y} {w} {h}\n".encode())
        self.proc.stdin.flush()
        size = struct.calcsize(HELPER_HEADER)
        t, gw, gh, frame_id, bus = struct.unpack(HELPER_HEADER, self.proc.stdout.read(size))
        raw = self.proc.stdout.read(gw * gh * 4)
        img = np.frombuffer(raw, np.uint8).reshape(gh, gw, 4)
        return t, img, frame_id, "bus" if bus else "x11"

    def full(self) -> np.ndarray:
        return self.grab(0, 0, *desktop())[1]

    def close(self) -> None:
        with contextlib.suppress(Exception):
            if self.proc.stdin:
                self.proc.stdin.close()
            self.proc.wait(timeout=3)


def to_png(bgra: np.ndarray, path: Path) -> Path:
    import zlib

    h, w = bgra.shape[:2]
    rgb = bgra[:, :, 2::-1].astype(np.uint8)
    raw = b"".join(b"\x00" + rgb[y].tobytes() for y in range(h))

    def chunk(tag: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data))

    png = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
    png += chunk(b"IDAT", zlib.compress(raw, 6)) + chunk(b"IEND", b"")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(png)
    return path


def grey_thumb(bgra: np.ndarray) -> np.ndarray:
    small = bgra[::SIG_SCALE, ::SIG_SCALE, :3].astype(np.float32)
    return small[..., 0] * 0.114 + small[..., 1] * 0.587 + small[..., 2] * 0.299


def signature_path(state: str) -> Path:
    return STATE_DIR / "signatures" / f"{state}.npy"


def region_for(state: str) -> tuple[int, int, int, int]:
    """Desktop region of a state's signature: fixed for Windows UI, else a box relative to the
    client origin saved at calibration (a dialog, not the animated background)."""
    if state == "eng":
        raw = env().get("RO_TRAY_LANG", "")  # the ENG/ไทย indicator moves with the tray's icons
        if raw:
            x, y, w, h = (int(v) for v in raw.split(","))
            return x, y, w, h
        return tray_lang()
    if state in ("shortcut_icon", "shortcut_icon_sel"):
        x, y = shortcut_xy()
        return x - 32, y - 34, SHORTCUT_BOX[2], SHORTCUT_BOX[3]
    if state in ("shell_shortcut_icon", "shell_shortcut_icon_sel"):
        x, y = shell_shortcut_xy()
        return x - 32, y - 34, SHORTCUT_BOX[2], SHORTCUT_BOX[3]
    meta = signature_path(state).with_suffix(".json")
    x, y, w, h = game_region()
    if meta.exists():
        dx, dy, bw, bh = json.loads(meta.read_text())["box"]
        return x + dx, y + dy, bw, bh
    return x, y, w, h


# Locale variants (ADR-0012; 2026-10-03, the Thai pack): signatures/<state>@<locale>.npy is the SAME
# box in another locale pack's text. A state matches if ANY of its variants does; the English
# signature is never overwritten, so switching packs back needs no recalibration.
LOCALE_SEP = "@"


def base_state(state: str) -> str:
    return state.split(LOCALE_SEP, 1)[0]


def signature_variants(state: str) -> list[Path]:
    """The signature files that stand for ``state``: itself (if calibrated) and, for a base
    state, every ``state@locale`` variant. An explicit ``state@locale`` is just that file."""
    path = signature_path(state)
    found = [path] if path.exists() else []
    if LOCALE_SEP not in state:
        found += sorted(path.parent.glob(f"{state}{LOCALE_SEP}*.npy"))
    return found


def calibrate(screen: Screen, state: str, box: list[int] | None = None) -> None:
    if state == "eng_stream":  # the console stream's ENG template (only that file)
        _, img = screen.grab(*region_for("eng"))
        np.save(STATE_DIR / "signatures" / "eng_full_stream.npy", _grey(img))
        to_png(img, SHOTS / "sig_eng_stream.png")
        log(f"stream ENG template saved ({img.shape[1]}x{img.shape[0]})")
        return
    path = signature_path(state)
    path.parent.mkdir(parents=True, exist_ok=True)
    if box is not None:
        path.with_suffix(".json").write_text(json.dumps({"box": box}))
    _, img = screen.grab(*region_for(state if box is not None else base_state(state)))
    np.save(path, grey_thumb(img))
    if state == "eng":  # full resolution, for the sliding tray search
        np.save(STATE_DIR / "signatures" / "eng_full.npy", _grey(img))
    to_png(img, SHOTS / f"sig_{state}.png")
    log(f"signature {state} saved ({img.shape[1]}x{img.shape[0]})")


def _grey(img: np.ndarray) -> np.ndarray:
    px = img[:, :, :3].astype(np.float32)
    return px[..., 0] * 0.114 + px[..., 1] * 0.587 + px[..., 2] * 0.299


# One ENG template per display path: the H.264 console stream softens the tray's small text, so
# the RDP template measured 6.8 there against a 6.0 threshold (2026-10-03). Not a looser guard: a
# second template, calibrated on the stream while the tray visibly said ENG.
ENG_TEMPLATES = ("eng_full.npy", "eng_full_stream.npy")


def eng_distance(screen: Screen) -> float:
    """Best match of a full-resolution ENG template anywhere in the tray strip: the indicator's
    x shifts as tray icons come and go (1086 vs 1115 on the same account, 2026-10-01)."""
    _, img = screen.grab(*tray_strip())
    strip = _grey(img)
    best = float("inf")
    for name in ENG_TEMPLATES:
        path = STATE_DIR / "signatures" / name
        if not path.exists():
            continue
        tmpl = np.load(path)
        th, tw = tmpl.shape
        for x in range(0, strip.shape[1] - tw + 1):
            best = min(best, float(np.abs(strip[:th, x : x + tw] - tmpl).mean()))
    return best


class FrozenStream(Stop):
    """No frame decoded AFTER an action arrived in time: the stream is frozen (a dropped frame
    waiting for an IDR), so the action's effect is UNKNOWN -- never decide on the older picture
    (the frame-age guard, 2026-10-04: a frozen frame made the chat look closed at 05:58)."""


FRESH_WAIT_S = 1.5  # the longest measured freeze was 239 ms; a static screen sends no frames


def grab_after(
    screen: Screen, region: tuple[int, int, int, int], after_ns: int | None
) -> np.ndarray:
    """``region`` from a frame decoded after ``after_ns`` (bus) -- an X grab is always "now".
    Without ``after_ns`` it is a plain grab, exactly as before."""
    if after_ns is None:
        return screen.grab(*region)[1]
    end = time.monotonic() + FRESH_WAIT_S
    while True:
        t, img, _, source = screen.grab_meta(*region)
        if source != "bus" or t > after_ns:
            return img
        if time.monotonic() > end:
            raise FrozenStream(f"no frame newer than the action within {FRESH_WAIT_S} s")
        time.sleep(0.02)


def distance(screen: Screen, state: str, after_ns: int | None = None) -> float:
    if state == "eng" and (STATE_DIR / "signatures" / "eng_full.npy").exists():
        return eng_distance(screen)
    paths = signature_variants(state)
    if not paths:
        raise Stop(f"no signature for {state!r}: run `ro_agent.py calibrate {state}` first")
    img = grab_after(screen, region_for(base_state(state)), after_ns)
    cur = grey_thumb(img)
    best = float("inf")
    for path in paths:
        ref = np.load(path)
        if cur.shape == ref.shape:
            best = min(best, float(np.abs(cur - ref).mean()))
    return best


def is_state(screen: Screen, state: str, after_ns: int | None = None) -> bool:
    """``after_ns``: judge only a frame decoded after this time (the effect of an action)."""
    return distance(screen, state, after_ns) <= SIG_MATCH


def wait_state(screen: Screen, states: list[str], timeout: float) -> str:
    if not any(signature_variants(st) for st in states):  # first run: calibrating
        log(f"no signature yet for {states}: waiting {min(timeout, 25):.0f} s instead")
        time.sleep(min(timeout, 25))
        return "uncalibrated"
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        for st in states:
            if signature_variants(st) and is_state(screen, st):
                return st
        time.sleep(0.5)
    to_png(screen.full(), SHOTS / f"timeout_{'_'.join(states)}.png")
    raise Stop(f"timed out ({timeout:.0f} s) waiting for {states}; screenshot saved")


def black(screen: Screen) -> bool:
    _, img = screen.grab(*game_region())
    px = img[::4, ::4, :3].astype(np.uint16)
    luma = (px[..., 0] * 29 + px[..., 1] * 150 + px[..., 2] * 77) >> 8
    return bool((luma < 10).mean() >= 0.98)


# --- the mux channel ------------------------------------------------------------------------------


def backend_ws() -> str:
    here = str(Path(__file__).resolve().parent)
    if here not in sys.path:
        sys.path.insert(0, here)
    from backend_addr import backend_ip  # the DEFAULT network's address (two networks since c2)

    ip = backend_ip(BACKEND)
    if not ip:
        raise Stop(f"{BACKEND} has no address on the default network (not running?)")
    return f"ws://{ip}:8001/internal/agent"


def backend_health() -> dict[str, Any]:
    """The backend's /health (public port, the default network's address), or {}."""
    import urllib.request

    url = backend_ws().replace("ws://", "http://").replace(":8001/internal/agent", ":8000/health")
    try:
        with urllib.request.urlopen(url, timeout=3) as resp:
            data: dict[str, Any] = json.loads(resp.read())
            return data
    except OSError:
        return {}


# --- the environment interlock (ADR-0016, rewritten 2026-10-04) -----------------------------------


class Unattested(Stop):
    """The mux refused bot input: no attested lab session and no operator window (ADR-0016).
    Never retried as if the screen were at fault (dataset_activity.safe_gm re-raises it)."""


WINDOW_MIN_LEFT_S = 25


def ensure_window(
    kind: str, phase: str, seconds: int = 90, min_left: float = WINDOW_MIN_LEFT_S
) -> None:
    """Login and desktop phases happen before (or outside) an attested in-game session: open a
    bounded operator window through the HOST tool (capture_backend.py window; never the agent
    channel). Skipped while the interlock is green, or a window of this kind is open long enough
    (capture_backend opens its own before its ro_agent steps, holding the mutation lock).

    The window is read FRESH from the host's state/ with the backend's own parser: /health reports
    the interlock as of its last 1 Hz tick. Right after capture_backend re-opened its window for the
    new SEQ, that stale view said "no window", so the child `window` command waited 30 s for the
    flock its own parent held and to-console failed (21:18, 21:26 and 21:43 on 2026-10-04; the one
    run whose check landed after a tick went through)."""
    open_now = read_window(LAB_STATE, read_lock(LAB_STATE), time.time())
    if open_now is not None and open_now[0] == kind and open_now[2] >= min_left:
        return
    env_status = backend_health().get("environment") or {}
    if env_status.get("state") == "green":
        return
    cmd = [sys.executable, str(ROOT / "scripts" / "capture_backend.py"), "window", kind,
           "--seconds", str(seconds), "--reason", phase]  # fmt: skip
    res = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if res.returncode != 0:
        raise Stop(f"could not open the {kind} window for {phase}: {res.stderr.strip()[-300:]}")
    log(f"interlock: {kind} window for {phase} ({seconds} s)")


def key(code: str, action: str) -> dict[str, Any]:
    return {"type": "key", "t_mono_ns": ns(), "frame_id": -1, "code": code, "action": action}


def tap(code: str, shift: bool = False) -> list[dict[str, Any]]:
    if shift:
        return [
            key("ShiftLeft", "down"),
            key(code, "down"),
            key(code, "up"),
            key("ShiftLeft", "up"),
        ]
    return [key(code, "down"), key(code, "up")]


def char_events(c: str) -> list[dict[str, Any]]:
    if c.isascii() and c.isalpha():
        return tap(f"Key{c.upper()}", shift=c.isupper())
    if c.isascii() and c.isdigit():
        return tap(f"Digit{c}")
    if c in PLAIN:
        return tap(PLAIN[c])
    if c in SHIFTED:
        return tap(SHIFTED[c], shift=True)
    raise Stop("cannot type that character (US-layout ASCII only)")  # never echo the character


# max_queue=None: no receive-side flow control. With the library's default (16 frames) its reader
# thread STOPS reading the socket once 16 unread messages queue up -- ~16 s of the backend's 1 Hz
# status -- so pings go unanswered and the connection dies 20-40 s later, and a close then waits
# its 10 s timeout ("sent 1000 (OK); no close frame received", to-console 2026-10-04). Callers do
# host work between sends (docker exec read-backs, subprocesses); the backlog is ~1 KB/s of status,
# read through by the next _drain. test_ro_agent_ws.py reproduces both behaviours.
AGENT_WS: dict[str, Any] = {"open_timeout": 5, "max_size": 2**20, "max_queue": None}


class Agent:
    """One /internal/agent connection; every send checks ASSIST and waits out a human lease."""

    def __init__(self, name: str = "ro_agent", *, allow_handover: bool = False) -> None:
        self.allow_handover = allow_handover  # only scripts/capture_backend.py, mid-handover
        self._conn = connect(backend_ws(), **AGENT_WS)
        self.ws: ClientConnection = self._conn.__enter__()
        hello = {"type": "agent_hello", "t_mono_ns": ns(), "frame_id": -1, "agent_id": name,
                 "version": "1"}  # fmt: skip
        self.ws.send(json.dumps(hello))
        self.status: dict[str, Any] = {}
        self._drain(1.5, want="status")
        if self.status.get("mode") != "ASSIST":
            self.ws.close()
            raise Stop(f"mux mode is {self.status.get('mode')}, not ASSIST: no input sent")
        self.backend = self._check_capture_backend()

    def _check_capture_backend(self) -> str:
        """ADR-0009: input only while the capture-backend lock is steady, and the host file and the
        backend agree on it (a backend created before the lock mount reports nothing)."""
        lock = self.status.get("capture_backend")
        host = read_lock(LAB_STATE)
        if lock is None:
            print("WARNING: the backend reports no capture_backend (predates the lock)", flush=True)
            return host.backend
        if lock.get("backend") == "hold" or host.backend == "hold":
            self.ws.close()
            raise Stop(f"capture-backend lock HOLD ({lock.get('reason') or host.reason}): no input")
        if (lock.get("phase") == "switching" or host.phase == "switching") and not (
            self.allow_handover
        ):
            self.ws.close()
            raise Stop("a capture-backend handover is in progress: no input sent")
        if (lock.get("backend"), lock.get("seq")) != (host.backend, host.seq):
            self.ws.close()
            raise Stop(
                f"capture-backend lock mismatch: host {host.backend}/{host.seq}, backend "
                f"{lock.get('backend')}/{lock.get('seq')} (scripts/capture_backend.py status)"
            )
        return str(lock["backend"])

    def idle(self, seconds: float) -> None:
        """Wait without sending input, reading the backend's messages so the connection stays
        healthy (a session left unread for ~35 s failed its websocket keepalive, 2026-10-02)."""
        end = time.monotonic() + seconds
        while (left := end - time.monotonic()) > 0:
            self._drain(min(1.0, left))

    def _drain(self, timeout: float, want: str | None = None) -> dict[str, Any] | None:
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            try:
                msg = json.loads(self.ws.recv(timeout=max(0.0, end - time.monotonic())))
            except TimeoutError:
                break
            if msg.get("type") == "status":
                self.status = msg
            if msg.get("type") == "error":
                raise Stop(f"backend error reply: {msg.get('reason')}")
            if want and msg.get("type") == want:
                return dict(msg)
        return None

    def wait_for_human(self, max_wait_s: float = 600.0) -> None:
        """Batt holds the ASSIST lease: wait (never fight), up to max_wait_s, then stop."""
        end = time.monotonic() + max_wait_s
        while True:
            self._drain(0.05)
            lease = self.status.get("lease_until_ns")
            if self.status.get("mode") != "ASSIST":
                raise Stop(f"mux left ASSIST ({self.status.get('mode')}): stopping")
            if not lease or lease < ns():
                return
            if time.monotonic() > end:
                raise Stop("the human kept the lease for 10 min: giving up")
            log("human lease active: waiting")
            self._drain(1.0)

    def send(self, events: list[dict[str, Any]], *, sensitive: bool = False) -> None:
        self.wait_for_human()
        for i in range(0, len(events), 64):
            chunk = events[i : i + 64]
            msg = {"type": "agent_input", "t_mono_ns": ns(), "frame_id": -1, "t_capture_ns": ns(),
                   "events": chunk, "sensitive": sensitive}  # fmt: skip
            self.ws.send(json.dumps(msg))
            ack = self._drain(3.0, want="input_ack")
            if ack is None:
                raise Stop("no input_ack within 3 s")
            if ack["dropped"]:
                why = f"mux refused {ack['dropped']}/{len(chunk)} ({ack['reasons']}): stopping"
                if "environment_unattested" in ack["reasons"]:
                    raise Unattested(why)
                raise Stop(why)

    def keys(self, *codes: str) -> None:
        for c in codes:
            self.send([key(c, "down")])
            time.sleep(HOLD_S)
            self.send([key(c, "up")])
            time.sleep(HOLD_S)

    def clear_field(self, n: int) -> None:
        """n paced Backspaces. The client drops edit keys injected back-to-back in one batch (only
        4 of 24 registered, 2026-10-01); typed characters arrive intact (they come as WM_CHAR)."""
        for _ in range(n):
            self.send([key("Backspace", "down")])
            time.sleep(0.03)
            self.send([key("Backspace", "up")])
            time.sleep(0.03)

    def chord(self, *codes: str) -> None:
        """Press in order, release in reverse, each step its own batch CHORD_STEP_S apart (the
        modifier is held while the key goes down and up). Whatever was pressed is released even
        when a later step is refused: a stuck Alt would turn every later click into Alt+click."""
        pressed: list[str] = []
        try:
            for c in codes:
                self.send([key(c, "down")])
                pressed.append(c)
                time.sleep(CHORD_STEP_S)
        finally:
            for c in reversed(pressed):
                with contextlib.suppress(Stop):  # releases always pass the mux; keep the cause
                    self.send([key(c, "up")])
                time.sleep(CHORD_STEP_S)

    def type_text(self, text: str, *, sensitive: bool = False) -> None:
        for c in text:  # one balanced batch per character, paced
            self.send(char_events(c), sensitive=sensitive)
            time.sleep(0.03)

    def type_secret(self, text: str, guard: Callable[[], None]) -> None:
        """Sensitive typing that re-verifies the target screen before it starts and every 4
        characters (2026-10-01: a password typed into a PowerShell window that had covered the
        client was executed and saved to PSReadLine history). `guard` raises Stop."""
        for i, c in enumerate(text):
            if i % 4 == 0:
                guard()
            self.send(char_events(c), sensitive=True)
            time.sleep(0.03)

    def move(self, x: int, y: int) -> None:
        self.send([{"type": "mouse_move", "t_mono_ns": ns(), "frame_id": -1,
                    "x": x / desktop()[0], "y": y / desktop()[1]}])  # fmt: skip

    def click(self, x: int, y: int, button: str = "left") -> None:
        w, h = desktop()
        nx, ny = x / w, y / h
        self.move(x, y)
        time.sleep(HOLD_S)
        for action in ("down", "up"):
            self.send([{"type": "mouse_button", "t_mono_ns": ns(), "frame_id": -1,
                        "button": button, "action": action, "x": nx, "y": ny}])  # fmt: skip
            time.sleep(HOLD_S)

    def drag(
        self, x1: int, y1: int, x2: int, y2: int, button: str = "left", steps: int = 10
    ) -> None:
        """Press at (x1, y1), move to (x2, y2) in `steps` paced moves, release. RO's camera
        (right-drag) reads motion spread over frames while the button is held, so the moves are
        30 ms apart, never one batch; the button is released even if a move is refused."""
        w, h = desktop()
        self.move(x1, y1)
        time.sleep(HOLD_S)
        self.send([{"type": "mouse_button", "t_mono_ns": ns(), "frame_id": -1, "button": button,
                    "action": "down", "x": x1 / w, "y": y1 / h}])  # fmt: skip
        try:
            for i in range(1, steps + 1):
                time.sleep(0.03)
                self.move(round(x1 + (x2 - x1) * i / steps), round(y1 + (y2 - y1) * i / steps))
        finally:
            time.sleep(HOLD_S)
            self.send([{"type": "mouse_button", "t_mono_ns": ns(), "frame_id": -1,
                        "button": button, "action": "up", "x": x2 / w, "y": y2 / h}])  # fmt: skip

    def close(self) -> None:
        with contextlib.suppress(Exception):
            self.ws.close()


@contextlib.contextmanager
def session(
    name: str = "ro_agent", *, allow_handover: bool = False
) -> Iterator[tuple[Agent, Screen]]:
    screen = Screen()
    try:
        agent = Agent(name, allow_handover=allow_handover)
    except BaseException:
        screen.close()
        raise
    try:
        yield agent, screen
    finally:
        agent.close()
        screen.close()


def at(dx: int, dy: int) -> tuple[int, int]:
    x, y, _, _ = game_region()
    return x + dx, y + dy


def centre_offset(dx: int, dy: int) -> tuple[int, int]:
    """Login/char-select windows are centred in the client area: offsets from its centre."""
    x, y, w, h = game_region()
    return x + w // 2 + dx, y + h // 2 + dy


# --- Windows one-liners through the Run dialog ----------------------------------------------------


# --- an existing PowerShell console (never the Run dialog: Defender's ClickFix detection) -------


# Templates per console kind: a Windows Terminal tab, and a classic console window's title bar
# (Batt's elevated console opened as one on 2026-10-02 -- same icon + title, another background).
# "poring-lab shell" is the agent's OWN terminal (open_terminal, Batt 2026-10-03); a plain
# "Windows PowerShell" tab is one Batt opened.
SHELL_TEMPLATE = "shell_tab_template.npy"
# One copy per display path, like ENG_TEMPLATES: the console stream's H.264 softens a tab's small
# text, so a template cut on RDP frames may miss it there (2026-10-03: `calibrate-shell --stream`).
STREAM_SUFFIX = "_stream.npy"


def template_names(name: str) -> tuple[str, str]:
    return name, name.removesuffix(".npy") + STREAM_SUFFIX


CONSOLE_TEMPLATES = {
    False: (SHELL_TEMPLATE, "ps_tab_template.npy"),
    True: ("ps_admin_tab_template.npy", "ps_admin_conhost_template.npy"),
}


def find_console(screen: Screen, admin: bool = False) -> tuple[int, int, float] | None:
    """Locate an ACTIVE Windows PowerShell tab or title bar anywhere on screen by template (its
    icon + title), anchored on the icon's blue pixels. Returns (x, y, error) of the template origin
    of the best match over the kind's templates, or None. A dark heuristic is not enough: the
    black wallpaper passed one (2026-10-01, Enter landed on the desktop and launched CPU-Z's UAC
    prompt -- declined)."""
    rgb = screen.full()[:, :, 2::-1].astype(np.int16)
    best: tuple[int, int, float] | None = None
    for name in (n for base in CONSOLE_TEMPLATES[admin] for n in template_names(base)):
        path = STATE_DIR / "signatures" / name
        if not path.exists():
            continue
        found = _match_console(rgb, np.load(path).astype(np.int16))
        if found is not None and (best is None or found[2] < best[2]):
            best = found
    if best is None and not any(
        (STATE_DIR / "signatures" / n).exists() for n in CONSOLE_TEMPLATES[admin]
    ):
        raise Stop(f"no PowerShell console template ({', '.join(CONSOLE_TEMPLATES[admin])})")
    return best


def _match_console(rgb: np.ndarray, tmpl: np.ndarray) -> tuple[int, int, float] | None:
    """One template (RGB int16) against the screen (RGB int16): (x, y, error) or None."""
    th, tw = tmpl.shape[:2]
    blue = (tmpl[..., 2] > 150) & (tmpl[..., 0] < 110)
    # Anchor on an INTERIOR icon pixel (all 8 neighbours blue too): an edge pixel is anti-aliased
    # and changes with the tab's sub-pixel position (missed a visible tab, 2026-10-01).
    inner = blue.copy()
    inner[1:-1, 1:-1] &= (
        blue[:-2, 1:-1] & blue[2:, 1:-1] & blue[1:-1, :-2] & blue[1:-1, 2:]
        & blue[:-2, :-2] & blue[:-2, 2:] & blue[2:, :-2] & blue[2:, 2:]
    )  # fmt: skip
    inner[[0, -1], :] = False
    inner[:, [0, -1]] = False
    pts = np.argwhere(inner) if inner.any() else np.argwhere(blue)
    ay, ax = (int(v) for v in pts[len(pts) // 2])
    h, w = rgb.shape[:2]
    anchor = tmpl[ay, ax]
    cand = np.argwhere(np.abs(rgb - anchor).max(axis=2) <= 24) - (ay, ax)
    ok = (cand[:, 0] >= 0) & (cand[:, 1] >= 0) & (cand[:, 0] + th <= h) & (cand[:, 1] + tw <= w)
    cand = cand[ok]
    if len(cand) == 0:
        return None
    # Vectorised pre-filter on a sparse grid of template pixels, so blue game pixels matching the
    # anchor (there were >5000 with water on screen, 2026-10-01) can't crowd the tab out.
    gy, gx = np.mgrid[0:th:4, 0:tw:8]
    gy, gx = gy.ravel(), gx.ravel()
    sample = rgb[cand[:, 0, None] + gy, cand[:, 1, None] + gx]  # (n, k, 3)
    coarse = np.abs(sample - tmpl[gy, gx]).mean(axis=(1, 2))
    best: tuple[int, int, float] | None = None
    for i in np.argsort(coarse)[:20]:
        oy, ox = int(cand[i, 0]), int(cand[i, 1])
        err = float(np.abs(rgb[oy : oy + th, ox : ox + tw] - tmpl).mean())
        if best is None or err < best[2]:
            best = (ox, oy, err)
    return best if best is not None and best[2] < 10 else None


def any_console(screen: Screen) -> bool:
    """A PowerShell console -- normal OR Administrator -- is visible. Never right-drag, click the
    world or press game keys then: a right-click in a console pastes the clipboard."""
    return find_console(screen) is not None or find_console(screen, admin=True) is not None


def minimize_consoles(agent: Agent, screen: Screen) -> None:
    """Minimise every visible PowerShell console (normal and Administrator): focus it by its tab,
    then Win+Down (a second press when the first only restored a maximised window)."""
    if any_console(screen):
        ensure_window("desktop", "minimize-consoles")
    for admin in (False, True):
        for _ in range(3):
            found = find_console(screen, admin)
            if found is None:
                break
            agent.click(found[0] + 40, found[1])  # the tab label: focuses, never pastes
            time.sleep(0.5)
            agent.chord("MetaLeft", "ArrowDown")
            time.sleep(0.8)
    if any_console(screen):
        raise Stop("a PowerShell console stays visible after Win+Down: minimise it by hand")


def focus_console(agent: Agent, screen: Screen, admin: bool = False) -> tuple[int, int]:
    """Click the console's own tab and re-verify it is the active window; its tab origin."""
    ensure_window("desktop", "console")
    log("focus_console: window ok; looking for the console")
    found = find_console(screen, admin)
    log(f"focus_console: found {found is not None}")
    if found is None:
        to_png(screen.full(), SHOTS / "console_missing.png")
        raise Stop("no active PowerShell console on screen: nothing typed")
    ox, oy, _ = found
    agent.click(ox + 75, oy + 9)  # its tab: focuses that window
    log("focus_console: clicked its tab")
    time.sleep(0.4)
    again = find_console(screen, admin)
    if again is None or abs(again[0] - ox) > 2 or abs(again[1] - oy) > 2:
        raise Stop("the console moved or lost focus after the click: nothing typed")
    return ox, oy


def console_type(
    agent: Agent, screen: Screen, command: str, admin: bool = False, *, prove: bool = True
) -> None:
    """Type a NON-secret command line into the verified console (it lands in PSReadLine history,
    so never a credential: use console_secret for those), and (prove) return only once it RAN."""
    focus_console(agent, screen, admin)
    type_line(agent, screen, command, prove=prove)


PROOF_TIMEOUT_S = 6.0


def proven_line(command: str, cells: int) -> str:
    """`cls`, the proof bar, then the command (its own leading `cls; ` dropped: it would wipe the
    bar the moment it is drawn)."""
    body = command.removeprefix("cls; ")
    return f"cls; Write-Host (' ' * {cells}) -BackgroundColor DarkMagenta; {body}"


def type_line(agent: Agent, screen: Screen, command: str, *, prove: bool = True) -> None:
    """One command line into the console ALREADY verified in front.

    Escape first: PSReadLine's RevertLine drops any half-typed input, even a multi-line `>>` one,
    and never touches a running command. On 2026-10-04 a long line cut off mid-typing left an
    unclosed `{`, and every later line was appended to it at a `>>` prompt and never ran -- tscon
    included, so the console showed the Windows sign-in screen.

    prove: the line starts with `cls` + a DarkMagenta bar of a width no bar on screen has now, and
    this returns only once that bar shows (a Stop otherwise): the line ran, not an older one."""
    # A window long enough for THIS line (~9 characters/s, 2026-10-05: a 30 s window expired
    # mid-line and the mux refused the rest) -- skipped while the interlock is green.
    ensure_window("desktop", "console-line", 120, min(110.0, 15 + len(command) / 7))
    agent.keys("Escape")
    time.sleep(0.2)
    if not prove:
        agent.type_text(command + "\n")
        return
    cells = fresh_cells(screen.full(), (MARKER_PROOF,))
    agent.type_text(proven_line(command, cells) + "\n")
    deadline = time.monotonic() + PROOF_TIMEOUT_S
    while time.monotonic() < deadline:
        time.sleep(0.4)
        if any(cells_match(n, cells) for _, n in marker_runs(screen.full(), MARKER_PROOF)):
            return
    to_png(screen.full(), SHOTS / "console_line_not_run.png")
    raise Stop("the console did not run the typed line (no fresh proof bar): stopped")


def console_secret(agent: Agent, screen: Screen, var: str, admin: bool = False) -> None:
    """Answer a `Read-Host -AsSecureString` prompt with the .env value of ``var``: sensitive input
    batches (the input log keeps counts only), the console re-verified every 4 characters. The
    value goes to the SecureString, never to a command line or the PSReadLine history."""
    value = env().get(var)
    if not value:
        raise Stop(f"{var} is not set in .env")
    ox, oy = focus_console(agent, screen, admin)

    def guard() -> None:
        now = find_console(screen, admin)
        if now is None or abs(now[0] - ox) > 2 or abs(now[1] - oy) > 2:
            raise Stop("the console lost focus while typing a secret: stopped")

    agent.type_secret(value, guard)
    guard()
    agent.keys("Enter")


def require_eng(screen: Screen) -> None:
    if not is_state(screen, "eng"):
        to_png(screen.full(), SHOTS / "layout_not_eng.png")
        raise Stop("keyboard layout is not ENG (tray): no credentials typed")


def activate_client(agent: Agent, screen: Screen) -> None:
    """Click the client's own title bar, then VERIFY it is the foreground window (its active
    title-bar signature; inactive scores ~30). Another window can cover the title bar: on
    2026-10-01 a console did, the click focused the console, and a camera rotation's
    right-clicks pasted the Windows clipboard onto its prompt (not executed; cleared)."""
    x, y, w, _ = game_region()
    clicked = ns()
    agent.click(x + w // 2, y - 15)
    if not signature_path("client_title_active").exists():
        time.sleep(0.4)
        return
    end = time.monotonic() + 2.0  # the title repaints a beat after focus returns
    while not is_state(screen, "client_title_active", after_ns=clicked):
        if time.monotonic() > end:
            to_png(screen.full(), SHOTS / "client_not_front.png")
            raise Stop("the client is not the foreground window after activation: stopped")
        time.sleep(0.2)


def login_guard(screen: Screen) -> Callable[[], None]:
    """The login dialog is visible and uncovered, and the layout is ENG -- or Stop."""

    def check() -> None:
        if not is_state(screen, "login"):
            to_png(screen.full(), SHOTS / "guard_login_not_visible.png")
            raise Stop("the login dialog is not visible (covered or gone): stopped typing")
        require_eng(screen)

    return check


def to_char_select(agent: Agent, screen: Screen, which: str) -> None:
    """Service select or login screen -> character select, credentials typed as sensitive."""
    ensure_window("login", "login")
    user, pw, _ = account(which)
    st = wait_state(screen, ["service_select", "login"], 10)
    if st == "service_select":
        # A freshly launched window takes its first click as activation: retry, bounded.
        for _ in range(3):
            agent.click(*layout("service_ok"))
            with contextlib.suppress(Stop):
                wait_state(screen, ["login"], 4)
                break
        else:
            raise Stop("the service-select OK did not register after 3 clicks")
    activate_client(agent, screen)
    guard = login_guard(screen)
    guard()
    # The ID field may hold a remembered id ("Save ID"): click it, go to the end, clear it.
    agent.click(*layout("id"))
    guard()
    agent.keys("End")
    agent.clear_field(24)
    agent.type_secret(user, guard)
    agent.click(*layout("password"))
    guard()
    agent.clear_field(32)
    agent.type_secret(pw, guard)
    guard()
    # Click "Login" rather than Enter: with Enter the client never dialled the char server
    # (2026-10-01, both agent accounts; a human clicking logged in fine).
    agent.click(*layout("login_button"))
    log(f"{which} credentials sent (sensitive)")
    # Choose the server AT ONCE: the client gives up ("Failed to Connect to Server", without even
    # dialling the char server) when no server is chosen within ~1-2 s of the list arriving.
    # A human picking it in 1.3 s worked; the agent waiting 2-19 s failed 8/8 (2026-10-01).
    # The list arrives ~10 ms after the login reply; RDP shows it at reduced quality first, so a
    # signature can lag by seconds. Click OK on a fixed delay instead.
    time.sleep(0.8)
    agent.click(*layout("server_ok"))
    wait_state(screen, ["char_select"], 20)
    log("character select")


def enter_game(agent: Agent, screen: Screen, which: str) -> None:
    _, _, char = account(which)
    if char not in account_chars(which):
        raise Stop(f"{which}: no character {char!r} yet: run `ro_agent.py create-char {which}`")
    ensure_window("login", "enter-game")  # covers the gap until the session is attested
    agent.keys("Enter")
    end = time.monotonic() + 40
    while time.monotonic() < end:
        if char in online_chars(which):
            break
        time.sleep(1)
    else:
        to_png(screen.full(), SHOTS / f"login_{which}_not_online.png")
        raise Stop(f"{which}: the character never came online=1")
    for _ in range(20):
        if not black(screen):
            log(f"{which} in game: online=1 and drawing")
            return
        time.sleep(1)
    raise Stop(f"{which}: online=1 but the game region stays black")


def create_char(agent: Agent, screen: Screen, which: str) -> None:
    """From character select: first slot -> Human, default look -> the name from .env -> Create."""
    _, _, char = account(which)
    if char in account_chars(which):
        log(f"{which}: {char!r} already exists")
        return
    ensure_window("login", "char-make")
    if not is_state(screen, "char_make"):
        wait_state(screen, ["char_select"], 10)
        agent.click(*layout("slot1"))
        wait_state(screen, ["char_make"], 10)
    agent.click(*layout("char_name"))
    agent.keys("End")
    agent.clear_field(24)
    agent.type_text(char)
    agent.click(*layout("char_create"))
    end = time.monotonic() + 15
    while char not in account_chars(which):
        if time.monotonic() > end:
            to_png(screen.full(), SHOTS / f"create_{which}_failed.png")
            raise Stop(f"{which}: {char!r} was not created")
        time.sleep(1)
    log(f"{which}: created {char!r}")


def login(agent: Agent, screen: Screen, which: str) -> None:
    to_char_select(agent, screen, which)
    enter_game(agent, screen, which)


# Login-screen layout, client-relative (GAME_REGION origin), per client size, measured on the live
# client (docs/client/rathena-client.md "Agent automation"). Never guessed at runtime: an unknown
# size stops.
LAYOUTS: dict[tuple[int, int], dict[str, tuple[int, int]]] = {
    # 1024x768 window: client 1008 wide, bottom hidden by the taskbar (visible 721).
    (1008, 721): {
        "service_ok": (578, 560),
        "id": (461, 504),
        "password": (461, 526),
        "login_button": (604, 529),
        "server_row": (509, 404),
        "server_ok": (578, 560),
        "slot1": (101, 159),
        "char_name": (606, 358),
        "char_create": (798, 476),
    },
    # 800x664 window (2026-10-01): client 784x625 at (248,99), fully above the taskbar.
    (784, 625): {
        "service_ok": (466, 495),
        "id": (349, 439),
        "password": (349, 461),
        "login_button": (492, 463),
        "server_ok": (466, 495),
        "chat_input": (300, 613),
    },
    # 1296x759 window (2026-10-02, frozen for Phase 2): a 1:1 1280x720 client at (80,77) of the
    # 1440x900 session. The login dialogs sit +248,+60 from the 784x625 layout (the old signature
    # templates match there, distance ~2); the in-game windows keep their client positions.
    (1280, 720): {
        "service_ok": (714, 555),
        "id": (597, 499),
        "password": (597, 521),
        "login_button": (740, 523),
        "server_ok": (714, 555),
        "chat_input": (300, 613),
        # character select / make (2026-10-05, the th client: the same kRO UI as the main one)
        "slot1": (231, 156),
        "char_name": (742, 354),
        "char_create": (934, 472),
    },
}


def layout(name: str) -> tuple[int, int]:
    _, _, w, h = game_region()
    try:
        dx, dy = LAYOUTS[(w, h)][name]
    except KeyError:
        raise Stop(f"no measured layout for a {w}x{h} client ({name})") from None
    return at(dx, dy)


def account_chars(which: str) -> list[str]:
    user = account(which)[0]
    rows = db_query(
        "SELECT c.name FROM `char` c JOIN login l ON l.account_id = c.account_id "
        f"WHERE l.userid = {sql_str(user)};"
    )
    return [r[0] for r in rows]


def open_chat(agent: Agent, screen: Screen) -> None:
    """Make sure the chat input is open (Enter opens it), then click INTO it: an open but
    unfocused input (e.g. after clicks on the world) drops the first keystrokes -- a `@warp ...`
    went out as public chat without its `@warp ` (2026-10-01)."""
    # Enter toggles an EMPTY input. The signature can miss an input that IS open (the blinking text
    # cursor, 2026-10-02): then the first Enter closed it -- so toggle up to twice.
    pressed: int | None = None
    for _ in range(2):
        if is_state(screen, "chat_open", after_ns=pressed):
            break
        pressed = ns()
        agent.keys("Enter")
        time.sleep(1.0)
    # judged on a frame decoded AFTER the last Enter: a frozen frame is FrozenStream, not "closed"
    if not is_state(screen, "chat_open", after_ns=pressed):
        raise Stop("the chat input did not open: nothing typed")
    agent.click(*layout("chat_input"))
    time.sleep(0.2)


def chat_line(agent: Agent, screen: Screen, text: str) -> None:
    """Open the chat input if it is closed, type, send (Enter)."""
    open_chat(agent, screen)
    agent.type_text(text + "\n")


def gm(agent: Agent, screen: Screen, command: str) -> None:
    if not command.startswith("@"):
        raise Stop("GM commands start with @")
    _, _, char = account("gm")
    if char not in online_chars("gm"):
        raise Stop("the GM character is not online=1 on our rAthena: nothing sent")
    if black(screen):
        raise Stop("the game region is black: nothing sent")
    record = {"t_mono_ns": ns(), "t_wall": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "cmd": command}
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    with (STATE_DIR / "gm.jsonl").open("a") as fh:
        fh.write(json.dumps(record) + "\n")
    activate_client(agent, screen)  # a Windows popup can take focus at any time
    chat_line(agent, screen, command)
    log(f"gm: {command}")


def say(agent: Agent, screen: Screen, which: str, text: str, thai_keys: bool) -> None:
    _, _, char = account(which)
    if char not in online_chars(which):
        raise Stop(f"{which} is not online=1: nothing sent")
    activate_client(agent, screen)
    open_chat(agent, screen)  # typed while closed, the letters are hotkeys (2026-10-01)
    if thai_keys:
        require_eng(screen)
        agent.chord("MetaLeft", "Space")  # next input language (ENG -> Thai Kedmanee)
        time.sleep(0.8)
        if is_state(screen, "eng"):
            raise Stop("layout did not switch to Thai: nothing typed")
        try:
            agent.type_text(text + "\n")
        finally:
            agent.chord("MetaLeft", "Space")
            time.sleep(0.8)
        require_eng(screen)
    else:
        agent.type_text(text + "\n")
    log(f"said ({'thai keys' if thai_keys else 'ascii'}) as {which}")


# The "Ragnarok Offline" desktop shortcut (C:\\RO-rAthena\\PoringLab.cmd); its icon position depends
# on the Windows account's desktop layout: RO_SHORTCUT="x,y" in .env.
SHORTCUT = (112, 140)


def shortcut_xy() -> tuple[int, int]:
    raw = env().get(PROFILE.shortcut_env, "")
    if not raw:
        return SHORTCUT
    x, y = (int(v) for v in raw.split(","))
    return x, y


def close_client(agent: Agent, screen: Screen) -> None:  # noqa: ARG001
    """Alt+F4 on the client itself (a lost-D3D client still takes window messages); confirm the
    quit prompt if it shows. No PowerShell: Run-dialog PowerShell trips Defender's ClickFix
    detection (2026-10-01, severity 5, the processes were killed)."""
    ensure_window("login", "close")  # the session may already be gone (a lost-D3D client)
    activate_client(agent, screen)
    agent.chord("AltLeft", "F4")  # paced (CHORD_STEP_S): one instantaneous batch is ignored
    time.sleep(3)
    log("close requested (Alt+F4)")


def client_absent(screen: Screen) -> bool:
    """No client window at all: the strip its title bar would occupy (above the game region) is
    the bare black desktop. A lost-D3D client renders a black GAME region but still draws its
    title bar, so this never mistakes it for a closed one (that would launch a second client)."""
    x, y, w, _ = game_region()
    _, img = screen.grab(x, y - 30, w, 26)
    px = img[::2, ::4, :3].astype(np.uint16)
    luma = (px[..., 0] * 29 + px[..., 1] * 150 + px[..., 2] * 77) >> 8
    return bool((luma < 10).mean() >= 0.98)


def launch_client(agent: Agent, screen: Screen) -> None:
    """Double-click the desktop shortcut (a plain user action; it starts PoringLab.exe with
    __COMPAT_LAYER=RunAsInvoker, i.e. non-elevated)."""

    def visible() -> bool:  # the icon, plain or selected (highlighted after a double-click)
        return is_state(screen, "shortcut_icon") or (
            signature_path("shortcut_icon_sel").exists() and is_state(screen, "shortcut_icon_sel")
        )

    ensure_window("login", "launch")
    if not visible():
        agent.chord("MetaLeft", "KeyD")  # show the desktop: windows may cover the icon
        time.sleep(1.5)
    if not visible():
        to_png(screen.full(), SHOTS / "shortcut_not_visible.png")
        raise Stop("the desktop shortcut is not visible: no double-click")
    x, y = shortcut_xy()
    agent.move(x, y)
    time.sleep(0.1)
    for action in ("down", "up", "down", "up"):
        agent.send([{"type": "mouse_button", "t_mono_ns": ns(), "frame_id": -1, "button": "left",
                     "action": action, "x": x / desktop()[0], "y": y / desktop()[1]}])  # fmt: skip
        time.sleep(0.04)
    log("launch requested (desktop shortcut, non-elevated)")
    wait_state(screen, ["service_select", "login"], 90)


# The durable lab-client watcher (Batt, 2026-10-05): a scheduled task as the standard user runs
# %USERPROFILE%\poring-lab-watch\labwatch.ps1 (every 500 ms: a lab-client exe with a non-lab TCP
# connection is killed and logged; an `alive` line every ~60 s). Read-only status line:
WATCH_STATUS = (
    "$i = Get-ScheduledTaskInfo -TaskName 'poring-lab watch'; "
    "'task ' + (Get-ScheduledTask -TaskName 'poring-lab watch').State + ' last=' + $i.LastRunTime"
    " + ' result=' + $i.LastTaskResult; "
    "Get-Content (Join-Path $env:USERPROFILE 'poring-lab-watch\\watch.log') -Tail 3; "
    "'KILLED lines: ' + @(Select-String -Path (Join-Path $env:USERPROFILE "
    "'poring-lab-watch\\watch.log') -Pattern 'KILLED').Count; 'now ' + (Get-Date -f s)"
)

# The agent's own terminal (Batt, 2026-10-03): a desktop shortcut "poring-lab shell" ->
# `wt.exe -w new new-tab --title "poring-lab shell" --suppressApplicationTitle -d C:\RO-rAthena
# powershell.exe -NoLogo`, NOT "Run as administrator" (checked in the .lnk at creation). The Run
# dialog stays forbidden (Defender ClickFix); elevated consoles stay Batt's (UAC).
# SHELL_SHORTCUT="x,y" in .env.
SHELL_SHORTCUT = (37, 645)


def elevation_check(cells: int) -> str:
    """The check line; its marker is ``cells`` wide, a width no bar on screen has (fresh_cells),
    so a marker left by an earlier check can never pass for this one (2026-10-04: a stale green
    bar passed three checks typed into a `>>` prompt that never ran them)."""
    return (
        "cls; if (([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::"
        "GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) "
        f"{{ Write-Host (' ' * {cells}) -BackgroundColor DarkRed }} "
        f"else {{ Write-Host (' ' * {cells}) -BackgroundColor DarkGreen }}"
    )


MARKER_RED, MARKER_GREEN = (197, 15, 31), (19, 161, 14)  # Campbell DarkRed / DarkGreen
MARKER_PROOF = (136, 23, 152)  # Campbell DarkMagenta: type_line's proof bar, never a verdict colour
CELL_W = 9  # px per cell in the agent's shell: its 40-cell marker measured 360 px (2026-10-04)
MARKER_CELLS = range(24, 61)  # proof/marker widths: >= 150 px, and inside the console window


def shell_shortcut_xy() -> tuple[int, int]:
    raw = env().get("SHELL_SHORTCUT", "")
    if not raw:
        return SHELL_SHORTCUT
    x, y = (int(v) for v in raw.split(","))
    return x, y


def find_shell(screen: Screen) -> tuple[int, int, float] | None:
    """The ACTIVE "poring-lab shell" tab (its own templates only: RDP and stream), or None."""
    paths = [
        p for n in template_names(SHELL_TEMPLATE) if (p := STATE_DIR / "signatures" / n).exists()
    ]
    if not paths:
        raise Stop("no poring-lab shell template: run `ro_agent.py calibrate-shell` once")
    rgb = screen.full()[:, :, 2::-1].astype(np.int16)
    best: tuple[int, int, float] | None = None
    for path in paths:
        found = _match_console(rgb, np.load(path).astype(np.int16))
        if found is not None and (best is None or found[2] < best[2]):
            best = found
    return best


def marker_runs(
    bgra: np.ndarray, colour: tuple[int, int, int], min_run: int = 150
) -> list[tuple[int, int]]:
    """(row, px) of the longest solid run of ``colour`` in every row that has one >= min_run."""
    hit = np.abs(bgra[:, :, 2::-1].astype(np.int16) - np.array(colour)).max(axis=2) <= 30
    out: list[tuple[int, int]] = []
    for y in np.nonzero(hit.sum(axis=1) >= min_run)[0]:
        row = np.concatenate(([0], hit[y].astype(np.int8), [0]))
        edges = np.flatnonzero(np.diff(row))
        longest = int((edges[1::2] - edges[::2]).max(initial=0))
        if longest >= min_run:
            out.append((int(y), longest))
    return out


def cells_match(px: int, cells: int) -> bool:
    return abs(px - cells * CELL_W) <= CELL_W // 2


def fresh_cells(
    bgra: np.ndarray, colours: tuple[tuple[int, int, int], ...], rng: random.Random | None = None
) -> int:
    """A marker width (cells) within 1 cell of no bar of ``colours`` now on screen: a bar of this
    width can only come from the line about to be typed."""
    taken = {round(px / CELL_W) for c in colours for _, px in marker_runs(bgra, c)}
    free = [n for n in MARKER_CELLS if all(abs(n - t) > 1 for t in taken)]
    if not free:
        raise Stop("no free marker width (the console is full of bars): stopped")
    return (rng or random).choice(free)


def marker_colour(bgra: np.ndarray, min_run: int = 150, cells: int | None = None) -> str | None:
    """'red' / 'green' if a horizontal run of >= min_run marker pixels is on screen (the newest,
    bottom-most wins), else None. ``cells``: only a run of exactly that width counts."""
    found: tuple[int, str] | None = None
    for name, colour in (("red", MARKER_RED), ("green", MARKER_GREEN)):
        for y, px in marker_runs(bgra, colour, min_run):
            if cells is not None and not cells_match(px, cells):
                continue
            if found is None or y > found[0]:
                found = (y, name)
    return found[1] if found else None


def open_terminal(agent: Agent, screen: Screen) -> tuple[int, int]:
    """The agent's own NON-elevated terminal, in front: reuse a visible "poring-lab shell" tab, or
    double-click the shortcut and wait for one. Any mismatch stops (Batt: stop and ask)."""
    ensure_window("desktop", "open-terminal")
    found = find_shell(screen)
    if found is None:

        def visible() -> bool:
            return is_state(screen, "shell_shortcut_icon") or (
                signature_path("shell_shortcut_icon_sel").exists()
                and is_state(screen, "shell_shortcut_icon_sel")
            )

        if not visible():
            to_png(screen.full(), SHOTS / "shell_shortcut_not_visible.png")
            raise Stop("the 'poring-lab shell' shortcut is not visible: nothing clicked")
        x, y = shell_shortcut_xy()
        agent.move(x, y)
        time.sleep(0.1)
        for action in ("down", "up", "down", "up"):
            agent.send([{"type": "mouse_button", "t_mono_ns": ns(), "frame_id": -1,
                         "button": "left", "action": action, "x": x / desktop()[0],
                         "y": y / desktop()[1]}])  # fmt: skip
            time.sleep(0.04)
        deadline = time.monotonic() + 20
        while found is None and time.monotonic() < deadline:
            time.sleep(1)
            found = find_shell(screen)
        if found is None:
            to_png(screen.full(), SHOTS / "shell_not_found.png")
            raise Stop("no window titled 'poring-lab shell' within 20 s: nothing typed")
        log("opened 'poring-lab shell' (desktop shortcut)")
        opened_new = True
    else:
        opened_new = False
    ox, oy, _ = found
    agent.click(ox + 75, oy + 9)  # its tab: focuses that window
    time.sleep(0.4)
    again = find_shell(screen)
    if again is None or abs(again[0] - ox) > 2 or abs(again[1] - oy) > 2:
        raise Stop("'poring-lab shell' moved or lost focus after the click: nothing typed")
    agent.keys("Escape")  # drop any half-typed input first (type_line's docstring)
    time.sleep(0.2)
    cells = fresh_cells(screen.full(), (MARKER_RED, MARKER_GREEN))
    agent.type_text(elevation_check(cells) + "\n")
    deadline = time.monotonic() + 10
    colour = None
    while colour is None and time.monotonic() < deadline:
        time.sleep(0.8)
        colour = marker_colour(screen.full(), cells=cells)
    if colour != "green":
        to_png(screen.full(), SHOTS / "shell_elevation_check.png")
        raise Stop(f"'poring-lab shell' is not verified non-elevated (marker {colour}): stop")
    log("'poring-lab shell' is in front and NOT elevated")
    if opened_new:  # an older one was minimised or hidden: keep exactly one (Batt, 2026-10-03)
        type_line(agent, screen, CLOSE_EXTRA_SHELLS)
        time.sleep(3)
        log("closed any other 'poring-lab shell' window (see the shell for the count)")
    return ox, oy


# Exactly one agent terminal (Batt, 2026-10-03): open_terminal opens a NEW window whenever the old
# one is minimised. Typed into the verified front shell: every OTHER top-level window titled
# exactly "poring-lab shell" gets WM_CLOSE (a one-tab Windows Terminal window closes); Batt's own
# consoles have other titles and the foreground window is never touched. Then the count.
CLOSE_EXTRA_SHELLS = (
    "cls; Add-Type -TypeDefinition 'using System;using System.Text;using System.Runtime."
    "InteropServices;public class PlShells{public delegate bool P(IntPtr h,IntPtr l);"
    '[DllImport("user32.dll")]public static extern bool EnumWindows(P p,IntPtr l);'
    '[DllImport("user32.dll")]public static extern int GetWindowText(IntPtr h,StringBuilder s,'
    'int n);[DllImport("user32.dll")]public static extern IntPtr GetForegroundWindow();'
    '[DllImport("user32.dll")]public static extern bool PostMessage(IntPtr h,uint m,IntPtr w,'
    "IntPtr l);}' -ErrorAction SilentlyContinue; "
    "function Get-PlShells { $hs = New-Object System.Collections.ArrayList; "
    "[void][PlShells]::EnumWindows({ param($h, $l) $sb = New-Object System.Text.StringBuilder 256; "
    "[void][PlShells]::GetWindowText($h, $sb, 256); "
    "if ($sb.ToString() -ceq 'poring-lab shell') { [void]$hs.Add($h) }; $true }, [IntPtr]::Zero); "
    "$hs }; $fg = [PlShells]::GetForegroundWindow(); $before = @(Get-PlShells); "
    "$before | Where-Object { $_ -ne $fg } | ForEach-Object { "
    "[void][PlShells]::PostMessage($_, 0x10, [IntPtr]::Zero, [IntPtr]::Zero) }; "
    "Start-Sleep 2; 'poring-lab shell windows: ' + $before.Count + ' -> ' + @(Get-PlShells).Count"
)


def file_check_command(path: str) -> str:
    """The read-only check typed before Batt is asked to drop a file (Batt, 2026-10-03)."""
    if "'" in path:
        raise Stop("a path with a single quote: check it by hand")
    return (
        f"cls; $p = '{path}'; $i = Get-Item -LiteralPath $p -ErrorAction Stop; "
        "'{0}  {1:N0} B  {2}  sha256 {3}' -f $i.FullName, $i.Length, $i.LastWriteTime, "
        "(Get-FileHash -LiteralPath $p).Hash"
    )


def copy_item_line(path: str) -> str:
    """The ready line Batt pastes into HIS console to drop the file (never the agent's)."""
    return f"Copy-Item -LiteralPath '{path}' -Destination " + r"'\\tsclient\transfer\'"


def calibrate_shell(screen: Screen, stream: bool = False) -> None:
    """Once, with a fresh 'poring-lab shell' window ACTIVE and its shortcut visible: save its tab
    template (located by the PowerShell tab icon) and the shortcut icon's signature. ``stream``:
    the console stream's copy of the tab template only (cut while streaming)."""
    rgb = screen.full()[:, :, 2::-1]
    ps = np.load(STATE_DIR / "signatures" / "ps_tab_template.npy")
    icon_only = ps[:, :24].astype(np.int16)  # the PowerShell icon (columns 3-18), no title text
    found = _match_console(rgb.astype(np.int16), icon_only)
    if found is None:
        raise Stop("no active PowerShell tab icon on screen: open 'poring-lab shell' first")
    ox, oy, _ = found
    h, w = ps.shape[:2]
    crop = np.ascontiguousarray(rgb[oy : oy + h, ox : ox + w]).astype(np.uint8)
    name = template_names(SHELL_TEMPLATE)[1 if stream else 0]
    np.save(STATE_DIR / "signatures" / name, crop)
    if stream:
        log(f"stream shell tab template saved at ({ox},{oy}) as {name}")
        return
    to_png(np.dstack([crop[..., ::-1], np.full(crop.shape[:2], 255, np.uint8)]),
           SHOTS / "sig_shell_tab.png")  # fmt: skip
    for state in ("shell_shortcut_icon_sel",):
        calibrate(screen, state)
    log(f"shell tab template saved at ({ox},{oy}); icon signature saved")


def recover(which: str, retries: int = 2, agent_id: str = "ro_agent-recover") -> None:
    """Close, relaunch and log in ``which``. ``retries``: further attempts after a failure (the
    auto recover after a sniffer restart passes 0: one attempt, no loop). ``agent_id`` names the
    connection in the backend's input log (agent_hello) and on the console."""
    for attempt in range(1, retries + 2):
        try:
            with session(agent_id) as (agent, screen):
                agent.wait_for_human()
                if client_absent(screen):  # 2026-10-04: a previous attempt had closed it already
                    log(f"recover attempt {attempt}: no client window: launching")
                else:
                    log(f"recover attempt {attempt}: closing the client")
                    close_client(agent, screen)
                launch_client(agent, screen)
                login(agent, screen, which)
                return
        except Stop as exc:
            log(f"recover attempt {attempt} failed: {exc}")
            if attempt > retries or "ASSIST" in str(exc) or "refused" in str(exc):
                raise
            time.sleep(10)


def status() -> None:
    out: dict[str, Any] = {"online_total": any_online()}
    for which in ("player", "gm"):
        with contextlib.suppress(Stop):
            out[f"{which}_online"] = bool(online_chars(which))
    screen = Screen()
    try:
        states = sorted(p.stem for p in (STATE_DIR / "signatures").glob("*.npy"))
        dist = {}
        for s in states:
            with contextlib.suppress(Stop):
                dist[s] = round(distance(screen, s), 1)
        out["signature_distance"] = dist
    finally:
        screen.close()
    print(json.dumps(out, indent=1))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("cmd")
    ap.add_argument("args", nargs="*")
    ap.add_argument("--right", action="store_true")
    ap.add_argument("--admin", action="store_true", help="console: the Administrator tab template")
    ap.add_argument("--abs", action="store_true", help="click: desktop pixels, not client-relative")
    ap.add_argument("--thai-keys", action="store_true")
    ap.add_argument("--stream", action="store_true", help="calibrate-shell: the stream's copy")
    ap.add_argument("--as", dest="who", default="gm", choices=["player", "gm"])
    ap.add_argument("--retries", type=int, default=2, help="recover: attempts after a failure")
    ap.add_argument(
        "--agent-id",
        default="ro_agent-recover",
        help="recover: the agent id the backend logs (auto_recover: guarded_build)",
    )
    ap.add_argument(
        "--profile", choices=sorted(PROFILES), default=None,
        help="client profile: kro (default) or th (C:\\RO-rAthena-th + rathena-th)",
    )  # fmt: skip
    a = ap.parse_args()
    use_profile(a.profile)
    cmd, args = a.cmd, a.args
    if cmd == "status":
        return status()
    if cmd in ("shot", "crop", "calibrate", "where"):
        screen = Screen()
        try:
            if cmd == "shot":
                print(to_png(screen.full(), SHOTS / f"{args[0]}.png"))
            elif cmd == "crop":  # crop NAME X Y W H (desktop pixels)
                x, y, w, h = (int(v) for v in args[1:5])
                print(to_png(screen.grab(x, y, w, h)[1], SHOTS / f"{args[0]}.png"))
            elif cmd == "calibrate":
                calibrate(screen, args[0], [int(v) for v in args[1:5]] if len(args) == 5 else None)
            else:
                for st in sorted(p.stem for p in (STATE_DIR / "signatures").glob("*.npy")):
                    print(f"{st:16} {distance(screen, st):6.1f}")
        finally:
            screen.close()
        return None
    if cmd == "recover":
        if a.retries < 0 or not re.fullmatch(r"[A-Za-z0-9_.-]{1,64}", a.agent_id):
            raise Stop("recover: --retries >= 0, --agent-id letters/digits/_.- (<= 64)")
        return recover(args[0] if args else "player", a.retries, a.agent_id)
    with session() as (agent, screen):
        if cmd == "click":
            xy = (int(args[0]), int(args[1]))
            agent.click(*(xy if a.abs else at(*xy)), "right" if a.right else "left")
        elif cmd == "open-terminal":
            open_terminal(agent, screen)
        elif cmd == "calibrate-shell":
            calibrate_shell(screen, stream=a.stream)
        elif cmd == "close-extra-shells":
            open_terminal(agent, screen)
            console_type(agent, screen, CLOSE_EXTRA_SHELLS)
            time.sleep(4)
            print(to_png(screen.full(), SHOTS / "close_extra_shells.png"))
        elif cmd == "minimize-consoles":
            minimize_consoles(agent, screen)
        elif cmd == "watch-status":  # the durable watcher (scheduled task; Batt 2026-10-05)
            open_terminal(agent, screen)
            console_type(agent, screen, WATCH_STATUS)
            time.sleep(3)
            print(to_png(screen.full(), SHOTS / "watch_status.png"))
        elif cmd == "file-check":  # file-check "<windows path>": BEFORE asking Batt for a drop
            open_terminal(agent, screen)
            console_type(agent, screen, file_check_command(args[0]))
            time.sleep(4)
            print(to_png(screen.full(), SHOTS / "file_check.png"))
            print("for Batt's console: " + copy_item_line(args[0]))
        elif cmd == "drag":
            x1, y1, x2, y2 = (int(v) for v in args[:4])
            p1, p2 = ((x1, y1), (x2, y2)) if a.abs else (at(x1, y1), at(x2, y2))
            agent.drag(*p1, *p2, "right" if a.right else "left")
        elif cmd == "keys":
            agent.keys(*args)
        elif cmd == "chord":
            agent.chord(*args)
        elif cmd == "type":
            agent.type_text(args[0].replace("\\n", "\n"))
        elif cmd == "login":
            login(agent, screen, args[0])
        elif cmd == "to-char-select":
            to_char_select(agent, screen, args[0])
        elif cmd == "create-char":
            create_char(agent, screen, args[0])
        elif cmd == "enter-game":
            enter_game(agent, screen, args[0])
        elif cmd == "console-secret":  # console-secret VAR [--admin]
            console_secret(agent, screen, args[0], a.admin)
        elif cmd == "console":  # console "<command>" [shot-name] [wait-s] [--admin]
            console_type(agent, screen, args[0], a.admin)
            time.sleep(float(args[2]) if len(args) > 2 else 2.0)
            if len(args) > 1 and args[1] != "-":
                to_png(screen.full(), SHOTS / f"{args[1]}.png")
        elif cmd == "gm":
            gm(agent, screen, args[0])
        elif cmd == "say":
            say(agent, screen, a.who, args[0], a.thai_keys)
        elif cmd == "close":
            close_client(agent, screen)
        elif cmd == "launch":
            launch_client(agent, screen)
        else:
            raise Stop(f"unknown command {cmd}")
    return None


if __name__ == "__main__":
    try:
        main()
    except Stop as stop:
        print(f"STOP: {stop}", file=sys.stderr)
        sys.exit(3)
