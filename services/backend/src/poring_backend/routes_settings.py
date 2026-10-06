"""The Settings page: the USER-MANAGED environment set (Batt, 2026-10-06, feedback #2; ADR-0016).

    GET /settings/environments           every environment: type, plain words, servers (current
                                         IPs, CDN warnings), suggestions, revision
    GET /settings/environments/export    the whole set as one file (sharing a setup)
    PUT /settings/environments           the whole new set (from the page or an import):
                                         {base_revision, environments, reason?, confirm?, source}
    GET /settings/audit?days=N           who changed what (newest first)

A PUT is checked (envstore.validate), compared with the stored set and CLASSIFIED
(envstore.classify):
easy (tightening) and normal changes go through on the write gate below; a HARD change (loosening a
forbidden list: deleting a forbidden environment, removing a forbidden endpoint, forbidden ->
allowed/pending) also needs a typed reason (>= 10 characters) and its subject typed again, one hard
change per save. Every change is audited with its rule; the interlock re-reads the set at once.

Who may READ: the console browser (public listener, a LAN viewer, an allowlisted Origin), and the
agent on its own listener :8001 (GET /settings/environments only).

Who may WRITE (the human-only rule; the qa/transfer pattern, ADR-0004, tightened):
  * the PUBLIC listener (:8000) only -- the agent's :8001 never (refused, counted and audited);
    the agent network is refused on :8000 before any route by AgentNetworkGuard (ADR-0005 c2);
  * a LAN VIEWER (VIEWER_NETWORKS; the compose subnet and its gateway refused: host scripts and
    containers that dial the published port arrive from there);
  * an allowlisted Origin (browsers send it; the agent and scripts do not);
  * NOT the lab host itself (HOST_LAN_IP: a host process can forge the Origin -- found live,
    2026-10-06: the host reaches the published port as 192.168.1.13, a LAN viewer) and NOT the
    Windows host (WIN_HOST: the bot drives that desktop, so a Save there could be the bot's).

Every refused write is counted in /health (``dropped_messages.settings_http``) AND written to the
audit log with its reason. A save is reported only after the file was read back.
"""

from __future__ import annotations

import asyncio
import json
import logging
import socket
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from poring_backend import allowlist, envstore
from poring_backend.input_log import wall_clock_iso
from poring_backend.interlock import load_config
from poring_backend.routes_packets import viewer_refusal
from poring_backend.routes_public import get_state
from poring_backend.state import AppState

log = logging.getLogger(__name__)
router = APIRouter(prefix="/settings")

MAX_BODY = 64 * 1024
RESOLVE_TIMEOUT_S = 3.0


class Who(BaseModel):
    client: str | None
    origin: str | None
    listener: int | None


class ServerIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    host: str = Field(max_length=253)  # empty/bad hosts get their own reasons (envstore.validate)
    port: int | None = None
    note: str = Field(default="", max_length=300)
    source: str = "manual"


class EnvIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str | None = Field(default=None, max_length=40)  # None: a new environment
    name: str = Field(min_length=1, max_length=80)
    type: envstore.EnvType
    summary: str = Field(default="", max_length=400)
    why: str = Field(default="", max_length=300)
    servers: list[ServerIn] = Field(default_factory=list, max_length=envstore.MAX_SERVERS)


class PutBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    base_revision: int = Field(ge=0)
    environments: list[EnvIn] = Field(max_length=envstore.MAX_ENVS)
    reason: str = Field(default="", max_length=500)
    confirm: str = Field(default="", max_length=260)
    source: str = "page"  # "page" | "import"


def _who(request: Request) -> Who:
    server = request.scope.get("server")
    return Who(
        client=request.client.host if request.client else None,
        origin=request.headers.get("origin"),
        listener=server[1] if server else None,
    )


def _refuse(request: Request, status: int, reason: str, *, audit: bool,
            env_id: str | None = None, entry: str | None = None,
            extra: dict[str, Any] | None = None) -> HTTPException:  # fmt: skip
    state = get_state(request)
    state.drops.record("settings_http", reason, request.method.lower())
    if audit:
        try:
            state.allowlist_audit.write(
                action="refused", env_id=env_id, entry=entry, revision_before=None,
                revision_after=None, before=None, after=None, ok=False, reason=reason,
                **_who(request).model_dump(),
            )  # fmt: skip
        except OSError as exc:  # the refusal stands; the missing store is its own alarm
            log.error("settings audit not written (%s): %s", reason, exc)
        log.warning("settings write refused: %s (%s)", reason, _who(request).model_dump())
    return HTTPException(status, {"reason": reason, **(extra or {})})


