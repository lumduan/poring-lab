#!/usr/bin/env python3
"""s11scr, the screen size (docs/planning/screen-size-ab.md, pre-registered 2026-11-19 22:57 ICT):
the ready-made functions box as it is (s10ab's B: xmas02sk; fly_first, fly_first_hp and
fly_first_land ON) on the lab's Rogue at xmas_dun02, one BLOCK of runs per screen size -- 1280x720
fullscreen (A) and 1920x1080 fullscreen (B, through the virtual 1280x720 client) -- each block its
own series (label), stage2_ab's setup before every run, the same code and box in both.

`plan` / `run` refuse before any input unless the box passes stage10_ab's plan (its proofs and
the B box's runner argv) and, for `run`, `.env`'s SESSION_SIZE / GAME_REGION are the block's
screen and the screen grab is that size. The switch between blocks is a person's step (the
client's OptionInfo.lua, `.env`, recreate:desktop + recreate:backend, recover gm), never this
script's.

    screen_ab.py plan  --label s11scr-1080 --screen 1080 --runs 3 --minutes 20
    screen_ab.py run   --label s11scr-1080 --screen 1080 --runs 3 --minutes 20
    screen_ab.py score --a s11scr-720 --b s11scr-1080 [--json] [--no-econ-update]
    screen_ab.py diag  s11scr-1080 s11scr-720      (the runner's records per run; reported)
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import flow_run as fr  # noqa: E402
import stage2_ab as s2  # noqa: E402
import stage4_ab as s4  # noqa: E402
import stage5c_ab as s5c  # noqa: E402
import stage7_ab as s7  # noqa: E402
import stage10_ab as s10  # noqa: E402

SCREENS = {
    "720": {"arm": "A", "session": "1280x720", "region": "0,0,1280,720", "size": (1280, 720)},
    "1080": {"arm": "B", "session": "1920x1080", "region": "0,0,1920,1080", "size": (1920, 1080)},
}
BOX_ARM = "B"  # s10ab's B box = the ready-made box as it is (fly_first_land ON), in both blocks
SCRATCH = Path("/dev/shm/poring-lab-tmp/screen-ab")
VALID_SHARE = 0.80  # stage10's: a run counts when it played >= 80 % of its time box
SE_K = 2.0
BAR = {
    "deaths": "B (1080) <= A (720) over the played runs (non-strict)",
    "kills_h": "mean(B) - mean(A) >= -2 SE (Welch; >= 2 valid runs a block, else INCONCLUSIVE)",
    "loot_h": "mean(B) - mean(A) >= -2 SE (Welch; >= 2 valid runs a block, else INCONCLUSIVE)",
    "errors": "no B run ends with a code error or refuses its start unless an A run does too",
    "reported": "openers/h, the median tick, detect ms, Fly Wings/h by kind and false boss Fly "
                "Wings/h (packets), z/h with steals, the model, each block's mean +- SE, s10ab's "
                "B runs (before), Batt's bar",
}  # fmt: skip


# --- pure: the plan -----------------------------------------------------------------------------
def runs_of(label: str, n: int, screen: str, cells: Sequence[tuple[int, int]]) -> list[s2.Run]:
    """PURE: a block's runs in order; every one plays the box arm (BOX_ARM), its label names the
    screen; the setup's warps alternate the map's two patrol starts (the chat guard)."""
    if n < 1:
        raise ValueError("at least one run")
    if screen not in SCREENS:
        raise ValueError(f"screen {screen!r}: one of {sorted(SCREENS)}")
    w = s2.warp_lines(n, cells)
    tag = SCREENS[screen]["arm"]
    return [s2.Run(k + 1, k + 1, BOX_ARM, f"{label}-r{k + 1:02d}{tag}", w[k]) for k in range(n)]


def screen_problem(screen: str, env: Mapping[str, str], grab: tuple[int, int] | None) -> str | None:
    """PURE: why the lab is not at the block's screen (None: it is)."""
    want = SCREENS[screen]
    have = (env.get("SESSION_SIZE", "").strip(), env.get("GAME_REGION", "").replace(" ", ""))
    if have != (want["session"], want["region"]):
        return (f".env says SESSION_SIZE {have[0] or '-'} / GAME_REGION {have[1] or '-'}, not the "
                f"{screen} block's {want['session']} / {want['region']}")  # fmt: skip
    if grab is None:
        return "the screen grab did not read"
    if tuple(grab) != want["size"]:
        return f"the screen grab is {grab[0]}x{grab[1]}, not {want['session']}"
    return None


