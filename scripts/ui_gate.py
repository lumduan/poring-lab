#!/usr/bin/env python3
"""THE UI GATE (Batt 2026-10-09 ~15:20, walk@17 item 6, MANDATORY): before ANY typing, every
harness checks the client's UI state from PIXELS and never presses Enter into an unknown state.

Why: on 2026-10-09 (demonstrations 3.29a) a walk click opened an NPC's dialog; every Enter the
harness typed afterwards went into it (5 "next" + 5 menu choices), and the next run started on top
of it. Typing is the path that presses Enter, so the gate sits in ro_agent.open_chat (every
chat_line / gm / say / where_fix line) and in bench.close_chat.

What is read, on two FRESH frames that must agree, with the cursor parked away from the windows:
* an NPC dialog / menu: talk@1's T2 reader (poring_env.npc_dialog; proven 168 / 168 on held-out
  RDP frames, 2026-10-09 15:49), templates in data/ui_anchors/npc_dialog/;
* the four windows with cut anchors (status, skills, inventory, equipment; ADR-0011,
  open_window@1): data/ui_anchors, each looked for within HOME_PX of where the client reopens it
  (ui_anchors.CAPTURE_ORIGINS: the client reopens a window where it last was, and the lab never
  drags them). A full-frame search costs ~4 s per frame, too slow for every typed line.

Only KNOWN steps close anything, each followed by the same two-frame check:
* an NPC dialog showing CLOSE and no menu: Enter (talk@1's drives: every Enter on CLOSE became the
  server's npc_close_click);
* one of the four windows: its own L2 chord (open_window@1's toggle).
Anything else STOPS (ro_agent.Stop), nothing typed, a frame saved for a person: a dialog showing
NEXT (Enter would advance an unknown script), a menu (a choice is an NPC interaction), an unreadable
or unstable state, missing templates, a path without a PROVEN template set (below).
Known gaps (stated, not hidden): windows without a cut anchor (the options window, a shop, a
trade) are not seen by this gate, nor one of the four dragged more than HOME_PX from its home.

    ui_gate.py check          one live check (read only: no key; the cursor is parked)
    ui_gate.py clear          ensure_clear once (may press the KNOWN steps; else stops)
    ui_gate.py prove-windows  the positive case for the windows: each of the four opened by its
                              chord, then the gate must see it and close it by the same chord

PER PATH (2026-10-09, poring_env.ui_sets): the lock picks the template set. BACKEND=rdp -> the
RDP set in data/ui_anchors (unchanged); console -> the S2 set in data/ui_anchors/s2, used ONLY
while its proof.json says the windows and T2 are proven on S2 and every template file still has
the proven bytes; anything else (hold, no set, unproven, stale) -> UiUnknown, nothing typed.
The S2 set is cut and proven by these (docs/operations/s2-gate-templates.md):

    ui_gate.py status                         the lock's path and the S2 set's proof (read only)
    ui_gate.py bank-windows --out DIR --scene NAME [--rounds N]
        LIVE, chords only (no Enter, no typed line): per round, each of the four windows closed /
        opened by its own chord / closed again, frames (cursor parked) + labels.json from the
        steps. A person has judged the client clear first (no window, no dialog).
    ui_gate.py cut-windows --path s2 --cut-rounds 0,1 BANK [BANK ...]
        offline: each window's template from its first open frame of those rounds, its stable
        mask from the others (ui_anchors.cut_templates / stable_masks, ui_anchors_tool's cut)
    ui_gate.py prove-windows-offline --path s2 BANK [BANK ...]
        offline, on rounds the cut did NOT use: PASS writes the "windows" component of
        proof.json (a FAIL removes it)
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ro_agent as r  # noqa: E402

WINDOWS4 = ("status", "skills", "inventory", "equipment")  # == poring_env.ui_sets.GATE_WINDOWS
PARK = ((1250, 380), (1250, 300))  # talk1's rest points: right of the dialog's default place
LOG = r.ROOT / "data" / "ro_agent" / "ui_gate.jsonl"
FAIL_DIR = Path("/dev/shm/poring-lab-tmp/ui-gate")
MAX_STEPS = 4  # known closing steps per check (a dialog's CLOSE + up to three windows)
SETTLE_S = 0.6
HOME_PX = 12  # a window's search box around its home (CAPTURE_ORIGINS), each side
WINDOW_CLIENT = "kro-20211103-prere"  # the lab client's L2 build (rule_run.WINDOW_CLIENT)

# The S2 windows proof (prove-windows-offline), pre-registered 2026-10-09 from the RDP cut's margins
# (ui_anchors.WINDOWS: own 0.00, nearest other window 16.6, nothing open >= 20.2, max_distance 6):
# on every held-out frame a window's OWN distance at its home <= max_distance / OWN_SHARE, and
# every OTHER window's template >= max_distance * OTHER_FACTOR there (open or nothing open).
OWN_SHARE = 2.0  # own <= 3.0
OTHER_FACTOR = 2.0  # others >= 12.0
PROVE_MIN_OPEN = 3  # held-out frames per window with it open
PROVE_MIN_NONE = 6  # held-out frames with none of the four open
WINDOWS_CUT = "windows_cut.json"
BANK_LABELS = "labels.json"

_cache: dict[str, Any] = {}


class UiUnknown(r.Stop):
    """The gate could not establish a known, clear state: nothing was typed."""


def _set_root(path: str) -> Path:
    from poring_env import ui_sets

    return ui_sets.set_root(r.ROOT / "data" / "ui_anchors", path)


def _templates(path: str = "rdp") -> Any:
    from poring_env import npc_dialog as nd

    key = "nd" if path == "rdp" else f"nd:{path}"
    if key not in _cache:
        where = (
            r.ROOT / nd.TEMPLATE_DIR if path == "rdp" else _set_root(path) / nd.TEMPLATE_DIR.name
        )
        _cache[key] = nd.load_templates(where)
    return _cache[key]


def _registry(path: str = "rdp") -> Any:
    from poring_env import ui_anchors as ua

    key = "reg" if path == "rdp" else f"reg:{path}"
    if key not in _cache:
        _cache[key] = ua.default_registry(_set_root(path))
    return _cache[key]


def window_keys(window: str) -> list[str]:
    from poring_skills.resolve import load_l2

    return list(load_l2(WINDOW_CLIENT)["shortcut"]["window"][window]["keys"])


def decide(a: dict[str, Any], b: dict[str, Any]) -> dict[str, Any]:
    """PURE: what to do from two observations ({"npc": NpcUiState-like summary, "windows": [...]}).
    -> {"do": "clear" | "enter_close" | "chord", "window"?} or {"do": "stop", "why": ...}."""
    na, nb = a["npc"], b["npc"]
    if not (na["ok"] and nb["ok"]):
        why = na["reason"] if not na["ok"] else nb["reason"]
        return {"do": "stop", "why": f"npc_unreadable:{why}"}
    if na["sig"] != nb["sig"] or sorted(a["windows"]) != sorted(b["windows"]):
        return {"do": "stop", "why": "unstable"}
    dialog, menu = na.get("dialog"), na.get("menu")
    if menu is not None:
        return {"do": "stop", "why": "npc_menu_open"}
    if dialog is not None:
        if dialog.get("button") == "close":
            return {"do": "enter_close"}
        return {"do": "stop", "why": f"npc_dialog_open:{dialog.get('button') or 'no_button'}"}
    if a["windows"]:
        return {"do": "chord", "window": sorted(a["windows"])[0]}
    return {"do": "clear"}


def _park(agent: Any, k: int) -> None:
    gx, gy, _, _ = r.game_region()
    pu, pv = PARK[k % 2]
    agent.move(gx + pu - 3, gy + pv - 3)
    time.sleep(0.05)
    agent.move(gx + pu, gy + pv)
    time.sleep(SETTLE_S)


def observe(agent: Any, screen: Any, after_ns: int | None, k: int,
            park: bool = True, *, path: str) -> tuple[dict[str, Any], Any]:  # fmt: skip
    """Two readers on one fresh frame, with the ``path``'s template set (``_require_ready``)."""
    from poring_env import npc_dialog as nd

    if park:
        _park(agent, k)
    frame = np.ascontiguousarray(r.grab_after(screen, r.game_region(), after_ns)[..., :3])
    st = nd.state(frame, _templates(path))
    summ = st.summary()
    summ["sig"] = repr(st.signature())
    return {"npc": summ, "windows": windows_at_home(frame, _registry(path))}, frame


