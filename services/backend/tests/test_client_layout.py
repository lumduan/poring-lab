from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts"))

import client_layout as cl  # noqa: E402

OLD_STANDARD = ((0, 0, 220, 326), (230, 0, 520, 132), (750, 0, 828, 36), (1135, 14, 1266, 162),
                (0, 532, 600, 626), (0, 668, 50, 720), (1228, 668, 1280, 720))  # fmt: skip


def _d(**over: float) -> dict[str, float]:
    base = {"tabs_battle": 50.0, "tabs_regular": 50.0, "arrow_collapsed": 40.0,
            "arrow_expanded": 40.0, "row1": 90.0, "row2": 120.0, "row4": 120.0}  # fmt: skip
    return {**base, **over}


def test_the_standard_rectangles_are_unchanged_and_the_hunting_ones_smaller() -> None:
    assert cl.RECTS["standard"] == OLD_STANDARD
    h = cl.RECTS["hunt"]
    assert len(h) == len(OLD_STANDARD)
    assert h[0] == (0, 0, 220, 143) and h[1] == (230, 0, 520, 33)  # the panel and 3 rows gone
    assert h[2:] == OLD_STANDARD[2:]  # the chat window did not move (Batt's recorded attempt)


def test_decide_reads_each_part_and_says_unknown_otherwise() -> None:
    hunt = cl.decide(_d(tabs_battle=1.0, arrow_collapsed=2.0, row1=0.5))
    assert hunt == {"rows": 1, "panel": "collapsed", "tab": "battle"} and cl.matches(hunt, "hunt")
    std = cl.decide(_d(tabs_regular=1.0, arrow_expanded=0.0, row1=0.5, row2=0.0, row4=0.0))
    assert cl.matches(std, "standard") and not cl.matches(std, "hunt")
    assert cl.decide(_d(row1=95.0))["rows"] == 0  # hidden
    assert cl.decide(_d(row1=1.0, row2=1.0, row4=99.0))["rows"] == 2  # 2-3 rows: an F12 step
    assert cl.decide(_d(row1=1.0, row4=1.0))["rows"] is None  # row 4 without row 2: no sense
    assert cl.decide(_d(tabs_battle=5.0, tabs_regular=6.0))["tab"] is None  # both near: unsure
    # the arrow under the hover cursor (25 vs 50, seen live) is not decisive
    assert cl.decide(_d(arrow_collapsed=25.3, arrow_expanded=50.0))["panel"] is None


def test_next_step_walks_to_the_target_and_never_acts_blind() -> None:
    st = {"rows": 4, "panel": "expanded", "tab": "regular"}
    assert cl.next_step(st, "standard") is None
    assert cl.next_step(st, "hunt") == "f12"
    assert cl.next_step({**st, "rows": 1}, "hunt") == "arrow"
    assert cl.next_step({**st, "rows": 1, "panel": "collapsed"}, "hunt") == "tab:battle"
    assert cl.next_step({"rows": 1, "panel": "collapsed", "tab": "battle"}, "hunt") is None
    assert cl.next_step({**st, "tab": None}, "hunt") == "unknown"
    assert cl.next_step({**st, "rows": None}, "standard") == "unknown"
    assert cl.next_step({**st, "rows": 2}, "standard") == "f12"  # on through the F12 cycle
    assert cl.next_step({**st, "rows": 0}, "hunt") == "f12"


def test_the_ui_rectangles_follow_the_selected_layout_of_the_process() -> None:
    code = (
        "import sys; sys.path.insert(0, 'scripts'); import route_preview as rp, ui_mask as um,"
        " loot1; print(rp.UI_WINDOWS[0], um.STATIC_WINDOWS[0][1], loot1.in_ui(100, 250))"
    )
    out = {}
    for name in ("standard", "hunt"):
        env = {**os.environ, cl.ENV: name, "PYTHONDONTWRITEBYTECODE": "1"}
        out[name] = subprocess.run([sys.executable, "-c", code], cwd=ROOT, env=env, check=True,
                                   capture_output=True, text=True).stdout.strip()  # fmt: skip
    assert out["standard"] == "(0, 0, 220, 326) (0.0, 0.0, 220.0, 326.0) True"
    assert out["hunt"] == "(0, 0, 220, 143) (0.0, 0.0, 220.0, 143.0) False"


