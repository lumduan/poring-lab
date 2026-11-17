#!/usr/bin/env python3
"""Stage 7's live A/B, s7ab (docs/planning/live-blocks.md 18.7; Batt 2026-11-16, 17 item 6: "A
boss on the screen, at ANY distance: press the Fly Wing first, no Knife swap"): today's runner (A)
against the Fly Wing FIRST (B, dungeon@9.57 --fly-first), on the SAME box -- the ready-made
functions box -- alternating runs on the lab's own Rogue on the lab rAthena's xmas_dun02 (player
mode; the MVP alive).

THE ARMS differ ONLY in one setting block: each arm plays a copy of
services/frontend/src/lib/flow/fixtures/project_xmas_dun02_functions.json whose safety tab's
`fly_first` is False (A) or True (B) and `fly_first_hp` False in both -- set explicitly (arm_doc):
since live-blocks 18.10 #1 / 18.13 the fixture itself holds both ON, and A keeps the dagger-first
order of 9.56 -- through `flow_play.py play` with that copy's own runner settings
(runner-config-A.json / -B.json). `plan` refuses before any input unless: the copies differ in that
block alone; their runner settings differ in fly_first alone and keep the fast alarm on (section
11); their runner argv differ by `--fly-first` alone and their run() arguments, keys and loop not at
all; the checkout's runner is 9.57 (it takes --fly-first) and huntstate_check's `drive` and `check`
hold (every fly-first change a branch whose else is today's code); and the box's step traces equal
the driver's (hunt_trace.compare: the hand scenarios and SEEDS random ones).

THE SETUP before every run: exactly stage2_ab.py's. A STOP file in the series folder
(/dev/shm/poring-lab-tmp/stage7-ab/<label>/STOP) ends the series before its next run.

THE SCORE per run: stage5b2_ab's (kills, loot steps, openers, the tick pace, the record kinds, a
runner exception, the drive's records) and, from the runner session, its packets and the backend's
input log (data/input_log/<UTC date>.jsonl): every fly-first Fly Wing (its read, its send time, the
F4 / F5 keys between them, its use_item_request), the deaths, the boss sightings and the flies by
source, and the economy WITH steals (18.10 #4: econ_db.totals_of, the dashboard's gross / cost / net
an hour; each arm's valid runs pooled; data/econ/lab.sqlite, after `econ_db.py update`). The verdict
applies BAR (18.7). `derive` re-measures 18.2's key-to-request delays over sessions (read-only).

    stage7_ab.py plan   --label s7ab --pairs 4 --minutes 20
    stage7_ab.py run    --label s7ab --pairs 4 --minutes 20
    stage7_ab.py score  --label s7ab [--json]
    stage7_ab.py derive SESSION_DIR [SESSION_DIR ...] [--input-log FILE ...]
"""

from __future__ import annotations

import argparse
import contextlib
import gzip
import io
import json
import sqlite3
import statistics
import sys
import time
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import flow_run as fr  # noqa: E402
import hunt_trace as ht  # noqa: E402
import huntstate_check as hc  # noqa: E402
import stage2_ab as s2  # noqa: E402
import stage4_ab as s4  # noqa: E402
import stage5b2_ab as s5b2  # noqa: E402
import stage5b_ab as s5b  # noqa: E402
import stage5c_ab as s5c  # noqa: E402

