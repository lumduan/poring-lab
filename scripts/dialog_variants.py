#!/usr/bin/env python3
"""The Merchant delivery-dialog classifier's L3 side and its offline checks (labels-v2-plan.md 7.4a;
poring_env.dialog_variant is the reader / classifier).

    dialog_variants.py extract [--src DIR] [--kb data/kb/first_workflow.json]
                               [--out data/kb/merchant_delivery.json]
        L3, LOCAL ONLY: runs the job changer's script (the pinned pre-renewal merchant.txt) for
        every path the script can take after the application (each random destination x each
        random serial) and for the reminder of every variant, and writes the pages the client would
        show, each with the variants that show it. Prints counts only.
    dialog_variants.py coverage [--variants ...] [--glyphs data/ui_anchors/menu_glyphs.npz]
                                [--banked SESSION ...] [--show]
        Which characters of the 8 variants' pages the T3 glyph set lacks (counts per class; the
        characters themselves only with --show, on this host). With --banked, how many of the
        missing ones occur in banked packet-labelled dialog pages (could be cut from banked frames)
        and how many only a new live capture can give.
    dialog_variants.py measure-wrap SESSION [SESSION ...]
        The wrap rule's evidence on banked dialog frames (numbers only): per physical line its ink
        end, and for a wrapped line where its next word would have ended; PASS when one wrap column
        separates every line that fit from every word that did not.
    dialog_variants.py cut SESSION [SESSION ...] [--out data/ui_anchors/dialog_glyphs.npz]
        T3's fit (menu_text.fit_menu_glyphs, unchanged rules) on DIALOG lines of banked sessions:
        each band of a judged frame is labelled by packet truth (its words, counted from its ink
        gaps, are the next words of the page's npc_say lines; a band whose words would span two
        mes lines is skipped; a band in colour -- the serial's digits are only ever blue -- is
        redrawn black first, ``as_black``). Client pixels: a gitignored file, never committed.
        Prints counts only.
    dialog_variants.py selfcheck GLYPHS SESSION [SESSION ...]     sessions NOT used by `cut`
        The reader + classifier on banked dialogs of OTHER NPCs: every banked page is its own
        "destination" (a closed set of every page those sessions show; the set is cut down to the
        pages the glyph set covers). Counts right / wrong / refused per judged frame; PASS = 0
        wrong and >= 1 right. Evidence for the geometry, the wrap rule and the colour-ink path on
        real pixels before any merchant frame exists -- not the merchant proof.
    dialog_variants.py prove SESSION [SESSION ...] [--variants ...] [--glyphs ...] [--templates DIR]
        The LIVE proof, on banked sessions of the merchant dialog (none exist yet: Batt's (a) or
        (b), 7.4a). Frames are labelled by packet truth (ADR-0007): a page is the npc_say lines up
        to its npc_wait / npc_close / npc_menu, its label the L3 page whose lines equal them (a page
        L3 does not know is reported, never guessed). Only frames >= --settle-ms after the page's
        last event and before the next dialog event are judged; the dialog is found by T2.
        Each conversation is read in time order with the classifier's OWN earlier reads as context
        (Conversation), as the workflow would.
        THE BAR (fixed before any live frame exists):
          * 0 WRONG: no frame names a variant or a destination its label does not show;
          * every banked page instance that shows a variant (its serial) is classified as that
            variant on >= 1 of its judged frames, and every page naming a destination as that
            destination; frames refused (variant None) are counted and listed as UNKNOWN, never
            excused as correct;
          * PASS covers only the variants actually banked: the verdict lists them; the workflow
            relies on a variant only after it has passed here.

rAthena is GPL-3.0: the script text and the serial numbers stay in data/kb/ (gitignored) and are
never printed by default (CLAUDE.md rule 4). The interpreter below runs only the statements the job
changer uses (mes, next, close, select, switch, if, set, callsub/return, rand); anything else on an
executed path stops the extract (``unsupported``) rather than guess.
"""

from __future__ import annotations

import argparse
import dataclasses
import gzip
import hashlib
import json
import re
import sys
from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import kb_first_workflow as fw  # noqa: E402

from poring_env import dialog_variant as dv  # noqa: E402
from poring_env import menu_text as mt  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
SRC = fw.SRC
KB = ROOT / "data" / "kb" / "first_workflow.json"
OUT = ROOT / "data" / "kb" / "merchant_delivery.json"
GLYPHS = ROOT / mt.DEFAULT_GLYPHS
TEMPLATES = ROOT / "data" / "ui_anchors" / "npc_dialog"
VARIANT_VAR = "job_merchant_q2"  # the variant the application stores (labels-v2-plan.md 7.4)
STAGE_VAR = "job_merchant_q"  # the test's stage: the reminder shows while it is 1..6
REMIND_STAGE = 2
COLOURED_RUN = re.compile(r"\^(?!000000)[0-9A-Fa-f]{6}([^^]*)")  # text drawn in a colour
NAME = "\x00name\x00"  # strcharinfo(0): a page showing it is dynamic (never a classifier page)
FORMAT_VERSION = 1
SETTLE_MS = 600
DIALOG_END = ("npc_wait", "npc_close", "npc_menu")
WORD_GAP = 4  # blank columns that split words on a dialog band: spaces are 4-6, an ellipsis 3
DIALOG_EVENTS = ("npc_contact", "npc_say", "npc_wait", "npc_menu", "npc_choose",
                 "npc_next_click", "npc_close", "npc_close_click")  # fmt: skip

