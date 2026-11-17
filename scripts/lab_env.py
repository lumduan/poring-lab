"""What differs between poring-lab installs, in ONE place (Batt 2026-11-17).

Batt: "every user's hardware is different; our project should run on any hardware, in containers"
and "don't lock an IP or anything". So nothing here is the lab's own: each value is read from the
environment first, else the repo's `.env` (the lab's style: `KEY=value`, no quotes), else a
DEFAULT that suits a fresh clone. The lab's own values are those same defaults (the project name,
the ports, the subnets) or its `.env` lines (the storage folder: the lab's NAS mount).

    COMPOSE_PROJECT_NAME   the Docker Compose project: every container, network, volume and image
                           name starts with it (default poring-lab). Two copies on one host need
                           two names; ./setup.sh refuses a name another folder's containers use.
    LAB_STORE_DIR          the long-term storage folder (datasets, archives, recordings, scratch
                           archives): any absolute path; a NAS is just a folder mounted there.
                           Default ~/poring-lab-store. The lab: its NAS mount.
    RATHENA_*_PORT, ...    the host ports (PORTS); rAthena's char and map ports are ADVERTISED to
                           the game client, so the container listens on the same number.
    LAB_NET_PREFIX, ...    the two pinned /24s (NETS; CLAUDE.md rule 6: one pinned /24 inside
                           10.210.0.0/16, never 192.168.x).

compose.yaml interpolates the same keys with the same defaults (test_lab_env.py checks they
agree). Stdlib only: guarded_build runs under the system python3.
"""

from __future__ import annotations

import ipaddress
import os
import re
from collections.abc import Mapping
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DOTENV = REPO / ".env"

PROJECT_KEY = "COMPOSE_PROJECT_NAME"
PROJECT_DEFAULT = "poring-lab"
# Docker Compose's own rule for a project name (lowercase letters, digits, '-' and '_', starting
# with a letter or digit); every name built from it (containers, networks, images) is then valid.
PROJECT_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,62}$")

STORE_KEY = "LAB_STORE_DIR"
STORE_DEFAULT = "poring-lab-store"  # under the user's home

# The host ports (key -> default). Each is published on HOST_LAN_IP.
PORTS: dict[str, int] = {
    "RATHENA_LOGIN_PORT": 6900,
    "RATHENA_CHAR_PORT": 6121,
    "RATHENA_MAP_PORT": 5121,
    "RATHENA_WEB_PORT": 8888,
    "NOVNC_PORT": 6080,
    "BACKEND_PORT": 8000,
    "CONSOLE_PORT": 3000,
}
# The pinned /24s, as their first three octets (key -> default).
NETS: dict[str, str] = {
    "LAB_NET_PREFIX": "10.210.96",  # the default network: rathena, backend, desktop, ...
    "LAB_AGENT_NET_PREFIX": "10.210.97",  # the internal agent network (ADR-0005 option c2)
}
POOL = ipaddress.ip_network("10.210.0.0/16")  # CLAUDE.md rule 6: every pin lives inside it
INGEST_HOST = 6  # rathena's pinned address on the default network (the backend's ingest peer)


def dotenv_value(key: str, path: Path = DOTENV) -> str | None:
    """The first `KEY=value` line of a .env file (no quotes, no expansion: the lab's .env style)."""
    try:
        lines = path.read_text().splitlines()
    except OSError:
        return None
    for line in lines:
        k, eq, v = line.partition("=")
        if eq and k.strip() == key:
            return v.strip()
    return None


def value(key: str, default: str | None = None, env: Mapping[str, str] | None = None,
          dotenv: Path = DOTENV) -> str | None:  # fmt: skip
    """The environment's value, else the .env file's, else ``default``. Empty counts as unset."""
    v = (os.environ if env is None else env).get(key)
    if not v:
        v = dotenv_value(key, dotenv)
    return v or default


# --- the project and the names built from it ------------------------------------------------------


def project(env: Mapping[str, str] | None = None, dotenv: Path = DOTENV) -> str:
    name = value(PROJECT_KEY, PROJECT_DEFAULT, env, dotenv) or PROJECT_DEFAULT
    if not PROJECT_RE.match(name):
        raise SystemExit(f"{PROJECT_KEY}={name!r}: lowercase letters, digits, '-' and '_' only, "
                         "starting with a letter or digit (Docker Compose's rule)")  # fmt: skip
    return name


def container(service: str, env: Mapping[str, str] | None = None, dotenv: Path = DOTENV) -> str:
    """A compose service's container: ``<project>-<service>-1``."""
    return f"{project(env, dotenv)}-{service}-1"


