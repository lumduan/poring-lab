"""The route PLAN channel (Batt, 2026-10-08): walk rules publish their plan in CELLS, and the live
previewer (route_previewd.py) subscribes and draws it anchored to the world.

This replaces the one-shot RoutePreview, which a rule drew once in screen pixels: it stayed put
while the camera scrolled, so it floated off the character during the walk (Batt saw it during
walk@12). The console no longer draws one-shot previews (ffb5b82).

- **Transport:** one unix DATAGRAM socket, PLAN_SOCK, in /dev/shm (RAM, host processes only). Each
  datagram carries one JSON object.
- **Fire and forget:** a publish never blocks and never raises. It is display only, and the rule's
  walk never waits on its preview.
- **The previewer binds the socket.** A rule that finds no listener starts one (ensure_previewer,
  once per process). The previewer holds a lock, so only one runs.
- **What the messages carry:** what the previewer cannot know by itself, all in CELLS:
  - the map (for its GAT), the camera (its six numbers), the game region and the desktop size;
  - the route; the engine's walk from the click; the rule's believed cell; its /where fixes.
- **The rule side** (the bottom of this module): a run calls `enable` once, and the walk rules'
  `preview` IS `route_plan.preview`. The `hook_*` wrappers publish the engine's walk at each click,
  each /where fix, and the clear at each route's end, around the rule's own functions; they change
  no argument and no result. A rule that never enables publishes nothing: walk@8-11 (retired) keep
  their calls and show no line.

DISPLAY ONLY: nothing travels back to the rule, and no message can carry input.
"""

from __future__ import annotations

import contextlib
import functools
import json
import os
import socket
import subprocess
import sys
import time
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

PLAN_DIR = Path(os.environ.get("ROUTE_PLAN_DIR", "/dev/shm/poring-lab-route"))
PLAN_SOCK = PLAN_DIR / "plan.sock"
PLAN_LOCK = PLAN_DIR / "previewd.lock"
PREVIEWD_LOG = PLAN_DIR / "previewd.log"
START_WAIT_S = 5.0  # how long ensure_previewer waits for a new previewer's socket
MAX_DATAGRAM = 60_000  # a route of 64 cells is ~2 KB; anything near this is a bug

COMMANDS = ("route", "walk", "snap", "fix", "clear", "ping")
# The lab GM's walk speed (ms per cell; rAthena's default 150, verify.speed_before reads it
# offline): the previewer's model of the engine's walk after a click. Display only.
SELF_MS_PER_CELL = 150.0


def _cells(cells: Sequence[Sequence[float]]) -> list[list[int]]:
    return [[int(c[0]), int(c[1])] for c in cells]


def _cell(cell: Sequence[float] | None) -> list[int] | None:
    return None if cell is None else [int(cell[0]), int(cell[1])]


def camera_dict(camera: Any) -> dict[str, Any]:
    """The camera's six numbers + its height (poring_dataset.camera.Camera), JSON-safe."""
    return {"vector": [float(v) for v in camera.vector()], "height": int(camera.height)}


def encode(cmd: str, **body: Any) -> bytes:
    if cmd not in COMMANDS:
        raise ValueError(f"unknown plan command {cmd!r}")
    data = json.dumps({"cmd": cmd, "t_mono_ns": time.monotonic_ns(), **body},
                      separators=(",", ":")).encode()  # fmt: skip
    if len(data) > MAX_DATAGRAM:
        raise ValueError(f"plan message too large ({len(data)} bytes)")
    return data


def decode(data: bytes) -> dict[str, Any] | None:
    """One datagram -> its message, or None for anything malformed (never raises)."""
    try:
        msg = json.loads(data)
    except (ValueError, UnicodeDecodeError):
        return None
    if not isinstance(msg, dict) or msg.get("cmd") not in COMMANDS:
        return None
    return msg


