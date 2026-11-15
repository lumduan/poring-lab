"""scripts/stage6_ab.py: section 16's live A/B (live-blocks.md 16) -- the one box (B) against the
same box with no Knife swap on the Christmas Cookie and the Cookie (C): the plan's refusals before
any input, the score's readers on synthetic sessions, and every judged line of the pre-registered
bar with a positive case and a failing one. NOT run live."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts"))

import stage6_ab as ab  # noqa: E402

from poring_flow import recipes as rc  # noqa: E402

ONE = ab.PROJECTS["B"]
NOSWAP = ab.PROJECTS["C"]
HUNT = ab.s4.FIX / "project_xmas_dun02_hunt.json"


def _d(path: Path) -> dict[str, Any]:
    return dict(json.loads(path.read_text()))


def _defs(d: dict[str, Any], tab: str) -> list[dict[str, Any]]:
    return list(next(t for t in d["nodes"][0]["tabs"] if t["name"] == tab)["defs"])


def _var(d: dict[str, Any], tab: str, name: str, value: Any) -> None:
    t = next(t for t in d["nodes"][0]["tabs"] if t["name"] == tab)
    t["vars"][name] = {"kind": "lit", "value": value}


def _plain(d: dict[str, Any], names: tuple[str, ...]) -> dict[str, Any]:
    """The box with those recipes cut to their own strike, wait_kill, loot."""
    for x in _defs(d, "monsters"):
        if x["name"] in names:
            x["body"] = [x["body"][i] for i in (1, 4, 5)]
    return d


def _plan(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, b: dict[str, Any],
          c: dict[str, Any]) -> dict[str, Any] | str:  # fmt: skip
    pb, pc = tmp_path / "b.json", tmp_path / "c.json"
    pb.write_text(json.dumps(b))
    pc.write_text(json.dumps(c))
    monkeypatch.setattr(ab, "PROJECTS", {"B": pb, "C": pc})
    monkeypatch.setattr(ab, "ROOT", tmp_path)  # the plan names the files relative to it
    return ab.plan_doc("s", 1, 20, "alternate", tmp_path / "s")


# --- the plan -------------------------------------------------------------------------------------
def test_the_series_alternates_b_and_c() -> None:
    runs = ab.series("s6", 3)
    assert [r.arm for r in runs] == ["B", "C", "C", "B", "B", "C"]
    assert [r.label for r in runs][:2] == ["s6-r01B", "s6-r02C"]
    assert ab.KNIFE == rc.KNIFE_SHAPE and ab.PLAIN == rc.PLAIN_SHAPE
    assert ab.STEAL_CUES == ("popup", "cyan") and ab.VERSION == "9.51"


def test_the_plan_plays_both_boxes_with_the_same_runner_and_settings(tmp_path: Path) -> None:
    doc = ab.plan_doc("s", 3, 20, "alternate", tmp_path / "s")
    assert isinstance(doc, dict), doc
    b, c = doc["arms"]["B"], doc["arms"]["C"]
    assert b["loop"] is None and c["loop"] is None and b["keys"] == c["keys"]
    assert b["box_plays"] == c["box_plays"] and b["box_roles"] == c["box_roles"]
    assert {sp: r["knife"] for sp, r in c["box_recipes"].items()} == {
        "cookie": False, "cookie_xmas": False, "cruiser": True, "mystcase": True}  # fmt: skip
    assert all(r["knife"] for r in b["box_recipes"].values())
    assert b["project_hash"] != c["project_hash"]
    assert doc["vals"]["alarm_fast"] is True and doc["vals"]["bare_ready"] is True
    assert doc["bar"] is ab.BAR and [r["arm"] for r in doc["runs"]] == ["B", "C", "C", "B", "B",
                                                                         "C"]  # fmt: skip
    for r in doc["runs"]:
        argv = r["argv"]
        assert str(tmp_path / "s" / f"project-{r['arm']}.json") in argv
        assert "scripts/flow_play.py" in argv and doc["arms"][r["arm"]]["project_hash"] in argv
    norm = [[x for x in r["argv"] if not x.startswith(str(tmp_path)) and x not in (
        b["project_hash"], c["project_hash"]) and "-r0" not in x] for r in doc["runs"]]  # fmt: skip
    assert all(v == norm[0] for v in norm)  # the same command but the box and the labels


def test_the_box_difference_is_the_two_cookie_recipes_alone() -> None:
    b, c = _d(ONE), _d(NOSWAP)
    assert ab.box_difference(b, c) is None
    assert "C's attack_cookie is not B's own" in str(ab.box_difference(b, b))  # no change at all
    assert "B's attack_cookie is not the Knife swap" in str(ab.box_difference(c, c))
    three = _plain(_d(ONE), ("attack_cookie", "attack_cookie_xmas", "attack_mystcase"))
    assert "more than its two cookies' recipes" in str(ab.box_difference(b, three))
    bent = _d(NOSWAP)
    bent["max_runtime_s"] = 60
    assert "more than its two cookies' recipes" in str(ab.box_difference(b, bent))
    noloot = _d(NOSWAP)
    next(x for x in _defs(noloot, "monsters") if x["name"] == "attack_cookie")["body"].pop()
    assert "strike(t), wait_kill(t), loot(t)" in str(ab.box_difference(b, noloot))
    heavy = _d(NOSWAP)
    next(x for x in _defs(heavy, "monsters") if x["name"] == "attack_cookie")["params"][1][
        "default"]["value"] = 2  # fmt: skip
    assert "more than its two cookies' recipes" in str(ab.box_difference(b, heavy))
    gone = _d(NOSWAP)
    tab = next(t for t in gone["nodes"][0]["tabs"] if t["name"] == "monsters")
    tab["defs"] = [x for x in tab["defs"] if x["name"] != "attack_cookie_xmas"]
    assert "C has no attack_cookie_xmas" in str(ab.box_difference(b, gone))
    b2 = _d(ONE)
    b2["name"], b2["description"] = "other", "other words"  # the name and the words may differ
    assert ab.box_difference(b2, c) is None


def test_the_plan_refuses_before_any_input(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    b, c = _d(ONE), _d(NOSWAP)
    got = _plan(tmp_path, monkeypatch, b, b)
    assert isinstance(got, str) and got.startswith("refused before any input: C's attack_cookie")
    off_b, off_c = _d(ONE), _d(NOSWAP)
    for d in (off_b, off_c):
        _var(d, "safety", "alarm_fast", False)
    assert "alarm_fast off" in str(_plan(tmp_path, monkeypatch, off_b, off_c))
    other = _d(NOSWAP)
    _var(other, "knife", "bare_ready", False)  # a setting differs: not one change
    got = _plan(tmp_path, monkeypatch, b, other)
    assert isinstance(got, str) and "runner settings differ: bare_ready" in got
    # the hunt box and its no-swap copy: both would play a hunt loop (14.12: the one box has none)
    hb, hc = _d(HUNT), _plain(_d(HUNT), ("attack_cookie", "attack_cookie_xmas"))
    assert "a box with a hunt loop" in str(_plan(tmp_path, monkeypatch, hb, hc))
    # and the real pair plans
    assert isinstance(_plan(tmp_path, monkeypatch, b, c), dict)


def test_recipes_problem_names_each_way_the_recipes_are_not_this_experiments() -> None:
    k = {"function": "f", "steps": list(ab.KNIFE), "knife": True, "priority": 1.0}
    p = {"function": "f", "steps": list(ab.PLAIN), "knife": False, "priority": 1.0}
    b = {sp: k for sp in ("cookie", "cookie_xmas", "cruiser", "mystcase")}
    c = {**b, "cookie": p, "cookie_xmas": p}
    assert ab.recipes_problem(b, c) is None
    assert "not the Knife swap" in str(ab.recipes_problem(c, c))
    assert "not ['strike', 'wait_kill', 'loot']" in str(ab.recipes_problem(b, b))
    assert "not B's" in str(ab.recipes_problem(b, {**c, "cruiser": p}))
    assert "priority 2" in str(ab.recipes_problem(b, {**c, "cookie": {**p, "priority": 2}}))
    lone = {sp: r for sp, r in c.items() if sp != "cruiser"}
    assert "a monster on the runner's own" in str(ab.recipes_problem(b, lone))


# --- the score's readers --------------------------------------------------------------------------
def _write(path: Path, events: list[dict[str, Any]]) -> None:
    path.mkdir(parents=True)
    (path / "events.jsonl").write_text("".join(json.dumps(e) + "\n" for e in events))


def _session(label: str, minutes: float, locks: list[dict[str, Any]],
             gap_ms: float = 200.0) -> list[dict[str, Any]]:  # fmt: skip
    """A runner session: run_start, hp_read every gap_ms, the locks' records, run_end."""
    s = 1_000_000_000
    ev: list[dict[str, Any]] = [{"kind": "run_start", "t_ns": 0}]
    t = 0
    n = int(minutes * 60 * 1000 / gap_ms)
    ev += [{"kind": "hp_read", "pct": 90, "t_ns": int(i * gap_ms * 1e6)} for i in range(1, n)]
    for i, lk in enumerate(locks):
        t = (i + 1) * 10 * s
        ev.append({"kind": "recipe", "species": lk["sp"], "by": "box", "knife": lk["knife"],
                   "function": f"attack_{lk['sp']}", "t_ns": t})  # fmt: skip
        for rec in lk.get("bare", []):
            ev.append({"kind": "bare", **rec, "t_ns": t + s})
        if lk.get("kill"):
            ev.append({"kind": "kill", "by": "exp_line", "t_ns": t + 6 * s})
            ev.append({"kind": "loot_step", "t_ns": t + 7 * s})
        ev.append({"kind": "bare", "what": "opener", "ok": True, "by": "ready", "t_ns": t + 8 * s})
    ev.append({"kind": "run_end", "reason": "time_box", "t_ns": int(minutes * 60 * s)})
    return sorted(ev, key=lambda e: int(e["t_ns"]))


