#!/usr/bin/env python3
"""Calibrate the minimap readout reader (Phase 3 T0): digit glyphs cut from recorded H.264 sessions,
labelled by packet truth (offline ground truth, ADR-0007 -- it labels, it never feeds the reader).

    selfpos_calibrate.py [SESSION ...] [--per-session 4000] [--per-position 40] [--offset-ms auto]
                         [--guard-ms 300] [--load-ms 3000] [--mapcache DIR] [--cache DIR]
                         [--out data/ui_anchors/minimap_digits.npz] [--report OUT.json]

* Sessions: names under /mnt/poring-lab-datasets (or paths). Default: the TRAINING subset
  outdoor-a, outdoor-b and indoor-b. outdoor-c, outdoor-d and indoor-c are held out for
  scripts/selfpos_eval.py and are refused here.
* Truth, per frame (SessionTruth, shared with the evaluation): the packet timeline at (frame time
  - the backend's packet->frame offset, the same 'auto' rule as qa_export.py: ~114 ms for the S2
  console). STANDING when no walk of our own runs within --guard-ms of that time, WALKING
  otherwise. Left out: GM-command windows (qa_export's 2 s), --load-ms after a map change (the
  loading screen), frames without a position.
  Our own AID: the recordings start at the last map change, so login_accepted (which carries it)
  is not in them and the Timeline ignored our own entity_stop (a walk cut short: the readout said
  168 372, the Timeline 168 371). It is inferred -- the one player-range block id (rAthena:
  accounts from 2000000, NPCs/mobs from 110000000) that stops but never appears to us -- and
  given to the Timeline as a login_accepted at the session's first event.
* Which maps show the readout: the minimap window found by its zoom buttons (seeded by the
  magnifier icon); per map the share of frames that show it. The client draws no minimap on
  indoor maps (prt_church). The window's template and stable mask go to
  data/ui_anchors/minimap{,_mask}.npy (ADR-0011 locate()).
* Glyphs: standing frames of readout maps, at most --per-position frames per session x cell (one
  long stand must not outvote every other scene). The label "x y" places every digit on the
  measured cell grid (poring_vision.selfpos.Layout: the first cell at x=1158, 7 px a digit, 8 px
  between the numbers, rows 147-157); poring_vision.selfpos.fit_templates turns them into
  templates and thresholds by fixed rules (its docstring), from these TRAINING frames only.
* In-sample check: the reader over every training frame (a sanity check, not the evaluation).

Writes data/ui_anchors/minimap_digits.npz and the window template: client-derived pixels,
gitignored, NEVER committed. Decoding is CPU-heavy: the process runs at nice 10; the decoded
readout strips are cached in /dev/shm (rule 7), so a re-run decodes nothing.
"""

import argparse
import bisect
import dataclasses
import gzip
import json
import math
import os
import sys
import time
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "services" / "vision" / "src"))  # the reader itself (pure numpy)
import qa_export  # noqa: E402

from poring_dataset import mapcache  # noqa: E402
from poring_dataset.labels import gm_windows, in_windows  # noqa: E402
from poring_dataset.timeline import Timeline, tick_of  # noqa: E402
from poring_dataset.timeline import _cells as walk_cells  # noqa: E402  (the Timeline's own path)
from poring_env import ui_anchors as ua  # noqa: E402
from poring_packets.world import MOVE_COST, MOVE_DIAGONAL_COST, TICK_MOD, World  # noqa: E402
from poring_vision import selfpos  # noqa: E402

DATASETS = Path(os.environ.get("PORING_DATASETS", "/mnt/poring-lab-datasets"))
SCRATCH = Path(os.environ.get("SCRATCH", "/dev/shm/poring-lab-tmp"))
OUT = ROOT / "data" / "ui_anchors" / "minimap_digits.npz"
TRAIN = (
    "20261004T130548-console-p3-outdoor-a",
    "20261004T135714-console-p3-outdoor-b",
    "20261004T141832-console-p3-indoor-b",
)
HELD_OUT = (
    "20261004T143947-console-p3-outdoor-c",
    "20261004T150114-console-p3-outdoor-d",
    "20261004T152232-console-p3-indoor-c",
)

