#!/usr/bin/env python3
"""Stage 9's live A/B, s9ab (docs/planning/live-blocks.md 18.15; Batt 2026-11-17, 18.14: "use it for
real"): the ready-made functions box naming the old model (A, use_model("xmas02") = xmas02-gb: the
alarm flies on the Garm Baby) against the same box naming the deployed one (B,
use_model("xmas02sk"): the alarm flies on the Garm Baby, the Christmas Goblin and the Stormy
Knight), alternating runs on the lab's own Rogue on the lab rAthena's xmas_dun02 (player mode; the
MVP alive). Both arms hold fly_first and fly_first_hp ON (the ready-made box's, 18.10 #1 / 18.13),
set explicitly.

THE ARMS differ ONLY in the box's model: each arm plays a copy of
services/frontend/src/lib/flow/fixtures/project_xmas_dun02_functions.json whose main's use_model
names MODELS[arm], through `flow_play.py play` with that copy's own runner settings. `plan` refuses
before any input unless: the copies differ in that one block's model alone; their runner settings,
runner argv, keys, loop and tick not at all; their run() box arguments only in box_model, whose
entries differ only in the model's own facts (id, file, sha256) and the alarm that follows from it
(models.yaml `alarm`: B's three classes, A's none = garm_baby alone); each is a model the runner's
box detector loads on the map (dungeon_hunt.box_model_refused: B the map's own, A its reference,
dungeon@9.59) and the detect server serves (GPU_WEIGHTS); the checkout's runner is 9.59 and
huntstate_check's `drive`, `check`, `flag` and `pick` hold (`pick`: with the model-pick branches as
their else the WHOLE module is PICK_BASE's, the 9.58 runner s8ab measured -- so with no reference
named the runner plays s8ab's program); and the box's step traces equal the driver's.

THE SCORE per run: stage7_ab's (kills, loot steps, openers, the pace, kinds, errors, the drive, the
fly-first Fly Wings, the economy WITH steals) and, from each runner session's packets:
  * THE BOSS FLY WINGS (every fly_first record of a boss Fly Wing: src alarm / line / box; the HP
    ones left out) and their TRUTH at the moment the runner acted on (the alarm's: the sighting's
    grab time; else its read): a FALSE Fly Wing has no alarm-species unit (eval_q1.ALARM_SPECIES:
    the Goblin, the knight, Garm Baby) ON SCREEN by the packets (the Timeline world FRAME_LAG_S
    earlier -- the frames trail the packets -- each unit's cell projected by the runner's own camera
    relative to her cell, its sprite ENVELOPE meeting the 1280 x 720 game region) and lies outside
    every post-vanish window (xmas02-detector.md S7.1's rule, eval_q1.in_post_vanish: POST_VANISH_S
    after a vanish, reason 0 or 1, of an alarm-species unit of the session);
  * THE PARTY'S VISITS (reported): runs of SAMPLE_S samples with a party unit (Goblin or knight) on
    screen, a gap > VISIT_GAP_S ending one (S6's rule); per visit the first boss Fly Wing in it (to
    its end + POST_VANISH_S) and the time from the visit's first sample to that Fly Wing's key;
  * the detect server's call ms (detections.jsonl, the GPU path) and the run's box_model records.

    stage9_ab.py plan    --label s9ab --pairs 4 --minutes 20
    stage9_ab.py run     --label s9ab --pairs 4 --minutes 20
    stage9_ab.py score   --label s9ab [--json]
    stage9_ab.py derive  SESSION_DIR [SESSION_DIR ...]   the false-Fly-Wing ruler on banked runs
"""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import math
import statistics
import sys
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import eval_q1 as eq  # noqa: E402
import flow_run as fr  # noqa: E402
import hunt_trace as ht  # noqa: E402
import huntstate_check as hc  # noqa: E402
import stage2_ab as s2  # noqa: E402
import stage4_ab as s4  # noqa: E402
import stage5b_ab as s5b  # noqa: E402
import stage5c_ab as s5c  # noqa: E402
import stage7_ab as s7  # noqa: E402
import stage8_ab as s8  # noqa: E402

VERSION = "9.59"  # dungeon_hunt.MODEL_PICK_VERSION: the runner it measures
NODE = s2.NODE
PROJECT = s7.PROJECT  # the ready-made functions box (use_model xmas02sk since 18.15)
MODELS = {"A": "xmas02", "B": "xmas02sk"}
ARMS = {"A": "use_model xmas02 (xmas02-gb, the map's reference): the alarm on the Garm Baby",
        "B": "use_model xmas02sk (the deployed model): the alarm on the Garm Baby, the Christmas "
             "Goblin and the Stormy Knight"}  # fmt: skip
