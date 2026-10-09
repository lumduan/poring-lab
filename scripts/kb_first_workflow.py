#!/usr/bin/env python3
"""KB P1 for the FIRST WORKFLOW: the Novice training grounds -> Merchant (Batt 2026-10-09 ~18:20).

    kb_first_workflow.py build [--src DIR] [--out data/kb/first_workflow.json]
    kb_first_workflow.py summary [--kb ...]               ids, cells and counts only
    kb_first_workflow.py check-packets SESSION... [--kb ...]   banked packets vs the KB
    kb_first_workflow.py budget [--kb ...] [--kb-dir ...]  training-cost.md's estimate

Reads the pinned PRE-RENEWAL rAthena tree the way the map-server does, and writes, for every map in
the first workflow's scope: warps (cell, span, destination), spawns (mob id, count, delays, area),
EVERY NPC (keyed by script file:line; sprite id, cell, facing, kind, drawn or not, its script's
warps / savepoints / calls / variable tests), the mapflags, and the Novice -> Merchant path.

Which files: the map-server's own list, never a hand list. map.cpp `map_reloadnpc` reads
npc/pre-re/scripts_main.conf in a pre-renewal build; its `npc:` / `delnpc:` / `import:` lines are
followed recursively with `map_reloadnpc_sub`'s rules (a `//` line is skipped, a trailing `//` is
cut, a file listed twice loads once: `npc_addsrcfile`). Each file is split into top-level
definitions like `npc_parsesrcfile`: w1<TAB>w2<TAB>w3<TAB>w4, comments and blank space skipped, a
script's `{...}` body skipped by brace matching (strings and comments respected).

Which maps (derived, not listed by hand):
- the training grounds: the char-server's pre-renewal start points (conf/char_athena.conf
  `start_point_pre`), closed over the warp lines and the literal `warp "map",x,y` commands of the
  NPCs standing on them. A script warp right after a `savepoint` on a map OUTSIDE the closure leaves
  the grounds (the novice's new home: graduation or "skip training"); it is an EXIT, not expanded.
  The maps of the server's map list that share the start points' name pattern (digits generalised)
  but are never reached are reported as `unreachable`.
- the Merchant job change: every NPC whose script changes the job to the Merchant constant, every
  NPC placed by the same file(s), and every NPC that calls a function defined there; the
  graduation exits that land on those maps; travel between them over warp lines, the Kafra
  teleport tables (functions_kafras's setter / teleport functions) and literal NPC warps.

rAthena is GPL-3.0 and the client's text is the client's: the JSON goes to data/kb/ (gitignored)
and is NEVER committed (CLAUDE.md rule 4). It holds NPC names and menu options (ADR-0015: static
game data at run time); `summary` prints ids, cells and counts only, which is what a committed doc
may quote.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import re
import sys
import time
from collections import Counter, defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
import kb_build  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
SRC = Path("/dev/shm/poring-lab-rathena-src")
OUT = ROOT / "data" / "kb" / "first_workflow.json"
ENTRY = "npc/pre-re/scripts_main.conf"  # map.cpp map_reloadnpc(), #ifndef RENEWAL
MAPS_CONF = "conf/maps_athena.conf"
CHAR_CONF = "conf/char_athena.conf"
EXP_CONF = "conf/battle/exp.conf"
NPC_HPP = "src/map/npc.hpp"
MOB_DB = "db/pre-re/mob_db.yml"
JOB_EXP = "db/pre-re/job_exp.yml"
START_KEY = "start_point_pre"  # char.cpp: the pre-renewal start points
SHOPS = frozenset({"shop", "cashshop", "itemshop", "pointshop", "marketshop"})
STATES = frozenset({"CLOAKED", "HIDDEN", "DISABLED"})
# The job a workflow changes to. rAthena's e_job name; the script constant is "Job_" + its title.
# Built at run time: job names are client UI strings (ADR-0012 hook), never literals here.
TARGET_JOB_ENUM = "JOB_MERCHANT"
NOVICE_ENUM = "JOB_NOVICE"
# Kafra teleports (npc/kafras/functions_kafras.txt): the setter fills @wrpD$ / @wrpP per map, the
# teleport function maps a destination to its warp. Function identifiers, not client text.
KAFRA_SETTER_ARRAY = "@wrpD$"
TOKEN = r"(?<![\w-]){}(?![\w-])"

# --- reading the tree ---


class Src:
    """The extracted pinned tree first; any file missing there comes from kb_build's /dev/shm cache
    of the same ref (fetched once)."""

    def __init__(self, root: Path, ref: str | None = None) -> None:
        self.root = root
        self.ref = ref or json.loads(kb_build.LOCK.read_text())["rathena_ref"]
        self.hashes: dict[str, str] = {}

    def exists(self, path: str) -> bool:
        return (self.root / path).is_file()

    def read(self, path: str) -> str:
        p = self.root / path
        data = p.read_bytes() if p.is_file() else kb_build.fetch(self.ref, path)
        self.hashes[path] = hashlib.sha256(data).hexdigest()
        return data.decode("latin-1")


def load_list(read: Any, entry: str = ENTRY) -> tuple[list[str], list[dict[str, Any]]]:
    """The npc source list as map_reloadnpc_sub builds it: files in load order, and its events."""
    files: list[str] = []
    events: list[dict[str, Any]] = []

    def sub(cfg: str, depth: int) -> None:
        if depth > 16:
            raise RuntimeError(f"import loop at {cfg}")
        for no, line in enumerate(read(cfg).splitlines(), 1):
            if line.startswith("//"):
                continue
            line = line.split("//", 1)[0]
            m = re.match(r"([^:]+):\s*([^\t\r\n]*)", line)
            if not m or not m[2].strip(" "):
                continue
            key, value = m[1].strip().lower(), m[2].rstrip(" ")
            if key == "npc":
                if value in files:
                    events.append({"at": f"{cfg}:{no}", "event": "listed_twice", "file": value})
                else:
                    files.append(value)
            elif key == "delnpc":
                if value in files:
                    files.remove(value)
                events.append({"at": f"{cfg}:{no}", "event": "delnpc", "file": value})
            elif key == "import":
                sub(value, depth + 1)
            else:
                events.append({"at": f"{cfg}:{no}", "event": "unknown_setting", "key": key})

    sub(entry, 0)
    return files, events


# --- the top-level parser (npc_parsesrcfile) ---

_SCAN = re.compile(r'"(?:[^"\\\n]|\\.)*"|//[^\n]*|/\*.*?\*/|[{}]', re.S)
_STR_OR_COMMENT = re.compile(r'"(?:[^"\\\n]|\\.)*"|//[^\n]*|/\*.*?\*/', re.S)


def match_brace(text: str, i: int) -> int:
    """The index of the `}` closing the `{` at i; strings and comments are skipped."""
    depth = 0
    for m in _SCAN.finditer(text, i):
        tok = m.group()
        if tok == "{":
            depth += 1
        elif tok == "}":
            depth -= 1
            if depth == 0:
                return m.start()
    raise ValueError(f"unbalanced braces from offset {i}")


def mask_comments(code: str) -> str:
    """Comments become blanks (newlines kept, so line numbers hold); strings stay."""

    def blank(m: re.Match[str]) -> str:
        s = m.group()
        return s if s.startswith('"') else re.sub(r"[^\n]", " ", s)

    return _STR_OR_COMMENT.sub(blank, code)


def _skip_space(text: str, i: int) -> int:
    """skip_space(): whitespace, // and /* */ comments (top level, not string-aware)."""
    n = len(text)
    while i < n:
        if text[i].isspace():
            i += 1
        elif text.startswith("//", i):
            j = text.find("\n", i)
            i = n if j < 0 else j + 1
        elif text.startswith("/*", i):
            j = text.find("*/", i + 2)
            i = n if j < 0 else j + 2
        else:
            break
    return i


@dataclass
class Rec:
    file: str
    line: int
    w1: str
    w2: str
    w3: str
    w4: str
    body: str | None = None  # a script's {...}, raw
    body_line: int = 0  # the line of its `{`
    end_line: int = 0

    @property
    def key(self) -> str:
        return f"{self.file}:{self.line}"

    @property
    def type(self) -> str:
        w2 = self.w2.lower()
        if w2.startswith("warp"):
            return "warp"
        if w2 in SHOPS:
            return "shop"
        if w2.startswith("script"):
            return "function" if self.w1.lower() == "function" else "script"
        if w2.startswith("duplicate("):
            return "duplicate"
        if w2 in ("monster", "boss_monster"):
            return "monster"
        if w2 == "mapflag":
            return "mapflag"
        return "unparsed"

    @property
    def map(self) -> str | None:
        if self.w1 == "-" or self.w1.lower() == "function":
            return None
        return self.w1.split(",", 1)[0].strip()


def parse_file(text: str, file: str) -> tuple[list[Rec], list[dict[str, Any]]]:
    """Every top-level definition of one script file, and the parse problems."""
    text = text.replace("\r\n", "\n")
    recs: list[Rec] = []
    problems: list[dict[str, Any]] = []
    i = _skip_space(text, 0)
    while i < len(text):
        nl = text.find("\n", i)
        nl = len(text) if nl < 0 else nl
        line_no = text.count("\n", 0, i) + 1
        fields = text[i:nl].split("\t", 3)
        if len(fields) < 3:
            problems.append({"at": f"{file}:{line_no}", "problem": "unknown_syntax"})
            i = _skip_space(text, nl + 1)
            continue
        w1, w2, w3 = fields[0], fields[1], fields[2]
        w4 = fields[3] if len(fields) > 3 else ""
        rec = Rec(file, line_no, w1, w2, w3, w4)
        if rec.type in ("script", "function") and len(fields) > 3:
            brace = text.find("{", i + len(w1) + len(w2) + len(w3) + 3)
            try:
                end = match_brace(text, brace) if brace >= 0 else -1
            except ValueError:
                end = -1
            if end < 0:
                problems.append({"at": rec.key, "problem": "script_body_unbalanced"})
                break
            rec.body = text[brace : end + 1]
            rec.body_line = text.count("\n", 0, brace) + 1
            rec.end_line = text.count("\n", 0, end) + 1
            rec.w4 = text[i + len(w1) + len(w2) + len(w3) + 3 : brace]
            nl = end
        else:
            rec.w4 = re.sub(r"/\*.*?\*/", " ", w4).split("//", 1)[0].strip()
            rec.end_line = line_no
        if rec.type == "unparsed":
            problems.append({"at": rec.key, "problem": "unparsed_w2", "w2": w2})
        recs.append(rec)
        i = _skip_space(text, nl + 1)
    return recs, problems


# --- constants ---