def home_distances(frame: Any, reg: Any) -> dict[str, float]:
    """Each of the four windows' best match distance within HOME_PX of its home (the registry's
    own match, on a small box instead of the whole frame); inf when the box does not fit or
    nothing matches. Windows without a template are left out."""
    from poring_env import ui_anchors as ua

    gray = ua.to_gray(frame)
    h, w = gray.shape
    out: dict[str, float] = {}
    for name in WINDOWS4:
        spec, tmpl = reg.windows[name], reg.templates.get(name)
        if tmpl is None:
            continue
        hx, hy = ua.CAPTURE_ORIGINS[name]
        tx, ty = hx + spec.template_offset[0], hy + spec.template_offset[1]
        th, tw = tmpl.shape
        x0, y0 = max(0, tx - HOME_PX), max(0, ty - HOME_PX)
        x1, y1 = min(w, tx + tw + HOME_PX), min(h, ty + th + HOME_PX)
        if x1 - x0 < tw or y1 - y0 < th:
            out[name] = float("inf")
            continue
        m = ua.match_template(gray[y0:y1, x0:x1], tmpl, reg.masks.get(name))
        out[name] = float("inf") if m is None else m.distance
    return out


def windows_at_home(frame: Any, reg: Any = None) -> list[str]:
    """Which of the four windows show within HOME_PX of their home (the registry's own match
    and threshold, on a small box instead of the whole frame)."""
    reg = reg if reg is not None else _registry()
    dist = home_distances(frame, reg)
    return sorted(n for n, d in dist.items() if d <= reg.windows[n].max_distance)


