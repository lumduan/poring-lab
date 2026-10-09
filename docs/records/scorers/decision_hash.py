"""Hash every function's COMPILED code in a source file (bytecode, constants, names, argument
layout; line numbers ignored), without importing or running it. Usage: decision_hash.py FILE..."""
import hashlib, json, sys, types

def norm(c):
    if isinstance(c, types.CodeType):
        return ("code", c.co_name, c.co_code, tuple(norm(x) for x in c.co_consts), c.co_names,
                c.co_varnames, c.co_freevars, c.co_cellvars, c.co_argcount, c.co_posonlyargcount,
                c.co_kwonlyargcount, c.co_flags)
    if isinstance(c, (tuple, frozenset)):
        return (type(c).__name__, tuple(norm(x) for x in c))
    return repr(c)

def functions(code, prefix=""):
    out = {}
    for c in code.co_consts:
        if isinstance(c, types.CodeType):
            q = f"{prefix}{c.co_qualname}"
            out[q] = hashlib.sha256(repr(norm(c)).encode()).hexdigest()[:16]
            out.update(functions(c))
    return out

res = {}
for f in sys.argv[1:]:
    src = open(f).read()
    res[f] = functions(compile(src, f.split("/")[-1], "exec"))
print(json.dumps(res))
