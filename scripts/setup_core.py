"""The setup wizard's logic (2026-11-17, Batt: a student runs `./setup.sh` and nothing else).

`scripts/setup_wizard.py` draws the screens (rich); everything that decides, detects, validates,
writes or runs lives here as plain functions. Every command goes through an injectable RUNNER
(`run_process` for real, a fake in the tests), so the install, pairing and stream steps are tested
without Docker, Windows or a network. No rich import here: the unit tests do not need it.

What it never does (CLAUDE.md, the setup manual):
- prints a secret: .env values are shown only for the non-secret SAFE_KEYS, anything else as
  "set" / "empty";
- regenerates a secret: a missing .env is created by scripts/init_env.sh (its random secrets),
  an existing one only gets the settings the student confirmed, each through
  `rotate_secrets.set_values` (it refuses secret-looking names and reads every value back);
- runs sudo, edits /etc/docker/daemon.json, restarts Docker or touches the network: those are the
  student's own steps (manual section 1), shown as fixes;
- builds, starts or pairs outside `scripts/guarded_build.py` and `scripts/capture_backend.py`;
- writes the capture-backend lock itself (capture_backend.py is its only writer).

Files: the resumable progress is `.setup/progress.json` (gitignored; never settings/ or state/);
step logs and the stream-test picture go to RAM, `/dev/shm/<project>-tmp/setup/` (rule 7; the
lab: /dev/shm/poring-lab-tmp/setup/). Every Docker name is this copy's compose project's
(scripts/lab_env.py: COMPOSE_PROJECT_NAME, default poring-lab), read fresh at each use.
"""

from __future__ import annotations

import ipaddress
import json
import os
import re
import secrets
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Protocol

if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
import gpu_ready  # noqa: E402  (a sibling, stdlib only: is the GPU ready, ADR-0022 11-17)
import lab_env  # noqa: E402  (a sibling, stdlib only: this copy's compose project names)

REPO = Path(__file__).resolve().parents[1]
PROGRESS = REPO / ".setup" / "progress.json"
SCRATCH = Path(os.environ.get("SETUP_SCRATCH", str(lab_env.shm("tmp") / "setup")))
PY = sys.executable
PROGRESS_VERSION = 1

DEFAULT_CONSOLE_PORT = 3000
DEFAULT_BACKEND_PORT = 8000  # lab_env.PORTS' (the backend's host port)
PORT_MIN, PORT_MAX = 1024, 65535
# The lab's own ports on this host (docs/services-and-ports.md): published on HOST_LAN_IP, or used
# inside the compose network. The console may take none of them.
# The published ones are this install's (lab_env.PORTS, ADR-0026): LAB_PORTS holds the defaults,
# install_ports(env) a .env's own values.
PORT_NAMES = {
    "RATHENA_LOGIN_PORT": "the rAthena login server",
    "RATHENA_CHAR_PORT": "the rAthena char server",
    "RATHENA_MAP_PORT": "the rAthena map server",
    "RATHENA_WEB_PORT": "the rAthena web-server",
    "BACKEND_PORT": "the backend",
    "NOVNC_PORT": "noVNC",
}
INNER_PORTS = {8001: "the backend's internal listener", 3306: "MariaDB", 5900: "x11vnc"}


def install_ports(env: Mapping[str, str] | None = None) -> dict[int, str]:
    """Every port of this install but the console's: the published ones from ``env`` (else the
    defaults), and the ones used inside the compose network."""
    env = env or {}
    out = {int(env.get(k, "").strip() or lab_env.PORTS[k]): name for k, name in PORT_NAMES.items()}
    return {**out, **INNER_PORTS}


LAB_PORTS: dict[int, str] = install_ports()
# Sunshine on the PC (docs/console-capture-plan.md 3.3, from Sunshine's own Network settings page).
# TCP = capture_backend.SUNSHINE_PORTS (tested): what pairing and a stream start need.
SUNSHINE_TCP = (47984, 47989, 48010)
SUNSHINE_UDP = (47998, 47999, 48000)
SUNSHINE_WEB = 47990
# ➡️ No fixed game PC any more (Batt 2026-11-17, "don't lock an IP"; ADR-0026): the shipped
# environment set names ${WIN_HOST}, the sniffer follows WIN_HOST, and a person can change an
# environment's Windows PC on the Settings page (ADR-0023 decision 4). LAB_WIN_HOST is gone.
# Docker's ranges on a lab host (manual 1.1; compose pins 10.210.96/97; the default bridge).
DOCKER_NETS = tuple(
    ipaddress.ip_network(n) for n in ("10.210.0.0/16", "10.209.255.0/24", "172.17.0.0/16")
)
PROFILES = (
    "dedicated-intel", "dedicated-nvidia", "dedicated-amd", "dedicated-cpu", "shared-nvidia",
)  # fmt: skip


def project() -> str:
    """This copy's compose project (lab_env.project(): the environment, else .env, else
    poring-lab), read FRESH at each use, the way every guarded step's own process reads it."""
    return lab_env.project()


# The vision image each GPU profile builds (its overlay's `image:`); the CUDA one otherwise.
VISION_IMAGES = {"dedicated-intel": "vision-intel", "dedicated-amd": "vision-vulkan"}

# .env names whose VALUES may be shown. Everything else is shown as "set" / "empty".
SAFE_KEYS = frozenset(
    {
        "HOST_LAN_IP", "CONSOLE_PORT", "WIN_HOST", "LAB_HOST_PROFILE", "RENDER_GID",
        "VISION_MAX_VRAM_FRACTION", "RATHENA_WEB_SERVER", "S2_REC_DIR", "FRONTEND_ORIGINS",
        "PACKETVER", "RATHENA_PRERE", "VIEWER_NETWORKS", "SESSION_SIZE", "RDP_PORT",
        "COMPOSE_PROJECT_NAME", "LAB_STORE_DIR", "DETECTOR_DIR", "VISION_WORKER_MEM",
        "GPU_RENDER_NODE",
        *lab_env.PORTS, *lab_env.NETS,
    }
)  # fmt: skip
CHECK_KEYS = (
    "HOST_LAN_IP", "CONSOLE_PORT", "WIN_HOST", "LAB_HOST_PROFILE", "RENDER_GID",
    "VISION_MAX_VRAM_FRACTION", "RATHENA_WEB_SERVER", "S2_REC_DIR", "FRONTEND_ORIGINS",
    "DB_PASSWORD", "DB_ROOT_PASSWORD", "RATHENA_SERVER_USER", "RATHENA_SERVER_PASSWORD",
    "RATHENA_AGENT_USER", "RATHENA_GM_USER", "RDP_USER", "RDP_PASSWORD",
    "COMPOSE_PROJECT_NAME", "LAB_STORE_DIR", "VIEWER_NETWORKS", "VISION_WORKER_MEM",
    "GPU_RENDER_NODE",
)  # fmt: skip


class SetupError(Exception):
    """A step that cannot go on; the message is for the student (never a secret)."""


# --- the command runner ---------------------------------------------------------------------------


# The backend's default VIEWER_NETWORKS (poring_backend.config.PRIVATE_NETWORKS; parity-tested):
# every private range, so a LAN of any numbering and a VPN can use the console (Batt 2026-11-19)
PRIVATE_NETWORKS = "10.0.0.0/8,172.16.0.0/12,192.168.0.0/16,100.64.0.0/10,fc00::/7"


@dataclass(frozen=True)
class Result:
    rc: int
    out: str  # stdout + stderr; the TAIL when the output went to a log file

    @property
    def ok(self) -> bool:
        return self.rc == 0


Tick = Callable[[float], None]


class Runner(Protocol):
    def __call__(
        self,
        cmd: Sequence[str],
        *,
        timeout: float | None = None,
        log: Path | None = None,
        tick: Tick | None = None,
    ) -> Result: ...


TAIL_CHARS = 6000


def tail_of(path: Path, chars: int = TAIL_CHARS) -> str:
    try:
        with path.open("rb") as fh:
            fh.seek(0, os.SEEK_END)
            size = fh.tell()
            fh.seek(max(0, size - chars))
            return fh.read().decode("utf-8", "replace")
    except OSError:
        return ""


def child_env() -> dict[str, str]:
    """Rule 7 for every child: scratch in RAM, no bytecode on the disk."""
    env = dict(os.environ)
    env.setdefault("TMPDIR", "/dev/shm/poring-lab-tmp")
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    Path(env["TMPDIR"]).mkdir(parents=True, exist_ok=True)
    return env