def npc_constants(npc_hpp: str) -> dict[str, int]:
    """src/map/npc.hpp `enum e_job_types`: JT_X -> id, with C's implicit increments. Scripts name a
    sprite without the JT_ prefix (script_constants.hpp export_constant_npc: offset 3)."""
    m = re.search(r"enum\s+e_job_types\s*\{(.*?)\};", npc_hpp, re.S)
    if not m:
        raise ValueError("enum e_job_types not found")
    out: dict[str, int] = {}
    value = -1
    for raw in mask_comments(m[1]).split(","):
        item = raw.strip()
        if not item or item.startswith("#"):
            continue
        name, _, expr = (p.strip() for p in item.partition("="))
        if expr:
            value = int(expr, 0) if re.fullmatch(r"-?(0x)?[0-9A-Fa-f]+", expr) else out[expr]
        else:
            value += 1
        out[name] = value
    return out


@dataclass(frozen=True)
class Sprites:
    consts: dict[str, int]  # JT_ names -> ids
    mobs: dict[str, int]  # mob aegis names -> ids

    @property
    def portal(self) -> int:
        return self.consts["JT_WARPNPC"]

    @property
    def hidden(self) -> dict[int, str]:
        """The classes the client never draws (npc.hpp), by id."""
        names = ("JT_FAKENPC", "JT_HIDDEN_NPC", "JT_HIDDEN_WARP_NPC", "JT_INVISIBLE")
        return {self.consts[n]: n.removeprefix("JT_").lower() for n in names}

    def resolve(self, view: str) -> tuple[int, str | None]:
        """npc_parseview: a number, a constant, a mob's aegis name, else INVISIBLE (warned)."""
        token = re.split(r"[\s/,]", view.strip(), maxsplit=1)[0]
        try:
            return int(token, 0), None
        except ValueError:
            pass
        if "JT_" + token in self.consts:
            return self.consts["JT_" + token], None
        if token in self.mobs:
            return self.mobs[token], None
        return self.consts["JT_INVISIBLE"], f"unknown sprite constant {token!r}"

    def sprite_class(self, sid: int) -> str:
        c = self.consts
        if sid in self.hidden:
            return "hidden"
        ranges = (
            (c["NPC_RANGE1_START"], c["NPC_RANGE1_END"]),
            (c["NPC_RANGE2_START"], c["NPC_RANGE2_END"]),
            (c["NPC_RANGE3_START"], c["NPC_RANGE3_END"]),
        )
        if any(lo < sid < hi for lo, hi in ranges):
            return "npc"
        if sid in set(self.mobs.values()):
            return "mob"
        return "player_job"  # a composite (body + head) sprite


# --- what a script body does ---

WARP_LIT = re.compile(r'\bwarp\s*\(?\s*"([\w@-]+)"\s*,\s*(-?\d+)\s*,\s*(-?\d+)')
WARP_DYN = re.compile(r"\bwarp\s*\(?\s*([.@$'\w]+\$)")
SAVEPOINT = re.compile(r'\bsavepoint\s*\(?\s*"([\w@-]+)"\s*,\s*(-?\d+)\s*,\s*(-?\d+)')
SPAWN_CMD = re.compile(r'\b(monster|areamonster)\s*\(?\s*"([\w@-]+)"\s*,\s*(-?\d+)\s*,\s*(-?\d+)')
CALLFUNC = re.compile(r'\bcallfunc\s*\(?\s*"(\w+)"')
CALLSUB = re.compile(r"\bcallsub\s+(\w+)")
JOBCHANGE = re.compile(r'\bjobchange\s+(\w+)|\bcallfunc\s*\(?\s*"Job_Change"\s*,\s*(\w+)')
LABEL = re.compile(r"^\s*(On\w+)\s*:", re.M)
STATE_CMD = re.compile(
    r"\b(disablenpc|enablenpc|hideonnpc|hideoffnpc|cloakonnpc|cloakoffnpc|movenpc|unloadnpc)\b"
    r'\s*\(?\s*(?:"([^"]*)"|(strnpcinfo\s*\(\s*0\s*\)))?'
)
VAR_TEST = re.compile(r"(?<![.@$\w])([A-Za-z_]\w*)\s*==\s*(\d+)\b")
ZENY_TEST = re.compile(r"\bZeny\s*(<|>=|>|<=)\s*(\d+)")
ZENY_ANY = re.compile(r"\bZeny\b")
# A script that handles zeny but whose fee for this warp is not a literal `Zeny < N` in the same
# `case`: charged as unknown (large), so a least-zeny route never relies on it.
UNKNOWN_FEE = 1_000_000
SKILL_TEST = re.compile(r'getskilllv\s*\(\s*"(\w+)"\s*\)\s*(>|>=)\s*(\d+)')
ITEM_OP = re.compile(r"\b(getitem|delitem|countitem)\s*\(?\s*(\d+)\s*(?:,\s*(\d+))?")
CUTIN = re.compile(r'\bcutin\s*\(?\s*"([^"]*)"')
MES = re.compile(r"\bmes\s")
SET_VAR = re.compile(r"(?:\bset\s+([A-Za-z_]\w*)\s*,|^\s*([A-Za-z_]\w*)\s*[+-]?=[^=])", re.M)


def _prev_statement(code: str, pos: int) -> str:
    """The statement just before position pos (they end at ';'; blocks at '{' / '}')."""
    j = pos - 1
    while j >= 0 and code[j].isspace():
        j -= 1
    if j < 0 or code[j] != ";":
        return ""
    k = max(code.rfind(";", 0, j), code.rfind("{", 0, j), code.rfind("}", 0, j))
    stmt = code[k + 1 : j].strip()
    while True:  # leading `case N:`, `default:` and `L_label:` lines belong to no statement
        m = re.match(r"(?:case\s+[^:;]+|default|[A-Za-z_]\w*)\s*:(?!:)\s*", stmt)
        if not m:
            return stmt
        stmt = stmt[m.end() :]


def _renewal_only(code: str, pos: int) -> bool:
    """True when the statement at pos is the THEN branch of `if (checkre(0)...)`: renewal servers
    only (`checkre(0)` is true on a renewal build). Its `else` branch is the pre-renewal one."""
    k = max(code.rfind(";", 0, pos), code.rfind("{", 0, pos), code.rfind("}", 0, pos))
    head = code[k + 1 : pos]
    if not head.strip() and k >= 0 and code[k] == "{":  # `if (...) {` then the statement
        k2 = max(code.rfind(";", 0, k), code.rfind("{", 0, k), code.rfind("}", 0, k))
        head = code[k2 + 1 : k]
    m = re.search(r"\bif\s*\((.*)\)\s*$", head.strip(), re.S)
    return bool(m and re.search(r"(?<!!)\bcheckre\s*\(\s*0\s*\)(\s*==\s*true)?\s*$", m[1].strip()))


def body_facts(body: str, first_line: int) -> dict[str, Any]:
    """What one script body does, with line numbers. Text (mes) is counted, never kept. Warps in
    a renewal-only branch are kept apart (the lab server is pre-renewal)."""
    code = mask_comments(body)

    def ln(pos: int) -> int:
        return first_line + code.count("\n", 0, pos)

    warps, renewal = [], []
    for m in WARP_LIT.finditer(code):
        sp = SAVEPOINT.match(_prev_statement(code, m.start()))
        case = max(
            (c.end() for c in re.finditer(r"\bcase\s+[^:;]+:", code[: m.start()])), default=0
        )
        fee = [int(z[2]) for z in ZENY_TEST.finditer(code[case : m.start()]) if z[1] == "<"]
        row = {
            "line": ln(m.start()),
            "map": m[1],
            "x": int(m[2]),
            "y": int(m[3]),
            "savepoint": [sp[1], int(sp[2]), int(sp[3])] if sp else None,
            "zeny": fee[-1] if fee else (UNKNOWN_FEE if ZENY_ANY.search(code) else 0),
            "zeny_known": bool(fee) or not ZENY_ANY.search(code),
        }
        (renewal if _renewal_only(code, m.start()) else warps).append(row)
    tests: dict[str, set[int]] = defaultdict(set)
    for m in VAR_TEST.finditer(code):
        tests[m[1]].add(int(m[2]))
    jobs = sorted({m[1] or m[2] for m in JOBCHANGE.finditer(code)})
    return {
        "warps": warps,
        "warps_renewal_only": renewal,
        "warps_dynamic": [{"line": ln(m.start()), "expr": m[1]} for m in WARP_DYN.finditer(code)],
        "savepoints": [
            {"line": ln(m.start()), "map": m[1], "x": int(m[2]), "y": int(m[3])}
            for m in SAVEPOINT.finditer(code)
        ],
        "spawn_commands": [
            {"line": ln(m.start()), "cmd": m[1], "map": m[2], "x": int(m[3]), "y": int(m[4])}
            for m in SPAWN_CMD.finditer(code)
        ],
        "callfunc": sorted(set(CALLFUNC.findall(code))),
        "callsub": sorted(set(CALLSUB.findall(code))),
        "jobchange": jobs,
        "labels": sorted(set(LABEL.findall(code))),
        "state_commands": [
            {
                "line": ln(m.start()),
                "cmd": m[1],
                "target": m[2] if m[2] is not None else ("self" if m[3] else None),
            }
            for m in STATE_CMD.finditer(code)
        ],
        "var_tests": {k: sorted(v) for k, v in sorted(tests.items())},
        "zeny_tests": sorted({int(m[2]) for m in ZENY_TEST.finditer(code)}),
        "skill_tests": sorted({(m[1], m[2], int(m[3])) for m in SKILL_TEST.finditer(code)}),
        "items": sorted({(m[1], int(m[2])) for m in ITEM_OP.finditer(code)}),
        "cutins": sorted({c for c in CUTIN.findall(code) if c}),
        "mes_lines": len(MES.findall(code)),
        "sets": sorted({a or b for a, b in SET_VAR.findall(code)}),
    }


# --- the world: every loaded definition ---


def _name_parts(w3: str) -> tuple[str, str]:
    """npc_parsename: `display::unique` -> (display, unique); without '::' both are w3."""
    if "::" in w3:
        disp, ex = w3.split("::", 1)
        return disp.strip(), ex.strip()
    return w3.strip(), w3.strip()


def _state(w2: str) -> str | None:
    m = re.search(r"\((\w+)\)\s*$", w2)
    if m and m[1].upper() in STATES:
        return m[1].upper()
    return None