class PlanPublisher:
    """A walk rule's side of the channel. Every method is fire and forget."""

    def __init__(self, session: str, *, sock_path: Path = PLAN_SOCK, autostart: bool = True,
                 log_path: str | None = None) -> None:  # fmt: skip
        self.session = session[:96]
        self.log_path = log_path  # the previewer appends its messages there (route_demo's check)
        self.sock_path = sock_path
        self.autostart = autostart
        self.sent = 0
        self.dropped = 0
        self._started = False
        self._sock = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
        self._sock.setblocking(False)

    # --- the plan ---------------------------------------------------------------------------
    def route(self, *, map_name: str, camera: Any, region: Sequence[int], desktop: Sequence[int],
              position: Sequence[int], corners: Sequence[Sequence[int]], goal: Sequence[int],
              click: Sequence[int] | None = None, label: str = "",
              log_path: str | None = None) -> None:  # fmt: skip
        """A new route (made at rest): where we stand, its corners, the goal, the next click."""
        if self.autostart and not self._started:
            self._started = True
            ensure_previewer(self.sock_path)
        self._send("route", map=map_name, camera=camera_dict(camera),
                   region=[int(v) for v in region], desktop=[int(v) for v in desktop],
                   position=_cell(position), corners=_cells(corners), goal=_cell(goal),
                   click=_cell(click), label=label[:64], log=log_path)  # fmt: skip

    def walk(self, start: Sequence[int], path: Sequence[Sequence[int]], ms_per_cell: float,
             t_click_ns: int) -> None:  # fmt: skip
        """The rule CLICKED at t_click_ns: the engine walks `path` (cells after start)."""
        self._send("walk", start=_cell(start), path=_cells(path), ms_per_cell=float(ms_per_cell),
                   t_click_ns=int(t_click_ns))  # fmt: skip

    def snap(self, cell: Sequence[int]) -> None:
        """The rule believes the step ends on `cell` (applied at the first rest after the move)."""
        self._send("snap", cell=_cell(cell))

    def fix(self, cell: Sequence[int]) -> None:
        """A /where fix: where we stand now."""
        self._send("fix", cell=_cell(cell))

    def clear(self) -> None:
        """The route ended (reached, declined or stopped)."""
        self._send("clear")

    def close(self) -> None:
        with contextlib.suppress(OSError):
            self._sock.close()

    def _send(self, cmd: str, **body: Any) -> None:
        try:
            self._sock.sendto(encode(cmd, session=self.session, **body), str(self.sock_path))
            self.sent += 1
        except (OSError, ValueError, TypeError):  # no previewer, a full queue, a bad value
            self.dropped += 1


def listening(sock_path: Path = PLAN_SOCK) -> bool:
    """True when a previewer receives on the socket (a ping is accepted)."""
    s = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
    try:
        s.setblocking(False)
        s.sendto(encode("ping"), str(sock_path))
        return True
    except OSError:
        return False
    finally:
        s.close()


def ensure_previewer(sock_path: Path = PLAN_SOCK, wait_s: float = START_WAIT_S) -> bool:
    """Start route_previewd.py, detached, unless one already listens. Never raises; returns whether
    a previewer listens afterwards (a rule walks on either way)."""
    try:
        if listening(sock_path):
            return True
        sock_path.parent.mkdir(parents=True, exist_ok=True)
        daemon = Path(__file__).resolve().parent / "route_previewd.py"
        with open(PREVIEWD_LOG, "a") as out:
            subprocess.Popen([sys.executable, str(daemon), "--sock", str(sock_path)],
                             stdin=subprocess.DEVNULL, stdout=out, stderr=subprocess.STDOUT,
                             start_new_session=True)  # fmt: skip
        end = time.monotonic() + wait_s
        while time.monotonic() < end:
            if listening(sock_path):
                return True
            time.sleep(0.05)
    except Exception:  # noqa: BLE001 -- display only: never a reason to stop a walk
        pass
    return False


# --- the rule side --------------------------------------------------------------------------------
_PUB: PlanPublisher | None = None
_MAP: str | None = None
_OWNER: object | None = None
_REGION: tuple[tuple[int, int, int, int], tuple[int, int]] | None = None


def enable(session: str, map_name: str, *, log_path: str | None = None,
           sock_path: Path = PLAN_SOCK) -> object | None:  # fmt: skip
    """Start publishing for this run. Returns a token for `disable`, or None when publishing was
    already enabled (an outer caller, e.g. route_demo with its log, keeps ownership)."""
    global _PUB, _MAP, _OWNER
    if _PUB is not None:
        return None
    _PUB = PlanPublisher(session, sock_path=sock_path, log_path=log_path)
    _MAP, _OWNER = map_name, object()
    return _OWNER