def _browser_refusal(request: Request) -> tuple[int, str] | None:
    """The console-browser gate (routes_qa.qa_dir's checks); None when it passes."""
    settings = get_state(request).settings
    server = request.scope.get("server")
    if not server or server[1] != settings.public_port:
        return 404, "not_public_listener"
    peer = request.client.host if request.client else None
    refusal = viewer_refusal(peer, settings.compose_subnet, settings.viewer_nets)
    if refusal is not None:
        return 403, refusal
    origin = request.headers.get("origin")
    if origin is None:
        return 403, "origin_required"
    if origin.rstrip("/") not in settings.origins:
        return 403, "origin_not_allowed"
    return None


def read_gate(request: Request) -> AppState:
    """The console browser, or the agent on its own listener (read-only)."""
    state = get_state(request)
    server = request.scope.get("server")
    if server and server[1] == state.settings.internal_port:
        return state
    refusal = _browser_refusal(request)
    if refusal is not None:
        raise _refuse(request, refusal[0], refusal[1], audit=False)
    return state


def browser_gate(request: Request) -> AppState:
    refusal = _browser_refusal(request)
    if refusal is not None:
        raise _refuse(request, refusal[0], refusal[1], audit=False)
    return get_state(request)


def write_gate(request: Request) -> AppState:
    """HUMAN-ONLY: a console browser on the LAN, but never on the lab host itself (any process
    there can forge the Origin) nor on the Windows host the bot drives. Every refusal is audited."""
    refusal = _browser_refusal(request)
    if refusal is None:
        settings = get_state(request).settings
        peer = request.client.host if request.client else None
        if peer and peer == settings.host_lan_ip:
            refusal = (403, "lab_host_peer")
        elif peer and peer == settings.win_host:
            refusal = (403, "windows_host_peer")
    if refusal is not None:
        raise _refuse(request, refusal[0], refusal[1], audit=True)
    return get_state(request)


async def resolve(host: str) -> list[str]:
    """IPv4 addresses of a DNS name ([] when it does not resolve in time); an IP is itself."""
    if allowlist.host_refusal(host) is None and host.replace(".", "").isdigit():
        return [host]
    loop = asyncio.get_running_loop()
    try:
        infos = await asyncio.wait_for(
            loop.getaddrinfo(host, None, family=socket.AF_INET, type=socket.SOCK_STREAM),
            RESOLVE_TIMEOUT_S,
        )
    except (OSError, TimeoutError):
        return []
    return sorted({str(info[4][0]) for info in infos})


def _resolved_view(state: AppState, host: str, forbidden: bool) -> list[dict[str, Any]]:
    if host.startswith(".") or host.replace(".", "").isdigit():
        return []
    cache = state.forbidden_resolved if forbidden else state.allowlist_resolved
    return [{"ip": ip, "cdn": allowlist.cdn_of(ip)} for ip in cache.get(host, [])]


def view(state: AppState) -> dict[str, Any]:
    """What the Settings page shows; the same for the console and the agent's read."""
    es, error = state.envset()
    defaults, _ = load_config(state.settings.environments_file)
    suggested = envstore.suggestions(defaults, es) if es is not None else {}
    blocked = state.forbidden()
    envs: list[dict[str, Any]] = []
    for env in es.environments if es is not None else ():
        is_forbidden = env.type == "forbidden"
        envs.append({
            "id": env.id, "name": env.name, "type": env.type, "summary": env.summary,
            "why": env.why,
            "servers": [{
                "host": s.host, "port": s.port, "key": s.key, "note": s.note, "source": s.source,
                "added_at": s.added_at, "added_by": s.added_by,
                "resolved": _resolved_view(state, s.host, is_forbidden),
                # tightening wins: an allowed server now matching the forbidden list is ignored
                "forbidden": env.type == "allowed" and s.port is not None and blocked.hit(
                    s.host, s.port, state.allowlist_resolved.get(s.host, [])),
            } for s in env.servers],
            "suggestions": [{"host": s.host, "port": s.port} for s in suggested.get(env.id, [])],
            # the bot can act here only with servers AND a way to verify a session (signals)
            "ready": env.type == "allowed" and bool(env.servers) and bool(env.signals),
            "signals": list(env.signals),
        })  # fmt: skip
    return {
        "revision": es.revision if es is not None else None,
        "store": error or "ok",
        "seeded_from": es.seeded_from if es is not None else None,
        "config": state.interlock.config_error or "ok",
        "environments": envs,
        "forbidden": sorted(
            [f"{h}:{p}" if p else h for h, p in blocked.hosts] + [f"*{d}" for d in blocked.domains]
        ),
    }


