"""live-blocks 5b-1 (docs/planning/live-blocks.md 13.3): scripts/huntstate_check.py's rewrites keep
behaviour, shown BY EXECUTION on a small program with each hazard (a closure's nonlocal, a
shadowing parameter, a default read at def time, a lambda, a comprehension with a walrus, an
except-as, break / continue in a loop of its own, a for-else, a continue inside try / finally);
the checker names each kind of wrong rewrite (a verifier proves a positive case)."""

from __future__ import annotations

import ast
import contextlib
import io
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts"))

import huntstate_check as hc  # noqa: E402

TOY = '''
def run(xs, *, hook=None):
    """the toy's docstring"""
    trace = []
    mode = "search"
    n = 0
    here = None
    seen: list[int] = []
    flags = [False]

    def bump(k):
        nonlocal n, here
        n += k
        here = (n, k)
        flags[0] = not flags[0]

    def shadow(here, mode=mode):
        return (here, mode)

    def later():
        return (mode, n, here)

    t_end = len(xs) + 1
    try:
        while time.monotonic() < t_end:
            tick = time.monotonic()
            x = xs[int(tick * 2) % len(xs)]
            trace.append(("tick", tick, x, mode))
            if x == "stop":
                trace.append("stopping")
                break
            for j in range(3):
                if isinstance(x, int) and j == x % 3:
                    continue
                if j == 2:
                    break
                bump(j)
            else:
                trace.append("for-else")
            vals = [v * n for v in range(2) if (w := v + n) > 0]
            trace.append(("comp", vals, w))
            if isinstance(x, int) and x % 4 == 0:
                mode = "fight"
                try:
                    trace.append("try")
                    continue
                finally:
                    trace.append("finally")
            try:
                if x == "boom":
                    raise ValueError("boom")
            except ValueError as e:
                trace.append(("caught", str(e)))
            seen.append(n)
            f = lambda q=here: (q, mode)  # noqa: E731
            trace.append(("lambda", f(), shadow(1), later()))
            if mode == "fight":
                mode = "after"
                continue
            mode = "search"
    finally:
        trace.append(("end", mode, n, here, list(seen), flags[0]))
    return trace
'''
ALIASED = ("seen", "flags")
SPEC = (("a", "tick = time.monotonic()"), ("b", "for j in range(3):"), ("c", "vals = "),
        ("d", "if isinstance(x, int) and x % 4 == 0:"), ("e", "try:"), ("f", "seen.append("),
        ("g", 'if hs.mode == "fight":'))  # fmt: skip
INPUTS = ([1, 4, "boom", 2, 8, 3, 5, 0, 7], [2, 3, "stop", 4], [0, 0, 1, "boom", 6])


class Clock:
    def __init__(self) -> None:
        self.t = 0.0

    def monotonic(self) -> float:
        self.t += 0.25
        return self.t


def _derive(src: str) -> str:
    """LIFT + ALIAS, the class and the signals, then OUTLINE: the toy as 5b-1 rewrites it."""
    ri = hc.parse_run(src)
    lifted = hc.lifted_names(ri, (), ())
    assert hc.conditions(ri, lifted, ALIASED) == []
    assert hc.cross_check(src, ri.sb) == [] and hc.symtable_renames(src, ri.sb, lifted) == []
    head = (f'TICK_DONE = "tick_done"\nRUN_END = "run_end"\n\n\nclass HuntState:\n'
            f"    __slots__ = {tuple(lifted) + ALIASED!r}\n\n")  # fmt: skip
    return hc.derive_outline(head + hc.derive_lift(src, lifted, ALIASED), SPEC)


def _play(src: str, xs: list[Any]) -> list[Any]:
    ns: dict[str, Any] = {"time": Clock()}
    exec(compile(src, "<toy>", "exec"), ns)  # noqa: S102 -- the test's own program
    return ns["run"](xs)  # type: ignore[no-any-return]


def _check(base: str, new: str) -> tuple[int, str]:
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        rc = hc.check(base, new, ALIASED, (), ())
    return rc, out.getvalue()


def test_the_toy_has_every_hazard_and_the_rewrite_lifts_what_the_rule_says() -> None:
    ri = hc.parse_run(TOY)
    assert hc.lifted_names(ri, (), ()) == ["here", "mode", "n"]  # bound before and again
    new = _derive(TOY)
    assert "nonlocal" not in new.split("def shadow")[0].split("def bump")[1]  # bump's went
    assert "def shadow(here, mode=hs.mode):" in new  # the parameter stays, the default lifts
    assert "seen = hs.seen = []" in new and "flags = hs.flags = [False]" in new
    assert new.count("return TICK_DONE") == 2 and new.count("return RUN_END") == 1
    # its own
    assert "                    continue\n" in new and "                    break\n" in new
    tree = ast.parse(new)
    steps = [n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)
             and n.name.startswith("step_")]  # fmt: skip
    assert steps == [f"step_{k}" for k, _ in SPEC]


