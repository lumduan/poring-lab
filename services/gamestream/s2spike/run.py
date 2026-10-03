"""s2spike entry points (run inside the gamestream container; the loop starts `stream`).

    python3 -m s2spike selftest     offline: library + layout, decoder (low_delay), VK, identity
    python3 -m s2spike serverinfo   online, starts NOTHING: PairStatus for the lab cert, currentgame
    python3 -m s2spike stream ...   ONLY on console/steady, no RDP window, no other lab client:
                                    launch/resume -> receive -> decode once -> evidence PNG +
                                    stats every 2 s (/tmp/s2spike) [+ --mirror-x: the X shim]
                                    [--framebus PATH: V3b -- every decoded frame goes to the
                                    frame bus (the backend and the bot read it); the X window
                                    only receives input and is never painted]
                                    [--framebus PATH --input-socket PATH: S2 (step 3) -- input
                                    comes from the backend's mux over a unix socket, NO X window
                                    takes part (an unmapped presence marker keeps the interlocks)]
                                    [--evidence thread, --decode-threads N, --fps 60: the
                                    key->paint tail experiments (docs/benchmarks/
                                    s2-latency-experiments.md); frames.csv = per-frame timing]

`stream` never relaunches and never sends /cancel: the capture backend's `hold` / `to-rdp` end the
session (Moonlight-qt's `quit` = Sunshine /cancel, host-wide). It exits when Sunshine ends the
connection ("Connection terminated", the line capture_backend waits for) or on SIGTERM.
"""

from __future__ import annotations

import argparse
import collections
import ctypes
import json
import os
import secrets
import signal
import sys
import threading
import time
from pathlib import Path
from typing import Any

from . import identity, lockstate, nvhttp, pngout
from . import limelight as ll

OUT = Path(os.environ.get("S2_OUT_DIR", "/tmp/s2spike"))
LIB_DIR = Path(os.environ.get("S2_LIB_DIR", "/opt/s2spike/lib"))
EVIDENCE_EVERY_S = 2.0
TIMING_MAX_BYTES = 16 * 1024 * 1024  # frames.csv rotates to frames.csv.1 (the /tmp tmpfs is 640m)
TIMING_HEADER = ("frame_id,frame_number,frame_type,receive_ms,enqueue_ms,host_latency_01ms,"
                 "t_dequeue_ns,t_publish_ns,decode_us\n")  # fmt: skip


