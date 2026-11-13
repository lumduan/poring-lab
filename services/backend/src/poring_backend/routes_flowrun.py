"""The /flows page's RUN button, the backend side (Batt 2026-11-13: "I put the bot on the map,
press run on flows, and the bot plays by itself").

    GET  /flows/run   the host helper's status (scripts/flow_run.py) and whether it is alive
    POST /flows/run   {"action": "start" | "stop", "flow": "<id>"}: one request for the helper

The backend starts nothing itself (it cannot reach the host's processes, by design). It writes ONE
request file into the human-only settings store (``settings/flowrun/request.json``, mounted only
into the backend) and the host helper, a user service, consumes it. A request only NAMES a flow the
helper lists in its own status; the command line it runs lives in scripts/flow_run.py.

Writes pass routes_settings.write_gate unchanged: a console browser on the LAN, with the console's
Origin and the CSRF token, never the lab host itself (any process there can forge the Origin) nor
the Windows host the bot drives, at most 20 a minute, every refusal audited. Each accepted request
is logged (requests.jsonl, who and what). Reads pass the console-browser gate.
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
from poring_env.protocol import Mode

router = APIRouter(prefix="/flows")

HELPER_FRESH_S = 10.0  # the helper rewrites its status every 2 s: older = not running
ACTIVE = ("starting", "running", "stopping")


class RunBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: Literal["start", "stop"]
    flow: str | None = Field(default=None, max_length=64)


def run_dir(state: AppState) -> Path:
    return state.settings.settings_dir / "flowrun"


def read_status(d: Path, now: float | None = None) -> dict[str, Any]:
    """PURE but for the file read: the helper's status, with ``helper_alive``."""
    f = d / "status.json"
    try:
        st = json.loads(f.read_text())
    except (OSError, ValueError):
        why = "the Run helper has not started (poring-lab-flowrun.service)"
        return {"state": "no_helper", "helper_alive": False, "flows": {}, "detail": why}
    if not isinstance(st, dict):
        return {"state": "no_helper", "helper_alive": False, "flows": {}, "detail": "unreadable"}
    age = (time.time() if now is None else now) - float(st.get("t_wall") or 0.0)
    st["helper_alive"] = age <= HELPER_FRESH_S
    st["age_s"] = round(age, 1)
    if not st["helper_alive"]:
        st["detail"] = f"the Run helper has not answered for {age:.0f} s"
    return st


def refusal(body: RunBody, st: dict[str, Any], mode: Mode) -> tuple[int, str] | None:
    """PURE: why this request cannot be passed to the helper (None: it can)."""
    if not st.get("helper_alive"):
        return 503, "helper_not_running"
    if body.action == "stop":
        return None if st.get("state") in ACTIVE else (409, "nothing_running")
    if body.flow not in (st.get("flows") or {}):
        return 400, "unknown_flow"
    if st.get("state") in ACTIVE:
        return 409, "already_running"
    if mode != Mode.ASSIST:
        return 409, "mode_not_assist"
    return None


@router.get("/run")
def get_run(state: AppState = Depends(browser_gate)) -> dict[str, Any]:
    return {**read_status(run_dir(state)), "mode": state.mux.mode}


@router.post("/run")
def post_run(body: RunBody, request: Request,
             state: AppState = Depends(write_gate)) -> dict[str, Any]:  # fmt: skip
    d = run_dir(state)
    st = read_status(d)
    why = refusal(body, st, state.mux.mode)
    if why is not None:
        state.drops.record("flowrun_http", why[1], "post")
        raise HTTPException(why[0], {"reason": why[1]})
    rid = uuid.uuid4().hex
    req = {"id": rid, "action": body.action, "flow": body.flow, "at": time.time()}
    d.mkdir(parents=True, exist_ok=True)
    tmp = d / f".request.{rid}"
    tmp.write_text(json.dumps(req) + "\n")
    os.replace(tmp, d / "request.json")
    with open(d / "requests.jsonl", "a") as fh:
        fh.write(json.dumps({**req, **_who(request).model_dump()}) + "\n")
    return {"ok": True, "id": rid, "action": body.action, "flow": body.flow}
