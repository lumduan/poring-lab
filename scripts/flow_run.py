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
five of flow_config.KEY_FIELDS, each F1-F9, over the config file's for THAT run or check only.

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
   (ASSIST, the interlock, her identity, her cell).
A STOP sends SIGINT to the runner's process group (a clean end, rc 130). Either way the detect
server is ended by PID when the runner exits, and the run's session goes into data/econ/lab.sqlite.
A PROJECT RUN (Batt 2026-11-13 ~21:4x, docs/planning/live-blocks.md stage 1): POST
/flows/run/project writes the checked project (``project.json``, its hash in the request) and a
request {"action": "start", "flow": "project", "node", "project_hash", "max_s"}; the helper
checks the file's hash against the request's, copies it into the run's folder and starts the LIVE
BLOCK PLAYER (scripts/flow_play.py play) instead of the runner -- the same busy rules, ASSIST, the
detect server when a hunt core plays, the stop file, status.json (its flow id "project", titled
with the project's name). A check of the flow "project" is the runner's check (PROJECT_CHECK_FLOW)
for now.
A CHECK (dungeon@9.45, Batt 2026-11-13 "do it": /flows' start checklist ticked from the game screen)
runs ``dungeon_hunt.py check`` with the SAME argv a start would build (the config, the keys): the
runner's preamble, then the player start's checks READ from the screen -- it sends no input. It is
refused while a run starts or runs (the start's busy rule), time-boxed (CHECK_TIMEOUT_S), and its
result goes into status.json's "check"; a Run pressed meanwhile ends it (its process group).
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import re
import shutil
import signal
import subprocess
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import flow_config as fc  # the settings' registry (same directory: scripts/)

ROOT = Path(__file__).resolve().parents[1]
DIR = ROOT / "settings" / "flowrun"
SCRATCH = Path("/dev/shm/poring-lab-tmp")
SERVE_LOG = SCRATCH / "poring-guarded-execdev-vision.log"
WORKER = "poring-lab-vision-worker-1"
PY = str(ROOT / ".venv" / "bin" / "python")
STATUS_EVERY_S = 2.0
POLL_S = 1.0
LISTEN_WAIT_S = 120.0
CAP_GRACE_S = 300.0  # the helper's own cap beyond the runner's --minutes
VERSION = 1
CHECK_TIMEOUT_S = 20.0  # dungeon@9.45's check: uv + the runner's preamble + <= PLAYER_POS_S reads
CHECK_LABEL = "flowcheck"  # its --label (a check makes no session) and its scratch folder
CHECK_MARK = "CHECK "  # dungeon_hunt.CHECK_MARK: the check's result line (test_flow_run pins it)

# The runner's fixed part, as the night chain ran it (docs/records/pilot-chain/run_pilot_v3.sh +
# pilot_rec2.sh's BASE) WITHOUT --clear-map (a GM line: --player-mode refuses it), --seed fixed.
FIXED = [
    "--char", "rogue", "--map", "xmas_dun02", "--strategy", "P2", "--seed", "20261105",
]  # fmt: skip
# ➡️ 2026-11-13 ~15:2x (Batt: "do all of them"): every technique of the night chain's base is a
# SWITCH now (scripts/flow_config.py), its default the base's own (the flow's ``defaults``); FIXED
# keeps only what flow_config.NOT_SETTINGS names: the character, the map, the strategy, the seed.


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


# THE CONFIG (Batt 2026-11-13; scripts/flow_config.py): every setting of a run comes from ONE file
# in the human-only settings store, settings/flowrun/config.json, written only by the backend
# (PUT /flows/config, the Settings write gate). At each start the run takes, per setting, the
# flow's default < every map's < its map's own; a request names a flow and nothing else; a broken
# file, or two settings on one hotbar key, refuses the run before any input.
CONFIG_DIR = DIR


def config_of(flow: Flow, cfg: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, str]]:
    """PURE: a run's values and where each came from (flow_config.effective on its map)."""
    return fc.effective(flow.defaults, cfg, flow.map)


# rogue-xmas02.md 4DQ (2026-11-13): the Knife on arm B's fast loot JOINED THE BASE -- the highest
# common-item z/h with every bar passed (67,269); Batt chose it for the Run button, played until
# Stop or until the stock runs low, a 2-h cap.
FLOWS: dict[str, Flow] = {
    "xmas_dun02_rogue": Flow(
        "xmas_dun02_rogue",
        "xmas_dun02: the Rogue with Batt's Knife swap (the base of 4DQ), as a player",
        120,
        ("--player-mode",),  # Batt: the Run button plays as a player (flow_config.NOT_SETTINGS)
        "rogue-xmas02.md 4DQ (the base) + --player-mode (Batt 2026-11-13: no GM lines) + the "
        "map's two exits (dungeon@9.41, Batt 2026-11-13): weight over 50 % -> the Butterfly Wing "
        "home; a death -> the death dialog's move to saved location",
        map="xmas_dun02",
        # Batt 2026-11-13: "the Butterfly Wing on F9, the Fly Wing on F8"; "nothing fixed, we only
        # put the defaults": each one a DEFAULT, set again on /flows (every map, or this map's own).
        # The heal and escape numbers are its --strategy P2's own (test_flow_run pins them).
        defaults={
            "heal_key": "F1",
            "fly_key": "F8",
            "home_key": "F9",
            "knife_key": "F4",
            "dagger_key": "F5",
            "knife_max_s": 8.0,
            "knife_hp_min": 0.50,
            "potion_below": 0.40,
            "fly_below": 0.20,
            "fly_rate": 150,
            "fly_rate_below": 0.50,
            "weight_home": 0.50,
            "respawn_at": "645,481",
            "respawn_confirm_at": "714,405",
            # the runner numbers it reads from flags of their own (flow_config: a --tune would miss)
            "WALK_AHEAD": 7,
            "WALK_EVERY_S": 1.2,
            "BOX_EVERY_S": 1.0,
            # every TECHNIQUE (2026-11-13 ~15:2x): the night chain's base, as it ran (4DQ)
            "minutes": 120,
            "knife_swap": True,
            "bare_ready": True,
            "steal_cue": "popup",
            "swap_gap": True,
            "weight_exit": True,
            "respawn": True,
            "engage_screen": True,
            "reach_check": True,
            "unreach_escape": False,
            "miss_cue": True,
            "late_confirm": True,
            "exp_first": True,
            "kill_gap": True,
            "quiet_scan": True,
            "defend_box": False,
            "quick_drop": False,
            "quick_drop_scaled": False,
            "value_target": True,
            "box_strike": True,
            "box_now": True,
            "queue": False,
            "self_recheck": True,
            "still_strike": True,
            "still_target": True,
            "lead_press": True,
            "far_single": True,
            "near_single": False,
            "near_single_still": False,
            "far_approach": True,
            "skip_own_cells": False,
            "walk_stop": False,
            "box_ignore": 2,
            "loot": "trim",
            "loot_items": "xmas02fi5",
            "loot_memory": True,
            "loot_recheck": False,
            "loot_aim": False,
            "loot_first": True,
            "search": "patrol",
            "explore": True,
            "explore_cover": False,
            "walk_through": False,
            "walk_pick": True,
            "walk_pick_step": True,
            "walk_trust": True,
            "npc_guard": True,
            "garm_fly": True,
            "garm_confirm": 2,
            "boss_walk": False,
            "unread_step": False,
            "box_detector": "gpu",
            "hud": True,
            "hud_fast": 0.2,
        },
    ),
}


# THE PROJECT RUN (live-blocks.md stage 1): its flow id in requests and status.json, the files
PROJECT = "project"
PROJECT_FILE = "project.json"  # settings/flowrun/: the backend's checked project (canonical JSON)
PROJECT_CHECK_FLOW = "xmas_dun02_rogue"  # a check of "project" is this runner's check (for now)
PROJECT_LABEL = "flowplay"
NODE_ID = re.compile(r"[A-Za-z][A-Za-z0-9_]{0,39}")  # poring_flow.ir.NAME
HASH = re.compile(r"[0-9a-f]{64}")

STOP_NAME = "STOP"  # the runner's --stop-file, in the run's own scratch folder
STOP_GRACE_S = 90.0  # Stop: the runner ends at its next tick; SIGINT only if it has not by then


def command(flow: Flow, label: str, stop_file: Path | None = None,
            vals: Mapping[str, Any] | None = None, sub: str = "run") -> list[str]:  # fmt: skip
    """PURE: the runner's argv for ``flow`` (the label names its session; ``stop_file`` is the
    runner's --stop-file: its Stop ends the run through the normal end, with the packets;
    ``vals``: config_of's values, else the flow's defaults; ``sub``: "run", or dungeon@9.45's
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


def run_values(flow: Flow, keys: Mapping[str, str] | None, config_dir: Path = CONFIG_DIR,
               ) -> tuple[dict[str, Any], dict[str, str], str, str | None]:  # fmt: skip
    """A start's (and a check's) values: the config file (default < every map < this map), the
    flow's keys over it when given, then the clash rule -- (vals, src, keys_src, why). The live
    player's hunt core takes the same values (scripts/flow_play.py)."""
    keys_src = fc.KEYS_SRC["flow" if keys else "config"]
    cfg = fc.read_config(config_dir)  # 2026-11-13: default < every map < this map
    if isinstance(cfg, str):
        return {}, {}, keys_src, f"refused before any input: {cfg}"
    vals, src = config_of(flow, cfg)
    if keys:
        vals = fc.with_keys(vals, keys)
        src = {**src, **{k: "flow" for k in fc.KEY_FIELDS}}
    clash = fc.clash(vals)
    return vals, src, keys_src, (f"refused before any input: {clash}" if clash else None)


def check_command(flow: Flow, vals: Mapping[str, Any] | None = None) -> list[str]:
    """PURE (dungeon@9.45): the read-only check's argv -- the start's, with "check" for "run" (no
    --stop-file: a check is time-boxed by the helper)."""
    return command(flow, CHECK_LABEL, None, vals, sub="check")


def parse_request(text: str) -> dict[str, Any] | str:
    """PURE: a valid request ({"id", "action", "flow"}, and "keys" when the flow's functions gave
    them) or why it is not one. It names a flow and nothing else: every setting comes from the
    config file (Batt 2026-11-13 ~14:4x), but the five hotbar keys a flow's functions may give."""
    try:
        req = json.loads(text)
    except ValueError:
        return "unparsable request"
    if not isinstance(req, dict):
        return "unparsable request"
    rid, action, flow = req.get("id"), req.get("action"), req.get("flow")
    if not isinstance(rid, str) or not re.fullmatch(r"[A-Za-z0-9_-]{8,64}", rid):
        return "bad request id"
    if action not in ("start", "stop", "check"):
        return f"unknown action {action!r}"
    if action == "start" and flow == PROJECT:  # live-blocks.md stage 1: the live block player
        node, h, max_s = req.get("node"), req.get("project_hash"), req.get("max_s")
        if not isinstance(node, str) or not NODE_ID.fullmatch(node):
            return "a project run names its map node"
        if not isinstance(h, str) or not HASH.fullmatch(h):
            return "a project run carries the checked project's hash"
        if isinstance(max_s, bool) or not isinstance(max_s, int) or not 1 <= max_s <= 86_400:
            return "a project run carries the configured maximum run time"
        if set(req) - {"id", "action", "flow", "node", "project_hash", "max_s", "keys", "at"}:
            return "a project run carries nothing else"
        out_p: dict[str, Any] = {"id": rid, "action": action, "flow": flow, "node": node,
                                 "project_hash": h, "max_s": max_s}  # fmt: skip
        keys_p = req.get("keys")
        if keys_p is not None:  # shown only: the player reads the keys from the project itself
            why = fc.keys_problem(keys_p)
            if why is not None:
                return why
            out_p["keys"] = {k: keys_p[k] for k in fc.KEY_FIELDS}
        return out_p
    if action == "check" and flow == PROJECT:  # for now: the runner's check (PROJECT_CHECK_FLOW)
        flow = PROJECT_CHECK_FLOW
    if action in ("start", "check") and flow not in FLOWS:
        return f"unknown flow {flow!r}"
    out: dict[str, Any] = {"id": rid, "action": action, "flow": flow}
    keys = req.get("keys")
    if keys is not None:
        if action == "stop":
            return "keys go with start or check, not stop"
        why = fc.keys_problem(keys)
        if why is not None:
            return why
        out["keys"] = {k: keys[k] for k in fc.KEY_FIELDS}
    return out


def parse_check_output(text: str) -> dict[str, Any]:
    """PURE (dungeon@9.45): the check's log as its result -- its CHECK line (the items, ok,
    refuses, the values it used), else the runner's refusal (a preamble refusal: no line read)."""
    for ln in reversed(text.splitlines()):
        if ln.startswith(CHECK_MARK):
            try:
                got = json.loads(ln[len(CHECK_MARK) :])
            except ValueError:
                break
            if not isinstance(got, dict) or not isinstance(got.get("items"), list):
                break
            fails = [i for i in got["items"] if isinstance(i, dict) and i.get("ok") is False]
            unread = [i for i in got["items"] if isinstance(i, dict) and i.get("ok") is None]
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
PRESS_DOING = {"opener": "the Knife on", "equip": "the dagger back on", "potion": "a potion",
               "fly": "a Fly Wing", "home": "the Butterfly Wing home"}  # fmt: skip
# the live block player's blocks (its "block" events' "what") in a player's words
PLAYER_DOING = {"press_key": "pressing a key", "wait": "waiting", "wait_until": "waiting",
                "dungeon_hunt": "hunting", "take_exit": "taking an exit", "call": "a function",
                "while": "a loop", "repeat": "a loop", "for": "a loop", "if": "deciding",
                "stop": "stopping", "assert_save_point": "the save point"}  # fmt: skip


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

    def feed(self, e: Mapping[str, Any]) -> None:
        k, t = e.get("kind"), e.get("t_ns")
        if isinstance(t, int):
            self.t_ns = t
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
        if k == "run_start" and isinstance(t, int):
            self.t0_ns = t
        elif k == "hp_read":
            if isinstance(e.get("pct"), int):
                self.hp = e["pct"]
                self.hp_low = self.hp if self.hp_low is None else min(self.hp_low, self.hp)
            if isinstance(e.get("pos"), list):
                self.pos = [int(x) for x in e["pos"][:2]]
            return  # a look every tick: what she does stays the last action
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
                "last_event": self.last_event, "end": dict(self.end)}  # fmt: skip


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
    """PURE: the project holds a dungeon_hunt action anywhere (the detect server is started)."""
    if isinstance(doc, dict):
        if doc.get("kind") == "action" and doc.get("block") == "dungeon_hunt":
            return True
        return any(has_hunt_core(v) for v in doc.values())
    if isinstance(doc, list):
        return any(has_hunt_core(v) for v in doc)
    return False


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


