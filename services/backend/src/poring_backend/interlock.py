"""The environment interlock (ADR-0016, rewritten 2026-10-04; ADR-0006 rule 2): the mux accepts a
BOT press only while the session is verifiably on an allowed environment. A LOGIC interlock
driven by config/environments.yaml (Batt, 2026-10-04: the lab stays flexible; OS-level locks are
for production/teaching distributions).

Inputs, none of them reachable by the agent:
  * the allowlist (/lab-config/environments.yaml, read-only mount; missing/invalid => fail closed);
  * the capture-backend lock (state/, written only by capture_backend.py);
  * the sniffer's ATTESTATION (/ingest/packets: internal port + rathena's pinned IP only) --
    "a map session from <client_ip> is live, account <aid>, last packet <age> ago", never world
    data;
  * an operator WINDOW (state/interlock-window, written only by capture_backend.py window; <= 120 s,
    tied to the lock's SEQ). It counts in ASSIST only -- never in BOT mode -- for the phases before
    a session exists (login) and desktop work (the agent's own shell).

The verdict is pure (``evaluate``): tests drive it with explicit times. Reasons are short words for
/health, the Status line and the refusal counters.
"""

import logging
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import yaml  # type: ignore[import-untyped]  # no stubs in the dev env
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from poring_env.protocol import CaptureBackend, EnvironmentStatus, Mode
from poring_packets.events import Attestation

log = logging.getLogger(__name__)

SIGNALS = ("lab_host", "session")
_UNSET: Any = object()
WINDOW_KINDS = ("login", "desktop")


class ClientProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")
    exe: str
    shortcut: str
    server_select: str


class Server(BaseModel):
    model_config = ConfigDict(extra="forbid")
    host: str
    ports: list[int]


