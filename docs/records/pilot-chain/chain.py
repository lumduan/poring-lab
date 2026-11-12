"""chain.py -- the NIGHT CHAIN (Batt 2026-11-11 22:1x: "prevent this from happening again; it wastes time"):
runs the pre-registered pilot QUEUE by itself, so a pilot never waits for the agent to wake up.

    python chain.py LAST_KILL_EPOCH        (detached: setsid nohup ...; logs to chain.log)

queue.txt: one pilot a line, "LABEL|REC_LABEL|FLAGS|MINUTES" (REC "-" = not recorded); lines may be
APPENDED while it runs; a label in done.txt is skipped. STOP (a file) ends the chain before the next pilot.
For each pilot, in order:
  1. the weight: read from the Basic Info line (gm_state); unread or >= 40 % -> immunity ON, clear-bag of
     the Etc + Use tabs (the Knife on F4 and the worn gear stay);
  2. the MVP (immunity ON): mvp_look; alive -> @killmonster2 and read "1[dead]" back; dead -> a pilot
     must END before last_kill + 60 min, else poll every 3 min until it shows alive, then kill;
  3. immunity OFF, judged on the Chat tab's last line (templates cut 2026-11-11); else a 2nd toggle
     (with a filler line for the chat guard); unknown -> STOP;
  4. the pilot (pilot_rec2.sh / pilot_rec_min.sh), waited to its PILOT DONE;
  5. in the background: ship its recording, score it (score_full.sh).
Anything it cannot judge stops the chain (a person first) with the reason in chain.log.
"""
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import chatjudge as cj  # noqa: E402

REPO = Path("/home/bot/docker/poring-lab")
T = Path("/dev/shm/poring-lab-tmp")
C = T / "chain"
PY = str(REPO / ".venv/bin/python")
LOG = C / "chain.log"
WINDOW_S = 60 * 60  # the MVP respawns 61-70 min after its death (measured 61.6, 69.6, 64.4, 63, 61, 69, 70)
POLL_S = 180
WEIGHT_CLEAR = 0.40
WEIGHT_IDLE_CLEAR = 0.28  # 23:2x: in an MVP wait a clear-bag costs nothing: clear from here
IMM = {"off": np.load(C / "imm-off-line.npy"), "on": np.load(C / "imm-on-line.npy")}
DEAD = np.load(C / "mvp-dead-line.npy")
# 22:33 fix: the first ENV was a bare PATH without ~/.local/bin (run_pilot_v3's `uv` -> rc 127) and no TZ
# (the recorder named its folder in UTC). Inherit the launching shell's environment instead.
ENV = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "TMPDIR": str(T), "TZ": "Asia/Bangkok"}
ENV["PATH"] = "/home/bot/.local/bin:" + ENV.get("PATH", "/usr/bin:/bin")


def ts() -> str:
    return time.strftime("%H:%M:%S")


def log(msg: str) -> None:
    with open(LOG, "a") as fh:
        fh.write(f"[{ts()}] {msg}\n")


class Stop(Exception):
    pass


def sh(cmd: list[str], timeout: float = 600) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=REPO, env=ENV, capture_output=True, text=True, timeout=timeout)


def gm(line: str) -> str:
    """11-12 08:55 fix: crusader.py's identity check can refuse a line (right after a @warp, the map
    still loading: "'@killmonster2' NOT sent" on stderr), and this returned "" silently -- the F1
    aftercare's kill never ran. Now: one retry 3 s later, then Stop."""
    for attempt in (1, 2):
        out = sh([PY, "scripts/crusader.py", "--char", "thief", "gm", "--job", "rogue", line], 180)
        last = (out.stdout.strip().splitlines() or [""])[-1]
        if '"typed": true' in last:
            return last
        why = (out.stderr or last).strip()
        log(f"gm {line!r} attempt {attempt} not typed: {why[-160:]}")
        if "identical chat line" in why:  # the chat guard's repeat rule: a filler line first
            sh([PY, "scripts/crusader.py", "--char", "thief", "gm", "--job", "rogue", "@where"], 180)
        time.sleep(3)
    raise Stop(f"gm {line!r}: not typed after 2 attempts")


def chat(tag: str) -> str:
    p = C / f"chat-{tag}-{int(time.time())}.png"
    sh([PY, str(T / "chat_shot.py"), str(p)], 120)
    return str(p)