def disable(token: object | None) -> None:
    """Clear the line and stop publishing, if `token` enabled it (None: not ours, nothing)."""
    global _PUB, _MAP, _OWNER
    if token is None or token is not _OWNER or _PUB is None:
        return
    _PUB.clear()
    _PUB.close()
    _PUB, _MAP, _OWNER = None, None, None


def publisher() -> PlanPublisher | None:
    return _PUB


def _screen() -> tuple[tuple[int, int, int, int], tuple[int, int]]:
    global _REGION
    if _REGION is None:
        import ro_agent as r

        _REGION = (tuple(r.game_region()), tuple(r.desktop()))  # type: ignore[assignment]
    assert _REGION is not None
    return _REGION


def preview(agent: Any, w: Any, start: Sequence[int], wps: Sequence[Sequence[int]],
            click: Sequence[int] | None, label: str) -> None:  # fmt: skip
    """The walk rules' route preview (walk@8-12 call it under this signature when they plan a
    route): the route in CELLS to the previewer. Nothing when no run enabled publishing. Display
    only: never raises."""
    if _PUB is None or _MAP is None:
        return
    try:
        region, desktop = _screen()
        goal = wps[-1] if wps else start
        _PUB.route(map_name=_MAP, camera=w.camera, region=region, desktop=desktop,
                   position=w.position, corners=list(wps), goal=goal, click=click, label=label,
                   log_path=_PUB.log_path)  # fmt: skip
    except Exception:  # noqa: BLE001 -- the preview must never break the walk
        pass


Planner = Callable[[Any, tuple[int, int], tuple[int, int]], Sequence[Sequence[int]]]


def hook_click_step(fn: Callable[..., dict[str, Any]],
                    planner: Planner) -> Callable[..., dict[str, Any]]:  # fmt: skip
    """Around a rule's click_step(pr, w, end, ...): after a click, the engine's walk from the cell
    the rule stood on (planner(w, start, end): the cells the engine walks, computed AFTER the
    click, so the click's timing is unchanged); after the step, the rule's believed cell. The
    step's arguments and result are untouched."""

    @functools.wraps(fn)
    def step(pr: Any, w: Any, end: tuple[int, int], *a: Any, **k: Any) -> dict[str, Any]:
        if _PUB is None:
            return fn(pr, w, end, *a, **k)
        start = tuple(w.position)
        res = fn(pr, w, end, *a, **k)
        with contextlib.suppress(Exception):  # display only
            if res.get("clicked") and res.get("t_click"):
                path = list(planner(w, start, end)) or [end]
                _PUB.walk(start, path, SELF_MS_PER_CELL, int(res["t_click"]))
            _PUB.snap(w.position)
        return res

    return step


def hook_relocalise(factory: Callable[..., Callable[..., dict[str, Any]]]
                    ) -> Callable[..., Callable[..., dict[str, Any]]]:  # fmt: skip
    """Around where_relocalise(templates) -> fix(...): each confirmed /where fix ("ok", "to")."""

    @functools.wraps(factory)
    def make(*fa: Any, **fk: Any) -> Callable[..., dict[str, Any]]:
        fix = factory(*fa, **fk)

        @functools.wraps(fix)
        def wrapped(*a: Any, **k: Any) -> dict[str, Any]:
            rl = fix(*a, **k)
            if _PUB is not None and isinstance(rl, dict) and rl.get("ok") and rl.get("to"):
                with contextlib.suppress(Exception):
                    _PUB.fix(rl["to"])
            return rl

        return wrapped

    return make


def hook_route_end(fn: Callable[..., Any]) -> Callable[..., Any]:
    """Around walk_route(...): the line is cleared when the route ends, however it ends."""

    @functools.wraps(fn)
    def route(*a: Any, **k: Any) -> Any:
        try:
            return fn(*a, **k)
        finally:
            if _PUB is not None:
                _PUB.clear()

    return route
