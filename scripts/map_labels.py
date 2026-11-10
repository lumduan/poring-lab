#!/usr/bin/env python3
"""MAP-PARAMETERISED MONSTER LABELS for RECORDER sessions: the orcsdun01 o3h rule on another map
(docs/planning/payf07-detector.md, PRE-REGISTERED 2026-10-24 18:25:24 ICT, 7ed0422, before this
was built). The rule is scripts/orc_labels_fix.py's (fix 2 facing, 2b / 2c, the fit, o3h); this
module adds what another map and another recording path need, and never changes orcsdun01's.

    map_labels.py offset    PART... --out JSON                     4b: 1d, FIT only
    map_labels.py threshold PART... --offset JSON --out JSON       4e: o3h's T_h, FIT only
    map_labels.py freeze --offset JSON --threshold JSON --out PARAMS
    map_labels.py check     PART... --params PARAMS --out JSON     5: C1 / C2 (T1 on TEST, or a
                                                                   TRAIN session's own C1, 3c)
    map_labels.py labels    PART    --params PARAMS --out JSON     the kept labels (no pixels)
    map_labels.py pack      LABELS.json... --seed 21 --pack-dir DIR --key-dir DIR
                            --instructions TXT --instructions-sha256 HEX       6: T2's pack

gef_fild10 (docs/planning/gef10-detector.md, PROPOSED 2026-10-25 20:51:49 ICT, 3e31b01, before
this was built): ``--map gef_fild10``. Its "staged" session is the Orc Lord WATCH, split by CELL
(one cell per map change, 3a); TEST is also refused by NAME (``*-rdp-rogue-s7`` / ``-s8``); the
ENGAGED units are LABELLED by the frozen variant (4h: E1 / E2 / E3, chosen on FIT by ``engaged``;
E0 = payf07's Amendment B); ``dying_in_view`` (4g) excludes a frame with a die animation on
screen; T2's pack has two strata per species (N / E: the key's ``samples``, blind_score.py
``--sample N|E``).

    map_labels.py engaged   PART... --offset-ms MS --o3h-tau T --out JSON   4h's selection (FIT)

gef_fild10 ROUND 2 (docs/planning/gef10-round2.md, DRAFT 2026-10-26): ``check --c1-rule round2``
adds ONE exclusion to C1, the PICKUP NOTICE: a standing label whose PREDICTED box overlaps (any
area > 0) a notice that ``gef10_r2_measure.find_notices`` detects in that frame's top rows is not
scored (reason ``notice``, counted per species like ``ui_or_edge``). The default ``--c1-rule
round1`` is the frozen round-1 check, unchanged bit for bit (its rows file is byte-identical); the
output's ``c1_rule`` records which ran. ``round2`` was gef_fild10's only (➡️ since xmas02's T-8
also xmas_dun02's, its only rule: below), and it refuses round 1's spent TEST parts (the watch's
cells 11-14, a7, a8). Round 2's TEST2 (a9, a10, a11) is refused by
NAME by the measuring commands, ``labels`` and ``pack`` (``test2_suffixes``), except under
``--eval-test2`` below.

TEST2's EVALUATION (docs/benchmarks/gef10-eval.md AMENDMENT R2-2, 2026-10-29 12:53 ICT, before
TEST2's evaluation labels exist): ``--eval-test2`` is gef_fild10's only (xmas_dun02 has its own
flag, ``--eval-test``: below) and reads TEST2 parts
ONLY (a9, a10, a11, w3 by NAME); round 1's spent TEST and round 3's TEST3 stay refused. Without
the flag both commands behave exactly as before.

    map_labels.py labels PART --eval-test2 --params PARAMS(FROZEN) --classes JSON --out JSON
    map_labels.py pack   LABELS.json... --eval-test2 --per-species 60 --seed 35 --min-fit T_h ...

``labels --eval-test2`` needs the FROZEN parameters and records ``"eval_test2": true``; ``pack
--eval-test2`` takes only such TEST2 label files, puts every map species with at least one kept
label in the pool (no conditional tier), draws the first N of t2_order per species and stratum
(N / E) and records ``per_species_target`` N and ``"eval_test2": true``.

xmas_dun02 (docs/planning/xmas02-detector.md, ACCEPTED 2026-11-06, Amendment A; its tool gaps
T-1, T-2, T-3, T-8, T-9 of 1f): ``--map xmas_dun02``. FIT is xw1 and TEST is xw5, xp1 and X2, all
by session NAME (the sessions are recorded after the plan: ``<stamp>-rdp-xmas02-xw1``); a part is
refused by its NAME before anything of it is read. Amendment M (2026-11-09, the Garm Baby class):
the held-out watch gw3 (``<stamp>-rdp-gb-gw3``) is refused like TEST, and Garm Baby (1515) is in
T2's tier whatever its pool (the Goblin stays conditional). Engaged units are EXCLUDED (E0, D11)
with gef10's Amendments B (``crowded``, T_h's set) and C (``facing_unknown``); ``dying_in_view``
(D8); one T2 stratum, seed 51, salt ``xmas02``. Its C1 always has the pickup-notice rule (``check
--c1-rule round2``, 4h / 5; ``round1`` is refused there). Its evaluation reads TEST under its own
flag, ``--eval-test`` (9: seed 53, 60 per species), and refuses everything else:

    map_labels.py labels PART --map xmas_dun02 --eval-test --params PARAMS(FROZEN) --classes JSON
    map_labels.py pack   LABELS.json... --map xmas_dun02 --eval-test --per-species 60 --seed 53 ...

UI RECTANGLES (every map; T-1): the hunting (or 4-row) layout's windows with the chat window of
the session's DATE (chat_window.for_sid: the 2026-11-05 standard (0, 585, 600, 720) from
20261105T12 on, the legacy (0, 532, 600, 626) before -- RECTS's own value, so every older
session's rectangles are unchanged), minus a window lying wholly inside another (the standard
chat window holds notice_left whole; detector_vs_packets.nested_rects). The recorder path accepts
``recorder_version`` 5 or 6 (T-3: v6 changed only the IO-guard rule, e5d892f).

xmas_dun02's TERRAIN candidate (docs/planning/xmas02-detector.md 4f, D10): a spec with
``terrain=True`` adds orc_labels_fix.TerrainOccluders (the map's GAT: a cell >= 10 units above a
label's own cell, south of it, drawn from the label's floor to its top) beside the RSW models.
``threshold`` then reports o3h AND o3h-t (o3h-t's own T_h, clear of terrain too) and 4f's FIT
adoption test (n >= 30 under terrain, median NCC lower by >= 0.05, Mann-Whitney p < 0.01; steps 5
and 20 reported); ``freeze`` takes the rule the test chose (``occlusion`` o3h or o3h-t, its T_h,
the GAT's sha256 among the occluders); ``check`` scores BOTH rules from one pass (the rows'
``under`` / ``o3h_t``; the verdict is the frozen rule's); ``labels`` labels by the frozen rule.
Every spec without the switch (pay_fild07, gef_fild10) runs exactly as before.

A PART is a session directory, optionally restricted to the staged session's spots:
``DIR`` or ``DIR:spots=0-7``. The map's spec (MAPS) names its FIT and TEST parts; the measuring
commands refuse TEST, and ``labels`` / ``pack`` refuse TEST too (TEST2's evaluation labels and
pack: ``--eval-test2``).

OFFLINE ONLY (ADR-0007: packets are ground truth for labels, never an agent input): the session's
packets, its PNG tar shards (read-only, NAS), the decoded sprites, the map's RSW / RSM models and a
local KB (client- and GPL-derived: /dev/shm only, never committed). No GPU, no client, no input.

The candidate frames (4f): the map is the spec's at tw = t - 1d and at t; no map change in
[t - 5 s, t]; our character's Timeline position the same at every 100 ms from tw - 1 s to t;
outside the GM windows; the staged session outside each spot's inventory span [first drop - 20 s,
last drop result + 5 s]; the hunting layout read from pixels (client_layout) per frame.
"""

from __future__ import annotations

import argparse
import bisect
import hashlib
import io
import json
import random
import shutil
import statistics
import sys
from collections import Counter, defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

import numpy as np
import numpy.typing as npt

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import orc_camera_check as occ  # noqa: E402
import orc_labels_fix as olf  # noqa: E402
import qa_export  # noqa: E402

from poring_dataset import frames as recorded  # noqa: E402
from poring_dataset.camera import map_key  # noqa: E402
from poring_dataset.labels import STATE_ACTION, in_windows  # noqa: E402
from poring_dataset.render import MonsterAction, anchor_and_depth  # noqa: E402
from poring_dataset.sprites import union  # noqa: E402
from poring_dataset.timeline import Timeline  # noqa: E402
from poring_packets.world import direction_toward  # noqa: E402

Box = tuple[float, float, float, float]
TMP = Path("/dev/shm/poring-lab-tmp/payf07")
STILL_BACK_NS = 1_000_000_000  # 4f: still from tw - 1 s ...
STILL_STEP_NS = 100_000_000  # ... checked every 100 ms up to t
MAP_CHANGE_NS = 5_000_000_000  # 4f: no map change in [t - 5 s, t]
INV_BEFORE_NS = 20_000_000_000  # 4f: the staged inventory span, first drop - 20 s ...
INV_AFTER_NS = 5_000_000_000  # ... last drop result + 5 s
SWEEP_MAX_MS = 500  # 4b: the 1d sweep's upper edge (Amendment A 18:35:20; attempt 1: 1,000)
COARSE_MS = tuple(range(0, SWEEP_MAX_MS + 1, 50))
MIN_WALKER_SAMPLES = 50  # 4b's stop
T_H_PERCENTILE = 5.0  # 4e: the clear kept labels' p5
C1_BAR = 0.050  # T1 (5): unrounded
C2_BAR_PX = 4.0  # every species is ground (1b)
C2_MIN_LABELS = 20
OWN_C1_MIN = 50  # 3c: a session's own C1 needs >= 50 standing labels scored
T2_PER_SPECIES = 30
T2_SALT = "payf07"
LABELS = "payf07-o3h"
ENGAGED = "engaged"  # Amendment B (18:54:50): a fight with our character near the label's time
ENGAGED_BACK_NS = 3_000_000_000
ENGAGED_FWD_NS = 1_000_000_000


REFERENCE_PRT = (1002, 1082, 1063, 1008, 1113, 1018)  # Poring, White Plant + prt_fild08's others


@dataclass(frozen=True)
class MapSpec:
    """One map's label inputs (payf07-detector.md 1-4; gef10-detector.md 3-4 for the fields with
    defaults, which keep pay_fild07's behaviour)."""

    name: str
    cells: tuple[int, int]
    rsw: Path
    models: Path
    species: tuple[int, ...]  # the map's spawn species (the tier's)
    walkers: tuple[int, ...]  # 1d's mobile species
    fit_px: int
    staged: str  # the staged session's id
    fit: dict[str, frozenset[int] | None]  # session id -> its FIT spots (None: the whole session)
    test: dict[str, frozenset[int] | None]
    kb: Path
    sprites: Path
    labels: str = "payf07-o3h"  # the labels' name (label files, params, the cache)
    t2_salt: str = "payf07"
    staged_kind: str = "items"  # "items": stage_items' spots; "watch": one spot per map change
    test_suffixes: tuple[str, ...] = ()  # TEST by session NAME too (gef10 3b: s7, s8)
    conditional: tuple[int, ...] = (1080,)  # in T2's tier only with >= 30 kept labels in the pool
    reference: tuple[int, ...] = REFERENCE_PRT  # T2's reference beside the map's species
    engaged_labels: bool = False  # gef10 4h: engaged units may be LABELLED (the frozen variant)
    dying_rule: bool = False  # gef10 4g (D8): dying_in_view
    tmp: Path = Path("/dev/shm/poring-lab-tmp/payf07")
    plan: str = "docs/planning/payf07-detector.md"
    layouts: dict[str, str] = field(default_factory=dict)  # session id -> its layout (else hunt)
    test2_suffixes: tuple[str, ...] = ()  # gef10 ROUND 2's TEST2 by NAME (gef10-round2.md)
    test3_suffixes: tuple[str, ...] = ()  # gef10 ROUND 3's TEST3 by NAME (gef10-round3.md 2)
    # gef10 round 3 (gef10-round3.md 5): MORE staged sessions, each with its own kind ("items":
    # stage_items' spots; "watch": one cell per map change); ``staged`` keeps ``staged_kind``
    staged_extra: dict[str, str] = field(default_factory=dict)
    # xmas02-detector.md 3b: FIT by session NAME too (its sessions are recorded after the plan)
    fit_suffixes: tuple[str, ...] = ()
    # xmas02 4a / 4i (D11): engaged units EXCLUDED by a FIXED variant (no FIT selection, no N / E
    # strata), with gef10's Amendments B (crowded, T_h's set) and C (facing_unknown); None: the
    # map's own rule (payf07: EngagedRule; gef10: engaged_labels and 4h's selection)
    engaged_fixed: str | None = None
    kb_classes: Path | None = None  # the KB's classes.json when it is not ``kb``'s (xmas02 11.3)
    c1_rules: tuple[str, ...] = ("round1",)  # the C1 rules this map is checked under (T-8)
    test_spent: bool = False  # gef10 13r: round 1's TEST was read once by T1 (round 2 never reads)
    # the evaluation's flag (EVAL_FLAGS) and the TEST names it reads (gef10-eval.md R2-2: TEST2;
    # xmas02 9: TEST); None: no evaluation labels or pack on this map
    eval_flag: str | None = None
    eval_suffixes: tuple[str, ...] = ()
    t2_seed: int | None = None  # a pre-registered T2 seed (xmas02 6: 51); None: any
    eval_seed: int | None = None  # a pre-registered evaluation pack seed (xmas02 9: 53)
    eval_per_species: int | None = None  # ... and its N per species (xmas02 9: 60)
    # xmas02-detector.md 4f (D10): the TERRAIN occluders (orc_labels_fix.TerrainOccluders, the
    # map's GAT in camera.GAT_DIR) beside the models: ``threshold`` and ``check`` report o3h AND
    # o3h-t, ``freeze`` takes the rule 4f's adoption test chose. Off: every rule as before
    terrain: bool = False

    def staged_kind_of(self, sid: str) -> str | None:
        """The staged kind of session ``sid`` (its spots exist), or None (no spots)."""
        if sid == self.staged:
            return self.staged_kind
        return self.staged_extra.get(sid)

    def is_test(self, sid: str, spots: frozenset[int] | None) -> bool:
        """The part shares a frame with TEST (round 1's, round 2's TEST2 or round 3's TEST3): by
        the role table, or by the session's NAME."""
        return self.is_round1_test(sid, spots) or any(
            sid.endswith(s) for s in (*self.test2_suffixes, *self.test3_suffixes))  # fmt: skip

    def is_round1_test(self, sid: str, spots: frozenset[int] | None) -> bool:
        """Round 1's TEST (gef10: read once by T1, 13r; spent): the role table or the NAME."""
        return overlaps_role(sid, spots, self.test) or any(
            sid.endswith(s) for s in self.test_suffixes)  # fmt: skip

    def is_fit(self, sid: str, spots: frozenset[int] | None) -> bool:
        """Every frame of the part lies in FIT: by the role table, or the whole session by NAME."""
        return inside_role(sid, spots, self.fit) or self.fit_by_name(sid)

    def overlaps_fit(self, sid: str, spots: frozenset[int] | None) -> bool:
        """The part shares a frame with FIT (the parameters' own data)."""
        return overlaps_role(sid, spots, self.fit) or self.fit_by_name(sid)

    def fit_by_name(self, sid: str) -> bool:
        return any(sid.endswith(s) for s in self.fit_suffixes)

    def labels_engaged_rule(self) -> bool:
        """The label stack is gef10's EngagedLabeler / EngagedLabelRule (Amendments B and C):
        a map that labels engaged units (4h), or one with a fixed engaged variant (xmas02 E0)."""
        return self.engaged_labels or self.engaged_fixed is not None


