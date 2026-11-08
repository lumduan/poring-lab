#!/usr/bin/env python3
"""The GPU RECORDING BENCH (docs/planning/gpu-recording.md; its bars PRE-REGISTERED 2026-11-08,
before any number existed): would the Arc A380's hardware video encoder (VA-API, low-power
VDEnc) record the lab's frames as well as today's 1-fps lossless PNG, for less?

    gpu_rec_bench.py sample --session SID:MAP [--session SID:MAP ...] [--motion SID]
                            [--runs 2] [--run-len 50] [--motion-len 150] [--motion-start-s 300]
                            [--root /dev/shm/poring-lab-recbench] [--datasets DIR] [--round 1|2]
    (the container side: the guarded one-shot service media-recbench, recbench.sh; the doc's
     section 7 has the exact commands)
    gpu_rec_bench.py score --root ROOT --out OUT.json [--det-threads 8] [--no-detector]
    gpu_rec_bench.py verdict OUT.json

ROUNDS: round 1 (section 8's run) is the original arm table; round 2 (doc 6.6, Batt 2026-11-08
"try fixing the colours too") re-runs its references and adds the GPU-side colour conversion done
right: four GPU colour controls (gctl: the conversion alone, with a luma fingerprint of the
convention it actually used) and two 4:4:4 candidates. ``sample --round N`` writes that round's
arms; ``score`` and ``verdict`` read it back (a score without one is round 1's).

THREE PARTS, one source of truth for the arms (ARMS, below):
  * ``sample`` (host): REAL lab frames, read-only from the NAS. Each ``--session`` is an RDP PNG
    session (the recorder's own lossless frames: their PNG bytes are copied, never re-encoded),
    ``--runs`` contiguous runs of ``--run-len`` frames each, spread over the session
    (run_starts). ``--motion`` is an S2 console H.264 session: ``--motion-len`` consecutive 30-fps
    frames decoded with its own checksums verified (SIZE ONLY at 30 / 10 / 5 fps: its source is
    already lossy). Writes ROOT/in/<sample>/{r0,r1,...}/NNNNNN.png + kind / fps / size / map /
    frames.json, ROOT/in/arms.tsv and an empty ROOT/out. Refuses beyond the RAM limits (CLAUDE.md
    rule 7: an item <= 1 GB, the lab's /dev/shm <= 4 GB, the container's /out cap included).
  * the container (services/media-probe/recbench.sh in the media-probe image): every arm encoded
    by VA-API from the PNGs, the controls, the encode / decode timings and the decoders' frame
    md5s, into ROOT/out. No network; the render node only.
  * ``score`` (host, the main .venv): decodes every bitstream with the host's pinned PyAV
    (software), against the PNG originals: PSNR / SSIM on the game region and three UI crops, the
    saturated-colour keep rate, the second-generation loss through the training cache's JPEG q95,
    the CPU detector's box parity (unit_detector.for_map, scored like gpu_live_parity), each frame
    decoded alone (D1), the decoders' agreement (D2), sizes, GB per hour, CPU per frame; the
    references: the PNG itself and the training cache's JPEG q95 (build_frame_cache.jpeg). Then
    ``verdict`` (pure) applies BARS and names the candidate arm.

Offline: no client, no input, no GPU on the host side. Nothing here writes outside --root and
--out.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import math
import os
import statistics
import sys
import tarfile
import time
from collections.abc import Iterable, Sequence
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import numpy.typing as npt

sys.path.insert(0, str(Path(__file__).resolve().parent))

ROOT_DEFAULT = Path("/dev/shm/poring-lab-recbench")  # NOT under poring-lab-tmp (test_guards)
DATASETS = Path("/mnt/poring-lab-datasets")
SHM = Path("/dev/shm")
ITEM_CAP = 10**9  # CLAUDE.md rule 7: one scratch item
SHM_LAB_CAP = 4 * 10**9  # rule 7: the lab's /dev/shm in total
OUT_CAP = 1_200_000_000  # recbench.sh stops encoding past this much in /out (RECBENCH_OUT_CAP)
MOTION_FRAME_BYTES = 2_300_000  # a level-1 PNG of a 1280 x 720 frame, the upper end measured
COLOR = ("ITU709", "JPEG")  # BT.709, FULL range: the container's forward conversion, inverted here
# UI-text crops in GAME_REGION pixels (x, y, w, h): gm_state.BASIC_INFO_BOX, the docked chat
# window's 6 lines + input bar (chat_window.py: bottom-left, last row 719, pitch 14) and
# hunt_flow.MINIMAP_IMG. A crop that shows the world in some session is still graded.
CROPS: dict[str, tuple[int, int, int, int]] = {
    "basic_info": (0, 0, 220, 140),
    "chat": (0, 600, 600, 120),
    "minimap": (1138, 21, 124, 120),
}
SAT_CORE = (144, 16)  # a clearly saturated PNG pixel: its channel >= 144, both others <= 16
SAT_KEEP = (128, 32)  # ... is KEPT if the decoded pixel still has >= 128 and both others <= 32
PARITY_IOU = 0.7  # gpu_live_parity's same-class match
FPS_LADDER = (1, 5, 10, 30)
JPEG_ARM = "ref-jpeg95"  # the training cache's own encoder (build_frame_cache.jpeg, q95)


# --- the arms (pre-registered; recbench.sh reads them from in/arms.tsv) --------------------------


@dataclass(frozen=True)
class Arm:
    """One encoder setting. ``mode``: ctl (BGR -> YUV by swscale -> raw, the colour round trip
    alone), gctl (round 2: BGRA -> YUV on the GPU by scale_vaapi -> downloaded raw, the GPU's
    conversion alone; reported, never graded), intra (every frame an IDR), vpp (intra, the
    BGR -> YUV conversion on the GPU), gop (an IDR every 30 frames, no B-frames), x (exploratory,
    the lowest quantiser ffmpeg lets us ask for: 0 means "unset" to vaapi_encode; reported, never
    graded). ``samples``: ref (the PNG sessions), motion (the 30 / 10 / 5 fps clips) or all.
    ``frames``: 0 = every frame of a run, else at most that many. ``vpp``: scale_vaapi's options
    (vpp / gctl only). ``color_range``: the DECLARED range, pc (full) or tv (limited): the stream's
    tag and the scorer's inverse conversion (the matrix is always BT.709). ``args``: the encoder's
    own options, appended as written (last in the tsv, so a shell ``read`` gives it the rest)."""

    name: str
    mode: str
    codec: str
    sw_fmt: str  # the upload / raw format ("a|b": the first that encodes, recbench.sh)
    dl_fmt: str  # what the VA decoder downloads ("-" for ctl)
    plane_fmt: str  # the planar format the md5s are taken in
    va_profile: str  # the vainfo profile it needs with VAEntrypointEncSliceLP ("-": none)
    samples: str
    timing: int  # 1: timed in the encode / decode timing pass
    ext: str
    mux: str
    frames: int
    vpp: str = field(default="-", kw_only=True)
    color_range: str = field(default="pc", kw_only=True)
    args: str = ""

    def tsv(self) -> str:
        return "\t".join(str(v) for v in asdict(self).values())


_I = "-g 1 -bf 0"  # every frame an IDR (vaapi_encode: gop 1, idr_interval 0)
_G = "-g 30 -bf 0"  # an IDR every 30 frames: 30 s at 1 fps, 1 s at 30 fps
H264, HEVC, AV1 = "VAProfileH264High", "VAProfileHEVCMain", "VAProfileAV1Profile0"
HEVC444 = "VAProfileHEVCMain444"
# scale_vaapi's colour options (doc 8.1 / 6.6). Round 1 named the matrix and the range only; the
# output frame's primaries stayed "unknown" (the encode log: "vaapi(pc, bt709/unknown/unknown)").
# ffmpeg 8's vaapi_vpp passes VAProcColorStandardExplicit when the driver lists it, and iHD's
# explicit path picks the YUV target colour space from the PRIMARIES alone (matrix ignored),
# falling back to CSpace_BT601 -- BT.601, LIMITED range -- when they are unknown.
VPP_R1 = "out_color_matrix=bt709:out_range=full"  # round 1's exact options (vpp-hevc420-q20)
_P709 = "out_color_primaries=bt709:out_color_transfer=bt709"
VPP_FULL = f"{VPP_R1}:{_P709}"
VPP_TV = f"out_color_matrix=bt709:out_range=limited:{_P709}"
_Q444 = f"-profile:v rext -rc_mode CQP -qp 20 {_I} -aud 1"  # hevc444-q20's encoder options
ARMS: tuple[Arm, ...] = (
    Arm("ctl-yuv444", "ctl", "rawvideo", "yuv444p", "-", "yuv444p", "-", "ref", 0, "yuv",
        "rawvideo", 10, ""),
    Arm("ctl-yuv420", "ctl", "rawvideo", "yuv420p", "-", "yuv420p", "-", "ref", 0, "yuv",
        "rawvideo", 10, ""),
    Arm("hevc420-q14", "intra", "hevc_vaapi", "nv12", "nv12", "yuv420p", HEVC, "ref", 1, "hevc",
        "hevc", 0, f"-rc_mode CQP -qp 14 {_I} -aud 1"),
    Arm("hevc420-q20", "intra", "hevc_vaapi", "nv12", "nv12", "yuv420p", HEVC, "all", 1, "hevc",
        "hevc", 0, f"-rc_mode CQP -qp 20 {_I} -aud 1"),
    Arm("hevc420-q26", "intra", "hevc_vaapi", "nv12", "nv12", "yuv420p", HEVC, "ref", 1, "hevc",
        "hevc", 0, f"-rc_mode CQP -qp 26 {_I} -aud 1"),
    Arm("hevc444-q14", "intra", "hevc_vaapi", "vuyx|vuya", "vuyx", "yuv444p", HEVC444, "ref", 1,
        "hevc", "hevc", 0, f"-profile:v rext -rc_mode CQP -qp 14 {_I} -aud 1"),
    Arm("hevc444-q20", "intra", "hevc_vaapi", "vuyx|vuya", "vuyx", "yuv444p", HEVC444, "ref", 1,
        "hevc", "hevc", 0, f"-profile:v rext -rc_mode CQP -qp 20 {_I} -aud 1"),
    Arm("hevc444-q26", "intra", "hevc_vaapi", "vuyx|vuya", "vuyx", "yuv444p", HEVC444, "ref", 1,
        "hevc", "hevc", 0, f"-profile:v rext -rc_mode CQP -qp 26 {_I} -aud 1"),
    Arm("h264-420-q20", "intra", "h264_vaapi", "nv12", "nv12", "yuv420p", H264, "ref", 1, "h264",
        "h264", 0, f"-profile:v high -rc_mode CQP -qp 20 {_I} -aud 1"),
    Arm("av1-420-g40", "intra", "av1_vaapi", "nv12", "nv12", "yuv420p", AV1, "ref", 1, "obu",
        "obu", 0, f"-rc_mode CQP -global_quality 40 {_I}"),
    Arm("av1-420-g80", "intra", "av1_vaapi", "nv12", "nv12", "yuv420p", AV1, "ref", 1, "obu",
        "obu", 0, f"-rc_mode CQP -global_quality 80 {_I}"),
    Arm("vpp-hevc420-q20", "vpp", "hevc_vaapi", "nv12", "nv12", "yuv420p", HEVC, "ref", 1,
        "hevc", "hevc", 0, f"-rc_mode CQP -qp 20 {_I} -aud 1", vpp=VPP_R1),
    Arm("hevc420-q20-g30", "gop", "hevc_vaapi", "nv12", "nv12", "yuv420p", HEVC, "all", 0,
        "hevc", "hevc", 0, f"-rc_mode CQP -qp 20 {_G} -aud 1"),
    Arm("hevc444-q20-g30", "gop", "hevc_vaapi", "vuyx|vuya", "vuyx", "yuv444p", HEVC444, "all", 0,
        "hevc", "hevc", 0, f"-profile:v rext -rc_mode CQP -qp 20 {_G} -aud 1"),
    Arm("h264-420-q20-g30", "gop", "h264_vaapi", "nv12", "nv12", "yuv420p", H264, "all", 0,
        "h264", "h264", 0, f"-profile:v high -rc_mode CQP -qp 20 {_G} -aud 1"),
    Arm("x-hevc444-q1", "x", "hevc_vaapi", "vuyx|vuya", "vuyx", "yuv444p", HEVC444, "ref", 0,
        "hevc", "hevc", 10, f"-profile:v rext -rc_mode CQP -qp 1 {_I} -aud 1"),
    Arm("x-av1-g1", "x", "av1_vaapi", "nv12", "nv12", "yuv420p", AV1, "ref", 0, "obu", "obu", 10,
        f"-rc_mode CQP -global_quality 1 {_I}"),
    # --- round 2 (doc 6.6, PRE-REGISTERED before its run): the GPU's own conversion -------------
    # the controls: BGRA -> scale_vaapi -> downloaded raw, 10 frames a run (never graded)
    Arm("gctl-vpp420-r1", "gctl", "rawvideo", "nv12", "-", "yuv420p", "-", "ref", 0, "yuv",
        "rawvideo", 10, "", vpp=VPP_R1),
    Arm("gctl-vpp420", "gctl", "rawvideo", "nv12", "-", "yuv420p", "-", "ref", 0, "yuv",
        "rawvideo", 10, "", vpp=VPP_FULL),
    Arm("gctl-vpp444", "gctl", "rawvideo", "vuyx|vuya", "-", "yuv444p", "-", "ref", 0, "yuv",
        "rawvideo", 10, "", vpp=VPP_FULL),
    Arm("gctl-vpp444-tv", "gctl", "rawvideo", "vuyx|vuya", "-", "yuv444p", "-", "ref", 0, "yuv",
        "rawvideo", 10, "", vpp=VPP_TV, color_range="tv"),
    # the candidates: hevc444-q20's encoder, the conversion on the GPU (8-bit 4:4:4 surfaces)
    Arm("vpp-hevc444-q20", "vpp", "hevc_vaapi", "vuyx|vuya", "vuyx", "yuv444p", HEVC444, "ref", 1,
        "hevc", "hevc", 0, _Q444, vpp=VPP_FULL),
    Arm("vpp-hevc444-q20-tv", "vpp", "hevc_vaapi", "vuyx|vuya", "vuyx", "yuv444p", HEVC444, "ref",
        1, "hevc", "hevc", 0, _Q444, vpp=VPP_TV, color_range="tv"),
)  # fmt: skip
GRADED_MODES = ("intra", "vpp", "gop")
CANDIDATE_MODES = ("intra", "vpp")
CONTROL_MODES = ("ctl", "gctl")
DECODERS = {"hevc": "hevc", "h264": "h264", "obu": "libdav1d"}  # host software decoders
DEMUXERS = {"hevc": "hevc", "h264": "h264", "obu": "obu"}
# Which arms each round runs, in the container's order. Round 1 is the original table (section
# 8's run); round 2 re-runs its references so it stands on its own (doc 6.6). A score without a
# "round" is round 1's.
ROUNDS: dict[int, tuple[str, ...]] = {
    1: ("ctl-yuv444", "ctl-yuv420", "hevc420-q14", "hevc420-q20", "hevc420-q26", "hevc444-q14",
        "hevc444-q20", "hevc444-q26", "h264-420-q20", "av1-420-g40", "av1-420-g80",
        "vpp-hevc420-q20", "hevc420-q20-g30", "hevc444-q20-g30", "h264-420-q20-g30",
        "x-hevc444-q1", "x-av1-g1"),
    2: ("ctl-yuv444", "ctl-yuv420", "gctl-vpp420-r1", "gctl-vpp420", "gctl-vpp444",
        "gctl-vpp444-tv", "hevc444-q20", "vpp-hevc444-q20", "vpp-hevc444-q20-tv"),
}  # fmt: skip
# the encode timing pass: passes per arm (round 2 grades S2 / S3 on their MEDIAN, doc 6.6)
TIMING_REPS = {1: 1, 2: 3}


def arm_by_name(name: str) -> Arm:
    return next(a for a in ARMS if a.name == name)


def round_arms(n: int) -> tuple[Arm, ...]:
    """The arms of round ``n``, in its order (KeyError for an unknown round)."""
    return tuple(arm_by_name(name) for name in ROUNDS[n])


def arms_tsv(arms: Sequence[Arm] | None = None) -> str:
    """PURE: the container's arm table, one tab-separated line per arm (the args last, so a shell
    `read` gives it the rest of the line); round 1's arms by default."""
    head = "#" + "\t".join(Arm.__dataclass_fields__)
    rows = round_arms(1) if arms is None else arms
    return "\n".join([head, *(a.tsv() for a in rows)]) + "\n"


