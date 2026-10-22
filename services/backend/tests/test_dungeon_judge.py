"""dungeon_judge.py (2026-10-22): the orcsdun01 sustain runs' offline judge (A potions / B rest /
C heal) -- synthetic runs for every column, and the REAL positive cases (each column against the
judge that already owns it) when the banked sessions are on this host."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))

import dungeon_judge as dj  # noqa: E402

S = 10**9
A = dj.AID
MOB, NPC = 7, 9


def pk(t: float, **kw: object) -> dict:
    return {"t_mono_ns": int(t * S), **kw}


def ev(t: float, kind: str, **kw: object) -> dict:
    return {"t_ns": int(t * S), "kind": kind, **kw}


def hp(t: float, v: int) -> dict:
    return pk(t, type="stat_change", name="hp", value=v)


def sp(t: float, v: int) -> dict:
    return pk(t, type="stat_change", name="sp", value=v)


def appear(t: float, gid: int, objtype: int, x: int = 10, y: int = 10, job: int = 1152) -> dict:
    return pk(t, type="entity_appear", gid=gid, objtype=objtype, x=x, y=y, job=job)


def run(t0: float, t1: float, strategy: str = "A", **kw: object) -> list[dict]:
    return [ev(t0, "run_start", strategy=strategy, seed=1, version="t", minutes=45.0,
               map="orcsdun01"), ev(t1, "run_end", reason=kw.get("reason", "time_box"),
                                    counts={})]  # fmt: skip


def judge(events: list[dict], packets: list[dict], table: dict | None = None) -> dict:
    events = sorted(events, key=lambda e: e["t_ns"])
    packets = sorted(packets, key=lambda e: e["t_mono_ns"])
    return dj.judge(events, packets, table, {"sid": "20261022T120000-test"})


# --- the window -----------------------------------------------------------------------------------


def test_the_window_is_run_start_to_run_end_else_the_manifest() -> None:
    got = dj.window(run(5, 65), {"t0_ns": 1, "t1_ns": 2})
    assert got == (5 * S, 65 * S, "events run_start..run_end")
    assert dj.window([ev(3, "hp_read")], {"t0_ns": 1, "t1_ns": 2})[:2] == (1, 2)  # a trial
    assert dj.window([], {"t0_mono_ns": 7, "t1_mono_ns": 9})[2] == "manifest t0_mono_ns..t1_mono_ns"


# --- the Heal detector (NO real Heal session exists yet: synthetic only) -------------------------


def test_heals_are_sp_falls_of_34_confirmed_by_the_hp_rise() -> None:
    packets = [
        pk(0, type="stat_change", name="max_hp", value=5260), hp(0, 3000), sp(0, 312),
        sp(10, 278), hp(10.2, 3544),  # a Heal: -34 SP, +544 HP (absolute packet)
        sp(20, 248),  # Auto Guard: -30, not a Heal
        hp(25, 4900), sp(30, 214), hp(30.3, 5260),  # a CAPPED Heal: +360, ends at MaxHP
        sp(40, 180),  # -34 with no HP rise (cast at full HP): a cast, not confirmed
        hp(45, 4000), sp(50, 146),
        pk(50.1, type="recovery", name="hp", var=5, amount=544),  # a Heal sent as ZC_RECOVERY
        hp(53, 4000), sp(55, 112), hp(55.5, 4033),  # -34, only a natural +33: not confirmed
    ]  # fmt: skip
    r = judge(run(1, 60), packets)
    assert r["heals"] == 5 and r["heals_confirmed"] == 3
    assert r["heal_detail"]["times_s"] == [9.0, 29.0, 39.0, 49.0, 54.0]
    assert "no skill-use packet" in r["heal_detail"]["via"]
    assert r["autoguard"] == 1 and r["sp_used"] == 5 * 34 + 30 and r["sp_min"] == 112
    assert r["sp_start"] == 312 and "sp_start" not in r["why"]
    assert r["heals_h"] == round(5 / (59 / 3600), 2)
    m = r["moving_hp_recovery"]  # the 544 recovery is a Heal, not an IRP tick
    assert m["irp_ticks"] == 0 and m["recovery_not_regen"] == 1
    assert r["runner_vs_packets"]["heal"] == [0, 5]


def test_the_sp_at_the_start_is_assumed_maxsp_only_when_no_packet_precedes_it() -> None:
    r = judge(run(1, 60), [hp(0, 3000), sp(10, 278), hp(10.1, 3544)])
    assert r["heals"] == 1 and r["heals_confirmed"] == 1
    assert r["sp_start"] == dj.MAX_SP and "ASSUMED" in r["why"]["sp_start"]


# --- events: strikes and their landing, rest spans, the sit cross-check --------------------------


def test_a_strike_lands_with_our_attack_request_and_our_act_on_a_monster_within_1_5_s() -> None:
    packets = [
        appear(0, MOB, 5), appear(0, NPC, 6),
        pk(10.4, type="attack_request", target_gid=MOB, action=7, kind="repeat", is_attack=True),
        pk(10.9, type="act", src_gid=A, target_gid=MOB, damage=50, kind="normal"),  # landed
        pk(20.5, type="attack_request", target_gid=MOB, action=7, kind="repeat", is_attack=True),
        pk(30.2, type="attack_request", target_gid=NPC, action=0, kind="normal", is_attack=True),
        pk(30.6, type="act", src_gid=A, target_gid=NPC, damage=0, kind="normal"),  # not a monster
        pk(41.8, type="attack_request", target_gid=MOB, action=7, kind="repeat", is_attack=True),
        pk(42.0, type="act", src_gid=A, target_gid=MOB, damage=50, kind="normal"),  # too late
        pk(45.0, type="attack_request", target_gid=11, action=7, kind="repeat", is_attack=True),
        pk(46.0, type="attack_request", target_gid=0, action=2, kind="sit", is_attack=False),
    ]  # fmt: skip
    events = run(1, 100) + [ev(t, "strike", u=1.0, v=2.0, clicks=1, arrow_s=None, end="ok")
                            for t in (10, 20, 30, 40)]  # fmt: skip
    events += [ev(9, "engage", by="battle_log", name=None), ev(19, "engage", by="hp_drop",
                                                               name=None),
               ev(29, "engage", by="box", name="Orc Warrior"),
               ev(39, "engage", by="hp_drop", name=None)]  # fmt: skip
    r = judge(events, packets)
    assert r["strikes"] == {"n": 4, "landed": 1, "request_only": 2, "landed_rate": 0.25,
                            "ends": {"ok": 4}}  # fmt: skip
    assert r["engagements"] == {"battle_log": 1, "hp_drop": 2, "box": 1}
    hb = r["hard_bars"]  # the NPC attack is a bar; a never-seen target is reported, not a bar
    assert hb["attack_requests_non_monster"] == 1 and hb["attack_requests_unknown_target"] == 1
    assert hb["pass"] is False


def test_resting_spans_and_the_sitting_cross_check() -> None:
    events = run(0, 520, "B") + [ev(100, "rest_start", cell=[1, 2], pct=40, sp_pct=90),
                                 ev(160, "rest_end", why="full", pct=100, sp_pct=100),
                                 ev(500, "rest_start", cell=[1, 2], pct=50, sp_pct=90)]  # fmt: skip
    packets = [pk(101, type="act", src_gid=A, target_gid=0, damage=0, kind="sit"),
               pk(159, type="act", src_gid=A, target_gid=0, damage=0, kind="stand"),
               pk(300, type="act", src_gid=123, target_gid=0, damage=0, kind="sit"),  # not ours
               pk(501, type="act", src_gid=A, target_gid=0, damage=0, kind="sit")]  # fmt: skip
    r = judge(events, packets)
    assert r["rest"]["spans"] == 2 and r["rest"]["seconds"] == 80.0  # the open one ends at t1
    assert r["resting_pct"] == round(80 / 520, 4)
    assert r["sitting_pct"] == round((58 + 19) / 520, 4)
    assert r["rest"]["sitting_share_of_rest"] == round(77 / 80, 4)
    assert r["rest"]["sitting_seconds"] == 77.0 and r["runner_vs_packets"]["sit"] == [0, 2]
    assert dj.pool([r, r])["sitting_pct"] == r["sitting_pct"]
    assert r["rest"]["end_why"] == {"full": 1, "open at the window's end": 1}
    assert r["strategy"] == "B"


# --- packets: Moving HP Recovery, the hard bars ---------------------------------------------------


def test_natural_ticks_while_walking_are_moving_hp_recoverys_evidence() -> None:
    # NO real positive case exists (3.96f: every natural tick fell in a standing gap): synthetic
    packets = [
        hp(5, 3000),
        pk(10, type="self_move", x0=0, y0=0, x1=100, y1=0, server_tick=0),  # 100 cells = 15 s
        hp(17, 3033),  # a natural tick WHILE walking: MHR
        pk(18, type="recovery", name="hp", var=5, amount=155),  # IRP while walking: must be 0
        hp(30, 3221),  # 3033 + 155 + 33: a natural tick, standing (inside the rest span)
        hp(32, 3721),  # a potion's +500: not regen
    ]  # fmt: skip
    events = run(0, 60) + [ev(25, "rest_start", cell=[0, 0], pct=60, sp_pct=None),
                           ev(35, "rest_end", why="full", pct=None, sp_pct=None)]  # fmt: skip
    m = judge(events, packets)["moving_hp_recovery"]
    assert (m["natural_ticks"], m["natural_while_walking"]) == (2, 1)
    assert (m["irp_ticks"], m["irp_while_walking"]) == (1, 1)
    assert m["walking_min"] == 0.25 and m["walking_share"] == round(15 / 60, 4)
    assert m["regen_hp_per_min"] == round((33 + 155 + 33) / 1.0, 1)
    assert m["regen_hp_per_min_resting"] == round(33 / (10 / 60), 1)


def test_a_fly_wing_is_a_same_map_teleport_and_another_map_is_the_bar() -> None:
    packets = [
        pk(0.5, type="map_change", map="orcsdun01.gat", x=1, y=1, gm_command=True),  # before t0
        pk(10, type="use_item_result", item_id=601, aid=A, ok=True, index=3, amount=9),
        pk(10.05, type="map_change", map="orcsdun01.gat", x=50, y=60, gm_command=False),
        pk(20, type="npc_contact", npc_gid=110000895, contact_type=1),
        pk(30, type="map_change", map="prontera.gat", x=150, y=150, gm_command=False),
    ]  # fmt: skip
    r = judge(run(1, 60) + [ev(9.9, "escape", how="fly", why="hp")], packets)
    assert r["fly_wings"] == 1 and r["escapes"] == 1
    hb = r["hard_bars"]
    assert hb["map_changes_same_map"] == 1 and hb["same_map_by_gm_command"] == 0
    assert hb["map_changes_other"] == 1 and hb["other_maps"] == ["prontera"]
    assert hb["npc_contacts"] == 1 and hb["pass"] is False


# --- a whole run, its economics, the pooling and the table ----------------------------------------

TABLE = {
    "504": {"npc_buy": 1200, "npc_buy_dc10": 912, "type": "Healing", "sell": 600,
            "sell_oc10": 744, "weight": 15.0},
    "601": {"npc_buy": 60, "npc_buy_dc10": 45, "type": "Delayconsume", "sell": 30,
            "sell_oc10": 37, "weight": 5.0},
    "909": {"sell": 3, "sell_oc10": 3, "weight": 1.0, "type": "Etc"},
}  # fmt: skip


def a_run(t0: float, kills: int, potions: int, strategy: str = "A", death: bool = False
          ) -> tuple[list[dict], list[dict]]:  # fmt: skip
    """A 1-hour run: ``kills`` kills of ours each dropping one Jellopy (909, 3 z) we pick up,
    ``potions`` White Potions of ours (and one of somebody else's), one Fly Wing."""
    events = [ev(t0, "run_start", strategy=strategy, seed=1, version="t", minutes=60.0,
                 map="orcsdun01")]  # fmt: skip
    packets = [hp(t0 - 1, 5260), pk(t0 - 1, type="stat_change", name="max_hp", value=5260),
               sp(t0 - 1, 312)]  # fmt: skip
    for k in range(kills):
        t, g, f = t0 + 60 + 120 * k, 1000 + k, 5000 + k
        packets += [
            appear(t - 10, g, 5),
            pk(t - 0.5, type="attack_request", target_gid=g, action=7, kind="repeat",
               is_attack=True),
            pk(t, type="act", src_gid=A, target_gid=g, damage=300, kind="normal"),
            pk(t + 0.2, type="floor_item_appear", kind="fall", floor_id=f, item_id=909, x=10,
               y=10, amount=1, identified=True, sub_x=0, sub_y=0),
            pk(t + 0.5, type="entity_vanish", gid=g, reason=1),
            pk(t + 2, type="pickup_request", floor_id=f),
            pk(t + 2.1, type="pickup_result", ok=True, item_id=909, amount=1),
            pk(t + 2.1, type="floor_item_vanish", floor_id=f),
            hp(t + 3, 5000),
        ]  # fmt: skip
        events += [ev(t - 1, "engage", by="battle_log", name=None),
                   ev(t - 0.8, "strike", u=1.0, v=2.0, clicks=1, arrow_s=0.2, end="ok"),
                   ev(t + 1, "kill", by="exp_line", name=None)]  # fmt: skip
    for i in range(potions):
        packets.append(pk(t0 + 30 + 300 * i, type="use_item_result", item_id=504, aid=A, ok=True))
        events.append(ev(t0 + 29.9 + 300 * i, "press", what="potion", key="F1", why="hp<60"))
    events.append(ev(t0 + 2000, "press", what="potion", key="F1", why="hp<60"))  # did nothing
    packets.append(pk(t0 + 31, type="use_item_result", item_id=504, aid=123, ok=True))  # theirs
    packets.append(pk(t0 + 3000, type="use_item_result", item_id=601, aid=A, ok=True))
    if death:
        packets += [hp(t0 + 3500, 1), pk(t0 + 3500, type="entity_vanish", gid=A, reason=1)]
        events.append(ev(t0 + 3501, "death"))
    events.append(ev(t0 + 3600, "run_end", reason="death" if death else "time_box", counts={}))
    return events, packets


def test_a_whole_run_row() -> None:
    r = judge(*a_run(100, kills=4, potions=2), table=TABLE)
    assert r["hours"] == 1.0 and r["window"]["source"] == "events run_start..run_end"
    assert r["kills"] == 4 and r["kills_h"] == 4.0 and r["runner_kills"] == 4
    assert r["potions"] == 2 and r["fly_wings"] == 1 and r["deaths"] == 0
    assert r["picked_value"] == 12.0 and r["gross_h"] == 12.0
    assert r["cost"] == 2 * 1200 + 60 and r["net_h"] == 12.0 - 2460
    assert r["cost_ratio"] == round(2460 / 12, 4)
    assert r["economics"]["consumables"] == {"potion": 2, "fly_wing": 1}
    assert r["economics"]["windows_10min"] == 6 and r["sharpe_10min"] is not None
    assert r["loot_completeness"] == 1.0 and r["loot"]["items"] == 4
    assert r["strikes"]["landed"] == 4 and r["engagements"] == {"battle_log": 4}
    assert r["hp_min"] == 5000 and r["hp_min_pct"] == round(5000 / 5260, 4)
    assert r["hard_bars"]["pass"] is True and r["end_reason"] == "time_box"
    rv = r["runner_vs_packets"]
    assert rv["kills"] == [4, 4] and rv["potion"] == [3, 2] and rv["deaths"] == [0, 0]


def test_no_item_table_is_said_never_invented() -> None:
    r = judge(*a_run(100, kills=1, potions=0))
    assert r["gross_h"] is None and r["net_h"] is None and "economics" in r["why"]
    assert r["kills"] == 1 and r["loot_completeness"] == 1.0  # the packet columns stand


def test_pooled_per_strategy_rates_from_the_sums_and_the_box() -> None:
    rows = [judge(*a_run(100, kills=4, potions=2), table=TABLE),
            judge(*a_run(10_000, kills=2, potions=0, death=True), table=TABLE),
            judge(*a_run(20_000, kills=3, potions=0, strategy="B"), table=TABLE)]  # fmt: skip
    p = dj.by_strategy(rows)
    assert list(p) == ["A", "B"]
    a = p["A"]
    assert a["runs"] == 2 and a["hours"] == 2.0 and a["kills"] == 6 and a["kills_h"] == 3.0
    assert a["deaths"] == 1 and a["deaths_h"] == 0.5 and a["hp_min"] == 1
    assert a["potions_h"] == 1.0 and a["fly_wings"] == 2
    assert a["gross_h"] == 9.0 and a["net_h"] == round((18 - 2400 - 120) / 2, 1)
    assert a["economics"]["windows_10min"] == 12
    assert a["strikes"] == {"n": 6, "landed": 6, "landed_rate": 1.0}
    assert a["end_reason"] == "time_box x1, death x1"
    text = dj.box([(f"{k} pooled", v) for k, v in p.items()], "BY STRATEGY (pooled)")
    lines = text.splitlines()
    assert len({len(x) for x in lines}) == 1  # every line the same width
    assert "A pooled" in lines[1] and "B pooled" in lines[1]
    assert any(x.startswith("│ NET z / h") for x in lines)
    assert dj.run_label(rows[0]) == "A 1200"


# --- REAL positive cases (banked sessions; the item table is built locally at run time) ---------


def _have(*sids: str) -> bool:
    return all((dj.session_dir(s) / "packets.jsonl.gz").exists() for s in sids)


REAL = (*dj.SURVIVAL.values(), dj.REGEN, dj.HUNT, dj.HARD)


@pytest.mark.skipif(not _have(*REAL), reason="the banked positive-case sessions are not here")
def test_real_positive_cases_agree_with_the_judges_that_own_each_column() -> None:
    """Every column against its owner on a REAL session: survive_judge (potions, Fly Wings,
    deaths, Auto Guard, HP min), regen_walk (ticks while walking), econ_row + loot_complete
    (kills, zeny, Sharpe-like, completeness on the v55 run's search_study window), and the
    hard bars on the 10-08 garnet safety check (a warp to prt_church, an NPC contact)."""
    import econ_items as ei

    env = os.environ.get("PORING_LAB_ECON_ITEMS")  # a worktree: the main checkout's table
    table = dj.load_table(Path(env) if env else ei.OUT)
    res = dj.positive(table)
    bad = [x for x in res if x["ok"] is False]
    assert not bad, bad
    assert sum(x["ok"] is True for x in res) >= 28
    got = {x["case"]: x["got"] for x in res}
    assert got["potions 193536: potions == survive_judge S2"] == 26
    assert got["death 184414: deaths == survive_judge S6"] == 1
    assert got["autoguard 235737: Auto Guard == survive_judge S4"] == 1
    if table is not None:
        assert got["hunt v55: kills == econ_row (search_study window)"] == 116
        assert got["hunt v55: gross / cost / net z/h == econ_row"] == (802.3, 0.0, 802.3)
