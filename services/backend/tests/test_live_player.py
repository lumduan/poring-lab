"""scripts/flow_play.py, the LIVE BLOCK PLAYER (Batt 2026-11-13, docs/planning/live-blocks.md stage
1; ADR-0020 Amendment E): offline, no game. A FakeIO records every input and scripts the sensor
values on a fake clock; the hunt core's runner is a fake run() that drives the tick hook."""

from __future__ import annotations

import ast
import inspect
import json
import sys
import textwrap
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts"))

import dungeon_hunt as dh  # noqa: E402
import flow_config as fc  # noqa: E402
import flow_play as fp  # noqa: E402
import flow_run as fr  # noqa: E402

from poring_flow import catalogue, editor, live  # noqa: E402
from poring_flow import project as pj  # noqa: E402


# --- a project to play (format 3: login -> character -> field; field's item warp -> home) --------
def lit(v: Any) -> dict[str, Any]:
    return {"kind": "lit", "value": v}


def sense(n: str) -> dict[str, Any]:
    return {"kind": "sense", "sensor": n, "args": {}}


def cmp(op: str, left: Any, right: Any) -> dict[str, Any]:
    return {"kind": "cmp", "op": op, "left": left, "right": right}


def action(
    block: str, concept: str, params: dict[str, Any], timeout: float = 2.0
) -> dict[str, Any]:
    return {"kind": "action", "block": block, "concept": concept, "params": params,
            "timeout_s": timeout, "on_fail": "stop", "outcome_to": None, "note": None}  # fmt: skip


def press(k: str) -> dict[str, Any]:
    return action("press_key", "ui.press_hotkey", {"key": lit(k)})


def wait(s: float) -> dict[str, Any]:  # the view's wait(s): wait_until(False, s)
    return {"kind": "wait_until", "cond": lit(False), "timeout_s": s, "outcome_to": None}


def wait_until(c: Any, s: float) -> dict[str, Any]:
    return {"kind": "wait_until", "cond": c, "timeout_s": s, "outcome_to": None}


def call(p: str) -> dict[str, Any]:
    return {"kind": "call", "proc": p, "args": [], "kwargs": {}}


def forever(body: list[Any]) -> dict[str, Any]:
    return {"kind": "while", "cond": lit(True), "body": body, "max_iter": None, "max_s": None}


def fdef(name: str, body: list[Any], on: Any = None) -> dict[str, Any]:
    return {"name": name, "params": [], "varargs": None, "kwargs": None, "body": body, "on": on}


def tab(name: str, main: Any = None, defs: Any = None) -> dict[str, Any]:
    return {"name": name, "main": main, "defs": defs or [], "vars": {}}


def wing_exit(timeout: float = 30.0) -> dict[str, Any]:
    return {"kind": "take_exit", "exit": {"kind": "item_warp", "proc": "butterfly_wing",
                                          "to_block": "home", "to_entry": "save",
                                          "timeout_s": timeout, "options": [], "item": None,
                                          "npc": None, "warp": None}}  # fmt: skip


HUNT = action("dungeon_hunt", "combat.hunt", {"heal": lit("heal"), "fly": lit("fly_wing"),
                                               "knife_on": lit("knife_on"),
                                               "knife_back": lit("knife_back")}, 600.0)  # fmt: skip
HP_LOW = {"when": cmp("<", sense("hp_percent"), lit(30)), "until": None,
          "rearm": cmp(">", sense("hp_percent"), lit(50)), "priority": "survival", "rank": None,
          "mode": "insert", "escalate": None, "max_insert_fails": 3, "cooldown_s": 0.0,
          "max_per_min": None, "max_fires_per_10min": 10, "max_per_run": None,
          "then": "resume"}  # fmt: skip
KEYS = {
    "heal": "F1",
    "fly_wing": "F8",
    "butterfly_wing": "F9",
    "knife_on": "F4",
    "knife_back": "F5",
}


