#!/usr/bin/env python3
"""talk@1's prerequisites (docs/demonstrations.md 3.30): deliberate NPC dialogs on the live client
(T4, T5 and the frames T2 / T3 are cut from and proven on), then the cut and the proofs, offline.

LIVE (the parent runs these; RDP, ASSIST, the interlock green, the GM):
    talk_calibrate.py drive --npc garnet|henson|guide [--first N]
        One deliberate dialog, start to end: @warp to a stand cell 3 cells from the NPC, the ONE
        TALK-gated contact click (cursor_gate: TALK read twice; 3.30's points 0, -14, -28 px), then
        KEYS only, decided from template-free pixels at the windows' default places (their border
        lines, the button's ink, the highlight band, the scrollbar's thumb): Enter on NEXT / CLOSE;
        in a menu ArrowDown / ArrowUp until the selected line is option N (first menu) or the end
        option (later menus), then Enter. Frames after every step (the cursor parked away), then
        `collect`. Stops (no key) on anything it cannot read.
    talk_calibrate.py key CODE [CODE ...] | frames [--n 4] | click next|close|ok|cancel|up|down|row
        [--row K] | contact --npc NPC | collect
        Single steps on the CURRENT session (a person looking at the frames decides); `click` finds
        its element by T2 (cut templates) and clicks it through talk1.LiveIo (its one UI click).

OFFLINE (frames + the session's packets; labels from packet truth, ADR-0007; never committed):
    talk_calibrate.py cut SESSION [SESSION ...]
        T2: the two windows' templates and masks, NEXT / CLOSE / the blank button place, OK /
        Cancel, the scroll arrows, into data/ui_anchors/npc_dialog/; T3: one glyph per character,
        into data/ui_anchors/menu_glyphs.npz. Rules fixed in poring_env.npc_dialog.Params and
        menu_text.fit_menu_glyphs, verified on the training frames, self-checked on every 3rd.
    talk_calibrate.py prove-t2 SESSION [SESSION ...]      sessions NOT used by `cut`
        PASS: >= 50 labelled frames, EVERY one ok and agreeing with the packets (dialog present /
        absent, the button NEXT / CLOSE / none, menu present / absent), with >= 1 frame each of
        NEXT, CLOSE, a menu and no window.
    talk_calibrate.py prove-t3 SESSION [SESSION ...]      sessions NOT used by `cut`
        PASS: every labelled option line read EXACTLY (0 wrong, 0 refused), every option of every
        menu seen read at least once, and the damaged copies (2 ink pixels removed, a coloured
        patch) never read WRONG.

A frame is labelled only when the dialog's last packet event and our last step are >= --settle-ms
(600) old. Menu rows are labelled by STRUCTURE (each row's glyph runs and word gaps against the
option list, one offset only, the scrollbar's thumb agreeing), never by the reader under test.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import random
import sys
import time
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import talk1  # noqa: E402

from poring_env import menu_text as mt  # noqa: E402
from poring_env import npc_dialog as nd  # noqa: E402
from poring_env.ui_anchors import CAPTURE_ORIGINS  # noqa: E402

S = 1_000_000_000
CURRENT = Path("/dev/shm/poring-lab-tmp/talk-cal/current.json")
STEPS_FILE = "talk_cal.json"
FRAMES_DIR = "frames"
SETTLE_MS = 600
HOLDOUT_EVERY = 3
PROVE_T2_MIN = 50
STAND = [(0, 3), (-3, 0), (0, -3), (3, 0), (-3, 3), (3, 3), (-3, -3), (3, -3)]
DRIVE_MAX_STEPS = 60
DRIVE_WAIT_S = 4.0
DRIVE_REPEATS = 3  # the same keys on the same reading this many times: the key has no effect
DIALOG_O = CAPTURE_ORIGINS[nd.DIALOG]
MENU_O = CAPTURE_ORIGINS[nd.MENU]
DIALOG_EVENTS = ("npc_contact", "npc_say", "npc_wait", "npc_menu", "npc_choose",
                 "npc_next_click", "npc_close", "npc_close_click")  # fmt: skip


# --- packet truth (pure) ------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Label:
    """What the client shows, per the packets: dialog / menu present, the dialog's button."""

    dialog: bool = False
    menu: bool = False
    button: str | None = None  # "next" | "close" | None
    options: tuple[str, ...] | None = None  # the open menu's options


CLOSED = Label()


def dialog_timeline(events: Sequence[dict[str, Any]]) -> list[tuple[int, Label]]:
    """(time, label) at every dialog event of OUR conversations (each starts at our npc_contact;
    the server's events of that NPC follow). Times are the host's (t_mono_ns)."""
    out: list[tuple[int, Label]] = [(0, CLOSED)]
    gid: int | None = None
    cur = CLOSED
    for e in sorted(events, key=lambda e: int(e["t_mono_ns"])):
        typ = e.get("type")
        if typ not in DIALOG_EVENTS:
            continue
        if typ == "npc_contact":
            gid, cur = int(e["npc_gid"]), CLOSED
        elif gid is None or int(e.get("npc_gid", -1)) != gid:
            continue
        elif typ == "npc_say":
            cur = replace(cur, dialog=True, button=None)
        elif typ == "npc_wait":
            cur = replace(cur, dialog=True, button="next")
        elif typ == "npc_close":
            cur = replace(cur, dialog=True, button="close")
        elif typ == "npc_menu":
            cur = replace(cur, menu=True, button=None, options=tuple(e["options"]))
        elif typ == "npc_next_click":
            cur = replace(cur, button=None)
        elif typ == "npc_choose":
            cur = CLOSED if e.get("cancelled") else replace(cur, menu=False, options=None)
        elif typ == "npc_close_click":
            cur = CLOSED
        out.append((int(e["t_mono_ns"]), cur))
    return out