@dataclass
class World:
    files: list[str]
    recs: list[Rec]
    problems: list[dict[str, Any]]
    sprites: Sprites
    server_maps: set[str]
    by_exname: dict[str, Rec] = field(default_factory=dict)
    functions: dict[str, Rec] = field(default_factory=dict)
    facts: dict[str, dict[str, Any]] = field(default_factory=dict)  # rec key -> body facts
    on_map: dict[str, list[Rec]] = field(default_factory=lambda: defaultdict(list))

    def __post_init__(self) -> None:
        for r in self.recs:
            if r.type in ("script", "shop", "duplicate", "warp"):
                self.by_exname.setdefault(_name_parts(r.w3)[1], r)
            if r.type == "function":
                self.functions[r.w3.strip()] = r
            if r.body is not None:
                self.facts[r.key] = body_facts(r.body, r.body_line)
            m = r.map
            if m is not None:
                self.on_map[m].append(r)

    def source(self, r: Rec) -> Rec | None:
        """A duplicate's source script (by its unique name)."""
        if r.type != "duplicate":
            return r
        m = re.match(r"duplicate\(([^)]*)\)", r.w2, re.I)
        return self.by_exname.get(m[1].strip()) if m else None

    def body_of(self, r: Rec) -> dict[str, Any]:
        src = self.source(r)
        return self.facts.get(src.key, {}) if src is not None else {}

    def callers_of(self, names: set[str]) -> list[Rec]:
        return [r for r in self.recs if r.map and set(self.body_of(r).get("callfunc", [])) & names]


def build_world(src: Src) -> World:
    files, events = load_list(src.read)
    recs: list[Rec] = []
    problems: list[dict[str, Any]] = [e for e in events if e["event"] == "unknown_setting"]
    for f in files:
        if not src.exists(f):
            problems.append({"at": f, "problem": "listed_file_missing"})
            continue
        r, p = parse_file(src.read(f), f)
        recs += r
        problems += p
    mob_doc = yaml.load(src.read(MOB_DB), Loader=getattr(yaml, "CSafeLoader", yaml.SafeLoader))
    mobs = {str(e["AegisName"]): int(e["Id"]) for e in mob_doc["Body"]}
    sprites = Sprites(npc_constants(src.read(NPC_HPP)), mobs)
    server_maps = set(re.findall(r"^map:\s*(\S+)", src.read(MAPS_CONF), re.M))
    return World(files, recs, problems, sprites, server_maps)


# --- per-map records ---


def _ints(s: str) -> list[int]:
    return [int(v) for v in re.findall(r"-?\d+", s)]


def warp_entry(r: Rec) -> dict[str, Any]:
    """`map,x,y,dir<TAB>warp[2][(STATE)]<TAB>name<TAB>spanx,spany,tomap,tox,toy` (its sscanf)."""
    where = r.w1.split(",")
    m = re.match(r"\s*(-?\d+)\s*,\s*(-?\d+)\s*,\s*([^,\s]+)\s*,\s*(-?\d+)\s*,\s*(-?\d+)", r.w4)
    if m is None:
        raise ValueError(f"{r.key}: bad warp target {r.w4!r}")
    to = list(m.groups())
    return {
        "key": r.key,
        "kind": "warp2" if r.w2.lower().startswith("warp2") else "warp",
        "x": int(where[1]),
        "y": int(where[2]),
        "span_x": int(to[0]),
        "span_y": int(to[1]),
        "to_map": to[2],
        "to_x": int(to[3]),
        "to_y": int(to[4]),
        "name": r.w3.strip(),
        "state": _state(r.w2),
        "drawn": _state(r.w2) is None,
    }


def spawn_entry(r: Rec, mobs: dict[str, int]) -> dict[str, Any]:
    where = r.w1.split(",")
    nums = [int(v) for v in where[1:5]] + [0] * (4 - len(where[1:5]))
    what = [p.strip() for p in r.w4.split(",")]
    mob = int(what[0]) if what[0].lstrip("-").isdigit() else mobs.get(what[0], -1)

    def num(i: int) -> int:
        return int(what[i]) if len(what) > i and what[i].lstrip("-").isdigit() else 0

    return {
        "key": r.key,
        "id": mob,
        "amount": num(1),
        "x": nums[0],
        "y": nums[1],
        "xs": nums[2],
        "ys": nums[3],
        "delay1_ms": num(2),
        "delay2_ms": num(3),
        "event": what[4] if len(what) > 4 and what[4] else None,
        "boss": r.w2.lower() == "boss_monster",
        "name": r.w3.strip(),
    }


def npc_entry(r: Rec, w: World) -> dict[str, Any]:
    """One placed NPC (script, duplicate or shop)."""
    where = r.w1.split(",")
    x, y = int(where[1]), int(where[2])
    facing = int(where[3]) if len(where) > 3 and where[3].strip().lstrip("-").isdigit() else 0
    sid, warn = w.sprites.resolve(r.w4)
    span = _ints(r.w4.split(",", 1)[1]) if r.type != "shop" and "," in r.w4 else []
    span = span[:2] if len(span) >= 2 else []
    src = w.source(r)
    facts = w.body_of(r)
    labels = facts.get("labels", [])
    hidden = w.sprites.hidden
    if r.type == "shop":
        kind = "shop"
    elif sid in hidden:
        kind = "invisible_trigger" if span and any(s > 0 for s in span) else "invisible"
    elif sid == w.sprites.portal:
        kind = "warp_portal"
    else:
        kind = "dialog"
    state = _state(r.w2)
    names = {"self", None, r.w3.strip(), *_name_parts(r.w3)}
    if src is not None:
        names |= {src.w3.strip(), *_name_parts(src.w3)}
    self_hide = [
        c
        for c in facts.get("state_commands", [])
        if c["cmd"] in ("disablenpc", "hideonnpc", "cloakonnpc") and c["target"] in names
    ]
    if sid in hidden or state is not None:
        drawn: bool | str = False
    elif self_hide:
        drawn = "conditional"
    else:
        drawn = True
    display, exname = _name_parts(r.w3)
    entry: dict[str, Any] = {
        "key": r.key,
        "type": r.type,
        "kind": kind,
        "sprite": sid,
        "sprite_raw": r.w4.split(",")[0],
        "sprite_class": w.sprites.sprite_class(sid),
        "hidden_class": hidden.get(sid),
        "x": x,
        "y": y,
        "dir": facing,
        "trigger_span": span or None,
        "state": state,
        "drawn": drawn,
        "name": display,
        "exname": exname,
        "duplicate_of": src.key if (r.type == "duplicate" and src is not None) else None,
        "touch": "OnTouch" in labels or "OnTouch_" in labels,
    }
    if warn:
        entry["warning"] = warn
    if r.type == "duplicate" and src is None:
        entry["warning"] = "duplicate source not found"
    if r.type == "shop":
        entry["shop_items"] = [int(a) for a, _ in re.findall(r"(\d+):(-?\d+)", r.w4)]
    if facts:
        keep = (
            "warps",
            "warps_renewal_only",
            "warps_dynamic",
            "savepoints",
            "spawn_commands",
            "callfunc",
            "callsub",
            "jobchange",
            "labels",
            "state_commands",
            "var_tests",
            "zeny_tests",
            "skill_tests",
            "items",
            "cutins",
            "mes_lines",
        )
        entry["script"] = {k: facts[k] for k in keep if facts.get(k)}
        if src is not None and src.body is not None:
            entry["script"]["menus"] = _menus(src)
    return entry


def _menus(r: Rec) -> list[dict[str, Any]]:
    """The body's select / menu options with line numbers (kb_route's reading; local only)."""
    import kb_route

    out = []
    for no, line in enumerate((r.body or "").splitlines(), r.body_line):
        if line.lstrip().startswith("//"):
            continue
        for s in kb_route.SELECT.finditer(line):
            out.append({"line": no, "call": s.group(1), "options": kb_route.split_args(s["args"])})
        mm = kb_route.MENU.search(line)
        if mm:
            opts = re.findall(r"\"((?:[^\"\\]|\\.)*)\"\s*,", mm["args"])
            out.append({"line": no, "call": "menu", "options": opts})
    return out


def map_entry(m: str, w: World) -> dict[str, Any]:
    recs = w.on_map.get(m, [])
    by_type: dict[str, list[Rec]] = defaultdict(list)
    for r in recs:
        by_type[r.type].append(r)
    return {
        "loaded_by_server": m in w.server_maps,
        "warps": [warp_entry(r) for r in by_type["warp"]],
        "spawns": [spawn_entry(r, w.sprites.mobs) for r in by_type["monster"]],
        "npcs": [
            npc_entry(r, w) for r in by_type["script"] + by_type["duplicate"] + by_type["shop"]
        ],
        "mapflags": [
            {"key": r.key, "flag": r.w3.strip(), "value": r.w4.strip() or None}
            for r in by_type["mapflag"]
        ],
        "unparsed": [r.key for r in by_type["unparsed"]],
    }


# --- the scope ---


def start_points(char_conf: str, key: str = START_KEY) -> list[tuple[str, int, int]]:
    """conf/char_athena.conf `start_point_pre: map,x,y:map,x,y` (later lines win)."""
    out: list[tuple[str, int, int]] = []
    for line in char_conf.splitlines():
        m = re.match(rf"\s*{key}\s*:\s*(\S+)", line.split("//", 1)[0])
        if m:
            out = [
                (p.split(",")[0], int(p.split(",")[1]), int(p.split(",")[2]))
                for p in m[1].split(":")
                if p.count(",") == 2
            ]
    return out


def grounds(w: World, seeds: Sequence[str]) -> dict[str, Any]:
    """The closure from the start points (module docstring), its edges and exits."""
    closure: list[str] = []
    todo = list(dict.fromkeys(seeds))
    edges: list[dict[str, Any]] = []
    exits: list[dict[str, Any]] = []
    while todo:
        m = todo.pop(0)
        if m in closure:
            continue
        closure.append(m)
        for r in w.on_map.get(m, []):
            if r.type == "warp":
                e = warp_entry(r)
                edges.append(
                    {
                        "from": m,
                        "to": e["to_map"],
                        "via": "portal",
                        "key": r.key,
                        "cell": [e["x"], e["y"]],
                        "to_cell": [e["to_x"], e["to_y"]],
                    }
                )
                todo.append(e["to_map"])
            if r.type not in ("script", "duplicate"):
                continue
            facts = w.body_of(r)
            for wp in facts.get("warps", []):
                sp = wp["savepoint"]
                row = {
                    "from": m,
                    "to": wp["map"],
                    "via": "npc",
                    "key": r.key,
                    "script_line": wp["line"],
                    "to_cell": [wp["x"], wp["y"]],
                    "savepoint": sp,
                }
                if wp["map"] not in w.server_maps:  # "Random", "SavePoint": warp keywords
                    exits.append({**row, "special": True})
                elif sp is not None and sp[0] not in closure:
                    exits.append(row)
                else:
                    edges.append(row)
                    todo.append(wp["map"])
            for d in facts.get("warps_dynamic", []):
                exits.append(
                    {
                        "from": m,
                        "to": None,
                        "via": "npc_dynamic",
                        "key": r.key,
                        "script_line": d["line"],
                        "expr": d["expr"],
                    }
                )
    patterns = {re.sub(r"\d+", r"\\d+", re.escape(s)) for s in seeds}
    family = sorted(m for m in w.server_maps if any(re.fullmatch(p, m) for p in patterns))
    return {
        "rule": "closure of the start points over warp lines and literal NPC warps; a warp right "
        "after a savepoint outside the closure is an exit",
        "seeds": list(dict.fromkeys(seeds)),
        "maps": closure,
        "family": family,
        "unreachable": [m for m in family if m not in closure],
        "edges": _dedupe(edges),
        "exits": _dedupe(exits),
    }


