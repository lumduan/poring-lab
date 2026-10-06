"""scripts/hooks/guard_walk.py: no filesystem walks outside the repo and RAM filesystems."""

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[3]
HOOK = ROOT / "scripts" / "hooks" / "guard_walk.py"


KEYS = {"R": "repo", "D": "disk", "M": "ram", "N": "nas", "A": "auto", "O": "overlay"}


@pytest.fixture
def paths(tmp_path: Path) -> dict[str, str]:
    out = {}
    for key, name in KEYS.items():
        (tmp_path / name / "sub").mkdir(parents=True)
        (tmp_path / name / "sub" / "f.txt").write_text("x\n")
        out[key] = str(tmp_path / name)
    return out


@pytest.fixture
def hook(monkeypatch: pytest.MonkeyPatch, paths: dict[str, str]) -> ModuleType:
    spec = importlib.util.spec_from_file_location("guard_walk", HOOK)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["guard_walk"] = mod
    spec.loader.exec_module(mod)
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", paths["R"])
    # A fake mount table: the tmp tree sits on "/" (ext4) unless a deeper mount says otherwise.
    # (A stacked autofs + nfs4 pair, as /proc/mounts shows a mounted NAS share: the last wins.)
    table = [("/", "ext4"), ("/proc", "proc"), (paths["M"], "tmpfs"), (paths["N"], "autofs"),
             (paths["N"], "nfs4"), (paths["A"], "autofs"), (paths["O"], "overlay")]  # fmt: skip
    monkeypatch.setattr(mod, "mounts", lambda: table)
    return mod


def fill(command: str, paths: dict[str, str]) -> str:
    for key, value in paths.items():
        command = command.replace("{" + key + "}", value)
    return command


REFUSED = [
    # the whole filesystem, however it is written or wrapped
    "find / -name foo", "find / -maxdepth 1 -type d", "find -L / -name x", "find -H -O3 / -x",
    "sudo nice -n 19 ionice -c3 find / -xdev -name x", "timeout 30 find / -name x",
    "du -sh /", "tree /", "ls -R /", "ls -laR /", "rg foo /", "rg -e foo -- /", "ag foo /",
    "grep -r foo /", "grep -Rn foo /", "grep --recursive foo /", "fd foo /",
    "bash -c 'find / -name x'", "sh -c \"du -s /\"", "echo $(find / -name x)",
    "true; find / -name x", "cat x | grep -rl foo /", "bash <<EOF\nfind / -name x\nEOF",
    # /mnt (the NAS automounts), by name, globbed or not
    "find /mnt -name x", "du -sh /mnt/*", "ls -R /mnt/quant-artifacts", "rg foo /mnt/x/y",
    "grep -r foo /mnt/poring-lab-datasets",
    # a network or automount filesystem anywhere
    "find {N} -name x", "rg foo {N}/sub", "du -s {A}", "grep -rn x {N}",
    # the shared disk outside the repo: ext4, Docker's overlays
    "find {D} -name x", "du -sh {D}", "du -sh {O}/sub", "rg foo {D}", "grep -r foo {D}/sub",
    "find {D}/*", "fd -e py foo {D}", "ag foo {D}", "tree -L 2 {D}", "ls -R {D}",
    "grep -d recurse foo {D}", "grep --directories=recurse foo {D}",
    "grep --directories recurse x {D}",
    "rg --files {D}", "rg -r X pat {D}", "find {R}/.. -name x", "find {R}/../disk",
    # roots a hook cannot see
    "find $SOMEWHERE -name x", 'find "$(pwd)" -name x', "du -s `pwd`", "rg foo $DIR",
]  # fmt: skip

ALLOWED = [
    # inside the repo (default root "." with cwd = the repo)
    "find . -name '*.py'", "find", "rg foo", "rg foo services", "grep -r foo", "grep -rn foo src",
    "du -sh .", "du -sh {R}/sub", "find {R} -name x", "ls -R {R}", "tree {R}", "rg -e x {R}",
    "rg / {R}", "grep -r / {R}", "rg -r X pat {R}", "fd foo", "find {R}/sub/../sub",
    # RAM filesystems
    "find {M} -name x", "du -sh {M}/*", "rg foo {M}", "grep -r foo {M}/sub", "du -s /proc/self",
    # not walks
    "grep foo {D}/sub/f.txt", "grep -eroot {D}/sub/f.txt", "ls -la /", "ls /mnt", "stat /",
    "findmnt -no FSTYPE /", "df -h", "git ls-files", "cat {D}/sub/f.txt", "xargs echo",
    "python3 -c 'print(1)'", "echo find / -name x", "git grep foo",
]  # fmt: skip