VERSION = "9.57"  # dungeon_hunt.FLY_FIRST_VERSION: the runner it measures
NODE = s2.NODE
PROJECT = s4.FIX / "project_xmas_dun02_functions.json"  # the ready-made box (15.6), both arms
ARMS = {"A": "fly_first off: today's runner", "B": "fly_first on: the Fly Wing first (18.4)"}
FLY_TAB, FLY_VAR, FLY_FLAG = "safety", "fly_first", "--fly-first"
SCRATCH = Path("/dev/shm/poring-lab-tmp/stage7-ab")
INPUT_LOG = ROOT / "data" / "input_log"
ECON_DATA = ROOT / "data"  # data/econ/lab.sqlite, the item table, the KB names (econ_db.totals_of)
SEEDS = 50
FLY_KIND = "fly_first"  # the runner's fly-first record (dungeon_hunt 9.57)
SELF_GID = 2000002  # the lab Rogue's block id (her own entity_vanish, reason 1: her death)
WEAPON_KEYS = ("F4", "F5")  # the Knife (the opener) and the dagger: no key of these before the fly
# 18.2: the Fly Wing's request after the runner's own send time, 76 Fly Wings of 2026-11-15:
# median 0.075 s, p95 0.088, max 0.272 -- the bound leaves 0.08 s over the slowest seen
FLY_BOUND_S = 0.35
# THE PRE-REGISTERED BAR (live-blocks.md 18.7, written 2026-11-16 10:51 ICT, before any 9.57 code)
BAR = {
    **{k: v for k, v in s5b2.BAR.items() if k not in ("drive", "deaths", "kinds")},
    "kinds": "every record kind B's runner sessions write is one the 5b-1 runner's source writes "
             "(its literal kinds), one A's sessions wrote, the drive's own (drive), or "
             "fly-first's (fly_first)",
    "deaths": "REPORTED per played run, per arm, not judged: deaths are rare (2 in 7.5 h, 18.2) "
              "and no line compares them against an arm that may read 0 (13.7 / 10.2)",
    "drive": s5c.BAR["drive"],
    "fly_first": "every B fly-first Fly Wing pressed while she was alive: no F4 / F5 key down (the "
                 "backend's input log) between the runner's read of the sighting and the F8, and "
                 f"its use_item_request within {FLY_BOUND_S} s of the F8's send time; judged when "
                 "B made at least one (none: INCONCLUSIVE)",
    "fly_bound_s": FLY_BOUND_S,
}  # fmt: skip


def _quiet(f: Any, *a: Any, **k: Any) -> tuple[int, str]:
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        rc = f(*a, **k)
    return int(rc), out.getvalue()


# --- the arms ------------------------------------------------------------------------------------
# live-blocks 18.13: the block both arms hold OFF -- s7ab measured the boss Fly Wing first alone
# (the ready-made box holds fly_first_hp ON since s8ab passed)
OFF_IN_BOTH = ("fly_first_hp",)
# live-blocks 18.15: the model both arms name -- s7ab (and s8ab) measured xmas02 (xmas02-gb); the
# ready-made box names xmas02sk since 2026-11-17
MEASURED_MODEL = "xmas02"


def arm_doc(arm: str, minutes: float, path: Path = PROJECT) -> dict[str, Any]:
    """PURE but for the read: the box with its time box set to the run's length, its safety tab's
    fly_first block set for the arm (A off, B on), OFF_IN_BOTH off in both and its use_model
    MEASURED_MODEL in both -- every one explicitly, whatever the fixture holds (18.10 #1, 18.13,
    18.15)."""
    d = json.loads(path.read_text())
    d["max_runtime_s"] = int(round(minutes * 60))
    s5c.set_box_model(d, MEASURED_MODEL)
    tab = next((t for t in d["nodes"][0]["tabs"] if t["name"] == FLY_TAB), None)
    if tab is None:
        raise ValueError(f"the box has no tab {FLY_TAB}")
    tab["vars"][FLY_VAR] = {"kind": "lit", "value": arm == "B"}
    for var in OFF_IN_BOTH:
        tab["vars"][var] = {"kind": "lit", "value": False}
    return d


def arm_text(arm: str, minutes: float, path: Path = PROJECT) -> str:
    from poring_flow import project as pj

    return pj.to_json(pj.validate(arm_doc(arm, minutes, path)))


def box_difference(a: Mapping[str, Any], b: Mapping[str, Any]) -> str | None:
    """PURE: B is A with its fly_first block on, and nothing else -- or why not."""
    a, b = json.loads(json.dumps(a)), json.loads(json.dumps(b))
    got: dict[str, Any] = {}
    for arm, d in (("A", a), ("B", b)):
        if s5c.box_model_of(d) != MEASURED_MODEL:  # 18.15: s7ab's arms name xmas02
            return f"{arm}'s use_model is not {MEASURED_MODEL} (s7ab's arms)"
        tab = next((t for t in d["nodes"][0]["tabs"] if t["name"] == FLY_TAB), None)
        lit = None if tab is None else tab["vars"].get(FLY_VAR)
        if not isinstance(lit, Mapping) or lit.get("value") is not (arm == "B"):
            return f"{arm}'s {FLY_TAB} tab does not hold {FLY_VAR} = {arm == 'B'}"
        for var in OFF_IN_BOTH:  # 18.13: s7ab's arms hold the HP Fly Wing first off
            off = tab["vars"].get(var)
            if not isinstance(off, Mapping) or off.get("value") is not False:
                return f"{arm}'s {FLY_TAB} tab does not hold {var} = False (s7ab's arms)"
        got[arm] = tab
        tab["vars"].pop(FLY_VAR)
    if a != b:
        return "B differs from A in more than its fly_first block (an A/B changes one thing)"
    return None


