"""Phase 3 M3: the ZC_NOTIFY_ACT family and ZC_CHANGE_DIRECTION, decoded and applied to the world
(synthetic packets built from the pinned rAthena struct layouts)."""

import struct
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
from helpers import (  # noqa: E402
    cz_enter2,
    seg,
    table,
    zc_change_direction,
    zc_notify_act,
)

from poring_packets import tables
from poring_packets.clock import Sample
from poring_packets.decode import ACT_KINDS, decode
from poring_packets.events import Act, EntityTurn, parse_event
from poring_packets.sniffer import Session
from poring_packets.world import (
    DEAD_KEEP_MAX,
    Walk,
    World,
    direction_toward,
    ticks_since,
)

MS = 1_000_000
ACT_LENGTHS = {0x008A: 29, 0x02E1: 33, 0x08C8: 34}


# --- decoders ------------------------------------------------------------------------------------
@pytest.mark.parametrize("pid", sorted(ACT_LENGTHS))
def test_the_three_act_layouts_decode_to_one_event(pid: int) -> None:
    raw = zc_notify_act(110001, 2000001, 4_000_000_123, 672, 480, 37, 10, div=1, damage2=5,
                        sp=1, pid=pid)  # fmt: skip
    assert len(raw) == ACT_LENGTHS[pid]
    d = decode("map", "sc", pid, raw)
    assert d is not None and d.type == "act"
    assert d.fields == {
        "src_gid": 110001, "target_gid": 2000001, "server_tick": 4_000_000_123,
        "src_speed": 672, "dmotion": 480, "damage": 37, "damage2": 5, "div": 1, "action": 10,
        "kind": "critical", "sp_damage": True if pid == 0x08C8 else None,
    }  # fmt: skip


def test_act_damage_is_signed_and_kinds_follow_the_enum() -> None:
    hidden = decode("map", "sc", 0x08C8, zc_notify_act(1, 2, 3, 400, 300, -1, 0))
    assert hidden is not None and hidden.fields["damage"] == -1  # a disguised source
    old = decode("map", "sc", 0x008A, zc_notify_act(1, 2, 3, 400, 300, -1, 8, div=3, pid=0x008A))
    assert old is not None and (old.fields["damage"], old.fields["div"]) == (-1, 3)
    assert old.fields["kind"] == "multi_hit"
    sit = decode("map", "sc", 0x08C8, zc_notify_act(7, 0, 0, 0, 0, 0, 2))
    assert sit is not None and sit.fields["kind"] == "sit" and sit.fields["server_tick"] == 0
    odd = decode("map", "sc", 0x08C8, zc_notify_act(7, 8, 9, 1, 1, 0, 99))
    assert odd is not None and odd.fields["kind"] == "type99"
    assert [ACT_KINDS[i] for i in (0, 1, 2, 3, 4, 9, 11, 14)] == [
        "normal", "pickup", "sit", "stand", "endure", "multi_hit_endure", "lucky_dodge",
        "splash_endure",
    ]  # fmt: skip


def test_change_direction_decodes_body_and_head() -> None:
    d = decode("map", "sc", 0x009C, zc_change_direction(110001, 5, head_dir=2))
    assert d is not None and d.type == "entity_turn"
    assert d.fields == {"gid": 110001, "head_dir": 2, "heading": 5}
    bad = decode("map", "sc", 0x009C, zc_change_direction(110001, 9))
    assert bad is not None and bad.fields["heading"] is None  # out of range: not trusted


def test_the_new_events_validate_and_round_trip() -> None:
    d = decode("map", "sc", 0x08C8, zc_notify_act(1, 2, 3, 672, 480, 9, 0))
    assert d is not None
    base = {"t_mono_ns": 5, "server": "map", "dir": "sc", "packet_id": 0x08C8}
    ev = parse_event(Act(**base, **d.fields).model_dump_json())
    assert isinstance(ev, Act) and ev.kind == "normal" and ev.src_speed == 672
    t = decode("map", "sc", 0x009C, zc_change_direction(4, 3))
    assert t is not None
    turn = parse_event(EntityTurn(**{**base, "packet_id": 0x009C}, **t.fields).model_dump_json())
    assert isinstance(turn, EntityTurn) and turn.heading == 3


