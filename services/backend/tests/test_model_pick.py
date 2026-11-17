"""dungeon@9.59, the box's model among the map's (docs/planning/live-blocks.md 18.15; Batt
2026-11-17, 18.14: "use it for real" -- xmas02sk is xmas_dun02's model, xmas02gb the reference
arm's).

Offline, no game: the box watcher loads the file the box's use_model names (its CPU and GPU
detector, by execution with the detector constructors faked); run() hands the box's file to it;
the proofs: every model-pick change is a branch `if MODEL_PICK:` whose else is 9.58's code, and
BoxWatch's keyword is the family's own -- a use of it outside a branch is refused."""

from __future__ import annotations

import ast
import contextlib
import io
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts"))

import dungeon_hunt as dh  # noqa: E402
import huntstate_check as hc  # noqa: E402
import unit_detector as ud  # noqa: E402

SRC = hc.TARGET.read_text()


def _quiet(f: Any, *a: Any, **k: Any) -> tuple[int, str]:
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        rc = f(*a, **k)
    return int(rc), out.getvalue()


def _base(rev: str) -> str:
    try:
        return hc.git_show(rev, hc.TARGET)
    except (subprocess.CalledProcessError, OSError):
        pytest.skip(f"git cannot show {rev} here (a shallow checkout)")


# --- the box watcher loads the box's file --------------------------------------------------------
class _Det:
    def __init__(self, onnx: str | None, gpu: bool) -> None:
        self.model = Path(onnx or "map-default.onnx")
        self.collapse = {"mystcase": "monster"}
        self.weights = "w"
        self.gpu = gpu
        self.last_ms = 1.0

    def info(self) -> dict[str, str]:
        return {"sha256": "s" * 64}

    def detect(self, img: Any, prefer: str | None = None) -> list[Any]:
        return []

    def close(self) -> None:
        pass


class _Screen:
    def grab(self, *region: int) -> tuple[None, Any]:
        return None, np.zeros((4, 4, 4), np.uint8)


