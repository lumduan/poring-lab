"""scripts/flow_run.py: the /flows Run button's host helper (Batt 2026-11-13)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts"))

import dungeon_hunt as dh  # noqa: E402
import flow_config as fc  # noqa: E402
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
        "settings": {"fly_key": "F1"},
    }  # an argument or a setting in a request is ignored: every setting is the config file's
    assert fr.parse_request(json.dumps(req)) == {"id": "a1b2c3d4e5", "action": "start",
                                                 "flow": "xmas_dun02_rogue"}  # fmt: skip
    assert fr.parse_request("{") == "unparsable request"
    assert fr.parse_request(json.dumps({"id": "x", "action": "start"})) == "bad request id"
    assert "unknown flow" in str(fr.parse_request(json.dumps(
        {"id": "a1b2c3d4e5", "action": "start", "flow": "rm -rf"})))  # fmt: skip
    assert "unknown action" in str(fr.parse_request(json.dumps(
        {"id": "a1b2c3d4e5", "action": "exec", "flow": "xmas_dun02_rogue"})))  # fmt: skip
    stop = fr.parse_request(json.dumps({"id": "a1b2c3d4e5", "action": "stop", "flow": None}))
    assert isinstance(stop, dict) and stop["action"] == "stop"


# --- 2026-11-13 (Batt: "the Butterfly Wing on F9, the Fly Wing on F8; don't hard-code them";
# "nothing is fixed, we only put the defaults"; "a global config for every map's flow, a map's own
# on top") -- every setting is scripts/flow_config.py's, its value from settings/flowrun/config.json
def test_the_defaults_are_valid_settings_and_the_strategys_own() -> None:
    f = fr.FLOWS["xmas_dun02_rogue"]
    assert f.map == "xmas_dun02"
    for k, v in f.defaults.items():
        assert k in fc.BY_NAME and not fc.BY_NAME[k].tune, k  # a flag or a switch of its own
        assert fc.problem_of(fc.BY_NAME[k], v) is None, (k, v)
    own = {x.name for x in fc.FIELDS if x.flag or x.kind in ("switch", "choice")}
    assert own == set(f.defaults)  # every flag and switch has the flow's default
    assert fc.clash(f.defaults) is None
    p2 = dh.STRATEGIES[fr.FIXED[fr.FIXED.index("--strategy") + 1]]
    for k in ("potion_below", "fly_below", "fly_rate", "fly_rate_below"):
        assert f.defaults[k] == p2[k], k
    assert set(dh.SURVIVAL_RANGES) <= set(f.defaults)


def test_the_maps_own_value_first_then_every_maps_then_the_default() -> None:
    f = fr.FLOWS["xmas_dun02_rogue"]
    cfg = {"global": {"potion_below": 0.3, "LOOT_TRIM_HOVERS": 12, "fly_key": "F7"},
           "maps": {"xmas_dun02": {"potion_below": 0.5},
                    "prt_fild08": {"fly_key": "F6"}}}  # fmt: skip
    vals, src = fr.config_of(f, cfg)
    assert vals["potion_below"] == 0.5 and src["potion_below"] == "map"
    assert vals["fly_key"] == "F7" and src["fly_key"] == "global"  # another map's own is not hers
    assert vals["LOOT_TRIM_HOVERS"] == 12 and src["LOOT_TRIM_HOVERS"] == "global"
    assert vals["home_key"] == "F9" and src["home_key"] == "default"
    argv = fr.command(f, "x", None, vals)
    assert argv[argv.index("--potion-below") + 1] == "0.50"
    assert argv[argv.index("--fly-key") + 1] == "F7" and argv.count("--fly-key") == 1
    assert argv[argv.index("LOOT_TRIM_HOVERS=12") - 1] == "--tune"
    assert "--tune" not in fr.command(f, "x")  # nobody set a runner number: the runner's own


def test_two_settings_on_one_key_never_run() -> None:
    f = fr.FLOWS["xmas_dun02_rogue"]
    with pytest.raises(ValueError, match="both on F4"):
        fr.command(f, "x", None, {**f.defaults, "dagger_key": "F4"})


def test_the_runner_accepts_the_default_keys_and_another_set() -> None:
    """The defaults pass the runner's own key checks, and so does a person's other set of keys,
    as the runner composes them (dungeon@9.42)."""
    conf = dh.CHARS_CONF["rogue"]
    d = fr.FLOWS["xmas_dun02_rogue"].defaults
    for st in (dict(d), {**d, "heal_key": "F3", "fly_key": "F1", "home_key": "F2",
                         "knife_key": "F6", "dagger_key": "F7"}):  # fmt: skip
        no_steal = {w: k for w, k in conf["keys"].items() if w != "steal"}  # --steal is off
        keys, why = dh.person_keys(no_steal, st["heal_key"], st["dagger_key"])
        assert why is None
        assert dh.fly_key_refused(st["fly_key"], keys, st["knife_key"]) is None
        keys = {**keys, "fly": st["fly_key"], "home": st["home_key"]}
        assert dh.keys_clash(keys, st["knife_key"]) is None, st
        assert dh.steal_opener_refused(st["knife_key"], True, keys) is None, st


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


def test_a_broken_config_or_a_key_clash_refuses_before_anything_starts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    f = fr.FLOWS["xmas_dun02_rogue"]
    monkeypatch.setattr(fr, "busy_reason", lambda _lines: None)  # a live run on this host: not ours
    orig = fr.CONFIG_DIR
    try:
        fr.CONFIG_DIR = tmp_path
        for text, word in (("{", "not valid JSON"),
                           (json.dumps({"v": 2, "maps": {"xmas_dun02": {"dagger_key": "F4"}}}),
                            "both on F4")):  # fmt: skip
            (tmp_path / "config.json").write_text(text)
            h = fr.Helper(tmp_path)
            h.start(f, "a1b2c3d4e5")
            assert h.state == "refused" and word in h.detail and h.runner is None, h.detail
            assert "refused before any input" in h.detail
    finally:
        fr.CONFIG_DIR = orig
