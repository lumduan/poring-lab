"""Which sniffer container watches which server (environment ids, config/environments.yaml).

2026-10-05, the Thai-data experiment: rathena-th has its own sniffer (sniffer-th, its own captures
volume). Host scripts that read a sniffer's events (record_session, measure_delay, replay_states)
pick it from $PORING_SERVER (default lab-rathena); `--server` on those scripts sets it."""

from __future__ import annotations

import os

SNIFFERS = {"lab-rathena": "poring-lab-sniffer-1", "lab-rathena-th": "poring-lab-sniffer-th-1"}
DEFAULT = "lab-rathena"
ENV = "PORING_SERVER"


def server() -> str:
    name = os.environ.get(ENV) or DEFAULT
    if name not in SNIFFERS:
        raise SystemExit(f"{ENV}={name!r}: unknown server (known: {', '.join(sorted(SNIFFERS))})")
    return name


def sniffer() -> str:
    """The container whose /captures holds this server's events."""
    return SNIFFERS[server()]


def select(name: str | None) -> str:
    """Set the server for this process (a script's --server), and return it."""
    if name is not None:
        os.environ[ENV] = name
    return server()