def _log(rec: dict[str, Any]) -> None:
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a") as fh:
        fh.write(json.dumps(rec) + "\n")


def _lock_backend() -> str:
    import record_session

    return str(record_session.read_lock(r.ROOT / "state").backend)


def _require_ready() -> str:
    """The template set for the lock's path ("rdp" | "s2"), ready to read; else UiUnknown.
    rdp: the RDP set, exactly as before. console: the S2 set, only while its proof says the
    windows and T2 are proven on S2 and no template changed since (poring_env.ui_sets)."""
    from poring_env import ui_sets

    backend = _lock_backend()
    try:
        path = ui_sets.path_for_backend(backend)
    except ui_sets.UnknownPath:
        raise UiUnknown(
            f"ui gate: no template set for the lock's {backend}: nothing typed"
        ) from None
    if path != "rdp":
        root = _set_root(path)
        why = ui_sets.problems(root, ui_sets.GATE_NEEDS)
        if why:
            raise UiUnknown(f"ui gate: the {path} template set is not proven ({'; '.join(why)}; "
                            "docs/operations/s2-gate-templates.md): nothing typed")  # fmt: skip
        dg = ui_sets.digest(root, ui_sets.GATE_NEEDS)
        if _cache.get(f"digest:{path}") != dg:  # re-cut and re-proven: load the new files
            _cache.pop(f"nd:{path}", None)
            _cache.pop(f"reg:{path}", None)
            _cache[f"digest:{path}"] = dg
    missing = _templates(path).missing
    if missing:
        raise UiUnknown(f"ui gate: no NPC dialog templates ({','.join(missing)}; talk@1 cut): "
                        "nothing typed")  # fmt: skip
    if not all(w in _registry(path).templates for w in WINDOWS4):
        raise UiUnknown("ui gate: a window anchor is missing (data/ui_anchors): nothing typed")
    return path