# --- a tiny interpreter for the job changer's script --------------------------------------------

_TOKEN = re.compile(
    r"""(?P<ws>\s+)|(?P<str>"(?:[^"\\\n]|\\.)*")|(?P<num>\d+)
    |(?P<id>[.@$#']*[A-Za-z_][A-Za-z0-9_]*\$?)
    |(?P<op>\+\+|--|==|!=|<=|>=|&&|\|\||[-+*/%<>!=(){};:,\[\]?])""",
    re.X,
)
Value = int | str
Stmt = tuple[Any, ...]


class Unsupported(Exception):
    pass


class _Stop(Exception):
    pass


class _Break(Exception):
    pass


class _Return(Exception):
    pass


@dataclass(frozen=True)
class NeedRand(Exception):  # noqa: N818 -- control flow, not an error
    key: tuple[int, ...]


def tokenize(code: str) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    pos = 0
    code = fw.mask_comments(code)
    while pos < len(code):
        m = _TOKEN.match(code, pos)
        if m is None:
            raise Unsupported(f"token at offset {pos}")
        kind = m.lastgroup or ""
        if kind != "ws":
            out.append((kind, m.group()))
        pos = m.end()
    return out


def _close_paren(toks: Sequence[tuple[str, str]], i: int) -> int:
    """The index of the ')' (or ']' / '}') matching the opener at i."""
    pairs = {"(": ")", "[": "]", "{": "}"}
    depth = 0
    for j in range(i, len(toks)):
        t = toks[j][1] if toks[j][0] == "op" else ""
        if t in pairs:
            depth += 1
        elif t in pairs.values():
            depth -= 1
            if depth == 0:
                return j
    raise Unsupported(f"unbalanced from token {i}")


def parse_block(toks: Sequence[tuple[str, str]], i: int) -> tuple[list[Stmt], int]:
    """Statements of the block opening at i ('{'); returns them and the index after its '}'."""
    end = _close_paren(toks, i)
    stmts: list[Stmt] = []
    j = i + 1
    while j < end:
        s, j = parse_stmt(toks, j, end)
        stmts.append(s)
    return stmts, end + 1


def parse_stmt(toks: Sequence[tuple[str, str]], i: int, end: int) -> tuple[Stmt, int]:
    kind, t = toks[i]
    if kind == "op" and t == "{":
        body, j = parse_block(toks, i)
        return ("block", body), j
    if kind == "op" and t == ";":
        return ("block", []), i + 1
    if kind == "id" and t in ("if", "while", "for", "switch"):
        close = _close_paren(toks, i + 1)
        head = list(toks[i + 2 : close])
        if t == "switch":
            items: list[Stmt] = []
            bend = _close_paren(toks, close + 1)
            j = close + 2
            while j < bend:
                if toks[j] == ("id", "case"):
                    colon = next(k for k in range(j, bend) if toks[k] == ("op", ":"))
                    items.append(("case", list(toks[j + 1 : colon])))
                    j = colon + 1
                elif toks[j] == ("id", "default") and toks[j + 1] == ("op", ":"):
                    items.append(("default",))
                    j += 2
                else:
                    s, j = parse_stmt(toks, j, bend)
                    items.append(s)
            return ("switch", head, items), bend + 1
        then, j = parse_stmt(toks, close + 1, end)
        if t != "if":
            return ("loop", head, then), j
        other: Stmt | None = None
        if j < end and toks[j] == ("id", "else"):
            other, j = parse_stmt(toks, j + 1, end)
        return ("if", head, then, other), j
    if kind == "id" and i + 1 < end and toks[i + 1] == ("op", ":"):
        return ("label", t), i + 2
    j = i
    depth = 0
    while j < end:
        k, v = toks[j]
        if k == "op" and v in "([{":
            depth += 1
        elif k == "op" and v in ")]}":
            depth -= 1
        elif k == "op" and v == ";" and depth == 0:
            break
        j += 1
    return ("stmt", list(toks[i:j])), j + 1


_BINARY = {"||": 1, "&&": 2, "==": 3, "!=": 3, "<": 4, ">": 4, "<=": 4, ">=": 4,
           "+": 5, "-": 5, "*": 6, "/": 6, "%": 6}  # fmt: skip


def _split_args(toks: Sequence[tuple[str, str]]) -> list[list[tuple[str, str]]]:
    """Comma-separated groups at depth 0."""
    out: list[list[tuple[str, str]]] = [[]]
    depth = 0
    for k, v in toks:
        if k == "op" and v in "([{":
            depth += 1
        elif k == "op" and v in ")]}":
            depth -= 1
        if k == "op" and v == "," and depth == 0:
            out.append([])
        else:
            out[-1].append((k, v))
    return [] if out == [[]] else out


def _unquote(s: str) -> str:
    return re.sub(r"\\(.)", r"\1", s[1:-1])


