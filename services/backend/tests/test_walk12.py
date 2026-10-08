"""scripts/walk12.py (walk@12, demonstrations 3.21): walk@11 unchanged + Batt's three decisions.
1. the work zone: no click point over a UI window (route_preview.UI_WINDOWS + 12 px);
2. a TALK read blocks every point of its picked cell;
3. the harness finishes its session (t1 + packets) on a Stop, an exception or an interrupt, and
   exits nonzero.
Plus: walk@11's module is untouched, and walk@12's walk_route / run ARE walk@11's code.
The fakes are walk@6/7's (test_walk6.py, test_walk7.py), as in test_walk11.py."""

from __future__ import annotations

import builtins
import contextlib
import gzip
import importlib.util
import json
import sys
import types
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

import numpy as np
import pytest

HERE = Path(__file__).resolve().parent
SCRIPTS = HERE.parents[2] / "scripts"
BASIC_INFO_CLICK = (52.9, 295.8)  # walk@11 indoor CROWD route 53: the Basic Information icon grid


def _load(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def mods() -> tuple[ModuleType, ModuleType, ModuleType, ModuleType]:
    sys.path.insert(0, str(SCRIPTS))
    for name in ("walk5", "walk6", "reloc2", "where_fix", "walk7", "walk8", "walk9", "walk10",
                 "walk11", "work_zone", "walk12"):  # fmt: skip
        _load(name, SCRIPTS / f"{name}.py")
    f = _load("fakes_walk6", HERE / "test_walk6.py")
    t7 = _load("fakes_walk7", HERE / "test_walk7.py")
    return sys.modules["walk12"], sys.modules["walk11"], f, t7


TIERS: dict[tuple[int, int], str] = {}


@pytest.fixture
def fake(mods: Any, monkeypatch: pytest.MonkeyPatch) -> Any:
    w12, w11, f, t7 = mods
    for mod in (w12, w11, w12.w6, w12.w5):
        monkeypatch.setattr(mod.time, "sleep", lambda s: None)
    monkeypatch.setattr(w12.r, "game_region", lambda: (f.GX, f.GY, 1280, 720))
    monkeypatch.setattr(w12.r, "desktop", lambda: (1440, 900))
    monkeypatch.setattr(w12.r, "ns", lambda: 0)
    TIERS.clear()

    def points(w: Any, end: tuple[int, int], tier: str) -> list[tuple[float, float]]:
        want = TIERS.get(end, "A")
        if want != tier:
            return []
        nb = np.array([(end[0] + dx, end[1] + dy) for dx, dy in w12.rr.NB9], dtype=float)
        return w12.rr.in_cell_points(w.project(nb))  # the centre, then 4 alternates in the cell

    for mod in (w12, w11):
        monkeypatch.setattr(mod, "moved", lambda a, b: (True, 1.0))  # the fake floor: no scroll
        monkeypatch.setattr(mod, "unit_check", lambda pr, w, u, v: (True, {"fake": 1}))  # no units
        monkeypatch.setattr(mod, "observe_frame", lambda frame, w, t: None)
    monkeypatch.setattr(w12, "tier_points", points)
    monkeypatch.setattr(w11, "pick_points", lambda w, end: (points(w, end, "A"), "A"))
    return w12, w11, f, t7


class Ws:
    def send(self, text: str) -> None:
        json.loads(text)


def sim(fake: Any, true: tuple[int, int], prober_mod: Any = None, **kw: Any) -> Any:
    w12, w11, f, t7 = fake
    s = t7.World(f, w12, true, **kw)
    s.client.ws = Ws()
    s.pr = (prober_mod or w12).Prober9(s.client, s.client, s.pr.refs)
    return s


def ring() -> np.ndarray:
    yy, xx = np.mgrid[0:64, 0:64]
    return (np.hypot(xx - 36, yy - 42) >= 9) & (np.hypot(xx - 36, yy - 42) <= 12)


def fix_to_truth(s: Any) -> Any:
    def fix(agent: Any, screen: Any, w: Any, mask: Any, band: Any) -> dict[str, Any]:
        w.position = s.client.true
        return {"ok": True, "to": list(s.client.true)}

    return fix


BAND = (100, 60, 1180, 680)


# --- walk@11 stays walk@11 ---------------------------------------------------------------------
def names(code: types.CodeType) -> set[str]:
    out = set(code.co_names)
    for c in code.co_consts:
        if isinstance(c, types.CodeType):
            out |= names(c)
    return out


def test_walk11_is_untouched_and_walk12_reuses_its_code(mods: Any) -> None:
    w12, w11, _, _ = mods
    assert w11.WALK8_RULE == "walk@11" and w12.WALK8_RULE == "walk@12"
    assert w11.walk_route.__globals__ is vars(w11) and w11.run.__globals__ is vars(w11)
    assert vars(w11)["click_step"].__module__ == "walk11"  # walk@11 still calls its own
    assert w11.DemoLog is sys.modules["poring_env.demo"].DemoLog
    assert w12.walk_route.__code__ is w11.walk_route.__code__  # the SAME code, not a copy
    assert w12.run11.__code__ is w11.run.__code__
    assert w12.walk_route.__defaults__ == w11.walk_route.__defaults__
    g = w12.walk_route.__globals__
    assert g is vars(w12) and g["click_step"] is w12.click_step and g["DemoLog"] is w12.SessionLog
    assert g["UNITS"] is w11.UNITS  # one unit memory and detector, read by walk@11's gate
    assert "pick_points" not in g  # walk@12 picks through zone_points only


def test_every_name_walk11s_code_uses_resolves_in_walk12(mods: Any) -> None:
    w12, w11, _, _ = mods
    for fn in (w11.walk_route, w11.run):
        used = {n for n in names(fn.__code__) if n in vars(w11)}  # walk@11's own globals
        missing = sorted(n for n in used if n not in vars(w12) and not hasattr(builtins, n))
        assert not missing, (fn.__name__, missing)


# --- decision 1: the work zone ---------------------------------------------------------------
def test_the_observed_ui_click_is_outside_the_work_zone(mods: Any) -> None:
    wz = sys.modules["work_zone"]
    assert len(wz.WINDOW_NAMES) == len(wz.UI_WINDOWS)
    assert wz.MARGIN_PX == 12.0
    assert wz.ui_window_at(*BASIC_INFO_CLICK) == "basic_info"
    assert not wz.in_work_zone(*BASIC_INFO_CLICK)


def test_a_point_just_outside_the_margin_is_allowed(mods: Any) -> None:
    wz = sys.modules["work_zone"]
    x1, y1 = 220, 326  # the Basic Information window's right and bottom edges
    assert not wz.in_work_zone(x1 + 12.0, 200.0)  # on the grown edge: inside
    assert wz.in_work_zone(x1 + 12.5, 200.0)
    assert not wz.in_work_zone(100.0, y1 + 12.0)
    assert wz.in_work_zone(100.0, y1 + 12.5)
    assert wz.in_work_zone(640.0, 360.0)  # our own feet
    assert not wz.in_work_zone(-1.0, 360.0) and not wz.in_work_zone(640.0, 720.0)
    assert not wz.in_work_zone(300.0, 525.0)  # the chat window's top margin (532 - 12)


def test_zone_points_refuse_ui_pixels_and_keep_walk11s_order_otherwise(
    mods: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    w12, _, _, _ = mods
    w = SimpleNamespace(position=(10, 10))
    outside = [(400.0 + 10 * i, 400.0) for i in range(8)]
    pts = {"A": [BASIC_INFO_CLICK, *outside], "B": []}
    monkeypatch.setattr(w12, "tier_points", lambda w, end, tier: list(pts[tier]))
    got, tier, refused = w12.zone_points(w, (12, 10))
    assert tier == "A" and BASIC_INFO_CLICK not in got and got == outside[:5]
    assert refused == [[52.9, 295.8]]
    pts["A"] = list(outside)  # nothing near a window: exactly the first five, no refusals
    assert w12.zone_points(w, (12, 10)) == (outside[:5], "A", [])
    pts["A"], pts["B"] = [BASIC_INFO_CLICK], [(205.0, 290.0), (600.0, 300.0)]
    got, tier, refused = w12.zone_points(w, (12, 10))  # tier A only under a window: tier B
    assert (got, tier) == ([(600.0, 300.0)], "B") and len(refused) == 2
    pts["B"] = [(205.0, 290.0)]
    assert w12.zone_points(w, (12, 10))[:2] == ([], "none")


def test_tier_points_are_walk11s_with_more_alternates(
    mods: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    w12, w11, _, _ = mods
    calls: list[dict[str, Any]] = []

    def safe_points(camera: Any, gat: Any, origin: Any, rel: Any, **kw: Any) -> Any:
        calls.append({"rel": rel, **kw})
        k = kw.get("k", 5)
        return [(500.0 + i, 400.0) for i in range(k)] if kw["margin"] == 6.0 else []

    monkeypatch.setattr(w12.picking, "safe_points", safe_points)
    w = SimpleNamespace(position=(10, 10), camera=None, gat=None)
    assert w12.zone_points(w, (12, 11))[:2] == w11.pick_points(w, (12, 11))
    assert calls[0] == {"rel": (2, 1), "margin": 6.0, "grid": 2.0, "k": w12.SEARCH_K}


def test_a_cell_whose_points_all_lie_under_a_window_is_never_hovered(
    fake: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    w12, _, _, _ = fake
    s = sim(fake, (10, 18))
    monkeypatch.setattr(w12, "tier_points", lambda w, end, tier: [BASIC_INFO_CLICK])
    moves: list[Any] = []
    real_move = s.client.move
    s.client.move = lambda x, y: (moves.append((x, y)), real_move(x, y))
    step = w12.click_step(s.pr, s.w, (12, 18))
    assert step["outcome"] == "no_safe_point" and not step["clicked"]
    assert step["ui_refused"] == [[52.9, 295.8]] and step["target"] == [] and not moves


def test_a_route_never_clicks_inside_a_ui_window(fake: Any) -> None:
    """The goal projects into the Basic Information window from the start (cells are 30 x 20 px in
    the fake): its pixels are refused there, the route walks nearer points first, and every click
    lands in the work zone."""
    w12, _, f, _ = fake
    wz = sys.modules["work_zone"]
    s = sim(fake, (30, 30))
    did = w12.walk_route(s.pr, s.w, (15, 28), BAND, 16, lambda *a: None, ring(),
                         relocalise=fix_to_truth(s))  # fmt: skip
    assert did.get("arrived_belief") and s.client.true == (15, 28), did
    assert any(e.get("ui_refused") for e in did["events"]), did["events"]
    assert s.client.clicks
    assert all(wz.in_work_zone(x - f.GX, y - f.GY) for x, y in s.client.clicks), s.client.clicks


# --- decision 2: a TALK read blocks its picked cell -------------------------------------------
class StubProber:
    """Scripted cursor reads per point index; records hovers and clicks."""

    def __init__(self, shapes: list[str]) -> None:
        self.shapes, self.hovered, self.clicks = shapes, [], []
        self.background = None
        self.agent = SimpleNamespace(click=lambda x, y: self.clicks.append((x, y)))
        self.at: tuple[float, float] = (0.0, 0.0)

    def park(self) -> bool:
        return True

    def hover(self, u: float, v: float) -> None:
        self.at = (u, v)
        self.hovered.append((u, v))

    def read(self, u: float, v: float) -> dict[str, Any]:
        i = int(round((u - 600.0) / 9.0))
        return {"shape": self.shapes[i], "iou": 0.9, "marker_px": 0, "comps": []}


def test_a_talk_read_refuses_every_later_point_of_the_same_picked_cell(
    fake: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """walk@11's contacts: two TALK reads, then a WALK read 8 px away in the same cell was clicked.
    Here point 0 reads WALK (unnamed, not clicked), point 1 TALK; points 2 and 3 pick the same cell
    and are refused unhovered; point 4 picks another cell and is still read."""
    w12, _, _, _ = fake
    queue = [(600.0 + 9.0 * i, 400.0) for i in range(5)]
    cells = {0: (2, 0), 1: (2, 0), 2: (2, 0), 3: (2, 0), 4: (3, 0)}
    monkeypatch.setattr(w12, "tier_points", lambda w, end, tier: queue if tier == "A" else [])
    monkeypatch.setattr(w12, "picked_cells", lambda w, pts: [cells[queue.index(p)] for p in pts])
    pr = StubProber(["walk", "talk", "walk", "walk", "walk"])
    w = SimpleNamespace(position=(10, 18))
    step = w12.click_step(pr, w, (12, 18))
    assert step["outcome"] == "covered_talk_cell" and not step["clicked"] and not pr.clicks
    assert pr.hovered == [queue[0], queue[1], queue[4]]
    assert step["talk_cells"] == [[12, 18]]
    assert step["talk_refused"] == [[618.0, 400.0], [627.0, 400.0]]
    assert step["target"][-1]["shape"] == "walk" and step["target"][1]["shape"] == "talk"


def test_the_observed_contact_band_is_refused_where_walk11_clicked_it(
    fake: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The synthetic band: the cell (13,18)'s most interior point reads TALK (an NPC's hit region),
    its four alternates read WALK with the marker naming the cell. walk@11 clicks an alternate
    (the POSITIVE CONTROL: the mechanism of every NPC contact since walk@8); walk@12 refuses the
    four unhovered, names the outcome, and the route goes on through other cells."""
    w12, w11, f, _ = fake
    talk_cell = (13, 18)

    def scene(mod: Any) -> Any:
        s = sim(fake, (10, 18), prober_mod=mod)
        c = s.client

        def talk_px() -> tuple[int, int]:  # the cell's centre pixel, from where we stand NOW
            rel = np.array([[talk_cell[0] - c.true[0], talk_cell[1] - c.true[1]]], dtype=float)
            u, v = f.Cam().project(rel)[0]
            return f.GX + round(u), f.GY + round(v)

        base, real_move, real_click = c.shape_at, c.move, c.click
        c.shape_at = lambda cell: "talk" if c.cursor == talk_px() else base(cell)
        s.moves, s.clicked = [], []
        c.move = lambda x, y: (s.moves.append((c.true, x, y)), real_move(x, y))
        c.click = lambda x, y: (s.clicked.append(c.cell_under(x, y)), real_click(x, y))
        return s

    def picked(s: Any) -> Any:
        def cells(w: Any, pts: Any) -> list[tuple[int, int]]:
            got = [s.client.cell_under(f.GX + round(u), f.GY + round(v)) for u, v in pts]
            return [(c[0] - w.position[0], c[1] - w.position[1]) for c in got]

        return cells

    s11 = scene(w11)
    did11 = w11.walk_route(s11.pr, s11.w, (15, 18), BAND, 3, lambda *a: None, ring(),
                           relocalise=fix_to_truth(s11))  # fmt: skip
    assert talk_cell in s11.clicked, did11

    s = scene(w12)
    monkeypatch.setattr(w12, "picked_cells", picked(s))
    did = w12.walk_route(s.pr, s.w, (15, 18), BAND, 3, lambda *a: None, ring(),
                         relocalise=fix_to_truth(s))  # fmt: skip
    assert did.get("arrived_belief") and s.client.true == (15, 18), did
    assert s.clicked and talk_cell not in s.clicked, s.clicked
    covered = [e for e in did["events"] if e.get("outcome") == "covered_talk_cell"]
    assert covered and covered[0]["talk_cells"] == [list(talk_cell)]
    refused = covered[0]["talk_refused"]
    assert len(refused) == 4  # the four alternates, never hovered
    assert covered[0]["from"] == [10, 18]
    hovered = {(x - f.GX, y - f.GY) for at, x, y in s.moves if at == (10, 18)}
    assert {(round(u), round(v)) for u, v in refused}.isdisjoint(hovered)


# --- decision 3: the harness finishes its session ---------------------------------------------
class FakeDetector:
    closed = 0

    def __init__(self) -> None:
        self.model = "fake.onnx"

    def close(self) -> None:
        FakeDetector.closed += 1


class FakeGat:
    def __init__(self) -> None:
        self.altitude = np.zeros((300, 300))

    def walkable(self) -> np.ndarray:
        return np.ones((300, 300), dtype=bool)

    def relative_altitude(self, origin: object, cells: object) -> np.ndarray:
        return np.zeros(len(np.asarray(cells)))


@pytest.fixture
def harness(mods: Any, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Any:
    """walk@11's REAL run (re-bound in walk@12) up to its GM commands, against fakes: no client,
    no detector, no sniffer. ``gm`` decides what each GM command does."""
    w12, _, _, _ = mods
    from poring_dataset import camera as cam
    from poring_dataset import gat as gatmod
    from poring_env import selfpos

    FakeDetector.closed = 0
    monkeypatch.setattr(w12.time, "sleep", lambda s: None)
    monkeypatch.setitem(sys.modules, "unit_detector",
                        SimpleNamespace(UnitDetector=FakeDetector))  # fmt: skip
    monkeypatch.setitem(sys.modules, "bench", SimpleNamespace(close_chat=lambda a, s: None))
    monkeypatch.setattr(
        w12.w6.CursorRefs, "load", classmethod(lambda c, p: SimpleNamespace(cls=[1]))
    )
    monkeypatch.setattr(w12, "map_ms_per_cell", lambda m: 400)
    mask = tmp_path / "mask.npy"
    np.save(mask, np.zeros((64, 64), dtype=bool))
    monkeypatch.setattr(w12.w5, "NOENTRY_MASK", mask)
    monkeypatch.setattr(w12.wf, "load_templates", lambda p: {})
    gats = tmp_path / "gat"
    gats.mkdir()
    (gats / "prt_church.gat").write_bytes(b"")
    monkeypatch.setattr(cam, "GAT_DIR", gats)
    monkeypatch.setattr(cam, "load_indoor_table", lambda *a: frozenset())
    monkeypatch.setattr(gatmod, "parse", lambda b: FakeGat())
    monkeypatch.setattr(selfpos, "load_digit_templates", lambda *a: {})
    monkeypatch.setattr(w12.record_session, "read_lock",
                        lambda p: SimpleNamespace(backend="rdp", seq=7))  # fmt: skip
    monkeypatch.setattr(w12.SessionLog, "root", tmp_path / "demo")
    monkeypatch.setattr(w12.r, "ns", lambda: 123)

    @contextlib.contextmanager
    def session(name: str, **kw: Any) -> Iterator[tuple[Any, Any]]:
        yield object(), object()

    monkeypatch.setattr(w12.r, "session", session)
    state: dict[str, Any] = {"gm": [], "packets": []}

    def write_packets(out: Path, t0: int, t1: int) -> tuple[list[dict[str, Any]], Any]:
        if state.get("packets_fail"):
            raise OSError("the sniffer archive is unreachable")
        state["packets"].append((t0, t1))
        with gzip.open(out / "packets.jsonl.gz", "wt") as fh:
            fh.write('{"e": 1}\n{"e": 2}\n')
        return [{"e": 1}, {"e": 2}], {"anchor": 1}

    monkeypatch.setattr(w12.record_session, "write_packets", write_packets)

    def gm(agent: Any, screen: Any, cmd: str) -> None:
        state["gm"].append(cmd)
        fail = state.get("fail_at")
        if fail is not None and len(state["gm"]) == fail[0]:
            raise fail[1]

    monkeypatch.setattr(w12.r, "gm", gm)
    return w12, state, tmp_path / "demo"


def manifest(root: Path) -> dict[str, Any]:
    (session,) = list(root.iterdir())
    return dict(json.loads((session / "manifest.json").read_text()))


def test_a_typing_failure_still_finishes_the_session_and_exits_nonzero(
    harness: Any, capsys: pytest.CaptureFixture[str]
) -> None:
    """walk@11 indoor CROWD route 54: "the chat input did not open" ended the run without t1 or
    packets. Here the second GM command (route 0's @killmonster2) cannot be typed."""
    w12, state, root = harness
    state["fail_at"] = (2, w12.r.Stop("the chat input did not open: nothing typed"))
    rc = w12.run("indoor", "clean", 3, 1, "walk12-test", 4)
    assert rc == w12.EXIT_STOP != 0
    m = manifest(root)
    assert m["rule"] == "walk@12" and m["work_zone_margin_px"] == 12.0 and m["talk_cell_block"]
    assert m["t1_mono_ns"] and m["ended"] == "harness_stop" and m["exit_code"] == rc
    assert "chat input did not open" in m["reason"]
    assert m["packet_events"] == 2 and m["routes"] == 0
    assert state["packets"] == [(m["t0_mono_ns"], 123)]  # the session's window: t0 .. the end
    (session,) = list(root.iterdir())
    assert (session / "packets.jsonl.gz").exists()
    assert FakeDetector.closed == 1
    assert state["gm"] == ["@warp prt_church 104 122", "@killmonster2"]  # no input after it
    err = capsys.readouterr().err
    assert "ENDED (harness_stop)" in err and "finished (t1 + packets)" in err


def test_an_exception_still_finishes_the_session_and_exits_nonzero(harness: Any) -> None:
    w12, state, root = harness
    state["fail_at"] = (2, RuntimeError("boom"))
    rc = w12.run("indoor", "clean", 3, 1, "walk12-test", 4)
    m = manifest(root)
    assert (
        rc == w12.EXIT_ERROR and m["ended"] == "exception" and m["reason"] == "RuntimeError: boom"
    )
    assert m["t1_mono_ns"] and m["packet_events"] == 2


def test_an_interrupt_still_finishes_the_session_and_exits_nonzero(harness: Any) -> None:
    w12, state, root = harness
    state["fail_at"] = (2, KeyboardInterrupt())
    rc = w12.run("indoor", "clean", 3, 1, "walk12-test", 4)
    m = manifest(root)
    assert rc == w12.EXIT_INTERRUPTED and m["ended"] == "interrupted" and m["packet_events"] == 2


def test_a_packets_failure_still_writes_the_end(harness: Any) -> None:
    w12, state, root = harness
    state["fail_at"] = (2, RuntimeError("boom"))
    state["packets_fail"] = True
    rc = w12.run("indoor", "clean", 3, 1, "walk12-test", 4)
    m = manifest(root)
    assert rc == w12.EXIT_ERROR and m["t1_mono_ns"] and "unreachable" in m["packets_error"]


def test_the_normal_end_is_walk11s_and_exits_zero(harness: Any) -> None:
    w12, state, root = harness
    rc = w12.run("indoor", "clean", 0, 1, "walk12-test", 4)
    m = manifest(root)
    assert rc == 0 and m["ended"] == "complete" and m["routes"] == 0 and m["packet_events"] == 2
    assert state["packets"] == [(123, 123)]  # walk@11's own finish path (t_first .. now)
    assert FakeDetector.closed == 1
