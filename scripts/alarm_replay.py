#!/usr/bin/env python3
"""goblin-alarm-1080.md section 4 (pre-registered 2026-11-21 00:37 ICT, a120bc61): the runner's
ALARM decisions replayed OFFLINE from a session's own detection logs, under today's rule, the
near-her rule (rule A) and confirm 3, each sighting judged by the packets. Nothing here reaches a
runner.

    alarm_replay.py replay ifT4-play ifT5-play ... [--json] [--out FILE]

A SERIES label (screen_ab's) names its runs' hunt-core sessions in the demo folder
(``*-<label>-r*-hunt*``). Per session:
- the alarm FEED: the decision detector's rows (detections.jsonl) and, when the session's start
  record says the HUD twin feeds the alarm (``alarm_fast``'s second field), the HUD twin's rows
  (detections_hud.jsonl), in time order (the log time of each detection; the runner's watcher feeds
  them in grab order, ~the same order);
- the alarm boxes of a row: its boxes of the box model's alarm classes (the start record's
  ``box_model.alarm``), in the row's order; the STREAK: consecutive rows with one
  (dungeon_hunt.alarm_streak), over all of them;
- a row QUALIFIES by dungeon_hunt.alarm_seen's rule with the session's need (``garm_fly``'s fourth
  field, else 1) and solo (``alarm_fast``'s first, else none): ``streak >= need`` -> the first box;
  else a box scoring >= solo. Rule A filters the boxes alarm_seen is GIVEN (the streak stays the
  feed's): a box whose centre lies within NEAR_PX of her body's point (HER_POINT) passes only at a
  score >= NEAR_SOLO. Confirm 3: need 3, solo as the session's.
- an EPISODE: a qualifying row with none in the EPISODE_GAP_S before it;
- each episode judged by the packets (stage9_ab.Truth, the world FRAME_LAG_S before it, the
  runner's camera): ``false`` (no alarm-species unit on screen), ``true`` (one is: its nearest
  one's Chebyshev cells from her), ``post_vanish`` (S7.1's windows: not counted), ``unknown``
  (her cell unknown);
- a LOST true episode: today's true episode with no episode of the rule within EPISODE_GAP_S.
"""

from __future__ import annotations

import argparse
import gzip
import json
import math
import sys
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
ROOT = Path(__file__).resolve().parents[1]

DEMO = Path("/dev/shm/poring-lab-demo")  # stage2_ab.DEMO
FOOT_PX, BODY_UP = (641, 362), 26  # dungeon_hunt's
HER_POINT = (FOOT_PX[0], FOOT_PX[1] - BODY_UP)  # her body's point in the 1280 x 720 client
NEAR_PX, NEAR_SOLO = 60.0, 0.85  # rule A (goblin-alarm-1080.md 3)
EPISODE_GAP_S = 2.0
RULES = ("today", "near", "confirm3")
START_KINDS = ("run_start",)  # the runner's first record (its fixes, its box model)


# --- pure ---------------------------------------------------------------------------------------
def settings(start: Mapping[str, Any]) -> dict[str, Any]:
    """PURE: the alarm's settings from a session's run_start record."""
    fixes = start.get("fixes") or {}
    gf = fixes.get("garm_fly")
    af = fixes.get("alarm_fast")
    model = start.get("box_model") or {}
    return {
        "on": gf is not None,
        "need": int(gf[3]) if isinstance(gf, list) and len(gf) > 3 else 1,
        "solo": float(af[0]) if isinstance(af, list) and af else None,
        "hud": bool(af[1]) if isinstance(af, list) and len(af) > 1 else False,
        "classes": tuple(model.get("alarm") or ("garm_baby",)),
    }


def feed(main: Iterable[Mapping[str, Any]], hud: Iterable[Mapping[str, Any]], use_hud: bool,
         classes: Sequence[str]) -> list[tuple[int, list[list[Any]]]]:  # fmt: skip
    """PURE: the alarm feed: (t_ns, the row's alarm boxes) for every detection row, the HUD
    twin's too when ``use_hud``, in time order."""
    rows = [dict(r, _src="main") for r in main]
    if use_hud:
        rows += [dict(r, _src="hud") for r in hud]
    rows.sort(key=lambda r: int(r["t_ns"]))
    cls = set(classes)
    return [(int(r["t_ns"]), [b for b in r.get("boxes") or [] if str(b[5]) in cls]) for r in rows]


def her_px(box: Sequence[Any]) -> float:
    """PURE: a box centre's distance from her body's point."""
    cx, cy = (float(box[0]) + float(box[2])) / 2, (float(box[1]) + float(box[3])) / 2
    return math.hypot(cx - HER_POINT[0], cy - HER_POINT[1])