# Measured on the frozen 1280x720 layout (game-region pixels), 2026-10-04 S2 console frames.
ROI = (1128, 136, 152, 28)  # the strip kept per frame: magnifier, readout, zoom buttons
CELL_ORIGIN = (1158, 147)  # the first digit cell: its left column (the glyph's shadow), top row
SPACE = 8  # px from the x number's last cell to the y number's first
MAGNIFIER = (1136, 145, 12, 12)  # the magnifier icon left of the readout (x, y, w, h)
_RECT = selfpos.default_rect()
LAYOUT = selfpos.Layout(text_left=CELL_ORIGIN[0] - _RECT[0], top=CELL_ORIGIN[1] - _RECT[1],
                        number_gap=SPACE)  # fmt: skip
PLAYER_IDS = range(2_000_000, 110_000_000)  # rAthena: START_ACCOUNT_NUM .. START_NPC_NUM


# --- packet truth -------------------------------------------------------------------------------


def _tick_delta_ms(a: int, b: int) -> int:
    """a - b on the server's wrapping ms tick."""
    d = (a - b) % TICK_MOD
    return d - TICK_MOD if d > TICK_MOD // 2 else d


def walk_ms(walk: Any, grid: Any) -> float:
    """How long a walk takes on the Timeline's own path (rAthena's step timing)."""
    x, y, total = walk.x0, walk.y0, 0.0
    for cx, cy in walk_cells(grid, walk.x0, walk.y0, walk.x1, walk.y1):
        diagonal = cx != x and cy != y
        total += walk.speed * (MOVE_DIAGONAL_COST if diagonal else MOVE_COST) / MOVE_COST
        x, y = cx, cy
    return total


def infer_self_aid(events: Iterable[Mapping[str, Any]]) -> int | None:
    """Our own block id when the events do not carry login_accepted: the one player-range id
    that stops or vanishes but never appears (every other unit enters our view by appearing).
    None when it is not exactly one."""
    seen, appeared = set(), set()
    for e in events:
        if e["type"] in ("entity_stop", "entity_vanish") and int(e["gid"]) in PLAYER_IDS:
            seen.add(int(e["gid"]))
        elif e["type"] == "entity_appear":
            appeared.add(int(e["gid"]))
    candidates = seen - appeared
    return candidates.pop() if len(candidates) == 1 else None


def self_walk_spans(
    events: Iterable[Mapping[str, Any]], maps: Mapping[str, Any]
) -> list[tuple[int, int]]:
    """[start, end] (CLOCK_MONOTONIC ns, server time) of every walk of our own; a walk cut short
    by the next one, a stop or a map change ends there."""
    world = World()
    spans: list[list[int]] = []
    for e in sorted(events, key=lambda ev: int(ev["t_mono_ns"])):
        t, etype = int(e["t_mono_ns"]), str(e["type"])
        if etype == "login_accepted":
            world.aid = int(e["aid"])
        cut: int | None = None
        stopped = etype == "entity_stop" and world.aid is not None and int(e["gid"]) == world.aid
        if etype in ("map_change", "map_enter", "char_selected") or stopped:
            cut = t
        elif etype == "self_move":
            cut = t + _tick_delta_ms(int(e["server_tick"]), tick_of(t)) * 1_000_000
        if cut is not None and spans and spans[-1][1] > cut:
            spans[-1][1] = max(spans[-1][0], cut)
        world.apply(etype, dict(e))
        if etype == "self_move" and world.self_walk is not None:
            w = world.self_walk
            start = t + _tick_delta_ms(w.start_tick, tick_of(t)) * 1_000_000
            spans.append([start, start + int(walk_ms(w, maps.get(world.map or "")) * 1e6)])
    return [(a, b) for a, b in spans]


@dataclass(frozen=True, slots=True)
class FrameTruth:
    kind: str  # "standing" | "walking" | "excluded"
    map: str | None = None
    pos: tuple[float, float] | None = None  # cells, sub-cell while walking
    why: str = ""  # the exclusion's reason
    walk_dt_ms: float | None = None  # distance to the nearest walk span (0 inside one)


