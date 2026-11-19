"""No host tool names a Docker object after the LAB (Batt 2026-11-17: "every user's hardware is
different; our project should run on any hardware, in containers; don't lock an IP or anything").

A second copy of poring-lab on one host runs under another COMPOSE_PROJECT_NAME. Every container,
network, volume and image name of a copy starts with it, and so do the copy's own RAM directories
that compose mounts (/dev/shm/<project>-detect, -hwshm, -mediarec) and its capture-backend flock.
A script that still said "poring-lab-backend-1" would act on the LIVE lab from the second copy.

So: (1) no script, package or container-side shell script spells a lab Docker name literally
(scripts/lab_env.py builds them; scripts/lab_project.sh for bash), (2) the scripts loaded under
another project name use that name everywhere, and (3) the bash snippet reads the name in the same
order as lab_env (the environment, else .env, else poring-lab). The lab's own name stays the
default, so the live lab's names are exactly what they were."""

from __future__ import annotations

import importlib.util
import re
import shutil
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[3]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

import lab_env as le  # noqa: E402

# A lab Docker name spelled out: a container ("poring-lab-<svc>-1"), a network or volume
# ("poring-lab_<name>"), one of our images ("poring-lab/<name>:<tag>"), a compose project filter or
# comparison, or a project constant.
LITERAL = re.compile(
    r"poring-lab-[a-z][a-z0-9-]*-1\b|poring-lab_[a-z]|poring-lab/[a-z][a-z0-9-]*:"
    r"|compose\.project=poring-lab|[=!]= [\"']poring-lab[\"']|PROJECT = [\"']poring-lab[\"']"
)
SUFFIXES = {".py", ".sh", ".service", ".yaml", ".yml", ".toml", ".json", ""}
# The one place the default lives (plus the root helper, which is installed alone and carries a
# copy of the default; it names no container, so LITERAL does not match it).
ALLOWED = {SCRIPTS / "lab_env.py"}
OTHER = "lab2"  # a second copy's project name


@pytest.fixture(autouse=True)
def _scratch(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """guarded_build makes its LOGDIR at import: a test's own TMPDIR, never /dev/shm/lab2-*."""
    monkeypatch.setenv("TMPDIR", str(tmp_path))


def _tracked(root: Path) -> list[Path]:
    return [p for p in sorted(root.rglob("*")) if p.is_file() and "__pycache__" not in p.parts
            and "_generated" not in p.parts and p.suffix in SUFFIXES]  # fmt: skip


def _sources() -> list[Path]:
    files = _tracked(SCRIPTS)
    for pkg in sorted((ROOT / "packages").iterdir()):
        if (pkg / "src").is_dir():
            files += _tracked(pkg / "src")
    for svc in sorted((ROOT / "services").iterdir()):
        if svc.name == "frontend":  # TypeScript; it names no Docker object
            continue
        for sub in ("bin", "src"):
            if (svc / sub).is_dir():
                files += _tracked(svc / sub)
        files += sorted(svc.glob("*.sh"))
    return [f for f in files if f not in ALLOWED]


def test_no_script_names_a_lab_docker_object_literally() -> None:
    hits = []
    for path in _sources():
        try:
            text = path.read_text()
        except UnicodeDecodeError:
            continue
        for n, line in enumerate(text.splitlines(), 1):
            if LITERAL.search(line):
                hits.append(f"{path.relative_to(ROOT)}:{n}: {line.strip()}")
    assert not hits, "use scripts/lab_env.py (bash: scripts/lab_project.sh):\n" + "\n".join(hits)


def test_the_literal_pattern_catches_each_kind_of_name() -> None:
    """A positive case for each kind: a zero from a pattern that cannot see a name proves
    nothing."""
    for line in ('BACKEND = "poring-lab-backend-1"', "docker exec poring-lab-vision-worker-1 true",
                 'NET = "poring-lab_default"', 'vol = "poring-lab_captures"',
                 'IMAGE = "poring-lab/rathena-build:local"', "FROM poring-lab/desktop:local",
                 '"label=com.docker.compose.project=poring-lab"', 'if project == "poring-lab":',
                 'PROJECT = "poring-lab"', "C=poring-lab-media-rec-1"):  # fmt: skip
        assert LITERAL.search(line), line
    for line in ("/dev/shm/poring-lab-tmp/gat", "/mnt/poring-lab-datasets/archive",
                 '"poring-lab shell"', "~/poring-lab-rec/.media-rec", "poring-lab-flowrun.service",
                 'PROJECT_DEFAULT = "poring-lab"'):  # fmt: skip
        assert not LITERAL.search(line), line


def test_no_dockerfile_builds_on_the_labs_own_image() -> None:
    for dockerfile in sorted((ROOT / "services").glob("*/Dockerfile*")):
        for line in dockerfile.read_text().splitlines():
            if line.startswith("FROM "):
                assert not LITERAL.search(line), (dockerfile.name, line)
    text = (ROOT / "services" / "gamestream" / "Dockerfile").read_text()
    head = text.split("\nFROM ", 1)[0]  # a global ARG: declared before the first FROM
    assert "\nARG LAB_PROJECT=poring-lab\n" in head
    assert "\nFROM ${LAB_PROJECT}/desktop:local\n" in text


# --- the scripts, loaded as a second copy -----------------------------------------------------


def _load(monkeypatch: pytest.MonkeyPatch, script: str, project: str = OTHER) -> ModuleType:
    """``scripts/<script>`` loaded fresh under COMPOSE_PROJECT_NAME=``project`` (its own module
    name, so the cached copies other tests use are untouched)."""
    monkeypatch.setenv(le.PROJECT_KEY, project)
    path = SCRIPTS / script
    name = f"names_{project}_{path.stem.replace('-', '_')}"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, name, mod)
    spec.loader.exec_module(mod)
    return mod


