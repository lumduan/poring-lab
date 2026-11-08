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


@pytest.mark.parametrize("name", ["compose.yaml", "compose.dev.yaml", "compose.vision-worker.yaml"])
def test_transfer_volume_is_mounted_only_in_desktop_and_backend(name: str) -> None:
    services = compose(name)["services"]
    mounting = {svc for svc, spec in services.items() if "transfer" in volume_sources(spec or {})}
    assert mounting <= TRANSFER_SERVICES, mounting
    for forbidden in ("vision", "vision-worker", "rathena", "sniffer", "db", "frontend",
                      "frontend-dev"):  # fmt: skip
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


# --- ADR-0018: the AGPL-3.0 boundary -------------------------------------------------------------
# ultralytics (AGPL-3.0) is imported only inside services/vision, the one AGPL component; nothing
# else imports poring_vision. Everything outside it stays Apache-2.0.
AGPL_IMPORT = re.compile(r"^\s*(?:import|from)\s+(ultralytics|poring_vision)\b", re.MULTILINE)
NOT_SOURCE = {
    ".venv",
    "node_modules",
    ".git",
    ".next",
    "__pycache__",
    ".claude",
}  # .claude: worktrees
# Part of the vision component although it lives in scripts/: COPYed into the vision image only and
# run there (`run:vision@600=python scripts/check_gpu.py`). Its header says so (ADR-0018).
VISION_COMPONENT_SCRIPTS = {Path("scripts/check_gpu.py")}


def python_sources_outside_vision() -> list[Path]:
    vision = ROOT / "services" / "vision"
    return [
        p
        for p in ROOT.rglob("*.py")
        if not NOT_SOURCE.intersection(p.relative_to(ROOT).parts)
        and vision not in p.parents
        and p.relative_to(ROOT) not in VISION_COMPONENT_SCRIPTS
    ]


def test_the_vision_component_scripts_say_so() -> None:
    for rel in VISION_COMPONENT_SCRIPTS:
        assert "AGPL-3.0 vision component (ADR-0018)" in (ROOT / rel).read_text(), rel


def test_ultralytics_and_poring_vision_are_imported_only_inside_vision() -> None:
    sources = python_sources_outside_vision()
    assert len(sources) > 50
    offenders = [
        f"{path.relative_to(ROOT)}: {m.group(0).strip()}"
        for path in sources
        for m in AGPL_IMPORT.finditer(path.read_text(errors="replace"))
    ]
    assert offenders == []


def test_the_licences_are_declared_per_component() -> None:
    assert (ROOT / "LICENSE").read_text().lstrip().startswith("Apache License")
    agpl = (ROOT / "services" / "vision" / "LICENSE").read_text()
    assert agpl.lstrip().startswith("GNU AFFERO GENERAL PUBLIC LICENSE")
    vision = (ROOT / "services" / "vision" / "pyproject.toml").read_text()
    assert 'license = "AGPL-3.0-only"' in vision
    for rel in ("pyproject.toml", "packages/poring_env/pyproject.toml",
                "packages/poring_packets/pyproject.toml", "packages/poring_dataset/pyproject.toml",
                "packages/poring_flow/pyproject.toml",
                "services/backend/pyproject.toml"):  # fmt: skip
        assert 'license = "Apache-2.0"' in (ROOT / rel).read_text(), rel


# --- ADR-0007: packet captures stay offline ground truth -----------------------------------------
CAPTURE_MOUNTS = {"sniffer": False, "backend": True}  # service -> must be read-only


def mounts_of(service: dict[str, Any], volume: str) -> list[str]:
    out = []
    for vol in service.get("volumes", []):
        if isinstance(vol, str) and vol.split(":", 1)[0] == volume:
            out.append(vol)
    return out


