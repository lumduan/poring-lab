#!/usr/bin/env python3
"""Record a session for Phase 2 (ADR-0010, ADR-0024): GAME_REGION frames + the packet events.

    record_session.py --backend console --label outdoor-a --seconds 1200 --max-bytes 3G
    record_session.py --backend rdp --label calib --seconds 120 [--fps 1] --max-bytes 2G
    record_session.py --backend rdp --format png [--out DIR] ...        (lossless PNG, selectable)
    record_session.py --backend console --format png --fps 1 ...        (PNG, still selectable)

* THE DEFAULT FORMAT: console -> raw H.264 with an IDR every 1 s (Batt, 2026-10-04, C4; the S2
  client's own bitstream, console only; ADR-0010's 2026-10-04 note has the rates); rdp ->
  vpp-hevc444-10-q20, GPU-encoded video in place of PNG (ADR-0024, Batt 2026-11-09 "use the GPU
  video in place of PNG"; below). PNG stays selectable with --format png, and REQUIRED for the
  studies that fit pixel cues or templates (ADR-0024; their tools refuse a video session).
* --format h264: no frames are grabbed here. The S2 client writes the bitstream it decodes into its
  recording dir (S2_REC_DIR, a host bind mount: .s2-h264 under the local root, dot-named so
  dataset_ship never lists it), driven by a control file this script writes and re-touches (the
  client's dead-man switch). At the end the client's files move into the session as stream.h264,
  stream.idx.csv (one row per access unit), stream.hash.csv (a hash per decoded frame) and
  stream.done.json. The determinism check runs OFFLINE on the host after shipping
  (scripts/dataset_check.py: every frame against the live checksum); --check additionally runs
  s2spike.h264check in the gamestream container at the end (it contends with the live stream: a
  20-min session's check took ~12 min, so it is off by default).
* Limits the S2 client enforces (s2spike.h264rec.parse_control), checked here up front: at most
  H264_MAX_SECONDS per recording and an 8192 MB cap.

* Frames: GAME_REGION grabbed inside the backend container (ro_agent.Screen: same CLOCK_MONOTONIC
  as the packets), at most --fps, and only when the picture changed (a still scene costs nothing).
  --format png: lossless PNG in WebDataset-style tar shards (poring_dataset.shards).
  In console mode (S2, ADR-0014) the frames come from the S2 frame bus: each record carries the
  bus writer's `bus_frame_id`, `source` and the decode-complete time as `t_mono_ns`, and the
  recording STOPS on the first non-bus frame (an X grab there is a black or foreign picture).
  RDP mode grabs X (`source` x11, `bus_frame_id` -1).
* Packets: after the run, the sniffer's events for [t0 - 5 s, t1 + 5 s], with every name and chat
  line of anyone but the lab's own accounts replaced by an HMAC pseudonym (CLAUDE.md rule 9; the
  salt lives in data/dataset-pseudonym.salt, gitignored, never in a shard).
* Safety: the capture-backend lock must say --backend (ADR-0009); the quant IO guard
  (guarded_build's Guard) stops the recording on a breach -- the tolerant rule (DISK_RULE) on a
  disk sink, sustained stall only (RAM_RULE) on a tmpfs sink (Batt 2026-10-28); a hard size cap.
* PAUSE AND RESUME (Batt 2026-11-06 ~14:0x, xmas02-detector.md Amendment D; png and video):
  --io-rule sustained stops a part only on SUSTAINED stall (above 30 % for 30 s, no one-spike stop)
  on any sink. --resume N: a part stopped by the IO guard, or by a market-open window (weekdays
  09:30-10:15 and 14:00-14:45, CLAUDE.md rule 5), is followed by a NEW SESSION of the same label
  once the disk is calm (every capture cgroup at or under CALM_PCT for CALM_S, at least
  RESUME_MIN_S after the stop), at most N times and PAUSE_MAX_S of pauses in all; --seconds and
  --max-bytes then budget the whole recording. --state-file (in /dev/shm) tells a watch beside it
  whether frames are being banked (stage_items.py watch --recorder-state): JSON, re-written every
  frame and every pause second (`beat_ns`).
* THE VIDEO RECORDING (ADR-0024; gpu-recording.md 9.4, stage 3; rdp only, the default there):
  every kept frame (raw BGRA, alpha set to 255) goes to round 3's encoder (10-bit 4:4:4 HEVC, CQP
  20, all-intra) in the contained sidecar `media-rec` (scripts/media_rec.py: one named pipe in
  /dev/shm/poring-lab-mediarec; the stream lands in ~/poring-lab-rec/.media-rec and is renamed into
  the session as video.hevc, beside video.idx.csv: one row per kept frame with its frame_id,
  t_mono_ns, place in the stream and the PNG record's t_wall / bus_frame_id / source). No shards:
  the manifest's format is vpp-hevc444-10-q20, `frames` the frames in the stream, `video` the
  encoder's block. poring_dataset.frames reads it (and PNG) for every reader. LOSSY (stage 2: PSNR
  43.4 dB, the detector's boxes 0.9973 of PNG's; 0.84 vs 5.69 GB/h at 1 fps).
  - The sidecar must be UP: a video side that cannot start REFUSES the recording (every part; there
    is no PNG to fall back on). Start it first: guarded_build.py start:media-rec@60.
  - The video side failing mid-session (the encoder closed its pipe, a write blocked 20 s) STOPS
    the recording cleanly (stop_reason `video_failed: ...`): the frames already in the stream are
    the session. A frame the encoder's queue could not take is lost (its index row says so).
  - --out must be ~/poring-lab-rec (the sidecar's .media-rec is bound under it; a rename joins the
    two); --format png records to any --out.
* STAGE 2 (gpu-recording.md 9.1; Batt 2026-11-08 "do it now"): --also-png with the video format
  records the PNG session exactly as --format png AND the video twin of every kept frame. The
  manifest's format stays "png" (the PNG is the reference) and its `video` block describes the
  twin: an encoder that stops or falls behind ends the VIDEO side only, and its reason is recorded;
  a video side that cannot start refuses part 0 (a later --resume part records PNG only).
  --max-bytes and the local caps count both files.
* Sink (ADR-0010): the host's local disk, ~/poring-lab-rec (never ./data: vision mounts it).
  It is a buffer on the disk shared with live capture, so it is capped -- refused at the start, and
  stopped cleanly mid-recording, when the filesystem has < --min-free-gb free or more than
  --max-unshipped-gb of sessions wait under the root. scripts/dataset_ship.py ships them to the
  TrueNAS cold store (checksummed, verified, then deleted locally). A warning during SET hours.
"""