@pytest.mark.parametrize("xs", INPUTS)
def test_the_rewritten_toy_plays_exactly_as_the_original(xs: list[Any]) -> None:
    new = _derive(TOY)
    want = _play(TOY, xs)
    assert len(want) >= 5
    assert _play(new, xs) == want


def test_the_inputs_reach_every_hazard_path() -> None:
    got = [t for xs in INPUTS for t in _play(TOY, xs)]
    for mark in ("finally", "try", "stopping", "for-else"):
        assert mark in got, mark  # continue in try / finally, the loop's break, a for-else
    kinds = {t[0] for t in got if isinstance(t, tuple)}
    assert {"tick", "comp", "caught", "lambda", "end"} <= kinds
    assert any(t[0] == "tick" and t[3] == "after" for t in got if isinstance(t, tuple))


def test_the_checker_passes_the_rewrite_and_prints_every_condition() -> None:
    rc, out = _check(TOY, _derive(TOY))
    assert rc == 0, out
    assert "run() == OUTLINE(ALIAS(LIFT(base))): YES" in out
    assert "OUTLINE (7 steps): a b c d e f g" in out
    assert "resolver vs symtable" in out and "the same" in out


# --- positive cases: each kind of wrong rewrite is named -----------------------------------------
def test_a_wrong_rename_of_a_shadowing_parameter_is_caught_and_plays_differently() -> None:
    new = _derive(TOY)
    bad = new.replace("        return (here, mode)\n", "        return (hs.here, mode)\n")
    assert bad != new
    rc, out = _check(TOY, bad)
    assert rc == 1 and "run() == OUTLINE(ALIAS(LIFT(base))): NO" in out
    assert _play(bad, INPUTS[0]) != _play(TOY, INPUTS[0])  # and it does play differently


def test_a_step_that_binds_a_name_without_nonlocal_is_named() -> None:
    new = _derive(TOY)
    line = next(ln for ln in new.splitlines() if ln.strip().startswith("nonlocal tick"))
    bad = new.replace(line + "\n", line.replace("tick, ", "") + "\n", 1)
    assert bad != new
    rc, out = _check(TOY, bad)
    assert rc == 1 and "step_a: binds ['tick'] not as nonlocal" in out


def test_steps_in_another_order_or_a_swapped_signal_are_caught() -> None:
    new = _derive(TOY)
    swapped = new.replace('("b", step_b),\n', "@@").replace('("c", step_c),\n', '("b", step_b),\n')
    swapped = swapped.replace("@@", '("c", step_c),\n')
    assert swapped != new
    assert _check(TOY, swapped)[0] == 1
    sig = new.replace("return TICK_DONE", "return RUN_END", 1)
    rc, out = _check(TOY, sig)
    assert rc == 1 and "NO" in out


def test_a_missing_slot_and_a_new_top_level_statement_are_named() -> None:
    new = _derive(TOY)
    bad = new.replace("'flags'", "'flagz'")
    rc, out = _check(TOY, bad)
    assert rc == 1 and "missing ['flags']" in out and "extra ['flagz']" in out
    rc2, out2 = _check(TOY, new + "\nX = 1\n")
    assert rc2 == 1 and "the module outside run(): DIFFERS" in out2


def test_the_symtable_cross_check_catches_a_wrong_resolver(monkeypatch: Any) -> None:
    ri = hc.parse_run(TOY)
    lifted = hc.lifted_names(ri, (), ())
    assert hc.symtable_renames(TOY, ri.sb, lifted) == []

    def naive(self: hc.Scope, name: str) -> hc.Scope | None:  # every name: the outermost scope
        s = self
        while s.parent is not None:
            s = s.parent
        return s

    monkeypatch.setattr(hc.Scope, "resolve", naive)
    bad = hc.symtable_renames(TOY, ri.sb, lifted)
    assert any("here: symtable False, mine True" in b for b in bad)  # shadow()'s parameter


def test_the_preconditions_refuse_what_the_rewrite_cannot_keep() -> None:
    src = TOY.replace("    t_end = len(xs) + 1\n", "    t_end = len(xs) + 1\n    print(locals())\n")
    src = src.replace("except ValueError as e:", "except NameError as e:")
    ri = hc.parse_run(src)
    bad = hc.conditions(ri, hc.lifted_names(ri, (), ()), ALIASED)
    assert any("locals()" in b for b in bad) and any("NameError" in b for b in bad)
    twice = TOY.replace("    flags = [False]\n", "    flags = [False]\n    flags = [True]\n")
    ri2 = hc.parse_run(twice)
    assert any(b.startswith("flags: an alias needs exactly one binding")
               for b in hc.conditions(ri2, hc.lifted_names(ri2, (), ()), ALIASED))  # fmt: skip