def ensure_clear(agent: Any, screen: Any, *, why: str) -> dict[str, Any]:
    """Return once the client shows no NPC dialog / menu and none of the four windows, closing
    them by KNOWN steps only; else raise UiUnknown. Every check and step is logged."""
    path = _require_ready()
    t0 = r.ns()
    steps: list[dict[str, Any]] = []
    after: int | None = t0
    for k in range(MAX_STEPS + 1):
        a, _ = observe(agent, screen, after, k, path=path)  # the cursor parked once per round ...
        b, frame = observe(agent, screen, r.ns(), k, park=False, path=path)  # ... a later frame
        d = decide(a, b)
        rec = {"t_ns": r.ns(), "why": why, "k": k, "decision": d, "npc": a["npc"],
               "windows": a["windows"]}  # fmt: skip
        if path != "rdp":
            rec["path"] = path
        _log(rec)
        if d["do"] == "clear":
            return {"clear": True, "steps": steps, "checks": k + 1,
                    "ms": round((r.ns() - t0) / 1e6)}  # fmt: skip
        if d["do"] == "stop" or k == MAX_STEPS:
            FAIL_DIR.mkdir(parents=True, exist_ok=True)
            shot = r.to_png(frame, FAIL_DIR / f"{time.strftime('%Y%m%d-%H%M%S')}.png")
            reason = d.get("why", "too_many_steps")
            raise UiUnknown(f"ui gate ({why}): {reason}; nothing typed, left for a person "
                            f"(frame {shot})")  # fmt: skip
        r.activate_client(agent, screen)
        if d["do"] == "enter_close":
            agent.keys("Enter")  # the KNOWN close: the dialog shows CLOSE on two frames, no menu
            steps.append({"step": "enter_close", "t_ns": r.ns()})
        else:
            agent.chord(*window_keys(d["window"]))  # its own toggle (open_window@1)
            steps.append({"step": "chord", "window": d["window"], "t_ns": r.ns()})
        after = r.ns()
        time.sleep(SETTLE_S)
    raise AssertionError("unreachable")


def prove_windows(agent: Any, screen: Any, path: str = "rdp") -> dict[str, Any]:
    """Each of the four windows opened by its own chord, seen by the gate (and by the full-frame
    locate, the registry's own search), then closed by ensure_clear. PASS: all four."""
    out: dict[str, Any] = {}
    first = ensure_clear(agent, screen, why="prove-windows:start")
    for w in WINDOWS4:
        r.activate_client(agent, screen)
        agent.chord(*window_keys(w))
        time.sleep(1.0)
        frame = np.ascontiguousarray(r.grab_after(screen, r.game_region(), r.ns())[..., :3])
        home = windows_at_home(frame, _registry(path))
        full = sorted(set(_registry(path).locate(frame)) & set(WINDOWS4))
        got = ensure_clear(agent, screen, why=f"prove-windows:{w}")
        out[w] = {"home": home, "full": full, "steps": got["steps"],
                  "pass": home == [w] and full == [w]
                  and [st.get("window") for st in got["steps"]] == [w]}  # fmt: skip
    out["start_steps"] = first["steps"]
    out["pass"] = all(out[w]["pass"] for w in WINDOWS4)
    return out


# --- the S2 set: bank (live, chords only), cut and prove (offline) -------------------------------


def _png(path: Path) -> Any:
    """A banked frame as BGR (ro_agent.to_png writes true RGB)."""
    from PIL import Image

    return np.ascontiguousarray(np.asarray(Image.open(path).convert("RGB"))[..., ::-1])


def _sha(path: Path) -> str:
    import hashlib

    return hashlib.sha256(path.read_bytes()).hexdigest()


def bank_items(banks: list[Path], path: str) -> list[dict[str, Any]]:
    """Every labelled frame of the banks taken on ``path`` (others are never used for its set),
    with its absolute file and sha256."""
    out = []
    for bank in banks:
        for it in json.loads((bank / BANK_LABELS).read_text()):
            if it.get("path") != path:
                continue
            f = bank / "frames" / str(it["file"])
            out.append({**it, "abs": f, "sha256": _sha(f), "bank": bank.name})
    return out


