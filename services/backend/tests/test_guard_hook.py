"""scripts/hooks/guard_docker.py: the PreToolUse hook that keeps heavy docker steps in the guard."""

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

HOOK = Path(__file__).resolve().parents[3] / "scripts" / "hooks" / "guard_docker.py"


@pytest.fixture(scope="module")
def hook() -> ModuleType:
    spec = importlib.util.spec_from_file_location("guard_docker", HOOK)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["guard_docker"] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.mark.parametrize(
    "command",
    [
        "docker build --target build -t x services/rathena",
        "docker buildx build .",
        "docker pull debian:trixie",
        "docker run --rm -it debian:trixie true",
        "docker restart poring-lab-backend-1",
        "docker start poring-lab-sniffer-1",
        "docker container restart poring-lab-backend-1",
        "docker image pull mariadb:11",
        "docker compose up -d backend",
        "docker compose -f compose.yaml -f compose.dev.yaml --profile sniffer up -d sniffer",
        "docker compose build desktop",
        "docker compose restart backend",
        "docker compose down",
        "docker compose -f compose.yaml config",
        "docker compose config --format json",
        "docker-compose up -d",
        "scripts/dev.sh up -d --no-build --no-deps --force-recreate desktop",
        "scripts/dev.sh restart backend",
        "./scripts/dev.sh --profile sniffer up -d sniffer",
        "bash scripts/dev.sh up -d backend",
        "scripts/dev.sh exec x true --force-recreate",
        "cd /x && docker compose up -d",
        "echo hi; docker build .",
        "true || docker pull x",
        "sudo -u root docker restart x",
        "env A=1 timeout 30 docker run x",
        "nohup docker compose up -d >/dev/null 2>&1 &",
        "bash -c 'docker compose up -d'",
        'sh -c "cd /tmp && docker build ."',
        "FOO=1 docker build .",
        "bash <<'EOF'\ndocker compose up -d\nEOF",
        "echo start\ndocker build .",
        # 2026-10-03: shlex's comment handling ate the newline, so these were ONE `echo` command
        "echo hi # a note\ndocker build .",
        "ls # it's a comment with a quote\ndocker compose up -d",
        "echo '#'; docker build .",
        'echo "#" ; docker pull x',
        "echo $# ; docker pull x",
    ],
)
def test_refused(hook: ModuleType, command: str) -> None:
    assert hook.classify(command), command


@pytest.mark.parametrize(
    "command",
    [
        "docker ps",
        "docker logs --since 1m poring-lab-desktop-1",
        "docker exec poring-lab-desktop-1 supervisorctl -c /etc/supervisor/x.conf stop rdp",
        "docker inspect -f '{{.State.Health.Status}}' poring-lab-backend-1",
        "docker images",
        "docker tag poring-lab/desktop:local poring-lab/desktop:freerdp-3.15",
        "docker stats --no-stream",
        "docker compose -f compose.yaml config -q",
        "docker compose -f compose.yaml -f compose.dev.yaml --profile core config --no-interpolate",
        "docker compose ps",
        "docker compose logs backend",
        "scripts/dev.sh ps",
        "scripts/dev.sh logs -f frontend-dev",
        "scripts/dev.sh stop frontend-dev",
        "python3 scripts/guarded_build.py --sustain 30 --spike 25 build:desktop",
        "python3 scripts/guarded_build.py --sustain 30 --spike 25 recreate:desktop@90",
        "uv run python - <<'EOF'\nimport subprocess  # docker build . is only a string here\nEOF",
        "cat <<'EOF' > /dev/shm/x.txt\ndocker compose up -d\nEOF",
        "grep -n 'docker build' README.md",
        "echo 'docker compose up -d'",
        "git commit -m 'docs: docker build guard'",
        "ls # docker build .",
        "# docker compose up -d\nls",
        "rg 'foo#bar' README.md",
    ],
)
def test_allowed(hook: ModuleType, command: str) -> None:
    assert hook.classify(command) is None, command


def test_hook_exit_codes_and_message() -> None:
    def run(payload: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(HOOK)], input=payload, capture_output=True, text=True
        )

    blocked = run(json.dumps({"tool_name": "Bash", "tool_input": {"command": "docker pull x"}}))
    assert blocked.returncode == 2
    assert "guarded_build.py" in blocked.stderr
    ok = run(json.dumps({"tool_name": "Bash", "tool_input": {"command": "docker ps"}}))
    assert ok.returncode == 0
    assert run("not json").returncode == 0  # unreadable input: fail open
