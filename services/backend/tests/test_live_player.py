"""scripts/flow_play.py, the LIVE BLOCK PLAYER (Batt 2026-11-13, docs/planning/live-blocks.md stage
1; ADR-0020 Amendment E): offline, no game. A FakeIO records every input and scripts the sensor
values on a fake clock; the hunt core's runner is a fake run() that drives the tick hook."""

from __future__ import annotations

import ast
import inspect
import io
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
import huntstate_check as hc  # noqa: E402

from poring_flow import catalogue, editor, ir, live  # noqa: E402
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


# Round 29 (Batt 2026-11-16, live-blocks.md 17 #2: the old one-block runner is no longer used in
# real runs): a project as the PRODUCT Run path takes it -- every map node's runner block (HUNT) as
# the functions shape: its main calls hunt_loop(), its roles are role blocks on a tab hunt with the
# hunt loop (the ready-made functions box's own def). flow_play itself still plays both shapes.
HUNT_LOOP_CALL = {"kind": "call", "proc": "hunt_loop", "args": [], "kwargs": {}}
FUNCTIONS_BOX = ROOT / "services/frontend/src/lib/flow/fixtures/project_xmas_dun02_functions.json"


def functions_shape(d: dict[str, Any]) -> dict[str, Any]:
    import copy

    out = copy.deepcopy(d)
    box = json.loads(FUNCTIONS_BOX.read_text())
    loop = next(x for t in box["nodes"][0]["tabs"] if t["name"] == "hunt" for x in t["defs"]
                if x["name"] == "hunt_loop")  # fmt: skip
    for n in out["nodes"]:
        if n.get("kind") != "map":
            continue
        for t in n["tabs"]:
            if t["name"] != "main" or not t["main"]:
                continue
            hunts = [st for st in t["main"] if st.get("block") == "dungeon_hunt"]
            if not hunts:
                continue
            t["main"] = [HUNT_LOOP_CALL if st.get("block") == "dungeon_hunt" else st
                         for st in t["main"]]  # fmt: skip
            roles = {f"role_{k}": v for k, v in hunts[0]["params"].items()}
            n["tabs"].append({"name": "hunt", "main": None, "defs": [loop], "vars": roles})
            break
    return out


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
    got = fp.prepare(json.dumps(project(field_main, **kw)), "field", 3600)
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
    # stage 3: click_at (only inside dungeon_hunt's respawn functions: live.click_problems);
    # stage 4a: use_model and the recipe primitives (only inside a monster's recipe: recipes.py);
    # 5b-2 (live-blocks.md 14): the hunt loop's blocks (only inside hunt_loop: huntloop.py);
    # 5c (15.3): the tick's step blocks (only inside hunt_tick: poring_flow.tick)
    from poring_flow import tick as tk

    assert live.live_blocks() == sorted(["assert_save_point", "choose_target", "click_at",
                                         "dungeon_hunt", "fight_target", "find_target", "look",
                                         "loot", "press_key", "strike", "use_model", "use_skill",
                                         "wait_kill", "wait_steal", "walk_to_target",
                                         *tk.STEP_BLOCKS])  # fmt: skip
    assert live.live_sensors() == ["current_map", "hotbar_count", "hp_percent", "is_dead",
                                   "map_load_seen", "sees_boss", "sp_percent",
                                   "weight_percent"]  # fmt: skip  # 2026-11-14: hotbar_count
    doc = editor.catalogue_doc()
    assert doc["live"]["blocks"] == live.live_blocks() and doc["live"]["stage"] == 4
    assert doc["live"]["hunt_core"]["recipes"]["shapes"] == [list(x) for x in dh.RECIPE_SHAPES]
    assert doc["live"]["hunt_core"]["sensors"] == ["hp_percent", "sp_percent", "sees_boss",
                                                   "weight_percent", "hotbar_count"]  # fmt: skip
    assert doc["live"]["hunt_core"]["eat"]["role"] == "eat"
    assert doc["live"]["hunt_core"]["calls"]["max_wait_s"] == 1.0
    assert doc["blocks"]["press_key"]["spec"]["live"] is True
    assert doc["blocks"]["walk_to"]["spec"]["live"] is False
    assert doc["sensors"]["hp_percent"]["spec"]["live"] is True
    assert doc["live"]["later"]["walk_to"] == "stage 4" and "press_key" not in doc["live"]["later"]
    assert set(doc["live"]["later"]) == {*cat.blocks, *cat.sensors} - {
        *live.live_blocks(),
        *live.live_sensors(),
    }
    # one version, three places (2026-11-14: the box eats from the hotbar; stage 4a's model and
    # recipes stay 9.51, stage 3's functions 9.50, stage 2's survival events 9.49, stage 1's
    # library seam 9.48); the runner's own version is unchanged
    assert dh.BOX_EAT_VERSION == live.VERSION == fp.VERSION == "9.52"
    assert dh.BOX_RECIPES_VERSION == "9.51"
    assert dh.BOX_FUNCTIONS_VERSION == "9.50"
    assert dh.SURVIVAL_EVENTS_VERSION == "9.49"
    assert dh.LIVE_BLOCKS_VERSION == "9.48" and dh.VERSION == "dungeon@8.7"
    assert dh.BOX_PLAYS == live.PLAYS


