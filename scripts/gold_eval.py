#!/usr/bin/env python3
"""M10: a model against Batt's hand-checked gold set (model-vs-hand), scored exactly like B6's
auto-vs-hand (scripts/label_iou.py: the same per-class greedy match at IoU >= 0.5).

    gold_eval.py extract SESSION              the hand-checked frames -> data/train/eval/gold/
                                              SESSION/frames/<frame_id>.png (+ index.json:
                                              frame_id -> t_mono_ns); vision sees /data/...
    gold_eval.py score SESSION PRED.json ...  per run: per class + overall TP/FP/FN, P, R, mean IoU

PRED.json comes from `python -m poring_vision.predict_dir` in the vision container (GPU, guarded).
The frames are client-derived pixels: they stay in data/ (gitignored), never committed.
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import label_iou  # noqa: E402

from poring_dataset.shards import encode_png, read_shard  # noqa: E402

NAS = Path("/mnt/poring-lab-datasets")
OUT = ROOT / "data" / "train" / "eval" / "gold"


def hand_of(session: str) -> dict[str, Any]:
    return json.loads((label_iou.HANDCHECK / f"{session}.json").read_text())  # type: ignore[no-any-return]


def extract(session: str, datasets: Path) -> int:
    hand = hand_of(session)
    want = {int(f["frame_id"]) for f in hand["frames"]}
    src = datasets / session
    manifest = json.loads((src / "manifest.json").read_text())
    dest = OUT / session / "frames"
    dest.mkdir(parents=True, exist_ok=True)
    index: dict[str, int] = {}
    if (manifest.get("format") or "png") == "h264":
        from poring_dataset.h264 import H264Session

        pairs = H264Session(src).frames(sorted(want))
    else:
        pairs = (pi for shard in manifest["shards"] for pi in read_shard(src / shard))
    for meta, img in pairs:
        fid = int(meta["frame_id"])
        if fid not in want or str(fid) in index:
            continue
        (dest / f"{fid}.png").write_bytes(encode_png(img))
        index[str(fid)] = int(meta["t_mono_ns"])
        if len(index) == len(want):
            break
    (OUT / session / "index.json").write_text(json.dumps(index, indent=1))
    missing = sorted(want - {int(k) for k in index})
    print(json.dumps({"session": session, "frames": len(index), "missing": missing,
                      "dir": str(dest)}))  # fmt: skip
    return 1 if missing else 0


def score(session: str, preds: list[Path]) -> int:
    hand = hand_of(session)
    index = json.loads((OUT / session / "index.json").read_text())
    by_t = {int(t): fid for fid, t in index.items()}
    out = {}
    for path in preds:
        p = json.loads(path.read_text())
        frames = p["frames"]
        result = label_iou.score(hand, lambda t, f=frames: f.get(by_t.get(t, ""), None))
        out[p["weights"]] = {"conf": p["conf"], "imgsz": p["imgsz"], **result}
    print(json.dumps(out, indent=1))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    ex = sub.add_parser("extract")
    ex.add_argument("session")
    ex.add_argument("--datasets", type=Path, default=NAS)
    sc = sub.add_parser("score")
    sc.add_argument("session")
    sc.add_argument("preds", type=Path, nargs="+")
    a = ap.parse_args()
    if a.cmd == "extract":
        return extract(a.session, a.datasets)
    return score(a.session, a.preds)


if __name__ == "__main__":
    sys.exit(main())
