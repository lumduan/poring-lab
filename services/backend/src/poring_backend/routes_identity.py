"""The Settings page's "Who may play a Run" (Batt 2026-11-19, ADR-0020 Amendment R).

Batt: "make any the default, this machine too, and settable in Settings; the character names set
in Settings -- .env is hard for a new user (a restart); on Settings, Save and it works at once";
and the Remember button "in Settings too".

    GET  /settings/run-identity           the mode, the characters remembered here (each with its
                                          name-line picture), the revision, whether the store is
                                          the default (no file), ok or unreadable
    PUT  /settings/run-identity           {base_revision, mode, characters: [{id, name}]}: the mode,
                                          and the remembered characters renamed (a new name) or
                                          forgotten (left out); a new one comes only from Remember
    POST /settings/run-identity/remember  {base_revision, name}: the Run helper reads the name line
                                          of the character on screen ONCE (crusader.py plate:
                                          pixels only, no input); stored under the typed name

The store is ``settings/run-identity.json`` (poring_env.runidentity: the format, shared with the
host's readers). This module is its ONLY writer; the Run's checks on the host read it every time
they run, so a Save applies to the next check or Run without a restart. No file = the default:
any, no character (every install, the lab too, Batt 2026-11-19).

Writes pass routes_settings.write_gate unchanged (a console browser on the LAN with the console's
Origin and the CSRF token; never the lab host, whose processes include the bot, nor the Windows
host the bot drives; rate-limited; every refusal audited), so only a PERSON changes who may play
and only a person's press cuts a name-line picture. Every change is in the Settings audit log.
Reads pass the console-browser gate only (the pictures never go to the agent's listener).

Remember asks the host's Run helper through its request file (routes_flowrun's channel:
``settings/flowrun/request.json``, action "plate") and waits for ``settings/flowrun/plate.json``
with the same id (at most PLATE_WAIT_S); it deletes that file whatever it says, so the picture is
kept only in the store, and only on success.
"""

from __future__ import annotations

import asyncio
import base64
import json
import os
import secrets
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from poring_backend.input_log import wall_clock_iso
from poring_backend.routes_flowrun import read_status, run_dir
from poring_backend.routes_settings import Who, _who, browser_gate, write_gate
from poring_backend.state import AppState
from poring_env import runidentity as ri

router = APIRouter(prefix="/settings")

PLATE_FILE = "plate.json"  # flow_run.PLATE_FILE (test_run_identity_settings pins the two)
PLATE_WAIT_S = 25.0  # the helper's own time box is 15 s (flow_run.PLATE_TIMEOUT_S) + its 1 s poll
PLATE_POLL_S = 0.2
SUBJECT = "Who may play a Run"
_LOCK = threading.Lock()  # one writer at a time (sync routes run in the thread pool)


class CharIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(pattern=r"^c_[0-9a-f]{8}$")
    name: str = Field(max_length=64)  # the exact limit and the other rules: runidentity


class IdentityPut(BaseModel):
    model_config = ConfigDict(extra="forbid")
    base_revision: int = Field(ge=0)
    mode: Literal["any", "known", "mine"]
    characters: list[CharIn] = Field(max_length=ri.MAX_CHARACTERS)


class RememberBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    base_revision: int = Field(ge=0)
    name: str = Field(max_length=64)


def store_file(state: AppState) -> Path:
    return state.settings.settings_dir / ri.FILE_NAME


def load(state: AppState) -> tuple[ri.Store, str, str | None]:
    """(the store, "ok" | "default" | "unreadable", the problem). Unreadable: the default's
    values are SHOWN, but the Run's checks fail until a person saves (crusader.identity_store)."""
    f = store_file(state)
    try:
        text = f.read_text(encoding="utf-8")
    except FileNotFoundError:
        return ri.DEFAULT, "default", None
    except (OSError, UnicodeDecodeError) as e:
        return ri.DEFAULT, "unreadable", f"{f.name} cannot be read ({type(e).__name__})"
    got = ri.parse(text)
    if isinstance(got, str):
        return ri.DEFAULT, "unreadable", f"{f.name}: {got}"
    return got, "ok", None


