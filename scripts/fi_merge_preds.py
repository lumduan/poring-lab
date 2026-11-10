#!/usr/bin/env python3
"""ONE prediction set (predict_dir's format) from several runs of the SAME weights on disjoint
refs (xmas02-detector.md O15: the staged held-out first, the pilots' later), for fi_eval.py.

    fi_merge_preds.py OUT.json IN1.json IN2.json ... [--weights-sha256 HEX]

Refuses differing weights or a frame key in two inputs. Nothing is changed in any prediction.
``--weights-sha256 HEX``: the inputs name ONE file by two paths (O15f: predicted before and after
the run's archive); the caller vouches that both held the bytes HEX, and the output records the
paths and HEX.
"""

import json
import sys
from pathlib import Path


def main() -> int:
    args = sys.argv[1:]
    sha = None
    if "--weights-sha256" in args:
        i = args.index("--weights-sha256")
        sha = args[i + 1]
        args = args[:i] + args[i + 2 :]
    out, ins = Path(args[0]), [Path(p) for p in args[1:]]
    docs = [json.loads(p.read_text()) for p in ins]
    weights = {d.get("weights") for d in docs}
    if len(weights) != 1 and sha is None:
        raise SystemExit(f"differing weights: {weights} (--weights-sha256 if they are one file)")
    frames: dict[str, object] = {}
    for d in docs:
        dup = set(frames) & set(d["frames"])
        if dup:
            raise SystemExit(f"shared frame keys: {sorted(dup)[:3]}")
        frames.update(d["frames"])
    w = sorted(str(x) for x in weights)
    doc = {"weights": w[0] if len(w) == 1 else w, "weights_sha256": sha,
           "merged_from": [str(p) for p in ins], "frames": frames}  # fmt: skip
    out.write_text(json.dumps(doc))
    print(json.dumps({"frames": len(frames), "out": str(out)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
