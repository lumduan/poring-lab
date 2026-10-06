"""The Settings page's server allowlist (Batt, 2026-10-06; ADR-0016): HUMAN-ONLY writes.

The list decides when the interlock's client-side provider can turn green, so only a console
browser on the LAN may change it. The agent's own listener (:8001), the agent network, host
scripts/containers (the compose gateway) and requests without the console's Origin are refused,
counted and AUDITED. Entries are validated: host:port only, no wildcard, unspecified, loopback or
link-local address, nothing on the known-forbidden list (names, IPs, whole domains).
"""

import json
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from poring_backend import routes_settings
from poring_backend.config import Settings
from poring_backend.main import create_app

ORIGIN = "http://lab.test:3000"
H = {"origin": ORIGIN}
LAN = ("192.168.1.50", 50123)
ENVS = """
version: 1
attestation_max_age_s: 10
window_max_s: 120
environments:
  - id: lab-rathena
    status: allowed
    adr: ADR-0006
    server: {host: 192.168.1.13, ports: [6900, 5121]}
    windows_host: 192.168.1.169
    accounts: [2000001]
    signals: [lab_host, session]
  - id: community
    status: pending
    adr: ADR-0006
    signals: []
  - id: official-ro-thai
    status: forbidden
    adr: ADR-0006
    server: {host: thro-acc3.gnjoy.in.th, ports: [50001, 3000]}
    forbidden_endpoints: [.gnjoy.in.th, "49.229.28.99:3000", 49.229.28.13]
  - id: official-ro-korea
    status: forbidden
    adr: ADR-0006
    server: {host: kro-assit.ragnarok.co.kr, ports: [3000]}
    forbidden_endpoints: [.ragnarok.co.kr, "kro-qm-1a.ragnarok.co.kr:3000"]
"""


class NoCapture:
    def grab(self) -> Any:
        raise RuntimeError("no display in this test")

    def close(self) -> None:
        pass


class NoInput:
    def send_many(self, events: list[Any]) -> None:
        pass

    def pointer(self) -> tuple[int, int]:
        return (0, 0)

    def has_window_class(self, needle: str) -> bool:
        return False

    def close(self) -> None:
        pass


Make = Callable[..., TestClient]


@pytest.fixture
def make(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Make]:
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "environments.yaml").write_text(ENVS)
    (tmp_path / "settings").mkdir()

    async def no_dns(host: str) -> list[str]:  # tests never touch the network
        return [host] if host.replace(".", "").isdigit() else []

    monkeypatch.setattr(routes_settings, "resolve", no_dns)
    clients: list[TestClient] = []

    def factory(peer: tuple[str, int] = LAN, **overrides: Any) -> TestClient:
        fields: dict[str, Any] = {
            "data_dir": tmp_path / "data", "public_port": 80, "frontend_origins": ORIGIN,
            "status_hz": 20.0, "environments_file": tmp_path / "config" / "environments.yaml",
            "settings_dir": tmp_path / "settings", "lab_state_dir": tmp_path / "lab-state",
        }  # fmt: skip
        fields.update(overrides)
        app = create_app(Settings(**fields), capture_factory=NoCapture, input_factory=NoInput)
        client = TestClient(app, client=peer)
        client.__enter__()
        clients.append(client)
        return client

    yield factory
    for client in clients:
        client.__exit__(None, None, None)


def audit(tmp_path: Path) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for path in sorted((tmp_path / "settings" / "allowlist_audit").glob("*.jsonl")):
        out += [json.loads(line) for line in path.read_text().splitlines()]
    return out


def put(client: TestClient, entries: list[dict[str, Any]], rev: int = 0,
        env: str = "lab-rathena", headers: dict[str, str] = H) -> Any:  # fmt: skip
    return client.put(f"/settings/servers/{env}", json={"base_revision": rev, "entries": entries},
                      headers=headers)  # fmt: skip


def env_view(body: dict[str, Any], env: str = "lab-rathena") -> dict[str, Any]:
    return next(e for e in body["environments"] if e["id"] == env)


def test_round_trip_saves_reads_back_and_audits(make: Make, tmp_path: Path) -> None:
    client = make()
    first = client.get("/settings/servers", headers=H).json()
    assert first["revision"] == 0 and first["store"] == "ok"
    lab = env_view(first)
    assert lab["editable"] and lab["entries"] == []
    # the lab config's server is a SUGGESTION, never allowed by itself
    assert {(d["host"], d["port"]) for d in lab["discovered"]} == {
        ("192.168.1.13", 6900),
        ("192.168.1.13", 5121),
    }
    r = put(client, [{"host": "192.168.1.13", "port": 6900, "source": "discovered"}])
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["saved"] and body["read_back"] and body["revision"] == 1
    assert [e["host"] for e in env_view(body)["entries"]] == ["192.168.1.13"]
    stored = json.loads((tmp_path / "settings" / "allowlist.json").read_text())
    assert stored["revision"] == 1
    assert stored["environments"]["lab-rathena"][0]["added_by"] == LAN[0]
    [rec] = audit(tmp_path)
    assert (rec["action"], rec["entry"], rec["ok"]) == ("add", "192.168.1.13:6900", True)
    assert (rec["before"], rec["after"]) == ([], ["192.168.1.13:6900"])
    assert (rec["client"], rec["origin"], rec["listener"]) == (LAN[0], ORIGIN, 80)
    assert (rec["revision_before"], rec["revision_after"]) == (0, 1)
    assert client.get("/health").json()["allowlist"]["revision"] == 1