KNIFE_LOCK = [{"what": "begin", "ok": True, "by": "box"},
              {"what": "equip", "why": "popup", "ok": True, "ms": 340}]  # fmt: skip
PLAIN_LOCK = [{"what": "equip", "why": "recipe", "ok": True, "ms": 340},
              {"what": "recipe", "knife": False, "by": "box", "swap": True,
               "ok": True}]  # fmt: skip


def test_the_lock_reader_attributes_each_records_to_its_lock() -> None:
    ev = _session("x", 1.0, [
        {"sp": "cookie", "knife": False, "bare": PLAIN_LOCK, "kill": True},
        {"sp": "mystcase", "knife": True, "bare": KNIFE_LOCK, "kill": True},
        {"sp": None, "knife": True, "bare": [{"what": "begin", "ok": False, "by": "scan"},
                                             {"what": "opener", "ok": True, "by": "scan"}]},
        {"sp": "cookie_xmas", "knife": True, "bare": [{"what": "opener", "ok": False,
                                                       "by": "box"}]},
    ])  # fmt: skip
    locks, before = ab.locks_of([{"kind": "kill", "t_ns": 0}, *ev])
    assert before == 1 and [lk.species for lk in locks] == ["cookie", "mystcase", "?",
                                                            "cookie_xmas"]  # fmt: skip
    ck, mc, unk, cx = locks
    assert (ck.tried, ck.plain, ck.dagger_first, ck.steals, ck.kills, ck.kill_s) == (
        False, True, True, 0, 1, 6.0)  # fmt: skip
    assert (mc.tried, mc.struck, mc.steals, mc.plain) == (True, True, 1, False)
    assert (unk.tried, unk.struck) == (True, True)  # armed after all, then the opener at the strike
    assert (cx.tried, cx.struck) == (True, False)  # a failed opener is still a Knife TRY
    # the idle opener (by "ready") after each lock is nobody's Knife strike
    assert not any(lk.tried for lk in locks if lk.species == "cookie")