# xmas02-1080-detector.md 8c (Amendment 19): a block may name another of the map's loadable models
# (unit_detector MAP_MODELS / MAP_REFERENCES); the default is s11scr's, the fixture's xmas02sk
MODELS = ("xmas02sk", "xmas02v1080")


def use_model(model: str) -> None:
    """The block's model for stage10's box, checks and pins (its module constant, read at call
    time): set before its plan, run or score."""
    if model not in MODELS:
        raise ValueError(f"the model {model!r} is not one of {MODELS}")
    s10.MODEL = model


# goblin-alarm-1080.md section 6 (the play bar, 2026-11-21): a block may set PLAYER settings
# (poring_flow.settings Field.player: the live player applies them, flow_play; never a runner
# flag nor a --tune constant), e.g. rule A's alarm_near_px. Nothing else may differ between two
# blocks: the runner's argv, box, keys and loop are checked equal to the box's own.
def player_sets(items: Sequence[str]) -> dict[str, Any] | str:
    """PURE: ``--player-set NAME=VALUE`` items as {name: value}, or why not: NAME a player
    setting, VALUE one it can take (the settings' own check), each name once."""
    from poring_flow import settings as st

    by = {f.name: f for f in st.FIELDS}
    out: dict[str, Any] = {}
    for it in items:
        name, sep, raw = it.partition("=")
        f = by.get(name.strip())
        if not sep or f is None:
            return f"--player-set {it!r}: NAME=VALUE, NAME a setting's name"
        if not f.player:
            return (f"--player-set {f.name}: not a player setting (it would reach the pinned "
                    "runner; a block changes the box, not the runner)")  # fmt: skip
        if f.name in out:
            return f"--player-set {f.name}: given twice"
        try:
            v: Any = float(raw) if f.kind in ("number", "share") else raw.strip()
        except ValueError:
            return f"--player-set {f.name}: {raw!r} is not a number"
        why = st.problem_of(f, v)
        if why:
            return f"--player-set {f.name}: {why}"
        out[f.name] = v
    return out


# xmas02-items-1080.md 8c (2026-11-21): a block may set ONE kind of runner setting too -- a BOX
# setting with its own runner flag (e.g. loot_items, the item model): the runner's argv must then
# differ from the box's in that flag's VALUE alone (box_set_arm checks it)
def box_sets(items: Sequence[str]) -> dict[str, Any] | str:
    """PURE: ``--box-set NAME=VALUE`` items as {name: value}, or why not: NAME a setting with its
    own runner flag (not a player setting, not a --tune constant), each once, VALUE one it can
    take (a choice's option, a switch's true / false, a number)."""
    from poring_flow import settings as st

    by = {f.name: f for f in st.FIELDS}
    out: dict[str, Any] = {}
    for it in items:
        name, sep, raw = it.partition("=")
        f = by.get(name.strip())
        if not sep or f is None:
            return f"--box-set {it!r}: NAME=VALUE, NAME a setting's name"
        if f.player or not f.flag:
            return (f"--box-set {f.name}: not a box setting with its own runner flag "
                    "(--player-set takes the player's)")  # fmt: skip
        if f.name in out:
            return f"--box-set {f.name}: given twice"
        raw = raw.strip()
        v: Any
        if f.kind == "switch":
            if raw.lower() not in ("true", "false", "on", "off"):
                return f"--box-set {f.name}: {raw!r} is not true / false"
            v = raw.lower() in ("true", "on")
        elif f.kind in ("number", "share"):
            try:
                v = float(raw)
            except ValueError:
                return f"--box-set {f.name}: {raw!r} is not a number"
        else:
            v = raw
        why = st.problem_of(f, v)
        if why:
            return f"--box-set {f.name}: {why}"
        out[f.name] = v
    return out


