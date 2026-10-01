#!/usr/bin/env python3
"""The agent's operator tool for the lab's rAthena client: log in, create a character, recover a
black client, run GM validation queries and short measurement moves. There is NO play loop.

Rules it enforces (CLAUDE.md, ADR-0002/0006):
  * input only through the backend's /internal/agent (source=bot), so every event passes the mux;
  * refuses unless the mux is in ASSIST (Batt sets it); waits while a human lease is active;
    stops at once (exit 3) on any refusal -- it never fights the human;
  * credentials come from .env and are typed as SENSITIVE batches (the input log keeps only counts
    and timing); they are never printed, logged or passed on a command line;
  * before typing: the expected screen must be showing (a signature of the client area, or the
    Run dialog), and before credentials the keyboard layout must be ENG (tray signature);
  * in-game input only while OUR rAthena shows the account online=1;
  * Windows commands go through the Run dialog as one-liners and touch only PoringLab.exe (the
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
TRAY_LANG = (1098, 764, 36, 22)  # the ENG / ไทย indicator, left of the clock (1280x800 desktop)
RUN_DIALOG = (16, 537, 396, 90)  # Win+R dialog title + text (constant), bottom-left
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
        return TRAY_LANG
    if state == "run_dialog":
        return RUN_DIALOG
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
    to_png(img, SHOTS / f"sig_{state}.png")
    log(f"signature {state} saved ({img.shape[1]}x{img.shape[0]})")


def distance(screen: Screen, state: str) -> float:
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

CLOSE_CMD = (
    f'powershell -NoP -W Hidden -C "$p=Get-Process {EXE} -EA 0;if($p){{$p.CloseMainWindow()'
    '|Out-Null;if(!$p.WaitForExit(10000)){$p.Kill()}}"'
)
LAUNCH_CMD = f'cmd /c "set __COMPAT_LAYER=RunAsInvoker&& start "" /D {CLIENT} {CLIENT}\\{EXE}.exe"'


def run_dialog(agent: Agent, screen: Screen, command: str) -> None:
    """Win+R, verify the Run dialog is up (foreground check), type, Enter."""
    agent.chord("MetaLeft", "KeyR")
    end = time.monotonic() + 5
    while not is_state(screen, "run_dialog"):
        if time.monotonic() > end:
            to_png(screen.full(), SHOTS / "run_dialog_missing.png")
            raise Stop("the Run dialog did not appear: nothing typed")
        time.sleep(0.2)
    time.sleep(0.3)
    agent.chord("ControlLeft", "KeyA")  # replace whatever the dialog remembered
    agent.type_text(command)
    agent.keys("Enter")


# --- commands -------------------------------------------------------------------------------------


def require_eng(screen: Screen) -> None:
    if not is_state(screen, "eng"):
        to_png(screen.full(), SHOTS / "layout_not_eng.png")
        raise Stop("keyboard layout is not ENG (tray): no credentials typed")


def activate_client(agent: Agent) -> None:
    """Click the client's own title bar: it becomes the foreground window (a freshly launched
    or uncovered window takes its first click as activation)."""
    x, y, w, _ = game_region()
    agent.click(x + w // 2, y - 15)
    time.sleep(0.3)


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
    activate_client(agent)
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
    if not signature_path("server_select").exists():  # calibrating: look, don't wait
        time.sleep(2.5)
        log(f"post-login screen saved: {to_png(screen.full(), SHOTS / 'post_login.png')}")
        return
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
    agent.type_text(command + "\n")
    log(f"gm: {command}")


def say(agent: Agent, screen: Screen, which: str, text: str, thai_keys: bool) -> None:
    _, _, char = account(which)
    if char not in online_chars(which):
        raise Stop(f"{which} is not online=1: nothing sent")
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


def close_client(agent: Agent, screen: Screen) -> None:
    run_dialog(agent, screen, CLOSE_CMD)
    log("close requested (CloseMainWindow, kill after 10 s)")
    time.sleep(12)


def launch_client(agent: Agent, screen: Screen) -> None:
    run_dialog(agent, screen, LAUNCH_CMD)
    log("launch requested (non-elevated)")
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
    ap.add_argument("--abs", action="store_true", help="click: desktop pixels, not client-relative")
    ap.add_argument("--thai-keys", action="store_true")
    ap.add_argument("--as", dest="who", default="gm", choices=["player", "gm"])
    a = ap.parse_args()
    cmd, args = a.cmd, a.args
    if cmd == "status":
        return status()
    if cmd in ("shot", "calibrate", "where"):
        screen = Screen()
        try:
            if cmd == "shot":
                print(to_png(screen.full(), SHOTS / f"{args[0]}.png"))
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
