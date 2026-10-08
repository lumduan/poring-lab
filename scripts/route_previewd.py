#!/usr/bin/env python3
"""The live route previewer as a daemon (Batt, 2026-10-08): it subscribes to the route plan channel
(route_plan.py) and draws every walk run's route anchored to the world. Rules no longer draw it.

    route_previewd.py [--sock PATH] [--hz 20]       (a rule's PlanPublisher starts it when needed)

- **One at a time:** it holds an exclusive flock on PLAN_LOCK; a second copy exits at once.
- **Idle costs nothing:** with no active route it only waits on the socket. It grabs frames
  (ro_agent.Screen, which is the RDP frame bus after the backend restart, else X) and runs
  route_preview.PreviewCore only while a route is active.
- **Exit:** after IDLE_EXIT_S with no message at all. The next rule starts a new one.
- **Its state follows the rule's session:** a route from a new session, map or camera builds a
  fresh PreviewCore. walk / snap / fix / clear from any other session are ignored, so a stale
  publisher cannot move the line.
- **Output:** the same live RoutePreview messages as route_demo's LivePreview
  (route_preview.message), on its own agent connection.
  - Display only: a send that fails reconnects later and never stops anything.
  - With `log` in the route message, it appends each message and its measurements to that file
    (route_demo's offline check). The default is no log.
"""

from __future__ import annotations

import argparse
import contextlib
import fcntl
import json
import select
import signal
import socket
import sys
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import route_plan as plan  # noqa: E402

IDLE_EXIT_S = 1800.0  # no message for 30 min: exit
RECONNECT_S = 5.0  # a failed agent connection is retried after this
IDLE_WAIT_S = 1.0


def make_core(msg: dict[str, Any]) -> Any:
    """A PreviewCore for a route message: its camera, and the map's GAT (cached per map)."""
    import numpy as np
    import route_preview as rp

    from poring_dataset import camera as cam

    camera = cam.Camera.from_vector(np.asarray(msg["camera"]["vector"], dtype=float),
                                    int(msg["camera"]["height"]))  # fmt: skip
    return rp.PreviewCore(camera, _gat(str(msg["map"])), msg["region"], msg["desktop"],
                          str(msg.get("label", "")))  # fmt: skip


_GATS: dict[str, Any] = {}


def _gat(map_name: str) -> Any:
    if map_name not in _GATS:
        from poring_dataset import camera as cam
        from poring_dataset import gat as gatmod

        if "/" in map_name or map_name.startswith("."):
            raise ValueError(f"bad map name {map_name!r}")
        _GATS[map_name] = gatmod.parse((cam.GAT_DIR / f"{map_name}.gat").read_bytes())
    return _GATS[map_name]


class Previewd:
    """The daemon's state machine, one plan message at a time (testable without a socket)."""

    def __init__(self, core_factory: Callable[[dict[str, Any]], Any] = make_core,
                 clock: Callable[[], float] = time.monotonic) -> None:  # fmt: skip
        self.core_factory = core_factory
        self.clock = clock
        self.core: Any = None
        self.key: tuple[Any, ...] | None = None
        self.session: str | None = None
        self.region: tuple[int, int, int, int] | None = None
        self.log_path: str | None = None
        self.last_msg = clock()
        self.handled = 0
        self.ignored = 0

    @property
    def active(self) -> bool:
        return self.core is not None and bool(self.core.active)

    def idle_too_long(self, idle_exit_s: float = IDLE_EXIT_S) -> bool:
        return not self.active and self.clock() - self.last_msg > idle_exit_s

    def handle(self, msg: dict[str, Any]) -> dict[str, Any] | None:
        """Apply one message; returns a body to send at once (the empty one of a clear), else
        None."""
        self.last_msg = self.clock()
        cmd = msg["cmd"]
        if cmd == "ping":
            return None
        try:
            if cmd == "route":
                self._route(msg)
                return None
            if self.core is None or msg.get("session") != self.session:
                self.ignored += 1  # nothing to anchor it to, or another (stale) publisher
                return None
            self.handled += 1
            if cmd == "walk":
                self.core.walk(msg["start"], msg["path"], float(msg["ms_per_cell"]),
                               int(msg["t_click_ns"]))  # fmt: skip
            elif cmd == "snap":
                self.core.snap(msg["cell"])
            elif cmd == "fix":
                self.core.snap_fix(msg["cell"])
            elif cmd == "clear":
                body: dict[str, Any] = self.core.clear()
                return body
        except (KeyError, TypeError, ValueError, OSError) as exc:  # a malformed message: skip it
            self.ignored += 1
            print(f"{time.strftime('%H:%M:%S')} ignored {cmd}: {exc}", flush=True)
        return None

    def _route(self, msg: dict[str, Any]) -> None:
        key = (msg.get("session"), msg["map"], tuple(msg["camera"]["vector"]),
               msg["camera"]["height"], tuple(msg["region"]), tuple(msg["desktop"]))  # fmt: skip
        if self.core is None or key != self.key:
            self.core, self.key = self.core_factory(msg), key
            self.session = msg.get("session")
            self.region = tuple(int(v) for v in msg["region"])  # type: ignore[assignment]
        self.core.label = str(msg.get("label", ""))[:64]
        self.log_path = msg.get("log")
        self.core.set_route(msg["position"], msg["corners"], msg["goal"], msg.get("click"))
        self.handled += 1