# the runner settings a box text's hunt core takes: stage5c_ab's (one rule for the A/B tools)
vals_of = s5c.vals_of


def runner_problem(runner_text: str) -> str | None:
    """PURE: the checkout's runner is 9.57: it takes --fly-first and records it."""
    if f'FLY_FIRST_VERSION = "{VERSION}"' not in runner_text or f'"{FLY_FLAG}",' not in runner_text:
        return f"the checkout's runner is not dungeon@{VERSION} (no {FLY_FLAG})"
    return None


def plan_doc(label: str, pairs: int, minutes: float, order: str, folder: Path,
             runner_text: str | None = None, base_text: str | None = None,
             check_base: str | None = None,
             seeds: int = SEEDS) -> dict[str, Any] | str:  # fmt: skip
    """PURE but for reads (the fixture, git, the checkout's runner): everything a series will do,
    before any screen is read or any input path opened; a refusal: its words."""
    import flow_play as fp

    from poring_flow import project as pj

    texts = {arm: arm_text(arm, minutes) for arm in ("A", "B")}
    why = box_difference(json.loads(texts["A"]), json.loads(texts["B"]))
    if why is not None:
        return f"refused before any input: {why}"
    vals: dict[str, dict[str, Any]] = {}
    for arm, text in texts.items():
        v = vals_of(text)
        if isinstance(v, str):
            return f"refused before any input: {arm}: {v}"
        vals[arm] = v
    diff = sorted(
        k for k in set(vals["A"]) | set(vals["B"]) if vals["A"].get(k) != vals["B"].get(k)
    )
    if diff != [FLY_VAR] or vals["A"][FLY_VAR] is not False or vals["B"][FLY_VAR] is not True:
        return (f"refused before any input: the arms' runner settings differ in {diff}, not "
                "fly_first alone")  # fmt: skip
    if not (vals["A"].get("garm_fly") and vals["A"].get("alarm_fast")):
        return "refused before any input: the Run config has garm_fly / alarm_fast off (section 11)"
    runner_text = hc.TARGET.read_text() if runner_text is None else runner_text
    bad = runner_problem(runner_text)
    if bad:
        return f"refused before any input: {bad}"
    base_text = hc.git_show(hc.DRIVE_BASE, hc.TARGET) if base_text is None else base_text
    check_base = hc.git_show(hc.BASE_REV, hc.TARGET) if check_base is None else check_base
    proofs = (("drive", _quiet(hc.drive_check, base_text, runner_text)),
              ("check", _quiet(hc.check, check_base, runner_text, drive_ok=True)))  # fmt: skip
    for name, (rc, out) in proofs:
        if rc != 0:
            lines = [
                ln for ln in out.splitlines() if "NO" in ln or "DIFFERS" in ln or "CHANGED" in ln
            ]
            return (f"refused before any input: huntstate_check {name} fails (every fly-first "
                    "change must be a branch whose else is today's code): "
                    f"{'; '.join(lines)[:300]}")  # fmt: skip
    hashes: dict[str, str] = {}
    arms: dict[str, Any] = {}
    argv: dict[str, list[str]] = {}
    for arm, text in texts.items():
        h = pj.project_hash(pj.from_json(text))
        prep = fp.prepare(text, NODE, int(round(minutes * 60)), runner_vals={NODE: vals[arm]},
                          want_hash=h)  # fmt: skip
        if isinstance(prep, str):
            return f"{arm}: {prep}"
        rp = prep.runners[NODE]
        hashes[arm] = h
        argv[arm] = rp.argv("L", None, None)
        arms[arm] = {"what": ARMS[arm], "project": str(PROJECT.relative_to(ROOT)),
                     "fly_first": arm == "B", "project_hash": h, "loop": rp.loop,
                     "left_out": list(rp.tick_left_out), "box": rp.box_kwargs(),
                     "keys": rp.keys}  # fmt: skip
    if FLY_FLAG in argv["A"] or argv["B"].count(FLY_FLAG) != 1:
        return f"refused before any input: {FLY_FLAG} must be in B's runner argv alone"
    if [x for x in argv["B"] if x != FLY_FLAG] != argv["A"]:
        return f"refused before any input: the arms' runner argv differ in more than {FLY_FLAG}"
    for k in ("box", "keys", "loop", "left_out"):
        if arms["A"][k] != arms["B"][k]:
            return f"refused before any input: the arms give the runner different {k}"
    if arms["A"]["loop"] != "hunt_loop" or arms["A"]["left_out"]:
        return "refused before any input: the box must drive its hunt loop with the full tick"
    scns = [*ht.hand_scenarios(), *ht.random_scenarios(seeds)]
    diffs = [f"{s.name}: {r.first_diff}" for s in scns if not (r := ht.compare(s, texts["B"])).same]
    if diffs:
        return (f"refused before any input: the box's hunt loop's step trace is not the driver's "
                f"(hunt_trace.py): {'; '.join(diffs[:3])}")  # fmt: skip
    runs = s2.series(label, pairs, order)
    return {
        "version": VERSION, "label": label, "pairs": pairs, "minutes": minutes, "order": order,
        "arms": arms, "vals": vals, "bar": BAR, "drive_base": hc.DRIVE_BASE,
        "check_base": hc.BASE_REV, "runner_sha256": s5b.sha(runner_text),
        "trace_scenarios": len(scns),
        "serve_s": int(len(runs) * (minutes * 60 + s2.START_GRACE_S + 120) + s2.SERVE_EXTRA_S),
        "runs": [{**asdict(r), "argv": fr.play_command(
            s4.project_file(r.arm, folder), NODE, r.label, folder / f"{r.label}.STOP",
            int(round(minutes * 60)), hashes[r.arm], folder / f"runner-config-{r.arm}.json")}
            for r in runs],
    }  # fmt: skip