def test_score_run_reads_the_sessions_the_pace_and_a_traceback(tmp_path: Path) -> None:
    demo, folder = tmp_path / "demo", tmp_path / "s"
    folder.mkdir()
    _write(demo / "20261115T150000-demo-dungeon-rogue-xmas_dun02-patrol-P2-s-r02C-hunt1",
           _session("s-r02C", 20.0, [{"sp": "cookie", "knife": False, "bare": PLAIN_LOCK,
                                      "kill": True}] * 3, gap_ms=205.0))  # fmt: skip
    _write(demo / "20261115T150000-play-s-r02C", [{"kind": "run_end", "words": "Ended"}])
    (folder / "s-r02C.log").write_text(
        "...\nTraceback (most recent call last)\n  x\nKeyError: 'a'\n"
    )
    sc = ab.score_run({"label": "s-r02C", "arm": "C", "pair": 1}, folder, demo)
    assert sc.found and round(sc.minutes, 1) == 20.0 and sc.kills == 3 and sc.loot_steps == 3
    assert sc.locks_sp == {"cookie": 3} and sc.plain_sp == {"cookie": 3} and sc.tries_sp == {}
    assert sc.dagger_first == 3 and sc.kills_sp == {"cookie": 3}
    assert sc.openers == 3  # the idle ones: stage 5's count, every opener read on
    assert ab.s5b.pace(sc.gaps_ms)["median"] == 205.0 and sc.error == "KeyError: 'a'"
    assert sc.doc()["kill_s_median"] == {"cookie": 6.0}