def imm_state(tag: str) -> str:
    state, ds = cj.judge(chat(tag), IMM)
    log(f"immunity read {state} {json.dumps({k: round(v, 3) for k, v in ds.items()})}")
    return state


def set_imm(target: str) -> None:
    if NO_IMM:  # Batt 2026-11-12 ~19:1x: "no immunity from now on; play like a normal player"
        log(f"immunity {target}: skipped (--no-immunity: she is never immune)")
        return
    gm("@monsterignore")
    s = imm_state(f"imm-{target}-1")
    if s == target:
        return
    if s == "unknown":
        raise Stop("immunity: the answer line is unreadable")
    gm("@where")  # a filler: the chat guard refuses a 3rd identical line in a row
    gm("@monsterignore")
    if imm_state(f"imm-{target}-2") != target:
        raise Stop(f"immunity: not {target} after two toggles")


def mvp_dead(tag: str) -> bool:
    sh(["bash", str(T / "mvp_look.sh"), tag], 300)
    p = T / "mvp" / f"mvp-{tag}-chat.png"
    d = cj.dist(cj.last_green_line(str(p)), DEAD)
    log(f"mvp {tag}: dist to 1[dead] {d:.3f}")
    return d < 0.04


def kill_mvp(tag: str) -> float:
    gm("@killmonster2")
    t = time.time()
    if not mvp_dead(f"{tag}-after"):
        raise Stop("the MVP did not read dead after @killmonster2")
    log(f"MVP killed {time.strftime('%H:%M:%S', time.localtime(t))}")
    return t


def weight_share() -> float | None:
    code = ("import sys; sys.path.insert(0,'scripts'); import ro_agent as r, gm_state as gs, dungeon_hunt as dh\n"
            "with r.session('rule:chain-weight') as (agent, screen):\n"
            "    fr = gs._frames(screen); w = gs._weight(fr)\n"
            "    print(gs.weight_share(w) if w else ('RED' if dh.overweight_red(fr[0]) else 'NONE'))")
    out = sh([PY, "-c", code], 120).stdout.strip().splitlines()
    v = out[-1] if out else "NONE"
    log(f"weight read {v}")
    try:
        return float(v)
    except ValueError:
        return None


def clear_bag() -> None:
    out_dir = T / f"clear-bag-{int(time.time())}"
    out_dir.mkdir(parents=True, exist_ok=True)
    r = sh([PY, "scripts/dungeon_hunt.py", "clear-bag", "--char", "rogue", "--tabs", "etc,use",
            "--out", str(out_dir)], 900)
    last = (r.stdout.strip().splitlines() or [""])[-1]
    log(f"clear-bag rc={r.returncode} {last[-160:]}")
    if r.returncode != 0:
        raise Stop("clear-bag failed")


def worker_free(max_s: float = 35 * 60) -> None:
    """The vision worker runs one job at a time: wait until no detect server / job of ours is in
    it (a refused or killed run's server keeps its own time box)."""
    t0 = time.time()
    while True:
        out = subprocess.run(["docker", "top", "poring-lab-vision-worker-1"], capture_output=True,
                             text=True, timeout=30).stdout
        if "poring_vision" not in out:
            return
        if time.time() - t0 > max_s:
            raise Stop("the vision worker stayed busy")
        log("the vision worker is busy (a job of ours): waiting 20 s")
        time.sleep(20)


def end_servers(label: str) -> None:
    """Our own detect server(s) in the worker, ended by host PID (uid bot) after a failed run."""
    out = subprocess.run(["docker", "top", "poring-lab-vision-worker-1"], capture_output=True,
                         text=True, timeout=30).stdout
    for ln in out.splitlines():
        f = ln.split()
        if len(f) > 8 and f[0] == "bot" and f[7:10] == ["python", "-m", "poring_vision.detect_server"]:
            subprocess.run(["kill", "-TERM", f[1]], timeout=10)
            log(f"{label}: the run failed; ended its detect server (pid {f[1]})")


def pilot_alive(label: str) -> bool:
    """23:2x: a pilot runner of this label is a live process (pilot_rec2.sh / pilot_rec_min.sh)."""
    out = subprocess.run(["ps", "-eo", "args"], capture_output=True, text=True, timeout=30).stdout
    return any(("pilot_rec2.sh " + label + " ") in ln or ("pilot_rec_min.sh " + label + " ") in ln
               for ln in out.splitlines())