class SessionTruth:
    """Our own cell at any frame time, from the session's packets (offline only)."""

    def __init__(
        self,
        session: Path,
        maps: Mapping[str, Any],
        *,
        offset_ms: str = "auto",
        guard_ms: float = 300.0,
        load_ms: float = 3000.0,
    ) -> None:
        self.manifest = json.loads((session / "manifest.json").read_text())
        if offset_ms == "auto":
            self.offset_ms, self.offset_run = qa_export.auto_offset_ms(self.manifest["config"])
        else:
            self.offset_ms, self.offset_run = float(offset_ms), "manual"
        with gzip.open(session / "packets.jsonl.gz", "rt") as fh:
            events = [json.loads(line) for line in fh]
        self.aid: int | None = None
        self.aid_source = "login_accepted"
        if events and not any(e["type"] == "login_accepted" for e in events):
            self.aid, self.aid_source = infer_self_aid(events), "inferred"
            if self.aid is not None:
                first = min(int(e["t_mono_ns"]) for e in events)
                events.insert(0, {"type": "login_accepted", "aid": self.aid,
                                  "t_mono_ns": first - 1})  # fmt: skip
        self.timeline = Timeline(events, maps)
        self.gm = gm_windows(events)
        self.loads = [(int(e["t_mono_ns"]), int(e["t_mono_ns"]) + int(load_ms * 1e6))
                      for e in events if e["type"] in ("map_change", "map_enter")]  # fmt: skip
        self.spans = self_walk_spans(events, maps)
        self._starts = [a for a, _ in self.spans]
        self.guard_ns = int(guard_ms * 1e6)

    def walk_distance_ns(self, t_w: int) -> int:
        """0 inside a walk span, else the distance to the nearest one (a large number if none)."""
        best = 1 << 62
        i = bisect.bisect_right(self._starts, t_w)
        for a, b in self.spans[max(0, i - 2) : i + 2]:
            best = min(best, 0 if a <= t_w <= b else min(abs(t_w - a), abs(t_w - b)))
        return best

    def at(self, t_frame_ns: int) -> FrameTruth:
        if in_windows(t_frame_ns, self.gm):
            return FrameTruth("excluded", why="gm_window")
        if in_windows(t_frame_ns, self.loads):
            return FrameTruth("excluded", why="map_loading")
        t_w = t_frame_ns - int(self.offset_ms * 1e6)
        world = self.timeline.frame_world(t_w)
        if world.self_pos is None or world.map is None:
            return FrameTruth("excluded", world.map, why="no_position")
        dist = self.walk_distance_ns(t_w)
        kind = "walking" if dist <= self.guard_ns else "standing"
        return FrameTruth(kind, world.map, world.self_pos, walk_dt_ms=dist / 1e6)


def cell_of(v: float) -> int:
    """The cell a (sub-cell) position is in, ties up (never Python's banker's rounding)."""
    return math.floor(v + 0.5)


def resolve_session(name: str) -> Path:
    path = Path(name)
    return path if path.is_dir() else DATASETS / name


# --- frames -------------------------------------------------------------------------------------


def sample_strips(
    session: Path, n: int, cache: Path | None
) -> tuple[list[int], list[int], np.ndarray]:
    """(frame ids, frame times, ROI strips BGR) of ``n`` frames spread evenly over the session."""
    from poring_dataset.h264 import H264Session

    path = None if cache is None else cache / f"{session.name}-n{n}-roi.npz"
    if path is not None and path.exists():
        with np.load(path) as z:
            return [int(v) for v in z["frame_ids"]], [int(v) for v in z["t_ns"]], z["strips"]
    stream = H264Session(session)
    ids, times, strips = [], [], []
    x, y, w, h = ROI
    t0 = time.monotonic()
    for meta, img in stream.frames(stream.sample(n), verify=False, crop=True):
        ids.append(int(meta["frame_id"]))
        times.append(int(meta["t_mono_ns"]))
        strips.append(img[y : y + h, x : x + w].copy())
    print(f"  {session.name}: decoded {len(ids)} frames in {time.monotonic() - t0:.0f} s",
          file=sys.stderr)  # fmt: skip
    arr = np.stack(strips) if strips else np.zeros((0, h, w, 3), np.uint8)
    if path is not None:
        path.parent.mkdir(parents=True, exist_ok=True)
        np.savez(path, frame_ids=np.array(ids), t_ns=np.array(times), strips=arr)
    return ids, times, arr


def rect_in_roi() -> tuple[int, int, int, int]:
    x, y, w, h = _RECT
    return x - ROI[0], y - ROI[1], w, h


def button_strip_in_roi() -> tuple[int, int, int, int]:
    spec = ua.WINDOWS["minimap"]
    ox, oy = ua.CAPTURE_ORIGINS["minimap"]
    tx, ty = spec.template_offset
    assert spec.template_size is not None
    return ox + tx - ROI[0], oy + ty - ROI[1], *spec.template_size


def rect_gray(f: Mapping[str, Any]) -> np.ndarray:
    qx, qy, qw, qh = rect_in_roi()
    return np.asarray(f["gray"][qy : qy + qh, qx : qx + qw], np.float32)


# --- the minimap window, the training readouts, the in-sample check -----------------------------


