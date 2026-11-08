"""Scratch (not committed): which colour convention reproduces round 1's vpp-hevc420-q20 numbers?
Same PNG frames as round 1 (the NAS sessions, read-only, the run_starts runs), forward BGR -> 4:2:0
under each hypothesis, back with the scorer's own convention (BT.709 full), round 1's metrics."""

import json
import sys
from pathlib import Path

import av
import numpy as np

import gpu_rec_bench as g

HYP = {
    "709-full (the bench's own)": ("ITU709", "JPEG"),
    "709-limited": ("ITU709", "MPEG"),
    "601-limited": ("ITU601", "MPEG"),
    "601-full": ("ITU601", "JPEG"),
}
SESSIONS = {
    "xmas_dun02": "20261105T225409-rdp-xmas02-x2",
    "gef_fild10": "20261026T120547-rdp-rogue-c1",
}


def main() -> None:
    out = {}
    for name, sid in SESSIONS.items():
        session = g.DATASETS / sid
        manifest = json.loads((session / "manifest.json").read_text())
        starts = g.run_starts(int(manifest["frames"]), 2, 50)
        wanted = sorted({s + i for s in starts for i in range(50)})
        got = g.png_session_frames(session, set(wanted))
        per = {h: [] for h in HYP}
        for idx in wanted:
            ref = g.decode_png_bgr(got[idx][0])
            src = av.VideoFrame.from_ndarray(ref, format="bgr24")
            for h, (cs, rng) in HYP.items():
                yuv = src.reformat(format="yuv420p", dst_colorspace=cs, dst_color_range=rng)
                dec = g.to_bgr(yuv)
                per[h].append(g.frame_metrics(ref, dec))
        out[name] = {"starts": starts, "frames": len(wanted)}
        for h in HYP:
            s = g.summarise(per[h])
            out[name][h] = {k: s[k] for k in ("psnr_mean", "psnr_min", "ssim_mean", "ssim_min",
                                              "maxabs", "sat_keep")}
            out[name][h]["crops"] = {k: v["psnr_mean"] for k, v in s["crops"].items()}
        print(json.dumps({name: out[name]}), flush=True)
    Path(sys.argv[1]).write_text(json.dumps(out, indent=1) + "\n")


if __name__ == "__main__":
    main()