def arm_color(arm: Arm) -> tuple[str, str]:
    """PURE: the arm's DECLARED convention as the scorer inverts it: BT.709, and its range (pc =
    full = round 1's COLOR, tv = limited)."""
    if arm.color_range not in ("pc", "tv"):
        raise ValueError(f"{arm.name}: color_range {arm.color_range!r}")
    return (COLOR[0], "JPEG" if arm.color_range == "pc" else "MPEG")


# --- the pre-registered bars (the doc's section 6 table carries the same ids and values) --------

BARS: dict[str, float] = {
    # ctl-yuv444 on every ref sample, else the colour handling is wrong. An 8-bit BT.709 4:4:4
    # round trip through swscale gave 48.7 dB / max 2 on a synthetic frame (the e2e test); a range
    # or matrix mix-up errs by more than 10 (doc 6.4)
    "V1_psnr": 45.0,
    "V1_maxabs": 4.0,
    "Q1_psnr_vs_jpeg": 0.0,  # psnr_mean >= the JPEG q95 reference's + this
    "Q2_psnr_min": 36.0,  # the worst frame's game PSNR
    "Q3_ssim_vs_jpeg": -0.002,  # ssim_mean >= the JPEG reference's + this
    "Q3_ssim_min": 0.97,
    "Q4_crop_vs_jpeg": -0.5,  # each UI crop's psnr_mean >= the JPEG reference's + this
    "Q5_crop_min": 32.0,  # each UI crop's worst frame
    "Q6_sat_keep": 0.95,
    "Q6_min_pixels": 1000,  # fewer saturated core pixels in a sample: NA
    "G1_gen2": -1.0,  # psnr(png, jpeg95(decoded)) - psnr(png, jpeg95(png))
    "P1_of": 0.97,  # matched / PNG boxes and matched / decoded boxes
    "P_min_boxes": 100,  # fewer PNG boxes in a sample: P1-P3 NA (underpowered) there
    "P2_vs_jpeg": -0.01,  # both fractions >= the JPEG reference's + this
    "P3_coord_med": 1.0,
    "P3_coord_p95": 3.0,
    "S1_size_ratio": 0.25,  # bytes per frame <= this x the PNG's, every ref sample
    "S2_cpu_ms": 15.0,  # the container's CPU ms per encoded frame (raw BGRA in RAM)
    "S2_png_ratio": 0.10,  # ... and <= this x the host's encode_png (level 1)
    "S3_fps": 60.0,
}


# --- pure helpers --------------------------------------------------------------------------------


def run_starts(n_frames: int, runs: int, run_len: int) -> list[int]:
    """PURE: the first frame index of each of ``runs`` contiguous runs of ``run_len`` frames, run k
    centred on (k + 0.5) / runs of the session, clamped into it. Raises when they do not fit."""
    if runs < 1 or run_len < 1 or runs * run_len > n_frames:
        raise ValueError(f"{runs} runs of {run_len} frames do not fit in {n_frames} frames")
    starts = []
    for k in range(runs):
        s = round((k + 0.5) * n_frames / runs) - run_len // 2
        starts.append(max(0, min(n_frames - run_len, s)))
    for a, b in zip(starts, starts[1:], strict=False):
        if b < a + run_len:
            raise ValueError(f"runs overlap: {starts}")
    return starts


