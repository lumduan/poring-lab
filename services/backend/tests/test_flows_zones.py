"""B2's zones layer (blocks-from-hunt-flow.md section 3; ADR-0020 Amendment A 4, DRAFT; Batt D6
2026-10-21: export only): the runner's OWN loader on the editor's YAML text -- the same errors as
the CLI over the loader's whole error corpus, the sha256 of the bytes, each item's cells as the
loader rasterises them, the sealed pieces and the search area; the file as the editor imports it
(never its reviewer); the editor's form reproduced byte for byte by its hand-written twins; the
routes' gates; the linter's zones provider wired into /flows/lint. Nothing is ever written."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
import yaml

from poring_backend import flows_zones

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "scripts"))
import map_zones as mz  # noqa: E402

TS_ZONES = REPO / "services/frontend/src/lib/flow/fixtures/zones"
CONFIG_ZONES = REPO / "config/map_zones"


def _load_tmz() -> Any:
    """The loader's own test module: its fixture map and its error corpus (one corpus, not two)."""
    spec = importlib.util.spec_from_file_location(
        "_tmz_corpus", Path(__file__).with_name("test_map_zones.py")
    )
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


TMZ = _load_tmz()
ENG = flows_zones.engine(None)
assert ENG is not None


def fixture_rows() -> list[str]:
    ok = TMZ.fixture_map()
    return ["".join("." if v else "#" for v in row) for row in ok]


def corpus() -> list[tuple[str, str]]:
    """(name, text) of every refused file in the loader's tests: the parametrized corpus of
    test_a_wrong_file_refuses_the_run, then the delegated-review cases (test_map_zones's own
    transformations of DELEGATED / GOOD)."""
    mark = next(m for m in TMZ.test_a_wrong_file_refuses_the_run.pytestmark
                if m.name == "parametrize")  # fmt: skip
    out = [(f"{i:02d} {why}", change(TMZ.GOOD)) for i, (change, why) in enumerate(mark.args[1])]
    d, g = TMZ.DELEGATED, TMZ.GOOD
    note = 'delegation: "Batt 2026-10-21, decision 1: zone authoring delegated"\n'
    out += [
        ("d1 needs a `delegation` note", d.replace(note, "")),
        ("d2 never approves", d.replace("delegated by batt", "delegated by claude")),
        ("d3 never approves", d.replace("delegated by batt", "approved by batt")),
        ("d4 never approves", d.replace("batt, 2026-10-21)", "batt)")),
        ("d5 not a date", d.replace("batt, 2026-10-21)", "batt, 2026-13-40)")),
        ("d6 never approves", d.replace('"agent (delegated', '"agent and claude (delegated')),
        ("d7 only a delegated reviewer",
         g.replace("reviewed_by: batt\n", 'reviewed_by: batt\ndelegation: "x"\n')),
    ]  # fmt: skip
    return out


def cli_error(tmp: Path, text: str, monkeypatch: pytest.MonkeyPatch) -> str:
    """What `map_zones.py check` prints for the file, run from the repo root (a relative root, so
    the message names config/map_zones/<map>.yaml as the route does)."""
    root = tmp / "config" / "map_zones"
    root.mkdir(parents=True, exist_ok=True)
    (root / "fix_map.yaml").write_text(text, encoding="utf-8")
    monkeypatch.chdir(tmp)
    try:
        mz.load("fix_map", Path("config/map_zones"), shape=(TMZ.H, TMZ.W))
    except mz.ZoneError as e:
        return str(e)
    return ""


# --- the committed fixtures (the frontend's tests read them; regenerate, never hand-edit) --------
def _model_doc(path_dir: Path, map_name: str) -> str:
    doc = flows_zones.read_file(ENG, path_dir, map_name, None)
    out = {
        "map": map_name,
        "sha256": doc["file"]["sha256"],
        "model": doc["model"],
        # the review a PERSON types at export (the file's own, from the loader): the editor never
        # fills it from a file -- the twin tests type it
        "review": {k: (v or "") for k, v in doc["file"]["review"].items()},
        "notes": doc["notes"],
    }
    return json.dumps(out, indent=1, ensure_ascii=False) + "\n"


