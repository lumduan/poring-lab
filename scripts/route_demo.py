#!/usr/bin/env python3
"""The LIVE route preview, demonstrated (Batt 2026-10-08): a recorded walk where the route stays
GLUED to the floor while the camera moves, and the walked-over part fades. NOT scored.

    route_demo.py run [--scene indoor] [--n 3] [--seed 31]      then
    route_demo.py render DIR                                    (the composite video + the check)

run: walk@11 routes with route_preview.LivePreview attached through runtime hooks (walk11.py, the
pre-registered rule, is not modified): its plan sets the route, each click starts the walk timing,
each /where fix snaps it, each route end clears it. A second grabber records the game region ~10
times a second; the frames, the live messages and the session's packets go to /dev/shm (client
pixels: never committed).
render: each frame gets the live message nearest its capture time (exactly as the console picks)
drawn on it -> an MP4; and the CHECK, from the pixels alone: between consecutive frames the goal
ring must move exactly as the scene scrolls (phase correlation), walking and standing apart.
"""

from __future__ import annotations

import argparse
import json
import sys
import threading
import time
from pathlib import Path
from typing import Any

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ro_agent as r  # noqa: E402
import route_preview as rp  # noqa: E402

OUT = Path("/dev/shm/poring-lab-tmp/route-demo")
GM_SPEED_MS = 150  # a character's default walk speed


def run(scene: str, n: int, seed: int) -> int:
    import walk6 as w6
    import walk11

    state: dict[str, Any] = {"lp": None, "rec": None}
    out = OUT / time.strftime("%Y%m%dT%H%M%S")
    (out / "frames").mkdir(parents=True, exist_ok=True)
    stop = threading.Event()

    def recorder() -> None:
        screen = r.Screen()
        k = 0
        while not stop.is_set():
            gx, gy, gw, gh = r.game_region()
            t, img = screen.grab(gx, gy, gw, gh)
            np.save(out / "frames" / f"{k:05d}-{t}.npy", img[..., :3])
            k += 1
            time.sleep(0.1)

    orig_preview = walk11.preview

    def preview(agent: Any, w: Any, start: Any, wps: Any, click: Any, label: str) -> None:
        if state["lp"] is None:
            state["lp"] = rp.LivePreview(agent.ws.send, w.camera, w.gat, r.game_region(),
                                         r.desktop(), "route demo").start()  # fmt: skip
            state["rec"] = threading.Thread(target=recorder, daemon=True)
            state["rec"].start()
        goal = wps[-1] if wps else start
        state["lp"].set_route(w.position, list(wps), goal, click)

    orig_click = walk11.click_step

    def click_step(pr: Any, w: Any, end: Any, *a: Any, **k: Any) -> dict[str, Any]:
        path = w6.plan(w, end, set()) or [end]
        res = orig_click(pr, w, end, *a, **k)
        if res.get("clicked") and state["lp"] is not None:
            state["lp"].walk(w.position, path, int(res["t_click"]), GM_SPEED_MS)
        return res

    orig_reloc = walk11.where_relocalise

    def where_relocalise(templates: Any) -> Any:
        fix = orig_reloc(templates)

        def wrapped(*a: Any, **k: Any) -> dict[str, Any]:
            rl = fix(*a, **k)
            if rl.get("ok") and state["lp"] is not None:
                state["lp"].snap(rl["to"])
            return rl

        return wrapped

    orig_route = walk11.walk_route

    def walk_route(*a: Any, **k: Any) -> dict[str, Any]:
        try:
            return orig_route(*a, **k)
        finally:
            if state["lp"] is not None:
                state["lp"].clear()

    walk11.preview, walk11.click_step = preview, click_step
    walk11.where_relocalise, walk11.walk_route = where_relocalise, walk_route
    try:
        rc = walk11.run(scene, "clean", n, seed, "route-demo", 4)
    finally:
        stop.set()
        if state["lp"] is not None:
            state["lp"].stop()
            (out / "live.json").write_text(json.dumps(state["lp"].sent))
        walk11.preview = orig_preview
    sessions = sorted(Path("/dev/shm/poring-lab-demo").glob("*route-demo*"))
    (out / "session.txt").write_text(str(sessions[-1]) if sessions else "")
    print(json.dumps({"out": str(out), "session": str(sessions[-1]) if sessions else None}))
    return rc