def bank_windows(agent: Any, screen: Any, out: Path, scene: str, rounds: int,
                 path: str) -> dict[str, Any]:  # fmt: skip
    """LIVE, chords only. Per round and window: 2 frames closed, its chord, 3 frames open, its
    chord, 2 frames closed; the label is the step taken (a person checks the frames: a window
    that was already open turns the labels round, and the prove then FAILS, never passes)."""
    frames = out / "frames"
    frames.mkdir(parents=True, exist_ok=True)
    lpath = out / BANK_LABELS
    labels: list[dict[str, Any]] = json.loads(lpath.read_text()) if lpath.exists() else []
    first = 1 + max((int(it["round"]) for it in labels), default=-1)
    k = 0

    def shot(rnd: int, tag: str, opened: str | None, n: int) -> None:
        nonlocal k
        for _ in range(n):
            _park(agent, k)
            k += 1
            img = np.ascontiguousarray(r.grab_after(screen, r.game_region(), r.ns())[..., :3])
            name = f"{rnd:02d}-{tag}-{r.ns()}.png"
            r.to_png(img, frames / name)
            labels.append({"file": name, "open": opened, "round": rnd, "scene": scene,
                           "path": path, "t_ns": r.ns()})  # fmt: skip

    for rnd in range(first, first + rounds):
        for w in WINDOWS4:
            shot(rnd, f"{w}-before", None, 2)
            r.activate_client(agent, screen)
            agent.chord(*window_keys(w))
            time.sleep(1.0)
            shot(rnd, f"{w}-open", w, 3)
            r.activate_client(agent, screen)
            agent.chord(*window_keys(w))
            time.sleep(1.0)
            shot(rnd, f"{w}-after", None, 2)
        lpath.write_text(json.dumps(labels, indent=1) + "\n")
    return {"bank": str(out), "rounds": list(range(first, first + rounds)), "frames": len(labels),
            "path": path, "scene": scene}  # fmt: skip


def cut_windows(banks: list[Path], cut_rounds: set[int], root: Path,
                path: str = "s2") -> dict[str, Any]:  # fmt: skip
    """Each window's template from its first open frame in ``cut_rounds`` (its home,
    CAPTURE_ORIGINS), the stable mask from every other open frame of it there. Writes nothing
    unless all four have >= 2 frames."""
    from poring_env import ui_anchors as ua

    items = [it for it in bank_items(banks, path) if int(it["round"]) in cut_rounds]
    per: dict[str, list[dict[str, Any]]] = {w: [] for w in WINDOWS4}
    for it in sorted(items, key=lambda it: (int(it["round"]), int(it["t_ns"]))):
        if it.get("open") in per:
            per[str(it["open"])].append(it)
    lacking = [w for w, its in per.items() if len(its) < 2]
    rep: dict[str, Any] = {"cut_rounds": sorted(cut_rounds), "frames": {w: len(v) for w, v in
                                                                         per.items()}}  # fmt: skip
    if lacking:
        rep["verdict"] = f"NOT READY: < 2 open frames of {lacking}; nothing written"
        return rep
    templates: dict[str, Any] = {}
    masks: dict[str, Any] = {}
    for w, its in per.items():
        origin = {w: ua.CAPTURE_ORIGINS[w]}
        t = ua.cut_templates(_png(its[0]["abs"]), origin, ua.WINDOWS)
        variants = [ua.cut_templates(_png(it["abs"]), origin, ua.WINDOWS) for it in its[1:]]
        templates.update(t)
        masks.update(ua.stable_masks(t, variants))
    ua.save_templates(root, templates, masks)
    used = sorted({str(it["sha256"]) for its in per.values() for it in its})
    rounds = sorted({(str(it["bank"]), int(it["round"])) for it in items})  # never held out
    meta = {"frames": used, "rounds": rounds, "cut_rounds": sorted(cut_rounds),
            "cut_at": time.strftime("%Y-%m-%dT%H:%M:%S%z")}  # fmt: skip
    (root / WINDOWS_CUT).write_text(json.dumps(meta, indent=1) + "\n")
    rep["stable_share"] = {w: round(float(m.mean()), 3) for w, m in masks.items()}
    rep["verdict"] = "CUT (prove on held-out rounds next)"
    return rep


