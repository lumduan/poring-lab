#!/usr/bin/env python3
"""The dedicated TEST characters on the GM account: the CRUSADER (Batt 2026-10-21: "Character A
(2nd character on the GM account, with the name+job check before every command)";
docs/planning/crusader-orcsdun01.md) and, since 2026-10-24, the THIEF (slot 3; Batt's economics
phase, docs/planning/thief-payon.md). Each character has its own data dir and job list (CHARS);
every function defaults to the Crusader, so its callers are unchanged.

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
`ro_agent.gm()` refuses while a test character is online (it requires the Novice GM), so the
characters' scripts cannot cross.

    crusader.py [--char C] check [--job JOB]        print the identity read (no input)
    crusader.py [--char C] gm --job JOB '@command'  one guarded GM line
    crusader.py [--char C] cut-job JOB              save the current job line as JOB's reference
                                                    (only after a judged frame shows that job)
    crusader.py [--char C] cut-name                 save the current name line as the reference
                                                    (only after a judged frame; the DB must say
                                                    the character is the one online)
    crusader.py plate --request ID --out FILE       the name line of the character on screen, for
                                                    the Settings page's Remember (the Run helper
                                                    runs it; no input, nothing kept here)

Reference crops and the name live in data/<char>/ (gitignored: client pixels).
"""

from __future__ import annotations

import argparse
import base64
import json
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np
import numpy.typing as npt

from poring_env import runidentity

sys.path.insert(0, str(Path(__file__).resolve().parent))

ROOT = Path(__file__).resolve().parents[1]
CHARS: dict[str, tuple[str, ...]] = {  # each test character's jobs, in the order it takes them
    "crusader": ("novice", "swordman", "crusader"),
    "thief": ("novice", "thief", "rogue"),  # Batt 2026-10-24 (thief-payon.md)
    # Batt 2026-11-18 ~22:1x: "create another character, another name, a Rogue with the same
    # settings as the old one, and Run it" (ADR-0020 Amendment Q's test of RUN_IDENTITY=known)
    "rogue2": ("novice", "thief", "rogue"),
}
DATA = ROOT / "data" / "crusader"  # the Crusader's (kept for callers); data_dir(char) in general
NAME_BOX = (4, 22, 120, 36)  # x0, y0, x1, y1, client px: Basic Info's character name line
JOB_BOX = (4, 36, 120, 50)  # its job line
DIFF_LEVEL = 60  # gray levels (gm_state.DIFF_LEVEL)
MATCH = 4  # at most this many strongly differing pixels (gm_state.MATCH)
JOBS = CHARS["crusader"]


def data_dir(char: str = "crusader") -> Path:
    if char not in CHARS:
        raise ValueError(f"unknown test character {char!r} (known: {sorted(CHARS)})")
    return ROOT / "data" / char


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


def load_refs(char: str = "crusader") -> tuple[str, Any, dict[str, Any]]:
    d = data_dir(char)
    name = json.loads((d / "char.json").read_text())["name"]
    name_ref = np.load(d / "ref_name.npy")
    jobs = {
        j: np.load(d / f"ref_job_{j}.npy") for j in CHARS[char] if (d / f"ref_job_{j}.npy").exists()
    }
    return name, name_ref, jobs


def client_frame(screen: Any) -> Img:
    import ro_agent as r

    x0, y0, w, h = r.game_region()
    return np.asarray(screen.grab(x0, y0, w, h)[1])[..., :3]


# Who may play a Run (Batt 2026-11-18: "no need to lock the character's name: a user should be
# free to create a character; teaching many at once, the same name for all would confuse"). The
# PLAYER path only (``check(db=False)``: a Run, its start checks); a GM line (db=True) always proves
# the lab's own character before it types (gm_line). ADR-0020 Amendment Q.
# ➡️ 2026-11-19 (ADR-0020 Amendment R, Batt: "any the default, this machine too, and settable in
# Settings ... on Settings, Save and it works at once"): the mode and the characters a Run knows
# live on the SETTINGS PAGE (settings/run-identity.json, poring_env.runidentity), read at every
# check -- .env's RUN_IDENTITY is no longer read. No file = any (every install, the lab too). A
# character is remembered by the page's Remember button (the Run helper runs `plate` below once).
IDENTITY_FILE = ROOT / "settings" / runidentity.FILE_NAME
UNREADABLE = "unreadable"  # run_identity() when the file does not parse (every Run's check fails)
IDENTITY_ANY_WORDS = ("any character: a Run does not check the name or the job (Who may play a "
                      "Run: any, on the Settings page; each player makes their own)")  # fmt: skip