class Output:
    """The agent connection and the frame grabber, opened lazily, re-opened after a failure."""

    def __init__(self) -> None:
        self.agent: Any = None
        self.screen: Any = None
        self.retry_at = 0.0
        self._log: Any = None
        self._log_path: str | None = None

    def _open(self) -> bool:
        if self.agent is not None and self.screen is not None:
            return True
        if time.monotonic() < self.retry_at:
            return False
        import ro_agent as r

        try:
            if self.agent is None:
                self.agent = r.Agent("route-preview")
            if self.screen is None:
                self.screen = r.Screen()
            return True
        except Exception as exc:  # noqa: BLE001 -- not ASSIST, backend down, ...
            print(f"{time.strftime('%H:%M:%S')} output unavailable ({exc}); retry in "
                  f"{RECONNECT_S:.0f} s", flush=True)  # fmt: skip
            self.close()
            self.retry_at = time.monotonic() + RECONNECT_S
            return False

    def grab(self, region: tuple[int, int, int, int]) -> tuple[int, Any] | None:
        if not self._open():
            return None
        try:
            t, img = self.screen.grab(*region)
            return int(t), img
        except Exception:  # noqa: BLE001
            self.close()
            self.retry_at = time.monotonic() + RECONNECT_S
            return None

    def send(self, msg: dict[str, Any], meas: dict[str, Any] | None, log_path: str | None) -> None:
        if self.agent is not None:
            try:
                self.agent.ws.send(json.dumps(msg))
            except Exception:  # noqa: BLE001 -- display only
                self.close()
                self.retry_at = time.monotonic() + RECONNECT_S
        if log_path:
            if log_path != self._log_path:
                if self._log is not None:
                    self._log.close()
                self._log, self._log_path = open(log_path, "a"), log_path  # noqa: SIM115
            self._log.write(json.dumps({**msg, "measured": meas}) + "\n")

    def drain(self) -> None:
        if self.agent is None:
            return
        with contextlib.suppress(Exception):  # the backend's status messages: drop them
            while True:
                self.agent.ws.recv(timeout=0)

    def close(self) -> None:
        with contextlib.suppress(Exception):
            if self.agent is not None:
                self.agent.ws.close()
        with contextlib.suppress(Exception):
            if self.screen is not None:
                self.screen.close()
        self.agent = self.screen = None

    def close_log(self) -> None:
        if self._log is not None:
            self._log.close()
        self._log, self._log_path = None, None


def serve(sock_path: Path, hz: float) -> int:
    import route_preview as rp

    sock_path.parent.mkdir(parents=True, exist_ok=True)
    lock = open(plan.PLAN_LOCK, "w")  # noqa: SIM115 -- held for the process's life
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        print(f"{time.strftime('%H:%M:%S')} another previewer runs: exiting", flush=True)
        return 0
    with contextlib.suppress(FileNotFoundError):
        sock_path.unlink()  # a stale socket from a previewer that died (we hold the lock)
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
    sock.bind(str(sock_path))
    sock.setblocking(False)
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))  # run the cleanup below
    pd, out = Previewd(), Output()
    print(f"{time.strftime('%H:%M:%S')} previewer listening on {sock_path} at {hz:g} Hz",
          flush=True)  # fmt: skip
    try:
        while True:
            t0 = time.monotonic()
            while True:  # every queued plan message, in order
                try:
                    data = sock.recv(plan.MAX_DATAGRAM)
                except BlockingIOError:
                    break
                msg = plan.decode(data)
                if msg is None:
                    continue
                body = pd.handle(msg)
                if body is not None:
                    out.send(rp.message(body, pd.core.label), None, pd.log_path)
            if pd.active and pd.region is not None:
                got = out.grab(pd.region)
                if got is not None:
                    t, img = got
                    t1 = time.monotonic()
                    body = pd.core.step(t, img)
                    pd.core.last["step_ms"] = round(1000 * (time.monotonic() - t1), 1)
                    if body is not None:
                        out.send(rp.message(body, pd.core.label), pd.core.last, pd.log_path)
                out.drain()
                wait = 1.0 / hz - (time.monotonic() - t0)
            else:
                out.close_log()
                if pd.idle_too_long():
                    print(f"{time.strftime('%H:%M:%S')} idle {IDLE_EXIT_S:.0f} s: exiting",
                          flush=True)  # fmt: skip
                    return 0
                out.drain()
                wait = IDLE_WAIT_S
            select.select([sock], [], [], max(0.0, wait))
    finally:
        out.close()
        out.close_log()
        sock.close()
        with contextlib.suppress(FileNotFoundError):
            sock_path.unlink()
        lock.close()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--sock", type=Path, default=plan.PLAN_SOCK)
    ap.add_argument("--hz", type=float, default=20.0)
    a = ap.parse_args()
    return serve(a.sock, a.hz)


if __name__ == "__main__":
    sys.exit(main())