def shm_refusal(used: int, planned: int, *, out_cap: int = OUT_CAP,
                lab_cap: int = SHM_LAB_CAP, item_cap: int = ITEM_CAP,
                largest_item: int = 0) -> str | None:  # fmt: skip
    """PURE: why the sample may not be written (rule 7), or None."""
    if largest_item > item_cap:
        return (
            f"a sample of {largest_item / 1e9:.2f} GB is over the {item_cap / 1e9:.1f} GB item cap"
        )
    if used + planned + out_cap > lab_cap:
        return (f"/dev/shm would reach {(used + planned + out_cap) / 1e9:.2f} GB (used "
                f"{used / 1e9:.2f} + sample {planned / 1e9:.2f} + the container's out cap "
                f"{out_cap / 1e9:.2f}) > the lab's {lab_cap / 1e9:.1f} GB")  # fmt: skip
    return None


def psnr(a: npt.NDArray[np.uint8], b: npt.NDArray[np.uint8]) -> float:
    """PURE: PSNR in dB over every pixel and channel; identical images give 100.0 (a cap)."""
    if a.shape != b.shape:
        raise ValueError(f"shapes differ: {a.shape} vs {b.shape}")
    mse = float(np.mean((a.astype(np.float64) - b.astype(np.float64)) ** 2))
    return 100.0 if mse == 0.0 else min(100.0, 10.0 * math.log10(255.0**2 / mse))


def luma(bgr: npt.NDArray[np.uint8]) -> npt.NDArray[np.float64]:
    """PURE: BT.601 luma, float, from a BGR image (SSIM's input)."""
    f = bgr.astype(np.float64)
    return 0.114 * f[..., 0] + 0.587 * f[..., 1] + 0.299 * f[..., 2]


def _box_sum(x: npt.NDArray[np.float64], w: int) -> npt.NDArray[np.float64]:
    """Sums of every w x w window (valid positions only), by an integral image."""
    s = np.zeros((x.shape[0] + 1, x.shape[1] + 1), np.float64)
    s[1:, 1:] = x.cumsum(0).cumsum(1)
    return s[w:, w:] - s[:-w, w:] - s[w:, :-w] + s[:-w, :-w]


def ssim_luma(a: npt.NDArray[np.uint8], b: npt.NDArray[np.uint8], win: int = 8) -> float:
    """PURE: mean SSIM of the two images' luma over every ``win`` x ``win`` window (stride 1, a
    uniform window), K1 0.01, K2 0.03, L 255."""
    if a.shape != b.shape:
        raise ValueError(f"shapes differ: {a.shape} vs {b.shape}")
    x, y = luma(a), luma(b)
    n = float(win * win)
    mx, my = _box_sum(x, win) / n, _box_sum(y, win) / n
    vx = _box_sum(x * x, win) / n - mx * mx
    vy = _box_sum(y * y, win) / n - my * my
    cxy = _box_sum(x * y, win) / n - mx * my
    c1, c2 = (0.01 * 255) ** 2, (0.03 * 255) ** 2
    s = ((2 * mx * my + c1) * (2 * cxy + c2)) / ((mx * mx + my * my + c1) * (vx + vy + c2))
    return float(np.mean(s))


def crop(img: npt.NDArray[np.uint8], box: tuple[int, int, int, int]) -> npt.NDArray[np.uint8]:
    x, y, w, h = box
    return img[y : y + h, x : x + w]


def sat_counts(ref: npt.NDArray[np.uint8], dec: npt.NDArray[np.uint8]) -> tuple[int, int]:
    """PURE: (clearly saturated pixels in ``ref``, how many of them ``dec`` keeps). A pixel is
    clearly saturated in channel c when c >= SAT_CORE[0] and the other two <= SAT_CORE[1]; kept
    when the decoded pixel still has c >= SAT_KEEP[0] and the other two <= SAT_KEEP[1] (the
    no-entry ring, red damage text, coloured UI: what 4:2:0 smears)."""
    total = kept = 0
    for c in range(3):
        o = [i for i in range(3) if i != c]
        core = (
            (ref[..., c] >= SAT_CORE[0])
            & (ref[..., o[0]] <= SAT_CORE[1])
            & (ref[..., o[1]] <= SAT_CORE[1])
        )
        keep = (
            (dec[..., c] >= SAT_KEEP[0])
            & (dec[..., o[0]] <= SAT_KEEP[1])
            & (dec[..., o[1]] <= SAT_KEEP[1])
        )
        total += int(core.sum())
        kept += int((core & keep).sum())
    return total, kept


def planar_bytes(planes: Sequence[npt.NDArray[np.uint8]]) -> bytes:
    """PURE: the planes, each cropped to its width, concatenated: ffmpeg's framemd5 layout."""
    return b"".join(np.ascontiguousarray(p).tobytes() for p in planes)


def md5_hex(data: bytes) -> str:
    return hashlib.md5(data, usedforsecurity=False).hexdigest()


def parse_framemd5(text: str) -> list[str]:
    """PURE: the per-frame md5s of an ffmpeg `-f framemd5` file, in order."""
    out = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        out.append(line.rsplit(",", 1)[1].strip())
    return out


def parse_tsv(text: str, fields: Sequence[str]) -> list[dict[str, str]]:
    """PURE: tab-separated rows (no header; '#' comments skipped) as dicts; a short row is padded
    with empty strings, an over-long row keeps the rest in its last field."""
    rows = []
    for line in text.splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        parts = line.split("\t", len(fields) - 1)
        parts += [""] * (len(fields) - len(parts))
        rows.append(dict(zip(fields, parts, strict=True)))
    return rows


STATUS_FIELDS = ("arm", "sample", "run", "status", "bytes", "note")
TIMING_FIELDS = ("name", "frames", "rtime", "utime", "stime", "status", "note")


def timing_row(row: dict[str, str]) -> dict[str, Any]:
    """PURE: a recbench.sh timing row -> frames, CPU ms per frame, fps (None when not measured)."""
    try:
        frames, rt = int(row["frames"]), float(row["rtime"])
        cpu = float(row["utime"]) + float(row["stime"])
    except (KeyError, ValueError):
        return {"status": row.get("status") or "failed", "note": row.get("note", "")}
    ok = row.get("status") == "ok" and frames > 0 and rt > 0
    return {
        "status": row.get("status"), "frames": frames, "note": row.get("note", ""),
        "cpu_ms_per_frame": round(cpu * 1000 / frames, 3) if ok else None,
        "fps": round(frames / rt, 1) if ok else None,
    }  # fmt: skip


def merge_timing(rows: Sequence[dict[str, str]]) -> dict[str, dict[str, Any]]:
    """PURE: timing.tsv rows -> one entry per name. A name with ONE ok row is exactly its
    timing_row (round 1: one pass per arm, plus a failed loop pass before some decode fallbacks);
    several ok rows (round 2: TIMING_REPS passes) give the MEDIAN CPU ms per frame and fps, with
    every pass listed; a name with no ok row keeps its last row, as round 1's scorer did."""
    by: dict[str, list[dict[str, Any]]] = {}
    for r in rows:
        by.setdefault(r["name"], []).append(timing_row(r))
    out: dict[str, dict[str, Any]] = {}
    for name, got in by.items():
        ok = [t for t in got if t.get("cpu_ms_per_frame") is not None]
        if len(ok) <= 1:
            out[name] = ok[0] if ok else got[-1]
            continue
        cpu = [t["cpu_ms_per_frame"] for t in ok]
        fps = [t["fps"] for t in ok]
        out[name] = {
            "status": "ok", "frames": ok[0]["frames"], "note": ok[0]["note"],
            "cpu_ms_per_frame": round(statistics.median(cpu), 3),
            "fps": round(statistics.median(fps), 1),
            "passes": len(ok), "cpu_ms_passes": cpu, "fps_passes": fps,
        }  # fmt: skip
    return out


# --- the colour fingerprint (round 2): which convention did a YUV plane actually get? ----------

# Y' = scale * (kr R + kg G + kb B) + offset, 8-bit, per named convention
CONVENTIONS: dict[str, tuple[float, float, float, float, float]] = {
    "bt709-full": (0.2126, 0.7152, 0.0722, 1.0, 0.0),
    "bt709-limited": (0.2126, 0.7152, 0.0722, 219 / 255, 16.0),
    "bt601-full": (0.299, 0.587, 0.114, 1.0, 0.0),
    "bt601-limited": (0.299, 0.587, 0.114, 219 / 255, 16.0),
}
FIT_NAMED_LEVELS = 3.0  # a fit within this many 8-bit levels of a convention is NAMED (doc 6.6)
RAW_FORMATS = ("yuv444p", "yuv420p", "nv12", "vuyx", "vuya")


def raw_frame_bytes(fmt: str, w: int, h: int) -> int:
    """PURE: bytes of one raw frame of ``fmt``."""
    if fmt == "yuv444p":
        return w * h * 3
    if fmt in ("yuv420p", "nv12"):
        return w * h * 3 // 2
    if fmt in ("vuyx", "vuya"):
        return w * h * 4
    raise ValueError(f"unknown raw format {fmt!r}")