def label_at(timeline: Sequence[tuple[int, Label]], t_ns: int, settle_ns: int,
             actions: Sequence[int] = ()) -> Label | None:  # fmt: skip
    """The label at ``t_ns`` when the last dialog event and our last action are >= settle old."""
    before = [(t, lab) for t, lab in timeline if t <= t_ns]
    if not before:
        return None
    last, lab = before[-1]
    if last > 0 and t_ns - last < settle_ns:
        return None
    if any(t_ns - settle_ns < a <= t_ns for a in actions):
        return None
    return lab


def structure(text: str) -> tuple[int, tuple[bool, ...]]:
    """(non-space characters, a word break after each but the last) of an option."""
    words = text.strip(" ").split()
    flags: list[bool] = []
    for w in words:
        flags += [False] * (len(w) - 1) + [True]
    return sum(len(w) for w in words), tuple(flags[:-1])


def row_structure(row_bgr: Any) -> tuple[int, tuple[bool, ...]] | str:
    """The same from a row's pixels (runs of ink columns; a gap >= 3 is a word break), or
    "coloured" / "foreign" / "empty" / "no_background"."""
    p, foreign, bg = mt.ink_map(row_bgr)
    if bg is None:
        return "no_background"
    kind = mt.foreign_kind(row_bgr, foreign)
    if kind is not None:
        return "coloured" if kind == "coloured_text" else "foreign"
    runs = mt.ink_runs(p >= mt.INK_P)
    if not runs:
        return "empty"
    return len(runs), tuple(runs[i + 1][0] - runs[i][1] >= 3 for i in range(len(runs) - 1))


def align_rows(rows: Sequence[Any], options: Sequence[str],
               thumb: tuple[int, int] | None = None, track_len: int = 39
               ) -> tuple[int, list[str | None]] | str:  # fmt: skip
    """(top, the text each row shows: "" empty, None coloured) for a menu whose listed options
    are ``options``, by structure only; or why the rows cannot be labelled."""
    vis = [o for _, o in mt.visible_options(options)]
    sigs = [row_structure(r) for r in rows]
    if any(s in ("foreign", "no_background") for s in sigs):
        return "row_unlabelled"
    n, k = len(vis), len(rows)
    fits = []
    for top in range(0, max(1, n - k + 1)):
        ok = True
        for j, s in enumerate(sigs):
            i = top + j
            if i >= n:
                ok = ok and s == "empty"
                continue
            want = mt.visible_text(vis[i])
            ok = ok and (s == "coloured" if want is None else s == structure(want))
        if ok:
            fits.append(top)
    if len(fits) != 1:
        return "no_structure_fit" if not fits else "ambiguous_structure"
    top = fits[0]
    if thumb is not None and n > k:
        span = track_len - (thumb[1] - thumb[0])
        if span <= 0 or abs(thumb[0] - top * span / (n - k)) > 2.0:
            return "thumb_disagrees"
    texts: list[str | None] = [mt.visible_text(vis[top + j]) if top + j < n else ""
                               for j in range(k)]  # fmt: skip
    return top, texts


# --- template-free driving (pure) ----------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Coarse:
    """The windows at their default places, without templates (drive only)."""

    dialog: bool
    menu: bool
    button: bool  # the dialog's button place shows something (NEXT or CLOSE: Enter does both)
    highlight: int | None
    thumb: tuple[int, int] | None
    text: str  # a digest of the dialog text's ink: each page differs


def coarse(frame: Any) -> Coarse:
    g = nd.GEOMETRY
    dialog = nd.border_ok(frame, DIALOG_O, nd.DIALOG)
    menu = nd.border_ok(frame, MENU_O, nd.MENU)
    button, text = False, "-"
    if dialog:
        x, y, w, h = nd._abs(DIALOG_O, g.dialog_button)
        button = bool((np.asarray(frame[y : y + h, x : x + w, :3]).max(axis=-1) < 100).sum() > 20)
        x, y, w, h = nd._abs(DIALOG_O, g.dialog_text)
        ink = np.asarray(frame[y : y + h, x : x + w, :3]).max(axis=-1) < 100
        text = hashlib.sha1(np.packbits(ink).tobytes()).hexdigest()[:12]
    lit: int | None = None
    thumb = None
    if menu:
        backs = [nd.row_background(frame, MENU_O, k, g) for k in range(g.rows)]
        lit_rows = [k for k, b in enumerate(backs) if b == "highlight"]
        lit = lit_rows[0] if len(lit_rows) == 1 else None
        x = MENU_O[0] + g.track_col
        y0 = MENU_O[1] + g.track[1]
        col = np.asarray(frame[y0 : y0 + g.track[3], x : x + 1, :3])
        rows = np.flatnonzero(~nd.colour_is(col, nd.TRACK_RGB)[:, 0])
        if rows.size and rows[-1] - rows[0] + 1 == rows.size:
            thumb = (int(rows[0]), int(rows[-1]) + 1)
    return Coarse(dialog, menu, button, lit, thumb, text)


