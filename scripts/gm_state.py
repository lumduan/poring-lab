#!/usr/bin/env python3
"""The GM's FIXED TEST STATE (Batt 2026-10-09 ~16:00): restored at every run start (and at every
loot@1 trial start), checked from pixels, and recorded.

Why: loot@1's pilot 2 killed a Poring and the GM levelled up (Base Lv 1 -> 2; HP 40 -> 45, status
points, the client's level-up icon and badges). "The GM's level is now an uncontrolled variable.
Restore a fixed test state (reset or set the level/points by GM command, clear the badges by known
steps) and record the GM's state at each run start."

The fixed state: Base Lv 1 and Job Lv 1, full HP / SP (@heal). Lowering a level by
`@baselevelup -N` / `@joblevelup -N` takes back that level's status / skill points and sets the EXP
to 0 (pinned rAthena atcommand.cpp, ACMD_FUNC(baselevelup)); group 20 has both commands since
2026-10-09 (groups.yml). At Lv 1 the server answers "can't go any lower" and changes nothing.
Job EXP is NOT fixed (it keeps rising at Job Lv 1): it is recorded, not restored.

The check (pixels, two fresh frames that must agree): the Basic Information window's two level
lines ("Base Lv. N" / "Job Lv. N" text, left of the EXP bars) against a template cut once at
Lv 1 / 1, by the COUNT of strongly differing pixels (`gm_state.py cut`, data/ui_anchors/gm_state/,
client pixels: gitignored). The badges and the
level-up icon cleared when the status window opened (2026-10-09 16:02, ui_gate prove-windows):
the gate's known step, not checked here (no template of them).

The record (every run start): the match distance, whether a restore was needed, the weight readout
(poring_env.weight, two equal reads) and a crop of the Basic Information window (in the session
dir). The packets judge offline: after a restore the server sends the new levels and points.

    gm_state.py check     read only: the level lines vs the template
    gm_state.py restore   ensure_fixed once (types the restore lines only when the check fails)
    gm_state.py cut       cut the Lv 1 / 1 template from the CURRENT frame (a person has checked
                          the screen shows Base Lv. 1 and Job Lv. 1)

PER PATH (2026-10-09, poring_env.ui_sets; as ui_gate): the lock picks the template set. rdp ->
data/ui_anchors/gm_state/ (unchanged); console -> data/ui_anchors/s2/gm_state/, used ONLY while
data/ui_anchors/s2/proof.json says "gm_levels" (the level lines) / "gm_notices" (the notices) are
proven on S2 with the same bytes; anything else -> Stop. The S2 templates
(docs/operations/s2-gate-templates.md):

    gm_state.py bank --out DIR --levels fixed|not_fixed --notices none|badge,levelup_icon
                     --scene NAME [--n 4]
        LIVE, no input at all: n client frames + labels.json; the labels are a PERSON's reading
        of the client at that moment (the same standard as `cut`)
    gm_state.py cut --path s2 --png FRAME             the level lines from a banked Lv 1 / 1 frame
    gm_state.py cut-notices --path s2 --with FRAME --without FRAME
        each notice's template from a frame showing both, its mask = its own pixels (those that
        differ from a frame without them by > NOTICE_DIFF)
    gm_state.py prove --path s2 BANK [BANK ...]
        offline, frames NOT used by the cuts: PASS writes "gm_levels" / "gm_notices" (each on its
        own bar) into proof.json; a FAIL removes it
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ro_agent as r  # noqa: E402

# client px (basic_info at its home (0, 0)): the "Base Lv. N" / "Job Lv. N" text, left of the
# EXP bars (measured 2026-10-09 on RDP frames: text x 16-72, rows y 87-97 and 98-108)
LEVEL_BOX = (14, 85, 68, 25)  # x, y, w, h
BASIC_INFO_BOX = (0, 0, 220, 140)
TEMPLATE = r.ROOT / "data" / "ui_anchors" / "gm_state" / "levels_1_1.npy"  # the rdp set
LEVELS_REL = "gm_state/levels_1_1.npy"  # inside another path's set root (poring_env.ui_sets)
NOTICE_FILES = {"badge": "badge.npy", "badge_mask": "badge_mask.npy",
                "levelup_icon": "levelup_icon.npy",
                "levelup_icon_mask": "levelup_mask.npy"}  # fmt: skip
CUT_META = "cut.json"  # the S2 cuts' source frames (sha256): never used to prove
BANK_LABELS = "labels.json"
# The S2 proof's bars (pre-registered 2026-10-09): every held-out frame right, with margins; a
# changed digit gives "tens" of strongly differing pixels (above), so a not-fixed frame must sit
# well clear of MATCH.
NOT_FIXED_MIN = 10  # a not-fixed frame differs in at least this many pixels
PROVE_MIN_LEVELS = 4  # held-out frames of each: fixed, not fixed
PROVE_MIN_NOTICES = 3  # held-out frames showing both notices, and showing none
# A mean difference over the box dilutes one changed digit (~20 ink px of ~1700): count the pixels
# that differ strongly instead. RDP codec noise stays far below DIFF_LEVEL; a changed digit gives
# tens of such pixels.
DIFF_LEVEL = 60.0  # gray levels
MATCH = 4  # at most this many strongly differing pixels
RESTORE = ("@baselevelup -98", "@joblevelup -49", "@heal")
SETTLE_S = 2.0
# The client's NOTICES after a level change (either way): a badge on the first shortcut icon and the
# level-up icon in the corner. Opening the status window clears both (2026-10-09 16:53, checked on a
# frame); ui_gate then closes it by its own chord. Client px, measured that day by differencing a
# frame with the notices (16:40) and one without (16:53).
# Both are judged on their OWN pixels only (a template + the mask of the pixels that differ between
# a frame with the notice and one without, both cut in prontera): the shortcut window is see-through
# around and slightly through its icons, so a clean-reference comparison read the field's grass as a
# badge (loot@1 P3 trial 0, 2026-10-09 16:55: stopped, nothing else typed).
BADGE_BOX = (7, 145, 39, 40)  # x, y, w, h: the first shortcut icon, with the badge's corner
ICON_BOX = (1235, 675, 45, 45)  # the level-up icon over the scene
NOTICE_DIFF = 40.0  # gray levels
NOTICE_SHARE = 0.8  # this share of a notice's own pixels matching its template = it is shown


def to_gray(bgr: Any) -> Any:
    return np.asarray(bgr[..., :3], np.float32) @ np.array([0.114, 0.587, 0.299], np.float32)


def crop(frame: Any, box: tuple[int, int, int, int] = LEVEL_BOX) -> Any:
    x, y, w, h = box
    return to_gray(frame)[y : y + h, x : x + w]


def distance(frame: Any, template: Any) -> float:
    """The number of pixels of the level lines that differ from the template by > DIFF_LEVEL."""
    c = crop(frame)
    if c.shape != template.shape:
        return float("inf")
    return float((np.abs(c - template) > DIFF_LEVEL).sum())


def decide(d1: float, d2: float) -> str:
    """PURE: 'fixed' when both frames match, 'restore' when both differ, 'unstable' otherwise."""
    if d1 <= MATCH and d2 <= MATCH:
        return "fixed"
    if d1 > MATCH and d2 > MATCH:
        return "restore"
    return "unstable"


def _frames(screen: Any) -> tuple[Any, Any]:
    a = np.ascontiguousarray(r.grab_after(screen, r.game_region(), r.ns())[..., :3])
    b = np.ascontiguousarray(r.grab_after(screen, r.game_region(), r.ns())[..., :3])
    return a, b


def _path() -> str:
    """The lock's template path ("rdp" | "s2"), or Stop (poring_env.ui_sets)."""
    import record_session

    from poring_env import ui_sets

    backend = str(record_session.read_lock(r.ROOT / "state").backend)
    try:
        return ui_sets.path_for_backend(backend)
    except ui_sets.UnknownPath:
        raise r.Stop(f"gm_state: no template set for the lock's {backend}: nothing checked or "
                     "typed") from None  # fmt: skip


