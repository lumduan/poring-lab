"""scripts/build_frame_cache.py: per-session shards and --resume (Batt, 2026-10-06: a daytime
cache pauses when the IO guard trips, then resumes; it never retries fast and never redoes or
corrupts what it already wrote)."""

import importlib.util
import json
import sys
import tarfile
from pathlib import Path
from types import ModuleType

import pytest

SCRIPTS = Path(__file__).resolve().parents[3] / "scripts"


@pytest.fixture(scope="module")
def bfc() -> ModuleType:
    sys.path.insert(0, str(SCRIPTS))
    spec = importlib.util.spec_from_file_location(
        "build_frame_cache", SCRIPTS / "build_frame_cache.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["build_frame_cache"] = module  # its dataclasses resolve their module by name
    spec.loader.exec_module(module)
    return module


ARGS = {"labels": "v0", "k": None, "every": 15, "every_png": 1, "max_per_session": None,
        "shard_mb": 512, "image": "png", "quality": None,
        "split": {"train": ["A", "B"], "val": ["C"], "test": []}}  # fmt: skip


def write_shard(sink: object, key: str) -> None:
    sink.add(key, {"png": b"x" * 10, "txt": b"", "json": b"{}"})  # type: ignore[attr-defined]


def interrupted(bfc: ModuleType, d: Path) -> dict[str, dict[str, int]]:
    """Session A finished (recorded), session B was cut off mid-shard by a SIGINT."""
    sink = bfc.ShardSink(d, 1 << 20)
    write_shard(sink, "A.000000001")
    sink.close()
    bfc.write_json(d, "progress.json", {"args": ARGS, "sessions": {"A": {"kept": 1}},
                                        "shards": sink.done})  # fmt: skip
    write_shard(sink, "B.000000001")  # shard-000001.tar.part, never closed
    sink.tar.close()
    (d / "shard-000002.tar").write_bytes(b"unrecorded")  # a closed shard of the cut session
    return sink.done  # type: ignore[no-any-return]


def test_each_session_owns_its_shards(bfc: ModuleType, tmp_path: Path) -> None:
    sink = bfc.ShardSink(tmp_path, 1 << 20)
    write_shard(sink, "A.000000001")
    sink.close()
    write_shard(sink, "B.000000001")
    sink.close()
    assert sorted(sink.done) == ["shard-000000.tar", "shard-000001.tar"]
    with tarfile.open(tmp_path / "shard-000001.tar") as t:
        assert {m.name.split(".")[0] for m in t.getmembers()} == {"B"}


def test_resume_returns_the_recorded_state_and_removes_leftovers(
    bfc: ModuleType, tmp_path: Path
) -> None:
    done = interrupted(bfc, tmp_path)
    sessions, shards = bfc.resume_state(tmp_path, ARGS)
    assert list(sessions) == ["A"] and shards == done
    assert sorted(p.name for p in tmp_path.glob("shard-*")) == ["shard-000000.tar"]


def test_resume_continues_the_numbering(bfc: ModuleType, tmp_path: Path) -> None:
    done = interrupted(bfc, tmp_path)
    _, shards = bfc.resume_state(tmp_path, ARGS)
    start = 1 + max((int(n[6:12]) for n in shards), default=-1)
    sink = bfc.ShardSink(tmp_path, 1 << 20, start, shards)
    write_shard(sink, "B.000000001")
    sink.close()
    assert sorted(sink.done) == ["shard-000000.tar", "shard-000001.tar"]
    assert sink.done["shard-000000.tar"] == done["shard-000000.tar"]


def test_resume_refuses_other_arguments(bfc: ModuleType, tmp_path: Path) -> None:
    interrupted(bfc, tmp_path)
    with pytest.raises(SystemExit, match="image"):
        bfc.resume_state(tmp_path, {**ARGS, "image": "jpeg", "quality": 95})
    assert (tmp_path / "shard-000001.tar.part").exists()  # refused before touching anything


def test_resume_refuses_a_recorded_shard_that_changed(bfc: ModuleType, tmp_path: Path) -> None:
    interrupted(bfc, tmp_path)
    (tmp_path / "shard-000000.tar").write_bytes(b"truncated")
    with pytest.raises(SystemExit, match="shard-000000.tar"):
        bfc.resume_state(tmp_path, ARGS)


def test_resume_needs_progress(bfc: ModuleType, tmp_path: Path) -> None:
    with pytest.raises(SystemExit, match="progress.json"):
        bfc.resume_state(tmp_path, ARGS)


def test_write_json_is_atomic_and_read_back(bfc: ModuleType, tmp_path: Path) -> None:
    bfc.write_json(tmp_path, "progress.json", {"a": 1})
    assert json.loads((tmp_path / "progress.json").read_text()) == {"a": 1}
    assert not list(tmp_path.glob(".*.part"))
