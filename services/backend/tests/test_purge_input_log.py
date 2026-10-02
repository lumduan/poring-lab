"""scripts/purge_input_log.py: human typing and paste digests leave the logs; everything else, and
the order of the rest, stays -- and a concurrently appending backend is never interleaved."""

import importlib.util
import json
from pathlib import Path
from types import ModuleType

import pytest

from poring_backend.input_log import DailyJsonl

SCRIPTS = Path(__file__).resolve().parents[3] / "scripts"


@pytest.fixture
def purge() -> ModuleType:
    spec = importlib.util.spec_from_file_location("purge_input_log", SCRIPTS / "purge_input_log.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def rec(source: str, event: dict[str, object]) -> str:
    return json.dumps({"source": source, "event": event}, separators=(",", ":"))


def write(path: Path, lines: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(f"{line}\n" for line in lines))


@pytest.fixture
def data(tmp_path: Path) -> Path:
    write(
        tmp_path / "input_log" / "2026-10-02.jsonl",
        [
            rec("human", {"type": "key", "code": "KeyP", "action": "down"}),
            rec("human", {"type": "key", "code": "Digit4", "action": "up"}),
            rec("human", {"type": "key", "code": "Enter", "action": "down"}),
            rec("human", {"type": "key", "code": "ShiftLeft", "action": "down"}),
            rec("human", {"type": "key", "action": "down", "secret": True}),
            rec("human", {"type": "mouse_move", "x": 0.5, "y": 0.5}),
            rec("bot", {"type": "key", "code": "KeyQ", "action": "down"}),
            rec("human", {"type": "clipboard_paste", "chars": 9, "bytes": 9, "sha256": "ab" * 32}),
        ],
    )
    write(
        tmp_path / "transfer_log" / "2026-10-02.jsonl",
        [
            json.dumps({"action": "paste", "size": 9, "sha256": "abcdef012345", "ok": True}),
            json.dumps({"action": "upload", "name": "a.png", "size": 5, "sha256": "f" * 64}),
        ],
    )
    return tmp_path


def test_dry_run_writes_nothing(
    purge: ModuleType, data: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    before = {p: p.read_text() for p in data.rglob("*.jsonl")}
    assert purge.main(["--data", str(data)]) == 0
    assert {p: p.read_text() for p in data.rglob("*.jsonl")} == before
    out = capsys.readouterr().out
    assert "'human_printable_keys_deleted': 2" in out and "dry run" in out


def test_apply_removes_printable_human_keys_and_redacts_pastes(
    purge: ModuleType, data: Path
) -> None:
    assert purge.main(["--data", str(data), "--apply"]) == 0
    events = [
        json.loads(line)["event"]
        for line in (data / "input_log" / "2026-10-02.jsonl").read_text().splitlines()
    ]
    codes = [e.get("code") for e in events if e["type"] == "key"]
    assert codes == [
        "Enter",
        "ShiftLeft",
        None,
        "KeyQ",
    ]  # printable human keys gone, bot kept, order kept
    assert {"type": "clipboard_paste", "redacted": True} in events
    assert not any("sha256" in e or "chars" in e for e in events)
    audits = [
        json.loads(line)
        for line in (data / "transfer_log" / "2026-10-02.jsonl").read_text().splitlines()
    ]
    paste, upload = audits
    assert paste["sha256"] is None and paste["size"] == 0 and paste["redacted"] is True
    assert upload["sha256"] == "f" * 64  # a file's digest is not a secret
    on_disk = "".join(p.read_text() for p in data.rglob("*.jsonl"))
    assert "KeyP" not in on_disk and "Digit4" not in on_disk and "abcdef012345" not in on_disk


def test_apply_is_idempotent(
    purge: ModuleType, data: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    purge.main(["--data", str(data), "--apply"])
    capsys.readouterr()
    purge.main(["--data", str(data), "--apply"])
    assert "PURGED: {'human_keys': 3}" in capsys.readouterr().out  # nothing left to delete


def test_a_backend_still_appending_continues_after_the_rewrite(
    purge: ModuleType, data: Path
) -> None:
    """The writer's fd stays open across the purge (same inode, O_APPEND): its next line lands at
    the new end of the file, intact."""
    writer = DailyJsonl(data / "input_log")
    writer.append("2026-10-02", rec("human", {"type": "mouse_move", "x": 0.1, "y": 0.1}))
    purge.main(["--data", str(data), "--apply"])
    writer.append("2026-10-02", rec("human", {"type": "mouse_move", "x": 0.9, "y": 0.9}))
    writer.close()
    lines = (data / "input_log" / "2026-10-02.jsonl").read_text().splitlines()
    assert all(json.loads(line) for line in lines)  # no torn or interleaved line
    assert json.loads(lines[-1])["event"]["x"] == 0.9
    assert sum('"x":0.1' in line for line in lines) == 1