def render(out: Path) -> int:
    import subprocess

    from PIL import Image, ImageDraw

    live = json.loads((out / "live.json").read_text())
    live_t = np.array([m["t_mono_ns"] for m in live])
    gx, gy, gw, gh = r.game_region()
    dw, dh = r.desktop()
    frames = sorted((out / "frames").glob("*.npy"))
    (out / "png").mkdir(exist_ok=True)
    drawn = 0
    for k, f in enumerate(frames):
        t = int(f.stem.split("-")[1])
        img = Image.fromarray(np.load(f)[..., ::-1].copy())
        d = ImageDraw.Draw(img)
        j = int(np.argmin(np.abs(live_t - t))) if len(live_t) else -1
        m = live[j] if j >= 0 and abs(int(live_t[j]) - t) <= 200_000_000 else None
        if m and m["points"]:
            to = lambda p: ((p["x"] * dw) - gx, (p["y"] * dh) - gy)  # noqa: E731
            for s in m.get("passed", []):
                a = 1 - s["age_ms"] / 400
                if a > 0:
                    d.line([to(s["points"][0]), to(s["points"][-1])],
                           fill=(245, 158, 11, int(150 * a)), width=4)  # fmt: skip
            line = [to(p) for p in m["points"] if p["kind"] in ("feet", "waypoint")]
            if len(line) > 1:
                d.line(line, fill=(0, 0, 0), width=7)
                d.line(line, fill=(245, 158, 11), width=4)
            for p in m["points"]:
                u, v = to(p)
                if p["kind"] == "goal":
                    d.ellipse([u - 10, v - 10, u + 10, v + 10], outline=(245, 158, 11), width=3)
                elif p["kind"] == "click":
                    d.line([(u - 8, v), (u + 8, v)], fill=(253, 230, 138), width=2)
                    d.line([(u, v - 8), (u, v + 8)], fill=(253, 230, 138), width=2)
            drawn += 1
        img.save(out / "png" / f"{k:05d}.png")
    mp4 = out / "route-demo.mp4"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-framerate", "10", "-i",
                    str(out / "png" / "%05d.png"), "-pix_fmt", "yuv420p", str(mp4)],
                   check=True)  # fmt: skip
    print(json.dumps({"frames": len(frames), "with_route": drawn, "video": str(mp4),
                      "glued": check(frames, live, live_t)}))  # fmt: skip
    return 0


def scene_shift(a: np.ndarray, b: np.ndarray) -> tuple[float, float]:
    """How far the scene moved from frame a to frame b (px), by phase correlation of the band
    around the character (the UI windows excluded)."""

    def band(x: np.ndarray) -> np.ndarray:
        g = x[200:600, 300:1100].astype(float).mean(-1)
        return (g - g.mean()) * np.hanning(g.shape[0])[:, None] * np.hanning(g.shape[1])[None, :]

    fa, fb = np.fft.fft2(band(a)), np.fft.fft2(band(b))
    c = np.fft.ifft2(fb * np.conj(fa) / (np.abs(fb * np.conj(fa)) + 1e-9)).real
    dy, dx = np.unravel_index(int(np.argmax(c)), c.shape)
    h, w = c.shape
    return (float(dx - w if dx > w // 2 else dx), float(dy - h if dy > h // 2 else dy))


def check(frames: list[Path], live: list[dict[str, Any]], live_t: np.ndarray) -> dict[str, Any]:
    """GLUED = between consecutive frames the goal ring moves exactly as the scene scrolls. The
    old screen-anchored overlay would score the whole scroll (its ring never moved)."""
    dw, dh = r.desktop()

    def goal_at(t: int) -> tuple[float, float] | None:
        j = int(np.argmin(np.abs(live_t - t)))
        if abs(int(live_t[j]) - t) > 200_000_000:
            return None
        g = [p for p in live[j]["points"] if p["kind"] == "goal"]
        return (g[0]["x"] * dw, g[0]["y"] * dh) if g else None

    moving, still = [], []
    prev = None
    for f in frames:
        t = int(f.stem.split("-")[1])
        img = np.load(f)
        g = goal_at(t)
        if prev is not None and g is not None and prev[1] is not None:
            sx, sy = scene_shift(prev[0], img)
            gxd, gyd = g[0] - prev[1][0], g[1] - prev[1][1]
            err = float(np.hypot(gxd - sx, gyd - sy))
            (moving if np.hypot(sx, sy) >= 2 else still).append((err, float(np.hypot(sx, sy))))
        prev = (img, g)

    def q(xs: list[tuple[float, float]], k: int) -> dict[str, Any]:
        if not xs:
            return {"n": 0}
        e = np.array([x[k] for x in xs])
        return {"n": len(xs), "median": round(float(np.median(e)), 1),
                "p95": round(float(np.percentile(e, 95)), 1)}  # fmt: skip

    return {"walking_ring_error_px": q(moving, 0), "walking_scene_shift_px": q(moving, 1),
            "standing_ring_error_px": q(still, 0)}  # fmt: skip


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = ap.add_subparsers(dest="cmd", required=True)
    a1 = sub.add_parser("run")
    a1.add_argument("--scene", default="indoor")
    a1.add_argument("--n", type=int, default=3)
    a1.add_argument("--seed", type=int, default=31)
    a2 = sub.add_parser("render")
    a2.add_argument("dir", type=Path)
    a = ap.parse_args()
    return run(a.scene, a.n, a.seed) if a.cmd == "run" else render(a.dir)


if __name__ == "__main__":
    sys.exit(main())
