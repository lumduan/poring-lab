"""scripts/stage_items.py `run`, driven OFFLINE through fakes (no ro_agent, no screen, no input):
the GM lines it would type, in order. pay_fild07's run types exactly stage@4's lines; gef_fild10's
types each spot's group and ends with two @killmonster2 lines LOOT_LIFE_S apart, also after a wrong
drop, and one (plus the printed TODO) after a stop. The refusals come before any line."""

from __future__ import annotations

import argparse
import contextlib
import json
import sys
import types
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))
import stage_items as si  # noqa: E402

SPOTS = [(100, 100), (150, 100), (200, 100)]


class _Stop(SystemExit):
    pass


class _World:
    """What the fakes saw: every GM line, the sleeps, and the bag the @item lines filled."""

    def __init__(self, items: dict[int, str], fail: dict[int, str]) -> None:
        self.lines: list[str] = []
        self.sleeps: list[float] = []
        self.bag: list[int] = []
        self.items, self.fail, self.clears = items, fail, 0


def _install(monkeypatch: pytest.MonkeyPatch, tmp: Path, map_: str,
             fail: dict[int, str] | None = None) -> _World:  # fmt: skip
    """Fakes for every live module run() imports, a tmp icon dir with the map's icons and a tmp
    DEMO; the spots and the DB's held rows are fixed."""
    ms = si.map_set(map_)
    icons = tmp / "icons"
    icons.mkdir()
    for n in ms.items.values():
        np.save(icons / f"loot-{n}.npy", np.zeros((16, 14)))
    monkeypatch.setitem(si.MAP_SETS, map_, si.replace(ms, icon_dir=icons))
    w = _World(ms.items, fail or {})

    r = types.ModuleType("ro_agent")
    r.Stop = _Stop  # type: ignore[attr-defined]
    r.SHOTS = tmp  # type: ignore[attr-defined]
    r.ns = lambda: 0  # type: ignore[attr-defined]
    r.to_png = lambda img, path: path  # type: ignore[attr-defined]

    @contextlib.contextmanager
    def session(name: str) -> Iterator[tuple[Any, Any]]:
        agent = types.SimpleNamespace(wait_for_human=lambda: None)
        yield agent, types.SimpleNamespace(full=lambda: np.zeros((2, 2, 4), np.uint8))

    r.session = session  # type: ignore[attr-defined]

    def gm_line(agent: Any, screen: Any, cmd: str, job: str, char: str) -> dict[str, Any]:
        assert (job, char) == (si.JOB, si.CHAR)
        w.lines.append(cmd)
        if cmd.startswith("@item "):
            w.bag.append(int(cmd.split()[1]))
        return {"ok": True}

    cr = types.ModuleType("crusader")
    cr.gm_line = gm_line  # type: ignore[attr-defined]
    cr.check = lambda screen, job, char: {"ok": True}  # type: ignore[attr-defined]

    def clear_loot(agent: Any, screen: Any, *, why: str, refs_dir: Path) -> dict[str, Any]:
        assert refs_dir == icons
        k, w.clears = w.clears, w.clears + 1
        if w.fail.get(k) == "stop":
            raise _Stop("a prompt stayed open")
        got = [{"tab": "etc", "slot": 0, "item": w.items[i]} for i in w.bag]
        if w.fail.get(k) == "short":
            got = got[1:]
        w.bag = []
        return {"dropped": got, "unknown": 0, "kept": []}

    gs = types.ModuleType("gm_state")
    gs.clear_loot = clear_loot  # type: ignore[attr-defined]
    bench = types.ModuleType("bench")
    bench.close_chat = lambda agent, screen: None  # type: ignore[attr-defined]
    ui = types.ModuleType("ui_gate")
    ui.ensure_clear = lambda agent, screen, why: {}  # type: ignore[attr-defined]
    for name, mod in (("ro_agent", r), ("crusader", cr), ("gm_state", gs), ("bench", bench),
                      ("ui_gate", ui)):  # fmt: skip
        monkeypatch.setitem(sys.modules, name, mod)
    monkeypatch.setattr(si, "plan_spots", lambda m, n, seed, open_, views="default": SPOTS[:n])
    monkeypatch.setattr(si, "_held_rows", lambda items: [])
    monkeypatch.setattr(si, "DEMO", tmp / "demo")
    monkeypatch.setattr(si.time, "sleep", w.sleeps.append)
    return w