def project(field_main: list[Any], home_main: list[Any] | None = None) -> dict[str, Any]:
    session = [{"kind": "action", "block": "login", "concept": "session.login",
                "params": {"server": lit("lab-rathena"), "credential": lit("lab_gm")},
                "timeout_s": 60.0, "on_fail": "stop", "outcome_to": None,
                "note": None}]  # fmt: skip
    char = [action("choose_character", "session.select_char", {}, 60.0)]
    return {
        "format": "poring-lab.project", "version": 3, "name": "live_test", "description": "",
        "target": {"client": "kro-20211103-prere", "server": "lab-rathena", "locale": "en",
                   "path": "s2"},
        "max_runtime_s": 600, "where_budget": 12, "stop_when": None, "assumes": [],
        "start": "login",
        "nodes": [
            {"id": "login", "kind": "login", "pos": {"x": 0, "y": 0},
             "tabs": [tab("main", session)]},
            {"id": "character", "kind": "character", "pos": {"x": 0, "y": 100},
             "tabs": [tab("main", char)]},
            {"id": "field", "kind": "map", "pos": {"x": 200, "y": 0},
             "map": {"kind": "map", "map": "xmas_dun02"},
             "entries": [{"name": "here", "at": None, "radius": 2}], "targets": [], "ignore": [],
             "resume_here": True, "tabs": [tab("main", field_main)]},
            {"id": "home", "kind": "map", "pos": {"x": 400, "y": 0},
             "map": {"kind": "map", "map": "geffen"},
             "entries": [{"name": "save", "radius": 2,
                          "at": {"kind": "cell", "map": "geffen", "x": 119, "y": 40}}],
             "targets": [], "ignore": [], "resume_here": True,
             "tabs": [tab("main", home_main or [{"kind": "stop", "reason": "home"}])]},
            {"id": "global", "kind": "global", "pos": {"x": 200, "y": 200}, "tabs": [
                tab("keys", defs=[fdef(k, [press(v)]) for k, v in KEYS.items()]),
                tab("safety", defs=[fdef("hp_low", [call("heal")], on=HP_LOW)])]},
        ],
        "edges": [{"from": "login", "to": "character"},
                  {"from": "character", "to": "field", "entry": "here"}],
    }  # fmt: skip


START = {"hp_percent": 100, "sp_percent": 100, "weight_percent": 10, "is_dead": False,
         "map": "xmas_dun02"}  # fmt: skip


class FakeIO(fp.LiveIO):
    """Every input recorded with its time; the sensors scripted [(t, changes)] on a fake clock; a
    press of F9 (the Butterfly Wing) lands her on ``wing_to`` after 2 s."""

    def __init__(self, script: list[tuple[float, dict[str, Any]]] | None = None,
                 wing_to: str | None = "geffen", stop_at: float | None = None,
                 stop_file: Path | None = None, refuse_tap: bool = False) -> None:  # fmt: skip
        self.now, self.w = 0.0, dict(START)
        self.script = sorted(script or [], key=lambda x: x[0])
        self.out: list[tuple[Any, ...]] = []
        self.agent, self.screen = "AGENT", "SCREEN"
        self.wing_to, self.stop_at, self.stop_file = wing_to, stop_at, stop_file
        self.refuse_tap = refuse_tap

    def clock(self) -> float:
        return self.now

    def sleep(self, s: float) -> None:
        self.now += s
        if self.stop_at is not None and self.now >= self.stop_at and self.stop_file is not None:
            self.stop_file.touch()

    def ns(self) -> int:
        return int(self.now * 1e9)

    def senses(self) -> dict[str, Any]:
        while self.script and self.script[0][0] <= self.now:
            self.w.update(self.script.pop(0)[1])
        return dict(self.w)

    def open(self) -> None:
        self.out.append(("open",))

    def ui_clear(self) -> None:
        self.out.append(("ui_clear",))

    def tap(self, code: str) -> None:
        if self.refuse_tap:
            raise SystemExit("mux refused 1/1 (['client_not_foreground']): stopping")
        self.out.append(("tap", code))
        self.now += 0.1
        if code == "F9" and self.wing_to is not None:
            self.script = sorted([*self.script, (self.now + 2.0, {"map": self.wing_to})],
                                 key=lambda x: x[0])  # fmt: skip

    def release(self) -> None:
        self.out.append(("release",))


def ok_check(_p: Any, _io: Any) -> dict[str, Any]:
    return {"items": [{"id": "cell", "ok": True, "words": "the minimap is xmas_dun02's"}],
            "ok": True}  # fmt: skip


def prep(tmp_path: Path, field_main: list[Any], **kw: Any) -> fp.Prepared:
    got = fp.prepare(json.dumps(project(field_main, **kw)), "field", 3600, config_dir=tmp_path)
    assert isinstance(got, fp.Prepared), got
    return got


def events(demo: Path) -> list[dict[str, Any]]:
    (d,) = list(demo.iterdir())
    return [json.loads(x) for x in (d / "events.jsonl").read_text().splitlines()]


def taps(io_: FakeIO) -> list[str]:
    return [o[1] for o in io_.out if o[0] == "tap"]


