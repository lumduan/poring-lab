"""scripts/lab_env.py (Batt 2026-11-17: "nothing locked; run on any hardware"): every install value
comes from the environment, else .env, else a default -- and compose.yaml's defaults are the SAME
defaults, so a host tool and a container never disagree about a name, a port or a subnet."""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts"))

import lab_env as le  # noqa: E402

NO_ENV: dict[str, str] = {}
# The tracked compose files only: compose.override.yaml is this machine's own (gitignored; the lab's
# holds its NAS address), never shipped
COMPOSE_FILES = sorted(f for f in ROOT.glob("compose*.yaml") if f.name != "compose.override.yaml")


def _defaults_in(text: str, key: str) -> set[str]:
    return set(re.findall(r"\$\{" + re.escape(key) + r":-([^}$]*)\}", text))


@pytest.fixture
def no_dotenv(tmp_path: Path) -> Path:
    return tmp_path / "absent.env"


def test_the_lab_values_are_the_defaults(no_dotenv: Path) -> None:
    assert le.project(NO_ENV, no_dotenv) == "poring-lab"
    assert le.container("backend", NO_ENV, no_dotenv) == "poring-lab-backend-1"
    assert le.network("default", NO_ENV, no_dotenv) == "poring-lab_default"
    assert le.volume("db-data", NO_ENV, no_dotenv) == "poring-lab_db-data"
    assert le.image("sniffer", env=NO_ENV, dotenv=no_dotenv) == "poring-lab/sniffer:local"
    assert le.shm("tmp", NO_ENV, no_dotenv) == Path("/dev/shm/poring-lab-tmp")
    assert le.ports(NO_ENV, no_dotenv) == {
        "RATHENA_LOGIN_PORT": 6900, "RATHENA_CHAR_PORT": 6121, "RATHENA_MAP_PORT": 5121,
        "RATHENA_WEB_PORT": 8888, "NOVNC_PORT": 6080, "BACKEND_PORT": 8000, "CONSOLE_PORT": 3000,
    }  # fmt: skip
    assert le.subnet("LAB_NET_PREFIX", NO_ENV, no_dotenv) == "10.210.96.0/24"
    assert le.subnet("LAB_AGENT_NET_PREFIX", NO_ENV, no_dotenv) == "10.210.97.0/24"
    assert le.ingest_peer(NO_ENV, no_dotenv) == "10.210.96.6"


def test_another_install_changes_every_name(no_dotenv: Path) -> None:
    env = {"COMPOSE_PROJECT_NAME": "lab2", "RATHENA_LOGIN_PORT": "7900",
           "LAB_NET_PREFIX": "10.210.120", "LAB_AGENT_NET_PREFIX": "10.210.121"}  # fmt: skip
    assert le.container("rathena", env, no_dotenv) == "lab2-rathena-1"
    assert le.network("agent", env, no_dotenv) == "lab2_agent"
    assert le.image("backend", env=env, dotenv=no_dotenv) == "lab2/backend:local"
    assert le.shm("detect", env, no_dotenv) == Path("/dev/shm/lab2-detect")
    assert le.port("RATHENA_LOGIN_PORT", env, no_dotenv) == 7900
    assert le.port("RATHENA_CHAR_PORT", env, no_dotenv) == 6121  # unset keys keep their default
    assert le.ingest_peer(env, no_dotenv) == "10.210.120.6"


def test_the_environment_wins_over_dotenv_and_empty_is_unset(tmp_path: Path) -> None:
    dotenv = tmp_path / ".env"
    dotenv.write_text("COMPOSE_PROJECT_NAME=fromfile\nBACKEND_PORT=\nLAB_STORE_DIR=/srv/store\n")
    assert le.project({}, dotenv) == "fromfile"
    assert le.project({"COMPOSE_PROJECT_NAME": "fromenv"}, dotenv) == "fromenv"
    assert le.project({"COMPOSE_PROJECT_NAME": ""}, dotenv) == "fromfile"
    assert le.port("BACKEND_PORT", {}, dotenv) == 8000
    assert le.store_dir({}, dotenv) == Path("/srv/store")
    assert le.store("archive", "models", env={}, dotenv=dotenv) == Path("/srv/store/archive/models")


def test_the_store_defaults_to_the_home_folder(no_dotenv: Path, tmp_path: Path) -> None:
    assert le.store_dir(NO_ENV, no_dotenv, home=tmp_path) == tmp_path / "poring-lab-store"
    with pytest.raises(SystemExit, match="absolute"):
        le.store_dir({"LAB_STORE_DIR": "relative/dir"}, no_dotenv)


