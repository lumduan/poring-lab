"""scripts/hooks/guard_bigread.py: no whole-file reads of session transcripts or big local files."""

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

HOOK = Path(__file__).resolve().parents[3] / "scripts" / "hooks" / "guard_bigread.py"


@pytest.fixture
def hook(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location("guard_bigread", HOOK)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["guard_bigread"] = mod
    spec.loader.exec_module(mod)
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setattr(mod, "BIG_BYTES", 1024)

    def fake_fs(path: str) -> str:
        if "/ram/" in path:
            return "tmpfs"
        if "/nas/" in path:
            return "nfs4"
        return "ext4"

    monkeypatch.setattr(mod, "fs_type", fake_fs)
    return mod


@pytest.fixture
def paths(tmp_path: Path) -> dict[str, str]:
    home = tmp_path / "home"
    transcript = home / ".claude" / "projects" / "proj" / "session.jsonl"
    transcript.parent.mkdir(parents=True)
    transcript.write_text('{"x": 1}\n')  # small: a transcript is refused whatever its size
    subagent = home / ".claude" / "projects" / "proj" / "subagents" / "agent-1.jsonl"
    subagent.parent.mkdir()
    subagent.write_text("{}\n")
    tasks = tmp_path / "scratch" / "tasks"
    tasks.mkdir(parents=True)
    (tasks / "agent.output").symlink_to(subagent)  # how a subagent's output file looks
    (tasks / "bash.output").write_text("build log\n")  # a Bash background output: a plain file
    data = tmp_path / "data"
    data.mkdir()
    (data / "big.csv").write_bytes(b"x" * 4096)
    (data / "small.csv").write_text("a,b\n")
    for fs in ("ram", "nas"):
        (tmp_path / fs).mkdir()
        (tmp_path / fs / "big.bin").write_bytes(b"x" * 4096)
    return {
        "T": str(transcript),
        "L": str(tasks / "agent.output"),
        "O": str(tasks / "bash.output"),
        "B": str(data / "big.csv"),
        "S": str(data / "small.csv"),
        "R": str(tmp_path / "ram" / "big.bin"),
        "N": str(tmp_path / "nas" / "big.bin"),
        "H": str(home),
        "D": str(data),
    }


def fill(command: str, paths: dict[str, str]) -> str:
    for key, value in paths.items():
        command = command.replace("{" + key + "}", value)
    return command


@pytest.mark.parametrize(
    "command",
    [
        "grep -n foo {T}",
        "LC_ALL=C grep -F x ~/.claude/projects/*/*.jsonl",
        "grep -c x $HOME/.claude/projects/proj/session.jsonl",
        "cat {T} | wc -l",
        "rg foo {T}",
        "awk 'NR<5' {B}",
        "sed -n 1,5p {B}",
        "sort {B} | head -c 100",
        "sha256sum {B}",
        "grep x < {T}",
        "grep x <{T}",
        "cat {L}",
        "tail -n 100 {T}",
        "tail {T}",
        "head {B}",
        "tail -c +100 {T}",
        "head -c -100 {T}",
        "tail -c 100000000 {T}",
        "dd if={T} bs=1M",
        "dd if={T} bs=1M count=100",
        "ionice -c3 grep x {T}",
        "ionice -c3 tail -n 50 {T} | grep x",
        "grep -r foo {H}/.claude",
        "grep -rn foo {H}",
        "rg --hidden foo {H}",
        "rg -uu foo {H}",
        "rg foo {H}/.claude/projects",
        "find {H}/.claude/projects -name '*.jsonl' -exec grep -l x {} +",
        "bash -c 'grep x {T}'",
        "echo start # a comment\ngrep x {T}",
        "cd /tmp && grep x {T}",
        "timeout 30 nice -n 19 cat {T}",
    ],
)
def test_refused(hook: ModuleType, paths: dict[str, str], command: str) -> None:
    command = fill(command, paths)
    assert hook.classify(command, "/"), command


@pytest.mark.parametrize(
    "command",
    [
        "grep x {S}",
        "tail -c 5000000 {T} | LC_ALL=C grep -F x",
        "head -c 2M {T}",
        "head -c2M {T} | wc -l",
        "head --bytes=1000 {T}",
        "ionice -c3 tail -c 1000 {T} | wc -c",
        "dd if={T} bs=1M skip=2 count=5",
        "dd if={T} iflag=count_bytes count=4096",
        "ls -la {T}",
        "stat {T}",
        "du -sh {H}/.claude",
        "cat {O}",
        "grep x {R}",
        "sha256sum {N}",
        "rg foo {H}",
        "echo x > {B}",
        "grep x {S} > {B}",
        "grep x {S} 2>&1 | tail -n 5",
        "grep x {S} 2> {B}",
        "find {H}/.claude/projects -name '*.jsonl' -size -16k",
        "python3 - <<'EOF'\nopen('{T}').read()\nEOF",
        "git log --oneline -3",
        "docker exec poring-lab-sniffer-1 cat /captures/big.pcapng",
        "grep x /nonexistent/file.jsonl",
        "cat",
        "ls # grep x {T}",
        "echo 'grep x {T}'",
    ],
)
def test_allowed(hook: ModuleType, paths: dict[str, str], command: str) -> None:
    command = fill(command, paths)
    assert hook.classify(command, "/") is None, command


def test_relative_paths_resolve_against_the_commands_cwd(
    hook: ModuleType, paths: dict[str, str]
) -> None:
    assert hook.classify("grep x big.csv", paths["D"])
    assert hook.classify("grep x big.csv", "/") is None  # not there: nothing to read


def test_the_message_names_the_reader_and_why(hook: ModuleType, paths: dict[str, str]) -> None:
    assert "session transcript" in hook.classify(fill("grep x {T}", paths), "/")
    assert "MB on the shared disk" in hook.classify(fill("cat {B}", paths), "/")


def test_hook_exit_codes_and_message(tmp_path: Path, paths: dict[str, str]) -> None:
    """Run as Claude Code runs it: a subprocess. An ImportError of the shared tokenizer would
    exit 1 here (non-blocking, so the guard would fail open) and this test would catch it."""
    env = {**os.environ, "HOME": str(tmp_path / "home")}

    def run(payload: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(HOOK)], input=payload, capture_output=True, text=True, env=env
        )

    def bash(command: str) -> str:
        return json.dumps({"tool_name": "Bash", "tool_input": {"command": command}, "cwd": "/"})

    blocked = run(bash(f"grep -c x {paths['T']}"))
    assert blocked.returncode == 2, blocked.stderr
    assert "big-read guard" in blocked.stderr and "tail -c" in blocked.stderr
    assert run(bash(f"tail -c 1000 {paths['T']} | wc -c")).returncode == 0
    assert run("not json").returncode == 0  # unreadable input: fail open
