#!/usr/bin/env python3
"""The HUD SCENE process (Batt 2026-10-08, H.264-style): a RETAINED overlay the console draws on
every frame, kept current by DELTAS, whether a rule runs or not (bot idle, or Batt playing).

    hud_scene.py [--hz 10] [--det-period 1.0]         (one at a time: an flock)

- **Screen-anchored objects** (the client's UI windows, the work zone) are sent once and never
  shift.
- **World-anchored objects** (units, signboards) all shift by ONE global motion per frame: the
  scene's measured scroll (`route_preview.scene_shift`, sub-pixel, the UI and our character masked
  out), like a motion vector. It needs no map knowledge.
- **Messages** (`poring_env.protocol`):
  - `HudMotion` (the frame's offset), only while the scene moves;
  - `HudDelta` (add / move / remove), only on changes;
  - `HudScene`, a full KEYFRAME every KEYFRAME_S.
  So the rate while idle is about zero apart from keyframes.
- **Detection only DISCOVERS changes:** new units in view, moving monsters, units gone, signboards.
  The unit detector runs in its own thread, niced, DET_THREADS threads, at most every DET_PERIOD_S
  while the scene changes and every DET_IDLE_S when still. NPCs, once found, ride the global motion.
- **Frames:** the RDP frame bus through ro_agent's screen helper (the `frame_id` the console shows).
  It runs only while the frames come from the bus (never an extra X grab).
- **Output:** the backend's display-only channel (`/internal/display`, the internal listener). It is
  not an agent, works in any mux mode, and sends no input.
- **Log:** every message sent goes to SCENE_LOG (RAM, rotated) for renders and the offline check.

Distance in cells needs the map's camera and our cell; that is the DECISION layer's (a rule's
OperatorHud), not this perception layer's.
"""

from __future__ import annotations

import argparse
import contextlib
import fcntl
import json
import os
import signal
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

STATE_DIR = Path(os.environ.get("ROUTE_PLAN_DIR", "/dev/shm/poring-lab-route"))
LOCK = STATE_DIR / "hud_scene.lock"
SCENE_LOG = STATE_DIR / "scene.jsonl"
SCENE_LOG_MAX = 20_000_000  # bytes, then rotated once (.1)
KEYFRAME_S = 5.0
MOTION_MIN_PX = 0.3  # a smaller frame-to-frame shift is noise: no motion, no message
DET_THREADS = 2
DET_PERIOD_S = 1.0  # the detector, while the scene moves or changes
DET_IDLE_S = 5.0  # ... and when it is still (to discover a unit walking in)
MATCH_PX = 40.0  # a detection within this of an object's feet (scene px) IS that object
MOVE_PX = 4.0  # a matched object that moved more than this gets a move delta
MISSES = 2  # an object missed by this many consecutive detection passes is removed
CHANGE_DIFF = 6.0  # mean abs gray difference (downsampled) above which the frame "changed"


@dataclass
class Obj:
    id: int
    kind: str  # unit | window | zone | sign
    anchor: str  # world | screen
    box: tuple[float, float, float, float]  # game px, x0 y0 x1 y1; world objects at offset 0
    cls: str = ""
    conf: float | None = None
    misses: int = 0


