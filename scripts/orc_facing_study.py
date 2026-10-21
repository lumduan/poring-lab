#!/usr/bin/env python3
"""THE FACING STUDY (docs/planning/orcsdun01-detector.md 3e, a DRAFT for Batt): which of a monster's
drawn VIEWS the client shows, measured on the FITTING block col3 only, against candidate rules.

    orc_facing_study.py classes [--kb DIR]                the view classes of each species' ACT
    orc_facing_study.py rows SESSION --half 1|2 [--every 2] [--workers 4] --params PARAMS --out ROWS
    orc_facing_study.py score ROWS [ROWS ...] [--margin 0.05] --out JSON

OFFLINE ONLY (ADR-0007: packets are ground truth for labels, never an agent input): the session's
packets, its JPEG shards, the local KB, the decoded sprites and the map's models (client data,
/dev/shm only). No GPU, no client. The CHECK block (col1) and the TEST block (col2) are refused by
name: this study reads col3, the block the label fix's parameters were measured on.

WHY THE VIEW CLASS, NOT THE HEADING. Every orcsdun01 species' ACT draws its 8 directions in PAIRS
of identical images (S = SW, W = NW, N = NE, E = SE for the walkers and the bats; the two plants
have two mirrored images). Under the current mapping (camera.displayed_direction, nostalro's
(camera_dir + 12 - heading) % 8) an AXIS heading shares its image with its CLOCKWISE diagonal
neighbour (N with NE, W with NW, S with SW, E with SE). A "best of the 8 headings" that keeps the
first of equal scores can therefore never name W, S or E: 3c's "after an axis move the client draws
a diagonal view" (best view -45 deg 153 of 259) is mostly that tie. This study scores the distinct
IMAGES (the classes) and compares classes.

ROWS. Every --every-th recorded frame inside a dwell of the chosen HALF (the session's dwells in
time order: half 1 = the first n // 2, half 2 = the rest), outside the GM-command windows, at the
frozen packet -> frame offset (1d) with the flyers' frozen anchor (1b). Each orcsdun01 monster that
is STANDING (section 3's rule: idle >= 1 s) or WALKING, isolated (120 px), clear of the UI and the
edges (16 px): its NCC for each view class (label_check's masked NCC, the best over the action's
frames and every offset within +-3 px standing / +-4 px walking), whether its box meets a map model
(1c, a flag here, not an exclusion), the camera geometry (the eye -> unit azimuth, the screen x),
and where its facing could come from: the appear packet's heading (a unit that APPEARED standing),
its move (from -> to; the A* path the Timeline walks, rAthena's game rule; the diagonal-first and
the straight-first paths), the step it walks, its facing before the move, and its previous move.

SCORE. Each candidate rule names a heading (or directly an ACT direction); the species' view class
of that ACT direction is compared with the drawn class (the best-scoring one), per state / move
shape / species, on samples whose best class beats the second by >= --margin (all samples
reported too) and per EPISODE (one unit's one standing spell or one walk: the majority drawn class).
Also an ESTIMATE of C1's low share on this block (``c1_like``: standing, clear of the models, the
rule's view scored at the projected place) -- an estimate on the fitting block, never the check.

THE PROTOCOL (fixed at the commit time of this file's first commit, BEFORE half 2's rows were made): the rules
were explored on half 1 only; ``fix2`` (fix2_heading) is the rule chosen there. Half 2 CONFIRMS it
if, on its decisive rows (margin 0.05, best class >= tau 0.092), fix2's pooled agreement is >= 0.85
AND it is >= the frozen 1a rule's (``a_whole_vector|yaw0``) in every state x move shape with >= 20
rows. Every other rule is reported on both halves, unchanged.
"""

from __future__ import annotations

import argparse
import bisect
import json
import math
import sys
from collections import Counter, defaultdict
from collections.abc import Callable, Iterable, Sequence
from pathlib import Path
from typing import Any

import numpy as np
import numpy.typing as npt

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import label_check  # noqa: E402
import orc_camera_check as occ  # noqa: E402
import orc_labels_fix as olf  # noqa: E402
import qa_export  # noqa: E402

from poring_dataset.camera import CELL, displayed_direction  # noqa: E402
from poring_dataset.labels import in_windows  # noqa: E402
from poring_dataset.render import Actor, MonsterAction, SpriteSheet, predict_sprite  # noqa: E402
from poring_dataset.sprites import compose_frame  # noqa: E402
from poring_dataset.timeline import _cells, tick_of, walk_ms  # noqa: E402
from poring_packets.world import (  # noqa: E402
    HEADING_OF_STEP,
    TICK_MOD,
    direction_toward,
    heading_of,
    ticks_since,
)

