"""Backend settings, read from the environment (names are case-insensitive)."""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")

    display: str = ":99"
    data_dir: Path = Path("/data")

    bind_host: str = "0.0.0.0"
    # LAN-published: /health, /ws/stream, /ws/input.
    public_port: int = 8000
    # Compose-network only (never published): /internal/agent.
    internal_port: int = 8001
    # Comma-separated Origins allowed to open browser WebSockets (cross-site WS hijacking guard).
    # Requests without an Origin header (scripts, the agent) are not browsers and are allowed.
    allowed_origins: str = "http://localhost:3000,http://127.0.0.1:3000"

    assist_lease_s: float = 3.0
    stream_fps: float = 30.0
    jpeg_quality: int = 80
    capture_with_cursor: bool = False
    status_hz: float = 1.0

    @property
    def origins(self) -> frozenset[str]:
        return frozenset(
            o.strip().rstrip("/") for o in self.allowed_origins.split(",") if o.strip()
        )

    @property
    def lease_ns(self) -> int:
        return int(self.assist_lease_s * 1e9)
