"""B6 hand-checked labels (Post-S2 round Part D, 2026-10-04): the /qa editor saves a human's box
corrections here; scripts/label_iou.py pins them on the NAS and scores the auto-labels against them.

    GET /qa/handcheck/{session}   the saved hand-check, or 404
    PUT /qa/handcheck/{session}   replace it (the editor sends the whole file)

Who may (the transfer routes' pattern, ADR-0004):
  * the PUBLIC listener (:8000) only -- never the agent's :8001 (and the agent network is refused on
    :8000 by AgentNetworkGuard, ADR-0005 c2);
  * a LAN VIEWER (VIEWER_NETWORKS, the compose subnet refused: a container dialling the published
    port arrives from its gateway);
  * an allowlisted Origin -- browsers send it; the agent and scripts do not.
Refusals are counted in /health (``dropped_messages.qa_http``). Bodies are validated and capped.

Files: data/qa/handcheck/<session>.json (gitignored data/), written atomically, read back. The
labels describe the lab's own scenes; other players' names never appear (boxes carry a class, not
a name).
"""

import json
import logging
import os
import re
import time
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from poring_backend.routes_packets import viewer_refusal
from poring_backend.routes_public import get_state

log = logging.getLogger(__name__)
router = APIRouter(prefix="/qa")

SESSION_RE = re.compile(r"^[0-9]{8}T[0-9]{6}-[A-Za-z0-9_.-]{1,60}$")
MAX_BODY = 2 * 1024 * 1024
MAX_FRAMES = 2000
MAX_BOXES = 200


class HandBox(BaseModel):
    model_config = ConfigDict(extra="forbid")
    x1: float = Field(ge=-10000, le=10000)
    y1: float = Field(ge=-10000, le=10000)
    x2: float = Field(ge=-10000, le=10000)
    y2: float = Field(ge=-10000, le=10000)
    cls: Literal["player", "monster", "npc"]
    gid: int | None = None  # the auto-label it came from; None for a box the human added


class HandFrame(BaseModel):
    model_config = ConfigDict(extra="forbid")
    frame_id: int
    t_mono_ns: int
    status: Literal["accepted", "edited"]
    boxes: list[HandBox] = Field(max_length=MAX_BOXES)


class HandCheck(BaseModel):
    model_config = ConfigDict(extra="forbid")
    session: str
    size: tuple[int, int]
    author: str = Field(default="batt", min_length=1, max_length=40, pattern=r"^[A-Za-z0-9_.-]+$")
    frames: list[HandFrame] = Field(max_length=MAX_FRAMES)


def _fail(request: Request, status: int, reason: str) -> HTTPException:
    get_state(request).drops.record("qa_http", reason, request.method.lower())
    return HTTPException(status, {"reason": reason})


def qa_dir(request: Request) -> Path:
    settings = get_state(request).settings
    server = request.scope.get("server")
    if not server or server[1] != settings.public_port:
        raise _fail(request, 404, "not_public_listener")
    peer = request.client.host if request.client else None
    refusal = viewer_refusal(peer, settings.compose_subnet, settings.viewer_nets)
    if refusal is not None:
        raise _fail(request, 403, refusal)
    origin = request.headers.get("origin")
    if origin is None:
        raise _fail(request, 403, "origin_required")
    if origin.rstrip("/") not in settings.origins:
        raise _fail(request, 403, "origin_not_allowed")
    return settings.data_dir / "qa" / "handcheck"


def _path(request: Request, root: Path, session: str) -> Path:
    if not SESSION_RE.match(session):
        raise _fail(request, 400, "bad_session")
    return root / f"{session}.json"


@router.get("/handcheck/{session}")
def get_handcheck(session: str, request: Request, root: Path = Depends(qa_dir)) -> Any:
    path = _path(request, root, session)
    if not path.is_file():
        raise HTTPException(404, {"reason": "not_found"})
    return json.loads(path.read_text())


@router.put("/handcheck/{session}")
async def put_handcheck(
    session: str, request: Request, root: Path = Depends(qa_dir)
) -> dict[str, Any]:
    path = _path(request, root, session)
    length = request.headers.get("content-length")
    if length is not None and int(length) > MAX_BODY:
        raise _fail(request, 413, "too_large")
    body = await request.body()
    if len(body) > MAX_BODY:
        raise _fail(request, 413, "too_large")
    try:
        check = HandCheck.model_validate_json(body)
    except ValidationError:
        raise _fail(request, 422, "invalid") from None
    if check.session != session:
        raise _fail(request, 422, "session_mismatch")
    doc = check.model_dump() | {"saved_at": time.strftime("%Y-%m-%dT%H:%M:%S%z")}
    root.mkdir(parents=True, exist_ok=True)
    tmp = root / f".{session}.json.tmp"
    tmp.write_text(json.dumps(doc, indent=1) + "\n")
    os.replace(tmp, path)
    stored = json.loads(path.read_text())  # read back
    stored.pop("saved_at", None)
    back = HandCheck.model_validate(stored)
    edited = sum(1 for f in back.frames if f.status == "edited")
    log.info("qa handcheck saved: %s, %d frames (%d edited)", session, len(back.frames), edited)
    return {"saved": session, "frames": len(back.frames), "edited": edited}