def test_steal_values_draw_one_item_in_proportion_to_its_rate(tmp_path: Path) -> None:
    maps = {"maps": {"xmas_dun02": {"species": {
        "1": {"aegis": "COOKIE", "drops": [{"p": 0.1, "sell_oc": 600, "type": "Healing"},
                                           {"p": 0.1, "sell_oc": 200, "type": "Etc"},
                                           {"p": 0.0001, "sell_oc": 99999, "type": "Card"}]},
        "2": {"aegis": "MYSTCASE", "drops": []}}}}}  # fmt: skip
    p = tmp_path / "maps.json"
    p.write_text(json.dumps(maps))
    assert ab.steal_values(p) == {"cookie": 400.0}  # no card, no species without drops
    assert ab.steal_values(tmp_path / "missing.json") == {}


# --- the bar --------------------------------------------------------------------------------------
def _sc(label: str, arm: str, pair: int, **kw: Any) -> ab.Score6:
    ck = {"cookie": 4, "cookie_xmas": 3}
    oth = {"mystcase": 22, "cruiser": 14}
    base: dict[str, Any] = {
        "found": True, "minutes": 20.0, "kills": 48, "loot_steps": 55, "openers": 40,
        "gaps_ms": [201.0] * 50, "locks_sp": {**ck, **oth, "?": 20},
        "knife_sp": ({} if arm == "C" else ck) | oth | {"?": 20},
        "tries_sp": ({} if arm == "C" else ck) | oth | {"?": 20},
        "plain_sp": ck if arm == "C" else {}, "dagger_first": 7 if arm == "C" else 0,
        "steals_sp": {"mystcase": 9, "cruiser": 8, "?": 6, **({} if arm == "C" else {
            "cookie": 2, "cookie_xmas": 3})},
        "kills_sp": {"mystcase": 15, "cruiser": 11, "cookie": 4, "cookie_xmas": 3, "?": 15},
        "kill_s": {"cookie": [8.0, 7.5] if arm == "B" else [5.0, 5.5]},
    }  # fmt: skip
    base.update(kw)
    s = ab.Score6(label, arm, pair)
    for k, v in base.items():
        setattr(s, k, v)
    return s


def _six(**c_kw: Any) -> list[ab.Score6]:
    out = []
    for p in (1, 2, 3):
        out.append(_sc(f"r{p}B", "B", p, kills=48 + p))
        out.append(_sc(f"r{p}C", "C", p, **{"kills": 49 + p, **c_kw}))
    return out


def test_the_bar_passes_on_three_good_pairs_and_reports_the_cookie_steals() -> None:
    v = ab.verdict(_six(), 20.0, values={"cookie": 600.0, "cookie_xmas": 350.0})
    assert v["verdict"] == "PASS", v["lines"]
    ln = v["lines"]
    assert ln["plays"] == {"C_cookie_locks": 21, "C_knife_tries": 0, "C_plain_locks": 21,
                           "B_cookie_locks": 21, "B_knife_locks": 21,
                           "mismatch": {"B": 0, "C": 0}, "pass": True}  # fmt: skip
    assert ln["deaths"]["pass"] is True  # 0 vs 0: never a strict "<" against an arm at zero
    assert ln["others_h"] == {"B": 108.0, "C": 108.0, "share": 0.25, "pass": True}
    rep = ln["report"]
    assert rep["steals_h"]["B"]["cookie"] == 6.0 and rep["steals_h"]["C"]["cookie"] == 0.0
    # B steals 6 cookies + 9 christmas cookies an hour; C none: 6 x 600 + 9 x 350 lost
    zh = rep["steal_zeny"]["cookie_steal_z_h"]
    assert zh == {"B": {"cookie": 3600, "cookie_xmas": 3150}, "C": {"cookie": 0, "cookie_xmas": 0}}
    assert rep["steal_zeny"]["lost_z_h"] == 6750
    assert rep["kill_s_from_lock"]["C"]["cookie"] == {"median": 5.25, "n": 6}
    assert rep["dagger_first_h"] == {"B": 0.0, "C": 21.0} and rep["report_only"] is True
    assert ab.verdict(_six(), 20.0)["lines"]["report"]["steal_zeny"]["lost_z_h"] is None  # counts


@pytest.mark.parametrize(("c_kw", "why"), [
    ({"tries_sp": {"cookie": 1, "mystcase": 22, "cruiser": 14}}, "C tried the Knife on a cookie"),
    ({"plain_sp": {"cookie": 1}}, "C played its recipe on fewer than 5 cookie locks"),
    ({"mismatch_locks": 1}, "a lock's answer was not the plan"),
])  # fmt: skip
def test_the_plays_line_fails_when_c_swaps_on_a_cookie_or_its_recipe_never_played(
    c_kw: dict[str, Any], why: str
) -> None:
    v = ab.verdict(_six(**c_kw), 20.0)
    assert v["lines"]["plays"]["pass"] is False and v["verdict"] == "FAIL", why