@pytest.mark.parametrize("name", ["compose.yaml", "compose.dev.yaml", "compose.vision-worker.yaml"])
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
    """2026-10-03: the slim image replaced the dev overlay (backend image + host source).
    ADR-0007 Amendment C (ACCEPTED, Batt 2026-10-13): the dev overlay mounts ONLY the decoder's
    source, read-only, on that slim image; each start copies it to tmpfs and runs the start-time
    self-test (the table + the scrub) BEFORE the sniffer; no other service gains the mount."""
    build = compose("compose.yaml")["services"]["sniffer"]["build"]
    assert build == {"context": ".", "dockerfile": "services/sniffer/Dockerfile"}
    dev = compose("compose.dev.yaml")["services"]
    sniffer = dev["sniffer"]
    assert sniffer["volumes"] == ["./packages/poring_packets/src:/dev-src:ro"]
    assert set(sniffer) == {"volumes", "environment", "command"}  # nothing else is overridden
    cmd = " ".join(sniffer["command"])
    assert cmd.index("cp -R /dev-src/. /tmp/devsrc/") < cmd.index("poring_packets.selftest")
    assert cmd.index("poring_packets.selftest &&") < cmd.index("python -m poring_packets.sniffer")
    assert "SNIFFER_COMMIT" in sniffer["environment"]
    mounting = {n for n, svc in dev.items()
                if any("poring_packets" in str(v) for v in svc.get("volumes", []))}  # fmt: skip
    assert mounting == {"backend", "sniffer"}  # the backend's mount predates Amendment C
    base = compose("compose.yaml")["services"]["sniffer"]
    assert base["read_only"] is True and base["cap_add"] == ["NET_RAW"]


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


# --- ADR-0020: the flow package (the IR, the linter and the views; offline) -----------------------
FLOW_SRC = ROOT / "packages" / "poring_flow" / "src" / "poring_flow"
FLOW_BANNED_IMPORTS = {"poring_packets", "poring_dataset", "poring_vision", "ultralytics", "torch",
                       "runpy", "code", "codeop"}  # fmt: skip
FLOW_BANNED_CALLS = {"exec", "eval", "compile", "__import__", "import_module", "execfile"}


def _flow_trees() -> list[tuple[Path, Any]]:
    import ast

    sources = sorted(FLOW_SRC.rglob("*.py"))
    assert len(sources) >= 8
    return [(p, ast.parse(p.read_text())) for p in sources]


def test_poring_flow_imports_no_packets_dataset_or_vision() -> None:
    """ADR-0020 F1: the flow package never sees packets (ADR-0007), the label code (ADR-0010, so
    vision may import it) or the AGPL vision component (ADR-0018)."""
    import ast

    offenders = []
    for path, tree in _flow_trees():
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""]
            else:
                continue
            offenders += [
                f"{path.name}: {n}" for n in names if n.split(".")[0] in FLOW_BANNED_IMPORTS
            ]
    assert offenders == []
    deps = (ROOT / "packages" / "poring_flow" / "pyproject.toml").read_text()
    deps = deps.split("dependencies = [", 1)[1].split("]", 1)[0]
    for banned in ("poring-packets", "poring-dataset", "poring-vision", "ultralytics"):
        assert banned not in deps


def test_poring_flow_never_runs_text() -> None:
    """ADR-0020 7.4: no exec, eval, compile, __import__ or import_module in poring_flow; the Python
    view's single entry point is ast.parse, which builds an AST and runs nothing."""
    import ast

    offenders = []
    for path, tree in _flow_trees():
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                f = node.func
                name = (
                    f.id
                    if isinstance(f, ast.Name)
                    else f.attr
                    if isinstance(f, ast.Attribute)
                    else ""
                )
                regex = (
                    isinstance(f, ast.Attribute)
                    and isinstance(f.value, ast.Name)
                    and (f.value.id == "re")
                )  # re.compile builds a regular expression, not code
                if name in FLOW_BANNED_CALLS and not regex:
                    offenders.append(f"{path.name}:{node.lineno}: {name}")
    assert offenders == []


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


@pytest.mark.parametrize("name", ["compose.yaml", "compose.dev.yaml", "compose.vision-worker.yaml"])
def test_lock_directory_is_read_only_everywhere_and_never_in_vision(name: str) -> None:
    for service_name, service in compose(name)["services"].items():
        for vol in service.get("volumes", []):
            if not isinstance(vol, str) or not vol.startswith("./state"):
                continue
            assert vol.endswith(":ro"), f"{name}: {service_name} mounts the lock writable: {vol}"
            assert service_name != "vision", f"{name}: vision must not see the lock"
            if service_name == "vision-worker":  # the duty level only, never the lock directory
                assert vol == "./state/train-duty:/lab-duty:ro", f"{name}: {vol}"
    base = compose("compose.yaml")["services"]
    for must in ("desktop", "backend"):
        assert "./state:/lab-state:ro" in base[must]["volumes"], f"{must} must see the lock"


