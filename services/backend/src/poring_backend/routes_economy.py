"""GET /economy/*: the economy dashboard's exports (scripts/econ_dash.py, Batt 2026-11-11), for the
console's /economy page. READ-ONLY: this module never writes a file.

    GET /economy/list           the export names in <DATA_DIR>/econ/dashboard/ (newest first)
    GET /economy/data/{name}    one export, <name>.json, as written (JSON)

Who may: as /hardware, it is read-only lab data -- no Origin needed (the page fetches it
cross-origin; CORS lets the console's origins read the answer) -- but on the PUBLIC listener only:
  * the internal listener :8001 (the agent's) answers 404, counted in /health
    ``dropped_messages.economy_http``: the bot never reads its own P&L;
  * the agent network is refused on the public listener before any route runs
    (AgentNetworkGuard, ADR-0005 c2).

Names: a fixed character set (NAME_RE, the exporter's rule too), and the resolved path must stay
inside the directory, so no name reaches another file (no separator, no leading dot, no symlink
out). A refused name is counted (``economy_http``: bad_name / outside_dir). The files hold item
and monster names and prices read at run time from rAthena's db and the client (GPL- / client-
derived, gitignored data/): served to the LAN console only, never committed.
"""

import json
import re
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response

from poring_backend.routes_public import get_state

router = APIRouter(prefix="/economy")

NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")
MAX_BYTES = 16 * 1024 * 1024  # an export is ~10-100 kB; anything this big is not one of ours
CHANNEL = "economy_http"


def _refuse(request: Request, status: int, reason: str) -> HTTPException:
    get_state(request).drops.record(CHANNEL, reason, request.method.lower())
    return HTTPException(status, {"reason": reason})


def economy_dir(request: Request) -> Path:
    """The export directory, for a request on the PUBLIC listener only."""
    state = get_state(request)
    server = request.scope.get("server")
    if not server or server[1] != state.settings.public_port:
        raise _refuse(request, 404, "not_public_listener")
    return Path(state.settings.data_dir) / "econ" / "dashboard"


def valid_name(name: str) -> bool:
    return bool(NAME_RE.fullmatch(name))


def resolve(root: Path, name: str) -> Path | None:
    """PURE but for the filesystem's resolve(): <root>/<name>.json when ``name`` is valid AND the
    resolved path stays directly inside the resolved root; else None."""
    if not valid_name(name):
        return None
    base = root.resolve()
    path = (root / f"{name}.json").resolve()
    return path if path.parent == base else None


@router.get("/list")
def economy_list(root: Path = Depends(economy_dir)) -> dict[str, Any]:
    if not root.is_dir():
        return {"exports": [], "why": "no export yet (scripts/econ_dash.py export ... --name N)"}
    found: list[tuple[float, str, int]] = []
    for p in root.glob("*.json"):
        if resolve(root, p.stem) is None or not p.is_file():
            continue  # a foreign file (a dot-file, a temp, an odd name) is not listed
        st = p.stat()
        found.append((round(st.st_mtime, 3), p.stem, st.st_size))
    found.sort(key=lambda x: (-x[0], x[1]))  # newest first
    return {"exports": [{"name": n, "bytes": b, "modified": m} for m, n, b in found]}


@router.get("/data/{name}")
def economy_data(name: str, request: Request, root: Path = Depends(economy_dir)) -> Response:
    if not valid_name(name):
        raise _refuse(request, 400, "bad_name")
    path = resolve(root, name)
    if path is None:
        raise _refuse(request, 400, "outside_dir")
    if not path.is_file():
        raise HTTPException(404, {"reason": "not_found"})
    if path.stat().st_size > MAX_BYTES:
        raise _refuse(request, 413, "too_large")
    body = path.read_bytes()
    try:
        json.loads(body)
    except ValueError:
        raise _refuse(request, 422, "not_json") from None
    return Response(content=body, media_type="application/json")
