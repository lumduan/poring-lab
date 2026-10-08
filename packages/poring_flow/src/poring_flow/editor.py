"""What the MW2 editor asks of the flow engine (mw2-block-editor.md sections 3-5): pure
computation, IR in, documents out. No state, no input path, no I/O beyond reading the committed
catalogue / L1 / L2 files and the static map sheets it is handed.

- `catalogue_doc()`: the block catalogue plus each block's VERIFICATION BADGE, derived from L1's
  `verified_on` (an alone-test pass per path): verified on RDP / on S2 / on both, unverified,
  unknown (no L1 concept), core (no input). Flipping a concept's `verified_on` flips the badge.
- `lint_doc()`: MW1's linter findings, each with the canvas node that owns it, the counts, and
  every map block's effective event set (13.6.2).
- `python_doc()`: MW1's canonical Python view (read-only in MW2: import waits for F3's sandbox).
- `world_doc()`: what the pickers offer from the static data (NPCs, their menu keys, warps,
  spawns, items), keys and numbers only plus the sheet's own labels.
- `sample_*`: the committed SYNTHETIC sample (Batt's town -> NPC warp -> farm loop example).
"""

from __future__ import annotations

from importlib import resources
from pathlib import Path
from typing import Any, Literal

from poring_flow import ir, pyview
from poring_flow.catalogue import Catalogue, catalogue
from poring_flow.effective import global_set, merge
from poring_flow.lint import Detector, Resolver, lint
from poring_flow.sheet import World, load_world
from poring_skills.schema import Concept, load_l1

Badge = Literal["verified_rdp_s2", "verified_rdp", "verified_s2", "unverified", "unknown", "core"]
# The blocks MW2's block editor offers as their own blocks (section 3); every other catalogue
# block is still shown, lossless, as a generic action block.
PALETTE = ("walk_to", "talk_npc", "choose_menu", "open_window", "use_item")
SAMPLE = "town_warp_farm"
SAMPLE_SERVER = "sample"  # the synthetic sheets' server id (examples/sheets/sample)


def badge(concept: str | None, l1: dict[str, Concept], core: bool = False) -> Badge:
    """The verification badge of a concept, from its L1 `verified_on` paths."""
    if core:
        return "core"
    if concept is None or concept not in l1:
        return "unknown"
    paths = {v.path for v in l1[concept].verified_on}
    if paths >= {"rdp", "s2"}:
        return "verified_rdp_s2"
    if "rdp" in paths:
        return "verified_rdp"
    if "s2" in paths:
        return "verified_s2"
    return "unverified"


def catalogue_doc(
    l1: dict[str, Concept] | None = None, cat: Catalogue | None = None, client: str | None = None
) -> dict[str, Any]:
    l1 = load_l1() if l1 is None else l1
    cat = catalogue() if cat is None else cat
    blocks: dict[str, Any] = {}
    for name, b in cat.blocks.items():
        c = l1.get(b.spec.concept)
        blocks[name] = {
            **b.model_dump(mode="json"),
            "badge": badge(b.spec.concept, l1, b.spec.kind == "core"),
            "verified_on": [
                {"path": v.path, "server": v.server, "rule": v.rule, "date": v.date}
                for v in (c.verified_on if c else [])
            ],
        }
    sensors = {
        name: {**s.model_dump(mode="json"), "badge": badge(s.spec.concept, l1)}
        for name, s in cat.sensors.items()
    }
    windows: list[str] = []
    if client is not None:
        try:
            from poring_skills.resolve import load_l2

            windows = sorted((load_l2(client).get("window") or {}).keys())
        except (FileNotFoundError, ValueError):
            windows = []
    return {
        "version": cat.version,
        "blocks": blocks,
        "sensors": sensors,
        "constants": dict(cat.constants),
        "palette": list(PALETTE),
        "windows": windows,
        "outcomes": list(ir.OUTCOMES),
        "classes": list(ir.CLASSES),
        "safety_critical": list(ir.SAFETY_CRITICAL),
        "limits": {"json_bytes": ir.MAX_JSON_BYTES, "json_depth": ir.MAX_JSON_DEPTH},
    }


def owners(flow: ir.Flow) -> dict[str, str]:
    """Node-path ROOT -> the canvas node that shows it: `block:<name>`, `global` (a global
    event), or `flow` (main, a procedure, the whole workflow)."""
    out: dict[str, str] = {"": "flow", "main": "flow"}
    for name in flow.procedures:
        out[name] = "flow"
    for h in flow.handlers:
        out[h.name] = "global"
    for b in flow.workflow.blocks if flow.workflow else []:
        out[b.name] = f"block:{b.name}"
        for ev in b.events:
            out[ir.event_label(ev, b)] = f"block:{b.name}"
    return out


def owner_of(path: str, roots: dict[str, str]) -> str:
    root = path.split(".", 1)[0].split(":", 1)[0]
    return roots.get(root, "flow")


