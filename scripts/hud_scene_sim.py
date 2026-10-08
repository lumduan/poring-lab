#!/usr/bin/env python3
"""The HUD SCENE's offline simulator (2026-10-08 night): hud_scene.py's own per-frame logic over
RECORDED frames, so variants of its motion model, detector cadence and matching can be compared
on the same walk, cheaply.

    hud_scene_check.py truth DIR      the per-frame caches, once per recording (detector: slow)
    hud_scene_check.py sim DIR ...    one variant: its message stream, scored like `offsets`

- **Truth** (`truth.npz`): the unit detector (2 threads, as live) and the signboard finder on EVERY
  recorded frame, plus how long each took. The sim's detector passes READ it (a pass on frame k
  returns frame k's boxes, after that frame's measured detect time), and the score uses it as each
  frame's truth -- as `hud_scene_check.py offsets` does with a live run.
- **Motion** (`motion.npz`): per consecutive pair of recorded frames, the motion features the scene
  process computes live (the global phase correlation; the floor patches around it), and the
  frame-change signal the detector's cadence uses.
- Both live in RAM (CACHE_DIR, /dev/shm): recorded frames are client-derived and stay where they
  are; nothing here is ever committed.

The frames are `<k>-<t_mono_ns>.jpg` (route_demo's recorder, ~10 Hz on the bus) or `.npy` (raw).
"""

from __future__ import annotations

import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

CACHE_DIR = Path(os.environ.get("HUD_SIM_CACHE", "/dev/shm/poring-lab-tmp/hud-sim"))
CLASSES = ("player", "monster", "npc")
GRAY_DOWN = 8  # hud_scene.frame_changed's downsampling


def frames(d: Path) -> list[tuple[int, Path]]:
    """`<k>-<t_mono_ns>.jpg` (route_demo's recorder), or `.npy` (raw BGR, the 12:33 recording)."""
    fs = sorted(d.glob("*.jpg")) or sorted(d.glob("*.npy"))
    return [(int(f.stem.split("-")[1]), f) for f in fs]


def load_bgr(path: Path) -> np.ndarray:
    if path.suffix == ".npy":
        return np.ascontiguousarray(np.load(path)[..., :3])
    from PIL import Image

    return np.ascontiguousarray(np.asarray(Image.open(path).convert("RGB"))[..., ::-1])


def cache_dir(d: Path) -> Path:
    """One cache directory per recording, named after it (route-demo/<stamp> -> <stamp>)."""
    name = d.parent.name if d.name == "frames" else d.name
    return CACHE_DIR / name


# --- the caches --------------------------------------------------------------------------------
def build_truth(d: Path, threads: int = 2, log_every: int = 100) -> Path:
    """The detector and the signboard finder on every frame (resumable: a partial cache is kept)."""
    import route_preview as rp
    import unit_detector

    from poring_env.signboard import find_signs

    out = cache_dir(d) / "truth.npz"
    out.parent.mkdir(parents=True, exist_ok=True)
    fs = frames(d)
    ts = np.array([t for t, _ in fs], dtype=np.int64)
    units: list[list[float]] = []
    signs: list[list[float]] = []
    det_ms = np.full(len(fs), np.nan)
    sign_ms = np.full(len(fs), np.nan)
    start = 0
    part = out.with_suffix(".part.npz")
    if part.exists():
        z = np.load(part)
        if len(z["t"]) == len(ts) and (z["t"] == ts).all():
            units = z["units"].tolist()
            signs = z["signs"].tolist()
            det_ms, sign_ms = z["det_ms"], z["sign_ms"]
            start = int(z["done"])

    def save(path: Path, done: int) -> None:
        np.savez(path, t=ts, units=np.array(units, dtype=float).reshape(-1, 7),
                 signs=np.array(signs, dtype=float).reshape(-1, 5), det_ms=det_ms,
                 sign_ms=sign_ms, done=done)  # fmt: skip

    det = unit_detector.UnitDetector(threads=threads)
    t_start = time.monotonic()
    try:
        for k in range(start, len(fs)):
            img = load_bgr(fs[k][1])
            t0 = time.monotonic()
            boxes = det.detect(img)
            det_ms[k] = 1000 * (time.monotonic() - t0)
            for b in boxes:
                units.append([k, b.x0, b.y0, b.x1, b.y1, b.score, CLASSES.index(b.cls)])
            npcs = [(b.x0, b.y0, b.x1, b.y1) for b in boxes if b.cls == "npc"]
            t0 = time.monotonic()
            for s in find_signs(img, npcs=npcs, exclude=rp.UI_WINDOWS):
                sb = s.box
                signs.append([k, sb.x0, sb.y0, sb.x1 + 1, sb.y1 + 1])  # as hud_scene sends it
            sign_ms[k] = 1000 * (time.monotonic() - t0)
            if (k + 1) % log_every == 0:
                el = time.monotonic() - t_start
                print(f"{time.strftime('%H:%M:%S')} {d}: {k + 1}/{len(fs)} "
                      f"({el / (k + 1 - start):.2f} s/frame)", flush=True)  # fmt: skip
                save(part, k + 1)
    finally:
        det.close()
    save(out, len(fs))
    part.unlink(missing_ok=True)
    return out


