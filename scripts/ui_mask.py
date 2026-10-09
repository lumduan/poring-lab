#!/usr/bin/env python3
"""THE DYNAMIC UI MASK (Batt 2026-10-09 ~16:10): the client's always-on windows, plus the NPC
dialog's CUT-IN illustration while a dialog is open.

Batt, verbatim (his 16:04 screenshot, prontera, the city guide's dialog): "The NPC dialog's large
CUT-IN illustration (the character art at the lower right) is boxed as 'monster 31%'. It's client
UI, shown only while a dialog is open, at a fixed place: when the dialog reader sees an open
dialog, mask the cut-in area as UI (screen-anchored) for the detector, the HUD and the walk gate;
add cut-in frames as hard negatives in the next labels."

What a cut-in is: an NPC script shows an image with a screen position (bottom left, bottom middle,
bottom right, or a movable window in the middle). The client draws it at the image's own size,
anchored to the screen there, over the scene, until the script removes it. Its packet,
ZC_SHOW_IMAGE2 (0x01B3), is NOT decoded by poring_packets (2026-10-09; no decoder is added here):
the offline truth below is the packets' dialog state instead (talk_calibrate.dialog_timeline).

THE MASK (``UiMask``):
- STATIC: route_preview.UI_WINDOWS (work_zone.WINDOW_NAMES), always -- today's mask, unchanged.
- CUT-IN regions (``CUTIN_REGIONS``) while the dialog reader (poring_env.npc_dialog.state, talk@1
  T2: 168 / 168 on held-out frames) reports an open dialog or menu on an ``ok`` state, and FAIL
  CLOSED: also when the state is unreadable (not ``ok``, no templates, the reader failed). Only a
  certain "no dialog and no menu" leaves them unmasked.
- For CLICK POINTS (the walk gate, loot): ``window_at`` / ``in_work_zone``, every region grown by
  the margin, as work_zone.
- For DETECTIONS (the HUD, the walk gate's units): ``split`` drops a box that lies at least
  INSIDE_SHARE inside a masked CUT-IN region. Boxes over the static windows are not touched (as
  before). Fail closed means MASK for exclusion and for the display; a SAFETY gate's unit memory
  should drop boxes only on a positive read (``dialog_seen``): there an unreadable state keeps
  the box, the conservative direction for an envelope.

MEASURED (2026-10-09, banked RDP talk-cal sessions, 1280x720 client area; packet truth for the
dialog state; `ui_mask.py measure` / `check` repeat it):
- the prontera guide's cut-in (CUTIN_GUIDE) is pixel-identical in two sessions, at the same place,
  on every dialog-open frame (54 + 54; and on the 12 of the 16:03 session, checked), and gone on
  every closed one (6 + 6);
- the v0-PNG detector boxes it as "monster" 0.305-0.316 at (984, 599)-(1033, 644) -- the hand on
  the spear -- on 120 / 120 open frames, and draws nothing there on the 12 closed ones;
- Garnet and Henson (prt_church) show NO cut-in (102 open frames each, three sessions: at most 784
  px differ steadily from their closed frames, all at the NPC's feet: its selection marker);
- read_mask's dialog state agrees with the packets on 456 / 456 frames of those six sessions.
NOT MEASURED (no frames show them): any other NPC's cut-in, and every other anchor (bottom left,
bottom middle, the middle window). They are NOT masked: a phantom there stays a known gap. A cut-in
a script leaves on screen after its dialog closes is not masked either (the reader then says "no
dialog"). Both are stated gaps (docs/planning/labels-v2.md section 2a), not hidden.

    ui_mask.py measure SESSION [SESSION ...]   the cut-in's extent from a talk-cal session's frames
    ui_mask.py check SESSION [SESSION ...]     on every frame: the reader, the mask, the detector's
                                               boxes over the cut-in (CPU detector, offline)

Pixels in only: the mask is decided from frames; packets are offline truth (ADR-0007).
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, TypeVar

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import route_preview  # noqa: E402
import work_zone as wz  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
Rect = tuple[float, float, float, float]  # x0, y0, x1, y1 client px
T = TypeVar("T")

GAME_W, GAME_H = wz.GAME_W, wz.GAME_H
STATIC_WINDOWS: tuple[tuple[str, Rect], ...] = tuple(
    (name, (float(x0), float(y0), float(x1), float(y1)))
    for name, (x0, y0, x1, y1) in zip(wz.WINDOW_NAMES, route_preview.UI_WINDOWS, strict=True)
)

# The prontera city guide's cut-in (Guide#prt::PrtGuide, the bottom-right anchor): the extent of
# its OPAQUE pixels, x0, y0, x1, y1 (client px; x1 / y1 exclusive). Measured 2026-10-09 on the
# banked talk-cal sessions 20261009T153815 and T154802 (RDP): the pixels that differ from the same
# view with the dialog closed (packets: after npc_close_click) and stay constant over every open
# frame; thresholds 8 / 16 / 24 / 40 grey levels give the same box. It reaches the screen's bottom
# edge; the 97 px between its art and the right edge are the image's transparent margin or the
# client's placement (the frames cannot tell which).
CUTIN_GUIDE: Rect = (957.0, 249.0, 1183.0, 720.0)
# The CONSERVATIVE region for ANY bottom-right cut-in: the guide's extent from the corner (323 x 471
# px) grown by CUTIN_BR_GROW. A MARGIN, NOT A MEASUREMENT: no other NPC's cut-in has been seen.
CUTIN_BR_GROW = 1.25
CUTIN_BOTTOM_RIGHT: Rect = (
    float(GAME_W - round(CUTIN_BR_GROW * (GAME_W - CUTIN_GUIDE[0]))),
    float(GAME_H - round(CUTIN_BR_GROW * (GAME_H - CUTIN_GUIDE[1]))),
    float(GAME_W),
    float(GAME_H),
)  # = (876, 131, 1280, 720)
# What is masked while a dialog is open (or its state is unreadable). Other anchors: not measured.
CUTIN_REGIONS: tuple[tuple[str, Rect], ...] = (("cutin_bottom_right", CUTIN_BOTTOM_RIGHT),)
# A detection is UI when at least this share of its box lies inside a masked cut-in region (the
# guide's phantom: 1.0). A unit only partly behind the region's edge is kept.
INSIDE_SHARE = 0.5
# CutinWatch: a dialog read is reused while the cut-in region looks the same as at that read --
# fewer than REGION_CHANGE of its 1/REGION_DOWN pixels moved by more than PIXEL_CHANGE grey levels
# -- and it is at most MAX_AGE_S old. The guide's cut-in appearing changes ~30 % of the region
# (72,000 of its 238,000 px); a cut-in of ~98 x 98 px or more crosses 4 %; a walking monster
# (~42 x 40 px, old and new place) changes ~1.4 %. A smaller cut-in waits for MAX_AGE_S.
REGION_DOWN = 8
PIXEL_CHANGE = 24
REGION_CHANGE = 0.04
MAX_AGE_S = 3.0
TEMPLATES = ROOT / "data" / "ui_anchors" / "npc_dialog"  # = poring_env.npc_dialog.TEMPLATE_DIR


def inside_share(box: Sequence[float], rect: Sequence[float]) -> float:
    """The share of ``box``'s area inside ``rect`` (0 for an empty box)."""
    x0, y0, x1, y1 = (float(c) for c in box[:4])
    area = max(0.0, x1 - x0) * max(0.0, y1 - y0)
    if area <= 0:
        return 0.0
    iw = max(0.0, min(x1, rect[2]) - max(x0, rect[0]))
    ih = max(0.0, min(y1, rect[3]) - max(y0, rect[1]))
    return iw * ih / area