def network(name: str = "default", env: Mapping[str, str] | None = None,
            dotenv: Path = DOTENV) -> str:  # fmt: skip
    return f"{project(env, dotenv)}_{name}"


def volume(name: str, env: Mapping[str, str] | None = None, dotenv: Path = DOTENV) -> str:
    return f"{project(env, dotenv)}_{name}"


def image(name: str, tag: str = "local", env: Mapping[str, str] | None = None,
          dotenv: Path = DOTENV) -> str:  # fmt: skip
    """One of OUR images: ``<project>/<name>:<tag>`` (compose.yaml names them the same way)."""
    return f"{project(env, dotenv)}/{name}:{tag}"


def shm(name: str, env: Mapping[str, str] | None = None, dotenv: Path = DOTENV) -> Path:
    """A per-copy RAM path: ``/dev/shm/<project>-<name>`` (the lab: /dev/shm/poring-lab-<name>)."""
    return Path("/dev/shm") / f"{project(env, dotenv)}-{name}"


# --- the storage folder ---------------------------------------------------------------------------


def store_dir(env: Mapping[str, str] | None = None, dotenv: Path = DOTENV,
              home: Path | None = None) -> Path:  # fmt: skip
    """The long-term storage folder (LAB_STORE_DIR), absolute; default ~/poring-lab-store."""
    raw = value(STORE_KEY, None, env, dotenv)
    if raw is None:
        return (Path.home() if home is None else home) / STORE_DEFAULT
    p = Path(raw).expanduser()
    if not p.is_absolute():
        raise SystemExit(f"{STORE_KEY}={raw!r}: give an absolute folder (e.g. /srv/poring-lab)")
    return p


def store(*parts: str, env: Mapping[str, str] | None = None, dotenv: Path = DOTENV) -> Path:
    """A path inside the storage folder, e.g. ``store("archive", "models")``."""
    return store_dir(env, dotenv).joinpath(*parts)


# --- the CPU detector's environment ---------------------------------------------------------------

DETECTOR_KEY = "DETECTOR_DIR"


def detector_dir(env: Mapping[str, str] | None = None, dotenv: Path = DOTENV,
                 home: Path | None = None) -> Path:  # fmt: skip
    """The CPU detector's environment (its .venv and model/): DETECTOR_DIR, else
    ~/.local/share/<project>/detector (on disk, so it survives a reboot). The lab keeps it in RAM
    (/dev/shm/poring-lab-detector, its .env)."""
    raw = value(DETECTOR_KEY, None, env, dotenv)
    if raw is None:
        base = Path.home() if home is None else home
        return base / ".local" / "share" / project(env, dotenv) / "detector"
    p = Path(raw).expanduser()
    if not p.is_absolute():
        raise SystemExit(f"{DETECTOR_KEY}={raw!r}: give an absolute folder")
    return p


# --- ports and subnets ----------------------------------------------------------------------------


def port(key: str, env: Mapping[str, str] | None = None, dotenv: Path = DOTENV) -> int:
    if key not in PORTS:
        raise KeyError(key)
    raw = value(key, str(PORTS[key]), env, dotenv) or str(PORTS[key])
    if not raw.isdigit() or not 1 <= int(raw) <= 65535:
        raise SystemExit(f"{key}={raw!r}: a port number, 1-65535")
    return int(raw)


def ports(env: Mapping[str, str] | None = None, dotenv: Path = DOTENV) -> dict[str, int]:
    return {k: port(k, env, dotenv) for k in PORTS}


def net_prefix(key: str, env: Mapping[str, str] | None = None, dotenv: Path = DOTENV) -> str:
    """A pinned /24's first three octets, checked to lie inside 10.210.0.0/16 (rule 6)."""
    if key not in NETS:
        raise KeyError(key)
    raw = value(key, NETS[key], env, dotenv) or NETS[key]
    try:
        net = ipaddress.ip_network(f"{raw}.0/24")
    except ValueError:
        raise SystemExit(f"{key}={raw!r}: three octets, e.g. {NETS[key]}") from None
    if not net.subnet_of(POOL):  # type: ignore[arg-type]
        raise SystemExit(f"{key}={raw!r}: must lie inside {POOL} (CLAUDE.md rule 6)")
    return raw


def subnet(key: str, env: Mapping[str, str] | None = None, dotenv: Path = DOTENV) -> str:
    return f"{net_prefix(key, env, dotenv)}.0/24"


def ingest_peer(env: Mapping[str, str] | None = None, dotenv: Path = DOTENV) -> str:
    """rathena's pinned address: the backend accepts /ingest/packets only from it."""
    return f"{net_prefix('LAB_NET_PREFIX', env, dotenv)}.{INGEST_HOST}"