def test_generated_table_frames_the_new_ids() -> None:
    if not tables.DEFAULT_TABLE.exists():
        pytest.skip("generated at build time: python3 scripts/gen_packet_tables.py")
    t = tables.load()
    for pid, length in {**ACT_LENGTHS, 0x009C: 9}.items():
        assert t.length("map", "sc", pid) == length


# --- the game's direction rule ------------------------------------------------------------------
def test_direction_toward_uses_the_one_to_three_slope() -> None:
    assert direction_toward(0, 0) is None
    assert [direction_toward(*d) for d in ((0, 5), (-5, 0), (0, -5), (5, 0))] == [0, 2, 4, 6]
    assert [direction_toward(*d) for d in ((2, 2), (-2, 2), (-2, -2), (2, -2))] == [7, 1, 3, 5]
    # within 1:3 of an axis it is the axis; the boundary belongs to the axis on the east side
    assert direction_toward(3, 1) == 6 and direction_toward(3, -1) == 6
    assert direction_toward(-3, 1) == 1 and direction_toward(-3, -1) == 3
    assert direction_toward(-4, 1) == 2
    assert direction_toward(1, 3) == 7 and direction_toward(1, 4) == 0
    assert direction_toward(-1, 3) == 0 and direction_toward(-1, -3) == 4


def test_ticks_since_is_signed_across_the_wrap() -> None:
    assert ticks_since(5, (1 << 32) - 5) == 10
    assert ticks_since((1 << 32) - 5, 5) == -10


# --- world ---------------------------------------------------------------------------------------
def appear(gid: int, x: int, y: int, t: int, *, heading: int | None = None, job: int = 1002,
           to: tuple[int, int] | None = None, tick: int = 0) -> dict[str, object]:  # fmt: skip
    f: dict[str, object] = {"gid": gid, "objtype": 5, "job": job, "speed": 200, "name": "Poring",
                            "x": x, "y": y, "heading": heading, "t_mono_ns": t}  # fmt: skip
    if to is not None:
        f |= {"x1": to[0], "y1": to[1], "move_start_tick": tick}
    return f


def act(src: int, dst: int, tick: int, kind: str = "normal", *, damage: int = 10,
        src_speed: int = 672, dmotion: int = 480,
        t: int | None = None) -> dict[str, object]:  # fmt: skip
    action = {v: k for k, v in ACT_KINDS.items()}[kind]
    f: dict[str, object] = {"src_gid": src, "target_gid": dst, "server_tick": tick,
                            "src_speed": src_speed, "dmotion": dmotion, "damage": damage,
                            "damage2": 0, "div": 1, "action": action, "kind": kind}  # fmt: skip
    if t is not None:
        f["t_mono_ns"] = t
    return f


def world_with(*units: tuple[int, int, int]) -> World:
    w = World(aid=2000001, map="prt_fild08", self_x=50, self_y=50)
    for gid, x, y in units:
        w.apply("entity_appear", appear(gid, x, y, 1000 * MS, heading=4))
    return w


def test_an_attack_swings_the_source_and_flinches_the_target() -> None:
    w = world_with((7, 52, 50))
    w.apply("act", act(7, 2000001, 5000))  # the Poring hits us
    swing, flinch = w.entities[7].motion.action, w.self_motion.action
    assert swing is not None and (swing.kind, swing.start_tick, swing.duration_ms) == (
        "attacking", 5000, 672)  # fmt: skip
    assert swing.other == 2000001 and swing.active(5000) and not swing.active(5672)
    assert flinch is not None
    assert (flinch.kind, flinch.duration_ms, flinch.other) == ("hurt", 480, 7)
    turn = w.entities[7].motion.turn
    assert turn is not None and (turn.heading, turn.tick, turn.source) == (2, 5000, "target")
    assert w.entities[7].dir == 4  # the packet-reported heading (frame_world) is left alone