def _dedupe(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    out = []
    for r in rows:
        k = json.dumps(r, sort_keys=True)
        if k not in seen:
            seen.add(k)
            out.append(r)
    return out


def job_const(enum: str) -> str:
    return "Job_" + enum.removeprefix("JOB_").title()


def job_quest(w: World, enum: str = TARGET_JOB_ENUM) -> dict[str, Any]:
    """The NPCs of one job change: who changes the job, the quest file(s), the NPCs placed by them
    or calling their functions, the quest variables and which values each NPC tests."""
    const = job_const(enum)
    changers = [r for r in w.recs if r.map and const in w.body_of(r).get("jobchange", [])]
    files = sorted({(w.source(r) or r).file for r in changers})
    funcs = {r.w3.strip() for r in w.recs if r.type == "function" and r.file in files}
    placed = [r for r in w.recs if r.file in files and r.map and r.type != "mapflag"]
    callers = [r for r in w.callers_of(funcs) if r not in placed]
    qvars: set[str] = set()
    for r in w.recs:
        if r.file in files and r.key in w.facts:
            qvars |= {v for v in w.facts[r.key]["sets"] if v[0].islower()}
    npcs = []
    for r in placed + callers:
        own = w.body_of(r)
        bodies = [own] + [
            w.facts[w.functions[f].key]
            for f in own.get("callfunc", [])
            if f in funcs and f in w.functions
        ]
        tests: dict[str, set[int]] = defaultdict(set)
        zeny: set[int] = set()
        items: set[tuple[str, int]] = set()
        for b in bodies:
            for k, v in b.get("var_tests", {}).items():
                if k in qvars:
                    tests[k] |= set(v)
            zeny |= set(b.get("zeny_tests", []))
            items |= {tuple(i) for i in b.get("items", [])}
        role = "job_change" if r in changers else ("function_caller" if r in callers else "quest")
        npcs.append(
            {
                "key": r.key,
                "map": r.map,
                "cell": _cell(r),
                "role": role,
                "tests": {k: sorted(v) for k, v in sorted(tests.items())},
                "zeny_tests": sorted(zeny),
                "items": sorted(items),
            }
        )
    return {
        "job": enum,
        "constant": const,
        "files": files,
        "functions": sorted(funcs),
        "variables": sorted(qvars),
        "npcs": npcs,
        "maps": sorted({n["map"] for n in npcs if n["map"] is not None}),
    }


def _cell(r: Rec) -> list[int]:
    p = r.w1.split(",")
    return [int(p[1]), int(p[2])] if len(p) > 2 else []


def requirement_checks(w: World, quest: dict[str, Any]) -> dict[str, Any]:
    """The job changer's own checks, and those of the functions it calls (one level)."""
    out: dict[str, Any] = {"zeny_tests": set(), "skill_tests": set(), "functions": set()}
    for n in quest["npcs"]:
        if n["role"] != "job_change":
            continue
        r = next(x for x in w.recs if x.key == n["key"])
        facts = w.body_of(r)
        out["zeny_tests"] |= set(facts.get("zeny_tests", []))
        out["skill_tests"] |= set(facts.get("skill_tests", []))
        for f in facts.get("callfunc", []):
            fr = w.functions.get(f)
            if fr is not None and w.facts[fr.key]["skill_tests"]:
                out["functions"].add(fr.key)
                out["skill_tests"] |= set(w.facts[fr.key]["skill_tests"])
    return {k: sorted(v) for k, v in out.items()}


# --- travel ---


def kafra_edges(w: World) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Kafra teleports: the setter function's per-map destination lists and prices, the teleport
    function's destination -> warp (pre-renewal branch), the free-ticket item it consumes."""
    setter = next(
        (
            f
            for f in w.functions.values()
            if re.search(r"setarray\s+" + re.escape(KAFRA_SETTER_ARRAY), f.body or "")
            and re.search(r'\.@map\$\s*==\s*"', f.body or "")
        ),
        None,
    )
    tele = next(
        (f for f in w.functions.values() if KAFRA_SETTER_ARRAY + "[.@j] ==" in (f.body or "")), None
    )
    if setter is None or tele is None:
        return [], {"found": False}
    code = mask_comments(setter.body or "")
    per_map: dict[str, list[tuple[str, int]]] = {}
    marks = list(re.finditer(r'\.@map\$\s*==\s*"([\w-]+)"', code))
    for i, mk in enumerate(marks):
        seg = code[mk.end() : marks[i + 1].start() if i + 1 < len(marks) else len(code)]
        names = re.search(r"setarray\s+@wrpD\$\[0\]\s*,(.*?);", seg, re.S)
        prices = re.search(r"setarray\s+@wrpP\[0\]\s*,(.*?);", seg, re.S)
        if names:
            ns = re.findall(r'"([^"]*)"', names[1])
            ps = _ints(prices[1]) if prices else []
            per_map[mk[1]] = [(n, ps[j] if j < len(ps) else -1) for j, n in enumerate(ns)]
    tcode = mask_comments(tele.body or "")
    dest: dict[str, tuple[str, int, int]] = {}
    tmarks = list(re.finditer(r'@wrpD\$\[\.@j\]\s*==\s*"([^"]+)"', tcode))
    for i, mk in enumerate(tmarks):
        seg = tcode[mk.end() : tmarks[i + 1].start() if i + 1 < len(tmarks) else len(tcode)]
        ws = WARP_LIT.findall(seg)
        if not ws:
            continue
        pick = ws[-1] if ("checkre(0)" in seg and len(ws) > 1) else ws[0]  # pre-re: the else
        dest[mk[1]] = (pick[0], int(pick[1]), int(pick[2]))
    ticket = re.search(r"countitem\s*\(\s*(\d+)\s*\)\s*>\s*0", tcode)
    setter_name = setter.w3.strip()
    edges = []
    for r in w.recs:
        if not r.map or setter_name not in w.body_of(r).get("callfunc", []):
            continue
        for name, price in per_map.get(r.map, []):
            if name in dest:
                d = dest[name]
                edges.append(
                    {
                        "from": r.map,
                        "to": d[0],
                        "via": "kafra",
                        "key": r.key,
                        "npc_cell": _cell(r),
                        "to_cell": [d[1], d[2]],
                        "zeny": price,
                    }
                )
    info = {
        "found": True,
        "setter": setter.key,
        "teleport": tele.key,
        "free_ticket_item": int(ticket[1]) if ticket else None,
        "maps": sorted(per_map),
    }
    return _dedupe(edges), info


def all_edges(w: World) -> list[dict[str, Any]]:
    edges = []
    for r in w.recs:
        if not r.map:
            continue
        if r.type == "warp":
            e = warp_entry(r)
            edges.append(
                {
                    "from": r.map,
                    "to": e["to_map"],
                    "via": "portal",
                    "key": r.key,
                    "cell": [e["x"], e["y"]],
                    "span": [e["span_x"], e["span_y"]],
                    "to_cell": [e["to_x"], e["to_y"]],
                    "drawn": e["drawn"],
                }
            )
        elif r.type in ("script", "duplicate"):
            facts = w.body_of(r)
            tests = sorted(facts.get("var_tests", {}))
            for wp in facts.get("warps", []):
                edges.append(
                    {
                        "from": r.map,
                        "to": wp["map"],
                        "key": r.key,
                        "via": "npc" if tests else "transport",
                        "npc_cell": _cell(r),
                        "script_line": wp["line"],
                        "to_cell": [wp["x"], wp["y"]],
                        "zeny": wp["zeny"],
                        "zeny_known": wp["zeny_known"],
                        "conditions": tests,
                    }
                )
    k, _ = kafra_edges(w)
    return edges + k


def _fee(e: dict[str, Any], tickets: bool) -> int:
    if tickets and e["via"] == "kafra":
        return 0  # a free Kafra teleport ticket
    return max(0, int(e.get("zeny", 0) or 0))


def shortest(
    edges: Sequence[dict[str, Any]],
    start: str,
    goal: str,
    via: frozenset[str],
    zeny_first: bool = False,
    tickets: bool = False,
) -> list[dict[str, Any]] | None:
    """Fewest map changes then least zeny (or zeny first), Dijkstra; None when unreachable.
    `tickets`: Kafra teleports cost no zeny (the graduate's free tickets)."""
    import heapq

    adj: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for e in edges:
        if e["via"] in via and e["from"] != e["to"]:
            adj[e["from"]].append(e)
    heap: list[tuple[int, int, int, str, list[dict[str, Any]]]] = [(0, 0, 0, start, [])]
    best: dict[str, tuple[int, int]] = {}
    n = 0
    while heap:
        a, b, _, m, path = heapq.heappop(heap)
        if m == goal:
            return path
        if m in best and best[m] <= (a, b):
            continue
        best[m] = (a, b)
        for e in adj.get(m, []):
            n += 1
            fee = _fee(e, tickets)
            nxt = (a + fee, b + 1) if zeny_first else (a + 1, b + fee)
            heapq.heappush(heap, (*nxt, n, e["to"], [*path, e]))
    return None


# The ways between maps: portals (warp lines), Kafra teleports, "transport" NPCs (literal warps
# in a script that tests no variable: boats, warpers) and any other NPC warp (it tests a variable:
# a quest state or a job, so it may not be offered).
POLICIES = {
    "walk": frozenset({"portal"}),
    "walk_kafra": frozenset({"portal", "kafra"}),
    "walk_kafra_transport": frozenset({"portal", "kafra", "transport"}),
    "walk_kafra_npc": frozenset({"portal", "kafra", "transport", "npc"}),
}


def legs(edges: Sequence[dict[str, Any]], home: str, stops: Sequence[str]) -> dict[str, Any]:
    """Round trips home -> stop -> home per policy (fewest map changes), plus `least_zeny`: walk,
    Kafra and transport NPCs, zeny first, Kafra teleports on free tickets."""
    out: dict[str, Any] = {}
    variants = [(name, via, False, False) for name, via in POLICIES.items()]
    variants.append(("least_zeny", POLICIES["walk_kafra_transport"], True, True))
    for stop in stops:
        row: dict[str, Any] = {}
        for name, via, zf, tk in variants:
            go = shortest(edges, home, stop, via, zf, tk)
            back = shortest(edges, stop, home, via, zf, tk)
            if go is None or back is None:
                row[name] = None
                continue
            maps = [home] + [e["to"] for e in go] + [e["to"] for e in back]
            row[name] = {
                "maps": list(dict.fromkeys(maps)),
                "go": go,
                "back": back,
                "hops": len(go) + len(back),
                "kafra_hops": sum(e["via"] == "kafra" for e in go + back),
                "zeny_listed": sum(_fee(e, False) for e in go + back),
                "zeny_with_tickets": sum(_fee(e, True) for e in go + back),
            }
        out[stop] = row
    return out


# --- rooms: the walkable components of a map ---
# An interior map (alberta_in, geffen_in, ...) is several rooms joined by its own portals, so a
# map-level route can be impossible on foot. The travel search below runs on (map, room) nodes:
# rooms are the 8-connected components of the server's walkable cells (a diagonal step needs both
# orthogonal cells free, as rAthena's path_search), from poring_dataset.mapcache.

AREA_SIZE = 14  # rAthena: an NPC answers a click from within AREA_SIZE cells
NEAR = 3  # an NPC is approached from a walkable cell this close (else AREA_SIZE)


class Rooms:
    def __init__(self, grids: Any) -> None:
        self.grids = grids or {}
        self._labels: dict[str, list[int]] = {}

    def labels(self, m: str) -> list[int] | None:
        if m in self._labels:
            return self._labels[m]
        g = self.grids.get(m)
        if g is None:
            return None
        from collections import deque

        lab = [-1] * (g.xs * g.ys)
        n = 0
        for start in range(g.xs * g.ys):
            sx, sy = start % g.xs, start // g.xs
            if lab[start] >= 0 or g.nopass(sx, sy):
                continue
            lab[start] = n
            q = deque([(sx, sy)])
            while q:
                x, y = q.popleft()
                for dx in (-1, 0, 1):
                    for dy in (-1, 0, 1):
                        nx, ny = x + dx, y + dy
                        if (not (dx or dy)) or g.nopass(nx, ny) or lab[nx + ny * g.xs] >= 0:
                            continue
                        if dx and dy and (g.nopass(x + dx, y) or g.nopass(x, y + dy)):
                            continue
                        lab[nx + ny * g.xs] = n
                        q.append((nx, ny))
            n += 1
        self._labels[m] = lab
        return lab

    def near(self, m: str, cell: Sequence[int], radius: int = NEAR) -> set[int]:
        """The rooms of the walkable cells within `radius` of cell (Chebyshev); -1 when the map
        is unknown to the map cache."""
        lab = self.labels(m)
        if lab is None:
            return {-1}
        g = self.grids[m]
        cx, cy = int(cell[0]), int(cell[1])
        for r in (0, radius, AREA_SIZE) if radius else (0,):
            found = {
                lab[x + y * g.xs]
                for x in range(max(0, cx - r), min(g.xs, cx + r + 1))
                for y in range(max(0, cy - r), min(g.ys, cy + r + 1))
                if lab[x + y * g.xs] >= 0
            }
            if found:
                return found
        return set()

    def span(self, m: str, cell: Sequence[int], span: Sequence[int]) -> set[int]:
        """The rooms from which a portal's trigger area (cell +- span) can be stepped on."""
        lab = self.labels(m)
        if lab is None:
            return {-1}
        g = self.grids[m]
        cx, cy, sx, sy = int(cell[0]), int(cell[1]), int(span[0]), int(span[1])
        return {
            lab[x + y * g.xs]
            for x in range(max(0, cx - sx), min(g.xs, cx + sx + 1))
            for y in range(max(0, cy - sy), min(g.ys, cy + sy + 1))
            if lab[x + y * g.xs] >= 0
        }


def room_edges(
    edges: Sequence[dict[str, Any]], maps: set[str], rooms: Rooms
) -> list[dict[str, Any]]:
    """Map-level edges as (map#room) -> (map#room) edges, for the maps in `maps`."""
    out = []
    for e in edges:
        if e["from"] not in maps:
            continue
        if e["via"] == "portal":
            src = rooms.span(e["from"], e["cell"], e.get("span", [1, 1]))
        else:
            src = rooms.near(e["from"], e["npc_cell"])
        dst = rooms.near(e["to"], e["to_cell"]) if e["to"] in maps else {-1}
        d = min(dst) if dst else -1
        for r in sorted(src):
            out.append({**e, "a": f"{e['from']}#{r}", "b": f"{e['to']}#{d}"})
    return out


def shortest_nodes(
    redges: Sequence[dict[str, Any]],
    starts: set[str],
    goals: set[str],
    via: frozenset[str],
    zeny_first: bool = False,
    tickets: bool = False,
) -> list[dict[str, Any]] | None:
    """Dijkstra over room nodes: fewest edges then least zeny (or zeny first)."""
    import heapq

    adj: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for e in redges:
        if e["via"] in via and e["a"] != e["b"]:
            adj[e["a"]].append(e)
    heap: list[tuple[int, int, int, str, list[dict[str, Any]]]] = [
        (0, 0, i, s, []) for i, s in enumerate(sorted(starts))
    ]
    heapq.heapify(heap)
    best: dict[str, tuple[int, int]] = {}
    n = len(heap)
    while heap:
        a, b, _, node, path = heapq.heappop(heap)
        if node in goals:
            return path
        if node in best and best[node] <= (a, b):
            continue
        best[node] = (a, b)
        for e in adj.get(node, []):
            n += 1
            fee = _fee(e, tickets)
            nxt = (a + fee, b + 1) if zeny_first else (a + 1, b + fee)
            heapq.heappush(heap, (*nxt, n, e["b"], [*path, e]))
    return None


def _route(go: list[dict[str, Any]], back: list[dict[str, Any]], home: str) -> dict[str, Any]:
    seq = go + back
    maps = [home] + [e["to"] for e in seq]
    return {
        "maps": list(dict.fromkeys(maps)),
        "go": go,
        "back": back,
        "hops": len(seq),
        "map_changes": sum(e["from"] != e["to"] for e in seq),
        "kafra_hops": sum(e["via"] == "kafra" for e in seq),
        "zeny_listed": sum(_fee(e, False) for e in seq),
        "zeny_with_tickets": sum(_fee(e, True) for e in seq),
        "fee_unknown": any(not e.get("zeny_known", True) for e in seq),
    }


def room_trips(
    edges: Sequence[dict[str, Any]],
    map_level: dict[str, Any],
    quest: dict[str, Any],
    home: str,
    grad: Sequence[dict[str, Any]],
    grids: Any,
) -> dict[str, Any]:
    """The delivery round trips on (map, room) nodes: from the home map's hub NPC (the quest NPC
    there that is not the job changer; it hands out and takes back the delivery) to each stop's
    quest NPC and back; and on the home map, from the graduation arrival to each quest NPC."""
    rooms = Rooms(grids)
    cand: set[str] = {home} | set(quest["maps"])
    for row in map_level.values():
        for pol, r in row.items():
            if r and pol != "walk":
                cand |= set(r["maps"])
    for e in edges:  # one portal hop around, for the doors a map-level route did not use
        if e["via"] == "portal" and e["from"] in cand and e["to"] in rooms.grids:
            cand.add(e["to"])
    redges = room_edges(edges, cand, rooms)
    home_npcs = [n for n in quest["npcs"] if n["map"] == home]
    hub = max(
        (n for n in home_npcs if n["role"] != "job_change"),
        key=lambda n: sum(len(v) for v in n["tests"].values()),
        default=None,
    )
    hub = hub or next(iter(home_npcs), None)
    if hub is None:
        return {"error": "no quest NPC on the home map"}
    starts = {f"{home}#{r}" for r in rooms.near(home, hub["cell"])}
    variants = [(name, via, False, False) for name, via in POLICIES.items()]
    variants.append(("least_zeny", POLICIES["walk_kafra_transport"], True, True))
    trips: dict[str, Any] = {}
    for n in quest["npcs"]:
        if n["map"] == home:
            continue
        goals = {f"{n['map']}#{r}" for r in rooms.near(n["map"], n["cell"])}
        row: dict[str, Any] = {}
        for name, via, zf, tk in variants:
            go = shortest_nodes(redges, starts, goals, via, zf, tk)
            back = shortest_nodes(redges, goals, starts, via, zf, tk)
            row[name] = None if go is None or back is None else _route(go, back, home)
        trips[n["map"]] = row
    inside: list[dict[str, Any]] = []
    for g in grad[:1]:
        arrive = {f"{home}#{r}" for r in rooms.near(home, g["to_cell"])}
        for n in home_npcs:
            goal = {f"{home}#{r}" for r in rooms.near(home, n["cell"])}
            path = [] if arrive & goal else shortest_nodes(redges, arrive, goal, POLICIES["walk"])
            inside.append(
                {
                    "from": g["to_cell"],
                    "npc": n["key"],
                    "cell": n["cell"],
                    "role": n["role"],
                    "reachable": path is not None,
                    "via": [(e["from"], e["cell"], e["to"], e["to_cell"]) for e in path or []],
                }
            )
    return {
        "hub": hub["key"],
        "candidate_maps": sorted(cand),
        "trips": trips,
        "home_inside": inside,
    }


# --- requirements: job EXP and zeny per kill ---


def job_exp_needed(job_exp_yml: str, job_name: str, level: int) -> int:
    doc = yaml.load(job_exp_yml, Loader=getattr(yaml, "CSafeLoader", yaml.SafeLoader))
    for e in doc["Body"]:
        if (e.get("Jobs") or {}).get(job_name) and "JobExp" in e:
            table = [int(r["Exp"]) for r in sorted(e["JobExp"], key=lambda r: r["Level"])]
            return sum(table[: level - 1])
    raise KeyError(job_name)


def mob_table(mob_db: str) -> dict[int, dict[str, Any]]:
    doc = yaml.load(mob_db, Loader=getattr(yaml, "CSafeLoader", yaml.SafeLoader))
    return {
        int(e["Id"]): {
            "aegis": e.get("AegisName"),
            "name": e.get("Name"),
            "level": e.get("Level", 1),
            "hp": e.get("Hp", 1),
            "base_exp": e.get("BaseExp", 0),
            "job_exp": e.get("JobExp", 0),
            "ai": str(e.get("Ai", "06")).zfill(2),
            "modes": sorted(k for k, v in (e.get("Modes") or {}).items() if v),
            "class": e.get("Class"),  # absent = the default class
        }
        for e in doc["Body"]
    }


def exp_rates(exp_conf: str) -> dict[str, int]:
    conf = kb_build.parse_battle_conf(exp_conf)
    return {k: int(conf.get(k, "100")) for k in ("base_exp_rate", "job_exp_rate")}


def kill_math(
    spawns: Sequence[dict[str, Any]],
    mobs: dict[int, dict[str, Any]],
    need_job: int,
    rate: int,
    zeny_per_kill: dict[int, float],
    ai_bits: dict[str, int],
) -> dict[str, Any]:
    """Per map: the species, their job EXP, the population-weighted job EXP and zeny per kill, and
    the kills to the job-level target and to 1,000 zeny. Assumes kills in spawn proportion."""
    pop: dict[int, int] = defaultdict(int)
    for s in spawns:
        pop[s["id"]] += s["amount"]
    n = sum(pop.values())
    if not n:
        return {}
    jexp = sum(mobs[i]["job_exp"] * a for i, a in pop.items()) * rate / 100 / n
    zeny = sum(zeny_per_kill.get(i, 0.0) * a for i, a in pop.items()) / n
    species = {}
    for i, a in sorted(pop.items()):
        mb = mobs[i]
        bits = ai_bits.get(mb["ai"], 0)
        species[str(i)] = {
            "amount": a,
            "level": mb["level"],
            "hp": mb["hp"],
            "base_exp": mb["base_exp"],
            "job_exp": mb["job_exp"],
            "ai": mb["ai"],
            "aggressive": bool(bits & 0x4) or "Aggressive" in mb["modes"],
            "looter": bool(bits & 0x2),
            "assist": bool(bits & 0x8),
            "zeny_per_kill": round(zeny_per_kill.get(i, 0.0), 2),
        }
    return {
        "population": n,
        "species": species,
        "job_exp_per_kill": round(jexp, 2),
        "kills_to_job_target": round(need_job / jexp) if jexp else None,
        "zeny_per_kill": round(zeny, 2),
        "kills_to_1000_zeny": round(1000 / zeny) if zeny else None,
    }


def zeny_table(kb: Path) -> dict[int, float]:
    """Expected NPC-sell zeny per kill from the local KB (kb_build: drops.json at the server's
    effective rates, items.json). A missing sell price is Buy / 2 (rAthena's item_db default)."""
    try:
        drops = json.loads((kb / "drops.json").read_text())
        items = json.loads((kb / "items.json").read_text())
    except OSError:
        return {}
    out: dict[int, float] = {}
    for mid, rows in drops.items():
        z = 0.0
        for d in rows:
            if d.get("mvp") or d.get("item_id") is None:
                continue
            it = items.get(str(d["item_id"])) or {}
            sell = it.get("sell")
            if sell is None:
                sell = (it.get("buy") or 0) // 2
            rate = d["rate_effective"] if d["rate_effective"] is not None else d["rate"]
            z += min(rate, 10000) / 10000 * sell
        out[int(mid)] = z
    return out


# --- completeness ---

# Script commands that PLACE something on a map at run time (a unit, an NPC move, a cell change):
# any on a scope map must be in the KB as dynamic. (warp / areawarp / mapwarp move players only.)
PLACING = frozenset(
    {
        "monster",
        "areamonster",
        "movenpc",
        "setcell",
        "setwall",
        "duplicate_dynamic",
        "bg_monster",
        "guardian",
    }
)
TEXT_CMDS = frozenset(
    {
        "mes",
        "select",
        "prompt",
        "menu",
        "npctalk",
        "dispbottom",
        "announce",
        "mapannounce",
        "message",
        "input",
    }
)


def mentions(
    w: World, read: Any, maps: Sequence[str], not_loaded: Sequence[str] = (), read_other: Any = None
) -> dict[str, Any]:
    """Every line of every LOADED file that names a scope map, accounted for: a comment, a
    top-level definition (placing on it, or a warp line to it), or a script statement classified
    by its command. Placement commands in scripts are listed (they must be in the KB as dynamic).
    The files the server does NOT load are only listed when they name a scope map."""
    header: dict[tuple[str, int], Rec] = {(r.file, r.line): r for r in w.recs}
    names = sorted(maps, key=len, reverse=True)
    big = re.compile(r"(?<![\w-])(" + "|".join(map(re.escape, names)) + r")(?![\w-])")
    pats = {m: re.compile(TOKEN.format(re.escape(m))) for m in maps}
    counts: dict[str, Counter[str]] = {m: Counter() for m in maps}
    files: dict[str, set[str]] = defaultdict(set)
    unclassified: list[dict[str, Any]] = []
    placing: list[dict[str, Any]] = []
    for f in w.files:
        raw = read(f).replace("\r\n", "\n")
        found = {(raw.count("\n", 0, mt.start()) + 1, mt[1]) for mt in big.finditer(raw)}
        if not found:
            continue
        lines = raw.split("\n")
        masked_lines = mask_comments(raw).split("\n")
        for no, m in sorted(found):
            files[m].add(f)
            p = pats[m]
            masked = masked_lines[no - 1]
            if not p.search(masked):
                counts[m]["comment"] += 1
                continue
            r = header.get((f, no))
            if r is not None and r.map == m:
                counts[m][f"defines_{r.type}"] += 1
                continue
            if r is not None and r.type == "warp" and warp_entry(r)["to_map"] == m:
                counts[m]["warp_line_to"] += 1
                continue
            if r is not None:  # another map's definition that names it (a name, a shop list)
                counts[m]["named_in_other_header"] += 1
                continue
            cmd = _statement_command(masked, p)
            counts[m][f"script_{cmd}"] += 1
            if cmd in PLACING:
                placing.append({"map": m, "at": f"{f}:{no}", "command": cmd})
            if cmd == "other":
                unclassified.append({"map": m, "at": f"{f}:{no}", "line": lines[no - 1].strip()})
    other: dict[str, set[str]] = defaultdict(set)
    for f in not_loaded:
        try:
            raw = (read_other or read)(f)
        except OSError:
            continue
        for m in set(big.findall(raw)):
            other[m].add(f)
    return {
        "counts": {m: dict(c) for m, c in counts.items()},
        "files": {m: sorted(v) for m, v in files.items()},
        "script_placements": placing,
        "unclassified": unclassified,
        "not_loaded_files_naming": {m: sorted(v) for m, v in other.items()},
    }


def _statement_command(line: str, p: re.Pattern[str]) -> str:
    """The command whose argument names the map on this (comment-masked) line: `warp`,
    `savepoint`, `monster`, ...; `condition` for a comparison; `text` inside a dialog / menu
    string; `array` inside a setarray; else the line's leading word, or `other`."""
    m = p.search(line)
    assert m is not None
    before, after = line[: m.start()], line[m.end() :]
    if re.search(r'(==|!=)\s*"?\s*$', before) or re.match(r'\s*"?\s*(==|!=)', after):
        return "condition"
    lead_m = re.match(
        r"\s*(?:\}\s*)?(?:(?:case\s+[^:;]+|default)\s*:\s*)?(?:else\s*)?"
        r"(?:if\s*\(.*?\)\s*)?([A-Za-z_]\w*)",
        line,
    )
    lead = lead_m[1] if lead_m else ""
    if before.count('"') % 2 == 1:  # the map name is inside a string
        call = re.search(r'([A-Za-z_]\w*)\s*\(?\s*"[^"]*$', before)
        name = call[1] if call else lead
        if name in TEXT_CMDS or lead in TEXT_CMDS:
            return "text"
        if lead == "setarray":
            return "array"
        return name or "other"
    return lead or "other"


# --- build ---


def build(
    src: Src, kb: Path, mapcache_dir: Path | None = None, also: Sequence[str] = ()
) -> dict[str, Any]:
    """The KB. `also`: extra maps to extract the same way (e.g. a packet-checked map such as
    prt_church for the NPC-click test's P1); they are listed apart and join no budget block."""
    t0 = time.time()
    w = build_world(src)
    seeds = [s[0] for s in start_points(src.read(CHAR_CONF))]
    tg = grounds(w, seeds)
    quest = job_quest(w)
    changer_maps = {n["map"] for n in quest["npcs"] if n["role"] == "job_change"}
    grad = [e for e in tg["exits"] if e.get("to") in changer_maps]
    home = grad[0]["to"] if grad else (quest["maps"][0] if quest["maps"] else None)
    savehome = grad[0]["savepoint"][0] if grad and grad[0]["savepoint"] else None
    edges = all_edges(w)
    _, kafra = kafra_edges(w)
    stops = [m for m in quest["maps"] if m != home]
    map_level = legs(edges, home, stops) if home else {}
    grids = _grids(mapcache_dir)
    rt = room_trips(edges, map_level, quest, home, grad, grids) if home else {}
    travel = rt.get("trips", {})
    mobs = mob_table(src.read(MOB_DB))
    import kb_route

    ai_bits = kb_route.ai_modes(src.ref)
    need = job_exp_needed(src.read(JOB_EXP), NOVICE_ENUM.removeprefix("JOB_").title(), 10)
    rates = exp_rates(src.read(EXP_CONF))
    zeny = zeny_table(kb)
    path_maps: list[str] = []  # per stop: the fewest-changes route and the least-zeny one
    for row in travel.values():
        for pol in ("walk_kafra", "walk_kafra_transport", "walk_kafra_npc"):
            if row.get(pol):
                path_maps += row[pol]["maps"]
                break
        if row.get("least_zeny"):
            path_maps += row["least_zeny"]["maps"]
    maps = list(
        dict.fromkeys(
            tg["maps"]
            + tg["unreachable"]
            + quest["maps"]
            + ([savehome] if savehome else [])
            + path_maps
        )
    )
    also = [m for m in also if m not in maps]
    maps += also
    per_map = {m: map_entry(m, w) for m in maps}
    for m in maps:
        km = kill_math(per_map[m]["spawns"], mobs, need, rates["job_exp_rate"], zeny, ai_bits)
        if km:
            per_map[m]["kill_math"] = km
    not_loaded = _not_loaded(src, set(w.files))
    complete = mentions(
        w,
        src.read,
        maps,
        not_loaded,
        read_other=lambda f: (src.root / f).read_bytes().decode("latin-1"),
    )
    clones = _clone_groups(maps, mapcache_dir)

    return {
        "rathena_ref": src.ref,
        "mode": "pre-re",
        "built_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "generator": "scripts/kb_first_workflow.py",
        "sources": {
            "entry": ENTRY,
            "loaded_files": len(w.files),
            "files": w.files,
            "problems": w.problems,
            "inputs": dict(sorted(src.hashes.items())),
        },
        "scope": {
            "training_grounds": tg,
            "merchant": {
                **quest,
                "graduation": grad,
                "home": home,
                "savepoint_town": savehome,
                "requirements": requirement_checks(w, quest),
                "travel": travel,
                "travel_map_level": map_level,
                "hub": rt.get("hub"),
                "home_inside": rt.get("home_inside"),
                "travel_candidate_maps": rt.get("candidate_maps"),
                "kafra": kafra,
            },
            "maps": maps,
            "also": also,
        },
        "requirements": {
            "novice_job_level": 10,
            "job_exp_needed": need,
            "exp_rates": rates,
            "start_points": seeds,
            "zeny_source": str(kb) if zeny else None,
        },
        "maps": per_map,
        "clone_groups": clones,
        "completeness": complete,
        "seconds": round(time.time() - t0, 1),
    }


def _not_loaded(src: Src, loaded: set[str]) -> list[str]:
    """Script files under npc/ that the server does NOT load (the renewal tree, tests, customs):
    read only to report that they name a scope map. git-free listing inside the extracted tree."""
    base = src.root / "npc"
    if not base.is_dir():
        return []
    out = []
    for p in sorted(base.rglob("*.txt")):  # the extracted tree is in tmpfs (guard_walk allows it)
        rel = p.relative_to(src.root).as_posix()
        if rel not in loaded:
            out.append(rel)
    return out


def _grids(directory: Path | None) -> Any:
    try:
        from poring_dataset import mapcache

        return mapcache.load(directory) if directory else mapcache.load()
    except Exception:  # noqa: BLE001 -- optional: reported, never fatal
        return None


def _clone_groups(maps: Sequence[str], directory: Path | None = None) -> list[dict[str, Any]]:
    """Maps whose server walkability grids are byte-identical (poring_dataset.mapcache)."""
    try:
        from poring_dataset import mapcache

        grids = mapcache.load(directory) if directory else mapcache.load()
    except Exception as e:  # noqa: BLE001 -- optional: reported, never fatal
        return [{"error": str(e)}]
    groups: dict[str, list[str]] = defaultdict(list)
    for m in maps:
        g = grids.get(m)
        if g is not None:
            groups[hashlib.sha256(g.cells + f"{g.xs}x{g.ys}".encode()).hexdigest()[:12]].append(m)
    return [{"cells_sha": k, "maps": v} for k, v in groups.items() if len(v) > 1]


# --- summary: ids, cells, counts (what a committed doc may quote) ---


def summary(doc: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {
        "ref": doc["rathena_ref"][:10],
        "loaded_files": doc["sources"]["loaded_files"],
        "problems": len(doc["sources"]["problems"]),
    }
    tg = doc["scope"]["training_grounds"]
    out["training_grounds"] = {
        "seeds": tg["seeds"],
        "maps": tg["maps"],
        "unreachable": tg["unreachable"],
        "edges": [
            (e["from"], e["via"], e.get("cell") or e.get("key"), e["to"], e["to_cell"])
            for e in tg["edges"]
        ],
        "exits": [
            (e["from"], e["key"], e.get("to"), e.get("to_cell"), e.get("savepoint"))
            for e in tg["exits"]
        ],
    }
    maps = {}
    for m, e in doc["maps"].items():
        kinds = Counter(n["kind"] for n in e["npcs"])
        drawn = sorted({n["sprite"] for n in e["npcs"] if n["drawn"] is True})
        maps[m] = {
            "warps": [
                (
                    x["x"],
                    x["y"],
                    x["span_x"],
                    x["span_y"],
                    x["to_map"],
                    x["to_x"],
                    x["to_y"],
                    x["kind"],
                    x["drawn"],
                )
                for x in e["warps"]
            ],
            "spawns": [
                (
                    s["id"],
                    s["amount"],
                    s["x"],
                    s["y"],
                    s["xs"],
                    s["ys"],
                    s["delay1_ms"],
                    s["delay2_ms"],
                )
                for s in e["spawns"]
            ],
            "npc_kinds": dict(kinds),
            "drawn_sprites": drawn,
            "npcs": [
                (n["key"], n["kind"], n["sprite"], n["x"], n["y"], n["dir"], n["drawn"])
                for n in e["npcs"]
            ],
            "mapflags": sorted({f["flag"] for f in e["mapflags"]}),
            "kill_math": {k: v for k, v in e.get("kill_math", {}).items() if k != "species"},
            "species": e.get("kill_math", {}).get("species"),
        }
    out["maps"] = maps
    mq = doc["scope"]["merchant"]
    out["merchant"] = {
        "files": mq["files"],
        "functions": mq["functions"],
        "maps": mq["maps"],
        "variables": mq["variables"],
        "home": mq["home"],
        "savepoint_town": mq["savepoint_town"],
        "npcs": [
            (n["key"], n["map"], n["cell"], n["role"], n["tests"], n["zeny_tests"])
            for n in mq["npcs"]
        ],
        "graduation": [
            (g["from"], g["key"], g["to"], g["to_cell"], g["savepoint"]) for g in mq["graduation"]
        ],
        "requirements": mq["requirements"],
        "kafra": mq["kafra"],
        "hub": mq["hub"],
        "home_inside": mq["home_inside"],
        "travel": {
            stop: {
                pol: (
                    None
                    if r is None
                    else {
                        "maps": r["maps"],
                        "hops": r["hops"],
                        "kafra_hops": r["kafra_hops"],
                        "zeny_listed": r["zeny_listed"],
                        "zeny_with_tickets": r["zeny_with_tickets"],
                        "map_changes": r.get("map_changes"),
                        "fee_unknown": r.get("fee_unknown"),
                        "legs": [
                            (e["from"], e["via"], e.get("cell") or e["key"], e["to"], e["to_cell"])
                            for e in r["go"] + r["back"]
                        ],
                    }
                )
                for pol, r in row.items()
            }
            for stop, row in mq["travel"].items()
        },
    }
    out["requirements"] = doc["requirements"]
    out["clone_groups"] = doc["clone_groups"]
    c = doc["completeness"]
    out["completeness"] = {
        "counts": c["counts"],
        "script_placements": c["script_placements"],
        "unclassified": c["unclassified"],
        "files": c["files"],
        "not_loaded_files_naming": {m: len(v) for m, v in c["not_loaded_files_naming"].items()},
    }
    return out


# --- the packet check ---


def packet_npcs(session: Path) -> list[dict[str, Any]]:
    """Every NPC object (objtype 6) the server showed in a banked session, with the map it was on
    (the session's last map_change). Names are not returned."""
    out = []
    current: str | None = None
    p = session / "packets.jsonl.gz"
    if not p.exists():
        return out
    with gzip.open(p, "rt") as f:
        for line in f:
            if '"map_change"' not in line and '"objtype": 6' not in line:
                continue
            r = json.loads(line)
            if r.get("type") == "map_change":
                current = str(r["map"]).split(".")[0]
            elif r.get("type") == "entity_appear" and r.get("objtype") == 6 and current:
                out.append(
                    {
                        "map": current,
                        "x": r["x"],
                        "y": r["y"],
                        "job": r["job"],
                        "effect_state": r.get("effect_state", 0),
                        "gid": r.get("gid"),
                    }
                )
    return out


def check_packets(doc: dict[str, Any], sessions: Sequence[Path]) -> dict[str, Any]:
    """Every NPC the server showed on a scope map must be in the KB at that cell with that sprite.
    Server-side duplicates of the same object (gid) count once."""
    seen: dict[tuple[str, int, int, int], set[int]] = defaultdict(set)
    sess_maps: Counter[str] = Counter()
    for s in sessions:
        rows = packet_npcs(s)
        for m in {r["map"] for r in rows}:
            sess_maps[m] += 1
        for r in rows:
            if r["map"] in doc["maps"]:
                seen[(r["map"], r["x"], r["y"], r["job"])].add(int(r["effect_state"] or 0))
    kb: dict[tuple[str, int, int], list[dict[str, Any]]] = defaultdict(list)
    for m, e in doc["maps"].items():
        for n in e["npcs"]:
            kb[(m, n["x"], n["y"])].append({"sprite": n["sprite"], "key": n["key"]})
        for x in e["warps"]:
            kb[(m, x["x"], x["y"])].append({"sprite": 45, "key": x["key"]})
    matched, mismatched, missing = [], [], []
    for (m, x, y, job), effects in sorted(seen.items()):
        here = kb.get((m, x, y), [])
        if any(h["sprite"] == job for h in here):
            matched.append((m, x, y, job))
        elif here:
            mismatched.append(
                {"map": m, "cell": [x, y], "packet_job": job, "kb": [h["sprite"] for h in here]}
            )
        else:
            missing.append({"map": m, "cell": [x, y], "job": job, "effect_state": sorted(effects)})
    per_map = Counter(m for m, *_ in matched)
    return {
        "sessions": len(sessions),
        "maps_in_sessions": dict(sess_maps),
        "objects": len(seen),
        "matched": len(matched),
        "matched_per_map": dict(per_map),
        "mismatched": mismatched,
        "missing_from_kb": missing,
    }


# --- npc_cells.json (npc_noclick / npc_click_test's L3 list; npc-click-test.md 5.1 P1) ---

HIDDEN_OPTIONS = 0x2 | 0x4 | 0x40  # poring_packets.world: HIDE, CLOAK, INVISIBLE (sent, not drawn)
NPC_CELLS = ROOT / "data" / "kb" / "npc_cells.json"


def _file_line(key: str) -> tuple[str, int | None]:
    file, _, line = key.rpartition(":")
    return (file, int(line)) if line.isdigit() else (key, None)


def map_complete(doc: dict[str, Any], m: str) -> bool:
    """A map's NPC list is COMPLETE when the server loads it, every file line naming it was
    classified, and no script places anything on it at run time (the build's completeness)."""
    c = doc.get("completeness", {})
    rec = doc["maps"].get(m, {})
    if not rec.get("loaded_by_server") or m not in c.get("counts", {}):
        return False
    unclassified = [u for u in c.get("unclassified", []) if m in json.dumps(u)]
    placements = [p for p in c.get("script_placements", []) if m in json.dumps(p)]
    return not unclassified and not placements


def npc_cells(doc: dict[str, Any], check: dict[str, Any] | None = None) -> dict[str, Any]:
    """The KB's NPCs per map in npc_noclick's format, each MARKED drawn / not: ``drawn`` is the
    KB's (True, False, or "conditional": the script hides itself at start, e.g. prt_church's
    wedding row, sent with an invisibility option). ``probe`` is True only for an NPC the client
    always draws with its own sprite (the probe plan's candidates)."""
    out: dict[str, Any] = {}
    for m, rec in doc["maps"].items():
        rows = []
        for n in rec.get("npcs", []):
            file, line = _file_line(n["key"])
            drawn = n.get("drawn")
            rows.append({
                "x": n["x"], "y": n["y"], "file": file, "line": line, "sprite": n["sprite"],
                "sprite_class": n.get("sprite_class"), "kind": n.get("kind"), "drawn": drawn,
                "probe": drawn is True and n.get("sprite_class") == "npc"
                and n.get("kind") != "warp_portal",
            })  # fmt: skip
        block: dict[str, Any] = {"complete": map_complete(doc, m), "npcs": rows}
        if check is not None:
            block["packet_check"] = check.get(m)
        out[m] = block
    return {
        "generator": "scripts/kb_first_workflow.py npc-cells",
        "kb_built_at": doc.get("built_at"),
        "rathena_ref": doc.get("rathena_ref"),
        "rule": "complete = every loaded file parsed, every line naming the map classified, no "
        "run-time placement; drawn: True / False / 'conditional' (hidden at start)",
        "maps": out,
    }


def packet_check_per_map(doc: dict[str, Any], sessions: Sequence[Path]) -> dict[str, Any]:
    """P1's check per map: every NPC object the server showed is in the list at its cell with its
    sprite, and the DRAWN marks agree with the packets: an object sent with an invisibility option
    must not be marked drawn=True; one sent without it must not be marked drawn=False."""
    seen: dict[tuple[str, int, int, int], set[int]] = defaultdict(set)
    for s in sessions:
        for r in packet_npcs(s):
            if r["map"] in doc["maps"]:
                seen[(r["map"], r["x"], r["y"], r["job"])].add(int(r["effect_state"] or 0))
    kb: dict[tuple[str, int, int], list[dict[str, Any]]] = defaultdict(list)
    for m, e in doc["maps"].items():
        for n in e["npcs"]:
            kb[(m, n["x"], n["y"])].append({"sprite": n["sprite"], "drawn": n.get("drawn")})
        for x in e["warps"]:
            kb[(m, x["x"], x["y"])].append({"sprite": 45, "drawn": x.get("drawn", True)})
    per: dict[str, dict[str, Any]] = {}
    for (m, x, y, job), effects in sorted(seen.items()):
        row = per.setdefault(m, {"objects": 0, "matched": 0, "hidden_sent": 0, "missing": [],
                                 "wrong_sprite": [], "drawn_disagrees": []})  # fmt: skip
        row["objects"] += 1
        here = [h for h in kb.get((m, x, y), []) if h["sprite"] == job]
        hidden = any(e & HIDDEN_OPTIONS for e in effects)
        shown = any(not e & HIDDEN_OPTIONS for e in effects)
        row["hidden_sent"] += int(hidden)
        if not here:
            other = [h["sprite"] for h in kb.get((m, x, y), [])]
            (row["wrong_sprite"] if other else row["missing"]).append([x, y, job])
            continue
        row["matched"] += 1
        marks = {h["drawn"] for h in here}
        if (hidden and not shown and True in marks) or (shown and not hidden and False in marks):
            row["drawn_disagrees"].append([x, y, job, sorted(effects)])
    for row in per.values():
        row["pass"] = row["matched"] == row["objects"] and not row["drawn_disagrees"]
    return per


# --- budget ---


def budget(doc: dict[str, Any], kb: Path, blocks: dict[str, list[str]]) -> dict[str, Any]:
    """training-cost.md's estimate (poring_flow.prep.estimate) per block, NEW species and NEW maps
    only, in block order; species = every spawn on the block's maps plus metamorphosis
    (kb_build.classes_for), difficulty = labels_v2.difficulty, trained = labels_v2.TRAINED.
    Also per block: the drawn NPC sprites first met in it (player-class ones are composites), the
    drawn portal cells on its new maps, and the map prep if a clone group (identical server
    walkability) counted as one map."""
    import labels_v2

    from poring_flow.prep import estimate

    skills = {int(k): v for k, v in json.loads((kb / "mob_skills.json").read_text()).items()}
    mobs = {int(k): v for k, v in json.loads((kb / "mobs.json").read_text()).items()}
    clone_of = {
        m: g["maps"][0] for g in doc.get("clone_groups", []) if "maps" in g for m in g["maps"]
    }
    seen_s: set[int] = set(labels_v2.TRAINED)
    seen_m: set[str] = set(labels_v2.PREPARED_MAPS)
    seen_sprites: set[int] = set()
    rows = []
    for name, maps in blocks.items():
        spawns = {m: doc["maps"][m]["spawns"] for m in maps if m in doc["maps"]}
        classes = kb_build.classes_for(list(maps), spawns, skills, mobs)
        new: dict[int, str] = {}
        trained: set[int] = set()
        for m in maps:
            bosses = {s["id"] for s in spawns.get(m, []) if s["boss"]}
            for mid_s in classes.get(m, {}):
                mid = int(mid_s)
                if mid in seen_s:
                    trained.add(mid)
                elif mid not in new:
                    new[mid] = labels_v2.difficulty(mobs.get(mid), mid in bosses)
        new_maps = [m for m in maps if m not in seen_m]
        est = estimate(new, new_maps)
        layouts = sorted({clone_of.get(m, m) for m in new_maps})
        est_layouts = estimate(new, layouts)
        seen_s |= set(new)
        seen_m |= set(new_maps)
        npcs = [
            n
            for m in maps
            for n in doc["maps"].get(m, {}).get("npcs", [])
            if n["drawn"] is True and n["kind"] != "warp_portal"
        ]
        sprites = sorted({n["sprite"] for n in npcs} - seen_sprites)
        player = sorted(
            {n["sprite"] for n in npcs if n["sprite_class"] == "player_job"} & set(sprites)
        )
        seen_sprites |= set(sprites)
        portals = sum(
            1 for m in new_maps for x in doc["maps"].get(m, {}).get("warps", []) if x["drawn"]
        )
        portals += sum(
            1
            for m in new_maps
            for n in doc["maps"].get(m, {}).get("npcs", [])
            if n["kind"] == "warp_portal" and n["drawn"] is True
        )
        rows.append(
            {
                "block": name,
                "maps": list(maps),
                "new_maps": new_maps,
                "new_layouts": layouts,
                "trained_species": sorted(trained),
                "new_species": {str(k): v for k, v in sorted(new.items())},
                "sum_d": est.sum_d,
                "map_prep_h": round(est.map_prep_h, 2),
                "map_prep_h_clones_once": round(est_layouts.map_prep_h, 2),
                "collect_s2_h": round(est.collect_s2_h, 2),
                "train_compute_h": round(est.train_compute_h, 2),
                "wall_h": {k: round(v, 1) for k, v in est.wall_h.items()},
                "npc_sprites_new": sprites,
                "npc_sprites_player_class": player,
                "portals_drawn_new_maps": portals,
            }
        )
    keys = ("sum_d", "map_prep_h", "map_prep_h_clones_once", "collect_s2_h", "train_compute_h")
    total = {k: round(sum(float(r[k]) for r in rows), 2) for k in keys}
    total["npc_sprites"] = len(seen_sprites)
    total["new_species"] = sum(len(r["new_species"]) for r in rows)
    total["portals_drawn"] = sum(int(r["portals_drawn_new_maps"]) for r in rows)
    return {"blocks": rows, "total": total}


# --- CLI ---


def _write(path: Path, doc: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.part")
    tmp.write_text(json.dumps(doc, indent=1, ensure_ascii=False, default=list) + "\n")
    tmp.replace(path)
    json.loads(path.read_text())  # read back


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("build")
    p.add_argument("--src", type=Path, default=SRC)
    p.add_argument("--out", type=Path, default=OUT)
    p.add_argument(
        "--kb-dir",
        type=Path,
        default=ROOT / "data" / "kb",
        help="the local KB (kb_build): drops.json, items.json",
    )
    p.add_argument(
        "--also",
        nargs="*",
        default=[],
        help="extra maps to extract the same way (not part of the workflow's scope)",
    )
    p.add_argument(
        "--mapcache-dir",
        type=Path,
        default=None,
        help="poring_dataset's _generated map caches (clone groups)",
    )
    q = sub.add_parser("npc-cells", help="data/kb/npc_cells.json (npc-click-test.md 5.1 P1)")
    q.add_argument("--kb", type=Path, default=OUT)
    q.add_argument("--out", type=Path, default=NPC_CELLS)
    q.add_argument("--sessions", nargs="*", type=Path, default=[], help="banked: P1's check")
    for name in ("summary", "budget", "check-packets"):
        q = sub.add_parser(name)
        q.add_argument("--kb", type=Path, default=OUT)
        if name == "budget":
            q.add_argument(
                "--kb-dir",
                type=Path,
                default=ROOT / "data" / "kb",
                help="mobs.json, mob_skills.json",
            )
        if name == "check-packets":
            q.add_argument("sessions", nargs="+", type=Path)
    a = ap.parse_args(argv)
    if a.cmd == "build":
        doc = build(Src(a.src), a.kb_dir, a.mapcache_dir, a.also)
        _write(a.out, doc)
        s = summary(doc)
        print(
            json.dumps(
                {
                    "out": str(a.out),
                    "loaded_files": s["loaded_files"],
                    "problems": s["problems"],
                    "maps": len(doc["maps"]),
                    "seconds": doc["seconds"],
                }
            )
        )
        return 0
    doc = json.loads(a.kb.read_text())
    if a.cmd == "npc-cells":
        check = packet_check_per_map(doc, a.sessions) if a.sessions else None
        cells = npc_cells(doc, check)
        _write(a.out, cells)
        report = {
            m: {"complete": b["complete"], "npcs": len(b["npcs"]),
                "probe": sum(1 for n in b["npcs"] if n["probe"]),
                "not_drawn": sum(1 for n in b["npcs"] if n["drawn"] is not True),
                **({"packet_check": {k: (len(v) if isinstance(v, list) else v)
                                     for k, v in b["packet_check"].items()}}
                   if b.get("packet_check") else {})}
            for m, b in cells["maps"].items()
        }  # fmt: skip
        print(json.dumps({"out": str(a.out), "maps": report}, indent=1))
        failed = [m for m, b in cells["maps"].items()
                  if b.get("packet_check") and not b["packet_check"]["pass"]]  # fmt: skip
        return 1 if failed else 0
    if a.cmd == "summary":
        print(json.dumps(summary(doc), indent=1, default=list))
    elif a.cmd == "check-packets":
        print(json.dumps(check_packets(doc, a.sessions), indent=1))
    elif a.cmd == "budget":
        sc = doc["scope"]
        tg = sc["training_grounds"]["maps"]
        mq = sc["merchant"]
        core = [m for m in [mq["home"], mq["savepoint_town"]] if m]
        blocks = {"training_grounds": tg, "merchant_guild": core}
        for stop, row in mq["travel"].items():
            maps: list[str] = []
            pol = (
                row.get("walk_kafra")
                or row.get("walk_kafra_transport")
                or row.get("walk_kafra_npc")
            )
            for r in (pol, row.get("least_zeny")):
                maps += [m for m in (r or {}).get("maps", []) if m not in core]
            blocks[f"delivery:{stop}"] = list(dict.fromkeys(maps))
        print(json.dumps(budget(doc, a.kb_dir, blocks), indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
