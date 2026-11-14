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


def test_a_start_is_a_projects_and_never_carries_arguments() -> None:
    """2026-11-14 (live-blocks.md 12): the runner-only start went with the runner page; a start
    names the checked project (its node and hash) and nothing else -- no argument, no setting."""
    base = {"id": "a1b2c3d4e5", "action": "start", "flow": "project", "node": "xmas_dun02",
            "project_hash": "a" * 64, "max_s": 7200}  # fmt: skip
    assert fr.parse_request(json.dumps(base)) == base
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
    own = {x.name for x in fc.FIELDS if x.flag or x.kind in ("switch", "choice")}
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
    assert lv.knife == 1 and lv.steals == 1 and lv.kills == 0 and lv.doing == "the dagger back on"
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
    assert ck["items"] == items and ck["flow"] == "project" and "T" in ck["at"]
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
