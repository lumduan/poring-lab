"""scripts/flow_run.py: the /flows Run button's host helper (Batt 2026-11-13)."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

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
    # Batt 2026-11-19: no time limit unless a person sets one (was the 2-h cap): the byte-pinned
    # runner's --minutes has no "none", so it gets 10 years
    assert argv[argv.index("--minutes") + 1] == str(fc.NO_LIMIT_MINUTES) == "5256000"
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


def test_a_start_is_a_projects_and_never_carries_arguments() -> None:
    """2026-11-14 (live-blocks.md 12): the runner-only start went with the runner page; a start
    names the checked project (its node and hash) and nothing else -- no argument, no setting."""
    base = {"id": "a1b2c3d4e5", "action": "start", "flow": "project", "node": "xmas_dun02",
            "project_hash": "a" * 64, "max_s": 7200}  # fmt: skip
    assert fr.parse_request(json.dumps(base)) == base
    # 0 = no maximum run time (Batt 2026-11-19, ADR-0020 Amendment T): the backend's default now;
    # more than the old 24 h too; below 0 or above the IR's sanity cap is refused
    for ok in (0, 90_000):
        assert fr.parse_request(json.dumps({**base, "max_s": ok})) == {**base, "max_s": ok}
    for bad in (-1, 31_536_001, True, "7200"):
        assert "maximum run time" in str(fr.parse_request(json.dumps({**base, "max_s": bad})))
    for extra in ({"args": ["--clear-map"]}, {"settings": {"fly_key": "F1"}},
                  {"vals": {"minutes": 5}}):  # fmt: skip
        assert "nothing else" in str(fr.parse_request(json.dumps({**base, **extra}))), extra
    old = {"id": "a1b2c3d4e5", "action": "start", "flow": "xmas_dun02_rogue"}
    assert "unknown flow" in str(fr.parse_request(json.dumps(old)))
    assert fr.parse_request("{") == "unparsable request"
    assert fr.parse_request(json.dumps({"id": "x", "action": "start"})) == "bad request id"
    assert "unknown flow" in str(fr.parse_request(json.dumps(
        {"id": "a1b2c3d4e5", "action": "start", "flow": "rm -rf"})))  # fmt: skip
    assert "unknown action" in str(fr.parse_request(json.dumps(
        {"id": "a1b2c3d4e5", "action": "exec", "flow": "project"})))  # fmt: skip
    stop = fr.parse_request(json.dumps({"id": "a1b2c3d4e5", "action": "stop", "flow": None}))
    assert isinstance(stop, dict) and stop["action"] == "stop"


# --- 2026-11-13 (Batt: "the Butterfly Wing on F9, the Fly Wing on F8; don't hard-code them";
# "nothing is fixed, we only put the defaults"; "a global config for every map's flow, a map's own
# on top") -- every setting is scripts/flow_config.py's (poring_flow.settings); since 2026-11-14 its
# value is a project's setting block (the map node's > Global's > the default)
def test_the_defaults_are_valid_settings_and_the_strategys_own() -> None:
    f = fr.FLOWS["xmas_dun02_rogue"]
    assert f.map == "xmas_dun02"
    for k, v in f.defaults.items():
        assert k in fc.BY_NAME and not fc.BY_NAME[k].tune, k  # a flag or a switch of its own
        assert fc.problem_of(fc.BY_NAME[k], v) is None, (k, v)
    # an item setting (roles-not-names.md step 2) has the flow's default too: the player applies it
    # and step 3's alarm monsters (a monsters setting)
    own = {
        x.name for x in fc.FIELDS if x.flag or x.kind in ("switch", "choice", "item", "monsters")
    }
    assert own == set(f.defaults)  # every flag and switch has the flow's default
    assert fc.clash(f.defaults) is None
    p2 = dh.STRATEGIES[fr.FIXED[fr.FIXED.index("--strategy") + 1]]
    for k in ("potion_below", "fly_below", "fly_rate", "fly_rate_below"):
        assert f.defaults[k] == p2[k], k
    assert set(dh.SURVIVAL_RANGES) <= set(f.defaults)


def _project(node_vars: dict[str, Any], global_vars: dict[str, Any] | None) -> dict[str, Any]:
    """A project as the checked file holds it (the dict): a map node xmas_dun02 and, given its
    variables, a Global node; tab names are the settings' groups."""

    def tabs(vs: dict[str, Any]) -> list[dict[str, Any]]:
        by: dict[str, dict[str, Any]] = {}
        for k, v in vs.items():
            f = fc.BY_VAR.get(k)
            by.setdefault(f.group if f else "misc", {})[k] = {"kind": "lit", "value": v}
        return [{"name": t, "main": None, "defs": [], "vars": x} for t, x in by.items()]

    nodes: list[dict[str, Any]] = [{"id": "xmas_dun02", "kind": "map", "tabs": [
        {"name": "main", "main": [], "defs": [], "vars": {}}, *tabs(node_vars)]}]  # fmt: skip
    if global_vars is not None:
        nodes.append({"id": "global", "kind": "global", "tabs": tabs(global_vars)})
    return {"nodes": nodes}


