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
                  "settings": DEFAULTS}  # fmt: skip
    assert fr.parse_request("{") == "unparsable request"
    assert fr.parse_request(json.dumps({"id": "x", "action": "start"})) == "bad request id"
    assert "unknown flow" in str(fr.parse_request(json.dumps(
        {"id": "a1b2c3d4e5", "action": "start", "flow": "rm -rf"})))  # fmt: skip
    assert "unknown action" in str(fr.parse_request(json.dumps(
        {"id": "a1b2c3d4e5", "action": "exec", "flow": "xmas_dun02_rogue"})))  # fmt: skip
    stop = fr.parse_request(json.dumps({"id": "a1b2c3d4e5", "action": "stop", "flow": None}))
    assert isinstance(stop, dict) and stop["action"] == "stop"


# --- 2026-11-13 (Batt: "the Butterfly Wing on F9, the Fly Wing on F8; don't hard-code them";
# ~13:3x "everything a user can set again; nothing fixed, we only put the defaults") -------------
DEFAULTS = {"fly_key": "F8", "home_key": "F9", "weight_home": 0.5, "respawn_at": "645,481",
            "respawn_confirm_at": "714,405", "heal_key": "F1", "knife_key": "F4",
            "dagger_key": "F5", "knife_max_s": 8.0, "knife_hp_min": 0.5}  # fmt: skip


def test_the_settings_are_the_defaults_or_a_persons_from_fixed_lists() -> None:
    f = fr.FLOWS["xmas_dun02_rogue"]
    assert fr.settings_of(f, None) == DEFAULTS
    assert f.reserved_keys == ()  # no key is the run's own: every one is the person's
    assert fr.settings_of(f, {"respawn_confirm_at": "none"})["respawn_confirm_at"] == "none"  # type: ignore[index]
    assert fr.settings_of(f, {"fly_key": "F6", "weight_home": 0.6, "respawn_at": "600,500"}) == {
        **DEFAULTS, "fly_key": "F6", "weight_home": 0.6, "respawn_at": "600,500"}  # fmt: skip
    # the Knife swap, the heal key (Batt's "F4, wait 200 ms, F5" = a Knife time of 0.2 s)
    mine = fr.settings_of(f, {"heal_key": "F2", "knife_key": "F6", "dagger_key": "F7",
                              "knife_max_s": 0.2, "knife_hp_min": 0.35})  # fmt: skip
    assert isinstance(mine, dict) and mine["knife_max_s"] == 0.2 and mine["knife_hp_min"] == 0.35
    assert fr.settings_of(f, {"knife_max_s": 20})["knife_max_s"] == 20.0  # type: ignore[index]
    bad = (({"fly_key": "F10"}, "not a row-1"), ({"home_key": "Enter"}, "not a row-1"),
           ({"fly_key": "F4"}, "the Fly Wing and the Knife are both on F4"),
           ({"home_key": "F1"}, "the heal item and the Butterfly Wing are both on F1"),
           ({"dagger_key": "F4"}, "the Knife and the dagger are both on F4"),
           ({"heal_key": "F8"}, "the heal item and the Fly Wing are both on F8"),
           ({"knife_key": "F12"}, "not a row-1"),
           ({"knife_max_s": 0.1}, "is not a time"), ({"knife_max_s": 21}, "is not a time"),
           ({"knife_max_s": "8"}, "is not a time"), ({"knife_max_s": True}, "is not a time"),
           ({"knife_hp_min": 0.33}, "is not one of"), ({"knife_hp_min": 0.95}, "is not one of"),
           ({"fly_key": "F9"}, "two different keys"), ({"weight_home": 0.33}, "is not one of"),
           ({"weight_home": True}, "is not one of"), ({"weight_home": "0.5"}, "is not one of"),
           ({"steal_opener": "F2"}, "unknown setting"),
           ({"respawn_at": "1280,10"}, "not a point"), ({"respawn_at": "10,720"}, "not a point"),
           ({"respawn_at": "645;481"}, "not a point"),
           ({"respawn_at": 645}, "not a point"),
           ({"respawn_confirm_at": "1300,1"}, "not a point"),
           ({"respawn_confirm_at": "NONE!"}, "not a point"))  # fmt: skip
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
    assert argv[argv.index("--respawn-confirm-at") + 1] == "714,405"
    for flag, v in (("--heal-key", "F1"), ("--steal-opener", "F4"), ("--dagger-key", "F5"),
                    ("--knife-max-s", "8.00"), ("--knife-hp-min", "0.50")):  # fmt: skip
        assert argv[argv.index(flag) + 1] == v and argv.count(flag) == 1, flag
    req = {"id": "a1b2c3d4e5", "action": "start", "flow": "xmas_dun02_rogue",
           "settings": {"fly_key": "F4"}}  # fmt: skip
    assert "both on F4" in str(fr.parse_request(json.dumps(req)))
    req["settings"] = ["F8"]
    assert fr.parse_request(json.dumps(req)) == "settings must be an object"