# --- the set is ONE place ------------------------------------------------------------------------
def test_the_live_set_is_one_place_and_the_catalogue_serves_it() -> None:
    cat = catalogue.catalogue()
    assert live.live_blocks() == ["assert_save_point", "dungeon_hunt", "press_key"]
    assert live.live_sensors() == ["current_map", "hp_percent", "is_dead", "map_load_seen",
                                   "sp_percent", "weight_percent"]  # fmt: skip
    doc = editor.catalogue_doc()
    assert doc["live"]["blocks"] == live.live_blocks() and doc["live"]["stage"] == 1
    assert doc["blocks"]["press_key"]["spec"]["live"] is True
    assert doc["blocks"]["walk_to"]["spec"]["live"] is False
    assert doc["sensors"]["hp_percent"]["spec"]["live"] is True
    assert doc["live"]["later"]["walk_to"] == "stage 4" and "press_key" not in doc["live"]["later"]
    assert set(doc["live"]["later"]) == {*cat.blocks, *cat.sensors} - {
        *live.live_blocks(),
        *live.live_sensors(),
    }
    # one version, three places; the runner's own version is unchanged
    assert dh.LIVE_BLOCKS_VERSION == live.VERSION == fp.VERSION == "9.48"
    assert dh.VERSION == "dungeon@8.7"


def test_a_block_without_a_live_binding_refuses_before_any_input(tmp_path: Path) -> None:
    walk = action("walk_to", "nav.walk_to", {"cell": lit({"kind": "cell", "map": "xmas_dun02",
                                                          "x": 10, "y": 10})}, 120.0)  # fmt: skip
    got = fp.prepare(json.dumps(project([press("F2"), walk, wing_exit()])), "field", 3600,
                     config_dir=tmp_path)  # fmt: skip
    assert isinstance(got, str) and "refused before any input" in got
    assert "walk_to cannot play live yet (stage 4) at field/main/main.1" in got
    # the ready-made sample: every block it cannot play is named, with its node path
    sample = (ROOT / "services/frontend/src/lib/flow/fixtures/project_sample.json").read_text()
    c = pj.compile_project(pj.from_json(sample))
    assert c.flow is not None
    named = {(c.where(b.path).path, b.words) for b in live.problems(c.flow)}
    assert ("town/main/main.1", "walk_to cannot play live yet (stage 4)") in named
    assert ("town/main/main.2", "npc_warp cannot play live yet (a later stage)") in named
    # the ready-made xmas_dun02 project plays live (its hunt core, its keys, its wing home)
    xmas = (ROOT / "services/frontend/src/lib/flow/fixtures/project_xmas_dun02.json").read_text()
    c2 = pj.compile_project(pj.from_json(xmas))
    assert c2.flow is not None and live.problems(c2.flow) == []
    # and nothing about it opened an input path: prepare() is pure (no screen, no agent)
    assert not list(tmp_path.glob("*"))


def test_a_node_that_is_no_map_node_or_a_time_box_above_the_maximum_refuses(
    tmp_path: Path,
) -> None:
    text = json.dumps(project([press("F2")]))
    assert "no map node" in str(fp.prepare(text, "login", 3600, config_dir=tmp_path))
    assert "above the configured maximum 300" in str(fp.prepare(text, "field", 300,
                                                                config_dir=tmp_path))  # fmt: skip
    assert "no configured maximum" in str(fp.prepare(text, "field", None, config_dir=tmp_path))
    h = fp.prepare(text, "field", 3600, config_dir=tmp_path)
    assert isinstance(h, fp.Prepared)
    assert "not the checked" in str(fp.prepare(text, "field", 3600, config_dir=tmp_path,
                                               want_hash="0" * 64))  # fmt: skip