@pytest.mark.parametrize(("key", "raw"), [
    ("COMPOSE_PROJECT_NAME", "Poring Lab"), ("COMPOSE_PROJECT_NAME", "-lab"),
    ("COMPOSE_PROJECT_NAME", "lab/2"), ("RATHENA_MAP_PORT", "0"), ("RATHENA_MAP_PORT", "70000"),
    ("BACKEND_PORT", "80a"), ("LAB_NET_PREFIX", "192.168.96"), ("LAB_NET_PREFIX", "10.211.5"),
    ("LAB_NET_PREFIX", "10.210"), ("LAB_AGENT_NET_PREFIX", "10.210.300"),
])  # fmt: skip
def test_bad_values_are_refused_never_replaced(key: str, raw: str, no_dotenv: Path) -> None:
    env = {key: raw}
    with pytest.raises(SystemExit):
        if key == "COMPOSE_PROJECT_NAME":
            le.project(env, no_dotenv)
        elif key in le.PORTS:
            le.port(key, env, no_dotenv)
        else:
            le.net_prefix(key, env, no_dotenv)


@pytest.mark.parametrize("key", sorted(le.PORTS))
def test_compose_uses_the_same_port_defaults(key: str) -> None:
    found: set[str] = set()
    for f in COMPOSE_FILES:
        found |= _defaults_in(f.read_text(), key)
    assert found == {str(le.PORTS[key])}, (key, found)


@pytest.mark.parametrize("key", sorted(le.NETS))
def test_compose_uses_the_same_subnet_defaults(key: str) -> None:
    text = (ROOT / "compose.yaml").read_text()
    assert _defaults_in(text, key) == {le.NETS[key]}


def test_compose_names_every_image_of_ours_by_the_project() -> None:
    """No image of ours is fixed to the lab's name: two copies on one host never share a tag."""
    for f in COMPOSE_FILES:
        for line in f.read_text().splitlines():
            m = re.match(r"\s*image:\s*(\S+)", line)
            if m is None or line.lstrip().startswith("#"):
                continue
            ref = m.group(1)
            if ref.startswith(("mariadb:", "node:")):
                continue  # public images
            assert ref.startswith("${COMPOSE_PROJECT_NAME:-poring-lab}/"), (f.name, ref)
    assert "\nname: ${COMPOSE_PROJECT_NAME:-poring-lab}\n" in (ROOT / "compose.yaml").read_text()


def test_compose_fixes_no_lan_address_and_no_subnet() -> None:
    """The one LAN range left is VIEWER_NETWORKS' DEFAULT (a range for hand installs; ./setup.sh
    writes the host's own LAN there)."""
    for f in COMPOSE_FILES:
        for n, line in enumerate(f.read_text().splitlines(), 1):
            code = line.split("#", 1)[0].replace("${VIEWER_NETWORKS:-192.168.0.0/16}", "")
            assert not re.search(r"192\.168\.\d+\.\d+", code), (f.name, n, line)
            assert not re.search(r"(?<![-{])10\.210\.\d+\.\d+", code), (f.name, n, line)


def test_the_store_volume_is_the_store_folder() -> None:
    text = (ROOT / "compose.yaml").read_text()
    assert "device: ${LAB_STORE_DIR:-${HOME}/poring-lab-store}" in text
    assert le.STORE_DEFAULT == "poring-lab-store"


def test_dev_sh_passes_the_same_project_name() -> None:
    text = (ROOT / "scripts" / "dev.sh").read_text()
    assert 'exec docker compose -p "${PROJECT}"' in text
    assert "COMPOSE_PROJECT_NAME" in text and 'PROJECT="${PROJECT:-poring-lab}"' in text


def test_env_example_lists_every_install_key() -> None:
    example = (ROOT / ".env.example").read_text()
    for key in [
        le.PROJECT_KEY,
        le.STORE_KEY,
        le.DETECTOR_KEY,
        *le.PORTS,
        *le.NETS,
        "VISION_WORKER_MEM",
    ]:
        assert re.search(rf"^{key}=", example, re.M), key


def test_rathena_listens_on_the_ports_compose_publishes() -> None:
    """char and map are ADVERTISED to the game client: each server listens on the very number
    compose publishes (X:X), from the same RATHENA_*_PORT the entrypoint renders into the conf
    (rAthena's keys at the pinned commit: login_port, char_port, map_port, web_port)."""
    tmpl = ROOT / "services" / "rathena" / "conf" / "import"
    want = {
        "login_conf.txt.tmpl": {"login_port: ${RATHENA_LOGIN_PORT}"},
        "char_conf.txt.tmpl": {
            "login_port: ${RATHENA_LOGIN_PORT}",
            "char_port: ${RATHENA_CHAR_PORT}",
        },
        "map_conf.txt.tmpl": {"char_port: ${RATHENA_CHAR_PORT}", "map_port: ${RATHENA_MAP_PORT}"},
        "web_conf.txt.tmpl": {"web_port: ${RATHENA_WEB_PORT}"},
    }
    for name, lines in want.items():
        text = (tmpl / name).read_text().splitlines()
        assert lines <= set(text), name
    entry = (ROOT / "services" / "rathena" / "entrypoint.sh").read_text()
    for key in ("RATHENA_LOGIN_PORT", "RATHENA_CHAR_PORT", "RATHENA_MAP_PORT", "RATHENA_WEB_PORT"):
        assert f"${{{key}:={le.PORTS[key]}}}" in entry, key  # the same default as lab_env
        assert f"${{{key}}}" in entry.split("vars='", 1)[1], key  # substituted into the templates
    # smoke_test.sh greps this line's prefix
    assert 'log "clients will be sent to char ${HOST_LAN_IP}:${RATHENA_CHAR_PORT} and map' in entry
    compose = (ROOT / "compose.yaml").read_text()
    for key in ("RATHENA_LOGIN_PORT", "RATHENA_CHAR_PORT", "RATHENA_MAP_PORT", "RATHENA_WEB_PORT"):
        v = f"${{{key}:-{le.PORTS[key]}}}"
        assert f":{v}:{v}" in compose, key


