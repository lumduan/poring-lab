#!/usr/bin/env python3
"""Judge a demo session's actions from its packets (docs/demonstrations.md §2), offline.

    demo_verify.py SESSION_DIR [SESSION_DIR ...] [--aid-gm 2000002] [--aid-player 2000001]

- Reads `demo.jsonl` and the session's `packets.jsonl.gz`.
- Fills each record's outcome with poring_dataset.verify (VERIFIER_VERSION) and writes
  `demo.verified.jsonl` beside them. The actor's stated cue is never consulted.
- An attack click (`attack_target`, 3.3) is resolved to the gid it meant: predict_sprite's monster
  boxes (qa_export.Labeler, v1) on the frame the actor looked at, shifted by the backend's
  packet->frame offset (--offset-ms, default: the newest matching benchmark run); then
  verify_attack (verify@2) with the walk-in time from the cell distance.
- Client-side windows (menu shortcuts) are judged on the session's snapshots by the anchor map
  (§2): the window absent before, present 1 s after.
- `interrupted.json` in a session (scripts/demo_interruptions.py: a human took the lease) makes
  those records `interrupted`: neither success nor fail, left out of the rate. Their re-runs are
  separate sessions (rule_run.py --rerun-of); give them all to score the rule as one set.
- Prints, per rule: attempts, verified successes, failures by cause, ambiguous by cause, and
  the time per attempt p50/p95. The bar (pre-registered) is >= 95 % of the non-ambiguous
  attempts, with at most 10 % ambiguous.

Packets are verification ground truth ONLY (ADR-0007): this runs after the fact, never in a loop
that acts.
"""

from __future__ import annotations

import argparse
import functools
import gzip
import json
import statistics
import sys
from collections import Counter
from pathlib import Path
from typing import Any

from poring_dataset import verify as V
from poring_env.demo import DemoRecord, Outcome, read

BAR = 0.95
MAX_AMBIGUOUS = 0.10
ROOT = Path(__file__).resolve().parents[1]
OFFSET_MS: float | None = None  # --offset-ms; None = auto (qa_export.auto_offset_ms)


def load_events(session_dir: Path) -> list[dict[str, Any]]:
    path = session_dir / "packets.jsonl.gz"
    if not path.exists():
        raise SystemExit(f"no packets.jsonl.gz in {session_dir}")
    with gzip.open(path, "rt") as fh:
        return [json.loads(line) for line in fh if line.strip()]


ANCHORS = Path(__file__).resolve().parents[1] / "data" / "ui_anchors"


@functools.cache
def window_registry() -> Any:
    """The ADR-0011 anchor map with the cut templates (the menu verifier's screen check)."""
    from poring_env import ui_anchors as ua

    return ua.default_registry(ANCHORS)


def windows_on(session_dir: Path, ref: str | None) -> set[str] | None:
    """The windows whose anchors are found on a snapshot of this session, or None (no frame)."""
    if not ref or ref.startswith("session:"):
        return None
    from poring_dataset.shards import decode_png

    return set(window_registry().locate(decode_png((session_dir / ref).read_bytes())[:, :, :3]))


def judge_window(rec: DemoRecord, session_dir: Path | None) -> V.Verdict:
    """§2 menu shortcut: the window's anchor absent before, present 1 s after (the snapshots)."""
    w = rec.action.intended.window
    if w is None or session_dir is None:
        return V.Verdict("ambiguous", "no window or no session to judge on")
    if w not in window_registry().templates:
        return V.Verdict("ambiguous", f"no cut anchor for {w}")
    before = windows_on(session_dir, rec.frame.ref)
    after = windows_on(session_dir, rec.frame_after.ref if rec.frame_after else None)
    if before is None or after is None:
        return V.Verdict("ambiguous", "a snapshot is missing")
    v = V.verify_menu(w in before, w in after)
    evidence = {"before": sorted(before), "after": sorted(after)}
    return V.Verdict(v.status, v.cause, {**v.evidence, **evidence})


