"""scripts/map_agreement.py + kb_bindings' L3 map.walkability (Batt's decision 4, 2026-10-15):
the per-map record of where the client's GAT and the server's map cache disagree. SYNTHETIC GATs
and caches only (CLAUDE.md rule 4)."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import struct
import sys
import zlib
from pathlib import Path
from types import ModuleType

import numpy as np
import pytest

SCRIPTS = Path(__file__).resolve().parents[3] / "scripts"


def _load(name: str) -> ModuleType:
    sys.path.insert(0, str(SCRIPTS))
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def ma() -> ModuleType:
    return _load("map_agreement")


def write_gat(path: Path, types: np.ndarray) -> None:
    from poring_dataset import gat as gatmod

    h, w = types.shape
    tiles = np.zeros(w * h, gatmod.TILE)
    tiles["type"] = types.ravel()
    path.write_bytes(struct.pack("<4sBBII", b"GRAT", 1, 2, w, h) + tiles.tobytes())


def write_cache(directory: Path, maps: dict[str, np.ndarray]) -> Path:
    """The four cache files mapcache.load reads (the maps in pre-re) and a lock naming them."""
    lock: dict[str, object] = {"rathena_ref": "test-ref", "files": {}}
    for key in ("import", "pre-re", "base", "re"):
        content = maps if key == "pre-re" else {}
        body = b""
        for name, types in content.items():
            ys, xs = types.shape
            z = zlib.compress(types.astype(np.uint8).tobytes())
            body += struct.pack("<12shhi", name.encode(), xs, ys, len(z)) + z
        data = struct.pack("<IHH", 8 + len(body), len(content), 0) + body
        (directory / f"c.{key}.dat").write_bytes(data)
        lock["files"][key] = {"name": f"c.{key}.dat",  # type: ignore[index]
                              "sha256": hashlib.sha256(data).hexdigest()}  # fmt: skip
    path = directory / "lock.json"
    path.write_text(json.dumps(lock))
    return path


@pytest.fixture
def world(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path, Path]:
    """Maps: `agree` (both sources, one cell each way different), `taller` (the client's map
    taller than the server's), `clientonly` (no server entry), `l3only` (L3 lists it, no GAT)."""
    from poring_dataset import mapcache

    gat_dir, cache, kb = tmp_path / "gat", tmp_path / "cache", tmp_path / "kb"
    for d in (gat_dir, cache, kb):
        d.mkdir()
    client = np.zeros((6, 6), np.uint16)
    client[1, 1] = 1  # the client's wall; the server walks there
    write_gat(gat_dir / "agree.gat", client)
    write_gat(gat_dir / "taller.gat", np.zeros((8, 5), np.uint16))
    write_gat(gat_dir / "clientonly.gat", np.zeros((3, 3), np.uint16))
    server = np.zeros((6, 6), np.uint8)
    server[2, 3] = 5  # the server's cliff; the client walks there
    maps = {"agree": server, "taller": np.zeros((5, 5), np.uint8), "l3only": np.zeros((4, 4))}
    monkeypatch.setattr(mapcache, "LOCK", write_cache(cache, maps))
    (kb / "route.json").write_text(json.dumps({"warps": {"agree": [], "l3only": []}}))
    return gat_dir, cache, kb


def test_build_counts_each_map_lists_its_cells_and_the_maps_a_source_lacks(
    ma: ModuleType, world: tuple[Path, Path, Path]
) -> None:
    gat_dir, cache, kb = world
    doc = ma.build(gat_dir, cache, kb)
    assert sorted(doc["maps"]) == ["agree", "taller"]
    assert doc["missing"] == {"client_gat": ["l3only"], "server_cache": ["clientonly"]}
    a = doc["maps"]["agree"]
    assert (a["client_only"], a["server_only"], a["both"]) == (1, 1, 23)  # 5 x 5 overlap
    assert a["client_only_cells"] == [[3, 2]] and a["server_only_cells"] == [[1, 1]]
    assert a["edge_client_walkable"] == 11 and not a["size_differs"]
    t = doc["maps"]["taller"]
    assert t["size_differs"] and t["client_size"] == [5, 8] and t["server_size"] == [5, 5]
    assert t["outside_client_walkable"] == 15 and t["client_only_cells"] == []
    assert doc["mapcache_ref"] == "test-ref" and "decision 4" in doc["decision"]
    assert "agree" in ma.table(doc) and "SIZE DIFFERS" in ma.table(doc)
    assert "client_only_cells" not in ma.build(gat_dir, cache, kb, cells=False)["maps"]["agree"]


def test_the_build_command_writes_where_it_is_told(
    ma: ModuleType, world: tuple[Path, Path, Path], tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:  # fmt: skip
    gat_dir, cache, kb = world
    out = tmp_path / "out" / "map_agreement.json"
    assert ma.main(["build", "--gat-dir", str(gat_dir), "--mapcache-dir", str(cache),
                    "--kb", str(kb), "--out", str(out)]) == 0  # fmt: skip
    doc = json.loads(out.read_text())
    assert doc["maps"]["agree"]["client_only_cells"] == [[3, 2]]
    assert "agree" in capsys.readouterr().out


def test_l3_walkability_is_client_and_server_with_counts(
    world: tuple[Path, Path, Path],
) -> None:
    """kb_bindings' leaf: the source is client∩server; counts only (no cell lists); the
    gat_dir key poring_flow's kbsheet reads is kept; and resolve() still sees a LEAF."""
    gat_dir, cache, kb = world
    kbb = _load("kb_bindings")
    leaf = kbb.walkability(gat_dir, cache, kb)
    assert leaf["status"] == "generated" and leaf["source"] == "client∩server"
    assert leaf["gat_dir"] == str(gat_dir) and leaf["helper"] == "poring_dataset.walkable.both"
    assert leaf["by_map"]["agree"]["client_only"] == 1
    assert "client_only_cells" not in leaf["by_map"]["agree"]
    assert leaf["missing"] == {"client_gat": ["l3only"], "server_cache": ["clientonly"]}
    from poring_skills.resolve import ActiveEnv, resolve

    (kb / "lab-rathena.json").write_text(json.dumps({"map": {"walkability": leaf}}))
    env = ActiveEnv(client="kro-20211103-prere", server="lab-rathena", locale="en", path="rdp")
    got = resolve("nav.walk_to", env, l3_root=kb)["L3.map.walkability"]
    assert got["source"] == "client∩server" and got["by_map"]["taller"]["size_differs"]