assert CUTIN_BOTTOM_RIGHT == (876.0, 131.0, 1280.0, 720.0)
assert inside_share(CUTIN_GUIDE, CUTIN_BOTTOM_RIGHT) == 1.0  # the measured box lies inside it


def touches(box: Sequence[float], rect: Sequence[float], margin: float = 0.0) -> bool:
    """``box`` overlaps ``rect`` grown by ``margin`` (edges count)."""
    return not (box[2] < rect[0] - margin or box[0] > rect[2] + margin
                or box[3] < rect[1] - margin or box[1] > rect[3] + margin)  # fmt: skip


def _box_of(item: Any) -> Sequence[float]:
    """A detector Box (x0..y1 attributes), a {"box": [...]} dict (hud_scene), or a sequence."""
    if isinstance(item, dict):
        return [float(c) for c in item["box"]]
    if hasattr(item, "x0"):
        return (item.x0, item.y0, item.x1, item.y1)
    return [float(c) for c in item[:4]]


@dataclass(frozen=True)
class UiMask:
    """The UI regions on one frame (client px). ``cutin``: the cut-in regions are masked; ``why``:
    dialog_open | no_dialog | unreadable:<reason> | static (no dialog read: today's mask) |
    not_read (CutinWatch.lazy: nothing a read could change; valid for those boxes only)."""

    cutin: bool
    why: str
    windows: tuple[tuple[str, Rect], ...] = STATIC_WINDOWS
    state: dict[str, Any] | None = field(default=None, compare=False)  # the reader's summary

    @property
    def cutin_regions(self) -> tuple[tuple[str, Rect], ...]:
        return CUTIN_REGIONS if self.cutin else ()

    @property
    def dialog_seen(self) -> bool:
        """The reader SAW an open dialog or menu (masked by a positive read, not by fail-closed)."""
        return self.why == "dialog_open"

    def regions(self) -> tuple[tuple[str, Rect], ...]:
        return self.windows + self.cutin_regions

    def window_at(self, u: float, v: float, margin: float = 0.0) -> str | None:
        """The region whose rectangle, grown by ``margin``, holds client pixel (u, v); None if
        none. The grown edge counts as inside (as work_zone.ui_window_at)."""
        for name, (x0, y0, x1, y1) in self.regions():
            if x0 - margin <= u <= x1 + margin and y0 - margin <= v <= y1 + margin:
                return name
        return None

    def in_work_zone(self, u: float, v: float, margin: float = wz.MARGIN_PX) -> bool:
        """work_zone.in_work_zone with this mask's regions: inside the game area and outside every
        region grown by ``margin``."""
        if not (0 <= u < GAME_W and 0 <= v < GAME_H):
            return False
        return self.window_at(u, v, margin) is None

    def masking(self, box: Sequence[float]) -> str | None:
        """The masked cut-in region holding >= INSIDE_SHARE of ``box``; None if none."""
        for name, rect in self.cutin_regions:
            if inside_share(box, rect) >= INSIDE_SHARE:
                return name
        return None

    def split(self, items: Iterable[T], box_of: Callable[[Any], Sequence[float]] = _box_of
              ) -> tuple[list[T], list[T]]:  # fmt: skip
        """(kept, masked): detections inside a masked cut-in region are UI, not units."""
        kept: list[T] = []
        masked: list[T] = []
        for it in items:
            (masked if self.masking(box_of(it)) else kept).append(it)
        return kept, masked

    def summary(self) -> dict[str, Any]:
        regions = [list(r) for _, r in self.cutin_regions]
        out: dict[str, Any] = {"cutin": self.cutin, "why": self.why, "cutin_regions": regions}
        if self.state is not None:
            out["dialog_state"] = self.state
        return out


