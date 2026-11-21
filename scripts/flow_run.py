#!/usr/bin/env python3
"""The /flows page's RUN button, the host side (Batt 2026-11-13: "I put the bot on the map, press
run on flows, and the bot plays by itself, with the flow that earns the most a round").

    flow_run.py serve        the helper loop (scripts/host/poring-lab-flowrun.service)
    flow_run.py status       print the status file
    flow_run.py command FLOW [--check]   print the exact runner command a FLOW runs (or checks)

WHAT IT RUNS: the proven runner (scripts/dungeon_hunt.py run), never a new executor. A flow is a
FIXED entry of FLOWS below: its whole command line lives here, in the repo. A request names a flow
by its id and says start, check or stop; nothing in a request becomes an argument, except the
flow's five hotbar keys (2026-11-13, Batt: every key from a FUNCTION of the flow): ``keys``, all
five of flow_config.KEY_FIELDS, each F1-F9, over the settings for THAT run or check only.

➡️ 2026-11-14 ~15:2x (Batt: "there should be no runner [page] ... make them ALL blocks";
docs/planning/live-blocks.md section 12): every SETTING is a block of the project
(poring_flow.settings), so a run takes the settings from the CHECKED PROJECT (the map node's blocks
> Global's > the default), never from a file: settings/flowrun/config.json and GET / PUT
/flows/config are gone (the file was empty). The runner-only Run (a start of the flow
"xmas_dun02_rogue" from the runner page) went with that page: a start is a PROJECT run (below), and
a check of "project" carries the settings the backend computed from the project's blocks
(``vals``, checked again here). FLOWS stays: the map's runner (its fixed part, its flags; its
``defaults`` derived from the settings' defaults) the live block player and the stage tools build
the hunt core's argv from.

THE CHANNEL: the backend writes ``settings/flowrun/request.json`` (POST /flows/run, behind
routes_settings.write_gate: a console browser on the LAN, never the lab host or the Windows host,
the CSRF token, rate-limited and audited) and reads ``status.json``, which this loop rewrites every
STATUS_EVERY_S (its heartbeat). ``settings/`` is the human-only store, mounted only into the backend
(CLAUDE.md, "The human-only settings store"); vision cannot write it.

A START runs, in order (as the night chain's run_pilot_v3.sh does):
1. refuse while another input writer of ours plays: another runner, the live block player, the
   night chain or an A/B series (one input writer at a time, ADR-0002; ``writer_busy``). Between
   runs the status says so too (matpilot round 17 N5): while the helper has no run of its own, it
   reads ``ps`` every STATUS_EVERY_S and is "busy" with those words (status.json ``busy``), so the
   page disables Run and the backend refuses a start or a check (input_writer_busy);
2. the vision worker up (``guarded_build.py worker:vision``) if it is not;
3. the detect server (``unit_detector.py serve-cmd``, its time box = the run's cap + 150 s), and
   its "listening" line;
4. the runner, in --player-mode (it types no line; it starts where the person left her, reads her
   stock from the hotbar, refuses a heavy bag or too little stock, ends when the Fly Wings fall to
   one and goes home on a Butterfly Wing if F8 holds one). Its two map EXITS (dungeon@9.41): a bag
   over 50 % ends the run and the Butterfly Wing takes her home; a death presses the death dialog's
   move to saved location. Its own checks refuse every unsafe start
   (ASSIST or BOT, the interlock, her identity, her cell).
A STOP sends SIGINT to the runner's process group (a clean end, rc 130). Either way the detect
server is ended by PID when the runner exits, and the run's session goes into data/econ/lab.sqlite.
A PROJECT RUN (Batt 2026-11-13 ~21:4x, docs/planning/live-blocks.md stage 1): POST
/flows/run/project writes the checked project (``project.json``, its hash in the request) and a
request {"action": "start", "flow": "project", "node", "project_hash", "max_s"}; the helper
checks the file's hash against the request's, copies it into the run's folder and starts the LIVE
BLOCK PLAYER (scripts/flow_play.py play) instead of the runner -- the same busy rules, ASSIST or
BOT (Batt 2026-11-18: "with BOT it must run too"; RUN_INPUT_MODES), the
detect server when a hunt core plays, the stop file, status.json (its flow id "project", titled
with the project's name). A check of the flow "project" is the runner's check (PROJECT_CHECK_FLOW)
with that project's keys and setting blocks.
A CHECK (dungeon@9.45, Batt 2026-11-13 "do it": /flows' start checklist ticked from the game screen)
runs ``dungeon_hunt.py check`` with the SAME argv a start would build (the project's settings and
keys the request carries, 2026-11-14): the runner's preamble, then the player start's checks READ
from the screen -- it sends no input. It is refused while a run starts or runs (the start's busy
rule), time-boxed (CHECK_TIMEOUT_S), and its result goes into status.json's "check"; a Run pressed
meanwhile ends it (its process group).
"""

from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import json
import math
import os
import re
import shutil
import signal
import subprocess
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import flow_config as fc  # the settings' registry (same directory: scripts/)
import host_profile  # this host's detect backend (ADR-0022; same directory, stdlib only)
import lab_env  # this copy's compose project names (same directory, stdlib only)

from poring_flow import ir  # the time box rule: 0 = no time limit (Batt 2026-11-19)

ROOT = Path(__file__).resolve().parents[1]
DIR = ROOT / "settings" / "flowrun"
# this copy's scratch (ADR-0026 Implementation 2026-11-19: two copies on one host, Batt): its
# Stop file, run folders and logs; the lab's /dev/shm/poring-lab-tmp
SCRATCH = lab_env.shm("tmp")
# Batt 2026-11-18 ("with BOT it must run too"; ADR-0020 Amendment 2026-11-18): a Run's input path
# (ro_agent.Agent, ro_agent.MODES_ENV) may send in ASSIST or BOT. In BOT the mux drops the person's
# input, so watching the Console never pauses the run; Stop, or HUMAN, ends it. Only the processes
# this helper starts get it: every other script of ours stays ASSIST-only.
RUN_MODES_ENV = "PORING_INPUT_MODES"
RUN_INPUT_MODES = "ASSIST,BOT"
RUN_PAUSE_ENV = "PORING_PAUSE_AWAY"  # ro_agent.AWAY_ENV: a Run waits while the game is off screen
RUN_CONFIRM_ENV = (
    "PORING_CONFIRM_READS"  # poring_env.selfpos.CONFIRM_READS_ENV: re-read before a run-ending read
)
# the run log's last lines in the status (the page's log; Batt 2026-11-18); 300 since 2026-11-19
# for the /flows Logs tab (Batt: "the bot stops by itself and I cannot see why")
LOG_TAIL_N = 300
LOG_LINE_MAX = 400
SERVE_LOG = SCRATCH / "poring-guarded-execdev-vision.log"
WORKER = lab_env.container("vision-worker")
PY = str(ROOT / ".venv" / "bin" / "python")
STATUS_EVERY_S = 2.0
POLL_S = 1.0
# round 29: how long a run's end waits for its economy record (econ_db.record_after_run) before the
# record goes on in the background -- under the backend's HELPER_FRESH_S (10 s), so the helper's
# status stays fresh and the page never reads "the Run helper has not answered"
ECON_WAIT_S = 5.0
LISTEN_WAIT_S = 120.0
CAP_GRACE_S = 300.0  # the helper's own cap beyond the runner's --minutes
VERSION = 1
CHECK_TIMEOUT_S = 20.0  # dungeon@9.45's check: uv + the runner's preamble + <= PLAYER_POS_S reads
CHECK_LABEL = "flowcheck"  # its --label (a check makes no session) and its scratch folder
CHECK_MARK = "CHECK "  # dungeon_hunt.CHECK_MARK: the check's result line (test_flow_run pins it)
# 2026-11-19 (ADR-0020 Amendment R): the Settings page's Remember -- the name line of the character
# on screen, read once by `crusader.py plate` (pixels only, no input) into PLATE_FILE, which the
# backend reads, stores on the person's word and deletes. Served even while a run plays (it only
# looks); one at a time; time-boxed.
PLATE_FILE = "plate.json"
PLATE_TIMEOUT_S = 15.0
PANELS_TIMEOUT_S = 8.0  # 4f: the check's find of the game's windows (ro_agent.py find-panels)

# The runner's fixed part, as the night chain ran it (docs/records/pilot-chain/run_pilot_v3.sh +
# pilot_rec2.sh's BASE) WITHOUT --clear-map (a GM line: --player-mode refuses it), --seed fixed.
FIXED = [
    "--char", "rogue", "--map", "xmas_dun02", "--strategy", "P2", "--seed", "20261105",
]  # fmt: skip
# ➡️ 2026-11-13 ~15:2x (Batt: "do all of them"): every technique of the night chain's base is a
# SWITCH now (scripts/flow_config.py), its default the base's own (the flow's ``defaults``); FIXED
# keeps only what flow_config.NOT_SETTINGS names: the character, the map, the strategy, the seed.


# A run with no time limit (Batt 2026-11-19) still gives the detect server's guarded step a time
# box (its command needs one): 10 years. The run's end stops the server itself (end_server).
NO_LIMIT_SERVE_S = 315_360_000


def serve_seconds(cap_s: float) -> str:
    """PURE: the detect server's time box: the run's cap + 150 s, or NO_LIMIT_SERVE_S."""
    return str(int(cap_s + 150) if math.isfinite(cap_s) else NO_LIMIT_SERVE_S)


@dataclass(frozen=True)
class Flow:
    id: str
    title: str
    minutes: int
    flags: tuple[str, ...]
    why: str = ""
    extra: dict[str, Any] = field(default_factory=dict)
    # 2026-11-13 (Batt: "nothing is fixed, we only put the defaults"; "a global config for every
    # map's flow, a map's own on top"): the map it plays (its config level) and the DEFAULTS of
    # every setting with a flag of its own (scripts/flow_config.py FIELDS); a runner number nobody
    # set keeps the runner's own value (no --tune)
    map: str = ""
    defaults: dict[str, Any] = field(default_factory=dict)


# rogue-xmas02.md 4DQ (2026-11-13): the Knife on arm B's fast loot JOINED THE BASE -- the highest
# common-item z/h with every bar passed (67,269); Batt chose it for the Run button, played until
# Stop or until the stock runs low, a 2-h cap.
FLOWS: dict[str, Flow] = {
    "xmas_dun02_rogue": Flow(
        "xmas_dun02_rogue",
        "xmas_dun02: the Rogue with Batt's Knife swap (the base of 4DQ), as a player",
        0,  # no time limit (Batt 2026-11-19, ADR-0020 Amendment T; was 120 min)
        ("--player-mode",),  # Batt: the Run button plays as a player (flow_config.NOT_SETTINGS)
        "rogue-xmas02.md 4DQ (the base) + --player-mode (Batt 2026-11-13: no GM lines) + the "
        "map's two exits (dungeon@9.41, Batt 2026-11-13): weight over 50 % -> the Butterfly Wing "
        "home; a death -> the death dialog's move to saved location",
        map="xmas_dun02",
        # Batt 2026-11-13: "the Butterfly Wing on F9, the Fly Wing on F8"; "nothing fixed, we only
        # put the defaults": each one a DEFAULT. ➡️ 2026-11-14 (live-blocks.md 12): DERIVED from
        # the settings' own defaults (poring_flow.settings.DEFAULTS: every setting but the runner
        # constants), set again as BLOCKS of a project (the map node's, Global's); test_flow_run
        # pins them to the dict this was before (the night chain's base 4DQ, P2's numbers)
        defaults=fc.flag_defaults(),
    ),
}


