#!/usr/bin/env python3
"""The NESTED bytecode proof: which code objects of a source file changed, one by one, closures
included (docs/planning/blocks-from-hunt-flow.md, B3: "bytecode proof of the decision code").

    nested_code_proof.py OLD.py NEW.py [--allow QUALNAME ...] [--show QUALNAME ...]

`bytecode_proof.py` fingerprints a function WITH its nested functions, so a changed line at the top
of hunt_flow.run (thousands of lines, every decision closure nested inside it) says only "run
changed". This compiles both files (nothing is imported or run) and fingerprints EVERY code
object -- the module, each function, each closure, each comprehension -- by its qualified name,
each WITHOUT its children (a nested code object counts as its name only), so a change shows
exactly where it is.

A fingerprint is the bytecode, the constants, names, variable / free / cell names, flags and
argument counts; line numbers are ignored. PASS when every changed, added or removed code object
is in --allow. For each changed one (and each --show), the instruction diff (opname + argument,
jump targets and line numbers left out) is printed: the reviewer reads what moved.
"""

from __future__ import annotations

import argparse
import difflib
import dis
import hashlib
import json
import sys
import types
from pathlib import Path


def _const(c: object) -> str:
    return f"<code {c.co_qualname}>" if isinstance(c, types.CodeType) else repr(c)


def fingerprint(c: types.CodeType) -> str:
    h = hashlib.sha256(c.co_code)
    h.update(repr([_const(k) for k in c.co_consts]).encode())
    h.update(
        repr(
            (
                c.co_names,
                c.co_varnames,
                c.co_freevars,
                c.co_cellvars,
                c.co_flags,
                c.co_argcount,
                c.co_kwonlyargcount,
                c.co_posonlyargcount,
            )
        ).encode()
    )
    return h.hexdigest()[:16]


def code_objects(path: Path) -> dict[str, types.CodeType]:
    """Every code object in the file by qualified name (``<module>`` for the module; a repeated
    name, e.g. two lambdas in one function, gets ``#2``, ``#3`` in source order)."""
    top = compile(path.read_text(encoding="utf-8"), str(path), "exec")
    out: dict[str, types.CodeType] = {}

    def walk(c: types.CodeType) -> None:
        name = c.co_qualname if c is not top else "<module>"
        key, n = name, 1
        while key in out:
            n += 1
            key = f"{name}#{n}"
        out[key] = c
        for k in c.co_consts:
            if isinstance(k, types.CodeType):
                walk(k)

    walk(top)
    return out


def instructions(c: types.CodeType) -> list[str]:
    out = []
    for ins in dis.get_instructions(c):
        if ins.opcode in dis.hasjrel or ins.opcode in dis.hasjabs:
            out.append(ins.opname)  # a jump: its target offset moves with any insertion
        elif isinstance(ins.argval, types.CodeType):
            out.append(f"{ins.opname} <code {ins.argval.co_qualname}>")
        else:
            out.append(f"{ins.opname} {ins.argrepr}".rstrip())
    return out


def diff(old: types.CodeType, new: types.CodeType) -> list[str]:
    return [line for line in difflib.unified_diff(instructions(old), instructions(new), "old",
                                                    "new", n=2, lineterm="")]  # fmt: skip


def compare(old_path: Path, new_path: Path, allow: set[str], show: set[str]) -> dict[str, object]:
    old, new = code_objects(old_path), code_objects(new_path)
    fo = {k: fingerprint(c) for k, c in old.items()}
    fn = {k: fingerprint(c) for k, c in new.items()}
    changed = sorted(k for k in fo.keys() & fn.keys() if fo[k] != fn[k])
    removed = sorted(fo.keys() - fn.keys())
    added = sorted(fn.keys() - fo.keys())
    undeclared = [k for k in changed + removed + added if k not in allow]
    diffs = {k: diff(old[k], new[k]) for k in sorted(set(changed) | (show & fo.keys() & fn.keys()))}
    return {"compared": len(fo.keys() & fn.keys()), "identical": len(fo.keys() & fn.keys())
            - len(changed), "changed": changed, "removed": removed, "added": added,
            "undeclared": undeclared, "verdict": "PASS" if not undeclared else "FAIL",
            "diffs": diffs}  # fmt: skip


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)  # fmt: skip
    ap.add_argument("old", type=Path)
    ap.add_argument("new", type=Path)
    ap.add_argument("--allow", nargs="*", default=[])
    ap.add_argument("--show", nargs="*", default=[])
    a = ap.parse_args()
    out = compare(a.old, a.new, set(a.allow), set(a.show))
    diffs = out.pop("diffs")
    print(json.dumps(out, indent=1))
    for k, lines in diffs.items():  # type: ignore[attr-defined]
        print(f"\n--- {k}: the instruction diff (jump targets and line numbers left out)")
        print("\n".join(lines) if lines else "(no instruction change)")
    return 0 if out["verdict"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