def near_filter(boxes: Sequence[Sequence[Any]], near_px: float = NEAR_PX,
                near_solo: float = NEAR_SOLO) -> list[Sequence[Any]]:  # fmt: skip
    """PURE (rule A): the boxes alarm_seen may use: a box within ``near_px`` of her body's point
    only at a score >= ``near_solo``."""
    return [b for b in boxes if her_px(b) > near_px or float(b[4]) >= near_solo]


def seen(boxes: Sequence[Sequence[Any]], streak: int, need: int,
         solo: float | None) -> Sequence[Any] | None:  # fmt: skip
    """PURE: dungeon_hunt.alarm_seen's rule on a fresh row (the box, or None)."""
    if not boxes:
        return None
    if streak >= need:
        return boxes[0]
    if solo:
        best = max(boxes, key=lambda b: float(b[4]))
        if float(best[4]) >= solo:
            return best
    return None


def qualifying(fd: Sequence[tuple[int, list[list[Any]]]], rule: str, need: int,
               solo: float | None) -> list[tuple[int, Sequence[Any]]]:  # fmt: skip
    """PURE: the rows that qualify under ``rule`` (today / near / confirm3), with their box."""
    out: list[tuple[int, Sequence[Any]]] = []
    streak = 0
    for t, boxes in fd:
        streak = streak + 1 if boxes else 0
        use = near_filter(boxes) if rule == "near" else boxes
        b = seen(use, streak, 3 if rule == "confirm3" else need, solo)
        if b is not None:
            out.append((t, b))
    return out


def episodes(q: Sequence[tuple[int, Sequence[Any]]], gap_s: float = EPISODE_GAP_S,
             ) -> list[tuple[int, Sequence[Any]]]:  # fmt: skip
    """PURE: the qualifying rows with none in the ``gap_s`` before them."""
    out: list[tuple[int, Sequence[Any]]] = []
    last: int | None = None
    for t, b in q:
        if last is None or t - last > gap_s * 1e9:
            out.append((t, b))
        last = t
    return out


def lost(today: Sequence[Mapping[str, Any]], other: Sequence[Mapping[str, Any]],
         gap_s: float = EPISODE_GAP_S) -> list[Mapping[str, Any]]:  # fmt: skip
    """PURE: today's TRUE episodes with no episode of the other rule within ``gap_s``."""
    ts = [int(e["t_ns"]) for e in other]
    return [e for e in today if e["judged"] == "true"
            and not any(abs(t - int(e["t_ns"])) <= gap_s * 1e9 for t in ts)]  # fmt: skip


def tally(rows: Sequence[Mapping[str, Any]], hours: float) -> dict[str, Any]:
    """PURE: a rule's episodes by verdict, the false ones an hour, by class and nearest job."""
    by = Counter(str(e["judged"]) for e in rows)
    fl = [e for e in rows if e["judged"] == "false"]
    return {
        "episodes": len(rows),
        **{k: by.get(k, 0) for k in ("false", "true", "post_vanish", "unknown")},
        "false_h": round(len(fl) / hours, 2) if hours > 0 else None,
        "false_by_class": dict(Counter(str(e["cls"]) for e in fl)),
        "false_by_nearest_job": dict(Counter(str(e.get("nearest_job")) for e in fl)),
    }


def verdict(out: Mapping[str, Any], share: float = 0.30) -> dict[str, Any]:
    """PURE: section 5's bars on the pooled tallies (rule A against today's)."""
    t, n = out["rules"]["today"], out["rules"]["near"]
    lost_far = [e for e in out["lost"]["near"] if (e.get("cells") or 0) >= 2]
    a = (
        t["false_h"] is not None
        and n["false_h"] is not None
        and n["false_h"] <= share * t["false_h"]
    )
    return {"false_h": {"today": t["false_h"], "near": n["false_h"], "bar": f"<= {share:.0%}",
                        "verdict": "PASS" if a else "FAIL"},
            "true_lost": {"lost": len(out["lost"]["near"]), "lost_2_cells_or_more": len(lost_far),
                          "verdict": "PASS" if not lost_far else "FAIL"},
            "verdict": "PASS" if a and not lost_far else "FAIL"}  # fmt: skip


