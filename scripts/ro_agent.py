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
    ro_agent.py keys CODE...                    key taps (50 ms holds)
    ro_agent.py chord CODE...                   press in order, release in reverse
    ro_agent.py type TEXT                       US-layout ASCII into the focused field (+ \\n)
    ro_agent.py login player|gm                 login screen -> character in game, online=1
    ro_agent.py create-char player|gm           on an empty char-select slot (name from .env)
    ro_agent.py gm "@where"                     GM account only; logged to data/ro_agent/gm.jsonl
    ro_agent.py say [--thai-keys] TEXT          chat line (Thai: Kedmanee key positions)
    ro_agent.py close | launch | recover [player|gm]
    ro_agent.py walk DX DY                      one click-to-walk at a cell offset from the centre

Coordinates: GAME_REGION (.env, "x,y,w,h") is the client area; clicks are relative to its origin
(the same region the backend's black-screen detector watches).
"""

import argparse
import contextlib
import json
import struct
import subprocess
import sys
import time
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import numpy as np
from websockets.sync.client import ClientConnection, connect

ROOT = Path(__file__).resolve().parents[1]
STATE_DIR = ROOT / "data" / "ro_agent"  # gitignored (rule 4): signatures + GM command log
SHOTS = Path("/dev/shm/poring-lab-tmp/shots")
BACKEND = "poring-lab-backend-1"
DB = "poring-lab-db-1"
DESKTOP_W, DESKTOP_H = 1280, 800
HOLD_S = 0.05  # 50 ms holds: 20 ms registers 6/6 in the client (docs/client/rathena-client.md)
SHORTCUT_BOX = (80, 106, 64, 84)  # the "Ragnarok Offline" desktop icon + label
TRAY_LANG = (1098, 764, 36, 22)  # the ENG / ไทย indicator, left of the clock (1280x800 desktop)
CLIENT = r"C:\RO-rAthena\client"
EXE = "PoringLab"  # the rAthena copy ONLY (ADR-0006: the community client is never touched)
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
    prefix = {"player": "RATHENA_AGENT", "gm": "RATHENA_GM"}[which]
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

_HELPER = r"""
import struct, sys, time, mss
s = mss.MSS(display=":99")
out = sys.stdout.buffer
for line in sys.stdin:
    x, y, w, h = map(int, line.split())
    t = time.monotonic_ns()
    img = s.grab({"left": x, "top": y, "width": w, "height": h})
    out.write(struct.pack("<qII", t, img.width, img.height))
    out.write(img.raw)
    out.flush()
"""


class Screen:
    def __init__(self) -> None:
        self.proc = subprocess.Popen(
            ["docker", "exec", "-i", BACKEND, "python", "-u", "-c", _HELPER],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        )  # fmt: skip

    def grab(self, x: int, y: int, w: int, h: int) -> tuple[int, np.ndarray]:
        assert self.proc.stdin is not None and self.proc.stdout is not None
        self.proc.stdin.write(f"{x} {y} {w} {h}\n".encode())
        self.proc.stdin.flush()
        t, gw, gh = struct.unpack("<qII", self.proc.stdout.read(16))
        raw = self.proc.stdout.read(gw * gh * 4)
        return t, np.frombuffer(raw, np.uint8).reshape(gh, gw, 4)

    def full(self) -> np.ndarray:
        return self.grab(0, 0, DESKTOP_W, DESKTOP_H)[1]

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
        return TRAY_LANG
    if state in ("shortcut_icon", "shortcut_icon_sel"):
        x, y = shortcut_xy()
        return x - 32, y - 34, SHORTCUT_BOX[2], SHORTCUT_BOX[3]
    meta = signature_path(state).with_suffix(".json")
    x, y, w, h = game_region()
    if meta.exists():
        dx, dy, bw, bh = json.loads(meta.read_text())["box"]
        return x + dx, y + dy, bw, bh
    return x, y, w, h


def calibrate(screen: Screen, state: str, box: list[int] | None = None) -> None:
    path = signature_path(state)
    path.parent.mkdir(parents=True, exist_ok=True)
    if box is not None:
        path.with_suffix(".json").write_text(json.dumps({"box": box}))
    _, img = screen.grab(*region_for(state))
    np.save(path, grey_thumb(img))
    if state == "eng":  # full resolution, for the sliding tray search
        np.save(STATE_DIR / "signatures" / "eng_full.npy", _grey(img))
    to_png(img, SHOTS / f"sig_{state}.png")
    log(f"signature {state} saved ({img.shape[1]}x{img.shape[0]})")


TRAY_STRIP = (900, 764, 340, 22)  # where the ENG/ไทย indicator can sit (it moves with tray icons)


def _grey(img: np.ndarray) -> np.ndarray:
    px = img[:, :, :3].astype(np.float32)
    return px[..., 0] * 0.114 + px[..., 1] * 0.587 + px[..., 2] * 0.299


def eng_distance(screen: Screen) -> float:
    """Best match of the full-resolution ENG template anywhere in the tray strip: the indicator's
    x shifts as tray icons come and go (1086 vs 1115 on the same account, 2026-10-01)."""
    tmpl = np.load(STATE_DIR / "signatures" / "eng_full.npy")
    _, img = screen.grab(*TRAY_STRIP)
    strip = _grey(img)
    th, tw = tmpl.shape
    best = float("inf")
    for x in range(0, strip.shape[1] - tw + 1):
        best = min(best, float(np.abs(strip[:th, x : x + tw] - tmpl).mean()))
    return best


def distance(screen: Screen, state: str) -> float:
    if state == "eng" and (STATE_DIR / "signatures" / "eng_full.npy").exists():
        return eng_distance(screen)
    path = signature_path(state)
    if not path.exists():
        raise Stop(f"no signature for {state!r}: run `ro_agent.py calibrate {state}` first")
    ref = np.load(path)
    _, img = screen.grab(*region_for(state))
    cur = grey_thumb(img)
    if cur.shape != ref.shape:
        return float("inf")
    return float(np.abs(cur - ref).mean())


def is_state(screen: Screen, state: str) -> bool:
    return distance(screen, state) <= SIG_MATCH


def wait_state(screen: Screen, states: list[str], timeout: float) -> str:
    if not any(signature_path(st).exists() for st in states):  # first run: calibrating
        log(f"no signature yet for {states}: waiting {min(timeout, 25):.0f} s instead")
        time.sleep(min(timeout, 25))
        return "uncalibrated"
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        for st in states:
            if signature_path(st).exists() and is_state(screen, st):
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
    ip = subprocess.run(
        ["docker", "inspect", "-f", "{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}",
         BACKEND], capture_output=True, text=True, check=True,
    ).stdout.strip()  # fmt: skip
    return f"ws://{ip}:8001/internal/agent"


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


class Agent:
    """One /internal/agent connection; every send checks ASSIST and waits out a human lease."""

    def __init__(self, name: str = "ro_agent") -> None:
        self._conn = connect(backend_ws(), open_timeout=5, max_size=2**20)
        self.ws: ClientConnection = self._conn.__enter__()
        hello = {"type": "agent_hello", "t_mono_ns": ns(), "frame_id": -1, "agent_id": name,
                 "version": "1"}  # fmt: skip
        self.ws.send(json.dumps(hello))
        self.status: dict[str, Any] = {}
        self._drain(1.5, want="status")
        if self.status.get("mode") != "ASSIST":
            self.ws.close()
            raise Stop(f"mux mode is {self.status.get('mode')}, not ASSIST: no input sent")

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
                raise Stop(
                    f"mux refused {ack['dropped']}/{len(chunk)} ({ack['reasons']}): stopping"
                )

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
        self.send([key(c, "down") for c in codes] + [key(c, "up") for c in reversed(codes)])

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
                    "x": x / DESKTOP_W, "y": y / DESKTOP_H}])  # fmt: skip

    def click(self, x: int, y: int, button: str = "left") -> None:
        nx, ny = x / DESKTOP_W, y / DESKTOP_H
        self.move(x, y)
        time.sleep(HOLD_S)
        for action in ("down", "up"):
            self.send([{"type": "mouse_button", "t_mono_ns": ns(), "frame_id": -1,
                        "button": button, "action": action, "x": nx, "y": ny}])  # fmt: skip
            time.sleep(HOLD_S)

    def close(self) -> None:
        with contextlib.suppress(Exception):
            self.ws.close()


@contextlib.contextmanager
def session(name: str = "ro_agent") -> Iterator[tuple[Agent, Screen]]:
    screen = Screen()
    try:
        agent = Agent(name)
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


def find_console(screen: Screen, admin: bool = False) -> tuple[int, int, float] | None:
    """Locate an ACTIVE Windows PowerShell tab anywhere on screen by template (its icon + title),
    anchored on the icon's blue pixels. Returns (x, y, error) of the template origin, or None.
    A dark heuristic is not enough: the black wallpaper passed one (2026-10-01, Enter landed on
    the desktop and launched CPU-Z's UAC prompt -- declined)."""
    name = "ps_admin_tab_template.npy" if admin else "ps_tab_template.npy"
    path = STATE_DIR / "signatures" / name
    if not path.exists():
        raise Stop(f"no PowerShell tab template (data/ro_agent/signatures/{name})")
    tmpl = np.load(path).astype(np.int16)  # RGB
    th, tw = tmpl.shape[:2]
    blue_t = np.argwhere((tmpl[..., 2] > 150) & (tmpl[..., 0] < 110))
    ay, ax = (int(v) for v in blue_t[0])
    rgb = screen.full()[:, :, 2::-1].astype(np.int16)
    h, w = rgb.shape[:2]
    anchor = tmpl[ay, ax]
    cand = np.argwhere(np.abs(rgb - anchor).max(axis=2) <= 12)
    best: tuple[int, int, float] | None = None
    for y, x in cand[:5000]:
        oy, ox = int(y) - ay, int(x) - ax
        if oy < 0 or ox < 0 or oy + th > h or ox + tw > w:
            continue
        err = float(np.abs(rgb[oy : oy + th, ox : ox + tw] - tmpl).mean())
        if best is None or err < best[2]:
            best = (ox, oy, err)
    return best if best is not None and best[2] < 10 else None


def focus_console(agent: Agent, screen: Screen, admin: bool = False) -> tuple[int, int]:
    """Click the console's own tab and re-verify it is the active window; its tab origin."""
    found = find_console(screen, admin)
    if found is None:
        to_png(screen.full(), SHOTS / "console_missing.png")
        raise Stop("no active PowerShell console on screen: nothing typed")
    ox, oy, _ = found
    agent.click(ox + 75, oy + 9)  # its tab: focuses that window
    time.sleep(0.4)
    again = find_console(screen, admin)
    if again is None or abs(again[0] - ox) > 2 or abs(again[1] - oy) > 2:
        raise Stop("the console moved or lost focus after the click: nothing typed")
    return ox, oy


def console_type(agent: Agent, screen: Screen, command: str, admin: bool = False) -> None:
    """Type a NON-secret command line into the verified console (it lands in PSReadLine history,
    so never a credential: use console_secret for those)."""
    focus_console(agent, screen, admin)
    agent.type_text(command + "\n")


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
    agent.click(x + w // 2, y - 15)
    if not signature_path("client_title_active").exists():
        time.sleep(0.4)
        return
    end = time.monotonic() + 2.0  # the title repaints a beat after focus returns
    while not is_state(screen, "client_title_active"):
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
    if not is_state(screen, "chat_open"):
        agent.keys("Enter")
        time.sleep(1.0)
        if not is_state(screen, "chat_open"):
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
    raw = env().get("RO_SHORTCUT", "")
    if not raw:
        return SHORTCUT
    x, y = (int(v) for v in raw.split(","))
    return x, y


def close_client(agent: Agent, screen: Screen) -> None:  # noqa: ARG001
    """Alt+F4 on the client itself (a lost-D3D client still takes window messages); confirm the
    quit prompt if it shows. No PowerShell: Run-dialog PowerShell trips Defender's ClickFix
    detection (2026-10-01, severity 5, the processes were killed)."""
    activate_client(agent, screen)
    # Paced: an Alt+F4 injected as one instantaneous chord is ignored; 60 ms steps close it at once.
    for code, action in (("AltLeft", "down"), ("F4", "down"), ("F4", "up"), ("AltLeft", "up")):
        agent.send([key(code, action)])
        time.sleep(0.06)
    time.sleep(3)
    log("close requested (Alt+F4)")


def launch_client(agent: Agent, screen: Screen) -> None:
    """Double-click the desktop shortcut (a plain user action; it starts PoringLab.exe with
    __COMPAT_LAYER=RunAsInvoker, i.e. non-elevated)."""

    def visible() -> bool:  # the icon, plain or selected (highlighted after a double-click)
        return is_state(screen, "shortcut_icon") or (
            signature_path("shortcut_icon_sel").exists() and is_state(screen, "shortcut_icon_sel")
        )

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
                     "action": action, "x": x / DESKTOP_W, "y": y / DESKTOP_H}])  # fmt: skip
        time.sleep(0.04)
    log("launch requested (desktop shortcut, non-elevated)")
    wait_state(screen, ["service_select", "login"], 90)


def recover(which: str, retries: int = 2) -> None:
    for attempt in range(1, retries + 2):
        try:
            with session("ro_agent-recover") as (agent, screen):
                agent.wait_for_human()
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
    ap.add_argument("--as", dest="who", default="gm", choices=["player", "gm"])
    a = ap.parse_args()
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
        return recover(args[0] if args else "player")
    with session() as (agent, screen):
        if cmd == "click":
            xy = (int(args[0]), int(args[1]))
            agent.click(*(xy if a.abs else at(*xy)), "right" if a.right else "left")
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
