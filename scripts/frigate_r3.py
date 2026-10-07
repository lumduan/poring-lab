#!/usr/bin/env python3
"""R1-R3: the GPU sharing rules for ANY GPU work of ours (infra side, adopted by Batt 2026-10-07).

The GPU is shared with Frigate (NVR: 16 cameras, 3 ONNX detectors) and Ollama (qwen3-vl). The
20:00-05:00 GPU window is RETIRED: these rules decide, not the clock.
  R1  Ollama + vision VRAM <= 9 GiB combined (VISION_MAX_VRAM_FRACTION keeps vision under it).
  R2  One model at a time: refuse to start while Ollama has a model loaded (/api/ps); yield if one
      loads during our job.
  R3  Stop if the Frigate detector is > 5 ms slower than its baseline, measured close in time with
      nothing of ours running; stop HARD if any camera drops frames for 30 s.

Standard library only: scripts/guarded_build.py imports this module and runs under `python3 -S`.

    frigate_r3.py baseline [--minutes 15] [--out PATH]
        Measure the baseline: nothing of ours on the GPU, Ollama unloaded (R2), >= --minutes of
        distinct Frigate stats updates. Writes PATH (default BASELINE, on /dev/shm).
    frigate_r3.py sample OUT.csv
        Every 5 s, one row per DISTINCT Frigate update (deduped on service.last_updated):
        detector inference, fleet detection_fps, every camera's camera_fps / skipped_fps, GPU util
        and memory, Ollama's loaded models. OUT stays on /dev/shm (rule 7).
    frigate_r3.py watch [--csv OUT.csv] [--sigint]
        The R3Guard over the live stats, printing every breach (ICT + UTC). With --sigint, a breach
        SIGINTs our running vision container(s) (`docker kill --signal INT`; a SIGINT to the
        compose client alone does not stop the container). The interim guard before
        guarded_build had R3.
    frigate_r3.py check
        The pre-start checks guarded_build runs for every vision step; prints the verdict.

Frigate 0.17 facts (verified 2026-10-07):
- There is no "dropped" field. A camera's dropped frames show as skipped_fps (the detector queue
  was full); camera_fps ~= process_fps + skipped_fps.
- Stats refresh about every 15 s, so dedupe on service.last_updated.
- inference_speed depends on the load regime (idle ~28 ms, saturated ~12 ms). That is why the
  baseline is measured close in time, re-measured every <= 3 h, and re-measured when the fleet's
  detection rate moves out of [0.5x, 2x] of the baseline's.
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import subprocess
import sys
import time
from collections import deque
from collections.abc import Callable
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.request import urlopen

FRIGATE_STATS = "http://127.0.0.1:5000/api/stats"
OLLAMA = "http://127.0.0.1:11434"
BASELINE = Path("/dev/shm/poring-lab-frigate/baseline.json")
ICT = timezone(timedelta(hours=7))

DELTA_MS = 5.0  # R3: +5 ms over the baseline median
LAT_WINDOW_S = 60.0  # ... as a rolling 60 s median of distinct updates
LAT_MIN_UPDATES = 3
DROP_S = 30.0  # R3: a camera dropping frames for 30 s -> HARD stop
DROP_MIN_UPDATES = 2
CAM_FPS_FLOOR = 0.5  # camera_fps below half its baseline median also counts as dropping
UNREACHABLE_S = 60.0  # no fresh Frigate update for 60 s -> fail closed (pause)
BASELINE_MAX_AGE_S = 3 * 3600  # re-measure at least every 3 h
ACTIVITY_WINDOW_S = 600.0  # the activity pattern: 10 min median fleet detection_fps ...
ACTIVITY_BAND = (0.5, 2.0)  # ... outside [0.5x, 2x] of the baseline's -> re-measure
OLLAMA_POLL_S = 15.0

Fetch = Callable[[str], dict[str, Any] | None]


def stamp(t: float | None = None) -> str:
    t = time.time() if t is None else t
    ict = datetime.fromtimestamp(t, ICT).strftime("%H:%M:%S")
    utc = datetime.fromtimestamp(t, UTC).strftime("%H:%M:%S")
    return f"{ict} ICT / {utc} UTC"


def fetch_json(url: str, timeout: float = 2.0) -> dict[str, Any] | None:
    try:
        with urlopen(url, timeout=timeout) as r:  # noqa: S310 (fixed loopback URLs)
            data = json.load(r)
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def parse_stats(stats: dict[str, Any]) -> dict[str, Any] | None:
    """One Frigate update: its id, the detectors' inference (each + mean), the fleet detection
    rate and each camera's (camera_fps, skipped_fps). None if the shape is not Frigate's."""
    try:
        dets = {k: float(v["inference_speed"]) for k, v in stats["detectors"].items()}
        cams = {k: (float(v["camera_fps"]), float(v["skipped_fps"]))
                for k, v in stats["cameras"].items()}  # fmt: skip
        return {"updated": stats["service"]["last_updated"],
                "inference": sum(dets.values()) / len(dets), "detectors": dets,
                "detection_fps": float(stats["detection_fps"]), "cameras": cams}  # fmt: skip
    except (KeyError, TypeError, ValueError, ZeroDivisionError):
        return None


def ollama_models(fetch: Fetch = fetch_json) -> list[dict[str, Any]] | None:
    """Loaded models ([] = none), or None when Ollama does not answer (then nothing can be loaded
    through it, which R2 accepts; it is reported)."""
    ps = fetch(f"{OLLAMA}/api/ps")
    if ps is None:
        return None
    return [
        {"name": m.get("name"), "size_vram": m.get("size_vram")} for m in ps.get("models") or []
    ]


def gpu_state() -> tuple[str, str, list[tuple[str, int]]]:
    """(util %, memory used MiB, [(process name, MiB)]) from nvidia-smi; empty strings on error."""
    try:
        g = subprocess.run(["nvidia-smi", "--query-gpu=utilization.gpu,memory.used",
                            "--format=csv,noheader,nounits"], capture_output=True, text=True,
                           timeout=10, check=True).stdout.split(",")  # fmt: skip
        a = subprocess.run(["nvidia-smi", "--query-compute-apps=process_name,used_memory",
                            "--format=csv,noheader,nounits"], capture_output=True, text=True,
                           timeout=10, check=True).stdout  # fmt: skip
        apps = []
        for line in a.splitlines():
            name, _, mib = line.rpartition(",")
            if name:
                apps.append((name.strip(), int(mib.strip() or 0)))
        return g[0].strip(), g[1].strip(), apps
    except Exception:
        return "", "", []


def our_gpu_jobs(apps: list[tuple[str, int]]) -> list[str]:
    """Our GPU jobs: python processes on the GPU (the vision container's; Frigate's detectors are
    `frigate.detector:*`, its decoders ffmpeg, Ollama's runner `ollama`)."""
    return [f"{n} ({m} MiB)" for n, m in apps if "python" in Path(n).name]


def load_baseline(
    path: Path, now: float | None = None, max_age: float = BASELINE_MAX_AGE_S
) -> tuple[dict[str, Any] | None, str]:
    now = time.time() if now is None else now
    try:
        b = json.loads(path.read_text())
        age = now - float(b["t_end"])
        float(b["inference_median"])
    except FileNotFoundError:
        return None, f"no Frigate baseline at {path}: run `frigate_r3.py baseline` first"
    except (ValueError, KeyError, TypeError) as e:
        return None, f"Frigate baseline {path} unreadable ({e})"
    if age > max_age:
        return None, (f"Frigate baseline is {age / 3600:.1f} h old (> {max_age / 3600:.0f} h): "
                      "re-measure it")  # fmt: skip
    return b, "ok"


def prestart(path: Path = BASELINE, fetch: Fetch = fetch_json,
             apps: list[tuple[str, int]] | None = None) -> str | None:  # fmt: skip
    """The checks before ANY GPU job of ours: the refusal reason, or None to go."""
    models = ollama_models(fetch)
    if models:
        names = ", ".join(str(m["name"]) for m in models)
        return f"R2: Ollama has a model loaded ({names}); one model at a time"
    if apps is None:
        apps = gpu_state()[2]
    jobs = our_gpu_jobs(apps)
    if jobs:
        return f"R2: another job of ours is on the GPU ({'; '.join(jobs)})"
    s = fetch(FRIGATE_STATS)
    if s is None or parse_stats(s) is None:
        return "R3: Frigate stats unreachable (fail closed)"
    b, why = load_baseline(path)
    if b is None:
        return f"R3: {why}"
    return None


def summarise(samples: list[dict[str, Any]]) -> dict[str, Any]:
    inf = [s["inference"] for s in samples]
    cams: dict[str, dict[str, Any]] = {}
    for name in samples[0]["cameras"]:
        fps = [s["cameras"][name][0] for s in samples if name in s["cameras"]]
        sk = sorted(s["cameras"][name][1] for s in samples if name in s["cameras"])
        cams[name] = {"camera_fps_median": statistics.median(fps),
                      "skipped_nonzero_fraction": round(sum(v > 0 for v in sk) / len(sk), 4),
                      "skipped_p99": sk[min(len(sk) - 1, int(0.99 * len(sk)))]}  # fmt: skip
    q = statistics.quantiles(inf, n=20) if len(inf) > 1 else [inf[0]] * 19
    return {
        "updates": len(samples),
        "inference_median": round(statistics.median(inf), 2),
        "inference_p95": round(q[18], 2),
        "detectors_median": {
            k: round(statistics.median(s["detectors"][k] for s in samples), 2)
            for k in samples[0]["detectors"]
        },  # fmt: skip
        "detection_fps_median": round(statistics.median(s["detection_fps"] for s in samples), 2),
        "cameras": cams,
    }


def baseline(out: Path, minutes: float, fetch: Fetch = fetch_json, every: float = 5.0) -> int:
    why = prestart_for_baseline(fetch)
    if why:
        print(f"[{stamp()}] BASELINE REFUSED: {why}", flush=True)
        return 3
    t0 = time.time()
    print(f"[{stamp(t0)}] baseline: {minutes:g} min, nothing of ours on the GPU, Ollama unloaded",
          flush=True)  # fmt: skip
    samples: list[dict[str, Any]] = []
    seen = None
    while time.time() - t0 < minutes * 60:
        s = fetch(FRIGATE_STATS)
        p = parse_stats(s) if s else None
        if p and p["updated"] != seen:
            seen = p["updated"]
            samples.append(p)
        why = prestart_for_baseline(fetch, check_frigate=False)
        if why:
            print(f"[{stamp()}] BASELINE ABORTED: {why}", flush=True)
            return 3
        time.sleep(every)
    if len(samples) < 10:
        print(
            f"[{stamp()}] BASELINE FAILED: only {len(samples)} distinct Frigate updates", flush=True
        )
        return 1
    t1 = time.time()
    res = {"t_start": t0, "t_end": t1, "start": stamp(t0), "end": stamp(t1),
           "date_ict": datetime.fromtimestamp(t0, ICT).strftime("%Y-%m-%d"),
           **summarise(samples)}  # fmt: skip
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".tmp")
    tmp.write_text(json.dumps(res, indent=1))
    os.replace(tmp, out)
    print(json.dumps(res), flush=True)
    return 0


