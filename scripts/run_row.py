#!/usr/bin/env python3
"""The STANDARD RUN ROW (Batt 2026-10-18 night, "standard columns in every run row"): one column
per hunt-flow run, beside Batt's demo, on the rulers the night's verdicts use. OFFLINE: packets
are ground truth here (ADR-0007) and never a bot decision (rule 1).

    run_row.py SID [SID ...] [--fresh] [--json] [--pool]

Each run needs flow_judge.json (``--fresh`` writes it first: flow_judge.bot). The columns:
- engagements; landing within 5 s of the 1st click (Wilson 95);
- kills / h; kills per sighting (kills / h per monster seen / 10 min, windowed); seconds per kill
  (the judged window / our kills); monsters seen / 10 min (windowed);
- free targets attacked within 10 s (search_study.turn_toward's FREE entries);
- the GM's moving share while steering (the runner's steer spans, packets; arm_judge.mode_spans);
- seen -> click p50; death -> next click p50;
- dead calls without a real death (flow_judge.dead_calls);
- LOOT COMPLETENESS (Batt 2026-10-20, the loot block's primary; loot_complete.py): items picked
  / dropped by ALL our kills (packets), and the fates' split: left behind (out of our sight) /
  looters / expired, with their counts; Batt's demo 61 / 63 = 96.8 %, 0 / 3 / 0 %;
  and NET of looter re-drops (Batt 2026-10-20's step 4: a looter we kill drops our item again,
  the same item counted once; loot_complete.link_redrops), with the items recovered so: his demo
  61 / 61 = 100 % (2);
- loot: items picked / dropped at the kills of engagements ended "dead", and lost to looters
  (arm_judge.item_fates; the older, narrower base);
- reversals / min, and outside loot steps (Batt 2026-10-19: the bot's loot steps from its own log,
  his demo's from packets, kill -> its last pickup request; his demo: 4.28 / min); Creamy (our
  damaging hits / attack requests on job 1018), and Creamy hits per hour of the judged window
  (Batt 2026-10-19: the steer walk-guard change's cost);
- hard bars: NPC contacts / map changes / non-Creamy non-target jobs hit;
- kill -> loot start (3.87's ruler: the kill's vanish packet -> the loot step's start, the
  engagements the runner ended "dead"), mean / p50; the run's end reason (its manifest).
BATT is the demo's fixed benchmark (competition.md; Batt's night order): 300 kills / h, 44 seen,
6.82 per sighting, 12.0 s per kill, 78 % of free targets, steer moving 92 %, seen -> click 1.11 s,
death -> next 1.24 s, landing 100 %, loot 97 %, reversals 3.6 / min.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

DEMO = Path("/dev/shm/poring-lab-demo")
NS = 1_000_000_000
GM = 2000002
CREAMY = 1018
BATT = {
    "engagements": "66", "landing within 5 s": "100 %", "kills / h": "300.0",
    "kills per sighting": "6.82", "s per kill": "12.0", "seen / 10 min": "44.0",
    "free targets attacked <= 10 s": "78 %", "steer moving share": "92 %",
    "seen -> click p50 s": "1.11", "death -> next p50 s": "1.24",
    "dead calls without a real death": "-",
    "LOOT COMPLETENESS (all our kills)": "61/63 = 96.8 %",
    "  left behind / looters / expired": "0 / 3 / 0 % (0 / 2 / 0)",
    "  net of looter re-drops (recovered)": "61/61 = 100.0 % (2)",
    "loot picked / dropped (looters)": "97 %",
    "reversals / min": "3.6", "reversals outside loot / min": "4.28",
    "Creamy hits (requests)": "-", "Creamy hits / h": "-",
    "hard bars NPC / map / other": "-",
    "kill -> loot start mean / p50 s": "-", "end reason": "-",
}  # fmt: skip


def kill_to_loot_start(events: Iterable[Mapping[str, Any]],
                       engagements: Iterable[Mapping[str, Any]],
                       gid_by_k: Mapping[int, Any]) -> list[float]:  # fmt: skip
    """PURE (3.87's ruler, expdead_null.py): per engagement the runner ended "dead" with a loot
    step, the kill's first vanish (reason 1) of its gid from 1 s before its last click to 3 s after
    its end -> the loot step's start (its end minus its duration), seconds."""
    van: dict[int, list[int]] = {}
    for e in events:
        if e.get("type") == "entity_vanish" and int(e.get("reason", -1)) == 1:
            van.setdefault(int(e.get("gid") or -1), []).append(int(e["t_mono_ns"]))
    out = []
    for x in engagements:
        if x.get("result") != "dead":
            continue
        g = gid_by_k.get(int(x["k"]))
        loot = x.get("loot") or {}
        t_end = int(x.get("t_end") or 0)
        if g is None or loot.get("s") is None or not t_end:
            continue
        t0 = int(x.get("t_last_click") or x["t_first_click"]) - NS
        vs = sorted(t for t in van.get(int(g), []) if t0 <= t <= t_end + 3 * NS)
        if vs:
            out.append((t_end - vs[0]) / NS - float(loot["s"]))
    return out


def creamy(events: Iterable[Mapping[str, Any]], t0: int, w1: int) -> tuple[int, int]:
    """PURE: (our damaging hits, our attack requests) on a unit that IS a Creamy at that moment
    (its latest appear's job: rAthena reuses a dead mob's id for a later spawn), in [t0, w1)."""
    job: dict[int, int] = {}
    hits = reqs = 0
    for e in sorted(events, key=lambda x: int(x["t_mono_ns"])):
        if e.get("type") == "entity_appear" and e.get("objtype") == 5:
            job[int(e["gid"])] = int(e.get("job", -1))
            continue
        t = int(e["t_mono_ns"])
        if not t0 <= t < w1 or job.get(int(e.get("target_gid") or -1)) != CREAMY:
            continue
        if e.get("type") == "attack_request":
            reqs += 1
        elif (e.get("type") == "act" and int(e.get("src_gid") or -1) == GM
              and int(e.get("damage") or 0) > 0):  # fmt: skip
            hits += 1
    return hits, reqs


def steer_moving_share(fld: Any, bot_events: Sequence[Mapping[str, Any]], t0: int, w1: int,
                       dt_s: float = 0.1) -> float | None:  # fmt: skip
    """The GM's moving share (packets) over the runner's steer spans in [t0, w1)."""
    import arm_judge as aj

    dt = int(dt_s * NS)
    n = m = 0
    for a, b in aj.mode_spans(bot_events, "steer", t0, w1):
        for t in range(a, b, dt):
            n += 1
            m += fld.is_moving(t)
    return round(m / n, 3) if n else None


def row(sid: str, fresh: bool = False) -> dict[str, Any]:
    import arm_judge as aj
    import flow_judge as fj
    import hunt_core as hc
    import search_study as ss

    o = fj.bot(sid) if fresh else json.loads((DEMO / sid / "flow_judge.json").read_text())
    sess = ss.load_session(sid)
    fld = ss.Field(sess.events)
    tt = ss.turn_toward(fld, sess.t0, sess.w1)["free_any"]
    pos = hc.walk_positions(sess.events)
    items = aj.item_fates(sess.events, pos, fj.mob_at)
    kills = dict((g, t) for t, g in aj.kills_of(sess.events))
    rows = {int(r_["k"]): r_ for r_ in o["engagements_w"]["rows"]}
    loot = {"items": 0, "picked": 0, "looter": 0}
    for x in sess.engagements:
        g = (rows.get(int(x["k"])) or {}).get("gid")
        if x.get("result") != "dead" or g is None or g not in kills:
            continue
        for f in aj.drops_of_kill(items, kills[g], fj.mob_at(pos, g, kills[g] - 1)):
            loot["items"] += 1
            loot["picked"] += items[f]["fate"] == "picked"
            loot["looter"] += items[f]["fate"] == "looter"
    t0 = sess.t0
    w1 = t0 + int(float(o["window_s"]) * NS)
    hits, reqs = creamy(sess.events, t0, w1)
    hb = o.get("hard_bars") or {}
    others = [j for j in hb.get("non_target_jobs_hit", []) if j != CREAMY]
    ew = o["engagements_w"]
    dc = o.get("dead_calls") or fj.dead_calls(sess.events, sess.engagements, ew["rows"], t0, w1)
    kps = fj.kills_per_sighting(o)
    ibk = (o.get("idle_between_kills") or {}).get("p50_p90") or [
        (o.get("idle_between_kills") or {}).get("p50")
    ]
    sm = steer_moving_share(fld, sess.bot_events, t0, w1)
    import loot_complete as lc

    lcs = lc.summary(lc.session_rows(sid, sess))
    lc_c, lc_f = lc.cells(lcs)
    kls = kill_to_loot_start(sess.events, sess.engagements,
                             {int(r_["k"]): r_.get("gid") for r_ in ew["rows"]})  # fmt: skip
    try:
        man = json.loads((DEMO / sid / "manifest.json").read_text())
    except (OSError, ValueError):
        man = {}
    return {
        "session": sid,
        "engagements": ew["engagements"],
        "landing within 5 s": f"{ew['hit_within_w']}/{ew['counted']} = "
        f"{100 * (ew['rate'] or 0):.1f} % ({100 * ew['wilson95'][0]:.1f}-"
        f"{100 * ew['wilson95'][1]:.1f})",
        "kills / h": o["kills_per_hour"],
        "kills per sighting": kps,
        "s per kill": round(float(o["window_s"]) / o["kills"], 1) if o.get("kills") else None,
        "seen / 10 min": o.get("sight_per_10min_win", o.get("sight_per_10min")),
        "free targets attacked <= 10 s": None if tt.get("attacked_10s") is None
        else f"{100 * tt['attacked_10s']:.0f} % (n {tt.get('n')})",
        "steer moving share": None if sm is None else f"{100 * sm:.0f} %",
        "seen -> click p50 s": o["reaction_s"]["seen_to_click"][0],
        "death -> next p50 s": ibk[0] if ibk else None,
        "dead calls without a real death": f"{dc['without_death']}/{dc['called']} = "
        f"{100 * (dc['share'] or 0):.1f} %",
        "LOOT COMPLETENESS (all our kills)": lc_c,
        "  left behind / looters / expired": lc_f,
        "  net of looter re-drops (recovered)": f"{lcs['picked']}/{lcs['items'] - lcs['redrops']}"
        f" = {100 * lcs['picked'] / max(1, lcs['items'] - lcs['redrops']):.1f} % "
        f"({lcs['recovered']})",
        "loot picked / dropped (looters)": f"{loot['picked']}/{loot['items']} = "
        f"{100 * loot['picked'] / max(1, loot['items']):.0f} % ({loot['looter']})",
        "reversals / min": (o.get("heading") or {}).get("reversals_per_min"),
        "reversals outside loot / min": (o.get("heading") or {}).get(
            "reversals_outside_loot_per_min"),  # fmt: skip
        "Creamy hits (requests)": f"{hits} ({reqs})",
        "Creamy hits / h": round(hits / (float(o["window_s"]) / 3600), 2) if o.get("window_s")
        else None,
        "hard bars NPC / map / other": f"{hb.get('npc_contacts')} / {hb.get('map_changes')} / "
        f"{len(others)}",
        "kill -> loot start mean / p50 s": None if not kls else
        f"{sum(kls) / len(kls):.2f} / {sorted(kls)[len(kls) // 2]:.2f} (n {len(kls)})",
        "end reason": str(man.get("ended") or "-")[:60],
    }  # fmt: skip


_FRAC = re.compile(r"^(\d+)/(\d+) = ")
_PCT_N = re.compile(r"^(\d+) % \(n (\d+)\)$")
_LOOT = re.compile(r"^(\d+)/(\d+) = \d+ % \((\d+)\)$")
_LCF = re.compile(r"^\d+ / \d+ / \d+ % \((\d+) / (\d+) / (\d+)\)$")
_NET = re.compile(r"^(\d+)/(\d+) = [\d.]+ % \((\d+)\)$")
_KLS = re.compile(r"^([\d.]+) / ([\d.]+) \(n (\d+)\)$")
_CREAMY = re.compile(r"^(\d+) \((\d+)\)$")
_BARS = re.compile(r"^(\S+) / (\S+) / (\S+)$")


def pool(rows_: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """PURE: the POOLED column of several runs (Batt's night report: "the bot-vs-Batt table for the
    best base"). Counts are summed (landing, dead calls, loot, Creamy, hard bars: the fractions are
    re-taken from the sums, landing with its Wilson 95); rates are the MEAN of the runs (kills / h,
    per sighting, seen / 10 min, steer moving, reversals: the runs are equal time boxes); s per
    kill is 3600 / that kills / h; free targets and kill -> loot start mean are n-weighted; the two
    p50 columns are the mean of the runs' p50s ("p50" stays the runs' own ruler)."""
    import hunt_core as hc

    n = len(rows_)

    def vals(k: str) -> list[float]:
        return [float(r[k]) for r in rows_ if r.get(k) is not None]

    def mean(k: str, nd: int = 2) -> float | None:
        v = vals(k)
        return round(sum(v) / len(v), nd) if v else None

    def fracs(k: str, rx: re.Pattern[str]) -> list[tuple[int, ...]]:
        out = []
        for r in rows_:
            m = rx.match(str(r.get(k) or ""))
            if m:
                out.append(tuple(int(g) for g in m.groups()))
        return out

    out: dict[str, Any] = {
        "session": f"pooled ({n} runs)",
        "engagements": sum(int(r.get("engagements") or 0) for r in rows_),
    }
    lk, ln = (sum(x) for x in zip(*fracs("landing within 5 s", _FRAC), strict=True)) if fracs(
        "landing within 5 s", _FRAC) else (0, 0)  # fmt: skip
    if ln:
        lo, hi = hc.wilson(lk, ln)
        out["landing within 5 s"] = (f"{lk}/{ln} = {100 * lk / ln:.1f} % "
                                     f"({100 * lo:.1f}-{100 * hi:.1f})")  # fmt: skip
    kph = mean("kills / h", 1)
    out["kills / h"] = kph
    out["kills per sighting"] = mean("kills per sighting")
    out["s per kill"] = round(3600 / kph, 1) if kph else None
    out["seen / 10 min"] = mean("seen / 10 min", 1)
    ft = fracs("free targets attacked <= 10 s", _PCT_N)
    if ft:
        nn = sum(b for _a, b in ft)
        out["free targets attacked <= 10 s"] = (f"{sum(a * b for a, b in ft) / nn:.0f} % "
                                                f"(n {nn})")  # fmt: skip
    sm = [float(str(r["steer moving share"]).rstrip(" %")) for r in rows_
          if r.get("steer moving share")]  # fmt: skip
    out["steer moving share"] = f"{sum(sm) / len(sm):.0f} %" if sm else None
    out["seen -> click p50 s"] = mean("seen -> click p50 s")
    out["death -> next p50 s"] = mean("death -> next p50 s")
    dc = fracs("dead calls without a real death", _FRAC)
    if dc:
        a, b = sum(x[0] for x in dc), sum(x[1] for x in dc)
        out["dead calls without a real death"] = f"{a}/{b} = {100 * a / max(1, b):.1f} %"
    lcp = fracs("LOOT COMPLETENESS (all our kills)", _FRAC)
    lcf = fracs("  left behind / looters / expired", _LCF)
    if lcp:
        a, b = sum(x[0] for x in lcp), sum(x[1] for x in lcp)
        out["LOOT COMPLETENESS (all our kills)"] = f"{a}/{b} = {100 * a / max(1, b):.1f} %"
        if len(lcf) == len(lcp):
            o_, l_, e_ = (sum(x[i] for x in lcf) for i in range(3))
            nb = max(1, b)
            out["  left behind / looters / expired"] = (
                f"{100 * o_ / nb:.0f} / {100 * l_ / nb:.0f} / {100 * e_ / nb:.0f} % "
                f"({o_} / {l_} / {e_})")  # fmt: skip
    nt = fracs("  net of looter re-drops (recovered)", _NET)
    if nt:
        a, b, c = (sum(x[i] for x in nt) for i in range(3))
        out["  net of looter re-drops (recovered)"] = (
            f"{a}/{b} = {100 * a / max(1, b):.1f} % ({c})")  # fmt: skip
    lt = fracs("loot picked / dropped (looters)", _LOOT)
    if lt:
        a, b, c = (sum(x[i] for x in lt) for i in range(3))
        out["loot picked / dropped (looters)"] = f"{a}/{b} = {100 * a / max(1, b):.0f} % ({c})"
    out["reversals / min"] = mean("reversals / min")
    out["reversals outside loot / min"] = mean("reversals outside loot / min")
    cr = fracs("Creamy hits (requests)", _CREAMY)
    if cr:
        out["Creamy hits (requests)"] = f"{sum(x[0] for x in cr)} ({sum(x[1] for x in cr)})"
    out["Creamy hits / h"] = mean("Creamy hits / h")
    bars = [_BARS.match(str(r.get("hard bars NPC / map / other") or "")) for r in rows_]
    if all(bars):
        tot = [sum(int(m.group(i)) for m in bars if m and m.group(i).isdigit()) for i in (1, 2, 3)]
        out["hard bars NPC / map / other"] = " / ".join(str(t) for t in tot)
    kl = [tuple(float(g) for g in _KLS.match(str(r.get("kill -> loot start mean / p50 s")))
                .groups()) for r in rows_
          if _KLS.match(str(r.get("kill -> loot start mean / p50 s") or ""))]  # fmt: skip
    if kl:
        nn = sum(x[2] for x in kl)
        out["kill -> loot start mean / p50 s"] = (
            f"{sum(x[0] * x[2] for x in kl) / nn:.2f} / {sum(x[1] for x in kl) / len(kl):.2f} "
            f"(n {int(nn)})")  # fmt: skip
    ends = [str(r.get("end reason") or "-") for r in rows_]
    out["end reason"] = ", ".join(f"{e} x{ends.count(e)}" for e in dict.fromkeys(ends))[:60]
    return out


def box_table(cols: Sequence[tuple[str, Mapping[str, Any]]]) -> str:
    """PURE: a box-drawing table, one column per run (the metric names down the left)."""
    names = [k for k in BATT]
    w0 = max(len(n) for n in names + ["METRIC"])
    ws = [max(len(h), *(len(str(c.get(n, "-"))) for n in names)) for h, c in cols]

    def line(l_: str, m_: str, r_: str) -> str:  # noqa: E306
        return l_ + m_.join("─" * (w + 2) for w in [w0, *ws]) + r_

    out = [line("┌", "┬", "┐"),
           "│ " + " │ ".join([("METRIC").ljust(w0)] + [h.center(w) for (h, _), w in
                                                       zip(cols, ws, strict=True)]) + " │",
           line("├", "┼", "┤")]  # fmt: skip
    for n in names:
        out.append(
            "│ "
            + " │ ".join(
                [n.ljust(w0)]
                + [
                    str(c.get(n, "-") if c.get(n) is not None else "-").ljust(w)
                    for (_h, c), w in zip(cols, ws, strict=True)
                ]
            )
            + " │"
        )
    out.append(line("└", "┴", "┘"))
    return "\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)  # fmt: skip
    ap.add_argument("sessions", nargs="+")
    ap.add_argument("--fresh", action="store_true", help="flow_judge.bot first (writes its json)")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--pool", action="store_true", help="add the pooled column (run_row.pool)")
    a = ap.parse_args()
    rows_ = [row(s, a.fresh) for s in a.sessions]
    if a.pool:
        rows_.append(pool(rows_))
    if a.json:
        print(json.dumps(rows_, indent=1, default=str))
        return 0
    cols = [("BATT demo", BATT)] + [
        (
            r_["session"][:15].replace("2026", "") if r_["session"][0].isdigit() else r_["session"],
            r_,
        )
        for r_ in rows_
    ]
    print(box_table(cols))
    return 0


if __name__ == "__main__":
    sys.exit(main())
