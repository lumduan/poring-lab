"""A STUB for learners (Batt 2026-11-09: "add the import line and try/finally now").

The Python view of a flow starts with ``from poring_flow.learner import *``, so it reads like a
file a learner could run. poring-lab runs flows ITSELF: the flow engine parses that Python and
never runs it (ADR-0020 7.2, 7.4). So every name here has its block's (or sensor's) name and
signature, and calling it raises NotImplementedError with that message; ``python my_flow.py``
explains itself at its first block instead of failing with a NameError.

- The names come from the catalogue (blocks.yaml: every block and sensor with its parameters) and
  the Python view's helpers, reference constructors and constants (catalogue.py), so the stub
  never drifts from what the view prints (tests/test_models.py checks it).
- ``release_all()`` is the one name that does NOTHING: it is the view's ``finally:``, which the
  engine really does at the end of a flow (it lets go of every key and mouse button still held,
  runtime.Sim.run). In this stub nothing ran, so nothing is held.
- ``range`` is Python's own (``for _ in range(3)`` is the repeat block).
- Nothing here sends input, reads the screen or imports the engine's runtime: it is a stub.
"""

from __future__ import annotations

import inspect
from collections.abc import Callable
from typing import Any, NoReturn

from poring_flow.catalogue import CONSTANTS, HELPERS, REF_CONSTRUCTORS, ParamSpec, registry

MESSAGE = "poring-lab runs flows itself; this file is read, never run"
ACTION_OPTIONS = ("timeout_s", "on_fail", "note")  # every action block's own keywords
PYTHON_OWN = ("range",)  # helpers the view takes from Python itself

__all__: list[str] = []


def _signature(params: list[ParamSpec], extra: tuple[str, ...] = ()) -> inspect.Signature:
    out: list[inspect.Parameter] = []
    for p in params:
        if p.positional:
            default = inspect.Parameter.empty if p.required else None
            kind = inspect.Parameter.POSITIONAL_OR_KEYWORD
            out.append(inspect.Parameter(p.name, kind, default=default))
    for p in params:
        if not p.positional:
            default = inspect.Parameter.empty if p.required else None
            out.append(inspect.Parameter(p.name, inspect.Parameter.KEYWORD_ONLY, default=default))
    out += [inspect.Parameter(k, inspect.Parameter.KEYWORD_ONLY, default=None) for k in extra]
    return inspect.Signature(out)


def _stub(name: str, what: str, sig: inspect.Signature | None) -> Callable[..., NoReturn]:
    def stub(*args: Any, **kwargs: Any) -> NoReturn:
        raise NotImplementedError(f"{name}(): {MESSAGE}")

    stub.__name__ = stub.__qualname__ = name
    stub.__doc__ = f"{what} (a stub: {MESSAGE})."
    if sig is not None:
        setattr(stub, "__signature__", sig)  # noqa: B010 -- a function attribute inspect reads
    return stub


def release_all() -> None:
    """The view's ``finally:``: the engine lets go of every key and mouse button still held when
    a flow ends. In this stub nothing ran, so nothing is held and it does nothing."""


def _build() -> dict[str, Any]:
    reg = registry()
    names: dict[str, Any] = {}
    for name, b in reg.blocks.items():
        names[name] = _stub(name, f"the {name} block", _signature(b.params, ACTION_OPTIONS))
    for name, s in reg.sensors.items():
        names[name] = _stub(name, f"the {name} sensor", _signature(s.params))
    for name in (*REF_CONSTRUCTORS, *HELPERS):
        if name not in names and name not in PYTHON_OWN and name != "release_all":
            names[name] = _stub(name, f"the view's {name}(...)", None)
    names["release_all"] = release_all
    names.update(CONSTANTS)  # OK = "ok", CRITICAL = "critical", S2 = "s2", ...
    return names


_NAMES = _build()
globals().update(_NAMES)
__all__ += sorted(_NAMES)