# --- the input log, the packets ----------------------------------------------------------------
@dataclass(frozen=True)
class KeyDown:
    sent_ns: int  # the runner's own send time (the event's t_mono_ns)
    accept_ns: int  # the backend's
    code: str


def key_downs(lines: Iterable[str], t0_ns: int, t1_ns: int,
              codes: Sequence[str] = ("F4", "F5", "F8")) -> list[KeyDown]:  # fmt: skip
    """PURE: the bot's accepted key downs of ``codes`` sent in [t0, t1], in time order."""
    out: list[KeyDown] = []
    for line in lines:
        if '"type":"key"' not in line or '"action":"down"' not in line:
            continue
        d = json.loads(line)
        e = d.get("event") or {}
        if d.get("source") != "bot" or not d.get("accepted") or e.get("code") not in codes:
            continue
        sent = int(e.get("t_mono_ns") or d["t_mono_ns"])
        if t0_ns <= sent <= t1_ns:
            out.append(KeyDown(sent, int(d["t_mono_ns"]), str(e["code"])))
    return sorted(out, key=lambda k: k.sent_ns)


def log_files(t0_wall: float, t1_wall: float, folder: Path = INPUT_LOG) -> list[Path]:
    """The input log's day files (UTC dates) a run's wall-clock window touches."""
    days = {time.strftime("%Y-%m-%d", time.gmtime(t)) for t in (t0_wall, t1_wall)}
    return [p for p in (folder / f"{d}.jsonl" for d in sorted(days)) if p.is_file()]