def run_process(
    cmd: Sequence[str],
    *,
    timeout: float | None = None,
    log: Path | None = None,
    tick: Tick | None = None,
) -> Result:
    """The real runner. With `log`: the whole output goes to that file (appended, with the command
    line first) and `tick(elapsed_s)` is called about twice a second; the result carries the tail.
    Ctrl+C reaches the child too (same terminal): its own SIGINT handling runs (guarded_build
    stops its step), this waits up to 30 s for it, then re-raises."""
    try:
        if log is None:
            proc = subprocess.run(
                list(cmd), capture_output=True, text=True, timeout=timeout, cwd=REPO,
                env=child_env(), stdin=subprocess.DEVNULL,
            )  # fmt: skip
            return Result(proc.returncode, (proc.stdout or "") + (proc.stderr or ""))
    except FileNotFoundError:
        return Result(127, f"{cmd[0]}: command not found")
    except subprocess.TimeoutExpired:
        return Result(124, f"timed out after {timeout:.0f} s")
    log.parent.mkdir(parents=True, exist_ok=True)
    start = time.monotonic()
    with log.open("a", encoding="utf-8") as fh:
        stamp = time.strftime("%Y-%m-%d %H:%M:%S")
        fh.write(f"\n=== {stamp} $ {' '.join(cmd)}\n")
        fh.flush()
        try:
            proc2 = subprocess.Popen(
                list(cmd), stdout=fh, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                cwd=REPO, env=child_env(),
            )  # fmt: skip
        except FileNotFoundError:
            fh.write(f"{cmd[0]}: command not found\n")
            return Result(127, f"{cmd[0]}: command not found")
        try:
            while proc2.poll() is None:
                elapsed = time.monotonic() - start
                if timeout is not None and elapsed > timeout:
                    proc2.send_signal(2)
                    try:
                        proc2.wait(30)
                    except subprocess.TimeoutExpired:
                        proc2.kill()
                    fh.write(f"\n=== timed out after {timeout:.0f} s\n")
                    return Result(124, tail_of(log) + f"\ntimed out after {timeout:.0f} s")
                if tick is not None:
                    tick(elapsed)
                time.sleep(0.5)
        except KeyboardInterrupt:
            try:
                proc2.wait(30)
            except subprocess.TimeoutExpired:
                proc2.kill()
            raise
        fh.write(f"=== exit {proc2.returncode} after {time.monotonic() - start:.0f} s\n")
    return Result(proc2.returncode, tail_of(log))


# --- pre-flight (read-only) -----------------------------------------------------------------------


@dataclass(frozen=True)
class Check:
    key: str
    title: str
    status: str  # ok | warn | fail | info
    detail: str
    fix: str = ""
    blocking: bool = False  # a failure the wizard cannot go past


MANUAL = "docs/setup/new-lab-host.md"
FIX_POOL = (
    f"Docker's address pool is not set: Docker could take a 192.168.x range from your LAN. Follow "
    f"{MANUAL} section 1.1 (write /etc/docker/daemon.json with the 10.210.0.0/16 pool), then "
    "`sudo systemctl restart docker`, then run ./setup.sh again. The wizard never edits it."
)
FIX_DOCKER_MISSING = (
    f"Install Docker AFTER writing its address pool: {MANUAL} sections 1.1 and 1.2."
)
FIX_DOCKER_GROUP = (
    'Your user may not use Docker yet: `sudo usermod -aG docker "$USER"`, then log out and in '
    f"again (or `newgrp docker`), then ./setup.sh ({MANUAL} section 1.2)."
)
FIX_DOCKER_DOWN = "The Docker daemon does not answer: `sudo systemctl start docker`."
FIX_SHM = (
    f'{MANUAL} section 1.3: `sudo loginctl enable-linger "$USER"`, then `sudo mkdir -p '
    "/etc/systemd/logind.conf.d` and `printf '[Login]\\nRemoveIPC=no\\n' | sudo tee "
    "/etc/systemd/logind.conf.d/poring-lab-keep-shm.conf` (active after a reboot)."
)


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def os_release(root: Path = Path("/")) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in read_text(root / "etc/os-release").splitlines():
        key, sep, value = line.partition("=")
        if sep:
            out[key] = value.strip().strip('"')
    return out


def mem_total_gib(root: Path = Path("/")) -> float | None:
    match = re.search(r"^MemTotal:\s+(\d+) kB", read_text(root / "proc/meminfo"), re.M)
    return int(match.group(1)) / 1024 / 1024 if match else None


@dataclass(frozen=True)
class Gpu:
    vendor: str  # intel | nvidia | amd | none
    render_node: bool

    @property
    def label(self) -> str:
        return {"intel": "an Intel GPU", "nvidia": "an NVIDIA GPU", "amd": "an AMD GPU"}.get(
            self.vendor, "no GPU"
        )


PCI_VENDORS = {"0x8086": "intel", "0x10de": "nvidia", "0x1002": "amd"}


def detect_gpu(root: Path = Path("/")) -> Gpu:
    """From sysfs only (no lspci): each DRM card's PCI vendor, plus the NVIDIA driver's proc file
    (its cards may have no DRM node). NVIDIA wins, then AMD, then Intel: an Intel iGPU sits beside
    many NVIDIA and AMD cards (ADR-0022 Amendment 2026-11-18b)."""
    found: set[str] = set()
    drm = root / "sys/class/drm"
    if drm.is_dir():
        for card in drm.iterdir():
            if re.fullmatch(r"card\d+", card.name):
                vendor = read_text(card / "device" / "vendor").strip().lower()
                if vendor in PCI_VENDORS:
                    found.add(PCI_VENDORS[vendor])
    if (root / "proc/driver/nvidia/version").exists():
        found.add("nvidia")
    dri = root / "dev/dri"
    render = dri.is_dir() and any(p.name.startswith("renderD") for p in dri.iterdir())
    for vendor in ("nvidia", "amd", "intel"):
        if vendor in found:
            return Gpu(vendor, render)
    return Gpu("none", render)


def default_profile(gpu: Gpu) -> str:
    """ADR-0022 / manual section 5, by the vendor alone: NVIDIA -> dedicated-nvidia, Intel ->
    dedicated-intel, AMD -> dedicated-amd (Amendment 2026-11-18b), anything else -> dedicated-cpu
    (Amendment 2026-11-17). The wizard uses gpu_recommendation, which also checks the driver and
    runtime. Never shared-nvidia."""
    return {"nvidia": "dedicated-nvidia", "intel": "dedicated-intel", "amd": "dedicated-amd"}.get(
        gpu.vendor, "dedicated-cpu"
    )


def check_docker(runner: Runner, which: Callable[[str], str | None] = shutil.which) -> list[Check]:
    if which("docker") is None:
        return [Check("docker", "Docker", "fail", "not installed", FIX_DOCKER_MISSING, True)]
    res = runner(["docker", "info", "--format", "{{json .DefaultAddressPools}}"], timeout=20)
    if not res.ok:
        low = res.out.lower()
        if "permission denied" in low:
            return [Check("docker", "Docker without sudo", "fail", "permission denied",
                          FIX_DOCKER_GROUP, True)]  # fmt: skip
        return [Check("docker", "Docker", "fail", "the daemon does not answer", FIX_DOCKER_DOWN,
                      True)]  # fmt: skip
    checks = [Check("docker", "Docker without sudo", "ok", "docker info answers")]
    pools = res.out.strip().splitlines()[-1].strip() if res.out.strip() else ""
    try:
        parsed = json.loads(pools) if pools else None
    except json.JSONDecodeError:
        parsed = None
    if not parsed:
        checks.append(Check("pool", "Docker address pool", "fail", f"{pools or 'empty'}",
                            FIX_POOL, True))  # fmt: skip
    else:
        bases = ", ".join(str(p.get("Base", "?")) for p in parsed if isinstance(p, dict))
        checks.append(Check("pool", "Docker address pool", "ok", bases or str(parsed)))
    return checks


def check_bridges(runner: Runner) -> Check:
    """No Docker bridge may hold a 192.168.x range (manual 1.2 step 3 and section 13)."""
    res = runner(["ip", "-4", "route"], timeout=10)
    if not res.ok:
        return Check("bridges", "LAN routes", "warn", "could not read `ip route`")
    bad = []
    lan = ipaddress.ip_network("192.168.0.0/16")
    for line in res.out.splitlines():
        parts = line.split()
        if not parts or not re.search(r"\bdev (br-\S+|docker0)\b", line):
            continue
        try:
            net = ipaddress.ip_network(parts[0], strict=False)
        except ValueError:
            continue
        if net.version == 4 and net.overlaps(lan):
            bad.append(line.strip())
    if bad:
        return Check(
            "bridges", "LAN routes", "fail", f"a Docker bridge holds a LAN range: {bad[0]}",
            f"{MANUAL} section 13, first row: remove that Docker network, pin a /24 in 10.210.x, "
            "check `docker info` for the pool.",
        )  # fmt: skip
    return Check("bridges", "LAN routes", "ok", "no Docker bridge on 192.168.x")


