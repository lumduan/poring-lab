"""The /flows page's RUN button, the backend side (Batt 2026-11-13: "I put the bot on the map,
press run on flows, and the bot plays by itself").

    GET  /flows/run   the host helper's status (scripts/flow_run.py) and whether it is alive; its
         "check" is the last check of the game screen (dungeon@9.45), passed through as written
    POST /flows/run   {"action": "start" | "check" | "stop", "flow": "<id>", "keys"?: {...}}: one
         request for the helper. "check" (Batt 2026-11-13 "do it"): the start checklist ticked from
         the game screen -- the runner's read-only check, which sends no input (no ASSIST needed).
         "keys" (Batt 2026-11-13: every hotbar key from a FUNCTION of the flow): all five of
         flow_config.KEY_FIELDS, each F1-F9, over the config file's for that run or check only
    POST /flows/run/project  {"project": <format 3>, "node": "<map node id>"} (Batt 2026-11-13,
         docs/planning/live-blocks.md stage 1): Run of a PROJECT by the LIVE BLOCK PLAYER
         (scripts/flow_play.py). The engine checks it first -- it validates, the node is a map
         node, 0 lint errors, every block plays live (poring_flow.live), the run-start check's
         verdict allows it (a hunt core's own L2 binding readiness is the runner's: answered),
         each hunt core's keys resolve from that node's functions (project.runner_keys) -- then
         the helper's state (alive, nothing running, ASSIST). Only then is the CHECKED project
         written (settings/flowrun/project.json, its canonical JSON; never one that may hold a
         secret) with ONE request {"action": "start", "flow": "project", "node", "project_hash",
         "max_s", "keys"?, "at"}. Refusals: 400 / 409 / 503 {"reason", "detail"} with reasons
         invalid_project (422, problems), not_a_map_node, lint_errors, not_live, run_start_refused,
         keys_refused, helper_not_running, already_running, mode_not_assist. Status stays GET
         /flows/run (flow id "project"); Stop is POST /flows/run {"action": "stop"}
    GET  /flows/config  every setting a person set: every map's ("global") and each map's own
    PUT  /flows/config  {"scope": "global" | "map", "map": "<map>", "group": "<group>",
         "values": {...} | null}: one group at one level (Batt 2026-11-13: "nothing is fixed, we
         only put the defaults"; "a global config for every map's flow, a map's own on top";
         scripts/flow_config.py is the registry); the helper reads the file at each start

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

import importlib.util
import json
import os
import sys
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
    """A Run request names a flow and nothing else (Batt 2026-11-13 ~14:4x: every setting lives in
    the config file, every map's and each map's own; the helper reads it at the start) -- but the
    five hotbar keys the flow's functions give (``keys``, checked by flow_config.keys_problem)."""

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
    """POST /flows/run/check: the read-only start check (dungeon@9.45; pixels only, no input)."""

    model_config = ConfigDict(extra="forbid")
    flow: str = Field(max_length=64)
    keys: dict[str, Any] | None = None


class ConfigBody(BaseModel):
    """PUT /flows/config: one GROUP of settings at one level (every map, or one map's own);
    ``values`` None or {}: that group's own values there are removed (the next level applies)."""

    model_config = ConfigDict(extra="forbid")
    scope: Literal["global", "map"]
    map: str | None = Field(default=None, pattern=r"^[a-z0-9_@-]{1,40}$")
    group: str = Field(max_length=40)
    values: dict[str, Any] | None = None


def flow_config(state: AppState) -> Any:
    """scripts/flow_config.py (the settings' registry: pure, stdlib only), from the read-only
    scripts mount (ZONES_CODE_DIR, as flows_zones imports the zones loader) or, on the host's
    tests, the repo's scripts/; None when it is not there (the routes then answer 503)."""
    if "fc" in _FC:
        return _FC["fc"]
    out: Any = None
    here = Path(__file__).resolve().parents
    repo_scripts = here[4] / "scripts" if len(here) > 4 else None  # the host's tests only
    for d in (state.settings.zones_code_dir, repo_scripts):
        if d is None or not (Path(d) / "flow_config.py").is_file():
            continue
        path = Path(d) / "flow_config.py"
        spec = importlib.util.spec_from_file_location("flow_config_backend", path)
        if spec is None or spec.loader is None:
            continue
        mod = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = mod  # its dataclasses look their module up while it loads
        try:
            spec.loader.exec_module(mod)
        except Exception:  # noqa: BLE001 -- a broken module is "not there", never a 500
            sys.modules.pop(spec.name, None)
            continue
        out = mod
        break
    _FC["fc"] = out
    return out


_FC: dict[str, Any] = {}


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
    if body.action == "check":  # dungeon@9.45: it reads the screen only (no ASSIST needed)
        checking = (st.get("check") or {}).get("state") == "checking"
        return (409, "check_running") if checking else None
    if mode != Mode.ASSIST:
        return 409, "mode_not_assist"
    return None


