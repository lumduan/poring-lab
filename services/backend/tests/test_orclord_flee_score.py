"""orclord_flee_score (orclord-recognizer.md 12): a trial counts only with a party unit in view,
passes only on an AURA flee before the party's first damage, and bar 1's counting rule."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))

import orclord_flee_score as fs  # noqa: E402

S = 1_000_000_000
AID = 2000009


def _events(flee: dict | None) -> list[dict]:
    ev = [{"t_ns": 0, "kind": "run_start"},
          {"t_ns": 1 * S, "kind": "spawn", "i": 0},
          {"t_ns": 3 * S, "kind": "immune", "want": "off", "got": "off"}]  # fmt: skip
    if flee:
        ev.append({"t_ns": flee["t"], "kind": "flee", "i": 0, "why": flee["why"]})
    ev.append({"t_ns": 20 * S, "kind": "trial_end", "i": 0})
    return ev


def _packets(hit_t: int | None) -> list[dict]:
    p = [{"type": "entity_appear", "gid": 7, "job": 1190, "t_mono_ns": 1 * S},
         {"type": "stat_change", "name": "hp", "value": 2146, "t_mono_ns": 2 * S}]  # fmt: skip
    if hit_t is not None:
        p += [{"type": "act", "src_gid": 7, "target_gid": AID, "damage": 400, "t_mono_ns": hit_t},
              {"type": "stat_change", "name": "hp", "value": 1746, "t_mono_ns": hit_t}]  # fmt: skip
    p.append({"type": "map_change", "gm_command": False, "t_mono_ns": 13 * S})
    return p


def _truth(seen_t: int | None) -> list[dict]:
    rows = [{"t": t * S, "units": []} for t in range(3, 20)]
    if seen_t is not None:
        for r in rows:
            if r["t"] >= seen_t:
                r["units"] = [{"gid": 7, "job": 1190, "in_view": True}]
    return rows


def _score(flee: dict | None, seen_t: int | None, hit_t: int | None) -> dict:
    (w,) = fs.trial_windows(_events(flee))
    return fs.score_trial(w, _truth(seen_t), _packets(hit_t), AID)


def test_an_aura_flee_before_the_first_hit_passes() -> None:
    t = _score({"t": 12 * S, "why": "aura"}, seen_t=11 * S, hit_t=15 * S)
    assert t["counted"] and t["passed"]
    assert t["seen_to_f2_ms"] == 1000.0 and t["f2_to_teleport_ms"] == 1000.0
    assert t["hp_start"] == 2146 and t["hp_min"] == 1746


def test_a_flee_after_the_hit_or_by_hp_fails() -> None:
    assert not _score({"t": 16 * S, "why": "aura"}, seen_t=11 * S, hit_t=15 * S)["passed"]
    assert not _score({"t": 12 * S, "why": "hp"}, seen_t=11 * S, hit_t=None)["passed"]
    assert not _score(None, seen_t=11 * S, hit_t=None)["passed"]


def test_a_trial_with_no_party_in_view_is_not_counted() -> None:
    t = _score({"t": 12 * S, "why": "aura"}, seen_t=None, hit_t=None)  # an aura FP: unseen
    assert not t["counted"] and not t["passed"]


def test_bar1_counts_five_of_six_and_needs_four_counted() -> None:
    def trials(c: int, p: int) -> list[dict]:
        return [{"counted": i < c, "passed": i < p, "died": False} for i in range(6)]

    assert fs.verdict(trials(6, 5))["bar1"] == "PASS"
    assert fs.verdict(trials(6, 4))["bar1"] == "FAIL"
    assert fs.verdict(trials(5, 5))["bar1"] == "PASS"  # ceil(25 / 6) = 5
    assert fs.verdict(trials(5, 4))["bar1"] == "FAIL"
    assert fs.verdict(trials(4, 4))["bar1"] == "PASS"  # ceil(20 / 6) = 4
    assert fs.verdict(trials(3, 3))["bar1"] == "NO_VERDICT"
    assert fs.verdict(trials(6, 6), stopped_dead=True)["bar2"] == "FAIL"


def test_the_press_is_the_fly_wing_request_not_the_late_event() -> None:
    """fp1c: the flee event is logged ~130 ms after the press; the teleport precedes the event."""
    (w,) = fs.trial_windows(_events({"t": 12 * S, "why": "aura"}))
    pk = [p for p in _packets(hit_t=None) if p["type"] != "map_change"]
    press = 12 * S - 130_000_000
    pk += [{"type": "use_item_request", "index": 11, "t_mono_ns": press},
           {"type": "map_change", "gm_command": True, "t_mono_ns": press + 40_000_000}]  # fmt: skip
    t = fs.score_trial(w, _truth(11 * S), pk, AID)
    assert t["flee_t"] == press and t["f2_to_teleport_ms"] == 40.0
    assert t["seen_to_f2_ms"] == 870.0 and t["passed"]
