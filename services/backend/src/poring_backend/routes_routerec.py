"""The console's "Record route" button, the backend side (docs/planning/waypoints-npc-recording.md
Amendment 11: phase 2 of Amendment 8, routes from a recording of the player's own play).

    GET  /routes/record   the host helper's status (scripts/route_rec.py) and whether it is alive by
         its heartbeat: its last check (readiness, the minimap, the disk and the minutes that fit),
         the recording going on (elapsed, disk used, minutes left), the last one's end, and the
         guide notifications (the last N, each with an id: the page shows the new ones)
    POST /routes/record   {"action": "check" | "start" | "stop", "map"?: start only}: ONE request
         for the helper. Refusals (409 / 503 {"reason", "detail"}): helper_not_running,
         already_recording (a check or a start while one records: the status carries its live
         readiness), nothing_recording (a stop), input_writer_busy (a start while a bot of ours
         plays: a route recording is the PERSON's play; the helper refuses it too). A map goes with
         a start only (400 map_goes_with_start); anything else in the body is refused (422).

The backend starts nothing itself (it cannot reach the host's processes, by design). It writes ONE
request file into the human-only settings store (``settings/routerec/request.json``, mounted only
into the backend at /lab-settings) and the host helper, a user service
(scripts/host/poring-lab-routerec.service), consumes it. The helper sends no input, ever; it runs
the readiness check on a fresh frame before every start and refuses a start that is not ready.
No mux mode is needed: the person plays, the bot does not.

Writes pass routes_settings.write_gate UNCHANGED: a console browser on the LAN, with the console's
Origin and the CSRF token, never the lab host itself nor the Windows host, at most 20 a minute,
every refusal audited. Each accepted request is logged (requests.jsonl, who and what). Reads pass
the console-browser gate.
"""

from __future__ import annotations

import json
import os
import time
import uuid
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from poring_backend.routes_settings import _who, browser_gate, write_gate
from poring_backend.state import AppState

router = APIRouter(prefix="/routes")

HELPER_FRESH_S = 10.0  # the helper rewrites its status every 2 s: older = not running
ACTIVE = ("starting", "recording", "stopping")
STOPPABLE = ("starting", "recording")
MAP_NAME = r"^[a-z0-9][a-z0-9_]{0,31}$"  # scripts/route_rec.py MAP_NAME: the folder's map name


class RecordBody(BaseModel):
    """POST /routes/record: a check, a start (with the map for the folder's name, if known) or a
    stop."""

    model_config = ConfigDict(extra="forbid")
    action: Literal["check", "start", "stop"]
    map: str | None = Field(default=None, pattern=MAP_NAME)


def rec_dir(state: AppState) -> Path:
    return state.settings.settings_dir / "routerec"


def read_status(d: Path, now: float | None = None) -> dict[str, Any]:
    """PURE but for the file read: the helper's status, with ``helper_alive`` and ``age_s``."""
    try:
        st = json.loads((d / "status.json").read_text())
    except (OSError, ValueError):
        why = "the Record route helper has not started (poring-lab-routerec.service)"
        return {"state": "no_helper", "helper_alive": False, "detail": why,
                "notifications": []}  # fmt: skip
    if not isinstance(st, dict):
        return {"state": "no_helper", "helper_alive": False, "detail": "unreadable",
                "notifications": []}  # fmt: skip
    age = (time.time() if now is None else now) - float(st.get("t_wall") or 0.0)
    st["helper_alive"] = age <= HELPER_FRESH_S
    st["age_s"] = round(age, 1)
    if not st["helper_alive"]:
        st["detail"] = f"the Record route helper has not answered for {age:.0f} s"
    return st


def refusal(body: RecordBody, st: dict[str, Any]) -> tuple[int, str] | None:
    """PURE: why this request cannot be passed to the helper (None: it can)."""
    if body.map is not None and body.action != "start":
        return 400, "map_goes_with_start"
    if not st.get("helper_alive"):
        return 503, "helper_not_running"
    state = st.get("state")
    if body.action == "stop":
        return None if state in STOPPABLE else (409, "nothing_recording")
    if state in ACTIVE:
        return 409, "already_recording"
    if body.action == "start" and st.get("busy"):
        return 409, "input_writer_busy"
    return None


@router.get("/record")
def get_record(state: AppState = Depends(browser_gate)) -> dict[str, Any]:
    return read_status(rec_dir(state))


@router.post("/record")
def post_record(body: RecordBody, request: Request,
                state: AppState = Depends(write_gate)) -> dict[str, Any]:  # fmt: skip
    d = rec_dir(state)
    st = read_status(d)
    why = refusal(body, st)
    if why is not None:
        state.drops.record("routerec_http", why[1], "post")
        detail = str(st.get("busy") or st.get("detail") or "")
        raise HTTPException(why[0], {"reason": why[1], "detail": detail})
    rid = uuid.uuid4().hex
    req: dict[str, Any] = {"id": rid, "action": body.action, "at": time.time()}
    if body.action == "start" and body.map is not None:
        req["map"] = body.map
    d.mkdir(parents=True, exist_ok=True)
    tmp = d / f".request.{rid}"
    tmp.write_text(json.dumps(req) + "\n")
    os.replace(tmp, d / "request.json")
    with open(d / "requests.jsonl", "a") as fh:  # who and what
        fh.write(json.dumps({**req, **_who(request).model_dump()}) + "\n")
    return {"ok": True, "id": rid, "action": body.action,
            **({"map": body.map} if body.map is not None else {})}  # fmt: skip
