"""Human-only clipboard paste into the ONE RDP session, plus a CLIPBOARD watchdog (ADR-0004).

One paste (verified live on FreeRDP 3.15 + Windows 11, 2026-09-30):
  1. This service's own X connection takes ownership of CLIPBOARD, offering the text as
     UTF8_STRING (and text/plain;charset=utf-8).
  2. xfreerdp, started with ``/clipboard:direction-to:remote,files-to:off``, sees the owner change
     through XFixes, asks us for TARGETS and announces a text format to Windows.
  3. The caller injects Ctrl+V through the input mux, as the human. Windows asks xfreerdp for the
     data; xfreerdp converts our selection and we serve it.
  4. We give up ownership, then SCRUB: take CLIPBOARD again offering nothing, so xfreerdp announces
     a fresh, empty text format that replaces Windows' copy, and give it up again.
     Releasing alone is NOT enough (ADR-0004 amendment, 2026-10-01): once a Windows app has pasted,
     the rendered text stays on the Windows clipboard. A password pasted at 12:10 was still
     pasteable at 13:04, and a 4-character paste still sat there 1 h 40 min later.

Watchdog: only this service may own CLIPBOARD. In text-to-remote mode xfreerdp never takes it
(Windows -> X is off), so any other owner -- e.g. another client on the X socket (ADR-0005) -- is
counted, logged and cleared at once. Only lengths are ever logged, never the text.

Threading: a python-xlib connection is not thread-safe, so one dedicated thread owns this
service's X connection. asyncio hands it commands through a queue plus a wake-up pipe, and gets
answers through futures resolved with ``call_soon_threadsafe``.
"""

import asyncio
import contextlib
import logging
import os
import queue
import select
import threading
import time
from collections import deque
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, Protocol

from Xlib import X, Xatom
from Xlib import display as xdisplay
from Xlib import error as xerror
from Xlib.ext import xfixes
from Xlib.protocol import event as xevent
from Xlib.protocol import request as xrequest

log = logging.getLogger(__name__)
# WM_CLASS class names of the RDP client (FreeRDP 3.x X11 client sets "xfreerdp").
RDP_CLIENT_CLASSES = frozenset({"xfreerdp"})

TEXT_TARGETS = ("UTF8_STRING", "text/plain;charset=utf-8")
OFFERED_TARGETS = ("TARGETS", *TEXT_TARGETS)


@dataclass(frozen=True, slots=True)
class PasteOutcome:
    ok: bool
    reason: str


# --- the X side, behind a small interface so the logic is testable without an X server ----------


@dataclass(frozen=True, slots=True)
class ConvertRequest:
    """Someone asked the CLIPBOARD owner (us) for ``target``."""

    target: str
    handle: Any = None  # adapter-private: the X event to answer


@dataclass(frozen=True, slots=True)
class OwnerChanged:
    """XFixes: CLIPBOARD has a new owner window (0 = none)."""

    owner: int


@dataclass(frozen=True, slots=True)
class OwnershipLost:
    """SelectionClear: another client took CLIPBOARD from us."""


type SelectionEvent = ConvertRequest | OwnerChanged | OwnershipLost


class SelectionIO(Protocol):
    @property
    def window(self) -> int: ...

    def fileno(self) -> int: ...

    def own(self) -> bool:
        """Take CLIPBOARD; True when we are the owner afterwards."""
        ...

    def release(self) -> None:
        """Set the owner to None if we own it."""
        ...

    def owner(self) -> int: ...

    def owner_class(self, window: int) -> str | None:
        """WM_CLASS class of the X client that owns ``window``: the window's own WM_CLASS, else the
        first top-level window of the same client (same XID resource base). None if unknown or
        already gone. Never cached: a new client can reuse a departed client's base."""
        ...

    def events(self) -> list[SelectionEvent]:
        """Every event pending right now (non-blocking)."""
        ...

    def reply_targets(self, request: ConvertRequest, targets: tuple[str, ...]) -> None: ...

    def reply_data(self, request: ConvertRequest, data: bytes) -> None: ...

    def refuse(self, request: ConvertRequest) -> None: ...

    def close(self) -> None: ...


def _window_id(value: object) -> int:
    return value if isinstance(value, int) else int(getattr(value, "id", 0))


def _wm_class(window: Any) -> str | None:
    cls = window.get_wm_class()
    return str(cls[1]) if cls else None