def effective_doc(flow: ir.Flow) -> dict[str, list[dict[str, Any]]]:
    """Every map block's effective event set (and the global set under "")."""
    sets = {"": global_set(flow)}
    for b in flow.workflow.blocks if flow.workflow else []:
        sets[b.name] = merge(flow, b)
    return {
        name: [
            {
                "key": e.key,
                "state": e.state,
                "priority": e.handler.priority,
                "mode": e.handler.mode,
                "label": e.label,
                "active": e.active,
                "safety_critical": e.key in ir.SAFETY_CRITICAL,
                "extension": e.extension_label,
            }
            for e in m.events
        ]
        for name, m in sets.items()
    }


def lint_doc(
    flow: ir.Flow,
    *,
    world: World | None,
    resolver: Resolver | None,
    detector: Detector | None = None,
) -> dict[str, Any]:
    findings = lint(flow, world=world, resolver=resolver, detector=detector)
    roots = owners(flow)
    counts = {"error": 0, "warning": 0, "info": 0}
    by_owner: dict[str, dict[str, int]] = {}
    items = []
    for f in findings:
        own = owner_of(f.path, roots)
        counts[f.severity] += 1
        c = by_owner.setdefault(own, {"error": 0, "warning": 0, "info": 0, "unsupported": 0})
        c[f.severity] += 1
        if f.rule == "bindings":
            c["unsupported"] += 1
        items.append(
            {
                "rule": f.rule,
                "severity": f.severity,
                "layer": f.layer,
                "path": f.path,
                "text": f.text,
                "message": f.message,
                "ack": f.ack,
                "owner": own,
            }
        )
    return {
        "flow_hash": ir.flow_hash(flow),
        "findings": items,
        "counts": counts,
        "by_owner": by_owner,
        "effective": effective_doc(flow),
        "world": {
            "server": world.server if world else None,
            "maps": sorted(world.sheets) if world else [],
        },
    }


def python_doc(flow: ir.Flow) -> dict[str, Any]:
    return {"flow_hash": ir.flow_hash(flow), "python": pyview.print_flow(flow)}


def maps_of(flow: ir.Flow) -> list[str]:
    """Every map a flow names (blocks, cells, map refs), for the sheets to load."""
    out: set[str] = set()
    for b in flow.workflow.blocks if flow.workflow else []:
        out.add(b.map.map)

    def scan(e: Any) -> None:
        for x in ir.sub_exprs(e):
            if isinstance(x, ir.Lit):
                for v in x.value if isinstance(x.value, list) else [x.value]:
                    if isinstance(v, ir.MapRef | ir.CellRef):
                        out.add(v.map)

    for lit in flow.variables.values():
        scan(lit)
    for site in ir.sites(flow):
        for _, e in ir.stmt_exprs(site.stmt):
            scan(e)
        if isinstance(site.stmt, ir.TakeExit) and site.stmt.exit.warp is not None:
            out.add(site.stmt.exit.warp.map)
    return sorted(out)


def world_doc(world: World, maps: list[str] | None = None) -> dict[str, Any]:
    """The pickers' data: keys, cells and the sheets' own labels (local data, never stored)."""
    sheets = {}
    for m, s in sorted(world.sheets.items()):
        if maps is not None and m not in maps:
            continue
        sheets[m] = {
            "town": s.town,
            "size": [s.walk.width, s.walk.height] if s.walk else None,
            "npcs": [
                {
                    "key": n.key,
                    "x": n.x,
                    "y": n.y,
                    "menu": list(n.menu),
                    "warps": [w.model_dump(mode="json") for w in n.warps],
                    "kafra": n.kafra.model_dump(mode="json") if n.kafra else None,
                }
                for n in s.npcs
            ],
            "warps": [w.model_dump(mode="json") for w in s.warps],
            "spawns": [sp.model_dump(mode="json") for sp in s.spawns],
            "flags": s.flags.model_dump(mode="json") if s.flags else None,
        }
    return {
        "server": world.server,
        "maps": sheets,
        "mobs": {str(k): {"label": m.label, "level": m.level} for k, m in world.mobs.items()},
        "items": {str(k): {"label": i.label, "kind": i.kind} for k, i in world.items.items()},
    }


def walk_rows(world: World, map_id: str) -> list[str] | None:
    s = world.sheet(map_id)
    return list(s.walk.rows) if s and s.walk else None


# --- the committed synthetic sample ---------------------------------------------------------------
def _examples() -> Any:
    return resources.files("poring_flow") / "examples"


def sample_flow() -> ir.Flow:
    return pyview.parse((_examples() / f"{SAMPLE}.flow").read_text(encoding="utf-8"))


def sample_world(maps: list[str] | None = None) -> World:
    root = Path(str(_examples() / "sheets"))
    names = maps if maps is not None else ["town_1", "field_1"]
    return load_world(SAMPLE_SERVER, names, root=root)
