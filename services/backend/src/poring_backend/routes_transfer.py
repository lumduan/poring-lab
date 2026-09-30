"""Human-only file transfer through ``\\\\tsclient\\transfer`` (ADR-0004).

The desktop redirects the tmpfs volume ``/transfer`` into Windows (``/drive:transfer,/transfer``);
these routes let the browser put files there and fetch the files Windows puts there.

Every route passes ``transfer_root``:
  * it arrived on the PUBLIC listener (:8000), else 404 -- never on the agent's :8001;
  * the feature is on (``RDP_DRIVES=transfer`` and the volume is mounted), else 503;
  * it carries an allowlisted Origin, else 403. Browsers send Origin on every cross-origin
    fetch/XHR -- downloads included, because the console fetches them as blobs -- while the agent
    and scripts do not, so they can neither list, read nor write files here. (A client that forges
    Origin is the ADR-0005 threat; it is tracked there.)
Refusals are counted in /health (``dropped_messages.transfer_http``) and logged. Actions are
audited in ``data/transfer_log``: name, size, sha256 -- never contents.
"""

import asyncio
import errno
import hashlib
import os
import re
import unicodedata
import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse

from poring_backend.routes_public import get_state
from poring_backend.state import AppState

router = APIRouter(prefix="/transfer")

PARTIAL_PREFIX = ".partial-"
NAME_MAX_BYTES = 200
_WINDOWS_FORBIDDEN = str.maketrans(dict.fromkeys('<>:"|?*', "_"))
_WINDOWS_RESERVED = re.compile(r"^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(\..*)?$", re.IGNORECASE)


def safe_name(raw: str) -> str:
    """A NEW file name that is safe on both sides of \\\\tsclient: no path, nothing hidden, nothing
    Windows cannot represent. Raises ValueError when no usable name remains."""
    name = unicodedata.normalize("NFC", raw).strip()
    if "/" in name or "\\" in name:
        raise ValueError("path separators are not allowed")
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in name):
        raise ValueError("control characters are not allowed")
    name = name.translate(_WINDOWS_FORBIDDEN).rstrip(". ")  # Windows drops trailing dots/spaces
    if not name:
        raise ValueError("empty name")
    if name.startswith("."):
        raise ValueError("hidden names are not allowed")
    if _WINDOWS_RESERVED.match(name):
        name = f"_{name}"
    if len(name.encode("utf-8")) > NAME_MAX_BYTES:
        raise ValueError(f"name longer than {NAME_MAX_BYTES} bytes")
    return name


def sweep_partials(root: Path) -> None:
    """Remove uploads that were interrupted by a restart."""
    for path in root.glob(f"{PARTIAL_PREFIX}*"):
        path.unlink(missing_ok=True)


def _fail(request: Request, status: int, reason: str, **extra: Any) -> HTTPException:
    get_state(request).drops.record("transfer_http", reason, request.method.lower())
    return HTTPException(status, {"reason": reason, **extra})


def transfer_root(request: Request) -> Path:
    state = get_state(request)
    settings = state.settings
    server = request.scope.get("server")
    if not server or server[1] != settings.public_port:
        raise _fail(request, 404, "not_public_listener")
    if not settings.transfer_enabled:
        raise _fail(request, 503, "transfer_disabled")
    origin = request.headers.get("origin")
    if origin is None:
        raise _fail(request, 403, "origin_required")
    if origin.rstrip("/") not in settings.origins:
        raise _fail(request, 403, "origin_not_allowed")
    return settings.transfer_dir


def _client(request: Request) -> str | None:
    return request.client.host if request.client else None


def _existing(request: Request, root: Path, raw: str) -> Path:
    """An entry that already exists directly in ``root`` (Windows may name it anything)."""
    if raw in {"", ".", ".."} or "/" in raw or "\\" in raw or "\x00" in raw:
        raise _fail(request, 400, "bad_name")
    path = root / raw
    if path.parent != root or raw.startswith(PARTIAL_PREFIX):
        raise _fail(request, 400, "bad_name")
    if path.is_symlink() or not path.exists():
        raise _fail(request, 404, "not_found")
    return path


def _free_bytes(root: Path) -> int:
    usage = os.statvfs(root)
    return usage.f_bavail * usage.f_frsize