@dataclass
class Machine:
    """Runs one path through an NPC body. ``rands``: the forced value of each rand() call, keyed by
    its arguments (a missing key raises NeedRand, so the driver can fork every value);
    ``choices``: the menu answers in order."""

    top: list[Stmt]
    env: dict[str, Value]
    choices: list[int]
    rands: dict[tuple[int, ...], int]
    funcs: dict[str, Callable[[list[Value]], Value]] = field(default_factory=dict)
    pages: list[tuple[str, list[str]]] = field(default_factory=list)
    cur: list[str] = field(default_factory=list)
    quests: list[int] = field(default_factory=list)
    args: list[list[Value]] = field(default_factory=list)
    used_choices: int = 0

    def page(self, end: str) -> None:
        if self.cur:
            self.pages.append((end, self.cur))
        self.cur = []

    # expressions
    def expr(self, toks: Sequence[tuple[str, str]]) -> Value:
        val, j = self._expr(list(toks), 0, 0)
        if j != len(toks):
            raise Unsupported(f"trailing tokens in expression: {len(toks) - j}")
        return val

    def _expr(self, t: list[tuple[str, str]], i: int, min_prec: int) -> tuple[Value, int]:
        left, i = self._unary(t, i)
        while i < len(t) and t[i][0] == "op" and _BINARY.get(t[i][1], 0) > min_prec:
            op = t[i][1]
            right, i = self._expr(t, i + 1, _BINARY[op])
            left = self._apply(op, left, right)
        return left, i

    def _apply(self, op: str, a: Value, b: Value) -> Value:
        if op == "&&":
            return int(bool(a) and bool(b))
        if op == "||":
            return int(bool(a) or bool(b))
        if op == "==":
            return int(a == b)
        if op == "!=":
            return int(a != b)
        if op == "+":
            return a + b if isinstance(a, int) and isinstance(b, int) else f"{a}{b}"
        if not (isinstance(a, int) and isinstance(b, int)):
            raise Unsupported(f"operator {op} on text")
        if op == "-":
            return a - b
        if op == "*":
            return a * b
        if op in ("/", "%"):
            return a // b if op == "/" else a % b
        return int({"<": a < b, ">": a > b, "<=": a <= b, ">=": a >= b}[op])

    def _unary(self, t: list[tuple[str, str]], i: int) -> tuple[Value, int]:
        k, v = t[i]
        if k == "op" and v == "!":
            val, j = self._unary(t, i + 1)
            return int(not val), j
        if k == "op" and v == "-":
            val, j = self._unary(t, i + 1)
            if not isinstance(val, int):
                raise Unsupported("unary minus on text")
            return -val, j
        if k == "op" and v == "(":
            close = _close_paren(t, i)
            return self.expr(t[i + 1 : close]), close + 1
        if k == "num":
            return int(v), i + 1
        if k == "str":
            return _unquote(v), i + 1
        if k == "id":
            if i + 1 < len(t) and t[i + 1] == ("op", "("):
                close = _close_paren(t, i + 1)
                return self.call(v, t[i + 2 : close]), close + 1
            return self.var(v), i + 1
        raise Unsupported(f"unexpected token {k}")

    def var(self, name: str) -> Value:
        if name in self.env:
            return self.env[name]
        if name[:1].isupper():  # a script constant (Job_..., SKILL_PERM): its own name
            return name
        return "" if name.endswith("$") else 0

    def call(self, name: str, arg_toks: Sequence[tuple[str, str]]) -> Value:
        groups = _split_args(arg_toks)
        if name == "select":
            if len(groups) == 1:
                self.expr(groups[0])  # the options: evaluated, never shown on the dialog
            self.page("menu")
            if self.used_choices >= len(self.choices):
                raise Unsupported("more menus than scripted answers")
            self.used_choices += 1
            return self.choices[self.used_choices - 1]
        args = [self.expr(g) for g in groups]
        if name == "rand":
            key = tuple(int(a) for a in args)
            if key not in self.rands:
                raise NeedRand(key)
            return self.rands[key]
        if name == "getarg":
            return self.args[-1][int(args[0])]
        if name == "strcharinfo":
            return NAME
        if name in self.funcs:
            return self.funcs[name](args)
        raise Unsupported(f"function {name}")

    # statements
    def run_list(self, stmts: Sequence[Stmt]) -> None:
        for s in stmts:
            self.run(s)

    def run(self, s: Stmt) -> None:
        tag = s[0]
        if tag == "block":
            self.run_list(s[1])
        elif tag == "if":
            if self.expr(s[1]):
                self.run(s[2])
            elif s[3] is not None:
                self.run(s[3])
        elif tag == "switch":
            self.switch(s[1], s[2])
        elif tag == "label":
            pass
        elif tag == "loop":
            raise Unsupported("loop on an executed path")
        elif tag == "stmt":
            self.command(s[1])
        else:
            raise Unsupported(f"statement {tag}")

    def switch(self, head: Sequence[tuple[str, str]], items: Sequence[Stmt]) -> None:
        v = self.expr(head)
        start = next((k for k, it in enumerate(items)
                      if it[0] == "case" and self.expr(it[1]) == v), None)  # fmt: skip
        if start is None:
            start = next((k for k, it in enumerate(items) if it[0] == "default"), None)
        if start is None:
            return
        try:
            for it in items[start:]:
                if it[0] not in ("case", "default"):
                    self.run(it)
        except _Break:
            pass

    def command(self, toks: Sequence[tuple[str, str]]) -> None:  # noqa: C901
        if not toks:
            return
        k, name = toks[0]
        rest = list(toks[1:])
        if k != "id":
            raise Unsupported("statement without a command")
        if rest and rest[0] == ("op", "="):
            self.env[name] = self.expr(rest[1:])
        elif name == "mes":
            self.cur.append(str(self.expr(rest)))
        elif name == "next":
            self.page("next")
        elif name in ("close", "end"):
            self.page(name)
            raise _Stop
        elif name == "break":
            raise _Break
        elif name == "return":
            raise _Return
        elif name == "set":
            groups = _split_args(rest)
            if len(groups) != 2 or len(groups[0]) != 1 or groups[0][0][0] != "id":
                raise Unsupported("set form")
            self.env[groups[0][0][1]] = self.expr(groups[1])
        elif name == "setquest":
            self.quests.append(int(self.expr(rest)))
        elif name == "callsub":
            groups = _split_args(rest)
            label = groups[0][0][1]
            at = next((i for i, s in enumerate(self.top) if s == ("label", label)), None)
            if at is None:
                raise Unsupported(f"no label {label}")
            self.args.append([self.expr(g) for g in groups[1:]])
            try:
                self.run_list(self.top[at + 1 :])
                raise Unsupported(f"{label} fell off the end")
            except _Return:
                pass
            finally:
                self.args.pop()
        elif name in ("input", "menu", "warp"):
            raise Unsupported(f"{name} on an executed path")
        # anything else (getitem, skill, jobchange, completequest, callfunc as a statement, ...)
        # changes no dialog text: a no-op here


