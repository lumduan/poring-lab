"""scripts/foreground_template.py: templates reach the human-only store atomically, read back, with
a shape that fits their box; nothing is installed from a missing or mismatched calibration."""

import importlib.util
import json
from pathlib import Path
from types import ModuleType

import numpy as np
import pytest

from poring_backend.signature import SIG_SCALE

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "foreground_template.py"


@pytest.fixture(scope="module")
def ft() -> ModuleType:
    spec = importlib.util.spec_from_file_location("foreground_template", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def calibrated(src: Path, *, stream: bool = False, shape: tuple[int, int] = (2, 7)) -> None:
    src.mkdir(parents=True)
    (src / "client_title_active.json").write_text(json.dumps({"box": [6, -24, 56, 16]}))
    np.save(src / "client_title_active.npy", np.ones(shape, np.float32))
    if stream:
        np.save(src / "client_title_active@stream.npy", np.full(shape, 2, np.float32))


def test_the_scale_matches_the_backend(ft: ModuleType) -> None:
    assert ft.SIG_SCALE == SIG_SCALE


def test_install_copies_atomically_and_logs(ft: ModuleType, tmp_path: Path) -> None:
    src, dest = tmp_path / "sig", tmp_path / "settings" / "foreground"
    (tmp_path / "settings").mkdir()
    calibrated(src, stream=True)
    assert ft.install("rdp", src, dest) == 0
    assert ft.install("stream", src, dest) == 0
    for name in ("client_title_active.json", "client_title_active.npy",
                 "client_title_active@stream.npy"):  # fmt: skip
        assert (dest / name).read_bytes() == (src / name).read_bytes()
    assert not list(dest.glob(".*.tmp"))
    log = [json.loads(line) for line in (dest / "install.log").read_text().splitlines()]
    assert [entry["install"] for entry in log] == ["rdp", "stream"]


def test_a_missing_or_mismatched_calibration_installs_nothing(ft: ModuleType,
                                                             tmp_path: Path) -> None:  # fmt: skip
    (tmp_path / "settings").mkdir()
    dest = tmp_path / "settings" / "foreground"
    with pytest.raises(SystemExit, match="calibrate"):
        ft.install("stream", tmp_path / "nothing", dest)
    calibrated(tmp_path / "sig", shape=(3, 7))  # not the box's thumbnail
    with pytest.raises(SystemExit, match="does not fit"):
        ft.install("rdp", tmp_path / "sig", dest)
    assert not dest.exists() or not list(dest.iterdir())


def test_a_missing_store_is_never_created(ft: ModuleType, tmp_path: Path) -> None:
    calibrated(tmp_path / "sig")
    with pytest.raises(SystemExit, match="settings store"):
        ft.install("rdp", tmp_path / "sig", tmp_path / "absent" / "foreground")
    assert not (tmp_path / "absent").exists()
