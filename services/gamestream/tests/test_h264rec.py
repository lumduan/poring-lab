"""The raw H.264 recorder (Post-S2 round C1) on the host: synthetic access units, no PyAV."""

import json
import os
import sys
import time
from pathlib import Path

import numpy as np
import pytest

GAMESTREAM = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(GAMESTREAM))

from s2spike import h264rec  # noqa: E402

SPS, PPS = b"\x00\x00\x00\x01\x67\x64", b"\x00\x00\x00\x01\x68\xee"
IDR = SPS + PPS + b"\x00\x00\x01\x65\x88\x80" + b"\x11" * 50
P = b"\x00\x00\x00\x01\x41\x9a" + b"\x22" * 30
RID = "20261004T120000-console-c3-h264-idr2"


def unit(au: bytes, fid: int) -> h264rec.Unit:
    return h264rec.Unit(au, [fid] if fid >= 0 else [], fid, 0, fid * 33, 1000 + fid, 5_000 + fid)


def frame(v: int) -> np.ndarray:
    return np.full((4, 6, 4), v, np.uint8)


def control(root: Path, text: str, age_s: float = 0.0) -> None:
    (root / "control").write_text(text + "\n")
    t = time.time() - age_s
    os.utime(root / "control", (t, t))


def wait_done(root: Path, rid: str) -> dict:
    for _ in range(100):
        done = root / f"{rid}.done.json"
        if done.exists():
            return json.loads(done.read_text())
        time.sleep(0.02)
    raise AssertionError("no done.json")


@pytest.fixture
def rec(tmp_path: Path):
    idr_calls: list[float] = []
    r = h264rec.Recorder(tmp_path, lambda: idr_calls.append(time.time()), lambda m: None,
                         {"pyav": "test"})  # fmt: skip
    r._stop.set()  # the tests call poll() themselves
    r.idr_calls = idr_calls  # type: ignore[attr-defined]
    yield r
    r.close()


def test_nal_parsing() -> None:
    assert h264rec.nal_types(IDR) == [7, 8, 5] and h264rec.is_idr(IDR)
    assert h264rec.nal_types(P) == [1] and not h264rec.is_idr(P)


@pytest.mark.parametrize(("text", "ok"), [
    (f"start {RID} 2 240 1000", True), ("stop", True),
    (f"start {RID} 2 240", False), ("start ../etc 2 240 1000", False),
    (f"start {RID.upper()} 2 240 1000", False), (f"start {RID} 99 240 1000", False),
    (f"start {RID} 2 99999 1000", False), (f"start {RID} x 240 1000", False),
])  # fmt: skip
def test_the_control_grammar_is_strict(text: str, ok: bool) -> None:
    assert (h264rec.parse_control(text) is not None) is ok


def test_a_recording_starts_at_the_first_idr_and_ends_as_a_finished_set(
    rec: h264rec.Recorder, tmp_path: Path
) -> None:
    control(tmp_path, f"start {RID} 0 240 1000")
    rec.poll()
    assert rec.active is not None and len(rec.idr_calls) == 1  # asked for an IDR at once
    rec.offer(unit(P, 1), [frame(1)])  # before the first IDR: not written
    rec.offer(unit(IDR, 2), [frame(2)])
    rec.offer(unit(P, 3), [frame(3)])
    rec.offer(unit(P, -1), [])  # a live decode error: kept, flagged
    control(tmp_path, "stop")
    rec.poll()
    summary = wait_done(tmp_path, RID)
    assert summary["reason"] == "stop"
    assert (summary["aus"], summary["idrs"], summary["frames"]) == (3, 1, 2)
    assert summary["skipped_before_idr"] == 1 and summary["decode_errors"] == 1
    assert summary["hashes_complete"] and summary["versions"] == {"pyav": "test"}
    data = (tmp_path / f"{RID}.h264").read_bytes()
    assert data == IDR + P + P  # exactly the access units, from the IDR on
    rows = (tmp_path / f"{RID}.idx.csv").read_text().splitlines()
    assert rows[0] == h264rec.IDX_HEADER.strip() and len(rows) == 4
    assert rows[1].split(",")[1:5] == ["2", "2", "0", "1"]  # frame_id 2, the IDR flag
    assert rows[3].split(",")[1] == "-1"
    hashes = dict(line.split(",") for line in
                  (tmp_path / f"{RID}.hash.csv").read_text().splitlines()[1:])  # fmt: skip
    assert hashes["2"] == h264rec.frame_digest(np.ascontiguousarray(frame(2)))
    assert set(hashes) == {"1", "2", "3"}  # every decoded frame; checks join by frame_id
    assert not list(tmp_path.glob(f".{RID}*"))  # no dot file left: the set is finished


