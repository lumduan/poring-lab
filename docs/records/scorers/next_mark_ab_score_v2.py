"""next_mark_ab_score_v2.py "A1+A2+..." "B1+B2+...": next-target-mark.md Amendment 4's A/B, scored
ONCE after the chain's last run. v2 (Amendment 5, before any score): next_mark_ab_score.py read the
runner record's error as `errors`, a field Score10 does not have (it is `error`), so no run's error
could count; v2 reads `error`. Nothing else differs.

A = today's fists box (knife_swap off; queue off, mark off); B = the same + the runner's queue + the
player's mark (next_mark.py, its defaults). Per run (the labels as screen_ab ran them, e.g. mk-A1):
the run's own session folder(s) in /dev/shm/poring-lab-demo (<time>-...-<label>-r01B-hunt<N>):
  - packets (scripts/weapon_swap_study.py on each folder, summed over the run's hunt cores): kills,
    kills with a steal, the window (s), weapon changes;
  - the runner's record (stage10_ab.score_run on screen_ab's series): played minutes, how it ended,
    deaths, errors.
A run is VALID when it played >= 18 min, ended by its time box, with no error and 0 weapon changes;
invalid runs are listed and left out of the means.

The lines (Amendment 4):
  K  packet kills/h: mean(B) - mean(A) > +2 SE (Welch: sqrt(var A / nA + var B / nB)) -> PASS;
     else FAIL;
  S  steals/h (packet kills with a steal): mean(B) - mean(A) >= -2 SE -> PASS (no harm);
  D  deaths: B's total <= A's total -> PASS;
  E  errors: no B run ends with an error unless an A run does too -> PASS;
  any arm with < 3 valid runs -> INCONCLUSIVE.
  The A/B PASSES when K, S, D and E pass.
Writes the verdict JSON to /dev/shm/poring-lab-tmp/ntm2/verdict-mk.json and prints it. Read-only
otherwise. Run from the repo root with the main .venv.
"""

from __future__ import annotations

import json
import math
import statistics
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, "scripts")
import stage10_ab as s10  # noqa: E402

DEMO = Path("/dev/shm/poring-lab-demo")
SA = Path("/dev/shm/poring-lab-tmp/screen-ab")
OUT = Path("/dev/shm/poring-lab-tmp/ntm2/verdict-mk.json")
MIN_PLAYED = 18.0


def packets(folder: Path) -> dict:
    w = subprocess.run([sys.executable, "scripts/weapon_swap_study.py", str(folder)],
                       capture_output=True, text=True, timeout=900)  # fmt: skip
    t = w.stdout
    return json.loads(t[t.index("{"):]) if "{" in t else {"error": w.stderr[-300:]}


def run_row(label: str) -> dict:
    folders = sorted(p for p in DEMO.iterdir()
                     if p.is_dir() and "-hunt" in p.name
                     and p.name.rsplit("-hunt", 1)[0].endswith(f"-{label}-r01B"))  # fmt: skip
    kills = steals = swaps = 0
    window = 0.0
    errs = []
    for f in folders:
        d = packets(f)
        if "error" in d:
            errs.append(d["error"])
            continue
        kills += int(d.get("kills") or 0)
        steals += int(d.get("with_steal") or 0)
        swaps += int(d.get("swaps") or 0)
        window += float(d.get("window_s") or 0.0)
    series = json.loads((SA / label / "series.json").read_text())["runs"][0]
    sc = s10.score_run(series, SA / label)
    minutes = float(sc.minutes or 0.0)
    end = str(sc.end or "")
    error = sc.error or None  # v2: Score10's field is `error` (v1 read `errors`, never there)
    valid = (minutes >= MIN_PLAYED and "time box" in end and not error and swaps == 0
             and window > 0 and not errs and bool(folders))  # fmt: skip
    return {"label": label, "folders": [f.name for f in folders], "minutes": round(minutes, 2),
            "end": end, "deaths": int(sc.deaths or 0), "error": error, "packet_errors": errs,
            "kills": kills, "steals": steals, "window_s": round(window, 1), "swaps": swaps,
            "kills_h": round(kills / window * 3600, 2) if window else None,
            "steals_h": round(steals / window * 3600, 2) if window else None,
            "valid": valid}  # fmt: skip


def diff_line(a: list[float], b: list[float], k: float, side: str) -> dict:
    if len(a) < 3 or len(b) < 3:
        return {"verdict": "INCONCLUSIVE", "why": "< 3 valid runs an arm"}
    ma, mb = statistics.mean(a), statistics.mean(b)
    se = math.sqrt(statistics.variance(a) / len(a) + statistics.variance(b) / len(b))
    d = mb - ma
    ok = d > k * se if side == "better" else d >= -k * se
    return {"mean_A": round(ma, 2), "mean_B": round(mb, 2), "diff": round(d, 2),
            "se": round(se, 2), "bar": (f"> +{k} SE" if side == "better" else f">= -{k} SE"),
            "verdict": "PASS" if ok else "FAIL"}  # fmt: skip


def main() -> int:
    arms = {"A": sys.argv[1].split("+"), "B": sys.argv[2].split("+")}
    rows = {arm: [run_row(x) for x in labels] for arm, labels in arms.items()}
    ok = {arm: [r for r in rs if r["valid"]] for arm, rs in rows.items()}
    lines = {
        "K_kills_h": diff_line([r["kills_h"] for r in ok["A"]], [r["kills_h"] for r in ok["B"]],
                               2.0, "better"),  # fmt: skip
        "S_steals_h": diff_line([r["steals_h"] for r in ok["A"]],
                                [r["steals_h"] for r in ok["B"]], 2.0, "no_harm"),  # fmt: skip
    }
    da = sum(r["deaths"] for r in rows["A"])
    db = sum(r["deaths"] for r in rows["B"])
    lines["D_deaths"] = {"A": da, "B": db, "verdict": "PASS" if db <= da else "FAIL"}
    ea = sum(1 for r in rows["A"] if r["error"])
    eb = sum(1 for r in rows["B"] if r["error"])
    lines["E_errors"] = {"A": ea, "B": eb, "verdict": "PASS" if eb == 0 or ea > 0 else "FAIL"}
    vs = [v["verdict"] for v in lines.values()]
    verdict = ("INCONCLUSIVE" if "INCONCLUSIVE" in vs else
               "PASS" if all(v == "PASS" for v in vs) else "FAIL")  # fmt: skip
    doc = {"ab": "next-target-mark.md Amendment 4", "arms": arms, "rows": rows,
           "invalid": [r["label"] for rs in rows.values() for r in rs if not r["valid"]],
           "lines": lines, "verdict": verdict}  # fmt: skip
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(doc, indent=1, default=str))
    print(json.dumps(doc, indent=1, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
