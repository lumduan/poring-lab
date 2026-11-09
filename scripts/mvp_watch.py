"""MVP WATCH (rogue-gef10.md Amendment A4; docs/planning/orclord-recognizer.md): "is the Orc Lord,
or its Orc Archers, in view?" from ONE frame's pixels, cheaply enough to run every ~0.5 s in the
runner (numpy only, one thread; ~25-35 ms per 1280 x 720 frame on this host, niced).

    model = mvp_watch.load()                       # data/mvp_watch/orclord-v1.npz (fails closed)
    model = mvp_watch.load(profile="stormy")       # data/mvp_watch/stormy-v1.npz (stormy only)
    v = mvp_watch.decide(frame_bgr, model)         # PURE: {"seen", "where", "score", "cue", ...}
    if v["seen"]: ...                              # the runner's flee rule (a Fly Wing at once)

PER BOSS (docs/planning/stormy-knight-recognizer.md B1): a model is fitted for ONE boss profile
(scripts/mvp_profiles.py: orclord, stormy) and its file names it (``profile``); ``load(...,
profile=P)`` refuses another profile's model. The Orc Lord's v1 file format is kept byte for byte
(no ``profile`` member: a file without one is the Orc Lord's), so its frozen sha256 stays.

PIXELS IN ONLY (rule 1): the decision reads the frame and the model, nothing else. Packets are the
offline truth the model was fitted and scored on (scripts/mvp_watch_study.py), never an input.

Two cues on a half-resolution view (every 2nd pixel), the client's UI windows and our own
character (the screen centre, with its HP / SP bars) left out:
- AURA (a rule, nothing learned): the client draws a bright green ring at the Orc Lord's feet (its
  boss effect). Its rim saturates the green channel (G >= 236, G - R >= 25, G - B >= 25), which the
  field's foliage does not reach; the score is the share of such pixels on an elliptical RING the
  aura's size, at the best position.
- PARTY (a linear window detector, learned on the DEV data): 8 x 8-pixel cells carry 11 features
  (a colour log-likelihood ratio of the party's own colours against the map's, the aura share, the
  mean R / G / B, the share of dark pixels, four gradient-orientation shares and the gradient
  energy); a 7 x 5-cell window (112 x 80 full pixels, a unit's size) is scored by a logistic
  regression trained on the Orc Lord's and its archers' windows against the hunting frames'.
`seen` when either score clears its frozen threshold. A frame that does not show the game (the
Basic Info title bar missing: a loading screen) is never `seen` (reason ``no_game_view``).

THE MODEL'S AURA MODE (stormy-knight-recognizer.md 9, round 2): how the two cues combine is the
model's own (``aura_mode``), so decide() follows the MODEL, not the code's profile values:
- ``or`` (every v1 model; a file without the field): seen = aura >= aura_thr OR party >= lin_thr;
- ``off``: the party detector alone (the aura's colour stays one of its cell features);
- ``and``: seen = party >= lin_thr OR (aura >= aura_thr AND party >= the AND threshold), the AND
  threshold = lin_thr - (1 - aura_and) x |lin_thr| (``aura_and`` 0.5: half a positive lin_thr).
An explicit ``cues`` argument (the Orc Lord's ("aura",) studies) still picks the cues.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import numpy.typing as npt

ROOT = Path(__file__).resolve().parents[1]
MODEL_DIR = ROOT / "data" / "mvp_watch"  # gitignored: a model holds client-derived pixel statistics
LEGACY_PROFILE = "orclord"  # every model before B1; its file format carries no profile field
DEFAULT_MODEL = MODEL_DIR / "orclord-v1.npz"  # the Orc Lord's (default_model(LEGACY_PROFILE))
NBINS = 32768  # 5 bits per channel: index (r >> 3) << 10 | (g >> 3) << 5 | (b >> 3)
STEP = 2  # the half-resolution view: every 2nd pixel of the 1280 x 720 frame
CELL = 8  # the party detector's cell (half-res px)
WIN = (7, 5)  # the party detector's window (cells: height, width)
N_FEATURES = 11
# client_layout.RECTS (x0, y0, x1, y1) in full-frame pixels; the hunt layout is the runner's
Rects = tuple[tuple[int, int, int, int], ...]
HUNT_RECTS: Rects = (
    (0, 0, 220, 143), (230, 0, 520, 33), (750, 0, 828, 36), (1135, 14, 1266, 162),
    (0, 532, 600, 626), (0, 668, 50, 720), (1228, 668, 1280, 720),
)  # fmt: skip
STANDARD_RECTS: Rects = (
    (0, 0, 220, 326), (230, 0, 520, 132), (750, 0, 828, 36), (1135, 14, 1266, 162),
    (0, 532, 600, 626), (0, 668, 50, 720), (1228, 668, 1280, 720),
)  # fmt: skip
# our own character and its HP / SP bars at the screen centre, left out of both cues (the bars' top
# was at y 358-396 on 99 % of 584 frames: the camera follows the ground's altitude)
CENTRE_BOX = (600, 250, 680, 412)
# around it, our own effects (potion sparkles, the weapon's light green swing arcs: x 574-712 on
# the DEV hunting frames) reach a party window's score; a window whose foot is in SELF_ZONE must
# clear the threshold by the model's ``zone_penalty`` more (orclord-recognizer.md Amendment B)
SELF_ZONE = (560, 230, 720, 450)
TITLE_BOX = (0, 0, 220, 16)  # Basic Info's title bar (full pixels), present in every layout
AURA_RULE = (236, 25)  # G >= 236, G - R >= 25, G - B >= 25 (the Orc Lord's; a model's aura_rule)
AURA_MODES = ("or", "and", "off")  # how a model combines its cues (``or``: every v1 model)
AURA_AND = 0.5  # ``and``: the share of a positive lin_thr the aura path's party score needs


class ModelUnavailable(RuntimeError):
    """No model here: a rule that needs it must not act on its absence (fail closed)."""


@dataclass(frozen=True)
class Model:
    body_lut: npt.NDArray[np.float32]  # (NBINS,) LLR: the party's own colours vs the map's
    lin_w: npt.NDArray[np.float32]  # (N_FEATURES, WIN[0], WIN[1]) the window's weights
    lin_b: float
    lin_thr: float
    aura_thr: float
    title: npt.NDArray[np.float32]  # the grey title bar at half resolution
    title_max: float = 15.0  # mean |difference| above which the frame is not the game
    # the aura's ring (defaults: the Orc Lord's, tuned to its sprite; per boss: mvp_profiles)
    ring: tuple[float, float, float, float] = (27.0, 15.0, 17.0, 8.0)  # outer a, b; inner a, b
    ring_cell: int = 3  # the ring's grid (half-res px)
    ring_dy: float = 8.0  # the ring's centre above the foot point (half-res px)
    zone_penalty: float = 0.0  # subtracted from party windows whose foot is in SELF_ZONE
    version: str = "orclord-v1"
    profile: str = LEGACY_PROFILE  # the boss profile it was fitted for (mvp_profiles)
    aura_rule: tuple[int, int] = AURA_RULE  # the rim's colour rule (aura_lut)
    aura_mode: str = "or"  # AURA_MODES: how the cues combine (decide)
    aura_and: float = AURA_AND  # ``and`` only: and_threshold()
    sha256: str = ""
    _cache: dict[Any, Any] = field(default_factory=dict, compare=False, repr=False)


# --- the pure parts ----------------------------------------------------------------------------


def aura_lut(rule: tuple[int, int] = AURA_RULE) -> npt.NDArray[np.float32]:
    """1.0 for the aura rim's colour bins (each bin judged at its centre), else 0.0."""
    b = np.arange(NBINS)
    r, g, bl = (b >> 10) * 8 + 4, ((b >> 5) & 31) * 8 + 4, (b & 31) * 8 + 4
    gmin, d = rule
    return ((g >= gmin) & (g - r >= d) & (g - bl >= d)).astype(np.float32)