def _sha256_file(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as fh:
        while chunk := fh.read(1 << 20):
            digest.update(chunk)
            size += len(chunk)
    return digest.hexdigest(), size


@router.get("/files")
def list_files(request: Request, root: Path = Depends(transfer_root)) -> dict[str, Any]:
    entries: list[dict[str, Any]] = []
    for entry in os.scandir(root):
        if entry.name.startswith(PARTIAL_PREFIX) or entry.is_symlink():
            continue
        is_dir = entry.is_dir(follow_symlinks=False)
        if not is_dir and not entry.is_file(follow_symlinks=False):
            continue
        st = entry.stat(follow_symlinks=False)
        entries.append(
            {
                "name": entry.name,
                "kind": "dir" if is_dir else "file",
                "size": 0 if is_dir else st.st_size,
                "mtime_ns": st.st_mtime_ns,
            }
        )
    entries.sort(key=lambda e: (e["kind"] != "dir", e["name"].casefold()))
    usage = os.statvfs(root)
    return {
        "files": entries,
        "free_bytes": usage.f_bavail * usage.f_frsize,
        "capacity_bytes": usage.f_blocks * usage.f_frsize,
        "max_file_bytes": get_state(request).settings.transfer_max_bytes,
    }


@router.put("/files/{name}")
async def upload(
    name: str,
    request: Request,
    overwrite: bool = False,
    root: Path = Depends(transfer_root),
) -> dict[str, Any]:
    state: AppState = get_state(request)
    try:
        final = safe_name(name)
    except ValueError as exc:
        raise _fail(request, 400, "bad_name", detail=str(exc)) from None
    target = root / final
    size = 0
    digest = hashlib.sha256()
    try:
        declared_raw = request.headers.get("content-length")
        if declared_raw is None or not declared_raw.isdigit():
            raise _fail(request, 411, "length_required")
        declared = int(declared_raw)
        cap = state.settings.transfer_max_bytes
        if declared > cap:
            raise _fail(request, 413, "too_large", size=declared, max_bytes=cap)
        free = _free_bytes(root)
        if declared > free:
            raise _fail(request, 507, "not_enough_space", size=declared, free_bytes=free)
        if target.is_dir():
            raise _fail(request, 409, "is_a_directory", name=final)
        if target.exists() and not overwrite:
            raise _fail(request, 409, "exists", name=final)
        partial = root / f"{PARTIAL_PREFIX}{uuid.uuid4().hex}"
        try:
            with partial.open("xb") as fh:
                async for chunk in request.stream():
                    size += len(chunk)
                    if size > declared:
                        raise _fail(request, 413, "body_larger_than_declared", max_bytes=cap)
                    digest.update(chunk)
                    fh.write(chunk)
            if size != declared:
                raise _fail(request, 400, "incomplete_body", size=size, declared=declared)
            os.replace(partial, target)
        except OSError as exc:
            if exc.errno == errno.ENOSPC:
                raise _fail(
                    request, 507, "not_enough_space", free_bytes=_free_bytes(root)
                ) from None
            raise
        finally:
            partial.unlink(missing_ok=True)
    except HTTPException as exc:
        reason = exc.detail["reason"] if isinstance(exc.detail, dict) else "error"
        state.transfer_log.write(
            "upload",
            name=final,
            size=size,
            sha256=None,
            ok=False,
            reason=reason,
            client=_client(request),
        )
        raise
    sha = digest.hexdigest()
    state.transfer_log.write(
        "upload", name=final, size=size, sha256=sha, ok=True, reason="ok", client=_client(request)
    )
    return {"name": final, "size": size, "sha256": sha}


@router.get("/files/{name}")
async def download(
    name: str, request: Request, root: Path = Depends(transfer_root)
) -> FileResponse:
    state = get_state(request)
    path = _existing(request, root, name)
    if not path.is_file():
        raise _fail(request, 409, "not_a_file")
    sha, size = await asyncio.to_thread(_sha256_file, path)
    state.transfer_log.write(
        "download",
        name=path.name,
        size=size,
        sha256=sha,
        ok=True,
        reason="ok",
        client=_client(request),
    )
    return FileResponse(
        path,
        filename=path.name,
        media_type="application/octet-stream",
        headers={"X-Content-SHA256": sha},
    )


@router.delete("/files/{name}")
def delete(name: str, request: Request, root: Path = Depends(transfer_root)) -> dict[str, Any]:
    state = get_state(request)
    path = _existing(request, root, name)
    size = 0
    try:
        if path.is_dir():
            path.rmdir()
        else:
            size = path.stat().st_size
            path.unlink()
    except OSError as exc:
        if exc.errno == errno.ENOTEMPTY:
            raise _fail(request, 409, "directory_not_empty") from None
        raise
    state.transfer_log.write(
        "delete",
        name=path.name,
        size=size,
        sha256=None,
        ok=True,
        reason="ok",
        client=_client(request),
    )
    return {"deleted": path.name}