def test_a_block_without_a_live_binding_refuses_before_any_input(tmp_path: Path) -> None:
    walk = action("walk_to", "nav.walk_to", {"cell": lit({"kind": "cell", "map": "xmas_dun02",
                                                          "x": 10, "y": 10})}, 120.0)  # fmt: skip
    got = fp.prepare(json.dumps(project([press("F2"), walk, wing_exit()])), "field", 3600)
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
    assert "no map node" in str(fp.prepare(text, "login", 3600))
    assert "above the configured maximum 300" in str(fp.prepare(text, "field", 300))
    assert "no configured maximum" in str(fp.prepare(text, "field", None))
    h = fp.prepare(text, "field", 3600)
    assert isinstance(h, fp.Prepared)
    assert "not the checked" in str(fp.prepare(text, "field", 3600, want_hash="0" * 64))


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
    # Batt 2026-11-21: the rule the Run plays rides with its reading (the story says both)
    assert fired[0]["when"].startswith("hp_percent()") and "reading" in fired[0]
    assert "(its rule: hp_percent()" in str(fr.event_words(fired[0]))
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
    p = fp.prepare(text, "field", 3600)
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
        assert end["words"] and ("stage 2" in end["words"] or "a person looks" in end["words"]
                                 or "a later stage" in end["words"])  # fmt: skip
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

    def __call__(self, a: Any, *, hook: Any = None, session: Any = None, **kw: Any) -> int:
        self.calls.append({"a": a, "hook": hook, "session": session, **kw})
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
    # stage 2: Global's hp_low presses the heal key, so inside the hunt core the box plays the
    # potion and the runner's own is off for this run (live.hunt_plan)
    assert call_["box_plays"] == ["potion"] and plan.events == ("hp_low",)
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
    """The main loop as the driver plays it (5b-1: the steps' bodies in their order)."""
    return hc.driver_loop(ast.parse(textwrap.dedent(fn_src)))


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
    # max_s 0 = no maximum since 2026-11-19 (ADR-0020 Amendment T): accepted; -1 is not
    assert fr.parse_request(json.dumps({**base, "max_s": 0})) == {**base, "max_s": 0}
    for k, v in (("node", "rm -rf"), ("project_hash", "x"), ("max_s", -1), ("max_s", True)):
        assert isinstance(fr.parse_request(json.dumps({**base, k: v})), str), k
    assert isinstance(fr.parse_request(json.dumps({**base, "argv": ["--clear-map"]})), str)
    keys = {"heal_key": "F1", "fly_key": "F8", "home_key": "F9", "knife_key": "F4",
            "dagger_key": "F5"}  # fmt: skip
    assert fr.parse_request(json.dumps({**base, "keys": keys}))["keys"] == keys  # type: ignore[index]
    # 2026-11-14 (live-blocks.md 12): a check of "project" carries its node, the keys and EVERY
    # setting block's value (the backend computed them from the project); checked here again
    vals = {f.name: f.default for f in fc.FIELDS if f.block}
    chk = {"id": "a1b2c3d4e5", "action": "check", "flow": "project", "node": "xmas_dun02",
           "keys": keys, "vals": vals}  # fmt: skip
    ck = fr.parse_request(json.dumps(chk))
    assert isinstance(ck, dict) and ck["flow"] == fr.PROJECT and ck["vals"] == vals
    for bad, words in (({**chk, "vals": {**vals, "knife_hp_min": 5.0}}, "is not from"),
                       ({**chk, "vals": {**vals, "heal_key": "F1"}}, "every setting block"),
                       ({**chk, "vals": {k: v for k, v in vals.items() if k != "minutes"}},
                        "every setting block"),
                       ({**chk, "keys": None}, "keys must be"),
                       ({**chk, "argv": ["--clear-map"]}, "nothing else"),
                       ({**chk, "flow": "xmas_dun02_rogue"}, "unknown flow")):  # fmt: skip
        got = fr.parse_request(json.dumps(bad))
        assert isinstance(got, str) and words in got, (got, words)
    # the runner-only start went with the runner page
    old = fr.parse_request(json.dumps({"id": "a1b2c3d4e5", "action": "start",
                                       "flow": "xmas_dun02_rogue"}))  # fmt: skip
    assert isinstance(old, str) and "unknown flow" in old
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
    monkeypatch.setattr(fr, "writer_busy", lambda _lines: None)
    monkeypatch.setattr(
        fr.subprocess, "run", lambda *a, **k: types.SimpleNamespace(stdout="", returncode=0)
    )
    monkeypatch.setattr(fr.subprocess, "Popen", Proc)
    h = fr.Helper(tmp_path)
    detect: list[float] = []
    monkeypatch.setattr(h, "detect_up", lambda: detect.append(h.cap_s) or True)
    req = {"id": "a1b2c3d4e5", "action": "start", "flow": "project", "node": "field",
           "project_hash": "b" * 64, "max_s": 86400}  # fmt: skip
    # round 29 (live-blocks.md 17 #2): the old one-block runner is no real run -- refused in words,
    # before any input, even as the checked file
    old = pj.canonical_json(pj.from_json(json.dumps(project([HUNT, wing_exit()])))).encode()
    (tmp_path / fr.PROJECT_FILE).write_bytes(old)
    h.handle({**req, "project_hash": hashlib.sha256(old).hexdigest()})
    assert h.state == "refused" and made == []
    assert h.detail == f"refused before any input: {pj.OLD_RUNNER_WORDS}"
    h.state = "idle"
    p = pj.from_json(json.dumps(functions_shape(project([HUNT, wing_exit()]))))
    text = pj.canonical_json(p).encode()
    (tmp_path / fr.PROJECT_FILE).write_bytes(text)
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