def _root(path: str) -> Path:
    from poring_env import ui_sets

    return ui_sets.set_root(r.ROOT / "data" / "ui_anchors", path)


def _template_path(path: str) -> Path:
    return TEMPLATE if path == "rdp" else _root(path) / LEVELS_REL


def _require_proven(path: str, needs: tuple[str, ...]) -> None:
    """rdp: nothing (its set is the one proven on RDP). Any other path: its proof, or Stop."""
    from poring_env import ui_sets

    if path == "rdp":
        return
    why = ui_sets.problems(_root(path), needs)
    if why:
        raise r.Stop(f"gm_state: the {path} template set is not proven ({'; '.join(why)}; "
                     "docs/operations/s2-gate-templates.md)")  # fmt: skip


def _template(path: str | None = None) -> Any:
    from poring_env import ui_sets

    path = path if path is not None else _path()
    _require_proven(path, ui_sets.GM_LEVELS_NEEDS)
    tp = _template_path(path)
    if not tp.exists():
        raise r.Stop(f"gm_state: no Lv 1 / 1 template ({tp}): run `gm_state.py cut` first")
    return np.load(tp)


def require_ready() -> str:
    """Everything ensure_fixed reads, for the lock's path (no input, no frame): the level lines'
    template and the notices' references, proven when the path is not rdp. Returns the path."""
    from poring_env import ui_sets

    path = _path()
    _require_proven(path, ui_sets.GM_LEVELS_NEEDS + ui_sets.GM_NOTICES_NEEDS)
    _template(path)
    d = _template_path(path).parent
    missing = [f for f in NOTICE_FILES.values() if not (d / f).exists()]
    if missing:
        raise r.Stop(f"gm_state: no notice references in {d} ({', '.join(missing)})")
    return path