def goal_taken(events: list[dict[str, Any]], goal: tuple[int, int], t_ns: int,
               slack_ns: int = 1_000_000_000) -> list[int]:  # fmt: skip
    """The gids of other units within one cell of ``goal`` at any 0.25 s step of t +- slack."""
    from poring_dataset.timeline import Timeline

    tl = Timeline(events)
    gids: set[int] = set()
    for t in range(t_ns - slack_ns, t_ns + slack_ns + 1, 250_000_000):
        for e in tl.frame_world(t).entities:
            if max(abs(round(e.x) - goal[0]), abs(round(e.y) - goal[1])) <= 1:
                gids.add(int(e.gid))
    return sorted(gids)


@functools.cache
def click_targets(session_dir: Path, offset_ms: float | None) -> tuple[Any, float, str | None]:
    """(a Labeler over this session's packets, the offset used, the benchmark run it came from)."""
    sys.path.insert(0, str(ROOT / "scripts"))
    import qa_export

    backend = str(json.loads((session_dir / "manifest.json").read_text())["backend"])
    run = None
    if offset_ms is None:
        config = {"backend": backend, "client": {"name": "xfreerdp" if backend == "rdp" else None}}
        offset_ms, run = qa_export.auto_offset_ms(config)
    labeler = qa_export.Labeler.from_events(load_events(session_dir), backend, (1280, 720),
                                            offset_ms)  # fmt: skip
    return labeler, offset_ms, run


def judge_attack(rec: DemoRecord, events: list[dict[str, Any]], aid: int, t_end: int | None,
                 targets: Any) -> V.Verdict:  # fmt: skip
    """§2 / 3.3: which gid the click meant (V.resolve_click on predict_sprite's monster boxes, at
    the time of the frame the actor looked at), then verify_attack. ``targets``: click_targets()."""
    if not rec.action.points:
        return V.Verdict("ambiguous", "no click point")
    labeler, offset_ms, run = targets
    t_frame = rec.frame.t_capture_ns or rec.t_mono_ns
    boxes = labeler.boxes(t_frame)
    if boxes is None:
        return V.Verdict("ambiguous", "the frame is inside a GM-command window")
    monsters = {b["gid"]: (b["x1"], b["y1"], b["x2"], b["y2"]) for b in boxes
                if b["cls"] == "monster"}  # fmt: skip
    point = rec.action.points[0]
    gid, dist = V.resolve_click((float(point[0]), float(point[1])), monsters)
    if gid is None:
        return V.Verdict("ambiguous", "no monster box on the actor's frame")
    walk_s = 0.0
    start = V.position_before(events, rec.t_mono_ns, aid)
    ent = next((e for e in labeler.timeline.frame_world(rec.t_mono_ns).entities if e.gid == gid),
               None)  # fmt: skip
    if start is not None and ent is not None:
        cells = max(abs(round(ent.x) - start[0]), abs(round(ent.y) - start[1]))
        walk_s = max(0, cells - 1) * V.speed_before(events, rec.t_mono_ns) / 1000.0
    v = V.verify_attack(events, rec.t_mono_ns, aid, gid, walk_s, t_end)
    evidence = {"target_gid": gid, "click_to_sprite_px": dist, "walk_in_s": round(walk_s, 2),
                "offset_ms": offset_ms, "offset_run": run}  # fmt: skip
    return V.Verdict(v.status, v.cause, {**v.evidence, **evidence})