# --- the packets (offline) ------------------------------------------------------------------------
class Judge:
    """A session's packets: the alarm-species units on screen at a time (stage9_ab.Truth)."""

    def __init__(self, packets: Sequence[Mapping[str, Any]]) -> None:
        import stage9_ab as s9

        self.s9 = s9
        self.truth = s9.Truth(packets)

    def judge(self, t_ns: int, box: Sequence[Any]) -> dict[str, Any]:
        import numpy as np

        s9 = self.s9
        if self.truth.post_vanish(t_ns):
            return {"judged": "post_vanish"}
        fw = self.truth.tl.frame_world(int(t_ns - s9.FRAME_LAG_S * 1e9))
        if fw.self_pos is None:
            return {"judged": "unknown"}
        sx, sy = fw.self_pos
        mons = [e for e in fw.entities if e.objtype == 5 and not e.hidden]
        alarm = [e for e in mons if e.job in s9.ALARM_SPECIES]
        on = []
        if alarm:
            uv = self.truth.project(np.array([[e.x - sx, e.y - sy] for e in alarm], dtype=float))
            on = [e for e, (u, v) in zip(alarm, uv, strict=True)
                  if s9.on_screen(float(u), float(v))]  # fmt: skip
        out: dict[str, Any] = {"judged": "true" if on else "false"}
        if on:
            out["cells"] = min(max(abs(e.x - sx), abs(e.y - sy)) for e in on)
        if mons:  # the unit nearest the box's centre (its body ~BODY_UP above its cell's point)
            uv = self.truth.project(np.array([[e.x - sx, e.y - sy] for e in mons], dtype=float))
            cx, cy = (float(box[0]) + float(box[2])) / 2, (float(box[1]) + float(box[3])) / 2
            d, e = min(
                (
                    (math.hypot(float(u) - cx, float(v) - BODY_UP - cy), e)
                    for e, (u, v) in zip(mons, uv, strict=True)
                ),
                key=lambda x: x[0],
            )
            out.update(nearest_job=int(e.job), nearest_px=round(d))
        return out


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    with path.open() as fh:
        return [json.loads(x) for x in fh if x.strip()]


def read_packets(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    with gzip.open(path, "rt") as fh:
        return [json.loads(x) for x in fh if x.strip()]


def replay_session(d: Path) -> dict[str, Any]:
    """One hunt-core session: every rule's episodes, judged."""
    ev = read_jsonl(d / "events.jsonl")
    start = next((e for e in ev if e.get("kind") in START_KINDS), None)
    if start is None:  # never the defaults in silence (they are not the session's rule)
        raise SystemExit(f"alarm_replay: {d.name} has no start record ({START_KINDS})")
    st = settings(start)
    fd = feed(read_jsonl(d / "detections.jsonl"), read_jsonl(d / "detections_hud.jsonl"),
              st["hud"], st["classes"])  # fmt: skip
    hours = (int(ev[-1]["t_ns"]) - int(ev[0]["t_ns"])) / 3.6e12 if len(ev) > 1 else 0.0
    judge = Judge(read_packets(d / "packets.jsonl.gz"))
    rules: dict[str, list[dict[str, Any]]] = {}
    for rule in RULES:
        rows = []
        for t, b in episodes(qualifying(fd, rule, st["need"], st["solo"])):
            rows.append({"t_ns": t, "cls": str(b[5]), "score": round(float(b[4]), 3),
                         "her_px": round(her_px(b)), **judge.judge(t, b)})  # fmt: skip
        rules[rule] = rows
    return {
        "session": d.name,
        "hours": round(hours, 4),
        "settings": st,
        "rows": len(fd),
        "rules": rules,
    }


def sessions_of(label: str, demo: Path = DEMO) -> list[Path]:
    """A series label's hunt-core sessions (its runs' -hunt* folders)."""
    return sorted(p for p in demo.glob(f"*-{label}-r*-hunt*") if (p / "events.jsonl").is_file())


def replay(labels: Sequence[str], demo: Path = DEMO) -> dict[str, Any]:
    per = [replay_session(d) for lab in labels for d in sessions_of(lab, demo)]
    hours = sum(s["hours"] for s in per)
    pooled = {r: [row for s in per for row in s["rules"][r]] for r in RULES}
    out: dict[str, Any] = {
        "labels": list(labels),
        "sessions": [s["session"] for s in per],
        "hours": round(hours, 3),
        "rules": {r: tally(pooled[r], hours) for r in RULES},
        "lost": {r: [dict(e) for e in lost(pooled["today"], pooled[r])] for r in RULES[1:]},
        "per_session": [
            {
                "session": s["session"],
                "hours": s["hours"],
                "settings": s["settings"],
                **{r: tally(s["rules"][r], s["hours"]) for r in RULES},
            }
            for s in per
        ],  # fmt: skip
    }
    out["verdict"] = verdict(out)
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("replay")
    p.add_argument("labels", nargs="+")
    p.add_argument("--json", action="store_true")
    p.add_argument("--out", type=Path, default=None)
    a = ap.parse_args(argv)
    got = replay(a.labels)
    if a.out is not None:
        a.out.write_text(json.dumps(got, indent=1) + "\n")
    show = {k: v for k, v in got.items() if k != "per_session"}
    print(json.dumps(show, indent=None if a.json else 1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
