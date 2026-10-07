"""scripts/vlm_flag.py: qwen3-vl as a label-QA FLAGGER (phase3-plan §6, pre-registered b9d3aee)."""

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType

import pytest

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "vlm_flag.py"


@pytest.fixture(scope="module")
def vf() -> ModuleType:
    spec = importlib.util.spec_from_file_location("vlm_flag", SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["vlm_flag"] = mod
    spec.loader.exec_module(mod)
    return mod


def row(truth: str, said: bool, crop: str = "tight", species: str = "poring") -> dict:
    return {"truth": truth, "crop": crop, "species": species if truth == "monster" else "none",
            "seconds": 1.0, "digest": "d", "prompt_sha256": "p",
            "answer": {"monster": said, "species": species, "occluded": False, "under_ui": False,
                       "dead": False}}  # fmt: skip


def test_the_pre_registered_bar(vf: ModuleType, tmp_path: Path,
                                capsys: pytest.CaptureFixture[str]) -> None:  # fmt: skip
    rows = [row("monster", True)] * 9 + [row("monster", False)] + [row("empty", False)] * 9
    rows += [row("empty", True)]  # recall 0.90, false-monster 0.10: exactly at the bar -> useful
    rows += [row("monster", True, "context50")] * 8 + [row("monster", False, "context50")] * 2
    rows += [row("empty", False, "context50")] * 10  # recall 0.80 -> not useful
    out = tmp_path / "a.jsonl"
    out.write_text("".join(json.dumps(r) + "\n" for r in rows))
    assert vf.score(out) == 0
    res = json.loads(capsys.readouterr().out)
    assert res["tight"]["useful_as_flagger"] is True
    assert res["context50"]["useful_as_flagger"] is False
    assert res["tight"]["species_accuracy"] == {"poring": 1.0}


def test_it_refuses_a_model_that_is_not_the_licence_checked_one(
    vf: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(vf.frigate_r3, "prestart", lambda *a, **k: None)
    monkeypatch.setattr(vf.frigate_r3, "fetch_json",
                        lambda url: {"models": [{"name": vf.MODEL, "digest": "abc"}]})  # fmt: skip
    assert "digest abc" in vf.gate()
    monkeypatch.setattr(vf.frigate_r3, "prestart", lambda *a, **k: "R2: Ollama has a model loaded")
    assert vf.gate().startswith("R2")


def test_crops_stay_inside_the_frame_and_grow_by_the_context(vf: ModuleType) -> None:
    from PIL import Image

    img = Image.new("RGB", (100, 50))
    tight = Image.open(__import__("io").BytesIO(vf.crop_png(img, (10, 10, 30, 20), 0.0)))
    wide = Image.open(__import__("io").BytesIO(vf.crop_png(img, (10, 10, 30, 20), 0.5)))
    edge = Image.open(__import__("io").BytesIO(vf.crop_png(img, (0, 0, 20, 10), 0.5)))
    assert tight.size == (20, 10) and wide.size == (40, 20) and edge.size == (30, 15)
