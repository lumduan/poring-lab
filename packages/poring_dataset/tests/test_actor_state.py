"""Phase 3 M3: Timeline.state -- idle / walk / attack / hurt / dying (+ sit) and the facing, from
recorded packet events (synthetic)."""

from typing import Any

import numpy as np
import pytest

from poring_dataset import labels as lb
from poring_dataset.timeline import DEFAULT_DIE_MS, Timeline, tick_of

MS = 1_000_000
T0 = 700_000_000 * MS  # host CLOCK_MONOTONIC (ns); the server tick is t // 1e6 mod 2^32
TICK0 = tick_of(T0)
AID = 2000001


def ev(t_ms: int, type_: str, **fields: object) -> dict[str, object]:
    return {"t_mono_ns": T0 + t_ms * MS, "type": type_, **fields}


def appear(t_ms: int, gid: int, x: int, y: int, *, heading: int | None = None,
           to: tuple[int, int] | None = None, job: int = 1002) -> dict[str, object]:  # fmt: skip
    f: dict[str, Any] = {"kind": "new" if to is None else "move", "gid": gid, "char_id": 0,
                         "objtype": 5, "job": job, "speed": 200, "name": "Poring", "x": x,
                         "y": y, "heading": heading}  # fmt: skip
    if to is not None:
        f |= {"x1": to[0], "y1": to[1], "move_start_tick": TICK0 + t_ms}
    return ev(t_ms, "entity_appear", **f)


def act(t_ms: int, src: int, dst: int, kind: str = "normal", *, damage: int = 5,
        src_speed: int = 672, dmotion: int = 480,
        timed: bool = True) -> dict[str, object]:  # fmt: skip
    action = {"normal": 0, "sit": 2, "stand": 3, "endure": 4}[kind]
    return ev(t_ms, "act", src_gid=src, target_gid=dst,
              server_tick=TICK0 + t_ms if timed else 0, src_speed=src_speed, dmotion=dmotion,
              damage=damage, damage2=0, div=1, action=action, kind=kind)  # fmt: skip


def events() -> list[dict[str, object]]:
    return [
        ev(0, "login_accepted", aid=AID, sex=0),
        ev(1, "map_change", map="lab", x=50, y=50),
        ev(2, "map_enter", server_tick=TICK0 + 2, x=50, y=50, facing=6),
        appear(10, 7, 53, 50, heading=4),  # a Poring 3 cells east of us, facing south
        appear(10, 8, 60, 60, heading=0),
        act(1000, 7, AID),  # it attacks us: 672 ms swing, we flinch for 480 ms
        ev(2000, "entity_vanish", gid=7, reason=1),  # and dies
        ev(3000, "entity_turn", gid=8, heading=3, head_dir=0),
        appear(4000, 9, 40, 40, to=(40, 44)),  # walks north: 4 steps x 200 ms
        appear(4000, 10, 30, 30, to=(34, 30)),  # walks east ...
        act(4150, AID, 9, dmotion=300),  # we hit the walker
        ev(4250, "entity_stop", gid=10, x=31, y=30),  # ... and is stopped in its 2nd step
        act(6000, AID, 0, "sit", damage=0, timed=False),
        act(6500, AID, 0, "stand", damage=0, timed=False),
        ev(7000, "entity_vanish", gid=8, reason=0),  # out of sight: no die animation
    ]


@pytest.fixture
def tl() -> Timeline:
    return Timeline(events(), snapshot_every=2, die_ms={1002: 800})


def at(ms: float) -> int:
    return T0 + int(ms * MS)


def test_an_attack_before_during_and_after(tl: Timeline) -> None:
    before = tl.state(7, at(999))
    assert before is not None and (before.state, before.facing, before.facing_from) == (
        "idle", 4, "appear")  # fmt: skip
    assert before.since_ns is None and before.job == 1002
    swing = tl.state(7, at(1300))
    assert swing is not None and swing.state == "attacking" and swing.other == AID
    assert (swing.since_ns, swing.duration_ms, swing.elapsed_ms) == (at(1000), 672, 300.0)
    assert (swing.facing, swing.facing_from) == (2, "target")  # turned west, toward us
    after = tl.state(7, at(1672))
    assert after is not None and after.state == "idle" and after.since_ns == at(1672)
    assert after.facing == 2  # keeps facing its target
    assert (after.x, after.y) == (53.0, 50.0)


def test_the_target_flinches_for_its_damage_motion(tl: Timeline) -> None:
    hit = tl.state(AID, at(1000))
    assert hit is not None and (hit.state, hit.other, hit.duration_ms) == ("hurt", 7, 480)
    assert hit.job is None and (hit.facing, hit.facing_from) == (6, "appear")  # map_enter's
    assert tl.state(AID, at(999)).state == "idle"  # type: ignore[union-attr]
    done = tl.state(AID, at(1480))
    assert done is not None and done.state == "idle" and done.since_ns == at(1480)


def test_a_death_plays_for_its_class_duration_then_the_unit_is_gone(tl: Timeline) -> None:
    alive = tl.state(7, at(1999))
    assert alive is not None and alive.state == "idle"
    dying = tl.state(7, at(2000))
    assert dying is not None and (dying.state, dying.since_ns, dying.duration_ms) == (
        "dying", at(2000), 800)  # fmt: skip
    assert (dying.x, dying.y, dying.facing) == (53.0, 50.0, 2)  # where and how it fell
    late = tl.state(7, at(2799))
    assert late is not None and late.state == "dying" and late.elapsed_ms == 799.0
    assert tl.state(7, at(2800)) is None
    # without a table entry: the placeholder default
    default = Timeline(events())
    assert default.state(7, at(2000 + DEFAULT_DIE_MS - 1)).state == "dying"  # type: ignore[union-attr]
    assert default.state(7, at(2000 + DEFAULT_DIE_MS)) is None
    # frame_world (labels v0) is unchanged: a dead unit is not an entity any more
    assert 7 not in {e.gid for e in tl.frame_world(at(2100)).entities}
    assert [(s.gid, s.state) for s in tl.states(at(2100))] == [
        (AID, "idle"), (8, "idle"), (7, "dying")]  # fmt: skip


