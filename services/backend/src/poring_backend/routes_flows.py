"""The MW2 flow editor's engine: COMPUTATION ONLY (docs/planning/mw2-block-editor.md section 5).

    GET  /flows/catalogue[?client=<L2 build>]   blocks, sensors, verification badges, windows
    GET  /flows/world?source=&server=&maps=      the pickers' static data (map sheets, labels)
    GET  /flows/sample                           the committed SYNTHETIC sample flow (IR JSON)
    POST /flows/lint      {flow, world}          MW1's linter (layers 1-3), findings by node
    POST /flows/simulate  {flow, world, scenario}  the trace (poring_flow.trace): no game
    POST /flows/python    {flow}                 MW1's canonical Python view (read-only)

What these routes NEVER do: send input, reach the mux, the executor, the agent channel or any
socket; store anything. They compute and return. The IR in a body is HOSTILE input: MW1's own
caps and validation apply (`ir.from_json`: 1 MiB, depth 256, the schema), the scenario is a
bounded model, and the computation runs in a worker thread, one at a time, so the stream's event
loop never waits on it.

Who may (the Settings page's pattern, routes_settings.py):
  * GET: the PUBLIC listener only, a LAN viewer, an allowlisted Origin (`browser_gate`);
  * POST: the same, plus the CSRF token of GET /settings/csrf in X-CSRF-Token and at most 20
    requests a minute per client;
  * never the agent's :8001 (refused: `not_public_listener`), and the agent network never reaches
    :8000 (AgentNetworkGuard, ADR-0005 c2).
Refusals are counted in /health (`dropped_messages.flows_http`).

The flow engine (poring_flow, poring_skills) is imported lazily: a backend without it still
starts, and these routes answer 503 `flow_engine_unavailable`.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, ValidationError

from poring_backend.flows_settings import runtime_limits
from poring_backend.routes_public import get_state
from poring_backend.routes_settings import _browser_refusal, csrf_valid
from poring_backend.state import AppState

router = APIRouter(prefix="/flows")

MAX_IR_BYTES = 1 << 20  # MW1's cap (ir.MAX_JSON_BYTES); the envelope adds the scenario
MAX_BODY = MAX_IR_BYTES + 64 * 1024
LOCK_WAIT_S = 5.0
MAP_ID = re.compile(r"^[A-Za-z0-9_@.\-]{1,40}$")
KEY = re.compile(r"^[A-Za-z0-9_.\-]{1,64}$")
World = Literal["local", "sample"]


def _fail(request: Request, status: int, reason: str, **extra: Any) -> HTTPException:
    get_state(request).drops.record("flows_http", reason, request.method.lower())
    return HTTPException(status, {"reason": reason, **extra})


def read_gate(request: Request) -> AppState:
    refusal = _browser_refusal(request)
    if refusal is not None:
        raise _fail(request, *refusal)
    return get_state(request)


def compute_gate(request: Request) -> AppState:
    state = read_gate(request)
    if not csrf_valid(state, request.headers.get("x-csrf-token", "")):
        raise _fail(request, 403, "csrf_invalid")
    client = request.client.host if request.client else ""
    if not state.flows_rate.allow(client, time.monotonic()):
        raise _fail(request, 429, "rate_limited")
    return state


def _engine(request: Request) -> Any:
    try:
        from poring_flow import editor, ir, trace  # noqa: F401  (lazy: see the module docstring)
    except ImportError:
        raise _fail(request, 503, "flow_engine_unavailable") from None
    import poring_flow

    return poring_flow


# --- bodies -----------------------------------------------------------------------------------
class Envelope(BaseModel):
    model_config = ConfigDict(extra="forbid")
    flow: dict[str, Any]
    world: World = "local"
    scenario: dict[str, Any] | None = None


async def _body(request: Request) -> Envelope:
    length = request.headers.get("content-length")
    if length is not None and (not length.isdigit() or int(length) > MAX_BODY):
        raise _fail(request, 413, "too_large")
    chunks: list[bytes] = []
    size = 0
    async for chunk in request.stream():  # capped while reading (a chunked body has no length)
        size += len(chunk)
        if size > MAX_BODY:
            raise _fail(request, 413, "too_large")
        chunks.append(chunk)
    raw = b"".join(chunks)
    from poring_flow import ir

    if ir._depth(raw.decode("utf-8", errors="replace")) > ir.MAX_JSON_DEPTH + 2:
        raise _fail(request, 422, "too_deep")
    try:
        return Envelope.model_validate_json(raw)
    except ValidationError as e:
        raise _fail(request, 422, "invalid_body", errors=_errors(e)) from None


def _errors(e: ValidationError) -> list[str]:
    """Locations and messages only, never the offending input."""
    out = []
    for err in e.errors(include_url=False, include_context=False, include_input=False)[:20]:
        loc = ".".join(str(p) for p in err["loc"])
        out.append(f"{loc}: {err['msg']}" if loc else str(err["msg"]))
    return out


def _flow(request: Request, env: Envelope) -> Any:
    """The IR through MW1's hostile-input path: size, depth, NFC, the schema."""
    from poring_flow import ir

    text = json.dumps(env.flow, ensure_ascii=False, separators=(",", ":"))
    try:
        return ir.from_json(text)
    except ir.FlowError as e:
        raise _fail(request, 422, "invalid_flow", errors=e.messages[:50]) from None


