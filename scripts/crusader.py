#!/usr/bin/env python3
"""The dedicated CRUSADER test character (Batt 2026-10-21: "Character A (2nd character on the GM
account, with the name+job check before every command)"; docs/planning/crusader-orcsdun01.md).

Group 20 is per ACCOUNT, so a level / job / stat / item command typed while the WRONG character is
online would change the Novice GM whose baseline backs every past test. Every GM line this module
types therefore passes three checks first, and nothing is sent on a mismatch:
  1. the DB says the Crusader is the account's online character (as ro_agent's own login checks do);
  2. Basic Info's NAME line (client px NAME_BOX; the window sits at the client origin in the
     standard layout) matches the Crusader's reference crop;
  3. its JOB line matches the reference of the job the caller expects (Novice -> Swordman ->
     Crusader; each reference is cut from a frame the parent judged, `cut-job`).
A crop "matches" when at most MATCH pixels differ strongly (> DIFF_LEVEL in any channel): the rule
gm_state uses for the level lines. Cut 2026-10-21 17:18: the name crop differs from itself by 0 px
and from the Novice GM's (Valcd8bd6) by 216.

The typing itself is ro_agent's: the client in front, the UI gate, chat_guard, the gm.jsonl record.
`ro_agent.gm()` refuses while the Crusader is online (it requires the Novice GM), so the two
characters' scripts cannot cross.

    crusader.py check [--job JOB]          print the identity read (no input)
    crusader.py gm --job JOB '@command'    one guarded GM line
    crusader.py cut-job JOB                save the current job line as JOB's reference
                                           (only after a judged frame shows that job)

Reference crops and the name live in data/crusader/ (gitignored: client pixels).
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np
import numpy.typing as npt

sys.path.insert(0, str(Path(__file__).resolve().parent))

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "crusader"
NAME_BOX = (4, 22, 120, 36)  # x0, y0, x1, y1, client px: Basic Info's character name line
JOB_BOX = (4, 36, 120, 50)  # its job line
DIFF_LEVEL = 60  # gray levels (gm_state.DIFF_LEVEL)
MATCH = 4  # at most this many strongly differing pixels (gm_state.MATCH)
JOBS = ("novice", "swordman", "crusader")

Img = npt.NDArray[np.uint8]


def crop(client: Img, box: tuple[int, int, int, int]) -> npt.NDArray[np.int16]:
    x0, y0, x1, y1 = box
    return client[y0:y1, x0:x1, :3].astype(np.int16)


def differing(a: npt.NDArray[np.int16], b: npt.NDArray[np.int16]) -> int:
    """PURE: pixels that differ strongly in any channel (shape mismatch = everything differs)."""
    if a.shape != b.shape:
        return int(max(a.size, b.size))
    return int((np.abs(a - b).max(axis=2) > DIFF_LEVEL).sum())


def identity(client: Img, name_ref: Any, job_refs: dict[str, Any], job: str) -> dict[str, Any]:
    """PURE: the name and job reads of one client frame against the references."""
    if job not in job_refs:
        return {"ok": False, "why": f"no reference for job {job!r} (cut-job after a judged frame)"}
    name_d = differing(crop(client, NAME_BOX), name_ref)
    job_d = differing(crop(client, JOB_BOX), job_refs[job])
    ok = name_d <= MATCH and job_d <= MATCH
    why = None if ok else ("name" if name_d > MATCH else "job")
    return {"ok": ok, "why": why, "name_diff": name_d, "job_diff": job_d, "job": job}


def load_refs() -> tuple[str, Any, dict[str, Any]]:
    name = json.loads((DATA / "char.json").read_text())["name"]
    name_ref = np.load(DATA / "ref_name.npy")
    jobs = {
        j: np.load(DATA / f"ref_job_{j}.npy") for j in JOBS if (DATA / f"ref_job_{j}.npy").exists()
    }
    return name, name_ref, jobs


def client_frame(screen: Any) -> Img:
    import ro_agent as r

    x0, y0, w, h = r.game_region()
    return np.asarray(screen.grab(x0, y0, w, h)[1])[..., :3]


def check(screen: Any, job: str) -> dict[str, Any]:
    """The three checks on a fresh frame (no input)."""
    import ro_agent as r

    name, name_ref, jobs = load_refs()
    online = r.online_chars("gm")
    if online != [name]:
        return {"ok": False, "why": f"online on the GM account: {online} (want [{name!r}])"}
    if r.black(screen):
        return {"ok": False, "why": "the game region is black"}
    return identity(client_frame(screen), name_ref, jobs, job)


def gm_line(agent: Any, screen: Any, command: str, job: str) -> dict[str, Any]:
    """One GM line, typed only after `check` passes; ro_agent.gm's path without its Novice-GM
    check (which would refuse here by design)."""
    import chat_guard
    import ro_agent as r

    if not command.startswith("@"):
        raise r.Stop("GM commands start with @")
    got = check(screen, job)
    if not got["ok"]:
        raise r.Stop(f"crusader: identity check failed ({got}): {command!r} NOT sent")
    record = {"t_mono_ns": r.ns(), "t_wall": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
              "cmd": command, "char": "crusader", "identity": got}  # fmt: skip
    r.STATE_DIR.mkdir(parents=True, exist_ok=True)
    with (r.STATE_DIR / "gm.jsonl").open("a") as fh:
        fh.write(json.dumps(record) + "\n")
    r.activate_client(agent, screen)
    try:
        r.chat_line(agent, screen, command)
    except chat_guard.ChatRefused as exc:
        raise r.Stop(f"crusader: {command!r} refused by chat_guard ({exc})") from None
    r.log(f"crusader gm: {command}")
    return got


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)  # fmt: skip
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check")
    c.add_argument("--job", default="novice", choices=JOBS)
    g = sub.add_parser("gm")
    g.add_argument("--job", required=True, choices=JOBS)
    g.add_argument("line")
    k = sub.add_parser("cut-job")
    k.add_argument("job", choices=JOBS)
    a = ap.parse_args()
    import ro_agent as r

    if a.cmd == "check":
        screen = r.Screen()
        try:
            print(json.dumps(check(screen, a.job)))
        finally:
            screen.close()
        return 0
    if a.cmd == "cut-job":
        screen = r.Screen()
        try:
            name, name_ref, _ = load_refs()
            frame = client_frame(screen)
            if r.online_chars("gm") != [name] or differing(crop(frame, NAME_BOX), name_ref) > MATCH:
                raise r.Stop("cut-job: the Crusader is not the character on screen")
            np.save(DATA / f"ref_job_{a.job}.npy", crop(frame, JOB_BOX))
            print(f"saved ref_job_{a.job}.npy")
        finally:
            screen.close()
        return 0
    with r.session("rule:crusader-gm") as (agent, screen):
        agent.wait_for_human()
        print(json.dumps(gm_line(agent, screen, a.line, a.job)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