# Today's mask (no dialog read): the static windows only. For callers without a frame; NOT the
# dynamic mask -- a caller that can read a frame should use read_mask / CutinWatch.
STATIC = UiMask(cutin=False, why="static")


def from_state(state: Any) -> UiMask:
    """The mask for a dialog reader's state (poring_env.npc_dialog.NpcUiState). FAIL CLOSED: None
    or a state that is not ``ok`` masks the cut-in; only a certain no-dialog-no-menu does not."""
    if state is None:
        return UiMask(cutin=True, why="unreadable:no_state")
    summ = state.summary() if hasattr(state, "summary") else None
    if not state.ok:
        return UiMask(cutin=True, why=f"unreadable:{state.reason}", state=summ)
    if state.dialog is not None or state.menu is not None:
        return UiMask(cutin=True, why="dialog_open", state=summ)
    return UiMask(cutin=False, why="no_dialog", state=summ)


_templates: dict[str, Any] = {}


def load_dialog_templates(path: Path | None = None) -> Any:
    """talk@1's T2 templates (default TEMPLATES; cached per path); None when they cannot be loaded
    (then the mask fails closed)."""
    path = TEMPLATES if path is None else path
    key = str(path)
    if key not in _templates:
        from poring_env import npc_dialog as nd

        try:
            _templates[key] = nd.load_templates(path)
        except Exception as exc:  # noqa: BLE001 -- missing / other format: the mask fails closed
            print(f"{time.strftime('%H:%M:%S')} ui_mask: no dialog templates at {path} "
                  f"({type(exc).__name__}): the cut-in is masked whenever asked",
                  flush=True)  # fmt: skip
            _templates[key] = None
    return _templates[key]