WEIGHTS = {"A": "xmas02gb", "B": "xmas02sk"}  # unit_detector GPU_WEIGHTS: the detect server's
SCRATCH = Path("/dev/shm/poring-lab-tmp/stage9-ab")
SEEDS = s7.SEEDS
# the model's own facts in the box's run() argument (recipes.BlockPlan.model_doc), and the alarm's
MODEL_KEYS = ("id", "file", "sha256", "alarm", "classes")
ALARM_SPECIES = eq.ALARM_SPECIES  # the Goblin 1607, the knight 1251, Garm Baby 1515
PARTY = eq.PARTY  # the knight's party: the Goblin and the knight (S6's visits)
POST_VANISH_S = eq.POST_VANISH_S  # 5.0 (S7.1)
VISIT_GAP_S = eq.VISIT_GAP_S  # 5.0 (S6)
FRAME_LAG_S = 0.12  # S7.1: the frames trail the packets (the labeller's 120-ms offset)
SAMPLE_S = 0.25  # the visits' sampling step (the runner's QUICK_S read)
SCREEN = (1280, 720)  # the game region (GAME_REGION's w, h)
# the knight's sprite envelope around its foot (docs/planning/xmas02-prep.md: -81.5 -122.5 59.5
# 10.5, 141 x 133 px), the largest of the three: a unit is on screen when it meets the game region
ENVELOPE = (-81.5, -122.5, 59.5, 10.5)
HP_SRCS = s8.HP_SRCS
# THE MARGIN of the false-Fly-Wing line (live-blocks.md 18.15, derived BEFORE any s9ab run from the
# 12 banked fly-first runs on xmas02-gb -- s7ab's B and s8ab's A and B; `derive` re-computes it):
# 2 x the standard error of the difference of two arms' pooled rates over PAIRS runs each under no
# difference, from the per-run rates' standard deviation s, floored at the Poisson one of their
# pooled rate (at least one Fly Wing over the banked hours): max(2 sqrt(2 / PAIRS) s,
# 2 sqrt(2 lam / H)), H = PAIRS x 20 min, rounded up to 0.1 / h
# 2026-11-17 07:00 ICT (`derive` over s7ab r02B r03B r06B r07B + s8ab r01A-r08A, 3.83 h): per-run
# false rates s = 4.32 / h, pooled 4.01 / h -> 2 sqrt(2 / 4) x 4.32 = 6.11, Poisson 4.91 -> 6.2 / h
PAIRS = 4
MARGIN_H = 6.2
# THE PRE-REGISTERED BAR (live-blocks.md 18.15, written before any s9ab run)
BAR = {
    **{k: v for k, v in s7.BAR.items() if k not in ("fly_first", "fly_bound_s")},
    "deaths": "JUDGED: B's deaths <= A's over EVERY run that played (>= 1 min, or a death); <=, "
              "not <: two zero arms pass (no line asks B to beat an arm that read 0)",
    "false_flies_h": "B's FALSE boss Fly Wings an hour <= A's + false_fly_margin_h (each arm's "
                     "valid runs pooled; a false one: no alarm-species unit on screen by the "
                     "packets at the moment the runner acted on, outside S7.1's post-vanish "
                     "windows); judged when both arms have a valid run",
    "false_fly_margin_h": MARGIN_H,
    "model": "every run that played loaded its arm's model in its box watcher (its box_model "
             "records: the ONNX and the detect server's weights of MODELS / WEIGHTS)",
    "reported": "the alarm's true Fly Wings per party visit, the time from a visit's first sample "
                "to its Fly Wing, the boss Fly Wings by source and the sightings by class, the "
                "economy with steals, the detect server's call ms, deaths per arm",
}  # fmt: skip


def _quiet(f: Any, *a: Any, **k: Any) -> tuple[int, str]:
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        rc = f(*a, **k)
    return int(rc), out.getvalue()


