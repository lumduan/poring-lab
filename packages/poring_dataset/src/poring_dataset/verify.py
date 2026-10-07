"""Outcome verifiers: did an action do what it was meant to do? (Batt 2026-10-07; demonstrations.md)

OFFLINE ONLY. Packets are ground truth for VERIFICATION (ADR-0007), never decision input. Every
function here is pure: decoded events (dicts, as in packets.jsonl.gz) + what the action intended
-> a Verdict (status, cause, evidence). It never reads the actor's stated reason: the OUTCOME
judges.

  login   our login_accepted (aid) -> char_selected -> map_enter, in order, within the window
  walk    the server accepted a walk to the TARGET cell (self_move destination) and nothing moved
          us elsewhere before the walk's duration (path cells x our speed); a click that never
          produced a move request, a different destination, or a stop short is a FAIL
  attack  an `act` FROM our aid ON the intended gid within the window: damage, MISS, critical and
          lucky dodge all count (the right target was hit at). Our act on another gid is a FAIL
          (wrong target), and so is our walk with no act (the click became a walk). The target
          vanishing first, or only OTHER attackers acting on it, is AMBIGUOUS.
  menu    a client-side window: its anchor absent before and present after (screen, not packets)

The windows are pre-registered (docs/demonstrations.md) and part of VERIFIER_VERSION.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

VERIFIER_VERSION = "1"
LOGIN_WINDOW_S = 60.0
WALK_REQUEST_S = 2.0  # the click must produce our move request within this
WALK_SLACK_S = 1.5  # added to the walk's own duration
ATTACK_WINDOW_S = 8.0  # cap: walk-in + swing
ATTACK_SWING_S = 2.0  # after the estimated walk-in
DIAGONAL = math.sqrt(2.0)  # rAthena: a diagonal step takes walk_speed * 14 / 10

Event = Mapping[str, Any]


@dataclass(frozen=True)
class Verdict:
    status: str  # success | fail | ambiguous
    cause: str | None = None
    evidence: dict[str, Any] = field(default_factory=dict)

    @property
    def verifier(self) -> str:
        return f"verify@{VERIFIER_VERSION}"


def _window(
    events: Iterable[Event], t0: int, seconds: float, t_end: int | None = None
) -> list[Event]:
    """Events in [t0, t0 + seconds], cut at ``t_end`` (the NEXT action's start): a window never
    lends one attempt's packets to another (2026-10-07: 60 s login windows overlapped the next
    attempt, 33 s later)."""
    t1 = t0 + int(seconds * 1e9)
    if t_end is not None:
        t1 = min(t1, t_end)
    return sorted((e for e in events if t0 <= int(e.get("t_mono_ns", 0)) <= t1),
                  key=lambda e: int(e["t_mono_ns"]))  # fmt: skip


def _ms(t0: int, e: Event) -> int:
    return (int(e["t_mono_ns"]) - t0) // 1_000_000


def verify_login(events: Iterable[Event], t0: int, aid: int, t_end: int | None = None) -> Verdict:
    seq = ("login_accepted", "char_selected", "map_enter")
    got: dict[str, Event] = {}
    for e in _window(events, t0, LOGIN_WINDOW_S, t_end):
        kind = e.get("type")
        if kind == "login_accepted" and int(e.get("aid", -1)) != aid:
            continue  # another account (never ours to judge)
        if kind in seq and kind not in got and all(k in got for k in seq[: seq.index(kind)]):
            got[kind] = e
    evidence = {k: _ms(t0, e) for k, e in got.items()}
    missing = [k for k in seq if k not in got]
    if missing:
        return Verdict("fail", f"no {missing[0]} within {LOGIN_WINDOW_S:g} s", evidence)
    return Verdict("success", None, {**evidence, "map": got["char_selected"].get("map")})


def path_seconds(a: tuple[int, int], b: tuple[int, int], speed_ms: float) -> float:
    """Free-path walk time (straight + diagonal steps), rAthena's step costs."""
    dx, dy = abs(a[0] - b[0]), abs(a[1] - b[1])
    diag = min(dx, dy)
    return (diag * DIAGONAL + (max(dx, dy) - diag)) * speed_ms / 1000.0


