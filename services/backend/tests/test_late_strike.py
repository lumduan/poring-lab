"""scripts/late_strike.py (rogue-xmas02.md Study S-LS): a box strike is LATE when its target moved
>= 1 cell between the picture the box came from and the client's resolve of the click. Synthetic
records in the sessions' own schema, and one REAL late strike copied from p49."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))

import late_strike as lst  # noqa: E402

S = 1_000_000_000
MS = 1_000_000
US, MOB, DECOY = 2000002, 110000001, 110000002


def appear_move(t_ns: int, gid: int, x: int, y: int, x1: int, y1: int, speed: int = 400,
                name: str = "Myst Case", job: int = 1249) -> dict[str, object]:  # fmt: skip
    return {"type": "entity_appear", "t_mono_ns": t_ns, "gid": gid, "objtype": 5, "kind": "move",
            "x": x, "y": y, "x1": x1, "y1": y1, "move_start_tick": t_ns // MS, "speed": speed,
            "name": name, "job": job}  # fmt: skip


def appear_stand(t_ns: int, gid: int, x: int, y: int, name: str = "Cruiser",
                 job: int = 1248) -> dict[str, object]:  # fmt: skip
    return {"type": "entity_appear", "t_mono_ns": t_ns, "gid": gid, "objtype": 5, "kind": "stand",
            "x": x, "y": y, "speed": 400, "name": name, "job": job}  # fmt: skip


def self_move(t_ns: int, x0: int, y0: int, x1: int, y1: int) -> dict[str, object]:
    return {"type": "self_move", "t_mono_ns": t_ns, "server_tick": t_ns // MS, "x0": x0,
            "y0": y0, "x1": x1, "y1": y1}  # fmt: skip


def walk_req(t_ns: int, x: int, y: int) -> dict[str, object]:
    return {"type": "self_move_request", "t_mono_ns": t_ns, "x": x, "y": y}


def attack_req(t_ns: int, gid: int) -> dict[str, object]:
    return {"type": "attack_request", "t_mono_ns": t_ns, "target_gid": gid}


def test_walk_interpolation_follows_rathena_steps() -> None:
    # diagonal first (560 ms a step at speed 400), then straight (400 ms)
    seg = lst.Seg(0, "move", 89, 113, 86, 106, t_start=0, speed=400.0)
    assert seg.at(-5) == (89.0, 113.0, True)
    x, y, walking = seg.at(1680 * MS)
    assert (round(x, 3), round(y, 3), walking) == (86.0, 110.0, True)
    x, y, _ = seg.at(2080 * MS + 200 * MS)  # halfway into the straight step (86,109) -> (86,108)
    assert (round(x, 3), round(y, 3)) == (86.0, 108.5)
    assert seg.at(10 * S) == (86.0, 106.0, False)
    assert seg.duration_ns() == (3 * 560 + 4 * 400) * MS


def test_tracks_stop_and_vanish() -> None:
    pk = [appear_move(1 * S, MOB, 10, 10, 13, 10), self_move(1 * S, 0, 0, 2, 0),
          {"type": "entity_stop", "t_mono_ns": int(1.5 * S), "gid": MOB, "x": 11, "y": 10},
          {"type": "entity_vanish", "t_mono_ns": 3 * S, "gid": MOB, "reason": 1}]  # fmt: skip
    mobs, ours = lst.tracks(pk)
    assert lst.pos_at(mobs[MOB], int(0.5 * S)) is None  # before it appeared
    assert lst.pos_at(mobs[MOB], int(1.2 * S)) == (10.5, 10.0, True)
    assert lst.pos_at(mobs[MOB], 2 * S) == (11.0, 10.0, False)
    assert lst.pos_at(mobs[MOB], 4 * S) is None  # gone
    assert lst.pos_at(ours, 2 * S) == (2.0, 0.0, False)
    assert lst.last_walk_end(ours, 2 * S) == 1 * S + 300 * MS


def test_target_attacked_wins_over_the_nearest() -> None:
    pk = [appear_stand(1 * S, MOB, 10, 10), appear_stand(1 * S, DECOY, 11, 11)]
    mobs, _ = lst.tracks(pk)
    assert lst.pick_target(mobs, (10.5, 10.75), 2 * S) == (DECOY, 0.5)
    assert lst.pick_target(mobs, (10.5, 10.75), 2 * S, attacked=[MOB]) == (MOB, 0.75)
    assert lst.pick_target(mobs, (20, 20), 2 * S) is None


def test_late_kinds() -> None:
    walker = [lst.Seg(0, "move", 0, 0, 5, 0, t_start=0, speed=400.0)]
    assert lst.late_kind(walker, 1 * S, int(1.16 * S), 2 * S, 2.0)[0] == "walking"
    assert lst.late_kind(walker, 1 * S, int(1.16 * S), 2 * S, 0.5)[0] is None  # not late
    later = [lst.Seg(0, "stand", 0, 0), lst.Seg(int(1.1 * S), "move", 0, 0, 5, 0,
                                                 t_start=int(1.1 * S), speed=400.0)]  # fmt: skip
    assert lst.late_kind(later, 1 * S, int(1.16 * S), 2 * S, 1.5) == ("unseen", int(1.1 * S))
    assert lst.late_kind(later, 1 * S, int(1.05 * S), 2 * S, 1.5) == ("latency", int(1.1 * S))


def test_an_on_time_strike_on_a_standing_target() -> None:
    t_det = 100 * S
    events = [{"t_ns": 50 * S, "kind": "run_start"},
              {"t_ns": t_det + 320 * MS, "kind": "box_target", "struck": True, "box": [1, 2, 3, 4],
               "verdict_from_grab_ms": 300, "hover_from_grab_ms": 50},
              {"t_ns": t_det + 380 * MS, "kind": "strike", "by": "box", "rel": [2, 0],
               "end": "damage", "clicks": 1}]  # fmt: skip
    dets = [{"t_ns": t_det + 21 * MS, "ms": 21.0, "boxes": [[1, 2, 3, 4, 0.9, "monster"]]}]
    pk = [self_move(90 * S, 0, 0, 5, 5), appear_stand(95 * S, MOB, 7, 5),
          walk_req(t_det + 730 * MS, 6, 5), attack_req(t_det + 1300 * MS, MOB)]  # fmt: skip
    (row,) = lst.strike_rows(events, pk, dets)
    assert row["grab_src"] == "detection"
    assert (row["target"], row["moved"], row["late"], row["outcome"]) == (MOB, 0.0, False, "target")
    assert row["attack_s"] == 0.92
    # grab_to_req runs from the runner's own grab stamp (the box_target time - its verdict ms)
    assert row["stages_ms"] == {"detect": 50, "hover": 250, "pre_click": 60, "client": 350,
                                "grab_to_req": 710}  # fmt: skip
    assert lst.add_lost([row]) == {"2-3": 0.92} and row["lost_s"] == 0.0


def p49_late_strike() -> tuple[list[dict[str, object]], list[dict[str, object]],
                               list[dict[str, object]]]:  # fmt: skip
    """The REAL positive case: p49 (20261110T185234-...-xmas02-p49), the box strike at 124.78 s.
    Records copied from its events.jsonl, packets.jsonl.gz and detections.jsonl (numbers verbatim;
    only the fields the scorer reads, plus a decoy Cruiser added 4 cells away)."""
    events = [
        {"t_ns": 276443663552380, "kind": "run_start"},
        {"t_ns": 276568381538421, "kind": "box_target", "fresh": True, "settle_ms": 1593,
         "still": False, "still_wait_ms": 1593, "box": [709.7, 201.8, 774.8, 270.2],
         "hover_from_grab_ms": 49, "verdict_from_grab_ms": 323, "verdicts": ["sword"],
         "struck": True, "rel": [3, 4]},
        {"t_ns": 276568438624544, "t_end_ns": 276569064708624, "kind": "strike", "u": 742.2,
         "v": 236.0, "rel": [3, 4], "clicks": 1, "arrow_s": 0.12, "end": "arrow", "by": "box"},
    ]  # fmt: skip
    gid = 110055224
    packets = [
        {"type": "entity_appear", "t_mono_ns": 276561184428945, "gid": gid, "objtype": 5,
         "kind": "move", "x": 90, "y": 113, "x1": 89, "y1": 113, "move_start_tick": 276561184,
         "speed": 400, "name": "Myst Case", "job": 1249},
        {"type": "self_move_request", "t_mono_ns": 276566221396318, "x": 83, "y": 106},
        {"type": "self_move", "t_mono_ns": 276566221546319, "server_tick": 276566221, "x0": 76,
         "y0": 106, "x1": 83, "y1": 106},
        {"type": "entity_appear", "t_mono_ns": 276566241763922, "gid": gid, "objtype": 5,
         "kind": "move", "x": 89, "y": 113, "x1": 86, "y1": 106, "move_start_tick": 276566241,
         "speed": 400, "name": "Myst Case", "job": 1249},
        appear_stand(276566300000000, DECOY, 87, 102),  # (not in p49: a decoy 4 cells off)
        {"type": "self_move_request", "t_mono_ns": 276568790311012, "x": 86, "y": 111},
        {"type": "self_move", "t_mono_ns": 276568790622635, "server_tick": 276568790, "x0": 83,
         "y0": 106, "x1": 86, "y1": 111},
        {"type": "self_move_request", "t_mono_ns": 276574159435795, "x": 86, "y": 107},
        {"type": "self_move", "t_mono_ns": 276574159591239, "server_tick": 276574159, "x0": 86,
         "y0": 111, "x1": 86, "y1": 107},
        {"type": "entity_appear", "t_mono_ns": 276574523799289, "gid": gid, "objtype": 5,
         "kind": "move", "x": 86, "y": 106, "x1": 91, "y1": 109, "move_start_tick": 276574523,
         "speed": 400, "name": "Myst Case", "job": 1249},
        {"type": "attack_request", "t_mono_ns": 276574659972883, "target_gid": gid},
    ]  # fmt: skip
    dets = [
        {"t_ns": 276567125895807, "ms": 19.5, "boxes": [[656.6, 290.9, 690.2, 362.2, 0.969,
                                                         "player"],
                                                        [876.1, 124.2, 938.1, 197.0, 0.963,
                                                         "monster"]]},
        {"t_ns": 276568098937848, "ms": 21.3, "boxes": [[625.9, 288.5, 659.3, 363.0, 0.976,
                                                         "player"],
                                                        [709.7, 201.8, 774.8, 270.2, 0.98,
                                                         "monster"]]},
    ]  # fmt: skip
    return events, packets, dets


def test_real_late_strike_p49_124s() -> None:
    """p49 at 124.78 s: a Myst Case WALKING north (89,113) -> (86,106) since 1.84 s before the
    grab; the box showed it at (86.01, 110.01); when the client resolved the click (+0.35 s) it was
    at (86, 107.83), 2.18 cells on. The client walked to the OLD spot (86,111), 3.17 cells from it;
    no attack until a new walk + attack request 6.22 s after the click. The scorer as run on p49:
    late (walking), outcome walk, lost 5.25 s against p49's 4-6 band baseline (0.97 s)."""
    events, packets, dets = p49_late_strike()
    (row,) = lst.strike_rows(events, packets, dets)
    assert row["t_s"] == 124.78 and row["grab_src"] == "detection"
    assert (row["target"], row["species"], row["band"]) == (110055224, "Myst Case", "4-6")
    assert row["me"] == [83.0, 106.0] and row["me_walking"] is False
    assert row["seen"] == [86.01, 110.01] and row["at_req"] == [86.0, 107.83]
    assert (row["moved"], row["late"], row["late_kind"]) == (2.18, True, "walking")
    assert row["walking_shown"] is True and row["move_start_s"] == -1.836
    assert (row["outcome"], row["first_req_to"], row["req_to_target"]) == ("walk", [86, 111], 3.17)
    assert row["stages_ms"] == {"detect": 49, "hover": 274, "pre_click": 57, "client": 352,
                                "grab_to_req": 732}  # fmt: skip
    assert (row["next_attack_s"], row["regain_s"]) == (6.22, 6.22)
    assert row["prev"]["match"] is False and row["walker_flag"] is None  # no box 1 s before
    lst.add_lost([row], baseline={"4-6": 0.97})
    assert row["lost_s"] == 5.25
    summ = lst.summary([row])
    assert (summ["late"], summ["late_failed"], summ["late_kinds"]) == (1, 1, {"walking": 1})
    assert summ["hit_by_moved"]["2.0-3.0"] == [1, 0]