def test_the_runner_accepts_the_default_keys_with_the_runs_own() -> None:
    """The defaults pass the runner's own key checks (no key of the run's is taken twice), and
    a person's other set of keys does too, as the runner composes them (dungeon@9.42)."""
    conf = dh.CHARS_CONF["rogue"]
    f = fr.FLOWS["xmas_dun02_rogue"]
    for st in (dict(f.settings), {**f.settings, "heal_key": "F3", "fly_key": "F1", "home_key": "F2",
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


# --- 2026-11-13 ~14:2x (Batt: "the heal and escape numbers: a global config for every map's flow;
# a map's flow that sets them again overrides it, that map's config first") ---------------------
def test_the_survival_defaults_are_the_strategys_own() -> None:
    f = fr.FLOWS["xmas_dun02_rogue"]
    strat = dh.STRATEGIES["P2"]
    assert f.map == "xmas_dun02" and "--strategy" in fr.FIXED
    assert fr.FIXED[fr.FIXED.index("--strategy") + 1] == "P2"
    assert f.survival == {k: strat[k] for k in fr.SURVIVAL_FLAGS}
    assert set(fr.SURVIVAL_FLAGS) == set(dh.SURVIVAL_RANGES)


def test_the_maps_own_numbers_first_then_every_maps_then_the_defaults() -> None:
    f = fr.FLOWS["xmas_dun02_rogue"]
    g = {"potion_below": 0.3, "fly_below": 0.15, "fly_rate": 200.0, "fly_rate_below": 0.6}
    m = {"potion_below": 0.5, "fly_below": 0.25, "fly_rate": 120.0, "fly_rate_below": 0.55}
    assert fr.survival_of(f, {}) == (f.survival, dict.fromkeys(f.survival, "default"))
    assert fr.survival_of(f, {"global": g, "maps": {}}) == (g, dict.fromkeys(g, "global"))
    assert fr.survival_of(f, {"global": g, "maps": {"xmas_dun02": m}}) == (
        m,
        dict.fromkeys(m, "map"),
    )
    assert fr.survival_of(f, {"global": g, "maps": {"prt_fild08": m}})[0] == g  # another map's
    vals, src = fr.survival_of(f, {"global": {"fly_below": 0.1}, "maps": {}})
    assert vals == {**f.survival, "fly_below": 0.1} and src["fly_below"] == "global"
    argv = fr.command(f, "x", None, None, m)
    for flag, v in (("--potion-below", "0.50"), ("--fly-below", "0.25"), ("--fly-rate", "120"),
                    ("--fly-rate-below", "0.55")):  # fmt: skip
        assert argv[argv.index(flag) + 1] == v and argv.count(flag) == 1, flag
    assert "--fly-rate" in fr.command(f, "x")  # the defaults when no config is given


def test_the_survival_file_is_checked_and_a_broken_one_refuses(tmp_path: Path) -> None:
    p = tmp_path / "survival.json"
    assert fr.read_survival(p) == {}
    p.write_text(json.dumps({"v": 1, "global": {"potion_below": 0.35}, "maps": {"xmas_dun02": {
        "fly_rate": 199.6}}}))  # fmt: skip
    assert fr.read_survival(p) == {"global": {"potion_below": 0.35},
                                   "maps": {"xmas_dun02": {"fly_rate": 200.0}}}  # fmt: skip
    for bad, why in (("{", "not valid JSON"), (json.dumps({"v": 2}), "version 1"),
                     (json.dumps({"v": 1, "global": {"potion_below": 0.33}}), "is not one of"),
                     (json.dumps({"v": 1, "global": {"fly_rate": 20}}), "HP/s"),
                     (json.dumps({"v": 1, "global": {"heal": 1}}), "unknown survival"),
                     (json.dumps({"v": 1, "maps": {"../x": {}}}), "not a map name"),
                     (json.dumps({"v": 1, "maps": {"m": {"fly_below": True}}}),
                      "not a number")):  # fmt: skip
        p.write_text(bad)
        got = fr.read_survival(p)
        assert isinstance(got, str) and why in got, (bad, got)
    # the helper refuses to start on a broken file, before anything starts
    h = fr.Helper(tmp_path)
    orig = fr.SURVIVAL_FILE
    try:
        fr.SURVIVAL_FILE = p
        h.start(fr.FLOWS["xmas_dun02_rogue"], "a1b2c3d4e5")
    finally:
        fr.SURVIVAL_FILE = orig
    assert h.state == "refused" and "refused before any input" in h.detail and h.runner is None
