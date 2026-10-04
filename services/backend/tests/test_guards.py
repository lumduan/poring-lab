"""Structural guards: what may touch the human-only clipboard/transfer (ADR-0004) and the packet
ground truth (ADR-0007)."""

import math
import re
import subprocess
from pathlib import Path
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[3]
RDP_LOOP = ROOT / "services" / "desktop" / "bin" / "rdp-loop.sh"
TRANSFER_SERVICES = {"desktop", "backend"}


class _ComposeLoader(yaml.SafeLoader):
    """SafeLoader + compose's merge tags (`!reset`, `!override`): their value as plain YAML."""


for _tag in ("!reset", "!override"):
    _ComposeLoader.add_constructor(
        _tag,
        lambda loader, node: (
            loader.construct_mapping(node)
            if isinstance(node, yaml.MappingNode)
            else loader.construct_sequence(node)
            if isinstance(node, yaml.SequenceNode)
            else loader.construct_scalar(node)
        ),
    )


def compose(name: str) -> dict[str, Any]:
    data: dict[str, Any] = yaml.load((ROOT / name).read_text(), Loader=_ComposeLoader)
    return data


def volume_sources(service: dict[str, Any]) -> set[str]:
    out = set()
    for vol in service.get("volumes", []):
        out.add(vol.split(":", 1)[0] if isinstance(vol, str) else str(vol.get("source")))
    return out


@pytest.mark.parametrize("name", ["compose.yaml", "compose.dev.yaml"])
def test_transfer_volume_is_mounted_only_in_desktop_and_backend(name: str) -> None:
    services = compose(name)["services"]
    mounting = {svc for svc, spec in services.items() if "transfer" in volume_sources(spec or {})}
    assert mounting <= TRANSFER_SERVICES, mounting
    for forbidden in ("vision", "rathena", "sniffer", "db", "frontend", "frontend-dev"):
        assert forbidden not in mounting


def test_transfer_volume_is_a_capped_tmpfs() -> None:
    volume = compose("compose.yaml")["volumes"]["transfer"]
    opts = volume["driver_opts"]
    assert (opts["type"], opts["device"]) == ("tmpfs", "tmpfs")
    size = re.search(r"size=(\d+)m", opts["o"])
    assert size is not None and int(size.group(1)) <= 512
    services = compose("compose.yaml")["services"]
    mounting = {svc for svc, spec in services.items() if "transfer" in volume_sources(spec)}
    assert mounting == TRANSFER_SERVICES


def test_containers_that_write_the_tmpfs_have_room_for_it() -> None:
    services = compose("compose.yaml")["services"]
    for svc in TRANSFER_SERVICES:
        limit = services[svc]["mem_limit"]
        assert limit == services[svc]["memswap_limit"], "no swap: mem_limit == memswap_limit"
    assert services["desktop"]["mem_limit"] == "1536m"


def test_cpu_heavy_lab_services_yield_to_the_quant_stack() -> None:
    """xfreerdp takes 7-15 cores in full-scene motion; the host also runs live quant capture."""
    services = compose("compose.yaml")["services"]
    desktop, backend = services["desktop"], services["backend"]
    assert desktop["cpu_shares"] < 1024 and backend["cpu_shares"] < 1024, "below the quant default"
    assert 0 < float(desktop["cpus"]) <= 8, "desktop keeps a hard CPU ceiling"