def run_paths(top: list[Stmt], env: dict[str, Value], choices: list[int],
              funcs: dict[str, Callable[[list[Value]], Value]]) -> list[Machine]:  # fmt: skip
    """Every path of the script under every value of every rand() it calls (forked on demand)."""
    done: list[Machine] = []
    todo: list[dict[tuple[int, ...], int]] = [{}]
    while todo:
        rands = todo.pop(0)
        m = Machine(top, dict(env), list(choices), dict(rands), dict(funcs))
        try:
            m.run_list(top)
            m.page("end")
        except _Stop:
            pass
        except NeedRand as need:
            lo, hi = (0, need.key[0] - 1) if len(need.key) == 1 else (need.key[0], need.key[1])
            todo += [{**rands, need.key: v} for v in range(lo, hi + 1)]
            continue
        done.append(m)
    return done


# --- the extract --------------------------------------------------------------------------------


def job_changer(kb: dict[str, Any]) -> tuple[str, int]:
    rows = [n for n in kb["scope"]["merchant"]["npcs"] if n["role"] == "job_change"]
    if len(rows) != 1:
        raise SystemExit(f"expected one job changer in the KB, found {len(rows)}")
    file, line = rows[0]["key"].rsplit(":", 1)
    return file, int(line)


def destinations(kb: dict[str, Any], home: str) -> dict[int, str]:
    """Variant value -> the map of the ONE delivery NPC (off the home map) that tests it."""
    out: dict[int, str] = {}
    for n in kb["scope"]["merchant"]["npcs"]:
        if n["map"] == home:
            continue
        for v in n.get("tests", {}).get(VARIANT_VAR, []):
            if v in out and out[v] != n["map"]:
                raise SystemExit(f"two delivery NPCs test {VARIANT_VAR} == {v}")
            out[int(v)] = n["map"]
    return out


def npc_body(text: str, file: str, line: int) -> str:
    recs, _ = fw.parse_file(text, file)
    rec = next((r for r in recs if r.line == line), None)
    if rec is None or rec.body is None:
        raise SystemExit(f"{file}:{line}: no script body")
    return rec.body


def _page_id(role: str, lines: Sequence[str]) -> str:
    h = hashlib.sha256("\n".join(lines).encode()).hexdigest()[:8]
    return f"{role}-{h}"


def extract(body: str, dest_of: dict[int, str]) -> dict[str, Any]:
    """The pages of the application paths and of every variant's reminder (see module doc)."""
    top, _ = parse_block(tokenize(body), 0)
    base: dict[str, Value] = {"Upper": 0, "BaseJob": "Job_Novice", "Class": "Job_Novice",
                              "Zeny": 1000, STAGE_VAR: 0, VARIANT_VAR: 0}  # fmt: skip
    funcs: dict[str, Callable[[list[Value]], Value]] = {"callfunc": lambda a: 1}
    # the application: be a Merchant (1), yes (1), pay in full (1)
    runs = run_paths(top, base, [1, 1, 1], funcs)
    variants: dict[str, dict[str, Any]] = {}
    pages: dict[tuple[str, ...], dict[str, Any]] = {}
    problems: list[str] = []

    def add(role: str, vid: str, seq: list[tuple[str, list[str]]]) -> None:
        for _end, lines in seq:
            if any(NAME in x for x in lines):
                continue  # shows the character's name: dynamic
            key = tuple(lines)
            row = pages.setdefault(key, {"id": _page_id(role, lines), "roles": [], "variants": []})
            if role not in row["roles"]:
                row["roles"].append(role)
            if vid not in row["variants"]:
                row["variants"].append(vid)

    found: list[tuple[int, str, Machine]] = []
    for m in runs:
        value = m.env.get(VARIANT_VAR, 0)
        if not isinstance(value, int) or value == 0 or m.used_choices != 3:
            problems.append("an application path set no variant")
            continue
        dest = dest_of.get(value)
        if dest is None:
            problems.append(f"no delivery NPC tests {VARIANT_VAR} == {value}")
            continue
        found.append((value, dest, m))
    for value, dest, m in sorted(found, key=lambda r: r[0]):
        slot = 1 + sum(1 for v, d, _ in found if d == dest and v < value)  # by variant value
        vid = f"{dest}/{slot}"
        if vid in variants:
            problems.append(f"{vid}: two application paths set {VARIANT_VAR} == {value}")
            continue
        coloured = sorted({run for _, ls in m.pages for x in ls
                           for run in COLOURED_RUN.findall(x)})  # fmt: skip
        variants[vid] = {"value": value, "destination": dest, "slot": slot,
                         "quest": m.quests[-1] if m.quests else None,
                         "coloured": coloured}  # fmt: skip
        add("assign", vid, m.pages)
    for vid, row in variants.items():
        env = {**base, STAGE_VAR: REMIND_STAGE, VARIANT_VAR: row["value"]}
        rem = run_paths(top, env, [], funcs)
        if len(rem) != 1:
            problems.append(f"{vid}: the reminder forks ({len(rem)} paths)")
            continue
        add("remind", vid, rem[0].pages)
    out_pages = [{"id": r["id"], "roles": r["roles"], "variants": sorted(r["variants"]),
                  "lines": list(k)} for k, r in pages.items()]  # fmt: skip
    return {"version": FORMAT_VERSION, "variants": dict(sorted(variants.items())),
            "pages": out_pages, "problems": problems}  # fmt: skip