@pytest.mark.parametrize("command", REFUSED)
def test_walks_outside_the_repo_and_ram_are_refused(
    hook: ModuleType, paths: dict[str, str], command: str
) -> None:
    reason = hook.classify(fill(command, paths), paths["R"])
    assert reason is not None, command


@pytest.mark.parametrize("command", ALLOWED)
def test_walks_in_the_repo_or_ram_and_non_walks_pass(
    hook: ModuleType, paths: dict[str, str], command: str
) -> None:
    assert hook.classify(fill(command, paths), paths["R"]) is None, command


def test_the_default_root_is_the_cwd(hook: ModuleType, paths: dict[str, str]) -> None:
    assert hook.classify("rg foo", paths["D"]) is not None  # walking the disk from a cwd outside
    assert hook.classify("grep -r foo", paths["D"]) is not None
    assert hook.classify("find -name x", paths["D"]) is not None
    assert hook.classify("du -sh", paths["R"]) is None


def test_home_and_pwd_are_expanded(
    hook: ModuleType, paths: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", paths["R"])
    assert hook.classify("find ~/sub -name x", paths["D"]) is None
    assert hook.classify("find $HOME -name x", paths["D"]) is None
    assert hook.classify("find $PWD -name x", paths["D"]) is not None  # $PWD = the disk cwd


def test_mnt_is_judged_by_name_without_touching_it(
    hook: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    real = hook.os.path.realpath

    def no_realpath(path: str) -> str:
        if path == "/mnt" or path.startswith("/mnt/"):
            raise AssertionError(f"realpath called on {path}: it would fire the automount")
        return real(path)

    monkeypatch.setattr(hook.os.path, "realpath", no_realpath)
    assert "NAS automounts" in (hook.classify("rg foo /mnt/tank-frigate/clips", "/") or "")
    assert "whole filesystem" in (hook.classify("find /", "/") or "")


def test_the_reason_names_the_tool_and_the_root(hook: ModuleType, paths: dict[str, str]) -> None:
    reason = hook.classify(f"du -sh {paths['O']}", paths["R"]) or ""
    assert (
        reason.startswith("`du` would walk")
        and "overlay" in reason
        and "outside the repo" in reason
    )
    assert "network mount, nfs4" in (hook.classify(f"find {paths['N']}", paths["R"]) or "")


def run_hook(command: str, cwd: str) -> subprocess.CompletedProcess[str]:
    payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": command}, "cwd": cwd})
    return subprocess.run([sys.executable, str(HOOK)], input=payload, capture_output=True,
                          text=True, timeout=30, check=False)  # fmt: skip


def test_the_hook_process_blocks_with_exit_2_and_explains() -> None:
    r = run_hook("find / -name '*.jsonl'", str(ROOT))
    assert r.returncode == 2
    assert "BLOCKED by poring-lab's walk guard" in r.stderr and "inside the repo" in r.stderr
    assert run_hook("rg foo services", str(ROOT)).returncode == 0
    assert run_hook("ls -la /", str(ROOT)).returncode == 0


def test_unreadable_input_fails_open() -> None:
    r = subprocess.run([sys.executable, str(HOOK)], input="not json", capture_output=True,
                       text=True, timeout=30, check=False)  # fmt: skip
    assert r.returncode == 0


def test_the_repo_settings_run_the_walk_guard_on_every_bash_call() -> None:
    settings = json.loads((ROOT / ".claude" / "settings.json").read_text())
    bash = [
        h for m in settings["hooks"]["PreToolUse"] if m["matcher"] == "Bash" for h in m["hooks"]
    ]
    assert any("scripts/hooks/guard_walk.py" in h["command"] for h in bash)