def selected_index(c: Coarse, n: int, rows: int = 4, track_len: int = 39) -> int | None:
    """The menu's selected option (0-based) from the highlight row and the thumb, or None."""
    if c.highlight is None:
        return None
    if n <= rows:
        return c.highlight
    if c.thumb is None:
        return None
    span = track_len - (c.thumb[1] - c.thumb[0])
    if span <= 0:
        return None
    top = round(c.thumb[0] * (n - rows) / span)
    if abs(c.thumb[0] - top * span / (n - rows)) > 1.5:
        return None
    return int(top) + c.highlight


def drive_keys(c: Coarse, want: int, n: int) -> list[str] | str:
    """The next key(s), or "wait" (no button yet) / "stop" (nothing open, or unreadable)."""
    if c.menu:
        sel = selected_index(c, n)
        if sel is None:
            return "stop"
        if sel < want:
            return ["ArrowDown"]
        if sel > want:
            return ["ArrowUp"]
        return ["Enter"]
    if c.dialog:
        return ["Enter"] if c.button else "wait"
    return "stop"


def stand_cell(walkable: Any, npc: tuple[int, int],
               others: Sequence[tuple[int, int]]) -> tuple[int, int] | None:  # fmt: skip
    """The first walkable cell 3 from the NPC (fixed order) with every other NPC >= 3 away."""
    for dx, dy in STAND:
        c = (npc[0] + dx, npc[1] + dy)
        if talk1._walk(walkable, c) and all(talk1.cheb(c, o) >= 3 for o in others):
            return c
    return None


# --- sessions on disk ----------------------------------------------------------------------------


def frames_of(session: Path) -> list[tuple[int, Path]]:
    out = []
    for p in sorted((session / FRAMES_DIR).glob("*.png")):
        parts = p.stem.split("-")
        if len(parts) == 2 and parts[1].isdigit():
            out.append((int(parts[1]), p))
    return sorted(out)


def load_frame(path: Path) -> Any:
    """A saved frame as BGR."""
    from PIL import Image

    return np.ascontiguousarray(np.asarray(Image.open(path).convert("RGB"))[..., ::-1])


def read_events(session: Path) -> list[dict[str, Any]]:
    with gzip.open(session / "packets.jsonl.gz", "rt") as f:
        return [json.loads(line) for line in f if line.strip()]


def actions_of(session: Path) -> list[int]:
    doc = json.loads((session / STEPS_FILE).read_text())
    return [int(s["t"]) for s in doc.get("steps", []) if s.get("t")]


def labelled(sessions: Sequence[Path], settle_ms: int) -> list[tuple[str, int, Path, Label]]:
    """(session name, t, path, label) of every settled frame."""
    out = []
    for s in sessions:
        tl = dialog_timeline(read_events(s))
        acts = actions_of(s)
        for t, p in frames_of(s):
            lab = label_at(tl, t, settle_ms * 1_000_000, acts)
            if lab is not None:
                out.append((s.name, t, p, lab))
    return out


# --- cut / prove (offline) ---------------------------------------------------------------------


def _crop_at(frame: Any, origin: tuple[int, int], window: str) -> Any:
    """The window's rect (at its default place) as its own small array (origin (0, 0))."""
    w, h = nd.GEOMETRY.size(window)
    return np.ascontiguousarray(frame[origin[1] : origin[1] + h, origin[0] : origin[0] + w, :3])


