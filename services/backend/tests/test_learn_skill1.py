"""scripts/learn_skill1.py + learn_skill1_score.py (docs/demonstrations.md 3.34): the skill window's
L2 geometry, the pure readers on SYNTHETIC frames (no client pixels), the rule and its known-step
closing through a fake client, the restore refusals, and the offline scorer on synthetic packets.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import numpy as np
import pytest

SCRIPTS = Path(__file__).resolve().parents[2].parent / "scripts"
S = 1_000_000_000


def _load(name: str) -> ModuleType:
    sys.path.insert(0, str(SCRIPTS))
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def ls() -> ModuleType:
    return _load("learn_skill1")


@pytest.fixture(scope="module")
def sc() -> ModuleType:
    return _load("learn_skill1_score")


# --- synthetic templates and frames ---------------------------------------------------------------

WHITE = 247.0
WIN_SIZE = (542, 400)


@pytest.fixture(scope="module")
def rig(ls: ModuleType) -> dict[str, Any]:
    from poring_env import weight as wt

    rng = np.random.default_rng(20261009)
    geo = ls.load_geometry()  # the committed L2 binding
    mean = (rng.random((11, 14, 7)) < 0.4).astype(np.float32)
    mean[:, :2] = 0
    mean[:, 12:] = 0
    mean[:, :, 6] = 0  # one blank column per cell, as the font has
    glyphs = wt.WeightGlyphs(mean, np.ones(11, np.int64), np.zeros((14, 49), np.float32), ink=0.0,
                             max_score=1.5, min_margin=2.0, label_max=1.0)  # fmt: skip
    one = np.zeros((13, 16), bool)
    one[2:11, 7:9] = True
    one[10, 5:11] = True
    lw, lh = geo.label[2], geo.label[3]
    refs = ls.Refs(
        window=rng.uniform(0, 255, (13, 60)).astype(np.float32), window_mask=None,
        window_max=6.0, window_offset=(14, 1), home=(378, 200),
        modal=rng.uniform(0, 120, (geo.modal[3], geo.modal[2])).astype(np.float32),
        nomodal=np.full((geo.modal[3], geo.modal[2]), WHITE, np.float32),
        modal_mask=np.ones((geo.modal[3], geo.modal[2]), bool),
        label=(rng.random((lh, lw)) < 0.3).astype(np.float32), level_one=one, glyphs=glyphs,
    )  # fmt: skip
    return {"geo": geo, "refs": refs}


def _gray3(g: Any) -> Any:
    v = np.clip(np.asarray(g), 0, 255).astype(np.uint8)
    return np.repeat(v[..., None], 3, axis=-1)


def make_frame(ls: ModuleType, rig: dict[str, Any], *, origin: tuple[int, int] | None = (378, 200),
               digits: str | None = "9", colour: bool = False, raise_k: int = 0,
               modal: float = 0.0, level: str | None = None, label: bool = True,
               mark: bool = False, digit_dx: int = 0, seed: int = 1) -> Any:  # fmt: skip
    geo, refs = rig["geo"], rig["refs"]
    rng = np.random.default_rng(seed)
    f = rng.integers(0, 255, (720, 1280, 3)).astype(np.uint8)  # the scene
    if origin is None:
        return f
    ox, oy = origin
    f[oy : oy + WIN_SIZE[1], ox : ox + WIN_SIZE[0]] = int(WHITE)
    tx, ty = ox + refs.window_offset[0], oy + refs.window_offset[1]
    f[ty : ty + 13, tx : tx + 60] = _gray3(refs.window)
    if label:
        x, y, w, h = ls.at(origin, geo.label)
        f[y : y + h, x : x + w] = _gray3(WHITE * (1 - refs.label))
    if digits:
        bx, by, _, _ = ls.at(origin, geo.band)
        for i, ch in enumerate(digits):
            g = refs.glyphs.mean[ls_symbols().index(ch)]
            x = ox + geo.first_cell + digit_dx + 7 * i
            cell = _gray3(WHITE * (1 - g))
            if colour:  # blue ink, as the tentative line shows
                cell = cell.copy()
                cell[..., 0] = np.where(g > 0.5, 255, int(WHITE))
            f[by : by + 14, x : x + 7] = cell
    if mark:
        bx, by, bw, _ = ls.at(origin, geo.band)
        f[by + 5 : by + 9, bx + bw - 6 : bx + bw - 4] = 0
    if raise_k:
        x, y, _, _ = ls.at(origin, geo.tentative)
        f[y + 3 : y + 10, x + 1 : x + 7] = (0, 0, 255)  # the "+"
        f[y + 3 : y + 3 + min(raise_k, 9), x + 9 : x + 12] = (0, 0, 255)  # "N" differs by N
    if modal:
        x, y, w, h = geo.modal
        rows = int(h * modal)
        f[y : y + rows, x : x + w] = _gray3(refs.modal[:rows])
    if level is not None:
        x, y, w, h = ls.at(origin, geo.level)
        other = np.eye(13, 16, dtype=bool) | np.eye(13, 16, 3, bool)
        pat = refs.level_one if level == "1" else other
        if level == "faint":
            pat = np.zeros((13, 16), bool)
            pat[5, 5:8] = True
        f[y : y + h, x : x + w][pat] = 0
    return f


def ls_symbols() -> str:
    from poring_env import weight as wt

    return wt.SYMBOLS


# --- the L2 binding -------------------------------------------------------------------------------


def test_the_l2_binding_loads_and_fails_closed(ls: ModuleType) -> None:
    geo = ls.load_geometry()
    ix, iy, iw, ih = geo.icon
    assert ix <= geo.click[0] < ix + iw and iy <= geo.click[1] < iy + ih
    assert geo.tentative[0] >= ix + iw  # the +N sits right of the icon
    assert geo.level[1] >= iy + ih  # the level digit under it
    for box in (geo.apply, geo.reset, geo.label, geo.band, geo.tentative, geo.level):
        assert box[0] + box[2] <= WIN_SIZE[0] and box[1] + box[3] <= WIN_SIZE[1]
    mx, my, mw, mh = geo.modal
    for b in (geo.ok, geo.cancel):
        assert mx <= b[0] and b[0] + b[2] <= mx + mw and my <= b[1] and b[1] + b[3] <= my + mh
    assert geo.band[3] == 14 and geo.band[0] <= geo.first_cell  # the weight font's cell rows
    from poring_skills.resolve import load_l2

    l2 = load_l2(ls.CLIENT)
    with pytest.raises(ls.Unbound, match="no skill_tree"):
        ls.geometry_from({k: v for k, v in l2.items() if k != "skill_tree"})
    broken = {**l2, "skill_tree": {**l2["skill_tree"], "modal": {"box": [1, 2, 3, 4]}}}
    with pytest.raises(ls.Unbound, match="incomplete"):
        ls.geometry_from(broken)
    with pytest.raises(ls.Unbound, match="incomplete"):
        ls.geometry_from(l2, skill="first_aid")  # no such entry: never guessed


# --- the readers ----------------------------------------------------------------------------------


def test_the_window_is_found_at_home_and_nothing_is_read_without_it(
    ls: ModuleType, rig: dict[str, Any]
) -> None:
    geo, refs = rig["geo"], rig["refs"]
    s = ls.read_all(make_frame(ls, rig), geo, refs)
    assert s.window and s.origin == (378, 200) and s.points == 9
    s = ls.read_all(make_frame(ls, rig, origin=(383, 196)), geo, refs)  # moved a little
    assert s.window and s.origin == (383, 196) and s.points == 9
    s = ls.read_all(make_frame(ls, rig, origin=(420, 260)), geo, refs)  # dragged away
    assert not s.window and s.points is None and s.tentative is None and s.modal is None
    s = ls.read_all(make_frame(ls, rig, origin=None), geo, refs)
    assert not s.window and s.why["window"].startswith("not_at_home")


def test_points_read_the_number_and_fail_closed(ls: ModuleType, rig: dict[str, Any]) -> None:
    geo, refs = rig["geo"], rig["refs"]

    def pts(**kw: Any) -> tuple[Any, str]:
        return tuple(ls.points(make_frame(ls, rig, **kw), (378, 200), geo, refs))  # type: ignore[return-value]

    assert pts(digits="9") == (9, "ok")
    assert pts(digits="0") == (0, "ok")
    assert pts(digits="48") == (48, "ok")
    assert pts(digits="9", colour=True) == (None, "tentative")  # coloured ink: a raise pending
    assert pts(digits="9", mark=True) == (None, "unexplained_ink")
    assert pts(digits="05") == (None, "leading_zero")
    assert pts(digits="8/9") == (None, "layout:slash")
    assert pts(digits="9", label=False) == (None, "no_label")
    assert pts(digits="9", digit_dx=7)[0] is None  # not where the number starts
    assert pts(digits=None) == (None, "no_digits")
    dark = make_frame(ls, rig)
    x, y, w, h = ls.at((378, 200), geo.band)
    dark[y - 2 : y + h + 2, 378 + geo.label[0] : x + w] = 90
    assert ls.points(dark, (378, 200), geo, refs) == (None, "no_window")


def test_the_tentative_is_red_ink_and_its_digest_changes_with_n(
    ls: ModuleType, rig: dict[str, Any]
) -> None:
    geo = rig["geo"]
    assert ls.tentative(make_frame(ls, rig), (378, 200), geo) == (False, "ok", None)
    one = ls.tentative(make_frame(ls, rig, raise_k=1), (378, 200), geo)
    two = ls.tentative(make_frame(ls, rig, raise_k=2), (378, 200), geo)
    assert one[0] is True and two[0] is True and one[2] != two[2]
    grey = make_frame(ls, rig)
    x, y, _, _ = ls.at((378, 200), geo.tentative)
    grey[y + 4 : y + 8, x + 2 : x + 6] = 40  # dark ink that is not red
    got = ls.tentative(grey, (378, 200), geo)
    assert got[0] is None and got[1].startswith("unexplained_ink")


def test_the_modal_by_its_own_pixels(ls: ModuleType, rig: dict[str, Any]) -> None:
    geo, refs = rig["geo"], rig["refs"]
    assert ls.modal(make_frame(ls, rig, modal=1.0), geo, refs)[0] is True
    assert ls.modal(make_frame(ls, rig), geo, refs)[0] is False
    half = ls.modal(make_frame(ls, rig, modal=0.5), geo, refs)
    assert half[0] is None and half[1].startswith("neither")


def test_the_level_digit_only_names_a_glyph_seen_before(ls: ModuleType,
                                                        rig: dict[str, Any]) -> None:  # fmt: skip
    geo, refs = rig["geo"], rig["refs"]
    o = (378, 200)
    assert ls.level(make_frame(ls, rig), o, geo, refs) == (False, None)
    assert ls.level(make_frame(ls, rig, level="1"), o, geo, refs) == (True, "1")
    assert ls.level(make_frame(ls, rig, level="other"), o, geo, refs) == (True, "unseen")
    assert ls.level(make_frame(ls, rig, level="faint"), o, geo, refs) == (None, None)


# --- the rule, through a fake client -------------------------------------------------------------


class FakeClient:
    """The skill window as 3.34 saw it: a raise is tentative, APPLY opens the modal, OK applies."""

    def __init__(self, ls: ModuleType, geo: Any, points: int = 9, *, drop_raise: int = 0,
                 modal_never: bool = False, unreadable: bool = False) -> None:  # fmt: skip
        self.ls, self.geo = ls, geo
        self.window = False
        self.k = 0
        self.raises = 0
        self.modal = False
        self.points = points
        self.level = 0
        self.drop_raise = drop_raise
        self.modal_never = modal_never
        self.unreadable = unreadable
        self.t = 0
        self.calls: list[tuple[str, Any]] = []

    def look(self) -> Any:
        self.t += S // 10
        if not self.window:
            return self.ls.Seen(window=False)
        return self.ls.Seen(
            window=True, origin=(378, 200),
            tentative=None if self.unreadable else self.k > 0,
            tent_digest=f"k{self.k}" if self.k else None, modal=self.modal,
            points=None if self.k else self.points, points_reason="tentative" if self.k else "ok",
            level_ink=self.level > 0, level_glyph=("1" if self.level == 1 else "unseen")
            if self.level else None,
        )  # fmt: skip

    def ui_click(self, xy: tuple[int, int], what: str, inside: tuple[int, int, int, int]) -> int:
        x, y = xy
        assert inside[0] <= x < inside[0] + inside[2] and inside[1] <= y < inside[1] + inside[3]
        self.calls.append(("click", what))
        if what.startswith("raise"):
            self.raises += 1
            if self.raises != self.drop_raise:
                self.k += 1
        elif what == "apply" and not self.modal_never and self.k:
            self.modal = True
        elif what == "ok" and self.modal:
            self.modal, self.points, self.level, self.k = False, self.points - self.k, self.k, 0
        elif what == "cancel":
            self.modal = False
        elif what == "reset":
            self.k = 0
        return self.t

    def chord(self, keys: Any) -> int:
        self.calls.append(("chord", tuple(keys)))
        self.window = not self.window
        return self.t

    def now(self) -> int:
        return self.t

    def wait(self, seconds: float) -> None:
        self.t += int(seconds * S)


KEYS = ["AltLeft", "KeyS"]


def test_the_rule_raises_n_applies_and_reads_the_points(ls: ModuleType,
                                                        rig: dict[str, Any]) -> None:  # fmt: skip
    io = FakeClient(ls, rig["geo"])
    out = ls.learn_skill(io, rig["geo"], KEYS, 3)
    assert out["decline"] is None and out["result_runtime"] == "applied"
    assert out["runtime"] == {"points_after": 6, "level_ink": True, "level_glyph": "unseen"}
    assert [w for kind, w in io.calls if kind == "click"] == [
        "raise 1/3", "raise 2/3", "raise 3/3", "apply", "ok"]  # fmt: skip
    assert [c["why"] for c in out["chords"]] == ["open", "close"] and not io.window
    one = ls.learn_skill(FakeClient(ls, rig["geo"]), rig["geo"], KEYS, 1)
    assert one["runtime"]["level_glyph"] == "1"


def test_the_rule_declines_and_known_steps_close_what_is_left(
    ls: ModuleType, rig: dict[str, Any]
) -> None:
    geo = rig["geo"]
    io = FakeClient(ls, geo, points=8)  # not the harness's 9: nothing clicked
    out = ls.learn_skill(io, geo, KEYS, 2)
    assert out["decline"] == "points_not_expected:8" and out["clicks"] == []
    assert ls.close_known(io, geo, KEYS) and not io.window
    io = FakeClient(ls, geo, drop_raise=2)  # the client ignored the 2nd click
    out = ls.learn_skill(io, geo, KEYS, 3)
    assert out["decline"] == "tentative_unchanged_after_raise_2"
    assert [x["do"] for x in ls.close_known(io, geo, KEYS)] == ["reset", "chord"]
    assert io.k == 0 and not io.window and io.points == 9
    io = FakeClient(ls, geo, modal_never=True)
    out = ls.learn_skill(io, geo, KEYS, 2)
    assert out["decline"] == "no_modal"
    assert [x["do"] for x in ls.close_known(io, geo, KEYS)] == ["reset", "chord"]
    assert ls.learn_skill(FakeClient(ls, geo), geo, KEYS, 10)["decline"] == "n_out_of_range:10"


def test_a_left_modal_is_cancelled_first_and_unreadable_stops(
    ls: ModuleType, rig: dict[str, Any]
) -> None:
    geo = rig["geo"]
    io = FakeClient(ls, geo)
    io.window, io.k, io.modal = True, 2, True
    steps = ls.close_known(io, geo, KEYS)
    assert [x["do"] for x in steps] == ["cancel", "reset", "chord"]
    assert ("click", "cancel") in io.calls and io.points == 9
    io = FakeClient(ls, geo, unreadable=True)
    io.window = True
    with pytest.raises(ls.r.Stop, match="tentative_unreadable"):
        ls.close_known(io, geo, KEYS)
    assert io.calls == []  # nothing pressed into an unknown state


def test_decide_close_is_pure(ls: ModuleType) -> None:
    seen = ls.Seen
    assert ls.decide_close(None)["do"] == "stop"
    assert ls.decide_close(seen(window=False)) == {"do": "clear"}
    assert ls.decide_close(seen(True, (0, 0), modal=None, tentative=False))["do"] == "stop"
    assert ls.decide_close(seen(True, (0, 0), modal=True, tentative=None)) == {"do": "cancel"}
    assert ls.decide_close(seen(True, (0, 0), modal=False, tentative=True)) == {"do": "reset"}
    assert ls.decide_close(seen(True, (0, 0), modal=False, tentative=False)) == {"do": "chord"}


def test_n_is_drawn_in_balanced_seeded_blocks(ls: ModuleType) -> None:
    plan = ls.n_plan(18, 7)
    assert sorted(plan) == sorted(list(range(1, 10)) * 2)
    assert plan == ls.n_plan(18, 7) and plan != ls.n_plan(18, 8)


def test_the_restore_modes_fail_closed(ls: ModuleType) -> None:
    from poring_skills.resolve import load_l2

    l2 = load_l2(ls.CLIENT)
    with pytest.raises(SystemExit, match="group 20"):
        ls.check_restore("skreset", False, l2)
    assert ls.check_restore("skreset", True, l2) == {}
    unbound = {k: val for k, val in l2.items() if k != "game_option"}
    with pytest.raises(ls.Unbound, match="unmeasured: the in-game route to character select"):
        ls.check_restore("charselect", False, unbound)
    # measured live 2026-10-10 (3.34): the game option window's first button
    assert ls.check_restore("charselect", False, l2) == {"char_select": (30, 18, 220, 20)}
    measured = {**l2, "game_option": {"char_select": {"box": [10, 20, 30, 40]}}}
    assert ls.check_restore("charselect", False, measured) == {"char_select": (10, 20, 30, 40)}


# --- the offline scorer -------------------------------------------------------------------------


def ev(t: float, kind: str, **kw: Any) -> dict[str, Any]:
    return {"t_mono_ns": int(t * S), "type": kind, **kw}


def applied(n: int, t0: float = 100.0, skill: int = 1) -> list[dict[str, Any]]:
    out = [ev(50, "stat_change", name="skill_point", value=9)]
    for k in range(1, n + 1):
        t = t0 + k
        out += [ev(t, "skill_up_request", skill_id=skill),
                ev(t + 0.001, "skill_update", skill_id=skill, level=k),
                ev(t + 0.001, "stat_change", name="skill_point", value=9 - k),
                ev(t + 0.001, "skill_list", skills=[{"skill_id": skill, "level": k}])]  # fmt: skip
    return out


def test_the_scorer_judges_a_trial_from_the_packets(sc: ModuleType) -> None:
    ok = {"points_after": 6}
    row = sc.judge_trial(applied(3), 3, 90 * S, 120 * S, runtime=ok)
    assert row["result"] == "success" and row["start_points"] == 9 and row["list_level"] == 3
    assert sc.judge_trial(applied(2), 3, 90 * S, 120 * S, runtime=ok)["result"].startswith(
        "fail: runtime claimed applied")  # fmt: skip
    other = applied(3) + [ev(105, "skill_update", skill_id=142, level=1)]
    assert "other skills [142]" in sc.judge_trial(other, 3, 90 * S, 120 * S, runtime=ok)["server"]
    unsafe = applied(3) + [ev(110, "npc_contact")]
    assert "unsafe" in sc.judge_trial(unsafe, 3, 90 * S, 120 * S, runtime=ok)["server"]
    missed = sc.judge_trial(applied(3), 3, 90 * S, 120 * S, decline="points_after:None/x")
    assert missed["result"] == "fail: applied on the server, the runtime check missed it"
    declined = sc.judge_trial(applied(0), 3, 90 * S, 120 * S, decline="no_modal")
    assert declined["result"] == "fail: declined (no_modal)"
    bad_start = [ev(50, "stat_change", name="skill_point", value=0)] + applied(3)[1:]
    assert sc.judge_trial(bad_start, 3, 90 * S, 120 * S, runtime=ok)["result"].startswith(
        "invalid: start points 0")  # fmt: skip
    harness_raise = applied(3) + [ev(130, "skill_up_request", skill_id=1)]
    row = sc.judge_trial(harness_raise, 3, 90 * S, 120 * S, runtime=ok, t_trial=(80 * S, 140 * S))
    assert row["requests_outside_rule"] == 1 and row["result"].startswith("fail")


def test_the_scorer_totals_and_invalid_trials(sc: ModuleType) -> None:
    events = applied(2) + [ev(300, "stat_change", name="skill_point", value=0)]
    trials = [
        {"k": 0, "n": 2, "t_start": 80 * S, "t_rule_start": 90 * S, "t_rule_end": 120 * S,
         "t_end": 140 * S, "rule": {"decline": None, "runtime": {"points_after": 7}}},
        {"k": 1, "n": 5, "t_start": 200 * S, "stop": "learn_skill@1 start state: points 1"},
    ]  # fmt: skip
    out = sc.judge(trials, events)
    assert out["trials"] == 2 and out["valid"] == 1 and out["success"] == 1
    assert out["rows"][1]["result"].startswith("invalid: harness stop before the rule")
    assert out["by_n"] == {"2": {"success": 1}} and out["unsafe"] == 0


# --- the harness's trial sequence, offline (the live calls patched) -----------------------------


class FakeServer(FakeClient):
    """FakeClient + the GM commands' effects as the pinned server and the 2021 client showed them
    (3.34): @joblevelup -49 resets a spent skill on the SERVER only (the client keeps its digit);
    @skreset resends the list."""

    def __init__(self, ls: ModuleType, geo: Any) -> None:
        super().__init__(ls, geo, points=0)
        self.level = 1  # the CLIENT's digit: the stale "1" tonight's look 6 left on the GM's client
        self.server_level = 0  # the server already reset it (3.34)
        self.typed: list[str] = []

    def ui_click(self, xy: tuple[int, int], what: str, inside: tuple[int, int, int, int]) -> int:
        t = super().ui_click(xy, what, inside)
        if what == "ok":
            self.server_level = self.level
        return t

    def gm(self, cmd: str) -> None:
        # the property under test: nothing is ever typed while a skill-window state is up
        assert not self.window and not self.modal and self.k == 0, cmd
        self.typed.append(cmd)
        if cmd == "@joblevelup 9":
            self.points = 9
        elif cmd == "@skreset":  # flag 1: the points back, and the list resent
            self.points += self.server_level
            self.server_level = self.level = 0
        elif cmd == "@joblevelup -49":  # fewer unspent than 9: the server resets, silently
            if self.points < 9:
                self.server_level = 0
            self.points = 0


def test_the_harness_trial_syncs_a_stale_client_then_restores(
    ls: ModuleType, rig: dict[str, Any], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    import types

    from poring_env.demo import DemoLog, FrameRef, new_session_id

    geo = rig["geo"]
    io = FakeServer(ls, geo)
    fixed = {"fixed": True}
    fake_gm_state = types.SimpleNamespace(
        ensure_fixed=lambda *a, **k: fixed, clear_notices=lambda *a, **k: {"notices": []}
    )
    monkeypatch.setitem(sys.modules, "gm_state", fake_gm_state)
    monkeypatch.setattr(ls.r, "gm", lambda agent, screen, cmd: io.gm(cmd))
    monkeypatch.setattr(ls, "_snap", lambda rig_, name: FrameRef())
    monkeypatch.setattr(ls.time, "sleep", lambda s: None)
    log = DemoLog(new_session_id("learn-skill1-test"), root=tmp_path)
    harness = ls.Rig(None, None, io, geo, KEYS, log, "skreset", {})  # type: ignore[arg-type]
    trial: dict[str, Any] = {"k": 0, "n": 4}
    ls.run_trial(harness, trial)
    assert trial["start"]["synced"] and trial["start"]["stale_level"] == "1"
    assert io.typed == ["@skreset", "@joblevelup 9", "@skreset", "@joblevelup -49"]
    assert trial["rule"]["decline"] is None and trial["rule"]["runtime"]["points_after"] == 5
    assert trial["t_rule_start"] < trial["t_rule_end"] <= trial["t_end"]
    assert (io.points, io.level, io.window) == (0, 0, False)
    actors = [x.actor for x in log.records()]
    assert actors.count("rule:learn_skill@1") == 1 and actors.count("rule:harness@1") >= 5
    io2 = FakeServer(ls, geo)
    io2.points = 3  # not the fixed state: the start check stops, nothing typed
    harness2 = ls.Rig(None, None, io2, geo, KEYS, log, "skreset", {})  # type: ignore[arg-type]
    with pytest.raises(ls.r.Stop, match="start state: points 3"):
        ls.run_trial(harness2, {"k": 1, "n": 2})
    assert io2.typed == []
