"""VIEWER_NETWORKS from a user's .env (Batt 2026-11-12: a 10.x / 172.x home LAN must be able to use
the Settings page; no hard locks). Batt 2026-11-19, outside on the VPN (10.0.1.2, refused
"not_a_lan_viewer"): "do not lock it to the local network" -- the default is every private range,
``any`` every address. The lab's own Docker subnets are EXCLUDED from every entry, never admitted,
and nothing here stops the backend."""

import ipaddress
import re
import sys
from pathlib import Path

from poring_backend.config import PRIVATE_NETWORKS, Settings
from poring_backend.routes_packets import in_networks

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts"))

import setup_core  # noqa: E402


def nets(s: Settings) -> list[str]:
    return [str(n) for n in s.viewer_nets]


def admitted(s: Settings, host: str) -> bool:
    return in_networks(host, s.viewer_nets)


def test_the_default_is_every_private_range_minus_our_docker_subnets() -> None:
    s = Settings()
    for host in ("10.0.1.2", "192.168.1.169", "192.168.110.55", "172.20.3.4", "100.101.102.103",
                 "fd7a:115c:a1e0::1", "::ffff:10.0.1.2"):  # fmt: skip
        assert admitted(s, host), host  # the VPN, the LAN, a 172.x LAN, Tailscale, IPv6 ULA
    for host in ("10.210.96.1", "10.210.96.6", "10.210.97.5", "8.8.8.8", "2001:db8::1"):
        assert not admitted(s, host), host  # our containers and their gateway; public addresses
    assert Settings(viewer_networks="  ").viewer_nets == s.viewer_nets  # empty = the default


def test_any_admits_every_address_but_never_our_containers() -> None:
    s = Settings(viewer_networks="any")
    assert all(admitted(s, h) for h in ("8.8.8.8", "203.0.113.9", "10.0.1.2", "2001:db8::1"))
    assert not any(admitted(s, h) for h in ("10.210.96.6", "10.210.96.1", "10.210.97.5"))


def test_a_home_lan_outside_192_168_is_accepted() -> None:
    got = nets(Settings(viewer_networks="10.0.1.0/24, 172.20.0.0/16"))
    assert got == ["10.0.1.0/24", "172.20.0.0/16"]


def test_an_entry_overlapping_our_docker_subnets_keeps_the_rest() -> None:
    s = Settings(viewer_networks="10.0.0.0/8,192.168.1.0/24,10.210.97.5/32")
    assert admitted(s, "10.0.1.2") and admitted(s, "10.210.95.9") and admitted(s, "192.168.1.9")
    assert not admitted(s, "10.210.96.6") and not admitted(s, "10.210.97.5")
    assert all(not n.overlaps(ipaddress.ip_network("10.210.96.0/24")) for n in s.viewer_nets)
    assert all(not n.overlaps(ipaddress.ip_network("10.210.97.0/24")) for n in s.viewer_nets)
    assert "10.210.97.5/32" not in nets(s)  # inside the agent network: dropped whole


def test_compose_passes_it_from_env_and_the_code_holds_the_default() -> None:
    text = (ROOT / "compose.yaml").read_text()
    assert re.search(r"VIEWER_NETWORKS: \$\{VIEWER_NETWORKS:-\}", text)
    assert re.search(r"(?m)^VIEWER_NETWORKS=$", (ROOT / ".env.example").read_text())
    assert setup_core.PRIVATE_NETWORKS == PRIVATE_NETWORKS  # the wizard's copy