def test_lock_directory_exists_in_git_so_docker_never_creates_it_as_root() -> None:
    assert (ROOT / "state" / ".gitignore").read_text().split() == ["*", "!.gitignore"]


# --- the human-only settings store (2026-10-06) --------------------------------------------------


@pytest.mark.parametrize("name", ["compose.yaml", "compose.dev.yaml", "compose.vision-worker.yaml"])
def test_the_settings_store_is_writable_by_the_backend_only(name: str) -> None:
    """The server allowlist decides when the interlock may turn green, and the foreground gate's
    templates decide when bot typing passes: only the backend (whose one writer is the Settings
    page's human-only PUT) may mount them. vision can write ./data, so it must never see them."""
    for service_name, service in compose(name)["services"].items():
        mounts = [str(v) for v in service.get("volumes", [])]
        if any(":/lab-settings" in v or v.startswith("./settings") for v in mounts):
            assert service_name == "backend", f"{name}: {service_name} mounts the settings store"
    if name == "compose.yaml":
        backend = compose(name)["services"]["backend"]
        assert "./settings:/lab-settings" in backend["volumes"]
        # writes are refused from the lab host itself and from the bot's Windows host
        assert backend["environment"]["HOST_LAN_IP"] == "${HOST_LAN_IP:?}"
        assert backend["environment"]["WIN_HOST"] == "${WIN_HOST:-}"
        from poring_backend.config import Settings

        assert Settings().settings_dir == Path("/lab-settings")


def test_settings_directory_exists_in_git_and_its_contents_never_do() -> None:
    assert (ROOT / "settings" / ".gitignore").read_text().split() == ["*", "!.gitignore"]


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


@pytest.mark.parametrize("name", ["compose.yaml", "compose.dev.yaml", "compose.vision-worker.yaml"])
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


def test_the_gat_mount_is_the_backends_read_only_local_copy() -> None:
    """MW2 simulate on real routes (Batt 2026-10-09): the GATs are client-derived. Only the
    backend sees them, read-only, from the local disk copy (scripts/flows_gat.py), never a bind of
    the /dev/shm extraction (a missing source would be created root-owned at boot)."""
    for name in ("compose.yaml", "compose.dev.yaml"):
        for svc, conf in compose(name)["services"].items():
            gat = [v for v in conf.get("volumes", []) if "gat" in str(v).lower()]
            if name == "compose.dev.yaml" and svc == "backend":
                assert gat == ["./data/gat:/lab-gat:ro"], gat
                assert conf["environment"]["PORING_GAT_DIR"] == "/lab-gat"
            else:
                assert not gat, (name, svc, gat)
            assert "/dev/shm/poring-lab-tmp" not in str(conf.get("volumes", [])), (name, svc)


def test_the_zones_code_is_the_dev_backends_read_only_mount_only() -> None:
    """B2 (blocks-from-hunt-flow.md, 2026-10-21): the /flows Zones layer runs the runner's own zones
    loader. Its code (./scripts) is bound READ-ONLY into the dev backend only, never anywhere else
    and never writable; the backend finds it through ZONES_CODE_DIR."""
    for name in ("compose.yaml", "compose.dev.yaml"):
        for svc, conf in compose(name)["services"].items():
            mounts = [str(v) for v in conf.get("volumes", []) if str(v).startswith("./scripts")]
            if name == "compose.dev.yaml" and svc == "backend":
                assert mounts == ["./scripts:/lab-scripts:ro"], mounts
                assert conf["environment"]["ZONES_CODE_DIR"] == "/lab-scripts"
            else:
                assert not mounts, (name, svc, mounts)
                assert "ZONES_CODE_DIR" not in (conf.get("environment") or {}), (name, svc)


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
FRAMEBUS_MOUNTS = {"gamestream": False, "backend": True, "vision": True,
                   "vision-worker": True}  # service -> read-only  # fmt: skip


