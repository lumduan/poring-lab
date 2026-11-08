"""poring_vision.bar_bench (bot-server-migration.md 16-17): its pure helpers, on the host."""

from __future__ import annotations

from poring_vision import bar_bench as bb


class FakeTensor:
    def backward(self) -> None:  # what tensors() recognises a tensor by
        pass


def test_tensors_walks_dicts_and_lists() -> None:
    a, b, c = FakeTensor(), FakeTensor(), FakeTensor()
    # ultralytics 8.4's train-mode head returns a dict (the 11-08 probe failed on it)
    assert bb.tensors({"one2many": [a, b], "x": "not a tensor", "y": (c,)}) == [a, b, c]
    assert bb.tensors(a) == [a] and bb.tensors([]) == [] and bb.tensors(3) == []


def test_stats_and_rates() -> None:
    st = bb.stats([3.0, 1.0, 2.0, 10.0])
    assert st["median_ms"] == 2.5 and st["p90_ms"] == 10.0
    assert bb.gbps(1_000_000_000, 1000.0) == 1.0  # 1 GB in 1 s
    assert bb.gbps(11_300_000, 3.48) > 3.2  # the 11-08 float32 frame copy