def lut_index(half: npt.NDArray[np.uint8]) -> npt.NDArray[np.uint16]:
    """BGR uint8 pixels -> the 5-bit colour bin of each."""
    r = (half[..., 2] >> 3).astype(np.uint16)
    g = (half[..., 1] >> 3).astype(np.uint16)
    b = (half[..., 0] >> 3).astype(np.uint16)
    return ((r << 10) | (g << 5) | b).astype(np.uint16, copy=False)


def rect_mask(shape: tuple[int, int], rects: tuple[tuple[int, int, int, int], ...],
              step: int = STEP) -> npt.NDArray[np.bool_]:  # fmt: skip
    """Full-frame rectangles (x0, y0, x1, y1) -> a mask on the ``step``-subsampled view."""
    m = np.zeros(shape, bool)
    for x0, y0, x1, y1 in rects:
        m[y0 // step : -(-y1 // step), x0 // step : -(-x1 // step)] = True
    return m


def pool(m: npt.NDArray[Any], cell: int) -> npt.NDArray[np.float32]:
    """Mean over ``cell`` x ``cell`` blocks (the edges that do not fill a block are dropped)."""
    h, w = m.shape[0] // cell, m.shape[1] // cell
    out: npt.NDArray[np.float32] = (
        m[: h * cell, : w * cell].reshape(h, cell, w, cell).mean(axis=(1, 3), dtype=np.float32)
    )
    return out


def ring_kernel(ring: tuple[float, float, float, float], cell: int) -> npt.NDArray[np.bool_]:
    """The aura's elliptical ring on a grid of ``cell`` half-res px."""
    a, b, ai, bi = ring
    h, w = int(np.ceil(2 * b / cell)) + 1, int(np.ceil(2 * a / cell)) + 1
    yy, xx = np.mgrid[0:h, 0:w]
    x, y = (xx - (w - 1) / 2) * cell, (yy - (h - 1) / 2) * cell
    out: npt.NDArray[np.bool_] = ((x / a) ** 2 + (y / b) ** 2 <= 1.0) & (
        (x / ai) ** 2 + (y / bi) ** 2 >= 1.0
    )
    return out


def aura_map(aura_px: npt.NDArray[np.float32], ring: tuple[float, float, float, float],
             cell: int) -> npt.NDArray[np.float32]:  # fmt: skip
    """The share of aura pixels on the ring at every grid position (top-left of its box);
    masked pixels must already be 0."""
    g = pool(aura_px, cell)
    k = ring_kernel(ring, cell)
    kh, kw = k.shape
    out = np.zeros((g.shape[0] - kh + 1, g.shape[1] - kw + 1), np.float32)
    for dy, dx in zip(*np.nonzero(k), strict=True):
        out += g[dy : dy + out.shape[0], dx : dx + out.shape[1]]
    out /= float(k.sum())
    return out


def cell_features(h: npt.NDArray[np.uint8], idx: npt.NDArray[np.uint16],
                  body_lut: npt.NDArray[np.float32],
                  aura_px: npt.NDArray[np.float32]) -> npt.NDArray[np.float32]:  # fmt: skip
    """The party detector's (N_FEATURES, 45, 80) cell features of the half-res view ``h``
    (360 x 640 BGR), its colour bins ``idx`` and its (masked) aura pixels ``aura_px``."""
    q4 = h[::2, ::2]
    grey = h[..., 1].astype(np.float32)  # the green channel stands in for luminance
    gx = np.zeros_like(grey)
    gy = np.zeros_like(grey)
    np.subtract(grey[:, 2:], grey[:, :-2], out=gx[:, 1:-1])
    np.subtract(grey[2:, :], grey[:-2, :], out=gy[1:-1, :])
    ax, ay = np.abs(gx), np.abs(gy)
    mag = ax + ay
    vert, horz = ax > 2 * ay, ay > 2 * ax
    diag = ~(vert | horz)
    same = (gx * gy) > 0
    o = [pool(mag * vert, CELL), pool(mag * horz, CELL), pool(mag * (diag & same), CELL),
         pool(mag * (diag & ~same), CELL)]  # fmt: skip
    tot = o[0] + o[1] + o[2] + o[3] + 8.0
    rgb = [pool(q4[..., i].astype(np.float32), CELL // 2) / 255.0 for i in (2, 1, 0)]
    dark = pool((q4[..., 1] < 45).astype(np.float32), CELL // 2)
    return np.stack([pool(body_lut[idx], CELL), pool(aura_px, CELL), *rgb, dark,
                     *(x / tot for x in o), np.log1p(tot) / 5.0])  # fmt: skip


def window_scores(feats: npt.NDArray[np.float32], w: npt.NDArray[np.float32],
                  b: float) -> npt.NDArray[np.float32]:  # fmt: skip
    """The linear window score at every window position (top-left cell), by correlation."""
    c, h, wd = feats.shape
    wh, ww = w.shape[1], w.shape[2]
    oh, ow = h - wh + 1, wd - ww + 1
    s = np.full((oh, ow), b, np.float32)
    for ci in range(c):
        for dy in range(wh):
            for dx in range(ww):
                s += w[ci, dy, dx] * feats[ci, dy : dy + oh, dx : dx + ow]
    return s


def window_vectors(feats: npt.NDArray[np.float32], win: tuple[int, int] = WIN
                   ) -> npt.NDArray[np.float32]:  # fmt: skip
    """(oh, ow, N_FEATURES * wh * ww): every window's feature vector, in w.reshape(-1)'s order
    (the training side's)."""
    c, h, wd = feats.shape
    wh, ww = win
    oh, ow = h - wh + 1, wd - ww + 1
    cols = [feats[:, dy : dy + oh, dx : dx + ow] for dy in range(wh) for dx in range(ww)]
    v = np.stack(cols, axis=1)  # (c, wh * ww, oh, ow)
    out: npt.NDArray[np.float32] = v.transpose(2, 3, 0, 1).reshape(oh, ow, -1)
    return out


def foot_window(fx: float, fy: float, win: tuple[int, int] = WIN) -> tuple[int, int]:
    """A half-res foot point -> the top-left cell of the window whose bottom centre it is."""
    return int(round(fy / CELL - win[0] + 0.5)), int(round(fx / CELL - win[1] / 2))


def valid_windows(skip: npt.NDArray[np.bool_], win: tuple[int, int] = WIN) -> npt.NDArray[np.bool_]:
    """A window is scored when its foot cell (bottom centre) is not mostly UI or the centre box;
    ``skip`` is the half-res mask."""
    sc = pool(skip.astype(np.float32), CELL) > 0.5
    h, w = sc.shape
    oh, ow = h - win[0] + 1, w - win[1] + 1
    out: npt.NDArray[np.bool_] = ~sc[win[0] - 1 : win[0] - 1 + oh, win[1] // 2 : win[1] // 2 + ow]
    return out


def model_cues(model: Model) -> tuple[str, ...]:
    """The cues a model decides with when the caller names none: ``off`` -> the party alone."""
    return ("party",) if model.aura_mode == "off" else ("aura", "party")


def and_threshold(model: Model) -> float:
    """``and``: the party score the aura path needs (half of a positive lin_thr by default)."""
    return model.lin_thr - (1.0 - model.aura_and) * abs(model.lin_thr)


def masks(model: Model, shape: tuple[int, int],
          ui_rects: tuple[tuple[int, int, int, int], ...]) -> tuple[Any, Any, Any]:  # fmt: skip
    """(the half-res skip mask: UI + centre, the valid party windows, the windows whose foot is
    in SELF_ZONE), cached per layout."""
    key = (shape, ui_rects)
    if key not in model._cache:
        skip = rect_mask(shape, ui_rects) | rect_mask(shape, (CENTRE_BOX,))
        zone = ~valid_windows(rect_mask(shape, (SELF_ZONE,)))
        model._cache[key] = (skip, valid_windows(skip), zone)
    if "aura_lut" not in model._cache:
        model._cache["aura_lut"] = aura_lut(model.aura_rule)
    out: tuple[Any, Any, Any] = model._cache[key]
    return out


def game_view(half: npt.NDArray[np.uint8], model: Model) -> bool:
    """The Basic Info title bar is where the game draws it (not a loading screen)."""
    x0, y0, x1, y1 = (v // STEP for v in TITLE_BOX)
    grey = half[y0:y1, x0:x1].astype(np.float32).mean(axis=2)
    if grey.shape != model.title.shape:
        return False
    return float(np.abs(grey - model.title).mean()) <= model.title_max


def scores(half: npt.NDArray[np.uint8], model: Model, ui_rects: Rects = HUNT_RECTS,
           party: bool = True) -> dict[str, Any]:  # fmt: skip
    """The cues' maps of one frame's half-res view (decide's inputs; the study's too); with
    ``party`` False only the aura's (about a third of the time)."""
    skip, valid, zone = masks(model, half.shape[:2], ui_rects)
    idx = lut_index(half)
    apx = model._cache["aura_lut"][idx]
    apx[skip] = 0.0
    am = aura_map(apx, model.ring, model.ring_cell)
    if not party:
        return {"aura_map": am, "party_map": None}
    feats = cell_features(half, idx, model.body_lut, apx)
    raw = window_scores(feats, model.lin_w, model.lin_b)
    raw[~valid] = -np.inf
    pm = raw - np.where(zone, model.zone_penalty, 0.0).astype(np.float32)
    return {
        "aura_map": am,
        "party_map": pm,
        "raw_party": raw,
        "feats": feats,
        "valid": valid,
        "zone": zone,
    }


def decide(frame: npt.NDArray[np.uint8], model: Model, ui_rects: Rects = HUNT_RECTS,
           cues: tuple[str, ...] | None = None) -> dict[str, Any]:  # fmt: skip
    """PURE: one 1280 x 720 BGR(A) frame -> {"seen", "where", "score", "cue", "aura", "party",
    "reason"}. ``where`` is the full-frame pixel of the winning cue's foot point (the aura ring's,
    or the party window's bottom centre); ``score`` = the larger relative margin over its
    threshold (>= 0: seen). ``cues`` None: the model's own (model_cues: both for every v1 model,
    the party alone for an ``off`` one); ("aura",) is the aura rule alone (orclord-recognizer.md
    6: no hunting false positive in 33 min, POST-HOC). Both cues combine by the model's
    ``aura_mode`` (``or``, or ``and``: the aura path also needs and_threshold())."""
    frame = np.asarray(frame)[..., :3]
    out: dict[str, Any] = {"seen": False, "where": None, "score": None, "cue": None,
                           "aura": None, "party": None, "reason": None}  # fmt: skip
    if frame.shape[:2] != (720, 1280):
        out["reason"] = "not_1280x720"
        return out
    return decide_half(frame[::STEP, ::STEP], model, ui_rects, out, cues)


def decide_half(half: npt.NDArray[np.uint8], model: Model,
                ui_rects: tuple[tuple[int, int, int, int], ...] = HUNT_RECTS,
                out: dict[str, Any] | None = None,
                cues: tuple[str, ...] | None = None) -> dict[str, Any]:  # fmt: skip
    """decide() on the half-res view (360 x 640) the study caches."""
    if out is None:
        out = {"seen": False, "where": None, "score": None, "cue": None, "aura": None,
               "party": None, "reason": None}  # fmt: skip
    if cues is None:
        cues = model_cues(model)
    if not set(cues) <= {"aura", "party"} or not cues:
        raise ValueError(f"unknown cues {cues!r}")
    if model.aura_mode not in AURA_MODES:
        raise ValueError(f"unknown aura_mode {model.aura_mode!r}")
    if not game_view(half, model):
        out["reason"] = "no_game_view"
        return out
    m = scores(half, model, ui_rects, party="party" in cues)
    am, pm = m["aura_map"], m["party_map"]
    ai = int(am.argmax())
    sa = float(am.flat[ai]) if "aura" in cues else -np.inf
    pi, sp = 0, -np.inf
    if pm is not None:
        pi = int(pm.argmax())
        sp = float(pm.flat[pi])
    ma = (sa - model.aura_thr) / max(model.aura_thr, 1e-6)
    mp = (sp - model.lin_thr) / max(abs(model.lin_thr), 1e-6)
    both_and = model.aura_mode == "and" and pm is not None and "aura" in cues
    if both_and:  # the aura path also needs the party's AND threshold
        at = and_threshold(model)
        ma = min(ma, (sp - at) / max(abs(at), 1e-6))
    out.update(aura=round(float(am.flat[ai]), 4), score=round(max(ma, mp), 4),
               party=None if pm is None else round(sp, 3))  # fmt: skip
    if "aura" in cues and ma >= mp:
        y, x = divmod(ai, am.shape[1])
        kh, kw = ring_kernel(model.ring, model.ring_cell).shape
        cx = (x + (kw - 1) / 2 + 0.5) * model.ring_cell
        cy = (y + (kh - 1) / 2 + 0.5) * model.ring_cell + model.ring_dy
        out["cue"] = "aura"
    else:
        y, x = divmod(pi, pm.shape[1])
        cx, cy = (x + WIN[1] / 2) * CELL, (y + WIN[0]) * CELL
        out["cue"] = "party"
    out["where"] = (round(cx * STEP), round(cy * STEP))
    aura_ok = sa >= model.aura_thr and (not both_and or sp >= and_threshold(model))
    out["seen"] = aura_ok or sp >= model.lin_thr
    return out


# --- the loader ---------------------------------------------------------------------------------


def check_profile(name: str) -> str:
    """A profile name is a lower-case identifier (it names a file: default_model)."""
    if not (name.isascii() and name.isidentifier() and name == name.lower()):
        raise ValueError(f"bad profile name {name!r}")
    return name


def default_model(profile: str = LEGACY_PROFILE) -> Path:
    """A profile's default model path: data/mvp_watch/<profile>-v1.npz."""
    return MODEL_DIR / f"{check_profile(profile)}-v1.npz"


def save(path: Path, model: Model) -> str:
    """Write a model (np.savez, no pickle) and return its sha256. The Orc Lord's (LEGACY_PROFILE)
    keeps the v1 format byte for byte: no ``profile`` / ``aura_rule`` / ``aura_mode`` member (so
    it cannot carry another aura rule or mode); every other profile's file names its profile and
    its aura rule, and its aura mode when it is not ``or`` (with ``aura_and`` for ``and``): an
    ``or`` model keeps the bytes of B1's format."""
    check_profile(model.profile)
    if model.aura_mode not in AURA_MODES:
        raise ValueError(f"aura_mode {model.aura_mode!r} not in {AURA_MODES}")
    legacy = model.profile == LEGACY_PROFILE
    if legacy and tuple(model.aura_rule) != AURA_RULE:
        raise ValueError(f"an {LEGACY_PROFILE} model keeps the v1 format: aura_rule {AURA_RULE}")
    if legacy and model.aura_mode != "or":
        raise ValueError(f"an {LEGACY_PROFILE} model keeps the v1 format: aura_mode 'or'")
    path.parent.mkdir(parents=True, exist_ok=True)
    arrays = {
        "body_lut": model.body_lut.astype(np.float32),
        "lin_w": model.lin_w.astype(np.float32),
        "title": model.title.astype(np.float32),
        "scalars": np.array(
            [
                model.lin_b,
                model.lin_thr,
                model.aura_thr,
                model.title_max,
                model.ring_cell,
                model.ring_dy,
                model.zone_penalty,
            ],
            np.float64,
        ),  # fmt: skip
        "ring": np.array(model.ring, np.float64),
        "version": np.array(model.version),
    }
    if not legacy:
        arrays["profile"] = np.array(model.profile)
        arrays["aura_rule"] = np.array(model.aura_rule, np.int64)
        if model.aura_mode != "or":
            arrays["aura_mode"] = np.array(model.aura_mode)
        if model.aura_mode == "and":
            arrays["aura_and"] = np.array(model.aura_and, np.float64)
    tmp = path.with_name(path.name + ".tmp")
    with tmp.open("wb") as fh:
        np.savez(fh, **arrays)  # type: ignore[arg-type]
    tmp.replace(path)
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path: Path | None = None, sha256: str | None = None, profile: str | None = None
         ) -> Model:  # fmt: skip
    """The frozen model, fail closed: a missing file, a wrong shape, a sha256 mismatch or (with
    ``profile``) another boss profile's model raises ModelUnavailable (the runner must then not
    rely on a flee rule that cannot see). ``path`` None: default_model(profile), the Orc Lord's
    without one. A file without a ``profile`` member is the Orc Lord's (LEGACY_PROFILE)."""
    if path is None:
        path = default_model(LEGACY_PROFILE if profile is None else profile)
    if not path.exists():
        raise ModelUnavailable(f"{path} missing (docs/planning/orclord-recognizer.md)")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if sha256 is not None and digest != sha256:
        raise ModelUnavailable(f"{path}: sha256 {digest[:16]} != {sha256[:16]}")
    with np.load(path, allow_pickle=False) as z:
        body, w = z["body_lut"].astype(np.float32), z["lin_w"].astype(np.float32)
        if body.shape != (NBINS,) or w.shape != (N_FEATURES, *WIN):
            raise ModelUnavailable(f"{path}: shapes {body.shape} / {w.shape}")
        sc, ring = z["scalars"], z["ring"]
        got = str(z["profile"]) if "profile" in z.files else LEGACY_PROFILE
        if profile is not None and got != profile:
            raise ModelUnavailable(f"{path}: a {got!r} model, not {profile!r}")
        rule = tuple(int(v) for v in z["aura_rule"]) if "aura_rule" in z.files else AURA_RULE
        if len(rule) != 2:
            raise ModelUnavailable(f"{path}: aura_rule {rule}")
        mode = str(z["aura_mode"]) if "aura_mode" in z.files else "or"
        if mode not in AURA_MODES:
            raise ModelUnavailable(f"{path}: aura_mode {mode!r}")
        aura_and = float(z["aura_and"]) if "aura_and" in z.files else AURA_AND
        return Model(
            body_lut=body, lin_w=w, lin_b=float(sc[0]), lin_thr=float(sc[1]),
            aura_thr=float(sc[2]), title=z["title"].astype(np.float32), title_max=float(sc[3]),
            ring=(float(ring[0]), float(ring[1]), float(ring[2]), float(ring[3])),
            ring_cell=int(sc[4]), ring_dy=float(sc[5]), zone_penalty=float(sc[6]),
            version=str(z["version"]), profile=got, aura_rule=(rule[0], rule[1]),
            aura_mode=mode, aura_and=aura_and, sha256=digest,
        )  # fmt: skip


def timed(frame: npt.NDArray[np.uint8], model: Model, **kw: Any) -> tuple[dict[str, Any], float]:
    """decide() and its wall time in ms (the runner logs both)."""
    t = time.perf_counter()
    v = decide(frame, model, **kw)
    return v, (time.perf_counter() - t) * 1e3
