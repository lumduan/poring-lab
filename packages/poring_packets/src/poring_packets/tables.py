"""Packet length tables, generated at build time by scripts/gen_packet_tables.py (never committed).

The table maps (server, direction, packet id) to a length: a positive fixed size, or -1 for a
variable-length packet whose u16 length sits at offset 2. Its SHA-256 must equal the one committed
in `tables.lock.json`, so a stale or hand-edited table is refused instead of silently misframing.
"""

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

Server = Literal["login", "char", "map"]
Direction = Literal["cs", "sc"]  # client->server, server->client

PACKAGE_DIR = Path(__file__).resolve().parent
DEFAULT_TABLE = PACKAGE_DIR / "_generated" / "lengths.json"
LOCK = PACKAGE_DIR / "tables.lock.json"
VARIABLE = -1


class TableError(RuntimeError):
    """The generated table is missing, stale, or does not match the committed lock."""


@dataclass(frozen=True)
class LengthTable:
    lengths: dict[tuple[str, str, int], int]
    sources: dict[tuple[str, str, int], str]

    def length(self, server: str, direction: str, packet_id: int) -> int | None:
        """Fixed length, VARIABLE (-1), or None for an id this table does not know."""
        return self.lengths.get((server, direction, packet_id))

    @classmethod
    def from_entries(cls, entries: list[dict[str, object]]) -> "LengthTable":
        lengths: dict[tuple[str, str, int], int] = {}
        sources: dict[tuple[str, str, int], str] = {}
        for e in entries:
            key = (str(e["server"]), str(e["dir"]), int(str(e["id"])))
            lengths[key] = int(str(e["len"]))
            sources[key] = str(e["source"])
        return cls(lengths, sources)


def load(path: Path = DEFAULT_TABLE, lock: Path = LOCK) -> LengthTable:
    if not path.exists():
        raise TableError(f"{path} missing: run scripts/gen_packet_tables.py")
    body = path.read_bytes()
    want = json.loads(lock.read_text()).get("output_sha256")
    got = hashlib.sha256(body).hexdigest()
    if got != want:
        raise TableError(f"{path.name} sha256 {got} != lock {want}: regenerate the table")
    doc = json.loads(body)
    return LengthTable.from_entries(doc["entries"])