def read_packets(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    with gzip.open(path, "rt") as f:
        return [json.loads(x) for x in f if x.strip()]


def deaths_of(packets: Sequence[Mapping[str, Any]], gid: int = SELF_GID) -> list[int]:
    """PURE: her deaths (her own entity_vanish, reason 1), monotonic ns."""
    return [int(p["t_mono_ns"]) for p in packets if p.get("type") == "entity_vanish"
            and p.get("gid") == gid and p.get("reason") == 1]  # fmt: skip


# --- the fly-first Fly Wings --------------------------------------------------------------------
@dataclass
class Fly:
    t_key_ns: int
    t_read_ns: int | None
    why: str
    src: str
    request_s: float | None = None  # its use_item_request after its send time (None: none)
    keys_before: list[str] = field(default_factory=list)  # F4 / F5 keys between read and F8
    after_death: bool = False
    sight: dict[str, Any] | None = None

    def ok(self, bound_s: float = FLY_BOUND_S) -> bool | None:
        """True / False by BAR's fly-first line; None: pressed after her death (not judged)."""
        if self.after_death:
            return None
        return not self.keys_before and self.request_s is not None and self.request_s <= bound_s


def flies_of(events: Sequence[Mapping[str, Any]], packets: Sequence[Mapping[str, Any]],
             downs: Sequence[KeyDown]) -> list[Fly]:  # fmt: skip
    """PURE: every fly-first Fly Wing of one runner session, with its packets and keys."""
    reqs = sorted(int(p["t_mono_ns"]) for p in packets if p.get("type") == "use_item_request")
    deaths = deaths_of(packets)
    out: list[Fly] = []
    for e in events:
        if e.get("kind") != FLY_KIND or e.get("what") != "fly" or e.get("t_key_ns") is None:
            continue
        tk = int(e["t_key_ns"])
        tr = None if e.get("t_read_ns") is None else int(e["t_read_ns"])
        nxt = next((r for r in reqs if r >= tk - 50_000_000), None)
        req = None if nxt is None or nxt - tk > 2_000_000_000 else round((nxt - tk) / 1e9, 3)
        lo = tr if tr is not None else tk
        before = [k.code for k in downs if k.code in WEAPON_KEYS and lo <= k.sent_ns < tk]
        dead = any(d <= tk for d in deaths)
        out.append(Fly(tk, tr, str(e.get("why")), str(e.get("src")), req, before, dead,
                       e.get("sight")))  # fmt: skip
    return out


# --- the per-run score ---------------------------------------------------------------------------
@dataclass
class Score7(s5b2.Score5b2):
    flies_ff: list[Fly] = field(default_factory=list)  # B's fly-first Fly Wings
    fly_presses: dict[str, int] = field(default_factory=dict)  # every Fly Wing press by its why
    garm_seen: int = 0
    dagger_first: int = 0  # Fly Wing presses with the dagger key (F5) in the 0.3 s before
    sessions: list[str] = field(default_factory=list)
    econ: dict[str, float] | None = None  # gross_h, cost_h, net_h WITH steals (econ_db.totals_of)

    def doc(self) -> dict[str, Any]:
        return {**super().doc(), "flies_ff": [asdict(f) for f in self.flies_ff],
                "fly_presses": self.fly_presses, "garm_seen": self.garm_seen,
                "dagger_first": self.dagger_first, "sessions": self.sessions,
                "econ": self.econ}  # fmt: skip


def score_session(sc: Score7, events: Sequence[Mapping[str, Any]],
                  packets: Sequence[Mapping[str, Any]],
                  downs: Sequence[KeyDown]) -> None:  # fmt: skip
    """PURE: one runner session's flies, presses and sightings."""
    sc.flies_ff.extend(flies_of(events, packets, downs))
    for e in events:
        if e.get("kind") == "press" and e.get("what") == "fly":
            w = str(e.get("why"))
            k = ("boss" if w in ("garm", "boss") else "box_boss" if "sees_boss True" in w
                 else "box" if w.startswith("box ") else "hp_or_other")  # fmt: skip
            sc.fly_presses[k] = sc.fly_presses.get(k, 0) + 1
        elif e.get("kind") == "garm_seen":
            sc.garm_seen += 1
    f8 = [k.sent_ns for k in downs if k.code == "F8"]
    f5 = [k.sent_ns for k in downs if k.code == "F5"]
    sc.dagger_first += sum(1 for t in f8 if any(0 < t - x <= 300_000_000 for x in f5))


ECON_KEYS = ("gross_h", "cost_h", "net_h")


def econ_pick(t: Mapping[str, Any] | None) -> dict[str, float] | None:
    """PURE: the zeny an hour of a dashboard totals dict (econ_dash.totals), or None."""
    if not t:
        return None
    return {k: float(t[k]) for k in ECON_KEYS if isinstance(t.get(k), int | float)}


def econ_of(session: str, data: Path = ECON_DATA) -> dict[str, float] | None:
    """One run's economy WITH Steal and Snatcher income (live-blocks 18.10 #4): the dashboard's
    totals (econ_db.totals_of), read-only; None: not in the file."""
    import econ_db as edb

    try:
        got = edb.totals_of([session], data=data)
    except (OSError, sqlite3.Error, ValueError):
        return None
    return econ_pick(got["runs"].get(Path(session).name))


def econ_arms(scores: Sequence[Score7], minutes: float, data: Path = ECON_DATA,
              bar: Mapping[str, Any] = BAR) -> dict[str, dict[str, Any] | None]:  # fmt: skip
    """Each arm's economy WITH steals, its valid runs POOLED (econ_db.totals_of: the dashboard's
    per-arm figure, the counts summed over the hours summed)."""
    import econ_db as edb

    ok_min = minutes * float(bar["min_minutes_share"])
    out: dict[str, dict[str, Any] | None] = {}
    for x in ("A", "B"):
        sids = [d for s in scores if s.arm == x and s.found
                and (s.minutes >= ok_min or str(s.end or "").startswith("weight_home"))
                for d in s.sessions]  # fmt: skip
        try:
            got = edb.totals_of(sids, data=data)
        except (OSError, sqlite3.Error, ValueError):
            out[x] = None
            continue
        pooled = econ_pick(got["pooled"])
        out[x] = None if pooled is None else {**pooled, "runs": len(got["runs"]),
                                               "missing": got["missing"]}  # fmt: skip
    return out


def score_run(r: Mapping[str, Any], folder: Path, demo: Path = s2.DEMO,
              logs: Path = INPUT_LOG, data: Path = ECON_DATA) -> Score7:  # fmt: skip
    """Reads (no screen): one run's sessions by its label, its log, the input log, the economy."""
    base = s5b2.score_run(r, folder, demo)
    sc = Score7(**{k: getattr(base, k) for k in base.__dataclass_fields__})
    for d in sorted(demo.glob(f"*-{r['label']}-hunt*")):
        if not (d / "events.jsonl").is_file():
            continue
        ev = s2.read_events(d / "events.jsonl")
        if not ev:
            continue
        t0, t1 = int(ev[0]["t_ns"]), int(ev[-1]["t_ns"])
        walls = [float(x["t_wall"]) for x in ev if isinstance(x.get("t_wall"), int | float)]
        now = time.time()
        w0, w1 = (min(walls), max(walls)) if walls else (now - 86_400, now)
        downs: list[KeyDown] = []
        for p in log_files(w0, w1, logs):
            with p.open(errors="replace") as f:
                downs.extend(key_downs(f, t0 - 5_000_000_000, t1 + 5_000_000_000))
        score_session(sc, ev, read_packets(d / "packets.jsonl.gz"), downs)
        sc.sessions.append(d.name)
        sc.econ = econ_of(d.name, data) or sc.econ
    return sc


# --- the verdict -------------------------------------------------------------------------------
def fly_line(scores: Sequence[Score7], bound_s: float = FLY_BOUND_S) -> dict[str, Any]:
    """PURE: BAR's fly-first line, over B's played runs."""
    played = [s for s in scores if s.arm == "B" and s.found
              and (s.minutes >= s5c.PLAYED_MIN or s.deaths)]  # fmt: skip
    flies = [(s.label, f) for s in played for f in s.flies_ff]
    judged = [(lab, f) for lab, f in flies if f.ok(bound_s) is not None]
    bad = [f"{lab}: {f.why} ({f.src}): " + ("a weapon key before it " + str(f.keys_before)
           if f.keys_before else "no use_item_request" if f.request_s is None
           else f"its request {f.request_s} s after its send") for lab, f in judged
           if not f.ok(bound_s)]  # fmt: skip
    reqs = sorted(f.request_s for _lab, f in judged if f.request_s is not None)
    return {"flies": len(flies), "judged": len(judged),
            "after_death": sum(1 for _lab, f in flies if f.after_death),
            "request_s": {"median": round(statistics.median(reqs), 3) if reqs else None,
                          "max": reqs[-1] if reqs else None},
            "problems": bad, "pass": None if not judged else not bad}  # fmt: skip


def report_of(scores: Sequence[Score7], minutes: float, bar: Mapping[str, Any] = BAR,
              econ: Mapping[str, Mapping[str, Any] | None] | None = None,
              ) -> dict[str, Any]:  # fmt: skip
    """PURE: the reported lines: deaths per played run, flies by source, the economy (``econ``:
    each arm's pooled totals WITH steals, econ_arms)."""
    ok_min = minutes * float(bar["min_minutes_share"])
    out: dict[str, Any] = {}
    for x in ("A", "B"):
        arm = [s for s in scores if s.arm == x and s.found]
        played = [s for s in arm if s.minutes >= s5c.PLAYED_MIN or s.deaths]
        valid = [
            s for s in arm if s.minutes >= ok_min or str(s.end or "").startswith("weight_home")
        ]
        hours = sum(s.minutes for s in valid) / 60.0
        presses: dict[str, int] = {}
        for s in valid:
            for k, n in s.fly_presses.items():
                presses[k] = presses.get(k, 0) + n
        out[x] = {
            "deaths": sum(s.deaths for s in played), "played": len(played),
            "deaths_per_run": (round(sum(s.deaths for s in played) / len(played), 2)
                               if played else None),
            "garm_seen_h": round(sum(s.garm_seen for s in valid) / hours, 1) if hours else None,
            "fly_presses_h": ({k: round(n / hours, 1) for k, n in sorted(presses.items())}
                              if hours else {}),
            "dagger_first": sum(s.dagger_first for s in valid),
            "inside": sum(1 for s in valid for f in s.flies_ff if f.src == "alarm" and f.sight
                          and f.t_read_ns is not None) if x == "B" else None,
            "econ_with_steals": (econ or {}).get(x),  # gross_h, cost_h, net_h: the dashboard's
        }  # fmt: skip
    return out


def verdict(scores: Sequence[Score7], minutes: float, a_kinds: set[str],
            bar: Mapping[str, Any] = BAR,
            econ: Mapping[str, Mapping[str, Any] | None] | None = None,
            ) -> dict[str, Any]:  # fmt: skip
    """PURE: the pre-registered bar (18.7). `a_kinds`: the 5b-1 runner text's kinds (the drive's
    and fly-first's own kinds are allowed besides). Deaths are reported, never judged."""
    v = s5b.verdict(scores, minutes, set(a_kinds) | {s5c.DRIVE_KIND, FLY_KIND}, bar)
    lines = dict(v.get("lines") or {})
    deaths = lines.pop("deaths", None)
    rep = dict(lines.get("report") or {})
    rep["deaths"] = deaths
    rep["arms"] = report_of(scores, minutes, bar, econ)
    lines["report"] = rep
    lines["drive"] = s5c.drive_line(scores)
    lines["fly_first"] = fly_line(scores, float(bar["fly_bound_s"]))
    out = {**v, "lines": lines}
    if out.get("why") == "an arm has no valid run":
        out["verdict"] = "INCONCLUSIVE"
        return out
    judged = [x["pass"] for k, x in lines.items() if k != "report"]
    out["verdict"] = "FAIL" if False in judged else ("INCONCLUSIVE" if None in judged else "PASS")
    return out


def table(scores: Sequence[Score7]) -> str:
    """PURE: the per-run table: stage5b2_ab's, then the flies and the economy."""
    rows = s5b2.table(scores).splitlines()
    out = [f"{rows[0]}  ff  ok  dagger  z/h"]
    for s, row in zip(scores, rows[1:], strict=True):
        ok = sum(1 for f in s.flies_ff if f.ok())
        z = "-" if not s.econ or "net_h" not in s.econ else f"{s.econ['net_h']:.0f}"
        out.append(f"{row}  {len(s.flies_ff):2d}  {ok:2d}  {s.dagger_first:6d}  {z}")
    return "\n".join(out)


# --- 18.2's measure: the key -> request delays (read-only) --------------------------------------
def request_delays(sessions: Sequence[Path], logs: Sequence[Path]) -> dict[str, dict[str, Any]]:
    """Each key down of the bot (the input log) -> the client's request for it (the session's
    packets: use_item_request for F1 / F6-F9, equip_request for F4 / F5) within 2 s: the delays
    from the backend's accept and from the runner's send, per key (ms)."""
    want = {"F1": "use_item_request", "F6": "use_item_request", "F7": "use_item_request",
            "F8": "use_item_request", "F9": "use_item_request", "F4": "equip_request",
            "F5": "equip_request"}  # fmt: skip
    downs: list[KeyDown] = []
    for p in logs:
        with p.open(errors="replace") as f:
            downs.extend(key_downs(f, 0, 2**63, tuple(want)))
    got: dict[str, list[tuple[float, float]]] = {}
    for d in sessions:
        pk = read_packets(d / "packets.jsonl.gz")
        if not pk:
            continue
        lo, hi = int(pk[0]["t_mono_ns"]), int(pk[-1]["t_mono_ns"])
        for k in downs:
            if not lo <= k.accept_ns <= hi:
                continue
            nxt = next((int(p["t_mono_ns"]) for p in pk if p.get("type") == want[k.code]
                        and k.accept_ns - 50_000_000 <= int(p["t_mono_ns"]) <= k.accept_ns
                        + 2_000_000_000), None)  # fmt: skip
            if nxt is not None:
                got.setdefault(k.code, []).append(((nxt - k.accept_ns) / 1e6,
                                                   (nxt - k.sent_ns) / 1e6))  # fmt: skip

    def stats(v: Sequence[float]) -> dict[str, float]:
        s = sorted(v)
        return {"median": round(statistics.median(s), 1),
                "p95": round(s[int(0.95 * (len(s) - 1))], 1), "max": round(s[-1], 1)}  # fmt: skip

    return {k: {"n": len(v), "from_accept_ms": stats([a for a, _ in v]),
                "from_send_ms": stats([b for _, b in v])}
            for k, v in sorted(got.items())}  # fmt: skip


def econ_update(runs: Sequence[Mapping[str, Any]], demo: Path = s2.DEMO) -> str:
    """The runs' sessions into data/econ/lab.sqlite (econ_db.py update: only the ones not there
    yet; Batt 2026-11-16, 17 #7). Its outcome in words."""
    import subprocess

    dirs = [str(d) for r in runs for d in sorted(demo.glob(f"*-{r['label']}-hunt*"))
            if (d / "events.jsonl").is_file()]  # fmt: skip
    if not dirs:
        return "econ_db: no session to add"
    got = subprocess.run([sys.executable, str(ROOT / "scripts" / "econ_db.py"), "update", *dirs],
                         cwd=ROOT, capture_output=True, text=True, timeout=900,
                         check=False)  # fmt: skip
    tail = (got.stdout.strip().splitlines() or got.stderr.strip().splitlines() or [""])[-1]
    return f"econ_db update ({len(dirs)} sessions): rc {got.returncode}; {tail[:200]}"


class Series7(s2.Series):
    """stage2_ab's live series (the setup, the detect server, one run at a time), for A / B."""

    score_cmd = "stage7_ab.py"


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("plan", "run", "score"):
        p = sub.add_parser(name)
        p.add_argument("--label", required=True, help="the series' name (its runs' labels)")
        if name != "score":
            p.add_argument("--pairs", type=int, default=4)
            p.add_argument("--minutes", type=int, default=20,
                           help="each run's length (the Run config's minutes: 5..600)")  # fmt: skip
            p.add_argument("--order", choices=("alternate", "ab"), default="alternate")
        else:
            p.add_argument("--json", action="store_true")
            p.add_argument("--no-econ-update", action="store_true",
                           help="do not add the runs' sessions to "
                           "data/econ/lab.sqlite first")  # fmt: skip
    dv = sub.add_parser("derive", help="18.2's key -> request delays over banked sessions")
    dv.add_argument("sessions", nargs="+", type=Path)
    dv.add_argument("--input-log", action="append", type=Path, default=[])
    a = ap.parse_args(argv)
    if a.cmd == "derive":
        logs = a.input_log or sorted(INPUT_LOG.glob("*.jsonl"))[-2:]
        print(json.dumps(request_delays(a.sessions, logs), indent=1))
        return 0
    folder = SCRATCH / a.label
    if a.cmd == "score":
        doc = json.loads((folder / "series.json").read_text())
        if not a.no_econ_update:  # Batt 2026-11-16 (17 #7): every run's economy in lab.sqlite
            print(econ_update(doc["runs"]), flush=True)
        scores = [score_run(r, folder) for r in doc["runs"]]
        base = (folder / "runner-5b1.py").read_text()
        v = verdict(scores, float(doc["minutes"]), s5b.base_kinds(base),
                    econ=econ_arms(scores, float(doc["minutes"])))  # fmt: skip
        if a.json:
            print(json.dumps({"runs": [s.doc() for s in scores], "verdict": v}, indent=1))
        else:
            print(table(scores))
            print(json.dumps(v, indent=1, default=str))
        return 0
    if not 5 <= a.minutes <= 600:
        print("refused before any input: --minutes is the Run config's: 5..600", flush=True)
        return 2
    got = plan_doc(a.label, a.pairs, a.minutes, a.order, folder)
    if isinstance(got, str):
        print(got, flush=True)
        return 2
    if a.cmd == "plan":
        print(json.dumps(got, indent=1))
        return 0
    folder.mkdir(parents=True, exist_ok=False)  # a series' folder is never reused
    (folder / "series.json").write_text(json.dumps(got, indent=1) + "\n")
    (folder / "runner-5b1.py").write_text(hc.git_show(hc.DRIVE_BASE, hc.TARGET))  # base kinds
    for arm in ("A", "B"):
        s4.project_file(arm, folder).write_text(arm_text(arm, a.minutes))
        (folder / f"runner-config-{arm}.json").write_text(json.dumps({NODE: got["vals"][arm]})
                                                         + "\n")  # fmt: skip
    return Series7(got, folder).run()


if __name__ == "__main__":
    raise SystemExit(main())