@pytest.mark.parametrize(
    ("kind", "damage", "flinches"),
    [("normal", 0, False), ("endure", 25, False), ("multi_hit_endure", 25, False),
     ("lucky_dodge", 0, False), ("critical", 40, True), ("multi_hit", 30, True)],
)  # fmt: skip
def test_misses_dodges_and_endure_swing_without_a_flinch(
    kind: str, damage: int, flinches: bool
) -> None:
    w = world_with((7, 52, 50), (8, 53, 50))
    w.apply("act", act(7, 8, 5000, kind, damage=damage))
    swing = w.entities[7].motion.action
    assert swing is not None and swing.kind == "attacking" and swing.act == kind
    assert (w.entities[8].motion.action is not None) is flinches


def test_skill_types_self_hits_and_zero_speeds_start_nothing() -> None:
    w = world_with((7, 52, 50), (8, 53, 50))
    w.apply("act", act(7, 8, 5000, "splash"))
    assert w.entities[7].motion.action is None  # a skill splash: no swing here
    assert w.entities[8].motion.action is not None  # but the hit still flinches
    w2 = world_with((7, 52, 50))
    w2.apply("act", act(7, 7, 5000, "endure"))  # reflected damage shown on the unit itself
    w2.apply("act", act(7, 2000001, 5000, src_speed=0, dmotion=0))
    assert w2.entities[7].motion.action is None and w2.self_motion.action is None


def test_the_newer_action_is_the_one_shown() -> None:
    w = world_with((7, 52, 50))
    w.apply("act", act(7, 2000001, 5000))
    w.apply("act", act(2000001, 7, 5200, src_speed=500))  # we hit back mid-swing
    a = w.entities[7].motion.action
    assert a is not None and (a.kind, a.start_tick) == ("hurt", 5200)
    w.apply("act", act(7, 2000001, 5100))  # an older swing arriving late does not replace it
    a = w.entities[7].motion.action
    assert a is not None and a.kind == "hurt"


def test_sitting_comes_from_act_and_a_hit_stands_you_up() -> None:
    w = world_with((7, 52, 50))
    w.apply("act", act(2000001, 0, 0, "sit", damage=0, t=2000 * MS))
    assert w.self_motion.sitting
    w.apply("act", act(7, 2000001, 5000))
    assert not w.self_motion.sitting
    w.apply("act", act(2000001, 0, 0, "sit", damage=0))
    w.apply("act", act(2000001, 0, 0, "stand", damage=0))
    assert not w.self_motion.sitting


def test_turns_set_the_heading_and_their_time() -> None:
    w = world_with((7, 52, 50))
    w.apply("entity_turn", {"gid": 7, "heading": 1, "head_dir": 0, "t_mono_ns": 3000 * MS})
    turn = w.entities[7].motion.turn
    assert turn is not None and (turn.tick, turn.source) == (3000, "turn")
    assert w.entities[7].dir == 1
    w.apply("entity_turn", {"gid": 7, "heading": None, "head_dir": 0})
    w.apply("entity_turn", {"gid": 99, "heading": 3, "head_dir": 0})  # not in sight: ignored
    assert w.entities[7].dir == 1


def test_a_death_keeps_the_unit_while_it_dies_and_a_respawn_clears_it() -> None:
    w = world_with((7, 52, 50), (8, 53, 50))
    w.apply("entity_vanish", {"gid": 7, "reason": 1, "t_mono_ns": 6000 * MS})
    w.apply("entity_vanish", {"gid": 8, "reason": 0, "t_mono_ns": 6000 * MS})
    assert 7 not in w.entities and w.dead[7].died_tick == 6000 and 8 not in w.dead
    w.apply("entity_appear", appear(7, 60, 60, 9000 * MS))  # the respawn keeps its block id
    assert 7 in w.entities and 7 not in w.dead
    w.apply("entity_vanish", {"gid": 7, "reason": 1, "t_mono_ns": 10_000 * MS})
    w.apply("time_sync", {"server_tick": 1, "t_mono_ns": (10_000 + w.dead_keep_ms + 1) * MS})
    assert 7 not in w.dead  # pruned once its die animation is long over
    for gid in range(100, 100 + DEAD_KEEP_MAX + 5):
        w.apply("entity_appear", appear(gid, 1, 1, 30_000 * MS))
        w.apply("entity_vanish", {"gid": gid, "reason": 1, "t_mono_ns": 30_000 * MS})
    assert len(w.dead) == DEAD_KEEP_MAX  # bounded, oldest first
    w.apply("map_change", {"map": "prontera", "x": 1, "y": 1})
    assert not w.dead