# --- it plays exactly the input expected ---------------------------------------------------------
def test_press_wait_an_insert_event_and_the_item_warp_play_exactly_this(tmp_path: Path) -> None:
    p = prep(
        tmp_path,
        [
            press("F2"),
            wait(1.0),
            wait_until(cmp(">", sense("hp_percent"), lit(90)), 10.0),
            wing_exit(),
        ],
    )
    io_ = FakeIO([(0.5, {"hp_percent": 25}), (3.0, {"hp_percent": 95})])
    demo = tmp_path / "demo"
    demo.mkdir()
    assert fp.play(p, io_, label="t1", stop_file=None, demo=demo, checker=ok_check) == 0
    # the input path opens after the start check; the UI gate; F2; hp_low's heal (an INSERT at a
    # safe point inside the wait); the Butterfly Wing (the exit's function); the end's release
    assert io_.out == [("open",), ("ui_clear",), ("tap", "F2"), ("tap", "F1"), ("tap", "F9"),
                       ("release",)]  # fmt: skip
    ev = events(demo)
    kinds = [e["kind"] for e in ev]
    assert kinds[0] == "run_start" and kinds[-1] == "run_end"
    assert [e["key"] for e in ev if e["kind"] == "key"] == ["F2", "F1", "F9"]
    nodes = [e["node"] for e in ev if e["kind"] == "block"]
    assert nodes[:3] == ["field/main/main.0", "field/main/main.1", "global/safety/hp_low.0"]
    assert "global/keys/butterfly_wing.0" in nodes and nodes[-1] == "home/main/main.0"
    fired = [e for e in ev if e["kind"] == "event"]
    assert [(e["event"], e["mode"], e["node"]) for e in fired] == [
        ("hp_low", "insert", "global/safety/hp_low")
    ]
    arrive = next(e for e in ev if e["kind"] == "map_node")
    assert arrive == {**arrive, "node": "home", "how": "exit", "map": "geffen"}
    end = ev[-1]
    assert end["reason"] == "home" and end["keys"] == ["F2", "F1", "F9"]
    assert (
        end["words"].startswith("The flow stopped after 0 min.") and 'stop "home"' in end["words"]
    )
    # the Run helper's Live tracker reads the same file: the node, the keys, the event, the words
    lv = fr.Live()
    fr.feed_new(lv, next(demo.iterdir()) / "events.jsonl", 0)
    s = lv.summary()
    assert s["keys"] == 3 and s["fired"] == 1 and s["node"] == "home/main/main.0"
    assert s["end"]["words"] == end["words"] and s["hp"] == 95


def test_the_exit_must_arrive_on_the_target_nodes_map(tmp_path: Path) -> None:
    p = prep(tmp_path, [wing_exit(timeout=5.0)])
    io_ = FakeIO(wing_to=None)  # the wing did nothing: the minimap keeps reading xmas_dun02
    demo = tmp_path / "demo"
    demo.mkdir()
    fp.play(p, io_, label="t2", stop_file=None, demo=demo, checker=ok_check)
    assert taps(io_) == ["F9"] and io_.out[-1] == ("release",)
    end = events(demo)[-1]
    assert end["reason"] == "exit_not_arrived" and "did not arrive" in end["words"]


def test_stop_ends_the_running_block_releases_and_ends(tmp_path: Path) -> None:
    stop = tmp_path / "STOP"
    p = prep(tmp_path, [forever([wait(1.0)])])
    io_ = FakeIO(stop_at=2.5, stop_file=stop)
    demo = tmp_path / "demo"
    demo.mkdir()
    fp.play(p, io_, label="t3", stop_file=stop, demo=demo, checker=ok_check)
    assert taps(io_) == [] and io_.out[-1] == ("release",)
    end = events(demo)[-1]
    assert end["reason"] == "stopped" and end["words"].startswith("Stopped by you")
    assert 2.5 <= io_.now < 3.0  # at the next tick, not at the loop's end


def test_the_time_box_is_the_projects_capped_by_the_settings_maximum(tmp_path: Path) -> None:
    text = json.dumps(project([forever([wait(1.0)])]))
    p = fp.prepare(text, "field", 3600, config_dir=tmp_path)
    assert isinstance(p, fp.Prepared) and p.cap_s == 600.0  # the project's max_runtime_s
    io_ = FakeIO()
    demo = tmp_path / "demo"
    demo.mkdir()
    fp.play(p, io_, label="t4", stop_file=None, demo=demo, checker=ok_check)
    assert events(demo)[-1]["reason"] == "max_runtime" and 600.0 <= io_.now < 600.5


def test_the_built_in_safety_events_play_as_the_safe_end(tmp_path: Path) -> None:
    for script, key in (([(1.0, {"is_dead": True})], "dead"),
                        ([(1.0, {"map": "prontera"})], "unexpected_map"),
                        ([(1.0, {"hp_percent": 10})], "hp_critical")):  # fmt: skip
        d = tmp_path / key
        d.mkdir()
        p = prep(d, [forever([wait(1.0)])])
        io_ = FakeIO(script)
        fp.play(p, io_, label=key, stop_file=None, demo=d, checker=ok_check)
        end = events(d)[-1]
        assert end["reason"] == key, (key, end)
        assert end["words"] and ("stage 2" in end["words"] or "a person looks" in end["words"])
        assert ("release",) in io_.out and io_.out[-1] == ("release",)
        assert "tap" not in {o[0] for o in io_.out} or key == "hp_critical"