def test_out_of_sight_is_gone_at_once(tl: Timeline) -> None:
    assert tl.state(8, at(6999)) is not None
    assert tl.state(8, at(7000)) is None
    assert tl.state(12345, at(7000)) is None


def test_a_direction_change_turns_the_unit_at_its_time(tl: Timeline) -> None:
    pre = tl.state(8, at(2999))
    post = tl.state(8, at(3000))
    assert pre is not None and (pre.facing, pre.facing_from) == (0, "appear")
    assert post is not None and (post.facing, post.facing_from, post.state) == (3, "turn", "idle")
    heading = {e.gid: e.heading for e in tl.frame_world(at(3000)).entities}
    assert heading[8] == 3  # the packet heading frame_world uses follows the turn too


def test_walking_faces_its_step_and_a_flinch_interrupts_it(tl: Timeline) -> None:
    walk = tl.state(9, at(4100))
    assert walk is not None and (walk.state, walk.facing, walk.facing_from) == ("walk", 0, "walk")
    assert (walk.x, walk.y, walk.since_ns) == (40.0, 40.5, at(4000))
    hurt = tl.state(9, at(4200))
    assert hurt is not None and (hurt.state, hurt.other, hurt.duration_ms) == ("hurt", AID, 300)
    assert tl.state(9, at(4460)).state == "walk"  # type: ignore[union-attr]
    arrived = tl.state(9, at(5000))
    assert arrived is not None and (arrived.state, arrived.facing, arrived.since_ns) == (
        "idle", 0, at(4800))  # fmt: skip
    # we swung at it: our own attack, turned toward where it was (40, 40.75 -> 40, 41)
    us = tl.state(AID, at(4150))
    assert us is not None and (us.state, us.other, us.facing, us.facing_from) == (
        "attacking", 9, 3, "target")  # fmt: skip


def test_a_stop_keeps_the_facing_of_the_step_it_cut(tl: Timeline) -> None:
    stopped = tl.state(10, at(4300))
    assert stopped is not None and (stopped.state, stopped.x, stopped.y) == ("idle", 31.0, 30.0)
    assert (stopped.facing, stopped.facing_from, stopped.since_ns) == (6, "stop", at(4250))


def test_sitting_and_standing(tl: Timeline) -> None:
    assert tl.state(AID, at(6000)).state == "sit"  # type: ignore[union-attr]
    assert tl.state(AID, at(6499)).state == "sit"  # type: ignore[union-attr]
    assert tl.state(AID, at(6500)).state == "idle"  # type: ignore[union-attr]


def test_labels_still_come_from_frame_world_unchanged(tl: Timeline) -> None:
    h = np.array([[30.0, 0, 392.0], [0, -30.0, 330.0], [0, 0, 1.0]])
    frame = tl.frame_world(at(1300))  # mid-attack
    out = lb.labels_for(frame, h, (784, 625), exclude_gids=[AID])
    assert [(b.gid, b.cls) for b in out] == [(7, "monster")]  # 8, 10 cells north, is off screen


def test_packet_map_names_find_the_map_cache_grid() -> None:
    """Packets name maps "prt_fild08.gat"; the map cache keys "prt_fild08". The lookup must strip
    the suffix, or every walk falls back to the straight path (T0 evaluation, 2026-10-04)."""
    from poring_dataset.mapcache import MapGrid

    grid = MapGrid("prt_fild08", 4, 4, bytes(16))
    tl = Timeline([], {"prt_fild08": grid})
    assert tl.grid("prt_fild08.gat") is grid
    assert tl.grid("prt_fild08") is grid
    assert tl.grid(None) is None and tl.grid("") is None and tl.grid("nowhere.gat") is None


def test_our_own_id_is_inferred_when_the_session_starts_after_the_login() -> None:
    """A recording starts at its last map change, so login_accepted is not in it. Our own
    entity_stop must still cut our walk, or every box is projected from the planned end (T0)."""
    from poring_dataset.timeline import infer_self_aid

    evs = [
        ev(1, "map_change", map="lab", x=50, y=50),
        ev(2, "map_enter", server_tick=TICK0 + 2, x=50, y=50, facing=6),
        appear(10, 110000001, 53, 50, heading=4),  # a monster: it appears, so it is not us
        ev(100, "self_move", server_tick=TICK0 + 100, x0=50, y0=50, x1=56, y1=50),
        ev(400, "entity_stop", gid=2000002, x=52, y=50),  # our walk, cut short at (52, 50)
    ]
    assert infer_self_aid(evs) == 2000002
    tl = Timeline(evs)
    assert tl.inferred_aid == 2000002
    late = tl.frame_world(T0 + 5_000 * MS).self_pos
    assert late is not None and (round(late[0]), round(late[1])) == (52, 50)  # not (56, 50)
    with_login = Timeline([ev(0, "login_accepted", aid=AID, sex=0), *evs])
    assert with_login.inferred_aid is None  # the login names the id; nothing is inferred
