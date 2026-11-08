"""Round 2's GPU 4:4:4 conversion (gctl-vpp444): which small one-sided bias reproduces what it
measured -- SSIM 0.987 on xmas_dun02 but 0.9997 on gef_fild10, at ~46.5 dB on both, its planes
within 2 (Y) / 1 (U, V) levels of swscale's -- and is SSIM's luminance term in DARK windows what
turns a sub-level bias into a structural-looking loss? (doc 8.3; no GPU: the CPU, the NAS read-only)

The frames are exactly the controls': the first 10 of each run_starts run (round 2: 2 runs of 50).
Each model perturbs swscale's own BT.709 full-range 4:4:4 planes (PyAV, as the fingerprint of 8.1
did), and the result is inverted with the bench's own convention (to_bgr) and scored with the
bench's own metrics. Reported per model and sample: PSNR / SSIM as frame_metrics computes them,
the planes against swscale's (plane_diff, as the controls report it), and the SSIM split into
DARK 8 x 8 windows (the PNG's luma mean < DARK) and the rest.

    run: PYTHONPATH=<worktree>/scripts .venv/bin/python gpu_rec_r2_ssim_sim.py OUT.json
"""

import json
import sys
from pathlib import Path

import av
import numpy as np

import gpu_rec_bench as g

SESSIONS = {
    "xmas_dun02": "20261105T225409-rdp-xmas02-x2",
    "gef_fild10": "20261026T120547-rdp-rogue-c1",
}
PER_RUN = 10  # the gctl arms' frames a run
DARK = 16.0  # an 8 x 8 window whose PNG luma mean is below this is DARK
MEASURED = {  # round 2's gctl-vpp444 (20261108-recbench-r2.json), for the printout only
    "xmas_dun02": {"psnr": 46.492, "ssim": 0.98719, "Y": -0.366, "U": -0.397, "V": -0.289},
    "gef_fild10": {"psnr": 46.602, "ssim": 0.99973, "Y": -0.399, "U": -0.041, "V": 0.012},
}


def ssim_map(a: np.ndarray, b: np.ndarray, win: int = 8) -> tuple[np.ndarray, np.ndarray]:
    """The SSIM map of g.ssim_luma (its mean is g.ssim_luma), and the reference's window means."""
    x, y = g.luma(a), g.luma(b)
    n = float(win * win)
    mx, my = g._box_sum(x, win) / n, g._box_sum(y, win) / n
    vx = g._box_sum(x * x, win) / n - mx * mx
    vy = g._box_sum(y * y, win) / n - my * my
    cxy = g._box_sum(x * y, win) / n - mx * my
    c1, c2 = (0.01 * 255) ** 2, (0.03 * 255) ** 2
    s = ((2 * mx * my + c1) * (2 * cxy + c2)) / ((mx * mx + my * my + c1) * (vx + vy + c2))
    return s, mx


def exact_y(bgr: np.ndarray) -> np.ndarray:
    f = bgr.astype(np.float64)
    return 0.2126 * f[..., 2] + 0.7152 * f[..., 1] + 0.0722 * f[..., 0]


def models(bgr: np.ndarray, planes: tuple[np.ndarray, ...]) -> dict[str, tuple[np.ndarray, ...]]:
    """Each hypothesis: (Y, U, V) uint8, from swscale's planes."""
    y, u, v = (p.astype(np.int16) for p in planes)
    ye = exact_y(bgr)
    neutral = (u == 128) & (v == 128)
    dark_px = ye < DARK

    def u8(*ps: np.ndarray) -> tuple[np.ndarray, ...]:
        return tuple(np.clip(p, 0, 255).astype(np.uint8) for p in ps)

    y_trunc = np.floor(ye + 0.1).astype(np.int16)  # round with 0.1, not 0.5: mean ~ -0.4
    y_trunc = np.minimum(y_trunc, y)  # one-sided (never above swscale), as measured
    return {
        "swscale (ctl-yuv444)": u8(y, u, v),
        "Y -1 everywhere (clipped at 0)": u8(y - 1, u, v),
        "Y floor(x + 0.1), one-sided": u8(y_trunc, u, v),
        "U, V -1 on neutral pixels": u8(y, u - neutral, v - neutral),
        "U, V -1 on dark pixels (luma < 16)": u8(y, u - dark_px, v - dark_px),
        "Y floor(x + 0.1) + U, V -1 neutral": u8(y_trunc, u - neutral, v - neutral),
        "Y floor(x + 0.1) + U, V -1 dark": u8(y_trunc, u - dark_px, v - dark_px),
    }


def main() -> None:
    out: dict[str, dict] = {}
    for name, sid in SESSIONS.items():
        session = g.DATASETS / sid
        manifest = json.loads((session / "manifest.json").read_text())
        starts = g.run_starts(int(manifest["frames"]), 2, 50)
        wanted = sorted(s + i for s in starts for i in range(PER_RUN))
        got = g.png_session_frames(session, set(wanted))
        acc: dict[str, dict[str, list]] = {}
        dark_share: list[float] = []
        for idx in wanted:
            ref = g.decode_png_bgr(got[idx][0])
            yuv = av.VideoFrame.from_ndarray(ref, format="bgr24").reformat(
                format="yuv444p", dst_colorspace="ITU709", dst_color_range="JPEG")
            sw = tuple(p.copy() for p in g.frame_planes(yuv))
            for m, planes in models(ref, sw).items():
                dec = g.to_bgr(av.VideoFrame.from_ndarray(g.planar_array(planes),
                                                          format="yuv444p"))
                smap, mref = ssim_map(ref, dec)
                dark = mref < DARK
                a = acc.setdefault(m, {"psnr": [], "ssim": [], "dark": [], "rest": [],
                                       "diff": []})
                a["psnr"].append(g.psnr(ref, dec))
                a["ssim"].append(float(smap.mean()))
                a["dark"].append(float(smap[dark].mean()) if dark.any() else None)
                a["rest"].append(float(smap[~dark].mean()) if (~dark).any() else None)
                a["diff"].append(g.plane_diff(planes, sw))
                if m.startswith("swscale"):
                    dark_share.append(float(dark.mean()))
        res = {"frames": len(wanted), "starts": starts,
               "dark_window_share": round(float(np.mean(dark_share)), 4),
               "measured_gctl_vpp444": MEASURED[name], "models": {}}
        for m, a in acc.items():
            dk = [v for v in a["dark"] if v is not None]
            rs = [v for v in a["rest"] if v is not None]
            res["models"][m] = {
                "psnr_mean": round(float(np.mean(a["psnr"])), 3),
                "ssim_mean": round(float(np.mean(a["ssim"])), 5),
                "ssim_min": round(float(np.min(a["ssim"])), 5),
                "ssim_dark": round(float(np.mean(dk)), 5) if dk else None,
                "ssim_rest": round(float(np.mean(rs)), 5) if rs else None,
                **{k: {"mean": round(float(np.mean([d[k]["mean"] for d in a["diff"]])), 3),
                       "max_abs": max(d[k]["max_abs"] for d in a["diff"])} for k in "YUV"},
            }
        out[name] = res
        print(json.dumps({name: res}), flush=True)
    Path(sys.argv[1]).write_text(json.dumps(out, indent=1) + "\n")


if __name__ == "__main__":
    main()