class TimingLog:
    """Per-frame timing (experiment 3d): the decode thread only appends a tuple; a flusher thread
    writes them to OUT/frames.csv once a second. receive_ms / enqueue_ms are moonlight-common-c's
    PltGetMillis() (CLOCK_MONOTONIC in ms on Linux at the pinned commit -- the same clock as
    t_*_ns); host_latency_01ms is Sunshine's own capture->send time in 1/10 ms (0 = not sent)."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.rows: collections.deque[tuple[int, ...]] = collections.deque(maxlen=20000)
        self.dropped = 0
        self._stop = threading.Event()
        path.parent.mkdir(parents=True, exist_ok=True)
        for old in (path, path.with_name(path.name + ".1")):
            old.unlink(missing_ok=True)  # one stream per file: the bench joins by t_publish_ns
        path.write_text(TIMING_HEADER)
        self._thread = threading.Thread(target=self._flush_loop, name="s2spike-timing",
                                        daemon=True)  # fmt: skip
        self._thread.start()

    def add(self, row: tuple[int, ...]) -> None:
        if len(self.rows) == self.rows.maxlen:
            self.dropped += 1
        self.rows.append(row)

    def flush(self) -> None:
        lines = []
        while self.rows:
            lines.append(",".join(map(str, self.rows.popleft())))
        if not lines:
            return
        if self.path.stat().st_size > TIMING_MAX_BYTES:
            self.path.replace(self.path.with_name(self.path.name + ".1"))
            self.path.write_text(TIMING_HEADER)
        with self.path.open("a") as f:
            f.write("\n".join(lines) + "\n")

    def _flush_loop(self) -> None:
        while not self._stop.wait(1.0):
            self.flush()

    def close(self) -> None:
        self._stop.set()
        self._thread.join(timeout=2)
        self.flush()


def log(msg: str) -> None:
    print(f"{time.strftime('%Y-%m-%dT%H:%M:%S%z')} s2spike: {msg}", file=sys.stderr, flush=True)


def selftest() -> int:
    identity.harden_process(b"s2selftest")  # NOT `s2spike`: it is not a stream client
    ok = True
    try:
        lib = ll.Lib(LIB_DIR)
        log(f"moonlight-common-c {lib.sha[:12]}: loaded, ctypes layout == pinned headers")
        params = lib.LiGetLaunchUrlQueryParameters().decode()
        log(f"LiGetLaunchUrlQueryParameters: {params!r}")
    except Exception as exc:  # noqa: BLE001 -- report every failure, then exit non-zero
        log(f"FAIL library: {exc}")
        ok = False
    try:
        from .decode import Decoder

        d = Decoder()
        log(f"PyAV decoder: h264, low_delay={d.low_delay}, thread_type={d.ctx.thread_type}")
        ok &= d.low_delay
    except Exception as exc:  # noqa: BLE001
        log(f"FAIL decoder: {exc}")
        ok = False
    from .vk import EVDEV_TO_VK

    log(f"VK table: {len(EVDEV_TO_VK)} physical keys")
    try:
        ident = identity.load()
        log(f"identity: certificate + key + paired host present; apps {sorted(ident.apps)}")
        identity.client_context(ident)
        log("identity: TLS context built from a sealed memfd (no file)")
    except Exception as exc:  # noqa: BLE001
        log(f"FAIL identity: {exc}")
        ok = False
    log("selftest OK" if ok else "selftest FAILED")
    return 0 if ok else 1


def serverinfo(host: str) -> int:
    identity.harden_process(b"s2serverinfo")  # NOT `s2spike`: it is not a stream client
    nv = nvhttp.NvHttp(host, identity.load())
    info = nv.serverinfo()
    shown = ("PairStatus", "currentgame", "state", "appversion", "GfeVersion",
             "ServerCodecModeSupport", "HttpsPort", "MaxLumaPixelsHEVC")  # fmt: skip
    for key in shown:
        log(f"serverinfo {key} = {info.get(key, '')}")
    log(f"applist: {sorted(nv.applist())}")
    return 0 if info.get("PairStatus") == "1" else 2


class Stream:
    """One connection: callbacks, the pull-renderer decode thread, evidence, the optional shim."""

    def __init__(self, args: argparse.Namespace, lib: ll.Lib) -> None:
        self.args, self.lib = args, lib
        self.const = ll.CONSTANTS
        self.width, self.height = (int(v) for v in args.size.split("x"))
        self.terminated = threading.Event()
        self.started = threading.Event()
        self.error = 0
        self.mirror: Any = None
        self.bus: Any = None  # framebus.FrameBusWriter (V3b)
        self.presence: Any = None  # presence.Presence (S2: the unmapped marker window)
        self.input_server: Any = None  # input_socket.InputServer (S2)
        self.timing: TimingLog | None = None
        # --evidence thread: the decode thread hands (frame, snapshot) over, latest only
        self._ev_lock = threading.Lock()
        self._ev_item: tuple[Any, dict[str, Any]] | None = None
        self._ev_wake = threading.Event()
        self.frame_id = 0
        self.stats: dict[str, Any] = {"stages": []}
        # Keep every ctypes callback object alive for the connection's lifetime.
        self._cbs = {
            "stage_start": ll.ClStage(lambda s: self._stage("starting", s)),
            "stage_done": ll.ClStage(lambda s: self._stage("complete", s)),
            "stage_fail": ll.ClStageFailed(self._stage_failed),
            "started": ll.ClVoid(self._started),
            "terminated": ll.ClTerminated(self._terminated),
            "status": ll.ClStatus(lambda st: log(f"connection status {st}")),
            "setup": ll.DrSetup(self._dr_setup),
            "log": ll.LogSink(
                lambda line: log("mlcc: " + line.decode("utf-8", "replace").rstrip())
            ),
        }

    def _stage(self, what: str, stage: int) -> None:
        name = self.lib.LiGetStageName(stage).decode()
        self.stats["stages"].append(f"{what} {name}")
        log(f"stage {what}: {name}")

    def _stage_failed(self, stage: int, err: int) -> None:
        log(f"stage FAILED: {self.lib.LiGetStageName(stage).decode()} (error {err})")
        self.error = err

    def _started(self) -> None:
        log("connection started")
        self.started.set()

    def _terminated(self, err: int) -> None:
        self.error = err
        log(f"Connection terminated (error {err})")  # capture_backend's STREAM_END_RX matches this
        self.terminated.set()
        self.lib.LiWakeWaitForVideoFrame()

    def _dr_setup(self, fmt: int, w: int, h: int, fps: int, _ctx: Any, _flags: int) -> int:
        log(f"decoder setup: format 0x{fmt:x} {w}x{h}@{fps}")
        return 0

    def run(self) -> int:
        nv = nvhttp.NvHttp(self.args.host, identity.load())
        info = nv.serverinfo()
        if info.get("PairStatus") != "1":
            log("REFUSED: the lab certificate is not paired with this host")
            return 3
        apps = nv.applist()
        if self.args.app not in apps:
            log(f"REFUSED: no app {self.args.app!r} on the host ({sorted(apps)})")
            return 3
        if self.args.framebus:
            # BEFORE the launch: a ring that cannot be created must never leave Sunshine's app
            # running (2026-10-03: the second stream of a room SIGBUSed on a full tmpfs).
            from .framebus import FrameBusError, FrameBusWriter

            try:
                self.bus = FrameBusWriter(
                    self.args.framebus, max_width=self.width, max_height=self.height
                )
            except FrameBusError as exc:
                log(f"REFUSED: frame bus: {exc}")
                return 3
            log(f"frame bus: {self.args.framebus} ({self.bus.slots} slots, reserved)")
        c = self.const
        cfg = ll.STREAM_CONFIGURATION()
        self.lib.LiInitializeStreamConfiguration(ctypes.byref(cfg))
        cfg.width, cfg.height, cfg.fps = self.width, self.height, self.args.fps
        cfg.bitrate, cfg.packetSize = self.args.bitrate, 1392
        cfg.streamingRemotely = c["STREAM_CFG_LOCAL"]
        cfg.audioConfiguration = c["AUDIO_CONFIGURATION_STEREO"]
        cfg.supportedVideoFormats = c["VIDEO_FORMAT_H264"]
        cfg.encryptionFlags = c["ENCFLG_ALL"]  # what Moonlight-qt picks with AES-NI and > 2 cores
        key, iv = secrets.token_bytes(16), secrets.token_bytes(4) + bytes(12)
        cfg.remoteInputAesKey, cfg.remoteInputAesIv = key, iv
        resume = info.get("currentgame", "0") not in ("", "0")
        params = nvhttp.LaunchParams(
            app_id=apps[self.args.app], width=self.width, height=self.height, fps=self.args.fps,
            rikey=key, riiv=iv, audio_configuration=cfg.audioConfiguration,
        )  # fmt: skip
        li_params = self.lib.LiGetLaunchUrlQueryParameters().decode()
        log(f"{'resume' if resume else 'launch'} app {self.args.app} "
            f"{self.width}x{self.height}@{self.args.fps}")  # fmt: skip
        rtsp = nv.launch(params, li_params, resume=resume)
        if not rtsp:
            log("REFUSED: the host returned no sessionUrl0")
            self._close()  # the reserved ring goes too
            return 3
        si = ll.SERVER_INFORMATION()
        self.lib.LiInitializeServerInformation(ctypes.byref(si))
        keep = [self.args.host.encode(), info.get("appversion", "").encode(),
                info.get("GfeVersion", "").encode(), rtsp.encode()]  # fmt: skip
        si.address, si.serverInfoAppVersion, si.serverInfoGfeVersion, si.rtspSessionUrl = keep
        si.serverCodecModeSupport = int(info.get("ServerCodecModeSupport") or 0)

        dr = ll.DECODER_RENDERER_CALLBACKS()
        self.lib.LiInitializeVideoCallbacks(ctypes.byref(dr))
        dr.setup = self._cbs["setup"]
        dr.capabilities = c["CAPABILITY_PULL_RENDERER"] | ll.capability_slices_per_frame(4)
        ar = ll.AUDIO_RENDERER_CALLBACKS()
        self.lib.LiInitializeAudioCallbacks(ctypes.byref(ar))  # all NULL: the library drops audio
        cl = ll.CONNECTION_LISTENER_CALLBACKS()
        self.lib.LiInitializeConnectionCallbacks(ctypes.byref(cl))
        cl.stageStarting, cl.stageComplete = self._cbs["stage_start"], self._cbs["stage_done"]
        cl.stageFailed, cl.connectionStarted = self._cbs["stage_fail"], self._cbs["started"]
        cl.connectionTerminated = self._cbs["terminated"]
        cl.connectionStatusUpdate = self._cbs["status"]
        cl.logMessage = self.lib.log_message_ptr
        self.lib.shim.s2_set_log_sink(self._cbs["log"])

        if self.args.input_socket:
            from .presence import Presence

            # S2: no window takes input. The marker is never mapped (rdp-loop's interlock,
            # /health and to-console's gate still see a stream client).
            self.presence = Presence(self.width, self.height)
            log("presence marker: an unmapped window, WM_CLASS moonlight/S2client")
        elif self.args.mirror_x or self.bus is not None:
            from .x11_mirror_shim import Mirror

            # V3b: the window stays (rdp-loop's interlock and /health see a stream client, and it
            # receives the mux's XTest input) but is never painted: humans and the bot read the bus.
            self.mirror = Mirror(self.width, self.height, self, log, paint=self.args.mirror_x)
        t0 = time.monotonic()
        err = self.lib.LiStartConnection(
            ctypes.byref(si), ctypes.byref(cfg), ctypes.byref(cl), ctypes.byref(dr),
            ctypes.byref(ar), None, 0, None, 0,
        )  # fmt: skip
        if err != 0:
            log(f"LiStartConnection failed: {err}")
            self._close()
            return 4
        log(f"connected in {time.monotonic() - t0:.2f} s")
        if self.args.input_socket:
            from .input_socket import InputMapper, InputServer

            mapper = InputMapper(self.lib, self.const, self.width, self.height)
            self.input_server = InputServer(Path(self.args.input_socket), mapper, log)
        self.timing = TimingLog(OUT / "frames.csv")
        log(f"experiment knobs: fps={self.args.fps} evidence={self.args.evidence} "
            f"decode_threads={self.args.decode_threads}")  # fmt: skip
        if self.args.evidence == "thread":
            threading.Thread(target=self._evidence_loop, name="s2spike-evidence",
                             daemon=True).start()  # fmt: skip
        decoder_thread = threading.Thread(target=self._decode_loop, name="s2spike-decode")
        decoder_thread.start()
        if self.bus is not None:
            # Alive while connected, frames or not (a static desktop may send none): readers then
            # repeat the last frame instead of falling back to X.
            threading.Thread(target=self._heartbeat, name="s2spike-bus-heartbeat",
                             daemon=True).start()  # fmt: skip
        signal.signal(signal.SIGTERM, lambda *_: self.terminated.set())
        signal.signal(signal.SIGINT, lambda *_: self.terminated.set())
        self.terminated.wait()
        self.lib.LiWakeWaitForVideoFrame()
        self.lib.LiStopConnection()
        decoder_thread.join(timeout=10)
        self._close()
        return 0

    def _decode_loop(self) -> None:
        from .decode import Decoder

        dec = Decoder(threads=self.args.decode_threads)
        handle = ctypes.c_void_p()
        du = ctypes.POINTER(ll.DECODE_UNIT)()
        OUT.mkdir(parents=True, exist_ok=True)
        last_evidence = 0.0
        while not self.terminated.is_set():
            if not self.lib.LiWaitForNextVideoFrame(ctypes.byref(handle), ctypes.byref(du)):
                break  # the connection is stopping
            t_dequeue = time.monotonic_ns()
            unit = du.contents
            timing = (unit.frameNumber, unit.frameType, unit.receiveTimeMs, unit.enqueueTimeMs,
                      unit.frameHostProcessingLatency)  # fmt: skip
            chunks: list[bytes] = []
            entry = unit.bufferList
            while entry:
                chunks.append(ctypes.string_at(entry.contents.data, entry.contents.length))
                entry = entry.contents.next
            self.lib.LiCompleteVideoFrame(handle, self.const["DR_OK"])
            t_decode = time.monotonic_ns()
            try:
                frames = dec.decode(b"".join(chunks))
            except Exception:  # noqa: BLE001 -- counted in stats; resync on the next IDR
                self.lib.LiRequestIdrFrame()
                continue
            decode_us = (time.monotonic_ns() - t_decode) // 1000
            for frame in frames:
                if dec.stats.frames == 1:
                    log(f"FIRST FRAME decoded: {frame.shape[1]}x{frame.shape[0]}")
                t_publish = time.monotonic_ns()
                if self.bus is not None:
                    self.frame_id += 1
                    self.bus.publish(frame, self.frame_id, t_publish)
                if self.mirror is not None:
                    self.mirror.show(frame)
                if self.timing is not None:
                    self.timing.add((self.frame_id, *timing, t_dequeue, t_publish, decode_us))
                now = time.monotonic()
                if now - last_evidence >= EVIDENCE_EVERY_S:
                    last_evidence = now
                    if self.args.evidence == "thread":
                        with self._ev_lock:  # latest only: never a queue behind the decoder
                            self._ev_item = (frame, self._snapshot(dec))
                        self._ev_wake.set()
                    else:
                        self._evidence(frame, self._snapshot(dec))

    def _heartbeat(self) -> None:
        while not self.terminated.wait(0.5):
            if self.bus is not None:
                self.bus.heartbeat()

    def _snapshot(self, dec: Any) -> dict[str, Any]:
        """On the decode thread (its stats deques are not shared with another thread)."""
        snap = {**dec.stats.snapshot(), "stages": self.stats["stages"][-24:],
                "error": self.error, "t": time.time(), "evidence": self.args.evidence,
                "decode_threads": self.args.decode_threads,
                "fps_requested": self.args.fps}  # fmt: skip
        if self.mirror is not None:
            snap["mirror"] = dict(self.mirror.counts)
        if self.input_server is not None:
            snap["input"] = {**self.input_server.mapper.counts, "peers": self.input_server.peers}
        if self.timing is not None:
            snap["timing_dropped"] = self.timing.dropped
        return snap

    def _evidence_loop(self) -> None:
        while not self.terminated.is_set():
            if not self._ev_wake.wait(0.5):
                continue
            self._ev_wake.clear()
            with self._ev_lock:
                item, self._ev_item = self._ev_item, None
            if item is not None:
                self._evidence(*item)

    def _evidence(self, frame: Any, snap: dict[str, Any]) -> None:
        if self.bus is not None:
            p50, p95 = snap.get("decode_ms_p50"), snap.get("decode_ms_p95")
            if p50 is not None and p95 is not None:
                self.bus.set_decode_stats(int(p50 * 1000), int(p95 * 1000))
            snap["framebus"] = {"frames_published": self.frame_id}
        pngout.write_atomic(OUT / "v3-latest.png", pngout.png_bytes(frame[:, :, 2::-1]))
        pngout.write_atomic(OUT / "v3-stats.json", json.dumps(snap, indent=1).encode())

    def _close(self) -> None:
        if self.input_server is not None:
            log(f"input socket counts: {self.input_server.mapper.counts}, "
                f"peers {self.input_server.peers}")  # fmt: skip
            self.input_server.close()  # releases anything still held, removes the socket
            self.input_server = None
        if self.presence is not None:
            self.presence.close()
            self.presence = None
        if self.timing is not None:
            self.timing.close()
            self.timing = None
        if self.mirror is not None:
            log(f"x11 shim counts: {self.mirror.counts}")
            self.mirror.close()
            self.mirror = None
        if self.bus is not None:
            log(f"frame bus: {self.frame_id} frames published")
            # Removed, not left stale: the backend falls back to X at once (no window = black).
            self.bus.close(unlink=True)
            self.bus = None


def stream(args: argparse.Namespace) -> int:
    identity.harden_process()  # non-dumpable + comm "s2spike" (capture_backend counts it)
    ok, why = lockstate.may_stream(lockstate.state_dir(), os.environ.get("DISPLAY", ":99"))
    if not ok:
        log(f"REFUSED to stream: {why}")
        return 3
    log(f"preconditions: {why}")
    return Stream(args, ll.Lib(LIB_DIR)).run()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="s2spike", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)  # fmt: skip
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("selftest")
    si = sub.add_parser("serverinfo")
    si.add_argument("--host", default=os.environ.get("WIN_HOST", ""))
    st = sub.add_parser("stream")
    st.add_argument("--host", default=os.environ.get("WIN_HOST", ""))
    st.add_argument("--app", default="Desktop")
    st.add_argument("--size", default="1440x900")
    st.add_argument("--fps", type=int, default=30)
    st.add_argument("--bitrate", type=int, default=20000)
    st.add_argument("--mirror-x", action="store_true", help="the spike-only X shim")
    st.add_argument("--framebus", help="V3b: publish decoded frames to this frame bus ring")
    st.add_argument("--input-socket", help="S2: take the mux's input on this unix socket")
    st.add_argument(
        "--evidence",
        choices=("inline", "thread"),
        default="inline",
        help="evidence PNG + stats every 2 s: on the decode thread or its own",
    )
    st.add_argument("--decode-threads", type=int, choices=(1, 2, 4), default=2)
    args = ap.parse_args(argv)
    if args.cmd == "stream" and args.mirror_x and args.framebus:
        ap.error("--mirror-x and --framebus exclude each other (decode once, one view)")
    if args.cmd == "stream" and args.input_socket and not args.framebus:
        ap.error("--input-socket needs --framebus (S2: no X window paints or takes input)")
    if args.cmd == "selftest":
        return selftest()
    if not args.host:
        log("no --host / WIN_HOST")
        return 2
    if args.cmd == "serverinfo":
        return serverinfo(args.host)
    return stream(args)