def prestart_for_baseline(fetch: Fetch = fetch_json, check_frigate: bool = True) -> str | None:
    models = ollama_models(fetch)
    if models:
        return f"R2: Ollama has a model loaded ({', '.join(str(m['name']) for m in models)})"
    jobs = our_gpu_jobs(gpu_state()[2])
    if jobs:
        return f"a job of ours is on the GPU ({'; '.join(jobs)})"
    if check_frigate:
        s = fetch(FRIGATE_STATS)
        if s is None or parse_stats(s) is None:
            return "Frigate stats unreachable"
    return None


class R3Guard:
    """R2 + R3 over the live stats. `poll(now)` then `breach(now)` -> None | (kind, detail, hard).

    kinds: latency (pause), drops (HARD: no resume), frigate_unreachable (pause, fail closed),
    r2_ollama_loaded (pause: yield the GPU), rebaseline_due (a planned pause, only right after a
    training epoch ends: a new row in results_csv; never without a results_csv)."""

    def __init__(self, base: dict[str, Any], fetch: Fetch = fetch_json,
                 results_csv: Path | None = None, now: float | None = None) -> None:  # fmt: skip
        now = time.time() if now is None else now
        self.base = base
        self.fetch = fetch
        self.results_csv = results_csv
        self.rows0 = self._rows()
        self.seen: Any = None
        self.last_fresh = now
        self.lat: deque[tuple[float, float]] = deque()
        self.act: deque[tuple[float, float]] = deque()
        self.bad_since: dict[str, tuple[float, int]] = {}
        self.last_ollama = -1e18
        self.models: list[dict[str, Any]] = []
        self.last: dict[str, Any] | None = None

    def _rows(self) -> int:
        try:
            return len(self.results_csv.read_text().splitlines()) if self.results_csv else 0
        except OSError:
            return 0

    def floor(self, cam: str) -> float:
        c = self.base.get("cameras", {}).get(cam)
        return 0.0 if not c or c["skipped_nonzero_fraction"] == 0 else float(c["skipped_p99"])

    def poll(self, now: float | None = None) -> None:
        now = time.time() if now is None else now
        s = self.fetch(FRIGATE_STATS)
        p = parse_stats(s) if s else None
        if p is not None and p["updated"] != self.seen:
            self.seen = p["updated"]
            self.last_fresh = now
            self.last = p
            self.lat.append((now, p["inference"]))
            self.act.append((now, p["detection_fps"]))
            for cam, (fps, skipped) in p["cameras"].items():
                base_fps = self.base.get("cameras", {}).get(cam, {}).get("camera_fps_median", 0)
                bad = skipped > self.floor(cam) or (base_fps > 0 and fps < CAM_FPS_FLOOR * base_fps)
                if bad:
                    since, n = self.bad_since.get(cam, (now, 0))
                    self.bad_since[cam] = (since, n + 1)
                else:
                    self.bad_since.pop(cam, None)
        while self.lat and now - self.lat[0][0] > LAT_WINDOW_S:
            self.lat.popleft()
        while self.act and now - self.act[0][0] > ACTIVITY_WINDOW_S:
            self.act.popleft()
        if now - self.last_ollama >= OLLAMA_POLL_S:
            self.last_ollama = now
            self.models = ollama_models(self.fetch) or []

    def latency_median(self) -> float | None:
        return (
            statistics.median(v for _, v in self.lat) if len(self.lat) >= LAT_MIN_UPDATES else None
        )

    def breach(self, now: float | None = None) -> tuple[str, str, bool] | None:
        now = time.time() if now is None else now
        b = float(self.base["inference_median"])
        for cam, (since, n) in sorted(self.bad_since.items()):
            if n >= DROP_MIN_UPDATES and now - since >= DROP_S:
                fps, sk = self.last["cameras"][cam] if self.last else (0.0, 0.0)
                return ("drops", f"camera {cam} dropping frames for {now - since:.0f} s "
                        f"(skipped_fps {sk}, camera_fps {fps})", True)  # fmt: skip
        if now - self.last_fresh > UNREACHABLE_S:
            return ("frigate_unreachable",
                    f"no fresh Frigate stats for {now - self.last_fresh:.0f} s", False)  # fmt: skip
        m = self.latency_median()
        if m is not None and m > b + DELTA_MS:
            return ("latency", f"detector 60 s median {m:.1f} ms vs baseline {b:.1f} ms "
                    f"(+{m - b:.1f} > +{DELTA_MS:g})", False)  # fmt: skip
        if self.models:
            names = ", ".join(str(x["name"]) for x in self.models)
            return ("r2_ollama_loaded", f"Ollama loaded {names}: yield the GPU", False)
        due = self.rebaseline_reason(now)
        if due and self.results_csv is not None and self._rows() > self.rows0:
            return ("rebaseline_due", f"{due}; an epoch just ended", False)
        return None

    def rebaseline_reason(self, now: float) -> str | None:
        age = now - float(self.base["t_end"])
        if age > BASELINE_MAX_AGE_S:
            return f"baseline {age / 3600:.1f} h old"
        if self.act and now - self.act[0][0] >= ACTIVITY_WINDOW_S - 30:
            cur = statistics.median(v for _, v in self.act)
            ref = float(self.base["detection_fps_median"])
            lo, hi = ACTIVITY_BAND
            if ref > 0 and not lo * ref <= cur <= hi * ref:
                return (f"camera activity changed: detection_fps 10 min median {cur:.1f} vs "
                        f"baseline {ref:.1f}")  # fmt: skip
        return None


