"""The main checkout's DEFAULT paths follow the owner's home (Path.home()), not a fixed
/home/batt: /home/batt/docker/poring-lab on VM 103, /home/bot/docker/poring-lab on bot-server.
Only the defaults moved; every one stays overridable as before."""

from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts"))

CHECKOUT = Path.home() / "docker" / "poring-lab"
SCRIPTS = ("mvp_watch_study.py", "detector_vs_packets.py", "item_labels.py", "gef10_items.py",
           "map_labels.py", "npc_render_measure.py")  # fmt: skip


@pytest.mark.parametrize("name", SCRIPTS)
def test_no_fixed_batt_checkout_path_in_code(name: str) -> None:
    """No string constant (docstrings included) names /home/batt/docker/poring-lab; comments
    may."""
    fixed_path = "/home/batt/docker/poring-lab"
    tree = ast.parse((ROOT / "scripts" / name).read_text())
    fixed = [
        n.value
        for n in ast.walk(tree)
        if isinstance(n, ast.Constant) and isinstance(n.value, str) and fixed_path in n.value
    ]
    assert fixed == []


def test_the_defaults_follow_the_home() -> None:
    import detector_vs_packets as dv
    import gef10_items
    import item_labels
    import mvp_watch_study as mws

    assert mws.MAIN == dv.MAIN == item_labels.MAIN == CHECKOUT
    assert gef10_items.LAYOUT_TEMPLATES == CHECKOUT / "data" / "ui_anchors" / "layout"
    a = mws.parser().parse_args(["truth", "S", "--layout", "hunt", "--out", "o.json"])
    assert a.kb == CHECKOUT / "data" / "kb"
    assert a.mapcache_dir == CHECKOUT / "packages/poring_dataset/src/poring_dataset/_generated"
