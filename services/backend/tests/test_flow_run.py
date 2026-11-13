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
    # dungeon@9.41 (Batt 2026-11-13): the map's two exits -- a bag over 50 %, a death
    assert argv[argv.index("--weight-home") + 1] == "0.50" and "--respawn" in argv
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
    # a start carries its SETTINGS, checked (the flow's defaults when the request names none)
    assert ok == {"id": "a1b2c3d4e5", "action": "start", "flow": "xmas_dun02_rogue",
                  "settings": {"fly_key": "F8", "home_key": "F9", "weight_home": 0.5,
                               "respawn_at": "645,481"}}  # fmt: skip
    assert fr.parse_request("{") == "unparsable request"
    assert fr.parse_request(json.dumps({"id": "x", "action": "start"})) == "bad request id"
    assert "unknown flow" in str(fr.parse_request(json.dumps(
        {"id": "a1b2c3d4e5", "action": "start", "flow": "rm -rf"})))  # fmt: skip
    assert "unknown action" in str(fr.parse_request(json.dumps(
        {"id": "a1b2c3d4e5", "action": "exec", "flow": "xmas_dun02_rogue"})))  # fmt: skip
    stop = fr.parse_request(json.dumps({"id": "a1b2c3d4e5", "action": "stop", "flow": None}))
    assert isinstance(stop, dict) and stop["action"] == "stop"


# --- 2026-11-13 (Batt: "the Butterfly Wing on F9, the Fly Wing on F8; don't hard-code them") ----
def test_the_settings_are_the_defaults_or_a_persons_from_fixed_lists() -> None:
    f = fr.FLOWS["xmas_dun02_rogue"]
    assert fr.settings_of(f, None) == {"fly_key": "F8", "home_key": "F9", "weight_home": 0.5,
                                       "respawn_at": "645,481"}  # fmt: skip
    assert fr.settings_of(f, {"fly_key": "F6", "weight_home": 0.6, "respawn_at": "600,500"}) == {
        "fly_key": "F6", "home_key": "F9", "weight_home": 0.6, "respawn_at": "600,500"}  # fmt: skip
    bad = (({"fly_key": "F10"}, "not a row-1"), ({"home_key": "Enter"}, "not a row-1"),
           ({"fly_key": "F4"}, "uses already"), ({"home_key": "F1"}, "uses already"),
           ({"fly_key": "F9"}, "two different keys"), ({"weight_home": 0.33}, "is not one of"),
           ({"weight_home": True}, "is not one of"), ({"weight_home": "0.5"}, "is not one of"),
           ({"steal_opener": "F2"}, "unknown setting"),
           ({"respawn_at": "1280,10"}, "not a point"), ({"respawn_at": "10,720"}, "not a point"),
           ({"respawn_at": "645;481"}, "not a point"),
           ({"respawn_at": 645}, "not a point"))  # fmt: skip
    for raw, why in bad:
        got = fr.settings_of(f, raw)
        assert isinstance(got, str) and why in got, (raw, got)


def test_the_settings_become_flags_and_nothing_else_does() -> None:
    f = fr.FLOWS["xmas_dun02_rogue"]
    st = fr.settings_of(f, {"fly_key": "F7", "home_key": "F6", "weight_home": 0.4})
    assert isinstance(st, dict)
    argv = fr.command(f, "flowrun-x", None, st)
    assert argv[argv.index("--fly-key") + 1] == "F7"
    assert argv[argv.index("--player-home-key") + 1] == "F6"
    assert argv[argv.index("--weight-home") + 1] == "0.40"
    assert argv.count("--fly-key") == 1 and argv.count("--weight-home") == 1
    assert argv[argv.index("--respawn-at") + 1] == "645,481"  # the default point
    req = {"id": "a1b2c3d4e5", "action": "start", "flow": "xmas_dun02_rogue",
           "settings": {"fly_key": "F4"}}  # fmt: skip
    assert "uses already" in str(fr.parse_request(json.dumps(req)))
    req["settings"] = ["F8"]
    assert fr.parse_request(json.dumps(req)) == "settings must be an object"


def test_the_runner_accepts_the_default_keys_with_the_runs_own() -> None:
    """The defaults pass the runner's own key checks (no key of the run's is taken twice)."""
    conf = dh.CHARS_CONF["rogue"]
    f = fr.FLOWS["xmas_dun02_rogue"]
    keys = {**conf["keys"], "fly": f.settings["fly_key"]}
    assert dh.fly_key_refused(f.settings["fly_key"], conf["keys"], "F4") is None
    assert set(f.reserved_keys) == {
        k for w, k in conf["keys"].items() if w != "fly" and k.startswith("F")
    } | {"F4"}
    assert f.settings["home_key"] not in keys.values()


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


def test_stop_goes_through_the_runners_normal_end(tmp_path: Path) -> None:
    """Stop = the runner's --stop-file (its normal end writes the packets); SIGINT backs it up."""
    argv = fr.command(fr.FLOWS["xmas_dun02_rogue"], "flowrun-x", tmp_path / "STOP")
    assert argv[argv.index("--stop-file") + 1] == str(tmp_path / "STOP")
    src = (ROOT / "scripts" / "dungeon_hunt.py").read_text()
    assert '"--stop-file"' in src and "if stop_file is not None and stop_file.exists():" in src
    i = src.index("if stop_file is not None and stop_file.exists():")
    assert "break  # the NORMAL end" in src[i : i + 400]
    assert fr.STOP_GRACE_S >= 30  # a tick is 0.2 s; a strike or loot step can take seconds
