#!/usr/bin/env python3
"""The BYTECODE-IDENTICAL proof (Batt 2026-10-09): a pre-registered rule's decision code may not
change without a new pre-registration. This imports a rule module from TWO source trees (e.g. the
pre-registration's commit and today's) in separate processes, fingerprints every function, method
and module constant in its import graph (the repo's own modules), and compares them.

    bytecode_proof.py walk15 OLD_ROOT NEW_ROOT --harness walk11.run ro_agent.chat_line ...

A fingerprint is the code object's bytecode, constants (nested code objects recursively), names,
variable names, defaults and flags; line numbers are ignored (a comment may move code down). PASS
when every changed or removed item is in --harness (the declared, non-decision code: the run loop,
typing, the position sensor's transport); an added item is reported. Exit 0 = PASS.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

PROBE = r"""
import hashlib, inspect, json, re, sys, types
root = sys.argv[1]; target = sys.argv[2]
ADDR = re.compile(r" at 0x[0-9a-f]+")
sys.path[:0] = [root + "/scripts"] + [p for p in sys.argv[3:]]
__import__(target)

def norm(x):  # the tree's own path and object addresses are not code
    return ADDR.sub("", repr(x).replace(root, "<ROOT>"))

def fp_code(c):
    h = hashlib.sha256()
    h.update(c.co_code)
    for k in c.co_consts:
        h.update(fp_code(k).encode() if isinstance(k, types.CodeType) else norm(k).encode())
    h.update(repr((c.co_names, c.co_varnames, c.co_freevars, c.co_cellvars, c.co_flags,
                   c.co_argcount, c.co_kwonlyargcount, c.co_posonlyargcount)).encode())
    return h.hexdigest()[:16]

def fp_func(f):
    f = inspect.unwrap(f)
    code = getattr(f, "__code__", None)
    if code is None or not code.co_filename.startswith(root) or "/.venv/" in code.co_filename:
        return None  # generated code (dataclass methods, exec'd helpers): not our source
    return fp_code(code) + ":" + hashlib.sha256(norm((f.__defaults__, f.__kwdefaults__)).encode()
                                                 ).hexdigest()[:8]

out = {}
for name, mod in list(sys.modules.items()):
    f = getattr(mod, "__file__", None)
    if not f or not f.startswith(root) or "/.venv/" in f:
        continue
    short = name
    for k, v in vars(mod).items():
        if getattr(v, "__module__", None) != mod.__name__:
            plain = (int, float, str, bytes, bool, tuple, frozenset, dict, list)
            if isinstance(v, plain) and not k.startswith("__"):
                val = sorted(map(repr, v)) if isinstance(v, frozenset) else v
                out[f"{short}.{k}"] = "const:" + hashlib.sha256(norm(val).encode()).hexdigest()[:16]
            continue
        if isinstance(v, types.FunctionType):
            if (fp := fp_func(v)) is not None:
                out[f"{short}.{k}"] = fp
        elif isinstance(v, type):
            for mk, mv in vars(v).items():
                fn = mv.__func__ if isinstance(mv, (staticmethod, classmethod)) else mv
                if isinstance(fn, types.FunctionType) and (fp := fp_func(fn)) is not None:
                    out[f"{short}.{k}.{mk}"] = fp
print(json.dumps(out))
"""


def fingerprints(root: Path, target: str, extra: list[str]) -> dict[str, str]:
    paths = [str(root / p) for p in extra]
    out = subprocess.run([sys.executable, "-c", PROBE, str(root), target, *paths],
                         capture_output=True, text=True, check=True,
                         env={"PYTHONDONTWRITEBYTECODE": "1", "PYTHONHASHSEED": "0",
                              "PATH": "/usr/bin:/bin"})  # fmt: skip
    return dict(json.loads(out.stdout))


def compare(old: dict[str, str], new: dict[str, str], harness: set[str]) -> dict[str, object]:
    changed = sorted(k for k in old.keys() & new.keys() if old[k] != new[k])
    removed = sorted(old.keys() - new.keys())
    added = sorted(new.keys() - old.keys())
    undeclared = [k for k in changed + removed if k not in harness]
    return {"compared": len(old.keys() & new.keys()), "changed": changed, "removed": removed,
            "added": added, "undeclared_changes": undeclared,
            "verdict": "PASS" if not undeclared else "FAIL"}  # fmt: skip


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)  # fmt: skip
    ap.add_argument("target")
    ap.add_argument("old_root", type=Path)
    ap.add_argument("new_root", type=Path)
    ap.add_argument("--harness", nargs="*", default=[])
    ap.add_argument("--path", nargs="*", default=[
        "packages/poring_env/src", "packages/poring_dataset/src", "packages/poring_packets/src",
        "packages/poring_skills/src", "services/backend/src"])  # fmt: skip
    a = ap.parse_args()
    old = fingerprints(a.old_root.resolve(), a.target, a.path)
    new = fingerprints(a.new_root.resolve(), a.target, a.path)
    out = compare(old, new, set(a.harness))
    digest = hashlib.sha256(json.dumps(sorted(old.items())).encode()).hexdigest()[:12]
    print(json.dumps({"target": a.target, "old_root": str(a.old_root), "new_root": str(a.new_root),
                      "old_digest": digest, **out}, indent=1))  # fmt: skip
    return 0 if out["verdict"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