SPECIES = (1153, 1152, 1005, 1042, 1111, 1082, 1084)
HELD_OUT = ("-col1", "-col2")  # the CHECK block and the TEST block: never read here
R_STAND, R_WALK = 3, 4  # the +- px search of the class scores
GROUPS = {"idle": int(MonsterAction.IDLE), "walk": int(MonsterAction.WALK)}

# --- pure parts -------------------------------------------------------------------------------


def refuse_held_out(session: Path) -> None:
    name = session.name.rstrip("/")
    if any(name.endswith(s) for s in HELD_OUT):
        raise SystemExit(f"{name}: col1 (the check block) and col2 (the test block) are not read "
                         "by the facing study")  # fmt: skip


def view_classes(sheet: SpriteSheet, group: int) -> list[tuple[int, ...]]:
    """The ACT directions of one action group that draw the SAME image in every frame (the composed
    RGBA and its origin), as classes in direction order: [(0, 1), (2, 3), (4, 5), (6, 7)] for an
    orc's idle. Needs the SPR."""
    if sheet.spr is None:
        raise ValueError("the classes need the sprite pixels")
    act = sheet.act

    def frames(d: int) -> list[tuple[bytes, tuple[int, ...], float, float]]:
        ai = act.action_index(group, d)
        out = []
        for m in range(sheet.motions(ai)):
            rgba, (ox, oy) = compose_frame(sheet.spr, act, ai, m)  # type: ignore[arg-type]
            out.append((rgba.tobytes(), rgba.shape, ox, oy))
        return out

    sig = [frames(d) for d in range(8)]
    classes: list[tuple[int, ...]] = []
    seen: set[int] = set()
    for d in range(8):
        if d in seen:
            continue
        same = tuple(e for e in range(8) if e not in seen and sig[e] == sig[d])
        seen.update(same)
        classes.append(same)
    return classes


def class_index(classes: Sequence[Sequence[int]], act_dir: int) -> int:
    for i, c in enumerate(classes):
        if act_dir % 8 in c:
            return i
    raise ValueError(f"ACT direction {act_dir} is in no class {classes}")


def compass(heading: int) -> float:
    """An RO heading (0 = north, counter-clockwise) as a compass angle (clockwise from north)."""
    return (-45.0 * heading) % 360.0


def act_floor(heading: int, az_deg: float, sign: float = 1.0) -> int:
    """The ACT direction when the client quantises the facing RELATIVE TO THE EYE with a floor:
    4 + floor((compass - sign * azimuth) / 45). With azimuth 0 it is displayed_direction at yaw 0;
    an axis heading sits ON a class boundary, so the sign of the azimuth picks its side."""
    rho = compass(heading) - sign * az_deg
    return int(4 + math.floor(rho / 45.0)) % 8


def axis(h: int | None) -> bool:
    return h is not None and h % 2 == 0


def shape_of(dx: int, dy: int) -> str:
    if not dx and not dy:
        return "none"
    if not dx or not dy:
        return "axis"
    return "diagonal" if abs(dx) == abs(dy) else "mixed"


def heading22(dx: int, dy: int) -> int | None:
    """The move vector's heading rounded to the nearest 45 degrees (sectors at +-22.5)."""
    if not dx and not dy:
        return None
    ang = math.degrees(math.atan2(-dx, dy)) % 360.0  # counter-clockwise from north, like RO
    return int(math.floor((ang + 22.5) / 45.0)) % 8


def step_headings(start: tuple[int, int], cells: Sequence[tuple[int, int]]) -> list[int]:
    out, (x, y) = [], start
    for cx, cy in cells:
        h = heading_of(cx - x, cy - y)
        if h is not None:
            out.append(h)
        x, y = cx, cy
    return out


def diagonal_first(x0: int, y0: int, x1: int, y1: int) -> list[tuple[int, int]]:
    """rAthena's easy path on open ground (path.cpp's flag & 1 branch, re-expressed): the
    diagonal steps first, then straight. Ideas only (GPL): our own code."""
    cells, x, y = [], x0, y0
    while (x, y) != (x1, y1):
        x += (x1 > x) - (x1 < x)
        y += (y1 > y) - (y1 < y)
        cells.append((x, y))
    return cells


def straight_first(x0: int, y0: int, x1: int, y1: int) -> list[tuple[int, int]]:
    """The mirror order: the straight steps first, then the diagonal ones (a client that plans
    the other way round would end on a diagonal)."""
    dx, dy = x1 - x0, y1 - y0
    n_diag = min(abs(dx), abs(dy))
    n_straight = max(abs(dx), abs(dy)) - n_diag
    sx, sy = (dx > 0) - (dx < 0), (dy > 0) - (dy < 0)
    cells, x, y = [], x0, y0
    for _ in range(n_straight):
        if abs(dx) > abs(dy):
            x += sx
        else:
            y += sy
        cells.append((x, y))
    for _ in range(n_diag):
        x, y = x + sx, y + sy
        cells.append((x, y))
    return cells