import argparse
import datetime as dt
import gzip
import hashlib
import hmac
import importlib.util
import io
import json
import os
import re
import secrets
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import dataset_ship  # noqa: E402
import lab_servers  # noqa: E402
import measure_delay  # noqa: E402
import ro_agent as r  # noqa: E402

from poring_backend.capture_lock import read_lock  # noqa: E402
from poring_dataset import frames as recorded_frames  # noqa: E402
from poring_dataset.shards import ShardWriter, write_manifest  # noqa: E402
from poring_dataset.timeline import session_events  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
SALT = ROOT / "data" / "dataset-pseudonym.salt"
# v6: the IO rule follows the sink (RAM: sustained only) + guard_rule; v5: h264 by default on
# console; v4: --format h264 + cpu; v3: bus ids (S2). Still 6 with --io-rule / --resume /
# --state-file (Amendment D): they add manifest fields (io_rule, part) only; frames, shards and
# packets are written as before. Still 6 with stage 2's side stream (gpu-recording.md 9.1): it
# adds manifest fields (video, png_writer_cpu_s) and files beside the shards, nothing else.
# v7 (ADR-0024, 2026-11-09): rdp records the video format by default (frames in video.hevc, no
# shards; video.idx.csv gains the PNG record's t_wall / bus_frame_id / source); manifest `kept`.
# A --format png session's frames, shards and packets are written exactly as in v6.
RECORDER_VERSION = 7
H264_MAX_SECONDS = 3570  # the client's time cap is 3600 s; we ask for seconds + 30
H264_MAX_MB = 8192  # the client's size cap
CAP_CHECK_S = 5.0  # how often the local caps are re-checked while recording
GAMESTREAM = "poring-lab-gamestream-1"
BACKEND = "poring-lab-backend-1"
VIDEO_FORMAT = recorded_frames.VIDEO_FORMAT  # media_rec.ARM: the rdp default (ADR-0024)
H264_ID = re.compile(r"^[0-9]{8}T[0-9]{6}-[a-z0-9][a-z0-9-]{0,47}$")  # s2spike.h264rec.ID_RE
TOUCH_S = 3.0  # the control file's dead-man touch (the client stops it after 15 s)
# SIGINT/SIGTERM end a recording CLEANLY (2026-10-05, the M4 re-run stops it when its spawns are
# done): the loop ends as on its duration, so the shards and the manifest are finalised.
STOP: dict[str, bool] = {"flag": False}


def request_stop(*_: object) -> None:
    STOP["flag"] = True


# --- pause and resume (Batt 2026-11-06, xmas02-detector.md Amendment D) ---------------------------
# "Go ahead, I grant the relaxation; a retry system that comes back and runs on is fine too, with:
# stop only when the disk is slow for 30 s straight, not for one spike."
SUSTAINED_RULE: dict[str, Any] = {"threshold": 30.0, "sustain": 30.0, "spike": None}
CALM_PCT = 10.0  # a resume waits until every capture cgroup's stall is at or under the tolerant
CALM_S = 60.0  # base threshold, for this long without a break,
RESUME_MIN_S = 120.0  # and at least this long after the stop
PAUSE_MAX_S = 3600.0  # all the pauses of one recording together; then it ends
CALM_WINDOW_S = 10.0  # the calm guard's averaging window (Guard's own)
OPEN_WINDOWS = ((dt.time(9, 30), dt.time(10, 15)), (dt.time(14, 0), dt.time(14, 45)))
RESUMABLE = ("io_guard:", "market_window")  # the stop reasons a part may be resumed after
STATE: dict[str, Any] = {"path": None, "doc": {}}


def in_open_window(when: dt.datetime | None = None) -> bool:
    """A market-open window (CLAUDE.md rule 5: no disk-heavy step 09:30-10:15 or 14:00-14:45 ICT,
    Monday to Friday)."""
    t = (when or dataset_ship.now()).astimezone(dataset_ship.BANGKOK)
    return t.weekday() < 5 and any(a <= t.time() < b for a, b in OPEN_WINDOWS)


def io_rule(a: argparse.Namespace) -> dict[str, Any] | None:
    """The IO rule a part runs under: --io-rule sustained, else None (the sink's: guard_rule)."""
    return SUSTAINED_RULE if getattr(a, "io_rule", "auto") == "sustained" else None


def _write_state() -> None:
    path = STATE["path"]
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(STATE["doc"]) + "\n")
    tmp.replace(path)


def set_state(state: str, **fields: Any) -> None:
    """The recorder's state for a watch beside it (--state-file): `state` (waiting | recording |
    finishing | paused | ended), `since_ns` (when it began), `beat_ns`, `session` + `part` (kept
    until changed), `reason`. A no-op without --state-file."""
    if STATE["path"] is None:
        return
    now = r.ns()
    keep = {k: STATE["doc"].get(k) for k in ("session", "part")}
    STATE["doc"] = {**keep, "reason": None, **fields, "state": state, "since_ns": now,
                    "beat_ns": now, "pid": os.getpid()}  # fmt: skip
    _write_state()


