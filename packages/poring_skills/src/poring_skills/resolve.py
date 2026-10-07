"""Resolve an L1 concept's bindings for the ACTIVE environment, failing closed (Batt, 2026-10-07).

- An L1 concept names the bindings it needs (`L2.*`, `L3.*`, `L4.*`). This module looks each one
  up for the environment in use:
  - L2, the client build: l2/<client>.yaml (committed: names and numbers only);
  - L3, the server: data/kb/bindings/<server>.json, GENERATED locally from the server's own
    files (GPL rAthena data is never committed);
  - L4, the locale: the locale pack (outside the repo, ADR-0012).
- A binding a concept needs but the environment lacks raises `Unsupported` with the layer, the
  key and the reason. A binding is NEVER guessed.

A key resolves by walking its dotted path; a parameter value (a window name, an NPC id) selects
the leaf when the key names a family, e.g. `L2.shortcut.window` + window=status.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from typing import Any, Literal

import yaml  # type: ignore[import-untyped]  # no stubs in the dev env

from poring_skills.schema import Concept, load_l1

L3_DIR = Path("data/kb/bindings")


@dataclass(frozen=True)
class ActiveEnv:
    client: str  # the L2 build, e.g. kro-20211103-prere
    server: str  # the attested environment id, e.g. lab-rathena
    locale: str  # the L4 pack, e.g. en
    path: Literal["rdp", "s2"]


class Unsupported(Exception):  # noqa: N818 -- the library's result vocabulary
    def __init__(self, concept: str, layer: str, key: str, reason: str) -> None:
        super().__init__(f"{concept}: {layer} binding {key} unsupported: {reason}")
        self.concept, self.layer, self.key, self.reason = concept, layer, key, reason


def load_l2(client: str) -> dict[str, Any]:
    path = resources.files("poring_skills") / "l2" / f"{client}.yaml"
    if not path.is_file():
        raise FileNotFoundError(client)
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if data.get("client") != client:
        raise ValueError(f"l2/{client}.yaml names client {data.get('client')!r}")
    return dict(data)


def client_for_profile(profile: str) -> str:
    """The L2 build an ro_agent client profile runs (l2/*.yaml `profiles`); fails closed."""
    hits = []
    for entry in (resources.files("poring_skills") / "l2").iterdir():
        if entry.name.endswith(".yaml"):
            data = yaml.safe_load(entry.read_text(encoding="utf-8"))
            if profile in (data.get("profiles") or []):
                hits.append(str(data["client"]))
    if len(hits) != 1:
        raise Unsupported("*", "L2", "profile", f"profile {profile!r} maps to {hits or 'no build'}")
    return hits[0]


def load_l3(server: str, root: Path = L3_DIR) -> dict[str, Any]:
    path = root / f"{server}.json"
    if not path.exists():
        raise FileNotFoundError(str(path))
    return dict(json.loads(path.read_text()))


def _walk(tree: Any, parts: list[str]) -> Any:
    for p in parts:
        if not isinstance(tree, dict) or p not in tree:
            return None
        tree = tree[p]
    return tree


def resolve(concept: Concept | str, env: ActiveEnv, params: dict[str, str] | None = None,
            *, l3_root: Path = L3_DIR) -> dict[str, Any]:  # fmt: skip
    """{binding key: resolved value} for every binding the concept needs, or Unsupported."""
    c = load_l1()[concept] if isinstance(concept, str) else concept
    params = params or {}
    layers: dict[str, Any] = {}
    out: dict[str, Any] = {}
    for key in c.bindings_needed:
        layer, *parts = key.split(".")
        if layer not in layers:
            try:
                if layer == "L2":
                    layers[layer] = load_l2(env.client)
                elif layer == "L3":
                    layers[layer] = load_l3(env.server, l3_root)
                else:
                    layers[layer] = None  # the locale pack resolver lands with the L4 work
            except FileNotFoundError:
                where = env.client if layer == "L2" else env.server
                raise Unsupported(c.id, layer, key, f"no {layer} bindings for {where}") from None
        if layers[layer] is None:
            raise Unsupported(c.id, layer, key, f"no {layer} resolver for locale {env.locale} yet")
        node = _walk(layers[layer], parts)
        if isinstance(node, dict) and node and all(isinstance(v, dict) for v in node.values()):
            # a family (every value is itself a table; a leaf never is): a parameter picks the
            # leaf, e.g. shortcut.window + window=status (a window may be NAMED "status")
            picks = [v for k, v in params.items() if v in node]
            node = node[picks[0]] if len(picks) == 1 else None
        if node is None:
            raise Unsupported(c.id, layer, key, f"not bound for {env.client}/{env.server} "
                                                f"(params {params or '{}'})")  # fmt: skip
        if isinstance(node, dict) and env.path in ("rdp", "s2") and env.path in node:
            node = {**node, "value": node[env.path]}
        out[key] = node
    return out
