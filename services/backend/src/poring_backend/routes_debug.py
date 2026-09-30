"""Loopback-only diagnostics for the Phase 0 latency work (docs/phase0-latency.md).

``scripts/latency_probe.py`` runs inside this container and uses these to read raw timing records
and to switch stream/console tuning at runtime, one change at a time, without restarts. Any other
client (the LAN, the agent on the compose network) gets 404.
"""

import logging
from dataclasses import asdict
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from poring_backend.routes_public import get_state
from poring_backend.state import AppState
from poring_env.clock import monotonic_ns

log = logging.getLogger(__name__)
router = APIRouter(prefix="/debug")


def loopback_only(request: Request) -> AppState:
    state = get_state(request)
    host = request.client.host if request.client else None
    if host not in state.settings.debug_clients:
        raise HTTPException(404)
    return state


class TuningUpdate(BaseModel):
    """Only the fields given change. ``move_interval_ms: "raf"`` restores one move per frame."""

    model_config = ConfigDict(extra="forbid")

    capture: Literal["fixed", "damage"] | None = None
    fps: float | None = Field(default=None, gt=0, le=120)
    max_fps: float | None = Field(default=None, gt=0, le=120)
    jpeg_quality: int | None = Field(default=None, ge=10, le=100)
    move_interval_ms: int | Literal["raf"] | None = Field(default=None)
    paint: Literal["decode", "raf"] | None = None


# async on purpose: these run on the event-loop thread, which is the only thread that mutates the
# recorder and the tuning, so no route can iterate a ring while it changes.
@router.get("/latency")
async def latency(since_ns: int = 0, state: AppState = Depends(loopback_only)) -> dict[str, Any]:
    return {"now_ns": monotonic_ns(), **state.latency.dump(since_ns)}


@router.get("/stream-tuning")
async def get_tuning(state: AppState = Depends(loopback_only)) -> dict[str, Any]:
    return asdict(state.tuning)


@router.post("/stream-tuning")
async def set_tuning(
    update: TuningUpdate, state: AppState = Depends(loopback_only)
) -> dict[str, Any]:
    tuning = state.tuning
    changes: dict[str, Any] = update.model_dump(exclude_none=True)
    if (
        isinstance(changes.get("move_interval_ms"), int)
        and not 0 <= changes["move_interval_ms"] <= 100
    ):
        raise HTTPException(422, "move_interval_ms must be 0..100 or 'raf'")
    if changes.get("move_interval_ms") == "raf":
        changes["move_interval_ms"] = None  # back to one pointer move per animation frame
    for name, value in changes.items():
        setattr(tuning, name, value)
    log.info("stream tuning changed: %s -> %s", changes, asdict(tuning))
    state.broadcast_status()  # console knobs reach the open tabs within a second
    return asdict(tuning)
