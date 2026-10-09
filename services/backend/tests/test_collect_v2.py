"""scripts/collect_v2.py (collect@1, labels-v2-plan 7.6a) on SYNTHETIC grids, KB snippets and
packet events built here -- never a client GAT or rAthena data (CLAUDE.md rule 4). No client, no
input: the live driver's ORDER is tested over injected fakes."""

import importlib.util
import json
import struct
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import numpy as np
import pytest

SCRIPTS = Path(__file__).resolve().parents[3] / "scripts"


@pytest.fixture(scope="module")
def cv() -> ModuleType:
    sys.path.insert(0, str(SCRIPTS))
    spec = importlib.util.spec_from_file_location("collect_v2", SCRIPTS / "collect_v2.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["collect_v2"] = module
    spec.loader.exec_module(module)
    return module


def grid(w: int = 80, h: int = 80) -> np.ndarray:
    g = np.ones((h, w), dtype=bool)
    g[0, :] = g[-1, :] = g[:, 0] = g[:, -1] = False
    return g


def mapdata(cv: ModuleType, **kw: Any) -> Any:
    base: dict[str, Any] = {
        "name": "syn_3", "walkable": grid(),
        "warps": [{"x": 40, "y": 40, "span_x": 2, "span_y": 1, "to_map": "syn_4"}],
        "npcs": [(15, 15)],
        "spawns": [{"id": 1002, "amount": 10, "delay1_ms": 0}, {"id": 1184, "amount": 5},
                   {"id": 1002, "amount": 3}],
        "mapflags": ["nobranch", "noteleport"],
    }  # fmt: skip
    base.update(kw)
    return cv.MapData(**base)


# --- the spot rules ------------------------------------------------------------------------------


def test_spots_stay_outside_warp_areas_and_away_from_every_npc(cv: ModuleType) -> None:
    md = mapdata(cv)
    cands = set(cv.spot_candidates(md))
    assert cands
    for c in cands:
        assert cv.area_distance(c, md.warps[0]) > 0  # never inside the trigger area
        assert cv.cheb(c, (15, 15)) >= cv.NPC_MIN_CELLS
        assert cv.OPEN_RADIUS <= c[0] < 80 - cv.OPEN_RADIUS
    assert (40, 40) not in cands and (42, 41) not in cands and (43, 41) in cands
    assert (22, 15) not in cands and (23, 15) in cands  # Chebyshev 7 refused, 8 allowed


def test_a_spot_needs_an_open_view(cv: ModuleType) -> None:
    g = np.zeros((80, 80), dtype=bool)
    g[40, 10:70] = True  # a one-cell corridor: 15 of 225 cells open around any of its cells
    assert cv.spot_candidates(mapdata(cv, walkable=g, warps=[], npcs=[])) == []


def test_spots_are_spaced_and_seeded(cv: ModuleType) -> None:
    md = mapdata(cv)
    cands = cv.spot_candidates(md)
    a = cv.pick_spots(cands, 6, cv.rng_for("syn_3", 7))
    b = cv.pick_spots(cands, 6, cv.rng_for("syn_3", 7))
    c = cv.pick_spots(cands, 6, cv.rng_for("syn_3", 8))
    assert a == b and a != c and len(a) == 6
    assert all(cv.cheb(p, q) >= cv.SPOT_SPACING for i, p in enumerate(a) for q in a[i + 1 :])


def test_the_plan_is_deterministic_by_seed(cv: ModuleType) -> None:
    md = mapdata(cv)
    p1, p2 = cv.make_plan(md, 20261010), cv.make_plan(md, 20261010)
    p3 = cv.make_plan(md, 20261011)
    assert p1 == p2 and p1["plan_sha"] == p2["plan_sha"]
    assert p3["spots"] != p1["spots"] and p3["plan_sha"] != p1["plan_sha"]


def test_portal_cells_sit_beside_the_area_outside_it(cv: ModuleType) -> None:
    md = mapdata(cv)
    (pc,) = cv.portal_cells(md, cv.rng_for("syn_3", 1))
    lo, hi = cv.PORTAL_RING
    assert pc["warp"] == [40, 40] and pc["to_map"] == "syn_4"
    assert lo <= cv.area_distance(pc["cell"], md.warps[0]) <= hi
    g = np.zeros((80, 80), dtype=bool)
    g[38:43, 37:44] = True  # only the area and a 1-cell rim: no cell 3-5 away
    assert cv.portal_cells(mapdata(cv, walkable=g), cv.rng_for("syn_3", 1))[0]["cell"] is None


def test_blocks_take_the_map_own_species_in_kb_order(cv: ModuleType) -> None:
    md = mapdata(cv)
    p = cv.make_plan(md, 1, k=3)
    assert [b["species"] for b in p["blocks"]] == [1002, 1184]  # 1184 kept: collection is data
    assert [b["spot"] for b in p["blocks"]] == [0, 1]
    assert all(b["count"] == cv.DEFAULT_COUNT for b in p["blocks"])
    assert p["spawn_range"] == 4  # int(sqrt(8)) + 2, atcommand.cpp:2393
    with pytest.raises(SystemExit, match="do not spawn"):
        cv.make_plan(md, 1, blocks=[1261])
    assert [b["species"] for b in cv.make_plan(md, 1, blocks=[1184])["blocks"]] == [1184]
    two = cv.make_plan(md, 1, k=3, repeats=2)  # rounds: each species again, the spots rotate on
    assert [(b["species"], b["spot"]) for b in two["blocks"]] == [
        (1002, 0), (1184, 1), (1002, 2), (1184, 0)]  # fmt: skip
    assert two["line_check"]["violations"] == []


def test_a_spot_without_room_takes_no_block(cv: ModuleType) -> None:
    md = mapdata(cv)
    g = md.walkable.copy()
    assert cv.block_room(mapdata(cv, walkable=g), (30, 30), 8)
    g2 = np.zeros_like(g)
    g2[30, 30] = True
    assert not cv.block_room(mapdata(cv, walkable=g2), (30, 30), 8)


def test_warp_mapflag_check(cv: ModuleType) -> None:
    ok = cv.warp_check(["nobranch", "nomemo", "nopenalty", "noteleport"])
    assert ok["ok"] and ok["blocking"] == []
    assert ok["not_checked_by_warp"] == ["nobranch", "nomemo", "nopenalty", "noteleport"]
    bad = cv.warp_check(["noteleport", "nowarpto"])
    assert not bad["ok"] and bad["blocking"] == ["nowarpto"]


# --- the typing guard's repeat rule --------------------------------------------------------------


def test_check_lines_follows_the_guard_count(cv: ModuleType) -> None:
    assert cv.check_lines(["@a", "@b", "@a", "@b"])["violations"] == []
    got = cv.check_lines(["@a", "@a", "@a", "@b"])
    assert got["violations"] == [{"index": 2, "line": "@a", "n": 3}]
    assert got["max_identical_in_a_row"] == 3
    # the guard's state before the run counts: a 2nd and 3rd in a row across processes
    seeded = cv.check_lines(["@a", "@b"], last={"text": "@a", "count": 2})
    assert seeded["violations"] == [{"index": 0, "line": "@a", "n": 3}]
    assert cv.repeat_count({"text": "@x", "count": 1}, "@x") == 2
    assert cv.repeat_count(None, "@x") == 1


def test_the_plan_never_repeats_a_line_and_skips_a_warp_in_place(cv: ModuleType) -> None:
    md = mapdata(cv)
    for k in (1, 2, 6):
        p = cv.make_plan(md, 3, k=k)
        lines = [x["line"] for x in p["lines"]]
        check = p["line_check"]
        assert check["violations"] == [] and check["max_identical_in_a_row"] == 1
        assert all(a != b for a, b in zip(lines, lines[1:], strict=False))
    one = cv.make_plan(md, 3, k=1, portals=False)
    assert [x["line"].split()[0] for x in one["lines"]] == [
        "@warp", "@monster", "@killmonster2", "@monster", "@killmonster2"]  # fmt: skip


def test_dwells_come_first_and_killmonster2_only_ends_a_block(cv: ModuleType) -> None:
    p = cv.make_plan(mapdata(cv), 5, k=4)
    phases = [x["phase"] for x in p["lines"]]
    assert phases == sorted(phases, key=["dwell", "block", "portal"].index)
    lines = [x["line"] for x in p["lines"]]
    assert lines[0].startswith("@warp")
    for i, line in enumerate(lines):
        if line == "@killmonster2":
            assert lines[i - 1].startswith("@monster")


# --- fail closed on the KB -----------------------------------------------------------------------


def write_gat(path: Path, walkable: np.ndarray) -> None:
    h, w = walkable.shape
    tile = struct.Struct("<4fHH")
    body = b"".join(tile.pack(0.0, 0.0, 0.0, 0.0, 0 if walkable[y, x] else 1, 0)
                    for y in range(h) for x in range(w))  # fmt: skip
    path.write_bytes(struct.pack("<4sBBII", b"GRAT", 1, 2, w, h) + body)


def kb(tmp_path: Path, *, warps: bool = True, complete: bool = True, fw: bool = True,
       gat: bool = True) -> tuple[Path, Path]:  # fmt: skip
    k, g = tmp_path / "kb", tmp_path / "gat"
    k.mkdir()
    g.mkdir()
    route = {"warps": {"syn_3": []} if warps else {"other": []},
             "npcs": {"grp": [{"map": "syn_3", "x": 50, "y": 50}]}}  # fmt: skip
    (k / "route.json").write_text(json.dumps(route))
    (k / "npc_cells.json").write_text(json.dumps({"maps": {"syn_3": {
        "complete": complete, "npcs": [{"x": 20, "y": 20, "drawn": False}]}}}))  # fmt: skip
    maps = {"syn_3": {"spawns": [{"id": 1002, "amount": 4}],
                      "mapflags": [{"flag": "noteleport"}]}} if fw else {}  # fmt: skip
    (k / "first_workflow.json").write_text(json.dumps({"maps": maps}))
    if gat:
        write_gat(g / "syn_3.gat", grid(40, 40))
    return k, g


def test_load_map_reads_every_npc_and_the_gat(cv: ModuleType, tmp_path: Path) -> None:
    k, g = kb(tmp_path)
    md = cv.load_map("syn_3", k, [g])
    assert md.walkable.shape == (40, 40) and md.walkable[5, 5] and not md.walkable[0, 0]
    assert md.npcs == [(20, 20), (50, 50)]  # npc_cells (undrawn too) + route.json's groups
    assert md.warps == [] and md.mapflags == ["noteleport"] and not md.server_checked


@pytest.mark.parametrize(("kw", "match"), [
    ({"warps": False}, "no L3 warp list"), ({"complete": False}, "not declared"),
    ({"fw": False}, "first_workflow"), ({"gat": False}, "no GAT"),
])  # fmt: skip
def test_load_map_fails_closed(cv: ModuleType, tmp_path: Path, kw: dict[str, bool],
                               match: str) -> None:  # fmt: skip
    k, g = kb(tmp_path, **kw)
    with pytest.raises(SystemExit, match=match):
        cv.load_map("syn_3", k, [g])


def test_server_walkability_closes_the_last_row_and_column(cv: ModuleType) -> None:
    cells = bytes([0, 0, 0, 1, 0, 0, 0, 0, 5, 0, 0, 0])  # 4 x 3, types 1 and 5 not walkable
    ok = cv.server_walkable(cells, 4, 3, frozenset({1, 5}))
    assert ok.tolist() == [[True, True, True, False], [True, True, True, False],
                           [False, False, False, False]]  # fmt: skip


# --- immunity: a toggle, tied to the GM's login ---------------------------------------------------

MARK = {"char_id": 1, "last_login": 100, "logincount": 7}


def test_immunity_must_be_confirmed_for_the_current_login(cv: ModuleType) -> None:
    assert not cv.immunity_ok(None, MARK)[0]
    sent = {"marker": MARK, "state": "sent", "shot": "s.png"}
    assert not cv.immunity_ok(sent, MARK)[0]
    conf = {**sent, "state": "confirmed"}
    assert cv.immunity_ok(conf, MARK)[0]
    relog = {**MARK, "last_login": 200}
    ok, why = cv.immunity_ok(conf, relog)
    assert not ok and "logged in again" in why


def test_immune_on_never_toggles_a_confirmed_flag_off(cv: ModuleType) -> None:
    conf = {"marker": MARK, "state": "confirmed"}
    assert "turn it OFF" in cv.immune_on_refusal(conf, MARK, again=False)
    assert "turn it OFF" in cv.immune_on_refusal(conf, MARK, again=True)
    sent = {"marker": MARK, "state": "sent", "shot": "s.png"}
    assert cv.immune_on_refusal(sent, MARK, again=False) is not None
    assert cv.immune_on_refusal(sent, MARK, again=True) is None  # a person read OFF on the shot
    assert cv.immune_on_refusal(None, MARK, again=False) is None
    assert cv.immune_on_refusal(conf, {**MARK, "logincount": 8}, again=False) is None


# --- the live driver's order, over fakes ----------------------------------------------------------


class Fake:
    def __init__(self, plan: dict[str, Any], *, refuse: str | None = None,
                 vitals: list[str | None] | None = None, stop_after: float | None = None,
                 live_block: Path | None = None) -> None:  # fmt: skip
        self.t, self.sent, self.notes = 0.0, [], []
        self.refuse, self.vit, self.stop_after = refuse, list(vitals or []), stop_after
        self.live_block = live_block
        self.plan = plan

    def send(self, line: str) -> bool:
        if self.refuse and line.startswith(self.refuse):
            return False
        self.sent.append(line)
        return True

    def idle(self, s: float) -> None:
        self.t += s

    def vitals(self) -> str | None:
        return self.vit.pop(0) if self.vit else None

    def note(self, event: str, **f: Any) -> None:
        self.notes.append({"event": event, **f})

    def stopped(self) -> str | None:
        return "max_minutes" if self.stop_after is not None and self.t >= self.stop_after else None

    def driver(self, cv: ModuleType) -> Any:
        return cv.Driver(self.plan, send=self.send, idle=self.idle, vitals=self.vitals,
                         note=self.note, stopped=self.stopped, ns=lambda: int(self.t * 1e9),
                         clock=lambda: self.t, live_block=self.live_block)  # fmt: skip


def small_plan(cv: ModuleType, **kw: Any) -> dict[str, Any]:
    return cv.make_plan(mapdata(cv), 9, k=2, dwell_s=10, block_s=20, portal_s=5, **kw)


def test_the_session_types_exactly_the_planned_lines(cv: ModuleType, tmp_path: Path) -> None:
    p = small_plan(cv)
    f = Fake(p, live_block=tmp_path / "live.json")
    assert f.driver(cv).run(portals=True) == "done"
    assert f.sent == [x["line"] for x in p["lines"]]
    assert "@killmonster2" not in f.sent[:3]  # never at the start: natural dwells first
    events = [n["event"] for n in f.notes]
    assert events.count("dwell_start") == 2 + 1  # two spots, one portal pass
    assert not (tmp_path / "live.json").exists()


def test_the_deadline_mid_block_kills_it_first(cv: ModuleType, tmp_path: Path) -> None:
    p = small_plan(cv)
    f = Fake(p, stop_after=40.0, live_block=tmp_path / "live.json")  # inside the first block
    assert f.driver(cv).run(portals=True) == "max_minutes"
    assert f.sent[-2].startswith("@monster") and f.sent[-1] == "@killmonster2"
    assert not (tmp_path / "live.json").exists()


def test_a_warp_not_typed_stops_the_run(cv: ModuleType) -> None:
    f = Fake(small_plan(cv), refuse="@warp")
    assert f.driver(cv).run(portals=False) == "warp_not_typed"
    assert f.sent == []


def test_a_vitals_need_after_the_start_is_a_condition_failure(cv: ModuleType) -> None:
    f = Fake(small_plan(cv), vitals=["heal", None, "revive"])
    assert f.driver(cv).run(portals=False) == "immunity_condition_failed"
    assert f.sent[0] == "@heal"  # the start condition: healed, the run goes on
    assert f.sent[-2:] == ["@alive", "@heal"]
    assert [n["start"] for n in f.notes if n["event"] == "vitals"] == [True, False]


def test_a_crashed_run_block_is_removed_first(cv: ModuleType, tmp_path: Path) -> None:
    live = tmp_path / "live.json"
    live.write_text(json.dumps({"map": "syn_3", "block": {}}))
    f = Fake(small_plan(cv), live_block=live)
    assert f.driver(cv).run(portals=False) == "done"
    assert f.sent[0] == "@killmonster2 syn_3" and not live.exists()


# --- the offline judge ---------------------------------------------------------------------------

S = 1_000_000_000


def timeline() -> list[dict[str, Any]]:
    plan = {"spawn_range": 4, "plan_sha": "abc"}
    return [
        {"event": "run_start", "t_mono_ns": 0, "plan": plan},
        {"event": "warp", "map": "syn_3", "cell": [30, 30], "gm_line": "@warp syn_3 30 30",
         "t_sent_ns": 1 * S, "t_mono_ns": 2 * S, "ok": True, "phase": "dwell", "ref": 0},
        {"event": "dwell_start", "t_mono_ns": 3 * S, "phase": "dwell", "ref": 0},
        {"event": "dwell_end", "t_mono_ns": 20 * S, "phase": "dwell", "ref": 0},
        {"event": "spawned", "map": "syn_3", "cell": [30, 30], "gm_line": "@monster 1002 2",
         "species": 1002, "count": 2, "t_sent_ns": 21 * S, "t_mono_ns": 22 * S, "ok": True,
         "phase": "block", "ref": 0},
        {"event": "killed", "gm_line": "@killmonster2", "t_sent_ns": 40 * S, "t_mono_ns": 41 * S,
         "ok": True, "phase": "block", "ref": 0},
        {"event": "run_end", "t_mono_ns": 42 * S, "reason": "done"},
    ]  # fmt: skip


def packets() -> list[dict[str, Any]]:
    def chat(t: float, text: str) -> dict[str, Any]:
        return {"type": "chat", "dir": "cs", "kind": "public", "text": text,
                "t_mono_ns": int(t * S), "validation_account": True,
                "gm_command": True}  # fmt: skip

    def mob(t: float, gid: int, job: int, kind: str, x: int, y: int) -> dict[str, Any]:
        return {"type": "entity_appear", "kind": kind, "gid": gid, "job": job, "objtype": 5,
                "x": x, "y": y, "t_mono_ns": int(t * S)}  # fmt: skip

    return [
        chat(1.1, "@warp syn_3 30 30"),
        {"type": "map_change", "map": "syn_3.gat", "x": 30, "y": 30, "t_mono_ns": int(1.3 * S)},
        mob(5, 900, 1063, "stand", 35, 33), mob(8, 900, 1063, "move", 36, 33),
        chat(21.1, "@monster 1002 2"),
        mob(21.3, 901, 1002, "new", 31, 29), mob(21.3, 902, 1002, "new", 28, 32),
        mob(21.4, 903, 1002, "new", 70, 70),  # a natural respawn far away: not the block's
        chat(40.1, "@killmonster2"),
        {"type": "entity_vanish", "gid": 901, "reason": 1, "t_mono_ns": int(40.3 * S)},
        {"type": "entity_vanish", "gid": 902, "reason": 1, "t_mono_ns": int(40.3 * S)},
    ]  # fmt: skip


def test_the_judge_passes_a_clean_session(cv: ModuleType) -> None:
    got = cv.judge(packets(), timeline())
    assert got["pass"] and got["protocol_ok"]
    assert got["sensor"] == {"gm_lines_typed": 3, "seen_client_to_server": 3, "matched": 3,
                             "pass": True}  # fmt: skip
    assert got["warps"]["landed_as_planned"] == 1
    assert got["blocks"] == [{"ref": 0, "species": 1002, "count": 2, "appeared": 2,
                              "killed_at_end": 2, "ok": True}]  # fmt: skip
    assert got["immunity"] == {"acts_on_gm": 0, "monster_moves": 1, "pass": True}
    assert got["dwells"] == {"n": 1, "monster_sightings_by_job": {1063: 1}}


@pytest.mark.parametrize("bad", [
    {"type": "attack_request", "target_gid": 901, "validation_account": True},
    {"type": "npc_contact", "npc_gid": 5, "validation_account": True},
    {"type": "pickup_request", "floor_id": 3, "validation_account": True},
    {"type": "self_move_request", "x": 1, "y": 1, "validation_account": True},
    {"type": "act", "src_gid": 2000002, "target_gid": 901, "kind": "normal"},
    {"type": "act", "src_gid": 2000002, "target_gid": 77, "kind": "pickup"},
])  # fmt: skip
def test_any_request_or_gm_act_fails_safety(cv: ModuleType, bad: dict[str, Any]) -> None:
    got = cv.judge([*packets(), {**bad, "t_mono_ns": 10 * S}], timeline())
    assert not got["safety"]["pass"] and not got["pass"]


def test_an_act_on_the_gm_fails_the_immunity(cv: ModuleType) -> None:
    hit = {"type": "act", "src_gid": 900, "target_gid": 2000002, "kind": "normal",
           "t_mono_ns": 9 * S}  # fmt: skip
    got = cv.judge([*packets(), hit], timeline())
    assert got["safety"]["pass"] and not got["immunity"]["pass"] and not got["pass"]


def test_a_blind_sensor_is_not_a_pass(cv: ModuleType) -> None:
    # no client -> server line seen: a zero from a sensor that saw nothing is not evidence
    blind = [e for e in packets() if e.get("dir") != "cs"]
    got = cv.judge(blind, timeline())
    assert got["safety"]["pass"] and not got["sensor"]["pass"] and not got["pass"]


def test_a_warp_that_landed_elsewhere_is_reported(cv: ModuleType) -> None:
    moved = [({**e, "x": 33} if e.get("type") == "map_change" else e) for e in packets()]
    got = cv.judge(moved, timeline())
    assert got["pass"] and not got["protocol_ok"]
    assert got["warps"]["off"][0]["landed"] == ["syn_3", 33, 30]


# --- preflight: no input, fail closed ------------------------------------------------------------


def test_preflight_fails_closed_then_passes(cv: ModuleType, monkeypatch: pytest.MonkeyPatch,
                                            tmp_path: Path) -> None:  # fmt: skip
    import gm_state
    import ui_gate

    p = cv.make_plan(mapdata(cv), 1)

    def console_path() -> None:
        raise ui_gate.UiUnknown("ui gate: the s2 template set is not proven (no valid proof.json)")

    def no_gm_set() -> None:
        raise gm_state.r.Stop("gm_state: the s2 template set is not proven (gm_levels)")

    monkeypatch.setattr(ui_gate, "_require_ready", console_path)
    monkeypatch.setattr(gm_state, "require_ready", no_gm_set)
    monkeypatch.setattr(cv, "IMMUNE", tmp_path / "immune.json")
    monkeypatch.setattr(cv, "gm_marker", lambda: MARK)
    monkeypatch.setattr(cv, "guard_state", lambda: None)
    monkeypatch.setattr(cv, "guard_limit", lambda: 3)
    out = cv.preflight(p, 55.0)
    assert not out["pass"]
    assert "not proven" in out["checks"]["ui_gate"]
    assert "no immune-on record" in out["checks"]["immunity"]
    assert out["checks"]["gm_state_template"] != "ok" and out["checks"]["typing_guard"] == "ok"
    # the guard's state: the plan's first line typed twice already -> a 3rd would be skipped
    monkeypatch.setattr(cv, "guard_state", lambda: {"text": p["lines"][0]["line"], "count": 2})
    assert "would be #3" in cv.preflight(p, 55.0)["checks"]["typing_guard"]
    monkeypatch.setattr(cv, "guard_state", lambda: None)
    monkeypatch.setattr(ui_gate, "_require_ready", lambda: None)
    monkeypatch.setattr(gm_state, "require_ready", lambda: "s2")
    cv.write_json(tmp_path / "immune.json", {"marker": MARK, "state": "confirmed"})
    ok = cv.preflight(p, 1.0)
    assert ok["pass"] and ok["duration"].startswith("cut at 1.0 min")