class Environment(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(pattern=r"^[a-z0-9-]+$")
    status: Literal["allowed", "pending", "forbidden"]
    adr: str
    # Plain words for the Settings page (2026-10-06): a display name, and ONE sentence saying what
    # this environment is -- for a pending one, what is still missing. The ADR stays a "why?" link.
    title: str | None = None
    summary: str | None = None
    server: Server | None = None
    windows_host: str | None = None
    client: ClientProfile | None = None
    accounts: list[int] = Field(default_factory=list)
    signals: list[Literal["lab_host", "session"]] = Field(default_factory=list)
    # Known-forbidden endpoints beyond ``server`` (forbidden environments only): "host",
    # "host:port", or ".domain" for a whole domain. The Settings page refuses every one of them as
    # an allowed server (allowlist.forbidden_of; 2026-10-06).
    forbidden_endpoints: list[str] = Field(default_factory=list)
    # The environment's servers ("host:port"; for a forbidden one also "host" / ".domain"), from
    # the user-managed store (envstore.py, 2026-10-06). An ALLOWED environment without servers is
    # never green: "allowed" means the client is connected to one of its servers.
    servers: list[str] = Field(default_factory=list)
    note: str | None = None


class EnvironmentsConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: Literal[1]
    attestation_max_age_s: float = Field(gt=0, le=60)
    window_max_s: float = Field(gt=0, le=120)
    environments: list[Environment]


def load_config(path: Path) -> tuple[EnvironmentsConfig | None, str]:
    """(config, "") or (None, why) -- a missing or invalid file is a refusal reason, not a crash."""
    try:
        raw = yaml.safe_load(path.read_text())
    except OSError:
        return None, "config_missing"
    except yaml.YAMLError:
        return None, "config_invalid"
    try:
        return EnvironmentsConfig.model_validate(raw), ""
    except ValidationError:
        return None, "config_invalid"


@dataclass(frozen=True)
class Window:
    kind: str
    until: float  # unix seconds
    left_s: float
    reason: str


@dataclass(frozen=True)
class Verdict:
    green: bool  # an allowed environment's signals all hold
    bot_allowed: bool  # what the mux uses (green, or a window in ASSIST)
    reason: str  # "ok", "window:<kind>", or why not
    env_id: str | None
    window: Window | None
    attest_age_s: float | None

    def status(self) -> EnvironmentStatus:
        state: Literal["green", "window", "red"] = (
            "green" if self.green else "window" if self.bot_allowed else "red"
        )
        return EnvironmentStatus(
            state=state, reason=self.reason, env_id=self.env_id,
            window=self.window.kind if self.window else None,  # type: ignore[arg-type]
            window_left_s=round(self.window.left_s, 1) if self.window else None,
            attest_age_s=None if self.attest_age_s is None else round(self.attest_age_s, 1),
        )  # fmt: skip


def _env_signals(
    env: Environment,
    cfg: EnvironmentsConfig,
    lock: CaptureBackend,
    win_host: str,
    attest: Attestation | None,
    attest_age_s: float | None,
) -> str:
    """ "" when every required signal of ``env`` holds, else the first failing reason."""
    if env.status != "allowed":
        return f"env_{env.status}"
    if not env.signals:
        return "no_signals_configured"
    if not env.servers:
        return "no_servers"  # confirm the environment's servers on the Settings page
    if "lab_host" in env.signals:
        if lock.backend not in ("rdp", "console") or lock.phase != "steady":
            return "lock_not_steady"
        if not env.windows_host or win_host != env.windows_host:
            return "host_mismatch"
    if "session" in env.signals:
        if attest is None or attest_age_s is None:
            return "no_attestation"
        if attest_age_s > cfg.attestation_max_age_s:
            return "attestation_stale"
        if attest.client_ip != env.windows_host:
            return "client_ip_mismatch"
        # WHICH server (2026-10-05, Batt): the attesting sniffer names its rathena; a session on
        # another server (or an unnamed one) never makes this environment green.
        if attest.server != env.id:
            return "server_mismatch"
        if not attest.session_live:
            return "no_session"
        if attest.aid not in env.accounts:
            return "account_not_lab"
    return ""


def evaluate(
    cfg: EnvironmentsConfig | None,
    cfg_error: str,
    *,
    mode: Mode,
    lock: CaptureBackend,
    win_host: str,
    attest: Attestation | None,
    attest_age_s: float | None,
    window: Window | None,
) -> Verdict:
    if cfg is None:
        return Verdict(False, False, cfg_error or "config_missing", None, None, attest_age_s)
    reasons = []
    for env in cfg.environments:
        why = _env_signals(env, cfg, lock, win_host, attest, attest_age_s)
        if not why:
            return Verdict(True, True, "ok", env.id, window, attest_age_s)
        reasons.append(why)
    # the most informative refusal: the allowed environments' (a pending one always says so)
    allowed = [r for r in reasons if not r.startswith("env_")]
    reason = allowed[0] if allowed else (reasons[0] if reasons else "no_environment")
    if window is not None and mode is Mode.ASSIST:
        return Verdict(False, True, f"window:{window.kind}", None, window, attest_age_s)
    return Verdict(False, False, reason, None, window, attest_age_s)


# (change key, config or None, error) -- the user-managed store's reader (state.py, envstore.py)
Source = Callable[[], tuple[Any, "EnvironmentsConfig | None", str]]


class Interlock:
    """The backend's live copy: the config (re-read when it changes), the last attestation and
    when it arrived (monotonic). The config comes from ``source`` -- the USER-MANAGED environment
    set (2026-10-06; fail closed when it is missing or invalid) -- or, without one, from ``path``
    (the YAML file; tests)."""

    def __init__(self, path: Path, win_host: str, source: Source | None = None) -> None:
        self.path, self.win_host, self.source = path, win_host, source
        self.attest: Attestation | None = None
        self.attest_at_ns: int | None = None
        self.attestations = 0
        self._mtime: Any = _UNSET
        self.config: EnvironmentsConfig | None = None
        self.config_error = "config_missing"
        self.reload()

    def reload(self) -> None:
        """Re-read the config when it changed (the source's key, or the YAML file's mtime)."""
        if self.source is not None:
            key, cfg, error = self.source()
            if key == self._mtime:
                return
            self._mtime = key
            self.config, self.config_error = cfg, error
        else:
            try:
                mtime: float | None = self.path.stat().st_mtime
            except OSError:
                mtime = None
            if mtime == self._mtime:
                return
            self._mtime = mtime
            self.config, self.config_error = load_config(self.path)
        if self.config is None:
            log.warning("interlock: %s (%s): every bot press is refused", self.path,
                        self.config_error)  # fmt: skip
        else:
            log.info("interlock: %d environments from %s", len(self.config.environments),
                     self.path)  # fmt: skip

    def attested(self, msg: Attestation, now_ns: int) -> None:
        self.attest, self.attest_at_ns = msg, now_ns
        self.attestations += 1

    def verdict(self, mode: Mode, lock: CaptureBackend, window: Window | None,
                now_ns: int) -> Verdict:  # fmt: skip
        age = None if self.attest_at_ns is None else (now_ns - self.attest_at_ns) / 1e9
        return evaluate(self.config, self.config_error, mode=mode, lock=lock,
                        win_host=self.win_host, attest=self.attest, attest_age_s=age,
                        window=window)  # fmt: skip

    def snapshot(self, verdict: Verdict) -> dict[str, Any]:
        """/health: the verdict plus the attestation's yes/no and age -- the aid only as 'lab or
        not' would hide a mismatch, so it is shown (a number the server assigned, not a secret)."""
        a = self.attest
        return {
            **verdict.status().model_dump(mode="json"),
            "config": self.config_error or "ok",
            "attestations": self.attestations,
            "session_live": None if a is None else a.session_live,
            "aid": None if a is None else a.aid,
            "map_conns": None if a is None else a.map_conns,
            "server": None if a is None else a.server,
        }