def test_a_refused_input_ends_the_run_and_releases(tmp_path: Path) -> None:
    p = prep(tmp_path, [press("F2"), wait(5.0)])
    io_ = FakeIO(refuse_tap=True)
    demo = tmp_path / "demo"
    demo.mkdir()
    fp.play(p, io_, label="t5", stop_file=None, demo=demo, checker=ok_check)
    end = events(demo)[-1]
    assert end["reason"] == "input_refused" and "client_not_foreground" in end["words"]
    assert io_.out[-1] == ("release",)


def test_the_start_check_refuses_before_any_input(tmp_path: Path) -> None:
    p = prep(tmp_path, [press("F2")])
    for got in ({"items": [{"id": "cell", "ok": None, "words": "cannot tell"}]},
                {"items": [{"id": "cell", "ok": True, "words": "x"},
                           {"id": "chat", "ok": False, "words": "the chat input is open"}]},
                {"items": [], "detail": "refused: dungeon@9.46"}):  # fmt: skip
        io_ = FakeIO()
        demo = tmp_path / "demo"
        assert fp.play(p, io_, label="t6", stop_file=None, demo=demo,
                       checker=lambda _p, _i, g=got: g) == 2  # fmt: skip
        assert io_.out == [] and not demo.exists()  # no input path was opened, no session
    assert fp.check_refusal({"items": [{"id": "cell", "ok": True}]}) is None
    # a line the runner does not refuse on (the Butterfly Wings' count) never refuses
    ok = {"items": [{"id": "cell", "ok": True}, {"id": "home", "ok": False, "refuses": False}]}
    assert fp.check_refusal(ok) is None


# --- the hunt core: dungeon_hunt IN-PROCESS, the same Agent, its tick hook -----------------------
class FakeRunner:
    """dungeon_hunt.run(a, hook=..., session=...) as the player calls it: drives the tick hook,
    sends the runner's own events through hook.event, ends as told."""

    def __init__(self, io_: FakeIO, ticks: int = 5, end: str = "weight_home: weight 0.52 > 0.50",
                 home: bool = True, raise_: BaseException | None = None) -> None:  # fmt: skip
        self.io, self.ticks, self.end, self.home, self.raise_ = io_, ticks, end, home, raise_
        self.calls: list[dict[str, Any]] = []
        self.stops: list[str | None] = []

    def __call__(self, a: Any, *, hook: Any = None, session: Any = None) -> int:
        self.calls.append({"a": a, "hook": hook, "session": session})
        if self.raise_ is not None:
            raise self.raise_
        hook.event({"kind": "run_start", "map": "xmas_dun02"}, self.io.now)
        reason = self.end
        for i in range(self.ticks):
            self.io.now += 0.2
            view = dh.HuntTick(self.io.now, 80, 60, False, (10, 10), "search", {}, None)
            hook.event({"kind": "hp_read", "pct": 80, "pos": [10, 10]}, self.io.now)
            why = dh.hook_stop(hook, view)
            self.stops.append(why)
            if why is not None:
                reason = f"stopped: {why}"
                break
            if i == 1:
                hook.event({"kind": "kill"}, self.io.now)
        hook.event({"kind": "run_end", "reason": reason, "counts": {}}, self.io.now)
        if self.home and not reason.startswith("stopped"):
            self.io.w["map"] = "geffen"  # the runner's own way home (player_home_end)
        hook.event({"kind": "player_end", "reason": reason, "home": self.home, "dead": False,
                    "respawned": False}, self.io.now)  # fmt: skip
        return 0


def hunt_prep(tmp_path: Path, main: list[Any] | None = None) -> fp.Prepared:
    return prep(tmp_path, main or [HUNT, wing_exit()])


