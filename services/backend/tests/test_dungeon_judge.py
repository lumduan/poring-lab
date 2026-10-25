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


def test_sp_falls_with_a_maxsp_change_are_not_casts_gm_flagged_ones_still_count() -> None:
    """v55 run 0017 (REAL): the runner's state rebuild moved SP 110 -> 80 WITH MaxSP, read as an
    "Auto Guard" before this rule. T-S2 F f1c (REAL): a real Auto Guard's SP packet came 1.9 s
    after a GM spawn, inside the gm_command flag's 2 s: the flag cannot decide, so it counts."""
    packets = [
        sp(0, 312), pk(0, type="stat_change", name="max_hp", value=5260), hp(0, 5000),
        pk(5, type="stat_change", name="sp", value=282, gm_command=True),  # AG after a GM line
        pk(10, type="stat_change", name="max_sp", value=248), sp(10, 248),  # -34 with MaxSP
        pk(20, type="stat_change", name="max_hp", value=400), hp(20, 300),  # 75 % of 400
        sp(30, 214),  # a real Heal's -34 (no HP rise: unconfirmed)
    ]  # fmt: skip
    r = judge(run(1, 60), packets)
    assert r["autoguard"] == 1 and r["heals"] == 1 and r["sp_used"] == 30 + 34
    assert "1 SP fall(s) with a MaxSP change" in r["why"]["sp_falls_skipped"]
    assert "1 SP fall(s) within 2 s of a GM command" in r["why"]["sp_falls_gm_window"]
    assert r["hp_min"] == 300 and r["hp_min_pct"] == 0.75  # the MaxHP in force at the min


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


def test_a_sit_request_is_not_an_attack_and_sitting_regen_is_counted() -> None:
    """LIVE 2026-10-22 (the parent's check): sit / stand arrive as attack_request kind sit / stand,
    action 2 / 3, target = OUR OWN id, and as our act sit / stand (stand twice); natural regen
    ticks +32 every 3 s while sitting (the +-1 of regen_walk's 33), IRP 155 every 10 s."""
    packets = [hp(0, 4000), appear(0, MOB, 5)]
    packets += [
        pk(10, type="attack_request", target_gid=A, action=2, kind="sit", is_attack=False),
        pk(10.001, type="act", src_gid=A, target_gid=0, damage=0, kind="sit", action=2),
        hp(13, 4032), hp(16, 4064), pk(17, type="recovery", name="hp", var=5, amount=155),
        hp(19, 4251), hp(22, 4283),
        pk(25, type="attack_request", target_gid=A, action=3, kind="stand", is_attack=False),
        pk(25.001, type="act", src_gid=A, target_gid=0, damage=0, kind="stand", action=3),
        pk(25.001, type="act", src_gid=A, target_gid=0, damage=0, kind="stand", action=3),
        pk(26, type="attack_request", target_gid=A, action=7, kind="repeat", is_attack=True),
    ]  # fmt: skip
    events = run(1, 60, "B") + [
        ev(9.9, "press", what="sit", key="Insert", why="rest"),
        ev(24.9, "press", what="stand", key="Insert", why="full"),
    ]
    r = judge(events, packets)
    hb = r["hard_bars"]  # neither the sit / stand requests nor one aimed at ourselves count
    assert hb["attack_requests_non_monster"] == 0 and hb["attack_requests_unknown_target"] == 0
    assert dj.is_attack_request(packets[-1]) is False  # an attack aimed at OUR id: not ours
    assert r["rest"]["sitting_seconds"] == 15.0 and r["runner_vs_packets"]["sit"] == [1, 1]
    m = r["moving_hp_recovery"]
    assert m["natural_while_sitting"] == 4 and m["sitting_min"] == 0.25
    assert m["regen_hp_per_min_sitting"] == round((4 * 32 + 155) / 0.25, 1)
    assert dj.pool([r])["moving_hp_recovery"]["regen_hp_per_min_sitting"] == 1132.0


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
    assert m["regen_hp"] == 33 + 155 + 33 and m["regen_hp_resting"] == 33
    r = judge(events, packets)
    pm = dj.pool([r, r])["moving_hp_recovery"]  # pooled from the sums: the same rates
    assert pm["regen_hp_per_min"] == m["regen_hp_per_min"]
    assert pm["regen_hp_per_min_resting"] == m["regen_hp_per_min_resting"]
    assert pm["natural_while_walking"] == 2 and pm["irp_while_walking"] == 2
    assert "198.0" in dj.cells(dj.pool([r]))["regen"]


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
    if dj.present(dj.LIVE):  # the parent's live sit / Heal check (2026-10-22 11:3x)
        assert got["live sit-heal: Heals = 1, HP-confirmed (sp -34 and hp +544 at the same tick)"
                   ] == (1, 1)  # fmt: skip
        assert got["live sit-heal: natural ticks while sitting (every 3 s: 9 in 26.7 s)"] == 9
    if table is not None:
        assert got["hunt v55: kills == econ_row (search_study window)"] == 116
        assert got["hunt v55: gross / cost / net z/h == econ_row"] == (802.3, 0.0, 802.3)


