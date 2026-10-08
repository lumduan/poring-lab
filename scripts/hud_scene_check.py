#!/usr/bin/env python3
"""Acceptance for the HUD SCENE (Batt 2026-10-08): replay the scene process's log exactly as a
console receives it, over recorded frames.

    hud_scene_check.py rate --from T0 --to T1            messages per minute by type (idle ~0)
    hud_scene_check.py render FRAMES_DIR [--latency-ms 100]   an MP4 + a still, the scene drawn
    hud_scene_check.py offsets FRAMES_DIR [--threads 4]  box-to-sprite foot offsets per frame

- **Frames:** `<k>-<t_mono_ns>.jpg` (route_demo's recorder). A frame's time is its bus capture time,
  the same clock as the scene's messages.
- **The console's view of a frame at time t:** every message LOGGED by t + latency (it has arrived),
  and the frame's own motion offset (exact by time, else the latest at or before it).
- **offsets:** on every frame, each drawn unit box against the SAME detector run offline on that
  frame (the nearest foot of that class, within 120 px). Reported by class, walking and standing
  apart (walking = the scene moved on that frame).
"""

from __future__ import annotations

import argparse
import json
import math
import subprocess
import sys
from pathlib import Path
from typing import Any

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ro_agent as r  # noqa: E402

LOG = Path("/dev/shm/poring-lab-route/scene.jsonl")
COLOUR = {"monster": (255, 90, 90), "npc": (255, 200, 60), "sign": (251, 146, 60)}


def load_log(t0: int | None = None, t1: int | None = None) -> list[dict[str, Any]]:
    rows = []
    for path in (LOG.with_suffix(".jsonl.1"), LOG):
        if path.exists():
            for line in path.read_text().splitlines():
                if line:
                    e = json.loads(line)
                    if (t0 is None or e["logged_ns"] >= t0) and (
                        t1 is None or e["logged_ns"] <= t1
                    ):
                        rows.append(e)
    return sorted(rows, key=lambda e: e["logged_ns"])


class Replay:
    """The console's SceneStore in Python (scene.ts): keyframes, ordered deltas, the motions."""

    def __init__(self, log: list[dict[str, Any]]) -> None:
        self.log, self.i = log, 0
        self.objects: dict[int, dict[str, Any]] = {}
        self.seq, self.stale = -1, True
        self.motions: list[tuple[int, dict[str, float]]] = []  # (frame t, offset)

    def advance(self, now_ns: int) -> None:
        while self.i < len(self.log) and self.log[self.i]["logged_ns"] <= now_ns:
            m = self.log[self.i]["msg"]
            self.i += 1
            if m["type"] == "hud_scene":
                self.objects = {o["id"]: o for o in m["objects"]}
                self.seq, self.stale = m["seq"], False
                self.motions.append((m["t_mono_ns"], m["offset"]))
            elif m["type"] == "hud_delta":
                if self.stale or m["seq"] != self.seq + 1:
                    self.stale = True
                    continue
                self.seq = m["seq"]
                for o in m["add"]:
                    self.objects[o["id"]] = o
                for mv in m["move"]:
                    if mv["id"] in self.objects:
                        self.objects[mv["id"]] = {**self.objects[mv["id"]], "box": mv["box"]}
                for i in m["remove"]:
                    self.objects.pop(i, None)
            elif m["type"] == "hud_motion":
                self.motions.append((m["t_mono_ns"], m["offset"]))

    def offset_at(self, t: int) -> dict[str, float]:
        best = None
        for tm, off in self.motions:
            if tm <= t:
                best = off
        return best or {"x": 0.0, "y": 0.0}

    def boxes(self, t: int, dw: int, dh: int, gx: int, gy: int) -> list[dict[str, Any]]:
        if self.stale:
            return []
        off = self.offset_at(t)
        out = []
        for o in self.objects.values():
            dx, dy = (off["x"], off["y"]) if o["anchor"] == "world" else (0.0, 0.0)
            b = o["box"]
            out.append({**o, "px": ((b["x"] + dx) * dw - gx, (b["y"] + dy) * dh - gy,
                                    b["w"] * dw, b["h"] * dh)})  # fmt: skip
        return out


def frames(d: Path) -> list[tuple[int, Path]]:
    fs = sorted(d.glob("*.jpg"))
    return [(int(f.stem.split("-")[1]), f) for f in fs]


def moving_times(log: list[dict[str, Any]]) -> set[int]:
    return {e["msg"]["t_mono_ns"] for e in log if e["msg"]["type"] == "hud_motion"}


def rate(t0: int, t1: int) -> int:
    log = load_log(t0, t1)
    mins = max((t1 - t0) / 60e9, 1e-9)
    by: dict[str, int] = {}
    for e in log:
        by[e["msg"]["type"]] = by.get(e["msg"]["type"], 0) + 1
    print(json.dumps({"minutes": round(mins, 2), "per_minute": {k: round(v / mins, 2)
                      for k, v in by.items()}, "total": by}, indent=1))  # fmt: skip
    return 0


