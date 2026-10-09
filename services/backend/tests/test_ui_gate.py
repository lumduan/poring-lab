"""scripts/ui_gate.py (Batt 2026-10-09, walk@17 item 6): the pure decision -- no Enter into an
unknown state; only a dialog showing CLOSE (no menu) is closed by Enter, a window by its chord;
NEXT, a menu, an unreadable or unstable state stop -- and the home-box window check."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

import numpy as np
import pytest

SCRIPTS = Path(__file__).resolve().parents[2].parent / "scripts"


@pytest.fixture(scope="module")
def ug() -> ModuleType:
    sys.path.insert(0, str(SCRIPTS))
    spec = importlib.util.spec_from_file_location("ui_gate", SCRIPTS / "ui_gate.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["ui_gate"] = mod
    spec.loader.exec_module(mod)
    return mod


def obs(ok: bool = True, dialog: Any = None, menu: Any = None, windows: tuple[str, ...] = (),
        sig: str = "s", reason: str = "ok") -> dict[str, Any]:  # fmt: skip
    npc: dict[str, Any] = {"ok": ok, "reason": reason, "sig": sig}
    if dialog is not None:
        npc["dialog"] = {"button": dialog}
    if menu is not None:
        npc["menu"] = menu
    return {"npc": npc, "windows": list(windows)}


def test_clear_only_when_both_frames_agree_and_nothing_is_open(ug: Any) -> None:
    assert ug.decide(obs(), obs()) == {"do": "clear"}
    assert ug.decide(obs(sig="a"), obs(sig="b"))["why"] == "unstable"
    assert ug.decide(obs(windows=("inventory",)), obs())["why"] == "unstable"
    assert ug.decide(obs(ok=False, reason="button_unknown"), obs())["why"] == (
        "npc_unreadable:button_unknown"
    )


def test_only_a_close_button_is_closed_by_enter(ug: Any) -> None:
    assert ug.decide(obs(dialog="close"), obs(dialog="close")) == {"do": "enter_close"}
    assert ug.decide(obs(dialog="next"), obs(dialog="next"))["why"] == "npc_dialog_open:next"
    assert ug.decide(obs(dialog=None, menu={}), obs(menu={}))["why"] == "npc_menu_open"
    both = obs(dialog="close", menu={})
    assert ug.decide(both, both)["why"] == "npc_menu_open"  # a menu is never closed by Enter
    blank = {"npc": {"ok": True, "reason": "ok", "sig": "s", "dialog": {"button": None}},
             "windows": []}  # fmt: skip
    assert ug.decide(blank, blank)["why"] == "npc_dialog_open:no_button"


def test_a_window_is_closed_by_its_chord_after_the_npc_check(ug: Any) -> None:
    two = obs(windows=("skills", "inventory"))
    assert ug.decide(two, two) == {"do": "chord", "window": "inventory"}
    mixed = obs(dialog="next", windows=("inventory",))
    assert ug.decide(mixed, mixed)["do"] == "stop"  # the dialog first: never a key into it


def test_a_window_is_seen_only_at_its_home(ug: Any) -> None:
    from poring_env import ui_anchors as ua

    rng = np.random.default_rng(3)
    tmpl = rng.integers(0, 255, (20, 30)).astype(np.float32)
    spec = SimpleNamespace(template_offset=(0, 0), max_distance=4.0)
    reg = SimpleNamespace(windows={w: spec for w in ug.WINDOWS4},
                          templates={"inventory": tmpl}, masks={})  # fmt: skip
    hx, hy = ua.CAPTURE_ORIGINS["inventory"]
    frame = np.full((720, 1280, 3), 40, np.uint8)
    for dx, want in ((5, ["inventory"]), (ug.HOME_PX + 25, [])):
        f = frame.copy()
        f[hy : hy + 20, hx + dx : hx + dx + 30] = tmpl.astype(np.uint8)[..., None]
        assert ug.windows_at_home(f, reg) == want, dx


# --- per path (2026-10-09, poring_env.ui_sets): rdp unchanged; console only with a PROVEN S2 set


def _windows(root: Path, seed: int) -> dict[str, np.ndarray]:
    """Synthetic title-text templates for the four windows, saved under ``root``."""
    from poring_env import ui_anchors as ua

    rng = np.random.default_rng(seed)
    out = {}
    for w in ("status", "skills", "inventory", "equipment"):
        tw, th = ua.WINDOWS[w].template_size or (0, 0)
        out[w] = (rng.random((th, tw)) * 255).astype(np.float32)
    ua.save_templates(root, out, {w: np.ones_like(t) for w, t in out.items()})
    return out


def _dialog_set(root: Path, seed: int, drop: tuple[str, ...] = ()) -> None:
    """Synthetic T2 templates (every name the reader loads), saved under ``root/npc_dialog``."""
    from poring_env import npc_dialog as nd

    rng = np.random.default_rng(seed)
    names = (*nd.WINDOW_NAMES, *nd.BUTTON_NAMES, *nd.ARROW_NAMES)
    images = {n: rng.random((4, 4)).astype(np.float32) for n in names if n not in drop}
    nd.DialogTemplates(images, meta={"seed": seed}).save(root / "npc_dialog")


@pytest.fixture()
def lab(ug: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Any:
    """ug with its ROOT in tmp_path, the lock's backend settable, and an empty cache."""
    state = {"backend": "rdp"}
    monkeypatch.setattr(ug.r, "ROOT", tmp_path)
    monkeypatch.setattr(ug, "_lock_backend", lambda: state["backend"])
    monkeypatch.setattr(ug, "_cache", {})
    monkeypatch.setattr(ug, "LOG", tmp_path / "ui_gate.jsonl")
    return SimpleNamespace(ug=ug, root=tmp_path / "data" / "ui_anchors", state=state)


