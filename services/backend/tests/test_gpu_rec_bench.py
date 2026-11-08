"""scripts/gpu_rec_bench.py: the GPU recording bench's pure helpers, its verdict, and the host
decode path (docs/planning/gpu-recording.md, PRE-REGISTERED 2026-11-08). No GPU, no NAS: the
decode tests use a tiny libx264 (CPU) stream made here."""

import hashlib
import importlib.util
import re
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[3]
SCRIPTS = ROOT / "scripts"


@pytest.fixture(scope="module")
def gb() -> ModuleType:
    sys.path.insert(0, str(SCRIPTS))
    spec = importlib.util.spec_from_file_location("gpu_rec_bench", SCRIPTS / "gpu_rec_bench.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["gpu_rec_bench"] = module  # its dataclasses resolve their module by name
    spec.loader.exec_module(module)
    return module


# --- the sample plan ------------------------------------------------------------------------------


def test_run_starts_centres_each_run_and_refuses_what_does_not_fit(gb: ModuleType) -> None:
    assert gb.run_starts(1320, 2, 50) == [305, 965]  # 20261105T225409-rdp-xmas02-x2
    assert gb.run_starts(560, 2, 50) == [115, 395]  # 20261026T120547-rdp-rogue-c1
    assert gb.run_starts(100, 2, 50) == [0, 50]  # exactly full: clamped, no overlap
    assert gb.run_starts(10, 1, 4) == [3]
    with pytest.raises(ValueError):
        gb.run_starts(99, 2, 50)
    with pytest.raises(ValueError):
        gb.run_starts(100, 0, 50)


def test_the_ram_budget_follows_rule_7(gb: ModuleType) -> None:
    assert gb.shm_refusal(400_000_000, 800_000_000, largest_item=500_000_000) is None
    assert "item cap" in gb.shm_refusal(0, 10**9, largest_item=1_100_000_000)
    why = gb.shm_refusal(2_500_000_000, 800_000_000, largest_item=500_000_000)
    assert why is not None and "4.0 GB" in why  # 2.5 + 0.8 + the 1.2 GB out cap > 4


@pytest.mark.parametrize("rnd", [1, 2])
def test_the_arm_table_is_what_recbench_sh_reads(gb: ModuleType, rnd: int) -> None:
    arms = gb.round_arms(rnd)
    text = gb.arms_tsv(arms)
    lines = text.splitlines()
    fields = list(gb.Arm.__dataclass_fields__)
    assert lines[0] == "#" + "\t".join(fields) and fields[-1] == "args"  # args last: `read` rest
    names = [ln.split("\t")[0] for ln in lines[1:]]
    assert len(names) == len(set(names)) == len(arms)
    for ln, arm in zip(lines[1:], arms, strict=True):
        parts = ln.split("\t")
        assert len(parts) == len(fields), ln
        # recbench.sh reads with IFS=tab, which merges EMPTY fields: only the last may be empty
        assert all(parts[:-1]), ln
        assert "\t" not in arm.args and "\n" not in arm.args
        assert arm.mode in ("ctl", "gctl", "intra", "vpp", "gop", "x")
        assert arm.samples in ("ref", "motion", "all")
        assert arm.color_range in ("pc", "tv") and gb.arm_color(arm)[0] == gb.COLOR[0]
        assert (arm.vpp != "-") == (arm.mode in ("vpp", "gctl")), arm.name
        if arm.mode in ("vpp", "gctl"):  # scale_vaapi's options, the range the arm declares
            want = "out_range=full" if arm.color_range == "pc" else "out_range=limited"
            assert want in arm.vpp.split(":") and "out_color_matrix=bt709" in arm.vpp.split(":")
        if arm.mode == "gctl":
            assert arm.codec == arm.mux == "rawvideo" and arm.frames == 10 and not arm.timing
            assert arm.va_profile == "-" and arm.plane_fmt in ("yuv420p", "yuv444p")
        if arm.mode not in gb.CONTROL_MODES:
            assert arm.va_profile.startswith("VAProfile") and arm.ext in gb.DECODERS
            assert "-low_power" not in arm.args  # recbench.sh adds it (VDEnc only, section 18)
        if arm.mode in ("intra", "vpp", "x"):
            assert "-g 1 -bf 0" in arm.args
        if arm.mode == "gop":
            assert "-g 30 -bf 0" in arm.args
        if arm.codec in ("hevc_vaapi", "h264_vaapi"):
            assert re.search(r"-rc_mode CQP -qp \d+", arm.args) and "-aud 1" in arm.args
        if arm.codec == "av1_vaapi":  # no private qp option: the base q index
            assert re.search(r"-rc_mode CQP -global_quality \d+", arm.args)
    assert any(a.mode == "vpp" for a in arms) and gb.JPEG_ARM not in names
    assert "ctl-yuv444" in names  # V1 runs in every round


def test_round_1_is_the_original_table_unchanged(gb: ModuleType) -> None:
    """Round 1's results (section 8) stay reproducible: its arms, their order, and every field
    that reaches the container or the scorer are what ran on 2026-11-08 17:15."""
    assert gb.ROUNDS[1] == (
        "ctl-yuv444", "ctl-yuv420", "hevc420-q14", "hevc420-q20", "hevc420-q26", "hevc444-q14",
        "hevc444-q20", "hevc444-q26", "h264-420-q20", "av1-420-g40", "av1-420-g80",
        "vpp-hevc420-q20", "hevc420-q20-g30", "hevc444-q20-g30", "h264-420-q20-g30",
        "x-hevc444-q1", "x-av1-g1")  # fmt: skip
    assert gb.arms_tsv() == gb.arms_tsv(gb.round_arms(1))  # the default is round 1's table
    for arm in gb.round_arms(1):
        assert arm.color_range == "pc" and gb.arm_color(arm) == gb.COLOR  # the same inverse
        assert arm.vpp == ("out_color_matrix=bt709:out_range=full"
                           if arm.name == "vpp-hevc420-q20" else "-")  # fmt: skip
    assert gb.TIMING_REPS[1] == 1  # one timing pass, as in round 1
    every = {n for names in gb.ROUNDS.values() for n in names}
    assert every == {a.name for a in gb.ARMS}  # no arm outside a round
    # round 2 stands on its own: V1, the swscale twins, and round 1's closest arm unchanged
    assert {"ctl-yuv444", "ctl-yuv420", "hevc444-q20"} <= set(gb.ROUNDS[2])
    assert gb.TIMING_REPS[2] == 3
    r1, r2 = gb.arm_by_name("hevc444-q20"), gb.arm_by_name("vpp-hevc444-q20")
    assert (r2.codec, r2.args, r2.va_profile, r2.sw_fmt) == (r1.codec, r1.args, r1.va_profile,
                                                            r1.sw_fmt)  # fmt: skip
    assert gb.arm_by_name("gctl-vpp420-r1").vpp == gb.arm_by_name("vpp-hevc420-q20").vpp


def test_the_doc_preregisters_every_bar_with_its_value(gb: ModuleType) -> None:
    doc = (ROOT / "docs" / "planning" / "gpu-recording.md").read_text()
    for key, value in gb.BARS.items():
        rows = [ln for ln in doc.splitlines() if f"`{key}`" in ln]
        assert rows, f"{key} is not in the doc's bar table"
        assert any(f"| {value} |" in ln or f"| {value:g} |" in ln for ln in rows), (key, value)
    for arm in gb.ARMS:
        assert f"`{arm.name}`" in doc, f"the arm {arm.name} is not in the doc"


# --- the metrics ---------------------------------------------------------------------------------


def test_psnr_is_capped_for_identical_and_exact_for_a_known_error(gb: ModuleType) -> None:
    a = np.zeros((8, 8, 3), np.uint8)
    assert gb.psnr(a, a) == 100.0
    assert gb.psnr(a, a + 1) == pytest.approx(10 * np.log10(255.0**2), abs=1e-9)  # MSE 1
    with pytest.raises(ValueError):
        gb.psnr(a, np.zeros((8, 9, 3), np.uint8))


def test_ssim_is_one_for_identical_and_drops_with_noise(gb: ModuleType) -> None:
    rng = np.random.default_rng(1)
    img = rng.integers(0, 256, (40, 48, 3), dtype=np.uint8)
    assert gb.ssim_luma(img, img) == pytest.approx(1.0)
    noisy = np.clip(img.astype(int) + rng.integers(-40, 41, img.shape), 0, 255).astype(np.uint8)
    low = gb.ssim_luma(img, noisy)
    assert low < 0.97 and low == pytest.approx(gb.ssim_luma(noisy, img))  # symmetric


def test_the_saturated_colour_keep_rate_sees_a_dulled_red_line(gb: ModuleType) -> None:
    ref = np.full((4, 6, 3), 60, np.uint8)
    ref[1, :] = (0, 0, 255)  # a 1-px pure red line (BGR): the no-entry ring's colour
    assert gb.sat_counts(ref, ref) == (6, 6)
    dull = ref.copy()
    dull[1, :3] = (40, 40, 200)  # what a chroma smear does: G and B rise above the keep limit
    assert gb.sat_counts(ref, dull) == (6, 3)
    assert gb.sat_counts(np.full((2, 2, 3), 128, np.uint8), np.zeros((2, 2, 3), np.uint8)) == (0, 0)


def test_frame_metrics_and_summary_cover_every_crop(gb: ModuleType) -> None:
    ref = np.zeros((720, 1280, 3), np.uint8)
    dec = ref.copy()
    dec[0:10, 0:10] = 8  # inside basic_info only
    m = gb.frame_metrics(ref, dec)
    assert m["maxabs"] == 8 and m["crops"]["chat"] == 100.0 and m["crops"]["basic_info"] < 100.0
    m["gen2"] = 40.0
    s = gb.summarise([m, gb.frame_metrics(ref, ref) | {"gen2": 42.0}])
    assert s["frames"] == 2 and s["psnr_min"] == pytest.approx(m["psnr"], abs=1e-3)
    assert set(s["crops"]) == set(gb.CROPS) and s["gen2_psnr_mean"] == 41.0
    assert s["sat_keep"] is None  # no saturated pixel at all


def test_framemd5_parsing_and_the_planar_layout(gb: ModuleType) -> None:
    y = np.arange(12, dtype=np.uint8).reshape(3, 4)
    u = np.full((2, 2), 7, np.uint8)
    padded = np.zeros((2, 4), np.uint8)
    padded[:, :2] = 9
    data = gb.planar_bytes([y, u, padded[:, :2]])
    assert data == y.tobytes() + u.tobytes() + bytes([9] * 4)
    want = hashlib.md5(data).hexdigest()
    text = ("#format: frame checksums\n#version: 2\n#hash: MD5\n#tb 0: 1/25\n"
            "#stream#, dts,        pts, duration,     size, hash\n"
            f"0,          0,          0,        1,       20, {want}\n"
            "0,          1,          1,        1,       20, 00ff\n")  # fmt: skip
    assert gb.parse_framemd5(text) == [want, "00ff"]
    assert gb.md5_hex(data) == want


def test_tsv_rows_and_timing(gb: ModuleType) -> None:
    rows = gb.parse_tsv("# c\nhevc\tx2\tr0\tok\t123\tnv12\nshort\tx2\n", gb.STATUS_FIELDS)
    assert rows[0] == {"arm": "hevc", "sample": "x2", "run": "r0", "status": "ok", "bytes": "123",
                       "note": "nv12"}  # fmt: skip
    assert rows[1]["status"] == "" and len(rows) == 2
    long = gb.parse_tsv("a\tb\tc\td\te\tf\tg\th", gb.STATUS_FIELDS)[0]
    assert long["note"] == "f\tg\th"
    ok = gb.timing_row({"name": "enc_x", "frames": "600", "rtime": "1.5", "utime": "1.2",
                        "stime": "0.6", "status": "ok", "note": ""})  # fmt: skip
    assert ok["cpu_ms_per_frame"] == 3.0 and ok["fps"] == 400.0
    bad = gb.timing_row({"name": "enc_y", "frames": "0", "rtime": "0", "utime": "0", "stime": "0",
                         "status": "failed", "note": "rc=1"})  # fmt: skip
    assert bad["cpu_ms_per_frame"] is None and bad["fps"] is None
    assert gb.timing_row({"name": "z", "frames": "x"})["status"] == "failed"


# round 1's real timing.tsv rows (the NAS scratch-archive 2026-11-08/recbench): one encode pass,
# and a decode whose loop pass failed before its no-loop fallback
R1_TIMING = (
    "enc_hevc444-q20\t600\t3.731\t11.818\t1.297\tok\thevc_vaapi ... rc=0\n"
    "dec_va_hevc444-q20\t50\t0\t0\t0\tfailed\tVA-API decode (loop x12) rc=1\n"
    "dec_va_hevc444-q20\t50\t0.305\t0.257\t0.161\tok\tVA-API decode (no loop) rc=0\n"
    "enc_vpp-hevc420-q20\t600\t2.435\t3.658\t1.757\tok\thevc_vaapi ... rc=0\n"
    "enc_x\t0\t0\t0\t0\tfailed\trc=1\n"
)


def test_merge_timing_keeps_round_1_and_takes_the_median_of_passes(gb: ModuleType) -> None:
    rows = gb.parse_tsv(R1_TIMING, gb.TIMING_FIELDS)
    old = {r["name"]: gb.timing_row(r) for r in rows}  # round 1's scorer: the last row wins
    assert gb.merge_timing(rows) == old  # so round 1's S2 / S3 inputs are unchanged
    assert old["enc_hevc444-q20"]["cpu_ms_per_frame"] == 21.858  # section 8's 21.9 ms
    assert old["enc_vpp-hevc420-q20"]["cpu_ms_per_frame"] == 9.025
    three = gb.parse_tsv(
        "enc_a\t600\t3.0\t5.0\t1.0\tok\tp1\n"  # 10.0 ms: a first-pass warm-up
        "enc_a\t600\t2.0\t4.2\t1.2\tok\tp2\n"  # 9.0 ms
        "enc_a\t600\t2.5\t4.5\t0.9\tok\tp3\n",  # 9.0 ms
        gb.TIMING_FIELDS,
    )
    m = gb.merge_timing(three)["enc_a"]
    assert m["cpu_ms_per_frame"] == 9.0 and m["passes"] == 3
    assert m["cpu_ms_passes"] == [10.0, 9.0, 9.0] and m["fps"] == 240.0  # median of 200 / 300 / 240
    one_bad = gb.merge_timing(three[:2] + gb.parse_tsv("enc_a\t0\t0\t0\t0\tfailed\trc=1\n",
                                                           gb.TIMING_FIELDS))["enc_a"]  # fmt: skip
    assert one_bad["passes"] == 2 and one_bad["cpu_ms_per_frame"] == 9.5  # failed passes drop out


def _yuv(img: np.ndarray, fmt: str, color: tuple[str, str]) -> Any:
    from av.video.frame import VideoFrame

    return VideoFrame.from_ndarray(img, format="bgr24").reformat(
        format=fmt, dst_colorspace=color[0], dst_color_range=color[1])  # fmt: skip


def _packed_bytes(frame: Any, bpp: tuple[int, ...]) -> bytes:
    """A frame's raw bytes, plane by plane. frame_planes crops each plane to its width in PIXELS
    (right for planar formats only): an interleaved or packed plane holds ``bpp`` bytes a pixel."""
    out = b""
    for pl, n in zip(frame.planes, bpp, strict=True):
        arr = np.frombuffer(memoryview(pl), np.uint8).reshape(pl.height, pl.line_size)
        out += np.ascontiguousarray(arr[:, : pl.width * n]).tobytes()
    return out


BPP = {"nv12": (1, 2), "vuyx": (4,), "vuya": (4,), "yuv444p": (1, 1, 1), "yuv420p": (1, 1, 1)}


def test_raw_planes_reads_every_layout_as_swscale_writes_it(gb: ModuleType) -> None:
    """The GPU controls download NV12 / VUYX / VUYA: known planar planes, repacked into those
    layouts by swscale itself (no conversion, no scaling), come back exactly."""
    from av.video.frame import VideoFrame

    rng = np.random.default_rng(4)
    w, h = 32, 16
    for packed, planar, bpp in (("nv12", "yuv420p", (1, 2)), ("vuyx", "yuv444p", (4,)),
                                ("vuya", "yuv444p", (4,))):  # fmt: skip
        cw, ch = (w // 2, h // 2) if planar == "yuv420p" else (w, h)
        frames = [(rng.integers(0, 256, (h, w), dtype=np.uint8),
                   rng.integers(0, 256, (ch, cw), dtype=np.uint8),
                   rng.integers(0, 256, (ch, cw), dtype=np.uint8)) for _ in range(2)]  # fmt: skip
        data = b"".join(
            _packed_bytes(VideoFrame.from_ndarray(gb.planar_array(f), format=planar)
                         .reformat(format=packed), bpp) for f in frames)  # fmt: skip
        assert len(data) == 2 * gb.raw_frame_bytes(packed, w, h)
        got = gb.raw_planes(data, packed, w, h)
        assert len(got) == 2
        for want, planes in zip(frames, got, strict=True):
            for k, a, b in zip("YUV", planes, want, strict=True):
                assert np.array_equal(a, b), (packed, k)
        # and the planar layouts themselves
        flat = b"".join(gb.planar_bytes(list(f)) for f in frames)
        assert all(np.array_equal(a, b) for f, g in zip(frames, gb.raw_planes(flat, planar, w, h),
                                                        strict=True)
                   for a, b in zip(f, g, strict=True))  # fmt: skip
    with pytest.raises(ValueError):
        gb.raw_frame_bytes("p010", w, h)


def test_the_gpu_control_path_inverts_exactly_like_the_ctl_path(
    gb: ModuleType, tmp_path: Path
) -> None:
    """score_gctl's planes -> planar_array -> to_bgr equals read_raw_yuv (the ctl arms' reader,
    V1's) on the same raw file: the two controls are read the same way."""
    from av.video.frame import VideoFrame

    rng = np.random.default_rng(5)
    w, h = 32, 16
    for fmt in ("yuv444p", "yuv420p"):
        raw = tmp_path / f"{fmt}.yuv"
        frames = [_yuv(rng.integers(0, 256, (h, w, 3), dtype=np.uint8), fmt, gb.COLOR)
                  for _ in range(3)]  # fmt: skip
        raw.write_bytes(b"".join(gb.planar_bytes(gb.frame_planes(f)) for f in frames))
        ctl = gb.read_raw_yuv(raw, fmt, w, h)
        gctl = [gb.to_bgr(VideoFrame.from_ndarray(gb.planar_array(p), format=fmt))
                for p in gb.raw_planes(raw.read_bytes(), fmt, w, h)]  # fmt: skip
        assert all(np.array_equal(a, b) for a, b in zip(ctl, gctl, strict=True)), fmt


def _scene(rng: np.random.Generator, w: int = 160, h: int = 96) -> np.ndarray:
    """A frame with colour: random blocks plus a smooth gradient (a fit needs R, G and B apart)."""
    blocks = rng.integers(0, 256, (h // 8, w // 8, 3), dtype=np.uint8).repeat(8, 0).repeat(8, 1)
    yy, xx = np.mgrid[0:h, 0:w]
    grad = np.stack([xx * 255 // w, yy * 255 // h, (xx + yy) * 255 // (w + h)], -1)
    return ((blocks.astype(int) + grad) // 2).astype(np.uint8)


@pytest.mark.parametrize(("color", "name"), [
    (("ITU709", "JPEG"), "bt709-full"), (("ITU709", "MPEG"), "bt709-limited"),
    (("ITU601", "JPEG"), "bt601-full"), (("ITU601", "MPEG"), "bt601-limited")])  # fmt: skip
def test_the_luma_fingerprint_names_the_convention_that_was_used(gb: ModuleType,
                                                                  color: tuple[str, str],
                                                                  name: str) -> None:  # fmt: skip
    """A range bug or a matrix mix-up is a NUMBER: swscale's own conversion under each convention
    is named back, at both chroma layouts (the fit reads luma only)."""
    rng = np.random.default_rng(6)
    imgs = [_scene(rng) for _ in range(3)]
    for fmt in ("yuv444p", "yuv420p"):
        ys = [gb.frame_planes(_yuv(i, fmt, color))[0] for i in imgs]
        fit = gb.luma_fit(imgs, ys, step=1)
        assert fit["convention"] == name, fit
        assert fit["convention_err_levels"] < 1.0 and fit["rms"] < 1.0, fit
    limited = name.endswith("limited")
    assert fit["scale"] == pytest.approx(219 / 255 if limited else 1.0, abs=0.01)
    assert fit["offset"] == pytest.approx(16.0 if limited else 0.0, abs=1.0)


def test_the_fingerprint_names_nothing_it_does_not_know(gb: ModuleType) -> None:
    assert gb.name_convention(0.2126, 0.7152, 0.0722, 0.0) == ("bt709-full", 0.0)
    name, err = gb.name_convention(0.25, 0.65, 0.10, 8.0)  # between conventions
    assert name == "none" and err > gb.FIT_NAMED_LEVELS
    rng = np.random.default_rng(8)
    img = _scene(rng)
    fit = gb.luma_fit([img], [np.full(img.shape[:2], 128, np.uint8)])  # a flat plane
    assert fit["convention"] == "none" and fit["offset"] == pytest.approx(128.0)


def test_plane_diff_is_signed_per_plane(gb: ModuleType) -> None:
    a = [
        np.full((4, 4), 20, np.uint8),
        np.full((2, 2), 130, np.uint8),
        np.full((2, 2), 120, np.uint8),
    ]
    b = [
        np.full((4, 4), 16, np.uint8),
        np.full((2, 2), 128, np.uint8),
        np.full((2, 2), 128, np.uint8),
    ]
    d = gb.plane_diff(a, b)
    assert d["Y"] == {"mean": 4.0, "mean_abs": 4.0, "max_abs": 4}
    assert d["U"]["mean"] == 2.0 and d["V"] == {"mean": -8.0, "mean_abs": 8.0, "max_abs": 8}
    with pytest.raises(ValueError):
        gb.plane_diff(a, [b[0], b[0], b[0]])


def _x265_444(path: Path, frames: list[np.ndarray], color: tuple[str, str], tag: str) -> None:
    """An all-intra HEVC 4:4:4 stream from libx265 (CPU), converted with ``color`` and tagged
    ``tag`` (pc | tv): the stand-in for a vpp-hevc444 arm."""
    import av

    with av.open(str(path), "w", format="hevc") as out:
        st = out.add_stream("libx265", rate=1, options={
            "x265-params": "keyint=1:min-keyint=1:scenecut=0:qp=16:log-level=error",
            "preset": "ultrafast"})  # fmt: skip
        st.width, st.height, st.pix_fmt = frames[0].shape[1], frames[0].shape[0], "yuv444p"
        st.codec_context.color_range = 2 if tag == "pc" else 1
        st.codec_context.colorspace = 1  # BT.709
        for img in frames:
            vf = _yuv(img, "yuv444p", color)
            vf.color_range = 2 if tag == "pc" else 1
            vf.colorspace = 1
            for pkt in st.encode(vf):
                out.mux(pkt)
        for pkt in st.encode(None):
            out.mux(pkt)


def test_a_declared_limited_range_is_decoded_as_declared(gb: ModuleType, tmp_path: Path) -> None:
    """The tv arm: a limited-range stream, tagged so, is inverted with ITS range (positive), reads
    washed out under round 1's full range (negative), and its VUI says what it is."""
    rng = np.random.default_rng(9)
    imgs = [_scene(rng, 64, 48) for _ in range(2)]
    tv = gb.arm_color(gb.arm_by_name("vpp-hevc444-q20-tv"))
    assert tv == ("ITU709", "MPEG")
    path = tmp_path / "tv.hevc"
    _x265_444(path, imgs, tv, "tv")
    right = gb.decode_stream(path, "hevc", "yuv444p", alone=True, color=tv)
    wrong = gb.decode_stream(path, "hevc", "yuv444p", alone=False)  # round 1's COLOR
    assert right["vui"] == {"range": "tv", "matrix": "bt709"}
    assert right["alone_identical"] == 2 and right["md5"] == wrong["md5"]  # the same planes
    good = min(gb.psnr(i, d) for i, d in zip(imgs, right["bgr"], strict=True))
    bad = max(gb.psnr(i, d) for i, d in zip(imgs, wrong["bgr"], strict=True))
    assert good > 38 and bad < good - 8, (good, bad)
    worst = max(int(np.max(np.abs(i.astype(int) - d))) for i, d in zip(imgs, wrong["bgr"],
                                                                        strict=True))  # fmt: skip
    assert worst > 10  # what doc 6.4 says a range mix-up does


def test_parity_counts_and_coordinate_differences(gb: ModuleType) -> None:
    box = [100.0, 100.0, 140.0, 180.0, 0.9, "monster", "cookie"]
    moved = [101.0, 100.0, 141.0, 182.0, 0.8, "monster", "cookie"]
    other = [300.0, 300.0, 340.0, 380.0, 0.9, "monster", "cruiser"]
    p = gb.parity_stats([([box], [moved]), ([box, other], [box])])
    assert (p["png_boxes"], p["dec_boxes"], p["matched"]) == (3, 2, 2)
    assert p["of_png"] == 0.6667 and p["of_dec"] == 1.0
    assert p["coord_med"] == 1.0 and p["coord_p95"] == 2.0
    species = [100.0, 100.0, 140.0, 180.0, 0.9, "monster", "cruiser"]
    assert gb.parity_stats([([box], [species])])["matched"] == 0  # same class AND species


def test_gb_per_hour(gb: ModuleType) -> None:
    assert gb.gb_per_hour(2_000_000, 1) == 7.2
    assert gb.gb_per_hour(20_000, 30) == 2.16


# --- the verdict ---------------------------------------------------------------------------------


def _quality(psnr: float, ssim: float = 0.99, crop: float | None = None) -> dict[str, Any]:
    c = psnr if crop is None else crop
    return {"psnr_mean": psnr, "psnr_min": psnr - 2, "ssim_mean": ssim, "ssim_min": ssim - 0.01,
            "maxabs": 2, "sat_count": 5000, "sat_kept": 4990, "sat_keep": 0.998,
            "crops": {k: {"psnr_mean": c, "psnr_min": c - 2} for k in
                      ("basic_info", "chat", "minimap")},
            "gen2_psnr_mean": 41.5}  # fmt: skip


def _arm(bpf: float, psnr: float, of: float = 0.99) -> dict[str, Any]:
    return {"status": "ok", "bytes_per_frame": bpf, "quality": _quality(psnr),
            "parity": {"png_boxes": 400, "dec_boxes": 400, "matched": int(400 * of),
                       "of_png": of, "of_dec": of, "coord_med": 0.3, "coord_p95": 1.2},
            "d1": {"frames": 100, "alone_identical": 100},
            "d2": {"compared": 100, "va_eq_sw": 100, "host_eq_sw": 100}}  # fmt: skip


def _score(arms: dict[str, Any], ctl_psnr: float = 55.0, boxes: int = 400) -> dict[str, Any]:
    sample = {"kind": "ref", "png": {"bytes_per_frame": 2_000_000, "encode_png_ms": 200.0},
              "arms": {"ctl-yuv444": {"status": "ok", "quality": {"psnr_mean": ctl_psnr,
                                                                  "maxabs": 2}},
                       "ref-jpeg95": {"status": "ok", "bytes_per_frame": 400_000,
                                      "quality": _quality(42.0),
                                      "parity": {"png_boxes": boxes, "dec_boxes": boxes,
                                                 "matched": boxes, "of_png": 0.99,
                                                 "of_dec": 0.99, "coord_med": 0.2,
                                                 "coord_p95": 1.0}},
                       **arms}}  # fmt: skip
    for a in arms.values():
        if a.get("parity"):
            a["parity"]["png_boxes"] = boxes
    timing = {f"enc_{n}": {"cpu_ms_per_frame": 4.0, "fps": 300.0} for n in arms}
    return {"samples": {"s1": sample, "s2": sample}, "timing": timing}


def test_the_verdict_picks_the_smallest_arm_that_passes_every_bar(gb: ModuleType) -> None:
    score = _score({"hevc420-q14": _arm(500_000, 44.0), "hevc420-q20": _arm(300_000, 43.0),
                    "hevc420-q26": _arm(150_000, 39.0)})  # fmt: skip
    v = gb.verdict(score)
    assert v["valid"] and v["candidate"] == "hevc420-q20"
    assert not v["arms"]["hevc420-q26"]["pass"]  # below the JPEG reference's PSNR (Q1)
    assert v["arms"]["hevc420-q26"]["samples"]["s1"]["Q1"]["result"] == "FAIL"
    assert v["arms"]["hevc420-q14"]["pass"]
    assert v["arms"]["hevc444-q20"]["samples"]["s1"]["status"] == "not run"


R1_SCORE = ROOT / "data" / "bench" / "gpu-rec" / "20261108-recbench.json"  # gitignored, local


@pytest.mark.skipif(not R1_SCORE.exists(), reason="round 1's score lives in data/ (local only)")
def test_round_1_score_gives_the_same_verdict_and_rates_today(gb: ModuleType) -> None:
    """Section 8's numbers stay reproducible: today's verdict and rates on round 1's own score are
    the ones it recorded (sha256 5ce0312bc88a0b3a... on 2026-11-08)."""
    import json

    score = json.loads(R1_SCORE.read_text())
    assert "round" not in score  # round 1 predates rounds: it is read as round 1
    assert gb.verdict(score) == score["verdict"] and gb.rates(score) == score["rates"]


def test_the_verdict_needs_the_colour_round_trip_first(gb: ModuleType) -> None:
    v = gb.verdict(_score({"hevc420-q20": _arm(300_000, 43.0)}, ctl_psnr=40.0))
    assert not v["valid"] and v["candidate"] is None and "V1" in v["note"]


def test_an_underpowered_detector_never_passes_an_arm(gb: ModuleType) -> None:
    v = gb.verdict(_score({"hevc420-q20": _arm(300_000, 43.0)}, boxes=50))
    assert v["arms"]["hevc420-q20"]["samples"]["s1"]["P"]["result"] == "NA"
    assert not v["arms"]["hevc420-q20"]["pass"] and v["candidate"] is None


def test_size_parity_decode_and_cpu_bars_each_fail_alone(gb: ModuleType) -> None:
    for broken, bar in (
        ({"bytes_per_frame": 600_000}, "S1"),
        ({"parity": {"png_boxes": 400, "dec_boxes": 400, "matched": 380, "of_png": 0.95,
                     "of_dec": 0.95, "coord_med": 0.3, "coord_p95": 1.2}}, "P1"),
        ({"d1": {"frames": 100, "alone_identical": 99}}, "D1"),
        ({"d2": {"compared": 100, "va_eq_sw": 99, "host_eq_sw": 100}}, "D2"),
    ):  # fmt: skip
        arm = _arm(300_000, 43.0) | broken
        v = gb.verdict(_score({"hevc420-q20": arm}))
        assert v["arms"]["hevc420-q20"]["samples"]["s1"][bar]["result"] == "FAIL", bar
        assert v["candidate"] is None, bar
    score = _score({"hevc420-q20": _arm(300_000, 43.0)})
    score["timing"]["enc_hevc420-q20"] = {"cpu_ms_per_frame": 25.0, "fps": 300.0}
    v = gb.verdict(score)
    assert v["arms"]["hevc420-q20"]["samples"]["s1"]["S2"]["result"] == "FAIL"
    del score["timing"]["enc_hevc420-q20"]
    assert gb.verdict(score)["candidate"] is None  # S2 / S3 must be measured, not NA


# --- the host decode path, on a CPU-encoded stream -----------------------------------------------


def _x264_stream(path: Path, n: int) -> list[bytes]:
    """An all-intra raw H.264 stream (libx264 repeats SPS / PPS at every IDR without a global
    header); returns its access units."""
    import av

    rng = np.random.default_rng(7)
    params = "keyint=1:min-keyint=1:scenecut=0"
    aus: list[bytes] = []
    with av.open(str(path), "w", format="h264") as out:
        st = out.add_stream("libx264", rate=1, options={"x264-params": params, "bf": "0"})
        st.width, st.height, st.pix_fmt = 64, 48, "yuv420p"
        for _ in range(n):
            img = rng.integers(0, 256, (48, 64, 3), dtype=np.uint8)
            vf = av.VideoFrame.from_ndarray(img, format="bgr24").reformat(format="yuv420p")
            for pkt in st.encode(vf):
                aus.append(bytes(pkt))
                out.mux(pkt)
        for pkt in st.encode(None):
            aus.append(bytes(pkt))
            out.mux(pkt)
    return aus


def _strip_parameter_sets(au: bytes) -> bytes:
    """An Annex-B access unit without its SPS (7) and PPS (8) NAL units."""
    starts = [m.start() for m in re.finditer(b"\x00\x00\x01", au)]
    out = b""
    for i, s in enumerate(starts):
        end = starts[i + 1] if i + 1 < len(starts) else len(au)
        nal = au[s:end]
        if nal[3] & 0x1F not in (7, 8):
            out += b"\x00" + nal
    return out


def test_d1_proves_a_positive_and_a_negative_case(gb: ModuleType, tmp_path: Path) -> None:
    """Each frame decoded ALONE: with the parameter sets repeated at every IDR every frame passes;
    without them only the first does -- the check can see the failure it exists for."""
    good, bad = tmp_path / "good.h264", tmp_path / "bad.h264"
    aus = _x264_stream(good, 5)
    bad.write_bytes(aus[0] + b"".join(_strip_parameter_sets(a) for a in aus[1:]))
    g = gb.decode_stream(good, "h264", "yuv420p", alone=True)
    b = gb.decode_stream(bad, "h264", "yuv420p", alone=True)
    assert len(g["bgr"]) == len(g["md5"]) == g["packets"] == g["keyframes"] == 5
    assert g["alone_identical"] == 5
    assert b["alone_identical"] == 1 and len(b["bgr"]) == 5 and b["undecodable"] == 0
    assert b["md5"] == g["md5"]  # the same pictures, decoded in sequence
    assert g["bgr"][0].shape == (48, 64, 3) and g["bytes"] > 0
    assert g["inter_bytes_mean"] is None and g["key_bytes_mean"] > 0


def test_the_colour_convention_round_trips(gb: ModuleType, tmp_path: Path) -> None:
    from av.video.frame import VideoFrame

    rng = np.random.default_rng(3)
    img = rng.integers(0, 256, (16, 32, 3), dtype=np.uint8)
    yuv = VideoFrame.from_ndarray(img, format="bgr24").reformat(
        format="yuv444p", dst_colorspace=gb.COLOR[0], dst_color_range=gb.COLOR[1]
    )
    back = gb.to_bgr(yuv)
    assert int(np.max(np.abs(back.astype(int) - img))) <= 2
    raw = tmp_path / "ctl.yuv"
    raw.write_bytes(gb.planar_bytes(gb.frame_planes(yuv)) * 2)
    frames = gb.read_raw_yuv(raw, "yuv444p", 32, 16)
    assert len(frames) == 2 and np.array_equal(frames[0], back)
    limited = VideoFrame.from_ndarray(img, format="bgr24").reformat(
        format="yuv444p", dst_colorspace=gb.COLOR[0], dst_color_range="MPEG"
    )
    assert int(np.max(np.abs(gb.to_bgr(limited).astype(int) - img))) > 10  # a range mix-up shows


# --- end to end without the GPU or the NAS: sample -> (stand-in container outputs) -> score ------


def _png_session(datasets: Path, sid: str, n: int) -> list[np.ndarray]:
    from poring_dataset.shards import ShardWriter, write_manifest

    rng = np.random.default_rng(11)
    yy, xx = np.mgrid[0:720, 0:1280]
    base = np.stack([(xx // 5) % 256, (yy // 3) % 256, ((xx + yy) // 7) % 256], -1).astype(np.uint8)
    base[600:606, 0:600] = (0, 0, 255)  # a red line in the chat crop: saturated core pixels
    frames = []
    w = ShardWriter(datasets / sid)
    for i in range(n):
        img = np.roll(base, 4 * i, axis=1)
        img = np.clip(img.astype(int) + rng.integers(-3, 4, img.shape), 0, 255).astype(np.uint8)
        w.add(i, 1_000 + i, img, t_wall="t")
        frames.append(img)
    w.close()
    manifest = {"format": "png", "frames": n, "bytes": w.bytes, "shards": w.shards,
                "game_region": [80, 77, 1280, 720]}  # fmt: skip
    write_manifest(datasets / sid, manifest)
    return frames


def _s2_session(datasets: Path, sid: str, n: int) -> None:
    """A tiny console H.264 session (64 x 48, an IDR every 5 frames) that H264Session accepts."""
    import csv
    import json

    import av

    from poring_dataset import h264

    d = datasets / sid
    d.mkdir(parents=True)
    rng = np.random.default_rng(5)
    aus: list[bytes] = []
    with av.open(str(d / "stream.h264"), "w", format="h264") as out:
        opts = {"x264-params": "keyint=5:min-keyint=5:scenecut=0", "bf": "0"}
        st = out.add_stream("libx264", rate=30, options=opts)
        st.width, st.height, st.pix_fmt = 64, 48, "yuv420p"
        for _ in range(n):
            img = rng.integers(0, 256, (48, 64, 3), dtype=np.uint8)
            vf = av.VideoFrame.from_ndarray(img, format="bgr24").reformat(format="yuv420p")
            for pkt in [*st.encode(vf)]:
                aus.append(bytes(pkt))
                out.mux(pkt)
        for pkt in st.encode(None):
            aus.append(bytes(pkt))
            out.mux(pkt)
    ctx = h264.new_decoder()
    rows, hashes, off = [], [], 0
    for i, au in enumerate(aus):
        frame = list(ctx.decode(av.Packet(au)))[0]
        idr = "1" if i % 5 == 0 else "0"
        rows.append([i, 100 + i, 100 + i, 1, idr, i * 33, off, len(au), 0, i * 33_333_333])
        hashes.append(
            [100 + i, h264.frame_digest(np.ascontiguousarray(frame.to_ndarray(format="bgra")))]
        )
        off += len(au)
    with (d / "stream.idx.csv").open("w", newline="") as fh:
        wr = csv.writer(fh)
        wr.writerow(["au", "frame_id", "frame_number", "frame_type", "idr", "pts_ms", "offset",
                     "length", "receive_ms", "t_publish_ns"])  # fmt: skip
        wr.writerows(rows)
    with (d / "stream.hash.csv").open("w", newline="") as fh:
        wr = csv.writer(fh)
        wr.writerow(["frame_id", "crc32_adler32"])
        wr.writerows(hashes)
    (d / "stream.done.json").write_text(json.dumps({"versions": h264.decoder_versions()}))
    (d / "manifest.json").write_text(json.dumps({"format": "h264", "game_region": [0, 0, 64, 48],
                                                 "frames": n, "bytes": off}))  # fmt: skip


def _x264_intra(path: Path, frames: list[np.ndarray], color: tuple[str, str]) -> None:
    import av

    with av.open(str(path), "w", format="h264") as out:
        st = out.add_stream("libx264", rate=1, options={
            "x264-params": "keyint=1:min-keyint=1:scenecut=0:qp=18", "bf": "0"})  # fmt: skip
        st.width, st.height, st.pix_fmt = frames[0].shape[1], frames[0].shape[0], "yuv420p"
        for img in frames:
            vf = av.VideoFrame.from_ndarray(img, format="bgr24").reformat(
                format="yuv420p", dst_colorspace=color[0], dst_color_range=color[1])  # fmt: skip
            for pkt in st.encode(vf):
                out.mux(pkt)
        for pkt in st.encode(None):
            out.mux(pkt)


def test_sample_then_score_end_to_end(gb: ModuleType, tmp_path: Path,
                                      monkeypatch: pytest.MonkeyPatch) -> None:  # fmt: skip
    """The whole host side on stand-ins: a PNG session and a console session in a fake NAS,
    ``sample``, then what recbench.sh would write (one arm encoded by libx264 on the CPU, the
    colour control, md5s, timing), then ``score`` and the verdict -- no GPU, no NAS, no detector."""
    import json

    from av.video.frame import VideoFrame

    datasets, root = tmp_path / "nas", tmp_path / "root"
    frames = _png_session(datasets, "S-png", 8)
    _s2_session(datasets, "S-s2", 10)
    monkeypatch.setattr(gb, "shm_used", lambda: 0)
    assert gb.main(["sample", "--session", "S-png:test_map", "--runs", "2", "--run-len", "2",
                    "--motion", "S-s2", "--motion-len", "6", "--motion-start-s", "0",
                    "--root", str(root), "--datasets", str(datasets)]) == 0  # fmt: skip
    ind = root / "in" / "test_map"
    assert (ind / "size").read_text().strip() == "1280x720"
    meta = json.loads((ind / "frames.json").read_text())
    assert [r["start"] for r in meta["runs"]] == [1, 5]  # run_starts(8, 2, 2)
    assert (
        gb.decode_png_bgr((ind / "r1" / "000001.png").read_bytes()).tobytes() == frames[6].tobytes()
    )
    assert (root / "in" / "arms.tsv").read_text() == gb.arms_tsv()
    m30, m10, m5 = (root / "in" / f"motion{f}" / "r0" for f in (30, 10, 5))
    assert len(list(m30.iterdir())) == 6 and len(list(m10.iterdir())) == 2
    assert len(list(m5.iterdir())) == 1
    assert (m10 / "000001.png").stat().st_ino == (m30 / "000003.png").stat().st_ino  # a link
    assert (root / "in" / "motion30" / "size").read_text().strip() == "64x48"
    assert gb.main(["sample", "--session", "S-png:test_map", "--root", str(root),
                    "--datasets", str(datasets)]) == 2  # fmt: skip  # a fresh root only
    # what recbench.sh would write: one arm (CPU stand-in), the control, md5s, timing
    out = root / "out"
    status = []
    for arm in gb.round_arms(1):
        for r in ("r0", "r1"):
            ok = arm.name in ("h264-420-q20", "ctl-yuv444")
            status.append(f"{arm.name}\ttest_map\t{r}\t{'ok' if ok else 'unavailable'}\t0\t-")
    (out / "status.tsv").write_text("\n".join(status) + "\n")
    (out / "timing.tsv").write_text("enc_h264-420-q20\t600\t2.0\t1.2\t0.6\tok\trc=0\n")
    for r, idx in (("r0", (1, 2)), ("r1", (5, 6))):
        enc = out / "enc" / "test_map" / "h264-420-q20"
        enc.mkdir(parents=True, exist_ok=True)
        _x264_intra(enc / f"{r}.h264", [frames[i] for i in idx], gb.COLOR)
        md5 = out / "md5" / "test_map" / "h264-420-q20"
        md5.mkdir(parents=True, exist_ok=True)
        lines = "".join(
            f"0, {i}, {i}, 1, 1382400, {h}\n"
            for i, h in enumerate(
                gb.decode_stream(enc / f"{r}.h264", "h264", "yuv420p", alone=False)["md5"]
            )
        )
        (md5 / f"{r}.va.md5").write_text("#hash: MD5\n" + lines)
        (md5 / f"{r}.sw.md5").write_text("#hash: MD5\n" + lines)
        ctl = out / "enc" / "test_map" / "ctl-yuv444"
        ctl.mkdir(parents=True, exist_ok=True)
        (ctl / f"{r}.yuv").write_bytes(b"".join(gb.planar_bytes(gb.frame_planes(
            VideoFrame.from_ndarray(frames[i], format="bgr24").reformat(
                format="yuv444p", dst_colorspace=gb.COLOR[0], dst_color_range=gb.COLOR[1])))
            for i in idx))  # fmt: skip
    res = tmp_path / "score.json"
    assert gb.main(["score", "--root", str(root), "--out", str(res), "--no-detector"]) == 0
    score = json.loads(res.read_text())
    s = score["samples"]["test_map"]
    assert s["png"]["bytes_per_frame"] > 0 and s["png"]["encode_png_ms"] > 0
    arm = s["arms"]["h264-420-q20"]
    assert arm["status"] == "ok" and arm["frames"] == 4 and arm["keyframes"] == 4
    assert arm["quality"]["psnr_mean"] > 30 and arm["quality"]["sat_count"] > 1000
    assert arm["d1"] == {"frames": 4, "alone_identical": 4}
    assert arm["d2"] == {"compared": 4, "va_eq_sw": 4, "host_eq_sw": 4}
    ctl = s["arms"]["ctl-yuv444"]["quality"]
    assert ctl["psnr_mean"] >= gb.BARS["V1_psnr"] and ctl["maxabs"] <= gb.BARS["V1_maxabs"]
    assert s["arms"][gb.JPEG_ARM]["status"] == "ok" and s["arms"]["hevc420-q20"]["status"] == (
        "unavailable"
    )
    assert score["timing"]["enc_h264-420-q20"]["cpu_ms_per_frame"] == 3.0
    assert set(score["rates"]) >= {"png", "h264-420-q20"} and score["rates"]["png"]["1"] > 0
    v = score["verdict"]
    assert v["valid"] and v["candidate"] is None  # no detector run: P is NA, so nothing passes
    assert v["arms"]["h264-420-q20"]["samples"]["test_map"]["P"]["result"] == "NA"
    assert v["arms"]["h264-420-q20"]["samples"]["test_map"]["D1"]["result"] == "PASS"
    assert s["arms"]["hevc420-q20-g30"]["status"] == "unavailable"
    assert score["samples"]["motion30"]["arms"]["hevc420-q20"]["status"] == "not run"


def test_round_2_sample_then_score_end_to_end(gb: ModuleType, tmp_path: Path,
                                              monkeypatch: pytest.MonkeyPatch) -> None:  # fmt: skip
    """Round 2 on stand-ins: ``sample --round 2``, then what recbench.sh would write -- the swscale
    controls, the four GPU controls (the r1 one converted BT.601 LIMITED, as doc 8.1 infers the
    GPU did in round 1; the others as declared), both 4:4:4 candidates (libx265 on the CPU, tagged
    as declared), three timing passes -- then ``score``: the fingerprint names the defect, the
    declared range decodes right, the verdict grades round 2's arms only."""
    import json

    datasets, root = tmp_path / "nas", tmp_path / "root"
    frames = _png_session(datasets, "S-png", 8)
    monkeypatch.setattr(gb, "shm_used", lambda: 0)
    assert gb.main(["sample", "--session", "S-png:test_map", "--runs", "2", "--run-len", "2",
                    "--root", str(root), "--datasets", str(datasets),
                    "--round", "2"]) == 0  # fmt: skip
    assert (root / "in" / "arms.tsv").read_text() == gb.arms_tsv(gb.round_arms(2))
    assert (root / "in" / "round").read_text() == "2\n"
    assert (root / "in" / "timing_reps").read_text() == "3\n"
    assert gb.main(["sample", "--session", "S-png:test_map", "--root", str(tmp_path / "r9"),
                    "--datasets", str(datasets), "--round", "9"]) == 2  # fmt: skip
    out = root / "out"
    full, tv, defect = gb.COLOR, ("ITU709", "MPEG"), ("ITU601", "MPEG")
    raw = {  # arm -> (the format recbench.sh would report, the conversion standing in for it)
        "ctl-yuv444": ("yuv444p", full),
        "ctl-yuv420": ("yuv420p", full),
        "gctl-vpp420-r1": ("nv12", defect),
        "gctl-vpp420": ("nv12", full),
        "gctl-vpp444": ("vuyx", full),
        "gctl-vpp444-tv": ("vuyx", tv),
    }
    streams = {"vpp-hevc444-q20": (full, "pc"), "vpp-hevc444-q20-tv": (tv, "tv")}
    status = []
    for r, idx in (("r0", (1, 2)), ("r1", (5, 6))):
        for arm, (fmt, color) in raw.items():
            d = out / "enc" / "test_map" / arm
            d.mkdir(parents=True, exist_ok=True)
            (d / f"{r}.yuv").write_bytes(b"".join(
                _packed_bytes(_yuv(frames[i], fmt, color), BPP[fmt]) for i in idx))  # fmt: skip
            status.append(f"{arm}\ttest_map\t{r}\tok\t0\t{fmt}")
        for arm, (color, tag) in streams.items():
            d = out / "enc" / "test_map" / arm
            d.mkdir(parents=True, exist_ok=True)
            _x265_444(d / f"{r}.hevc", [frames[i] for i in idx], color, tag)
            md5 = out / "md5" / "test_map" / arm
            md5.mkdir(parents=True, exist_ok=True)
            got = gb.decode_stream(d / f"{r}.hevc", "hevc", "yuv444p", alone=False)["md5"]
            lines = "".join(f"0, {i}, {i}, 1, 2764800, {h}\n" for i, h in enumerate(got))
            for side in ("va", "sw"):
                (md5 / f"{r}.{side}.md5").write_text("#hash: MD5\n" + lines)
            status.append(f"{arm}\ttest_map\t{r}\tok\t0\tvuyx")
        status.append(f"hevc444-q20\ttest_map\t{r}\tunavailable\t0\t-")
    (out / "status.tsv").write_text("\n".join(status) + "\n")
    (out / "timing.tsv").write_text(
        "enc_vpp-hevc444-q20\t600\t2.0\t4.5\t1.5\tok\tpass 1\n"  # 10 ms: a warm-up
        "enc_vpp-hevc444-q20-tv\t600\t2.0\t4.2\t1.2\tok\tpass 1\n"
        "enc_vpp-hevc444-q20\t600\t2.0\t4.2\t1.2\tok\tpass 2\n"
        "enc_vpp-hevc444-q20-tv\t600\t2.0\t4.2\t1.2\tok\tpass 2\n"
        "enc_vpp-hevc444-q20\t600\t2.0\t4.0\t1.0\tok\tpass 3\n"
        "enc_vpp-hevc444-q20-tv\t600\t2.0\t4.2\t1.2\tok\tpass 3\n")  # fmt: skip
    res = tmp_path / "score.json"
    assert gb.main(["score", "--root", str(root), "--out", str(res), "--no-detector"]) == 0
    score = json.loads(res.read_text())
    assert score["round"] == 2 and score["arms"] == list(gb.ROUNDS[2])
    s = score["samples"]["test_map"]
    assert set(s["arms"]) == set(gb.ROUNDS[2]) | {gb.JPEG_ARM}  # round 2's arms only
    c = score["controls"]["test_map"]
    assert set(c) == set(raw)
    assert c["ctl-yuv444"]["fit"] == c["ctl-yuv420"]["fit"] == "bt709-full"  # the known-good case
    assert c["gctl-vpp420-r1"]["fit"] == "bt601-limited"  # the defect, as a name
    assert c["gctl-vpp420-r1"]["offset"] == pytest.approx(16.0, abs=1.5)
    assert c["gctl-vpp420-r1"]["psnr_mean"] < 30 < c["gctl-vpp420"]["psnr_mean"]
    assert c["gctl-vpp420"]["fit"] == c["gctl-vpp444"]["fit"] == "bt709-full"
    assert c["gctl-vpp444-tv"]["fit"] == "bt709-limited"
    assert c["gctl-vpp444-tv"]["declared"] == "bt709-limited"
    assert c["gctl-vpp444"]["psnr_mean"] >= gb.BARS["V1_psnr"]  # read like V1
    assert c["gctl-vpp444-tv"]["psnr_mean"] >= 40 and c["gctl-vpp444-tv"]["maxabs"] <= 4
    assert c["gctl-vpp420"]["vs_swscale_Y"]["max_abs"] <= 1  # the same conversion as swscale's
    assert c["gctl-vpp444-tv"]["vs_swscale_Y"] is None  # another convention: no twin compare
    assert s["arms"]["gctl-vpp420"]["vs_swscale"]["twin"] == "ctl-yuv420"
    for arm in streams:
        a = s["arms"][arm]
        assert a["status"] == "ok" and a["vui_ok"], (arm, a.get("vui"))
        assert a["quality"]["psnr_mean"] > 38, arm  # decoded with ITS declared range
        assert a["d1"] == {"frames": 4, "alone_identical": 4}
    t = score["timing"]["enc_vpp-hevc444-q20"]
    assert t["passes"] == 3 and t["cpu_ms_per_frame"] == 9.0 and t["cpu_ms_passes"][0] == 10.0
    v = score["verdict"]
    assert v["valid"] and v["candidate"] is None  # no detector run: P is NA
    assert set(v["arms"]) == {"hevc444-q20", "vpp-hevc444-q20", "vpp-hevc444-q20-tv"}
    assert v["arms"]["vpp-hevc444-q20-tv"]["samples"]["test_map"]["D1"]["result"] == "PASS"
    assert v["arms"]["vpp-hevc444-q20-tv"]["samples"]["test_map"]["S2"]["value"][0] == 9.0
    assert v["arms"]["hevc444-q20"]["samples"]["test_map"]["status"] == "unavailable"
    assert gb.verdict(score) == v and gb.main(["verdict", str(res)]) == 0


# --- recbench.sh's control flow, with stub ffmpeg / vainfo (the real ones run only in phase 2) ---

STUB_FFMPEG = r"""#!/usr/bin/env bash
# a stand-in: writes a few bytes to the output path (the last argument) and the -benchmark lines
args=("$@"); out="${args[-1]}"
echo "$*" >>"$STUB_LOG"
case " $* " in
  *" -version "*) echo "ffmpeg version stub"; exit 0 ;;
  *" -h "*) echo "Encoder stub options: -qp -rc_mode -profile"; exit 0 ;;
esac
if [[ "$*" == *"format=vuyx,hwupload"* && -n "${STUB_NO_VUYX:-}" ]]; then
  echo "vuyx refused" >&2
  exit 1
fi
if [[ " $* " == *" framemd5 "* ]]; then
  printf '#hash: MD5\n0, 0, 0, 1, 10, aa\n0, 1, 1, 1, 10, bb\n' >"$out"
elif [[ "$out" != "-" && "$out" != /dev/null ]]; then
  printf 'stub-bitstream' >"$out"
fi
echo "frame=  600 fps=300 q=-0.0 size=N/A" >&2
echo "bench: utime=1.200s stime=0.300s rtime=2.000s" >&2
"""
STUB_VAINFO = r"""#!/usr/bin/env bash
cat <<'X'
vainfo: Driver version: stub
      VAProfileH264High               :	VAEntrypointEncSliceLP
      VAProfileHEVCMain               :	VAEntrypointEncSliceLP
      VAProfileHEVCMain10             :	VAEntrypointEncSliceLP
      VAProfileHEVCMain444            :	VAEntrypointVLD
      VAProfileAV1Profile0            :	VAEntrypointEncSliceLP
X
"""


def test_recbench_sh_runs_every_arm_with_stub_tools(gb: ModuleType, tmp_path: Path) -> None:
    import os
    import subprocess

    stub = tmp_path / "bin"
    stub.mkdir()
    for name, body in (("ffmpeg", STUB_FFMPEG), ("vainfo", STUB_VAINFO)):
        (stub / name).write_text(body)
        (stub / name).chmod(0o755)
    ind, out = tmp_path / "in", tmp_path / "out"
    out.mkdir()
    (ind / "arms.tsv").parent.mkdir()
    (ind / "arms.tsv").write_text(gb.arms_tsv())
    for s, kind, fps in (("xmas_dun02", "ref", 1), ("motion30", "motion", 30)):
        for r in ("r0", "r1") if kind == "ref" else ("r0",):
            (ind / s / r).mkdir(parents=True)
            for i in range(3):
                (ind / s / r / f"{i:06d}.png").write_bytes(b"png")
        for f, v in (("kind", kind), ("fps", str(fps)), ("size", "1280x720"), ("map", "m")):
            (ind / s / f).write_text(v + "\n")
    env = {**os.environ, "PATH": f"{stub}:{os.environ['PATH']}", "RECBENCH_IN": str(ind),
           "RECBENCH_OUT": str(out), "TMPDIR": str(tmp_path),
           "STUB_LOG": str(tmp_path / "log")}  # fmt: skip
    script = ROOT / "services" / "media-probe" / "recbench.sh"
    r = subprocess.run(["bash", str(script)], env=env, capture_output=True, text=True, timeout=120,
                       check=False)  # fmt: skip
    assert r.returncode == 0, r.stdout[-2000:] + r.stderr[-2000:]
    rows = gb.parse_tsv((out / "status.tsv").read_text(), gb.STATUS_FIELDS)
    got = {(x["arm"], x["sample"], x["run"]): x for x in rows}
    for arm in gb.round_arms(1):
        samples = {"ref": ["xmas_dun02"], "motion": ["motion30"],
                   "all": ["xmas_dun02", "motion30"]}[arm.samples]  # fmt: skip
        for s in samples:
            for run in ("r0", "r1") if s == "xmas_dun02" else ("r0",):
                row = got[(arm.name, s, run)]
                want = "unavailable" if arm.va_profile == gb.HEVC444 else "ok"
                assert row["status"] == want, (arm.name, s, run, row)
    assert len(rows) == sum(
        len(v)
        for v in [
            [1] * (2 if a.samples == "ref" else 1 if a.samples == "motion" else 3)
            for a in gb.round_arms(1)
        ]
    )
    assert got[("hevc420-q20", "xmas_dun02", "r0")]["note"] == "nv12"  # the format that encoded
    assert (
        out / "enc" / "xmas_dun02" / "hevc420-q20" / "r1.hevc"
    ).read_bytes() == b"stub-bitstream"
    assert (out / "md5" / "xmas_dun02" / "av1-420-g40" / "r0.va.md5").exists()
    assert not (out / "md5" / "xmas_dun02" / "hevc420-q20-g30").exists()  # GOP arms: no D2
    assert not (out / "md5" / "motion30").exists()
    timing = {x["name"]: gb.timing_row(x) for x in gb.parse_tsv(
        (out / "timing.tsv").read_text(), gb.TIMING_FIELDS)}  # fmt: skip
    timed = {f"enc_{a.name}" for a in gb.round_arms(1) if a.timing and a.va_profile != gb.HEVC444}
    assert timed <= set(timing) and {"raw_read", "conv_nv12", "conv_yuv444p"} <= set(timing)
    assert not any(k.endswith("hevc444-q20") for k in timing)  # unavailable: never timed
    assert timing["enc_hevc420-q20"]["cpu_ms_per_frame"] == 2.5
    assert timing["dec_va_hevc420-q20"]["fps"] == 300.0
    log = (tmp_path / "log").read_text()
    assert "-low_power 1" in log and "-color_range pc" in log and "-fps_mode passthrough" in log
    assert "scale_vaapi=out_color_matrix=bt709:out_range=full:format=nv12" in log  # the vpp arm
    assert "-g 30 -bf 0" in log and "-global_quality 40" in log
    assert (out / "help-hevc_vaapi.txt").exists() and (out / "vainfo.txt").exists()
    assert "recbench end" in (out / "results.txt").read_text()
    # a fresh /out only
    again = subprocess.run(["bash", str(script)], env=env, capture_output=True, text=True,
                           timeout=60, check=False)  # fmt: skip
    assert again.returncode != 0 and "not empty" in again.stdout


def test_recbench_sh_falls_back_to_the_second_upload_format(gb: ModuleType, tmp_path: Path) -> None:
    import os
    import subprocess

    stub = tmp_path / "bin"
    stub.mkdir()
    vainfo = STUB_VAINFO.replace(":\tVAEntrypointVLD", ":\tVAEntrypointEncSliceLP")
    for name, body in (("ffmpeg", STUB_FFMPEG), ("vainfo", vainfo)):
        (stub / name).write_text(body)
        (stub / name).chmod(0o755)
    ind, out = tmp_path / "in", tmp_path / "out"
    (ind / "x" / "r0").mkdir(parents=True)
    out.mkdir()
    one = [a for a in gb.ARMS if a.name == "hevc444-q20"]
    (ind / "arms.tsv").write_text(gb.arms_tsv(one))
    (ind / "x" / "r0" / "000000.png").write_bytes(b"png")
    for f, v in (("kind", "ref"), ("fps", "1"), ("size", "1280x720"), ("map", "m")):
        (ind / "x" / f).write_text(v + "\n")
    env = {**os.environ, "PATH": f"{stub}:{os.environ['PATH']}", "RECBENCH_IN": str(ind),
           "RECBENCH_OUT": str(out), "TMPDIR": str(tmp_path), "STUB_LOG": str(tmp_path / "log"),
           "STUB_NO_VUYX": "1"}  # fmt: skip
    r = subprocess.run(["bash", str(ROOT / "services" / "media-probe" / "recbench.sh")], env=env,
                       capture_output=True, text=True, timeout=60, check=False)  # fmt: skip
    assert r.returncode == 0, r.stdout[-2000:] + r.stderr[-2000:]
    rows = gb.parse_tsv((out / "status.tsv").read_text(), gb.STATUS_FIELDS)
    assert [(x["status"], x["note"]) for x in rows] == [("ok", "vuya")]
    assert (out / "logs" / "fmt-hevc444-q20").read_text().strip() == "vuya"
    assert "upload format vuya, not vuyx" in (out / "results.txt").read_text()
    timed = [ln for ln in (tmp_path / "log").read_text().splitlines()
             if "-benchmark" in ln and "-c:v hevc_vaapi" in ln]  # fmt: skip
    assert len(timed) == 1 and "format=vuya,hwupload" in timed[0]  # the timing pass reuses it


def test_recbench_sh_round_2_runs_the_gpu_controls_and_times_three_passes(
    gb: ModuleType, tmp_path: Path
) -> None:
    import os
    import subprocess

    stub = tmp_path / "bin"
    stub.mkdir()
    vainfo = STUB_VAINFO.replace(":\tVAEntrypointVLD", ":\tVAEntrypointEncSliceLP")
    for name, body in (("ffmpeg", STUB_FFMPEG), ("vainfo", vainfo)):
        (stub / name).write_text(body)
        (stub / name).chmod(0o755)
    ind, out = tmp_path / "in", tmp_path / "out"
    out.mkdir()
    for r in ("r0", "r1"):
        (ind / "xmas_dun02" / r).mkdir(parents=True)
        for i in range(3):
            (ind / "xmas_dun02" / r / f"{i:06d}.png").write_bytes(b"png")
    for f, v in (("kind", "ref"), ("fps", "1"), ("size", "1280x720"), ("map", "m")):
        (ind / "xmas_dun02" / f).write_text(v + "\n")
    (ind / "arms.tsv").write_text(gb.arms_tsv(gb.round_arms(2)))
    (ind / "round").write_text("2\n")
    (ind / "timing_reps").write_text(f"{gb.TIMING_REPS[2]}\n")
    env = {**os.environ, "PATH": f"{stub}:{os.environ['PATH']}", "RECBENCH_IN": str(ind),
           "RECBENCH_OUT": str(out), "TMPDIR": str(tmp_path),
           "STUB_LOG": str(tmp_path / "log")}  # fmt: skip
    script = ROOT / "services" / "media-probe" / "recbench.sh"
    r = subprocess.run(["bash", str(script)], env=env, capture_output=True, text=True, timeout=120,
                       check=False)  # fmt: skip
    assert r.returncode == 0, r.stdout[-2000:] + r.stderr[-2000:]
    rows = gb.parse_tsv((out / "status.tsv").read_text(), gb.STATUS_FIELDS)
    assert {(x["arm"], x["run"], x["status"]) for x in rows} == {
        (a, run, "ok") for a in gb.ROUNDS[2] for run in ("r0", "r1")}  # fmt: skip
    log = (tmp_path / "log").read_text().splitlines()
    gctl = [ln for ln in log if "/gctl-vpp420-r1/r0.yuv" in ln]
    assert len(gctl) == 1
    assert (
        "format=bgra,hwupload,scale_vaapi=out_color_matrix=bt709:out_range=full:format=nv12,"
        "hwdownload,format=nv12"
    ) in gctl[0]  # round 1's exact GPU conversion, downloaded
    assert "-f rawvideo -pix_fmt nv12" in gctl[0] and "-frames:v 10" in gctl[0]
    tv = [ln for ln in log if "/vpp-hevc444-q20-tv/r0.hevc" in ln and "-c:v hevc_vaapi" in ln]
    assert len(tv) == 1 and f"scale_vaapi={gb.VPP_TV}:format=vuyx" in tv[0]
    assert "-color_range tv" in tv[0] and "-profile:v rext" in tv[0]
    full = [ln for ln in log if "/vpp-hevc444-q20/r0.hevc" in ln and "-c:v hevc_vaapi" in ln]
    assert len(full) == 1 and "-color_range pc" in full[0]
    assert f"scale_vaapi={gb.VPP_FULL}:format=vuyx" in full[0]
    assert (out / "md5" / "xmas_dun02" / "vpp-hevc444-q20-tv" / "r0.va.md5").exists()
    assert not (out / "md5" / "xmas_dun02" / "gctl-vpp444").exists()  # controls: no D2
    trows = gb.parse_tsv((out / "timing.tsv").read_text(), gb.TIMING_FIELDS)
    enc = [x["name"] for x in trows if x["name"].startswith("enc_")]
    timed = [f"enc_{n}" for n in gb.ROUNDS[2] if gb.arm_by_name(n).timing]
    assert enc == timed * 3  # round-robin: pass 1 of every arm, then 2, then 3
    assert [x["name"] for x in trows if x["name"].startswith("dec_")] == [
        f"dec_{k}_{n[4:]}" for n in timed for k in ("va", "sw")]  # once, in pass 1  # fmt: skip
    merged = gb.merge_timing(trows)
    assert all(merged[n]["passes"] == 3 for n in timed)
    assert "(pass 2/3)" in next(x["note"] for x in trows if x["name"] == timed[0]
                                and "pass 2" in x["note"])  # fmt: skip
    assert (out / "help-scale_vaapi.txt").exists()
    # a malformed timing_reps refuses the run
    out2 = tmp_path / "out2"
    out2.mkdir()
    (ind / "timing_reps").write_text("x\n")
    bad = subprocess.run(["bash", str(script)], env={**env, "RECBENCH_OUT": str(out2)},
                         capture_output=True, text=True, timeout=60, check=False)  # fmt: skip
    assert bad.returncode != 0 and "timing_reps" in bad.stdout