# --- the arms ------------------------------------------------------------------------------------
def arm_doc(arm: str, minutes: float, path: Path = PROJECT) -> dict[str, Any]:
    """PURE but for the read: the box with its time box set, fly_first and fly_first_hp ON and its
    use_model MODELS[arm] -- each explicitly, whatever the fixture holds."""
    d = json.loads(path.read_text())
    d["max_runtime_s"] = int(round(minutes * 60))
    tab = next((t for t in d["nodes"][0]["tabs"] if t["name"] == s7.FLY_TAB), None)
    if tab is None:
        raise ValueError(f"the box has no tab {s7.FLY_TAB}")
    for var in (s7.FLY_VAR, s8.VAR):
        tab["vars"][var] = {"kind": "lit", "value": True}
    s5c.set_box_model(d, MODELS[arm])
    return d


def arm_text(arm: str, minutes: float, path: Path = PROJECT) -> str:
    from poring_flow import project as pj

    return pj.to_json(pj.validate(arm_doc(arm, minutes, path)))


def box_difference(a: Mapping[str, Any], b: Mapping[str, Any]) -> str | None:
    """PURE: B is A with its use_model naming B's model, and nothing else -- or why not."""
    a, b = json.loads(json.dumps(a)), json.loads(json.dumps(b))
    for arm, d in (("A", a), ("B", b)):
        if s5c.box_model_of(d) != MODELS[arm]:
            return f"{arm}'s use_model does not name {MODELS[arm]}"
        tab = next((t for t in d["nodes"][0]["tabs"] if t["name"] == s7.FLY_TAB), None)
        for var in (s7.FLY_VAR, s8.VAR):
            lit = None if tab is None else tab["vars"].get(var)
            if not isinstance(lit, Mapping) or lit.get("value") is not True:
                return f"{arm}'s {s7.FLY_TAB} tab does not hold {var} = True (both arms)"
        s5c.set_box_model(d, "-")
    if a != b:
        return "B differs from A in more than its use_model (an A/B changes one thing)"
    return None


def runner_problem(runner_text: str) -> str | None:
    """PURE: the checkout's runner is 9.59: a box's use_model picks the map's model."""
    if f'MODEL_PICK_VERSION = "{VERSION}"' not in runner_text:
        return f"the checkout's runner is not dungeon@{VERSION} (no MODEL_PICK_VERSION)"
    return None


def model_problems(box: Mapping[str, Mapping[str, Any]]) -> str | None:
    """PURE but for unit_detector's pins: the arms' box_model entries differ only in the model's
    own facts and its alarm, each is a model the runner's box detector loads on the map and the
    detect server serves, and the alarm classes follow from it (dungeon_hunt.alarm_classes)."""
    import dungeon_hunt as dh
    import unit_detector as ud

    docs = {x: dict(box[x].get("box_model") or {}) for x in ("A", "B")}
    for x, d in docs.items():
        if d.get("id") != MODELS[x]:
            return f"{x}'s box_model is {d.get('id')!r}, not {MODELS[x]}"
        why = dh.box_model_refused(d, "xmas_dun02")
        if why:
            return f"{x}: {why}"
        if WEIGHTS[x] not in ud.GPU_WEIGHTS or ud.GPU_WEIGHTS[WEIGHTS[x]].onnx != d.get("file"):
            return f"{x}: the detect server serves no weights {WEIGHTS[x]} of {d.get('file')}"
    other = {x: {k: v for k, v in d.items() if k not in MODEL_KEYS} for x, d in docs.items()}
    if other["A"] != other["B"]:
        return f"the box_model entries differ beyond {list(MODEL_KEYS)}: {other}"
    rest = {x: {k: v for k, v in box[x].items() if k != "box_model"} for x in ("A", "B")}
    if rest["A"] != rest["B"]:
        return "the arms give the runner different box arguments besides box_model"
    want = {"A": ("garm_baby",), "B": ("garm_baby", "g_gobline_xmas", "knight_of_windstorm")}
    for x, d in docs.items():
        if dh.alarm_classes(d) != want[x]:
            return f"{x}'s alarm classes are {dh.alarm_classes(d)}, not {want[x]}"
    return None