def build_motion(d: Path, log_every: int = 200) -> Path:
    """Per consecutive pair of frames: the global shift (route_preview.scene_shift: the first cut's
    plain one, and the HUD's band-passed one, `_hp`), each floor patch's shift around each
    (route_preview.patch_shifts), and the 1/8 gray frames for the detector cadence."""
    import hud_scene as hs
    import route_preview as rp

    out = cache_dir(d) / "motion.npz"
    out.parent.mkdir(parents=True, exist_ok=True)
    fs = frames(d)
    n, npatch = len(fs), len(rp.PATCHES)
    shift, shift_hp = np.zeros((n, 2)), np.zeros((n, 2))
    pshift = np.full((n, npatch, 2), np.nan)
    pshift_hp = np.full((n, npatch, 2), np.nan)
    pq, pq_hp = np.zeros((n, npatch)), np.zeros((n, npatch))
    gray8: np.ndarray | None = None
    prev: np.ndarray | None = None
    prev_g: np.ndarray | None = None
    for k, (_, f) in enumerate(fs):
        img = load_bgr(f)
        g8 = img[::GRAY_DOWN, ::GRAY_DOWN, :3].astype(np.float32).mean(-1)
        if gray8 is None:
            gray8 = np.zeros((n, *g8.shape), dtype=np.float16)
        gray8[k] = g8
        g = rp.gray(img)
        if prev is not None and prev_g is not None:
            for kw, sh, ps_, pq_ in ((None, shift, pshift, pq),
                                     (hs.SHARP_SHIFT, shift_hp, pshift_hp, pq_hp)):  # fmt: skip
                s = rp.scene_shift(prev, img, **(kw or {}))
                sh[k] = s
                idx, ps, q = rp.patch_shifts(prev_g, g, s)
                for i, v, qq in zip(idx, ps, q, strict=True):
                    ps_[k, i] = v
                    pq_[k, i] = qq
        prev, prev_g = img, g
        if (k + 1) % log_every == 0:
            print(f"{time.strftime('%H:%M:%S')} motion {d}: {k + 1}/{n}", flush=True)
    np.savez(out, t=np.array([t for t, _ in fs], dtype=np.int64), shift=shift, pshift=pshift,
             pq=pq, shift_hp=shift_hp, pshift_hp=pshift_hp, pq_hp=pq_hp,
             gray8=gray8 if gray8 is not None else np.zeros((0, 1, 1)))  # fmt: skip
    return out


def load_cache(d: Path) -> dict[str, Any]:
    c = cache_dir(d)
    z: dict[str, Any] = {}
    for name in ("truth", "motion"):
        p = c / f"{name}.npz"
        if not p.exists():
            raise FileNotFoundError(f"{p} missing: run `hud_scene_check.py truth {d}` first")
        with np.load(p) as f:
            z[name] = {k: f[k] for k in f.files}
    if not (z["truth"]["t"] == z["motion"]["t"]).all():
        raise ValueError(f"{c}: the truth and motion caches are of different frames")
    return z


# --- the simulation ----------------------------------------------------------------------------
LIVE_DET_MS = 590.0  # the live detector + signboards per pass at 2 threads (20:10-20:13 median)
LIVE_GRAB_MS = 76.0  # the live frame -> logged motion message (20:09 walk median, p95 102)
POLL_S = 0.1  # the detector thread's wait when nothing is due (hud_scene.serve)