def fixture_docs() -> dict[str, str]:
    """Every generated fixture: name -> text (scripts/gen_zones_fixtures.py writes them)."""
    errors = []
    rows = fixture_rows()
    with _empty_dir() as empty:
        for name, text in corpus():
            r = flows_zones.check(ENG, text, "fix_map", rows, empty)
            assert not r["ok"], name
            errors.append({"name": name, "yaml": text, "error": r["error"]})
    return {
        "prt_fild08.yaml": (CONFIG_ZONES / "prt_fild08.yaml").read_text(encoding="utf-8"),
        "prt_fild08.json": _model_doc(CONFIG_ZONES, "prt_fild08"),
        "syn_zones.json": _model_doc(TS_ZONES, "syn_zones"),
        "errors.json": json.dumps(errors, indent=1, ensure_ascii=False) + "\n",
    }


class _empty_dir:
    def __enter__(self) -> Path:
        import tempfile

        self._d = tempfile.TemporaryDirectory(dir="/dev/shm")
        return Path(self._d.name)

    def __exit__(self, *exc: object) -> None:
        self._d.cleanup()


def test_the_frontends_zones_fixtures_are_current() -> None:
    """Regenerate with: python scripts/gen_zones_fixtures.py"""
    for name, text in fixture_docs().items():
        p = TS_ZONES / name
        assert p.exists(), f"{name}: run scripts/gen_zones_fixtures.py"
        assert p.read_text(encoding="utf-8") == text, (
            f"{name} is stale: scripts/gen_zones_fixtures.py"
        )


# --- the acceptance: an editor-made file loads with the sha of its hand-written twin ------------
def test_the_hand_written_twins_load_with_the_sha_of_their_bytes() -> None:
    """The twins the frontend's zones.test.ts reproduces CLICK BY CLICK from the editor's form:
    the loader takes them, and its sha256 is the sha256 of the bytes the editor writes."""
    for root, name in ((CONFIG_ZONES, "prt_fild08"), (TS_ZONES, "syn_zones")):
        z = mz.load(name, root)
        assert z is not None
        raw = (root / f"{name}.yaml").read_bytes()
        assert z.sha256 == hashlib.sha256(raw).hexdigest()
        doc = json.loads((TS_ZONES / f"{name}.json").read_text(encoding="utf-8"))
        assert doc["sha256"] == z.sha256 and doc["notes"] == []
    # the committed prt_fild08 file IS the editor's form: its fixture copy, byte for byte
    assert (TS_ZONES / "prt_fild08.yaml").read_bytes() == (
        CONFIG_ZONES / "prt_fild08.yaml"
    ).read_bytes()
    syn = mz.load("syn_zones", TS_ZONES)
    assert syn is not None
    assert [i.id for i in syn.no_cross] == ["door_1", "door 2"]
    assert syn.no_cross[1].note == 'the "north" gap, near the café (path\\cell)'
    assert syn.no_enter[0].polygon == ((50, 50), (60, 50), (60, 58), (50, 58))