def magnifier_shown(gray_roi: np.ndarray) -> bool:
    """A crude seed: the magnifier icon left of the readout is a white ring (~44 px >= 200)."""
    x, y = MAGNIFIER[0] - ROI[0], MAGNIFIER[1] - ROI[1]
    return int((gray_roi[y : y + MAGNIFIER[3], x : x + MAGNIFIER[2]] >= 200).sum()) >= 15


def window_presence(
    frames: list[dict[str, Any]],
) -> tuple[np.ndarray, np.ndarray, dict[str, float]]:
    """The minimap window's template (its zoom buttons), its stable mask, and per map the share
    of frames that show it; sets each frame's "window" flag.
      1. seed: the maps where the magnifier icon shows on most frames;
      2. per scene (session x seed map) the median strip of its standing frames; the template is
         the median of those, and its mask keeps the pixels where EVERY scene agrees (within 10
         grey levels) and holds still inside its scene (MAD < 6): the icons, not what shows
         through them (one long stand in one scene must not decide the mask);
      3. a frame shows the window when the masked mean abs difference is within the window's
         ``max_distance`` (ADR-0011)."""
    seed: dict[str, list[bool]] = {}
    for f in frames:
        if f["truth"].kind != "excluded" and f["truth"].map:
            seed.setdefault(f["truth"].map, []).append(magnifier_shown(f["gray"]))
    seed_maps = {m for m, v in seed.items() if sum(v) >= 0.5 * len(v)}
    bx, by, bw, bh = button_strip_in_roi()
    scenes: dict[tuple[str, str], list[np.ndarray]] = {}
    for f in frames:
        if f["truth"].kind == "standing" and f["truth"].map in seed_maps:
            key = (f["session"], f["truth"].map)
            scenes.setdefault(key, []).append(f["gray"][by : by + bh, bx : bx + bw])
    if not scenes:
        raise SystemExit("no training frame shows the minimap")
    stacks = [np.stack(v) for v in scenes.values()]
    medians = [np.median(s, axis=0) for s in stacks]
    template = np.median(np.stack(medians), axis=0).astype(np.float32)
    stable = np.ones(template.shape, bool)
    for s, m in zip(stacks, medians, strict=True):
        stable &= (np.abs(m - template) < 10.0) & (np.median(np.abs(s - m), axis=0) < 6.0)
    mask = stable.astype(np.float32)
    max_dist = ua.WINDOWS["minimap"].max_distance
    per_map: dict[str, list[bool]] = {}
    for f in frames:
        diff = np.abs(f["gray"][by : by + bh, bx : bx + bw] - template)
        f["window"] = float((diff * mask).sum() / mask.sum()) <= max_dist
        if f["truth"].kind != "excluded" and f["truth"].map:
            per_map.setdefault(f["truth"].map, []).append(f["window"])
    shares = {m: round(sum(v) / len(v), 4) for m, v in sorted(per_map.items())}
    return template, mask, shares


def training_readouts(
    frames: list[dict[str, Any]], readout_maps: list[str], per_position: int
) -> tuple[list[np.ndarray], list[tuple[int, int]], dict[str, dict[str, int]]]:
    """(rects, labels) from standing frames of maps that show the readout: at most
    ``per_position`` frames (evenly spread) per session x cell. Also: digits per session."""
    by_position: dict[tuple[str, int, int], list[dict[str, Any]]] = {}
    for f in frames:
        tr = f["truth"]
        if tr.kind != "standing" or tr.map not in readout_maps or not f["window"]:
            continue
        x, y = (cell_of(v) for v in tr.pos)
        by_position.setdefault((f["session"], x, y), []).append(f)
    rects, labels = [], []
    by_session: dict[str, dict[str, int]] = {str(d): {} for d in range(10)}
    for (session, x, y), group in sorted(by_position.items(), key=lambda kv: kv[0]):
        step = max(1.0, len(group) / per_position)
        for f in (group[int(i * step)] for i in range(min(per_position, len(group)))):
            rects.append(rect_gray(f))
            labels.append((x, y))
            for ch in f"{x}{y}":
                by_session[ch][session] = by_session[ch].get(session, 0) + 1
    return rects, labels, by_session


def outcome(reading: selfpos.Reading, truth: FrameTruth) -> str:
    """exact / within1 / wrong against the truth cell (rounded), or none:<reason>."""
    if reading.xy is None:
        return f"none:{reading.reason}"
    if truth.pos is None:
        return "read"
    ex, ey = (cell_of(v) for v in truth.pos)
    err = max(abs(reading.xy[0] - ex), abs(reading.xy[1] - ey))
    return "exact" if err == 0 else ("within1" if err <= 1 else "wrong")