def tail(path: Path, n: int = 6) -> list[str]:
    try:
        with open(path, "rb") as fh:
            fh.seek(0, 2)
            size = fh.tell()
            fh.seek(max(0, size - 8192))
            lines = fh.read().decode("utf-8", "replace").splitlines()
    except OSError:
        return []
    return [ln[:240] for ln in lines[-n:]]


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
        self.live_off = 0
        self.end_png: str | None = None  # the session's end picture (GET /flows/run/end.png)
        self.config: dict[str, Any] | None = None  # the run's values (config_of)
        self.config_src: dict[str, str] | None = None  # each one's level
        self.keys_src: str | None = None  # the run's keys: the flow's functions, or the settings
        self.check: dict[str, Any] | None = None  # dungeon@9.45: the last check (status "check")
        self.check_proc: subprocess.Popen[bytes] | None = None
        self.check_t = 0.0
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
                "log_tail": [] if log is None else player_lines(tail(log)),
                "config": self.config, "config_src": self.config_src,
                "keys_src": self.keys_src, "check": self.check,
                "live": None if self.live is None else self.live.summary(),
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
            ps = subprocess.run(["ps", "-eo", "args"], capture_output=True, text=True).stdout
            ps_lines = ps.splitlines()
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
        if req["action"] == "stop":
            self.stop(req["id"])
        elif self.runner is not None or self.state in ("starting", "running", "stopping"):
            act = req["action"]
            self.detail = (
                "a run is going: the game is checked before a run, not during it"
                if act == "check"
                else "a run is already going: press Stop first"
            )
            self.note(event=f"{act}_refused", why="busy", request=req["id"])
        elif req["action"] == "check":
            self.check_start(FLOWS[req["flow"]], req["id"], req.get("keys"))
        elif req["flow"] == PROJECT:
            self.start_project(req)
        else:
            self.start(FLOWS[req["flow"]], req["id"], req.get("keys"))

    def values_for(self, flow: Flow, keys: Mapping[str, str] | None
                   ) -> tuple[dict[str, Any], dict[str, str], str, str | None]:  # fmt: skip
        """A start's (and a check's) values: run_values on the helper's config file."""
        return run_values(flow, keys, CONFIG_DIR)

    # -- a run --
    def start(self, flow: Flow, rid: str, keys: Mapping[str, str] | None = None) -> None:
        self.check_cancel("Run was pressed: the runner's own start checks decide")
        ps = subprocess.run(["ps", "-eo", "args"], capture_output=True, text=True).stdout
        why = writer_busy(ps.splitlines())
        vals: dict[str, Any] = {}
        src: dict[str, str] = {}
        keys_src = fc.KEYS_SRC["flow" if keys else "config"]
        if why is None:
            vals, src, keys_src, why = self.values_for(flow, keys)
        if why is not None:
            self.state, self.detail, self.request_id = "refused", why, rid
            self.note(event="start_refused", why=why, request=rid, keys_src=keys_src)
            return
        self.keys_src = keys_src
        self.state, self.flow, self.request_id = "starting", flow.id, rid
        self.started, self.ended, self.rc = ict(), None, None
        self.label = "flowrun-" + time.strftime("%m%d%H%M")
        self.run_dir = SCRATCH / self.label
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.cap_s = float(vals.get("minutes", flow.minutes)) * 60 + CAP_GRACE_S
        self.config, self.config_src = vals, src
        self.live, self.live_off, self.end_png = Live(), 0, None
        self.note(event="start", flow=flow.id, label=self.label, request=rid, config=vals,
                  config_src=src, keys={k: vals.get(k) for k in fc.KEY_FIELDS},
                  keys_src=keys_src)  # fmt: skip
        if not self.detect_up():
            return
        self.detail = "the runner starts (its own checks first: ASSIST, the interlock, her cell)"
        env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "TMPDIR": str(SCRATCH)}
        self.stop_file = self.run_dir / STOP_NAME
        self.stop_file.unlink(missing_ok=True)
        self.stop_t = None
        with open(self.run_dir / "run.log", "wb") as fh:
            argv = command(flow, self.label, self.stop_file, self.config)
            self.runner = subprocess.Popen(argv, cwd=ROOT, env=env, stdout=fh,
                                           stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                                           start_new_session=True)  # fmt: skip
        self.t_start = time.monotonic()
        # matpilot 2026-11-13: "playing" only once the runner's own start checks passed (its
        # session's run_start event); until then it may still refuse (the chat open, the stock)
        self.state, self.detail = "starting", "the runner's own start checks"
        self.write_status()

    def detect_up(self) -> bool:
        """The vision worker and the detect server (its time box: the run's cap + 150 s), as the
        night chain starts them; False: failed (status says why)."""
        assert self.run_dir is not None
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
        cmd = subprocess.run([PY, "scripts/unit_detector.py", "serve-cmd", "--backend", "openvino",
                              "--seconds", str(int(self.cap_s + 150))], cwd=ROOT,
                             capture_output=True, text=True)  # fmt: skip
        if cmd.returncode != 0 or not cmd.stdout.strip():
            self.fail("the detect server's command did not build", cmd.stderr[-300:])
            return False
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
        self.fail("the detect server did not listen in time", [])
        return False

    # -- a PROJECT run (live-blocks.md stage 1): the live block player --
    def start_project(self, req: Mapping[str, Any]) -> None:
        """The checked project (the backend wrote it and its hash), played by scripts/flow_play.py:
        the busy rule, the file's hash = the request's, the detect server when a hunt core plays,
        then the player (its own checks before any input)."""
        rid = str(req["id"])
        self.check_cancel("Run was pressed: the player's own start checks decide")
        ps = subprocess.run(["ps", "-eo", "args"], capture_output=True, text=True).stdout
        why = writer_busy(ps.splitlines())
        doc: dict[str, Any] | None = None
        if why is None:
            doc, why = read_project(self.dir / PROJECT_FILE, str(req["project_hash"]))
        node = str(req["node"])
        if why is None and doc is not None:
            why = project_node_problem(doc, node)
        if why is not None or doc is None:
            self.state, self.detail, self.request_id = "refused", str(why), rid
            self.note(event="start_refused", why=why, request=rid, flow=PROJECT)
            return
        max_s = int(req["max_s"])
        runtime_s = min(int(doc.get("max_runtime_s") or 0), max_s)
        self.project = {"name": doc.get("name"), "node": node, "map": node_map(doc, node),
                        "hash": req["project_hash"], "max_runtime_s": runtime_s}  # fmt: skip
        self.keys_src = KEYS_SRC_PROJECT
        self.state, self.flow, self.request_id = "starting", PROJECT, rid
        self.started, self.ended, self.rc = ict(), None, None
        self.label = PROJECT_LABEL + "-" + time.strftime("%m%d%H%M")
        self.run_dir = SCRATCH / self.label
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.cap_s = float(runtime_s) + CAP_GRACE_S
        keys = req.get("keys")
        flow = FLOWS.get(PROJECT_CHECK_FLOW)
        if keys and flow is not None and flow.map == self.project["map"]:  # shown in the status
            vals, src, _ks, _why = self.values_for(flow, keys)
            self.config, self.config_src = vals, src
        else:
            self.config, self.config_src = None, None
        self.live, self.live_off, self.end_png = Live(), 0, None
        pfile = self.run_dir / PROJECT_FILE
        shutil.copyfile(self.dir / PROJECT_FILE, pfile)
        self.note(event="start", flow=PROJECT, label=self.label, request=rid, node=node,
                  project=self.project, keys=keys)  # fmt: skip
        if has_hunt_core(doc) and not self.detect_up():
            return
        self.detail = "the player starts (its own checks first: the live set, the keys, her map)"
        env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "TMPDIR": str(SCRATCH)}
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
    def check_start(self, flow: Flow, rid: str, keys: Mapping[str, str] | None = None) -> None:
        if self.check_proc is not None:
            self.detail = "a check is already reading the game screen"
            return
        ps = subprocess.run(["ps", "-eo", "args"], capture_output=True, text=True).stdout
        why = writer_busy(ps.splitlines())
        vals: dict[str, Any] = {}
        keys_src = fc.KEYS_SRC["flow" if keys else "config"]
        if why is None:
            vals, _src, keys_src, why = self.values_for(flow, keys)
        self.check = {"state": "checking", "at": iso_now(), "flow": flow.id, "items": [],
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
        with open(d / "check.log", "wb") as fh:
            self.check_proc = subprocess.Popen(argv, cwd=ROOT, env=env, stdout=fh,
                                               stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                                               start_new_session=True)  # fmt: skip
        self.check_t = time.monotonic()
        self.write_status()

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
        self.check.update(parse_check_output(text), rc=rc)
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
        if rc is None:
            if self.state == "starting" and run_started(self.label):
                self.state, self.detail = "running", "playing"
                self.write_status()
            return
        self.rc, self.ended, self.runner = rc, ict(), None
        last = tail(self.run_dir / "run.log", 3) if self.run_dir else []
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
        png = (sess / "end.png") if sess is not None else None
        self.end_png = None
        if png is not None and png.is_file():  # the backend serves it (GET /flows/run/end.png)
            try:
                shutil.copyfile(png, self.dir / "end.png")
                self.end_png = self.ended
            except OSError:
                pass
        self.stop_t = None
        self.note(event="end", label=self.label, rc=rc, detail=self.detail)
        self.end_server()
        self.record()
        self.write_status()

    def record(self) -> None:
        """The run's session into data/econ/lab.sqlite (ADR-0025), when it made one (a project
        run: each of its hunt core's runner sessions)."""
        demo = Path("/dev/shm/poring-lab-demo")
        if self.flow == PROJECT and self.label:
            for d in sorted(demo.glob(f"*-{self.label}-hunt*")):
                subprocess.run([PY, "scripts/econ_db.py", "update", str(d)], cwd=ROOT,
                               capture_output=True)  # fmt: skip
            return
        sess = sorted(demo.glob(f"*-{self.label}")) if self.label else []
        if sess:
            subprocess.run([PY, "scripts/econ_db.py", "update", str(sess[-1])], cwd=ROOT,
                           capture_output=True)  # fmt: skip

    def serve(self) -> int:
        self.dir.mkdir(parents=True, exist_ok=True)
        last = 0.0
        while True:
            req = self.take_request()
            if req is not None:
                self.handle(req)
            self.tick()
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