def judge(
    rec: DemoRecord,
    events: list[dict[str, Any]],
    aids: dict[str, int],
    t_end: int | None = None,
    session_dir: Path | None = None,
) -> V.Verdict | None:
    """``t_end``: the next record's start; no window reaches into the next action."""
    """None = not a scored action (the harness's own records)."""
    if rec.actor.startswith("rule:harness@"):
        return None
    kind = rec.action.type
    decline = rec.outcome.evidence.get("decline") or rec.outcome.evidence.get("rule_decline")
    if decline:
        return V.Verdict("fail", f"declined:{decline}")  # pre-registered: a decline is a FAIL
    if kind == "login":
        return V.verify_login(events, rec.t_mono_ns, aids[rec.action.intended.note or "gm"], t_end)
    if kind == "walk" and rec.action.intended.kind == "route":
        # walk@5: end to end -- where the packets put us when the route ended (+0.5 s)
        goal = rec.action.intended.cell
        t_end_route = (rec.t_done_ns or rec.t_mono_ns) + 500_000_000
        end = V.position_before(events, t_end_route, aids["gm"])
        if goal is None or end is None:
            return V.Verdict("ambiguous", "no goal or no position fix at the route's end")
        to_map = rec.outcome.evidence.get("to_map")
        if to_map is not None:  # walk@8's portal walk: the route must end on the OTHER map
            maps = [str(e.get("map", "")).removesuffix(".gat") for e in events
                    if e.get("type") == "map_change"
                    and rec.t_mono_ns <= e["t_mono_ns"] <= t_end_route]  # fmt: skip
            if not maps or maps[-1] != to_map:
                return V.Verdict("fail", "the portal was not taken",
                                 {"end": list(end), "maps": maps, "to_map": to_map})  # fmt: skip
        if tuple(end) == tuple(goal):
            return V.Verdict("success", None, {"end": list(end)})
        sub = rec.outcome.evidence.get("substitute")
        if sub is not None and tuple(end) == tuple(sub):
            # walk@7 (b): a substitute counts only if the goal was really taken when the rule gave
            # it up -- another unit within one cell of it at that moment (the packets)
            t_sub = max((e["t"] for e in rec.outcome.evidence.get("events", [])
                         if "substitute" in e and "t" in e), default=None)  # fmt: skip
            near = goal_taken(events, tuple(goal), t_sub) if t_sub is not None else None
            ev = {"end": list(end), "goal": list(goal), "substitute": list(sub), "taken_by": near}
            if near:
                return V.Verdict("success", "substitute: the goal was taken", ev)
            return V.Verdict("fail", "substituted a goal nobody had taken", ev)
        return V.Verdict(
            "fail", "the route ended elsewhere", {"end": list(end), "goal": list(goal)}
        )
    if kind == "walk":
        aid = aids["gm"]
        start = V.position_before(events, rec.t_mono_ns, aid)
        cell = rec.action.intended.cell
        if start is None or cell is None:
            return V.Verdict("ambiguous", "no position fix before the click")
        target = (start[0] + cell[0], start[1] + cell[1]) if rec.action.intended.relative else cell
        speed = V.speed_before(events, rec.t_mono_ns)
        return V.verify_walk(events, rec.t_mono_ns, aid, target, speed, t_end)
    if kind == "menu_shortcut":
        return judge_window(rec, session_dir)
    if kind == "attack_target":
        if session_dir is None:
            return V.Verdict("ambiguous", "no session to resolve the click on")
        return judge_attack(rec, events, aids["gm"], t_end, click_targets(session_dir, OFFSET_MS))
    return V.Verdict("ambiguous", f"no verifier for {kind} yet")


UNSAFE_ACTS = ("normal", "pickup")  # our act kinds no walk may cause: a hit (or miss), a pickup
REQUESTS_NOTE = (
    "attack_request / npc_contact come from OFFLINE-only decoders (bc1a2e6): the live sniffer "
    "never emits them, so 0 here proves nothing; our_acts is the live record (2026-10-08)"
)


def safety(events: list[dict[str, Any]], aid: int) -> dict[str, Any]:
    """What the SERVER says we did: ZC_NOTIFY_ACT with src_gid = us (decoded live). In 2026-10-07/08
    the walk scores counted only request events, which the live sniffer never emits, and reported
    "SAFETY held" over runs where the GM attacked (demonstrations.md, the 03:15 correction)."""
    acts = Counter(str(e.get("kind")) for e in events
                   if e.get("type") == "act" and int(e.get("src_gid", -1)) == aid)  # fmt: skip
    requests = Counter(str(e["type"]) for e in events if e.get("type") in V.ATTACK_REQUESTS)
    return {"our_acts": dict(acts), "unsafe_acts": sum(acts[k] for k in UNSAFE_ACTS),
            "requests_seen": dict(requests), "requests_note": REQUESTS_NOTE}  # fmt: skip


