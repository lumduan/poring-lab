"""scripts/setup_core.py + setup_wizard.py + stream_frame.py + setup.sh (2026-11-17): the student
setup wizard's logic, with a FAKE runner -- no Docker, no Windows, no network, no rich. The .env
tests run the real init_env.sh and rotate_secrets.set_values in a temp tree, never the repo's."""

from __future__ import annotations

import importlib.util
import json
import os
import re
import shutil
import stat
import subprocess
import sys
from collections.abc import Callable, Sequence
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

import numpy as np
import pytest
import yaml

ROOT = Path(__file__).resolve().parents[3]
SCRIPTS = ROOT / "scripts"


def load(name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def core() -> ModuleType:
    return load("setup_core")


class Fake:
    """A runner: answers by the first matching command prefix, records every call."""

    def __init__(self, answers: dict[tuple[str, ...], tuple[int, str]] | None = None) -> None:
        self.answers = answers or {}
        self.calls: list[tuple[str, ...]] = []

    def __call__(
        self,
        cmd: Sequence[str],
        *,
        timeout: float | None = None,
        log: Path | None = None,
        tick: Callable[[float], None] | None = None,
    ) -> Any:
        from setup_core import Result

        call = tuple(cmd)
        self.calls.append(call)
        for prefix, (rc, out) in self.answers.items():
            if call[: len(prefix)] == prefix:
                return Result(rc, out)
        return Result(1, "")


# --- drift: the wizard's constants are the repo's -------------------------------------------------


def test_the_constants_match_their_sources(core: ModuleType) -> None:
    cb = load("capture_backend")
    assert core.SUNSHINE_TCP == cb.SUNSHINE_PORTS  # what pair / to-console test
    from poring_packets import capture

    # ADR-0026: no fixed game PC -- the shipped set names this install's WIN_HOST by token, and
    # the sniffer follows WIN_HOST (capture.bpf_program; its committed address is a template only)
    assert capture.bpf_program("10.0.5.31")[3][3] != capture.bpf_program("10.0.5.32")[3][3]
    seed = yaml.safe_load((ROOT / "config" / "environments.yaml").read_text())
    lab = next(e for e in seed["environments"] if e["id"] == "lab-rathena")
    assert lab["windows_host"] == "${WIN_HOST}"  # the interlock's shipped seed


def test_every_published_lab_port_is_refused_for_the_console(core: ModuleType) -> None:
    # the compose ports are ${KEY:-default} since ADR-0026: read with their defaults (lab_env)
    text = re.sub(r"\$\{([A-Z_]+_PORT):-(\d+)\}", r"\2", (ROOT / "compose.yaml").read_text())
    services = yaml.safe_load(text)["services"]
    published = set()
    for name, spec in services.items():
        for port in (spec or {}).get("ports", []):
            host = re.sub(r"^\$\{HOST_LAN_IP:[?-]\}:", "", str(port)).split(":")[0]
            if name != "frontend" and host.isdigit():
                published.add(int(host))
    assert published and published <= set(core.LAB_PORTS), published - set(core.LAB_PORTS)
    assert core.DEFAULT_CONSOLE_PORT not in core.LAB_PORTS
    # another install's own ports are refused for its console, the defaults then free
    other = core.install_ports({"RATHENA_LOGIN_PORT": "7900", "BACKEND_PORT": "9000"})
    assert {7900, 9000} <= set(other) and 6900 not in other and 8000 not in other
    assert "login server" in core.port_problem(7900, other) and core.port_problem(6900, other) == ""


# --- 1. the server address ------------------------------------------------------------------------

IP_ROUTE_GET = "1.1.1.1 via 192.168.50.1 dev eno1 src 192.168.50.10 uid 1000\n    cache\n"
IP_ADDR = """1: lo    inet 127.0.0.1/8 scope host lo\\       valid_lft forever
2: eno1    inet 192.168.50.10/24 brd 192.168.50.255 scope global dynamic eno1
3: wlp2s0    inet 10.0.0.7/24 brd 10.0.0.255 scope global wlp2s0
4: docker0    inet 10.209.255.1/24 brd 10.209.255.255 scope global docker0
5: br-1a2b    inet 10.210.96.1/24 brd 10.210.96.255 scope global br-1a2b
"""


def test_the_default_route_and_the_host_addresses(core: ModuleType) -> None:
    fake = Fake(
        {("ip", "-4", "route", "get"): (0, IP_ROUTE_GET), ("ip", "-4", "-o", "addr"): (0, IP_ADDR)}
    )
    assert core.default_route_ip(fake) == "192.168.50.10"
    addrs = core.host_addrs(fake)
    assert [(a.ifname, a.ip, a.prefix) for a in addrs] == [
        ("eno1", "192.168.50.10", 24),
        ("wlp2s0", "10.0.0.7", 24),
    ]
    assert core.default_route_ip(Fake()) is None  # no route: nothing guessed


@pytest.mark.parametrize(
    ("ip", "fragment"),
    [
        ("192.168.50.10", ""),
        ("10.0.0.7", ""),
        ("not-an-ip", "not an IPv4"),
        ("127.0.0.1", "not a LAN address"),
        ("169.254.1.2", "not a LAN address"),
        ("8.8.8.8", "public"),
        ("10.210.96.1", "Docker's own ranges"),
        ("192.168.50.99", "not an address of this machine"),
    ],
)
def test_server_ip_validation(core: ModuleType, ip: str, fragment: str) -> None:
    addrs = [
        core.Addr("eno1", "192.168.50.10", 24),
        core.Addr("wlp2s0", "10.0.0.7", 24),
        core.Addr("x", "10.210.96.1", 24),
    ]
    why = core.server_ip_problem(ip, addrs)
    assert (why == "") if not fragment else (fragment in why), why


# --- 2. the console port --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "ok", "fragment"),
    [
        ("3000", True, ""),
        ("3100", True, ""),
        ("80", False, "privileged"),
        ("70000", False, "outside"),
        ("8000", False, "backend"),
        ("6900", False, "login"),
        ("8888", False, "web-server"),
        ("abc", False, "not a number"),
    ],
)
def test_console_port_rules(core: ModuleType, text: str, ok: bool, fragment: str) -> None:
    port, why = core.parse_port(text)
    assert (why == "") is ok and fragment in why