def with_player_sets(text: str, sets: Mapping[str, Any]) -> str:
    """PURE: the box text with each player setting in its group's tab of the map node (the tab
    rule of settings.with_setting_tabs: an existing tab of that name, else a new one)."""
    from poring_flow import project as pj
    from poring_flow import settings as st

    if not sets:
        return text
    d = json.loads(text)
    node = next(n for n in d["nodes"] if n.get("id") == s10.NODE)
    by = {f.name: f for f in st.FIELDS}
    for name, v in sets.items():
        f = by[name]
        tab = next((t for t in node["tabs"] if t.get("name") == f.group), None)
        if tab is None:
            tab = {"name": f.group, "main": None, "defs": [], "vars": {}}
            node["tabs"].append(tab)
        tab["vars"][f.var] = {"kind": "lit", "value": st.lit_value(f, v)}
    return pj.to_json(pj.validate(d))


def argv_differs_in(a: Sequence[str], b: Sequence[str], flags: Sequence[str]) -> bool:
    """PURE: argv ``b`` is ``a`` but for the VALUES right after ``flags`` (same length, the same
    arguments everywhere else; each such flag present in both)."""
    if len(a) != len(b):
        return False
    for i, (x, y) in enumerate(zip(a, b, strict=True)):
        if x != y and not (i > 0 and a[i - 1] == b[i - 1] and a[i - 1] in flags):
            return False
    return True


def player_set_arm(text: str, sets: Mapping[str, Any], secs: int,
                   flags: Sequence[str] = ()) -> dict[str, Any] | str:  # fmt: skip
    """PURE but for flow_play.prepare: the block's box with its player settings -- its text, its
    settings and its project hash -- or a refusal: the settings must differ from the box's in the
    named ones alone, and the runner must get the same argv, box, keys and loop. ``flags``: runner
    flags whose VALUE may differ (box settings, box_sets): only the argument right after one."""
    import flow_play as fp

    from poring_flow import project as pj

    out = with_player_sets(text, sets)
    base, vals = s5c.vals_of(text), s5c.vals_of(out)
    if isinstance(base, str) or isinstance(vals, str):
        return f"refused before any input: {base if isinstance(base, str) else vals}"
    diff = sorted(k for k in set(base) | set(vals) if base.get(k) != vals.get(k))
    want = sorted(k for k, v in sets.items() if base.get(k) != v)
    if diff != want or any(vals.get(k) != v for k, v in sets.items()):
        return (f"refused before any input: the player settings changed {diff}, not "
                f"{sorted(sets)}")  # fmt: skip
    preps = []
    for t, v in ((text, base), (out, vals)):
        h = pj.project_hash(pj.from_json(t))
        prep = fp.prepare(t, s10.NODE, secs, runner_vals={s10.NODE: v}, want_hash=h)
        if isinstance(prep, str):
            return f"refused before any input: {prep}"
        preps.append((h, prep.runners[s10.NODE]))
    (_, a), (h, b) = preps
    if not argv_differs_in(a.argv("L", None, None), b.argv("L", None, None), flags):
        return ("refused before any input: the settings changed the runner's argv beyond "
                f"{list(flags) or 'nothing'}'s value")  # fmt: skip
    for k in ("box_kwargs", "keys", "loop", "tick_left_out"):
        va, vb = getattr(a, k), getattr(b, k)
        if (va() if callable(va) else va) != (vb() if callable(vb) else vb):
            return f"refused before any input: a player setting changed the runner's {k}"
    return {"text": out, "vals": vals, "project_hash": h}