class SceneTracker:
    """The retained scene: objects with ids, the global offset, and the deltas that keep a console
    current. Pure (no I/O): every input is game-region px, every output protocol-shaped dicts."""

    def __init__(self, region: tuple[int, int, int, int], desktop: tuple[int, int],
                 windows: list[tuple[int, int, int, int]]) -> None:  # fmt: skip
        self.gx, self.gy, self.gw, self.gh = region
        self.dw, self.dh = desktop
        self.offset = np.zeros(2)  # game px: the scene's cumulative motion
        self.objects: dict[int, Obj] = {}
        self.next_id = 1
        self.seq = 0
        self._add(Obj(0, "zone", "screen", (0.0, 0.0, float(self.gw), float(self.gh))))
        for x0, y0, x1, y1 in windows:
            self._add(Obj(0, "window", "screen", (float(x0), float(y0), float(x1), float(y1))))

    def _add(self, o: Obj) -> Obj:
        o.id = self.next_id
        self.next_id += 1
        self.objects[o.id] = o
        return o

    # --- protocol shapes ----------------------------------------------------------------------
    def _rect(self, box: tuple[float, float, float, float]) -> dict[str, float]:
        x0, y0, x1, y1 = box
        return {"x": (self.gx + x0) / self.dw, "y": (self.gy + y0) / self.dh,
                "w": max(0.0, x1 - x0) / self.dw, "h": max(0.0, y1 - y0) / self.dh}  # fmt: skip

    def _obj(self, o: Obj) -> dict[str, Any]:
        r = self._rect(o.box)  # a world object's box is where it is drawn at motion offset 0
        out: dict[str, Any] = {"id": o.id, "kind": o.kind, "anchor": o.anchor, "box": r,
                               "cls": o.cls[:32]}  # fmt: skip
        if o.conf is not None:
            out["conf"] = round(min(max(o.conf, 0.0), 1.0), 3)
        return out

    def offset_norm(self) -> dict[str, float]:
        return {"x": float(self.offset[0]) / self.dw, "y": float(self.offset[1]) / self.dh}

    def keyframe(self) -> dict[str, Any]:
        return {"seq": self.seq, "offset": self.offset_norm(),
                "objects": [self._obj(o) for o in self.objects.values()],
                "period_ms": int(KEYFRAME_S * 1000)}  # fmt: skip

    # --- inputs -------------------------------------------------------------------------------
    def motion(self, shift: tuple[float, float]) -> bool:
        """The scene moved by ``shift`` (game px) since the last frame: True when it counts."""
        if float(np.hypot(*shift)) < MOTION_MIN_PX:
            return False
        self.offset += np.asarray(shift, dtype=float)
        return True

    def observe(
        self, found: list[dict[str, Any]], frame_offset: np.ndarray
    ) -> dict[str, Any] | None:
        """One detection pass on a frame whose offset was ``frame_offset``: ``found`` = boxes in
        game px with cls / conf / kind ("unit" or "sign"). Returns a delta, or None."""
        add, move, remove = [], [], []
        world = {i: o for i, o in self.objects.items() if o.anchor == "world"}
        taken: set[int] = set()
        for f in found:
            x0, y0, x1, y1 = (float(v) for v in f["box"])
            sb = (x0 - frame_offset[0], y0 - frame_offset[1], x1 - frame_offset[0],
                  y1 - frame_offset[1])  # fmt: skip
            foot = np.array([(sb[0] + sb[2]) / 2, sb[3]])
            best, bd = None, MATCH_PX
            for i, o in world.items():
                if i in taken or o.kind != f.get("kind", "unit") or o.cls != f.get("cls", ""):
                    continue
                d = float(np.hypot(*(foot - np.array([(o.box[0] + o.box[2]) / 2, o.box[3]]))))
                if d < bd:
                    best, bd = i, d
            if best is None:
                o = self._add(Obj(0, f.get("kind", "unit"), "world", sb, str(f.get("cls", "")),
                                  f.get("conf")))  # fmt: skip
                taken.add(o.id)
                add.append(self._obj(o))
                continue
            o = world[best]
            taken.add(best)
            o.misses, o.conf = 0, f.get("conf", o.conf)
            if bd > MOVE_PX:
                o.box = sb
                move.append({"id": o.id, "box": self._rect(o.box)} |
                            ({"conf": round(o.conf, 3)} if o.conf is not None else {}))  # fmt: skip
        for i, o in world.items():
            if i in taken:
                continue
            fx, fy = (o.box[0] + o.box[2]) / 2 + frame_offset[0], o.box[3] + frame_offset[1]
            in_view = 0 <= fx <= self.gw and 0 <= fy <= self.gh
            o.misses += 1
            if not in_view or o.misses >= MISSES:
                del self.objects[i]
                remove.append(i)
        if not (add or move or remove):
            return None
        self.seq += 1
        return {"seq": self.seq, "add": add, "move": move, "remove": remove}


# --- the process --------------------------------------------------------------------------------
class Sender:
    """The display channel (the internal listener), reconnecting; every message is also logged."""

    def __init__(self) -> None:
        self.ws: Any = None
        self.retry_at = 0.0
        self.sent = 0

    def _url(self) -> str:
        import ro_agent as r

        return r.backend_ws().replace("/internal/agent", "/internal/display")

    def send(self, msg: dict[str, Any]) -> None:
        text = json.dumps(msg)
        with contextlib.suppress(Exception):
            if SCENE_LOG.exists() and SCENE_LOG.stat().st_size > SCENE_LOG_MAX:
                SCENE_LOG.replace(SCENE_LOG.with_suffix(".jsonl.1"))
            with open(SCENE_LOG, "a") as fh:
                fh.write(text + "\n")
        if self.ws is None and time.monotonic() >= self.retry_at:
            try:
                from websockets.sync.client import connect

                self.ws = connect(self._url(), open_timeout=5, max_size=2**20)
            except Exception as exc:  # noqa: BLE001 -- display only
                print(f"{time.strftime('%H:%M:%S')} display channel down ({exc})", flush=True)
                self.retry_at = time.monotonic() + 5.0
                return
        if self.ws is None:
            return
        try:
            self.ws.send(text)
            self.sent += 1
            with contextlib.suppress(Exception):  # an ErrorReply would mean a protocol bug: log it
                while True:
                    reply = self.ws.recv(timeout=0)
                    print(
                        f"{time.strftime('%H:%M:%S')} display reply: {str(reply)[:200]}", flush=True
                    )
        except Exception:  # noqa: BLE001
            with contextlib.suppress(Exception):
                self.ws.close()
            self.ws, self.retry_at = None, time.monotonic() + 5.0


def frame_changed(a: np.ndarray | None, b: np.ndarray) -> bool:
    if a is None:
        return True
    ga = a[::8, ::8, :3].astype(np.float32).mean(-1)
    gb = b[::8, ::8, :3].astype(np.float32).mean(-1)
    return float(np.abs(ga - gb).mean()) > CHANGE_DIFF


