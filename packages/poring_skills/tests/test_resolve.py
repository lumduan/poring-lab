"""poring_skills.resolve: bindings for the active environment, failing CLOSED."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from poring_skills.resolve import ActiveEnv, Unsupported, client_for_profile, load_l2, resolve

LAB = ActiveEnv(client="kro-20211103-prere", server="lab-rathena", locale="en", path="rdp")


def test_the_lab_client_profile_maps_to_its_build() -> None:
    assert client_for_profile("kro") == "kro-20211103-prere"
    with pytest.raises(Unsupported):
        client_for_profile("renewal-2024")
    assert load_l2("kro-20211103-prere")["build"]["renewal"] is False


def test_a_window_shortcut_resolves_by_its_parameter() -> None:
    got = resolve("vitals.read", LAB)
    assert got["L2.window.basic_info"]["anchor"] == "basic_info"
    with pytest.raises(Unsupported, match="not bound"):
        resolve("ui.open_window", LAB, {"window": "world_map"})
    # a bound shortcut whose window has no anchor-map entry yet is still unsupported
    with pytest.raises(Unsupported, match="L2.window"):
        resolve("ui.open_window", LAB, {"window": "party"})
    got = resolve("ui.open_window", LAB, {"window": "status"})  # anchors cut 2026-10-07
    assert got["L2.shortcut.window"]["keys"] == ["AltLeft", "KeyA"]
    assert got["L2.window"]["anchor"] == "status"
    got = resolve("ui.open_window", LAB, {"window": "basic_info"})
    assert got["L2.shortcut.window"]["keys"] == ["AltLeft", "KeyV"]
    assert got["L2.window"]["anchor"] == "basic_info"


def test_an_unknown_client_or_server_fails_closed(tmp_path: Path) -> None:
    other = ActiveEnv(client="kro-2024-renewal", server="lab-rathena", locale="en", path="rdp")
    with pytest.raises(Unsupported, match="no L2 bindings for kro-2024-renewal"):
        resolve("vitals.read", other)
    with pytest.raises(Unsupported, match="no L3 bindings for lab-rathena"):
        resolve("nav.walk_to", LAB, l3_root=tmp_path)  # nothing generated in tmp_path


def test_l3_comes_from_the_locally_generated_file(tmp_path: Path) -> None:
    (tmp_path / "lab-rathena.json").write_text(json.dumps({"map": {"walkability": {
        "status": "generated", "source": "gat"}}}))  # fmt: skip
    got = resolve("nav.walk_to", LAB, l3_root=tmp_path)
    assert got["L3.map.walkability"]["source"] == "gat"
    assert got["L2.camera.projection"]["value"] == "camera_rdp.json"
    s2 = ActiveEnv(LAB.client, LAB.server, LAB.locale, "s2")
    assert resolve("nav.walk_to", s2, l3_root=tmp_path)["L2.camera.projection"]["value"] == (
        "camera_console.json"
    )


def test_l4_has_no_resolver_yet_and_says_so(tmp_path: Path) -> None:
    (tmp_path / "lab-rathena.json").write_text(json.dumps({"npc": {"kafra": {"status": "g"}}}))
    with pytest.raises(Unsupported, match="L3 binding L3.kafra.destinations|L4"):
        resolve("nav.kafra_teleport", LAB, {"destination": "x"}, l3_root=tmp_path)
