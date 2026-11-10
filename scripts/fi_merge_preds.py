#!/usr/bin/env python3
"""ONE prediction set (predict_dir's format) from several runs of the SAME weights on disjoint
refs (xmas02-detector.md O15: the staged held-out first, the pilots' later), for fi_eval.py.

    fi_merge_preds.py OUT.json IN1.json IN2.json ...

Refuses differing weights or a frame key in two inputs. Nothing is changed in any prediction.
"""

import json
import sys
from pathlib import Path


def main() -> int:
    out, ins = Path(sys.argv[1]), [Path(p) for p in sys.argv[2:]]
    docs = [json.loads(p.read_text()) for p in ins]
    weights = {d.get("weights") for d in docs}
    if len(weights) != 1:
        raise SystemExit(f"differing weights: {weights}")
    frames: dict[str, object] = {}
    for d in docs:
        dup = set(frames) & set(d["frames"])
        if dup:
            raise SystemExit(f"shared frame keys: {sorted(dup)[:3]}")
        frames.update(d["frames"])
    doc = {"weights": weights.pop(), "merged_from": [str(p) for p in ins], "frames": frames}
    out.write_text(json.dumps(doc))
    print(json.dumps({"frames": len(frames), "out": str(out)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