def frame_class(truth: FrameTruth, readout_maps: list[str]) -> str:
    if truth.kind == "excluded":
        return f"excluded:{truth.why}"
    if truth.map not in readout_maps:
        return "no_readout_map"
    return truth.kind


def main() -> int:
    os.nice(10)
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("sessions", nargs="*", default=list(TRAIN))
    ap.add_argument("--per-session", type=int, default=4000)
    ap.add_argument("--per-position", type=int, default=40)
    ap.add_argument("--offset-ms", default="auto")
    ap.add_argument("--guard-ms", type=float, default=300.0)
    ap.add_argument("--load-ms", type=float, default=3000.0)
    ap.add_argument("--out", type=Path, default=OUT)
    ap.add_argument("--mapcache", type=Path, default=mapcache.GENERATED)
    ap.add_argument("--cache", type=Path, default=SCRATCH / "selfpos-cache")
    ap.add_argument("--report", type=Path, default=SCRATCH / "selfpos_calibrate.json")
    a = ap.parse_args()
    sessions = [resolve_session(s) for s in a.sessions]
    leaked = [s.name for s in sessions if s.name in HELD_OUT]
    if leaked:
        raise SystemExit(f"held-out sessions must not be calibrated on: {leaked}")
    maps = mapcache.load(a.mapcache, prere=True)

    frames: list[dict[str, Any]] = []
    truths = {}
    for session in sessions:
        truth = SessionTruth(session, maps, offset_ms=a.offset_ms, guard_ms=a.guard_ms,
                             load_ms=a.load_ms)  # fmt: skip
        truths[session.name] = {"offset_ms": truth.offset_ms, "offset_run": truth.offset_run,
                                "aid_source": truth.aid_source,
                                "aid_found": truth.aid is not None}  # fmt: skip
        ids, times, strips = sample_strips(session, a.per_session, a.cache)
        for fid, t, strip in zip(ids, times, strips, strict=True):
            frames.append({"session": session.name, "frame_id": fid, "truth": truth.at(t),
                           "gray": selfpos.to_gray(strip)})  # fmt: skip

    button_t, button_mask, shares = window_presence(frames)
    readout_maps = sorted(m for m, share in shares.items() if share >= 0.5)
    rects, labels, by_session = training_readouts(frames, readout_maps, a.per_position)
    templates, stats = selfpos.fit_templates(rects, labels, LAYOUT)
    meta = {
        "created": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "training_sessions": [s.name for s in sessions],
        "held_out_sessions": list(HELD_OUT),
        "per_session": a.per_session,
        "per_position": a.per_position,
        "truth": truths,
        "guard_ms": a.guard_ms,
        "load_ms": a.load_ms,
        "window_shown_share": shares,
        "readout_maps": readout_maps,
        "rect": list(_RECT),
        "layout": dataclasses.asdict(LAYOUT),
        "training_readouts": len(rects),
        "training_positions": len(set(labels)),
        "digits_by_session": by_session,
        "fit": stats,
    }
    templates = dataclasses.replace(templates, meta=meta)
    templates.save(a.out)
    ua.save_templates(a.out.parent, {"minimap": button_t}, {"minimap": button_mask})

    check: dict[str, dict[str, int]] = {}
    for f in frames:
        reading = selfpos.read_rect(rect_gray(f), templates)
        row = check.setdefault(frame_class(f["truth"], readout_maps), {})
        key = outcome(reading, f["truth"])
        row[key] = row.get(key, 0) + 1

    report = {
        "out": str(a.out),
        "bright": templates.bright,
        "max_score": templates.max_score,
        "min_margin": templates.min_margin,
        "ink_level": templates.ink_level,
        "shadow_level": templates.shadow_level,
        "stroke_rows": list(templates.stroke_rows),
        "text_left": templates.text_left,
        "number_gap": templates.number_gap,
        "window_mask_share": round(float(button_mask.mean()), 3),
        "in_sample": check,
        "meta": meta,
    }
    a.report.parent.mkdir(parents=True, exist_ok=True)
    a.report.write_text(json.dumps(report, indent=1))
    print(json.dumps(report, indent=1))
    missing = [d for d in range(10) if templates.counts[d] == 0]
    if missing:
        print(f"WARNING: digits never seen in training: {missing}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