def expected_pages(doc: dict[str, Any]) -> list[dv.ExpectedPage]:
    return [dv.ExpectedPage(p["id"], frozenset(p["variants"]), tuple(p["lines"]))
            for p in doc["pages"]]  # fmt: skip


def summary(doc: dict[str, Any]) -> dict[str, Any]:
    """Counts only (no script text, no serial)."""
    n_var = len(doc["variants"])
    kinds = {"variant": 0, "destination": 0, "generic": 0}
    for p in doc["pages"]:
        dests = {v.rsplit("/", 1)[0] for v in p["variants"]}
        if len(p["variants"]) == 1:
            kinds["variant"] += 1
        else:
            kinds["destination" if len(dests) == 1 else "generic"] += 1
    return {"variants": n_var,
            "per_destination": {d: sum(1 for v in doc["variants"].values() if v["destination"] == d)
                                for d in sorted({v["destination"]
                                                 for v in doc["variants"].values()})},
            "quests": sorted({v["quest"] for v in doc["variants"].values() if v["quest"]}),
            "pages": len(doc["pages"]), "page_kinds": kinds,
            "max_lines_per_page": max((len(p["lines"]) for p in doc["pages"]), default=0),
            "problems": doc["problems"]}  # fmt: skip


# --- coverage -----------------------------------------------------------------------------------

CODE = re.compile(r"\^[0-9A-Fa-f]{6}")


def banked_chars(sessions: Sequence[Path]) -> set[str]:
    """Characters of the npc_say lines of banked sessions (dialogs drawn on banked frames)."""
    out: set[str] = set()
    for s in sessions:
        for e in read_events(s):
            if e.get("type") == "npc_say":
                out |= set(CODE.sub("", str(e.get("text", "")))) - {" "}
    return out


def coverage_report(pages: Sequence[dv.ExpectedPage], g: mt.MenuGlyphs,
                    banked: set[str] | None, show: bool) -> dict[str, Any]:  # fmt: skip
    variant_pages = [p for p in pages if len(p.destinations) == 1]
    out: dict[str, Any] = {"pages": len(pages), "variant_or_destination_pages": len(variant_pages),
                           "glyph_set_chars": len(g.chars),
                           "all_pages": dv.coverage(pages, g),
                           "variant_pages": dv.coverage(variant_pages, g)}  # fmt: skip
    missing = dv.missing_chars(pages, g)
    out["missing"] = len(missing)
    coloured = {c for p in pages for x in p.lines for c, ink in dv.styled(x)
                if ink not in (None, dv.BLACK)}  # fmt: skip
    out["missing_in_coloured_text"] = sum(1 for c in missing if c in coloured)
    if banked is not None:
        out["missing_seen_in_banked_dialogs"] = sum(1 for c in missing if c in banked)
        out["missing_only_live"] = sum(1 for c in missing if c not in banked)
    if show:
        out["missing_chars"] = missing
    return out


# --- sessions (prove, measure-wrap) --------------------------------------------------------------


def read_events(session: Path) -> list[dict[str, Any]]:
    with gzip.open(session / "packets.jsonl.gz", "rt") as f:
        return sorted((json.loads(x) for x in f if x.strip()), key=lambda e: int(e["t_mono_ns"]))


def frames_of(session: Path) -> list[tuple[int, Path]]:
    out = []
    for p in sorted((session / "frames").glob("*.png")):
        parts = p.stem.split("-")
        if len(parts) == 2 and parts[1].isdigit():
            out.append((int(parts[1]), p))
    return sorted(out)


def load_frame(path: Path) -> Any:
    from PIL import Image

    return np.ascontiguousarray(np.asarray(Image.open(path).convert("RGB"))[..., ::-1])