def keys_refusal(body: RunBody, fc: Any) -> tuple[int, str, str] | None:
    """Why the request's ``keys`` cannot go to the helper (None: none given, or they can): the
    helper's own rule (flow_config.keys_problem), refused here first with its words."""
    if body.keys is None:
        return None
    if fc is None:
        return 503, "config_engine_unavailable", "the settings list cannot be read here"
    if body.action == "stop":
        return 400, "keys_refused", "keys go with start or check, not stop"
    why = fc.keys_problem(body.keys)
    return None if why is None else (400, "keys_refused", str(why))


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
    if body.action == "start" and body.flow == PROJECT:  # a project names its node and itself
        state.drops.record("flowrun_http", "project_has_its_own_route", "post")
        raise HTTPException(400, {"reason": "project_has_its_own_route",
                                  "detail": "POST /flows/run/project {project, node}"})  # fmt: skip
    if body.action == "check":  # its own route since matpilot's #16
        state.drops.record("flowrun_http", "check_has_its_own_route", "post")
        raise HTTPException(400, {"reason": "check_has_its_own_route",
                                  "detail": "POST /flows/run/check {flow, keys?}"})  # fmt: skip
    return _submit(body, request, state)


@router.post("/run/check")
def post_check(body: CheckBody, request: Request,
               state: AppState = Depends(write_gate)) -> dict[str, Any]:  # fmt: skip
    return _submit(RunBody(action="check", flow=body.flow, keys=body.keys), request, state)


def _submit(body: RunBody, request: Request, state: AppState) -> dict[str, Any]:
    d = run_dir(state)
    bad = keys_refusal(body, flow_config(state) if body.keys is not None else None)
    if bad is not None:
        state.drops.record("flowrun_http", bad[1], "post")
        raise HTTPException(bad[0], {"reason": bad[1], "detail": bad[2]})
    st = read_status(d)
    why = refusal(body, st, state.mux.mode)
    if why is not None:
        state.drops.record("flowrun_http", why[1], "post")
        raise HTTPException(why[0], {"reason": why[1]})
    rid = uuid.uuid4().hex
    req: dict[str, Any] = {"id": rid, "action": body.action, "flow": body.flow, "at": time.time()}
    if body.keys is not None:  # the flow's functions' keys (all five, checked): that run's only
        req["keys"] = dict(body.keys)
    d.mkdir(parents=True, exist_ok=True)
    tmp = d / f".request.{rid}"
    tmp.write_text(json.dumps(req) + "\n")
    os.replace(tmp, d / "request.json")
    with open(d / "requests.jsonl", "a") as fh:
        fh.write(json.dumps({**req, **_who(request).model_dump()}) + "\n")
    return {"ok": True, "id": rid, "action": body.action, "flow": body.flow,
            **({"keys": req["keys"]} if "keys" in req else {})}  # fmt: skip


# --- Run of a PROJECT (live-blocks.md stage 1): the live block player -----------------------------
PROJECT = "project"  # scripts/flow_run.py PROJECT: the run's flow id in requests and status.json
PROJECT_FILE = "project.json"


def _refuse_run(state: AppState, status: int, reason: str, detail: Any) -> HTTPException:
    state.drops.record("flowrun_http", reason, "post")
    return HTTPException(status, {"reason": reason, "detail": detail})


async def _project_body(request: Request, state: AppState) -> ProjectRunBody:
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
        return ProjectRunBody.model_validate_json(raw)
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


@router.get("/config")
def get_config(state: AppState = Depends(browser_gate)) -> dict[str, Any]:
    """Every map's values and each map's own (settings/flowrun/config.json, else 8e3ca2df's
    survival.json); ``broken``: the file a person must look at (Run refuses until then)."""
    fc = flow_config(state)
    if fc is None:
        raise HTTPException(503, {"reason": "config_engine_unavailable"})
    got = fc.read_config(run_dir(state))
    if isinstance(got, str):
        return {"global": {}, "maps": {}, "broken": got}
    return {"global": dict(got["global"]), "maps": dict(got["maps"])}


@router.put("/config")
def put_config(body: ConfigBody, request: Request,
               state: AppState = Depends(write_gate)) -> dict[str, Any]:  # fmt: skip
    fc = flow_config(state)
    if fc is None:
        raise HTTPException(503, {"reason": "config_engine_unavailable"})
    d = run_dir(state)
    cur = fc.read_config(d)
    if isinstance(cur, str):  # never write over a file a person must look at first
        raise HTTPException(409, {"reason": "config_file_broken", "detail": cur})
    doc = fc.put_level(cur, body.scope, body.map, body.group, body.values)
    if isinstance(doc, str):
        raise HTTPException(400, {"reason": "config_refused", "detail": doc})
    # every flow the helper lists must still run: no two of its settings on one hotbar key
    flows = (read_status(d).get("flows") or {}) if (d / "status.json").exists() else {}
    for f in flows.values():
        vals, _ = fc.effective(f.get("defaults") or {}, doc, f.get("map") or "")
        why = fc.clash(vals)
        if why:
            raise HTTPException(400, {"reason": "config_refused", "detail": why})
    d.mkdir(parents=True, exist_ok=True)
    tmp = d / f".config.{uuid.uuid4().hex}"
    tmp.write_text(json.dumps(doc, indent=2) + "\n")
    os.replace(tmp, d / fc.FILE)
    with open(d / "config.jsonl", "a") as fh:
        fh.write(json.dumps({"at": time.time(), "scope": body.scope, "map": body.map,
                             "group": body.group, "values": body.values,
                             **_who(request).model_dump()}) + "\n")  # fmt: skip
    return {"ok": True, "global": doc["global"], "maps": doc["maps"]}