def test_port_verdict_binds_and_recognises_our_own_console(core: ModuleType) -> None:
    ip = "192.168.50.10"
    assert core.port_verdict(ip, 3000, binder=lambda i, p: "free")[0]
    ours = core.port_verdict(ip, 3000, binder=lambda i, p: "in-use", fetch=lambda u: True)
    assert ours == (True, f"{ip}:3000 already serves this lab's console")
    other = core.port_verdict(ip, 3000, binder=lambda i, p: "in-use", fetch=lambda u: False)
    assert not other[0] and "another program" in other[1]
    assert not core.port_verdict(ip, 8000, binder=lambda i, p: "free")[0]  # never even bound
    # ADR-0026: with this copy's own ports known, ANOTHER copy's console is not ours
    other_copy = core.port_verdict(ip, 3000, binder=lambda i, p: "in-use", fetch=lambda u: True,
                                   held=set())  # fmt: skip
    assert not other_copy[0] and "another program" in other_copy[1]
    assert core.port_verdict(ip, 3000, binder=lambda i, p: "in-use", held={3000})[0]


def test_bind_state_is_a_real_bind(core: ModuleType) -> None:
    import socket

    holder = socket.socket()
    holder.bind(("127.0.0.1", 0))
    holder.listen()
    port = holder.getsockname()[1]
    try:
        assert core.bind_state("127.0.0.1", port) == "in-use"
    finally:
        holder.close()
    assert core.bind_state("127.0.0.1", port) == "free"


# --- 3. the Windows PC ----------------------------------------------------------------------------


def test_windows_address_rules(core: ModuleType) -> None:
    addrs = [core.Addr("eno1", "192.168.50.10", 24)]
    server = "192.168.50.10"
    assert "THIS server" in core.win_ip_problems(server, server, addrs)[0]
    assert "not a private" in core.win_ip_problems("8.8.8.8", server, addrs)[0]
    err, warnings = core.win_ip_problems("192.168.50.20", server, addrs)
    # ADR-0026 (Batt 2026-11-17, "don't lock an IP"): any game PC on the LAN, no fixed address
    assert err == "" and warnings == []
    assert not hasattr(core, "LAB_WIN_HOST") and not hasattr(core, "BOT_PC_LIMIT")
    err, warnings = core.win_ip_problems("10.1.1.5", server, addrs)
    assert err == "" and any("not on this server's subnet" in w for w in warnings)
    lab_addrs = [core.Addr("eno1", "192.168.1.228", 24)]
    assert core.win_ip_problems("192.168.1.169", "192.168.1.228", lab_addrs) == ("", [])


def test_sunshine_probe_reports_each_tcp_port(core: ModuleType) -> None:
    seen: list[tuple[str, int]] = []

    def connect(ip: str, port: int) -> bool:
        seen.append((ip, port))
        return port != 48010

    assert core.probe_sunshine("192.168.50.20", connect) == {47984: True, 47989: True, 48010: False}
    assert [p for _, p in seen] == [47984, 47989, 48010]


# --- 0. pre-flight --------------------------------------------------------------------------------


def sysfs(
    tmp: Path, vendors: dict[str, str], *, nvidia_proc: bool = False, render: bool = True
) -> Path:
    for card, vendor in vendors.items():
        dev = tmp / "sys/class/drm" / card / "device"
        dev.mkdir(parents=True)
        (dev / "vendor").write_text(vendor + "\n")
    (tmp / "sys/class/drm/card0-HDMI-A-1").mkdir(parents=True, exist_ok=True)  # a connector
    if nvidia_proc:
        (tmp / "proc/driver/nvidia").mkdir(parents=True)
        (tmp / "proc/driver/nvidia/version").write_text("NVRM 580\n")
    (tmp / "dev/dri").mkdir(parents=True)
    if render:
        (tmp / "dev/dri/renderD128").write_text("")
    return tmp


@pytest.mark.parametrize(
    ("vendors", "proc", "vendor", "profile"),
    [
        ({"card0": "0x8086"}, False, "intel", "dedicated-intel"),
        ({"card0": "0x8086", "card1": "0x10de"}, False, "nvidia", "dedicated-nvidia"),
        ({"card0": "0x8086"}, True, "nvidia", "dedicated-nvidia"),
        ({}, False, "none", "dedicated-cpu"),  # ADR-0022 Amendment 2026-11-17
        ({"card0": "0x1002"}, False, "amd", "dedicated-cpu"),
    ],
)
def test_gpu_detection_and_the_default_profile(
    core: ModuleType, tmp_path: Path, vendors: dict[str, str], proc: bool, vendor: str, profile: str
) -> None:
    gpu = core.detect_gpu(sysfs(tmp_path, vendors, nvidia_proc=proc))
    assert gpu.vendor == vendor and core.default_profile(gpu) == profile
    assert core.default_profile(gpu) != "shared-nvidia"  # never the default


@pytest.mark.parametrize(
    ("which", "rc", "out", "status", "blocking", "fragment"),
    [
        (None, 0, "", "fail", True, "Install Docker AFTER"),
        (
            "/usr/bin/docker",
            1,
            "permission denied while trying to connect",
            "fail",
            True,
            "usermod -aG docker",
        ),
        (
            "/usr/bin/docker",
            1,
            "Cannot connect to the Docker daemon",
            "fail",
            True,
            "systemctl start docker",
        ),
    ],
)
def test_docker_checks(
    core: ModuleType,
    which: str | None,
    rc: int,
    out: str,
    status: str,
    blocking: bool,
    fragment: str,
) -> None:
    checks = core.check_docker(Fake({("docker", "info"): (rc, out)}), lambda n: which)
    assert checks[0].status == status and checks[0].blocking is blocking
    assert fragment in checks[0].fix


