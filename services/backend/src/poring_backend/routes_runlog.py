"""The Settings page's "Run log" (Batt 2026-11-21): "What she does" kept as history.

Batt: "keep the logs of What she does as history, set on /settings: record or not (the default:
not), the folder (the default logs/bot/<the run's start time>; a NAS folder if wanted), and a
retention by the total size, e.g. 100 MB: when full, the oldest is written over, like a CCTV
camera."

    GET /settings/run-log   the settings (the default when no file), the revision, ok / default /
                            unreadable, the limits
    PUT /settings/run-log   {base_revision, record, folder, max_total_mb}

The store is ``settings/run-log.json`` (poring_env.runlog: the format, shared with the Run helper,
which reads it at every Run's start, so a Save applies to the next Run). This module is its ONLY
writer. Writes pass routes_settings.write_gate unchanged (a console browser with the console's
Origin and the CSRF token; never the lab host or the Windows host; rate-limited; refusals
audited), so only a PERSON turns the recording on or points it at a folder; every change is in the
Settings audit log. The folder is checked for its form here (runlog.folder_problem); whether it can
be written is the helper's to find at a Run's start (it may be a NAS mount the backend cannot see),
and the Run's status says so.
"""

from __future__ import annotations

import os
import threading
import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from poring_backend.routes_settings import Who, _who, browser_gate, write_gate
from poring_backend.state import AppState
from poring_env import runlog as rl

router = APIRouter(prefix="/settings")

SUBJECT = "The Run log"
_LOCK = threading.Lock()  # one writer at a time (sync routes run in the thread pool)


class RunLogPut(BaseModel):
    model_config = ConfigDict(extra="forbid")
    base_revision: int = Field(ge=0)
    record: bool
    folder: str = Field(max_length=rl.MAX_FOLDER)
    max_total_mb: int


def store_file(state: AppState) -> Path:
    return state.settings.settings_dir / rl.FILE_NAME


def load(state: AppState) -> tuple[rl.Store, str, str | None]:
    """(the store, "ok" | "default" | "unreadable", the problem). Unreadable: the default's
    values are SHOWN, and the helper records nothing until a person saves."""
    f = store_file(state)
    try:
        text = f.read_text(encoding="utf-8")
    except FileNotFoundError:
        return rl.DEFAULT, "default", None
    except (OSError, UnicodeDecodeError) as e:
        return rl.DEFAULT, "unreadable", f"{f.name} cannot be read ({type(e).__name__})"
    got = rl.parse(text)
    if isinstance(got, str):
        return rl.DEFAULT, "unreadable", f"{f.name}: {got}"
    return got, "ok", None


def view(state: AppState, **extra: Any) -> dict[str, Any]:
    store, status, problem = load(state)
    return {"store": status, "problem": problem, **store.as_json(),
            "default": rl.DEFAULT.as_json(), "max_folder": rl.MAX_FOLDER,
            "max_total_mb_range": [rl.MAX_MB_LO, rl.MAX_MB_HI],
            "files": [rl.STORY_JSONL, rl.STORY_TEXT], **extra}  # fmt: skip


def write(state: AppState, store: rl.Store) -> None:
    """Atomic, then READ BACK: a save is reported only when the file parses to the same store."""
    f = store_file(state)
    if not f.parent.is_dir():  # never create the mount: a directory made here is the container's
        raise HTTPException(503, {"reason": "settings_store_missing"})
    tmp = f.with_name(f".{f.name}.{uuid.uuid4().hex}")
    tmp.write_text(rl.dumps(store), encoding="utf-8")
    os.replace(tmp, f)
    if rl.parse(f.read_text(encoding="utf-8")) != store:
        raise HTTPException(500, {"reason": "read_back_failed"})


def refuse(state: AppState, status: int, reason: str, detail: Any = None) -> HTTPException:
    state.drops.record("settings_http", reason, "run_log")
    return HTTPException(status, {"reason": reason, **({"detail": detail} if detail else {})})


def audit(state: AppState, who: Who, rev: tuple[int, int], before: list[str],
          after: list[str], note: str) -> None:  # fmt: skip
    state.allowlist_audit.write(
        action="run_log", kind="normal", env_id=None, entry=SUBJECT, revision_before=rev[0],
        revision_after=rev[1], before=before, after=after, ok=True, reason="page", note=note,
        **who.model_dump(),
    )  # fmt: skip


def words(s: rl.Store) -> list[str]:
    return [f"record {'on' if s.record else 'off'}", f"folder {s.folder}",
            f"keep at most {s.max_total_mb} MB"]  # fmt: skip


@router.get("/run-log")
def get_run_log(state: AppState = Depends(browser_gate)) -> dict[str, Any]:
    return view(state)


@router.put("/run-log")
def put_run_log(body: RunLogPut, request: Request,
                state: AppState = Depends(write_gate)) -> dict[str, Any]:  # fmt: skip
    who = _who(request)
    with _LOCK:
        store, status, _ = load(state)
        if status != "unreadable" and body.base_revision != store.revision:
            raise refuse(state, 409, "revision_conflict", store.revision)
        folder = body.folder.strip()
        why = rl.folder_problem(folder) or rl.max_problem(body.max_total_mb)
        if why:
            raise refuse(state, 400, why)
        base_rev = store.revision if status != "unreadable" else body.base_revision
        new = rl.Store(revision=base_rev + 1, record=body.record, folder=folder,
                       max_total_mb=body.max_total_mb)  # fmt: skip
        if status == "ok" and (new.record, new.folder, new.max_total_mb) == (
                store.record, store.folder, store.max_total_mb):  # fmt: skip
            return view(state, saved=False)
        write(state, new)
        audit(state, who, (base_rev, new.revision), words(store), words(new),
              "; ".join(words(new)))  # fmt: skip
    return view(state, saved=True)
