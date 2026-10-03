"""The backend's sink for the S2 input socket (ADR-0014, S2 step 3): mux -> Injector -> this ->
unix socket -> the S2 client -> LiSend* -> Sunshine. No X window takes part.

ONLY the backend's Injector may own one (single-writer invariant, ADR-0002): every event it sends
has passed the InputMux. The socket lives on the ``s2-input`` volume, which only the backend and
gamestream mount (test_guards); the bot reaches it only through the mux.

The wire (services/gamestream/s2spike/input_socket.py): one JSON line per batch,
``{"t": sent_ns, "events": [...]}``, answered with ``{"t", "recv", "done", "n", "refused"}`` once
every LiSend* call has returned. ``send_many`` waits for that ack (``timeout_s``), so a caller's
"injected" time means what XSync meant for XTest: the input left this host. A missing or mismatched
ack raises (the Injector then drops this connection and opens a new one): stale input is never
queued or retried.
"""

import collections
import json
import logging
import socket
from pathlib import Path

from poring_env.clock import monotonic_ns
from poring_env.protocol import InputEvent, MouseButton, MouseMove

log = logging.getLogger(__name__)

SOCKET_PATH = Path("/s2-input/input.sock")
MAX_ACK = 64 * 1024


class S2InputError(RuntimeError):
    """The S2 client did not acknowledge a batch as sent (timeout, closed, mismatched)."""


class GameStreamInput:
    """Input sink over the S2 input socket. Not thread-safe: the Injector uses it from its one
    thread. ``pointer()`` is the last position SENT (Windows' own cursor is not observable here)."""

    def __init__(
        self,
        path: Path = SOCKET_PATH,
        *,
        size: tuple[int, int] = (1440, 900),
        timeout_s: float = 1.0,
    ) -> None:
        self.path = path
        self.width, self.height = size
        self._sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self._sock.settimeout(timeout_s)
        try:
            self._sock.connect(str(path))
        except OSError:
            self._sock.close()
            raise
        self._buf = b""
        self._pointer = (0, 0)
        self.acks = 0
        self.refused = 0
        self.leg_ns: collections.deque[int] = collections.deque(maxlen=512)  # done - sent

    def send_many(self, events: list[InputEvent]) -> None:
        sent = monotonic_ns()
        line = json.dumps(
            {"t": sent, "events": [e.model_dump(mode="json") for e in events]},
            separators=(",", ":"),
        )
        try:
            self._sock.sendall(line.encode() + b"\n")
            ack = self._read_ack()
        except (OSError, ValueError) as exc:
            raise S2InputError(f"no ack from the S2 client: {exc}") from exc
        if ack.get("t") != sent:
            raise S2InputError("the S2 client acknowledged another batch")
        self.acks += 1
        done = ack.get("done")
        if isinstance(done, int):
            self.leg_ns.append(done - sent)
        raw = ack.get("refused")
        refused: list[object] = raw if isinstance(raw, list) else []
        if refused:
            # The mux already accepted these: a refusal here is a table drift, never user input.
            # Reasons only, never which key (secret typing).
            self.refused += len(refused)
            reasons = sorted({str(r[1]) for r in refused if isinstance(r, list) and len(r) == 2})
            log.warning("S2 client refused %d event(s): %s", len(refused), reasons)
        for e in events:
            if isinstance(e, MouseMove) or (isinstance(e, MouseButton) and e.x is not None):
                x, y = e.x, e.y
                assert x is not None and y is not None
                self._pointer = (
                    min(self.width - 1, max(0, int(x * self.width))),
                    min(self.height - 1, max(0, int(y * self.height))),
                )

    def _read_ack(self) -> dict[str, object]:
        while b"\n" not in self._buf:
            chunk = self._sock.recv(4096)
            if not chunk:
                raise ValueError("the S2 client closed the socket")
            self._buf += chunk
            if len(self._buf) > MAX_ACK:
                raise ValueError("an ack over 64 KiB")
        line, self._buf = self._buf.split(b"\n", 1)
        ack = json.loads(line)
        if not isinstance(ack, dict):
            raise ValueError("an ack that is not an object")
        return ack

    def pointer(self) -> tuple[int, int]:
        return self._pointer

    def has_window_class(self, needle: str) -> bool:
        return False  # windows are X's business (the Injector polls them on its X sink)

    def close(self) -> None:
        self._sock.close()
