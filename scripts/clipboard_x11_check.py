r"""Exercise the backend's clipboard service against a REAL X display -- no RDP, no Windows.

A stand-in for xfreerdp (a second X client) watches CLIPBOARD through XFixes, asks the new owner
for TARGETS, and asks for UTF8_STRING when "Ctrl+V" happens -- the sequence FreeRDP 3.15 performs
(ADR-0004). Then a foreign client takes CLIPBOARD and the watchdog must clear it.

    python scripts/clipboard_x11_check.py :97      # PASS/FAIL lines; exit status 0/1

Runs from test_clipboard_x11.py when Xvfb is installed. On this host (no Xvfb) run it inside the
backend container against a throwaway display in the desktop container (both share the X socket
directory, and the backend's dev mount already has the current source):

    docker exec poring-lab-desktop-1 sh -c \
        'Xvfb :97 -nolisten tcp -nolock -ac -screen 0 64x64x24 & echo $! >/dev/shm/xvfb97.pid'
    docker exec -i -e PYTHONPATH=/dev-src/poring_env:/dev-src/backend poring-lab-backend-1 \
        python - :97 < scripts/clipboard_x11_check.py
    docker exec poring-lab-desktop-1 sh -c 'kill "$(cat /dev/shm/xvfb97.pid)"'
"""

import asyncio
import select
import sys
import threading
import time
from typing import Any

from Xlib import X
from Xlib import display as xdisplay
from Xlib.ext import xfixes

from poring_backend.clipboard import ClipboardService, XSelectionIO

TEXT = "poring clipboard check สวัสดีครับ\nline 2"


class StandInXfreerdp(threading.Thread):
    """Asks every new CLIPBOARD owner for TARGETS; on ``want_paste`` asks for UTF8_STRING."""

    def __init__(self, name: str) -> None:
        super().__init__(daemon=True)
        self.d = xdisplay.Display(name)
        self.d.xfixes_query_version()
        root = self.d.screen().root
        self.win = root.create_window(0, 0, 1, 1, 0, X.CopyFromParent)
        self.clipboard = self.d.intern_atom("CLIPBOARD")
        self.prop = self.d.intern_atom("PORING_CHECK")
        self.d.xfixes_select_selection_input(
            root, self.clipboard, xfixes.XFixesSetSelectionOwnerNotifyMask
        )
        self.d.sync()
        self.targets: list[str] = []
        self.text: bytes | None = None
        self.want_paste = threading.Event()
        self.stop = threading.Event()

    def convert(self, target: str) -> Any:
        """The converted property value (array of atoms for TARGETS, bytes for text) or None."""
        self.win.convert_selection(
            self.clipboard, self.d.intern_atom(target), self.prop, X.CurrentTime
        )
        self.d.flush()
        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline:
            select.select([self.d], [], [], 0.05)
            while self.d.pending_events():
                e = self.d.next_event()
                if e.type == X.SelectionNotify and e.requestor.id == self.win.id:
                    if e.property == X.NONE:
                        return None
                    prop = self.win.get_full_property(self.prop, X.AnyPropertyType)
                    return None if prop is None else prop.value
        return None

    def run(self) -> None:
        while not self.stop.is_set():
            select.select([self.d], [], [], 0.05)
            while self.d.pending_events():
                e = self.d.next_event()
                # python-xlib clones extension event classes per display: match the base class
                # and the sub-code, and compare window ids (Window(0) != 0 in python-xlib).
                is_new_owner = (
                    isinstance(e, xfixes.SelectionNotify)
                    and e.sub_code == xfixes.XFixesSetSelectionOwnerNotify
                )
                owner = int(getattr(getattr(e, "owner", 0), "id", 0))
                if is_new_owner and owner not in (0, self.win.id):
                    atoms = self.convert("TARGETS")
                    self.targets = [self.d.get_atom_name(int(a)) for a in (atoms or [])]
            if self.want_paste.is_set():
                self.want_paste.clear()
                value = self.convert("UTF8_STRING")
                self.text = bytes(value) if isinstance(value, (bytes, bytearray)) else None


async def check(name: str) -> list[str]:
    failures: list[str] = []

    def expect(ok: bool, what: str) -> None:
        print(("PASS " if ok else "FAIL ") + what)
        if not ok:
            failures.append(what)

    standin = StandInXfreerdp(name)
    standin.start()
    observer = xdisplay.Display(name)
    clipboard = observer.intern_atom("CLIPBOARD")
    service = ClipboardService(lambda: XSelectionIO(name), settle_s=0.1, data_timeout_s=3.0)
    service.start()
    try:
        for _ in range(100):
            if service.connected:
                break
            await asyncio.sleep(0.02)
        expect(service.connected, "service connected to X")

        async def inject() -> str | None:
            standin.want_paste.set()  # the "Ctrl+V": the stand-in now asks for the data
            return None

        outcome = await service.paste(TEXT, inject)
        expect(outcome.ok, f"paste served (outcome={outcome.reason})")
        expect("UTF8_STRING" in standin.targets, f"TARGETS offered UTF8_STRING ({standin.targets})")
        expect(standin.text == TEXT.encode(), "stand-in received the exact UTF-8 text")
        owner = int(getattr(observer.get_selection_owner(clipboard), "id", 0))
        expect(owner == 0, "ownership released after the paste")

        foreign = observer.screen().root.create_window(0, 0, 1, 1, 0, X.CopyFromParent)
        foreign.set_selection_owner(clipboard, X.CurrentTime)
        observer.sync()
        for _ in range(100):
            if service.foreign_owner_clears >= 1:
                break
            await asyncio.sleep(0.02)
        await asyncio.sleep(0.1)
        expect(service.foreign_owner_clears >= 1, "watchdog noticed a foreign owner")
        owner = int(getattr(observer.get_selection_owner(clipboard), "id", 0))
        expect(owner == 0, "watchdog cleared the foreign owner")
    finally:
        await asyncio.to_thread(service.stop)
        standin.stop.set()
        standin.join(timeout=2)
        observer.close()
    return failures


def main() -> int:
    name = sys.argv[1] if len(sys.argv) > 1 else ":97"
    failures = asyncio.run(check(name))
    print("RESULT", "FAIL" if failures else "PASS")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
