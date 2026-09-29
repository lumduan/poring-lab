"""App factory and entry point: one uvicorn server, two listening sockets.

``:8000`` is published to the LAN (health, stream, human input). ``:8001`` stays on the compose
network for the vision agent; ``/internal/*`` refuses connections that did not arrive on it
(uvicorn sets ``scope["server"]`` per connection from the accepting socket).
"""

import logging
import socket
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI

from poring_backend.config import Settings
from poring_backend.routes_internal import router as internal_router
from poring_backend.routes_public import router as public_router
from poring_backend.state import AppState, XInput
from poring_env.env import FrameSource


def create_app(
    settings: Settings | None = None,
    *,
    capture_factory: Callable[[], FrameSource] | None = None,
    input_factory: Callable[[], XInput] | None = None,
) -> FastAPI:
    cfg = settings or Settings()

    def default_capture() -> FrameSource:
        from poring_env.x11 import X11Capture

        return X11Capture(cfg.display, with_cursor=cfg.capture_with_cursor)

    def default_input() -> XInput:
        from poring_env.x11 import X11Input

        return X11Input(cfg.display)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        state = AppState(
            cfg,
            capture_factory=capture_factory or default_capture,
            input_factory=input_factory or default_input,
        )
        app.state.poring = state
        await state.start()
        try:
            yield
        finally:
            await state.stop()

    app = FastAPI(title="poring-lab backend", version="0.1.0", lifespan=lifespan)
    app.include_router(public_router)
    app.include_router(internal_router)
    return app


def _listen(host: str, port: int) -> socket.socket:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind((host, port))
    sock.set_inheritable(True)
    return sock


def build_config(app: FastAPI) -> uvicorn.Config:
    return uvicorn.Config(
        app,
        log_level="info",
        proxy_headers=False,
        ws_max_size=1 << 20,
        # No permessage-deflate: JPEG frames don't compress, and zlib ran on the event loop for
        # every ~600 KB frame, delaying the capture loop (22 fps instead of 30, measured).
        ws_per_message_deflate=False,
    )


def main() -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    settings = Settings()
    server = uvicorn.Server(build_config(create_app(settings)))
    server.run(
        sockets=[
            _listen(settings.bind_host, settings.public_port),
            _listen(settings.bind_host, settings.internal_port),
        ]
    )


if __name__ == "__main__":
    main()
