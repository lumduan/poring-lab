"""rec_paths: the two recording paths the label, cache and scoring tools read
(xmas02-1080-detector.md T-V1 to T-V4)."""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts"))

import map_labels as ml  # noqa: E402
import rec_paths as rp  # noqa: E402
import ro_agent as ro  # noqa: E402

from poring_env.clientview import ClientView, Panel  # noqa: E402

PANELS = [{"name": "basic_info", "virtual": [0, 0, 230, 150], "real_xy": [0, 0]},
          {"name": "hotbar", "virtual": [226, 0, 300, 40], "real_xy": [226, 0]},
          {"name": "chat", "virtual": [0, 578, 600, 142], "real_xy": [0, 938]},
          {"name": "minimap", "virtual": [1130, 10, 150, 160], "real_xy": [1770, 10]},
          {"name": "cursor", "virtual": [600, 300, 68, 68], "real_xy": [880, 410]}]  # fmt: skip


def lab720(**kw: object) -> dict:
    m = {"session_id": "20261116T205751-rdp-xmas02-sk6a", "backend": "rdp",
         "game_region": [80, 77, 1280, 720], "server": "lab-rathena", "format": "png",
         "recorder_version": 7}  # fmt: skip
    return {**m, **kw}


def virtual1080(**kw: object) -> dict:
    view = {"rect": [0, 0, 1920, 1080], "mode": "fullscreen", "world_scale": 1.5,
            "world_centre": [960.0, 540.0], "panels": PANELS}  # fmt: skip
    m = {"session_id": "20261120T090000-rdp-xmas02-v1f", "backend": "rdp",
         "game_region": [100000, 0, 1280, 720], "server": "lab-rathena", "format": "png",
         "recorder_version": 8, "client_view": view}  # fmt: skip
    return {**m, **kw}


def test_virtual_origin_is_ro_agents() -> None:
    assert rp.VIRTUAL_X0 == ro.VIRTUAL_X0


def test_the_720_path_unchanged_and_v8_admitted() -> None:
    for v in (5, 6, 7, 8):
        assert rp.path_of(lab720(recorder_version=v)) == "lab-720"
    assert rp.path_of(lab720(recorder_version=4)) is None
    assert rp.path_of(lab720(format="hevc")) is None  # the GPU video stays refused
    assert rp.path_of(lab720(game_region=[80, 77, 1440, 900])) is None
    assert rp.path_of(lab720(server="lab-rathena-th")) is None
    assert rp.panel_rects(lab720()) == ()


def test_the_virtual_path_needs_v8_and_its_view() -> None:
    assert rp.path_of(virtual1080()) == "virtual-1080"
    assert rp.problems(virtual1080(recorder_version=7)) == {"recorder_version": 7}  # no view in v7
    assert "client_view" in rp.problems(virtual1080(client_view=None))
    bad = virtual1080()
    bad["client_view"] = {**bad["client_view"], "world_scale": 1.333333}  # a 1440x... client
    assert rp.problems(bad) == {"client_view.world_scale": 1.333333}
    bad["client_view"] = {**virtual1080()["client_view"], "mode": "window"}
    assert rp.problems(bad) == {"client_view.mode": "window"}
    assert rp.path_of(virtual1080(format="hevc")) is None
    assert rp.path_of(virtual1080(backend="console")) is None


def test_panel_rects_are_the_pasted_panels_without_the_pointer() -> None:
    assert rp.panel_rects(virtual1080()) == (
        (0, 0, 230, 150),
        (226, 0, 526, 40),
        (0, 578, 600, 720),
        (1130, 10, 1280, 170),
    )
    assert rp.panel_rects(virtual1080(recorder_version=7)) == ()  # refused: no rects either


def test_map_labels_gate_follows_the_paths() -> None:
    ml.check_recording(lab720())
    ml.check_recording(virtual1080())
    with pytest.raises(SystemExit, match="not the recording path"):
        ml.check_recording(virtual1080(recorder_version=7))
    with pytest.raises(SystemExit, match="not the recording path"):
        ml.check_recording(lab720(game_region=[0, 0, 1920, 1080]))  # real 1080 frames: refused


def test_the_virtual_panels_hold_the_720_windows_whole() -> None:
    """T-V3: with the panels added, the layout's 720 windows they cover are dropped as nested,
    and the bottom-right corner (no panel) stays."""
    rects = ml.session_ui_rects("20261120T090000-rdp-xmas02-v1f", "hunt",
                                rp.panel_rects(virtual1080()))  # fmt: skip
    assert (0, 0, 230, 150) in rects and (0, 578, 600, 720) in rects
    assert (0, 0, 220, 143) not in rects and (0, 585, 600, 720) not in rects
    assert (1228, 668, 1280, 720) in rects
    assert ml.session_ui_rects("20261116T205751-rdp-xmas02-sk6a", "hunt") == ml.session_ui_rects(
        "20261116T205751-rdp-xmas02-sk6a", "hunt", ()
    )


def test_view_record_round_trips_a_clientview() -> None:
    view = ClientView((0, 0, 1920, 1080), "fullscreen", 1.5, None,
                      (Panel("chat", (0, 578, 600, 142), (0, 938)),))  # fmt: skip
    rec = rp.view_record(view)
    assert rec == {"rect": [0, 0, 1920, 1080], "mode": "fullscreen", "world_scale": 1.5,
                   "world_centre": [960.0, 540.0],
                   "panels": [{"name": "chat", "virtual": [0, 578, 600, 142],
                               "real_xy": [0, 938]}]}  # fmt: skip
    m = virtual1080(client_view=rec)
    assert rp.path_of(m) == "virtual-1080"


def test_the_1080_names() -> None:
    spec = ml.MAPS["xmas_dun02"]
    assert spec.fit_by_name("20261120T090000-rdp-xmas02-v1f")
    for name in ("v1T", "v1Tg", "v1Tk"):
        sid = f"20261120T120000-rdp-xmas02-{name}"
        assert spec.is_test(sid, None) and any(sid.endswith(s) for s in spec.eval_suffixes)
    for name in ("v1t1", "v1t2", "v1g1", "v1k1", "v1k2"):  # TRAIN: neither
        sid = f"20261120T100000-rdp-xmas02-{name}"
        assert not spec.is_test(sid, None) and not spec.fit_by_name(sid)
