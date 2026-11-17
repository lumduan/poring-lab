"""scripts/detector_setup.py (Batt 2026-11-17: "no GPU -> the CPU"; the starter model v1 from the
teaching-kit branch): only the pinned v1 is ever installed, and --check never writes."""

from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts"))

import detector_setup as ds  # noqa: E402
import unit_detector as ud  # noqa: E402


def test_the_pin_is_the_labs_own_v1() -> None:
    w = ud.GPU_WEIGHTS["v1"]
    assert (w.onnx, w.onnx_sha256) == (ds.V1_ONNX, ds.V1_SHA256)
    assert ud.MODEL.name == ds.V1_ONNX  # the CPU detector's default model file


def fake_git(blob: bytes, ok_refs: tuple[str, ...]) -> object:
    calls: list[tuple[str, ...]] = []

    def run(*args: str, timeout: int = 300) -> subprocess.CompletedProcess[bytes]:
        calls.append(args)
        if args[0] == "show" and args[1].split(":")[0] in ok_refs:
            return subprocess.CompletedProcess(args, 0, blob, b"")
        if args[0] == "fetch":
            return subprocess.CompletedProcess(args, 0, b"", b"")
        return subprocess.CompletedProcess(args, 128, b"", b"no such ref")

    run.calls = calls  # type: ignore[attr-defined]
    return run


def test_a_file_that_is_not_the_pin_is_never_installed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(ds, "_git", fake_git(b"not the model", ("origin/teaching-kit",)))
    dest = tmp_path / "model" / ds.V1_ONNX
    with pytest.raises(SystemExit, match="not the pinned v1"):
        ds.fetch_model(dest)
    assert not dest.exists() and not list(tmp_path.rglob("*.tmp"))


def test_the_local_ref_first_then_one_shallow_fetch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    blob = b"pretend v1"
    monkeypatch.setattr(ds, "V1_SHA256", hashlib.sha256(blob).hexdigest())
    git = fake_git(blob, ("FETCH_HEAD",))  # no local ref: a clone with --single-branch
    monkeypatch.setattr(ds, "_git", git)
    dest = tmp_path / "model" / ds.V1_ONNX
    ds.fetch_model(dest)
    assert dest.read_bytes() == blob
    fetches = [c for c in git.calls if c[0] == "fetch"]  # type: ignore[attr-defined]
    assert fetches == [("fetch", "--depth", "1", "origin", "refs/heads/teaching-kit")]


def test_check_is_read_only_and_says_what_is_missing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    folder, store = tmp_path / "det", tmp_path / "store"
    assert ds.main(["--check", "--dir", str(folder), "--store-models", str(store)]) == 1
    out = capsys.readouterr().out
    assert "venv missing, model missing, store_model missing" in out
    assert not folder.exists() and not store.exists()


def test_a_copy_that_does_not_match_is_removed(tmp_path: Path) -> None:
    src = tmp_path / "src.onnx"
    src.write_bytes(b"other bytes")
    with pytest.raises(SystemExit, match="does not match the pin"):
        ds.install_copy(src, tmp_path / "store" / ds.V1_ONNX)
    assert not (tmp_path / "store" / ds.V1_ONNX).exists()
