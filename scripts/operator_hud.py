"""The operator HUD's sender (Batt, 2026-10-08; docs/phase4-ui.md "The operator HUD").

A walk rule calls it with what it saw and decided -- the detector's boxes, each unit's cell from
the camera model + the client's picking, the unit gate's refusals, the chosen click, a plain-words
log line -- and the console draws it over the stream for the human, on its own canvas, while that
tab's HUD toggle is on.

    hud = HudSender(agent, region=r.game_region(), desktop=r.desktop(), label="walk@12")
    cells = unit_cells(boxes, w.camera, w.gat, w.position)       # the gate's own picking
    hud.note(line_detected(len(boxes)))
    hud.note(line_refused("TALK cell"))
    hud.send(boxes=boxes, cells=cells, det_ms=det.last_ms,
             walk=walk_vector(goal, region, desktop, text=line_walking(goal)))

DISPLAY ONLY (poring_env.protocol.OperatorHud): the backend relays it to viewers, never to the
mux, never into the input log, and the message cannot carry input. It is never a reason to stop:
- every error is swallowed (like route_preview's send);
- every field is clamped to the protocol's bounds here, and the message is validated against the
  protocol before it leaves (when poring_env is importable). A message the backend refused would
  come back as an ErrorReply on the rule's own socket, and ro_agent.Agent stops on an error reply:
  a malformed HUD must never reach the backend.

Distances are in CELLS (Chebyshev, from our cell to the cell under the unit's feet), from our own
camera model and picking, never screen px: the rules reason in cells.
"""

from __future__ import annotations

import contextlib
import functools
import json
import math
import time
from collections import deque
from collections.abc import Callable, Sequence
from typing import Any

MAX_UNITS = 64  # poring_env.protocol.HUD_MAX_UNITS
MAX_LOG = 12  # poring_env.protocol.HUD_MAX_LOG
MAX_EXCLUDE = 16
LINE_CHARS = 96
LABEL_CHARS = 64
CLS_CHARS = 32
MAX_CELL = 4096
MAX_TTL_MS = 60_000
DEFAULT_TTL_MS = 1500
MIN_INTERVAL_S = 0.1  # at most ~10 a second: a viewer's control queue holds 64 messages
NO_CELL = 10**5  # poring_dataset.picking's "nothing picked" magnitude (unit_gate.py)


# --- plain values, clamped to the protocol's bounds ---------------------------------------------


def plain(text: Any, limit: int = LINE_CHARS) -> str:
    """One printable line: control characters become spaces, the length is capped."""
    s = "".join(" " if ord(ch) < 0x20 or ord(ch) == 0x7F else ch for ch in str(text))
    return s[:limit]


def _unit(v: float) -> float:
    """A finite value clamped to [0, 1] (NaN -> 0)."""
    v = float(v)
    return min(max(v, 0.0), 1.0) if math.isfinite(v) else 0.0


def _int(v: Any, lo: int, hi: int) -> int:
    f = float(v)
    return int(min(max(f, lo), hi)) if math.isfinite(f) else lo


def norm_point(
    u: float, v: float, region: Sequence[int], desktop: Sequence[int]
) -> dict[str, float]:
    """A point in game-region px (the detector's and the camera model's frame) -> normalized to
    the desktop."""
    gx, gy = region[0], region[1]
    dw, dh = desktop[0], desktop[1]
    return {"x": _unit((gx + u) / dw), "y": _unit((gy + v) / dh)}


def norm_rect(x0: float, y0: float, x1: float, y1: float, region: Sequence[int],
              desktop: Sequence[int]) -> dict[str, float]:  # fmt: skip
    """A box in game-region px -> desktop-normalized x, y, w, h (clamped to the desktop)."""
    a = norm_point(min(x0, x1), min(y0, y1), region, desktop)
    b = norm_point(max(x0, x1), max(y0, y1), region, desktop)
    return {"x": a["x"], "y": a["y"], "w": _unit(b["x"] - a["x"]), "h": _unit(b["y"] - a["y"])}


def chebyshev(rel: Sequence[int] | None) -> int | None:
    """The distance in CELLS from our cell to a cell offset (dx, dy) from it."""
    if rel is None:
        return None
    return _int(max(abs(int(rel[0])), abs(int(rel[1]))), 0, MAX_CELL)


def fps_from_ms(ms: float | None) -> float | None:
    """The detector's rate from its last inference time (UnitDetector.last_ms)."""
    if ms is None or not math.isfinite(ms) or ms <= 0:
        return None
    return round(min(1000.0 / ms, 1000.0), 2)