def _prove_s2(root: Path, *components: str) -> None:
    from poring_env import ui_sets

    for c in components:
        before = ui_sets.file_hashes(root, c)
        assert ui_sets.record(root, c, True, {}, before, command="test")["verdict"] == "PASS"


def test_rdp_is_unchanged_and_needs_no_proof(lab: Any) -> None:
    ug, root = lab.ug, lab.root
    _dialog_set(root, 1, drop=("npc_menu_ok",))
    with pytest.raises(ug.UiUnknown) as e:
        ug._require_ready()
    assert str(e.value) == ("ui gate: no NPC dialog templates (npc_menu_ok; talk@1 cut): "
                            "nothing typed")  # fmt: skip
    lab.ug._cache.clear()
    _dialog_set(root, 1)
    with pytest.raises(ug.UiUnknown) as e:
        ug._require_ready()
    assert str(e.value) == "ui gate: a window anchor is missing (data/ui_anchors): nothing typed"
    lab.ug._cache.clear()
    _windows(root, 2)
    (root / "s2").mkdir()
    (root / "s2" / "proof.json").write_text("{broken")  # another path's set never matters here
    assert ug._require_ready() == "rdp"
    assert not (root / "proof.json").exists()
    assert ug._templates("rdp").meta == {"seed": 1}  # read from data/ui_anchors/npc_dialog
    assert "status" in ug._registry("rdp").templates


def test_an_unknown_backend_refuses(lab: Any) -> None:
    _dialog_set(lab.root, 1)
    _windows(lab.root, 2)
    for backend in ("hold", "", "moonlight"):
        lab.state["backend"] = backend
        with pytest.raises(lab.ug.UiUnknown, match="no template set for the lock's"):
            lab.ug._require_ready()


