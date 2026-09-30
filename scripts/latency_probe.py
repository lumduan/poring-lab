"""Phase 0 latency probe: decompose web-console latency on the host clock (docs/phase0-latency.md).

Runs INSIDE the backend container (it needs the X socket, and /debug/* answers loopback only):

    E=PYTHONPATH=/dev-src/poring_env:/dev-src/backend
    P="docker exec -i -e $E poring-lab-backend-1 python -"
    $P passive --seconds 30 --region 0,0,1280,720        < scripts/latency_probe.py   # no input
    $P cursor --a 1000,560 --b 1180,640 --trials 60      < scripts/latency_probe.py   # MOVES ONLY
    $P cursor --k1 ControlLeft+KeyA --k2 ArrowRight --via agent < scripts/latency_probe.py  # bot
    $P jpeg-bench --frames 20                            < scripts/latency_probe.py   # no input
    $P tune '{"capture": "damage"}'                      < scripts/latency_probe.py

Clocks: the probe, the backend and Xvfb share the host's CLOCK_MONOTONIC. Browser numbers come
from the console's ViewerTiming (its clock mapped by a ping offset, with an uncertainty).

  L1  probe send -> backend arrival -> mux decision -> XTest synced             (cursor)
  L2  XTest synced -> first XDamage in the target box whose pixels changed      (cursor)
  L3  change in Xvfb -> the grab (t_capture) of the first stream frame with it  (both)
  L4  capture -> encoded -> sent; sent -> received (probe: loopback; browser: LAN)
  L5  browser received -> decoded -> painted (rAF or decode time)                (ViewerTiming)

SAFETY: the only input this probe can send is pointer MOVES (cursor mode) -- never a click, never a
key. It refuses to start if a browser tab sent input in the last 10 s, so it never fights a human.
"""

import argparse
import hashlib
import json
import statistics
import sys
import threading
import time
import urllib.error
import urllib.request
from collections import deque
from dataclasses import dataclass, field
from typing import Any

import mss
import numpy as np
import simplejpeg
from websockets.sync.client import connect
from Xlib import display as xdisplay
from Xlib.ext import damage as xdamage

BACKEND = "http://127.0.0.1:8000"
WS = "ws://127.0.0.1:8000"
SCREEN_W, SCREEN_H = 1280, 720  # replaced by the real Xvfb size in main()
AGENT_WS = "ws://127.0.0.1:8001/internal/agent"
MS = 1e6


def now_ns() -> int:
    return time.monotonic_ns()


def stats(values: list[float]) -> dict[str, Any]:
    if not values:
        return {"n": 0}
    if len(values) == 1:
        return {"n": 1, "p50": round(values[0], 2), "p95": round(values[0], 2)}
    q = statistics.quantiles(values, n=100, method="inclusive")
    return {"n": len(values), "p50": round(q[49], 2), "p95": round(q[94], 2)}


def http_json(path: str, body: dict[str, Any] | None = None) -> Any:
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(
        BACKEND + path, data=data, headers={"content-type": "application/json"}
    )
    for attempt in range(40):  # backends before 2026-09-30 R2 could race on /debug/latency (500)
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                return json.loads(resp.read())
        except urllib.error.HTTPError as exc:
            if exc.code != 500 or attempt == 39:
                raise
            time.sleep(0.05)
    raise AssertionError("unreachable")


def box(x: int, y: int, w: int, h: int) -> tuple[int, int, int, int]:
    x, y = max(0, x), max(0, y)
    return x, y, min(w, SCREEN_W - x), min(h, SCREEN_H - y)


