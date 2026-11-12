#!/usr/bin/env python3
"""The Stormy Knight FLEE proof's scorer (rogue-xmas02.md 4CS / 4CT; committed BEFORE trial F1).
Packets are ground truth OFFLINE only; nothing here reaches the bot.

Per trial k of the trial driver's events.jsonl (`spawn`, `immune`, `trial_end` lines, each with
`t_ns` on the host's CLOCK_MONOTONIC, the packets' clock):
- the WINDOW: from the trial's verified immunity OFF to its `trial_end` (or the last event);
- the KNIGHT: every Stormy Knight (1251) gid the packets show appearing from 2 s before the spawn
  to the window's end; its SUMMONS, reported only: Christmas Goblin (1607, a summon only on this
  map) and Garm Baby (1515, also a regular spawn here, so a Garm Baby is reported, not blamed);
- APPEAR: the first `entity_appear` of a knight gid at or after the window's start (the server's
  view, ~14 cells: wider than the screen) -- or, when the knight was already in view as the window
  opened, the window's start;
- HIT: the knight's first `act` on our AID with damage > 0 (its first act of any damage, a miss
  included, is reported beside it);
- FLEE: our first map change in the window at or after APPEAR that is NOT a GM command's
  (`gm_command` false: a Fly Wing, or a death's return), with the Fly Wing's `use_item_request` in
  the 1.5 s before it as the press time when there is one;
- DEATH: our own `entity_vanish` with reason 1 (died) in the window, or an hp `stat_change` of 0
  (p18, 11-08: the server sent hp 1 and the vanish, never an hp of 0);
- UNEXPLAINED DROP: skill hits are not decoded (only `act`), so the knight's skill hit (p18:
  5,912) is invisible as an act. Between two hp readings in the window, the drop minus the act
  damage on us in between is UNEXPLAINED; one of >= 1,000 (the knight's normal hit was 1,170, a
  Garm Baby's 900) counts as a knight HIT at the later reading.

COUNTED (4CT): the knight appeared in the window AND there was a contest -- a FLEE or a HIT.
A trial without one is NOT counted ("no contest") and is re-run once on the same pair.
PASSED: counted, a FLEE whose press precedes HIT (or no HIT), and no death before the FLEE.
The proof (4CS): PASS when 5 counted trials all pass; any counted fail -> FAIL; fewer than 5
counted after the re-runs -> NO_VERDICT.

    sk_flee_score.py --events EVENTS.jsonl (--packets PACKETS.jsonl.gz | --archive) --out JSON
"""

from __future__ import annotations

import argparse
import gzip
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

KNIGHT = 1251
SUMMONS = (1607, 1515)
PRESS_BEFORE_NS = 1_500_000_000
UNEXPLAINED_HP = 1000
NEED = 5


def _first(ts: Sequence[int]) -> int | None:
    return min(ts) if ts else None


