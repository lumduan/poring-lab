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


def test_the_free_space_floor_is_batts_120_gb(
    ds: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Batt 2026-11-05 (ADR-0010 amendment): 120 GB stays free on the shared root disk (was 140)."""
    assert ds.MIN_FREE_BYTES == 120 * 10**9
    monkeypatch.setattr(ds, "free_bytes", lambda path: 119 * 10**9)
    assert "floor 120 GB" in (ds.local_caps(tmp_path, unshipped=0) or "")
    monkeypatch.setattr(ds, "free_bytes", lambda path: 121 * 10**9)
    assert ds.local_caps(tmp_path, unshipped=0) is None


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


def test_keep_local_banks_a_verified_copy_and_keeps_the_working_one(
    ds: ModuleType, dirs: SimpleNamespace
) -> None:
    make_session(dirs.root, SID)
    assert ds.main(ship_argv(dirs, "--keep-local")) == 0
    assert (dirs.root / SID / "shard-000000.tar").exists()  # the working copy stays
    assert (dirs.dest / SID / "shard-000000.tar").exists()
    assert [e["session_id"] for e in index_lines(dirs.dest) if e["event"] == "shipped"] == [SID]
    nas = json.loads((dirs.dest / SID / "manifest.json").read_text())
    assert nas["storage"]["verified_at"] and nas["storage"]["files"] >= 1


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
    monkeypatch.setattr(ds, "free_bytes", lambda path: ds.MIN_FREE_BYTES - 10**9)
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


def test_status_never_walks_the_nas(
    ds: ModuleType,
    dirs: SimpleNamespace,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """2026-11-05 23:17: status walked ~550 NAS sessions (tree_bytes) for > 12 min in NFS calls.
    NAS sizes come from the manifests' storage records; the local side may still be measured."""
    make_session(dirs.dest, "20261001T000000-rdp-done")
    walked: list[Path] = []
    real = ds.tree_bytes
    monkeypatch.setattr(ds, "tree_bytes", lambda path: walked.append(path) or real(path))
    assert ds.main(["status", "--root", str(dirs.root), "--dest", str(dirs.dest),
                    "--dest-is-dir-for-tests"]) == 0  # fmt: skip
    assert not [w for w in walked if dirs.dest in w.parents]
    assert "20261001T000000-rdp-done" in capsys.readouterr().out


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


def test_mark_invalid_keeps_the_session_and_its_hashes(
    ds: ModuleType, dirs: SimpleNamespace
) -> None:
    """Post-S2 round B6': the indoor set labelled with the outdoor camera is marked, not deleted."""
    sid = "20261004T061500-console-indoor"
    session = make_session(dirs.dest, sid)
    shard = (session / "shard-000000.tar").read_bytes()
    argv = ["mark-invalid", sid, "--reason", "outdoor camera on an indoor map", "--dest",
            str(dirs.dest), "--dest-is-dir-for-tests"]  # fmt: skip
    assert ds.main(argv) == 0
    manifest = json.loads((session / "manifest.json").read_text())
    assert manifest["validity"]["status"] == "INVALID"
    assert manifest["validity"]["reason"] == "outdoor camera on an indoor map"
    assert (session / "shard-000000.tar").read_bytes() == shard  # data untouched
    assert [(e["event"], e["session_id"]) for e in index_lines(dirs.dest)] == [("invalidated", sid)]
    assert ds.main([*argv[:1], "nope", *argv[2:]]) == 2  # no such session: refused


def test_record_session_h264_helpers(tmp_path: Path) -> None:
    """Experiment C1: the control file reads back; freeze spans come from the stream's own index."""
    rs = load("record_session")
    rs.write_control(tmp_path, "start 20261004T120000-console-c3-h0 0 210 2000")
    assert (tmp_path / "control").read_text() == "start 20261004T120000-console-c3-h0 0 210 2000\n"
    assert rs.H264_ID.match("20261004T120000-console-c3-h0")
    assert not rs.H264_ID.match("20261004T120000-console-C3_h0")  # the client's id grammar
    idx = tmp_path / "stream.idx.csv"
    ms = 1_000_000
    rows = [f"{i},{i + 1},{i},0,{int(i == 0)},{i * 33},0,10,{i},{t}"
            for i, t in enumerate([0, 33 * ms, 66 * ms, 300 * ms, 333 * ms])]  # fmt: skip
    rows.insert(2, f"-1,-1,99,0,0,0,0,0,0,{50 * ms}")  # a gap row is not a frame
    idx.write_text("au,frame_id,frame_number,frame_type,idr,pts_ms,offset,length,receive_ms,"
                   "t_publish_ns\n" + "\n".join(rows) + "\n")  # fmt: skip
    fr = rs.h264_freezes(idx)
    assert fr is not None and (fr["frames"], fr["count"]) == (5, 1)
    assert fr["max_ms"] == 234.0


def test_record_session_h264_refuses_rdp_and_bad_labels(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    rs = load("record_session")
    args = SimpleNamespace(backend="rdp", out=tmp_path)
    with pytest.raises(rs.r.Stop, match="console mode only"):
        rs.record_h264(args, None, {}, "", "20261004T120000-rdp-x", tmp_path / "s", {}, 0)
    args = SimpleNamespace(backend="console", out=tmp_path)
    with pytest.raises(rs.r.Stop, match="lowercase"):
        rs.record_h264(args, None, {}, "", "20261004T120000-console-X_1", tmp_path / "s", {}, 0)
    with pytest.raises(rs.r.Stop, match="does not exist"):
        rs.record_h264(args, None, {}, "", "20261004T120000-console-x", tmp_path / "s", {}, 0)


def test_the_default_format_is_h264_on_console_and_png_on_rdp() -> None:
    """Batt 2026-10-04 (C4): H.264 with an IDR every 1 s is the default dataset format; PNG stays
    selectable; the S2 client's own limits are checked before anything starts."""
    rs = load("record_session")

    def args(**kw: object) -> SimpleNamespace:
        base: dict[str, object] = {"backend": "console", "format": None, "seconds": 1200.0,
                                   "max_bytes": 3 * 10**9, "idr_every": 1.0}  # fmt: skip
        return SimpleNamespace(**(base | kw))

    a = args()
    rs.resolve_format(a)
    assert (a.format, a.idr_every) == ("h264", 1.0)
    a = args(backend="rdp")
    rs.resolve_format(a)
    assert a.format == "png"
    a = args(format="png")
    rs.resolve_format(a)
    assert a.format == "png"  # still selectable on console
    with pytest.raises(rs.r.Stop, match="at most 3570 s"):
        rs.resolve_format(args(seconds=3600.0))
    with pytest.raises(rs.r.Stop, match="8192 MB"):
        rs.resolve_format(args(max_bytes=9 * 10**9))
    with pytest.raises(rs.r.Stop, match="0..60"):
        rs.resolve_format(args(idr_every=90.0))
    assert rs.RECORDER_VERSION == 6  # v6 (2026-10-28): the IO rule follows the sink


def test_a_sidecar_joins_a_shipped_session_and_is_never_replaced(
    ds: ModuleType, dirs: SimpleNamespace, tmp_path: Path
) -> None:
    """replay_states.py (Phase 3 M3): re-decoded packets join a shipped session as a sidecar;
    the shipped files stay exactly what was verified."""
    make_session(dirs.root, SID)
    assert ds.main(ship_argv(dirs)) == 0
    remote = dirs.dest / SID
    before = ds.read_checksums(remote / "checksums.sha256")
    src = tmp_path / "packets.states.jsonl.gz"
    src.write_bytes(b"\x1f\x8b states")
    record = ds.add_sidecar(remote, src)
    sums = ds.read_checksums(remote / "checksums.sha256")
    assert sums == {**before, "packets.states.jsonl.gz": ds.sha256_file(src)}
    assert (remote / "packets.states.jsonl.gz").read_bytes() == b"\x1f\x8b states"
    assert record["event"] == "sidecar" and index_lines(dirs.dest)[-1]["file"] == src.name
    with pytest.raises(ds.Refused):
        ds.add_sidecar(remote, src)  # never replaced
    bad = tmp_path / "manifest.json"
    bad.write_text("{}")
    with pytest.raises(ds.Refused):
        ds.add_sidecar(remote, bad)  # only packets.<kind>.jsonl.gz
    assert not list(remote.glob(".*.part"))


MOUNTS = """\
/dev/mapper/ubuntu--vg-ubuntu--lv / ext4 rw,relatime 0 0
tmpfs /dev/shm tmpfs rw,nosuid,nodev 0 0
192.168.1.6:/mnt/tank-main/poring-lab/datasets /mnt/poring-lab-datasets nfs4 rw 0 0
"""


def test_the_ship_guard_rule_follows_the_sessions_root(
    ds: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Batt 2026-10-29 (rogue-gef10.md AK-4): a ship from tmpfs stops only on sustained stall, like
    a recorder on tmpfs; a ship from a disk keeps the tolerant one-spike rule; unknown = disk."""
    assert ds.guard_rule(Path("/dev/shm/poring-lab-rec"), MOUNTS) == ds.RAM_RULE
    assert ds.guard_rule(Path("/home/batt/poring-lab-rec"), MOUNTS) == ds.DISK_RULE
    assert ds.guard_rule(Path("/dev/shm/poring-lab-rec"), "") == ds.DISK_RULE
    assert ds.RAM_RULE == {"threshold": 30.0, "sustain": 30.0, "spike": None}
    assert ds.DISK_RULE == {"threshold": 10.0, "sustain": 30.0, "spike": 25.0}
    # load_guard builds guarded_build's Guard with that rule (no docker: cgroup ids come back empty)
    monkeypatch.setattr(
        ds.subprocess, "run", lambda *a, **k: SimpleNamespace(stdout="", returncode=1)
    )
    ram = ds.load_guard(Path("/dev/shm/poring-lab-rec"), MOUNTS)
    disk = ds.load_guard(Path("/home/batt/poring-lab-rec"), MOUNTS)
    assert ram.describe() == ">30.0% for 30s"
    assert disk.describe() == ">10.0% for 30s or >25.0% once"
    # record_session uses the same objects (one definition)
    rs = load("record_session")
    assert rs.guard_rule(Path("/dev/shm/x"), MOUNTS) == ds.RAM_RULE
    assert rs.DISK_RULE == ds.DISK_RULE and rs.RAM_RULE == ds.RAM_RULE


def test_cmd_ship_builds_its_guard_for_its_root_and_says_which_rule(
    ds: ModuleType, dirs: SimpleNamespace, capsys: pytest.CaptureFixture[str]
) -> None:
    seen: list[Path] = []

    class Quiet:
        def describe(self) -> str:
            return ">30.0% for 30s"

        def breach(self) -> None:
            return None

    def factory(root: Path) -> Quiet:
        seen.append(root)
        return Quiet()

    make_session(dirs.root, SID)
    a = ds.parser().parse_args(ship_argv(dirs))
    assert ds.cmd_ship(a, factory) == 0
    assert seen == [dirs.root]
    assert f"IO guard: >30.0% for 30s (sessions under {dirs.root})" in capsys.readouterr().err
    assert not (dirs.root / SID).exists()


def test_the_ram_rule_lets_a_ship_ride_out_the_10_28_spike_and_stops_on_sustained_stall(
    ds: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Positive and negative case on one scripted capture cgroup: 10-28 17:04:54 cut the e4 ship on
    a single 29.0 % quant-postgres second (the disk rule); the RAM rule rides that out and still
    stops on 30 s above 30 %."""
    gb: Any = load("guarded_build")
    clock = {"t": 0.0}
    monkeypatch.setattr(gb.time, "monotonic", lambda: clock["t"])

    def run(rule: dict[str, Any], stall_pct: list[float]) -> object:
        f = tmp_path / "io.pressure"
        total = 0
        f.write_text(f"some avg10=0 total=0\nfull avg10=0 avg60=0 avg300=0 total={total}\n")
        clock["t"] = 0.0
        g = gb.Guard({"quant-postgres": f}, rule["threshold"], 1.0, sustain=rule["sustain"],
                     spike=rule["spike"])  # fmt: skip
        g.breach()
        for pct in stall_pct:
            clock["t"] += 1.0
            total += int(pct * 1e4)
            f.write_text(f"some avg10=0 total=0\nfull avg10=0 avg60=0 avg300=0 total={total}\n")
            hit = g.breach()
            if hit:
                return hit
        return None

    spike = [3.0] * 10 + [29.0] + [3.0] * 60
    sustained = [3.0] * 5 + [35.0] * 40
    assert run(ds.DISK_RULE, spike) is not None  # what cut the ship on 10-28
    assert run(ds.RAM_RULE, spike) is None
    hit = run(ds.RAM_RULE, sustained)
    assert hit is not None and hit[0] == "quant-postgres" and "above 30.0% for" in hit[2]