def test_a_stop_keeps_the_cut_walk_and_a_new_walk_keeps_the_action() -> None:
    w = world_with()
    w.apply("entity_appear", appear(7, 50, 50, 1000 * MS, to=(55, 50), tick=1000))
    w.apply("act", act(2000001, 7, 1100))
    w.apply("entity_stop", {"gid": 7, "x": 51, "y": 50, "t_mono_ns": 1150 * MS})
    cut = w.entities[7].motion.cut
    assert cut is not None and cut[1] == 1150 and cut[0] == Walk(50, 50, 55, 50, 1000, 200)
    w.apply("entity_appear", appear(7, 51, 50, 1700 * MS, to=(51, 55), tick=1700))  # walks on
    m = w.entities[7].motion
    assert m.cut is None and m.action is not None and m.action.kind == "hurt"


# --- end to end: sniffer session and replay -------------------------------------------------------
EXTRA = {("map", "sc", pid): n for pid, n in {**ACT_LENGTHS, 0x009C: 9}.items()}


def test_the_session_and_the_replay_emit_act_and_turn_events(tmp_path: Path) -> None:
    from poring_packets.pcapng import PcapngWriter
    from poring_packets.replay import replay

    path = tmp_path / "capture.pcapng"
    w = PcapngWriter(path)
    w.clock_sample({"mono_ns": 5_000_000_000, "real_ns": 1_000_000_000_000, "read_ns": 10})
    hit = zc_notify_act(110001, 2000002, 5003, 672, 480, 12, 0)
    sc = hit + zc_change_direction(110001, 6) + zc_notify_act(1, 2, 3, 4, 5, 6, 0, pid=0x02E1)
    t = 1_000_000_000_000
    for direction, seq, payload, flags in (
        ("cs", 0, b"", 0x02),
        ("sc", 0, b"", 0x12),
        ("cs", 1, cz_enter2(2000002), 0x18),
        ("sc", 1, sc, 0x18),
    ):
        w.packet(seg(direction, 5121, seq, payload, flags=flags, cport=50002).frame, t)
        t += 1_000_000
    w.close()
    s = Session(table(EXTRA), "192.168.1.169", set())
    events = [e for e in replay([path], s) if e.type in ("act", "entity_turn")]
    assert [e.type for e in events] == ["act", "entity_turn", "act"]
    first = events[0]
    assert isinstance(first, Act) and (first.src_gid, first.target_gid, first.kind) == (
        110001, 2000002, "normal")  # fmt: skip
    assert first.packet_id == 0x08C8 and first.sp_damage is False
    assert isinstance(events[1], EntityTurn) and events[1].heading == 6
    assert isinstance(events[2], Act) and events[2].packet_id == 0x02E1
    assert events[2].sp_damage is None
    # the live session's world took the hit on our own character
    action = s.world.self_motion.action
    assert action is not None and (action.kind, action.duration_ms) == ("hurt", 480)


def test_the_live_session_feeds_the_world_without_receive_times() -> None:
    """The sniffer applies decoded fields only (no t_mono_ns): timed events still apply."""
    s = Session(table(EXTRA), "192.168.1.169", set())
    s.clock.add(Sample(mono_ns=0, real_ns=0, read_ns=1))
    s.feed(seg("cs", 5121, 1, cz_enter2(2000001), cport=50100))
    sit = zc_notify_act(2000001, 0, 0, 0, 0, 0, 2)
    hit = zc_notify_act(110001, 2000001, 9000, 672, 480, 3, 0)
    ev = s.feed(seg("sc", 5121, 1, sit + struct.pack("<HI", 0x007F, 8999) + hit, cport=50100))
    assert [e.type for e in ev] == ["act", "time_sync", "act"]
    assert not s.world.self_motion.sitting  # sat down, then a hit stood us up
    action = s.world.self_motion.action
    assert action is not None and (action.kind, action.start_tick) == ("hurt", 9000)
    assert s.world.tick == 9000  # the latest server tick seen
