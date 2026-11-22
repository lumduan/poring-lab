#!/usr/bin/env python3
"""FLOOR-ITEM labels on xmas_dun02: the rule ``xmas02-fi-1`` (docs/planning/xmas02-detector.md
Amendment O, sections O.3-O.6 and O.9; ACCEPTED by O1, 2026-11-10 10:29 ICT, with O.12's
defaults: one class ``floor_item``, a SEPARATE item model ``xmas02-fi``). Tools T-O1 and T-O3.

    fi_labels.py freeze [--out PARAMS]                       O.3 (g): the frozen params file, once
    fi_labels.py freeze-v2 --v1 PARAMS --labels FIT.json DEV.json [--out PARAMS_V2]
                                                             O3: v1 + the absent rule's ids, once
    fi_labels.py label PART --split train|val --params PARAMS --out LABELS.json [--workers N]
    fi_labels.py label PART --eval-test --model WEIGHTS --model-sha256 HEX --params PARAMS
                       --out LABELS.json                      O.9: fiT only, after the model froze
    fi_labels.py g2 LABELS.json... --out JSON                O.6's join rule (G2) per session
    fi_labels.py pack LABELS.json... --params PARAMS --seed 61 --out JSON        O.5: T2-items
    fi_labels.py pack LABELS.json... --eval-test --params PARAMS --seed 63 --out JSON    O.9
    fi_labels.py refs LABELS.json... --out REFS.json         predict_dir --refs for the evaluation

AT 1920 x 1080 (docs/planning/xmas02-items-1080.md, tools T-I1, T-I2, T-I4; the virtual 1280 x 720
picture of the fullscreen client, rec_paths' ``virtual-1080`` path):
    fi_labels.py fit-1080 PART --out REPORT.json [--workers N]
                                          T-I2: the 1080 constants FITTED on ifF (nothing frozen)
    fi_labels.py freeze-1080 --fit REPORT.json [--out PARAMS]
                                          T-I2: items-params-1080.json, frozen once (its sha256)
    fi_labels.py label PART --spec 1080 --split train|val --params PARAMS --out LABELS.json
    fi_labels.py pack LABELS.json... --spec 1080 --params PARAMS --seed 71 --out JSON
                                          section 6: T2 on the 1080 TRAIN labels
    fi_labels.py pack LABELS.json... --spec 1080 --round 6 --eval-test --params PARAMS --seed N
    fi_labels.py pack LABELS.json... --spec 1080 --round 7 --eval-test --params PARAMS --seed 74
    fi_labels.py pack LABELS.json... --spec 1080 --round 9 --eval-test --params PARAMS --seed 76
    fi_labels.py pack LABELS.json... --spec 1080 --round 10 --eval-test --params PARAMS --seed 77
                      --out JSON          T-I4: round 6's evaluation pack
``--spec 1080`` is XMAS02_FI_1080: rule xmas02-fi-1's text under its own name xmas02-fi-1-1080
(RULE_1080), the 1080 monster params (9c73278f), FIT / VAL = ifF, the held-out ifH1 / ifH2 /
ifsH1 refused by NAME (under either spec: foreign_refusal), and every pixel constant (the
anchor, the scale, r_label, T_item, the bar, the self box, the margin) READ from its frozen params
(freeze-1080), never from the 720 values; a recording of the other screen is refused once opened
(its manifest's path). The 720 spec (the default) is unchanged.

THE RULE (O.3, every value fixed on FIT p31 and frozen by ``freeze``):
- (a) an item lies on the floor from its ``floor_item_appear`` to its ``floor_item_vanish`` or our
  map change (item_labels.floor_items); on a frame at capture time t it is LABELLED when t_a + 2.2 s
  <= t < t_v; the FRAME is excluded while one settles (``item_settling``) or vanishes
  (``item_vanishing``, t_v <= t < t_v + 0.6 s). Frames: the monsters' candidate frames
  (map_labels.RecSession, our character still, 1d 120 ms) whose layout is the session's
  (``ui_layout_mismatch``) -- item-free ones too (O.3 (a); the study's dry run skipped that read
  on item-free frames, so its negative count is an upper bound of this one's);
- (b) the cell (x + OX[sub_x], y + OY[sub_y]) of item-class.md 8a, projected like a monster's
  anchor (camera on our cell at tw = t - 120 ms, the GAT altitude), + the ANCHOR (-4, +2) px;
- (c) the box: the item's OWN client sprite (one frame) at scale 1.0, moved by the best masked
  COLOUR NCC (the 3 channels as one vector) within +-10 px; below T_item 0.65 or at the search
  edge: ``item_unfit``;
- (d) frame exclusions: item_settling, item_vanishing, ui_partial / edge_partial, stacked (two
  item boxes IoU >= 0.5), under_self (labels_v2's 34 x 74 self box + 4 px), under_bar (the
  FIT-measured bar (-31, +10, +28, +18) px from our anchor), under_unit (the generic unit box at tw
  and tw - 0.5 s), item_unfit, item_unsprited (an id outside the frozen sprite table; params v2,
  Amendment O3: also an id the ABSENT RULE excludes -- its sprite fits >= T_item on > 1 % of FIT +
  DEV's empty-floor absent points, so a fit cannot show it is there); and, fail closed,
  item_unprojected (a prediction that does not exist). Under a model / terrain box: kept
  only when (c) passes (o3h for items);
- (e) ONE class ``floor_item``; (f) a kept frame with no item label is a NEGATIVE.

ROLES, refused by the part's NAME before anything of it is read (O.6; map_labels.XMAS02's
test_suffixes, Amendment O1): the monster TEST (xw5, xp1, X2), gw3, the floor items' held-out
(round 2, O15: fiT4-fiT6, fsTa, fsTn; round 1's fiT1-fiT3 are TRAIN-eligible since O15), and
p30 (the GPU video, O.0). FIT (p31) is labelled only as ``--split val`` (VAL,
monitor only); ``--split train`` refuses it, and ``--split val`` takes nothing else. ``--eval-test``
reads fiT and nothing else, under FROZEN params and only once a frozen MODEL exists (its weights
re-hashed against ``--model-sha256``; map_labels' ``--eval-test`` asks FROZEN params the same way).

G2 (O.6's join rule, gef10 round 3 4.3's form): the median |dx|, |dy| of a session's CLEAR views'
colour fits at the anchored prediction <= 3 px on >= 30 fits. A clear view: an item ON the floor
(phase on), wholly clear of the UI, >= 30 px inside the frame and from every UI window, clear of
our self box + 4 px, our bar, every unit box (tw, tw - 0.5 s), every other item on the floor and
every model / terrain box; every fit counts (the study's 184 FIT / 52 DEV fits, O.4). ``label``
records each item's ``g2_clear`` and the session's summary; ``g2`` reads label files.

T2-items (O.5): strata N (within 1 cell of our cell: the runner's case), F (2+ cells, clear of
every model box), M (2+ cells, under a model / terrain box, kept by the fit) -- a partition, N
first -- and E (10 plain absent points by O.1e's rule + 10 HARD ones: the absent points with the
highest colour fit on TRAIN frames); <= 3 crops per floor item; seed 61, salt ``xmas02-fi``; one
seeded order, the strata's sizes not in the pack. ``reference.png`` (the distinct floor sprites of
the map's drop tables, native size x3 on the floor's orange and pale tiles, no names) is generated
at pack time; the instructions are the committed file, pinned by sha256. The evaluation's pack
(O.9, ``--eval-test``, seed 63): every kept fiT label up to 60 (<= 3 a floor item) + 20 E crops.

OFFLINE ONLY (ADR-0007: packets are ground truth for labels, never an agent input): packets, the
recorder's PNG tar shards (read-only, NAS), the client's item sprites and resname table and the
map's RSW / GAT in /dev/shm (client-derived, never committed), the local KB's drop tables
(rAthena-derived, never committed). No GPU, no client, no input. Item NAMES are never written.
"""

from __future__ import annotations

import argparse
import bisect
import dataclasses
import hashlib
import json
import math
import random
import statistics
import sys
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import numpy.typing as npt

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import gef10_items as gi  # noqa: E402
import item_labels as il  # noqa: E402
import lab_env  # noqa: E402
import label_check  # noqa: E402
import map_labels as ml  # noqa: E402
import orc_camera_check as occ  # noqa: E402
import orc_labels_fix as olf  # noqa: E402
import qa_export  # noqa: E402
import rec_paths  # noqa: E402

from poring_dataset.render import (  # noqa: E402
    Actor,
    SpritePrediction,
    SpriteSheet,
    anchor_and_depth,
    predict_sprite,
)
from poring_dataset.sprites import compose_frame, parse_act, parse_spr  # noqa: E402

Box = tuple[float, float, float, float]
NS = 1_000_000_000
RULE = "xmas02-fi-1"
# T-I1: the 1080 spec's rule -- (a)-(f) as RULE, its own frozen constants -- under its own name, so
# a params or label file names its screen's rule (build_frame_cache.item_spec matches the name)
RULE_1080 = "xmas02-fi-1-1080"
CLASS_NAME = "floor_item"
FI = Path("/dev/shm/poring-lab-tmp/xmas-fi")  # client-derived inputs and outputs: RAM (rule 7)
NAS = lab_env.store_dir()  # the storage folder (LAB_STORE_DIR)
LAYOUT_TEMPLATES = Path.home() / "docker" / "poring-lab" / "data" / "ui_anchors" / "layout"
INSTRUCTIONS = ROOT / "docs" / "planning" / "xmas02-item-blind-instructions.txt"
INSTRUCTIONS_SHA256 = "cff8ee8b7e738c13357c680072f9ce39762b652403a86a15ef462ff50e5fcdf5"
G2_BAR_PX = 3.0  # O.6: the join rule's median |dx|, |dy|
G2_MIN_FITS = 30  # ... on >= 30 fits
MARGIN_PX = 30.0  # a clear view lies >= 30 px inside the frame and from every UI window
PACK_N = {"N": 15, "F": 15, "M": 10}  # O.5's item strata
PACK_E_PLAIN, PACK_E_HARD = 10, 10  # O.5's E: plain + hard absent points
EVAL_ITEMS, EVAL_E = 60, 20  # O.9: every kept label up to 60 + 20 E crops
# Amendment O15 (round 2, `pack --round 2`): T2-r2 on the NEW TRAIN labels, seed 65, 40 item crops
# with the N stratum (within 1 cell of her) first; the evaluation's pack, seed 66, up to 70 AURA
# item crops (fiT4-fiT6 + fsTa) and 50 NO-AURA ones (fsTn), each + its E crops as round 1
R2_PACK_SEED, R2_EVAL_SEED = 65, 66
R2_PACK_ITEMS = 40
R2_EVAL_SIZES = {"aura": 70, "no_aura": 50}
R2_NOAURA = ("-rdp-xmas02-fsTn",)  # fi_eval.R2_NOAURA (a test pins the two equal)
# Amendment O17 (round 3, `pack --round 3 --eval-test`): seed 67, the same sizes, its no-aura name
R3_EVAL_SEED = 67
R3_NOAURA = ("-rdp-xmas02-fsTn3",)  # fi_eval.R3_NOAURA
R4_EVAL_SEED = 68  # O20 (round 4, `pack --round 4 --eval-test`)
R4_NOAURA = ("-rdp-xmas02-fsTn4",)  # fi_eval.R4_NOAURA
# O26 (round 5, `pack --round 5 --eval-test`): seed 69; round 2's two size slots carry the NATURAL
# drops (fiH1 + fiH2, the first slot, <= 70) and the STAGING (fsH1, the second slot, <= 50) --
# round 5 is aura-off throughout (O22), so the slot names mean natural / staging here
R5_EVAL_SEED = 69
R5_STAGING = ("-rdp-xmas02-fsH1",)  # the second slot (fi_eval.R5_AURA_OFF's staging)
# xmas02-items-1080.md (round 6, the 1080 item round; T-I4): round 5's evaluation pack, the first
# slot the natural drops (ifH1 + ifH2, <= 70), the second the staging (ifsH1, <= 50); its seed from
# the CLI (the plan names none; the parent's amendment records it before the pack is drawn)
R6_STAGING = ("-xmas02-ifsH1", "-xmas02-ifsH2")  # fi_eval.R6_STAGING (a test pins them equal)
# xmas02-items-1080.md Amendment 22 (round 7, pre-registered 2026-11-21 16:11): a NEW 1080 held-out
# (fi_eval.R7_*; a test pins them equal) packed as round 6 (the first slot the natural drops, the
# second the stagings), at the plan's own seed 74
R7_PILOTS = ("-xmas02-ifH5", "-xmas02-ifH6", "-xmas02-ifH7", "-xmas02-ifH8", "-xmas02-ifH9",
             "-xmas02-ifH10")  # fmt: skip
R7_STAGING = ("-xmas02-ifsH3", "-xmas02-ifsH4")
R7_HELD_OUT = (*R7_PILOTS, *R7_STAGING)
R7_EVAL_SEED = 74
# xmas02-items-1080.md Amendment 26 (round 8, pre-registered 2026-11-22 03:2x): a NEW 1080 held-out
# (fi_eval.R8_*; a test pins them equal). Its names are reserved now, the one extension's too
# (ifH11 .. ifH20), so each is refused for TRAIN before its first recording.
R8_PILOTS = tuple(f"-xmas02-ifH{k}" for k in range(11, 21))
R8_STAGING = ("-xmas02-ifsH5", "-xmas02-ifsH6")
R8_HELD_OUT = (*R8_PILOTS, *R8_STAGING)
R8_EVAL_SEED = 75
# xmas02-items-1080.md Amendment 32 (round 9, pre-registered 2026-11-22): xmas02fi8 unchanged + the
# fi7 rule with its floor at 0.40, scored on a NEW 1080 held-out (fi_eval.R9_*; a test pins them
# equal). Its names are reserved now, the one extension's too (ifH21 .. ifH30).
R9_PILOTS = tuple(f"-xmas02-ifH{k}" for k in range(21, 31))
R9_STAGING = ("-xmas02-ifsH7", "-xmas02-ifsH8")
R9_HELD_OUT = (*R9_PILOTS, *R9_STAGING)
R9_EVAL_SEED = 76
# xmas02-items-1080.md Amendment 36 (round 10, pre-registered 2026-11-22): xmas02fi8 + the fi7 rule
# at 0.40 + the view edge, scored on a NEW 1080 held-out (fi_eval.R10_*; a test pins them equal).
# Its names are reserved now, the one extension's too (ifH31 .. ifH40).
R10_PILOTS = tuple(f"-xmas02-ifH{k}" for k in range(31, 41))
R10_STAGING = ("-xmas02-ifsH9", "-xmas02-ifsH10")
R10_HELD_OUT = (*R10_PILOTS, *R10_STAGING)
R10_EVAL_SEED = 77
# Amendment 38 (2026-11-23): I2 was short (18 < 20), so round 10 takes Amendment 16's ONE extension,
# ifH37 .. ifH39 (ifH40 reserved). A pack that holds any of them is the extension's: seed 78 (the
# seed-77 pack and key are set aside, never shown).
R10_EXT_PILOTS = tuple(f"-xmas02-ifH{k}" for k in range(37, 41))
R10_EXT_SEED = 78


def r10_seed(names: Sequence[str]) -> int:
    """PURE (Amendment 38): round 10's pack seed for these sessions (ids, or label file stems):
    the extension's 78 when any is ifH37 .. ifH40, else Amendment 36's 77."""
    ext = any(str(n).endswith(x) for n in names for x in R10_EXT_PILOTS)
    return R10_EXT_SEED if ext else R10_EVAL_SEED
# every round `pack` packs (the CLI's --round choices; round 9's code first missed it, 11-22)
PACK_ROUNDS = (1, 2, 3, 4, 5, 6, 7, 8, 9, 10)
# Amendment 26: rounds 6 and 7's held-outs are SPENT (each scored once: 8a 11-21 14:59, round 7
# 11-22 03:17) and RELEASED for TRAIN from round 8; --eval-test still reads them (old scores stay
# reproducible). Matched like every name (the id ENDS with it): "-xmas02-ifH1" is not "-ifH11".
IF_RELEASED = (*(f"-xmas02-ifH{k}" for k in range(1, 11)),
               *(f"-xmas02-ifsH{k}" for k in range(1, 5)))  # fmt: skip