# THE PROJECT RUN (live-blocks.md stage 1): its flow id in requests and status.json, the files
PROJECT = "project"
PROJECT_FILE = "project.json"  # settings/flowrun/: the backend's checked project (canonical JSON)
PROJECT_CHECK_FLOW = "xmas_dun02_rogue"  # a check of "project" is this runner's read-only check
# the runner writes every copy's sessions in ONE folder (dungeon_hunt.DEMO, byte-pinned), named for
# the label: another copy's Runs carry its project name, so no copy reads another's session
PROJECT_LABEL = ("flowplay" if lab_env.project() == lab_env.PROJECT_DEFAULT
                 else f"flowplay-{lab_env.project()}")  # fmt: skip
NODE_ID = re.compile(r"[A-Za-z][A-Za-z0-9_]{0,39}")  # poring_flow.ir.NAME
HASH = re.compile(r"[0-9a-f]{64}")

STOP_NAME = "STOP"  # the runner's --stop-file, in the run's own scratch folder
STOP_GRACE_S = 90.0  # Stop: the runner ends at its next tick; SIGINT only if it has not by then


def command(flow: Flow, label: str, stop_file: Path | None = None,
            vals: Mapping[str, Any] | None = None, sub: str = "run") -> list[str]:  # fmt: skip
    """PURE: the runner's argv for ``flow`` (the label names its session; ``stop_file`` is the
    runner's --stop-file: its Stop ends the run through the normal end, with the packets;
    ``vals``: the run's values (a project's settings, the keys over them), else the flow's
    defaults; ``sub``: "run", or dungeon@9.45's
    read-only "check", which takes run's own flags)."""
    if sub not in ("run", "check"):
        raise ValueError(f"not a runner command: {sub!r}")
    stop = [] if stop_file is None else ["--stop-file", str(stop_file)]
    head = ["nice", "-n", "10", "uv", "run", "--quiet", "python", "scripts/dungeon_hunt.py", sub]
    v = dict(flow.defaults) if vals is None else dict(vals)
    why = fc.clash(v)
    if why:
        raise ValueError(why)
    return [*head, *FIXED, "--label", label, *stop, *flow.flags, *fc.argv(v)]


def play_command(project_file: Path, node: str, label: str, stop_file: Path, max_s: int,
                 project_hash: str, runner_config: Path | None = None) -> list[str]:  # fmt: skip
    """PURE (live-blocks.md stage 1): the live block player's argv for a project run."""
    rc = [] if runner_config is None else ["--runner-config", str(runner_config)]
    return ["nice", "-n", "10", "uv", "run", "--quiet", "python", "scripts/flow_play.py", "play",
            "--project", str(project_file), "--node", node, "--label", label, "--stop-file",
            str(stop_file), "--max-s", str(int(max_s)), "--project-hash", project_hash,
            *rc]  # fmt: skip


def values_of(vals: Mapping[str, Any], src: Mapping[str, str], keys: Mapping[str, str] | None,
              ) -> tuple[dict[str, Any], dict[str, str], str, str | None]:  # fmt: skip
    """PURE: a start's (and a check's) values: the settings, the flow's keys over them when
    given, then the clash rule -- (vals, src, keys_src, why)."""
    keys_src = fc.KEYS_SRC["flow" if keys else "config"]
    out, where = dict(vals), dict(src)
    if keys:
        out = fc.with_keys(out, keys)
        where = {**where, **{k: "flow" for k in fc.KEY_FIELDS}}
    clash = fc.clash(out)
    return out, where, keys_src, (f"refused before any input: {clash}" if clash else None)


def project_values(doc: Mapping[str, Any], node: str, keys: Mapping[str, str] | None,
                   ) -> tuple[dict[str, Any], dict[str, str], str, str | None]:  # fmt: skip
    """PURE (2026-11-14, live-blocks.md 12): the hunt core's values on ``node`` of a project (its
    JSON as a dict): the node's setting blocks > Global's > the defaults
    (poring_flow.settings.node_values), the flow's keys over them, the clash rule. A setting block
    whose value cannot be used refuses (the backend's lint refused it first)."""
    nv = fc.node_values(fc.doc_levels(doc, node))
    if nv.problems:
        keys_src = fc.KEYS_SRC["flow" if keys else "config"]
        return {}, {}, keys_src, f"refused before any input: a setting block: {nv.problems[0]}"
    return values_of(nv.vals, nv.src, keys)


def check_command(flow: Flow, vals: Mapping[str, Any] | None = None) -> list[str]:
    """PURE (dungeon@9.45): the read-only check's argv -- the start's, with "check" for "run" (no
    --stop-file: a check is time-boxed by the helper)."""
    return command(flow, CHECK_LABEL, None, vals, sub="check")


def parse_request(text: str) -> dict[str, Any] | str:
    """PURE: a valid request or why it is not one. A START is a project run ({"id", "action":
    "start", "flow": "project", "node", "project_hash", "max_s", "keys"?}: the checked project
    file decides everything). A CHECK of "project" carries the five keys and the settings the
    backend computed from the project's blocks ({"keys", "vals"}: 2026-11-14, live-blocks.md 12),
    each checked here again; it runs the runner's read-only check (PROJECT_CHECK_FLOW). A STOP
    names nothing else. The runner-only start (a flow of FLOWS) went with the runner page."""
    try:
        req = json.loads(text)
    except ValueError:
        return "unparsable request"
    if not isinstance(req, dict):
        return "unparsable request"
    rid, action, flow = req.get("id"), req.get("action"), req.get("flow")
    if not isinstance(rid, str) or not re.fullmatch(r"[A-Za-z0-9_-]{8,64}", rid):
        return "bad request id"
    if action not in ("start", "stop", "check", "plate"):
        return f"unknown action {action!r}"
    if action == "plate":  # the Settings page's Remember (Amendment R): it names nothing else
        if set(req) - {"id", "action", "at"}:
            return "a name-line read carries nothing else"
        return {"id": rid, "action": action}
    if action == "stop":
        if req.get("keys") is not None:
            return "keys go with start or check, not stop"
        return {"id": rid, "action": action, "flow": flow}
    if flow != PROJECT:  # 2026-11-14: a start or a check is a project's (the runner page is gone)
        return f"unknown flow {flow!r}: a start or a check is a project's (flow {PROJECT!r})"
    keys = req.get("keys")
    if action == "start":  # live-blocks.md stage 1: the live block player
        node, h, max_s = req.get("node"), req.get("project_hash"), req.get("max_s")
        if not isinstance(node, str) or not NODE_ID.fullmatch(node):
            return "a project run names its map node"
        if not isinstance(h, str) or not HASH.fullmatch(h):
            return "a project run carries the checked project's hash"
        # 0 = no maximum (Batt 2026-11-19, ADR-0020 Amendment T); the IR's sanity cap above
        bad = isinstance(max_s, bool) or not isinstance(max_s, int)
        if bad or not 0 <= max_s <= ir.MAX_RUNTIME_S:
            return "a project run carries the configured maximum run time"
        if set(req) - {"id", "action", "flow", "node", "project_hash", "max_s", "keys", "at"}:
            return "a project run carries nothing else"
        out_p: dict[str, Any] = {"id": rid, "action": action, "flow": flow, "node": node,
                                 "project_hash": h, "max_s": max_s}  # fmt: skip
        if keys is not None:  # shown only: the player reads the keys from the project itself
            why = fc.keys_problem(keys)
            if why is not None:
                return why
            out_p["keys"] = {k: keys[k] for k in fc.KEY_FIELDS}
        return out_p
    # a check of a project: the runner's read-only check with the project's keys and settings
    if set(req) - {"id", "action", "flow", "node", "keys", "vals", "at"}:
        return "a project check carries its node, keys and settings, nothing else"
    node = req.get("node")
    if not isinstance(node, str) or not NODE_ID.fullmatch(node):
        return "a project check names its map node"
    why = fc.keys_problem(keys)
    if why is not None:
        return why
    vals = fc.check_level(req.get("vals"))
    if isinstance(vals, str):
        return f"the check's settings: {vals}"
    if set(vals) != {f.name for f in fc.FIELDS if f.block}:
        return "the check's settings must name every setting block (and no hotbar key)"
    return {"id": rid, "action": action, "flow": flow, "node": node,
            "keys": {k: keys[k] for k in fc.KEY_FIELDS}, "vals": vals}  # fmt: skip


def identity_any(items: list[Any], mode: str = "any") -> list[Any]:
    """PURE (ADR-0020 Amendment Q): the runner's identity line names the lab's character in its
    words ("the name plate reads Thief8fce"); under RUN_IDENTITY=any crusader.check compared no
    name, under =known every character this install knows, so the words are replaced (a black
    game region still fails under any)."""
    import crusader as cr

    names = cr.known_names() if mode == "known" else []
    out = []
    for it in items:
        if isinstance(it, dict) and it.get("id") == "identity":
            if mode == "any" and it.get("ok") is not False:
                it = {**it, "ok": True, "words": cr.IDENTITY_ANY_WORDS, "value": "any character"}
            elif mode == "known":
                ok = it.get("ok") is True
                it = {**it, "words": cr.known_words(ok, names),
                      "value": "a known character" if ok else None}  # fmt: skip
        out.append(it)
    return out


# Batt 2026-11-19: "do not lock the bot over the hotbar: it is the user's own business ... without
# Fly Wings the bot dies; the user learns and improves -- or a user may use an item with a
# teleport skill" and "do not lock this". The start check's HOTBAR lines (the counts and what each
# role's key shows) WARN, they never refuse: the runner's words say "a person first", the line says
# the Run starts anyway (flow_play also lets the runner's own start pass them, and plays without
# the Knife swap when its slots do not read right).
HOTBAR_LINES = ("wings", "heals", "home", "knife", "dagger")
HOTBAR_WARN = ("a WARNING only: the Run starts anyway (what the hotbar holds is the player's own "
               "choice)")  # fmt: skip


# Batt 2026-11-19 ~11:5x (asked: another client's weight digits did not read): "an unreadable weight
# is a warning" -- the Run starts; the bag-full exit cannot work until the weight reads. A weight
# READ over the limit, or the line drawn red (>= 50 %), still refuses (flow_play checks the red).
WEIGHT_WARN = ("a WARNING only: the weight did not read (this client's digits), so the Run starts "
               "and its bag-full exit cannot work until it reads; a weight read over the limit, or "
               "the line drawn red, still refuses")  # fmt: skip


def weight_unread(it: Any) -> bool:
    """PURE: the check's weight line failed WITHOUT a weight read (unread, or red: the line's
    words are the same; flow_play tells red apart on a frame of its own)."""
    return (isinstance(it, dict) and it.get("id") == "weight" and it.get("ok") is False
            and it.get("value") in (None, ""))  # fmt: skip


