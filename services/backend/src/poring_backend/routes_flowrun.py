"""The /flows page's RUN button, the backend side (Batt 2026-11-13: "I put the bot on the map,
press run on flows, and the bot plays by itself").

    GET  /flows/run   the host helper's status (scripts/flow_run.py) and whether it is alive
    POST /flows/run   {"action": "start" | "stop", "flow": "<id>"}: one request for the helper
    GET  /flows/survival  the heal and escape numbers: every map's ("global") and each map's own
    PUT  /flows/survival  {"scope": "global" | "map", "map": "<map>", "values": {...} | null}
         (Batt 2026-11-13 ~14:2x: "a global config for every map's flow; a map's flow that sets
         them again overrides it"); the helper reads the file at each start

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
from pydantic import BaseModel, ConfigDict, Field, field_validator

from poring_backend.routes_settings import _who, browser_gate, write_gate
from poring_backend.state import AppState
from poring_env.protocol import Mode

router = APIRouter(prefix="/flows")

HELPER_FRESH_S = 10.0  # the helper rewrites its status every 2 s: older = not running
ACTIVE = ("starting", "running", "stopping")


HotbarKey = Literal["F1", "F2", "F3", "F4", "F5", "F6", "F7", "F8", "F9"]


class RunSettings(BaseModel):
    """A person's run settings (2026-11-13, Batt: "don't hard-code the keys"): hotbar keys and the
    weight limit only, each from a fixed range. The Run helper checks them again against the flow
    (its defaults and the keys the run uses already: scripts/flow_run.py settings_of)."""

    model_config = ConfigDict(extra="forbid")
    fly_key: HotbarKey | None = None
    home_key: HotbarKey | None = None
    weight_home: float | None = Field(default=None, ge=0.3, le=0.8)
    # the death menu's button, game-picture px "X,Y" (another server's menu may differ)
    respawn_at: str | None = Field(default=None, pattern=r"^\d{1,4},\d{1,4}$")
    # its confirmation's OK, or "none" (a server that asks no confirmation)
    respawn_confirm_at: str | None = Field(default=None, pattern=r"^(\d{1,4},\d{1,4}|none)$")
    # Batt 2026-11-13 ~13:3x: "everything a user can set again; we only put the defaults"
    heal_key: HotbarKey | None = None
    knife_key: HotbarKey | None = None  # Batt's Knife swap: the Knife
    dagger_key: HotbarKey | None = None  # ... and the dagger back on
    knife_max_s: float | None = Field(default=None, ge=0.2, le=20.0)
    knife_hp_min: float | None = Field(default=None, ge=0.2, le=0.9)


def _on_step(v: float, step: float = 0.05) -> float:
    """A share on the helper's 0.05 grid (scripts/flow_run.py SURVIVAL_CHOICES), else refused."""
    if abs(v / step - round(v / step)) > 1e-6:
        raise ValueError(f"{v} is not a multiple of {step}")
    return round(v, 2)


class Survival(BaseModel):
    """The SURVIVAL group, all four numbers (a level's group is set whole): the ranges of
    dungeon_hunt.SURVIVAL_RANGES; the helper checks them again (flow_run.survival_check)."""

    model_config = ConfigDict(extra="forbid")
    potion_below: float = Field(ge=0.10, le=0.90)  # a heal item under this HP share
    fly_below: float = Field(ge=0.05, le=0.60)  # a Fly Wing under this HP share
    fly_rate: float = Field(ge=50.0, le=1000.0)  # a Fly Wing when the HP falls faster (HP/s) ...
    fly_rate_below: float = Field(ge=0.20, le=0.90)  # ... while under this share

    @field_validator("potion_below", "fly_below", "fly_rate_below")
    @classmethod
    def _grid(cls, v: float) -> float:
        return _on_step(v)

    @field_validator("fly_rate")
    @classmethod
    def _whole(cls, v: float) -> float:
        return float(round(v))


class SurvivalBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scope: Literal["global", "map"]
    map: str | None = Field(default=None, pattern=r"^[a-z0-9_@-]{1,40}$")
    values: Survival | None = None  # None: clear this level (the next one down applies)


def read_survival(d: Path) -> dict[str, Any]:
    """PURE but for the file read: {"global": {...}, "maps": {...}} (empty when there is none;
    ``broken`` when it cannot be read: the helper then refuses to start a run)."""
    try:
        doc = json.loads((d / "survival.json").read_text())
    except FileNotFoundError:
        return {"global": {}, "maps": {}}
    except (OSError, ValueError):
        return {"global": {}, "maps": {}, "broken": True}
    if not isinstance(doc, dict) or doc.get("v") != 1:
        return {"global": {}, "maps": {}, "broken": True}
    return {"global": doc.get("global") or {}, "maps": doc.get("maps") or {}}


class RunBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: Literal["start", "stop"]
    flow: str | None = Field(default=None, max_length=64)
    settings: RunSettings | None = None


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
    s = body.settings
    if s is not None:
        keys = [k for k in (s.heal_key, s.fly_key, s.home_key, s.knife_key, s.dagger_key) if k]
        if len(keys) != len(set(keys)):  # every key its own (the helper checks the whole set)
            return 400, "settings_same_key"
    for pt in (s.respawn_at, s.respawn_confirm_at) if s is not None else ():
        if pt is not None and pt != "none":
            x, y = (int(v) for v in pt.split(","))
            if x >= 1280 or y >= 720:
                return 400, "settings_off_picture"
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
    req: dict[str, Any] = {"id": rid, "action": body.action, "flow": body.flow, "at": time.time()}
    if body.action == "start" and body.settings is not None:
        req["settings"] = body.settings.model_dump(exclude_none=True)
    d.mkdir(parents=True, exist_ok=True)
    tmp = d / f".request.{rid}"
    tmp.write_text(json.dumps(req) + "\n")
    os.replace(tmp, d / "request.json")
    with open(d / "requests.jsonl", "a") as fh:
        fh.write(json.dumps({**req, **_who(request).model_dump()}) + "\n")
    return {"ok": True, "id": rid, "action": body.action, "flow": body.flow}


@router.get("/survival")
def get_survival(state: AppState = Depends(browser_gate)) -> dict[str, Any]:
    return read_survival(run_dir(state))


@router.put("/survival")
def put_survival(body: SurvivalBody, request: Request,
                 state: AppState = Depends(write_gate)) -> dict[str, Any]:  # fmt: skip
    if body.scope == "map" and not body.map:
        raise HTTPException(400, {"reason": "survival_map_missing"})
    d = run_dir(state)
    cur = read_survival(d)
    if cur.get("broken"):  # never write over a file a person must look at first
        raise HTTPException(409, {"reason": "survival_file_broken"})
    doc: dict[str, Any] = {"v": 1, "global": dict(cur["global"]), "maps": dict(cur["maps"])}
    vals = body.values.model_dump() if body.values is not None else None
    if body.scope == "global":
        doc["global"] = vals or {}
    elif vals is None:
        doc["maps"].pop(body.map, None)
    else:
        doc["maps"][body.map] = vals
    d.mkdir(parents=True, exist_ok=True)
    tmp = d / f".survival.{uuid.uuid4().hex}"
    tmp.write_text(json.dumps(doc, indent=2) + "\n")
    os.replace(tmp, d / "survival.json")
    with open(d / "survival.jsonl", "a") as fh:
        fh.write(json.dumps({"at": time.time(), "scope": body.scope, "map": body.map,
                             "values": vals, **_who(request).model_dump()}) + "\n")  # fmt: skip
    return {"ok": True, "global": doc["global"], "maps": doc["maps"]}