def pilot_state(label: str) -> str:
    """none (no folder) / running (its runner alive, no PILOT DONE) / done / stale (a person first)."""
    pr = T / label / "progress.txt"
    if not pr.exists():
        return "none"
    if "PILOT DONE" in pr.read_text():
        return "done"
    return "running" if pilot_alive(label) else "stale"


def run_pilot(label: str, rec: str, flags: str, minutes: int, adopt: bool = False) -> str:
    d = T / label
    if not adopt:
        if d.exists() and (d / "progress.txt").exists():
            raise Stop(f"{label}: its folder exists already (a person first)")
        script = "pilot_rec2.sh" if minutes == 25 else "pilot_rec_min.sh"
        args = ["bash", str(T / script), label, rec, flags] + ([] if minutes == 25 else [str(minutes)])
        with open(T / f"{label}.launch.log", "w") as fh:
            subprocess.Popen(args, cwd=REPO, env=ENV, stdout=fh, stderr=subprocess.STDOUT,
                             stdin=subprocess.DEVNULL, start_new_session=True)
        log(f"{label} started ({flags}; {minutes} min; rec {rec})")
    else:
        log(f"{label}: adopted (its runner was already going when the chain restarted)")
    failed_at = None
    while True:
        time.sleep(10)
        p = d / "progress.txt"
        txt = p.read_text() if p.exists() else ""
        # 22:33 fix: a run that FAILS (p71's rc 127) left its detect server holding the worker for the
        # whole time box (~27 min); end our own server by PID 30 s after a non-zero run rc
        bad = [ln.split("run rc=")[1].strip() for ln in txt.splitlines() if "run rc=" in ln]
        if bad and bad[0] != "0" and "PILOT DONE" not in txt:
            failed_at = failed_at or time.time()
            if time.time() - failed_at > 30:
                end_servers(label)
                failed_at = time.time() + 120  # once, then wait for PILOT DONE
        if "PILOT DONE" in txt:
            rc = next((ln.split("run rc=")[1] for ln in txt.splitlines() if "run rc=" in ln), "?")
            log(f"{label} DONE run rc={rc}")
            return rc


def post(label: str, rec: str) -> None:
    cmd = (f"cd {REPO}; export PYTHONDONTWRITEBYTECODE=1 TMPDIR={T}; "
           f"R=$(ls ~/poring-lab-rec | grep -- '{rec}$' | head -1); "
           f"[ -n \"$R\" ] && {PY} scripts/dataset_ship.py ship $R > {T}/ships/{label}-rec.log 2>&1; "
           f"nice -n 10 bash {T}/score_full.sh {label} > {T}/{label}/score_full.out 2>&1; "
           f"echo 'all scored' >> {T}/{label}/score_full.out; "
           # ADR-0025 (11-12): the judged run joins data/econ/lab.sqlite (update: once per id)
           f"S=$(ls -d /dev/shm/poring-lab-demo/*-{label.replace('p', 'xmas02-p', 1)} 2>/dev/null | tail -1); "
           f"[ -n \"$S\" ] && nice -n 10 {PY} scripts/econ_db.py update \"$S\" "
           f"> {T}/{label}/econ_db.out 2>&1")
    subprocess.Popen(["bash", "-c", cmd], env=ENV, stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL, start_new_session=True)


# 11-12: --poll-max-min N (default 40): a start whose last death is only BOUNDED polls longer
POLL_MAX_S = 60 * int(next((sys.argv[i + 1] for i, x in enumerate(sys.argv[:-1]) if x == "--poll-max-min"), 40))
LIVE = "--mvp-live" in sys.argv[2:]  # rogue-xmas02.md 4CS: set only after the flee proof PASSES
# Batt 2026-11-12 ~19:1x (rogue-xmas02.md 4DF): no immunity ever, the MVP left alive, no MVP GM lines
NO_IMM = "--no-immunity" in sys.argv[2:]


