"""scripts/sight_supply.py (rogue-xmas02.md 5, p13's E1 study): the monster supply of a run."""

from __future__ import annotations

import gzip
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))
import sight_supply as ss  # noqa: E402

T0, T1 = 1_000_000_000_000, 1_000_000_000_000 + 600 * 10**9  # a 10-minute window


def appear(gid: int, t: int, name: str = "Cruiser", objtype: int = 5) -> dict[str, object]:
    return {"type": "entity_appear", "objtype": objtype, "gid": gid, "t_mono_ns": t, "name": name}


def test_window_needs_start_and_end() -> None:
    ev = [{"kind": "x", "t_ns": 1}, {"kind": "run_start", "t_ns": T0},
          {"kind": "run_end", "t_ns": T1}]  # fmt: skip
    assert ss.window(ev) == (T0, T1)
    with pytest.raises(ValueError):
        ss.window([{"kind": "run_start", "t_ns": T0}])


def test_sightings_count_distinct_monsters_in_the_window() -> None:
    pk = [appear(1, T0 + 5), appear(1, T0 + 9),  # the same monster twice: once
          appear(2, T0 + 7, "Myst Case"),
          appear(3, T0 - 1),  # before the window
          appear(4, T0 + 8, "Thief8fce", objtype=1),  # a player, not a monster
          {"type": "entity_vanish", "gid": 5, "t_mono_ns": T0 + 3}]  # fmt: skip
    seen = ss.sightings(pk, T0, T1)
    assert seen == {1: "Cruiser", 2: "Myst Case"}
    got = ss.supply(seen, T0, T1, kills=1)
    assert got["seen"] == 2 and got["minutes"] == 10.0 and got["seen_per_10min"] == 2.0
    assert got["by_species"] == {"Cruiser": 1, "Myst Case": 1} and got["kills_per_seen"] == 0.5
    assert ss.supply({}, T0, T1)["kills_per_seen"] is None


def test_main_reads_a_session(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    (tmp_path / "events.jsonl").write_text(
        json.dumps({"kind": "run_start", "t_ns": T0}) + "\n"
        + json.dumps({"kind": "run_end", "t_ns": T1}) + "\n")  # fmt: skip
    with gzip.open(tmp_path / "packets.jsonl.gz", "wt") as fh:
        fh.write(json.dumps(appear(7, T0 + 1)) + "\n")
    assert ss.main([str(tmp_path), "--kills", "1"]) == 0
    rep = json.loads(capsys.readouterr().out)
    assert rep["seen"] == 1 and rep["kills_per_seen"] == 1.0
