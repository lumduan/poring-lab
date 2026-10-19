#!/usr/bin/env python3
"""battle_log.py's lines against PACKETS, offline (Batt 2026-10-19). Packets are ground truth for
JUDGING only (ADR-0007): nothing here reaches the bot.

    battle_log_judge.py SID [SID ...] [--json]

Per session (/dev/shm/poring-lab-demo/SID/: packets.jsonl.gz, battle_log.jsonl and
battle_log_frames.jsonl from `battle_log.py replay SID`):
- DAMAGE lines <-> our GM's damaging hits (act, src 2000002, damage > 0, not the pickup motion):
  the value N vs the packet's damage, the NAME vs the unit's species (the job / name of its
  LATEST entity_appear before the hit: rAthena reuses gids), the latency (the line's first
  visible frame - the act packet);
- BASE / JOB EXP lines <-> OUR kills (arm_judge.kills_of: the unit vanished dead <= 1.5 s after
  our damaging hit): the latency (line - the vanish), the share of kills with an EXP line and of
  EXP lines with a kill; N vs the base_exp / job_exp stat_change delta at the kill;
- ITEM lines <-> our pickups (pickup_result ok): the count vs the packet's amount, the latency;
- with engagements.json: the BASE EXP line as a dead signal against the bot's own dead call.
A line is matched to the nearest unmatched truth event of its kind with truth in
[line - MAX_LAT_S, line + LEAD_S] (frames are taken after the packet: the recorded frame shows
the client ~0.5 s behind the server), the equal value first. Recall counts only truth inside
the frames' span (first frame .. last frame - MAX_LAT_S). Every miss gets a reason from the
reader's per-frame trace: other_tab (the chat showed another tab), frame_gap (no frame for
> GAP_S around it), overflow (>= 3 new lines in one frame interval: any beyond 3 were never
visible), garbage / held (a spoiled frame), misread (a line of another type at that time), or
unseen.
"""

from __future__ import annotations

import argparse
import bisect
import gzip
import json
import sys
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import arm_judge as aj  # noqa: E402

DEMO = Path("/dev/shm/poring-lab-demo")
NS = 1_000_000_000
GM = 2000002
MAX_LAT_S = 3.0  # a line this long after its truth event still matches it
LEAD_S = 0.3  # ... and a truth event this long after the line (clock noise)
GAP_S = 0.5  # a frame gap this long around a miss is a frame drop
SPECIES = {1002: "Poring", 1063: "Lunatic", 1008: "Pupa", 1113: "Drops", 1018: "Creamy",
           1007: "Fabre", 1052: "Rocker", 1011: "Chonchon", 1010: "Willow"}  # fmt: skip


def q(v: Sequence[float], p: float) -> float | None:
    return aj.q(v, p)


# --- truth from packets --------------------------------------------------------------------------


def hits_of(packets: Sequence[Mapping[str, Any]], gm: int = GM) -> list[dict[str, Any]]:
    """PURE: our damaging hits [{t, gid, damage, species}] (the species of the target's latest
    appearance before the hit)."""
    seen: dict[int, str | None] = {}
    out = []
    for e in packets:
        typ = e.get("type")
        if typ == "entity_appear" and e.get("objtype") == 5 and e.get("gid") is not None:
            job = e.get("job")
            known = job is not None and int(job) in SPECIES
            seen[int(e["gid"])] = SPECIES[int(job)] if known else e.get("name")
        elif (typ == "act" and e.get("src_gid") == gm and int(e.get("damage") or 0) > 0
              and e.get("kind") != "pickup"):  # fmt: skip
            g = int(e.get("target_gid") or -1)
            out.append({"t": int(e["t_mono_ns"]), "gid": g, "damage": int(e["damage"]),
                        "species": seen.get(g)})  # fmt: skip
    return out


def exp_deltas(packets: Sequence[Mapping[str, Any]], name: str) -> list[tuple[int, int]]:
    """PURE: [(t, delta)] of the cumulative ``name`` (base_exp / job_exp) stat, not from GM
    commands; a level-up (the value drops) is skipped."""
    out = []
    last: int | None = None
    for e in packets:
        if e.get("type") != "stat_change" or e.get("name") != name:
            continue
        v = int(e.get("value") or 0)
        if last is not None and not e.get("gm_command") and v > last:
            out.append((int(e["t_mono_ns"]), v - last))
        last = v
    return out