@pytest.mark.parametrize("detector", ["cpu", "gpu"])
def test_the_box_watcher_loads_the_file_the_box_names(
    detector: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[tuple[str, str | None, str | None]] = []

    def cpu(map_name: str | None, **kw: Any) -> _Det:
        calls.append(("cpu", map_name, kw.get("onnx")))
        return _Det(kw.get("onnx"), False)

    def gpu(map_name: str | None, **kw: Any) -> _Det:
        calls.append(("gpu", map_name, kw.get("onnx")))
        return _Det(kw.get("onnx"), True)

    monkeypatch.setattr(ud, "for_map", cpu)
    monkeypatch.setattr(ud, "for_map_gpu", gpu)
    r = SimpleNamespace(Screen=_Screen)
    ref = ud.MAP_REFERENCES["xmas_dun02"][0].onnx
    for model_file in (None, ref):
        bw = dh.BoxWatch(None, (0, 0, 4, 4), r, "xmas_dun02", detector, 60.0,
                         model_file=model_file)  # fmt: skip
        bw.halt.set()
        bw.th.join(timeout=5)
        assert bw.model["onnx"] == (model_file or "map-default.onnx")
    assert calls == [(detector, "xmas_dun02", None), (detector, "xmas_dun02", ref)]


def test_run_hands_the_box_files_to_the_box_watcher() -> None:
    """run()'s one BoxWatch call under MODEL_PICK passes the box's use_model's file (never with
    --box-model v1, which box_model_refused refuses before any input anyway); its else is 9.58's."""
    run = next(n for n in ast.parse(SRC).body if isinstance(n, ast.FunctionDef) and n.name == "run")
    picks = [
        n for n in ast.walk(run) if isinstance(n, ast.If) and ast.unparse(n.test) == "MODEL_PICK"
    ]
    assert len(picks) == 1
    (call,) = [c for c in ast.walk(picks[0].body[0]) if isinstance(c, ast.Call)
               and ast.unparse(c.func) == "BoxWatch"]  # fmt: skip
    kw = {k.arg: ast.unparse(k.value) for k in call.keywords}
    assert kw == {"model_file": "None if box_model_ is None or a.box_model == 'v1' else "
                                "str(box_model_['file'])"}  # fmt: skip
    (other,) = [c for c in ast.walk(picks[0].orelse[0]) if isinstance(c, ast.Call)
                and ast.unparse(c.func) == "BoxWatch"]  # fmt: skip
    assert not other.keywords and [ast.unparse(x) for x in other.args] == [
        ast.unparse(x) for x in call.args
    ]


def test_the_runner_takes_the_maps_own_or_its_reference_by_the_box_file() -> None:
    own, (ref,) = ud.MAP_MODELS["xmas_dun02"], ud.MAP_REFERENCES["xmas_dun02"]

    def doc(m: ud.MapModel, mid: str) -> dict[str, Any]:
        return {"id": mid, "file": m.onnx, "sha256": m.sha256[:12], "maps": ["xmas_dun02"],
                "status": "live", "kind": "detector", "strikes": list(m.collapse)}  # fmt: skip

    assert dh.MODEL_PICK is True and dh.MODEL_PICK_VERSION == "9.59"
    for m, mid in ((own, "xmas02sk"), (ref, "xmas02")):
        assert dh.box_model_refused(doc(m, mid), "xmas_dun02") is None
        assert ud.GPU_WEIGHTS[str(m.gpu)].onnx == m.onnx  # the detect server serves its weights
    bad = dh.box_model_refused({**doc(ref, "xmas02"), "sha256": own.sha256[:12]}, "xmas_dun02")
    assert bad is not None and "is not a model the runner's box detector loads" in bad


# --- the proofs ----------------------------------------------------------------------------------
def test_every_model_pick_change_is_a_branch_whose_else_is_958s_code() -> None:
    text, n = hc.unpick(SRC)
    assert n == 5 and "MODEL_PICK" not in text and "model_file" not in text
    rc, out = _quiet(hc.pick_check, _base(hc.PICK_BASE), SRC)
    assert rc == 0 and "the module == the base's (as ASTs): YES" in out, out
    # the older proofs read the family as its else too, so each still means what it meant
    rc_f, out_f = _quiet(hc.flag_check, _base(hc.FLAG_BASE), SRC)
    assert rc_f == 0 and "model-pick branches read as their else (live-blocks 18.15): 5" in out_f
    rc_d, out_d = _quiet(hc.drive_check, _base(hc.DRIVE_BASE), SRC)
    rc_c, out_c = _quiet(hc.check, _base(hc.BASE_REV), SRC, drive_ok=True)
    assert rc_d == 0 and rc_c == 0, out_d + out_c
    assert "model-pick branches read as their else (live-blocks 18.15): 5" in out_d + out_c


def test_a_change_outside_the_branches_or_a_stray_keyword_is_refused() -> None:
    base = _base(hc.PICK_BASE)
    old = '        self.gpu = detector != "cpu"\n'
    assert SRC.count(old) == 1
    stray = SRC.replace(old, '        self.gpu = detector != "cpu" and model_file is None\n')
    assert _quiet(hc.pick_check, base, stray)[0] == 1  # the keyword used outside a branch
    bent = SRC.replace('MODEL_PICK_VERSION = "9.59"', 'MODEL_PICK_VERSION = "9.59"\nX_ = 1', 1)
    assert _quiet(hc.pick_check, base, bent)[0] == 1  # a statement outside the family
    # the keyword itself: dropped only from signatures, only with a None default
    toy = "def f(a, *, model_file=None, k=1):\n    return a\n"
    assert hc.unflag(toy, hc.MODEL_PICK_TESTS, hc.MODEL_PICK_ADDED, hc.MODEL_PICK_PARAMS)[0] == (
        "def f(a, *, k=1):\n    return a"
    )
    with pytest.raises(ValueError, match="no None default"):
        hc.unflag("def f(*, model_file=1):\n    return 0\n", (), (), ("model_file",))
