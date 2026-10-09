"""scripts/flows_gat.py: the GATs copied to the MW2 editor's read-only mount, hashed back; files
already identical are left alone."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "flows_gat.py"


def load() -> object:
    spec = importlib.util.spec_from_file_location("flows_gat", SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["flows_gat"] = mod
    spec.loader.exec_module(mod)
    return mod


def test_copies_then_leaves_identical_files_alone(tmp_path: Path) -> None:
    fg = load()
    src, dst = tmp_path / "src", tmp_path / "dst"
    src.mkdir()
    (src / "a.gat").write_bytes(b"GRAT-a")
    (src / "b.gat").write_bytes(b"GRAT-b")
    (src / "indoorrswtable.txt").write_text("not a gat")
    first = fg.publish(src, dst)  # type: ignore[attr-defined]
    assert [(n, w) for n, w, _ in first] == [("a.gat", "copied"), ("b.gat", "copied")]
    assert (dst / "a.gat").read_bytes() == b"GRAT-a" and not (dst / "indoorrswtable.txt").exists()
    (src / "b.gat").write_bytes(b"GRAT-b2")
    again = fg.publish(src, dst)  # type: ignore[attr-defined]
    assert [(n, w) for n, w, _ in again] == [("a.gat", "same"), ("b.gat", "copied")]
    assert not list(dst.glob("*.part"))


def test_refuses_a_missing_extraction(tmp_path: Path) -> None:
    fg = load()
    with pytest.raises(SystemExit, match="no GAT extraction"):
        fg.publish(tmp_path / "gone", tmp_path / "dst")  # type: ignore[attr-defined]