def beat() -> None:
    """Re-write the state file with a fresh `beat_ns` (each frame and each pause second)."""
    if STATE["path"] is None:
        return
    STATE["doc"]["beat_ns"] = r.ns()
    _write_state()


def wait_ready(first: bool, budget_s: float, *, guard_factory: Any = None, clock: Any = None,
               sleep: Any = None, opening: Any = None) -> tuple[bool, float]:  # fmt: skip
    """Before a part: outside the market-open windows and, before a RESUME (``first`` False), the
    calm guard silent (every capture cgroup at or under CALM_PCT) for CALM_S without a break, at
    least RESUME_MIN_S after the stop. Returns (ok, seconds waited); ok is False on a signal or when
    ``budget_s`` runs out."""
    clock = clock or time.monotonic
    sleep = sleep or time.sleep
    opening = opening or in_open_window
    t0 = clock()
    g = None if first else (guard_factory or calm_guard)()
    calm_since: float | None = None
    while True:
        now = clock()
        if STOP["flag"] or now - t0 > budget_s:
            return False, now - t0
        hit = g.breach() if g is not None else None
        busy = opening() or hit is not None or (g is not None and now - t0 < CALM_WINDOW_S)
        if busy:
            calm_since = None
        elif calm_since is None:
            calm_since = now
        if calm_since is not None and (
            first or (now - calm_since >= CALM_S and now - t0 >= RESUME_MIN_S)
        ):
            return True, now - t0
        beat()
        sleep(1.0)


def rec_dir(out: Path) -> Path:
    """The S2 client's recording dir on the host (compose.dev.yaml mounts it at /s2-rec)."""
    return Path(os.environ.get("S2_REC_DIR") or out / ".s2-h264")


def container_cpu_usec(name: str) -> int | None:
    cid = subprocess.run(["docker", "inspect", "-f", "{{.Id}}", name], capture_output=True,
                         text=True, check=False).stdout.strip()  # fmt: skip
    stat = Path(f"/sys/fs/cgroup/system.slice/docker-{cid}.scope/cpu.stat")
    if not cid or not stat.exists():
        return None
    for line in stat.read_text().splitlines():
        if line.startswith("usage_usec "):
            return int(line.split()[1])
    return None


class CpuMeter:
    """Average cores of the lab containers and of this process over the recording (C3); with
    ``extra``, those containers too (stage 2: the media-rec sidecar)."""

    def __init__(self, extra: tuple[str, ...] = ()) -> None:
        self.t0 = time.monotonic()
        self.c0 = {n: container_cpu_usec(n) for n in (GAMESTREAM, BACKEND, *extra)}
        self.self0 = os.times()
        self.wall = 0.0  # the span cores() averaged over (stage 2 turns cores back into seconds)

    def cores(self) -> dict[str, float | None]:
        wall = self.wall = time.monotonic() - self.t0
        out: dict[str, float | None] = {}
        for name, before in self.c0.items():
            after = container_cpu_usec(name)
            short = name.removeprefix("poring-lab-").removesuffix("-1")
            out[short] = (None if before is None or after is None or wall <= 0
                          else round((after - before) / 1e6 / wall, 3))  # fmt: skip
        t = os.times()
        used = (t.user - self.self0.user) + (t.system - self.self0.system)
        out["recorder_process"] = round(used / wall, 3) if wall > 0 else None
        return out


# The IO rule by sink (Batt 2026-10-28, gef10-detector.md 13y): RAM_RULE on tmpfs, else DISK_RULE.
# It lives in dataset_ship.py since 2026-10-29, because a ship follows the same rule by its
# sessions' root (Batt 2026-10-29, rogue-gef10.md AK-4).
DISK_RULE, RAM_RULE = dataset_ship.DISK_RULE, dataset_ship.RAM_RULE
fs_type, guard_rule = dataset_ship.fs_type, dataset_ship.guard_rule