def check(screen: Any) -> dict[str, Any]:
    t = _template()
    a, b = _frames(screen)
    d1, d2 = distance(a, t), distance(b, t)
    return {"decision": decide(d1, d2), "dist": [round(d1, 2), round(d2, 2)], "frames": (a, b)}


def _weight(frames: tuple[Any, Any]) -> list[int] | None:
    """The weight readout, two equal reads on the two frames (poring_env.weight), or None."""
    from poring_env import weight as wt

    path = _path()
    gpath = (r.ROOT / wt.DEFAULT_TEMPLATES if path == "rdp"
             else _root(path) / wt.DEFAULT_TEMPLATES.name)  # fmt: skip
    if path != "rdp" and not gpath.exists():
        return None  # recorded, not gated: RDP-cut glyphs are never read on another path's frames
    glyphs = wt.load_weight_glyphs(gpath)
    v = wt.stable_value([wt.read_weight(f, glyphs) for f in frames])
    return None if v is None else list(v)


def notices(frame: Any, refs: dict[str, Any]) -> list[str]:
    """PURE: which notices show ("badge", "levelup_icon"): each by its own pixels matching its
    template (``refs[name]``, ``refs[name + "_mask"]``), whatever the scene behind."""
    out = []
    for name, box in (("badge", BADGE_BOX), ("levelup_icon", ICON_BOX)):
        m = refs[f"{name}_mask"]
        near = np.abs(crop(frame, box) - refs[name]) < NOTICE_DIFF
        if m.sum() and float((near & m).sum()) / float(m.sum()) >= NOTICE_SHARE:
            out.append(name)
    return out


