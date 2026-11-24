"""score_fists.py LABEL...: fists-1080.md Amendment 2's rulers for recorded pilots (fst* or the base
ifH*): stage10_ab.score_run per run (kills/h, loot/h over the played minutes, deaths, end, errors),
weapon_swap_study on the NAS session (packet kills/h, steals/h, stolen share, kill seconds), the
economy line of score_run. Scratch, reads only."""
import json, subprocess, sys
from pathlib import Path
sys.path.insert(0, "scripts")
import stage10_ab as s10

SA = Path("/dev/shm/poring-lab-tmp/screen-ab")
out = {}
for lab in sys.argv[1:]:
    folder = SA / f"{lab}-play"
    r = json.loads((folder / "series.json").read_text())["runs"][0]
    sc = s10.score_run(r, folder)
    d = {k: getattr(sc, k) for k in sc.__dataclass_fields__}
    m = float(d["minutes"] or 0)
    sess = next(p.name for p in Path("/mnt/poring-lab-datasets").iterdir() if p.name.endswith(f"-rdp-xmas02-{lab}"))
    w = subprocess.run([sys.executable, "scripts/weapon_swap_study.py", f"/mnt/poring-lab-datasets/{sess}"],
                       capture_output=True, text=True)
    wd = json.loads(w.stdout[w.stdout.index("{"):]) if "{" in w.stdout else {"error": w.stderr[-300:]}
    win = float(wd.get("window_s") or 0)
    econ = {k: d[k] for k in d if any(x in k for x in ("zeny", "econ", "z_h", "gross", "net"))}
    out[lab] = {"session": sess, "minutes": round(m, 2), "end": d.get("end"), "deaths": d.get("deaths"),
                "errors": d.get("errors"), "runner_kills": d.get("kills"), "loot_steps": d.get("loot_steps"),
                "runner_kills_h": round(d["kills"] / m * 60, 1) if m else None,
                "runner_loot_h": round(d["loot_steps"] / m * 60, 1) if m else None,
                "packet_kills": wd.get("kills"), "with_steal": wd.get("with_steal"), "window_s": win,
                "packet_kills_h": round(wd["kills"] / win * 3600, 1) if win else None,
                "steals_h": round(wd["with_steal"] / win * 3600, 1) if win else None,
                "kill_s_with": wd.get("kill_s_with_steal"), "kill_s_without": wd.get("kill_s_without_steal"),
                "swaps": wd.get("swaps"), "econ": econ}
print(json.dumps(out, indent=1, default=str))