# --- matpilot round 17 N1: what a box run's box replaces in the run settings ----------------------
def test_the_box_takeovers_name_real_settings_and_follow_the_plan() -> None:
    """live.PLAY_SETTINGS names flow_config FIELDS (the settings rows Before Run shows); a play's
    settings are the runner's own handler that dungeon_hunt switches off for it (stage 2: sustain's
    off= potion / fly_hp; stage 3: the weight exit and the respawn clicks on box_plays); the HP-rate
    fly stays the runner's."""
    names = {f.name for f in fc.FIELDS}
    for play, settings in live.PLAY_SETTINGS.items():
        assert play in live.PLAYS and set(settings) <= names, play
    assert set(live.RUNNER_STAYS) <= names
    assert set(live.PLAY_WORDS) == set(live.PLAYS)
    src = (ROOT / "scripts" / "dungeon_hunt.py").read_text()
    assert 'box_off = box_set & {"potion", "fly_hp"}' in src  # potion_below / fly_below off
    assert '"fly_hp" not in off and hp < strat["fly_below"]' in src
    assert '"potion" not in off and hp < strat["potion_below"]' in src
    assert 'rate > strat["fly_rate"] and hp < strat["fly_rate_below"]' in src  # never `off`
    fixtures = ROOT / "services" / "frontend" / "src" / "lib" / "flow" / "fixtures"
    one = pj.from_json((fixtures / "project_xmas_dun02.json").read_text())
    c = pj.compile_project(one)
    assert c.flow is not None
    doc = live.takeovers(c.flow, "xmas_dun02", lambda s: c.where(s).path)
    assert doc is not None and doc["playable"] is True
    assert doc["plays"] == sorted(live.hunt_plan(c.flow, "xmas_dun02").plays)
    rows = {(r["play"], r["by"]): r for r in doc["takeovers"]}
    drink = rows[("potion", "drink")]
    assert (drink["settings"], drink["when"], drink["until"], drink["path"]) == (
        ["potion_below"],
        "HP < 50 %",  # Batt 2026-11-14: "raise the drink" (live-blocks.md 10; it was 30 %)
        "HP >= 51 %",
        "xmas_dun02/survival/drink",
    )
    # 2026-11-14: the candies, eaten at once -- a play of the box's own, no takeover row (it
    # switches nothing of the runner's off); its words are cond_words'
    assert "eat" in doc["plays"] and not [r for r in doc["takeovers"] if r["play"] == "eat"]
    assert live.OWN_PLAYS == ("eat",)
    assert live.hunt_plan(c.flow, "xmas_dun02").play_by["eat"] == ("eat_cane", "eat_candy")
    cnt = ir.Sense(sensor="hotbar_count", args={"key": ir.Lit(value="F6")})
    assert live.cond_words(ir.Cmp(op=">", left=cnt, right=ir.Lit(value=0))) == "F6's count > 0"
    assert live.cond_words(ir.Cmp(op="==", left=cnt, right=ir.Lit(value=0))) == "F6's count = 0"
    fly = rows[("fly_hp", "fly_away")]
    assert (fly["settings"], fly["when"]) == (["fly_below"], "a boss is seen or HP < 25 %")
    assert rows[("boss_fly", "fly_away")]["settings"] == []  # no setting: the boss line itself
    bag = rows[("weight_home", "bag_full")]
    assert (bag["settings"], bag["when"]) == (["weight_home"], "weight >= 50 %")
    assert (rows[("respawn", "respawn_button")]["settings"], rows[("respawn", "respawn_button")]
            ["steps"]) == (["respawn_at"], "a click at 645,481")  # fmt: skip
    assert rows[("respawn", "respawn_ok")]["settings"] == ["respawn_confirm_at"]
    assert doc["stays"] == ["fly_rate", "fly_rate_below"]
    # the stage-2 box: its two events only; the runner keeps its weight exit and its respawn points
    s2 = pj.from_json((fixtures / "project_xmas_dun02_stage2.json").read_text())
    c2 = pj.compile_project(s2)
    assert c2.flow is not None
    d2 = live.takeovers(c2.flow, "xmas_dun02")
    assert d2 is not None
    took = sorted({x for r in d2["takeovers"] for x in r["settings"]})
    assert took == ["fly_below", "potion_below"]
    # a box without the survival events replaces none of them (the runner's own, as stage 1)
    raw = json.loads((fixtures / "project_xmas_dun02_stage2.json").read_text())
    raw["nodes"][0]["tabs"] = [t for t in raw["nodes"][0]["tabs"] if t["name"] != "survival"]
    c3 = pj.compile_project(pj.validate(raw))
    assert c3.flow is not None
    d3 = live.takeovers(c3.flow, "xmas_dun02")
    assert d3 is not None and d3["takeovers"] == [] and d3["plays"] == []
    # the lint document carries it per node (the pages read it)
    lint = pj.lint_doc(one, world=None, resolver=None)
    assert set(lint["box"]) == {"xmas_dun02"} and lint["box"]["xmas_dun02"] == doc


# --- the run's diary (Batt 2026-11-18: "log the status, the checklist and the errors more") ------
class DiaryIO(FakeIO):
    def describe(self) -> list[str]:
        return ["screen: the session 1920x1080; the game = FULLSCREEN"]


