"""scripts/talk_calibrate.py (talk@1 T2 / T3 / T4 / T5 tooling): the packet truth of the dialog
(labels, the settle rule), the menu rows labelled by STRUCTURE, the template-free driver's
decisions, and cut -> prove end to end on SYNTHETIC sessions (frames drawn to the measured geometry
with a synthetic bitmap font, packets and the step log written to a temporary directory). No
client pixels, no server strings, no input."""

from __future__ import annotations

import gzip
import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import numpy as np
import pytest

from poring_env import npc_dialog as nd

SCRIPTS = Path(__file__).resolve().parents[2].parent / "scripts"
S = 1_000_000_000
G = nd.GEOMETRY
GID = 110_000_123


@pytest.fixture(scope="module")
def tc() -> ModuleType:
    sys.path.insert(0, str(SCRIPTS))
    spec = importlib.util.spec_from_file_location("talk_calibrate", SCRIPTS / "talk_calibrate.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["talk_calibrate"] = mod
    spec.loader.exec_module(mod)
    return mod


# --- a synthetic font and synthetic windows -------------------------------------------------

CHARS = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz."


def _font() -> dict[str, np.ndarray]:
    rng = np.random.default_rng(11)
    out: dict[str, np.ndarray] = {}
    for c in CHARS:
        w = 1 if c in "il." else int(rng.integers(3, 8))
        g = np.zeros((16, w), bool)
        g[2:12] = rng.random((10, w)) < 0.45
        for x in range(w):
            g[2 + int(rng.integers(0, 10)), x] = True
        out[c] = g
    return out


FONT = _font()
OPTS = ["Alpha", "Beta gamma", "Delta epsilon zeta", "Eta", "Theta iota kappa", "Lambda mu",
        "Omicron pi rho sigma"]  # fmt: skip


def put_text(row: np.ndarray, text: str) -> None:
    x = 3
    for c in text:
        if c == " ":
            x += 4
            continue
        g = FONT[c]
        row[:, x : x + g.shape[1]][g] = 0
        x += g.shape[1] + 1


def scene(seed: int, h: int = 480, w: int = 640) -> np.ndarray:
    return (np.random.default_rng(seed).random((h, w, 3)) * 255).astype(np.uint8)


def button(seed: int) -> np.ndarray:
    """A button image: a light face and a dark label (as the client's)."""
    img = (np.random.default_rng(seed).random((20, 42)) * 60 + 180).astype(np.uint8)
    img[6:14, 12:30][np.random.default_rng(seed + 9).random((8, 18)) < 0.5] = 50
    return img


NEXT_IMG, CLOSE_IMG, BTN_IMG = button(1), button(2), button(3)


def _frame(img: np.ndarray, origin: tuple[int, int], window: str) -> np.ndarray:
    w, h = G.size(window)
    x, y = origin
    win = img[y : y + h, x : x + w]
    win[:] = 255
    c = G.corner
    win[2, c : w - c] = 198
    win[h - 3, c : w - c] = 198
    win[c : h - c, 2] = 198
    win[c : h - c, w - 3] = 198
    return win


def draw(img: np.ndarray, dialog: str | None, menu: tuple[int, int] | None,
         page: int = 0) -> np.ndarray:  # fmt: skip
    """``dialog``: "next" | "close" | "blank" | None; ``menu``: (top, selected) of OPTS."""
    if dialog is not None:
        win = _frame(img, nd.CAPTURE_ORIGINS_DIALOG, nd.DIALOG)
        x, y, w, h = G.dialog_text
        win[y : y + h, x : x + w] = 247
        rng = np.random.default_rng(page)
        win[20:60, 15 : 15 + 200][rng.random((40, 200)) < 0.2] = 0
        bx, by, bw, bh = G.dialog_button
        if dialog in ("next", "close"):
            win[by : by + bh, bx : bx + bw] = (NEXT_IMG if dialog == "next" else CLOSE_IMG)[
                ..., None
            ]
    if menu is not None:
        top, sel = menu
        win = _frame(img, nd.CAPTURE_ORIGINS_MENU, nd.MENU)
        lx, ly, lw, lh = G.menu_list
        win[ly : ly + lh, lx : lx + lw] = 247
        for k in range(4):
            rt = G.row_top + k * G.row_pitch
            if top + k == sel:
                win[rt : rt + 15, lx : lx + lw] = (255, 222, 206)
            if top + k < len(OPTS):
                put_text(win[rt : rt + 16, G.row_text[0] : G.row_text[0] + G.row_text[1]],
                         OPTS[top + k])  # fmt: skip
        for name in (nd.UP, nd.DOWN):
            ax, ay, aw, ah = G.element_box(name)
            win[ay + 2 : ay + ah - 2, ax + 3 : ax + aw - 3] = (160, 70, 60)
        tx, ty, tw, th = G.track
        win[ty : ty + th, tx + 2 : tx + tw - 2] = (222, 222, 214)
        t0 = round(top * 17 / 3)
        win[ty + t0 : ty + t0 + 22, tx + 2 : tx + tw - 2] = (230, 160, 90)
        for name in (nd.OK, nd.CANCEL):
            bx, by, bw, bh = G.element_box(name)
            win[by : by + bh, bx : bx + bw] = (BTN_IMG if name == nd.OK else 255 - BTN_IMG)[
                ..., None
            ]
    return img


nd.CAPTURE_ORIGINS_DIALOG = (201, 101)  # type: ignore[attr-defined]
nd.CAPTURE_ORIGINS_MENU = (201, 301)  # type: ignore[attr-defined]


def ev(t: float, typ: str, **f: Any) -> dict[str, Any]:
    return {"t_mono_ns": int(t * S), "type": typ, "npc_gid": GID, **f}


def session(root: Path, name: str, seed: int, first: int = 3) -> Path:
    """One deliberate dialog: contact, 2 NEXT pages, the menu (scrolled to the bottom), choose
    ``first``, 1 page, the menu again, the end option, CLOSE, closed. Frames 0.8 s after each
    change; packets; the step log."""
    from PIL import Image

    d = root / name
    (d / "frames").mkdir(parents=True)
    events = [ev(1.0, "npc_contact", contact_type=1)]
    shots: list[tuple[float, str | None, tuple[int, int] | None, int]] = [(0.5, None, None, 0)]
    t = 1.2
    page = 0
    for _ in range(2):
        events += [ev(t, "npc_say", text="x", raw_hex=""), ev(t, "npc_wait")]
        shots += [(t + 0.8, "next", None, page), (t + 1.0, "next", None, page)]
        t += 1.2
        events.append(ev(t, "npc_next_click"))
        page += 1
        t += 0.1
    for round_ in range(2):
        events.append(ev(t, "npc_menu", options=OPTS, raw_hex=""))
        want = first - 1 if round_ == 0 else len(OPTS) - 1
        for top, sel in [(0, 0), (0, 2), (1, 4), (3, 5), (3, 6), (2, 2)][: 3 + 3 * (1 - round_)]:
            shots.append((t + 0.8, "blank", (top, sel), page))
            t += 0.9
        t += 0.2
        events.append(ev(t, "npc_choose", choice=want + 1, cancelled=False))
        t += 0.1
        page += 1
        if round_ == 0:
            events += [ev(t, "npc_say", text="y", raw_hex=""), ev(t, "npc_wait")]
            shots.append((t + 0.8, "next", None, page))
            t += 1.2
            events.append(ev(t, "npc_next_click"))
            t += 0.1
    events += [ev(t, "npc_say", text="z", raw_hex=""), ev(t, "npc_close")]
    shots += [(t + 0.8, "close", None, page), (t + 1.0, "close", None, page)]
    t += 1.2
    events.append(ev(t, "npc_close_click"))
    shots += [(t + 0.8, None, None, 0), (t + 1.0, None, None, 0)]
    for k, (ts, dlg, menu, pg) in enumerate(shots):
        img = draw(scene(seed + k), dlg, menu, pg)
        Image.fromarray(img[..., ::-1]).save(d / "frames" / f"{k:04d}-{int(ts * S)}.png")
    with gzip.open(d / "packets.jsonl.gz", "wt") as f:
        for e in events:
            f.write(json.dumps(e) + "\n")
    (d / "talk_cal.json").write_text(json.dumps({"session": name, "steps": []}))
    return d


# --- packet truth -------------------------------------------------------------------------------


def test_the_dialog_timeline_and_the_settle_rule(tc: Any) -> None:
    events = [ev(1.0, "npc_contact", contact_type=1), ev(1.1, "npc_say", text="", raw_hex=""),
              ev(1.1, "npc_wait"), ev(2.0, "npc_next_click"),
              ev(2.1, "npc_menu", options=OPTS, raw_hex=""), ev(3.0, "npc_choose", choice=255,
                                                                 cancelled=True),
              {**ev(3.5, "npc_say", text="", raw_hex=""), "npc_gid": 999},  # another NPC
              ev(4.0, "npc_contact", contact_type=1), ev(4.1, "npc_say", text="", raw_hex=""),
              ev(4.2, "npc_close"), ev(5.0, "npc_close_click")]  # fmt: skip
    tl = tc.dialog_timeline(events)
    settle = 600_000_000
    at = {s: tc.label_at(tl, int(s * S), settle) for s in (0.5, 1.5, 1.8, 2.9, 3.7, 4.9, 5.7)}
    assert at[0.5] == tc.CLOSED and at[1.5] is None  # unsettled: no label
    assert at[1.8] == tc.Label(True, False, "next")
    assert at[2.9] == tc.Label(True, True, None, tuple(OPTS))
    assert at[3.7] == tc.CLOSED  # cancelled: both windows close; the other NPC is ignored
    assert at[4.9] == tc.Label(True, False, "close") and at[5.7] == tc.CLOSED
    assert tc.label_at(tl, int(1.8 * S), settle, actions=[int(1.5 * S)]) is None  # our step


def test_a_close_after_our_close_click_opens_no_window(tc: Any) -> None:
    """The city guide (2026-10-09 15:40): ZC_CLOSE_DIALOG again 0.5 ms after our close click; the
    client showed no window on the six frames after it, so the label stays CLOSED."""
    events = [ev(1.0, "npc_contact", contact_type=1), ev(1.1, "npc_say", text="", raw_hex=""),
              ev(1.2, "npc_close"), ev(2.0, "npc_close_click"),
              ev(2.0005, "npc_close")]  # fmt: skip
    tl = tc.dialog_timeline(events)
    settle = 600_000_000
    assert tc.label_at(tl, int(1.9 * S), settle) == tc.Label(True, False, "close")
    assert tc.label_at(tl, int(3.0 * S), settle) == tc.CLOSED


def test_rows_are_labelled_by_structure_and_the_thumb(tc: Any) -> None:
    img = draw(scene(1), "blank", (2, 3))
    o = nd.CAPTURE_ORIGINS_MENU
    rows = [img[o[1] + y : o[1] + y + h, o[0] + x : o[0] + x + w]
            for x, y, w, h in (G.row_box(k) for k in range(4))]  # fmt: skip
    got = tc.align_rows(rows, OPTS, (round(2 * 17 / 3), round(2 * 17 / 3) + 22))
    assert got == (2, OPTS[2:6])
    assert tc.align_rows(rows, OPTS, (0, 22)) == "thumb_disagrees"
    assert tc.align_rows(rows, ["Alpha", "Beta"]) == "no_structure_fit"
    assert tc.structure("Delta epsilon zeta ") == (16, tuple([False] * 4 + [True] + [False] * 6
                                                          + [True] + [False] * 3))  # fmt: skip


def test_the_driver_reads_windows_without_templates(tc: Any) -> None:
    c = tc.coarse(draw(scene(2), "next", None))
    assert (c.dialog, c.menu, c.button) == (True, False, True)
    assert tc.drive_keys(c, 2, 7) == ["Enter"]
    c = tc.coarse(draw(scene(3), "blank", None))
    assert tc.drive_keys(c, 2, 7) == "wait"
    c = tc.coarse(draw(scene(4), "blank", (1, 4)))
    assert c.menu and c.highlight == 3 and tc.selected_index(c, 7) == 4
    assert tc.drive_keys(c, 2, 7) == ["ArrowUp"] and tc.drive_keys(c, 6, 7) == ["ArrowDown"]
    assert tc.drive_keys(c, 4, 7) == ["Enter"]
    assert tc.drive_keys(tc.coarse(scene(5)), 2, 7) == "stop"
    a, b = tc.coarse(draw(scene(6), "next", None, page=1)), tc.coarse(draw(scene(6), "next", None))
    assert a != b  # each page differs: the no-progress guard does not fire on new pages


def test_the_stand_cell(tc: Any) -> None:
    walk = np.zeros((200, 200), bool)
    walk[50:100, 96:104] = True
    assert tc.stand_cell(walk, (103, 76), [(103, 71)]) == (103, 79)
    assert tc.stand_cell(walk, (103, 71), [(103, 76)]) == (100, 71)  # (103, 74): 2 from (103, 76)
    assert tc.stand_cell(np.zeros((200, 200), bool), (103, 76), []) is None


def test_cut_then_prove_on_held_out_sessions(tc: Any, tmp_path: Path,
                                             monkeypatch: pytest.MonkeyPatch) -> None:  # fmt: skip
    monkeypatch.setattr(tc, "DIALOG_O", nd.CAPTURE_ORIGINS_DIALOG)
    monkeypatch.setattr(tc, "MENU_O", nd.CAPTURE_ORIGINS_MENU)
    monkeypatch.setattr(tc, "PROVE_T2_MIN", 10)
    a = [session(tmp_path, "A0", 100, first=2)]
    b = [session(tmp_path, "B0", 900, first=5)]
    out = tmp_path / "anchors"
    rep = tc.cut(a, 600, out)
    assert rep["verdict"].startswith("READY"), json.dumps(rep, default=str)[:2000]
    assert rep["missing_t2"] == [] and rep["t2_train"]["disagree"] == []
    assert rep["t3_held_self_check"]["wrong"] == [] and rep["t3_fit"]["gaps1"] == [5]
    assert (out / "npc_dialog" / nd.PARAMS_FILE).exists() and (out / "menu_glyphs.npz").exists()
    p2 = tc.prove_t2(b, 600, out)
    assert p2["verdict"] == "PASS", json.dumps(p2, default=str)[:2000]
    assert set(p2["classes"]) == {"no_window", "dialog_next", "dialog_close", "menu"}
    p3 = tc.prove_t3(b, 600, out)
    assert p3["verdict"] == "PASS", json.dumps(p3, default=str)[:2000]
    assert p3["exact"] == p3["rows"] > 0 and p3["neg_wrong"] == []
    assert all(c["options"] == c["read_exactly"] for c in p3["coverage"].values())
    assert tc.prove_t2(a, 600, out)["verdict"].startswith("REFUSED")  # cut sessions never prove
    assert tc.prove_t3(a[:1], 600, out)["verdict"].startswith("REFUSED")


def test_a_cut_without_close_frames_is_not_ready_and_writes_nothing(
    tc: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(tc, "DIALOG_O", nd.CAPTURE_ORIGINS_DIALOG)
    monkeypatch.setattr(tc, "MENU_O", nd.CAPTURE_ORIGINS_MENU)
    s = session(tmp_path, "A0", 50)
    with gzip.open(s / "packets.jsonl.gz", "rt") as f:
        t_close = [json.loads(x)["t_mono_ns"] for x in f if '"npc_close"' in x][0]
    for p in (s / "frames").glob("*.png"):
        if int(p.stem.split("-")[1]) > t_close:  # the CLOSE and closed frames at the end
            p.unlink()
    rep = tc.cut([s], 600, tmp_path / "anchors")
    assert rep["verdict"].startswith("NOT READY") and nd.CLOSE in rep["missing_t2"]
    assert not (tmp_path / "anchors" / "npc_dialog").exists()


# --- the S2 set (2026-10-09, poring_env.ui_sets): prove-t2 / prove-t3 record their verdict --------


def test_an_s2_prove_records_a_pass_and_removes_it_on_a_failure(
    tc: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from poring_env import ui_sets

    monkeypatch.setattr(tc, "DIALOG_O", nd.CAPTURE_ORIGINS_DIALOG)
    monkeypatch.setattr(tc, "MENU_O", nd.CAPTURE_ORIGINS_MENU)
    monkeypatch.setattr(tc, "PROVE_T2_MIN", 10)
    a = [session(tmp_path, "A0", 100, first=2)]
    b = [session(tmp_path, "B0", 900, first=5)]
    s2 = tmp_path / "s2"
    assert tc.cut(a, 600, s2)["verdict"].startswith("READY")
    assert ui_sets.problems(s2, ["t2"])  # cut, not proven
    p2 = tc.prove_t2(b, 600, s2, record=True)
    p3 = tc.prove_t3(b, 600, s2, record=True)
    assert p2["verdict"] == p3["verdict"] == "PASS" and p2["proof"] == p3["proof"] == "PASS"
    assert ui_sets.problems(s2, ["t2", "t3"]) == []
    entry = json.loads((s2 / ui_sets.PROOF_FILE).read_text())["components"]["t2"]
    assert entry["evidence"]["sessions"] == ["B0"] and entry["evidence"]["agree"] == p2["frames"]
    assert tc.prove_t2(a, 600, s2, record=True)["verdict"].startswith("REFUSED")
    assert ui_sets.problems(s2, ["t2"]) == []  # a refused prove proves nothing, removes nothing
    monkeypatch.setattr(tc, "PROVE_T2_MIN", 10_000)
    p2 = tc.prove_t2(b, 600, s2, record=True)
    assert p2["verdict"].startswith("INCOMPLETE") and p2["proof"] == "FAIL"
    assert ui_sets.problems(s2, ["t2"]) == ["t2: not proven"]
    assert ui_sets.problems(s2, ["t3"]) == []  # T3's own proof stands
    rdp = tmp_path / "rdp"
    assert tc.cut(a, 600, rdp)["verdict"].startswith("READY")
    assert tc.prove_t2(b, 600, rdp)["verdict"].startswith("INCOMPLETE")
    assert not (rdp / ui_sets.PROOF_FILE).exists()  # without record (rdp): no proof file


def test_attach_waits_for_a_persons_dialog_then_the_lease(tc: Any) -> None:
    """drive --attach: no input at all until a dialog shows on two agreeing frames AND the
    ASSIST lease has ended; else it says why (no key is pressed)."""
    closed = draw(scene(1), None, None)
    opened = draw(scene(1), "next", None)
    t = [0.0]

    def clock() -> float:
        return t[0]

    def sleep(s: float) -> None:
        t[0] += s

    frames = iter([closed, closed, closed, opened, opened, opened])
    leases = iter([{"lease_active": True}, {}, {"lease_active": False}])
    got = tc.wait_for_person(None, grab=lambda: next(frames), health=lambda: next(leases),
                             clock=clock, sleep=sleep)  # fmt: skip
    assert got is None
    assert tc.wait_for_person(None, grab=lambda: closed, health=lambda: {}, clock=clock,
                              sleep=sleep) == "no_dialog"  # fmt: skip
    assert tc.wait_for_person(None, grab=lambda: opened, health=lambda: {"lease_active": True},
                              clock=clock, sleep=sleep) == "lease_active"  # fmt: skip