def _args(map_: str, **kw: Any) -> argparse.Namespace:
    base = {"map": map_, "n": 3, "seed": 5, "label": "t", "immune_confirmed": True,
            "open": None, "per_spot": None, "clear": None}  # fmt: skip
    return argparse.Namespace(**{**base, **kw})


def _events(tmp: Path) -> list[dict[str, Any]]:
    (d,) = (tmp / "demo").iterdir()
    return [json.loads(x) for x in (d / "events.jsonl").read_text().splitlines()]


def test_pay_fild07_types_exactly_stage4s_lines(monkeypatch: pytest.MonkeyPatch,
                                               tmp_path: Path) -> None:  # fmt: skip
    w = _install(monkeypatch, tmp_path, "pay_fild07")
    assert si.run(_args("pay_fild07")) == 0
    want = []
    for x, y in SPOTS:  # stage@4's loop, verbatim
        want.append(f"@warp pay_fild07 {x} {y}")
        want += [f"@item {i} 1" for i in si.TARGETS]
        want += [f"@warp pay_fild07 {x + dx} {y + dy}" for dx, dy in si.OFFSETS[1:]]
    assert w.lines == want and "@killmonster2" not in w.lines
    start, end = _events(tmp_path)[0], _events(tmp_path)[-1]
    assert set(start) == {"t_ns", "kind", "version", "map", "seed", "spots", "open", "offsets",
                          "still_s", "targets", "char", "job", "views"}  # fmt: skip
    assert (start["char"], start["job"], start["views"]) == ("thief", "rogue", "default")
    assert end == {"t_ns": 0, "kind": "run_end", "reason": "done"}


def test_gef10_types_each_group_then_the_end_pair(monkeypatch: pytest.MonkeyPatch,
                                                  tmp_path: Path) -> None:  # fmt: skip
    w = _install(monkeypatch, tmp_path, "gef_fild10")
    assert si.run(_args("gef_fild10")) == 0
    groups = si.item_groups(list(si.GEF10_ITEMS), 3, 6, 5)
    want = []
    for (x, y), g in zip(SPOTS, groups, strict=True):
        want.append(f"@warp gef_fild10 {x} {y}")
        want += [f"@item {i} 1" for i in g]
        want += [f"@warp gef_fild10 {x + 3} {y}", f"@warp gef_fild10 {x} {y + 3}"]
    assert w.lines == [*want, "@killmonster2", "@killmonster2"]
    assert si.LOOT_LIFE_S in w.sleeps and w.sleeps.index(si.LOOT_LIFE_S) > 0
    ev = _events(tmp_path)
    assert ev[0]["groups"] == groups and ev[0]["per_spot"] == 6 and ev[0]["clear"] == "end"
    assert [e["i"] for e in ev if e["kind"] == "killmonster2"] == [0, 1]
    assert len(ev[-1]["killmonster2"]) == 2 and ev[-1]["reason"] == "done"


def test_gef10_wrong_drop_stops_but_still_types_the_end_pair(monkeypatch: pytest.MonkeyPatch,
                                                            tmp_path: Path) -> None:  # fmt: skip
    w = _install(monkeypatch, tmp_path, "gef_fild10", fail={1: "short"})
    assert si.run(_args("gef_fild10")) == 1
    assert w.lines.count("@warp gef_fild10 150 100") == 1  # spot 1 reached, no views after it
    assert "@warp gef_fild10 153 100" not in w.lines
    assert w.lines[-2:] == ["@killmonster2", "@killmonster2"]
    assert _events(tmp_path)[-1]["reason"].startswith("spot 1: dropped")