def view(state: AppState, **extra: Any) -> dict[str, Any]:
    store, status, problem = load(state)
    helper = read_status(run_dir(state))
    return {"store": status, "problem": problem, "revision": store.revision, "mode": store.mode,
            "default_mode": ri.DEFAULT_MODE, "modes": list(ri.MODES),
            "characters": [c.as_json() for c in store.characters],
            "max_characters": ri.MAX_CHARACTERS, "max_name": ri.MAX_NAME,
            "helper_alive": bool(helper.get("helper_alive")), **extra}  # fmt: skip


def write(state: AppState, store: ri.Store) -> None:
    """Atomic, then READ BACK: a save is reported only when the file parses to the same store."""
    f = store_file(state)
    if not f.parent.is_dir():  # never create the mount: a directory made here is the container's
        raise HTTPException(503, {"reason": "settings_store_missing"})
    tmp = f.with_name(f".{f.name}.{uuid.uuid4().hex}")
    tmp.write_text(ri.dumps(store), encoding="utf-8")
    os.replace(tmp, f)
    back = ri.parse(f.read_text(encoding="utf-8"))
    if back != store:
        raise HTTPException(500, {"reason": "read_back_failed"})


def refuse(state: AppState, status: int, reason: str, detail: Any = None) -> HTTPException:
    state.drops.record("settings_http", reason, "run_identity")
    return HTTPException(status, {"reason": reason, **({"detail": detail} if detail else {})})


def audit(state: AppState, who: Who, action: str, entry: str, rev: tuple[int, int],
          before: list[str] | None, after: list[str] | None, note: str) -> None:  # fmt: skip
    state.allowlist_audit.write(
        action=action, kind="normal", env_id=None, entry=entry, revision_before=rev[0],
        revision_after=rev[1], before=before, after=after, ok=True, reason="page", note=note,
        **who.model_dump(),
    )  # fmt: skip


MODE_WORDS = {"any": "any character", "known": "only the characters remembered here",
              "mine": "only the lab's own character"}  # fmt: skip


@router.get("/run-identity")
def get_identity(state: AppState = Depends(browser_gate)) -> dict[str, Any]:
    return view(state)


@router.put("/run-identity")
def put_identity(body: IdentityPut, request: Request,
                 state: AppState = Depends(write_gate)) -> dict[str, Any]:  # fmt: skip
    who = _who(request)
    with _LOCK:
        store, status, _ = load(state)
        if status == "unreadable":  # a person replaces a broken file: its pictures are lost
            if body.characters:
                raise refuse(state, 409, "store_unreadable_characters",
                             "the file does not parse: save with no character first")  # fmt: skip
            base = ri.Store(revision=body.base_revision)
        elif body.base_revision != store.revision:
            raise refuse(state, 409, "revision_conflict", store.revision)
        else:
            base = store
        by_id = {c.id: c for c in base.characters}
        seen: list[ri.Character] = []
        for ci in body.characters:
            if ci.id not in by_id:
                raise refuse(state, 400, "unknown_character", ci.id)
            if any(o.id == ci.id for o in seen):
                raise refuse(state, 400, "character_twice", ci.id)
            why = ri.name_problem(ci.name)
            if why is not None:
                raise refuse(state, 400, why, ci.name[: ri.MAX_NAME])
            if any(ri.same_name(o.name, ci.name) for o in seen):
                raise refuse(state, 409, "name_taken", ci.name)
            old = by_id[ci.id]
            seen.append(ri.Character(id=old.id, name=ci.name, remembered=old.remembered,
                                     w=old.w, h=old.h, rgb=old.rgb))  # fmt: skip
        changes: list[tuple[str, str, list[str] | None, list[str] | None, str]] = []
        if body.mode != base.mode or status == "unreadable":
            changes.append(("run_identity_mode", SUBJECT, [base.mode], [body.mode],
                            f"{MODE_WORDS[base.mode]} -> {MODE_WORDS[body.mode]}"))  # fmt: skip
        kept = {c.id: c for c in seen}
        for old in base.characters:
            new = kept.get(old.id)
            if new is None:
                changes.append(("char_forget", old.name, [old.name], None, "forgotten"))
            elif new.name != old.name:
                changes.append(("char_rename", new.name, [old.name], [new.name],
                                f"{old.name} -> {new.name}"))  # fmt: skip
        if not changes and [c.id for c in seen] == [c.id for c in base.characters]:
            return view(state, saved=False, changes=[])
        saved = ri.Store(revision=base.revision + 1, mode=body.mode, characters=tuple(seen))
        write(state, saved)
        for action, entry, before, after, note in changes:
            audit(state, who, action, entry, (base.revision, saved.revision), before, after, note)
    return view(state, saved=True,
                changes=[{"action": a, "text": n if a != "char_forget" else f"forgot {e}"}
                         for a, e, _, _, n in changes])  # fmt: skip


