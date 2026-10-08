"""scripts/route_plan.py + route_previewd.py: walk rules publish their route in CELLS; the live
previewer subscribes (Batt, 2026-10-08: the one-shot screen-pixel preview floated)."""

from __future__ import annotations

import socket
import sys
from pathlib import Path
from typing import Any

import pytest

SCRIPTS = Path(__file__).resolve().parents[3] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import route_plan as plan  # noqa: E402
import route_previewd as pd  # noqa: E402


class FakeCamera:
    height = 720

    def vector(self) -> list[float]:
        return [0.1, 0.9, 400.0, 0.3, 640.0, 360.0]


class FakeCore:
    def __init__(self, msg: dict[str, Any]) -> None:
        self.msg, self.calls, self.active, self.label = msg, [], False, ""

    def set_route(self, *a: Any) -> None:
        self.calls.append(("set_route", a))
        self.active = True

    def walk(self, *a: Any) -> None:
        self.calls.append(("walk", a))

    def snap(self, *a: Any) -> None:
        self.calls.append(("snap", a))

    def snap_fix(self, *a: Any) -> None:
        self.calls.append(("snap_fix", a))

    def clear(self) -> dict[str, Any]:
        self.calls.append(("clear", ()))
        self.active = False
        return {"points": [], "passed": [], "clip": []}


@pytest.fixture
def sock(tmp_path: Path) -> Any:
    path = Path("/dev/shm") / f"route-plan-test-{tmp_path.name}.sock"
    s = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
    s.bind(str(path))
    s.settimeout(1.0)
    yield path, s
    s.close()
    path.unlink(missing_ok=True)


def _route(pub: plan.PlanPublisher) -> None:
    pub.route(map_name="prt_church", camera=FakeCamera(), region=(8, 31, 1280, 720),
              desktop=(1440, 900), position=(99, 120), corners=[(99, 125), (101, 127)],
              goal=(101, 127), click=(99, 124), label="walk@12 route 3")  # fmt: skip


def test_a_rule_publishes_its_route_in_cells_and_never_blocks(sock: Any) -> None:
    path, s = sock
    pub = plan.PlanPublisher("sess-1", sock_path=path, autostart=False)
    _route(pub)
    pub.walk((99, 120), [(99, 121), (99, 122)], 150, 123)
    pub.snap((99, 122))
    pub.fix((99, 122))
    pub.clear()
    got = [plan.decode(s.recv(plan.MAX_DATAGRAM)) for _ in range(5)]
    assert [m["cmd"] for m in got if m] == ["route", "walk", "snap", "fix", "clear"]
    r = got[0]
    assert r is not None and r["session"] == "sess-1" and r["map"] == "prt_church"
    assert r["position"] == [99, 120] and r["corners"] == [[99, 125], [101, 127]]
    assert r["camera"] == {"vector": [0.1, 0.9, 400.0, 0.3, 640.0, 360.0], "height": 720}
    assert "points" not in r  # cells only: no screen pixels travel
    assert pub.sent == 5 and pub.dropped == 0


def test_no_previewer_is_a_dropped_message_never_an_error(tmp_path: Path) -> None:
    pub = plan.PlanPublisher("s", sock_path=Path("/dev/shm/route-plan-nobody.sock"),
                             autostart=False)  # fmt: skip
    _route(pub)
    pub.clear()
    assert pub.sent == 0 and pub.dropped == 2
    assert plan.listening(Path("/dev/shm/route-plan-nobody.sock")) is False


def test_malformed_datagrams_decode_to_nothing() -> None:
    assert plan.decode(b"\xff\x00") is None
    assert plan.decode(b"[1, 2]") is None
    assert plan.decode(b'{"cmd": "click", "x": 1}') is None  # not a plan command
    assert plan.decode(plan.encode("clear"))["cmd"] == "clear"  # type: ignore[index]
    with pytest.raises(ValueError):
        plan.encode("input")


def _msgs(session: str = "sess-1") -> dict[str, dict[str, Any]]:
    cam = plan.camera_dict(FakeCamera())
    route = plan.decode(plan.encode("route", session=session, map="prt_church", camera=cam,
                                    region=[8, 31, 1280, 720], desktop=[1440, 900],
                                    position=[99, 120], corners=[[99, 125]], goal=[99, 125],
                                    click=None, label="r1", log=None))  # fmt: skip
    walk = plan.decode(plan.encode("walk", session=session, start=[99, 120],
                                   path=[[99, 121]], ms_per_cell=150.0, t_click_ns=5))  # fmt: skip
    clear = plan.decode(plan.encode("clear", session=session))
    assert route and walk and clear
    return {"route": route, "walk": walk, "clear": clear}


def test_the_previewer_follows_one_session_and_ignores_stale_publishers() -> None:
    made: list[FakeCore] = []

    def factory(msg: dict[str, Any]) -> FakeCore:
        made.append(FakeCore(msg))
        return made[-1]

    d = pd.Previewd(core_factory=factory)
    assert d.handle(_msgs()["walk"]) is None and d.ignored == 1  # no route yet: nothing to anchor
    m = _msgs()
    d.handle(m["route"])
    assert d.active and d.region == (8, 31, 1280, 720) and len(made) == 1
    d.handle(_msgs("old-session")["walk"])  # another publisher: ignored
    assert [c[0] for c in made[0].calls] == ["set_route"]
    d.handle(m["walk"])
    assert made[0].calls[-1] == ("walk", ([99, 120], [[99, 121]], 150.0, 5))
    d.handle(m["route"])  # the same session's next route: the same core (its camera state kept)
    assert len(made) == 1
    body = d.handle(m["clear"])
    assert body == {"points": [], "passed": [], "clip": []} and not d.active
    d.handle(_msgs("sess-2")["route"])  # a new run: a fresh core
    assert len(made) == 2 and d.session == "sess-2"