# --- the check: the loader's verdict, exactly --------------------------------------------------
@pytest.mark.parametrize(("name", "text"), corpus(), ids=[n for n, _ in corpus()])
def test_every_corpus_error_is_the_clis_own_message(
    name: str, text: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    expected = cli_error(tmp_path, text, monkeypatch)
    assert expected, f"{name}: the loader accepts it?"
    r = flows_zones.check(ENG, text, "fix_map", fixture_rows(), tmp_path / "none")
    assert r["ok"] is False and r["error"] == expected
    assert r["sha256"] == hashlib.sha256(text.encode()).hexdigest()


def test_a_good_text_gives_the_loaders_cells_the_sealed_room_and_the_area(tmp_path: Path) -> None:
    rows = fixture_rows()
    r = flows_zones.check(ENG, TMZ.GOOD, "fix_map", rows, tmp_path)
    assert r["ok"] and r["error"] is None, r
    assert r["sha256"] == hashlib.sha256(TMZ.GOOD.encode()).hexdigest()
    assert r["shape"] == [TMZ.W, TMZ.H]
    line, room = r["items"]
    assert (line["kind"], line["id"], room["kind"], room["id"]) == (
        "no_cross",
        "nc1",
        "no_enter",
        "ne1",
    )
    # the line: the CLOSED supercover of its segment, as the loader rasterises it
    assert {tuple(c) for c in line["cells"]} == set(mz.supercover((28, 35), (31, 35), closed=True))
    # the area: every cell whose CENTRE is inside or on the polygon
    poly = ((16, 36), (44, 36), (44, 54), (16, 54))
    want = {(x, y) for x in range(TMZ.W) for y in range(TMZ.H) if mz.in_polygon((x, y), poly)}
    assert {tuple(c) for c in room["cells"]} == want and room["cell_count"] == len(want)
    # the preview: the zones' cells, nothing sealed (the room is itself no-enter), the field kept
    a = r["area"]
    ok = TMZ.fixture_map()
    zone = mz.no_cross_mask(mz.parse(yaml.safe_load(TMZ.GOOD), "fix_map"), ok.shape)
    assert a["walkable"] == int(ok.sum())
    assert a["zone_cells"] + a["cut_cells"] + a["main_cells"] + a["other_cells"] == a["walkable"]
    assert a["rows"][TMZ.FIELD[1]][TMZ.FIELD[0]] == "."
    assert a["rows"][TMZ.ROOM[1]][TMZ.ROOM[0]] == "z"
    assert zone[35, 29] and a["rows"][35][29] == "z"


def test_a_line_alone_seals_the_room_off_the_search_area(tmp_path: Path) -> None:
    """Batt 2026-10-21 (decision 1): a no-cross line SEALS a room -- the preview shows the room as
    cut off (`sealed_off`) and the largest piece is the field, where the start cell is drawn."""
    text = TMZ.GOOD.split("no_enter:")[0]
    r = flows_zones.check(ENG, text, "fix_map", fixture_rows(), tmp_path)
    assert r["ok"], r
    a = r["area"]
    rows = a["rows"]
    assert rows[TMZ.ROOM[1]][TMZ.ROOM[0]] == "c" and rows[TMZ.FIELD[1]][TMZ.FIELD[0]] == "."
    ok = TMZ.fixture_map()
    walk = ok.copy()
    after = mz.route_grid(walk, mz.parse(yaml.safe_load(text), "fix_map"))
    assert a["cut_cells"] == int(mz.sealed_off(walk, after).sum()) > 400


def test_no_walk_grid_still_checks_and_says_what_it_skips(tmp_path: Path) -> None:
    r = flows_zones.check(ENG, TMZ.GOOD.replace("[31, 35]", "[310, 35]"), "fix_map", None, tmp_path)
    assert r["ok"] and r["area"] is None and r["shape"] is None
    assert any("bounded" in n for n in r["notes"])


def test_the_diff_against_the_committed_file_and_nothing_is_written(tmp_path: Path) -> None:
    (tmp_path / "fix_map.yaml").write_text(TMZ.GOOD, encoding="utf-8")
    before = sorted((p.name, p.stat().st_mtime_ns) for p in tmp_path.iterdir())
    same = flows_zones.check(ENG, TMZ.GOOD, "fix_map", fixture_rows(), tmp_path)
    assert same["committed"]["same"] and same["committed"]["ok"] and same["diff"] == ""
    edited = TMZ.GOOD.replace("across the entrance", "across the door")
    r = flows_zones.check(ENG, edited, "fix_map", fixture_rows(), tmp_path)
    assert not r["committed"]["same"]
    assert "-    note: across the entrance\n+    note: across the door\n" in r["diff"]
    assert r["diff"].startswith("--- a/config/map_zones/fix_map.yaml\n")
    assert sorted((p.name, p.stat().st_mtime_ns) for p in tmp_path.iterdir()) == before


def test_the_import_never_fills_the_reviewer(tmp_path: Path) -> None:
    """The editor starts from the file's items and comment; the review is returned as a REFERENCE
    only (`file.review`), never in the model a person exports (the agent never approves)."""
    doc = flows_zones.read_file(ENG, CONFIG_ZONES, "prt_fild08", None)
    assert doc["file"]["ok"] and doc["file"]["exists"]
    assert set(doc["model"]) == {"map", "comment", "items"}
    assert doc["file"]["review"]["reviewed_by"] == "agent (delegated by batt, 2026-10-21)"
    assert [i["id"] for i in doc["model"]["items"]] == ["c1-door", "c3-door"]
    assert doc["model"]["comment"][0].startswith("prt_fild08's forbidden zones")
    missing = flows_zones.read_file(ENG, tmp_path, "fix_map", None)
    assert missing["file"]["exists"] is False and missing["model"] is None


def test_the_engine_import_restores_the_import_path(tmp_path: Path) -> None:
    before = list(sys.path)
    flows_zones._CACHE.clear()
    assert flows_zones.engine(REPO / "scripts") is not None
    assert sys.path == before
    flows_zones._CACHE.clear()


def test_the_routes_provider_comes_with_the_engine(tmp_path: Path) -> None:
    """flow_routes rides along with the zones engine (the same code directory); an engine without
    it gives no routes provider (a patrol hunt is then refused at run start), the zones kept."""
    flows_zones._CACHE.clear()
    eng = flows_zones.engine(REPO / "scripts")
    assert eng is not None and eng.fr is not None
    assert flows_zones.routes_provider(eng, tmp_path, {})("field_1") is None  # no file
    assert flows_zones.routes_provider(flows_zones.Engine(eng.mz, eng.fz), tmp_path, {}) is None
    flows_zones._CACHE.clear()


def test_without_the_loader_there_is_no_engine(monkeypatch: pytest.MonkeyPatch) -> None:
    flows_zones._CACHE.clear()

    def no(*a: Any) -> Any:
        raise ImportError("no map_zones here")

    monkeypatch.setattr(flows_zones, "_import", no)
    assert flows_zones.engine(None) is None
    assert flows_zones.engine(Path("/nonexistent")) is None
    flows_zones._CACHE.clear()


# --- the routes -----------------------------------------------------------------------------------
@pytest.fixture
def zclient(tmp_path: Path) -> Iterator[Any]:
    from fastapi.testclient import TestClient

    from poring_backend.config import Settings
    from poring_backend.main import create_app

    sys.path.insert(0, str(Path(__file__).parent))
    from test_routes_flows import LAN, ORIGIN, NoCapture, NoInput

    zd = tmp_path / "zones"
    zd.mkdir()
    rd = tmp_path / "routes"
    rd.mkdir()
    s = Settings(data_dir=tmp_path / "data", public_port=80, frontend_origins=ORIGIN,
                 status_hz=20.0, settings_dir=tmp_path / "settings", zones_dir=zd,
                 routes_dir=rd, flows_config_dir=REPO / "config" / "flows")  # fmt: skip
    app = create_app(s, capture_factory=NoCapture, input_factory=NoInput)
    c = TestClient(app, client=LAN)
    c.__enter__()
    c.zones_dir = zd  # type: ignore[attr-defined]
    c.routes_dir = rd  # type: ignore[attr-defined]
    yield c
    c.__exit__(None, None, None)


def _hdr(c: Any) -> dict[str, str]:
    from poring_backend import routes_settings

    return {"origin": "http://lab.test:3000",
            "x-csrf-token": routes_settings.csrf_token(c.app.state.poring)}  # fmt: skip


FIELD_TEXT = (
    'map: field_1\nreviewed_by: "batt"\nreviewed: 2026-10-21\nno_cross:\n  - id: a\n'
    '    note: "x"\n    points: [[5, 5], [9, 5]]\n'
)


def test_the_check_route_runs_the_loader_and_writes_nothing(zclient: Any) -> None:
    body = {"map": "field_1", "yaml": FIELD_TEXT, "world": "sample"}
    r = zclient.post("/flows/zones/check", json=body, headers=_hdr(zclient))
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["ok"] and d["sha256"] == hashlib.sha256(FIELD_TEXT.encode()).hexdigest()
    assert d["shape"] == [100, 100] and d["area"]["walkable"] > 0
    assert d["committed"]["exists"] is False
    bad = {**body, "yaml": FIELD_TEXT.replace("[9, 5]", "[9, 500]")}
    e = zclient.post("/flows/zones/check", json=bad, headers=_hdr(zclient)).json()
    assert e["ok"] is False
    assert e["error"] == ("config/map_zones/field_1.yaml: no_cross 'a' point 1: (9, 500) is off "
                          "the map (100 x 100 cells)")  # fmt: skip
    assert list(zclient.zones_dir.iterdir()) == []


def test_the_check_route_keeps_the_flows_gates(
    zclient: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    body = {"map": "field_1", "yaml": FIELD_TEXT, "world": "sample"}
    no_csrf = zclient.post(
        "/flows/zones/check", json=body, headers={"origin": "http://lab.test:3000"}
    )
    assert no_csrf.status_code == 403 and no_csrf.json()["detail"]["reason"] == "csrf_invalid"
    bad_origin = zclient.post("/flows/zones/check", json=body,
                              headers={**_hdr(zclient), "origin": "http://evil.test"})  # fmt: skip
    assert bad_origin.status_code == 403
    big = {**body, "yaml": "#" * (1 << 20) + "\n"}
    assert zclient.post("/flows/zones/check", json=big, headers=_hdr(zclient)).status_code == 413
    odd = {**body, "map": "../etc"}
    assert zclient.post("/flows/zones/check", json=odd, headers=_hdr(zclient)).status_code == 422
    extra = {**body, "save": True}
    assert zclient.post("/flows/zones/check", json=extra, headers=_hdr(zclient)).status_code == 422
    monkeypatch.setattr(flows_zones, "engine", lambda code_dir: None)
    r = zclient.post("/flows/zones/check", json=body, headers=_hdr(zclient))
    assert r.status_code == 503 and r.json()["detail"]["reason"] == "zones_engine_unavailable"


def test_the_file_route_gives_the_editor_its_starting_point(zclient: Any) -> None:
    r = zclient.get("/flows/zones/file?map=field_1&source=sample", headers=_hdr(zclient))
    assert r.status_code == 200 and r.json()["file"]["exists"] is False
    (zclient.zones_dir / "field_1.yaml").write_text("# a note\n" + FIELD_TEXT, encoding="utf-8")
    d = zclient.get("/flows/zones/file?map=field_1&source=sample", headers=_hdr(zclient)).json()
    assert d["model"] == {"map": "field_1", "comment": ["a note"], "items": [
        {"kind": "no_cross", "id": "a", "note": "x", "points": [[5, 5], [9, 5]]}]}  # fmt: skip
    assert d["file"]["review"]["reviewed_by"] == "batt" and "reviewed_by" not in d["model"]
    assert zclient.get("/flows/zones/file?map=a/b", headers=_hdr(zclient)).status_code == 422


def test_lint_reads_the_zones_files_through_the_provider(zclient: Any) -> None:
    """B1's open point 2: the /flows routes pass the zones provider (fail closed without it)."""
    flow = json.loads((REPO / "packages/poring_flow/src/poring_flow/examples/town_warp_farm.json")
                      .read_text())  # fmt: skip
    (zclient.zones_dir / "field_1.yaml").write_text(FIELD_TEXT, encoding="utf-8")

    def lint(f: dict[str, Any]) -> dict[str, Any]:
        r = zclient.post("/flows/lint", json={"flow": f, "world": "sample"}, headers=_hdr(zclient))
        assert r.status_code == 200, r.text
        return dict(r.json())

    doc = lint(flow)
    rules = {f["rule"] for f in doc["findings"]}
    assert "zones_unreferenced" in rules
    assert not any("zones" in n and "unchecked" in n for n in doc["world_notes"])
    sha = hashlib.sha256(FIELD_TEXT.encode()).hexdigest()
    for b in flow["workflow"]["blocks"]:
        if b["map"]["map"] == "field_1":
            b["zones"] = {"map": "field_1", "sha256": sha}
    doc = lint(flow)
    assert not {f["rule"] for f in doc["findings"]} & {
        "zones_unreferenced",
        "zones_changed",
        "zones_missing",
        "zones_unreadable",
    }
    assert not any("zones" in r for r in doc["run"]["reasons"])


def test_lint_reads_the_patrol_routes_through_the_provider(zclient: Any) -> None:
    """The hunt block's search_route patrol_route (Batt 2026-10-22, plan section 7d): /flows/lint
    passes the routes provider (scripts/flow_routes.py over the runner's loader), so a map without
    a routes file is refused, a file the loader refuses is refused, and a good one passes."""
    flow = json.loads((REPO / "packages/poring_flow/src/poring_flow/examples/town_warp_farm.json")
                      .read_text())  # fmt: skip
    rules = {"strike": "arm_c@32", "engage_on_the_way": "on_the_way@19", "dead": "exp_line@48",
             "loot": "gm_fast_scan@54", "search": "heading_coverage@22",
             "search_route": "patrol_route"}  # fmt: skip
    hunt = {"block": "hunt", "concept": "combat.hunt", "kind": "action", "note": None,
            "on_fail": "stop", "outcome_to": None, "timeout_s": 600.0,
            "params": {k: {"kind": "lit", "value": v} for k, v in rules.items()}}  # fmt: skip
    farm = next(b for b in flow["workflow"]["blocks"] if b["map"]["map"] == "field_1")
    farm["main"].insert(0, hunt)

    def patrol(text: str | None) -> tuple[set[str], dict[str, Any]]:
        path = zclient.routes_dir / "field_1.yaml"
        path.unlink(missing_ok=True)
        if text is not None:
            path.write_text(text, encoding="utf-8")
        r = zclient.post("/flows/lint", json={"flow": flow, "world": "sample"},
                         headers=_hdr(zclient))  # fmt: skip
        assert r.status_code == 200, r.text
        doc = dict(r.json())
        return {f["rule"] for f in doc["findings"] if f["rule"].startswith("patrol_")}, doc

    good = ("map: field_1\nreviewed_by: batt\nreviewed: 2026-10-22\nsource: synthetic\n"
            "routes:\n  - id: ring\n    kind: loop\n    note: round\n"
            "    waypoints: [[5, 5], [10, 5], [10, 10]]\n")  # fmt: skip
    found, doc = patrol(None)
    assert found == {"patrol_route_missing"}
    assert not any("routes" in n and "unchecked" in n for n in doc["world_notes"])
    found, _ = patrol(good.replace("kind: loop", "kind: circle"))
    assert found == {"patrol_route_unreadable"}
    found, doc = patrol(good)
    assert found == set() and not any("routes" in r for r in doc["run"]["reasons"])


def test_the_catalogue_carries_the_hunt_blocks_rule_versions(zclient: Any) -> None:
    doc = zclient.get("/flows/catalogue", headers=_hdr(zclient)).json()
    hr = doc["hunt_rules"]
    assert doc["hunt_rules_error"] is None and hr["adopted"] == 56  # 4K (11-06); 55, 52 before
    assert [g["name"] for g in hr["groups"]] == ["engage", "dead_loot", "search", "stop"]
    assert hr["evidence"]["badges"] == ["one path (RDP), prt_fild08"]


def test_no_rule_index_no_rule_badges(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    from poring_backend.config import Settings
    from poring_backend.main import create_app

    sys.path.insert(0, str(Path(__file__).parent))
    from test_routes_flows import LAN, ORIGIN, NoCapture, NoInput

    s = Settings(data_dir=tmp_path / "data", public_port=80, frontend_origins=ORIGIN,
                 status_hz=20.0, settings_dir=tmp_path / "settings",
                 flows_config_dir=tmp_path / "nothing")  # fmt: skip
    with TestClient(create_app(s, capture_factory=NoCapture, input_factory=NoInput),
                    client=LAN) as c:  # fmt: skip
        doc = c.get("/flows/catalogue", headers={"origin": ORIGIN}).json()
    assert doc["hunt_rules"] is None and doc["hunt_rules_error"].startswith("FileNotFoundError")
    assert "hunt" in doc["blocks"]


def test_a_hostile_text_meets_the_checks_own_bounds_before_the_loader(tmp_path: Path) -> None:
    """The loader's polygon test is O(n^2) and its supercover scans each segment's box: the check
    refuses a text far past any real zones file BEFORE it runs, saying it is the editor's limit."""
    head = 'map: fix_map\nreviewed_by: "batt"\nreviewed: 2026-10-21\n'
    many = (
        head
        + "no_cross:\n"
        + "".join(
            f"  - id: n{i}\n    note: x\n    points: [[1, 1], [2, 2]]\n"
            for i in range(flows_zones.MAX_ITEMS + 1)
        )
    )
    long = (
        head
        + "no_enter:\n  - id: p\n    note: x\n    polygon: ["
        + ", ".join(f"[{i}, {i % 7}]" for i in range(flows_zones.MAX_POINTS_PER_ITEM + 1))
        + "]\n"
    )
    huge = (
        head
        + "no_cross:\n"
        + "".join(
            f"  - id: d{i}\n    note: x\n    points: [[0, 0], [1000, 1000], [0, 1000]]\n"
            for i in range(4)
        )
    )
    for text, why in ((many, "items"), (long, "points"), (huge, "boxes")):
        r = flows_zones.check(ENG, text, "fix_map", None, tmp_path)
        assert r["ok"] is False and why in r["error"] and "an editor limit" in r["error"], r[
            "error"
        ]
    # a real file is far inside them: prt_fild08 and the corpus check as the loader says
    z = flows_zones.check(ENG, (CONFIG_ZONES / "prt_fild08.yaml").read_text(), "prt_fild08",
                          None, CONFIG_ZONES)  # fmt: skip
    assert z["ok"] and z["committed"]["same"]