@router.get("/environments")
def get_environments(state: AppState = Depends(read_gate)) -> dict[str, Any]:
    return view(state)


@router.get("/environments/export")
def export_environments(state: AppState = Depends(browser_gate)) -> Response:
    """The whole set as ONE file (no technical fields: accounts, Windows host, signals)."""
    es, error = state.envset()
    if es is None:
        raise HTTPException(503, {"reason": error})
    doc = {
        "format": "poring-lab-environments/1", "exported_at": wall_clock_iso(),
        "revision": es.revision,
        "environments": [{
            "id": e.id, "name": e.name, "type": e.type, "summary": e.summary, "why": e.why,
            "servers": [{"host": s.host, "port": s.port, "note": s.note} for s in e.servers],
        } for e in es.environments],
    }  # fmt: skip
    return Response(
        json.dumps(doc, indent=1) + "\n",
        media_type="application/json",
        headers={"content-disposition": 'attachment; filename="poring-lab-environments.json"'},
    )


@router.get("/audit")
def get_audit(days: int = 7, state: AppState = Depends(browser_gate)) -> dict[str, Any]:
    return {"records": state.allowlist_audit.tail(min(max(days, 1), 90))}


def _build(body: PutBody, current: envstore.EnvSet, who: Who) -> envstore.EnvSet | tuple[str, str]:
    """The new set from the request: stable ids, kept metadata, technical fields from the current
    set only; (reason, subject) for a request that cannot be one."""
    by_id = {e.id: e for e in current.environments}
    used: set[str] = set()
    envs: list[envstore.EnvEntry] = []
    now = wall_clock_iso()
    for e in body.environments:
        base = by_id.get(e.id) if e.id else None
        if base is not None:
            env_id = base.id
        elif e.id and body.source == "import" and envstore.ID_RE.match(e.id) and e.id not in used:
            env_id = e.id  # an imported environment keeps its id (the sniffer may name it)
        else:
            env_id = envstore.new_id(e.name, set(by_id) | used)
        if env_id in used:
            return "duplicate_environment", env_id
        used.add(env_id)
        known = {s.key: s for s in base.servers} if base else {}
        servers = []
        for srv in e.servers:
            host = allowlist.normalise_host(srv.host)
            if srv.port is not None and not 1 <= srv.port <= 65535:
                return "bad_port", f"{host}:{srv.port}"
            key = allowlist.entry_key(host, srv.port)
            prev = known.get(key)
            if prev is not None:
                servers.append(prev.model_copy(update={"note": srv.note.strip()}))
                continue
            if not host:
                return "empty_host", ""
            source: Literal["manual", "discovered", "import"] = (
                "import"
                if body.source == "import"
                else "discovered"
                if srv.source == "discovered"
                else "manual"
            )
            servers.append(envstore.ServerEntry(
                host=host, port=srv.port, note=srv.note.strip(), source=source, added_at=now,
                added_by=who.client or ""))  # fmt: skip
        technical = {k: getattr(base, k) for k in envstore.TECHNICAL} if base else {}
        envs.append(envstore.EnvEntry(id=env_id, name=e.name.strip(), type=e.type,
                                      summary=e.summary.strip(), why=e.why.strip(),
                                      servers=servers, **technical))  # fmt: skip
    return current.model_copy(update={"environments": envs})


