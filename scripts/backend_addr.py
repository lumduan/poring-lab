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
import sys
from pathlib import Path

_HERE = str(Path(__file__).resolve().parent)
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)
import lab_env  # noqa: E402  (a sibling, stdlib only: this copy's compose project names)

BACKEND = lab_env.container("backend")
DEFAULT_NETWORK = lab_env.network("default")
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