class XSelectionIO:
    """SelectionIO over python-xlib: an unmapped 1x1 window, CLIPBOARD, XFixes owner events."""

    def __init__(self, display: str | None = None) -> None:
        self._d = xdisplay.Display(display)
        if not self._d.has_extension("XFIXES"):
            self._d.close()
            raise RuntimeError(f"X display {display!r} has no XFIXES extension")
        self._d.xfixes_query_version()
        root = self._d.screen().root
        self._win = root.create_window(0, 0, 1, 1, 0, X.CopyFromParent)
        self._clipboard = self._d.intern_atom("CLIPBOARD")
        self._atoms: dict[str, int] = {}
        self._names: dict[int, str] = {}
        self._ignore = xerror.CatchError()  # a requestor window may vanish mid-reply
        self._d.xfixes_select_selection_input(
            root,
            self._clipboard,
            xfixes.XFixesSetSelectionOwnerNotifyMask
            | xfixes.XFixesSelectionWindowDestroyNotifyMask
            | xfixes.XFixesSelectionClientCloseNotifyMask,
        )
        self._d.sync()

    @property
    def window(self) -> int:
        return int(self._win.id)

    def fileno(self) -> int:
        return self._d.fileno()

    def _atom(self, name: str) -> int:
        if name not in self._atoms:
            self._atoms[name] = self._d.intern_atom(name)
        return self._atoms[name]

    def _name(self, atom: int) -> str:
        if atom not in self._names:
            self._names[atom] = self._d.get_atom_name(atom)
        return self._names[atom]

    def owner(self) -> int:
        return _window_id(self._d.get_selection_owner(self._clipboard))

    def owner_class(self, window: int) -> str | None:
        mask = int(self._d.display.info.resource_id_mask)
        base = window & ~mask
        try:
            found = _wm_class(self._d.create_resource_object("window", window))
            if found is None:
                # xfreerdp's cliprdr owns the selection through an unmapped helper window with no
                # WM_CLASS; its main window (same client) carries the class.
                for child in self._d.screen().root.query_tree().children:
                    if int(child.id) & ~mask == base:
                        found = _wm_class(child)
                        if found is not None:
                            break
        except (xerror.BadWindow, xerror.BadDrawable, xerror.BadValue):
            return None  # the owner (or a sibling) vanished mid-lookup
        return found

    def own(self) -> bool:
        self._win.set_selection_owner(self._clipboard, X.CurrentTime)
        return self.owner() == self.window

    def release(self) -> None:
        if self.owner() == self.window:
            xrequest.SetSelectionOwner(
                display=self._d.display,
                onerror=None,
                window=X.NONE,
                selection=self._clipboard,
                time=X.CurrentTime,
            )
            self._d.sync()

    def events(self) -> list[SelectionEvent]:
        out: list[SelectionEvent] = []
        while self._d.pending_events():
            e = self._d.next_event()
            if e.type == X.SelectionRequest:
                request = ConvertRequest(self._name(e.target), e)
                if e.selection == self._clipboard:
                    out.append(request)
                else:
                    self.refuse(request)  # PRIMARY etc.: we never own those
            elif e.type == X.SelectionClear:
                if e.atom == self._clipboard:  # python-xlib names this field "atom"
                    out.append(OwnershipLost())
            elif (
                # python-xlib clones extension event classes per display (type(...) in
                # extension_add_subevent), so match the base class plus the sub-code.
                isinstance(e, xfixes.SelectionNotify)
                and e.sub_code == xfixes.XFixesSetSelectionOwnerNotify
                and e.selection == self._clipboard
            ):
                out.append(OwnerChanged(_window_id(e.owner)))
        return out

    def _notify(self, e: Any, prop: int) -> None:
        notify = xevent.SelectionNotify(
            time=e.time,
            requestor=e.requestor,
            selection=e.selection,
            target=e.target,
            property=prop,
        )
        e.requestor.send_event(notify, onerror=self._ignore)
        self._d.flush()

    def reply_targets(self, request: ConvertRequest, targets: tuple[str, ...]) -> None:
        e = request.handle
        prop = e.property or e.target
        atoms = [self._atom(name) for name in targets]
        e.requestor.change_property(prop, Xatom.ATOM, 32, atoms, onerror=self._ignore)
        self._notify(e, prop)

    def reply_data(self, request: ConvertRequest, data: bytes) -> None:
        e = request.handle
        prop = e.property or e.target
        e.requestor.change_property(prop, e.target, 8, data, onerror=self._ignore)
        self._notify(e, prop)

    def refuse(self, request: ConvertRequest) -> None:
        self._notify(request.handle, X.NONE)

    def close(self) -> None:
        with contextlib.suppress(Exception):
            self._win.destroy()
        self._d.close()


