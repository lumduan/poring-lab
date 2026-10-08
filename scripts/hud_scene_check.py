#!/usr/bin/env python3
"""Acceptance for the HUD SCENE (Batt 2026-10-08): replay the scene process's log exactly as a
console receives it, over recorded frames.

    hud_scene_check.py rate --from T0 --to T1            messages per minute by type (idle ~0)
    hud_scene_check.py render FRAMES_DIR [--latency-ms 100]   an MP4 + a still, the scene drawn
    hud_scene_check.py offsets FRAMES_DIR [--threads 4]  box-to-sprite foot offsets per frame
    hud_scene_check.py truth FRAMES_DIR...               the sim's per-frame caches (detector: slow)
    hud_scene_check.py rescore FRAMES_DIR [--log L]      a live log, scored as `sim` (cached truth)
    hud_scene_check.py sim FRAMES_DIR [--variants a,b]   the scene process OFFLINE, per variant
    hud_scene_check.py simtable DIR... [--variants a,b]  ... over recordings, offsets pooled

- **Frames:** `<k>-<t_mono_ns>.jpg` (route_demo's recorder). A frame's time is its bus capture time,
  the same clock as the scene's messages.
- **The console's view of a frame at time t:** every message LOGGED by t + latency (it has arrived),
  and the frame's own motion offset (exact by time, else the latest at or before it).
- **offsets:** on every frame, each drawn unit box against the SAME detector run offline on that
  frame (the nearest foot of that class, within 120 px). Reported by class, walking and standing
  apart (walking = the scene moved >= 1 px since the previous recorded frame; `:exact` = the scene
  process saw that very frame, `:between` = the console drew it with an older motion).
- **truth / rescore / sim** (2026-10-08 night, scripts/hud_scene_sim.py): the detector and the
  motion features cached once per recording in RAM; `sim` runs hud_scene.py's own tracker over the
  recorded frames at their recorded times and scores what a console would draw, per variant
  (walking = the scene moved >= 1 px since the previous recorded frame; `rescore` scores a live
  log the same way, so the two compare).
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


def load_log(t0: int | None = None, t1: int | None = None, log: Path = LOG) -> list[dict[str, Any]]:
    rows = []
    for path in (log.with_suffix(".jsonl.1"), log):
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
    import hud_scene as hs
    import route_preview as rpv
    import unit_detector
    from PIL import Image

    fs = frames(d)
    log = load_log(fs[0][0] - int(60e9), fs[-1][0] + int(5e9))
    sent = {e["msg"]["t_mono_ns"] for e in log}  # the frames the scene process itself saw
    rp = Replay(log)
    gx, gy, _, _ = r.game_region()
    dw, dh = r.desktop()
    det = unit_detector.UnitDetector(threads=threads)
    per: dict[str, list[float]] = {}
    prev: np.ndarray | None = None
    try:
        for t, f in fs:
            rp.advance(t + int(latency_ms * 1e6))
            img = np.asarray(Image.open(f).convert("RGB"))[..., ::-1]
            # walking = THIS frame moved since the previous recorded one (the band-passed scroll).
            # The first cut asked "did the process send a motion for this exact frame", which
            # filed every walking frame between the process's own frames as standing (2026-10-08
            # night: 83 walking samples of ~290). `:between` = the console used an older motion.
            moved = prev is not None and math.hypot(*rpv.scene_shift(prev, img, **hs.SHARP_SHIFT))
            prev = img
            drawn = [o for o in rp.boxes(t, dw, dh, gx, gy) if o["kind"] == "unit"]
            if not drawn:
                continue
            found = det.detect(img)
            state = "standing"
            if moved and moved >= 1.0:
                state = "walking:exact" if t in sent else "walking:between"
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


REGION, DESKTOP = (80, 77, 1280, 720), (1440, 900)  # the recordings' (sim: no .env, no backend)


def _table(rows: list[tuple[str, dict[str, Any]]]) -> str:
    """One line per variant: offsets per class x state (median / p95 / max, n), doubled boxes,
    message rates and the detector's cores."""
    keys = sorted({k for _, rep in rows for k in rep["score"]["offsets"]})
    out = []
    for name, rep in rows:
        sc = rep["score"]
        cells = []
        for k in keys:
            st = sc["offsets"].get(k, {"n": 0})
            cells.append(f"{k} " + (f"{st['median_px']}/{st['p95_px']}/{st['max_px']} n{st['n']}"
                                    if st["n"] else "-"))  # fmt: skip
        rt = rep.get("rates", {})
        mv, still = rt.get("moving", {}), rt.get("still", {})
        cost = rep.get("cost", {})
        out.append(
            f"{name:16s} " + " | ".join(cells)
            + f" | doubled {sc['doubled']} ({sc['doubled_frames']} fr) ghosts {sc['ghosts']}"
            + (f" | msgs/min moving {sum(mv.get('per_minute', {}).values()):.0f} "
               f"(moves {mv.get('moves_per_minute', 0)}), still deltas "
               f"{still.get('per_minute', {}).get('hud_delta', 0)}" if rt else "")
            + (f" | det cores moving {cost['moving']['cores']} still {cost['still']['cores']}"
               if cost else "")
        )  # fmt: skip
    return "\n".join(out)