def main() -> int:
    last_kill = float(sys.argv[1])
    log(f"MVP mode: {'LIVE (no kills; the bot escapes it, 4CS)' if LIVE else 'killed before each window'}")
    log(f"chain start; last MVP kill {time.strftime('%H:%M:%S', time.localtime(last_kill))}")
    done = set((C / "done.txt").read_text().split()) if (C / "done.txt").exists() else set()
    try:
        while True:
            if (C / "STOP").exists():
                log("STOP file: the chain ends")
                return 0
            items = [ln.strip() for ln in (C / "queue.txt").read_text().splitlines() if ln.strip()]
            todo = [ln for ln in items if ln.split("|")[0] not in done]
            if not todo:
                log("queue empty: waiting for lines (60 s)")
                time.sleep(60)
                continue
            label, rec, flags, minutes = todo[0].split("|")
            minutes = int(minutes)
            st = pilot_state(label)
            if st == "stale":
                raise Stop(f"{label}: its folder exists, no PILOT DONE and no live runner")
            if st in ("running", "done"):  # 23:2x: a restart adopts it (no setup steps again)
                rc = (run_pilot(label, rec, flags, minutes, adopt=True) if st == "running" else
                      next((ln.split("run rc=")[1].strip() for ln in
                            (T / label / "progress.txt").read_text().splitlines()
                            if "run rc=" in ln), "?"))
                if not (T / label / "score_full.out").exists():
                    post(label, rec if rec != "-" else "NO-REC")
                if rc.strip() != "0":
                    raise Stop(f"{label}: run rc={rc} (adopted)")
                done.add(label)
                with open(C / "done.txt", "a") as fh:
                    fh.write(label + "\n")
                continue
            # 1. the weight (read; the clear-bag below goes where it costs no window)
            w = weight_share()
            heavy = w is None or w >= WEIGHT_CLEAR
            # 2. the MVP
            if LIVE:  # 4CS: ONLY after the flee proof PASSES -- the bot escapes the MVP as in real play
                if heavy:
                    set_imm("on")
                    clear_bag()
                if NO_IMM:  # no @mobsearch either: a normal player has none
                    log(f"{label}: MVP-LIVE, no immunity: the MVP is left as it is (no check, no kill)")
                else:
                    alive = not mvp_dead(f"pre-{label}")
                    log(f"{label}: MVP-LIVE (4CS): the MVP reads {'ALIVE' if alive else 'dead'}; no kill")
            else:
                set_imm("on")
            if LIVE:
                pass  # no kill, no wait for a respawn window
            elif not mvp_dead(f"pre-{label}"):
                if heavy:
                    clear_bag()  # before the kill: the window starts after it
                last_kill = kill_mvp(f"pre-{label}")
            else:
                if heavy:
                    clear_bag()
                if time.time() + (minutes + 4) * 60 > last_kill + WINDOW_S:
                    # 23:2x (4CD's rule): a SHORTER queued item that still fits runs first (U0)
                    fit = next((ln for ln in todo[1:] if time.time() + (int(ln.split("|")[3]) + 4)
                                * 60 <= last_kill + WINDOW_S), None)  # fmt: skip
                    if fit is not None:
                        label, rec, flags, minutes = fit.split("|")
                        minutes = int(minutes)
                        log(f"{label} fits the short window: it runs before {todo[0].split('|')[0]}")
                    else:
                        if not heavy and w is not None and w >= WEIGHT_IDLE_CLEAR:
                            log("the wait for the MVP: a clear-bag now costs no window")
                            clear_bag()
                        log(f"{label}: the window is too short; polling the MVP every {POLL_S} s")
                        t_poll0 = time.time()
                        while mvp_dead(f"poll-{label}-{int(time.time())}"):
                            if time.time() - t_poll0 > POLL_MAX_S:
                                raise Stop(f"the MVP did not respawn in {POLL_MAX_S // 60} min of polling")
                            time.sleep(POLL_S)
                        last_kill = kill_mvp(f"pre-{label}")
            # 3. immunity off, 4. the pilot, 5. post
            worker_free()
            set_imm("off")
            rc = run_pilot(label, rec, flags, minutes)
            post(label, rec if rec != "-" else "NO-REC")
            if rc.strip() != "0":
                raise Stop(f"{label}: run rc={rc} (its scores are made; look at {label}/run.log)")
            done.add(label)
            with open(C / "done.txt", "a") as fh:
                fh.write(label + "\n")
    except Stop as exc:
        log(f"STOPPED: {exc} (a person first)")
        return 2
    except Exception as exc:  # noqa: BLE001
        log(f"STOPPED on an error: {type(exc).__name__}: {exc}")
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
