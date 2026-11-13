"""Builders for the project model's tests (format 3): JSON pieces, the two fixtures as dicts."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

from poring_flow import project as P
from poring_flow.catalogue import catalogue

REPO = Path(__file__).resolve().parents[3]
FIXTURES = REPO / "services/frontend/src/lib/flow/fixtures"
XMAS = FIXTURES / "project_xmas_dun02.json"
SAMPLE = FIXTURES / "project_sample.json"
SAMPLE_TRACE = REPO / "services/frontend/src/lib/maps/fixtures/project_sample_trace.json"
ZONES = REPO / "config/map_zones/xmas_dun02.yaml"


def lit(v: Any) -> dict[str, Any]:
    return {"kind": "lit", "value": v}


def var(name: str) -> dict[str, Any]:
    return {"kind": "var", "name": name}


def act(block: str, **params: Any) -> dict[str, Any]:
    spec = catalogue().blocks[block].spec
    return {"kind": "action", "block": block, "concept": spec.concept, "params": params,
            "timeout_s": spec.timeout_s}  # fmt: skip


def press(key: str | dict[str, Any]) -> dict[str, Any]:
    return act("press_key", key=key if isinstance(key, dict) else lit(key))


def call(proc: str, *args: Any, **kwargs: Any) -> dict[str, Any]:
    return {"kind": "call", "proc": proc, "args": list(args), "kwargs": kwargs}


def callv(proc: str, *args: Any, **kwargs: Any) -> dict[str, Any]:
    return {"kind": "callv", "proc": proc, "args": list(args), "kwargs": kwargs}


def fdef(name: str, *body: Any, params: Any = (), varargs: str | None = None,
         kwargs: str | None = None, on: Any = None) -> dict[str, Any]:  # fmt: skip
    ps = [p if isinstance(p, dict) else {"name": p, "default": None} for p in params]
    return {"name": name, "params": ps, "varargs": varargs, "kwargs": kwargs, "body": list(body),
            "on": on}  # fmt: skip


def tab(name: str, *defs: Any, main: Any = None, vars: Any = None) -> dict[str, Any]:  # noqa: A002
    return {"name": name, "main": main, "defs": list(defs), "vars": dict(vars or {})}


def hp(op: str, v: int) -> dict[str, Any]:
    return {"kind": "cmp", "op": op, "left": {"kind": "sense", "sensor": "hp_percent"},
            "right": lit(v)}  # fmt: skip


def xmas() -> dict[str, Any]:
    return dict(json.loads(XMAS.read_text(encoding="utf-8")))


def sample() -> dict[str, Any]:
    return dict(json.loads(SAMPLE.read_text(encoding="utf-8")))


def node(d: dict[str, Any], node_id: str) -> dict[str, Any]:
    return next(n for n in d["nodes"] if n["id"] == node_id)


def add_tab(d: dict[str, Any], node_id: str, t: dict[str, Any]) -> dict[str, Any]:
    d = copy.deepcopy(d)
    node(d, node_id)["tabs"].append(t)
    return d


def build(d: dict[str, Any]) -> P.Project:
    return P.validate(copy.deepcopy(d))
