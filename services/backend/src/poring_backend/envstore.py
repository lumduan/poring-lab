"""The USER-MANAGED environment set (Batt, 2026-10-06, Settings feedback #2; ADR-0016).

Official servers open and close over time, so environments are not fixed in the repository: people
create, rename and delete them, and edit their server lists, on the console's Settings page.

Every environment has ONE type:
  * ``allowed``   -- the bot may act while the client is connected to one of its servers (an
                     allowed environment WITHOUT servers is never green: ``no_servers``);
  * ``forbidden`` -- the bot never acts; its endpoints ("host", "host:port", ".domain") can never
                     be added to any allowed environment;
  * ``pending``   -- not approved; the summary says what is missing.

Defaults and the store:
  * ``config/environments.yaml`` (shipped, read-only) is only a STARTING SET. At the first start
    with an empty settings store it is copied ONCE into ``environments.json`` (audited as ``seed``,
    marker ``.environments-seeded``). Allowed environments are seeded WITHOUT servers: their shipped
    servers are offered as suggestions ("Found by the lab") for a person to confirm. Forbidden
    endpoints are seeded as they are (tightening needs no confirmation).
  * From then on the store is the ONLY source. Missing (after the seed) or invalid => the
    interlock fails closed.
  * Export/import: the whole set as one JSON file (sharing a setup, e.g. the course). An import is
    one change like any other, under the same asymmetric rules, and never carries the technical
    fields (accounts, Windows host, signals, client profile): those stay from the current set.

Asymmetric rules (``classify``):
  * easy (tightening): create a forbidden environment, add to a forbidden one, delete or shrink an
    allowed one, change anything to forbidden, allowed -> pending;
  * normal (a person confirms from their own browser, the write gate): create or extend an allowed
    environment, pending -> allowed, rename, summaries, pending changes;
  * hard (loosening a forbidden list): delete a forbidden environment, remove a forbidden endpoint,
    forbidden -> allowed/pending -- a typed reason (>= 10 characters) AND the subject typed again,
    one hard change per save. All of it is audited.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from poring_backend import allowlist
from poring_backend.interlock import ClientProfile, Environment, EnvironmentsConfig

STORE_NAME = "environments.json"
MARKER_NAME = ".environments-seeded"
MAX_ENVS = 50
MAX_SERVERS = 64
MIN_REASON = 10
EnvType = Literal["allowed", "forbidden", "pending"]
ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,39}$")


class ServerEntry(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    host: str = Field(min_length=1, max_length=253)  # a name, an IPv4 address, or ".domain"
    port: int | None = Field(default=None, ge=1, le=65535)  # None: every port (forbidden only)
    note: str = Field(default="", max_length=300)
    # "file": found by the Settings page's game-file finder (parsed in the browser), then picked
    source: Literal["default", "manual", "discovered", "import", "file"] = "manual"
    added_at: str = ""
    added_by: str = ""

    @property
    def key(self) -> str:
        return allowlist.entry_key(self.host, self.port)


class EnvEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(pattern=ID_RE.pattern)  # stable; the sniffer names its server by it
    name: str = Field(min_length=1, max_length=80)
    type: EnvType
    summary: str = Field(default="", max_length=400)  # ONE sentence, plain words
    why: str = Field(default="", max_length=300)  # the reference (ADR) behind it: a "why?" link
    servers: list[ServerEntry] = Field(default_factory=list, max_length=MAX_SERVERS)
    # Technical, from the shipped defaults only (never from the page or an import):
    windows_host: str | None = None
    accounts: list[int] = Field(default_factory=list)
    signals: list[Literal["lab_host", "session"]] = Field(default_factory=list)
    client: ClientProfile | None = None


class EnvSet(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: Literal[1] = 1
    revision: int = Field(default=0, ge=0)
    seeded_from: str = ""  # sha256 of the defaults file it started from
    attestation_max_age_s: float = Field(default=10, gt=0, le=60)
    window_max_s: float = Field(default=120, gt=0, le=120)
    environments: list[EnvEntry] = Field(default_factory=list, max_length=MAX_ENVS)


TECHNICAL = ("windows_host", "accounts", "signals", "client")


# --- the defaults ---------------------------------------------------------------------------------


def from_defaults(cfg: EnvironmentsConfig, sha: str) -> EnvSet:
    """The shipped starting set. Allowed environments get NO servers (they are suggestions)."""
    envs = []
    for env in cfg.environments:
        servers: list[ServerEntry] = []
        if env.status == "forbidden":
            if env.server is not None:
                servers.append(ServerEntry(host=env.server.host.lower(), port=None,
                                           source="default"))  # fmt: skip
            for raw in env.forbidden_endpoints:
                parsed = allowlist.parse_forbidden(raw)
                if parsed is not None:
                    servers.append(ServerEntry(host=parsed[0], port=parsed[1], source="default"))
        envs.append(EnvEntry(
            id=env.id, name=env.title or env.id, type=env.status, summary=env.summary or "",
            why=env.adr, servers=servers, windows_host=env.windows_host, accounts=env.accounts,
            signals=env.signals, client=env.client,
        ))  # fmt: skip
    return EnvSet(seeded_from=sha, attestation_max_age_s=cfg.attestation_max_age_s,
                  window_max_s=cfg.window_max_s, environments=envs)  # fmt: skip


def suggestions(
    defaults: EnvironmentsConfig | None, current: EnvSet
) -> dict[str, list[ServerEntry]]:
    """Per allowed environment: the shipped servers not yet in its list ("Found by the lab")."""
    out: dict[str, list[ServerEntry]] = {}
    shipped = {e.id: e for e in defaults.environments} if defaults else {}
    blocked = forbidden(current, {})
    for env in current.environments:
        d = shipped.get(env.id)
        if env.type != "allowed" or d is None or d.server is None:
            continue
        have = {s.key for s in env.servers}
        host = allowlist.normalise_host(d.server.host)
        out[env.id] = [ServerEntry(host=host, port=p, source="default") for p in d.server.ports
                       if f"{host}:{p}" not in have and not blocked.hit(host, p)]  # fmt: skip
    return out


# --- the store ------------------------------------------------------------------------------------


def load(directory: Path) -> EnvSet:
    return EnvSet.model_validate_json((directory / STORE_NAME).read_text())


def save(directory: Path, es: EnvSet) -> EnvSet:
    """Atomic write (temp + rename), then read back; raises OSError on a mismatch."""
    tmp = directory / f".{STORE_NAME}.tmp"
    tmp.write_text(es.model_dump_json(indent=1) + "\n")
    os.replace(tmp, directory / STORE_NAME)
    back = load(directory)
    if back != es:
        raise OSError("environment set read-back differs from what was written")
    return back


def file_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def state_of(directory: Path) -> Literal["ok", "unseeded", "missing", "invalid", "no_dir"]:
    if not directory.is_dir():
        return "no_dir"
    store = directory / STORE_NAME
    if not store.exists():
        return "missing" if (directory / MARKER_NAME).exists() else "unseeded"
    try:
        load(directory)
    except (OSError, ValueError):
        return "invalid"
    return "ok"


def seed(directory: Path, defaults: EnvironmentsConfig, sha: str) -> EnvSet:
    """The ONE automatic write: the shipped starting set, into an empty store, with its marker."""
    es = save(directory, from_defaults(defaults, sha))
    (directory / MARKER_NAME).write_text(json.dumps({"seeded_from": sha}) + "\n")
    return es


# --- what the interlock and the matching use ------------------------------------------------------


def blocked_of(es: EnvSet) -> list[allowlist.Blocked]:
    out = []
    for env in es.environments:
        if env.type != "forbidden":
            continue
        for s in env.servers:
            source: Literal["lab_config", "added"] = (
                "lab_config" if s.source == "default" else "added"
            )
            out.append(allowlist.Blocked(env.id, s.host, s.port, source, (), s.note, s.added_at,
                                         s.added_by))  # fmt: skip
    return out


def forbidden(es: EnvSet, resolved: dict[str, list[str]]) -> allowlist.Forbidden:
    return allowlist.forbidden_from(blocked_of(es), resolved)


def usable(env: EnvEntry, blocked: allowlist.Forbidden) -> list[str]:
    """An allowed environment's servers that do NOT match the forbidden list (tightening wins)."""
    out = []
    for s in env.servers:
        if env.type != "allowed" or s.port is None or not blocked.hit(s.host, s.port):
            out.append(s.key)
    return out