def test_a_null_address_pool_stops_the_wizard(core: ModuleType) -> None:
    checks = core.check_docker(Fake({("docker", "info"): (0, "null\n")}), lambda n: "docker")
    pool = next(c for c in checks if c.key == "pool")
    assert pool.status == "fail" and pool.blocking and "section 1.1" in pool.fix
    good = '[{"Base":"10.210.0.0/16","Size":24}]\n'
    checks = core.check_docker(Fake({("docker", "info"): (0, good)}), lambda n: "docker")
    assert [c.status for c in checks] == ["ok", "ok"] and "10.210.0.0/16" in checks[1].detail
    assert not core.blocking(checks)


def test_a_bridge_on_a_lan_range_is_flagged(core: ModuleType) -> None:
    bad = "default via 192.168.1.1 dev eno1\n192.168.96.0/20 dev br-77 proto kernel scope link\n"
    assert core.check_bridges(Fake({("ip", "-4", "route"): (0, bad)})).status == "fail"
    good = "default via 192.168.1.1 dev eno1\n10.210.96.0/24 dev br-77 proto kernel\n"
    assert core.check_bridges(Fake({("ip", "-4", "route"): (0, good)})).status == "ok"


@pytest.mark.parametrize(
    ("linger", "conf", "status"),
    [
        ("Linger=yes", "[Login]\nRemoveIPC=no\n", "ok"),
        ("Linger=yes", "", "warn"),
        ("Linger=no", "RemoveIPC=yes\nRemoveIPC=no\n", "warn"),
        ("Linger=no", "", "warn"),
    ],
)
def test_shm_kept_at_logout(core: ModuleType, linger: str, conf: str, status: str) -> None:
    fake = Fake({("loginctl",): (0, linger + "\n"), ("systemd-analyze",): (0, conf)})
    check = core.check_shm(fake, "student")
    assert check.status == status and (status == "ok" or "section 1.3" in check.fix)


def test_disk_and_ram_thresholds(core: ModuleType, tmp_path: Path) -> None:
    def usage(gb: float) -> Callable[[Path], Any]:
        return lambda p: SimpleNamespace(free=gb * 1e9)

    assert core.check_disk(tmp_path, False, usage(20)).status == "fail"
    assert core.check_disk(tmp_path, False, usage(30)).status == "warn"
    assert core.check_disk(tmp_path, True, usage(30)).status == "fail"  # + the vision image
    assert core.check_disk(tmp_path, False, usage(100)).status == "ok"
    assert [core.check_ram(g).status for g in (None, 4.0, 11.5, 15.0)] == [
        "warn",
        "fail",
        "warn",
        "ok",
    ]


def test_preflight_stops_off_linux_and_runs_read_only_commands(
    core: ModuleType, tmp_path: Path
) -> None:
    checks, _ = core.preflight(Fake(), platform="darwin")
    assert core.blocking(checks)[0].key == "linux"
    fake = Fake(
        {
            ("docker", "info"): (0, '[{"Base":"10.210.0.0/16","Size":24}]'),
            ("ip", "-4", "route"): (0, "default via 192.168.50.1 dev eno1\n"),
        }
    )
    (tmp_path / "etc").mkdir()
    (tmp_path / "etc/os-release").write_text('ID=ubuntu\nVERSION_ID="26.04"\nPRETTY_NAME="U"\n')
    checks, gpu = core.preflight(
        fake,
        root=sysfs(tmp_path, {"card0": "0x8086"}),
        repo=tmp_path,
        user="student",
        uid=1000,
        which=lambda n: "/usr/bin/docker",
    )
    assert not core.blocking(checks) and gpu.vendor == "intel"
    verbs = {c[0] for c in fake.calls}
    assert verbs <= {"docker", "ip", "loginctl", "systemd-analyze"}
    # read-only docker only: info, and (ADR-0026) the project's owners and the networks' subnets
    allowed = {("docker", "info"), ("docker", "ps"), ("docker", "network")}
    assert all(c[:2] in allowed for c in fake.calls if c[0] == "docker")
    assert all(c[2] in ("ls", "inspect") for c in fake.calls if c[:2] == ("docker", "network"))


# --- 4. .env --------------------------------------------------------------------------------------

SECRET_NAMES = (
    "DB_PASSWORD",
    "DB_ROOT_PASSWORD",
    "RATHENA_SERVER_USER",
    "RATHENA_SERVER_PASSWORD",
    "RATHENA_TEST_PASSWORD",
    "RATHENA_AGENT_PASSWORD",
    "RATHENA_GM_PASSWORD",
)


def test_shown_never_reveals_a_secret(core: ModuleType) -> None:
    for name in (*SECRET_NAMES, "RDP_USER", "RDP_PASSWORD", "WIN_LAB_PASSWORD", "ANYTHING_NEW"):
        assert core.shown(name, "s3cr3t-value") == "set (hidden)"
        assert core.shown(name, "") == "(empty)"
    assert core.shown("HOST_LAN_IP", "192.168.50.10") == "192.168.50.10"
    assert core.shown("WIN_HOST", None) == "(absent)"
    assert not (core.SAFE_KEYS & set(SECRET_NAMES))
    assert not any(h in k for k in core.SAFE_KEYS for h in ("PASSWORD", "SECRET", "TOKEN", "_USER"))


def answers(core: ModuleType, **kw: Any) -> Any:
    base = {
        "server_ip": "192.168.50.10",
        "console_port": 3100,
        "win_ip": "192.168.50.20",
        "profile": "dedicated-intel",
    }
    return core.Answers(**{**base, **kw})