@dataclass(frozen=True)
class Variant:
    """One way to run the scene process over a recording."""

    name: str
    tuning: Any = None  # a hud_scene.Tuning; None = the first cut's own code (LEGACY_SOURCE)
    hud_every: int = 1  # the scene process sees every k-th recorded frame (the rest are between)
    preview: bool = False  # the route previewer's camera (live.jsonl) while it has one
    det_ms: float | None = LIVE_DET_MS  # every pass's time (None: the cached per-frame times)


def variants() -> dict[str, Variant]:
    """The named variants (`hud_scene_check.py sim --variants a,b`). `first-cut` runs the deployed
    code itself; `legacy` is the new code with the first cut's behaviour (a cross-check)."""
    from dataclasses import replace

    import hud_scene as hs

    lg, best = hs.LEGACY, hs.TUNING
    dd = {"dedupe_px": best.dedupe_px, "dedupe_iou": best.dedupe_iou,
          "misses_moving": best.misses_moving}  # fmt: skip
    vs = [
        Variant("first-cut"),
        Variant("legacy", lg),
        Variant("det0.5", replace(lg, det_moving_s=0.5)),
        Variant("det0.25", replace(lg, det_moving_s=0.25)),
        Variant("dedupe", replace(lg, **dd)),  # type: ignore[arg-type]
        Variant("floor", replace(lg, motion="floor")),
        Variant("floor+dedupe", replace(lg, motion="floor", **dd)),  # type: ignore[arg-type]
        Variant("floor+det0.5", replace(lg, motion="floor", det_moving_s=0.5)),
        Variant("sharp", replace(lg, sharp=True)),
        Variant("chosen", best),
        Variant("chosen+preview", best, preview=True),
        # ablations: each part of `chosen` taken back out, and its thresholds
        Variant("chosen-plain-shift", replace(best, sharp=False)),
        Variant("chosen-global", replace(best, motion="global")),
        Variant("chosen-det1.0", replace(best, det_moving_s=1.0)),
        Variant("chosen-no-dedupe", replace(best, dedupe_px=0.0, dedupe_iou=0.0, misses_moving=2)),
        Variant("chosen-fine1.5", replace(best, fine_px=1.5)),
        Variant("chosen-fine4", replace(best, fine_px=4.0)),
        Variant("chosen-resid2", replace(best, resid_px=2.0)),
        Variant("chosen-resid1", replace(best, resid_px=1.0)),
        Variant("chosen-no-unclip", replace(best, unclip=False)),
        Variant("first-cut/2", hud_every=2),
        Variant("chosen/2", best, hud_every=2),
    ]
    return {v.name: v for v in vs}


def _legacy_module() -> Any:
    """hud_scene.py as first deployed (5b189c2), for the 'before' row: $HUD_LEGACY_SOURCE, else
    git."""
    import importlib.util
    import subprocess

    src = os.environ.get("HUD_LEGACY_SOURCE")
    if src is None:
        root = Path(__file__).resolve().parents[1]
        code = subprocess.run(["git", "-C", str(root), "show", "5b189c2:scripts/hud_scene.py"],
                              check=True, capture_output=True, text=True).stdout  # fmt: skip
        tmp = CACHE_DIR / "hud_scene_5b189c2.py"  # RAM, next to the caches
        tmp.parent.mkdir(parents=True, exist_ok=True)
        tmp.write_text(code)
        src = str(tmp)
    spec = importlib.util.spec_from_file_location("hud_scene_5b189c2", src)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["hud_scene_5b189c2"] = mod
    spec.loader.exec_module(mod)
    return mod


def found_on(cache: dict[str, Any], k: int) -> list[dict[str, Any]]:
    """Frame k's detections as the scene process's detector thread hands them over."""
    tr = cache["truth"]
    u = tr["units"][tr["units"][:, 0] == k]
    s = tr["signs"][tr["signs"][:, 0] == k]
    found = [{"kind": "unit", "cls": CLASSES[int(r[6])], "conf": float(r[5]),
              "box": [float(v) for v in r[1:5]]} for r in u if int(r[6]) != 0]  # fmt: skip
    found += [{"kind": "sign", "cls": "sign", "conf": None,
               "box": [float(v) for v in r[1:5]]} for r in s]  # fmt: skip
    return found