def test_console_needs_a_complete_proven_s2_set(lab: Any) -> None:
    ug, root = lab.ug, lab.root
    _dialog_set(root, 1)  # a complete RDP set: never used for console
    _windows(root, 2)
    lab.state["backend"] = "console"
    with pytest.raises(ug.UiUnknown, match="not proven .*no valid proof.json"):
        ug._require_ready()  # no S2 set at all
    s2 = root / "s2"
    _dialog_set(s2, 7)
    _windows(s2, 8)
    with pytest.raises(ug.UiUnknown, match="not proven"):
        ug._require_ready()  # present, unproven
    _prove_s2(s2, "windows")
    with pytest.raises(ug.UiUnknown, match="t2: not proven"):
        ug._require_ready()  # half proven
    _prove_s2(s2, "t2")
    assert ug._require_ready() == "s2"
    assert ug._templates("s2").meta == {"seed": 7}  # the S2 set, not the RDP one
    s2_status = ug._registry("s2").templates["status"]
    assert not np.array_equal(s2_status, ug._registry("rdp").templates["status"])
    # a template edited after the proof: refused, and nothing cached is used
    np.save(s2 / "status.npy", s2_status + 1)
    with pytest.raises(ug.UiUnknown, match=r"windows: stale since the proof \(status.npy\)"):
        ug._require_ready()
    lab.state["backend"] = "rdp"  # the RDP path is not affected by the S2 set's state
    assert ug._require_ready() == "rdp"


def test_a_reproven_s2_set_is_reloaded(lab: Any) -> None:
    ug, s2 = lab.ug, lab.root / "s2"
    lab.state["backend"] = "console"
    _dialog_set(s2, 7)
    _windows(s2, 8)
    _prove_s2(s2, "windows", "t2")
    assert ug._require_ready() == "s2" and ug._templates("s2").meta == {"seed": 7}
    _dialog_set(s2, 9)  # re-cut ...
    _prove_s2(s2, "t2")  # ... and re-proven
    assert ug._require_ready() == "s2" and ug._templates("s2").meta == {"seed": 9}