def trial_windows(events: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    """PURE: per spawned trial, its label, spawn time, verified-OFF time and end time."""
    last = max((int(e["t_ns"]) for e in events), default=0)
    out = []
    for sp in (e for e in events if e.get("kind") == "spawn"):
        k, t_sp = str(sp["i"]), int(sp["t_ns"])
        ends = [int(e["t_ns"]) for e in events
                if e.get("kind") == "trial_end" and str(e["i"]) == k]  # fmt: skip
        end_t = ends[0] if ends else last
        offs = [int(e["t_ns"]) for e in events if e.get("kind") == "immune"
                and e.get("want") == "off" and e.get("got") == "off"
                and t_sp <= int(e["t_ns"]) <= end_t]  # fmt: skip
        out.append({"i": k, "spawn_t": t_sp, "off_t": _first(offs), "end_t": end_t})
    return out


def score_trial(w: dict[str, Any], packets: Sequence[dict[str, Any]], aid: int) -> dict[str, Any]:
    """PURE: one trial's APPEAR / HIT / FLEE / DEATH and its verdict (the module docstring)."""
    t0, t1 = w["off_t"], w["end_t"]
    res: dict[str, Any] = {"i": w["i"], "off_t": t0, "end_t": t1}
    if t0 is None:
        return {**res, "counted": False, "passed": False, "note": "no verified immunity OFF"}

    def t(p: dict[str, Any]) -> int:
        return int(p["t_mono_ns"])

    lo = w["spawn_t"] - 2_000_000_000
    appears = [p for p in packets if p.get("type") == "entity_appear" and lo <= t(p) <= t1]
    knights = {int(p["gid"]) for p in appears if p.get("job") == KNIGHT}
    summons = {int(p["gid"]): int(p["job"]) for p in appears if p.get("job") in SUMMONS}
    k_app = [t(p) for p in appears if int(p["gid"]) in knights]
    appear = _first([x for x in k_app if x >= t0])
    gone = [t(p) for p in packets if p.get("type") in ("entity_vanish", "entity_disappear")
            and int(p.get("gid", -1)) in knights and lo <= t(p) <= t0]  # fmt: skip
    if k_app and min(k_app) < t0 and (not gone or max(gone) < min(k_app)):
        appear = t0  # in view as the window opened (appeared before it, never left)
    inwin = [p for p in packets if t0 <= t(p) <= t1]
    on_us = [p for p in inwin if p.get("type") == "act" and int(p.get("target_gid", -1)) == aid]
    k_acts = [p for p in on_us if int(p.get("src_gid", -1)) in knights]
    hit = _first([t(p) for p in k_acts if int(p.get("damage", 0)) > 0])
    k_attack = _first([t(p) for p in k_acts])
    hp_in = [(t(p), int(p["value"])) for p in inwin
             if p.get("type") == "stat_change" and p.get("name") == "hp"]  # fmt: skip
    death = _first([x for x, v in hp_in if v == 0] + [
        t(p) for p in inwin if p.get("type") == "entity_vanish"
        and int(p.get("gid", -1)) == aid and int(p.get("reason", -1)) == 1])  # fmt: skip
    big = None  # the largest unexplained drop (time, hp): a skill hit we cannot see as an act
    for (ta, va), (tb, vb) in zip(hp_in, hp_in[1:], strict=False):
        dmg = sum(max(0, int(p.get("damage", 0))) for p in on_us if ta < t(p) <= tb)
        if va - vb - dmg >= UNEXPLAINED_HP and (big is None or va - vb - dmg > big[1]):
            big = (tb, va - vb - dmg)
    if big is not None and (hit is None or big[0] < hit):
        hit = big[0]
    flee = tele = None
    if appear is not None:
        tele = _first([t(p) for p in inwin if p.get("type") == "map_change"
                       and not p.get("gm_command") and t(p) >= appear])  # fmt: skip
        if tele is not None:
            press = [t(p) for p in inwin if p.get("type") == "use_item_request"
                     and tele - PRESS_BEFORE_NS <= t(p) <= tele]  # fmt: skip
            flee = max(press) if press else tele
    before = flee if flee is not None else t1
    s_dmg: dict[str, int] = {}
    for p in on_us:
        j = summons.get(int(p.get("src_gid", -1)))
        if j is not None and t(p) < before:
            s_dmg[str(j)] = s_dmg.get(str(j), 0) + int(p.get("damage", 0))
    contest = flee is not None or hit is not None
    counted = appear is not None and contest
    died_first = death is not None and (flee is None or death <= flee)
    passed = bool(counted and flee is not None and (hit is None or flee < hit) and not died_first)

    def ms(a: int | None, b: int | None) -> float | None:
        return None if a is None or b is None else round((b - a) / 1e6, 1)

    hp_min = min((v for _, v in hp_in), default=None)
    note = (
        ""
        if counted
        else "the knight never appeared"
        if appear is None
        else "no contest (no flee, no hit)"
    )
    return {**res, "knight_gids": sorted(knights),
            "summons": {str(g): j for g, j in summons.items()},
            "appear_t": appear, "hit_t": hit, "first_attack_t": k_attack, "flee_t": flee,
            "teleport_t": tele, "appear_to_flee_ms": ms(appear, flee),
            "flee_minus_hit_ms": ms(hit, flee), "summon_damage_before_flee": s_dmg,
            "hp_min": hp_min, "unexplained_drop": None if big is None else list(big),
            "death_t": death, "counted": counted, "passed": passed,
            "note": note}  # fmt: skip


def verdict(trials: Sequence[dict[str, Any]], need: int = NEED) -> dict[str, Any]:
    """PURE: the proof (4CS + 4CT): every counted trial passes and there are at least ``need``."""
    c = [x for x in trials if x["counted"]]
    p = sum(1 for x in c if x["passed"])
    if len(c) > p:
        v = "FAIL"
    elif len(c) >= need:
        v = "PASS"
    else:
        v = "NO_VERDICT"
    died = any(x.get("death_t") is not None for x in trials)
    return {"trials": len(trials), "counted": len(c), "passed": p, "needed": need,
            "proof": v, "deaths": sum(1 for x in trials if x.get("death_t") is not None),
            "no_death": not died}  # fmt: skip


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)  # fmt: skip
    ap.add_argument("--events", type=Path, required=True)
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--packets", type=Path, help="a packets.jsonl.gz (a recorder session's)")
    src.add_argument(
        "--archive",
        action="store_true",
        help="read the sniffer's archive (kept 7 days) for the events' span",
    )
    ap.add_argument("--aid", type=int, default=None, help="our AID (default: inferred)")
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args()
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root / "packages/poring_dataset/src"))
    sys.path.insert(0, str(root / "scripts"))
    from poring_dataset.timeline import infer_self_aid

    events = [json.loads(x) for x in a.events.read_text().splitlines() if x.strip()]
    if a.packets is not None:
        with gzip.open(a.packets, "rt") as f:
            packets = [json.loads(x) for x in f]
    else:
        import record_session

        ts = [int(e["t_ns"]) for e in events]
        packets = record_session.packets_for(min(ts) - 5_000_000_000, max(ts))
    aid = a.aid if a.aid is not None else infer_self_aid(packets)
    if aid is None:
        raise SystemExit("our AID could not be inferred: pass --aid")
    trials = [score_trial(w, packets, aid) for w in trial_windows(events)]
    doc = {"aid": aid, "trials": trials, "verdict": verdict(trials)}
    a.out.write_text(json.dumps(doc, indent=1))
    print(json.dumps(doc["verdict"]))
    for x in trials:
        print(json.dumps({k: x.get(k) for k in ("i", "counted", "passed", "appear_to_flee_ms",
                                                 "flee_minus_hit_ms", "summon_damage_before_flee",
                                                 "hp_min", "note")}))  # fmt: skip
    return 0


if __name__ == "__main__":
    sys.exit(main())