def preview_track(d: Path) -> tuple[np.ndarray, np.ndarray] | None:
    """The route previewer's camera over time (live.jsonl next to the frames): (t ns, c cells)."""
    import json

    p = (d.parent if d.name == "frames" else d) / "live.jsonl"
    if not p.exists():
        return None
    ts, cs = [], []
    for line in p.read_text().splitlines():
        m = json.loads(line).get("measured") or {}
        if m.get("c") is not None and m.get("t"):
            ts.append(int(m["t"]))
            cs.append(m["c"])
    if not ts:
        return None
    o = np.argsort(ts)
    return np.asarray(ts, dtype=np.int64)[o], np.asarray(cs, dtype=float)[o]


def preview_to_ground(ground: Any) -> np.ndarray:
    """The previewer's cells (the map's camera: the indoor yaw and distance) -> the Ground's: a
    rotation and a scale, exact on a flat floor (both cameras share pitch, FOV and centre)."""
    import json

    import hud_scene as hs

    from poring_dataset import camera as cam

    cj = json.loads(hs.CAMERA_JSON.read_text())
    table = cam.load_indoor_table(cam.GAT_DIR)
    mc = cam.map_camera(cj, "prt_church", table)  # every recording here is prt_church (indoor)
    gp = hs.Ground(mc)
    jp = gp.flow(gp.to_floor([gp.target]), np.zeros(2))[1][0]
    jg = ground.flow(ground.to_floor([ground.target]), np.zeros(2))[1][0]
    return np.asarray(np.linalg.solve(jg, jp))


def _preview_c(track: tuple[np.ndarray, np.ndarray], t: int, gap_ns: int = 250_000_000
               ) -> np.ndarray | None:  # fmt: skip
    ts, cs = track
    i = int(np.searchsorted(ts, t))
    if i == 0 or i >= len(ts) or ts[i] - ts[i - 1] > gap_ns:
        return None
    f = (t - ts[i - 1]) / max(1, ts[i] - ts[i - 1])
    return np.asarray(cs[i - 1] + f * (cs[i] - cs[i - 1]))


class _LegacyCadence:
    """The first cut's detector cadence: det_period while the frame changed, else 5 s."""

    def __init__(self, mod: Any) -> None:
        self.mod, self.last_run, self.last_gray = mod, -1e18, None
        self.last_motion = -1e18

    def moving(self, now: float) -> bool:
        return False

    def due(self, now: float, g8: np.ndarray) -> bool:
        import hud_scene as hs

        changed = hs.frame_changed_gray(self.last_gray, g8)
        return now - self.last_run >= (self.mod.DET_PERIOD_S if changed else self.mod.DET_IDLE_S)

    def ran(self, now: float, g8: np.ndarray) -> None:
        self.last_run, self.last_gray = now, g8