# --- the storage folder in the host code (Batt 2026-11-17: "most users have no NAS") -------------

LAB_NAS = "/mnt/poring-lab-datasets"  # the lab's own LAB_STORE_DIR (its NAS automount)
CODE_ROOTS = (("scripts", "*.py"), ("scripts", "*.sh"), ("services", "*/src/**/*.py"),
              ("packages", "*/src/**/*.py"))  # fmt: skip


def test_no_host_code_hard_codes_the_labs_nas() -> None:
    """Every host-side path into long-term storage comes from LAB_STORE_DIR (lab_env.store_dir /
    store). The lab keeps its folder by setting LAB_STORE_DIR to its NAS mount in .env; the code
    names it nowhere, not even in a comment or a help string."""
    hits = []
    for top, pattern in CODE_ROOTS:
        for path in sorted((ROOT / top).rglob(pattern)):
            if "__pycache__" in path.parts or not path.is_file():
                continue
            for n, line in enumerate(path.read_text(errors="replace").splitlines(), 1):
                if LAB_NAS in line:
                    hits.append(f"{path.relative_to(ROOT)}:{n}")
    assert hits == []


def test_the_host_scripts_follow_the_storage_folder(tmp_path: Path) -> None:
    """A positive case through the real import path: with LAB_STORE_DIR set, the converted
    scripts' roots (module constants, argparse defaults) all land in that folder, subpaths kept."""
    store = tmp_path / "store"
    probe = (
        "import sys; sys.path.insert(0, 'scripts');"
        "import battle_log, dataset_ship, drop_blobs, eval_latency, migration_check, mvp_profiles,"
        " warp_watch;"
        "print(dataset_ship.NAS_ROOT); print(battle_log.RECORDINGS); print(drop_blobs.REC_ROOT);"
        "print(warp_watch.NAS_ROOT); print(mvp_profiles._X1); print(eval_latency.HOST);"
        "print(migration_check.NAS_MOUNTS[0]);"
        "print(dataset_ship.parser().parse_args(['status']).dest)"
    )
    env = {**os.environ, "LAB_STORE_DIR": str(store), "PYTHONDONTWRITEBYTECODE": "1"}
    out = subprocess.run([sys.executable, "-c", probe], cwd=ROOT, env=env, capture_output=True,
                         text=True, timeout=120, check=True).stdout.split()  # fmt: skip
    assert out == [str(store), f"{store}/hunt-recordings", f"{store}/hunt-recordings",
                   f"{store}/detector-collection", f"{store}/scratch-archive/2026-11-05/x1",
                   f"{store}/", str(store), str(store)]  # fmt: skip


def test_the_cache_runbook_reads_the_store_through_lab_env(tmp_path: Path) -> None:
    """scripts/runbooks/cache-day.sh's resume check reads the same folder as build_frame_cache's
    --out default (<store>/.framecache): lab_env itself resolves it; a bad value stops the run."""
    text = (ROOT / "scripts" / "runbooks" / "cache-day.sh").read_text()
    lines = text.splitlines()
    start = next(i for i, x in enumerate(lines) if x.startswith("STORE=$(python3 "))
    snippet = "\n".join([*lines[start : start + 3], 'echo "$STORE"'])
    assert '[ -e "$STORE/.framecache/$ID/progress.json" ] && extra="--resume"' in text
    run = {**os.environ, "LAB_STORE_DIR": str(tmp_path / "s"), "PYTHONDONTWRITEBYTECODE": "1"}
    got = subprocess.run(["bash", "-c", snippet], cwd=ROOT, env=run, capture_output=True,
                         text=True, timeout=60)  # fmt: skip
    assert (got.returncode, got.stdout.strip()) == (0, str(tmp_path / "s"))
    run["LAB_STORE_DIR"] = "relative/s"
    got = subprocess.run(["bash", "-c", snippet], cwd=ROOT, env=run, capture_output=True,
                         text=True, timeout=60)  # fmt: skip
    assert got.returncode == 1 and "absolute" in got.stderr
