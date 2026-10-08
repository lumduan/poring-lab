"""scripts/route_demo.py's HUD redraw: the message the console would show at a frame (the latest one
at or before it, within its ttl), drawn onto the frame without error (Batt 2026-10-08)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np

SCRIPTS = Path(__file__).resolve().parents[3] / "scripts"


def test_the_hud_at_a_frame_respects_the_messages_ttl() -> None:
    sys.path.insert(0, str(SCRIPTS))
    spec = importlib.util.spec_from_file_location("route_demo", SCRIPTS / "route_demo.py")
    assert spec and spec.loader
    rd = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(rd)
    S = 1_000_000_000
    msgs = [{"t_mono_ns": 10 * S, "ttl_ms": 1500, "label": "a"},
            {"t_mono_ns": 20 * S, "ttl_ms": 1500, "label": "b"}]  # fmt: skip
    ts = np.array([m["t_mono_ns"] for m in msgs])
    assert rd._hud_at(msgs, ts, 9 * S) is None  # before any message
    assert rd._hud_at(msgs, ts, 11 * S)["label"] == "a"
    assert rd._hud_at(msgs, ts, 12 * S) is None  # a's ttl has passed
    assert rd._hud_at(msgs, ts, 20 * S + S // 2)["label"] == "b"

    from PIL import Image, ImageDraw

    img = Image.new("RGB", (1280, 720))
    hud = {"label": "walk@12", "log": ["click clear of 1 unit envelope(s)"],
           "zone": {"exclude": [{"x": 0.06, "y": 0.09, "w": 0.15, "h": 0.36}]},
           "units": [{"cls": "monster", "conf": 0.91, "dist_cells": 3,
                      "box": {"x": 0.5, "y": 0.4, "w": 0.03, "h": 0.05}}],
           "walk": {"text": "walking to (101,99)", "start": {"x": 0.5, "y": 0.5},
                    "end": {"x": 0.55, "y": 0.45}}}  # fmt: skip
    rd.draw_hud(
        ImageDraw.Draw(img), hud, lambda p: (p["x"] * 1440 - 80, p["y"] * 900 - 77), img.size
    )
    assert np.asarray(img).any()  # something was drawn