@pytest.mark.parametrize("name", ["compose.yaml", "compose.dev.yaml", "compose.vision-worker.yaml"])
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


@pytest.mark.parametrize("name", ["compose.yaml", "compose.dev.yaml", "compose.vision-worker.yaml"])
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


@pytest.mark.parametrize(
    "name",
    ["compose.yaml", "compose.dev.yaml", "compose.vision-dev.yaml", "compose.vision-worker.yaml"],
)
def test_the_nas_datasets_are_mounted_read_only_in_vision_only(name: str) -> None:
    """Batt 2026-10-04: training reads the NAS datasets READ-ONLY; nothing else mounts them (the
    host's own mount stays the only writer, nas-sink.md). The vision worker (option A) is a vision
    container."""
    for svc, spec in compose(name)["services"].items():
        mounts = mounts_of(spec or {}, "datasets-nas")
        if (svc, name) in (
            ("vision", "compose.yaml"),
            ("vision-worker", "compose.vision-worker.yaml"),
        ):
            assert mounts == ["datasets-nas:/datasets:ro"]
        else:
            assert mounts == [], f"{name}: {svc} mounts the NAS datasets"
    if name == "compose.yaml":
        opts = compose(name)["volumes"]["datasets-nas"]["driver_opts"]
        assert opts["type"] == "nfs" and opts["device"] == ":/mnt/tank-main/poring-lab/datasets"
        assert {"ro", "soft"} <= set(opts["o"].split(","))


def test_the_vision_dev_overlay_adds_only_the_source() -> None:
    """`rundev:vision`: the host's vision source read-only on PYTHONPATH, the host's duty level
    read-only (Batt 2026-10-07: the adaptive duty cycle), and nothing else."""
    services = compose("compose.vision-dev.yaml")["services"]
    assert list(services) == ["vision"]
    vision = services["vision"]
    assert set(vision) == {"volumes", "environment"}
    assert vision["volumes"] == [
        "./services/vision/src:/opt/vision-src:ro",
        "./state/train-duty:/lab-duty:ro",
    ]
    assert vision["environment"] == {"PYTHONPATH": "/opt/vision-src"}


# --- OPTION A: the long-lived vision worker (docs/operations/vision-long-lived.md, 2026-10-09) ---
WORKER_KEYS = {
    "profiles", "image", "pull_policy", "restart", "init", "oom_score_adj", "logging",
    "entrypoint", "environment", "volumes", "networks", "deploy", "mem_limit", "memswap_limit",
    "shm_size",
}  # fmt: skip


def test_the_vision_worker_is_exactly_a_rundev_vision_container() -> None:
    """The worker IS today's `rundev:vision` container, made long-lived: compose.yaml's vision plus
    compose.vision-dev.yaml's two read-only mounts and PYTHONPATH -- the same image, environment
    (R1's VRAM cap, bus-only frames, offline), limits (mem == memswap, oom_score_adj 500, no CPU
    change), GPU and network (agent only, ADR-0005). The only differences: an IDLE entrypoint (it
    never imports torch: no CUDA context), restart "no" (it starts only through the guarded step,
    never after a reboot: an unmeasured cold start), no build / pull / depends_on, and ONE more
    mount, the detect server's socket directory (ADR-0005 Amendment 2026-11-07)."""
    services = compose("compose.vision-worker.yaml")["services"]
    assert list(services) == ["vision-worker"]
    worker = services["vision-worker"]
    base = compose("compose.yaml")["services"]["vision"]
    dev = compose("compose.vision-dev.yaml")["services"]["vision"]
    assert set(worker) == WORKER_KEYS, set(worker) ^ WORKER_KEYS
    assert worker["image"] == base["image"] == "poring-lab/vision:local"
    assert worker["environment"] == {**base["environment"], **dev["environment"]}
    assert worker["volumes"] == [*base["volumes"], *dev["volumes"], DETECT_MOUNT]
    assert worker["networks"] == base["networks"] == ["agent"]
    assert worker["deploy"] == base["deploy"]
    for key in ("mem_limit", "memswap_limit", "shm_size", "oom_score_adj", "init", "logging",
                "cpus", "cpu_shares"):  # fmt: skip
        assert worker.get(key) == base.get(key), key
    assert worker["mem_limit"] == worker["memswap_limit"] and worker["oom_score_adj"] == 500
    assert worker["environment"]["VISION_MAX_VRAM_FRACTION"] == "${VISION_MAX_VRAM_FRACTION:-0.25}"
    assert worker["environment"]["VISION_FRAME_SOURCE"] == "bus"
    assert mounts_of(worker, "x11-unix") == [] and "DISPLAY" not in worker["environment"]
    assert worker["entrypoint"] == ["sleep", "infinity"] and "command" not in worker
    assert worker["restart"] == "no" and worker["pull_policy"] == "never"
    assert worker["profiles"] == ["vision-worker"]
    assert "./state/train-duty:/lab-duty:ro" in worker["volumes"]
    assert "./services/vision/src:/opt/vision-src:ro" in worker["volumes"]