def plan_doc(label: str, n: int, minutes: float, screen: str, folder: Path,
             base: Mapping[str, Any] | None = None, sets: Mapping[str, Any] | None = None,
             base_text: str | None = None,
             box_set: Mapping[str, Any] | None = None) -> dict[str, Any] | str:  # fmt: skip
    """PURE but for stage10's reads: the block's series document, or a refusal. ``base``: a
    stage10 plan document (tests); else stage10's own plan (its proofs, the box's argv).
    ``sets``: the block's player settings (player_sets); ``base_text``: the box text they go
    into (tests), else stage10's B box."""
    got = base if base is not None else s10.plan_doc(label, 1, minutes, "ab", folder)
    if isinstance(got, str):
        return got
    arm = got["arms"][BOX_ARM]
    vals = got["vals"][BOX_ARM]
    secs = int(round(minutes * 60))
    if sets or box_set:
        from poring_flow import settings as st

        by = {f.name: f for f in st.FIELDS}
        flags = tuple(by[k].flag for k in (box_set or {}))
        ps = player_set_arm(base_text if base_text is not None
                            else s10.arm_text(BOX_ARM, minutes),
                            {**(sets or {}), **(box_set or {})}, secs, flags)  # fmt: skip
        if isinstance(ps, str):
            return ps
        arm, vals = {**arm, "project_hash": ps["project_hash"]}, ps["vals"]
    runs = runs_of(label, n, screen, s2.dh_cells() if base is None else ((1, 1), (2, 2)))
    return {
        "version": got["version"], "label": label, "screen": screen, "model": s10.MODEL,
        "screen_want": {k: SCREENS[screen][k] for k in ("session", "region")},
        "runs_n": n, "minutes": minutes, "box_arm": BOX_ARM, "arm": arm,
        "player_set": dict(sets or {}),
        "box_set": dict(box_set or {}),
        "vals": {BOX_ARM: vals}, "bar": {**s10.BAR, "screen": BAR},
        "runner_sha256": got["runner_sha256"], "drive_base": got["drive_base"],
        "serve_s": int(n * (minutes * 60 + s2.START_GRACE_S + 120) + s2.SERVE_EXTRA_S),
        "runs": [{**{k: getattr(r, k) for k in ("k", "pair", "arm", "label", "warp")},
                  "argv": fr.play_command(s4.project_file(BOX_ARM, folder), s10.NODE, r.label,
                                          folder / f"{r.label}.STOP", secs, arm["project_hash"],
                                          folder / f"runner-config-{BOX_ARM}.json")}
                 for r in runs],
    }  # fmt: skip


# --- pure: the comparison -----------------------------------------------------------------------
def false_boss_line(a_runs: Sequence[Mapping[str, Any]], b_runs: Sequence[Mapping[str, Any]],
                    minutes: float) -> dict[str, Any]:  # fmt: skip
    """PURE (goblin-alarm-1080.md 6): the FALSE boss Fly Wings an hour per block over its valid
    runs (stage9_ab's packet judgement in each run's ``boss``: ``false``), B against A: "lower"
    when B is under A by more than SE_K Poisson SEs (sqrt(nA / tA^2 + nB / tB^2)), else "not
    lower"; INCONCLUSIVE under 2 valid runs a block."""

    def rate(runs: Sequence[Mapping[str, Any]]) -> tuple[int, float, int]:
        ok = [r for r in runs if valid(r, minutes)]
        n = sum(sum(1 for b in (r.get("boss") or []) if b.get("false")) for r in ok)
        return n, sum(float(r.get("minutes") or 0.0) for r in ok) / 60.0, len(ok)

    (na, ta, ka), (nb, tb, kb) = rate(a_runs), rate(b_runs)
    out: dict[str, Any] = {"a": na, "a_h": round(ta, 3), "b": nb, "b_h": round(tb, 3),
                           "valid": [ka, kb]}  # fmt: skip
    if ka < 2 or kb < 2 or ta <= 0 or tb <= 0:
        return {**out, "verdict": "INCONCLUSIVE"}
    ra, rb = na / ta, nb / tb
    se = math.sqrt(na / ta**2 + nb / tb**2)
    return {
        **out,
        "a_per_h": round(ra, 2),
        "b_per_h": round(rb, 2),
        "diff": round(rb - ra, 2),
        "se": round(se, 2),
        "verdict": "lower" if rb - ra < -SE_K * se else "not lower",
    }


