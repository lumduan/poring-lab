#!/usr/bin/env python3
"""crusader-regen@1 (docs/demonstrations.md 3.96f, pre-registered 2026-10-21 21:17 ICT BEFORE this
was built): the Crusader's HP regen while STANDING, WALKING and FIGHTING, with Moving HP Recovery
(Batt 2026-10-21: "I want to see whether HP regen keeps up while the bot walks and fights
continuously").

    regen_walk.py run [--cycles 2] [--phase-s 60]     the trial (the Crusader online, at its stand)
    regen_walk.py judge SID                            the offline numbers (packets = the truth)

The trial, per cycle: `@killmonster2`, `@heal`, `@warp` to the stand, `@heal -3000` (atcommand.cpp
:1398-1399: status_damage), then three phases:
- S: standing, no keys;
- W: walking between cells 264 and 273 of row 107 (inside the box 258-278 x 102-112 that
  `npc_click_test.check_warps` passes), each click by pixels only through `cursor_gate.gated_click`
  (two-motion hover, the WALK cursor twice), the direction flipped only after a click;
- F: standing while ONE Orc Zombie attacks, the potion at 60 % (survive.py's S1b + S2).
PIXELS IN, KEYS OUT at run time; the judge reads the packets only afterwards.

What the pinned source predicts (status.cpp `status_natural_heal`): natural regen 33 HP every 6 s
(the absolute hp); Increase HP Recovery 155 every 10 s (ZC_RECOVERY 0x0A27, `recovery`); while
walking, IRP is OFF and natural regen runs at the doubled interval (Moving HP Recovery).
"""

from __future__ import annotations

import argparse
import bisect
import gzip
import json
import sys
import time
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import numpy as np

DEMO = Path("/dev/shm/poring-lab-demo")
NS = 1_000_000_000
STAND = ("prt_fild08", 268, 107)
WALK_X = (264, 273)  # the two walk targets on row 107 (+-9 cells: client x ~336 / ~949)
WALK_Y = 107
DEFICIT = 3000  # @heal -3000: HP 2,260 of 5,260, so regen never meets the max in a cycle
NATURAL = 33  # 1 + VIT 32 / 5 + MaxHP 5260 / 200 (status_calc_regen)
IRP = 155  # 5 x 10 + 5260 x 10 / 500
CELL_MS = 150  # DEFAULT_WALK_SPEED (common/mmo.hpp:93); straight moves only here
F_PACK = (1153, 1)  # one Orc Zombie
GATE_TRIES = 4


def walk_target(pos: int, toward_high: bool) -> int:
    """PURE: the next walk target on row 107 (the far end in the current direction)."""
    return WALK_X[1] if toward_high else WALK_X[0]


# --- offline: the judge ---------------------------------------------------------------------------


def walk_spans(packets: Sequence[Mapping[str, Any]]) -> list[tuple[int, int]]:
    """PURE: [(t0, t1)] of our walks: each `self_move` from its packet time for max(|dx|, |dy|)
    cells at CELL_MS (a new move cuts the previous one short)."""
    moves = sorted((int(e["t_mono_ns"]), int(e["x0"]), int(e["y0"]), int(e["x1"]), int(e["y1"]))
                   for e in packets if e.get("type") == "self_move")  # fmt: skip
    out: list[tuple[int, int]] = []
    for i, (t, x0, y0, x1, y1) in enumerate(moves):
        end = t + max(abs(x1 - x0), abs(y1 - y0)) * CELL_MS * 1_000_000
        if i + 1 < len(moves):
            end = min(end, moves[i + 1][0])
        if end > t:
            out.append((t, end))
    return out


def walking_at(spans: Sequence[tuple[int, int]], t: int) -> bool:
    i = bisect.bisect_right([s[0] for s in spans], t) - 1
    return i >= 0 and spans[i][0] <= t < spans[i][1]