def summarise(rows: list[tuple[DemoRecord, V.Verdict]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    by_rule: dict[str, list[tuple[DemoRecord, V.Verdict]]] = {}
    for rec, v in rows:
        by_rule.setdefault(rec.rule or rec.actor, []).append((rec, v))
    for rule, all_rs in by_rule.items():
        rs = [(rec, v) for rec, v in all_rs if v.status != "interrupted"]
        status = Counter(v.status for _, v in rs)
        n_amb = status["ambiguous"]
        scored = len(rs) - n_amb
        secs = [((rec.t_done_ns or rec.t_mono_ns) - rec.t_mono_ns) / 1e9 for rec, _ in rs]
        q = sorted(secs)
        rate = status["success"] / scored if scored else 0.0
        out[rule] = {
            "attempts": len(rs), "interrupted": len(all_rs) - len(rs),
            "verified_success": status["success"], "fail": status["fail"],
            "ambiguous": n_amb, "success_rate": round(rate, 4),
            "fail_causes": dict(Counter(v.cause for _, v in rs if v.status == "fail")),
            "ambiguous_causes": dict(Counter(v.cause for _, v in rs if v.status == "ambiguous")),
            "seconds_p50": round(statistics.median(secs), 1) if secs else None,
            "seconds_p95": round(q[int(0.95 * (len(q) - 1))], 1) if q else None,
            "verdict": ("INCONCLUSIVE (ambiguous > 10 %)"
                        if len(rs) and n_amb / len(rs) > MAX_AMBIGUOUS
                        else "PASS" if rate >= BAR else "FAIL"),
        }  # fmt: skip
    return out


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("session_dirs", type=Path, nargs="+")
    ap.add_argument("--aid-gm", type=int, default=2000002)
    ap.add_argument("--aid-player", type=int, default=2000001)
    ap.add_argument(
        "--offset-ms",
        type=float,
        default=None,
        help="packet->frame offset for attack clicks (default: newest benchmark)",
    )
    a = ap.parse_args()
    global OFFSET_MS
    OFFSET_MS = a.offset_ms
    aids = {"gm": a.aid_gm, "player": a.aid_player}
    rows: list[tuple[DemoRecord, V.Verdict]] = []
    n_events = 0
    safety_by_session: dict[str, Any] = {}
    for session_dir in a.session_dirs:
        records = read(session_dir / "demo.jsonl")
        events = load_events(session_dir)
        n_events += len(events)
        safety_by_session[session_dir.name] = {
            who: safety(events, aid) for who, aid in aids.items()
        }
        marks_path = session_dir / "interrupted.json"
        marks: dict[str, str] = json.loads(marks_path.read_text()) if marks_path.exists() else {}
        out_lines = []
        starts = sorted(r.t_mono_ns for r in records)
        for rec in records:
            later = [t for t in starts if t > rec.t_mono_ns]
            if rec.record_id in marks:
                v: V.Verdict | None = V.Verdict("interrupted", marks[rec.record_id][:200])
            else:
                v = judge(rec, events, aids, later[0] if later else None, session_dir)
            if v is None:
                out_lines.append(rec.model_dump_json())
                continue
            rows.append((rec, v))
            evidence = {**rec.outcome.evidence, **v.evidence}
            outcome = Outcome(
                status=v.status,  # type: ignore[arg-type]
                verifier=v.verifier,
                cause=v.cause,
                evidence=evidence,
            )
            done = rec.model_copy(update={"outcome": outcome})
            out_lines.append(done.model_dump_json())
        (session_dir / "demo.verified.jsonl").write_text("".join(x + "\n" for x in out_lines))
    sessions = [d.name for d in a.session_dirs]
    print(json.dumps({"sessions": sessions, "verifier": f"verify@{V.VERIFIER_VERSION}",
                      "events": n_events, "rules": summarise(rows),
                      "safety": safety_by_session}, indent=1))  # fmt: skip
    return 0


if __name__ == "__main__":
    sys.exit(main())