STEP_OF_HEADING = {h: s for s, h in HEADING_OF_STEP.items()}
QUADRANT = {(1, 1): 7, (-1, 1): 1, (-1, -1): 3, (1, -1): 5}  # NE, NW, SW, SE


def quadrant(dx: int, dy: int) -> int | None:
    """The DIAGONAL heading of a move vector's quadrant, an axis vector counted with dx = 0 as WEST
    and dy = 0 as NORTH (north -> NW, east -> NE, west -> NW, south -> SW). None for no move."""
    if not dx and not dy:
        return None
    return QUADRANT[(1 if dx > 0 else -1, 1 if dy >= 0 else -1)]


def lateral_side(axis_heading: int, other: int | None) -> int | None:
    """+1 when ``other`` lies counter-clockwise of the axis heading (h + 1 .. h + 3), -1 when
    clockwise (h - 1 .. h - 3), None when it is the same or opposite heading (or unknown)."""
    if other is None:
        return None
    d = (other - axis_heading) % 8
    return 1 if d in (1, 2, 3) else -1 if d in (5, 6, 7) else None


def side_act(axis_heading: int, side: int | None) -> int | None:
    """The ACT direction an AXIS heading draws when it takes the image of its neighbouring diagonal
    on ``side`` (+1: the counter-clockwise one, -1: the clockwise one), at yaw 0."""
    if side is None:
        return None
    return displayed_direction((axis_heading + side) % 8, 0.0)


# --- the rules (each: row -> ACT direction or None) ---------------------------------------------

Rule = Callable[[dict[str, Any]], int | None]


def _yaw0(h: int | None) -> int | None:
    return None if h is None else displayed_direction(int(h) % 8, 0.0)


def _k3(h: int | None) -> int | None:
    """Axis headings take their counter-clockwise neighbour's image; diagonals unchanged."""
    if h is None:
        return None
    return side_act(h, 1) if axis(h) else _yaw0(h)


def _floor_az(h: int | None, row: dict[str, Any], sign: float) -> int | None:
    return None if h is None else act_floor(int(h), float(row["az_deg"]), sign)


HeadingRule = Callable[[dict[str, Any]], int | None]


def heading_rules() -> dict[str, HeadingRule]:
    """Candidate HEADINGS a row's facing could come from (None: the rule does not apply)."""

    def move(key: str) -> Callable[[dict[str, Any]], int | None]:
        return lambda r: (r.get("move") or {}).get(key)

    def stand_or(key: str) -> Callable[[dict[str, Any]], int | None]:
        def f(r: dict[str, Any]) -> int | None:
            if r["source"] == "stand":
                return r.get("stand_heading")
            return (r.get("move") or {}).get(key)

        return f

    def quad(key: str) -> Callable[[dict[str, Any]], int | None]:
        """The quadrant of the move vector itself."""

        def f(r: dict[str, Any]) -> int | None:
            if r["source"] == "stand":
                return r.get("stand_heading")
            v = (r.get("move") or {}).get(key)
            return None if v is None else quadrant(int(v[0]), int(v[1]))

        return f

    def quad_of(rule: str) -> Callable[[dict[str, Any]], int | None]:
        """The quadrant of another rule's heading (an axis heading -> its diagonal by the
        zero convention; a diagonal stays)."""

        def f(r: dict[str, Any]) -> int | None:
            if r["source"] == "stand":
                return r.get("stand_heading")
            h = (r.get("move") or {}).get(rule)
            return None if h is None else quadrant(*STEP_OF_HEADING[int(h)])

        return f

    return {
        "q_calc_dir": quad_of("whole"),
        "q_whole_vector": quad("d"),
        "q_last_step": quad_of("last_astar"),
        "q_step_now": quad_of("step_now"),
        "timeline": lambda r: r.get("timeline_facing"),
        "a_whole_vector": stand_or("whole"),
        "a_whole_vector_22": stand_or("whole22"),
        "b_last_step_astar": stand_or("last_astar"),
        "b_last_step_diag_first": stand_or("last_diag_first"),
        "b_last_step_straight_first": stand_or("last_straight_first"),
        "b_step_now": lambda r: (r.get("move") or {}).get("step_now"),
        "c_packet_stand": lambda r: r.get("stand_heading") if r["source"] == "stand" else None,
        "move_only_whole": move("whole"),
        "move_only_last_astar": move("last_astar"),
    }