def plan_doc(label: str, pairs: int, minutes: float, order: str, folder: Path,
             runner_text: str | None = None, bases: Mapping[str, str] | None = None,
             seeds: int = SEEDS, bar: Mapping[str, Any] = BAR) -> dict[str, Any] | str:  # fmt: skip
    """PURE but for reads (the fixture, git, the checkout's runner): everything a series will do,
    before any screen is read or any input path opened; a refusal: its words. ``bases``: the
    proofs' base texts by name (drive, check, flag, pick), else git's."""
    import flow_play as fp

    from poring_flow import project as pj

    if bar.get("false_fly_margin_h") is None:
        return "refused before any input: the false-Fly-Wing margin is not set (18.15's derive)"
    texts = {arm: arm_text(arm, minutes) for arm in ("A", "B")}
    why = box_difference(json.loads(texts["A"]), json.loads(texts["B"]))
    if why is not None:
        return f"refused before any input: {why}"
    vals: dict[str, dict[str, Any]] = {}
    for arm, text in texts.items():
        v = s5c.vals_of(text)
        if isinstance(v, str):
            return f"refused before any input: {arm}: {v}"
        vals[arm] = v
    if vals["A"] != vals["B"]:
        diff = sorted(k for k in set(vals["A"]) | set(vals["B"])
                      if vals["A"].get(k) != vals["B"].get(k))  # fmt: skip
        return f"refused before any input: the arms' runner settings differ in {diff}"
    need = ("garm_fly", "alarm_fast", "fly_first", "fly_first_hp")
    if not all(vals["A"].get(k) for k in need):
        return f"refused before any input: {' / '.join(need)} not all on in the Run config"
    runner_text = hc.TARGET.read_text() if runner_text is None else runner_text
    bad = runner_problem(runner_text)
    if bad:
        return f"refused before any input: {bad}"
    revs = {"drive": hc.DRIVE_BASE, "check": hc.BASE_REV, "flag": hc.FLAG_BASE,
            "pick": hc.PICK_BASE}  # fmt: skip
    got_b = {k: (bases or {}).get(k) or hc.git_show(rev, hc.TARGET) for k, rev in revs.items()}
    proofs = (("drive", _quiet(hc.drive_check, got_b["drive"], runner_text)),
              ("check", _quiet(hc.check, got_b["check"], runner_text, drive_ok=True)),
              ("flag", _quiet(hc.flag_check, got_b["flag"], runner_text)),
              ("pick", _quiet(hc.pick_check, got_b["pick"], runner_text)))  # fmt: skip
    for name, (rc, out) in proofs:
        if rc != 0:
            lines = [ln for ln in out.splitlines() if "NO" in ln or "DIFFERS" in ln
                     or "CHANGED" in ln]  # fmt: skip
            return (f"refused before any input: huntstate_check {name} fails: "
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
                     "model": MODELS[arm], "weights": WEIGHTS[arm], "project_hash": h,
                     "loop": rp.loop, "left_out": list(rp.tick_left_out), "box": rp.box_kwargs(),
                     "keys": rp.keys}  # fmt: skip
    if argv["A"] != argv["B"]:
        return "refused before any input: the arms' runner argv differ (the model is the box's)"
    if "--fly-first" not in argv["A"] or "--fly-first-hp" not in argv["A"]:
        return "refused before any input: the runner argv lacks --fly-first / --fly-first-hp"
    for k in ("keys", "loop", "left_out"):
        if arms["A"][k] != arms["B"][k]:
            return f"refused before any input: the arms give the runner different {k}"
    bad = model_problems({x: arms[x]["box"] for x in ("A", "B")})
    if bad:
        return f"refused before any input: {bad}"
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
        "arms": arms, "vals": vals, "bar": dict(bar), "drive_base": hc.DRIVE_BASE,
        "check_base": hc.BASE_REV, "flag_base": hc.FLAG_BASE, "pick_base": hc.PICK_BASE,
        "runner_sha256": s5b.sha(runner_text), "trace_scenarios": len(scns),
        "serve_s": int(len(runs) * (minutes * 60 + s2.START_GRACE_S + 120) + s2.SERVE_EXTRA_S),
        "runs": [{**asdict(r), "argv": fr.play_command(
            s4.project_file(r.arm, folder), NODE, r.label, folder / f"{r.label}.STOP",
            int(round(minutes * 60)), hashes[r.arm], folder / f"runner-config-{r.arm}.json")}
            for r in runs],
    }  # fmt: skip


# --- the truth: the packets' world on screen ------------------------------------------------------
def camera_project() -> Callable[[Any], Any]:
    """The runner's own camera (camera_rdp.json, flat ground): cell offsets (N, 2) -> pixels."""
    from poring_dataset import camera as cam

    cj = json.loads((ROOT / "packages/poring_dataset/src/poring_dataset/camera_rdp.json")
                    .read_text())  # fmt: skip
    c = cam.camera_from_json(cj["camera"])
    return lambda offs: c.project(offs)


def on_screen(
    u: float, v: float, env: Sequence[float] = ENVELOPE, screen: tuple[int, int] = SCREEN
) -> bool:
    """PURE: a sprite whose foot projects to (u, v) meets the game region."""
    return (u + env[2] > 0 and u + env[0] < screen[0] and v + env[3] > 0
            and v + env[1] < screen[1])  # fmt: skip


