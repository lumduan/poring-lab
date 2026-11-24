"""The next-target MARK (docs/planning/next-target-mark.md Amendment 3; Batt 2026-11-23/24): the
player side's re-find for the runner's own ``--queue``.

The runner (scripts/dungeon_hunt.py, byte-pinned) keeps the OTHER monster boxes of a fight as a
queue and, after the fight and its loot step, re-finds the head on ONE fresh detection within
QUEUE_MATCH_PX of the entry's last foot pixel (``bq_next``). Its trial (rogue-xmas02.md 4CN) lost
98 of 117 re-finds: her own steps moved every pixel of the view (20 of 98), and the one detection
held no box of monsters still standing there (39 of 98 held no monster box at all).

The mark replaces ``bq_next`` (a module-level function the runner looks up by name at each call;
flow_play swaps it for one hunt core and puts it back, as it does ``alarm_seen``):

- each entry is anchored to the WORLD: her cell when it was seen (the hook's trail of her cells)
  plus its own cell relative to her (``QEntry.rel``); its foot is predicted on the CURRENT view from
  her current cell through the runner's own camera (camera_rdp.json + the map's GAT altitudes),
  keeping the box's offset within its cell;
- the re-find matches the fresh detection's boxes at that predicted foot;
- when the detection holds no box there, the predicted foot itself is offered to the runner's own
  ``accept`` (the box path's skips: off the view, ignored spots, unreachable, far) and ``aim``
  (hovers for a SWORD cursor): a strike only on a SWORD, never on a guess alone (``hover_max`` of
  them a pick at most);
- an entry last seen more than ``ttl_s`` ago is dropped.

Everything the runner does with the answer is its own (the strike, the lock, the events). The
returned dict keeps ``bq_next``'s contract exactly: what / n / entry / why, and on an aimed entry
box / rank / moved_px / verdicts, on a pick point.
"""

from __future__ import annotations

import bisect
import contextlib
import json
import math
from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
Cell = tuple[int, int]

MARK_VERSION = "1"
TTL_S = 8.0  # an entry last seen longer ago than this is dropped (the player's mark_ttl_s)
HOVER_MAX = 2  # predicted feet hovered a pick at most when no box is there (mark_hover_max)
AIM_MAX = 3  # entries aimed at (hovered) a pick at most: each aim hovers up to two points
SYNTH_W, SYNTH_H = 48.0, 72.0  # the synthetic box around a predicted foot (a monster's sprite)
TRAIL_KEEP = 600  # her cells kept (the hook's ticks: ~2 min at 5 Hz)


@dataclass(frozen=True)
class SynthBox:
    """A box drawn around a PREDICTED foot (no detection there): what the runner's aim and strike
    read of a box (x0..y1, cls, species, score)."""

    x0: float
    y0: float
    x1: float
    y1: float
    species: str | None
    cls: str = "monster"
    score: float = 0.0


def synth_box(foot: Sequence[float], species: str | None) -> SynthBox:
    """PURE: a monster-sized box whose bottom centre is ``foot``."""
    u, v = float(foot[0]), float(foot[1])
    return SynthBox(u - SYNTH_W / 2, v - SYNTH_H, u + SYNTH_W / 2, v, species)


class CellTrail:
    """Her cells by time (the hook's ticks: HuntTick.t and .pos, time.monotonic -- the box
    watcher's grab times are on the same clock)."""

    def __init__(self, keep: int = TRAIL_KEEP) -> None:
        self.keep = keep
        self.ts: list[float] = []
        self.cells: list[Cell] = []

    def add(self, t: float, cell: Sequence[int] | None) -> None:
        if cell is None:
            return
        c = (int(cell[0]), int(cell[1]))
        if self.ts and t < self.ts[-1]:
            return  # never out of order
        if self.cells and self.cells[-1] == c:
            self.ts[-1] = t  # a still cell: the newest time of it
            return
        self.ts.append(t)
        self.cells.append(c)
        if len(self.ts) > self.keep:
            del self.ts[: len(self.ts) - self.keep]
            del self.cells[: len(self.cells) - self.keep]

    def at(self, t: float) -> Cell | None:
        """Her cell at ``t``: the last one read at or before it (the first one when ``t`` is
        earlier than every read; None: no read yet)."""
        if not self.ts:
            return None
        i = bisect.bisect_right(self.ts, t) - 1
        return self.cells[max(i, 0)]

    def latest(self) -> Cell | None:
        return self.cells[-1] if self.cells else None


def cheb(a: Sequence[int], b: Sequence[int]) -> int:
    return int(max(abs(a[0] - b[0]), abs(a[1] - b[1])))


Project = Callable[[Cell, Cell], tuple[float, float]]