def _notice_refs(path: str | None = None) -> dict[str, Any]:
    from poring_env import ui_sets

    path = path if path is not None else _path()
    _require_proven(path, ui_sets.GM_NOTICES_NEEDS)
    d = _template_path(path).parent
    return {"badge": np.load(d / "badge.npy"), "badge_mask": np.load(d / "badge_mask.npy"),
            "levelup_icon": np.load(d / "levelup_icon.npy"),
            "levelup_icon_mask": np.load(d / "levelup_mask.npy")}  # fmt: skip


def clear_notices(agent: Any, screen: Any, *, why: str) -> dict[str, Any]:
    """The known step: open the status window by its chord, ui_gate closes it; then no notice
    may show."""
    import ui_gate

    refs = _notice_refs()
    a, b = _frames(screen)
    seen = sorted(set(notices(a, refs)) & set(notices(b, refs)))
    if not seen:
        return {"notices": [], "cleared": False}
    r.activate_client(agent, screen)
    agent.chord(*ui_gate.window_keys("status"))
    time.sleep(1.2)
    ui_gate.ensure_clear(agent, screen, why=f"{why}:clear-notices")
    a, b = _frames(screen)
    left = sorted(set(notices(a, refs)) | set(notices(b, refs)))
    if left:
        raise r.Stop(f"gm_state ({why}): the notices {left} did not clear after the status window")
    return {"notices": seen, "cleared": True}


def ensure_fixed(agent: Any, screen: Any, *, why: str,
                 out_dir: Path | None = None) -> dict[str, Any]:  # fmt: skip
    """The fixed state, restored by GM command when the level lines differ; else r.Stop."""
    rec: dict[str, Any] = {"why": why, "t_ns": r.ns(), "restored": False}
    got = check(screen)
    if got["decision"] == "unstable":
        time.sleep(0.5)
        got = check(screen)
    rec["before"] = got["dist"]
    if got["decision"] != "fixed":
        for cmd in RESTORE:
            r.gm(agent, screen, cmd)
        time.sleep(SETTLE_S)
        rec["restored"] = True
        got = check(screen)
        rec["after"] = got["dist"]
        if got["decision"] != "fixed":
            raise r.Stop(f"gm_state ({why}): the GM is not at Base Lv 1 / Job Lv 1 after "
                         f"the restore (differing px {got['dist']}, match <= {MATCH})")  # fmt: skip
    rec["notices"] = clear_notices(agent, screen, why=why)
    got = check(screen)  # the level lines again, after the status window came and went
    if got["decision"] != "fixed":
        raise r.Stop(f"gm_state ({why}): the level lines changed after the notices step")
    frame = got["frames"][1]
    rec["weight"] = _weight(got["frames"])
    if out_dir is not None:
        out_dir.mkdir(parents=True, exist_ok=True)
        x, y, w, h = BASIC_INFO_BOX
        path = out_dir / f"gm-state-{rec['t_ns']}.png"
        r.to_png(np.ascontiguousarray(frame[y : y + h, x : x + w]), path)
        rec["basic_info_crop"] = str(path)
    rec["fixed"] = True
    return rec


# --- the S2 set: bank (live, no input), cut and prove (offline) -----------------------------------


def _png(path: Path) -> Any:
    """A banked frame as BGR (ro_agent.to_png writes true RGB)."""
    from PIL import Image

    return np.ascontiguousarray(np.asarray(Image.open(path).convert("RGB"))[..., ::-1])


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


NOTICE_NAMES = ("badge", "levelup_icon")


def parse_notices(text: str) -> list[str]:
    """``none`` -> []; ``badge,levelup_icon`` -> both (sorted); anything else -> ValueError."""
    if text == "none":
        return []
    got = sorted({x.strip() for x in text.split(",") if x.strip()})
    if not got or any(x not in NOTICE_NAMES for x in got):
        raise ValueError(f"--notices: 'none' or a comma list of {NOTICE_NAMES}, not {text!r}")
    return got