def _world(state: AppState, flow: Any, source: World) -> tuple[Any, list[str]]:
    """The static data: the committed synthetic sample's sheets, or the LOCAL KB (data/kb: a
    generated sheet file, else a sheet built in memory from the extracted L3 data; kbsheet.py)."""
    from poring_flow import editor
    from poring_flow.kbsheet import load_local_world

    maps = editor.maps_of(flow)
    if source == "sample":
        return editor.sample_world(maps), []
    world, labels = load_local_world(flow.target.server, maps, _kb_root(state), _gat_dir())
    return world, labels.notes


def _kb_root(state: AppState) -> Path:
    return Path(state.settings.data_dir) / "kb"


def _gat_dir() -> Path | None:
    """The map GATs, read-only (Batt 2026-10-09: simulate on real routes). compose.dev.yaml mounts
    the local copy `data/gat` (scripts/flows_gat.py; client-derived, never committed) at /lab-gat
    and sets PORING_GAT_DIR. Unset: the bindings' own directory, which the container cannot read,
    so routes are estimates (kbsheet's note says so)."""
    gd = os.environ.get("PORING_GAT_DIR")
    return Path(gd) if gd else None


def _resolver(state: AppState, flow: Any) -> Any:
    from poring_flow.lint import default_resolver

    return default_resolver(flow.target, l3_root=Path(state.settings.data_dir) / "kb" / "bindings")


async def _compute(request: Request, state: AppState, fn: Callable[[], Any]) -> Any:
    """One computation at a time, in a worker thread (the stream's event loop never waits)."""
    try:
        await asyncio.wait_for(state.flows_lock.acquire(), LOCK_WAIT_S)
    except TimeoutError:
        raise _fail(request, 503, "busy") from None
    try:
        return await asyncio.to_thread(fn)
    finally:
        state.flows_lock.release()


# --- GET ----------------------------------------------------------------------------------------
@router.get("/catalogue")
async def get_catalogue(
    request: Request,
    client: str | None = Query(default=None, max_length=64),
    state: AppState = Depends(read_gate),
) -> dict[str, Any]:
    _engine(request)
    if client is not None and not KEY.match(client):
        raise _fail(request, 422, "invalid_client")
    from poring_flow import editor

    default_s, max_s = runtime_limits(state)
    doc = dict(await _compute(request, state, lambda: editor.catalogue_doc(client=client)))
    # #17: the configured run-time limits (a new flow's default; the most a flow may set)
    return {**doc, "runtime_limits": {"default_s": default_s, "max_s": max_s}}


