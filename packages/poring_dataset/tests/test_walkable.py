"""poring_dataset.walkable (Batt's decision 4, 2026-10-15): a walk uses only cells walkable in
BOTH the client's GAT and the server's map cache. SYNTHETIC grids only (CLAUDE.md rule 4)."""

from __future__ import annotations

import hashlib
import json
import struct
import zlib
from pathlib import Path

import numpy as np
import pytest

from poring_dataset import gat as gatmod
from poring_dataset import mapcache
from poring_dataset import walkable as wk


def synthetic_gat(types: np.ndarray) -> gatmod.Gat:
    """A flat GAT 1.2 with these cell types, (height, width) indexed [y, x]."""
    h, w = types.shape
    tiles = np.zeros(w * h, gatmod.TILE)
    tiles["type"] = types.ravel()
    return gatmod.parse(struct.pack("<4sBBII", b"GRAT", 1, 2, w, h) + tiles.tobytes())


def grid(types: np.ndarray, name: str = "syn") -> mapcache.MapGrid:
    ys, xs = types.shape
    return mapcache.MapGrid(name, xs, ys, types.astype(np.uint8).tobytes())


def test_both_is_the_intersection_with_the_servers_nopass_rule() -> None:
    client = np.zeros((4, 5), np.uint16)
    client[1, 1] = 1  # a client wall
    server = np.zeros((4, 5), np.uint8)
    server[2, 2] = 5  # a server cliff the client calls walkable
    server[1, 3] = 1
    got = wk.both(synthetic_gat(client), grid(server))
    assert got.shape == (4, 5) and got.dtype == np.bool_
    srv = grid(server)
    for y in range(4):
        for x in range(5):  # the per-cell reference: the client AND not CELL_CHKNOPASS
            assert got[y, x] == (client[y, x] == 0 and not srv.nopass(x, y)), (x, y)
    assert not got[:, -1].any() and not got[-1, :].any()  # the server's last column / row


def test_client_cells_outside_the_servers_grid_are_not_walkable() -> None:
    """izlude's case: the client's map is taller than the server's."""
    g = synthetic_gat(np.zeros((6, 4), np.uint16))
    got = wk.both(g, grid(np.zeros((4, 4), np.uint8)))
    assert got.shape == (6, 4)
    assert got[:3, :3].all() and not got[3:, :].any() and not got[:, 3].any()
    wide = wk.both(synthetic_gat(np.zeros((3, 3), np.uint16)), grid(np.zeros((5, 5), np.uint8)))
    assert wide.shape == (3, 3) and wide.all()  # a server grid bigger than the client's


def test_a_missing_server_grid_fails_closed() -> None:
    g = synthetic_gat(np.zeros((3, 3), np.uint16))
    with pytest.raises(wk.MapSourceError):
        wk.both(g, None)
    with pytest.raises(wk.MapSourceError):
        wk.agreement(g, None)


def test_agreement_counts_the_overlap_without_the_servers_edge() -> None:
    client = np.zeros((5, 6), np.uint16)
    client[0, 0] = 1  # server-walkable, client-not
    server = np.zeros((5, 6), np.uint8)
    server[1, 1] = server[2, 3] = 1  # client-walkable, server-NOPASS
    g, s = synthetic_gat(client), grid(server)
    got = wk.agreement(g, s)
    # the interior: 4 rows x 5 columns = 20 cells; the edge (last row + column) 10 cells
    assert got == {
        "client_size": [6, 5], "server_size": [6, 5], "size_differs": False,
        "client_walkable": 19, "server_walkable": 18, "client_only": 2, "server_only": 1,
        "both": 17, "edge_client_walkable": 10, "outside_client_walkable": 0,
    }  # fmt: skip
    assert got["both"] == int(wk.both(g, s).sum())
    total = got["client_walkable"] + got["edge_client_walkable"] + got["outside_client_walkable"]
    assert total == int(g.walkable().sum())


def test_agreement_on_maps_of_different_sizes() -> None:
    g = synthetic_gat(np.zeros((7, 4), np.uint16))  # 4 wide, 7 tall
    got = wk.agreement(g, grid(np.zeros((4, 4), np.uint8)))
    assert got["size_differs"] and got["client_size"] == [4, 7] and got["server_size"] == [4, 4]
    assert got["client_walkable"] == got["both"] == 9  # 3 x 3
    assert got["edge_client_walkable"] == 7 and got["outside_client_walkable"] == 12
    assert got["both"] == int(wk.both(g, grid(np.zeros((4, 4), np.uint8))).sum())


def _write_cache(directory: Path, maps: dict[str, np.ndarray]) -> Path:
    """Three synthetic cache files and a lock naming them (load()'s format and checks)."""
    files = {"import": {}, "pre-re": maps, "base": {}, "re": {}}
    lock: dict[str, dict[str, dict[str, str]]] = {"files": {}}
    for key, content in files.items():
        body = b""
        for name, types in content.items():
            ys, xs = types.shape
            z = zlib.compress(types.astype(np.uint8).tobytes())
            body += struct.pack("<12shhi", name.encode(), xs, ys, len(z)) + z
        data = struct.pack("<IHH", 8 + len(body), len(content), 0) + body
        fname = f"map_cache.{key}.dat"
        (directory / fname).write_bytes(data)
        lock["files"][key] = {"name": fname, "sha256": hashlib.sha256(data).hexdigest()}
    lock_path = directory / "lock.json"
    lock_path.write_text(json.dumps(lock))
    return lock_path


def test_load_both_reads_both_sources_and_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    gat_dir, cache = tmp_path / "gat", tmp_path / "cache"
    gat_dir.mkdir()
    cache.mkdir()
    types = np.zeros((4, 4), np.uint8)
    types[1, 2] = 1
    monkeypatch.setattr(mapcache, "LOCK", _write_cache(cache, {"syn": types}))
    client = np.zeros((4, 4), np.uint16)
    tiles = np.zeros(16, gatmod.TILE)
    tiles["type"] = client.ravel()
    for name in ("syn", "clientonly"):
        (gat_dir / f"{name}.gat").write_bytes(
            struct.pack("<4sBBII", b"GRAT", 1, 2, 4, 4) + tiles.tobytes())  # fmt: skip
    g, mask = wk.load_both("syn", gat_dir, cache)
    assert (g.width, g.height) == (4, 4)
    assert mask[0, 0] and not mask[1, 2] and not mask[3, :].any() and int(mask.sum()) == 8
    with pytest.raises(wk.MapSourceError, match="lacks clientonly"):
        wk.load_both("clientonly", gat_dir, cache)  # the server's cache lacks it
    with pytest.raises(wk.MapSourceError, match="no client GAT"):
        wk.load_both("nogat", gat_dir, cache)
    assert wk.server_grid("syn", cache).xs == 4