# "known" (Batt 2026-11-18 ~22:1x, after a Run was pressed twice on another server's character,
# rog101): only the characters REMEMBERED here (their name line cut once, on the Settings page)
# play; a character of another server has no picture here and is refused at the first line.
PLATE_GAP_S = 0.5  # `plate`: the second look, to tell a still name line from a moving scene
BLANK_MIN_PX = 20  # a name line has 148-186 pixels far from its median (the lab's three, measured)


def identity_store(path: Path | None = None) -> runidentity.Store | str:
    """The Settings page's store (read when called): no file = the default (any, no character);
    a file that does not parse = its problem in words (a Run's check then fails: fail closed)."""
    f = IDENTITY_FILE if path is None else path
    try:
        text = f.read_text(encoding="utf-8")
    except FileNotFoundError:
        return runidentity.DEFAULT
    except (OSError, UnicodeDecodeError) as e:
        return f"{f.name} cannot be read ({type(e).__name__})"
    got = runidentity.parse(text)
    return got if isinstance(got, runidentity.Store) else f"{f.name}: {got}"


def run_identity() -> str:
    """This install's mode: "any" | "known" | "mine", or UNREADABLE (the Settings page's file)."""
    got = identity_store()
    return got.mode if isinstance(got, runidentity.Store) else UNREADABLE


def unreadable_words(why: str) -> str:
    return (f"the Run's identity setting cannot be read ({why}): open the Settings page "
            "(Who may play a Run) and save it again")  # fmt: skip


def plate_array(c: runidentity.Character) -> npt.NDArray[np.int16]:
    return np.frombuffer(c.rgb, np.uint8).reshape(c.h, c.w, 3).astype(np.int16)


def known_chars(store: runidentity.Store | None = None) -> list[tuple[str, str, Any]]:
    """The characters this install knows: (id, name, name-line picture) of every character
    remembered on the Settings page."""
    got = identity_store() if store is None else store
    if not isinstance(got, runidentity.Store):
        return []
    return [(c.id, c.name, plate_array(c)) for c in got.characters]


def known_names() -> list[str]:
    return [name for _, name, _ in known_chars()]


def known_match(client: Img, chars: list[tuple[str, str, Any]]) -> dict[str, Any]:
    """PURE: the name plate against every known character's: the closest one, ok within MATCH."""
    if not chars:
        return {"ok": False, "why": "no character is remembered on this install: on the Settings "
                "page, press Remember with the character in front", "who": None,
                "name_diff": None, "known": []}  # fmt: skip
    plate = crop(client, NAME_BOX)
    d, name = min((differing(plate, ref), name) for _, name, ref in chars)
    ok = d <= MATCH
    return {"ok": ok, "why": None if ok else "name", "who": name if ok else None,
            "name_diff": d, "known": [n for _, n, _ in chars]}  # fmt: skip


def known_words(ok: bool, names: list[str]) -> str:
    """PURE: the identity line under "known"."""
    shown = ", ".join(names) or "none"
    if ok:
        return f"a character remembered on this install (its name line is one of: {shown})"
    if not names:
        return ("no character is remembered on this install: on the Settings page (Who may play a "
                "Run), press Remember with the character in front, or choose Any")  # fmt: skip
    return (f"the name line is none of the characters remembered here ({shown}): another "
            "server's character, or a window over it -- a Run plays only the ones remembered on "
            "the Settings page (Who may play a Run: known)")  # fmt: skip


def check(screen: Any, job: str, char: str = "crusader", *, db: bool = True) -> dict[str, Any]:
    """The three checks on a fresh frame (no input). ``db=False`` (dungeon@9.35c, --player-mode):
    a public server has no DB of ours, so the lab DB's "who is online" check is skipped and the
    identity rests on the pixels alone (the name plate and the job, against this char's refs).
    ➡️ 2026-11-18 (ADR-0020 Amendment Q): with ``db=False`` and the mode any (the default) no
    name or job is compared -- any character plays; only a black game region still fails. No
    reference pictures are needed (a learner's install has none).
    ➡️ 2026-11-19 (Amendment R): the mode and the known characters come from the Settings page's
    store (identity_store); an unreadable store fails the check in words."""
    import ro_agent as r

    store = runidentity.DEFAULT if db else identity_store()
    if isinstance(store, str):
        return {"ok": False, "why": unreadable_words(store)}
    mode = "mine" if db else store.mode
    if mode in ("any", "known") and r.black(screen):
        return {"ok": False, "why": "the game region is black"}
    if mode == "any":
        return {"ok": True, "why": None, "who": "any", "job": job, "name_diff": None,
                "job_diff": None}  # fmt: skip
    if mode == "known":
        return {**known_match(client_frame(screen), known_chars(store)), "job": job,
                "job_diff": None}  # fmt: skip
    try:
        name, name_ref, jobs = load_refs(char)
    except FileNotFoundError:
        if db:
            raise  # a GM line: the lab's own character, always (never a word in its place)
        return {"ok": False, "why": "this install has no reference pictures of its own character "
                "(mine is the lab's setting): on the Settings page choose Any, or Known and "
                "Remember"}  # fmt: skip
    if db:
        online = r.online_chars("gm")
        if online != [name]:
            return {"ok": False, "why": f"online on the GM account: {online} (want [{name!r}])"}
    if r.black(screen):
        return {"ok": False, "why": "the game region is black"}
    return identity(client_frame(screen), name_ref, jobs, job)