PAYF07 = MapSpec(
    name="pay_fild07",
    cells=(400, 400),
    rsw=TMP / "grf" / "data" / "pay_fild07.rsw",
    models=TMP / "grf" / "data" / "model",
    species=(1033, 1010, 1116, 1060, 1031, 1080),
    walkers=(1033, 1116, 1060, 1031, 1010),
    fit_px=6,
    staged="20261024T170356-rdp-stage-items-b",
    fit={"20261024T170356-rdp-stage-items-b": frozenset(range(8)),
         "20261024T123622-rdp-thief-t1b": None},
    test={"20261024T170356-rdp-stage-items-b": frozenset(range(8, 12)),
          "20261024T131838-rdp-thief-t2": None},
    kb=TMP / "kb",
    sprites=TMP / "sprites-all",
)  # fmt: skip
G10 = Path("/dev/shm/poring-lab-tmp/gef10-det")
GEF10_WATCH = "20261025T195325-rdp-ow1"
# ROUND 2's TEST2 by NAME (gef10-round2.md), also the parts --eval-test2 reads (R2-2)
GEF10_TEST2 = ("-rdp-rogue-a9", "-rdp-rogue-a10", "-rdp-rogue-a11", "-rdp-w3")
GEF10 = MapSpec(
    name="gef_fild10",
    cells=(400, 400),
    rsw=G10 / "grf" / "data" / "gef_fild10.rsw",
    models=G10 / "grf" / "data" / "model",
    species=(1273, 1023, 1031, 1686, 1190, 1189, 1079, 1080),
    walkers=(1273, 1023, 1686, 1031, 1190, 1189),
    fit_px=6,
    staged=GEF10_WATCH,
    fit={GEF10_WATCH: frozenset(range(11)),
         "20261025T200922-rdp-rogue-pilot": None,
         "20261025T203115-rdp-rogue-pilot2": None,
         "20261028T151136-rdp-stage-gef10-e3": frozenset(range(4))},  # round 3: the item anchor
    test={GEF10_WATCH: frozenset(range(11, 15))},
    kb=G10 / "kb",
    sprites=G10 / "sprites-all",
    labels="gef10-o3h-e",
    t2_salt="gef10",
    staged_kind="watch",
    # Amendment D (the parent, rogue-gef10.md Amendment C, 21:39): the scored block restarted as
    # a1..a8; TEST = a7, a8 (s7 / s8 stay refused: they never exist)
    test_suffixes=("-rdp-rogue-a7", "-rdp-rogue-a8", "-rdp-rogue-s7", "-rdp-rogue-s8"),
    conditional=(1273, 1023, 1031, 1686, 1190, 1189, 1079, 1080),  # D4: every species
    reference=(1002, 1082, 1153, 1152),  # Poring, White Plant, Orc Zombie, Orc Skeleton (6)
    engaged_labels=True,
    dying_rule=True,
    tmp=G10,
    plan="docs/planning/gef10-detector.md",
    layouts={GEF10_WATCH: "rows4"},  # Amendment A (2026-10-25 21:10:53): the watch's 4-row layout
    # ROUND 2 (gef10-detector.md 13s; Batt 2026-10-26 ~09:4x "do round 2 now"): TEST2 = a9, a10,
    # a11 (recorded after round 1's T1, never read) + w3, an immune lattice watch recorded AFTER
    # 13s's commit (its name is refused before it exists); all refused like TEST
    test2_suffixes=GEF10_TEST2,
    # ROUND 3 (gef10-round3.md 2, PROPOSED 2026-10-29 12:07, before any read): TEST3 = the staged
    # session e3b, held out for the item rule's G2; E3 and e3b are stage_items sessions (spots =
    # a first warp followed by drops); FIT for the item anchor = E3's spots 0-3
    test3_suffixes=("-rdp-stage-gef10-e3b",),
    staged_extra={"20261028T151136-rdp-stage-gef10-e3": "items",
                  "20261029T110813-rdp-stage-gef10-e3b": "items"},
    c1_rules=("round1", "round2"),  # round 2 (gef10-round2.md): + the pickup notice
    test_spent=True,  # 13r: T1 read round 1's TEST once
    eval_flag="eval_test2", eval_suffixes=GEF10_TEST2,  # gef10-eval.md AMENDMENT R2-2
)  # fmt: skip
# xmas_dun02 (docs/planning/xmas02-detector.md, ACCEPTED 2026-11-06 Amendment A): the client data
# in /dev/shm (11.3: the RSW + its 37 RSMs, the sprites, the MERGED sprite-name table; data/kb's
# classes.json); the GAT is camera.GAT_DIR's (X1's)
XD = Path("/dev/shm/poring-lab-tmp/xmas-det")
XMAS02_X2 = "20261105T225409-rdp-xmas02-x2"  # 2e (D8): TEST-P, refused for FIT and TRAIN
XMAS02_GW3 = "-rdp-gb-gw3"  # Amendment M: the held-out Garm Baby watch (`--label gb-gw3`)
# Amendment O1 (2026-11-10): the floor items' held-out, fresh base pilots recorded beside the
# runner (`--label hunt-xmas02-fiT<n>`): refused by NAME before any of them records, for the
# monster labels, T2's pool and the cache as for TEST; NOT in eval_suffixes (the item model's)
XMAS02_FIT = ("-rdp-hunt-xmas02-fiT1", "-rdp-hunt-xmas02-fiT2", "-rdp-hunt-xmas02-fiT3")
XMAS02 = MapSpec(
    name="xmas_dun02",
    cells=(260, 260),
    rsw=XD / "grf" / "data" / "xmas_dun02.rsw",
    models=XD / "grf" / "data" / "model",
    # 1b / D3: the tier (Myst Case, Cruiser, Cookie, Christmas Cookie) + Garm Baby and Christmas
    # Goblin CONDITIONAL (Amendment M, 2026-11-09: Garm Baby in the tier); Stormy Knight (1251)
    # OUT: its frames are unchecked_species (4h)
    species=(1249, 1248, 1265, 1246, 1515, 1607),
    walkers=(1249, 1248, 1265, 1246, 1515),  # 4b: Garm Baby counts when seen
    fit_px=6,  # 4c-4d: +-6 px for every species, no anchor (no species flies)
    staged="",  # no staged session: every part is a whole session
    fit={},  # 3b: FIT = xw1, by NAME (fit_suffixes)
    test={XMAS02_X2: None},
    kb=XD / "kb-sprites",  # the merged monster_sprite_names.json (Santa Poring's stem poring_)
    kb_classes=ROOT / "data" / "kb" / "classes.json",
    sprites=XD / "sprites" / "data" / "sprite" / "몬스터",
    # 4 / Amendment C: "xmas02-o3h", renamed "xmas02-o3h-t" because 4f's FIT test ADOPTED terrain
    # (2026-11-06 17:27, xmas02-detector.md Amendment G); cmd_freeze refuses a name and a rule apart
    labels="xmas02-o3h-t",
    terrain=True,  # 4f (D10): o3h-t is reported beside o3h; freeze takes the rule 4f chose
    t2_salt="xmas02",
    # 3b: TEST by NAME; Amendment M (2026-11-09): + gw3, the Garm Baby watch on 3a's TEST stands,
    # held out until the model is frozen (refused by labels / pack / the cache like xw5)
    test_suffixes=("-rdp-xmas02-xw5", "-rdp-xmas02-xp1", XMAS02_X2, XMAS02_GW3, *XMAS02_FIT),
    # D3: in T2's tier only with >= 30 kept labels; Amendment M: Garm Baby (1515) IN the tier
    conditional=(1607,),
    # 6: the multi-view reference beside the map's species: Stormy Knight, Poring, Santa Poring
    reference=(1251, 1002, 1062),
    dying_rule=True,  # D8 (gef10 4g)
    tmp=XD,
    plan="docs/planning/xmas02-detector.md",
    fit_suffixes=("-rdp-xmas02-xw1",),
    engaged_fixed="E0",  # D11
    c1_rules=("round2",),  # 4h / 5: C1 always drops a label under a pickup notice (T-8)
    eval_flag="eval_test",  # 9 (T-9): the evaluation reads TEST only
    # Amendment M7 (2026-11-09): gw3, the held-out Garm Baby watch, is scored with TEST -- read only
    # after the model is frozen (its last.pt sha256 recorded first)
    eval_suffixes=("-rdp-xmas02-xw5", "-rdp-xmas02-xp1", XMAS02_X2, XMAS02_GW3),
    t2_seed=51,
    eval_seed=53,
    eval_per_species=60,
)  # fmt: skip
MAPS = {"pay_fild07": PAYF07, "gef_fild10": GEF10, "xmas_dun02": XMAS02}


# --- pure parts -------------------------------------------------------------------------------


def parse_part(text: str) -> tuple[Path, frozenset[int] | None]:
    """``DIR`` -> (DIR, None); ``DIR:spots=0-7`` / ``DIR:spots=0,2,5-6`` -> (DIR, {spots})."""
    path, sep, rest = text.partition(":spots=")
    if not sep:
        return Path(text), None
    spots: set[int] = set()
    for chunk in rest.split(","):
        lo, dash, hi = chunk.partition("-")
        if not lo.isdigit() or (dash and not hi.isdigit()):
            raise SystemExit(f"{text!r}: spots are N, N-M or a comma list of them")
        spots.update(range(int(lo), int(hi if dash else lo) + 1))
    return Path(path), frozenset(spots)


def overlaps_role(sid: str, spots: frozenset[int] | None,
                  role: dict[str, frozenset[int] | None]) -> bool:  # fmt: skip
    """The part (session, spots or the whole session) shares a frame with ``role``'s parts."""
    if sid not in role:
        return False
    rs = role[sid]
    return rs is None or spots is None or bool(spots & rs)


def inside_role(sid: str, spots: frozenset[int] | None,
                role: dict[str, frozenset[int] | None]) -> bool:  # fmt: skip
    """Every frame of the part lies in ``role``'s parts."""
    if sid not in role:
        return False
    rs = role[sid]
    return rs is None or (spots is not None and spots <= rs)


def spot_starts(events: Iterable[dict[str, Any]]) -> list[int]:
    """The staged session's spot starts (3a): the ``map_change`` times followed by at least one
    ``drop_request`` before the next ``map_change``, in time order."""
    out: list[int] = []
    last: int | None = None
    dropped = False
    for e in sorted(events, key=lambda e: int(e["t_mono_ns"])):
        if e.get("type") == "map_change":
            if last is not None and dropped:
                out.append(last)
            last, dropped = int(e["t_mono_ns"]), False
        elif e.get("type") == "drop_request" and last is not None:
            dropped = True
    if last is not None and dropped:
        out.append(last)
    return out


def cell_starts(events: Iterable[dict[str, Any]], map_name: str) -> list[int]:
    """gef10-detector.md 3a: the WATCH's cells, one per ``map_change`` to ``map_name`` (each cell
    starts with its @warp), in time order."""
    return sorted(int(e["t_mono_ns"]) for e in events if e.get("type") == "map_change"
                  and map_key(str(e.get("map") or "")) == map_name)  # fmt: skip


def starts_of(kind: str, map_name: str, events: Iterable[dict[str, Any]]) -> list[int]:
    """A staged session's spot (or cell) starts by ``kind``."""
    return cell_starts(events, map_name) if kind == "watch" else spot_starts(events)


def staged_starts(spec: MapSpec, events: Iterable[dict[str, Any]]) -> list[int]:
    """The staged session's spot (or cell) starts by its kind."""
    return starts_of(spec.staged_kind, spec.name, events)


def spot_of(t: int, starts: Sequence[int]) -> int | None:
    """The spot index of time ``t`` (None before the first spot)."""
    i = bisect.bisect_right(starts, t) - 1
    return i if i >= 0 else None


def inventory_spans(events: Iterable[dict[str, Any]], starts: Sequence[int]
                    ) -> list[tuple[int, int]]:  # fmt: skip
    """4f: per spot, [its first ``drop_request`` - 20 s, its last ``drop_result`` (or request)
    + 5 s]."""
    by: dict[int, list[int]] = defaultdict(list)
    for e in events:
        if e.get("type") in ("drop_request", "drop_result"):
            k = spot_of(int(e["t_mono_ns"]), starts)
            if k is not None:
                by[k].append(int(e["t_mono_ns"]))
    return [(min(ts) - INV_BEFORE_NS, max(ts) + INV_AFTER_NS) for _k, ts in sorted(by.items())]


def still_times(tw: int, t: int, back: int = STILL_BACK_NS,
                step: int = STILL_STEP_NS) -> list[int]:  # fmt: skip
    """The times our character must stand at one place (4f): every ``step`` from tw - back to t,
    both ends included."""
    out = list(range(tw - back, t, step))
    return out + [t]


def same_place(points: Sequence[tuple[float, float] | None]) -> bool:
    return bool(points) and points[0] is not None and all(p == points[0] for p in points)


def recent(times: Sequence[int], t: int, window: int) -> bool:
    """A time of ``times`` (sorted) lies in [t - window, t]."""
    i = bisect.bisect_left(times, t - window)
    return i < len(times) and times[i] <= t


def sweep_fine(best: int) -> list[int]:
    """4b's fine grid: 10 ms within +-50 of the coarse best, clipped to the sweep (Amendment A)."""
    return olf.fine_grid(best, lo=COARSE_MS[0], hi=COARSE_MS[-1])


def engagement_times(events: Iterable[dict[str, Any]], aid: int) -> dict[int, list[int]]:
    """Amendment B: per unit, the times of an ``act`` between it and our character (either
    direction) or of our ``attack_request`` on it, sorted."""
    out: dict[int, list[int]] = defaultdict(list)
    for e in events:
        kind = e.get("type")
        if kind == "act":
            src, dst = e.get("src_gid"), e.get("target_gid")
            if src == aid and dst is not None and dst != aid:
                out[int(dst)].append(int(e["t_mono_ns"]))
            elif dst == aid and src is not None and src != aid:
                out[int(src)].append(int(e["t_mono_ns"]))
        elif kind == "attack_request" and e.get("target_gid") is not None:
            out[int(e["target_gid"])].append(int(e["t_mono_ns"]))
    return {g: sorted(ts) for g, ts in out.items()}


def is_engaged(times: dict[int, list[int]], gid: int, tw: int, back: int = ENGAGED_BACK_NS,
               fwd: int = ENGAGED_FWD_NS) -> bool:  # fmt: skip
    """Amendment B: an engagement time of ``gid`` lies in [tw - back, tw + fwd]."""
    ts = times.get(gid, [])
    i = bisect.bisect_left(ts, tw - back)
    return i < len(ts) and ts[i] <= tw + fwd


@dataclass
class EngagedRule(olf.FacingRule):
    """fix 2's facing and 2b / 2c (orc_labels_fix.FacingRule), then Amendment B's ``engaged``."""

    times: dict[int, list[int]] = field(default_factory=dict)

    def choose(self, world: Any, e: Any, st: Any, rules: Any, tw: int, sheet: Any,
               yaw: float) -> tuple[tuple[int, str], str | None]:  # fmt: skip
        facing, why = super().choose(world, e, st, rules, tw, sheet, yaw)
        if why is None and is_engaged(self.times, e.gid, tw):
            return facing, ENGAGED
        return facing, why


ENGAGED_VARIANTS = ("E0", "E1", "E2", "E3")  # gef10-detector.md 4h
ENGAGED_TAG = "engaged:"  # an engaged label's facing source starts with it
SELF_MASK_PAD_PX = 4  # 4h E2 / E3: our self box + 4 px leaves the fit's valid pixels
E3_GROUPS = (MonsterAction.IDLE, MonsterAction.ATTACK, MonsterAction.HURT)
E_OFFSET_BAR_PX = 2.0  # 4h's selection: the kept engaged fits' median |dx| and |dy|
FACING_UNKNOWN = "facing_unknown"  # gef10 Amendment C (2d): the Timeline never saw the facing


def heading_toward(src: tuple[float, float], dst: tuple[float, float]) -> int | None:
    """PURE (4h E2 / E3): rAthena's direction from cell ``src`` toward ``dst`` (map_calc_dir's
    rule, poring_packets.world.direction_toward, on the rounded offset). None for the same cell."""
    return direction_toward(int(round(dst[0] - src[0])), int(round(dst[1] - src[1])))


@dataclass
class EngagedLabelRule(EngagedRule):
    """gef10 4h: fix 2 + 2b / 2c for every unit, and an ENGAGED unit (Amendment B's test) by
    ``variant``: E0 EXCLUDED (``engaged``: payf07's rule, EngagedRule's exactly); E1 fix 2's facing,
    labelled (2b / 2c as any unit); E2 / E3 fix 2's walk facing while WALKING, else TOWARD our
    character, labelled (2b applies, 2c does not: the facing is not a move's). The engaged units
    labelled at the current timeline time are ``engaged_now`` (the labeller's fit reads it); their
    facing source is prefixed ``engaged:``."""

    variant: str = "E0"
    engaged_now: set[int] = field(default_factory=set)
    tw_now: int | None = None

    def choose(self, world: Any, e: Any, st: Any, rules: Any, tw: int, sheet: Any,
               yaw: float) -> tuple[tuple[int, str], str | None]:  # fmt: skip
        if self.variant not in ENGAGED_VARIANTS:
            raise SystemExit(f"engaged variant {self.variant!r}: one of {ENGAGED_VARIANTS}")
        if tw != self.tw_now:
            self.tw_now, self.engaged_now = tw, set()
        facing, why = olf.FacingRule.choose(self, world, e, st, rules, tw, sheet, yaw)
        unknown = facing[1] == "timeline:None"  # Amendment C (2d): no facing source at all
        if not is_engaged(self.times, e.gid, tw):
            return facing, FACING_UNKNOWN if why is None and unknown else why
        if self.variant == "E0":
            return facing, ENGAGED if why is None else why
        tagged = (facing[0], ENGAGED_TAG + facing[1])
        if why == olf.NEXT_MOVE or self.variant == "E1":
            if why is None and unknown:
                why = FACING_UNKNOWN
            if why is None:
                self.engaged_now.add(e.gid)
            return tagged, why
        self.engaged_now.add(e.gid)
        me = (getattr(world, "self_x", None), getattr(world, "self_y", None))
        if st.state == "walk" or me[0] is None or me[1] is None:
            if unknown:
                self.engaged_now.discard(e.gid)
                return tagged, FACING_UNKNOWN
            return tagged, None
        h = heading_toward((float(e.x), float(e.y)), (float(me[0]), float(me[1])))
        if h is None and unknown:  # on our own cell with no facing source: nothing to draw by
            self.engaged_now.discard(e.gid)
            return tagged, FACING_UNKNOWN
        return ((h, ENGAGED_TAG + "toward_self") if h is not None else tagged), None


