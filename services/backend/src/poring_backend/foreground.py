"""The TYPING-ONLY foreground gate (Batt, 2026-10-06): before a BOT batch types anything (keys,
chords, chat, hotkeys), the lab RO client must be the foreground window on a FRESH frame.

Evidence (pixel-based, no new Windows component): the client's ACTIVE title bar, matched with the
same signature ro_agent uses (signature.py), in the picture the bot itself sees:
  * the S2 frame bus in console mode with a live writer, else X (grabsource.GrabSource: the
    backend's own rule);
  * a frame captured at most ``CITED_MAX_AGE_MS`` (400 ms) ago -- judged by the frame's capture
    time, never by when it was read (a static S2 screen sends no new frames);
  * the template OF THAT PATH: ``client_title_active.npy`` (RDP/X) or
    ``client_title_active@stream.npy`` (the H.264 console stream softens pixels). A missing
    template refuses (``foreground_uncalibrated``): fail closed, the console path included until
    it is calibrated (Batt's answer 2).

The templates live in the HUMAN-ONLY settings store (``<settings_dir>/foreground/``; compose
mounts it into the backend only), installed by ``scripts/foreground_template.py``. vision can write
``./data``, so a template there could be replaced by the agent.

Clicks, moves, the wheel, key RELEASES and ReleaseAll are never gated. The exemption (Batt's
answer 1): while a ``desktop`` operator window is open (ASSIST only, <= 120 s, tied to the lock SEQ)
the agent types into its own Windows console (ro_agent console lines, capture_backend's TSCON);
those batches pass and are logged as exempt.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections import Counter
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import numpy as np
from numpy.typing import NDArray

from poring_backend.display import Region
from poring_backend.signature import SIG_MATCH, distance, grey_thumb
from poring_env.clock import monotonic_ns
from poring_env.freshness import CITED_MAX_AGE_MS

log = logging.getLogger(__name__)

TEMPLATE = "client_title_active"
STREAM_SUFFIX = "@stream"
GrabRegion = tuple[int, int, int, int]
Grab = tuple[int, NDArray[np.uint8], str]  # (capture t_mono_ns, BGRA crop, "bus" | "x11")
GrabFn = Callable[[GrabRegion], Grab]
Path_ = Literal["x11", "bus"]


@dataclass(frozen=True)
class Check:
    ok: bool
    reason: str  # "ok" | client_not_foreground | foreground_stale_frame | foreground_uncalibrated
    distance: float | None = None
    age_ms: float | None = None
    path: str | None = None


class ForegroundGate:
    def __init__(
        self,
        settings_dir: Path,
        game_region: Region | None,
        grab_factory: Callable[[], GrabFn],
        *,
        max_age_ns: int = int(CITED_MAX_AGE_MS * 1e6),
    ) -> None:
        self.dir = settings_dir / "foreground"
        self.game_region = game_region
        self._grab_factory = grab_factory
        self._grab: GrabFn | None = None
        self.max_age_ns = max_age_ns
        self._cache: dict[Path, tuple[float, Any]] = {}
        # Grabs run on ONE thread of their own (an X connection is not thread-safe).
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="foreground")
        self.last: Check | None = None
        self.last_at_ns: int | None = None
        self.last_state: Literal["ok", "refused", "exempt", "unchecked"] = "unchecked"
        self.refused: Counter[str] = Counter()
        self.passed = 0
        self.exempt = 0

    # --- templates --------------------------------------------------------------------------------

    def _load(self, path: Path, kind: Literal["npy", "json"]) -> Any:
        try:
            mtime = path.stat().st_mtime
        except OSError:
            self._cache.pop(path, None)
            return None
        cached = self._cache.get(path)
        if cached is not None and cached[0] == mtime:
            return cached[1]
        try:
            if kind == "npy":
                value = np.load(path).astype(np.float32)
            else:
                value = json.loads(path.read_text())["box"]
        except (OSError, ValueError, KeyError, EOFError, TypeError):
            # a half-written or broken template counts as NO template (fail closed), never a
            # crash of the status loop that reads it; scripts/foreground_template.py writes
            # atomically, so this is a transient
            log.warning("foreground template unreadable: %s", path)
            return None
        self._cache[path] = (mtime, value)
        return value

    def region(self) -> GrabRegion | None:
        """The client title bar's desktop box: the template's box, relative to GAME_REGION."""
        box = self._load(self.dir / f"{TEMPLATE}.json", "json")
        if box is None or self.game_region is None:
            return None
        dx, dy, w, h = (int(v) for v in box)
        return self.game_region.x + dx, self.game_region.y + dy, w, h

    def template(self, path: str) -> NDArray[np.float32] | None:
        name = TEMPLATE + (STREAM_SUFFIX if path == "bus" else "")
        ref = self._load(self.dir / f"{name}.npy", "npy")
        return None if ref is None else np.asarray(ref, dtype=np.float32)

    def calibrated(self) -> dict[str, bool]:
        return {
            "rdp": self.template("x11") is not None,
            "stream": self.template("bus") is not None,
            "box": self.region() is not None,
        }

    # --- the check --------------------------------------------------------------------------------

    def check(self) -> Check:
        """One fresh look (blocking: run it on the gate's own thread, ``check_async``)."""
        region = self.region()
        if region is None:
            return Check(False, "foreground_uncalibrated")
        if self._grab is None:
            self._grab = self._grab_factory()
        t, crop, path = self._grab(region)
        age_ns = max(0, monotonic_ns() - t)
        age_ms = round(age_ns / 1e6, 1)
        if age_ns > self.max_age_ns:
            return Check(False, "foreground_stale_frame", None, age_ms, path)
        ref = self.template(path)
        if ref is None:
            return Check(False, "foreground_uncalibrated", None, age_ms, path)
        d = round(distance(grey_thumb(crop), ref), 2)
        ok = d <= SIG_MATCH
        return Check(ok, "ok" if ok else "client_not_foreground", d, age_ms, path)

    async def check_async(self) -> Check:
        loop = asyncio.get_running_loop()
        try:
            result = await loop.run_in_executor(self._executor, self.check)
        except Exception as exc:  # noqa: BLE001  any failure to look is a refusal, never a pass
            log.warning("foreground check failed: %s", exc)
            result = Check(False, "foreground_check_failed")
        self.note(result)
        return result

    def note(self, result: Check) -> None:
        self.last, self.last_at_ns = result, monotonic_ns()
        if result.ok:
            self.passed += 1
            self.last_state = "ok"
        else:
            self.refused[result.reason] += 1
            self.last_state = "refused"

    def note_exempt(self) -> None:
        self.exempt += 1
        self.last, self.last_at_ns = Check(True, "foreground_exempt_desktop_window"), monotonic_ns()
        self.last_state = "exempt"

    def snapshot(self) -> dict[str, Any]:
        last = self.last
        return {
            "state": self.last_state,
            "reason": last.reason if last else None,
            "distance": last.distance if last else None,
            "age_ms": last.age_ms if last else None,
            "path": last.path if last else None,
            "since_s": None
            if self.last_at_ns is None
            else round((monotonic_ns() - self.last_at_ns) / 1e9, 1),
            "passed": self.passed,
            "exempt": self.exempt,
            "refused": dict(self.refused),
            "calibrated": self.calibrated(),
            "threshold": SIG_MATCH,
            "max_age_ms": round(self.max_age_ns / 1e6),
        }

    def close(self) -> None:
        self._executor.shutdown(wait=False, cancel_futures=True)
