#!/usr/bin/env python3
"""xmas02-items-1080.md Amendment 26 (round 8): the item model's OWN false boxes as hard negatives.

    fi_hard_negs.py refs LABELS.json... --out REFS.json
        the item-free frames' refs (fi_onnx_pred.py's input; paths as the worker sees the NAS)
    fi_hard_negs.py mine --labels LABELS.json... --predictions PRED.json... [--conf 0.25]
                         --out HARD.json
        every item-free frame on which an item box scored >= --conf: build_frame_cache --hard-negs

An ITEM-FREE frame (fi_eval.i3's frames, so a real item the labels left out is never taught as
background): kept, no item label, no floor item near (n_near 0) and, where the label file records
it (--eval-test files), no floor item in any phase. The cache then writes each listed frame that
its TRAIN labels keep item-free; the rest are counted, not written.

Label files and predictions are local inputs (never committed); nothing here reads a picture.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fi_eval as fe  # noqa: E402

CONTAINER_ROOT = "/datasets"  # the worker's NAS mount (eval_latency.host_path maps it back)


def item_free(f: Mapping[str, Any]) -> bool:
    """PURE: a kept frame with no item label, no floor item near, and (when recorded) none on
    the floor in any phase."""
    return (f.get("status") == "keep" and not f.get("items") and f.get("n_near") == 0
            and not f.get("floor"))  # fmt: skip


def refs_of(docs: Sequence[Mapping[str, Any]], root: str = CONTAINER_ROOT) -> dict[str, Any]:
    """PURE: predict_dir / fi_onnx_pred refs of every item-free frame, keyed as fi_eval's."""
    out: dict[str, Any] = {}
    for d in docs:
        sid = str(d["session"])
        for f in d["frames"]:
            if item_free(f):
                out[fe.frame_key(sid, f["frame_id"])] = {
                    "path": f"{root.rstrip('/')}/{sid}/{f['shard']}",
                    "offset": int(f["offset"]),
                    "size": int(f["size"]),
                }
    return out


def mine(docs: Sequence[Mapping[str, Any]], preds: Sequence[Mapping[str, Any]],
         conf: float = fe.CONF) -> dict[str, Any]:  # fmt: skip
    """PURE: {"sessions": {sid: [frame ids]}, counts}: the item-free frames that some prediction
    set boxed an item on at >= ``conf`` (a frame no set predicted on is not a hard negative)."""
    frames: dict[str, Sequence[Mapping[str, Any]]] = {}
    for p in preds:
        for k, dets in p["frames"].items():
            frames.setdefault(k, [])
            frames[k] = [*frames[k], *dets]
    out: dict[str, list[int]] = {}
    free = predicted = 0
    for d in docs:
        sid = str(d["session"])
        for f in d["frames"]:
            if not item_free(f):
                continue
            free += 1
            dets = frames.get(fe.frame_key(sid, f["frame_id"]))
            if dets is None:
                continue
            predicted += 1
            if any(x.get("cls") == fe.CLASS and float(x.get("conf", 0.0)) >= conf for x in dets):
                out.setdefault(sid, []).append(int(f["frame_id"]))
    return {"sessions": {s: sorted(v) for s, v in sorted(out.items())}, "conf": conf,
            "item_free": free, "predicted": predicted,
            "hard": sum(len(v) for v in out.values())}  # fmt: skip


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("refs")
    r.add_argument("labels", type=Path, nargs="+")
    r.add_argument("--container-root", default=CONTAINER_ROOT)
    r.add_argument("--out", type=Path, required=True)
    m = sub.add_parser("mine")
    m.add_argument("--labels", type=Path, nargs="+", required=True)
    m.add_argument("--predictions", type=Path, nargs="+", required=True)
    m.add_argument("--conf", type=float, default=fe.CONF)
    m.add_argument("--out", type=Path, required=True)
    a = ap.parse_args(argv)
    docs = [json.loads(p.read_text()) for p in a.labels]
    if a.cmd == "refs":
        got = refs_of(docs, a.container_root)
        a.out.write_text(json.dumps(got, indent=0))
        print(json.dumps({"refs": str(a.out), "frames": len(got)}))
        return 0
    doc = mine(docs, [json.loads(p.read_text()) for p in a.predictions], a.conf)
    doc["labels"] = [str(p) for p in a.labels]
    doc["predictions"] = [str(p) for p in a.predictions]
    a.out.write_text(json.dumps(doc, indent=1))
    print(json.dumps({k: doc[k] for k in ("conf", "item_free", "predicted", "hard")}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