def bank(screen: Any, out: Path, levels: str, notices: list[str], scene: str, n: int,
         path: str) -> dict[str, Any]:  # fmt: skip
    """LIVE, no input: ``n`` client frames, labelled with what a PERSON reads on the client now."""
    frames = out / "frames"
    frames.mkdir(parents=True, exist_ok=True)
    lpath = out / BANK_LABELS
    labels: list[dict[str, Any]] = json.loads(lpath.read_text()) if lpath.exists() else []
    for _ in range(n):
        img = np.ascontiguousarray(r.grab_after(screen, r.game_region(), r.ns())[..., :3])
        name = f"{levels}-{'-'.join(notices) or 'clean'}-{r.ns()}.png"
        r.to_png(img, frames / name)
        labels.append({"file": name, "levels": levels, "notices": notices, "scene": scene,
                       "path": path, "t_ns": r.ns()})  # fmt: skip
        time.sleep(0.3)
    lpath.write_text(json.dumps(labels, indent=1) + "\n")
    return {"bank": str(out), "frames": len(labels), "added": n, "levels": levels,
            "notices": notices, "path": path}  # fmt: skip


def _cut_meta(root: Path) -> dict[str, Any]:
    p = root / "gm_state" / CUT_META
    return dict(json.loads(p.read_text())) if p.exists() else {}


def _write_cut_meta(root: Path, key: str, shas: list[str]) -> None:
    meta = _cut_meta(root)
    meta[key] = {"frames": shas, "cut_at": time.strftime("%Y-%m-%dT%H:%M:%S%z")}
    (root / "gm_state" / CUT_META).write_text(json.dumps(meta, indent=1) + "\n")


def cut_levels(png: Path, root: Path) -> dict[str, Any]:
    """The Lv 1 / 1 level lines from a banked frame (a person read Base Lv. 1 / Job Lv. 1)."""
    frame = _png(png)
    dest = root / LEVELS_REL
    dest.parent.mkdir(parents=True, exist_ok=True)
    np.save(dest, crop(frame))
    r.to_png(np.ascontiguousarray(frame[:140, :220]), dest.with_suffix(".png"))
    _write_cut_meta(root, "levels", [_sha(png)])
    return {"cut": str(dest), "check": str(dest.with_suffix(".png")), "from": png.name}


def cut_notice_refs(with_frame: Any, without_frame: Any) -> dict[str, Any]:
    """PURE: each notice's template (its box on the frame WITH both notices) and its mask (the
    pixels there that differ from the frame WITHOUT them by > NOTICE_DIFF: its own pixels)."""
    out: dict[str, Any] = {}
    for name, box in (("badge", BADGE_BOX), ("levelup_icon", ICON_BOX)):
        t = crop(with_frame, box)
        out[name] = t
        out[f"{name}_mask"] = np.abs(t - crop(without_frame, box)) > NOTICE_DIFF
    return out


def cut_notices(with_png: Path, without_png: Path, root: Path) -> dict[str, Any]:
    refs = cut_notice_refs(_png(with_png), _png(without_png))
    d = root / "gm_state"
    d.mkdir(parents=True, exist_ok=True)
    for key, fname in NOTICE_FILES.items():
        np.save(d / fname, refs[key])
    _write_cut_meta(root, "notices", [_sha(with_png), _sha(without_png)])
    return {"cut": str(d), "mask_px": {n: int(refs[f"{n}_mask"].sum()) for n in NOTICE_NAMES},
            "with": with_png.name, "without": without_png.name}  # fmt: skip


def bank_items(banks: list[Path], path: str) -> list[dict[str, Any]]:
    out = []
    for b in banks:
        for it in json.loads((b / BANK_LABELS).read_text()):
            if it.get("path") != path:
                continue
            f = b / "frames" / str(it["file"])
            out.append({**it, "abs": f, "sha256": _sha(f), "bank": b.name})
    return out