def hotbar_warnings(items: list[Any]) -> list[Any]:
    """PURE: the hotbar lines never refuse; a failed one says it is a warning. An unread weight
    is a warning too (Batt 2026-11-19)."""
    out = []
    for it in items:
        if isinstance(it, dict) and it.get("id") in HOTBAR_LINES:
            it = {**it, "refuses": False}
            if it.get("ok") is False and HOTBAR_WARN not in str(it.get("words")):
                it["words"] = f"{it.get('words')} -- {HOTBAR_WARN}"
        elif weight_unread(it) and WEIGHT_WARN not in str(it.get("words")):
            it = {**it, "refuses": False, "words": f"{it.get('words')} -- {WEIGHT_WARN}"}
        out.append(it)
    return out


# Batt 2026-11-21 ~22:0x ("these need no warning: each class plays differently -- a swordsman may
# carry another potion; do not require the White Potion, warn only when the heal key was forgotten,
# else note that its item is what she heals with. F4-F5: no warning, just say the flow swaps weapons
# there so the user prepares them. Never hardcode F1-F9: the keys the flow's blocks set"): the
# heals line warns only on an EMPTY heal key; another item there is a NOTE (its count read). The
# Knife / dagger lines are NOTES on what the flow swaps, on ITS keys (the check's ``used``: the
# flow's functions). Their ok stays as read: knife_swap_off still plays without the swap when the
# set-up did not read right (an unknown weapon state could equip anything; Batt 2026-11-19).
SWAP_LINES = ("knife", "dagger")


def _lead_int(value: Any) -> int | None:
    m = re.match(r"\s*(\d+)", str(value or ""))
    return int(m.group(1)) if m else None


def _key_in(value: Any) -> str | None:
    m = re.search(r"\bon (\S+)$", str(value or ""))
    return m.group(1) if m else None


def heal_note(it: dict[str, Any], used: Mapping[str, Any]) -> dict[str, Any]:
    """PURE: the heals line by Batt's rule -- an empty key warns, any item there is a note."""
    if it.get("ok") is True:
        return it
    key = used.get("heal_key") or _key_in(it.get("value")) or "the heal key"
    n = _lead_int(it.get("value"))
    if n is not None and n > 0:
        return {**it, "ok": True, "info": True, "refuses": False,
                "words": f"{key} holds {n} of the item she drinks or eats to heal: any heal item "
                         "(the player's choice; each class carries its own)"}  # fmt: skip
    if n == 0 or "empty" in str(it.get("words")):
        return {**it, "ok": False, "refuses": False,
                "words": f"{key} is empty: put the item she heals with there (any heal item), "
                         "or she plays without healing"}  # fmt: skip
    return it  # the count did not read: the runner's own words


def swap_note(it: dict[str, Any], used: Mapping[str, Any]) -> dict[str, Any]:
    """PURE: a Knife / dagger line as a note on what the flow swaps, on its own keys."""
    k = used.get("knife_key") or "its idle-weapon key"
    d = used.get("dagger_key") or "its weapon key"
    what = (f"{k}: the idle weapon this flow swaps to" if it.get("id") == "knife"
            else f"{d}: the fighting weapon it swaps back (worn at the start)")  # fmt: skip
    words = f"this flow swaps weapons on {k} and {d}; {what}: put them there to use the swap"
    if it.get("ok") is False:
        words += " (this Run: they did not read as that set-up, so it plays without the swap)"
    return {**it, "info": True, "refuses": False, "words": words}


def hotbar_notes(items: list[Any], used: Mapping[str, Any]) -> list[Any]:
    """PURE: hotbar_warnings' lines with Batt's notes (heal_note, swap_note)."""
    out = []
    for it in items:
        if isinstance(it, dict) and it.get("id") == "heals":
            it = heal_note(it, used)
        elif isinstance(it, dict) and it.get("id") in SWAP_LINES:
            it = swap_note(it, used)
        out.append(it)
    return out


def parse_check_output(text: str, identity: str | None = None) -> dict[str, Any]:
    """PURE (dungeon@9.45): the check's log as its result -- its CHECK line (the items, ok,
    refuses, the values it used), else the runner's refusal (a preamble refusal: no line read).
    ``identity`` "any": the identity line in RUN_IDENTITY=any's words (identity_any)."""
    for ln in reversed(text.splitlines()):
        if ln.startswith(CHECK_MARK):
            try:
                got = json.loads(ln[len(CHECK_MARK) :])
            except ValueError:
                break
            if not isinstance(got, dict) or not isinstance(got.get("items"), list):
                break
            if identity in ("any", "known"):
                got["items"] = identity_any(got["items"], identity)
            got["items"] = hotbar_notes(hotbar_warnings(got["items"]), got.get("used") or {})
            got["refuses"] = any(isinstance(i, dict) and i.get("ok") is False
                                 and i.get("refuses", True) for i in got["items"])  # fmt: skip
            fails = [i for i in got["items"] if isinstance(i, dict) and i.get("ok") is False
                     and not i.get("info")]  # fmt: skip
            unread = [i for i in got["items"] if isinstance(i, dict) and i.get("ok") is None
                      and not i.get("info")]  # fmt: skip
            n = len(got["items"])
            detail = (f"{len(fails)} of {n} lines fail" if fails else
                      f"{len(unread)} of {n} lines not read" if unread else
                      "every line passes")  # fmt: skip
            return {"state": "done", "items": got["items"], "ok": got.get("ok"),
                    "refuses": bool(got.get("refuses")), "used": got.get("used") or {},
                    "detail": detail}  # fmt: skip
    lines = [ln.strip() for ln in player_lines(text.splitlines()) if ln.strip()]
    why = next((ln for ln in reversed(lines) if "refused" in ln), lines[-1] if lines else "")
    refused = "refused" in why  # the runner's preamble refused: its start would refuse the same
    return {"state": "refused" if refused else "failed", "items": [],
            "ok": False if refused else None, "refuses": refused, "used": {},
            "detail": why[:300] or "the check ended without a result"}  # fmt: skip


DEMO = Path("/dev/shm/poring-lab-demo")  # dungeon_hunt.DEMO: each run's session folder


def run_started(label: str | None, demo: Path = DEMO) -> bool:
    """The runner passed its start checks: its session (named after the run's label) has the
    run_start event. A session folder or a line it cannot read: not yet."""
    if not label:
        return False
    for d in demo.glob(f"*-{label}"):
        try:
            with open(d / "events.jsonl", "rb") as fh:
                head = fh.read(200_000)
        except OSError:
            continue
        if b'"kind": "run_start"' in head:
            return True
    return False


# --- LIVE (matpilot's player test 2026-11-13: "while she really plays, the page tells me nothing";
# "the end is written for a developer"): the run's own session events, read as they grow, give
# the page one live line (HP, what she does, kills, loot, Knife swaps, time) and the block to
# highlight, then the end in plain words. Display only: nothing here decides anything.
EVENT_BLOCK = {"walk": "walk_click", "strike": "strike", "kill": "kill", "loot_step": "loot",
               "loot_click": "loot", "engage": "fight_on", "fight_end": "fight_over",
               "box_target": "choose", "explore": "explore", "goal": "explore", "unlock": "unlock",
               "scan": "ring_scan", "player_home": "home"}  # fmt: skip
PRESS_BLOCK = {"opener": "press_knife", "equip": "press_dagger", "potion": "drink",
               "fly": "wing_hp_fly", "home": "home"}  # fmt: skip
DOING = {"walk": "walking", "strike": "striking", "kill": "a kill", "loot_step": "looting",
         "loot_click": "picking up", "engage": "a fight starts", "fight_end": "the fight is over",
         "box_target": "aiming", "explore": "exploring", "goal": "exploring",
         "unlock": "letting go",
         "scan": "scanning around her", "player_home": "flying home"}  # fmt: skip
# 2026-11-20 (roles-not-names.md: "make it WEAPON, so other classes can use it"): the swap's roles
PRESS_DOING = {"opener": "the idle weapon on", "equip": "the fighting weapon back on",
               "potion": "a potion",
               "fly": "a Fly Wing", "home": "the Butterfly Wing home"}  # fmt: skip
# the live block player's blocks (its "block" events' "what") in a player's words
PLAYER_DOING = {"press_key": "pressing a key", "wait": "waiting", "wait_until": "waiting",
                "dungeon_hunt": "hunting", "take_exit": "taking an exit", "call": "a function",
                "while": "a loop", "repeat": "a loop", "for": "a loop", "if": "deciding",
                "stop": "stopping", "assert_save_point": "the save point"}  # fmt: skip


# The /flows Logs tab's "what she does" (Batt 2026-11-19: "what it thinks, what it will do, is it
# attacking a monster"): the last STORY_N session events in a person's words, newest last
STORY_N = 80
WALK_WHY = {"search": "searching for monsters", "explore": "exploring", "loot": "to the loot",
            "approach": "closing in on a monster", "home": "on the way home",
            "escape": "getting away", "patrol": "on the patrol route"}  # fmt: skip
STRIKE_END = {"damage": "a hit", "arrow": "she walks to it", "walked": "she walked to it",
              "escape": "it got away", "bound": "no answer in time"}  # fmt: skip
HP_STEP = 10  # an HP line when it moves this many points from the last one said


def unit_words(seen: Any) -> str | None:
    """PURE (Batt 2026-11-20: "the monster's name and %, and the cell, as in the HUD"): the HUD's
    own label of a seen box -- the model's class name, its confidence, its distance in cells --
    e.g. "cookie_xmas 87% 3 cells" (services/frontend/src/lib/hud.ts unitLabel); None: no box."""
    if not isinstance(seen, Mapping) or not seen.get("name"):
        return None
    out = str(seen["name"])[:32]
    conf = seen.get("conf")
    if isinstance(conf, (int, float)) and not isinstance(conf, bool):
        out += f" {round(float(conf) * 100)}%"
    cells = seen.get("cells")
    if isinstance(cells, int) and not isinstance(cells, bool):
        out += " 1 cell" if cells == 1 else f" {cells} cells"
    return out


def _cell(v: Any) -> str:
    try:
        return f"({int(v[0])}, {int(v[1])})"
    except (TypeError, ValueError, IndexError):
        return "?"


