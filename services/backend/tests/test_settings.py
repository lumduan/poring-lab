"""The Settings page: the USER-MANAGED environment set (Batt, 2026-10-06; ADR-0016).

Environments are created, renamed, deleted and edited by people on the page. The shipped defaults
are only a starting set, seeded ONCE into the store; then the store is the only source (the
interlock fails closed when it is missing or invalid). Writes are HUMAN-ONLY: a LAN browser with the
console's Origin -- never the agent's :8001, the agent network, host scripts/containers (gateway),
the lab host itself or the Windows host the bot drives. Changes are ASYMMETRIC: tightening is easy,
loosening an allowed list is normal, loosening a FORBIDDEN list is hard (typed reason + the subject
typed again, one per save). Everything is audited.
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
    title: Lab rAthena
    summary: The lab's own rAthena server.
    status: allowed
    adr: ADR-0006
    server: {host: 192.168.1.13, ports: [6900, 5121]}
    windows_host: 192.168.1.169
    accounts: [2000001]
    signals: [lab_host, session]
  - id: community
    title: Community bot-testing server
    summary: Not approved yet; the owner's permission is not on file.
    status: pending
    adr: ADR-0006
    signals: []
  - id: official-ro-thai
    title: Official Thai RO
    status: forbidden
    adr: ADR-0006
    server: {host: thro-acc3.gnjoy.in.th, ports: [50001, 3000]}
    forbidden_endpoints: [.gnjoy.in.th, "49.229.28.99:3000", 49.229.28.13]
  - id: official-ro-korea
    title: Official Korean RO
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
DNS: dict[str, list[str]] = {}


@pytest.fixture
def make(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Make]:
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "environments.yaml").write_text(ENVS)
    (tmp_path / "settings").mkdir()
    DNS.clear()

    async def fake_dns(host: str) -> list[str]:  # tests never touch the network
        return DNS.get(host, [host] if host.replace(".", "").isdigit() else [])

    monkeypatch.setattr(routes_settings, "resolve", fake_dns)
    clients: list[TestClient] = []

    def factory(peer: tuple[str, int] = LAN, **overrides: Any) -> TestClient:
        fields: dict[str, Any] = {
            "data_dir": tmp_path / "data", "public_port": 80, "frontend_origins": ORIGIN,
            "status_hz": 20.0, "environments_file": tmp_path / "config" / "environments.yaml",
            "settings_dir": tmp_path / "settings", "lab_state_dir": tmp_path / "lab-state",
            "host_lan_ip": "192.168.1.13", "win_host": "192.168.1.169",
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


def get(client: TestClient) -> dict[str, Any]:
    r = client.get("/settings/environments", headers=H)
    assert r.status_code == 200, r.text
    return r.json()  # type: ignore[no-any-return]


def env(view: dict[str, Any], env_id: str) -> dict[str, Any]:
    return next(e for e in view["environments"] if e["id"] == env_id)


def as_input(view: dict[str, Any]) -> list[dict[str, Any]]:
    """The page's request: every environment's user fields."""
    return [{"id": e["id"], "name": e["name"], "type": e["type"], "summary": e["summary"],
             "why": e["why"], "servers": [{"host": s["host"], "port": s["port"], "note": s["note"]}
                                          for s in e["servers"]]}
            for e in view["environments"]]  # fmt: skip


def token(client: TestClient) -> str:
    return routes_settings.csrf_token(client.app.state.poring)  # type: ignore[attr-defined]


def put(client: TestClient, envs: list[dict[str, Any]], rev: int, headers: dict[str, str] = H,
        csrf: bool = True, **extra: Any) -> Any:  # fmt: skip
    body = {"base_revision": rev, "environments": envs, **extra}
    if csrf:
        headers = {**headers, "x-csrf-token": token(client)}
    return client.put("/settings/environments", headers=headers, json=body)


def edit(client: TestClient, change: Callable[[list[dict[str, Any]]], Any], **extra: Any) -> Any:
    view = get(client)
    envs = as_input(view)
    change(envs)
    return put(client, envs, view["revision"], **extra)


def find(envs: list[dict[str, Any]], env_id: str) -> dict[str, Any]:
    return next(e for e in envs if e["id"] == env_id)


def add_server(env_id: str, host: str, port: int | None) -> Callable[[list[dict[str, Any]]], None]:
    def change(envs: list[dict[str, Any]]) -> None:
        find(envs, env_id)["servers"].append({"host": host, "port": port})

    return change


def confirm_lab(client: TestClient) -> Any:
    def change(envs: list[dict[str, Any]]) -> None:
        find(envs, "lab-rathena")["servers"] = [{"host": "192.168.1.13", "port": 6900},
                                                {"host": "192.168.1.13", "port": 5121}]  # fmt: skip

    return edit(client, change)


# --- defaults, seed, and the store as the only source ---------------------------------------------


def test_the_defaults_are_seeded_once_allowed_servers_only_as_suggestions(
    make: Make, tmp_path: Path
) -> None:
    view = get(make())
    assert view["revision"] == 0 and len(view["seeded_from"]) == 64
    lab = env(view, "lab-rathena")
    assert (lab["name"], lab["type"], lab["servers"]) == ("Lab rAthena", "allowed", [])
    assert lab["suggestions"] == [{"host": "192.168.1.13", "port": 6900},
                                  {"host": "192.168.1.13", "port": 5121}]  # fmt: skip
    assert lab["ready"] is False  # no confirmed server: the bot cannot act there
    thai = {s["key"] for s in env(view, "official-ro-thai")["servers"]}
    assert thai == {"thro-acc3.gnjoy.in.th", ".gnjoy.in.th", "49.229.28.99:3000", "49.229.28.13"}
    assert env(view, "community")["summary"].startswith("Not approved yet")
    [seed] = audit(tmp_path)
    assert (seed["action"], seed["ok"]) == ("seed", True)
    assert (tmp_path / "settings" / ".environments-seeded").exists()


def test_the_interlock_reads_the_store_and_fails_closed(make: Make, tmp_path: Path) -> None:
    client = make()
    state = client.app.state.poring  # type: ignore[attr-defined]
    lab = next(e for e in state.interlock.config.environments if e.id == "lab-rathena")
    assert lab.servers == []  # seeded without servers -> red "no_servers" (test_interlock)
    confirm_lab(client)
    lab = next(e for e in state.interlock.config.environments if e.id == "lab-rathena")
    assert lab.servers == ["192.168.1.13:6900", "192.168.1.13:5121"]
    (tmp_path / "settings" / "environments.json").write_text("{not json")
    state.interlock.reload()
    assert (state.interlock.config, state.interlock.config_error) == (
        None, "environments_store_invalid")  # fmt: skip
    (tmp_path / "settings" / "environments.json").unlink()
    state.interlock.reload()  # NOT re-seeded: the marker says the store existed
    assert (state.interlock.config, state.interlock.config_error) == (
        None, "environments_store_missing")  # fmt: skip
    assert get(client)["store"] == "environments_store_missing"


def test_a_missing_settings_mount_refuses_and_is_never_created(make: Make, tmp_path: Path) -> None:
    client = make(settings_dir=tmp_path / "absent")
    state = client.app.state.poring  # type: ignore[attr-defined]
    assert state.interlock.config_error == "settings_store_missing"
    r = put(client, [], 0)
    assert r.status_code == 503 and r.json()["detail"]["reason"] == "settings_store_missing"
    assert not (tmp_path / "absent").exists()


# --- confirming servers (normal) and the audit ----------------------------------------------------


def test_confirming_the_suggested_servers_saves_reads_back_and_audits(
    make: Make, tmp_path: Path
) -> None:
    client = make()
    r = confirm_lab(client)
    assert r.status_code == 200, r.text
    body = r.json()
    assert (body["saved"], body["read_back"], body["revision"]) == (True, True, 1)
    lab = env(body, "lab-rathena")
    assert [s["key"] for s in lab["servers"]] == ["192.168.1.13:6900", "192.168.1.13:5121"]
    assert (lab["suggestions"], lab["ready"]) == ([], True)
    adds = [r for r in audit(tmp_path) if r["action"] == "server_add"]
    assert {(a["entry"], a["kind"]) for a in adds} == {
        ("192.168.1.13:6900", "normal"), ("192.168.1.13:5121", "normal")}  # fmt: skip
    assert (adds[0]["client"], adds[0]["origin"], adds[0]["listener"]) == (LAN[0], ORIGIN, 80)
    stored = json.loads((tmp_path / "settings" / "environments.json").read_text())
    assert stored["revision"] == 1


def test_an_unchanged_set_writes_nothing(make: Make, tmp_path: Path) -> None:
    client = make()
    view = get(client)
    r = put(client, as_input(view), 0)
    assert r.json()["saved"] is False and len(audit(tmp_path)) == 1  # the seed only


# --- who may write --------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("peer", "overrides", "headers", "reason"),
    [
        (LAN, {}, {}, "origin_required"),
        (LAN, {}, {"origin": "http://evil.test"}, "origin_not_allowed"),
        (("10.210.96.1", 1), {}, H, "compose_peer"),  # host scripts/containers via the gateway
        (("8.8.8.8", 1), {}, H, "not_a_lan_viewer"),
        (LAN, {"public_port": 8000, "internal_port": 80}, H, "not_public_listener"),  # :8001
        (("192.168.1.13", 1), {}, H, "lab_host_peer"),  # host processes can forge the Origin
        (("192.168.1.169", 1), {}, H, "windows_host_peer"),  # the desktop the bot drives
    ],
)  # fmt: skip
def test_only_a_person_at_their_own_browser_may_write(
    make: Make, tmp_path: Path, peer: tuple[str, int], overrides: dict[str, Any],
    headers: dict[str, str], reason: str,
) -> None:  # fmt: skip
    client = make(peer=peer, **overrides)
    r = put(client, [], 0, headers=headers)
    assert r.json()["detail"]["reason"] == reason
    rec = audit(tmp_path)[-1]
    assert (rec["action"], rec["ok"], rec["reason"], rec["client"]) == (
        "refused", False, reason, peer[0])  # fmt: skip
    assert json.loads((tmp_path / "settings" / "environments.json").read_text())["revision"] == 0
    drops = client.get("/health").json()["dropped_messages"]["settings_http"]
    assert drops[reason] == 1


def test_the_agent_listener_can_read_but_never_write(make: Make) -> None:
    client = make(public_port=8000, internal_port=80)
    assert client.get("/settings/environments").status_code == 200  # no Origin: the agent
    assert client.get("/settings/audit").status_code == 404  # the history is the console's
    assert client.get("/settings/environments/export").status_code == 404


def test_the_agent_network_is_refused_before_any_route(make: Make) -> None:
    client = make(peer=("10.210.97.7", 1))
    for r in (client.get("/settings/environments", headers=H), put(client, [], 0)):
        assert r.status_code == 403 and r.json()["detail"]["reason"] == "agent_network"


# --- validation -----------------------------------------------------------------------------------


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
        ("<script>alert(1)</script>", 6900, "bad_host"),
        ("192.168.1.13", 0, "bad_port"),
        ("192.168.1.13", 70000, "bad_port"),
        ("192.168.1.13", None, "port_required"),
        (".example.com", 6900, "domain_not_allowed_here"),
        ("kro-assit.ragnarok.co.kr", 3000, "forbidden_endpoint"),
        ("KRO-Assit.Ragnarok.co.kr", 3000, "forbidden_endpoint"),
        ("anything.ragnarok.co.kr", 6900, "forbidden_endpoint"),
        ("thro-acc3.gnjoy.in.th", 50001, "forbidden_endpoint"),
        ("49.229.28.99", 3000, "forbidden_endpoint"),
        ("49.229.28.13", 6900, "forbidden_endpoint"),
    ],
)  # fmt: skip
def test_allowed_servers_are_validated(make: Make, tmp_path: Path, host: str, port: int | None,
                                       reason: str) -> None:  # fmt: skip
    r = edit(make(), add_server("lab-rathena", host, port))
    assert r.status_code == 422, r.text
    assert r.json()["detail"]["reason"] == reason
    assert audit(tmp_path)[-1]["reason"] == reason


def test_a_port_specific_forbidden_ip_allows_its_other_ports(make: Make) -> None:
    r = edit(make(), add_server("lab-rathena", "49.229.28.99", 6900))
    assert r.status_code == 200, r.text


def test_resolved_ips_block_unless_they_sit_in_a_cdn_range(make: Make) -> None:
    DNS.update({"official2.example.com": ["203.0.113.9"], "cdn-hosted.example.com": ["104.16.1.1"]})
    client = make()

    def block(envs: list[dict[str, Any]]) -> None:
        find(envs, "official-ro-korea")["servers"] += [
            {"host": "official2.example.com"}, {"host": "cdn-hosted.example.com"}]  # fmt: skip

    body = edit(client, block).json()
    shown = {s["key"]: s["resolved"] for s in env(body, "official-ro-korea")["servers"]}
    assert shown["official2.example.com"] == [{"ip": "203.0.113.9", "cdn": None}]
    assert shown["cdn-hosted.example.com"] == [{"ip": "104.16.1.1", "cdn": "cloudflare"}]
    r = edit(client, add_server("lab-rathena", "203.0.113.9", 6900))
    assert r.json()["detail"]["reason"] == "forbidden_endpoint"  # the official server's own IP
    r = edit(client, add_server("lab-rathena", "104.16.1.1", 6900))
    assert r.status_code == 200  # a shared CDN address is matched by NAME only


def test_a_name_resolving_to_a_forbidden_ip_is_refused(make: Make) -> None:
    DNS["innocent.example.com"] = ["49.229.28.13"]
    r = edit(make(), add_server("lab-rathena", "innocent.example.com", 6900))
    assert r.json()["detail"]["reason"] == "forbidden_endpoint"


# --- the asymmetric rules -------------------------------------------------------------------------


def test_tightening_is_easy(make: Make, tmp_path: Path) -> None:
    client = make()
    confirm_lab(client)
    seen = len(audit(tmp_path))

    def tighten(envs: list[dict[str, Any]]) -> None:
        servers = [{"host": "ro.asiasoft.co.th"}, {"host": ".asiasoft.co.th"}]
        envs.append({"name": "Old Asiasoft Thai RO", "type": "forbidden",
                     "summary": "The old Thai official servers.", "servers": servers})  # fmt: skip
        find(envs, "official-ro-korea")["servers"].append({"host": "new-assist.example.com",
                                                           "port": 3000})  # fmt: skip
        find(envs, "lab-rathena")["servers"].pop()  # shrinking an allowed list

    r = edit(client, tighten)
    assert r.status_code == 200, r.text
    created = next(e for e in r.json()["environments"] if e["name"] == "Old Asiasoft Thai RO")
    assert created["id"] == "old-asiasoft-thai-ro" and created["type"] == "forbidden"
    kinds = {(a["action"], a["kind"]) for a in audit(tmp_path)[seen:]}
    assert kinds == {("env_create", "easy"), ("server_add", "easy"), ("server_remove", "easy")}
    edit(client, lambda envs: find(envs, "lab-rathena").update(type="pending"))
    assert audit(tmp_path)[-1]["kind"] == "easy"
    edit(client, lambda envs: envs.remove(find(envs, "lab-rathena")))  # pending -> deleted
    assert audit(tmp_path)[-1]["action"] == "env_delete"


def test_loosening_an_allowed_list_is_normal(make: Make, tmp_path: Path) -> None:
    client = make()

    def loosen(envs: list[dict[str, Any]]) -> None:
        envs.append({"name": "My private server", "type": "allowed",
                     "servers": [{"host": "ro.my-guild.example", "port": 6900}]})  # fmt: skip
        find(envs, "community").update(type="allowed", name="Community (approved)")

    r = edit(client, loosen)
    assert r.status_code == 200, r.text
    kinds = {(a["action"], a["kind"]) for a in audit(tmp_path)[1:]}
    assert kinds == {("env_create", "normal"), ("server_add", "normal"), ("env_rename", "normal"),
                     ("env_type", "normal")}  # fmt: skip


def remove_thai_stage(envs: list[dict[str, Any]]) -> None:
    servers = find(envs, "official-ro-thai")["servers"]
    servers[:] = [s for s in servers if (s["host"], s["port"]) != ("49.229.28.99", 3000)]


@pytest.mark.parametrize(
    ("change", "subject"),
    [
        (remove_thai_stage, "49.229.28.99:3000"),
        (lambda envs: envs.remove(find(envs, "official-ro-korea")), "Official Korean RO"),
        (lambda envs: find(envs, "official-ro-korea").update(type="pending"), "Official Korean RO"),
    ],
)  # fmt: skip
def test_loosening_a_forbidden_list_is_hard(make: Make, tmp_path: Path, change: Any,
                                            subject: str) -> None:  # fmt: skip
    client = make()
    r = edit(client, change)
    assert r.json()["detail"] == {"reason": "reason_required", "subject": subject}
    r = edit(client, change, reason="the server was retired in 2026", confirm="something else")
    assert r.json()["detail"] == {"reason": "confirm_mismatch", "subject": subject}
    r = edit(client, change, reason="the server was retired in 2026", confirm=subject.upper())
    assert r.status_code == 200, r.text
    rec = audit(tmp_path)[-1]
    assert (rec["kind"], rec["entry"], rec["note"]) == (
        "hard", subject, "the server was retired in 2026")  # fmt: skip
    assert [r["reason"] for r in audit(tmp_path)[-3:-1]] == ["reason_required", "confirm_mismatch"]


def test_forbidden_to_allowed_is_hard_and_only_one_hard_change_per_save(make: Make) -> None:
    client = make()

    def two(envs: list[dict[str, Any]]) -> None:
        envs.remove(find(envs, "official-ro-korea"))
        remove_thai_stage(envs)

    r = edit(client, two, reason="cleaning up old entries", confirm="x")
    assert r.json()["detail"]["reason"] == "one_hard_change_at_a_time"
    r = edit(client, lambda envs: find(envs, "official-ro-korea").update(
        type="allowed", servers=[]))  # fmt: skip
    assert r.json()["detail"]["reason"] in ("reason_required", "one_hard_change_at_a_time")


def test_an_allowed_server_that_becomes_forbidden_is_flagged(make: Make) -> None:
    client = make()
    confirm_lab(client)
    body = edit(client, add_server("official-ro-korea", "192.168.1.13", 6900)).json()
    flags = {s["key"]: s["forbidden"] for s in env(body, "lab-rathena")["servers"]}
    assert flags == {"192.168.1.13:6900": True, "192.168.1.13:5121": False}


def test_names_are_unique_and_ids_are_stable(make: Make) -> None:
    client = make()
    r = edit(client, lambda envs: envs.append({"name": "lab rathena", "type": "pending"}))
    assert r.json()["detail"]["reason"] == "duplicate_name"
    r = edit(client, lambda envs: find(envs, "lab-rathena").update(name="Renamed lab"))
    assert env(r.json(), "lab-rathena")["name"] == "Renamed lab"  # the id stays: the sniffer's


def test_stale_revisions_are_refused(make: Make) -> None:
    client = make()
    view = get(client)
    confirm_lab(client)
    r = put(client, as_input(view), view["revision"])
    assert r.status_code == 409
    assert r.json()["detail"] == {"reason": "stale_revision", "revision": 1}


def test_technical_fields_never_come_from_a_request(make: Make) -> None:
    client = make()
    envs = as_input(get(client))
    find(envs, "lab-rathena")["accounts"] = [1]  # not a user field
    r = put(client, envs, 0)
    assert r.status_code == 422 and r.json()["detail"]["reason"] == "invalid"


# --- export / import ------------------------------------------------------------------------------


def test_export_and_import_share_a_setup_under_the_same_rules(make: Make, tmp_path: Path) -> None:
    client = make()
    confirm_lab(client)
    r = client.get("/settings/environments/export", headers=H)
    assert r.status_code == 200 and "attachment" in r.headers["content-disposition"]
    doc = r.json()
    assert doc["format"] == "poring-lab-environments/1"
    assert "accounts" not in json.dumps(doc) and "windows_host" not in json.dumps(doc)
    # the course's set: one more forbidden server (easy), imported as one change
    find(doc["environments"], "official-ro-thai")["servers"].append(
        {"host": "old.gnjoy-mirror.example", "port": None, "note": ""})  # fmt: skip
    r = put(client, doc["environments"], 1, source="import")
    assert r.status_code == 200, r.text
    assert env(r.json(), "lab-rathena")["signals"] == ["lab_host", "session"]  # kept, not imported
    assert audit(tmp_path)[-1]["reason"] == "import"
    find(doc["environments"], "official-ro-thai")["servers"] = []  # loosening: still hard
    r = put(client, doc["environments"], 2, source="import")
    assert r.json()["detail"]["reason"] == "one_hard_change_at_a_time"


def test_extra_fields_and_huge_bodies_are_refused(make: Make) -> None:
    client = make()
    hdr = {**H, "x-csrf-token": token(client)}
    r = client.put("/settings/environments", headers=hdr,
                   json={"base_revision": 0, "environments": [], "allow_all": True})  # fmt: skip
    assert r.status_code == 422 and r.json()["detail"]["reason"] == "invalid"
    r = client.put("/settings/environments", headers=hdr, content=b"x" * (64 * 1024 + 1))
    assert r.status_code == 413


def test_the_audit_page_lists_newest_first(make: Make) -> None:
    client = make()
    confirm_lab(client)
    records = client.get("/settings/audit", headers=H).json()["records"]
    assert records[-1]["action"] == "seed" and records[0]["action"] == "server_add"


# --- CSRF, rate limit, control characters (Batt's hostile-input controls, 2026-10-06) -------------


def test_a_write_without_the_csrf_token_is_refused(make: Make, tmp_path: Path) -> None:
    client = make()
    view = get(client)
    r = put(client, as_input(view), 0, csrf=False)
    assert r.status_code == 403 and r.json()["detail"]["reason"] == "csrf_invalid"
    forged = {**H, "x-csrf-token": "9999999999." + "0" * 64}
    r = client.put("/settings/environments", headers=forged,
                   json={"base_revision": 0, "environments": as_input(view)})  # fmt: skip
    assert r.json()["detail"]["reason"] == "csrf_invalid"
    expired = routes_settings.csrf_token(client.app.state.poring, now=0)  # type: ignore[attr-defined]
    r = client.put("/settings/environments", headers={**H, "x-csrf-token": expired},
                   json={"base_revision": 0, "environments": as_input(view)})  # fmt: skip
    assert r.json()["detail"]["reason"] == "csrf_invalid"
    assert [a["reason"] for a in audit(tmp_path)[-3:]] == ["csrf_invalid"] * 3


def test_only_the_console_browser_gets_a_token(make: Make) -> None:
    client = make()
    r = client.get("/settings/csrf", headers=H)
    assert r.status_code == 200
    state = client.app.state.poring  # type: ignore[attr-defined]
    assert routes_settings.csrf_valid(state, r.json()["token"])
    assert client.get("/settings/csrf").json()["detail"]["reason"] == "origin_required"
    assert make(public_port=8000, internal_port=80).get("/settings/csrf").status_code == 404


def test_settings_writes_are_rate_limited(make: Make, tmp_path: Path) -> None:
    client = make()
    view = get(client)
    statuses = [put(client, as_input(view), 0).status_code for _ in range(21)]
    assert statuses[:20] == [200] * 20 and statuses[20] == 429
    assert audit(tmp_path)[-1]["reason"] == "rate_limited"


def test_control_characters_never_reach_the_store_or_the_log(
    make: Make, caplog: pytest.LogCaptureFixture
) -> None:
    client = make()
    r = edit(client, lambda envs: envs.append(
        {"name": "Evil\x1b[31m\nname", "type": "forbidden", "summary": "a\rb"}))  # fmt: skip
    created = next(e for e in r.json()["environments"] if e["name"].startswith("Evil"))
    assert (created["name"], created["summary"]) == ("Evil[31mname", "ab")
    assert not any("\x1b" in rec.getMessage() or "\n" in rec.getMessage()
                   for rec in caplog.records)  # fmt: skip


def test_endpoints_from_a_game_file_keep_their_source_and_nothing_else_passes(
    make: Make, tmp_path: Path
) -> None:
    """The finder sends only the endpoints a person ticked, marked source "file", through the
    same PUT: same grammar, same rules. A made-up source, or a hostile host, is refused."""
    client = make()

    def block(envs: list[dict[str, Any]]) -> None:
        envs.append({"name": "Found in data.grf", "type": "forbidden", "servers": [
            {"host": "203.0.113.7", "port": 6900, "note": "found in data.grf: data\\clientinfo.xml",
             "source": "file"}]})  # fmt: skip

    r = edit(client, block)
    assert r.status_code == 200, r.text
    made = next(e for e in r.json()["environments"] if e["name"] == "Found in data.grf")
    assert made["type"] == "forbidden"
    assert [(s["host"], s["port"], s["source"]) for s in made["servers"]] == [
        ("203.0.113.7", 6900, "file")]  # fmt: skip
    assert any(a["action"] == "env_create" and a["ok"] for a in audit(tmp_path))

    def made_up(envs: list[dict[str, Any]]) -> None:
        find(envs, "lab-rathena")["servers"].append(
            {"host": "192.168.1.13", "port": 6900, "source": "trusted-by-file"}
        )

    assert edit(client, made_up).status_code == 422
    for host in ("<script>alert(1)</script>", "javascript:alert(1)", "evil.example.com/x"):
        r = edit(client, lambda envs, h=host: find(envs, "lab-rathena")["servers"].append(
            {"host": h, "port": 6900, "source": "file"}))  # fmt: skip
        assert r.status_code == 422 and r.json()["detail"]["reason"] == "bad_host", (host, r.text)


def test_a_malformed_content_length_is_refused_not_a_crash(make: Make) -> None:
    client = make()
    hdr = {**H, "x-csrf-token": token(client), "content-length": "12abc",
           "content-type": "application/json"}  # fmt: skip
    r = client.put("/settings/environments", headers=hdr, content=b"{}" + b" " * 10)
    assert r.status_code == 413
