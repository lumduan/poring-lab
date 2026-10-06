"""The SERVER ALLOWLIST (zero-config, Batt 2026-10-06; ADR-0016): the servers (host:port) each
environment's game client may talk to. It decides when the interlock's client-side provider can
turn green, so WRITES ARE HUMAN-ONLY.

How the rule is enforced:
  * the store lives in its own directory, mounted read-write into the BACKEND ONLY
    (compose.yaml ``./settings:/lab-settings``; test_guards pins it). vision, which can write
    ``./data``, never sees it;
  * the one writer is routes_settings' PUT, which serves only a LAN browser on the public listener
    with an allowlisted Origin. The agent's :8001 gets a read-only GET; every refused write is
    counted and written to the audit log.

Files under the settings directory:
  * ``allowlist.json``: ``{version, revision, environments: {env_id: [entry, ...]}}``. It is
    written atomically (temp + rename) and read back before a save is reported.
  * ``allowlist_audit/YYYY-MM-DD.jsonl`` (UTC day): one line per add, remove or refused attempt,
    with who (peer, Origin, listener), the revisions and the list before and after.

Entries: an IPv4 address or a DNS name, plus a port. No wildcards, no unspecified, loopback,
link-local or multicast address, and nothing on the known-forbidden list (environments.yaml:
each forbidden environment's ``server.host`` and ``forbidden_endpoints``; a leading "." there
forbids a whole domain). Forbidden names are matched as names and NEVER resolved: their IPs are
shared CDN addresses, and "never connect, never test against" covers DNS too.
"""

from __future__ import annotations

import ipaddress
import json
import os
import re
import time
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from poring_backend.input_log import DailyJsonl, wall_clock_iso
from poring_backend.interlock import EnvironmentsConfig

STORE_NAME = "allowlist.json"
AUDIT_DIR = "allowlist_audit"
MAX_ENTRIES = 32
_LABEL = r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?"
DNS_NAME = re.compile(rf"^(?=.{{1,253}}$){_LABEL}(?:\.{_LABEL})*$")


class Entry(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    host: str = Field(min_length=1, max_length=253)
    port: int = Field(ge=1, le=65535)
    source: Literal["manual", "discovered"] = "manual"
    added_at: str = ""
    added_by: str = ""

    @property
    def key(self) -> str:
        return f"{self.host}:{self.port}"


class Store(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: Literal[1] = 1
    revision: int = Field(default=0, ge=0)
    environments: dict[str, list[Entry]] = Field(default_factory=dict)


class AuditRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    t_wall: str
    action: Literal["add", "remove", "refused"]
    env_id: str | None
    entry: str | None  # "host:port"
    revision_before: int | None
    revision_after: int | None
    before: list[str] | None
    after: list[str] | None
    ok: bool
    reason: str
    client: str | None  # the browser's peer address
    origin: str | None
    listener: int | None  # the port the request arrived on


@dataclass(frozen=True)
class Forbidden:
    """The known-forbidden endpoints, as names (never resolved) and literal IPs."""

    hosts: frozenset[tuple[str, int | None]]  # (name or IP, port or any)
    domains: frozenset[str]  # ".ragnarok.co.kr": the domain and every name under it

    def hit(self, host: str, port: int, resolved: Iterable[str] = ()) -> bool:
        names = {host, *resolved}
        for name in names:
            if (name, None) in self.hosts or (name, port) in self.hosts:
                return True
        return any(host == d[1:] or host.endswith(d) for d in self.domains)


def forbidden_of(cfg: EnvironmentsConfig | None) -> Forbidden:
    hosts: set[tuple[str, int | None]] = set()
    domains: set[str] = set()
    for env in cfg.environments if cfg is not None else ():
        if env.status != "forbidden":
            continue
        if env.server is not None:
            hosts.add((env.server.host.lower(), None))
        for raw in env.forbidden_endpoints:
            item = raw.strip().lower()
            if item.startswith("."):
                domains.add(item)
                continue
            host, _, port = item.rpartition(":") if ":" in item else (item, "", "")
            hosts.add((host, int(port) if port else None))
    return Forbidden(frozenset(hosts), frozenset(domains))


def normalise_host(raw: str) -> str:
    return raw.strip().lower().rstrip(".")


def host_refusal(host: str) -> str | None:
    """Why ``host`` (already normalised) can never be an allowed server; None when it can."""
    if not host:
        return "empty_host"
    if "*" in host or "?" in host:
        return "wildcard"
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        ip = None
    if ip is not None:
        if ip.version != 4:
            return "ipv6_not_supported"
        if ip.is_unspecified:
            return "unspecified_address"
        if ip.is_loopback:
            return "loopback"
        if ip.is_link_local:
            return "link_local"
        if ip.is_multicast or ip.is_reserved:
            return "not_unicast"
        return None
    if host == "localhost" or host.endswith(".localhost"):
        return "loopback"
    if not DNS_NAME.match(host) or host.replace(".", "").isdigit():
        return "bad_host"
    return None


def validate(host: str, port: int, forbidden: Forbidden) -> tuple[str, str | None]:
    """(normalised host, refusal reason or None)."""
    norm = normalise_host(host)
    why = host_refusal(norm)
    if why is None and not 1 <= port <= 65535:
        why = "bad_port"
    if why is None and forbidden.hit(norm, port):
        why = "forbidden_endpoint"
    return norm, why


def load(directory: Path) -> Store:
    """The stored allowlist; an absent file is an empty store (revision 0). A corrupt file raises:
    the caller refuses writes rather than overwrite what a human saved."""
    path = directory / STORE_NAME
    if not path.exists():
        return Store()
    return Store.model_validate_json(path.read_text())


def save(directory: Path, store: Store) -> Store:
    """Atomic write (temp + rename), then read back; raises if the file does not hold ``store``."""
    directory.mkdir(parents=True, exist_ok=True)
    tmp = directory / f".{STORE_NAME}.tmp"
    tmp.write_text(store.model_dump_json(indent=1) + "\n")
    os.replace(tmp, directory / STORE_NAME)
    back = load(directory)
    if back != store:
        raise OSError("allowlist read-back differs from what was written")
    return back


def keys(entries: Iterable[Entry]) -> list[str]:
    return [e.key for e in entries]


class AuditLog(DailyJsonl):
    def __init__(self, settings_dir: Path) -> None:
        super().__init__(settings_dir / AUDIT_DIR)

    def write(self, **fields: object) -> AuditRecord:
        """One record; raises OSError when the settings mount is missing (never creates it: a
        directory made here would be on the container's own disk, not the human-only store)."""
        record = AuditRecord(t_wall=wall_clock_iso(), **fields)  # type: ignore[arg-type]
        if not self.directory.parent.is_dir():
            raise OSError(f"settings store {self.directory.parent} is missing")
        self.append(record.t_wall[:10], record.model_dump_json())
        return record

    def tail(self, days: int, limit: int = 500) -> list[dict[str, object]]:
        """The newest records of the last ``days`` UTC days, newest first."""
        out: list[dict[str, object]] = []
        now = time.time()
        for back in range(max(1, days)):
            day = time.strftime("%Y-%m-%d", time.gmtime(now - back * 86400))
            path = self.directory / f"{day}.jsonl"
            if not path.exists():
                continue
            for line in reversed(path.read_text().splitlines()):
                try:
                    out.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
                if len(out) >= limit:
                    return out
        return out
