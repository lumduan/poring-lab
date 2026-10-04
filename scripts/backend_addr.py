"""The backend container's address on the compose DEFAULT network. Stdlib only (guarded_build runs
on the host's bare python3).

Since the internal `agent` network (ADR-0005 option c2, 2026-10-04) the backend sits on two
networks. `{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}` then CONCATENATES both
addresses ("10.210.96.5" + "10.210.97.2"), and every host tool's /health and agent URL broke.
Docker also sorts the map keys, so "the first" address would be the agent network's. Index the
default network by NAME instead.
"""

from __future__ import annotations

import subprocess

BACKEND = "poring-lab-backend-1"
DEFAULT_NETWORK = "poring-lab_default"
FORMAT = '{{with index .NetworkSettings.Networks "%s"}}{{.IPAddress}}{{end}}'


def backend_ip(
    container: str = BACKEND, network: str = DEFAULT_NETWORK, *, run=subprocess.run
) -> str:
    """The container's IPv4 on ``network``, or "" when it is not running or not on it."""
    res = run(
        ["docker", "inspect", "-f", FORMAT % network, container],
        capture_output=True, text=True, check=False,
    )  # fmt: skip
    return res.stdout.strip() if res.returncode == 0 else ""