def _plate_result(d: Path, rid: str) -> dict[str, Any] | None:
    try:
        got = json.loads((d / PLATE_FILE).read_text())
    except (OSError, ValueError):
        return None
    return got if isinstance(got, dict) and got.get("id") == rid else None


@router.post("/run-identity/remember")
async def post_remember(body: RememberBody, request: Request,
                        state: AppState = Depends(write_gate)) -> dict[str, Any]:  # fmt: skip
    """A person's press: the helper reads the name line of the character on screen once; the
    picture is stored under the typed name, or nothing is kept (the result file is deleted)."""
    store, status, _ = load(state)
    if status == "unreadable":
        raise refuse(state, 409, "store_unreadable")
    if body.base_revision != store.revision:
        raise refuse(state, 409, "revision_conflict", store.revision)
    why = ri.name_problem(body.name)
    if why is not None:
        raise refuse(state, 400, why)
    if any(ri.same_name(c.name, body.name) for c in store.characters):
        raise refuse(state, 409, "name_taken", body.name)
    if len(store.characters) >= ri.MAX_CHARACTERS:
        raise refuse(state, 409, "too_many_characters", ri.MAX_CHARACTERS)
    d = run_dir(state)
    if not read_status(d).get("helper_alive"):
        raise refuse(state, 503, "helper_not_running")
    if (d / "request.json").exists():
        raise refuse(state, 409, "helper_busy")
    rid = uuid.uuid4().hex
    (d / PLATE_FILE).unlink(missing_ok=True)
    tmp = d / f".request.{rid}"
    tmp.write_text(json.dumps({"id": rid, "action": "plate", "at": time.time()}) + "\n")
    os.replace(tmp, d / "request.json")
    with open(d / "requests.jsonl", "a") as fh:  # who and what (the typed name is not logged)
        fh.write(json.dumps({"id": rid, "action": "plate", **_who(request).model_dump()}) + "\n")
    got: dict[str, Any] | None = None
    t_end = time.monotonic() + PLATE_WAIT_S
    try:
        while got is None and time.monotonic() < t_end:
            await asyncio.sleep(PLATE_POLL_S)
            got = _plate_result(d, rid)
    finally:
        (d / PLATE_FILE).unlink(missing_ok=True)  # the picture is kept only in the store
    if got is None:
        raise refuse(state, 504, "plate_timeout",
                     f"no answer from the Run helper in {PLATE_WAIT_S:.0f} s")  # fmt: skip
    if not got.get("ok"):
        raise refuse(state, 409, "plate_failed", str(got.get("why") or "")[:300])
    bad = ri.plate_problem(got.get("w"), got.get("h"), got.get("rgb"))
    if bad is not None:
        raise refuse(state, 409, "plate_failed", bad)
    if got.get("same_as"):
        raise refuse(state, 409, "already_remembered", str(got["same_as"])[: ri.MAX_NAME])
    who = _who(request)
    with _LOCK:  # the store again: another save may have landed while the helper read
        now, status, _ = load(state)
        if status == "unreadable":
            raise refuse(state, 409, "store_unreadable")
        if any(ri.same_name(c.name, body.name) for c in now.characters):
            raise refuse(state, 409, "name_taken", body.name)
        if len(now.characters) >= ri.MAX_CHARACTERS:
            raise refuse(state, 409, "too_many_characters", ri.MAX_CHARACTERS)
        cid = f"c_{secrets.token_hex(4)}"
        while any(c.id == cid for c in now.characters):
            cid = f"c_{secrets.token_hex(4)}"
        char = ri.Character(id=cid, name=body.name, remembered=wall_clock_iso(),
                            w=int(got["w"]), h=int(got["h"]),
                            rgb=base64.b64decode(got["rgb"]))  # fmt: skip
        saved = ri.Store(revision=now.revision + 1, mode=now.mode,
                         characters=(*now.characters, char))  # fmt: skip
        write(state, saved)
        audit(state, who, "char_remember", body.name, (now.revision, saved.revision), None,
              [body.name], "remembered the name line of the character on screen")  # fmt: skip
    done = [{"action": "char_remember", "text": f"remembered {body.name}"}]
    return view(state, saved=True, remembered=cid, changes=done)