def vision_containers(run: Any = subprocess.run) -> list[str]:
    """Our running vision containers (compose service `vision`). 2026-10-07: a SIGINT to the
    host-side `timeout ... docker compose run` stopped only the compose client and the training
    container ran on, so a stop must signal the CONTAINER."""
    out = run(["docker", "ps", "-q", "--filter", "label=com.docker.compose.service=vision"],
              capture_output=True, text=True, check=False).stdout  # fmt: skip
    return [c for c in out.split() if c]


def csv_header(cams: list[str], dets: list[str]) -> str:
    cols = ["t_epoch", "t_utc", "t_ict", "updated", "inference_mean", *dets, "detection_fps",
            *[f"{c}:fps" for c in cams], *[f"{c}:skip" for c in cams],
            "gpu_util", "gpu_mem", "python_mib", "ollama_models"]  # fmt: skip
    return ",".join(cols) + "\n"


def csv_row(
    now: float,
    p: dict[str, Any],
    cams: list[str],
    dets: list[str],
    gpu: tuple[str, str, list[tuple[str, int]]],
    models: list[dict[str, Any]],
) -> str:
    py = sum(m for n, m in gpu[2] if "python" in Path(n).name)
    vals = [f"{now:.1f}", datetime.fromtimestamp(now, UTC).strftime("%F %T"),
            datetime.fromtimestamp(now, ICT).strftime("%F %T"), str(p["updated"]),
            f"{p['inference']:.2f}", *[f"{p['detectors'].get(d, '')}" for d in dets],
            f"{p['detection_fps']}", *[f"{p['cameras'].get(c, ('', ''))[0]}" for c in cams],
            *[f"{p['cameras'].get(c, ('', ''))[1]}" for c in cams], gpu[0], gpu[1], str(py),
            "|".join(str(m["name"]) for m in models)]  # fmt: skip
    return ",".join(vals) + "\n"