def check_disk(path: Path, build_vision: bool = False,
               usage: Callable[[Path], Any] = shutil.disk_usage) -> Check:  # fmt: skip
    free_gb = usage(path).free / 1e9
    need, want = (40.0, 60.0) if build_vision else (25.0, 40.0)
    detail = f"{free_gb:.0f} GB free on {path}"
    fix = "Images take ~15 GB (+ ~12 GB for the GPU vision image). Free some space first."
    if free_gb < need:
        return Check("disk", "Free disk", "fail", detail + f" (need {need:.0f} GB)", fix)
    if free_gb < want:
        return Check("disk", "Free disk", "warn", detail + f" (recommended {want:.0f} GB)", fix)
    return Check("disk", "Free disk", "ok", detail)


def check_ram(gib: float | None) -> Check:
    if gib is None:
        return Check("ram", "Memory", "warn", "could not read /proc/meminfo")
    detail = f"{gib:.1f} GiB"
    if gib < 7:
        return Check("ram", "Memory", "fail", detail, "16 GB is the minimum (README).")
    if gib < 14:
        return Check("ram", "Memory", "warn", detail, "16 GB is the minimum, 32 GB to train.")
    return Check("ram", "Memory", "ok", detail)


def check_shm(runner: Runner, user: str) -> Check:
    """Manual 1.3: logind's RemoveIPC deletes a user's /dev/shm files at the last logout."""
    linger = runner(["loginctl", "show-user", user, "-p", "Linger"], timeout=10).out.strip()
    conf = runner(["systemd-analyze", "cat-config", "systemd/logind.conf"], timeout=10)
    remove_ipc = "yes"
    for line in conf.out.splitlines():
        match = re.match(r"\s*RemoveIPC\s*=\s*(\S+)", line)
        if match:
            remove_ipc = match.group(1).lower()  # the last one wins, as in logind
    lingers = linger.endswith("=yes")
    kept = remove_ipc in ("no", "false", "0")
    detail = f"Linger={'yes' if lingers else 'no'}, RemoveIPC={remove_ipc}"
    if lingers and kept:
        return Check("shm", "/dev/shm kept at logout", "ok", detail)
    if lingers or kept:
        return Check("shm", "/dev/shm kept at logout", "warn", detail, FIX_SHM)
    return Check("shm", "/dev/shm kept at logout", "warn", detail + ": RAM files vanish", FIX_SHM)


def preflight(
    runner: Runner,
    *,
    root: Path = Path("/"),
    repo: Path = REPO,
    user: str | None = None,
    uid: int | None = None,
    platform: str = sys.platform,
    which: Callable[[str], str | None] = shutil.which,
    build_vision: bool = False,
) -> tuple[list[Check], Gpu]:
    """Every check is read-only. Returns the checks and the detected GPU."""
    user = user or os.environ.get("USER") or "unknown"
    uid = os.getuid() if uid is None else uid
    checks: list[Check] = []
    if not platform.startswith("linux"):
        return [Check("linux", "Linux", "fail", platform, "poring-lab runs on a Linux server "
                      "(Ubuntu 26.04 LTS: README).", True)], Gpu("none", False)  # fmt: skip
    rel = os_release(root)
    name = rel.get("PRETTY_NAME", "unknown")
    ubuntu = rel.get("ID") == "ubuntu" and rel.get("VERSION_ID") == "26.04"
    checks.append(Check("linux", "Linux", "ok" if ubuntu else "warn", name,
                        "" if ubuntu else "The lab runs Ubuntu 26.04 LTS; others are untested "
                        "(the Intel vision image is built FROM ubuntu:26.04)."))  # fmt: skip
    checks.append(
        Check(
            "uid",
            "User id",
            "ok" if uid == 1000 else "warn",
            f"{user} (uid {uid})",
            ""
            if uid == 1000
            else "The containers run as uid 1000 and write into the "
            "repo's bind mounts: use the first user Ubuntu created (manual 0).",
        )
    )
    checks.extend(check_docker(runner, which))
    checks.append(check_bridges(runner))
    checks.append(check_disk(repo, build_vision))
    checks.append(check_ram(mem_total_gib(root)))
    checks.append(check_shm(runner, user))
    gpu = detect_gpu(root)
    # ADR-0022 Amendment 2026-11-17 (Batt: "detect the GPU and recommend it; no GPU -> the CPU"):
    # what a container cannot bring decides; not ready = a warning with the fixes, never a stop
    rec = gpu_recommendation(gpu, runner, root)
    state = "warn" if rec.fixes else "info"
    checks.append(Check("gpu", "GPU", state, rec.summary(), "; ".join(rec.fixes + rec.notes)))
    # ADR-0026: this copy's Docker name and subnets (a name another folder's containers use stops)
    checks.append(check_project(runner, repo))
    checks.append(check_subnets(runner, env_baseline(repo), repo=repo)[0])
    return checks, gpu


# --- 0b. this install's names, subnets and GPU (ADR-0026, Batt 2026-11-17: nothing locked) -------


def project_owners(runner: Runner, name: str) -> set[str]:
    """The folders whose compose containers carry project ``name`` (compose's working_dir label)."""
    res = runner(
        [
            "docker",
            "ps",
            "-a",
            "--filter",
            f"label=com.docker.compose.project={name}",
            "--format",
            '{{.Label "com.docker.compose.project.working_dir"}}',
        ],
        timeout=20,
    )
    return {line.strip() for line in res.out.splitlines() if line.strip()} if res.ok else set()


def check_project(runner: Runner, repo: Path = REPO, name: str | None = None) -> Check:
    """Batt 2026-11-17: "check first: if the name poring-lab exists, tell the user to use another".
    Only ANOTHER folder's containers count: a re-run here finds its own."""
    name = name or project()
    owners = project_owners(runner, name)
    here = str(repo.resolve())
    other = sorted(o for o in owners if str(Path(o).resolve()) != here)
    if other:
        return Check(
            "project",
            "Docker name",
            "fail",
            f"'{name}' belongs to the poring-lab copy in {other[0]}",
            "This copy needs its own name (COMPOSE_PROJECT_NAME): the wizard asks for "
            "one; that copy is never touched.",
            True,
        )
    return Check(
        "project",
        "Docker name",
        "ok",
        f"'{name}'" + (" (this folder's containers)" if owners else ""),
    )


def free_project_name(runner: Runner, base: str, repo: Path = REPO) -> str:
    """``base``-2, -3, ...: the first name no other folder's containers use."""
    for n in range(2, 100):
        cand = f"{base}-{n}"[:63]
        if check_project(runner, repo, cand).status == "ok":
            return cand
    raise SetupError("no free project name found")


def used_subnets(runner: Runner) -> list[tuple[ipaddress.IPv4Network, str]]:
    """Every IPv4 subnet on this host, with its owner: Docker networks (by name) and routes."""
    out: list[tuple[ipaddress.IPv4Network, str]] = []
    ids = runner(["docker", "network", "ls", "-q"], timeout=20)
    if ids.ok and ids.out.split():
        res = runner(
            [
                "docker",
                "network",
                "inspect",
                "--format",
                "{{.Name}}{{range .IPAM.Config}} {{.Subnet}}{{end}}",
                *ids.out.split(),
            ],
            timeout=20,
        )
        for line in res.out.splitlines() if res.ok else []:
            name, *nets = line.split()
            for n in nets:
                try:
                    net = ipaddress.ip_network(n, strict=False)
                except ValueError:
                    continue
                if isinstance(net, ipaddress.IPv4Network):
                    out.append((net, f"Docker network {name}"))
    routes = runner(["ip", "-4", "route"], timeout=10)
    for line in routes.out.splitlines() if routes.ok else []:
        parts = line.split()
        if not parts or parts[0] == "default" or re.search(r"\bdev (br-\S+|docker0)\b", line):
            continue  # Docker's own bridges are listed by name above
        try:
            net = ipaddress.ip_network(parts[0], strict=False)
        except ValueError:
            continue
        if isinstance(net, ipaddress.IPv4Network):
            out.append((net, f"route {line.strip()}"))
    return out


def check_subnets(
    runner: Runner, env: Mapping[str, str], name: str | None = None, repo: Path = REPO
) -> tuple[Check, dict[str, str]]:
    """The two pinned /24s must be free on this host (rule 6), or this copy's own. Taken: the
    proposal is the first free pair inside 10.210.0.0/16 (from 10.210.96 up). The networks of
    ``name`` are this copy's only when no OTHER folder's containers use that name."""
    name = name or project()
    mine = check_project(runner, repo, name).status == "ok"
    own = {f"Docker network {name}_default", f"Docker network {name}_agent"} if mine else set()
    used = [(n, o) for n, o in used_subnets(runner) if o not in own]
    want = {k: env.get(k, "").strip() or lab_env.NETS[k] for k in lab_env.NETS}

    def taken(prefix: str) -> str | None:
        net = ipaddress.ip_network(f"{prefix}.0/24")
        return next((o for n, o in used if n.overlaps(net)), None)

    hits = {k: t for k in want if (t := taken(want[k]))}
    if not hits:
        return Check(
            "subnets",
            "Docker subnets",
            "ok",
            f"{want['LAB_NET_PREFIX']}.0/24 and {want['LAB_AGENT_NET_PREFIX']}.0/24 are free",
        ), {}
    for x in range(96, 254):
        pair = (f"10.210.{x}", f"10.210.{x + 1}")
        if not taken(pair[0]) and not taken(pair[1]):
            proposal = dict(zip(("LAB_NET_PREFIX", "LAB_AGENT_NET_PREFIX"), pair, strict=True))
            key, owner = next(iter(hits.items()))
            return Check(
                "subnets",
                "Docker subnets",
                "warn",
                f"{want[key]}.0/24 is taken ({owner}): this copy will use "
                f"{pair[0]}.0/24 and {pair[1]}.0/24",
                "",
            ), proposal
    return Check(
        "subnets",
        "Docker subnets",
        "fail",
        "no free /24 pair inside 10.210.0.0/16",
        f"{MANUAL} section 1.1",
        True,
    ), {}