def test_ensure_clear_reads_with_the_locks_path(lab: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    ug, s2 = lab.ug, lab.root / "s2"
    lab.state["backend"] = "console"
    _dialog_set(s2, 7)
    _windows(s2, 8)
    _prove_s2(s2, "windows", "t2")
    seen: list[str] = []

    def fake_observe(agent: Any, screen: Any, after: Any, k: int, park: bool = True, *,
                     path: str) -> tuple[dict[str, Any], Any]:  # fmt: skip
        seen.append(path)
        return obs(), None

    monkeypatch.setattr(ug, "observe", fake_observe)
    got = ug.ensure_clear(None, None, why="test")
    assert got["clear"] and seen == ["s2", "s2"]
    lab.state["backend"] = "hold"
    with pytest.raises(ug.UiUnknown):
        ug.ensure_clear(None, None, why="test")
    assert seen == ["s2", "s2"]  # refused before any frame was read


# --- the S2 windows: cut and prove offline on banked frames (synthetic) ---------------------------


def _bank(ug: Any, bank: Path, tmpls: dict[str, np.ndarray], rounds: range, seed: int,
          wrong: bool = False) -> None:  # fmt: skip
    """Frames as bank-windows writes them: per round and window, 2 closed, 3 open, 2 closed."""
    from PIL import Image

    from poring_env import ui_anchors as ua

    rng = np.random.default_rng(seed)
    (bank / "frames").mkdir(parents=True, exist_ok=True)
    labels = []
    for rnd in rounds:
        for w in ug.WINDOWS4:
            for tag, opened, n in (("before", None, 2), ("open", w, 3), ("after", None, 2)):
                for _ in range(n):  # a blocky scene (fast PNGs), big enough for the four homes
                    img = np.kron(rng.random((45, 80)) * 255, np.ones((8, 8))).astype(np.float32)
                    if opened is not None:
                        hx, hy = ua.CAPTURE_ORIGINS[opened]
                        tx, ty = ua.WINDOWS[opened].template_offset
                        t = tmpls[opened] + rng.normal(0, 1.0, tmpls[opened].shape)  # codec noise
                        th, tw = t.shape
                        img[hy + ty : hy + ty + th, hx + tx : hx + tx + tw] = t
                    name = f"{rnd:02d}-{w}-{tag}-{len(labels)}.png"
                    gray = np.clip(img, 0, 255).astype(np.uint8)
                    Image.fromarray(np.stack([gray] * 3, -1)).save(bank / "frames" / name)
                    label = ("skills" if opened == "status" else opened) if wrong else opened
                    labels.append({"file": name, "open": label, "round": rnd, "scene": "syn",
                                   "path": "s2", "t_ns": len(labels)})  # fmt: skip
    (bank / "labels.json").write_text(json.dumps(labels))


def test_the_s2_windows_cut_and_offline_proof(ug: Any, tmp_path: Path) -> None:
    from poring_env import ui_sets

    rng = np.random.default_rng(4)
    tmpls = {w: (rng.random((13, 60)) * 255).astype(np.float32) for w in ug.WINDOWS4}
    bank = tmp_path / "bank"
    _bank(ug, bank, tmpls, range(0, 3), seed=5)
    root = tmp_path / "s2"
    rep = ug.cut_windows([bank], {0}, root)
    assert rep["verdict"].startswith("CUT") and rep["frames"] == {w: 3 for w in ug.WINDOWS4}
    assert all((root / f"{w}.npy").exists() and (root / f"{w}_mask.npy").exists()
               for w in ug.WINDOWS4)  # fmt: skip
    res = ug.prove_windows_offline([bank], root, full=False)
    assert res["verdict"] == "PASS", res
    assert res["excluded_cut"] == 28 and res["held_out"] == 2 * 28  # the cut's whole round out
    assert res["own_max"] <= 3.0 and res["other_min"] >= 12.0
    before = res.pop("before")
    ui_sets.record(root, "windows", res["pass"], res, before, command="test")
    assert ui_sets.problems(root, ["windows"]) == []


def test_the_s2_windows_proof_fails_on_wrong_labels_or_too_few(ug: Any, tmp_path: Path) -> None:
    rng = np.random.default_rng(4)
    tmpls = {w: (rng.random((13, 60)) * 255).astype(np.float32) for w in ug.WINDOWS4}
    good, bad = tmp_path / "good", tmp_path / "bad"
    _bank(ug, good, tmpls, range(0, 1), seed=5)
    _bank(ug, bad, tmpls, range(1, 2), seed=6, wrong=True)  # status frames labelled skills
    root = tmp_path / "s2"
    assert ug.cut_windows([good], {0}, root)["verdict"].startswith("CUT")
    res = ug.prove_windows_offline([good, bad], root, full=False)
    assert res["verdict"] == "FAIL" and not res["pass"]
    assert any("own skills" in why for f in res["fails"] for why in f["why"])
    few = ug.prove_windows_offline([good], root, full=False)  # only the cut's own frames
    assert few["verdict"].startswith("INCOMPLETE") and few["held_out"] == 0
    assert ug.cut_windows([good], {5}, tmp_path / "none")["verdict"].startswith("NOT READY")
    assert not (tmp_path / "none").exists()


def test_a_frame_is_judged_on_own_and_others_margins(ug: Any) -> None:
    spec = SimpleNamespace(max_distance=6.0)
    reg = SimpleNamespace(windows={w: spec for w in ug.WINDOWS4})
    far = {w: 30.0 for w in ug.WINDOWS4}
    assert ug.judge_frame(far, None, reg, []) == []
    assert ug.judge_frame({**far, "status": 1.0}, "status", reg, ["status"]) == []
    assert ug.judge_frame({**far, "status": 4.0}, "status", reg, None) == [
        "own status 4.00 > 3.00"
    ]  # accepted by the gate (<= 6) but not by the proof's margin
    near = {**far, "status": 1.0, "equipment": 11.0}  # the window sharing status's home
    assert ug.judge_frame(near, "status", reg, None) == ["other equipment 11.00 < 12.00"]
    assert ug.judge_frame(far, None, reg, ["skills"]) == ["full-frame ['skills'] != []"]