def event_words(e: Mapping[str, Any]) -> str | None:
    """PURE: one session event in a person's words, or None (not worth a line). Display only."""
    k = e.get("kind")
    if k == "walk":
        why = str(e.get("why") or "")
        sent = "" if e.get("clicked", True) else " (the click was not sent)"
        return f"walks to {_cell(e.get('to'))}{', ' + WALK_WHY.get(why, why) if why else ''}{sent}"
    if k == "goal":
        return f"heads for {_cell(e.get('to'))}, {e.get('len', '?')} cells of path"
    if k == "explore":
        near = f" (near {_cell(e['anchor'])})" if e.get("anchor") else ""
        return f"chooses where to explore next{near}"
    if k == "box_target":
        if e.get("box"):
            unit = unit_words(e.get("seen"))
            return f"aims at {unit}" if unit else "aims at a monster on the screen"
        return "looks for a monster in reach: none chosen"
    if k == "recipe":
        how = "the Knife swap first" if e.get("knife") else "plain strikes"
        return f"a {e.get('species') or 'monster'}: {how}"
    if k == "engage":
        unit = unit_words(e.get("seen"))
        at = f" at {_cell(e['spot'])}" if e.get("spot") else ""
        return f"a fight starts ({e.get('by') or '?'}){': ' + unit if unit else ''}{at}"
    if k == "strike":
        of = f" {str(e['of'])[:32]}" if e.get("of") else ""
        return f"strikes{of}: {STRIKE_END.get(str(e.get('end')), str(e.get('end') or '?'))}"
    if k == "kill":
        of = f": {str(e['of'])[:32]}" if e.get("of") else ""
        return f"a kill{of} ({e.get('by') or '?'})"
    if k == "unlock":
        return f"lets go of the target ({e.get('why') or '?'})"
    if k == "fight_end":
        return f"the fight is over: {e.get('kills', 0)} kill(s)"
    if k == "loot_step":
        return f"loot: {e.get('picks', 0)} picked ({e.get('end') or 'done'})"
    if k == "loot_click":
        return "picks up an item"
    if k == "press":
        what = str(e.get("what") or "")
        return f"presses {e.get('key') or '?'}: {PRESS_DOING.get(what, what)}"
    if k == "scan":
        return f"looks around her ({e.get('purpose') or 'scan'})"
    if k == "player_home":
        if e.get("pressed"):
            return f"flies home ({e.get('key') or '?'})"
        return f"cannot fly home: {e.get('why') or '?'}"
    if k == "hunt_start":
        return "the hunt core starts"
    if k == "hunt_end":
        return f"the hunt core ends: {e.get('error') or e.get('reason') or '?'}"
    if k == "retry":
        return f"RETRY {e.get('n')} of {e.get('of')} after a code error: {e.get('error') or '?'}"
    if k == "retry_go":
        return "she is ready again: the hunt core starts again"
    if k == "retry_refused":
        return f"not ready for a retry: {e.get('why') or '?'}"
    if k == "pause":
        return "PAUSED: the game is not on the screen"
    if k == "resume":
        return "back on the screen: playing on"
    if k == "event":
        # Batt 2026-11-21: the reading and the rule the Run plays (a box edited after its Start
        # keeps the rule it started with: a Run plays its checked project)
        rd = e.get("reading")
        said = ", ".join(f"{n} {v}" for n, v in rd.items()) if isinstance(rd, dict) else ""
        rule = f" (its rule: {str(e['when'])[:120]})" if e.get("when") else ""
        return (
            f"the box's function {e.get('event') or '?'} fires{': ' + said if said else ''}{rule}"
        )
    if k == "run_end":
        return f"the run ends: {e.get('words') or e.get('reason') or '?'}"
    return None


class StoryKeeper:
    """Batt 2026-11-21: a Run's "What she does" kept as history (poring_env.runlog), when the
    Settings page records the Runs: story.jsonl (to analyse) and story.log (to read) in its own
    folder under the chosen one; the total size kept under the cap, the OLDEST Run deleted first.
    A write that fails stops the keeping (said in ``problem``), never the Run."""

    def __init__(self, settings_dir: Path, root: Path, run_id: str, start: dt.datetime) -> None:
        from poring_env import runlog as rl

        self.rl, self.dir, self.problem, self.lines, self.deleted = rl, None, None, 0, []
        self._files: list[Any] = []
        self.store = rl.DEFAULT
        try:
            text = (settings_dir / rl.FILE_NAME).read_text(encoding="utf-8")
        except FileNotFoundError:
            return  # the default: not recorded
        except (OSError, UnicodeDecodeError) as e:
            self.problem = f"{rl.FILE_NAME} cannot be read ({type(e).__name__}): not recorded"
            return
        got = rl.parse(text)
        if isinstance(got, str):
            self.problem = f"{rl.FILE_NAME}: {got}: not recorded"
            return
        self.store = got
        if not got.record:
            return
        base = Path(got.folder) if Path(got.folder).is_absolute() else root / got.folder
        self.base = base
        try:
            d = base / rl.run_dir_name(start, run_id)
            d.mkdir(parents=True, exist_ok=False)
            self._files = [
                open(d / rl.STORY_JSONL, "a", encoding="utf-8"),  # noqa: SIM115
                open(d / rl.STORY_TEXT, "a", encoding="utf-8"),  # noqa: SIM115
            ]  # the Run's own files: open while it plays, closed at its end (close())
            self.dir = d
        except OSError as e:
            self.problem = f"the Run log folder {base}: {type(e).__name__}: not recorded"
            self.close()
            return
        self.retain()

    @property
    def recording(self) -> bool:
        return self.dir is not None and bool(self._files)

    def write(self, line: dict[str, Any]) -> None:
        if not self.recording:
            return
        try:
            rec = self.rl.story_record(line, line.get("at_iso"))
            self._files[0].write(json.dumps(rec, ensure_ascii=False) + "\n")
            self._files[1].write(self.rl.story_text(line) + "\n")
            for f in self._files:
                f.flush()
            self.lines += 1
        except OSError as e:
            self.problem = f"the Run log stopped ({type(e).__name__}) after {self.lines} lines"
            self.close()

    def retain(self) -> None:
        """Delete the OLDEST Run folders while the total is over the cap (never this Run's)."""
        if self.dir is None:
            return
        try:
            entries = []
            for p in self.base.iterdir():
                if p.is_dir() and self.rl.RUN_DIR_RE.fullmatch(p.name):
                    entries.append((p.name, sum(f.stat().st_size for f in p.iterdir()
                                                if f.is_file())))  # fmt: skip
            cap = self.store.max_total_mb * 1024 * 1024
            for name in self.rl.plan_deletes(entries, cap, keep=(self.dir.name,)):
                shutil.rmtree(self.base / name)
                self.deleted.append(name)
        except OSError as e:
            self.problem = f"the Run log's retention: {type(e).__name__}"

    def close(self) -> None:
        for f in self._files:
            with contextlib.suppress(OSError):
                f.close()
        self._files = []

    def summary(self) -> dict[str, Any]:
        return {"recording": self.dir is not None,
                "dir": None if self.dir is None else str(self.dir), "lines": self.lines,
                "problem": self.problem, "deleted": list(self.deleted),
                "max_total_mb": self.store.max_total_mb}  # fmt: skip


def wall_minus_mono() -> float:
    """The wall clock minus CLOCK_MONOTONIC now, in seconds (the story's clock times)."""
    return time.time() - time.monotonic()