def test_remove_is_audited_with_before_and_after(make: Make, tmp_path: Path) -> None:
    client = make()
    put(client, [{"host": "192.168.1.13", "port": 6900}, {"host": "192.168.1.13", "port": 5121}])
    r = put(client, [{"host": "192.168.1.13", "port": 5121}], rev=1)
    assert r.json()["revision"] == 2
    rec = audit(tmp_path)[-1]
    assert (rec["action"], rec["entry"]) == ("remove", "192.168.1.13:6900")
    assert rec["before"] == ["192.168.1.13:6900", "192.168.1.13:5121"]
    assert rec["after"] == ["192.168.1.13:5121"]


def test_an_unchanged_list_writes_nothing(make: Make, tmp_path: Path) -> None:
    client = make()
    put(client, [{"host": "192.168.1.13", "port": 6900}])
    r = put(client, [{"host": "192.168.1.13", "port": 6900}], rev=1)
    assert r.json()["saved"] is False and r.json()["revision"] == 1
    assert len(audit(tmp_path)) == 1


@pytest.mark.parametrize(
    ("peer", "headers", "status", "reason"),
    [
        (LAN, {}, 403, "origin_required"),
        (LAN, {"origin": "http://evil.test"}, 403, "origin_not_allowed"),
        (("10.210.96.1", 1), H, 403, "compose_peer"),  # a host script / container via the gateway
        (("8.8.8.8", 1), H, 403, "not_a_lan_viewer"),
    ],
)  # fmt: skip
def test_only_a_console_browser_may_write(
    make: Make, tmp_path: Path, peer: tuple[str, int], headers: dict[str, str], status: int,
    reason: str,
) -> None:  # fmt: skip
    client = make(peer=peer)
    r = put(client, [{"host": "192.168.1.13", "port": 6900}], headers=headers)
    assert r.status_code == status and r.json()["detail"]["reason"] == reason
    assert not (tmp_path / "settings" / "allowlist.json").exists()
    [rec] = audit(tmp_path)
    assert (rec["action"], rec["ok"], rec["reason"]) == ("refused", False, reason)
    assert rec["client"] == peer[0]
    drops = client.get("/health").json()["dropped_messages"]["settings_http"]
    assert drops[reason] == 1


def test_the_agent_listener_can_read_but_never_write(make: Make, tmp_path: Path) -> None:
    """:8001 (here: requests arrive on 80 while the PUBLIC port is 8000) -- the agent's listener."""
    client = make(public_port=8000, internal_port=80)
    r = client.get("/settings/servers")  # no Origin: the agent is not a browser
    assert r.status_code == 200 and r.json()["revision"] == 0
    r = put(client, [{"host": "192.168.1.13", "port": 6900}])
    assert r.status_code == 404 and r.json()["detail"]["reason"] == "not_public_listener"
    [rec] = audit(tmp_path)
    assert (rec["action"], rec["reason"], rec["listener"]) == ("refused", "not_public_listener", 80)
    assert not (tmp_path / "settings" / "allowlist.json").exists()
    # the audit log is the console's, not the agent's
    assert client.get("/settings/audit").status_code == 404


def test_the_agent_network_is_refused_before_any_route(make: Make, tmp_path: Path) -> None:
    client = make(peer=("10.210.97.7", 1))  # ADR-0005 c2: AgentNetworkGuard, outermost layer
    for r in (client.get("/settings/servers", headers=H),
              put(client, [{"host": "192.168.1.13", "port": 6900}])):  # fmt: skip
        assert r.status_code == 403 and r.json()["detail"]["reason"] == "agent_network"
    assert not (tmp_path / "settings" / "allowlist.json").exists()


