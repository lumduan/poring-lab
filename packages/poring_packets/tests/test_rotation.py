"""The sniffer's capture shards (ADR-0007): pcapng + events rotate by age or size -- on the first
packet after the limit, not on the wall-clock hour -- and retention removes the oldest shards by
age or total size, never the open shard and never a clock map."""

import os
from pathlib import Path

import pytest

from poring_packets import sniffer
from poring_packets.sniffer import Rotating


class Clock:
    def __init__(self, t: float) -> None:
        self.t = t

    def __call__(self) -> float:
        return self.t


@pytest.fixture
def clock(monkeypatch: pytest.MonkeyPatch) -> Clock:
    c = Clock(1_790_000_000.0)
    monkeypatch.setattr(sniffer.time, "time", c)
    return c


def shards(root: Path) -> list[str]:
    return sorted(p.name for p in root.iterdir())


def test_rotates_by_age_on_the_next_packet(tmp_path: Path, clock: Clock) -> None:
    r = Rotating(tmp_path)
    first, _ = r.ensure()
    clock.t += sniffer.ROTATE_S - 1
    assert r.ensure()[0] is first  # not yet
    clock.t += 1
    second, _ = r.ensure()
    assert second is not first
    r.close()
    names = shards(tmp_path)
    assert len([n for n in names if n.startswith("capture-")]) == 2
    assert len([n for n in names if n.startswith("events-")]) == 2


def test_rotates_by_size(tmp_path: Path, clock: Clock, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sniffer, "ROTATE_BYTES", 2_000)
    r = Rotating(tmp_path)
    pcap, _ = r.ensure()
    for i in range(40):
        pcap.packet(b"\x00" * 60, int(clock.t * 1e9) + i)
    assert pcap.bytes >= 2_000
    clock.t += 1  # a new second: a new shard name
    assert r.ensure()[0] is not pcap
    r.close()


def test_retention_removes_the_oldest_by_size_never_the_open_shard_or_a_clock_map(
    tmp_path: Path, clock: Clock, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sniffer, "RETAIN_BYTES", 3_000)
    for i, name in enumerate(["capture-a.pcapng", "events-a.jsonl.gz", "capture-b.pcapng"]):
        p = tmp_path / name
        p.write_bytes(b"x" * 1_500)
        os.utime(p, (clock.t - 100 + i, clock.t - 100 + i))
    keep = tmp_path / "capture-a.map.jsonl"
    keep.write_bytes(b"x" * 1_500)
    os.utime(keep, (clock.t - 200, clock.t - 200))
    r = Rotating(tmp_path)
    pcap, _ = r.ensure()
    names = shards(tmp_path)
    assert "capture-a.pcapng" not in names  # the oldest shards go first...
    assert "capture-a.map.jsonl" in names  # ...but never a clock map
    assert pcap.path.name in names  # ...and never the open shard
    r.close()


def test_retention_by_age(tmp_path: Path, clock: Clock) -> None:
    old = tmp_path / "capture-old.pcapng"
    old.write_bytes(b"x")
    os.utime(old, (clock.t - sniffer.RETAIN_S - 1,) * 2)
    fresh = tmp_path / "capture-fresh.pcapng"
    fresh.write_bytes(b"x")
    os.utime(fresh, (clock.t - 60,) * 2)
    r = Rotating(tmp_path)
    r.ensure()
    names = shards(tmp_path)
    assert "capture-old.pcapng" not in names and "capture-fresh.pcapng" in names
    r.close()