@dataclass(frozen=True)
class ShownPage:
    """One page as the packets show it: its lines, when it was complete, when the next dialog
    event came, and the conversation it belongs to (npc_contact count)."""

    lines: tuple[str, ...]
    t_done: int
    t_next: int
    conversation: int


def shown_pages(events: Sequence[dict[str, Any]]) -> list[ShownPage]:
    out: list[ShownPage] = []
    cur: list[str] = []
    conv = 0
    pending: list[tuple[tuple[str, ...], int]] = []
    for e in events:
        typ = e.get("type")
        if typ not in DIALOG_EVENTS:
            continue
        t = int(e["t_mono_ns"])
        for lines, done in pending:
            out.append(ShownPage(lines, done, t, conv))
        pending = []
        if typ == "npc_contact":
            conv += 1
        elif typ == "npc_say":
            cur.append(str(e.get("text", "")))
        elif typ in DIALOG_END:
            if cur:
                pending.append((tuple(cur), t))
            cur = []
    for lines, done in pending:
        out.append(ShownPage(lines, done, 1 << 62, conv))
    return out


def judged_frames(session: Path, settle_ms: int) -> Iterator[tuple[ShownPage, int, Path]]:
    frames = frames_of(session)
    for page in shown_pages(read_events(session)):
        for t, path in frames:
            if page.t_done + settle_ms * 1_000_000 <= t < page.t_next:
                yield page, t, path


def measure_wrap(sessions: Sequence[Path], t: dv.DialogText = dv.TEXT,
                 origin: tuple[int, int] | None = None) -> dict[str, Any]:  # fmt: skip
    """Ink ends of the physical lines on the first judged frame of every banked page (the dialog at
    its default place; pages with a scrollbar skipped), matched to the npc_say words."""
    from poring_env.ui_anchors import CAPTURE_ORIGINS

    ox, oy = origin or CAPTURE_ORIGINS["npc_dialog"]
    ax, ay, aw, ah = t.area
    fits: list[int] = []
    overs: list[int] = []
    pages = skipped = 0
    for s in sessions:
        seen: set[tuple[int, int]] = set()
        for page, _t, path in judged_frames(s, SETTLE_MS):
            if (page.conversation, page.t_done) in seen:
                continue
            seen.add((page.conversation, page.t_done))
            area = load_frame(path)[oy + ay : oy + ay + ah, ox + ax : ox + ax + aw].astype(int)
            ink = ~(np.abs(area - 247) <= 16).all(axis=-1)
            lines = []
            for k in range(t.bands + 1):
                top, bottom = t.band_rows(k)
                band = ink[top:bottom]
                if not band.any():
                    continue
                cols = np.flatnonzero(band.any(axis=0))
                runs = np.split(cols, np.flatnonzero(np.diff(cols) > WORD_GAP) + 1)
                lines.append([(int(r[0]), int(r[-1]) + 1) for r in runs])
            words = [len(CODE.sub("", x).split()) for x in page.lines]
            if any(w[-1][1] > t.wrap_end + 20 for w in lines) or sum(map(len, lines)) != sum(words):
                skipped += 1
                continue
            pages += 1
            i = 0
            for n in words:  # each mes line's words over its physical lines
                left = n
                while left > 0 and i < len(lines):
                    fits.append(lines[i][-1][1])
                    left -= len(lines[i])
                    if left > 0 and i + 1 < len(lines):
                        nxt = lines[i + 1][0]
                        overs.append(lines[i][-1][1] + 5 + (nxt[1] - nxt[0]))
                    i += 1
    ok = bool(fits and overs and max(fits) < min(overs))
    return {"pages": pages, "skipped": skipped, "lines": len(fits), "wraps": len(overs),
            "max_end_that_fit": max(fits, default=None),
            "min_end_that_did_not": min(overs, default=None),
            "verdict": "PASS" if ok else "FAIL"}  # fmt: skip


def _band_words(band: Any) -> int:
    """Words on one band: ink column runs split at gaps of >= WORD_GAP blank columns."""
    ink = ~(np.abs(band.astype(np.int16) - 247) <= 16).all(axis=-1)
    if not ink.any():
        return 0
    cols = np.flatnonzero(ink.any(axis=0))
    return len(np.split(cols, np.flatnonzero(np.diff(cols) > WORD_GAP) + 1))


def as_black(band: Any, lines: Sequence[str]) -> Any | None:
    """A band drawn in the page's inks, redrawn black on the background (T3's fit reads black
    ink only; the font is crisp, so the shapes are unchanged); None when any pixel is none of the
    page's inks."""
    inks = dv.page_inks([dv.ExpectedPage("", frozenset(), tuple(lines))])
    prob, _kind, foreign = dv.ink_layers(band, inks)
    if int(foreign.sum()) > dv.PARAMS.foreign_max:
        return None
    grey = np.round(np.float32(dv.PLAIN_RGB[0]) * (1.0 - prob)).astype(np.uint8)
    return np.ascontiguousarray(np.repeat(grey[..., None], 3, axis=2))