def rules() -> dict[str, Rule]:
    """Every heading rule under each mapping to an ACT direction: ``yaw0`` (the current
    displayed_direction), ``k3`` (axis headings take the counter-clockwise diagonal's image),
    ``floor_az+`` / ``floor_az-`` (the facing relative to the eye -> unit azimuth, floored: the
    azimuth's sign picks an axis heading's side), and the APPROACH rules (an axis heading takes the
    image of the diagonal it turned from: the path's last diagonal step, else the facing before the
    move)."""
    out: dict[str, Rule] = {}

    def mapped(hr: HeadingRule, how: str) -> Rule:
        def f(r: dict[str, Any]) -> int | None:
            h = hr(r)
            if how == "yaw0":
                return _yaw0(h)
            if how == "k3":
                return _k3(h)
            return _floor_az(h, r, 1.0 if how == "floor_az+" else -1.0)

        return f

    for name, hr in heading_rules().items():
        for how in ("yaw0", "k3", "floor_az+", "floor_az-"):
            out[f"{name}|{how}"] = mapped(hr, how)

    def approach(r: dict[str, Any], key: str) -> int | None:
        mv = r.get("move") or {}
        h = r.get("stand_heading") if r["source"] == "stand" else mv.get(key)
        if h is None:
            return None
        if not axis(h):
            return _yaw0(h)
        if r["source"] == "stand":
            return None
        side = lateral_side(h, mv.get("last_diag_astar"))
        if side is None:
            side = lateral_side(h, r.get("facing_before"))
        return side_act(h, side)

    out["approach_last_astar"] = lambda r: approach(r, "last_astar")
    out["approach_step_now"] = lambda r: approach(r, "step_now")
    out[PROPOSED] = lambda r: _yaw0(fix2_heading(r))
    return out


PROPOSED = "fix2"  # the rule 3e proposes, chosen on half 1 BEFORE half 2 was read
FROZEN_1A = "a_whole_vector|yaw0"  # 3b's 1a (timeline.walk_rule_facing) with the current mapping
C1_LIKE_RULES = (PROPOSED, FROZEN_1A, "timeline|yaw0")


def fix2_heading(row: dict[str, Any]) -> int | None:
    """THE PROPOSED RULE (3e DRAFT), as the heading whose image the client draws (yaw 0):
    - a unit that APPEARED standing and has not moved since: its appear packet's heading;
    - a WALKING unit: the quadrant diagonal of its move's whole vector (x1 - x0, y1 - y0);
    - a unit STANDING after its move: rAthena's map_calc_dir heading of the whole vector (the
      frozen 1a heading); an axis heading takes the diagonal of the zero convention (north -> NW,
      east -> NE, south -> SW, west -> NW), a diagonal stays.
    None when none applies (no move seen, no appear heading)."""
    if row["source"] == "stand":
        return row.get("stand_heading")
    mv = row.get("move") or {}
    d = mv.get("d")
    if not d:
        return None
    if row["state"] == "walk":
        return quadrant(int(d[0]), int(d[1]))
    h = direction_toward(int(d[0]), int(d[1]))
    return None if h is None else quadrant(*STEP_OF_HEADING[h])


# --- scoring rows -----------------------------------------------------------------------------


def decisive(row: dict[str, Any], margin: float) -> bool:
    sc = [s for s in row["class_scores"] if s is not None]
    if len(sc) < 2:
        return False
    top = sorted(sc, reverse=True)
    return bool(top[0] >= olf.TAU and top[0] - top[1] >= margin)


def drawn_class(row: dict[str, Any]) -> int | None:
    sc = row["class_scores"]
    vals = [(s, i) for i, s in enumerate(sc) if s is not None]
    return max(vals)[1] if vals else None


def category(row: dict[str, Any]) -> str:
    """state / source / move shape: walk:axis, stand_after_move:mixed, stand_since_appear, ..."""
    if row["state"] == "walk":
        return f"walk:{(row.get('move') or {}).get('shape', 'none')}"
    if row["source"] == "stand":
        return "stand_since_appear"
    if row["source"] == "turn":
        return "turned_in_place"
    return f"stand_after_move:{(row.get('move') or {}).get('shape', 'none')}"