def test_the_dead_man_and_the_caps_end_a_recording(rec: h264rec.Recorder, tmp_path: Path) -> None:
    control(tmp_path, f"start {RID} 0 240 1000")
    rec.poll()
    rec.offer(unit(IDR, 1), [frame(1)])
    control(tmp_path, f"start {RID} 0 240 1000", age_s=h264rec.STALE_S + 1)
    rec.poll()
    assert wait_done(tmp_path, RID)["reason"].startswith("control file stale")
    # the same id never records twice; a new id with a tiny size cap stops on the cap
    control(tmp_path, f"start {RID} 0 240 1000")
    rec.poll()
    assert rec.active is None
    rid2 = RID + "-b"
    control(tmp_path, f"start {rid2} 0 240 0.00001")
    rec.poll()
    rec.offer(unit(IDR, 5), [frame(5)])
    time.sleep(0.1)
    rec.poll()
    assert wait_done(tmp_path, rid2)["reason"] == "size cap"


def test_a_stale_start_is_never_obeyed(rec: h264rec.Recorder, tmp_path: Path) -> None:
    control(tmp_path, f"start {RID} 0 240 1000", age_s=h264rec.STALE_S + 1)
    rec.poll()
    assert rec.active is None


def test_a_full_queue_drops_to_the_next_idr(
    rec: h264rec.Recorder, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    control(tmp_path, f"start {RID} 0 240 1000")
    rec.poll()
    active = rec.active
    assert active is not None
    active.offer(unit(IDR, 1), [frame(1)])
    while not active.au_q.empty():
        time.sleep(0.01)
    monkeypatch.setattr(active.au_q, "put_nowait", lambda _u: (_ for _ in ()).throw(
        __import__("queue").Full()))  # fmt: skip
    active.offer(unit(P, 2), [frame(2)])  # dropped
    monkeypatch.undo()
    active.offer(unit(P, 3), [frame(3)])  # after the drop: a gap until the next IDR
    active.offer(unit(IDR, 4), [frame(4)])
    control(tmp_path, "stop")
    rec.poll()
    s = wait_done(tmp_path, RID)
    assert s["queue_overflows"] == 1 and s["gaps"] == 1 and s["idrs"] == 2
    assert (tmp_path / f"{RID}.h264").read_bytes() == IDR + IDR
    assert s["idr_requests"] == 2  # the start + the overflow


def test_the_stream_end_finishes_a_running_recording(tmp_path: Path) -> None:
    r = h264rec.Recorder(tmp_path, lambda: None, lambda m: None)
    r._stop.set()
    control(tmp_path, f"start {RID} 0 240 1000")
    r.poll()
    r.offer(unit(IDR, 1), [frame(1)])
    r.close()
    assert wait_done(tmp_path, RID)["reason"] == "stream ended"


def test_a_missing_dir_is_refused_loudly(tmp_path: Path) -> None:
    with pytest.raises(OSError, match="missing or not writable"):
        h264rec.Recorder(tmp_path / "nope", lambda: None, lambda m: None)