def test_guarded_build_names_everything_after_its_project(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("TMPDIR", raising=False)  # its logs then go to THIS copy's scratch
    made = not Path("/dev/shm/lab2-tmp").exists()
    gb = _load(monkeypatch, "guarded_build.py")
    if made:  # the import makes its LOGDIR: leave no test folder in /dev/shm
        shutil.rmtree("/dev/shm/lab2-tmp", ignore_errors=True)
    # 2026-11-19: the live copy's detect server logged into the lab's scratch, and its Run helper
    # (flow_run.SERVE_LOG, in its own) waited for a "listening" line that never came there
    assert str(gb.LOGDIR) == "/dev/shm/lab2-tmp" == str(_load(monkeypatch, "flow_run.py").SCRATCH)
    assert gb.COMPOSE_PROJECT == OTHER
    assert gb.COMPOSE == ["docker", "compose", "-p", OTHER]
    assert (gb.BACKEND, gb.WORKER) == ("lab2-backend-1", "lab2-vision-worker-1")
    assert gb.REPLAY_IMAGE == "lab2/sniffer:local"
    assert {img for _svc, img, _owner in gb.VOLUME_DUMP.values()} >= {"lab2/sniffer:local"}
    assert gb.DETECT_DIR == Path("/dev/shm/lab2-detect") == gb.WORKER_MOUNTS["/detect"]
    assert gb.EXEC_HOST == b"docker\x00exec\x00lab2-vision-worker-1\x00"
    # every raw compose argv carries the project right after `compose`
    assert gb.worker_start_cmd()[:4] == gb.worker_stop_cmd()[:4] == gb.COMPOSE
    run = gb.parse_step("run:vision@60=python -c pass")
    assert gb.run_cmd(run)[2:6] == gb.COMPOSE
    assert gb.container_name(run).startswith("lab2-vision-run-")
    dump, count_vol, _ = gb.volume_cmds("captures", "/dev/shm/x.tgz")
    assert "lab2_captures:/v:ro" in dump[2] and "lab2/sniffer:local" in count_vol[2]
    assert gb.exec_cmd(gb.parse_step("execdev:vision@5=true"))[4] == "lab2-vision-worker-1"


def test_guarded_build_s_compose_steps_carry_the_project(monkeypatch: pytest.MonkeyPatch) -> None:
    gb = _load(monkeypatch, "guarded_build.py")
    calls: list[list[str]] = []
    monkeypatch.setattr(gb, "cgroup_paths", lambda: [])
    monkeypatch.setattr(gb, "run_process",
                        lambda label, cmd, guard, env=None: calls.append(cmd) or True)  # fmt: skip
    monkeypatch.setattr(sys, "argv", ["guarded_build.py", "build:desktop", "pull:db"])
    assert gb.main() == 0
    assert [c[:4] for c in calls] == [["docker", "compose", "-p", OTHER]] * 2
    ps: list[list[str]] = []

    def fake_run(cmd: list[str], **_kw: object) -> subprocess.CompletedProcess[str]:
        ps.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(gb.subprocess, "run", fake_run)
    assert gb.dev_overlay_active() is False
    assert "label=com.docker.compose.project=lab2" in ps[0]


@pytest.mark.parametrize(("script", "attrs"), [
    ("backend_addr.py", {"BACKEND": "lab2-backend-1", "DEFAULT_NETWORK": "lab2_default"}),
    ("capture_backend.py", {"DESKTOP": "lab2-desktop-1", "BACKEND": "lab2-backend-1",
                            "GAMESTREAM": "lab2-gamestream-1"}),
    ("cleanroom.py", {"GAMESTREAM": "lab2-gamestream-1", "BACKEND": "lab2-backend-1",
                      "DESKTOP": "lab2-desktop-1"}),
    ("db_move.py", {"DB": "lab2-db-1", "RATHENA": "lab2-rathena-1"}),
    ("gen_packet_tables.py", {"IMAGE": "lab2/rathena-build:local"}),
    ("media_rec.py", {"CONTAINER": "lab2-media-rec-1", "CTL": Path("/dev/shm/lab2-mediarec")}),
    ("migration_check.py", {"DB": "lab2-db-1", "LAB_PREFIX": "lab2-",
                            "IMAGE_SUBSTITUTES": {"lab2/vision:local": "lab2/vision-intel:local"}}),
    ("rotate_secrets.py", {"DB": "lab2-db-1", "DB_TH": "lab2-db-th-1"}),
    ("scrub_check.py", {"BACKEND": "lab2-backend-1"}),
    ("unit_detector.py", {"GPU_DIR": Path("/dev/shm/lab2-detect"),
                          "GPU_SOCKET": Path("/dev/shm/lab2-detect/detect.sock")}),
    ("ro_agent.py", {"BACKEND": "lab2-backend-1", "DB": "lab2-db-1"}),
    ("measure_motion.py", {"DISPLAY_PATH": ("lab2-desktop-1", "lab2-gamestream-1")}),
    ("record_session.py", {"GAMESTREAM": "lab2-gamestream-1", "BACKEND": "lab2-backend-1",
                           "MEDIA_REC": "lab2-media-rec-1"}),
])  # fmt: skip
def test_each_script_names_its_containers_after_its_project(
    monkeypatch: pytest.MonkeyPatch, script: str, attrs: dict[str, object]
) -> None:
    mod = _load(monkeypatch, script)
    assert {k: getattr(mod, k) for k in attrs} == attrs


def test_the_sniffer_map_and_the_samplers_follow_the_project(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ls = _load(monkeypatch, "lab_servers.py")
    assert ls.SNIFFERS == {"lab-rathena": "lab2-sniffer-1", "lab-rathena-th": "lab2-sniffer-th-1"}
    ro = _load(monkeypatch, "ro_agent.py")
    assert (ro.PROFILES["kro"].db, ro.PROFILES["th"].db) == ("lab2-db-1", "lab2-db-th-1")
    ps = _load(monkeypatch, "pressure_sampler.py")
    assert all(n.startswith("lab2-") and n.endswith("-1") for n in ps.LAB) and len(ps.LAB) == 9
    vm = _load(monkeypatch, "verify_mount.py")
    seen: list[list[str]] = []

    def fake(cmd: list[str]) -> subprocess.CompletedProcess[str]:
        seen.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, "true\n", "")

    assert vm.container_of("backend", fake) == "lab2-backend-1" and seen[0][-1] == "lab2-backend-1"


def test_the_per_copy_ram_paths_follow_the_project(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CAPTURE_BACKEND_FLOCK", raising=False)
    monkeypatch.delenv("SETUP_SCRATCH", raising=False)
    cb = _load(monkeypatch, "capture_backend.py")
    assert str(cb.FLOCK) == "/dev/shm/lab2-tmp/capture-backend.flock"
    core = _load(monkeypatch, "setup_core.py")
    assert str(core.SCRATCH) == "/dev/shm/lab2-tmp/setup"
    # the lab's (the default): exactly the paths they were
    cb0 = _load(monkeypatch, "capture_backend.py", le.PROJECT_DEFAULT)
    assert str(cb0.FLOCK) == "/dev/shm/poring-lab-tmp/capture-backend.flock"
    monkeypatch.setenv("CAPTURE_BACKEND_FLOCK", "/dev/shm/elsewhere.flock")  # the override stays
    assert str(_load(monkeypatch, "capture_backend.py").FLOCK) == "/dev/shm/elsewhere.flock"


def test_setup_core_checks_its_own_projects_containers_and_images(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    core = _load(monkeypatch, "setup_core.py")
    seen: list[list[str]] = []

    class Res:
        ok, out = True, ""

    def runner(cmd: list[str], **_kw: object) -> Res:
        seen.append(cmd)
        return Res()

    core.lab_containers(runner)
    assert "label=com.docker.compose.project=lab2" in seen[-1]
    core.container_state(runner, "backend")
    assert seen[-1][-1] == "lab2-backend-1"
    assert core.project() == OTHER


def test_the_vram_helper_writes_its_copys_directory() -> None:
    path = SCRIPTS / "host" / "poring-lab-vram.py"
    spec = importlib.util.spec_from_file_location("names_vram", path)
    assert spec and spec.loader
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    assert helper.out_dir({}) == Path("/dev/shm/poring-lab-hwshm")  # the lab's, as before
    assert helper.out_dir({"COMPOSE_PROJECT_NAME": OTHER}) == Path("/dev/shm/lab2-hwshm")
    for bad in ("../etc", "Lab", "a/b", "-x"):
        with pytest.raises(SystemExit):
            helper.out_dir({"COMPOSE_PROJECT_NAME": bad})
    assert helper.PROJECT_DEFAULT == le.PROJECT_DEFAULT
    assert helper.PROJECT_RE.pattern == le.PROJECT_RE.pattern


# --- bash: scripts/lab_project.sh -----------------------------------------------------------------


def _bash_project(copy: Path, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["bash", str(copy / "scripts" / "lab_project.sh")], env=env,
                          capture_output=True, text=True, check=False)  # fmt: skip


@pytest.mark.parametrize(("environ", "dotenv", "want"), [
    ({}, None, "poring-lab"),
    ({}, "A=1\nCOMPOSE_PROJECT_NAME=fromfile\nCOMPOSE_PROJECT_NAME=second\n", "fromfile"),
    ({}, "COMPOSE_PROJECT_NAME=\n", "poring-lab"),
    ({"COMPOSE_PROJECT_NAME": "fromenv"}, "COMPOSE_PROJECT_NAME=fromfile\n", "fromenv"),
    ({"COMPOSE_PROJECT_NAME": ""}, "COMPOSE_PROJECT_NAME=fromfile\n", "fromfile"),
])  # fmt: skip
def test_the_bash_snippet_reads_the_name_like_lab_env(
    tmp_path: Path, environ: dict[str, str], dotenv: str | None, want: str
) -> None:
    (tmp_path / "scripts").mkdir()
    shutil.copy(SCRIPTS / "lab_project.sh", tmp_path / "scripts" / "lab_project.sh")
    env_file = tmp_path / ".env"
    if dotenv is not None:
        env_file.write_text(dotenv)
    res = _bash_project(tmp_path, {"PATH": "/usr/bin:/bin", **environ})
    assert res.returncode == 0, res.stderr
    assert res.stdout.strip() == want == le.project(environ, env_file)


def test_the_bash_snippet_refuses_a_bad_name(tmp_path: Path) -> None:
    (tmp_path / "scripts").mkdir()
    shutil.copy(SCRIPTS / "lab_project.sh", tmp_path / "scripts" / "lab_project.sh")
    res = _bash_project(tmp_path, {"PATH": "/usr/bin:/bin", "COMPOSE_PROJECT_NAME": "Bad Name"})
    assert res.returncode == 64 and res.stdout == "" and "COMPOSE_PROJECT_NAME" in res.stderr


@pytest.mark.parametrize(("script", "line"), [
    ("rdp_reconnect.sh", 'C="$(lab_project)-desktop-1"'),
    ("gen_protocol.sh", 'FRONTEND_DEV="$(lab_project)-frontend-dev-1"'),
])  # fmt: skip
def test_the_bash_tools_take_their_container_from_the_snippet(script: str, line: str) -> None:
    text = (SCRIPTS / script).read_text()
    assert "lab_project.sh" in text and line in text


def test_a_copy_s_run_helper_and_readers_keep_their_own_ram(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """2026-11-19 (Batt: a LIVE copy beside the dev lab on this host): the Run helper's scratch
    (its Stop file, run folders, logs), its Run labels (the byte-pinned runner writes every copy's
    sessions in one folder, named for the label), the window-find file and the route plans are the
    copy's own. The lab keeps its names."""
    monkeypatch.delenv("ROUTE_PLAN_DIR", raising=False)
    monkeypatch.delenv("PORING_PANELS_FILE", raising=False)
    fr = _load(monkeypatch, "flow_run.py")
    assert (str(fr.SCRATCH), fr.PROJECT_LABEL) == ("/dev/shm/lab2-tmp", "flowplay-lab2")
    for script in ("ro_agent.py", "chat_window.py"):
        assert str(_load(monkeypatch, script).PANELS_FILE) == "/dev/shm/lab2-tmp/panels.json"
    assert str(_load(monkeypatch, "route_plan.py").PLAN_DIR) == "/dev/shm/lab2-route"
    lab = _load(monkeypatch, "flow_run.py", project=le.PROJECT_DEFAULT)
    assert (str(lab.SCRATCH), lab.PROJECT_LABEL) == ("/dev/shm/poring-lab-tmp", "flowplay")
    rp = _load(monkeypatch, "route_plan.py", project=le.PROJECT_DEFAULT)
    assert str(rp.PLAN_DIR) == "/dev/shm/poring-lab-route"