# --- what the rule saw --------------------------------------------------------------------------


def _box_fields(b: Any) -> tuple[float, float, float, float, float, str]:
    """unit_detector.Box (x0, y0, x1, y1, score, cls) or a dict with the same keys."""
    get = b.get if isinstance(b, dict) else lambda k: getattr(b, k)
    return (float(get("x0")), float(get("y0")), float(get("x1")), float(get("y1")),
            float(get("score")), str(get("cls")))  # fmt: skip


def unit_cells(boxes: Sequence[Any], camera: Any, gat: Any, belief: Sequence[int],
               pick: Any = None) -> list[tuple[int, int] | None]:  # fmt: skip
    """Each unit's cell offset from ours: the client's pick under its feet (poring_dataset.picking),
    else the nearest flat cell from the camera model -- the unit gate's own rule (unit_gate.py), so
    the HUD shows the cells the gate reasoned with. None when neither works."""
    import numpy as np

    if pick is None:
        from poring_dataset.picking import pick_cells as pick
    out: list[tuple[int, int] | None] = []
    for b in boxes:
        try:
            x0, _, x1, y1, _, _ = _box_fields(b)
            fx, fy = (x0 + x1) / 2, y1
            cell = tuple(int(c) for c in pick(camera, gat, tuple(belief), np.array([[fx, fy]]))[0])
            if abs(cell[0]) > NO_CELL:
                import unit_gate

                cell = unit_gate._nearest_cell(camera, fx, fy)
            out.append((int(cell[0]), int(cell[1])))
        except Exception:  # noqa: BLE001 -- display only: an unknown distance, never a stop
            out.append(None)
    return out


def units(boxes: Sequence[Any], region: Sequence[int], desktop: Sequence[int],
          cells: Sequence[tuple[int, int] | None] | None = None,
          ids: Sequence[int | None] | None = None) -> list[dict[str, Any]]:  # fmt: skip
    """The detector's boxes (game-region px) as HUD units: desktop-normalized box and feet, class,
    confidence, and the distance in cells (from `cells`, our-cell-relative offsets). In the
    detector's order, the first MAX_UNITS (a lock index refers to this order)."""
    out: list[dict[str, Any]] = []
    for i, b in enumerate(boxes[:MAX_UNITS]):
        x0, y0, x1, y1, score, cls = _box_fields(b)
        rel = cells[i] if cells is not None and i < len(cells) else None
        uid = ids[i] if ids is not None and i < len(ids) else None
        out.append({
            "cls": plain(cls, CLS_CHARS) or "unit",
            "conf": _unit(score),
            "box": norm_rect(x0, y0, x1, y1, region, desktop),
            "foot": norm_point((x0 + x1) / 2, y1, region, desktop),
            "dist_cells": chebyshev(rel),
            "id": None if uid is None else _int(uid, 0, 2**31 - 1),
        })  # fmt: skip
    return out


def lock(index: int | None = None, uid: int | None = None,
         remaining_ms: float = 0) -> dict[str, Any] | None:  # fmt: skip
    """The locked target (by unit index in this message, or by track id) and its countdown."""
    idx = None if index is None or not 0 <= int(index) < MAX_UNITS else int(index)
    tid = None if uid is None else _int(uid, 0, 2**31 - 1)
    if idx is None and tid is None:
        return None
    return {"index": idx, "id": tid, "lock_remaining_ms": _int(remaining_ms, 0, MAX_TTL_MS)}


def zone(region: Sequence[int], desktop: Sequence[int],
         windows: Sequence[Sequence[int]] | None = None) -> dict[str, Any]:  # fmt: skip
    """The work zone: the game area, minus the client's UI windows (client px x0, y0, x1, y1;
    route_preview.UI_WINDOWS by default -- the same mask the clicks use, walk@12)."""
    if windows is None:
        from route_preview import UI_WINDOWS as windows
    gw, gh = region[2], region[3]
    return {
        "area": norm_rect(0, 0, gw, gh, region, desktop),
        "exclude": [
            norm_rect(x0, y0, x1, y1, region, desktop)
            for x0, y0, x1, y1 in list(windows)[:MAX_EXCLUDE]
        ],  # fmt: skip
    }