def test_live_window_is_first_input_plus_seconds_capped_at_the_end() -> None:
    man = {"t0_live_ns": 10 * dj.NS, "t_end_ns": 900 * dj.NS}
    assert dj.live_window(man, 600) == (10 * dj.NS, 610 * dj.NS)
    assert dj.live_window(man, 3600) == (10 * dj.NS, 900 * dj.NS)  # capped at the recording
    with pytest.raises(ValueError):
        dj.live_window({"t_end_ns": 5}, 600)  # never played: no window invented


def test_item_gains_by_cause_and_the_per_hour_table() -> None:
    """Batt 2026-10-24: every item per hour, by cause. A gain right after our pickup request is
    picked, right after a Steal's SP fall is stolen, anything else (a GM @item) is other; a failed
    pickup_result is no gain."""
    S = dj.NS
    pk = [
        {"type": "pickup_request", "t_mono_ns": 10 * S, "floor_id": 7},
        {"type": "pickup_result", "t_mono_ns": 10 * S + S // 2, "ok": True, "item_id": 907,
         "amount": 1},
        {"type": "pickup_result", "t_mono_ns": 20 * S, "ok": True, "item_id": 907, "amount": 1},
        {"type": "pickup_result", "t_mono_ns": 40 * S, "ok": True, "item_id": 604, "amount": 1},
        {"type": "pickup_result", "t_mono_ns": 41 * S, "ok": False, "item_id": 0, "amount": 0},
        {"type": "pickup_result", "t_mono_ns": 99 * S, "ok": True, "item_id": 518, "amount": 1},
    ]  # fmt: skip
    g = dj.item_gains(pk, 0, 60 * S, steal_falls=[int(19.5 * S)])
    assert g == {"604": {"other": 1}, "907": {"picked": 1, "stolen": 1}}
    rows = dj.items_rows(g, 0.5, {"907": "Resin"})
    assert [(x["name"], x["total"], x["per_h"], x["target"]) for x in rows] == [
        ("Resin", 2, 4.0, False), ("Dead Branch", 1, 2.0, True)]  # fmt: skip
    pooled = dj.pool_items([{"hours": 0.5, "items": rows}, {"hours": 0.5, "items": rows}])
    assert [(x["item_id"], x["picked"], x["stolen"], x["per_h"]) for x in pooled] == [
        (907, 2, 2, 4.0), (604, 0, 0, 2.0)]  # fmt: skip
    assert "* Dead Branch" in dj.items_box(rows, "t")


def _fall(t_s: float, fid: int, item: int, x: int, y: int) -> dict[str, object]:
    return {"type": "floor_item_appear", "t_mono_ns": int(t_s * dj.NS), "kind": "fall",
            "floor_id": fid, "item_id": item, "x": x, "y": y, "amount": 1}  # fmt: skip