def predict_foot(foot: Sequence[float], rel: Sequence[int] | None, here_then: Cell | None,
                 here_now: Cell | None, project: Project | None
                 ) -> tuple[tuple[float, float], int]:  # fmt: skip
    """PURE but for ``project`` (her cell, a cell relative to her -> its screen point): the
    entry's foot on the CURRENT view and how many cells she moved since it was seen. Unchanged
    when she did not move, or when anything is unknown (no rel, no cells, no projection). Else
    its world cell (here_then + rel) projected from here_now, plus the foot's offset from its own
    cell's point when it was seen (where in its cell it stood, the box's own bias)."""
    f = (float(foot[0]), float(foot[1]))
    if rel is None or here_then is None or here_now is None:
        return f, 0
    moved = cheb(here_then, here_now)
    if moved == 0 or project is None:
        return f, moved
    r_then = (int(rel[0]), int(rel[1]))
    world = (here_then[0] + r_then[0], here_then[1] + r_then[1])
    r_now = (world[0] - here_now[0], world[1] - here_now[1])
    u0, v0 = project(here_then, r_then)
    u1, v1 = project(here_now, r_now)
    return (u1 + f[0] - u0, v1 + f[1] - v0), moved


def foot_of(b: Any) -> tuple[float, float]:
    return ((float(b.x0) + float(b.x1)) / 2, float(b.y1))


def refind_at(pred: Sequence[float], boxes: Sequence[Any], match_px: float,
              own: Callable[[float, float], bool] | None = None
              ) -> tuple[float, Any] | None:  # fmt: skip
    """PURE: (the distance, the box) of the fresh detection's box whose foot is nearest the
    predicted foot, within ``match_px``; our own sprite's boxes (``own`` on a box's centre) left
    out. None: no box there."""
    best: tuple[float, Any] | None = None
    for b in boxes:
        if own is not None and own((float(b.x0) + float(b.x1)) / 2,
                                   (float(b.y0) + float(b.y1)) / 2):  # fmt: skip
            continue
        u, v = foot_of(b)
        d = math.hypot(u - pred[0], v - pred[1])
        if d <= match_px and (best is None or d < best[0]):
            best = (d, b)
    return best


@dataclass
class MarkConf:
    ttl_s: float = TTL_S
    hover_max: int = HOVER_MAX
    aim_max: int = AIM_MAX