def our_ports(runner: Runner, name: str | None = None) -> set[int]:
    """The host ports this copy's own containers publish now (a re-run holds them itself)."""
    res = runner(
        [
            "docker",
            "ps",
            "--filter",
            f"label=com.docker.compose.project={name or project()}",
            "--format",
            "{{.Ports}}",
        ],
        timeout=20,
    )
    return {int(m) for m in re.findall(r":(\d+)->", res.out)} if res.ok else set()


def port_moves(
    ip: str, env: Mapping[str, str], held: set[int], binder: Callable[[str, int], str] | None = None
) -> dict[str, tuple[int, int]]:
    """{key: (wanted, proposal)} for each install port another program holds on ``ip`` (the
    console's port has its own screen). A proposal: the wanted port + 1000 x k, free, unused."""
    binder = binder or bind_state
    wanted = {
        k: int(env.get(k, "").strip() or v) for k, v in lab_env.PORTS.items() if k != "CONSOLE_PORT"
    }
    chosen = set(wanted.values())
    out: dict[str, tuple[int, int]] = {}
    for key, port in wanted.items():
        if port in held or binder(ip, port) == "free":
            continue
        for k in range(1, 60):
            cand = port + 1000 * k
            if cand > PORT_MAX:
                break
            if cand not in chosen and cand not in LAB_PORTS and binder(ip, cand) == "free":
                out[key] = (port, cand)
                chosen.add(cand)
                break
        else:
            out[key] = (port, 0)  # none found: the person types one
    return out


def gpu_recommendation(gpu: Gpu, runner: Runner, root: Path = Path("/")) -> gpu_ready.GpuReady:
    """scripts/gpu_ready.py's recommendation for the detected GPU (ADR-0022 Amendment 11-17)."""

    def run(cmd: Sequence[str]) -> tuple[int, str]:
        res = runner(list(cmd), timeout=20)
        return res.rc, res.out

    return gpu_ready.recommend(gpu.vendor, ram_gib=mem_total_gib(root), root=root, run=run)


def detector_ready(repo: Path) -> Callable[[Runner], bool]:
    def check(runner: Runner) -> bool:
        res = runner([PY, str(repo / "scripts" / "detector_setup.py"), "--check"], timeout=300)
        return res.ok

    return check


def blocking(checks: Sequence[Check]) -> list[Check]:
    return [c for c in checks if c.status == "fail" and c.blocking]


# --- 1. the server address ------------------------------------------------------------------------


@dataclass(frozen=True)
class Addr:
    ifname: str
    ip: str
    prefix: int

    @property
    def network(self) -> ipaddress.IPv4Network:
        return ipaddress.IPv4Network(f"{self.ip}/{self.prefix}", strict=False)


def default_route_ip(runner: Runner) -> str | None:
    """scripts/init_env.sh's method: the source address of the default route."""
    out = runner(["ip", "-4", "route", "get", "1.1.1.1"], timeout=10).out.split()
    for i, word in enumerate(out[:-1]):
        if word == "src":
            return out[i + 1]
    return None


def host_addrs(runner: Runner) -> list[Addr]:
    """This host's IPv4 addresses, without loopback and Docker's own interfaces."""
    out: list[Addr] = []
    for line in runner(["ip", "-4", "-o", "addr", "show"], timeout=10).out.splitlines():
        match = re.match(r"\d+:\s+(\S+)\s+inet\s+([\d.]+)/(\d+)", line)
        if not match:
            continue
        ifname = match.group(1)
        if ifname == "lo" or ifname.startswith(("docker", "br-", "veth")):
            continue
        out.append(Addr(ifname, match.group(2), int(match.group(3))))
    return out


def server_ip_problem(ip: str, addrs: Sequence[Addr]) -> str:
    """'' when `ip` is a private LAN address of this host; else why not."""
    try:
        addr = ipaddress.IPv4Address(ip.strip())
    except ValueError:
        return f"{ip!r} is not an IPv4 address"
    if addr.is_loopback or addr.is_link_local or addr.is_unspecified:
        return f"{ip} is not a LAN address (loopback, link-local or 0.0.0.0)"
    if not addr.is_private:
        return f"{ip} is a public address: the lab binds only to a private LAN address"
    if any(addr in net for net in DOCKER_NETS):
        return f"{ip} is inside Docker's own ranges (10.210.0.0/16, 10.209.255.0/24, 172.17/16)"
    if ip.strip() not in {a.ip for a in addrs}:
        return f"{ip} is not an address of this machine ({', '.join(a.ip for a in addrs) or '-'})"
    return ""


# --- 2. the console port --------------------------------------------------------------------------


def parse_port(text: str) -> tuple[int | None, str]:
    text = text.strip()
    if not text.isdigit():
        return None, f"{text!r} is not a number"
    port = int(text)
    return port, port_problem(port)


def port_problem(port: int, taken: Mapping[int, str] | None = None) -> str:
    taken = LAB_PORTS if taken is None else taken
    if not PORT_MIN <= port <= PORT_MAX:
        return f"{port} is outside {PORT_MIN}-{PORT_MAX} (ports below 1024 are privileged)"
    if port in taken:
        return f"{port} is {taken[port]}'s port: pick another"
    return ""


def bind_state(ip: str, port: int) -> str:
    """'free', 'in-use', or 'error: ...' -- a real bind on (ip, port), closed at once."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind((ip, port))
        return "free"
    except OSError as exc:
        return "in-use" if exc.errno == 98 else f"error: {exc.strerror or exc}"
    finally:
        sock.close()


def http_ok(url: str, timeout: float = 3.0) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:  # noqa: S310 (LAN http only)
            return bool(200 <= resp.status < 400)
    except (urllib.error.URLError, OSError, ValueError):
        return False


def console_url(ip: str, port: int) -> str:
    return f"http://{ip}:{port}"


def port_verdict(
    ip: str,
    port: int,
    *,
    binder: Callable[[str, int], str] | None = None,
    fetch: Callable[[str], bool] | None = None,
    held: set[int] | None = None,
) -> tuple[bool, str]:
    """(usable, message). A port already serving THIS copy's console (a re-run) is fine: one
    this copy's own containers publish (``held``, our_ports), or -- when that is not known -- a
    console answering there. A console of ANOTHER copy on this host (ADR-0026) is not ours."""
    binder, fetch = binder or bind_state, fetch or http_ok  # resolved late: patchable
    why = port_problem(port)
    if why:
        return False, why
    state = binder(ip, port)
    if state == "free":
        return True, f"{ip}:{port} is free"
    if state == "in-use":
        mine = port in held if held is not None else fetch(f"{console_url(ip, port)}/api/health")
        if mine:
            return True, f"{ip}:{port} already serves this lab's console"
        return False, f"{ip}:{port} is in use by another program (`ss -ltnp | grep :{port}`)"
    return False, f"cannot test {ip}:{port}: {state}"


# --- 3. the Windows PC ----------------------------------------------------------------------------


def win_ip_problems(ip: str, server_ip: str, addrs: Sequence[Addr]) -> tuple[str, list[str]]:
    """(error, warnings) for the game PC's address."""
    try:
        addr = ipaddress.IPv4Address(ip.strip())
    except ValueError:
        return f"{ip!r} is not an IPv4 address", []
    if addr.is_loopback or addr.is_link_local or addr.is_unspecified or not addr.is_private:
        return f"{ip} is not a private LAN address", []
    if ip.strip() == server_ip or ip.strip() in {a.ip for a in addrs}:
        return f"{ip} is THIS server: type the Windows PC's own address (ipconfig on the PC)", []
    if any(addr in net for net in DOCKER_NETS):
        return f"{ip} is inside Docker's ranges", []
    warnings = []
    nets = [a.network for a in addrs if a.ip == server_ip]
    if nets and not any(addr in n for n in nets):
        warnings.append(f"{ip} is not on this server's subnet ({nets[0]}): the lab expects both "
                        "on the same LAN")  # fmt: skip
    return "", warnings


def tcp_open(ip: str, port: int, timeout: float = 3.0) -> bool:
    try:
        with socket.create_connection((ip, port), timeout=timeout):
            return True
    except OSError:
        return False