@pytest.mark.parametrize(
    ("host", "port", "reason"),
    [
        ("*.example.com", 6900, "wildcard"),
        ("", 6900, "empty_host"),
        ("0.0.0.0", 6900, "unspecified_address"),
        ("127.0.0.1", 6900, "loopback"),
        ("localhost", 6900, "loopback"),
        ("169.254.1.1", 6900, "link_local"),
        ("::1", 6900, "ipv6_not_supported"),
        ("a b.example", 6900, "bad_host"),
        ("192.168.1.13", 0, "bad_port"),
        ("192.168.1.13", 70000, "bad_port"),
        ("kro-assit.ragnarok.co.kr", 3000, "forbidden_endpoint"),
        ("KRO-Assit.Ragnarok.co.kr", 3000, "forbidden_endpoint"),  # names are case-insensitive
        ("anything.ragnarok.co.kr", 6900, "forbidden_endpoint"),  # the whole official domain
        ("ragnarok.co.kr", 6900, "forbidden_endpoint"),
        ("thro-acc3.gnjoy.in.th", 50001, "forbidden_endpoint"),
        ("49.229.28.99", 3000, "forbidden_endpoint"),
        ("49.229.28.13", 6900, "forbidden_endpoint"),  # an IP forbidden on any port
    ],
)  # fmt: skip
def test_entries_are_validated(make: Make, tmp_path: Path, host: str, port: int,
                               reason: str) -> None:  # fmt: skip
    client = make()
    r = put(client, [{"host": host, "port": port}])
    assert r.status_code == 422, r.text
    assert r.json()["detail"]["reason"] == reason
    assert not (tmp_path / "settings" / "allowlist.json").exists()
    assert audit(tmp_path)[-1]["reason"] == reason


def test_a_port_specific_forbidden_ip_allows_its_other_ports(make: Make) -> None:
    client = make()
    assert put(client, [{"host": "49.229.28.99", "port": 6900}]).status_code == 200


def test_a_name_resolving_to_a_forbidden_ip_is_refused(
    make: Make, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def evil(host: str) -> list[str]:
        return ["49.229.28.13"]

    monkeypatch.setattr(routes_settings, "resolve", evil)
    client = make()
    r = put(client, [{"host": "innocent.example", "port": 6900}])
    assert r.status_code == 422 and r.json()["detail"]["reason"] == "forbidden_endpoint"


def test_a_dns_name_is_stored_lower_case_with_its_resolved_ips(
    make: Make, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def lan(host: str) -> list[str]:
        return ["192.168.1.77"]

    monkeypatch.setattr(routes_settings, "resolve", lan)
    client = make()
    body = put(client, [{"host": "RO.Example.Net", "port": 6900}]).json()
    [entry] = env_view(body)["entries"]
    assert (entry["host"], entry["resolved"]) == ("ro.example.net", ["192.168.1.77"])


def test_duplicates_and_stale_revisions_are_refused(make: Make, tmp_path: Path) -> None:
    client = make()
    r = put(
        client, [{"host": "192.168.1.13", "port": 6900}, {"host": "192.168.1.13", "port": 6900}]
    )
    assert r.json()["detail"]["reason"] == "duplicate"
    put(client, [{"host": "192.168.1.13", "port": 6900}])
    r = put(client, [], rev=0)  # someone else saved revision 1 meanwhile
    assert r.status_code == 409
    assert r.json()["detail"] == {"reason": "stale_revision", "revision": 1}
    assert audit(tmp_path)[-1]["reason"] == "stale_revision"


@pytest.mark.parametrize(
    ("env", "status", "reason"),
    [
        ("community", 422, "environment_pending"),
        ("official-ro-korea", 422, "environment_forbidden"),
        ("nowhere", 404, "unknown_environment"),
    ],
)  # fmt: skip
def test_only_allowed_environments_hold_servers(
    make: Make, env: str, status: int, reason: str
) -> None:
    client = make()
    r = put(client, [{"host": "192.168.1.13", "port": 6900}], env=env)
    assert r.status_code == status and r.json()["detail"]["reason"] == reason


def test_extra_fields_and_huge_bodies_are_refused(make: Make) -> None:
    client = make()
    r = client.put("/settings/servers/lab-rathena", headers=H,
                   json={"base_revision": 0, "entries": [], "allow_all": True})  # fmt: skip
    assert r.status_code == 422 and r.json()["detail"]["reason"] == "invalid"
    r = client.put("/settings/servers/lab-rathena", headers=H, content=b"x" * (64 * 1024 + 1))
    assert r.status_code == 413


def test_a_missing_store_refuses_and_is_never_created(make: Make, tmp_path: Path) -> None:
    client = make(settings_dir=tmp_path / "absent")
    r = put(client, [{"host": "192.168.1.13", "port": 6900}])
    assert r.status_code == 503 and r.json()["detail"]["reason"] == "settings_store_missing"
    assert not (tmp_path / "absent").exists()
    assert client.get("/health").json()["allowlist"]["store"] == "settings_store_missing"


def test_the_audit_page_lists_newest_first(make: Make) -> None:
    client = make()
    put(client, [{"host": "192.168.1.13", "port": 6900}])
    put(client, [], rev=1)
    records = client.get("/settings/audit", headers=H).json()["records"]
    assert [r["action"] for r in records] == ["remove", "add"]
