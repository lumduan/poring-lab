#!/usr/bin/env python3
"""The LIVE route preview, demonstrated (Batt 2026-10-08). The test is a recorded walk where the
route stays GLUED to the floor while the camera moves, the line STARTS AT THE FEET, and the walked
part fades. NOT scored.

    route_demo.py run [--scene indoor] [--n 3] [--seed 31]      then
    route_demo.py render DIR                                    (the composite video + the check)

run: walk@12 routes, exactly as every walk run since 2026-10-08: the rule publishes its plan in
CELLS (route_plan.py) and the previewer daemon (route_previewd.py) draws it. route_demo only adds
the previewer's message log (live.jsonl) and the recorder.
- The plan sets the route; each click gives the engine's walk; each step and each /where fix gives
  the believed cell; each route end clears it.
- A RECORDER process grabs the game region ~10 times a second, independently of the preview's own
  grabs, as the console sees the stream.
- The frames (JPEG), the preview's live messages and the session's packets go to /dev/shm (client
  pixels: never committed).

render: each frame gets the live message nearest its capture time, exactly as the console picks,
drawn on it -> an MP4. Then the CHECK, from the pixels alone:
- glued: between consecutive frames the goal ring moves exactly as the scene scrolls (phase
  correlation), walking and standing apart;
- feet: the drawn line's start against the feet measured on that frame (route_preview.find_feet);
- per-frame numbers -> frames.csv.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ro_agent as r  # noqa: E402
import route_preview as rp  # noqa: E402

OUT = Path("/dev/shm/poring-lab-tmp/route-demo")
REC_HZ = 10.0
MATCH_NS = 200_000_000  # the console draws a live message only within 200 ms of the frame


def _record(out: str, region: tuple[int, int, int, int], stop: Any, hz: float) -> None:
    """The recorder process: the game region as JPEGs named <k>-<t_mono_ns>.jpg."""
    from PIL import Image

    screen = r.Screen()
    k = 0
    while not stop.is_set():
        t0 = time.monotonic()
        t, img = screen.grab(*region)
        Image.fromarray(np.ascontiguousarray(img[..., 2::-1])).save(
            Path(out) / f"{k:05d}-{t}.jpg", quality=92
        )
        k += 1
        time.sleep(max(0.0, 1.0 / hz - (time.monotonic() - t0)))


def run(scene: str, n: int, seed: int) -> int:
    import multiprocessing as mp

    import route_plan
    import walk12

    out = OUT / time.strftime("%Y%m%dT%H%M%S")
    (out / "frames").mkdir(parents=True, exist_ok=True)
    ctx = mp.get_context("spawn")
    stop = ctx.Event()
    rec = ctx.Process(target=_record, args=(str(out / "frames"), tuple(r.game_region()), stop,
                                            REC_HZ), daemon=True)  # fmt: skip
    # walk@12 publishes its plan itself; enabling it here first adds the previewer's log
    token = route_plan.enable(f"route-demo-{time.strftime('%H%M%S')}", walk12.SCENES8[scene][0],
                              log_path=str(out / "live.jsonl"))  # fmt: skip
    route_plan.ensure_previewer()
    rec.start()
    try:
        rc = walk12.run(scene, "clean", n, seed, "route-demo", 4)
    finally:
        stop.set()
        if rec.is_alive():
            rec.join(timeout=5)
        route_plan.disable(token)
    sessions = sorted(Path("/dev/shm/poring-lab-demo").glob("*route-demo*"))
    (out / "session.txt").write_text(str(sessions[-1]) if sessions else "")
    print(json.dumps({"out": str(out), "session": str(sessions[-1]) if sessions else None}))
    return rc


def _frames(out: Path) -> list[tuple[int, Path]]:
    fs = sorted((out / "frames").glob("*.jpg")) or sorted((out / "frames").glob("*.npy"))
    return [(int(f.stem.split("-")[1]), f) for f in fs]


def _load(f: Path) -> np.ndarray:
    """A recorded frame as BGR (the order the preview's pixel functions read)."""
    if f.suffix == ".npy":
        return np.load(f)[..., :3]
    from PIL import Image

    return np.asarray(Image.open(f).convert("RGB"))[..., ::-1]


def _live(out: Path) -> list[dict[str, Any]]:
    if (out / "live.jsonl").exists():
        return [json.loads(x) for x in (out / "live.jsonl").read_text().splitlines() if x]
    return list(json.loads((out / "live.json").read_text()))


def _nearest(live: list[dict[str, Any]], live_t: np.ndarray, t: int) -> dict[str, Any] | None:
    if not len(live_t):
        return None
    j = int(np.argmin(np.abs(live_t - t)))
    return live[j] if abs(int(live_t[j]) - t) <= MATCH_NS else None


RA2_LINE = (70, 230, 90)
RA2_NODE = (253, 230, 138)
RA2_PULSE_MS = 700


def ra2(d: Any, m: dict[str, Any], to: Any, t_ns: int) -> None:
    """The console's RA2 look (RouteCanvas.tsx): a thin line from the feet, square nodes at the
    corners, a box on the next click, four arrows converging on the goal (animated by time)."""
    for s in m.get("passed", []):
        a = 1 - s["age_ms"] / 400
        if a > 0:
            c = tuple(int(v * a + 0.5) for v in RA2_LINE)
            d.line([to(s["points"][0]), to(s["points"][-1])], fill=c, width=2)
    line = [to(p) for p in m["points"] if p["kind"] in ("feet", "waypoint")]
    if len(line) > 1:
        d.line(line, fill=(0, 0, 0), width=4)
        d.line(line, fill=RA2_LINE, width=2)
        for u, v in line[1:]:
            d.rectangle([u - 4, v - 4, u + 4, v + 4], fill=(0, 0, 0))
            d.rectangle([u - 3, v - 3, u + 3, v + 3], fill=RA2_NODE)
    phase = (t_ns / 1e6 % RA2_PULSE_MS) / RA2_PULSE_MS
    for p in m["points"]:
        u, v = to(p)
        if p["kind"] == "click":
            d.rectangle([u - 5, v - 5, u + 5, v + 5], outline=RA2_NODE, width=2)
        elif p["kind"] == "goal":
            r = 14 - 8 * phase
            for a in (np.pi / 4, 3 * np.pi / 4, 5 * np.pi / 4, 7 * np.pi / 4):
                tx, ty = u + np.cos(a) * r, v + np.sin(a) * r * 0.6
                bx, by = u + np.cos(a) * (r + 7), v + np.sin(a) * (r + 7) * 0.6
                nx, ny = -np.sin(a) * 4, np.cos(a) * 4 * 0.6
                d.polygon([(tx, ty), (bx + nx, by + ny), (bx - nx, by - ny)], fill=RA2_LINE,
                          outline=(0, 0, 0))  # fmt: skip


def render(out: Path) -> int:
    import subprocess

    from PIL import Image, ImageDraw

    live = _live(out)
    live_t = np.array([m["t_mono_ns"] for m in live])
    gx, gy, _, _ = r.game_region()
    dw, dh = r.desktop()
    frames = _frames(out)
    (out / "png").mkdir(exist_ok=True)
    drawn = 0
    for k, (t, f) in enumerate(frames):
        img = Image.fromarray(np.ascontiguousarray(_load(f)[..., ::-1]))
        d = ImageDraw.Draw(img)
        m = _nearest(live, live_t, t)
        if m and m["points"]:
            to = lambda p: ((p["x"] * dw) - gx, (p["y"] * dh) - gy)  # noqa: E731
            ra2(d, m, to, t)
            drawn += 1
        img.save(out / "png" / f"{k:05d}.png")
    ts = np.array([t for t, _ in frames])
    fps = 1e9 / float(np.median(np.diff(ts))) if len(ts) > 1 else REC_HZ
    mp4 = out / "route-demo.mp4"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-framerate", f"{fps:.2f}", "-i",
                    str(out / "png" / "%05d.png"), "-pix_fmt", "yuv420p", str(mp4)],
                   check=True)  # fmt: skip
    print(json.dumps({"frames": len(frames), "with_route": drawn, "fps": round(fps, 1),
                      "video": str(mp4), "check": check(out, frames, live, live_t)}))  # fmt: skip
    return 0


