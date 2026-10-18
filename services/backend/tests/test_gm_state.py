"""scripts/gm_state.py (Batt 2026-10-09 ~16:00): the GM's fixed test state -- the level lines'
check (two frames must agree), the restore decision, and the crop geometry."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import numpy as np
import pytest

SCRIPTS = Path(__file__).resolve().parents[2].parent / "scripts"


@pytest.fixture(scope="module")
def gs() -> ModuleType:
    sys.path.insert(0, str(SCRIPTS))
    spec = importlib.util.spec_from_file_location("gm_state", SCRIPTS / "gm_state.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["gm_state"] = mod
    spec.loader.exec_module(mod)
    return mod


def test_both_frames_must_agree(gs: Any) -> None:
    m = gs.MATCH
    assert gs.decide(0.5, m) == "fixed"
    assert gs.decide(m + 1, m + 9) == "restore"
    assert gs.decide(0.5, m + 1) == "unstable" and gs.decide(m + 1, 0.5) == "unstable"


def test_a_changed_digit_is_far_from_the_template(gs: Any) -> None:
    rng = np.random.default_rng(5)
    frame = rng.integers(180, 230, (720, 1280, 3)).astype(np.uint8)
    x, y, w, h = gs.LEVEL_BOX
    template = gs.crop(frame)
    assert template.shape == (h, w) and gs.distance(frame, template) == 0.0
    other = frame.copy()
    other[y + 3 : y + 12, x + 50 : x + 56] = 20  # a 6 x 9 dark digit where the level number sits
    assert gs.distance(other, template) > gs.MATCH
    assert gs.distance(frame[:50, :50], template) == float("inf")  # a wrong size never matches
    noisy = np.clip(frame.astype(int) + rng.integers(-12, 13, frame.shape), 0, 255).astype(np.uint8)
    assert gs.distance(noisy, template) <= gs.MATCH  # codec-level noise is not a change
    one = frame.copy()
    one[y + 4 : y + 9, x + 52] = 10  # a 1 x 5 stroke: the smallest digit change (1 -> 4, say)
    assert gs.distance(one, template) > gs.MATCH


def test_the_restore_lines_lower_both_levels_then_heal(gs: Any) -> None:
    assert gs.RESTORE == ("@baselevelup -98", "@joblevelup -49", "@heal")
    assert len(set(gs.RESTORE)) == len(gs.RESTORE)  # never an identical line in a row


def test_the_notices_are_seen_only_when_shown(gs: Any) -> None:
    """Each notice on its OWN pixels: the see-through shortcut window must not matter."""
    rng = np.random.default_rng(9)
    frame = rng.integers(60, 200, (720, 1280, 3)).astype(np.uint8)
    refs: dict[str, Any] = {}
    for name, box in (("badge", gs.BADGE_BOX), ("levelup_icon", gs.ICON_BOX)):
        _x, _y, w, h = box
        refs[name] = rng.integers(0, 255, (h, w)).astype(np.float32)
        mask = np.zeros((h, w), bool)
        mask[2:12, 2:12] = True
        refs[f"{name}_mask"] = mask
    assert gs.notices(frame, refs) == []
    for name, box in (("badge", gs.BADGE_BOX), ("levelup_icon", gs.ICON_BOX)):
        x, y, w, h = box
        shown = frame.copy()
        shown[y + 2 : y + 12, x + 2 : x + 12] = refs[name].astype(np.uint8)[2:12, 2:12, None]
        shown[y + 20 : y + 30, x + 20 : x + 30] = 0  # the scene behind changes: irrelevant
        assert gs.notices(shown, refs) == [name], name


# --- per path (2026-10-09, poring_env.ui_sets): rdp unchanged; console only with a PROVEN S2 set


@pytest.fixture()
def lab(gs: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Any:
    """gs with its ROOT (and the rdp TEMPLATE) in tmp_path and a writable lock."""
    from types import SimpleNamespace

    monkeypatch.setattr(gs.r, "ROOT", tmp_path)
    monkeypatch.setattr(gs, "TEMPLATE", tmp_path / "data/ui_anchors/gm_state/levels_1_1.npy")
    (tmp_path / "state").mkdir()

    def lock(backend: str) -> None:
        (tmp_path / "state" / "capture-backend").write_text(
            f"BACKEND={backend}\nSEQ=1\nPHASE=steady\nOWNER=t\nSINCE=1\nREASON=t\n"
        )

    lock("rdp")
    return SimpleNamespace(gs=gs, lock=lock, anchors=tmp_path / "data" / "ui_anchors")


def _gm_files(d: Path, seed: int) -> None:
    rng = np.random.default_rng(seed)
    d.mkdir(parents=True, exist_ok=True)
    np.save(d / "levels_1_1.npy", rng.random((25, 68)).astype(np.float32))
    for name in ("badge", "levelup_icon"):
        np.save(d / f"{name}.npy", rng.random((4, 4)).astype(np.float32))
    np.save(d / "badge_mask.npy", np.ones((4, 4), bool))
    np.save(d / "levelup_mask.npy", np.ones((4, 4), bool))


def _prove(root: Path, *components: str) -> None:
    from poring_env import ui_sets

    for c in components:
        ui_sets.record(root, c, True, {}, ui_sets.file_hashes(root, c), command="test")


def test_the_lock_picks_the_gm_state_set(lab: Any) -> None:
    gs = lab.gs
    assert gs._path() == "rdp"
    lab.lock("console")
    assert gs._path() == "s2"
    (lab.anchors.parent.parent / "state" / "capture-backend").write_text("BACKEND=both\n")
    with pytest.raises(gs.r.Stop, match="no template set for the lock's hold"):
        gs._path()  # a malformed lock reads as hold: refused


def test_rdp_is_unchanged_and_needs_no_proof(lab: Any) -> None:
    gs = lab.gs
    with pytest.raises(gs.r.Stop) as e:
        gs._template()
    assert str(e.value) == (f"gm_state: no Lv 1 / 1 template ({gs.TEMPLATE}): run "
                            "`gm_state.py cut` first")  # fmt: skip
    _gm_files(lab.anchors / "gm_state", 1)
    assert gs.require_ready() == "rdp"
    assert np.array_equal(gs._template(), np.load(gs.TEMPLATE))
    assert set(gs._notice_refs()) == {"badge", "badge_mask", "levelup_icon", "levelup_icon_mask"}
    assert not (lab.anchors / "proof.json").exists()


def test_console_needs_the_proven_s2_set(lab: Any) -> None:
    gs, s2 = lab.gs, lab.anchors / "s2"
    _gm_files(lab.anchors / "gm_state", 1)  # the RDP set: never read on console
    lab.lock("console")
    with pytest.raises(gs.r.Stop, match="the s2 template set is not proven"):
        gs.require_ready()
    _gm_files(s2 / "gm_state", 2)
    with pytest.raises(gs.r.Stop, match="not proven"):
        gs._template()
    _prove(s2, "gm_levels")
    assert np.array_equal(gs._template(), np.load(s2 / "gm_state" / "levels_1_1.npy"))
    with pytest.raises(gs.r.Stop, match="gm_notices: not proven"):
        gs.require_ready()  # the notices are not proven yet
    with pytest.raises(gs.r.Stop, match="gm_notices: not proven"):
        gs._notice_refs()
    _prove(s2, "gm_notices")
    assert gs.require_ready() == "s2"
    np.save(s2 / "gm_state" / "badge.npy", np.zeros((4, 4), np.float32))  # edited after
    with pytest.raises(gs.r.Stop, match=r"gm_notices: stale since the proof"):
        gs._notice_refs()
    lab.lock("rdp")
    assert gs.require_ready() == "rdp"  # the RDP path is not affected


def test_the_legacy_live_cut_refuses_off_rdp(lab: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    gs = lab.gs
    lab.lock("console")
    monkeypatch.setattr(gs.sys, "argv", ["gm_state.py", "cut"])
    with pytest.raises(gs.r.Stop, match="writes the RDP set from a live frame"):
        gs.main()  # never an S2 frame into the RDP template


# --- the S2 cut and proof on banked frames (synthetic) -------------------------------------------


def _scene(seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    return np.kron(rng.random((45, 80, 3)) * 255, np.ones((16, 16, 1))).astype(np.uint8)


LEVELS = np.random.default_rng(21).integers(150, 250, (25, 68))
BADGE = np.random.default_rng(22).integers(0, 255, (10, 10))
ICON = np.random.default_rng(23).integers(0, 255, (30, 30))


def _gm_frame(gs: Any, seed: int, fixed: bool, notices: bool) -> np.ndarray:
    f = _scene(seed)
    x, y, w, h = gs.LEVEL_BOX
    lv = LEVELS.copy()
    if not fixed:
        lv[4:13, 50:56] = 10  # a changed digit
    noise = np.random.default_rng(seed + 1).integers(-6, 7, lv.shape)
    f[y : y + h, x : x + w] = np.clip(lv + noise, 0, 255)[..., None]
    if notices:
        bx, by, _, _ = gs.BADGE_BOX
        f[by + 2 : by + 12, bx + 26 : bx + 36] = BADGE[..., None]
        ix, iy, _, _ = gs.ICON_BOX
        f[iy + 8 : iy + 38, ix + 8 : ix + 38] = ICON[..., None]
    return f


def _gm_bank(gs: Any, bank: Path, spec: list[tuple[int, bool, bool]]) -> list[Path]:
    from PIL import Image

    (bank / "frames").mkdir(parents=True, exist_ok=True)
    labels, paths = [], []
    for seed, fixed, shown in spec:
        name = f"{seed}-{fixed}-{shown}.png"
        Image.fromarray(_gm_frame(gs, seed, fixed, shown)[..., ::-1]).save(bank / "frames" / name)
        labels.append({"file": name, "levels": "fixed" if fixed else "not_fixed",
                       "notices": ["badge", "levelup_icon"] if shown else [], "scene": f"s{seed}",
                       "path": "s2", "t_ns": seed})  # fmt: skip
        paths.append(bank / "frames" / name)
    (bank / "labels.json").write_text(json.dumps(labels))
    return paths


def test_the_s2_gm_state_cut_and_proof(lab: Any) -> None:
    from poring_env import ui_sets

    gs, s2 = lab.gs, lab.anchors / "s2"
    cut_spec = [(100, True, True), (100, True, False)]  # the same place, with / without notices
    held = [(200 + k, k % 2 == 0, k % 3 == 0) for k in range(12)]
    bank = lab.anchors.parent / "bank"
    paths = _gm_bank(gs, bank, cut_spec + held)
    gs.cut_levels(paths[1], s2)
    rep = gs.cut_notices(paths[0], paths[1], s2)
    # each mask = the notice's own pixels (those differing from the frame without it by > 40)
    assert 0 < rep["mask_px"]["badge"] <= BADGE.size
    assert 0 < rep["mask_px"]["levelup_icon"] <= ICON.size
    out = gs.prove([bank], s2)
    assert out["excluded_cut"] == 2 and out["held_out"] == 12
    lv, nt = out["gm_levels"], out["gm_notices"]
    assert lv["verdict"] == "PASS", lv
    assert lv["fixed_max"] <= gs.MATCH and lv["not_fixed_min"] >= gs.NOT_FIXED_MIN
    assert nt["verdict"] == "PASS", nt
    assert len(nt["clean_scenes"]) >= 3  # clean frames over other scenes than the cut's
    for comp in ("gm_levels", "gm_notices"):
        res = out[comp]
        ui_sets.record(s2, comp, res["pass"], {}, res.pop("before"), command="test")
    lab.lock("console")
    assert gs.require_ready() == "s2"


def test_the_s2_gm_state_proof_fails_on_a_wrong_label(lab: Any) -> None:
    gs, s2 = lab.gs, lab.anchors / "s2"
    bank = lab.anchors.parent / "bank"
    held = [(300 + k, k % 2 == 0, k % 3 == 0) for k in range(10)]
    paths = _gm_bank(gs, bank, [(100, True, True), (100, True, False)] + held)
    labels = json.loads((bank / "labels.json").read_text())
    labels[3]["levels"] = "fixed" if labels[3]["levels"] == "not_fixed" else "not_fixed"
    (bank / "labels.json").write_text(json.dumps(labels))
    assert gs.prove([bank], s2)["gm_levels"]["verdict"].startswith("REFUSED")  # nothing cut
    gs.cut_levels(paths[1], s2)
    gs.cut_notices(paths[0], paths[1], s2)
    out = gs.prove([bank], s2)
    assert out["gm_levels"]["verdict"] == "FAIL" and len(out["gm_levels"]["wrong"]) == 1
    assert out["gm_notices"]["verdict"] == "PASS"  # each component on its own bar


def test_the_notices_label_parser(gs: Any) -> None:
    assert gs.parse_notices("none") == []
    assert gs.parse_notices("levelup_icon,badge") == ["badge", "levelup_icon"]
    for bad in ("", "badge,grass", "all"):
        with pytest.raises(ValueError):
            gs.parse_notices(bad)


# --- the loot rule (Batt 2026-10-16: the GM test state only) ---------------------------------


def test_the_weight_rule_clears_at_restore_from_50_and_mid_run_from_40(gs: Any) -> None:
    assert gs.weight_action([1052, 2030], at_restore=True) == "clear"  # 51.8 % (the 10-16 state)
    assert gs.weight_action([130, 2030], at_restore=True) == "ok"
    assert gs.weight_action([900, 2030], at_restore=True) == "ok"  # 44 %: under 50 %
    assert gs.weight_action([900, 2030], at_restore=False) == "clear"  # a run clears from 40 %
    assert gs.weight_action([700, 2030], at_restore=False) == "ok"
    assert gs.weight_action(None, at_restore=True) == "unknown"
    assert gs.weight_share([0, 0]) is None


def test_icons_are_matched_exactly_and_unknown_icons_stay(gs: Any) -> None:
    rng = np.random.default_rng(1)
    shape = (gs.INV_ICON_BOX[3] - gs.INV_ICON_BOX[1], gs.INV_ICON_BOX[2] - gs.INV_ICON_BOX[0])
    loot, kept, other = (rng.uniform(0, 255, shape).astype(np.float32) for _ in range(3))
    refs = {"jellopy": ("loot", loot), "fly_wing": ("kept", kept)}
    assert gs.classify_icon(loot + 1.0, refs)[:2] == ("loot", "jellopy")
    assert gs.classify_icon(kept, refs)[:2] == ("kept", "fly_wing")
    assert gs.classify_icon(other, refs)[0] == "unknown"  # never dropped


def test_only_loot_slots_are_dropped_and_kept_ones_are_skipped(gs: Any) -> None:
    assert gs.next_loot(["kept", "loot", "loot", "empty"]) == 1  # the Fly Wing stays in slot 0
    assert gs.next_loot(["kept", "unknown", "empty"]) is None
    assert gs.next_loot([]) is None


def test_the_icon_crop_never_reaches_the_count_digits(gs: Any) -> None:
    """The count is drawn right of and below the slot centre: the icon box stays left / above."""
    x0, y0, x1, y1 = gs.INV_ICON_BOX
    assert x1 <= 0 and y1 <= 0 and x1 - x0 >= 12 and y1 - y0 >= 12
    frame = np.zeros((720, 1280, 3), np.uint8)
    assert gs.icon_crop(frame, 6, 5).shape == (y1 - y0, x1 - x0)


def test_the_hunt_flow_profile_never_lowers_the_base_level(gs: Any) -> None:
    hf = gs.PROFILES["hunt-flow"]["restore"]
    assert not any(c.startswith("@baselevelup") for c in hf)  # STR's points stay
    assert "@joblevelup -49" in hf and "@heal" in hf
    assert gs.PROFILES["standard"]["restore"] == gs.RESTORE


def test_str_is_read_from_the_novices_weight_cap(gs: Any) -> None:
    """Batt 2026-10-18: the runner rebuilds the hunting state itself. The level lines say nothing
    of STR, so the weight cap does: 2000 + 30 x STR (4970 all of v32-v36; 2030 after @resetstat)."""
    assert gs.str_of_weight_max(4970) == 99 and gs.HUNT_WEIGHT_MAX == 4970
    assert gs.str_of_weight_max(2030) == 1
    assert gs.str_of_weight_max(2000) is None and gs.str_of_weight_max(4971) is None
    assert gs.str_of_weight_max(None) is None
    assert gs.hunting_ok("fixed", [355, 4970])
    assert not gs.hunting_ok("fixed", [355, 2030])  # Lv 70 lines but STR 1: rebuild
    assert not gs.hunting_ok("restore", [355, 4970])  # STR 99 but another level
    assert not gs.hunting_ok("fixed", None)


def test_the_rebuild_frees_every_point_then_lands_on_lv_70(gs: Any) -> None:
    assert gs.REBUILD_UP == ("@resetstat", "@baselevelup -98", "@baselevelup 98")
    assert gs.REBUILD_DOWN == ("@baselevelup -29",)  # 1 + 98 - 29 = 70, the profile's level
    assert 1 + 98 - 29 == 70 and gs.STR_CLICKS == gs.HUNT_STR - 1


def test_the_str_clicks_land_inside_the_status_window_only_after_it_is_found(gs: Any) -> None:
    from poring_env import ui_anchors as ua

    home = ua.CAPTURE_ORIGINS["status"]
    assert gs.status_plus_at(home) == (267, 330)  # the '+' the 2026-10-17 rebuild clicked
    assert tuple(ua.WINDOWS["status"].size) == gs.STATUS_SIZE
    src = Path(gs.__file__).read_text()
    body = src[src.index("def rebuild_hunting(") : src.index("def ensure_hunting(")]
    assert body.index("status_origin(a, reg), status_origin(b, reg)") < body.index("agent.click(")
    assert body.count("agent.click(") == 1  # the '+' only
    assert body.index("agent.click(") < body.index('agent.chord(*ui_gate.window_keys("status"))  #')
    # the re-check after the clicks reads the window with the pointer parked OFF it (the '+''s
    # tooltip covers the title strip: the first live rebuild stopped on it, 09:05)
    after = body[body.index("agent.click(") :]
    assert after.index("ui_gate.PARK[0]") < after.index("status_origin(a, reg) != o1")


def test_status_origin_finds_the_window_at_its_home_and_nothing_else(gs: Any) -> None:
    import ui_gate

    from poring_env import ui_anchors as ua

    if not (ui_gate.r.ROOT / "data" / "ui_anchors" / "status.npy").exists():
        pytest.skip("no status template on this host (client pixels, gitignored)")
    reg = ui_gate._registry("rdp")
    blank = np.full((720, 1280, 3), 60, np.uint8)
    assert gs.status_origin(blank, reg) is None
    spec, tmpl = reg.windows["status"], reg.templates["status"]
    hx, hy = ua.CAPTURE_ORIGINS["status"]
    tx, ty = hx + spec.template_offset[0], hy + spec.template_offset[1]
    frame = blank.copy()
    g = np.clip(tmpl, 0, 255).astype(np.uint8)
    frame[ty : ty + g.shape[0], tx : tx + g.shape[1]] = g[..., None]
    assert gs.status_origin(frame, reg) == (hx, hy)


def test_the_runner_rebuilds_the_hunting_state_before_a_run() -> None:
    src = (SCRIPTS / "hunt_flow.py").read_text()
    assert "gm_state.ensure_hunting(agent_raw, screen" in src
    assert 'why=f"hunt-flow@{version}:before"' in src