def truth(dirs: list[Path], threads: int) -> int:
    import hud_scene_sim as sim

    for d in dirs:
        print(sim.build_motion(d), flush=True)
        print(sim.build_truth(d, threads=threads), flush=True)
    return 0


def rescore(d: Path, log_path: Path, latency_ms: float) -> int:
    import hud_scene_sim as sim

    cache = sim.load_cache(d)
    t = cache["truth"]["t"]
    log = load_log(int(t[0]) - int(60e9), int(t[-1]) + int(5e9), log_path)
    hud_times = {e["msg"]["t_mono_ns"] for e in log}  # the frames the live process saw (logged)
    sc = sim.score(log, cache, REGION, DESKTOP, latency_ms, hud_times=hud_times)
    rep = {"score": {k: x for k, x in sc.items() if k != "raw"}, "rates": sim.rates(log, cache)}
    print(_table([("live", rep)]))
    out = sim.cache_dir(d) / "rescore-live.json"
    out.write_text(json.dumps(rep, indent=1))
    print(out)
    return 0


def run_sim(
    d: Path, names: list[str], latency_ms: float, grab_from: Path | None, console: str = "hold"
) -> int:
    import hud_scene_sim as sim

    cache = sim.load_cache(d)
    reg = sim.variants()
    grab: Any = sim.LIVE_GRAB_MS
    if grab_from is not None:  # the live process's own frame -> motion message latencies
        ls = [(e["logged_ns"] - e["msg"]["t_mono_ns"]) / 1e6 for e in load_log(log=grab_from)
              if e["msg"]["type"] == "hud_motion"]  # fmt: skip
        grab = ls or grab
    rows = []
    for name in names:
        v = reg[name]
        res = sim.simulate(d, cache, v, REGION, DESKTOP, grab_ms=grab)
        hud_times = {int(cache["truth"]["t"][k]) for k in res["hud_frames"]}
        between = hud_times if v.hud_every > 1 else None
        sc = sim.score(res["log"], cache, REGION, DESKTOP, latency_ms, hud_times=between,
                       console=console)  # fmt: skip
        rep = {
            "score": {k: x for k, x in sc.items() if k != "raw"},
            "rates": sim.rates(res["log"], cache),
            "cost": sim.det_cost(res["runs"], cache),
            "motion_source": res["motion_source"],
        }
        rows.append((name, rep))
        tag = name.replace("/", "_") + ("" if console == "hold" else f"-{console}")
        (sim.cache_dir(d) / f"sim-{tag}.json").write_text(json.dumps(rep, indent=1))
        print(_table([(name, rep)]), flush=True)
    return 0