def mark_next(
    queue: Sequence[Any],
    values: Mapping[str, float] | None,
    detect: Callable[[], Sequence[Any] | None],
    accept: Callable[[tuple[float, float]], str | None],
    aim: Callable[[Any], tuple[tuple[float, float] | None, list[str]]],
    match_px: float,
    *,
    order_of: Callable[[Sequence[Any], Mapping[str, float] | None], list[Any]],
    own: Callable[[float, float], bool] | None,
    trail: CellTrail,
    project: Project | None,
    now: float,
    conf: MarkConf,
    log: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    """The mark's pick, with ``bq_next``'s contract (dungeon_hunt): "empty" (no queue: nothing
    detected, nothing hovered), "refind_fail" (``why``: each entry's reason), "pick" (``point``:
    strike there). Down the queue in the runner's order: an entry older than ``ttl_s`` is passed
    ("old"); its predicted foot (predict_foot) is matched in the fresh detection (``detect``:
    None = none came, then only predicted feet are tried); with no box there, the predicted foot
    itself while ``hover_max`` lasts ("gone" after); the runner's ``accept`` then its ``aim``
    (a SWORD) decide, ``aim_max`` aims a pick at most. ``log`` gets one record of the mark's own
    per pick decision (how each entry went)."""
    if not queue:
        return {"what": "empty", "n": 0, "entry": None, "why": []}
    order = order_of(queue, values)
    rec: dict[str, Any] = {"n": len(order), "entry": order[0], "why": []}
    got = detect()
    boxes: Sequence[Any] = [] if got is None else got
    here_now = trail.latest()
    why: list[str] = [] if got is not None else ["no_detection"]
    tried: list[dict[str, Any]] = []
    hovers = aims = 0
    out: dict[str, Any] | None = None
    last_aimed: dict[str, Any] = {}
    for rank, e in enumerate(order):
        age = now - float(e.t)
        if age > conf.ttl_s:
            why.append("old")
            tried.append({"rank": rank, "how": "old", "age_s": round(age, 2)})
            continue
        here_then = trail.at(float(e.t))
        pred, moved = predict_foot(e.foot, e.rel, here_then, here_now, project)
        hit = refind_at(pred, boxes, match_px, own)
        if hit is not None:
            d, b = hit
            how = "box"
        elif hovers < conf.hover_max and aims < conf.aim_max:
            b, d, how = synth_box(pred, e.species), 0.0, "predicted"
        else:
            why.append("gone")
            tried.append({"rank": rank, "how": "gone", "moved": moved})
            continue
        refused = accept(foot_of(b))
        if refused is not None:
            why.append(refused)
            tried.append({"rank": rank, "how": how, "refused": refused, "moved": moved})
            continue
        if aims >= conf.aim_max:
            why.append("aim_max")
            break
        aims += 1
        if how == "predicted":
            hovers += 1
        point, verdicts = aim(b)
        moved_px = math.hypot(foot_of(b)[0] - float(e.foot[0]), foot_of(b)[1] - float(e.foot[1]))
        last_aimed = {"entry": e, "box": b, "rank": rank, "moved_px": moved_px,
                      "verdicts": verdicts}  # fmt: skip
        tried.append({"rank": rank, "how": how, "moved": moved, "d_px": round(d, 1),
                      "verdicts": verdicts})  # fmt: skip
        if point is None:
            why.append("verdict")
            continue
        out = {**rec, **last_aimed, "what": "pick", "point": point, "why": why}
        break
    if out is None:
        out = {**rec, **last_aimed, "what": "refind_fail", "why": why or ["gone"]}
    if log is not None:
        log({"kind": "mark", "what": out["what"], "n": len(order), "tried": tried,
             "detected": got is not None, "boxes": len(boxes)})  # fmt: skip
    return out


def runner_projection(map_name: str) -> Project | None:
    """The runner's own projection for this map (dungeon_hunt.run's ``project``: camera_rdp.json's
    camera, the map's GAT altitudes relative to her cell), as (her cell, rel) -> (u, v). None when
    the map's GAT or the camera cannot be read (the mark then keeps the entry's own pixels)."""
    try:
        import numpy as np

        from poring_dataset import camera as cam
        from poring_dataset import gat as gatmod

        gat = gatmod.parse((cam.GAT_DIR / f"{map_name}.gat").read_bytes())
        cj = json.loads((ROOT / "packages/poring_dataset/src/poring_dataset/camera_rdp.json")
                        .read_text())  # fmt: skip
        camera = cam.camera_from_json(cj["camera"])
    except Exception:  # noqa: BLE001 -- no GAT on this install: the entry's own pixels
        return None

    def project(here: Cell, rel: Cell) -> tuple[float, float]:
        r = np.asarray([rel], dtype=float)
        uv = camera.project(r, gat.relative_altitude(here, r))
        return float(uv[0][0]), float(uv[0][1])

    return project


def conf_of(vals: Mapping[str, Any]) -> MarkConf:
    from poring_flow import settings as st

    d = st.DEFAULTS
    return MarkConf(ttl_s=float(vals.get("mark_ttl_s", d["mark_ttl_s"])),
                    hover_max=int(vals.get("mark_hover_max", d["mark_hover_max"])))  # fmt: skip


def mark_on(vals: Mapping[str, Any]) -> bool:
    """The player's ``mark`` is on and the runner's ``queue`` (the mark's body) too."""
    return bool(vals.get("mark")) and bool(vals.get("queue"))


@contextlib.contextmanager
def marking(dh: Any, vals: Mapping[str, Any], trail: CellTrail, map_name: str | None,
            log: Callable[[dict[str, Any]], None] | None = None,
            clock: Callable[[], float] | None = None) -> Iterator[None]:  # fmt: skip
    """For ONE hunt core: the runner's ``bq_next`` becomes the mark's (mark_next) while the
    player's ``mark`` and the runner's ``queue`` are on; put back after. Off = unchanged."""
    if not mark_on(vals):
        yield
        return
    import time

    conf = conf_of(vals)
    project = runner_projection(map_name) if map_name else None
    saved = dh.bq_next
    tick = clock or time.monotonic

    def bq_next(queue: Sequence[Any], values: Mapping[str, float] | None,
                detect: Callable[[], Sequence[Any] | None],
                accept: Callable[[tuple[float, float]], str | None],
                aim: Callable[[Any], tuple[tuple[float, float] | None, list[str]]],
                match_px: float | None = None) -> dict[str, Any]:  # fmt: skip
        return mark_next(queue, values, detect, accept, aim,
                         float(dh.QUEUE_MATCH_PX if match_px is None else match_px),
                         order_of=dh.bq_order, own=dh.self_box, trail=trail, project=project,
                         now=tick(), conf=conf, log=log)  # fmt: skip

    dh.bq_next = bq_next
    if log is not None:
        log({"kind": "mark", "what": "on", "version": MARK_VERSION, "ttl_s": conf.ttl_s,
             "hover_max": conf.hover_max, "projection": project is not None})  # fmt: skip
    try:
        yield
    finally:
        dh.bq_next = saved