def ticks(packets: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """PURE: the regen ticks in time order. `recovery` hp events are IRP ticks (their amount); an
    absolute hp rise of NATURAL (+-1) over the value RECONSTRUCTED from the last absolute hp plus
    the recovery amounts since is a natural tick. Other rises (potions, @heal) are not regen."""
    evs = sorted((e for e in packets
                  if (e.get("type") == "stat_change" and e.get("name") == "hp")
                  or (e.get("type") == "recovery" and e.get("name") == "hp")),
                 key=lambda e: int(e["t_mono_ns"]))  # fmt: skip
    out: list[dict[str, Any]] = []
    cur: int | None = None
    for e in evs:
        t = int(e["t_mono_ns"])
        if e["type"] == "recovery":
            out.append({"t": t, "kind": "irp", "amount": int(e["amount"])})
            if cur is not None:
                cur += int(e["amount"])
            continue
        v = int(e["value"])
        if cur is not None and abs((v - cur) - NATURAL) <= 1:
            out.append({"t": t, "kind": "natural", "amount": v - cur})
        cur = v
    return out


def judge(events: Sequence[Mapping[str, Any]], packets: Sequence[Mapping[str, Any]]
          ) -> dict[str, Any]:  # fmt: skip
    """PURE: per phase (S / W / F of each cycle): its minutes, the walking share, IRP and natural
    ticks (and how many fell while walking), regen HP/min; the positive cases; our attacks."""
    spans = walk_spans(packets)
    tk = ticks(packets)
    acts = [int(e["t_mono_ns"]) for e in packets if e.get("type") == "act"
            and e.get("kind") == "normal" and int(e.get("src_gid") or -1) == 2000002]  # fmt: skip
    rows = []
    for ph in (e for e in events if e.get("kind") == "phase_end"):
        t0, t1 = int(ph["t0"]), int(ph["t1"])
        mins = (t1 - t0) / NS / 60
        mine = [x for x in tk if t0 <= x["t"] < t1]
        walk_ns = sum(max(0, min(b, t1) - max(a, t0)) for a, b in spans)
        irp = [x for x in mine if x["kind"] == "irp"]
        nat = [x for x in mine if x["kind"] == "natural"]
        rows.append({
            "cycle": ph["cycle"], "phase": ph["phase"], "minutes": round(mins, 3),
            "walking_share": round(walk_ns / max(1, t1 - t0), 3),
            "irp_ticks": len(irp), "irp_amounts": sorted({x["amount"] for x in irp}),
            "irp_while_walking": sum(walking_at(spans, x["t"]) for x in irp),
            "natural_ticks": len(nat),
            "natural_while_walking": sum(walking_at(spans, x["t"]) for x in nat),
            "regen_hp_per_min": round(sum(x["amount"] for x in mine) / mins, 1) if mins else None,
            "our_attacks": sum(t0 <= t < t1 for t in acts),
        })  # fmt: skip
    s_rows = [x for x in rows if x["phase"] == "S"]
    w_rows = [x for x in rows if x["phase"] == "W"]
    return {
        "phases": rows,
        "positive_recovery_decoded": any(IRP in x["irp_amounts"] for x in s_rows),
        "irp_while_walking_total": sum(x["irp_while_walking"] for x in rows),
        "attacks_in_S_or_W": sum(x["our_attacks"] for x in s_rows + w_rows),
    }


def load(sid: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    d = DEMO / sid
    ev = [json.loads(x) for x in (d / "events.jsonl").read_text().splitlines() if x]
    with gzip.open(d / "packets.jsonl.gz", "rt") as fh:
        pk = [json.loads(x) for x in fh]
    return ev, pk


# --- live -----------------------------------------------------------------------------------------


def run(a: argparse.Namespace) -> int:  # noqa: PLR0915
    import bench
    import crusader as cr
    import cursor_gate
    import hp_percent as hpp
    import record_session as rs
    import ro_agent as r
    import survive as sv
    import ui_gate

    from poring_dataset import camera as cam
    from poring_dataset import gat as gatmod

    z = np.load(hpp.GLYPHS)
    glyphs = {("%" if k == "pct" else k[1:]): z[k] for k in z.files}
    gat = gatmod.parse((cam.GAT_DIR / f"{STAND[0]}.gat").read_bytes())
    if STAND[0] in cam.load_indoor_table():
        raise SystemExit(f"{STAND[0]} is indoor: the outdoor camera does not apply")
    cj = json.loads((r.ROOT / "packages/poring_dataset/src/poring_dataset/camera_rdp.json")
                    .read_text())  # fmt: skip
    camera = cam.camera_from_json(cj["camera"])
    sid = f"{time.strftime('%Y%m%dT%H%M%S')}-demo-crusader-regen-{a.label}"
    out = DEMO / sid
    out.mkdir(parents=True, exist_ok=False)
    evf = (out / "events.jsonl").open("a")

    def ev(rec: dict[str, Any]) -> None:
        evf.write(json.dumps({"t_ns": r.ns(), **rec}) + "\n")
        evf.flush()

    t0 = r.ns()
    reason = "done"
    with r.session("rule:crusader-regen") as (agent, screen):
        agent.wait_for_human()
        got = cr.check(screen, "crusader")
        if not got["ok"]:
            raise r.Stop(f"identity {got}")
        ui_gate.ensure_clear(agent, screen, why="regen-start")
        x0, y0, w0, h0 = r.game_region()
        pr = cursor_gate.prober(agent, screen)

        def hp_read() -> int | None:
            pct = hpp.read(r.grab_after(screen, (x0, y0, w0, h0), r.ns()), glyphs)
            ev({"kind": "hp_read", "pct": pct})
            return pct

        try:
            for cyc in range(a.cycles):
                for cmd in ("@killmonster2", "@heal",
                            f"@warp {STAND[0]} {STAND[1]} {STAND[2]}"):  # fmt: skip
                    cr.gm_line(agent, screen, cmd, "crusader")
                    time.sleep(3.0 if "warp" in cmd else 0.8)
                cr.gm_line(agent, screen, f"@heal -{DEFICIT}", "crusader")
                bench.close_chat(agent, screen)
                time.sleep(1.0)
                pos, high = STAND[1], True
                for phase in ("S", "W", "F"):
                    if phase == "F":
                        cr.gm_line(agent, screen, f"@monster {F_PACK[0]} {F_PACK[1]}", "crusader")
                        bench.close_chat(agent, screen)
                    st = sv.State()
                    p0 = r.ns()
                    end = time.monotonic() + a.phase_s
                    while time.monotonic() < end:
                        pct = hp_read()
                        if phase == "W":
                            target = walk_target(pos, high)
                            rel = np.array([[target - pos, 0]], dtype=float)
                            u, v = camera.project(rel, gat.relative_altitude((pos, WALK_Y), rel))[0]
                            g: dict[str, Any] = {}
                            for _ in range(GATE_TRIES):
                                g = cursor_gate.gated_click(pr, u, v)
                                if g["clicked"]:
                                    break
                            ev({"kind": "walk_click", "from": pos, "to": target,
                                "clicked": g.get("clicked"), "why": g.get("why")})  # fmt: skip
                            if g.get("clicked"):
                                time.sleep(abs(target - pos) * CELL_MS / 1000 + 0.15)
                                pos, high = target, not high
                            continue
                        if phase == "F" and pct is not None:
                            for what, why in sv.decide(st, time.monotonic(), pct / 100.0, {"S2"}):
                                agent.keys(sv.KEYS[what])
                                ev({"kind": "press", "what": what, "why": why})
                        time.sleep(1.0)
                    ev({"kind": "phase_end", "cycle": cyc, "phase": phase, "t0": p0, "t1": r.ns()})
                    if phase == "W":  # back to the stand for F (a GM line, no walk)
                        cr.gm_line(agent, screen, f"@warp {STAND[0]} {STAND[1]} {STAND[2]}",
                                   "crusader")  # fmt: skip
                        bench.close_chat(agent, screen)
                        time.sleep(2.0)
        except r.Stop as exc:
            reason = f"stop: {exc}"
            raise
        finally:
            ev({"kind": "trial_end", "reason": reason})
            for cmd in ("@killmonster2", "@heal", f"@warp {STAND[0]} {STAND[1]} {STAND[2]}"):
                cr.gm_line(agent, screen, cmd, "crusader")
                time.sleep(0.8)
            bench.close_chat(agent, screen)
            print(r.to_png(screen.full(), r.SHOTS / f"regen-{sid}.png"), flush=True)
    t1 = r.ns()
    evf.close()
    events, _ = rs.write_packets(out, t0, t1)
    man = {"sid": sid, "t0_ns": t0, "t1_ns": t1, "cycles": a.cycles, "phase_s": a.phase_s,
           "deficit": DEFICIT, "packets": len(events), "reason": reason}  # fmt: skip
    (out / "manifest.json").write_text(json.dumps(man, indent=1))
    print(json.dumps({"sid": sid, "reason": reason, "packets": len(events)}), flush=True)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)  # fmt: skip
    sub = ap.add_subparsers(dest="cmd", required=True)
    t = sub.add_parser("run")
    t.add_argument("--cycles", type=int, default=2)
    t.add_argument("--phase-s", type=float, default=60.0)
    t.add_argument("--label", default="r")
    j = sub.add_parser("judge")
    j.add_argument("sid")
    a = ap.parse_args()
    if a.cmd == "judge":
        print(json.dumps(judge(*load(a.sid)), indent=1))
        return 0
    return run(a)


if __name__ == "__main__":
    sys.exit(main())