class Truth:
    """One runner session's packets: the alarm-species units on screen at a time (the Timeline
    world FRAME_LAG_S earlier, her cell from the same world) and S7.1's post-vanish windows."""

    def __init__(self, packets: Sequence[Mapping[str, Any]],
                 project: Callable[[Any], Any] | None = None) -> None:  # fmt: skip
        from poring_dataset.timeline import Timeline

        self.tl = Timeline(packets)
        self.project = project or camera_project()
        self.vanishes = eq.session_vanishes(packets)

    def units_at(self, t_ns: int, species: Sequence[int] = ALARM_SPECIES) -> list[int] | None:
        """The jobs of the ``species`` units on screen at ``t_ns``; None: her cell unknown."""
        import numpy as np

        fw = self.tl.frame_world(int(t_ns - FRAME_LAG_S * 1e9))
        if fw.self_pos is None:
            return None
        us = [e for e in fw.entities if e.objtype == 5 and not e.hidden and e.job in species]
        if not us:
            return []
        sx, sy = fw.self_pos
        uv = self.project(np.array([[e.x - sx, e.y - sy] for e in us], dtype=float))
        return sorted(e.job for e, (u, v) in zip(us, uv, strict=True)
                      if on_screen(float(u), float(v)))  # fmt: skip

    def post_vanish(self, t_ns: int) -> bool:
        return eq.in_post_vanish(int(t_ns), self.vanishes, POST_VANISH_S)


@dataclass
class BossFly:
    t_key_ns: int
    t_ns: int  # the moment the runner acted on: the sighting's grab (alarm), else its read
    src: str
    why: str
    cls: str | None  # the alarm sighting's class
    units: list[int] | None  # the alarm-species jobs on screen then (None: her cell unknown)
    post_vanish: bool
    after_death: bool = False

    @property
    def false(self) -> bool | None:
        """True: no alarm-species unit on screen, outside every post-vanish window; None: not
        judged (pressed after her death, or her cell unknown)."""
        if self.after_death or self.units is None:
            return None
        return not self.units and not self.post_vanish


def boss_flies_of(events: Sequence[Mapping[str, Any]], truth: Truth,
                  deaths: Sequence[int] = ()) -> list[BossFly]:  # fmt: skip
    """PURE but for the truth's reads: every boss Fly Wing of one session (its fly_first records
    but the HP ones), each with what the packets showed when the runner acted."""
    out: list[BossFly] = []
    for e in events:
        if e.get("kind") != s7.FLY_KIND or e.get("what") != "fly" or e.get("t_key_ns") is None:
            continue
        sight = e.get("sight") or {}
        if str(e.get("src")) in HP_SRCS or sight.get("hp"):
            continue
        tk = int(e["t_key_ns"])
        t = (int(sight["t_ns"]) if e.get("src") == "alarm" and sight.get("t_ns") is not None
             else int(e.get("t_read_ns") or tk))  # fmt: skip
        out.append(BossFly(tk, t, str(e.get("src")), str(e.get("why")), sight.get("cls"),
                           truth.units_at(t), truth.post_vanish(t),
                           any(d <= tk for d in deaths)))  # fmt: skip
    return out


def visits_of(truth: Truth, t0_ns: int, t1_ns: int, flies: Sequence[BossFly],
              step_s: float = SAMPLE_S) -> list[dict[str, Any]]:  # fmt: skip
    """The party's visits in [t0, t1] (samples every ``step_s`` with a Goblin or the knight on
    screen; a gap > VISIT_GAP_S ends one), each with its first boss Fly Wing (its moment in the
    visit, to its end + POST_VANISH_S) and the time from the visit's first sample to its key."""
    visits: list[list[int]] = []
    t, last = t0_ns, None
    while t <= t1_ns:
        got = truth.units_at(t, PARTY)
        if got:
            if last is None or (t - last) / 1e9 > VISIT_GAP_S:
                visits.append([])
            visits[-1].append(t)
            last = t
        t += int(step_s * 1e9)
    out = []
    for v in visits:
        lo, hi = v[0], v[-1] + int(POST_VANISH_S * 1e9)
        fl = sorted((f for f in flies if lo <= f.t_ns <= hi), key=lambda f: f.t_key_ns)
        out.append({"t0_ns": lo, "s": round((v[-1] - v[0]) / 1e9, 2), "samples": len(v),
                    "fly_src": fl[0].src if fl else None, "fly_cls": fl[0].cls if fl else None,
                    "to_fly_s": round((fl[0].t_key_ns - lo) / 1e9, 2) if fl else None})  # fmt: skip
    return out