def plate_verdict(a: npt.NDArray[np.int16], b: npt.NDArray[np.int16]) -> str | None:
    """PURE: why two looks at the name line (PLATE_GAP_S apart) are no usable picture of it."""
    if differing(a, b) > MATCH:
        return ("the name line changed between two looks: open Basic Info at the top left of the "
                "game, with nothing moving over it")  # fmt: skip
    med = np.median(a.reshape(-1, 3), axis=0)
    if int((np.abs(a - med).max(axis=2) > DIFF_LEVEL).sum()) < BLANK_MIN_PX:
        return ("the name line is blank: open Basic Info at the top left of the game (the window "
                "with the character's name, level and job)")  # fmt: skip
    return None


def read_plate(screen: Any, store: runidentity.Store | str) -> dict[str, Any]:
    """The Settings page's Remember (Batt 2026-11-19): the name line of the character on screen,
    two looks apart, with the name of a remembered character it already matches (``same_as``).
    Reads pixels only; sends no input; keeps nothing (the backend stores what a person saved)."""
    import ro_agent as r

    away = r.away_now(screen)
    if away is not None:
        return {"ok": False, "why": f"the game is not on the screen ({away}): bring it to front"}
    if r.black(screen):
        return {"ok": False, "why": "the game region is black"}
    a = crop(client_frame(screen), NAME_BOX)
    time.sleep(PLATE_GAP_S)
    b = crop(client_frame(screen), NAME_BOX)
    why = plate_verdict(a, b)
    if why is not None:
        return {"ok": False, "why": why}
    chars = known_chars(store) if isinstance(store, runidentity.Store) else []
    same = [name for _, name, ref in chars if differing(b, ref) <= MATCH]
    h, w = b.shape[:2]
    rgb = base64.b64encode(b.astype(np.uint8).tobytes()).decode("ascii")
    return {"ok": True, "w": int(w), "h": int(h), "rgb": rgb, "same_as": same[0] if same else None}


def write_plate(out: Path, rid: str, got: dict[str, Any]) -> None:
    """The result for the Run helper (atomic: the backend never reads half a file)."""
    tmp = out.with_name(f".{out.name}.{rid}")
    tmp.write_text(json.dumps({"id": rid, **got}) + "\n")
    tmp.replace(out)


def gm_line(agent: Any, screen: Any, command: str, job: str,
            char: str = "crusader", on_refuse: str = "raise") -> dict[str, Any]:  # fmt: skip
    """One GM line, typed only after `check` passes; ro_agent.gm's path without its Novice-GM
    check (which would refuse here by design). ``on_refuse="skip"``: chat_guard's own option for
    an IDEMPOTENT GM command (@heal), whose repeat the client would drop anyway: a refusal is not
    typed and returns ``typed: False`` instead of stopping (2026-10-24: a frozen client had
    swallowed one @heal, so the pre-run's would have been the 3rd in a row)."""
    import chat_guard
    import ro_agent as r

    if not command.startswith("@"):
        raise r.Stop("GM commands start with @")
    got = check(screen, job, char)
    if not got["ok"]:
        raise r.Stop(f"{char}: identity check failed ({got}): {command!r} NOT sent")
    record = {"t_mono_ns": r.ns(), "t_wall": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
              "cmd": command, "char": char, "identity": got}  # fmt: skip
    r.STATE_DIR.mkdir(parents=True, exist_ok=True)
    with (r.STATE_DIR / "gm.jsonl").open("a") as fh:
        fh.write(json.dumps(record) + "\n")
    if on_refuse == "skip" and not chat_guard.before_typing(command, on_refuse="skip"):
        r.log(f"{char} gm: {command} NOT typed (chat_guard refused; idempotent: skipped)")
        return {**got, "typed": False}
    r.activate_client(agent, screen)
    try:
        if on_refuse == "skip":  # the guard passed it just above: type without a 2nd count
            r.open_chat(agent, screen)
            agent.type_text(command + "\n")
        else:
            r.chat_line(agent, screen, command)
    except chat_guard.ChatRefused as exc:
        raise r.Stop(f"{char}: {command!r} refused by chat_guard ({exc})") from None
    r.log(f"{char} gm: {command}")
    return {**got, "typed": True}


NO_DB_WARNING = (
    "WARNING: --no-db: the lab DB is not asked who is online. Make sure the character "
    "on screen is the one in char.json, logged in alone, before you trust this."
)