def test_a_refused_start_logs_each_check_line_the_screen_and_its_pictures(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    p = prep(tmp_path, [press("F2")])
    got = {"items": [{"id": "identity", "ok": True, "words": "the name plate reads hers"},
                     {"id": "weight", "ok": False, "words": "the weight did not read"},
                     {"id": "cell", "ok": None, "words": "cannot tell",
                      "value": "(237, 117)"}]}  # fmt: skip
    io_ = DiaryIO()
    assert fp.play(p, io_, label="t10", stop_file=None, demo=tmp_path / "demo",
                   checker=lambda _p, _i: got, run_dir=tmp_path) == 2  # fmt: skip
    out = capsys.readouterr().out.splitlines()
    text = "\n".join(out)
    assert "screen: the session 1920x1080; the game = FULLSCREEN" in text
    assert "check OK   identity: the name plate reads hers" in text
    assert "check FAIL weight: the weight did not read" in text
    assert "check ?    cell: cannot tell [read: (237, 117)]" in text
    assert "1 of 3 lines pass; FAIL: weight; not read: cell" in text
    assert io_.out == []  # nothing pressed
    # Batt 2026-11-18 ~22:3x: no picture is saved (a frame can show other people's chat)
    assert not [p for p in tmp_path.rglob("*") if p.suffix in (".jpg", ".png")]
    assert not hasattr(fp.LiveIO, "snapshot") and not hasattr(fp, "START_SCREEN")
    assert "refused" in out[-1]  # the helper's detail is the last line (flow_run tail 3)
    assert not any(ln.startswith("CHECK ") for ln in out)  # the machine line's prefix is not ours


def test_a_fault_logs_its_traceback_and_keeps_it_whole_in_the_run_folder(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    p = prep(tmp_path, [press("F2")])

    class Boom(DiaryIO):
        def open(self) -> None:
            raise ValueError("the hotbar template is missing")

    demo = tmp_path / "demo"
    demo.mkdir()
    fp.play(p, Boom(), label="t11", stop_file=None, demo=demo, checker=ok_check, run_dir=tmp_path)
    text = capsys.readouterr().out
    assert "ERROR: ValueError: the hotbar template is missing" in text
    assert "  | ValueError: the hotbar template is missing" in text  # its traceback, in the log
    assert "ValueError" in (tmp_path / fp.ERROR_FILE).read_text()


def test_the_pause_notes_log_each_pause_and_return_and_sum_them(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    notes = fp.PauseNotes()
    demo = tmp_path / "demo"
    demo.mkdir()
    notes.session = fp.SessionLog(demo, "t12")
    notes("pause", {"why": "the Windows taskbar shows", "t_wall": 1.0})
    notes("resume", {"after_s": 12.5, "t_wall": 2.0})
    text = capsys.readouterr().out
    assert "PAUSED: the Windows taskbar shows. The bot waits and presses nothing" in text
    assert "RESUMED after 12.5 s: the game is back on the screen" in text
    assert notes.summary() == {"pauses": 1, "paused_s": 12.5}
    notes.session.close()
    kinds = [e["kind"] for e in events(demo)]
    assert kinds == ["pause", "resume"]


def test_a_run_that_ends_paused_counts_the_open_pause() -> None:
    """2026-11-22 16:28: the client crashed, the Run paused and was Stopped ~24 min later without a
    resume; its summary said "0 s in all". An open pause counts up to the end."""
    now = [100.0]
    notes = fp.PauseNotes(out=io.StringIO())
    notes.clock = lambda: now[0]
    notes("pause", {"why": "the Windows taskbar shows", "t_wall": 1.0})
    now[0] = 112.5
    notes("resume", {"after_s": 12.5, "t_wall": 2.0})
    assert notes.summary() == {"pauses": 1, "paused_s": 12.5}  # closed: as before
    notes("pause", {"why": "the Windows taskbar shows", "t_wall": 3.0})
    now[0] = 112.5 + 1468.0
    assert notes.summary() == {"pauses": 2, "paused_s": 1480.5, "ended_paused": True}


def test_a_run_turns_the_pause_on_and_stop_ends_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import ro_agent as r

    monkeypatch.setenv(r.AWAY_ENV, "")  # recorded as unset: teardown takes enable_pause's "1" away
    monkeypatch.setattr(r, "AWAY_HOOK", None)
    monkeypatch.setattr(r, "AWAY_STOP", None)
    stop = tmp_path / "STOP"
    notes = fp.enable_pause(stop)
    assert r.pause_away() and r.AWAY_HOOK is notes
    assert r.AWAY_STOP() is None
    stop.write_text("")
    assert "Stop was pressed while the run was paused" in r.AWAY_STOP()


def test_a_pause_during_the_start_check_shows_in_the_log_at_once(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Live test 2026-11-18 20:02: the start check captures stdout while it reads (runner_check);
    the PAUSED line written then reached the log only after the check, 83 s late."""
    import contextlib
    import io

    notes = fp.PauseNotes()  # made with the run's real stdout (enable_pause, before the check)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        notes("pause", {"why": "the Windows taskbar shows"})
    assert "PAUSED: the Windows taskbar shows" in capsys.readouterr().out
    assert buf.getvalue() == ""


# --- Batt 2026-11-19: after a CODE error she is checked and the hunt core plays again ------------
class FailsFirst(FakeRunner):
    """The runner's first call ends on ``first`` (an exception), the next ones as FakeRunner."""

    def __init__(self, io_: FakeIO, first: BaseException, fails: int = 1) -> None:
        super().__init__(io_)
        self.first, self.fails = first, fails

    def __call__(self, a: Any, *, hook: Any = None, session: Any = None, **kw: Any) -> int:
        if self.fails > 0:
            self.fails -= 1
            self.calls.append({"a": a})
            raise self.first
        return super().__call__(a, hook=hook, session=session, **kw)


def _retry_run(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    runner: FakeRunner,
    options: dict[str, Any] | None,
    checker: Any = None,
) -> list[dict[str, Any]]:
    opts_dir = tmp_path / "flowrun"
    opts_dir.mkdir(parents=True, exist_ok=True)
    if options is not None:
        (opts_dir / "options.json").write_text(json.dumps(options))
    monkeypatch.setattr(fr, "DIR", opts_dir)
    monkeypatch.setattr(fp, "default_checker", checker or ok_check)
    d = tmp_path / "demo"
    d.mkdir(parents=True, exist_ok=True)
    fp.play(hunt_prep(tmp_path), runner.io, label="r1", stop_file=None, demo=d, checker=ok_check,
            hunt=fp.HuntCore("r1", None, run_fn=runner))  # fmt: skip
    return events(d)


def test_a_code_error_is_retried_after_the_check_and_the_hunt_plays_on(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    io_ = FakeIO()
    runner = FailsFirst(io_, RuntimeError("chat tab battle not shown"))
    ev = _retry_run(tmp_path, monkeypatch, runner, {"v": 1, "retry_max": 2, "retry_wait_s": 5})
    kinds = [e["kind"] for e in ev]
    assert len(runner.calls) == 2  # it played again
    (r,) = [e for e in ev if e["kind"] == "retry"]
    assert (r["n"], r["of"], r["wait_s"]) == (1, 2, 5) and "chat tab battle" in r["error"]
    assert kinds.index("retry") < kinds.index("retry_go") < kinds.index("hunt_run_start")
    assert ev[-1]["reason"] == "home"  # the second hunt ended on its own way home
    assert io_.now >= 5.0  # it waited the option's seconds before the check


def test_a_frozen_picture_is_retried_a_refusal_never(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import ro_agent as r

    io_ = FakeIO()
    runner = FailsFirst(io_, r.FrozenStream("no frame newer than the action within 1.5 s"))
    ev = _retry_run(tmp_path, monkeypatch, runner, None)  # the default: 3 tries
    assert len(runner.calls) == 2 and [e["kind"] for e in ev].count("retry") == 1
    io2 = FakeIO()
    refused = FailsFirst(io2, SystemExit("dungeon@9.46 refused: she is on geffen"))
    ev2 = _retry_run(tmp_path / "b", monkeypatch, refused, None)
    assert len(refused.calls) == 1 and "retry" not in [e["kind"] for e in ev2]
    assert ev2[-1]["reason"] == "dungeon_hunt_failed"


def test_retry_off_or_used_up_ends_the_run_and_a_failed_check_never_plays(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    off = FailsFirst(FakeIO(), RuntimeError("boom"))
    ev = _retry_run(tmp_path, monkeypatch, off, {"retry_max": 0, "retry_wait_s": 5})
    assert len(off.calls) == 1 and ev[-1]["reason"] == "dungeon_hunt_failed"
    twice = FailsFirst(FakeIO(), RuntimeError("boom"), fails=5)
    ev = _retry_run(tmp_path / "b", monkeypatch, twice, {"retry_max": 2, "retry_wait_s": 5})
    assert len(twice.calls) == 3 and [e["kind"] for e in ev].count("retry") == 2

    def not_ready(_p: Any, _io: Any) -> dict[str, Any]:
        return {"ok": False, "items": [{"id": "chat", "ok": False, "words": "the chat input is "
                                        "open", "refuses": True}]}  # fmt: skip

    fails = FailsFirst(FakeIO(), RuntimeError("boom"))
    ev = _retry_run(tmp_path / "c", monkeypatch, fails, {"retry_max": 3, "retry_wait_s": 5},
                    checker=not_ready)  # fmt: skip
    assert len(fails.calls) == 1 and [e["kind"] for e in ev].count("retry_refused") == 1
    assert ev[-1]["reason"] == "dungeon_hunt_failed" and "retry" in ev[-1]["words"]


def test_a_hunt_core_s_pictures_are_removed_and_its_numbers_kept(tmp_path: Path) -> None:
    """Batt 2026-11-18 ("store no pictures at all"): the byte-pinned runner still saves end.png
    (the whole screen), strike frames, ring crops and a name tag per strike; a Run removes them
    from that hunt core's session folder only (2026-11-19)."""
    sess = tmp_path / "20261119T180953-demo-dungeon-x-flowplay-1-hunt1"
    other = tmp_path / "20261119T190000-demo-dungeon-x-flowplay-1-hunt11"  # another core
    for d in (sess / "tags", other):
        d.mkdir(parents=True)
    pics = ["end.png", "strike-001.jpg", "ring-001-red58-on0-out0.png", "tags/tag-x-0001.npy"]
    kept = ["events.jsonl", "battle_log_live.jsonl", "tags/cuts-x.jsonl"]
    for name in (*pics, *kept):
        (sess / name).write_text("x")
    (other / "end.png").write_text("x")
    assert fp.drop_pictures("flowplay-1-hunt1", tmp_path) == len(pics)
    assert not [n for n in pics if (sess / n).exists()]
    assert all((sess / n).exists() for n in kept) and (other / "end.png").exists()
    assert fp.drop_pictures("flowplay-1-hunt1", tmp_path) == 0


# --- Batt 2026-11-20: a hunt core that ended on its POSITION READ hunts on (fp.READ_ENDS) ---------
class ReadEndsFirst(FakeRunner):
    """The first ``n`` calls end on ``reason`` (a position-read end, no way home); then as
    FakeRunner (its weight home)."""

    def __init__(self, io_: FakeIO, reason: str, n: int = 1, map_after: str | None = None) -> None:
        super().__init__(io_)
        self.read_reason, self.n, self.map_after = reason, n, map_after

    def __call__(self, a: Any, *, hook: Any = None, session: Any = None, **kw: Any) -> int:
        if self.n <= 0:
            return super().__call__(a, hook=hook, session=session, **kw)
        self.n -= 1
        self.calls.append({"a": a})
        hook.event({"kind": "run_start", "map": "xmas_dun02"}, self.io.now)
        self.io.now += 1.0
        if self.map_after is not None:
            self.io.w["map"] = self.map_after
        hook.event({"kind": "run_end", "reason": self.read_reason, "counts": {}}, self.io.now)
        hook.event({"kind": "player_end", "reason": self.read_reason, "home": False,
                    "dead": False, "respawned": False}, self.io.now)  # fmt: skip
        return 0


def test_read_ends_and_their_waits() -> None:
    assert fp.read_end("position unread for 30 s")
    assert fp.read_end("hard_bar: position jump (map change?)")
    assert not fp.read_end("stock_out: item 601 reads 0 on the hotbar")
    assert not fp.read_end("death") and not fp.read_end(None)
    lo, hi = fp.REREAD_WAIT_S
    assert fp.reread_wait(None, 5.0) == lo  # the first
    assert fp.reread_wait(lo, 5.0) == 2 * lo  # a quick repeat doubles it
    assert fp.reread_wait(hi, 5.0) == hi  # capped
    assert fp.reread_wait(hi, fp.REREAD_QUICK_S) == lo  # after a real hunt: back to the first


@pytest.mark.parametrize("reason", ["position unread for 30 s",
                                    "hard_bar: position jump (map change?)"])  # fmt: skip
def test_a_position_read_end_hunts_on_without_a_limit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, reason: str
) -> None:
    """Batt 2026-11-20: "read again; if it still does not read, keep doing it" -- five read ends
    in a row (more than any retry budget), and the sixth hunt core ends on its own way home."""
    io_ = FakeIO()
    runner = ReadEndsFirst(io_, reason, n=5)
    ev = _retry_run(tmp_path, monkeypatch, runner, {"v": 1, "retry_max": 1, "retry_wait_s": 5})
    kinds = [e["kind"] for e in ev]
    assert len(runner.calls) == 6
    assert kinds.count("reread") == 5 and kinds.count("reread_go") == 5
    assert "retry" not in kinds  # the code-error budget is untouched
    rr = [e for e in ev if e["kind"] == "reread"]
    assert [e["wait_s"] for e in rr] == [3.0, 6.0, 12.0, 24.0, 30.0]  # quick repeats back off
    assert ev[-1]["reason"] == "home"


def test_a_read_end_on_another_map_or_with_stop_pressed_ends_the_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    io_ = FakeIO()
    moved = ReadEndsFirst(io_, "hard_bar: position jump (map change?)", map_after="prontera")
    ev = _retry_run(tmp_path, monkeypatch, moved, None)
    assert len(moved.calls) == 1
    assert [e["kind"] for e in ev].count("reread_refused") == 1
    assert ev[-1]["reason"] != "home"

    io2 = FakeIO()
    stop = tmp_path / "b" / "STOP"
    stop.parent.mkdir(parents=True)
    unread = ReadEndsFirst(io2, "position unread for 30 s", n=3)
    real_sleep = io2.sleep

    def sleep_then_stop(s: float) -> None:
        if unread.calls:  # the person presses Stop during the re-read's wait
            stop.write_text("")
        real_sleep(s)

    monkeypatch.setattr(io2, "sleep", sleep_then_stop)
    opts_dir = tmp_path / "b" / "flowrun"
    opts_dir.mkdir(parents=True)
    monkeypatch.setattr(fr, "DIR", opts_dir)
    monkeypatch.setattr(fp, "default_checker", ok_check)
    d = tmp_path / "b" / "demo"
    d.mkdir()
    fp.play(hunt_prep(tmp_path / "b"), io2, label="r1", stop_file=stop, demo=d, checker=ok_check,
            hunt=fp.HuntCore("r1", stop, run_fn=unread))  # fmt: skip
    ev2 = events(d)
    assert len(unread.calls) == 1 and ev2[-1]["reason"] == "stopped"


# --- roles-not-names.md step 2 (Batt 2026-11-20): the player's role items in the runner's tables
def test_role_items_at_the_defaults_leave_the_runners_tables_as_they_are() -> None:
    from poring_flow import settings as st

    got = fp.role_tables(dh, st.DEFAULTS, name=lambda i: f"item {i}")
    assert got["SLOT_ROLES"] is dh.SLOT_ROLES and got["STOCK_ITEMS"] is dh.STOCK_ITEMS
    assert got["HEAL_ORDER"] is dh.HEAL_ORDER


def test_picked_role_items_are_swapped_in_for_the_block_then_restored() -> None:
    from poring_flow import settings as st

    before = (dh.SLOT_ROLES, dh.STOCK_ITEMS, dh.HEAL_ORDER)
    vals = {**st.DEFAULTS, "swap_item": 1301, "heal_item": 505}
    with fp.role_items(dh, vals):
        assert dh.SLOT_ROLES["opener"].items == (1301,)
        assert "the idle weapon" in dh.SLOT_ROLES["opener"].what
        assert dh.SLOT_ROLES["potion"].items == (505,)
        assert dh.STOCK_ITEMS["potion"] == 505 and dh.STOCK_ITEMS["fly"] == before[1]["fly"]
        assert ("potion", 505) in dh.HEAL_ORDER
        assert dh.SLOT_ROLES["fly"] is before[0]["fly"]  # the other roles are the runner's
    assert before == (dh.SLOT_ROLES, dh.STOCK_ITEMS, dh.HEAL_ORDER)


def test_item_settings_never_reach_the_runners_argv() -> None:
    from poring_flow import settings as st

    base = st.argv(st.DEFAULTS)
    picked = st.argv({**st.DEFAULTS, "swap_item": 1301, "heal_item": 505})
    assert base == picked and not any("item" in a and a != "--loot-items" for a in base)


# --- econ-bag-count.md Amendment 3 (Batt 2026-11-20): the bag counted at the start and the end ----
def _bag(totals: dict[str, int]) -> dict[str, Any]:
    return {"totals": totals, "unread": 0, "full_tabs": [], "seconds": 1.0, "as_found": True}


def test_a_run_counts_the_bag_at_its_start_and_end_and_writes_its_economy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[str] = []
    bags = iter([_bag({"601": 20, "911": 1}), _bag({"601": 18, "911": 6})])

    def census(agent: Any, screen: Any) -> dict[str, Any]:
        calls.append("count")
        return next(bags)

    written: dict[str, Any] = {}

    def economy(start: Any, end: Any, events: Path, label: str) -> Path:
        written.update(start=start["totals"], end=end["totals"], label=label,
                       events=events.exists())  # fmt: skip
        return tmp_path / f"{label}.json"

    monkeypatch.setattr(fp, "bag_economy", economy)
    io_ = FakeIO()
    runner = FakeRunner(io_)
    opts = tmp_path / "flowrun"
    opts.mkdir()
    monkeypatch.setattr(fr, "DIR", opts)
    d = tmp_path / "demo"
    d.mkdir()
    fp.play(hunt_prep(tmp_path), io_, label="r1", stop_file=None, demo=d, checker=ok_check,
            hunt=fp.HuntCore("r1", None, run_fn=runner), census=census)  # fmt: skip
    assert calls == ["count", "count"]
    assert written == {"start": {"601": 20, "911": 1}, "end": {"601": 18, "911": 6},
                       "label": "r1", "events": True}  # fmt: skip


def test_no_end_count_after_a_death_and_a_failed_count_only_warns(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(fp, "bag_economy", lambda *a, **k: (_ for _ in ()).throw(AssertionError))
    calls: list[str] = []

    def broken(agent: Any, screen: Any) -> dict[str, Any]:
        calls.append("count")
        raise SystemExit("bag_count: Alt+E showed no bag")

    io_ = FakeIO()
    opts = tmp_path / "flowrun"
    opts.mkdir()
    monkeypatch.setattr(fr, "DIR", opts)
    d = tmp_path / "demo"
    d.mkdir()
    fp.play(hunt_prep(tmp_path), io_, label="r1", stop_file=None, demo=d, checker=ok_check,
            hunt=fp.HuntCore("r1", None, run_fn=FakeRunner(io_)), census=broken)  # fmt: skip
    assert calls == ["count"]  # the start's failed: no end count, no economy, the Run played
    out = capsys.readouterr().out
    assert "WARNING (the Run plays on): the bag did not count at the start" in out
    assert fp.NO_END_COUNT == ("input_refused", "error", "stopped_by_parent", "dead")


def test_the_bag_count_is_a_run_option_on_by_default() -> None:
    from poring_env import runoptions as ro

    assert ro.DEFAULTS.bag_count is True and ro.DEFAULTS.as_json()["bag_count"] is True
    got, why = ro.parse({"v": 1, "retry_max": 3, "retry_wait_s": 20, "bag_count": False})
    assert why is None and got is not None and got.bag_count is False
    assert (
        ro.parse({"retry_max": 3, "retry_wait_s": 20, "bag_count": "yes"})[1]
        == "bag_count: true or false"
    )
    assert ro.parse({"retry_max": 3, "retry_wait_s": 20})[0] == ro.DEFAULTS  # an older file


# --- Batt 2026-11-20: the story names the monster the HUD names (Seen; the runner unchanged) -----
def test_seen_finds_the_struck_box_with_the_huds_cells_first() -> None:
    import types

    b = types.SimpleNamespace(x0=634.9, y0=385.9, x1=662.3, y1=436.1, score=0.874,
                              cls="monster", species="cookie_xmas")  # fmt: skip
    seen = fp.Seen()
    seen.add([b])  # the detector's boxes: no cells
    assert seen.find([634.9, 385.9, 662.3, 436.1]) == {"name": "cookie_xmas", "conf": 0.874,
                                                       "cells": None}  # fmt: skip
    hud = types.SimpleNamespace(x0=635.0, y0=386.0, x1=662.0, y1=436.0, score=0.874,
                                cls="cookie_xmas")  # fmt: skip
    seen.add([hud], [(2, -3)])  # the HUD's unit: its cell offset
    assert seen.find([634.9, 385.9, 662.3, 436.1])["cells"] == 3  # type: ignore[index]
    assert seen.find([100.0, 100.0, 120.0, 140.0]) is None and seen.find(None) is None
    assert fp.chebyshev((2, -3)) == 3 and fp.chebyshev(None) is None


def test_seen_boxes_records_for_one_hunt_core_and_restores() -> None:
    import operator_hud as oh
    import unit_detector as ud

    before = (oh.units, ud.UnitDetector.detect, ud.GpuDetector.detect)
    seen = fp.Seen()
    with fp.seen_boxes(seen):
        assert oh.units is not before[0] and ud.UnitDetector.detect is not before[1]
    assert (oh.units, ud.UnitDetector.detect, ud.GpuDetector.detect) == before


def test_the_hook_adds_the_monster_to_its_events() -> None:
    import types

    recs: list[dict[str, Any]] = []
    player = types.SimpleNamespace(rec=types.SimpleNamespace(ev=recs.append))
    hook = fp.HuntHook(player, fp.HuntResult())  # type: ignore[arg-type]
    hook.last = types.SimpleNamespace(pos=(77, 240))
    b = types.SimpleNamespace(x0=1057.5, y0=258.4, x1=1092.9, y1=304.1, score=0.91,
                              cls="monster", species="garm_baby")  # fmt: skip
    hook.seen.add([b])
    hook.event({"kind": "engage", "by": "box", "box": [1057.5, 258.4, 1092.9, 304.1],
                "spot": [79, 242]}, 1.0)  # fmt: skip
    hook.event({"kind": "kill", "by": "exp_line"}, 2.0)
    hook.event({"kind": "fight_end", "kills": 1}, 3.0)
    hook.event({"kind": "kill", "by": "exp_line"}, 4.0)
    assert recs[0]["seen"] == {"name": "garm_baby", "conf": 0.91, "cells": 2}
    assert recs[1]["of"] == "garm_baby" and "of" not in recs[3]


# --- roles-not-names.md step 3 (Batt 2026-11-20): the alarm monsters from the trained model ------
SK = {"classes": ["player", "mystcase", "cookie", "garm_baby", "g_gobline_xmas",
                  "knight_of_windstorm"],
      "strikes": ["mystcase", "cookie"],
      "alarm": ["garm_baby", "g_gobline_xmas", "knight_of_windstorm"]}  # fmt: skip


def test_the_players_alarm_pick_replaces_the_models_list_for_one_run() -> None:
    import dungeon_hunt as dh

    before = dh.alarm_classes
    assert dh.alarm_classes(SK) == ("garm_baby", "g_gobline_xmas", "knight_of_windstorm")
    said: list[str] = []
    with fp.role_alarm(dh, {"alarm_monsters": "knight_of_windstorm"}, said.append):
        assert dh.alarm_classes(SK) == ("knight_of_windstorm",)
    assert dh.alarm_classes is before and said == []
    with fp.role_alarm(dh, {"alarm_monsters": ""}, said.append):  # not set: the model's own
        assert dh.alarm_classes is before


def test_a_pick_the_model_cannot_see_or_strikes_warns_and_keeps_the_rest() -> None:
    import dungeon_hunt as dh

    said: list[str] = []
    with fp.role_alarm(dh, {"alarm_monsters": "poring,cookie,garm_baby"}, said.append):
        assert dh.alarm_classes(SK) == ("garm_baby",)
    assert "WARNING (the Run plays on)" in said[0] and "poring, cookie" in said[0]
    said.clear()
    with fp.role_alarm(dh, {"alarm_monsters": "poring"}, said.append):  # none left: its own list
        assert dh.alarm_classes(SK) == ("garm_baby", "g_gobline_xmas", "knight_of_windstorm")
    assert "the model's own alarm list is used" in said[0]
    assert fp.alarm_pick(SK, ("cookie", "garm_baby")) == ("garm_baby",)


def test_the_alarm_monsters_setting_is_a_comma_list_of_model_names() -> None:
    from poring_flow import settings as st

    f = (
        st.BY_NAME["alarm_monsters"]
        if hasattr(st, "BY_NAME")
        else next(x for x in st.FIELDS if x.name == "alarm_monsters")
    )
    assert f.kind == "monsters" and f.optional and f.default == "" and not f.tune
    assert st.monster_names("") == () and st.norm(f, " garm_baby , knight_of_windstorm ") == (
        "garm_baby,knight_of_windstorm"
    )
    assert st.problem_of(f, "Garm Baby") is not None and st.problem_of(f, "a,a") is not None
    assert st.problem_of(f, ",".join(f"m{i}" for i in range(9))) is not None  # at most 8
    assert "alarm_monsters" not in " ".join(st.argv({"alarm_monsters": "garm_baby",
                                                    "garm_fly": True}))  # fmt: skip


# --- goblin-alarm-1080.md rule A: the near-her alarm rule, the live player's patch --------------
def _abox(cx: float, cy: float, score: float, cls: str = "g_gobline_xmas") -> Any:
    import unit_detector as ud

    return ud.Box(cx - 20, cy - 30, cx + 20, cy + 30, score, cls)


def test_the_near_alarm_rule_is_off_by_default_and_never_a_runner_flag() -> None:
    from poring_flow import settings as st

    f, g = st.BY_NAME["alarm_near_px"], st.BY_NAME["alarm_near_score"]
    assert f.player and g.player and not f.tune and not g.tune
    assert f.default == 0.0 and g.default == 0.85 and f.unit == "px"
    vals = {**st.flag_defaults(), "alarm_near_px": 60.0}
    assert not [x for x in st.argv(vals) if "near" in x]
    saved = dh.alarm_seen
    with fp.near_alarm(dh, st.flag_defaults()):  # 0 px: the runner's own rule
        assert dh.alarm_seen is saved
    with fp.near_alarm(dh, {**vals, "garm_fly": False}):  # the alarm off: not in use
        assert dh.alarm_seen is saved


def test_the_near_alarm_rule_drops_unsure_boxes_beside_her_for_one_run() -> None:
    from poring_flow import settings as st

    her_x, her_y = dh.FOOT_PX[0], dh.FOOT_PX[1] - dh.BODY_UP
    near = _abox(her_x + 10, her_y + 20, 0.78)  # her fight's neighbour, under 0.85
    sure = _abox(her_x - 15, her_y, 0.91, "garm_baby")
    far = _abox(her_x + 300, her_y - 100, 0.40)
    vals = {**st.flag_defaults(), "garm_fly": True, "alarm_near_px": 60.0}
    saved = dh.alarm_seen
    with fp.near_alarm(dh, vals):
        assert dh.alarm_seen is not saved
        # the runner's call shape: (grab time, its alarm boxes), now, streak / need / solo
        assert dh.alarm_seen((5.0, [near]), 5.0, streak=3, need=2, solo=0.7) is None
        assert dh.alarm_seen((5.0, [near, far]), 5.0, streak=2, need=2, solo=0.7) is far
        assert dh.alarm_seen((5.0, [near, sure]), 5.0, streak=1, need=2, solo=0.7) is sure
        assert dh.alarm_seen((5.0, [far]), 5.0, streak=1, need=2, solo=0.7) is None  # 0.4 < 0.7
    assert dh.alarm_seen is saved  # restored
    assert saved((5.0, [near]), 5.0, streak=3, need=2, solo=0.7) is near  # today's rule
    with fp.near_alarm(dh, {**vals, "alarm_near_score": 0.75}):
        assert dh.alarm_seen((5.0, [near]), 5.0, streak=3, need=2, solo=0.7) is near


def test_near_keeps_is_the_distance_and_the_sure_score() -> None:
    her = (641.0, 336.0)
    assert not fp.near_keeps(_abox(641 + 60, 336, 0.5), 60.0, 0.85, her)  # at 60 px: near
    assert fp.near_keeps(_abox(641 + 61, 336, 0.5), 60.0, 0.85, her)
    assert fp.near_keeps(_abox(641, 336, 0.85), 60.0, 0.85, her)  # sure enough


def test_the_hunt_core_applies_the_near_alarm_rule() -> None:
    src = inspect.getsource(fp.HuntCore.play)
    assert "near_alarm(dh, plan.vals)" in src