def valid(run: Mapping[str, Any], minutes: float) -> bool:
    """PURE: a scored run counts (stage10's rule): found, played >= 80 % of its time box or ended
    by a valid end (home), and not a code error."""
    if not run.get("found"):
        return False
    if run.get("rc") not in (0, 130, None):
        return False
    played = float(run.get("minutes") or 0.0)
    return played >= VALID_SHARE * minutes or run.get("end") in ("home", "weight_home")


def mean_se(xs: Sequence[float]) -> tuple[float | None, float | None]:
    """PURE: the mean and its standard error (None with fewer than 2 values for the SE)."""
    if not xs:
        return None, None
    m = statistics.fmean(xs)
    if len(xs) < 2:
        return m, None
    return m, statistics.stdev(xs) / math.sqrt(len(xs))


def diff_line(a: Sequence[float], b: Sequence[float], k: float = SE_K) -> dict[str, Any]:
    """PURE: mean(b) - mean(a) against -k SE (Welch); INCONCLUSIVE under 2 values a block."""
    ma, sa = mean_se(a)
    mb, sb = mean_se(b)
    out: dict[str, Any] = {"a": ma, "a_se": sa, "b": mb, "b_se": sb, "n": [len(a), len(b)]}
    if sa is None or sb is None or ma is None or mb is None:
        return {**out, "verdict": "INCONCLUSIVE", "why": "fewer than 2 valid runs in a block"}
    d, se = mb - ma, math.sqrt(sa * sa + sb * sb)
    ok = d >= -k * se
    return {**out, "diff": d, "se": se, "verdict": "PASS" if ok else "FAIL"}


def verdict(a_runs: Sequence[Mapping[str, Any]], b_runs: Sequence[Mapping[str, Any]],
            minutes: float) -> dict[str, Any]:  # fmt: skip
    """PURE: the judged lines over two blocks' scored runs (each a run's doc plus its rc)."""
    va = [r for r in a_runs if valid(r, minutes)]
    vb = [r for r in b_runs if valid(r, minutes)]
    deaths_a = sum(int(r.get("deaths") or 0) for r in a_runs if r.get("found"))
    deaths_b = sum(int(r.get("deaths") or 0) for r in b_runs if r.get("found"))
    err_a = sum(1 for r in a_runs if r.get("rc") not in (0, 130, None) or r.get("short"))
    err_b = sum(1 for r in b_runs if r.get("rc") not in (0, 130, None) or r.get("short"))
    lines = {
        "deaths": {"a": deaths_a, "b": deaths_b,
                   "verdict": "PASS" if deaths_b <= deaths_a else "FAIL"},
        "kills_h": diff_line([r["kills_h"] for r in va], [r["kills_h"] for r in vb]),
        "loot_h": diff_line([r["loot_h"] for r in va], [r["loot_h"] for r in vb]),
        "errors": {"a": err_a, "b": err_b,
                   "verdict": "PASS" if err_b == 0 or err_a >= err_b else "FAIL"},
    }  # fmt: skip
    states = [ln["verdict"] for ln in lines.values()]
    overall = ("WORSE" if "FAIL" in states else "INCONCLUSIVE" if "INCONCLUSIVE" in states
               else "SAME")  # fmt: skip
    return {"verdict": overall, "lines": lines, "valid": [len(va), len(vb)]}