def test_the_hunt_core_runs_in_process_with_the_same_agent_and_the_tick_hook(
    tmp_path: Path,
) -> None:
    p = hunt_prep(tmp_path)
    plan = p.runners["field"]
    assert plan.flow_id == "xmas_dun02_rogue"
    assert plan.keys == {"heal_key": "F1", "fly_key": "F8", "home_key": "F9", "knife_key": "F4",
                         "dagger_key": "F5"}  # fmt: skip
    io_ = FakeIO()
    runner = FakeRunner(io_)
    argvs: list[list[str]] = []

    def args_fn(argv: Any) -> Any:
        argvs.append(list(argv))
        return dh.args_for(argv)

    demo = tmp_path / "demo"
    demo.mkdir()
    stop = tmp_path / "STOP"
    hunt = fp.HuntCore("t7", stop, run_fn=runner, args_fn=args_fn)
    fp.play(p, io_, label="t7", stop_file=stop, demo=demo, checker=ok_check, hunt=hunt)
    (call_,) = runner.calls
    assert call_["session"] == ("AGENT", "SCREEN")  # ONE input writer: the player's own
    assert runner.stops == [None] * 5  # called once per runner tick, no stop asked
    # the runner's argv is exactly the Run helper's for that map (its head left out), its time box
    # the player's remaining time, its label its own
    (argv,) = argvs
    want = fr.command(fr.FLOWS["xmas_dun02_rogue"], "t7-hunt1", stop, plan.vals)[9:]
    i = want.index("--minutes") + 1
    assert argv[:i] == want[:i] and argv[i + 1 :] == want[i + 1 :]
    assert float(argv[i]) <= 10.0 and "--player-mode" in argv
    assert call_["a"].player_mode and call_["a"].stop_file == str(stop)
    # it ended on its own way home: the player follows her by the map's name to the home node
    ev = events(demo)
    kinds = [e["kind"] for e in ev]
    for k in ("hunt_start", "hunt_run_start", "kill", "hunt_run_end", "player_end", "hunt_end"):
        assert k in kinds, k
    reloc = next(e for e in ev if e["kind"] == "map_node")
    assert (reloc["node"], reloc["how"], reloc["map"]) == ("home", "relocate", "geffen")
    assert ev[-1]["reason"] == "home"
    assert taps(io_) == []  # the box's own wing never pressed: the runner took her home


def test_the_hunt_cores_hook_carries_stop_and_its_refusal_fails_the_block(tmp_path: Path) -> None:
    stop = tmp_path / "STOP"
    stop.touch()  # pressed while the runner plays: its hook asks it to end at the next tick
    p = hunt_prep(tmp_path)
    io_ = FakeIO()
    runner = FakeRunner(io_)
    pl = fp.LivePlayer(p, io_, fp.SessionLog(tmp_path, "h"), stop_file=stop,
                       hunt=fp.HuntCore("h", stop, run_fn=runner))  # fmt: skip
    pl.start_world("xmas_dun02")
    stop.unlink()
    pl.stack.clear()

    def once() -> str:
        gen = pl._hunt_core()
        next(gen)
        stop.touch()
        try:
            gen.send(None)
        except fp._Halt as h:
            return h.reason
        raise AssertionError("no end")

    runner.ticks = 3
    assert once() == "stopped" and runner.stops == ["Stop pressed"]
    # a refusal of the runner's preamble (a SystemExit) fails the block with its words
    stop.unlink()
    d = tmp_path / "demo"
    d.mkdir()
    bad = FakeRunner(io_, raise_=SystemExit("dungeon@9.46 refused: --player-mode: she is on "
                                            "geffen, not xmas_dun02"))  # fmt: skip
    fp.play(hunt_prep(tmp_path), FakeIO(), label="t8", stop_file=None, demo=d, checker=ok_check,
            hunt=fp.HuntCore("t8", None, run_fn=bad))  # fmt: skip
    end = events(d)[-1]
    assert end["reason"] == "dungeon_hunt_failed" and "she is on geffen" in end["words"]


def test_the_hunt_core_ending_on_the_map_goes_on_with_the_box(tmp_path: Path) -> None:
    """A runner that ends without leaving the map (its own time box, a weight exit with no wing):
    the box's main goes on -- its loop calls the hunt core again, then its own wing home."""
    p = hunt_prep(tmp_path, [{"kind": "repeat", "times": lit(2), "body": [HUNT]}, wing_exit()])
    io_ = FakeIO()
    runner = FakeRunner(io_, end="time_box", home=False)
    d = tmp_path / "demo"
    d.mkdir()
    fp.play(p, io_, label="t9", stop_file=None, demo=d, checker=ok_check,
            hunt=fp.HuntCore("t9", None, run_fn=runner))  # fmt: skip
    assert len(runner.calls) == 2 and events(d)[-1]["reason"] == "home"
    assert [c["a"].label for c in runner.calls] == ["t9-hunt1", "t9-hunt2"]
    assert taps(io_) == ["F9"]  # the box's own exit, after the two hunts


# --- dungeon_hunt: the library seams leave the CLI as it was --------------------------------------
def test_run_takes_an_optional_hook_and_session_and_the_cli_passes_neither() -> None:
    sig = inspect.signature(dh.run)
    assert sig.parameters["hook"].default is None and sig.parameters["session"].default is None
    src = inspect.getsource(dh.main)
    assert "return run(a)" in src  # the CLI: no hook, no session
    assert dh.hook_stop(None, None) is None  # type: ignore[arg-type]

    class H:
        def tick(self, view: Any) -> str | None:
            return "Stop pressed" if view == "x" else None

    assert dh.hook_stop(H(), "x") == "Stop pressed" and dh.hook_stop(H(), "y") is None  # type: ignore[arg-type]