def simulate(d: Path, cache: dict[str, Any], v: Variant, region: tuple[int, int, int, int],
             desktop: tuple[int, int], grab_ms: Any = LIVE_GRAB_MS, seed: int = 0
             ) -> dict[str, Any]:  # fmt: skip
    """The scene process over the recording: its message log (logged_ns + msg, as SCENE_LOG), the
    frames it processed, and its detector's work."""
    import hud_scene as hs
    import route_preview as rp

    tr, mo = cache["truth"], cache["motion"]
    t = tr["t"]
    n = len(t)
    windows = [tuple(w) for w in rp.UI_WINDOWS]
    legacy = v.tuning is None
    mod = _legacy_module() if legacy else hs
    ground = hs.load_ground() if not legacy and v.tuning.motion == "floor" else None
    floor = hs.FloorMotion(ground) if ground is not None else None
    if legacy:
        tracker = mod.SceneTracker(region, desktop, windows)
        cadence: Any = _LegacyCadence(mod)
    else:
        tracker = hs.SceneTracker(region, desktop, windows, ground, v.tuning)  # type: ignore[arg-type]
        cadence = hs.Cadence(v.tuning)
    track = preview_track(d) if v.preview else None
    to_g = preview_to_ground(ground) if track is not None and ground is not None else None
    rng = np.random.default_rng(seed)
    lat = np.atleast_1d(np.asarray(grab_ms, dtype=float))
    log: list[dict[str, Any]] = []
    hud = list(range(0, n, max(1, v.hud_every)))
    det_check = -1
    pending: tuple[int, int, Any] | None = None
    latest: tuple[int, Any] | None = None
    runs: list[tuple[int, float]] = []  # (pickup ns, pass ms)
    t_key = -(10**18)
    used = {"preview": 0, "patches": 0, "shift": 0}

    def detector_until(p: int) -> None:
        nonlocal det_check, pending
        while True:
            if pending is not None:
                done, k, ref = pending
                if done > p:
                    return
                found = found_on(cache, k)
                if legacy:
                    delta = tracker.observe(found, ref)
                else:
                    delta = tracker.observe(found, ref, moving=cadence.moving(done / 1e9))
                if delta is not None:
                    log.append({"logged_ns": done, "msg": {"type": "hud_delta",
                                "t_mono_ns": int(t[k]), "frame_id": k, **delta}})  # fmt: skip
                det_check, pending = done, None
                continue
            if latest is None or det_check > p:
                return
            k, ref = latest
            g8 = mo["gray8"][k]
            if cadence.due(det_check / 1e9, g8):
                ms = v.det_ms if v.det_ms is not None else tr["det_ms"][k] + tr["sign_ms"][k]
                pending = (det_check + int(ms * 1e6), k, ref)
                runs.append((det_check, float(ms)))
                cadence.ran(det_check / 1e9, g8)
            else:
                det_check += int(POLL_S * 1e9)

    sharp = not legacy and v.tuning.sharp
    sfx = "_hp" if sharp else ""
    if sharp and "shift_hp" not in mo:
        raise ValueError("motion cache without the band-passed shift: rebuild it (truth --motion)")
    m_shift, m_ps, m_pq = mo["shift" + sfx], mo["pshift" + sfx], mo["pq" + sfx]
    prev_k: int | None = None
    for k in hud:
        p = int(t[k] + 1e6 * float(lat[rng.integers(len(lat))]))
        detector_until(p)
        if det_check < 0:
            det_check = p
        msgs: list[dict[str, Any]] = []
        if prev_k is not None:
            ks = range(prev_k + 1, k + 1)
            shift = m_shift[list(ks)].sum(0)
            dc = None
            if floor is not None and float(np.hypot(*shift)) >= hs.MOTION_MIN_PX:
                c0 = _preview_c(track, int(t[prev_k])) if track is not None else None
                c1 = _preview_c(track, int(t[k])) if track is not None else None
                if c0 is not None and c1 is not None and to_g is not None:
                    dc = to_g @ (c1 - c0)
                    used["preview"] += 1
                else:
                    dc = np.zeros(2)
                    for j in ks:
                        idx = np.nonzero(~np.isnan(m_ps[j, :, 0]))[0]
                        dj = floor.from_patches(idx, m_ps[j, idx], m_pq[j, idx])
                        used["patches" if dj is not None else "shift"] += 1
                        dc = dc + (floor.from_shift(m_shift[j]) if dj is None else dj)
            if legacy:
                moved, delta = tracker.motion(tuple(shift)), None
            else:
                moved, delta = tracker.on_frame(shift, dc)
            msgs = hs.frame_messages(tracker, int(t[k]), k, moved, delta)
            if moved:
                cadence.last_motion = p / 1e9
        if p - t_key >= int(hs.KEYFRAME_S * 1e9):
            t_key = p
            msgs.append({"type": "hud_scene", "t_mono_ns": int(t[k]), "frame_id": k,
                         **tracker.keyframe()})  # fmt: skip
        log += [{"logged_ns": p, "msg": m} for m in msgs]
        latest = (k, tracker.ref() if not legacy else tracker.offset.copy())
        prev_k = k
    detector_until(int(t[-1] + 5e9))
    log.sort(key=lambda e: e["logged_ns"])  # stable: a frame's messages keep their order
    return {"log": log, "hud_frames": hud, "runs": runs, "motion_source": used}


# --- the score ---------------------------------------------------------------------------------
def walking_mask(mo: dict[str, Any], moving_px: float = 1.0) -> np.ndarray:
    """Per recorded frame: the scene moved >= moving_px since the previous one, by the band-passed
    shift (the plain one reads ~0 on some moving frames), the same for every variant."""
    s = mo.get("shift_hp", mo["shift"])
    return np.asarray(np.hypot(s[:, 0], s[:, 1]) >= moving_px)


NEAR_PX = 120.0  # hud_scene_check.offsets: the nearest truth of the class within this
EDGE_PX = 3.0  # a truth unit box this close to the view's bottom is cut: its feet are not seen
DOUBLE_PX = 80.0  # a drawn box left over near a truth another drawn box took: a DOUBLED box