def test_read_on_frames_built_from_the_live_templates() -> None:
    """POSITIVE case on the live-cut templates (local data; skipped where absent): a frame carrying
    the hunting layout's crops reads as the hunting layout, the standard crops as standard."""
    if not (cl.TEMPLATES / "arrow_collapsed.npy").exists():
        pytest.skip("the layout templates are not on this host")
    tm = cl.load_templates()

    def frame(parts: dict[str, str], tab: str) -> np.ndarray:
        img = np.full((720, 1280, 3), 120.0, np.float32)  # some ground behind the tabs
        for name, box in parts.items():
            x0, y0, x1, y1 = cl.BOX[box]
            img[y0:y1, x0:x1, :] = tm[name][..., None]  # grey: R = G = B
        x0, x1 = cl.TAB_SPAN[tab]
        img[cl.TAB_ROW, x0:x1, :] = 254.0  # the selected tab's white top border
        return img

    hunt = cl.read(frame({"arrow_collapsed": "arrow", "row1": "row1"}, "battle"), tm)
    assert cl.matches(hunt, "hunt"), hunt
    std = cl.read(frame({"arrow_expanded": "arrow", "row1": "row1", "row2": "row2",
                         "row4": "row4"}, "regular"), tm)  # fmt: skip
    assert cl.matches(std, "standard"), std


def test_the_runner_selects_the_layout_before_the_masks_and_applies_it() -> None:
    src = (ROOT / "scripts/hunt_flow.py").read_text()
    run_ = src[src.index("def run(version: int") :]
    # B3 (blocks plan, 2026-10-21): the layout comes from the RESOLVED config, read first
    i_sel = run_.index('cl.select(prm.get("ui_layout") or "standard")')
    assert run_.index("prm = hcfg.params_for(PARAMS, version)") < i_sel < run_.index("import loot1")
    i_lay = run_.index('lay_ = cl.ensure(agent_raw, screen, prm["ui_layout"])')
    assert run_.rindex("bench.close_chat(agent_raw, screen)", 0, i_lay) > i_lay - 400
    assert i_lay < run_.index("before = gm_state.ensure_hunting(")
    assert "except cl.LayoutError as exc:" in run_ and 'FarmStop(f"client layout: {exc}")' in run_
    w = run_[run_.index("hunt_tabs = prm.get") :][:700]
    assert 'cl.select_tab(agent_raw, screen, "regular")' in w and "finally:" in w
    assert 'cl.select_tab(agent_raw, screen, "battle")' in w


def test_v43_params_the_hunting_layout_and_the_ping_pong_fix_on_v40s_base() -> None:
    import hunt_flow as hf

    p = hf.PARAMS[43]
    assert p["ui_layout"] == "hunt" and p["dead_end_hyst_s"] == 10.0 and 43 in hf.VERSIONS
    assert p["false_dead_fix"] and not p["false_dead_ab"] and not p.get("strike_cells_walking")
    moved = ("false_dead_ab", "ui_layout", "dead_end_hyst_s")
    assert {k: v for k, v in p.items() if k not in moved} == {
        k: v for k, v in hf.PARAMS[40].items() if k not in moved
    }
    for n in (38, 39, 40, 41):
        assert not hf.PARAMS[n].get("ui_layout")


def test_layout_judge_on_a_real_standard_layout_run() -> None:
    """The v43 judge on v41 run 4 (a REAL session, the standard layout): every detected life was
    on screen at some point or boxed at the edge; the shares are proper; the uncovered area holds
    few first detections under the standard layout (partly visible sprites only)."""
    import layout_judge as lj

    sid = "20261019T112949-demo-hunt-flow41"
    if (
        not (ROOT / "data").exists()
        or not Path(f"/dev/shm/poring-lab-demo/{sid}/boxes.jsonl").exists()
    ):
        pytest.skip("the v41 session is not banked on this host")
    r_ = lj.row(sid)
    assert r_["detected"] == 294 and r_["onscreen"] == 322 and r_["detected_share"] == 0.913
    assert r_["bot_seen_10min"] == 50.5 and 0 <= r_["uncovered_share"] < 0.05
    assert lj.windowed_median([0, 1, 2], 0, int(3000e9)) == 0.0  # 5 windows: median of 0,0,0,0,3


def test_the_layout_clicks_only_its_two_ui_controls_inside_the_ui_windows() -> None:
    """Safety (the census's targeted test): client_layout clicks only Basic Info's arrow and the
    chat tabs, and those points lie inside the UI windows of BOTH layouts (never the ground: the
    agent's tab-strip drags of 2026-10-19 13:0x became walks)."""
    src = (ROOT / "scripts/client_layout.py").read_text()
    assert src.count(".click(") == 1 and src.count("_ui_click(agent, *") == 3
    assert src.count("_ui_click(agent, *ARROW_PX)") == 1
    assert src.count("_ui_click(agent, *TAB_PX[") == 2
    assert ".drag(" not in src
    import route_preview as rp

    for name in ("standard", "hunt"):
        rects = cl.RECTS[name]
        for u, v in (cl.ARROW_PX, *cl.TAB_PX.values()):
            assert any(x0 <= u <= x1 and y0 <= v <= y1 for x0, y0, x1, y1 in rects), (name, u, v)
    assert cl.RECTS["standard"] == rp.UI_WINDOWS  # this test process: the standard set