def walk_vector(dest: Sequence[int] | None, region: Sequence[int], desktop: Sequence[int],
                text: str = "", start_px: Sequence[float] | None = None,
                end_px: Sequence[float] | None = None) -> dict[str, Any]:  # fmt: skip
    """The walk vector: the destination cell, a short text and, when on screen, the vector from
    our feet (start_px) to the destination's screen point (end_px), both in game-region px."""
    return {
        "dest": None
        if dest is None
        else {"x": _int(dest[0], 0, MAX_CELL), "y": _int(dest[1], 0, MAX_CELL)},  # fmt: skip
        "text": plain(text),
        "start": None
        if start_px is None
        else norm_point(start_px[0], start_px[1], region, desktop),
        "end": None if end_px is None else norm_point(end_px[0], end_px[1], region, desktop),
    }


# --- plain-words log lines (the rule's decisions) -------------------------------------------------


def line_walking(cell: Sequence[int]) -> str:
    return f"walking to ({int(cell[0])},{int(cell[1])})"


def line_refused(why: str) -> str:
    return plain(f"refused: {why}")


def line_detected(n: int) -> str:
    return f"detected {int(n)} unit" + ("" if int(n) == 1 else "s")


def line_gate(ok: bool, info: dict[str, Any]) -> str:
    """walk@11's unit gate verdict (walk11.unit_check's info) in plain words."""
    if ok:
        return plain(f"click clear of {info.get('units', 0)} unit envelope(s)")
    if info.get("why"):
        return line_refused(str(info["why"]))
    who = info.get("nearest") or "unit"
    return line_refused(f"{who} {info.get('min_px')} px from the click")


# --- the message ---------------------------------------------------------------------------------


def message(
    *,
    t_ns: int,
    units_: Sequence[dict[str, Any]] = (),
    lock_: dict[str, Any] | None = None,
    zone_: dict[str, Any] | None = None,
    walk: dict[str, Any] | None = None,
    log: Sequence[str] = (),
    n_units: int | None = None,
    det_fps: float | None = None,
    label: str = "",
    ttl_ms: int = DEFAULT_TTL_MS,
    frame_id: int = -1,
) -> dict[str, Any]:
    """One OperatorHud message, every field within the protocol's bounds."""
    us = list(units_)[:MAX_UNITS]
    count = len(us) if n_units is None else n_units
    fps = None if det_fps is None or not math.isfinite(det_fps) else min(max(det_fps, 0.0), 1000.0)
    return {
        "type": "operator_hud",
        "t_mono_ns": max(0, int(t_ns)),
        "frame_id": max(-1, int(frame_id)),
        "units": us,
        "lock": lock_,
        "zone": zone_,
        "walk": walk,
        "log": [plain(line) for line in list(log)[-MAX_LOG:]],
        "counters": {"units": _int(count, 0, 512), "det_fps": fps},
        "label": plain(label, LABEL_CHARS),
        "ttl_ms": _int(ttl_ms, 0, MAX_TTL_MS),
    }


def _validator() -> Callable[[str], Any] | None:
    """The protocol's own parser (the backend's), when poring_env is importable here."""
    try:
        from poring_env.protocol import parse_agent_to_backend
    except Exception:  # noqa: BLE001 -- not importable: the clamping alone keeps it in bounds
        return None
    return parse_agent_to_backend


