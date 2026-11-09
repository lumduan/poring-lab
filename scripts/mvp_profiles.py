"""The MVP watch's BOSS PROFILES (docs/planning/stormy-knight-recognizer.md B1): what the offline
study (scripts/mvp_watch_study.py) and the model file (scripts/mvp_watch.py) know about ONE boss.

    import mvp_profiles as mp
    prof = mp.get("stormy")            # or mp.ORCLORD / mp.STORMY; mp.for_map("xmas_dun02")
    prof.party                         # (boss, *summons): the truth's "in view" party

- ``orclord``: the Orc Lord (1190) and its Orc Archers (1189, 1473) on gef_fild10 (round 2's watch
  on prt_fild08), EXACTLY the values the Orc Lord study froze (orclord-recognizer.md 3, 4b, 10a):
  its committed results stay reproducible.
- ``stormy``: the Stormy Knight (1251) and its summons Garm Baby (1515, also a regular 30-min
  spawn there: ``lone``) and Christmas Goblin (1607) on xmas_dun02 (stormy-knight-recognizer.md
  1-3). Its RECIPE (the aura threshold, the ring, the aura colour rule) was measured on DEV only
  and frozen by B3 part 1 (stormy-knight-recognizer.md 5) before its fit; a recipe field left None
  is a placeholder the fit refuses.

The ids are the KB's (data/kb spawns.json / mob_skills.json NPC_SUMMONSLAVE, the derivation of
dungeon_hunt.boss_names; ``kb_party`` re-derives them and the tests check the two agree when the
local KB is there). No client data here: the sprite paths are local defaults (client-derived,
/dev/shm or the NAS, never committed).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

Ring = tuple[float, float, float, float]  # the aura's elliptical ring: outer a, b; inner a, b


@dataclass(frozen=True)
class BossProfile:
    name: str  # the model's ``profile`` field; data/mvp_watch/<name>-v1.npz
    boss: int  # the MVP's mob id
    summons: tuple[int, ...]  # its NPC_SUMMONSLAVE slaves
    names: Mapping[int, str]  # mob id -> name: the party, then the map's other species
    negatives: Mapping[int, str]  # the map's other species (the truth's negatives)
    maps: tuple[str, ...]  # maps[0]: the hunting map (truth's default --map); then watch-only maps
    sprites: Path  # the decoded monster sprites of maps[0] (sprite_catalog.py; client-derived)
    sprite_names: Path  # their client stems (npc_sprites.py mob-names)
    dev_cells: frozenset[int]  # the watch's DEV lattice cells (pre-registered)
    held_cells: frozenset[int]  # the watch's HELD-OUT lattice cells, scored once (pre-registered)
    lone: tuple[int, ...]  # party jobs that also spawn WITHOUT the boss: not hunting negatives
    # the RECIPE (fit's defaults; the model carries what was used). None = a PLACEHOLDER: not
    # fitted yet (B3 fits it on DEV), the fit refuses it unless given on its command line
    aura_thr: float | None  # the aura rule's frozen threshold (ring share)
    ring: Ring | None  # the ring's size (half-res px), tuned to the boss's own aura
    ring_cell: int | None  # the ring's grid (half-res px)
    ring_dy: float | None  # the ring's centre above the foot point (half-res px)
    aura_rule: tuple[int, int] | None  # the rim's colour: G >= g_min, G - R >= d, G - B >= d
    plan: str  # the study's plan

    @property
    def party(self) -> tuple[int, ...]:
        return (self.boss, *self.summons)

    @property
    def map(self) -> str:
        return self.maps[0]

    def recipe(self, **override: Any) -> dict[str, Any]:
        """The fit's recipe: the profile's fields, each replaced by a non-None ``override``;
        raises ValueError naming every placeholder still None."""
        out = {k: getattr(self, k) for k in RECIPE_FIELDS}
        out |= {k: v for k, v in override.items() if k in RECIPE_FIELDS and v is not None}
        missing = [k for k, v in out.items() if v is None]
        if missing:
            raise ValueError(f"--boss {self.name}: {', '.join(missing)} not fitted yet (a "
                             f"placeholder: B3 fits it on DEV, {self.plan}); give it on the "
                             "command line or write it into scripts/mvp_profiles.py")  # fmt: skip
        return out


RECIPE_FIELDS = ("aura_thr", "ring", "ring_cell", "ring_dy", "aura_rule")

_ORC_NEG = {1023: "Orc Warrior", 1273: "Orc Lady", 1686: "Orc Baby", 1031: "Poporing",
            1079: "Blue Plant", 1080: "Green Plant"}  # fmt: skip
ORCLORD = BossProfile(
    name="orclord", boss=1190, summons=(1189, 1473),
    names={1190: "Orc Lord", 1189: "Orc Archer", 1473: "Orc Archer (G)", **_ORC_NEG},
    negatives=_ORC_NEG, maps=("gef_fild10", "prt_fild08"),
    # gef_fild10's prep dir of 2026-10-25, GONE from /dev/shm (its NAS copy:
    # scratch-archive/2026-11-03/gef10-prep)
    sprites=Path("/dev/shm/poring-lab-tmp/gef10-prep/sprites/data/sprite/몬스터"),
    sprite_names=Path("/dev/shm/poring-lab-tmp/gef10-prep/kb-sprites/monster_sprite_names.json"),
    dev_cells=frozenset(range(8)), held_cells=frozenset(range(8, 15)), lone=(),
    # Amendment B's frozen recipe (orclord-recognizer.md 4b): 0.08 on a (27, 15, 17, 8) ring,
    # grid 3, 8 px above the feet; the rim rule G >= 236, G - R >= 25, G - B >= 25
    aura_thr=0.08, ring=(27.0, 15.0, 17.0, 8.0), ring_cell=3, ring_dy=8.0, aura_rule=(236, 25),
    plan="docs/planning/orclord-recognizer.md",
)  # fmt: skip

_XMAS_NEG = {1249: "Myst Case", 1248: "Cruiser", 1265: "Cookie", 1246: "Christmas Cookie"}
# xmas_dun02's decoded sprites, the X1 archive on the NAS, read in place (xmas02-prep.md)
_X1 = Path("/mnt/poring-lab-datasets/scratch-archive/2026-11-05/x1")
STORMY = BossProfile(
    name="stormy", boss=1251, summons=(1515, 1607),
    # 1515 is "Garm Baby" in the spawns, "Baby Hatii" in the mob table (dungeon_hunt.boss_names)
    names={1251: "Stormy Knight", 1515: "Garm Baby", 1607: "Christmas Goblin", **_XMAS_NEG},
    negatives=_XMAS_NEG, maps=("xmas_dun02",),
    sprites=_X1 / "sprites" / "data" / "sprite" / "몬스터",
    sprite_names=_X1 / "kb-sprites" / "monster_sprite_names.json",
    # section 3 (pre-registered 2026-11-09): DEV = cells 0-7, HELD-OUT = cells 8-15 (16 cells)
    dev_cells=frozenset(range(8)), held_cells=frozenset(range(8, 16)), lone=(1515,),
    # FROZEN 2026-11-09 by B3 part 1 on DEV ONLY (stormy-knight-recognizer.md 5: watch cells 0-7,
    # the hunt's first 300 s): the Knight's aura is a mint-white ring at its feet, its centre ~8
    # half-res px above the foot point, measured 24 x 10 outside, 14 x 4 inside. The Orc Lord's
    # rim rule (236, 25) takes xmas_dun02's green puzzle floor (a DEV gap frame scores 0.165); the
    # saturated rim G >= 248, G - R >= 40, G - B >= 40 keeps every DEV negative <= 0.042 (hunt
    # 0.019). The threshold = that max + 0.015 (Amendment B's margin), rounded up: 0.06.
    aura_thr=0.06, ring=(24.0, 10.0, 14.0, 4.0), ring_cell=3, ring_dy=8.0, aura_rule=(248, 40),
    plan="docs/planning/stormy-knight-recognizer.md",
)  # fmt: skip

PROFILES: dict[str, BossProfile] = {p.name: p for p in (ORCLORD, STORMY)}
DEFAULT = ORCLORD.name


def get(name: str) -> BossProfile:
    """The profile called ``name`` (KeyError names the known ones)."""
    try:
        return PROFILES[name]
    except KeyError:
        raise KeyError(f"unknown boss profile {name!r} (known: {', '.join(PROFILES)})") from None


def for_map(map_name: str) -> BossProfile | None:
    """The profile whose HUNTING map is ``map_name`` (the runner loads its model), else None."""
    key = map_name.removesuffix(".gat")
    return next((p for p in PROFILES.values() if p.map == key), None)


def kb_party(map_name: str, spawns: Mapping[str, Any],
             skills: Mapping[str, Any]) -> dict[str, Any]:  # fmt: skip
    """PURE: a map's boss party from the KB (spawns.json, mob_skills.json), as
    dungeon_hunt.boss_names derives it but by id: ``bosses`` (the boss spawns), ``summons``
    (their NPC_SUMMONSLAVE slaves), ``others`` (the map's other spawns: the negatives) and ``lone``
    (party ids that are ALSO a regular, non-boss spawn of the map)."""
    entries = list(spawns.get(map_name) or [])
    bosses = {int(e["id"]) for e in entries if e.get("boss")}
    summons: set[int] = set()
    for b in bosses:
        for sk in skills.get(str(b), []):
            if str(sk.get("info", "")).endswith("@NPC_SUMMONSLAVE"):
                summons |= {int(v) for v in sk.get("vals", []) if str(v).strip()}
    party = bosses | summons
    regular = {int(e["id"]) for e in entries if not e.get("boss")}
    return {"bosses": sorted(bosses), "summons": sorted(summons - bosses),
            "others": sorted(regular - party), "lone": sorted(regular & party)}  # fmt: skip


def matches_kb(prof: BossProfile, spawns: Mapping[str, Any],
               skills: Mapping[str, Any]) -> list[str]:  # fmt: skip
    """PURE: how ``prof`` differs from its hunting map's KB party (empty: it agrees)."""
    kb = kb_party(prof.map, spawns, skills)
    want: dict[str, Iterable[int]] = {"bosses": [prof.boss], "summons": prof.summons,
                                      "others": prof.negatives, "lone": prof.lone}  # fmt: skip
    return [f"{k}: profile {sorted(want[k])} != KB {kb[k]}" for k in kb
            if sorted(int(v) for v in want[k]) != kb[k]]  # fmt: skip
