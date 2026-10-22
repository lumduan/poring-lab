"""The MW2 flow editor's engine: COMPUTATION ONLY (docs/planning/mw2-block-editor.md section 5).

    GET  /flows/catalogue[?client=<L2 build>]   blocks, sensors, verification badges, windows
    GET  /flows/world?source=&server=&maps=      the pickers' static data (map sheets, labels)
    GET  /flows/sample                           the committed SYNTHETIC sample flow (IR JSON)
    POST /flows/lint      {flow, world}          MW1's linter (layers 1-3), findings by node
    POST /flows/simulate  {flow, world, scenario}  the trace (poring_flow.trace): no game
    POST /flows/python    {flow}                 MW1's canonical Python view (read-only)
    GET  /flows/zones/file?map=&source=&server=  config/map_zones/<map>.yaml for the editor to start
                                                 from (its items, comment, the loader's verdict)
    POST /flows/zones/check {map, yaml, world, server}  the RUNNER'S loader on the editor's YAML
                                                 text: its error, sha256, the cells, the diff

The zones routes (blocks-from-hunt-flow.md section 3, B2; Batt D6 2026-10-21: EXPORT only): the
text is checked and returned, never written; a person commits the file and git is the review
record. The loader is the runner's own (scripts/map_zones.py, via flows_zones): without it they
answer 503 `zones_engine_unavailable`.

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

from poring_backend import flows_zones
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


def _zones_provider(state: AppState, world: Any) -> tuple[Any, list[str]]:
    """The linter's zones provider over config/map_zones (B1's flow_zones, the loader's own
    rasters), bounded by each sheet's walk grid; None + a note when the loader is not here (the
    run-start check then refuses a flow that names zones: fail closed)."""
    eng = flows_zones.engine(state.settings.zones_code_dir)
    if eng is None:
        return None, ["zones: the runner's zones loader is not available here (ZONES_CODE_DIR): "
                      "zones files and references are unchecked"]  # fmt: skip
    shapes = {}
    for m, sheet in world.sheets.items() if world is not None else []:
        if sheet.walk is not None:
            shapes[m] = (sheet.walk.height, sheet.walk.width)
    return flows_zones.provider(eng, state.settings.zones_dir, shapes), []


def _routes_provider(state: AppState, world: Any) -> tuple[Any, list[str]]:
    """The linter's patrol routes provider over config/routes (flow_routes, the runner's own
    loader), bounded by each sheet's walk grid; None + a note when the loader is not here (the
    run-start check then refuses a patrol hunt: fail closed)."""
    eng = flows_zones.engine(state.settings.zones_code_dir)
    shapes = {}
    for m, sheet in world.sheets.items() if world is not None else []:
        if sheet.walk is not None:
            shapes[m] = (sheet.walk.height, sheet.walk.width)
    rp = flows_zones.routes_provider(eng, state.settings.routes_dir, shapes) if eng else None
    if rp is None:
        return None, ["routes: the runner's routes loader is not available here (ZONES_CODE_DIR): "
                      "patrol routes are unchecked"]  # fmt: skip
    return rp, []


def _zones_engine(request: Request, state: AppState) -> flows_zones.Engine:
    eng = flows_zones.engine(state.settings.zones_code_dir)
    if eng is None:
        raise _fail(request, 503, "zones_engine_unavailable")
    return eng


def _walk_rows(state: AppState, source: World, server: str, map_name: str) -> list[str] | None:
    from poring_flow import editor
    from poring_flow.kbsheet import load_local_world

    if source == "sample":
        world = editor.sample_world([map_name])
    else:
        world, _ = load_local_world(server, [map_name], _kb_root(state), _gat_dir())
    rows = editor.walk_rows(world, map_name)
    return rows if rows and len(rows) * len(rows[0]) <= flows_zones.MAX_GRID else None


def _hunt_rules(state: AppState) -> tuple[dict[str, Any] | None, str | None]:
    """The hunt block's rule versions with their badges (poring_flow.hunt_rules) from the
    committed config/flows/hunt index + evidence; None + why when they cannot be read."""
    import yaml  # type: ignore[import-untyped]  # no stubs in the dev env

    from poring_flow.hunt_rules import RulesError, rules_doc

    root = Path(state.settings.flows_config_dir) / "hunt"
    try:
        index = yaml.safe_load((root / "index.yaml").read_text(encoding="utf-8"))
        ev_path = root / "evidence.yaml"
        evidence = (
            yaml.safe_load(ev_path.read_text(encoding="utf-8")) if ev_path.is_file() else None
        )
        return rules_doc(index, evidence), None
    except (OSError, yaml.YAMLError, RulesError, KeyError, TypeError, ValueError) as e:
        return None, f"{type(e).__name__}: {str(e)[:200]}"


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

    def build() -> dict[str, Any]:
        doc = dict(editor.catalogue_doc(client=client))
        # B2: the hunt block's groups, rule versions and badges (config/flows/hunt, committed)
        doc["hunt_rules"], doc["hunt_rules_error"] = _hunt_rules(state)
        return doc

    doc = dict(await _compute(request, state, build))
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
        zp, znotes = _zones_provider(state, world)
        rp, rnotes = _routes_provider(state, world)
        doc = editor.lint_doc(
            flow, world=world, resolver=_resolver(state, flow), runtime_max_s=max_s,
            zones_provider=zp, routes_provider=rp,
        )  # fmt: skip
        return {**doc, "world_notes": notes + znotes + rnotes}

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
        zp, znotes = _zones_provider(state, world)
        rp, rnotes = _routes_provider(state, world)
        lint = {**editor.lint_doc(flow, world=world, resolver=_resolver(state, flow),
                                  runtime_max_s=max_s, zones_provider=zp, routes_provider=rp),
                "world_notes": notes + znotes + rnotes}  # fmt: skip
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


# --- the zones layer (B2; Batt D6: export only) -------------------------------------------------
class ZonesBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    map: str
    yaml: str
    world: World = "local"
    server: str = "lab-rathena"


@router.get("/zones/file")
async def get_zones_file(
    request: Request,
    map: str = Query(max_length=40),
    source: World = "local",
    server: str = Query(default="lab-rathena", max_length=64),
    state: AppState = Depends(read_gate),
) -> dict[str, Any]:
    _engine(request)
    eng = _zones_engine(request, state)
    if not state.flows_read_rate.allow(
        request.client.host if request.client else "", time.monotonic()
    ):
        raise _fail(request, 429, "rate_limited")
    if not MAP_ID.match(map) or not eng.mz.MAP_NAME.fullmatch(map) or not KEY.match(server):
        raise _fail(request, 422, "invalid_query")

    def build() -> dict[str, Any]:
        rows = _walk_rows(state, source, server, map)
        return flows_zones.read_file(eng, Path(state.settings.zones_dir), map, rows)

    return dict(await _compute(request, state, build))


@router.post("/zones/check")
async def post_zones_check(
    request: Request, state: AppState = Depends(compute_gate)
) -> dict[str, Any]:
    _engine(request)
    eng = _zones_engine(request, state)
    length = request.headers.get("content-length")
    if length is not None and (not length.isdigit() or int(length) > MAX_BODY):
        raise _fail(request, 413, "too_large")
    chunks: list[bytes] = []
    size = 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > MAX_BODY:
            raise _fail(request, 413, "too_large")
        chunks.append(chunk)
    try:
        body = ZonesBody.model_validate_json(b"".join(chunks))
    except ValidationError as e:
        raise _fail(request, 422, "invalid_body", errors=_errors(e)) from None
    if len(body.yaml.encode("utf-8", errors="surrogatepass")) > MAX_IR_BYTES:
        raise _fail(request, 413, "too_large")
    if not MAP_ID.match(body.map) or not KEY.match(body.server):
        raise _fail(request, 422, "invalid_query")

    def run() -> dict[str, Any]:
        rows = _walk_rows(state, body.world, body.server, body.map) if eng.mz.MAP_NAME.fullmatch(
            body.map) else None  # fmt: skip
        return flows_zones.check(eng, body.yaml, body.map, rows, Path(state.settings.zones_dir))

    return dict(await _compute(request, state, run))