def raw_planes(data: bytes, fmt: str, w: int, h: int) -> list[tuple[npt.NDArray[np.uint8], ...]]:
    """PURE: a raw file of ``fmt`` frames -> (Y, U, V) per frame, each plane at its own size. NV12's
    interleaved chroma is U then V; VUYX / VUYA (ffmpeg's packed 4:4:4) is V, U, Y, X/A bytes."""
    per = raw_frame_bytes(fmt, w, h)
    out = []
    for i in range(len(data) // per):
        buf = np.frombuffer(data, np.uint8, per, i * per)
        if fmt == "yuv444p":
            p = buf.reshape(3, h, w)
            out.append((p[0], p[1], p[2]))
        elif fmt == "yuv420p":
            n, c = w * h, (w // 2) * (h // 2)
            out.append((buf[:n].reshape(h, w), buf[n : n + c].reshape(h // 2, w // 2),
                        buf[n + c :].reshape(h // 2, w // 2)))  # fmt: skip
        elif fmt == "nv12":
            uv = buf[w * h :].reshape(h // 2, w // 2, 2)
            out.append((buf[: w * h].reshape(h, w), uv[..., 0], uv[..., 1]))
        else:
            px = buf.reshape(h, w, 4)
            out.append((px[..., 2], px[..., 1], px[..., 0]))
    return out


def planar_array(planes: tuple[npt.NDArray[np.uint8], ...]) -> npt.NDArray[np.uint8]:
    """PURE: (Y, U, V) -> the array PyAV's VideoFrame.from_ndarray takes for yuv444p (3, h, w) or
    yuv420p (h * 3 / 2, w): read_raw_yuv's own layout."""
    y, u, v = planes
    h, w = y.shape
    if u.shape == y.shape:
        return np.stack([y, u, v])
    flat = np.concatenate([np.ascontiguousarray(p).reshape(-1) for p in (y, u, v)])
    return flat.reshape(h * 3 // 2, w)


def luma_fit(refs: Sequence[npt.NDArray[np.uint8]], ys: Sequence[npt.NDArray[np.uint8]],
             step: int = 4) -> dict[str, Any]:  # fmt: skip
    """PURE: least squares Y = a_r R + a_g G + a_b B + c over every ``step``-th pixel (both axes)
    of the BGR originals and the Y planes a conversion wrote: the matrix and the range it USED, as
    numbers (a limited range shows as scale ~0.859 and offset ~16, BT.601 as a_r / scale ~0.3)."""
    xs, ts = [], []
    for bgr, y in zip(refs, ys, strict=True):
        s = bgr[::step, ::step].reshape(-1, 3).astype(np.float64)
        xs.append(np.column_stack([s[:, 2], s[:, 1], s[:, 0], np.ones(len(s))]))
        ts.append(y[::step, ::step].reshape(-1).astype(np.float64))
    x, t = np.concatenate(xs), np.concatenate(ts)
    coef, *_ = np.linalg.lstsq(x, t, rcond=None)
    rms = float(np.sqrt(np.mean((x @ coef - t) ** 2)))
    kr, kg, kb, c = (float(v) for v in coef)
    scale = kr + kg + kb
    name, err = name_convention(kr, kg, kb, c)
    return {"kr": round(kr, 4), "kg": round(kg, 4), "kb": round(kb, 4), "offset": round(c, 2),
            "scale": round(scale, 4), "rms": round(rms, 3), "pixels": int(len(t)),
            "convention": name, "convention_err_levels": round(err, 2)}  # fmt: skip


def name_convention(kr: float, kg: float, kb: float, offset: float) -> tuple[str, float]:
    """PURE: the nearest named convention to a fitted luma, and its distance in 8-bit levels (the
    largest of: each coefficient's difference x 255, the offset's difference); "none" when even
    the nearest is more than FIT_NAMED_LEVELS away."""
    best, best_err = "none", math.inf
    for name, (r, g, b, scale, off) in CONVENTIONS.items():
        err = max(abs(kr - scale * r) * 255, abs(kg - scale * g) * 255,
                  abs(kb - scale * b) * 255, abs(offset - off))  # fmt: skip
        if err < best_err:
            best, best_err = name, err
    return (best if best_err <= FIT_NAMED_LEVELS else "none"), best_err


def plane_diff(a: Sequence[npt.NDArray[np.uint8]], b: Sequence[npt.NDArray[np.uint8]]
               ) -> dict[str, dict[str, float]]:  # fmt: skip
    """PURE: plane by plane (Y, U, V), ``a`` minus ``b``: the mean signed difference, the mean and
    the largest absolute difference (the GPU's planes against swscale's of the same frames)."""
    out = {}
    for k, pa, pb in zip("YUV", a, b, strict=True):
        if pa.shape != pb.shape:
            raise ValueError(f"plane {k}: {pa.shape} vs {pb.shape}")
        d = pa.astype(np.int16) - pb.astype(np.int16)
        out[k] = {"mean": round(float(d.mean()), 3), "mean_abs": round(float(np.abs(d).mean()), 3),
                  "max_abs": int(np.abs(d).max())}  # fmt: skip
    return out


VUI_RANGE = {0: "unspecified", 1: "tv", 2: "pc"}
VUI_MATRIX = {0: "gbr", 1: "bt709", 2: "unspecified", 5: "bt470bg", 6: "smpte170m", 9: "bt2020nc"}


def vui_of(frame: Any) -> dict[str, str]:
    """A decoded frame's signalled range and matrix (the bitstream's VUI as libavcodec reads it)."""
    return {"range": VUI_RANGE.get(int(frame.color_range), str(frame.color_range)),
            "matrix": VUI_MATRIX.get(int(frame.colorspace), str(frame.colorspace))}  # fmt: skip


def nearest_rank(vals: Sequence[float], q: float) -> float | None:
    s = sorted(vals)
    return s[min(len(s) - 1, int(q * len(s)))] if s else None


def parity_stats(pairs: Iterable[tuple[Sequence[Sequence[Any]], Sequence[Sequence[Any]]]],
                 thr: float = PARITY_IOU) -> dict[str, Any]:  # fmt: skip
    """PURE: (PNG rows, decoded rows) per frame -> box counts, matched fractions and the matched
    pairs' largest coordinate difference (median / p95), rows as gpu_live_parity.rows makes them."""
    from gpu_live_parity import match_same_class

    n_p = n_d = n_m = 0
    diffs: list[float] = []
    for ref, dec in pairs:
        m = match_same_class(ref, dec, thr)
        n_p, n_d, n_m = n_p + len(ref), n_d + len(dec), n_m + len(m)
        diffs += [max(abs(float(ref[i][k]) - float(dec[j][k])) for k in range(4)) for i, j, _ in m]
    return {
        "png_boxes": n_p, "dec_boxes": n_d, "matched": n_m,
        "of_png": round(n_m / n_p, 4) if n_p else None,
        "of_dec": round(n_m / n_d, 4) if n_d else None,
        "coord_med": round(statistics.median(diffs), 2) if diffs else None,
        "coord_p95": round(nearest_rank(diffs, 0.95) or 0.0, 2) if diffs else None,
    }  # fmt: skip


def gb_per_hour(bytes_per_frame: float, fps: float) -> float:
    """PURE: decimal GB an hour at ``fps`` kept frames a second."""
    return round(bytes_per_frame * fps * 3600 / 1e9, 2)


def frame_metrics(ref: npt.NDArray[np.uint8], dec: npt.NDArray[np.uint8]) -> dict[str, Any]:
    """PURE: one decoded frame against its PNG original."""
    total, kept = sat_counts(ref, dec)
    return {
        "psnr": psnr(ref, dec), "ssim": ssim_luma(ref, dec),
        "maxabs": int(np.max(np.abs(ref.astype(np.int16) - dec.astype(np.int16)))),
        "crops": {k: psnr(crop(ref, b), crop(dec, b)) for k, b in CROPS.items()},
        "sat": (total, kept),
    }  # fmt: skip


def summarise(per_frame: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """PURE: frame_metrics rows -> an arm-sample's quality summary."""
    if not per_frame:
        return {}
    ps = [f["psnr"] for f in per_frame]
    ss = [f["ssim"] for f in per_frame]
    total = sum(f["sat"][0] for f in per_frame)
    kept = sum(f["sat"][1] for f in per_frame)
    out: dict[str, Any] = {
        "frames": len(per_frame), "psnr_mean": round(statistics.fmean(ps), 3),
        "psnr_min": round(min(ps), 3), "ssim_mean": round(statistics.fmean(ss), 5),
        "ssim_min": round(min(ss), 5), "maxabs": max(f["maxabs"] for f in per_frame),
        "sat_count": total, "sat_kept": kept,
        "sat_keep": round(kept / total, 4) if total else None,
        "crops": {},
    }  # fmt: skip
    for k in CROPS:
        cs = [f["crops"][k] for f in per_frame]
        out["crops"][k] = {"psnr_mean": round(statistics.fmean(cs), 3),
                           "psnr_min": round(min(cs), 3)}  # fmt: skip
    if all("gen2" in f for f in per_frame):
        out["gen2_psnr_mean"] = round(statistics.fmean(f["gen2"] for f in per_frame), 3)
    return out


# --- the verdict (pure) --------------------------------------------------------------------------


def _bar(ok: bool | None, value: Any, need: str) -> dict[str, Any]:
    return {"result": "NA" if ok is None else ("PASS" if ok else "FAIL"), "value": value,
            "need": need}  # fmt: skip


def bars_for(arm: dict[str, Any], jpeg: dict[str, Any] | None, png: dict[str, Any],
             timing: dict[str, Any] | None, mode: str,
             bars: dict[str, float] = BARS) -> dict[str, dict[str, Any]]:  # fmt: skip
    """PURE: one arm on one ref sample -> {bar id: {result, value, need}}."""
    b = bars
    q = arm.get("quality") or {}
    jq = (jpeg or {}).get("quality") or {}
    out: dict[str, dict[str, Any]] = {}
    if not q or not jq:
        return {"Q": _bar(False, None, "a quality summary and the JPEG reference's")}
    out["Q1"] = _bar(q["psnr_mean"] >= jq["psnr_mean"] + b["Q1_psnr_vs_jpeg"], q["psnr_mean"],
                     f">= jpeg {jq['psnr_mean']} + {b['Q1_psnr_vs_jpeg']}")  # fmt: skip
    out["Q2"] = _bar(q["psnr_min"] >= b["Q2_psnr_min"], q["psnr_min"], f">= {b['Q2_psnr_min']}")
    out["Q3"] = _bar(q["ssim_mean"] >= jq["ssim_mean"] + b["Q3_ssim_vs_jpeg"]
                     and q["ssim_min"] >= b["Q3_ssim_min"], [q["ssim_mean"], q["ssim_min"]],
                     f"mean >= jpeg {jq['ssim_mean']} {b['Q3_ssim_vs_jpeg']:+}, "
                     f"min >= {b['Q3_ssim_min']}")  # fmt: skip
    worst_rel = min(q["crops"][k]["psnr_mean"] - jq["crops"][k]["psnr_mean"] for k in CROPS)
    out["Q4"] = _bar(worst_rel >= b["Q4_crop_vs_jpeg"], round(worst_rel, 3),
                     f"every crop's mean - jpeg's >= {b['Q4_crop_vs_jpeg']}")  # fmt: skip
    worst_min = min(q["crops"][k]["psnr_min"] for k in CROPS)
    out["Q5"] = _bar(worst_min >= b["Q5_crop_min"], worst_min, f">= {b['Q5_crop_min']}")
    sat_ok = (None if q["sat_count"] < b["Q6_min_pixels"] or q["sat_keep"] is None
              else q["sat_keep"] >= b["Q6_sat_keep"])  # fmt: skip
    out["Q6"] = _bar(sat_ok, [q["sat_keep"], q["sat_count"]], f">= {b['Q6_sat_keep']}")
    if "gen2_psnr_mean" in q:
        gen2 = round(q["gen2_psnr_mean"] - jq["psnr_mean"], 3)
        out["G1"] = _bar(gen2 >= b["G1_gen2"], gen2, f">= {b['G1_gen2']}")
    else:
        out["G1"] = _bar(False, None, "the second-generation JPEG measured")
    p, jp = arm.get("parity"), (jpeg or {}).get("parity")
    if p is None or jp is None:
        out["P"] = _bar(None, None, "the detector run (score without --no-detector)")
    elif p["png_boxes"] < b["P_min_boxes"]:
        out["P"] = _bar(None, p["png_boxes"], f"underpowered: < {b['P_min_boxes']} PNG boxes")
    else:
        fr = (p["of_png"] or 0.0, p["of_dec"] or 0.0)
        jfr = (jp["of_png"] or 0.0, jp["of_dec"] or 0.0)
        out["P1"] = _bar(min(fr) >= b["P1_of"], list(fr), f"both >= {b['P1_of']}")
        out["P2"] = _bar(fr[0] >= jfr[0] + b["P2_vs_jpeg"] and fr[1] >= jfr[1] + b["P2_vs_jpeg"],
                         list(fr), f"both >= jpeg {list(jfr)} {b['P2_vs_jpeg']:+}")  # fmt: skip
        med, p95 = p["coord_med"], p["coord_p95"]
        out["P3"] = _bar(
            med is not None
            and p95 is not None
            and med <= b["P3_coord_med"]
            and p95 <= b["P3_coord_p95"],
            [med, p95],
            f"median <= {b['P3_coord_med']}, p95 <= {b['P3_coord_p95']} px",
        )
    if mode in CANDIDATE_MODES:
        d1 = arm.get("d1") or {}
        out["D1"] = _bar(
            bool(d1) and d1["alone_identical"] == d1["frames"] > 0,
            [d1.get("alone_identical"), d1.get("frames")],
            "every frame alone",
        )
        d2 = arm.get("d2") or {}
        out["D2"] = _bar(bool(d2) and d2["compared"] > 0
                         and d2["va_eq_sw"] == d2["host_eq_sw"] == d2["compared"],
                         [d2.get("va_eq_sw"), d2.get("host_eq_sw"), d2.get("compared")],
                         "VA == SW == host, every frame")  # fmt: skip
    ratio = arm["bytes_per_frame"] / png["bytes_per_frame"]
    out["S1"] = _bar(ratio <= b["S1_size_ratio"], round(ratio, 4), f"<= {b['S1_size_ratio']}")
    t = timing or {}
    cpu, fps = t.get("cpu_ms_per_frame"), t.get("fps")
    if mode in CANDIDATE_MODES:
        enc_png = png.get("encode_png_ms")
        out["S2"] = _bar(
            None
            if cpu is None or enc_png is None
            else cpu <= b["S2_cpu_ms"] and cpu <= b["S2_png_ratio"] * enc_png,
            [cpu, enc_png],
            f"<= {b['S2_cpu_ms']} ms and <= {b['S2_png_ratio']} x encode_png",
        )
        out["S3"] = _bar(None if fps is None else fps >= b["S3_fps"], fps, f">= {b['S3_fps']}")
    return out


def verdict(score: dict[str, Any], bars: dict[str, float] = BARS) -> dict[str, Any]:
    """PURE: the pre-registered decision. V1 first (the colour round trip, else nothing is valid);
    then every graded arm on every ref sample; the CANDIDATE is the smallest (mean bytes per frame
    over the ref samples) intra / vpp arm with no FAIL anywhere, P powered on at least one sample,
    and S2 / S3 measured (not NA)."""
    refs = {s: v for s, v in score["samples"].items() if v.get("kind") == "ref"}
    v1: dict[str, Any] = {}
    valid = bool(refs)
    for s, v in refs.items():
        ctl = (v["arms"].get("ctl-yuv444") or {}).get("quality") or {}
        ok = (
            bool(ctl) and ctl["psnr_mean"] >= bars["V1_psnr"] and ctl["maxabs"] <= bars["V1_maxabs"]
        )
        v1[s] = _bar(ok, [ctl.get("psnr_mean"), ctl.get("maxabs")],
                     f"psnr >= {bars['V1_psnr']}, maxabs <= {bars['V1_maxabs']}")  # fmt: skip
        valid = valid and ok
    out: dict[str, Any] = {"valid": valid, "V1": v1, "arms": {}, "candidate": None}
    if not valid:
        out["note"] = "V1 failed: the colour handling is not what the bench assumes; no verdict"
        return out
    sizes: dict[str, float] = {}
    for a in round_arms(int(score.get("round", 1))):
        if a.mode not in GRADED_MODES:
            continue
        per: dict[str, Any] = {}
        ok = True
        powered = False
        for s, v in refs.items():
            arm = v["arms"].get(a.name)
            if not arm or arm.get("status") != "ok":
                per[s] = {"status": (arm or {}).get("status", "not run"),
                          "note": (arm or {}).get("note", "")}  # fmt: skip
                ok = False
                continue
            timing = (score.get("timing") or {}).get(f"enc_{a.name}")
            per[s] = bars_for(arm, v["arms"].get(JPEG_ARM), v["png"], timing, a.mode, bars)
            results = [r["result"] for r in per[s].values()]
            ok = ok and "FAIL" not in results
            powered = powered or "P1" in per[s]
            if a.mode in CANDIDATE_MODES and any(
                (per[s].get(k) or {}).get("result") in (None, "NA") for k in ("S2", "S3")
            ):
                ok = False
        passed = ok and powered
        out["arms"][a.name] = {"mode": a.mode, "pass": passed, "samples": per}
        if passed and a.mode in CANDIDATE_MODES:
            sizes[a.name] = statistics.fmean(refs[s]["arms"][a.name]["bytes_per_frame"]
                                             for s in refs)  # fmt: skip
    if sizes:
        out["candidate"] = min(sizes, key=lambda k: sizes[k])
    return out


def controls_summary(score: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """PURE: the colour controls per ref sample (reported, never graded; doc 6.6): the round trip's
    PSNR and largest error under the arm's DECLARED convention, the luma fingerprint (the
    convention the conversion actually used), and the GPU planes against swscale's."""
    out: dict[str, dict[str, Any]] = {}
    for s, v in score["samples"].items():
        if v.get("kind") != "ref":
            continue
        for name, arm in v["arms"].items():
            if arm.get("mode") not in CONTROL_MODES or arm.get("status") != "ok":
                continue
            q, fit = arm.get("quality") or {}, arm.get("fit") or {}
            out.setdefault(s, {})[name] = {
                "declared": arm.get("declared"), "psnr_mean": q.get("psnr_mean"),
                "maxabs": q.get("maxabs"), "sat_keep": q.get("sat_keep"),
                "fit": fit.get("convention"), "fit_err_levels": fit.get("convention_err_levels"),
                "scale": fit.get("scale"), "offset": fit.get("offset"),
                "vs_swscale_Y": (arm.get("vs_swscale") or {}).get("Y"),
            }  # fmt: skip
    return out


# --- sample (host, the NAS read-only) ------------------------------------------------------------


def shm_used() -> int:
    st = os.statvfs(SHM)
    return (st.f_blocks - st.f_bfree) * st.f_frsize


def png_session_frames(session: Path, wanted: set[int]) -> dict[int, tuple[bytes, dict[str, Any]]]:
    """The PNG bytes (verbatim) and json meta of the wanted frame indices (shard order) of a PNG
    session; reads tar headers and only the wanted members."""
    manifest = json.loads((session / "manifest.json").read_text())
    if (manifest.get("format") or "png") != "png":
        raise SystemExit(f"{session.name}: not a PNG session ({manifest.get('format')})")
    out: dict[int, tuple[bytes, dict[str, Any]]] = {}
    index = -1
    last = max(wanted)
    for shard in manifest["shards"]:
        with tarfile.open(session / shard, "r:") as tar:
            pending: dict[str, int] = {}
            for m in tar:
                key, _, ext = m.name.partition(".")
                if ext == "png":
                    index += 1
                    if index in wanted:
                        fh = tar.extractfile(m)
                        assert fh is not None
                        out[index] = (fh.read(), {})
                        pending[key] = index
                elif ext == "json" and key in pending:
                    fh = tar.extractfile(m)
                    assert fh is not None
                    out[pending.pop(key)][1].update(json.loads(fh.read()))
                if index > last and not pending:
                    return out
    return out


def write_sample(root: Path, name: str, kind: str, fps: int, size: str, meta: dict[str, Any],
                 runs: dict[str, list[bytes]], *, link_from: Path | None = None,
                 step: int = 1) -> int:  # fmt: skip
    """One sample directory; returns the bytes it added (a hard link from ``link_from``, frame
    i * ``step`` there, adds none)."""
    d = root / "in" / name
    d.mkdir(mode=0o700, parents=True)
    written = 0
    for run, frames in runs.items():
        (d / run).mkdir(mode=0o700)
        for i, data in enumerate(frames):
            if link_from is not None:
                os.link(link_from / f"{i * step:06d}.png", d / run / f"{i:06d}.png")
                continue
            (d / run / f"{i:06d}.png").write_bytes(data)
            written += len(data)
    for fname, text in (("kind", kind), ("fps", str(fps)), ("size", size),
                        ("map", str(meta.get("map", "")))):  # fmt: skip
        (d / fname).write_text(text + "\n")
    (d / "frames.json").write_text(json.dumps(meta, indent=1) + "\n")
    return written


def motion_clip(session: Path, start_s: float, n: int) -> tuple[list[bytes], dict[str, Any]]:
    """``n`` consecutive frames of an S2 console H.264 session from the first IDR at least
    ``start_s`` after its first, each checked against the live client's checksum, as level-1 PNGs
    (the recorder's own encoder). Reads only that byte range of stream.h264."""
    import av

    from poring_dataset import h264
    from poring_dataset.shards import encode_png

    s = h264.H264Session(session)  # refuses another decoder build (DecoderMismatch)
    if not s._idrs:
        raise SystemExit(f"{session.name}: no IDR")
    t0 = s.units[s._idrs[0]].t_ns + int(start_s * 1e9)
    first = next((i for i in s._idrs if s.units[i].t_ns >= t0), None)
    if first is None or first + n > len(s.units):
        raise SystemExit(f"{session.name}: no {n} units after {start_s} s")
    units = s.units[first : first + n]
    lo, hi = units[0].offset, units[-1].offset + units[-1].length
    with (session / "stream.h264").open("rb") as fh:
        fh.seek(lo)
        data = fh.read(hi - lo)
    ctx = h264.new_decoder()
    pngs: list[bytes] = []
    for u in units:
        out = list(ctx.decode(av.Packet(data[u.offset - lo : u.offset - lo + u.length])))
        if not out:
            raise SystemExit(f"{session.name}: unit {u.au} decoded to nothing")
        _, bgr = s._emit(u, out[0], verify=True, crop=True)
        pngs.append(encode_png(bgr, 1))
    meta = {"session": session.name, "kind": "motion", "first_au": units[0].au,
            "size": f"{s.region[2]}x{s.region[3]}",
            "frame_ids": [u.frame_id for u in units], "source_fps": 30,
            "checksums_verified": True}  # fmt: skip
    return pngs, meta


def cmd_sample(a: argparse.Namespace) -> int:
    root: Path = a.root
    if root.exists():
        print(f"REFUSED: {root} exists (a fresh run needs it gone: rm -rf {root})", file=sys.stderr)
        return 2
    if a.round not in ROUNDS:
        print(f"REFUSED: --round {a.round}: rounds are {sorted(ROUNDS)}", file=sys.stderr)
        return 2
    plan: list[tuple[str, str, Path, list[int], str]] = []
    planned = largest = 0
    for spec in a.session:
        sid, _, map_name = spec.partition(":")
        if not map_name:
            print(f"REFUSED: --session {spec}: expected SID:MAP", file=sys.stderr)
            return 2
        session = a.datasets / sid
        manifest = json.loads((session / "manifest.json").read_text())
        starts = run_starts(int(manifest["frames"]), a.runs, a.run_len)
        est = int(a.runs * a.run_len * manifest["bytes"] / manifest["frames"] * 1.1)
        planned, largest = planned + est, max(largest, est)
        _, _, gw, gh = manifest["game_region"]
        plan.append((map_name, sid, session, starts, f"{gw}x{gh}"))
    if a.motion:
        est = a.motion_len * MOTION_FRAME_BYTES
        planned, largest = planned + est, max(largest, est)
    why = shm_refusal(shm_used(), planned, largest_item=largest)
    if why:
        print(f"REFUSED: {why}", file=sys.stderr)
        return 2
    root.mkdir(mode=0o700)
    (root / "in").mkdir(mode=0o700)
    (root / "out").mkdir(mode=0o700)
    (root / "in" / "arms.tsv").write_text(arms_tsv(round_arms(a.round)))
    # recbench.sh reads the encode timing passes; score reads the round (files, not samples: the
    # container and the scorer list only directories as samples)
    (root / "in" / "round").write_text(f"{a.round}\n")
    (root / "in" / "timing_reps").write_text(f"{TIMING_REPS[a.round]}\n")
    total = 0
    for map_name, sid, session, starts, size in plan:
        wanted = {s + i for s in starts for i in range(a.run_len)}
        got = png_session_frames(session, wanted)
        if len(got) != len(wanted):
            raise SystemExit(f"{sid}: found {len(got)} of {len(wanted)} frames")
        runs: dict[str, list[bytes]] = {}
        meta: dict[str, Any] = {"session": sid, "map": map_name, "kind": "ref", "fps": 1,
                                "runs": []}  # fmt: skip
        for k, s0 in enumerate(starts):
            idx = list(range(s0, s0 + a.run_len))
            runs[f"r{k}"] = [got[i][0] for i in idx]
            meta["runs"].append({
                "name": f"r{k}", "start": s0, "frames": a.run_len,
                "frame_ids": [got[i][1].get("frame_id") for i in idx],
                "t_mono_ns": [got[i][1].get("t_mono_ns") for i in idx],
                "png_bytes": [len(got[i][0]) for i in idx],
            })  # fmt: skip
        total += write_sample(root, map_name, "ref", 1, size, meta, runs)
        print(json.dumps({"sample": map_name, "session": sid, "starts": starts,
                          "frames": len(wanted)}), flush=True)  # fmt: skip
    if a.motion:
        pngs, meta = motion_clip(a.datasets / a.motion, a.motion_start_s, a.motion_len)
        meta["map"] = a.motion_map
        for fps in (30, 10, 5):
            step = 30 // fps
            m = dict(
                meta,
                fps=fps,
                runs=[
                    {
                        "name": "r0",
                        "frames": len(pngs[::step]),
                        "png_bytes": [len(p) for p in pngs[::step]],
                    }
                ],
            )
            # 10 and 5 fps are every 3rd / 6th frame of the 30-fps clip: hard links, no new RAM
            link = None if fps == 30 else root / "in" / "motion30" / "r0"
            total += write_sample(root, f"motion{fps}", "motion", fps, meta["size"], m,
                                  {"r0": pngs[::step]}, link_from=link, step=step)  # fmt: skip
        print(json.dumps({"sample": "motion30/10/5", "session": a.motion,
                          "frames": len(pngs)}), flush=True)  # fmt: skip
    print(json.dumps({"root": str(root), "bytes_written": total,
                      "shm_used_now": shm_used()}), flush=True)  # fmt: skip
    return 0


# --- score (host) --------------------------------------------------------------------------------


def decode_png_bgr(data: bytes) -> npt.NDArray[np.uint8]:
    from PIL import Image

    return np.ascontiguousarray(np.asarray(Image.open(io.BytesIO(data)).convert("RGB"))[..., ::-1])


def frame_planes(frame: Any) -> list[npt.NDArray[np.uint8]]:
    """A PyAV frame's planes, each cropped to its width (line padding dropped)."""
    out = []
    for p in frame.planes:
        arr = np.frombuffer(memoryview(p), np.uint8).reshape(p.height, p.line_size)
        out.append(arr[:, : p.width])
    return out


def to_bgr(frame: Any, color: tuple[str, str] = COLOR) -> npt.NDArray[np.uint8]:
    """YUV -> BGR with the given convention (default the bench's: BT.709, full range; an arm's
    DECLARED one is arm_color), swscale via PyAV."""
    out = frame.reformat(format="bgr24", src_colorspace=color[0], src_color_range=color[1])
    return np.ascontiguousarray(out.to_ndarray())


def decode_stream(path: Path, ext: str, plane_fmt: str, *, alone: bool,
                  color: tuple[str, str] = COLOR) -> dict[str, Any]:  # fmt: skip
    """Decode one elementary stream on the host (PyAV software, one thread): BGR frames (inverted
    with ``color``), the planar md5s, packet sizes, key flags, CPU time, the first frame's
    signalled range / matrix (``vui``); with ``alone``, each packet also through a fresh decoder
    (D1: does every frame decode by itself, to the same planes?)."""
    import av

    name = DECODERS[ext]
    packets = []
    with av.open(str(path), format=DEMUXERS[ext]) as cont:
        for pkt in cont.demux(cont.streams.video[0]):
            if pkt.size:
                packets.append((bytes(pkt), bool(pkt.is_keyframe)))
    ctx = av.CodecContext.create(name, "r")
    ctx.thread_count = 1
    frames: list[Any] = []
    undecodable = 0
    t0 = time.process_time()
    for data, _ in packets:
        try:
            frames += ctx.decode(av.Packet(data))
        except av.error.FFmpegError:
            undecodable += 1  # reported; the frame count then no longer matches the run
    frames += ctx.decode(None)
    dec_s = time.process_time() - t0
    t0 = time.process_time()
    bgr = [to_bgr(f, color) for f in frames]
    bgr_s = time.process_time() - t0
    md5s = [md5_hex(planar_bytes(frame_planes(f if f.format.name == plane_fmt
                                              else f.reformat(format=plane_fmt))))
            for f in frames]  # fmt: skip
    alone_ok = None
    if alone:
        alone_ok = 0
        for (data, _), want in zip(packets, md5s, strict=False):
            c = av.CodecContext.create(name, "r")
            try:
                got = list(c.decode(av.Packet(data))) + list(c.decode(None))
            except av.error.FFmpegError:
                continue
            if len(got) == 1:
                g = got[0] if got[0].format.name == plane_fmt else got[0].reformat(format=plane_fmt)
                alone_ok += md5_hex(planar_bytes(frame_planes(g))) == want
    n = max(1, len(frames))
    keys = [len(d) for d, k in packets if k]
    inter = [len(d) for d, k in packets if not k]
    return {
        "bgr": bgr, "md5": md5s, "packets": len(packets),
        "bytes": sum(len(d) for d, _ in packets),
        "key_bytes_mean": statistics.fmean(keys) if keys else None,
        "inter_bytes_mean": statistics.fmean(inter) if inter else None,
        "keyframes": len(keys), "alone_identical": alone_ok, "undecodable": undecodable,
        "host_sw_ms": round(dec_s * 1000 / n, 3), "host_bgr_ms": round(bgr_s * 1000 / n, 3),
        "vui": vui_of(frames[0]) if frames else None,
    }  # fmt: skip


def read_raw_yuv(path: Path, fmt: str, w: int, h: int) -> list[npt.NDArray[np.uint8]]:
    """A raw planar yuv444p / yuv420p file (the ctl arms) -> BGR frames, our colour convention."""
    from av.video.frame import VideoFrame

    per = w * h * 3 if fmt == "yuv444p" else w * h * 3 // 2
    data = path.read_bytes()
    out = []
    for i in range(len(data) // per):
        buf = np.frombuffer(data, np.uint8, per, i * per)
        arr = buf.reshape(3, h, w) if fmt == "yuv444p" else buf.reshape(h * 3 // 2, w)
        out.append(to_bgr(VideoFrame.from_ndarray(arr, format=fmt)))
    return out


def jpeg95(bgr: npt.NDArray[np.uint8]) -> bytes:
    from build_frame_cache import jpeg  # the training cache's own encoder

    return jpeg(bgr, 95)


def score_sample(root: Path, name: str, status: dict[tuple[str, str, str], dict[str, str]],
                 det: Any, arms: Sequence[Arm] | None = None) -> dict[str, Any]:  # fmt: skip
    """One sample: the PNG reference, the JPEG q95 reference, then every arm of ``arms`` (round
    1's by default) that names this sample's kind."""
    from gpu_live_parity import rows

    from poring_dataset.shards import decode_png, encode_png

    d = root / "in" / name
    meta = json.loads((d / "frames.json").read_text())
    kind = meta["kind"]
    w, h = (int(v) for v in (d / "size").read_text().split("x"))
    runs = [r["name"] for r in meta["runs"]]
    out: dict[str, Any] = {"kind": kind, "map": meta.get("map"), "session": meta.get("session"),
                           "fps": int((d / "fps").read_text()), "arms": {}}  # fmt: skip
    png_bytes = [b for r in meta["runs"] for b in r["png_bytes"]]
    out["png"] = {"bytes_per_frame": round(statistics.fmean(png_bytes), 1),
                  "frames": len(png_bytes)}  # fmt: skip
    ref: dict[str, list[npt.NDArray[np.uint8]]] = {}
    ref_boxes: dict[str, list[list[list[Any]]]] = {}
    if kind == "ref":
        t_pil = t_repo = t_enc = 0.0
        for r in runs:
            ref[r] = []
            for p in sorted((d / r).glob("*.png")):
                data = p.read_bytes()
                t0 = time.process_time()
                img = decode_png_bgr(data)
                t1 = time.process_time()
                decode_png(data)
                t2 = time.process_time()
                encode_png(img, 1)
                t3 = time.process_time()
                t_pil, t_repo, t_enc = t_pil + t1 - t0, t_repo + t2 - t1, t_enc + t3 - t2
                ref[r].append(img)
        n = sum(len(v) for v in ref.values())
        out["png"].update({"pil_decode_ms": round(t_pil * 1000 / n, 2),
                           "repo_decode_ms": round(t_repo * 1000 / n, 2),
                           "encode_png_ms": round(t_enc * 1000 / n, 2)})  # fmt: skip
        if det is not None:
            ref_boxes = {r: [rows(det.detect(img)) for img in ref[r]] for r in runs}
        # the training cache's JPEG q95: the accepted lossy reference
        per: list[dict[str, Any]] = []
        jboxes: list[tuple[Any, Any]] = []
        jb = 0
        for r in runs:
            for i, img in enumerate(ref[r]):
                data = jpeg95(img)
                jb += len(data)
                dec = decode_png_bgr(data)
                per.append(frame_metrics(img, dec))
                if det is not None:
                    jboxes.append((ref_boxes[r][i], rows(det.detect(dec))))
        out["arms"][JPEG_ARM] = {
            "status": "ok",
            "frames": n,
            "bytes_per_frame": round(jb / n, 1),
            "quality": summarise(per),
            "parity": parity_stats(jboxes) if det is not None else None,
        }
    for arm in round_arms(1) if arms is None else arms:
        if arm.samples != "all" and arm.samples != kind:
            continue
        st = [status.get((arm.name, name, r)) for r in runs]
        if any(s is None or s["status"] != "ok" for s in st):
            bad = next((s for s in st if s is None or s["status"] != "ok"), None)
            out["arms"][arm.name] = {"status": (bad or {}).get("status", "not run"),
                                     "note": (bad or {}).get("note", "")}  # fmt: skip
            continue
        if arm.mode == "gctl":  # the raw format that ran (the first of "a|b" that worked)
            fmts = {r: (s or {}).get("note") or arm.sw_fmt.split("|")[0]
                    for r, s in zip(runs, st, strict=True)}  # fmt: skip
            out["arms"][arm.name] = score_gctl(root, name, arm, runs, ref, w, h, fmts)
            continue
        out["arms"][arm.name] = score_arm(root, name, arm, runs, ref, ref_boxes, w, h, det, kind)
    return out


def score_gctl(root: Path, name: str, arm: Arm, runs: list[str],
               ref: dict[str, list[npt.NDArray[np.uint8]]], w: int, h: int,
               fmts: dict[str, str]) -> dict[str, Any]:  # fmt: skip
    """A GPU colour control (round 2): its downloaded raw planes inverted with the arm's DECLARED
    convention against the PNG (the GPU's round trip, read like V1), the luma fingerprint of what
    the GPU actually wrote, and -- when it declares the bench's own convention -- its planes
    against swscale's for the same frames (ctl-yuv420 / ctl-yuv444, the same 10 frames a run)."""
    from av.video.frame import VideoFrame

    enc = root / "out" / "enc" / name
    color = arm_color(arm)
    twin = "ctl-yuv420" if arm.plane_fmt == "yuv420p" else "ctl-yuv444"
    per, refs, ys, diffs = [], [], [], []
    for r in runs:
        fmt = fmts[r]
        if fmt not in RAW_FORMATS:
            return {"status": "invalid", "mode": arm.mode, "note": f"{r}: raw format {fmt!r}"}
        planes = raw_planes((enc / arm.name / f"{r}.{arm.ext}").read_bytes(), fmt, w, h)
        want = min(arm.frames or len(ref[r]), len(ref[r]))
        if len(planes) != want:
            return {"status": "invalid", "mode": arm.mode,
                    "note": f"{r}: {len(planes)} frames, not {want}"}  # fmt: skip
        sw = enc / twin / f"{r}.yuv"
        sw_planes = (raw_planes(sw.read_bytes(), arm.plane_fmt, w, h)
                     if color == COLOR and sw.exists() else [])  # fmt: skip
        for i, p in enumerate(planes):
            dec = to_bgr(VideoFrame.from_ndarray(planar_array(p), format=arm.plane_fmt), color)
            per.append(frame_metrics(ref[r][i], dec))
            refs.append(ref[r][i])
            ys.append(p[0])
            if i < len(sw_planes):
                diffs.append(plane_diff(p, sw_planes[i]))
    res: dict[str, Any] = {"status": "ok", "mode": arm.mode, "formats": sorted(set(fmts.values())),
                           "declared": f"bt709-{'full' if color[1] == 'JPEG' else 'limited'}",
                           "quality": summarise(per), "fit": luma_fit(refs, ys)}  # fmt: skip
    if diffs:
        res["vs_swscale"] = {"twin": twin, "frames": len(diffs), **{
            k: {"mean": round(statistics.fmean(d[k]["mean"] for d in diffs), 3),
                "mean_abs": round(statistics.fmean(d[k]["mean_abs"] for d in diffs), 3),
                "max_abs": max(d[k]["max_abs"] for d in diffs)} for k in "YUV"}}  # fmt: skip
    return res


def score_arm(root: Path, name: str, arm: Arm, runs: list[str],
              ref: dict[str, list[npt.NDArray[np.uint8]]], ref_boxes: dict[str, Any], w: int,
              h: int, det: Any, kind: str) -> dict[str, Any]:  # fmt: skip
    from gpu_live_parity import rows

    enc = root / "out" / "enc" / name / arm.name
    res: dict[str, Any] = {"status": "ok", "mode": arm.mode}
    if arm.mode == "ctl":
        per, refs, ys = [], [], []
        for r in runs:
            path = enc / f"{r}.{arm.ext}"
            frames = read_raw_yuv(path, arm.sw_fmt, w, h)
            per += [frame_metrics(ref[r][i], f) for i, f in enumerate(frames)]
            refs += ref[r][: len(frames)]
            ys += [p[0] for p in raw_planes(path.read_bytes(), arm.sw_fmt, w, h)]
        res["quality"] = summarise(per)  # round 1's numbers, unchanged
        res["declared"] = "bt709-full"
        res["fit"] = luma_fit(refs, ys)  # the fingerprint's known-good case (doc 6.6)
        return res
    total = frames = keys = 0
    key_b: list[float] = []
    inter_b: list[float] = []
    per = []
    pairs: list[tuple[Any, Any]] = []
    d1 = {"frames": 0, "alone_identical": 0}
    d2 = {"compared": 0, "va_eq_sw": 0, "host_eq_sw": 0}
    host_ms: list[float] = []
    bgr_ms: list[float] = []
    vuis: list[dict[str, str] | None] = []
    for r in runs:
        got = decode_stream(enc / f"{r}.{arm.ext}", arm.ext, arm.plane_fmt,
                            alone=arm.mode in CANDIDATE_MODES, color=arm_color(arm))  # fmt: skip
        vuis.append(got["vui"])
        total, frames, keys = (
            total + got["bytes"],
            frames + len(got["bgr"]),
            keys + got["keyframes"],
        )
        if got["key_bytes_mean"] is not None:
            key_b.append(got["key_bytes_mean"])
        if got["inter_bytes_mean"] is not None:
            inter_b.append(got["inter_bytes_mean"])
        host_ms.append(got["host_sw_ms"])
        bgr_ms.append(got["host_bgr_ms"])
        if got["alone_identical"] is not None:
            d1["frames"] += len(got["md5"])
            d1["alone_identical"] += got["alone_identical"]
        md5 = root / "out" / "md5" / name / arm.name
        va = (md5 / f"{r}.va.md5").read_text() if (md5 / f"{r}.va.md5").exists() else ""
        sw = (md5 / f"{r}.sw.md5").read_text() if (md5 / f"{r}.sw.md5").exists() else ""
        va_l, sw_l = parse_framemd5(va), parse_framemd5(sw)
        if sw_l and len(sw_l) == len(got["md5"]):
            d2["compared"] += len(sw_l)
            d2["host_eq_sw"] += sum(x == y for x, y in zip(got["md5"], sw_l, strict=True))
            d2["va_eq_sw"] += sum(x == y for x, y in zip(va_l, sw_l, strict=False))
        if kind != "ref":
            continue
        want = len(ref[r]) if arm.frames == 0 else min(arm.frames, len(ref[r]))
        if len(got["bgr"]) != want:
            return {"status": "invalid", "note": f"{r}: {len(got['bgr'])} frames, not {want}"}
        for i, dec in enumerate(got["bgr"]):
            m = frame_metrics(ref[r][i], dec)
            m["gen2"] = psnr(ref[r][i], decode_png_bgr(jpeg95(dec)))
            per.append(m)
            if det is not None and arm.mode != "x":
                pairs.append((ref_boxes[r][i], rows(det.detect(dec))))
    res.update({
        "frames": frames, "bytes_per_frame": round(total / max(1, frames), 1),
        "keyframes": keys,
        "key_bytes_per_frame": round(statistics.fmean(key_b), 1) if key_b else None,
        "inter_bytes_per_frame": round(statistics.fmean(inter_b), 1) if inter_b else None,
        "decode": {"host_sw_ms": round(statistics.fmean(host_ms), 3),
                   "host_bgr_ms": round(statistics.fmean(bgr_ms), 3)},
        "d1": d1 if arm.mode in CANDIDATE_MODES else None, "d2": d2,
    })  # fmt: skip
    # what the stream SAYS it is, against what the arm declares (reported, not a bar: doc 6.6)
    want = {"range": arm.color_range, "matrix": "bt709"}
    res["vui"] = sorted({json.dumps(v, sort_keys=True) for v in vuis if v})
    res["vui_ok"] = bool(vuis) and all(v == want for v in vuis)
    if kind == "ref":
        res["quality"] = summarise(per)
        res["parity"] = parity_stats(pairs) if pairs else None
    return res


def rates(score: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """GB per hour at 1 / 5 / 10 / 30 fps: the PNG and every intra arm from the ref samples (their
    bytes per frame do not depend on the rate; the worst ref sample), the GOP arms at 1 fps from
    the ref samples and at 5 / 10 / 30 from the motion clips (an estimate: a lossy source)."""
    refs = [v for v in score["samples"].values() if v.get("kind") == "ref"]
    motion = {v["fps"]: v for v in score["samples"].values() if v.get("kind") == "motion"}
    out: dict[str, dict[str, Any]] = {}
    if refs:
        png = max(v["png"]["bytes_per_frame"] for v in refs)
        out["png"] = {str(f): gb_per_hour(png, f) for f in FPS_LADDER}
    for a in round_arms(int(score.get("round", 1))):
        if a.mode not in GRADED_MODES:
            continue
        sizes = [v["arms"][a.name]["bytes_per_frame"] for v in refs
                 if (v["arms"].get(a.name) or {}).get("status") == "ok"]  # fmt: skip
        if not sizes:
            continue
        row: dict[str, Any] = {}
        for f in FPS_LADDER:
            src = max(sizes)
            if a.mode == "gop" and f != 1:
                arm = (motion.get(f) or {}).get("arms", {}).get(a.name) or {}
                src = arm.get("bytes_per_frame") if arm.get("status") == "ok" else None
            row[str(f)] = gb_per_hour(src, f) if src is not None else None
        out[a.name] = row
    return out


def cmd_score(a: argparse.Namespace) -> int:
    root: Path = a.root
    out_dir = root / "out"
    status = {(r["arm"], r["sample"], r["run"]): r for r in parse_tsv(
        (out_dir / "status.tsv").read_text(), STATUS_FIELDS)}  # fmt: skip
    timing = merge_timing(parse_tsv((out_dir / "timing.tsv").read_text(), TIMING_FIELDS))
    round_file = root / "in" / "round"  # written by sample; absent in a round-1 root
    rnd = int(round_file.read_text()) if round_file.exists() else 1
    arms = round_arms(rnd)
    det_maps: dict[str, Any] = {}
    score: dict[str, Any] = {"started": time.strftime("%FT%T%z"), "root": str(root),
                             "round": rnd, "arms": [x.name for x in arms], "bars": BARS,
                             "samples": {}, "timing": timing}  # fmt: skip
    vainfo = out_dir / "vainfo.txt"
    if vainfo.exists():
        score["vainfo"] = [
            ln.strip() for ln in vainfo.read_text().splitlines() if "VAProfile" in ln
        ]
    from poring_dataset.h264 import decoder_versions

    score["host_decoder"] = decoder_versions()
    try:
        for name in sorted(p.name for p in (root / "in").iterdir() if p.is_dir()):
            meta = json.loads((root / "in" / name / "frames.json").read_text())
            det = None
            if not a.no_detector and meta["kind"] == "ref":
                import unit_detector as ud

                det = det_maps.get(meta["map"]) or ud.for_map(meta["map"], threads=a.det_threads)
                det_maps[meta["map"]] = det
                score.setdefault("detectors", {})[meta["map"]] = det.model.name
            score["samples"][name] = score_sample(root, name, status, det, arms)
            print(json.dumps({"scored": name}), flush=True)
    finally:
        for det in det_maps.values():
            det.close()
    score["rates"] = rates(score)
    score["controls"] = controls_summary(score)
    score["verdict"] = verdict(score)
    score["ended"] = time.strftime("%FT%T%z")
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(score, indent=1) + "\n")
    print_verdict(score)
    return 0


def print_verdict(score: dict[str, Any]) -> None:
    v = score["verdict"]
    print(json.dumps({"valid": v["valid"], "V1": v["V1"], "candidate": v["candidate"]}))
    for name, arm in v.get("arms", {}).items():
        fails = sorted({f"{s}:{b}" for s, bars in arm["samples"].items()
                        for b, r in bars.items() if isinstance(r, dict)
                        and r.get("result") == "FAIL"})  # fmt: skip
        print(f"{name:18s} {'PASS' if arm['pass'] else 'no  '} {' '.join(fails)}")
    for s, arms in controls_summary(score).items():  # the colour controls (never graded)
        for name, c in arms.items():
            print(json.dumps({"control": name, "sample": s, **c}))
    for s, smp in score["samples"].items():  # what each graded stream says it is
        for name, arm in smp["arms"].items():
            if "vui_ok" in arm and not arm["vui_ok"]:
                print(json.dumps({"vui_mismatch": name, "sample": s, "vui": arm["vui"]}))
    print(json.dumps({"rates_gb_per_hour": score.get("rates")}))


def cmd_verdict(a: argparse.Namespace) -> int:
    score = json.loads(a.score.read_text())
    score["verdict"] = verdict(score)
    print_verdict(score)
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)  # fmt: skip
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("sample")
    s.add_argument("--session", action="append", required=True, help="SID:MAP (a PNG session)")
    s.add_argument("--runs", type=int, default=2)
    s.add_argument("--run-len", type=int, default=50)
    s.add_argument("--motion", default=None, help="an S2 console H.264 session id (size only)")
    s.add_argument("--motion-map", default="prt_fild08")
    s.add_argument("--motion-len", type=int, default=150)
    s.add_argument("--motion-start-s", type=float, default=300.0)
    s.add_argument("--root", type=Path, default=ROOT_DEFAULT)
    s.add_argument("--datasets", type=Path, default=DATASETS)
    s.add_argument("--round", type=int, default=1,
                   help="which arms (ROUNDS): 1 = the original table, 2 = doc 6.6")  # fmt: skip
    c = sub.add_parser("score")
    c.add_argument("--root", type=Path, default=ROOT_DEFAULT)
    c.add_argument("--out", type=Path, required=True)
    c.add_argument("--det-threads", type=int, default=8)
    c.add_argument("--no-detector", action="store_true")
    v = sub.add_parser("verdict")
    v.add_argument("score", type=Path)
    a = ap.parse_args(argv)
    if a.cmd == "sample":
        return cmd_sample(a)
    if a.cmd == "score":
        return cmd_score(a)
    return cmd_verdict(a)


if __name__ == "__main__":
    raise SystemExit(main())