def serve(hz: float, det_period: float) -> int:
    import ro_agent as r
    import route_preview as rp

    STATE_DIR.mkdir(parents=True, exist_ok=True)
    lock = open(LOCK, "w")  # noqa: SIM115 -- held for the process's life
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        print(f"{time.strftime('%H:%M:%S')} another HUD scene process runs: exiting", flush=True)
        return 0
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    os.nice(10)  # display only: below every rule (its detector included; children inherit it)
    region, desktop = tuple(r.game_region()), tuple(r.desktop())
    tracker = SceneTracker(region, desktop, [tuple(w) for w in rp.UI_WINDOWS])  # type: ignore[arg-type]
    out = Sender()
    screen: Any = None
    latest: dict[str, Any] = {}
    stop = threading.Event()
    stats = {"det": 0, "det_ms": [], "frames": 0, "motion": 0}

    def detector() -> None:
        import unit_detector
        from idle_click import sign_box

        try:
            det = unit_detector.UnitDetector(threads=DET_THREADS)
        except Exception as exc:  # noqa: BLE001
            print(f"{time.strftime('%H:%M:%S')} HUD detector unavailable ({exc})", flush=True)
            return
        last_img: np.ndarray | None = None
        last_t = 0.0
        try:
            while not stop.is_set():
                got = latest.get("frame")
                now = time.monotonic()
                if got is None:
                    stop.wait(0.1)
                    continue
                t, fid, img, off = got
                changed = frame_changed(last_img, img)
                if now - last_t < (det_period if changed else DET_IDLE_S):
                    stop.wait(0.1)
                    continue
                t0 = time.monotonic()
                found = [{"kind": "unit", "cls": b.cls, "conf": b.score,
                          "box": [b.x0, b.y0, b.x1, b.y1]} for b in det.detect(img)
                         if b.cls != "player"]  # fmt: skip
                sb = sign_box(img)
                if sb is not None:
                    found.append({"kind": "sign", "cls": "sign", "conf": None, "box": list(sb)})
                stats["det_ms"].append(1000 * (time.monotonic() - t0))
                stats["det"] += 1
                last_img, last_t = img, now
                delta = tracker.observe(found, off)
                if delta is not None:
                    out.send({"type": "hud_delta", "t_mono_ns": t, "frame_id": fid, **delta})
        finally:
            with contextlib.suppress(Exception):
                det.close()

    th = threading.Thread(target=detector, name="hud-detector", daemon=True)
    th.start()
    prev: np.ndarray | None = None
    t_key, t_report = 0.0, time.monotonic()
    print(
        f"{time.strftime('%H:%M:%S')} HUD scene: {hz:g} Hz frames, detector every "
        f"{det_period:g} s (idle {DET_IDLE_S:g} s), keyframe every {KEYFRAME_S:g} s",
        flush=True,
    )
    try:
        while True:
            t_loop = time.monotonic()
            if screen is None:
                screen = r.Screen()
            t, img, fid, src = screen.grab_meta(*region)
            if src != "bus":  # never an extra X grab: wait for the frame bus
                prev = None
                time.sleep(1.0)
                continue
            stats["frames"] += 1
            if prev is not None:
                shift = rp.scene_shift(prev, img)
                if tracker.motion(shift):
                    stats["motion"] += 1
                    out.send({"type": "hud_motion", "t_mono_ns": int(t), "frame_id": int(fid),
                              "offset": tracker.offset_norm()})  # fmt: skip
            prev = img
            latest["frame"] = (int(t), int(fid), img, tracker.offset.copy())
            if time.monotonic() - t_key >= KEYFRAME_S:
                t_key = time.monotonic()
                out.send({"type": "hud_scene", "t_mono_ns": int(t), "frame_id": int(fid),
                          **tracker.keyframe()})  # fmt: skip
            if time.monotonic() - t_report >= 60:
                ms = sorted(stats["det_ms"]) or [0.0]
                print(f"{time.strftime('%H:%M:%S')} HUD scene: frames {stats['frames'] / 60:.1f}"
                      f" Hz, motion msgs {stats['motion'] / 60:.2f}/s, detector "
                      f"{stats['det'] / 60:.2f} Hz (median {ms[len(ms) // 2]:.0f} ms), objects "
                      f"{len(tracker.objects)}, sent {out.sent}", flush=True)  # fmt: skip
                stats.update(det=0, det_ms=[], frames=0, motion=0)
                t_report = time.monotonic()
            time.sleep(max(0.0, 1.0 / hz - (time.monotonic() - t_loop)))
    finally:
        stop.set()
        with contextlib.suppress(Exception):
            if screen is not None:
                screen.close()
        lock.close()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--hz", type=float, default=10.0)
    ap.add_argument("--det-period", type=float, default=DET_PERIOD_S)
    a = ap.parse_args()
    return serve(a.hz, a.det_period)


if __name__ == "__main__":
    sys.exit(main())
