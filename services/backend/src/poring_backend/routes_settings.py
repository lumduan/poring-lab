"""The Settings page's server allowlist (zero-config, Batt 2026-10-06; ADR-0016).

    GET /settings/servers              environments, allowed servers, suggestions, revision
    PUT /settings/servers/{env_id}     replace one environment's list {base_revision, entries}
    GET /settings/audit?days=N         who changed what (newest first)

Who may READ: the console browser (public listener, a LAN viewer, an allowlisted Origin), and the
agent on its own listener :8001 (GET /settings/servers only).

Who may WRITE (the human-only rule; the qa/transfer pattern, ADR-0004):
  * the PUBLIC listener (:8000) only -- the agent's :8001 never (refused, counted and audited);
    the agent network is refused on :8000 before any route by AgentNetworkGuard (ADR-0005 c2);
  * a LAN VIEWER (VIEWER_NETWORKS; the compose subnet and its gateway refused: host scripts and
    containers that dial the published port arrive from there);
  * an allowlisted Origin (browsers send it; the agent and scripts do not).

Every refused write is counted in /health (``dropped_messages.settings_http``) AND written to the
audit log with its reason. A save is reported only after the file was read back.
"""

from __future__ import annotations

import asyncio
import logging
import socket
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from poring_backend import allowlist
from poring_backend.input_log import wall_clock_iso
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


class EntryIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    host: str = Field(max_length=253)  # an empty host gets its own reason (allowlist.validate)
    port: int
    source: str = "manual"


class PutBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    base_revision: int = Field(ge=0)
    entries: list[EntryIn] = Field(max_length=allowlist.MAX_ENTRIES)


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
    """HUMAN-ONLY: a console browser on the LAN. Every refusal is audited."""
    refusal = _browser_refusal(request)
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


def view(state: AppState) -> dict[str, Any]:
    """What the Settings page shows; the same for the console and the agent's read."""
    cfg = state.interlock.config
    store, store_error = state.allowlist_store()
    forbidden = allowlist.forbidden_of(cfg)
    envs: list[dict[str, Any]] = []
    for env in cfg.environments if cfg is not None else ():
        entries = store.environments.get(env.id, []) if store is not None else []
        allowed = {e.key for e in entries}
        discovered = []
        if env.status == "allowed" and env.server is not None:
            for port in env.server.ports:
                host = allowlist.normalise_host(env.server.host)
                key = f"{host}:{port}"
                if key not in allowed and allowlist.validate(host, port, forbidden)[1] is None:
                    discovered.append({"host": host, "port": port, "from": "lab_config"})
        envs.append({
            "id": env.id, "status": env.status, "adr": env.adr,
            "editable": env.status == "allowed",
            "entries": [{**e.model_dump(), "resolved": state.allowlist_resolved.get(e.host, [])}
                        for e in entries],
            "discovered": discovered,
        })  # fmt: skip
    return {
        "revision": store.revision if store is not None else None,
        "store": store_error or "ok",
        "config": state.interlock.config_error or "ok",
        "environments": envs,
        "forbidden": sorted(
            [f"{h}:{p}" if p else h for h, p in forbidden.hosts]
            + [f"*{d}" for d in forbidden.domains]
        ),
    }


@router.get("/servers")
def get_servers(state: AppState = Depends(read_gate)) -> dict[str, Any]:
    return view(state)


@router.get("/audit")
def get_audit(days: int = 7, state: AppState = Depends(browser_gate)) -> dict[str, Any]:
    return {"records": state.allowlist_audit.tail(min(max(days, 1), 90))}


@router.put("/servers/{env_id}")
async def put_servers(env_id: str, request: Request,
                      state: AppState = Depends(write_gate)) -> dict[str, Any]:  # fmt: skip
    length = request.headers.get("content-length")
    if length is not None and int(length) > MAX_BODY:
        raise _refuse(request, 413, "too_large", audit=True, env_id=env_id)
    body_raw = await request.body()
    if len(body_raw) > MAX_BODY:
        raise _refuse(request, 413, "too_large", audit=True, env_id=env_id)
    try:
        body = PutBody.model_validate_json(body_raw)
    except ValidationError:
        raise _refuse(request, 422, "invalid", audit=True, env_id=env_id) from None
    cfg = state.interlock.config
    if cfg is None:
        raise _refuse(request, 503, state.interlock.config_error or "config_missing", audit=True,
                      env_id=env_id)  # fmt: skip
    env = next((e for e in cfg.environments if e.id == env_id), None)
    if env is None:
        raise _refuse(request, 404, "unknown_environment", audit=True, env_id=env_id)
    if env.status != "allowed":
        raise _refuse(request, 422, f"environment_{env.status}", audit=True, env_id=env_id)
    who = _who(request)
    forbidden = allowlist.forbidden_of(cfg)
    async with state.allowlist_lock:
        store, store_error = state.allowlist_store()
        if store is None:
            raise _refuse(request, 503, store_error, audit=True, env_id=env_id)
        if body.base_revision != store.revision:
            raise _refuse(request, 409, "stale_revision", audit=True, env_id=env_id,
                          extra={"revision": store.revision})  # fmt: skip
        current = {e.key: e for e in store.environments.get(env_id, [])}
        new: list[allowlist.Entry] = []
        for item in body.entries:
            host, why = allowlist.validate(item.host, item.port, forbidden)
            key = f"{host}:{item.port}"
            if why is None and item.source not in ("manual", "discovered"):
                why = "bad_source"
            if why is None and any(e.key == key for e in new):
                why = "duplicate"
            if why is None and not host.replace(".", "").isdigit():
                ips = await resolve(host)
                if forbidden.hit(host, item.port, ips):
                    why = "forbidden_endpoint"
                state.allowlist_resolved[host] = ips
            if why is not None:
                raise _refuse(request, 422, why, audit=True, env_id=env_id, entry=key,
                              extra={"entry": key})  # fmt: skip
            new.append(current.get(key) or allowlist.Entry(
                host=host, port=item.port, source=item.source,  # type: ignore[arg-type]
                added_at=wall_clock_iso(), added_by=who.client or "",
            ))  # fmt: skip
        before, after = allowlist.keys(current.values()), allowlist.keys(new)
        if before == after:
            return {**view(state), "saved": False, "read_back": True}
        rev_before = store.revision
        store.environments[env_id] = new
        store.revision += 1
        try:
            saved = allowlist.save(state.settings.settings_dir, store)
        except OSError as exc:
            log.error("allowlist write failed: %s", exc)
            raise _refuse(request, 500, "write_failed", audit=True, env_id=env_id) from None
        for action, keys_ in (("add", [k for k in after if k not in before]),
                              ("remove", [k for k in before if k not in after])):  # fmt: skip
            for key in keys_:
                state.allowlist_audit.write(
                    action=action, env_id=env_id, entry=key, revision_before=rev_before,
                    revision_after=saved.revision, before=before, after=after, ok=True,
                    reason="saved", **who.model_dump(),
                )  # fmt: skip
        log.info("allowlist %s: %s -> %s (revision %d, by %s)", env_id, before, after,
                 saved.revision, who.client)  # fmt: skip
    return {**view(state), "saved": True, "read_back": True}