Reader = Callable[[Any, Any, Any], Any]


def _nd_state(frame: Any, templates: Any, hints: Any) -> Any:
    from poring_env import npc_dialog as nd

    return nd.state(frame, templates, hints)


def read_mask(frame: Any, templates: Any = None, hints: Any = None,
              reader: Reader | None = None) -> tuple[UiMask, Any]:  # fmt: skip
    """THE PATCH POINT for a gate: the dialog reader on ``frame`` (the 1280x720 client area, BGR or
    BGRA), then ``from_state``. (mask, state); state None when nothing could be read. Templates
    missing, or the reader failing, mask the cut-in (fail closed)."""
    t = templates if templates is not None else load_dialog_templates()
    if t is None:
        return UiMask(cutin=True, why="unreadable:no_templates"), None
    try:
        st = (reader or _nd_state)(frame, t, hints)
    except Exception as exc:  # noqa: BLE001 -- an unreadable state masks the cut-in
        return UiMask(cutin=True, why=f"unreadable:{type(exc).__name__}"), None
    return from_state(st), st


def region_signature(frame: Any, rect: Rect = CUTIN_BOTTOM_RIGHT,
                     down: int = REGION_DOWN) -> np.ndarray:  # fmt: skip
    """The cut-in region's 1/down grey pixels (mean of B, G, R)."""
    x0, y0, x1, y1 = (int(c) for c in rect)
    return np.asarray(frame[y0:y1:down, x0:x1:down, :3].astype(np.float32).mean(-1))