def to_config(es: EnvSet) -> EnvironmentsConfig:
    """The interlock's view: type -> status, the servers as "host:port" strings (an allowed server
    that now matches the forbidden list is left out: an environment with none is red)."""
    blocked = forbidden(es, {})
    return EnvironmentsConfig(
        version=1, attestation_max_age_s=es.attestation_max_age_s, window_max_s=es.window_max_s,
        environments=[Environment(
            id=env.id, status=env.type, adr=env.why or "-", title=env.name, summary=env.summary,
            windows_host=env.windows_host, accounts=env.accounts, signals=env.signals,
            client=env.client, servers=usable(env, blocked),
            forbidden_endpoints=[s.key for s in env.servers] if env.type == "forbidden" else [],
        ) for env in es.environments],
    )  # fmt: skip


# --- validation and the asymmetric rules ----------------------------------------------------------


@dataclass(frozen=True)
class Change:
    kind: Literal["easy", "normal", "hard"]
    action: str  # env_create/_delete/_rename/_type/_text, server_add/_remove (AuditRecord.action)
    env_id: str
    subject: str  # what a hard change must be confirmed with (the endpoint, or the env's name)
    text: str  # plain words for the audit log and the page


def classify(old: EnvSet, new: EnvSet) -> list[Change]:
    out: list[Change] = []
    before = {e.id: e for e in old.environments}
    after = {e.id: e for e in new.environments}
    for env_id, e in before.items():
        if env_id not in after:
            kind: Literal["easy", "normal", "hard"] = (
                "hard" if e.type == "forbidden" else "easy" if e.type == "allowed" else "normal"
            )
            out.append(Change(kind, "env_delete", env_id, e.name,
                              f"deleted the {e.type} environment {e.name!r}"))  # fmt: skip
    for env_id, n in after.items():
        o = before.get(env_id)
        if o is None:
            kind = "easy" if n.type == "forbidden" else "normal"
            out.append(Change(kind, "env_create", env_id, n.name,
                              f"created the {n.type} environment {n.name!r}"))  # fmt: skip
            for s in n.servers:
                out.append(Change("easy" if n.type == "forbidden" else "normal", "server_add",
                                  env_id, s.key, f"added {s.key} to {n.name!r}"))  # fmt: skip
            continue
        if n.name != o.name:
            out.append(Change("normal", "env_rename", env_id, n.name,
                              f"renamed {o.name!r} to {n.name!r}"))  # fmt: skip
        if (n.summary, n.why) != (o.summary, o.why):
            out.append(Change("normal", "env_text", env_id, n.name,
                              f"edited the description of {n.name!r}"))  # fmt: skip
        if n.type != o.type:
            if n.type == "forbidden" or (o.type, n.type) == ("allowed", "pending"):
                kind = "easy"
            elif o.type == "forbidden":
                kind = "hard"
            else:
                kind = "normal"
            out.append(Change(kind, "env_type", env_id, n.name,
                              f"changed {n.name!r} from {o.type} to {n.type}"))  # fmt: skip
        old_keys = {s.key for s in o.servers}
        new_keys = {s.key for s in n.servers}
        for key in sorted(new_keys - old_keys):
            kind = "easy" if n.type == "forbidden" else "normal"
            out.append(Change(kind, "server_add", env_id, key, f"added {key} to {n.name!r}"))
        for key in sorted(old_keys - new_keys):
            # judged by the type the list HAD: emptying a forbidden list is loosening it
            kind = "hard" if o.type == "forbidden" else "easy" if o.type == "allowed" else "normal"
            out.append(Change(kind, "server_remove", env_id, key,
                              f"removed {key} from {n.name!r}"))  # fmt: skip
    return out