# --- pure: the diagnostics (REPORTED only; where a screen size can move the play) ---------------
def _med(xs: Sequence[float]) -> float | None:
    return round(statistics.median(xs), 1) if xs else None


def diag_of(events: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """PURE: one hunt session's play from the runner's own records (events.jsonl): the cursor's
    reads on box targets and scans, the strikes and how they ended, the targets missed or out of
    reach, the loot hovers and picks, the escapes by cause, the detection time. Per hour where a
    rate, else shares; the packets' truth (kills, loot) is the score's, not this."""
    t = [int(e["t_ns"]) for e in events if isinstance(e.get("t_ns"), int)]
    hours = (max(t) - min(t)) / 3.6e12 if len(t) > 1 else 0.0
    kinds: dict[str, int] = {}
    verdicts: dict[str, int] = {}
    scan_v: dict[str, int] = {}
    strike_end: dict[str, int] = {}
    escapes: dict[str, int] = {}
    det_ms: list[float] = []
    settle_ms: list[float] = []
    bt = struck = 0
    loot_steps = picks = hovers = 0
    for e in events:
        k = str(e.get("kind"))
        kinds[k] = kinds.get(k, 0) + 1
        if k == "box_target":
            bt += 1
            struck += bool(e.get("struck"))
            for v in e.get("verdicts") or []:
                verdicts[str(v)] = verdicts.get(str(v), 0) + 1
            if isinstance(e.get("det_ms"), (int, float)):
                det_ms.append(float(e["det_ms"]))
            if isinstance(e.get("settle_ms"), (int, float)):
                settle_ms.append(float(e["settle_ms"]))
        elif k == "scan":
            for v, n in (e.get("verdicts") or {}).items():
                scan_v[str(v)] = scan_v.get(str(v), 0) + int(n)
        elif k == "strike":
            strike_end[str(e.get("end"))] = strike_end.get(str(e.get("end")), 0) + 1
        elif k == "escape":
            w = str(e.get("why"))
            escapes[w] = escapes.get(w, 0) + 1
        elif k == "loot_step":
            loot_steps += 1
            picks += int(e.get("picks") or 0)
            hovers += int(e.get("hovers") or 0)

    def per_h(n: int) -> float | None:
        return round(n / hours, 1) if hours > 0 else None

    def share(d: Mapping[str, int]) -> dict[str, float]:
        tot = sum(d.values())
        return {k: round(n / tot, 3) for k, n in sorted(d.items())} if tot else {}

    kills = kinds.get("kill", 0)
    strikes = kinds.get("strike", 0)
    return {
        "minutes": round(hours * 60, 1),
        "kills_h": per_h(kills), "strikes_per_kill": round(strikes / kills, 2) if kills else None,
        "strike_end": share(strike_end),
        "box_targets_h": per_h(bt), "struck_share": round(struck / bt, 3) if bt else None,
        "cursor_box": share(verdicts), "cursor_scan": share(scan_v),
        "box_miss_h": per_h(kinds.get("box_miss", 0)),
        "reach_skip_h": per_h(kinds.get("reach_skip", 0)),
        "box_ignored_h": per_h(kinds.get("box_ignored", 0)),
        "stall_h": per_h(kinds.get("stall", 0)),
        "miss_cue_h": per_h(kinds.get("miss_cue", 0)),
        "loot_steps_h": per_h(loot_steps),
        "picks_per_step": round(picks / loot_steps, 2) if loot_steps else None,
        "hovers_per_step": round(hovers / loot_steps, 1) if loot_steps else None,
        "loot_clicks_h": per_h(kinds.get("loot_click", 0)),
        "escapes_h": {k: per_h(n) for k, n in sorted(escapes.items())},
        "det_ms_median": _med(det_ms), "settle_ms_median": _med(settle_ms),
    }  # fmt: skip


def read_events(path: Path) -> list[dict[str, Any]]:
    out = []
    for ln in path.read_text(errors="replace").splitlines():
        try:
            e = json.loads(ln)
        except ValueError:
            continue
        if isinstance(e, dict):
            out.append(e)
    return out


def diag_label(label: str, demo: Path = s2.DEMO) -> list[dict[str, Any]]:
    """Every hunt session of a run's label (its demo folders), diagnosed."""
    out = []
    for d in sorted(demo.glob(f"*-{label}-hunt*")):
        ev = d / "events.jsonl"
        if ev.is_file():
            out.append({"session": d.name, **diag_of(read_events(ev))})
    return out


# --- the live parts -----------------------------------------------------------------------------
def dotenv() -> dict[str, str]:
    """`.env`'s keys (ro_agent's reader: the file, not this process's environment)."""
    import ro_agent as r

    return r.env()


def grab_size() -> tuple[int, int] | None:
    try:
        import ro_agent as r

        img = r.Screen().full()
        return int(img.shape[1]), int(img.shape[0])
    except Exception:  # noqa: BLE001 -- the refusal says it did not read
        return None


class SeriesScr(s10.Series10):
    """stage2_ab's live series for one block; every run's setup first checks the screen."""

    score_cmd = "screen_ab.py"

    def setup(self, r: s2.Run) -> None:
        why = screen_problem(self.doc["screen"], dotenv(), grab_size())
        if why:
            raise s2.Stop(f"{r.label}: {why}")
        super().setup(r)


def score_block(label: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    folder = SCRATCH / label
    doc = json.loads((folder / "series.json").read_text())
    done = {d["label"]: d for d in json.loads((folder / "done.json").read_text())} if (
        folder / "done.json").is_file() else {}  # fmt: skip
    out = []
    for r in doc["runs"]:
        sc = s10.score_run(r, folder, bar=doc["bar"])
        d = sc.doc()
        d["rc"] = done.get(r["label"], {}).get("rc")
        d["short"] = bool(done.get(r["label"], {}).get("short"))
        out.append(d)
    return doc, out


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("plan", "run"):
        p = sub.add_parser(name)
        p.add_argument("--label", required=True)
        p.add_argument("--screen", required=True, choices=sorted(SCREENS))
        p.add_argument("--runs", type=int, default=3)
        p.add_argument("--minutes", type=int, default=20)
        p.add_argument(
            "--model",
            choices=MODELS,
            default=MODELS[0],
            help="the box's use_model (8c: the 1080 model; default s11scr's)",
        )
        p.add_argument(
            "--box-set",
            action="append",
            default=[],
            metavar="NAME=VALUE",
            help="a BOX setting with its own runner flag for this block (xmas02-items-1080.md 8c: "
            "loot_items=MODEL); the runner's argv may differ in that flag's value alone",
        )
        p.add_argument(
            "--player-set",
            action="append",
            default=[],
            metavar="NAME=VALUE",
            help="a PLAYER setting for this block (goblin-alarm-1080.md 6: alarm_near_px=60); "
            "never a runner flag",
        )
    dg = sub.add_parser("diag", help="the runner's own records, per run (REPORTED only)")
    dg.add_argument("labels", nargs="+", help="run labels (or series labels: every run of it)")
    dg.add_argument("--demo", type=Path, default=s2.DEMO, help="the sessions' folder (an archive)")
    sc = sub.add_parser("score")
    sc.add_argument("--a", required=True, help="the 720 block's label (X+Y: two series)")
    sc.add_argument("--b", required=True, help="the 1080 block's label (X+Y: two series)")
    sc.add_argument("--json", action="store_true")
    sc.add_argument("--no-econ-update", action="store_true")
    a = ap.parse_args(argv)
    if a.cmd == "diag":
        for label in a.labels:
            folder = SCRATCH / label
            names = ([r["label"] for r in json.loads((folder / "series.json").read_text())["runs"]]
                     if (folder / "series.json").is_file() else [label])  # fmt: skip
            for name in names:
                for d in diag_label(name, a.demo):
                    print(json.dumps({"label": name, **d}), flush=True)
        return 0
    if a.cmd == "score":
        blocks = {}
        models: dict[str, Any] = {}
        for side, labels in (("A", a.a), ("B", a.b)):
            # "X+Y": a block completed by a second series after a stop (s11scr-1080 + 1080b)
            names = labels.split("+")
            parts = [score_block(x) for x in names]
            if len({str(d.get("model") or MODELS[0]) for d, _ in parts}) != 1:
                raise SystemExit(f"{labels}: the series name different models")
            doc = parts[0][0]
            runs = [run for _, rs in parts for run in rs]
            use_model(str(doc.get("model") or MODELS[0]))  # a block before 8c named xmas02sk
            sets_of = [d.get("player_set") or {} for d, _ in parts]
            boxes_of = [d.get("box_set") or {} for d, _ in parts]
            if any(s != sets_of[0] for s in sets_of) or any(b != boxes_of[0] for b in boxes_of):
                raise SystemExit(f"{labels}: the series set different player / box settings")
            models[side] = {
                "model": s10.MODEL,
                "series": names,
                "player_set": sets_of[0],
                "box_set": boxes_of[0],
                **s10.model_report(
                    [s10.score_run(r, SCRATCH / x, bar=d["bar"])
                     for x, (d, _) in zip(names, parts, strict=True) for r in d["runs"]]
                ),
            }  # fmt: skip
            if not a.no_econ_update:
                for d, _ in parts:
                    print(s7.econ_update(d["runs"]), flush=True)
            blocks[side] = (doc, runs)
        minutes = float(blocks["A"][0]["minutes"])
        v = verdict(blocks["A"][1], blocks["B"][1], minutes)
        res = {"runs": {k: r for k, (_, r) in blocks.items()}, "verdict": v, "models": models,
               "false_boss": false_boss_line(blocks["A"][1], blocks["B"][1], minutes)}  # fmt: skip
        print(json.dumps(res, indent=1, default=str))
        return 0
    if not 5 <= a.minutes <= 600:
        print("refused before any input: --minutes is the Run config's: 5..600", flush=True)
        return 2
    folder = SCRATCH / a.label
    use_model(a.model)
    sets = player_sets(a.player_set)
    if isinstance(sets, str):
        print(f"refused before any input: {sets}", flush=True)
        return 2
    bsets = box_sets(a.box_set)
    if isinstance(bsets, str):
        print(f"refused before any input: {bsets}", flush=True)
        return 2
    got = plan_doc(a.label, a.runs, a.minutes, a.screen, folder, sets=sets, box_set=bsets)
    if isinstance(got, str):
        print(got, flush=True)
        return 2
    why = screen_problem(a.screen, dotenv(), grab_size())
    if a.cmd == "plan":
        print(json.dumps({**got, "screen_now": why or "the block's"}, indent=1))
        return 0
    if why:
        print(f"refused before any input: {why}", flush=True)
        return 2
    folder.mkdir(parents=True, exist_ok=False)  # a series' folder is never reused
    (folder / "series.json").write_text(json.dumps(got, indent=1) + "\n")
    import huntstate_check as hc

    (folder / "runner-5b1.py").write_text(hc.git_show(hc.DRIVE_BASE, hc.TARGET))
    s4.project_file(BOX_ARM, folder).write_text(
        with_player_sets(s10.arm_text(BOX_ARM, a.minutes), {**sets, **bsets}))  # fmt: skip
    (folder / f"runner-config-{BOX_ARM}.json").write_text(
        json.dumps({s10.NODE: got["vals"][BOX_ARM]}) + "\n")  # fmt: skip
    return SeriesScr(got, folder).run()


if __name__ == "__main__":
    raise SystemExit(main())
