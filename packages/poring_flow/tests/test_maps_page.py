"""The Maps page's facts (services/frontend/src/lib/maps, 2026-11-10; docs/planning/
world-map-flows.md) checked against the sources they are copied from, on the host (the frontend
container serves services/frontend only):

- its trace fixture is this simulator's own output (synthetic sample sheets);
- the Login node's server list is config/environments.yaml's (ids and statuses, in order) and only
  the lab's rAthena is selectable;
- the session mock's Python names scripts/ro_agent.py's real functions with their real parameters.
"""

from __future__ import annotations

import ast
import json
import re
from pathlib import Path

import yaml  # type: ignore[import-untyped]  # no stubs in the dev env

from poring_flow import editor, ir
from poring_flow.trace import Scenario, simulate

REPO = Path(__file__).resolve().parents[3]
LIB = REPO / "services/frontend/src/lib"
SESSION_TS = (LIB / "maps/session.ts").read_text(encoding="utf-8")


def test_the_maps_pages_fixture_is_the_simulators_output() -> None:
    """lib/maps/fixtures/starter_trace.json (maps.test.ts reads it): the two-map starter on the
    SYNTHETIC sample sheets. Regenerate it with this same call when the trace changes."""
    flow = ir.from_json((LIB / "flow/fixtures/starter.json").read_text())
    world = editor.sample_world(editor.maps_of(flow))
    doc = simulate(flow, world, Scenario(horizon_s=60, encounters=True, seed=3))
    fixture = json.loads((LIB / "maps/fixtures/starter_trace.json").read_text())
    assert fixture == json.loads(json.dumps(doc))


def test_the_login_servers_are_the_environment_allowlist() -> None:
    envs = yaml.safe_load((REPO / "config/environments.yaml").read_text(encoding="utf-8"))
    want = [(e["id"], e["status"]) for e in envs["environments"]]
    got = re.findall(r'id: "([a-z0-9-]+)",\s*title: "[^"]*",\s*status: "([a-z]+)"', SESSION_TS)
    assert got == want
    selectable = re.findall(r'id: "([a-z0-9-]+)",[^}]*?automatable: true', SESSION_TS, re.S)
    assert selectable == ["lab-rathena"]


def _signatures() -> dict[str, list[str]]:
    tree = ast.parse((REPO / "scripts/ro_agent.py").read_text(encoding="utf-8"))
    return {
        n.name: [a.arg for a in n.args.args] for n in tree.body if isinstance(n, ast.FunctionDef)
    }


def test_the_session_mock_names_ro_agents_real_calls() -> None:
    sig = _signatures()
    assert sig["to_char_select"] == ["agent", "screen", "which"]
    assert sig["enter_game"] == ["agent", "screen", "which", "char"]
    assert sig["login"] == ["agent", "screen", "which"]
    assert sig["session"][0] == "name"
    assert sig["account"] == ["which"]  # .env: <prefix>_GM_* / <prefix>_AGENT_*
    for call in ("to_char_select(agent, screen, ", "enter_game(agent, screen, ", 'session("'):
        assert call in SESSION_TS, call
    src = (REPO / "scripts/ro_agent.py").read_text(encoding="utf-8")
    assert '{"player": "AGENT", "gm": "GM"}[which]' in src
    assert 'elif cmd == "login":' in src  # `ro_agent.py login gm`, as the mock's comment says