class HudSender:
    """The walk rule's handle on the HUD: a bounded log, a rate limit, and a send that never
    raises. `agent` is anything with `.ws.send(str)` (ro_agent.Agent)."""

    def __init__(
        self,
        agent: Any,
        region: Sequence[int],
        desktop: Sequence[int],
        label: str = "",
        ttl_ms: int = DEFAULT_TTL_MS,
        windows: Sequence[Sequence[int]] | None = None,
        min_interval_s: float = MIN_INTERVAL_S,
        clock: Callable[[], int] = time.monotonic_ns,
        validate: bool = True,
    ) -> None:
        self.agent = agent
        self.region = tuple(int(v) for v in region)
        self.desktop = tuple(int(v) for v in desktop)
        self.label = plain(label, LABEL_CHARS)
        self.ttl_ms = ttl_ms
        self.min_interval_s = min_interval_s
        self.clock = clock
        self.log: deque[str] = deque(maxlen=MAX_LOG)
        self.sent = 0
        self.skipped = 0
        self.refused = 0  # failed the protocol's own validation here: never sent
        self.last_error: str | None = None
        self.log_path: str | None = None
        self._last_ns: int | None = None
        self._validate = _validator() if validate else None
        self.zone: dict[str, Any] | None
        try:
            self.zone = zone(self.region, self.desktop, windows)
        except Exception:  # noqa: BLE001 -- no zone outline, still a HUD
            self.zone = None

    def note(self, line: str) -> None:
        """A plain-words log line; it rides on the next message (and the ones after it)."""
        with contextlib.suppress(Exception):
            self.log.append(plain(line))

    def send(
        self,
        *,
        boxes: Sequence[Any] = (),
        cells: Sequence[tuple[int, int] | None] | None = None,
        ids: Sequence[int | None] | None = None,
        lock_: dict[str, Any] | None = None,
        walk: dict[str, Any] | None = None,
        det_ms: float | None = None,
        det_fps: float | None = None,
        n_units: int | None = None,
        frame_id: int = -1,
        ttl_ms: int | None = None,
        force: bool = False,
    ) -> bool:
        """Build the message from a decision and send it. True when it left; never raises."""
        try:
            now = int(self.clock())
            if (not force and self._last_ns is not None
                    and now - self._last_ns < self.min_interval_s * 1e9):  # fmt: skip
                self.skipped += 1  # its log lines ride on the next one
                return False
            us = units(boxes, self.region, self.desktop, cells, ids)
            msg = message(
                t_ns=now, units_=us, lock_=lock_, zone_=self.zone, walk=walk, log=self.log,
                n_units=len(boxes) if n_units is None else n_units,
                det_fps=det_fps if det_fps is not None else fps_from_ms(det_ms),
                label=self.label, ttl_ms=self.ttl_ms if ttl_ms is None else ttl_ms,
                frame_id=frame_id,
            )  # fmt: skip
            if self.send_message(msg):
                self._last_ns = now
                return True
            return False
        except Exception as exc:  # noqa: BLE001 -- display only: never a reason to stop
            self.last_error = f"{type(exc).__name__}: {exc}"[:200]
            return False

    def clear(self) -> bool:
        """An empty HUD that clears at once (ttl 0): the rule ended."""
        with contextlib.suppress(Exception):
            return self.send_message(message(t_ns=int(self.clock()), label=self.label, ttl_ms=0))
        return False

    def send_message(self, msg: dict[str, Any]) -> bool:
        """Validate (the backend's own parser) and send; a message that fails is never sent."""
        try:
            text = json.dumps(msg, allow_nan=False)
            if self._validate is not None:
                try:
                    self._validate(text)
                except Exception as exc:  # noqa: BLE001 -- the backend would answer with an error
                    self.refused += 1
                    self.last_error = f"invalid: {exc}"[:200]
                    return False
            self.agent.ws.send(text)
            self.sent += 1
            if self.log_path:  # route_demo's render redraws the HUD from these (display only)
                with contextlib.suppress(Exception), open(self.log_path, "a") as fh:
                    fh.write(text + "\n")
            return True
        except Exception as exc:  # noqa: BLE001 -- display only: never a reason to stop
            self.last_error = f"{type(exc).__name__}: {exc}"[:200]
            return False


# --- the rule side (Batt 2026-10-08: the walk / rec / idle harnesses publish; display only) -----
# A run calls `enable` once; walk rules wrap their own functions with the hooks below. The GATE hook
# only RECORDS its verdict (microseconds): the click-instant gate's envelope assumes the click
# follows at once, so nothing is built, picked or sent between the gate and the click. Everything is
# published by the click-step hook AFTER the step returned (the click is done). The HUD has its own
# agent connection ("operator-hud"): an error reply can never stop the rule.
_HUD: HudSender | None = None
_OWNER: object | None = None
_OWN_AGENT: Any = None
_PENDING: list[dict[str, Any]] = []
_LAST: dict[str, Any] = {}


def enable(label: str, *, log_path: str | None = None, agent: Any = None) -> object | None:
    """Start publishing (own agent unless given). None when already enabled (an outer caller,
    e.g. route_demo with its log, keeps ownership) or when the HUD could not start (display only:
    the run goes on without it)."""
    global _HUD, _OWNER, _OWN_AGENT
    if _HUD is not None:
        return None
    try:
        import ro_agent as r

        ag = agent if agent is not None else r.Agent("operator-hud")
        hud = HudSender(ag, r.game_region(), r.desktop(), label=label)
    except Exception:  # noqa: BLE001 -- display only
        return None
    hud.log_path = log_path
    _HUD, _OWNER, _OWN_AGENT = hud, object(), (None if agent is not None else ag)
    _PENDING.clear()
    _LAST.clear()
    return _OWNER


def disable(token: object | None) -> None:
    global _HUD, _OWNER, _OWN_AGENT
    if token is None or token is not _OWNER or _HUD is None:
        return
    with contextlib.suppress(Exception):
        _HUD.clear()
    with contextlib.suppress(Exception):
        if _OWN_AGENT is not None:
            _OWN_AGENT.ws.close()
    _HUD, _OWNER, _OWN_AGENT = None, None, None


