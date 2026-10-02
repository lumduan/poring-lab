#!/usr/bin/env python3
"""Cut and check the UI anchor templates (ADR-0011) on the frozen 1280x720 layout.

    ui_anchors_tool.py capture [--png SHOT] [--mask-png SHOT2] [--windows basic_info,hotbar,chat]
        Cut each window's template strip where it sits now (poring_env.ui_anchors.CAPTURE_ORIGINS)
        from the live client area, or from a PNG saved by `ro_agent.py shot` (full screen) or a
        client-area PNG, into data/ui_anchors/ (gitignored: cut from the lab's frames, like
        ro_agent's signatures). --mask-png: the SAME UI over another scene; the pixels that agree
        become the template's stable mask (RO windows are translucent; the chat almost entirely).
    ui_anchors_tool.py check [--png SHOT]
        Locate every window that has a template, resolve every element, print both; an overlay
        of the boxes goes to /dev/shm (rule 7).

Pixels in only: frames come from the screen (or a saved screenshot), nothing else.
"""

import argparse
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ro_agent as r  # noqa: E402

from poring_dataset.shards import decode_png, encode_png  # noqa: E402
from poring_env import ui_anchors as ua  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / "data" / "ui_anchors"
SCRATCH = Path("/dev/shm/poring-lab-tmp")


def client_frame(png: str | None) -> np.ndarray:
    """The client area as BGR: from a full-screen PNG (stored RGB) or a live grab (BGRA)."""
    gx, gy, gw, gh = r.game_region()
    if png:
        rgb = decode_png(Path(png).read_bytes())
        if rgb.shape[:2] != (gh, gw):  # a full-screen shot: cut the client area out
            rgb = rgb[gy : gy + gh, gx : gx + gw]
        return np.ascontiguousarray(rgb[:, :, ::-1])
    screen = r.Screen()
    try:
        _, img = screen.grab(gx, gy, gw, gh)
    finally:
        screen.close()
    return np.ascontiguousarray(img[:, :, :3])


def cmd_capture(png: str | None, mask_png: str | None, names: list[str]) -> int:
    origins = {n: ua.CAPTURE_ORIGINS[n] for n in names}
    templates = ua.cut_templates(client_frame(png), origins, ua.WINDOWS)
    masks = {}
    if mask_png:
        others = ua.cut_templates(client_frame(mask_png), origins, ua.WINDOWS)
        masks = ua.stable_masks(templates, others)
    ua.save_templates(TEMPLATES, templates, masks)
    stable = {n: round(float(m.mean()), 3) for n, m in masks.items()}
    summary = {n: {"shape": list(t.shape), "stable": stable.get(n)} for n, t in templates.items()}
    print(json.dumps(summary))
    return 0


def cmd_check(png: str | None) -> int:
    frame = client_frame(png)
    anchors = ua.default_registry(TEMPLATES)
    gray = ua.to_gray(frame)
    windows = {}
    for name, spec in ua.WINDOWS.items():
        tmpl = anchors.templates.get(name)
        if tmpl is None:
            windows[name] = "no template"
            continue
        m = ua.match_template(gray, tmpl, anchors.masks.get(name))
        if m is None:
            windows[name] = None
            continue
        tx, ty = spec.template_offset
        windows[name] = {
            "origin": [m.origin[0] - tx, m.origin[1] - ty],
            "distance": round(m.distance, 2),
            "accepted": m.distance <= spec.max_distance,
        }
    origins = anchors.locate(frame)
    elements = {name: anchors.resolve(name, origins, frame) for name in ua.ELEMENTS}
    print(json.dumps({"windows": windows, "elements": elements}, indent=1))
    overlay = frame[:, :, ::-1].copy()  # RGB for the PNG
    for spec in ua.ELEMENTS.values():
        origin = origins.get(spec.window)
        if origin is None or spec.box is None:
            continue
        x, y = origin[0] + spec.box[0], origin[1] + spec.box[1]
        w, h = spec.box[2], spec.box[3]
        overlay[y, x : x + w] = overlay[y + h - 1, x : x + w] = (0, 255, 0)
        overlay[y : y + h, x] = overlay[y : y + h, x + w - 1] = (0, 255, 0)
    SCRATCH.mkdir(parents=True, exist_ok=True)
    out = SCRATCH / "ui_anchors_check.png"
    out.write_bytes(encode_png(np.ascontiguousarray(overlay)))
    print(out)
    return 0 if origins else 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("cmd", choices=["capture", "check"])
    ap.add_argument("--png", help="a full-screen PNG (`ro_agent.py shot`), not a live grab")
    ap.add_argument("--mask-png", help="the same UI over another scene: stable-pixel masks")
    ap.add_argument("--windows", default="basic_info,hotbar,chat")
    a = ap.parse_args()
    if a.cmd == "capture":
        return cmd_capture(a.png, a.mask_png, [n for n in a.windows.split(",") if n])
    return cmd_check(a.png)


if __name__ == "__main__":
    raise SystemExit(main())