def _loop(fn_src: str) -> ast.While:
    tree = ast.parse(textwrap.dedent(fn_src))
    loops = [n for n in ast.walk(tree) if isinstance(n, ast.While)
             and ast.unparse(n.test) == "time.monotonic() < t_end"]  # fmt: skip
    assert len(loops) == 1
    return loops[0]


def _loop_continues(stmts: list[ast.stmt]) -> list[ast.Continue]:
    """`continue`s that belong to THIS loop (not to a nested loop or a function)."""
    out: list[ast.Continue] = []
    for st in stmts:
        if isinstance(st, ast.Continue):
            out.append(st)
        elif isinstance(st, ast.For | ast.While | ast.AsyncFor | ast.FunctionDef):
            continue
        else:
            for field in ("body", "orelse", "finalbody", "handlers"):
                for sub in getattr(st, field, []) or []:
                    if isinstance(sub, ast.ExceptHandler):
                        out += _loop_continues(sub.body)
                    else:
                        out += _loop_continues([sub])
    return out


def test_run_calls_the_tick_hook_once_on_every_tick_of_its_loop() -> None:
    """The hook call is a TOP-LEVEL statement of the loop's body (every tick reaches it: no
    `continue` of the loop before it), right after the tick's hp_read event; the CLI (no hook)
    builds nothing."""
    loop = _loop(inspect.getsource(dh.run))
    body = loop.body
    at = next(i for i, st in enumerate(body) if "hook_stop(hook" in ast.unparse(st))
    st = body[at]
    assert isinstance(st, ast.If) and ast.unparse(st.test) == "hook is not None"
    inner = st.body
    assert isinstance(inner[0], ast.Assign) and "hook_stop(hook, HuntTick(" in ast.unparse(inner[0])
    assert isinstance(inner[1], ast.If) and "why_hk is not None" in ast.unparse(inner[1].test)
    assert "break" in ast.unparse(inner[1])  # the NORMAL end (run_end, the player's end)
    assert _loop_continues(body[:at]) == []
    assert "'kind': 'hp_read'" in ast.unparse(body[at - 1])  # right after the tick's HUD read
    assert (
        sum("hook_stop(" in ast.unparse(n) for n in ast.walk(loop) if isinstance(n, ast.Assign))
        == 1
    )
    # the session: the player's own (kept open for it) or, the CLI's, ro_agent.session
    src = inspect.getsource(dh.run)
    assert "None if session is None else contextlib.nullcontext(session)" in src
    assert 'with r.session(f"rule:dungeon-{a.strategy}") if given is None else given as' in src


def test_args_for_is_the_clis_own_parse() -> None:
    plan_argv = fr.command(fr.FLOWS["xmas_dun02_rogue"], "flowplay-x")[9:]
    a = dh.args_for(plan_argv)
    b = dh.build_parser().parse_args(["run", *plan_argv])
    assert a.cmd == "run" and vars(a) == {**vars(b), "ag_match": a.ag_match}
    assert a.ag_match is not None  # main()'s default (survive.AG_MATCH_DUNGEON)
    assert dh.args_for(plan_argv, cmd="check").cmd == "check"
    with pytest.raises(ValueError):
        dh.args_for(plan_argv, cmd="clear-bag")


def test_the_runners_check_runs_in_process_without_an_input_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import ro_agent as r

    p = hunt_prep(tmp_path)
    seen: dict[str, Any] = {}

    def fake_run(a: Any) -> int:
        seen["cmd"] = a.cmd
        with pytest.raises(SystemExit, match="sends no input"):
            r.Agent()  # the no-input guard holds while the check runs
        print(dh.CHECK_MARK + json.dumps({"items": [{"id": "cell", "ok": True, "words": "w"}],
                                          "ok": True, "refuses": False}))  # fmt: skip
        return 0

    agent_before = r.Agent
    got = fp.runner_check(p.runners["field"], run_fn=fake_run)
    assert seen["cmd"] == "check" and got["state"] == "done" and got["ok"] is True
    assert r.Agent is agent_before  # restored: the player opens its own Agent afterwards
    assert fp.check_refusal(got) is None