def simtable(dirs: list[Path], names: list[str], latency_ms: float, grab_from: Path | None) -> int:
    """The variants over several recordings: one row per recording and variant, and the offsets
    POOLED over the recordings (the raw distances, not an average of medians)."""
    import hud_scene_sim as sim

    reg = sim.variants()
    grab: Any = sim.LIVE_GRAB_MS
    if grab_from is not None:
        ls = [(e["logged_ns"] - e["msg"]["t_mono_ns"]) / 1e6 for e in load_log(log=grab_from)
              if e["msg"]["type"] == "hud_motion"]  # fmt: skip
        grab = ls or grab
    pooled: dict[str, dict[str, Any]] = {}
    out: dict[str, Any] = {"recordings": {}, "pooled": {}}
    for d in dirs:
        cache = sim.load_cache(d)
        name_d = sim.cache_dir(d).name
        out["recordings"][name_d] = {}
        for name in names:
            v = reg[name]
            if v.preview and sim.preview_track(d) is None:
                continue
            res = sim.simulate(d, cache, v, REGION, DESKTOP, grab_ms=grab)
            hud_times = {int(cache["truth"]["t"][k]) for k in res["hud_frames"]}
            between = hud_times if v.hud_every > 1 else None
            sc = sim.score(res["log"], cache, REGION, DESKTOP, latency_ms, hud_times=between)
            rep = {"score": {k: x for k, x in sc.items() if k != "raw"},
                   "rates": sim.rates(res["log"], cache),
                   "cost": sim.det_cost(res["runs"], cache)}  # fmt: skip
            out["recordings"][name_d][name] = rep
            print(_table([(f"{name_d[9:]} {name}", rep)]), flush=True)
            p = pooled.setdefault(name, {"raw": {}, "doubled": 0, "ghosts": 0, "frames": 0})
            for key, ds in sc["raw"].items():
                p["raw"].setdefault(key, []).extend(ds)
            p["doubled"] += sc["doubled"]
            p["ghosts"] += sum(sc["ghosts"].values())
            p["frames"] += sc["frames"]
    print("POOLED")
    for name, p in pooled.items():
        st = {key: sim._stat(ds) for key, ds in sorted(p["raw"].items())}
        out["pooled"][name] = {"offsets": st, "doubled": p["doubled"], "ghosts": p["ghosts"],
                               "frames": p["frames"]}  # fmt: skip
        cells = " | ".join(f"{k} {x['median_px']}/{x['p95_px']}/{x['max_px']} n{x['n']}"
                           for k, x in st.items() if x["n"])  # fmt: skip
        print(f"{name:18s} {cells} | doubled {p['doubled']} ghosts {p['ghosts']}")
    path = sim.CACHE_DIR / "simtable.json"
    path.write_text(json.dumps(out, indent=1))
    print(path)
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
    tr = sub.add_parser("truth")
    tr.add_argument("dirs", type=Path, nargs="+")
    tr.add_argument("--threads", type=int, default=2)
    rs = sub.add_parser("rescore")
    rs.add_argument("dir", type=Path)
    rs.add_argument("--log", type=Path, default=LOG)
    rs.add_argument("--latency-ms", type=float, default=100.0)
    sm = sub.add_parser("sim")
    sm.add_argument("dir", type=Path)
    sm.add_argument("--variants", default="first-cut,chosen")
    sm.add_argument("--latency-ms", type=float, default=100.0)
    sm.add_argument("--grab-from", type=Path, default=None,
                    help="a live scene log: sample its frame -> motion latencies")  # fmt: skip
    sm.add_argument("--console", choices=("hold", "extrapolate"), default="hold",
                    help="hold = scene.ts today; extrapolate = a parked option")  # fmt: skip
    st = sub.add_parser("simtable")
    st.add_argument("dirs", type=Path, nargs="+")
    st.add_argument("--variants", default="first-cut,chosen")
    st.add_argument("--latency-ms", type=float, default=100.0)
    st.add_argument("--grab-from", type=Path, default=None)
    x = ap.parse_args()
    if x.cmd == "simtable":
        return simtable(x.dirs, x.variants.split(","), x.latency_ms, x.grab_from)
    if x.cmd == "rate":
        return rate(x.t0, x.t1)
    if x.cmd == "truth":
        return truth(x.dirs, x.threads)
    if x.cmd == "rescore":
        return rescore(x.dir, x.log, x.latency_ms)
    if x.cmd == "sim":
        return run_sim(x.dir, x.variants.split(","), x.latency_ms, x.grab_from, x.console)
    return (
        render(x.dir, x.latency_ms)
        if x.cmd == "render"
        else offsets(x.dir, x.latency_ms, x.threads)
    )


if __name__ == "__main__":
    sys.exit(main())