@router.get("/sample")
async def get_sample(request: Request, state: AppState = Depends(read_gate)) -> dict[str, Any]:
    _engine(request)
    from poring_flow import editor, ir

    def build() -> dict[str, Any]:
        flow = editor.sample_flow()
        return {
            "flow": json.loads(ir.to_json(flow)),
            "flow_hash": ir.flow_hash(flow),
            "world": "sample",
        }

    return dict(await _compute(request, state, build))


@router.get("/world")
async def get_world(
    request: Request,
    source: World = "local",
    server: str = Query(default="lab-rathena", max_length=64),
    maps: str = Query(default="", max_length=1000),
    walk: bool = False,
    state: AppState = Depends(read_gate),
) -> dict[str, Any]:
    _engine(request)
    if not state.flows_read_rate.allow(
        request.client.host if request.client else "", time.monotonic()
    ):
        raise _fail(request, 429, "rate_limited")
    names = [m for m in maps.split(",") if m]
    if not KEY.match(server) or len(names) > 20 or not all(MAP_ID.match(m) for m in names):
        raise _fail(request, 422, "invalid_query")
    from poring_flow import editor
    from poring_flow.kbsheet import Labels, load_local_world

    def build() -> dict[str, Any]:
        if source == "sample":
            world, labels = editor.sample_world(names or None), Labels()
        else:
            world, labels = load_local_world(server, names, _kb_root(state), _gat_dir())
        doc = editor.world_doc(world)
        # display text for the keys (local data, never stored in a flow)
        doc["labels"] = {"npcs": labels.npcs, "options": labels.options}
        doc["notes"] = labels.notes
        if walk:
            doc["walk"] = {
                m: rows
                for m in doc["maps"]
                if (rows := editor.walk_rows(world, m)) is not None
                and len(rows) * len(rows[0]) <= 512 * 512
            }
        return doc

    return dict(await _compute(request, state, build))


# --- POST: compute ------------------------------------------------------------------------------
@router.post("/lint")
async def post_lint(request: Request, state: AppState = Depends(compute_gate)) -> dict[str, Any]:
    _engine(request)
    env = await _body(request)
    flow = _flow(request, env)
    from poring_flow import editor

    _, max_s = runtime_limits(state)

    def run() -> dict[str, Any]:
        world, notes = _world(state, flow, env.world)
        doc = editor.lint_doc(
            flow, world=world, resolver=_resolver(state, flow), runtime_max_s=max_s
        )
        return {**doc, "world_notes": notes}

    return dict(await _compute(request, state, run))


@router.post("/simulate")
async def post_simulate(
    request: Request, state: AppState = Depends(compute_gate)
) -> dict[str, Any]:
    _engine(request)
    env = await _body(request)
    flow = _flow(request, env)
    from poring_flow import editor, ir, trace

    try:
        scenario = trace.Scenario.model_validate(env.scenario or {})
    except ValidationError as e:
        raise _fail(request, 422, "invalid_scenario", errors=_errors(e)) from None

    _, max_s = runtime_limits(state)

    def run() -> dict[str, Any]:
        world, notes = _world(state, flow, env.world)
        lint = {**editor.lint_doc(flow, world=world, resolver=_resolver(state, flow),
                                  runtime_max_s=max_s),
                "world_notes": notes}  # fmt: skip
        result = trace.simulate(flow, world, scenario)
        return {"flow_hash": ir.flow_hash(flow), "trace": result, "lint": lint}

    try:
        return dict(await _compute(request, state, run))
    except ValueError as e:  # a start block / entry the flow does not have
        raise _fail(request, 422, "invalid_scenario", errors=[str(e)[:200]]) from None


@router.post("/python")
async def post_python(request: Request, state: AppState = Depends(compute_gate)) -> dict[str, Any]:
    _engine(request)
    env = await _body(request)
    flow = _flow(request, env)
    from poring_flow import editor

    return dict(await _compute(request, state, lambda: editor.python_doc(flow)))