def envelope(sheet: Any, pred: Any, group: int) -> Any:
    """4h E2 / E3: ``pred`` redrawn with action ``group`` at the same anchor, scale and direction,
    EVERY frame (the phase is not trusted): its box the frames' envelope. None: it draws nothing."""
    ai = sheet.act.action_index(int(group), pred.direction)
    ext = union([sheet.extent(ai, m) for m in range(sheet.motions(ai))])
    if ext is None:
        return None
    ax, ay = pred.anchor_px
    k = pred.scale
    return replace(pred, box=(ax + k * ext[0], ay + k * ext[1], ax + k * ext[2], ay + k * ext[3]),
                   action=int(group), action_index=ai, motion=None, phase_known=False,
                   mask=None, mask_origin=None)  # fmt: skip


def without_box(valid: npt.NDArray[np.bool_], box: Box, pad: float = SELF_MASK_PAD_PX
                ) -> npt.NDArray[np.bool_]:  # fmt: skip
    """PURE (4h E2 / E3): ``valid`` with ``box`` grown by ``pad`` px set False (a copy)."""
    out = valid.copy()
    h, w = out.shape
    x0, y0 = max(0, int(np.floor(box[0] - pad))), max(0, int(np.floor(box[1] - pad)))
    x1, y1 = min(w, int(np.ceil(box[2] + pad))), min(h, int(np.ceil(box[3] + pad)))
    if x1 > x0 and y1 > y0:
        out[y0:y1, x0:x1] = False
    return out


class EngagedLabeler(olf.FixLabeler):
    """FixLabeler with 4h's fit for the engaged units of E2 / E3 (every frame of the Timeline
    action -- E3: also of IDLE, ATTACK and HURT -- at the rule's facing, our self box masked out of
    the valid pixels; the best fit). Every other unit, and E0 / E1, is FixLabeler's fit."""

    def __init__(self, *args: Any, variant: str = "E0", **kw: Any) -> None:
        super().__init__(*args, **kw)
        if variant not in ENGAGED_VARIANTS:
            raise SystemExit(f"engaged variant {variant!r}: one of {ENGAGED_VARIANTS}")
        self.variant = variant
        self.crowded: dict[int, bool] = {}  # gef10 Amendment B: the predicted box touches a unit's

    def frame(self, t: int, bgr: npt.NDArray[np.uint8] | None) -> Any:
        self.crowded = {}
        return super().frame(t, bgr)

    def fate(self, e: Any, st: Any, sheet: Any, pred: Any, facing: tuple[int, str],
             why: str | None, under: bool, grey: npt.NDArray[np.float64],
             unit_boxes: Sequence[tuple[int, Box]]) -> olf.LabelFate:  # fmt: skip
        self.crowded[e.gid] = any(g != e.gid and olf.overlap(pred.box, b) for g, b in unit_boxes)
        if self.variant not in ("E2", "E3") or e.gid not in getattr(self.facing, "engaged_now", ()):
            return super().fate(e, st, sheet, pred, facing, why, under, grey, unit_boxes)
        from poring_dataset.ui_layout import covered_fraction

        r = self.fit_px.get(int(e.job), 6)
        own = next((b for g, b in unit_boxes if g == -1), None)
        valid = self.valid if own is None else without_box(self.valid, own)
        groups = [int(STATE_ACTION.get(st.state, MonsterAction.IDLE))]
        if self.variant == "E3":
            groups += [int(g) for g in E3_GROUPS if int(g) not in groups]
        best: tuple[tuple[float, int, int, int], Any, int] | None = None
        for g in groups:
            p = envelope(sheet, pred, g)
            if p is None:
                continue
            f = olf.best_fit(olf.fit_label_all(grey, valid, sheet, p, r))
            if f is not None and (best is None or f[0] > best[0][0]):
                best = (f, p, g)
        base = olf.LabelFate(e.gid, e.job, under, why, None, "unfit", heading=facing[0],
                             facing_from=facing[1], state=st.state)  # fmt: skip
        fit = None if best is None else best[0]
        if best is None or fit is None or fit[0] < self.tau or olf.at_edge(fit[1], fit[2], r):
            crowd = any(g != e.gid and olf.overlap(pred.box, b) for g, b in unit_boxes)
            grown = (pred.box[0] - r, pred.box[1] - r, pred.box[2] + r, pred.box[3] + r)
            ui = covered_fraction(grown, self.lab.ui_rects) > 0
            return replace(base, fit=fit, fail="crowd" if crowd else "ui" if ui else "unfit")
        f, p, g = best
        raw = olf.motion_box(sheet, p, f[3])
        if raw is None:
            return replace(base, fit=fit)
        raw = (raw[0] + f[1], raw[1] + f[2], raw[2] + f[1], raw[3] + f[2])
        w, h = self.lab.size
        box = (max(0.0, raw[0]), max(0.0, raw[1]), min(float(w), raw[2]), min(float(h), raw[3]))
        return replace(base, fit=fit, fail=None, box=box, raw=raw,
                       state=f"{st.state}>{MonsterAction(g).name.lower()}")  # fmt: skip


def engaged_selection(rows: Sequence[dict[str, Any]], t_h: float,
                      variants: Sequence[str] = ("E1", "E2", "E3"),
                      bar: float = E_OFFSET_BAR_PX) -> dict[str, Any]:  # fmt: skip
    """PURE (4h's selection, FIT): per variant, the engaged fates KEPT (no 2b / 2c, the fit passes,
    NCC >= ``t_h``: o3h under a model box, the floor elsewhere) and their median |dx|, |dy|; the
    chosen variant = the most kept among those with both medians <= ``bar`` px, ties to the
    earlier (simpler) one; none qualifies: E0."""
    per: dict[str, Any] = {}
    for v in variants:
        rs = [r for r in rows if r["variant"] == v]
        kept = [r for r in rs if r["pre"] is None and r["fail"] is None and r["ncc"] is not None
                and float(r["ncc"]) >= t_h]  # fmt: skip
        mdx = statistics.median(abs(r["dx"]) for r in kept) if kept else None
        mdy = statistics.median(abs(r["dy"]) for r in kept) if kept else None
        good = mdx is not None and mdy is not None and mdx <= bar and mdy <= bar
        per[v] = {"fates": len(rs), "kept": len(kept),
                  "kept_share": round(len(kept) / len(rs), 4) if rs else None,
                  "median_abs_dx": mdx, "median_abs_dy": mdy, "qualifies": good}  # fmt: skip
    ok = [v for v in variants if per[v]["qualifies"]]
    chosen = max(ok, key=lambda v: (per[v]["kept"], -variants.index(v))) if ok else "E0"
    return {"per_variant": per, "chosen": chosen, "t_h": t_h, "offset_bar_px": bar}


def percentile(values: Sequence[float], q: float) -> float:
    """numpy's linear percentile, rounded to 3 decimals (4e: frozen to 3 decimals)."""
    return round(float(np.percentile(np.asarray(values, float), q)), 3)


def c2_summary(rows: Sequence[dict[str, Any]], bar: float = C2_BAR_PX,
               min_n: int = C2_MIN_LABELS) -> dict[str, Any]:  # fmt: skip
    """C2 (5) for one species: median |dx|, |dy| <= bar with >= min_n labels."""
    offs = [r for r in rows if r.get("dx") is not None]
    out: dict[str, Any] = {"n": len(offs), "bar_px": bar}
    if not offs:
        return {**out, "verdict": "NO_VERDICT"}
    adx = statistics.median(abs(r["dx"]) for r in offs)
    ady = statistics.median(abs(r["dy"]) for r in offs)
    out.update({"median_abs_dx": adx, "median_abs_dy": ady,
                "median_dx": statistics.median(r["dx"] for r in offs),
                "median_dy": statistics.median(r["dy"] for r in offs),
                "best_ncc_median": round(statistics.median(r["best"] for r in offs), 3),
                })  # fmt: skip
    if len(offs) < min_n:
        out["verdict"] = "NO_VERDICT"
    else:
        out["verdict"] = "PASS" if adx <= bar and ady <= bar else "FAIL"
    return out


def t1_summary(rows: Sequence[dict[str, Any]], species: Sequence[int],
               tau: float = olf.TAU) -> dict[str, Any]:  # fmt: skip
    """T1 (5): C1 pooled over ``species`` (bar <= 0.050, unrounded), per species; C2 per species
    (a FAIL is a STOP, not the verdict)."""
    mine = [r for r in rows if int(r["mob"]) in species]
    by: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for r in mine:
        by[int(r["mob"])].append(r)
    pooled = occ.c1_summary(mine, tau)
    scored, bad = pooled["scored"], pooled["bad_label"]
    ratio = bad / scored if scored else None
    c2 = {str(m): c2_summary(by[m]) for m in sorted(by)}
    stops = sorted(m for m, v in c2.items() if v["verdict"] == "FAIL")
    return {
        "c1": {"bar": f"bad_label / scored <= {C1_BAR} pooled over {list(species)} (unrounded)",
               "pooled": pooled, "ratio": ratio,
               "per_species": {str(m): occ.c1_summary(by[m], tau) for m in sorted(by)}},
        "c2": {"bar": f"median |dx|, |dy| <= {C2_BAR_PX} px, species with >= {C2_MIN_LABELS}",
               "per_species": c2, "stop_species": stops},
        "T1": "NO_VERDICT" if ratio is None else "PASS" if ratio <= C1_BAR else "FAIL",
        "c2_stop": bool(stops),
        "other_species_rows": len(rows) - len(mine),
    }  # fmt: skip


def own_c1_verdict(summary: dict[str, Any]) -> str:
    """3c's join rule for a TRAIN session: its own C1 <= 0.050 on >= 50 standing labels."""
    scored = summary["c1"]["pooled"]["scored"]
    if scored < OWN_C1_MIN:
        return "NOT_ADDED_TOO_FEW"
    return "ADDED" if summary["c1"]["ratio"] <= C1_BAR else "NOT_ADDED_C1"


def t2_order(items: Sequence[dict[str, Any]], seed: int, mob: int, salt: str = T2_SALT,
             stratum: str | None = None) -> list[dict[str, Any]]:  # fmt: skip
    """6: one species' pool sorted by (session, frame, gid), shuffled by
    ``random.Random(f"payf07:{seed}:{mob}")`` (gef10 6: ``f"gef10:{seed}:{mob}:{stratum}"``)."""
    order = sorted(items, key=lambda it: (it["session"], it["frame_id"], it["gid"]))
    tail = "" if stratum is None else f":{stratum}"
    random.Random(f"{salt}:{seed}:{mob}{tail}").shuffle(order)
    return order


