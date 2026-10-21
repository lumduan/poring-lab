"""Backend settings, read from the environment (names are case-insensitive)."""

import ipaddress
import re
from pathlib import Path
from typing import Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")

    display: str = ":99"
    # SESSION_SIZE "WxH": the Windows session's area at the X screen's top-left (ADR-0009
    # amendment, 2026-10-02). The stream and the agent's frames are cropped to it and input is
    # normalised over it; "" = the whole screen. The canvas (XVFB_RESOLUTION) may be larger.
    session_size: str = ""
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
    # Phase 0 latency knobs (docs/phase0-latency.md); all switchable at runtime through
    # POST /debug/stream-tuning (loopback only). These are the boot values.
    #   STREAM_CAPTURE: fixed (a slot grid at STREAM_FPS) | damage (grab on XDamage, capped at
    #   STREAM_MAX_FPS)
    # damage since 2026-09-30: -12.5 ms p50 / -21 ms p95 key-to-sent (docs/phase0-latency.md).
    stream_capture: Literal["fixed", "damage"] = "damage"
    stream_max_fps: float = 60.0
    #   CONSOLE_MOVE_INTERVAL_MS: unset = one pointer move per animation frame; N = send on the
    #   event, at most one per N ms. CONSOLE_PAINT: decode | raf.
    console_move_interval_ms: int | None = None
    console_paint: Literal["decode", "raf"] = "decode"
    # Clients allowed on /debug/* (the latency probe runs inside this container).
    debug_hosts: str = "127.0.0.1,::1"
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
    # The capture-backend lock directory (ADR-0009), bind-mounted read-only (compose.yaml).
    lab_state_dir: Path = Path("/lab-state")
    # S2 frame bus (docs/s2-plan.md): in console mode with a live writer, the console stream reads
    # decoded frames from this ring instead of grabbing X. CONSOLE_FPS caps that human view.
    framebus_path: Path = Path("/framebus/ring")
    # the RDP frame bus (rdp_bus.py): backend-private, written by the one X grabber on the RDP path
    rdp_ring_path: Path = Path("/dev/shm/rdp-ring")
    # S2 input socket (ADR-0014): in console mode, while the S2 client listens here, the Injector
    # sends the mux's events to it instead of XTest.
    s2_input_socket: Path = Path("/s2-input/input.sock")
    console_fps: float = 15.0
    transfer_max_bytes: int = 512 * 1024 * 1024
    # Pause between xfreerdp announcing the text to Windows and the Ctrl+V (RDP format-list trip).
    clipboard_settle_s: float = 0.5

    # --- ADR-0007: packet ground truth (sniffer -> backend -> console only) ----------------------
    # The sniffer runs in rathena's network namespace, so its ingest connection comes from
    # rathena's pinned compose address (compose.yaml networks.default.ipv4_address).
    ingest_peer: str = "10.210.96.6"
    # /ws/packets: browsers arrive with their real LAN addresses (Docker's DNAT keeps them), so the
    # viewer channel accepts ONLY these networks (comma-separated CIDRs). Everything else is
    # refused and counted -- compose peers, and the lab gateway: a container that reaches the
    # PUBLISHED port is proxied in from the gateway, indistinguishable from a host script, and can
    # forge an Origin (live probe, 2026-10-01). Host scripts read /captures instead.
    viewer_networks: str = "192.168.0.0/16"
    compose_subnet: str = "10.210.96.0/24"
    # ADR-0005 option c2 (2026-10-04): the internal agent network (vision). Refused on every
    # listener but the internal one (agent_net.AgentNetworkGuard). Pinned like the compose subnet.
    agent_networks: str = "10.210.97.0/24"

    # --- ADR-0016: the environment interlock (a LOGIC interlock, rewritten 2026-10-04) ----------
    # The allowlist, mounted read-only from ./config (compose.yaml). Missing => every bot press is
    # refused. WIN_HOST: the Windows host this lab drives (the same .env value desktop and
    # gamestream connect to); the allowlist's windows_host must equal it.
    environments_file: Path = Path("/lab-config/environments.yaml")
    win_host: str = ""
    # --- the /flows editor's committed config (blocks-from-hunt-flow.md B2; READ-ONLY, the same
    # ./config mount): the hunt block's rule-version index + evidence (config/flows/hunt) and the
    # map zones files (config/map_zones; Batt D6 2026-10-21: the editor EXPORTS, a person commits).
    flows_config_dir: Path = Path("/lab-config/flows")
    zones_dir: Path = Path("/lab-config/map_zones")
    # ZONES_CODE_DIR: where the runner's zones loader lives (scripts/map_zones.py + flow_zones.py),
    # mounted read-only in dev mode (compose.dev.yaml). Unset and not importable: the zones routes
    # answer 503 zones_engine_unavailable and lint names zones references unchecked (fail closed).
    zones_code_dir: Path | None = None
    # The human-only settings store (2026-10-06): the server allowlist + its audit log, and the
    # foreground gate's templates. Mounted read-write into the BACKEND ONLY (compose.yaml
    # ./settings:/lab-settings; test_guards). vision can write ./data, so nothing here lives there.
    settings_dir: Path = Path("/lab-settings")
    # HOST_LAN_IP: the lab host's own LAN address. Settings WRITES are refused from it and from
    # WIN_HOST even with the console's Origin: any process on the lab host can forge that header
    # (host-side automation included), and the Windows host is the machine the bot itself drives,
    # so a "browser" Save there could be the bot's click. Batt's own machines are other addresses.
    host_lan_ip: str = ""
    # How often DNS names on the allowlist are re-resolved (the resolved IPs are shown and matched).
    allowlist_resolve_s: float = 300.0

    # --- Black-screen detector (display.py) ------------------------------------------------------
    # GAME_REGION: the RO client area in desktop pixels, "x,y,w,h"; "" = the whole frame (only a
    # fully black desktop would trip it). BLACK_HOLD_S: how long it must stay black.
    game_region: str = ""
    black_hold_s: float = 5.0

    @field_validator("session_size")
    @classmethod
    def _session_size(cls, value: str) -> str:
        # Refused at startup, not at the first grab: a typo must not reach the stream or the mux.
        value = value.strip()
        if value and not re.fullmatch(r"[1-9][0-9]*x[1-9][0-9]*", value):
            raise ValueError(f"SESSION_SIZE must be WxH (e.g. 1440x900), got {value!r}")
        return value

    @property
    def origins(self) -> frozenset[str]:
        return frozenset(
            o.strip().rstrip("/") for o in self.frontend_origins.split(",") if o.strip()
        )

    @property
    def agent_nets(self) -> tuple[ipaddress.IPv4Network | ipaddress.IPv6Network, ...]:
        return tuple(
            ipaddress.ip_network(n.strip()) for n in self.agent_networks.split(",") if n.strip()
        )

    @property
    def viewer_nets(self) -> tuple[ipaddress.IPv4Network | ipaddress.IPv6Network, ...]:
        return tuple(
            ipaddress.ip_network(n.strip()) for n in self.viewer_networks.split(",") if n.strip()
        )

    @property
    def debug_clients(self) -> frozenset[str]:
        return frozenset(h.strip() for h in self.debug_hosts.split(",") if h.strip())

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