def check(out: Path, frames: list[tuple[int, Path]], live: list[dict[str, Any]],
          live_t: np.ndarray) -> dict[str, Any]:  # fmt: skip
    """Per frame: the scene's scroll from the previous frame, the goal ring's move (GLUED = the
    same), and the feet measured on the frame against the drawn line's start (FEET). Walking = the
    scene scrolls >= 1 px, or the feet are off their rest point by > 3 px. A frame pair drawn with
    the SAME message is skipped for GLUED: it measures the preview's rate, not its gluing."""
    gx, gy, _, _ = r.game_region()
    dw, dh = r.desktop()
    anchor = (640.75, 361.89)  # the camera model's projection of our own cell (client px)

    def px(p: dict[str, Any]) -> tuple[float, float]:
        return (p["x"] * dw - gx, p["y"] * dh - gy)

    rows: list[dict[str, Any]] = []
    prev = None
    for t, f in frames:
        img = _load(f)
        m = _nearest(live, live_t, t)
        feet = rp.find_feet(img, anchor)
        shift = rp.scene_shift(prev, img) if prev is not None else None
        start = next((px(p) for p in m["points"] if p["kind"] == "feet"), None) if m else None
        goal = next((px(p) for p in m["points"] if p["kind"] == "goal"), None) if m else None
        sx, sy = (None, None) if shift is None else (round(shift[0], 1), round(shift[1], 1))
        age = None if m is None else round((t - m["t_mono_ns"]) / 1e6, 1)
        rows.append({"t_ms": t // 1_000_000, "shift_x": sx, "shift_y": sy, "feet": feet,
                     "line_start": start, "goal": goal, "msg_age_ms": age,
                     "msg_t": None if m is None else m["t_mono_ns"]})  # fmt: skip
        prev = img
    walking = [False] * len(rows)
    for i, w in enumerate(rows):
        sh = (w["shift_x"] or 0.0, w["shift_y"] or 0.0)
        off = math_dist(w["feet"], anchor) if w["feet"] else 0.0
        walking[i] = bool((w["shift_x"] is not None and np.hypot(*sh) >= 1.0) or off > 3.0)
        w["walking"] = walking[i]
        w["feet_to_line_px"] = (round(math_dist(w["feet"], w["line_start"]), 1)
                                if w["feet"] and w["line_start"] else None)  # fmt: skip
        same_msg = i and w["msg_t"] is not None and w["msg_t"] == rows[i - 1]["msg_t"]
        if i and w["goal"] and rows[i - 1]["goal"] and w["shift_x"] is not None and not same_msg:
            gdx = w["goal"][0] - rows[i - 1]["goal"][0]
            gdy = w["goal"][1] - rows[i - 1]["goal"][1]
            w["ring_err_px"] = round(float(np.hypot(gdx - w["shift_x"], gdy - w["shift_y"])), 1)
        else:
            w["ring_err_px"] = None
    with open(out / "frames.csv", "w", newline="") as fh:
        cols = ["t_ms", "walking", "shift_x", "shift_y", "feet_to_line_px", "ring_err_px",
                "msg_age_ms", "feet", "line_start", "goal"]  # fmt: skip
        wr = csv.DictWriter(fh, fieldnames=cols)
        wr.writeheader()
        for w in rows:
            wr.writerow({k: w.get(k) for k in cols})

    def q(xs: list[float]) -> dict[str, Any]:
        if not xs:
            return {"n": 0}
        a = np.array(xs, dtype=float)
        med, p95 = round(float(np.median(a)), 1), round(float(np.percentile(a, 95)), 1)
        return {"n": len(a), "median": med, "p95": p95, "max": round(float(a.max()), 1)}

    corrections, prev_c = [], None  # the camera's correction at each stop (eased in, not drawn)
    for m in live:
        me = m.get("measured") or {}
        if me.get("snapped") and prev_c is not None and me.get("c") is not None:
            corrections.append(float(np.hypot(me["c"][0] - prev_c[0], me["c"][1] - prev_c[1])))
        if me.get("c") is not None:
            prev_c = me["c"]
    sel = lambda key, walk: [w[key] for w in rows if w[key] is not None and w["walking"] == walk]  # noqa: E731
    return {"walking_feet_to_line_px": q(sel("feet_to_line_px", True)),
            "standing_feet_to_line_px": q(sel("feet_to_line_px", False)),
            "walking_ring_error_px": q(sel("ring_err_px", True)),
            "standing_ring_error_px": q(sel("ring_err_px", False)),
            "stop_corrections_cells": q(corrections),
            "walking_frames": int(sum(walking)), "frames_csv": str(out / "frames.csv")}  # fmt: skip


def math_dist(a: Any, b: Any) -> float:
    return float(np.hypot(a[0] - b[0], a[1] - b[1]))


def scene_shift(a: np.ndarray, b: np.ndarray) -> tuple[float, float]:
    """Kept for callers of the first version: the preview's own measurement."""
    return rp.scene_shift(a, b)


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