def test_the_planned_settings(core: ModuleType, tmp_path: Path) -> None:
    plan = core.planned_env(answers(core), {}, gid=991, home=tmp_path)
    assert plan == {
        "HOST_LAN_IP": "192.168.50.10",
        "CONSOLE_PORT": "3100",
        "WIN_HOST": "192.168.50.20",
        "LAB_HOST_PROFILE": "dedicated-intel",
        "RATHENA_WEB_SERVER": "true",
        "S2_REC_DIR": str(tmp_path / "poring-lab-rec/.s2-h264"),
        "RENDER_GID": "991",
        "VISION_MAX_VRAM_FRACTION": "1.0",
        "LAB_STORE_DIR": str(tmp_path / "poring-lab-store"),  # ADR-0026: always written
    }
    shared = core.planned_env(answers(core, profile="shared-nvidia"), {}, gid=None, home=tmp_path)
    assert "VISION_MAX_VRAM_FRACTION" not in shared and "RENDER_GID" not in shared
    kept = core.planned_env(answers(core), {"S2_REC_DIR": "/srv/rec"}, gid=None, home=tmp_path)
    assert kept["S2_REC_DIR"] == "/srv/rec"
    explicit = {"FRONTEND_ORIGINS": "http://localhost:3000"}
    plan = core.planned_env(answers(core), explicit, gid=None, home=tmp_path)
    assert plan["FRONTEND_ORIGINS"] == "http://localhost:3000,http://192.168.50.10:3100"
    listed = {"FRONTEND_ORIGINS": "http://192.168.50.10:3100/"}
    assert "FRONTEND_ORIGINS" not in core.planned_env(
        answers(core), listed, gid=None, home=tmp_path
    )
    assert "FRONTEND_ORIGINS" not in core.planned_env(answers(core), {}, gid=None, home=tmp_path)
    assert not any(k.startswith(("RDP_", "WIN_LAB")) for k in plan)  # RDP is never written


def test_the_planned_install_values(core: ModuleType, tmp_path: Path) -> None:
    """ADR-0026: a name, ports, subnets, the browsers' LAN and the worker's memory are written only
    when they differ from the defaults; an existing store and worker memory are kept."""
    a = answers(core)
    a.project, a.store_dir, a.viewer_net, a.worker_mem = "lab2", "/srv/store", "10.0.5.0/24", "9g"
    a.ports = {"RATHENA_LOGIN_PORT": 7900}
    a.nets = {"LAB_NET_PREFIX": "10.210.98", "LAB_AGENT_NET_PREFIX": "10.210.99"}
    plan = core.planned_env(a, {}, gid=None, home=tmp_path)
    assert {k: plan[k] for k in ("COMPOSE_PROJECT_NAME", "LAB_STORE_DIR", "RATHENA_LOGIN_PORT",
                                 "LAB_NET_PREFIX", "LAB_AGENT_NET_PREFIX", "VIEWER_NETWORKS",
                                 "VISION_WORKER_MEM")} == {  # fmt: skip
        "COMPOSE_PROJECT_NAME": "lab2", "LAB_STORE_DIR": "/srv/store", "RATHENA_LOGIN_PORT": "7900",
        "LAB_NET_PREFIX": "10.210.98", "LAB_AGENT_NET_PREFIX": "10.210.99",
        "VIEWER_NETWORKS": "10.0.5.0/24", "VISION_WORKER_MEM": "9g",
    }  # fmt: skip
    current = {"LAB_STORE_DIR": "/mnt/nas", "VISION_WORKER_MEM": "11g"}
    kept = core.planned_env(answers(core), current, gid=None, home=tmp_path)
    assert kept["LAB_STORE_DIR"] == "/mnt/nas" and "VISION_WORKER_MEM" not in kept
    default = core.planned_env(answers(core), {}, gid=None, home=tmp_path)
    assert "COMPOSE_PROJECT_NAME" not in default and "VIEWER_NETWORKS" not in default
    a2 = answers(core)
    a2.project = "poring-lab"  # the default is never written
    assert "COMPOSE_PROJECT_NAME" not in core.planned_env(a2, {}, gid=None, home=tmp_path)