def probe_sunshine(ip: str, connect: Callable[[str, int], bool] | None = None) -> dict[int, bool]:
    """capture_backend.sunshine_reachable's test, port by port (TCP only: UDP needs a stream)."""
    connect = connect or tcp_open
    return {port: connect(ip, port) for port in SUNSHINE_TCP}


SUNSHINE_FIXES = (
    "Sunshine runs on the PC: its tray icon is there, or `Get-Service SunshineService` says "
    "Running (docs/setup/sunshine-windows.md step 1).",
    "Sunshine's inbound firewall rules admit THIS server's address (step 4 of the guide): "
    "`Get-NetFirewallApplicationFilter -Program 'C:\\Program Files\\Sunshine\\sunshine.exe' | "
    "Get-NetFirewallRule | Get-NetFirewallAddressFilter` shows it.",
    "The PC and this server are on the same LAN; `ping <PC>` from here answers.",
    "The PC is awake: sleep off (step 7 of the guide).",
    "The address is the PC's current one (`ipconfig` on the PC, step 6).",
)


# --- 4. .env --------------------------------------------------------------------------------------


@dataclass
class Answers:
    server_ip: str = ""
    console_port: int = 0  # 0 = not chosen yet (screen 2 offers .env's value, else 3000)
    win_ip: str = ""
    profile: str = ""
    build_vision: bool = False
    # ADR-0026 (Batt 2026-11-17, nothing locked): set only when they differ from the defaults
    project: str = ""  # COMPOSE_PROJECT_NAME, when the default belongs to another folder
    store_dir: str = ""  # LAB_STORE_DIR
    ports: dict[str, int] = field(default_factory=dict)  # RATHENA_*_PORT / NOVNC / BACKEND moves
    nets: dict[str, str] = field(default_factory=dict)  # LAB_NET_PREFIX / LAB_AGENT_NET_PREFIX
    viewer_net: str = ""  # VIEWER_NETWORKS + the server's own network, when no private range has it
    worker_mem: str = ""  # VISION_WORKER_MEM, the GPU recommendation's (a new .env only)
    render_node: str = ""  # GPU_RENDER_NODE, the GPU recommendation's (the AMD card's own node)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Answers:
        known = {k: data[k] for k in asdict(cls()) if k in data}
        return cls(**known)


def parse_env_text(text: str) -> dict[str, str]:
    """rotate_secrets.parse_env's rule (the first value of a key wins here, as compose reads)."""
    out: dict[str, str] = {}
    for line in text.splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            key, value = line.split("=", 1)
            out.setdefault(key.strip(), value)
    return out


def read_env(path: Path) -> dict[str, str]:
    return parse_env_text(read_text(path)) if path.exists() else {}


def backend_port(env: Mapping[str, str]) -> int:
    """PURE: the backend's host port from .env (BACKEND_PORT), else DEFAULT_BACKEND_PORT
    (2026-11-19: a second copy on one host answers on its own port, not the lab's 8000)."""
    text = str(env.get("BACKEND_PORT", "")).strip()
    return int(text) if text.isdigit() else DEFAULT_BACKEND_PORT


def env_baseline(repo: Path) -> dict[str, str]:
    """What .env holds now, or, before it exists, what init_env.sh will start from
    (.env.example: its non-secret defaults; the secrets it generates are not known yet)."""
    env = repo / ".env"
    return read_env(env) if env.exists() else read_env(repo / ".env.example")


def shown(name: str, value: str | None) -> str:
    """A value for the screen: SAFE_KEYS in clear, every other name only as set / empty."""
    if value is None:
        return "(absent)"
    if name in SAFE_KEYS:
        return value if value != "" else "(empty)"
    return "set (hidden)" if value.strip() else "(empty)"


def rdp_configured(env: Mapping[str, str]) -> bool:
    """rdp-loop.sh's rule: RDP connects only when all three are set."""
    return all(env.get(k, "").strip() for k in ("WIN_HOST", "RDP_USER", "RDP_PASSWORD"))


def rdp_credentials_set(env: Mapping[str, str]) -> bool:
    return bool(env.get("RDP_USER", "").strip() or env.get("RDP_PASSWORD", "").strip())


def render_gid(lookup: Callable[[str], Any] | None = None) -> int | None:
    """`getent group render`'s third field (the Intel image's /dev/dri access)."""
    import grp

    try:
        return int((lookup or grp.getgrnam)("render").gr_gid)
    except (KeyError, AttributeError):
        return None


def s2_rec_default(home: Path) -> str:
    return str(home / "poring-lab-rec" / ".s2-h264")


def planned_env(
    a: Answers, current: Mapping[str, str], *, gid: int | None, home: Path
) -> dict[str, str]:
    """The settings the wizard owns, from the student's answers (manual sections 3 and 5)."""
    plan = {
        "HOST_LAN_IP": a.server_ip,
        "CONSOLE_PORT": str(a.console_port),
        "WIN_HOST": a.win_ip,
        "LAB_HOST_PROFILE": a.profile,
        "RATHENA_WEB_SERVER": "true",  # the client's account settings (manual 3 step 4, 7.1)
        # the S2 client's only writable bind: on another host than VM 103 it must be set
        "S2_REC_DIR": current.get("S2_REC_DIR", "").strip() or s2_rec_default(home),
    }
    if gid is not None:
        plan["RENDER_GID"] = str(gid)
    if a.profile.startswith("dedicated-"):
        plan["VISION_MAX_VRAM_FRACTION"] = "1.0"
    # ADR-0026 (Batt 2026-11-17: nothing locked): this install's own values, where they differ
    if a.project and a.project != lab_env.PROJECT_DEFAULT:
        plan["COMPOSE_PROJECT_NAME"] = a.project
    plan["LAB_STORE_DIR"] = (a.store_dir or current.get("LAB_STORE_DIR", "").strip()
                             or str(home / lab_env.STORE_DEFAULT))  # fmt: skip
    for key, port in a.ports.items():
        plan[key] = str(port)
    plan.update(a.nets)
    if a.viewer_net:
        plan["VIEWER_NETWORKS"] = a.viewer_net
    if a.worker_mem and not current.get("VISION_WORKER_MEM", "").strip():
        plan["VISION_WORKER_MEM"] = a.worker_mem
    if a.render_node:
        plan["GPU_RENDER_NODE"] = a.render_node
    origins = current.get("FRONTEND_ORIGINS", "").strip()
    if origins:  # an explicit list must name the console, or the backend refuses it
        want = console_url(a.server_ip, a.console_port)
        if want not in {o.strip().rstrip("/") for o in origins.split(",")}:
            plan["FRONTEND_ORIGINS"] = f"{origins},{want}"
    return plan


Change = tuple[str, str | None, str]  # (name, old value or None when absent, new value)


def env_changes(current: Mapping[str, str], plan: Mapping[str, str]) -> list[Change]:
    return [(k, current.get(k), v) for k, v in plan.items() if current.get(k) != v]


SetValues = Callable[[list[str], Path], list[str]]


def default_set_values(pairs: list[str], env_path: Path) -> list[str]:
    sys.path.insert(0, str(REPO / "scripts"))
    import rotate_secrets

    return rotate_secrets.set_values(pairs, env_path)


def write_env(
    repo: Path,
    a: Answers,
    runner: Runner,
    *,
    gid: int | None,
    home: Path,
    set_values: SetValues = default_set_values,
    log: Path | None = None,
) -> tuple[bool, list[Change]]:
    """Create .env with init_env.sh when missing (its random secrets), then set ONLY the changed
    settings through rotate_secrets.set_values (read back). Never a secret, never twice."""
    env_path = repo / ".env"
    created = False
    if not env_path.exists():
        res = runner(["bash", str(repo / "scripts" / "init_env.sh")], timeout=60, log=log)
        if not res.ok or not env_path.exists():
            raise SetupError(f"scripts/init_env.sh failed (exit {res.rc}): {res.out[-300:]}")
        created = True
    current = read_env(env_path)
    changes = env_changes(current, planned_env(a, current, gid=gid, home=home))
    if changes:
        try:
            set_values([f"{k}={v}" for k, _, v in changes], env_path)
        except SystemExit as exc:  # rotate_secrets exits with its reason (never a value)
            raise SetupError(f"rotate_secrets refused: {exc}") from None
    back = read_env(env_path)
    wrong = [k for k, _, v in changes if back.get(k) != v]
    if wrong:
        raise SetupError(f".env read-back differs for {wrong}")
    rec = Path(back.get("S2_REC_DIR", "").strip() or s2_rec_default(home))
    try:
        rec.mkdir(parents=True, exist_ok=True)  # must exist and be ours before gamestream starts
    except OSError as exc:
        raise SetupError(f"cannot create S2_REC_DIR {rec}: {exc}") from None
    # ADR-0026: the storage folder must exist before the vision worker binds it (Docker would
    # create it root-owned); its archive/models/ takes the starter model (detector_setup.py)
    store = Path(back.get("LAB_STORE_DIR", "").strip() or home / lab_env.STORE_DEFAULT)
    try:
        (store / "archive" / "models").mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise SetupError(f"cannot create the storage folder {store}: {exc}") from None
    return created, changes


