"""Stage 2 of the GPU recording plan (docs/planning/gpu-recording.md 9.1, PRE-REGISTERED before any
run): the side-by-side recording's video side, offline. No GPU, no container, no client:

* the sidecar's options are round 3's candidate, exactly (gpu_rec_bench's arm);
* the job protocol: the host's regex is the shell's, and bash agrees;
* the pure parts: the stage-2 bars (each fails alone), the verdict rule, the latency split;
* VideoFeed against a SIMULATED sidecar (a thread reading the pipe): the happy path, an encoder
  that dies, one that stops reading (a stall), none at all, a second recorder;
* END TO END with the REAL services/media-probe/mediarec.sh and a stub ffmpeg (libx265 4:4:4
  10-bit on the CPU, the GPU's stand-in): record_session.record() with a fake screen writes the
  PNG session AND video.hevc; the encoder dying mid-session leaves the PNG session whole; then
  media_rec.py check decodes every frame against its PNG twin.
"""

from __future__ import annotations

import argparse
import csv
import importlib.util
import json
import os
import re
import shlex
import subprocess
import sys
import threading
import time
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[3]
SCRIPTS = ROOT / "scripts"
SIDECAR = ROOT / "services" / "media-probe" / "mediarec.sh"
SID = "20261108T230000-rdp-s2test"


def _load(name: str) -> ModuleType:
    sys.path.insert(0, str(SCRIPTS))
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod  # dataclasses resolve their module; record_session imports media_rec
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def mr() -> ModuleType:
    return _load("media_rec")


@pytest.fixture(scope="module")
def gb() -> ModuleType:
    return _load("gpu_rec_bench")


def _dirs(tmp: Path) -> tuple[Path, Path, Path]:
    """ctl (RAM stand-in), the local root and its .media-rec: ours, 0700, as prep makes them."""
    ctl, root = tmp / "ctl", tmp / "rec-root"
    for d in (ctl, root, root / ".media-rec"):
        d.mkdir(parents=True, exist_ok=True)
        d.chmod(0o700)
    return ctl, root, root / ".media-rec"


def _shell_value(name: str) -> str:
    src = SIDECAR.read_text()
    m = re.search(rf"^{name}=(.*)$", src, re.M)
    assert m, name
    return m.group(1)


# --- the encoder is round 3's candidate -----------------------------------------------------------


def test_the_sidecar_runs_round_3s_candidate_exactly(mr: ModuleType, gb: ModuleType) -> None:
    arm = gb.arm_by_name(mr.ARM)
    assert arm.mode == "vpp" and mr.ARM in gb.ROUNDS[3]
    assert arm.codec == "hevc_vaapi" and arm.sw_fmt == "xv30" and arm.upload == "-"  # BGRA up
    assert arm.va_profile == gb.HEVC444_10 and arm.color_range == "pc"
    assert shlex.split(_shell_value("VPP"))[0] == arm.vpp == gb.VPP_FULL
    assert _shell_value("SW") == arm.sw_fmt
    enc = shlex.split(_shell_value("ENC").strip("()"))
    assert enc[:4] == ["-c:v", arm.codec, "-low_power", "1"]  # recbench.sh's vpp branch
    assert enc[4:] == shlex.split(arm.args)  # -profile:v rext -rc_mode CQP -qp 20 -g 1 -bf 0 -aud 1
    tags = shlex.split(_shell_value("TAGS").strip("()"))
    assert tags == ["-color_range", "pc", "-colorspace", "bt709", "-color_primaries", "bt709",
                    "-color_trc", "bt709"]  # fmt: skip  # recbench.sh's tags()
    src = SIDECAR.read_text()
    # recbench.sh's vpp command: BGRA in, uploaded, converted on the GPU, passthrough timing
    assert '-vf "format=bgra,hwupload,scale_vaapi=${VPP}:format=${SW}" -fps_mode passthrough' in src
    assert "-f rawvideo -pix_fmt bgra" in src and '-f hevc "$part"' in src
    assert '-fs "$max"' in src and "-nostdin" in src and " -n " in src  # never overwrite
    doc = (ROOT / "docs" / "planning" / "gpu-recording.md").read_text()
    assert f"CANDIDATE `{mr.ARM}`" in doc
    rs = _load("record_session")
    assert rs.VIDEO_FORMAT == mr.ARM


def test_the_job_regex_is_the_shells_and_bash_agrees(mr: ModuleType) -> None:
    assert _shell_value("JOB_RE") == f"'{mr.JOB_RE.pattern}'"
    good = mr.job_line(SID, 1280, 720, 8 << 30)
    assert good == f"start {SID} 1280 720 {8 << 30}"
    bad = ((SID.replace("rdp", "console"), 1280, 720, 1), ("../x", 1280, 720, 1),
           (SID + "/x", 1280, 720, 1), (SID, 1280, 7, 1), (SID, 123456, 720, 1),
           (SID, 1280, 720, 0))  # fmt: skip
    for sid, w, h, cap in bad:
        with pytest.raises(mr.VideoRefused):
            mr.job_line(sid, w, h, cap)
    script = 're=$1; shift; for l in "$@"; do [[ "$l" =~ $re ]] && echo 1 || echo 0; done'
    lines = [good, good + " x", good.replace("1280", "01280"), "start " + SID + " 64 48 1"]
    out = subprocess.run(["bash", "-c", script, "_", mr.JOB_RE.pattern, *lines],
                         capture_output=True, text=True, check=True).stdout.split()  # fmt: skip
    assert out == ["1" if mr.JOB_RE.match(x) else "0" for x in lines] == ["1", "0", "0", "1"]