def sender() -> HudSender | None:
    return _HUD


def note(line: str) -> None:
    if _HUD is not None:
        _HUD.note(line)


def publish(*, walk: dict[str, Any] | None = None, force: bool = True) -> None:
    """Send the latest detector boxes (with their cells), the pending log lines and `walk`."""
    if _HUD is None:
        return
    with contextlib.suppress(Exception):
        boxes, w = _LAST.get("boxes") or [], _LAST.get("w")
        cells = unit_cells(boxes, w.camera, w.gat, tuple(w.position)) if w is not None else None
        _HUD.send(boxes=boxes, cells=cells, det_ms=_LAST.get("det_ms"), walk=walk, force=force)


def _watch(det: Any) -> None:
    """Remember the detector's last boxes: its `detect` is wrapped on the INSTANCE, returning
    exactly what it returned (display only)."""
    if det is None or getattr(det, "_hud_watched", False):
        return
    orig = det.detect

    def detect(frame: Any) -> Any:
        boxes = orig(frame)
        _LAST["boxes"], _LAST["det_ms"] = boxes, getattr(det, "last_ms", None)
        return boxes

    det.detect, det._hud_watched = detect, True


def hook_unit_check(fn: Callable[..., Any], units_: dict[str, Any]) -> Callable[..., Any]:
    """Around the click-instant unit gate unit_check(pr, w, u, v) -> (ok, info): RECORD only."""

    @functools.wraps(fn)
    def check(pr: Any, w: Any, u: float, v: float) -> Any:
        if _HUD is not None:
            _watch(units_.get("detector"))
        res = fn(pr, w, u, v)
        if _HUD is not None:
            _PENDING.append({"ok": res[0], "info": res[1], "u": u, "v": v})
            _LAST["w"] = w
        return res

    return check


def _outcome_line(res: dict[str, Any]) -> str:
    out = str(res.get("outcome") or "")
    if res.get("clicked"):
        return plain(f"clicked: {out or 'walk'}")
    extra = []
    if res.get("ui_refused"):
        extra.append(f"{len(res['ui_refused'])} px in UI windows")
    if res.get("talk_refused"):
        extra.append(f"{len(res['talk_refused'])} px on a TALK cell")
    return line_refused(out + (f" ({', '.join(extra)})" if extra else ""))


def hook_click_step(fn: Callable[..., dict[str, Any]]) -> Callable[..., dict[str, Any]]:
    """Around click_step(pr, w, end, ...): AFTER it returned, the gate verdicts it recorded, its
    outcome and the walk vector to `end` go out (the decision and the click are done)."""

    @functools.wraps(fn)
    def step(pr: Any, w: Any, end: tuple[int, int], *a: Any, **k: Any) -> dict[str, Any]:
        if _HUD is None:
            return fn(pr, w, end, *a, **k)
        _PENDING.clear()
        res = fn(pr, w, end, *a, **k)
        with contextlib.suppress(Exception):
            for g in _PENDING[-3:]:
                _HUD.note(line_gate(bool(g["ok"]), g["info"]))
            _HUD.note(_outcome_line(res))
            at = res.get("at") or ((_PENDING[-1]["u"], _PENDING[-1]["v"]) if _PENDING else None)
            _LAST["w"] = w
            publish(walk=walk_vector(end, _HUD.region, _HUD.desktop, text=line_walking(end),
                                     end_px=at))  # fmt: skip
        _PENDING.clear()
        return res

    return step


def hook_route(fn: Callable[..., dict[str, Any]]) -> Callable[..., dict[str, Any]]:
    """Around walk_route(pr, w, goal, ...): a start line and the route's outcome."""

    @functools.wraps(fn)
    def route(pr: Any, w: Any, goal: tuple[int, int], *a: Any, **k: Any) -> dict[str, Any]:
        if _HUD is not None:
            with contextlib.suppress(Exception):
                _HUD.note(
                    plain(f"route: ({w.position[0]},{w.position[1]}) -> ({goal[0]},{goal[1]})")
                )
                # no boxes here: no picking work before the route's first decision
                _HUD.send(walk=walk_vector(goal, _HUD.region, _HUD.desktop,
                                           text=line_walking(goal)), force=True)  # fmt: skip
        did = fn(pr, w, goal, *a, **k)
        if _HUD is not None:
            with contextlib.suppress(Exception):
                why = did.get("decline") or ("arrived" if did.get("arrived_belief") else "ended")
                _HUD.note(plain(f"route ended: {why}"))
                publish()
        return did

    return route