def server_tz() -> str:
    """This server's time zone as a person reads it, e.g. "UTC+07:00" (the process's zone: TZ, else
    /etc/localtime)."""
    off = dt.datetime.now().astimezone().utcoffset() or dt.timedelta(0)
    m = int(off.total_seconds() // 60)
    return f"UTC{'+' if m >= 0 else '-'}{abs(m) // 60:02d}:{abs(m) % 60:02d}"


def sight_mobs(v: Any) -> list[list[Any]] | None:
    """PURE (Batt 2026-11-21, the live map): a record's monster cells as [x, y, name] (at most
    SIGHT_MAX_MOBS; a malformed one is left out), or None when the record carries none."""
    if not isinstance(v, list):
        return None
    out: list[list[Any]] = []
    for m in v[:SIGHT_MAX_MOBS]:
        try:
            out.append([int(m[0]), int(m[1]), str(m[2])[:32] if len(m) > 2 else "monster"])
        except (TypeError, ValueError, IndexError):
            continue
    return out


TRAIL_N = 240  # the live map: her last cells (one a change)
SIGHT_MAX_MOBS = 24  # the live map: monster cells a record may carry


@dataclass
class Live:
    """PURE: the live summary of one run's session events (fed line by line)."""

    t0_ns: int | None = None
    t_ns: int | None = None
    hp: int | None = None
    pos: list[int] | None = None
    doing: str = "starting"
    block: str | None = None
    kills: int = 0
    loot_steps: int = 0
    pickups: int = 0
    knife: int = 0
    steals: int = 0
    potions: int = 0
    flies: int = 0
    hp_low: int | None = None
    end: dict[str, Any] = field(default_factory=dict)
    # the live block player's own events (scripts/flow_play.py; live-blocks.md stage 1)
    node: str | None = None  # the project's node path "<node>/<tab>/<site>" of the block running
    keys: int = 0  # hotbar keys it pressed
    fired: int = 0  # events (functions with a trigger) that fired
    last_event: str | None = None
    retries: int = 0  # code-error retries (Batt 2026-11-19)
    story: list[dict[str, Any]] = field(default_factory=list)  # the Logs tab (STORY_N)
    # Batt 2026-11-20 ("the time: the Run's time, or the real time -- the server's, by its time
    # zone"): the wall clock minus the monotonic one (s), given once by the helper (the run's
    # events carry the shared CLOCK_MONOTONIC); each story line then also carries its clock time
    # in the server's time zone ("at"), and the summary names the zone ("tz")
    wall_minus_mono_s: float | None = None
    _hp_said: int | None = None
    # Batt 2026-11-21 (the Run log, poring_env.runlog): every story line is ALSO given here, with
    # its full clock time (ISO, the server's zone), when the Settings page records the Runs
    sink: Callable[[dict[str, Any]], None] | None = field(default=None, repr=False, compare=False)
    # Batt 2026-11-21 (the live map on /flows: "her as a green dot, the monsters she sees as red
    # dots"): the map she is on (the player's read), her last cells, and the monsters of the last
    # once-a-second record (flow_play.Sight: the detector's boxes placed from her cell); None: no
    # record carried any (an older player, or no hunt core playing)
    map: str | None = None
    trail: list[list[int]] = field(default_factory=list)
    mobs: list[list[Any]] | None = None
    mobs_t_ns: int | None = None
    # Batt 2026-11-21 ("add SP, the weight as a %, and the zeny: other jobs need them, a mage,
    # a merchant whose skill costs zeny"): SP from every HP read (sp_pct), the bag's weight from
    # the runner's weight events (its UI watch: every 10 s outside a fight, an event on a change),
    # the zeny from the player's read of the same Basic Info line (flow_play.Purse); None: not read
    sp: int | None = None
    sp_low: int | None = None
    weight: float | None = None  # the share, 0..1
    weight_red: bool = False  # the client draws the line red (>= 50 %: no natural regen)
    weight_nm: list[int] | None = None  # Batt 2026-11-21: the bag's N / M as the runner read it
    zeny: int | None = None
    zeny_start: int | None = None

    def clock_at(self, t: Any) -> str | None:
        """The event's clock time, "HH:MM:SS", in this server's time zone (None: no clock)."""
        if self.wall_minus_mono_s is None or not isinstance(t, int):
            return None
        return dt.datetime.fromtimestamp(t / 1e9 + self.wall_minus_mono_s).astimezone().strftime(
            "%H:%M:%S")  # fmt: skip

    def _tell(self, t: Any, words: str) -> None:
        el = None if self.t0_ns is None or not isinstance(t, int) else round((t - self.t0_ns) / 1e9)
        line: dict[str, Any] = {"t_s": el, "words": words[:240]}
        if (at := self.clock_at(t)) is not None:
            line["at"] = at
        self.story.append(line)
        del self.story[:-STORY_N]
        if self.sink is not None:
            iso = None
            if self.wall_minus_mono_s is not None and isinstance(t, int):
                iso = dt.datetime.fromtimestamp(t / 1e9 + self.wall_minus_mono_s).astimezone(
                ).isoformat(timespec="milliseconds")  # fmt: skip
            self.sink({**line, "at_iso": iso})

    def feed(self, e: Mapping[str, Any]) -> None:
        k, t = e.get("kind"), e.get("t_ns")
        if isinstance(t, int):
            self.t_ns = t
        if k == "run_start" and isinstance(t, int) and self.t0_ns is None:
            self.t0_ns = t
        words = event_words(e)
        if words is not None:
            self._tell(t, words)
        if k == "hp_read" and isinstance(e.get("pct"), int):
            pct = int(e["pct"])
            if self._hp_said is None or abs(pct - self._hp_said) >= HP_STEP:
                self._hp_said = pct
                self._tell(t, f"HP {pct} %")
        if k == "retry":
            self.retries += 1
            self.doing = f"RETRY {e.get('n')} of {e.get('of')}: waiting, then checking her"
            return
        if k == "block":  # the player: each block entered, with its node path
            self.node = str(e.get("node") or "") or None
            w = str(e.get("what") or "")
            self.doing = PLAYER_DOING.get(w, w.replace("_", " ") or self.doing)
            self.block = None
            return
        if k == "key":
            self.keys += 1
            return
        if k == "event":
            self.fired += 1
            self.last_event = str(e.get("event") or "") or None
            return
        if k in ("hunt_start",):
            self.doing, self.block = "the hunt core starts", None
            return
        if k == "hunt_end":  # no detector plays now: the map shows no monster
            self.mobs = self.mobs_t_ns = None
        if k == "pause":  # ro_agent.away_gate: the game off the screen (flow_play's PauseNotes)
            self.doing, self.block = "PAUSED: the game is not on the screen", None
            return
        if k == "resume":
            self.doing = "back on the screen: playing on"
            return
        if k == "run_start" and isinstance(t, int):
            self.t0_ns = t
        elif k == "hp_read":
            if isinstance(e.get("pct"), int):
                self.hp = e["pct"]
                self.hp_low = self.hp if self.hp_low is None else min(self.hp_low, self.hp)
            sp = e.get("sp_pct")
            if isinstance(sp, int) and not isinstance(sp, bool):
                self.sp = sp
                self.sp_low = sp if self.sp_low is None else min(self.sp_low, sp)
            nm = e.get("weight_nm")
            if (isinstance(nm, list) and len(nm) == 2
                    and all(isinstance(x, int) and not isinstance(x, bool) for x in nm)
                    and nm[0] >= 0 and nm[1] > 0):  # fmt: skip
                self.weight_nm = [nm[0], nm[1]]
                # Batt 2026-11-21 22:5x ("why does the weight show so late: 2 minutes, still
                # nothing"): the runner's weight EVENT comes only on a change of >= 0.5 % from its
                # start read, so a light-loot start showed "not read" for minutes; every read
                # (N / M, each UI watch) sets the share itself
                self.weight = nm[0] / nm[1]
            z = e.get("zeny")
            if isinstance(z, int) and not isinstance(z, bool) and z >= 0:
                self.zeny = z
                self.zeny_start = z if self.zeny_start is None else self.zeny_start
            if isinstance(e.get("map"), str) and e["map"] and e["map"][:40] != self.map:
                self.map, self.pos, self.mobs = e["map"][:40], None, None
                self.trail.clear()  # another map: her cells there are another picture
            if isinstance(e.get("pos"), list):
                with contextlib.suppress(TypeError, ValueError):
                    self.pos = [int(x) for x in e["pos"][:2]]
                    if not self.trail or self.trail[-1] != self.pos:
                        self.trail.append(self.pos)
                        del self.trail[:-TRAIL_N]
            if "mobs" in e:
                self.mobs, self.mobs_t_ns = (
                    sight_mobs(e.get("mobs")),
                    t if isinstance(t, int) else None,
                )
            return  # a look every tick: what she does stays the last action
        elif k == "weight":  # the runner's UI watch (mirrored by the player)
            sh = e.get("share")
            if isinstance(sh, (int, float)) and not isinstance(sh, bool) and 0 <= sh <= 2:
                self.weight = float(sh)
            self.weight_red = bool(e.get("red"))
            return
        elif k == "press":
            w = str(e.get("what"))
            self.knife += w == "opener"
            self.steals += w == "equip" and e.get("why") == "popup"
            self.potions += w == "potion"
            self.flies += w == "fly"
            if w in PRESS_BLOCK:
                self.doing, self.block = PRESS_DOING[w], PRESS_BLOCK[w]
            return
        elif k == "run_end":
            self.end["reason"] = str(e.get("reason") or "")
            if e.get("words"):  # the live block player's end in a player's words
                self.end["words"] = str(e["words"])
        elif k == "player_end":
            for x in ("home", "dead", "respawned"):
                self.end[x] = bool(e.get(x))
        self.kills += k == "kill"
        self.loot_steps += k == "loot_step"
        self.pickups += k == "loot_click"
        if k in EVENT_BLOCK:
            self.doing, self.block = DOING[k], EVENT_BLOCK[k]

    def summary(self) -> dict[str, Any]:
        t0, t1 = self.t0_ns, self.t_ns
        el = None if t0 is None or t1 is None else round((t1 - t0) / 1e9)
        return {"hp": self.hp, "hp_low": self.hp_low, "pos": self.pos, "doing": self.doing,
                "block": self.block, "elapsed_s": el, "kills": self.kills,
                "loot_steps": self.loot_steps, "pickups": self.pickups, "knife": self.knife,
                "steals": self.steals, "potions": self.potions, "flies": self.flies,
                "node": self.node, "keys": self.keys, "fired": self.fired,
                "last_event": self.last_event, "end": dict(self.end),
                "retries": self.retries, "story": list(self.story),
                "tz": server_tz(), "map": self.map, "trail": [list(c) for c in self.trail],
                "mobs": None if self.mobs is None else [list(m) for m in self.mobs],
                "mobs_age_s": self.mobs_age_s(), "sp": self.sp, "sp_low": self.sp_low,
                "weight": None if self.weight is None else round(self.weight * 100, 1),
                "weight_red": self.weight_red, "weight_nm": self.weight_nm, "zeny": self.zeny,
                "zeny_start": self.zeny_start}  # fmt: skip

    def mobs_age_s(self) -> float | None:
        """How old the monsters' record is (s), by the newest event's time."""
        if self.mobs_t_ns is None or self.t_ns is None:
            return None
        return round(max(0, self.t_ns - self.mobs_t_ns) / 1e9, 1)


def session_of(label: str | None, demo: Path) -> Path | None:
    """The run's session folder (named after its label), or None."""
    hits = sorted(demo.glob(f"*-{label}")) if label else []
    return hits[-1] if hits else None


def feed_new(live: Live, path: Path, offset: int) -> int:
    """Feed the complete lines written since ``offset``; returns the new offset."""
    try:
        with open(path, "rb") as fh:
            fh.seek(offset)
            data = fh.read(4_000_000)
    except OSError:
        return offset
    end = data.rfind(b"\n")
    if end < 0:
        return offset
    for ln in data[: end + 1].splitlines():
        try:
            e = json.loads(ln)
        except ValueError:
            continue
        if isinstance(e, dict):
            live.feed(e)
    return offset + end + 1


KEYS_SRC_PROJECT = "the project's functions"


def read_project(path: Path, want_hash: str) -> tuple[dict[str, Any] | None, str | None]:
    """The checked project file and why it cannot run (None: it can): it must be there, parse,
    and its canonical JSON's sha256 must be the request's (the file the backend checked)."""
    import hashlib

    try:
        raw = path.read_bytes()
    except OSError:
        return None, "refused before any input: the checked project file is not there"
    if len(raw) > 2 << 20:
        return None, "refused before any input: the project file is too large"
    if hashlib.sha256(raw).hexdigest() != want_hash:
        return None, "refused before any input: the project file is not the one checked"
    try:
        doc = json.loads(raw)
    except ValueError:
        return None, "refused before any input: the project file does not parse"
    if not isinstance(doc, dict):
        return None, "refused before any input: the project file is not a project"
    return doc, None


def _nodes(doc: Mapping[str, Any]) -> list[dict[str, Any]]:
    nodes = doc.get("nodes")
    return [n for n in nodes if isinstance(n, dict)] if isinstance(nodes, list) else []


def node_map(doc: Mapping[str, Any], node: str) -> str:
    n = next((x for x in _nodes(doc) if x.get("id") == node), None)
    m = n.get("map") if n is not None else None
    return str(m.get("map") or "") if isinstance(m, dict) else ""


def project_node_problem(doc: Mapping[str, Any], node: str) -> str | None:
    n = next((x for x in _nodes(doc) if x.get("id") == node), None)
    if n is None or n.get("kind") != "map":
        return f"refused before any input: {node} is no map node of the project"
    return None


def has_hunt_core(doc: Any) -> bool:
    """PURE: the project holds a dungeon_hunt action anywhere, or (live-blocks 5c, 15.2) a map
    node's main starts its hunt core with hunt_loop() (the detect server is started)."""
    if isinstance(doc, dict):
        if doc.get("kind") == "action" and doc.get("block") == "dungeon_hunt":
            return True
        if doc.get("kind") == "map" and any(
            isinstance(st, dict) and st.get("kind") == "call" and st.get("proc") == "hunt_loop"
            for t in doc.get("tabs") or [] for st in (t.get("main") or [])):  # fmt: skip
            return True
        return any(has_hunt_core(v) for v in doc.values())
    if isinstance(doc, list):
        return any(has_hunt_core(v) for v in doc)
    return False


def old_runner_problem(doc: Any) -> str | None:
    """PURE (round 29, live-blocks.md 17 #2): why a project is no REAL run -- a map node whose hunt
    core is the old one-block runner block (a dungeon_hunt action in its tabs; a lowered
    hunt_loop() is never in the file). The engine's words (poring_flow.project OLD_RUNNER_WORDS).
    The stage A/B tools play their reference arms through flow_play directly, never here."""
    from poring_flow.project import OLD_RUNNER_WORDS

    def holds(x: Any) -> bool:
        if isinstance(x, dict):
            if x.get("kind") == "action" and x.get("block") == "dungeon_hunt":
                return True
            return any(holds(v) for v in x.values())
        return isinstance(x, list) and any(holds(v) for v in x)

    if any(n.get("kind") == "map" and holds(n.get("tabs")) for n in _nodes(doc)):
        return f"refused before any input: {OLD_RUNNER_WORDS}"
    return None


def player_lines(lines: Sequence[str]) -> list[str]:
    """PURE: the log lines a person reads (matpilot: a server path and a raw JSON line cut off
    mid-word are a developer's): none starting with "{" or "/"."""
    return [ln for ln in lines if not ln.lstrip().startswith(("{", "/"))]


def end_words(live: Live, stopped: bool, rc: int | None) -> str:
    """The end in a player's words (matpilot: "did she get home? any deaths? what did she do?")."""
    s = live.summary()
    mins = (s["elapsed_s"] or 0) // 60
    how = "Stopped by you" if stopped else ("Ended by itself" if rc == 0 else "Ended")
    e = s["end"]
    where = ("She respawned at the save point." if e.get("respawned") else
             "She died there." if e.get("dead") else
             "She flew home on a Butterfly Wing." if e.get("home") else
             "She stayed on the map.")  # fmt: skip
    did = (f"{s['kills']} kills, {s['loot_steps']} loot steps ({s['pickups']} pickups), "
           f"{s['knife']} Knife swaps ({s['steals']} steals), {s['potions']} potions, "
           f"{s['flies']} Fly Wings; lowest HP {s['hp_low']} %.")  # fmt: skip
    return f"{how} after {mins} min. {where} {did}"


def copy_ps_lines(root: Path = ROOT, ps: str | None = None,
                  cwd_of: Callable[[str], str] | None = None) -> list[str]:  # fmt: skip
    """The `ps -eo pid=,args=` lines of THIS copy's processes: those whose working folder is
    ``root`` or inside it (2026-11-19, ADR-0026: two copies on one host; another copy's Run is its
    own input writer, on its own Windows, and never makes this one busy). ``ps`` / ``cwd_of``:
    the tests' own process list and folders."""
    if ps is None:
        ps = subprocess.run(["ps", "-eo", "pid=,args="], capture_output=True, text=True).stdout
    read = cwd_of or (lambda pid: os.readlink(f"/proc/{pid}/cwd"))
    out = []
    for ln in ps.splitlines():
        pid, _, args = ln.strip().partition(" ")
        try:
            cwd = Path(read(pid))
        except OSError:  # gone, or another user's: not ours
            continue
        if cwd == root or root in cwd.parents:
            out.append(args.strip())
    return out


def busy_reason(ps_lines: Sequence[str]) -> str | None:
    """PURE: why a new run must not start (another input writer of ours), from `ps -eo args`.
    The A/B series (scripts/stage*_ab.py) call it before each of their runs, so it never counts
    a series itself (that is `writer_busy`, the helper's)."""
    for ln in ps_lines:
        if "chain.py" in ln and "poring-lab-tmp/chain" in ln:
            return "the night chain is running (one input writer at a time)"
        if "dungeon_hunt.py run" in ln and "uv run" not in ln:
            return "another runner is playing (one input writer at a time)"
        if "flow_play.py play" in ln and "uv run" not in ln:  # live-blocks.md stage 1
            return "the live block player is playing (one input writer at a time)"
    return None


# an A/B series' `run` (live-blocks.md 3.2-3.4: scripts/stage2_ab.py, stage3_ab.py, stage4_ab.py):
# between its runs it types the setup's GM lines and reads the screen, so it is an input writer
# for its whole length, not only while one of its arms plays (matpilot round 17 N5)
AB_SERIES = re.compile(r"\bstage\d+_ab\.py\s+run\b")
IDLE_DETAIL = "waiting for the Run button"


def writer_busy(ps_lines: Sequence[str]) -> str | None:
    """PURE: the HELPER's busy rule (its starts, its checks and its status): an A/B series, or
    busy_reason's input writers (matpilot round 17 N5: GET /flows/run said "idle" while the live
    block player played an A/B run, and Run stayed enabled)."""
    for ln in ps_lines:
        if AB_SERIES.search(ln) and "uv run" not in ln:
            return "an A/B series is running (one input writer at a time)"
    return busy_reason(ps_lines)


def busy_state(state: str, detail: str, why: str | None) -> tuple[str, str]:
    """PURE: the helper's state with another input writer of ours playing (`why`) or not: an idle
    helper is "busy" with its words while one plays, and idle again once it is gone; a run of the
    helper's own, or a last run's end words, stay as they are (the status's `busy` says it)."""
    if why is not None and state in ("idle", "busy"):
        return "busy", why
    if why is None and state == "busy":
        return "idle", IDLE_DETAIL
    return state, detail


def tail(path: Path, n: int = 6, cut: int = 240) -> list[str]:
    try:
        with open(path, "rb") as fh:
            fh.seek(0, 2)
            size = fh.tell()
            fh.seek(max(0, size - 65536))
            lines = fh.read().decode("utf-8", "replace").splitlines()
    except OSError:
        return []
    return [ln[:cut] for ln in lines[-n:]]


PAUSE_LINE = re.compile(r"^\[(\d\d:\d\d:\d\d)\] (PAUSED|RESUMED)(?: after ([0-9.]+) s)?: (.*)$")


@dataclass
class RunLog:
    """PURE: what the page needs from a Run's log (flow_play's diary), fed as it grows: the Run's
    OWN start check (its CHECK line) and the pause (its PAUSED / RESUMED lines)."""

    check: dict[str, Any] | None = None
    identity: str | None = None  # the mode (Settings page) when the Run started (its check's words)
    pauses: int = 0
    paused_s: float = 0.0
    since: str | None = None  # the open pause's start (ICT), None: not paused
    why: str | None = None
    rest: str = ""

    def feed(self, text: str) -> None:
        lines = (self.rest + text).split("\n")
        self.rest = lines.pop()  # an unfinished last line waits for its end
        for ln in lines:
            if ln.startswith(CHECK_MARK) and self.check is None:
                got = parse_check_output(ln, self.identity)
                self.check = got if got.get("state") == "done" else None
                continue
            m = PAUSE_LINE.match(ln)
            if m is None:
                continue
            t, kind, after, words = m.groups()
            if kind == "PAUSED":
                self.pauses += 1
                self.since, self.why = t, words.split(". The bot waits")[0]
            else:
                self.paused_s += float(after or 0.0)
                self.since, self.why = None, None

    def pause(self) -> dict[str, Any] | None:
        if not self.pauses:
            return None
        return {"paused": self.since is not None, "since": self.since, "why": self.why,
                "count": self.pauses, "paused_s": round(self.paused_s, 1)}  # fmt: skip


def run_identity() -> str:
    """This install's mode from the Settings page ("any" | "known" | "mine", or "unreadable":
    crusader.run_identity; ADR-0020 Amendment R), "unreadable" if crusader cannot say."""
    try:
        import crusader as cr

        return cr.run_identity()
    except (OSError, ImportError, SystemExit):
        return "unreadable"


def feed_log(rl: RunLog, path: Path, offset: int) -> int:
    """Feed the run log's bytes written since ``offset``; returns the new offset."""
    try:
        with open(path, "rb") as fh:
            fh.seek(offset)
            data = fh.read(4_000_000)
    except OSError:
        return offset
    rl.feed(data.decode("utf-8", "replace"))
    return offset + len(data)


def write_json(path: Path, data: Mapping[str, Any]) -> None:
    tmp = path.with_name(f".{path.name}.{os.getpid()}")
    tmp.write_text(json.dumps(data, sort_keys=True) + "\n")
    os.replace(tmp, path)


def ict(t: float | None = None) -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(time.time() if t is None else t))