def test_staged_floor_ids_flag_a_looters_returned_set_not_a_natural_drop() -> None:
    """staged-items-looter-contamination: a pile with >= 3 DIFFERENT target ids (no pay_fild07
    species drops more than two) is a staged set back from a looter. The s3 shape: four target
    ids over 324..326 x 57..58 plus the Poporing's Sticky Mucus, in one batch. The looter's own
    drop stays income; a natural Elder Willow pile (Dead Branch + Rough Elunium + Resin) is not
    flagged; neither are three target ids 3 cells or 1 s apart."""
    pk = [
        _fall(978.8, 236, 757, 324, 58), _fall(978.8, 237, 756, 326, 57),
        _fall(978.8, 238, 604, 324, 58), _fall(978.8, 239, 518, 326, 58),
        _fall(978.8, 240, 938, 325, 58),  # the looter's own drop
        _fall(10.0, 50, 604, 100, 100), _fall(10.0, 51, 757, 101, 101),
        _fall(10.0, 52, 907, 99, 100),  # a natural Elder Willow pile: two target ids
        _fall(20.0, 60, 604, 200, 200), _fall(20.0, 61, 757, 203, 200),
        _fall(20.0, 62, 518, 206, 200),  # three target ids, but 3 cells apart: no pile
        _fall(30.0, 70, 604, 300, 300), _fall(31.0, 71, 757, 300, 300),
        _fall(32.0, 72, 518, 300, 300),  # three target ids, but 1 s apart: no pile
    ]  # fmt: skip
    assert dj.staged_floor_ids(pk) == {236, 237, 238, 239}


def test_a_gain_inside_our_own_attack_is_snatched_and_counts_as_income() -> None:
    """dungeon@8: the Rogue's Snatcher steals inside its attack -- a gain with no pickup request
    and no Steal SP fall just before, but OUR attack act <= SNATCH_S before it, is "snatched" (in
    the total); a gain with neither stays "other"; a pickup still wins over an attack."""
    S = dj.NS
    pk = [
        {"type": "pickup_result", "t_mono_ns": 10 * S + S // 2, "ok": True, "item_id": 7053,
         "amount": 1},
        {"type": "pickup_result", "t_mono_ns": 30 * S, "ok": True, "item_id": 931, "amount": 1},
        {"type": "pickup_request", "t_mono_ns": 50 * S, "floor_id": 9},
        {"type": "pickup_result", "t_mono_ns": 50 * S + S // 4, "ok": True, "item_id": 931,
         "amount": 1},
    ]  # fmt: skip
    g = dj.item_gains(pk, 0, 60 * S, attacks=[10 * S, 50 * S])
    assert g == {"7053": {"snatched": 1}, "931": {"other": 1, "picked": 1}}
    rows = dj.items_rows(g, 0.5)
    assert [(x["item_id"], x["snatched"], x["total"]) for x in rows] == [(931, 0, 2), (7053, 1, 1)]
    assert dj.pool_items([{"hours": 0.5, "items": rows}])[1]["snatched"] == 1
    assert "snatched" in dj.items_box(rows, "t")
    assert dj.item_gains(pk, 0, 60 * S) == {"7053": {"other": 1}, "931": {"other": 1, "picked": 1}}


def test_item_gains_count_a_staged_pickup_apart_and_out_of_the_total() -> None:
    """A pickup whose request names a staged floor id is "staged": shown in the table and pooled,
    never in the total or the per-hour rate."""
    S = dj.NS
    pk = [
        {"type": "pickup_request", "t_mono_ns": 10 * S, "floor_id": 238},
        {"type": "pickup_result", "t_mono_ns": 10 * S + S // 2, "ok": True, "item_id": 604,
         "amount": 1},
        {"type": "pickup_request", "t_mono_ns": 30 * S, "floor_id": 50},
        {"type": "pickup_result", "t_mono_ns": 30 * S + S // 2, "ok": True, "item_id": 604,
         "amount": 1},
    ]  # fmt: skip
    g = dj.item_gains(pk, 0, 60 * S, staged={236, 237, 238, 239})
    assert g == {"604": {"staged": 1, "picked": 1}}
    rows = dj.items_rows(g, 0.5)
    assert [(x["picked"], x["staged"], x["total"], x["per_h"]) for x in rows] == [(1, 1, 1, 2.0)]
    pooled = dj.pool_items([{"hours": 0.5, "items": rows}, {"hours": 0.5, "items": rows}])
    assert [(x["staged"], x["total"], x["per_h"]) for x in pooled] == [(2, 2, 2.0)]
    box = dj.items_box(rows, "t").splitlines()
    assert "staged" in box[2] and len({len(x) for x in box[1:]}) == 1