def labelled_bands(sessions: Sequence[Path], templates: Any, settle_ms: int = SETTLE_MS,
                   t: dv.DialogText = dv.TEXT) -> list[tuple[Any, str]]:  # fmt: skip
    """(band BGR, its text) of every black band of every judged dialog frame, the text from the
    page's npc_say words in order (see ``cut``)."""
    from poring_env import npc_dialog as nd

    out: list[tuple[Any, str]] = []
    ax, ay, aw, ah = t.area
    for s in sessions:
        for shown, _t, path in judged_frames(s, settle_ms):
            frame = load_frame(path)
            st = nd.state(frame, templates)
            if not st.ok or st.dialog is None:
                continue
            ox, oy = st.dialog.rect[:2]
            area = frame[oy + ay : oy + ay + ah, ox + ax : ox + ax + aw]
            bands = [np.ascontiguousarray(area[a:b, : t.wrap_end + t.wrap_slack + 1])
                     for a, b in (t.band_rows(k) for k in range(t.bands))]  # fmt: skip
            words = [(i, w) for i, x in enumerate(shown.lines) for w in CODE.sub("", x).split()]
            counts = [_band_words(b) for b in bands]
            if sum(counts) != len(words):
                continue
            k = 0
            for band, n in zip(bands, counts, strict=True):
                seg = words[k : k + n]
                k += n
                if not n or len({i for i, _ in seg}) != 1:
                    continue
                rgb = band.astype(np.int16)
                use: Any = band
                if ((rgb.max(axis=-1) - rgb.min(axis=-1)) >= 60).any():
                    use = as_black(band, shown.lines)  # the serial's digits are only ever blue
                    if use is None:
                        continue
                out.append((use, " ".join(w for _, w in seg)))
    return out


def selfcheck(sessions: Sequence[Path], g: mt.MenuGlyphs, templates: Any,
              settle_ms: int = SETTLE_MS) -> dict[str, Any]:  # fmt: skip
    """See ``selfcheck`` in the module docstring."""
    from poring_env import npc_dialog as nd

    seen: dict[tuple[str, ...], int] = {}
    for s in sessions:
        for shown in shown_pages(read_events(s)):
            seen.setdefault(shown.lines, len(seen))
    pages = [dv.ExpectedPage(f"page{i}", frozenset({f"page{i}/1"}), lines)
             for lines, i in seen.items()]  # fmt: skip
    covered = [p for p in pages if not dv.missing_chars([p], g)]
    tally: dict[str, int] = {}
    coloured_right = 0
    for s in sessions:
        for shown, _t, path in judged_frames(s, settle_ms):
            frame = load_frame(path)
            st = nd.state(frame, templates)
            if not st.ok or st.dialog is None:
                key = "t2_refused"
            else:
                page = pages[seen[shown.lines]]
                r, _ = dv.classify_frame(frame, st.dialog.rect[:2], g, covered)
                if r.variant is None:
                    key = f"refused:{r.reason.split(':')[-1]}"
                elif r.variant in page.variants:
                    key = "right"
                    coloured_right += int(any(CODE.search(x) for x in page.lines))
                else:
                    key = "wrong"
            tally[key] = tally.get(key, 0) + 1
    ok = tally.get("wrong", 0) == 0 and tally.get("right", 0) > 0
    return {"verdict": "PASS" if ok else "FAIL", "pages": len(pages), "covered": len(covered),
            "frames": dict(sorted(tally.items())),
            "right_on_coloured_pages": coloured_right}  # fmt: skip


def judge(r: dv.VariantRead, truth: dv.ExpectedPage) -> str:
    """The verdict ("right", "wrong" or "unknown") of one frame's read against its label."""
    if r.variant is not None:
        return "right" if r.variant in truth.variants else "wrong"
    if r.destination is not None:
        if r.destination not in truth.destinations:
            return "wrong"
        return "unknown" if len(truth.variants) == 1 else "right"
    if len(truth.destinations) == 1:
        return "unknown"  # a page naming a destination (or a variant) was refused
    return "right" if r.reason == "no_variant_info" else "unknown"


def prove(sessions: Sequence[Path], pages: Sequence[dv.ExpectedPage], g: mt.MenuGlyphs,
          templates: Any, settle_ms: int = SETTLE_MS) -> dict[str, Any]:  # fmt: skip
    """The bar in the module docstring, on banked sessions."""
    from poring_env import npc_dialog as nd

    by_lines = {p.lines: p for p in pages}
    wrong: list[dict[str, Any]] = []
    unknown: list[dict[str, Any]] = []
    unlabelled = 0
    instances: dict[tuple[str, int, int], dict[str, Any]] = {}
    for s in sessions:
        convs: dict[int, dv.Conversation] = {}
        for shown, t, path in judged_frames(s, settle_ms):
            truth = by_lines.get(shown.lines)
            if truth is None:
                unlabelled += 1
                continue
            frame = load_frame(path)
            st = nd.state(frame, templates)
            conv = convs.get(shown.conversation, dv.Conversation())
            if not st.ok or st.dialog is None:
                unknown.append({"session": s.name, "t": t, "why": f"t2:{st.reason}"})
                continue
            r, _ = dv.classify_frame(frame, st.dialog.rect[:2], g, pages, conv.context)
            convs[shown.conversation] = conv.add(r)
            key = (s.name, shown.conversation, shown.t_done)
            inst = instances.setdefault(key, {"page": truth.page_id, "variants": truth.variants,
                                              "right": 0, "frames": 0})  # fmt: skip
            inst["frames"] += 1
            verdict = judge(r, truth)
            if verdict == "wrong":
                wrong.append({"session": s.name, "t": t, "page": truth.page_id})
            elif verdict == "unknown":
                unknown.append({"session": s.name, "t": t, "why": r.reason})
            else:
                inst["right"] += 1
    shown_variants = sorted({v for i in instances.values() if len(i["variants"]) == 1
                             for v in i["variants"]})  # fmt: skip
    missed = [
        i["page"]
        for i in instances.values()
        if len({v.rsplit("/", 1)[0] for v in i["variants"]}) == 1 and not i["right"]
    ]
    ok = not wrong and not missed and bool(instances)
    return {"verdict": "PASS" if ok else "FAIL", "wrong": wrong, "unknown_frames": len(unknown),
            "unknown": unknown[:50], "unlabelled_frames": unlabelled,
            "page_instances": len(instances), "missed_pages": missed,
            "variants_banked": shown_variants}  # fmt: skip