def test_the_lag_shifts_the_seen_cell() -> None:
    """The same p49 strike with no stream lag: the box would put the walker 0.4 cell further on
    ((86, 109.61) at the grab), and it is still late: it moved 1.78 cells by the resolve."""
    events, packets, dets = p49_late_strike()
    (row,) = lst.strike_rows(events, packets, dets, lag_s=0.0)
    assert row["seen"] == row["at_grab"] == [86.0, 109.61]
    assert (row["moved"], row["late_kind"]) == (1.78, "walking")


def test_walker_flag_needs_a_settled_camera() -> None:
    assert lst.walker_flag(None) is None
    assert lst.walker_flag({"match": False}) is None
    moving = {"match": True, "scene_still": True, "settled_s": 0.9, "px": 14.0}
    assert lst.walker_flag(moving) is True
    assert lst.walker_flag({**moving, "px": 4.0}) is False
    assert lst.walker_flag({**moving, "settled_s": 0.2}) is None  # the camera still glides
    assert lst.walker_flag({**moving, "scene_still": False}) is None


def test_prev_box_matches_the_same_sprite() -> None:
    boxes = [[100, 100, 140, 160, 0.9, "monster"], [300, 100, 340, 160, 0.9, "monster"]]
    dets = [{"t_ns": int(9.7 * S), "ms": 20.0, "boxes": boxes}]
    pv = lst.prev_box(dets, [112, 100, 152, 160], 10 * S)
    assert pv is not None and pv["match"] is True
    assert (pv["foot_dx"], pv["foot_dy"], pv["px"]) == (12.0, 0.0, 12.0)
    assert pv["dt_s"] == 0.32 and pv["px_s"] == 37.5
    assert lst.prev_box(dets, [500, 500, 540, 560], 10 * S)["match"] is False
    assert lst.prev_box(dets, [112, 100, 152, 160], 20 * S) is None  # too old


