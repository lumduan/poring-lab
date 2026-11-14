"""The SETTING BLOCKS' lint (live-blocks.md section 12; Batt 2026-11-14 ~15:2x: "make them ALL
blocks, no hardcoding"): a project variable named like a setting (poring_flow.settings) is a
setting of the runner's hunt core. In words, on the block, in the editor and before any Run (the
backend's POST /flows/run/project refuses a project with an error):

- ``settings`` ERROR: a setting's value is not of its kind or outside its range / grid
  ("or at once under HP: 95 % is not from 20 % to 90 %");
- ``settings`` WARNING: a variable whose name looks like a TYPO of a setting's (another case, or a
  near spelling: "potion_bellow"); any other name is an ordinary variable and says nothing;
- ``settings`` WARNING: a hotbar key as a variable (heal_key = "F2"): the keys come from the
  functions dungeon_hunt names, never from a setting;
- ``settings_clash`` ERROR: the values a map node's hunt core takes cannot run together
  (settings.clash: two roles on one key, the HUD's fresh box not faster than the detector);
- ``settings_safety`` WARNING (matpilot round 20 #3): a SAFETY switch (one with ``warn``) that is
  off where a hunt core reads it ("npc_guard (...) is off: a strike near an NPC may open its
  dialog and stop the run"): the chip and the /maps card count it;
- ``settings_use`` INFO: a setting that is not in use on a map node while another is off or set
  otherwise ("not in use on xmas_dun02 while Batt's Knife swap (knife_swap) is off"), or that the
  box replaces in a Run (live.takeovers: drink plays the potion), or a node whose settings no hunt
  core reads.

One setting on two tabs of one node never gets here (matpilot round 20 #5): a node's tabs are ONE
namespace, so project.validate refuses it naming both tabs ("D0_PX is defined twice on xmas_dun02:
a variable in tab aim and a variable in tab loot"), and the block editor refuses the second block
at once (blocks.ts tabFromWorkspace).

``notes`` (matpilot round 20 #3, #4a) is the same facts per setting BLOCK, in a few words: its
"unused" row ("not used here: the drink event plays it", "not used while npc_guard is off") and its
"safety" row (the warning while it is off). POST /flows/lint sends them (``settings``) for the
blocks to show, greyed, and the Python view puts them on the setting's line as a comment: the
lint, the block and the Python never disagree, because they are one computation.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from poring_flow import settings as st

if TYPE_CHECKING:
    from poring_flow.project import Compiled, Project, Where

Found = tuple[str, str, "Where", str, int]  # (rule, severity, where, text, layer)


def levels_of(p: Project, node_id: str) -> list[st.Level]:
    """The levels a run on ``node_id`` reads, highest first: that node's tabs, then Global's (the
    project model's name rule; ``settings.node_values`` decides)."""
    from poring_flow.project import GlobalNode

    nodes = [n for n in p.nodes if n.id == node_id]
    nodes += [n for n in p.nodes if isinstance(n, GlobalNode) and n.id != node_id]
    return [st.Level(f"{n.id}/{t.name}", n.id, t.name, {k: v.value for k, v in t.vars.items()})
            for n in nodes for t in n.tabs]  # fmt: skip


def node_values(p: Project, node_id: str, keys: dict[str, str] | None = None) -> st.NodeValues:
    """The settings a hunt core on ``node_id`` takes (the node's blocks > Global's > the default),
    the flow's keys over them when given."""
    nv = st.node_values(levels_of(p, node_id))
    if keys:
        vals = st.with_keys(nv.vals, keys)
        return st.NodeValues(vals, {**nv.src, **{k: "flow" for k in st.KEY_FIELDS}}, nv.problems)
    return nv


def _hunt_nodes(c: Compiled) -> list[str]:
    from poring_flow import live

    if c.flow is None:
        return []
    out: list[str] = []
    for b, _a in live.runner_blocks(c.flow):
        if b not in out:
            out.append(b)
    return out


Notes = dict[str, dict[str, str]]  # a setting block's path ("node/tab/var") -> its rows' words


def findings(p: Project, c: Compiled) -> list[Found]:
    return _analyse(p, c)[0]


def notes(p: Project, c: Compiled) -> Notes:
    """Per setting block (its path, "xmas_dun02/survival/potion_below"): {"unused": its short
    not-used words, "safety": a safety switch's warning while it is off} -- the lint's own facts
    (findings), for the blocks (POST /flows/lint ``settings``) and the Python view's comments."""
    return _analyse(p, c)[1]


def _note(out: Notes, path: str, key: str, text: str) -> None:
    out.setdefault(path, {}).setdefault(key, text)


def _analyse(p: Project, c: Compiled) -> tuple[list[Found], Notes]:
    from poring_flow.project import MapNode, Where
    from poring_flow.project import runner_keys as _runner_keys

    out: list[Found] = []
    rows: Notes = {}
    hunts = _hunt_nodes(c)
    for n in p.nodes:
        set_here = False
        for t in n.tabs:
            for name, lit in t.vars.items():
                w = Where(n.id, t.name, name)
                f = st.BY_VAR.get(name)
                if f is None:
                    g = st.typo_of(name)
                    if g is not None:
                        out.append(("settings", "warning", w, f"{name} is not a setting: did you "
                                    f"mean {g.var} ({g.words})? As written it is an ordinary "
                                    "variable, and the hunt core does not read it", 1))  # fmt: skip
                    continue
                if not f.block:
                    out.append(("settings", "warning", w, f"{name} is not read: the hunt core "
                                "takes its hotbar keys from the functions dungeon_hunt names "
                                "(heal=, fly=, knife_on=, ... their press_key), not from a "
                                "setting", 1))  # fmt: skip
                    continue
                set_here = True
                why = st.problem_of(f, lit.value)
                if why:
                    out.append(("settings", "error", w, f"{name}: {why}", 1))
        if set_here and isinstance(n, MapNode) and n.id not in hunts:
            out.append(("settings_use", "info", Where(n.id), f"{n.id}'s settings are not read: "
                        "only hunt with the runner (dungeon_hunt) reads them, and this node's "
                        "main has none", 3))  # fmt: skip
            for t in n.tabs:
                for name in t.vars:
                    f = st.BY_VAR.get(name)
                    if f is not None and f.block:
                        _note(rows, Where(n.id, t.name, name).path, "unused",
                              "not used: no hunt with the runner on this map reads it")  # fmt: skip
    for node in hunts:
        rk = _runner_keys(p, node, c)
        nv = node_values(p, node, dict(rk.keys) if rk.keys else None)
        why = st.clash(nv.vals)
        if why:
            out.append(("settings_clash", "error", Where(node), f"the settings {node}'s hunt "
                        f"core takes cannot run together: {why}", 1))  # fmt: skip
        out += _use(p, c, node, nv, rows)
    return out, rows


def _replaced(c: Compiled, node: str) -> dict[str, tuple[str, str, str]]:
    """The settings the box replaces in a Run on ``node`` (live.takeovers): name -> (who plays it,
    "event" / "function", what of the runner's it replaces)."""
    from poring_flow import live

    out: dict[str, tuple[str, str, str]] = {}
    tk = live.takeovers(c.flow, node) if c.flow is not None else None
    for row in (tk or {}).get("takeovers") or []:
        by = row.get("by")
        for s in row.get("settings") or []:
            if by and s not in out:
                out[s] = (str(by), str(row.get("kind") or "function"), str(row.get("replaces")))
    return out


def _use(p: Project, c: Compiled, node: str, nv: st.NodeValues, rows: Notes) -> list[Found]:
    """INFO on each setting block a run on ``node`` reads that it does not use; a WARNING on each
    safety switch it reads off. ``rows`` gets each block's short words (notes)."""
    from poring_flow.project import Where

    out: list[Found] = []
    replaced = _replaced(c, node)
    for f in st.BLOCKS:
        where = nv.src.get(f.name, "default")
        if f.warn and f.kind == "switch" and nv.vals.get(f.name) is False \
                and st.in_use(f.name, nv.vals):  # fmt: skip
            n_id, _, tab = where.partition("/")
            w = Where(node) if where == "default" else Where(n_id, tab, f.var)
            on = "" if n_id == node else f" on {node}"
            out.append(("settings_safety", "warning", w, f"{f.var} ({f.words}) is off{on}: "
                        f"{f.warn}", 1))  # fmt: skip
            if where != "default":
                _note(rows, w.path, "safety", f.warn)
        if where == "default":
            continue
        n_id, _, tab = where.partition("/")
        w = Where(n_id, tab, f.var)
        on = "" if n_id == node else f" on {node}"
        why = st.not_in_use_why(f.name, nv.vals)
        if why is not None:
            out.append(("settings_use", "info", w, f"{f.var} ({f.words}) is not in use{on} while "
                        f"{why}: the runner is not given it", 3))  # fmt: skip
            short = st.unused_words(f.name, nv.vals) or "not used"
            _note(rows, w.path, "unused", short.replace("not used", f"not used{on}", 1))
        elif f.name in replaced:
            by, kind, replaces = replaced[f.name]
            out.append(("settings_use", "info", w, f"{f.var} ({f.words}) is not used in a Run of "
                        f"this box{on}: {by} plays {replaces} instead (the value counts only in a "
                        "box without it)", 3))  # fmt: skip
            _note(rows, w.path, "unused", f"not used {'here' if not on else on[1:]}: the {by} "
                  f"{kind} plays it")  # fmt: skip
    return out


def doc(p: Project, node_id: str, keys: dict[str, str] | None = None) -> dict[str, Any]:
    """A node's settings as the pages show them: each value and its level."""
    nv = node_values(p, node_id, keys)
    return {"values": nv.vals, "src": nv.src, "problems": list(nv.problems)}