DETECT_MOUNT = "/dev/shm/poring-lab-detect:/detect"  # ADR-0005 Amendment 2026-11-07


@pytest.mark.parametrize(
    "name",
    ["compose.yaml", "compose.dev.yaml", "compose.vision-dev.yaml", "compose.vision-worker.yaml"],
)
def test_the_detect_socket_directory_is_the_workers_alone(name: str) -> None:
    """ADR-0005 Amendment 2026-11-07 (Batt chose gpu-live-detector.md option A): the host RAM
    directory of the detect server's socket is mounted in the vision WORKER only, read-write (the
    server creates the socket), at /detect; never in the vision service or any other container,
    and no other host /dev/shm path reaches the worker."""
    for svc, spec in compose(name)["services"].items():
        vols = [v for v in (spec or {}).get("volumes", []) if isinstance(v, str)]
        detect = [v for v in vols if "poring-lab-detect" in v or v.split(":")[1:2] == ["/detect"]]
        if svc == "vision-worker":
            assert detect == [DETECT_MOUNT], (name, detect)
            assert [v for v in vols if v.startswith("/dev/shm")] == [DETECT_MOUNT]
        else:
            assert detect == [], (name, svc, detect)


def test_the_guard_creates_the_detect_directory_private_before_the_start(
    tmp_path: Path,
) -> None:
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "guarded_build_detect", ROOT / "scripts" / "guarded_build.py"
    )
    assert spec and spec.loader
    gb = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gb)
    assert str(gb.DETECT_DIR) == "/dev/shm/poring-lab-detect"
    assert gb.WORKER_MOUNTS["/detect"] == gb.DETECT_DIR
    d = tmp_path / "detect"
    assert gb.ensure_detect_dir(d) is None
    assert d.is_dir() and (d.stat().st_mode & 0o777) == 0o700
    d.chmod(0o755)
    assert gb.ensure_detect_dir(d) is None and (d.stat().st_mode & 0o777) == 0o700
    d.rmdir()
    target = tmp_path / "elsewhere"
    target.mkdir()
    d.symlink_to(target)
    assert "not a directory of ours" in str(gb.ensure_detect_dir(d))


def test_the_vision_worker_is_named_where_the_guard_looks_for_it() -> None:
    """guarded_build's steps target compose's container name for the service, and the worker's
    bind mounts are this checkout's (source, duty level, data)."""
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "guarded_build_names", ROOT / "scripts" / "guarded_build.py"
    )
    assert spec and spec.loader
    gb = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gb)
    project = compose("compose.yaml")["name"]
    assert project == "poring-lab"
    container = f"{project}-{gb.WORKER_SERVICE}-1"  # compose's default container name
    assert container == gb.WORKER
    assert gb.WORKER_SERVICE in compose("compose.vision-worker.yaml")["services"]
    assert gb.VISION_WORKER[:4] == ["-f", "compose.yaml", "-f", "compose.vision-worker.yaml"]
    worker = compose("compose.vision-worker.yaml")["services"]["vision-worker"]
    binds = {v.split(":")[1]: v.split(":")[0] for v in worker["volumes"]
             if v.startswith(("./", "/"))}  # fmt: skip
    for dst, src in gb.WORKER_MOUNTS.items():
        assert (ROOT / binds[dst]).resolve() == src.resolve(), dst


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
    for name in ("compose.yaml", "compose.dev.yaml", "compose.vision-worker.yaml"):
        for svc, spec in compose(name)["services"].items():
            nets = (spec or {}).get("networks") or []
            if "agent" in nets:
                assert svc in ("vision", "vision-worker", "backend"), (
                    f"{name}: {svc} joined the agent network"
                )


