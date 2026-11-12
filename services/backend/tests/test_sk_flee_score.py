"""sk_flee_score.py (rogue-xmas02.md 4CS / 4CT): the Stormy Knight flee proof's scorer, PURE parts.
The positive case from a real session (p18, 2026-11-08 23:16: the knight's hit, its skill as an
unexplained drop, her death 938 ms later) is recorded in 4CT."""

import importlib.util
import sys
from pathlib import Path

_P = Path(__file__).resolve().parents[3] / "scripts" / "sk_flee_score.py"
_spec = importlib.util.spec_from_file_location("sk_flee_score", _P)
assert _spec is not None and _spec.loader is not None
sk = importlib.util.module_from_spec(_spec)
sys.modules["sk_flee_score"] = sk
_spec.loader.exec_module(sk)

S = 1_000_000_000
AID = 2000002
KG = 110015908


def _events(end: int = 200) -> list[dict]:
    return [{"kind": "spawn", "i": "F1", "t_ns": 10 * S},
            {"kind": "immune", "want": "off", "got": "off", "t_ns": 20 * S},
            {"kind": "trial_end", "i": "F1", "t_ns": end * S}]  # fmt: skip


def _appear(t: float, gid: int = KG, job: int = 1251) -> dict:
    return {"type": "entity_appear", "t_mono_ns": int(t * S), "gid": gid, "job": job}


def _act(t: float, src: int = KG, dmg: int = 1170) -> dict:
    return {"type": "act", "t_mono_ns": int(t * S), "src_gid": src, "target_gid": AID,
            "damage": dmg}  # fmt: skip


def _hp(t: float, v: int) -> dict:
    return {"type": "stat_change", "t_mono_ns": int(t * S), "name": "hp", "value": v}


def _fly(t: float) -> list[dict]:
    tele = {"type": "map_change", "t_mono_ns": int((t + 0.4) * S), "gm_command": False}
    return [{"type": "use_item_request", "t_mono_ns": int(t * S)}, tele]


def _score(packets: list[dict], end: int = 200) -> dict:
    w = sk.trial_windows(_events(end))[0]
    return sk.score_trial(w, packets, AID)


def test_flee_before_the_knight_hit_passes() -> None:
    r = _score([_appear(40), *_fly(45), _act(46)])
    assert r["counted"] and r["passed"]
    assert r["flee_t"] == 45 * S and r["appear_to_flee_ms"] == 5000.0


def test_hit_before_flee_fails() -> None:
    r = _score([_appear(40), _act(44), *_fly(45)])
    assert r["counted"] and not r["passed"]


def test_a_gm_warp_is_not_a_flee() -> None:
    gm = {"type": "map_change", "t_mono_ns": 45 * S, "gm_command": True}
    r = _score([_appear(40), gm])
    assert r["flee_t"] is None and not r["counted"] and r["note"].startswith("no contest")


def test_no_knight_is_not_counted() -> None:
    r = _score([*_fly(45)])
    assert not r["counted"] and r["note"] == "the knight never appeared"


def test_knight_in_view_before_the_window_opens_it() -> None:
    r = _score([_appear(15), *_fly(25)])
    assert r["appear_t"] == 20 * S and r["passed"]


def test_unexplained_drop_counts_as_a_knight_hit() -> None:
    # p18's shape: the knight's skill is not an act; hp falls 2209 -> 1 with 900 of act damage
    r = _score([_appear(40), _hp(41, 2209), _act(41.5, src=777, dmg=900), _hp(42, 1),
                *_fly(43)])  # fmt: skip
    assert r["hit_t"] == 42 * S and r["unexplained_drop"] == [42 * S, 1308]
    assert r["counted"] and not r["passed"]


def test_death_by_vanish_fails_and_is_reported() -> None:
    dead = {"type": "entity_vanish", "t_mono_ns": 42 * S, "gid": AID, "reason": 1}
    r = _score([_appear(40), dead, {"type": "map_change", "t_mono_ns": 50 * S,
                                    "gm_command": False}])  # fmt: skip
    assert r["death_t"] == 42 * S and not r["passed"]


def test_summon_damage_is_reported_not_failed() -> None:
    r = _score([_appear(40), _appear(40, gid=55, job=1515), _act(41, src=55, dmg=300),
                *_fly(42)])  # fmt: skip
    assert r["passed"] and r["summon_damage_before_flee"] == {"1515": 300}


def test_verdict_counts() -> None:
    ok = {"counted": True, "passed": True}
    no = {"counted": False, "passed": False}
    bad = {"counted": True, "passed": False}
    assert sk.verdict([ok] * 5)["proof"] == "PASS"
    assert sk.verdict([ok] * 4 + [no])["proof"] == "NO_VERDICT"
    assert sk.verdict([ok] * 4 + [bad])["proof"] == "FAIL"