# --- main ---------------------------------------------------------------------------------------


def _write(path: Path, doc: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.part")
    tmp.write_text(json.dumps(doc, indent=1, ensure_ascii=False) + "\n")
    tmp.replace(path)
    json.loads(path.read_text())  # read back


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("extract")
    p.add_argument("--src", type=Path, default=SRC)
    p.add_argument("--kb", type=Path, default=KB)
    p.add_argument("--out", type=Path, default=OUT)
    p = sub.add_parser("coverage")
    p.add_argument("--variants", type=Path, default=OUT)
    p.add_argument("--glyphs", type=Path, default=GLYPHS)
    p.add_argument("--banked", nargs="*", type=Path, default=None)
    p.add_argument("--show", action="store_true", help="print the missing characters (local)")
    p = sub.add_parser("measure-wrap")
    p.add_argument("sessions", nargs="+", type=Path)
    p = sub.add_parser("cut")
    p.add_argument("sessions", nargs="+", type=Path)
    p.add_argument("--out", type=Path, default=ROOT / "data" / "ui_anchors" / "dialog_glyphs.npz")
    p.add_argument("--templates", type=Path, default=TEMPLATES)
    p = sub.add_parser("selfcheck")
    p.add_argument("glyphs", type=Path)
    p.add_argument("sessions", nargs="+", type=Path)
    p.add_argument("--templates", type=Path, default=TEMPLATES)
    p = sub.add_parser("prove")
    p.add_argument("sessions", nargs="+", type=Path)
    p.add_argument("--variants", type=Path, default=OUT)
    p.add_argument("--glyphs", type=Path, default=GLYPHS)
    p.add_argument("--templates", type=Path, default=TEMPLATES)
    p.add_argument("--settle-ms", type=int, default=SETTLE_MS)
    a = ap.parse_args(argv)
    if a.cmd == "extract":
        kb = json.loads(a.kb.read_text())
        file, line = job_changer(kb)
        src = fw.Src(a.src)
        home = kb["scope"]["merchant"]["home"]
        doc = extract(npc_body(src.read(file), file, line), destinations(kb, home))
        doc["source"] = {"file": file, "line": line, "sha256": src.hashes.get(file)}
        _write(a.out, doc)
        print(json.dumps({"out": str(a.out), **summary(doc)}, indent=1))
        return 1 if doc["problems"] or len(doc["variants"]) != 8 else 0
    if a.cmd == "measure-wrap":
        out = measure_wrap(a.sessions)
        print(json.dumps(out, indent=1))
        return 0 if out["verdict"] == "PASS" else 1
    if a.cmd in ("cut", "selfcheck"):
        from poring_env import npc_dialog as nd

        templates = nd.load_templates(a.templates)
        if a.cmd == "selfcheck":
            out = selfcheck(a.sessions, mt.load_menu_glyphs(a.glyphs), templates)
            print(json.dumps(out, indent=1))
            return 0 if out["verdict"] == "PASS" else 1
        rows = labelled_bands(a.sessions, templates)
        if not rows:
            raise SystemExit("no labelled dialog band in these sessions")
        glyphs, stats = mt.fit_menu_glyphs([r for r, _ in rows], [x for _, x in rows])
        glyphs = dataclasses.replace(
            glyphs,
            meta={"rows": len(rows), "source": "dialog", "sessions": [x.name for x in a.sessions]},
        )
        glyphs.save(a.out)
        classes: dict[str, int] = {}
        for c in glyphs.chars:
            classes[dv.char_class(c)] = classes.get(dv.char_class(c), 0) + 1
        print(json.dumps({"out": str(a.out), "rows": stats["rows"], "used_rows": stats["used_rows"],
                          "skipped": stats["skipped"], "chars": len(glyphs.chars),
                          "classes": classes, "gaps0": stats["gaps0"], "gaps1": stats["gaps1"],
                          "lead_range": stats["lead_range"], "max_score": stats["max_score"],
                          "min_margin": stats["min_margin"]}, indent=1))  # fmt: skip
        return 0
    pages = expected_pages(json.loads(a.variants.read_text()))
    g = mt.load_menu_glyphs(a.glyphs)
    if a.cmd == "coverage":
        banked = banked_chars(a.banked) if a.banked is not None else None
        print(json.dumps(coverage_report(pages, g, banked, a.show), indent=1))
        return 0
    from poring_env import npc_dialog as nd

    out = prove(a.sessions, pages, g, nd.load_templates(a.templates), a.settle_ms)
    print(json.dumps(out, indent=1, default=sorted))
    return 0 if out["verdict"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