def _stat(ds: list[float]) -> dict[str, Any]:
    if not ds:
        return {"n": 0}
    a = np.sort(np.asarray(ds))
    return {"n": len(a), "median_px": round(float(a[len(a) // 2]), 1),
            "p95_px": round(float(a[int(len(a) * 0.95)]), 1),
            "max_px": round(float(a[-1]), 1)}  # fmt: skip


def extrapolated(rp: Any, t: int, cap_ns: int = 120_000_000) -> dict[str, float]:
    """A console that EXTRAPOLATES (a parked frontend option, not scene.ts today): the offset at t
    from the last two motions at or before it, by their velocity, for at most cap_ns."""
    ms = sorted(((tm, off) for tm, off in rp.motions if tm <= t), key=lambda m: m[0])
    if not ms:
        return {"x": 0.0, "y": 0.0}
    t2, o2 = ms[-1]
    if t2 == t or len(ms) < 2:
        return dict(o2)
    t1, o1 = ms[-2]
    if t2 - t1 > 2 * cap_ns or t2 == t1:
        return dict(o2)
    f = min(t - t2, cap_ns) / (t2 - t1)
    return {"x": o2["x"] + f * (o2["x"] - o1["x"]), "y": o2["y"] + f * (o2["y"] - o1["y"])}


def score(log: list[dict[str, Any]], cache: dict[str, Any], region: tuple[int, int, int, int],
          desktop: tuple[int, int], latency_ms: float = 100.0, moving_px: float = 1.0,
          hud_times: set[int] | None = None, console: str = "hold") -> dict[str, Any]:  # fmt: skip
    """Every recorded frame as a console shows it (hud_scene_check.Replay, messages logged by the
    frame's time + latency_ms) against that frame's cached detections:
    - box-to-sprite FOOT offsets per class, WALKING (the scene moved >= moving_px since the
      previous recorded frame) and STANDING, as hud_scene_check.offsets: each drawn box to the
      nearest detection of its class within NEAR_PX;
    - with ``hud_times``, walking frames split into the ones the scene process saw (`exact`) and
      the ones between them (`between`: the console uses the latest motion before it);
    - a drawn box whose nearest detection is cut by the view's bottom edge is not scored (its feet
      are past the edge; counted in `edge_skipped`);
    - DOUBLED boxes: a drawn box left over (one to one, nearest first) within DOUBLE_PX of a
      detection another drawn box took; GHOSTS: a drawn box with no detection of its class within
      NEAR_PX."""
    import hud_scene_check as hc

    tr, mo = cache["truth"], cache["motion"]
    gx, gy, gh = region[0], region[1], region[3]
    dw, dh = desktop
    rp = hc.Replay(log)
    edge = 0
    if console == "extrapolate":
        rp.offset_at = lambda tt: extrapolated(rp, tt)  # type: ignore[method-assign]
    walk = walking_mask(mo, moving_px)
    per: dict[str, list[float]] = {}
    doubled = drawn_n = 0
    ghosts: dict[str, int] = {}
    doubled_frames = 0
    for k, t in enumerate(tr["t"]):
        t = int(t)
        rp.advance(t + int(latency_ms * 1e6))
        drawn = [o for o in rp.boxes(t, dw, dh, gx, gy) if o["kind"] in ("unit", "sign")]
        if not drawn:
            continue
        found = found_on(cache, k)
        state = "walking" if walk[k] else "standing"
        if walk[k] and hud_times is not None:
            state += ":exact" if t in hud_times else ":between"
        truth: dict[str, list[tuple[float, float]]] = {}
        cut: dict[str, list[bool]] = {}
        for f in found:
            b = f["box"]
            truth.setdefault(f["cls"], []).append(((b[0] + b[2]) / 2, b[3]))
            cut.setdefault(f["cls"], []).append(f["kind"] == "unit" and b[3] >= gh - EDGE_PX)
        feet = []
        for o in drawn:
            x, y, w, h = o["px"]
            feet.append((o["cls"], (x + w / 2, y + h)))
        pairs = []
        for di, (cls, ft) in enumerate(feet):
            same = truth.get(cls, [])
            ds = [float(np.hypot(ft[0] - s[0], ft[1] - s[1])) for s in same]
            if ds and min(ds) <= NEAR_PX and cut[cls][int(np.argmin(ds))]:
                edge += 1  # its sprite is cut by the view's bottom: no feet to measure to
            elif ds and min(ds) <= NEAR_PX:
                per.setdefault(f"{cls}:{state}", []).append(min(ds))
            else:
                ghosts[cls] = ghosts.get(cls, 0) + 1
            pairs += [(dd, di, si) for si, dd in enumerate(ds) if dd <= NEAR_PX]
        pairs.sort()
        got_d: set[int] = set()
        got_s: set[tuple[str, int]] = set()
        for _, di, si in pairs:
            key = (feet[di][0], si)
            if di not in got_d and key not in got_s:
                got_d.add(di)
                got_s.add(key)
        dbl = 0
        for di, (cls, ft) in enumerate(feet):
            if di in got_d:
                continue
            for si, s in enumerate(truth.get(cls, [])):
                if (cls, si) in got_s and np.hypot(ft[0] - s[0], ft[1] - s[1]) <= DOUBLE_PX:
                    dbl += 1
                    break
        doubled += dbl
        doubled_frames += dbl > 0
        drawn_n += len(drawn)
    mins = (int(tr["t"][-1]) - int(tr["t"][0])) / 60e9
    return {"offsets": {key: _stat(ds) for key, ds in sorted(per.items())},
            "doubled": doubled, "doubled_frames": doubled_frames, "ghosts": ghosts,
            "edge_skipped": edge,
            "drawn": drawn_n, "frames": len(tr["t"]), "minutes": round(mins, 2)}  # fmt: skip


def rates(log: list[dict[str, Any]], cache: dict[str, Any], moving_px: float = 1.0
          ) -> dict[str, Any]:  # fmt: skip
    """Messages per minute by type, while the scene moves and while it is still (by the recorded
    frames' own motion, the time up to the next recorded frame)."""
    tr, mo = cache["truth"], cache["motion"]
    t = tr["t"].astype(np.int64)
    walking = walking_mask(mo, moving_px)
    # a frame's state holds from the previous recorded frame up to it (its motion is since then)
    dur = np.diff(t, prepend=t[0])
    mins = {"moving": float(dur[walking].sum()) / 60e9, "still": float(dur[~walking].sum()) / 60e9}
    by: dict[str, dict[str, int]] = {"moving": {}, "still": {}}
    moves = {"moving": 0, "still": 0}
    for e in log:
        i = int(np.searchsorted(t, e["msg"]["t_mono_ns"]))
        i = min(max(i, 0), len(t) - 1)
        st = "moving" if walking[i] else "still"
        typ = e["msg"]["type"]
        by[st][typ] = by[st].get(typ, 0) + 1
        if typ == "hud_delta":
            moves[st] += len(e["msg"]["move"])
    out: dict[str, Any] = {}
    for st in ("moving", "still"):
        m = max(mins[st], 1e-9)
        out[st] = {"minutes": round(mins[st], 2),
                   "per_minute": {k: round(c / m, 1) for k, c in sorted(by[st].items())},
                   "moves_per_minute": round(moves[st] / m, 1)}  # fmt: skip
    return out


def det_cost(runs: list[tuple[int, float]], cache: dict[str, Any], threads: int = 2,
             moving_px: float = 1.0) -> dict[str, Any]:  # fmt: skip
    """The detector's CPU: passes, and cores busy (threads while it runs) while the scene moves
    and while it is still."""
    tr, mo = cache["truth"], cache["motion"]
    t = tr["t"].astype(np.int64)
    walking = walking_mask(mo, moving_px)
    dur = np.diff(t, prepend=t[0])
    secs = {"moving": float(dur[walking].sum()) / 1e9, "still": float(dur[~walking].sum()) / 1e9}
    busy = {"moving": 0.0, "still": 0.0}
    n = {"moving": 0, "still": 0}
    for t0, ms in runs:
        i = min(int(np.searchsorted(t, t0)), len(t) - 1)
        st = "moving" if walking[i] else "still"
        busy[st] += ms / 1000
        n[st] += 1
    return {st: {"passes_per_s": round(n[st] / max(secs[st], 1e-9), 2),
                 "cores": round(threads * busy[st] / max(secs[st], 1e-9), 2)}
            for st in ("moving", "still")}  # fmt: skip


if __name__ == "__main__":  # the cache builders, for a background job: DIR... [--motion-only]
    only_motion = "--motion-only" in sys.argv
    for a in [x for x in sys.argv[1:] if not x.startswith("--")]:
        build_motion(Path(a))
        if not only_motion and not (cache_dir(Path(a)) / "truth.npz").exists():
            build_truth(Path(a))