# --- the service ----------------------------------------------------------------------------------


class _Job:
    """One paste. ``offered``/``done`` are resolved from the X thread via call_soon_threadsafe."""

    def __init__(self, data: bytes, loop: asyncio.AbstractEventLoop) -> None:
        self.data = data
        self.loop = loop
        self.offered: asyncio.Future[None] = loop.create_future()
        self.done: asyncio.Future[PasteOutcome] = loop.create_future()
        # X-thread state
        # queued -> waiting_targets -> offered -> injected -> served -> scrubbing
        self.state = "queued"
        self.deadline: float | None = None
        self.scrub_announced = False  # xfreerdp asked for TARGETS during the scrub

    def resolve_offered(self) -> None:
        with contextlib.suppress(RuntimeError):  # event loop already closed (shutdown)
            self.loop.call_soon_threadsafe(_set_result, self.offered, None)

    def resolve_done(self, outcome: PasteOutcome) -> None:
        with contextlib.suppress(RuntimeError):
            self.loop.call_soon_threadsafe(_set_result, self.done, outcome)


def _set_result[T](future: asyncio.Future[T], value: T) -> None:
    if not future.done():
        future.set_result(value)


class ClipboardService:
    """Serialises pastes and watches CLIPBOARD ownership on a dedicated X thread."""

    def __init__(
        self,
        io_factory: Callable[[], SelectionIO],
        *,
        targets_timeout_s: float = 2.0,
        settle_s: float = 0.5,
        data_timeout_s: float = 5.0,
        linger_s: float = 0.3,
        reconnect_s: float = 2.0,
        warn_interval_s: float = 10.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._io_factory = io_factory
        self._targets_timeout = targets_timeout_s
        self._settle = settle_s
        self._data_timeout = data_timeout_s
        self._linger = linger_s
        self._reconnect = reconnect_s
        self._warn_interval = warn_interval_s
        self._clock = clock
        self._commands: queue.SimpleQueue[tuple[str, _Job, str]] = queue.SimpleQueue()
        self._wake_r, self._wake_w = os.pipe()
        os.set_blocking(self._wake_r, False)
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._current: _Job | None = None
        self._waiting: deque[_Job] = deque()
        self._scrub_incomplete = 0
        self._connected = False
        self._foreign_clears = 0
        self._rdp_claims = 0
        self._last_rdp_note: float | None = None
        self._last_foreign_warning: float | None = None
        self._suppressed_foreign = 0
        self._x_warned = False

    # --- public, event-loop side ------------------------------------------------------------------

    @property
    def connected(self) -> bool:
        return self._connected

    @property
    def foreign_owner_clears(self) -> int:
        """CLIPBOARD claims by any X client other than the backend and xfreerdp: the alarm."""
        return self._foreign_clears

    @property
    def rdp_empty_claims(self) -> int:
        """CLIPBOARD claims by xfreerdp itself (FreeRDP 3.32+ claims it, with no data targets, on
        every Windows-side copy even in text-to-remote mode; ADR-0004 amendment b). Cleared like
        any other, but counted apart so ``foreign_owner_clears`` stays a clean alarm."""
        return self._rdp_claims

    @property
    def scrub_incomplete(self) -> int:
        """Pastes after which Windows' clipboard may still hold the text (never silent)."""
        return self._scrub_incomplete

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, name="clipboard-x", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._wake()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
        for fd in (self._wake_r, self._wake_w):
            with contextlib.suppress(OSError):
                os.close(fd)

    async def paste(self, text: str, inject: Callable[[], Awaitable[str | None]]) -> PasteOutcome:
        """Offer ``text`` as CLIPBOARD, let ``inject`` send Ctrl+V (it returns a refusal reason or
        None), serve the data, release. Never raises for X trouble: it becomes the outcome."""
        job = _Job(text.encode("utf-8"), asyncio.get_running_loop())
        self._send("paste", job)
        try:
            either: set[asyncio.Future[Any]] = {job.offered, job.done}
            await asyncio.wait(either, return_when=asyncio.FIRST_COMPLETED)
            if not job.done.done():
                await asyncio.sleep(self._settle)
            # Re-check after the settle: a job that already ended (ownership taken, X lost) must
            # never get a Ctrl+V -- it would paste whatever Windows or a foreign owner holds.
            if not job.done.done():
                refusal = await inject()
                self._send("abort" if refusal else "injected", job, refusal or "")
            # offer + serve, then the scrub (another TARGETS round and linger), with margin
            budget = 2 * self._targets_timeout + self._data_timeout + 2 * self._linger + 5.0
            return await asyncio.wait_for(asyncio.shield(job.done), budget)
        except TimeoutError:
            self._send("abort", job, "timeout")
            return PasteOutcome(False, "timeout")
        except asyncio.CancelledError:
            self._send("abort", job, "cancelled")
            raise

    # --- X thread -------------------------------------------------------------------------------

    def _send(self, command: str, job: _Job, reason: str = "") -> None:
        self._commands.put((command, job, reason))
        self._wake()

    def _wake(self) -> None:
        with contextlib.suppress(OSError):
            os.write(self._wake_w, b"x")

    def _drain_wake(self) -> None:
        with contextlib.suppress(BlockingIOError, OSError):
            while os.read(self._wake_r, 4096):
                pass

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                io = self._io_factory()
            except Exception as exc:
                if not self._x_warned:
                    log.warning("clipboard: X display unavailable (%s); retrying", exc)
                    self._x_warned = True
                self._fail_all("x_unavailable")
                select.select([self._wake_r], [], [], self._reconnect)
                self._drain_wake()
                continue
            self._x_warned = False
            self._connected = True
            log.info("clipboard: watching CLIPBOARD on window 0x%x", io.window)
            try:
                self._serve(io)
            except Exception as exc:
                log.warning("clipboard: X connection lost (%s); reconnecting", exc)
                self._fail_all("x_unavailable")
            finally:
                self._connected = False
                with contextlib.suppress(Exception):
                    io.close()

    def _fail_all(self, reason: str) -> None:
        if self._current is not None:
            self._current.resolve_done(PasteOutcome(False, reason))
            self._current = None
        while self._waiting:
            self._waiting.popleft().resolve_done(PasteOutcome(False, reason))
        while True:
            try:
                command, job, _ = self._commands.get_nowait()
            except queue.Empty:
                break
            if command == "paste":
                job.resolve_done(PasteOutcome(False, reason))

    def _serve(self, io: SelectionIO) -> None:
        while not self._stop.is_set():
            timeout = 0.5
            job = self._current
            if job is not None and job.deadline is not None:
                timeout = min(timeout, max(0.0, job.deadline - self._clock()))
            readable, _, _ = select.select([io.fileno(), self._wake_r], [], [], timeout)
            if self._wake_r in readable:
                self._drain_wake()
            self._handle_commands(io)
            for ev in io.events():
                self._handle_event(io, ev)
            self._check_deadline(io)

    def _handle_commands(self, io: SelectionIO) -> None:
        while True:
            try:
                command, job, reason = self._commands.get_nowait()
            except queue.Empty:
                return
            if command == "paste":
                self._waiting.append(job)
            elif job is self._current:
                if command == "injected" and job.state == "offered":
                    job.state = "injected"
                    job.deadline = self._clock() + self._data_timeout
                elif command == "abort":
                    self._finish(io, PasteOutcome(False, reason))
            elif command == "abort" and job in self._waiting:
                self._waiting.remove(job)
                job.resolve_done(PasteOutcome(False, reason))

    def _start_next(self, io: SelectionIO) -> None:
        while self._current is None and self._waiting:
            job = self._waiting.popleft()
            if not io.own():
                job.resolve_done(PasteOutcome(False, "own_failed"))
                continue
            job.state = "waiting_targets"
            job.deadline = self._clock() + self._targets_timeout
            self._current = job

    def _finish(self, io: SelectionIO, outcome: PasteOutcome) -> None:
        job, self._current = self._current, None
        io.release()
        if job is not None:
            job.resolve_done(outcome)  # the event-loop side waits on offered OR done

    def _handle_event(self, io: SelectionIO, ev: SelectionEvent) -> None:
        job = self._current
        match ev:
            case ConvertRequest():
                if job is None or job.state == "queued":
                    io.refuse(ev)
                elif ev.target == "TARGETS":
                    io.reply_targets(ev, OFFERED_TARGETS)
                    if job.state == "waiting_targets":
                        job.state = "offered"
                        job.deadline = self._clock() + self._settle + self._data_timeout
                        job.resolve_offered()
                    elif job.state == "scrubbing" and not job.scrub_announced:
                        # xfreerdp is announcing our (empty) offer to Windows: linger to answer a
                        # data request with nothing, then release.
                        job.scrub_announced = True
                        job.deadline = self._clock() + self._linger
                elif ev.target in TEXT_TARGETS:
                    io.reply_data(ev, job.data)
                    if job.state == "scrubbing":
                        return
                    if job.state != "served":
                        log.info("clipboard: served a paste (%d bytes)", len(job.data))
                    job.state = "served"
                    job.deadline = self._clock() + self._linger
                else:
                    io.refuse(ev)
            case OwnershipLost():
                if job is None or io.owner() == io.window:
                    # Stale: the SelectionClear of our OWN earlier release, delivered after we took
                    # CLIPBOARD again (the scrub, or the next queued paste). Found on a real X
                    # server, 2026-10-01; we still own it, so nothing was taken.
                    return
                if job.state == "scrubbing":
                    self._scrub_failed(io, "ownership taken during the scrub")
                else:
                    self._finish(io, PasteOutcome(False, "ownership_taken"))
            case OwnerChanged(owner=owner):
                if owner not in (0, io.window):
                    self._clear_foreign(io, owner)

    def _clear_foreign(self, io: SelectionIO, owner: int) -> None:
        if (io.owner_class(owner) or "").lower() in RDP_CLIENT_CLASSES:
            self._rdp_claims += 1
            now = self._clock()
            if self._last_rdp_note is None or now - self._last_rdp_note >= self._warn_interval:
                self._last_rdp_note = now
                log.info(
                    "clipboard watchdog: xfreerdp claimed CLIPBOARD (a Windows-side copy; no data "
                    "crosses to X in text-to-remote mode) -- clearing it (%d so far)",
                    self._rdp_claims,
                )
            if io.own():
                io.release()
            return
        self._foreign_clears += 1
        now = self._clock()
        last = self._last_foreign_warning
        if last is None or now - last >= self._warn_interval:
            extra = self._suppressed_foreign
            self._suppressed_foreign = 0
            self._last_foreign_warning = now
            log.warning(
                "clipboard watchdog: CLIPBOARD taken by foreign window 0x%x -- clearing it "
                "(ADR-0004: only the backend may own it)%s",
                owner,
                f" (+{extra} more since the last warning)" if extra else "",
            )
        else:
            self._suppressed_foreign += 1
        if io.own():
            io.release()

    def _start_scrub(self, io: SelectionIO, job: _Job) -> None:
        """The paste is served: replace Windows' copy of the text with an empty offer."""
        io.release()
        job.data = b""
        job.state = "scrubbing"
        job.deadline = self._clock() + self._targets_timeout
        if not io.own():
            self._scrub_failed(io, "could not take CLIPBOARD back")

    def _scrub_failed(self, io: SelectionIO, why: str) -> None:
        self._scrub_incomplete += 1
        log.warning(
            "clipboard: scrub incomplete (%s); Windows may still hold the last paste "
            "(ADR-0004 amendment)",
            why,
        )
        self._finish(io, PasteOutcome(True, "ok"))  # the paste itself succeeded

    def _check_deadline(self, io: SelectionIO) -> None:
        self._start_next(io)
        job = self._current
        if job is None or job.deadline is None or self._clock() < job.deadline:
            return
        if job.state == "served":
            self._start_scrub(io, job)
            return
        if job.state == "scrubbing":
            if job.scrub_announced:
                self._finish(io, PasteOutcome(True, "ok"))
            else:
                self._scrub_failed(io, "xfreerdp never asked for TARGETS")
            self._start_next(io)
            return
        outcome = {
            "waiting_targets": PasteOutcome(False, "rdp_clipboard_not_listening"),
            "offered": PasteOutcome(False, "inject_timeout"),
            "injected": PasteOutcome(False, "no_data_request"),
        }.get(job.state, PasteOutcome(False, "timeout"))
        self._finish(io, outcome)
        self._start_next(io)