def test_the_nodes_own_value_first_then_globals_then_the_default() -> None:
    """The name rule (project-model.md section 3) for the setting blocks: the map node's own over
    Global's over the default; a setting nobody wrote takes its default; deleting the node's
    block falls back to Global's, deleting that to the default."""
    f = fr.FLOWS["xmas_dun02_rogue"]
    doc = _project({"potion_below": 0.5}, {"potion_below": 0.3, "LOOT_TRIM_HOVERS": 12,
                                           "fly_below": 0.25})  # fmt: skip
    vals, src, keys_src, why = fr.project_values(doc, "xmas_dun02", None)
    assert why is None and keys_src == "the settings"
    assert vals["potion_below"] == 0.5 and src["potion_below"] == "xmas_dun02/survival"
    assert vals["fly_below"] == 0.25 and src["fly_below"] == "global/survival"
    assert vals["LOOT_TRIM_HOVERS"] == 12 and src["LOOT_TRIM_HOVERS"] == "global/loot"
    assert vals["home_key"] == "F9" and src["home_key"] == "default"
    assert vals["KILL_GAP_S"] == fc.DEFAULTS["KILL_GAP_S"] and src["KILL_GAP_S"] == "default"
    argv = fr.command(f, "x", None, vals)
    assert argv[argv.index("--potion-below") + 1] == "0.50"
    assert argv[argv.index("--fly-below") + 1] == "0.25" and argv.count("--fly-below") == 1
    assert argv[argv.index("LOOT_TRIM_HOVERS=12") - 1] == "--tune"
    assert argv.count("--tune") == 1  # every other runner number at its default: not passed
    assert "--tune" not in fr.command(f, "x")  # nobody set a runner number: the runner's own
    # deleted on the node: Global's; deleted on Global too: the default
    gone = fr.project_values(_project({}, {"potion_below": 0.3}), "xmas_dun02", None)
    assert gone[0]["potion_below"] == 0.3 and gone[1]["potion_below"] == "global/survival"
    none = fr.project_values(_project({}, None), "xmas_dun02", None)
    assert none[0]["potion_below"] == fc.DEFAULTS["potion_below"] == 0.4
    assert none[1]["potion_below"] == "default"
    # a project without a setting block runs exactly the defaults (today's command)
    assert fr.command(f, "x", None, none[0]) == fr.command(f, "x")
    # the dotted runner constant and the two catalogue names take their variables' names
    vs = {"D0_PX": 300, "loot_step": "v1", "respawn_on_death": False}
    named = fr.project_values(_project(vs, None), "xmas_dun02", None)
    assert (named[0]["vt.D0_PX"], named[0]["loot"], named[0]["respawn"]) == (300, "v1", False)
    a = fr.command(f, "x", None, named[0])
    assert "vt.D0_PX=300" in a and a[a.index("--loot") + 1] == "v1" and "--no-respawn" in a


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


def test_the_helper_is_busy_while_another_input_writer_of_ours_plays(tmp_path: Path) -> None:
    """matpilot round 17 N5: GET /flows/run said "idle", "waiting for the Run button" while the
    live block player played an A/B run, and Run stayed enabled. The status is "busy" now, in the
    busy rule's words, while no run of the helper's own goes; idle again once the writer is gone."""
    series = "/home/bot/docker/poring-lab/.venv/bin/python scripts/stage4_ab.py run --label s4ab"
    player = "/home/bot/docker/poring-lab/.venv/bin/python scripts/flow_play.py play --project x"
    # the series counts for its whole length (its setup types too), never in busy_reason: the A/B
    # series call busy_reason before each of their runs and must not find themselves
    assert fr.writer_busy([series]) == "an A/B series is running (one input writer at a time)"
    assert fr.busy_reason([series]) is None
    quiet = (
        "python scripts/stage2_ab.py plan --label x",
        "python scripts/stage3_ab.py score",
        "uv run python scripts/stage2_ab.py run --label x",
        "less stage2_ab.py",
    )
    for ln in quiet:
        assert fr.writer_busy([ln]) is None, ln
    assert fr.writer_busy([player]) == fr.busy_reason([player])
    assert "live block player" in str(fr.writer_busy([player]))
    # the pure state rule
    why = "the live block player is playing (one input writer at a time)"
    assert fr.busy_state("idle", fr.IDLE_DETAIL, why) == ("busy", why)
    assert fr.busy_state("busy", why, None) == ("idle", fr.IDLE_DETAIL)
    end = "Stopped by you after 3 min."
    assert fr.busy_state("ended", end, why) == ("ended", end)  # the end words stay; `busy` says it
    assert fr.busy_state("running", "playing", None) == ("running", "playing")
    # the helper: busy, in the status, then idle; never while a run of its own goes
    h = fr.Helper(tmp_path)
    h.busy_tick([player])
    h.write_status()
    st = json.loads((tmp_path / "status.json").read_text())
    assert (st["state"], st["detail"], st["busy"]) == ("busy", why, why)
    h.busy_tick(["/usr/bin/bash"])
    assert (h.state, h.detail, h.busy) == ("idle", fr.IDLE_DETAIL, None)
    h.state = "running"  # its own player is in `ps` then: not another writer
    h.busy_tick([player])
    assert (h.state, h.busy) == ("running", None)
    h.state, h.detail = "ended", "Ended by itself after 20 min."
    h.busy_tick([series])
    assert (h.state, h.detail) == ("ended", "Ended by itself after 20 min.")
    assert h.busy == "an A/B series is running (one input writer at a time)"


