"""Dropped inbound messages are never silent (ADR-0004, decision 4).

A message that fails validation or cannot be read at all (bad JSON, a binary frame on a text
channel) is:
  * counted per ``(channel, reason)`` and exposed in ``/health`` as ``dropped_messages``;
  * logged as a WARNING -- the first occurrence of each ``(channel, reason)`` at once, then at most
    once per ``warn_interval_s`` with the number suppressed in between;
  * answered with an ``ErrorReply`` where the channel allows (rate-limited per connection).

Only the message ``type`` and Pydantic's error *type* and *location* are ever used -- never the
offending value (``include_input=False``), so a dropped clipboard paste cannot leak its text.
"""

import json
import logging
import re
import time
from collections import Counter
from collections.abc import Callable
from typing import Literal

from pydantic import ValidationError

log = logging.getLogger(__name__)

Channel = Literal["ws_input", "ws_stream", "agent", "ingest", "ws_packets"]

_TYPE = re.compile(r"^[a-z_]{1,32}$")
_LOC_PART = re.compile(r"^[A-Za-z0-9_]{1,32}$")
REASON_MAX = 128


def message_type(raw: str | bytes) -> str | None:
    """The ``type`` field of a dropped message, when it is readable and well-formed."""
    try:
        data = json.loads(raw)
    except (ValueError, UnicodeDecodeError):
        return None
    value = data.get("type") if isinstance(data, dict) else None
    return value if isinstance(value, str) and _TYPE.match(value) else None


def drop_reason(exc: ValidationError) -> str:
    """``<error type>:<location>`` of the first error, e.g. ``missing:key.t_mono_ns``.

    Location parts are field names from our own models or list indices; anything else (an unknown
    field name chosen by the sender) is replaced by ``?`` so no sender-chosen text reaches the log.
    """
    errors = exc.errors(include_url=False, include_context=False, include_input=False)
    if not errors:
        return "invalid"
    first = errors[0]
    if first["type"] == "json_invalid":
        return "json_invalid"
    loc = ".".join(
        str(part) if isinstance(part, int) or _LOC_PART.match(part) else "?"
        for part in first["loc"]
    )
    return f"{first['type']}:{loc}"[:REASON_MAX] if loc else first["type"][:REASON_MAX]


class DropCounter:
    """Counts drops and rate-limits the WARNING per ``(channel, reason)``."""

    def __init__(
        self,
        *,
        warn_interval_s: float = 10.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._interval = warn_interval_s
        self._clock = clock
        self._counts: Counter[tuple[str, str]] = Counter()
        self._suppressed: Counter[tuple[str, str]] = Counter()
        self._last_warning: dict[tuple[str, str], float] = {}

    def record(self, channel: str, reason: str, ref_type: str | None) -> None:
        key = (channel, reason)
        self._counts[key] += 1
        now = self._clock()
        last = self._last_warning.get(key)
        if last is not None and now - last < self._interval:
            self._suppressed[key] += 1
            return
        suppressed = self._suppressed.pop(key, 0)
        log.warning(
            "dropped %s message on %s: %s%s",
            ref_type or "unreadable",
            channel,
            reason,
            f" (+{suppressed} more since the last warning)" if suppressed else "",
        )
        self._last_warning[key] = now

    def snapshot(self) -> dict[str, dict[str, int]]:
        """``{channel: {reason: count}}`` for /health."""
        out: dict[str, dict[str, int]] = {}
        for (channel, reason), count in sorted(self._counts.items()):
            out.setdefault(channel, {})[reason] = count
        return out


class ReplyThrottle:
    """At most one ErrorReply per ``min_interval_s`` on one connection; drops are still counted."""

    def __init__(
        self, *, min_interval_s: float = 0.2, clock: Callable[[], float] = time.monotonic
    ) -> None:
        self._interval = min_interval_s
        self._clock = clock
        self._last: float | None = None

    def allow(self) -> bool:
        now = self._clock()
        if self._last is not None and now - self._last < self._interval:
            return False
        self._last = now
        return True