def init_char(d: Path, name: str, slot: int | None = None) -> dict[str, Any]:
    """A learner's own character (new-lab-host.md 11.1): write ``d/char.json`` with its name.
    Never over an existing file (a lab character's name and slot are kept); the references are
    cut after it (cut-name, cut-job), with --no-db on a server of someone else's."""
    f = d / "char.json"
    if not name.strip():
        raise SystemExit("init: --name is empty")
    if f.exists():
        raise SystemExit(f"init: {f} exists already: remove it yourself first if it is wrong")
    rec: dict[str, Any] = {"name": name, "made": time.strftime("%F")}
    if slot is not None:
        rec["slot"] = int(slot)
    d.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(rec) + "\n")
    return {"wrote": str(f), **{k: v for k, v in rec.items() if k != "name"}}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)  # fmt: skip
    ap.add_argument("--char", default="crusader", choices=sorted(CHARS))
    sub = ap.add_subparsers(dest="cmd", required=True)
    all_jobs = sorted({j for js in CHARS.values() for j in js})
    c = sub.add_parser("check")
    c.add_argument("--job", default="novice", choices=all_jobs)
    g = sub.add_parser("gm")
    g.add_argument("--job", required=True, choices=all_jobs)
    g.add_argument("line")
    k = sub.add_parser("cut-job")
    k.add_argument("job", choices=all_jobs)
    sub.add_parser("cut-name")
    # 2026-11-12 (new-lab-host.md 11.1, a learner's own character): the name file a server of
    # someone else's needs, and --no-db for its check and cuts (that server has no DB of ours)
    i = sub.add_parser("init", help="write data/<char>/char.json (never over an existing one)")
    i.add_argument(
        "--name", required=True, help="the character's name exactly as the client shows it"
    )
    i.add_argument("--slot", type=int, default=None, help="its slot at character select (optional)")
    # 2026-11-19 (ADR-0020 Amendment R): the Settings page's Remember, run by the Run helper only
    pl = sub.add_parser("plate", help="read the name line of the character on screen (no input)")
    pl.add_argument("--request", required=True, help="the request id the result carries")
    pl.add_argument("--out", required=True, type=Path, help="the result file (JSON)")
    for sp in (c, k, sub.choices["cut-name"]):
        sp.add_argument("--no-db", action="store_true",
                        help="a server with no DB of ours (ADR-0023's declared mode): skip the lab "
                        "DB's 'who is online' check; the identity rests on the pixels and on "
                        "YOUR word that this character is the one on screen")  # fmt: skip
    a = ap.parse_args()
    if getattr(a, "job", None) is not None and a.job not in CHARS[a.char]:
        ap.error(f"job {a.job!r} is not one of the {a.char}'s jobs {CHARS[a.char]}")
    d = data_dir(a.char)
    if a.cmd == "init":
        print(json.dumps(init_char(d, a.name, a.slot)))
        return 0
    import ro_agent as r

    if a.cmd == "plate":
        screen = r.Screen()
        try:
            got = read_plate(screen, identity_store())
        except Exception as e:  # noqa: BLE001 -- the page shows the words, never a traceback
            got = {"ok": False, "why": f"the name line could not be read ({type(e).__name__}: {e})"}
        finally:
            screen.close()
        write_plate(a.out, a.request, got)
        print(json.dumps({k: v for k, v in got.items() if k != "rgb"}))
        return 0 if got.get("ok") else 1
    no_db = bool(getattr(a, "no_db", False))
    if no_db:
        print(NO_DB_WARNING, flush=True)
    if a.cmd == "check":
        screen = r.Screen()
        try:
            print(json.dumps(check(screen, a.job, a.char, db=not no_db)))
        finally:
            screen.close()
        return 0
    if a.cmd in ("cut-job", "cut-name"):
        screen = r.Screen()
        try:
            name = json.loads((d / "char.json").read_text())["name"]
            if not no_db and r.online_chars("gm") != [name]:
                raise r.Stop(f"{a.cmd}: the DB does not say {a.char} {name!r} is the one online")
            frame = client_frame(screen)
            if a.cmd == "cut-name":
                np.save(d / "ref_name.npy", crop(frame, NAME_BOX))
                print(f"saved {a.char} ref_name.npy")
                return 0
            if differing(crop(frame, NAME_BOX), np.load(d / "ref_name.npy")) > MATCH:
                raise r.Stop(f"cut-job: the {a.char} is not the character on screen")
            np.save(d / f"ref_job_{a.job}.npy", crop(frame, JOB_BOX))
            print(f"saved {a.char} ref_job_{a.job}.npy")
        finally:
            screen.close()
        return 0
    with r.session(f"rule:{a.char}-gm") as (agent, screen):
        agent.wait_for_human()
        print(json.dumps(gm_line(agent, screen, a.line, a.job, a.char)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
