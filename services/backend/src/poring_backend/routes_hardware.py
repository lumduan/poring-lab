"""GET /hardware: the hardware monitor's newest sample and its 10-minute history (hardware.py), for
the console's /hardware page (Batt 2026-11-08).

Who may: as /health, it is read-only status -- no Origin needed (the page fetches it cross-origin;
CORS lets the console's origins read the answer) -- but on the PUBLIC listener only:
  * the internal listener :8001 (the agent's) answers 404, counted in /health
    ``dropped_messages.hardware_http``: the bot never gets host telemetry;
  * the agent network is refused on the public listener before any route runs
    (AgentNetworkGuard, ADR-0005 c2).
The answer is its own REST model (hardware.HardwareView), not part of the WebSocket protocol.
"""

from fastapi import APIRouter, Depends, HTTPException, Request

from poring_backend.hardware import HardwareView
from poring_backend.routes_public import get_state
from poring_backend.state import AppState
from poring_env.clock import monotonic_ns

router = APIRouter()


def public_listener_only(request: Request) -> AppState:
    state = get_state(request)
    server = request.scope.get("server")
    if not server or server[1] != state.settings.public_port:
        state.drops.record("hardware_http", "not_public_listener", request.method.lower())
        raise HTTPException(404, {"reason": "not_public_listener"})
    return state


@router.get("/hardware")
async def hardware(state: AppState = Depends(public_listener_only)) -> HardwareView:
    # On the event loop, like record(): the ring is never read while it changes.
    return state.hardware.view(monotonic_ns())