# --- the Run helper: a project run ----------------------------------------------------------------
def test_a_project_request_names_its_node_and_hash_and_nothing_else() -> None:
    base = {"id": "a1b2c3d4e5", "action": "start", "flow": "project", "node": "xmas_dun02",
            "project_hash": "a" * 64, "max_s": 86400}  # fmt: skip
    assert fr.parse_request(json.dumps(base)) == base
    for k, v in (("node", "rm -rf"), ("project_hash", "x"), ("max_s", 0), ("max_s", True)):
        assert isinstance(fr.parse_request(json.dumps({**base, k: v})), str), k
    assert isinstance(fr.parse_request(json.dumps({**base, "argv": ["--clear-map"]})), str)
    keys = {"heal_key": "F1", "fly_key": "F8", "home_key": "F9", "knife_key": "F4",
            "dagger_key": "F5"}  # fmt: skip
    assert fr.parse_request(json.dumps({**base, "keys": keys}))["keys"] == keys  # type: ignore[index]
    # a check of "project" is the runner's check (for now)
    ck = fr.parse_request(json.dumps({"id": "a1b2c3d4e5", "action": "check", "flow": "project"}))
    assert isinstance(ck, dict) and ck["flow"] == fr.PROJECT_CHECK_FLOW
    player = "/home/bot/docker/poring-lab/.venv/bin/python scripts/flow_play.py play --project x"
    assert "live block player" in str(fr.busy_reason([player]))


def test_the_helper_starts_the_player_with_the_checked_file_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import hashlib
    import types

    made: list[Any] = []

    class Proc:
        def __init__(self, argv: list[str], **kw: Any) -> None:
            self.argv, self.pid = argv, 4242
            made.append(self)

        def poll(self) -> int | None:
            return None

    monkeypatch.setattr(fr, "SCRATCH", tmp_path / "scratch")
    monkeypatch.setattr(fr, "busy_reason", lambda _lines: None)
    monkeypatch.setattr(
        fr.subprocess, "run", lambda *a, **k: types.SimpleNamespace(stdout="", returncode=0)
    )
    monkeypatch.setattr(fr.subprocess, "Popen", Proc)
    p = pj.from_json(json.dumps(project([HUNT, wing_exit()])))
    text = pj.canonical_json(p).encode()
    (tmp_path / fr.PROJECT_FILE).write_bytes(text)
    h = fr.Helper(tmp_path)
    detect: list[float] = []
    monkeypatch.setattr(h, "detect_up", lambda: detect.append(h.cap_s) or True)
    req = {"id": "a1b2c3d4e5", "action": "start", "flow": "project", "node": "field",
           "project_hash": "b" * 64, "max_s": 86400}  # fmt: skip
    h.handle(req)
    assert h.state == "refused" and "not the one checked" in h.detail and made == []
    req["project_hash"] = hashlib.sha256(text).hexdigest()
    h.state = "idle"
    h.handle({**req, "node": "login"})
    assert h.state == "refused" and "no map node" in h.detail and made == []
    h.state = "idle"
    h.handle(req)
    (proc,) = made
    assert proc.argv[:9] == ["nice", "-n", "10", "uv", "run", "--quiet", "python",
                             "scripts/flow_play.py", "play"]  # fmt: skip
    assert proc.argv[proc.argv.index("--node") + 1] == "field"
    assert proc.argv[proc.argv.index("--project-hash") + 1] == req["project_hash"]
    pfile = Path(proc.argv[proc.argv.index("--project") + 1])
    assert pfile.read_bytes() == text and pfile.parent == h.run_dir  # its own copy
    assert proc.argv[proc.argv.index("--stop-file") + 1] == str(h.run_dir / fr.STOP_NAME)
    assert detect == [600.0 + fr.CAP_GRACE_S]  # a hunt core plays: the detect server first
    st = h.status()
    assert st["flow"] == "project" and st["state"] == "starting"
    assert st["flows"]["project"]["title"] == "live_test"
    assert st["flows"]["project"]["map"] == "xmas_dun02" and st["flows"]["project"]["minutes"] == 10
    assert st["project"]["node"] == "field" and "xmas_dun02_rogue" in st["flows"]
    # one input writer: a second start while it plays is refused
    h.handle(req)
    assert len(made) == 1 and "already going" in h.detail


def test_the_helpers_project_entry_reads_the_same_way_before_any_run(tmp_path: Path) -> None:
    st = fr.Helper(tmp_path).status()
    assert st["flows"]["project"] == {"title": "a project", "minutes": 0, "map": "",
                                      "defaults": {}, "kind": "project"}  # fmt: skip
    assert fc.clash({}) is None  # the backend's config check over an empty defaults entry
