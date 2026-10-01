"""Structural guards: what may touch the human-only clipboard/transfer (ADR-0004) and the packet
ground truth (ADR-0007)."""

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
    # ADR-0007: packet ground truth is offline / human-console only.
    r"poring_packets|/ws/packets|/ingest/packets|captures",
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