def rdp_args(**env: str) -> tuple[list[str], str]:
    """Source rdp-loop.sh (the loop does not start) and run clipboard_args + drive_args."""
    script = f'source "{RDP_LOOP}"; clipboard_args; drive_args'
    result = subprocess.run(
        ["bash", "-c", script],
        env={"PATH": "/usr/bin:/bin", **env},
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.split(), result.stderr


def test_clipboard_is_off_by_default() -> None:
    assert rdp_args() == (["-clipboard"], "")


def test_text_to_remote_disables_files_and_windows_to_x(tmp_path: Path) -> None:
    args, _ = rdp_args(RDP_CLIPBOARD="text-to-remote")
    assert args == ["/clipboard:direction-to:remote,files-to:off"]


@pytest.mark.parametrize("value", ["all", "/clipboard:direction-to:all", "on", "+clipboard"])
def test_unknown_clipboard_values_stay_off_and_are_logged(value: str) -> None:
    args, log = rdp_args(RDP_CLIPBOARD=value)
    assert args == ["-clipboard"] and "clipboard stays OFF" in log


def test_transfer_drive_only_when_mounted(tmp_path: Path) -> None:
    args, _ = rdp_args(RDP_DRIVES="transfer", TRANSFER_DIR=str(tmp_path))
    assert args == ["-clipboard", f"/drive:transfer,{tmp_path}"]
    args, log = rdp_args(RDP_DRIVES="transfer", TRANSFER_DIR=str(tmp_path / "missing"))
    assert args == ["-clipboard"] and "not mounted" in log
    args, log = rdp_args(RDP_DRIVES="home,/etc", TRANSFER_DIR=str(tmp_path))
    assert args == ["-clipboard"] and "ignored" in log


def test_no_keyword_can_reach_the_forbidden_directions() -> None:
    text = RDP_LOOP.read_text()
    assert "direction-to:all" not in text and "direction-to:local" not in text
    assert "files-to:remote" not in text and "files-to:all" not in text


def test_x11vnc_never_relays_the_clipboard() -> None:
    script = (ROOT / "services" / "desktop" / "bin" / "run-x11vnc.sh").read_text()
    assert re.search(r"^args=\(.*-nosel", script, re.MULTILINE)


# Clipboard / selection / transfer are human-only: the agent side must not even mention them.
FORBIDDEN = re.compile(
    r"set_selection_owner|convert_selection|get_selection_owner|xfixes|CLIPBOARD|"
    r"ClipboardPaste|clipboard_paste|PasteResult|/transfer|tsclient|poring_backend|"
    # ADR-0007: packet ground truth is offline / human-console only -- and so are the Phase 2
    # labels derived from it (ADR-0010).
    r"poring_packets|poring_dataset|/ws/packets|/ingest/packets|captures",
    re.IGNORECASE,
)


def agent_side_sources() -> list[Path]:
    vision = sorted((ROOT / "services" / "vision" / "src").rglob("*.py"))
    return [*vision, ROOT / "packages" / "poring_env" / "src" / "poring_env" / "remote.py"]


def test_agent_side_code_has_no_clipboard_or_transfer_access() -> None:
    sources = agent_side_sources()
    assert len(sources) > 3
    offenders = [
        f"{path.relative_to(ROOT)}: {match.group(0)}"
        for path in sources
        for match in FORBIDDEN.finditer(path.read_text())
    ]
    assert offenders == []


# --- ADR-0007: packet captures stay offline ground truth -----------------------------------------
CAPTURE_MOUNTS = {"sniffer": False, "backend": True}  # service -> must be read-only


def mounts_of(service: dict[str, Any], volume: str) -> list[str]:
    out = []
    for vol in service.get("volumes", []):
        if isinstance(vol, str) and vol.split(":", 1)[0] == volume:
            out.append(vol)
    return out


@pytest.mark.parametrize("name", ["compose.yaml", "compose.dev.yaml"])
def test_captures_volume_only_in_sniffer_rw_and_backend_ro(name: str) -> None:
    services = compose(name)["services"]
    for svc, spec in services.items():
        mounts = mounts_of(spec or {}, "captures")
        if svc not in CAPTURE_MOUNTS:
            assert mounts == [], f"{name}: {svc} mounts captures"
            continue
        for mount in mounts:
            read_only = mount.endswith(":ro")
            assert read_only == CAPTURE_MOUNTS[svc], f"{name}: {svc} {mount}"


def test_the_dev_overlay_runs_the_slim_sniffer_image() -> None:
    """2026-10-03: the slim image replaced the dev overlay (backend image + host source)."""
    assert "sniffer" not in compose("compose.dev.yaml")["services"]
    build = compose("compose.yaml")["services"]["sniffer"]["build"]
    assert build == {"context": ".", "dockerfile": "services/sniffer/Dockerfile"}


def test_captures_volume_exists_and_sniffer_never_writes_the_data_dir() -> None:
    base = compose("compose.yaml")
    assert "captures" in base["volumes"]
    sniffer = base["services"]["sniffer"]
    assert mounts_of(sniffer, "captures") and not mounts_of(sniffer, "./data")
    assert sniffer.get("network_mode") == "service:rathena"
    assert sniffer["mem_limit"] == sniffer["memswap_limit"]


def test_vision_never_gets_the_packet_package() -> None:
    vision = (ROOT / "services" / "vision" / "pyproject.toml").read_text()
    assert "poring-packets" not in vision and "poring_packets" not in vision
    dockerfile = (ROOT / "services" / "vision" / "Dockerfile").read_text()
    copies = [
        line for line in dockerfile.splitlines() if "poring_packets" in line and "COPY" in line
    ]
    # Only the pyproject.toml (uv workspace discovery), never the source.
    assert copies == ["COPY packages/poring_packets/pyproject.toml packages/poring_packets/"]
    env = (ROOT / "packages" / "poring_env" / "pyproject.toml").read_text()
    assert "poring-packets" not in env


def test_vision_and_poring_env_never_get_the_dataset_package() -> None:
    """ADR-0010: packet-derived labels are training data, never decision-time input."""
    vision = (ROOT / "services" / "vision" / "pyproject.toml").read_text()
    assert "poring-dataset" not in vision and "poring_dataset" not in vision
    dockerfile = (ROOT / "services" / "vision" / "Dockerfile").read_text()
    copies = [
        line for line in dockerfile.splitlines() if "poring_dataset" in line and "COPY" in line
    ]
    assert copies == ["COPY packages/poring_dataset/pyproject.toml packages/poring_dataset/"]
    env_root = ROOT / "packages" / "poring_env"
    assert "poring-dataset" not in (env_root / "pyproject.toml").read_text()
    for path in (env_root / "src").rglob("*.py"):
        assert "poring_dataset" not in path.read_text(), f"{path} imports poring_dataset"


def test_rathena_ip_is_pinned_to_the_ingest_peer() -> None:
    from poring_backend.config import Settings

    rathena = compose("compose.yaml")["services"]["rathena"]
    pinned = rathena["networks"]["default"]["ipv4_address"]
    assert pinned == Settings().ingest_peer


# --- Phase 0: the RDP A/B override file (docs/phase0-latency.md) ---------------------------------


def rdp_override_args(tmp_path: Path, content: str) -> tuple[list[str], str]:
    override = tmp_path / "rdp-override"
    override.write_text(content)
    script = f'source "{RDP_LOOP}"; load_overrides; build_args'
    env = {
        "PATH": "/usr/bin:/bin",
        "WIN_HOST": "win.test",
        "RDP_USER": "u",
        "RDP_PASSWORD": "secret",
        "RDP_CERT_SHA256": "ab",
        "RDP_OVERRIDE_FILE": str(override),
    }
    result = subprocess.run(
        ["bash", "-c", script], env=env, capture_output=True, text=True, check=True
    )
    return result.stdout.split(), result.stderr


def test_override_file_switches_only_whitelisted_rdp_knobs(tmp_path: Path) -> None:
    args, log = rdp_override_args(
        tmp_path,
        "RDP_GFX=RFX\nRDP_NETWORK=lan\nRDP_FRAME_ACK=off\nRDP_GDI=hw\n"
        "RDP_GFX=$(touch /tmp/pwned)\nPATH=/evil\nRDP_CLIPBOARD=all\nRDP_DRIVES=transfer\n",
    )
    assert "/gfx:RFX,frame-ack:off" in args
    assert "/network:lan" in args and "/gdi:hw" in args
    assert "-clipboard" in args  # RDP_CLIPBOARD=all ignored: the clipboard stays off
    assert not any(a.startswith("/drive") for a in args)
    assert "(not KEY=word): PATH=/evil" in log and "(not KEY=word): RDP_GFX=$(touch" in log
    assert "override ignored: RDP_CLIPBOARD=all" in log
    assert not Path("/tmp/pwned").exists()


def test_no_override_file_means_todays_arguments(tmp_path: Path) -> None:
    args, _ = rdp_override_args(tmp_path, "")
    assert not any(a.startswith(("/gfx", "/network", "/gdi", "-gfx")) for a in args)
    args, _ = rdp_override_args(tmp_path, "RDP_GFX=off\n")
    assert "-gfx" in args and "/bpp:32" in args
    args, _ = rdp_override_args(tmp_path, "RDP_FRAME_ACK=off\n")
    assert "/gfx:frame-ack:off" in args


def test_avcthin_requests_10_3_avc_thin_client_caps(tmp_path: Path) -> None:
    args, log = rdp_override_args(tmp_path, "RDP_GFX=AVCthin\nRDP_FRAME_ACK=off\n")
    assert "/gfx:AVC444:on,thin-client:on,mask:2015,frame-ack:off" in args
    assert "override ignored" not in log


def test_a_missing_override_key_means_the_default_not_the_previous_value(tmp_path: Path) -> None:
    """Regression (2026-09-30): an override survived later reconnects (network=lan stuck)."""
    override = tmp_path / "rdp-override"
    script = (
        f'source "{RDP_LOOP}"; BASE_RDP_GFX=""; '
        f'printf "RDP_NETWORK=lan\\nRDP_GFX=RFX\\n" > "{override}"; load_overrides; build_args; '
        f'echo ---; printf "RDP_GDI=hw\\n" > "{override}"; load_overrides; build_args; '
        f'echo ---; rm "{override}"; load_overrides; build_args'
    )
    env = {
        "PATH": "/usr/bin:/bin",
        "WIN_HOST": "w",
        "RDP_USER": "u",
        "RDP_PASSWORD": "p",
        "RDP_CERT_SHA256": "ab",
        "RDP_OVERRIDE_FILE": str(override),
    }
    out = subprocess.run(["bash", "-c", script], env=env, capture_output=True, text=True).stdout
    first, second, third = (part.split() for part in out.split("---"))
    assert "/network:lan" in first and "/gfx:RFX" in first
    assert "/network:lan" not in second and "/gdi:hw" in second
    assert not any(a.startswith(("/gfx", "/network", "/gdi")) for a in second if a != "/gdi:hw")
    assert not any(a.startswith(("/gfx", "/network", "/gdi")) for a in third)


# --- the capture-backend lock (ADR-0009) ---------------------------------------------------------


@pytest.mark.parametrize("name", ["compose.yaml", "compose.dev.yaml"])
def test_lock_directory_is_read_only_everywhere_and_never_in_vision(name: str) -> None:
    for service_name, service in compose(name)["services"].items():
        for vol in service.get("volumes", []):
            if not isinstance(vol, str) or not vol.startswith("./state"):
                continue
            assert vol.endswith(":ro"), f"{name}: {service_name} mounts the lock writable: {vol}"
            assert service_name != "vision", f"{name}: vision must not see the lock"
    base = compose("compose.yaml")["services"]
    for must in ("desktop", "backend"):
        assert "./state:/lab-state:ro" in base[must]["volumes"], f"{must} must see the lock"


def test_lock_directory_exists_in_git_so_docker_never_creates_it_as_root() -> None:
    assert (ROOT / "state" / ".gitignore").read_text().split() == ["*", "!.gitignore"]


# --- gamestream (ADR-0009 console mode) ----------------------------------------------------------


def test_gamestream_service_is_contained() -> None:
    services = compose("compose.yaml")["services"]
    gs = services["gamestream"]
    assert gs["profiles"] == ["gamestream"]
    assert "depends_on" not in gs  # a guarded `up` must never recreate desktop as a dependency
    assert gs["mem_limit"] == gs["memswap_limit"] and gs["oom_score_adj"] == 500
    assert 0 < gs["cpu_shares"] < 1024 and 0 < float(gs["cpus"]) <= 4
    assert gs.get("read_only") is True
    assert set(gs["volumes"]) == {
        "x11-unix:/x11:ro",
        "./state:/lab-state:ro",
        "gamestream-state:/home/desk/.config",
        "framebus:/framebus",
        "s2-input:/s2-input",
    }
    env = gs.get("environment", {})
    assert not any(k.startswith("RDP_") for k in env), "no RDP credentials in gamestream"


@pytest.mark.parametrize("name", ["compose.yaml", "compose.dev.yaml"])
def test_the_pairing_key_volume_is_mounted_in_gamestream_only(name: str) -> None:
    for service_name, service in compose(name)["services"].items():
        if "gamestream-state" in volume_sources(service):
            assert service_name == "gamestream", f"{name}: {service_name} mounts the pairing key"


def test_gamestream_image_never_runs_the_desktop_startup() -> None:
    dockerfile = (ROOT / "services" / "gamestream" / "Dockerfile").read_text()
    assert "FROM poring-lab/desktop:local" in dockerfile
    assert 'CMD ["/usr/local/bin/gamestream-loop.sh"]' in dockerfile
    assert "HEALTHCHECK NONE" in dockerfile and "ENTRYPOINT []" in dockerfile
    assert "--checksum=sha256:" in dockerfile and "ARG MOONLIGHT_SHA256=" in dockerfile


def test_gamestream_creates_the_appimage_dir_traversable_before_the_add() -> None:
    """An ADD that creates /opt/moonlight applies its --chmod=0644 to the directory as well: the
    `desk` user could not reach the AppImage and the stream never started (2026-10-02)."""
    dockerfile = (ROOT / "services" / "gamestream" / "Dockerfile").read_text()
    mkdir = dockerfile.find("install -d -m 0755 /opt/moonlight")
    add = dockerfile.find("ADD --checksum")
    assert mkdir != -1 and add != -1 and mkdir < add


def test_gamestream_config_dir_is_owned_by_desk_in_the_image() -> None:
    """The gamestream-state volume mounts on /home/desk/.config. Root-owned, Moonlight could not
    save its identity, minted a new one per run, and no pairing could stick (2026-10-02)."""
    dockerfile = (ROOT / "services" / "gamestream" / "Dockerfile").read_text()
    assert "install -d -o desk -g desk -m 0700 /home/desk/.config" in dockerfile
    assert dockerfile.find("/home/desk/.config") < dockerfile.find("USER desk")


def test_gamestream_places_its_window_without_a_window_manager() -> None:
    """ADR-0009 amendment (2026-10-02): no WM on :99 by default -- a kiosk WM (matchbox) resized
    Moonlight's window during its renderer set-up and the stream stayed black. The placer runs only
    around the stream, and only moves. The clean room's V2 (2026-10-03) is the one exception:
    openbox, opt-in through the variant file only, around its own stream only, killed before the
    focus goes back to PointerRoot (and to-rdp refuses to let RDP connect while one runs)."""
    loop = (ROOT / "services" / "gamestream" / "bin" / "gamestream-loop.sh").read_text()
    dockerfile = (ROOT / "services" / "gamestream" / "Dockerfile").read_text()
    assert "matchbox" not in loop and "matchbox" not in dockerfile
    assert "xdotool" in dockerfile
    code = "\n".join(line for line in loop.splitlines() if not line.lstrip().startswith("#"))
    assert "windowsize" not in code and "windowstate" not in code
    start = code.find("    place_stream &\n")
    run = code.find('    run_moonlight "${args[@]}"')
    stop = code.find('    kill "${placer}"')
    refocus = code.find("    focus_pointer_root\n", stop)
    assert -1 < start < run < stop < refocus
    wm_start, wm_stop = code.find("    start_wm\n"), code.find("    stop_wm\n")
    assert -1 < wm_start < start and stop < wm_stop < refocus
    assert '[[ "${VARIANT_WM}" == openbox ]] || return 0' in code  # opt-in only
    assert code.count("openbox --config-file") == 1


def test_openbox_takes_no_input_and_never_touches_the_pairing_volume() -> None:
    rc = (ROOT / "services" / "gamestream" / "openbox" / "rc.xml").read_text()
    assert "<keyboard/>" in rc and "<mouse/>" in rc  # no binding can eat a bot's Alt+F4 or click
    assert "<maximized>no</maximized>" in rc and "<decor>no</decor>" in rc
    loop = (ROOT / "services" / "gamestream" / "bin" / "gamestream-loop.sh").read_text()
    launch = loop[loop.index("XDG_CONFIG_HOME=/tmp/") : loop.index("openbox --config-file")]
    assert "XDG_DATA_HOME=/tmp/" in launch  # not ~/.config (gamestream-state), not the rootfs


def test_gamestream_never_writes_a_core_file() -> None:
    """The S2 spike holds the pairing key in process memory (Batt, 2026-10-03)."""
    gs = compose("compose.yaml")["services"]["gamestream"]
    assert gs["ulimits"]["core"] == 0


def test_the_gamestream_dev_overlay_binds_code_read_only_and_no_secrets() -> None:
    dev = compose("compose.dev.yaml")["services"]["gamestream"]
    writable = [v for v in dev["volumes"] if not str(v).endswith(":ro")]
    # experiment C1: exactly ONE writable bind, the H.264 recording dir (dot-named, outside ./data)
    assert writable == ["${S2_REC_DIR:-/home/batt/poring-lab-rec/.s2-h264}:/s2-rec"]
    assert dev["environment"]["S2_REC"] == "/s2-rec"
    assert "gamestream-state" not in str(dev) and ".config" not in str(dev["volumes"])
    assert "/lab-state" not in str(writable) and "./data" not in str(writable)


def focus_function(path: Path) -> str:
    text = path.read_text()
    start = text.index("focus_pointer_root() {")
    return text[start : text.index("\n}\n", start)]


def test_both_display_paths_hand_back_the_keyboard_focus() -> None:
    """SDL focuses Moonlight's window with RevertToNone: after a stream the X focus was None and
    every key to the RDP session vanished (2026-10-02). rdp-loop resets it before every connect,
    gamestream after every stream, with the same code."""
    stream_loop = ROOT / "services" / "gamestream" / "bin" / "gamestream-loop.sh"
    assert focus_function(RDP_LOOP) == focus_function(stream_loop)
    assert "XSetInputFocus(dpy, 1, 1, 0)" in focus_function(RDP_LOOP)  # PointerRoot
    rdp = RDP_LOOP.read_text()
    connect = rdp.index("env -u RDP_PASSWORD xfreerdp3 /args-from:stdin")
    loop_top = rdp.rfind("    while true; do", 0, connect)
    assert rdp.rfind("    focus_pointer_root\n", 0, connect) > loop_top


def test_gdb_diagnostics_are_opt_in() -> None:
    services = compose("compose.yaml")["services"]
    assert services["gamestream"]["environment"]["GAMESTREAM_GDB_AFTER_S"] == (
        "${GAMESTREAM_GDB_AFTER_S:-}"
    )


def session_args(tmp_path: Path, **extra: str) -> list[str]:
    script = f'source "{RDP_LOOP}"; build_args'
    env = {"PATH": "/usr/bin:/bin", "WIN_HOST": "w", "RDP_USER": "u", "RDP_PASSWORD": "p",
           "RDP_CERT_SHA256": "ab", "RDP_OVERRIDE_FILE": str(tmp_path / "none")}  # fmt: skip
    out = subprocess.run(
        ["bash", "-c", script], env={**env, **extra}, capture_output=True, text=True, check=True
    )
    return out.stdout.split()


def test_rdp_draws_the_session_at_the_canvas_top_left(tmp_path: Path) -> None:
    args = session_args(tmp_path, SESSION_SIZE="1440x900")
    assert "/size:1440x900" in args and "/window-position:0x0" in args and "/f" not in args
    assert "-toggle-fullscreen" in args  # Ctrl+Alt+Enter can't change the geometry
    args = session_args(tmp_path)  # unset: the whole screen, as before 2026-10-02
    assert "/f" in args and not any(a.startswith(("/size", "/window-position")) for a in args)


def test_rdp_loop_refuses_a_malformed_session_size() -> None:
    script = (
        f'source "{RDP_LOOP}"; idle_forever() {{ echo "IDLE: $*"; exit 0; }}; '
        "xfreerdp3() { echo CONNECTED; }; main"
    )
    env = {"PATH": "/usr/bin:/bin", "WIN_HOST": "w", "RDP_USER": "u", "RDP_PASSWORD": "p",
           "SESSION_SIZE": "1440x900;rm"}  # fmt: skip
    out = subprocess.run(
        ["bash", "-c", script], env=env, capture_output=True, text=True, timeout=10
    )
    assert "IDLE: SESSION_SIZE='1440x900;rm' is not WxH" in out.stdout
    assert "CONNECTED" not in out.stdout


def test_backend_refuses_a_malformed_session_size() -> None:
    from pydantic import ValidationError

    from poring_backend.config import Settings

    assert Settings(session_size=" 1440x900 ").session_size == "1440x900"
    assert Settings(session_size="").session_size == ""
    for bad in ("1440", "1440x0", "x900", "1440X900", "1440x900+0+0"):
        with pytest.raises(ValidationError):
            Settings(session_size=bad)


SESSION_SERVICES = ("desktop", "backend", "vision", "gamestream")


def env_default(value: str) -> str:
    match = re.fullmatch(r"\$\{[A-Z_]+:-([^}]*)\}", value)
    assert match, value
    return match.group(1)


def test_every_display_consumer_uses_the_same_session_area() -> None:
    """The backend maps input over SESSION_SIZE; a consumer grabbing another area would click off
    target. Same variable, same default, in every service that touches the display."""
    services = compose("compose.yaml")["services"]
    values = {svc: services[svc]["environment"]["SESSION_SIZE"] for svc in SESSION_SERVICES}
    assert set(values.values()) == {"${SESSION_SIZE:-1440x900}"}, values


@pytest.mark.parametrize("source", ["compose.yaml", ".env.example"])
def test_the_canvas_lets_moonlight_open_the_stream_at_native_size(source: str) -> None:
    """Moonlight's windowed mode opens at the stream's size only if it is under 80 % of the screen
    in BOTH directions (Session::getWindowDimensions); otherwise 80 %, scaled (1152x720 on a
    1440x900 screen, 2026-10-02)."""
    if source == "compose.yaml":
        desktop = compose(source)["services"]["desktop"]["environment"]
        canvas = env_default(desktop["XVFB_RESOLUTION"])
        session = env_default(desktop["SESSION_SIZE"])
    else:
        env = dict(
            line.split("=", 1) for line in (ROOT / source).read_text().splitlines()
            if re.match(r"(XVFB_RESOLUTION|SESSION_SIZE)=", line)
        )  # fmt: skip
        canvas, session = env["XVFB_RESOLUTION"], env["SESSION_SIZE"]
    cw, ch = (int(v) for v in canvas.split("x")[:2])
    sw, sh = (int(v) for v in session.split("x"))
    # Moonlight: dst = ceil(screen * 0.8) & ~1; native only if dst > stream in both directions.
    assert (math.ceil(cw * 0.8) & ~1) > sw and (math.ceil(ch * 0.8) & ~1) > sh, (canvas, session)


# --- S2 frame bus (docs/s2-plan.md) ---------------------------------------------------------------
FRAMEBUS_MOUNTS = {"gamestream": False, "backend": True, "vision": True}  # service -> read-only


@pytest.mark.parametrize("name", ["compose.yaml", "compose.dev.yaml"])
def test_the_frame_bus_has_one_writer_and_read_only_readers(name: str) -> None:
    for svc, spec in compose(name)["services"].items():
        mounts = mounts_of(spec or {}, "framebus")
        if svc not in FRAMEBUS_MOUNTS:
            assert mounts == [], f"{name}: {svc} mounts the frame bus"
            continue
        for mount in mounts:
            assert mount.endswith(":ro") == FRAMEBUS_MOUNTS[svc], f"{name}: {svc} {mount}"


def test_the_frame_bus_is_a_capped_tmpfs_charged_to_its_writer() -> None:
    cfg = compose("compose.yaml")
    opts = cfg["volumes"]["framebus"]["driver_opts"]
    assert (opts["type"], opts["device"]) == ("tmpfs", "tmpfs")
    size = re.search(r"size=(\d+)m", opts["o"])
    assert size is not None and int(size.group(1)) <= 64
    gs = cfg["services"]["gamestream"]
    assert gs["mem_limit"] == gs["memswap_limit"] == "1600m"  # 1536m + the 64 MiB ring


# --- S2 input socket (ADR-0014, S2 step 3) --------------------------------------------------------
S2_INPUT_MOUNTS = {"gamestream": ["s2-input:/s2-input"], "backend": ["s2-input:/s2-input"]}


@pytest.mark.parametrize("name", ["compose.yaml", "compose.dev.yaml"])
def test_the_s2_input_socket_is_mounted_in_gamestream_and_backend_only(name: str) -> None:
    """An input path into Windows: the listener (the S2 client) and the ONE input writer (the
    backend's Injector) only. Never vision -- the bot reaches Windows only through the mux."""
    for svc, spec in compose(name)["services"].items():
        mounts = mounts_of(spec or {}, "s2-input")
        if name == "compose.dev.yaml" and svc in S2_INPUT_MOUNTS:
            assert mounts in ([], S2_INPUT_MOUNTS[svc]), f"{name}: {svc} {mounts}"  # base adds it
            continue
        assert mounts == S2_INPUT_MOUNTS.get(svc, []), f"{name}: {svc} {mounts}"


def test_the_s2_input_volume_is_a_tiny_private_tmpfs() -> None:
    opts = compose("compose.yaml")["volumes"]["s2-input"]["driver_opts"]
    assert (opts["type"], opts["device"]) == ("tmpfs", "tmpfs")
    assert "size=1m" in opts["o"] and "mode=0750" in opts["o"] and "uid=1000" in opts["o"]


def test_vision_never_ships_cuda_forward_compat_libs() -> None:
    """Error 804 on the GeForce (2026-10-03): the base image's cuda-compat libcuda is newer than the
    R580 driver, nvidia-container-toolkit loads it, and consumer GPUs refuse forward compat."""
    dockerfile = (ROOT / "services" / "vision" / "Dockerfile").read_text()
    assert "rm -rf /usr/local/cuda-13.0/compat" in dockerfile
    assert dockerfile.index("rm -rf /usr/local/cuda-13.0/compat") > dockerfile.index("uv sync")


# --- ADR-0005 closed for S2 (Batt, 2026-10-04): vision S2-only + option c2 -----------------------


def test_vision_has_no_x_and_reads_only_the_bus() -> None:
    vision = compose("compose.yaml")["services"]["vision"]
    assert mounts_of(vision, "x11-unix") == [], "vision must never reach X (ADR-0005 row 1)"
    assert "DISPLAY" not in vision.get("environment", {})
    assert vision["environment"]["VISION_FRAME_SOURCE"] == "bus"
    assert vision["environment"]["YOLO_OFFLINE"] == "1"


def test_vision_lives_on_the_internal_agent_network_only() -> None:
    cfg = compose("compose.yaml")
    assert cfg["services"]["vision"]["networks"] == ["agent"]
    assert set(cfg["services"]["backend"]["networks"]) == {"default", "agent"}
    agent = cfg["networks"]["agent"]
    assert agent["internal"] is True
    assert agent["driver_opts"]["com.docker.network.bridge.gateway_mode_ipv4"] == "isolated"
    subnet = agent["ipam"]["config"][0]["subnet"]
    assert subnet == "10.210.97.0/24" and not subnet.startswith("192.168.")  # CLAUDE.md rule 6


def test_the_backend_refuses_exactly_the_agent_subnet() -> None:
    from poring_backend.config import Settings

    subnet = compose("compose.yaml")["networks"]["agent"]["ipam"]["config"][0]["subnet"]
    assert Settings().agent_networks == subnet


def test_only_vision_and_backend_are_on_the_agent_network() -> None:
    for name in ("compose.yaml", "compose.dev.yaml"):
        for svc, spec in compose(name)["services"].items():
            nets = (spec or {}).get("networks") or []
            if "agent" in nets:
                assert svc in ("vision", "backend"), f"{name}: {svc} joined the agent network"


@pytest.mark.parametrize("name", ["compose.yaml", "compose.dev.yaml"])
def test_the_environment_allowlist_is_mounted_read_only_in_the_backend_only(name: str) -> None:
    """ADR-0016 (2026-10-04): the interlock's config is the backend's, read-only; nothing the
    agent runs in (vision) or that streams (gamestream) can see or change it."""
    for service_name, service in compose(name)["services"].items():
        mounts = [str(v) for v in service.get("volumes", [])]
        if any(":/lab-config" in v or v.startswith("./config") for v in mounts):
            assert service_name == "backend", f"{name}: {service_name} mounts the allowlist"
            assert "./config:/lab-config:ro" in mounts
    if name == "compose.yaml":
        backend = compose(name)["services"]["backend"]
        assert "./config:/lab-config:ro" in backend["volumes"]
        assert backend["environment"]["WIN_HOST"] == "${WIN_HOST:-}"
        from poring_backend.config import Settings

        assert Settings().environments_file == Path("/lab-config/environments.yaml")
