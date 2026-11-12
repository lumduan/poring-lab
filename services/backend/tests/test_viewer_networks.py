"""VIEWER_NETWORKS from a user's .env (Batt 2026-11-12: a 10.x / 172.x home LAN must be able to use
the Settings page; no hard locks). An entry overlapping the lab's own Docker subnets is dropped,
never admitted, and never stops the backend."""

import ipaddress
import re
from pathlib import Path

from poring_backend.config import Settings

ROOT = Path(__file__).resolve().parents[3]


def nets(s: Settings) -> list[str]:
    return [str(n) for n in s.viewer_nets]


def test_the_default_is_unchanged() -> None:
    assert nets(Settings()) == ["192.168.0.0/16"]


def test_a_home_lan_outside_192_168_is_accepted() -> None:
    got = nets(Settings(viewer_networks="10.0.1.0/24, 172.20.0.0/16"))
    assert got == ["10.0.1.0/24", "172.20.0.0/16"]


def test_an_entry_overlapping_our_docker_subnets_is_dropped() -> None:
    s = Settings(viewer_networks="10.0.0.0/8,192.168.1.0/24,10.210.97.5/32")
    assert nets(s) == ["192.168.1.0/24"]  # 10/8 covers the compose subnet; .97.5 is the agent net
    assert all(not n.overlaps(ipaddress.ip_network("10.210.96.0/24")) for n in s.viewer_nets)


def test_compose_passes_it_from_env_with_the_old_default() -> None:
    text = (ROOT / "compose.yaml").read_text()
    assert re.search(r"VIEWER_NETWORKS: \$\{VIEWER_NETWORKS:-192\.168\.0\.0/16\}", text)
    assert "VIEWER_NETWORKS=" in (ROOT / ".env.example").read_text()