def render(d: Path, latency_ms: float) -> int:
    from PIL import Image, ImageDraw

    fs = frames(d)
    log = load_log(fs[0][0] - int(60e9), fs[-1][0] + int(5e9))
    rp = Replay(log)
    gx, gy, _, _ = r.game_region()
    dw, dh = r.desktop()
    out = d.parent / "scene-png"
    out.mkdir(exist_ok=True)
    best = (-1, 0)
    for k, (t, f) in enumerate(fs):
        rp.advance(t + int(latency_ms * 1e6))
        img = Image.open(f).convert("RGB")
        dr = ImageDraw.Draw(img)
        n_units = 0
        for o in rp.boxes(t, dw, dh, gx, gy):
            x, y, w, h = o["px"]
            if o["kind"] in ("zone", "window"):
                dr.rectangle([x, y, x + w, y + h], outline=(90, 200, 255), width=1)
                continue
            col = COLOUR.get(o["cls"], (220, 220, 220))
            dr.rectangle([x, y, x + w, y + h], outline=col, width=2)
            label = f"{o['cls']}" + ("" if o.get("conf") is None else f" {round(o['conf'] * 100)}%")
            dr.rectangle([x, y - 13, x + 7 * len(label), y], fill=(0, 0, 0))
            dr.text((x + 2, y - 12), label, fill=col)
            n_units += o["kind"] == "unit"
        img.save(out / f"{k:05d}.jpg", quality=90)
        best = max(best, (n_units, k))
    ts = np.array([t for t, _ in fs])
    fps = 1e9 / float(np.median(np.diff(ts))) if len(ts) > 1 else 10.0
    mp4 = d.parent / "hud-scene.mp4"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-framerate", f"{fps:.2f}", "-i",
                    str(out / "%05d.jpg"), "-pix_fmt", "yuv420p", str(mp4)],
                   check=True)  # fmt: skip
    Image.open(out / f"{best[1]:05d}.jpg").save(d.parent / "hud-scene-still.png")
    for p in out.glob("*.jpg"):
        p.unlink()
    still = d.parent / "hud-scene-still.png"
    print(json.dumps({"frames": len(fs), "video": str(mp4), "still": str(still),
                      "fps": round(fps, 1)}))  # fmt: skip
    return 0


def offsets(d: Path, latency_ms: float, threads: int) -> int:
    import unit_detector
    from PIL import Image

    fs = frames(d)
    log = load_log(fs[0][0] - int(60e9), fs[-1][0] + int(5e9))
    moving = moving_times(log)
    rp = Replay(log)
    gx, gy, _, _ = r.game_region()
    dw, dh = r.desktop()
    det = unit_detector.UnitDetector(threads=threads)
    per: dict[str, list[float]] = {}
    try:
        for t, f in fs:
            rp.advance(t + int(latency_ms * 1e6))
            drawn = [o for o in rp.boxes(t, dw, dh, gx, gy) if o["kind"] == "unit"]
            if not drawn:
                continue
            img = np.asarray(Image.open(f).convert("RGB"))[..., ::-1]
            found = det.detect(img)
            state = "walking" if t in moving else "standing"
            for o in drawn:
                x, y, w, h = o["px"]
                foot = (x + w / 2, y + h)
                same = [b.foot for b in found if b.cls == o["cls"]]
                if not same:
                    continue
                dist = min(math.dist(foot, s) for s in same)
                if dist <= 120:
                    per.setdefault(f"{o['cls']}:{state}", []).append(dist)
    finally:
        det.close()
    rep: dict[str, Any] = {}
    for key, ds in sorted(per.items()):
        ds.sort()
        rep[key] = {"n": len(ds), "median_px": round(ds[len(ds) // 2], 1),
                    "p95_px": round(ds[int(len(ds) * 0.95)], 1),
                    "max_px": round(ds[-1], 1)}  # fmt: skip
    (d.parent / "hud-scene-offsets.json").write_text(json.dumps(rep, indent=1))
    print(json.dumps(rep, indent=1))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("rate")
    a.add_argument("--from", dest="t0", type=int, required=True)
    a.add_argument("--to", dest="t1", type=int, required=True)
    b = sub.add_parser("render")
    b.add_argument("dir", type=Path)
    b.add_argument("--latency-ms", type=float, default=100.0)
    c = sub.add_parser("offsets")
    c.add_argument("dir", type=Path)
    c.add_argument("--latency-ms", type=float, default=100.0)
    c.add_argument("--threads", type=int, default=4)
    x = ap.parse_args()
    if x.cmd == "rate":
        return rate(x.t0, x.t1)
    return (
        render(x.dir, x.latency_ms)
        if x.cmd == "render"
        else offsets(x.dir, x.latency_ms, x.threads)
    )


if __name__ == "__main__":
    sys.exit(main())
