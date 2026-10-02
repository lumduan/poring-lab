"""scripts/dataset_ship.py + record_session.py's local caps (ADR-0010): ship -> verify -> delete,
SET-hours refusal, pins, dry-run prune. Real rsync between two tmp dirs; no NAS, no docker."""

import datetime as dt
import importlib.util
import json
import shutil
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest

SCRIPTS = Path(__file__).resolve().parents[3] / "scripts"
BKK = dt.timezone(dt.timedelta(hours=7))
SATURDAY = dt.datetime(2026, 10, 3, 12, 0, tzinfo=BKK)  # outside SET hours
WEDNESDAY_10 = dt.datetime(2026, 9, 30, 10, 0, tzinfo=BKK)  # inside SET hours

pytestmark = pytest.mark.skipif(shutil.which("rsync") is None, reason="rsync is not installed")


def load(name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def ds(monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    module = load("dataset_ship")
    monkeypatch.setattr(module, "now", lambda: SATURDAY)
    return module


def make_session(root: Path, sid: str, payload: bytes = b"\x89PNG frame bytes" * 1000) -> Path:
    session = root / sid
    session.mkdir(parents=True)
    (session / "shard-000000.tar").write_bytes(payload)
    (session / "packets.jsonl.gz").write_bytes(b"\x1f\x8b gz")
    (session / "labels").mkdir()
    (session / "labels" / "000000001.txt").write_text("0 0.5 0.5 0.1 0.2\n")
    (session / "manifest.json").write_text(json.dumps({"session_id": sid, "frames": 1}))
    return session


@pytest.fixture
def dirs(tmp_path: Path) -> SimpleNamespace:
    root, dest = tmp_path / "local", tmp_path / "nas"
    root.mkdir()
    dest.mkdir()
    return SimpleNamespace(root=root, dest=dest)


def ship_argv(d: SimpleNamespace, *extra: str) -> list[str]:
    return ["ship", "--root", str(d.root), "--dest", str(d.dest), "--dest-is-dir-for-tests",
            "--no-io-guard", *extra]  # fmt: skip


def index_lines(dest: Path) -> list[dict[str, Any]]:
    path = dest / "INDEX.jsonl"
    return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []


SID = "20261003T110000-rdp-calib"


def test_ship_verifies_then_deletes_the_local_copy(ds: ModuleType, dirs: SimpleNamespace) -> None:
    make_session(dirs.root, SID)
    assert ds.main(ship_argv(dirs)) == 0
    assert not (dirs.root / SID).exists()
    remote = dirs.dest / SID
    assert (remote / "labels" / "000000001.txt").read_text() == "0 0.5 0.5 0.1 0.2\n"
    sums = ds.read_checksums(remote / "checksums.sha256")
    assert set(sums) == {"shard-000000.tar", "packets.jsonl.gz", "labels/000000001.txt"}
    assert all(ds.sha256_file(remote / rel) == digest for rel, digest in sums.items())
    storage = json.loads((remote / "manifest.json").read_text())["storage"]
    assert storage["nas_path"] == str(remote) and storage["files"] == 3
    assert storage["verified_at"] == SATURDAY.isoformat(timespec="seconds")
    assert storage["checksums_sha256"] == ds.sha256_file(remote / "checksums.sha256")
    (line,) = index_lines(dirs.dest)
    assert line["event"] == "shipped" and line["session_id"] == SID


def test_the_order_is_verify_record_index_then_delete(
    ds: ModuleType, dirs: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[str] = []
    for name in ("verify", "write_manifest", "append_index"):
        original = getattr(ds, name)

        def spy(*args: Any, _name: str = name, _orig: Any = original) -> Any:
            calls.append(_name)
            return _orig(*args)

        monkeypatch.setattr(ds, name, spy)
    rmtree = ds.shutil.rmtree

    def spy_rmtree(path: Any, *args: Any, **kwargs: Any) -> None:
        if Path(path).parent == dirs.root:
            calls.append("delete_local")
        rmtree(path, *args, **kwargs)

    monkeypatch.setattr(ds.shutil, "rmtree", spy_rmtree)
    make_session(dirs.root, SID)
    assert ds.main(ship_argv(dirs)) == 0
    assert calls == ["verify", "write_manifest", "append_index", "delete_local"]


def test_a_checksum_mismatch_on_the_nas_keeps_the_local_copy(
    ds: ModuleType, dirs: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    real_transfer = ds.transfer

    def corrupting(src: Path, dst: Path, bwlimit: int, guard: Any) -> None:
        real_transfer(src, dst, bwlimit, guard)
        with (dst / "shard-000000.tar").open("r+b") as fh:  # one flipped byte "in transit"
            fh.write(b"X")

    monkeypatch.setattr(ds, "transfer", corrupting)
    make_session(dirs.root, SID)
    assert ds.main(ship_argv(dirs)) == 1
    assert (dirs.root / SID / "shard-000000.tar").exists()
    assert "storage" not in json.loads((dirs.dest / SID / "manifest.json").read_text())
    assert index_lines(dirs.dest) == []
    # a clean re-run repairs the NAS copy (rsync compares checksums of changed files) and ships
    monkeypatch.setattr(ds, "transfer", real_transfer)
    (dirs.dest / SID / "shard-000000.tar").unlink()
    assert ds.main(ship_argv(dirs)) == 0
    assert not (dirs.root / SID).exists()


def test_a_failed_rsync_keeps_the_local_copy(
    ds: ModuleType, dirs: SimpleNamespace, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fake = tmp_path / "bin"
    fake.mkdir()
    (fake / "rsync").write_text("#!/bin/sh\nexit 23\n")
    (fake / "rsync").chmod(0o755)
    monkeypatch.setenv("PATH", f"{fake}:/usr/bin:/bin")
    make_session(dirs.root, SID)
    assert ds.main(ship_argv(dirs)) == 1
    assert (dirs.root / SID / "manifest.json").exists()


def test_ship_refuses_during_set_hours_unless_forced(
    ds: ModuleType, dirs: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(ds, "now", lambda: WEDNESDAY_10)
    make_session(dirs.root, SID)
    assert ds.main(ship_argv(dirs)) == 2
    assert (dirs.root / SID).exists() and not (dirs.dest / SID).exists()
    assert ds.main(ship_argv(dirs, "--force-market")) == 0
    assert not (dirs.root / SID).exists()


@pytest.mark.parametrize(
    ("when", "inside"),
    [
        (dt.datetime(2026, 9, 28, 9, 29, tzinfo=BKK), False),  # Monday, before the open
        (dt.datetime(2026, 9, 28, 9, 30, tzinfo=BKK), True),
        (dt.datetime(2026, 9, 28, 16, 59, tzinfo=BKK), True),
        (dt.datetime(2026, 9, 28, 17, 0, tzinfo=BKK), False),
        (dt.datetime(2026, 10, 3, 11, 0, tzinfo=BKK), False),  # Saturday
        (dt.datetime(2026, 9, 28, 3, 0, tzinfo=dt.UTC), True),  # 10:00 in Bangkok
    ],
)
def test_set_hours(ds: ModuleType, when: dt.datetime, inside: bool) -> None:
    assert ds.in_set_hours(when) is inside


def test_ship_refuses_an_unmounted_or_missing_nas(ds: ModuleType, dirs: SimpleNamespace) -> None:
    make_session(dirs.root, SID)
    plain = ["ship", "--root", str(dirs.root), "--dest", str(dirs.dest), "--no-io-guard"]
    assert ds.main(plain) == 2  # a tmp dir is not a mount point: the NAS is "down"
    missing = ["ship", "--root", str(dirs.root), "--dest", str(dirs.dest / "nope"),
               "--dest-is-dir-for-tests", "--no-io-guard"]  # fmt: skip
    assert ds.main(missing) == 2
    assert (dirs.root / SID).exists()
    assert list(dirs.dest.iterdir()) == []


def test_an_unfinished_recording_is_never_shipped(ds: ModuleType, dirs: SimpleNamespace) -> None:
    session = make_session(dirs.root, SID)
    (session / "manifest.json").unlink()  # still recording (the manifest is written last)
    assert ds.main(ship_argv(dirs)) == 0
    assert (dirs.root / SID / "shard-000000.tar").exists()
    assert ds.main(ship_argv(dirs, SID)) == 1  # named explicitly: refused, still kept
    assert (dirs.root / SID).exists()


def test_prune_is_a_dry_run_by_default_and_never_touches_pins(
    ds: ModuleType, dirs: SimpleNamespace, capsys: pytest.CaptureFixture[str]
) -> None:
    old, pinned, fresh = "20240101T000000-rdp-old", "20240102T000000-rdp-bench", SID
    for sid in (old, pinned, fresh):
        make_session(dirs.dest, sid)
    pin = ["pin", pinned, "--reason", "SPEC v2 baseline", "--dest", str(dirs.dest),
           "--dest-is-dir-for-tests"]  # fmt: skip
    assert ds.main(pin) == 0
    prune = ["prune", "--dest", str(dirs.dest), "--dest-is-dir-for-tests"]
    assert ds.main(prune) == 0
    out = capsys.readouterr().out
    assert f"would delete {old}" in out and "dry run: nothing deleted" in out
    assert f"pinned    {pinned}" in out and fresh not in out
    assert all((dirs.dest / sid).exists() for sid in (old, pinned, fresh))
    assert ds.main([*prune, "--apply"]) == 0
    assert not (dirs.dest / old).exists()
    assert (dirs.dest / pinned).exists() and (dirs.dest / fresh).exists()
    events = [(e["event"], e["session_id"]) for e in index_lines(dirs.dest)]
    assert events == [("pinned", pinned), ("pruned", old)]


def test_prune_honours_older_than(ds: ModuleType, dirs: SimpleNamespace) -> None:
    make_session(dirs.dest, "20260901T000000-rdp-month")  # 32 days before SATURDAY
    prune = ["prune", "--dest", str(dirs.dest), "--dest-is-dir-for-tests", "--apply"]
    assert ds.main([*prune, "--older-than", "60d"]) == 0
    assert (dirs.dest / "20260901T000000-rdp-month").exists()
    assert ds.main([*prune, "--older-than", "30d"]) == 0
    assert not (dirs.dest / "20260901T000000-rdp-month").exists()


def test_local_caps(ds: ModuleType, dirs: SimpleNamespace, monkeypatch: pytest.MonkeyPatch) -> None:
    make_session(dirs.root, SID, payload=b"x" * 50_000)
    monkeypatch.setattr(ds, "free_bytes", lambda path: 200 * 10**9)
    assert ds.local_caps(dirs.root) is None
    assert "unshipped" in ds.local_caps(dirs.root, max_unshipped=10_000)
    assert ds.local_caps(dirs.root, max_unshipped=10**6) is None
    # a running recording: measured once, then its own bytes added on top
    running = ds.local_caps(dirs.root, max_unshipped=10**6, unshipped=0, extra=2 * 10**6)
    assert "unshipped" in running
    monkeypatch.setattr(ds, "free_bytes", lambda path: 139 * 10**9)
    assert "free" in ds.local_caps(dirs.root)
    # a root that doesn't exist yet: nothing unshipped, free space of its parent
    monkeypatch.setattr(ds, "free_bytes", lambda path: 200 * 10**9)
    assert ds.local_caps(dirs.root / "not-yet") is None


def test_free_bytes_walks_up_to_an_existing_parent(ds: ModuleType, tmp_path: Path) -> None:
    assert ds.free_bytes(tmp_path / "a" / "b") == ds.free_bytes(tmp_path) > 0


def test_status_lists_both_sides(
    ds: ModuleType, dirs: SimpleNamespace, capsys: pytest.CaptureFixture[str]
) -> None:
    make_session(dirs.root, SID)
    make_session(dirs.root, "20261003T120000-rdp-live").joinpath("manifest.json").unlink()
    make_session(dirs.dest, "20261001T000000-rdp-done")
    assert ds.main(["status", "--root", str(dirs.root), "--dest", str(dirs.dest),
                    "--dest-is-dir-for-tests"]) == 0  # fmt: skip
    out = capsys.readouterr().out
    assert f"{SID}" in out and "unshipped" in out
    assert "recording/incomplete" in out and "UNVERIFIED" in out
    assert f"nas {dirs.dest}: mounted" in out
    assert ds.main(["status", "--root", str(dirs.root), "--dest", str(dirs.dest)]) == 0
    assert "NOT mounted" in capsys.readouterr().out


def test_record_session_refuses_before_touching_x_when_the_caps_are_hit(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    rs = load("record_session")
    assert str(rs.dataset_ship.LOCAL_ROOT) == "/home/batt/poring-lab-rec"
    monkeypatch.setattr(rs, "read_lock", lambda _: SimpleNamespace(backend="rdp", phase="steady"))
    monkeypatch.setattr(rs.dataset_ship, "free_bytes", lambda path: 100 * 10**9)

    def no_screen() -> None:
        raise AssertionError("the screen was opened despite the cap")

    monkeypatch.setattr(rs.r, "Screen", no_screen)
    args = SimpleNamespace(backend="rdp", label="t", out=tmp_path / "rec", min_free_gb=140.0,
                           max_unshipped_gb=20.0, fps=10.0, seconds=1.0)  # fmt: skip
    with pytest.raises(rs.r.Stop, match="not recording: only 100 GB free"):
        rs.record(args)
    assert not (tmp_path / "rec").exists()