def prove(banks: list[Path], root: Path, path: str = "s2") -> dict[str, Any]:
    """Both components on held-out frames, each on its own bar:
    gm_levels: every "fixed" frame <= MATCH, every "not_fixed" >= NOT_FIXED_MIN, >= 4 of each;
    gm_notices: notices() == the label on every frame, >= 3 showing both and >= 3 showing none.
    -> {"gm_levels": {...}, "gm_notices": {...}}, each with "pass" and "before" (its hashes)."""
    from poring_env import ui_sets

    out: dict[str, Any] = {}
    meta = _cut_meta(root)
    used = {s for v in meta.values() for s in v.get("frames", [])}
    items = bank_items(banks, path)
    held = [it for it in items if it["sha256"] not in used]
    # the level lines
    before = ui_sets.file_hashes(root, "gm_levels")
    tp = root / LEVELS_REL
    if "levels" not in meta or not tp.exists():
        out["gm_levels"] = {"verdict": "REFUSED: no level-lines cut (cut --path s2 first)"}
    else:
        t = np.load(tp)
        res: dict[str, Any] = {"fixed": [], "not_fixed": [], "wrong": []}
        for it in held:
            d = distance(_png(it["abs"]), t)
            res[str(it["levels"])].append(d)
            ok = d <= MATCH if it["levels"] == "fixed" else d >= NOT_FIXED_MIN
            if not ok:
                res["wrong"].append({"file": it["file"], "label": it["levels"], "dist": d})
        n_f, n_n = len(res["fixed"]), len(res["not_fixed"])
        passed = not res["wrong"] and n_f >= PROVE_MIN_LEVELS and n_n >= PROVE_MIN_LEVELS
        out["gm_levels"] = {
            "verdict": "PASS" if passed else "FAIL" if res["wrong"] else
            f"INCOMPLETE: {n_f} fixed / {n_n} not fixed (need {PROVE_MIN_LEVELS} each)",
            "pass": passed, "fixed": n_f, "not_fixed": n_n,
            "fixed_max": max(res["fixed"], default=None),
            "not_fixed_min": min(res["not_fixed"], default=None), "wrong": res["wrong"][:20],
            "bar": {"fixed": f"<= {MATCH}", "not_fixed": f">= {NOT_FIXED_MIN}",
                    "min_each": PROVE_MIN_LEVELS},
            "before": before,
        }  # fmt: skip
    # the notices
    before = ui_sets.file_hashes(root, "gm_notices")
    d = root / "gm_state"
    if "notices" not in meta or not all((d / f).exists() for f in NOTICE_FILES.values()):
        out["gm_notices"] = {"verdict": "REFUSED: no notices cut (cut-notices --path s2 first)"}
    else:
        refs = {k: np.load(d / f) for k, f in NOTICE_FILES.items()}
        wrong, both, none, scenes = [], 0, 0, set()
        for it in held:
            got = notices(_png(it["abs"]), refs)
            want = sorted(it["notices"])
            both += want == list(NOTICE_NAMES)
            none += not want
            if not want:
                scenes.add(str(it.get("scene")))
            if got != want:
                wrong.append({"file": it["file"], "label": want, "got": got})
        passed = not wrong and both >= PROVE_MIN_NOTICES and none >= PROVE_MIN_NOTICES
        out["gm_notices"] = {
            "verdict": "PASS" if passed else "FAIL" if wrong else
            f"INCOMPLETE: {both} with both / {none} with none (need {PROVE_MIN_NOTICES} each)",
            "pass": passed, "both": both, "none": none, "clean_scenes": sorted(scenes),
            "wrong": wrong[:20], "bar": {"share": NOTICE_SHARE, "min_each": PROVE_MIN_NOTICES},
            "before": before,
        }  # fmt: skip
    out["held_out"], out["excluded_cut"] = len(held), len(items) - len(held)
    return out