def kills_with_exp(packets: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """PURE: our kills [{t, gid, base, job}] with the EXP deltas that came for them (within
    1.5 s before .. 0.5 s after the vanish)."""
    base, job = exp_deltas(packets, "base_exp"), exp_deltas(packets, "job_exp")
    out = []
    for t, g in aj.kills_of(packets):
        b = next((d for tb, d in base if t - 1.5 * NS <= tb <= t + 0.5 * NS), None)
        j = next((d for tj, d in job if t - 1.5 * NS <= tj <= t + 0.5 * NS), None)
        out.append({"t": t, "gid": g, "base": b, "job": j})
    return out


def pickups_of(packets: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return [{"t": int(e["t_mono_ns"]), "amount": int(e.get("amount") or 0),
             "item_id": e.get("item_id")}
            for e in packets if e.get("type") == "pickup_result" and e.get("ok")]  # fmt: skip


def drops_of(packets: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return [{"t": int(e["t_mono_ns"]), "amount": int(e.get("amount") or 0)}
            for e in packets if e.get("type") == "drop_result" and e.get("ok")]  # fmt: skip


# --- matching ----------------------------------------------------------------------------------


def match(lines: Sequence[Mapping[str, Any]], truth: Sequence[Mapping[str, Any]],
          line_val: str | None = None, truth_val: str | None = None,
          max_lat_s: float = MAX_LAT_S, lead_s: float = LEAD_S
          ) -> list[tuple[int, int | None]]:  # fmt: skip
    """PURE: [(line index, truth index or None)], lines in time order, each to the EARLIEST
    unmatched truth event in [line - max_lat, line + lead] -- the one with the equal value
    (``line_val`` / ``truth_val``) when there is one. Earliest, because the log is in order: the
    oldest unmatched hit is the one this line reports."""
    ts = [int(x["t"]) for x in truth]
    used: set[int] = set()
    out = []
    for i in sorted(range(len(lines)), key=lambda k: int(lines[k]["t_ns"])):
        tl = int(lines[i]["t_ns"])
        lo = bisect.bisect_left(ts, tl - int(max_lat_s * NS))
        hi = bisect.bisect_right(ts, tl + int(lead_s * NS))
        cand = [j for j in range(lo, hi) if j not in used]
        if line_val and truth_val and lines[i].get(line_val) is not None:
            same = [j for j in cand if truth[j].get(truth_val) == lines[i][line_val]]
            cand = same or cand
        j = cand[0] if cand else None
        if j is not None:
            used.add(j)
        out.append((i, j))
    return out


def miss_reason(t: int, trace: Sequence[Mapping[str, Any]], tts: Sequence[int],
                lines: Sequence[Mapping[str, Any]]) -> str:  # fmt: skip
    """Why a truth event at ``t`` got no line: the reader's frames in [t - 0.5 s, t + MAX_LAT]."""
    lo = bisect.bisect_left(tts, t - NS // 2)
    hi = bisect.bisect_right(tts, t + int(MAX_LAT_S * NS))
    win = trace[lo:hi]
    if not win:
        return "no_frames"
    gaps = [(tts[k + 1] - tts[k]) / NS for k in range(max(lo - 1, 0), min(hi, len(tts) - 1))]
    if any(x.get("other_tab") for x in win):
        return "other_tab"
    if gaps and max(gaps) > GAP_S:
        return "frame_gap"
    if any(x.get("overflow") for x in win):
        return "overflow"
    if any(x.get("garbage") or x.get("held") for x in win):
        return "garbage"
    near = [x for x in lines if t - NS // 2 <= int(x["t_ns"]) <= t + int(MAX_LAT_S * NS)
            and (x["type"] == "other" or not x.get("clean", True))]  # fmt: skip
    if near:
        return "misread"
    return "unseen"


def _emit_delays(ls: Sequence[Mapping[str, Any]]) -> list[float | None]:
    d = [(int(x["t_emit_ns"]) - int(x["t_ns"])) / NS for x in ls if x.get("t_emit_ns")]
    return [q(d, 0.5), q(d, 0.9), round(max(d), 2) if d else None]


def _values(val: Sequence[tuple[Any, Any]]) -> dict[str, Any]:
    """Read value vs truth value over the matched pairs."""
    return {"read": sum(1 for a, _ in val if a is not None),
            "equal": sum(1 for a, b in val if a is not None and a == b),
            "no_truth_value": sum(1 for a, b in val if a is not None and b is None),
            "wrong": [(a, b) for a, b in val
                      if a is not None and b is not None and a != b][:10]}  # fmt: skip


def _rate(a: int, b: int) -> float | None:
    return round(a / b, 3) if b else None


def judge(packets: Sequence[Mapping[str, Any]], lines: Sequence[Mapping[str, Any]],
          trace: Sequence[Mapping[str, Any]]) -> dict[str, Any]:  # fmt: skip
    """PURE: the per-type tables of one session."""
    trace = sorted(trace, key=lambda x: int(x["t"]))
    tts = [int(x["t"]) for x in trace]
    t_lo = tts[0] if tts else 0
    t_hi = (tts[-1] - int(MAX_LAT_S * NS)) if tts else 0
    lines = [dict(x) for x in sorted(lines, key=lambda r: (int(r["t_ns"]), int(r.get("slot", 0))))]
    out: dict[str, Any] = {"lines": dict(Counter(x["type"] for x in lines)),
                           "frames": len(trace)}  # fmt: skip

    def table(kind: str, truth: list[dict[str, Any]], lv: str | None, tv: str | None,
              lat_from: str = "t") -> tuple[dict[str, Any], list[tuple[int, int | None]],
                                             list[dict[str, Any]]]:  # fmt: skip
        ls = [x for x in lines if x["type"] == kind]
        pairs = match(ls, truth, lv, tv)
        lat = [(int(ls[i]["t_ns"]) - int(truth[j][lat_from])) / NS for i, j in pairs
               if j is not None]  # fmt: skip
        matched = {j for _, j in pairs if j is not None}
        inside = [k for k, x in enumerate(truth) if t_lo <= int(x["t"]) <= t_hi]
        missed = [k for k in inside if k not in matched]
        reasons = Counter(miss_reason(int(truth[k]["t"]), trace, tts, lines) for k in missed)
        tab = {"n_lines": len(ls), "n_truth": len(inside),
               "precision": _rate(sum(1 for _, j in pairs if j is not None), len(ls)),
               "recall": _rate(len(inside) - len(missed), len(inside)),
               "latency_p50_p90_s": [q(lat, 0.5), q(lat, 0.9)],
               "latency_min_max_s": [round(min(lat), 2), round(max(lat), 2)] if lat else None,
               # a live reader returns a line this long after its first frame (hold / refine)
               "emit_delay_p50_p90_max_s": _emit_delays(ls),
               "miss_reasons": dict(reasons),
               "unmatched_lines": [{"t_ns": ls[i]["t_ns"], "frame": ls[i].get("frame"),
                                    "text": ls[i].get("text")} for i, j in pairs
                                   if j is None][:20]}  # fmt: skip
        return tab, pairs, ls

    # DAMAGE
    hits = hits_of(packets)
    tab, pairs, ls = table("damage", hits, "n", "damage")
    val = [(ls[i].get("n"), hits[j]["damage"]) for i, j in pairs if j is not None]
    nam = [(ls[i].get("name"), hits[j]["species"]) for i, j in pairs if j is not None]
    tab["value"] = _values(val)
    tab["name"] = {"read": sum(1 for a, _ in nam if a is not None),
                   "equal": sum(1 for a, b in nam if a is not None and a == b),
                   "wrong": Counter(f"{a}->{b}" for a, b in nam
                                    if a is not None and a != b).most_common(10),
                   "unread": Counter(str(b) for a, b in nam if a is None).most_common(10),
                   "species_truth": dict(Counter(str(b) for _, b in nam))}  # fmt: skip
    out["damage"] = tab

    # EXP <-> kills
    kills = kills_with_exp(packets)
    for kind, field in (("base_exp", "base"), ("job_exp", "job")):
        tab, pairs, ls = table(kind, kills, "n", field)
        val = [(ls[i].get("n"), kills[j][field]) for i, j in pairs if j is not None]
        tab["value"] = _values(val)
        tab["kills_with_line"] = tab.pop("recall")
        tab["lines_with_kill"] = tab.pop("precision")
        out[kind] = tab
    # the EXP packet itself (any source of EXP, not only our kills)
    base = [{"t": t, "d": d} for t, d in exp_deltas(packets, "base_exp")]
    tab, _, _ = table("base_exp", base, "n", "d")
    out["base_exp_vs_exp_packet"] = {k: tab[k] for k in ("precision", "recall",
                                                          "latency_p50_p90_s")}  # fmt: skip

    # ITEM <-> pickups
    picks = pickups_of(packets)
    tab, pairs, ls = table("item", picks, "count", "amount")
    val = [(ls[i].get("count"), picks[j]["amount"]) for i, j in pairs if j is not None]
    tab["count"] = _values(val)
    out["item"] = tab
    out["other"] = {"n": sum(1 for x in lines if x["type"] == "other"),
                    "drops_in_frames": sum(1 for d in drops_of(packets)
                                           if t_lo <= int(d["t"]) <= t_hi),
                    "texts": Counter(str(x.get("text"))[:60] for x in lines
                                     if x["type"] == "other").most_common(12)}  # fmt: skip
    return out


def dead_vs_bot(engagements: Sequence[Mapping[str, Any]], kills: Sequence[Mapping[str, Any]],
                lines: Sequence[Mapping[str, Any]]) -> dict[str, Any]:  # fmt: skip
    """PURE: the BASE EXP line as a "dead" signal against the bot's own dead call. Per
    engagement the bot called dead (its loot step's start: t_end - loot.s), the server kill of
    ours nearest to it in [call - 10 s, call + 2 s] (none: ``no_kill_near`` -- the call was
    false, or its kill came later) and the first BASE EXP line after that kill (<= MAX_LAT_S):
    line - kill, bot call - kill, and how much earlier the line came than the bot's call."""
    kts = sorted(int(k["t"]) for k in kills)
    lts = sorted(int(x["t_ns"]) for x in lines if x["type"] == "base_exp")
    line_lat, bot_lat, gain = [], [], []
    false_dead = no_line = 0
    for x in engagements:
        loot = x.get("loot") or {}
        if x.get("result") != "dead" or not x.get("t_end") or loot.get("s") is None:
            continue
        t_call = int(x["t_end"]) - int(float(loot["s"]) * NS)
        near = [t for t in kts if t_call - 10 * NS <= t <= t_call + 2 * NS]
        if not near:
            false_dead += 1
            continue
        tk = min(near, key=lambda t: abs(t - t_call))
        j = bisect.bisect_left(lts, tk - int(LEAD_S * NS))
        if j >= len(lts) or lts[j] - tk > MAX_LAT_S * NS:
            no_line += 1
            continue
        line_lat.append((lts[j] - tk) / NS)
        bot_lat.append((t_call - tk) / NS)
        gain.append((t_call - lts[j]) / NS)
    return {"bot_dead_calls_with_kill": len(gain) + no_line, "no_kill_near": false_dead,
            "no_exp_line": no_line,
            "line_after_kill_p50_p90_s": [q(line_lat, 0.5), q(line_lat, 0.9)],
            "bot_call_after_kill_p50_p90_s": [q(bot_lat, 0.5), q(bot_lat, 0.9)],
            "line_earlier_than_bot_p10_p50_p90_s": [q(gain, 0.1), q(gain, 0.5), q(gain, 0.9)],
            "line_earlier_share": _rate(sum(1 for g in gain if g > 0), len(gain))}  # fmt: skip


def load(sid: str, root: Path = DEMO) -> tuple[list[dict[str, Any]], list[dict[str, Any]],
                                                list[dict[str, Any]]]:  # fmt: skip
    d = root / sid
    with gzip.open(d / "packets.jsonl.gz", "rt") as fh:
        packets = sorted((json.loads(x) for x in fh), key=lambda e: int(e["t_mono_ns"]))
    lines = [json.loads(x) for x in (d / "battle_log.jsonl").read_text().splitlines() if x]
    trace = [json.loads(x) for x in (d / "battle_log_frames.jsonl").read_text().splitlines()
             if x]  # fmt: skip
    return packets, lines, trace


def pooled(results: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """Counts summed over sessions (the per-session tables carry the latencies)."""
    out: dict[str, Counter[str]] = {}
    for r in results:
        for kind in ("damage", "base_exp", "job_exp", "item"):
            t = r[kind]
            c = out.setdefault(kind, Counter())
            c["n_lines"] += t["n_lines"]
            c["n_truth"] += t["n_truth"]
            prec = t.get("precision", t.get("lines_with_kill")) or 0.0
            rec = t.get("recall", t.get("kills_with_line")) or 0.0
            c["lines_matched"] += round(prec * t["n_lines"])
            c["truth_found"] += round(rec * t["n_truth"])
    return {
        k: {
            **dict(c),
            "precision": _rate(c["lines_matched"], c["n_lines"]),
            "recall": _rate(c["truth_found"], c["n_truth"]),
        }
        for k, c in out.items()
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)  # fmt: skip
    ap.add_argument("sids", nargs="+")
    a = ap.parse_args()
    res = {}
    for sid in a.sids:
        packets, lines, trace = load(sid)
        res[sid] = judge(packets, lines, trace)
        eng = DEMO / sid / "engagements.json"
        if eng.exists():
            res[sid]["dead_vs_bot"] = dead_vs_bot(json.loads(eng.read_text()),
                                                  kills_with_exp(packets), lines)  # fmt: skip
    if len(res) > 1:
        res["pooled"] = pooled(v for k, v in res.items())
    print(json.dumps(res, indent=1, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