def judge_frame(dist: dict[str, float], opened: str | None, reg: Any,
                full: list[str] | None) -> list[str]:  # fmt: skip
    """PURE: why a labelled frame fails the pre-registered windows bar (empty = it passes)."""
    bad = []
    for name in WINDOWS4:
        d = dist.get(name, float("inf"))
        lim = reg.windows[name].max_distance
        if name == opened:
            if not d <= lim / OWN_SHARE:
                bad.append(f"own {name} {d:.2f} > {lim / OWN_SHARE:.2f}")
        elif not d >= lim * OTHER_FACTOR:
            bad.append(f"other {name} {d:.2f} < {lim * OTHER_FACTOR:.2f}")
    home = sorted(n for n, d in dist.items() if d <= reg.windows[n].max_distance)
    want = [] if opened is None else [opened]
    if home != want:
        bad.append(f"home {home} != {want}")
    if full is not None and full != want:
        bad.append(f"full-frame {full} != {want}")
    return bad


def prove_windows_offline(banks: list[Path], root: Path, path: str = "s2",
                          full: bool = True) -> dict[str, Any]:  # fmt: skip
    """The S2 windows proof on banked frames of ROUNDS the cut did not use (a cut round is out
    whole, its closed frames too): every frame meets the bar (judge_frame), >= PROVE_MIN_OPEN
    per window, >= PROVE_MIN_NONE with none open."""
    from poring_env import ui_anchors as ua
    from poring_env import ui_sets

    before = ui_sets.file_hashes(root, "windows")
    try:
        meta = json.loads((root / WINDOWS_CUT).read_text())
        used = set(meta["frames"])
        rounds = {(str(b), int(k)) for b, k in meta["rounds"]}
    except (OSError, ValueError, KeyError, TypeError):
        return {"verdict": f"REFUSED: no {WINDOWS_CUT} in {root} (cut-windows first)"}
    reg = ua.default_registry(root)
    if not all(w in reg.templates for w in WINDOWS4):
        return {"verdict": "FAIL: a window template is missing", "pass": False, "before": before}
    items = bank_items(banks, path)
    held = [it for it in items if it["sha256"] not in used
            and (str(it["bank"]), int(it["round"])) not in rounds]  # fmt: skip
    counts = {str(w): 0 for w in (*WINDOWS4, None)}
    fails: list[dict[str, Any]] = []
    worst = {"own_max": 0.0, "other_min": float("inf")}
    scenes: set[str] = set()
    for it in held:
        frame = _png(it["abs"])
        dist = home_distances(frame, reg)
        opened = it.get("open")
        fl = sorted(set(reg.locate(frame)) & set(WINDOWS4)) if full else None
        bad = judge_frame(dist, opened, reg, fl)
        counts[str(opened)] += 1
        scenes.add(str(it.get("scene")))
        for n, d in dist.items():
            if n == opened:
                worst["own_max"] = max(worst["own_max"], d)
            else:
                worst["other_min"] = min(worst["other_min"], d)
        if bad:
            fails.append({"file": it["file"], "bank": it["bank"], "why": bad})
    lacking = [w for w in WINDOWS4 if counts[w] < PROVE_MIN_OPEN]
    if counts["None"] < PROVE_MIN_NONE:
        lacking.append("none")
    ok = not fails and not lacking
    verdict = ("PASS" if ok else "FAIL" if fails
               else f"INCOMPLETE: too few held-out frames of {lacking}")  # fmt: skip
    return {"verdict": verdict, "pass": ok, "held_out": len(held), "excluded_cut": len(items)
            - len(held), "counts": counts, "scenes": sorted(scenes), "fails": fails[:20],
            "own_max": round(worst["own_max"], 3), "other_min": round(worst["other_min"], 3),
            "bar": {"own_max": f"max_distance / {OWN_SHARE:g}",
                    "other_min": f"max_distance * {OTHER_FACTOR:g}",
                    "min_open": PROVE_MIN_OPEN, "min_none": PROVE_MIN_NONE, "full": full},
            "before": before}  # fmt: skip