def test_gef10_stop_types_one_kill_and_prints_the_todo(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    w = _install(monkeypatch, tmp_path, "gef_fild10", fail={0: "stop"})
    assert si.run(_args("gef_fild10")) == 1
    assert w.lines.count("@killmonster2") == 1 and w.lines[-1] == "@killmonster2"
    assert si.END_KILL_TODO in capsys.readouterr().err
    assert _events(tmp_path)[-1]["reason"].startswith("stop:")


def test_clear_none_and_refusals_type_nothing(monkeypatch: pytest.MonkeyPatch,
                                              tmp_path: Path) -> None:  # fmt: skip
    w = _install(monkeypatch, tmp_path, "gef_fild10")
    assert si.run(_args("gef_fild10", clear="none", n=1)) == 0
    assert "@killmonster2" not in w.lines
    w.lines.clear()
    with pytest.raises(SystemExit, match="immune-confirmed"):
        si.run(_args("gef_fild10", immune_confirmed=False))
    monkeypatch.setattr(si, "_held_rows", lambda items: [(7053, 3)])
    with pytest.raises(SystemExit, match="whole stacks"):
        si.run(_args("gef_fild10"))
    (si.map_set("gef_fild10").icon_dir / "loot-axe.npy").unlink()
    with pytest.raises(SystemExit, match="axe"):
        si.run(_args("gef_fild10"))
    assert w.lines == []


def test_xmas02_kills_at_each_spot_before_its_group(monkeypatch: pytest.MonkeyPatch,
                                                     tmp_path: Path) -> None:  # fmt: skip
    """stage@8 (xmas02-detector.md O.6 / O.11): one @killmonster2 right after each spot's warp,
    before its @item lines (the map's monsters and a living MVP die, no drops); no end pair (no
    xmas_dun02 species loots); the ICT times are the MVP clock in run_end."""
    w = _install(monkeypatch, tmp_path, "xmas_dun02")
    assert si.run(_args("xmas_dun02")) == 0
    groups = si.item_groups(list(si.XMAS02_ITEMS), 3, 6, 5)
    want = []
    for (x, y), g in zip(SPOTS, groups, strict=True):
        want += [f"@warp xmas_dun02 {x} {y}", "@killmonster2"]
        want += [f"@item {i} 1" for i in g]
        want += [f"@warp xmas_dun02 {x + 3} {y}", f"@warp xmas_dun02 {x} {y + 3}"]
    assert w.lines == want and si.LOOT_LIFE_S not in w.sleeps
    ev = _events(tmp_path)
    assert ev[0]["clear"] == "spot" and ev[0]["per_spot"] == 6
    assert [e["i"] for e in ev if e["kind"] == "killmonster2"] == [0, 1, 2]
    assert len(ev[-1]["killmonster2"]) == 3 and ev[-1]["reason"] == "done"


def test_xmas02_wrong_drop_stops_after_that_spots_kill(monkeypatch: pytest.MonkeyPatch,
                                                        tmp_path: Path) -> None:  # fmt: skip
    w = _install(monkeypatch, tmp_path, "xmas_dun02", fail={1: "short"})
    assert si.run(_args("xmas_dun02")) == 1
    assert w.lines.count("@killmonster2") == 2  # spots 0 and 1, no end pair
    assert "@warp xmas_dun02 153 100" not in w.lines
    assert _events(tmp_path)[-1]["reason"].startswith("spot 1: dropped")


def test_stage9_near_views_beside_the_crusader(monkeypatch: pytest.MonkeyPatch,
                                               tmp_path: Path) -> None:  # fmt: skip
    """stage@9 (xmas02-detector.md O15): --views near stands on the pile, then 2 cells off it on
    three sides; --char crusader types every line as the Base 60 Crusader (no aura)."""
    monkeypatch.setattr(si, "CHAR", si.CHAR)
    monkeypatch.setattr(si, "JOB", si.JOB)
    si.use_char("crusader")
    assert (si.CHAR, si.JOB) == ("crusader", "crusader")
    w = _install(monkeypatch, tmp_path, "xmas_dun02")
    assert si.run(_args("xmas_dun02", views="near")) == 0
    groups = si.item_groups(list(si.XMAS02_ITEMS), 3, 6, 5)
    want = []
    for (x, y), g in zip(SPOTS, groups, strict=True):
        want += [f"@warp xmas_dun02 {x} {y}", "@killmonster2"]
        want += [f"@item {i} 1" for i in g]
        want += [f"@warp xmas_dun02 {x + dx} {y + dy}" for dx, dy in si.NEAR_OFFSETS[1:]]
    assert w.lines == want
    ev = _events(tmp_path)
    assert (ev[0]["char"], ev[0]["job"], ev[0]["views"]) == ("crusader", "crusader", "near")
    assert [tuple(o) for o in ev[0]["offsets"]] == list(si.NEAR_OFFSETS)
    with pytest.raises(SystemExit, match="unknown character"):
        si.use_char("novice")