def test_lag_profile_finds_the_drawn_lag() -> None:
    """A walker drawn 0.15 s behind the server (a linear projector, 30 px a cell): the profile's
    error is smallest at 0.15 s."""
    t_walk = 10 * S
    pk = [self_move(1 * S, 0, 0, 0, 0), appear_stand(5 * S, MOB, 2, 0),
          appear_move(t_walk, MOB, 2, 0, 9, 0, speed=200)]  # fmt: skip
    mobs, ours = lst.tracks(pk)

    def project(off: tuple[float, float], _me: tuple[int, int]) -> tuple[float, float]:
        return 640 + 30 * off[0], 360 - 20 * off[1]

    dets = []
    for k in range(4):
        tg = t_walk + int((0.8 + 0.1 * k) * S)
        x, y, _w = lst.pos_at(mobs[MOB], tg - int(0.15 * S))
        u, v = project((x, y), (0, 0))
        dets.append({"t_ns": tg + 20 * MS, "ms": 20.0,
                     "boxes": [[u - 20, v - 60, u + 20, v, 0.9, "monster"]]})  # fmt: skip
    lags = [0.0, 0.05, 0.1, 0.15, 0.2, 0.25]
    prof = lst.lag_profile(dets, mobs, ours, project, lags)
    med = {lag: sorted(v)[len(v) // 2] for lag, v in prof.items()}
    assert len(prof[0.15]) == 4 and min(med, key=lambda lag: med[lag]) == 0.15
    assert med[0.15] < 1e-6 < med[0.0]


def test_a_held_strike_is_timed_from_the_holds_last_matched_grab() -> None:
    """4BO: --still-target's held strike (press.end "still") clicked press.box_end, so its grab is
    that box's detection before the click; without it, D1's grab + end_gap_ms. Others unchanged."""
    ns = 1_000_000_000
    b1, b_end = [100.0, 100.0, 130.0, 150.0], [118.0, 104.0, 148.0, 154.0]
    dets = [{"t_ns": 10 * ns, "ms": 40.0, "boxes": [b1]},
            {"t_ns": 11 * ns, "ms": 40.0, "boxes": [b_end]}]  # fmt: skip
    bt = {"t_ns": 10 * ns + 300_000_000, "verdict_from_grab_ms": 340.0, "box": b1}
    t, src, end = lst.strike_grab(bt, dets, 11 * ns + 500_000_000)
    assert (t, src, end) == (10 * ns - 40_000_000, "detection", None)
    held = {**bt, "press": {"end": "still", "box_end": b_end, "end_gap_ms": 1000.0}}
    t, src, end = lst.strike_grab(held, dets, 11 * ns + 500_000_000)
    assert (t, src, end) == (11 * ns - 40_000_000, "hold_detection", "still")
    t, src, _ = lst.strike_grab(held, dets[:1], 11 * ns + 500_000_000)
    assert (t, src) == (10 * ns - 40_000_000 + 1000 * 1_000_000, "hold_gap")
    today = {**bt, "press": {"end": "strike", "moved_px": 3.0}}
    assert lst.strike_grab(today, dets, 11 * ns)[1] == "detection"


def led_strike(press_end: str = "led") -> tuple[list[dict[str, object]], list[dict[str, object]],
                                                list[dict[str, object]]]:  # fmt: skip
    """A synthetic --lead-press strike (dungeon@9.24, LS-1): D1 grabbed at 100.0 s, D2 at 100.3 s
    with the sprite's foot 20 px east (press.box2, gap_ms 300), the click led 1 cell ahead (rel
    (4, 0) from (5, 5)). The Myst Case walks east from (6, 5) since 99.5 s (400 ms a cell): at D2's
    picture (100.3 - 0.16 s) it was at (7.6, 5); the client resolved the click at 100.75 s with an
    attack request on it, at (9.12, 5): the led cell (9, 5)."""
    t_det = 100 * S
    d1, d2 = [600.0, 300.0, 640.0, 360.0], [620.0, 300.0, 660.0, 360.0]
    events = [{"t_ns": 50 * S, "kind": "run_start"},
              {"t_ns": t_det + 345 * MS, "kind": "box_target", "struck": True, "box": d1,
               "verdict_from_grab_ms": 280, "hover_from_grab_ms": 50, "rel": [4, 0],
               "press": {"end": press_end, "moved_px": 20.0, "box2": d2, "gap_ms": 300,
                         "lead": {"lead_px": [34.0, 0.0], "capped": True,
                                  "sword": "unchecked"}}},
              {"t_ns": t_det + 400 * MS, "kind": "strike", "by": "box", "rel": [4, 0],
               "end": "arrow", "clicks": 1}]  # fmt: skip
    dets = [{"t_ns": t_det + 21 * MS, "ms": 21.0, "boxes": [[*d1, 0.9, "monster"]]},
            {"t_ns": t_det + 321 * MS, "ms": 21.0, "boxes": [[*d2, 0.9, "monster"]]}]  # fmt: skip
    pk = [self_move(90 * S, 0, 0, 5, 5), appear_move(int(99.5 * S), MOB, 6, 5, 12, 5),
          attack_req(t_det + 750 * MS, MOB)]  # fmt: skip
    return events, pk, dets


def test_a_led_strike_is_scored_from_its_d2_grab() -> None:
    """4BP / LS-1: a led strike (press.end "led") clicked ahead of D2's box, so its picture is D2's
    (press.box2's detection; without it, D1's grab + press.gap_ms); its previous detection is D1,
    compared with D2's box (the runner's own 20-px shift). The summary counts the led strikes and
    their outcomes. Today's strike and a held one are scored as before."""
    events, pk, dets = led_strike()
    (row,) = lst.strike_rows(events, pk, dets)
    assert (row["grab_src"], row["press_end"]) == ("lead_detection", "led")
    assert row["seen"] == [7.6, 5.0] and row["at_req"] == [9.12, 5.0]  # from D2's picture
    assert (row["target"], row["outcome"], row["attack_s"]) == (MOB, "target", 0.35)
    assert (row["moved"], row["late"], row["late_kind"]) == (1.53, True, "walking")
    assert row["prev"]["match"] and row["prev"]["t_prev"] == 100 * S  # D1's grab
    assert (row["prev"]["px"], row["prev"]["dt_s"], row["walker_flag"]) == (20.0, 0.3, True)
    summ = lst.summary([row])
    assert (summ["led"], summ["led_outcomes"], summ["late_failed"]) == (1, {"target": 1}, 0)
    # D2's detection not logged: D1's grab + gap_ms
    bt, t_click = events[1], 100 * S + 400 * MS
    t, src, end = lst.strike_grab(bt, dets[:1], t_click)
    assert (t, src, end) == (100 * S + 300 * MS, "lead_gap", "led")
    t, src, _ = lst.strike_grab(bt, dets, t_click)
    assert (t, src) == (100 * S + 300 * MS, "lead_detection")
    # the same click scored as today's strike (D2 matched, < 10 px): D1's picture, D1's box
    events_t, pk_t, dets_t = led_strike("strike")
    (row_t,) = lst.strike_rows(events_t, pk_t, dets_t)
    assert (row_t["grab_src"], row_t["press_end"]) == ("detection", "strike")
    assert row_t["seen"] == [6.85, 5.0] and row_t["prev"] is None  # no detection before D1
    assert lst.summary([row_t])["led"] == 0 and lst.summary([row_t])["led_outcomes"] == {}