@pytest.mark.parametrize("name", ["compose.yaml", "compose.dev.yaml", "compose.vision-worker.yaml"])
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


# --- The Thai-data experiment (Batt, 2026-10-05): db-th, rathena-th, sniffer-th ----------------
TH_SERVICES = ("db-th", "rathena-th", "sniffer-th")


def lan_ports(spec: dict[str, Any]) -> list[str]:
    return [re.sub(r"^\$\{HOST_LAN_IP:[?-]\}:", "", p.split("#")[0].strip()) for p in spec["ports"]]


def test_the_th_services_are_separate_limited_and_never_built() -> None:
    services = compose("compose.yaml")["services"]
    for name in TH_SERVICES:
        spec = services[name]
        assert spec["profiles"] == ["th"], f"{name}: profile th only (never core: up/smoke)"
        assert spec["mem_limit"] == spec["memswap_limit"], f"{name}: no swap"
        assert spec["oom_score_adj"] == 500, name
        assert "build" not in spec and spec["pull_policy"] == "never", f"{name}: no build, no pull"
    th, rathena = services["rathena-th"], services["rathena"]
    assert th["image"] == rathena["image"]  # the same SHA and pre-renewal mode
    assert services["db-th"]["image"] == services["db"]["image"]


def test_rathena_th_runs_one_at_a_time_with_rathena() -> None:
    """The same pinned IP (the backend's only ingest peer) and the same LAN ports: Docker refuses
    to start one while the other runs. Concurrent instances would need a second LAN IP or new
    ports (the sniffer's compiled BPF, the image HEALTHCHECK and smoke_test all use these)."""
    from poring_backend.config import Settings

    services = compose("compose.yaml")["services"]
    th, rathena = services["rathena-th"], services["rathena"]
    ip = th["networks"]["default"]["ipv4_address"]
    assert ip == rathena["networks"]["default"]["ipv4_address"] == Settings().ingest_peer
    assert lan_ports(th) == ["6900:6900", "6121:6121", "5121:5121"]
    # + rathena's web-server (Batt 2026-11-05: the client's account settings; rathena only, on the
    # LAN address like the game ports)
    assert lan_ports(rathena) == [*lan_ports(th), "8888:8888"]
    # db-th is pinned HIGH: unpinned, it took rathena's .6 while rathena was down (2026-10-05)
    db_th_ip = services["db-th"]["networks"]["default"]["ipv4_address"]
    assert int(db_th_ip.rsplit(".", 1)[1]) >= 200 and db_th_ip != ip


def test_the_current_rathena_and_its_db_are_untouched_by_the_experiment() -> None:
    services = compose("compose.yaml")["services"]
    rathena, th = services["rathena"], services["rathena-th"]
    assert "RATHENA_IMPORT_MAPCACHE" not in rathena["environment"]
    for name in ("compose.yaml", "compose.dev.yaml"):
        spec = compose(name)["services"].get("rathena") or {}
        assert not any("mapcache" in str(v) for v in spec.get("volumes", [])), name
    assert rathena["environment"]["DB_HOST"] == "db" and th["environment"]["DB_HOST"] == "db-th"
    assert "./data/mapcache-th:/opt/rathena-mapcache:ro" in th["volumes"]
    assert th["environment"]["RATHENA_IMPORT_MAPCACHE"] == "/opt/rathena-mapcache/map_cache.dat"
    assert "db-th-data" in compose("compose.yaml")["volumes"]
    assert "db-th-data" not in volume_sources(services["db"])