def agree_table(rows: Sequence[dict[str, Any]], rule: Rule, margin: float,
                key: Callable[[dict[str, Any]], str]) -> dict[str, dict[str, Any]]:  # fmt: skip
    """{group: {n, agree, share, n_episodes, agree_episodes, share_episodes}} over the decisive
    rows the rule applies to. An episode = (gid, episode id): its majority drawn class, and the
    rule's class for it (the rows of one episode share one rule value except walk steps, whose
    majority prediction is used)."""
    acc: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    eps: dict[tuple[str, Any], list[tuple[int, int]]] = defaultdict(list)
    for r in rows:
        if not decisive(r, margin):
            continue
        a = rule(r)
        if a is None:
            continue
        drawn = drawn_class(r)
        pred = class_index(r["classes"], a)
        for g in (key(r), "all"):
            acc[g][0] += 1
            acc[g][1] += int(drawn == pred)
            eps[(g, r["episode"])].append((drawn if drawn is not None else -1, pred))
    out: dict[str, dict[str, Any]] = {}
    for g, (n, k) in sorted(acc.items()):
        e_n = e_k = 0
        for (gg, _ep), pairs in eps.items():
            if gg != g:
                continue
            d = Counter(p[0] for p in pairs).most_common(1)[0][0]
            p = Counter(p[1] for p in pairs).most_common(1)[0][0]
            e_n += 1
            e_k += int(d == p)
        out[g] = {"n": n, "agree": k, "share": round(k / n, 4) if n else None,
                  "episodes": e_n, "agree_episodes": e_k,
                  "share_episodes": round(e_k / e_n, 4) if e_n else None}  # fmt: skip
    return out


def c1_like(rows: Sequence[dict[str, Any]], rule: Rule) -> dict[str, Any]:
    """An ESTIMATE on this block, not the check: of the STANDING rows clear of the map's models, the
    share whose rule-chosen view scores below tau AT the projected place (label_check.score, no
    shift: what C1 measures), per species and pooled; and the same for the best class (an upper
    bound: a max over the classes)."""
    by: dict[str, list[int]] = defaultdict(lambda: [0, 0, 0])
    for r in rows:
        if r["state"] != "stand" or r["under_model"] is not None:
            continue
        a = rule(r)
        at0 = r["class_scores_at0"]
        if a is None or any(v is None for v in at0):
            continue
        low = at0[class_index(r["classes"], a)] < olf.TAU
        best_low = max(at0) < olf.TAU
        for g in (str(r["mob"]), "pooled"):
            by[g][0] += 1
            by[g][1] += int(low)
            by[g][2] += int(best_low)
    return {g: {"n": n, "low": k, "low_share": round(k / n, 4) if n else None,
                "low_share_best_class": round(b / n, 4) if n else None}
            for g, (n, k, b) in sorted(by.items())}  # fmt: skip


def summarize(rows: Sequence[dict[str, Any]], margin: float,
              names: Iterable[str] | None = None) -> dict[str, Any]:  # fmt: skip
    rs = rules()
    chosen = list(rs) if names is None else list(names)
    by_cat = {n: agree_table(rows, rs[n], margin, category) for n in chosen}
    by_species = {n: agree_table(rows, rs[n], margin, lambda r: f"{category(r)}|{r['mob']}")
                  for n in chosen}  # fmt: skip
    n_dec = sum(1 for r in rows if decisive(r, margin))
    return {"rows": len(rows), "decisive": n_dec, "margin": margin,
            "categories": dict(Counter(category(r) for r in rows if decisive(r, margin))),
            "by_category": by_cat, "by_category_species": by_species}  # fmt: skip


# --- the session ------------------------------------------------------------------------------