def round2_pool(
    items: Sequence[dict[str, Any]], min_fit: float | None, exclude: set[tuple[str, int, int]]
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """PURE (11, round 2): the pool without (a) labels NOT under a model whose fit is below
    ``min_fit`` (``weak_fit``: the frozen T_h on every label) and (b) the crops an earlier round
    judged (session, frame, gid). Returns the kept items and the counts removed by each rule."""
    kept, cut = [], {"weak_fit": 0, "judged_before": 0}
    for it in items:
        if (it["session"], int(it["frame_id"]), int(it["gid"])) in exclude:
            cut["judged_before"] += 1
        elif min_fit is not None and not it["under"] and float(it["ncc"]) < min_fit:
            cut["weak_fit"] += 1
        else:
            kept.append(it)
    return kept, cut


def frame_exclusions(world: Any, scene: Any, size: tuple[int, int], spec_species: Sequence[int],
                     class_species: Sequence[int], aid: int | None,
                     dying: Sequence[tuple[float, float]] = ()) -> list[str]:  # fmt: skip
    """4g: what keeps a frame from being labelled whole besides its monster labels: a warp / NPC
    in view, another player in view, a monster of a species outside the tier or the classes;
    gef10 4g (D8): a unit in its die animation whose cell projects on screen (``dying``: their
    cells; ``dying_in_view``)."""
    out = []
    w, h = size
    for cell in dying:
        u = anchor_and_depth(scene, (float(cell[0]), float(cell[1])))[0]
        if 0 <= u[0] < w and 0 <= u[1] < h:
            out.append("dying_in_view")
            break
    for e in world.entities:
        if e.hidden:
            continue
        u = anchor_and_depth(scene, (e.x, e.y))[0]
        if not (0 <= u[0] < w and 0 <= u[1] < h):
            continue
        if e.objtype == 6:
            out.append("warp_in_view")
        elif e.objtype == 0 and e.gid != aid:
            out.append("other_player")
        elif e.objtype == 5 and e.job not in spec_species and e.job not in class_species:
            out.append(f"unchecked_species:{e.job}")
    return sorted(set(out))


# --- the session ------------------------------------------------------------------------------


def png_index(session: Path, manifest: dict[str, Any]) -> list[Any]:
    """Every frame of a recorder session, in frame order, from its index only: PNG (tar headers
    and the json members; a frame's png and json may lie in two shards; a cut shard raises) or an
    RDP video (ADR-0024: video.idx.csv and the stream's access units). poring_dataset.frames
    FrameRefs: qa_export.JpegRef's fields (``shard`` is the tar or video.hevc)."""
    return recorded.frame_refs(session, manifest, strict=True)


def read_png(ref: Any) -> npt.NDArray[np.uint8]:
    """One frame as BGR (one seek and read of its bytes): a PNG member (PIL), or an RDP video's
    access unit decoded alone (poring_dataset.frames.read_ref: BT.709 full range, checked)."""
    if Path(ref.shard).suffix == ".hevc":
        return recorded.read_ref(ref)
    from PIL import Image

    with ref.shard.open("rb") as fh:
        fh.seek(ref.offset)
        data = fh.read(ref.size)
    if len(data) != ref.size:
        raise ValueError(f"{ref.shard}@{ref.offset}: short read")
    rgb = np.asarray(Image.open(io.BytesIO(data)).convert("RGB"))
    return np.ascontiguousarray(rgb[:, :, ::-1])


# T-3: v6 changed only the IO-guard rule and guard_rule (e5d892f); v7 (ADR-0024, 2026-11-09) the
# rdp default format (the GPU video; a --format png session is written as in v6)
RECORDER_VERSIONS = (5, 6, 7)
# ADR-0024: an RDP recording is PNG or the GPU video (the same grab, clock and region; lossy).
# 3c's frame gates (the layout check, o3h's sprite NCC with T_h) were fitted on PNG: a video
# recording stays REFUSED here until a pre-registered parity check passes (gpu-recording.md 9.4
# live check 4; the parent's review, 2026-11-09) -- record label data with --format png
RECORDING_FORMATS = ("png",)


def check_recording(manifest: dict[str, Any]) -> None:
    """3c's recording path (fail closed): RDP at 1280 x 720 on the lab server, PNG only (the GPU
    video refused until its parity check, ADR-0024), recorder v5 to v7 (xmas02-detector.md 3c / T-3;
    detector_vs_packets.SESSION_VERSIONS)."""
    want = {"backend": "rdp", "game_region": [80, 77, 1280, 720],
            "server": "lab-rathena"}  # fmt: skip
    bad = {k: manifest.get(k) for k, v in want.items() if manifest.get(k) != v}
    if manifest.get("format") not in RECORDING_FORMATS:
        bad["format"] = manifest.get("format")
    if manifest.get("recorder_version") not in RECORDER_VERSIONS:
        bad["recorder_version"] = manifest.get("recorder_version")
    if bad:
        raise SystemExit(f"{manifest.get('session_id')}: not the recording path of 3c: {bad}")


LAYOUT_RECTS = {"hunt": "hunt", "rows4": "standard"}  # a frame layout -> its UI rectangles


def layout_matches(state: dict[str, Any], layout: str) -> bool:
    """PURE (4f; gef10 Amendment A): the read state IS the session's layout: ``hunt`` (1 row,
    collapsed, Battle Log) or ``rows4`` (the hotbar at 4 rows, the panel expanded, either tab)."""
    import client_layout

    if layout == "hunt":
        return bool(client_layout.matches(state, "hunt"))
    if layout == "rows4":
        return state.get("rows") == 4 and state.get("panel") == "expanded"
    raise SystemExit(f"unknown layout {layout!r}")


def use_kb(spec: MapSpec) -> None:
    qa_export.KB_CLASSES = spec.kb_classes or spec.kb / "classes.json"
    qa_export.KB_SPRITE_NAMES = spec.kb / "monster_sprite_names.json"


Rect = tuple[int, int, int, int]


def session_ui_rects(sid: str, layout: str = "hunt") -> tuple[Rect, ...]:
    """T-1 (xmas02-detector.md 1f): the UI windows (x0, y0, x1, y1) of the RECORDED session
    ``sid`` in ``layout``: client_layout.RECTS with the chat window of the session's date
    (chat_window.for_sid: the 2026-11-05 standard (0, 585, 600, 720) from 20261105T12 on; the
    legacy (0, 532, 600, 626), RECTS's own value, before -- so every older session's rectangles are
    unchanged), minus a window lying wholly inside another (covered_fraction SUMS the windows'
    overlaps: the standard chat window holds the hunting layout's notice_left whole). The same
    rule as detector_vs_packets' score-session (chat_rect_for, session_rects, nested_rects)."""
    import detector_vs_packets as dvp

    chat_rect, _how = dvp.chat_rect_for(sid, "auto")
    return dvp.nested_rects(dvp.session_rects(LAYOUT_RECTS[layout], chat_rect))[0]


def session_labeler(path: Path, spec: MapSpec, layout: str = "hunt") -> qa_export.Labeler:
    """The recorder session's label stack (packets only, no pixel): the map's KB and sprites, the
    layout's UI rectangles with the chat window of the session's date (session_ui_rects), a finer
    Timeline. RecSession and the frame cache share it (build_frame_cache.py --labels map: our own
    character's box from the same camera)."""
    use_kb(spec)
    lab = qa_export.Labeler(path, str(olf.OLD_OFFSET_MS), labels="v1", k=olf.K)
    rects = session_ui_rects(qa_export.session_id(lab.manifest), layout)
    lab.ui_rects = tuple((x0, y0, x1 - x0, y1 - y0) for x0, y0, x1, y1 in rects)
    lab.sheets = qa_export.Sheets(directory=spec.sprites)
    tl = lab.timeline
    lab.timeline = Timeline(tl.events, tl.maps, snapshot_every=32, die_ms=tl.die_ms,
                            default_die_ms=tl.default_die_ms)  # fmt: skip
    return lab


@dataclass
class RecSession:
    """A recorder session (or some of the staged session's spots) as orc_labels_fix.Session's
    interface: lab, refs, sid, dwells, scene(), layout_ok(), facing_rule(), candidates()."""

    path: Path
    spec: MapSpec
    spots: frozenset[int] | None
    lab: qa_export.Labeler
    refs: list[qa_export.JpegRef]
    sid: str
    layout: Any
    starts: list[int] = field(default_factory=list)
    inventory: list[tuple[int, int]] = field(default_factory=list)
    map_changes: list[int] = field(default_factory=list)
    dwells: list[tuple[int, int]] = field(default_factory=list)  # (orc's report reads len())
    dropped: Counter[str] = field(default_factory=Counter)

    @classmethod
    def open(cls, part: str, spec: MapSpec, layout_templates: Path) -> RecSession:
        path, spots = parse_part(part)
        manifest = json.loads((path / "manifest.json").read_text())
        check_recording(manifest)
        sid = qa_export.session_id(manifest)
        layout = spec.layouts.get(sid, "hunt")
        lab = session_labeler(path, spec, layout)
        import client_layout

        occ.cache_compose()
        olf._speed_up()
        events = lab.timeline.events
        kind = spec.staged_kind_of(sid)
        starts = starts_of(kind, spec.name, events) if kind is not None else []
        if spots is not None and kind is None:
            raise SystemExit(f"{sid}: spots exist only in a staged session ({spec.staged}, "
                             f"{', '.join(sorted(spec.staged_extra))})")  # fmt: skip
        tm = client_layout.load_templates(layout_templates)
        import chat_window  # the recorded frames show the chat window of their date

        chat = chat_window.for_sid(sid)

        def check(bgr: npt.NDArray[np.uint8]) -> bool:
            state = client_layout.read(np.ascontiguousarray(bgr[:, :, 2::-1]), tm, chat=chat)
            return layout_matches(state, layout)

        changes = sorted(int(e["t_mono_ns"]) for e in events if e.get("type") == "map_change")
        return cls(path, spec, spots, lab, png_index(path, manifest), sid, check, starts,
                   inventory_spans(events, starts) if starts else [], changes)  # fmt: skip

    @property
    def name(self) -> str:
        if self.spots is None:
            return self.sid
        return f"{self.sid}:spots={','.join(str(s) for s in sorted(self.spots))}"

    def layout_ok(self, bgr: npt.NDArray[np.uint8]) -> bool:
        return bool(self.layout(bgr))

    def facing_rule(self, rule: str, variant: str | None = None) -> olf.FacingRule:
        """fix 2 + Amendment B (``engaged``), our character's id from the Timeline; a map whose
        spec labels engaged units (gef10 4h) gets EngagedLabelRule with ``variant`` (E0 when
        None: payf07's exclusion)."""
        base = olf.FacingRule.for_events(rule, self.lab.timeline.events)
        events = self.lab.timeline.events
        aid = self.lab.timeline.frame_world(self.refs[-1].t_mono_ns).aid if self.refs else None
        fights = any(e.get("type") in ("act", "attack_request") for e in events)
        if aid is None and fights:
            raise SystemExit(f"{self.sid}: our character's id is unknown (Amendment B needs it)")
        times = engagement_times(events, int(aid)) if aid is not None else {}  # no fight: none
        if self.spec.labels_engaged_rule():  # gef10 4h; xmas02's fixed E0 (Amendment C's 2d)
            return EngagedLabelRule(base.rule, base.moves, base.classes, times,
                                    variant=variant or self.spec.engaged_fixed or "E0")  # fmt: skip
        return EngagedRule(base.rule, base.moves, base.classes, times)

    def scene(self, world: Any) -> Any:
        if world.self_pos is None or not world.map or map_key(world.map) != self.spec.name:
            return None
        return occ.scene_for(self.lab, world.map, world.self_pos)

    def spot(self, t: int) -> int | None:
        return spot_of(t, self.starts) if self.starts else None

    def candidate(self, ref: qa_export.JpegRef, offset_ms: float) -> str | None:
        """None when the frame is a candidate (4f's packet-side rules), else the reason."""
        t = ref.t_mono_ns
        tw = t - int(offset_ms * 1e6)
        if self.starts:
            k = self.spot(t)
            if k is None:
                return "before_first_spot"
            if self.spots is not None and k not in self.spots:
                return "other_spot"
            if in_windows(t, self.inventory) or in_windows(tw, self.inventory):
                return "inventory_window"
        if in_windows(t, self.lab.windows):
            return "gm_window"
        if recent(self.map_changes, t, MAP_CHANGE_NS):
            return "map_change"
        tl = self.lab.timeline
        first, last = tl.frame_world(tw - STILL_BACK_NS), tl.frame_world(t)
        if not first.map or map_key(first.map) != self.spec.name or not last.map or \
                map_key(last.map) != self.spec.name:  # fmt: skip
            return "other_map"
        if first.self_pos is None or first.self_pos != last.self_pos:
            return "self_moving"
        pts = [tl.frame_world(x).self_pos for x in still_times(tw, t)[1:-1]]
        if not same_place([first.self_pos, *pts, last.self_pos]):
            return "self_moving"
        return None

    def candidates_at(self, offset_ms: float) -> list[qa_export.JpegRef]:
        out = []
        self.dropped = Counter()
        for ref in self.refs:
            why = self.candidate(ref, offset_ms)
            if why is None:
                out.append(ref)
            else:
                self.dropped[why] += 1
        return out


def role_refusal(spec: MapSpec, sid: str, spots: frozenset[int] | None, name: str,
                 role: str) -> None:  # fmt: skip
    if role == "fit" and not spec.is_fit(sid, spots):
        raise SystemExit(f"{name}: not a FIT part ({spec.plan} 3b): refused")
    if role == "not_test" and spec.is_test(sid, spots):
        raise SystemExit(f"{name}: shares frames with TEST (3b): refused")


def refuse(sess: RecSession, role: str) -> None:
    """The part by the session id its MANIFEST names (after it is opened)."""
    role_refusal(sess.spec, sess.sid, sess.spots, sess.name, role)


def refuse_part(spec: MapSpec, part: str, role: str) -> None:
    """The part by its directory's NAME, BEFORE anything of it is read (xmas02 3b: TEST is never
    opened by a command that refuses it); ``refuse`` checks the manifest's id after the open."""
    path, spots = parse_part(part)
    role_refusal(spec, path.name, spots, part, role)


# T-9: one evaluation flag per map (MapSpec.eval_flag): its CLI spelling and the parts it reads
EVAL_FLAGS = {"eval_test2": "--eval-test2", "eval_test": "--eval-test"}
EVAL_NOUN = {"eval_test2": "TEST2", "eval_test": "TEST"}


def eval_flag_of(a: argparse.Namespace) -> str | None:
    """The evaluation flag a command was given (None: none); two at once are refused."""
    on = [f for f in EVAL_FLAGS if getattr(a, f, False)]
    if len(on) > 1:
        raise SystemExit(f"one evaluation flag at a time, not {[EVAL_FLAGS[f] for f in on]}")
    return on[0] if on else None


def eval_map_refusal(spec: MapSpec, flag: str = "eval_test2") -> str | None:
    """PURE (AMENDMENT R2-2; xmas02 9): why evaluation flag ``flag`` cannot run on ``spec``'s
    map (another map's flag, or none), else None."""
    if spec.eval_flag != flag or not spec.eval_suffixes:
        owners = " / ".join(sorted(m.name for m in MAPS.values() if m.eval_flag == flag))
        return f"{EVAL_FLAGS[flag]} is {owners}'s only, not {spec.name}'s"
    return None


def eval_part_refusal(spec: MapSpec, sid: str, spots: frozenset[int] | None,
                      flag: str = "eval_test2") -> str | None:  # fmt: skip
    """PURE: why the part (session ``sid``, ``spots``) is NOT one the map's evaluation (``flag``)
    labels or packs, else None. gef_fild10 (``--eval-test2``, gef10-eval.md AMENDMENT R2-2): round
    1's spent TEST (gef10-detector.md 13r) and round 3's TEST3 stay refused; the NAME must end in a
    TEST2 suffix (a9, a10, a11, w3). xmas_dun02 (``--eval-test``, xmas02-detector.md 9): the NAME
    must be one of TEST's (xw5, xp1, X2); FIT and TRAIN are refused."""
    why = eval_map_refusal(spec, flag)
    if why is not None:
        return why
    if spec.test_spent and spec.is_round1_test(sid, spots):
        return "round 1's TEST is spent (gef10-detector.md 13r)"
    if any(sid.endswith(s) for s in spec.test3_suffixes):
        return "round 3's TEST3 (gef10-round3.md 2)"
    if not any(sid.endswith(s) for s in spec.eval_suffixes):
        return (f"not a {EVAL_NOUN[flag]} part (a name ending in "
                f"{', '.join(spec.eval_suffixes)})")  # fmt: skip
    return None


def eval_test2_refusal(spec: MapSpec, sid: str, spots: frozenset[int] | None) -> str | None:
    """PURE (gef10-eval.md AMENDMENT R2-2, ``--eval-test2``): eval_part_refusal's gef_fild10
    rule."""
    return eval_part_refusal(spec, sid, spots, "eval_test2")


def refuse_unless_eval(spec: MapSpec, sid: str, spots: frozenset[int] | None, name: str,
                       flag: str = "eval_test2") -> None:  # fmt: skip
    why = eval_part_refusal(spec, sid, spots, flag)
    if why is not None:
        raise SystemExit(f"{name}: {why}: refused ({EVAL_FLAGS[flag]})")


def occluders(spec: MapSpec) -> olf.Occluders:
    """The map's RSW models, and with ``spec.terrain`` its GAT's terrain occluders (4f)."""
    terrain = None
    if spec.terrain:
        from poring_dataset.camera import GAT_DIR

        terrain = olf.TerrainOccluders(GAT_DIR / f"{spec.name}.gat")
    return olf.Occluders(spec.rsw, spec.models, spec.cells, terrain=terrain)


def terrain_report(rows: Sequence[dict[str, Any]], alone: bool,
                   t_h: float) -> dict[str, Any]:  # fmt: skip
    """PURE (xmas02-detector.md 4f / 4e, FIT): from ``threshold``'s fates of the map's species,
    o3h-t's T_h (the p5 of the clear kept labels that are also clear of terrain at the rule's
    step), the adoption test at that step (orc_labels_fix.terrain_test) on 4e's own set (clear of
    every model box, the fit passing, no 2b / 2c / engaged / facing_unknown, and ``alone``:
    uncrowded), the same counts at the REPORTED steps (never chosen from), and the rule it
    chooses: ``o3h-t`` when adopted (its T_h), else ``o3h`` (``t_h``, the models' set)."""
    pop = [r for r in rows if not r["under"] and r["pre"] is None and r["fail"] is None
           and not (alone and r.get("crowded"))]  # fmt: skip
    pairs = [(float(r["ncc"]), r.get("terrain_rise")) for r in pop]
    step = olf.TERRAIN_STEP
    clear_t = [n for n, rise in pairs if rise is None or rise < step]
    t_h_t = percentile(clear_t, T_H_PERCENTILE) if clear_t else None
    test = olf.terrain_test(pairs, step)
    adopt = bool(test["adopt"]) and t_h_t is not None
    by_species: dict[str, dict[str, int]] = {}
    for r in rows:
        c = by_species.setdefault(str(r["mob"]), {"fates": 0, "under_terrain": 0,
                                                  "under_terrain_only": 0})  # fmt: skip
        c["fates"] += 1
        c["under_terrain"] += bool(r.get("terrain"))
        c["under_terrain_only"] += bool(r.get("terrain")) and not r["under"]
    return {
        "what": "4f: o3h-t (o3h with the GAT's raised cells south of a label as occluders) vs "
                "o3h; the adoption test on 4e's set: under terrain vs the rest",
        "step": step, "adoption_test": test,
        "reported_steps": {str(s): olf.terrain_test(pairs, s) for s in olf.TERRAIN_REPORT_STEPS},
        "o3h_t_tau": t_h_t, "o3h_tau": t_h,
        "clear_kept_clear_of_terrain": len(clear_t),
        "rule": olf.TERRAIN_OCCLUSION if adopt else "o3h",
        "rule_tau": t_h_t if adopt else t_h,
        "per_species": dict(sorted(by_species.items())),
    }  # fmt: skip


def scored_rows(rows: Sequence[dict[str, Any]], rule: str) -> list[dict[str, Any]]:
    """PURE (4f): the check rows a rule SCORES. o3h scores every row; o3h-t drops a label under
    terrain (and no model) whose fit failed (the row's ``o3h_t``). A map without terrain: all."""
    if rule == "o3h":
        return list(rows)
    return [r for r in rows if r.get("o3h_t", True)]


# --- 4b: 1d on FIT ----------------------------------------------------------------------------


def _offset_frame(ref: qa_export.JpegRef) -> tuple[list[tuple[int, int, dict[int, float]]], str]:
    sess, occl = olf._JOB["sess"], olf._JOB["occluders"]
    found = olf.walker_samples(sess, ref.t_mono_ns, list(COARSE_MS), occl)
    if not found:
        return [], "no_walker"
    bgr = read_png(ref)
    if not sess.layout_ok(bgr):
        return [], "ui_layout_mismatch"
    out = []
    for gid, by in found.items():
        errs = {}
        for ms, (e, pred) in by.items():
            bo = occ.best_offset(bgr, sess.lab.sheets(e.job), pred, olf.SEARCH_PX)
            if bo is not None:
                errs[ms] = float(np.hypot(bo[1], bo[2]))
        out.append((ref.frame_id, gid, errs))
    return out, "sampled"


def _offset_fine(job: tuple[qa_export.JpegRef, list[int]]) -> list[tuple[int, dict[int, float]]]:
    ref, gids = job
    sess, occl = olf._JOB["sess"], olf._JOB["occluders"]
    bgr = read_png(ref)
    out: dict[int, dict[int, float]] = defaultdict(dict)
    for ms in olf._JOB["fine"]:
        found = olf.walkers_at(sess, ref.t_mono_ns, ms, occl)
        for gid in gids:
            got = found.get(gid)
            if got is None or got[1] is None:
                continue
            bo = occ.best_offset(bgr, sess.lab.sheets(got[0].job), got[1], olf.SEARCH_PX)
            if bo is not None:
                out[gid][ms] = float(np.hypot(bo[1], bo[2]))
    return list(out.items())


def cmd_offset(a: argparse.Namespace) -> dict[str, Any]:
    spec = MAPS[a.map]
    occl = occluders(spec)
    errs: dict[int, list[float]] = defaultdict(list)
    per_part: dict[str, Any] = {}
    samples: list[tuple[RecSession, qa_export.JpegRef, int, dict[int, float]]] = []
    role = "not_test" if a.diagnostic else "fit"  # --diagnostic: any non-TEST part (9b)
    for p in a.parts:  # by NAME before anything is read, then by the manifest's id
        refuse_part(spec, p, role)
    sessions = [RecSession.open(p, spec, a.layout_templates) for p in a.parts]
    for sess in sessions:  # never frozen (9b)
        refuse(sess, role)
    for sess in sessions:  # the coarse sweep: still from the sweep's edge (1,000 ms) to t
        refs = sess.candidates_at(SWEEP_MAX_MS)
        olf._JOB.update(sess=sess, occluders=occl, walkers=spec.walkers, reader=read_png)
        why: Counter[str] = Counter()
        n = 0
        ref_of = {r.frame_id: r for r in refs}
        for rows, w in olf.run_parallel(_offset_frame, refs, a.workers):
            why[w] += 1
            for fid, gid, by in rows:
                n += 1
                samples.append((sess, ref_of[fid], gid, by))
                for ms, v in by.items():
                    errs[ms].append(v)
        per_part[sess.name] = {"frames": len(sess.refs), "candidates": len(refs),
                               "dropped": dict(sorted(sess.dropped.items())),
                               "frames_by_outcome": dict(why), "samples": n}  # fmt: skip
    curve = {ms: round(statistics.median(errs[ms]), 3) if errs[ms] else None
             for ms in COARSE_MS}  # fmt: skip
    best_coarse = olf.pick_offset(curve)
    result: dict[str, Any] = {
        "what": "4b: 1d, the packet -> frame offset on the recorder path (RDP bus, 1 fps PNG)",
        "map": spec.name, "parts": [s.name for s in sessions], "measured_at": olf.now_ict(),
        "commit": olf.git_head(), "walkers": list(spec.walkers), "samples": len(samples),
        "sweep_ms": [COARSE_MS[0], COARSE_MS[-1]], "amendment": "A (2026-10-24 18:35:20 ICT)",
        "diagnostic": bool(a.diagnostic),
        "per_part": per_part, "curve_coarse_median_px": {str(k): v for k, v in curve.items()},
        "curve_coarse_n": {str(k): len(errs[k]) for k in COARSE_MS},
        "best_coarse_ms": best_coarse,
    }  # fmt: skip
    stop = None
    if len(samples) < MIN_WALKER_SAMPLES:
        stop = f"{len(samples)} walker samples < {MIN_WALKER_SAMPLES}"
    elif best_coarse is None or best_coarse in (COARSE_MS[0], COARSE_MS[-1]):
        stop = f"the best coarse offset {best_coarse} is at the sweep's edge"
    if stop is not None:
        result.update({"STOP": stop, "offset_ms": None})
        return result
    fine = [ms for ms in sweep_fine(best_coarse) if ms not in COARSE_MS]
    by_sess: dict[int, list[tuple[qa_export.JpegRef, int]]] = defaultdict(list)
    for sess, ref, gid, _by in samples:
        by_sess[id(sess)].append((ref, gid))
    for sess in sessions:
        jobs: dict[int, tuple[qa_export.JpegRef, list[int]]] = {}
        for ref, gid in by_sess.get(id(sess), []):
            jobs.setdefault(ref.frame_id, (ref, []))[1].append(gid)
        olf._JOB.update(sess=sess, occluders=occl, walkers=spec.walkers, fine=fine)
        for rows in olf.run_parallel(_offset_fine, list(jobs.values()), a.workers):
            for _gid, by in rows:
                for ms, v in by.items():
                    errs[ms].append(v)
    full = {ms: round(statistics.median(errs[ms]), 3) if errs[ms] else None
            for ms in sorted(set(COARSE_MS) | set(fine))}  # fmt: skip
    best = olf.pick_offset({ms: full[ms] for ms in sweep_fine(best_coarse)})
    species: Counter[str] = Counter()
    for sess, ref, gid, _by in samples:
        ent = next((e for e in sess.lab.timeline.frame_world(ref.t_mono_ns).entities
                    if e.gid == gid), None)  # fmt: skip
        species[str(ent.job if ent is not None else "?")] += 1
    result.update({
        "curve_median_px": {str(k): v for k, v in full.items()},
        "curve_n": {str(k): len(errs[k]) for k in full},
        "curve_p25_p75_px": {str(k): [round(float(np.percentile(errs[k], 25)), 2),
                                      round(float(np.percentile(errs[k], 75)), 2)]
                             for k in full if errs[k]},
        "samples_by_species": dict(sorted(species.items())),
        "units": len({(id(s), g) for s, _r, g, _b in samples}),
        "offset_ms": best, "occluders": occl.provenance(),
    })  # fmt: skip
    return result


# --- 4e: T_h on FIT (and 4c's reported anchors) ------------------------------------------------


def labeler_for(sess: RecSession, params: dict[str, Any], occl: olf.Occluders,
                occlusion: str, fit_all: bool = False,
                variant: str | None = None) -> olf.FixLabeler:  # fmt: skip
    """The label stack: fix 2 + Amendment B; gef10 (4h): the engaged ``variant`` (else the
    parameters' frozen ``engaged_variant``, else E0); xmas02: its fixed variant (E0, D11), on
    gef10's stack (Amendments B and C)."""
    if not sess.spec.labels_engaged_rule():
        fl = olf.FixLabeler(sess.lab, params, occl, rule="fix2", occlusion=occlusion,
                            fit_all=fit_all, map_name=sess.spec.name)  # fmt: skip
        fl.facing = sess.facing_rule("fix2")  # Amendment B
        return fl
    v = variant or str(params.get("engaged_variant") or sess.spec.engaged_fixed or "E0")
    if sess.spec.engaged_fixed is not None and v != sess.spec.engaged_fixed:
        raise SystemExit(f"{sess.spec.name}: engaged variant {v!r}; its rule is "
                         f"{sess.spec.engaged_fixed} ({sess.spec.plan} 4i)")  # fmt: skip
    fl = EngagedLabeler(sess.lab, params, occl, rule="fix2", occlusion=occlusion,
                        fit_all=fit_all, map_name=sess.spec.name, variant=v)  # fmt: skip
    fl.facing = sess.facing_rule("fix2", v)
    return fl


def _fates_frame(ref: qa_export.JpegRef) -> tuple[list[dict[str, Any]], str]:
    sess: RecSession = olf._JOB["sess"]
    fl: olf.FixLabeler = olf._JOB["labeler"]
    bgr = read_png(ref)
    if not sess.layout_ok(bgr):
        return [], "ui_layout_mismatch"
    ff = fl.frame(ref.t_mono_ns, bgr)
    if ff is None or not ff.applies:
        return [], "no_scene"
    models: dict[int, str | None] = {}
    if any(f.under for f in ff.fates):  # REPORTED: which model the FITTED box falls under
        scene = sess.scene(sess.lab.timeline.frame_world(ref.t_mono_ns - fl.offset_ns))
        names = {idx: name for idx, name, _c, _a in fl.occluders.models}
        for f in ff.fates:
            if f.under and f.raw is not None and scene is not None:
                hit = fl.occluders.hit(scene, f.raw)
                models[f.gid] = None if hit is None else names.get(hit)
    rows = [{"frame_id": ref.frame_id, "gid": f.gid, "mob": f.mob, "under": f.under,
             "pre": f.pre, "fail": f.fail, "ncc": None if f.fit is None else round(f.fit[0], 4),
             "dx": None if f.fit is None else f.fit[1], "dy": None if f.fit is None else f.fit[2],
             "w": None if f.raw is None else round(f.raw[2] - f.raw[0], 1),
             "h": None if f.raw is None else round(f.raw[3] - f.raw[1], 1),
             "state": f.state, "facing_from": f.facing_from, "model": models.get(f.gid),
            "box": None if f.raw is None else [round(v, 1) for v in f.raw],
            "crowded": getattr(fl, "crowded", {}).get(f.gid)}
            for f in ff.fates]  # fmt: skip
    if getattr(fl.occluders, "terrain", None) is not None:  # 4f: o3h-t's evidence (REPORTED)
        tf = {f.gid: f for f in ff.fates}
        for row in rows:
            f = tf[row["gid"]]
            row.update(terrain=f.terrain, terrain_rise=None if f.terrain_rise is None
                       else round(f.terrain_rise, 2))  # fmt: skip
    return rows, "labelled"


def box_geometry(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """PURE (REPORTED): the fitted boxes' width / height (px) of kept labels clear of every model
    box: n, median, p10, p90 of each."""
    ws = [float(r["w"]) for r in rows if r.get("w") is not None]
    hs = [float(r["h"]) for r in rows if r.get("h") is not None]
    if not ws or not hs:
        return {"n": 0}
    return {
        "n": len(ws),
        "w": {q: percentile(ws, v) for q, v in (("p10", 10), ("p50", 50), ("p90", 90))},
        "h": {q: percentile(hs, v) for q, v in (("p10", 10), ("p50", 50), ("p90", 90))},
    }


def provisional(offset: dict[str, Any], spec: MapSpec) -> dict[str, Any]:
    return {"offset_ms": float(offset["offset_ms"]), "anchors_px": {},
            "fit_px": {str(m): spec.fit_px for m in spec.species}, "tau": olf.TAU}  # fmt: skip


def cmd_threshold(a: argparse.Namespace) -> dict[str, Any]:
    spec = MAPS[a.map]
    for p in a.parts:  # by NAME before anything is read (then by the manifest's id)
        refuse_part(spec, p, "fit")
    if (a.offset is None) == (a.proposed_offset_ms is None):
        raise SystemExit("one of --offset (a measured 1d) or --proposed-offset-ms (9b)")
    if a.offset is not None:
        offset = json.loads(a.offset.read_text())
        if offset.get("offset_ms") is None or offset.get("diagnostic"):
            raise SystemExit("1d stopped (or a diagnostic): no offset to measure T_h at")
    else:
        offset = {"offset_ms": float(a.proposed_offset_ms), "proposal": a.proposal}
    params = provisional(offset, spec)
    occl = occluders(spec)
    sessions = [RecSession.open(p, spec, a.layout_templates) for p in a.parts]
    for sess in sessions:
        refuse(sess, "fit")
    rows: list[dict[str, Any]] = []
    per_part: dict[str, Any] = {}
    for sess in sessions:
        refs = sess.candidates_at(params["offset_ms"])
        olf._JOB.update(sess=sess, labeler=labeler_for(sess, params, occl, "1c", fit_all=True))
        why: Counter[str] = Counter()
        n0 = len(rows)
        for r, w in olf.run_parallel(_fates_frame, refs, a.workers):
            why[w] += 1
            rows += [{**x, "part": sess.name} for x in r]
        per_part[sess.name] = {"frames": len(sess.refs), "candidates": len(refs),
                               "dropped": dict(sorted(sess.dropped.items())),
                               "frames_by_outcome": dict(why), "fates": len(rows) - n0}  # fmt: skip
    if getattr(a, "rows", None) is not None:  # the per-label fates (REPORTED diagnostics)
        a.rows.write_text(json.dumps(rows) + "\n")
    mine = [r for r in rows if r["mob"] in spec.species]
    # gef10 Amendment B (2026-10-25 21:24:48): T_h's set also leaves out labels whose predicted
    # box touches another unit's (gef10's label stack records it: gef10, xmas02; payf07 nothing)
    alone = spec.labels_engaged_rule()
    clear = [r["ncc"] for r in mine if not r["under"] and r["pre"] is None and r["fail"] is None
             and not (alone and r.get("crowded"))]  # fmt: skip
    under = [r["ncc"] for r in mine if r["under"] and r["pre"] is None and r["fail"] is None]
    if not clear:
        raise SystemExit("4e: no clear kept label on FIT")
    t_h = percentile(clear, T_H_PERCENTILE)

    def dist(v: Sequence[float]) -> dict[str, Any]:
        return {"n": len(v), **({f"p{q}": percentile(v, q) for q in (5, 25, 50, 75, 95)}
                                if v else {})}  # fmt: skip

    per_species = {}
    for m in spec.species:
        rs = [r for r in mine if r["mob"] == m]
        per_species[str(m)] = {
            "fates": len(rs),
            "clear_kept": dist([r["ncc"] for r in rs if not r["under"] and r["pre"] is None
                                and r["fail"] is None]),
            "clear_kept_alone": dist([r["ncc"] for r in rs if not r["under"] and r["pre"] is None
                                      and r["fail"] is None and not r.get("crowded")]),
            "crowded_share_of_clear_kept": round(
                sum(1 for r in rs if not r["under"] and r["pre"] is None and r["fail"] is None
                    and r.get("crowded")) / max(1, sum(1 for r in rs if not r["under"]
                                                       and r["pre"] is None and r["fail"] is None)),
                4) if alone else None,
            "under_fit_passes": dist([r["ncc"] for r in rs if r["under"] and r["pre"] is None
                                      and r["fail"] is None]),
            "under_share": round(sum(r["under"] for r in rs) / len(rs), 4) if rs else None,
            "box_px_clear_kept": box_geometry([r for r in rs if not r["under"] and r["pre"] is None
                                               and r["fail"] is None]),
            "under_by_model": dict(Counter(str(r.get("model")) for r in rs if r["under"]
                                           ).most_common(8)),
            "excluded_pre": dict(Counter(str(r["pre"]) for r in rs if r["pre"] is not None)),
            "fails": dict(Counter(f"{'under' if r['under'] else 'clear'}:{r['fail']}"
                                  for r in rs if r["fail"] is not None and r["pre"] is None)),
            # 4c: the median fit offset of clear kept labels (REPORTED; no anchor is applied)
            "fit_offset_median_px": [statistics.median(r["dx"] for r in rs if r["dx"] is not None
                                                       and not r["under"] and r["fail"] is None
                                                       and r["pre"] is None)
                                     if any(r["dx"] is not None and not r["under"] and
                                            r["fail"] is None and r["pre"] is None for r in rs)
                                     else None,
                                     statistics.median(r["dy"] for r in rs if r["dy"] is not None
                                                       and not r["under"] and r["fail"] is None
                                                       and r["pre"] is None)
                                     if any(r["dy"] is not None and not r["under"] and
                                            r["fail"] is None and r["pre"] is None for r in rs)
                                     else None],
        }  # fmt: skip
    return {
        "what": "4e: o3h's T_h = the pooled p5 of the fit NCC of FIT's kept labels CLEAR of every "
                "model box (fix 2, 2b / 2c, the fit at +-6 px, tau, not at the edge)",
        "map": spec.name, "parts": [s.name for s in sessions], "measured_at": olf.now_ict(),
        "commit": olf.git_head(), "offset_ms": params["offset_ms"], "o3h_tau": t_h,
        "offset_source": offset.get("proposal") or str(a.offset),
        "clear_kept": dist(clear), "under_fit_passes": dist(under),
        "t_h_set": "clear of every model box, not engaged" + (
            ", predicted box touching no other unit's (gef10 Amendment B)" if alone else ""),
        "clear_kept_any_crowding": dist([r["ncc"] for r in mine if not r["under"]
                                         and r["pre"] is None and r["fail"] is None]),
        "under_below_t_h": sum(1 for v in under if v < t_h), "per_species": per_species,
        "per_part": per_part, "other_species_fates": len(rows) - len(mine),
        "under_share_pooled": round(sum(r["under"] for r in mine) / len(mine), 4) if mine else None,
        "under_by_model_pooled": dict(Counter(str(r.get("model")) for r in mine if r["under"]
                                              ).most_common(12)),
        "fates_by_part_species": {pt: dict(Counter(str(r["mob"]) for r in mine if r["part"] == pt))
                                  for pt in per_part},
        **({"terrain": terrain_report(mine, alone, t_h)} if occl.terrain is not None else {}),
    }  # fmt: skip


def cmd_freeze(a: argparse.Namespace) -> dict[str, Any]:
    spec = MAPS[a.map]
    th = json.loads(a.threshold.read_text())
    if a.proposed or a.decision:  # 10a: 1d stopped; a proposed offset (NOT frozen), or the
        if a.offset is not None or "offset_source" not in th:  # decision that adopts it
            raise SystemExit("--proposed / --decision take a T_h measured at a proposed offset")
        off = {"offset_ms": th["offset_ms"], "parts": [th["offset_source"]]}
        if a.decision:
            status = "FROZEN"
            off_file: dict[str, Any] = {"offset_file": None, "offset_sha256": None,
                                        "decision": a.decision}  # fmt: skip
        else:
            status = f"PROPOSED_NOT_FROZEN: {th['offset_source']}"
            off_file = {"offset_file": None, "offset_sha256": None}
    else:
        off = json.loads(a.offset.read_text())
        if off.get("offset_ms") is None or off.get("diagnostic") or \
                float(th["offset_ms"]) != float(off["offset_ms"]):  # fmt: skip
            raise SystemExit("T_h must be measured at 1d's frozen offset")
        status = "FROZEN"
        off_file = {"offset_file": str(a.offset), "offset_sha256": olf.sha256_file(a.offset)}
    occl = occluders(spec)
    rule, rule_tau = "o3h", float(th["o3h_tau"])
    if occl.terrain is not None:  # 4f: the rule the FIT adoption test chose, and its T_h
        terr = th.get("terrain")
        if terr is None:
            raise SystemExit(f"{a.threshold}: no 4f terrain report (measured without terrain)")
        rule, rule_tau = str(terr["rule"]), float(terr["rule_tau"])
        if (rule == "o3h-t") != spec.labels.endswith("-o3h-t"):  # Amendment C: the name says it
            raise SystemExit(f"4f chose {rule}, but the labels are named {spec.labels!r}: the "
                             "freeze's amendment renames them first (xmas02-detector.md "
                             "Amendment C)")  # fmt: skip
    extra: dict[str, Any] = {}
    if spec.engaged_labels:  # gef10 4h / 4g: the engaged variant (4h's selection file) + D8
        if a.engaged is None:
            raise SystemExit(f"{spec.name}: --engaged SELECTION.json (4h's FIT selection)")
        sel = json.loads(a.engaged.read_text())
        variant = a.engaged_variant or sel["chosen"]
        if variant not in ENGAGED_VARIANTS:
            raise SystemExit(f"engaged variant {variant!r}: one of {ENGAGED_VARIANTS}")
        if float(sel["t_h"]) != rule_tau or float(sel["offset_ms"]) != float(
                th["offset_ms"]):  # fmt: skip
            raise SystemExit("the engaged selection must be measured at the same 1d and T_h")
        extra = {
            "engaged_variant": variant,
            "engaged_selection": str(a.engaged),
            "engaged_selection_sha256": olf.sha256_file(a.engaged),
            "engaged_chosen_by_fit": sel["chosen"],
            "dying_in_view": spec.dying_rule,
        }
    elif spec.engaged_fixed is not None:  # xmas02 4i (D11): a fixed variant, no FIT selection
        if a.engaged is not None or a.engaged_variant not in (None, spec.engaged_fixed):
            raise SystemExit(f"{spec.name}: engaged units are {spec.engaged_fixed} by "
                             f"{spec.plan} 4i: no --engaged file, no other variant")  # fmt: skip
        extra = {"engaged_variant": spec.engaged_fixed,
                 "engaged_fixed_by": f"{spec.plan} 4i (D11)",
                 "dying_in_view": spec.dying_rule}  # fmt: skip
    return {
        "labels": spec.labels, "status": status, "plan": f"{spec.plan} 4",
        "map": spec.name, **extra,
        "map_cells": list(spec.cells), "frozen_at": olf.now_ict(), "commit": olf.git_head(),
        "measured_on": off["parts"], "offset_ms": float(off["offset_ms"]), "anchors_px": {},
        "fit_px": {str(m): spec.fit_px for m in spec.species}, "tau": olf.TAU, "k": olf.K,
        "search_px": olf.SEARCH_PX, "o3h_tau": rule_tau, "facing_rule": "fix2",
        "occlusion": rule, "occluders": occl.provenance(),
        **({"occlusion_chosen_by": "4f's adoption test (the threshold file's terrain.rule)"}
           if occl.terrain is not None else {}),
        **off_file,
        "threshold_file": str(a.threshold), "threshold_sha256": olf.sha256_file(a.threshold),
    }  # fmt: skip


def load_params(path: Path, spec: MapSpec) -> dict[str, Any]:
    p = json.loads(path.read_text())
    if p.get("labels") != spec.labels or p.get("map") != spec.name:
        raise SystemExit(f"{path}: not a {spec.labels} parameter file for {spec.name}")
    return p


def frozen_occluders(params: dict[str, Any], spec: MapSpec) -> olf.Occluders:
    occl = occluders(spec)
    prov = occl.provenance()
    if prov["rsw_sha256"] != params["occluders"]["rsw_sha256"] or \
            occl.files != params["occluders"]["model_files_sha256"]:  # fmt: skip
        raise SystemExit("the RSW / RSM files differ from the frozen ones")
    if (prov.get("terrain") or {}).get("gat_sha256") != \
            (params["occluders"].get("terrain") or {}).get("gat_sha256"):  # fmt: skip
        raise SystemExit("4f: the map's terrain (GAT) differs from the frozen one")
    return occl


# --- gef10 4h: the ENGAGED variants on FIT (the selection) -----------------------------------


def _engaged_frame(ref: qa_export.JpegRef) -> tuple[list[dict[str, Any]], list[dict[str, Any]],
                                                    str]:  # fmt: skip
    """One FIT frame under every variant: the engaged units' fates (rows) and the frame's
    wholeness (monsters + 4g, the T_h floor on kept labels clear of a model). A frame with no
    engaged unit at tw (packets only) is not read."""
    sess: RecSession = olf._JOB["sess"]
    labelers: dict[str, EngagedLabeler] = olf._JOB["labelers"]
    t_h: float = olf._JOB["t_h"]
    first = next(iter(labelers.values()))
    tw = ref.t_mono_ns - first.offset_ns
    _replay, world, states, _rules = sess.lab.timeline.at_world(tw)
    times = first.facing.times  # type: ignore[attr-defined]
    if not any(e.objtype == 5 and not e.hidden and is_engaged(times, e.gid, tw)
               for e in world.entities):  # fmt: skip
        return [], [], "no_engaged"
    bgr = read_png(ref)
    if not sess.layout_ok(bgr):
        return [], [], "ui_layout_mismatch"
    scene = sess.scene(world)
    if scene is None:
        return [], [], "no_scene"
    dying = [(st.x, st.y) for st in states if st.state == "dying"] if sess.spec.dying_rule else []
    frame_ex = frame_exclusions(world, scene, sess.lab.size, sess.spec.species,
                                sess.spec.species, world.aid, dying)  # fmt: skip
    rows: list[dict[str, Any]] = []
    frames: list[dict[str, Any]] = []
    for v, fl in labelers.items():
        ff = fl.frame(ref.t_mono_ns, bgr)
        if ff is None or not ff.applies:
            return [], [], "no_scene"
        n_eng = 0
        for f in ff.fates:
            if not f.facing_from.startswith(ENGAGED_TAG):
                continue
            n_eng += 1
            rows.append({"variant": v, "frame_id": ref.frame_id, "gid": f.gid, "mob": f.mob,
                         "under": f.under, "pre": f.pre, "fail": f.fail,
                         "ncc": None if f.fit is None else round(f.fit[0], 4),
                         "dx": None if f.fit is None else f.fit[1],
                         "dy": None if f.fit is None else f.fit[2],
                         "w": None if f.raw is None else round(f.raw[2] - f.raw[0], 1),
                         "h": None if f.raw is None else round(f.raw[3] - f.raw[1], 1),
                         "state": f.state, "facing_from": f.facing_from})  # fmt: skip
        floor_ok = all(k.ncc >= t_h for k in ff.kept)  # o3h already gated the under-box ones
        frames.append({"variant": v, "frame_id": ref.frame_id, "engaged_fates": n_eng,
                       "kept": len(ff.kept), "excluded": len(ff.excluded),
                       "whole": not ff.excluded and floor_ok and not frame_ex,
                       "frame_exclusions": frame_ex})  # fmt: skip
    return rows, frames, "sampled"


def cmd_engaged(a: argparse.Namespace) -> dict[str, Any]:
    """4h's selection on FIT: E1 / E2 / E3 at a 1d and a T_h (measured or proposed: 13)."""
    spec = MAPS[a.map]
    if not spec.engaged_labels:
        raise SystemExit(f"{spec.name}: its rule does not label engaged units")
    for p in a.parts:  # by NAME before anything is read (then by the manifest's id)
        refuse_part(spec, p, "fit")
    for v in a.variants:
        if v not in ENGAGED_VARIANTS[1:]:
            raise SystemExit(f"--variants: E1 / E2 / E3, not {v!r}")
    params = {**provisional({"offset_ms": a.offset_ms}, spec), "o3h_tau": float(a.o3h_tau)}
    occl = occluders(spec)
    sessions = [RecSession.open(p, spec, a.layout_templates) for p in a.parts]
    for sess in sessions:
        refuse(sess, "fit")
    rows: list[dict[str, Any]] = []
    frames: list[dict[str, Any]] = []
    per_part: dict[str, Any] = {}
    for sess in sessions:
        refs = sess.candidates_at(float(a.offset_ms))
        labelers = {v: labeler_for(sess, params, occl, "o3h", variant=v) for v in a.variants}
        olf._JOB.update(sess=sess, labelers=labelers, t_h=float(a.o3h_tau))
        why: Counter[str] = Counter()
        n0, f0 = len(rows), len(frames)
        for r, fr, w in olf.run_parallel(_engaged_frame, refs, a.workers):
            why[w] += 1
            rows += [{**x, "part": sess.name} for x in r]
            frames += [{**x, "part": sess.name} for x in fr]
        per_part[sess.name] = {"frames": len(sess.refs), "candidates": len(refs),
                               "dropped": dict(sorted(sess.dropped.items())),
                               "frames_by_outcome": dict(why), "engaged_rows": len(rows) - n0,
                               "frame_rows": len(frames) - f0}  # fmt: skip
    sel = engaged_selection(rows, float(a.o3h_tau), tuple(a.variants))
    per_variant_species: dict[str, Any] = {}
    for v in a.variants:
        rs = [r for r in rows if r["variant"] == v]
        per_variant_species[v] = {}
        for m in sorted({int(r["mob"]) for r in rs}):
            mr = [r for r in rs if int(r["mob"]) == m]
            kept = [r for r in mr if r["pre"] is None and r["fail"] is None
                    and r["ncc"] is not None and float(r["ncc"]) >= float(a.o3h_tau)]  # fmt: skip
            nccs = [float(r["ncc"]) for r in mr if r["ncc"] is not None and r["pre"] is None]
            per_variant_species[v][str(m)] = {
                "fates": len(mr), "kept": len(kept),
                "pre": dict(Counter(str(r["pre"]) for r in mr if r["pre"] is not None)),
                "fail": dict(Counter(str(r["fail"]) for r in mr if r["pre"] is None
                                     and r["fail"] is not None)),
                "ncc_median": round(statistics.median(nccs), 3) if nccs else None,
                "below_floor": sum(1 for r in mr if r["pre"] is None and r["fail"] is None
                                   and r["ncc"] is not None and float(r["ncc"]) < float(a.o3h_tau)),
                "kept_median_abs_dxdy": [statistics.median(abs(r["dx"]) for r in kept),
                                         statistics.median(abs(r["dy"]) for r in kept)]
                if kept else None,
                "kept_box_px": box_geometry(kept),
                "kept_states": dict(Counter(str(r["state"]) for r in kept)),
            }  # fmt: skip
    whole = {v: sum(1 for f in frames if f["variant"] == v and f["whole"]) for v in a.variants}
    if a.rows is not None:
        a.rows.write_text(json.dumps({"rows": rows, "frames": frames}) + "\n")
    return {
        "what": "4h: the ENGAGED variants on FIT (frames with an engaged unit at tw only)",
        "map": spec.name, "parts": [s.name for s in sessions], "measured_at": olf.now_ict(),
        "commit": olf.git_head(), "offset_ms": float(a.offset_ms), "t_h": float(a.o3h_tau),
        "offset_source": a.offset_source, "variants": list(a.variants),
        **sel, "per_variant_species": per_variant_species,
        "frames_with_engaged_read": len({(f["part"], f["frame_id"]) for f in frames}),
        "whole_frames_by_variant": whole, "per_part": per_part,
    }  # fmt: skip


# --- gef10 ROUND 2: the pickup-notice exclusion in C1 (gef10-round2.md) ------------------------

C1_RULES = {
    "round1": "the frozen check (gef10-detector.md 5; payf07-detector.md 5): the static UI "
              "rectangles only",
    "round2": "round1 + NOTICE (gef10-round2.md): a standing label whose PREDICTED box overlaps "
              "(area > 0) a pickup notice detected in that frame (gef10_r2_measure.find_notices "
              "on its top rows) is not scored (reason 'notice'); the maps whose MapSpec.c1_rules "
              "list it (gef_fild10; xmas_dun02, its only rule: xmas02-detector.md 4h / 5)",
}  # fmt: skip
# T-8 (xmas02-detector.md 4h / 5): round 2's notice rule on another map -- the notice band and the
# detector are gef_fild10's (measured there: gef10-round2-measure.md 2), the UI windows the
# session's (session_ui_rects: the 2026-11-05 chat window)
NOTICE_MEASURED_ON = "gef_fild10"
NOTICE = "notice"  # round 2's exclusion reason (per species: "notice:<job>")
NOTICE_NEAR_PX = 16.0  # REPORTED only: a scored box this close to a notice (C1's UI margin)


def notice_hits(box: Sequence[float], notices: Sequence[Sequence[float]]) -> bool:
    """PURE (round 2): ``box`` (x0, y0, x1, y1) overlaps a notice box by any area > 0."""
    return any(min(box[2], n[2]) > max(box[0], n[0]) and min(box[3], n[3]) > max(box[1], n[1])
               for n in notices)  # fmt: skip


@dataclass
class NoticeRule:
    """Round 2's C1 exclusion as orc_labels_fix._check_rows' ``frame_rule``: the notices of the
    frame's top rows (found once per frame read), every candidate whose PREDICTED box overlaps
    one dropped as ``notice`` (standing ones and the under-model ones before their fit), the
    frame's notices kept in ``last`` for the rows' REPORTED ``notice_near``."""

    last: list[tuple[float, float, float, float]] = field(default_factory=list)

    def __call__(self, bgr: npt.NDArray[np.uint8], cands: list[Any], under: list[Any] | None,
                 dropped: Counter[str]) -> tuple[list[Any], list[Any] | None]:  # fmt: skip
        import gef10_r2_measure as r2m

        self.last = [tuple(float(v) for v in b)  # type: ignore[misc]
                     for b in r2m.find_notices(bgr[: r2m.TOP_ROWS])]  # fmt: skip
        if not self.last:
            return cands, under
        dropped["frame_with_notice"] += 1

        def keep(cs: list[Any]) -> list[Any]:
            out = []
            for c in cs:
                e, pred = c[0], c[3]
                if notice_hits(pred.box, self.last):
                    dropped[NOTICE] += 1
                    dropped[f"{NOTICE}:{e.job}"] += 1
                else:
                    out.append(c)
            return out

        return keep(cands), None if under is None else keep(under)


def _check_rows_round2(ref: qa_export.JpegRef) -> tuple[list[dict[str, Any]], Counter[str],
                                                        Counter[int]]:  # fmt: skip
    """olf._check_rows with the job's NoticeRule; each scored row of a frame with a notice gets
    ``notice_near`` (its box grown by 16 px touches one: REPORTED, not deciding)."""
    rule: NoticeRule = olf._JOB["frame_rule"]
    rule.last = []
    rows, dropped, seen = olf._check_rows(ref)
    if rule.last:
        m = NOTICE_NEAR_PX
        for r in rows:
            b = r["box"]
            r["notice_near"] = notice_hits((b[0] - m, b[1] - m, b[2] + m, b[3] + m), rule.last)
    return rows, dropped, seen


def c1_rule_refusals(spec: MapSpec, rule: str, parts: Sequence[str]) -> None:
    """Round 2's guards, before anything is read: a map is checked only under the rules of its
    MapSpec.c1_rules (T-8: ``round2`` on gef_fild10 and xmas_dun02 -- xmas_dun02's ONLY rule, its
    C1 always drops a label under a notice; ``round1`` on pay_fild07 and gef_fild10); round 2
    never reads gef_fild10's spent round-1 TEST (the watch's cells 11-14, a7, a8); TEST2 (a9-a11)
    is checked under ``round2`` only (the round-1 rule would spend it)."""
    if rule not in C1_RULES:
        raise SystemExit(f"--c1-rule: {sorted(C1_RULES)}, not {rule!r}")
    if rule not in spec.c1_rules:
        owners = " / ".join(sorted(m.name for m in MAPS.values() if rule in m.c1_rules))
        raise SystemExit(f"--c1-rule {rule}: {owners} only, not {spec.name} (its rules: "
                         f"{', '.join(spec.c1_rules)})")  # fmt: skip
    for part in parts:
        path, spots = parse_part(part)
        if rule == "round2" and spec.test_spent and spec.is_round1_test(path.name, spots):
            raise SystemExit(f"{part}: round 1's TEST is spent (13r): round 2 never reads it")
        if rule != "round2" and any(path.name.endswith(s) for s in spec.test2_suffixes):
            raise SystemExit(f"{part}: round 2's TEST2: checked under --c1-rule round2 only")


# --- 5: the check (C1 / C2 on the PREDICTION) -------------------------------------------------


def cmd_check(a: argparse.Namespace) -> dict[str, Any]:
    spec = MAPS[a.map]
    params = load_params(a.params, spec)
    diag = bool(getattr(a, "fit_diagnostic", False))
    c1_rule = str(getattr(a, "c1_rule", "round1"))
    if params.get("status") != "FROZEN" and not diag:
        raise SystemExit(f"{a.params}: {params.get('status')}: T1 runs on FROZEN parameters only")
    c1_rule_refusals(spec, c1_rule, a.parts)
    if diag:  # gef10 13: C1 on FIT under PROPOSED parameters, a DIAGNOSTIC (never T1, never 3c)
        for part in a.parts:
            path, spots = parse_part(part)
            if not spec.is_fit(path.name, spots):
                raise SystemExit(f"{part}: --fit-diagnostic reads FIT parts only")
    occl = frozen_occluders(params, spec)
    off_ms = float(params["offset_ms"])
    rule = str(params.get("occlusion", "o3h"))  # 4f: o3h, or o3h-t when the FIT test adopted it
    rules = ("o3h", olf.TERRAIN_OCCLUSION) if occl.terrain is not None else (rule,)
    rows: list[dict[str, Any]] = []
    per_part: dict[str, Any] = {}
    terrain_parts: dict[str, Any] = {}
    dropped_all: Counter[str] = Counter()
    for part in a.parts:
        sess = RecSession.open(part, spec, a.layout_templates)
        if diag and not spec.is_fit(sess.sid, sess.spots):
            raise SystemExit(f"{sess.name}: --fit-diagnostic reads FIT parts only")
        if spec.overlaps_fit(sess.sid, sess.spots) and not (a.allow_fit or diag):
            raise SystemExit(f"{sess.name}: a FIT part (the parameters' own data): --allow-fit")
        c1_rule_refusals(spec, c1_rule, [sess.name])  # by the manifest's session id too
        refs = sess.candidates_at(off_ms)
        olf._JOB.update(sess=sess, occluders=occl, offset_ms=off_ms, anchors={},
                        facing_rule=sess.facing_rule("fix2"), occlusion=rule,
                        tau=float(params["tau"]), o3h_tau=float(params["o3h_tau"]),
                        fit_px={int(k): int(v) for k, v in params["fit_px"].items()},
                        reader=read_png)  # fmt: skip
        olf._JOB.pop("frame_rule", None)  # round1: orc_labels_fix._check_rows, unchanged
        func = olf._check_rows
        if c1_rule == "round2":
            olf._JOB["frame_rule"], func = NoticeRule(), _check_rows_round2
        prow: list[dict[str, Any]] = []
        dropped: Counter[str] = Counter()
        for r, d, _sn in olf.run_parallel(func, refs, a.workers):
            prow += [{**x, "part": sess.name} for x in r]
            dropped.update(d)
        prow.sort(key=lambda r: (r["frame_id"], r["gid"]))
        summ = t1_summary(scored_rows(prow, rule), spec.species)
        if occl.terrain is not None:  # 4f: both rules, per part
            terrain_parts[sess.name] = {}
            for rl in rules:
                ts = t1_summary(scored_rows(prow, rl), spec.species)
                terrain_parts[sess.name][rl] = {"c1": ts["c1"]["pooled"],
                                                "c1_ratio": ts["c1"]["ratio"],
                                                "own_c1": own_c1_verdict(ts)}  # fmt: skip
        per_part[sess.name] = {
            "frames": len(sess.refs), "candidates": len(refs),
            "candidate_drops": dict(sorted(sess.dropped.items())),
            "dropped": {k: v for k, v in sorted(dropped.items()) if ":" not in k},
            "c1": summ["c1"]["pooled"], "c1_ratio": summ["c1"]["ratio"],
            "c1_per_species": summ["c1"]["per_species"], "c2": summ["c2"]["per_species"],
            "own_c1": own_c1_verdict(summ),
        }  # fmt: skip
        rows += prow
        dropped_all.update(dropped)
    olf._JOB.pop("frame_rule", None)
    summ = t1_summary(scored_rows(rows, rule), spec.species)

    def by_species(reason: str) -> dict[str, int]:
        return dict(sorted((k.split(":", 1)[1], v) for k, v in dropped_all.items()
                           if k.startswith(f"{reason}:")))  # fmt: skip

    rule_doc: dict[str, Any] = {"name": c1_rule, "what": C1_RULES[c1_rule]}
    if c1_rule == "round2":
        import gef10_r2_measure as r2m

        near = [r for r in rows if r.get("notice_near")]
        rule_doc.update({
            "detector": "scripts/gef10_r2_measure.py find_notices (gef10-round2-measure.md 2: "
                        "587 / 595 positives, 0 / 8,156 false)",
            "band_y0_y1_x0_x1": list(r2m.NOTICE_BAND), "top_rows_read": r2m.TOP_ROWS,
            "overlap": "the predicted box and a notice box share any area > 0",
            "excluded": dropped_all.get(NOTICE, 0), "excluded_by_species": by_species(NOTICE),
            "frames_with_notice": dropped_all.get("frame_with_notice", 0),
            "scored_rows_near_notice_16px": len(near),
            "scored_rows_near_notice_bad": sum(1 for r in near if r.get("why_low") == "bad_label"),
        })  # fmt: skip
        if spec.name != NOTICE_MEASURED_ON:  # T-8: say where the band and detector were measured
            rule_doc["notice_band_measured_on"] = NOTICE_MEASURED_ON

    if a.rows is not None:
        a.rows.write_text(json.dumps(rows) + "\n")
    motion = Counter(bool(r.get("self_moving")) for r in rows)
    if diag:
        summ = {**summ, "T1": "NOT_T1: a FIT diagnostic under PROPOSED parameters"}
        for row in per_part.values():
            row["own_c1"] = f"DIAGNOSTIC (not 3c): {row['own_c1']}"
    return {
        "diagnostic": diag, "params_status": params.get("status"),
        "what": f"5: C1 / C2 on the {spec.labels} PREDICTION (fix 2 facing, 1d, no anchor, no "
                "fit), o3h's under-box rule, 2b / 2c (engaged units excluded: E0)",
        "c1_rule": rule_doc,
        "map": spec.name, "parts": a.parts, "checked_at": olf.now_ict(),
        "commit": olf.git_head(), "params": str(a.params),
        "params_sha256": olf.sha256_file(a.params), "offset_ms": off_ms,
        "o3h_tau": params["o3h_tau"], "tau": olf.TAU, "k": olf.K,
        **summ,
        "dropped": {k: v for k, v in sorted(dropped_all.items()) if ":" not in k},
        "occluded_model_by_species": by_species("occluded_model"),
        "under_model_kept_by_species": by_species("under_model_kept"),
        "next_move_by_species": by_species(olf.NEXT_MOVE),
        "ambiguous_view_by_species": by_species(olf.AMBIGUOUS),
        "engaged_by_species": by_species(ENGAGED),
        "facing_unknown_by_species": by_species(FACING_UNKNOWN),
        "facing_agreement": olf.agreement(rows),
        "self_moving_rows": motion.get(True, 0),
        "per_part": per_part,
        **({"occlusion": rule, "terrain": {
            "what": "4f: C1 / C2 under BOTH rules from one pass (the rows' 'under' / 'o3h_t'); "
                    "the verdict above is the frozen rule's",
            "frozen_rule": rule,
            "rules": {rl: {k: v for k, v in t1_summary(scored_rows(rows, rl), spec.species).items()
                           if k in ("c1", "T1", "c2_stop")} for rl in rules},
            "rows_under_terrain_only": sum(1 for r in rows if r.get("under") == "terrain"),
            "under_terrain_kept_by_species": by_species("under_terrain_kept"),
            "occluded_terrain_by_species": by_species(olf.OCCLUDED_TERRAIN),
            "per_part": terrain_parts}} if occl.terrain is not None else {}),
    }  # fmt: skip


# --- the labels (no pixels in the output) -----------------------------------------------------


def _label_frame(ref: qa_export.JpegRef) -> dict[str, Any]:
    sess: RecSession = olf._JOB["sess"]
    fl: olf.FixLabeler = olf._JOB["labeler"]
    classes: Sequence[int] = olf._JOB["classes"]
    row: dict[str, Any] = {
        "frame_id": ref.frame_id,
        "t": ref.t_mono_ns,
        "shard": ref.shard.name,
        "offset": ref.offset,
        "size": ref.size,
        "spot": sess.spot(ref.t_mono_ns),
    }
    bgr = read_png(ref)
    if not sess.layout_ok(bgr):
        return {**row, "excluded_frame": ["ui_layout_mismatch"], "whole": False}
    ff = fl.frame(ref.t_mono_ns, bgr)
    if ff is None or not ff.applies:
        return {**row, "excluded_frame": ["no_scene"], "whole": False}
    tw = ref.t_mono_ns - fl.offset_ns
    dying: list[tuple[float, float]] = []
    if sess.spec.dying_rule:  # gef10 4g (D8): the die animations at tw, from ONE replay
        _replay, world, states, _rules = sess.lab.timeline.at_world(tw)
        dying = [(st.x, st.y) for st in states if st.state == "dying"]
    else:
        world = sess.lab.timeline.frame_world(tw)
    scene = sess.scene(world)
    frame_ex = frame_exclusions(world, scene, sess.lab.size, sess.spec.species, classes,
                                world.aid, dying)  # fmt: skip
    under = {f.gid: f.under for f in ff.fates}
    terrain = {f.gid: f.terrain for f in ff.fates}  # 4f (a map with the terrain rule only)
    kept = [{"gid": k.gid, "mob": k.mob, "box": [round(v, 1) for v in k.box],
             "ncc": k.ncc, "dx": k.dx, "dy": k.dy, "motion": k.motion, "heading": k.heading,
             "facing_from": k.facing_from, "state": k.state, "under": under.get(k.gid),
             **({"engaged": k.facing_from.startswith(ENGAGED_TAG)}
                if sess.spec.engaged_labels else {}),
             **({"terrain": terrain.get(k.gid)} if sess.spec.terrain else {})}
            for k in ff.kept]  # fmt: skip
    return {**row, "kept": kept, "excluded": [list(x) for x in ff.excluded],
            "hidden": ff.hidden, "excluded_frame": frame_ex,
            "whole": not ff.excluded and not frame_ex}  # fmt: skip


def count_labels(frames: Sequence[dict[str, Any]], species: Sequence[int],
                 drop_species: Sequence[int] = ()) -> dict[str, Any]:  # fmt: skip
    """Per species: kept labels in any frame / in frames kept WHOLE; exclusions by reason; the
    whole frames. ``drop_species``: species that are NOT classes (7: Green Plant's fallback), so a
    frame where one is kept or excluded is not whole either (``unchecked_species``)."""
    kept: Counter[int] = Counter()
    whole_lab: Counter[int] = Counter()
    excl: dict[int, Counter[str]] = defaultdict(Counter)
    frame_ex: Counter[str] = Counter()
    whole = 0
    labelled = 0
    for f in frames:
        if "kept" not in f:
            frame_ex.update(f.get("excluded_frame", []))
            continue
        labelled += 1
        mobs = [k["mob"] for k in f["kept"]] + [x[1] for x in f["excluded"]]
        dropped = bool(set(mobs) & set(drop_species))
        is_whole = f["whole"] and not dropped
        for k in f["kept"]:
            kept[k["mob"]] += 1
            if is_whole:
                whole_lab[k["mob"]] += 1
        for _g, mob, why in f["excluded"]:
            excl[mob][why] += 1
        frame_ex.update(f["excluded_frame"])
        if dropped:
            frame_ex["unchecked_species:dropped_class"] += 1
        whole += is_whole
    return {
        "frames_labelled": labelled, "frames_whole": whole,
        "frame_exclusions": dict(sorted(frame_ex.items())),
        "per_species": {str(m): {"kept": kept[m], "kept_in_whole_frames": whole_lab[m],
                                 "excluded": dict(sorted(excl[m].items()))}
                        for m in sorted(set(species) | set(kept) | set(excl))},
        "kept_total": sum(kept[m] for m in species),
        "kept_in_whole_frames_total": sum(whole_lab[m] for m in species),
    }  # fmt: skip


def cmd_labels(a: argparse.Namespace) -> dict[str, Any]:
    """The kept labels of ONE part. TEST is refused; the map's evaluation flag (``--eval-test2``:
    gef10-eval.md AMENDMENT R2-2, TEST2; ``--eval-test``: xmas02-detector.md 9, TEST) labels such
    a part instead, under FROZEN parameters, and refuses everything else."""
    spec = MAPS[a.map]
    flag = eval_flag_of(a)
    for part in a.parts:  # the map and every part's NAME, before anything is read
        if flag is not None:
            path, spots = parse_part(part)
            refuse_unless_eval(spec, path.name, spots, part, flag)
        else:
            refuse_part(spec, part, "not_test")
    params = load_params(a.params, spec)
    if flag is not None and params.get("status") != "FROZEN":
        raise SystemExit(f"{a.params}: {params.get('status')}: {EVAL_FLAGS[flag]} labels "
                         f"{EVAL_NOUN[flag]} under FROZEN parameters only")  # fmt: skip
    occl = frozen_occluders(params, spec)
    sess = RecSession.open(a.parts[0], spec, a.layout_templates)
    if flag is not None:  # by the manifest's session id too
        refuse_unless_eval(spec, sess.sid, sess.spots, sess.name, flag)
    else:
        refuse(sess, "not_test")
    classes = json.loads(a.classes.read_text())["monsters"]
    refs = sess.candidates_at(float(params["offset_ms"]))
    rule = str(params.get("occlusion", "o3h"))  # 4f: o3h-t when the FIT test adopted it
    olf._JOB.update(sess=sess, labeler=labeler_for(sess, params, occl, rule), classes=classes)
    frames = olf.run_parallel(_label_frame, refs, a.workers)
    out = {
        "what": f"the {spec.labels} labels (no pixels): kept fitted boxes per candidate frame",
        "labels": spec.labels, "params_status": params.get("status"), "map": spec.name,
        "part": sess.name, "session": sess.sid,
        "labelled_at": olf.now_ict(), "commit": olf.git_head(), "params": str(a.params),
        "params_sha256": olf.sha256_file(a.params), "frames_recorded": len(sess.refs),
        "candidates": len(refs), "candidate_drops": dict(sorted(sess.dropped.items())),
    }  # fmt: skip
    if flag is not None:  # the evaluation's TEST2 / TEST labels, and the classes file used
        out.update({flag: True, "classes": str(a.classes),
                    "classes_sha256": olf.sha256_file(a.classes)})  # fmt: skip
    if spec.name == "pay_fild07":  # payf07 7: the Green Plant fallback, both ways
        gp = 1080
        out["counts_green_plant_class"] = count_labels(frames, spec.species)
        out["counts_green_plant_not_class"] = count_labels(
            frames, [m for m in spec.species if m != gp], drop_species=[gp]
        )
    else:
        out["counts"] = count_labels(frames, spec.species)
        out["counts_engaged"] = count_engaged(frames)
    out["frames"] = frames
    return out


def count_engaged(frames: Sequence[dict[str, Any]]) -> dict[str, dict[str, int]]:
    """PURE (gef10 4h): per species, the kept ENGAGED labels in any frame / in frames whole."""
    out: dict[str, Counter[str]] = defaultdict(Counter)
    for f in frames:
        for k in f.get("kept", []):
            if k.get("engaged"):
                out[str(k["mob"])]["kept"] += 1
                out[str(k["mob"])]["kept_in_whole_frames"] += bool(f.get("whole"))
    return {m: dict(c) for m, c in sorted(out.items())}


# --- 6: the T2 pack ---------------------------------------------------------------------------


def stratum_of(items: Sequence[dict[str, Any]], stratum: str | None) -> list[dict[str, Any]]:
    """PURE (gef10 6): the items of one stratum: N = not engaged, E = engaged, None = all."""
    if stratum is None:
        return list(items)
    return [it for it in items if bool(it.get("engaged")) == (stratum == "E")]


def strata_for(spec: MapSpec) -> tuple[str | None, ...]:
    """gef10 6: N / E for a map that labels engaged units, else one stratum (None)."""
    return ("N", "E") if spec.engaged_labels else (None,)


def draw_strata(pool: dict[int, list[dict[str, Any]]], spec: MapSpec, seed: int,
                species: Sequence[int], n: int
                ) -> tuple[list[dict[str, Any]], dict[str, dict[str, int]]]:  # fmt: skip
    """PURE (6): per species of ``species`` and stratum, the first ``n`` of t2_order, then one
    seeded shuffle of the whole pack (``{salt}:{seed}:order``). Returns (chosen, per)."""
    chosen: list[dict[str, Any]] = []
    per: dict[str, dict[str, int]] = {}
    for mob in species:
        for st in strata_for(spec):
            items = stratum_of(pool.get(mob, []), st)
            pick = t2_order(items, seed, mob, spec.t2_salt, st)[:n]
            per[str(mob) if st is None else f"{mob}:{st}"] = {"pool": len(items),
                                                              "sampled": len(pick)}  # fmt: skip
            chosen += [{**it, "stratum": st} for it in pick]
    random.Random(f"{spec.t2_salt}:{seed}:order").shuffle(chosen)
    return chosen, per


def t2_sample(pool: dict[int, list[dict[str, Any]]], spec: MapSpec, seed: int
              ) -> tuple[list[dict[str, Any]], dict[str, dict[str, int]], list[int]]:  # fmt: skip
    """PURE (6): T2's sample: the tier (a ``conditional`` species needs >= 30 kept labels -- in its
    N stratum for a map that labels engaged units), per species and stratum the first 30 of
    t2_order, then one seeded shuffle of the whole pack. Returns (chosen, per, tier)."""
    first = strata_for(spec)[0]
    tier = [m for m in spec.species if m not in spec.conditional
            or len(stratum_of(pool.get(m, []), first)) >= T2_PER_SPECIES]  # fmt: skip
    chosen, per = draw_strata(pool, spec, seed, tier, T2_PER_SPECIES)
    return chosen, per, tier


Sample = tuple[list[dict[str, Any]], dict[str, dict[str, int]], list[int]]  # chosen, per, tier


def eval_test2_sample(pool: dict[int, list[dict[str, Any]]], spec: MapSpec, seed: int,
                      per_species: int) -> Sample:  # fmt: skip
    """PURE (gef10-eval.md AMENDMENT R2-2): the evaluation pack's draw. EVERY species of the map
    with at least one kept label in the pool (no conditional tier: "fewer: all of them"), per
    species and stratum (N / E) the first ``per_species`` of t2_order, then T2's one seeded shuffle
    of the whole pack. Returns (chosen, per, the species drawn)."""
    if per_species < 1:
        raise SystemExit(f"--per-species {per_species}: at least 1")
    species = [m for m in spec.species if pool.get(m)]
    chosen, per = draw_strata(pool, spec, seed, species, per_species)
    return chosen, per, species


def eval_pack_refusals(spec: MapSpec, flag: str | None, per_species: int | None,
                       seed: int | None = None) -> None:  # fmt: skip
    """AMENDMENT R2-2 / xmas02 6, 9, before anything is read: ``--per-species`` only with an
    evaluation flag (T2 draws 30); the flag is the map's own (``--eval-test2`` gef_fild10's,
    ``--eval-test`` xmas_dun02's) and needs ``--per-species N >= 1``; a map's PRE-REGISTERED seed
    and N (MapSpec.t2_seed, eval_seed, eval_per_species: xmas02 51, 53, 60) are the only ones."""
    if flag is None:
        if per_species is not None:
            raise SystemExit("--per-species: only with --eval-test2 / --eval-test (T2 draws "
                             f"{T2_PER_SPECIES} per species and stratum)")  # fmt: skip
        if seed is not None and spec.t2_seed is not None and seed != spec.t2_seed:
            raise SystemExit(f"--seed {seed}: {spec.name}'s T2 seed is {spec.t2_seed} "
                             f"({spec.plan} 6)")  # fmt: skip
        return
    why = eval_map_refusal(spec, flag)
    if why is not None:
        raise SystemExit(why)
    if per_species is None or per_species < 1:
        raise SystemExit(f"{EVAL_FLAGS[flag]}: --per-species N (N >= 1; the amendment draws 60)")
    if spec.eval_per_species is not None and per_species != spec.eval_per_species:
        raise SystemExit(f"--per-species {per_species}: {spec.name}'s evaluation draws "
                         f"{spec.eval_per_species} ({spec.plan} 9)")  # fmt: skip
    if seed is not None and spec.eval_seed is not None and seed != spec.eval_seed:
        raise SystemExit(f"--seed {seed}: {spec.name}'s evaluation pack seed is "
                         f"{spec.eval_seed} ({spec.plan} 9)")  # fmt: skip


def pack_pool(paths: Sequence[Path], spec: MapSpec, session_root: str, eval_test2: bool = False,
              eval_flag: str | None = None
              ) -> tuple[dict[int, list[dict[str, Any]]], list[dict[str, Any]], set[str],
                         set[str]]:  # fmt: skip
    """6: the pack's pool from label files: per species the kept labels, the files (sources),
    their parameter sha256s and statuses. TEST label files are refused; under an evaluation flag
    (``eval_test2``: gef10-eval.md AMENDMENT R2-2; ``eval_flag`` names any map's, xmas02's
    ``eval_test``) ONLY the parts it reads, in label files made by ``labels`` with that flag, are
    taken, and every other file (FIT, TRAIN, gef10's round 1 TEST and TEST3) is refused."""
    flag = eval_flag or ("eval_test2" if eval_test2 else None)
    pool: dict[int, list[dict[str, Any]]] = defaultdict(list)
    sources = []
    params_sha = set()
    statuses: set[str] = set()
    root = Path(session_root)
    for path in paths:
        doc = json.loads(path.read_text())
        if doc.get("labels") != spec.labels:
            raise SystemExit(f"{path}: not {spec.labels} labels")
        spots = parse_part(doc["part"])[1]
        if flag is not None:
            why = eval_part_refusal(spec, doc["session"], spots, flag)
            if why is None and doc.get(flag) is not True:
                why = f"not made by labels {EVAL_FLAGS[flag]}"
            if why is not None:
                raise SystemExit(f"{doc['part']}: {why}: not in the evaluation pack's pool")
        elif spec.is_test(doc["session"], spots):
            raise SystemExit(f"{doc['part']}: TEST is not in T2's pool")
        params_sha.add(doc["params_sha256"])
        statuses.add(str(doc.get("params_status")))
        sources.append({"part": doc["part"], "file": str(path), "sha256": olf.sha256_file(path)})
        for f in doc["frames"]:
            for k in f.get("kept", []):
                pool[int(k["mob"])].append({
                    "session": doc["session"], "frame_id": f["frame_id"], "gid": k["gid"],
                    "mob": k["mob"], "box": k["box"], "ncc": k["ncc"], "under": k["under"],
                    "state": k["state"], "spot": f.get("spot"), "t": f["t"],
                    "engaged": bool(k.get("engaged")),
                    "ref": (str(root / doc["session"] / f["shard"]), f["offset"], f["size"]),
                })  # fmt: skip
    return pool, sources, params_sha, statuses


def cmd_pack(a: argparse.Namespace) -> dict[str, Any]:
    import orc_label_sheets as ols

    spec = MAPS[a.map]
    flag = eval_flag_of(a)  # the map's evaluation flag (--eval-test2 / --eval-test), or None
    per_species: int | None = getattr(a, "per_species", None)
    eval_pack_refusals(spec, flag, per_species, a.seed)
    instr = a.instructions.read_bytes()
    sha = hashlib.sha256(instr).hexdigest()
    if sha != a.instructions_sha256:
        raise SystemExit(f"{a.instructions}: sha256 {sha}, not the pre-registered one")
    pool, sources, params_sha, statuses = pack_pool(a.labels, spec, a.session_root,
                                                    eval_flag=flag)  # fmt: skip
    if len(params_sha) != 1:
        raise SystemExit(f"the labels come from {len(params_sha)} parameter files")
    exclude: set[tuple[str, int, int]] = set()
    for kp in a.exclude_key or []:  # 11: the crops an earlier round judged
        for c in json.loads(kp.read_text())["crops"].values():
            exclude.add((c["session"], int(c["frame_id"]), int(c["gid"])))
    cut_by: dict[str, dict[str, int]] = {}
    if a.min_fit is not None or exclude:
        for mob in list(pool):
            pool[mob], cut_by[str(mob)] = round2_pool(pool[mob], a.min_fit, exclude)
    if flag is not None:  # R2-2 / xmas02 9: every species with a kept label, N per species
        assert per_species is not None  # eval_pack_refusals
        chosen, per, tier = eval_test2_sample(pool, spec, a.seed, per_species)
    else:
        chosen, per, tier = t2_sample(pool, spec, a.seed)
    pack, key_dir = a.pack_dir, a.key_dir
    if pack.resolve() == key_dir.resolve() or key_dir.resolve().is_relative_to(pack.resolve()):
        raise SystemExit("the key must live outside the pack")
    (pack / "crops").mkdir(parents=True, exist_ok=True)
    key_dir.mkdir(parents=True, exist_ok=True)
    frames: dict[tuple[str, int, int], npt.NDArray[np.uint8]] = {}
    for it in sorted(chosen, key=lambda x: x["ref"]):
        r = it["ref"]
        if r not in frames:
            frames[r] = read_png(qa_export.JpegRef(it["frame_id"], it["t"], Path(r[0]), r[1],
                                                   r[2]))[:, :, ::-1]  # fmt: skip
    size = (1280, 720)
    key_crops, names, enlarged = {}, [], []
    for i, it in enumerate(chosen, 1):
        x0, y0, x1, y1 = ols.crop_box(it["box"], size)
        img = ols.draw_box(frames[it["ref"]][y0:y1, x0:x1], it["box"], (x0, y0))
        big = ols.enlarge(img)
        num = f"{i:03d}"
        ols.save_png(pack / "crops" / f"{num}.png", big)
        enlarged.append((num, big))
        names.append(f"{num}.png")
        key_crops[num] = {k: it[k] for k in ("mob", "session", "frame_id", "gid", "box", "ncc",
                                             "under", "state", "spot")}  # fmt: skip
        if it.get("stratum") is not None:  # gef10 6: blind_score.py --sample N | E
            key_crops[num].update({"stratum": it["stratum"], "samples": [it["stratum"]],
                                   "engaged": it["engaged"]})  # fmt: skip
    use_kb(spec)
    sheets = qa_export.Sheets(directory=spec.sprites)
    ref_mobs = list(spec.species) + list(spec.reference)
    ref_mobs = ref_mobs[:12] if len(ref_mobs) > 12 else ref_mobs
    letters = ols.letters_for(ref_mobs, a.seed)
    ols.save_png(
        pack / "reference.png",
        ols.reference_sheet({m: sheets(m) for m in ref_mobs}, letters, views="multi"),
    )
    grids = []
    for page, idx in enumerate(ols.grid_pages(len(enlarged)), 1):
        gname = f"grids/grid_{page:02d}.png"
        ols.save_png(pack / gname, ols.blind_grid([enlarged[i] for i in idx]))
        grids.append(gname)
    (pack / "pack.json").write_text(json.dumps({
        "crops": names, "grids": grids, "reference": "reference.png", "letters": sorted(letters),
        "box": "the green rectangle drawn just outside the label box",
        "questions": ols.QUESTIONS}, indent=1) + "\n")  # fmt: skip
    shutil.copyfile(a.instructions, pack / "instructions.txt")
    target = per_species if flag is not None else T2_PER_SPECIES
    evaluation = {flag: True} if flag is not None else {}  # the evaluation's pack only
    key = {"labels": spec.labels, "seed": a.seed, "per_species_target": target,
           **({"candidates": ["N", "E"]} if spec.engaged_labels else {}),
           "letters": letters, "crops": key_crops, "tier_species": tier,
           "per_species": per, "sources": sources, "params_sha256": params_sha.pop(),
           "params_status": sorted(statuses),
           "instructions_sha256": sha, "built_at": olf.now_ict(), "commit": olf.git_head(),
           "note": "THE ANSWER KEY: never give it (or this directory) to a blind labeller",
           "min_fit": a.min_fit, "removed_from_pool": cut_by,
           "exclude_keys": [str(k) for k in (a.exclude_key or [])],
           **evaluation,
           }  # fmt: skip
    (key_dir / "answer_key.json").write_text(json.dumps(key, indent=1) + "\n")
    return {"pack": str(pack), "key": str(key_dir / "answer_key.json"), "crops": len(names),
            "per_species": per, "tier_species": tier, "letters": len(letters),
            "params_status": key["params_status"], "removed_from_pool": cut_by,
            "grids": len(grids),
            **({"per_species_target": target, **evaluation} if flag is not None else {}),
            }  # fmt: skip


# --- CLI --------------------------------------------------------------------------------------


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    layout = Path.home() / "docker" / "poring-lab" / "data" / "ui_anchors" / "layout"

    def common(p: argparse.ArgumentParser, parts: bool = True) -> None:
        p.add_argument("--map", default="pay_fild07", choices=sorted(MAPS))
        if parts:
            p.add_argument("parts", nargs="+")
            p.add_argument("--workers", type=int, default=1)
            p.add_argument("--layout-templates", type=Path, default=layout)
        p.add_argument("--out", type=Path, required=True)

    p = sub.add_parser("offset")
    common(p)
    p.add_argument("--diagnostic", action="store_true",
                   help="9b: any non-TEST part; reported, never frozen")  # fmt: skip
    p = sub.add_parser("threshold")
    common(p)
    p.add_argument("--offset", type=Path, default=None)
    p.add_argument("--proposed-offset-ms", type=float, default=None)
    p.add_argument("--proposal", default=None, help="the proposal's name (9b)")
    p.add_argument("--rows", type=Path, default=None, help="write every FIT fate (diagnostics)")
    p = sub.add_parser("freeze")
    common(p, parts=False)
    p.add_argument("--offset", type=Path, default=None)
    p.add_argument("--threshold", type=Path, required=True)
    p.add_argument("--engaged", type=Path, default=None,
                   help="gef10 4h: the engaged selection (map_labels.py engaged)")  # fmt: skip
    p.add_argument("--engaged-variant", default=None,
                   help="gef10 4h: an amendment's variant instead of the selection's")  # fmt: skip
    p.add_argument("--proposed", action="store_true",
                   help="10a: write the proposal's parameters, NOT frozen")  # fmt: skip
    p.add_argument("--decision", default=None,
                   help="10a: FREEZE the proposed offset (cite the amendment)")  # fmt: skip
    p = sub.add_parser("engaged")
    common(p)
    p.add_argument("--offset-ms", type=float, required=True)
    p.add_argument("--offset-source", required=True, help="the 1d file or the proposal's name")
    p.add_argument("--o3h-tau", type=float, required=True, help="T_h (4e), the floor")
    p.add_argument("--variants", nargs="+", default=["E1", "E2", "E3"])
    p.add_argument("--rows", type=Path, default=None)
    p = sub.add_parser("check")
    common(p)
    p.add_argument("--params", type=Path, required=True)
    p.add_argument("--rows", type=Path, default=None)
    p.add_argument("--allow-fit", action="store_true", help="report C1 on FIT (not T1)")
    p.add_argument(
        "--fit-diagnostic",
        action="store_true",
        help="gef10 13: FIT parts only, PROPOSED parameters allowed (not T1, not 3c)",
    )
    p.add_argument("--c1-rule", choices=sorted(C1_RULES), default="round1",
                   help="round1: the frozen check; round2: + the pickup-notice exclusion "
                        "(gef10-round2.md; MapSpec.c1_rules: gef_fild10, and xmas_dun02 where "
                        "it is the only rule)")  # fmt: skip
    p = sub.add_parser("labels")
    common(p)
    p.add_argument("--params", type=Path, required=True)
    p.add_argument("--classes", type=Path, default=ROOT / "config/detector/classes-v2orc.json")
    p.add_argument("--eval-test2", action="store_true",
                   help="gef10-eval.md AMENDMENT R2-2: label ONE TEST2 part (gef_fild10, a9 / "
                        "a10 / a11 / w3) under FROZEN parameters for the evaluation")  # fmt: skip
    p.add_argument("--eval-test", action="store_true",
                   help="xmas02-detector.md 9: label ONE TEST part (xmas_dun02: xw5 / xp1 / X2) "
                        "under FROZEN parameters for the evaluation")  # fmt: skip
    p = sub.add_parser("pack")
    p.add_argument("--map", default="pay_fild07", choices=sorted(MAPS))
    p.add_argument("labels", nargs="+", type=Path)
    p.add_argument("--eval-test2", action="store_true",
                   help="gef10-eval.md AMENDMENT R2-2: the evaluation pack from TEST2 label "
                        "files (labels --eval-test2) only; every species with a kept label, "
                        "no conditional tier")  # fmt: skip
    p.add_argument("--eval-test", action="store_true",
                   help="xmas02-detector.md 9: the evaluation pack from TEST label files "
                        "(labels --eval-test) only; seed 53, 60 per species")  # fmt: skip
    p.add_argument("--per-species", type=int, default=None,
                   help="--eval-test2 / --eval-test only: the first N per species and "
                        "stratum")  # fmt: skip
    p.add_argument("--seed", type=int, required=True)
    p.add_argument("--pack-dir", type=Path, required=True)
    p.add_argument("--key-dir", type=Path, required=True)
    p.add_argument("--instructions", type=Path, required=True)
    p.add_argument("--instructions-sha256", required=True)
    p.add_argument("--session-root", default="/mnt/poring-lab-datasets")
    p.add_argument("--min-fit", type=float, default=None,
                   help="11: the frozen T_h on labels NOT under a model (weak_fit)")  # fmt: skip
    p.add_argument("--exclude-key", type=Path, action="append", default=None,
                   help="11: an earlier round's answer key: its crops leave the pool")  # fmt: skip
    p.add_argument("--out", type=Path, required=True)
    a = ap.parse_args(argv)
    if a.cmd == "labels" and len(a.parts) != 1:
        raise SystemExit("labels: one PART per run")
    run = {"offset": cmd_offset, "threshold": cmd_threshold, "freeze": cmd_freeze,
           "check": cmd_check, "labels": cmd_labels, "pack": cmd_pack,
           "engaged": cmd_engaged}  # fmt: skip
    out = run[a.cmd](a)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(out, indent=1) + "\n")
    brief = {k: v for k, v in out.items() if k != "frames"}
    print(json.dumps(brief, indent=1)[:20000])
    return 0


if __name__ == "__main__":
    sys.exit(main())