def test_each_sniffer_names_its_server_and_keeps_its_own_captures() -> None:
    base = compose("compose.yaml")
    services = base["services"]
    sn = services["sniffer-th"]
    assert sn["network_mode"] == "service:rathena-th"
    assert services["sniffer"]["environment"]["SNIFFER_SERVER_ID"] == "lab-rathena"
    assert sn["environment"]["SNIFFER_SERVER_ID"] == "lab-rathena-th"
    envs = yaml.safe_load((ROOT / "config" / "environments.yaml").read_text())["environments"]
    assert {"lab-rathena", "lab-rathena-th"} <= {e["id"] for e in envs}
    assert mounts_of(sn, "captures-th") and not mounts_of(sn, "captures")
    assert not mounts_of(sn, "./data") and "captures-th" in base["volumes"]
    for name in ("compose.yaml", "compose.dev.yaml"):
        for svc, spec in compose(name)["services"].items():
            if svc != "sniffer-th":
                assert not mounts_of(spec or {}, "captures-th"), f"{name}: {svc}"
    assert "sniffer-th" not in compose("compose.dev.yaml")["services"]


def test_no_th_variable_is_required_at_interpolation() -> None:
    """Compose interpolates every service before it filters profiles: a required (':?') TH
    variable would break every compose command until .env has it."""
    text = (ROOT / "compose.yaml").read_text()
    assert not re.search(r"\$\{(?:RATHENA_TH|DB_TH)_[A-Z_]+:\?", text)


def test_every_uv_image_copies_every_workspace_member_pyproject() -> None:
    """`uv sync --frozen` needs every workspace member's pyproject in the build context's first
    layer. poring_skills (2026-10-07) was missing from all three Dockerfiles until the sniffer
    rebuild of 2026-10-08 found it."""
    import tomllib

    members = tomllib.loads((ROOT / "pyproject.toml").read_text())["tool"]["uv"]["workspace"][
        "members"
    ]
    for name in ("sniffer", "backend", "vision"):
        text = (ROOT / "services" / name / "Dockerfile").read_text()
        for m in members:
            assert f"COPY {m}/pyproject.toml {m}/" in text, (name, m)


# --- ADR-0022: the Intel vision image and its overlays (bot-server's Arc A380) --------------------
INTEL_OVERLAYS = {
    "compose.intel.yaml": "vision",
    "compose.vision-worker.intel.yaml": "vision-worker",
}


@pytest.mark.parametrize(("name", "svc"), INTEL_OVERLAYS.items())
def test_the_intel_overlays_change_only_the_image_the_gpu_and_the_accelerator(
    name: str, svc: str
) -> None:
    """Everything that isolates vision (the agent network only, no X, the mounts, mem == memswap,
    oom_score_adj) stays compose.yaml's / the worker file's: an overlay may set only these keys."""
    services = compose(name)["services"]
    assert list(services) == [svc]
    spec = services[svc]
    keys = {"image", "deploy", "devices", "group_add", "environment"}
    # the worker on a dedicated host: its memory cap too (Batt 2026-11-08), mem == memswap
    worker_keys = keys | {"mem_limit", "memswap_limit"}
    assert set(spec) == (keys | {"build"} if svc == "vision" else worker_keys)
    if svc == "vision-worker":
        assert spec["mem_limit"] == spec["memswap_limit"] == "11g"
    assert spec["image"] == "poring-lab/vision-intel:local"
    assert spec["deploy"] == {}  # `!reset {}`: no NVIDIA reservation
    assert spec["devices"] == ["/dev/dri/renderD128:/dev/dri/renderD128"]  # no KMS nodes (11-08)
    assert spec["group_add"] == ["${RENDER_GID:-991}"]
    assert spec["environment"] == {
        "PORING_ACCEL": "xpu", "VISION_MAX_VRAM_FRACTION": "${VISION_MAX_VRAM_FRACTION:-1.0}",
    }  # fmt: skip
    if svc == "vision":
        assert spec["build"] == {"context": ".", "dockerfile": "services/vision/Dockerfile.intel"}
    assert "!reset {}" in (ROOT / name).read_text()