@router.put("/environments")
async def put_environments(request: Request,
                           state: AppState = Depends(write_gate)) -> dict[str, Any]:  # fmt: skip
    length = request.headers.get("content-length")
    if length is not None and int(length) > MAX_BODY:
        raise _refuse(request, 413, "too_large", audit=True)
    raw = await request.body()
    if len(raw) > MAX_BODY:
        raise _refuse(request, 413, "too_large", audit=True)
    try:
        body = PutBody.model_validate_json(raw)
    except ValidationError:
        raise _refuse(request, 422, "invalid", audit=True) from None
    if body.source not in ("page", "import"):
        raise _refuse(request, 422, "invalid", audit=True)
    who = _who(request)
    async with state.envset_lock:
        current, error = state.envset()
        if current is None:
            raise _refuse(request, 503, error, audit=True)
        if body.base_revision != current.revision:
            raise _refuse(request, 409, "stale_revision", audit=True,
                          extra={"revision": current.revision})  # fmt: skip
        built = _build(body, current, who)
        if isinstance(built, tuple):
            raise _refuse(request, 422, built[0], audit=True, entry=built[1] or None,
                          extra={"entry": built[1]})  # fmt: skip
        new = built
        # resolve new names first: a name whose (non-CDN) address is forbidden is refused
        for env in new.environments:
            is_forbidden = env.type == "forbidden"
            cache = state.forbidden_resolved if is_forbidden else state.allowlist_resolved
            for srv in env.servers:
                if srv.host.startswith(".") or srv.host.replace(".", "").isdigit():
                    continue
                if srv.host not in cache:
                    cache[srv.host] = await resolve(srv.host)
        resolved = {**state.forbidden_resolved}
        names = resolved | {
            h: ips for h, ips in state.allowlist_resolved.items() if h not in resolved
        }
        problem = envstore.validate(new, names, current)
        if problem is not None:
            raise _refuse(request, 422, problem[0], audit=True, entry=problem[1] or None,
                          extra={"entry": problem[1]})  # fmt: skip
        changes = envstore.classify(current, new)
        if not changes:
            return {**view(state), "saved": False, "read_back": True, "changes": []}
        hard = [c for c in changes if c.kind == "hard"]
        if len(hard) > 1:
            raise _refuse(request, 422, "one_hard_change_at_a_time", audit=True,
                          extra={"subjects": [c.subject for c in hard]})  # fmt: skip
        if hard:
            subject = hard[0].subject
            if len(body.reason.strip()) < envstore.MIN_REASON:
                raise _refuse(request, 422, "reason_required", audit=True, env_id=hard[0].env_id,
                              entry=subject, extra={"subject": subject})  # fmt: skip
            if body.confirm.strip().lower() != subject.lower():
                raise _refuse(request, 422, "confirm_mismatch", audit=True, env_id=hard[0].env_id,
                              entry=subject, extra={"subject": subject})  # fmt: skip
        rev_before = current.revision
        new.revision = current.revision + 1
        try:
            saved = envstore.save(state.settings.settings_dir, new)
        except OSError as exc:
            log.error("environment set write failed: %s", exc)
            raise _refuse(request, 500, "write_failed", audit=True) from None
        names_before = [f"{e.id}:{e.type}:{len(e.servers)}" for e in current.environments]
        names_after = [f"{e.id}:{e.type}:{len(e.servers)}" for e in saved.environments]
        for c in changes:
            state.allowlist_audit.write(
                action=c.action, kind=c.kind, env_id=c.env_id, entry=c.subject,
                revision_before=rev_before, revision_after=saved.revision, before=names_before,
                after=names_after, ok=True, reason=body.source,
                note=body.reason.strip() if c.kind == "hard" else c.text, **who.model_dump(),
            )  # fmt: skip
        log.warning("environment set revision %d by %s (%s): %s", saved.revision, who.client,
                    body.source, "; ".join(f"[{c.kind}] {c.text}" for c in changes))  # fmt: skip
    state.interlock.reload()  # the interlock reads the new set at once
    task = asyncio.create_task(state.resolve_allowlist(), name="envset-resolve")
    await asyncio.wait({task}, timeout=RESOLVE_TIMEOUT_S + 1)
    return {**view(state), "saved": True, "read_back": True,
            "changes": [{"kind": c.kind, "text": c.text} for c in changes]}  # fmt: skip