S3 = "20261024T185652-demo-dungeon-thief-pay_fild07-B-s3"
S7 = "20261024T225301-demo-dungeon-thief-pay_fild07-B-s7"


@pytest.mark.skipif(not _have(S3, S7), reason="the 4.04 s3 / s7 sessions are not here")
def test_real_staged_sets_back_from_looters_in_404_s3_and_s7() -> None:
    """The REAL positive case: 4.04 s3 (18:5x) and s7 (22:5x) each picked a staged set a Poporing
    had looted (all four target ids in one pile beside Sticky Mucus); s3's natural Dead Branch
    beside Resin (floor id 220, an Elder Willow kill) stays income."""
    st3 = dj.staged_floor_ids(dj.load(S3)[1])
    assert st3 == {236, 237, 238, 239} and 220 not in st3
    assert dj.staged_floor_ids(dj.load(S7)[1]) == {375, 376, 377, 378}


P405 = "20261025T200925-demo-dungeon-rogue-gef_fild10-B-pilot"


@pytest.mark.skipif(not _have(P405), reason="the 4.05 pilot session is not here")
def test_real_snatcher_gains_in_the_405_pilot() -> None:
    """The REAL positive case (4.05's pilot, arm N, 2026-10-25 20:09-20:24): 7 gains with no
    pickup request and no Steal, each 0.289-0.306 s after OUR attack act, and each an item of the
    attacked species' drop table (Cyfar <- Orc Lady x6, Orcish Voucher <- Orc Warrior x1)."""
    row = dj.row(P405, None, map_name="gef_fild10")
    got = {it["item_id"]: (it["picked"], it["snatched"], it["other"]) for it in row["items"]}
    assert got == {7053: (5, 6, 0), 931: (3, 1, 0), 756: (1, 0, 0)}


def test_steal_by_species_names_the_monster_our_next_attack_hits() -> None:
    """dungeon@7 (a Steal on every monster): each Steal's SP fall is credited to the monster OUR
    next attack act hits within STEAL_TARGET_S (its entity_appear name); stolen = an item gained
    within STEAL_S with no pickup request of ours just before it."""
    me, s = 2000002, 10**9
    pk = [
        {"type": "entity_appear", "gid": 7, "name": "Elder Willow", "t_mono_ns": 0},
        {"type": "entity_appear", "gid": 8, "name": "Bigfoot", "t_mono_ns": 0},
        # Steal 1 at 10 s: Resin in at 10.5 s, then our hit on the Elder Willow at 12 s
        {"type": "pickup_result", "ok": True, "item_id": 907, "t_mono_ns": 10 * s + s // 2},
        {"type": "act", "src_gid": me, "target_gid": 7, "action": 0, "t_mono_ns": 12 * s},
        # Steal 2 at 30 s: nothing gained; a sit (action 2) is no attack; the Bigfoot hit at 31 s
        {"type": "act", "src_gid": me, "target_gid": me, "action": 2, "t_mono_ns": 30 * s + 1},
        {"type": "act", "src_gid": me, "target_gid": 8, "action": 8, "t_mono_ns": 31 * s},
        # Steal 3 at 50 s: a PICKUP's gain (request at 49.9 s) is not a steal; no attack follows
        {"type": "pickup_request", "t_mono_ns": 49 * s + 9 * s // 10},
        {"type": "pickup_result", "ok": True, "item_id": 907, "t_mono_ns": 50 * s + s // 4},
        {"type": "act", "src_gid": me, "target_gid": 7, "action": 0, "t_mono_ns": 80 * s},
    ]
    got = dj.steal_by_species(pk, [10 * s, 30 * s, 50 * s], me)
    assert got == {"Elder Willow": {"tries": 1, "stolen": 1}, "Bigfoot": {"tries": 1, "stolen": 0},
                   "unknown": {"tries": 1, "stolen": 0}}  # fmt: skip
    # the 4.04 pilot: a stolen item and its SP fall share a packet batch, so the SAME t_mono_ns
    pk2 = [*pk, {"type": "pickup_result", "ok": True, "item_id": 907, "t_mono_ns": 30 * s}]
    assert dj.steal_by_species(pk2, [10 * s, 30 * s, 50 * s], me)["Bigfoot"]["stolen"] == 1