def test_a_run_plays_in_assist_or_bot_and_only_the_run_does() -> None:
    """Batt 2026-11-18 ("with BOT it must run too"; ADR-0020 Amendment 2026-11-18): the run the
    helper starts may send in ASSIST or BOT (ro_agent reads it), never HUMAN; the helper's own
    environment, and so every other script of ours, keeps ASSIST alone."""
    import inspect

    import ro_agent

    assert fr.RUN_MODES_ENV == ro_agent.MODES_ENV
    assert ro_agent.input_modes(fr.RUN_INPUT_MODES) == ("ASSIST", "BOT")
    src = inspect.getsource(fr.Helper.start_project)
    assert "RUN_MODES_ENV: RUN_INPUT_MODES" in src and "env=env" in src


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
    assert "# the NORMAL end" in src[i : i + 400] and "return RUN_END" in src[i : i + 400]
    assert fr.STOP_GRACE_S >= 30  # a tick is 0.2 s; a strike or loot step can take seconds


def test_a_bad_setting_block_or_a_clash_refuses_before_anything_starts() -> None:
    for node_vars, word in (
        ({"knife_hp_min": 0.95}, "is not from 20 % to 90 %"),
        ({"knife_swap": "yes"}, "is not on or off"),
        ({"hud_fast": 0.5, "BOX_EVERY_S": 0.5}, "faster than the detector"),
    ):
        vals, _src, _ks, why = fr.project_values(_project(node_vars, None), "xmas_dun02", None)
        assert why is not None and why.startswith("refused before any input") and word in why
        assert word in why, (node_vars, why)
    _, _, _, why = fr.project_values(_project({}, None), "xmas_dun02",
                                     {**fr.FLOWS["xmas_dun02_rogue"].defaults,
                                      "dagger_key": "F4"})  # fmt: skip
    assert "both on F4" in str(why)


# --- matpilot's player test 2026-11-13: "while she plays, the page tells me nothing"; "the end is
# written for a developer" ------------------------------------------------------------------------
def test_the_live_line_follows_the_runs_own_events(tmp_path: Path) -> None:
    ev = [{"t_ns": 1_000_000_000, "kind": "run_start"},
          {"t_ns": 2_000_000_000, "kind": "hp_read", "pct": 97, "pos": [7, 21]},
          {"t_ns": 3_000_000_000, "kind": "press", "what": "opener", "why": "ready"},
          {"t_ns": 4_000_000_000, "kind": "strike"},
          {"t_ns": 5_000_000_000, "kind": "press", "what": "equip", "why": "popup"},
          {"t_ns": 6_000_000_000, "kind": "kill"},
          {"t_ns": 7_000_000_000, "kind": "hp_read", "pct": 88, "pos": [8, 22]},
          {"t_ns": 8_000_000_000, "kind": "loot_step"},
          {"t_ns": 9_000_000_000, "kind": "loot_click"}]  # fmt: skip
    f = tmp_path / "events.jsonl"
    f.write_text("".join(json.dumps(e) + "\n" for e in ev[:5]) + '{"t_ns": 5')  # a half line
    lv = fr.Live()
    off = fr.feed_new(lv, f, 0)
    assert lv.knife == 1 and lv.steals == 1 and lv.kills == 0
    assert lv.doing == "the fighting weapon back on"
    with open(f, "a") as fh:
        fh.write('500000000, "kind": "hp_read"}\n' + "".join(json.dumps(e) + "\n" for e in ev[5:]))
    fr.feed_new(lv, f, off)
    s = lv.summary()
    assert (s["kills"], s["loot_steps"], s["pickups"], s["hp"], s["hp_low"]) == (1, 1, 1, 88, 88)
    assert s["block"] == "loot" and s["doing"] == "picking up" and s["elapsed_s"] == 8
    assert s["pos"] == [8, 22]
    # every block it may highlight is a block of the runner's outline (scripts/runner_flow_export)
    import runner_flow_export as rfe

    ids: set[str] = set()

    def walk(n: dict[str, Any]) -> None:
        ids.add(n["id"])
        for c in n.get("body", []):
            walk(c)
        for b in n.get("branches", []):
            for c in b["body"]:
                walk(c)

    for st in rfe.build()["stacks"]:
        walk(st)
    for b in {*fr.EVENT_BLOCK.values(), *fr.PRESS_BLOCK.values()}:
        assert b in ids, b


def test_the_end_in_a_players_words() -> None:
    lv = fr.Live()
    for e in ({"t_ns": 0, "kind": "run_start"}, {"t_ns": 600_000_000_000, "kind": "kill"},
              {"t_ns": 600_000_000_001, "kind": "run_end", "reason": "stopped"},
              {"t_ns": 600_000_000_002, "kind": "player_end", "home": True, "dead": False,
               "respawned": False}):  # fmt: skip
        lv.feed(e)
    w = fr.end_words(lv, True, 0)
    assert w.startswith("Stopped by you after 10 min. She flew home on a Butterfly Wing.")
    assert "1 kills" in w or "1 kill" in w
    lv.feed({"kind": "player_end", "home": False, "dead": True, "respawned": True})
    assert "She respawned at the save point." in fr.end_words(lv, False, 0)
    # the log a person reads: no server path, no raw JSON
    assert fr.player_lines(["/dev/shm/x/end.png", '{"sid": "x"}', "refused: the chat"]) == [
        "refused: the chat"]  # fmt: skip