# --- 5. the install -------------------------------------------------------------------------------


@dataclass(frozen=True)
class Step:
    id: str
    title: str
    cmd: tuple[str, ...]
    fix: str
    optional: bool = False
    timeout: float | None = None
    done: Callable[[Runner], bool] | None = None  # None: always run (it is itself a check)


def guarded(step: str) -> tuple[str, ...]:
    return (PY, "scripts/guarded_build.py", step)


def image_present(name: str) -> Callable[[Runner], bool]:
    def check(runner: Runner) -> bool:
        return runner(["docker", "image", "inspect", "--format", "{{.Id}}", name], timeout=20).ok

    return check


def container_state(runner: Runner, service: str) -> str:
    """'running healthy' / 'running none' / 'exited none' / 'absent'."""
    res = runner(
        ["docker", "inspect", "-f",
         "{{.State.Status}} {{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}",
         lab_env.container(service)],
        timeout=20,
    )  # fmt: skip
    return res.out.strip() if res.ok else "absent"


def services_up(*services: str) -> Callable[[Runner], bool]:
    def check(runner: Runner) -> bool:
        for svc in services:
            state = container_state(runner, svc).split()
            if not state or state[0] != "running" or (len(state) > 1 and state[1] == "unhealthy"):
                return False
            if len(state) > 1 and state[1] == "starting":
                return False
        return True

    return check


def files_present(*paths: Path) -> Callable[[Runner], bool]:
    return lambda runner: all(p.exists() for p in paths)


def lock_present(repo: Path) -> Callable[[Runner], bool]:
    def check(runner: Runner) -> bool:
        text = read_text(repo / "state" / "capture-backend")
        return bool(re.search(r"^BACKEND=(rdp|console)$", text, re.M))

    return check


FIX_BUILD = ("Read the last lines: a download failed (internet, DNS, a mirror), or the disk is "
             "full (`df -h`). Then Retry.")  # fmt: skip
FIX_LOGS = "`scripts/dev.sh logs {svc}` shows why; then Retry ({manual} sections 6 and 13)."


def install_plan(repo: Path, env: Mapping[str, str], a: Answers) -> list[Step]:
    """docs/setup/new-lab-host.md section 6, in order, one guarded step at a time, plus the
    Sunshine client (gamestream). Every step that leaves something behind has a done-check, so a
    resumed install checks it and does not redo it."""
    pv = env.get("PACKETVER", "").strip() or "20211103"
    prere = env.get("RATHENA_PRERE", "").strip() or "no"
    pkt = repo / "packages/poring_packets/src/poring_packets/_generated/lengths.json"
    maps = repo / "packages/poring_dataset/src/poring_dataset/_generated"
    logs = FIX_LOGS.replace("{manual}", MANUAL)
    steps = [
        Step(
            "build-rathena",
            "Build the rAthena game server image",
            guarded("build:rathena"),
            "The rapidyaml race: set RATHENA_MAKE_JOBS=1 (`uv run python scripts/rotate_secrets.py "
            "set RATHENA_MAKE_JOBS=1`), then Retry (manual 6 step 8). " + FIX_BUILD,
            timeout=3 * 3600,
            done=image_present(lab_env.image("rathena", f"pv{pv}-prere-{prere}")),
        ),
        Step(
            "pull-db",
            "Pull the MariaDB image",
            guarded("pull:db"),
            "Docker Hub must be reachable (internet, DNS). Then Retry.",
            timeout=3600,
            done=image_present("mariadb:11.8.9"),
        ),
        Step(
            "build-backend",
            "Build the backend image",
            guarded("build:backend"),
            FIX_BUILD,
            timeout=3 * 3600,
            done=image_present(lab_env.image("backend")),
        ),
        Step(
            "build-desktop",
            "Build the desktop image",
            guarded("build:desktop"),
            FIX_BUILD,
            timeout=3 * 3600,
            done=image_present(lab_env.image("desktop")),
        ),
        Step(
            "build-toolchain",
            "Build the rAthena toolchain (for the tables)",
            guarded(f"target:rathena:build:{lab_env.image('rathena-build')}"),
            FIX_BUILD,
            timeout=3 * 3600,
            done=image_present(lab_env.image("rathena-build")),
        ),
        Step(
            "tables",
            "Generate the packet length table",
            guarded("tables"),
            "A lock mismatch means the pinned sources changed: never --update-lock; report it. "
            + FIX_BUILD,
            timeout=3600,
            done=files_present(pkt),
        ),
        Step(
            "mapcache",
            "Extract the server map caches",
            (PY, "scripts/gen_mapcache.py"),
            "It reads the same pinned rAthena tarball as the tables step: run that first. "
            + FIX_BUILD,
            timeout=1800,
            done=files_present(
                *(maps / f"map_cache.{n}.dat" for n in ("import", "pre-re", "re", "base"))
            ),
        ),
        Step(
            "build-sniffer",
            "Build the packet sniffer image",
            guarded("build:sniffer"),
            "It refuses without the exact length table: Retry after the tables step. " + FIX_BUILD,
            timeout=3 * 3600,
            done=image_present(lab_env.image("sniffer")),
        ),
        Step(
            "build-gamestream",
            "Build the Sunshine client image (gamestream)",
            guarded("build:gamestream"),
            FIX_BUILD,
            timeout=3 * 3600,
            done=image_present(lab_env.image("gamestream")),
        ),
    ]
    if a.build_vision:
        steps.append(
            Step(
                "build-vision",
                "Build the GPU vision image (~12 GB, optional)",
                guarded("build:vision"),
                "Optional: Skip it and the CPU detector runs (manual section 9). " + FIX_BUILD,
                optional=True,
                timeout=4 * 3600,
                # the Intel profile builds the Intel image (compose.intel.yaml), the AMD one the
                # Vulkan image (compose.amd.yaml)
                done=image_present(lab_env.image(VISION_IMAGES.get(a.profile, "vision"))),
            )
        )
    steps.append(
        Step(
            "detector",
            "Set up the CPU detector and its starter model (v1, from the teaching-kit branch)",
            (PY, "scripts/detector_setup.py"),
            "Read the last lines: uv could not download numpy / onnxruntime (internet), or git "
            "could not fetch the teaching-kit branch (manual section 9).",
            timeout=1800,
            done=detector_ready(repo),
        )
    )
    steps += [
        Step(
            "start-db",
            "Start the database",
            guarded("start:db@120"),
            logs.replace("{svc}", "db"),
            timeout=900,
            done=services_up("db"),
        ),
        Step(
            "start-rathena",
            "Start the game server",
            guarded("start:rathena@240"),
            logs.replace("{svc}", "rathena") + " A login that hangs at server select: "
            "HOST_LAN_IP is not this server's LAN address.",
            timeout=1200,
            done=services_up("rathena"),
        ),
        Step(
            "smoke-core",
            "Smoke test the game server",
            ("bash", "scripts/smoke_test.sh", "--core"),
            "Every FAIL line names its check. rathena advertising another address: HOST_LAN_IP; "
            "charset not tis620: the database (manual section 13).",
            timeout=900,
        ),
        Step(
            "lock-init",
            "Create the capture lock (rdp/steady: nothing streams yet)",
            (PY, "scripts/capture_backend.py", "init"),
            "A container that sees another lock is stale: Retry after the services start.",
            timeout=120,
            done=lock_present(repo),
        ),
        Step(
            "start-backend",
            "Start the backend and the desktop",
            guarded("start:backend,desktop@90"),
            logs.replace("{svc}", "backend") + " (and `logs desktop`).",
            timeout=900,
            done=services_up("backend", "desktop"),
        ),
        Step(
            "start-sniffer",
            "Start the sniffer",
            guarded("start:sniffer@120"),
            "It refuses an uncommitted packages/poring_packets (`git status`), and its "
            "self-test must pass: " + logs.replace("{svc}", "sniffer"),
            timeout=900,
            done=services_up("sniffer"),
        ),
        Step(
            "start-console",
            "Start the web console",
            guarded("start:frontend-dev@120"),
            "Its first start installs the console's packages from the internet (a few minutes): "
            "Retry. " + logs.replace("{svc}", "frontend-dev"),
            timeout=1200,
            done=services_up("frontend-dev"),
        ),
        Step(
            "start-gamestream",
            "Start the Sunshine client (gamestream)",
            guarded("start:gamestream@60"),
            "S2_REC_DIR must exist and be yours (the .env step makes it). "
            + logs.replace("{svc}", "gamestream"),
            timeout=600,
            done=services_up("gamestream"),
        ),
    ]
    return steps