def test_the_previewer_exits_only_when_idle_and_inactive() -> None:
    now = [0.0]
    d = pd.Previewd(core_factory=FakeCore, clock=lambda: now[0])
    d.handle(_msgs()["route"])
    now[0] = pd.IDLE_EXIT_S + 10
    assert not d.idle_too_long()  # a route is active: never idle
    d.handle(_msgs()["clear"])
    assert not d.idle_too_long()  # the clear itself was a message
    now[0] += pd.IDLE_EXIT_S + 1
    assert d.idle_too_long()


def test_a_malformed_message_is_skipped_not_fatal() -> None:
    d = pd.Previewd(core_factory=FakeCore)
    d.handle(_msgs()["route"])
    assert d.handle({"cmd": "walk", "session": "sess-1"}) is None  # missing fields
    assert d.ignored == 1 and d.active


def test_map_names_cannot_leave_the_gat_directory() -> None:
    for bad in ("../etc/passwd", "a/b", ".hidden"):
        with pytest.raises(ValueError):
            pd._gat(bad)


# --- the rule side: enable / preview / hooks ------------------------------------------------------
class FakeWorld:
    def __init__(self) -> None:
        self.camera, self.position = FakeCamera(), (10, 10)


@pytest.fixture
def enabled(sock: Any, monkeypatch: pytest.MonkeyPatch) -> Any:
    path, s = sock
    monkeypatch.setattr(plan, "_screen", lambda: ((8, 31, 1280, 720), (1440, 900)))
    token = plan.enable("run-1", "prt_church", sock_path=path, log_path="/dev/shm/x.jsonl")
    pub = plan.publisher()
    assert pub is not None
    pub.autostart = False
    yield s
    plan.disable(token)


def _recv(s: socket.socket) -> dict[str, Any]:
    msg = plan.decode(s.recv(plan.MAX_DATAGRAM))
    assert msg is not None
    return msg


def test_nothing_is_published_until_a_run_enables_it() -> None:
    assert plan.publisher() is None
    plan.preview(None, FakeWorld(), (10, 10), [(12, 12)], None, "walk@11 route 1")  # a no-op
    step = plan.hook_click_step(lambda pr, w, end: {"clicked": True, "t_click": 5},
                                lambda w, a, b: [b])  # fmt: skip
    assert step(None, FakeWorld(), (12, 12)) == {"clicked": True, "t_click": 5}


def test_the_rule_side_publishes_the_route_the_walk_the_fix_and_the_clear(enabled: Any) -> None:
    s = enabled
    w = FakeWorld()
    plan.preview(None, w, (10, 10), [(10, 14), (12, 16)], (10, 13), "walk@12 route 3")
    r = _recv(s)
    assert (r["cmd"], r["position"], r["corners"], r["goal"], r["click"]) == (
        "route",
        [10, 10],
        [[10, 14], [12, 16]],
        [12, 16],
        [10, 13],
    )
    assert r["map"] == "prt_church" and r["region"] == [8, 31, 1280, 720]
    assert r["log"] == "/dev/shm/x.jsonl" and r["session"] == "run-1"

    seen: list[Any] = []

    def rule_step(pr: Any, w: Any, end: tuple[int, int]) -> dict[str, Any]:
        seen.append(tuple(w.position))
        return {"clicked": True, "t_click": 77, "outcome": "confirmed"}

    step = plan.hook_click_step(rule_step, lambda w, a, b: [(a[0], a[1] + 1), b])
    assert step(None, w, (10, 13)) == {"clicked": True, "t_click": 77, "outcome": "confirmed"}
    wk, sn = _recv(s), _recv(s)
    assert (wk["cmd"], wk["start"], wk["path"], wk["t_click_ns"]) == (
        "walk",
        [10, 10],
        [[10, 11], [10, 13]],
        77,
    )
    assert wk["ms_per_cell"] == plan.SELF_MS_PER_CELL and sn["cmd"] == "snap"

    fix = plan.hook_relocalise(lambda tpl: lambda *a: {"ok": True, "to": [11, 12]})(None)
    assert fix() == {"ok": True, "to": [11, 12]}
    assert (lambda m: (m["cmd"], m["cell"]))(_recv(s)) == ("fix", [11, 12])

    def route_fails(*a: Any) -> None:
        raise RuntimeError("the chat input did not open")

    with pytest.raises(RuntimeError):
        plan.hook_route_end(route_fails)()
    assert _recv(s)["cmd"] == "clear"  # cleared however the route ends


def test_an_unclicked_step_publishes_no_walk(enabled: Any) -> None:
    s = enabled
    step = plan.hook_click_step(lambda pr, w, end: {"clicked": False, "outcome": "no_safe_point"},
                                lambda w, a, b: [b])  # fmt: skip
    step(None, FakeWorld(), (12, 12))
    assert _recv(s)["cmd"] == "snap"  # the belief only


def test_an_outer_enable_keeps_ownership(sock: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    """route_demo enables first (with its log); walk@12's own enable then neither replaces nor
    disables it."""
    path, s = sock
    outer = plan.enable("demo", "prt_church", sock_path=path, log_path="/dev/shm/live.jsonl")
    try:
        inner = plan.enable("walk@12-indoor", "prt_church", sock_path=path)
        assert inner is None
        plan.disable(inner)  # not ours: nothing
        pub = plan.publisher()
        assert pub is not None and pub.log_path == "/dev/shm/live.jsonl"
    finally:
        plan.disable(outer)
    assert plan.publisher() is None
