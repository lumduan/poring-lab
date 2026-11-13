"""scripts/flow_run.py: the /flows Run button's host helper (Batt 2026-11-13)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts"))

import dungeon_hunt as dh  # noqa: E402
import flow_run as fr  # noqa: E402


def test_the_flow_is_the_4dq_base_as_a_player() -> None:
    f = fr.FLOWS["xmas_dun02_rogue"]
    argv = fr.command(f, "flowrun-x")
    assert argv[:9] == ["nice", "-n", "10", "uv", "run", "--quiet", "python",
                        "scripts/dungeon_hunt.py", "run"]  # fmt: skip
    for flag in ("--player-mode", "--bare-steal", "--bare-ready", "--steal-opener", "--swap-gap",
                 "--loot-items", "--loot-memory", "--value-target", "--engage-screen"):  # fmt: skip
        assert flag in argv, flag
    assert "--clear-map" not in argv  # a GM line: refused under --player-mode
    assert argv[argv.index("--minutes") + 1] == "120"  # Batt: the 2-h cap
    assert argv[argv.index("--label") + 1] == "flowrun-x"


def test_every_flag_exists_and_player_mode_accepts_the_set() -> None:
    import argparse

    src = (ROOT / "scripts" / "dungeon_hunt.py").read_text()
    argv = fr.command(fr.FLOWS["xmas_dun02_rogue"], "flowrun-x")
    for tok in argv[9:]:
        if tok.startswith("--"):
            assert f'"{tok}"' in src, tok  # a renamed flag fails here, not at 10:00
    ns = argparse.Namespace(player_mode=True, clear_map=False, stage_mob=None, stage_at=None,
                            start_cell=None, engage="defend_scan")  # fmt: skip
    assert dh.player_mode_refused(ns) is None


def test_requests_name_a_flow_and_never_carry_arguments() -> None:
    req = {
        "id": "a1b2c3d4e5",
        "action": "start",
        "flow": "xmas_dun02_rogue",
        "args": ["--clear-map"],
    }  # an argument in a request is ignored
    ok = fr.parse_request(json.dumps(req))
    assert ok == {"id": "a1b2c3d4e5", "action": "start", "flow": "xmas_dun02_rogue"}
    assert fr.parse_request("{") == "unparsable request"
    assert fr.parse_request(json.dumps({"id": "x", "action": "start"})) == "bad request id"
    assert "unknown flow" in str(fr.parse_request(json.dumps(
        {"id": "a1b2c3d4e5", "action": "start", "flow": "rm -rf"})))  # fmt: skip
    assert "unknown action" in str(fr.parse_request(json.dumps(
        {"id": "a1b2c3d4e5", "action": "exec", "flow": "xmas_dun02_rogue"})))  # fmt: skip
    stop = fr.parse_request(json.dumps({"id": "a1b2c3d4e5", "action": "stop", "flow": None}))
    assert isinstance(stop, dict) and stop["action"] == "stop"


def test_one_input_writer_at_a_time() -> None:
    assert fr.busy_reason(["/usr/bin/bash", "next-server"]) is None
    chain = ".venv/bin/python /dev/shm/poring-lab-tmp/chain/chain.py 179 --mvp-live"
    assert "chain" in str(fr.busy_reason([chain]))
    runner = "/home/bot/docker/poring-lab/.venv/bin/python scripts/dungeon_hunt.py run --char rogue"
    assert "another runner" in str(fr.busy_reason([runner]))
    # uv's own wrapper line is not counted twice (its python child is)
    assert fr.busy_reason(["uv run --quiet python scripts/dungeon_hunt.py run --char x"]) is None


def test_a_request_is_consumed_once(tmp_path: Path) -> None:
    h = fr.Helper(tmp_path)
    (tmp_path / "request.json").write_text("not json")
    assert h.take_request() is None and not (tmp_path / "request.json").exists()
    assert "refused" in h.detail
    h.write_status()
    st = json.loads((tmp_path / "status.json").read_text())
    assert st["state"] == "idle" and "xmas_dun02_rogue" in st["flows"]
