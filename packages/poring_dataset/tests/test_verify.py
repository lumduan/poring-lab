"""poring_dataset.verify: outcome verifiers on synthetic event fixtures (demonstrations.md)."""

from __future__ import annotations

from typing import Any

from poring_dataset.verify import (
    path_seconds,
    resolve_click,
    verify_attack,
    verify_login,
    verify_menu,
    verify_walk,
)

T0 = 900_000_000_000_000
AID, MOB, MOB2, OTHER = 2000002, 110012875, 110012876, 2000001


def ev(ms: float, type: str, **f: Any) -> dict[str, Any]:
    return {"t_mono_ns": T0 + int(ms * 1e6), "type": type, **f}


# --- login -------------------------------------------------------------------------------------


def test_login_in_order_is_a_success() -> None:
    evs = [ev(4000, "login_accepted", aid=AID), ev(5200, "char_selected", map="prt_fild08.gat"),
           ev(6100, "map_enter", x=170, y=375)]  # fmt: skip
    v = verify_login(evs, T0, AID)
    assert v.status == "success" and v.evidence["map_enter"] == 6100


def test_login_of_another_account_or_out_of_order_fails() -> None:
    assert (
        verify_login(
            [
                ev(4000, "login_accepted", aid=OTHER),
                ev(5000, "char_selected"),
                ev(6000, "map_enter"),
            ],
            T0,
            AID,
        ).cause
        == "no login_accepted within 60 s"
    )
    late = [
        ev(4000, "login_accepted", aid=AID),
        ev(61_000, "char_selected"),
        ev(62_000, "map_enter"),
    ]
    assert verify_login(late, T0, AID).cause == "no char_selected within 60 s"
    before = [
        ev(-1000, "login_accepted", aid=AID),
        ev(1000, "char_selected"),
        ev(2000, "map_enter"),
    ]
    assert verify_login(before, T0, AID).status == "fail"  # before the click is not this login


# --- walk --------------------------------------------------------------------------------------


def walk(dest: tuple[int, int], at: float = 120) -> list[dict[str, Any]]:
    return [ev(at - 1, "self_move_request", x=dest[0], y=dest[1]),
            ev(at, "self_move", x0=170, y0=375, x1=dest[0], y1=dest[1])]  # fmt: skip


def test_a_walk_to_the_target_cell_is_a_success() -> None:
    v = verify_walk(walk((173, 372)), T0, AID, (173, 372))
    assert v.status == "success" and v.evidence["off_cells"] == 0
    assert v.evidence["arrive_ms"] > 120


def test_a_walk_one_cell_off_fails_with_its_distance() -> None:
    v = verify_walk(walk((174, 372)), T0, AID, (173, 372))
    assert v.status == "fail" and v.evidence["off_cells"] == 1


def test_no_move_request_in_time_means_the_click_was_not_a_walk() -> None:
    assert verify_walk(walk((173, 372), at=2500), T0, AID, (173, 372)).status == "fail"
    assert verify_walk([], T0, AID, (173, 372)).cause.startswith("no move request")


def test_stopped_short_rerouted_or_map_change() -> None:
    stop = walk((176, 372)) + [ev(400, "entity_stop", gid=AID, x=172, y=374)]
    assert verify_walk(stop, T0, AID, (176, 372)).cause == "stopped short"
    other_stop = walk((176, 372)) + [ev(400, "entity_stop", gid=MOB, x=172, y=374)]
    assert verify_walk(other_stop, T0, AID, (176, 372)).status == "success"  # not us
    reroute = walk((176, 372)) + [ev(300, "self_move", x0=171, y0=374, x1=160, y1=370)]
    assert verify_walk(reroute, T0, AID, (176, 372)).cause == "re-routed before arriving"
    warp = walk((176, 372)) + [ev(300, "map_change", map="prontera.gat", x=1, y=1)]
    assert verify_walk(warp, T0, AID, (176, 372)).status == "ambiguous"


def test_path_time_uses_diagonal_steps() -> None:
    assert path_seconds((0, 0), (3, 0), 150) == 0.45
    assert round(path_seconds((0, 0), (3, 3), 150), 3) == round(3 * 1.41421356 * 0.15, 3)


# --- attack ------------------------------------------------------------------------------------


def act(ms: float, src: int, tgt: int, damage: int = 7, kind: str = "normal") -> dict[str, Any]:
    return ev(ms, "act", src_gid=src, target_gid=tgt, damage=damage, kind=kind)


def test_damage_miss_and_critical_on_the_intended_target_all_count() -> None:
    for a in (act(600, AID, MOB), act(600, AID, MOB, damage=0), act(600, AID, MOB, 30, "critical"),
              act(600, AID, MOB, 0, "lucky_dodge")):  # fmt: skip
        assert verify_attack([a], T0, AID, MOB).status == "success"


def test_our_act_on_another_gid_is_the_wrong_target() -> None:
    v = verify_attack([act(600, AID, MOB2)], T0, AID, MOB)
    assert v.status == "fail" and v.cause == "attacked a different target"


def test_a_click_that_became_a_walk_fails() -> None:
    v = verify_attack([ev(100, "self_move_request", x=1, y=1)], T0, AID, MOB)
    assert v.cause == "the click became a walk (no act on the target)"
    # the server's approach walk for an attack click is NOT a walk click
    approach = [ev(100, "self_move", x0=1, y0=1, x1=2, y1=2), act(900, AID, MOB)]
    assert verify_attack(approach, T0, AID, MOB).status == "success"


def test_other_attackers_vanishing_targets_and_late_acts_are_ambiguous() -> None:
    assert verify_attack([act(500, OTHER, MOB)], T0, AID, MOB).status == "ambiguous"
    gone = [ev(300, "entity_vanish", gid=MOB, reason=1), act(900, AID, MOB)]
    assert verify_attack(gone, T0, AID, MOB).status == "ambiguous"
    late = [act(2500, AID, MOB)]  # walk-in 0 s: window 2 s
    assert verify_attack(late, T0, AID, MOB).cause == "our act came after the window"
    assert verify_attack(late, T0, AID, MOB, walk_s=1.0).status == "success"


def test_sit_and_stand_are_not_attacks_on_another_target() -> None:
    v = verify_attack([act(100, AID, AID, kind="stand"), act(600, AID, MOB)], T0, AID, MOB)
    assert v.status == "success"


def test_nothing_at_all_is_an_ignored_click() -> None:
    assert verify_attack([], T0, AID, MOB).cause == "no act and no walk (click ignored)"


# --- click resolution and menus ----------------------------------------------------------------


def test_a_click_resolves_to_the_box_containing_it_or_the_nearest_anchor() -> None:
    boxes = {MOB: (100, 100, 140, 140), MOB2: (120, 90, 200, 150)}
    assert resolve_click((130, 120), boxes) == (MOB, 0.0)  # inside both: the smaller box
    assert resolve_click((300, 140), boxes) == (MOB2, 140.4)  # foot point (160, 150)
    assert resolve_click((0, 0), {}) == (None, None)


def test_menu_verdicts() -> None:
    assert verify_menu(False, True).status == "success"
    assert verify_menu(False, False).status == "fail"
    assert verify_menu(True, True).status == "ambiguous"