def detect_ms_of(path: Path) -> list[float]:
    """The detect server's call ms of a session's GPU-path detections (detections.jsonl)."""
    if not path.is_file():
        return []
    out = []
    with path.open() as f:
        for line in f:
            if '"path": "gpu"' not in line:
                continue
            ms = json.loads(line).get("ms")
            if isinstance(ms, int | float):
                out.append(float(ms))
    return out


# --- the per-run score ---------------------------------------------------------------------------
@dataclass
class Score9(s7.Score7):
    boss: list[BossFly] = field(default_factory=list)
    visits: list[dict[str, Any]] = field(default_factory=list)
    detect_ms: list[float] = field(default_factory=list)
    box_models: list[list[str | None]] = field(default_factory=list)  # [onnx, gpu weights]

    def doc(self) -> dict[str, Any]:
        return {**super().doc(),
                "boss": [{**asdict(f), "false": f.false} for f in self.boss],
                "visits": self.visits, "box_models": self.box_models,
                "detect_ms": ms_stats(self.detect_ms)}  # fmt: skip


def ms_stats(v: Sequence[float]) -> dict[str, float | int | None]:
    s = sorted(v)
    if not s:
        return {"n": 0, "median": None, "p95": None}
    return {"n": len(s), "median": round(statistics.median(s), 1),
            "p95": round(s[int(0.95 * (len(s) - 1))], 1)}  # fmt: skip


def score_session(sc: Score9, d: Path, events: Sequence[Mapping[str, Any]],
                  project: Callable[[Any], Any] | None = None) -> None:  # fmt: skip
    """Reads one runner session's packets and detections into ``sc`` (no screen)."""
    packets = s7.read_packets(d / "packets.jsonl.gz")
    for e in events:
        if e.get("kind") == "box_model":
            sc.box_models.append([e.get("onnx"), e.get("gpu_weights")])
    sc.detect_ms.extend(detect_ms_of(d / "detections.jsonl"))
    if not packets or not events:
        return
    truth = Truth(packets, project)
    flies = boss_flies_of(events, truth, s7.deaths_of(packets))
    sc.boss.extend(flies)
    sc.visits.extend(visits_of(truth, int(events[0]["t_ns"]), int(events[-1]["t_ns"]), flies))


def score_run(r: Mapping[str, Any], folder: Path, demo: Path = s2.DEMO,
              logs: Path = s7.INPUT_LOG, data: Path = s7.ECON_DATA) -> Score9:  # fmt: skip
    """Reads (no screen): stage7_ab's score of the run, then its sessions' truth."""
    base = s7.score_run(r, folder, demo, logs, data)
    sc = Score9(**{k: getattr(base, k) for k in base.__dataclass_fields__})
    project = camera_project()
    for d in sorted(demo.glob(f"*-{r['label']}-hunt*")):
        if (d / "events.jsonl").is_file():
            score_session(sc, d, s2.read_events(d / "events.jsonl"), project)
    return sc


# --- the verdict -------------------------------------------------------------------------------
def _valid(scores: Sequence[Score9], minutes: float, bar: Mapping[str, Any]) -> list[Score9]:
    ok_min = minutes * float(bar["min_minutes_share"])
    return [s for s in scores if s.found
            and (s.minutes >= ok_min or str(s.end or "").startswith("weight_home"))]  # fmt: skip


def false_line(scores: Sequence[Score9], minutes: float, bar: Mapping[str, Any] = BAR
               ) -> dict[str, Any]:  # fmt: skip
    """PURE: BAR's false-Fly-Wing line, each arm's valid runs pooled."""
    valid = _valid(scores, minutes, bar)
    out: dict[str, Any] = {}
    for x in ("A", "B"):
        arm = [s for s in valid if s.arm == x]
        hours = sum(s.minutes for s in arm) / 60.0
        judged = [f for s in arm for f in s.boss if f.false is not None]
        false = [f for f in judged if f.false]
        out[x] = {"runs": len(arm), "hours": round(hours, 3), "boss_flies": len(judged),
                  "false": len(false), "false_h": round(len(false) / hours, 2) if hours else None,
                  "unjudged": sum(1 for s in arm for f in s.boss if f.false is None),
                  "false_by_src": dict(sorted(_count(f.src for f in false).items()))}  # fmt: skip
    margin = float(bar["false_fly_margin_h"])
    a, b = out["A"]["false_h"], out["B"]["false_h"]
    out["margin_h"] = margin
    out["pass"] = None if a is None or b is None else b <= a + margin
    return out