def halves(dwells: Sequence[tuple[int, int]]) -> dict[int, list[tuple[int, int]]]:
    d = sorted(dwells)
    return {1: d[: len(d) // 2], 2: d[len(d) // 2 :]}


class History:
    """Per unit, its appear packets (stand / move) in receive order (poring_packets events)."""

    def __init__(self, events: Iterable[dict[str, Any]]) -> None:
        self.by: dict[int, list[dict[str, Any]]] = defaultdict(list)
        for e in events:
            if e.get("type") == "entity_appear" and int(e.get("objtype", -1)) == 5:
                self.by[int(e["gid"])].append(e)
        self.times = {g: [int(e["t_mono_ns"]) for e in es] for g, es in self.by.items()}

    def before(self, gid: int, t_ns: int) -> list[dict[str, Any]]:
        """The unit's appear packets received at or before ``t_ns`` (oldest first)."""
        es = self.by.get(gid, [])
        return es[: bisect.bisect_right(self.times.get(gid, []), t_ns)]


def move_info(grid: Any, x0: int, y0: int, x1: int, y1: int) -> dict[str, Any]:
    dx, dy = x1 - x0, y1 - y0
    path = list(_cells(grid, x0, y0, x1, y1))
    hs = step_headings((x0, y0), path)
    diag = [h for h in hs if h % 2 == 1]
    df = step_headings((x0, y0), diagonal_first(x0, y0, x1, y1))
    sf = step_headings((x0, y0), straight_first(x0, y0, x1, y1))
    return {
        "from": [x0, y0], "to": [x1, y1], "d": [dx, dy], "shape": shape_of(dx, dy),
        "steps": len(hs), "whole": direction_toward(dx, dy), "whole22": heading22(dx, dy),
        "last_astar": hs[-1] if hs else None, "first_astar": hs[0] if hs else None,
        "last_diag_astar": diag[-1] if diag else None,
        "astar_path_headings": "".join(str(h) for h in hs),
        "last_diag_first": df[-1] if df else None,
        "last_straight_first": sf[-1] if sf else None,
        "astar_is_diag_first": hs == df,
    }  # fmt: skip


_STATE: dict[str, Any] = {}


def _classes_of(sheet: SpriteSheet, job: int, group: int) -> list[tuple[int, ...]]:
    key = (job, group)
    cache = _STATE.setdefault("classes", {})
    if key not in cache:
        cache[key] = view_classes(sheet, group)
    return cache[key]  # type: ignore[no-any-return]


def _facing_before(gid: int, start_tick: int, t_ref_ns: int) -> tuple[int | None, str | None]:
    """The unit's Timeline facing 1 ms before its walk started (cached per walk)."""
    key = (gid, start_tick)
    cache = _STATE.setdefault("before", {})
    if key not in cache:
        sess = _STATE["sess"]
        t0 = t_ref_ns - ticks_since(tick_of(t_ref_ns), start_tick) * 1_000_000 - 1_000_000
        st = sess.lab.timeline.state(gid, t0)
        cache[key] = (None, None) if st is None else (st.facing, st.facing_from)
    return cache[key]  # type: ignore[no-any-return]


def eye_azimuth(scene: Any, cell: tuple[float, float], alt: float = 0.0) -> float:
    """Degrees clockwise from north of the horizontal eye -> unit direction."""
    eye, _r, _u, _f = scene.camera.basis()
    wx = (cell[0] - scene.player[0]) * CELL
    wz = (cell[1] - scene.player[1]) * CELL
    return math.degrees(math.atan2(wx - float(eye[0]), wz - float(eye[2])))


def class_scores(bgr: npt.NDArray[np.uint8], sheet: SpriteSheet, scene: Any,
                 cell: tuple[float, float], action: int, classes: Sequence[Sequence[int]],
                 anchor: tuple[float, float], r: int,
                 ) -> tuple[list[float | None], list[float | None], Any]:  # fmt: skip
    """Per class: (the best NCC within +-r px over the action's frames, the NCC at the projected
    place) and the union box of the classes' predictions."""
    yaw = scene.camera.yaw
    best: list[float | None] = []
    at0: list[float | None] = []
    boxes = []
    for c in classes:
        d = c[0]
        heading = (int(round(-math.degrees(yaw) / 45.0)) % 8 + 12 - d) % 8  # displayed -> d
        pred = predict_sprite(Actor(cell, heading, action), sheet, scene, olf.K)
        if pred is None:
            best.append(None)
            at0.append(None)
            continue
        pred = olf.shifted(pred, *anchor)
        assert pred.direction == d, (pred.direction, d)
        boxes.append(pred.box)
        bo = occ.best_offset(bgr, sheet, pred, r)
        best.append(None if bo is None else round(bo[0], 4))
        s0 = label_check.score(bgr, sheet, pred)
        at0.append(None if s0 is None else round(s0, 4))
    union = None
    if boxes:
        union = (min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes),
                 max(b[3] for b in boxes))  # fmt: skip
    return best, at0, union


def _rows_of(ref: qa_export.JpegRef) -> tuple[list[dict[str, Any]], Counter[str]]:
    sess, occl, hist = _STATE["sess"], _STATE["occl"], _STATE["hist"]
    off_ns, anchors, half = _STATE["offset_ns"], _STATE["anchors"], _STATE["half"]
    tl = sess.lab.timeline
    dropped: Counter[str] = Counter()
    tw = ref.t_mono_ns - off_ns
    world = tl.world_at(tw)
    fw = tl._frame_of(world, tw)
    scene = sess.scene(fw)
    if scene is None:
        dropped["frame_no_scene"] += 1
        return [], dropped
    now = {s.gid: s for s in tl._states_of(world, tw)}
    prev = {s.gid: s for s in tl.states(tw - occ.STANDING_NS)}
    units = olf.unit_anchors(fw, scene)
    grid = tl.grid(world.map)
    tick = tick_of(tw)
    bgr = None
    rows = []
    for e in fw.entities:
        if e.objtype != 5 or e.hidden or e.job not in SPECIES:
            continue
        st = now.get(e.gid)
        sheet = sess.lab.sheets(e.job)
        if st is None or sheet is None:
            continue
        if st.state == "walk":
            state, group, r = "walk", GROUPS["walk"], R_WALK
        elif occ.standing(st, prev.get(e.gid)):
            state, group, r = "stand", GROUPS["idle"], R_STAND
        else:
            dropped[f"state:{st.state}"] += 1
            continue
        anchor = units.get(e.gid)
        if anchor is None or not olf.isolated_from(anchor, e.gid, units):
            dropped["crowded"] += 1
            continue
        classes = _classes_of(sheet, e.job, group)
        if len(classes) < 2:
            dropped["one_view"] += 1
            continue
        if bgr is None:
            bgr = qa_export.read_jpeg(ref)
        shift = anchors.get(int(e.job), (0.0, 0.0))
        best, at0, union = class_scores(bgr, sheet, scene, (float(e.x), float(e.y)), group,
                                        classes, shift, r)  # fmt: skip
        if union is None or not occ.clear_box(union, sess.lab.ui_rects, sess.lab.size):
            dropped["ui_or_edge"] += 1
            continue
        ent = world.entities.get(e.gid)
        assert ent is not None
        walk = ent.walk
        move = None
        source = "stand"
        stand_heading = None
        facing_before = None
        if walk is not None and ticks_since(tick, walk.start_tick) >= 0:
            move = move_info(grid, walk.x0, walk.y0, walk.x1, walk.y1)
            source = "move"
            move["since_start_ms"] = ticks_since(tick, walk.start_tick)
            move["walk_ms"] = walk_ms(walk, grid)
            if state == "walk":
                move["step_now"] = st.facing if st.facing_from == "walk" else None
            fb = _facing_before(e.gid, walk.start_tick, tw)
            facing_before = fb[0]
            move["facing_before_from"] = fb[1]
            turn = ent.motion.turn
            arrived = (walk.start_tick + move["walk_ms"]) % TICK_MOD
            if (turn is not None and turn.tick is not None and state == "stand"
                    and ticks_since(turn.tick, arrived) > 0):  # fmt: skip
                source = "turn"
        elif walk is None:
            stand_heading = ent.dir
            if ent.motion.turn is not None and ent.motion.turn.source != "appear":
                source = "turn"
        else:
            dropped["walk_not_started"] += 1
            continue
        past = hist.before(e.gid, int(tw))
        prev_move = None
        moves = [p for p in past if p.get("kind") == "move" and p.get("x1") is not None]
        if source == "stand":
            if moves:
                p = moves[-1]
                prev_move = move_info(grid, int(p["x"]), int(p["y"]), int(p["x1"]), int(p["y1"]))
                prev_move["ends_here"] = [int(p["x1"]), int(p["y1"])] == [ent.x, ent.y]
        elif len(moves) >= 2:
            p = moves[-2]
            prev_move = move_info(grid, int(p["x"]), int(p["y"]), int(p["x1"]), int(p["y1"]))
            prev_move["contiguous"] = [int(p["x1"]), int(p["y1"])] == [walk.x0, walk.y0] \
                if walk is not None else None  # fmt: skip
        episode = f"{e.gid}:{state}:{walk.start_tick if walk is not None else 'appear'}"
        hit = occl.hit(scene, union) if occl is not None else None
        rows.append({
            "half": half, "frame_id": ref.frame_id, "t_ns": ref.t_mono_ns, "gid": e.gid,
            "mob": e.job, "state": state, "source": source, "episode": episode,
            "cell": [round(e.x, 2), round(e.y, 2)],
            "rel": [round(e.x - scene.player[0], 2), round(e.y - scene.player[1], 2)],
            "anchor_px": [round(anchor[0], 1), round(anchor[1], 1)],
            "u_minus_cx": round(anchor[0] - scene.camera.cx, 1),
            "az_deg": round(eye_azimuth(scene, (float(e.x), float(e.y))), 3),
            "classes": [list(c) for c in classes],
            "class_scores": best, "class_scores_at0": at0,
            "union_box": [round(v, 1) for v in union], "under_model": hit,
            "timeline_facing": st.facing, "timeline_from": st.facing_from,
            "stand_heading": stand_heading, "facing_before": facing_before,
            "idle_ms": None if st.since_ns is None or state != "stand"
            else round((tw - st.since_ns) / 1e6),
            "move": move, "prev_move": prev_move,
        })  # fmt: skip
    return rows, dropped


def cmd_rows(a: argparse.Namespace) -> dict[str, Any]:
    refuse_held_out(a.session)
    params = olf.load_params(a.params)
    if params["measured_on"] != a.session.name.rstrip("/"):
        raise SystemExit(f"the frozen parameters were measured on {params['measured_on']}: "
                         "the study reads that block only")  # fmt: skip
    sess = olf.Session.open(a.session, a.kb)
    occl = olf.Occluders(a.rsw, a.models) if a.models.exists() else None
    if occl is not None and occl.provenance()["rsw_sha256"] != params["occluders"]["rsw_sha256"]:
        raise SystemExit("the RSW differs from the frozen one")
    hist = History(sess.lab.timeline.events)
    spans = halves(sess.dwells)[a.half]
    refs = [ref for ref in sess.refs[:: a.every]
            if in_windows(ref.t_mono_ns, spans)
            and not in_windows(ref.t_mono_ns, sess.lab.windows)]  # fmt: skip
    _STATE.update(sess=sess, occl=occl, hist=hist, offset_ns=int(float(params["offset_ms"]) * 1e6),
                  anchors=olf.anchors_of(params), half=a.half)  # fmt: skip
    rows: list[dict[str, Any]] = []
    dropped: Counter[str] = Counter()
    for rs, d in olf.run_parallel(_rows_of, refs, a.workers):
        rows += rs
        dropped.update(d)
    rows.sort(key=lambda r: (r["frame_id"], r["gid"]))
    out = {
        "what": "the facing study's rows (orc_facing_study.py rows)", "session": sess.sid,
        "half": a.half, "dwells": [spans[0][0], spans[-1][1]] if spans else None,
        "n_dwells": len(spans), "every": a.every, "frames": len(refs),
        "offset_ms": params["offset_ms"], "anchors_px": params["anchors_px"],
        "params_sha256": olf.sha256_file(a.params), "commit": olf.git_head(),
        "made_at": olf.now_ict(), "dropped": dict(sorted(dropped.items())), "rows": rows,
    }  # fmt: skip
    return out


def cmd_classes(a: argparse.Namespace) -> dict[str, Any]:
    qa_export.KB_CLASSES = a.kb / "classes.json"
    qa_export.KB_SPRITE_NAMES = a.kb / "monster_sprite_names.json"
    sheets = qa_export.Sheets()
    out: dict[str, Any] = {}
    for job in SPECIES:
        sh = sheets(job)
        if sh is None:
            out[str(job)] = None
            continue
        out[str(job)] = {g: view_classes(sh, gi) for g, gi in GROUPS.items()}
    return out


def cmd_score(a: argparse.Namespace) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    meta = []
    for p in a.rows:
        doc = json.loads(Path(p).read_text())
        rows += doc["rows"]
        meta.append({k: doc.get(k) for k in ("session", "half", "every", "frames", "made_at")})
    by_half: dict[str, Any] = {}
    for half in sorted({r["half"] for r in rows}):
        hr = [r for r in rows if r["half"] == half]
        by_half[str(half)] = {
            "margin": summarize(hr, a.margin, a.rule or None),
            "all": summarize(hr, -1.0, a.rule or None),
            "clear_of_models": summarize([r for r in hr if r["under_model"] is None], a.margin,
                                         a.rule or None),
            "c1_like": {n: c1_like(hr, rules()[n]) for n in C1_LIKE_RULES},
        }  # fmt: skip
    return {"inputs": meta, "margin": a.margin, "by_half": by_half}


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("classes")
    p.add_argument("--kb", type=Path, default=ROOT / "data" / "kb")
    p.add_argument("--out", type=Path, required=True)
    p = sub.add_parser("rows")
    p.add_argument("session", type=Path)
    p.add_argument("--half", type=int, choices=(1, 2), required=True)
    p.add_argument("--kb", type=Path, default=ROOT / "data" / "kb")
    p.add_argument("--every", type=int, default=2)
    p.add_argument("--workers", type=int, default=1)
    p.add_argument("--params", type=Path, required=True)
    p.add_argument("--rsw", type=Path, default=olf.RSW_PATH)
    p.add_argument("--models", type=Path, default=olf.MODEL_DIR)
    p.add_argument("--out", type=Path, required=True)
    p = sub.add_parser("score")
    p.add_argument("rows", nargs="+", type=Path)
    p.add_argument("--margin", type=float, default=0.05)
    p.add_argument("--rule", action="append", default=[], help="only these rules (repeatable)")
    p.add_argument("--out", type=Path, required=True)
    a = ap.parse_args(argv)
    run = {"classes": cmd_classes, "rows": cmd_rows, "score": cmd_score}
    out = run[a.cmd](a)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(out, indent=1) + "\n")
    if a.cmd != "rows":
        print(json.dumps(out, indent=1)[:4000])
    else:
        print(f"{len(out['rows'])} rows from {out['frames']} frames; dropped {out['dropped']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