def test_the_plays_line_needs_bs_positive_case() -> None:
    runs = [s if s.arm == "C" else _sc(s.label, "B", s.pair, knife_sp={"mystcase": 22,
                                                                       "cruiser": 14})
            for s in _six()]  # fmt: skip
    v = ab.verdict(runs, 20.0)
    assert v["lines"]["plays"]["B_knife_locks"] == 0 and v["lines"]["plays"]["pass"] is False
    only_b = [s for s in _six() if s.arm == "B"]
    assert ab.verdict(only_b, 20.0)["lines"]["plays"]["pass"] is None  # C never played


def test_deaths_count_over_every_run_that_played() -> None:
    runs = [*_six(), _sc("r4C", "C", 4, minutes=2.0, deaths=1)]  # short, invalid, but it played
    v = ab.verdict(runs, 20.0)
    assert v["lines"]["deaths"] == {"B": 0, "C": 1, "pass": False} and v["verdict"] == "FAIL"
    assert v["invalid"] == ["r4C"] and v["pairs_valid"] == 3
    runs[0].deaths = 1  # B died once too: C <= B
    assert ab.verdict(runs, 20.0)["lines"]["deaths"]["pass"] is True


def test_kills_per_hour_is_non_inferiority_over_three_valid_pairs() -> None:
    runs = _six()
    for s, k in zip([s for s in runs if s.arm == "C"], (30, 31, 29), strict=True):
        s.kills = k  # ~ -57 kills / h, SE ~2: far below -2 SE
    v = ab.verdict(runs, 20.0)
    assert v["lines"]["kills_h"]["pass"] is False and v["verdict"] == "FAIL"
    noisy = _six()
    for s, k in zip([s for s in noisy if s.arm == "C"], (40, 60, 45), strict=True):
        s.kills = k  # a lower mean but inside its own noise
    assert ab.verdict(noisy, 20.0)["lines"]["kills_h"]["pass"] is True
    two = _six()[:4]
    v2 = ab.verdict(two, 20.0)
    assert v2["lines"]["kills_h"]["pass"] is None and v2["verdict"] == "INCONCLUSIVE"


def test_the_other_monsters_knife_rate_is_held_to_25_percent() -> None:
    hi = ab.verdict(_six(knife_sp={"mystcase": 30, "cruiser": 16}), 20.0)  # 138 vs 108 /h: +28 %
    assert hi["lines"]["others_h"]["pass"] is False and hi["verdict"] == "FAIL"
    ok = ab.verdict(_six(knife_sp={"mystcase": 28, "cruiser": 16}), 20.0)  # 132 vs 108: +22 %
    assert ok["lines"]["others_h"]["pass"] is True
    lo = ab.verdict(_six(knife_sp={"mystcase": 16, "cruiser": 10}), 20.0)  # 78 vs 108: -28 %
    assert lo["lines"]["others_h"]["pass"] is False


def test_the_pace_line_judges_the_median_with_5_ms() -> None:
    slow = ab.verdict(_six(gaps_ms=[207.0] * 50), 20.0)
    assert slow["lines"]["pace"]["pass"] is False and slow["verdict"] == "FAIL"
    ok = ab.verdict(_six(gaps_ms=[205.0] * 49 + [3000.0]), 20.0)  # a long action: p95 not judged
    assert ok["lines"]["pace"]["pass"] is True and ok["verdict"] == "PASS"


def test_a_runner_exception_in_c_fails_and_in_b_is_reported() -> None:
    v = ab.verdict(_six(error="KeyError: 'x'"), 20.0)
    assert v["lines"]["errors"]["pass"] is False and v["verdict"] == "FAIL"
    runs = _six()
    runs[0].error = "ValueError"
    v2 = ab.verdict(runs, 20.0)
    assert v2["lines"]["errors"] == {"C": [], "B": ["r1B: ValueError"], "pass": True}


def test_no_valid_run_in_an_arm_is_inconclusive() -> None:
    runs = [s if s.arm == "B" else _sc(s.label, "C", s.pair, minutes=10.0) for s in _six()]
    v = ab.verdict(runs, 20.0)
    assert v["pairs_valid"] == 0 and v["verdict"] == "INCONCLUSIVE"
    assert v["lines"]["plays"]["pass"] is True  # the plays line counts every run that played
    assert ab.table(runs).splitlines()[0].startswith("run")