PER_FLOOR_ITEM = 3  # O.5 / O.9: at most 3 crops per floor item
HARD_POOL = 200  # absent points fitted to find the hard ones (one per TRAIN frame, seeded)
NEG_DX, NEG_DY = 7, 5  # O.1e (fi_study.py): an absent point within +-7 x +-5 cells of ours ...
NEG_ITEM_CHEB, NEG_UNIT_CHEB = 3, 2  # ... > 3 cells from a floor item, > 2 from a unit ...
NEG_ITEM_SPAN_NS = 3 * NS  # ... alive within +-3 s of the frame
NEG_TRIES = 40
SUBS = (3, 6, 9, 12)
# the floor's colours behind reference.png's sprites: the median RGB of the orange and the pale
# floor pixels in the 33 x 33 windows around 12 of O.1e's absent points on FIT p31 (measured
# 2026-11-10 11:1x ICT: 8,795 orange and 88 pale pixels)
TILE_ORANGE = (202, 125, 86)
TILE_PALE = (224, 202, 172)
# --- xmas02-items-1080.md (T-I1, T-I2): the 1080 round ------------------------------------------
FI_1080 = Path("/dev/shm/poring-lab-tmp/i1080")  # the 1080 item round's RAM folder (Amendment 1)
X1080_MONSTER = Path("/dev/shm/poring-lab-tmp/x1080/fit/params-1080.json")  # 1080 monster, FROZEN
X1080_MONSTER_SHA256 = "9c73278f8c1aca1fb315673e3ee350db904407349b7655b14dee4d47c8de0331"
# the recorder names a session <stamp>-<backend>-xmas02-<label> (20261120T214246-rdp-xmas02-ifF);
# no backend in the suffixes, so a name is refused whatever path recorded it
IF_FIT = ("-xmas02-ifF",)  # section 4: FIT / VAL, the absent controls; never TRAIN
# section 4 + Amendment 16 (the one extension: ifH3, ifH4, ifsH2) + Amendment 22 (round 7's new
# held-out): refused for TRAIN by NAME
IF_HELD_OUT = (
    "-xmas02-ifH1",
    "-xmas02-ifH2",
    "-xmas02-ifsH1",
    "-xmas02-ifH3",
    "-xmas02-ifH4",
    "-xmas02-ifsH2",
    *R7_HELD_OUT,
    *R8_HELD_OUT,
    *R9_HELD_OUT,
    *R10_HELD_OUT,
)
FIT_SCALES_1080 = tuple(round(0.85 + 0.05 * k, 2) for k in range(7))  # 0.85 .. 1.15 (T-I2)
FIT_R_1080 = gi.R_MEASURE  # the anchor's search around the UNANCHORED prediction (gef10 8's +-10)
T_GRID = tuple(round(0.05 * k, 2) for k in range(1, 21))  # 0.05 .. 1.00 (O.3 (c)'s 0.05 grid)
T_ITEM_MAX_RATE = 0.005  # O.3 (c): the smallest T whose FIT absent-control pass rate <= 0.5 %
ABSENT_POINTS_1080 = 400  # absent points on FIT (one a kept frame; O.1e's rule, absent_points)
ABSENT_MIN_POINTS = 200  # a 0.5 % rate is resolved only with >= 200 points (one pass in 200)
BAR_CHECK_WINDOW = (-39.0, 2.0, 36.0, 26.0)  # the 720 FIT bar + 8 px: where the check looks
BAR_CHECK_MIN_PX = 20  # a frame's bar-coloured pixels for its bar to count as read


@dataclass(frozen=True)
class FiSpec:
    """One map's floor-item rule (xmas_dun02's: Amendment O at 720, xmas02-items-1080.md at 1080).
    A spec whose pixel constants (``anchor_px`` ... ``bar``) are None reads them from its frozen
    params file only (the 1080 spec: freeze-1080)."""

    name: str
    mspec: ml.MapSpec
    rule: str
    val_suffixes: tuple[str, ...]  # FIT -> VAL (monitor only)
    refused_suffixes: tuple[str, ...]  # refused by NAME beside the map's monster TEST
    eval_suffixes: tuple[str, ...]  # the held-out, read only by --eval-test
    monster_params: Path  # the frozen monster params: the 1d offset and k
    monster_params_sha256: str
    sprites: Path  # the decoded item SPR / ACT files
    resnames: Path  # idnum2itemresnametable.txt
    params: Path  # O.3 (g)
    anchor_px: tuple[float, float] | None
    scale: float | None
    r_label: int | None
    t_item: float | None
    bar: Box | None
    d_appear_s: float
    d_gone_s: float
    stack_iou: float
    pack_seed: int
    eval_seed: int | None
    salt: str
    plan: str
    # params v2 (Amendment O3): the absent rule's sessions (FIT, DEV) and its output file
    absent_suffixes: tuple[str, ...] = ()
    # a SPENT held-out (scored once) a later round releases for TRAIN; --eval-test still reads it
    released_suffixes: tuple[str, ...] = ()
    params_v2: Path | None = None
    # the species whose drop tables name the floor items (drop_ids); empty: the monster MapSpec's
    drop_species: tuple[int, ...] = ()
    # T-I1: the screen the spec labels (rec_paths' lab-720 / virtual-1080 path), the virtual
    # picture's world scale, its RAM folder (packs), and the names role_refusal's reasons cite
    screen: str = "720"
    world_scale: float = 1.0
    work: Path = FI
    heldout_note: str = "fiT, Amendment O1"
    fit_note: str = "p31"
    refused_note: str = "O.0: p30 is the GPU video recording"


XMAS02_FI = FiSpec(
    name="xmas_dun02",
    mspec=ml.XMAS02,
    rule=RULE,
    val_suffixes=("-rdp-hunt-xmas02-p31",),
    refused_suffixes=("-rdp-s3-xmas02-p30",),
    eval_suffixes=ml.XMAS02_FIT,
    monster_params=ml.XD / "fit" / "params.json",
    monster_params_sha256="d4cc0a5d9e530e382e31ea9c9ae1fc1087dd31c37577b43b307eff65994fdb6e",
    sprites=FI / "items" / "data" / "sprite" / "아이템",
    resnames=FI / "grf" / "data" / "idnum2itemresnametable.txt",
    params=FI / "params.json",
    anchor_px=(-4.0, 2.0),
    scale=1.0,
    r_label=10,
    t_item=0.65,
    bar=(-31.0, 10.0, 28.0, 18.0),
    d_appear_s=2.2,
    d_gone_s=0.6,
    stack_iou=0.5,
    pack_seed=61,
    eval_seed=63,
    salt="xmas02-fi",
    plan="docs/planning/xmas02-detector.md Amendment O / O1",
    absent_suffixes=("-rdp-hunt-xmas02-p31", "-rdp-hunt-xmas02-p38"),
    params_v2=FI / "params-v2.json",
    # O.3 (g)'s species, pinned: xmas02-detector.md Amendment S (2026-11-12) put Stormy Knight
    # (1251) in the monster MapSpec's species; its drops join the floor items only by an item
    # amendment of their own
    drop_species=(1249, 1248, 1265, 1246, 1515, 1607),
)  # fmt: skip
# T-I1 (xmas02-items-1080.md 3): the same rule (RULE_1080) on the virtual 1280 x 720 picture of
# the 1920 x 1080 fullscreen client. Its pixel constants are None here: they are FITTED on ifF
# (fit-1080) and read from items-params-1080.json (freeze-1080) only. The times (2.2 / 0.6 s), the
# stack IoU, the sprites and the species are the rule's, not pixels: the 720 values
XMAS02_FI_1080 = FiSpec(
    name="xmas_dun02",
    mspec=ml.XMAS02,
    rule=RULE_1080,
    val_suffixes=IF_FIT,
    refused_suffixes=(),
    eval_suffixes=IF_HELD_OUT,
    released_suffixes=IF_RELEASED,  # Amendment 26
    monster_params=X1080_MONSTER,
    monster_params_sha256=X1080_MONSTER_SHA256,
    sprites=XMAS02_FI.sprites,
    resnames=XMAS02_FI.resnames,
    params=FI_1080 / "items-params-1080.json",
    anchor_px=None,
    scale=None,
    r_label=None,
    t_item=None,
    bar=None,
    d_appear_s=XMAS02_FI.d_appear_s,
    d_gone_s=XMAS02_FI.d_gone_s,
    stack_iou=XMAS02_FI.stack_iou,
    pack_seed=71,  # section 6: T2 on the 1080 TRAIN labels, seed 71
    eval_seed=None,  # round 6's evaluation pack takes its seed from the CLI (T-I4)
    salt=XMAS02_FI.salt,  # round 5's method: only the seed differs
    plan="docs/planning/xmas02-items-1080.md (T-I1, T-I2)",
    absent_suffixes=IF_FIT,
    params_v2=None,
    drop_species=XMAS02_FI.drop_species,
    screen="1080",
    world_scale=1.5,  # rec_paths.VIEW_1080's (a test pins the two equal)
    work=FI_1080,
    heldout_note=(
        "round 10's ifH31-ifH40, ifsH9, ifsH10 (Amendment 36); round 9's ifH21-ifH30, ifsH7, "
        "ifsH8 (Amendment 32); round 8's ifH11-ifH20, ifsH5, "
        "ifsH6 (Amendment 26); rounds 6-7's ifH1-ifH10 and ifsH1-ifsH4 are spent and released "
        "for TRAIN, xmas02-items-1080.md"
    ),
    fit_note="ifF",
    refused_note="",
)
# every registered floor-item rule (build_frame_cache's item_specs reads the values, item_spec
# matches a params file's rule NAME: xmas02-fi-1 at 720, xmas02-fi-1-1080 at 1080; both params
# record their monster_params_sha256 too, d4cc0a5d... / 9c73278f...). The "xmas_dun02" key
# stays the 720 rule (freeze, freeze-v2); --map takes the MAP names (MAP_NAMES)
FI_MAPS = {"xmas_dun02": XMAS02_FI, "xmas_dun02@1080": XMAS02_FI_1080}
MAP_NAMES = sorted({s.name for s in FI_MAPS.values()})
# every spec by (map, screen); a params file names its spec by its "screen" (spec_for_params)
FI_SPECS = {("xmas_dun02", "720"): XMAS02_FI, ("xmas_dun02", "1080"): XMAS02_FI_1080}
SCREENS = ("720", "1080")  # --spec


def spec_of(a: argparse.Namespace) -> FiSpec:
    """The spec a command names: ``--map`` and ``--spec`` (720 when the command has no --spec)."""
    return FI_SPECS[(a.map, str(getattr(a, "spec", None) or "720"))]


def spec_for_params(doc: Mapping[str, Any]) -> FiSpec:
    """The spec a params file was frozen for: its map and its ``screen`` (none: the 720 files)."""
    key = (str(doc.get("map")), str(doc.get("screen", "720")))
    if key not in FI_SPECS:
        raise SystemExit(f"map {key[0]!r} at {key[1]} has no floor-item rule")
    return FI_SPECS[key]


# --- pure parts --------------------------------------------------------------------------------


def role_refusal(spec: FiSpec, sid: str, split: str | None, eval_test: bool) -> str | None:
    """PURE (O.6): why the session NAMED ``sid`` may not be labelled in this role, else None.
    ``split`` train / val (None with ``eval_test``). Checked on the directory's name BEFORE anything
    is read, and again on the manifest's session id."""

    def on(xs: Sequence[str]) -> bool:
        return any(sid.endswith(x) for x in xs)

    if eval_test:
        if on(spec.eval_suffixes):
            return None
        names = ", ".join(spec.eval_suffixes)
        return f"--eval-test reads the held-out only (a name ending in {names})"
    if on(spec.eval_suffixes) and not on(spec.released_suffixes):
        return f"the floor items' held-out ({spec.heldout_note}): --eval-test only"
    if spec.mspec.is_test(sid, None):
        return "shares frames with the map's TEST (3b; gw3, Amendment M)"
    if on(spec.refused_suffixes):
        return f"not usable ({spec.refused_note})"
    if split == "val" and not on(spec.val_suffixes):
        return f"--split val is FIT only ({', '.join(spec.val_suffixes)}; O.6)"
    if split == "train" and on(spec.val_suffixes):
        return f"FIT ({spec.fit_note}) is VAL only (O.6): --split val"
    if split not in ("train", "val"):
        return f"--split {split}: train or val"
    return None


def foreign_refusal(spec: FiSpec, sid: str) -> str | None:
    """PURE (T-I1): a name ANOTHER spec of the map holds back as its held-out is never read under
    ``spec`` (the label pass checks it by NAME before anything is read). role_refusal stays one
    spec's roles; the frame cache asks every rule of the map (build_frame_cache's
    train_role_refusals)."""
    for other in FI_SPECS.values():
        if other is not spec and other.name == spec.name and \
                any(sid.endswith(x) for x in other.eval_suffixes):  # fmt: skip
            return f"the {other.screen} floor items' held-out: --eval-test under its own spec only"
    return None


def screen_refusal(spec: FiSpec, manifest: Mapping[str, Any]) -> str | None:
    """PURE (T-I1): why an OPENED recording may not be labelled under ``spec``: the 720 spec labels
    the lab's 720 path only, the 1080 spec the virtual 1080 path at its world scale (rec_paths);
    a constant fitted on one screen never labels the other's pixels."""
    path = rec_paths.path_of(manifest)
    want = "lab-720" if spec.screen == "720" else "virtual-1080"
    if path != want:
        return f"a {path or 'refused'} recording: the {spec.screen} spec labels {want} only"
    if want == "virtual-1080":
        ws = float((manifest.get("client_view") or {}).get("world_scale", 0.0))
        if abs(ws - spec.world_scale) > 1e-6:
            return f"world scale {ws}, not the {spec.screen} spec's {spec.world_scale}"
    return None


def at_scale(p: SpritePrediction, s: float) -> SpritePrediction:
    """PURE (O.1b): the prediction drawn at the FIXED scale ``s`` about its anchor (items are
    not billboard-scaled)."""
    a, b = p.anchor_px, p.box
    k = s / p.scale
    box = (a[0] + (b[0] - a[0]) * k, a[1] + (b[1] - a[1]) * k,
           a[0] + (b[2] - a[0]) * k, a[1] + (b[3] - a[1]) * k)  # fmt: skip
    return dataclasses.replace(p, scale=s, box=box, mask=None, mask_origin=None)


def cheb(a: Sequence[float], b: Sequence[float]) -> float:
    return max(abs(float(a[0]) - float(b[0])), abs(float(a[1]) - float(b[1])))


def self_box_of(prm: Mapping[str, Any], me: tuple[float, float]) -> Box:
    """Our self box at our anchor ``me``. A params file of another screen (its ``screen`` key: the
    1080 one) carries its own (w, h, pad); a 720 file has no ``screen`` and keeps gef10_items' box
    (labels v2's 34 x 74 + 4 px) exactly as before."""
    if "screen" not in prm:
        return gi.self_box(me)
    sb = prm["self_box"]
    w, h, pad = float(sb["w"]), float(sb["h"]), float(sb["pad"])
    return (me[0] - w / 2 - pad, me[1] - h - pad, me[0] + w / 2 + pad, me[1] + pad)


def margin_of(prm: Mapping[str, Any]) -> float:
    """The clear-view margin: the params' (another screen's) or MARGIN_PX (a 720 file)."""
    return MARGIN_PX if "screen" not in prm else float(prm["g2"]["margin_px"])


def bar_1080(bar: Sequence[float], world_scale: float, about: str) -> list[float]:
    """PURE (T-I2): the 720 FIT bar (x0, y0, x1, y1 from her foot point) at native size in the
    virtual frame: its size / world_scale, scaled about her FOOT POINT ("feet": its offset from her
    feet native too) or about its own CENTRE ("centre": its place below her feet keeps the
    world's scale, only its size is native)."""
    s = float(world_scale)
    if about == "feet":
        return [round(float(v) / s, 4) for v in bar]
    if about == "centre":
        cx, cy = (bar[0] + bar[2]) / 2, (bar[1] + bar[3]) / 2
        hw, hh = (bar[2] - bar[0]) / 2 / s, (bar[3] - bar[1]) / 2 / s
        return [round(cx - hw, 4), round(cy - hh, 4), round(cx + hw, 4), round(cy + hh, 4)]
    raise SystemExit(f"bar scaled about {about!r}: feet or centre")


# T-I2's bar rule as the parent gave it: native-size, / 1.5 about her foot point. NOTE (a smoke
# of this tool, 2026-11-20 ~22:2x ICT, scratch, NOT a fit: bar_check on 60 frames of the 1080
# MONSTER FIT v1f, 20261120T083735): the bar-coloured pixels lay at (-20.8, 11.1, 19.2, 17.1)
# from her feet, the size / 1.5 at the 720 place; 15.2 % of them inside the "feet" box, 98.6 %
# inside the "centre" box (the reader on 720 fiT19: (-30.75, 10.11, 29.25, 19.11) against the
# measured (-31, 10, 28, 18), 83.4 % inside). Which one is frozen is the plan's decision;
# fit-1080's bar_check reports both on ifF.
# ➡️ 2026-11-20 (the plan's rule, "measured on the 1080 virtual frames"; xmas02-items-1080.md
# Amendment 3): "centre" -- the measured place (98.6 % inside on v1f; the "feet" guess 15.2 %).
# freeze-1080 must see it again on ifF (>= 95 % inside), else no freeze.
BAR_ABOUT_1080 = "centre"
BAR_INSIDE_MIN = 0.95


def constants_1080(world_scale: float, about: str = BAR_ABOUT_1080) -> dict[str, Any]:
    """PURE (T-I2): the 1080 pixel constants that are SET BY RULE, not fitted. The virtual 1280 x
    720 picture resamples the 1920 x 1080 client's world by 1 / world_scale about the centre
    (fullscreen-client.md; rec_paths); a thing drawn at NATIVE size inside the world shrinks with
    it, a world-size thing keeps its 720 size:
    - the bar (our small HP / SP bar under her) is native-size: the 720 FIT bar / world_scale,
      about her foot point (``about`` "feet": its offset from her feet is native pixels too) or
      about its own centre ("centre"; bar_1080, BAR_ABOUT_1080);
    - the self box (her body) is world-size: labels v2's 34 x 74 + 4 px, unchanged;
    - r_label and the clear-view margin bound the item sprite's window, and the item sprites are
      world-size (drawn in the world at a fixed scale, O.1b): unchanged;
    - the unit box (a unit's body) is world-size: unchanged (recorded, as in the 720 params).
    The anchor, the sprite scale and T_item are FITTED (fit-1080)."""
    s = float(world_scale)
    bar, r = XMAS02_FI.bar, XMAS02_FI.r_label
    assert bar is not None and r is not None
    return {
        "world_scale": s,
        "bar_px": bar_1080(bar, s, about),
        "bar_about": about,
        "bar_px_by_about": {k: bar_1080(bar, s, k) for k in ("feet", "centre")},
        "bar_720_px": list(bar),
        "self_box": {"w": gi.SELF_W, "h": gi.SELF_H, "pad": gi.SELF_PAD},
        "r_label": int(r),
        "margin_px": MARGIN_PX,
        "unit_box": list(gi.UNIT_BOX),
        "rule": {
            "bar_px": f"native-size: the 720 FIT bar (-31, +10, +28, +18), its size / "
                      f"world_scale, about {'her foot point' if about == 'feet' else 'its centre'}",
            "self_box": "world-size (her body): the 720 box",
            "r_label": "world-size (the item sprite's search): the 720 value",
            "margin_px": "world-size (the item sprite's window): the 720 value",
            "unit_box": "world-size (a unit's body): the 720 box",
        },
    }  # fmt: skip


