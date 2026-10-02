"""The never-commit guard (ADR-0012, C7): .gitignore rules and .githooks/pre-commit, exercised on
a throwaway git repository with SYNTHETIC pack content."""

import importlib.util
import os
import shutil
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[3]
HOOK = ROOT / ".githooks" / "pre-commit"


@pytest.fixture(scope="module")
def lp() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "locale_pack", ROOT / "scripts" / "locale_pack.py"
    )
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["locale_pack"] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.mark.parametrize(
    "path",
    [
        "locale-packs/th/msg.json",
        "locales/en/locale-pack.json",
        "x.localepack/msg.json",
        "thai-data/a.txt",
        "anywhere/ro_thai/data/a.txt",
        "anywhere/kro-reference/table.txt",
        "anywhere/grf-extract/data/a.txt",
        "data2/msgStringTable.txt",
        "locale-pack.json",
    ],
)
def test_gitignore_covers_pack_and_client_text_paths(path: str) -> None:
    ok = subprocess.run(["git", "check-ignore", "-q", "--no-index", path], cwd=ROOT)
    assert ok.returncode == 0, f"{path} is not ignored"


def test_no_tracked_file_is_ignored_by_the_new_rules() -> None:
    out = subprocess.run(
        ["git", "ls-files", "-ci", "--exclude-standard"], cwd=ROOT, capture_output=True, text=True
    )
    assert out.stdout == ""


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    if shutil.which("git") is None:
        pytest.skip("git not installed")
    r = tmp_path / "repo"
    (r / ".githooks").mkdir(parents=True)
    shutil.copy2(HOOK, r / ".githooks" / "pre-commit")
    for args in (
        ["init", "-q"],
        ["config", "core.hooksPath", ".githooks"],
        ["config", "user.name", "test"],
        ["config", "user.email", "test@example.invalid"],
        ["config", "commit.gpgsign", "false"],
    ):
        subprocess.run(["git", *args], cwd=r, check=True)
    return r


def commit(repo: Path, fingerprints: Path) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "PORING_PACK_FINGERPRINTS": str(fingerprints)}
    return subprocess.run(
        ["git", "commit", "-q", "-m", "test"], cwd=repo, env=env, capture_output=True, text=True
    )


def stage(repo: Path, rel: str, content: str, *, force: bool = False) -> None:
    path = repo / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    subprocess.run(["git", "add", *(["-f"] if force else []), rel], cwd=repo, check=True)


def test_hook_is_executable() -> None:
    assert os.access(HOOK, os.X_OK)


def test_clean_file_passes(repo: Path, tmp_path: Path) -> None:
    stage(repo, "docs/notes.md", "Thai in our own docs stays allowed: สวัสดีครับ ทุกท่าน\n")
    result = commit(repo, tmp_path / "none.txt")
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize(
    ("rel", "reason"),
    [
        ("locale-packs/th/msg.json", "locale pack / extracted client data directory"),
        ("thai-client/data/a.txt", "locale pack / extracted client data directory"),
        ("tools/x.localepack/a.json", "locale pack / extracted client data directory"),
        ("data2/msgstringtable.txt", "client asset"),
        ("assets/ui.lub", "client asset"),
    ],
)
def test_planted_pack_paths_are_refused(repo: Path, tmp_path: Path, rel: str, reason: str) -> None:
    stage(repo, rel, "synthetic\n", force=True)
    result = commit(repo, tmp_path / "none.txt")
    assert result.returncode != 0
    assert f"refused {rel}: {reason}" in result.stderr


def test_any_file_inside_a_pack_directory_is_refused(repo: Path, tmp_path: Path) -> None:
    (repo / "out" / "pack").mkdir(parents=True)
    (repo / "out" / "pack" / "locale-pack.json").write_text("{}")  # untracked marker on disk
    stage(repo, "out/pack/tables/items.json", "{}\n")
    result = commit(repo, tmp_path / "none.txt")
    assert result.returncode != 0 and "inside a locale pack (out/pack/locale-pack.json)" in (
        result.stderr
    )


def test_a_fingerprinted_pack_string_is_refused(lp: ModuleType, repo: Path, tmp_path: Path) -> None:
    pack_string = "ข้อความสังเคราะห์สำหรับทดสอบ"  # synthetic, made up for this test
    fps = tmp_path / "fp.txt"
    lp.write_fingerprints(fps, [pack_string + "#"])
    stage(repo, "src/strings.py", f'LABEL = "{pack_string}"\n')
    result = commit(repo, fps)
    assert result.returncode != 0
    assert "refused src/strings.py: line 1 carries a locale-pack string" in result.stderr
    assert pack_string not in result.stderr  # paths and reasons only, never the text

    subprocess.run(["git", "rm", "-q", "--cached", "src/strings.py"], cwd=repo, check=True)
    stage(repo, "src/table.txt", f"{pack_string}#\n")  # a whole msgstringtable-style line
    assert commit(repo, fps).returncode != 0


def test_hook_repeats_the_builders_fingerprint_rule(lp: ModuleType) -> None:
    hook = HOOK.read_text()
    assert "if len(norm) < 6:" in hook and lp.FINGERPRINT_MIN == 6
    assert 'unicodedata.normalize("NFC", text)' in hook
    assert 'hashlib.sha256(norm.encode("utf-8")).hexdigest()' in hook