# --- the pure parts -------------------------------------------------------------------------------


def _passing(mr: ModuleType) -> dict[str, Any]:
    return {
        "completeness": {"kept": 100, "matched": 100, "undecodable": 0, "decoded": 100,
                         "fed": 100},
        "vui": {"frames": 100, "ok": 100, "seen": [{"range": "pc", "matrix": "bt709"}]},
        "cpu": {"video_ms_per_frame": 12.0, "png_writer_ms_per_frame": 95.0,
                "feed_ms_per_frame": 2.5},
        "latency": {"recording": {"calls": 9000, "gpu_ms_p50": 20.9, "gpu_ms_p95": 24.0,
                                  "gpu_share": 0.999},
                    "baseline": {"calls": 9000, "gpu_ms_p50": 20.5, "gpu_ms_p95": 22.0,
                                 "gpu_share": 1.0}},
    }  # fmt: skip


def test_each_stage_2_bar_fails_alone(mr: ModuleType) -> None:
    base = mr.stage2_bars(_passing(mr))
    assert {k: v["result"] for k, v in base.items()} == {
        k: "PASS" for k in ("K1", "F1", "C1", "C2", "C3", "L1", "L2", "L3")}  # fmt: skip
    cases = {
        "K1": lambda r: r["completeness"].update(matched=99),
        "F1": lambda r: r["vui"].update(ok=99),
        "C1": lambda r: r["cpu"].update(video_ms_per_frame=20.5, png_writer_ms_per_frame=200.0),
        "C2": lambda r: r["cpu"].update(png_writer_ms_per_frame=55.0),
        "C3": lambda r: r["cpu"].update(feed_ms_per_frame=5.1),
        "L1": lambda r: r["latency"]["recording"].update(gpu_ms_p50=21.6),
        "L2": lambda r: r["latency"]["recording"].update(gpu_ms_p95=25.1),
        "L3": lambda r: r["latency"]["recording"].update(gpu_share=0.985),
    }
    for key, change in cases.items():
        res = _passing(mr)
        change(res)
        got = mr.stage2_bars(res)
        assert [k for k, v in got.items() if v["result"] == "FAIL"] == [key], key
    res = _passing(mr)
    res["completeness"].update(decoded=99)  # a fed frame the stream does not hold
    assert mr.stage2_bars(res)["K1"]["result"] == "FAIL"
    res = _passing(mr)
    res["latency"]["baseline"]["calls"] = 499  # underpowered: NA, never PASS
    assert {mr.stage2_bars(res)[k]["result"] for k in ("L1", "L2", "L3")} == {"NA"}
    res = _passing(mr)
    del res["latency"]["baseline"]
    assert mr.stage2_bars(res)["L1"]["result"] == "NA"


def test_the_verdict_needs_every_bar_measured_but_q6(mr: ModuleType) -> None:
    ok = {"result": "PASS", "value": 1, "need": ""}
    na = {"result": "NA", "value": None, "need": ""}
    quality = {k: ok for k in ("Q1", "Q2", "Q3", "Q4", "Q5", "G1", "P1", "P2", "P3", "D1", "S1")}
    s2 = mr.stage2_bars(_passing(mr))
    assert mr.stage2_verdict(quality, s2)["pass"] is True
    assert mr.stage2_verdict({**quality, "Q6": na}, s2)["pass"] is True  # too few saturated px
    no_det = {k: v for k, v in quality.items() if not k.startswith("P")} | {"P": na}
    v = mr.stage2_verdict(no_det, s2)
    assert v["pass"] is False and v["not_measured"] == ["P"] and not v["detector_powered"]
    v = mr.stage2_verdict(quality, {**s2, "L1": na})
    assert v["pass"] is False and v["not_measured"] == ["L1"]
    v = mr.stage2_verdict({**quality, "Q3": {**ok, "result": "FAIL"}}, s2)
    assert v["pass"] is False and v["fail"] == ["Q3"]


def test_stage_1_only_bars_are_left_to_stage_1(mr: ModuleType, gb: ModuleType) -> None:
    """S2 / S3 (the container's encode from RAM) and D2 (the VA-API decode) are stage 1's; the
    quality and parity bars are gpu_rec_bench's own, with its values (BARS, unchanged)."""
    assert mr.STAGE1_ONLY == ("S2", "S3", "D2")
    q = {"psnr_mean": 44.0, "psnr_min": 42.0, "ssim_mean": 0.995, "ssim_min": 0.99,
         "crops": {k: {"psnr_mean": 40.0, "psnr_min": 38.0} for k in gb.CROPS},
         "sat_count": 5000, "sat_keep": 0.99, "gen2_psnr_mean": 33.0}  # fmt: skip
    jq = {**q, "psnr_mean": 33.0, "ssim_mean": 0.993}
    par = {"png_boxes": 200, "of_png": 1.0, "of_dec": 1.0, "coord_med": 0.1, "coord_p95": 0.3}
    arm = {"quality": q, "parity": par, "bytes_per_frame": 200.0,
           "d1": {"frames": 10, "alone_identical": 10}}  # fmt: skip
    bars = gb.bars_for(arm, {"quality": jq, "parity": par}, {"bytes_per_frame": 1000.0}, None,
                       "vpp")  # fmt: skip
    kept = {k: v for k, v in bars.items() if k not in mr.STAGE1_ONLY}
    assert set(bars) - set(kept) == {"S2", "S3", "D2"}
    assert {v["result"] for v in kept.values()} == {"PASS"}