class CutinWatch:
    """The dynamic mask for a STREAM of frames (the HUD; a gate deciding often), cheaply:
    - the dialog is read ONLY when its answer can change something (``needed``): a detection or a
      drawn box the cut-in region would mask (>= INSIDE_SHARE inside it), or a click point inside
      it grown by the gate's margin; otherwise no read at all (``lazy``, ``filter``);
    - a read is REUSED while the cut-in region looks the same as at that read (REGION_CHANGE) and
      it is at most MAX_AGE_S old: a cut-in cannot appear or go without changing that region;
    - the windows' last places are the reader's hints (a present window is found in ~36 ms
      instead of a ~170 ms search).
    Fail closed as read_mask. ``stats``: reads / reused / skipped and each read's ms."""

    def __init__(self, templates: Any = None, reader: Reader | None = None,
                 max_age_s: float = MAX_AGE_S, change: float = REGION_CHANGE,
                 clock: Callable[[], float] = time.monotonic) -> None:  # fmt: skip
        self._templates = templates
        self.reader = reader
        self.max_age_s, self.change, self.clock = max_age_s, change, clock
        self.last: tuple[float, np.ndarray, UiMask] | None = None
        self.hints: dict[str, tuple[int, int]] = {}
        self.stats: dict[str, Any] = {"reads": 0, "reused": 0, "skipped": 0, "read_ms": []}

    def templates(self) -> Any:
        if self._templates is None:
            self._templates = load_dialog_templates()
        return self._templates

    @staticmethod
    def needed(boxes: Iterable[Sequence[float]] = (), points: Iterable[Sequence[float]] = (),
               margin: float = 0.0) -> bool:  # fmt: skip
        """A read can change an answer: a box the cut-in region would mask, or a point inside the
        region grown by ``margin``."""
        boxes, points = list(boxes), list(points)
        for _, (x0, y0, x1, y1) in CUTIN_REGIONS:
            if any(inside_share(b, (x0, y0, x1, y1)) >= INSIDE_SHARE for b in boxes):
                return True
            if any(x0 - margin <= u <= x1 + margin and y0 - margin <= v <= y1 + margin
                   for u, v in points):  # fmt: skip
                return True
        return False

    def changed(self, a: np.ndarray, b: np.ndarray) -> bool:
        """The cut-in region's look changed between two signatures (REGION_CHANGE)."""
        return float((np.abs(a - b) > PIXEL_CHANGE).mean()) > self.change

    def mask(self, frame: Any) -> UiMask:
        """The mask on this frame (a reused read, or a new one)."""
        sig = region_signature(frame)
        now = self.clock()
        if self.last is not None:
            t, s, m = self.last
            if now - t <= self.max_age_s and not self.changed(s, sig):
                self.stats["reused"] += 1
                return m
        t0 = time.perf_counter()
        m, st = read_mask(frame, self.templates(), self.hints or None, self.reader)
        self.stats["read_ms"].append(1000 * (time.perf_counter() - t0))
        self.stats["reads"] += 1
        if st is not None and getattr(st, "ok", False):
            self.hints = {}
            if st.dialog is not None:
                self.hints["npc_dialog"] = tuple(st.dialog.rect[:2])
            if st.menu is not None:
                self.hints["npc_menu"] = tuple(st.menu.rect[:2])
        self.last = (now, sig, m)
        return m

    def lazy(self, frame: Any, boxes: Iterable[Sequence[float]] = (),
             points: Iterable[Sequence[float]] = (), margin: float = 0.0) -> UiMask:  # fmt: skip
        """The mask, read only when ``needed`` for these boxes / points; else
        UiMask(cutin=False, why="not_read"), valid for THOSE boxes and points only."""
        if not self.needed(boxes, points, margin):
            self.stats["skipped"] += 1
            return UiMask(cutin=False, why="not_read")
        return self.mask(frame)

    def filter(self, frame: Any, items: Sequence[T], box_of: Callable[[Any], Sequence[float]]
               = _box_of, also: Iterable[Sequence[float]] = ()
               ) -> tuple[list[T], list[T], UiMask]:  # fmt: skip
        """(kept, masked, mask) for detections on ``frame``; ``also``: other boxes that make a read
        needed (the HUD's drawn objects)."""
        m = self.lazy(frame, [*(box_of(i) for i in items), *also])
        kept, masked = m.split(items, box_of)
        return kept, masked, m

    def report(self) -> str:
        ms = sorted(self.stats["read_ms"]) or [0.0]
        return (f"cut-in mask: {self.stats['reads']} reads (median {ms[len(ms) // 2]:.0f} ms), "
                f"{self.stats['reused']} reused, {self.stats['skipped']} not needed")  # fmt: skip


# --- offline (banked talk-cal sessions; nothing here is committed) ------------------------------


def _session(name: str) -> Path:
    p = Path(name)
    return p if p.is_dir() else Path("/dev/shm/poring-lab-demo") / name


def _labelled_frames(session: Path) -> list[tuple[int, Path, Any]]:
    """(t, path, packet label or None) per frame: talk_calibrate's packet truth, no settle."""
    import talk_calibrate as tc

    tl = tc.dialog_timeline(tc.read_events(session))
    return [(t, p, tc.label_at(tl, t, 0)) for t, p in tc.frames_of(session)]