def _main_s2(argv: list[str]) -> int:
    from poring_env import ui_sets

    ap = argparse.ArgumentParser(prog="ui_gate.py", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)  # fmt: skip
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status")
    b = sub.add_parser("bank-windows")
    b.add_argument("--out", type=Path, required=True)
    b.add_argument("--scene", required=True)
    b.add_argument("--rounds", type=int, default=1)
    c = sub.add_parser("cut-windows")
    c.add_argument("--path", choices=("s2",), required=True)
    c.add_argument("--cut-rounds", required=True, help="comma-separated round numbers, e.g. 0,1")
    c.add_argument("banks", nargs="+", type=Path)
    p = sub.add_parser("prove-windows-offline")
    p.add_argument("--path", choices=("s2",), required=True)
    p.add_argument("--no-full", action="store_true", help="skip the full-frame locate (~4 s/frame)")
    p.add_argument("banks", nargs="+", type=Path)
    a = ap.parse_args(argv)
    out: dict[str, Any]
    if a.cmd == "status":
        backend = _lock_backend()
        try:
            lock_path: str = ui_sets.path_for_backend(backend)
        except ui_sets.UnknownPath as exc:
            lock_path = f"refused: {exc}"
        out = {
            "lock": backend,
            "path": lock_path,
            "s2": ui_sets.status(_set_root("s2")),
            "gate_ready_on_s2": not ui_sets.problems(_set_root("s2"), ui_sets.GATE_NEEDS),
        }
    elif a.cmd == "bank-windows":
        backend = _lock_backend()
        try:
            path = ui_sets.path_for_backend(backend)
        except ui_sets.UnknownPath as exc:
            raise r.Stop(f"bank-windows: {exc}: nothing pressed") from None
        with r.session("ui-gate-bank") as (agent, screen):
            out = bank_windows(agent, screen, a.out, a.scene, a.rounds, path)
    elif a.cmd == "cut-windows":
        rounds = {int(x) for x in a.cut_rounds.split(",") if x.strip()}
        out = cut_windows(a.banks, rounds, _set_root(a.path), a.path)
    else:
        root = _set_root(a.path)
        out = prove_windows_offline(a.banks, root, a.path, full=not a.no_full)
        before = out.pop("before", None)
        if before is not None:
            evidence = {k: v for k, v in out.items() if k not in ("fails",)}
            evidence["banks"] = [str(x) for x in a.banks]
            out["proof"] = ui_sets.record(
                root,
                "windows",
                bool(out["pass"]),
                evidence,
                before,
                command="ui_gate.py prove-windows-offline",
            )["verdict"]
    print(json.dumps(out, indent=1, default=str))
    if a.cmd in ("status", "bank-windows"):
        return 0
    if a.cmd == "cut-windows":
        return 0 if str(out["verdict"]).startswith("CUT") else 1
    return 0 if out.get("proof") == "PASS" else 1  # the RECORDED verdict, not the computed one


S2_COMMANDS = ("status", "bank-windows", "cut-windows", "prove-windows-offline")


def main() -> int:
    cmd = sys.argv[1:]
    if cmd and cmd[0] in S2_COMMANDS:
        return _main_s2(cmd)
    if cmd not in (["check"], ["clear"], ["prove-windows"]):
        print(__doc__)
        return 2
    path = _require_ready()
    with r.session("ui-gate-check") as (agent, screen):
        if cmd == ["check"]:
            a, _ = observe(agent, screen, r.ns(), 0, path=path)
            b, _ = observe(agent, screen, r.ns(), 1, path=path)
            print(json.dumps({"decision": decide(a, b), "a": a, "b": b}, indent=1))
        elif cmd == ["clear"]:
            print(json.dumps(ensure_clear(agent, screen, why="cli"), indent=1))
        else:
            res = prove_windows(agent, screen, path)
            print(json.dumps(res, indent=1))
            return 0 if res["pass"] else 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
