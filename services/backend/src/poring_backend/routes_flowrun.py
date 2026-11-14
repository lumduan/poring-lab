"""The /flows page's RUN button, the backend side (Batt 2026-11-13: "I put the bot on the map,
press run on flows, and the bot plays by itself").

    GET  /flows/run   the host helper's status (scripts/flow_run.py) and whether it is alive; its
         "check" is the last check of the game screen (dungeon@9.45), passed through as written
    POST /flows/run   {"action": "stop"}: Stop. A start is a project's (POST /flows/run/project)
         and a check has its own route (POST /flows/run/check); either here is refused in words
    POST /flows/run/project  {"project": <format 3>, "node": "<map node id>"} (Batt 2026-11-13,
         docs/planning/live-blocks.md stage 1): Run of a PROJECT by the LIVE BLOCK PLAYER
         (scripts/flow_play.py). The engine checks it first -- it validates, the node is a map
         node, 0 lint errors (the setting blocks' values and their clash rule among them), every
         block plays live (poring_flow.live), the run-start check's verdict allows it (a hunt
         core's own L2 binding readiness is the runner's: answered), each hunt core's keys resolve
         from that node's functions (project.runner_keys) -- then the helper's state (alive,
         nothing running, ASSIST). Only then is the CHECKED project written
         (settings/flowrun/project.json, its canonical JSON; never one that may hold a secret) with
         ONE request {"action": "start", "flow": "project", "node", "project_hash", "max_s",
         "keys"?, "at"}. Refusals: 400 / 409 / 503 {"reason", "detail"} with reasons
         invalid_project (422, problems), not_a_map_node, lint_errors, not_live,
         run_start_refused, keys_refused, helper_not_running, already_running, input_writer_busy
         (round 17 N5: the helper's status names another input writer of ours playing, its
         `busy`), mode_not_assist. Status stays GET /flows/run (flow id "project"); Stop is POST
         /flows/run {"action": "stop"}
    POST /flows/run/check  {"project": <format 3>, "node": "<map node id>"} (dungeon@9.45, Batt
         2026-11-13 "do it"; a project's since 2026-11-14): the start checklist ticked from the
         game screen -- the runner's read-only check, which sends no input (no ASSIST needed),
         with the node's keys (its functions) and its SETTINGS (its setting blocks > Global's >
         the defaults: poring_flow.settings, live-blocks.md 12), which go in the request
         ({"action": "check", "flow": "project", "node", "keys", "vals"}; the helper checks them
         again). Refusals: invalid_project, not_a_map_node, no_hunt_core, keys_refused,
         settings_refused, and the helper's states

➡️ 2026-11-14 ~15:2x (Batt: "there should be no runner [page] ... make them ALL blocks"): GET /
PUT /flows/config (the settings file settings/flowrun/config.json, empty when it went) and the
runner-only start (POST /flows/run {"action": "start", "flow": "xmas_dun02_rogue"}) are gone: every
setting is a block of the project, read from the project a start or a check sends.

The backend starts nothing itself (it cannot reach the host's processes, by design). It writes ONE
request file into the human-only settings store (``settings/flowrun/request.json``, mounted only
into the backend) and the host helper, a user service, consumes it. A request names the project run
(its checked file's hash) or a check's node, keys and settings; the command line it runs lives in
scripts/flow_run.py.

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
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from poring_backend.routes_settings import _who, browser_gate, write_gate
from poring_backend.state import AppState
from poring_env.protocol import Mode

router = APIRouter(prefix="/flows")

HELPER_FRESH_S = 10.0  # the helper rewrites its status every 2 s: older = not running
ACTIVE = ("starting", "running", "stopping")


class RunBody(BaseModel):
    """POST /flows/run: Stop (``action`` "stop"). A start or a check here is refused in words:
    each has its own route with the project (2026-11-14: the settings are the project's blocks)."""

    model_config = ConfigDict(extra="forbid")
    # matpilot 2026-11-13 #16: the read-only check has its OWN route (POST /flows/run/check), so a
    # guard can tell a start from a check and a mistyped body can never start the bot
    action: Literal["start", "stop", "check"]
    flow: str | None = Field(default=None, max_length=64)
    keys: dict[str, Any] | None = None


class ProjectRunBody(BaseModel):
    """POST /flows/run/project: a project and the map node to play (the contract the /flows and
    /maps pages build against; anything else is refused, 422)."""

    model_config = ConfigDict(extra="forbid")
    project: dict[str, Any]
    node: str = Field(pattern=r"^[A-Za-z][A-Za-z0-9_]{0,39}$")


class CheckBody(BaseModel):
    """POST /flows/run/check: the read-only start check (dungeon@9.45; pixels only, no input) of
    a project's map node: its keys and settings come from the project (2026-11-14)."""

    model_config = ConfigDict(extra="forbid")
    project: dict[str, Any]
    node: str = Field(pattern=r"^[A-Za-z][A-Za-z0-9_]{0,39}$")


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
    """PURE: why this request cannot be passed to the helper (None: it can). A start or a check
    of the project carries its own body (post_run_project, post_check); this is its state rule."""
    if not st.get("helper_alive"):
        return 503, "helper_not_running"
    if body.action == "stop":
        return None if st.get("state") in ACTIVE else (409, "nothing_running")
    if st.get("state") in ACTIVE:
        return 409, "already_running"
    if st.get("busy"):  # round 17 N5: another input writer of ours plays (the helper refuses too)
        return 409, "input_writer_busy"
    if body.action == "check":  # dungeon@9.45: it reads the screen only (no ASSIST needed)
        checking = (st.get("check") or {}).get("state") == "checking"
        return (409, "check_running") if checking else None
    if mode != Mode.ASSIST:
        return 409, "mode_not_assist"
    return None


@router.get("/run")
def get_run(state: AppState = Depends(browser_gate)) -> dict[str, Any]:
    return {**read_status(run_dir(state)), "mode": state.mux.mode}


@router.get("/run/end.png")
def get_end_png(state: AppState = Depends(browser_gate)) -> FileResponse:
    """The last run's end picture (matpilot 2026-11-13: "show end.png as an image, not a server
    path"): the helper copies it into its own folder at the run's end. A console browser only."""
    f = run_dir(state) / "end.png"
    if not f.is_file():
        raise HTTPException(404, {"reason": "no_end_picture"})
    return FileResponse(f, media_type="image/png", headers={"Cache-Control": "no-store"})


@router.post("/run")
def post_run(body: RunBody, request: Request,
             state: AppState = Depends(write_gate)) -> dict[str, Any]:  # fmt: skip
    if body.action == "start":  # a project names its node and itself (no runner-only start)
        state.drops.record("flowrun_http", "project_has_its_own_route", "post")
        raise HTTPException(400, {"reason": "project_has_its_own_route",
                                  "detail": "POST /flows/run/project {project, node}"})  # fmt: skip
    if body.action == "check":  # its own route since matpilot's #16
        state.drops.record("flowrun_http", "check_has_its_own_route", "post")
        raise HTTPException(400, {"reason": "check_has_its_own_route",
                                  "detail": "POST /flows/run/check {project, node}"})  # fmt: skip
    return _submit(body, request, state)


@router.post("/run/check")
async def post_check(request: Request,
                     state: AppState = Depends(write_gate)) -> dict[str, Any]:  # fmt: skip
    from poring_backend import routes_flows as rf

    body = await _project_body(request, state, CheckBody)
    got = await rf._compute(request, state, lambda: check_values(state, body.project, body.node))
    return _submit(RunBody(action="check"), request, state, extra=got)


def _submit(body: RunBody, request: Request, state: AppState,
            extra: dict[str, Any] | None = None) -> dict[str, Any]:  # fmt: skip
    d = run_dir(state)
    if body.keys is not None:
        state.drops.record("flowrun_http", "keys_refused", "post")
        raise HTTPException(400, {"reason": "keys_refused",
                                  "detail": "keys come from a project's functions"})  # fmt: skip
    st = read_status(d)
    why = refusal(body, st, state.mux.mode)
    if why is not None:
        state.drops.record("flowrun_http", why[1], "post")
        raise HTTPException(why[0], {"reason": why[1]})
    rid = uuid.uuid4().hex
    flow = PROJECT if body.action == "check" else body.flow
    req: dict[str, Any] = {"id": rid, "action": body.action, "flow": flow, "at": time.time()}
    if extra:  # a check: the node, its keys and its settings (check_values)
        req.update({k: extra[k] for k in ("node", "keys", "vals")})
    d.mkdir(parents=True, exist_ok=True)
    tmp = d / f".request.{rid}"
    tmp.write_text(json.dumps(req) + "\n")
    os.replace(tmp, d / "request.json")
    with open(d / "requests.jsonl", "a") as fh:  # who and what (a check's settings by count)
        logged = {k: v for k, v in req.items() if k != "vals"}
        if "vals" in req:
            logged["vals_n"] = len(req["vals"])
        fh.write(json.dumps({**logged, **_who(request).model_dump()}) + "\n")
    return {"ok": True, "id": rid, "action": body.action, "flow": flow,
            **({"node": req["node"], "keys": req["keys"]} if extra else {})}  # fmt: skip


def check_values(state: AppState, raw: dict[str, Any], node: str) -> dict[str, Any]:
    """A project check's keys and settings (2026-11-14, live-blocks.md 12): the project validates,
    the node is a map node with a hunt core, its keys resolve from its functions, its setting
    blocks hold usable values that run together. Raises the refusal (HTTPException)."""
    from poring_flow import live
    from poring_flow import project as pj
    from poring_flow import settings as st
    from poring_flow.lint import settings as ls

    text = json.dumps(raw, ensure_ascii=False, separators=(",", ":"))
    try:
        p = pj.from_json(text)
        c = pj.compile_project(p)
    except pj.ProjectError as e:
        raise _refuse_run(state, 422, "invalid_project",
                          [q.doc() for q in e.problems[:50]]) from None  # fmt: skip
    if not isinstance(p.node(node), pj.MapNode):
        raise _refuse_run(state, 400, "not_a_map_node", f"{node} is no map node of the project")
    hunts = {b for b, _ in live.runner_blocks(c.flow)} if c.flow is not None else set()
    if node not in hunts:
        raise _refuse_run(state, 400, "no_hunt_core", f"{node}'s main has no hunt with the "
                          "runner: the check is the runner's")  # fmt: skip
    rk = pj.runner_keys(p, node, c)
    if rk.keys is None:
        raise _refuse_run(state, 400, "keys_refused", {"node": node, "problems": rk.problems})
    nv = ls.node_values(p, node, dict(rk.keys))
    why = nv.problems[0] if nv.problems else st.clash(nv.vals)
    if why:
        raise _refuse_run(state, 400, "settings_refused", why)
    vals = {f.name: nv.vals[f.name] for f in st.FIELDS if f.block}
    return {"node": node, "keys": dict(rk.keys), "vals": vals}


# --- Run of a PROJECT (live-blocks.md stage 1): the live block player -----------------------------
PROJECT = "project"  # scripts/flow_run.py PROJECT: the run's flow id in requests and status.json
PROJECT_FILE = "project.json"


def _refuse_run(state: AppState, status: int, reason: str, detail: Any) -> HTTPException:
    state.drops.record("flowrun_http", reason, "post")
    return HTTPException(status, {"reason": reason, "detail": detail})


async def _project_body(request: Request, state: AppState,
                        model: type[BaseModel] = ProjectRunBody) -> Any:  # fmt: skip
    """The body, read with the flow routes' caps (size while reading, depth), then the model."""
    from poring_backend import routes_flows as rf

    length = request.headers.get("content-length")
    if length is not None and (not length.isdigit() or int(length) > rf.MAX_BODY):
        raise _refuse_run(state, 413, "too_large", "at most 1 MiB")
    chunks: list[bytes] = []
    size = 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > rf.MAX_BODY:
            raise _refuse_run(state, 413, "too_large", "at most 1 MiB")
        chunks.append(chunk)
    raw = b"".join(chunks)
    try:
        from poring_flow import ir
    except ImportError:
        raise _refuse_run(state, 503, "flow_engine_unavailable", "no flow engine here") from None
    if ir._depth(raw.decode("utf-8", errors="replace")) > ir.MAX_JSON_DEPTH + 2:
        raise _refuse_run(state, 422, "too_deep", "nested too deep")
    try:
        return model.model_validate_json(raw)
    except ValidationError as e:
        errs = [
            f"{'.'.join(str(x) for x in er['loc'])}: {er['msg']}"
            for er in e.errors(include_url=False, include_context=False, include_input=False)[:20]
        ]
        raise _refuse_run(state, 422, "invalid_body", errs) from None


def project_check(state: AppState, raw: dict[str, Any], node: str) -> dict[str, Any]:
    """The engine's checks of a project run, in order; raises the refusal (HTTPException) or
    returns {"project", "text", "hash", "keys", "max_s", "verdict"}. Runs in the flows' worker
    thread (routes_flows._compute)."""
    from poring_backend import routes_flows as rf
    from poring_backend.flows_settings import runtime_limits
    from poring_flow import live
    from poring_flow import project as pj

    text = json.dumps(raw, ensure_ascii=False, separators=(",", ":"))
    try:
        p = pj.from_json(text)
    except pj.ProjectError as e:
        raise _refuse_run(state, 422, "invalid_project",
                          [q.doc() for q in e.problems[:50]]) from None  # fmt: skip
    if pj.has_secret(p):  # never written, never hashed back (ADR-0004 c)
        raise _refuse_run(state, 400, "lint_errors", "a login credential that is not a plain "
                          "name: a project never holds a secret")  # fmt: skip
    n = p.node(node)
    if not isinstance(n, pj.MapNode):
        raise _refuse_run(
            state,
            400,
            "not_a_map_node",
            f"{node} is no map node of the project: the player starts on one",
        )
    try:
        c = pj.compile_project(p)
    except pj.ProjectError as e:
        raise _refuse_run(state, 422, "invalid_project",
                          [q.doc() for q in e.problems[:50]]) from None  # fmt: skip
    _, max_s = runtime_limits(state)
    world, _notes = rf._world(state, p, c, "local")
    zp, _ = rf._zones_provider(state, world)
    rp, _ = rf._routes_provider(state, world)
    c, findings = pj.project_lint(p, world=world, resolver=rf._resolver(state, p),
                                  runtime_max_s=max_s, zones_provider=zp, routes_provider=rp,
                                  envs=rf._envs(state), compiled=c)  # fmt: skip
    errors = [f.message for f in findings if f.severity == "error"]
    if errors:
        raise _refuse_run(state, 400, "lint_errors", {"count": len(errors), "first": errors[:10]})
    bad = live.problems(c.flow) if c.flow is not None else []
    if bad:
        raise _refuse_run(state, 400, "not_live", [
            {"path": c.where(b.path).path or b.path, "what": b.what, "words": b.words}
            for b in bad[:50]])  # fmt: skip
    v = live.verdict(c, findings, world=world, resolver_given=True, runtime_max_s=max_s,
                     zones_loaded=zp is not None, routes_loaded=rp is not None)  # fmt: skip
    if not v.allowed:
        why = [c.text(r) for r in (*v.errors, *v.readiness, *v.reasons)][:20]
        raise _refuse_run(state, 400, "run_start_refused",
                          {"summary": c.text(v.summary()), "reasons": why})  # fmt: skip
    keys: dict[str, str] | None = None
    hunts = {b for b, _ in live.runner_blocks(c.flow)} if c.flow is not None else set()
    for b in sorted(hunts):
        rk = pj.runner_keys(p, b, c)
        if rk.keys is None:
            raise _refuse_run(state, 400, "keys_refused", {"node": b, "problems": rk.problems})
        if b == node:
            keys = dict(rk.keys)
    return {"project": p, "text": pj.canonical_json(p), "hash": pj.project_hash(p),
            "keys": keys, "max_s": max_s, "verdict": v.summary()}  # fmt: skip


@router.post("/run/project")
async def post_run_project(request: Request,
                           state: AppState = Depends(write_gate)) -> dict[str, Any]:  # fmt: skip
    from poring_backend import routes_flows as rf

    body = await _project_body(request, state)
    got = await rf._compute(request, state, lambda: project_check(state, body.project, body.node))
    d = run_dir(state)
    st = read_status(d)
    if not st.get("helper_alive"):
        raise _refuse_run(state, 503, "helper_not_running", str(st.get("detail") or ""))
    if st.get("state") in ACTIVE:
        raise _refuse_run(state, 409, "already_running", "a run is going: press Stop first")
    if st.get("busy"):  # round 17 N5: another input writer of ours plays (the helper refuses too)
        raise _refuse_run(state, 409, "input_writer_busy", str(st["busy"]))
    if state.mux.mode != Mode.ASSIST:
        raise _refuse_run(state, 409, "mode_not_assist", f"the mux is {state.mux.mode.value}")
    rid = uuid.uuid4().hex
    d.mkdir(parents=True, exist_ok=True)
    tmp = d / f".{PROJECT_FILE}.{rid}"
    tmp.write_bytes(got["text"].encode("utf-8"))  # the CHECKED project: its hash is the request's
    os.replace(tmp, d / PROJECT_FILE)
    req: dict[str, Any] = {"id": rid, "action": "start", "flow": PROJECT, "node": body.node,
                           "project_hash": got["hash"], "max_s": int(got["max_s"]),
                           "at": time.time()}  # fmt: skip
    if got["keys"] is not None:
        req["keys"] = got["keys"]
    tmp = d / f".request.{rid}"
    tmp.write_text(json.dumps(req) + "\n")
    os.replace(tmp, d / "request.json")
    with open(d / "requests.jsonl", "a") as fh:  # who and what (the project by its hash)
        fh.write(json.dumps({**req, "project": got["project"].name,
                             **_who(request).model_dump()}) + "\n")  # fmt: skip
    return {"ok": True, "id": rid, "action": "start", "flow": PROJECT, "node": body.node,
            "project_hash": got["hash"], "max_s": int(got["max_s"]), "verdict": got["verdict"],
            **({"keys": got["keys"]} if got["keys"] is not None else {})}  # fmt: skip
