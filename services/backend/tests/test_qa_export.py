"""scripts/qa_export.py end to end on a synthetic recorded session (no X, no Windows, no docker)."""

import gzip
import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType

import numpy as np
import pytest

from poring_dataset import mapcache
from poring_dataset.shards import ShardWriter, write_manifest

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "qa_export.py"
T0 = 700_000_000_000_000_000

pytestmark = pytest.mark.skipif(
    not (mapcache.GENERATED / "map_cache.base.dat").exists(), reason="run scripts/gen_mapcache.py"
)


@pytest.fixture
def qa(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    spec = importlib.util.spec_from_file_location("qa_export", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    camera = tmp_path / "camera.json"
    h = [[30.0, 0, 392.0], [0, -30.0, 330.0], [0, 0, 1.0]]
    camera.write_text(json.dumps({"h": h}))
    monkeypatch.setattr(module, "CAMERA", camera)
    monkeypatch.setattr(module, "BUNDLES", tmp_path / "bundles")
    return module


def session(tmp_path: Path) -> Path:
    out = tmp_path / "sess"
    writer = ShardWriter(out)
    for i in range(6):
        writer.add(i, T0 + i * 100_000_000, np.full((625, 784, 3), 40 + i, np.uint8))
    writer.close()
    ms = 1_000_000
    events = [
        {"t_mono_ns": T0 - 1000 * ms, "type": "map_change", "map": "prt_fild08", "x": 170,
         "y": 375},
        {"t_mono_ns": T0 - 900 * ms, "type": "entity_appear", "kind": "new", "gid": 7, "char_id": 0,
         "objtype": 5, "job": 1002, "speed": 400, "name": "Poring", "x": 172, "y": 375},
    ]  # fmt: skip
    with gzip.open(out / "packets.jsonl.gz", "wt") as fh:
        for e in events:
            fh.write(json.dumps(e) + "\n")
    write_manifest(out, {"session_id": "s1", "backend": "rdp", "game_region": [248, 99, 784, 625],
                         "shards": writer.shards})  # fmt: skip
    return out


def test_bundle_has_frames_labels_and_index(
    qa: ModuleType,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    sheet = tmp_path / "sheet.png"
    monkeypatch.setattr(sys, "argv", ["qa_export.py", str(session(tmp_path)), "--every", "2",
                                      "--offset-ms", "120", "--sheet", str(sheet)])  # fmt: skip
    assert qa.main() == 0
    bundle = tmp_path / "bundles" / "s1"
    labels = json.loads((bundle / "labels.json").read_text())
    assert labels["offset_ms"] == 120 and len(labels["frames"]) == 3  # every 2nd of 6
    box = labels["frames"][0]["boxes"][0]
    assert box["cls"] == "monster" and box["gid"] == 7
    assert (box["x1"] + box["x2"]) / 2 == pytest.approx(392 + 60)  # 2 cells right at 30 px/cell
    index = json.loads((tmp_path / "bundles" / "index.json").read_text())
    assert index["sessions"] == [{"id": "s1", "title": "s1 (rdp)", "frames": 3}]
    assert sheet.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
    assert json.loads(capsys.readouterr().out)["with_boxes"] == 3