def _main_s2(argv: list[str]) -> int:
    from poring_env import ui_sets

    ap = argparse.ArgumentParser(prog="gm_state.py", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)  # fmt: skip
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("bank")
    b.add_argument("--out", type=Path, required=True)
    b.add_argument("--levels", choices=("fixed", "not_fixed"), required=True)
    b.add_argument("--notices", required=True, help="none | badge,levelup_icon | one of them")
    b.add_argument("--scene", required=True)
    b.add_argument("--n", type=int, default=4)
    c = sub.add_parser("cut")
    c.add_argument("--path", choices=("s2",), required=True)
    c.add_argument("--png", type=Path, required=True)
    cn = sub.add_parser("cut-notices")
    cn.add_argument("--path", choices=("s2",), required=True)
    cn.add_argument("--with", dest="with_png", type=Path, required=True)
    cn.add_argument("--without", dest="without_png", type=Path, required=True)
    p = sub.add_parser("prove")
    p.add_argument("--path", choices=("s2",), required=True)
    p.add_argument("banks", nargs="+", type=Path)
    a = ap.parse_args(argv)
    out: dict[str, Any]
    rc = 0
    if a.cmd == "bank":
        path = _path()
        screen = r.Screen()  # frames only: no agent, no input
        try:
            out = bank(screen, a.out, a.levels, parse_notices(a.notices), a.scene, a.n, path)
        finally:
            screen.close()
    elif a.cmd == "cut":
        out = cut_levels(a.png, _root(a.path))
    elif a.cmd == "cut-notices":
        out = cut_notices(a.with_png, a.without_png, _root(a.path))
    else:
        root = _root(a.path)
        out = prove(a.banks, root, a.path)
        for comp in ("gm_levels", "gm_notices"):
            res = out[comp]
            before = res.pop("before", None)
            if before is None:  # REFUSED: nothing proven, nothing recorded
                rc = 1
                continue
            evidence = {k: v for k, v in res.items() if k != "wrong"}
            evidence["banks"] = [str(x) for x in a.banks]
            res["proof"] = ui_sets.record(root, comp, bool(res["pass"]), evidence, before,
                                          command="gm_state.py prove")["verdict"]  # fmt: skip
            rc = rc or (0 if res["proof"] == "PASS" else 1)  # the RECORDED verdict
    print(json.dumps(out, indent=1, default=str))
    return rc


S2_COMMANDS = ("bank", "cut-notices", "prove")


def main() -> int:
    cmd = sys.argv[1:]
    if cmd and (cmd[0] in S2_COMMANDS or (cmd[0] == "cut" and len(cmd) > 1)):
        return _main_s2(cmd)
    if cmd not in (["check"], ["restore"], ["cut"]):
        print(__doc__)
        return 2
    if cmd == ["cut"] and _path() != "rdp":
        raise r.Stop(
            "gm_state: `cut` writes the RDP set from a live frame; on this path use "
            "`bank` + `cut --path s2 --png FRAME` (docs/operations/s2-gate-templates.md)"
        )
    with r.session("gm-state") as (agent, screen):
        if cmd == ["cut"]:
            frame = np.ascontiguousarray(r.grab_after(screen, r.game_region(), r.ns())[..., :3])
            TEMPLATE.parent.mkdir(parents=True, exist_ok=True)
            np.save(TEMPLATE, crop(frame))
            r.to_png(np.ascontiguousarray(frame[:140, :220]), TEMPLATE.with_suffix(".png"))
            print(json.dumps({"cut": str(TEMPLATE), "check": str(TEMPLATE.with_suffix(".png"))}))
        elif cmd == ["check"]:
            got = check(screen)
            got.pop("frames")
            print(json.dumps(got))
        else:
            rec = ensure_fixed(agent, screen, why="cli")
            print(json.dumps(rec))
    return 0


if __name__ == "__main__":
    sys.exit(main())