def test_the_doc_preregisters_every_stage_2_bar(mr: ModuleType) -> None:
    doc = (ROOT / "docs" / "planning" / "gpu-recording.md").read_text()
    sec = doc[doc.index("### 9.1") :]
    for key, value in mr.STAGE2_BARS.items():
        rows = [ln for ln in sec.splitlines() if f"`{key}`" in ln]
        assert rows, f"{key} is not in 9.1's bar table"
        assert any(f"| {value} |" in ln or f"| {value:g} |" in ln for ln in rows), (key, value)
    for key in mr.STAGE1_ONLY:
        assert f"`{key}`" in sec or f" {key} " in sec


def test_near_encode_and_the_window(mr: ModuleType) -> None:
    ms = 1_000_000
    writes = [(1000 * ms, 1002 * ms), (2000 * ms, 2003 * ms)]
    calls = [{"t_ns": 1030 * ms, "ms": 20.0},  # 1010..1030 meets 1000..1052: near
             {"t_ns": 1100 * ms, "ms": 20.0},  # 1080..1100: after 1052, far
             {"t_ns": 1999 * ms, "ms": 20.0},  # 1979..1999 ends before 2000: far
             {"t_ns": 2010 * ms, "ms": 20.0},  # near the second
             {"t_ns": 990 * ms, "ms": 5.0}]  # fmt: skip
    near, far = mr.near_encode(calls, writes)
    assert [c["t_ns"] // ms for c in near] == [1030, 2010]
    assert [c["t_ns"] // ms for c in far] == [1100, 1999, 990]
    assert [r["t_ns"] for r in mr.window_rows(calls, 1000 * ms, 2000 * ms)] == [
        1030 * ms, 1100 * ms, 1999 * ms]  # fmt: skip
    assert mr.ms_per_frame(1.5, 100) == 15.0 and mr.ms_per_frame(None, 10) is None


def test_the_alpha_is_forced_on_a_copy(mr: ModuleType) -> None:
    img = np.zeros((4, 5, 4), np.uint8)
    img[..., :3] = 7
    img.setflags(write=False)  # the grab's array is read-only
    out = mr.force_alpha(img)
    assert out.flags.c_contiguous and (out[..., 3] == 255).all() and (out[..., :3] == 7).all()
    assert (img[..., 3] == 0).all()


def test_record_session_resolves_the_video_and_stage_2_formats(mr: ModuleType) -> None:
    """ADR-0024 (Batt 2026-11-09): the video format is the rdp default, alone (the video holds
    the frames) or with --also-png (stage 2's side-by-side: a PNG session with its twin); PNG stays
    selectable and records to any --out; the console keeps its H.264."""
    rs = _load("record_session")
    root = rs.dataset_ship.LOCAL_ROOT

    def ns(**kw: Any) -> argparse.Namespace:
        base = {"backend": "rdp", "format": None, "also_png": False, "out": root,
                "seconds": 60.0, "max_bytes": 1 << 30, "idr_every": 1.0}  # fmt: skip
        return argparse.Namespace(**{**base, **kw})

    for a, fmt, video in ((ns(), mr.ARM, mr.ARM),  # the rdp default: video only
                          (ns(format=mr.ARM), mr.ARM, mr.ARM),
                          (ns(format=mr.ARM, also_png=True), "png", mr.ARM),  # stage 2
                          (ns(also_png=True), "png", mr.ARM),  # the default's twin
                          (ns(format="png"), "png", None),
                          (ns(format="png", out=Path("/dev/shm/x")), "png", None),
                          (ns(backend="console"), "h264", None)):  # fmt: skip
        rs.resolve_format(a)
        assert (a.format, a.video) == (fmt, video)
    assert rs.VIDEO_FORMAT == mr.ARM and rs.RECORDER_VERSION == 7
    for bad, why in ((ns(format="png", also_png=True), "goes with"),
                     (ns(backend="console", also_png=True), "goes with"),
                     (ns(format=mr.ARM, backend="console"), "rdp only"),
                     (ns(out=Path("/dev/shm/x")), "--out must"),  # the default needs the root
                     (ns(format=mr.ARM, also_png=True, out=Path("/dev/shm/x")), "--out must"),
                     ):  # fmt: skip
        with pytest.raises(rs.r.Stop, match=why):
            rs.resolve_format(bad)


# --- VideoFeed against a simulated sidecar --------------------------------------------------------


class SimSidecar(threading.Thread):
    """mediarec.sh's protocol in a thread: take the job, open the pipe's read end (the host's open
    waits for it), read frames per ``mode``, write the part file and the done file."""

    def __init__(self, ctl: Path, rec: Path, mode: str = "ok", n: int = 0, pause: float = 0.0,
                 rc: int = 0) -> None:  # fmt: skip
        super().__init__(daemon=True)
        self.ctl, self.rec, self.mode, self.n, self.pause, self.rc = ctl, rec, mode, n, pause, rc
        self.frames: list[bytes] = []
        self.size: tuple[int, int] | None = None

    def run(self) -> None:
        job = self.ctl / "job"
        while not job.exists():
            time.sleep(0.01)
        m = re.match(r"^start (\S+) (\d+) (\d+) (\d+)$", job.read_text().strip())
        job.unlink()
        assert m
        sid, w, h = m.group(1), int(m.group(2)), int(m.group(3))
        self.size = (w, h)
        if self.mode == "refuse":
            self._done(sid, 2, "refused: its output exists")
            return
        per = w * h * 4
        with open(self.ctl / "frames.fifo", "rb") as fh, (self.rec / f".{sid}.hevc").open(
                "wb") as part:  # fmt: skip
            while True:
                if self.mode == "pause" and len(self.frames) == self.n:
                    time.sleep(self.pause)
                    self.mode = "ok"
                buf = fh.read(per)
                if len(buf) < per:
                    break
                self.frames.append(buf)
                part.write(b"AU%d;" % len(self.frames))
                if self.mode == "die" and len(self.frames) == self.n:
                    break  # the read end closes: the host's next write gets EPIPE
        (self.rec / f".{sid}.ffmpeg.log").write_text("stub log\n")
        self._done(sid, self.rc if self.mode != "die" else 1, "ffmpeg exit")

    def _done(self, sid: str, rc: int, note: str) -> None:
        tmp = self.ctl / f".done-{sid}.tmp"
        tmp.write_text(f"SID={sid}\nRC={rc}\nBYTES=0\nENDED=now\nNOTE={note}\n")
        tmp.replace(self.ctl / f"done-{sid}")


def _frame(i: int, w: int = 64, h: int = 48) -> np.ndarray:
    img = np.zeros((h, w, 4), np.uint8)
    img[..., 0], img[..., 1], img[..., 2] = i % 256, (3 * i) % 256, 200
    img.setflags(write=False)
    return img


def _feed(mr: ModuleType, ctl: Path, rec: Path, **kw: Any) -> Any:
    opts = {"require_container": False, "open_timeout_s": 3.0, "stall_s": 0.4,
            "done_timeout_s": 3.0, "pipe_bytes": None, **kw}  # fmt: skip
    return mr.VideoFeed(SID, 64, 48, 1 << 30, ctl=ctl, rec=rec, **opts)


def _wait(cond: Any, s: float = 5.0) -> None:
    end = time.monotonic() + s
    while not cond():
        assert time.monotonic() < end, "timed out"
        time.sleep(0.01)


def test_the_feed_writes_every_frame_and_moves_the_stream_into_the_session(
        mr: ModuleType, tmp_path: Path) -> None:  # fmt: skip
    ctl, _root, rec = _dirs(tmp_path)
    sim = SimSidecar(ctl, rec)
    sim.start()
    feed = _feed(mr, ctl, rec)
    feed.start()
    assert feed.status == "feeding" and (ctl / "frames.fifo").exists()
    for i in range(6):
        assert feed.offer(i, 1000 + i, _frame(i)) is True
    _wait(lambda: feed.fed == 6)
    session = tmp_path / SID
    session.mkdir()
    info = feed.finish(session)
    sim.join(3)
    assert info["status"] == "ok" and info["reason"] is None and info["fed"] == 6
    assert info["by_status"] == {"fed": 6} and info["sidecar"]["done"]["RC"] == "0"
    assert sorted(info["files"]) == ["video.ffmpeg.log", "video.hevc"]
    assert (session / "video.hevc").read_bytes().startswith(b"AU1;")
    assert not (rec / f".{SID}.hevc").exists() and not (ctl / f"done-{SID}").exists()
    assert not (ctl / "frames.fifo").exists() and info["feed_cpu_s"] >= 0
    rows = list(csv.DictReader((session / "video.idx.csv").open()))
    assert [int(r["video_index"]) for r in rows] == list(range(6))
    assert [int(r["t_mono_ns"]) for r in rows] == [1000 + i for i in range(6)]
    assert all(int(r["write_end_ns"]) >= int(r["write_start_ns"]) > 0 for r in rows)
    for i, buf in enumerate(sim.frames):  # the pixels as grabbed, the alpha forced to 255
        got = np.frombuffer(buf, np.uint8).reshape(48, 64, 4)
        assert (got[..., :3] == _frame(i)[..., :3]).all() and (got[..., 3] == 255).all()
    again = _feed(mr, ctl, rec)  # the lock was released, the job protocol is clean again
    with pytest.raises(mr.VideoRefused, match="already exists"):
        (rec / f".{SID}.hevc").write_bytes(b"x")
        again.start()


def test_an_encoder_that_dies_ends_the_video_side_only(mr: ModuleType, tmp_path: Path) -> None:
    ctl, _root, rec = _dirs(tmp_path)
    sim = SimSidecar(ctl, rec, mode="die", n=2)
    sim.start()
    feed = _feed(mr, ctl, rec)
    feed.start()
    results = []
    for i in range(10):
        results.append(feed.offer(i, i, _frame(i)))
        time.sleep(0.02)
    _wait(lambda: feed.check() is not None)
    assert feed.status == "failed" and "EPIPE" in (feed.reason or "")
    assert feed.offer(10, 10, _frame(10)) is False  # nothing more is queued
    session = tmp_path / SID
    session.mkdir()
    info = feed.finish(session)
    assert info["status"] == "failed" and "EPIPE" in info["reason"]
    assert info["sidecar"]["done"]["RC"] == "1" and info["fed"] >= 2
    st = info["by_status"]
    assert sum(st.values()) == 11 and st["fed"] == info["fed"]
    assert st.get("not_fed_failed", 0) + st.get("write_failed", 0) >= 1
    assert 10 in info["not_fed_ids"]["not_fed_failed"]


def test_a_stalled_encoder_is_found_and_later_frames_dropped(mr: ModuleType,
                                                             tmp_path: Path) -> None:  # fmt: skip
    """The encoder stops reading (a hung GPU): the pipe fills (64 KiB, 12 KiB a frame), a write
    blocks past stall_s, the video side fails; the PNG loop's offers never block. When the
    encoder reads again, the blocked frame is whole in the stream and keeps its index."""
    ctl, _root, rec = _dirs(tmp_path)
    sim = SimSidecar(ctl, rec, mode="pause", n=0, pause=1.5)
    sim.start()
    feed = _feed(mr, ctl, rec, queue_frames=2)
    feed.start()
    t0 = time.monotonic()
    for i in range(30):
        feed.offer(i, i, _frame(i))
        time.sleep(0.03)
    assert time.monotonic() - t0 < 3.0  # never blocked
    _wait(lambda: feed.check() is not None, 3.0)
    assert feed.status == "failed" and "stalled" in (feed.reason or "")
    session = tmp_path / SID
    session.mkdir()
    info = feed.finish(session)
    st = info["by_status"]
    assert st.get("dropped_queue_full", 0) >= 1 and st.get("not_fed_failed", 0) >= 1
    rows = list(csv.DictReader((session / "video.idx.csv").open()))
    fed = [int(r["video_index"]) for r in rows if r["status"] == "fed"]
    assert fed == list(range(len(fed))) and len(fed) == info["fed"] >= 5
    sim.join(3)
    assert len(sim.frames) == info["fed"]  # every frame it holds is one the index places


def test_no_sidecar_refuses_and_leaves_nothing_behind(mr: ModuleType, tmp_path: Path) -> None:
    ctl, _root, rec = _dirs(tmp_path)
    feed = _feed(mr, ctl, rec, open_timeout_s=0.3)
    with pytest.raises(mr.VideoRefused, match="did not open the frame pipe"):
        feed.start()
    assert feed.status == "refused"
    assert not (ctl / "job").exists() and not (ctl / "frames.fifo").exists()
    assert sorted(os.listdir(ctl)) == ["lock"]
    sim = SimSidecar(ctl, rec, mode="refuse")
    sim.start()
    with pytest.raises(mr.VideoRefused, match="rc 2"):
        _feed(mr, ctl, rec).start()


def test_one_recorder_at_a_time_and_only_our_own_directories(mr: ModuleType,
                                                             tmp_path: Path) -> None:  # fmt: skip
    ctl, _root, rec = _dirs(tmp_path)
    sim = SimSidecar(ctl, rec)
    sim.start()
    first = _feed(mr, ctl, rec)
    first.start()
    second = mr.VideoFeed(SID.replace("s2test", "other"), 64, 48, 1 << 30, ctl=ctl, rec=rec,
                          require_container=False, open_timeout_s=0.3)  # fmt: skip
    with pytest.raises(mr.VideoRefused, match="another recorder"):
        second.start()
    assert (ctl / "frames.fifo").exists()  # the first's pipe was not touched
    first.offer(0, 0, _frame(0))
    session = tmp_path / SID
    session.mkdir()
    assert first.finish(session)["status"] == "ok"
    rec.chmod(0o750)
    with pytest.raises(mr.VideoRefused, match="not 700"):
        _feed(mr, ctl, rec).start()
    rec.chmod(0o700)
    assert mr.dir_problem(tmp_path / "absent") is not None


def test_prep_makes_both_directories_ours_and_0700(mr: ModuleType, tmp_path: Path) -> None:
    root, ctl = tmp_path / "root", tmp_path / "ctl"
    assert mr.main(["prep", "--root", str(root), "--ctl", str(ctl)]) == 0
    for d in (ctl, root / ".media-rec"):
        assert mr.dir_problem(d) is None
    (root / ".media-rec").chmod(0o755)
    assert mr.main(["prep", "--root", str(root), "--ctl", str(ctl)]) == 0  # put back to 0700
    assert mr.dir_problem(root / ".media-rec") is None


# --- END TO END: the real sidecar script, a stub ffmpeg, record_session.record(), check -----------

STUB_FFMPEG = r"""#!{python}
# a stand-in for the image's ffmpeg: the same command line, libx265 4:4:4 10-bit on the CPU
import os, sys
args = sys.argv[1:]
with open(os.environ["STUB_LOG"], "a") as fh:
    fh.write(" ".join(args) + "\n")
if "-version" in args:
    print("ffmpeg version stub")
    sys.exit(0)
import numpy as np
import av
src, out = args[args.index("-i") + 1], args[-1]
w, h = (int(v) for v in args[args.index("-video_size") + 1].split("x"))
die_after = int(os.environ.get("STUB_DIE_AFTER") or 0)
fh = open(src, "rb")  # waits for the host's end, as ffmpeg's open of a pipe does
per, n, died = w * h * 4, 0, False
with av.open(out, "w", format="hevc") as cont:
    st = cont.add_stream("libx265", rate=1, options={
        "x265-params": "keyint=1:min-keyint=1:scenecut=0:qp=4:pools=2:frame-threads=1:"
                       "log-level=error", "preset": "ultrafast"})
    st.width, st.height, st.pix_fmt = w, h, "yuv444p10le"
    st.codec_context.color_range, st.codec_context.colorspace = 2, 1
    while True:
        buf = fh.read(per)
        if len(buf) < per:
            break
        img = np.frombuffer(buf, np.uint8).reshape(h, w, 4)
        if (img[..., 3] != 255).any():
            print("alpha is not 255", file=sys.stderr)
            sys.exit(3)
        vf = av.VideoFrame.from_ndarray(np.ascontiguousarray(img[..., :3]), format="bgr24")
        vf = vf.reformat(format="yuv444p10le", dst_colorspace="ITU709", dst_color_range="JPEG")
        vf.color_range, vf.colorspace = 2, 1
        for pkt in st.encode(vf):
            cont.mux(pkt)
        n += 1
        if die_after and n >= die_after:
            died = True  # the encoder stops: its stream ends whole, then the pipe's read end closes
            break
    for pkt in st.encode(None):
        cont.mux(pkt)
fh.close()
print(f"frame={n}", file=sys.stderr)
sys.exit(1 if died else 0)
"""


class _Sidecar:
    """services/media-probe/mediarec.sh itself, on the host, with the stub ffmpeg first on PATH."""

    def __init__(self, tmp: Path, ctl: Path, rec: Path, **env: str) -> None:
        stub = tmp / "bin"
        stub.mkdir(exist_ok=True)
        (stub / "ffmpeg").write_text(STUB_FFMPEG.replace("{python}", sys.executable))
        (stub / "ffmpeg").chmod(0o755)
        self.out = tmp / "sidecar.out"
        self.log = tmp / "stub.log"
        full = {**os.environ, "PATH": f"{stub}:{os.environ['PATH']}", "MEDIAREC_CTL": str(ctl),
                "MEDIAREC_REC": str(rec), "MEDIAREC_POLL": "0.05", "MEDIAREC_OPEN_WAIT": "20",
                "STUB_LOG": str(self.log), **env}  # fmt: skip
        self.proc = subprocess.Popen(["bash", str(SIDECAR)], env=full, stdout=self.out.open("w"),
                                     stderr=subprocess.STDOUT)  # fmt: skip
        _wait(lambda: "ready" in self.out.read_text(), 10)

    def stop(self) -> str:
        self.proc.terminate()
        assert self.proc.wait(15) == 0
        return self.out.read_text()


class FakeScreen:
    """ro_agent.Screen's grab_meta: ``n`` distinct 1280 x 720 BGRA pictures (alpha 0, read-only
    arrays like the real pipe's), then the last one again (unchanged: skipped)."""

    def __init__(self, n: int) -> None:
        rng = np.random.default_rng(7)
        yy, xx = np.mgrid[0:720, 0:1280]
        base = np.stack([(xx // 5) % 256, (yy // 3) % 256, ((xx + yy) // 7) % 256,
                         np.zeros_like(xx)], -1).astype(np.uint8)  # fmt: skip
        base[600:606, 0:600, :3] = (0, 0, 255)
        self.frames = []
        for i in range(n):
            img = np.roll(base, 8 * i, axis=1).copy()
            img[..., :3] = np.clip(img[..., :3].astype(int) + rng.integers(-2, 3, (720, 1280, 3)),
                                   0, 255).astype(np.uint8)  # fmt: skip
            img.setflags(write=False)
            self.frames.append(img)
        self.i = 0

    def grab_meta(self, x: int, y: int, w: int, h: int) -> tuple[int, Any, int, str]:
        img = self.frames[min(self.i, len(self.frames) - 1)]
        self.i += 1
        return time.monotonic_ns(), img, -1, "x11"

    def close(self) -> None:
        pass


def _record(rs: ModuleType, mr: ModuleType, monkeypatch: pytest.MonkeyPatch, ctl: Path,
            root: Path, n: int, *, fmt: str = "png", part: int = 0) -> dict[str, Any]:  # fmt: skip
    """record_session.record() with everything around the frames faked: the lock, the config, the
    screen, the guard, the packets, the caps; the video side is real (VideoFeed + the sidecar).
    ``fmt``: "png" (stage 2: the PNG and its video twin) or mr.ARM (the video only)."""
    usec = {"n": 0}

    def cpu_usec(name: str) -> int:
        usec["n"] += 50_000
        return usec["n"]

    monkeypatch.setattr(
        rs, "read_lock", lambda _p: SimpleNamespace(backend="rdp", phase="steady", seq=1)
    )
    monkeypatch.setitem(
        sys.modules,
        "bench",
        SimpleNamespace(
            run_config=lambda b: {"backend": b}, benchlib=SimpleNamespace(config_hash=lambda c: "h")
        ),
    )
    monkeypatch.setattr(rs.dataset_ship, "local_caps", lambda *a, **k: None)
    monkeypatch.setattr(rs.dataset_ship, "unshipped_bytes", lambda _r: 0)
    monkeypatch.setattr(rs.dataset_ship, "in_set_hours", lambda: False)
    monkeypatch.setattr(rs.r, "game_region", lambda: (0, 0, 1280, 720))
    monkeypatch.setattr(rs.r, "Screen", lambda: FakeScreen(n))
    guard = SimpleNamespace(breach=lambda: None, summary=lambda: {}, describe=lambda: "fake")
    monkeypatch.setattr(rs, "load_guard", lambda *a: guard)
    monkeypatch.setattr(rs, "write_packets", lambda *a: ([], None))
    monkeypatch.setattr(rs, "freeze_report", lambda *a: None)
    monkeypatch.setattr(rs, "container_cpu_usec", cpu_usec)
    monkeypatch.setattr(rs.lab_servers, "server", lambda: "lab-rathena")
    monkeypatch.setattr(mr, "CTL", ctl)
    monkeypatch.setattr(mr, "container_state", lambda name=mr.CONTAINER: "running")
    monkeypatch.setattr(mr, "container_image", lambda name=mr.CONTAINER: "sha256:stub")
    a = argparse.Namespace(backend="rdp", label="s2test", seconds=3.0, fps=4.0, format=fmt,
                           video=mr.ARM, png_level=1, out=root, max_bytes=1 << 30,
                           min_free_gb=0.0, max_unshipped_gb=1000.0, io_rule="auto", resume=0,
                           part=part)  # fmt: skip
    res: dict[str, Any] = rs.record(a)
    return res


def test_end_to_end_the_png_and_its_video_twin_then_check(mr: ModuleType, gb: ModuleType,
                                                          tmp_path: Path,
                                                          monkeypatch: pytest.MonkeyPatch
                                                          ) -> None:  # fmt: skip
    rs = _load("record_session")
    ctl, root, rec = _dirs(tmp_path)
    side = _Sidecar(tmp_path, ctl, rec)
    try:
        res = _record(rs, mr, monkeypatch, ctl, root, 5)
    finally:
        log = side.stop()
    assert "stopped" in log and "job 20" in log and "rc=0" in log
    session = Path(res["dir"])
    manifest = json.loads((session / "manifest.json").read_text())
    assert manifest["format"] == "png" and manifest["frames"] == 5
    v = manifest["video"]
    assert v["status"] == "ok" and v["fed"] == 5 and v["by_status"] == {"fed": 5}
    assert v["arm"] == mr.ARM and v["sidecar"]["image"] == "sha256:stub"
    assert manifest["cpu_cores"]["media-rec"] is not None and manifest["png_writer_cpu_s"] > 0
    assert manifest["cpu_wall_s"] > 0
    assert (session / "video.hevc").stat().st_size > 0 and not os.listdir(rec)
    stub = (tmp_path / "stub.log").read_text()  # the command the real image would run
    assert "-f rawvideo -pix_fmt bgra -video_size 1280x720 -framerate 1 -i " in stub
    assert f"scale_vaapi={gb.VPP_FULL}:format=xv30" in stub and "-qp 20 -g 1 -bf 0 -aud 1" in stub
    out = tmp_path / "check.json"
    assert mr.main(["check", str(session), "--map", "test_map", "--out", str(out),
                    "--no-detector"]) == 1  # fmt: skip  # no detector: P is not measured
    chk = json.loads(out.read_text())
    k = chk["completeness"]
    assert k["kept"] == k["fed"] == k["decoded"] == k["matched"] == 5 and k["t_mismatch"] == 0
    assert k["d1_alone_identical"] == 5 and k["undecodable"] == 0 and k["shard_cuts"] == []
    s2, q = chk["bars"]["stage2"], chk["bars"]["quality"]
    assert s2["K1"]["result"] == s2["F1"]["result"] == q["D1"]["result"] == "PASS"
    assert chk["video"]["quality"]["psnr_mean"] > 40  # libx265 qp 4, 4:4:4 10-bit
    assert chk["cpu"]["video_ms_per_frame"] is not None and chk["cpu"]["feed_ms_per_frame"] >= 0
    assert {s2[x]["result"] for x in ("L1", "L2", "L3")} == {"NA"}  # no pilot named
    assert chk["verdict"]["pass"] is False and "P" in chk["verdict"]["not_measured"]
    assert not set(q) & set(mr.STAGE1_ONLY)


def test_end_to_end_an_encoder_crash_leaves_the_png_session_whole(
        mr: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:  # fmt: skip
    rs = _load("record_session")
    ctl, root, rec = _dirs(tmp_path)
    side = _Sidecar(tmp_path, ctl, rec, STUB_DIE_AFTER="2")
    try:
        res = _record(rs, mr, monkeypatch, ctl, root, 5)
    finally:
        log = side.stop()
    assert "rc=1" in log
    session = Path(res["dir"])
    manifest = json.loads((session / "manifest.json").read_text())
    assert manifest["frames"] == 5 and manifest["stop_reason"] == "duration"  # the PNG: whole
    v = manifest["video"]
    assert v["status"] == "failed" and "EPIPE" in v["reason"] and v["fed"] >= 2
    assert sum(v["by_status"].values()) == 5
    out = tmp_path / "check.json"
    mr.main(["check", str(session), "--map", "test_map", "--out", str(out), "--no-detector"])
    chk = json.loads(out.read_text())
    assert chk["bars"]["stage2"]["K1"]["result"] == "FAIL"
    assert chk["completeness"]["matched"] == 2 and chk["video_status"] == "failed"


def test_the_sidecar_ends_a_job_whose_host_never_came(mr: ModuleType, tmp_path: Path) -> None:
    """A job without a writer (the host died between the job and its open): the watchdog opens
    and closes a writer, ffmpeg reads end-of-file, the job ends, the sidecar takes the next."""
    ctl, _root, rec = _dirs(tmp_path)
    side = _Sidecar(tmp_path, ctl, rec, MEDIAREC_OPEN_WAIT="1")
    try:
        os.mkfifo(ctl / "frames.fifo", 0o600)
        (ctl / "job").write_text(mr.job_line(SID, 64, 48, 1 << 20) + "\n")
        _wait(lambda: (ctl / f"done-{SID}").exists(), 15)
        done = mr.parse_done((ctl / f"done-{SID}").read_text())
        assert done["SID"] == SID and not (ctl / "running").exists()
        (ctl / "job").write_text("start ../../etc 1 1 1\n")  # malformed: refused, not run
        _wait(lambda: "malformed" in side.out.read_text(), 5)
    finally:
        log = side.stop()
    assert "a writer opened and closed" in log


# --- STAGE 3 (ADR-0024): the video holds the frames -----------------------------------------------


def _psnr(a: np.ndarray, b: np.ndarray) -> float:
    mse = float(np.mean((a.astype(np.float64) - b.astype(np.float64)) ** 2))
    return 99.0 if mse == 0 else 10 * np.log10(255.0**2 / mse)


def test_end_to_end_a_video_only_recording_and_its_reader(
        mr: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:  # fmt: skip
    """record() with the video format alone: no shards, the frames in video.hevc, every kept
    frame's row with the PNG record's fields; poring_dataset.frames serves every frame, by index
    and in order, matched to its grab by frame id and time."""
    from poring_dataset import frames as fr

    rs = _load("record_session")
    ctl, root, rec = _dirs(tmp_path)
    side = _Sidecar(tmp_path, ctl, rec)
    screen = FakeScreen(5)  # the same pictures the recorder grabs (a seeded generator)
    try:
        res = _record(rs, mr, monkeypatch, ctl, root, 5, fmt=mr.ARM)
    finally:
        log = side.stop()
    assert "rc=0" in log
    session = Path(res["dir"])
    manifest = json.loads((session / "manifest.json").read_text())
    assert manifest["format"] == mr.ARM and res["format"] == mr.ARM
    assert manifest["shards"] == [] and not list(session.glob("shard-*.tar"))
    assert manifest["frames"] == manifest["kept"] == 5 and manifest["recorder_version"] == 7
    assert manifest["png_level"] is None and manifest["stop_reason"] == "duration"
    v = manifest["video"]
    assert v["status"] == "ok" and v["fed"] == 5 and v["access_units"] == 5
    size = (session / "video.hevc").stat().st_size
    assert manifest["bytes"] == size == res["bytes"] == res["bytes_total"]
    names = sorted(p.name for p in session.iterdir())  # (the packets file: faked here)
    assert names == ["manifest.json", "video.ffmpeg.log", "video.hevc", "video.idx.csv"]
    rows = list(csv.DictReader((session / "video.idx.csv").open()))
    assert [r["source"] for r in rows] == ["x11"] * 5 and all(r["t_wall"] for r in rows)
    assert [r["bus_frame_id"] for r in rows] == ["-1"] * 5
    refs = fr.frame_refs(session)
    assert [r.frame_id for r in refs] == list(range(5))
    got = list(fr.iter_bgr(session))
    assert [m["frame_id"] for m, _ in got] == list(range(5))
    for (meta, img), ref, row in zip(got, refs, rows, strict=True):
        assert meta["t_mono_ns"] == ref.t_mono_ns == int(row["t_mono_ns"])
        assert meta["source"] == "x11" and meta["t_wall"] == row["t_wall"]
        assert img.shape == (720, 1280, 3)
        assert _psnr(img, np.asarray(screen.frames[meta["frame_id"]])[..., :3]) > 40
        assert np.array_equal(fr.read_ref(ref, (1280, 720)), img)  # alone == in order
    assert fr.verify_video(session)["ok"] is True


def test_end_to_end_a_video_only_recording_stops_when_its_encoder_dies(
        mr: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:  # fmt: skip
    from poring_dataset import frames as fr

    rs = _load("record_session")
    ctl, root, rec = _dirs(tmp_path)
    side = _Sidecar(tmp_path, ctl, rec, STUB_DIE_AFTER="2")
    try:
        res = _record(rs, mr, monkeypatch, ctl, root, 5, fmt=mr.ARM)
    finally:
        log = side.stop()
    assert "rc=1" in log
    session = Path(res["dir"])
    manifest = json.loads((session / "manifest.json").read_text())
    assert manifest["stop_reason"].startswith("video_failed: ") and "EPIPE" in res["stop_reason"]
    assert manifest["video"]["status"] == "failed" and manifest["frames"] == 2
    assert manifest["kept"] >= 3  # the frame whose write failed is kept, never in the stream
    assert [r.frame_id for r in fr.frame_refs(session)] == [0, 1]


def test_a_video_only_recording_without_its_sidecar_refuses_every_part(
        mr: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:  # fmt: skip
    """No fallback: a video recording whose encoder cannot start records nothing (part 0 and a
    resumed part alike) and leaves no session directory behind."""
    rs = _load("record_session")
    ctl, root, _rec = _dirs(tmp_path)
    monkeypatch.setattr(mr, "OPEN_TIMEOUT_S", 0.3)
    real = mr.VideoFeed

    def quick(*a: Any, **k: Any) -> Any:
        return real(*a, **{**k, "open_timeout_s": 0.3})

    monkeypatch.setattr(mr, "VideoFeed", quick)
    for part in (0, 1):
        with pytest.raises(rs.r.Stop, match="the video side cannot start"):
            _record(rs, mr, monkeypatch, ctl, root, 3, fmt=mr.ARM, part=part)
    assert [p.name for p in root.iterdir()] == [".media-rec"]


def test_resume_takes_the_video_format_and_budgets_both_files() -> None:
    rs = _load("record_session")
    calls: list[argparse.Namespace] = []

    def part(a: argparse.Namespace) -> dict[str, Any]:
        calls.append(a)
        why = "io_guard: cg 41.0% (above 30.0% for 30s)" if len(calls) == 1 else "duration"
        return {"dir": f"/rec/{len(calls)}", "frames": 10, "bytes": 1 << 20, "seconds": 100.0,
                "stop_reason": why, "bytes_total": 3 << 20}  # fmt: skip

    rs.wait_ready = lambda first, budget: (True, 0.0)
    a = argparse.Namespace(format=rs.VIDEO_FORMAT, seconds=600.0, max_bytes=10 << 20, resume=2,
                           io_rule="sustained", label="v")  # fmt: skip
    out = rs.record_parts(a, part)
    assert out["parts"] == 2 and [c.max_bytes for c in calls] == [10 << 20, 7 << 20]