def verify_walk(
    events: Iterable[Event],
    t0: int,
    aid: int,
    target: tuple[int, int],
    speed_ms: float = 150.0,
    t_end: int | None = None,
) -> Verdict:
    evs = _window(events, t0, WALK_REQUEST_S + 30.0, t_end)
    first = next((e for e in evs if e.get("type") in ("self_move_request", "self_move")), None)
    if first is None or (int(first["t_mono_ns"]) - t0) > WALK_REQUEST_S * 1e9:
        return Verdict("fail", f"no move request within {WALK_REQUEST_S:g} s (click not a walk)")
    move = next((e for e in evs if e.get("type") == "self_move"), None)
    if move is None:
        return Verdict("fail", "move requested but never accepted (no self_move)")
    start, dest = (int(move["x0"]), int(move["y0"])), (int(move["x1"]), int(move["y1"]))
    off = max(abs(dest[0] - target[0]), abs(dest[1] - target[1]))
    evidence: dict[str, Any] = {"start": list(start), "dest": list(dest), "target": list(target),
                                "off_cells": off, "accepted_ms": _ms(t0, move)}  # fmt: skip
    if off:
        return Verdict("fail", f"walked to a different cell ({off} off)", evidence)
    t_move = int(move["t_mono_ns"])
    arrive = t_move + int((path_seconds(start, dest, speed_ms) + WALK_SLACK_S) * 1e9)
    for e in evs:
        t = int(e["t_mono_ns"])
        if t <= t_move or t > arrive:
            continue
        kind = e.get("type")
        if kind in ("map_change", "map_enter"):
            return Verdict("ambiguous", f"{kind} during the walk", evidence)
        if kind == "self_move" and (int(e["x1"]), int(e["y1"])) != dest:
            return Verdict(
                "fail", "re-routed before arriving", {**evidence, "new_dest": [e["x1"], e["y1"]]}
            )
        if (
            kind == "entity_stop"
            and int(e.get("gid", -1)) == aid
            and (int(e["x"]), int(e["y"])) != dest
        ):
            return Verdict("fail", "stopped short", {**evidence, "stop": [e["x"], e["y"]]})
        if kind == "entity_vanish" and int(e.get("gid", -1)) == aid:
            return Verdict("ambiguous", "we vanished (died?) during the walk", evidence)
    return Verdict("success", None, {**evidence, "arrive_ms": (arrive - t0) // 1_000_000})


def position_before(events: Iterable[Event], t: int, aid: int) -> tuple[int, int] | None:
    """Our cell just before ``t``: the last warp / map entry / own stop, or a walk that has had
    time to finish (its destination), else that walk's start."""
    pos: tuple[int, int] | None = None
    for e in sorted(events, key=lambda e: int(e.get("t_mono_ns", 0))):
        te = int(e.get("t_mono_ns", 0))
        if te >= t:
            break
        kind = e.get("type")
        warped = kind in ("map_change", "map_enter") and "x" in e
        stopped = kind == "entity_stop" and int(e.get("gid", -1)) == aid
        if warped or stopped:
            pos = (int(e["x"]), int(e["y"]))
        elif kind == "self_move":
            a, b = (int(e["x0"]), int(e["y0"])), (int(e["x1"]), int(e["y1"]))
            pos = b if t - te >= path_seconds(a, b, 150.0) * 1e9 else a
    return pos


def speed_before(events: Iterable[Event], t: int, default: float = 150.0) -> float:
    """Our walk speed (ms per cell) from the last `speed` stat change before ``t``."""
    speed = default
    for e in events:
        if e.get("type") == "stat_change" and e.get("name") == "speed" and int(e["t_mono_ns"]) < t:
            speed = float(e["value"])
    return speed


def verify_attack(
    events: Iterable[Event],
    t0: int,
    aid: int,
    target_gid: int,
    walk_s: float = 0.0,
    t_end: int | None = None,
) -> Verdict:
    window = min(ATTACK_WINDOW_S, walk_s + ATTACK_SWING_S)
    evs = _window(events, t0, ATTACK_WINDOW_S + 4.0, t_end)
    t_end = t0 + int(window * 1e9)
    others: list[int] = []
    for e in evs:
        t = int(e["t_mono_ns"])
        kind = e.get("type")
        if kind == "entity_vanish" and int(e.get("gid", -1)) == target_gid and t <= t_end:
            return Verdict("ambiguous", f"target vanished (reason {e.get('reason')}) first",
                           {"others": others})  # fmt: skip
        if kind != "act":
            continue
        src, tgt = int(e.get("src_gid", -1)), int(e.get("target_gid", -1))
        if src == aid:
            ev = {"kind": e.get("kind"), "damage": e.get("damage"), "ms": _ms(t0, e)}
            if t > t_end:
                return Verdict("ambiguous", "our act came after the window", {**ev, "target": tgt})
            if tgt == target_gid:
                return Verdict("success", None, ev)
            if e.get("kind") not in ("sit", "stand", "pickup"):
                return Verdict("fail", "attacked a different target", {**ev, "target": tgt})
        elif tgt == target_gid and t <= t_end:
            others.append(src)
    # A walk CLICK sends our move request (CZ_REQUEST_MOVE2); an attack click sends an attack
    # request instead, and the server's own approach walk (self_move) proves nothing either way.
    walked = any(e.get("type") == "self_move_request" and int(e["t_mono_ns"]) <= t_end
                 for e in evs)  # fmt: skip
    if others:
        return Verdict("ambiguous", "only other attackers acted on the target", {"others": others})
    if walked:
        return Verdict("fail", "the click became a walk (no act on the target)")
    return Verdict("fail", "no act and no walk (click ignored)")


def resolve_click(
    point: tuple[float, float],
    boxes: Mapping[int, Sequence[float]],
    anchors: Mapping[int, tuple[float, float]] | None = None,
) -> tuple[int | None, float | None]:
    """The gid a click meant: the predicted box containing it (smallest if several), else the
    nearest anchor; and the click's distance to that sprite (0 inside the box)."""
    x, y = point
    inside = [(abs((b[2] - b[0]) * (b[3] - b[1])), g) for g, b in boxes.items()
              if b[0] <= x <= b[2] and b[1] <= y <= b[3]]  # fmt: skip
    if inside:
        return min(inside)[1], 0.0
    pts = anchors or {g: ((b[0] + b[2]) / 2, b[3]) for g, b in boxes.items()}
    if not pts:
        return None, None
    g, d = min(((g, math.hypot(x - p[0], y - p[1])) for g, p in pts.items()), key=lambda t: t[1])
    return g, round(d, 1)


def verify_menu(before: bool, after: bool) -> Verdict:
    if before:
        return Verdict("ambiguous", "the window was already open before the shortcut")
    if after:
        return Verdict("success")
    return Verdict("fail", "the window did not appear")