def tree(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    (repo / "scripts").mkdir(parents=True)
    shutil.copy(SCRIPTS / "init_env.sh", repo / "scripts" / "init_env.sh")
    shutil.copy(ROOT / ".env.example", repo / ".env.example")
    return repo


def real(cmd: Sequence[str], **kw: Any) -> Any:
    from setup_core import Result

    proc = subprocess.run(list(cmd), capture_output=True, text=True, check=False)
    return Result(proc.returncode, proc.stdout + proc.stderr)


def test_a_new_env_gets_random_secrets_and_the_answers(core: ModuleType, tmp_path: Path) -> None:
    repo = tree(tmp_path)
    created, changes = core.write_env(repo, answers(core), real, gid=991, home=tmp_path)
    env = core.read_env(repo / ".env")
    assert created and stat.S_IMODE((repo / ".env").stat().st_mode) == 0o600
    for name in SECRET_NAMES:
        assert len(env[name]) >= 8, name  # init_env.sh's random values
    assert (env["HOST_LAN_IP"], env["CONSOLE_PORT"], env["WIN_HOST"]) == (
        "192.168.50.10",
        "3100",
        "192.168.50.20",
    )
    assert env["RDP_USER"] == env["RDP_PASSWORD"] == ""  # Sunshine only: RDP stays off
    assert (tmp_path / "poring-lab-rec/.s2-h264").is_dir()
    second = core.write_env(tree(tmp_path / "b"), answers(core), real, gid=991, home=tmp_path)
    assert core.read_env(tmp_path / "b/repo/.env")["DB_PASSWORD"] != env["DB_PASSWORD"]
    assert second[0] is True


def test_an_existing_env_keeps_every_secret_and_changes_only_what_changed(
    core: ModuleType, tmp_path: Path
) -> None:
    repo = tree(tmp_path)
    core.write_env(repo, answers(core), real, gid=991, home=tmp_path)
    before = (repo / ".env").read_text()
    secrets_before = {k: core.read_env(repo / ".env")[k] for k in SECRET_NAMES}
    created, changes = core.write_env(repo, answers(core), real, gid=991, home=tmp_path)
    assert (created, changes) == (False, []) and (repo / ".env").read_text() == before
    created, changes = core.write_env(
        repo, answers(core, console_port=3200), real, gid=991, home=tmp_path
    )
    assert not created and [k for k, _, _ in changes] == ["CONSOLE_PORT"]
    env = core.read_env(repo / ".env")
    assert {k: env[k] for k in SECRET_NAMES} == secrets_before
    diff = [ln for ln in (repo / ".env").read_text().splitlines() if ln not in before.splitlines()]
    assert diff == ["CONSOLE_PORT=3200"]


def test_write_env_never_hands_a_secret_name_to_set(core: ModuleType, tmp_path: Path) -> None:
    repo = tree(tmp_path)
    seen: list[str] = []

    def spy(pairs: list[str], path: Path) -> list[str]:
        seen.extend(pairs)
        return core.default_set_values(pairs, path)

    core.write_env(repo, answers(core), real, gid=991, home=tmp_path, set_values=spy)
    rotate = load("rotate_secrets")
    names = [p.split("=", 1)[0] for p in seen]
    assert names and not any(n in rotate.GENERATORS for n in names)
    assert not any(h in n.upper() for n in names for h in rotate.SECRET_HINTS)


def test_init_env_failure_is_reported(core: ModuleType, tmp_path: Path) -> None:
    repo = tmp_path / "empty"
    repo.mkdir()
    with pytest.raises(core.SetupError, match="init_env.sh failed"):
        core.write_env(repo, answers(core), Fake(), gid=None, home=tmp_path)


def test_rdp_detection_follows_rdp_loop(core: ModuleType) -> None:
    assert not core.rdp_configured({"WIN_HOST": "w", "RDP_USER": "", "RDP_PASSWORD": ""})
    assert core.rdp_configured({"WIN_HOST": "w", "RDP_USER": "u", "RDP_PASSWORD": "p"})
    assert core.rdp_credentials_set({"RDP_USER": "u"}) and not core.rdp_credentials_set({})


# --- 5. the install -------------------------------------------------------------------------------

MANUAL_ORDER = [
    "build:rathena",
    "pull:db",
    "build:backend",
    "build:desktop",
    "target:rathena:build:poring-lab/rathena-build:local",
    "tables",
    "scripts/gen_mapcache.py",
    "build:sniffer",
    "build:gamestream",
    "scripts/detector_setup.py",  # ADR-0026: the CPU detector + the starter model v1
    "start:db@120",
    "start:rathena@240",
    "scripts/smoke_test.sh",
    "scripts/capture_backend.py",
    "start:backend,desktop@90",
    "start:sniffer@120",
    "start:frontend-dev@120",
    "start:gamestream@60",
]


def key(step: Any) -> str:
    return step.cmd[2] if step.cmd[1] == "scripts/guarded_build.py" else step.cmd[1]


def test_the_install_follows_the_manual_one_guarded_step_at_a_time(
    core: ModuleType, tmp_path: Path
) -> None:
    steps = core.install_plan(tmp_path, {}, answers(core))
    assert [key(s) for s in steps] == MANUAL_ORDER
    for s in steps:
        assert s.cmd[1] in (
            "scripts/guarded_build.py",
            "scripts/gen_mapcache.py",
            "scripts/smoke_test.sh",
            "scripts/capture_backend.py",
            "scripts/detector_setup.py",
        ), s.cmd
        assert Path(s.cmd[0]).name != "docker" and not key(s).startswith("up:"), s.cmd
        assert s.fix and not s.optional
    lock = next(s for s in steps if s.cmd[1] == "scripts/capture_backend.py")
    assert lock.cmd[2:] == ("init",)  # rdp/steady: nothing streams until the pairing
    vision = core.install_plan(tmp_path, {}, answers(core, build_vision=True))
    extra = [s for s in vision if key(s) == "build:vision"]
    assert len(extra) == 1 and extra[0].optional
    assert [key(s) for s in vision if s.optional] == ["build:vision"]


def test_a_changed_setting_recreates_only_the_running_services_it_reaches(
    core: ModuleType,
) -> None:
    running = Fake({("docker", "inspect"): (0, "running healthy\n")})
    port = [("CONSOLE_PORT", "3000", "3100")]
    assert core.services_to_recreate(port, running) == ["backend", "frontend-dev"]
    assert core.services_to_recreate(port, Fake()) == []  # a fresh install creates them anyway
    win = [("WIN_HOST", None, "192.168.50.20"), ("LAB_HOST_PROFILE", None, "dedicated-intel")]
    assert core.services_to_recreate(win, running) == ["backend", "desktop", "gamestream"]
    steps = core.recreate_steps(["rathena", "backend", "desktop", "frontend-dev", "gamestream"])
    assert [s.cmd[2] for s in steps] == [
        "recreate:rathena@240",
        "recreate:sniffer@120",
        "recreate:backend,desktop@90",
        "recreate:frontend-dev@120",
        "recreate:gamestream@60",
    ]
    assert [s.cmd[2] for s in core.recreate_steps(["backend"])] == ["recreate:backend@30"]
    assert all(s.cmd[1] == "scripts/guarded_build.py" and s.done is None for s in steps)
    assert core.RECREATE_DONE["recreate-sniffer"] == ("rathena",)  # settled only after its sniffer


def test_the_rathena_image_tag_follows_env(core: ModuleType, tmp_path: Path) -> None:
    steps = core.install_plan(
        tmp_path, {"PACKETVER": "20200401", "RATHENA_PRERE": "yes"}, answers(core)
    )
    fake = Fake({("docker", "image", "inspect"): (0, "sha256:x")})
    assert steps[0].done(fake)
    assert fake.calls[-1][-1] == "poring-lab/rathena:pv20200401-prere-yes"


@pytest.mark.parametrize(
    ("state", "up"),
    [
        ("running healthy", True),
        ("running none", True),
        ("running unhealthy", False),
        ("running starting", False),
        ("exited none", False),
    ],
)
def test_service_done_checks(core: ModuleType, state: str, up: bool) -> None:
    fake = Fake({("docker", "inspect"): (0, state + "\n")})
    assert core.services_up("backend", "desktop")(fake) is up
    assert fake.calls[0][-1] == "poring-lab-backend-1"
    assert core.services_up("db")(Fake()) is False  # absent


def test_file_and_lock_done_checks(core: ModuleType, tmp_path: Path) -> None:
    assert not core.lock_present(tmp_path)(Fake())
    (tmp_path / "state").mkdir()
    (tmp_path / "state/capture-backend").write_text("BACKEND=rdp\nSEQ=1\nPHASE=steady\n")
    assert core.lock_present(tmp_path)(Fake())
    f = tmp_path / "x.json"
    assert not core.files_present(f)(Fake())
    f.write_text("{}")
    assert core.files_present(f)(Fake())


def test_run_process_logs_everything_and_returns_the_tail(core: ModuleType, tmp_path: Path) -> None:
    log = tmp_path / "logs" / "01-x.log"
    ticks: list[float] = []
    res = core.run_process(
        ["sh", "-c", "echo one; sleep 0.7; echo two >&2; exit 3"], log=log, tick=ticks.append
    )
    assert res.rc == 3 and "one" in res.out and "two" in res.out and ticks
    text = log.read_text()
    assert "$ sh -c" in text and "=== exit 3" in text
    assert core.run_process(["sh", "-c", "sleep 5"], timeout=0.6, log=log).rc == 124
    assert core.run_process(["no-such-command-xyz"]).rc == 127
    assert core.run_process(["no-such-command-xyz"], log=log).rc == 127


# --- 6. pairing / 7. the stream -------------------------------------------------------------------


def test_pins_and_the_pair_command(core: ModuleType) -> None:
    pins = {core.new_pin() for _ in range(200)}
    assert all(re.fullmatch(r"\d{4}", p) for p in pins) and len(pins) > 100
    assert core.pair_cmd("0420")[1:] == ("scripts/capture_backend.py", "pair", "0420")
    with pytest.raises(core.SetupError):
        core.pair_cmd("12a4")


@pytest.mark.parametrize(
    ("rc", "state"),
    [(0, "paired"), (1, "not paired"), (2, "gamestream not running"), (9, "unknown")],
)
def test_paired_state(core: ModuleType, rc: int, state: str) -> None:
    fake = Fake({(core.PY, "scripts/capture_backend.py", "paired"): (rc, "")})
    assert core.paired_state(fake) == state


def frame(**kw: Any) -> dict[str, Any]:
    return {
        "path": "/dev/shm/x.png",
        "width": 1440,
        "height": 900,
        "source": "bus",
        "frame_id": 812,
        "age_ms": 31.0,
        "advanced": True,
        "dark_fraction": 0.12,
        **kw,
    }


def test_judging_the_grabbed_frame(core: ModuleType) -> None:
    assert core.judge_frame(frame()) == []
    assert "not the S2 frame bus" in core.judge_frame(frame(source="x11"))[0]
    assert "black" in core.judge_frame(frame(dark_fraction=0.995))[0]
    assert "SESSION_SIZE" in core.judge_frame(frame(width=1280))[0]
    assert core.judge_frame(frame(width=1280, height=800), (1280, 800)) == []
    assert core.session_size("") == core.session_size("bogus") == (1440, 900)
    assert core.session_size("1280x800") == (1280, 800)
    text = "noise\n" + json.dumps(frame()) + "\n"
    assert core.parse_frame_report(text)["frame_id"] == 812
    with pytest.raises(core.SetupError):
        core.parse_frame_report("Traceback ...")


def test_the_stream_steps_use_the_existing_writers(core: ModuleType, tmp_path: Path) -> None:
    assert core.stream_on_cmd()[1:] == (
        "scripts/capture_backend.py",
        "to-console",
        "--sunshine-only",
    )
    out = tmp_path / "f.png"
    assert core.frame_cmd(out)[1:] == ("scripts/stream_frame.py", "--out", str(out))
    assert str(core.SCRATCH).startswith("/dev/shm/")  # rule 7: logs and the picture in RAM
    (tmp_path / "state").mkdir()
    (tmp_path / "state/capture-backend").write_text(
        "BACKEND=console\nSEQ=4\nPHASE=steady\nREASON=sunshine-only\n"
    )
    assert core.lock_now(tmp_path)["REASON"] == "sunshine-only"


def test_the_stream_frame_report(tmp_path: Path) -> None:
    sf = load("stream_frame")
    black = np.zeros((900, 1440, 4), np.uint8)
    lit = black.copy()
    lit[:450, :, :3] = 200
    rep = sf.report(tmp_path / "f.png", (10, black, 5, "bus"), (20, lit, 9, "bus"), 50_000_000)
    assert (rep["width"], rep["height"], rep["source"], rep["frame_id"]) == (1440, 900, "bus", 9)
    assert rep["advanced"] and rep["dark_fraction"] == 0.5 and rep["age_ms"] == 50.0
    same = sf.report(tmp_path / "f.png", (10, lit, 9, "bus"), (10, lit, 9, "bus"), 10)
    assert not same["advanced"]
    xs = sf.report(tmp_path / "f.png", (10, lit, -1, "x11"), (20, black, -1, "x11"), 30)
    assert xs["advanced"] and xs["source"] == "x11"


# --- progress, --check, --dry-run -----------------------------------------------------------------


def test_progress_is_atomic_private_and_versioned(core: ModuleType, tmp_path: Path) -> None:
    path = tmp_path / ".setup" / "progress.json"
    core.save_progress({"screen": "install", "answers": {"server_ip": "192.168.50.10"}}, path)
    assert stat.S_IMODE(path.stat().st_mode) == 0o600 and not list(path.parent.glob("*.tmp"))
    assert core.load_progress(path)["screen"] == "install"
    path.write_text(json.dumps({"version": 99, "screen": "x"}))
    assert core.load_progress(path) == {}
    path.write_text("{broken")
    assert core.load_progress(path) == {}
    assert core.Answers.from_dict({"server_ip": "a", "junk": 1}).server_ip == "a"


def test_the_progress_file_is_gitignored_and_never_in_settings_or_state(core: ModuleType) -> None:
    rel = core.PROGRESS.relative_to(core.REPO)
    assert rel.parts[0] not in ("settings", "state", "data")
    res = subprocess.run(["git", "-C", str(ROOT), "check-ignore", "-q", str(rel)], check=False)
    assert res.returncode == 0, f"{rel} must be gitignored"


def lab_env(path: Path) -> Path:
    path.write_text(
        "HOST_LAN_IP=192.168.50.10\nCONSOLE_PORT=3100\nWIN_HOST=192.168.50.20\n"
        "LAB_HOST_PROFILE=dedicated-intel\nDB_PASSWORD=TOPSECRETdb\nRATHENA_GM_USER=val_SECRET\n"
        "RDP_USER=\nRDP_PASSWORD=\n"
    )
    return path


def test_check_is_read_only_masks_secrets_and_can_skip_container_probes(
    core: ModuleType, tmp_path: Path
) -> None:
    lab_env(tmp_path / ".env")
    fake = Fake(
        {
            ("docker", "info"): (0, '[{"Base":"10.210.0.0/16","Size":24}]'),
            ("docker", "ps"): (0, "backend\tUp 2 hours (healthy)\ndb\tUp 2 hours\n"),
        }
    )
    rep = core.run_check(
        fake,
        tmp_path,
        exec_ok=False,
        root=tmp_path,
        connect=lambda ip, port: True,
        fetch=lambda url: False,
    )
    text = core.format_check(rep)
    assert "TOPSECRET" not in text and "val_SECRET" not in text
    assert dict(rep.env)["DB_PASSWORD"] == "set (hidden)"
    assert dict(rep.env)["CONSOLE_PORT"] == "3100"
    assert not any("paired" in c for call in fake.calls for c in call)  # --no-exec honoured
    assert all(call[0] in ("docker", "ip", "loginctl", "systemd-analyze") for call in fake.calls)
    assert all(call[1] in ("info", "ps", "network") for call in fake.calls if call[0] == "docker")
    assert all(
        call[2] in ("ls", "inspect") for call in fake.calls if call[:2] == ("docker", "network")
    )
    status = {c.key: c for c in rep.status}
    assert status["sunshine"].status == "ok" and status["svc-backend"].status == "ok"
    assert status["svc-gamestream"].status == "warn" and "Sunshine only" in status["path"].detail
    closed = core.run_check(
        fake,
        tmp_path,
        exec_ok=True,
        root=tmp_path,
        connect=lambda ip, port: False,
        fetch=lambda url: False,
    )
    assert {c.key: c for c in closed.status}["sunshine"].status == "fail"
    assert any(call[1:3] == ("scripts/capture_backend.py", "paired") for call in fake.calls)


def test_dry_run_lists_every_step_and_no_secret(core: ModuleType, tmp_path: Path) -> None:
    env = core.read_env(lab_env(tmp_path / ".env"))
    lines = core.dry_run_lines(tmp_path, answers(core), env, gid=991, home=tmp_path)
    text = "\n".join(lines)
    assert "TOPSECRET" not in text and "init_env.sh" not in text  # .env exists: no new secrets
    for want in MANUAL_ORDER:
        assert want in text, want
    assert "to-console --sunshine-only" in text and "stream_frame.py" in text
    done = core.dry_run_lines(
        tmp_path,
        answers(core),
        env,
        gid=991,
        home=tmp_path,
        runner=Fake({("docker", "image", "inspect"): (0, "sha256:x")}),
    )
    assert "pull:db   # already done" in "\n".join(done)
    rdp = {**env, "RDP_USER": "u", "RDP_PASSWORD": "p"}
    skipped = core.dry_run_lines(tmp_path, answers(core), rdp, gid=991, home=tmp_path)
    assert "SKIPPED" in skipped[-1] and not any("pair <PIN>" in ln for ln in skipped)


# --- the wizard module and setup.sh -------------------------------------------------------------


def test_the_wizard_imports_and_dry_runs_without_rich(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setitem(sys.modules, "rich", None)  # any `import rich` raises ImportError
    wiz = load("setup_wizard")
    monkeypatch.setattr(wiz.core, "REPO", tmp_path)
    monkeypatch.setattr(wiz.core, "run_process", Fake())
    lab_env(tmp_path / ".env")
    assert wiz.main(["--dry-run", "--restart"]) == 0
    out = capsys.readouterr().out
    assert "DRY RUN" in out and "guarded_build.py build:rathena" in out and "TOPSECRET" not in out
    assert wiz.interactive({}) == 1  # no rich: says to run ./setup.sh, changes nothing
    assert list(wiz.SCREENS) == [
        "preflight",
        "server",
        "port",
        "windows",
        "storage",  # ADR-0026: where long-term files go (no NAS assumed)
        "review",
        "install",
        "pair",
        "stream",
        "done",
    ]


def test_setup_sh_asks_before_installing_uv_and_is_read_only_for_check() -> None:
    text = (ROOT / "setup.sh").read_text()
    assert os.access(ROOT / "setup.sh", os.X_OK)
    ask = text.index('read -r -p "Run that command now? [Y/n] "')
    run = text.index('sh -c "${UV_INSTALL}"')
    assert ask < run and "curl -LsSf https://astral.sh/uv/install.sh | sh" in text
    check = text.index("if $read_only; then")
    assert check < text.index("\nuv sync ||")
    assert check < text.index("\ngit config core.hooksPath .githooks\n")
    assert "exec python3 scripts/setup_wizard.py" in text
    assert "exec uv run --no-sync python scripts/setup_wizard.py" in text
    assert "sudo " not in text.replace("sudo apt-get install", "")  # never sudo by itself
    res = subprocess.run(["bash", "-n", str(ROOT / "setup.sh")], check=False)
    assert res.returncode == 0


def test_the_wizard_never_writes_the_lock_or_daemon_config() -> None:
    for name in ("setup_core.py", "setup_wizard.py", "stream_frame.py"):
        src = (SCRIPTS / name).read_text()
        assert 'daemon.json")' not in src and "write_lock" not in src, name
        assert 'capture-backend").write' not in src and "systemctl restart" not in src.replace(
            "`sudo systemctl restart docker`", ""
        ), name


# --- ADR-0026 (Batt 2026-11-17, nothing locked): names, subnets, ports, the GPU ---


def test_a_name_another_folder_uses_is_refused_and_a_free_one_offered(
    core: ModuleType, tmp_path: Path
) -> None:
    """Batt: "check first: if the name poring-lab exists, tell the user to use another name". Only
    ANOTHER folder's containers count: a re-run in the same folder finds its own."""
    fake = Fake({("docker", "ps", "-a", "--filter", "label=com.docker.compose.project=poring-lab"):
                 (0, "/home/bot/docker/poring-lab\n/home/bot/docker/poring-lab\n")})  # fmt: skip
    other = core.check_project(fake, tmp_path, "poring-lab")
    assert (
        other.status == "fail" and other.blocking and "/home/bot/docker/poring-lab" in other.detail
    )
    mine = core.check_project(fake, Path("/home/bot/docker/poring-lab"), "poring-lab")
    assert mine.status == "ok" and "this folder's" in mine.detail
    assert core.check_project(fake, tmp_path, "lab2").status == "ok"  # nobody's
    assert core.free_project_name(fake, "poring-lab", tmp_path) == "poring-lab-2"


def nets_fake(subnets: str, routes: str = "") -> Any:
    return Fake({("docker", "network", "ls"): (0, "a\nb\n"),
                 ("docker", "network", "inspect"): (0, subnets),
                 ("ip", "-4", "route"): (0, routes)})  # fmt: skip


def test_taken_subnets_get_the_first_free_pair(core: ModuleType) -> None:
    own = (
        "poring-lab_default 10.210.96.0/24\nporing-lab_agent 10.210.97.0/24\nbridge 172.17.0.0/16\n"
    )
    check, proposal = core.check_subnets(nets_fake(own), {}, "poring-lab")
    assert check.status == "ok" and proposal == {}  # this copy's own networks
    other = "poring-lab_default 10.210.96.0/24\nporing-lab_agent 10.210.97.0/24\nx 10.210.98.0/24\n"
    check, proposal = core.check_subnets(nets_fake(other), {}, "lab2")
    assert check.status == "warn" and "taken" in check.detail and not check.blocking
    assert proposal == {"LAB_NET_PREFIX": "10.210.99", "LAB_AGENT_NET_PREFIX": "10.210.100"}
    vpn = "default via 192.168.1.1 dev eno1\n10.210.96.0/22 dev wg0 scope link\n"
    check, proposal = core.check_subnets(nets_fake("", vpn), {}, "poring-lab")
    assert proposal == {"LAB_NET_PREFIX": "10.210.100", "LAB_AGENT_NET_PREFIX": "10.210.101"}


def test_busy_install_ports_get_a_free_proposal(core: ModuleType) -> None:
    busy = {6900, 6121, 8000}

    def binder(ip: str, port: int) -> str:
        return "in-use" if port in busy else "free"

    moves = core.port_moves("192.168.50.10", {}, set(), binder)
    assert moves == {"RATHENA_LOGIN_PORT": (6900, 7900), "RATHENA_CHAR_PORT": (6121, 7121),
                     "BACKEND_PORT": (8000, 9000)}  # fmt: skip
    assert core.port_moves("192.168.50.10", {}, busy, binder) == {}  # held by this copy itself
    assert core.port_moves("192.168.50.10", {"BACKEND_PORT": "8100"}, set(), binder) == {
        "RATHENA_LOGIN_PORT": (6900, 7900), "RATHENA_CHAR_PORT": (6121, 7121)}  # fmt: skip


def test_the_gpu_recommendation_comes_from_gpu_ready(core: ModuleType, tmp_path: Path) -> None:
    root = sysfs(tmp_path, {})
    (root / "proc").mkdir(exist_ok=True)
    (root / "proc/meminfo").write_text("MemTotal:       16303104 kB\n")
    rec = core.gpu_recommendation(core.Gpu("none", False), Fake(), root)
    assert (rec.profile, rec.build_vision) == ("dedicated-cpu", False)
    assert "dedicated-cpu" in core.PROFILES


def test_another_folders_networks_are_never_this_copys(core: ModuleType, tmp_path: Path) -> None:
    """A second folder whose default name belongs to the live lab: the lab's networks are TAKEN
    (found live 2026-11-17 by --check from a worktree, which called them free)."""
    fake = nets_fake("poring-lab_default 10.210.96.0/24\nporing-lab_agent 10.210.97.0/24\n")
    fake.answers[("docker", "ps", "-a")] = (0, "/home/bot/docker/poring-lab\n")
    check, proposal = core.check_subnets(fake, {}, "poring-lab", repo=tmp_path)
    assert check.status == "warn" and proposal["LAB_NET_PREFIX"] == "10.210.98"
    check, _ = core.check_subnets(fake, {}, "poring-lab", repo=Path("/home/bot/docker/poring-lab"))
    assert check.status == "ok"  # the lab's own folder
