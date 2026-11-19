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


def plan_doc(label: str, n: int, minutes: float, screen: str, folder: Path,
             base: Mapping[str, Any] | None = None) -> dict[str, Any] | str:  # fmt: skip
    """PURE but for stage10's reads: the block's series document, or a refusal. ``base``: a
    stage10 plan document (tests); else stage10's own plan (its proofs, the box's argv)."""
    got = base if base is not None else s10.plan_doc(label, 1, minutes, "ab", folder)
    if isinstance(got, str):
        return got
    arm = got["arms"][BOX_ARM]
    secs = int(round(minutes * 60))
    runs = runs_of(label, n, screen, s2.dh_cells() if base is None else ((1, 1), (2, 2)))
    return {
        "version": got["version"], "label": label, "screen": screen,
        "screen_want": {k: SCREENS[screen][k] for k in ("session", "region")},
        "runs_n": n, "minutes": minutes, "box_arm": BOX_ARM, "arm": arm,
        "vals": {BOX_ARM: got["vals"][BOX_ARM]}, "bar": {**s10.BAR, "screen": BAR},
        "runner_sha256": got["runner_sha256"], "drive_base": got["drive_base"],
        "serve_s": int(n * (minutes * 60 + s2.START_GRACE_S + 120) + s2.SERVE_EXTRA_S),
        "runs": [{**{k: getattr(r, k) for k in ("k", "pair", "arm", "label", "warp")},
                  "argv": fr.play_command(s4.project_file(BOX_ARM, folder), s10.NODE, r.label,
                                          folder / f"{r.label}.STOP", secs, arm["project_hash"],
                                          folder / f"runner-config-{BOX_ARM}.json")}
                 for r in runs],
    }  # fmt: skip


# --- pure: the comparison -----------------------------------------------------------------------
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
    sc = sub.add_parser("score")
    sc.add_argument("--a", required=True, help="the 720 block's label")
    sc.add_argument("--b", required=True, help="the 1080 block's label")
    sc.add_argument("--json", action="store_true")
    sc.add_argument("--no-econ-update", action="store_true")
    a = ap.parse_args(argv)
    if a.cmd == "score":
        blocks = {}
        for side, label in (("A", a.a), ("B", a.b)):
            doc, runs = score_block(label)
            if not a.no_econ_update:
                print(s7.econ_update(doc["runs"]), flush=True)
            blocks[side] = (doc, runs)
        minutes = float(blocks["A"][0]["minutes"])
        v = verdict(blocks["A"][1], blocks["B"][1], minutes)
        res = {"runs": {k: r for k, (_, r) in blocks.items()}, "verdict": v}
        print(json.dumps(res, indent=1, default=str))
        return 0
    if not 5 <= a.minutes <= 600:
        print("refused before any input: --minutes is the Run config's: 5..600", flush=True)
        return 2
    folder = SCRATCH / a.label
    got = plan_doc(a.label, a.runs, a.minutes, a.screen, folder)
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
    s4.project_file(BOX_ARM, folder).write_text(s10.arm_text(BOX_ARM, a.minutes))
    (folder / f"runner-config-{BOX_ARM}.json").write_text(
        json.dumps({s10.NODE: got["vals"][BOX_ARM]}) + "\n")  # fmt: skip
    return SeriesScr(got, folder).run()


if __name__ == "__main__":
    raise SystemExit(main())
