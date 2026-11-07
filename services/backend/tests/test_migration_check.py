"""scripts/migration_check.py: the comparisons that decide "poring-lab arrived whole" (pure)."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))

import migration_check as mc  # noqa: E402


def status(rows: list[dict[str, str]]) -> dict[str, str]:
    return {r["item"]: r["status"] for r in rows}


def test_env_is_compared_by_salted_hashes_never_values() -> None:
    src = mc.parse_env(
        "# c\nDB_PASSWORD=s3cret\nHOST_LAN_IP=192.168.1.13\nWIN_HOST=192.168.1.169\n"
    )
    want = {k: mc.salted("salt", v) for k, v in src.items()}
    assert "s3cret" not in str(want)
    tgt = {"DB_PASSWORD": "s3cret", "HOST_LAN_IP": "192.168.1.228", "WIN_HOST": "",
           "LAB_HOST_PROFILE": "dedicated-intel", "VISION_MAX_VRAM_FRACTION": "1.0"}  # fmt: skip
    s = status(mc.env_rows(want, tgt, "salt", "prep"))
    assert set(s.values()) == {"PASS"}
    s2 = status(mc.env_rows(want, {**tgt, "DB_PASSWORD": "other"}, "salt", "prep"))
    assert s2["env: the values equal (salted hashes)"] == "FAIL"
    nothing = status(mc.env_rows(want, {}, "salt", "prep"))  # an empty target proves nothing
    assert nothing["env: the values equal (salted hashes)"] == "FAIL"
    shared = status(mc.env_rows(want, {**tgt, "LAB_HOST_PROFILE": ""}, "salt", "prep"))
    assert shared["env: LAB_HOST_PROFILE=dedicated-intel (ADR-0022)"] == "FAIL"
    capped = status(mc.env_rows(want, {**tgt, "VISION_MAX_VRAM_FRACTION": "0.25"}, "salt", "prep"))
    assert capped["env: VISION_MAX_VRAM_FRACTION=1.0 (a dedicated GPU)"] == "FAIL"


def test_win_host_empty_before_the_cutover_and_set_after() -> None:
    want = {"WIN_HOST": mc.salted("s", "192.168.1.169")}
    base = {"HOST_LAN_IP": "192.168.1.228"}
    prep_bad = status(mc.env_rows(want, {**base, "WIN_HOST": "192.168.1.169"}, "s", "prep"))
    assert prep_bad["env: WIN_HOST EMPTY before the cutover (ADR-0001: one session)"] == "FAIL"
    final_ok = status(mc.env_rows(want, {**base, "WIN_HOST": "192.168.1.169"}, "s", "final"))
    assert final_ok["env: WIN_HOST set after the cutover"] == "PASS"
    assert status(mc.env_rows(want, {"HOST_LAN_IP": "192.168.1.13"}, "s", "prep"))[
        "env: HOST_LAN_IP is the target's"] == "FAIL"  # fmt: skip


def test_trees_need_every_file_with_the_same_size_and_hash() -> None:
    want = {"a": {"size": 3, "sha256": "x"}, "b": {"size": 5}}
    assert status(mc.tree_rows("t", want, {"a": {"size": 3, "sha256": "x"}, "b": {"size": 5}})) \
        == {"t: every file arrived, the same": "PASS"}  # fmt: skip
    assert status(mc.tree_rows("t", want, {"a": {"size": 3, "sha256": "y"}, "b": {"size": 5}})) \
        == {"t: every file arrived, the same": "FAIL"}  # fmt: skip
    assert status(mc.tree_rows("t", want, {"a": {"size": 3, "sha256": "x"}})) \
        == {"t: every file arrived, the same": "FAIL"}  # fmt: skip
    empty = mc.tree_rows("t", {}, {"a": {"size": 3}})  # an empty source proves nothing
    assert status(empty) == {"t: every file arrived, the same": "FAIL"}


def test_a_runtime_item_is_a_directory_or_one_file_hashed(tmp_path: Path) -> None:
    (tmp_path / "poring-lab-tmp" / "gat" / "data").mkdir(parents=True)
    (tmp_path / "poring-lab-tmp" / "gat" / "data" / "m.gat").write_bytes(b"GRAT")
    (tmp_path / "poring-lab-tmp" / "chat-guard.json").write_text("{}")
    d = mc.runtime_tree("poring-lab-tmp/gat", tmp_path)
    assert list(d) == ["poring-lab-tmp/gat/data/m.gat"] and d[next(iter(d))]["sha256"]
    f = mc.runtime_tree("poring-lab-tmp/chat-guard.json", tmp_path)
    assert f == {"poring-lab-tmp/chat-guard.json": {"size": 2, "sha256": mc.sha256_file(
        tmp_path / "poring-lab-tmp" / "chat-guard.json")}}  # fmt: skip
    assert mc.runtime_tree("poring-lab-tmp/absent", tmp_path) == {}
    assert "poring-lab-tmp/chat-guard.json" in mc.RUNTIME and "poring-lab-pktgen" not in mc.RUNTIME


def test_networks_must_be_pinned_off_the_home_ranges() -> None:
    assert mc.pinned(["10.210.96.0/24", "10.210.97.0/24"]) == (True, [])
    assert mc.pinned(["192.168.96.0/20"])[0] is False  # the 2026-09-29 outage's range
    assert mc.pinned(["172.18.0.0/16"])[0] is False
    assert mc.pinned(["10.211.0.0/24"])[0] is False  # outside the pool


def test_every_source_image_is_needed_vision_as_its_intel_image() -> None:
    want = ["poring-lab/backend:local", "poring-lab/vision:local", "mariadb:11.8.9"]
    have = ["poring-lab/backend:local", "poring-lab/vision-intel:local", "mariadb:11.8.9"]
    assert status(mc.image_rows(want, have))[
        "docker: every image the source ran, built here (vision: Intel)"] == "PASS"  # fmt: skip
    assert "FAIL" in status(mc.image_rows(want, have[:1])).values()


def test_the_agent_must_arrive_whole() -> None:
    skills = {"bilingual-report": {"SKILL.md": "k"}}
    src = {"memory": {"a.md": "h1", "MEMORY.md": "h2"}, "history": {"s.jsonl": 100},
           "sessions": {"s": {"subagents": 3, "tool_results": 1}},
           "claude_md": "Batt's rules\n", "skills": skills}  # fmt: skip
    tgt = {**src, "history": {"s.jsonl": 150},
           "claude_md": mc.PREFACE_MARK + " ...\n---\nBatt's rules\n"}  # fmt: skip
    assert set(status(mc.claude_rows(src, tgt)).values()) == {"PASS"}
    short = {**tgt, "history": {"s.jsonl": 99}}
    assert status(mc.claude_rows(src, short))[
        "agent: the history (every transcript, at least as long)"] == "FAIL"  # fmt: skip
    edited = {**tgt, "memory": {"a.md": "CHANGED", "MEMORY.md": "h2"}}
    assert status(mc.claude_rows(src, edited))["agent: memory files identical"] == "FAIL"
    no_preface = {**tgt, "claude_md": "Batt's rules\n"}
    assert status(mc.claude_rows(src, no_preface))[
        "agent: Batt's CLAUDE.md verbatim under the bot-server preface"] == "FAIL"  # fmt: skip