def frame_reasons(
    preds: Mapping[int, Box], phases: Sequence[str], me: tuple[float, float],
    units: Sequence[tuple[float, float]], size: tuple[int, int],
    rects: Sequence[tuple[int, int, int, int]], bar: Box, stack_iou: float,
    selfb: Box | None = None,
) -> tuple[list[str], list[int]]:  # fmt: skip
    """PURE (O.3 (d), before the fit): the frame's exclusion reasons and the floor ids to fit.
    ``preds``: floor id -> the ANCHORED box of every item ON the floor; ``phases``: every nearby
    item's phase; ``rects``: UI windows (x, y, w, h). Wholly behind the UI or off the region: not
    drawn, no label. ``selfb``: our self box (self_box_of; None: gef10_items' at ``me``)."""
    sb = gi.self_box(me) if selfb is None else selfb
    why: list[str] = []
    if "settling" in phases:
        why.append("item_settling")
    if "vanishing" in phases:
        why.append("item_vanishing")
    xyxy = [(float(x), float(y), float(x + w), float(y + h)) for x, y, w, h in rects]
    vis: list[int] = []
    for fid, b in preds.items():
        st = il.ui_status(b, xyxy, size)
        if st == "hidden":
            continue
        if st != "clear":
            why.append(st)
            continue
        vis.append(fid)
    if il.stacked([preds[f] for f in vis], stack_iou):
        why.append("stacked")
    for fid in vis:
        b = preds[fid]
        if gi.overlaps(b, sb):
            why.append("under_self")
        if gi.overlaps(b, gi.at(me, bar)):
            why.append("under_bar")
        if any(gi.overlaps(b, gi.at(u, gi.UNIT_BOX)) for u in units):
            why.append("under_unit")
    return list(dict.fromkeys(why)), vis


def g2_clear(box: Box, me: tuple[float, float], units: Sequence[tuple[float, float]],
             others: Sequence[Box], size: tuple[int, int],
             rects: Sequence[tuple[int, int, int, int]], bar: Box,
             under: str | None, selfb: Box | None = None,
             margin: float = MARGIN_PX) -> bool:  # fmt: skip
    """PURE (O.4 / O.6): the view is a CLEAR one for G2 (the module docstring). ``selfb`` and
    ``margin``: the params' (self_box_of, margin_of); the defaults are the 720 values."""
    sb = gi.self_box(me) if selfb is None else selfb
    if gi.overlaps(box, sb) or gi.overlaps(box, gi.at(me, bar)):
        return False
    if any(gi.overlaps(box, gi.at(u, gi.UNIT_BOX)) for u in units):
        return False
    if any(gi.overlaps(box, o) for o in others):
        return False
    return gi.inside(box, size, rects, margin) and under is None


def g2_summary(fits: Sequence[Mapping[str, Any]], bar: float = G2_BAR_PX,
               min_fits: int = G2_MIN_FITS) -> dict[str, Any]:  # fmt: skip
    """PURE (O.6): the join rule's offset check on a session's clear fits (each with dx, dy):
    PASS when the median |dx| and |dy| are <= ``bar`` on >= ``min_fits`` fits; fewer fits:
    NOT_ENOUGH (not admitted); else FAIL (not admitted)."""
    n = len(fits)
    out: dict[str, Any] = {
        "n": n,
        "bar_px": bar,
        "min_fits": min_fits,
        "floor_items": len({(x.get("session"), x["floor_id"]) for x in fits}),
    }
    if n == 0:
        return {**out, "verdict": "NOT_ENOUGH"}
    mdx = statistics.median(abs(float(x["dx"])) for x in fits)
    mdy = statistics.median(abs(float(x["dy"])) for x in fits)
    out.update({"median_abs_dx": mdx, "median_abs_dy": mdy,
                "within_3px": round(sum(abs(x["dx"]) <= 3 and abs(x["dy"]) <= 3 for x in fits)
                                    / n, 3)})  # fmt: skip
    if n < min_fits:
        return {**out, "verdict": "NOT_ENOUGH"}
    return {**out, "verdict": "PASS" if mdx <= bar and mdy <= bar else "FAIL"}


def g2_rows(frames: Sequence[Mapping[str, Any]], session: str = "") -> list[dict[str, Any]]:
    """PURE: the clear fits of a label file's frames (any status: G2 reads every fitted view)."""
    return [{"session": session, "frame_id": f["frame_id"], "floor_id": it["floor_id"],
             "dx": it["dx"], "dy": it["dy"], "ncc": it["ncc"]}
            for f in frames for it in f.get("items", []) if it.get("g2_clear")]  # fmt: skip