def intersects(a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> bool:
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    return ax < bx + bw and bx < ax + aw and ay < by + bh and by < ay + ah


# --- XDamage watcher (raw rectangles, receipt time on our clock) ----------------------------------


class DamageLog(threading.Thread):
    def __init__(self) -> None:
        super().__init__(daemon=True)
        self.events: deque[tuple[int, int, tuple[int, int, int, int]]] = deque(maxlen=200_000)
        self.stop = threading.Event()
        self.ready = threading.Event()

    def run(self) -> None:
        import select

        d = xdisplay.Display(":99")
        d.damage_query_version()
        info = d.query_extension("DAMAGE")
        assert info is not None
        notify = info.first_event + xdamage.DamageNotifyCode
        d.screen().root.damage_create(xdamage.DamageReportRawRectangles)
        d.sync()
        self.ready.set()
        while not self.stop.is_set():
            select.select([d], [], [], 0.2)
            while d.pending_events():
                e = d.next_event()
                if e.type == notify:
                    # Xvfb's server time IS CLOCK_MONOTONIC in ms (verified 2026-09-30: receipt -
                    # timestamp = 1 ms median). Receipt can lag by tens of ms while this process
                    # decodes frames, so the change time is rebuilt from the X timestamp (+-1 ms).
                    received = now_ns()
                    lag_ms = ((received // 1_000_000) % 2**32 - int(e.timestamp)) % 2**32
                    at = received - min(lag_ms, 1000) * 1_000_000
                    a = e.area
                    self.events.append((at, int(e.timestamp), (a.x, a.y, a.width, a.height)))

    def first_in(self, region: tuple[int, int, int, int], after_ns: int) -> int | None:
        for t, _ts, rect in list(self.events):
            if t >= after_ns and intersects(rect, region):
                return t
        return None


# --- stream viewer -----------------------------------------------------------------------------


@dataclass
class StreamFrame:
    frame_id: int
    t_capture: int
    t_encoded: int
    t_sent: int
    t_recv: int
    jpeg: bytes = field(repr=False)


class StreamViewer(threading.Thread):
    def __init__(self) -> None:
        super().__init__(daemon=True)
        self.frames: deque[StreamFrame] = deque(maxlen=4000)
        self.stop = threading.Event()
        self.ready = threading.Event()

    def run(self) -> None:
        with connect(f"{WS}/ws/stream", max_size=2**24, open_timeout=5) as ws:
            self.ready.set()
            meta: dict[str, Any] | None = None
            while not self.stop.is_set():
                try:
                    raw = ws.recv(timeout=0.5)
                except TimeoutError:
                    continue
                if isinstance(raw, bytes):
                    if meta is not None:
                        self.frames.append(
                            StreamFrame(
                                meta["frame_id"],
                                meta["t_capture_ns"],
                                meta["t_encoded_ns"],
                                meta["t_mono_ns"],
                                now_ns(),
                                raw,
                            )
                        )
                    meta = None
                    continue
                msg = json.loads(raw)
                if msg.get("type") == "frame":
                    meta = msg


def region_of_jpeg(jpeg: bytes, region: tuple[int, int, int, int]) -> np.ndarray:
    img = simplejpeg.decode_jpeg(jpeg, colorspace="RGB", fastdct=True, fastupsample=True)
    x, y, w, h = region
    return np.asarray(img[y : y + h, x : x + w], dtype=np.int16)


def changed(a: np.ndarray, b: np.ndarray, level: int = 40, min_pixels: int = 25) -> bool:
    if a.shape != b.shape:
        return True
    diff = np.abs(a - b).max(axis=-1)
    return int((diff > level).sum()) >= min_pixels


def grab_region(sct: Any, region: tuple[int, int, int, int]) -> np.ndarray:
    x, y, w, h = region
    shot = sct.grab({"left": x, "top": y, "width": w, "height": h})
    return np.frombuffer(shot.rgb, np.uint8).reshape(h, w, 3).astype(np.int16)


# --- modes ---------------------------------------------------------------------------------------


def browser_segments(since_ns: int, frames: dict[int, dict[str, Any]]) -> dict[str, Any]:
    dump = http_json(f"/debug/latency?since_ns={since_ns}")
    net, dec, paint, send_paint, cap_paint, unc = [], [], [], [], [], []
    for v in dump["viewer"]:
        f = frames.get(v["frame_id"]) or next(
            (x for x in dump["frames"] if x["frame_id"] == v["frame_id"]), None
        )
        dec.append((v["t_decoded"] - v["t_recv"]) / MS)
        paint.append((v["t_painted"] - v["t_decoded"]) / MS)
        unc.append(v["uncertainty_ns"] / MS)
        if f and f.get("t_sent"):
            net.append((v["t_recv"] - f["t_sent"]) / MS)
            send_paint.append((v["t_painted"] - f["t_sent"]) / MS)
            cap_paint.append((v["t_painted"] - f["t_capture"]) / MS)
    agent = dump["viewer"][-1]["user_agent"] if dump["viewer"] else None
    return {
        "user_agent": agent,
        "offset_uncertainty_ms": stats(unc),
        "net_ms": stats(net),
        "decode_ms": stats(dec),
        "paint_wait_ms": stats(paint),
        "send_to_paint_ms": stats(send_paint),
        "capture_to_paint_ms": stats(cap_paint),
    }


def passive(args: argparse.Namespace) -> dict[str, Any]:
    region = box(*args.region)
    dmg, view = DamageLog(), StreamViewer()
    dmg.start()
    view.start()
    dmg.ready.wait(5)
    view.ready.wait(5)
    t0 = now_ns()
    hashes: list[str] = []
    with mss.MSS(display=":99") as sct:
        deadline = time.monotonic() + args.seconds
        while time.monotonic() < deadline:  # distinct content of the region in Xvfb, ~100 Hz
            shot = sct.grab({"left": region[0], "top": region[1], "width": region[2],
                             "height": region[3]})  # fmt: skip
            hashes.append(hashlib.blake2b(shot.raw[::97], digest_size=8).hexdigest())
            time.sleep(0.01)
    t1 = now_ns()
    dmg.stop.set()
    view.stop.set()
    time.sleep(0.6)
    frames = [f for f in view.frames if t0 <= f.t_capture <= t1]
    damage = [e for e in dmg.events if t0 <= e[0] <= t1 and intersects(e[2], region)]
    # L3: each frame's capture minus the earliest change it contains (since the previous grab).
    l3, prev = [], t0
    for f in frames:
        pending = [t for t, _ts, _r in damage if prev < t <= f.t_capture]
        if pending:
            l3.append((f.t_capture - min(pending)) / MS)
        prev = f.t_capture
    distinct_x = sum(1 for a, b in zip(hashes, hashes[1:], strict=False) if a != b)
    delivered = [hashlib.blake2b(region_of_jpeg(f.jpeg, region)[::8, ::8].tobytes(),
                                 digest_size=8).hexdigest() for f in frames]  # fmt: skip
    distinct_web = sum(1 for a, b in zip(delivered, delivered[1:], strict=False) if a != b)
    seconds = (t1 - t0) / 1e9
    xmap = [(t // 1_000_000) % 2**32 - ts for t, ts, _ in damage[:500]]
    return {
        "mode": "passive",
        "tuning": http_json("/debug/stream-tuning"),
        "seconds": round(seconds, 1),
        "region": region,
        "ro_render": {
            "xdamage_events_per_s": round(len(damage) / seconds, 1),
            "distinct_region_frames_in_xvfb_per_s": round(distinct_x / seconds, 1),
            "xvfb_sampling_hz": round(len(hashes) / seconds, 1),
            "distinct_region_frames_delivered_per_s": round(distinct_web / seconds, 1),
        },
        "stream_frames_per_s": round(len(frames) / seconds, 1),
        "L3_capture_wait_ms": stats(l3),
        "L4_encode_ms": stats([(f.t_encoded - f.t_capture) / MS for f in frames]),
        "L4_queue_send_ms": stats([(f.t_sent - f.t_encoded) / MS for f in frames]),
        "L4_loopback_recv_ms": stats([(f.t_recv - f.t_sent) / MS for f in frames]),
        "x_timestamp_minus_receipt_ms": stats([float(v) for v in xmap]),
        "browser": browser_segments(t0, {}),
    }


def cursor(args: argparse.Namespace) -> dict[str, Any]:
    recent = http_json(f"/debug/latency?since_ns={now_ns() - 10_000_000_000}")["inputs"]
    if any(i["clock"] == "browser" for i in recent):
        sys.exit("a browser tab sent input in the last 10 s: not fighting a human -- try later")
    a, b = tuple(args.a), tuple(args.b)
    dmg, view = DamageLog(), StreamViewer()
    dmg.start()
    view.start()
    dmg.ready.wait(5)
    view.ready.wait(5)
    time.sleep(0.5)
    trials: list[dict[str, Any]] = []
    aborted: str | None = None
    t_start = now_ns()
    # --via agent: the bot path (/internal/agent on :8001, source=bot, mux in ASSIST). That channel
    # doesn't feed the latency recorder, so L1 isn't split out: rows get L12_ms = send -> change.
    via_agent = args.via == "agent"
    url = AGENT_WS if via_agent else f"{WS}/ws/input"
    with connect(url, open_timeout=5) as ws, mss.MSS(display=":99") as sct:
        if via_agent:
            ws.send(json.dumps({"type": "agent_hello", "t_mono_ns": now_ns(), "frame_id": -1,
                                "agent_id": "latency-probe", "version": "2"}))  # fmt: skip

        def emit(event: dict[str, Any]) -> int:
            t = now_ns()
            event = {**event, "t_mono_ns": t, "frame_id": -1}
            if not via_agent:
                ws.send(json.dumps(event))
                return t
            ws.send(json.dumps({"type": "agent_input", "t_mono_ns": t, "frame_id": -1,
                                "t_capture_ns": t, "events": [event]}))  # fmt: skip
            while True:  # the mux verdict for this batch; a refusal (human lease) stops the probe
                reply = json.loads(ws.recv(timeout=2))
                if reply.get("type") == "input_ack":
                    if reply["dropped"]:
                        sys.exit(f"mux refused the probe's input: {reply['reasons']}")
                    return t

        def move(p: tuple[int, int]) -> int:
            return emit({"type": "mouse_move", "x": p[0] / SCREEN_W, "y": p[1] / SCREEN_H})

        def key(code: str, action: str) -> int:
            return emit({"type": "key", "code": code, "action": action})

        def chord(spec: str) -> int:
            """Press the keys in order, release in reverse; returns the LAST key-down's send time
            (the trigger: e.g. the A of Ctrl+A)."""
            codes = spec.split("+")
            t_trigger = 0
            for code in codes:
                t_trigger = key(code, "down")
            for code in reversed(codes):
                key(code, "up")
            return t_trigger

        if not args.k1:
            move(a)
            time.sleep(0.8)
        here, there = a, b
        toggles = [args.k1, args.k2] if args.k1 else []
        misses = 0
        for i in range(args.trials):
            if args.watch:  # a fixed box that changes both ways (e.g. a hover highlight)
                target = box(*args.watch)
            else:  # the destination (e.g. RO's drawn cursor appearing there)
                target = box(there[0] - args.box // 4, there[1] - args.box // 4, args.box, args.box)
            base_x = grab_region(sct, target)
            last = view.frames[-1] if view.frames else None
            base_web = region_of_jpeg(last.jpeg, target) if last else None
            t_send = chord(toggles[i % 2]) if toggles else move(there)
            t_change = None
            deadline = time.monotonic() + 1.5
            while time.monotonic() < deadline and t_change is None:  # L2: damage + pixels
                t = dmg.first_in(target, t_send)
                if t is not None and changed(grab_region(sct, target), base_x):
                    t_change = t
                time.sleep(0.001)
            frame = None
            deadline = time.monotonic() + 1.5
            while time.monotonic() < deadline and frame is None and base_web is not None:
                for f in list(view.frames):
                    if f.t_capture >= (t_change or t_send) and changed(
                        region_of_jpeg(f.jpeg, target), base_web
                    ):
                        frame = f
                        break
                time.sleep(0.005)
            time.sleep(args.gap)
            inputs = http_json(f"/debug/latency?since_ns={t_send}")["inputs"]
            rec = next((r for r in inputs if r["t_sent"] == t_send), None)
            row: dict[str, Any] = {"trial": i, "to": there, "t_send": t_send}
            if rec and rec["t_injected"]:
                row["L1_ms"] = (rec["t_injected"] - t_send) / MS
                if t_change:
                    row["L2_ms"] = (t_change - rec["t_injected"]) / MS
            elif via_agent and t_change:
                row["L12_ms"] = (t_change - t_send) / MS
            if frame and t_change:
                row["frame_id"] = frame.frame_id
                row["L3_ms"] = (frame.t_capture - t_change) / MS
                row["L4_encode_ms"] = (frame.t_encoded - frame.t_capture) / MS
                row["L4_send_ms"] = (frame.t_sent - frame.t_encoded) / MS
                row["server_total_ms"] = (frame.t_sent - t_send) / MS
            trials.append(row)
            here, there = there, here
            misses = misses + 1 if "L2_ms" not in row and "L12_ms" not in row else 0
            if misses >= 3:  # focus moved (or the window changed): stop sending anything
                aborted = f"no change for 3 trials in a row at trial {i}: stopped"
                break
    time.sleep(1.5)  # let the browser report the last frames
    dump = http_json(f"/debug/latency?since_ns={t_start}")
    viewer = {v["frame_id"]: v for v in dump["viewer"]}
    frames = {f["frame_id"]: f for f in dump["frames"]}
    for row in trials:
        v = viewer.get(row.get("frame_id", -1))
        f = frames.get(row.get("frame_id", -1))
        if v and f and f.get("t_sent"):
            row["L4_net_browser_ms"] = (v["t_recv"] - f["t_sent"]) / MS
            row["L5_decode_ms"] = (v["t_decoded"] - v["t_recv"]) / MS
            row["L5_paint_wait_ms"] = (v["t_painted"] - v["t_decoded"]) / MS
            row["end_to_end_browser_ms"] = (v["t_painted"] - row["t_send"]) / MS
    dmg.stop.set()
    view.stop.set()
    keys = [
        "L1_ms",
        "L2_ms",
        "L12_ms",
        "L3_ms",
        "L4_encode_ms",
        "L4_send_ms",
        "server_total_ms",
        "L4_net_browser_ms",
        "L5_decode_ms",
        "L5_paint_wait_ms",
        "end_to_end_browser_ms",
    ]
    summary = {k: stats([r[k] for r in trials if k in r]) for k in keys}
    return {
        "mode": "cursor" if not args.k1 else f"keys {args.k1} / {args.k2}",
        "aborted": aborted,
        "tuning": http_json("/debug/stream-tuning"),
        "trials": len(trials),
        "via": args.via,
        "screen": [SCREEN_W, SCREEN_H],
        "detected_in_xvfb": sum(1 for r in trials if "L2_ms" in r or "L12_ms" in r),
        "detected_in_stream": sum(1 for r in trials if "L3_ms" in r),
        "summary": summary,
        "rows": trials if args.rows else None,
        "browser_agent": dump["viewer"][-1]["user_agent"] if dump["viewer"] else None,
    }


def jpeg_bench(args: argparse.Namespace) -> dict[str, Any]:
    frames = []
    with mss.MSS(display=":99") as sct:
        for _ in range(args.frames):
            shot = sct.grab(sct.monitors[1])
            frames.append(np.frombuffer(shot.raw, np.uint8).reshape(shot.height, shot.width, 4))
            time.sleep(0.05)
    out: dict[str, Any] = {"mode": "jpeg-bench", "frames": len(frames),
                           "size": f"{frames[0].shape[1]}x{frames[0].shape[0]}"}  # fmt: skip
    for q in (60, 70, 80, 90):
        times, sizes = [], []
        for f in frames:
            t = time.perf_counter()
            data = simplejpeg.encode_jpeg(f, quality=q, colorspace="BGRA",
                                          colorsubsampling="420", fastdct=True)  # fmt: skip
            times.append((time.perf_counter() - t) * 1000)
            sizes.append(len(data) / 1024)
        out[f"q{q}"] = {"encode_ms": stats(times), "kib": stats(sizes)}
    return out


def main() -> int:
    global SCREEN_W, SCREEN_H
    with mss.MSS(display=":99") as sct:  # the real screen: XVFB_RESOLUTION can change
        SCREEN_W, SCREEN_H = sct.monitors[1]["width"], sct.monitors[1]["height"]
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="mode", required=True)
    p = sub.add_parser("passive")
    p.add_argument("--seconds", type=float, default=30)
    p.add_argument("--region", type=lambda s: [int(v) for v in s.split(",")],
                   default=[0, 0, SCREEN_W, SCREEN_H])  # fmt: skip
    c = sub.add_parser("cursor")
    c.add_argument("--a", type=lambda s: [int(v) for v in s.split(",")], default=[0, 0])
    c.add_argument("--b", type=lambda s: [int(v) for v in s.split(",")], default=[0, 0])
    # Key toggle instead of moves (e.g. --k1 ControlLeft+KeyA --k2 ArrowRight in Notepad): only
    # for a known, focused, safe window -- the probe cannot see where keys go.
    c.add_argument("--k1", default=None)
    c.add_argument("--k2", default=None)
    c.add_argument("--trials", type=int, default=60)
    c.add_argument("--box", type=int, default=64)
    c.add_argument("--watch", type=lambda s: [int(v) for v in s.split(",")], default=None)
    c.add_argument("--gap", type=float, default=0.25)
    c.add_argument("--rows", action="store_true")
    # agent: send as the bot through /internal/agent (the mux must be in ASSIST or BOT).
    c.add_argument("--via", choices=["input", "agent"], default="input")
    j = sub.add_parser("jpeg-bench")
    j.add_argument("--frames", type=int, default=20)
    t = sub.add_parser("tune")
    t.add_argument("changes")
    args = ap.parse_args()
    if args.mode == "tune":
        result: Any = http_json("/debug/stream-tuning", json.loads(args.changes))
    elif args.mode == "passive":
        result = passive(args)
    elif args.mode == "cursor":
        result = cursor(args)
    else:
        result = jpeg_bench(args)
    print(json.dumps(result, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
