"""scripts/selfpos_calibrate.py's packet truth (Phase 3 T0, offline): our own walks and our own AID.

The recorded sessions start at the last map change, so they never carry login_accepted -- our own
AID. Without it the Timeline ignored our own entity_stop and kept a walk's planned end: the
readout said 168 372 where the Timeline said 168 371. The truth infers the AID."""

import gzip
import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType

import pytest

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "selfpos_calibrate.py"
ME, MOB, OTHER_PLAYER = 2_000_002, 110_000_001, 2_000_005
T0 = 5_000_000_000_000  # ns on CLOCK_MONOTONIC; the server tick is the same clock in ms


@pytest.fixture(scope="module")
def cal() -> ModuleType:
    sys.path.insert(0, str(SCRIPT.parent))
    spec = importlib.util.spec_from_file_location("selfpos_calibrate", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def ev(t_ms: int, etype: str, **fields: object) -> dict[str, object]:
    return {"t_mono_ns": T0 + t_ms * 1_000_000, "type": etype, **fields}


def walk(t_ms: int, x0: int, y0: int, x1: int, y1: int) -> dict[str, object]:
    tick = (T0 // 1_000_000 + t_ms) % (1 << 32)
    return ev(t_ms, "self_move", x0=x0, y0=y0, x1=x1, y1=y1, server_tick=tick)


def test_our_aid_is_the_one_player_that_stops_but_never_appears(cal: ModuleType) -> None:
    events = [
        ev(0, "entity_appear", gid=MOB),
        ev(10, "entity_stop", gid=MOB, x=1, y=1),
        ev(20, "entity_appear", gid=OTHER_PLAYER),
        ev(30, "entity_stop", gid=OTHER_PLAYER, x=2, y=2),
        ev(40, "entity_stop", gid=ME, x=3, y=3),
    ]
    assert cal.infer_self_aid(events) == ME
    assert cal.infer_self_aid(events[:4]) is None  # nobody unexplained: unknown, never guessed
    two = [*events, ev(50, "entity_vanish", gid=2_000_009)]
    assert cal.infer_self_aid(two) is None  # two candidates: unknown


def test_walk_spans_follow_the_step_timing_and_end_where_cut(cal: ModuleType) -> None:
    events = [ev(0, "map_change", map="test.gat", x=10, y=10), walk(100, 10, 10, 13, 10)]
    (span,) = cal.self_walk_spans(events, {})
    assert span == (T0 + 100_000_000, T0 + 550_000_000)  # 3 straight steps of 150 ms
    cut = [*events, walk(300, 11, 10, 11, 13)]
    first, second = cal.self_walk_spans(cut, {})
    assert first[1] == T0 + 300_000_000 and second[0] == T0 + 300_000_000
    stopped = [ev(-1, "login_accepted", aid=ME), *events,
               ev(250, "entity_stop", gid=ME, x=11, y=10)]  # fmt: skip
    (span,) = cal.self_walk_spans(stopped, {})
    assert span[1] == T0 + 250_000_000


def test_a_walk_cut_short_by_our_own_stop_ends_where_the_server_stopped_us(
    cal: ModuleType, tmp_path: Path
) -> None:
    events = [
        ev(0, "map_change", map="test.gat", x=10, y=10),
        walk(100, 10, 10, 14, 10),
        ev(300, "entity_stop", gid=ME, x=11, y=10),  # the server stopped us one cell out
    ]
    (tmp_path / "manifest.json").write_text(json.dumps({"config": {}}))
    with gzip.open(tmp_path / "packets.jsonl.gz", "wt") as fh:
        fh.writelines(json.dumps(e) + "\n" for e in events)
    truth = cal.SessionTruth(tmp_path, {}, offset_ms="0", guard_ms=300, load_ms=0)
    assert truth.aid == ME and truth.aid_source == "inferred"
    later = truth.at(T0 + 2_000_000_000)
    assert later.kind == "standing" and later.pos == (11.0, 10.0)  # not the planned (14, 10)
    during = truth.at(T0 + 200_000_000)
    assert during.kind == "walking" and during.walk_dt_ms == 0


def test_cells_round_half_up(cal: ModuleType) -> None:
    assert [cal.cell_of(v) for v in (165.49, 165.5, 166.5, 167.0)] == [165, 166, 167, 167]