# A container keeps the environment it was created with: a changed setting reaches a RUNNING
# service only through a guarded recreate (manual 3 "After writing .env", 7.3 step 4).
RECREATE_FOR: dict[str, tuple[str, ...]] = {
    "HOST_LAN_IP": ("rathena", "backend", "desktop", "frontend-dev"),
    "CONSOLE_PORT": ("backend", "frontend-dev"),  # the port, and the Origin list that follows it
    "FRONTEND_ORIGINS": ("backend",),
    "WIN_HOST": ("backend", "desktop", "gamestream"),
    "RATHENA_WEB_SERVER": ("rathena",),
    "S2_REC_DIR": ("gamestream",),
    # ADR-0026: the install values a running copy must take (the game ports reach rathena, which
    # takes its sniffer along; the backend's environment set suggests them)
    "RATHENA_LOGIN_PORT": ("rathena", "backend"),
    "RATHENA_CHAR_PORT": ("rathena", "backend"),
    "RATHENA_MAP_PORT": ("rathena", "backend"),
    "RATHENA_WEB_PORT": ("rathena",),
    "BACKEND_PORT": ("backend", "frontend-dev"),
    "NOVNC_PORT": ("desktop",),
    "VIEWER_NETWORKS": ("backend",),
}


RECREATE_ORDER = ("rathena", "backend", "desktop", "frontend-dev", "gamestream")


def services_to_recreate(changes: Sequence[Change], runner: Runner) -> list[str]:
    """The EXISTING services a .env change must reach (a fresh install creates them anyway)."""
    hit = {svc for name, _, _ in changes for svc in RECREATE_FOR.get(name, ())}
    return [s for s in RECREATE_ORDER if s in hit and container_state(runner, s) != "absent"]


# Which pending recreates a finished step settles (rathena's only after its sniffer followed).
RECREATE_DONE: dict[str, tuple[str, ...]] = {
    "recreate-sniffer": ("rathena",),
    "recreate-backend": ("backend", "desktop"),
    "recreate-console": ("frontend-dev",),
    "recreate-gamestream": ("gamestream",),
}


def logs_fix(svc: str) -> str:
    return FIX_LOGS.replace("{svc}", svc).replace("{manual}", MANUAL)


def recreate_steps(services: Sequence[str]) -> list[Step]:
    """Guarded recreates, in start order. The sniffer lives in rathena's network namespace, so a
    recreated rathena takes a recreated sniffer with it."""
    want = set(services)
    steps = []
    if "rathena" in want:
        steps += [
            Step(
                "recreate-rathena",
                "Recreate the game server (new settings)",
                guarded("recreate:rathena@240"),
                logs_fix("rathena"),
                timeout=1200,
            ),
            Step(
                "recreate-sniffer",
                "Recreate the sniffer (rathena's namespace)",
                guarded("recreate:sniffer@120"),
                logs_fix("sniffer"),
                timeout=900,
            ),
        ]
    if "desktop" in want:
        steps.append(
            Step(
                "recreate-backend",
                "Recreate the backend and the desktop",
                guarded("recreate:backend,desktop@90"),
                logs_fix("backend"),
                timeout=900,
            )
        )
    elif "backend" in want:
        steps.append(
            Step(
                "recreate-backend",
                "Recreate the backend",
                guarded("recreate:backend@30"),
                logs_fix("backend"),
                timeout=600,
            )
        )
    if "frontend-dev" in want:
        steps.append(
            Step(
                "recreate-console",
                "Recreate the web console (new port or address)",
                guarded("recreate:frontend-dev@120"),
                logs_fix("frontend-dev"),
                timeout=1200,
            )
        )
    if "gamestream" in want:
        steps.append(
            Step(
                "recreate-gamestream",
                "Recreate the Sunshine client",
                guarded("recreate:gamestream@60"),
                logs_fix("gamestream"),
                timeout=600,
            )
        )
    return steps


def wait_http(url: str, seconds: float, fetch: Callable[[str], bool] | None = None,
              sleep: Callable[[float], None] = time.sleep) -> bool:  # fmt: skip
    fetch = fetch or http_ok
    deadline = time.monotonic() + seconds
    while True:
        if fetch(url):
            return True
        if time.monotonic() >= deadline:
            return False
        sleep(3)


# --- 6. pairing -----------------------------------------------------------------------------------


def new_pin() -> str:
    """A fresh single-use pairing PIN (the student types it into Sunshine's PIN page)."""
    return f"{secrets.randbelow(10000):04d}"


def pair_cmd(pin: str) -> tuple[str, ...]:
    if not re.fullmatch(r"\d{4}", pin):
        raise SetupError("the PIN is 4 digits")
    return (PY, "scripts/capture_backend.py", "pair", pin)


def paired_state(runner: Runner) -> str:
    """'paired' | 'not paired' | 'gamestream not running' | 'unknown' (capture_backend paired)."""
    res = runner([PY, "scripts/capture_backend.py", "paired"], timeout=30)
    return {0: "paired", 1: "not paired", 2: "gamestream not running"}.get(res.rc, "unknown")


PAIR_FIXES = (
    "The PIN goes on Sunshine's PIN page ON THE PC (https://localhost:47990), within 3 minutes.",
    "Sunshine accepts a PIN only while this wizard waits for it: start the pairing again (a new "
    "PIN), then type it.",
    "'Pairing Failed: Check if the PIN is typed correctly': type exactly the 4 digits shown.",
    "The PC's firewall admits this server on TCP 47984, 47989 and 48010 (the guide, step 4).",
    "The same failure twice: restart Sunshine on the PC (`Restart-Service SunshineService` in an "
    "administrator PowerShell, or reboot it), then pair again.",
)


# --- 7. the stream test ---------------------------------------------------------------------------


def lock_now(repo: Path) -> dict[str, str]:
    """The capture lock as the host file says (read-only; capture_backend.py is its writer)."""
    out: dict[str, str] = {}
    for line in read_text(repo / "state" / "capture-backend").splitlines():
        key, sep, value = line.partition("=")
        if sep:
            out[key] = value
    return out


def stream_on_cmd() -> tuple[str, ...]:
    return (PY, "scripts/capture_backend.py", "to-console", "--sunshine-only")


def frame_cmd(out: Path) -> tuple[str, ...]:
    return (PY, "scripts/stream_frame.py", "--out", str(out))


SESSION = (1440, 900)  # SESSION_SIZE's default: the stream's size


def session_size(text: str) -> tuple[int, int]:
    """SESSION_SIZE ("WxH"; empty or malformed = compose's default 1440x900)."""
    match = re.fullmatch(r"([1-9]\d*)x([1-9]\d*)", text.strip())
    return (int(match.group(1)), int(match.group(2))) if match else SESSION


def parse_frame_report(text: str) -> dict[str, Any]:
    for line in reversed(text.strip().splitlines()):
        line = line.strip()
        if line.startswith("{"):
            try:
                data: dict[str, Any] = json.loads(line)
                return data
            except json.JSONDecodeError:
                break
    raise SetupError("stream_frame.py printed no report")


def judge_frame(rep: Mapping[str, Any], session: tuple[int, int] = SESSION) -> list[str]:
    """Problems with one grabbed frame ([] = it is the live Windows screen)."""
    problems = []
    if rep.get("source") != "bus":
        problems.append(
            f"the frame came from {rep.get('source')!r}, not the S2 frame bus: no live stream "
            "(its writer stopped heart-beating)"
        )
    if (rep.get("width"), rep.get("height")) != session:
        problems.append(f"the frame is {rep.get('width')}x{rep.get('height')}, not "
                        f"{session[0]}x{session[1]} (SESSION_SIZE)")  # fmt: skip
    dark = float(rep.get("dark_fraction", 0.0))
    if dark >= 0.98:
        problems.append(f"the frame is {dark:.0%} black: the PC's display is off or asleep, or "
                        "Sunshine captures a display nobody sees")  # fmt: skip
    return problems


STREAM_FIXES = (
    "A display: a monitor that stays ON, or the virtual display driver (the guide, step 5). A "
    "black stream is a display that is off, asleep or not the one Sunshine captures.",
    "Somebody is logged in on the PC and the screen lock and sleep are off (step 7).",
    "UDP 47998, 47999 and 48000 inbound for this server: the video comes back over UDP "
    "(the firewall rules of step 4 cover Sunshine's program for TCP AND UDP).",
    "The encoder: Sunshine's web page (on the PC) -> Troubleshooting shows its log. If no "
    "hardware encoder starts, set the `encoder` setting to software (Configuration).",
    "Still nothing: `scripts/dev.sh logs gamestream` (the S2 client's lines: s2spike: ...).",
)


# --- progress (resumable) -------------------------------------------------------------------------


def load_progress(path: Path | None = None) -> dict[str, Any]:
    path = path or PROGRESS  # resolved late (tests and the smoke run point it elsewhere)
    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) and data.get("version") == PROGRESS_VERSION else {}


