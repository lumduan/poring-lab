#!/usr/bin/env python3
"""The mid-epoch resume PROOF (Batt, 2026-10-08), host side. Pre-registered in
docs/operations/mid-epoch-checkpoints.md BEFORE any run; the bar is `compare` below. (Apache-2.0,
host only: it reads the vision runs' trace files and imports nothing from the AGPL component.)

    resume_proof.py plan [--cache v0png-20261006]     the guarded commands, in order (run by hand)
    resume_proof.py compare A.jsonl A2.jsonl B.jsonl  PASS (rc 0) or FAIL (rc 1), JSON on stdout

The runs, all `--smoke` (1,000 train frames = 500 batches/epoch at batch 2), 3 epochs,
close_mosaic 1 (mosaic in epochs 1-2, the reset at epoch 3's start), warmup over epochs 1-2,
batch 2 / workers 1 as v1, a mid checkpoint every 64 batches (time trigger off: positions are
deterministic), each batch traced:
- A: uninterrupted.
- A2: A again: the GPU's own nondeterminism floor (the envelope for B's losses).
- B: killed twice, resumed twice, on ONE trace file:
  - B1 dies after global batch 850 (epoch 2, batch 350: mosaic on, still in warmup). The last mid
    save was at batch 300, so 51 batches are trained again.
  - B2 resumes there and dies after global batch 1037 (epoch 3, batch 37: after close_mosaic's
    reset, before epoch 3's first mid save).
  - B3 resumes from the BOUNDARY checkpoint written at the end of epoch 2 and runs to the end.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np

KILLS = (850, 1037)
GUARD = "python3 scripts/guarded_build.py --sustain 30 --spike 25"


def train_cmd(cache: str, name: str, extra: str = "") -> str:
    run = (f"python -m poring_vision.train --cache /datasets/.framecache/{cache} --smoke "
           f"--batch 2 --workers 1 --name {name} --mid-ckpt --close-mosaic 1 "
           f"--mid-every-batches 64 --mid-every-s 0 --trace /data/train/{name}/trace.jsonl "
           f"--step-sleep-ms 2000 --duty-file /lab-duty/duty.json{extra}")  # fmt: skip
    return f"{GUARD} 'rundev:vision@3600={run}'"


def plan(cache: str) -> list[tuple[str, str, str]]:
    """(label, command, the expected outcome)."""
    b = "resume-proof-B"
    return [
        ("A", train_cmd(cache, "resume-proof-A"), "rc 0"),
        ("A2", train_cmd(cache, "resume-proof-A2"), "rc 0"),
        ("B1", train_cmd(cache, b, f" --die-after-batches {KILLS[0]}"), "dies, rc 86"),
        (
            "B2",
            train_cmd(cache, b, f" --resume --die-after-batches {KILLS[1]}"),
            "resumes from a mid save in epoch 2, dies, rc 86",
        ),
        ("B3", train_cmd(cache, b, " --resume"), "resumes from the epoch-2 boundary, rc 0"),
    ]


# --- the proof: trace comparison ----------------------------------------------------------------
def load_trace(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in Path(path).read_text().splitlines() if line.strip()]


def _batches(records: list[dict[str, Any]]) -> dict[tuple[int, int], dict[str, Any]]:
    """The LAST record of each (epoch, i): a resume re-trains the batches after its mid save."""
    return {(r["epoch"], r["i"]): r for r in records if r.get("kind") == "batch"}


def compare(a: list[dict[str, Any]], a2: list[dict[str, Any]], b: list[dict[str, Any]],
            rel_slack: float = 1.5, abs_floor: float = 1e-6) -> dict[str, Any]:  # fmt: skip
    """The pre-registered bar (docs/operations/mid-epoch-checkpoints.md). ``b`` = the killed run's
    trace followed by its resume's. PASS iff:
    (a) every batch of A exists in B with the same sample indices, positions and image + label
        hashes (the data stream and its augmentation are EXACT);
    (b) every optimizer step has the same lr and momentum per parameter group, the same
        accumulate and the same EMA update count (the schedule is EXACT);
    (c) losses: bitwise equal to A's when A and A2 are bitwise equal; otherwise, over the batches
        after the resume point, |B - A|'s median and p95 per loss item stay within ``rel_slack``
        times A2-vs-A's (+ ``abs_floor``): the GPU's own nondeterminism floor;
    (d) every resume restored the state bitwise (its post-restore digest == the saved one)."""
    A, A2, B = _batches(a), _batches(a2), _batches(b)
    out: dict[str, Any] = {"batches": len(A), "fail": []}
    missing = sorted(set(A) - set(B))
    if missing:
        out["fail"].append(f"(a) {len(missing)} batches of A missing in B, first {missing[0]}")
    data_bad = [k for k in sorted(A) if k in B and any(
        A[k].get(f) != B[k].get(f) for f in ("idx", "pos", "img", "lab"))]  # fmt: skip
    if data_bad:
        out["fail"].append(f"(a) data differs in {len(data_bad)} batches, first {data_bad[0]}")
    steps = [k for k in sorted(A) if "lr" in A[k]]
    sched = ("lr", "momentum", "accumulate", "ema_updates")
    sched_bad = [k for k in steps if k in B and any(A[k].get(f) != B[k].get(f) for f in sched)]
    if sched_bad:
        out["fail"].append(f"(b) schedule differs at {len(sched_bad)} steps, first {sched_bad[0]}")
    resumes = [r for r in b if r.get("kind") == "resume"]
    if not resumes:
        out["fail"].append("(d) B never resumed: no resume record")
    for r in resumes:
        if r.get("restored_sha256") != r.get("saved_sha256"):
            out["fail"].append(f"(d) resume at {r.get('at')}: restored state != saved state")
    out["resumed_at"] = [r.get("at") for r in resumes]
    bitwise_aa2 = all(k in A2 and A[k].get("loss") == A2[k].get("loss") for k in A)
    out["a_equals_a2"] = bitwise_aa2
    after = [k for k in sorted(A) if resumes and k >= tuple(resumes[0]["at"]) and k in B]
    if bitwise_aa2:
        loss_bad = [k for k in after if A[k].get("loss") != B[k].get("loss")]
        if loss_bad:
            out["fail"].append(f"(c) A == A2 bitwise, but B's loss differs at {len(loss_bad)} "
                               f"batches, first {loss_bad[0]}")  # fmt: skip
    else:
        env = _loss_stats(A, A2, after)
        got = _loss_stats(A, B, after)
        out["loss_envelope_a_a2"], out["loss_diff_a_b"] = env, got
        for item, (med, p95) in got.items():
            emed, ep95 = env.get(item, (0.0, 0.0))
            if med > rel_slack * emed + abs_floor or p95 > rel_slack * ep95 + abs_floor:
                out["fail"].append(f"(c) {item}: |B-A| median/p95 {med:.3g}/{p95:.3g} beyond "
                                   f"{rel_slack} x A2's {emed:.3g}/{ep95:.3g}")  # fmt: skip
    out["pass"] = not out["fail"]
    return out


def _loss_stats(x: dict[tuple[int, int], dict[str, Any]], y: dict[tuple[int, int], dict[str, Any]],
                keys: list[tuple[int, int]]) -> dict[str, tuple[float, float]]:  # fmt: skip
    diffs: dict[str, list[float]] = {}
    for k in keys:
        if k not in y:
            continue
        for item, v in (x[k].get("loss") or {}).items():
            w = (y[k].get("loss") or {}).get(item)
            if w is not None:
                diffs.setdefault(item, []).append(abs(float(v) - float(w)))
    return {item: (float(np.median(d)), float(np.percentile(d, 95))) for item, d in diffs.items()}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)  # fmt: skip
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("plan")
    p.add_argument("--cache", default="v0png-20261006")
    c = sub.add_parser("compare")
    c.add_argument("a", type=Path)
    c.add_argument("a2", type=Path)
    c.add_argument("b", type=Path)
    args = ap.parse_args()
    if args.cmd == "plan":
        for label, cmd, expect in plan(args.cache):
            print(f"# {label}: expect {expect}\n{cmd}\n")
        traces = " ".join(f"data/train/resume-proof-{r}/trace.jsonl" for r in ("A", "A2", "B"))
        print(f"# then:\npython3 scripts/resume_proof.py compare {traces}")
        return 0
    out = compare(load_trace(args.a), load_trace(args.a2), load_trace(args.b))
    print(json.dumps(out, indent=1))
    return 0 if out["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