def test_the_intel_image_never_gets_the_packet_or_dataset_package() -> None:
    """ADR-0007 / ADR-0010, as for the CUDA image -- here not even their pyproject.toml (no uv
    workspace in this image): only poring_env and services/vision are copied."""
    text = (ROOT / "services" / "vision" / "Dockerfile.intel").read_text()
    copies = [line for line in text.splitlines() if line.startswith("COPY")]
    assert not [c for c in copies if "poring_packets" in c or "poring_dataset" in c]
    assert "COPY packages/poring_env packages/poring_env" in copies
    assert "COPY services/vision services/vision" in copies
    assert "--require-hashes --no-deps -r /opt/requirements-intel.txt" in text
    assert "useradd --uid 1000" in text and "\nUSER agent\n" in text
    assert "PORING_ACCEL=xpu" in text


def _pins(text: str) -> dict[str, str]:
    pin = re.compile(r"^([A-Za-z0-9_.-]+)==([^ ;\\\n]+)", re.M)
    return {m[1].lower(): m[2] for m in pin.finditer(text)}


def test_the_intel_requirements_hold_the_locks_versions_but_the_torch_stack() -> None:
    """scripts/gen_intel_requirements.sh: every package uv.lock also has is at the lock's version,
    so the Intel image differs from the CUDA one only where it must. A lock bump without a re-run
    of the generator fails here."""
    import tomllib

    lock = {p["name"]: p["version"] for p in
            tomllib.loads((ROOT / "uv.lock").read_text())["package"] if "version" in p}  # fmt: skip
    req = _pins((ROOT / "services" / "vision" / "requirements-intel.txt").read_text())
    assert req["torch"] == "2.15.0+xpu" and req["torchvision"] == "0.29.2+xpu"
    assert req["openvino"] == "2026.4.1" and "opencv-python" not in req
    assert not [n for n in req if n.startswith(("nvidia-cu", "nvidia-cudnn", "nvidia-nccl"))]
    differ = {n: (v, lock[n]) for n, v in req.items()
              if n in lock and n not in ("torch", "torchvision") and v != lock[n]}  # fmt: skip
    assert differ == {}


def test_the_hardware_pages_shm_mount_is_an_empty_read_only_dir_in_the_backend_only() -> None:
    """Batt 2026-11-08: the hardware page shows /dev/shm's use. statvfs of an EMPTY directory on
    the host's /dev/shm reads the whole tmpfs; no file of it (the detect socket, rdp files) is
    exposed, and nothing may write there."""
    for name in ("compose.yaml", "compose.dev.yaml", "compose.vision-worker.yaml"):
        for svc, service in compose(name)["services"].items():
            vols = [v for v in service.get("volumes", []) if isinstance(v, str)]
            hw = [v for v in vols if v.startswith("/dev/shm/poring-lab-hwshm")]
            if svc != "backend":
                assert not hw, f"{name}: {svc} mounts the hardware page's shm dir"
    backend = compose("compose.yaml")["services"]["backend"]
    assert "/dev/shm/poring-lab-hwshm:/host-shm:ro" in backend["volumes"]
    assert backend["environment"]["HARDWARE_SHM_PATH"] == "/host-shm"
    # never the whole /dev/shm, never writable
    assert not any(v.split(":")[0] == "/dev/shm" for v in backend["volumes"] if isinstance(v, str))


def test_the_lab_servers_have_no_mvp_tombstones() -> None:
    """Batt 2026-11-08 (pilot p11's NPC-contact hard bar): the battle_conf import turns MVP
    tombstones off; the dev overlay binds it into both lab servers until the next image build."""
    tmpl = (ROOT / "services" / "rathena" / "conf" / "import" / "battle_conf.txt.tmpl").read_text()
    assert "mvp_tomb_enabled: no" in tmpl.splitlines()
    services = compose("compose.dev.yaml")["services"]
    mount = ("./services/rathena/conf/import/battle_conf.txt.tmpl:"
             "/opt/rathena-conf-templates/battle_conf.txt.tmpl:ro")  # fmt: skip
    for name in ("rathena", "rathena-th"):
        assert mount in services[name]["volumes"], name
