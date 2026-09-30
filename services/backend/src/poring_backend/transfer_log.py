"""Audit log of the human-only clipboard and file-transfer tools (ADR-0004):
``<data_dir>/transfer_log/YYYY-MM-DD.jsonl`` (UTC day), one line per action.

METADATA ONLY -- action, file name, size, sha256, outcome. Never the pasted text or file contents;
``TransferRecord`` forbids extra fields and tests pin its exact keys.
"""

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict

from poring_backend.input_log import DailyJsonl, wall_clock_iso

Action = Literal["paste", "upload", "download", "delete"]


class TransferRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    t_wall: str
    action: Action
    name: str | None  # file name; None for a paste
    size: int  # bytes (UTF-8 bytes for a paste)
    sha256: str | None
    ok: bool
    reason: str
    client: str | None  # peer address of the browser


class TransferLog(DailyJsonl):
    def __init__(self, data_dir: Path) -> None:
        super().__init__(data_dir / "transfer_log")

    def write(
        self,
        action: Action,
        *,
        name: str | None,
        size: int,
        sha256: str | None,
        ok: bool,
        reason: str,
        client: str | None,
    ) -> None:
        record = TransferRecord(
            t_wall=wall_clock_iso(),
            action=action,
            name=name,
            size=size,
            sha256=sha256,
            ok=ok,
            reason=reason,
            client=client,
        )
        self.append(record.t_wall[:10], record.model_dump_json())