def measure(sessions: Sequence[str], thresholds: Sequence[int] = (8, 16, 24, 40),
            stable_px: int = 12, x_min: int = 640) -> dict[str, Any]:  # fmt: skip
    """The cut-in's extent per session: pixels right of ``x_min`` that differ from the closed
    frames' median by > threshold and stay within ``stable_px`` of the open frames' median on 90 %
    of them; the widest run of such columns is the art (the parked cursor is another run)."""
    import talk_calibrate as tc

    out: dict[str, Any] = {}
    for name in sessions:
        rows = _labelled_frames(_session(name))
        closed = [p for _, p, lab in rows if lab is not None and not (lab.dialog or lab.menu)]
        opened = [p for _, p, lab in rows if lab is not None and (lab.dialog or lab.menu)]
        res: dict[str, Any] = {"open": len(opened), "closed": len(closed)}
        out[name] = res
        if not closed or not opened:
            res["extent"] = None
            continue
        bg = np.median(np.stack([tc.load_frame(p).astype(np.int16) for p in closed]), axis=0)
        st = np.stack([tc.load_frame(p).astype(np.int16) for p in opened])
        med = np.median(st, axis=0)
        stable = (np.abs(st - med).max(-1) <= stable_px).mean(0) >= 0.9
        for thr in thresholds:
            m = (np.abs(med - bg).max(-1) > thr) & stable
            m[:, :x_min] = False
            cols = np.flatnonzero(m.any(0))
            if cols.size == 0:
                res[f"extent@{thr}"] = None
                continue
            # the widest run of columns: the art (the parked cursor is a separate, narrow run)
            runs = np.split(cols, np.flatnonzero(np.diff(cols) > 1) + 1)
            run = max(runs, key=len)
            ys = np.flatnonzero(m[:, run[0] : run[-1] + 1].any(1))
            res[f"extent@{thr}"] = [int(run[0]), int(ys[0]), int(run[-1]) + 1, int(ys[-1]) + 1]
            res[f"pixels@{thr}"] = int(m[:, run[0] : run[-1] + 1].sum())
    return out


def check(sessions: Sequence[str], detector: bool = True, threads: int = 2) -> dict[str, Any]:
    """Per frame: the packets' dialog state against the mask's (read_mask), and, with the CPU
    detector, every unit box touching the cut-in region: whether it lies on the guide's art
    (CUTIN_GUIDE) and whether the mask drops it -- by the frame's packet state. Plus CutinWatch
    over the frames in order (its reads, reuses and ms), as the HUD would meet them."""
    import talk_calibrate as tc

    det: Any = None
    if detector:
        import unit_detector

        try:
            det = unit_detector.UnitDetector(threads=threads)
        except unit_detector.DetectorUnavailable as exc:
            print(f"detector unavailable ({exc}): reader and mask only", flush=True)
    out: dict[str, Any] = {"frames": 0, "agree": 0, "disagree": [], "sessions": {}}
    try:
        for name in sessions:
            watch = CutinWatch()
            ses: dict[str, Any] = {"open": 0, "closed": 0, "boxes": {}, "examples": []}
            for _, p, lab in _labelled_frames(_session(name)):
                frame = tc.load_frame(p)
                m, _ = read_mask(frame)
                out["frames"] += 1
                state = "open" if lab is not None and (lab.dialog or lab.menu) else "closed"
                ses[state] += 1
                if m.why == ("dialog_open" if state == "open" else "no_dialog"):
                    out["agree"] += 1
                else:
                    out["disagree"].append([name, p.name, m.why, state])
                if det is None:
                    continue
                units = [b for b in det.detect(frame) if b.cls != "player"]
                watch.filter(frame, units)
                for b in units:
                    box = _box_of(b)
                    if not touches(box, CUTIN_BOTTOM_RIGHT):
                        continue
                    where = "on_guide_art" if inside_share(box, CUTIN_GUIDE) >= INSIDE_SHARE \
                        else "elsewhere_in_region"  # fmt: skip
                    fate = "masked" if m.masking(box) else "kept"
                    key = f"{state}/{where}/{b.cls}/{fate}"
                    ses["boxes"][key] = ses["boxes"].get(key, 0) + 1
                    if len(ses["examples"]) < 6 and key not in [e[0] for e in ses["examples"]]:
                        ses["examples"].append([key, p.name[:4], round(b.score, 3),
                                                [round(c) for c in box]])  # fmt: skip
            ses["watch"] = watch.report()
            out["sessions"][name] = ses
    finally:
        if det is not None:
            det.close()
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    m = sub.add_parser("measure")
    m.add_argument("sessions", nargs="+")
    c = sub.add_parser("check")
    c.add_argument("sessions", nargs="+")
    c.add_argument("--no-detector", action="store_true")
    a = ap.parse_args()
    if a.cmd == "measure":
        res = measure(a.sessions)
    else:
        res = check(a.sessions, detector=not a.no_detector)
    print(json.dumps(res, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