def _count(xs: Any) -> dict[str, int]:
    out: dict[str, int] = {}
    for x in xs:
        out[str(x)] = out.get(str(x), 0) + 1
    return out


def model_line(scores: Sequence[Score9]) -> dict[str, Any]:
    """PURE: every run that played loaded its arm's model (its box_model records)."""
    import unit_detector as ud

    bad = []
    for s in scores:
        if not s.found or not (s.minutes >= s5c.PLAYED_MIN or s.deaths):
            continue
        want = [ud.GPU_WEIGHTS[WEIGHTS[s.arm]].onnx, WEIGHTS[s.arm]]
        if not s.box_models or any(m != want for m in s.box_models):
            bad.append(f"{s.label}: {s.box_models or 'no box_model record'}, not {want}")
    return {"problems": bad, "pass": not bad}


def alarm_report(scores: Sequence[Score9], minutes: float, bar: Mapping[str, Any] = BAR
                 ) -> dict[str, Any]:  # fmt: skip
    """PURE: the reported alarm lines per arm (valid runs): visits, true Fly Wings per visit, the
    time to the Fly Wing, the boss Fly Wings by source, the sightings by class, the detect ms."""
    valid = _valid(scores, minutes, bar)
    out: dict[str, Any] = {}
    for x in ("A", "B"):
        arm = [s for s in valid if s.arm == x]
        vis = [v for s in arm for v in s.visits]
        flown = [v for v in vis if v["fly_src"] is not None]
        delays = sorted(float(v["to_fly_s"]) for v in flown)
        out[x] = {"visits": len(vis), "visits_flown": len(flown),
                  "true_flies_per_visit": round(len(flown) / len(vis), 3) if vis else None,
                  "to_fly_s": {"median": round(statistics.median(delays), 2) if delays else None,
                               "max": delays[-1] if delays else None},
                  "boss_by_src": dict(sorted(_count(f.src for s in arm for f in s.boss).items())),
                  "sightings_by_cls": dict(sorted(_count(f.cls for s in arm for f in s.boss
                                                         if f.src == "alarm").items())),
                  "detect_ms": ms_stats([m for s in arm for m in s.detect_ms])}  # fmt: skip
    return out


def verdict(scores: Sequence[Score9], minutes: float, a_kinds: set[str],
            bar: Mapping[str, Any] = BAR,
            econ: Mapping[str, Mapping[str, Any] | None] | None = None,
            ) -> dict[str, Any]:  # fmt: skip
    """PURE: the pre-registered bar (18.15). `a_kinds`: the 5b-1 runner text's kinds (the drive's
    and fly-first's own kinds are allowed besides). Deaths are JUDGED (stage5b_ab's line)."""
    v = s5b.verdict(scores, minutes, set(a_kinds) | {s5c.DRIVE_KIND, s7.FLY_KIND}, bar)
    lines = dict(v.get("lines") or {})
    rep = dict(lines.get("report") or {})
    rep["arms"] = s7.report_of(scores, minutes, bar, econ)
    rep["alarm"] = alarm_report(scores, minutes, bar)
    lines["report"] = rep
    lines["drive"] = s5c.drive_line(scores)
    lines["false_flies_h"] = false_line(scores, minutes, bar)
    lines["model"] = model_line(scores)
    out = {**v, "lines": lines}
    if out.get("why") == "an arm has no valid run":
        out["verdict"] = "INCONCLUSIVE"
        return out
    judged = [x["pass"] for k, x in lines.items() if k != "report"]
    out["verdict"] = "FAIL" if False in judged else ("INCONCLUSIVE" if None in judged else "PASS")
    return out


def table(scores: Sequence[Score9]) -> str:
    """PURE: stage7_ab's table, then the boss Fly Wings, the false ones and the visits."""
    rows = s7.table(scores).splitlines()
    out = [f"{rows[0]}  boss  false  visits"]
    for s, row in zip(scores, rows[1:], strict=True):
        n_f = sum(1 for f in s.boss if f.false)
        out.append(f"{row}  {len(s.boss):4d}  {n_f:5d}  {len(s.visits):6d}")
    return "\n".join(out)