def _guarded_build() -> Any:
    spec = importlib.util.spec_from_file_location(
        "guarded_build", ROOT / "scripts" / "guarded_build.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_guard(out: Path, rule: dict[str, Any] | None = None) -> Any:
    """The quant IO guard of a part: ``rule`` (--io-rule), else the sink's (guard_rule)."""
    module = _guarded_build()
    rule = rule or guard_rule(out)
    return module.Guard(module.cgroup_paths(), rule["threshold"], 10.0, sustain=rule["sustain"],
                        spike=rule["spike"])  # fmt: skip


def calm_guard() -> Any:
    """wait_ready's guard: a breach whenever any capture cgroup is above CALM_PCT (no sustain)."""
    module = _guarded_build()
    return module.Guard(module.cgroup_paths(), CALM_PCT, CALM_WINDOW_S, sustain=0.0, spike=None)


def parse_size(text: str) -> int:
    m = re.fullmatch(r"(\d+)([KMG]?)", text.upper())
    if m is None:
        raise SystemExit(f"bad size {text!r}")
    return int(m.group(1)) * {"": 1, "K": 1 << 10, "M": 1 << 20, "G": 1 << 30}[m.group(2)]


def pseudonymiser() -> Any:
    SALT.parent.mkdir(parents=True, exist_ok=True)
    if not SALT.exists():
        SALT.write_text(secrets.token_hex(32))
        SALT.chmod(0o600)
    key = bytes.fromhex(SALT.read_text().strip())
    env = r.env()
    lab = {env.get("RATHENA_GM_CHAR", ""), env.get("RATHENA_AGENT_CHAR", "")} - {""}

    def name(value: str) -> str:
        if not value or value in lab:
            return value
        return "p_" + hmac.new(key, value.encode(), hashlib.sha256).hexdigest()[:10]

    def event(e: dict[str, Any]) -> dict[str, Any]:
        e = dict(e)
        if e.get("type") == "entity_appear" and e.get("objtype") == 0:
            e["name"] = name(str(e.get("name", "")))
        if e.get("type") == "chat":
            speaker = str(e.get("speaker") or "")
            if speaker not in lab:
                e["speaker"] = name(speaker)
                e["text"] = "<pseudonymised>"
                e["raw_hex"] = ""
        return e

    return event


LOOKBACK_S = 30 * 60  # how far before t0 to look for the anchor (the last map change)


def packets_for(t0_ns: int, t1_ns: int) -> list[dict[str, Any]]:
    """The sniffer's events for [t0 - 5 s, t1 + 5 s] (the measurement window)."""
    return _events_since(t0_ns, 5, t0_ns - 5_000_000_000, t1_ns)


def session_packets(t0_ns: int, t1_ns: int) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    """A recording's events: from the last map change before t0 (so the player's position and the
    entities already on screen are known) through t1 + 5 s. See timeline.session_events."""
    events = _events_since(t0_ns, LOOKBACK_S + 5, t0_ns - (LOOKBACK_S + 5) * 1_000_000_000, t1_ns)
    return session_events(events, t0_ns, t1_ns, lookback_ns=LOOKBACK_S * 1_000_000_000)


def _events_since(t0_ns: int, back_s: float, lo_ns: int, t1_ns: int) -> list[dict[str, Any]]:
    since_wall = time.time() - (r.ns() - t0_ns) / 1e9
    files = measure_delay.events_files(since_wall - back_s)
    if not files:
        return []
    raw = subprocess.run(
        ["docker", "exec", lab_servers.sniffer(), "cat", *files], capture_output=True, check=True
    ).stdout
    out: list[dict[str, Any]] = []
    with gzip.GzipFile(fileobj=io.BytesIO(raw)) as fh:
        try:
            for line in fh:
                e = json.loads(line)
                if lo_ns <= int(e.get("t_mono_ns", 0)) <= t1_ns + 5_000_000_000:
                    out.append(e)
        except EOFError:
            pass
    return out


def record(a: argparse.Namespace) -> dict[str, Any]:
    lock = read_lock(ROOT / "state")
    if lock.backend != a.backend or lock.phase != "steady":
        raise r.Stop(f"the lock says {lock.backend}/{lock.phase}, not {a.backend}/steady")
    import bench  # the same config + hash as the benchmark

    caps = {"min_free": int(a.min_free_gb * 1e9), "max_unshipped": int(a.max_unshipped_gb * 1e9)}
    unshipped = dataset_ship.unshipped_bytes(a.out)
    refused = dataset_ship.local_caps(a.out, unshipped=unshipped, **caps)
    if refused:
        raise r.Stop(f"not recording: {refused}")
    if dataset_ship.in_set_hours():
        print("WARNING: SET hours -- the quant stack is busiest now; the IO guard stays armed",
              file=sys.stderr)  # fmt: skip
    config = bench.run_config(a.backend)
    chash = bench.benchlib.config_hash(config)
    session_id = f"{time.strftime('%Y%m%dT%H%M%S')}-{a.backend}-{a.label}"
    out = a.out / session_id
    if a.format == "h264":
        return record_h264(a, lock, config, chash, session_id, out, caps, unshipped)
    gx, gy, gw, gh = r.game_region()
    png = a.format == "png"  # PNG shards: alone, or with stage 2's video twin
    video = start_video(a, session_id, gw, gh)  # the video side (the frames, or the twin), or None
    if png:
        writer: Any = ShardWriter(out, png_level=a.png_level)
    else:
        out.mkdir(parents=True, exist_ok=True)
        writer = NoShards()
    cpu = CpuMeter(("poring-lab-media-rec-1",) if video is not None else ())
    guard = load_guard(a.out, io_rule(a))
    period = 1.0 / a.fps
    screen = r.Screen()
    stop_reason = "duration"
    t0 = r.ns()
    t_end = time.monotonic() + a.seconds
    prev: np.ndarray | None = None
    frame_id = skipped = repeats = 0
    png_cpu_s = 0.0  # this thread's CPU in the PNG writer (encode + tar), stage 2's comparison
    video_warned = False
    last_bus_id = -1
    sources: dict[str, int] = {}
    next_cap_check = time.monotonic() + CAP_CHECK_S
    resume = getattr(a, "resume", 0) > 0
    try:
        with subprocess.Popen(["ionice", "-c3", "-p", str(os.getpid())]) as p:
            p.wait()
        next_t = time.monotonic()
        set_state("recording", session=session_id, part=getattr(a, "part", 0))
        while time.monotonic() < t_end and not STOP["flag"]:
            t_cap, img, bus_id, source = screen.grab_meta(gx, gy, gw, gh)
            sources[source] = sources.get(source, 0) + 1
            if a.backend == "console" and source != "bus":
                stop_reason = "non_bus_frame: the S2 frame bus went away (console mode)"
                break
            bgr = img[:, :, :3].copy()
            if source == "bus" and bus_id == last_bus_id:
                repeats += 1  # no new decoded frame since the last grab
            elif prev is not None and np.array_equal(bgr, prev):
                skipped += 1
            else:
                rec = {"t_wall": time.strftime("%FT%T%z"), "bus_frame_id": bus_id, "source": source}
                if png:
                    t_png = time.thread_time()
                    writer.add(frame_id, t_cap, bgr, **rec)
                    png_cpu_s += time.thread_time() - t_png
                if video is not None:  # never blocks: a lagging encoder loses frames, not the loop
                    video.offer(frame_id, t_cap, img, rec)
                frame_id += 1
                prev = bgr
            last_bus_id = bus_id
            if video is not None and not video_warned and video.check():
                video_warned = True
                if not png:  # the video IS the recording: end it cleanly with what it holds
                    stop_reason = f"video_failed: {video.reason}"
                    break
                print(f"WARNING: the video side failed, the PNG recording goes on: "
                      f"{video.reason}", file=sys.stderr)  # fmt: skip
            if writer.bytes + (video.bytes() if video is not None else 0) > a.max_bytes:
                stop_reason = "size_cap"
                break
            hit = guard.breach()
            if hit:
                stop_reason = f"io_guard: {hit[0]} {hit[1]:.1f}% ({hit[2]})"
                break
            if time.monotonic() >= next_cap_check:
                next_cap_check += CAP_CHECK_S
                extra = writer.bytes + (video.bytes() if video is not None else 0)
                full = dataset_ship.local_caps(a.out, unshipped=unshipped, extra=extra, **caps)
                if full:
                    stop_reason = f"local_cap: {full}"
                    break
                if resume and in_open_window():
                    stop_reason = "market_window: a market-open window began (CLAUDE.md rule 5)"
                    break
            beat()
            next_t += period
            time.sleep(max(0.0, next_t - time.monotonic()))
    finally:
        set_state("finishing", reason=stop_reason)
        writer.close()
        vinfo = finish_video(video, out)
    if STOP["flag"] and stop_reason == "duration":
        stop_reason = "stopped by signal"
        screen.close()
    t1 = r.ns()
    cpu_cores = cpu.cores()
    freezes = freeze_report(t0, t1)
    events, anchor = write_packets(out, t0, t1)
    seconds = (t1 - t0) / 1e9
    vbytes = video_file_bytes(out) if video is not None else 0
    frames, nbytes = (writer.frames, writer.bytes) if png else (served_frames(out, vinfo), vbytes)
    manifest = {
        "session_id": session_id, "recorder_version": RECORDER_VERSION,
        "backend": a.backend, "server": lab_servers.server(), "lock_seq": lock.seq,
        "config": config, "config_hash": chash,
        "game_region": [gx, gy, gw, gh], "fps_cap": a.fps,
        "png_level": a.png_level if png else None,
        "shards": writer.shards, "kept": frame_id,
        "frames": frames, "unchanged_skipped": skipped, "bus_repeats": repeats,
        "frame_sources": sources, "bytes": nbytes,
        "t0_mono_ns": t0, "t1_mono_ns": t1, "seconds": round(seconds, 1),
        "mb_per_min": round(nbytes / 1e6 / max(seconds / 60, 1e-9), 1),
        "stop_reason": stop_reason, "guard": guard.summary(), "guard_rule": guard.describe(),
        "packet_events": len(events),
        "packet_anchor": anchor, "pseudonymised": True, "freezes": freezes,
        "sink": {"root": str(a.out), **caps}, "format": a.format, "cpu_cores": cpu_cores,
        "io_rule": getattr(a, "io_rule", "auto"), "part": getattr(a, "part", 0),
        "png_writer_cpu_s": round(png_cpu_s, 3), "cpu_wall_s": round(cpu.wall, 3),
    }  # fmt: skip
    if vinfo is not None:
        manifest["video"] = vinfo
    write_manifest(out, manifest)
    keys = ("format", "frames", "bytes", "seconds", "mb_per_min", "stop_reason", "packet_events",
            "cpu_cores")  # fmt: skip
    res = {"dir": str(out), **{k: manifest[k] for k in keys},
           "bytes_total": writer.bytes + vbytes}  # fmt: skip
    if vinfo is not None:
        res["video"] = {k: vinfo.get(k) for k in ("status", "reason", "fed", "by_status")}
    return res


class NoShards:
    """The PNG writer's stand-in for a video-only recording: no shards, nothing written."""

    def __init__(self) -> None:
        self.shards: list[str] = []
        self.frames = 0
        self.bytes = 0

    def close(self) -> None:
        pass


def video_file_bytes(out: Path) -> int:
    path = out / recorded_frames.VIDEO_FILE
    return path.stat().st_size if path.exists() else 0


def served_frames(out: Path, vinfo: dict[str, Any] | None) -> int:
    """A video-only session's ``frames``: the fed frames the stream holds (a stream cut short by
    its encoder holds fewer than were fed). The access units are counted once here (one scan of
    the file just written) and recorded in ``video.access_units``."""
    fed = int((vinfo or {}).get("fed") or 0)
    path = out / recorded_frames.VIDEO_FILE
    try:
        aus = len(recorded_frames.stream_access_units(path)) if path.exists() else 0
    except OSError as exc:  # the manifest is still written; the reader counts again
        if vinfo is not None:
            vinfo["access_units_error"] = f"{type(exc).__name__}: {exc}"
        return fed
    if vinfo is not None:
        vinfo["access_units"] = aus
    return min(fed, aus)


def start_video(a: argparse.Namespace, session_id: str, w: int, h: int) -> Any:
    """The video side (``a.video``): a started media_rec.VideoFeed, or None without one. A video
    side that cannot start REFUSES the recording: always when the video holds the frames
    (video-only: there is nothing to fall back on; start the sidecar and retry), and in stage 2's
    side-by-side the first part; a later side-by-side part (--resume) records PNG only, the reason
    in its manifest (the PNG is the reference)."""
    if not getattr(a, "video", None):
        return None
    import media_rec

    feed = media_rec.VideoFeed(session_id, w, h, a.max_bytes, ctl=media_rec.CTL,
                               rec=media_rec.rec_dir(a.out))  # fmt: skip
    try:
        feed.start()
    except media_rec.VideoRefused as exc:
        if a.format != "png" or getattr(a, "part", 0) == 0:
            raise r.Stop(f"not recording: the video side cannot start: {exc}") from exc
        print(f"WARNING: part {a.part}: the video side cannot start, PNG only: {exc}",
              file=sys.stderr)  # fmt: skip
    return feed


def finish_video(video: Any, out: Path) -> dict[str, Any] | None:
    """The side stream's end (EOF to the encoder, its files renamed into ``out``) -> the manifest's
    ``video`` block. Never raises: a failure here is recorded, the PNG session is finalised."""
    if video is None:
        return None
    if video.status == "refused":
        return video.summary()
    try:
        info: dict[str, Any] = video.finish(out)
    except Exception as exc:  # noqa: BLE001 -- the PNG session must still get its manifest
        info = {**video.summary(), "status": "failed",
                "reason": f"finish: {type(exc).__name__}: {exc}"}  # fmt: skip
    return info


def record_parts(a: argparse.Namespace, rec: Any = None) -> dict[str, Any]:
    """--resume / --state-file (Amendment D): one recording as PARTS, each its own session of the
    same label. A part stopped by the IO guard or a market-open window is followed by the next once
    wait_ready says so, at most --resume times and PAUSE_MAX_S of pauses in all; --seconds and
    --max-bytes budget the whole recording. Any other stop (its duration, the size or local cap, a
    signal, a refusal) ends it. The state file ends "ended" whatever happens. ``rec``: the part
    recorder (tests; default record)."""
    if a.format not in ("png", VIDEO_FORMAT):
        raise r.Stop(f"--resume / --state-file: png or {VIDEO_FORMAT} recordings only")
    rec = rec or record
    parts: list[dict[str, Any]] = []
    left_s, left_b, paused_s, end = a.seconds, a.max_bytes, 0.0, "duration"
    try:
        while True:
            set_state("waiting" if not parts else "paused", reason=None if not parts else end)
            ok, waited = wait_ready(not parts, PAUSE_MAX_S - paused_s)
            paused_s += waited
            if not ok:
                end = "stopped by signal" if STOP["flag"] else f"pause_cap: {PAUSE_MAX_S:.0f} s"
                break
            part = argparse.Namespace(**{**vars(a), "seconds": left_s, "max_bytes": left_b,
                                         "part": len(parts)})  # fmt: skip
            res = rec(part)
            parts.append(res)
            print(json.dumps({"part": len(parts) - 1, **res}), flush=True)
            left_s -= res["seconds"]
            left_b -= res.get("bytes_total", res["bytes"])  # stage 2: the PNG and its video twin
            end = res["stop_reason"]
            if (STOP["flag"] or not end.startswith(RESUMABLE) or len(parts) > a.resume
                    or left_s <= 0 or left_b <= 0):  # fmt: skip
                break
    except r.Stop as exc:
        end = f"refused: {exc}"
    finally:
        set_state("ended", reason=end)
    return {"parts": len(parts), "sessions": [p["dir"] for p in parts], "end": end,
            "paused_s": round(paused_s, 1), "frames": sum(p["frames"] for p in parts),
            "bytes": sum(p["bytes"] for p in parts)}  # fmt: skip


def write_control(directory: Path, text: str) -> None:
    tmp = directory / ".control.tmp"
    tmp.write_text(text + "\n")
    tmp.replace(directory / "control")
    if (directory / "control").read_text().strip() != text:
        raise r.Stop("the S2 recorder's control file did not read back")


def h264_freezes(idx: Path) -> dict[str, Any] | None:
    """Freeze spans from the recording's own index (the decode-complete time of every frame)."""
    from poring_env.freshness import FREEZE_MS, freeze_spans

    times = []
    with idx.open() as f:
        next(f)
        for line in f:
            parts = line.rstrip("\n").split(",")
            if len(parts) == 10 and int(parts[1]) >= 0:
                times.append(int(parts[9]))
    if len(times) < 2:
        return None
    spans = freeze_spans(times, FREEZE_MS)
    return {"threshold_ms": FREEZE_MS, "frames": len(times), "count": len(spans),
            "max_ms": round(max(((b - c) / 1e6 for c, b in spans), default=0.0), 1),
            "spans_ns": [[c, b] for c, b in spans]}  # fmt: skip


def record_h264(
    a: argparse.Namespace, lock: Any, config: dict[str, Any], chash: str, session_id: str,
    out: Path, caps: dict[str, int], unshipped: int,
) -> dict[str, Any]:  # fmt: skip
    if a.backend != "console":
        raise r.Stop("--format h264 records the S2 client's bitstream: console mode only")
    if not H264_ID.match(session_id):
        raise r.Stop("--format h264: the label must be lowercase letters, digits and '-'")
    rec = rec_dir(a.out)
    if not rec.is_dir():
        raise r.Stop(f"{rec} does not exist (the S2 recording dir; compose.dev.yaml S2_REC_DIR)")
    for stale in rec.glob(f"*{session_id}*"):
        raise r.Stop(f"{stale} already exists")
    guard = load_guard(a.out, io_rule(a))
    gx, gy, gw, gh = r.game_region()
    max_mb = a.max_bytes / 1e6
    part = rec / f".{session_id}.h264"
    cpu = CpuMeter()
    stop_reason = "duration"
    t0 = r.ns()
    write_control(rec, f"start {session_id} {a.idr_every:g} {a.seconds + 30:.0f} {max_mb:.0f}")
    try:
        deadline = time.monotonic() + 5
        while not part.exists():
            if time.monotonic() > deadline:
                raise r.Stop("the S2 client did not start the recording in 5 s (is it streaming "
                             "with --h264-rec? docker logs poring-lab-gamestream-1)")  # fmt: skip
            time.sleep(0.2)
        t_end = time.monotonic() + a.seconds
        next_touch = next_cap = time.monotonic()
        while time.monotonic() < t_end and not STOP["flag"]:
            now = time.monotonic()
            if now >= next_touch:
                os.utime(rec / "control")  # the dead-man touch
                next_touch = now + TOUCH_S
            if not part.exists():
                stop_reason = "the client ended the recording (stream end or cap)"
                break
            hit = guard.breach()
            if hit:
                stop_reason = f"io_guard: {hit[0]} {hit[1]:.1f}% ({hit[2]})"
                break
            if now >= next_cap:
                next_cap = now + CAP_CHECK_S
                full = dataset_ship.local_caps(a.out, unshipped=unshipped,
                                               extra=part.stat().st_size, **caps)  # fmt: skip
                if full:
                    stop_reason = f"local_cap: {full}"
                    break
            time.sleep(0.5)
    finally:
        write_control(rec, "stop")
    if STOP["flag"] and stop_reason == "duration":
        stop_reason = "stopped by signal"
    done = rec / f"{session_id}.done.json"
    deadline = time.monotonic() + 60
    while not done.exists():
        if time.monotonic() > deadline:
            raise r.Stop(f"the S2 client did not finish {session_id} in 60 s")
        time.sleep(0.5)
    t1 = r.ns()
    cpu_cores = cpu.cores()
    summary = json.loads(done.read_text())
    check = None
    if a.check:
        cmd = ["docker", "exec", GAMESTREAM, "python3", "-m", "s2spike.h264check",
               f"/s2-rec/{session_id}"]  # fmt: skip
        res = subprocess.run(cmd, capture_output=True, text=True, check=False)
        lines = res.stdout.strip().splitlines()
        check = json.loads(lines[-1]) if lines else {"error": res.stderr[-400:]}
        check["exit"] = res.returncode
    out.mkdir(parents=True)
    for kind in ("h264", "idx.csv", "hash.csv", "check.json", "done.json"):
        src = rec / f"{session_id}.{kind}"
        if src.exists():
            src.rename(out / f"stream.{kind}")  # same filesystem: a rename, no copy
    events, anchor = write_packets(out, t0, t1)
    seconds = (t1 - t0) / 1e9
    size = (out / "stream.h264").stat().st_size
    manifest = {
        "session_id": session_id, "recorder_version": RECORDER_VERSION, "format": "h264",
        "backend": a.backend, "server": lab_servers.server(), "lock_seq": lock.seq,
        "config": config, "config_hash": chash,
        "game_region": [gx, gy, gw, gh], "idr_every_s": a.idr_every, "shards": [],
        "frames": summary.get("frames"), "bytes": size, "t0_mono_ns": t0, "t1_mono_ns": t1,
        "seconds": round(seconds, 1), "mb_per_min": round(size / 1e6 / max(seconds / 60, 1e-9), 1),
        "stop_reason": stop_reason, "guard": guard.summary(), "guard_rule": guard.describe(),
        "packet_events": len(events),
        "packet_anchor": anchor, "pseudonymised": True,
        "freezes": h264_freezes(out / "stream.idx.csv"), "stream": summary, "check": check,
        "cpu_cores": cpu_cores, "sink": {"root": str(a.out), **caps},
    }  # fmt: skip
    write_manifest(out, manifest)
    keys = ("frames", "bytes", "mb_per_min", "stop_reason", "packet_events", "cpu_cores")
    return {"dir": str(out), **{k: manifest[k] for k in keys}, "check": check}


def freeze_report(t0: int, t1: int) -> dict[str, Any] | None:
    """Freeze spans of the S2 stream over [t0, t1] (the frame-age guard, 2026-10-04): gaps above
    FREEZE_MS between consecutive decoded frames, from the S2 client's per-frame log. None in RDP
    mode or when the log is unavailable (stated, never guessed)."""
    from poring_env.freshness import FREEZE_MS, freeze_spans

    cmd = ["docker", "exec", "poring-lab-gamestream-1", "cat", "/tmp/s2spike/frames.csv"]
    res = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if res.returncode != 0:
        return None
    times = []
    for line in res.stdout.splitlines()[1:]:
        parts = line.split(",")
        if len(parts) == 9 and parts[7].isdigit() and t0 <= int(parts[7]) <= t1:
            times.append(int(parts[7]))
    if len(times) < 2:
        return None
    spans = freeze_spans(times, FREEZE_MS)
    return {
        "threshold_ms": FREEZE_MS, "frames": len(times), "count": len(spans),
        "max_ms": round(max(((b - a) / 1e6 for a, b in spans), default=0.0), 1),
        "spans_ns": [[a, b] for a, b in spans],
    }  # fmt: skip


def write_packets(
    out: Path, t0: int, t1: int
) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    events, anchor = session_packets(t0, t1)
    pseudo = pseudonymiser()
    with gzip.open(out / "packets.jsonl.gz", "wt") as fh:
        for e in events:
            fh.write(json.dumps(pseudo(e), sort_keys=True) + "\n")
    return events, anchor


def repack(session: Path) -> dict[str, Any]:
    """Rebuild a session's packets.jsonl.gz from the sniffer's archive (kept 7 days) with the
    current window rule, and update the manifest. Frames are untouched."""
    manifest = json.loads((session / "manifest.json").read_text())
    events, anchor = write_packets(session, manifest["t0_mono_ns"], manifest["t1_mono_ns"])
    manifest.update(
        packet_events=len(events), packet_anchor=anchor, recorder_version=RECORDER_VERSION
    )
    write_manifest(session, manifest)
    return {"dir": str(session), "packet_events": len(events), "packet_anchor": anchor}


def main() -> int:
    signal.signal(signal.SIGINT, request_stop)
    signal.signal(signal.SIGTERM, request_stop)
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--repack", type=Path, help="rebuild an existing session's packets file")
    ap.add_argument("--backend", choices=["rdp", "console"])
    ap.add_argument(
        "--server", choices=sorted(lab_servers.SNIFFERS), default=None,
        help="which server's sniffer holds the packets (default: $PORING_SERVER or lab-rathena)",
    )  # fmt: skip
    ap.add_argument("--label")
    ap.add_argument("--seconds", type=float, default=120.0)
    ap.add_argument("--fps", type=float, default=1.0,
                    help="png / video: the frame rate cap (Batt: 1)")  # fmt: skip
    ap.add_argument(
        "--format",
        choices=["png", "h264", VIDEO_FORMAT],
        default=None,
        help=f"default: h264 on console (Batt 2026-10-04), {VIDEO_FORMAT} on rdp (ADR-0024, "
        "Batt 2026-11-09: GPU video in place of PNG; the media-rec sidecar must be up); png: "
        "lossless PNG shards (still selectable; required by the cue-fitting studies)",
    )
    ap.add_argument(
        "--also-png",
        action="store_true",
        help=f"with {VIDEO_FORMAT} (the rdp default): every kept frame to BOTH the PNG shards and "
        "the encoder sidecar (stage 2's side-by-side, gpu-recording.md 9.1); the PNG is the "
        "reference",
    )
    ap.add_argument(
        "--idr-every",
        type=float,
        default=1.0,
        help="h264: ask for an IDR every N s (default 1; 0 = never)",
    )
    ap.add_argument(
        "--check",
        dest="check",
        action="store_true",
        help="h264: also run s2spike.h264check in gamestream at the end (contends with the stream)",
    )
    ap.add_argument(
        "--png-level", type=int, choices=range(0, 10), default=1,
        help="zlib level of the lossless PNGs: 1 fast (default), 6 smaller and slower",
    )  # fmt: skip
    ap.add_argument("--out", type=Path, default=dataset_ship.LOCAL_ROOT)
    ap.add_argument(
        "--io-rule", choices=["auto", "sustained"], default="auto",
        help="auto: the sink's rule (disk: >10%% for 30 s or >25%% once); sustained: >30%% for "
             "30 s only, on any sink (Batt 2026-11-06, Amendment D)",
    )  # fmt: skip
    ap.add_argument(
        "--resume", type=int, default=0,
        help="png / video: resume after an IO-guard or market-window stop as a new session of "
             "the same label, at most N times (Amendment D); --seconds / --max-bytes budget all "
             "parts",
    )  # fmt: skip
    ap.add_argument(
        "--state-file", type=Path, default=None,
        help="png / video: the recorder's state (JSON, under /dev/shm) for a watch beside it",
    )  # fmt: skip
    ap.add_argument(
        "--max-bytes",
        type=parse_size,
        required=True,
        help="hard size cap for this session, e.g. 12G (explicit: no default)",
    )
    ap.add_argument(
        "--min-free-gb",
        type=float,
        default=dataset_ship.MIN_FREE_BYTES / 1e9,
        help="refuse / stop below this much free space on --out's filesystem",
    )
    ap.add_argument(
        "--max-unshipped-gb",
        type=float,
        default=dataset_ship.MAX_UNSHIPPED_BYTES / 1e9,
        help="refuse / stop above this much unshipped data under --out",
    )
    a = ap.parse_args()
    lab_servers.select(a.server)  # every packet read below uses this server's sniffer
    if a.repack:
        print(json.dumps(repack(a.repack)))
        return 0
    if not a.backend or not a.label:
        raise r.Stop("--backend and --label are required to record")
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", a.label):
        raise r.Stop("label: letters, digits, _ . - only")
    if str(a.out.resolve()).startswith(str((ROOT / "data").resolve())):
        raise r.Stop("never under ./data: vision mounts it (ADR-0010)")
    resolve_format(a)
    if a.resume or a.state_file:
        if a.resume < 0:
            raise r.Stop("--resume: 0 or more")
        if a.state_file is not None:
            if not str(a.state_file.resolve()).startswith("/dev/shm/"):
                raise r.Stop("--state-file: under /dev/shm (rule 7)")
            STATE["path"] = a.state_file
        out = record_parts(a)
        print(json.dumps(out))
        return 1 if out["end"].startswith("refused") else 0
    print(json.dumps(record(a)))
    return 0


def resolve_format(a: argparse.Namespace) -> None:
    """The default format per backend: h264 on console (Batt 2026-10-04), VIDEO_FORMAT on rdp
    (ADR-0024, Batt 2026-11-09: the GPU video in place of PNG); png stays selectable. The video
    format alone is the video-only recording (``format`` VIDEO_FORMAT, ``video`` set); with
    --also-png it is stage 2's side-by-side (gpu-recording.md 9.1: ``format`` png, ``video`` set,
    the PNG the reference). The S2 client's own limits are checked up front for h264 (it silently
    ignores an out-of-range start)."""
    also = getattr(a, "also_png", False)
    a.video = None
    if a.format is None:
        a.format = "h264" if a.backend == "console" else VIDEO_FORMAT
    if a.format == VIDEO_FORMAT:
        if a.backend != "rdp":
            raise r.Stop(f"--format {VIDEO_FORMAT}: rdp only (the console records its own H.264)")
        out = getattr(a, "out", dataset_ship.LOCAL_ROOT)
        if out.resolve() != dataset_ship.LOCAL_ROOT.resolve():
            raise r.Stop(f"--format {VIDEO_FORMAT} (the rdp default): --out must be "
                         f"{dataset_ship.LOCAL_ROOT} (the sidecar writes its .media-rec there; a "
                         "rename joins the two); --format png records to any --out")  # fmt: skip
        a.format, a.video = ("png" if also else VIDEO_FORMAT), VIDEO_FORMAT
        return
    if also:
        raise r.Stop(f"--also-png goes with {VIDEO_FORMAT} (the rdp default), not --format "
                     f"{a.format}")  # fmt: skip
    if a.format != "h264":
        return
    if a.seconds > H264_MAX_SECONDS:
        raise r.Stop(f"--format h264: at most {H264_MAX_SECONDS} s per recording")
    if a.max_bytes / 1e6 > H264_MAX_MB:
        raise r.Stop(f"--format h264: --max-bytes at most {H264_MAX_MB} MB (the client's cap)")
    if not 0 <= a.idr_every <= 60:
        raise r.Stop("--idr-every: 0..60 s")


if __name__ == "__main__":
    sys.exit(main())