# --- dungeon@9.45 (Batt 2026-11-13 "do it"): the start checklist ticked from the game screen; and
# the flow's keys (Batt: every hotbar key from a FUNCTION of the flow) over the settings -----------
KEYS = {"heal_key": "F2", "fly_key": "F3", "home_key": "F6", "knife_key": "F7", "dagger_key": "F9"}
VALS = {f.name: f.default for f in fc.FIELDS if f.block}  # a check's settings: every block's
CHECK = {"id": "a1b2c3d4e5", "action": "check", "flow": "project", "node": "xmas_dun02",
         "keys": KEYS, "vals": VALS}  # fmt: skip


def test_the_check_runs_the_starts_own_argv_read_only() -> None:
    f = fr.FLOWS["xmas_dun02_rogue"]
    vals = fc.with_keys(dict(f.defaults), KEYS)
    run, check = fr.command(f, "flowrun-x", None, vals), fr.check_command(f, vals)
    assert run[8] == "run" and check[8] == "check" and run[:8] == check[:8]

    def settings(a: list[str]) -> list[str]:  # the argv but the label's value
        i = a.index("--label")
        return a[9:i] + a[i + 2 :]

    assert settings(run) == settings(check) and "flowrun-x" not in check
    assert check[check.index("--fly-key") + 1] == "F3" and "--stop-file" not in check
    assert fr.CHECK_MARK == dh.CHECK_MARK and fr.CHECK_TIMEOUT_S <= 30
    with pytest.raises(ValueError, match="not a runner command"):
        fr.command(f, "x", sub="clear-bag")


def test_a_check_carries_the_projects_five_keys_and_settings_and_nothing_else() -> None:
    got = fr.parse_request(json.dumps(CHECK))
    assert isinstance(got, dict) and got["keys"] == KEYS and got["vals"] == VALS
    for keys, word in (({**KEYS, "steal_key": "F1"}, "only heal_key"),
                       ({k: v for k, v in KEYS.items() if k != "home_key"}, "lack home_key"),
                       ({**KEYS, "fly_key": "F10"}, "not a row-1 hotbar key"),
                       ({**KEYS, "fly_key": 8}, "not a row-1 hotbar key"),
                       (["F1"], "must be an object")):  # fmt: skip
        assert word in str(fr.parse_request(json.dumps({**CHECK, "keys": keys}))), keys
    assert "is not a whole number" in str(fr.parse_request(json.dumps(
        {**CHECK, "vals": {**VALS, "minutes": 1.5}})))  # fmt: skip
    stop = {"id": "a1b2c3d4e5", "action": "stop", "keys": KEYS}
    assert "not stop" in str(fr.parse_request(json.dumps(stop)))
    assert "unknown flow" in str(fr.parse_request(json.dumps({**CHECK, "flow": "x"})))


def test_the_flows_keys_go_over_the_settings_for_that_run_only() -> None:
    f = fr.FLOWS["xmas_dun02_rogue"]
    vals, src, keys_src, why = fr.values_of({**f.defaults, "fly_key": "F7"}, {}, KEYS)
    assert why is None and keys_src == "the flow's functions"
    assert {k: vals[k] for k in KEYS} == KEYS and src["fly_key"] == "flow"
    vals, src, keys_src, why = fr.values_of({**f.defaults, "fly_key": "F7"}, {}, None)
    assert vals["fly_key"] == "F7" and keys_src == "the settings"
    # two on one key: refused before any input, in the clash rule's own words
    _, _, _, why = fr.values_of(dict(f.defaults), {}, {**KEYS, "dagger_key": "F7"})
    clash = fc.clash({**f.defaults, **KEYS, "dagger_key": "F7"})
    assert why == f"refused before any input: {clash}"
    assert "both on F7" in str(why)


class FakeProc:
    def __init__(self, argv: list[str], log: Any, rc: int | None, text: str) -> None:
        self.argv, self.pid, self.rc = argv, 424242, rc
        log.write(text.encode())

    def poll(self) -> int | None:
        return self.rc

    def wait(self, timeout: float | None = None) -> int:
        return self.rc or 0


def _helper(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, rc: int | None,
            text: str) -> tuple[Any, list[Any]]:  # fmt: skip
    made: list[Any] = []

    def popen(argv: list[str], **kw: Any) -> FakeProc:
        made.append(FakeProc(argv, kw["stdout"], rc, text))
        return made[-1]

    monkeypatch.setattr(fr, "SCRATCH", tmp_path / "scratch")
    # SERVE_LOG was built from the REAL scratch at import: unpatched, detect_up unlinked the running
    # guard's own step log (2026-11-20 12:4x: the 1080 training's, while these tests ran)
    monkeypatch.setattr(fr, "SERVE_LOG", tmp_path / "scratch" / fr.SERVE_LOG.name)
    monkeypatch.setattr(fr, "writer_busy", lambda _lines: None)
    import types

    ps = types.SimpleNamespace(stdout="", returncode=0)  # `ps -eo args`: writer_busy is faked
    monkeypatch.setattr(fr.subprocess, "run", lambda *a, **k: ps)
    monkeypatch.setattr(fr.subprocess, "Popen", popen)
    return fr.Helper(tmp_path), made


