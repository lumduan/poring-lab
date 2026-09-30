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
    # FRONTEND_ORIGINS: comma-separated Origins allowed to open browser WebSockets (cross-site
    # WebSocket hijacking guard); anything else is refused. Requests without an Origin header
    # (scripts, the agent) are not browsers and are allowed. compose.yaml defaults it to
    # http://${HOST_LAN_IP}:3000; add e.g. http://localhost:3000 for `pnpm dev` on a workstation.
    frontend_origins: str = "http://192.168.1.13:3000"

    assist_lease_s: float = 3.0
    # STREAM_FPS / JPEG_QUALITY: browser stream only (the agent grabs frames itself).
    stream_fps: float = 30.0
    jpeg_quality: int = 80
    capture_with_cursor: bool = False
    status_hz: float = 1.0

    # --- ADR-0004: human-only clipboard + file transfer ------------------------------------------
    # The SAME keywords the desktop's rdp-loop.sh reads (compose passes them to both containers),
    # so the backend offers exactly what the RDP session was started with.
    #   RDP_CLIPBOARD: off (default) | text-to-remote
    #   RDP_DRIVES:    "" (default)  | transfer
    rdp_clipboard: str = "off"
    rdp_drives: str = ""
    # The tmpfs volume redirected into Windows as \\tsclient\transfer (compose: size=512m).
    transfer_dir: Path = Path("/transfer")
    transfer_max_bytes: int = 512 * 1024 * 1024
    # Pause between xfreerdp announcing the text to Windows and the Ctrl+V (RDP format-list trip).
    clipboard_settle_s: float = 0.5

    @property
    def origins(self) -> frozenset[str]:
        return frozenset(
            o.strip().rstrip("/") for o in self.frontend_origins.split(",") if o.strip()
        )

    @property
    def lease_ns(self) -> int:
        return int(self.assist_lease_s * 1e9)

    @property
    def clipboard_enabled(self) -> bool:
        return self.rdp_clipboard.strip() == "text-to-remote"

    @property
    def transfer_enabled(self) -> bool:
        drives = {d.strip() for d in self.rdp_drives.split(",")}
        return "transfer" in drives and self.transfer_dir.is_dir()
