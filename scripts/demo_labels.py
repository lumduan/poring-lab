#!/usr/bin/env python3
"""Export WEAK point labels from a verified demo session (docs/demonstrations.md §4).

    demo_labels.py SESSION_DIR [--out data/labels/demo]

- Reads `demo.verified.jsonl` (written by demo_verify.py). It refuses a session that has not been
  verified: a pending outcome is never a label.
- Only VERIFIED SUCCESSES become labels, and only on the frame the actor decided on (`frame`):
  - a walk click that the server accepted as a walk to the intended cell -> a NEGATIVE point:
    no clickable entity at that pixel;
  - an attack click whose act landed on the intended gid -> a POSITIVE point: that pixel
    belongs to that gid. Its box is attached later (predict_sprite over the session's
    Timeline), so `box` is null here.
- Every label says where it came from: source=demo (weak), the actor (claude-demo, rule:..,
  bot:..: the same schema for the bot's own actions), the rule, the verifier, the session and
  record. They are kept apart from the auto-labels (v0/v1); mixing is a separate
  pre-registration.
- Output: <out>/<session>.jsonl, atomically replaced. data/ is gitignored: never committed.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

from poring_env.demo import DemoRecord, read

LABEL_VERSION = 1
NEGATIVE = "no clickable entity at this pixel: the click became the intended walk"
POSITIVE = "this pixel belongs to the target gid: the click's attack landed on it"


def label_for(rec: DemoRecord) -> dict[str, Any] | None:
    """One label for a verified success with a click point, else None."""
    if rec.outcome.status != "success" or not rec.action.points:
        return None
    if rec.actor.startswith("rule:harness@"):
        return None
    kind = rec.action.type
    if kind == "walk":
        polarity, meaning, gid = "negative", NEGATIVE, None
    elif kind == "attack_target":
        if rec.action.intended.gid is None:
            return None
        polarity, meaning, gid = "positive", POSITIVE, rec.action.intended.gid
    else:
        return None
    u, v = rec.action.points[-1]
    evidence = rec.outcome.evidence
    return {
        "label_version": LABEL_VERSION,
        "source": "demo",
        "weak": True,
        "polarity": polarity,
        "meaning": meaning,
        "point": [round(u, 1), round(v, 1)],  # client px, GAME_REGION origin
        "gid": gid,
        "mob_id": evidence.get("mob_id"),
        "box": None,
        "frame": rec.frame.model_dump(),
        "scene": rec.scene,
        "session": rec.session,
        "record_id": rec.record_id,
        "actor": rec.actor,
        "rule": rec.rule,
        "verifier": rec.outcome.verifier,
        "click_to_sprite_px": rec.click_to_sprite_px,
    }


def export(session_dir: Path, out_dir: Path) -> tuple[Path, list[dict[str, Any]]]:
    path = session_dir / "demo.verified.jsonl"
    if not path.exists():
        raise SystemExit(f"{session_dir.name}: no demo.verified.jsonl (run demo_verify.py first)")
    labels = [x for x in (label_for(r) for r in read(path)) if x is not None]
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"{session_dir.name}.jsonl"
    tmp = out.with_suffix(".tmp")
    tmp.write_text("".join(json.dumps(x, sort_keys=True) + "\n" for x in labels))
    os.replace(tmp, out)
    return out, labels


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("session_dir", type=Path)
    ap.add_argument("--out", type=Path, default=Path("data/labels/demo"))
    a = ap.parse_args()
    out, labels = export(a.session_dir, a.out)
    counts: dict[str, int] = {}
    for x in labels:
        counts[x["polarity"]] = counts.get(x["polarity"], 0) + 1
    print(json.dumps({"session": a.session_dir.name, "out": str(out), "labels": counts}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