def run_loop(csv_out: Path | None, guard: R3Guard | None, sigint: bool, every: float = 5.0) -> int:
    fh = None
    cams: list[str] = []
    dets: list[str] = []
    seen = None
    last_status = 0.0
    while True:
        now = time.time()
        if guard is not None:
            guard.poll(now)
            p = guard.last
        else:
            s = fetch_json(FRIGATE_STATS)
            p = parse_stats(s) if s else None
        if csv_out is not None and p is not None and p["updated"] != seen:
            seen = p["updated"]
            if fh is None:
                cams, dets = sorted(p["cameras"]), sorted(p["detectors"])
                new = not csv_out.exists()
                fh = csv_out.open("a")
                if new:
                    fh.write(csv_header(cams, dets))
            fh.write(csv_row(now, p, cams, dets, gpu_state(), guard.models if guard else []))
            fh.flush()
        if guard is not None:
            hit = guard.breach(now)
            if hit:
                kind, detail, hard = hit
                tag = "R3-HARD" if hard else "R3"
                print(f"[{stamp(now)}] BREACH {tag} {kind}: {detail}", flush=True)
                if sigint:
                    ids = vision_containers()
                    for cid in ids:
                        subprocess.run(["docker", "kill", "--signal", "INT", cid],
                                       capture_output=True, check=False)  # fmt: skip
                    print(f"[{stamp()}] SIGINT sent to vision container(s) {ids or 'none'}",
                          flush=True)  # fmt: skip
                    t0 = time.monotonic()  # verified, never assumed (Batt 2026-10-07)
                    while vision_containers() and time.monotonic() - t0 < 30:
                        time.sleep(2)
                    left = vision_containers()
                    for cid in left:
                        subprocess.run(["docker", "kill", cid], capture_output=True, check=False)
                    time.sleep(5 if left else 0)
                    still = vision_containers()
                    verdict = ("STOP VERIFIED" if not still else f"STOP-UNVERIFIED {still}") + (
                        f" (escalated: docker kill {left})" if left else ""
                    )
                    print(f"[{stamp()}] {verdict}", flush=True)
                    return 2 if not still else 4
            elif now - last_status >= 900:
                last_status = now
                m = guard.latency_median()
                print(f"[{stamp(now)}] ok: detector 60 s median "
                      f"{'-' if m is None else f'{m:.1f}'} ms (baseline "
                      f"{guard.base['inference_median']}), cameras ok", flush=True)  # fmt: skip
        time.sleep(every)


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("baseline")
    b.add_argument("--minutes", type=float, default=15.0)
    b.add_argument("--out", type=Path, default=BASELINE)
    s = sub.add_parser("sample")
    s.add_argument("csv", type=Path)
    w = sub.add_parser("watch")
    w.add_argument("--csv", type=Path)
    w.add_argument("--baseline", type=Path, default=BASELINE)
    w.add_argument("--results-csv", type=Path)
    w.add_argument("--sigint", action="store_true")
    c = sub.add_parser("check")
    c.add_argument("--baseline", type=Path, default=BASELINE)
    a = ap.parse_args()
    for path in (getattr(a, "csv", None), getattr(a, "out", None)):
        if path is not None and not str(path).startswith("/dev/shm/"):
            sys.exit("keep it on /dev/shm (CLAUDE.md rule 7)")
    if a.cmd == "baseline":
        return baseline(a.out, a.minutes)
    if a.cmd == "sample":
        return run_loop(a.csv, None, False)
    if a.cmd == "check":
        why = prestart(a.baseline)
        print(f"[{stamp()}] {'REFUSED: ' + why if why else 'OK: R2 + R3 pre-start checks pass'}")
        return 3 if why else 0
    base, why = load_baseline(a.baseline)
    if base is None:
        print(f"[{stamp()}] WATCH REFUSED: {why}", flush=True)
        return 3
    return run_loop(a.csv, R3Guard(base, results_csv=a.results_csv), a.sigint)


if __name__ == "__main__":
    sys.exit(main())