def count_labels(frames: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """PURE (O.4's table): kept frames with >= 1 item label, the labels, the floor items, by id,
    the frame exclusions (a frame may carry several), the negatives."""
    with_near = [f for f in frames if f.get("n_near")]
    kept = [f for f in frames if f["status"] == "keep" and f["items"]]
    labels = [it for f in kept for it in f["items"]]
    rel: Counter[str] = Counter()
    for it in labels:
        r = it.get("rel")
        d = None if r is None else cheb(r, (0, 0))
        rel["within_1" if d is not None and d <= 1 else "2_5" if d is not None and d <= 5
            else "farther"] += 1  # fmt: skip
    return {
        "frames": len(frames),
        "frames_with_items_near": len(with_near),
        "kept_frames_with_items": len(kept),
        "item_labels": len(labels),
        "floor_items": len({it["floor_id"] for it in labels}),
        "by_item_id": dict(Counter(str(it["item_id"]) for it in labels).most_common()),
        "by_distance": dict(rel),
        "under_model_kept": sum(1 for it in labels if it.get("under")),
        "frame_exclusions": dict(Counter(r for f in frames for r in f["reasons"]).most_common()),
        "negatives": sum(1 for f in frames if f["status"] == "keep" and not f["items"]),
        "excluded_frames": sum(1 for f in frames if f["status"] == "exclude"),
    }  # fmt: skip


def stratum_of(item: Mapping[str, Any]) -> str:
    """PURE (O.5): N within 1 cell of our cell (any cover), else M under a model / terrain box,
    else F. A label without a position (no self cell) is F or M by its cover."""
    rel = item.get("rel")
    if rel is not None and cheb(rel, (0, 0)) <= 1:
        return "N"
    return "M" if item.get("under") else "F"


def pack_short(picks: Sequence[Mapping[str, Any]], by: Mapping[str, int], eval_test: bool,
               r2: bool) -> dict[str, int]:  # fmt: skip
    """PURE: how far the pack fell short of its sizes (round 1 per N / F / M or X; O15's round 2
    per its total (T2-r2) or per aura / no-aura (the evaluation))."""
    if not r2:
        sizes = {"X": EVAL_ITEMS} if eval_test else PACK_N
        return {k: n - by.get(k, 0) for k, n in sizes.items() if by.get(k, 0) < n}
    if not eval_test:
        return {"items": R2_PACK_ITEMS - len(picks)} if len(picks) < R2_PACK_ITEMS else {}
    got = Counter("aura" if p.get("aura") else "no_aura" for p in picks)
    return {k: n - got[k] for k, n in R2_EVAL_SIZES.items() if got[k] < n}


def round_refusal(spec: FiSpec, rnd: int, eval_test: bool) -> str | None:
    """PURE (T-I4): rounds 1-5 are the 720 spec's (as they were); rounds 6-10 are the 1080
    rounds' evaluations; the 1080 spec packs T2 (round 1's strata, its seed 71), round 6-10."""
    if spec.screen == "720":
        return f"--round {rnd} is a 1080 round: --spec 1080" if rnd in (6, 7, 8, 9, 10) else None
    if rnd in (2, 3, 4, 5):
        return f"--round {rnd} is a 720 round: not under the {spec.screen} spec"
    if rnd == 1 and eval_test:
        return f"the {spec.screen} spec's evaluation pack is --round 6, 7, 8, 9 or 10"
    return None


def seed_source(rnd: int, r2: bool, eval_test: bool) -> str:
    """PURE: where a pack's pre-registered seed is written."""
    if rnd in (7, 8, 9, 10):
        return {7: "Amendment 22", 8: "Amendment 26", 9: "Amendment 32", 10: "Amendment 36"}[rnd]
    return "O15" if r2 else "O.9" if eval_test else "O.5"


def round_docs_refusal(rnd: int, docs: Sequence[Mapping[str, Any]]) -> str | None:
    """PURE (Amendments 22, 26, 32): rounds 7, 8 and 9's packs read their own held-out only (by
    NAME; fail closed); other rounds: None."""
    own = {7: R7_HELD_OUT, 8: R8_HELD_OUT, 9: R9_HELD_OUT, 10: R10_HELD_OUT}.get(rnd)
    if own is None:
        return None
    for d in docs:
        sid = str(d.get("session"))
        if not any(sid.endswith(x) for x in own):
            return f"{sid}: not round {rnd}'s held-out ({', '.join(own)})"
    return None


def r2_picks(cands: Sequence[Mapping[str, Any]], eval_test: bool, seed: int, salt: str,
             noaura: Sequence[str] = R2_NOAURA) -> list[dict[str, Any]]:  # fmt: skip
    """PURE (O15, round 2): T2-r2 = R2_PACK_ITEMS item crops, the N stratum first, then F, then M
    for what N lacks; the evaluation = R2_EVAL_SIZES per aura / no-aura (by session NAME), each
    crop's N / F / M stratum kept and its ``aura`` recorded. <= 3 crops per floor item."""
    if not eval_test:  # N first: one draw in the order N, F, M (the per-item cap shared)
        sizes = {"N": R2_PACK_ITEMS, "F": R2_PACK_ITEMS, "M": R2_PACK_ITEMS}
        return draw_strata(cands, sizes, seed, salt)[:R2_PACK_ITEMS]

    def aura(c: Mapping[str, Any]) -> str:
        return "no_aura" if any(str(c["session"]).endswith(x) for x in noaura) else "aura"

    picks = draw_strata([{**c, "stratum": aura(c)} for c in cands], R2_EVAL_SIZES, seed, salt)
    for p in picks:
        p["aura"] = p["stratum"] == "aura"
        p["stratum"] = stratum_of(p)
    return picks


def draw_strata(cands: Sequence[Mapping[str, Any]], sizes: Mapping[str, int], seed: int,
                salt: str, per_floor: int = PER_FLOOR_ITEM) -> list[dict[str, Any]]:  # fmt: skip
    """PURE (O.5): per stratum (in ``sizes``' order) its first ``sizes[s]`` candidates in a
    seeded order (sorted by session, frame, floor id; ``random.Random(f"{salt}:{seed}:{s}")``),
    at most ``per_floor`` crops per (session, floor id) over the whole pack."""
    per: Counter[tuple[str, int]] = Counter()
    out: list[dict[str, Any]] = []
    for s, n in sizes.items():
        pool = sorted(
            (c for c in cands if c["stratum"] == s),
            key=lambda c: (c["session"], int(c["frame_id"]), int(c["floor_id"])),
        )
        random.Random(f"{salt}:{seed}:{s}").shuffle(pool)
        k = 0
        for c in pool:
            if k >= n:
                break
            key = (str(c["session"]), int(c["floor_id"]))
            if per[key] >= per_floor:
                continue
            per[key] += 1
            out.append(dict(c))
            k += 1
    return out


def hard_pick(points: Sequence[Mapping[str, Any]], n: int) -> list[dict[str, Any]]:
    """PURE (O.5's HARD negatives): the ``n`` absent points with the highest colour fit, one per
    frame (ties: session, frame)."""
    order = sorted(
        (p for p in points if p.get("ncc") is not None),
        key=lambda p: (-float(p["ncc"]), p["session"], int(p["frame_id"])),
    )
    out, seen = [], set()
    for p in order:
        key = (p["session"], int(p["frame_id"]))
        if key in seen:
            continue
        seen.add(key)
        out.append(dict(p))
        if len(out) >= n:
            break
    return out


def absent_cell(me_cell: tuple[float, float], items: Sequence[tuple[float, float]],
                units: Sequence[tuple[float, float]], rng: random.Random
                ) -> tuple[int, int] | None:  # fmt: skip
    """PURE (O.1e, fi_study.py's controls): a cell within +-7 x +-5 of ours, not ours or next to
    it, > 3 cells (Chebyshev) from every floor item alive within +-3 s and > 2 from every unit;
    None after NEG_TRIES tries."""
    for _ in range(NEG_TRIES):
        c = (int(round(me_cell[0])) + rng.randint(-NEG_DX, NEG_DX),
             int(round(me_cell[1])) + rng.randint(-NEG_DY, NEG_DY))  # fmt: skip
        if cheb(c, me_cell) <= 1 or any(cheb(c, x) <= NEG_ITEM_CHEB for x in items):
            continue
        if any(cheb(c, u) <= NEG_UNIT_CHEB for u in units):
            continue
        return c
    return None


def cell_box(scene: Any, cell: tuple[float, float], half: float) -> Box:
    """The pixel bbox of the projected square of +-``half`` cells around ``cell`` (corners and
    edge midpoints, the GAT altitude): a cell neighbourhood on screen."""
    pts = [anchor_and_depth(scene, (cell[0] + dx * half, cell[1] + dy * half))[0]
           for dx in (-1, 0, 1) for dy in (-1, 0, 1)]  # fmt: skip
    us, vs = [p[0] for p in pts], [p[1] for p in pts]
    return (round(min(us), 1), round(min(vs), 1), round(max(us), 1), round(max(vs), 1))


def kill_rows(deaths: Sequence[Mapping[str, Any]], floors: Sequence[il.Floor],
              before_s: float = 1.5, after_s: float = 1.0, cells: float = 2.5
              ) -> list[dict[str, Any]]:  # fmt: skip
    """PURE (O.1a, the study's pk_stats.py): each of OUR kills (``deaths``: t, gid, job, cell)
    with its drops: the ``fall`` floor items appearing from ``before_s`` before to ``after_s``
    after the death within ``cells`` cells (Chebyshev) of the death cell."""
    out = []
    for d in deaths:
        t, cell = int(d["t"]), d.get("cell")
        drops = [f.floor_id for f in floors if cell is not None and f.kind == "fall"
                 and -before_s <= (f.t_a - t) / NS <= after_s
                 and cheb((f.x, f.y), cell) <= cells]  # fmt: skip
        out.append({"t": t, "gid": d["gid"], "job": d.get("job"), "cell": cell,
                    "drops": drops})  # fmt: skip
    return out


# --- the colour fit (O.1e / O.3 (c); the study's fi_refit.py) ----------------------------------


def rendered_rgb(sheet: SpriteSheet, p: SpritePrediction, window: tuple[int, int, int, int]
                 ) -> tuple[npt.NDArray[np.float64], npt.NDArray[np.bool_]]:  # fmt: skip
    """The sprite's frame (action ``p.action_index``, frame 0) drawn at ``p``'s anchor and scale
    over the pixel window (i0, j0, i1, j1): its RGB and its opaque pixels (nearest canvas pixel of
    each screen pixel centre)."""
    i0, j0, i1, j1 = window
    rgba, (ox, oy) = compose_frame(sheet.spr, sheet.act, p.action_index, 0)  # type: ignore[arg-type]
    rgb = np.zeros((j1 - j0, i1 - i0, 3))
    op = np.zeros((j1 - j0, i1 - i0), bool)
    cx = np.floor((np.arange(i0, i1) + 0.5 - p.anchor_px[0]) / p.scale + ox).astype(np.int64)
    cy = np.floor((np.arange(j0, j1) + 0.5 - p.anchor_px[1]) / p.scale + oy).astype(np.int64)
    okx = (cx >= 0) & (cx < rgba.shape[1])
    oky = (cy >= 0) & (cy < rgba.shape[0])
    sub = rgba[np.ix_(cy[oky], cx[okx])]
    rgb[np.ix_(oky, okx)] = sub[..., :3]
    op[np.ix_(oky, okx)] = sub[..., 3] > 0
    return rgb, op


def _corr_terms(obs: npt.NDArray[np.float64], valid: npt.NDArray[np.bool_],
                tpl: npt.NDArray[np.float64], mask: npt.NDArray[np.bool_],
                r: int) -> list[npt.NDArray[np.float64]]:  # fmt: skip
    shape = obs.shape
    m = mask.astype(float)
    v = valid.astype(float)
    o = np.where(valid, obs, 0.0)
    f_v, f_o, f_oo = np.fft.rfft2(v), np.fft.rfft2(o), np.fft.rfft2(o * o)

    def corr(k: npt.NDArray[np.float64], f: Any) -> npt.NDArray[np.float64]:
        kk = np.fft.rfft2(k, s=shape)
        return np.fft.irfft2(f * np.conj(kk), s=shape)[: 2 * r + 1, : 2 * r + 1]

    tm = tpl * m
    return [np.round(corr(m, f_v)), corr(tm, f_v), corr(tm * tpl, f_v), corr(m, f_o),
            corr(m, f_oo), corr(tm, f_o)]  # fmt: skip


def ncc_grid(chans_obs: Sequence[npt.NDArray[np.float64]], valid: npt.NDArray[np.bool_],
             chans_tpl: Sequence[npt.NDArray[np.float64]], mask: npt.NDArray[np.bool_],
             r: int) -> npt.NDArray[np.float64]:  # fmt: skip
    """The joint zero-mean masked NCC over the channels (3 = colour as one vector) at every
    offset in +-r (row = dy + r, column = dx + r); NaN where < MIN_PIXELS per channel score."""
    tot: list[npt.NDArray[np.float64]] | None = None
    for o, t in zip(chans_obs, chans_tpl, strict=True):
        terms = _corr_terms(o, valid, t, mask, r)
        tot = terms if tot is None else [a + b for a, b in zip(tot, terms, strict=True)]
    assert tot is not None
    n, st, stt, so, soo, sto = tot
    out = np.full(n.shape, np.nan)
    ok = n >= label_check.MIN_PIXELS * len(chans_obs)
    with np.errstate(divide="ignore", invalid="ignore"):
        cov = sto - st * so / n
        vt = stt - st * st / n
        vo = soo - so * so / n
        good = ok & (vt > 1e-9 * np.maximum(stt, 1.0)) & (vo > 1e-9 * np.maximum(soo, 1.0))
        out[good] = cov[good] / np.sqrt(vt[good] * vo[good])
    return out


def colour_fit(bgr: npt.NDArray[np.uint8], valid_full: npt.NDArray[np.bool_],
               sheet: SpriteSheet, p: SpritePrediction,
               r: int) -> tuple[float, int, int] | None:  # fmt: skip
    """(NCC, dx, dy): the best masked COLOUR NCC of the sprite drawn at ``p`` within +-``r`` px,
    on the frame's valid (non-UI) pixels; None when nothing scores (off the frame)."""
    i0, j0 = math.floor(p.box[0]), math.floor(p.box[1])
    i1, j1 = math.ceil(p.box[2]), math.ceil(p.box[3])
    rgb_t, op = rendered_rgb(sheet, p, (i0, j0, i1, j1))
    h, w = bgr.shape[:2]
    wi0, wj0, wi1, wj1 = i0 - r, j0 - r, i1 + r, j1 + r
    shp = (wj1 - wj0, wi1 - wi0)
    ci0, cj0, ci1, cj1 = max(0, wi0), max(0, wj0), min(w, wi1), min(h, wj1)
    if ci1 <= ci0 or cj1 <= cj0:
        return None
    ok = np.zeros(shp, bool)
    ok[cj0 - wj0 : cj1 - wj0, ci0 - wi0 : ci1 - wi0] = valid_full[cj0:cj1, ci0:ci1]
    rgb = bgr[cj0:cj1, ci0:ci1, 2::-1].astype(float)
    obs = []
    for c in range(3):
        z = np.zeros(shp)
        z[cj0 - wj0 : cj1 - wj0, ci0 - wi0 : ci1 - wi0] = rgb[..., c]
        obs.append(z)
    grid = ncc_grid(obs, ok, [rgb_t[..., c] for c in range(3)], op, r)
    if np.isnan(grid).all():
        return None
    a_, b_ = np.unravel_index(int(np.nanargmax(grid)), grid.shape)
    return round(float(grid[a_, b_]), 4), int(b_) - r, int(a_) - r


# --- the client's item sprites, the frozen params ------------------------------------------------


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def drop_ids(spec: FiSpec, drops: Path | None = None) -> list[int]:
    """The map's floor items: every item id in its species' drop tables (the local KB's
    drops.json, rAthena-derived, never committed); the species are ``drop_species`` when the spec
    pins them (xmas_dun02: O.3 (g)'s six), else the monster MapSpec's."""
    d = json.loads((drops or ROOT / "data" / "kb" / "drops.json").read_text())
    species = spec.drop_species or spec.mspec.species
    return sorted({int(x["item_id"]) for s in species for x in (d.get(str(s)) or [])})


def sprite_table(ids: Iterable[int], sprites: Path, resnames: Path) -> dict[str, Any]:
    """Item id -> its resname and the sha256 of its ACT / SPR (None when missing)."""
    names = gi.parse_resnames(resnames.read_bytes())
    out: dict[str, Any] = {}
    for i in sorted(set(ids)):
        n = names.get(i)
        act, spr = (sprites / f"{n}.act", sprites / f"{n}.spr") if n else (None, None)
        if n is None or act is None or spr is None or not act.exists() or not spr.exists():
            out[str(i)] = None
            continue
        out[str(i)] = {"resname": n, "act_sha256": sha256_bytes(act.read_bytes()),
                       "spr_sha256": sha256_bytes(spr.read_bytes())}  # fmt: skip
    return out


class FrozenSheets:
    """Item id -> its SpriteSheet, ONLY for the ids of the frozen table and only when the files'
    sha256 still match it (checked once, at load: a changed sprite refuses the run). ``excluded``
    (params v2, Amendment O3): ids treated as ``item_unsprited`` -- never labelled (``__call__``
    and ``sheets`` leave them out), though their sprite is still drawn where a box is only
    predicted (``any``: the evaluation's floor targets, G2's other items) and on reference.png
    (``all``)."""

    def __init__(self, table: Mapping[str, Any], sprites: Path,
                 excluded: Iterable[int] = ()) -> None:  # fmt: skip
        self.all: dict[int, SpriteSheet] = {}
        for k, v in table.items():
            if v is None:
                continue
            act = (sprites / f"{v['resname']}.act").read_bytes()
            spr = (sprites / f"{v['resname']}.spr").read_bytes()
            if sha256_bytes(act) != v["act_sha256"] or sha256_bytes(spr) != v["spr_sha256"]:
                raise SystemExit(f"item {k}: its sprite files differ from the frozen params")
            self.all[int(k)] = SpriteSheet(parse_act(act), parse_spr(spr))
        self.excluded = frozenset(int(i) for i in excluded)
        self.sheets = {k: v for k, v in self.all.items() if k not in self.excluded}

    def __call__(self, item_id: int) -> SpriteSheet | None:
        return self.sheets.get(int(item_id))

    def any(self, item_id: int) -> SpriteSheet | None:
        return self.all.get(int(item_id))


def frozen_sheets(prm: Mapping[str, Any]) -> FrozenSheets:
    """The params' sprites (v2: without the ids its absent rule excluded)."""
    return FrozenSheets(prm["items"], Path(prm["sprites_dir"]), prm.get("items_excluded", ()))


def monster_check(spec: FiSpec, monster: Mapping[str, Any], monster_sha: str) -> None:
    """PURE: refuses unless ``monster`` is the spec's FROZEN monster params (the 1d offset)."""
    if monster_sha != spec.monster_params_sha256 or monster.get("status") != "FROZEN":
        raise SystemExit(
            f"{spec.monster_params}: not the frozen monster params "
            f"({spec.monster_params_sha256[:8]}...): the 1d offset comes from it"
        )


def freeze_params(spec: FiSpec, table: Mapping[str, Any], monster: Mapping[str, Any],
                  monster_sha: str, provenance: Mapping[str, Any]) -> dict[str, Any]:  # fmt: skip
    """PURE (O.3 (g)): the frozen params document (O-D2's values, O1)."""
    monster_check(spec, monster, monster_sha)
    if spec.anchor_px is None or spec.scale is None or spec.bar is None:
        raise SystemExit(f"{spec.name} at {spec.screen}: its constants are fitted (freeze-1080)")
    return {
        "rule": spec.rule, "status": "FROZEN", "map": spec.name, "plan": spec.plan,
        "accepted_by": "Amendment O1 (2026-11-10 10:29 ICT): O-D2, frozen when T-O1 first "
                       "writes this file",
        "class": CLASS_NAME, "anchor_px": list(spec.anchor_px), "scale": spec.scale,
        "fit": "masked colour NCC (the 3 channels as one vector), the best offset",
        "r_label": spec.r_label, "t_item": spec.t_item, "bar_px": list(spec.bar),
        "self_box": {"w": gi.SELF_W, "h": gi.SELF_H, "pad": gi.SELF_PAD},
        "unit_box": list(gi.UNIT_BOX), "unit_back_s": gi.UNIT_BACK_NS / NS,
        "stack_iou": spec.stack_iou, "d_appear_s": spec.d_appear_s, "d_gone_s": spec.d_gone_s,
        "sub_table": {"OX": gi.OX, "OY": gi.OY}, "offset_ms": float(monster["offset_ms"]),
        "k": olf.K, "min_pixels": label_check.MIN_PIXELS,
        "monster_params": str(spec.monster_params), "monster_params_sha256": monster_sha,
        "g2": {"bar_px": G2_BAR_PX, "min_fits": G2_MIN_FITS, "margin_px": MARGIN_PX},
        "items": dict(table),
        "items_unsprited": sorted(int(k) for k, v in table.items() if v is None),
        **provenance,
    }  # fmt: skip


ABSENT_POINTS = 60  # O3 (params v2): the absent points drawn on FIT + DEV's kept frames ...
ABSENT_SEED = "per-sprite"  # ... in this seeded order (O2's per-sprite check, reproduced)
ABSENT_MAX_RATE = 0.01  # an id whose sprite fits >= T_item on MORE than 1 % of them is excluded


def absent_groups(table: Mapping[str, Any]) -> dict[int, list[int]]:
    """PURE: each distinct sprite (ACT + SPR sha256) -> its ids, keyed by its smallest id."""
    groups: dict[tuple[str, str], list[int]] = {}
    for k, v in sorted(table.items(), key=lambda kv: int(kv[0])):
        if v is not None:
            groups.setdefault((v["act_sha256"], v["spr_sha256"]), []).append(int(k))
    return {ids[0]: ids for ids in groups.values()}


def absent_rule(fits: Mapping[int, Sequence[float]], groups: Mapping[int, Sequence[int]],
                t_item: float, max_rate: float = ABSENT_MAX_RATE
                ) -> tuple[list[int], dict[str, Any]]:  # fmt: skip
    """PURE (Amendment O3, params v2): per sprite (its representative id -> the colour fits at
    the empty-floor absent points) the share of fits >= ``t_item``; every id of a sprite whose
    share is > ``max_rate`` is EXCLUDED (treated as item_unsprited). A sprite with no fit is
    kept (nothing measured). Returns the excluded ids and the per-sprite rows."""
    excluded: list[int] = []
    rows: dict[str, Any] = {}
    for rep_id, ids in sorted(groups.items()):
        v = [float(x) for x in fits.get(rep_id, [])]
        n, k = len(v), sum(x >= t_item for x in v)
        rate = k / n if n else 0.0
        out = n > 0 and rate > max_rate
        rows[str(rep_id)] = {
            "ids": list(ids),
            "n": n,
            "pass": k,
            "rate": round(rate, 4),
            "max": round(max(v), 4) if v else None,
            "excluded": out,
        }
        if out:
            excluded += list(ids)
    return sorted(excluded), rows


def load_params(path: Path, spec: FiSpec) -> dict[str, Any]:
    d: dict[str, Any] = json.loads(path.read_text())
    if d.get("rule") != spec.rule or d.get("map") != spec.name:
        raise SystemExit(f"{path}: not {spec.rule} params of {spec.name}")
    if d.get("status") != "FROZEN":
        raise SystemExit(f"{path}: {d.get('status')}: FROZEN params only")
    if str(d.get("screen", "720")) != spec.screen:  # T-I1: a 720 file has no "screen"
        raise SystemExit(f"{path}: {d.get('screen', '720')} params, not the {spec.screen} spec's")
    return d


# --- the label pass (forked workers read olf._JOB) ----------------------------------------------


def _units(sess: ml.RecSession, world: Any, scene: Any, tw: int) -> list[tuple[float, float]]:
    out = []
    for when in (tw, tw - gi.UNIT_BACK_NS):
        fw = world if when == tw else sess.lab.timeline.frame_world(when)
        for e in fw.entities:
            if e.objtype in occ.UNIT_OBJTYPES and not e.hidden:
                out.append(anchor_and_depth(scene, (e.x, e.y))[0])
    return out


def _predict(sheet: SpriteSheet, cell: tuple[float, float], scene: Any,
             prm: Mapping[str, Any]) -> SpritePrediction | None:  # fmt: skip
    p = predict_sprite(Actor(cell, 0, 0), sheet, scene, olf.K)
    if p is None:
        return None
    return gi.anchored(at_scale(p, float(prm["scale"])), prm["anchor_px"])


def _label_frame(ref: qa_export.JpegRef,
                 bgr: npt.NDArray[np.uint8] | None = None) -> dict[str, Any]:  # fmt: skip
    """One candidate frame under the rule (``bgr``: the frame already read, else read here)."""
    J = olf._JOB
    sess: ml.RecSession = J["sess"]
    floors: list[il.Floor] = J["floors"]
    sheets: FrozenSheets = J["sheets"]
    occl: olf.Occluders = J["occluders"]
    prm: dict[str, Any] = J["params"]
    eval_test: bool = J["eval_test"]
    d_a, d_g = int(float(prm["d_appear_s"]) * NS), int(float(prm["d_gone_s"]) * NS)
    t = ref.t_mono_ns
    base: dict[str, Any] = {"frame_id": ref.frame_id, "t": t, "shard": ref.shard.name,
                            "offset": ref.offset, "size": ref.size}  # fmt: skip
    tw = t - int(float(prm["offset_ms"]) * 1e6)
    world = sess.lab.timeline.frame_world(tw)
    scene = sess.scene(world)
    if scene is None:
        return {**base, "status": "exclude", "reasons": ["no_scene"], "items": [], "n_near": None}
    if bgr is None:
        bgr = ml.read_png(ref)
    if not sess.layout_ok(bgr):
        return {**base, "status": "exclude", "reasons": ["ui_layout_mismatch"], "items": [],
                "n_near": None}  # fmt: skip
    me = anchor_and_depth(scene, scene.player)[0]
    sp = world.self_pos
    near = [(f, ph) for f in floors if (ph := il.phase(f, t, d_a, d_g)) != "none"]
    base.update({"me": [round(me[0], 1), round(me[1], 1)], "n_near": len(near),
                 "self_cell": None if sp is None else [float(sp[0]), float(sp[1])]})  # fmt: skip
    if eval_test:
        base["around_box"] = cell_box(scene, scene.player, 2.5)
    if not near:
        if eval_test:
            base["floor"] = []
        return {**base, "status": "keep", "reasons": [], "items": []}
    units = _units(sess, world, scene, tw)
    reasons: list[str] = []
    preds: dict[int, tuple[il.Floor, SpriteSheet, SpritePrediction, tuple[float, float]]] = {}
    present: dict[int, Box] = {}  # every item on the floor (on or settling): G2's other items
    floor_rows = []
    unsprited: list[int] = []
    for f, ph in near:
        cell = il.item_cell(f, gi.OX, gi.OY)
        sheet = sheets(f.item_id)  # None: unsprited, or excluded by v2's absent rule (O3)
        draw = sheets.any(f.item_id)  # its sprite even when excluded: a predicted box only
        p = None if draw is None else _predict(draw, cell, scene, prm)
        if eval_test:
            floor_rows.append({"floor_id": f.floor_id, "item_id": f.item_id, "phase": ph,
                               "pred_box": None if p is None else [round(x, 1) for x in p.box],
                               "near_box": cell_box(scene, cell, 1.5)})  # fmt: skip
        if p is not None and ph in ("on", "settling"):
            present[f.floor_id] = p.box
        if ph == "on" and sheet is None:
            reasons.append("item_unsprited")
            unsprited.append(f.item_id)
            continue
        if ph == "on" and p is None:
            reasons.append("item_unprojected")
            continue
        if ph == "on" and p is not None and sheet is not None:
            preds[f.floor_id] = (f, sheet, p, cell)
    if eval_test:
        base["floor"] = floor_rows
    size, rects = sess.lab.size, sess.lab.ui_rects
    selfb, margin = self_box_of(prm, me), margin_of(prm)
    why, vis = frame_reasons({k: v[2].box for k, v in preds.items()}, [ph for _f, ph in near], me,
                             units, size, rects, tuple(prm["bar_px"]),
                             float(prm["stack_iou"]), selfb)  # fmt: skip
    reasons += why
    valid = olf.valid_map(size, rects)
    r, t_item = int(prm["r_label"]), float(prm["t_item"])
    items = []
    for fid in vis:
        f, sheet, p, cell = preds[fid]
        fr = colour_fit(bgr, valid, sheet, p, r)
        if fr is None:
            reasons.append("edge_partial")
            continue
        ncc, dx, dy = fr
        unfit = ncc < t_item or olf.at_edge(dx, dy, r)
        b = p.box
        under = occl.under(scene, b, cell)
        others = [x for k, x in present.items() if k != fid]
        items.append({
            "floor_id": f.floor_id, "item_id": f.item_id, "kind": f.kind,
            "box": [round(b[0] + dx, 1), round(b[1] + dy, 1), round(b[2] + dx, 1),
                    round(b[3] + dy, 1)],
            "pred_box": [round(x, 1) for x in b], "ncc": ncc, "dx": dx, "dy": dy,
            "unfit": unfit, "under": under,
            "rel": None if sp is None else [round(f.x - sp[0], 1), round(f.y - sp[1], 1)],
            "age_s": round((t - f.t_a) / NS, 2),
            "g2_clear": g2_clear(b, me, units, others, size, rects, tuple(prm["bar_px"]), under,
                                 selfb, margin),
        })  # fmt: skip
        if unfit:
            reasons.append("item_unfit")
    reasons = list(dict.fromkeys(reasons))
    if unsprited:  # which ids made it item_unsprited (v2: the absent rule's, O3)
        base["unsprited_ids"] = sorted(set(unsprited))
    return {**base, "status": "exclude" if reasons else "keep", "reasons": reasons,
            "items": items}  # fmt: skip


def our_deaths(sess: ml.RecSession) -> tuple[int | None, list[dict[str, Any]]]:
    """Our character's id and the deaths of the units it hit (the study's pk_stats.py: an
    ``entity_vanish`` reason 1 of a gid with our ``act`` of damage > 0), each with its cell 50 ms
    before (Timeline)."""
    tl = sess.lab.timeline
    evs = tl.events
    aid = tl.frame_world(sess.refs[-1].t_mono_ns).aid if sess.refs else None
    ours = {e.get("target_gid") for e in evs
            if e.get("type") == "act" and aid is not None and e.get("src_gid") == aid
            and (e.get("damage") or 0) > 0}  # fmt: skip
    out = []
    for e in evs:
        if e.get("type") != "entity_vanish" or e.get("reason") != 1 or e.get("gid") not in ours:
            continue
        td = int(e["t_mono_ns"])
        ent = [x for x in tl.frame_world(td - 50_000_000).entities if x.gid == e["gid"]]
        out.append({"t": td, "gid": e["gid"], "job": ent[0].job if ent else None,
                    "cell": [ent[0].x, ent[0].y] if ent else None})  # fmt: skip
    return aid, out


def kills_for_eval(
    sess: ml.RecSession, floors: Sequence[il.Floor], prm: Mapping[str, Any]
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Our kills with their drops (kill_rows), the death cell relative to us, and for I4 the first
    recorded frame 2.0-3.0 s after the death with the death cell's 3 x 3 on screen (None when the
    frame has no scene)."""
    aid, deaths = our_deaths(sess)
    rows = kill_rows(deaths, floors)
    off = int(float(prm["offset_ms"]) * 1e6)
    tl = sess.lab.timeline
    times = [x.t_mono_ns for x in sess.refs]
    for k in rows:
        me = tl.frame_world(int(k["t"])).self_pos
        k["rel"] = (
            None
            if me is None or k["cell"] is None
            else [round(k["cell"][0] - me[0], 1), round(k["cell"][1] - me[1], 1)]
        )
        k["i4"] = None
        i = bisect.bisect_left(times, int(k["t"]) + 2 * NS)
        if i < len(times) and times[i] < int(k["t"]) + 3 * NS and k["cell"] is not None:
            ref = sess.refs[i]
            scene = sess.scene(tl.frame_world(ref.t_mono_ns - off))
            k["i4"] = {
                "frame_id": ref.frame_id,
                "t": ref.t_mono_ns,
                "shard": ref.shard.name,
                "offset": ref.offset,
                "size": ref.size,
                "box3": None if scene is None else cell_box(scene, tuple(k["cell"]), 1.5),
            }
    return rows, {"aid": aid, "kills": len(rows),
                  "with_drop": sum(1 for k in rows if k["drops"])}  # fmt: skip


def cmd_freeze(a: argparse.Namespace) -> dict[str, Any]:
    spec = FI_MAPS[a.map]
    out: Path = a.out or spec.params
    if out.exists():
        raise SystemExit(f"{out} exists: the params are frozen ONCE (O.3 (g)); a change is a new "
                         "amendment and a new file")  # fmt: skip
    if out.resolve().is_relative_to(ROOT):
        raise SystemExit(f"{out}: client-derived (sprite hashes): never inside the repo")
    mraw = spec.monster_params.read_bytes()
    ids = drop_ids(spec, a.drops)
    table = sprite_table(ids, a.sprites or spec.sprites, a.resnames or spec.resnames)
    occl = ml.occluders(spec.mspec)
    tool = Path(__file__).resolve()
    prov = {
        "drops": str(a.drops or ROOT / "data" / "kb" / "drops.json"),
        "drops_sha256": olf.sha256_file(a.drops or ROOT / "data" / "kb" / "drops.json"),
        "sprites_dir": str(a.sprites or spec.sprites),
        "resnames": str(a.resnames or spec.resnames),
        "resnames_sha256": olf.sha256_file(a.resnames or spec.resnames),
        "occluders": {"rsw_sha256": occl.provenance()["rsw_sha256"],
                      "terrain": spec.mspec.terrain},
        "tool": str(tool.relative_to(ROOT)), "tool_sha256": olf.sha256_file(tool),
        "frozen_at": olf.now_ict(), "commit": olf.git_head(),
    }  # fmt: skip
    doc = freeze_params(spec, table, json.loads(mraw), sha256_bytes(mraw), prov)
    out.parent.mkdir(parents=True, exist_ok=True)
    raw = (json.dumps(doc, indent=1, ensure_ascii=False) + "\n").encode()
    out.write_bytes(raw)
    return {"what": "O.3 (g): the frozen xmas02-fi-1 params", "out": str(out),
            "sha256": sha256_bytes(raw), "items": len(table),
            "items_unsprited": doc["items_unsprited"],
            "distinct_sprites": len({(v["act_sha256"], v["spr_sha256"]) for v in table.values()
                                     if v}), "frozen_at": prov["frozen_at"],
            "commit": prov["commit"]}  # fmt: skip


def cmd_label(a: argparse.Namespace) -> dict[str, Any]:
    spec = spec_of(a)
    split = None if a.eval_test else a.split
    path = ml.parse_part(a.part)[0]
    if ml.parse_part(a.part)[1] is not None:
        raise SystemExit(f"{a.part}: whole sessions only (no spots on {spec.name})")
    # the NAME, before anything is read (and another screen's held-out: foreign_refusal)
    why = role_refusal(spec, path.name, split, a.eval_test) or foreign_refusal(spec, path.name)
    if why is not None:
        raise SystemExit(f"{a.part}: {why}: refused")
    params_raw = a.params.read_bytes()
    prm = load_params(a.params, spec)
    model: dict[str, Any] | None = None
    if a.eval_test:  # O.9: the held-out is read only after the model is frozen
        if a.model is None or a.model_sha256 is None:
            raise SystemExit("--eval-test needs --model WEIGHTS and --model-sha256 HEX (the frozen "
                             "item model, its sha256 recorded before fiT is read)")  # fmt: skip
        if not a.model.is_file():
            raise SystemExit(f"{a.model}: no frozen model: fiT stays unread")
        got = olf.sha256_file(a.model)
        if got != a.model_sha256:
            raise SystemExit(f"{a.model}: sha256 {got}, not the frozen {a.model_sha256}")
        model = {"weights": str(a.model), "sha256": got, "bytes": a.model.stat().st_size}
    elif a.model is not None or a.model_sha256 is not None:
        raise SystemExit("--model / --model-sha256 belong to --eval-test")
    sheets = frozen_sheets(prm)
    occl = ml.occluders(spec.mspec)
    if occl.provenance()["rsw_sha256"] != prm["occluders"]["rsw_sha256"]:
        raise SystemExit("the map's RSW differs from the frozen params'")
    sess = ml.RecSession.open(a.part, spec.mspec, a.layout_templates)
    # by the manifest's id too; T-I1: and the screen it was recorded on (its manifest's path)
    why = role_refusal(spec, sess.sid, split, a.eval_test) or foreign_refusal(spec, sess.sid)
    if why is None:
        why = screen_refusal(spec, sess.lab.manifest)
    if why is not None:
        raise SystemExit(f"{sess.sid}: {why}: refused")
    refs = sess.candidates_at(float(prm["offset_ms"]))
    floors = il.floor_items(sess.lab.timeline.events)
    olf._JOB.update(sess=sess, floors=floors, sheets=sheets, occluders=occl, params=prm,
                    eval_test=bool(a.eval_test))  # fmt: skip
    frames = olf.run_parallel(_label_frame, refs, a.workers)
    out: dict[str, Any] = {
        "what": f"the {spec.rule} floor-item labels (no pixels): per candidate frame",
        "rule": spec.rule, "class": CLASS_NAME, "map": spec.name, "part": a.part,
        "session": sess.sid, "split": "eval" if a.eval_test else split,
        "eval_test": bool(a.eval_test), "params": str(a.params),
        "params_sha256": sha256_bytes(params_raw), "params_status": prm["status"],
        "labelled_at": olf.now_ict(), "commit": olf.git_head(),
        "frames_recorded": len(sess.refs), "candidates": len(refs),
        "candidate_drops": dict(sorted(sess.dropped.items())),
        "floor_items_in_packets": len(floors),
        "floor_items_by_kind": dict(Counter(f.kind for f in floors)),
        "counts": count_labels(frames),
        "g2": g2_summary(g2_rows(frames, sess.sid)),
    }  # fmt: skip
    if spec.screen != "720":  # T-I1: a 1080 label file says so (a 720 one stays as it was)
        out.update({"screen": spec.screen, "world_scale": spec.world_scale})
    if model is not None:
        out["model"] = model
        out["kills"], out["kills_summary"] = kills_for_eval(sess, floors, prm)
    out["frames"] = frames
    return out


def absent_fits(
    docs: Sequence[Mapping[str, Any]],
    spec: FiSpec,
    prm: Mapping[str, Any],
    sheets: FrozenSheets,
    layout: Path,
    n: int = ABSENT_POINTS,
    seed: str = ABSENT_SEED,
    sessions: dict[str, ml.RecSession] | None = None,
) -> tuple[list[dict[str, Any]], dict[int, list[float]]]:
    """Params v2's measurement (O3; O2's per-sprite check as a tool): ``n`` absent points of
    O.1e's rule on the docs' kept frames (absent_points, ``random.Random(seed)``), and at each
    one the colour fit (+-r_label, the params' scale and anchor) of EVERY distinct sprite of the
    table, its sub-cell drawn by ``random.Random(frame_id)`` / ``random.Random(frame_id + 1)``.
    Returns the points (their provenance and fits) and the fits per sprite (its smallest id).
    ``sessions``: sessions already open, by id (fit-1080's), else each is opened from the store."""
    sessions = {} if sessions is None else sessions
    pts = absent_points(docs, spec, prm, sheets, sessions, layout, n, random.Random(seed),
                        fit=False)  # fmt: skip
    groups = absent_groups(prm["items"])
    off = int(float(prm["offset_ms"]) * 1e6)
    r = int(prm["r_label"])
    fits: dict[int, list[float]] = {k: [] for k in groups}
    rows = []
    for pt in pts:
        sess = sessions[pt["session"]]
        bgr = ml.read_png(_ref(sess, pt))
        valid = olf.valid_map(sess.lab.size, sess.lab.ui_rects)
        scene = sess.scene(sess.lab.timeline.frame_world(int(pt["t"]) - off))
        fid = int(pt["frame_id"])
        sub = (random.Random(fid).choice(SUBS), random.Random(fid + 1).choice(SUBS))
        cell = (pt["cell"][0] + gi.OX[sub[0]], pt["cell"][1] + gi.OY[sub[1]])
        row: dict[str, Any] = {"session": pt["session"], "frame_id": fid, "t": pt["t"],
                               "cell": pt["cell"], "sub": list(sub), "fits": {}}  # fmt: skip
        for rep_id in groups:
            sh = sheets.any(rep_id)
            pr = None if sh is None or scene is None else _predict(sh, cell, scene, prm)
            fr = None if pr is None or sh is None else colour_fit(bgr, valid, sh, pr, r)
            if fr is not None:
                fits[rep_id].append(fr[0])
                row["fits"][str(rep_id)] = fr[0]
        rows.append(row)
    return rows, fits


def cmd_freeze_v2(a: argparse.Namespace) -> dict[str, Any]:
    """Params v2 (Amendment O3): v1 + the ids its absent rule excludes, frozen ONCE in a new file
    (v1 stays the record of the positive cases)."""
    spec = FI_MAPS[a.map]
    out: Path | None = a.out or spec.params_v2
    if out is None:
        raise SystemExit(f"{spec.name}: no params v2 path")
    if out.exists():
        raise SystemExit(f"{out} exists: params v2 is frozen ONCE (O3); a change is a new file")
    if out.resolve().is_relative_to(ROOT):
        raise SystemExit(f"{out}: client-derived (sprite hashes): never inside the repo")
    raw1 = a.v1.read_bytes()
    v1 = load_params(a.v1, spec)
    if v1.get("version", 1) != 1 or "items_excluded" in v1:
        raise SystemExit(f"{a.v1}: v2 is built from the v1 params")
    v1_sha = sha256_bytes(raw1)
    docs, files = [], []
    for path in a.labels:
        doc = json.loads(path.read_text())
        sid = str(doc.get("session"))
        if doc.get("rule") != spec.rule or doc.get("params_sha256") != v1_sha:
            raise SystemExit(f"{path}: not {spec.rule} labels under {a.v1}")
        if doc.get("eval_test") or role_refusal(spec, sid, doc.get("split"), False):
            raise SystemExit(f"{path}: {sid}: not a FIT / DEV label file")
        docs.append(doc)
        files.append({"file": str(path), "sha256": olf.sha256_file(path), "session": sid,
                      "split": doc["split"]})  # fmt: skip
    got = sorted(next((x for x in spec.absent_suffixes if f["session"].endswith(x)), "")
                 for f in files)  # fmt: skip
    if got != sorted(spec.absent_suffixes):
        raise SystemExit(f"--labels: one label file each of {', '.join(spec.absent_suffixes)} "
                         "(O3: the rule is fixed on FIT + DEV)")  # fmt: skip
    sheets = frozen_sheets(v1)
    rows, fits = absent_fits(docs, spec, v1, sheets, a.layout_templates)
    excluded, per = absent_rule(fits, absent_groups(v1["items"]), float(v1["t_item"]))
    tool = Path(__file__).resolve()
    doc = dict(v1)
    doc.update({
        "version": 2, "plan": f"{spec.plan} / O3",
        "accepted_by": "Amendment O3 (2026-11-10 11:30 ICT): O2 finding 7.2, a per-id rule fixed "
                       "on FIT + DEV's empty-floor absent points; frozen when this tool first "
                       "writes this file",
        "v1": str(a.v1), "v1_sha256": v1_sha, "v1_frozen_at": v1.get("frozen_at"),
        "v1_commit": v1.get("commit"),
        "absent_rule": {
            "what": "an id whose sprite fits >= t_item on MORE than max_rate of the absent points "
                    "is treated as item_unsprited (never labelled; its frames excluded)",
            "t_item": float(v1["t_item"]), "max_rate": ABSENT_MAX_RATE,
            "points_drawn": ABSENT_POINTS, "points": len(rows), "seed": ABSENT_SEED,
            "point_rule": "O.1e via fi_labels.absent_points on the label files' kept frames",
            "sub_rule": "random.Random(frame_id) / random.Random(frame_id + 1) over 3, 6, 9, 12",
            "fit": f"colour NCC +-{v1['r_label']} px, scale {v1['scale']}, anchor "
                   f"{v1['anchor_px']}", "label_files": files, "per_sprite": per,
            "point_rows": rows},
        "items_excluded": excluded,
        "frozen_at": olf.now_ict(), "commit": olf.git_head(),
        "tool": str(tool.relative_to(ROOT)), "tool_sha256": olf.sha256_file(tool),
    })  # fmt: skip
    out.parent.mkdir(parents=True, exist_ok=True)
    raw = (json.dumps(doc, indent=1, ensure_ascii=False) + "\n").encode()
    out.write_bytes(raw)
    return {"what": "O3: the frozen xmas02-fi-1 params v2", "out": str(out),
            "sha256": sha256_bytes(raw), "v1_sha256": v1_sha, "points": len(rows),
            "items_excluded": excluded,
            "excluded_rates": {k: {x: r[x] for x in ("ids", "n", "pass", "rate", "max")}
                               for k, r in per.items() if r["excluded"]},
            "kept_max_rate": max((r["rate"] for r in per.values() if not r["excluded"]),
                                 default=None),
            "frozen_at": doc["frozen_at"], "commit": doc["commit"]}  # fmt: skip


def pooled_g2(docs: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """PURE (xmas02-items-1080.md Amendment 7, 2026-11-21): the TRAIN label files whose OWN G2
    is NOT_ENOUGH (fewer than 30 clear fits: natural pilots pick their loot up in seconds) are
    judged TOGETHER -- their clear fits pooled, the same bar (median |dx|, |dy| <= 3 px on >= 30
    fits): PASS admits every one of them, FAIL or NOT_ENOUGH none. A file whose own G2 PASSes
    is admitted on its own (not pooled); one whose own G2 FAILs is never pooled. Every pooled
    file must be TRAIN at one frozen params sha (else the pool is refused)."""
    own, pooled, refused = [], [], []
    rows: list[dict[str, Any]] = []
    for doc in docs:
        g = g2_summary(g2_rows(doc["frames"], doc["session"]))
        if g["verdict"] == "PASS":
            own.append(doc["session"])
        elif g["verdict"] == "FAIL":
            refused.append(doc["session"])
        else:
            pooled.append(doc)
            rows += g2_rows(doc["frames"], doc["session"])
    shas = {d["params_sha256"] for d in pooled}
    splits = {d["split"] for d in pooled}
    out: dict[str, Any] = {"admitted_alone": own, "never_pooled": refused,
                           "pooled": [d["session"] for d in pooled]}  # fmt: skip
    if pooled and (len(shas) != 1 or splits != {"train"}):
        return {
            **out,
            "verdict": "REFUSED",
            "why": f"params {sorted(shas)}, splits {sorted(splits)}: one frozen sha, TRAIN",
        }
    summary = g2_summary(rows)
    return {**out, **summary,
            "admitted_by_pool": [d["session"] for d in pooled] if summary["verdict"] == "PASS"
            else []}  # fmt: skip


def cmd_g2(a: argparse.Namespace) -> dict[str, Any]:
    per = {}
    docs = []
    for p in a.labels:
        doc = json.loads(p.read_text())
        docs.append(doc)
        per[doc["session"]] = {"file": str(p), "split": doc["split"],
                               "params_sha256": doc["params_sha256"],
                               "floor_items_in_packets": doc["floor_items_in_packets"],
                               **g2_summary(g2_rows(doc["frames"], doc["session"]))}  # fmt: skip
    out = {"what": "O.6: the join rule's G2 per session (median |dx|, |dy| <= 3 px on >= 30 "
                   "clear fits)", "checked_at": olf.now_ict(), "commit": olf.git_head(),
           "per_session": per}  # fmt: skip
    if getattr(a, "pool", False):
        out["pooled"] = pooled_g2(docs)
    return out


# --- T-I2 (xmas02-items-1080.md 3 and 5): the 1080 constants, FITTED on ifF, then frozen ---------


def _rank(values: Sequence[float], q: float) -> float:
    """PURE: the nearest-rank percentile (q in 0..100) of a non-empty sequence."""
    s = sorted(values)
    return float(s[max(1, math.ceil(q / 100 * len(s))) - 1])


def fit_constants(per_scale: Mapping[float, Sequence[Mapping[str, Any]]],
                  min_fits: int = G2_MIN_FITS) -> dict[str, Any]:  # fmt: skip
    """PURE (T-I2): the sprite scale and the anchor from the FIT session's views at every scale of
    the grid. A row is one view of an item ON the floor (frame_id, floor_id) with its best colour
    fit (ncc, dx, dy) around the UNANCHORED prediction, ``edge`` (the fit at the search edge) and
    ``g2_clear`` (G2's clear view, at that scale's box):
    - the COMMON views are clear at every scale (one set, so the scales are compared alike);
    - per scale, the median NCC over the common views; the best scale has the highest (a tie: the
      one nearer 1.0, then the smaller);
    - the anchor is the median (dx, dy) of the best scale's clear views not at the search edge.
    NOT_ENOUGH when the common views or the anchor's fits are fewer than ``min_fits`` (G2's 30)."""
    scales = sorted(per_scale)
    clear = {s: {(int(v["frame_id"]), int(v["floor_id"])): v for v in per_scale[s]
                 if v.get("g2_clear")} for s in scales}  # fmt: skip
    common = set.intersection(*(set(c) for c in clear.values())) if scales else set()
    rows: dict[float, dict[str, Any]] = {}
    for s in scales:
        nccs = [float(clear[s][k]["ncc"]) for k in common]
        rows[s] = {"views": len(per_scale[s]), "clear": len(clear[s]),
                   "clear_at_edge": sum(1 for v in clear[s].values() if v.get("edge")),
                   "median_ncc_common": round(statistics.median(nccs), 4) if nccs
                   else None}  # fmt: skip
    out: dict[str, Any] = {"scales": {f"{s:.2f}": r for s, r in rows.items()},
                           "common_views": len(common), "min_fits": min_fits}  # fmt: skip
    ranked = [s for s in scales if rows[s]["median_ncc_common"] is not None]
    if not ranked:
        return {**out, "best_scale": None, "anchor": None, "verdict": "NOT_ENOUGH"}
    best = max(ranked, key=lambda s: (rows[s]["median_ncc_common"], -round(abs(s - 1.0), 6), -s))
    fits = [v for v in clear[best].values() if not v.get("edge")]
    anchor = None
    if fits:
        nccs = [float(v["ncc"]) for v in fits]
        anchor = {"dx": float(statistics.median(int(v["dx"]) for v in fits)),
                  "dy": float(statistics.median(int(v["dy"]) for v in fits)), "n": len(fits),
                  "floor_items": len({int(v["floor_id"]) for v in fits}),
                  "edge_left_out": rows[best]["clear_at_edge"],
                  "ncc_p5": round(_rank(nccs, 5), 4),
                  "ncc_median": round(statistics.median(nccs), 4)}  # fmt: skip
    ok = len(common) >= min_fits and anchor is not None and anchor["n"] >= min_fits
    return {**out, "best_scale": best, "anchor": anchor, "verdict": "READY" if ok else "NOT_ENOUGH"}


def view_weights(item_ids: Sequence[int], groups: Mapping[int, Sequence[int]]) -> dict[int, float]:
    """PURE (T-I2): each distinct sprite's share of FIT's clear item views (a view counts for its
    sprite's smallest id, absent_groups' key; an id of no sprite is left out)."""
    rep = {int(i): int(r) for r, ids in groups.items() for i in ids}
    c = Counter(rep[int(i)] for i in item_ids if int(i) in rep)
    n = sum(c.values())
    return {r: c[r] / n for r in sorted(c)} if n else {}


def absent_rates(fits: Mapping[int, Sequence[float]], weights: Mapping[int, float],
                 grid: Sequence[float] = T_GRID,
                 max_rate: float = T_ITEM_MAX_RATE) -> list[dict[str, Any]]:  # fmt: skip
    """PURE (T-I2): the FIT absent controls' pass rate (a fit >= T) at every T of the grid, two
    ways, both from freeze-v2's measurement (absent_fits: EVERY distinct sprite at each point):
    - ``rate_all``: over every (point, sprite) fit, pooled (reported);
    - ``rate_views``: each sprite's own rate weighted by its share of FIT's clear item views. The
      720 study's absent control (O.1e) was a view's OWN sprite at an empty point of its frame, so
      this is that control's expected rate; T_item's rule (``meets_rule``: <= ``max_rate``) reads
      it. A sprite with views but no absent fit leaves the weights (they are renormalised)."""
    allv = [float(x) for v in fits.values() for x in v]
    w = {int(r): float(x) for r, x in weights.items() if fits.get(int(r))}
    tot = sum(w.values())
    out = []
    for t in grid:
        k = sum(x >= t for x in allv)
        per = {r: sum(float(x) >= t for x in fits[r]) / len(fits[r]) for r in w}
        vw = sum(w[r] * per[r] for r in w) / tot if tot > 0 else None
        out.append({"t": t, "pass_all": k, "n_all": len(allv),
                    "rate_all": round(k / len(allv), 5) if allv else None,
                    "rate_views": None if vw is None else round(vw, 5),
                    "meets_rule": vw is not None and vw <= max_rate})  # fmt: skip
    return out


def t_item_of(rows: Sequence[Mapping[str, Any]]) -> float | None:
    """PURE (O.3 (c)'s rule): the smallest T of the grid whose absent pass rate meets the rule."""
    ok = [float(r["t"]) for r in rows if r.get("meets_rule")]
    return min(ok) if ok else None


def bar_pixels(mask: npt.NDArray[np.bool_], origin: tuple[int, int], me: tuple[float, float],
               boxes: Mapping[str, Sequence[float]]) -> dict[str, Any]:  # fmt: skip
    """PURE (T-I2's bar check): the bar-coloured pixels of a window (``origin``: its top-left in
    the frame) relative to her foot point ``me``: their count, their bbox (pixel edges) and, per
    named box (x0, y0, x1, y1 from her foot point), how many pixel centres lie inside it."""
    ys, xs = np.nonzero(mask)
    if len(xs) == 0:
        return {"n": 0, "bbox": None, "inside": {k: 0 for k in boxes}}
    px, py = xs + origin[0], ys + origin[1]
    cx, cy = px + 0.5 - me[0], py + 0.5 - me[1]
    inside = {k: int(((cx >= b[0]) & (cx <= b[2]) & (cy >= b[1]) & (cy <= b[3])).sum())
              for k, b in boxes.items()}  # fmt: skip
    return {"n": int(len(xs)), "inside": inside,
            "bbox": [round(float(px.min() - me[0]), 2), round(float(py.min() - me[1]), 2),
                     round(float(px.max() + 1 - me[0]), 2),
                     round(float(py.max() + 1 - me[1]), 2)]}  # fmt: skip


def bar_check(rows: Sequence[Mapping[str, Any] | None], boxes: Mapping[str, Sequence[float]],
              chosen: str, bar_720: Sequence[float],
              min_px: int = BAR_CHECK_MIN_PX) -> dict[str, Any]:  # fmt: skip
    """PURE (T-I2): the check of the 1080 bar on FIT's item-free frames with the repo's reader of
    her bar's colours (route_preview._bar_mask: the green HP row and the blue SP row): the median
    bbox of the bar-coloured pixels around her foot point and the share inside each candidate box
    (``boxes``: bar_1080's "feet" and "centre"; ``chosen`` the rule's, BAR_ABOUT_1080). A CHECK,
    reported: the bar is set by constants_1080's rule, not by this."""
    read = [r for r in rows if r is not None]
    got = [r for r in read if int(r["n"]) >= min_px]
    rule_box = boxes[chosen]
    out: dict[str, Any] = {
        "available": True,
        "reader": "route_preview._bar_mask (the green HP row and the blue SP row; written at 720)",
        "frames": "FIT's item-free judged frames at the fitted scale and anchor",
        "window_px": list(BAR_CHECK_WINDOW), "min_px": min_px, "frames_read": len(read),
        "frames_with_bar": len(got), "rule_about": chosen, "rule_bar_px": list(rule_box),
        "boxes_px": {k: list(b) for k, b in boxes.items()}, "bar_720_px": list(bar_720),
    }  # fmt: skip
    if not got:
        return {**out, "median_bbox_px": None, "share_inside": None,
                "median_bbox_inside_rule_box": None}  # fmt: skip
    med = [round(statistics.median(float(r["bbox"][i]) for r in got), 2) for i in range(4)]
    n = sum(int(r["n"]) for r in got)
    share = {k: round(sum(int(r["inside"][k]) for r in got) / n, 4) for k in boxes}
    inside = (rule_box[0] <= med[0] and rule_box[1] <= med[1] and med[2] <= rule_box[2]
              and med[3] <= rule_box[3])  # fmt: skip
    return {**out, "median_bbox_px": med, "share_inside": share,
            "median_bbox_inside_rule_box": inside}  # fmt: skip


def _bar_read(bgr: npt.NDArray[np.uint8], me: tuple[float, float],
              boxes: Mapping[str, Sequence[float]]) -> dict[str, Any] | None:  # fmt: skip
    import route_preview as rp  # the repo's reader of her bar's colours

    h, w = bgr.shape[:2]
    wx0, wy0, wx1, wy1 = BAR_CHECK_WINDOW
    x0, y0 = max(0, math.floor(me[0] + wx0)), max(0, math.floor(me[1] + wy0))
    x1, y1 = min(w, math.ceil(me[0] + wx1)), min(h, math.ceil(me[1] + wy1))
    if x1 <= x0 or y1 <= y0:
        return None
    return bar_pixels(rp._bar_mask(bgr[y0:y1, x0:x1]), (x0, y0), me, boxes)


def fit_base_params(spec: FiSpec, consts: Mapping[str, Any], offset_ms: float) -> dict[str, Any]:
    """PURE (T-I2): the label pass's params for fit-1080's passes: the rule's times and IoU, the
    1080 rule constants (constants_1080), the 1080 monster offset and NO NCC floor (t_item -1:
    T_item is fitted after them); the scale, the anchor and the search are set per pass."""
    return {"screen": spec.screen, "world_scale": spec.world_scale,
            "d_appear_s": spec.d_appear_s, "d_gone_s": spec.d_gone_s,
            "stack_iou": spec.stack_iou, "offset_ms": float(offset_ms),
            "bar_px": list(consts["bar_px"]), "self_box": dict(consts["self_box"]),
            "g2": {"margin_px": float(consts["margin_px"])}, "t_item": -1.0}  # fmt: skip


def _fit_frame(ref: qa_export.JpegRef) -> dict[str, Any]:
    """fit-1080's first pass (forked workers read olf._JOB): the frame read ONCE, then the label
    pass's own frame rule (_label_frame: the projection, the exclusions, the colour fit, G2's
    clear view) at every scale of the grid around the UNANCHORED prediction. A frame with no
    item near is the same at every scale (one call)."""
    J = olf._JOB
    bgr = ml.read_png(ref)
    fits: dict[str, list[dict[str, Any]]] = {}
    n_near = None
    for s, prm in J["fit_params"].items():
        J["params"] = prm
        row = _label_frame(ref, bgr)
        n_near = row.get("n_near")
        if not n_near:
            break
        r = int(prm["r_label"])
        fits[f"{s:.2f}"] = [{"floor_id": it["floor_id"], "item_id": it["item_id"],
                             "dx": it["dx"], "dy": it["dy"], "ncc": it["ncc"],
                             "edge": olf.at_edge(int(it["dx"]), int(it["dy"]), r),
                             "g2_clear": bool(it["g2_clear"])} for it in row["items"]]  # fmt: skip
    return {"frame_id": ref.frame_id, "n_near": n_near, "fits": fits}


def _fit2_frame(ref: qa_export.JpegRef) -> dict[str, Any]:
    """fit-1080's second pass: the label pass's frame rule at the FITTED scale and anchor (still
    no NCC floor), and the bar check on the item-free judged frames."""
    J = olf._JOB
    bgr = ml.read_png(ref)
    row = _label_frame(ref, bgr)
    bar = None
    if row.get("n_near") == 0 and row.get("me") is not None:
        bar = _bar_read(bgr, (float(row["me"][0]), float(row["me"][1])), J["bar_boxes"])
    return {"row": row, "bar": bar}


def cmd_fit_1080(a: argparse.Namespace) -> dict[str, Any]:
    """T-I2: the 1080 constants FITTED on the FIT session (ifF); nothing is frozen here."""
    spec = XMAS02_FI_1080
    path, spots = ml.parse_part(a.part)
    if spots is not None:
        raise SystemExit(f"{a.part}: whole sessions only")
    why = role_refusal(spec, path.name, "val", False)  # the NAME, before anything is read
    if why is not None:
        raise SystemExit(f"{a.part}: {why}: refused (fit-1080 reads the FIT session only)")
    if a.out.resolve().is_relative_to(ROOT):
        raise SystemExit(f"{a.out}: client-derived (sprite hashes): never inside the repo")
    mraw = spec.monster_params.read_bytes()
    monster = json.loads(mraw)
    monster_check(spec, monster, sha256_bytes(mraw))
    drops = a.drops or ROOT / "data" / "kb" / "drops.json"
    sprites, resnames = a.sprites or spec.sprites, a.resnames or spec.resnames
    table = sprite_table(drop_ids(spec, drops), sprites, resnames)
    sheets = FrozenSheets(table, sprites)
    occl = ml.occluders(spec.mspec)
    sess = ml.RecSession.open(a.part, spec.mspec, a.layout_templates)
    why = role_refusal(spec, sess.sid, "val", False) or screen_refusal(spec, sess.lab.manifest)
    if why is not None:
        raise SystemExit(f"{sess.sid}: {why}: refused")
    consts = constants_1080(spec.world_scale)
    offset = float(monster["offset_ms"])
    base = fit_base_params(spec, consts, offset)
    grid = {s: {**base, "scale": s, "anchor_px": [0.0, 0.0], "r_label": FIT_R_1080}
            for s in FIT_SCALES_1080}  # fmt: skip
    refs = sess.candidates_at(offset)
    floors = il.floor_items(sess.lab.timeline.events)
    olf._JOB.update(sess=sess, floors=floors, sheets=sheets, occluders=occl, params=grid[1.0],
                    eval_test=False, fit_params=grid,
                    bar_boxes=consts["bar_px_by_about"])  # fmt: skip
    p1 = olf.run_parallel(_fit_frame, refs, a.workers)
    per_scale = {s: [{**v, "frame_id": f["frame_id"]} for f in p1
                     for v in f["fits"].get(f"{s:.2f}", [])] for s in FIT_SCALES_1080}  # fmt: skip
    fc = fit_constants(per_scale)
    tool = Path(__file__).resolve()
    report: dict[str, Any] = {
        "what": "T-I2: the 1080 item constants FITTED on the FIT session (nothing frozen)",
        "kind": "fit-1080", "rule": spec.rule, "map": spec.name, "screen": spec.screen,
        "world_scale": spec.world_scale, "plan": spec.plan, "part": a.part, "session": sess.sid,
        "monster_params": str(spec.monster_params), "monster_params_sha256": sha256_bytes(mraw),
        "offset_ms": offset, "rule_constants": consts,
        "search": {"scales": list(FIT_SCALES_1080), "r_px": FIT_R_1080,
                   "around": "the UNANCHORED prediction (anchor 0, 0)"},
        "frames_recorded": len(sess.refs), "candidates": len(refs),
        "candidate_drops": dict(sorted(sess.dropped.items())),
        "floor_items_in_packets": len(floors), "fit": fc,
        "items": table, "drops": str(drops), "drops_sha256": olf.sha256_file(drops),
        "sprites_dir": str(sprites), "resnames": str(resnames),
        "resnames_sha256": olf.sha256_file(resnames),
        "occluders": {"rsw_sha256": occl.provenance()["rsw_sha256"],
                      "terrain": spec.mspec.terrain},
        "tool": str(tool.relative_to(ROOT)), "tool_sha256": olf.sha256_file(tool),
        "fitted_at": olf.now_ict(), "commit": olf.git_head(),
    }  # fmt: skip
    if fc["verdict"] != "READY":
        return {**report, "verdict": "NOT_ENOUGH", "why": ["the scale and anchor fits (fit)"]}
    # the pass's params, with the sprite table as a params file holds it (absent_fits reads it)
    prm2 = {**base, "scale": float(fc["best_scale"]), "r_label": int(consts["r_label"]),
            "anchor_px": [float(fc["anchor"]["dx"]), float(fc["anchor"]["dy"])],
            "items": table}  # fmt: skip
    olf._JOB["params"] = prm2
    p2 = olf.run_parallel(_fit2_frame, refs, a.workers)
    frames = [x["row"] for x in p2]
    doc = {"session": sess.sid, "split": "val", "frames": frames}
    points, fits = absent_fits([doc], spec, prm2, sheets, a.layout_templates, n=a.absent_points,
                               seed=ABSENT_SEED, sessions={sess.sid: sess})  # fmt: skip
    groups = absent_groups(table)
    weights = view_weights([int(it["item_id"]) for f in frames for it in f["items"]
                            if it.get("g2_clear")], groups)  # fmt: skip
    rates = absent_rates(fits, weights)
    t_item = t_item_of(rates)
    excluded, per = absent_rule(fits, groups, t_item) if t_item is not None else ([], {})
    why_not = []
    if t_item is None:
        why_not.append("no T on the grid meets the absent rule")
    if len(points) < ABSENT_MIN_POINTS:
        why_not.append(f"{len(points)} absent points < {ABSENT_MIN_POINTS}")
    report.update({
        "provisional_params": {k: v for k, v in prm2.items() if k != "items"},
        "at_fit": {"counts": count_labels(frames), "g2": g2_summary(g2_rows(frames, sess.sid)),
                   "note": "the label rule at the fitted scale and anchor, no NCC floor: G2 here "
                           "previews T1 (T1 is the label pass under the frozen params)"},
        "absent": {"points": len(points), "points_drawn": a.absent_points,
                   "min_points": ABSENT_MIN_POINTS, "seed": ABSENT_SEED,
                   "point_rule": "O.1e via fi_labels.absent_points on the kept frames at the "
                                 "fitted scale and anchor (no NCC floor)",
                   "sub_rule": "random.Random(frame_id) / random.Random(frame_id + 1) over 3, 6, "
                               "9, 12",
                   "fit": f"colour NCC +-{prm2['r_label']} px, scale {prm2['scale']}, anchor "
                          f"{prm2['anchor_px']}",
                   "view_weights": {str(k): round(v, 4) for k, v in weights.items()},
                   "t_grid": rates, "t_item_rule": "the smallest T of the 0.05 grid whose FIT "
                   "absent-control pass rate (rate_views) is <= 0.5 % (O.3 (c))",
                   "t_item": t_item, "max_rate": ABSENT_MAX_RATE, "per_sprite": per,
                   "items_excluded": excluded,
                   "kept_max_rate": max((r["rate"] for r in per.values() if not r["excluded"]),
                                        default=None)},
        "bar_check": bar_check([x["bar"] for x in p2], consts["bar_px_by_about"],
                               consts["bar_about"], consts["bar_720_px"]),
        "verdict": "NOT_ENOUGH" if why_not else "READY", "why": why_not,
    })  # fmt: skip
    return report


def freeze_1080_params(spec: FiSpec, report: Mapping[str, Any], report_sha: str,
                       monster: Mapping[str, Any], monster_sha: str,
                       provenance: Mapping[str, Any]) -> dict[str, Any]:  # fmt: skip
    """PURE (T-I2): items-params-1080.json from a READY fit-1080 report of the FIT session: the
    v2 schema (the absent rule's exclusions) with the fitted anchor, scale and T_item, the rule's
    constants (constants_1080, re-derived and compared), the monster params' and the report's
    sha256. Refuses a report of another kind, screen, session or monster params, or not READY."""
    monster_check(spec, monster, monster_sha)
    if report.get("kind") != "fit-1080" or str(report.get("screen")) != spec.screen:
        raise SystemExit(f"not a fit-1080 report of the {spec.screen} spec")
    sid = str(report.get("session"))
    why = role_refusal(spec, sid, "val", False)
    if why is not None:
        raise SystemExit(f"{sid}: {why}: not a report of the FIT session")
    if report.get("monster_params_sha256") != monster_sha or report.get("rule") != spec.rule:
        raise SystemExit("the report was fitted under other monster params or another rule")
    if report.get("verdict") != "READY":
        raise SystemExit(f"the fit report says {report.get('verdict')}: nothing to freeze")
    consts = constants_1080(spec.world_scale)
    if report.get("rule_constants") != consts:
        raise SystemExit("the report's rule constants are not this tool's (constants_1080)")
    # Amendment 3: the frozen bar box must hold the bar on the FIT session too (>= 95 % inside)
    share = ((report.get("bar_check") or {}).get("share_inside") or {}).get(BAR_ABOUT_1080)
    if not isinstance(share, (int, float)) or share < BAR_INSIDE_MIN:
        raise SystemExit(
            f"the bar check on the FIT session: {share!r} of the bar inside the "
            f"{BAR_ABOUT_1080!r} box, under {BAR_INSIDE_MIN}: nothing to freeze"
        )
    fc, ab = report["fit"], report["absent"]
    return {
        "rule": spec.rule, "status": "FROZEN", "map": spec.name, "screen": spec.screen,
        "world_scale": spec.world_scale, "plan": spec.plan,
        "accepted_by": "xmas02-items-1080.md 3 (T-I2) and 5: fitted on the FIT session by "
                       "fit-1080; frozen when freeze-1080 first writes this file (its sha256 is "
                       "recorded before any TRAIN label)",
        "class": CLASS_NAME,
        "anchor_px": [float(fc["anchor"]["dx"]), float(fc["anchor"]["dy"])],
        "scale": float(fc["best_scale"]),
        "fit": "masked colour NCC (the 3 channels as one vector), the best offset",
        "r_label": int(consts["r_label"]), "t_item": float(ab["t_item"]),
        "bar_px": list(consts["bar_px"]), "bar_720_px": list(consts["bar_720_px"]),
        "self_box": dict(consts["self_box"]), "unit_box": list(consts["unit_box"]),
        "unit_back_s": gi.UNIT_BACK_NS / NS, "constants_rule": dict(consts["rule"]),
        "stack_iou": spec.stack_iou, "d_appear_s": spec.d_appear_s, "d_gone_s": spec.d_gone_s,
        "sub_table": {"OX": gi.OX, "OY": gi.OY}, "offset_ms": float(monster["offset_ms"]),
        "k": olf.K, "min_pixels": label_check.MIN_PIXELS,
        "monster_params": str(spec.monster_params), "monster_params_sha256": monster_sha,
        "g2": {"bar_px": G2_BAR_PX, "min_fits": G2_MIN_FITS,
               "margin_px": float(consts["margin_px"])},
        "items": dict(report["items"]),
        "items_unsprited": sorted(int(k) for k, v in report["items"].items() if v is None),
        "version": 2,
        "absent_rule": {
            "what": "an id whose sprite fits >= t_item on MORE than max_rate of the absent points "
                    "is treated as item_unsprited (never labelled; its frames excluded)",
            "t_item": float(ab["t_item"]), "max_rate": ab["max_rate"], "points": ab["points"],
            "seed": ab["seed"], "point_rule": ab["point_rule"], "sub_rule": ab["sub_rule"],
            "fit": ab["fit"], "per_sprite": ab["per_sprite"], "t_item_rule": ab["t_item_rule"]},
        "items_excluded": list(ab["items_excluded"]),
        "fit_report_sha256": report_sha, "fit_session": sid,
        "fitted_at": report.get("fitted_at"), "fit_commit": report.get("commit"),
        "drops": report["drops"], "drops_sha256": report["drops_sha256"],
        "sprites_dir": report["sprites_dir"], "resnames": report["resnames"],
        "resnames_sha256": report["resnames_sha256"], "occluders": dict(report["occluders"]),
        **provenance,
    }  # fmt: skip


def cmd_freeze_1080(a: argparse.Namespace) -> dict[str, Any]:
    """T-I2: items-params-1080.json, frozen ONCE from a READY fit-1080 report; prints its sha256."""
    spec = XMAS02_FI_1080
    out: Path = a.out or spec.params
    if out.exists():
        raise SystemExit(f"{out} exists: the 1080 params are frozen ONCE (T-I2); a change is a "
                         "new amendment and a new file")  # fmt: skip
    if out.resolve().is_relative_to(ROOT):
        raise SystemExit(f"{out}: client-derived (sprite hashes): never inside the repo")
    raw = a.fit.read_bytes()
    mraw = spec.monster_params.read_bytes()
    tool = Path(__file__).resolve()
    prov = {"fit_report": str(a.fit), "tool": str(tool.relative_to(ROOT)),
            "tool_sha256": olf.sha256_file(tool), "frozen_at": olf.now_ict(),
            "commit": olf.git_head()}  # fmt: skip
    doc = freeze_1080_params(spec, json.loads(raw), sha256_bytes(raw), json.loads(mraw),
                             sha256_bytes(mraw), prov)  # fmt: skip
    frozen_sheets(doc)  # the sprite files still hash as the report's table (refuses otherwise)
    if ml.occluders(spec.mspec).provenance()["rsw_sha256"] != doc["occluders"]["rsw_sha256"]:
        raise SystemExit("the map's RSW differs from the fit report's")
    out.parent.mkdir(parents=True, exist_ok=True)
    data = (json.dumps(doc, indent=1, ensure_ascii=False) + "\n").encode()
    out.write_bytes(data)
    return {"what": f"T-I2: the frozen 1080 {spec.rule} params", "out": str(out),
            "sha256": sha256_bytes(data), "fit_report_sha256": doc["fit_report_sha256"],
            "anchor_px": doc["anchor_px"], "scale": doc["scale"], "t_item": doc["t_item"],
            "bar_px": doc["bar_px"], "items_excluded": doc["items_excluded"],
            "frozen_at": prov["frozen_at"], "commit": prov["commit"]}  # fmt: skip


# --- T2-items (O.5) and the evaluation's pack (O.9) ----------------------------------------------


def pool_labels(docs: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """PURE: every kept item label of the label files, with its stratum and frame reference."""
    out = []
    for doc in docs:
        for f in doc["frames"]:
            if f["status"] != "keep":
                continue
            for it in f["items"]:
                out.append({"session": doc["session"], "split": doc["split"],
                            "frame_id": f["frame_id"], "t": f["t"], "shard": f["shard"],
                            "offset": f["offset"], "size": f["size"], "floor_id": it["floor_id"],
                            "item_id": it["item_id"], "box": it["box"], "rel": it.get("rel"),
                            "under": it.get("under"), "ncc": it["ncc"],
                            "stratum": stratum_of(it)})  # fmt: skip
    return out


def check_pack_docs(spec: FiSpec, docs: Sequence[Mapping[str, Any]], eval_test: bool,
                    params_sha: str) -> None:  # fmt: skip
    """O.5 / O.9: T2-items pools FIT (val) + TRAIN label files; the evaluation's pack pools the
    held-out's ``--eval-test`` label files only; one frozen params file for all."""
    for doc in docs:
        sid = str(doc["session"])
        if doc.get("rule") != spec.rule or doc.get("params_sha256") != params_sha:
            raise SystemExit(f"{sid}: not {spec.rule} labels under the given frozen params")
        if str(doc.get("screen", "720")) != spec.screen:  # T-I1 (a 720 file has no "screen")
            raise SystemExit(f"{sid}: {doc.get('screen', '720')} labels, not the {spec.screen}")
        if eval_test:
            if doc.get("eval_test") is not True or role_refusal(spec, sid, None, True):
                raise SystemExit(f"{sid}: the evaluation's pack takes --eval-test fiT labels only")
        else:
            why = role_refusal(spec, sid, doc.get("split"), False)
            if doc.get("eval_test") or why is not None:
                raise SystemExit(f"{sid}: not in T2-items' pool ({why or 'evaluation labels'})")


def _open(sid: str, spec: FiSpec, layout: Path, cache: dict[str, ml.RecSession]
          ) -> ml.RecSession:  # fmt: skip
    if sid not in cache:
        cache[sid] = ml.RecSession.open(str(NAS / sid), spec.mspec, layout)
    return cache[sid]


def _ref(sess: ml.RecSession, row: Mapping[str, Any]) -> qa_export.JpegRef:
    return qa_export.JpegRef(int(row["frame_id"]), int(row["t"]), sess.path / str(row["shard"]),
                             int(row["offset"]), int(row["size"]))  # fmt: skip


def absent_points(docs: Sequence[Mapping[str, Any]], spec: FiSpec, prm: Mapping[str, Any],
                  sheets: FrozenSheets, sessions: dict[str, ml.RecSession], layout: Path,
                  n: int, rng: random.Random, fit: bool) -> list[dict[str, Any]]:  # fmt: skip
    """O.1e's absent points on the docs' KEPT frames (one per frame, frames in a seeded order):
    the box of a random drop sprite of the map at a random sub-cell of an absent cell, inside
    the frame (>= 30 px from the UI and the edge), clear of our self box, our bar and every unit
    box. ``fit``: also its best colour fit (the HARD negatives' score) and the fitted box."""
    frames = [(str(doc["session"]), str(doc["split"]), f) for doc in docs for f in doc["frames"]
              if f["status"] == "keep"]  # fmt: skip
    frames.sort(key=lambda x: (x[0], int(x[2]["frame_id"])))
    rng.shuffle(frames)
    ids = sorted(sheets.sheets)  # the labelled ids (v1: every sprited id; v2: not the excluded)
    off = int(float(prm["offset_ms"]) * 1e6)
    out: list[dict[str, Any]] = []
    for sid, split, f in frames:
        if len(out) >= n:
            break
        sess = _open(sid, spec, layout, sessions)
        t = int(f["t"])
        tw = t - off
        world = sess.lab.timeline.frame_world(tw)
        scene = sess.scene(world)
        if scene is None or world.self_pos is None:
            continue
        floors = il.floor_items(sess.lab.timeline.events)
        live = [(fl.x, fl.y) for fl in floors if fl.t_a - NEG_ITEM_SPAN_NS <= t
                < fl.t_v + NEG_ITEM_SPAN_NS]  # fmt: skip
        ucells = [(float(e.x), float(e.y)) for e in world.entities
                  if e.objtype in occ.UNIT_OBJTYPES and not e.hidden]  # fmt: skip
        sp = world.self_pos
        c = absent_cell((float(sp[0]), float(sp[1])), live, ucells, rng)
        if c is None:
            continue
        iid = rng.choice(ids)
        sub = (rng.choice(SUBS), rng.choice(SUBS))
        cell = (c[0] + gi.OX[sub[0]], c[1] + gi.OY[sub[1]])
        sheet = sheets(iid)
        p = None if sheet is None else _predict(sheet, cell, scene, prm)
        if p is None or sheet is None:
            continue
        me = anchor_and_depth(scene, scene.player)[0]
        units = _units(sess, world, scene, tw)
        b = p.box
        if not gi.inside(b, sess.lab.size, sess.lab.ui_rects, margin_of(prm)) or \
                gi.overlaps(b, self_box_of(prm, me)) or \
                gi.overlaps(b, gi.at(me, tuple(prm["bar_px"]))) \
                or any(gi.overlaps(b, gi.at(u, gi.UNIT_BOX)) for u in units):  # fmt: skip
            continue
        row: dict[str, Any] = {"session": sid, "split": split, "frame_id": f["frame_id"],
                               "t": t, "shard": f["shard"], "offset": f["offset"],
                               "size": f["size"], "floor_id": None, "item_id": None,
                               "sprite_of": iid, "cell": list(c), "box": [round(x, 1) for x in b],
                               "under": occl_under(spec, scene, b, cell)}  # fmt: skip
        if fit:
            bgr = ml.read_png(_ref(sess, f))
            fr = colour_fit(bgr, olf.valid_map(sess.lab.size, sess.lab.ui_rects), sheet, p,
                            int(prm["r_label"]))  # fmt: skip
            if fr is None:
                continue
            row.update({"ncc": fr[0], "dx": fr[1], "dy": fr[2],
                        "box": [round(b[0] + fr[1], 1), round(b[1] + fr[2], 1),
                                round(b[2] + fr[1], 1), round(b[3] + fr[2], 1)]})  # fmt: skip
        out.append(row)
    return out


_OCCL: dict[str, olf.Occluders] = {}


def occl_under(spec: FiSpec, scene: Any, box: Box, cell: tuple[float, float]) -> str | None:
    if spec.name not in _OCCL:
        _OCCL[spec.name] = ml.occluders(spec.mspec)
    return _OCCL[spec.name].under(scene, box, cell)


def reference_sheet(sheets: Mapping[int, SpriteSheet], scale: int = 3,
                    tiles: Sequence[tuple[int, int, int]] = (TILE_ORANGE, TILE_PALE)
                    ) -> tuple[npt.NDArray[np.uint8], int]:  # fmt: skip
    """O.5's reference.png: each DISTINCT floor sprite (its one frame; identical images once) at
    native size x ``scale``, once on each floor colour, side by side, in a grid; no names. Returns
    the image and the number of distinct sprites."""
    seen: set[tuple[tuple[int, ...], bytes]] = set()
    imgs = []
    for _iid, sh in sorted(sheets.items()):
        rgba = compose_frame(sh.spr, sh.act, 0, 0)[0]  # type: ignore[arg-type]
        k = (tuple(rgba.shape), np.ascontiguousarray(rgba).tobytes())
        if k in seen:
            continue
        seen.add(k)
        imgs.append(rgba)
    cell_w = max(x.shape[1] for x in imgs) * scale + 12
    cell_h = max(x.shape[0] for x in imgs) * scale + 12
    cols = 4
    rows = (len(imgs) + cols - 1) // cols
    canvas = np.full((rows * cell_h, cols * cell_w * len(tiles), 3), 90, np.uint8)
    for i, rgba in enumerate(imgs):
        r, c = divmod(i, cols)
        a = rgba[..., 3:4].astype(float) / 255.0
        for j, bg in enumerate(tiles):
            rgb = (rgba[..., :3] * a + np.array(bg, float) * (1 - a)).astype(np.uint8)
            big = np.repeat(np.repeat(rgb, scale, axis=0), scale, axis=1)
            y0 = r * cell_h
            x0 = (c * len(tiles) + j) * cell_w
            canvas[y0 + 2 : y0 + cell_h - 2, x0 + 2 : x0 + cell_w - 2] = np.array(bg, np.uint8)
            oy = y0 + (cell_h - big.shape[0]) // 2
            ox = x0 + (cell_w - big.shape[1]) // 2
            canvas[oy : oy + big.shape[0], ox : ox + big.shape[1]] = big
    return canvas, len(imgs)


def order_entries(entries: Sequence[Mapping[str, Any]], seed: int, salt: str
                  ) -> list[dict[str, Any]]:  # fmt: skip
    """PURE: the pack's ONE seeded order of every crop (items and E mixed)."""
    out = sorted((dict(e) for e in entries),
                 key=lambda e: (e["stratum"], e["session"], int(e["frame_id"]),
                                -1 if e.get("floor_id") is None else int(e["floor_id"]),
                                e.get("kind", "")))  # fmt: skip
    random.Random(f"{salt}:{seed}:order").shuffle(out)
    return out


def cmd_pack(a: argparse.Namespace) -> dict[str, Any]:
    from PIL import Image

    spec = spec_of(a)
    rnd = getattr(a, "round", 1)
    why = round_refusal(spec, rnd, bool(a.eval_test))
    if why is not None:
        raise SystemExit(why)
    # rounds 3-7 (O17 / O20 / O26 / items-1080 T-I4 / Amendment 22) pack as round 2, own seed +
    # slots
    r2 = rnd in (2, 3, 4, 5, 6, 7, 8, 9, 10)
    if rnd in (3, 4, 5, 6, 7, 8, 9, 10):
        if not a.eval_test:
            raise SystemExit(f"--round {rnd}: the evaluation's pack only (--eval-test)")
        # round 6: the seed from the CLI (T-I4), recorded in the key; round 7: the plan's 74
        want = {3: R3_EVAL_SEED, 4: R4_EVAL_SEED, 5: R5_EVAL_SEED, 6: a.seed,
                7: R7_EVAL_SEED, 8: R8_EVAL_SEED, 9: R9_EVAL_SEED,
                10: r10_seed([Path(p).stem for p in a.labels])}[rnd]  # fmt: skip
    elif r2:
        want = R2_EVAL_SEED if a.eval_test else R2_PACK_SEED
    else:
        want = spec.eval_seed if a.eval_test else spec.pack_seed
    if a.seed != want:
        src = ("Amendment 38" if rnd == 10 and want == R10_EXT_SEED
               else seed_source(rnd, r2, bool(a.eval_test)))  # fmt: skip
        raise SystemExit(f"--seed {a.seed}: the pre-registered seed is {want} ({src})")
    raw = INSTRUCTIONS.read_bytes()
    if sha256_bytes(raw) != INSTRUCTIONS_SHA256:
        raise SystemExit(f"{INSTRUCTIONS}: not the pinned instructions ({INSTRUCTIONS_SHA256[:8]})")
    params_raw = a.params.read_bytes()
    prm = load_params(a.params, spec)
    docs = [json.loads(p.read_text()) for p in a.labels]
    check_pack_docs(spec, docs, a.eval_test, sha256_bytes(params_raw))
    if rnd == 10 and r10_seed([str(d.get("session")) for d in docs]) != a.seed:
        raise SystemExit(f"--seed {a.seed}: the labels' sessions are not that pack's "
                         "(Amendment 38: seed 78 exactly when one is ifH37 .. ifH40)")  # fmt: skip
    why_docs = round_docs_refusal(rnd, docs)
    if why_docs is not None:
        raise SystemExit(why_docs)
    sheets = frozen_sheets(prm)
    cands = pool_labels(docs)
    if r2:
        second = {3: R3_NOAURA, 4: R4_NOAURA, 5: R5_STAGING, 6: R6_STAGING,
                  7: R7_STAGING, 8: R8_STAGING, 9: R9_STAGING,
                  10: R10_STAGING}.get(rnd, R2_NOAURA)  # fmt: skip
        picks = r2_picks(cands, a.eval_test, a.seed, spec.salt, second)
    elif a.eval_test:
        picks = draw_strata([{**c, "stratum": "X"} for c in cands], {"X": EVAL_ITEMS}, a.seed,
                            spec.salt)  # fmt: skip
        for p in picks:
            p["stratum"] = stratum_of(p)
    else:
        picks = draw_strata(cands, PACK_N, a.seed, spec.salt)
    sessions: dict[str, ml.RecSession] = {}
    rng = random.Random(f"{spec.salt}:{a.seed}:E")
    plain = absent_points(docs, spec, prm, sheets, sessions, a.layout_templates, PACK_E_PLAIN,
                          rng, fit=False)  # fmt: skip
    hard_docs = docs if a.eval_test else [d for d in docs if d["split"] == "train"]
    hard_pool = absent_points(hard_docs, spec, prm, sheets, sessions, a.layout_templates,
                              HARD_POOL, rng, fit=True)  # fmt: skip
    plain_keys = {(p["session"], int(p["frame_id"])) for p in plain}
    hard = hard_pick(
        [p for p in hard_pool if (p["session"], int(p["frame_id"])) not in plain_keys],
        (EVAL_E if a.eval_test else PACK_E_PLAIN + PACK_E_HARD) - len(plain),
    )
    entries = (
        [{**p, "truth": "item", "kind": "item"} for p in picks]
        + [{**p, "truth": "none", "stratum": "E", "kind": "plain"} for p in plain]
        + [{**p, "truth": "none", "stratum": "E", "kind": "hard"} for p in hard]
    )
    entries = order_entries(entries, a.seed, spec.salt)
    tag = "eval" if a.eval_test else "t2"
    root = a.pack_dir or spec.work / f"pack-{tag}-seed{a.seed}"
    keyd = a.key_dir or spec.work / f"key-{tag}-seed{a.seed}"
    for d in (root, keyd):
        if d.resolve().is_relative_to(ROOT):
            raise SystemExit(f"{d}: client pixels never go inside the repo")
        if d.exists() and any(d.iterdir()):
            raise SystemExit(f"{d} is not empty: a pack is built once")
        d.mkdir(parents=True, exist_ok=True)
    ref_img, n_sprites = reference_sheet(sheets.all)  # every floor sprite of the drop tables
    Image.fromarray(ref_img).save(root / "reference.png")
    (root / "instructions.txt").write_bytes(raw)
    key: dict[str, Any] = {"what": f"{'O.9' if a.eval_test else 'O.5'}: the answer key",
                           "rule": spec.rule, "seed": a.seed, "salt": spec.salt,
                           "eval_test": bool(a.eval_test),
                           "params_sha256": sha256_bytes(params_raw),
                           "instructions_sha256": INSTRUCTIONS_SHA256,
                           "reference_sha256": olf.sha256_file(root / "reference.png"),
                           "label_files": [{"file": str(p), "sha256": olf.sha256_file(p)}
                                           for p in a.labels], "crops": {}}  # fmt: skip
    if spec.screen != "720":  # T-I4: a 1080 key names its screen and round (720 keys unchanged)
        key.update({"screen": spec.screen, "round": rnd})
    for i, e in enumerate(entries, 1):
        cid = f"{i:03d}"
        sess = _open(e["session"], spec, a.layout_templates, sessions)
        rgb = np.ascontiguousarray(ml.read_png(_ref(sess, e))[:, :, 2::-1])
        Image.fromarray(il.crop_pair(rgb, e["box"])).save(root / f"crop-{cid}.png")
        key["crops"][cid] = {
            k: e.get(k)
            for k in (
                "truth",
                "stratum",
                "kind",
                "session",
                "frame_id",
                "floor_id",
                "item_id",
                "box",
                "rel",
                "under",
                "ncc",
                "sprite_of",
            )
        }
    (keyd / "answer_key.json").write_text(json.dumps(key, indent=1))
    by = Counter(e["stratum"] for e in entries)
    return {"what": key["what"], "pack": str(root), "key": str(keyd / "answer_key.json"),
            "crops": len(entries), "by_stratum": dict(sorted(by.items())),
            "items": len(picks), "e_plain": len(plain), "e_hard": len(hard),
            "hard_pool": len(hard_pool),
            "hard_ncc": [p["ncc"] for p in hard],
            "short": pack_short(picks, by, a.eval_test, r2), "round": rnd,
            "pool": dict(Counter(c["stratum"] for c in cands)),
            "reference_sprites": n_sprites, "reference_sha256": key["reference_sha256"],
            "instructions_sha256": INSTRUCTIONS_SHA256, "built_at": olf.now_ict(),
            "commit": olf.git_head()}  # fmt: skip


def cmd_refs(a: argparse.Namespace) -> dict[str, Any]:
    """predict_dir's --refs for the evaluation: every judged frame (scene and layout read) and
    every I4 frame of the ``--eval-test`` label files, keyed ``<session>.<frame_id:09d>``, paths
    as the worker sees the NAS (``--container-root``)."""
    out: dict[str, Any] = {}
    for p in a.labels:
        doc = json.loads(p.read_text())
        if not doc.get("eval_test"):
            raise SystemExit(f"{p}: refs are for --eval-test label files only")
        sid = doc["session"]
        rows = [
            f for f in doc["frames"] if f["reasons"] not in (["no_scene"], ["ui_layout_mismatch"])
        ]
        rows += [k["i4"] for k in doc.get("kills", []) if k.get("i4")]
        for f in rows:
            out[f"{sid}.{int(f['frame_id']):09d}"] = {
                "path": f"{a.container_root.rstrip('/')}/{sid}/{f['shard']}",
                "offset": int(f["offset"]),
                "size": int(f["size"]),
            }
    a.refs_out.parent.mkdir(parents=True, exist_ok=True)
    a.refs_out.write_text(json.dumps(out, indent=0))
    return {
        "what": "predict_dir --refs for the evaluation",
        "refs": str(a.refs_out),
        "frames": len(out),
    }


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("freeze")
    p.add_argument("--map", default="xmas_dun02", choices=MAP_NAMES)
    p.add_argument("--sprites", type=Path, default=None)
    p.add_argument("--resnames", type=Path, default=None)
    p.add_argument("--drops", type=Path, default=None)
    p.add_argument("--out", type=Path, default=None, help="default: the map's O.3 (g) path")
    p.add_argument("--report", type=Path, default=None)
    p = sub.add_parser("freeze-v2")
    p.add_argument("--map", default="xmas_dun02", choices=MAP_NAMES)
    p.add_argument("--v1", type=Path, required=True, help="the v1 params (FROZEN)")
    p.add_argument("--labels", type=Path, nargs="+", required=True,
                   help="FIT p31 and DEV p38's label files under v1")  # fmt: skip
    p.add_argument("--layout-templates", type=Path, default=LAYOUT_TEMPLATES)
    p.add_argument("--out", type=Path, default=None, help="default: the map's params v2 path")
    p.add_argument("--report", type=Path, default=None)
    p = sub.add_parser("fit-1080")
    p.add_argument("part", help="the 1080 FIT session (a name ending in -xmas02-ifF)")
    p.add_argument("--sprites", type=Path, default=None)
    p.add_argument("--resnames", type=Path, default=None)
    p.add_argument("--drops", type=Path, default=None)
    p.add_argument("--absent-points", type=int, default=ABSENT_POINTS_1080)
    p.add_argument("--workers", type=int, default=1)
    p.add_argument("--layout-templates", type=Path, default=LAYOUT_TEMPLATES)
    p.add_argument("--out", type=Path, required=True, help="the fit report (RAM, not the repo)")
    p = sub.add_parser("freeze-1080")
    p.add_argument("--fit", type=Path, required=True, help="a READY fit-1080 report")
    p.add_argument("--out", type=Path, default=None, help="default: the 1080 spec's params path")
    p.add_argument("--report", type=Path, default=None)
    p = sub.add_parser("label")
    p.add_argument("part")
    p.add_argument("--map", default="xmas_dun02", choices=MAP_NAMES)
    p.add_argument("--spec", choices=SCREENS, default="720", help="T-I1: the screen's spec")
    p.add_argument("--split", choices=("train", "val"), default=None)
    p.add_argument("--eval-test", action="store_true")
    p.add_argument("--model", type=Path, default=None)
    p.add_argument("--model-sha256", default=None)
    p.add_argument("--params", type=Path, required=True)
    p.add_argument("--workers", type=int, default=1)
    p.add_argument("--layout-templates", type=Path, default=LAYOUT_TEMPLATES)
    p.add_argument("--out", type=Path, required=True)
    p = sub.add_parser("g2")
    p.add_argument("labels", type=Path, nargs="+")
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--pool", action="store_true",
                   help="Amendment 7: the NOT_ENOUGH TRAIN files judged together")  # fmt: skip
    p = sub.add_parser("pack")
    p.add_argument("labels", type=Path, nargs="+")
    p.add_argument("--map", default="xmas_dun02", choices=MAP_NAMES)
    p.add_argument("--spec", choices=SCREENS, default="720", help="T-I1: the screen's spec")
    p.add_argument("--params", type=Path, required=True)
    p.add_argument("--seed", type=int, required=True)
    p.add_argument("--round", type=int, choices=PACK_ROUNDS, default=1,
                   help="O15: round 2's seeds (65 T2-r2, 66 the evaluation) and sizes; "
                        "6: the 1080 round's evaluation (T-I4, --spec 1080); 7: Amendment 22's "
                        "(seed 74); 8: Amendment 26's (seed 75); 9: Amendment 32's "
                        "(seed 76); 10: Amendment 36's (seed 77)")  # fmt: skip
    p.add_argument("--eval-test", action="store_true")
    p.add_argument("--pack-dir", type=Path, default=None)
    p.add_argument("--key-dir", type=Path, default=None)
    p.add_argument("--layout-templates", type=Path, default=LAYOUT_TEMPLATES)
    p.add_argument("--out", type=Path, required=True)
    p = sub.add_parser("refs")
    p.add_argument("labels", type=Path, nargs="+")
    p.add_argument("--container-root", default="/datasets")
    p.add_argument("--refs-out", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    a = ap.parse_args(argv)
    if a.cmd == "label" and not a.eval_test and a.split is None:
        raise SystemExit("label: --split train|val, or --eval-test")
    if a.cmd == "label" and a.eval_test and a.split is not None:
        raise SystemExit("label: --eval-test has no --split")
    out = {"freeze": cmd_freeze, "freeze-v2": cmd_freeze_v2, "label": cmd_label, "g2": cmd_g2,
           "pack": cmd_pack, "refs": cmd_refs, "fit-1080": cmd_fit_1080,
           "freeze-1080": cmd_freeze_1080}[a.cmd](a)  # fmt: skip
    dest = a.report if a.cmd in ("freeze", "freeze-v2", "freeze-1080") else a.out
    if dest is not None:
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(json.dumps(out) + "\n")
    summary = {k: v for k, v in out.items() if k != "frames"}
    if a.cmd == "fit-1080":  # the verdict first; the sprite table and the grids are in --out
        summary = fit_summary(out)
    print(json.dumps(summary, indent=1)[:8000])
    return 0


def fit_summary(report: Mapping[str, Any]) -> dict[str, Any]:
    """PURE: fit-1080's printed lines (the whole report is written to --out)."""
    ab = report.get("absent") or {}
    fc = report.get("fit") or {}
    return {"verdict": report.get("verdict"), "why": report.get("why"),
            "session": report.get("session"), "best_scale": fc.get("best_scale"),
            "anchor": fc.get("anchor"), "common_views": fc.get("common_views"),
            "scales": fc.get("scales"), "t_item": ab.get("t_item"),
            "absent_points": ab.get("points"), "items_excluded": ab.get("items_excluded"),
            "g2_at_fit": (report.get("at_fit") or {}).get("g2"),
            "bar_check": report.get("bar_check"), "fitted_at": report.get("fitted_at"),
            "commit": report.get("commit")}  # fmt: skip


if __name__ == "__main__":
    sys.exit(main())