def iso_now() -> str:
    """The time as ISO 8601 with its offset (the check's "at": the browser shows it locally)."""
    return datetime.now().astimezone().isoformat(timespec="seconds")


class Helper:
    def __init__(self, d: Path = DIR) -> None:
        self.dir = d
        self.state = "idle"
        self.detail = IDLE_DETAIL
        self.busy: str | None = None  # another input writer of ours plays (writer_busy), or None
        self.flow: str | None = None
        self.live: Live | None = None  # the run's live summary (its session events)
        self.keeper: StoryKeeper | None = None  # the Run log (Batt 2026-11-21), when recorded
        self.live_off = 0
        self.end_png: str | None = None  # the session's end picture (GET /flows/run/end.png)
        self.run_log = RunLog()  # the Run's own check and its pauses, from its log
        self.run_log_off = 0
        self.config: dict[str, Any] | None = None  # the run's values (the project's settings)
        self.config_src: dict[str, str] | None = None  # each one's level
        self.keys_src: str | None = None  # the run's keys: the flow's functions, or the settings
        self.check: dict[str, Any] | None = None  # dungeon@9.45: the last check (status "check")
        self.check_proc: subprocess.Popen[bytes] | None = None
        self.check_t = 0.0
        self.plate_proc: subprocess.Popen[bytes] | None = None  # the Settings page's Remember
        self.plate_rid: str | None = None
        self.plate_t = 0.0
        self.label: str | None = None
        self.request_id: str | None = None
        self.started: str | None = None
        self.ended: str | None = None
        self.rc: int | None = None
        self.runner: subprocess.Popen[bytes] | None = None
        self.server: subprocess.Popen[bytes] | None = None
        self.run_dir: Path | None = None
        self.t_start = 0.0
        self.cap_s = 0.0
        self.stop_file = SCRATCH / STOP_NAME
        self.stop_t: float | None = None
        # a PROJECT run (live-blocks.md stage 1): the live block player plays it
        self.project: dict[str, Any] | None = None  # {name, node, map, hash, max_runtime_s}

    # -- status --
    def status(self) -> dict[str, Any]:
        log = None if self.run_dir is None else self.run_dir / "run.log"
        return {"v": VERSION, "state": self.state, "detail": self.detail, "flow": self.flow,
                "label": self.label, "request_id": self.request_id, "started": self.started,
                "ended": self.ended, "rc": self.rc, "t_wall": time.time(), "busy": self.busy,
                "log_tail": [] if log is None else player_lines(tail(log, LOG_TAIL_N,
                                                                       LOG_LINE_MAX)),
                "run_check": self.run_log.check, "pause": self.run_log.pause(),
                "identity": run_identity(),
                "config": self.config, "config_src": self.config_src,
                "keys_src": self.keys_src, "check": self.check,
                "live": None if self.live is None else self.live.summary(),
                "run_log": None if self.keeper is None else self.keeper.summary(),
                "end_png": self.end_png, "project": self.project,
                "flows": {**{k: {"title": f.title, "minutes": f.minutes, "map": f.map,
                                 "defaults": dict(f.defaults)}
                             for k, f in FLOWS.items()},
                          PROJECT: self.project_entry()}}  # fmt: skip

    def project_entry(self) -> dict[str, Any]:
        """status.json flows["project"]: the project run (the page's poller and live line read it
        like a runner flow's), titled with the current or last project's name."""
        pr = self.project or {}
        mins = int(pr.get("max_runtime_s") or 0) // 60
        return {"title": str(pr.get("name") or "a project"), "minutes": mins,
                "map": str(pr.get("map") or ""), "defaults": {}, "kind": PROJECT}  # fmt: skip

    def write_status(self) -> None:
        write_json(self.dir / "status.json", self.status())

    def own_run(self) -> bool:
        """A run or a check of the helper's own is going (its processes are in `ps` too)."""
        return (self.runner is not None or self.check_proc is not None
                or self.state in ("starting", "running", "stopping"))  # fmt: skip

    def busy_tick(self, ps_lines: Sequence[str] | None = None) -> None:
        """Round 17 N5: while the helper has no run of its own, another input writer of ours (a
        night chain, a runner, the live block player, an A/B series) makes it "busy", in words, so
        the page disables Run (its starts refuse the same, writer_busy)."""
        if self.own_run():
            self.busy = None
            return
        if ps_lines is None:
            ps_lines = copy_ps_lines()
        self.busy = writer_busy(ps_lines)
        self.state, self.detail = busy_state(self.state, self.detail, self.busy)

    def note(self, **kw: Any) -> None:
        with open(self.dir / "runs.jsonl", "a") as fh:
            fh.write(json.dumps({"t": ict(), **kw}) + "\n")

    # -- requests --
    def take_request(self) -> dict[str, Any] | None:
        f = self.dir / "request.json"
        if not f.exists():
            return None
        try:
            text = f.read_text()
        finally:
            f.unlink(missing_ok=True)  # a request is consumed once, valid or not
        req = parse_request(text)
        if isinstance(req, str):
            self.note(event="request_refused", why=req)
            self.detail = f"a request was refused: {req}"
            return None
        return req

    def handle(self, req: Mapping[str, Any]) -> None:
        if req["action"] == "plate":  # it only looks: served while a run plays too
            self.plate_start(req["id"])
        elif req["action"] == "stop":
            self.stop(req["id"])
        elif self.runner is not None or self.state in ("starting", "running", "stopping"):
            act = req["action"]
            self.detail = (
                "a run is going: the game is checked before a run, not during it"
                if act == "check"
                else "a run is already going: press Stop first"
            )
            self.note(event=f"{act}_refused", why="busy", request=req["id"])
        elif req["action"] == "check":  # a project's: the runner's read-only check
            self.check_start(FLOWS[PROJECT_CHECK_FLOW], req["id"], req["keys"], req["vals"])
        else:
            self.start_project(req)

    def detect_up(self) -> bool:
        """The vision worker and the detect server (its time box: the run's cap + 150 s), as the
        night chain starts them; False: failed (status says why). ADR-0022 Amendment 2026-11-17:
        the backend is this host's profile's (OpenVINO on Intel, onnxruntime's CUDA provider on
        NVIDIA, its WebGPU provider on AMD: the deployed ONNX on all, ADR-0022 Amendments
        2026-11-18 and 2026-11-18b), with the profile's device where it names one; with none
        (dedicated-cpu), or no model of the server's in the storage folder, the run goes on with the
        CPU detector alone (the runner falls back to it by itself)."""
        assert self.run_dir is not None
        prof = host_profile.current()
        backend = prof.detect_backend
        if backend == "none":
            self.note(event="detect_cpu_only", why="profile")
            return True  # no GPU here: the CPU detector serves
        self.detail = "building the detect server's command"
        self.write_status()
        device = ["--device", prof.detect_device] if prof.detect_device else []
        cmd = subprocess.run([PY, "scripts/unit_detector.py", "serve-cmd", "--backend", backend,
                              *device, "--seconds", serve_seconds(self.cap_s)], cwd=ROOT,
                             capture_output=True, text=True)  # fmt: skip
        if cmd.returncode == 3:  # no model for this backend in the storage folder
            self.note(event="detect_cpu_only", why="no_model")
            return True
        if cmd.returncode != 0 or not cmd.stdout.strip():
            self.fail("the detect server's command did not build", cmd.stderr[-300:])
            return False
        self.detail = "starting the vision worker"
        self.write_status()
        up = subprocess.run(["docker", "inspect", "-f", "{{.State.Running}}", WORKER],
                            capture_output=True, text=True).stdout.strip()  # fmt: skip
        if up != "true":
            r = subprocess.run(["python3", "scripts/guarded_build.py", "worker:vision@60"],
                               cwd=ROOT, capture_output=True, text=True)  # fmt: skip
            if r.returncode != 0:
                self.fail("the vision worker did not start", r.stdout[-300:])
                return False
        self.detail = "starting the detect server"
        self.write_status()
        SERVE_LOG.unlink(missing_ok=True)  # only the NEW step's start line may match
        with open(self.run_dir / "serve.log", "wb") as fh:
            self.server = subprocess.Popen(
                ["bash", "-c", cmd.stdout.strip()],
                cwd=ROOT,
                stdout=fh,
                stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
                start_new_session=True,
            )
        t0 = time.monotonic()
        while time.monotonic() - t0 < LISTEN_WAIT_S:
            time.sleep(1.0)
            text = SERVE_LOG.read_text(errors="replace") if SERVE_LOG.exists() else ""
            if '"listening"' in text and '"precision": "f32"' in text:
                return True
            if "REFUSED" in (self.run_dir / "serve.log").read_text(errors="replace"):
                self.fail("the detect server refused", tail(self.run_dir / "serve.log", 3))
                return False
            if self.server.poll() is not None:
                # ADR-0022 Amendment 2026-11-18: the server stopped before it listened (its GPU
                # provider did not load, a card its build has no code for, ...): the run goes on
                # with the CPU detector, as with no model; the run's serve.log says why
                self.note(event="detect_cpu_only", why="server_exit",
                          tail=tail(self.run_dir / "serve.log", 3))  # fmt: skip
                self.server = None
                return True
        self.fail("the detect server did not listen in time", [])
        return False

    # -- a PROJECT run (live-blocks.md stage 1): the live block player --
    def start_project(self, req: Mapping[str, Any]) -> None:
        """The checked project (the backend wrote it and its hash), played by scripts/flow_play.py:
        the busy rule, the file's hash = the request's, the detect server when a hunt core plays,
        then the player (its own checks before any input)."""
        rid = str(req["id"])
        self.check_cancel("Run was pressed: the player's own start checks decide")
        why = writer_busy(copy_ps_lines())
        doc: dict[str, Any] | None = None
        if why is None:
            doc, why = read_project(self.dir / PROJECT_FILE, str(req["project_hash"]))
        node = str(req["node"])
        if why is None and doc is not None:
            why = project_node_problem(doc, node) or old_runner_problem(doc)
        if why is not None or doc is None:
            self.state, self.detail, self.request_id = "refused", str(why), rid
            self.note(event="start_refused", why=why, request=rid, flow=PROJECT)
            return
        max_s = int(req["max_s"])
        runtime_s = ir.runtime_box(int(doc.get("max_runtime_s") or 0), max_s)  # 0: no time limit
        self.project = {"name": doc.get("name"), "node": node, "map": node_map(doc, node),
                        "hash": req["project_hash"], "max_runtime_s": runtime_s}  # fmt: skip
        self.keys_src = KEYS_SRC_PROJECT
        self.state, self.flow, self.request_id = "starting", PROJECT, rid
        self.started, self.ended, self.rc = ict(), None, None
        self.label = PROJECT_LABEL + "-" + time.strftime("%m%d%H%M")
        self.run_dir = SCRATCH / self.label
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.cap_s = float(runtime_s) + CAP_GRACE_S if runtime_s else math.inf
        keys = req.get("keys")
        if keys and has_hunt_core(doc):  # shown in the status: the hunt core's settings (blocks)
            vals, src, _ks, _why = project_values(doc, node, keys)
            self.config, self.config_src = (vals, src) if vals else (None, None)
        else:
            self.config, self.config_src = None, None
        self.live, self.live_off, self.end_png = Live(wall_minus_mono_s=wall_minus_mono()), 0, None
        self.keeper = StoryKeeper(ROOT / "settings", ROOT, self.label.rsplit("-", 1)[-1],
                                  dt.datetime.now().astimezone())  # fmt: skip
        if self.keeper.recording:
            self.live.sink = self.keeper.write
        self.run_log = RunLog(identity=run_identity())
        self.run_log_off = 0
        pfile = self.run_dir / PROJECT_FILE
        shutil.copyfile(self.dir / PROJECT_FILE, pfile)
        self.note(event="start", flow=PROJECT, label=self.label, request=rid, node=node,
                  project=self.project, keys=keys)  # fmt: skip
        if has_hunt_core(doc) and not self.detect_up():
            return
        self.detail = "the player starts (its own checks first: the live set, the keys, her map)"
        env = {
            **os.environ,
            "PYTHONDONTWRITEBYTECODE": "1",
            "TMPDIR": str(SCRATCH),
            RUN_MODES_ENV: RUN_INPUT_MODES,
            RUN_PAUSE_ENV: "1",  # it waits while the game is off the screen (Batt 2026-11-18)
            # Batt 2026-11-20 ("retry the read, it may read wrong"): a read that would END a
            # player's Run is read again first (poring_env.selfpos.guarded, hotbar_count)
            RUN_CONFIRM_ENV: "1",
        }  # a Run plays in ASSIST or BOT, never HUMAN
        self.stop_file = self.run_dir / STOP_NAME
        self.stop_file.unlink(missing_ok=True)
        self.stop_t = None
        argv = play_command(pfile, node, self.label, self.stop_file, max_s,
                            str(req["project_hash"]))  # fmt: skip
        with open(self.run_dir / "run.log", "wb") as fh:
            self.runner = subprocess.Popen(argv, cwd=ROOT, env=env, stdout=fh,
                                           stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                                           start_new_session=True)  # fmt: skip
        self.t_start = time.monotonic()
        self.state, self.detail = "starting", "the player's own start checks"
        self.write_status()

    # -- a check (dungeon@9.45): the runner's read-only `check`, the start's own argv --
    def check_start(self, flow: Flow, rid: str, keys: Mapping[str, str] | None = None,
                    settings: Mapping[str, Any] | None = None) -> None:  # fmt: skip
        """A project's check: the runner's read-only check with the keys and the settings the
        backend computed from the project's blocks (2026-11-14; parse_request checked them)."""
        if self.check_proc is not None:
            self.detail = "a check is already reading the game screen"
            return
        why = writer_busy(copy_ps_lines())
        vals: dict[str, Any] = {}
        keys_src = fc.KEYS_SRC["flow" if keys else "config"]
        if why is None:
            base = {**flow.defaults, **(settings or {})}
            vals, _src, keys_src, why = values_of(base, {}, keys)
        self.check = {"state": "checking", "at": iso_now(), "flow": PROJECT, "items": [],
                      "ok": None, "refuses": False, "keys_src": keys_src,
                      "keys": {k: vals.get(k) for k in fc.KEY_FIELDS}, "used": {},
                      "request_id": rid, "detail": "reading the game screen"}  # fmt: skip
        if why is not None:
            self.check.update(state="refused", ok=False, detail=why)
            self.note(event="check_refused", why=why, request=rid, keys_src=keys_src)
            return
        d = SCRATCH / CHECK_LABEL
        d.mkdir(parents=True, exist_ok=True)
        env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "TMPDIR": str(SCRATCH)}
        argv = check_command(flow, vals)
        self.note(event="check", flow=flow.id, request=rid, keys=self.check["keys"],
                  keys_src=keys_src)  # fmt: skip
        self.find_panels(env)  # 4f: the game's windows, before the check reads them
        with open(d / "check.log", "wb") as fh:
            self.check_proc = subprocess.Popen(argv, cwd=ROOT, env=env, stdout=fh,
                                               stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                                               start_new_session=True)  # fmt: skip
        self.check_t = time.monotonic()
        self.write_status()

    def plate_result(self, rid: str, why: str) -> None:
        """A failed name-line read, in words (the backend waits for its request's id)."""
        write_json(self.dir / PLATE_FILE, {"id": rid, "ok": False, "why": why})

    def plate_start(self, rid: str) -> None:
        """The Settings page's Remember: `crusader.py plate` once, its result in PLATE_FILE."""
        if self.plate_proc is not None:
            self.plate_result(rid, "a name line is being read already: try again in a moment")
            return
        (self.dir / PLATE_FILE).unlink(missing_ok=True)
        env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "TMPDIR": str(SCRATCH)}
        argv = [PY, str(ROOT / "scripts" / "crusader.py"), "plate", "--request", rid,
                "--out", str(self.dir / PLATE_FILE)]  # fmt: skip
        self.note(event="plate", request=rid)
        SCRATCH.mkdir(parents=True, exist_ok=True)
        with open(SCRATCH / "plate.log", "wb") as fh:
            self.plate_proc = subprocess.Popen(argv, cwd=ROOT, env=env, stdout=fh,
                                               stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                                               start_new_session=True)  # fmt: skip
        self.plate_rid, self.plate_t = rid, time.monotonic()

    def plate_tick(self) -> None:
        p, rid = self.plate_proc, self.plate_rid
        if p is None or rid is None:
            return
        rc = p.poll()
        if rc is None and time.monotonic() - self.plate_t <= PLATE_TIMEOUT_S:
            return
        if rc is None:
            with contextlib.suppress(ProcessLookupError):
                os.killpg(p.pid, signal.SIGKILL)
            p.wait(timeout=5)
        self.plate_proc = self.plate_rid = None
        try:
            got = json.loads((self.dir / PLATE_FILE).read_text())
        except (OSError, ValueError):
            got = None
        if not isinstance(got, dict) or got.get("id") != rid:
            why = (f"the name line was not read within {PLATE_TIMEOUT_S:.0f} s" if rc is None
                   else f"the name-line reader ended without a result (rc {rc})")  # fmt: skip
            self.plate_result(rid, why)
        self.note(event="plate_end", request=rid, rc=rc,
                  ok=bool(isinstance(got, dict) and got.get("ok")))  # fmt: skip

    def find_panels(self, env: Mapping[str, str]) -> None:
        """4f (teaching-prerun.md): find the game's windows before the check (`ro_agent.py
        find-panels`, pixels only), so a client whose windows sit elsewhere -- even a 1280x720
        window -- is read through the virtual client (the check reads ro_agent's shared find).
        At most PANELS_TIMEOUT_S; a failure is a note and the check goes on (the lab's places)."""
        argv = [PY, str(ROOT / "scripts" / "ro_agent.py"), "find-panels"]
        try:
            got = subprocess.run(argv, cwd=ROOT, env=dict(env), capture_output=True, text=True,
                                 timeout=PANELS_TIMEOUT_S, stdin=subprocess.DEVNULL)  # fmt: skip
            self.note(event="find_panels", rc=got.returncode,
                      lines=[ln for ln in got.stdout.splitlines()[1:] if ln][:6])  # fmt: skip
        except (OSError, subprocess.TimeoutExpired) as e:
            self.note(event="find_panels", rc=None, why=f"{type(e).__name__}")

    def check_tick(self) -> None:
        p = self.check_proc
        if p is None or self.check is None:
            return
        rc = p.poll()
        if rc is None:
            if time.monotonic() - self.check_t > CHECK_TIMEOUT_S:
                self.check_cancel(f"the check did not finish within {CHECK_TIMEOUT_S:.0f} s",
                                  "timeout")  # fmt: skip
                self.write_status()
            return
        self.check_proc = None
        log = SCRATCH / CHECK_LABEL / "check.log"
        text = log.read_text(errors="replace") if log.exists() else ""
        self.check.update(parse_check_output(text, run_identity()), rc=rc)
        self.note(event="check_end", request=self.check.get("request_id"), rc=rc,
                  ok=self.check.get("ok"), detail=self.check.get("detail"))  # fmt: skip
        self.write_status()

    def check_cancel(self, why: str, state: str = "cancelled") -> None:
        """End a running check (its own process group: uv, the runner, its screen reader)."""
        p = self.check_proc
        if p is None:
            return
        if p.poll() is None:
            with contextlib.suppress(ProcessLookupError):
                os.killpg(p.pid, signal.SIGTERM)
            try:
                p.wait(timeout=5)
            except subprocess.TimeoutExpired:
                with contextlib.suppress(ProcessLookupError):
                    os.killpg(p.pid, signal.SIGKILL)
        self.check_proc = None
        if self.check is not None:
            self.check.update(state=state, ok=None, detail=why)
        self.note(event=f"check_{state}", why=why)

    def stop(self, rid: str) -> None:
        if self.runner is None or self.runner.poll() is not None:
            self.detail = "nothing is running"
            return
        if self.state == "stopping":  # Batt 2026-11-20: a SECOND Stop skips the end's bag count
            self.detail, self.request_id = "Stop pressed again: ending now (no bag count)", rid
            self.note(event="stop_again", label=self.label, request=rid)
            os.killpg(self.runner.pid, signal.SIGINT)
            self.stop_t = None
            return
        self.state, self.detail, self.request_id = "stopping", "Stop pressed: ending cleanly", rid
        self.note(event="stop", label=self.label, request=rid)
        # the runner's --stop-file: it ends at its next tick through its NORMAL end (the safe-end
        # escape, the packets, a player's way home); SIGINT only if it has not ended by then
        self.stop_file.touch()
        self.stop_t = time.monotonic()

    def fail(self, why: str, info: Any) -> None:
        self.state, self.detail, self.ended = "failed", why, ict()
        self.note(event="failed", why=why, info=info, label=self.label)
        self.end_server()
        self.write_status()

    def end_server(self) -> None:
        """Our own detect server in the worker, ended by host PID (as the night chain does)."""
        out = subprocess.run(["docker", "top", WORKER], capture_output=True, text=True).stdout
        for ln in out.splitlines():
            f = ln.split()
            ours = f[7:10] == ["python", "-m", "poring_vision.detect_server"]
            if len(f) > 8 and f[0] == "bot" and ours:
                subprocess.run(["kill", "-TERM", f[1]])
        if self.server is not None:
            try:
                self.server.wait(timeout=60)
            except subprocess.TimeoutExpired:
                os.killpg(self.server.pid, signal.SIGTERM)
        self.server = None

    def tick(self) -> None:
        self.plate_tick()
        self.check_tick()
        if self.runner is None:
            return
        rc = self.runner.poll()
        if rc is None and time.monotonic() - self.t_start > self.cap_s:
            self.note(event="cap", label=self.label)
            os.killpg(self.runner.pid, signal.SIGINT)
            return
        if rc is None and self.stop_t is not None and time.monotonic() - self.stop_t > STOP_GRACE_S:
            self.note(event="stop_sigint", label=self.label)  # the runner did not see the file
            os.killpg(self.runner.pid, signal.SIGINT)
            self.stop_t = None
            return
        sess = session_of(self.label, DEMO) if self.live is not None else None
        if sess is not None and self.live is not None:
            self.live_off = feed_new(self.live, sess / "events.jsonl", self.live_off)
        if self.run_dir is not None:
            self.run_log_off = feed_log(self.run_log, self.run_dir / "run.log", self.run_log_off)
        if rc is None:
            if self.state == "starting" and run_started(self.label):
                self.state, self.detail = "running", "playing"
                self.write_status()
            return
        self.rc, self.ended, self.runner = rc, ict(), None
        last = tail(self.run_dir / "run.log", 3, 4000) if self.run_dir else []
        refused = next((ln for ln in last if "refused" in ln), None)
        self.state = "ended" if rc in (0, 130) else "failed"
        stopped = self.stop_t is not None or rc == 130
        self.detail = (refused or ("stopped (Stop)" if stopped else
                                   "ended by itself (time box or stock)" if rc == 0
                                   else f"the runner ended rc {rc}"))  # fmt: skip
        if self.live is not None and self.live.t0_ns is not None and not refused:
            self.detail = end_words(self.live, stopped, rc)  # matpilot: the end in plain words
            if self.flow == PROJECT and self.live.end.get("words"):  # the player's own words
                self.detail = str(self.live.end["words"])
        # ➡️ 2026-11-19 (Batt 2026-11-18: "store no pictures at all"): the end picture (the whole
        # screen) is no longer copied here nor shown; flow_play removes the runner's pictures as
        # each hunt core ends (drop_pictures). end_png stays None (the page's slot is inert).
        self.end_png = None
        with contextlib.suppress(OSError):
            (self.dir / "end.png").unlink(missing_ok=True)  # an older Run's copy
        self.stop_t = None
        self.note(event="end", label=self.label, rc=rc, detail=self.detail)
        if self.keeper is not None:
            self.keeper.close()
            self.keeper.retain()
        self.end_server()
        self.write_status()  # the run's end shows at once; its economy record follows
        self.record()
        self.write_status()

    def record(self) -> None:
        """The run's hunt sessions into data/econ/lab.sqlite (ADR-0025; round 29, Batt 2026-11-16:
        "every run, collect the economy too"): econ_db.record_after_run -- `update`, niced, under
        its own cap, waited for ECON_WAIT_S (then in the background: reap_econ notes its end);
        NON-FATAL: whatever happens is a note in the helper's log, and the run's own result is
        never touched."""
        try:
            import econ_db

            sessions = econ_db.hunt_sessions(self.label or "", DEMO)
            log = (self.run_dir or self.dir) / "econ.log"
            res = econ_db.record_after_run(
                sessions, log, wait_s=ECON_WAIT_S, py=PY, export=self.label
            )  # the /economy page fills itself
        except Exception as e:  # noqa: BLE001 -- never the run's result
            res = {"state": "failed", "why": f"{type(e).__name__}: {e}"}
        self.note(event="econ", label=self.label, **res)

    def reap_econ(self) -> None:
        """A background economy record that has ended: a note (``econ_end``), never more."""
        try:
            import econ_db

            for r in econ_db.reap_background():
                self.note(event="econ_end", **r)
        except Exception as e:  # noqa: BLE001 -- never the helper's loop
            self.note(event="econ_end", state="failed", why=f"{type(e).__name__}: {e}")

    def serve(self) -> int:
        self.dir.mkdir(parents=True, exist_ok=True)
        last = 0.0
        while True:
            req = self.take_request()
            if req is not None:
                self.handle(req)
            self.tick()
            self.reap_econ()
            if time.monotonic() - last >= STATUS_EVERY_S:
                self.busy_tick()
                self.write_status()
                last = time.monotonic()
            time.sleep(POLL_S)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("serve")
    sub.add_parser("status")
    c = sub.add_parser("command")
    c.add_argument("flow", choices=sorted(FLOWS))
    c.add_argument("--check", action="store_true", help="the read-only check's (dungeon@9.45)")
    a = ap.parse_args(argv)
    if a.cmd == "serve":
        return Helper().serve()
    if a.cmd == "status":
        f = DIR / "status.json"
        print(f.read_text() if f.exists() else '{"state": "no helper"}')
        return 0
    f = FLOWS[a.flow]
    print(" ".join(check_command(f) if a.check else command(f, "flowrun-LABEL")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
