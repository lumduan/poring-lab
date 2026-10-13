"""poring_packets.selftest (ADR-0007 Amendment C, Batt 2026-10-13): the sniffer's start-time checks.
A broken credential scrub must REFUSE the start; the real one passes on every login request id, on a
configured login port and by shape on any other port."""

from __future__ import annotations

from typing import Any

from poring_packets import selftest
from poring_packets.pcapng import LOGIN_REQUEST_IDS, LoginScrub


def test_the_real_scrub_passes_by_port_and_by_shape() -> None:
    assert selftest.scrub_failures(LoginScrub, frozenset({6900})) == []
    assert selftest.scrub_failures(LoginScrub, None) == []  # ports unknown: shape only


class Broken(LoginScrub):
    """Forgets to zero anything."""

    def __call__(self, seg: Any) -> bytes:
        return bytes(seg.frame)


class KeepsContinuations(LoginScrub):
    """Zeroes the first segment only."""

    def __call__(self, seg: Any) -> bytes:
        out = super().__call__(seg)
        return (
            bytes(seg.frame)
            if seg.payload[:2] not in {i.to_bytes(2, "little") for i in LOGIN_REQUEST_IDS}
            else out
        )


def test_a_broken_scrub_refuses_the_start() -> None:
    fails = selftest.scrub_failures(Broken, frozenset({6900}))
    assert len(fails) >= 2 * len(LOGIN_REQUEST_IDS)
    assert any("continuation" in f for f in selftest.scrub_failures(KeepsContinuations, None))


def test_main_refuses_on_a_table_failure(monkeypatch: Any, capsys: Any) -> None:
    monkeypatch.setattr(selftest, "table_failure", lambda: "TableError: stale")
    assert selftest.main() == 1
    assert "REFUSED" in capsys.readouterr().out
    monkeypatch.setattr(selftest, "table_failure", lambda: None)
    assert selftest.main() == 0
