"""xmas02-items-1080.md Amendment 26: the model's own false boxes as hard negatives (pure parts)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts"))

import fi_hard_negs as hn  # noqa: E402

SID = "20261121T183716-rdp-xmas02-ifH8"


def frame(fid: int, **kw: object) -> dict[str, object]:
    return {"frame_id": fid, "status": "keep", "items": [], "n_near": 0,
            "shard": "shard-000001.tar", "offset": 512 * fid, "size": 100, **kw}  # fmt: skip


def test_only_strictly_item_free_frames_count() -> None:
    assert hn.item_free(frame(1))
    assert not hn.item_free(frame(2, status="exclude"))
    assert not hn.item_free(frame(3, items=[{"floor_id": 1}]))
    assert not hn.item_free(frame(4, n_near=1))  # an item near, even unlabelled
    assert not hn.item_free(frame(5, floor=[7]))  # an item on the floor in some phase
    assert hn.item_free(frame(6, floor=[]))


def test_refs_and_mining(tmp_path: Path) -> None:
    doc = {"session": SID, "frames": [frame(1), frame(2), frame(3, n_near=1), frame(4)]}
    refs = hn.refs_of([doc])
    assert sorted(refs) == [f"{SID}.000000001", f"{SID}.000000002", f"{SID}.000000004"]
    assert refs[f"{SID}.000000002"] == {"path": f"/datasets/{SID}/shard-000001.tar",
                                        "offset": 1024, "size": 100}  # fmt: skip
    box = {"cls": "floor_item", "x1": 1, "y1": 1, "x2": 9, "y2": 9}
    pred = {"frames": {f"{SID}.000000001": [{**box, "conf": 0.31}],
                       f"{SID}.000000002": [{**box, "conf": 0.2}],
                       f"{SID}.000000003": [{**box, "conf": 0.9}],  # an item near: never hard
                       f"{SID}.000000004": []}}  # fmt: skip
    got = hn.mine([doc], [pred])
    assert got["sessions"] == {SID: [1]} and (got["item_free"], got["predicted"], got["hard"]) == (
        3, 3, 1)  # fmt: skip
    assert hn.mine([doc], [pred], conf=0.15)["sessions"] == {SID: [1, 2]}
    mon = {"frames": {f"{SID}.000000004": [{**box, "cls": "monster", "conf": 0.9}]}}
    assert hn.mine([doc], [mon])["sessions"] == {}  # only the item class counts
    other = {"frames": {f"{SID}.000000004": [{**box, "conf": 0.5}]}}  # a second set adds its own
    assert hn.mine([doc], [pred, other])["sessions"] == {SID: [1, 4]}
    lab, p1 = tmp_path / "l.json", tmp_path / "p.json"
    lab.write_text(json.dumps(doc))
    p1.write_text(json.dumps(pred))
    assert hn.main(["mine", "--labels", str(lab), "--predictions", str(p1), "--out",
                    str(tmp_path / "h.json")]) == 0  # fmt: skip
    assert json.loads((tmp_path / "h.json").read_text())["sessions"] == {SID: [1]}