def validate(new: EnvSet, resolved: dict[str, list[str]],
             old: EnvSet | None = None) -> tuple[str, str] | None:  # fmt: skip
    """(reason, subject) of the first problem in ``new``; None when the set is valid. Only allowed
    servers NEW in this save are refused for matching the forbidden list: tightening a forbidden
    list stays easy even when an allowed server already matches (that one is flagged and ignored,
    ``to_config``)."""
    ids, names = set(), set()
    for env in new.environments:
        if env.id in ids:
            return "duplicate_environment", env.id
        if env.name.strip().lower() in names:
            return "duplicate_name", env.name
        ids.add(env.id)
        names.add(env.name.strip().lower())
        keys = set()
        for s in env.servers:
            if s.key in keys:
                return "duplicate", s.key
            keys.add(s.key)
            if env.type in ("forbidden", "pending"):  # pending lists are informational
                if allowlist.parse_forbidden(s.key) != (s.host, s.port):
                    return "bad_forbidden_entry" if env.type == "forbidden" else "bad_host", s.key
                continue
            if s.host.startswith("."):
                return "domain_not_allowed_here", s.key
            why = allowlist.host_refusal(s.host)
            if why is not None:
                return why, s.key
            if env.type == "allowed" and s.port is None:
                return "port_required", s.key
    blocked = forbidden(new, resolved)
    before = {e.id: {s.key for s in e.servers if e.type == "allowed"}
              for e in (old.environments if old else [])}  # fmt: skip
    for env in new.environments:
        if env.type != "allowed":
            continue
        for s in env.servers:
            if s.key in before.get(env.id, set()):
                continue  # already allowed: flagged and ignored if it is now forbidden
            if s.port is not None and blocked.hit(s.host, s.port, resolved.get(s.host, [])):
                return "forbidden_endpoint", s.key
    return None


def new_id(name: str, taken: set[str]) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:32] or "env"
    if not base[0].isalnum():
        base = f"env-{base}"
    cand, n = base, 2
    while cand in taken:
        cand, n = f"{base}-{n}", n + 1
    return cand