# --- the margin's derivation (18.15, before any s9ab run) ---------------------------------------
def margin_of(rates_h: Sequence[float], hours: float, pairs: int = PAIRS,
              run_min: float = 20.0) -> dict[str, Any]:  # fmt: skip
    """PURE: BAR's margin from banked per-run false rates (an hour) over ``hours``: max(2 sqrt(2 /
    pairs) s, 2 sqrt(2 lam / H)), lam the pooled rate (at least 1 / hours), H = pairs x run_min."""
    n = len(rates_h)
    s = statistics.stdev(rates_h) if n > 1 else 0.0
    lam = max(sum(r * 1.0 for r in rates_h) / n if n else 0.0, 1.0 / hours if hours else 0.0)
    h_arm = pairs * run_min / 60.0
    sd_based = 2.0 * math.sqrt(2.0 / pairs) * s
    poisson = 2.0 * math.sqrt(2.0 * lam / h_arm)
    return {"runs": n, "hours": round(hours, 3), "sd_h": round(s, 3), "pooled_h": round(lam, 3),
            "sd_based_h": round(sd_based, 3), "poisson_h": round(poisson, 3),
            "margin_h": math.ceil(max(sd_based, poisson) * 10.0 - 1e-9) / 10.0}  # fmt: skip


def derive(sessions: Sequence[Path]) -> dict[str, Any]:
    """Reads (no screen) banked runner sessions: per session its boss Fly Wings and the false ones
    by this module's truth, an hour, and the margin over them (margin_of)."""
    project = camera_project()
    rows = []
    for d in sessions:
        ev = s2.read_events(d / "events.jsonl")
        if not ev:
            continue
        sc = Score9(label=d.name, arm="-", pair=0)
        score_session(sc, d, ev, project)
        minutes = (int(ev[-1]["t_ns"]) - int(ev[0]["t_ns"])) / 60e9
        judged = [f for f in sc.boss if f.false is not None]
        false = [f for f in judged if f.false]
        rows.append({"session": d.name, "minutes": round(minutes, 2), "boss": len(sc.boss),
                     "judged": len(judged), "false": len(false),
                     "false_h": round(len(false) * 60.0 / minutes, 3) if minutes > 0 else None,
                     "false_flies": [{"src": f.src, "cls": f.cls, "t_ns": f.t_ns}
                                     for f in false],
                     "visits": len(sc.visits),
                     "visits_flown": sum(1 for v in sc.visits if v["fly_src"])})  # fmt: skip
    rates = [float(r["false_h"]) for r in rows if r["false_h"] is not None]
    hours = sum(float(r["minutes"]) for r in rows) / 60.0
    return {"rows": rows, "margin": margin_of(rates, hours)}


class Series9(s2.Series):
    """stage2_ab's live series (the setup, the detect server, one run at a time), for A / B."""

    score_cmd = "stage9_ab.py"


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("plan", "run", "score"):
        p = sub.add_parser(name)
        p.add_argument("--label", required=True, help="the series' name (its runs' labels)")
        if name != "score":
            p.add_argument("--pairs", type=int, default=PAIRS)
            p.add_argument("--minutes", type=int, default=20,
                           help="each run's length (the Run config's minutes: 5..600)")  # fmt: skip
            p.add_argument("--order", choices=("alternate", "ab"), default="alternate")
        else:
            p.add_argument("--json", action="store_true")
            p.add_argument("--no-econ-update", action="store_true",
                           help="do not add the runs' sessions to "
                           "data/econ/lab.sqlite first")  # fmt: skip
    dv = sub.add_parser("derive", help="18.15: the false-Fly-Wing ruler on banked sessions")
    dv.add_argument("sessions", nargs="+", type=Path)
    a = ap.parse_args(argv)
    if a.cmd == "derive":
        print(json.dumps(derive(a.sessions), indent=1))
        return 0
    folder = SCRATCH / a.label
    if a.cmd == "score":
        doc = json.loads((folder / "series.json").read_text())
        if not a.no_econ_update:  # Batt 2026-11-16 (17 #7): every run's economy in lab.sqlite
            print(s7.econ_update(doc["runs"]), flush=True)
        scores = [score_run(r, folder) for r in doc["runs"]]
        base = (folder / "runner-5b1.py").read_text()
        v = verdict(scores, float(doc["minutes"]), s5b.base_kinds(base), doc["bar"],
                    econ=s7.econ_arms(scores, float(doc["minutes"])))  # fmt: skip
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
    return Series9(got, folder).run()


if __name__ == "__main__":
    raise SystemExit(main())