def cut(sessions: Sequence[Path], settle_ms: int, out_dir: Path,
        force: bool = False) -> dict[str, Any]:  # fmt: skip
    """See the module docstring. Frames are loaded one at a time; only window crops are kept."""
    items = labelled(sessions, settle_ms)
    train = [it for i, it in enumerate(items) if i % HOLDOUT_EVERY]
    held = [it for i, it in enumerate(items) if not i % HOLDOUT_EVERY]
    report: dict[str, Any] = {"sessions": [s.name for s in sessions], "labelled": len(items),
                              "train": len(train), "held": len(held)}  # fmt: skip
    crops: dict[str, list[Any]] = {k: [] for k in ("dialog", "menu", "scrolled", nd.NEXT,
                                                   nd.CLOSE, nd.BLANK)}  # fmt: skip
    for _, _, path, lab in train:
        frame = load_frame(path)
        if lab.dialog and nd.border_ok(frame, DIALOG_O, nd.DIALOG):
            c = _crop_at(frame, DIALOG_O, nd.DIALOG)
            crops["dialog"].append(c)
            crops[{"next": nd.NEXT, "close": nd.CLOSE}.get(str(lab.button), nd.BLANK)].append(c)
        if lab.menu and nd.border_ok(frame, MENU_O, nd.MENU):
            c = _crop_at(frame, MENU_O, nd.MENU)
            crops["menu"].append(c)
            if lab.options and len(mt.visible_options(lab.options)) > 4:
                crops["scrolled"].append(c)
    report["frames"] = {k: len(v) for k, v in crops.items()}
    zero = (0, 0)
    images: dict[str, nd.Gray] = {}
    masks: dict[str, nd.Gray] = {}
    if crops["dialog"]:
        images[nd.DIALOG], masks[nd.DIALOG] = nd.cut_window(
            crops["dialog"], [zero] * len(crops["dialog"]), nd.DIALOG)  # fmt: skip
    if crops["menu"]:
        images[nd.MENU], masks[nd.MENU] = nd.cut_window(crops["menu"], [zero] * len(crops["menu"]),
                                                        nd.MENU)  # fmt: skip
        for name in (nd.OK, nd.CANCEL):
            images[name] = nd.cut_element(crops["menu"], [zero] * len(crops["menu"]), name)
    for name in (nd.NEXT, nd.CLOSE, nd.BLANK):
        if crops[name]:
            images[name] = nd.cut_element(crops[name], [zero] * len(crops[name]), name)
    if crops["scrolled"]:
        for name in nd.ARROW_NAMES:
            images[name] = nd.cut_element(crops["scrolled"], [zero] * len(crops["scrolled"]), name)
            masks[name] = nd.arrow_mask(crops["scrolled"], [zero] * len(crops["scrolled"]), name)
    del crops
    templates = nd.DialogTemplates(images, masks, meta={
        "sessions": [s.name for s in sessions], "settle_ms": settle_ms,
        "frames": report["frames"], "cut_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    })  # fmt: skip
    report["missing_t2"] = list(templates.missing) + ([] if nd.CLOSE in images else [nd.CLOSE])
    report["button_pairs"] = {
        f"{a}~{b}": round(nd.image_distance(images[a], images[b]), 2)
        for i, a in enumerate((nd.NEXT, nd.CLOSE, nd.BLANK))
        for b in (nd.NEXT, nd.CLOSE, nd.BLANK)[i + 1 :] if a in images and b in images
    }  # fmt: skip
    t2_train = agree_t2(templates, train) if not templates.missing else None
    report["t2_train"] = t2_train
    report["t2_held_self_check"] = agree_t2(templates, held) if not templates.missing else None
    rows, texts, why = [], [], Counter()
    if not templates.missing:
        for _, _, path, lab in train:
            if not lab.menu or not lab.options:
                continue
            frame = load_frame(path)
            st = nd.state(frame, templates)
            if not st.ok or st.menu is None:
                why[f"t2_{st.reason}"] += 1
                continue
            rcrops = [np.ascontiguousarray(frame[y : y + h, x : x + w])
                      for x, y, w, h in st.menu.rows]  # fmt: skip
            got = align_rows(rcrops, lab.options, st.menu.thumb, nd.GEOMETRY.track[3])
            if isinstance(got, str):
                why[got] += 1
                continue
            for crop, text in zip(rcrops, got[1], strict=True):
                if text:
                    rows.append(crop)
                    texts.append(text)
    report["t3_rows"] = {"rows": len(rows), "skipped_frames": dict(why)}
    glyphs = None
    if rows:
        try:
            glyphs, stats = mt.fit_menu_glyphs(rows, texts)
        except ValueError as exc:
            report["t3_fit_error"] = str(exc)
        else:
            glyphs = replace(glyphs, meta={"sessions": [s.name for s in sessions],
                                           "rows": len(rows)})  # fmt: skip
            report["t3_fit"] = {k: v for k, v in stats.items() if k != "dropped_mislabelled"}
            report["t3_held_self_check"] = agree_t3(templates, glyphs, held)
    ok_t2 = bool(not report["missing_t2"] and t2_train and not t2_train["disagree"])
    ok_t3 = glyphs is not None
    ready = ok_t2 and ok_t3
    report["verdict"] = (
        "READY (prove on held-out sessions next)"
        if ready
        else "NOT READY: " + ", ".join(x for x, ok in (("T2", ok_t2), ("T3", ok_t3)) if not ok)
    )
    if ready or force:
        templates.save(out_dir / "npc_dialog")
        if glyphs is not None:
            glyphs.save(out_dir / "menu_glyphs.npz")
        report["written"] = [str(out_dir / "npc_dialog"), str(out_dir / "menu_glyphs.npz")]
    else:
        report["written"] = "nothing (NOT READY; --force writes anyway)"
    return report


Item = tuple[str, int, Path, Label]


def agree_t2(templates: nd.DialogTemplates, items: Sequence[Item]) -> dict[str, Any]:
    """Per labelled frame: T2's state against the label (dialog / menu present, the button)."""
    out: dict[str, Any] = {"frames": len(items), "agree": 0, "disagree": [], "refused": Counter(),
                           "classes": Counter()}  # fmt: skip
    for _, _, path, lab in items:
        frame = load_frame(path)
        cls = ("menu" if lab.menu else f"dialog_{lab.button or 'none'}" if lab.dialog
               else "no_window")  # fmt: skip
        out["classes"][cls] += 1
        st = nd.state(frame, templates)
        if not st.ok:
            out["refused"][st.reason] += 1
            out["disagree"].append({"frame": path.name, "label": cls, "got": st.reason})
            continue
        got_button = st.dialog.button if st.dialog is not None else None
        same = ((st.dialog is not None) == lab.dialog and (st.menu is not None) == lab.menu
                and (not lab.dialog or got_button == lab.button))  # fmt: skip
        if same:
            out["agree"] += 1
        else:
            out["disagree"].append({"frame": path.name, "label": cls, "got": st.summary()})
    out["refused"], out["classes"] = dict(out["refused"]), dict(out["classes"])
    return out


def damaged(row: Any, rng: random.Random) -> Any:
    """A copy with 2 ink pixels of one glyph turned to background."""
    out = np.array(row, copy=True)
    p, _, _ = mt.ink_map(out)
    ys, xs = np.nonzero(p >= mt.INK_P)
    if ys.size < 3:
        return out
    pick = rng.sample(range(ys.size), 2)
    bg = np.array(mt.PLAIN_RGB[::-1], np.uint8)
    for i in pick:
        out[ys[i], xs[i]] = bg
    return out


def coloured(row: Any) -> Any:
    out = np.array(row, copy=True)
    w = out.shape[1]
    out[5:9, w // 4 : w // 4 + 4] = (255, 0, 0)  # BGR: a blue patch
    return out


def agree_t3(templates: nd.DialogTemplates, glyphs: mt.MenuGlyphs, items: Sequence[Item],
             seed: int = 20261009) -> dict[str, Any]:  # fmt: skip
    """Per labelled menu row: exact / refused / WRONG, the damaged copies, option coverage."""
    rng = random.Random(seed)
    out: dict[str, Any] = {"menu_frames": 0, "rows": 0, "exact": 0, "refused": Counter(),
                           "wrong": [], "unlabelled": Counter(), "neg": Counter(),
                           "neg_wrong": [], "coverage": {}}  # fmt: skip
    seen: dict[tuple[str, ...], set[str]] = {}
    for _, _, path, lab in items:
        if not lab.menu or not lab.options:
            continue
        out["menu_frames"] += 1
        frame = load_frame(path)
        st = nd.state(frame, templates)
        if not st.ok or st.menu is None:
            out["unlabelled"][f"t2_{st.reason}"] += 1
            continue
        crops = [np.ascontiguousarray(frame[y : y + h, x : x + w]) for x, y, w, h in st.menu.rows]
        got = align_rows(crops, lab.options, st.menu.thumb, nd.GEOMETRY.track[3])
        if isinstance(got, str):
            out["unlabelled"][got] += 1
            continue
        menu_seen = seen.setdefault(lab.options, set())
        for crop, truth in zip(crops, got[1], strict=True):
            if truth == "":
                continue
            out["rows"] += 1
            rd = mt.read_row(crop, glyphs)
            if truth is None:  # a coloured option: refusing it as coloured is the right answer
                if rd.reason == "coloured_text":
                    out["exact"] += 1
                elif rd.text is not None:
                    out["wrong"].append({"truth": "coloured", "read_len": len(rd.text)})
                else:
                    out["refused"][rd.reason] += 1
                continue
            if rd.text == truth:
                out["exact"] += 1
                menu_seen.add(truth)
                for kind, bad in (("damaged", damaged(crop, rng)), ("coloured", coloured(crop))):
                    nr = mt.read_row(bad, glyphs)
                    if nr.text is not None and nr.text != truth:
                        out["neg_wrong"].append({"kind": kind, "len": len(truth)})
                    out["neg"][f"{kind}:{'exact' if nr.text == truth else nr.reason}"] += 1
            elif rd.text is None:
                out["refused"][rd.reason] += 1
            else:
                out["wrong"].append({"truth_len": len(truth), "read_len": len(rd.text)})
    for opts, got_lines in seen.items():
        vis = [v for _, o in mt.visible_options(opts) if (v := mt.visible_text(o))]
        out["coverage"][f"menu of {len(opts)}"] = {
            "options": len(vis),
            "read_exactly": sum(1 for v in vis if v in got_lines),
        }
    out["refused"], out["unlabelled"], out["neg"] = (dict(out["refused"]), dict(out["unlabelled"]),
                                                     dict(out["neg"]))  # fmt: skip
    return out


def used_by_cut(out_dir: Path) -> set[str]:
    doc = json.loads((out_dir / "npc_dialog" / nd.PARAMS_FILE).read_text())
    return set(doc.get("meta", {}).get("sessions", []))


def prove_t2(sessions: Sequence[Path], settle_ms: int, out_dir: Path) -> dict[str, Any]:
    clash = used_by_cut(out_dir) & {s.name for s in sessions}
    if clash:
        return {"verdict": f"REFUSED: {sorted(clash)} were used to cut the templates"}
    t = nd.load_templates(out_dir / "npc_dialog")
    items = labelled(sessions, settle_ms)
    res = agree_t2(t, items)
    classes = res["classes"]
    need = ("dialog_next", "dialog_close", "menu", "no_window")
    lacking = [c for c in need if not classes.get(c)]
    ok = res["frames"] >= PROVE_T2_MIN and res["agree"] == res["frames"] and not lacking
    res["verdict"] = (
        "PASS"
        if ok
        else "FAIL"
        if res["agree"] != res["frames"]
        else (f"INCOMPLETE: {res['frames']} frames (need {PROVE_T2_MIN}), no frame of {lacking}")
    )
    return {"sessions": [s.name for s in sessions], **res}


def prove_t3(sessions: Sequence[Path], settle_ms: int, out_dir: Path) -> dict[str, Any]:
    clash = used_by_cut(out_dir) & {s.name for s in sessions}
    if clash:
        return {"verdict": f"REFUSED: {sorted(clash)} were used to cut the templates"}
    t = nd.load_templates(out_dir / "npc_dialog")
    g = mt.load_menu_glyphs(out_dir / "menu_glyphs.npz")
    items = labelled(sessions, settle_ms)
    res = agree_t3(t, g, items)
    covered = all(c["options"] == c["read_exactly"] for c in res["coverage"].values())
    clean = not res["wrong"] and not res["neg_wrong"]
    ok = clean and not res["refused"] and res["rows"] > 0 and covered
    res["verdict"] = ("PASS" if ok else "FAIL: WRONG reads" if not clean
                      else "FAIL: refusals on clean lines" if res["refused"]
                      else "INCOMPLETE: not every option read")  # fmt: skip
    return {"sessions": [s.name for s in sessions], **res}


# --- the live steps ------------------------------------------------------------------------------


def _current() -> dict[str, Any]:
    if not CURRENT.exists():
        raise SystemExit("no current calibration session: run `contact` or `drive` first")
    return dict(json.loads(CURRENT.read_text()))


def _save_steps(doc: dict[str, Any]) -> None:
    (Path(doc["dir"]) / STEPS_FILE).write_text(json.dumps(doc, indent=1))
    CURRENT.parent.mkdir(parents=True, exist_ok=True)
    CURRENT.write_text(json.dumps({"session": doc["session"], "dir": doc["dir"]}))


def _doc() -> dict[str, Any]:
    cur = _current()
    return dict(json.loads((Path(cur["dir"]) / STEPS_FILE).read_text()))


def grab_frames(io: talk1.LiveIo, doc: dict[str, Any], n: int, gap_s: float = 0.25) -> list[Any]:
    """Park the cursor away from the windows, then ``n`` frames (decoded after the last step)."""
    import ro_agent as r

    io.park()
    out = []
    fdir = Path(doc["dir"]) / FRAMES_DIR
    k = len(list(fdir.glob("*.png"))) if fdir.exists() else 0
    after = doc["steps"][-1]["t"] if doc["steps"] else None
    for _ in range(n):
        img = r.grab_after(io.screen, r.game_region(), after)
        t = r.ns()
        r.to_png(img, fdir / f"{k:04d}-{t}.png")
        out.append(np.ascontiguousarray(img[..., :3]))
        k += 1
        time.sleep(gap_s)
    doc["frames"] = k
    return out


def live_contact(npc_key: str, agent: Any, screen: Any) -> dict[str, Any]:
    """A new calibration session: warp beside the NPC, the TALK-gated contact click."""
    import bench
    import cursor_gate
    import record_session
    import ro_agent as r
    import rule_run as rr
    import walk5 as w5

    from poring_dataset import camera as cam
    from poring_dataset import gat as gatmod
    from poring_env.demo import DemoLog, new_session_id

    tgt = talk1.TARGETS[npc_key]
    info = talk1.l3_target(talk1.load_l3(), tgt)
    gat = gatmod.parse((cam.GAT_DIR / f"{tgt.map}.gat").read_bytes())
    stand = stand_cell(gat.walkable(), tgt.cell, info["others"])
    if stand is None:
        raise SystemExit(f"no stand cell beside {npc_key}")
    cj = json.loads((r.ROOT / "packages/poring_dataset/src/poring_dataset/camera_rdp.json")
                    .read_text())  # fmt: skip
    base = cam.camera_from_json(cj["camera"])
    camera = (cam.camera_for_map(base, True, cj["indoor"]["yaw_deg"], cj["indoor"]["distance"])
              if tgt.map in cam.load_indoor_table() else base)  # fmt: skip
    sid = new_session_id(f"talk-cal-{npc_key}")
    log = DemoLog(sid)
    lock = record_session.read_lock(r.ROOT / "state")
    log.start(backend=str(lock.backend), lock_seq=lock.seq, server="lab-rathena",
              rule="talk@1/calibration", npc=info["name"], account="gm")  # fmt: skip
    doc: dict[str, Any] = {"session": sid, "dir": str(log.dir), "npc": info["name"],
                           "target": npc_key, "npc_cell": list(tgt.cell), "map": tgt.map,
                           "stand": list(stand), "t_first": r.ns(), "t_click": None,
                           "steps": [], "menu_len": tgt.menu_len}  # fmt: skip
    r.gm(agent, screen, "@killmonster2")
    r.gm(agent, screen, f"@warp {tgt.map} {stand[0]} {stand[1]}")
    time.sleep(rr.SCENE_ENTRY_S)
    bench.close_chat(agent, screen)
    r.activate_client(agent, screen)
    pr = cursor_gate.prober(agent, screen)
    w = w5.World(camera, gat, stand)
    u, v = (float(c) for c in w.project([tgt.cell])[0])
    for dv in talk1.CONTACT_POINTS:
        got = cursor_gate.gated_click(pr, u, v + dv, allow=(talk1.TALK,))
        doc["steps"].append({"kind": "contact_try", "dv": dv, "why": got["why"],
                             "t": got.get("t_click")})  # fmt: skip
        if got["clicked"]:
            doc["t_click"] = int(got["t_click"])
            break
    _save_steps(doc)
    return doc


def collect(doc: dict[str, Any]) -> dict[str, Any]:
    """The session's packets; T5 (our contact on the NPC at its L3 cell within 5 s of the click)
    and T4 (each of the 8 dialog events seen live)."""
    import record_session
    import ro_agent as r
    import talk1_score

    from poring_dataset.timeline import Timeline
    from poring_env.demo import DemoLog

    log = DemoLog(doc["session"])
    events, anchor = record_session.write_packets(log.dir, int(doc["t_first"]), r.ns())
    ev = sorted(events, key=lambda e: int(e["t_mono_ns"]))
    out: dict[str, Any] = {"session": doc["session"], "npc": doc["npc"]}
    t = doc.get("t_click")
    gid = talk1_score.target_gid(Timeline(ev), doc["npc_cell"], int(t)) if t else None
    contacts = [e for e in ev if e.get("type") == "npc_contact" and t is not None
                and 0 <= int(e["t_mono_ns"]) - int(t) <= 5 * S]  # fmt: skip
    out["t5"] = {
        "clicked": t is not None,
        "target_gid_found": gid is not None,
        "contacts": [int(e["npc_gid"]) for e in contacts],
        "pass": gid is not None and any(int(e["npc_gid"]) == gid for e in contacts),
    }
    counts = Counter(str(e["type"]) for e in ev if e.get("type") in DIALOG_EVENTS
                     and int(e["t_mono_ns"]) >= int(doc["t_first"]))  # fmt: skip
    out["t4"] = {"counts": {k: counts.get(k, 0) for k in DIALOG_EVENTS},
                 "pass": all(counts.get(k, 0) > 0 for k in DIALOG_EVENTS)}  # fmt: skip
    log.finish(packet_events=len(events), packet_anchor=anchor, result=out)
    doc["collected"] = True
    _save_steps(doc)
    return out


def drive(npc_key: str, first: int | None) -> dict[str, Any]:
    import ro_agent as r

    tgt = talk1.TARGETS[npc_key]
    first = first if first is not None else tgt.first[0]
    if first not in tgt.first:
        raise SystemExit(f"--first {first}: {npc_key}'s allowed first options are {tgt.first}")
    with r.session("rule:talk-calibrate") as (agent, screen):
        doc = live_contact(npc_key, agent, screen)
        io = talk1.LiveIo(agent, screen, nd.DialogTemplates({}))
        io.last_action = doc["t_click"]
        grab_frames(io, doc, 4)
        menus_done, ended = 0, "max_steps"
        waited = 0.0
        last: tuple[Coarse, list[str]] | None = None
        repeats = 0
        if doc["t_click"] is None:
            ended = "no_contact"
        else:
            for _ in range(DRIVE_MAX_STEPS):
                fr = grab_frames(io, doc, 2, 0.15)
                c1, c2 = coarse(fr[0]), coarse(fr[1])
                if c1 != c2:
                    continue
                want = first - 1 if menus_done == 0 else tgt.menu_len - 1
                keys = drive_keys(c2, want, tgt.menu_len)
                if keys == "wait":
                    waited += 0.5
                    if waited > DRIVE_WAIT_S:
                        ended = "no_button"
                        break
                    time.sleep(0.5)
                    continue
                if keys == "stop":
                    ended = "closed" if not (c2.dialog or c2.menu) else "unreadable"
                    break
                waited = 0.0
                assert isinstance(keys, list)
                if (c2, keys) == last:
                    repeats += 1
                    if repeats >= DRIVE_REPEATS:
                        ended = "no_effect"
                        break
                else:
                    repeats, last = 0, (c2, keys)
                r.activate_client(agent, screen)
                for code in keys:
                    agent.keys(code)
                    doc["steps"].append({"kind": "key", "code": code, "t": r.ns(),
                                         "menu": c2.menu, "menus_done": menus_done})  # fmt: skip
                    if c2.menu and code == "Enter":
                        menus_done += 1
                io.last_action = doc["steps"][-1]["t"]
                io.parked = False
                time.sleep(0.6)
                grab_frames(io, doc, 4)
                _save_steps(doc)
        doc["drive"] = {"first": first, "menus_done": menus_done, "ended": ended}
        _save_steps(doc)
    return {
        "session": doc["session"],
        "drive": doc["drive"],
        "frames": doc.get("frames"),
        **collect(doc),
    }


def one_step(kind: str, args: argparse.Namespace) -> dict[str, Any]:
    import ro_agent as r

    doc = _doc()
    with r.session("rule:talk-calibrate") as (agent, screen):
        templates = (nd.load_templates(talk1.TEMPLATES) if kind == "click"
                     else nd.DialogTemplates({}))  # fmt: skip
        io = talk1.LiveIo(agent, screen, templates)
        if kind == "key":
            r.activate_client(agent, screen)
            for code in args.codes:
                agent.keys(code)
                doc["steps"].append({"kind": "key", "code": code, "t": r.ns()})
        elif kind == "click":
            if not talk1.GLYPHS.exists():
                raise SystemExit("no T3 glyphs yet: cut first")
            seen = talk1.observe_stable(io, talk1.menu_reader(mt.load_menu_glyphs(talk1.GLYPHS)))
            st = seen.state
            if not st.ok:
                raise SystemExit(f"T2 cannot read the windows ({st.reason}): no click")
            box, inside = element_box(st, args.element, args.row)
            t = io.click(*nd.centre(box), args.element, inside)
            doc["steps"].append({"kind": "click", "element": args.element, "row": args.row,
                                 "t": t})  # fmt: skip
        frames = grab_frames(io, doc, args.n)
        _save_steps(doc)
        st = nd.state(frames[-1], nd.load_templates(talk1.TEMPLATES)) \
            if (talk1.TEMPLATES / nd.PARAMS_FILE).exists() else None  # fmt: skip
    return {"session": doc["session"], "frames": doc.get("frames"),
            "t2": st.summary() if st is not None else "no templates yet",
            "coarse": coarse(frames[-1]).__repr__()}  # fmt: skip


def element_box(st: nd.NpcUiState, element: str, row: int | None) -> tuple[nd.Box, nd.Box]:
    """(the element's box, the window it must be inside) on an ok state, or SystemExit."""
    if element in ("next", "close"):
        d = st.dialog
        if d is None or d.button != element:
            raise SystemExit(f"the dialog does not show {element.upper()}: no click")
        return d.button_rect, d.rect
    m = st.menu
    if m is None:
        raise SystemExit("no menu: no click")
    if element == "row":
        if row is None or not 0 <= row < len(m.rows):
            raise SystemExit("--row 0..3")
        return m.rows[row], m.rect
    if element in ("up", "down") and not m.scrollbar:
        raise SystemExit("the menu has no scrollbar: no click")
    box = {"ok": m.ok_rect, "cancel": m.cancel_rect, "up": m.up_rect, "down": m.down_rect}
    return box[element], m.rect


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)  # fmt: skip
    sub = ap.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("drive")
    d.add_argument("--npc", choices=sorted(talk1.TARGETS), required=True)
    d.add_argument("--first", type=int)
    c = sub.add_parser("contact")
    c.add_argument("--npc", choices=sorted(talk1.TARGETS), required=True)
    k = sub.add_parser("key")
    k.add_argument("codes", nargs="+", choices=("Enter", "ArrowDown", "ArrowUp", "Escape"))
    k.add_argument("--n", type=int, default=4)
    cl = sub.add_parser("click")
    cl.add_argument("element", choices=("next", "close", "ok", "cancel", "up", "down", "row"))
    cl.add_argument("--row", type=int)
    cl.add_argument("--n", type=int, default=4)
    f = sub.add_parser("frames")
    f.add_argument("--n", type=int, default=4)
    sub.add_parser("collect")
    for name in ("cut", "prove-t2", "prove-t3"):
        p = sub.add_parser(name)
        p.add_argument("sessions", nargs="+", type=Path)
        p.add_argument("--settle-ms", type=int, default=SETTLE_MS)
        p.add_argument("--out-dir", type=Path, default=talk1.TEMPLATES.parent)
        p.add_argument("--report", type=Path)
        if name == "cut":
            p.add_argument("--force", action="store_true", help="write even when NOT READY")
    a = ap.parse_args()
    out: dict[str, Any]
    if a.cmd == "drive":
        out = drive(a.npc, a.first)
    elif a.cmd == "contact":
        import ro_agent as r

        with r.session("rule:talk-calibrate") as (agent, screen):
            doc = live_contact(a.npc, agent, screen)
            io = talk1.LiveIo(agent, screen, nd.DialogTemplates({}))
            io.last_action = doc["t_click"]
            grab_frames(io, doc, 4)
            _save_steps(doc)
        out = {"session": doc["session"], "clicked": doc["t_click"] is not None}
    elif a.cmd in ("key", "click", "frames"):
        out = one_step(a.cmd, a)
    elif a.cmd == "collect":
        out = collect(_doc())
    else:
        if a.cmd == "cut":
            out = cut(a.sessions, a.settle_ms, a.out_dir, a.force)
        else:
            fn = prove_t2 if a.cmd == "prove-t2" else prove_t3
            out = fn(a.sessions, a.settle_ms, a.out_dir)
    text = json.dumps(out, indent=1, default=str)
    if getattr(a, "report", None):
        a.report.write_text(text + "\n")
    print(text, flush=True)
    verdict = str(out.get("verdict", ""))
    return 0 if not verdict or verdict.startswith(("PASS", "READY")) else 1


if __name__ == "__main__":
    sys.exit(main())
