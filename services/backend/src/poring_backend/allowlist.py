"""Endpoint rules and the settings audit log (Batt, 2026-10-06; ADR-0016).

The environments themselves -- their types and server lists -- are the USER-MANAGED environment
set (envstore.py), edited on the console's Settings page through the human-only write gate
(routes_settings.py). This module holds what both need:
  * what an endpoint may be: an allowed server is an IPv4 address or a DNS name plus a port (no
    wildcard, unspecified, loopback, link-local or multicast address); a forbidden entry is "host",
    "host:port" or ".domain" (the domain and every name under it);
  * matching against the forbidden list: names, IP literals, and the IPs the forbidden NAMES
    currently resolve to -- unless an IP lies in a CDN range (Cloudflare's published list): such
    addresses are shared, so they are matched by NAME only and shown with a firewall warning
    (Batt, 2026-10-06: re-resolve periodically; this supersedes "forbidden names are never
    resolved");
  * the audit log ``allowlist_audit/YYYY-MM-DD.jsonl`` (UTC day): every change and every refused
    attempt, with who (peer, Origin, listener), the change's rule (easy/normal/hard), the revision
    before and after, and the typed reason of a hard change.
"""

from __future__ import annotations

import ipaddress
import json
import re
import time
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict

from poring_backend.input_log import DailyJsonl, wall_clock_iso

AUDIT_DIR = "allowlist_audit"
MAX_ENTRIES = 32
_LABEL = r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?"
DNS_NAME = re.compile(rf"^(?=.{{1,253}}$){_LABEL}(?:\.{_LABEL})*$")


class AuditRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    t_wall: str
    action: Literal[
        "refused", "seed", "env_create", "env_delete", "env_rename", "env_type", "env_text",
        "server_add", "server_remove", "declare", "withdraw",
    ]  # fmt: skip
    kind: Literal["easy", "normal", "hard", "declare"] | None = None  # the rule that applied
    env_id: str | None
    entry: str | None  # the subject: "host:port", "host", ".domain", or an environment's name
    revision_before: int | None
    revision_after: int | None
    before: list[str] | None
    after: list[str] | None
    ok: bool
    reason: str
    client: str | None  # the browser's peer address
    origin: str | None
    listener: int | None  # the port the request arrived on
    # a hard change: the typed reason; declare / withdraw: the person's statement (ADR-0023);
    # else the change in plain words
    note: str | None = None


# Cloudflare's published IPv4 ranges (https://www.cloudflare.com/ips-v4, unchanged since 2021). A
# forbidden name resolving here shares its address with unrelated sites.
CDN_RANGES: dict[str, tuple[ipaddress.IPv4Network, ...]] = {
    "cloudflare": tuple(ipaddress.IPv4Network(n) for n in (
        "173.245.48.0/20", "103.21.244.0/22", "103.22.200.0/22", "103.31.4.0/22",
        "141.101.64.0/18", "108.162.192.0/18", "190.93.240.0/20", "188.114.96.0/20",
        "197.234.240.0/22", "198.41.128.0/17", "162.158.0.0/15", "104.16.0.0/13",
        "104.24.0.0/14", "172.64.0.0/13", "131.0.72.0/22",
    )),
}  # fmt: skip


def cdn_of(ip: str) -> str | None:
    """The CDN whose shared range holds ``ip`` (None: not a known CDN address)."""
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return None
    for name, nets in CDN_RANGES.items():
        if any(addr in net for net in nets):
            return name
    return None


def parse_forbidden(raw: str) -> tuple[str, int | None] | None:
    """("host" | ".domain", port or None) from "host", "host:port" or ".domain"; None when it is
    not one (wildcards, empty, a bad name or port)."""
    item = raw.strip().lower().rstrip(".")
    if not item or "*" in item or "?" in item or " " in item:
        return None
    if item.startswith("."):
        return (item, None) if DNS_NAME.match(item[1:]) else None
    host, port = item, None
    if ":" in item:
        host, _, port_text = item.rpartition(":")
        if not port_text.isdigit() or not 1 <= int(port_text) <= 65535:
            return None
        port = int(port_text)
    try:
        ipaddress.IPv4Address(host)
    except ValueError:
        if not DNS_NAME.match(host) or host.replace(".", "").isdigit():
            return None
    return host, port


def entry_key(host: str, port: int | None) -> str:
    return host if port is None else f"{host}:{port}"


@dataclass(frozen=True)
class Blocked:
    """One effective forbidden entry, for matching and for the page."""

    env_id: str
    host: str  # a name, an IP, or ".domain"
    port: int | None  # None: every port
    source: Literal["lab_config", "added"]
    ports_known: tuple[int, ...] = ()  # the YAML server block's ports (shown, not matched)
    note: str = ""
    added_at: str = ""
    added_by: str = ""

    @property
    def key(self) -> str:
        return entry_key(self.host, self.port)

    @property
    def is_domain(self) -> bool:
        return self.host.startswith(".")

    @property
    def is_name(self) -> bool:
        return not self.is_domain and not self.host.replace(".", "").isdigit()


@dataclass(frozen=True)
class Forbidden:
    """The effective forbidden list for matching: names, IP literals, the non-CDN IPs the
    forbidden names resolve to, and whole domains."""

    hosts: frozenset[tuple[str, int | None]]  # (name or IP, port or any)
    domains: frozenset[str]  # ".ragnarok.co.kr": the domain and every name under it

    def hit(self, host: str, port: int, resolved: Iterable[str] = ()) -> bool:
        names = {host, *resolved}
        for name in names:
            if (name, None) in self.hosts or (name, port) in self.hosts:
                return True
        return any(host == d[1:] or host.endswith(d) for d in self.domains)


def forbidden_from(blocked: Iterable[Blocked],
                   resolved: dict[str, list[str]] | None = None) -> Forbidden:  # fmt: skip
    hosts: set[tuple[str, int | None]] = set()
    domains: set[str] = set()
    for b in blocked:
        if b.is_domain:
            domains.add(b.host)
            continue
        hosts.add((b.host, b.port))
        if b.is_name:
            for ip in (resolved or {}).get(b.host, []):
                if cdn_of(ip) is None:  # a shared CDN address is matched by NAME only
                    hosts.add((ip, b.port))
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
