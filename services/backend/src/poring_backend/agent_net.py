"""ADR-0005 option c2 (Batt approved 2026-10-04): the bot's network may reach the backend ONLY on
the internal agent channel.

vision lives on the internal `agent` network (compose: `internal: true`, 10.210.97.0/24). From there
it could still dial the backend's PUBLIC listener -- `/ws/input` accepts script clients as HUMAN
input, and `/transfer` trusts an Origin header it cannot authenticate. This ASGI middleware refuses
every connection from AGENT_NETWORKS that did not arrive on the internal listener: HTTP 403, and a
WebSocket is closed before it is accepted. `/internal/agent` (internal port only) is untouched, so
the bot's one way in stays the mux.
"""

import ipaddress
import logging
from collections.abc import Awaitable, Callable, MutableMapping
from typing import Any

log = logging.getLogger(__name__)

Scope = MutableMapping[str, Any]
Message = MutableMapping[str, Any]
Receive = Callable[[], Awaitable[Message]]
Send = Callable[[Message], Awaitable[None]]
ASGIApp = Callable[[Scope, Receive, Send], Awaitable[None]]
Nets = tuple[ipaddress.IPv4Network | ipaddress.IPv6Network, ...]


class AgentNetworkGuard:
    """Refuses the agent subnet on every listener except the internal one."""

    refused = 0  # class-wide counter for /health (one app per process)

    def __init__(self, app: ASGIApp, *, nets: Nets, internal_port: int) -> None:
        self.app, self.nets, self.internal_port = app, nets, internal_port

    def _from_agent_net(self, scope: Scope) -> bool:
        client = scope.get("client")
        if not client:
            return False
        try:
            ip = ipaddress.ip_address(client[0])
        except ValueError:
            return False
        return any(ip in net for net in self.nets)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] in ("http", "websocket"):
            server = scope.get("server") or ("", 0)
            if server[1] != self.internal_port and self._from_agent_net(scope):
                AgentNetworkGuard.refused += 1
                kind, path = scope["type"], scope.get("path")
                log.warning("refused %s %s from the agent network", kind, path)
                if scope["type"] == "websocket":
                    await send({"type": "websocket.close", "code": 1008})
                    return
                await send({"type": "http.response.start", "status": 403,
                            "headers": [(b"content-type", b"application/json")]})  # fmt: skip
                await send({"type": "http.response.body",
                            "body": b'{"detail":{"reason":"agent_network"}}'})  # fmt: skip
                return
        await self.app(scope, receive, send)
