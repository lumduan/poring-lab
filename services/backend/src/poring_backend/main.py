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
from starlette.middleware.cors import CORSMiddleware

from poring_backend.agent_net import AgentNetworkGuard
from poring_backend.clipboard import SelectionIO
from poring_backend.config import Settings
from poring_backend.routes_debug import router as debug_router
from poring_backend.routes_internal import router as internal_router
from poring_backend.routes_packets import router as packets_router
from poring_backend.routes_public import router as public_router
from poring_backend.routes_qa import router as qa_router
from poring_backend.routes_settings import router as settings_router
from poring_backend.routes_transfer import router as transfer_router
from poring_backend.routes_transfer import sweep_partials
from poring_backend.state import AppState, S2Sink, XInput
from poring_backend.stream import ChangeWatcher
from poring_env.env import FrameSource


def create_app(
    settings: Settings | None = None,
    *,
    capture_factory: Callable[[], FrameSource] | None = None,
    input_factory: Callable[[], XInput] | None = None,
    s2_input_factory: Callable[[], S2Sink] | None = None,
    clipboard_factory: Callable[[], SelectionIO] | None = None,
    damage_factory: Callable[[Callable[[int], None]], ChangeWatcher] | None = None,
) -> FastAPI:
    cfg = settings or Settings()

    def default_capture() -> FrameSource:
        from poring_env.x11 import X11Capture, parse_session_size

        session = parse_session_size(cfg.session_size)
        return X11Capture(cfg.display, with_cursor=cfg.capture_with_cursor, session=session)

    def default_input() -> XInput:
        from poring_env.x11 import X11Input, parse_session_size

        return X11Input(cfg.display, session=parse_session_size(cfg.session_size))

    def default_s2_input() -> S2Sink:
        from poring_env.s2input import GameStreamInput
        from poring_env.x11 import parse_session_size

        size = parse_session_size(cfg.session_size) or (1440, 900)
        return GameStreamInput(cfg.s2_input_socket, size=size)

    def default_damage(on_damage: Callable[[int], None]) -> ChangeWatcher:
        from poring_backend.damage import DamageWatcher

        return DamageWatcher(cfg.display, on_damage)

    def default_clipboard() -> SelectionIO:
        from poring_backend.clipboard import XSelectionIO

        return XSelectionIO(cfg.display)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        state = AppState(
            cfg,
            capture_factory=capture_factory or default_capture,
            input_factory=input_factory or default_input,
            s2_input_factory=s2_input_factory or default_s2_input,
            clipboard_factory=clipboard_factory or default_clipboard,
            damage_factory=damage_factory or default_damage,
        )
        if cfg.transfer_enabled:
            sweep_partials(cfg.transfer_dir)
        app.state.poring = state
        await state.start()
        try:
            yield
        finally:
            await state.stop()

    app = FastAPI(title="poring-lab backend", version="0.1.0", lifespan=lifespan)
    app.include_router(public_router)
    app.include_router(internal_router)
    app.include_router(packets_router)
    app.include_router(transfer_router)
    app.include_router(qa_router)
    app.include_router(settings_router)
    app.include_router(debug_router)
    # The console (another origin: :3000) calls the /transfer HTTP routes with fetch/XHR. Only the
    # allowlisted console origins may read the responses; the routes also refuse any request
    # without an allowlisted Origin (routes_transfer.transfer_root).
    app.add_middleware(
        CORSMiddleware,
        allow_origins=sorted(cfg.origins),
        allow_methods=["GET", "PUT", "DELETE"],
        allow_headers=["content-type", "x-csrf-token"],
        expose_headers=["content-disposition", "x-content-sha256"],
        max_age=600,
    )
    # ADR-0005 c2: added last, so it is the OUTERMOST layer -- the agent network is refused before
    # any route, CORS or WebSocket accept runs.
    app.add_middleware(AgentNetworkGuard, nets=cfg.agent_nets, internal_port=cfg.internal_port)
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