def test_a_check_runs_and_its_result_goes_into_the_status(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    items = [
        {"id": "wings", "ok": True, "words": "12", "value": "12 Fly Wings on F3"},
        {"id": "chat", "ok": False, "words": "the chat input is open", "value": "open"},
    ]
    line = fr.CHECK_MARK + json.dumps({"items": items, "ok": False, "refuses": True,
                                       "used": {"fly_key": "F3"}})  # fmt: skip
    h, made = _helper(tmp_path, monkeypatch, 0, f"some uv line\n{line}\n")
    req = fr.parse_request(json.dumps({**CHECK, "vals": {**VALS, "knife_hp_min": 0.6}}))
    assert isinstance(req, dict)
    h.handle(req)
    assert len(made) == 1 and made[0].argv[8] == "check"
    assert made[0].argv[made[0].argv.index("--heal-key") + 1] == "F2"  # the flow's keys
    # the project's settings (its blocks, as the backend computed them): its 60 % Knife floor
    assert made[0].argv[made[0].argv.index("--knife-hp-min") + 1] == "0.60"
    assert h.check is not None and h.check["state"] == "checking" and h.state == "idle"
    h.tick()
    st = json.loads((tmp_path / "status.json").read_text())
    ck = st["check"]
    assert ck["state"] == "done" and ck["ok"] is False and ck["refuses"] is True
    # Batt 2026-11-19: the hotbar lines warn, never refuse (fr.hotbar_warnings)
    assert ck["items"] == fr.hotbar_warnings(items) and ck["flow"] == "project" and "T" in ck["at"]
    assert ck["keys_src"] == "the flow's functions" and ck["keys"] == KEYS
    assert ck["used"] == {"fly_key": "F3"} and ck["detail"] == "1 of 2 lines fail"
    assert st["state"] == "idle" and h.runner is None  # a check is no run
    runs = [json.loads(x) for x in (tmp_path / "runs.jsonl").read_text().splitlines()]
    assert runs[0]["event"] == "check" and runs[0]["keys"] == KEYS
    assert runs[-1]["event"] == "check_end"


def test_a_check_is_refused_while_a_run_goes_and_is_time_boxed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    h, made = _helper(tmp_path, monkeypatch, None, "")
    for state in ("starting", "running", "stopping"):
        h.state = state
        h.handle(dict(CHECK))
        assert made == [] and h.check is None and "checked before a run" in h.detail
    h.state = "idle"
    monkeypatch.setattr(fr, "writer_busy", lambda _lines: "the night chain is running")
    h.handle(dict(CHECK))
    assert made == [] and h.check is not None and h.check["state"] == "refused"
    assert "night chain" in h.check["detail"]
    # a check that does not end in CHECK_TIMEOUT_S: its process group ends
    monkeypatch.setattr(fr, "writer_busy", lambda _lines: None)
    killed: list[tuple[int, int]] = []
    monkeypatch.setattr(fr.os, "killpg", lambda pid, sig: killed.append((pid, sig)))
    h.handle(dict(CHECK))
    assert len(made) == 1 and h.check["state"] == "checking"
    h.handle({**CHECK, "id": "b1b2c3d4e5"})
    assert len(made) == 1  # one at a time
    h.check_t -= fr.CHECK_TIMEOUT_S + 1
    h.tick()
    assert h.check["state"] == "timeout" and h.check_proc is None and killed[0][0] == 424242
    assert "did not finish" in h.check["detail"]


def test_run_ends_a_running_check(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    h, made = _helper(tmp_path, monkeypatch, None, "")
    killed: list[int] = []
    monkeypatch.setattr(fr.os, "killpg", lambda pid, sig: killed.append(pid))
    h.handle(dict(CHECK))
    # a project start with no checked file refuses before any input (and the check ended first)
    h.handle({"id": "b1b2c3d4e5", "action": "start", "flow": "project", "node": "xmas_dun02",
              "project_hash": "a" * 64, "max_s": 7200, "keys": KEYS})  # fmt: skip
    assert killed == [424242] and h.check is not None and h.check["state"] == "cancelled"
    assert h.state == "refused" and "not there" in h.detail and len(made) == 1


def test_the_checks_output_is_its_result_or_the_runners_refusal() -> None:
    items = [{"id": "cell", "ok": None, "words": "w", "value": None}]
    got = fr.parse_check_output("x\n" + fr.CHECK_MARK + json.dumps({"items": items, "ok": None}))
    assert got["state"] == "done" and got["detail"] == "1 of 1 lines not read"
    ok = fr.parse_check_output(fr.CHECK_MARK + json.dumps({"items": [{"id": "a", "ok": True}],
                                                           "ok": True}))  # fmt: skip
    assert ok["detail"] == "every line passes" and ok["ok"] is True
    why = "dungeon@9.42 refused: F4 is set for --steal-opener and equip: each needs its own key"
    got = fr.parse_check_output(f"/home/bot/x.py:1: a path\n{why}\n")
    assert got == {"state": "refused", "items": [], "ok": False, "refuses": True, "used": {},
                   "detail": why}  # fmt: skip
    crash = fr.parse_check_output("Traceback (most recent call last):\nKeyError: 'x'\n")
    assert crash["state"] == "failed" and crash["ok"] is None and crash["detail"] == "KeyError: 'x'"
    assert fr.parse_check_output("")["detail"] == "the check ended without a result"


def test_the_detect_server_follows_the_host_profile(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """ADR-0022 Amendment 2026-11-17: the Run helper starts the profile's detect backend (it was
    always OpenVINO); no GPU (dedicated-cpu) or no model of the server's -> the CPU detector alone,
    the run goes on; nothing is started."""
    import types

    import host_profile as hp

    h, made = _helper(tmp_path, monkeypatch, None, "")
    h.run_dir = tmp_path / "run"
    h.run_dir.mkdir()
    h.cap_s = 600.0
    calls: list[list[str]] = []

    def run(argv: list[str], **kw: Any) -> Any:
        calls.append(list(argv))
        if "serve-cmd" in argv:
            return types.SimpleNamespace(stdout="", stderr="no model", returncode=rc["serve"])
        return types.SimpleNamespace(stdout="true", stderr="", returncode=0)

    rc = {"serve": 3}
    monkeypatch.setattr(fr.subprocess, "run", run)
    monkeypatch.setattr(hp, "current", lambda: hp.PROFILES["dedicated-cpu"])
    assert h.detect_up() is True and calls == [] and made == []
    # ADR-0022 Amendment 2026-11-18: NVIDIA serves the deployed ONNX too (onnxruntime), never .pt;
    # Amendment 2026-11-18b: AMD on onnxruntime's WebGPU provider, the profile naming the device
    for name, backend, device in (("dedicated-intel", "openvino", None),
                                  ("dedicated-nvidia", "onnxruntime", None),
                                  ("shared-nvidia", "onnxruntime", None),
                                  ("dedicated-amd", "onnxruntime", "webgpu")):  # fmt: skip
        calls.clear()
        monkeypatch.setattr(hp, "current", lambda n=name: hp.PROFILES[n])
        assert h.detect_up() is True and made == []  # rc 3: no model -> CPU only
        serve = next(c for c in calls if "serve-cmd" in c)
        assert serve[serve.index("--backend") + 1] == backend, name
        got = serve[serve.index("--device") + 1] if "--device" in serve else None
        assert got == device, name  # the backend's default device unless the profile names one
        assert not any("worker:vision@60" in " ".join(c) for c in calls)  # no worker started


def test_a_detect_server_that_stops_before_it_listens_leaves_the_cpu_detector(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """ADR-0022 Amendment 2026-11-18: the server's step ended without its listening line (its GPU
    provider did not load: onnxruntime refuses its own CPU fallback) -> the run goes on with the
    CPU detector, noted with the log's tail; never a 120 s wait and a failed run."""
    import types

    import host_profile as hp

    why = "onnxruntime runs ['CPUExecutionProvider'], not CUDAExecutionProvider: ..."
    h, made = _helper(tmp_path, monkeypatch, 1, f"{why}\n")
    h.run_dir = tmp_path / "run"
    h.run_dir.mkdir()
    h.cap_s = 600.0

    def run(argv: list[str], **kw: Any) -> Any:
        out = (
            "python3 scripts/guarded_build.py 'execdev:vision@750=...'"
            if "serve-cmd" in argv
            else "true"
        )
        return types.SimpleNamespace(stdout=out, stderr="", returncode=0)

    monkeypatch.setattr(fr.subprocess, "run", run)
    monkeypatch.setattr(fr.time, "sleep", lambda _s: None)
    monkeypatch.setattr(hp, "current", lambda: hp.PROFILES["dedicated-nvidia"])
    assert h.detect_up() is True and len(made) == 1 and h.server is None
    notes = [json.loads(x) for x in (tmp_path / "runs.jsonl").read_text().splitlines()]
    assert notes[-1]["event"] == "detect_cpu_only" and notes[-1]["why"] == "server_exit"
    assert why in " ".join(notes[-1]["tail"])


# --- the Run's log on the page (Batt 2026-11-18: "log the status, the checklist and the errors";
# "if a user presses Alt+Tab, only pause") ------------------------------------------------------
def test_a_run_pauses_while_the_game_is_off_the_screen() -> None:
    import ro_agent

    assert fr.RUN_PAUSE_ENV == ro_agent.AWAY_ENV
    src = (Path(fr.__file__)).read_text()
    assert 'RUN_PAUSE_ENV: "1"' in src  # in the Run's own environment, beside its modes


def test_the_run_log_gives_the_runs_own_check_and_its_pauses_as_it_grows() -> None:
    rl = fr.RunLog()
    items = [{"id": "identity", "ok": False, "words": "the name plate is not hers"},
             {"id": "chat", "ok": True, "words": "the chat input is closed"}]  # fmt: skip
    rl.feed(
        "[19:25:24] RUN flowplay-1: the project x\n"
        + fr.CHECK_MARK
        + json.dumps({"items": items, "ok": False})
        + "\n[19:25:30] PAUSED: the Windows taskbar sh"
    )
    assert rl.check is not None and rl.check["detail"] == "1 of 2 lines fail"
    assert rl.pause() is None  # the PAUSED line is not finished yet
    rl.feed("ows: the game is not in front. The bot waits and presses nothing; it goes on\n")
    assert rl.pause() == {"paused": True, "since": "19:25:30", "count": 1, "paused_s": 0.0,
                          "why": "the Windows taskbar shows: the game is not in front"}  # fmt: skip
    rl.feed("[19:25:42] RESUMED after 12.5 s: the game is back on the screen; the bot goes on.\n")
    p = rl.pause()
    assert p is not None and p["paused"] is False and p["paused_s"] == 12.5 and p["count"] == 1
    assert p["since"] is None and p["why"] is None


def test_the_pause_shows_on_the_live_line() -> None:
    live = fr.Live()
    live.feed({"kind": "pause", "why": "the Windows taskbar shows", "t_ns": 5})
    assert live.summary()["doing"].startswith("PAUSED")
    live.feed({"kind": "resume", "after_s": 3.0, "t_ns": 6})
    assert "playing on" in live.summary()["doing"]


def test_a_refusal_s_detail_is_whole_and_the_log_tail_is_longer(tmp_path: Path) -> None:
    log = tmp_path / "run.log"
    why = "flow_play refused before any input: the start check: " + "x" * 700
    log.write_text("\n".join([f"line {i}" for i in range(fr.LOG_TAIL_N + 20)] + [why]) + "\n")
    assert fr.tail(log, 3, 4000)[-1] == why  # the helper's end detail: not cut at 240
    assert len(fr.tail(log, fr.LOG_TAIL_N, fr.LOG_LINE_MAX)) == fr.LOG_TAIL_N


def test_no_start_picture_is_kept_or_offered(tmp_path: Path) -> None:
    """Batt 2026-11-18 ~22:3x: "store no pictures at all, known character or not" (a frame can
    show other people's chat, a password typed in the game)."""
    h = fr.Helper(tmp_path)
    assert "start_pictures" not in h.status() and not hasattr(h, "copy_start_pictures")
    assert not hasattr(fr, "START_PICTURES")


def test_a_check_first_finds_the_game_s_windows_and_a_failure_is_only_a_note(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """4f (teaching-prerun.md): `ro_agent.py find-panels` before the check, so a client whose
    windows sit elsewhere is read through the virtual client; at most PANELS_TIMEOUT_S."""
    import subprocess
    import types

    seen: list[list[str]] = []

    def run(argv: list[str], **kw: Any) -> Any:
        seen.append(argv)
        if argv[-1] == "find-panels":
            assert kw["timeout"] == fr.PANELS_TIMEOUT_S
            return types.SimpleNamespace(returncode=0, stdout='{"found": {}}\nBasic Info found\n')
        return types.SimpleNamespace(stdout="", returncode=0)

    h, made = _helper(tmp_path, monkeypatch, 0, "")
    monkeypatch.setattr(fr.subprocess, "run", run)
    req = fr.parse_request(json.dumps({**CHECK, "vals": VALS}))
    assert isinstance(req, dict)
    h.handle(req)
    assert [a[-1] for a in seen if a[-1] == "find-panels"] == ["find-panels"]
    assert made and made[0].argv[8] == "check"  # the check still runs
    runs = [json.loads(x) for x in (tmp_path / "runs.jsonl").read_text().splitlines()]
    assert [r["event"] for r in runs][:2] == ["check", "find_panels"]
    assert runs[1]["lines"] == ["Basic Info found"] and runs[1]["rc"] == 0

    def slow(argv: list[str], **kw: Any) -> Any:
        raise subprocess.TimeoutExpired(argv, kw.get("timeout", 0))

    monkeypatch.setattr(fr.subprocess, "run", slow)
    h.find_panels({})
    last = json.loads((tmp_path / "runs.jsonl").read_text().splitlines()[-1])
    assert last == {"t": last["t"], "event": "find_panels", "rc": None, "why": "TimeoutExpired"}


# --- Batt 2026-11-19: the Logs tab -- what she does, in words ----------------------------------
def test_the_story_says_what_she_does_in_words() -> None:
    lv = fr.Live()
    t0 = 1_000_000_000_000
    feed = [
        {"kind": "run_start", "t_ns": t0},
        {"kind": "hp_read", "pct": 98, "pos": [201, 21], "t_ns": t0 + 1},
        {"kind": "walk", "to": [199, 28], "why": "search", "clicked": True, "t_ns": t0 + 2 * 10**9},
        {"kind": "hp_read", "pct": 95, "t_ns": t0 + 3 * 10**9},  # under HP_STEP: no line
        {"kind": "recipe", "species": "Myst Case", "knife": True, "t_ns": t0 + 4 * 10**9},
        {"kind": "strike", "end": "damage", "t_ns": t0 + 5 * 10**9},
        {"kind": "kill", "by": "exp_line", "t_ns": t0 + 6 * 10**9},
        {"kind": "hp_read", "pct": 70, "t_ns": t0 + 7 * 10**9},
        {"kind": "press", "what": "potion", "key": "F1", "t_ns": t0 + 8 * 10**9},
        {"kind": "retry", "n": 1, "of": 3, "error": "FrozenStream", "t_ns": t0 + 9 * 10**9},
        {"kind": "box_watch", "t_ns": t0 + 10 * 10**9},  # bookkeeping: no line
    ]
    for e in feed:
        lv.feed(e)
    words = [x["words"] for x in lv.story]
    assert words == ["HP 98 %", "walks to (199, 28), searching for monsters",
                     "a Myst Case: the Knife swap first", "strikes: a hit", "a kill (exp_line)",
                     "HP 70 %", "presses F1: a potion",
                     "RETRY 1 of 3 after a code error: FrozenStream"]  # fmt: skip
    assert [x["t_s"] for x in lv.story][:3] == [0, 2, 4]
    sm = lv.summary()
    assert sm["retries"] == 1 and sm["story"] == lv.story and sm["doing"].startswith("RETRY 1")
    for i in range(fr.STORY_N + 5):
        lv.feed({"kind": "kill", "t_ns": t0 + i})
    assert len(lv.story) == fr.STORY_N  # the last lines only
    assert fr.event_words({"kind": "walk", "to": [1, 2], "clicked": False}) == (
        "walks to (1, 2) (the click was not sent)")  # fmt: skip
    assert fr.event_words({"kind": "explore"}) == "chooses where to explore next"
    assert fr.event_words({"kind": "explore", "anchor": [6, 124]}).endswith("(near (6, 124))")
    assert fr.LOG_TAIL_N == 300


def test_another_copy_s_run_never_makes_this_copy_busy(tmp_path: Path) -> None:
    """2026-11-19 (ADR-0026: a LIVE copy beside the dev lab): the live helper said "the live block
    player is playing" for the DEV lab's Run, so neither copy could play while the other did. Only
    the processes whose working folder is this copy count (another copy plays its own Windows)."""
    here, other = tmp_path / "poring-lab-live", tmp_path / "poring-lab"
    ps = ("101 /x/.venv/bin/python scripts/flow_play.py play --project p\n"
          "102 /y/.venv/bin/python scripts/flow_play.py play --project q\n"
          "103 /usr/bin/bash\n104 gone\n")  # fmt: skip
    cwds = {"101": str(other), "102": str(here / "scripts"), "103": str(here)}

    def cwd_of(pid: str) -> str:
        if pid not in cwds:
            raise OSError(pid)
        return cwds[pid]

    lines = fr.copy_ps_lines(here, ps, cwd_of)
    assert lines == ["/y/.venv/bin/python scripts/flow_play.py play --project q", "/usr/bin/bash"]
    assert fr.busy_reason(lines) == "the live block player is playing (one input writer at a time)"
    assert fr.busy_reason(fr.copy_ps_lines(here, ps.replace("102 ", "105 "), cwd_of)) is None


def test_a_second_stop_ends_the_run_at_once_skipping_the_bag_count(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Batt 2026-11-20: Stop = "count, then stop"; a SECOND Stop skips the count (SIGINT now)."""
    import types

    h = fr.Helper(tmp_path)
    sent: list[tuple[int, int]] = []
    monkeypatch.setattr(fr.os, "killpg", lambda pid, sig: sent.append((pid, sig)))
    h.runner = types.SimpleNamespace(pid=4242, poll=lambda: None)  # type: ignore[assignment]
    h.stop_file = tmp_path / "STOP"
    h.label = "flowplay-x"
    h.stop("r1")
    assert h.state == "stopping" and h.stop_file.exists() and sent == []
    h.stop("r2")
    assert sent == [(4242, fr.signal.SIGINT)] and "no bag count" in h.detail


# --- Batt 2026-11-20: the monster's name, %, cells as in the HUD; the Run's time or the clock ----
def test_the_story_names_the_monster_as_the_hud_does() -> None:
    seen = {"name": "cookie_xmas", "conf": 0.874, "cells": 3}
    assert fr.unit_words(seen) == "cookie_xmas 87% 3 cells"
    assert fr.unit_words({**seen, "cells": 1}) == "cookie_xmas 87% 1 cell"
    assert fr.unit_words({"name": "cookie_xmas", "conf": None, "cells": None}) == "cookie_xmas"
    assert fr.unit_words(None) is None and fr.unit_words({"conf": 0.5}) is None
    box = [1.0, 2.0, 3.0, 4.0]
    assert fr.event_words({"kind": "box_target", "box": box, "seen": seen}) == (
        "aims at cookie_xmas 87% 3 cells"
    )
    assert fr.event_words({"kind": "box_target", "box": box}) == "aims at a monster on the screen"
    assert fr.event_words(
        {"kind": "engage", "by": "miss_cue", "seen": seen, "spot": [79, 242]}
    ) == ("a fight starts (miss_cue): cookie_xmas 87% 3 cells at (79, 242)")
    assert fr.event_words({"kind": "engage", "by": "box"}) == "a fight starts (box)"
    assert fr.event_words({"kind": "strike", "end": "damage", "of": "cookie_xmas"}) == (
        "strikes cookie_xmas: a hit"
    )
    assert fr.event_words({"kind": "kill", "by": "exp_line", "of": "cookie_xmas"}) == (
        "a kill: cookie_xmas (exp_line)"
    )
    assert fr.event_words({"kind": "kill", "by": "exp_line"}) == "a kill (exp_line)"


def test_each_story_line_carries_the_servers_clock_and_its_zone(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import time

    monkeypatch.setenv("TZ", "Asia/Bangkok")
    time.tzset()
    try:
        # the wall clock = the monotonic one + 1_763_633_946 s: 2025-11-20 10:19:06 UTC
        lv = fr.Live(wall_minus_mono_s=1_763_633_946.0)
        lv.feed({"kind": "run_start", "t_ns": 0})
        lv.feed({"kind": "walk", "t_ns": 105_000_000_000, "to": [91, 210], "why": "search"})
        line = lv.story[-1]
        assert line["t_s"] == 105 and line["at"] == "17:20:51"  # ICT = UTC+7
        assert lv.summary()["tz"] == "UTC+07:00" == fr.server_tz()
        assert fr.Live().clock_at(5) is None  # no clock given: no "at" (the Run's time only)
    finally:
        monkeypatch.delenv("TZ")
        time.tzset()
