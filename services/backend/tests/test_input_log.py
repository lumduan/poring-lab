import json
from pathlib import Path

from poring_backend.input_log import InputLog, InputLogRecord
from poring_env.protocol import Mode


def record(t_wall: str, **overrides: object) -> InputLogRecord:
    base: dict[str, object] = {
        "t_mono_ns": 1,
        "t_wall": t_wall,
        "source": "human",
        "mode": Mode.HUMAN,
        "accepted": True,
        "reason": "ok",
        "synthetic": False,
        "frame_id": 3,
        "event": {"type": "key", "code": "KeyA", "action": "down"},
    }
    base.update(overrides)
    return InputLogRecord.model_validate(base)


def test_one_jsonl_file_per_utc_day(tmp_path: Path) -> None:
    log = InputLog(tmp_path)
    log.write(record("2026-09-29T23:59:59.999999+00:00"))
    log.write(record("2026-09-30T00:00:00.000001+00:00", source="bot", accepted=False))
    log.close()

    directory = tmp_path / "input_log"
    assert sorted(p.name for p in directory.iterdir()) == ["2026-09-29.jsonl", "2026-09-30.jsonl"]
    first = json.loads((directory / "2026-09-29.jsonl").read_text().splitlines()[0])
    assert first["source"] == "human" and first["frame_id"] == 3 and first["mode"] == "HUMAN"
    second = json.loads((directory / "2026-09-30.jsonl").read_text())
    assert (second["source"], second["accepted"]) == ("bot", False)


def test_appends_across_instances(tmp_path: Path) -> None:
    for _ in range(2):
        log = InputLog(tmp_path)
        log.write(record("2026-09-29T10:00:00+00:00"))
        log.close()
    assert len((tmp_path / "input_log" / "2026-09-29.jsonl").read_text().splitlines()) == 2