def save_progress(data: Mapping[str, Any], path: Path | None = None) -> None:
    """Atomic (temp + rename), mode 600. It holds answers and step states only, never a secret."""
    path = path or PROGRESS
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps({**data, "version": PROGRESS_VERSION}, indent=2, sort_keys=True))
    os.chmod(tmp, 0o600)
    os.replace(tmp, path)


def step_log(step_id: str, index: int) -> Path:
    return SCRATCH / "logs" / f"{index:02d}-{step_id}.log"


# --- --check and --dry-run (read-only) ------------------------------------------------------------


@dataclass
class CheckReport:
    preflight: list[Check] = field(default_factory=list)
    env: list[tuple[str, str]] = field(default_factory=list)
    status: list[Check] = field(default_factory=list)


def lab_containers(runner: Runner) -> dict[str, str]:
    """{service: status} of this compose project's containers (read-only `docker ps`)."""
    res = runner(["docker", "ps", "-a", "--filter", f"label=com.docker.compose.project={project()}",
                  "--format", "{{.Label \"com.docker.compose.service\"}}\t{{.Status}}"],
                 timeout=20)  # fmt: skip
    out: dict[str, str] = {}
    for line in res.out.splitlines() if res.ok else []:
        svc, _, status = line.partition("\t")
        if svc:
            out[svc] = status
    return out


WANTED = ("db", "rathena", "desktop", "backend", "sniffer", "frontend-dev", "gamestream")


def run_check(
    runner: Runner,
    repo: Path = REPO,
    *,
    exec_ok: bool = True,
    root: Path = Path("/"),
    connect: Callable[[str, int], bool] | None = None,
    fetch: Callable[[str], bool] | None = None,
) -> CheckReport:
    """`--check`: everything read-only. `exec_ok=False` skips the one probe that runs inside a
    container (the pairing check) -- for a host where a live session must not be touched."""
    rep = CheckReport()
    connect, fetch = connect or tcp_open, fetch or http_ok
    rep.preflight, _ = preflight(runner, root=root, repo=repo)
    env = read_env(repo / ".env")
    if not env:
        rep.status.append(Check("env", ".env", "warn", "no .env yet", "./setup.sh creates it"))
        return rep
    rep.env = [(k, shown(k, env.get(k))) for k in CHECK_KEYS]
    ip = env.get("HOST_LAN_IP", "").strip()
    port_text = env.get("CONSOLE_PORT", "").strip()
    port = int(port_text) if port_text.isdigit() else DEFAULT_CONSOLE_PORT
    win = env.get("WIN_HOST", "").strip()
    path = "RDP (the desktop connects)" if rdp_configured(env) else "Sunshine only (RDP off)"
    rep.status.append(Check("path", "Display path", "info", path))
    if win:
        ports = probe_sunshine(win, connect)
        closed = [str(p) for p, ok in ports.items() if not ok]
        rep.status.append(Check(
            "sunshine", f"Sunshine on {win}", "fail" if closed else "ok",
            f"TCP {', '.join(closed)} closed" if closed else "TCP 47984, 47989, 48010 open",
            " ".join(SUNSHINE_FIXES[:2]) if closed else ""))  # fmt: skip
    else:
        rep.status.append(Check("sunshine", "Windows PC", "warn", "WIN_HOST is empty"))
    have = lab_containers(runner)
    for svc in WANTED:
        status = have.get(svc, "")
        up = status.startswith("Up") and "unhealthy" not in status
        rep.status.append(Check(f"svc-{svc}", f"service {svc}", "ok" if up else "warn",
                                status or "not created"))  # fmt: skip
    if ip:
        health = f"http://{ip}:{backend_port(env)}/health"
        rep.status.append(Check("health", "backend /health", "ok" if fetch(health) else "warn",
                                health))  # fmt: skip
        url = console_url(ip, port)
        rep.status.append(Check("console", "the console", "ok" if fetch(f"{url}/api/health")
                                else "warn", url))  # fmt: skip
    lock = lock_now(repo)
    rep.status.append(Check("lock", "capture lock", "info" if lock else "warn",
                            f"{lock.get('BACKEND')}/{lock.get('PHASE')} ({lock.get('REASON')})"
                            if lock else "no state/capture-backend yet"))  # fmt: skip
    if exec_ok:
        state = paired_state(runner)
        rep.status.append(Check("paired", "Sunshine pairing", "ok" if state == "paired"
                                else "warn", state))  # fmt: skip
    else:
        rep.status.append(Check("paired", "Sunshine pairing", "info", "not checked (--no-exec)"))
    return rep


def format_check(rep: CheckReport) -> str:
    mark = {"ok": "OK  ", "warn": "WARN", "fail": "FAIL", "info": "INFO"}
    lines = ["PRE-FLIGHT"]
    for c in rep.preflight:
        lines.append(f"  {mark[c.status]} {c.title}: {c.detail}")
        if c.fix and c.status in ("warn", "fail"):
            lines.append(f"       fix: {c.fix}")
    if rep.env:
        lines.append(".ENV (secrets hidden)")
        lines += [f"  {k:<26} {v}" for k, v in rep.env]
    lines.append("THE LAB")
    for c in rep.status:
        lines.append(f"  {mark[c.status]} {c.title}: {c.detail}")
        if c.fix and c.status in ("warn", "fail"):
            lines.append(f"       fix: {c.fix}")
    return "\n".join(lines)


def dry_run_lines(
    repo: Path,
    a: Answers,
    env: Mapping[str, str],
    *,
    gid: int | None,
    home: Path,
    runner: Runner | None = None,
) -> list[str]:
    """`--dry-run`: every write and command the wizard would run, in order; nothing runs. With a
    `runner`, each step's read-only done-check is evaluated and a step already done is marked
    (the wizard checks it and does not redo it)."""
    lines = []
    if not (repo / ".env").exists():
        lines.append("bash scripts/init_env.sh                      # creates .env, random secrets")
        env = {**read_env(repo / ".env.example"), **env}  # what init_env.sh starts from
    plan = planned_env(a, env, gid=gid, home=home)
    changes = env_changes(env, plan)
    if changes:
        pairs = " ".join(f"{k}={shown(k, v)}" for k, _, v in changes)
        lines.append(f"rotate_secrets.set_values: {pairs}")
    else:
        lines.append("# .env: nothing to change")
    lines.append(f"mkdir -p {plan['S2_REC_DIR']}")
    steps = install_plan(repo, {**env, **plan}, a)
    if runner is not None:
        steps += recreate_steps(services_to_recreate(changes, runner))
    for step in steps:
        note = "   # optional" if step.optional else ""
        if runner is not None and step.done is not None and step.done(runner):
            note += "   # already done: checked, not redone"
        lines.append(" ".join(step.cmd).replace(PY, "python") + note)
    lines.append(f"# wait for {console_url(a.server_ip, a.console_port)} and the backend's /health")
    if rdp_configured({**env, **plan}):
        lines.append(
            "# RDP is configured in .env: the Sunshine pairing and stream test are SKIPPED"
        )
        return lines
    lines.append("python scripts/capture_backend.py paired       # pairing skipped when paired")
    lines.append("python scripts/capture_backend.py pair <PIN>   # the PIN typed on the PC")
    lines.append(" ".join(stream_on_cmd()).replace(PY, "python"))
    lines.append(" ".join(frame_cmd(SCRATCH / "stream-test.png")).replace(PY, "python"))
    return lines


# --- the known limit of the Sunshine-only path (stated on the success page, as in the docs) -------

S2_LIMIT = (
    "WORKS on this path: you SEE the Windows PC in the console, and a person PLAYS through it "
    "(mouse and keyboard go through the input mux to the S2 client, then to Sunshine).",
    "Paste and file transfer: NOT on this path (they need the RDP session; the backend refuses "
    "paste in console mode).",
    "The bot's TYPED lines (chat, GM commands): REFUSED, every one. The UI gate types only after "
    "it has read the client from pixels with templates PROVEN on the same display path, and the "
    "S2 path's set (data/ui_anchors/s2) is not cut or proven anywhere yet "
    "(docs/operations/s2-gate-templates.md). It fails closed: nothing is typed. The typing-only "
    "foreground gate also refuses every bot key until its stream template is cut on this path.",
    "The bot's PROGRAMS (the dungeon runner, hunt, farm, the competition player): they do not "
    "run here. They refuse a console lock (their cursor references exist for RDP only) or stop "
    "at the UI gate at their start.",
    "A single bot click (e.g. `ro_agent.py click`): the mux passes it only in ASSIST or BOT (a "
    "person switches the mode) AND while the safety interlock is green (the servers confirmed on "
    "the Settings page, and today a game PC at 192.168.1.169: the environment set's Windows "
    "host), or in ASSIST during a short "
    "operator window. Everything else is refused.",
    "The lab itself runs on RDP. This path is the bot's designed primary path (ADR-0014); its "
    "UI-gate templates are the open step, and on a new host they must be cut from YOUR client "
    "(manual section 8).",
)
